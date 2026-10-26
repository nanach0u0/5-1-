"""LINE に送るメッセージ（クイックリプライ）と、ボタンの postback データを組み立てる。

会話の状態はサーバーに持たず、postback データに入れる（requirements.md 6章）。
postback データは300文字までなので、レシピIDは末尾12文字に縮める。
Notion のページIDは先頭が作成時刻で、同じ時期に作ったページは先頭がそろうため、末尾を使う。
"""

import json
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from notion_repo import Log
from recipe import RATING_BAD, RATING_GOOD, RATING_SO_SO, Recipe
from recommender import ALLOWED_EFFORTS, MOODS, Proposal

POSTBACK_LIMIT = 300

# 「別のがいい」で引き直せる回数。これを超えたら、これまでの提案を並べて終える
MAX_REROLLS = 2

# 提案の履歴。round（1回の提案）ごとに、セット（[メインのキー, 副菜のキー]）のリスト
History = list[list[list[str]]]


def short_id(recipe: Recipe) -> str:
    return recipe.id.replace("-", "")[-12:]


def encode(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text) > POSTBACK_LIMIT:
        raise ValueError(f"postback データが {len(text)} 文字で上限を超えています")
    return text


def decode(text: str) -> dict:
    return json.loads(text)


def _postback(label: str, data: dict) -> dict:
    return {
        "type": "action",
        "action": {"type": "postback", "label": label, "data": encode(data), "displayText": label},
    }


def _text(text: str, buttons: Optional[list[dict]] = None) -> dict:
    message: dict = {"type": "text", "text": text}
    if buttons:
        message["quickReply"] = {"items": buttons}
    return message


def ask_condition() -> dict:
    return _text(
        "今日のコンディションは？",
        [_postback(c, {"a": "cond", "c": c}) for c in ALLOWED_EFFORTS],
    )


def ask_mood(condition: str) -> dict:
    return _text(
        "気分は？",
        [_postback(m, {"a": "mood", "c": condition, "m": m}) for m in MOODS],
    )


# 共有元の記録などに使われる、開くのに不要なクエリ
TRACKING_PARAMS = {"si", "igsh", "igshid", "fbclid", "img_index", "stkn"}
# クックパッドの URL 末尾の料理名（例: /recipes/18978075-しょうが焼き）
COOKPAD_SLUG = re.compile(r"^(/jp/recipes/\d+)-.+$")


def short_url(url: str) -> str:
    """LINE で何行にもならないよう、開くのに不要な部分を取り除く。"""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in TRACKING_PARAMS and not k.startswith("utm_")
    ]
    path = parts.path
    if parts.netloc.endswith("cookpad.com"):
        path = COOKPAD_SLUG.sub(r"\1", path)
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _set_lines(p: Proposal) -> list[str]:
    lines = []
    for icon, r in (("🍖", p.main), ("🥗", p.side)):
        if r is None:
            continue
        if r.is_untried:
            lines.append(f"🆕 {r.name}（まだ作ったことないレシピ）")
        else:
            lines.append(f"{icon} {r.name}")
        if r.url:
            lines.append(f"   {short_url(r.url)}")
    if p.with_rice:
        lines.append("（ごはんと一緒に）")
    if p.reason:
        lines.append(f"→ {p.reason}")
    return lines


def to_round(proposals: list[Proposal]) -> list[list[str]]:
    return [[short_id(r) for r in p.recipes] for p in proposals]


def proposal_message(
    proposals: list[Proposal], condition: str, mood: str, history: History
) -> dict:
    """提案メッセージ。history は今回の提案を含めたこれまでの提案。"""
    current = history[-1]
    more = _postback("別のがいい", {"a": "more", "c": condition, "m": mood, "h": history})

    if len(proposals) == 1:
        text = "\n".join(["今日はこれどう？", *_set_lines(proposals[0])])
        return _text(text, [_postback("これにする", {"a": "pick", "s": current[0]}), more])

    challenge, regular = proposals
    text = "\n".join(
        [
            f"今日は{condition}！どっちにする？",
            "",
            "【A】作ってみない？",
            *_set_lines(challenge),
            "",
            "【B】いつもの一軍",
            *_set_lines(regular),
        ]
    )
    return _text(
        text,
        [
            _postback("Aにする", {"a": "pick", "s": current[0]}),
            _postback("Bにする", {"a": "pick", "s": current[1]}),
            more,
        ],
    )


def final_list_message(sets: list[list[Recipe]]) -> dict:
    """引き直しの上限に達したとき、これまでの提案を並べて終える。"""
    lines = ["今日はこの中から決めちゃおう"]
    for i, recipes in enumerate(sets, 1):
        lines.append(f"{i}. " + "＋".join(r.name for r in recipes))
    return _text("\n".join(lines))


def no_candidates_message() -> dict:
    return _text("条件に合うレシピが見つかりませんでした。Notion のレシピを見直してみてください")


def decided_message() -> dict:
    return _text("いってらっしゃい！")


def confirm_message(log: Log) -> dict:
    """[これにする]から約90分後に送る「作った？」。"""
    return _text(
        f"さっき決めた「{log.menu}」、作った？",
        [
            _postback("作った", {"a": "made", "l": log.id}),
            _postback("作ってない", {"a": "notmade", "l": log.id}),
        ],
    )


def made_message(untried: Optional[Recipe]) -> dict:
    """[作った]への返事。作ったことないレシピが含まれていたら評価を聞く。"""
    text = "おつかれさま！記録しておきました"
    if untried is None:
        return _text(text)
    return _text(
        f"{text}\n初めての「{untried.name}」、どうだった？",
        [
            _postback(v, {"a": "rate", "r": untried.id, "v": v})
            for v in (RATING_GOOD, RATING_SO_SO, RATING_BAD)
        ],
    )


def not_made_message() -> dict:
    return _text("了解！また今度作りましょう")


def already_recorded_message() -> dict:
    return _text("この献立はもう記録してあります")


RATED_TEXT = {
    RATING_GOOD: "一軍入り！次から候補に入れておきます",
    RATING_SO_SO: "了解、記録しておきました。これからは候補に出さないでおきます",
    RATING_BAD: "残念…記録しておきました。もう提案しません",
}


def rated_message(rating: str) -> dict:
    return _text(RATED_TEXT[rating])


def help_message() -> dict:
    return _text("「何食べよう」と送ってくれたら、今日の献立を提案します")

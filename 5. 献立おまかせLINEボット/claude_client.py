"""Claude で献立の最終選択と、自由文の読み替えを行う（requirements.md 3.1, 4.3）。

選べるIDは JSON スキーマの enum で候補一覧に限定する。組み合わせのルール違反は
recommender.is_valid で弾き、ランダム選択に切り替える。
"""

import json
from typing import Optional

import anthropic

from recipe import Recipe
from recommender import ALLOWED_EFFORTS, CONDITION_RELAXED, MOODS, Pools, Proposal

MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000
# 拒否されたときに Anthropic 推奨のモデルで自動的にやり直す
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SELECT_SYSTEM = """あなたは、疲れている人の代わりに今日の夕食を決めるアシスタントです。
候補一覧（すべて本人が実際に作っておいしかった、または作ってみたいレシピ）の中から、
今日の気分に合うメインと副菜の組み合わせを選びます。

- 気分「がっつり」: 肉・揚げ物・味の濃いもの・ボリュームのあるメインを優先する
- 気分「さっぱり」: 魚・野菜が多いもの・あっさりした味・麺類などを優先する
- 気分「なんでも」: 気分は問わず、組み合わせのバランスがよいものを選ぶ
- メインと副菜は、味や食感がかぶらず、一緒に食べておいしい組み合わせにする
- 一品完結のメインには、手間が「ラク」の副菜だけを合わせる
- reason は、なぜこの組み合わせなのかを20〜40文字の1文で、親しみやすく書く（例: 手間が少なく、がっつり食べられます）"""

CHALLENGE_RULES = """
今日は余裕がある日なので、2セット選びます。
- challenge: 「作ってみたい」セット。🆕（まだ作ったことない）のレシピをちょうど1品だけ含める。もう1品は一軍から選ぶ
- regular: 一軍だけのセット
- challenge と regular で同じレシピは使わない"""

INTERPRET_SYSTEM = """ユーザーが夕食について送ってきた文章から、今日のコンディションと気分を読み取ります。
- condition: ヘトヘト（疲れている・作る気力がない）／ふつう／余裕あり（時間や元気がある）
- mood: がっつり（肉・こってり・たくさん食べたい）／さっぱり（あっさり・軽め）／なんでも（特にこだわりなし）
はっきりしないときは condition は「ふつう」、mood は「なんでも」にする。
- about_meal: 今日の食事・献立の相談として読めるなら true。お礼やあいさつなど、食事と関係ない文章なら false"""


def _client(client: Optional[anthropic.Anthropic]) -> anthropic.Anthropic:
    return client or anthropic.Anthropic()


def _ask_json(client: anthropic.Anthropic, system: str, user: str, schema: dict) -> dict:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"Claude の応答が完了しませんでした: stop_reason={response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def _line(r: Recipe) -> str:
    label = "🆕" if r.is_untried else "一軍"
    one_dish = "／一品完結" if r.one_dish else ""
    return f"- {r.id}: {r.name}（{label}／手間: {r.effort}{one_dish}）"


def _id_schema(recipes: list[Recipe], nullable: bool) -> dict:
    ids = [r.id for r in recipes]
    if not nullable:
        return {"type": "string", "enum": ids}
    if not ids:
        return {"type": "null"}
    return {"anyOf": [{"type": "string", "enum": ids}, {"type": "null"}]}


def _set_schema(mains: list[Recipe], sides: list[Recipe]) -> dict:
    return {
        "type": "object",
        "properties": {
            "main_id": _id_schema(mains, nullable=False),
            "side_id": _id_schema(sides, nullable=True),
            "reason": {"type": "string"},
        },
        "required": ["main_id", "side_id", "reason"],
        "additionalProperties": False,
    }


def _can_challenge(pools: Pools) -> bool:
    return bool(
        (pools.untried_mains and pools.first_sides) or (pools.untried_sides and pools.first_mains)
    )


def select_menu(
    pools: Pools, condition: str, mood: str, client: Optional[anthropic.Anthropic] = None
) -> list[Proposal]:
    """候補から気分に合う献立を選ぶ。余裕ありで作ったことないレシピがあれば
    [作ってみたいセット, 一軍セット] を返す。recommender.suggest の selector として使う。
    """
    challenge = condition == CONDITION_RELAXED and _can_challenge(pools)
    all_mains = pools.first_mains + pools.untried_mains
    all_sides = pools.first_sides + pools.untried_sides

    properties = {"regular": _set_schema(pools.first_mains, pools.first_sides)}
    if challenge:
        properties["challenge"] = _set_schema(all_mains, all_sides)
    schema = {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }

    shown_mains = all_mains if challenge else pools.first_mains
    shown_sides = all_sides if challenge else pools.first_sides
    user = "\n".join(
        [
            f"今日のコンディション: {condition}",
            f"今日の気分: {mood}",
            "",
            "メインの候補:",
            *map(_line, shown_mains),
            "",
            "副菜の候補:",
            *(map(_line, shown_sides) if shown_sides else ["（なし。side_id は null）"]),
        ]
    )
    data = _ask_json(
        _client(client), SELECT_SYSTEM + (CHALLENGE_RULES if challenge else ""), user, schema
    )

    by_id = {r.id: r for r in all_mains + all_sides}

    def to_proposal(d: dict, is_challenge: bool) -> Proposal:
        side = by_id[d["side_id"]] if d["side_id"] else None
        return Proposal(
            main=by_id[d["main_id"]], side=side, challenge=is_challenge, reason=d["reason"].strip()
        )

    proposals = [to_proposal(data["challenge"], True)] if challenge else []
    proposals.append(to_proposal(data["regular"], False))
    return proposals


def interpret(
    text: str, client: Optional[anthropic.Anthropic] = None
) -> Optional[tuple[str, str]]:
    """「疲れたけど肉食べたい」のような自由文を (コンディション, 気分) に読み替える。
    食事と関係ない文章なら None。
    """
    schema = {
        "type": "object",
        "properties": {
            "condition": {"type": "string", "enum": list(ALLOWED_EFFORTS)},
            "mood": {"type": "string", "enum": list(MOODS)},
            "about_meal": {"type": "boolean"},
        },
        "required": ["condition", "mood", "about_meal"],
        "additionalProperties": False,
    }
    data = _ask_json(_client(client), INTERPRET_SYSTEM, text, schema)
    if not data["about_meal"]:
        return None
    return data["condition"], data["mood"]

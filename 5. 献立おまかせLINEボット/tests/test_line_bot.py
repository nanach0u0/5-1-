"""LINE の会話フロー（main.Bot）と Webhook 受け口のテスト。LINE・Notion・Claude は呼ばない。"""

import base64
import hashlib
import hmac
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import line_messages as msg
import main
from config import JST
from line_api import verify_signature
from notion_repo import Log
from recipe import SIDE
from tests.test_recommender import TODAY, make

NOW = datetime(2026, 10, 24, 18, 0, tzinfo=JST)


class FakeStore:
    """Notion の代わりに、記録・更新をメモリに残す。"""

    def __init__(self, recipes):
        self.recipes = {r.id: r for r in recipes}
        self.logs: dict[str, Log] = {}
        self.last_made: dict[str, object] = {}
        self.ratings: dict[str, str] = {}

    def create_log(self, recipes, decided_at):
        log_id = f"log-{len(self.logs) + 1}"
        title = f"{decided_at.date()} " + "＋".join(r.name for r in recipes)
        self.logs[log_id] = Log(log_id, title, [r.id for r in recipes], "確認待ち")
        self.decided_at = decided_at
        return log_id

    def fetch_log(self, log_id):
        return self.logs[log_id]

    def update_log(self, log_id, status):
        log = self.logs[log_id]
        self.logs[log_id] = Log(log.id, log.title, log.recipe_ids, status)

    def fetch_recipe(self, recipe_id):
        return self.recipes.get(recipe_id)

    def set_last_made(self, recipe_id, day):
        self.last_made[recipe_id] = day

    def set_rating(self, recipe_id, rating):
        self.ratings[recipe_id] = rating


def recipes():
    # 実際の Notion のページIDと同じく、先頭（作成時刻）がそろい、末尾だけが違う形にする
    def uid(n):
        return f"4039d529-dc1f-81b5-b59b-{n:012x}"

    mains = [make(uid(i), effort="ラク") for i in range(1, 6)]
    sides = [make(uid(i), role=SIDE) for i in range(11, 14)]
    untried = [make(uid(21), rating=None), make(uid(22), role=SIDE, rating=None)]
    return mains + sides + untried


def make_bot(interpret=lambda text: ("ヘトヘト", "がっつり")):
    data = recipes()
    return main.Bot(
        load_recipes=lambda: data,
        select=None,
        interpret=interpret,
        now=lambda: NOW,
        store=FakeStore(data),
    )


def buttons(message):
    return [
        (item["action"]["label"], msg.decode(item["action"]["data"]))
        for item in message["quickReply"]["items"]
    ]


def press(bot, message, label):
    [data] = [d for lbl, d in buttons(message) if lbl == label]
    [reply] = bot.handle_postback(msg.encode(data))
    return reply


# --- 会話フロー -------------------------------------------------------------


def test_button_flow_to_decision():
    bot = make_bot()
    [m] = bot.handle_text("今日何食べよう")
    assert [lbl for lbl, _ in buttons(m)] == ["ヘトヘト", "ふつう", "余裕あり"]

    m = press(bot, m, "ヘトヘト")
    assert [lbl for lbl, _ in buttons(m)] == ["がっつり", "さっぱり", "なんでも"]

    m = press(bot, m, "がっつり")
    assert m["text"].startswith("今日はこれどう？")
    assert "（ごはんと一緒に）" in m["text"]
    assert [lbl for lbl, _ in buttons(m)] == ["これにする", "別のがいい"]

    assert press(bot, m, "これにする")["text"] == "いってらっしゃい！"


def shown_set(message) -> str:
    """提案メッセージに表示されたレシピ名を「メイン＋副菜」の形にする。"""
    names = [
        line.split(" ", 1)[1].removesuffix("（まだ作ったことないレシピ）")
        for line in message["text"].splitlines()
        if line.startswith(("🍖", "🥗", "🆕"))
    ]
    return "＋".join(names)


def test_reroll_twice_then_final_list():
    bot = make_bot()
    [m] = bot.handle_postback(msg.encode({"a": "mood", "c": "ヘトヘト", "m": "がっつり"}))
    shown = [shown_set(m)]
    for _ in range(msg.MAX_REROLLS):
        m = press(bot, m, "別のがいい")
        shown.append(shown_set(m))
    # 引き直しでは、これまでに提案したレシピは出ない
    names = [n for s in shown for n in s.split("＋")]
    assert len(names) == len(set(names))

    final = press(bot, m, "別のがいい")
    lines = final["text"].splitlines()
    assert lines[0] == "今日はこの中から決めちゃおう"
    # 最後の一覧は、実際に表示した提案と同じ
    assert [line.split(". ", 1)[1] for line in lines[1:]] == shown
    assert "quickReply" not in final


def test_relaxed_offers_a_or_b():
    bot = make_bot()
    [m] = bot.handle_postback(msg.encode({"a": "mood", "c": "余裕あり", "m": "なんでも"}))
    assert "【A】作ってみない？" in m["text"] and "【B】いつもの一軍" in m["text"]
    assert "🆕" in m["text"]
    assert [lbl for lbl, _ in buttons(m)] == ["Aにする", "Bにする", "別のがいい"]


def test_postback_fits_limit_after_max_rerolls_on_relaxed():
    bot = make_bot()
    [m] = bot.handle_postback(msg.encode({"a": "mood", "c": "余裕あり", "m": "がっつり"}))
    for _ in range(msg.MAX_REROLLS):
        m = press(bot, m, "別のがいい")  # encode が上限超えなら ValueError になる
    history = dict(buttons(m))["別のがいい"]["h"]
    assert len(history) == 3


def test_free_text_is_interpreted():
    bot = make_bot(interpret=lambda text: ("ヘトヘト", "がっつり"))
    [m] = bot.handle_text("疲れたけど肉食べたい")
    assert m["text"].startswith("今日はこれどう？")


def test_free_text_not_about_meal():
    [m] = make_bot(interpret=lambda text: None).handle_text("ありがとう")
    assert "何食べよう" in m["text"]


def test_free_text_falls_back_to_buttons_on_error():
    def broken(text):
        raise RuntimeError("API エラー")

    [m] = make_bot(interpret=broken).handle_text("疲れたけど肉食べたい")
    assert m["text"] == "今日のコンディションは？"


def test_no_candidates():
    bot = main.Bot(load_recipes=lambda: [], select=None, interpret=None, now=lambda: NOW)
    [m] = bot.handle_postback(msg.encode({"a": "mood", "c": "ヘトヘト", "m": "がっつり"}))
    assert "見つかりませんでした" in m["text"]


# --- 署名検証・Webhook ------------------------------------------------------

SECRET = "test-secret"


def sign(body: bytes, secret=SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_verify_signature():
    body = b'{"events":[]}'
    assert verify_signature(SECRET, body, sign(body))
    assert not verify_signature(SECRET, body, sign(body, "other"))
    assert not verify_signature("", body, sign(body, ""))  # 未設定なら必ず拒否


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setattr(main.config, "LINE_CHANNEL_SECRET", SECRET)
    monkeypatch.setattr(main.config, "LINE_USER_ID", "Ume")
    replies = []
    monkeypatch.setattr(main, "reply", lambda token, rt, messages: replies.append((rt, messages)))
    monkeypatch.setattr(main, "show_loading", lambda token, user: None)
    monkeypatch.setattr(main, "bot", make_bot())
    return TestClient(main.app), replies


def post(client, events):
    body = json.dumps({"events": events}).encode()
    return client.post("/callback", content=body, headers={"X-Line-Signature": sign(body)})


def text_event(user, text):
    return {
        "type": "message",
        "replyToken": "rt",
        "source": {"userId": user},
        "message": {"type": "text", "text": text},
    }


def test_webhook_replies_to_owner(webhook):
    client, replies = webhook
    assert post(client, [text_event("Ume", "何食べよう")]).status_code == 200
    [(reply_token, [m])] = replies
    assert reply_token == "rt" and m["text"] == "今日のコンディションは？"


def test_webhook_ignores_others(webhook):
    client, replies = webhook
    assert post(client, [text_event("Uother", "何食べよう")]).status_code == 200
    assert replies == []


def test_webhook_rejects_bad_signature(webhook):
    client, _ = webhook
    response = client.post("/callback", content=b'{"events":[]}', headers={"X-Line-Signature": "x"})
    assert response.status_code == 400


# --- URL の短縮 -------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://cookpad.com/jp/recipes/18978075-%E3%81%97%E3%82%87%E3%81%86%E3%81%8C%E7%84%BC%E3%81%8D",
            "https://cookpad.com/jp/recipes/18978075",
        ),
        (
            "https://cookpad.com/jp/recipes/17825374-%E3%81%94%E9%A3%AF#",
            "https://cookpad.com/jp/recipes/17825374",
        ),
        ("https://youtu.be/B2tS8Y7FDyQ?si=6WOwY72ag613nXm4", "https://youtu.be/B2tS8Y7FDyQ"),
        (
            "https://www.instagram.com/p/BxnvhO_HUR3/?utm_source=ig_web_copy_link&igshid=MzRlODBiNWFlZA==",
            "https://www.instagram.com/p/BxnvhO_HUR3/",
        ),
        ("https://kurelife.jp/recipe/0328293/?fbclid=PAZXh0", "https://kurelife.jp/recipe/0328293/"),
        # 開くのに必要なクエリは残す
        ("https://www.youtube.com/watch?v=abc123&si=xyz", "https://www.youtube.com/watch?v=abc123"),
        # 短くする必要のないものはそのまま
        ("https://www.kurashiru.com/recipes/6d35d433-54de", "https://www.kurashiru.com/recipes/6d35d433-54de"),
    ],
)
def test_short_url(url, expected):
    assert msg.short_url(url) == expected



# --- 献立ログと「作った？」（ステップ5） -----------------------------------


def decide(bot, condition="ヘトヘト", label="これにする"):
    """提案を出して決めるところまで進め、作られたログを返す。"""
    [m] = bot.handle_postback(msg.encode({"a": "mood", "c": condition, "m": "なんでも"}))
    assert press(bot, m, label)["text"] == "いってらっしゃい！"
    [log] = bot.store.logs.values()
    return log


def test_decision_creates_pending_log():
    bot = make_bot()
    log = decide(bot)
    assert log.status == "確認待ち"
    assert len(log.recipe_ids) == 2
    assert log.title.startswith("2026-10-24 ")
    assert bot.store.decided_at == NOW


def test_made_updates_recipes_and_log():
    bot = make_bot()
    log = decide(bot)
    [reply] = bot.handle_postback(msg.encode({"a": "made", "l": log.id}))
    assert reply["text"] == "おつかれさま！記録しておきました"
    assert "quickReply" not in reply  # 一軍だけなので評価は聞かない
    assert bot.store.last_made == {rid: NOW.date() for rid in log.recipe_ids}
    assert bot.store.logs[log.id].status == "作った"


def test_made_with_untried_recipe_asks_rating():
    bot = make_bot()
    log = decide(bot, condition="余裕あり", label="Aにする")  # A は作ったことないレシピを含む
    [reply] = bot.handle_postback(msg.encode({"a": "made", "l": log.id}))
    untried = [bot.store.recipes[r] for r in log.recipe_ids if bot.store.recipes[r].is_untried]
    assert len(untried) == 1
    assert f"初めての「{untried[0].name}」、どうだった？" in reply["text"]
    assert [lbl for lbl, _ in buttons(reply)] == ["おいしい", "ふつう", "残念"]

    rated = press(bot, reply, "おいしい")
    assert rated["text"] == "一軍入り！次から候補に入れておきます"
    assert bot.store.ratings == {untried[0].id: "おいしい"}


def test_not_made_changes_only_log():
    bot = make_bot()
    log = decide(bot)
    [reply] = bot.handle_postback(msg.encode({"a": "notmade", "l": log.id}))
    assert reply["text"] == "了解！また今度作りましょう"
    assert bot.store.last_made == {}
    assert bot.store.logs[log.id].status == "作ってない"


def test_answering_twice_does_not_update_again():
    bot = make_bot()
    log = decide(bot)
    bot.handle_postback(msg.encode({"a": "notmade", "l": log.id}))
    [reply] = bot.handle_postback(msg.encode({"a": "made", "l": log.id}))
    assert reply["text"] == "この献立はもう記録してあります"
    assert bot.store.last_made == {}
    assert bot.store.logs[log.id].status == "作ってない"


def test_confirm_message():
    log = Log("log-1", "2026-10-24 しょうが焼き＋漬け新玉ねぎ", ["r1", "r2"], "確認待ち")
    m = msg.confirm_message(log)
    assert m["text"] == "さっき決めた「しょうが焼き＋漬け新玉ねぎ」、作った？"
    assert buttons(m) == [("作った", {"a": "made", "l": "log-1"}), ("作ってない", {"a": "notmade", "l": "log-1"})]

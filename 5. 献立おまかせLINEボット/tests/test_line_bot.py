"""LINE の会話フロー（main.Bot）と Webhook 受け口のテスト。LINE・Notion・Claude は呼ばない。"""

import base64
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import line_messages as msg
import main
from line_api import verify_signature
from recipe import SIDE
from tests.test_recommender import TODAY, make


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
    return main.Bot(load_recipes=lambda: data, select=None, interpret=interpret, today=lambda: TODAY)


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
    bot = main.Bot(load_recipes=lambda: [], select=None, interpret=None, today=lambda: TODAY)
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

"""LINE Messaging API の呼び出し（署名検証・返信・ローディング表示）。"""

import base64
import hashlib
import hmac

import requests

LINE_API = "https://api.line.me/v2/bot"


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """X-Line-Signature が、チャネルシークレットで body を署名したものと一致するか。"""
    if not channel_secret:
        return False  # 未設定のまま受け付けると、誰でも署名を作れてしまう
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def reply(token: str, reply_token: str, messages: list[dict]) -> None:
    response = requests.post(
        f"{LINE_API}/message/reply",
        headers=_headers(token),
        json={"replyToken": reply_token, "messages": messages},
        timeout=10,
    )
    response.raise_for_status()


def push(token: str, user_id: str, messages: list[dict]) -> None:
    """こちらから送る（「作った？」の確認用）。無料プランの月間上限にカウントされる。"""
    response = requests.post(
        f"{LINE_API}/message/push",
        headers=_headers(token),
        json={"to": user_id, "messages": messages},
        timeout=10,
    )
    response.raise_for_status()


def show_loading(token: str, user_id: str, seconds: int = 20) -> None:
    """返信までの間、トーク画面に「…」を表示する（Claude の応答待ちが数秒かかるため）。"""
    requests.post(
        f"{LINE_API}/chat/loading/start",
        headers=_headers(token),
        json={"chatId": user_id, "loadingSeconds": seconds},
        timeout=10,
    )

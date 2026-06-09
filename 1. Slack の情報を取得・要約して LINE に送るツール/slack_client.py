import time
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def fetch_messages(token: str, channel_id: str, hours: int = 24) -> list[str]:
    """
    指定チャンネルから過去 hours 時間のメッセージを取得する。
    ボット投稿は除外し、テキストのみのリストを返す。
    エラー時は空リストを返す。
    """
    client = WebClient(token=token)
    oldest = str(time.time() - hours * 3600)

    try:
        response = client.conversations_history(
            channel=channel_id,
            oldest=oldest,
            limit=200,
        )
    except SlackApiError as e:
        print(f"[slack_client] SlackApiError: {e.response['error']}")
        return []

    messages = []
    for msg in response.get("messages", []):
        # ボット投稿（subtype あり、または bot_id あり）を除外
        if msg.get("subtype") or msg.get("bot_id"):
            continue
        text = msg.get("text", "").strip()
        if text:
            messages.append(text)

    return messages

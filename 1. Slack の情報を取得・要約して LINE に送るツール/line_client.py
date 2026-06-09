import requests

LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def send_line(token: str, message: str) -> int:
    """
    LINE Messaging API の broadcast でメッセージを送信する。
    戻り値は HTTP ステータスコード。
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ]
    }

    response = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload)
    return response.status_code

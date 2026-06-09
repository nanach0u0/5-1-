import anthropic

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 500

SYSTEM_PROMPT = (
    "あなたはSlackチャンネルの内容を簡潔に要約するアシスタントです。"
    "日本語で3〜5行にまとめ、重要な決定事項・アクション・期日を特に強調してください。"
    "箇条書きは使わず、自然な文章で要約してください。"
)


def summarize(messages: list[str]) -> str:
    """
    メッセージリストを Claude で要約して返す。
    メッセージが空の場合は固定文言を返す。
    """
    if not messages:
        return "新着メッセージはありません。"

    joined = "\n".join(f"- {m}" for m in messages)
    user_content = f"以下はSlackチャンネルの直近メッセージです。要約してください。\n\n{joined}"

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_content},
        ],
    )

    return response.content[0].text.strip()

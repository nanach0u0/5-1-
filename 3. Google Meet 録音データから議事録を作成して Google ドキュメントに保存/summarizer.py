import sys
import anthropic

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """あなたは会議の議事録作成を担当するアシスタントです。
提供された会議の文字起こしテキストを読み、以下のフォーマットで日本語の議事録を作成してください。

情報が文字起こしから読み取れない場合は「不明」と記載し、推測で補完しないでください。
決定事項やToDoがない場合は「なし」と記載してください。"""

USER_TEMPLATE = """以下の会議の文字起こしから議事録を作成してください。

【フォーマット】
■ 日時
（文字起こし内から推定、不明な場合は「不明」）

■ 参加者
（発言者名を抽出、不明な場合は「不明」）

■ 議題
（会議のメインテーマを1〜2文で）

■ 決定事項
・（箇条書き。なければ「なし」）

■ ToDo（担当と期日）
・担当者：内容（期日があれば記載。なければ「期日未定」。ToDoがなければ「なし」）

---

【文字起こし】
{transcript}"""


def summarize(transcript: str, api_key: str) -> str:
    if not transcript or not transcript.strip():
        return "文字起こし結果がありません。"

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": USER_TEMPLATE.format(transcript=transcript)}
            ],
        )
    except anthropic.AuthenticationError:
        print("[ERROR] Claude API 認証エラー: ANTHROPIC_API_KEY を確認してください。")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"[ERROR] Claude API エラー: {e}")
        sys.exit(1)

    for block in message.content:
        if block.type == "text":
            return block.text

    return ""

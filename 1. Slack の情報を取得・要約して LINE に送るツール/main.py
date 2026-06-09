import os
import sys
from dotenv import load_dotenv

from slack_client import fetch_messages
from summarizer import summarize
from line_client import send_line

load_dotenv()


def get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        print(f"[main] 環境変数 {key} が設定されていません。", file=sys.stderr)
        sys.exit(1)
    return value


def main():
    # --- 環境変数の読み込み ---
    slack_token = get_env("SLACK_BOT_TOKEN")
    channel_id = get_env("SLACK_CHANNEL_ID")
    anthropic_api_key = get_env("ANTHROPIC_API_KEY")
    line_token = get_env("LINE_CHANNEL_ACCESS_TOKEN")
    fetch_hours = int(os.getenv("FETCH_HOURS", "24"))

    # Anthropic SDK は環境変数 ANTHROPIC_API_KEY を自動参照するため設定
    os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key

    # --- 1. Slack メッセージ取得 ---
    print(f"[1/3] Slack チャンネル {channel_id} から過去 {fetch_hours} 時間のメッセージを取得中...")
    messages = fetch_messages(slack_token, channel_id, hours=fetch_hours)
    print(f"      取得件数: {len(messages)} 件")

    # --- 2. Claude で要約 ---
    print("[2/3] Claude で要約中...")
    summary = summarize(messages)
    print(f"      要約:\n{summary}")

    # --- 3. LINE に送信 ---
    print("[3/3] LINE に送信中...")
    status_code = send_line(line_token, summary)
    if status_code == 200:
        print(f"      送信成功 (HTTP {status_code})")
    else:
        print(f"      送信失敗 (HTTP {status_code})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

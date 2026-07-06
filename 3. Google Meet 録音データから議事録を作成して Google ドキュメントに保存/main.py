import os
from dotenv import load_dotenv
from loader import load_transcript
from summarizer import summarize
from docs_client import append_to_doc

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_DOC_ID = os.environ["GOOGLE_DOC_ID"]
TRANSCRIPT_FILE_PATH = os.getenv("TRANSCRIPT_FILE_PATH", "./transcript.txt")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")


def main() -> None:
    transcript = load_transcript(TRANSCRIPT_FILE_PATH)
    print(f"[読み込み] 文字起こしを読み込みました（{len(transcript):,} 文字）")

    minutes = summarize(transcript, api_key=ANTHROPIC_API_KEY)
    print("[要約]")
    print(minutes)

    success = append_to_doc(minutes, doc_id=GOOGLE_DOC_ID, credentials_path=GOOGLE_CREDENTIALS_PATH)
    if success:
        print("[書き込み結果] Google ドキュメントへの追記が完了しました。")


if __name__ == "__main__":
    main()

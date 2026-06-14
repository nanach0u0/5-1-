import os
from dotenv import load_dotenv
from fetcher import fetch_items
from processor import process_items
from sheets_client import append_rows

load_dotenv()

APPLICATION_ID = os.environ["RAKUTEN_APP_ID"]
ACCESS_KEY = os.environ["RAKUTEN_ACCESS_KEY"]
KEYWORD = os.environ["SEARCH_KEYWORD"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
CREDENTIALS_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]


def main():
    print(f"検索キーワード: {KEYWORD}")

    items = fetch_items(APPLICATION_ID, ACCESS_KEY, KEYWORD)
    print(f"取得件数: {len(items)} 件")

    if not items:
        return

    rows = process_items(items)
    written = append_rows(SPREADSHEET_ID, CREDENTIALS_PATH, rows)
    print(f"書き込み件数: {written} 件")


if __name__ == "__main__":
    main()

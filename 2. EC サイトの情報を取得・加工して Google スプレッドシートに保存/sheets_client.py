import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = ["商品名", "価格", "店舗名", "在庫", "レビュー件数", "商品URL", "取得日時"]


def _get_client(credentials_path: str) -> gspread.Client:
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)


def append_rows(
    spreadsheet_id: str,
    credentials_path: str,
    rows: list[list],
) -> int:
    try:
        client = _get_client(credentials_path)
        sheet = client.open_by_key(spreadsheet_id).sheet1

        existing = sheet.get_all_values()
        if not existing or existing[0] != HEADERS:
            sheet.insert_row(HEADERS, index=1)

        sheet.append_rows(rows, value_input_option="USER_ENTERED")
        return len(rows)
    except Exception as e:
        print(f"[sheets_client] シート書き込みエラー: {e}")
        return 0

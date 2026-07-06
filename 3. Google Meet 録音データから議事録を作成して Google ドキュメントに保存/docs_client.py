import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/documents"]


def _build_service(credentials_path: str):
    creds = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=SCOPES
    )
    return build("docs", "v1", credentials=creds)


def append_to_doc(minutes: str, doc_id: str, credentials_path: str) -> bool:
    try:
        service = _build_service(credentials_path)

        # 現在のドキュメント末尾インデックスを取得
        doc = service.documents().get(documentId=doc_id).execute()
        end_index = doc["body"]["content"][-1]["endIndex"] - 1

        requests = [
            {
                "insertText": {
                    "location": {"index": end_index},
                    "text": "\n\n" + minutes,
                }
            }
        ]

        service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

        return True

    except FileNotFoundError:
        print(f"[ERROR] {credentials_path} が見つかりません。サービスアカウントキーを配置してください。")
        sys.exit(1)
    except HttpError as e:
        status = e.resp.status
        if status == 403:
            print(
                "[ERROR] Google Docs API エラー: 403 Forbidden - "
                "サービスアカウントにドキュメントの編集権限があるか確認してください。"
            )
        elif status == 404:
            print(
                "[ERROR] Google Docs API エラー: 404 Not Found - "
                "GOOGLE_DOC_ID が正しいか確認してください。"
            )
        else:
            print(f"[ERROR] Google Docs API エラー: {e}")
        sys.exit(1)

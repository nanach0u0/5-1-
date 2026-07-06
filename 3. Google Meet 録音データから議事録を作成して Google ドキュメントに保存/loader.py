import sys
from pathlib import Path


def load_transcript(path: str) -> str:
    file = Path(path)

    if not file.exists():
        print(f"[ERROR] 文字起こしファイルが見つかりません: {path}")
        sys.exit(1)

    text = file.read_text(encoding="utf-8").strip()

    if not text:
        print(f"[ERROR] 文字起こしファイルの中身が空です: {path}")
        sys.exit(1)

    return text

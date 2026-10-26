"""followup.py のテスト。Notion・LINE は呼ばない。"""

from datetime import timedelta

import followup
from notion_repo import Log
from tests.test_line_bot import NOW


def test_sends_once_per_log_and_marks_sent(monkeypatch):
    logs = [
        Log("log-1", "2026-10-24 しょうが焼き＋漬け新玉ねぎ", ["r1", "r2"], "確認待ち"),
        Log("log-2", "2026-10-24 究極のレタスチャーハン＋ミニトマト", ["r3", "r4"], "確認待ち"),
    ]
    calls = []
    monkeypatch.setattr(
        followup,
        "find_logs_to_confirm",
        lambda token, ds, before: calls.append(("find", before)) or logs,
    )
    monkeypatch.setattr(followup, "push", lambda token, user, messages: calls.append(("push", messages[0]["text"])))
    monkeypatch.setattr(followup, "update_log", lambda token, log_id, sent: calls.append(("sent", log_id, sent)))

    assert followup.send_followups(NOW) == 2
    assert calls == [
        ("find", NOW - timedelta(minutes=90)),
        ("push", "さっき決めた「しょうが焼き＋漬け新玉ねぎ」、作った？"),
        ("sent", "log-1", True),
        ("push", "さっき決めた「究極のレタスチャーハン＋ミニトマト」、作った？"),
        ("sent", "log-2", True),
    ]

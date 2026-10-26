"""[これにする]から90分たった献立に「作った？」を送る（requirements.md 3.2）。

GitHub Actions から30分おきに実行する。使い方: python followup.py
"""

import logging
from datetime import datetime, timedelta

import config
import line_messages as msg
from line_api import push
from notion_repo import find_logs_to_confirm, update_log

# [これにする]から「作った？」を送るまでの時間
FOLLOWUP_DELAY = timedelta(minutes=90)

logger = logging.getLogger(__name__)


def send_followups(now: datetime) -> int:
    """送るべきログに「作った？」を送り、送った件数を返す。送信は1回だけで、再送はしない。"""
    logs = find_logs_to_confirm(config.NOTION_TOKEN, config.NOTION_LOG_DS_ID, now - FOLLOWUP_DELAY)
    for log in logs:
        push(config.LINE_CHANNEL_ACCESS_TOKEN, config.LINE_USER_ID, [msg.confirm_message(log)])
        update_log(config.NOTION_TOKEN, log.id, sent=True)
        logger.info("「作った？」を送りました: %s", log.title)
    return len(logs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = send_followups(datetime.now(config.JST))
    logger.info("%d 件送りました", count)

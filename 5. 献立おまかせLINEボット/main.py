"""LINE Webhook の受け口（requirements.md 3章, 6章）。

起動: uvicorn main:app --port 8000
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

import config
import line_messages as msg
from claude_client import interpret, select_menu
from line_api import reply, show_loading, verify_signature
import notion_repo
from notion_repo import STATUS_MADE, STATUS_NOT_MADE, STATUS_PENDING, Log
from recipe import RATING_BAD, RATING_GOOD, RATING_SO_SO, Recipe
from recommender import ALLOWED_EFFORTS, MOODS, Selector, suggest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# これを含むメッセージなら、ボタンで状態を聞くところから始める
TRIGGERS = ("何食べよう", "なに食べよう", "何食べる", "献立", "ごはん", "ご飯")


class NotionStore:
    """献立ログとレシピの更新（Bot から使う Notion の操作）。"""

    def __init__(self, token: str, log_data_source_id: str):
        self.token = token
        self.log_data_source_id = log_data_source_id

    def create_log(self, recipes: list[Recipe], decided_at: datetime) -> str:
        return notion_repo.create_log(self.token, self.log_data_source_id, recipes, decided_at)

    def fetch_log(self, log_id: str) -> Log:
        return notion_repo.fetch_log(self.token, log_id)

    def update_log(self, log_id: str, status: str) -> None:
        notion_repo.update_log(self.token, log_id, status=status)

    def fetch_recipe(self, recipe_id: str) -> Optional[Recipe]:
        return notion_repo.fetch_recipe(self.token, recipe_id)

    def set_last_made(self, recipe_id: str, day: date) -> None:
        notion_repo.set_last_made(self.token, recipe_id, day)

    def set_rating(self, recipe_id: str, rating: str) -> None:
        notion_repo.set_rating(self.token, recipe_id, rating)


@dataclass
class Bot:
    """会話の処理。外部サービスへの依存は差し替えられるようにしておく（テスト用）。"""

    load_recipes: Callable[[], list[Recipe]]
    select: Optional[Selector]
    interpret: Callable[[str], Optional[tuple[str, str]]]
    now: Callable[[], datetime]
    store: Optional[NotionStore] = None

    def handle_text(self, text: str) -> list[dict]:
        if any(t in text for t in TRIGGERS):
            return [msg.ask_condition()]
        try:
            interpreted = self.interpret(text)
        except Exception:
            logger.exception("自由文の読み替えに失敗したのでボタンで聞きます")
            return [msg.ask_condition()]
        if interpreted is None:
            return [msg.help_message()]
        condition, mood = interpreted
        return self._propose(condition, mood, [])

    def handle_postback(self, raw: str) -> list[dict]:
        data = msg.decode(raw)
        action = data.get("a")
        condition, mood = data.get("c"), data.get("m")
        if action == "cond" and condition in ALLOWED_EFFORTS:
            return [msg.ask_mood(condition)]
        if action == "mood" and condition in ALLOWED_EFFORTS and mood in MOODS:
            return self._propose(condition, mood, [])
        if action == "more" and condition in ALLOWED_EFFORTS and mood in MOODS:
            return self._more(condition, mood, data["h"])
        if action == "pick":
            return self._pick(data["s"])
        if action in ("made", "notmade"):
            return self._confirm(data["l"], made=action == "made")
        if action == "rate" and data.get("v") in (RATING_GOOD, RATING_SO_SO, RATING_BAD):
            self.store.set_rating(data["r"], data["v"])
            return [msg.rated_message(data["v"])]
        logger.warning("知らない postback: %s", raw)
        return [msg.help_message()]

    def _propose(self, condition: str, mood: str, history: msg.History) -> list[dict]:
        recipes = self.load_recipes()
        by_key = {msg.short_id(r): r for r in recipes}
        exclude = frozenset(
            by_key[k].id for round_ in history for s in round_ for k in s if k in by_key
        )
        today = self.now().date()
        proposals = suggest(recipes, condition, mood, today, exclude, select=self.select)
        if not proposals:
            if history:
                return [self._final_list(by_key, history)]
            return [msg.no_candidates_message()]
        history = history + [msg.to_round(proposals)]
        return [msg.proposal_message(proposals, condition, mood, history)]

    def _more(self, condition: str, mood: str, history: msg.History) -> list[dict]:
        if len(history) > msg.MAX_REROLLS:
            by_key = {msg.short_id(r): r for r in self.load_recipes()}
            return [self._final_list(by_key, history)]
        return self._propose(condition, mood, history)

    def _pick(self, keys: list[str]) -> list[dict]:
        """[これにする]／[Aにする]／[Bにする]: 献立ログに「確認待ち」で記録する（3.1）。"""
        by_key = {msg.short_id(r): r for r in self.load_recipes()}
        recipes = [by_key[k] for k in keys if k in by_key]
        self.store.create_log(recipes, self.now())
        return [msg.decided_message()]

    def _confirm(self, log_id: str, made: bool) -> list[dict]:
        """「作った？」への返事（3.2, 3.3）。"""
        log = self.store.fetch_log(log_id)
        if log.status != STATUS_PENDING:
            return [msg.already_recorded_message()]
        if not made:
            self.store.update_log(log_id, STATUS_NOT_MADE)
            return [msg.not_made_message()]

        today = self.now().date()
        untried = None
        for recipe_id in log.recipe_ids:
            self.store.set_last_made(recipe_id, today)
            recipe = self.store.fetch_recipe(recipe_id)
            if untried is None and recipe and recipe.is_untried:
                untried = recipe  # 作ってみたいセットに含まれる未経験のレシピは1品だけ
        self.store.update_log(log_id, STATUS_MADE)
        return [msg.made_message(untried)]

    @staticmethod
    def _final_list(by_key: dict[str, Recipe], history: msg.History) -> dict:
        sets = [[by_key[k] for k in s if k in by_key] for round_ in history for s in round_]
        return msg.final_list_message([s for s in sets if s])


bot = Bot(
    load_recipes=lambda: notion_repo.fetch_recipes(config.NOTION_TOKEN, config.NOTION_RECIPE_DS_ID),
    select=select_menu,
    interpret=interpret,
    now=lambda: datetime.now(config.JST),
    store=NotionStore(config.NOTION_TOKEN, config.NOTION_LOG_DS_ID),
)

app = FastAPI()


def handle_event(event: dict) -> None:
    user_id = event.get("source", {}).get("userId")
    if not config.LINE_USER_ID or user_id != config.LINE_USER_ID:
        # LINE_USER_ID が未設定のときは、ここに出る userId を .env に設定する
        logger.info("本人以外（または LINE_USER_ID 未設定）なので無視します: userId=%s", user_id)
        return

    if event["type"] == "message" and event["message"]["type"] == "text":
        handler, arg = bot.handle_text, event["message"]["text"]
    elif event["type"] == "postback":
        handler, arg = bot.handle_postback, event["postback"]["data"]
    else:
        return

    token = config.LINE_CHANNEL_ACCESS_TOKEN
    try:
        show_loading(token, user_id)
        messages = handler(arg)
    except Exception:
        logger.exception("イベントの処理に失敗しました: %s", event)
        messages = [{"type": "text", "text": "ごめんなさい、エラーが起きました。もう一度送ってみてください"}]
    reply(token, event["replyToken"], messages)


@app.get("/")
def health() -> dict:
    return {"status": "ok"}


@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks) -> str:
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_signature(config.LINE_CHANNEL_SECRET, body, signature):
        raise HTTPException(status_code=400, detail="invalid signature")
    # LINE にはすぐ 200 を返し、Notion・Claude を使う処理は後ろで行う
    for event in json.loads(body).get("events", []):
        background_tasks.add_task(handle_event, event)
    return "OK"

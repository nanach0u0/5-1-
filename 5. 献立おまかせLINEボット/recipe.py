from dataclasses import dataclass
from datetime import date
from typing import Optional

MAIN = "メイン"
SIDE = "副菜"

RATING_GOOD = "おいしい"
RATING_NOT_YET = "まだ作ってない"

EFFORT_EASY = "ラク"
EFFORT_NORMAL = "ふつう"
EFFORT_HARD = "がんばる"


@dataclass(frozen=True)
class Recipe:
    id: str
    name: str
    role: str  # MAIN または SIDE
    rating: Optional[str]
    effort: str
    one_dish: bool
    last_made: Optional[date]
    url: Optional[str]

    @property
    def is_untried(self) -> bool:
        """作ったことがない（評価が「まだ作ってない」または未評価）かどうか。"""
        return self.rating in (None, RATING_NOT_YET)

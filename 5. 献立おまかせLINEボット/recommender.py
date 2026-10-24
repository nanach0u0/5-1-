"""献立の候補を絞り込み、提案を組み立てる（requirements.md 4章）。

ここはルールだけで動き、Claude にも Notion にも依存しない。
最終的にどれを選ぶかは selector（Claude など）に任せ、失敗したらランダムに選ぶ。
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from recipe import EFFORT_EASY, EFFORT_HARD, EFFORT_NORMAL, MAIN, RATING_GOOD, SIDE, Recipe

CONDITION_TIRED = "ヘトヘト"
CONDITION_NORMAL = "ふつう"
CONDITION_RELAXED = "余裕あり"

MOOD_HEARTY = "がっつり"
MOOD_LIGHT = "さっぱり"
MOOD_ANY = "なんでも"
MOODS = (MOOD_HEARTY, MOOD_LIGHT, MOOD_ANY)

ALLOWED_EFFORTS = {
    CONDITION_TIRED: {EFFORT_EASY},
    CONDITION_NORMAL: {EFFORT_EASY, EFFORT_NORMAL},
    CONDITION_RELAXED: {EFFORT_EASY, EFFORT_NORMAL, EFFORT_HARD},
}

logger = logging.getLogger(__name__)

# 今日・昨日・一昨日に作ったものは出さない
RECENT_DAYS = 3


@dataclass(frozen=True)
class Proposal:
    main: Recipe
    side: Optional[Recipe]
    challenge: bool = False  # 作ったことないレシピを含む「作ってみたい」セットか
    reason: Optional[str] = None  # Claude が選んだときの提案理由（ランダムのときは None）

    @property
    def with_rice(self) -> bool:
        return not self.main.one_dish

    @property
    def recipes(self) -> list[Recipe]:
        return [r for r in (self.main, self.side) if r]


@dataclass
class Pools:
    """絞り込み後の候補。first_* は一軍、untried_* は作ったことないレシピ。"""

    first_mains: list[Recipe] = field(default_factory=list)
    first_sides: list[Recipe] = field(default_factory=list)
    untried_mains: list[Recipe] = field(default_factory=list)
    untried_sides: list[Recipe] = field(default_factory=list)


def _is_recent(recipe: Recipe, today: date) -> bool:
    return recipe.last_made is not None and (today - recipe.last_made).days < RECENT_DAYS


def build_pools(
    recipes: list[Recipe],
    condition: str,
    today: date,
    exclude_ids: frozenset[str] = frozenset(),
    skip_recent: bool = True,
) -> Pools:
    allowed = ALLOWED_EFFORTS[condition]
    pools = Pools()
    for r in recipes:
        if r.id in exclude_ids or r.effort not in allowed:
            continue
        if skip_recent and _is_recent(r, today):
            continue
        if r.rating == RATING_GOOD:
            (pools.first_mains if r.role == MAIN else pools.first_sides).append(r)
        elif r.is_untried and condition == CONDITION_RELAXED:
            (pools.untried_mains if r.role == MAIN else pools.untried_sides).append(r)
        # 「ふつう」「残念」はどの候補にも入れない
    return pools


def sides_for(main: Recipe, sides: list[Recipe]) -> list[Recipe]:
    """一品完結のメインには、手間が「ラク」の副菜だけを合わせる。"""
    if main.one_dish:
        return [s for s in sides if s.effort == EFFORT_EASY]
    return sides


Chooser = Callable[[list[Recipe]], Recipe]


def _random_chooser(rng: random.Random) -> Chooser:
    return lambda items: rng.choice(items)


def _pick_set(mains: list[Recipe], sides: list[Recipe], choose: Chooser) -> Optional[Proposal]:
    if not mains:
        return None
    main = choose(mains)
    matching = sides_for(main, sides)
    side = choose(matching) if matching else None
    return Proposal(main=main, side=side)


def _pick_challenge(pools: Pools, choose: Chooser) -> Optional[Proposal]:
    """作ったことないレシピを1品だけ含むセットを作る。"""
    options = []
    if pools.untried_mains and pools.first_sides:
        options.append("main")
    if pools.untried_sides and pools.first_mains:
        options.append("side")
    if not options:
        return None

    if choose(options) == "main":
        main = choose(pools.untried_mains)
        matching = sides_for(main, pools.first_sides)
        return Proposal(main=main, side=choose(matching) if matching else None, challenge=True)

    side = choose(pools.untried_sides)
    # 副菜が「ラク」でなければ、一品完結のメインとは組ませない
    mains = [m for m in pools.first_mains if side in sides_for(m, [side])]
    if not mains:
        return None
    return Proposal(main=choose(mains), side=side, challenge=True)


def candidate_pools(
    recipes: list[Recipe],
    condition: str,
    today: date,
    exclude_ids: frozenset[str] = frozenset(),
) -> Pools:
    pools = build_pools(recipes, condition, today, exclude_ids)
    if not pools.first_mains and not pools.untried_mains:
        # かぶり防止を外してもう一度
        pools = build_pools(recipes, condition, today, exclude_ids, skip_recent=False)
    return pools


def _assemble(pools: Pools, condition: str, choose: Chooser) -> list[Proposal]:
    proposals = []
    challenge = _pick_challenge(pools, choose) if condition == CONDITION_RELAXED else None
    if challenge:
        proposals.append(challenge)
        used = {r.id for r in challenge.recipes}
        first_mains = [m for m in pools.first_mains if m.id not in used]
        first_sides = [s for s in pools.first_sides if s.id not in used]
    else:
        first_mains, first_sides = pools.first_mains, pools.first_sides

    regular = _pick_set(first_mains, first_sides, choose)
    if regular:
        proposals.append(regular)
    return proposals


def recommend(
    recipes: list[Recipe],
    condition: str,
    today: date,
    exclude_ids: frozenset[str] = frozenset(),
    choose: Optional[Chooser] = None,
) -> list[Proposal]:
    """ランダムに選んだ提案を返す。通常は1セット、余裕ありで作ったことないレシピがあれば
    [作ってみたいセット, 一軍セット] の2セット。候補がなければ空リスト。
    """
    choose = choose or _random_chooser(random.Random())
    return _assemble(candidate_pools(recipes, condition, today, exclude_ids), condition, choose)


def _valid_set(p: Proposal, mains: list[Recipe], sides: list[Recipe]) -> bool:
    if p.main not in mains:
        return False
    matching = sides_for(p.main, sides)
    if p.side is None:
        return not matching  # 合わせられる副菜があるのに付けないのは不可
    return p.side in matching


def is_valid(pools: Pools, condition: str, proposals: list[Proposal]) -> bool:
    """selector の返した提案が 4章のルールを守っているか。"""
    if not proposals:
        return False
    regulars = [p for p in proposals if not p.challenge]
    challenges = [p for p in proposals if p.challenge]
    if len(regulars) != 1 or len(challenges) > 1:
        return False
    if challenges and (condition != CONDITION_RELAXED or proposals[0] is not challenges[0]):
        return False

    used: set[str] = set()
    if challenges:
        c = challenges[0]
        if sum(r.is_untried for r in c.recipes) != 1:
            return False
        if not _valid_set(c, pools.first_mains + pools.untried_mains, pools.first_sides + pools.untried_sides):
            return False
        used = {r.id for r in c.recipes}

    regular = regulars[0]
    if used & {r.id for r in regular.recipes}:
        return False
    mains = [m for m in pools.first_mains if m.id not in used]
    sides = [s for s in pools.first_sides if s.id not in used]
    return _valid_set(regular, mains, sides)


Selector = Callable[[Pools, str, str], list[Proposal]]


def suggest(
    recipes: list[Recipe],
    condition: str,
    mood: str,
    today: date,
    exclude_ids: frozenset[str] = frozenset(),
    select: Optional[Selector] = None,
    choose: Optional[Chooser] = None,
) -> list[Proposal]:
    """selector（Claude）で気分に合わせて選ぶ。エラーやルール違反ならランダムに選ぶ（4.5）。"""
    pools = candidate_pools(recipes, condition, today, exclude_ids)
    if select and pools.first_mains:
        try:
            proposals = select(pools, condition, mood)
            if is_valid(pools, condition, proposals):
                return proposals
            logger.warning("selector の提案がルール外だったのでランダムに選びます: %s", proposals)
        except Exception:
            logger.exception("selector が失敗したのでランダムに選びます")
    return _assemble(pools, condition, choose or _random_chooser(random.Random()))

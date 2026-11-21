"""Coach <-> learner matching.

The matcher never pairs anyone by itself. It ranks approved coaches for one
learner, explains every point, and an admin confirms the pairing. Weights are
deliberately simple so a human can sanity-check them at a glance.

    availability  40   shared weekly hours (4+ shared hours = full marks)
    strength      25   coach rating vs learner estimate (400+ gap = full)
    focus         25   learner goals covered by coach specialties
    capacity      10   room left on the coach's roster (spreads the load)

All coaching is online, so location/format plays no part.

Hard requirements (otherwise the coach is listed as ineligible, with why):
approved status, at least one open roster spot, and at least one shared hour.
"""
from dataclasses import dataclass, field

from .catalog import FOCUS_LABELS, describe_slots

WEIGHTS = {"availability": 40, "strength": 25, "focus": 25, "capacity": 10}


@dataclass
class MatchResult:
    coach: object  # CoachProfile
    total: int = 0
    parts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    shared_slots: list = field(default_factory=list)

    @property
    def eligible(self):
        return not self.blockers

    @property
    def shared_label(self):
        return describe_slots(self.shared_slots, limit=4) or "None"

    def as_dict(self):
        return {"total": self.total, "parts": self.parts, "notes": self.notes,
                "shared": self.shared_slots}


def _strength_points(gap):
    """Map rating gap -> 0..25."""
    if gap is None:
        return 12
    if gap >= 400:
        return 25
    if gap >= 200:
        return round(18 + (gap - 200) / 200 * 7)
    if gap >= 0:
        return round(8 + gap / 200 * 10)
    return 0


def score(coach, learner):
    r = MatchResult(coach=coach)

    # --- hard requirements
    if coach.status != "approved":
        r.blockers.append("Coach is not approved")
    if coach.capacity_left <= 0:
        r.blockers.append("Roster is full")

    shared = sorted(set(coach.availability or []) & set(learner.availability or []),
                    key=lambda s: tuple(int(x) for x in s.split("-")))
    r.shared_slots = shared
    if not shared:
        r.blockers.append("No overlapping hours")

    # --- availability
    r.parts["availability"] = round(WEIGHTS["availability"] * min(len(shared), 4) / 4)
    if 0 < len(shared) < 2:
        r.notes.append("Only one shared hour - scheduling will be tight")

    # --- strength
    gap = None
    if coach.rating:
        gap = coach.rating - learner.rating_estimate
    r.parts["strength"] = _strength_points(gap)
    if gap is None:
        r.notes.append("Coach rating unverified")
    elif gap < 0:
        r.notes.append(f"Learner may be stronger ({gap:+d})")
    elif gap < 150:
        r.notes.append(f"Small rating gap ({gap:+d})")

    # --- focus
    goals = set(learner.goals or [])
    specs = set(coach.specialties or [])
    if goals:
        covered = goals & specs
        r.parts["focus"] = round(WEIGHTS["focus"] * len(covered) / len(goals))
        missing = goals - specs
        if missing:
            r.notes.append("Not a specialty: " + ", ".join(FOCUS_LABELS.get(m, m) for m in sorted(missing)))
    else:
        r.parts["focus"] = WEIGHTS["focus"] // 2

    # --- capacity
    if coach.max_learners:
        r.parts["capacity"] = round(WEIGHTS["capacity"] * coach.capacity_left / coach.max_learners)
    else:
        r.parts["capacity"] = 0

    r.total = sum(r.parts.values())
    return r


def rank(coaches, learner):
    """Return (eligible, ineligible) lists, each sorted best-first."""
    results = [score(c, learner) for c in coaches]
    eligible = sorted([r for r in results if r.eligible], key=lambda r: -r.total)
    ineligible = sorted([r for r in results if not r.eligible], key=lambda r: -r.total)
    return eligible, ineligible

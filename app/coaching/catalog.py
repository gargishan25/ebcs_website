"""Static vocabulary for the coaching platform.

Everything that is a fixed list (skills, focus areas, time grid, statuses)
lives here so templates, forms and the matching engine all agree.
"""

# ---------------------------------------------------------------- skills ---
# Skills a coach can assess. Order matters: it is the order of the radar axes.
SKILLS = [
    ("tactics", "Tactics"),
    ("calculation", "Calculation"),
    ("openings", "Openings"),
    ("strategy", "Strategy"),
    ("endgames", "Endgames"),
    ("time", "Clock use"),
    ("mindset", "Mindset"),
]
SKILL_LABELS = dict(SKILLS)

# Level scale used by assessments (0-5).
SKILL_SCALE = {
    0: "Not yet seen",
    1: "Introduced",
    2: "Developing",
    3: "Consistent",
    4: "Strong",
    5: "Teaches it",
}

# Focus areas: learners pick goals, coaches pick specialties. Same vocabulary
# so the matcher can intersect them.
FOCUS_AREAS = [
    ("fundamentals", "Rules & fundamentals"),
    ("tactics", "Tactics"),
    ("openings", "Opening repertoire"),
    ("strategy", "Positional play"),
    ("endgames", "Endgames"),
    ("tournament", "Tournament prep"),
    ("analysis", "Game review"),
    ("comeback", "Returning to chess"),
]
FOCUS_LABELS = dict(FOCUS_AREAS)

# ------------------------------------------------------------- formats ---
# All coaching is online. In-person meetings are not part of the program.
FORMATS = [("online", "Online")]
FORMAT_LABELS = dict(FORMATS)

# ----------------------------------------------------------- age bands ---
AGE_BANDS = [
    ("u10", "Under 10"),
    ("10_13", "10 - 13"),
    ("14_17", "14 - 17"),
    ("18p", "18 or older"),
]
AGE_LABELS = dict(AGE_BANDS)
MINOR_BANDS = {"u10", "10_13", "14_17"}

LEVELS = [
    ("new", "Brand new - learning how pieces move"),
    ("casual", "Casual - I play but have never studied"),
    ("club", "Club - I play rated games or online regularly"),
    ("competitive", "Competitive - I want to push my rating"),
]
LEVEL_LABELS = dict(LEVELS)
# Rough rating estimate when a learner doesn't know their rating.
LEVEL_RATING_GUESS = {"new": 200, "casual": 600, "club": 1100, "competitive": 1500}

GRADES = [("9", "9th"), ("10", "10th"), ("11", "11th"), ("12", "12th")]

# ------------------------------------------------------------ the grid ---
# Weekly availability grid, one cell per hour. Cell key is "<day>-<hour>",
# day 0 = Monday, hour in 24h local time.
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOURS = list(range(8, 21))  # 8:00 through 20:00 starts


def slot_key(day, hour):
    return f"{day}-{hour}"


ALL_SLOTS = [slot_key(d, h) for d in range(7) for h in HOURS]


def hour_label(h):
    suffix = "a" if h < 12 else "p"
    h12 = h % 12 or 12
    return f"{h12}{suffix}"


def describe_slots(slots, limit=3):
    """Turn a set of slot keys into short human ranges: 'Tue 4-6p, Sat 10a-12p'."""
    by_day = {}
    for s in slots:
        try:
            d, h = (int(x) for x in s.split("-"))
        except ValueError:
            continue
        by_day.setdefault(d, []).append(h)
    parts = []
    for d in sorted(by_day):
        hours = sorted(by_day[d])
        start = prev = hours[0]
        for h in hours[1:] + [None]:
            if h is not None and h == prev + 1:
                prev = h
                continue
            parts.append(f"{DAYS[d]} {hour_label(start)}-{hour_label(prev + 1)}")
            if h is not None:
                start = prev = h
    if limit and len(parts) > limit:
        return ", ".join(parts[:limit]) + f" +{len(parts) - limit} more"
    return ", ".join(parts)


# ------------------------------------------------------------ statuses ---
COACH_STATUSES = [
    ("applied", "Applied"),
    ("screening", "Screening"),
    ("approved", "Approved"),
    ("paused", "Paused"),
    ("rejected", "Not accepted"),
]
COACH_STATUS_LABELS = dict(COACH_STATUSES)

LEARNER_STATUSES = [
    ("waiting", "Waiting for match"),
    ("matched", "Matched"),
    ("paused", "Paused"),
    ("graduated", "Graduated"),
]
LEARNER_STATUS_LABELS = dict(LEARNER_STATUSES)

SESSION_STATUSES = [
    ("scheduled", "Scheduled"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
    ("no_show", "No-show"),
]
SESSION_STATUS_LABELS = dict(SESSION_STATUSES)

HOUR_KINDS = [
    ("session", "Coaching session"),
    ("prep", "Lesson prep"),
    ("event", "EBCS event"),
    ("training", "Coach training"),
]
HOUR_KIND_LABELS = dict(HOUR_KINDS)

TRACKS = [
    ("foundations", "Foundations"),
    ("tactics", "Tactics"),
    ("openings", "Openings"),
    ("strategy", "Strategy"),
    ("endgames", "Endgames"),
]
TRACK_LABELS = dict(TRACKS)

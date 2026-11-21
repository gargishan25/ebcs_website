"""Database models for the coaching platform.

All tables are prefixed ``cp_`` so they never collide with the original
v1 coaching tables (student, coach_application, match) that may still exist
in the production database. ``db.create_all()`` only creates missing tables,
so adding these is safe on an existing database.
"""
import json
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from ..models import db
from .catalog import LEVEL_RATING_GUESS, MINOR_BANDS


def _now():
    return datetime.utcnow()


class JSONList(db.TypeDecorator):
    """Stores a Python list as JSON text (works on SQLite and Postgres)."""

    impl = db.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return json.dumps(list(value or []))

    def process_result_value(self, value, dialect):
        if not value:
            return []
        try:
            return json.loads(value)
        except ValueError:
            return []


# ------------------------------------------------------------------ users ---
class User(UserMixin, db.Model):
    __tablename__ = "cp_user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="learner")  # learner | coach | admin
    created_at = db.Column(db.DateTime, default=_now)
    last_seen_at = db.Column(db.DateTime)
    disabled = db.Column(db.Boolean, default=False)
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)

    coach = db.relationship("CoachProfile", uselist=False, back_populates="user", cascade="all, delete-orphan",
                            foreign_keys="CoachProfile.user_id")
    learner = db.relationship("LearnerProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")

    # --- auth helpers
    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_active(self):  # Flask-Login hook
        return not self.disabled

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > _now())

    def register_failed_login(self):
        self.failed_logins = (self.failed_logins or 0) + 1
        if self.failed_logins >= 6:
            self.locked_until = _now() + timedelta(minutes=15)
            self.failed_logins = 0

    def register_login(self):
        self.failed_logins = 0
        self.locked_until = None
        self.last_seen_at = _now()

    # --- convenience
    @property
    def first_name(self):
        return (self.name or "").split(" ")[0]

    @property
    def initials(self):
        parts = [p for p in (self.name or "?").split() if p]
        return "".join(p[0] for p in parts[:2]).upper()

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_coach(self):
        return self.role == "coach"

    @property
    def is_learner(self):
        return self.role == "learner"


# --------------------------------------------------------------- profiles ---
class CoachProfile(db.Model):
    __tablename__ = "cp_coach"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), unique=True, nullable=False)
    status = db.Column(db.String(16), default="applied", index=True)

    school = db.Column(db.String(160))
    grade = db.Column(db.String(4))
    phone = db.Column(db.String(40))

    uscf_id = db.Column(db.String(20))
    uscf_rating = db.Column(db.Integer)
    online_platform = db.Column(db.String(20))  # lichess | chess.com
    online_username = db.Column(db.String(60))
    online_rating = db.Column(db.Integer)

    bio = db.Column(db.Text)
    why = db.Column(db.Text)
    experience = db.Column(db.Text)
    specialties = db.Column(JSONList, default=list)
    formats = db.Column(JSONList, default=list)
    availability = db.Column(JSONList, default=list)
    max_learners = db.Column(db.Integer, default=2)
    hours_goal = db.Column(db.Integer, default=40)

    agreed_conduct_at = db.Column(db.DateTime)
    admin_notes = db.Column(db.Text)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_now)

    user = db.relationship("User", foreign_keys=[user_id], back_populates="coach")
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])

    @property
    def rating(self):
        """Best available strength signal. USCF first, then online (discounted)."""
        if self.uscf_rating:
            return self.uscf_rating
        if self.online_rating:
            # online pools run high; a light discount keeps comparisons honest
            return int(self.online_rating * 0.9)
        return None

    def active_pairings(self):
        return [p for p in self.user.coach_pairings if p.status == "active"]

    @property
    def load(self):
        return len(self.active_pairings())

    @property
    def capacity_left(self):
        return max(0, (self.max_learners or 0) - self.load)


class LearnerProfile(db.Model):
    __tablename__ = "cp_learner"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), unique=True, nullable=False)
    status = db.Column(db.String(16), default="waiting", index=True)

    age_band = db.Column(db.String(8))
    level = db.Column(db.String(16))
    rating = db.Column(db.Integer)  # self-reported, optional
    goals = db.Column(JSONList, default=list)
    goal_text = db.Column(db.Text)
    formats = db.Column(JSONList, default=list)
    availability = db.Column(JSONList, default=list)
    city = db.Column(db.String(80))

    guardian_name = db.Column(db.String(120))
    guardian_email = db.Column(db.String(160))
    guardian_phone = db.Column(db.String(40))
    guardian_consent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_now)

    user = db.relationship("User", back_populates="learner")

    @property
    def is_minor(self):
        return self.age_band in MINOR_BANDS

    @property
    def rating_estimate(self):
        return self.rating or LEVEL_RATING_GUESS.get(self.level or "casual", 600)

    def active_pairing(self):
        for p in self.user.learner_pairings:
            if p.status == "active":
                return p
        return None

    @property
    def waiting_days(self):
        return (_now() - (self.created_at or _now())).days


# -------------------------------------------------------------- pairings ---
class Pairing(db.Model):
    __tablename__ = "cp_pairing"

    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), nullable=False, index=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), nullable=False, index=True)
    status = db.Column(db.String(16), default="active")  # active | ended
    score = db.Column(db.Integer)
    score_detail = db.Column(db.Text)  # JSON breakdown at time of match
    created_by_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"))
    created_at = db.Column(db.DateTime, default=_now)
    ended_at = db.Column(db.DateTime)
    end_reason = db.Column(db.String(200))

    coach = db.relationship("User", foreign_keys=[coach_id], backref="coach_pairings")
    learner = db.relationship("User", foreign_keys=[learner_id], backref="learner_pairings")
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    sessions = db.relationship("Session", back_populates="pairing", order_by="Session.starts_at",
                               cascade="all, delete-orphan")
    messages = db.relationship("Message", back_populates="pairing", order_by="Message.created_at",
                               cascade="all, delete-orphan")
    assignments = db.relationship("Assignment", back_populates="pairing", cascade="all, delete-orphan")

    @property
    def detail(self):
        try:
            return json.loads(self.score_detail or "{}")
        except ValueError:
            return {}

    def involves(self, user):
        return user.is_admin or user.id in (self.coach_id, self.learner_id)

    def other(self, user):
        return self.learner if user.id == self.coach_id else self.coach

    @property
    def completed_sessions(self):
        return [s for s in self.sessions if s.status == "completed"]

    def next_session(self):
        now = _now()
        upcoming = [s for s in self.sessions if s.status == "scheduled" and s.starts_at >= now - timedelta(hours=1)]
        return upcoming[0] if upcoming else None


# -------------------------------------------------------------- sessions ---
class Session(db.Model):
    __tablename__ = "cp_session"

    id = db.Column(db.Integer, primary_key=True)
    pairing_id = db.Column(db.Integer, db.ForeignKey("cp_pairing.id"), nullable=False, index=True)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)  # UTC
    duration_min = db.Column(db.Integer, default=60)
    format = db.Column(db.String(16), default="online")
    location = db.Column(db.String(240))  # meeting link
    agenda = db.Column(db.Text)
    status = db.Column(db.String(16), default="scheduled", index=True)
    created_at = db.Column(db.DateTime, default=_now)

    # coach report
    topics = db.Column(JSONList, default=list)
    summary = db.Column(db.Text)
    homework = db.Column(db.Text)
    reported_at = db.Column(db.DateTime)

    # learner feedback
    learner_rating = db.Column(db.Integer)
    learner_feedback = db.Column(db.Text)

    pairing = db.relationship("Pairing", back_populates="sessions")

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.duration_min or 60)

    @property
    def needs_report(self):
        return self.status == "scheduled" and self.ends_at < _now()

    @property
    def is_upcoming(self):
        return self.status == "scheduled" and self.starts_at >= _now()


class Message(db.Model):
    __tablename__ = "cp_message"

    id = db.Column(db.Integer, primary_key=True)
    pairing_id = db.Column(db.Integer, db.ForeignKey("cp_pairing.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=_now, index=True)
    flagged = db.Column(db.Boolean, default=False)
    flag_reason = db.Column(db.String(200))
    read_at = db.Column(db.DateTime)

    pairing = db.relationship("Pairing", back_populates="messages")
    sender = db.relationship("User")


# ------------------------------------------------------------ assessment ---
class SkillAssessment(db.Model):
    __tablename__ = "cp_skill"

    id = db.Column(db.Integer, primary_key=True)
    learner_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), nullable=False, index=True)
    assessed_by_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"))
    skill = db.Column(db.String(24), nullable=False)
    level = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(240))
    created_at = db.Column(db.DateTime, default=_now)

    assessed_by = db.relationship("User", foreign_keys=[assessed_by_id])


# --------------------------------------------------------------- library ---
class Lesson(db.Model):
    __tablename__ = "cp_lesson"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    track = db.Column(db.String(24), nullable=False)
    level = db.Column(db.Integer, default=1)  # 1 beginner .. 4 advanced
    minutes = db.Column(db.Integer, default=15)
    summary = db.Column(db.String(300))
    body = db.Column(db.Text)  # light markup: blank line = paragraph, "- " = bullet
    fen = db.Column(db.String(100))
    solution = db.Column(db.String(200))  # e.g. "Re8#" in SAN, shown on reveal
    published = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"))
    created_at = db.Column(db.DateTime, default=_now)


class Assignment(db.Model):
    __tablename__ = "cp_assignment"

    id = db.Column(db.Integer, primary_key=True)
    pairing_id = db.Column(db.Integer, db.ForeignKey("cp_pairing.id"), nullable=False, index=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("cp_lesson.id"), nullable=False)
    note = db.Column(db.String(300))
    due_on = db.Column(db.Date)
    assigned_at = db.Column(db.DateTime, default=_now)
    completed_at = db.Column(db.DateTime)

    pairing = db.relationship("Pairing", back_populates="assignments")
    lesson = db.relationship("Lesson")


# ---------------------------------------------------------------- hours ---
class HourEntry(db.Model):
    """Hours supported: time a coach spends helping learners. Internal
    tracking only (not official service hours). Session entries are created
    automatically when a coach files a session report; other kinds are logged
    manually. Staff confirm each entry (status "verified" = confirmed)."""

    __tablename__ = "cp_hours"

    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("cp_session.id"), unique=True)
    kind = db.Column(db.String(16), default="session")
    worked_on = db.Column(db.Date, nullable=False)
    minutes = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(300))
    status = db.Column(db.String(16), default="pending", index=True)  # pending | verified | rejected
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=_now)

    coach = db.relationship("User", foreign_keys=[coach_id], backref="hour_entries")
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    session = db.relationship("Session")


# ---------------------------------------------------------------- audit ---
class Event(db.Model):
    """Append-only activity log. Powers the admin feed and safety review."""

    __tablename__ = "cp_event"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("cp_user.id"))
    verb = db.Column(db.String(40), nullable=False)
    subject = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=_now, index=True)

    actor = db.relationship("User")


def log_event(actor, verb, subject=""):
    db.session.add(Event(actor_id=actor.id if actor else None, verb=verb, subject=subject[:200]))

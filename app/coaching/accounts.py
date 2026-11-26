"""Email verification, password resets, notifications and deactivation.

All user-facing wording here was approved by EBCS - change it only with
their sign-off.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from ..models import db
from .mail import absolute_url, send_email
from .models import EmailVerification, Event, HourEntry, PasswordReset, SkillAssessment, User, log_event

CODE_TTL = timedelta(minutes=15)
RESET_TTL = timedelta(hours=1)
MAX_ATTEMPTS = 5
RESEND_GAP = timedelta(seconds=30)


def _now():
    return datetime.utcnow()


# ------------------------------------------------------------ verification ---
def is_verified(user):
    """Accounts with no verification record (created before this feature,
    admins, demo data) count as verified."""
    row = db.session.get(EmailVerification, user.id)
    return row is None or row.verified_at is not None


def unverified_ids():
    return {uid for (uid,) in db.session.query(EmailVerification.user_id)
            .filter(EmailVerification.verified_at.is_(None)).all()}


def issue_code(user, force=False):
    """Create/refresh a 6-digit code and email it. Returns False if throttled."""
    row = db.session.get(EmailVerification, user.id)
    if row is None:
        row = EmailVerification(user_id=user.id)
        db.session.add(row)
    elif not force and row.last_sent_at and _now() - row.last_sent_at < RESEND_GAP:
        return False
    code = f"{secrets.randbelow(10 ** 6):06d}"
    row.code_hash = generate_password_hash(code)
    row.expires_at = _now() + CODE_TTL
    row.attempts = 0
    row.last_sent_at = _now()
    row.verified_at = None
    db.session.commit()
    send_email(
        user.email,
        f"Your EBCS Coaching code: {code}",
        f"Your verification code is {code}. It expires in 15 minutes. "
        "If you didn't sign up for EBCS Coaching, you can ignore this email.",
    )
    return True


def check_code(user, code):
    """Returns 'ok', 'wrong', 'expired' or 'locked'."""
    row = db.session.get(EmailVerification, user.id)
    if row is None or row.verified_at:
        return "ok"
    if not row.expires_at or row.expires_at < _now():
        return "expired"
    if (row.attempts or 0) >= MAX_ATTEMPTS:
        return "locked"
    if row.code_hash and check_password_hash(row.code_hash, (code or "").strip()):
        row.verified_at = _now()
        row.code_hash = None
        log_event(user, "verified email", user.name)
        db.session.commit()
        send_welcome(user)
        notify_admin_signup(user)
        return "ok"
    row.attempts = (row.attempts or 0) + 1
    db.session.commit()
    return "locked" if row.attempts >= MAX_ATTEMPTS else "wrong"


# ----------------------------------------------------------- notifications ---
def send_welcome(user):
    link = absolute_url("coaching.app_home")
    if user.is_coach:
        send_email(user.email, "We got your coaching application",
                   f"Hi {user.first_name}, thanks for applying to coach with EBCS. We'll review your application "
                   f"and get in touch at this email. You can sign in any time to check its status: {link}")
    else:
        send_email(user.email, "Welcome to EBCS Coaching",
                   f"Hi {user.first_name}, your account is all set. We’ll match you with a coach after reviewing "
                   f"your application. You can sign in any time to see your status: {link}.")


def notify_admin_signup(user):
    to = current_app.config.get("ADMIN_EMAIL")
    if not to:
        return
    kind = "coach" if user.is_coach else "learner"
    link = (absolute_url("coaching.admin_coach", user_id=user.id) if user.is_coach
            else absolute_url("coaching.learner_file", user_id=user.id))
    send_email(to, f"New {kind} sign-up: {user.name}",
               f"{user.name} ({user.email}) just signed up. Review: {link}")


def send_match_emails(pairing):
    link = absolute_url("coaching.thread", pairing_id=pairing.id)
    for me, other in ((pairing.learner, pairing.coach), (pairing.coach, pairing.learner)):
        send_email(me.email, "You've been matched on EBCS Coaching",
                   f"You've been matched with {other.name}. "
                   f"Sign in to message them and set up your first session: {link}")


# --------------------------------------------------------- password reset ---
def _hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def start_reset(email):
    """Always behaves the same whether or not the account exists."""
    user = User.query.filter_by(email=(email or "").strip().lower()).first()
    if not user or user.disabled:
        return
    recent = (PasswordReset.query.filter_by(user_id=user.id)
              .filter(PasswordReset.created_at > _now() - timedelta(minutes=2)).first())
    if recent:
        return
    token = secrets.token_urlsafe(32)
    db.session.add(PasswordReset(user_id=user.id, token_hash=_hash_token(token),
                                 expires_at=_now() + RESET_TTL))
    db.session.commit()
    link = absolute_url("coaching.reset_password", token=token)
    send_email(user.email, "Reset your EBCS Coaching password",
               "Click the link below to choose a new password. It expires in 1 hour. "
               f"If you didn't ask for this, you can ignore this email.\n\n{link}")


def find_reset(token):
    row = PasswordReset.query.filter_by(token_hash=_hash_token(token or "")).first()
    if not row or row.used_at or row.expires_at < _now():
        return None
    return row


def finish_reset(row, new_password):
    user = db.session.get(User, row.user_id)
    user.set_password(new_password)
    user.failed_logins = 0
    user.locked_until = None
    now = _now()
    for r in PasswordReset.query.filter_by(user_id=user.id, used_at=None).all():
        r.used_at = now
    log_event(user, "reset password", user.name)
    db.session.commit()


# ------------------------------------------------------------ deactivation ---
def set_active(user, active, actor):
    """Deactivate: block sign-in, end active pairings, cancel future sessions."""
    if active:
        user.disabled = False
        log_event(actor, "reactivated account", user.name)
        db.session.commit()
        return
    user.disabled = True
    now = _now()
    for p in list(user.coach_pairings) + list(user.learner_pairings):
        if p.status != "active":
            continue
        p.status = "ended"
        p.ended_at = now
        p.end_reason = "Account deactivated"
        for s in p.sessions:
            if s.status == "scheduled" and s.starts_at > now:
                s.status = "cancelled"
        lp = p.learner.learner
        if lp:
            # the learner goes back in the queue unless they're the one deactivated
            lp.status = "paused" if p.learner_id == user.id else "waiting"
    if user.learner:
        user.learner.status = "paused"  # out of the matching queue
    log_event(actor, "deactivated account", user.name)
    db.session.commit()


# ---------------------------------------------------------------- deletion ---
DELETED_NAME = "Deleted user"


def delete_account(user, actor):
    """Permanently erase a (deactivated) person's account and personal details.

    Shared history is KEPT so nobody else loses anything: sessions, session
    notes, messages (safety record) and every logged/confirmed hour stay, now
    shown under "Deleted user". Erased: name, email, password, coach
    application / learner profile, skill ratings, verification and reset records.
    """
    old_name = user.name
    for row in (user.coach, user.learner):
        if row is not None:
            db.session.delete(row)
    SkillAssessment.query.filter_by(learner_id=user.id).delete()
    EmailVerification.query.filter_by(user_id=user.id).delete()
    PasswordReset.query.filter_by(user_id=user.id).delete()

    # scrub the old name from text that mentions it (hours stay, minutes untouched)
    if old_name:
        for e in HourEntry.query.filter(HourEntry.description.contains(old_name)).all():
            e.description = e.description.replace(old_name, DELETED_NAME)
        for ev in Event.query.filter(Event.subject.contains(old_name)).all():
            ev.subject = ev.subject.replace(old_name, DELETED_NAME)

    user.name = DELETED_NAME
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.set_password(secrets.token_urlsafe(32))  # nobody knows it; sign-in impossible
    user.disabled = True
    log_event(actor, "deleted account", DELETED_NAME)
    db.session.commit()

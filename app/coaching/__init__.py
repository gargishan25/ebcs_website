"""EBCS Coaching platform.

A self-contained Flask blueprint mounted at /coaching. It shares the main
site's database, login manager and look, and is wired up in app/main.py via
``init_coaching(app)``.

    catalog.py     fixed vocabularies (skills, focus areas, time grid)
    models.py      cp_* tables
    matching.py    coach/learner scoring
    views_*.py     routes, split by audience
    seed.py        CLI: create-admin, demo data
"""
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, request
from flask_login import current_user

bp = Blueprint("coaching", __name__, url_prefix="/coaching")

# Public sign-up pages that disappear when COACHING_ENABLED is False.
# Sign-in and the app itself stay reachable so admins can prepare.
_GATED = {"coaching.landing", "coaching.join_learner", "coaching.join_coach", "coaching.guidelines"}


# Pages an unverified (or signed-out) person may still reach.
_OPEN_WHEN_UNVERIFIED = {"coaching.verify", "coaching.verify_resend", "coaching.logout", "coaching.login",
                         "coaching.forgot_password", "coaching.reset_password", "coaching.guidelines",
                         "coaching.landing"}


@bp.before_request
def _gate_and_touch():
    if not current_app.config.get("COACHING_ENABLED") and request.endpoint in _GATED:
        abort(404)
    if current_user.is_authenticated:
        from flask import flash, redirect, url_for
        from flask_login import logout_user

        from ..models import db
        from .accounts import is_verified

        if current_user.disabled:
            logout_user()
            flash("This account has been deactivated. Contact eastbaychesssociety@gmail.com "
                  "if you think this is a mistake.", "error")
            return redirect(url_for("coaching.login"))
        if request.endpoint not in _OPEN_WHEN_UNVERIFIED and not is_verified(current_user):
            return redirect(url_for("coaching.verify"))

        now = datetime.utcnow()
        if not current_user.last_seen_at or now - current_user.last_seen_at > timedelta(minutes=5):
            current_user.last_seen_at = now
            db.session.commit()


@bp.app_template_filter("dt")
def _dt(value, style="full"):
    from .util import fmt_dt

    return fmt_dt(value, style)


@bp.app_template_filter("rel")
def _rel(value):
    from .util import relative

    return relative(value)


@bp.app_template_filter("mins")
def _mins(value):
    from .util import minutes_label

    return minutes_label(value)


@bp.app_template_filter("body")
def _body(value):
    from .util import render_body

    return render_body(value)


@bp.context_processor
def _shell_context():
    """Counts for sidebar badges and the command palette."""
    from . import catalog

    ctx = {"cat": catalog}
    if not current_user.is_authenticated:
        return ctx

    from .models import CoachProfile, HourEntry, LearnerProfile, Message, Pairing

    pairing_ids = [p.id for p in Pairing.query.filter(
        Pairing.status == "active",
        (Pairing.coach_id == current_user.id) | (Pairing.learner_id == current_user.id)).all()]
    unread = 0
    if pairing_ids:
        unread = Message.query.filter(Message.pairing_id.in_(pairing_ids),
                                      Message.sender_id != current_user.id,
                                      Message.read_at.is_(None)).count()
    ctx["unread_count"] = unread
    if current_user.is_admin:
        from .accounts import unverified_ids

        uv = unverified_ids()
        ctx["admin_counts"] = {
            "applicants": sum(1 for c in CoachProfile.query.filter(CoachProfile.status.in_(["applied", "screening"])).all()
                              if c.user_id not in uv),
            "waiting": sum(1 for l in LearnerProfile.query.filter_by(status="waiting").all() if l.user_id not in uv),
            "hours": HourEntry.query.filter_by(status="pending").count(),
            "flagged": Message.query.filter_by(flagged=True).count(),
        }
    return ctx


def init_coaching(app):
    """Register the blueprint, CLI commands and first-run data."""
    from . import views_admin, views_app, views_public  # noqa: F401  (registers routes)
    from .seed import register_cli

    app.register_blueprint(bp)
    register_cli(app)


def bootstrap(app):
    """Run inside app context after create_all(): starter lessons + env admin."""
    from .curriculum import ensure_curriculum
    from .seed import ensure_env_admin

    try:
        ensure_curriculum()
        ensure_env_admin(app)
    except Exception as exc:  # never block the public site from booting
        from ..models import db

        db.session.rollback()
        app.logger.warning("coaching bootstrap skipped: %s", exc)

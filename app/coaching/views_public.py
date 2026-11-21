"""Public pages: program landing, sign-up flows, sign-in."""
from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func

from ..models import db
from . import bp
from .forms import CoachApplyForm, LearnerSignupForm, LoginForm
from .models import CoachProfile, HourEntry, LearnerProfile, Session, User, log_event
from .util import safe_next


def _email(raw):
    return (raw or "").strip().lower()


@bp.route("/")
def landing():
    stats = {
        "coaches": CoachProfile.query.filter_by(status="approved").count(),
        "learners": LearnerProfile.query.count(),
        "sessions": Session.query.filter_by(status="completed").count(),
        "hours": int((db.session.query(func.coalesce(func.sum(HourEntry.minutes), 0))
                      .filter(HourEntry.status == "verified").scalar() or 0) / 60),
    }
    return render_template("coaching/landing.html", stats=stats, active_page="coaching")


@bp.route("/guidelines")
def guidelines():
    return render_template("coaching/guidelines.html", active_page="coaching")


@bp.route("/join/learner", methods=["GET", "POST"])
def join_learner():
    if current_user.is_authenticated:
        return redirect(url_for("coaching.app_home"))
    form = LearnerSignupForm()
    if form.validate_on_submit():
        email = _email(form.email.data)
        if User.query.filter_by(email=email).first():
            form.email.errors.append("An account with this email already exists. Sign in instead.")
        else:
            user = User(email=email, name=form.name.data.strip(), role="learner")
            user.set_password(form.password.data)
            profile = LearnerProfile(
                user=user,
                age_band=form.age_band.data,
                level=form.level.data,
                rating=form.rating.data,
                goals=form.goals.data,
                goal_text=form.goal_text.data,
                formats=["online"],
                availability=form.availability.data,
            )
            if profile.is_minor:
                profile.guardian_name = form.guardian_name.data
                profile.guardian_email = _email(form.guardian_email.data)
                profile.guardian_phone = form.guardian_phone.data
                profile.guardian_consent_at = datetime.utcnow()
            db.session.add_all([user, profile])
            db.session.flush()
            log_event(user, "joined as learner", user.name)
            db.session.commit()
            login_user(user)
            user.register_login()
            db.session.commit()
            flash("You're in. We'll match you with a coach and let you know here.", "success")
            return redirect(url_for("coaching.app_home"))
    return render_template("coaching/join_learner.html", form=form, active_page="coaching")


@bp.route("/join/coach", methods=["GET", "POST"])
def join_coach():
    if current_user.is_authenticated:
        return redirect(url_for("coaching.app_home"))
    form = CoachApplyForm()
    if form.validate_on_submit():
        email = _email(form.email.data)
        if User.query.filter_by(email=email).first():
            form.email.errors.append("An account with this email already exists. Sign in instead.")
        else:
            user = User(email=email, name=form.name.data.strip(), role="coach")
            user.set_password(form.password.data)
            profile = CoachProfile(
                user=user,
                school=form.school.data, grade=form.grade.data, phone=form.phone.data,
                uscf_id=form.uscf_id.data, uscf_rating=form.uscf_rating.data,
                online_platform=form.online_platform.data or None,
                online_username=form.online_username.data, online_rating=form.online_rating.data,
                experience=form.experience.data, why=form.why.data, bio=form.bio.data,
                specialties=form.specialties.data, formats=["online"],
                availability=form.availability.data, max_learners=int(form.max_learners.data),
                agreed_conduct_at=datetime.utcnow(),
            )
            db.session.add_all([user, profile])
            db.session.flush()
            log_event(user, "applied to coach", f"{user.name}, {profile.school}")
            db.session.commit()
            login_user(user)
            user.register_login()
            db.session.commit()
            flash("Application received. You can track its status here.", "success")
            return redirect(url_for("coaching.app_home"))
    return render_template("coaching/join_coach.html", form=form, active_page="coaching")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("coaching.app_home"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=_email(form.email.data)).first()
        if user and user.is_locked:
            flash("Too many attempts. Try again in a few minutes.", "error")
        elif user and not user.disabled and user.check_password(form.password.data):
            user.register_login()
            db.session.commit()
            login_user(user, remember=form.remember.data)
            return redirect(safe_next(request.args.get("next")) or url_for("coaching.app_home"))
        else:
            if user:
                user.register_failed_login()
                db.session.commit()
            flash("That email and password don't match.", "error")
    return render_template("coaching/login.html", form=form, active_page="coaching")


@bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("coaching.login"))

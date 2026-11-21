"""Public pages: program landing, sign-up flows, sign-in."""
from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func

from ..models import db
from . import bp
from .accounts import unverified_ids, check_code, finish_reset, find_reset, is_verified, issue_code, start_reset
from .forms import CoachApplyForm, ForgotForm, LearnerSignupForm, LoginForm, ResetForm, VerifyForm
from .models import CoachProfile, HourEntry, LearnerProfile, Session, User, log_event
from .util import safe_next


def _email(raw):
    return (raw or "").strip().lower()


@bp.route("/")
def landing():
    stats = {
        "coaches": CoachProfile.query.filter_by(status="approved").count(),
        "learners": len({uid for (uid,) in db.session.query(LearnerProfile.user_id).all()} - unverified_ids()),
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
            issue_code(user, force=True)
            return redirect(url_for("coaching.verify"))
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
            issue_code(user, force=True)
            return redirect(url_for("coaching.verify"))
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
        elif user and user.disabled and user.check_password(form.password.data):
            flash("This account has been deactivated. Contact eastbaychesssociety@gmail.com "
                  "if you think this is a mistake.", "error")
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


# ------------------------------------------------------ email verification ---
@bp.route("/verify", methods=["GET", "POST"])
def verify():
    if not current_user.is_authenticated:
        return redirect(url_for("coaching.login"))
    if is_verified(current_user):
        return redirect(url_for("coaching.app_home"))
    form = VerifyForm()
    if form.validate_on_submit():
        result = check_code(current_user, form.code.data)
        if result == "ok":
            flash("Email verified. Welcome to EBCS Coaching!", "success")
            return redirect(url_for("coaching.app_home"))
        if result == "wrong":
            flash("That code isn't right. Try again.", "error")
        elif result == "expired":
            issue_code(current_user, force=True)
            flash("That code has expired. We've sent you a new one.", "error")
        else:  # locked
            issue_code(current_user, force=True)
            flash("Too many tries. We've sent you a new code.", "error")
        return redirect(url_for("coaching.verify"))
    return render_template("coaching/verify.html", form=form, active_page="coaching")


@bp.route("/verify/resend", methods=["POST"])
def verify_resend():
    if not current_user.is_authenticated:
        return redirect(url_for("coaching.login"))
    if not is_verified(current_user):
        issue_code(current_user)
        flash(f"New code sent to {current_user.email}.", "success")
    return redirect(url_for("coaching.verify"))


# ---------------------------------------------------------- password reset ---
@bp.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    form = ForgotForm()
    if form.validate_on_submit():
        start_reset(form.email.data)
        flash("If an account exists for that email, we've sent a reset link. Check your spam folder too.",
              "success")
        return redirect(url_for("coaching.login"))
    return render_template("coaching/forgot.html", form=form, active_page="coaching")


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    row = find_reset(token)
    if row is None:
        flash("This reset link has expired or was already used. Request a new one.", "error")
        return redirect(url_for("coaching.forgot_password"))
    form = ResetForm()
    if form.validate_on_submit():
        finish_reset(row, form.password.data)
        flash("Password updated. You can sign in now.", "success")
        return redirect(url_for("coaching.login"))
    return render_template("coaching/reset.html", form=form, active_page="coaching")

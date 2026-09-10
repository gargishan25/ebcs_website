from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .forms import AdminLoginForm, CoachApplicationForm, StudentLoginForm, StudentRegisterForm
from .models import CoachApplication, Match, Student, db

main = Blueprint("main", __name__)


@main.route("/")
def home():
    return render_template("home.html", active_page="home")


@main.route("/team/")
def team():
    return render_template("team.html", active_page="team")


@main.route("/events/")
def tournaments():
    return render_template("tournaments.html", active_page="tournaments")


@main.route("/2026r&b/")
def event_details():
    return render_template("event_details.html", active_page="tournaments")


# ---------- Coaching program: public-facing pages ----------
# These 404 until COACHING_ENABLED is True in app/config.py.

def _require_coaching_enabled():
    if not current_app.config["COACHING_ENABLED"]:
        abort(404)


@main.route("/coaching/")
def coaching_home():
    _require_coaching_enabled()
    return render_template("coaching_home.html", active_page="coaching")


@main.route("/coaching/apply", methods=["GET", "POST"])
def coach_apply():
    _require_coaching_enabled()
    form = CoachApplicationForm()
    if form.validate_on_submit():
        application = CoachApplication(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data,
            experience=form.experience.data,
            availability=form.availability.data,
        )
        db.session.add(application)
        db.session.commit()
        flash("Thanks! Your application has been submitted.", "success")
        return redirect(url_for("main.coach_apply"))
    return render_template("coach_apply.html", active_page="coaching", form=form)


@main.route("/student/register", methods=["GET", "POST"])
def student_register():
    _require_coaching_enabled()
    form = StudentRegisterForm()
    if form.validate_on_submit():
        existing = Student.query.filter_by(email=form.email.data).first()
        if existing:
            flash("An account with that email already exists.", "error")
        else:
            student = Student(
                name=form.name.data,
                email=form.email.data,
                password_hash=generate_password_hash(form.password.data),
            )
            db.session.add(student)
            db.session.commit()
            login_user(student)
            flash("Account created! You're signed in.", "success")
            return redirect(url_for("main.student_dashboard"))
    return render_template("student_register.html", active_page="coaching", form=form)


@main.route("/student/login", methods=["GET", "POST"])
def student_login():
    _require_coaching_enabled()
    form = StudentLoginForm()
    if form.validate_on_submit():
        student = Student.query.filter_by(email=form.email.data).first()
        if student and check_password_hash(student.password_hash, form.password.data):
            login_user(student)
            return redirect(url_for("main.student_dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("student_login.html", active_page="coaching", form=form)


@main.route("/coaching/logout")
@login_required
def student_logout():
    logout_user()
    return redirect(url_for("main.student_login"))


@main.route("/coaching/dashboard")
@login_required
def student_dashboard():
    _require_coaching_enabled()
    match = Match.query.filter_by(student_id=current_user.id).first()
    coach = match.coach_application if match else None
    return render_template("student_dashboard.html", active_page="coaching", coach=coach)


# ---------- Admin: always reachable (password-protected), independent of the flag ----------
# This lets you review applications and set up matches before COACHING_ENABLED is flipped on.

@main.route("/coaching/admin/login", methods=["GET", "POST"])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        correct_username = form.username.data == current_app.config["ADMIN_USERNAME"]
        admin_password_set = bool(current_app.config["ADMIN_PASSWORD"])
        correct_password = admin_password_set and form.password.data == current_app.config["ADMIN_PASSWORD"]
        if correct_username and correct_password:
            session["is_admin"] = True
            return redirect(url_for("main.admin_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin_login.html", form=form)


@main.route("/coaching/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("main.admin_login"))


@main.route("/coaching/admin")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("main.admin_login"))

    applications = CoachApplication.query.order_by(CoachApplication.submitted_at.desc()).all()
    students = Student.query.order_by(Student.created_at.desc()).all()
    matches = Match.query.all()

    matched_student_ids = {m.student_id for m in matches}
    matched_coach_ids = {m.coach_application_id for m in matches}

    unmatched_students = [s for s in students if s.id not in matched_student_ids]
    approved_unmatched_coaches = [
        a for a in applications if a.status == "approved" and a.id not in matched_coach_ids
    ]

    return render_template(
        "admin_dashboard.html",
        applications=applications,
        matches=matches,
        unmatched_students=unmatched_students,
        approved_unmatched_coaches=approved_unmatched_coaches,
    )


@main.route("/coaching/admin/applications/<int:application_id>/<action>")
def admin_update_application(application_id, action):
    if not session.get("is_admin"):
        return redirect(url_for("main.admin_login"))
    application = CoachApplication.query.get_or_404(application_id)
    if action == "approve":
        application.status = "approved"
    elif action == "reject":
        application.status = "rejected"
    db.session.commit()
    return redirect(url_for("main.admin_dashboard"))


@main.route("/coaching/admin/match", methods=["POST"])
def admin_create_match():
    if not session.get("is_admin"):
        return redirect(url_for("main.admin_login"))
    student_id = request.form.get("student_id")
    coach_application_id = request.form.get("coach_application_id")
    if student_id and coach_application_id:
        match = Match(student_id=student_id, coach_application_id=coach_application_id)
        db.session.add(match)
        db.session.commit()
    return redirect(url_for("main.admin_dashboard"))

@main.route("/sponsors/")
def sponsors():
    return render_template("sponsors.html", active_page="sponsors")
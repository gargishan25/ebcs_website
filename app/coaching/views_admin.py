"""Admin console: overview, coach pipeline, learner queue, matching, hours, safety."""
import json
from collections import Counter
from datetime import datetime, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from ..models import db
from . import bp
from .catalog import COACH_STATUSES
from .forms import CoachReviewForm
from .matching import WEIGHTS, rank
from .models import (CoachProfile, Event, HourEntry, LearnerProfile, Message, Pairing, Session as CSession,
                     User, log_event)
from .util import bars_svg, local_to_utc, roles_required
from .views_app import _week_start_local

admin_only = roles_required("admin")


@bp.route("/app/admin")
@admin_only
def admin_overview():
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)
    waiting = LearnerProfile.query.filter_by(status="waiting").order_by(LearnerProfile.created_at).all()
    applicants = (CoachProfile.query.filter(CoachProfile.status.in_(["applied", "screening"]))
                  .order_by(CoachProfile.created_at).all())
    pending_hours = HourEntry.query.filter_by(status="pending").count()
    flagged = Message.query.filter_by(flagged=True).count()

    completed_30 = CSession.query.filter(CSession.status == "completed", CSession.starts_at >= month_ago).count()
    no_show_30 = CSession.query.filter(CSession.status == "no_show", CSession.starts_at >= month_ago).count()
    verified_min = (db.session.query(func.coalesce(func.sum(HourEntry.minutes), 0))
                    .filter(HourEntry.status == "verified").scalar() or 0)
    avg_rating = db.session.query(func.avg(CSession.learner_rating)).filter(CSession.learner_rating.isnot(None)).scalar()

    # sessions completed per week, last 10 weeks
    weeks = 10
    start_local = _week_start_local(-(weeks - 1))
    start_utc = local_to_utc(start_local.replace(tzinfo=None))
    counts = [0] * weeks
    for (st,) in db.session.query(CSession.starts_at).filter(CSession.status == "completed",
                                                             CSession.starts_at >= start_utc).all():
        idx = (st - start_utc).days // 7
        if 0 <= idx < weeks:
            counts[idx] += 1
    labels = [(start_local + timedelta(weeks=i)).strftime("%-m/%-d") for i in range(weeks)]

    # coach capacity
    approved = CoachProfile.query.filter_by(status="approved").all()
    seats_total = sum(c.max_learners or 0 for c in approved)
    seats_used = sum(c.load for c in approved)

    kpis = [
        {"label": "Active pairings", "value": Pairing.query.filter_by(status="active").count(),
         "sub": f"{seats_used}/{seats_total} coach seats used"},
        {"label": "Waiting learners", "value": len(waiting),
         "sub": (f"longest {max(l.waiting_days for l in waiting)}d" if waiting else "queue clear"),
         "warn": bool(waiting) and max(l.waiting_days for l in waiting) > 7},
        {"label": "Sessions, 30d", "value": completed_30,
         "sub": f"{no_show_30} no-show" + ("" if no_show_30 == 1 else "s")},
        {"label": "Hours supported", "value": int(verified_min // 60), "sub": f"{pending_hours} entries to confirm"},
        {"label": "Learner rating", "value": f"{avg_rating:.1f}" if avg_rating else "-", "sub": "avg of session feedback"},
    ]
    events = Event.query.order_by(Event.created_at.desc()).limit(14).all()
    return render_template("coaching/admin_overview.html", kpis=kpis, waiting=waiting[:6], applicants=applicants[:6],
                           pending_hours=pending_hours, flagged=flagged, events=events,
                           bars=bars_svg(counts, labels), seats_free=seats_total - seats_used)


# ---------------------------------------------------------------- coaches ---
@bp.route("/app/admin/coaches")
@admin_only
def admin_coaches():
    coaches = CoachProfile.query.order_by(CoachProfile.created_at.desc()).all()
    columns = {k: [] for k, _ in COACH_STATUSES}
    for c in coaches:
        columns.setdefault(c.status, []).append(c)
    hours = dict(db.session.query(HourEntry.coach_id, func.sum(HourEntry.minutes))
                 .filter(HourEntry.status == "verified").group_by(HourEntry.coach_id).all())
    return render_template("coaching/admin_coaches.html", columns=columns, statuses=COACH_STATUSES,
                           approved=columns.get("approved", []), hours=hours)


@bp.route("/app/admin/coaches/<int:user_id>", methods=["GET", "POST"])
@admin_only
def admin_coach(user_id):
    user = db.session.get(User, user_id) or abort(404)
    profile = user.coach or abort(404)
    form = CoachReviewForm(obj=profile)
    if request.method == "GET":
        form.max_learners.data = str(profile.max_learners or 0)
    if form.validate_on_submit():
        old = profile.status
        profile.status = form.status.data
        profile.max_learners = int(form.max_learners.data)
        profile.admin_notes = form.admin_notes.data
        profile.reviewed_by_id = current_user.id
        profile.reviewed_at = datetime.utcnow()
        if old != profile.status:
            log_event(current_user, f"moved coach to {profile.status}", user.name)
        db.session.commit()
        flash("Review saved.", "success")
        return redirect(url_for("coaching.admin_coach", user_id=user.id))
    pairings = sorted(user.coach_pairings, key=lambda p: (p.status != "active", p.created_at))
    sessions = [s for p in user.coach_pairings for s in p.sessions]
    ratings = [s.learner_rating for s in sessions if s.learner_rating]
    stats = {
        "completed": sum(1 for s in sessions if s.status == "completed"),
        "no_show": sum(1 for s in sessions if s.status == "no_show"),
        "cancelled": sum(1 for s in sessions if s.status == "cancelled"),
        "rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "verified": sum(e.minutes for e in user.hour_entries if e.status == "verified"),
        "pending": sum(e.minutes for e in user.hour_entries if e.status == "pending"),
    }
    feedback = sorted([s for s in sessions if s.learner_feedback], key=lambda s: s.starts_at, reverse=True)[:5]
    return render_template("coaching/admin_coach.html", user=user, profile=profile, form=form,
                           pairings=pairings, stats=stats, feedback=feedback)


# --------------------------------------------------------------- learners ---
@bp.route("/app/admin/learners")
@admin_only
def admin_learners():
    tab = request.args.get("tab", "waiting")
    q = LearnerProfile.query
    if tab in ("waiting", "matched", "paused", "graduated"):
        q = q.filter_by(status=tab)
    learners = q.order_by(LearnerProfile.created_at).all()
    counts = Counter(s for (s,) in db.session.query(LearnerProfile.status).all())
    demand = Counter()
    for l in LearnerProfile.query.filter_by(status="waiting").all():
        for g in l.goals or []:
            demand[g] += 1
    return render_template("coaching/admin_learners.html", learners=learners, tab=tab, counts=counts,
                           demand=demand.most_common(5))


@bp.route("/app/admin/match/<int:user_id>", methods=["GET", "POST"])
@admin_only
def admin_match(user_id):
    learner_user = db.session.get(User, user_id) or abort(404)
    learner = learner_user.learner or abort(404)
    if request.method == "POST":
        coach_user = db.session.get(User, request.form.get("coach_id", type=int)) or abort(400)
        if not coach_user.coach:
            abort(400)
        if learner.active_pairing():
            flash("This learner already has an active coach.", "error")
            return redirect(url_for("coaching.admin_match", user_id=user_id))
        result = next((r for r in rank([coach_user.coach], learner)[0]), None)
        if not result and not request.form.get("override"):
            flash("That coach isn't eligible for this learner.", "error")
            return redirect(url_for("coaching.admin_match", user_id=user_id))
        pairing = Pairing(coach_id=coach_user.id, learner_id=learner_user.id, created_by_id=current_user.id,
                          score=result.total if result else None,
                          score_detail=json.dumps(result.as_dict()) if result else None)
        db.session.add(pairing)
        learner.status = "matched"
        db.session.flush()
        intro = (f"Hi {learner_user.first_name} and {coach_user.first_name}, you're matched. "
                 f"Use this thread to pick your first session time. "
                 + (f"You both have time on {result.shared_label}. " if result else "")
                 + "EBCS staff can read this thread to keep everyone safe.")
        db.session.add(Message(pairing=pairing, sender_id=current_user.id, body=intro))
        log_event(current_user, "matched", f"{learner_user.name} with {coach_user.name}")
        db.session.commit()
        flash(f"Matched {learner_user.name} with {coach_user.name}.", "success")
        return redirect(url_for("coaching.admin_learners"))

    coaches = CoachProfile.query.filter(CoachProfile.status.in_(["approved", "paused"])).all()
    eligible, ineligible = rank(coaches, learner)
    history = sorted(learner_user.learner_pairings, key=lambda p: p.created_at, reverse=True)
    return render_template("coaching/admin_match.html", learner_user=learner_user, learner=learner,
                           eligible=eligible, ineligible=ineligible, weights=WEIGHTS, history=history)


@bp.route("/app/admin/pairings/<int:pairing_id>/end", methods=["POST"])
@admin_only
def admin_end_pairing(pairing_id):
    p = db.session.get(Pairing, pairing_id) or abort(404)
    p.status = "ended"
    p.ended_at = datetime.utcnow()
    p.end_reason = (request.form.get("reason") or "")[:200]
    nxt = request.form.get("next", "waiting")
    if p.learner.learner:
        p.learner.learner.status = nxt if nxt in ("waiting", "paused", "graduated") else "waiting"
    for s in p.sessions:
        if s.status == "scheduled" and s.starts_at > datetime.utcnow():
            s.status = "cancelled"
    log_event(current_user, "ended pairing", f"{p.learner.name} / {p.coach.name}")
    db.session.commit()
    flash("Pairing ended; future sessions cancelled.", "success")
    return redirect(request.referrer or url_for("coaching.admin_learners"))


@bp.route("/app/admin/learners/<int:user_id>")
@admin_only
def admin_learner(user_id):
    """Admins reuse the coach-facing learner file, plus guardian details."""
    return redirect(url_for("coaching.learner_file", user_id=user_id))


# ------------------------------------------------------------------ hours ---
@bp.route("/app/admin/hours", methods=["GET", "POST"])
@admin_only
def admin_hours():
    if request.method == "POST":
        ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
        action = request.form.get("action")
        if ids and action in ("verified", "rejected"):
            entries = HourEntry.query.filter(HourEntry.id.in_(ids), HourEntry.status == "pending").all()
            for e in entries:
                e.status = action
                e.reviewed_by_id = current_user.id
                e.reviewed_at = datetime.utcnow()
            log_event(current_user, f"{'confirmed' if action == 'verified' else 'rejected'} hours", f"{len(entries)} entries")
            db.session.commit()
            flash(f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} {'confirmed' if action == 'verified' else 'rejected'}.", "success")
        return redirect(url_for("coaching.admin_hours"))
    pending = HourEntry.query.filter_by(status="pending").order_by(HourEntry.worked_on).all()
    recent = (HourEntry.query.filter(HourEntry.status != "pending")
              .order_by(HourEntry.reviewed_at.desc()).limit(20).all())
    return render_template("coaching/admin_hours.html", pending=pending, recent=recent)


# ----------------------------------------------------------------- safety ---
@bp.route("/app/admin/messages", methods=["GET", "POST"])
@admin_only
def admin_messages():
    if request.method == "POST":
        m = db.session.get(Message, request.form.get("id", type=int)) or abort(404)
        m.flagged = not m.flagged
        if not m.flagged:
            log_event(current_user, "cleared flag", f"message #{m.id}")
        db.session.commit()
        return redirect(url_for("coaching.admin_messages"))
    flagged = Message.query.filter_by(flagged=True).order_by(Message.created_at.desc()).all()
    recent = Message.query.order_by(Message.created_at.desc()).limit(60).all()
    pairings = Pairing.query.filter_by(status="active").order_by(Pairing.created_at.desc()).all()
    return render_template("coaching/admin_messages.html", flagged=flagged, recent=recent, pairings=pairings)


@bp.route("/app/admin/activity")
@admin_only
def admin_activity():
    page = request.args.get("page", 1, type=int)
    events = Event.query.order_by(Event.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template("coaching/admin_activity.html", events=events)

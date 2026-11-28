"""Signed-in app: dashboards, schedule, sessions, messages, learners, library, hours."""
from collections import defaultdict
from datetime import datetime, time, timedelta

from flask import Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..models import db
from . import bp
from .catalog import DAYS, HOURS, SKILLS, SKILL_LABELS, TRACKS
from .forms import (AssignForm, AvailabilityForm, FeedbackForm, HourForm, LessonForm, MessageForm,
                    ReportForm, SessionForm)
from .models import (Assignment, HourEntry, Lesson, Message, Pairing, Session as CSession,
                     SkillAssessment, User, log_event)
from .util import (bars_svg, fmt_dt, local_now, local_to_utc, radar_svg, ring_svg, roles_required,
                   to_local)


# ================================================================ helpers ===
def _active_pairings(user):
    q = Pairing.query.filter_by(status="active")
    if user.is_admin:
        return q.order_by(Pairing.created_at.desc()).all()
    if user.is_coach:
        return q.filter_by(coach_id=user.id).order_by(Pairing.created_at).all()
    return q.filter_by(learner_id=user.id).all()


def _pairing_or_404(pairing_id):
    p = db.session.get(Pairing, pairing_id) or abort(404)
    if not p.involves(current_user):
        abort(404)
    return p


def _session_or_404(session_id):
    s = db.session.get(CSession, session_id) or abort(404)
    if not s.pairing.involves(current_user):
        abort(404)
    return s


def _user_sessions_query(user):
    q = CSession.query.join(Pairing)
    if user.is_admin:
        return q
    if user.is_coach:
        return q.filter(Pairing.coach_id == user.id)
    return q.filter(Pairing.learner_id == user.id)


def skill_snapshot(learner_id, before=None):
    q = SkillAssessment.query.filter_by(learner_id=learner_id)
    if before:
        q = q.filter(SkillAssessment.created_at <= before)
    snap = {}
    for a in q.order_by(SkillAssessment.created_at).all():
        snap[a.skill] = a.level
    return snap


def _week_start_local(offset=0):
    now = local_now()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday + timedelta(weeks=offset)


def _weekly_minutes(entries, weeks=8):
    """Bucket hour entries into the last N local weeks."""
    start = _week_start_local(-(weeks - 1)).date()
    buckets = [0] * weeks
    for e in entries:
        idx = (e.worked_on - start).days // 7
        if 0 <= idx < weeks:
            buckets[idx] += e.minutes
    labels = [(start + timedelta(weeks=i)).strftime("%-m/%-d") for i in range(weeks)]
    return buckets, labels


def _unread_by_pairing(user, pairing_ids):
    if not pairing_ids:
        return {}
    rows = (db.session.query(Message.pairing_id, db.func.count(Message.id))
            .filter(Message.pairing_id.in_(pairing_ids), Message.sender_id != user.id,
                    Message.read_at.is_(None))
            .group_by(Message.pairing_id).all())
    return dict(rows)


# ============================================================= dashboards ===
@bp.route("/app")
@login_required
def app_home():
    if current_user.is_admin:
        return redirect(url_for("coaching.admin_overview"))
    if current_user.is_coach:
        return _coach_dashboard()
    return _learner_dashboard()


def _learner_dashboard():
    profile = current_user.learner
    if profile is None:
        abort(404)
    pairing = profile.active_pairing()
    ctx = {"profile": profile, "pairing": pairing}

    if not pairing:
        from .models import LearnerProfile

        ahead = LearnerProfile.query.filter(LearnerProfile.status == "waiting",
                                            LearnerProfile.created_at < profile.created_at).count()
        ctx["queue_position"] = ahead + 1
        return render_template("coaching/learner_dashboard.html", **ctx)

    completed = pairing.completed_sessions
    now_snap = skill_snapshot(current_user.id)
    prev_snap = skill_snapshot(current_user.id, before=datetime.utcnow() - timedelta(days=30))
    ctx.update(
        next_session=pairing.next_session(),
        upcoming=[s for s in pairing.sessions if s.is_upcoming][:4],
        homework=[a for a in pairing.assignments if not a.completed_at],
        done_homework=[a for a in pairing.assignments if a.completed_at][-5:],
        reports=list(reversed(completed))[:3],
        need_feedback=[s for s in completed if not s.learner_rating][-2:],
        total_sessions=len(completed),
        total_minutes=sum(s.duration_min or 0 for s in completed),
        radar=radar_svg(SKILLS, now_snap, previous=prev_snap if prev_snap != now_snap else None),
        has_skills=bool(now_snap),
        unread=_unread_by_pairing(current_user, [pairing.id]).get(pairing.id, 0),
    )
    return render_template("coaching/learner_dashboard.html", **ctx)


def _coach_dashboard():
    profile = current_user.coach
    if profile is None:
        abort(404)
    if profile.status != "approved":
        return render_template("coaching/coach_pending.html", profile=profile)

    pairings = _active_pairings(current_user)
    now = datetime.utcnow()
    sessions = _user_sessions_query(current_user).filter(CSession.status == "scheduled").order_by(CSession.starts_at).all()
    upcoming = [s for s in sessions if s.starts_at >= now - timedelta(minutes=30)][:6]
    overdue = [s for s in sessions if s.needs_report]

    entries = current_user.hour_entries
    verified = sum(e.minutes for e in entries if e.status == "verified")
    pending = sum(e.minutes for e in entries if e.status == "pending")
    goal_min = (profile.hours_goal or 40) * 60
    weekly, labels = _weekly_minutes([e for e in entries if e.status != "rejected"])

    unread = _unread_by_pairing(current_user, [p.id for p in pairings])
    roster = []
    attention = []
    for s in overdue:
        attention.append({"kind": "report", "text": f"File report for {s.pairing.learner.name}",
                          "meta": fmt_dt(s.starts_at, "short"), "href": url_for("coaching.session_detail", session_id=s.id)})
    for p in pairings:
        nxt = p.next_session()
        snap = skill_snapshot(p.learner_id)
        roster.append({"p": p, "next": nxt, "done": len(p.completed_sessions),
                       "avg": round(sum(snap.values()) / len(snap), 1) if snap else None,
                       "unread": unread.get(p.id, 0),
                       "open_hw": sum(1 for a in p.assignments if not a.completed_at)})
        if not nxt:
            attention.append({"kind": "schedule", "text": f"No session booked with {p.learner.name}",
                              "meta": "", "href": url_for("coaching.session_new", pairing=p.id)})
        if unread.get(p.id):
            attention.append({"kind": "message", "text": f"{unread[p.id]} unread from {p.learner.name}",
                              "meta": "", "href": url_for("coaching.thread", pairing_id=p.id)})
        if not snap and p.completed_sessions:
            attention.append({"kind": "assess", "text": f"Add a skill assessment for {p.learner.name}",
                              "meta": "", "href": url_for("coaching.learner_file", user_id=p.learner_id)})

    month_start = local_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_sessions = _user_sessions_query(current_user).filter(
        CSession.status == "completed",
        CSession.starts_at >= local_to_utc(month_start.replace(tzinfo=None))).count()

    return render_template(
        "coaching/coach_dashboard.html",
        profile=profile, roster=roster, upcoming=upcoming, attention=attention,
        verified=verified, pending=pending, goal_min=goal_min,
        ring=ring_svg(verified / goal_min if goal_min else 0),
        bars=bars_svg([round(m / 60, 1) for m in weekly], labels, unit="h"),
        month_sessions=month_sessions,
    )


# =============================================================== schedule ===
@bp.route("/app/schedule")
@login_required
def schedule():
    offset = request.args.get("w", 0, type=int)
    start_local = _week_start_local(offset)
    end_local = start_local + timedelta(days=7)
    start_utc = local_to_utc(start_local.replace(tzinfo=None))
    end_utc = local_to_utc(end_local.replace(tzinfo=None))

    sessions = (_user_sessions_query(current_user)
                .filter(CSession.starts_at >= start_utc, CSession.starts_at < end_utc)
                .order_by(CSession.starts_at).all())
    first_hour, last_hour = HOURS[0], HOURS[-1] + 1
    blocks = []
    for s in sessions:
        loc = to_local(s.starts_at)
        mins_from_top = (loc.hour - first_hour) * 60 + loc.minute
        if loc.hour < first_hour or loc.hour >= last_hour:
            mins_from_top = max(0, min(mins_from_top, (last_hour - first_hour) * 60 - 30))
        other = s.pairing.learner if (current_user.is_coach or current_user.is_admin) else s.pairing.coach
        blocks.append({"s": s, "day": loc.weekday(), "top": mins_from_top,
                       "height": s.duration_min or 60, "who": other.name,
                       "label": fmt_dt(s.starts_at, "time"),
                       "coach": s.pairing.coach.name})

    profile = current_user.coach or current_user.learner
    avail = set(profile.availability or []) if profile else set()
    today_idx = local_now().weekday() if offset == 0 else None
    days = [(DAYS[i], (start_local + timedelta(days=i)).day, (start_local + timedelta(days=i)).date().isoformat())
            for i in range(7)]
    now_line = None
    if offset == 0:
        n = local_now()
        if first_hour <= n.hour < last_hour:
            now_line = (n.hour - first_hour) * 60 + n.minute
    return render_template("coaching/schedule.html", blocks=blocks, days=days, hours=HOURS, avail=avail,
                           offset=offset, today_idx=today_idx, now_line=now_line,
                           range_label=f"{start_local.strftime('%b %-d')} - {(end_local - timedelta(days=1)).strftime('%b %-d, %Y')}",
                           can_schedule=current_user.is_coach or current_user.is_admin)


@bp.route("/app/calendar.ics")
@login_required
def calendar_ics():
    since = datetime.utcnow() - timedelta(days=14)
    sessions = (_user_sessions_query(current_user).filter(CSession.starts_at >= since,
                                                          CSession.status == "scheduled").all())
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//EBCS//Coaching//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:EBCS Coaching"]
    for s in sessions:
        other = s.pairing.other(current_user) if not current_user.is_admin else s.pairing.learner
        lines += ["BEGIN:VEVENT", f"UID:ebcs-session-{s.id}@ebcs", f"DTSTAMP:{stamp}",
                  f"DTSTART:{s.starts_at.strftime('%Y%m%dT%H%M%SZ')}",
                  f"DTEND:{s.ends_at.strftime('%Y%m%dT%H%M%SZ')}",
                  f"SUMMARY:Chess coaching with {other.name}",
                  f"LOCATION:{(s.location or '').replace(',', ' ')}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines), mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=ebcs-coaching.ics"})


# =============================================================== sessions ===
@bp.route("/app/sessions/new", methods=["GET", "POST"])
@roles_required("coach")
def session_new():
    pairings = _active_pairings(current_user)
    if not pairings:
        flash("You need an active learner before scheduling.", "error")
        return redirect(url_for("coaching.app_home"))
    form = SessionForm()
    form.pairing.choices = [(p.id, f"{p.learner.name}" + (f"  (coach: {p.coach.name})" if current_user.is_admin else ""))
                            for p in pairings]
    if request.method == "GET":
        pid = request.args.get("pairing", type=int)
        if pid in [p.id for p in pairings]:
            form.pairing.data = pid
        d = request.args.get("date")
        if d:
            try:
                form.date.data = datetime.strptime(d, "%Y-%m-%d").date()
            except ValueError:
                pass
        h = request.args.get("hour", type=int)
        if h is not None:
            form.time.data = time(h, 0)

    if form.validate_on_submit():
        pairing = next((p for p in pairings if p.id == form.pairing.data), None) or abort(400)
        start = local_to_utc(datetime.combine(form.date.data, form.time.data))
        dur = int(form.duration.data)
        repeats = int(form.repeat.data or 0) or 1
        created, clashes = [], []
        for i in range(repeats):
            st = start + timedelta(weeks=i)
            en = st + timedelta(minutes=dur)
            clash = (CSession.query.join(Pairing)
                     .filter(Pairing.coach_id == pairing.coach_id, CSession.status == "scheduled",
                             CSession.starts_at < en,
                             CSession.starts_at > st - timedelta(minutes=240)).all())
            if any(c.ends_at > st for c in clash):
                clashes.append(fmt_dt(st, "short"))
                continue
            s = CSession(pairing=pairing, starts_at=st, duration_min=dur, format="online",
                         location=form.location.data, agenda=form.agenda.data)
            db.session.add(s)
            created.append(s)
        if created:
            log_event(current_user, "scheduled", f"{len(created)} session(s) with {pairing.learner.name}")
            db.session.commit()
            msg = f"Scheduled {len(created)} session{'s' if len(created) > 1 else ''}."
            if clashes:
                msg += f" Skipped {len(clashes)} that clashed: {', '.join(clashes)}."
            flash(msg, "success")
            return redirect(url_for("coaching.schedule"))
        form.time.errors.append("That time clashes with a session you already have.")
    return render_template("coaching/session_new.html", form=form, pairings=pairings)


@bp.route("/app/sessions/<int:session_id>", methods=["GET", "POST"])
@login_required
def session_detail(session_id):
    s = _session_or_404(session_id)
    p = s.pairing
    is_coach = current_user.id == p.coach_id or current_user.is_admin
    is_learner = current_user.id == p.learner_id
    report_form = feedback_form = None

    if is_coach and s.status == "scheduled" and s.starts_at <= datetime.utcnow() + timedelta(minutes=15):
        report_form = ReportForm(prefix="r")
        if request.method == "GET":
            report_form.minutes.data = s.duration_min
        if report_form.submit.data and report_form.validate_on_submit():
            s.status = report_form.outcome.data
            s.reported_at = datetime.utcnow()
            if s.status == "completed":
                s.topics = report_form.topics.data
                s.summary = report_form.summary.data
                s.homework = report_form.homework.data
                if report_form.minutes.data:
                    s.duration_min = report_form.minutes.data
                if not HourEntry.query.filter_by(session_id=s.id).first():
                    db.session.add(HourEntry(coach_id=p.coach_id, session_id=s.id, kind="session",
                                             worked_on=to_local(s.starts_at).date(), minutes=s.duration_min,
                                             description=f"Session with {p.learner.name}"))
            log_event(current_user, f"reported session ({s.status})", p.learner.name)
            db.session.commit()
            flash("Report filed." + (" Your hours have been logged." if s.status == "completed" else ""), "success")
            return redirect(url_for("coaching.session_detail", session_id=s.id))

    if is_learner and s.status == "completed" and not s.learner_rating:
        feedback_form = FeedbackForm(prefix="f")
        if feedback_form.submit.data and feedback_form.validate_on_submit():
            s.learner_rating = int(feedback_form.rating.data)
            s.learner_feedback = feedback_form.feedback.data
            log_event(current_user, "left feedback", f"{s.learner_rating}/5 for {p.coach.name}")
            db.session.commit()
            flash("Thanks. Your coach sees your rating; comments go to EBCS staff too.", "success")
            return redirect(url_for("coaching.session_detail", session_id=s.id))

    return render_template("coaching/session_detail.html", s=s, p=p, is_coach=is_coach, is_learner=is_learner,
                           report_form=report_form, feedback_form=feedback_form, skill_labels=SKILL_LABELS)


@bp.route("/app/sessions/<int:session_id>/link", methods=["POST"])
@login_required
def session_link(session_id):
    """Coach (or admin) sets/changes the meeting link, optionally for every
    upcoming session with the same learner."""
    s = _session_or_404(session_id)
    p = s.pairing
    if current_user.id != p.coach_id and not current_user.is_admin:
        abort(403)
    link = (request.form.get("location") or "").strip()[:240] or None
    targets = [s]
    if request.form.get("apply_all"):
        now = datetime.utcnow()
        targets += [x for x in p.sessions
                    if x.id != s.id and x.status == "scheduled" and x.starts_at >= now]
    for x in targets:
        x.location = link
    log_event(current_user, "updated meeting link", f"{p.learner.name} ({len(targets)} session(s))")
    db.session.commit()
    flash("Meeting link updated.", "success")
    return redirect(url_for("coaching.session_detail", session_id=s.id))


@bp.route("/app/sessions/<int:session_id>/cancel", methods=["POST"])
@login_required
def session_cancel(session_id):
    s = _session_or_404(session_id)
    if s.status != "scheduled":
        abort(400)
    s.status = "cancelled"
    s.summary = (request.form.get("reason") or "").strip()[:300] or None
    log_event(current_user, "cancelled session", f"{s.pairing.learner.name}, {fmt_dt(s.starts_at, 'short')}")
    db.session.commit()
    flash("Session cancelled.", "success")
    return redirect(url_for("coaching.schedule"))


# =============================================================== messages ===
@bp.route("/app/messages")
@login_required
def inbox():
    if current_user.is_admin:
        return redirect(url_for("coaching.admin_messages"))
    q = Pairing.query.filter((Pairing.coach_id == current_user.id) | (Pairing.learner_id == current_user.id))
    pairings = q.order_by(Pairing.status, Pairing.created_at.desc()).all()
    if len(pairings) == 1:
        return redirect(url_for("coaching.thread", pairing_id=pairings[0].id))
    unread = _unread_by_pairing(current_user, [p.id for p in pairings])
    threads = [{"p": p, "other": p.other(current_user), "last": p.messages[-1] if p.messages else None,
                "unread": unread.get(p.id, 0)} for p in pairings]
    threads.sort(key=lambda t: t["last"].created_at if t["last"] else t["p"].created_at, reverse=True)
    return render_template("coaching/inbox.html", threads=threads)


@bp.route("/app/messages/<int:pairing_id>", methods=["GET", "POST"])
@login_required
def thread(pairing_id):
    p = _pairing_or_404(pairing_id)
    form = MessageForm()
    if form.validate_on_submit():
        if p.status != "active":
            flash("This pairing has ended, so the thread is read-only.", "error")
        else:
            db.session.add(Message(pairing=p, sender_id=current_user.id, body=form.body.data.strip()))
            db.session.commit()
            return redirect(url_for("coaching.thread", pairing_id=p.id) + "#end")
    now = datetime.utcnow()
    changed = False
    for m in p.messages:
        if m.sender_id != current_user.id and not m.read_at and not current_user.is_admin:
            m.read_at = now
            changed = True
    if changed:
        db.session.commit()
    other = p.learner if current_user.is_admin else p.other(current_user)
    return render_template("coaching/thread.html", p=p, form=form, other=other)


@bp.route("/app/messages/flag/<int:message_id>", methods=["POST"])
@login_required
def message_flag(message_id):
    m = db.session.get(Message, message_id) or abort(404)
    if not m.pairing.involves(current_user):
        abort(404)
    m.flagged = True
    m.flag_reason = (request.form.get("reason") or "Reported by participant")[:200]
    log_event(current_user, "reported a message", f"thread #{m.pairing_id}")
    db.session.commit()
    flash("Reported. EBCS staff will review it. You can also email eastbaychesssociety@gmail.com.", "success")
    return redirect(url_for("coaching.thread", pairing_id=m.pairing_id))


# ========================================================== learner file ===
def _coach_pairing_for(learner_id):
    q = Pairing.query.filter_by(learner_id=learner_id, status="active")
    if not current_user.is_admin:
        q = q.filter_by(coach_id=current_user.id)
    return q.first()


@bp.route("/app/learners/<int:user_id>")
@roles_required("coach")
def learner_file(user_id):
    learner = db.session.get(User, user_id) or abort(404)
    pairing = _coach_pairing_for(user_id)
    if not pairing and not current_user.is_admin:
        abort(404)
    if not learner.learner:
        abort(404)
    now_snap = skill_snapshot(user_id)
    prev_snap = skill_snapshot(user_id, before=datetime.utcnow() - timedelta(days=30))
    history = (SkillAssessment.query.filter_by(learner_id=user_id)
               .order_by(SkillAssessment.created_at.desc()).limit(30).all())
    assign_form = AssignForm()
    assign_form.lesson.choices = [(l.id, f"{l.title}") for l in
                                  Lesson.query.filter_by(published=True).order_by(Lesson.track, Lesson.level).all()]
    sessions = sorted([s for pr in learner.learner_pairings for s in pr.sessions],
                      key=lambda s: s.starts_at, reverse=True)
    return render_template("coaching/learner_file.html", learner=learner, profile=learner.learner, pairing=pairing,
                           snap=now_snap, radar=radar_svg(SKILLS, now_snap, previous=prev_snap or None),
                           history=history, assign_form=assign_form, sessions=sessions,
                           skill_labels=SKILL_LABELS)


@bp.route("/app/learners/<int:user_id>/assess", methods=["POST"])
@roles_required("coach")
def learner_assess(user_id):
    pairing = _coach_pairing_for(user_id)
    if not pairing:
        abort(404)
    current = skill_snapshot(user_id)
    changed = 0
    for key, _ in SKILLS:
        val = request.form.get(f"skill_{key}", type=int)
        if val is None or not 0 <= val <= 5:
            continue
        if current.get(key) != val:
            db.session.add(SkillAssessment(learner_id=user_id, assessed_by_id=current_user.id, skill=key,
                                           level=val, note=(request.form.get("note") or "")[:240] or None))
            changed += 1
    if changed:
        log_event(current_user, "updated skills", f"{pairing.learner.name} ({changed})")
        db.session.commit()
        flash(f"Saved {changed} skill change{'s' if changed > 1 else ''}.", "success")
    else:
        flash("No changes.", "info")
    return redirect(url_for("coaching.learner_file", user_id=user_id))


@bp.route("/app/pairings/<int:pairing_id>/assign", methods=["POST"])
@roles_required("coach")
def assign_lesson(pairing_id):
    p = _pairing_or_404(pairing_id)
    if p.coach_id != current_user.id and not current_user.is_admin:
        abort(403)
    form = AssignForm()
    form.lesson.choices = [(l.id, l.title) for l in Lesson.query.filter_by(published=True).all()]
    if form.validate_on_submit():
        db.session.add(Assignment(pairing=p, lesson_id=form.lesson.data, due_on=form.due_on.data,
                                  note=form.note.data))
        log_event(current_user, "assigned lesson", p.learner.name)
        db.session.commit()
        flash("Lesson assigned.", "success")
    else:
        flash("Couldn't assign that lesson.", "error")
    return redirect(url_for("coaching.learner_file", user_id=p.learner_id))


@bp.route("/app/assignments/<int:assignment_id>/toggle", methods=["POST"])
@login_required
def assignment_toggle(assignment_id):
    a = db.session.get(Assignment, assignment_id) or abort(404)
    if not a.pairing.involves(current_user):
        abort(404)
    a.completed_at = None if a.completed_at else datetime.utcnow()
    db.session.commit()
    return redirect(request.referrer or url_for("coaching.app_home"))


# ================================================================ library ===
@bp.route("/app/library")
@login_required
def library():
    track = request.args.get("track")
    q = Lesson.query
    if not (current_user.is_coach or current_user.is_admin):
        q = q.filter_by(published=True)
    if track:
        q = q.filter_by(track=track)
    lessons = q.order_by(Lesson.level, Lesson.title).all()
    grouped = defaultdict(list)
    for l in lessons:
        grouped[l.track].append(l)
    assigned = {}
    if current_user.is_learner:
        for p in current_user.learner_pairings:
            for a in p.assignments:
                assigned[a.lesson_id] = a
    return render_template("coaching/library.html", grouped=grouped, tracks=TRACKS, track=track,
                           assigned=assigned, count=len(lessons))


@bp.route("/app/library/<slug>")
@login_required
def lesson(slug):
    l = Lesson.query.filter_by(slug=slug).first_or_404()
    if not l.published and not (current_user.is_coach or current_user.is_admin):
        abort(404)
    assignment = None
    if current_user.is_learner:
        for p in current_user.learner_pairings:
            for a in p.assignments:
                if a.lesson_id == l.id and not a.completed_at:
                    assignment = a
    siblings = Lesson.query.filter_by(track=l.track, published=True).order_by(Lesson.level, Lesson.title).all()
    return render_template("coaching/lesson.html", l=l, assignment=assignment, siblings=siblings)


def _slugify(text):
    import re

    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70] or "lesson"
    slug, n = base, 2
    while Lesson.query.filter_by(slug=slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


@bp.route("/app/library/new", methods=["GET", "POST"])
@bp.route("/app/library/<slug>/edit", methods=["GET", "POST"])
@roles_required("coach")
def lesson_edit(slug=None):
    if current_user.is_coach and (not current_user.coach or current_user.coach.status != "approved"):
        abort(403)
    l = Lesson.query.filter_by(slug=slug).first_or_404() if slug else None
    if l and not current_user.is_admin and l.created_by_id != current_user.id:
        abort(403)
    form = LessonForm(obj=l)
    if request.method == "GET" and l:
        form.level.data = str(l.level)
    if form.validate_on_submit():
        if not l:
            l = Lesson(slug=_slugify(form.title.data), created_by_id=current_user.id)
            db.session.add(l)
        form.populate_obj(l)
        l.level = int(form.level.data)
        l.fen = (l.fen or "").strip() or None
        log_event(current_user, "saved lesson", l.title)
        db.session.commit()
        flash("Lesson saved.", "success")
        return redirect(url_for("coaching.lesson", slug=l.slug))
    return render_template("coaching/lesson_edit.html", form=form, l=l)


# ================================================================== hours ===
@bp.route("/app/hours", methods=["GET", "POST"])
@roles_required("coach")
def hours():
    form = HourForm()
    if request.method == "GET":
        form.worked_on.data = local_now().date()
    if form.validate_on_submit():
        db.session.add(HourEntry(coach_id=current_user.id, kind=form.kind.data, worked_on=form.worked_on.data,
                                 minutes=form.minutes.data, description=form.description.data))
        log_event(current_user, "logged hours", f"{form.minutes.data} min")
        db.session.commit()
        flash("Logged. EBCS staff will confirm it.", "success")
        return redirect(url_for("coaching.hours"))
    entries = sorted(current_user.hour_entries, key=lambda e: (e.worked_on, e.id), reverse=True)
    totals = defaultdict(int)
    for e in entries:
        totals[e.status] += e.minutes
    profile = current_user.coach
    goal = (profile.hours_goal if profile else 40) * 60
    return render_template("coaching/hours.html", form=form, entries=entries, totals=totals, goal=goal,
                           ring=ring_svg(totals["verified"] / goal if goal else 0, size=120, stroke=10))


@bp.route("/app/hours/statement")
@roles_required("coach")
def hours_statement():
    coach = current_user
    if current_user.is_admin and request.args.get("coach", type=int):
        coach = db.session.get(User, request.args.get("coach", type=int)) or abort(404)
    entries = sorted([e for e in coach.hour_entries if e.status == "verified"], key=lambda e: e.worked_on)
    by_month = defaultdict(int)
    for e in entries:
        by_month[e.worked_on.strftime("%B %Y")] += e.minutes
    total = sum(e.minutes for e in entries)
    return render_template("coaching/hours_statement.html", coach=coach, entries=entries, by_month=by_month,
                           total=total, issued=local_now())


# =============================================================== settings ===
@bp.route("/app/settings", methods=["GET", "POST"])
@login_required
def settings():
    profile = current_user.coach or current_user.learner
    form = AvailabilityForm(obj=profile) if profile else None
    if form and form.submit.data and form.validate_on_submit():
        profile.availability = form.availability.data
        if current_user.is_coach and request.form.get("bio") is not None:
            profile.bio = request.form.get("bio", "")[:600]
        db.session.commit()
        flash("Saved.", "success")
        return redirect(url_for("coaching.settings"))
    if request.method == "POST" and request.form.get("action") == "password":
        # CSRF is already enforced app-wide by CSRFProtect.
        cur, new = request.form.get("current", ""), request.form.get("new", "")
        if not current_user.check_password(cur):
            flash("Current password is wrong.", "error")
        elif len(new) < 8:
            flash("New password needs at least 8 characters.", "error")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password updated.", "success")
        return redirect(url_for("coaching.settings"))
    return render_template("coaching/settings.html", form=form, profile=profile)

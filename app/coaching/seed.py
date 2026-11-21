"""CLI commands and first-run helpers.

    flask --app run coaching-admin you@example.com "Your Name"   create/promote an admin
    flask --app run coaching-demo                                 fill a LOCAL db with demo data

On Render, set ADMIN_EMAIL and ADMIN_PASSWORD env vars and an admin account
is created automatically on boot if it doesn't exist yet.
"""
import os
import random
from datetime import datetime, timedelta

import click

from ..models import db
from .catalog import ALL_SLOTS, SKILLS
from .models import (Assignment, CoachProfile, HourEntry, LearnerProfile, Lesson, Message, Pairing,
                     Session, SkillAssessment, User, log_event)


def ensure_env_admin(app):
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD")
    if not email or not password:
        return
    if User.query.filter_by(email=email).first():
        return
    u = User(email=email, name=os.environ.get("ADMIN_NAME", "EBCS Admin"), role="admin")
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    app.logger.info("coaching: created admin %s", email)


def register_cli(app):
    @app.cli.command("coaching-admin")
    @click.argument("email")
    @click.argument("name")
    @click.password_option()
    def create_admin(email, name, password):
        """Create an admin account, or promote an existing one."""
        email = email.strip().lower()
        u = User.query.filter_by(email=email).first()
        if u:
            u.role = "admin"
            click.echo(f"Promoted {email} to admin.")
        else:
            u = User(email=email, name=name, role="admin")
            db.session.add(u)
            click.echo(f"Created admin {email}.")
        u.set_password(password)
        db.session.commit()

    @app.cli.command("coaching-demo")
    @click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
    def demo(yes):
        """Fill the database with realistic demo data (local use only)."""
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not uri.startswith("sqlite") and not yes:
            click.confirm(f"This is not a SQLite database ({uri.split('@')[-1]}). Really add demo data?", abort=True)
        if User.query.filter(User.email.like("%@demo.ebcs")).first():
            click.echo("Demo data already present.")
            return
        _build_demo()
        click.echo("Demo data created. Sign in with admin@demo.ebcs / coach1@demo.ebcs / learner1@demo.ebcs, "
                   "password: chessdemo")


def _slots(rng, n, days=None):
    pool = [s for s in ALL_SLOTS if days is None or int(s.split("-")[0]) in days]
    pool = [s for s in pool if 15 <= int(s.split("-")[1]) <= 19 or int(s.split("-")[0]) >= 5]
    return sorted(rng.sample(pool, min(n, len(pool))))


def _build_demo():
    rng = random.Random(7)
    pw = "chessdemo"

    def mk(email, name, role):
        u = User(email=email, name=name, role=role, created_at=datetime.utcnow() - timedelta(days=rng.randint(20, 60)))
        u.set_password(pw)
        db.session.add(u)
        return u

    admin = mk("admin@demo.ebcs", "Ishan Garg", "admin")

    coach_specs = [
        ("Maya Chen", "Mission San Jose High", "11", 1840, None, ["tactics", "openings", "tournament"], "approved", 3),
        ("Arjun Patel", "American High", "12", 1720, None, ["endgames", "strategy", "analysis"], "approved", 2),
        ("Lucas Romero", "Irvington High", "10", None, 1910, ["fundamentals", "tactics", "comeback"], "approved", 2),
        ("Priya Nair", "Washington High", "11", 1560, None, ["fundamentals", "openings"], "approved", 2),
        ("Ethan Wong", "Mission San Jose High", "9", 1490, None, ["tactics"], "screening", 2),
        ("Sofia Alvarez", "Logan High", "12", None, 1650, ["fundamentals", "comeback"], "applied", 1),
    ]
    coaches = []
    for i, (name, school, grade, uscf, online, specs, status, cap) in enumerate(coach_specs, 1):
        u = mk(f"coach{i}@demo.ebcs", name, "coach")
        c = CoachProfile(user=u, school=school, grade=grade, uscf_rating=uscf, online_rating=online,
                         online_platform="lichess" if online else None,
                         online_username=name.split()[0].lower() + "_plays" if online else None,
                         experience="Rated player for several years; helped run my school's chess club.",
                         why="I learned from older players who gave me their time. I want to do the same.",
                         bio=f"{grade}th grader at {school}. Loves {specs[0]}.", specialties=specs,
                         formats=["online"],
                         availability=_slots(rng, 14), max_learners=cap, status=status,
                         agreed_conduct_at=datetime.utcnow(), created_at=u.created_at)
        if status == "approved":
            c.reviewed_by = admin
            c.reviewed_at = u.created_at + timedelta(days=3)
        db.session.add(c)
        coaches.append(c)

    learner_specs = [
        ("Aiden Brooks", "10_13", "casual", None, ["tactics", "openings"]),
        ("Hannah Kim", "14_17", "club", 1050, ["tournament", "endgames"]),
        ("Rohan Mehta", "u10", "new", None, ["fundamentals"]),
        ("Grace Liu", "18p", "casual", None, ["comeback", "strategy"]),
        ("Noah Fischer", "10_13", "club", 900, ["tactics", "analysis"]),
        ("Olivia Park", "14_17", "casual", None, ["openings", "tactics"]),
        ("David Okafor", "18p", "new", None, ["fundamentals", "tactics"]),
        ("Isla Moreno", "10_13", "competitive", 1320, ["tournament", "openings"]),
        ("Kabir Singh", "u10", "casual", None, ["fundamentals", "tactics"]),
    ]
    learners = []
    for i, (name, age, level, rating, goals) in enumerate(learner_specs, 1):
        u = mk(f"learner{i}@demo.ebcs", name, "learner")
        lp = LearnerProfile(user=u, age_band=age, level=level, rating=rating, goals=goals,
                            formats=["online"],
                            availability=_slots(rng, 10),
                            created_at=datetime.utcnow() - timedelta(days=rng.randint(1, 40)))
        if lp.is_minor:
            lp.guardian_name = "Parent of " + name.split()[0]
            lp.guardian_email = f"parent{i}@demo.ebcs"
            lp.guardian_consent_at = datetime.utcnow()
        db.session.add(lp)
        learners.append(lp)
    db.session.flush()

    # pairings: first five learners matched; make sure they share hours with their coach
    plan = [(0, 0), (1, 1), (2, 2), (3, 1), (4, 0)]
    lessons = Lesson.query.all()
    for li, ci in plan:
        lp, c = learners[li], coaches[ci]
        shared = rng.sample(c.availability, 3)
        lp.availability = sorted(set(lp.availability) | set(shared))
        lp.status = "matched"
        p = Pairing(coach_id=c.user_id, learner_id=lp.user_id, created_by_id=admin.id, score=rng.randint(68, 92),
                    created_at=datetime.utcnow() - timedelta(days=35))
        db.session.add(p)
        db.session.flush()
        db.session.add(Message(pairing=p, sender_id=admin.id, created_at=p.created_at,
                               body=f"Hi {lp.user.first_name} and {c.user.first_name}, you're matched. "
                                    "Use this thread to pick your first session time."))
        db.session.add(Message(pairing=p, sender_id=c.user_id, created_at=p.created_at + timedelta(hours=3),
                               body="Hey! Does Thursday after school work for a first session? We'll start with a "
                                    "quick game so I can see how you play."))
        db.session.add(Message(pairing=p, sender_id=lp.user_id, created_at=p.created_at + timedelta(hours=5),
                               body="Thursday works. Looking forward to it!"))

        # past weekly sessions, one future, one overdue report for the first coach
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(weeks=5)
        base = base.replace(hour=1 + li)  # ~5-9pm Pacific previous day, varied
        for w in range(5):
            st = base + timedelta(weeks=w)
            s = Session(pairing=p, starts_at=st, duration_min=60, format="online",
                        location="https://meet.google.com/ebc-demo", status="completed",
                        topics=rng.sample([k for k, _ in SKILLS], 2),
                        summary=rng.choice([
                            "Played a training game, then reviewed the opening. Worked on developing before attacking.",
                            "Tactics set on forks and pins. Got 7/10 on first try, all 10 after hints.",
                            "King and pawn endings: opposition and the rule of the square.",
                            "Reviewed last weekend's online games. Main theme: hanging pieces after move 15."]),
                        homework="Ten puzzles a day on Lichess, focus on forks.",
                        reported_at=st + timedelta(hours=2),
                        learner_rating=rng.choice([4, 5, 5, None]))
            db.session.add(s)
            db.session.flush()
            db.session.add(HourEntry(coach_id=c.user_id, session_id=s.id, kind="session", worked_on=st.date(),
                                     minutes=60, description=f"Session with {lp.user.name}",
                                     status="verified" if w < 4 else "pending", reviewed_by_id=admin.id if w < 4 else None,
                                     reviewed_at=st + timedelta(days=2) if w < 4 else None))
        if li == 0:
            db.session.add(Session(pairing=p, starts_at=datetime.utcnow() - timedelta(days=1, hours=1),
                                   duration_min=60, format="online", location="https://meet.google.com/ebc-demo"))
        db.session.add(Session(pairing=p, starts_at=base + timedelta(weeks=6), duration_min=60, format="online",
                               location="https://meet.google.com/ebc-demo",
                               agenda="Review homework puzzles, then a themed game."))

        # skills: an older snapshot and a newer one
        for k, _ in SKILLS:
            lvl = rng.randint(1, 3)
            db.session.add(SkillAssessment(learner_id=lp.user_id, assessed_by_id=c.user_id, skill=k, level=lvl,
                                           created_at=datetime.utcnow() - timedelta(days=34)))
            if rng.random() < 0.6:
                db.session.add(SkillAssessment(learner_id=lp.user_id, assessed_by_id=c.user_id, skill=k,
                                               level=min(5, lvl + 1), created_at=datetime.utcnow() - timedelta(days=4)))
        for lesson in rng.sample(lessons, 3):
            db.session.add(Assignment(pairing=p, lesson=lesson, note="Try it before our next session.",
                                      completed_at=datetime.utcnow() - timedelta(days=2) if rng.random() < 0.4 else None))

    db.session.add(HourEntry(coach_id=coaches[0].user_id, kind="event", worked_on=(datetime.utcnow() - timedelta(days=9)).date(),
                             minutes=180, description="Helped run EBCS casual play afternoon"))
    log_event(admin, "loaded demo data")
    db.session.commit()

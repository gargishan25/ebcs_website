import os
from datetime import timedelta


def _normalize_db_url(url: str) -> str:
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.environ.get("DATABASE_URL_POOLED")
        or os.environ.get("DATABASE_URL")
        or "sqlite:///coaching.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # v1 admin login (retired, kept for reference). The new platform uses
    # real admin accounts: set ADMIN_EMAIL + ADMIN_PASSWORD (and optionally
    # ADMIN_NAME) on Render and one is created automatically on boot.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

    # Coaching platform (app/coaching/). When False, the public coaching
    # pages and sign-up return 404 and the nav link is hidden, but /coaching/login
    # and the signed-in app keep working so staff can prepare.
    COACHING_ENABLED = True
    COACHING_TZ = "America/Los_Angeles"

    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("RENDER") is not None  # https only on Render
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

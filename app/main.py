import os

from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from .config import Config
from .models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # The repo is public, so the fallback SECRET_KEY in config.py is known to
    # anyone. Refuse to run on Render without a real one (it signs logins).
    if os.environ.get("RENDER") and app.config["SECRET_KEY"] in ("", "dev-secret-change-me"):
        raise RuntimeError("SECRET_KEY is not set. Add a long random SECRET_KEY in Render > Environment.")

    db.init_app(app)
    CSRFProtect(app)

    login_manager = LoginManager()
    # Sign-in now goes through the coaching platform (app/coaching/).
    # v1 used "main.student_login", which is retired (see app/routes.py).
    login_manager.login_view = "coaching.login"
    login_manager.login_message = None
    login_manager.init_app(app)

    from .coaching.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from .routes import main
    app.register_blueprint(main)

    from .coaching import bootstrap, init_coaching
    init_coaching(app)

    @app.context_processor
    def inject_coaching_flag():
        return {"coaching_enabled": app.config["COACHING_ENABLED"]}

    with app.app_context():
        db.create_all()
        bootstrap(app)  # starter lessons + admin from ADMIN_EMAIL/ADMIN_PASSWORD

    return app

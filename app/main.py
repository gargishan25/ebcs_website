from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from .config import Config
from .models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    CSRFProtect(app)

    login_manager = LoginManager()
    login_manager.login_view = "main.student_login"
    login_manager.init_app(app)

    from .models import Student

    @login_manager.user_loader
    def load_student(student_id):
        return Student.query.get(int(student_id))

    from .routes import main
    app.register_blueprint(main)

    @app.context_processor
    def inject_coaching_flag():
        return {"coaching_enabled": app.config["COACHING_ENABLED"]}

    with app.app_context():
        db.create_all()

    return app
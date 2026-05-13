from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app(config_class="config.Config"):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from app.auth.routes import auth_bp
    from app.expenses.routes import expenses_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")

    @app.route("/")
    def index():
        return redirect(url_for("expenses.dashboard"))

    with app.app_context():
        db.create_all()

    return app
from flask import Flask
from pathlib import Path

# Simple in-memory store placeholder (will be populated after parsing)
COURSES = []
COURSES_BY_ID = {}


def create_app():
    # Base project directory: .../uni_programme
    base_dir = Path(__file__).resolve().parent.parent
    # Tell Flask where templates & static actually are (currently at project root)
    app = Flask(
        __name__,
        template_folder=str(base_dir / 'templates'),
        static_folder=str(base_dir / 'static')
    )
    app.config['SECRET_KEY'] = 'dev-key'  # Replace with secure key in production

    from .routes import bp as main_bp
    app.register_blueprint(main_bp)

    return app

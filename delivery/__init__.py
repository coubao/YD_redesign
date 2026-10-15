"""Application delivery module, with storage separate from the public website."""

from .routes import bp


def init_app(app):
    app.register_blueprint(bp, url_prefix='/delivery')

    from .commands import register_commands
    register_commands(app)

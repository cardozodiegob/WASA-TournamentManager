"""Blueprint registration for Tournament Manager V10."""

def register_blueprints(app):
    from routes.main import main_bp
    from routes.clans import clans_bp
    from routes.tournaments import tournaments_bp
    from routes.matches import matches_bp
    from routes.economy import economy_bp
    from routes.social import social_bp
    from routes.admin import admin_bp
    from routes.seasons import seasons_bp
    from routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(clans_bp)
    app.register_blueprint(tournaments_bp)
    app.register_blueprint(matches_bp)
    app.register_blueprint(economy_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(seasons_bp)
    app.register_blueprint(api_bp)

    from routes.chat import chat_bp
    app.register_blueprint(chat_bp)

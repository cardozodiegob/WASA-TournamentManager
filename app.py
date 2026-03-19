#!/usr/bin/env python3
"""
Tournament Manager V10 — Modular Flask Application
===================================================
Startup, hooks, context processors, db init.
Core objects (app, db, lm, log) live in extensions.py.
"""
import os, secrets, sqlite3
from datetime import datetime, timezone
from flask import request, g
from flask_login import current_user

from extensions import app, db, lm, log

_DIR = os.path.dirname(os.path.abspath(__file__))
_DB = os.path.join(_DIR, 'tournament_manager.db')

# Throttle for verification timeout checks (at most once per 5 minutes)
_last_timeout_check = 0.0


# ===========================================================================
# USER LOADER
# ===========================================================================
@lm.user_loader
def _lu(uid_token):
    from models import User
    try:
        parts = uid_token.split('|', 1)
        uid = int(parts[0])
        token = parts[1] if len(parts) > 1 else ''
        user = db.session.get(User, uid)
        if user is None:
            return None
        if user.session_token and token and user.session_token != token:
            return None
        return user
    except Exception:
        return None


# ===========================================================================
# REQUEST HOOKS
# ===========================================================================
@app.before_request
def _br():
    global _last_timeout_check
    g.theme = request.cookies.get('theme','dark')
    g.navbar_position = 'top'
    g.font_size = 'medium'
    try:
        if current_user and current_user.is_authenticated:
            g.theme = current_user.theme or g.theme
            g.navbar_position = current_user.navbar_position or 'top'
            g.font_size = current_user.font_size or 'medium'
            current_user.last_seen = datetime.now(timezone.utc)
    except Exception: pass
    # Throttled verification timeout check (at most once per 5 minutes)
    import time as _time
    now = _time.time()
    if now - _last_timeout_check >= 300:
        _last_timeout_check = now
        try:
            from helpers import _check_verification_timeouts
            _check_verification_timeouts()
        except Exception:
            pass

@app.after_request
def _cache(response):
    if request.path.startswith('/static/uploads/'):
        response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
        response.headers['Vary'] = 'Accept-Encoding'
    elif request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
        response.headers['Vary'] = 'Accept-Encoding'
    elif request.path.startswith('/favicon'):
        response.headers['Cache-Control'] = 'public, max-age=2592000'
    else:
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response


# ===========================================================================
# CONTEXT PROCESSORS
# ===========================================================================
@app.context_processor
def _inject_all():
    from flask_wtf.csrf import generate_csrf
    from helpers import COUNTRY_FLAGS
    def bust(path):
        try:
            full = os.path.join(app.config['UPLOAD_FOLDER'], path)
            mt = int(os.path.getmtime(full))
            return f"uploads/{path}?v={mt}"
        except OSError:
            return f"uploads/{path}"
    def rank_color(rank_title):
        m={'Undetermined':'#888',
           'Here for the Laughs':'#ff69b4','Twig':'#8B4513','Wood Plank':'#a0522d','Wood':'#b8860b',
           'Bronze Initiate':'#cd7f32','Bronze':'#cd8932',
           'Silver Elite Master':'#aaa',
           'Gold Nova':'#ffd700','Gold Nova Master':'#f0c800','Master Guardian':'#00b894',
           'Master Guardian Elite':'#00a88a','Distinguished Master Guardian':'#00cec9',
           'Legendary Eagle':'#6c5ce7','Legendary Eagle Master':'#a29bfe','Supreme':'#e17055','Global Elite':'#ff1744'}
        return m.get(rank_title,'#888')
    return dict(csrf_token=generate_csrf, bust=bust, rank_color=rank_color, country_flags=COUNTRY_FLAGS)

@app.context_processor
def _inject_alerts():
    from helpers import _top_alerts
    try: return dict(top_alerts=_top_alerts())
    except Exception: return dict(top_alerts=[])


# ===========================================================================
# AUTO MIGRATE
# ===========================================================================
def _auto_migrate():
    conn = sqlite3.connect(_DB)
    c = conn.cursor()
    migrations = [
        ("tournaments", "bracket_generated", "BOOLEAN NOT NULL DEFAULT 0"),
        ("tournaments", "current_round", "INTEGER NOT NULL DEFAULT 0"),
        ("matches", "bracket_pos", "INTEGER"),
        ("matches", "counter_p1", "INTEGER"),
        ("matches", "counter_p2", "INTEGER"),
        ("matches", "counter_by", "INTEGER"),
        ("matches", "winner_comment", "TEXT"),
        ("users", "session_token", "VARCHAR(64)"),
        ("clans", "bg_image", "VARCHAR(256)"),
        ("clans", "color_primary", "VARCHAR(7) DEFAULT '#6c5ce7'"),
        ("clans", "color_secondary", "VARCHAR(7) DEFAULT '#1e1e2e'"),
        ("clans", "invite_only", "BOOLEAN NOT NULL DEFAULT 0"),
        ("tournaments", "seeding_mode", "VARCHAR(32) DEFAULT 'elo'"),
        ("tournaments", "banner_image", "VARCHAR(256)"),
        ("tournaments", "logo", "VARCHAR(256)"),
        ("tournaments", "color_primary", "VARCHAR(7) DEFAULT '#6c5ce7'"),
        ("tournaments", "color_secondary", "VARCHAR(7) DEFAULT '#1e1e2e'"),
        ("users", "profile_color", "VARCHAR(7) DEFAULT '#6c5ce7'"),
        ("users", "featured_ach_id", "INTEGER"),
        ("matches", "proof_image", "VARCHAR(256)"),
        ("season_archives", "profile_color", "VARCHAR(7)"),
        ("season_archives", "featured_ach_id", "INTEGER"),
        ("users", "profile_color", "VARCHAR(7) DEFAULT '#6c5ce7'"),
        ("users", "featured_ach_id", "INTEGER"),
        ("users", "title", "VARCHAR(64)"),
        ("users", "country", "VARCHAR(2)"),
        ("users", "country_name", "VARCHAR(64)"),
        ("challenges", "ranked", "BOOLEAN NOT NULL DEFAULT 0"),
        # V10 additions
        ("users", "points", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "last_login_bonus", "DATE"),
        ("clans", "treasury", "INTEGER NOT NULL DEFAULT 0"),
        ("matches", "stake", "INTEGER NOT NULL DEFAULT 0"),
        ("matches", "series_format", "VARCHAR(8) NOT NULL DEFAULT 'bo1'"),
        ("tournaments", "default_series", "VARCHAR(8) NOT NULL DEFAULT 'bo1'"),
        ("challenges", "stake", "INTEGER NOT NULL DEFAULT 0"),
        ("challenges", "series_format", "VARCHAR(8) NOT NULL DEFAULT 'bo1'"),
        ("matches", "scheduled_at", "DATETIME"),
        # V11 additions
        ("tournaments", "verify_timeout_days", "INTEGER NOT NULL DEFAULT 0"),
        ("matches", "p1_total_points", "INTEGER NOT NULL DEFAULT 0"),
        ("matches", "p2_total_points", "INTEGER NOT NULL DEFAULT 0"),
        # V12 additions
        ("users", "font_size", "VARCHAR(16) NOT NULL DEFAULT 'medium'"),
        ("users", "navbar_position", "VARCHAR(16) NOT NULL DEFAULT 'top'"),
        # V13 additions
        ("cosmetic_items", "rarity", "VARCHAR(16) NOT NULL DEFAULT 'common'"),
        ("cosmetic_items", "effect_type", "VARCHAR(16) NOT NULL DEFAULT 'none'"),
        # V14 additions
        ("users", "showcase_config", "TEXT"),
        # V15 additions
        ("custom_clan_achievement_types", "image", "VARCHAR(256)"),
        # V16 additions
        ("cosmetic_items", "effect_mode", "VARCHAR(16) NOT NULL DEFAULT 'css'"),
        # V17 additions
        ("users", "chat_muted_until", "DATETIME"),
    ]
    for table, col, coltype in migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
            log.info(f"MIGRATE: Added {table}.{col}")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


# ===========================================================================
# INIT DB
# ===========================================================================
def init_db():
    from models import User, EloSnap
    log.info("Creating tables...")
    db.create_all()
    _auto_migrate()
    from sqlalchemy import inspect
    log.info(f"Tables: {inspect(db.engine).get_table_names()}")
    if User.query.count()==0:
        a=User(username='admin',email='admin@tm.local',admin=True,display_name='Admin',session_token=secrets.token_hex(32))
        a.set_pw('admin123')
        db.session.add(a); db.session.commit()
        db.session.add(EloSnap(user_id=a.id,elo_val=1200)); db.session.commit()
        log.info(f"ADMIN: id={a.id} is_active={a.is_active}")
    else:
        for u in User.query.filter(User.session_token.is_(None)).all():
            u.session_token = secrets.token_hex(32)
        db.session.commit()
        log.info(f"DB has {User.query.count()} users")
    log.info(f"DB: {_DB}")


# ===========================================================================
# BLUEPRINT REGISTRATION & STARTUP
# ===========================================================================
def _register_blueprints():
    from routes import register_blueprints
    register_blueprints(app)

def _startup():
    _register_blueprints()
    os.makedirs(os.path.join(_DIR, 'backups'), exist_ok=True)
    with app.app_context():
        init_db()

_startup()

if __name__=='__main__':
    app.run(debug=True, host='0.0.0.0', port=5000,
            extra_files=[], exclude_patterns=['*.db','*.db-journal','.secret_key'])

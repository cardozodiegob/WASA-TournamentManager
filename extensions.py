"""
Shared Flask extensions — single source of truth for app, db, log.
Every module imports from here to avoid circular imports and dual-module issues.
"""
import os, secrets, logging
from datetime import timedelta
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

_DIR = os.path.dirname(os.path.abspath(__file__))
_DB = os.path.join(_DIR, 'tournament_manager.db')
_KEY_FILE = os.path.join(_DIR, '.secret_key')

def _get_secret_key():
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, 'r') as f:
            key = f.read().strip()
            if key: return key
    key = secrets.token_hex(32)
    with open(_KEY_FILE, 'w') as f: f.write(key)
    return key

app = Flask(__name__, static_folder=os.path.join(_DIR, 'static'), static_url_path='/static',
            template_folder=os.path.join(_DIR, 'templates'))
app.config.update(
    SECRET_KEY=_get_secret_key(),
    SQLALCHEMY_DATABASE_URI=f'sqlite:///{_DB}',
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=16*1024*1024,
    UPLOAD_FOLDER=os.path.join(_DIR, 'static', 'uploads'),
    ALLOWED_EXT={'png','jpg','jpeg','gif','webp'},
    PIC_MAX=512, PLACEMENT=3,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_DURATION=timedelta(days=30),
    SESSION_COOKIE_NAME='tm_session',
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
for d in ['profiles','news','clans','misc','achievements','tournaments']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], d), exist_ok=True)

db = SQLAlchemy(app)
lm = LoginManager(app)
lm.login_view = 'main.login'
lm.login_message_category = 'info'
lm.session_protection = 'strong'
log = logging.getLogger('tm')
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

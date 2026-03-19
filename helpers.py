"""Utility functions, caching, rate limiting, ELO, bracket logic for Tournament Manager V10."""
import os, re, uuid, math, functools, random, time, logging, json
from datetime import datetime, timedelta, timezone
from flask import url_for, session, jsonify, abort, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import or_, and_, func

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

from extensions import db, app, log

# ===========================================================================
# DATA CONSTANTS
# ===========================================================================
COSMETIC_CATEGORIES = [
    'avatar_frame', 'profile_border', 'profile_banner', 'badge',
    'name_color', 'name_effect', 'chat_flair', 'profile_background',
    'profile_effect', 'title'
]

RARITY_TIERS = ['common', 'uncommon', 'rare', 'epic', 'legendary']

RARITY_COLORS = {
    'common': '#9e9e9e',
    'uncommon': '#4caf50',
    'rare': '#2196f3',
    'epic': '#9c27b0',
    'legendary': '#ffc107',
}

EFFECT_TYPES = ['none', 'glow', 'pulse', 'sparkle', 'rainbow', 'shadow', 'particle', 'holographic', 'glitch', 'animated_gradient']

EFFECT_MODES = ['css', 'svg_filter', 'canvas']

CANVAS_EFFECT_KEYS = [
    'sunburst_rays', 'electric_border', 'fire_aura', 'smoke_trail',
    'matrix_rain', 'lightning', 'plasma_field', 'snowfall_sparkle'
]

SHOWCASE_METRICS = {
    'elo': {'label': 'ELO', 'icon': 'fas fa-chart-line'},
    'win_rate': {'label': 'Win Rate', 'icon': 'fas fa-percentage'},
    'current_streak': {'label': 'Current Streak', 'icon': 'fas fa-fire'},
    'best_streak': {'label': 'Best Streak', 'icon': 'fas fa-trophy'},
    'pongcoins': {'label': 'PongCoins', 'icon': 'fas fa-coins'},
    'sets_won': {'label': 'Sets Won', 'icon': 'fas fa-check-circle'},
    'sets_lost': {'label': 'Sets Lost', 'icon': 'fas fa-times-circle'},
    'avg_pts_per_set': {'label': 'Avg Pts/Set', 'icon': 'fas fa-calculator'},
    'total_ranked': {'label': 'Ranked Matches', 'icon': 'fas fa-star'},
    'total_unranked': {'label': 'Unranked Matches', 'icon': 'fas fa-gamepad'},
    'rank_title': {'label': 'Rank', 'icon': 'fas fa-medal'},
    'points_scored': {'label': 'Points Scored', 'icon': 'fas fa-bullseye'},
}

DEFAULT_SHOWCASE = ['elo', 'win_rate', 'current_streak']

ENDORSEMENT_CATEGORIES = ['Good Sport', 'Fast Server', 'Spin Master', 'Clutch Player', 'Tactical Genius']

CLAN_ACHIEVEMENT_TYPES = {
    'score_1000': {'name': 'Rising Clan', 'icon': 'fas fa-star', 'desc': 'Reach 1,000 clan score'},
    'score_5000': {'name': 'Powerhouse', 'icon': 'fas fa-fire', 'desc': 'Reach 5,000 clan score'},
    'score_10000': {'name': 'Legendary Clan', 'icon': 'fas fa-crown', 'desc': 'Reach 10,000 clan score'},
    'war_veterans': {'name': 'War Veterans', 'icon': 'fas fa-shield-alt', 'desc': 'Win 3 clan wars'},
    'elite_squad': {'name': 'Elite Squad', 'icon': 'fas fa-gem', 'desc': '5 members with ELO > 1800'},
}

TITLE_COLORS = {
    'Centurion':'#ffd700','Veteran':'#f0c800','Seasoned':'#e0b800','Competitor':'#c0a000',
    'Unstoppable':'#ff1744','Dominator':'#ff4444','On Fire':'#ff6b6b','Hot Streak':'#ff8a80','Momentum':'#ffab91',
    'Elite':'#6c5ce7','Sharpshooter':'#a29bfe','Consistent':'#74b9ff',
    'Giant Slayer':'#e17055','Upset King':'#fdcb6e','Underdog':'#ffeaa7',
    'No Life':'#ff69b4','Grinder':'#fd79a8','Dedicated':'#fab1a0',
    'Dynasty':'#ffd700','Champion':'#f0c800','Tournament Winner':'#00b894',
    'Punching Bag':'#636e72','Participation Trophy':'#b2bec3','Iron Wall':'#00cec9',
}

ALL_RANKS = ['Undetermined','Here for the Laughs','Twig','Wood Plank','Wood','Bronze Initiate','Bronze',
             'Silver Elite Master','Gold Nova','Gold Nova Master',
             'Master Guardian','Master Guardian Elite','Distinguished Master Guardian',
             'Legendary Eagle','Legendary Eagle Master','Supreme','Global Elite']

COUNTRIES = [
    ('','No Country'),
    ('AF','🇦🇫 Afghanistan'),('AL','🇦🇱 Albania'),('DZ','🇩🇿 Algeria'),('AD','🇦🇩 Andorra'),('AO','🇦🇴 Angola'),
    ('AG','🇦🇬 Antigua and Barbuda'),('AR','🇦🇷 Argentina'),('AM','🇦🇲 Armenia'),('AU','🇦🇺 Australia'),('AT','🇦🇹 Austria'),
    ('AZ','🇦🇿 Azerbaijan'),('BS','🇧🇸 Bahamas'),('BH','🇧🇭 Bahrain'),('BD','🇧🇩 Bangladesh'),('BB','🇧🇧 Barbados'),
    ('BY','🇧🇾 Belarus'),('BE','🇧🇪 Belgium'),('BZ','🇧🇿 Belize'),('BJ','🇧🇯 Benin'),('BT','🇧🇹 Bhutan'),
    ('BO','🇧🇴 Bolivia'),('BA','🇧🇦 Bosnia and Herzegovina'),('BW','🇧🇼 Botswana'),('BR','🇧🇷 Brazil'),('BN','🇧🇳 Brunei'),
    ('BG','🇧🇬 Bulgaria'),('BF','🇧🇫 Burkina Faso'),('BI','🇧🇮 Burundi'),('CV','🇨🇻 Cabo Verde'),('KH','🇰🇭 Cambodia'),
    ('CM','🇨🇲 Cameroon'),('CA','🇨🇦 Canada'),('CF','🇨🇫 Central African Republic'),('TD','🇹🇩 Chad'),('CL','🇨🇱 Chile'),
    ('CN','🇨🇳 China'),('CO','🇨🇴 Colombia'),('KM','🇰🇲 Comoros'),('CG','🇨🇬 Congo'),('CD','🇨🇩 DR Congo'),
    ('CR','🇨🇷 Costa Rica'),('CI','🇨🇮 Ivory Coast'),('HR','🇭🇷 Croatia'),('CU','🇨🇺 Cuba'),('CY','🇨🇾 Cyprus'),
    ('CZ','🇨🇿 Czech Republic'),('DK','🇩🇰 Denmark'),('DJ','🇩🇯 Djibouti'),('DM','🇩🇲 Dominica'),('DO','🇩🇴 Dominican Republic'),
    ('EC','🇪🇨 Ecuador'),('EG','🇪🇬 Egypt'),('SV','🇸🇻 El Salvador'),('GQ','🇬🇶 Equatorial Guinea'),('ER','🇪🇷 Eritrea'),
    ('EE','🇪🇪 Estonia'),('SZ','🇸🇿 Eswatini'),('ET','🇪🇹 Ethiopia'),('FJ','🇫🇯 Fiji'),('FI','🇫🇮 Finland'),
    ('FR','🇫🇷 France'),('GA','🇬🇦 Gabon'),('GM','🇬🇲 Gambia'),('GE','🇬🇪 Georgia'),('DE','🇩🇪 Germany'),
    ('GH','🇬🇭 Ghana'),('GR','🇬🇷 Greece'),('GD','🇬🇩 Grenada'),('GT','🇬🇹 Guatemala'),('GN','🇬🇳 Guinea'),
    ('GW','🇬🇼 Guinea-Bissau'),('GY','🇬🇾 Guyana'),('HT','🇭🇹 Haiti'),('HN','🇭🇳 Honduras'),('HK','🇭🇰 Hong Kong'),
    ('HU','🇭🇺 Hungary'),('IS','🇮🇸 Iceland'),('IN','🇮🇳 India'),('ID','🇮🇩 Indonesia'),('IR','🇮🇷 Iran'),
    ('IQ','🇮🇶 Iraq'),('IE','🇮🇪 Ireland'),('IL','🇮🇱 Israel'),('IT','🇮🇹 Italy'),('JM','🇯🇲 Jamaica'),
    ('JP','🇯🇵 Japan'),('JO','🇯🇴 Jordan'),('KZ','🇰🇿 Kazakhstan'),('KE','🇰🇪 Kenya'),('KI','🇰🇮 Kiribati'),
    ('KP','🇰🇵 North Korea'),('KR','🇰🇷 South Korea'),('KW','🇰🇼 Kuwait'),('KG','🇰🇬 Kyrgyzstan'),('LA','🇱🇦 Laos'),
    ('LV','🇱🇻 Latvia'),('LB','🇱🇧 Lebanon'),('LS','🇱🇸 Lesotho'),('LR','🇱🇷 Liberia'),('LY','🇱🇾 Libya'),
    ('LI','🇱🇮 Liechtenstein'),('LT','🇱🇹 Lithuania'),('LU','🇱🇺 Luxembourg'),('MO','🇲🇴 Macau'),('MG','🇲🇬 Madagascar'),
    ('MW','🇲🇼 Malawi'),('MY','🇲🇾 Malaysia'),('MV','🇲🇻 Maldives'),('ML','🇲🇱 Mali'),('MT','🇲🇹 Malta'),
    ('MH','🇲🇭 Marshall Islands'),('MR','🇲🇷 Mauritania'),('MU','🇲🇺 Mauritius'),('MX','🇲🇽 Mexico'),('FM','🇫🇲 Micronesia'),
    ('MD','🇲🇩 Moldova'),('MC','🇲🇨 Monaco'),('MN','🇲🇳 Mongolia'),('ME','🇲🇪 Montenegro'),('MA','🇲🇦 Morocco'),
    ('MZ','🇲🇿 Mozambique'),('MM','🇲🇲 Myanmar'),('NA','🇳🇦 Namibia'),('NR','🇳🇷 Nauru'),('NP','🇳🇵 Nepal'),
    ('NL','🇳🇱 Netherlands'),('NZ','🇳🇿 New Zealand'),('NI','🇳🇮 Nicaragua'),('NE','🇳🇪 Niger'),('NG','🇳🇬 Nigeria'),
    ('MK','🇲🇰 North Macedonia'),('NO','🇳🇴 Norway'),('OM','🇴🇲 Oman'),('PK','🇵🇰 Pakistan'),('PW','🇵🇼 Palau'),
    ('PS','🇵🇸 Palestine'),('PA','🇵🇦 Panama'),('PG','🇵🇬 Papua New Guinea'),('PY','🇵🇾 Paraguay'),('PE','🇵🇪 Peru'),
    ('PH','🇵🇭 Philippines'),('PL','🇵🇱 Poland'),('PT','🇵🇹 Portugal'),('PR','🇵🇷 Puerto Rico'),('QA','🇶🇦 Qatar'),
    ('RO','🇷🇴 Romania'),('RU','🇷🇺 Russia'),('RW','🇷🇼 Rwanda'),('KN','🇰🇳 Saint Kitts and Nevis'),
    ('LC','🇱🇨 Saint Lucia'),('VC','🇻🇨 Saint Vincent'),('WS','🇼🇸 Samoa'),('SM','🇸🇲 San Marino'),
    ('ST','🇸🇹 Sao Tome and Principe'),('SA','🇸🇦 Saudi Arabia'),('SN','🇸🇳 Senegal'),('RS','🇷🇸 Serbia'),
    ('SC','🇸🇨 Seychelles'),('SL','🇸🇱 Sierra Leone'),('SG','🇸🇬 Singapore'),('SK','🇸🇰 Slovakia'),('SI','🇸🇮 Slovenia'),
    ('SB','🇸🇧 Solomon Islands'),('SO','🇸🇴 Somalia'),('ZA','🇿🇦 South Africa'),('SS','🇸🇸 South Sudan'),('ES','🇪🇸 Spain'),
    ('LK','🇱🇰 Sri Lanka'),('SD','🇸🇩 Sudan'),('SR','🇸🇷 Suriname'),('SE','🇸🇪 Sweden'),('CH','🇨🇭 Switzerland'),
    ('SY','🇸🇾 Syria'),('TW','🇹🇼 Taiwan'),('TJ','🇹🇯 Tajikistan'),('TZ','🇹🇿 Tanzania'),('TH','🇹🇭 Thailand'),
    ('TL','🇹🇱 Timor-Leste'),('TG','🇹🇬 Togo'),('TO','🇹🇴 Tonga'),('TT','🇹🇹 Trinidad and Tobago'),('TN','🇹🇳 Tunisia'),
    ('TR','🇹🇷 Turkey'),('TM','🇹🇲 Turkmenistan'),('TV','🇹🇻 Tuvalu'),('UG','🇺🇬 Uganda'),('UA','🇺🇦 Ukraine'),
    ('AE','🇦🇪 UAE'),('GB','🇬🇧 United Kingdom'),('US','🇺🇸 United States'),('UY','🇺🇾 Uruguay'),('UZ','🇺🇿 Uzbekistan'),
    ('VU','🇻🇺 Vanuatu'),('VA','🇻🇦 Vatican City'),('VE','🇻🇪 Venezuela'),('VN','🇻🇳 Vietnam'),('YE','🇾🇪 Yemen'),
    ('ZM','🇿🇲 Zambia'),('ZW','🇿🇼 Zimbabwe'),
]

COUNTRY_FLAGS = {code: label.split(' ')[0] for code, label in COUNTRIES if code}

# ===========================================================================
# SEED COSMETIC ITEMS
# ===========================================================================
SEED_COSMETIC_ITEMS = [
    # Animated Borders (3)
    {
        'name': 'Rotating Gradient Border',
        'category': 'profile_border',
        'description': 'A mesmerizing border that rotates through vibrant colors',
        'price': 500,
        'rarity': 'epic',
        'effect_type': 'rainbow',
        'css_data': '''border: 4px solid transparent; background: linear-gradient(#1a1a2e, #1a1a2e) padding-box, linear-gradient(var(--angle), #ff0080, #ff8c00, #40e0d0, #ff0080) border-box; animation: rotate-gradient 3s linear infinite; @keyframes rotate-gradient { from { --angle: 0deg; } to { --angle: 360deg; } }'''
    },
    {
        'name': 'Pulsing Glow Border',
        'category': 'profile_border',
        'description': 'A border that pulses with an ethereal glow',
        'price': 350,
        'rarity': 'rare',
        'effect_type': 'pulse',
        'css_data': '''border: 3px solid #00ffff; box-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff, 0 0 30px #00ffff; animation: pulse-glow 2s ease-in-out infinite; @keyframes pulse-glow { 0%, 100% { box-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff; } 50% { box-shadow: 0 0 20px #00ffff, 0 0 40px #00ffff, 0 0 60px #00ffff; } }'''
    },
    {
        'name': 'Rainbow Cycling Border',
        'category': 'profile_border',
        'description': 'A border that cycles through all rainbow colors',
        'price': 600,
        'rarity': 'legendary',
        'effect_type': 'rainbow',
        'css_data': '''border: 4px solid; animation: rainbow-cycle 5s linear infinite; @keyframes rainbow-cycle { 0% { border-color: #ff0000; } 17% { border-color: #ff8000; } 33% { border-color: #ffff00; } 50% { border-color: #00ff00; } 67% { border-color: #0080ff; } 83% { border-color: #8000ff; } 100% { border-color: #ff0000; } }'''
    },
    # Animated Backgrounds (3)
    {
        'name': 'Gradient Shift Background',
        'category': 'profile_background',
        'description': 'A background with smoothly shifting gradient colors',
        'price': 400,
        'rarity': 'rare',
        'effect_type': 'rainbow',
        'css_data': '''background: linear-gradient(-45deg, #ee7752, #e73c7e, #23a6d5, #23d5ab); background-size: 400% 400%; animation: gradient-shift 15s ease infinite; @keyframes gradient-shift { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }'''
    },
    {
        'name': 'Starfield Background',
        'category': 'profile_background',
        'description': 'A twinkling starfield effect for your profile',
        'price': 450,
        'rarity': 'epic',
        'effect_type': 'sparkle',
        'css_data': '''background: radial-gradient(ellipse at bottom, #1b2838 0%, #090a0f 100%); background-size: 100% 100%; animation: starfield-twinkle 3s ease-in-out infinite; @keyframes starfield-twinkle { 0%, 100% { opacity: 1; } 50% { opacity: 0.8; } }'''
    },
    {
        'name': 'Wave Background',
        'category': 'profile_background',
        'description': 'An animated wave pattern background',
        'price': 380,
        'rarity': 'rare',
        'effect_type': 'pulse',
        'css_data': '''background: linear-gradient(180deg, #0077b6 0%, #00b4d8 50%, #90e0ef 100%); animation: wave-motion 4s ease-in-out infinite; @keyframes wave-motion { 0%, 100% { background-position: 0% 0%; } 50% { background-position: 0% 10%; } }'''
    },
    # Badges (2)
    {
        'name': 'Champion Badge',
        'category': 'badge',
        'description': 'A golden trophy badge for champions',
        'price': 200,
        'rarity': 'uncommon',
        'effect_type': 'none',
        'css_data': '🏆'
    },
    {
        'name': 'Fire Badge',
        'category': 'badge',
        'description': 'Show everyone you are on fire',
        'price': 150,
        'rarity': 'common',
        'effect_type': 'none',
        'css_data': '🔥'
    },
    # Name Colors (2)
    {
        'name': 'Golden Name',
        'category': 'name_color',
        'description': 'Display your name in luxurious gold',
        'price': 300,
        'rarity': 'rare',
        'effect_type': 'none',
        'css_data': 'color: #ffd700;'
    },
    {
        'name': 'Neon Pink Name',
        'category': 'name_color',
        'description': 'A vibrant neon pink name color',
        'price': 250,
        'rarity': 'uncommon',
        'effect_type': 'none',
        'css_data': 'color: #ff1493;'
    },
    # Name Effects (2)
    {
        'name': 'Glowing Name',
        'category': 'name_effect',
        'description': 'Your name glows with an ethereal light',
        'price': 400,
        'rarity': 'epic',
        'effect_type': 'glow',
        'css_data': '''text-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff, 0 0 30px #00ffff; animation: name-glow 2s ease-in-out infinite; @keyframes name-glow { 0%, 100% { text-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff; } 50% { text-shadow: 0 0 20px #00ffff, 0 0 40px #00ffff, 0 0 60px #00ffff; } }'''
    },
    {
        'name': 'Pulsing Name',
        'category': 'name_effect',
        'description': 'Your name pulses with energy',
        'price': 350,
        'rarity': 'rare',
        'effect_type': 'pulse',
        'css_data': '''animation: name-pulse 1.5s ease-in-out infinite; @keyframes name-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }'''
    },
    # Chat Flairs (2)
    {
        'name': 'Star Flair',
        'category': 'chat_flair',
        'description': 'A sparkling star next to your name in chat',
        'price': 100,
        'rarity': 'common',
        'effect_type': 'none',
        'css_data': '⭐'
    },
    {
        'name': 'Crown Flair',
        'category': 'chat_flair',
        'description': 'A royal crown flair for chat',
        'price': 180,
        'rarity': 'uncommon',
        'effect_type': 'none',
        'css_data': '👑'
    },
    # Title (1)
    {
        'name': 'Legend Title',
        'category': 'title',
        'description': 'Display "Legend" below your username',
        'price': 500,
        'rarity': 'legendary',
        'effect_type': 'glow',
        'css_data': 'Legend'
    },
    # Avatar Frame (1)
    {
        'name': 'Golden Frame',
        'category': 'avatar_frame',
        'description': 'A luxurious golden frame around your avatar',
        'price': 350,
        'rarity': 'rare',
        'effect_type': 'none',
        'css_data': 'border: 3px solid #ffd700; box-shadow: 0 0 10px rgba(255, 215, 0, 0.5);'
    },
    # Profile Effect (1)
    {
        'name': 'Shadow Aura',
        'category': 'profile_effect',
        'description': 'A mysterious shadow aura surrounds your profile',
        'price': 400,
        'rarity': 'epic',
        'effect_type': 'shadow',
        'css_data': '''box-shadow: 0 0 30px rgba(0, 0, 0, 0.8), 0 0 60px rgba(75, 0, 130, 0.4); animation: shadow-pulse 3s ease-in-out infinite; @keyframes shadow-pulse { 0%, 100% { box-shadow: 0 0 30px rgba(0, 0, 0, 0.8), 0 0 60px rgba(75, 0, 130, 0.4); } 50% { box-shadow: 0 0 50px rgba(0, 0, 0, 0.9), 0 0 80px rgba(75, 0, 130, 0.6); } }'''
    },
    # Profile Banner (1)
    {
        'name': 'Sunset Banner',
        'category': 'profile_banner',
        'description': 'A beautiful sunset gradient banner',
        'price': 280,
        'rarity': 'uncommon',
        'effect_type': 'none',
        'css_data': 'background: linear-gradient(135deg, #ff6b6b 0%, #feca57 50%, #ff9ff3 100%);'
    },
    # --- Premium Animated Effects (8) ---
    # Particle (2)
    {
        'name': 'Stardust Aura',
        'category': 'profile_effect',
        'description': 'Tiny luminous particles orbit your profile like stardust',
        'price': 900,
        'rarity': 'legendary',
        'effect_type': 'particle',
        'css_data': '''box-shadow: 12px -8px 0 2px rgba(255,200,80,0.8), -10px 14px 0 2px rgba(80,200,255,0.8), 18px 10px 0 1px rgba(255,100,200,0.7), -15px -12px 0 1px rgba(100,255,180,0.7), 6px 18px 0 2px rgba(200,120,255,0.8); animation: stardust-orbit 4s ease-in-out infinite; @keyframes stardust-orbit { 0% { box-shadow: 12px -8px 0 2px rgba(255,200,80,0.8), -10px 14px 0 2px rgba(80,200,255,0.8), 18px 10px 0 1px rgba(255,100,200,0.7), -15px -12px 0 1px rgba(100,255,180,0.7), 6px 18px 0 2px rgba(200,120,255,0.8); } 50% { box-shadow: -8px 12px 0 2px rgba(255,200,80,0.8), 14px -10px 0 2px rgba(80,200,255,0.8), -10px -18px 0 1px rgba(255,100,200,0.7), 15px 12px 0 1px rgba(100,255,180,0.7), -6px -18px 0 2px rgba(200,120,255,0.8); } 100% { box-shadow: 12px -8px 0 2px rgba(255,200,80,0.8), -10px 14px 0 2px rgba(80,200,255,0.8), 18px 10px 0 1px rgba(255,100,200,0.7), -15px -12px 0 1px rgba(100,255,180,0.7), 6px 18px 0 2px rgba(200,120,255,0.8); } }'''
    },
    {
        'name': 'Ember Field',
        'category': 'profile_background',
        'description': 'Glowing ember particles drift across your profile background',
        'price': 800,
        'rarity': 'epic',
        'effect_type': 'particle',
        'css_data': '''background: radial-gradient(ellipse at center, #1a0a00 0%, #0d0d0d 100%); box-shadow: 5px -10px 0 1px rgba(255,120,30,0.7), -8px 6px 0 1px rgba(255,80,20,0.6), 14px 12px 0 2px rgba(255,160,50,0.8), -12px -8px 0 1px rgba(255,100,40,0.6), 3px 16px 0 2px rgba(255,140,60,0.7); animation: ember-drift 5s ease-in-out infinite; @keyframes ember-drift { 0% { box-shadow: 5px -10px 0 1px rgba(255,120,30,0.7), -8px 6px 0 1px rgba(255,80,20,0.6), 14px 12px 0 2px rgba(255,160,50,0.8), -12px -8px 0 1px rgba(255,100,40,0.6), 3px 16px 0 2px rgba(255,140,60,0.7); } 50% { box-shadow: -5px -16px 0 1px rgba(255,120,30,0.7), 8px -6px 0 1px rgba(255,80,20,0.6), -14px 6px 0 2px rgba(255,160,50,0.8), 12px -14px 0 1px rgba(255,100,40,0.6), -3px 10px 0 2px rgba(255,140,60,0.7); } 100% { box-shadow: 5px -10px 0 1px rgba(255,120,30,0.7), -8px 6px 0 1px rgba(255,80,20,0.6), 14px 12px 0 2px rgba(255,160,50,0.8), -12px -8px 0 1px rgba(255,100,40,0.6), 3px 16px 0 2px rgba(255,140,60,0.7); } }'''
    },
    # Holographic (2)
    {
        'name': 'Prismatic Border',
        'category': 'profile_border',
        'description': 'A holographic rainbow shimmer dances along your profile border',
        'price': 1000,
        'rarity': 'legendary',
        'effect_type': 'holographic',
        'css_data': '''border: 3px solid transparent; background: linear-gradient(#1a1a2e, #1a1a2e) padding-box, linear-gradient(90deg, #ff0000, #ff8800, #ffff00, #00ff00, #0088ff, #8800ff, #ff0000) border-box; background-size: 100% 100%, 300% 100%; animation: prismatic-shift 3s linear infinite; @keyframes prismatic-shift { 0% { background-position: 0 0, 0% 0; } 100% { background-position: 0 0, 300% 0; } }'''
    },
    {
        'name': 'Holographic Tag',
        'category': 'name_effect',
        'description': 'Your name shimmers with a holographic rainbow sheen',
        'price': 750,
        'rarity': 'epic',
        'effect_type': 'holographic',
        'css_data': '''background: linear-gradient(90deg, #ff0000, #ff8800, #ffff00, #00ff88, #0088ff, #8800ff, #ff0000); background-size: 300% 100%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: holo-name-shift 4s linear infinite; @keyframes holo-name-shift { 0% { background-position: 0% 50%; } 100% { background-position: 300% 50%; } }'''
    },
    # Glitch (2)
    {
        'name': 'Corrupted Name',
        'category': 'name_effect',
        'description': 'Your name flickers with digital glitch distortion',
        'price': 700,
        'rarity': 'epic',
        'effect_type': 'glitch',
        'css_data': '''animation: glitch-text 2s steps(20, end) infinite; @keyframes glitch-text { 0% { text-shadow: 2px 0 #ff0040, -2px 0 #00ffff; } 20% { text-shadow: -2px 1px #ff0040, 2px -1px #00ffff; } 40% { text-shadow: 2px -1px #ff0040, -2px 1px #00ffff; } 60% { text-shadow: -1px 2px #ff0040, 1px -2px #00ffff; } 80% { text-shadow: 1px -2px #ff0040, -1px 2px #00ffff; } 100% { text-shadow: 2px 0 #ff0040, -2px 0 #00ffff; } }'''
    },
    {
        'name': 'Glitch Frame',
        'category': 'avatar_frame',
        'description': 'Your avatar frame crackles with digital interference',
        'price': 650,
        'rarity': 'epic',
        'effect_type': 'glitch',
        'css_data': '''border: 3px solid #00ffff; animation: glitch-frame 3s steps(10, end) infinite; @keyframes glitch-frame { 0%, 100% { box-shadow: 2px 0 #ff0040, -2px 0 #00ffff; border-color: #00ffff; } 25% { box-shadow: -3px 1px #ff0040, 3px -1px #00ffff; border-color: #ff0040; } 50% { box-shadow: 2px -2px #ff0040, -2px 2px #00ffff; border-color: #00ffff; } 75% { box-shadow: -2px 2px #ff0040, 2px -2px #00ffff; border-color: #ff0040; } }'''
    },
    # Animated Gradient (2)
    {
        'name': 'Aurora Background',
        'category': 'profile_background',
        'description': 'A flowing aurora of shifting colors fills your profile background',
        'price': 850,
        'rarity': 'legendary',
        'effect_type': 'animated_gradient',
        'css_data': '''background: linear-gradient(-45deg, #0f3443, #34e89e, #43cea2, #185a9d, #6441a5, #0f3443); background-size: 600% 600%; animation: aurora-flow 12s ease infinite; @keyframes aurora-flow { 0% { background-position: 0% 50%; } 25% { background-position: 50% 0%; } 50% { background-position: 100% 50%; } 75% { background-position: 50% 100%; } 100% { background-position: 0% 50%; } }'''
    },
    {
        'name': 'Neon Tide Banner',
        'category': 'profile_banner',
        'description': 'A neon gradient tide sweeps across your profile banner',
        'price': 750,
        'rarity': 'epic',
        'effect_type': 'animated_gradient',
        'css_data': '''background: linear-gradient(90deg, #fc466b, #3f5efb, #00f2fe, #fc466b); background-size: 400% 100%; animation: neon-tide 8s ease infinite; @keyframes neon-tide { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }'''
    },
    # --- SVG Filter Items (2) ---
    {
        'name': 'Turbulence Warp Border',
        'category': 'profile_border',
        'description': 'An SVG turbulence distortion that warps your profile border',
        'price': 700,
        'rarity': 'epic',
        'effect_type': 'glitch',
        'effect_mode': 'svg_filter',
        'css_data': '<filter><feTurbulence type="turbulence" baseFrequency="0.03" numOctaves="3" result="turb"/><feDisplacementMap in="SourceGraphic" in2="turb" scale="8"/></filter>'
    },
    {
        'name': 'Color Matrix Shift',
        'category': 'profile_background',
        'description': 'An SVG color matrix filter that shifts hues on your background',
        'price': 650,
        'rarity': 'epic',
        'effect_type': 'glitch',
        'effect_mode': 'svg_filter',
        'css_data': '<filter><feColorMatrix type="matrix" values="0.8 0.2 0 0 0  0 0.7 0.3 0 0  0.1 0 0.9 0 0  0 0 0 1 0"/></filter>'
    },
    # --- Canvas Effect Items (3) ---
    {
        'name': 'Inferno Aura',
        'category': 'profile_effect',
        'description': 'Animated flames rise from the bottom of your profile',
        'price': 950,
        'rarity': 'legendary',
        'effect_type': 'particle',
        'effect_mode': 'canvas',
        'css_data': 'fire_aura'
    },
    {
        'name': 'Digital Rain',
        'category': 'profile_background',
        'description': 'Cascading green characters fall like digital rain',
        'price': 850,
        'rarity': 'legendary',
        'effect_type': 'particle',
        'effect_mode': 'canvas',
        'css_data': 'matrix_rain'
    },
    {
        'name': 'Winter Sparkle',
        'category': 'profile_effect',
        'description': 'Gentle snowflakes and sparkles drift across your profile',
        'price': 750,
        'rarity': 'epic',
        'effect_type': 'particle',
        'effect_mode': 'canvas',
        'css_data': 'snowfall_sparkle'
    },
]

# ===========================================================================
# COSMETIC ITEM GENERATOR
# ===========================================================================
_GENERATOR_TEMPLATES = {
    'profile_border': {
        'gradient_border': {
            'name_prefix': 'Gradient Border',
            'description': 'A stylish gradient border',
            'effect_type': 'rainbow',
            'css_template': '''border: {width}px solid transparent; background: linear-gradient(#1a1a2e, #1a1a2e) padding-box, linear-gradient({angle}deg, {color1}, {color2}) border-box;'''
        },
        'glow_border': {
            'name_prefix': 'Glow Border',
            'description': 'A glowing border effect',
            'effect_type': 'glow',
            'css_template': '''border: {width}px solid {color1}; box-shadow: 0 0 {glow}px {color1}, 0 0 {glow2}px {color1};'''
        },
        'solid_animated_border': {
            'name_prefix': 'Animated Border',
            'description': 'An animated solid border',
            'effect_type': 'pulse',
            'css_template': '''border: {width}px solid {color1}; animation: border-pulse-{uid} {duration}s ease-in-out infinite; @keyframes border-pulse-{uid} {{ 0%, 100% {{ border-color: {color1}; }} 50% {{ border-color: {color2}; }} }}'''
        },
        'holographic_border': {
            'name_prefix': 'Holo Border',
            'description': 'A holographic shimmer border',
            'effect_type': 'holographic',
            'css_template': '''border: {width}px solid transparent; background: linear-gradient(#1a1a2e, #1a1a2e) padding-box, linear-gradient(90deg, #ff0000, #ff8800, #ffff00, #00ff00, #0088ff, #8800ff, #ff0000) border-box; background-size: 100% 100%, 300% 100%; animation: holo-border-{uid} {duration}s linear infinite; @keyframes holo-border-{uid} {{ 0% {{ background-position: 0 0, 0% 0; }} 100% {{ background-position: 0 0, 300% 0; }} }}'''
        },
        'svg_turbulence_border': {
            'name_prefix': 'Turbulence Border',
            'description': 'An SVG turbulence distortion border effect',
            'effect_type': 'glitch',
            'effect_mode': 'svg_filter',
            'css_template': '<filter><feTurbulence type="turbulence" baseFrequency="0.0{freq}" numOctaves="{octaves}" /><feDisplacementMap in="SourceGraphic" scale="{scale}" /></filter>'
        },
    },
    'profile_banner': {
        'gradient_banner': {
            'name_prefix': 'Gradient Banner',
            'description': 'A colorful gradient banner',
            'effect_type': 'none',
            'css_template': '''background: linear-gradient({angle}deg, {color1} 0%, {color2} 100%);'''
        },
        'animated_gradient': {
            'name_prefix': 'Animated Banner',
            'description': 'An animated gradient banner',
            'effect_type': 'rainbow',
            'css_template': '''background: linear-gradient({angle}deg, {color1}, {color2}, {color3}); background-size: 200% 200%; animation: banner-shift-{uid} {duration}s ease infinite; @keyframes banner-shift-{uid} {{ 0% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} 100% {{ background-position: 0% 50%; }} }}'''
        },
    },
    'profile_background': {
        'gradient_background': {
            'name_prefix': 'Gradient BG',
            'description': 'A smooth gradient background',
            'effect_type': 'none',
            'css_template': '''background: linear-gradient({angle}deg, {color1} 0%, {color2} 100%);'''
        },
        'pattern': {
            'name_prefix': 'Pattern BG',
            'description': 'A patterned background',
            'effect_type': 'none',
            'css_template': '''background: repeating-linear-gradient({angle}deg, {color1}, {color1} 10px, {color2} 10px, {color2} 20px);'''
        },
        'animated_gradient': {
            'name_prefix': 'Animated Gradient BG',
            'description': 'An animated multi-color gradient background',
            'effect_type': 'animated_gradient',
            'css_template': '''background: linear-gradient(-45deg, {color1}, {color2}, {color3}); background-size: 400% 400%; animation: anim-grad-bg-{uid} {duration}s ease infinite; @keyframes anim-grad-bg-{uid} {{ 0% {{ background-position: 0% 50%; }} 50% {{ background-position: 100% 50%; }} 100% {{ background-position: 0% 50%; }} }}'''
        },
        'svg_color_matrix_bg': {
            'name_prefix': 'Color Matrix BG',
            'description': 'An SVG color matrix shift background effect',
            'effect_type': 'glitch',
            'effect_mode': 'svg_filter',
            'css_template': '<filter><feColorMatrix type="hueRotate" values="{angle}" /></filter>'
        },
        'fire_aura_canvas': {
            'name_prefix': 'Fire Aura',
            'description': 'Animated fire particles rising from the bottom',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'fire_aura'
        },
        'matrix_rain_canvas': {
            'name_prefix': 'Matrix Rain',
            'description': 'Falling digital character columns',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'matrix_rain'
        },
        'snowfall_canvas': {
            'name_prefix': 'Snowfall Sparkle',
            'description': 'Falling snowflakes and sparkle particles',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'snowfall_sparkle'
        },
    },
    'badge': {
        'emoji_badge': {
            'name_prefix': 'Emoji Badge',
            'description': 'A fun emoji badge',
            'effect_type': 'none',
            'css_template': '{emoji}'
        },
        'icon_badge': {
            'name_prefix': 'Icon Badge',
            'description': 'A stylish icon badge',
            'effect_type': 'none',
            'css_template': '{emoji}'
        },
    },
    'name_color': {
        'solid_color': {
            'name_prefix': 'Solid Name',
            'description': 'A solid color for your name',
            'effect_type': 'none',
            'css_template': '''color: {color1};'''
        },
        'gradient_text': {
            'name_prefix': 'Gradient Name',
            'description': 'A gradient text effect for your name',
            'effect_type': 'rainbow',
            'css_template': '''background: linear-gradient({angle}deg, {color1}, {color2}); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;'''
        },
    },
    'name_effect': {
        'glow_text': {
            'name_prefix': 'Glow Name',
            'description': 'A glowing name effect',
            'effect_type': 'glow',
            'css_template': '''text-shadow: 0 0 {glow}px {color1}, 0 0 {glow2}px {color1};'''
        },
        'pulse_text': {
            'name_prefix': 'Pulse Name',
            'description': 'A pulsing name effect',
            'effect_type': 'pulse',
            'css_template': '''animation: name-pulse-{uid} {duration}s ease-in-out infinite; @keyframes name-pulse-{uid} {{ 0%, 100% {{ transform: scale(1); opacity: 1; }} 50% {{ transform: scale(1.05); opacity: 0.9; }} }}'''
        },
        'glitch_text': {
            'name_prefix': 'Glitch Name',
            'description': 'A glitch distortion name effect',
            'effect_type': 'glitch',
            'css_template': '''animation: glitch-name-{uid} 2s steps(20, end) infinite; @keyframes glitch-name-{uid} {{ 0%, 100% {{ text-shadow: 2px 0 {color1}, -2px 0 {color2}; }} 25% {{ text-shadow: -2px 1px {color1}, 2px -1px {color2}; }} 50% {{ text-shadow: 2px -1px {color1}, -2px 1px {color2}; }} 75% {{ text-shadow: -1px 2px {color1}, 1px -2px {color2}; }} }}'''
        },
        'holographic_text': {
            'name_prefix': 'Holo Name',
            'description': 'A holographic shimmer name effect',
            'effect_type': 'holographic',
            'css_template': '''background: linear-gradient(90deg, {color1}, {color2}, {color3}, {color1}); background-size: 300% 100%; -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; animation: holo-text-{uid} {duration}s linear infinite; @keyframes holo-text-{uid} {{ 0% {{ background-position: 0% 50%; }} 100% {{ background-position: 300% 50%; }} }}'''
        },
    },
    'chat_flair': {
        'emoji_flair': {
            'name_prefix': 'Chat Flair',
            'description': 'A chat flair emoji',
            'effect_type': 'none',
            'css_template': '{emoji}'
        },
    },
    'profile_effect': {
        'glow_effect': {
            'name_prefix': 'Glow Effect',
            'description': 'A glowing profile effect',
            'effect_type': 'glow',
            'css_template': '''box-shadow: 0 0 {glow}px {color1}, 0 0 {glow2}px {color1};'''
        },
        'shadow_effect': {
            'name_prefix': 'Shadow Effect',
            'description': 'A shadow profile effect',
            'effect_type': 'shadow',
            'css_template': '''box-shadow: 0 {offset}px {blur}px rgba(0, 0, 0, 0.{opacity});'''
        },
        'particle_effect': {
            'name_prefix': 'Particle Effect',
            'description': 'A particle animation effect',
            'effect_type': 'particle',
            'css_template': '''box-shadow: {glow}px -{glow2}px 0 2px {color1}88, -{glow}px {glow2}px 0 2px {color2}88; animation: particle-{uid} {duration}s ease-in-out infinite; @keyframes particle-{uid} {{ 0%, 100% {{ box-shadow: {glow}px -{glow2}px 0 2px {color1}88, -{glow}px {glow2}px 0 2px {color2}88; }} 50% {{ box-shadow: -{glow}px {glow2}px 0 2px {color1}88, {glow}px -{glow2}px 0 2px {color2}88; }} }}'''
        },
        'svg_displacement_effect': {
            'name_prefix': 'Displacement Effect',
            'description': 'An SVG displacement distortion effect',
            'effect_type': 'glitch',
            'effect_mode': 'svg_filter',
            'css_template': '<filter><feTurbulence type="fractalNoise" baseFrequency="0.0{freq}" numOctaves="{octaves}" /><feDisplacementMap in="SourceGraphic" scale="{scale}" /></filter>'
        },
        'electric_border_canvas': {
            'name_prefix': 'Electric Border',
            'description': 'Animated electric arcs along the border',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'electric_border'
        },
        'sunburst_rays_canvas': {
            'name_prefix': 'Sunburst Rays',
            'description': 'Rotating ray patterns from center',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'sunburst_rays'
        },
        'lightning_canvas': {
            'name_prefix': 'Lightning',
            'description': 'Branching lightning bolt lines',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'lightning'
        },
        'plasma_field_canvas': {
            'name_prefix': 'Plasma Field',
            'description': 'Color-shifting plasma blobs',
            'effect_type': 'particle',
            'effect_mode': 'canvas',
            'css_template': 'plasma_field'
        },
    },
    'avatar_frame': {
        'glow_frame': {
            'name_prefix': 'Glow Frame',
            'description': 'A glowing avatar frame',
            'effect_type': 'glow',
            'css_template': '''border: {width}px solid {color1}; box-shadow: 0 0 {glow}px {color1};'''
        },
        'gradient_frame': {
            'name_prefix': 'Gradient Frame',
            'description': 'A gradient avatar frame',
            'effect_type': 'none',
            'css_template': '''border: {width}px solid transparent; background: linear-gradient(#1a1a2e, #1a1a2e) padding-box, linear-gradient({angle}deg, {color1}, {color2}) border-box; border-radius: 50%;'''
        },
        'glitch_frame': {
            'name_prefix': 'Glitch Frame',
            'description': 'A glitch distortion avatar frame',
            'effect_type': 'glitch',
            'css_template': '''border: {width}px solid {color1}; animation: glitch-frame-{uid} 3s steps(10, end) infinite; @keyframes glitch-frame-{uid} {{ 0%, 100% {{ box-shadow: 2px 0 {color1}, -2px 0 {color2}; border-color: {color1}; }} 50% {{ box-shadow: -2px 2px {color1}, 2px -2px {color2}; border-color: {color2}; }} }}'''
        },
    },
    'title': {
        'text_badge': {
            'name_prefix': 'Title',
            'description': 'A custom title badge',
            'effect_type': 'none',
            'css_template': '{title_text}'
        },
    },
}

_RANDOM_COLORS = [
    '#ff0080', '#ff8c00', '#40e0d0', '#00ffff', '#ff1493', '#ffd700',
    '#00ff00', '#ff4500', '#9400d3', '#00bfff', '#ff69b4', '#32cd32',
    '#ff6347', '#4169e1', '#dc143c', '#00ced1', '#ff00ff', '#7fff00',
    '#e6e6fa', '#ffa07a', '#20b2aa', '#87ceeb', '#778899', '#b0c4de',
]

_RANDOM_EMOJIS = ['⭐', '🌟', '✨', '💫', '🔥', '💎', '👑', '🎯', '🏆', '⚡', '💥', '🌈', '🎮', '🎲', '🃏', '♠️', '♥️', '♦️', '♣️', '🍀']

_RANDOM_TITLES = ['Champion', 'Elite', 'Master', 'Pro', 'Ace', 'Hero', 'Warrior', 'Legend', 'Star', 'King', 'Queen', 'Boss', 'Chief', 'Captain', 'Guru']


def generate_cosmetic_item(category, template_name):
    """
    Generate a cosmetic item dict with auto-generated name, description, css_data, rarity, price, effect_type.
    
    Args:
        category: One of COSMETIC_CATEGORIES
        template_name: Template name for the category (e.g., 'gradient_border', 'glow_border')
    
    Returns:
        dict with keys: name, category, description, price, rarity, effect_type, css_data
        Returns None if category or template_name is invalid.
    """
    if category not in _GENERATOR_TEMPLATES:
        return None
    
    templates = _GENERATOR_TEMPLATES[category]
    if template_name not in templates:
        return None
    
    template = templates[template_name]
    uid = uuid.uuid4().hex[:8]
    
    # Randomize CSS parameters
    color1 = random.choice(_RANDOM_COLORS)
    color2 = random.choice(_RANDOM_COLORS)
    color3 = random.choice(_RANDOM_COLORS)
    angle = random.randint(0, 360)
    width = random.randint(2, 5)
    glow = random.randint(5, 15)
    glow2 = random.randint(20, 40)
    duration = round(random.uniform(1.5, 4.0), 1)
    offset = random.randint(5, 15)
    blur = random.randint(10, 30)
    opacity = random.randint(3, 7)
    emoji = random.choice(_RANDOM_EMOJIS)
    title_text = random.choice(_RANDOM_TITLES)
    
    # SVG filter parameters
    freq = random.randint(1, 9)
    octaves = random.randint(1, 4)
    scale = random.randint(5, 20)
    
    # Determine effect_mode from template (default to 'css')
    effect_mode = template.get('effect_mode', 'css')
    
    # Generate CSS data from template
    css_data = template['css_template'].format(
        color1=color1, color2=color2, color3=color3,
        angle=angle, width=width, glow=glow, glow2=glow2,
        duration=duration, uid=uid, offset=offset, blur=blur,
        opacity=opacity, emoji=emoji, title_text=title_text,
        freq=freq, octaves=octaves, scale=scale
    )
    
    # Randomize rarity with weighted distribution
    rarity_weights = [
        ('common', 35),
        ('uncommon', 30),
        ('rare', 20),
        ('epic', 10),
        ('legendary', 5),
    ]
    rarity = random.choices(
        [r[0] for r in rarity_weights],
        weights=[r[1] for r in rarity_weights]
    )[0]
    
    # Calculate price based on rarity
    base_prices = {
        'common': (50, 150),
        'uncommon': (150, 300),
        'rare': (300, 500),
        'epic': (500, 800),
        'legendary': (800, 1200),
    }
    price_range = base_prices[rarity]
    price = random.randint(price_range[0], price_range[1])
    
    # Generate unique name
    name = f"{template['name_prefix']} #{uid[:4].upper()}"
    
    return {
        'name': name,
        'category': category,
        'description': template['description'],
        'price': price,
        'rarity': rarity,
        'effect_type': template['effect_type'],
        'effect_mode': effect_mode,
        'css_data': css_data,
    }


# ===========================================================================
# SHOWCASE HELPERS
# ===========================================================================
def serialize_showcase(metric_keys):
    """Serialize a list of metric keys to JSON string."""
    return json.dumps(metric_keys)

def deserialize_showcase(json_str):
    """Deserialize showcase config. Returns DEFAULT_SHOWCASE on invalid input."""
    if not json_str:
        return list(DEFAULT_SHOWCASE)
    try:
        data = json.loads(json_str)
        if not isinstance(data, list):
            return list(DEFAULT_SHOWCASE)
        return [k for k in data if k in SHOWCASE_METRICS]
    except (json.JSONDecodeError, TypeError):
        log.warning(f"Invalid showcase_config JSON: {json_str!r}")
        return list(DEFAULT_SHOWCASE)

def _resolve_metric_value(user, key, set_stats):
    """Return display string for a metric key, or None if unresolvable."""
    if key == 'elo': return str(user.elo)
    if key == 'win_rate': return f"{user.ranked_wr}%"
    if key == 'current_streak': return f"{user.streak} 🔥"
    if key == 'best_streak': return f"{user.best_streak} 🔥"
    if key == 'pongcoins': return f"{user.points} 🪙"
    if key == 'total_ranked': return str(user.total_ranked)
    if key == 'total_unranked': return str(user.total_unranked)
    if key == 'rank_title': return user.rank_title
    if key == 'sets_won':
        return str(set_stats['sets_won']) if set_stats else None
    if key == 'sets_lost':
        return str(set_stats['sets_lost']) if set_stats else None
    if key == 'avg_pts_per_set':
        return str(set_stats['avg_pts']) if set_stats else None
    if key == 'points_scored':
        return str(set_stats['pts_scored']) if set_stats else None
    return None

def resolve_showcase_metrics(user, metric_keys, set_stats=None):
    """Resolve metric keys to list of {key, label, icon, value} dicts."""
    results = []
    for key in metric_keys:
        meta = SHOWCASE_METRICS.get(key)
        if not meta:
            continue
        value = _resolve_metric_value(user, key, set_stats)
        if value is None:
            continue
        results.append({
            'key': key,
            'label': meta['label'],
            'icon': meta['icon'],
            'value': value,
        })
    return results


# ===========================================================================
# RATE LIMITER
# ===========================================================================
class _RateLimiter:
    def __init__(self):
        self._store = {}
        self._last_prune = time.time()
    def check(self, key, limit, window):
        now = time.time()
        if now - self._last_prune > 60:
            self._prune(now, window)
        hits = self._store.get(key, [])
        hits = [t for t in hits if now - t < window]
        if len(hits) >= limit:
            return False, int(window - (now - hits[0]))
        hits.append(now)
        self._store[key] = hits
        return True, 0
    def _prune(self, now, default_window=60):
        self._last_prune = now
        for k in list(self._store):
            self._store[k] = [t for t in self._store[k] if now - t < default_window * 2]
            if not self._store[k]:
                del self._store[k]

_limiter = _RateLimiter()

def rate_limit(limit, window, key_func):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            key = key_func()
            allowed, retry_after = _limiter.check(key, limit, window)
            if not allowed:
                return jsonify(error="Rate limit exceeded", retry_after=retry_after), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ===========================================================================
# ADMIN DECORATOR
# ===========================================================================
def _admin(f):
    @functools.wraps(f)
    @login_required
    def w(*a,**k):
        if not current_user.admin: abort(403)
        return f(*a,**k)
    return w

# ===========================================================================
# DB HELPERS
# ===========================================================================
def _ok():
    try: db.session.commit(); return True
    except Exception as e: db.session.rollback(); log.error(f"DB: {e}"); return False

def _alert(uid,title,msg,c='info',l=None):
    from models import Alert
    db.session.add(Alert(user_id=uid,title=title,message=msg,cat=c,link=l))

def _activity(atype, user_id, detail, icon='circle', color='info', link=None, target_id=None):
    from models import Activity
    db.session.add(Activity(type=atype, user_id=user_id, detail=detail, icon=icon, color=color, link=link, target_id=target_id))


def _escape_like(s):
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

def _user_has_clan(user_id):
    from models import clan_members
    return db.session.execute(
        clan_members.select().where(clan_members.c.user_id==user_id)
    ).first() is not None

def _award_points(user_id, amount, reason):
    from models import User, PointTransaction
    u = db.session.get(User, user_id)
    if not u: return False
    if amount < 0 and u.points + amount < 0:
        return False
    u.points += amount
    db.session.add(PointTransaction(user_id=user_id, amount=amount, reason=reason))
    return True

# ===========================================================================
# FILE UPLOAD HELPERS
# ===========================================================================
def _alw(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in app.config['ALLOWED_EXT']

def _validate_magic(stream):
    pos = stream.tell()
    header = stream.read(12)
    stream.seek(pos)
    if len(header) < 4: return False
    if header[:8] == b'\x89PNG\r\n\x1a\n': return True
    if header[:2] == b'\xff\xd8': return True
    if header[:4] in (b'GIF8',): return True
    if header[:4] == b'RIFF' and len(header) >= 12 and header[8:12] == b'WEBP': return True
    return False

def _simg(fs,sub='misc',mx=None,crop=None):
    if not fs or not fs.filename: return None
    fn=secure_filename(fs.filename)
    if not fn or not _alw(fn): return None
    ext=fn.rsplit('.',1)[1].lower()
    if ext=='jpeg': ext='jpg'
    out=f"{uuid.uuid4().hex}.{ext}"
    dest=os.path.join(app.config['UPLOAD_FOLDER'],sub,out)
    os.makedirs(os.path.dirname(dest),exist_ok=True)
    if PILImage:
        try:
            fs.stream.seek(0); img=PILImage.open(fs.stream)
            img=img.convert('RGBA') if img.mode=='RGBA' else img.convert('RGB')
            if crop:
                try:
                    cx,cy=float(crop.get('x',0)),float(crop.get('y',0))
                    cw,ch=float(crop.get('width',0)),float(crop.get('height',0))
                    if cw>0 and ch>0:
                        l,top_=max(int(cx),0),max(int(cy),0)
                        r,b=min(int(cx+cw),img.width),min(int(cy+ch),img.height)
                        if r>l and b>top_: img=img.crop((l,top_,r,b))
                except (ValueError, TypeError): pass
            if mx: img.thumbnail((mx,mx),PILImage.LANCZOS)
            sf='PNG' if ext=='png' else 'JPEG'
            if img.mode=='RGBA' and sf=='JPEG':
                bg=PILImage.new('RGB',img.size,(255,255,255)); bg.paste(img,mask=img.split()[3]); img=bg
            img.save(dest,sf,quality=90)
        except Exception:
            fs.stream.seek(0)
            if not _validate_magic(fs.stream): return None
            fs.stream.seek(0); fs.save(dest)
    else:
        fs.stream.seek(0)
        if not _validate_magic(fs.stream): return None
        fs.stream.seek(0); fs.save(dest)
    return f"{sub}/{out}"


# ===========================================================================
# ELO & MATCH PROCESSING
# ===========================================================================
def _elo(w,l,draw=False,k=32):
    ew=1.0/(1.0+10**((l-w)/400.0)); el=1.0-ew
    if draw: return round(k*(0.5-ew)),round(k*(0.5-el))
    return round(k*(1.0-ew)),round(k*(0.0-el))

def _check_rank_change(user, old_rank):
    new_rank=user.rank_title
    if new_rank==old_rank or new_rank=='Undetermined': return
    old_idx=ALL_RANKS.index(old_rank) if old_rank in ALL_RANKS else -1
    new_idx=ALL_RANKS.index(new_rank) if new_rank in ALL_RANKS else -1
    if new_idx>old_idx:
        _alert(user.id, f'🎉 Rank Up! {new_rank}', f'You ranked up from {old_rank} to {new_rank}! (ELO: {user.elo})', 'success')
        _activity('rank_up', user.id, f'Ranked up to {new_rank}!', 'arrow-up', 'success')
    elif new_idx<old_idx and old_idx>=0:
        _alert(user.id, f'📉 Rank Down: {new_rank}', f'You dropped from {old_rank} to {new_rank}. (ELO: {user.elo})', 'warning')
        _activity('rank_down', user.id, f'Dropped to {new_rank}', 'arrow-down', 'warn')

def _head_to_head(uid1, uid2):
    from models import Match
    matches=Match.query.filter(
        Match.state=='verified',
        or_(and_(Match.p1_id==uid1, Match.p2_id==uid2),
            and_(Match.p1_id==uid2, Match.p2_id==uid1))
    ).order_by(Match.played_at.desc()).all()
    if not matches: return None
    w1=0; w2=0; draws=0; elo_exchanged=0
    for m in matches:
        if m.draw: draws+=1
        elif m.winner_id==uid1: w1+=1
        elif m.winner_id==uid2: w2+=1
        if m.p1_id==uid1: elo_exchanged+=m.elo_d1
        else: elo_exchanged+=m.elo_d2
    return {'matches':matches,'total':len(matches),'w1':w1,'w2':w2,'draws':draws,
            'elo_exchanged':elo_exchanged,
            'ranked':len([m for m in matches if m.ranked]),
            'unranked':len([m for m in matches if not m.ranked]),
            'last_match':matches[0] if matches else None}


def _proc_r(m):
    from models import User, EloSnap, Match, Clan, ClanWarMatch, clan_members
    if not m.ranked or m.state!='verified': return
    p1=db.session.get(User,m.p1_id); p2=db.session.get(User,m.p2_id)
    if not p1 or not p2: return
    p1_old_rank=p1.rank_title; p2_old_rank=p2.rank_title
    p1_old_elo=p1.elo; p2_old_elo=p2.elo
    if m.draw:
        c1,c2=_elo(p1.elo,p2.elo,True); p1.elo+=c1; p2.elo+=c2
        p1.r_draws+=1; p2.r_draws+=1; p1.streak=0; p2.streak=0; m.elo_d1=c1; m.elo_d2=c2
    elif m.winner_id==p1.id:
        c1,c2=_elo(p1.elo,p2.elo); p1.elo+=c1; p2.elo+=c2
        p1.r_wins+=1; p2.r_losses+=1; p1.streak+=1; p1.best_streak=max(p1.best_streak,p1.streak); p2.streak=0
        m.elo_d1=c1; m.elo_d2=c2
    elif m.winner_id==p2.id:
        c1,c2=_elo(p2.elo,p1.elo); p2.elo+=c1; p1.elo+=c2
        p2.r_wins+=1; p1.r_losses+=1; p2.streak+=1; p2.best_streak=max(p2.best_streak,p2.streak); p1.streak=0
        m.elo_d1=c2; m.elo_d2=c1
    p1.elo_matches+=1; p2.elo_matches+=1
    match_time = m.played_at or datetime.now(timezone.utc)
    for p in [p1,p2]:
        ch_=m.elo_d1 if p.id==m.p1_id else m.elo_d2
        if ch_ > 0:
            memberships = db.session.execute(
                clan_members.select().where(clan_members.c.user_id==p.id)).fetchall()
            for mem in memberships:
                if mem.joined_at and mem.joined_at <= match_time:
                    clan = db.session.get(Clan, mem.clan_id)
                    if clan: clan.score += ch_
    checked_clans = set()
    for p in [p1, p2]:
        memberships = db.session.execute(
            clan_members.select().where(clan_members.c.user_id==p.id)).fetchall()
        for mem in memberships:
            if mem.clan_id not in checked_clans:
                checked_clans.add(mem.clan_id)
                clan = db.session.get(Clan, mem.clan_id)
                if clan: _check_clan_achievements(clan)
    db.session.add(EloSnap(user_id=p1.id,elo_val=p1.elo,match_id=m.id))
    db.session.add(EloSnap(user_id=p2.id,elo_val=p2.elo,match_id=m.id))
    log.info(f"[ELO] Match #{m.id}: {p1.name()} {p1_old_elo}->{p1.elo} ({m.elo_d1:+d}), {p2.name()} {p2_old_elo}->{p2.elo} ({m.elo_d2:+d})")
    _rival_count = Match.query.filter(
        Match.state == 'verified', Match.ranked == True,
        or_(and_(Match.p1_id == p1.id, Match.p2_id == p2.id),
            and_(Match.p1_id == p2.id, Match.p2_id == p1.id))).count()
    _riv_prefix = '🔥 Rivalry Match: ' if _rival_count >= 5 else ''
    if m.draw:
        _activity('match', p1.id, f'{_riv_prefix}drew with {p2.name()} {m.p1_score}–{m.p2_score} ({m.elo_d1:+d}/{m.elo_d2:+d})', 'handshake', 'warn', url_for('matches.match_view',mid=m.id))
    elif m.winner_id==p1.id:
        _activity('match', p1.id, f'{_riv_prefix}beat {p2.name()} {m.p1_score}–{m.p2_score} ({m.elo_d1:+d}/{m.elo_d2:+d})', 'trophy', 'success', url_for('matches.match_view',mid=m.id))
    elif m.winner_id==p2.id:
        _activity('match', p2.id, f'{_riv_prefix}beat {p1.name()} {m.p2_score}–{m.p1_score} ({m.elo_d1:+d}/{m.elo_d2:+d})', 'trophy', 'success', url_for('matches.match_view',mid=m.id))
    if m.winner_id: _award_points(m.winner_id, 10, f'Ranked win (Match #{m.id})')
    if m.stake and m.stake > 0 and m.winner_id:
        _award_points(m.winner_id, m.stake * 2, f'Challenge stake won (Match #{m.id})')
    for p in [p1, p2]:
        if p.streak in [3, 5, 7, 10, 15, 20]:
            streak_msgs = {
                3: ('🔥 3-Win Streak!', f'{p.name()} is on a 3-game winning streak!'),
                5: ('🔥🔥 5-Win Streak!', f'{p.name()} is on fire with 5 wins in a row!'),
                7: ('🔥🔥🔥 7-Win Streak!', f'{p.name()} is dominating with 7 consecutive wins!'),
                10: ('💥 10-WIN STREAK!', f'{p.name()} is UNSTOPPABLE with 10 straight wins!'),
                15: ('⚡ 15-WIN STREAK!', f'{p.name()} has reached legendary status — 15 wins!'),
                20: ('👑 20-WIN STREAK!', f'{p.name()} is a GOD — 20 consecutive wins!'),
            }
            title, msg = streak_msgs[p.streak]
            _alert(p.id, title, msg, 'success')
            _activity('streak', p.id, f'{p.streak}-win streak! 🔥', 'fire-flame-curved', 'success')
            streak_coins = {3: 5, 5: 15, 7: 30, 10: 50, 15: 75, 20: 100}
            if p.streak in streak_coins:
                _award_points(p.id, streak_coins[p.streak], f'{p.streak}-win streak bonus')
            if p.streak >= 5:
                from models import User as UserModel
                for u in UserModel.query.filter(UserModel.id!=p.id, UserModel.banned==False).limit(50).all():
                    _alert(u.id, f'🔥 {p.name()} on a Streak!', msg, 'info')
    _check_rank_change(p1, p1_old_rank)
    _check_rank_change(p2, p2_old_rank)
    _invalidate_title_cache(p1.id)
    _invalidate_title_cache(p2.id)
    for pred in m.predictions.all():
        if m.draw: pred.correct = False
        else:
            pred.correct = (pred.predicted_winner_id == m.winner_id)
            if pred.correct: _award_points(pred.user_id, 5, f'Correct match prediction (Match #{m.id})')
    if m.winner_id:
        cwm = ClanWarMatch.query.filter_by(match_id=m.id).first()
        if cwm and cwm.war.status == 'active':
            if m.winner_id == cwm.clan1_player_id: cwm.war.clan1_wins += 1
            elif m.winner_id == cwm.clan2_player_id: cwm.war.clan2_wins += 1
            _check_war_completion(cwm.war)
    _ok()


def _proc_u(m):
    from models import User, Match, ClanWarMatch
    if m.ranked or m.state!='verified': return
    p1=db.session.get(User,m.p1_id); p2=db.session.get(User,m.p2_id)
    if not p1 or not p2: return
    _rival_count = Match.query.filter(
        Match.state == 'verified', Match.ranked == True,
        or_(and_(Match.p1_id == p1.id, Match.p2_id == p2.id),
            and_(Match.p1_id == p2.id, Match.p2_id == p1.id))).count()
    _riv_prefix = '🔥 Rivalry Match: ' if _rival_count >= 5 else ''
    if m.draw:
        p1.u_draws+=1; p2.u_draws+=1
        _activity('match', p1.id, f'{_riv_prefix}drew with {p2.name()} {m.p1_score}–{m.p2_score} [Unranked]', 'handshake', 'warn', url_for('matches.match_view',mid=m.id))
    elif m.winner_id==p1.id:
        p1.u_wins+=1; p2.u_losses+=1
        _activity('match', p1.id, f'{_riv_prefix}beat {p2.name()} {m.p1_score}–{m.p2_score} [Unranked]', 'trophy', 'success', url_for('matches.match_view',mid=m.id))
    elif m.winner_id==p2.id:
        p2.u_wins+=1; p1.u_losses+=1
        _activity('match', p2.id, f'{_riv_prefix}beat {p1.name()} {m.p2_score}–{m.p1_score} [Unranked]', 'trophy', 'success', url_for('matches.match_view',mid=m.id))
    if m.winner_id: _award_points(m.winner_id, 5, f'Unranked win (Match #{m.id})')
    if m.stake and m.stake > 0 and m.winner_id:
        _award_points(m.winner_id, m.stake * 2, f'Challenge stake won (Match #{m.id})')
    for pred in m.predictions.all():
        if m.draw: pred.correct = False
        else:
            pred.correct = (pred.predicted_winner_id == m.winner_id)
            if pred.correct: _award_points(pred.user_id, 5, f'Correct match prediction (Match #{m.id})')
    if m.winner_id:
        cwm = ClanWarMatch.query.filter_by(match_id=m.id).first()
        if cwm and cwm.war.status == 'active':
            if m.winner_id == cwm.clan1_player_id: cwm.war.clan1_wins += 1
            elif m.winner_id == cwm.clan2_player_id: cwm.war.clan2_wins += 1
            _check_war_completion(cwm.war)


# ===========================================================================
# CLAN WAR & ACHIEVEMENTS
# ===========================================================================
def _check_war_completion(war):
    from models import Clan, ClanAchievement, clan_members
    majority = math.ceil(war.match_count / 2)
    winner_clan_id = None
    if war.clan1_wins >= majority: winner_clan_id = war.clan1_id
    elif war.clan2_wins >= majority: winner_clan_id = war.clan2_id
    if winner_clan_id is None: return
    war.winner_clan_id = winner_clan_id
    war.status = 'completed'
    war.completed_at = datetime.now(timezone.utc)
    winning_members = db.session.execute(
        clan_members.select().where(clan_members.c.clan_id == winner_clan_id)).fetchall()
    for m in winning_members:
        _award_points(m.user_id, 50, f'Clan war victory (war #{war.id})')
    winner_clan = db.session.get(Clan, winner_clan_id)
    loser_clan_id = war.clan2_id if winner_clan_id == war.clan1_id else war.clan1_id
    loser_clan = db.session.get(Clan, loser_clan_id)
    for cid_alert in [war.clan1_id, war.clan2_id]:
        leaders = db.session.execute(
            clan_members.select().where(and_(clan_members.c.clan_id == cid_alert, clan_members.c.role.in_(['owner', 'officer'])))).fetchall()
        for leader in leaders:
            _alert(leader.user_id, 'Clan War Completed',
                   f'[{winner_clan.tag}] {winner_clan.name} won the war against [{loser_clan.tag}] {loser_clan.name} ({war.clan1_wins}-{war.clan2_wins})!',
                   'success' if cid_alert == winner_clan_id else 'info',
                   url_for('clans.clan_war_detail', cid=cid_alert, wid=war.id))
    for cid_ach in [war.clan1_id, war.clan2_id]:
        c_ach = db.session.get(Clan, cid_ach)
        if c_ach: _check_clan_achievements(c_ach)

def _check_clan_achievements(clan):
    from models import ClanAchievement, ClanWar, User, clan_members
    existing = {a.achievement_type for a in clan.clan_achievements.all()}
    for threshold, atype in [(1000, 'score_1000'), (5000, 'score_5000'), (10000, 'score_10000')]:
        if clan.score >= threshold and atype not in existing:
            db.session.add(ClanAchievement(clan_id=clan.id, achievement_type=atype))
            existing.add(atype)
            info = CLAN_ACHIEVEMENT_TYPES[atype]
            leaders = db.session.execute(
                clan_members.select().where(and_(clan_members.c.clan_id == clan.id, clan_members.c.role.in_(['owner', 'officer'])))).fetchall()
            for ld in leaders:
                _alert(ld.user_id, f'🏆 Achievement Unlocked: {info["name"]}', info['desc'], 'success')
    if 'war_veterans' not in existing:
        war_wins = ClanWar.query.filter_by(winner_clan_id=clan.id).count()
        if war_wins >= 3:
            db.session.add(ClanAchievement(clan_id=clan.id, achievement_type='war_veterans'))
            existing.add('war_veterans')
            info = CLAN_ACHIEVEMENT_TYPES['war_veterans']
            leaders = db.session.execute(
                clan_members.select().where(and_(clan_members.c.clan_id == clan.id, clan_members.c.role.in_(['owner', 'officer'])))).fetchall()
            for ld in leaders: _alert(ld.user_id, f'🏆 Achievement Unlocked: {info["name"]}', info['desc'], 'success')
    if 'elite_squad' not in existing:
        member_rows = db.session.execute(clan_members.select().where(clan_members.c.clan_id == clan.id)).fetchall()
        elite_count = 0
        for mr in member_rows:
            u = db.session.get(User, mr.user_id)
            if u and u.elo > 1800: elite_count += 1
        if elite_count >= 5:
            db.session.add(ClanAchievement(clan_id=clan.id, achievement_type='elite_squad'))
            existing.add('elite_squad')
            info = CLAN_ACHIEVEMENT_TYPES['elite_squad']
            leaders = db.session.execute(
                clan_members.select().where(and_(clan_members.c.clan_id == clan.id, clan_members.c.role.in_(['owner', 'officer'])))).fetchall()
            for ld in leaders: _alert(ld.user_id, f'🏆 Achievement Unlocked: {info["name"]}', info['desc'], 'success')

def _get_clan_achievement_registry():
    """Merge predefined + custom achievement types. Predefined wins on collision."""
    from models import CustomClanAchievementType
    registry = {}
    for ct in CustomClanAchievementType.query.all():
        registry[ct.key] = {'name': ct.name, 'icon': ct.icon, 'desc': ct.description or '', 'image': ct.image}
    registry.update(CLAN_ACHIEVEMENT_TYPES)
    return registry


# ===========================================================================
# MVP
# ===========================================================================
def _resolve_mvp_period(period_type, period_key):
    from models import MVPVote, PointTransaction, User
    reason_pattern = f'%MVP ({period_type} {period_key})%'
    already = PointTransaction.query.filter(PointTransaction.reason.like(reason_pattern)).first()
    if already: return None
    results = db.session.query(
        MVPVote.candidate_id, func.count(MVPVote.id).label('vote_count')
    ).filter_by(period_type=period_type, period_key=period_key
    ).group_by(MVPVote.candidate_id).order_by(func.count(MVPVote.id).desc()).first()
    if not results: return None
    winner_id, vote_count = results
    winner = db.session.get(User, winner_id)
    if not winner: return None
    amount = 25 if period_type == 'weekly' else 100
    _award_points(winner_id, amount, f'{period_type.capitalize()} MVP ({period_type} {period_key}) — {vote_count} votes')
    _alert(winner_id, f'🏆 {period_type.capitalize()} MVP!',
           f'You were voted {period_type} MVP for {period_key} with {vote_count} vote(s)! +{amount} PongCoins', 'success')
    return winner

def _check_mvp_periods():
    now = datetime.now(timezone.utc)
    resolved_any = False
    prev_week = now - timedelta(weeks=1)
    prev_week_key = prev_week.strftime('%G-W%V')
    if _resolve_mvp_period('weekly', prev_week_key): resolved_any = True
    first_of_month = now.replace(day=1)
    prev_month_last = first_of_month - timedelta(days=1)
    prev_month_key = prev_month_last.strftime('%Y-%m')
    if _resolve_mvp_period('monthly', prev_month_key): resolved_any = True
    if resolved_any: _ok()

# ===========================================================================
# ALERTS
# ===========================================================================
def _top_alerts():
    from models import GlobalAlert, Alert
    try:
        items=[]
        dismissed_globals = session.get('dismissed_globals', []) if session else []
        for ga in GlobalAlert.query.filter_by(active=True).order_by(GlobalAlert.created_at.desc()).limit(3).all():
            if ga.id not in dismissed_globals:
                items.append({'title':ga.title,'cat':ga.cat,'link':ga.link or url_for('main.my_alerts'),'gl':True,'id':ga.id})
        if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
            for pa in current_user.alerts.filter_by(read=False).order_by(Alert.created_at.desc()).limit(3).all():
                items.append({'title':pa.title,'cat':pa.cat,'link':pa.link or url_for('main.my_alerts'),'gl':False,'id':pa.id})
        return items[:5]
    except Exception: return []


# ===========================================================================
# TITLE CACHE
# ===========================================================================
_title_cache = {}
_TITLE_CACHE_TTL = 300

def _calc_titles_cached(user):
    now = time.time()
    entry = _title_cache.get(user.id)
    if entry and (now - entry[1]) < _TITLE_CACHE_TTL: return entry[0]
    titles = _calc_titles(user)
    _title_cache[user.id] = (titles, now)
    return titles

def _invalidate_title_cache(user_id):
    _title_cache.pop(user_id, None)

def _invalidate_title_cache_for_tournament(tourney):
    from models import tourney_players
    pids = db.session.query(tourney_players.c.user_id).filter_by(tournament_id=tourney.id).all()
    for (pid,) in pids: _title_cache.pop(pid, None)

def _calc_titles(user):
    from models import Tournament, Match
    titles = []
    if user.r_wins >= 100: titles.append('Centurion')
    elif user.r_wins >= 50: titles.append('Veteran')
    elif user.r_wins >= 25: titles.append('Seasoned')
    elif user.r_wins >= 10: titles.append('Competitor')
    if user.best_streak >= 15: titles.append('Unstoppable')
    elif user.best_streak >= 10: titles.append('Dominator')
    elif user.best_streak >= 7: titles.append('On Fire')
    elif user.best_streak >= 5: titles.append('Hot Streak')
    elif user.best_streak >= 3: titles.append('Momentum')
    if user.total_ranked >= 10:
        if user.ranked_wr >= 80: titles.append('Elite')
        elif user.ranked_wr >= 70: titles.append('Sharpshooter')
        elif user.ranked_wr >= 60: titles.append('Consistent')
    if user.total_matches >= 200: titles.append('No Life')
    elif user.total_matches >= 100: titles.append('Grinder')
    elif user.total_matches >= 50: titles.append('Dedicated')
    tourney_wins = 0
    for t in Tournament.query.filter_by(status='completed').all():
        tr = t.total_rounds
        if tr > 0:
            final = t.matches.filter_by(round_num=tr).first()
            if final and final.winner_id == user.id: tourney_wins += 1
    if tourney_wins >= 5: titles.append('Dynasty')
    elif tourney_wins >= 3: titles.append('Champion')
    elif tourney_wins >= 1: titles.append('Tournament Winner')
    if user.r_losses >= 50 and user.ranked_wr < 30: titles.append('Punching Bag')
    if user.total_matches >= 10 and user.r_wins == 0 and user.r_losses > 0: titles.append('Participation Trophy')
    if user.total_ranked >= 20 and user.r_losses <= 3: titles.append('Iron Wall')
    return titles

def _calc_form(user):
    from models import Match
    recent = Match.query.filter(
        or_(Match.p1_id == user.id, Match.p2_id == user.id),
        Match.ranked == True, Match.state == 'verified'
    ).order_by(Match.played_at.desc()).limit(10).all()
    if len(recent) < 10: return {'label': 'New', 'arrow': '\u2014', 'color': 'var(--tm)'}
    wins = sum(1 for m in recent if m.winner_id == user.id)
    if wins >= 7: return {'label': 'On Fire', 'arrow': '\u2191', 'color': 'var(--ok)'}
    if wins >= 4: return {'label': 'Steady', 'arrow': '\u2192', 'color': 'var(--acc)'}
    return {'label': 'Cold', 'arrow': '\u2193', 'color': 'var(--err)'}

def _get_rivals(user):
    from models import Match, User
    matches = Match.query.filter(
        or_(Match.p1_id == user.id, Match.p2_id == user.id),
        Match.ranked == True, Match.state == 'verified').all()
    opp_stats = {}
    for m in matches:
        opp_id = m.p2_id if m.p1_id == user.id else m.p1_id
        if opp_id not in opp_stats:
            opp_stats[opp_id] = {'wins': 0, 'losses': 0, 'draws': 0, 'total_matches': 0, 'elo_exchanged': 0}
        s = opp_stats[opp_id]; s['total_matches'] += 1
        if m.winner_id == user.id: s['wins'] += 1
        elif m.winner_id is None: s['draws'] += 1
        else: s['losses'] += 1
        if m.p1_id == user.id: s['elo_exchanged'] += abs(m.elo_d1)
        else: s['elo_exchanged'] += abs(m.elo_d2)
    rivals = []
    for opp_id, s in opp_stats.items():
        if s['total_matches'] >= 5:
            opp = db.session.get(User, opp_id)
            if opp: rivals.append({'opponent':opp,'wins':s['wins'],'losses':s['losses'],'draws':s['draws'],
                                   'total_matches':s['total_matches'],'elo_exchanged':s['elo_exchanged']})
    rivals.sort(key=lambda r: r['total_matches'], reverse=True)
    return rivals[:3]


# ===========================================================================
# BRACKET & TOURNAMENT LOGIC
# ===========================================================================
def _next_pow2(n):
    p=1
    while p<n: p*=2
    return p

def _generate_bracket(tourney):
    from models import Match, User
    if tourney.bracket_generated: return False
    players=list(tourney.players.all())
    if len(players)<2: return False
    sm = tourney.seeding_mode or 'elo'
    if sm == 'elo': players.sort(key=lambda u: u.elo, reverse=True)
    elif sm == 'experience': players.sort(key=lambda u: u.total_matches, reverse=True)
    elif sm == 'winrate': players.sort(key=lambda u: (u.ranked_wr, u.elo), reverse=True)
    elif sm == 'random': random.shuffle(players)
    else: players.sort(key=lambda u: u.elo, reverse=True)
    size=_next_pow2(len(players))
    seeded=players+[None]*(size-len(players))
    def seed_order(n):
        if n==1: return [0]
        prev=seed_order(n//2)
        return [x for p in prev for x in (p, n-1-p)]
    order=seed_order(size)
    arranged=[seeded[i] for i in order]
    rnd=1; sf=tourney.default_series or 'bo1'
    for pos in range(0,size,2):
        p1=arranged[pos]; p2=arranged[pos+1]; bp=pos//2
        if p1 and p2:
            m=Match(tourney_id=tourney.id,p1_id=p1.id,p2_id=p2.id,round_num=rnd,bracket_pos=bp,ranked=tourney.ranked,state='scheduled',p1_score=0,p2_score=0,series_format=sf)
            db.session.add(m)
        elif p1 and not p2:
            m=Match(tourney_id=tourney.id,p1_id=p1.id,p2_id=p1.id,round_num=rnd,bracket_pos=bp,ranked=False,state='verified',winner_id=p1.id,p1_score=1,p2_score=0,notes='Bye')
            db.session.add(m)
        elif p2 and not p1:
            m=Match(tourney_id=tourney.id,p1_id=p2.id,p2_id=p2.id,round_num=rnd,bracket_pos=bp,ranked=False,state='verified',winner_id=p2.id,p1_score=0,p2_score=1,notes='Bye')
            db.session.add(m)
    tourney.bracket_generated=True; tourney.current_round=1; tourney.status='active'; _ok()
    _try_advance_round(tourney)
    return True


def _try_advance_round(tourney, _depth=0):
    from models import Match
    if _depth >= 20:
        log.warning(f"Max recursion depth reached for tournament {tourney.id}")
        return
    cr = tourney.current_round
    if cr <= 0: return
    all_round_nums = [r[0] for r in db.session.query(Match.round_num).filter(
        Match.tourney_id==tourney.id, Match.round_num > 0).distinct().all()]
    if not all_round_nums: return
    round_matches = tourney.matches.filter_by(round_num=cr).order_by(Match.bracket_pos).all()
    if not round_matches: return
    if not all(m.state == 'verified' for m in round_matches): return
    nr = cr + 1
    existing_next = tourney.matches.filter_by(round_num=nr).count()
    if existing_next > 0:
        tourney.current_round = nr; _ok()
    else:
        if len(round_matches) == 1 and round_matches[0].p1_id != round_matches[0].p2_id:
            if tourney.status != 'completed':
                tourney.status = 'completed'; _ok()
                _invalidate_title_cache_for_tournament(tourney)
                _create_victory_news(tourney, round_matches[0])
            return
        matches_created = 0
        sf = tourney.default_series or 'bo1'
        for i in range(0, len(round_matches), 2):
            if i + 1 < len(round_matches):
                m1 = round_matches[i]; m2 = round_matches[i + 1]
                w1 = m1.winner_id; w2 = m2.winner_id
                if w1 and w2:
                    nm = Match(tourney_id=tourney.id, p1_id=w1, p2_id=w2,
                              round_num=nr, bracket_pos=i // 2, ranked=tourney.ranked,
                              state='scheduled', p1_score=0, p2_score=0, series_format=sf)
                    db.session.add(nm); matches_created += 1
                elif w1:
                    nm = Match(tourney_id=tourney.id, p1_id=w1, p2_id=w1,
                              round_num=nr, bracket_pos=i // 2, ranked=False,
                              state='verified', winner_id=w1, p1_score=1, p2_score=0, notes='Bye')
                    db.session.add(nm); matches_created += 1
                elif w2:
                    nm = Match(tourney_id=tourney.id, p1_id=w2, p2_id=w2,
                              round_num=nr, bracket_pos=i // 2, ranked=False,
                              state='verified', winner_id=w2, p1_score=1, p2_score=0, notes='Bye')
                    db.session.add(nm); matches_created += 1
            elif i < len(round_matches):
                m1 = round_matches[i]
                if m1.winner_id:
                    nm = Match(tourney_id=tourney.id, p1_id=m1.winner_id, p2_id=m1.winner_id,
                              round_num=nr, bracket_pos=i // 2, ranked=False,
                              state='verified', winner_id=m1.winner_id, p1_score=1, p2_score=0, notes='Bye')
                    db.session.add(nm); matches_created += 1
        if matches_created > 0:
            tourney.current_round = nr; _ok()
            log.info(f"Advanced to round {nr}: {matches_created} matches created")
        else: return
    next_matches = tourney.matches.filter_by(round_num=nr).all()
    if next_matches and all(m.state == 'verified' for m in next_matches):
        real_matches = [m for m in next_matches if m.p1_id != m.p2_id]
        if len(next_matches) == 1 and len(real_matches) == 1 and next_matches[0].state == 'verified':
            if tourney.status != 'completed':
                tourney.status = 'completed'; _ok()
                _invalidate_title_cache_for_tournament(tourney)
                _create_victory_news(tourney, next_matches[0])
            return
        elif len(next_matches) == 1 and len(real_matches) == 0:
            pass
        _try_advance_round(tourney, _depth + 1)


def _partial_advance_round(tourney):
    """Create next-round matches for completed pairs in the current round.

    Iterates current-round matches in pairs by bracket_pos. For each pair
    where both feeder matches are verified, creates a next-round match with
    the winners (if it doesn't already exist). Returns count of matches created.
    """
    from models import Match
    cr = tourney.current_round
    if cr <= 0:
        return 0
    if tourney.fmt == 'round_robin':
        return 0
    round_matches = tourney.matches.filter_by(round_num=cr).order_by(Match.bracket_pos).all()
    if not round_matches:
        return 0
    nr = cr + 1
    sf = tourney.default_series or 'bo1'
    created = 0
    for i in range(0, len(round_matches), 2):
        if i + 1 >= len(round_matches):
            break
        m1 = round_matches[i]
        m2 = round_matches[i + 1]
        if m1.state != 'verified' or m2.state != 'verified':
            continue
        if not m1.winner_id or not m2.winner_id:
            continue
        bp = i // 2
        existing = tourney.matches.filter_by(round_num=nr, bracket_pos=bp).first()
        if existing:
            continue
        nm = Match(
            tourney_id=tourney.id, p1_id=m1.winner_id, p2_id=m2.winner_id,
            round_num=nr, bracket_pos=bp, ranked=tourney.ranked,
            state='scheduled', p1_score=0, p2_score=0, series_format=sf
        )
        db.session.add(nm)
        created += 1
    if created > 0:
        _ok()
        # If all current-round matches are now verified and all next-round
        # matches exist, advance the current_round.
        all_verified = all(m.state == 'verified' for m in round_matches)
        if all_verified:
            expected_next = len(round_matches) // 2
            actual_next = tourney.matches.filter_by(round_num=nr).count()
            if actual_next >= expected_next:
                tourney.current_round = nr
                _ok()
                log.info(f"[PARTIAL] Tournament {tourney.id} advanced to round {nr}")
    return created


def _check_tourney_completion(tourney):
    from models import Match
    if tourney.current_round == 0:
        play_in = tourney.matches.filter_by(round_num=0).all()
        if not play_in: return
        if all(m.state == 'verified' for m in play_in):
            main_exists = tourney.matches.filter(Match.round_num > 0).count()
            if main_exists == 0: _advance_play_in(tourney)
            else: tourney.current_round = 1; _ok(); _try_advance_round(tourney)
        return
    if tourney.fmt == 'round_robin':
        _check_round_robin_advancement(tourney)
        return
    # Partial advance: create next-round matches for any newly completed pairs
    _partial_advance_round(tourney)
    _try_advance_round(tourney)
    tr = tourney.total_rounds
    if tr > 0 and tourney.current_round >= tr:
        final = tourney.matches.filter_by(round_num=tr).first()
        if final and final.state == 'verified' and tourney.status != 'completed':
            tourney.status = 'completed'; _ok()
            _invalidate_title_cache_for_tournament(tourney)
            _create_victory_news(tourney, final)

def _check_round_robin_advancement(tourney):
    cr = tourney.current_round
    current_matches = tourney.matches.filter_by(round_num=cr).all()
    if not current_matches: return
    real_matches = [m for m in current_matches if m.notes != 'Bye' and m.p1_id != m.p2_id]
    if not all(m.state == 'verified' for m in real_matches): return
    next_round_matches = tourney.matches.filter_by(round_num=cr+1).count()
    if next_round_matches > 0:
        tourney.current_round = cr + 1; _ok()
    else:
        if tourney.status != 'completed':
            tourney.status = 'completed'
            _invalidate_title_cache_for_tournament(tourney)
            _ok()
            _create_round_robin_results(tourney)

def _create_round_robin_results(tourney):
    from models import Match, News
    all_matches = tourney.matches.filter(
        Match.state=='verified', Match.notes!='Bye', Match.p1_id!=Match.p2_id).all()
    standings = {}
    for p in tourney.players.all():
        standings[p.id] = {'user': p, 'wins': 0, 'losses': 0, 'draws': 0, 'pts': 0, 'scored': 0, 'conceded': 0}
    for m in all_matches:
        if m.p1_id in standings:
            standings[m.p1_id]['scored'] += m.p1_score; standings[m.p1_id]['conceded'] += m.p2_score
        if m.p2_id in standings:
            standings[m.p2_id]['scored'] += m.p2_score; standings[m.p2_id]['conceded'] += m.p1_score
        if m.draw:
            if m.p1_id in standings: standings[m.p1_id]['draws'] += 1; standings[m.p1_id]['pts'] += 1
            if m.p2_id in standings: standings[m.p2_id]['draws'] += 1; standings[m.p2_id]['pts'] += 1
        elif m.winner_id == m.p1_id:
            if m.p1_id in standings: standings[m.p1_id]['wins'] += 1; standings[m.p1_id]['pts'] += 3
            if m.p2_id in standings: standings[m.p2_id]['losses'] += 1
        elif m.winner_id == m.p2_id:
            if m.p2_id in standings: standings[m.p2_id]['wins'] += 1; standings[m.p2_id]['pts'] += 3
            if m.p1_id in standings: standings[m.p1_id]['losses'] += 1
    sorted_standings = sorted(standings.values(), key=lambda s: (s['pts'], s['wins'], s['scored']-s['conceded']), reverse=True)
    if not sorted_standings: return
    winner = sorted_standings[0]['user']
    title = f"🏆 {winner.name()} wins {tourney.name}!"
    table_rows = ''.join([
        f"<tr><td>{i+1}</td><td>{s['user'].name()}</td><td>{s['pts']}</td><td>{s['wins']}</td><td>{s['draws']}</td><td>{s['losses']}</td><td>{s['scored']}-{s['conceded']}</td></tr>"
        for i, s in enumerate(sorted_standings)])
    content = f"""<p><strong>{winner.name()}</strong> has won <strong>{tourney.name}</strong> in a round robin format!</p>
<h3>Final Standings</h3>
<table><thead><tr><th>#</th><th>Player</th><th>Pts</th><th>W</th><th>D</th><th>L</th><th>Score</th></tr></thead><tbody>{table_rows}</tbody></table>"""
    summary = f"{winner.name()} wins {tourney.name} with {sorted_standings[0]['pts']} points!"
    n = News(title=title, summary=summary, content=content, category='tournament',
             published=True, pinned=True, auto=False, author_id=tourney.created_by)
    n.make_slug()
    db.session.add(n); _ok()
    _alert(winner.id, '🏆 Tournament Champion!', f'You won {tourney.name}!', 'success', url_for('main.news_view', slug=n.slug)); _ok()
    for p in tourney.players.all():
        if p.id != winner.id:
            _alert(p.id, f'{tourney.name} Complete', f'{winner.name()} won the tournament!', 'info', url_for('main.news_view', slug=n.slug)); _ok()


def _generate_play_in(tourney):
    from models import Match, User
    if tourney.bracket_generated: return False
    players = list(tourney.players.all())
    if len(players) < 2: return False
    sm = tourney.seeding_mode or 'elo'
    if sm == 'elo': players.sort(key=lambda u: u.elo, reverse=True)
    elif sm == 'experience': players.sort(key=lambda u: u.total_matches, reverse=True)
    elif sm == 'winrate': players.sort(key=lambda u: (u.ranked_wr, u.elo), reverse=True)
    elif sm == 'random': random.shuffle(players)
    else: players.sort(key=lambda u: u.elo, reverse=True)
    pc = len(players)
    lower_pow2 = 1
    while lower_pow2 * 2 <= pc: lower_pow2 *= 2
    play_in_matches_needed = pc - lower_pow2
    auto_advance_count = pc - (play_in_matches_needed * 2)
    auto_advance = players[:auto_advance_count]
    play_in_players = players[auto_advance_count:]
    sf = tourney.default_series or 'bo1'
    for i in range(0, len(play_in_players), 2):
        if i + 1 < len(play_in_players):
            p1 = play_in_players[i]; p2 = play_in_players[i + 1]
            m = Match(tourney_id=tourney.id, p1_id=p1.id, p2_id=p2.id,
                     round_num=0, bracket_pos=i // 2, ranked=tourney.ranked,
                     state='scheduled', p1_score=0, p2_score=0, notes='Play-In', series_format=sf)
            db.session.add(m)
        else:
            p1 = play_in_players[i]
            m = Match(tourney_id=tourney.id, p1_id=p1.id, p2_id=p1.id,
                     round_num=0, bracket_pos=i // 2, ranked=False,
                     state='verified', winner_id=p1.id, p1_score=1, p2_score=0, notes='Bye')
            db.session.add(m)
    tourney.bracket_generated = True; tourney.current_round = 0; tourney.status = 'active'; _ok()
    for p in play_in_players:
        _alert(p.id, '🎮 Play-In Match!', f'You have a play-in match in {tourney.name}. Win to advance to the main bracket!', 'warning', url_for('tournaments.t_view', tid=tourney.id)); _ok()
    for p in auto_advance:
        _alert(p.id, '✅ Auto-Advanced!', f'You auto-advance to the main bracket in {tourney.name}. Waiting for play-in matches to complete.', 'success', url_for('tournaments.t_view', tid=tourney.id)); _ok()
    play_in_matches = tourney.matches.filter_by(round_num=0).all()
    if all(m.state == 'verified' for m in play_in_matches):
        _advance_play_in(tourney)
    return True


def _advance_play_in(tourney):
    from models import Match, User
    play_in_matches = tourney.matches.filter_by(round_num=0).all()
    if not play_in_matches:
        log.error(f"[PLAY-IN] No play-in matches found for tournament {tourney.id}"); return
    if not all(m.state == 'verified' for m in play_in_matches):
        log.info(f"[PLAY-IN] Not all play-in matches verified yet"); return
    main_count = tourney.matches.filter(Match.round_num > 0).count()
    if main_count > 0:
        log.info(f"[PLAY-IN] Main bracket already exists ({main_count} matches), setting round to 1")
        tourney.current_round = 1; _ok(); return
    all_players = list(tourney.players.all())
    play_in_player_ids = set()
    play_in_winner_ids = []
    for m in sorted(play_in_matches, key=lambda x: x.bracket_pos):
        if m.notes == 'Bye':
            if m.winner_id: play_in_winner_ids.append(m.winner_id); play_in_player_ids.add(m.winner_id)
        else:
            play_in_player_ids.add(m.p1_id); play_in_player_ids.add(m.p2_id)
            if m.winner_id: play_in_winner_ids.append(m.winner_id)
    sm = tourney.seeding_mode or 'elo'
    if sm == 'elo': all_players.sort(key=lambda u: u.elo, reverse=True)
    elif sm == 'experience': all_players.sort(key=lambda u: u.total_matches, reverse=True)
    elif sm == 'winrate': all_players.sort(key=lambda u: (u.ranked_wr, u.elo), reverse=True)
    elif sm == 'random': random.shuffle(all_players)
    else: all_players.sort(key=lambda u: u.elo, reverse=True)
    auto_advance = [p for p in all_players if p.id not in play_in_player_ids]
    play_in_winners = []
    for wid in play_in_winner_ids:
        w = db.session.get(User, wid)
        if w and w not in play_in_winners: play_in_winners.append(w)
    main_bracket_players = auto_advance + play_in_winners
    if len(main_bracket_players) < 2:
        log.error(f"[PLAY-IN] Only {len(main_bracket_players)} players for main bracket, aborting"); return
    size = _next_pow2(len(main_bracket_players))
    seeded = main_bracket_players + [None] * (size - len(main_bracket_players))
    def seed_order(n):
        if n == 1: return [0]
        prev = seed_order(n // 2)
        return [x for p in prev for x in (p, n - 1 - p)]
    order = seed_order(size)
    arranged = [seeded[i] for i in order]
    rnd = 1; sf = tourney.default_series or 'bo1'
    for pos in range(0, size, 2):
        p1 = arranged[pos]; p2 = arranged[pos + 1]; bp = pos // 2
        if p1 and p2:
            m = Match(tourney_id=tourney.id, p1_id=p1.id, p2_id=p2.id,
                     round_num=rnd, bracket_pos=bp, ranked=tourney.ranked,
                     state='scheduled', p1_score=0, p2_score=0, series_format=sf)
            db.session.add(m)
        elif p1 and not p2:
            m = Match(tourney_id=tourney.id, p1_id=p1.id, p2_id=p1.id,
                     round_num=rnd, bracket_pos=bp, ranked=False,
                     state='verified', winner_id=p1.id, p1_score=1, p2_score=0, notes='Bye')
            db.session.add(m)
        elif p2 and not p1:
            m = Match(tourney_id=tourney.id, p1_id=p2.id, p2_id=p2.id,
                     round_num=rnd, bracket_pos=bp, ranked=False,
                     state='verified', winner_id=p2.id, p1_score=0, p2_score=1, notes='Bye')
            db.session.add(m)
    _ok()
    tourney.current_round = 1; _ok()
    for p in main_bracket_players:
        if p: _alert(p.id, '🏆 Main Bracket Ready!', f'The main bracket for {tourney.name} has been generated!', 'success', url_for('tournaments.t_view', tid=tourney.id)); _ok()
    _try_advance_round(tourney)


def _generate_round_robin(tourney):
    from models import Match
    if tourney.bracket_generated: return False
    players = list(tourney.players.all())
    if len(players) < 2: return False
    sm = tourney.seeding_mode or 'elo'
    if sm == 'random': random.shuffle(players)
    else: players.sort(key=lambda u: u.elo, reverse=True)
    n = len(players)
    if n % 2 != 0: players.append(None); n += 1
    rnd = 1; sf = tourney.default_series or 'bo1'
    for r in range(n - 1):
        bp = 0
        for i in range(n // 2):
            p1 = players[i]; p2 = players[n - 1 - i]
            if p1 and p2:
                m = Match(tourney_id=tourney.id, p1_id=p1.id, p2_id=p2.id,
                         round_num=rnd, bracket_pos=bp, ranked=tourney.ranked,
                         state='scheduled', p1_score=0, p2_score=0, series_format=sf)
                db.session.add(m); bp += 1
            elif p1 and not p2:
                m = Match(tourney_id=tourney.id, p1_id=p1.id, p2_id=p1.id,
                         round_num=rnd, bracket_pos=bp, ranked=False,
                         state='verified', winner_id=p1.id, p1_score=1, p2_score=0, notes='Bye')
                db.session.add(m); bp += 1
        players.insert(1, players.pop())
        rnd += 1
    tourney.bracket_generated = True; tourney.current_round = 1; tourney.status = 'active'
    tourney.fmt = 'round_robin'; _ok()
    return True

def _calc_rr_standings(tourney):
    from models import Match
    all_matches = tourney.matches.filter(
        Match.state=='verified', Match.notes!='Bye', Match.p1_id!=Match.p2_id).all()
    standings = {}
    for p in tourney.players.all():
        standings[p.id] = type('S', (), {'user': p, 'wins': 0, 'losses': 0, 'draws': 0, 'pts': 0, 'scored': 0, 'conceded': 0})()
    for m in all_matches:
        if m.p1_id in standings:
            standings[m.p1_id].scored += m.p1_score; standings[m.p1_id].conceded += m.p2_score
        if m.p2_id in standings:
            standings[m.p2_id].scored += m.p2_score; standings[m.p2_id].conceded += m.p1_score
        if m.draw:
            if m.p1_id in standings: standings[m.p1_id].draws += 1; standings[m.p1_id].pts += 1
            if m.p2_id in standings: standings[m.p2_id].draws += 1; standings[m.p2_id].pts += 1
        elif m.winner_id == m.p1_id:
            if m.p1_id in standings: standings[m.p1_id].wins += 1; standings[m.p1_id].pts += 3
            if m.p2_id in standings: standings[m.p2_id].losses += 1
        elif m.winner_id == m.p2_id:
            if m.p2_id in standings: standings[m.p2_id].wins += 1; standings[m.p2_id].pts += 3
            if m.p1_id in standings: standings[m.p1_id].losses += 1
    return sorted(standings.values(), key=lambda s: (s.pts, s.wins, s.scored - s.conceded), reverse=True)

def _recalc_streak(user):
    from models import Match
    matches = Match.query.filter(
        or_(Match.p1_id==user.id, Match.p2_id==user.id),
        Match.state=='verified', Match.ranked==True
    ).order_by(Match.played_at.asc()).all()
    streak = 0; best = 0
    for m in matches:
        if m.draw: streak = 0
        elif m.winner_id == user.id: streak += 1; best = max(best, streak)
        else: streak = 0
    user.streak = streak; user.best_streak = best; _ok()


def _create_victory_news(tourney, final_match):
    from models import User, Match, News
    winner = db.session.get(User, final_match.winner_id)
    if not winner: return
    t_matches = tourney.matches.filter(Match.state=='verified', Match.notes!='Bye').all()
    total_played = len(t_matches)
    runner_id = final_match.p2_id if final_match.winner_id == final_match.p1_id else final_match.p1_id
    runner = db.session.get(User, runner_id)
    runner_name = runner.name() if runner else 'their opponent'
    w_matches = [m for m in t_matches if m.winner_id == winner.id]
    w_count = len(w_matches)
    phrases = [
        f"In a stunning display of skill and determination,",
        f"After an incredible run through the bracket,",
        f"Dominating the competition from start to finish,",
        f"In what can only be described as a masterclass performance,",
        f"Proving once again why they're a force to be reckoned with,",
    ]
    finals_phrases = [
        f"a thrilling final against {runner_name}",
        f"an intense showdown with {runner_name}",
        f"a hard-fought battle against {runner_name}",
        f"a decisive final match versus {runner_name}",
    ]
    narrative_open = random.choice(phrases)
    finals_desc = random.choice(finals_phrases)
    title = f"🏆 {winner.name()} wins {tourney.name}!"
    summary = f"{winner.name()} has claimed victory in {tourney.name}, defeating {runner_name} {final_match.p1_score}–{final_match.p2_score} in the final!"
    content = f"""<p>{narrative_open} <strong>{winner.name()}</strong> has emerged victorious in <strong>{tourney.name}</strong>!</p>
<p>The tournament featured <strong>{tourney.player_count} players</strong> competing across <strong>{tourney.total_rounds} rounds</strong> of intense {tourney.game or 'competition'}. A total of <strong>{total_played} matches</strong> were played throughout the event.</p>
<p>{winner.name()} secured the championship after {finals_desc}, winning <strong>{final_match.p1_score}–{final_match.p2_score}</strong>{' (as ' + ('P1' if final_match.winner_id == final_match.p1_id else 'P2') + ')' if final_match.p1_score != final_match.p2_score else ''}. Over the course of the tournament, {winner.name()} won <strong>{w_count} match{'es' if w_count != 1 else ''}</strong> to claim the title.</p>
<h3>🥇 Final Standings</h3>
<ul>
<li><strong>🥇 Champion:</strong> {winner.name()} (ELO: {winner.elo})</li>
<li><strong>🥈 Runner-up:</strong> {runner_name}{(' (ELO: ' + str(runner.elo) + ')') if runner else ''}</li>
</ul>"""
    if tourney.prize: content += f"\n<p><strong>Prize:</strong> {tourney.prize}</p>"
    content += f"\n<p>Congratulations to <strong>{winner.name()}</strong> and all participants! {'The tournament was ranked, so ELO ratings have been updated accordingly.' if tourney.ranked else ''}</p>"
    n = News(title=title, summary=summary, content=content, category='tournament', published=True, pinned=True, auto=False, author_id=tourney.created_by)
    n.make_slug()
    db.session.add(n); _ok()
    _activity('tournament', winner.id, f'Won {tourney.name}! 🏆', 'crown', 'success', url_for('tournaments.t_view', tid=tourney.id))
    _alert(winner.id, '🏆 Tournament Champion!', f'You won {tourney.name}! Check the news for the full story.', 'success', url_for('main.news_view', slug=n.slug)); _ok()
    for p in tourney.players.all():
        if p.id != winner.id:
            _alert(p.id, f'{tourney.name} Complete', f'{winner.name()} has won the tournament!', 'info', url_for('main.news_view', slug=n.slug)); _ok()
    _award_points(winner.id, 100, f'1st place — {tourney.name}')
    if runner: _award_points(runner.id, 50, f'2nd place — {tourney.name}')
    if tourney.total_rounds >= 2:
        semis = tourney.matches.filter_by(round_num=tourney.total_rounds - 1).all()
        for sm in semis:
            if sm.winner_id and sm.winner_id != winner.id and (not runner or sm.winner_id != runner.id):
                loser_id = sm.p1_id if sm.winner_id == sm.p2_id else sm.p2_id
                if loser_id and loser_id != winner.id and (not runner or loser_id != runner.id):
                    _award_points(loser_id, 25, f'3rd place — {tourney.name}')
    _ok()


def _build_projected_bracket(tourney, bracket):
    projected = {}
    if tourney.fmt == 'round_robin': return projected, sorted(bracket.keys())
    all_rounds = sorted(bracket.keys())
    if not all_rounds: return projected, all_rounds
    total_rounds = tourney.total_rounds
    max_existing = max(all_rounds) if all_rounds else 0
    for rnd in range(max_existing + 1, total_rounds + 1):
        projected_matches = []
        prev_matches = bracket.get(rnd - 1, [])
        if not prev_matches and (rnd - 1) in projected: prev_matches = projected[rnd - 1]
        for i in range(0, len(prev_matches), 2):
            m1 = prev_matches[i] if i < len(prev_matches) else None
            m2 = prev_matches[i + 1] if i + 1 < len(prev_matches) else None
            p1_name = '?'; p2_name = '?'; feeder_parts = []
            if m1:
                if hasattr(m1, 'is_projected') and m1.is_projected:
                    p1_name = f'W(M{m1.pos + 1})'; feeder_parts.append(f'W({tourney.round_name(rnd-1)} M{m1.pos + 1})')
                elif hasattr(m1, 'state') and m1.state == 'verified' and m1.winner_id:
                    w = m1.winner; p1_name = w.name() if w else '?'
                elif hasattr(m1, 'state') and m1.state == 'verified' and m1.notes == 'Bye':
                    p1_name = m1.p1.name() if m1.p1 else '?'
                else:
                    if hasattr(m1, 'p1') and hasattr(m1, 'p2') and m1.p1_id != m1.p2_id:
                        p1_name = f'{m1.p1.name()}/{m1.p2.name()}'
                        feeder_parts.append(f'W({m1.p1.name()[:6]} vs {m1.p2.name()[:6]})')
                    elif hasattr(m1, 'p1'): p1_name = m1.p1.name()
            if m2:
                if hasattr(m2, 'is_projected') and m2.is_projected:
                    p2_name = f'W(M{m2.pos + 1})'; feeder_parts.append(f'W({tourney.round_name(rnd-1)} M{m2.pos + 1})')
                elif hasattr(m2, 'state') and m2.state == 'verified' and m2.winner_id:
                    w = m2.winner; p2_name = w.name() if w else '?'
                elif hasattr(m2, 'state') and m2.state == 'verified' and m2.notes == 'Bye':
                    p2_name = m2.p1.name() if m2.p1 else '?'
                else:
                    if hasattr(m2, 'p1') and hasattr(m2, 'p2') and m2.p1_id != m2.p2_id:
                        p2_name = f'{m2.p1.name()}/{m2.p2.name()}'
                        feeder_parts.append(f'W({m2.p1.name()[:6]} vs {m2.p2.name()[:6]})')
                    elif hasattr(m2, 'p1'): p2_name = m2.p1.name()
            feeder = ' vs '.join(feeder_parts) if feeder_parts else ''
            pm = type('ProjectedMatch', (), {'is_projected': True, 'pos': i // 2, 'p1_name': p1_name, 'p2_name': p2_name, 'feeder': feeder})()
            projected_matches.append(pm)
        if projected_matches: projected[rnd] = projected_matches
    all_display_rounds = sorted(set(list(bracket.keys()) + list(projected.keys())))
    return projected, all_display_rounds


def _bracket_advice(player_count):
    if player_count < 2: return {'type':'error','msg':'Need at least 2 players.','suggestions':[]}
    lower_pow2 = 1
    while lower_pow2 * 2 <= player_count: lower_pow2 *= 2
    upper_pow2 = lower_pow2 * 2
    byes_needed = upper_pow2 - player_count
    bye_pct = (byes_needed / upper_pow2) * 100
    is_power_of_2 = (player_count & (player_count - 1) == 0) and player_count > 0
    suggestions = []; warnings = []; recommended = 'single_elimination'
    if is_power_of_2:
        suggestions.append({'type':'perfect','icon':'✅','title':'Perfect Bracket',
            'desc':f'{player_count} players fits perfectly into a single elimination bracket with {int(math.log2(player_count))} rounds.','action':None})
    else:
        suggestions.append({'type':'byes','icon':'📋','title':f'Standard Bracket ({upper_pow2}-slot)',
            'desc':f'{byes_needed} bye{"s" if byes_needed != 1 else ""} needed ({bye_pct:.0f}% empty slots). Top {byes_needed} seed{"s" if byes_needed != 1 else ""} advance automatically to round 2.','action':'standard'})
        play_in_matches = player_count - lower_pow2
        play_in_players = play_in_matches * 2
        auto_advance = player_count - play_in_players
        suggestions.append({'type':'play_in','icon':'🎮','title':f'Play-In Round + {lower_pow2}-Bracket',
            'desc':f'{play_in_matches} play-in match{"es" if play_in_matches != 1 else ""}: bottom {play_in_players} seeds play, {play_in_matches} winner{"s" if play_in_matches != 1 else ""} join top {auto_advance} seeds in a clean {lower_pow2}-player bracket.','action':'play_in'})
        if player_count <= 10:
            total_matches = player_count * (player_count - 1) // 2
            suggestions.append({'type':'round_robin','icon':'🔄','title':'Round Robin',
                'desc':f'Everyone plays everyone: {total_matches} total matches. Fairest format, no byes. Best for {player_count} players or fewer.','action':'round_robin'})
        if player_count >= 6:
            if player_count <= 8: groups = 2; per_group = math.ceil(player_count / 2)
            elif player_count <= 16: groups = 4; per_group = math.ceil(player_count / 4)
            else: groups = min(8, player_count // 3); per_group = math.ceil(player_count / groups)
            advance_per_group = 2; knockout_size = groups * advance_per_group
            suggestions.append({'type':'groups','icon':'🏟️','title':f'Group Stage ({groups} groups) + Knockout',
                'desc':f'{groups} groups of ~{per_group} players, round robin within groups. Top {advance_per_group} from each group advance to a {knockout_size}-player knockout bracket.','action':'groups'})
        if player_count >= 5:
            swiss_rounds = max(3, math.ceil(math.log2(player_count)))
            suggestions.append({'type':'swiss','icon':'🇨🇭','title':f'Swiss System ({swiss_rounds} rounds)',
                'desc':f'{swiss_rounds} rounds where players are matched against opponents with similar records. No eliminations — everyone plays all rounds. Top players by record advance or win.','action':'swiss'})
        if bye_pct > 40: warnings.append(f'⚠️ High bye percentage ({bye_pct:.0f}%). Consider a play-in round or different format.')
        if player_count % 2 != 0: warnings.append(f'⚠️ Odd number of players ({player_count}). One player will always have a bye in any round.')
        need_more = upper_pow2 - player_count; need_less = player_count - lower_pow2
        if need_more <= 2: warnings.append(f'💡 Only {need_more} more player{"s" if need_more != 1 else ""} needed for a perfect {upper_pow2}-player bracket.')
        if need_less <= 2 and lower_pow2 >= 4: warnings.append(f'💡 Removing {need_less} player{"s" if need_less != 1 else ""} would give a perfect {lower_pow2}-player bracket.')
    return {'player_count':player_count,'is_power_of_2':is_power_of_2,'upper_pow2':upper_pow2,'lower_pow2':lower_pow2,
            'byes_needed':byes_needed,'bye_pct':bye_pct,'suggestions':suggestions,'warnings':warnings,'recommended':recommended}

# ===========================================================================
# BETS
# ===========================================================================
def _resolve_bets(match):
    active_bets=match.bets.filter_by(status='active').all()
    if not active_bets: return
    now=datetime.now(timezone.utc)
    if not match.winner_id:
        for b in active_bets:
            _award_points(b.user_id, b.amount, f'Bet refund: match #{match.id} draw')
            b.status='refunded'; b.resolved_at=now
        return
    total_pool=sum(b.amount for b in active_bets)
    winner_pool=sum(b.amount for b in active_bets if b.predicted_winner_id==match.winner_id)
    if winner_pool==0:
        for b in active_bets:
            _award_points(b.user_id, b.amount, f'Bet refund: no winners match #{match.id}')
            b.status='refunded'; b.resolved_at=now
        return
    for b in active_bets:
        if b.predicted_winner_id==match.winner_id:
            payout=int((b.amount/winner_pool)*total_pool)
            b.payout=payout; b.status='won'; b.resolved_at=now
            _award_points(b.user_id, payout, f'Bet won: match #{match.id}')
        else: b.status='lost'; b.resolved_at=now

def _refund_match_bets(match):
    now=datetime.now(timezone.utc)
    for b in match.bets.filter_by(status='active').all():
        _award_points(b.user_id, b.amount, f'Bet refund: match #{match.id} cancelled')
        b.status='refunded'; b.resolved_at=now
    if match.stake and match.stake > 0:
        _award_points(match.p1_id, match.stake, f'Challenge stake refund: match #{match.id} cancelled')
        _award_points(match.p2_id, match.stake, f'Challenge stake refund: match #{match.id} cancelled')


# ===========================================================================
# VERIFICATION TIMEOUT
# ===========================================================================
def _check_verification_timeouts():
    """Auto-verify pending matches that have exceeded their verification timeout.

    For tournament matches: uses tourney.verify_timeout_days.
    For non-tournament matches: uses global default_verify_timeout_days from AppSetting.
    Timeout of 0 means disabled (no auto-verify).
    """
    from models import Match, Tournament, AppSetting
    try:
        now = datetime.now(timezone.utc)
        # Get global default for non-tournament matches
        global_setting = AppSetting.query.filter_by(key='default_verify_timeout_days').first()
        global_timeout = int(global_setting.value) if global_setting and global_setting.value else 0

        pending = Match.query.filter_by(state='pending').all()
        for m in pending:
            timeout_days = 0
            if m.tourney_id:
                t = db.session.get(Tournament, m.tourney_id)
                if t:
                    timeout_days = t.verify_timeout_days or 0
            else:
                timeout_days = global_timeout

            if timeout_days <= 0:
                continue

            # SQLite stores naive datetimes; ensure comparison is consistent
            played = m.played_at
            if played and played.tzinfo is not None:
                now_cmp = now
            else:
                now_cmp = now.replace(tzinfo=None)

            threshold = played + timedelta(days=timeout_days)
            if now_cmp < threshold:
                continue

            # Auto-verify this match
            m.state = 'verified'
            m.verify_by = None
            _ok()

            if m.ranked:
                _proc_r(m)
            else:
                _proc_u(m)
            _resolve_bets(m)

            if m.tourney_id:
                t = db.session.get(Tournament, m.tourney_id)
                if t:
                    _check_tourney_completion(t)

            _alert(m.p1_id, '⏰ Match Auto-Verified',
                   f'Match #{m.id} was auto-verified after {timeout_days} day(s) timeout.',
                   'info', url_for('matches.match_view', mid=m.id))
            _alert(m.p2_id, '⏰ Match Auto-Verified',
                   f'Match #{m.id} was auto-verified after {timeout_days} day(s) timeout.',
                   'info', url_for('matches.match_view', mid=m.id))
            _ok()

            log.info(f"[TIMEOUT] Auto-verified match #{m.id} after {timeout_days} day(s)")
    except Exception as e:
        log.error(f"[TIMEOUT] Error checking verification timeouts: {e}")


# ===========================================================================
# DATABASE BACKUP & ROLLBACK
# ===========================================================================
import shutil
import sqlite3 as _sqlite3

_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tournament_manager.db')
_MAX_BACKUPS = 20


def _create_backup():
    """Copy the active DB to backups/backup_YYYYMMDD_HHMMSS.db.
    Enforces a 20-backup limit by deleting the oldest if needed.
    Returns the filename on success, None on failure."""
    try:
        os.makedirs(_BACKUP_DIR, exist_ok=True)
        existing = _list_backups()
        while len(existing) >= _MAX_BACKUPS:
            oldest = existing[-1]  # list is sorted desc, so last is oldest
            _delete_backup(oldest['filename'])
            existing = _list_backups()
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        fname = f'backup_{ts}.db'
        dest = os.path.join(_BACKUP_DIR, fname)
        shutil.copy2(_DB_PATH, dest)
        log.info(f"[BACKUP] Created backup: {fname}")
        return fname
    except Exception as e:
        log.error(f"[BACKUP] Failed to create backup: {e}")
        return None


def _list_backups():
    """Return list of dicts {filename, created_at, size_bytes} sorted by created_at desc."""
    result = []
    if not os.path.isdir(_BACKUP_DIR):
        return result
    pattern = re.compile(r'^backup_(\d{8}_\d{6})\.db$')
    for fname in os.listdir(_BACKUP_DIR):
        m = pattern.match(fname)
        if not m:
            continue
        ts_str = m.group(1)
        try:
            created = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
        except ValueError:
            continue
        fpath = os.path.join(_BACKUP_DIR, fname)
        try:
            size = os.path.getsize(fpath)
        except OSError:
            size = 0
        result.append({'filename': fname, 'created_at': created, 'size_bytes': size})
    result.sort(key=lambda x: x['created_at'], reverse=True)
    return result


def _restore_backup(filename):
    """Restore a backup over the active DB.
    Validates filename, checks file exists and is valid SQLite.
    Creates a pre-rollback backup first.
    Returns True on success, False on failure."""
    # Validate filename — no path traversal
    if not re.match(r'^backup_\d{8}_\d{6}\.db$', filename):
        log.error(f"[BACKUP] Invalid backup filename: {filename}")
        return False
    src = os.path.join(_BACKUP_DIR, filename)
    if not os.path.isfile(src):
        log.error(f"[BACKUP] Backup file not found: {filename}")
        return False
    # Verify it's a valid SQLite database
    try:
        conn = _sqlite3.connect(src)
        conn.execute('SELECT 1')
        conn.close()
    except Exception:
        log.error(f"[BACKUP] Backup is not a valid SQLite DB: {filename}")
        return False
    # Create pre-rollback backup
    try:
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        pre_fname = f'backup_{ts}.db'
        pre_dest = os.path.join(_BACKUP_DIR, pre_fname)
        shutil.copy2(_DB_PATH, pre_dest)
        log.info(f"[BACKUP] Pre-rollback backup created: {pre_fname}")
    except Exception as e:
        log.error(f"[BACKUP] Failed to create pre-rollback backup: {e}")
        return False
    # Dispose engine, copy backup over active DB, reconnect
    try:
        db.engine.dispose()
        shutil.copy2(src, _DB_PATH)
        log.info(f"[BACKUP] Restored backup: {filename}")
        return True
    except Exception as e:
        log.error(f"[BACKUP] Failed to restore backup: {e}")
        return False


def _delete_backup(filename):
    """Delete a backup file. Returns True on success, False on failure."""
    if not re.match(r'^backup_\d{8}_\d{6}\.db$', filename):
        log.error(f"[BACKUP] Invalid backup filename for delete: {filename}")
        return False
    fpath = os.path.join(_BACKUP_DIR, filename)
    if not os.path.isfile(fpath):
        log.error(f"[BACKUP] Backup file not found for delete: {filename}")
        return False
    try:
        os.remove(fpath)
        log.info(f"[BACKUP] Deleted backup: {filename}")
        return True
    except Exception as e:
        log.error(f"[BACKUP] Failed to delete backup: {e}")
        return False

# ===========================================================================
# CHAT HELPERS
# ===========================================================================

def is_chat_muted(user):
    if not user.chat_muted_until:
        return False
    return user.chat_muted_until > datetime.now(timezone.utc)


def _get_user_chat_cosmetics(user_id):
    from models import UserCosmetic, CosmeticItem
    rows = UserCosmetic.query.filter_by(user_id=user_id, equipped=True).all()
    result = {'chat_flair': None, 'name_color': None}
    for uc in rows:
        if uc.item.category in ('chat_flair', 'name_color'):
            result[uc.item.category] = uc.item.css_data
    return result


def _serialize_chat_message(msg):
    cosmetics = _get_user_chat_cosmetics(msg.user_id)
    now = datetime.now(timezone.utc)
    ca = msg.created_at
    if ca.tzinfo is None:
        ca = ca.replace(tzinfo=timezone.utc)
    diff = (now - ca).total_seconds()
    if diff < 60: rel = f"{int(diff)}s ago"
    elif diff < 3600: rel = f"{int(diff//60)}m ago"
    elif diff < 86400: rel = f"{int(diff//3600)}h ago"
    else: rel = f"{int(diff//86400)}d ago"
    return {
        'id': msg.id,
        'content': msg.content,
        'user_id': msg.user_id,
        'display_name': msg.author.display_name or msg.author.username,
        'avatar': msg.author.avatar,
        'flair_css': cosmetics.get('chat_flair'),
        'name_color_css': cosmetics.get('name_color'),
        'created_at': rel,
        'ts_iso': ca.isoformat(),
        'is_admin': msg.author.admin
    }


def _serialize_dm_message(msg):
    from models import DMMessage
    cosmetics = _get_user_chat_cosmetics(msg.sender_id)
    now = datetime.now(timezone.utc)
    ca = msg.created_at
    if ca.tzinfo is None:
        ca = ca.replace(tzinfo=timezone.utc)
    diff = (now - ca).total_seconds()
    if diff < 60: rel = f"{int(diff)}s ago"
    elif diff < 3600: rel = f"{int(diff//60)}m ago"
    elif diff < 86400: rel = f"{int(diff//3600)}h ago"
    else: rel = f"{int(diff//86400)}d ago"
    return {
        'id': msg.id,
        'content': msg.content,
        'user_id': msg.sender_id,
        'display_name': msg.sender.display_name or msg.sender.username,
        'avatar': msg.sender.avatar,
        'flair_css': cosmetics.get('chat_flair'),
        'name_color_css': cosmetics.get('name_color'),
        'created_at': rel,
        'ts_iso': ca.isoformat(),
        'is_admin': msg.sender.admin
    }

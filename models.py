"""SQLAlchemy models and association tables for Tournament Manager V10."""
import secrets, math
from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy.orm import relationship
from sqlalchemy import and_
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db, app

# ===========================================================================
# ASSOCIATION TABLES
# ===========================================================================
clan_members = db.Table('clan_members',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('clan_id', db.Integer, db.ForeignKey('clans.id'), primary_key=True),
    db.Column('joined_at', db.DateTime, default=lambda: datetime.now(timezone.utc)),
    db.Column('role', db.String(32), default='member'))

tourney_players = db.Table('tourney_players',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('tournament_id', db.Integer, db.ForeignKey('tournaments.id'), primary_key=True),
    db.Column('registered_at', db.DateTime, default=lambda: datetime.now(timezone.utc)))

user_achs = db.Table('user_achs',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('ach_id', db.Integer, db.ForeignKey('achievements.id'), primary_key=True),
    db.Column('awarded_at', db.DateTime, default=lambda: datetime.now(timezone.utc)))

# Alias for query convenience
TourneyPlayer = tourney_players

# ===========================================================================
# USER
# ===========================================================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id=db.Column(db.Integer, primary_key=True)
    username=db.Column(db.String(64), unique=True, nullable=False, index=True)
    email=db.Column(db.String(120), unique=True, nullable=False)
    pw_hash=db.Column(db.String(256), nullable=False)
    display_name=db.Column(db.String(64))
    bio=db.Column(db.Text)
    avatar=db.Column(db.String(256))
    admin=db.Column(db.Boolean, nullable=False, default=False)
    banned=db.Column(db.Boolean, nullable=False, default=False)
    ban_reason=db.Column(db.String(256))
    theme=db.Column(db.String(16), nullable=False, default='dark')
    created_at=db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen=db.Column(db.DateTime)
    elo=db.Column(db.Integer, nullable=False, default=1200)
    elo_matches=db.Column(db.Integer, nullable=False, default=0)
    r_wins=db.Column(db.Integer, nullable=False, default=0)
    r_losses=db.Column(db.Integer, nullable=False, default=0)
    r_draws=db.Column(db.Integer, nullable=False, default=0)
    u_wins=db.Column(db.Integer, nullable=False, default=0)
    u_losses=db.Column(db.Integer, nullable=False, default=0)
    u_draws=db.Column(db.Integer, nullable=False, default=0)
    streak=db.Column(db.Integer, nullable=False, default=0)
    best_streak=db.Column(db.Integer, nullable=False, default=0)
    session_token=db.Column(db.String(64), default=lambda: secrets.token_hex(32))
    profile_color=db.Column(db.String(7),default='#6c5ce7')
    featured_ach_id=db.Column(db.Integer,db.ForeignKey('achievements.id'))
    featured_ach=relationship('Achievement',foreign_keys='User.featured_ach_id')
    title=db.Column(db.String(64))
    country=db.Column(db.String(2))
    country_name=db.Column(db.String(64))
    points=db.Column(db.Integer,nullable=False,default=0)
    last_login_bonus=db.Column(db.Date,nullable=True)
    font_size=db.Column(db.String(16),nullable=False,default='medium')
    navbar_position=db.Column(db.String(16),nullable=False,default='top')
    showcase_config=db.Column(db.Text,nullable=True)
    chat_muted_until=db.Column(db.DateTime,nullable=True)
    alerts=relationship('Alert', backref='user', lazy='dynamic', cascade='all,delete-orphan')
    news_posts=relationship('News', backref='author', lazy='dynamic')
    elo_hist=relationship('EloSnap', backref='user', lazy='dynamic', cascade='all,delete-orphan')
    trophies=relationship('Achievement', secondary=user_achs,
        backref=db.backref('holders', lazy='dynamic'), lazy='dynamic')
    ch_sent=relationship('Challenge', foreign_keys='Challenge.from_id', backref='sender', lazy='dynamic')
    ch_recv=relationship('Challenge', foreign_keys='Challenge.to_id', backref='receiver', lazy='dynamic')
    @property
    def is_active(self): return not self.banned
    def get_id(self):
        return f"{self.id}|{self.session_token or ''}"
    def set_pw(self, p): self.pw_hash = generate_password_hash(p)
    def check_pw(self, p): return check_password_hash(self.pw_hash, p)
    def rotate_session(self):
        self.session_token = secrets.token_hex(32)
    @property
    def rank_title(self):
        if self.elo_matches < app.config['PLACEMENT']: return 'Undetermined'
        e=self.elo
        if e>=2400: return 'Global Elite'
        if e>=2200: return 'Supreme'
        if e>=2000: return 'Legendary Eagle Master'
        if e>=1800: return 'Legendary Eagle'
        if e>=1600: return 'Distinguished Master Guardian'
        if e>=1500: return 'Master Guardian Elite'
        if e>=1400: return 'Master Guardian'
        if e>=1300: return 'Gold Nova Master'
        if e>=1200: return 'Gold Nova'
        if e>=1100: return 'Silver Elite Master'
        if e>=1000: return 'Bronze'
        if e>=900: return 'Bronze Initiate'
        if e>=800: return 'Wood'
        if e>=700: return 'Wood Plank'
        if e>=600: return 'Twig'
        return 'Here for the Laughs'
    @property
    def placement_left(self): return max(0, app.config['PLACEMENT']-self.elo_matches)
    @property
    def is_placement(self): return self.elo_matches < app.config['PLACEMENT']
    @property
    def rank_color(self):
        m={'Undetermined':'#888',
           'Here for the Laughs':'#ff69b4','Twig':'#8B4513','Wood Plank':'#a0522d','Wood':'#b8860b',
           'Bronze Initiate':'#cd7f32','Bronze':'#cd8932','Silver Elite Master':'#aaa',
           'Gold Nova':'#ffd700','Gold Nova Master':'#f0c800','Master Guardian':'#00b894',
           'Master Guardian Elite':'#00a88a','Distinguished Master Guardian':'#00cec9',
           'Legendary Eagle':'#6c5ce7','Legendary Eagle Master':'#a29bfe',
           'Supreme':'#e17055','Global Elite':'#ff1744'}
        return m.get(self.rank_title,'#888')
    @property
    def total_ranked(self): return self.r_wins+self.r_losses+self.r_draws
    @property
    def total_unranked(self): return self.u_wins+self.u_losses+self.u_draws
    @property
    def total_matches(self): return self.total_ranked+self.total_unranked
    @property
    def ranked_wr(self):
        t=self.total_ranked; return round(self.r_wins/t*100,1) if t else 0.0
    @property
    def unranked_wr(self):
        t=self.total_unranked; return round(self.u_wins/t*100,1) if t else 0.0
    def name(self): return self.display_name or self.username
    def get_clan(self):
        try: return self.clans.first()
        except Exception: return None
    def get_clan_role(self, clan_id):
        try:
            row=db.session.execute(clan_members.select().where(
                and_(clan_members.c.user_id==self.id,clan_members.c.clan_id==clan_id))).first()
            return row.role if row else None
        except Exception: return None


# ===========================================================================
# OTHER MODELS
# ===========================================================================
class EloSnap(db.Model):
    __tablename__='elo_snaps'
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    elo_val=db.Column(db.Integer,nullable=False)
    ts=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'))

class Clan(db.Model):
    __tablename__='clans'
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(64),unique=True,nullable=False)
    tag=db.Column(db.String(4),unique=True,nullable=False)
    description=db.Column(db.Text)
    logo=db.Column(db.String(256))
    bg_image=db.Column(db.String(256))
    color_primary=db.Column(db.String(7),default='#6c5ce7')
    color_secondary=db.Column(db.String(7),default='#1e1e2e')
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    active=db.Column(db.Boolean,nullable=False,default=True)
    recruiting=db.Column(db.Boolean,nullable=False,default=True)
    invite_only=db.Column(db.Boolean,nullable=False,default=False)
    max_members=db.Column(db.Integer,nullable=False,default=50)
    owner_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    score=db.Column(db.Integer,nullable=False,default=0)
    treasury=db.Column(db.Integer,nullable=False,default=0)
    owner=relationship('User',foreign_keys=[owner_id],backref='owned_clan')
    members=relationship('User',secondary=clan_members,
        backref=db.backref('clans',lazy='dynamic'),lazy='dynamic')
    @property
    def member_count(self): return self.members.count()
    @property
    def avg_elo(self):
        ml=self.members.all(); return int(sum(m.elo for m in ml)/len(ml)) if ml else 1200

class ClanInvite(db.Model):
    __tablename__='clan_invites'
    id=db.Column(db.Integer,primary_key=True)
    clan_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=False)
    from_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    to_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    state=db.Column(db.String(32),nullable=False,default='pending')
    message=db.Column(db.String(256))
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    clan=relationship('Clan',backref=db.backref('invites',lazy='dynamic'))
    sender=relationship('User',foreign_keys=[from_id],backref='sent_clan_invites')
    receiver=relationship('User',foreign_keys=[to_id],backref='recv_clan_invites')

class ClanMessage(db.Model):
    __tablename__='clan_messages'
    id=db.Column(db.Integer,primary_key=True)
    clan_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    content=db.Column(db.Text,nullable=False)
    pinned=db.Column(db.Boolean,nullable=False,default=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    clan=relationship('Clan',backref=db.backref('messages',lazy='dynamic'))
    author=relationship('User',backref='clan_messages')

class PointTransaction(db.Model):
    __tablename__='point_transactions'
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    amount=db.Column(db.Integer,nullable=False)
    reason=db.Column(db.String(256),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    user=relationship('User',backref=db.backref('point_transactions',lazy='dynamic'))

class CosmeticItem(db.Model):
    __tablename__='cosmetic_items'
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(64),nullable=False)
    description=db.Column(db.String(256))
    category=db.Column(db.String(32),nullable=False)
    price=db.Column(db.Integer,nullable=False,default=0)
    rarity=db.Column(db.String(16),nullable=False,default='common')
    effect_type=db.Column(db.String(16),nullable=False,default='none')
    effect_mode=db.Column(db.String(16),nullable=False,default='css')
    css_data=db.Column(db.String(512))
    image=db.Column(db.String(256))
    active=db.Column(db.Boolean,nullable=False,default=True)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))

class UserCosmetic(db.Model):
    __tablename__='user_cosmetics'
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    item_id=db.Column(db.Integer,db.ForeignKey('cosmetic_items.id'),nullable=False)
    equipped=db.Column(db.Boolean,nullable=False,default=False)
    purchased_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    __table_args__=(db.UniqueConstraint('user_id','item_id',name='uq_user_cosmetic'),)
    user=relationship('User',backref=db.backref('cosmetics',lazy='dynamic'))
    item=relationship('CosmeticItem',backref='owners')

class Bet(db.Model):
    __tablename__='bets'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    predicted_winner_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    amount=db.Column(db.Integer,nullable=False)
    payout=db.Column(db.Integer,default=0)
    status=db.Column(db.String(16),nullable=False,default='active')
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    resolved_at=db.Column(db.DateTime)
    match=relationship('Match',backref=db.backref('bets',lazy='dynamic'))
    user=relationship('User',foreign_keys=[user_id],backref=db.backref('bets',lazy='dynamic'))
    predicted_winner=relationship('User',foreign_keys=[predicted_winner_id])

class MatchGame(db.Model):
    __tablename__='match_games'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    game_number=db.Column(db.Integer,nullable=False)
    p1_score=db.Column(db.Integer,nullable=False,default=0)
    p2_score=db.Column(db.Integer,nullable=False,default=0)
    winner_id=db.Column(db.Integer,db.ForeignKey('users.id'))
    match=relationship('Match',backref=db.backref('games',lazy='dynamic',order_by='MatchGame.game_number'))
    winner=relationship('User',foreign_keys=[winner_id])
    __table_args__=(db.UniqueConstraint('match_id','game_number',name='uq_match_game'),)

class MatchPrediction(db.Model):
    __tablename__='match_predictions'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    predicted_winner_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    correct=db.Column(db.Boolean,nullable=True,default=None)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    match=relationship('Match',backref=db.backref('predictions',lazy='dynamic'))
    user=relationship('User',foreign_keys=[user_id],backref=db.backref('predictions',lazy='dynamic'))
    predicted_winner=relationship('User',foreign_keys=[predicted_winner_id])
    __table_args__=(db.UniqueConstraint('match_id','user_id',name='uq_match_prediction'),)

class Endorsement(db.Model):
    __tablename__='endorsements'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    from_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    to_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    category=db.Column(db.String(32),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    match=relationship('Match',backref=db.backref('endorsements',lazy='dynamic'))
    from_user=relationship('User',foreign_keys=[from_id],backref=db.backref('endorsements_given',lazy='dynamic'))
    to_user=relationship('User',foreign_keys=[to_id],backref=db.backref('endorsements_received',lazy='dynamic'))
    __table_args__=(db.UniqueConstraint('match_id','from_id',name='uq_endorsement_per_match'),)

class ClanWar(db.Model):
    __tablename__='clan_wars'
    id=db.Column(db.Integer,primary_key=True)
    clan1_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=False)
    clan2_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=False)
    status=db.Column(db.String(32),nullable=False,default='pending')
    match_count=db.Column(db.Integer,nullable=False,default=5)
    clan1_wins=db.Column(db.Integer,nullable=False,default=0)
    clan2_wins=db.Column(db.Integer,nullable=False,default=0)
    winner_clan_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=True)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    completed_at=db.Column(db.DateTime,nullable=True)
    clan1=relationship('Clan',foreign_keys=[clan1_id],backref=db.backref('wars_initiated',lazy='dynamic'))
    clan2=relationship('Clan',foreign_keys=[clan2_id],backref=db.backref('wars_received',lazy='dynamic'))
    winner=relationship('Clan',foreign_keys=[winner_clan_id])

class ClanWarMatch(db.Model):
    __tablename__='clan_war_matches'
    id=db.Column(db.Integer,primary_key=True)
    war_id=db.Column(db.Integer,db.ForeignKey('clan_wars.id'),nullable=False)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=True)
    slot_number=db.Column(db.Integer,nullable=False)
    clan1_player_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=True)
    clan2_player_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=True)
    war=relationship('ClanWar',backref=db.backref('war_matches',lazy='dynamic'))
    match=relationship('Match',backref='clan_war_match')
    clan1_player=relationship('User',foreign_keys=[clan1_player_id])
    clan2_player=relationship('User',foreign_keys=[clan2_player_id])

class ClanAchievement(db.Model):
    __tablename__='clan_achievements'
    id=db.Column(db.Integer,primary_key=True)
    clan_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=False)
    achievement_type=db.Column(db.String(32),nullable=False)
    awarded_at=db.Column(db.DateTime,nullable=False,default=datetime.now(timezone.utc))
    clan=relationship('Clan',backref=db.backref('clan_achievements',lazy='dynamic'))
    __table_args__=(db.UniqueConstraint('clan_id','achievement_type',name='uq_clan_achievement'),)

class CustomClanAchievementType(db.Model):
    __tablename__='custom_clan_achievement_types'
    id=db.Column(db.Integer,primary_key=True)
    key=db.Column(db.String(64),unique=True,nullable=False)
    name=db.Column(db.String(128),nullable=False)
    icon=db.Column(db.String(64),nullable=False,default='fas fa-award')
    image=db.Column(db.String(256),default=None)
    description=db.Column(db.String(256),default='')
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))

class MVPVote(db.Model):
    __tablename__='mvp_votes'
    id=db.Column(db.Integer,primary_key=True)
    voter_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    candidate_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    period_type=db.Column(db.String(16),nullable=False)
    period_key=db.Column(db.String(16),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=datetime.now(timezone.utc))
    voter=relationship('User',foreign_keys=[voter_id],backref=db.backref('mvp_votes_cast',lazy='dynamic'))
    candidate=relationship('User',foreign_keys=[candidate_id],backref=db.backref('mvp_votes_received',lazy='dynamic'))
    __table_args__=(db.UniqueConstraint('voter_id','period_type','period_key',name='uq_mvp_vote'),)

class MatchComment(db.Model):
    __tablename__='match_comments'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    content=db.Column(db.String(280),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=datetime.now(timezone.utc))
    match=relationship('Match',backref=db.backref('comments',lazy='dynamic'))
    author=relationship('User',backref=db.backref('match_comments',lazy='dynamic'))

class Tournament(db.Model):
    __tablename__='tournaments'
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(128),nullable=False)
    description=db.Column(db.Text)
    game=db.Column(db.String(64))
    fmt=db.Column(db.String(32),nullable=False,default='single_elimination')
    status=db.Column(db.String(32),nullable=False,default='upcoming')
    max_players=db.Column(db.Integer,nullable=False,default=32)
    prize=db.Column(db.String(128))
    rules=db.Column(db.Text)
    start_dt=db.Column(db.DateTime)
    end_dt=db.Column(db.DateTime)
    reg_deadline=db.Column(db.DateTime)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    created_by=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    ranked=db.Column(db.Boolean,nullable=False,default=True)
    bracket_generated=db.Column(db.Boolean,nullable=False,default=False)
    current_round=db.Column(db.Integer,nullable=False,default=0)
    banner_image=db.Column(db.String(256))
    logo=db.Column(db.String(256))
    color_primary=db.Column(db.String(7),default='#6c5ce7')
    color_secondary=db.Column(db.String(7),default='#1e1e2e')
    seeding_mode=db.Column(db.String(32),default='elo')
    default_series=db.Column(db.String(8),nullable=False,default='bo1')
    verify_timeout_days=db.Column(db.Integer,nullable=False,default=0)
    creator=relationship('User',foreign_keys=[created_by],backref='made_tourneys')
    players=relationship('User',secondary=tourney_players,
        backref=db.backref('tourneys',lazy='dynamic'),lazy='dynamic')
    matches=relationship('Match',backref='tournament',lazy='dynamic')
    @property
    def player_count(self): return self.players.count()
    @property
    def is_full(self): return self.player_count>=self.max_players
    @property
    def reg_open(self):
        if self.status!='upcoming': return False
        if self.reg_deadline and datetime.now(timezone.utc)>self.reg_deadline: return False
        return not self.is_full
    @property
    def total_rounds(self):
        max_round = db.session.query(db.func.max(Match.round_num)).filter(
            Match.tourney_id==self.id, Match.round_num > 0).scalar()
        pc = self.player_count
        if pc < 2: return max_round or 0
        lower_pow2 = 1
        while lower_pow2 * 2 <= pc: lower_pow2 *= 2
        is_pow2 = (pc & (pc - 1) == 0) and pc > 0
        has_play_in = self.matches.filter_by(round_num=0).count() > 0
        if has_play_in: expected = int(math.log2(lower_pow2))
        elif is_pow2: expected = int(math.log2(pc))
        else:
            upper_pow2 = lower_pow2 * 2
            expected = int(math.log2(upper_pow2))
        if max_round is not None and max_round > 0:
            return max(max_round, expected)
        return expected
    def round_name(self, rnd):
        if rnd == 0: return 'Play-In'
        if self.fmt == 'round_robin': return f'Round {rnd}'
        tr=self.total_rounds
        if tr == 0: return f'Round {rnd}'
        if rnd==tr: return 'Final'
        if rnd==tr-1 and tr>1: return 'Semi-Final'
        if rnd==tr-2 and tr>2: return 'Quarter-Final'
        return f'Round {rnd}'


class Match(db.Model):
    __tablename__='matches'
    id=db.Column(db.Integer,primary_key=True)
    tourney_id=db.Column(db.Integer,db.ForeignKey('tournaments.id'))
    p1_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    p2_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    p1_score=db.Column(db.Integer,nullable=False,default=0)
    p2_score=db.Column(db.Integer,nullable=False,default=0)
    p1_total_points=db.Column(db.Integer,nullable=False,default=0)
    p2_total_points=db.Column(db.Integer,nullable=False,default=0)
    winner_id=db.Column(db.Integer,db.ForeignKey('users.id'))
    draw=db.Column(db.Boolean,nullable=False,default=False)
    ranked=db.Column(db.Boolean,nullable=False,default=True)
    elo_d1=db.Column(db.Integer,nullable=False,default=0)
    elo_d2=db.Column(db.Integer,nullable=False,default=0)
    round_num=db.Column(db.Integer)
    bracket_pos=db.Column(db.Integer)
    played_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    notes=db.Column(db.Text)
    winner_comment=db.Column(db.Text)
    state=db.Column(db.String(32),nullable=False,default='verified')
    submit_by=db.Column(db.Integer,db.ForeignKey('users.id'))
    verify_by=db.Column(db.Integer,db.ForeignKey('users.id'))
    challenge_id=db.Column(db.Integer,db.ForeignKey('challenges.id'))
    proof_image=db.Column(db.String(256))
    counter_p1=db.Column(db.Integer)
    counter_p2=db.Column(db.Integer)
    counter_by=db.Column(db.Integer,db.ForeignKey('users.id'))
    stake=db.Column(db.Integer,nullable=False,default=0)
    series_format=db.Column(db.String(8),nullable=False,default='bo1')
    scheduled_at=db.Column(db.DateTime,nullable=True)
    p1=relationship('User',foreign_keys=[p1_id],backref='m_as_p1')
    p2=relationship('User',foreign_keys=[p2_id],backref='m_as_p2')
    winner=relationship('User',foreign_keys=[winner_id])
    submitter=relationship('User',foreign_keys=[submit_by])
    verifier=relationship('User',foreign_keys=[verify_by])
    counter_user=relationship('User',foreign_keys=[counter_by])

class Challenge(db.Model):
    __tablename__='challenges'
    id=db.Column(db.Integer,primary_key=True)
    from_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    to_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    when=db.Column(db.DateTime,nullable=False)
    msg=db.Column(db.String(256))
    state=db.Column(db.String(32),nullable=False,default='pending')
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'))
    news_id=db.Column(db.Integer)
    ranked=db.Column(db.Boolean,nullable=False,default=False)
    stake=db.Column(db.Integer,nullable=False,default=0)
    series_format=db.Column(db.String(8),nullable=False,default='bo1')
    match=relationship('Match',foreign_keys=[match_id],backref='from_challenge')

class News(db.Model):
    __tablename__='news'
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(200),nullable=False)
    slug=db.Column(db.String(220),unique=True,nullable=False,index=True)
    summary=db.Column(db.String(500))
    content=db.Column(db.Text,nullable=False)
    image=db.Column(db.String(256))
    category=db.Column(db.String(64),nullable=False,default='general')
    published=db.Column(db.Boolean,nullable=False,default=True)
    pinned=db.Column(db.Boolean,nullable=False,default=False)
    auto=db.Column(db.Boolean,nullable=False,default=False)
    views=db.Column(db.Integer,nullable=False,default=0)
    author_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    updated_at=db.Column(db.DateTime,default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
    def make_slug(self):
        import re, uuid
        b=re.sub(r'[^\w\s-]','',self.title.lower()); b=re.sub(r'[\s_]+','-',b).strip('-')
        self.slug=f"{b}-{uuid.uuid4().hex[:8]}"

class Alert(db.Model):
    __tablename__='alerts'
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    title=db.Column(db.String(128),nullable=False)
    message=db.Column(db.Text,nullable=False)
    cat=db.Column(db.String(32),nullable=False,default='info')
    read=db.Column(db.Boolean,nullable=False,default=False)
    link=db.Column(db.String(256))
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))

class GlobalAlert(db.Model):
    __tablename__='global_alerts'
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(128),nullable=False)
    message=db.Column(db.Text,nullable=False)
    cat=db.Column(db.String(32),nullable=False,default='info')
    link=db.Column(db.String(256))
    active=db.Column(db.Boolean,nullable=False,default=True)
    created_by=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    author=relationship('User',foreign_keys=[created_by])

class Achievement(db.Model):
    __tablename__='achievements'
    id=db.Column(db.Integer,primary_key=True)
    title=db.Column(db.String(128),nullable=False)
    description=db.Column(db.Text)
    image=db.Column(db.String(256))
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    created_by=db.Column(db.Integer,db.ForeignKey('users.id'))

class Audit(db.Model):
    __tablename__='audits'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    by_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    reason=db.Column(db.Text)
    state=db.Column(db.String(32),nullable=False,default='pending')
    resolved_by=db.Column(db.Integer,db.ForeignKey('users.id'))
    resolved_at=db.Column(db.DateTime)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    match=relationship('Match',backref='audits')
    disputer=relationship('User',foreign_keys=[by_id])
    resolver=relationship('User',foreign_keys=[resolved_by])

class Season(db.Model):
    __tablename__='seasons'
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(128),nullable=False)
    number=db.Column(db.Integer,nullable=False,default=1)
    started_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    ended_at=db.Column(db.DateTime)
    active=db.Column(db.Boolean,nullable=False,default=True)
    created_by=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    notes=db.Column(db.Text)
    creator=relationship('User',foreign_keys=[created_by])

class SeasonArchive(db.Model):
    __tablename__='season_archives'
    id=db.Column(db.Integer,primary_key=True)
    season_id=db.Column(db.Integer,db.ForeignKey('seasons.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    final_elo=db.Column(db.Integer,nullable=False)
    final_rank=db.Column(db.String(64),nullable=False)
    r_wins=db.Column(db.Integer,nullable=False,default=0)
    r_losses=db.Column(db.Integer,nullable=False,default=0)
    r_draws=db.Column(db.Integer,nullable=False,default=0)
    u_wins=db.Column(db.Integer,nullable=False,default=0)
    u_losses=db.Column(db.Integer,nullable=False,default=0)
    u_draws=db.Column(db.Integer,nullable=False,default=0)
    best_streak=db.Column(db.Integer,nullable=False,default=0)
    elo_matches=db.Column(db.Integer,nullable=False,default=0)
    leaderboard_pos=db.Column(db.Integer)
    season=relationship('Season',backref=db.backref('archives',lazy='dynamic'))
    user=relationship('User',backref=db.backref('season_history',lazy='dynamic'))

class Activity(db.Model):
    __tablename__='activities'
    id=db.Column(db.Integer,primary_key=True)
    type=db.Column(db.String(32),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'))
    target_id=db.Column(db.Integer)
    detail=db.Column(db.String(500))
    icon=db.Column(db.String(32),default='circle')
    color=db.Column(db.String(32),default='info')
    link=db.Column(db.String(256))
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    user=relationship('User',backref=db.backref('activities',lazy='dynamic'))

class MatchReaction(db.Model):
    __tablename__='match_reactions'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    emoji=db.Column(db.String(8),nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    match=relationship('Match',backref=db.backref('reactions',lazy='dynamic'))
    user=relationship('User')

class MatchSet(db.Model):
    __tablename__='match_sets'
    id=db.Column(db.Integer,primary_key=True)
    match_id=db.Column(db.Integer,db.ForeignKey('matches.id'),nullable=False)
    set_number=db.Column(db.Integer,nullable=False)
    p1_points=db.Column(db.Integer,nullable=False,default=0)
    p2_points=db.Column(db.Integer,nullable=False,default=0)
    winner_id=db.Column(db.Integer,db.ForeignKey('users.id'))
    match=relationship('Match',backref=db.backref('sets',lazy='dynamic',order_by='MatchSet.set_number'))
    winner=relationship('User',foreign_keys=[winner_id])
    __table_args__=(db.UniqueConstraint('match_id','set_number',name='uq_match_set'),)

class AppSetting(db.Model):
    __tablename__='app_settings'
    id=db.Column(db.Integer,primary_key=True)
    key=db.Column(db.String(128),unique=True,nullable=False,index=True)
    value=db.Column(db.String(512))

class ChatMessage(db.Model):
    __tablename__='chat_messages'
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    room_type=db.Column(db.String(16),nullable=False,index=True)
    clan_id=db.Column(db.Integer,db.ForeignKey('clans.id'),nullable=True)
    content=db.Column(db.Text,nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    author=relationship('User',backref='chat_messages_sent')
    clan=relationship('Clan',backref='chat_msgs')
    __table_args__=(db.Index('ix_chat_room_clan_id','room_type','clan_id','id'),)

class DMConversation(db.Model):
    __tablename__='dm_conversations'
    id=db.Column(db.Integer,primary_key=True)
    user1_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    user2_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    last_message_at=db.Column(db.DateTime,nullable=True)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    user1_last_read=db.Column(db.Integer,nullable=False,default=0)
    user2_last_read=db.Column(db.Integer,nullable=False,default=0)
    user1=relationship('User',foreign_keys=[user1_id])
    user2=relationship('User',foreign_keys=[user2_id])
    __table_args__=(db.UniqueConstraint('user1_id','user2_id',name='uq_dm_conversation_pair'),)

class DMMessage(db.Model):
    __tablename__='dm_messages'
    id=db.Column(db.Integer,primary_key=True)
    conversation_id=db.Column(db.Integer,db.ForeignKey('dm_conversations.id'),nullable=False)
    sender_id=db.Column(db.Integer,db.ForeignKey('users.id'),nullable=False)
    content=db.Column(db.Text,nullable=False)
    created_at=db.Column(db.DateTime,nullable=False,default=lambda: datetime.now(timezone.utc))
    conversation=relationship('DMConversation',backref=db.backref('messages',lazy='dynamic'))
    sender=relationship('User')
    __table_args__=(db.Index('ix_dm_msg_conv_id','conversation_id','id'),)

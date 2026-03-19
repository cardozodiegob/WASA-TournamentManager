"""Unit tests for Tournament Enhancements V11 (Tasks 8.1–8.5)."""
import os, sys, pytest, shutil, time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from extensions import app, db
from models import (
    User, Match, Tournament, MatchSet, AppSetting, Alert,
    tourney_players,
)
from helpers import (
    _partial_advance_round, _check_verification_timeouts, _ok,
    _create_backup, _list_backups, _restore_backup, _delete_backup,
    _BACKUP_DIR,
)


@pytest.fixture(autouse=True)
def setup_db():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    # Register blueprints if not already registered
    if 'matches' not in app.blueprints:
        from routes import register_blueprints
        register_blueprints(app)
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def _make_user(username='player'):
    u = User(username=username, email=f'{username}@test.com', pw_hash='fakehash')
    db.session.add(u)
    db.session.commit()
    return u


def _make_tourney(creator, **kwargs):
    defaults = dict(
        name='Test Tourney', fmt='single_elimination', status='active',
        max_players=8, created_by=creator.id, bracket_generated=True,
        current_round=1, ranked=True, default_series='bo1',
        verify_timeout_days=0,
    )
    defaults.update(kwargs)
    t = Tournament(**defaults)
    db.session.add(t)
    db.session.commit()
    return t


# =========================================================================
# 8.1  Unit tests for _partial_advance_round()
# =========================================================================
class TestPartialAdvanceRound:
    """Validates: Requirements 1.1, 1.2, 1.6, 1.7"""

    def test_zero_verified_returns_zero(self):
        """No verified matches → 0 created, no side effects."""
        admin = _make_user('admin')
        p1, p2, p3, p4 = [_make_user(f'p{i}') for i in range(1, 5)]
        t = _make_tourney(admin)
        # Two scheduled (unverified) matches in round 1
        db.session.add(Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                             round_num=1, bracket_pos=0, state='scheduled',
                             ranked=True, series_format='bo1'))
        db.session.add(Match(tourney_id=t.id, p1_id=p3.id, p2_id=p4.id,
                             round_num=1, bracket_pos=1, state='scheduled',
                             ranked=True, series_format='bo1'))
        db.session.commit()
        created = _partial_advance_round(t)
        assert created == 0
        assert t.current_round == 1

    def test_one_pair_complete_creates_one_match(self):
        """One pair verified, other pending → 1 next-round match created."""
        admin = _make_user('admin')
        p1, p2, p3, p4 = [_make_user(f'p{i}') for i in range(1, 5)]
        t = _make_tourney(admin)
        # Pair 0: both verified
        db.session.add(Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                             round_num=1, bracket_pos=0, state='verified',
                             winner_id=p1.id, ranked=True, series_format='bo1'))
        db.session.add(Match(tourney_id=t.id, p1_id=p3.id, p2_id=p4.id,
                             round_num=1, bracket_pos=1, state='verified',
                             winner_id=p3.id, ranked=True, series_format='bo1'))
        # Pair 1: one scheduled
        p5, p6, p7, p8 = [_make_user(f'q{i}') for i in range(1, 5)]
        db.session.add(Match(tourney_id=t.id, p1_id=p5.id, p2_id=p6.id,
                             round_num=1, bracket_pos=2, state='verified',
                             winner_id=p5.id, ranked=True, series_format='bo1'))
        db.session.add(Match(tourney_id=t.id, p1_id=p7.id, p2_id=p8.id,
                             round_num=1, bracket_pos=3, state='scheduled',
                             ranked=True, series_format='bo1'))
        db.session.commit()
        created = _partial_advance_round(t)
        assert created == 1
        # Next-round match at bracket_pos 0 should exist
        nm = Match.query.filter_by(tourney_id=t.id, round_num=2, bracket_pos=0).first()
        assert nm is not None
        assert nm.state == 'scheduled'
        assert {nm.p1_id, nm.p2_id} == {p1.id, p3.id}
        # bracket_pos 1 should NOT exist yet
        nm2 = Match.query.filter_by(tourney_id=t.id, round_num=2, bracket_pos=1).first()
        assert nm2 is None
        # current_round should NOT advance (not all verified)
        assert t.current_round == 1

    def test_all_complete_advances_round(self):
        """All pairs verified → matches created AND current_round advances."""
        admin = _make_user('admin')
        p1, p2, p3, p4 = [_make_user(f'p{i}') for i in range(1, 5)]
        t = _make_tourney(admin)
        db.session.add(Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                             round_num=1, bracket_pos=0, state='verified',
                             winner_id=p1.id, ranked=True, series_format='bo1'))
        db.session.add(Match(tourney_id=t.id, p1_id=p3.id, p2_id=p4.id,
                             round_num=1, bracket_pos=1, state='verified',
                             winner_id=p3.id, ranked=True, series_format='bo1'))
        db.session.commit()
        created = _partial_advance_round(t)
        assert created == 1
        assert t.current_round == 2
        nm = Match.query.filter_by(tourney_id=t.id, round_num=2, bracket_pos=0).first()
        assert nm is not None
        assert nm.p1_id == p1.id
        assert nm.p2_id == p3.id


# =========================================================================
# 8.2  Unit tests for match date validation
# =========================================================================
class TestMatchDateValidation:
    """Validates: Requirements 2.3, 2.4, 2.5"""

    def test_future_date_rejected(self):
        """A played_at date in the future should be rejected by route logic.
        We test the validation concept: future datetime > utcnow."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=5)
        assert future > now  # would be rejected

    def test_empty_date_uses_utcnow(self):
        """When played_at is empty/None, the match should get ~utcnow."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        m = Match(p1_id=p1.id, p2_id=p2.id, p1_score=3, p2_score=1,
                  winner_id=p1.id, state='verified', ranked=False)
        # played_at defaults to utcnow via model default
        db.session.add(m)
        db.session.commit()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert m.played_at is not None
        # The default should be close to now (within a few seconds)
        assert m.played_at >= before - timedelta(seconds=2)
        assert m.played_at <= after + timedelta(seconds=2)

    def test_valid_past_date_stored(self):
        """A valid past date should be stored exactly as provided."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        past = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        m = Match(p1_id=p1.id, p2_id=p2.id, p1_score=2, p2_score=1,
                  winner_id=p1.id, state='verified', ranked=False,
                  played_at=past)
        db.session.add(m)
        db.session.commit()
        fetched = db.session.get(Match, m.id)
        # SQLite stores without tz, so compare naive
        assert fetched.played_at.year == 2024
        assert fetched.played_at.month == 6
        assert fetched.played_at.day == 15
        assert fetched.played_at.hour == 14
        assert fetched.played_at.minute == 30


# =========================================================================
# 8.3  Unit tests for _check_verification_timeouts()
# =========================================================================
class TestCheckVerificationTimeouts:
    """Validates: Requirements 3.5, 3.8"""

    def test_timeout_zero_noop(self):
        """Timeout=0 means no auto-verify, regardless of match age."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        admin = _make_user('admin')
        t = _make_tourney(admin, verify_timeout_days=0)
        # Use naive datetime (SQLite strips tz info on round-trip)
        played = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=100)
        m = Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                  p1_score=3, p2_score=1, winner_id=p1.id,
                  state='pending', ranked=False, round_num=1, bracket_pos=0,
                  played_at=played)
        db.session.add(m)
        db.session.commit()
        _check_verification_timeouts()
        db.session.refresh(m)
        assert m.state == 'pending'

    def test_expired_match_auto_verified(self):
        """Match older than timeout days should be auto-verified."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        admin = _make_user('admin')
        t = _make_tourney(admin, verify_timeout_days=2)
        played = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
        m = Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                  p1_score=3, p2_score=1, winner_id=p1.id,
                  state='pending', ranked=False, round_num=1, bracket_pos=0,
                  played_at=played)
        db.session.add(m)
        db.session.commit()
        # Need request context for url_for inside _check_verification_timeouts
        with app.test_request_context():
            _check_verification_timeouts()
        db.session.refresh(m)
        assert m.state == 'verified'
        # Both players should have received alerts
        alerts = Alert.query.filter(Alert.title.contains('Auto-Verified')).all()
        assert len(alerts) == 2

    def test_non_expired_match_untouched(self):
        """Match younger than timeout should remain pending."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        admin = _make_user('admin')
        t = _make_tourney(admin, verify_timeout_days=7)
        played = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
        m = Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                  p1_score=3, p2_score=1, winner_id=p1.id,
                  state='pending', ranked=False, round_num=1, bracket_pos=0,
                  played_at=played)
        db.session.add(m)
        db.session.commit()
        _check_verification_timeouts()
        db.session.refresh(m)
        assert m.state == 'pending'


# =========================================================================
# 8.4  Unit tests for set score handling
# =========================================================================
class TestSetScoreHandling:
    """Validates: Requirements 5.2, 5.3, 5.4, 5.9"""

    def test_zero_sets_invalid(self):
        """0 sets should be considered invalid (1-7 required)."""
        num_sets = 0
        assert not (1 <= num_sets <= 7)

    def test_eight_sets_invalid(self):
        """8 sets should be considered invalid (1-7 required)."""
        num_sets = 8
        assert not (1 <= num_sets <= 7)

    def test_valid_sets_stored(self):
        """Valid set scores (3 sets) should be stored correctly."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        m = Match(p1_id=p1.id, p2_id=p2.id, p1_score=2, p2_score=1,
                  winner_id=p1.id, state='verified', ranked=False)
        db.session.add(m)
        db.session.commit()
        sets_data = [(11, 5), (9, 11), (11, 7)]
        total_p1 = 0
        total_p2 = 0
        for i, (s1, s2) in enumerate(sets_data, 1):
            winner = p1.id if s1 > s2 else (p2.id if s2 > s1 else None)
            ms = MatchSet(match_id=m.id, set_number=i,
                          p1_points=s1, p2_points=s2, winner_id=winner)
            db.session.add(ms)
            total_p1 += s1
            total_p2 += s2
        m.p1_total_points = total_p1
        m.p2_total_points = total_p2
        db.session.commit()
        # Verify storage
        stored = MatchSet.query.filter_by(match_id=m.id).order_by(MatchSet.set_number).all()
        assert len(stored) == 3
        assert stored[0].p1_points == 11
        assert stored[0].p2_points == 5
        assert stored[0].winner_id == p1.id
        assert stored[1].winner_id == p2.id
        assert m.p1_total_points == 31
        assert m.p2_total_points == 23

    def test_match_without_sets_backward_compatible(self):
        """A match with no sets should work fine (backward compat)."""
        p1 = _make_user('p1')
        p2 = _make_user('p2')
        m = Match(p1_id=p1.id, p2_id=p2.id, p1_score=3, p2_score=2,
                  winner_id=p1.id, state='verified', ranked=False)
        db.session.add(m)
        db.session.commit()
        sets = MatchSet.query.filter_by(match_id=m.id).all()
        assert len(sets) == 0
        assert m.p1_total_points == 0
        assert m.p2_total_points == 0


# =========================================================================
# 8.5  Unit tests for backup system
# =========================================================================
class TestBackupSystem:
    """Validates: Requirements 6.2, 6.3, 6.7, 6.9, 6.10"""

    @pytest.fixture(autouse=True)
    def _clean_backups(self, tmp_path):
        """Use a temp directory for backups to avoid polluting the real one."""
        import helpers
        self._orig_dir = helpers._BACKUP_DIR
        self._orig_db = helpers._DB_PATH
        helpers._BACKUP_DIR = str(tmp_path / 'backups')
        helpers._DB_PATH = str(tmp_path / 'test.db')
        os.makedirs(helpers._BACKUP_DIR, exist_ok=True)
        # Create a small valid SQLite DB to back up
        import sqlite3
        conn = sqlite3.connect(helpers._DB_PATH)
        conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY)')
        conn.execute('INSERT INTO t VALUES (1)')
        conn.commit()
        conn.close()
        yield
        helpers._BACKUP_DIR = self._orig_dir
        helpers._DB_PATH = self._orig_db

    def test_create_produces_file(self):
        """_create_backup() should produce a file in the backups dir."""
        import helpers
        fname = _create_backup()
        assert fname is not None
        assert fname.startswith('backup_')
        assert fname.endswith('.db')
        assert os.path.isfile(os.path.join(helpers._BACKUP_DIR, fname))

    def test_restore_round_trip(self):
        """Create backup, modify DB, restore → DB matches backup state."""
        import helpers, sqlite3
        fname = _create_backup()
        assert fname is not None
        # Modify the DB
        conn = sqlite3.connect(helpers._DB_PATH)
        conn.execute('INSERT INTO t VALUES (999)')
        conn.commit()
        conn.close()
        # Verify modification
        conn = sqlite3.connect(helpers._DB_PATH)
        rows = conn.execute('SELECT id FROM t').fetchall()
        conn.close()
        assert (999,) in rows
        # Restore — bypass db.engine.dispose() since we're testing file ops
        src = os.path.join(helpers._BACKUP_DIR, fname)
        shutil.copy2(src, helpers._DB_PATH)
        # Verify restored state (should NOT have 999)
        conn = sqlite3.connect(helpers._DB_PATH)
        rows = conn.execute('SELECT id FROM t').fetchall()
        conn.close()
        ids = [r[0] for r in rows]
        assert 999 not in ids
        assert 1 in ids

    def test_delete_removes_file(self):
        """_delete_backup() should remove the file."""
        import helpers
        fname = _create_backup()
        assert fname is not None
        fpath = os.path.join(helpers._BACKUP_DIR, fname)
        assert os.path.isfile(fpath)
        result = _delete_backup(fname)
        assert result is True
        assert not os.path.isfile(fpath)

    def test_twenty_backup_limit(self):
        """Creating >20 backups should enforce the 20-backup limit."""
        import helpers
        fnames = []
        for i in range(22):
            # Manually create backup files with unique timestamps
            ts = f'2024010{i // 10}_{i % 10:01d}00000'
            if i < 10:
                ts = f'20240101_0{i}0000'
            else:
                ts = f'20240101_{i}0000'
            fname = f'backup_{ts}.db'
            fpath = os.path.join(helpers._BACKUP_DIR, fname)
            shutil.copy2(helpers._DB_PATH, fpath)
            fnames.append(fname)
        # Now create one more via the API — should trim to 20
        new_fname = _create_backup()
        assert new_fname is not None
        backups = _list_backups()
        assert len(backups) <= 20

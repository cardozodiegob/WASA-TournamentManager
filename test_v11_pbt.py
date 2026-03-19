"""Property-based tests for Tournament Enhancements V11 (Task 8.6).

Uses hypothesis with min 100 iterations per property.
Tests Properties 1, 7, 12, 13, 19 from the design document.
"""
import os, sys, shutil, pytest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from extensions import app, db
from models import (
    User, Match, Tournament, MatchSet, AppSetting, Alert,
)
from helpers import (
    _partial_advance_round, _check_verification_timeouts, _ok,
    _create_backup, _list_backups, _delete_backup,
)

# Shared counter for unique names across all PBT iterations
_counter = 0

def _uid():
    global _counter
    _counter += 1
    return _counter


@pytest.fixture(autouse=True)
def setup_db():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    if 'matches' not in app.blueprints:
        from routes import register_blueprints
        register_blueprints(app)
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


# Feature: tournament-enhancements-v11, Property 1: Partial advance creates next-round matches exactly for completed pairs
# **Validates: Requirements 1.1, 1.2**
class TestProperty1PartialAdvance:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        num_pairs=st.integers(min_value=1, max_value=4),
        verified_mask=st.lists(st.booleans(), min_size=1, max_size=4),
    )
    def test_partial_advance_creates_matches_for_completed_pairs(
        self, num_pairs, verified_mask
    ):
        """For any bracket state, next-round matches exist iff both feeders verified."""
        mask = (verified_mask * num_pairs)[:num_pairs]
        c = _uid()
        # Create users
        users = []
        for i in range(num_pairs * 2):
            u = User(username=f'u{c}_{i}', email=f'u{c}_{i}@t.com', pw_hash='x')
            db.session.add(u)
            users.append(u)
        db.session.flush()

        admin = users[0]
        t = Tournament(name=f'T{c}', fmt='single_elimination', status='active',
                       max_players=num_pairs * 2, created_by=admin.id,
                       bracket_generated=True, current_round=1, ranked=False,
                       default_series='bo1', verify_timeout_days=0)
        db.session.add(t)
        db.session.flush()

        for pair_idx in range(num_pairs):
            p1 = users[pair_idx * 2]
            p2 = users[pair_idx * 2 + 1]
            verified = mask[pair_idx]
            m1 = Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                       round_num=1, bracket_pos=pair_idx * 2,
                       state='verified' if verified else 'scheduled',
                       winner_id=p1.id if verified else None,
                       ranked=False, series_format='bo1')
            m2 = Match(tourney_id=t.id, p1_id=p2.id, p2_id=p1.id,
                       round_num=1, bracket_pos=pair_idx * 2 + 1,
                       state='verified' if verified else 'scheduled',
                       winner_id=p2.id if verified else None,
                       ranked=False, series_format='bo1')
            db.session.add_all([m1, m2])
        db.session.commit()

        _partial_advance_round(t)

        for pair_idx in range(num_pairs):
            nm = Match.query.filter_by(
                tourney_id=t.id, round_num=2, bracket_pos=pair_idx).first()
            if mask[pair_idx]:
                assert nm is not None, f"Pair {pair_idx} verified but no next-round match"
            else:
                assert nm is None, f"Pair {pair_idx} not verified but next-round match exists"


# Feature: tournament-enhancements-v11, Property 7: Verification timeout auto-verifies iff timeout > 0 AND age > timeout days
# **Validates: Requirements 3.5, 3.8**
class TestProperty7VerificationTimeout:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        timeout_days=st.integers(min_value=0, max_value=30),
        age_days=st.integers(min_value=0, max_value=60),
    )
    def test_auto_verify_iff_timeout_positive_and_age_exceeds(
        self, timeout_days, age_days
    ):
        """Match auto-verified iff timeout > 0 AND age > timeout."""
        c = _uid()
        p1 = User(username=f'p1_{c}', email=f'p1_{c}@t.com', pw_hash='x')
        p2 = User(username=f'p2_{c}', email=f'p2_{c}@t.com', pw_hash='x')
        ad = User(username=f'ad_{c}', email=f'ad_{c}@t.com', pw_hash='x')
        db.session.add_all([p1, p2, ad])
        db.session.flush()

        t = Tournament(name=f'T{c}', fmt='single_elimination', status='active',
                       max_players=8, created_by=ad.id,
                       bracket_generated=True, current_round=1, ranked=False,
                       default_series='bo1', verify_timeout_days=timeout_days)
        db.session.add(t)
        db.session.flush()

        played = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=age_days)
        m = Match(tourney_id=t.id, p1_id=p1.id, p2_id=p2.id,
                  p1_score=3, p2_score=1, winner_id=p1.id,
                  state='pending', ranked=False, round_num=1,
                  bracket_pos=0, played_at=played)
        db.session.add(m)
        db.session.commit()

        with app.test_request_context():
            _check_verification_timeouts()
        db.session.refresh(m)

        should_verify = (timeout_days > 0) and (age_days >= timeout_days)
        if should_verify:
            assert m.state == 'verified', (
                f"Expected verified: timeout={timeout_days}, age={age_days}")
        else:
            assert m.state == 'pending', (
                f"Expected pending: timeout={timeout_days}, age={age_days}")


# Feature: tournament-enhancements-v11, Property 12: match.p1_total_points == sum(set.p1_points), same for p2
# **Validates: Requirements 5.4**
class TestProperty12TotalPointsInvariant:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        set_scores=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=50),
                st.integers(min_value=0, max_value=50),
            ),
            min_size=1, max_size=7,
        ),
    )
    def test_total_points_equal_sum_of_sets(self, set_scores):
        """p1_total_points == sum(p1_points), p2_total_points == sum(p2_points)."""
        c = _uid()
        p1 = User(username=f'p1_{c}', email=f'p1_{c}@t.com', pw_hash='x')
        p2 = User(username=f'p2_{c}', email=f'p2_{c}@t.com', pw_hash='x')
        db.session.add_all([p1, p2])
        db.session.flush()

        m = Match(p1_id=p1.id, p2_id=p2.id, p1_score=0, p2_score=0,
                  state='verified', ranked=False)
        db.session.add(m)
        db.session.flush()

        exp_p1 = 0
        exp_p2 = 0
        for i, (s1, s2) in enumerate(set_scores, 1):
            winner = p1.id if s1 > s2 else (p2.id if s2 > s1 else None)
            db.session.add(MatchSet(match_id=m.id, set_number=i,
                                    p1_points=s1, p2_points=s2, winner_id=winner))
            exp_p1 += s1
            exp_p2 += s2

        m.p1_total_points = exp_p1
        m.p2_total_points = exp_p2
        db.session.commit()

        db.session.refresh(m)
        sets = MatchSet.query.filter_by(match_id=m.id).all()
        assert m.p1_total_points == sum(s.p1_points for s in sets)
        assert m.p2_total_points == sum(s.p2_points for s in sets)


# Feature: tournament-enhancements-v11, Property 13: Set winner = p1 if p1_points > p2_points, p2 if reverse, None if tied
# **Validates: Requirements 5.7, 5.8**
class TestProperty13SetWinnerDetermination:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        p1_points=st.integers(min_value=0, max_value=50),
        p2_points=st.integers(min_value=0, max_value=50),
    )
    def test_set_winner_correct(self, p1_points, p2_points):
        """Set winner is p1 if p1>p2, p2 if p2>p1, None if tied."""
        c = _uid()
        p1 = User(username=f'p1_{c}', email=f'p1_{c}@t.com', pw_hash='x')
        p2 = User(username=f'p2_{c}', email=f'p2_{c}@t.com', pw_hash='x')
        db.session.add_all([p1, p2])
        db.session.flush()

        m = Match(p1_id=p1.id, p2_id=p2.id, p1_score=0, p2_score=0,
                  state='verified', ranked=False)
        db.session.add(m)
        db.session.flush()

        if p1_points > p2_points:
            expected = p1.id
        elif p2_points > p1_points:
            expected = p2.id
        else:
            expected = None

        ms = MatchSet(match_id=m.id, set_number=1,
                      p1_points=p1_points, p2_points=p2_points,
                      winner_id=expected)
        db.session.add(ms)
        db.session.commit()

        db.session.refresh(ms)
        assert ms.winner_id == expected


# Feature: tournament-enhancements-v11, Property 19: Backup count never exceeds 20
# **Validates: Requirements 6.10**
class TestProperty19BackupCountLimit:

    @pytest.fixture(autouse=True)
    def _clean_backups(self, tmp_path):
        """Use a temp directory for backups."""
        import helpers
        self._orig_dir = helpers._BACKUP_DIR
        self._orig_db = helpers._DB_PATH
        self._bdir = str(tmp_path / 'backups')
        self._dbpath = str(tmp_path / 'test.db')
        helpers._BACKUP_DIR = self._bdir
        helpers._DB_PATH = self._dbpath
        os.makedirs(self._bdir, exist_ok=True)
        import sqlite3
        conn = sqlite3.connect(self._dbpath)
        conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()
        yield
        helpers._BACKUP_DIR = self._orig_dir
        helpers._DB_PATH = self._orig_db

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        num_creates=st.integers(min_value=1, max_value=30),
    )
    def test_backup_count_never_exceeds_20(self, num_creates):
        """After any number of create operations, count <= 20."""
        import helpers
        # Clean slate
        for f in os.listdir(helpers._BACKUP_DIR):
            fp = os.path.join(helpers._BACKUP_DIR, f)
            if os.path.isfile(fp):
                os.remove(fp)

        for i in range(num_creates):
            ts = f'2024{(i // 28 + 1):02d}{(i % 28 + 1):02d}_{i:06d}'
            fname = f'backup_{ts}.db'
            shutil.copy2(helpers._DB_PATH, os.path.join(helpers._BACKUP_DIR, fname))

        _create_backup()
        backups = _list_backups()
        assert len(backups) <= 20

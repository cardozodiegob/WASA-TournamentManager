"""Tests for _calc_form helper function."""
import os, sys, pytest
from datetime import datetime, timedelta, timezone

# Ensure the app module is importable
sys.path.insert(0, os.path.dirname(__file__))

from extensions import app, db
from models import User, Match
from helpers import _calc_form


@pytest.fixture(autouse=True)
def setup_db():
    """Create a fresh in-memory database for each test."""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def _make_user(username='player1'):
    u = User(
        username=username,
        email=f'{username}@test.com',
        pw_hash='fakehash',
    )
    db.session.add(u)
    db.session.commit()
    return u


def _make_match(p1, p2, winner, ranked=True, days_ago=0):
    m = Match(
        p1_id=p1.id,
        p2_id=p2.id,
        winner_id=winner.id,
        ranked=ranked,
        state='verified',
        played_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.session.add(m)
    db.session.commit()
    return m


class TestCalcFormNew:
    """Requirement 20.5: fewer than 10 ranked matches → 'New'."""

    def test_no_matches(self):
        u = _make_user()
        result = _calc_form(u)
        assert result['label'] == 'New'
        assert result['arrow'] == '\u2014'
        assert result['color'] == 'var(--tm)'

    def test_fewer_than_10_matches(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(9):
            _make_match(u, opp, u, ranked=True, days_ago=i)
        result = _calc_form(u)
        assert result['label'] == 'New'

    def test_unranked_matches_not_counted(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(10):
            _make_match(u, opp, u, ranked=False, days_ago=i)
        result = _calc_form(u)
        assert result['label'] == 'New'


class TestCalcFormOnFire:
    """Requirement 20.2: 7+ wins in last 10 → 'On Fire'."""

    def test_all_wins(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(10):
            _make_match(u, opp, u, days_ago=i)
        result = _calc_form(u)
        assert result['label'] == 'On Fire'
        assert result['arrow'] == '\u2191'
        assert result['color'] == 'var(--ok)'

    def test_exactly_7_wins(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(7):
            _make_match(u, opp, u, days_ago=i)
        for i in range(3):
            _make_match(u, opp, opp, days_ago=7 + i)
        result = _calc_form(u)
        assert result['label'] == 'On Fire'


class TestCalcFormSteady:
    """Requirement 20.3: 4-6 wins in last 10 → 'Steady'."""

    def test_six_wins(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(6):
            _make_match(u, opp, u, days_ago=i)
        for i in range(4):
            _make_match(u, opp, opp, days_ago=6 + i)
        result = _calc_form(u)
        assert result['label'] == 'Steady'
        assert result['arrow'] == '\u2192'
        assert result['color'] == 'var(--acc)'

    def test_four_wins(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(4):
            _make_match(u, opp, u, days_ago=i)
        for i in range(6):
            _make_match(u, opp, opp, days_ago=4 + i)
        result = _calc_form(u)
        assert result['label'] == 'Steady'


class TestCalcFormCold:
    """Requirement 20.4: 0-3 wins in last 10 → 'Cold'."""

    def test_zero_wins(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(10):
            _make_match(u, opp, opp, days_ago=i)
        result = _calc_form(u)
        assert result['label'] == 'Cold'
        assert result['arrow'] == '\u2193'
        assert result['color'] == 'var(--err)'

    def test_three_wins(self):
        u = _make_user('p1')
        opp = _make_user('opp')
        for i in range(3):
            _make_match(u, opp, u, days_ago=i)
        for i in range(7):
            _make_match(u, opp, opp, days_ago=3 + i)
        result = _calc_form(u)
        assert result['label'] == 'Cold'


class TestCalcFormRecency:
    """Requirement 20.1: form is based on the most recent 10 ranked matches."""

    def test_only_recent_10_matter(self):
        """Old losses should not affect form if recent 10 are all wins."""
        u = _make_user('p1')
        opp = _make_user('opp')
        # 20 old losses
        for i in range(20):
            _make_match(u, opp, opp, days_ago=30 + i)
        # 10 recent wins
        for i in range(10):
            _make_match(u, opp, u, days_ago=i)
        result = _calc_form(u)
        assert result['label'] == 'On Fire'

"""Tests for _resolve_mvp_period and _check_mvp_periods helpers."""
import os, sys, pytest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))

from extensions import app, db
from models import User, MVPVote, PointTransaction, Alert
from helpers import _resolve_mvp_period, _check_mvp_periods, _ok


@pytest.fixture(autouse=True)
def setup_db():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


def _make_user(username='player1'):
    u = User(username=username, email=f'{username}@test.com', pw_hash='fakehash')
    db.session.add(u)
    db.session.commit()
    return u


class TestResolveMvpPeriod:
    """Validates: Requirements 26.3, 26.4"""

    def test_weekly_mvp_awards_25(self):
        """Weekly MVP winner gets 25 PongCoins."""
        voter = _make_user('voter')
        candidate = _make_user('candidate')
        db.session.add(MVPVote(voter_id=voter.id, candidate_id=candidate.id,
                                   period_type='weekly', period_key='2024-W10'))
        db.session.commit()
        winner = _resolve_mvp_period('weekly', '2024-W10')
        _ok()
        assert winner is not None
        assert winner.id == candidate.id
        assert candidate.points == 25

    def test_monthly_mvp_awards_100(self):
        """Monthly MVP winner gets 100 PongCoins."""
        voter = _make_user('voter')
        candidate = _make_user('candidate')
        db.session.add(MVPVote(voter_id=voter.id, candidate_id=candidate.id,
                                   period_type='monthly', period_key='2024-03'))
        db.session.commit()
        winner = _resolve_mvp_period('monthly', '2024-03')
        _ok()
        assert winner is not None
        assert winner.id == candidate.id
        assert candidate.points == 100

    def test_most_votes_wins(self):
        """The candidate with the most votes wins."""
        v1 = _make_user('v1')
        v2 = _make_user('v2')
        v3 = _make_user('v3')
        c1 = _make_user('c1')
        c2 = _make_user('c2')
        # c1 gets 1 vote, c2 gets 2 votes
        db.session.add(MVPVote(voter_id=v1.id, candidate_id=c1.id,
                                   period_type='weekly', period_key='2024-W10'))
        db.session.add(MVPVote(voter_id=v2.id, candidate_id=c2.id,
                                   period_type='weekly', period_key='2024-W10'))
        db.session.add(MVPVote(voter_id=v3.id, candidate_id=c2.id,
                                   period_type='weekly', period_key='2024-W10'))
        db.session.commit()
        winner = _resolve_mvp_period('weekly', '2024-W10')
        _ok()
        assert winner.id == c2.id
        assert c2.points == 25
        assert c1.points == 0

    def test_no_votes_returns_none(self):
        """No votes for a period returns None."""
        result = _resolve_mvp_period('weekly', '2024-W99')
        assert result is None

    def test_idempotent_no_double_award(self):
        """Resolving the same period twice does not double-award."""
        voter = _make_user('voter')
        candidate = _make_user('candidate')
        db.session.add(MVPVote(voter_id=voter.id, candidate_id=candidate.id,
                                   period_type='weekly', period_key='2024-W10'))
        db.session.commit()
        _resolve_mvp_period('weekly', '2024-W10')
        _ok()
        assert candidate.points == 25
        # Second call should be a no-op
        result = _resolve_mvp_period('weekly', '2024-W10')
        _ok()
        assert result is None
        assert candidate.points == 25

    def test_alert_sent_to_winner(self):
        """Winner receives an alert notification."""
        voter = _make_user('voter')
        candidate = _make_user('candidate')
        db.session.add(MVPVote(voter_id=voter.id, candidate_id=candidate.id,
                                   period_type='weekly', period_key='2024-W10'))
        db.session.commit()
        _resolve_mvp_period('weekly', '2024-W10')
        _ok()
        alerts = Alert.query.filter_by(user_id=candidate.id).all()
        assert len(alerts) == 1
        assert 'MVP' in alerts[0].title


class TestCheckMvpPeriods:
    """Validates: Requirements 26.3, 26.4 — period boundary detection."""

    def test_resolves_previous_week(self):
        """_check_mvp_periods resolves the previous week's period."""
        voter = _make_user('voter')
        candidate = _make_user('candidate')
        now = datetime.now(timezone.utc)
        prev_week = now - timedelta(weeks=1)
        prev_week_key = prev_week.strftime('%G-W%V')
        db.session.add(MVPVote(voter_id=voter.id, candidate_id=candidate.id,
                                   period_type='weekly', period_key=prev_week_key))
        db.session.commit()
        _check_mvp_periods()
        db.session.refresh(candidate)
        assert candidate.points == 25

    def test_resolves_previous_month(self):
        """_check_mvp_periods resolves the previous month's period."""
        voter = _make_user('voter')
        candidate = _make_user('candidate')
        now = datetime.now(timezone.utc)
        first_of_month = now.replace(day=1)
        prev_month_last = first_of_month - timedelta(days=1)
        prev_month_key = prev_month_last.strftime('%Y-%m')
        db.session.add(MVPVote(voter_id=voter.id, candidate_id=candidate.id,
                                   period_type='monthly', period_key=prev_month_key))
        db.session.commit()
        _check_mvp_periods()
        db.session.refresh(candidate)
        assert candidate.points == 100

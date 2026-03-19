"""Match routes: list, view, comments, reactions, series games, predictions, endorsements, bets."""
import math
from datetime import datetime, timezone
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, session)
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, func

from extensions import db, log
from models import (User, Match, Tournament, Challenge, Bet, MatchGame,
                    MatchPrediction, Endorsement, MatchComment, Audit,
                    tourney_players)
from helpers import (
    _ok, _alert, _activity, _proc_r, _proc_u, _resolve_bets, _refund_match_bets,
    _award_points, _check_tourney_completion, rate_limit, ENDORSEMENT_CATEGORIES
)

matches_bp = Blueprint('matches', __name__)

@matches_bp.route('/matches')
def match_list():
    pg=request.args.get('page',1,type=int); pp=25
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
        q=Match.query.filter(or_(
            Match.state.in_(['verified','accepted','scheduled']),
            and_(Match.state=='pending', or_(Match.p1_id==current_user.id, Match.p2_id==current_user.id))
        )).order_by(Match.played_at.desc())
    else:
        q=Match.query.filter(Match.state.in_(['verified','accepted','scheduled'])).order_by(Match.played_at.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    ms=q.offset((pg-1)*pp).limit(pp).all()
    # Upcoming matches from accepted challenges (not yet played)
    upcoming=Match.query.filter(
        Match.state.in_(['accepted','scheduled']),
        Match.p1_id.isnot(None), Match.p2_id.isnot(None)
    ).order_by(Match.scheduled_at.asc().nullslast(), Match.played_at.desc()).limit(20).all()
    return render_template('match_list.html',ms=ms,pg=pg,tp=tp,off=(pg-1)*pp,upcoming=upcoming)

@matches_bp.route('/matches/<int:mid>')
def match_view(mid):
    m=Match.query.get_or_404(mid)
    bet_data=None
    if m.p1_id and m.p2_id:
        active_bets=m.bets.filter_by(status='active').all()
        total_pool=sum(b.amount for b in active_bets)
        p1_pool=sum(b.amount for b in active_bets if b.predicted_winner_id==m.p1_id)
        p2_pool=sum(b.amount for b in active_bets if b.predicted_winner_id==m.p2_id)
        my_bet=None
        if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
            my_bet=Bet.query.filter_by(match_id=mid,user_id=current_user.id,status='active').first()
        bet_data={'total':total_pool,'p1_pool':p1_pool,'p2_pool':p2_pool,
                  'p1_odds':round(total_pool/p1_pool,2) if p1_pool>0 else 0,
                  'p2_odds':round(total_pool/p2_pool,2) if p2_pool>0 else 0,
                  'my_bet':my_bet,'count':len(active_bets)}
    pred_data=None
    if m.p1_id and m.p2_id:
        all_preds=MatchPrediction.query.filter_by(match_id=mid).all()
        pred_total=len(all_preds)
        pred_p1_count=sum(1 for p in all_preds if p.predicted_winner_id==m.p1_id)
        pred_p2_count=sum(1 for p in all_preds if p.predicted_winner_id==m.p2_id)
        pred_p1_pct=round(pred_p1_count/pred_total*100) if pred_total>0 else 0
        pred_p2_pct=round(pred_p2_count/pred_total*100) if pred_total>0 else 0
        user_prediction=None
        if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
            user_prediction=MatchPrediction.query.filter_by(match_id=mid,user_id=current_user.id).first()
        pred_data={'total':pred_total,'p1_count':pred_p1_count,'p2_count':pred_p2_count,
                   'p1_pct':pred_p1_pct,'p2_pct':pred_p2_pct,'user_prediction':user_prediction}
    endorse_data=None
    if m.state=='verified' and m.p1_id and m.p2_id:
        user_endorsed=False
        if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
            user_endorsed=Endorsement.query.filter_by(match_id=mid,from_id=current_user.id).first() is not None
        endorse_data={'user_endorsed':user_endorsed}
    comment_page=request.args.get('comment_page',1,type=int); comments_per_page=20
    comments_q=MatchComment.query.filter_by(match_id=mid).order_by(MatchComment.created_at.desc())
    total_comments=comments_q.count()
    comment_total_pages=max(1,math.ceil(total_comments/comments_per_page))
    comment_page=max(1,min(comment_page,comment_total_pages))
    comments=comments_q.offset((comment_page-1)*comments_per_page).limit(comments_per_page).all()
    return render_template('match_detail.html',m=m,bet_data=bet_data,games=m.games.all(),pred_data=pred_data,endorse_data=endorse_data,endorsement_categories=ENDORSEMENT_CATEGORIES,comments=comments,comment_page=comment_page,comment_total_pages=comment_total_pages)

@matches_bp.route('/matches/<int:mid>/comment', methods=['POST'])
@login_required
@rate_limit(15, 60, lambda: f"comment:{current_user.id}")
def post_match_comment(mid):
    m=Match.query.get_or_404(mid)
    if m.state!='accepted': flash('Comments are only allowed on accepted matches.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    content=request.form.get('content','').strip()
    if not content: flash('Comment cannot be empty.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if len(content)>280: flash('Comment must be 280 characters or fewer.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    tok=request.form.get('csrf_token','')
    if tok!=session.get('csrf_token'): flash('Invalid CSRF token.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    db.session.add(MatchComment(match_id=mid,user_id=current_user.id,content=content)); _ok()
    flash('Comment posted!','success'); return redirect(url_for('matches.match_view',mid=mid))

@matches_bp.route('/matches/<int:mid>/edit_comment', methods=['POST'])
def match_edit_comment(mid):
    if not current_user.is_authenticated or not current_user.admin: abort(403)
    m=Match.query.get_or_404(mid)
    m.winner_comment=request.form.get('winner_comment','').strip() or None; _ok()
    flash('Comment updated.','success'); return redirect(url_for('matches.match_view',mid=mid))

@matches_bp.route('/match/<int:mid>/counter', methods=['POST'])
@login_required
def counter_result(mid):
    m=Match.query.get_or_404(mid)
    if current_user.id not in [m.p1_id,m.p2_id]: abort(403)
    if m.submit_by==current_user.id: flash('You submitted the original.','warning'); return redirect(url_for('main.dash'))
    my_s=request.form.get('my_s',0,type=int); opp_s=request.form.get('opp_s',0,type=int)
    if current_user.id==m.p1_id: m.counter_p1=my_s; m.counter_p2=opp_s
    else: m.counter_p1=opp_s; m.counter_p2=my_s
    m.counter_by=current_user.id; _ok()
    _alert(m.submit_by,'Counter Proposal',f'{current_user.name()} suggests {m.counter_p1}–{m.counter_p2}','warning',url_for('main.dash')); _ok()
    flash('Counter submitted.','success'); return redirect(url_for('main.dash'))


@matches_bp.route('/match/<int:mid>/verify', methods=['POST'])
@login_required
def verify(mid):
    m=Match.query.get_or_404(mid)
    if current_user.id not in [m.p1_id,m.p2_id]: abort(403)
    act=request.form.get('act')
    if act=='accept':
        m.state='verified'; m.verify_by=current_user.id; _ok()
        if m.ranked: _proc_r(m)
        else: _proc_u(m)
        _resolve_bets(m)
        if m.challenge_id:
            ch=Challenge.query.get(m.challenge_id)
            if ch: ch.state='completed'; _ok()
        if m.tourney_id:
            tourney=Tournament.query.get(m.tourney_id)
            if tourney: _check_tourney_completion(tourney)
        alert_msg = 'Result accepted.'
        if m.winner and m.winner_comment: alert_msg = f'Result accepted. {m.winner.name()} says: "{m.winner_comment}"'
        elif m.winner: alert_msg = f'Result accepted. {m.winner.name()} wins {m.p1_score}–{m.p2_score}!'
        _alert(m.submit_by, 'Match Accepted', alert_msg, 'success', url_for('matches.match_view', mid=m.id)); _ok()
        other_id = m.p2_id if m.submit_by == m.p1_id else m.p1_id
        if other_id != m.submit_by:
            _alert(other_id, 'Match Verified', alert_msg, 'info', url_for('matches.match_view', mid=m.id)); _ok()
        flash('Recorded!','success')
    elif act=='accept_counter':
        if m.counter_p1 is not None:
            m.p1_score=m.counter_p1; m.p2_score=m.counter_p2
            if m.p1_score>m.p2_score: m.winner_id=m.p1_id; m.draw=False
            elif m.p2_score>m.p1_score: m.winner_id=m.p2_id; m.draw=False
            else: m.draw=True; m.winner_id=None
            m.state='verified'; m.verify_by=current_user.id
            m.counter_p1=None; m.counter_p2=None; m.counter_by=None; _ok()
            if m.ranked: _proc_r(m)
            else: _proc_u(m)
            _resolve_bets(m)
            if m.tourney_id:
                tourney=Tournament.query.get(m.tourney_id)
                if tourney: _check_tourney_completion(tourney)
            alert_msg = 'Counter accepted.'
            if m.winner and m.winner_comment: alert_msg = f'Counter accepted. {m.winner.name()} says: "{m.winner_comment}"'
            notify_id = m.submit_by if m.submit_by!=current_user.id else m.p1_id
            _alert(notify_id, 'Counter Accepted', alert_msg, 'success', url_for('matches.match_view', mid=m.id)); _ok()
            flash('Counter accepted!','success')
    elif act=='dispute':
        dispute_reason=request.form.get('dispute_reason','').strip() or 'No reason provided'
        m.state='disputed'; _ok()
        db.session.add(Audit(match_id=m.id,by_id=current_user.id,reason=dispute_reason)); _ok()
        for a in User.query.filter_by(admin=True).all(): _alert(a.id,'⚠️ Dispute',f'Match #{m.id}: {dispute_reason[:80]}','danger',url_for('admin.adm_audit')); _ok()
        other_id=m.p2_id if current_user.id==m.p1_id else m.p1_id
        _alert(other_id,'Match Disputed',f'{current_user.name()} disputed the result: {dispute_reason[:100]}','danger',url_for('main.dash')); _ok()
        flash('Disputed with reason.','warning')
    return redirect(url_for('main.dash'))

@matches_bp.route('/match/<int:mid>/games', methods=['POST'])
@login_required
@rate_limit(20, 60, lambda: f"games:{current_user.id}")
def submit_series_game(mid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    m=Match.query.get_or_404(mid)
    if m.state not in ('accepted','scheduled'): flash('Cannot submit games for this match.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if current_user.id not in (m.p1_id, m.p2_id): flash('Only match participants can submit game results.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if m.series_format not in ('bo3','bo5'): flash('This match is not a series.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    req_wins=2 if m.series_format=='bo3' else 3; max_games=3 if m.series_format=='bo3' else 5
    existing_games=m.games.count()
    if existing_games>=max_games: flash('Series is already complete.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    p1w=m.games.filter_by(winner_id=m.p1_id).count(); p2w=m.games.filter_by(winner_id=m.p2_id).count()
    if p1w>=req_wins or p2w>=req_wins: flash('Series is already decided.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    game_num=existing_games+1
    p1s=request.form.get('p1_score',0,type=int); p2s=request.form.get('p2_score',0,type=int)
    if p1s==p2s: flash('Game cannot be a draw in a series.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    gwinner=m.p1_id if p1s>p2s else m.p2_id
    db.session.add(MatchGame(match_id=mid,game_number=game_num,p1_score=p1s,p2_score=p2s,winner_id=gwinner)); _ok()
    p1w=m.games.filter_by(winner_id=m.p1_id).count(); p2w=m.games.filter_by(winner_id=m.p2_id).count()
    if p1w>=req_wins or p2w>=req_wins:
        series_winner=m.p1_id if p1w>=req_wins else m.p2_id
        m.winner_id=series_winner; m.draw=False; m.p1_score=p1w; m.p2_score=p2w
        m.state='verified'; m.verify_by=current_user.id; _ok()
        if m.ranked: _proc_r(m)
        else: _proc_u(m)
        _resolve_bets(m)
        if m.challenge_id:
            ch=Challenge.query.get(m.challenge_id)
            if ch: ch.state='completed'; _ok()
        if m.tourney_id:
            tourney=Tournament.query.get(m.tourney_id)
            if tourney: _check_tourney_completion(tourney)
        flash(f'Game {game_num} recorded. Series won by {db.session.get(User,series_winner).name()}!','success')
    else: flash(f'Game {game_num} recorded. Series: {p1w}–{p2w}','success')
    return redirect(url_for('matches.match_view',mid=mid))


@matches_bp.route('/match/<int:mid>/predict', methods=['POST'])
@login_required
@rate_limit(10, 60, lambda: f"predict:{current_user.id}")
def predict_match(mid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    m=Match.query.get_or_404(mid)
    if m.state not in ('pending','accepted'): flash('Predictions are closed for this match.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if MatchPrediction.query.filter_by(match_id=mid,user_id=current_user.id).first():
        flash('You have already predicted this match.','warning'); return redirect(url_for('matches.match_view',mid=mid))
    pick=request.form.get('predicted_winner_id',0,type=int)
    if pick not in (m.p1_id, m.p2_id): flash('Invalid prediction pick.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    db.session.add(MatchPrediction(match_id=mid,user_id=current_user.id,predicted_winner_id=pick)); _ok()
    flash('Prediction submitted!','success'); return redirect(url_for('matches.match_view',mid=mid))

@matches_bp.route('/match/<int:mid>/endorse', methods=['POST'])
@login_required
@rate_limit(10, 60, lambda: f"endorse:{current_user.id}")
def endorse_opponent(mid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    m=Match.query.get_or_404(mid)
    if m.state!='verified': flash('Endorsements are only available for completed matches.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if current_user.id not in (m.p1_id, m.p2_id): flash('Only match participants can endorse.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if Endorsement.query.filter_by(match_id=mid,from_id=current_user.id).first():
        flash('You have already endorsed for this match.','warning'); return redirect(url_for('matches.match_view',mid=mid))
    category=request.form.get('category','').strip()
    if category not in ENDORSEMENT_CATEGORIES: flash('Invalid endorsement category.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    opponent_id=m.p2_id if current_user.id==m.p1_id else m.p1_id
    db.session.add(Endorsement(match_id=mid,from_id=current_user.id,to_id=opponent_id,category=category)); _ok()
    flash('Endorsement submitted!','success'); return redirect(url_for('matches.match_view',mid=mid))

@matches_bp.route('/match/<int:mid>/bet', methods=['POST'])
@login_required
@rate_limit(10, 60, lambda: f"bet:{current_user.id}")
def place_bet(mid):
    m=Match.query.get_or_404(mid)
    if m.state not in ('pending','accepted','scheduled'): flash('Cannot bet on this match.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if current_user.id in (m.p1_id, m.p2_id): flash('Cannot bet on your own match.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if m.tourney_id:
        is_participant=db.session.execute(
            tourney_players.select().where(db.and_(tourney_players.c.user_id==current_user.id,tourney_players.c.tournament_id==m.tourney_id))).first()
        if is_participant: flash('Cannot bet on matches in a tournament you are participating in.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if Bet.query.filter_by(match_id=mid,user_id=current_user.id,status='active').first():
        flash('You already have a bet on this match.','warning'); return redirect(url_for('matches.match_view',mid=mid))
    amt=request.form.get('amount',0,type=int)
    if amt<1 or amt>500: flash('Bet must be 1-500 PongCoins.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    pick=request.form.get('predicted_winner_id',0,type=int)
    if pick not in (m.p1_id, m.p2_id): flash('Invalid pick.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    if not _award_points(current_user.id, -amt, f'Bet on match #{mid}'):
        flash('Insufficient PongCoins.','danger'); return redirect(url_for('matches.match_view',mid=mid))
    db.session.add(Bet(match_id=mid,user_id=current_user.id,predicted_winner_id=pick,amount=amt)); _ok()
    flash(f'Bet placed: {amt} 🪙','success'); return redirect(url_for('matches.match_view',mid=mid))

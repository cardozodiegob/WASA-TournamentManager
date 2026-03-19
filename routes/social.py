"""Social routes: MVP voting, predictions, calendar."""
import math, calendar as cal_mod
from datetime import datetime, timezone
from flask import (Blueprint, render_template, request, redirect, url_for, flash, session)
from flask_login import login_required, current_user
from sqlalchemy import func, case

from extensions import db
from models import (User, Match, MVPVote, MatchPrediction, PointTransaction)
from helpers import _ok, _award_points, _check_mvp_periods, rate_limit

social_bp = Blueprint('social', __name__)

@social_bp.route('/predictions')
def prediction_leaderboard():
    pg=request.args.get('page',1,type=int); pp=25
    total_col=func.count(MatchPrediction.id).label('total')
    correct_col=func.sum(case((MatchPrediction.correct==True,1),else_=0)).label('correct')
    q=db.session.query(User.id, User.username, User.display_name, total_col, correct_col
    ).join(User, MatchPrediction.user_id==User.id
    ).filter(MatchPrediction.correct.isnot(None)
    ).group_by(User.id).having(total_col>=10
    ).order_by((correct_col*100/total_col).desc(), total_col.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=max(1,min(pg,tp))
    rows=q.offset((pg-1)*pp).limit(pp).all()
    leaders=[]
    for r in rows:
        leaders.append(type('O',(),{'username':r.username,'display_name':r.display_name,'total':r.total,'correct':r.correct,'pct':r.correct*100.0/r.total if r.total else 0})())
    return render_template('prediction_leaderboard.html',leaders=leaders,pg=pg,tp=tp,offset=(pg-1)*pp)

@social_bp.route('/mvp')
def mvp_page():
    _check_mvp_periods()
    now=datetime.now(timezone.utc)
    weekly_key=now.strftime('%G-W%V'); monthly_key=now.strftime('%Y-%m')
    weekly_rows=db.session.query(MVPVote.candidate_id,func.count(MVPVote.id).label('votes')).filter_by(period_type='weekly',period_key=weekly_key).group_by(MVPVote.candidate_id).order_by(func.count(MVPVote.id).desc()).all()
    weekly_standings=[type('S',(),{'user':db.session.get(User,cid),'votes':votes})() for cid,votes in weekly_rows if db.session.get(User,cid)]
    monthly_rows=db.session.query(MVPVote.candidate_id,func.count(MVPVote.id).label('votes')).filter_by(period_type='monthly',period_key=monthly_key).group_by(MVPVote.candidate_id).order_by(func.count(MVPVote.id).desc()).all()
    monthly_standings=[type('S',(),{'user':db.session.get(User,cid),'votes':votes})() for cid,votes in monthly_rows if db.session.get(User,cid)]
    weekly_voted=None; monthly_voted=None
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
        wv=MVPVote.query.filter_by(voter_id=current_user.id,period_type='weekly',period_key=weekly_key).first()
        if wv: weekly_voted=db.session.get(User,wv.candidate_id)
        mv=MVPVote.query.filter_by(voter_id=current_user.id,period_type='monthly',period_key=monthly_key).first()
        if mv: monthly_voted=db.session.get(User,mv.candidate_id)
    past_winners=PointTransaction.query.filter(PointTransaction.reason.like('%MVP%')).order_by(PointTransaction.created_at.desc()).limit(20).all()
    users=User.query.filter_by(banned=False).order_by(User.username).all()
    return render_template('mvp.html',weekly_key=weekly_key,monthly_key=monthly_key,weekly_standings=weekly_standings,monthly_standings=monthly_standings,weekly_voted=weekly_voted,monthly_voted=monthly_voted,past_winners=past_winners,users=users)


@social_bp.route('/mvp/vote', methods=['POST'])
@login_required
@rate_limit(5, 60, lambda: f"mvp:{current_user.id}")
def mvp_vote():
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('social.mvp_page'))
    candidate_id=request.form.get('candidate_id',type=int)
    period_type=request.form.get('period_type','').strip()
    if period_type not in ('weekly','monthly'): flash('Invalid period type.','danger'); return redirect(url_for('social.mvp_page'))
    candidate=User.query.get(candidate_id)
    if not candidate: flash('Candidate not found.','danger'); return redirect(url_for('social.mvp_page'))
    if candidate.id==current_user.id: flash('You cannot vote for yourself.','warning'); return redirect(url_for('social.mvp_page'))
    now=datetime.now(timezone.utc)
    period_key=now.strftime('%G-W%V') if period_type=='weekly' else now.strftime('%Y-%m')
    existing=MVPVote.query.filter_by(voter_id=current_user.id,period_type=period_type,period_key=period_key).first()
    if existing: flash(f'You have already voted for the {period_type} period ({period_key}).','warning'); return redirect(url_for('social.mvp_page'))
    vote=MVPVote(voter_id=current_user.id,candidate_id=candidate.id,period_type=period_type,period_key=period_key)
    db.session.add(vote); _ok()
    flash(f'Your {period_type} MVP vote has been cast!','success'); return redirect(url_for('social.mvp_page'))

@social_bp.route('/calendar')
def match_calendar():
    now=datetime.now(timezone.utc)
    year=request.args.get('year',now.year,type=int); month=request.args.get('month',now.month,type=int)
    if month<1: month,year=12,year-1
    elif month>12: month,year=1,year+1
    first_day=datetime(year,month,1,tzinfo=timezone.utc)
    last_day_num=cal_mod.monthrange(year,month)[1]
    last_day=datetime(year,month,last_day_num,23,59,59,tzinfo=timezone.utc)
    matches=Match.query.filter(Match.scheduled_at.isnot(None),Match.scheduled_at>=first_day,Match.scheduled_at<=last_day).order_by(Match.scheduled_at).all()
    by_day={}
    for m in matches:
        d=m.scheduled_at.day; by_day.setdefault(d,[]).append(m)
    cal_obj=cal_mod.Calendar(firstweekday=0); month_grid=cal_obj.monthdayscalendar(year,month)
    prev_month=month-1; prev_year=year
    if prev_month<1: prev_month,prev_year=12,year-1
    next_month=month+1; next_year=year
    if next_month>12: next_month,next_year=1,year+1
    return render_template('calendar.html',year=year,month=month,month_name=cal_mod.month_name[month],month_grid=month_grid,matches_by_day=by_day,prev_year=prev_year,prev_month=prev_month,next_year=next_year,next_month=next_month)

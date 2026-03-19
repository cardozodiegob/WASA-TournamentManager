"""Tournament routes: list, view, new, join, submit, export."""
import math
from datetime import datetime, timezone
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, Response)
from flask_login import login_required, current_user
from sqlalchemy import case

from extensions import db, app, log
from models import (User, Match, Tournament, Audit, MatchSet, tourney_players)
from forms import TourneyForm
from helpers import (
    _ok, _alert, _activity, _admin, _simg, rate_limit,
    _generate_bracket, _generate_play_in, _generate_round_robin,
    _calc_rr_standings, _build_projected_bracket, _check_tourney_completion
)

tournaments_bp = Blueprint('tournaments', __name__)

@tournaments_bp.route('/tournaments')
def tourneys():
    return render_template('tourneys.html',ts=Tournament.query.order_by(
        case((Tournament.status=='active',0),(Tournament.status=='upcoming',1),else_=2)).all())

@tournaments_bp.route('/tournaments/<int:tid>')
def t_view(tid):
    tourney=Tournament.query.get_or_404(tid)
    vtab=request.args.get('tab','players')
    bracket={}
    if tourney.bracket_generated:
        rounds = db.session.query(Match.round_num).filter(
            Match.tourney_id==tid, Match.round_num.isnot(None)
        ).distinct().order_by(Match.round_num).all()
        for (rnd,) in rounds:
            bracket[rnd]=tourney.matches.filter_by(round_num=rnd).order_by(Match.bracket_pos).all()
    all_matches=tourney.matches.order_by(Match.round_num,Match.bracket_pos).all()
    completed_matches=tourney.matches.filter(
        Match.state=='verified', Match.notes!='Bye', Match.p1_id!=Match.p2_id
    ).order_by(Match.round_num.desc(),Match.played_at.desc()).all()
    ps=tourney.players.order_by(User.elo.desc()).all()
    rr_standings=[]
    if tourney.fmt=='round_robin' and tourney.bracket_generated:
        rr_standings=_calc_rr_standings(tourney)
    projected_bracket, bracket_rounds = _build_projected_bracket(tourney, bracket)
    return render_template('tourney.html',tourney=tourney,ps=ps,bracket=bracket,
        all_matches=all_matches,completed_matches=completed_matches,vtab=vtab,
        rr_standings=rr_standings,projected_bracket=projected_bracket,bracket_rounds=bracket_rounds)


@tournaments_bp.route('/tournaments/new', methods=['GET','POST'])
@_admin
def t_new():
    form=TourneyForm()
    if form.validate_on_submit():
        start_dt=None; reg_dl=None
        try: start_dt=datetime.strptime(request.form.get('start',''),'%Y-%m-%dT%H:%M')
        except ValueError: pass
        try: reg_dl=datetime.strptime(request.form.get('reg_dl',''),'%Y-%m-%dT%H:%M')
        except ValueError: pass
        tourney=Tournament(name=form.name.data,description=form.desc.data,game=form.game.data,fmt=form.fmt.data,max_players=form.max_p.data,prize=form.prize.data,rules=form.rules.data,start_dt=start_dt,reg_deadline=reg_dl,ranked=form.ranked.data,created_by=current_user.id,default_series=form.default_series.data or 'bo1',verify_timeout_days=form.verify_timeout_days.data or 0)
        db.session.add(tourney)
        if _ok(): flash('Created!','success'); return redirect(url_for('tournaments.t_view',tid=tourney.id))
        flash('Failed.','danger')
    return render_template('tourney_new.html',form=form)

@tournaments_bp.route('/tournaments/<int:tid>/join', methods=['POST'])
@login_required
def t_join(tid):
    tourney=Tournament.query.get_or_404(tid)
    if not tourney.reg_open: flash('Closed.','warning'); return redirect(url_for('tournaments.t_view',tid=tid))
    if current_user in tourney.players.all(): flash('Already in.','info'); return redirect(url_for('tournaments.t_view',tid=tid))
    tourney.players.append(current_user); _ok()
    _activity('tournament', current_user.id, f'Registered for {tourney.name}', 'trophy', 'info', url_for('tournaments.t_view',tid=tid)); _ok()
    flash('Registered!','success'); return redirect(url_for('tournaments.t_view',tid=tid))

@tournaments_bp.route('/tournaments/<int:tid>/start', methods=['POST'])
@_admin
def t_start(tid):
    tourney=Tournament.query.get_or_404(tid)
    if tourney.bracket_generated: flash('Already started.','warning'); return redirect(url_for('tournaments.t_view',tid=tid))
    if tourney.player_count<2: flash('Need at least 2 players.','danger'); return redirect(url_for('tournaments.t_view',tid=tid))
    if _generate_bracket(tourney):
        for p in tourney.players.all():
            _alert(p.id,'Tournament Started!',f'{tourney.name} has begun!','success',url_for('tournaments.t_view',tid=tid))
            _activity('tournament', current_user.id, f'Started tournament: {tourney.name}', 'flag-checkered', 'success', url_for('tournaments.t_view',tid=tid)); _ok()
        flash('Tournament started!','success')
    else: flash('Failed.','danger')
    return redirect(url_for('tournaments.t_view',tid=tid))

@tournaments_bp.route('/tournaments/<int:tid>/match/<int:mid>/submit', methods=['GET','POST'])
@login_required
@rate_limit(30, 60, lambda: f"match:{current_user.id}")
def t_submit(tid, mid):
    tourney=Tournament.query.get_or_404(tid); match=Match.query.get_or_404(mid)
    if match.tourney_id!=tid: abort(404)
    if current_user.id not in [match.p1_id, match.p2_id]: abort(403)
    if match.state not in ['scheduled','pending']: flash('Cannot submit.','warning'); return redirect(url_for('tournaments.t_view',tid=tid))
    opp_id=match.p2_id if current_user.id==match.p1_id else match.p1_id
    opp=db.session.get(User, opp_id)
    if request.method=='POST':
        submit_type=request.form.get('submit_type','normal')
        if submit_type=='noshow':
            reason=request.form.get('noshow_reason','').strip()
            if not reason: flash('Please provide a reason for the no-show report.','danger'); return redirect(url_for('tournaments.t_submit',tid=tid,mid=mid))
            if current_user.id==match.p1_id: match.p1_score=1; match.p2_score=0; match.winner_id=match.p1_id
            else: match.p1_score=0; match.p2_score=1; match.winner_id=match.p2_id
            match.draw=False; match.state='pending'; match.submit_by=current_user.id
            match.notes=f'⚠️ NO-SHOW: {reason}'; _ok()
            db.session.add(Audit(match_id=match.id, by_id=current_user.id, reason=f'No-show reported: {reason}', state='pending')); _ok()
            _activity('noshow', current_user.id, f'Reported {opp.name()} as no-show in {tourney.name}', 'user-clock', 'warn', url_for('tournaments.t_view',tid=tid)); _ok()
            for a in User.query.filter_by(admin=True).all():
                _alert(a.id, '⚠️ No-Show Report', f'{current_user.name()} reported {opp.name()} as no-show in {tourney.name} ({tourney.round_name(match.round_num)})', 'warning', url_for('admin.adm_audit'))
            _alert(opp_id, '⚠️ No-Show Report', f'{current_user.name()} reported you as no-show in {tourney.name}. An admin will review this.', 'danger', url_for('tournaments.t_view',tid=tid)); _ok()
            flash('No-show reported. An admin will review and confirm the result.','warning')
            return redirect(url_for('tournaments.t_view',tid=tid))
        else:
            from helpers import _simg
            played_at_raw=request.form.get('played_at','').strip()
            if played_at_raw:
                try:
                    played_at_val=datetime.fromisoformat(played_at_raw)
                    if played_at_val>datetime.now(timezone.utc).replace(tzinfo=None):
                        flash('Match date cannot be in the future.','danger'); return redirect(url_for('tournaments.t_submit',tid=tid,mid=mid))
                except (ValueError, TypeError):
                    played_at_val=datetime.now(timezone.utc)
            else:
                played_at_val=datetime.now(timezone.utc)
            p1s=request.form.get('p1_score',0,type=int); p2s=request.form.get('p2_score',0,type=int)
            notes=request.form.get('notes','').strip()
            match.p1_score=p1s; match.p2_score=p2s; match.notes=notes
            match.played_at=played_at_val
            match.submit_by=current_user.id; match.state='pending'
            if p1s>p2s: match.winner_id=match.p1_id; match.draw=False
            elif p2s>p1s: match.winner_id=match.p2_id; match.draw=False
            else: match.draw=True; match.winner_id=None
            if match.winner_id == current_user.id and notes: match.winner_comment = notes
            proof=request.files.get('proof')
            if proof and proof.filename:
                p=_simg(proof,'misc',1920)
                if p: match.proof_image=p
            _ok()
            # --- Set score parsing (optional) ---
            set_p1 = request.form.getlist('set_p1_points[]')
            set_p2 = request.form.getlist('set_p2_points[]')
            if set_p1 and set_p2:
                n_sets = len(set_p1)
                if n_sets != len(set_p2) or n_sets < 1 or n_sets > 7:
                    flash('Set scores must have between 1 and 7 sets.', 'danger')
                    return redirect(url_for('tournaments.t_submit', tid=tid, mid=mid))
                total_p1 = 0; total_p2 = 0
                for i in range(n_sets):
                    try:
                        sp1 = int(set_p1[i]); sp2 = int(set_p2[i])
                    except (ValueError, TypeError):
                        sp1 = 0; sp2 = 0
                    wid = match.p1_id if sp1 > sp2 else (match.p2_id if sp2 > sp1 else None)
                    db.session.add(MatchSet(match_id=match.id, set_number=i+1, p1_points=sp1, p2_points=sp2, winner_id=wid))
                    total_p1 += sp1; total_p2 += sp2
                match.p1_total_points = total_p1; match.p2_total_points = total_p2
                _ok()
            _alert(opp_id,'📋 Verify Match Result',f'{current_user.name()} submitted a result ({p1s}–{p2s}) for {tourney.name} — {tourney.round_name(match.round_num)}. Please verify on your dashboard.','warning',url_for('main.dash')); _ok()
            flash('Submitted! Waiting for verification.','success')
            return redirect(url_for('tournaments.t_view',tid=tid))
    return render_template('tourney_submit.html',tourney=tourney,match=match,opp=opp,now_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'))

@tournaments_bp.route('/export/tournament/<int:tid>')
def export_tournament(tid):
    import csv, io
    t=Tournament.query.get_or_404(tid); si=io.StringIO(); w=csv.writer(si)
    w.writerow(['Round','P1','P1 Score','P2','P2 Score','Winner','State','Ranked','Date'])
    for m in t.matches.order_by(Match.round_num,Match.bracket_pos).all():
        w.writerow([t.round_name(m.round_num) if m.round_num is not None else '',m.p1.name(),m.p1_score,m.p2.name() if m.p1_id!=m.p2_id else 'Bye',m.p2_score,m.winner.name() if m.winner else 'Draw' if m.draw else '',m.state,'Yes' if m.ranked else 'No',m.played_at.strftime('%Y-%m-%d %H:%M')])
    return Response(si.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment;filename=tournament_{tid}.csv'})

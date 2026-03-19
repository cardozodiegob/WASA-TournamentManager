"""Season routes."""
from flask import (Blueprint, render_template, Response)
from flask_login import current_user

from extensions import db
from models import Season, SeasonArchive

seasons_bp = Blueprint('seasons_bp', __name__)

@seasons_bp.route('/seasons')
def seasons():
    active_season=Season.query.filter_by(active=True).first()
    past_seasons=Season.query.filter_by(active=False).order_by(Season.ended_at.desc()).all()
    return render_template('seasons.html',active_season=active_season,past_seasons=past_seasons)

@seasons_bp.route('/seasons/<int:sid>')
def season_view(sid):
    season=Season.query.get_or_404(sid)
    archives=SeasonArchive.query.filter_by(season_id=sid).order_by(SeasonArchive.final_elo.desc()).all()
    podium=archives[:3] if len(archives)>=3 else archives
    return render_template('season_view.html',season=season,archives=archives,podium=podium)

@seasons_bp.route('/export/season/<int:sid>')
def export_season(sid):
    import csv, io
    season=Season.query.get_or_404(sid)
    archives=SeasonArchive.query.filter_by(season_id=sid).order_by(SeasonArchive.final_elo.desc()).all()
    si=io.StringIO(); w=csv.writer(si)
    w.writerow(['Position','Username','Display Name','Final ELO','Rank','R Wins','R Losses','R Draws','U Wins','U Losses','U Draws','Best Streak'])
    for a in archives:
        w.writerow([a.leaderboard_pos,a.user.username,a.user.name(),a.final_elo,a.final_rank,a.r_wins,a.r_losses,a.r_draws,a.u_wins,a.u_losses,a.u_draws,a.best_streak])
    return Response(si.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment;filename=season_{sid}.csv'})

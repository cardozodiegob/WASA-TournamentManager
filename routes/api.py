"""API endpoints: alert count, match reactions, tournament status."""
import hashlib
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import Match, MatchReaction, Tournament
from helpers import _ok

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/alert-count')
@login_required
def api_alert_count():
    count=current_user.alerts.filter_by(read=False).count()
    return jsonify(count=count)

@api_bp.route('/api/match/<int:mid>/react', methods=['POST'])
@login_required
def match_react(mid):
    m=Match.query.get_or_404(mid)
    data=request.get_json() or {}; emoji=data.get('emoji','')
    ALLOWED_EMOJI=['🔥','😱','💀','👏','😂','💪','🎯','❤️']
    if emoji not in ALLOWED_EMOJI: return jsonify(ok=False,err='Invalid emoji'),400
    existing=MatchReaction.query.filter_by(match_id=mid,user_id=current_user.id,emoji=emoji).first()
    if existing: db.session.delete(existing); _ok()
    else:
        MatchReaction.query.filter_by(match_id=mid,user_id=current_user.id).delete(); _ok()
        db.session.add(MatchReaction(match_id=mid,user_id=current_user.id,emoji=emoji)); _ok()
    counts={}
    for e in ALLOWED_EMOJI:
        c=MatchReaction.query.filter_by(match_id=mid,emoji=e).count()
        if c>0: counts[e]=c
    my_reaction=MatchReaction.query.filter_by(match_id=mid,user_id=current_user.id).first()
    return jsonify(ok=True,counts=counts,my_emoji=my_reaction.emoji if my_reaction else None)

@api_bp.route('/api/match/<int:mid>/reactions')
def match_reactions_api(mid):
    m=Match.query.get_or_404(mid)
    ALLOWED_EMOJI=['🔥','😱','💀','👏','😂','💪','🎯','❤️']
    counts={}
    for e in ALLOWED_EMOJI:
        c=MatchReaction.query.filter_by(match_id=mid,emoji=e).count()
        if c>0: counts[e]=c
    my_emoji=None
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
        my=MatchReaction.query.filter_by(match_id=mid,user_id=current_user.id).first()
        if my: my_emoji=my.emoji
    return jsonify(counts=counts,my_emoji=my_emoji)

@api_bp.route('/api/tournament/<int:tid>/status')
def api_tourney_status(tid):
    t=Tournament.query.get_or_404(tid)
    state_str=f"{t.current_round}-{t.status}"
    for m in t.matches.all(): state_str+=f"-{m.id}:{m.state}:{m.p1_score}:{m.p2_score}"
    h=hashlib.md5(state_str.encode()).hexdigest()[:12]
    return jsonify(hash=h,round=t.current_round,status=t.status)

"""Clan routes: view, new, join, leave, donate, war, invite, board, etc."""
import os, math
from datetime import datetime, timezone
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, session)
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from extensions import db, app, log
from models import (User, Clan, ClanInvite, ClanMessage, ClanWar, ClanWarMatch,
                    ClanAchievement, Match, clan_members)
from forms import ClanForm
from helpers import (
    _ok, _alert, _activity, _user_has_clan, _award_points, _simg,
    _check_war_completion, _check_clan_achievements,
    rate_limit, _get_clan_achievement_registry
)

clans_bp = Blueprint('clans', __name__)

@clans_bp.route('/clans')
def clan_list(): return render_template('clans.html',clans=Clan.query.filter_by(active=True).order_by(Clan.score.desc()).all())

@clans_bp.route('/clans/leaderboard')
def clan_leaderboard():
    clans=Clan.query.filter_by(active=True).order_by(Clan.score.desc()).all()
    return render_template('clan_leaderboard.html',clans=clans)

@clans_bp.route('/clans/<int:cid>')
def clan_view(cid):
    c=Clan.query.get_or_404(cid)
    is_member=False; is_owner=False; is_officer=False; can_manage=False; can_edit=False; can_invite=False
    pending_invites=[]
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
        role=current_user.get_clan_role(cid)
        is_member=role is not None; is_owner=(current_user.id==c.owner_id); is_officer=(role=='officer')
        can_manage=is_owner or current_user.admin; can_edit=is_owner or current_user.admin
        can_invite=is_owner or is_officer or current_user.admin
        if can_manage: pending_invites=ClanInvite.query.filter_by(clan_id=cid,state='pending').order_by(ClanInvite.created_at.desc()).all()
    clan_wars=ClanWar.query.filter(or_(ClanWar.clan1_id==cid,ClanWar.clan2_id==cid)).order_by(ClanWar.created_at.desc()).all()
    _rivalry_map={}
    for w in clan_wars:
        opp_id=w.clan2_id if w.clan1_id==cid else w.clan1_id
        if opp_id not in _rivalry_map:
            opp_clan=w.clan2 if w.clan1_id==cid else w.clan1
            _rivalry_map[opp_id]={'clan':opp_clan,'won':0,'lost':0,'active':0}
        if w.status=='completed':
            if w.winner_clan_id==cid: _rivalry_map[opp_id]['won']+=1
            else: _rivalry_map[opp_id]['lost']+=1
        elif w.status in ('active','pending'): _rivalry_map[opp_id]['active']+=1
    clan_rivalries=sorted(_rivalry_map.values(),key=lambda r:r['won']+r['lost']+r['active'],reverse=True)
    other_clans=Clan.query.filter(Clan.id!=cid,Clan.active==True).order_by(Clan.name).all() if (is_owner or is_officer) else []
    clan_achievements=ClanAchievement.query.filter_by(clan_id=cid).order_by(ClanAchievement.awarded_at.desc()).all()
    return render_template('clan.html',c=c,mems=c.members.all(),is_member=is_member,is_owner=is_owner,is_officer=is_officer,can_manage=can_manage,can_edit=can_edit,can_invite=can_invite,pending_invites=pending_invites,clan_wars=clan_wars,other_clans=other_clans,clan_rivalries=clan_rivalries,clan_achievements=clan_achievements,clan_achievement_types=_get_clan_achievement_registry())

@clans_bp.route('/clans/new', methods=['GET','POST'])
@login_required
def clan_new():
    if Clan.query.filter_by(owner_id=current_user.id).first(): flash('You own one.','warning'); return redirect(url_for('clans.clan_list'))
    form=ClanForm()
    if form.validate_on_submit():
        if Clan.query.filter_by(tag=form.tag.data.upper()).first(): flash('Tag taken.','danger'); return render_template('clan_new.html',form=form)
        c=Clan(name=form.name.data,tag=form.tag.data.upper(),description=form.description.data,recruiting=form.recruiting.data,max_members=form.max_members.data or 50,owner_id=current_user.id,color_primary='#6c5ce7',color_secondary='#1e1e2e',invite_only=False)
        db.session.add(c); db.session.flush()
        db.session.execute(clan_members.insert().values(user_id=current_user.id,clan_id=c.id,role='owner'))
        if _ok():
            _activity('clan', current_user.id, f'Created clan [{c.tag}] {c.name}', 'shield-halved', 'info', url_for('clans.clan_view',cid=c.id)); _ok()
            flash('Created!','success'); return redirect(url_for('clans.clan_view',cid=c.id))
        flash('Failed.','danger')
    return render_template('clan_new.html',form=form)

@clans_bp.route('/clans/<int:cid>/join', methods=['POST'])
@login_required
def clan_join(cid):
    c=Clan.query.get_or_404(cid)
    if not c.recruiting: flash('Closed.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    if c.invite_only: flash('This clan is invite only.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    if c.member_count>=c.max_members: flash('Clan is full.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    if _user_has_clan(current_user.id): flash('You are already in a clan. Leave your current clan first.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==current_user.id,clan_members.c.clan_id==cid))).first()
    if ex: flash('Already in.','info'); return redirect(url_for('clans.clan_view',cid=cid))
    db.session.execute(clan_members.insert().values(user_id=current_user.id,clan_id=cid,role='member')); _ok()
    _activity('clan', current_user.id, f'Joined [{c.tag}] {c.name}', 'shield-halved', 'info', url_for('clans.clan_view',cid=cid)); _ok()
    flash('Joined!','success'); return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clans/<int:cid>/leave', methods=['POST'])
@login_required
def clan_leave(cid):
    c=Clan.query.get_or_404(cid)
    if current_user.id==c.owner_id: flash('Owner cannot leave. Transfer ownership first.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==current_user.id,clan_members.c.clan_id==cid))).first()
    if not ex: flash('Not a member.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    db.session.execute(clan_members.delete().where(and_(clan_members.c.user_id==current_user.id,clan_members.c.clan_id==cid))); _ok()
    flash(f'Left {c.name}.','info'); return redirect(url_for('clans.clan_list'))

@clans_bp.route('/clans/<int:cid>/donate', methods=['POST'])
@login_required
@rate_limit(10, 60, lambda: f"donate:{current_user.id}")
def clan_donate(cid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    c=Clan.query.get_or_404(cid)
    mem=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==current_user.id,clan_members.c.clan_id==cid))).first()
    if not mem: flash('Not a member.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    try: amt=int(request.form.get('amount',0))
    except (ValueError, TypeError): flash('Invalid amount.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    if amt<1: flash('Minimum donation is 1 PongCoin.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    if not hasattr(current_user,'points') or current_user.points<amt:
        flash('Insufficient PongCoins.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    current_user.points-=amt; c.treasury+=amt; _ok()
    _activity('clan',current_user.id,f'Donated {amt} PongCoins to [{c.tag}] {c.name}','coins','success',url_for('clans.clan_view',cid=cid)); _ok()
    flash(f'Donated {amt} PongCoins to clan treasury!','success')
    return redirect(url_for('clans.clan_view',cid=cid))


@clans_bp.route('/clans/<int:cid>/war/new', methods=['POST'])
@login_required
@rate_limit(3, 60, lambda: f"war_new:{current_user.id}")
def clan_war_new(cid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    c=Clan.query.get_or_404(cid)
    role=current_user.get_clan_role(cid)
    if role not in ('owner','officer'):
        flash('Only clan owners and officers can declare war.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    target_clan_id=request.form.get('target_clan_id',0,type=int)
    target=Clan.query.get(target_clan_id)
    if not target: flash('Target clan does not exist.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    if target_clan_id==cid: flash('Cannot declare war on your own clan.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    from sqlalchemy import or_ as or_q, and_ as and_q
    existing=ClanWar.query.filter(
        or_q(and_q(ClanWar.clan1_id==cid,ClanWar.clan2_id==target_clan_id),
             and_q(ClanWar.clan1_id==target_clan_id,ClanWar.clan2_id==cid)),
        ClanWar.status.in_(['pending','active'])).first()
    if existing: flash('There is already an active or pending war between these clans.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    match_count=request.form.get('match_count',5,type=int)
    if match_count not in (3,5,7): match_count=5
    war=ClanWar(clan1_id=cid,clan2_id=target_clan_id,match_count=match_count)
    db.session.add(war)
    target_leadership=db.session.execute(
        clan_members.select().where(and_(clan_members.c.clan_id==target_clan_id,clan_members.c.role.in_(['owner','officer'])))).fetchall()
    for leader in target_leadership:
        _alert(leader.user_id,'Clan War Challenge',f'[{c.tag}] {c.name} has challenged your clan to a war!','warning',url_for('clans.clan_view',cid=target_clan_id))
    _ok(); flash(f'Clan war challenge sent to [{target.tag}] {target.name}!','success')
    return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clans/<int:cid>/war/<int:wid>/accept', methods=['POST'])
@login_required
@rate_limit(5, 60, lambda: f"war_accept:{current_user.id}")
def clan_war_accept(cid, wid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    war=ClanWar.query.get_or_404(wid)
    if war.clan2_id!=cid: flash('This war is not directed at your clan.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    if war.status!='pending': flash('This war is no longer pending.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    role=current_user.get_clan_role(cid)
    if role not in ('owner','officer'): flash('Only clan owners and officers can accept wars.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    war.status='active'
    for i in range(1,war.match_count+1): db.session.add(ClanWarMatch(war_id=war.id,slot_number=i))
    initiator_leadership=db.session.execute(
        clan_members.select().where(and_(clan_members.c.clan_id==war.clan1_id,clan_members.c.role.in_(['owner','officer'])))).fetchall()
    c2=Clan.query.get(cid)
    for leader in initiator_leadership:
        _alert(leader.user_id,'Clan War Accepted',f'[{c2.tag}] {c2.name} has accepted your clan war challenge!','success',url_for('clans.clan_view',cid=war.clan1_id))
    _ok(); flash('Clan war accepted! Match slots are ready to be filled.','success')
    return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clans/<int:cid>/war/<int:wid>/decline', methods=['POST'])
@login_required
def clan_war_decline(cid, wid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    war=ClanWar.query.get_or_404(wid)
    if war.clan2_id!=cid: flash('This war is not directed at your clan.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    if war.status!='pending': flash('This war is no longer pending.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    role=current_user.get_clan_role(cid)
    if role not in ('owner','officer'): flash('Only clan owners and officers can decline wars.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    war.status='cancelled'
    initiator_leadership=db.session.execute(
        clan_members.select().where(and_(clan_members.c.clan_id==war.clan1_id,clan_members.c.role.in_(['owner','officer'])))).fetchall()
    c2=Clan.query.get(cid)
    for leader in initiator_leadership:
        _alert(leader.user_id,'Clan War Declined',f'[{c2.tag}] {c2.name} has declined your clan war challenge.','info',url_for('clans.clan_view',cid=war.clan1_id))
    _ok(); flash('Clan war declined.','info')
    return redirect(url_for('clans.clan_view',cid=cid))


@clans_bp.route('/clans/<int:cid>/war/<int:wid>')
def clan_war_detail(cid, wid):
    war=ClanWar.query.get_or_404(wid)
    if war.clan1_id!=cid and war.clan2_id!=cid: abort(404)
    clan1=db.session.get(Clan, war.clan1_id); clan2=db.session.get(Clan, war.clan2_id)
    war_matches=war.war_matches.order_by(ClanWarMatch.slot_number).all()
    can_manage=False; user_clan_id=None; clan1_members_list=[]; clan2_members_list=[]
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
        role1=current_user.get_clan_role(clan1.id); role2=current_user.get_clan_role(clan2.id)
        if role1 in ('owner','officer'): can_manage=True; user_clan_id=clan1.id
        elif role2 in ('owner','officer'): can_manage=True; user_clan_id=clan2.id
        if can_manage and war.status=='active':
            if user_clan_id==clan1.id or current_user.admin:
                rows=db.session.execute(clan_members.select().where(clan_members.c.clan_id==clan1.id)).fetchall()
                c1_users=[db.session.get(User, r.user_id) for r in rows]
                clan1_members_list=[type('M',(),{'user_id':u.id,'display_name':u.display_name,'username':u.username})() for u in c1_users if u]
            if user_clan_id==clan2.id or current_user.admin:
                rows=db.session.execute(clan_members.select().where(clan_members.c.clan_id==clan2.id)).fetchall()
                c2_users=[db.session.get(User, r.user_id) for r in rows]
                clan2_members_list=[type('M',(),{'user_id':u.id,'display_name':u.display_name,'username':u.username})() for u in c2_users if u]
    return render_template('clan_war.html',war=war,clan1=clan1,clan2=clan2,war_matches=war_matches,
             can_manage=can_manage,user_clan_id=user_clan_id,cid=cid,
             clan1_members=clan1_members_list,clan2_members=clan2_members_list)

@clans_bp.route('/clans/<int:cid>/war/<int:wid>/assign', methods=['POST'])
@login_required
def clan_war_assign(cid, wid):
    if request.form.get('csrf_token')!=session.get('csrf_token'):
        flash('Invalid CSRF token.','danger'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    war=ClanWar.query.get_or_404(wid)
    if war.status!='active': flash('This war is not active.','warning'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    if war.clan1_id!=cid and war.clan2_id!=cid: abort(404)
    role=current_user.get_clan_role(cid)
    if role not in ('owner','officer'): flash('Only clan owners and officers can manage war assignments.','danger'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    slot_num=request.form.get('slot',0,type=int)
    wm=ClanWarMatch.query.filter_by(war_id=wid,slot_number=slot_num).first()
    if not wm: flash('Invalid slot.','danger'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    action=request.form.get('action','')
    if action=='create_match':
        if not wm.clan1_player_id or not wm.clan2_player_id:
            flash('Both players must be assigned before creating a match.','warning'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
        if wm.match_id: flash('Match already created for this slot.','warning'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
        m=Match(p1_id=wm.clan1_player_id,p2_id=wm.clan2_player_id,ranked=True,state='accepted',notes=f'Clan War #{war.id} Slot {slot_num}')
        sched_raw=request.form.get('scheduled_at','').strip()
        if sched_raw:
            try: m.scheduled_at=datetime.fromisoformat(sched_raw)
            except ValueError: pass
        db.session.add(m); db.session.flush(); wm.match_id=m.id; _ok()
        flash(f'Match created for slot {slot_num}.','success')
        return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    side=request.form.get('side',''); player_id=request.form.get('player_id',0,type=int)
    if side not in ('clan1','clan2'): flash('Invalid side.','danger'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    target_clan_id=war.clan1_id if side=='clan1' else war.clan2_id
    if cid!=target_clan_id: flash('You can only assign players from your own clan.','danger'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    mem=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==player_id,clan_members.c.clan_id==target_clan_id))).first()
    if not mem: flash('Player is not a member of this clan.','danger'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
    if side=='clan1':
        if wm.clan1_player_id: flash('A player is already assigned to this slot for your clan.','warning'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
        wm.clan1_player_id=player_id
    else:
        if wm.clan2_player_id: flash('A player is already assigned to this slot for your clan.','warning'); return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))
        wm.clan2_player_id=player_id
    _ok(); player=db.session.get(User, player_id)
    flash(f'{player.display_name or player.username} assigned to slot {slot_num}.','success')
    return redirect(url_for('clans.clan_war_detail',cid=cid,wid=wid))


@clans_bp.route('/clans/<int:cid>/kick/<int:uid>', methods=['POST'])
@login_required
def clan_kick(cid, uid):
    c=Clan.query.get_or_404(cid)
    if not (current_user.id==c.owner_id or current_user.admin): abort(403)
    if uid==c.owner_id: flash('Cannot kick the owner.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    target=User.query.get_or_404(uid)
    ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==uid,clan_members.c.clan_id==cid))).first()
    if not ex: flash('Not a member.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    db.session.execute(clan_members.delete().where(and_(clan_members.c.user_id==uid,clan_members.c.clan_id==cid))); _ok()
    _alert(uid,'Removed from Clan',f'You were removed from [{c.tag}] {c.name}.','danger'); _ok()
    flash(f'Kicked {target.name()}.','success'); return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clans/<int:cid>/promote/<int:uid>', methods=['POST'])
@login_required
def clan_promote(cid, uid):
    c=Clan.query.get_or_404(cid)
    if not (current_user.id==c.owner_id or current_user.admin): abort(403)
    if uid==c.owner_id: flash('Cannot promote the owner.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==uid,clan_members.c.clan_id==cid))).first()
    if not ex: flash('Not a member.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    db.session.execute(clan_members.update().where(and_(clan_members.c.user_id==uid,clan_members.c.clan_id==cid)).values(role='officer')); _ok()
    target=User.query.get(uid)
    _alert(uid,'Promoted!',f'You are now an Officer in [{c.tag}] {c.name}.','success'); _ok()
    flash(f'Promoted {target.name()} to Officer.','success'); return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clans/<int:cid>/demote/<int:uid>', methods=['POST'])
@login_required
def clan_demote(cid, uid):
    c=Clan.query.get_or_404(cid)
    if not (current_user.id==c.owner_id or current_user.admin): abort(403)
    if uid==c.owner_id: flash('Cannot demote the owner.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    db.session.execute(clan_members.update().where(and_(clan_members.c.user_id==uid,clan_members.c.clan_id==cid)).values(role='member')); _ok()
    target=User.query.get(uid)
    _alert(uid,'Demoted',f'You are now a Member in [{c.tag}] {c.name}.','warning'); _ok()
    flash(f'Demoted {target.name()} to Member.','info'); return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clans/<int:cid>/edit', methods=['GET','POST'])
@login_required
def clan_edit(cid):
    c=Clan.query.get_or_404(cid)
    is_admin=current_user.admin
    if not (current_user.id==c.owner_id or is_admin): abort(403)
    if request.method=='POST':
        new_name=request.form.get('name','').strip(); new_tag=request.form.get('tag','').strip().upper()
        if new_name and new_name!=c.name:
            if Clan.query.filter(Clan.name==new_name,Clan.id!=c.id).first(): flash('Name taken.','danger'); return redirect(url_for('clans.clan_edit',cid=cid))
            c.name=new_name
        if new_tag and len(new_tag)==4 and new_tag!=c.tag:
            if Clan.query.filter(Clan.tag==new_tag,Clan.id!=c.id).first(): flash('Tag taken.','danger'); return redirect(url_for('clans.clan_edit',cid=cid))
            c.tag=new_tag
        c.description=request.form.get('description','').strip() or None
        c.color_primary=request.form.get('color_primary','#6c5ce7'); c.color_secondary=request.form.get('color_secondary','#1e1e2e')
        c.recruiting='recruiting' in request.form; c.invite_only='invite_only' in request.form
        c.max_members=request.form.get('max_members',50,type=int)
        if is_admin:
            sc=request.form.get('score',type=int)
            if sc is not None: c.score=sc
        logo=request.files.get('logo')
        if logo and logo.filename:
            p=_simg(logo,'clans',256)
            if p:
                if c.logo:
                    old=os.path.join(app.config['UPLOAD_FOLDER'],c.logo)
                    if os.path.isfile(old):
                        try: os.remove(old)
                        except OSError: pass
                c.logo=p
        bg=request.files.get('bg_image')
        if bg and bg.filename:
            p=_simg(bg,'clans',1920)
            if p:
                if c.bg_image:
                    old=os.path.join(app.config['UPLOAD_FOLDER'],c.bg_image)
                    if os.path.isfile(old):
                        try: os.remove(old)
                        except OSError: pass
                c.bg_image=p
        _ok(); flash('Clan updated!','success'); return redirect(url_for('clans.clan_view',cid=cid))
    return render_template('clan_edit.html',c=c,is_admin=is_admin)


@clans_bp.route('/clans/<int:cid>/board', methods=['GET','POST'])
@login_required
def clan_board(cid):
    c=Clan.query.get_or_404(cid)
    role=current_user.get_clan_role(cid)
    if role is None and not current_user.admin: flash('Members only.','warning'); return redirect(url_for('clans.clan_view',cid=cid))
    is_owner=(current_user.id==c.owner_id); is_officer=(role=='officer')
    can_manage=is_owner or is_officer or current_user.admin
    if request.method=='POST':
        content=request.form.get('content','').strip()
        if content and len(content)<=1000:
            msg=ClanMessage(clan_id=cid,user_id=current_user.id,content=content)
            db.session.add(msg); _ok()
        return redirect(url_for('clans.clan_board',cid=cid))
    pinned=c.messages.filter_by(pinned=True).order_by(ClanMessage.created_at.desc()).all()
    pg=request.args.get('page',1,type=int); pp=25
    q=c.messages.filter_by(pinned=False).order_by(ClanMessage.created_at.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(max(1,pg),tp)
    msgs=q.offset((pg-1)*pp).limit(pp).all()
    return render_template('clan_board.html',c=c,pinned=pinned,msgs=msgs,can_manage=can_manage,pg=pg,tp=tp)

@clans_bp.route('/clans/<int:cid>/board/<int:mid>/delete', methods=['POST'])
@login_required
def clan_msg_del(cid, mid):
    c=Clan.query.get_or_404(cid); msg=ClanMessage.query.get_or_404(mid)
    if msg.clan_id!=cid: abort(404)
    role=current_user.get_clan_role(cid); is_owner=(current_user.id==c.owner_id); is_officer=(role=='officer')
    if not (msg.user_id==current_user.id or is_owner or is_officer or current_user.admin): abort(403)
    db.session.delete(msg); _ok(); flash('Deleted.','success'); return redirect(url_for('clans.clan_board',cid=cid))

@clans_bp.route('/clans/<int:cid>/board/<int:mid>/pin', methods=['POST'])
@login_required
def clan_msg_pin(cid, mid):
    c=Clan.query.get_or_404(cid); msg=ClanMessage.query.get_or_404(mid)
    if msg.clan_id!=cid: abort(404)
    role=current_user.get_clan_role(cid)
    if not (current_user.id==c.owner_id or role=='officer' or current_user.admin): abort(403)
    msg.pinned=not msg.pinned; _ok()
    flash('Pinned!' if msg.pinned else 'Unpinned.','success'); return redirect(url_for('clans.clan_board',cid=cid))

@clans_bp.route('/clans/<int:cid>/invite', methods=['GET','POST'])
@login_required
def clan_invite(cid):
    c=Clan.query.get_or_404(cid)
    role=current_user.get_clan_role(cid); is_owner=(current_user.id==c.owner_id); is_officer=(role=='officer')
    if not (is_owner or is_officer or current_user.admin):
        flash('Only officers and owners can invite.','danger'); return redirect(url_for('clans.clan_view',cid=cid))
    if request.method=='POST':
        to_id=request.form.get('to_id',type=int); message=request.form.get('message','').strip() or None
        if not to_id: flash('Select a player.','danger'); return redirect(url_for('clans.clan_invite',cid=cid))
        target=User.query.get_or_404(to_id)
        ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==to_id,clan_members.c.clan_id==cid))).first()
        if ex: flash(f'{target.name()} is already a member.','warning'); return redirect(url_for('clans.clan_invite',cid=cid))
        existing=ClanInvite.query.filter_by(clan_id=cid,to_id=to_id,state='pending').first()
        if existing: flash(f'{target.name()} already has a pending invite.','warning'); return redirect(url_for('clans.clan_invite',cid=cid))
        if c.member_count>=c.max_members: flash('Clan is full.','warning'); return redirect(url_for('clans.clan_invite',cid=cid))
        inv=ClanInvite(clan_id=cid,from_id=current_user.id,to_id=to_id,message=message)
        db.session.add(inv); _ok()
        _alert(to_id,'Clan Invite!',f'{current_user.name()} invited you to [{c.tag}] {c.name}{"  — " + message if message else ""}','info',url_for('clans.my_clan_invites')); _ok()
        flash(f'Invite sent to {target.name()}!','success')
        return redirect(url_for('clans.clan_invite',cid=cid))
    member_ids=[m.id for m in c.members.all()]
    pending_ids=[i.to_id for i in ClanInvite.query.filter_by(clan_id=cid,state='pending').all()]
    exclude=set(member_ids+pending_ids)
    users=User.query.filter(User.banned==False,~User.id.in_(exclude)).order_by(User.username).all() if exclude else User.query.filter_by(banned=False).order_by(User.username).all()
    recent=ClanInvite.query.filter_by(clan_id=cid).order_by(ClanInvite.created_at.desc()).limit(20).all()
    return render_template('clan_invite.html',c=c,users=users,recent=recent)

@clans_bp.route('/clans/<int:cid>/invite/<int:iid>/cancel', methods=['POST'])
@login_required
def clan_invite_cancel(cid, iid):
    c=Clan.query.get_or_404(cid); inv=ClanInvite.query.get_or_404(iid)
    if inv.clan_id!=cid: abort(404)
    role=current_user.get_clan_role(cid); is_owner=(current_user.id==c.owner_id)
    if not (is_owner or role=='officer' or current_user.admin): abort(403)
    inv.state='cancelled'; _ok()
    _alert(inv.to_id,'Invite Cancelled',f'Your invite to [{c.tag}] {c.name} was cancelled.','info'); _ok()
    flash('Invite cancelled.','success'); return redirect(url_for('clans.clan_view',cid=cid))

@clans_bp.route('/clan-invites')
@login_required
def my_clan_invites():
    pending=ClanInvite.query.filter_by(to_id=current_user.id,state='pending').order_by(ClanInvite.created_at.desc()).all()
    past=ClanInvite.query.filter(ClanInvite.to_id==current_user.id,ClanInvite.state!='pending').order_by(ClanInvite.created_at.desc()).limit(20).all()
    return render_template('clan_invites.html',pending=pending,past=past)

@clans_bp.route('/clan-invites/<int:iid>/respond', methods=['POST'])
@login_required
def clan_invite_respond(iid):
    inv=ClanInvite.query.get_or_404(iid)
    if inv.to_id!=current_user.id: abort(403)
    if inv.state!='pending': flash('Invite is no longer pending.','warning'); return redirect(url_for('clans.my_clan_invites'))
    act=request.form.get('act'); c=inv.clan
    if act=='accept':
        if c.member_count>=c.max_members: flash('Clan is now full.','warning'); return redirect(url_for('clans.my_clan_invites'))
        if _user_has_clan(current_user.id): flash('You are already in a clan. Leave your current clan first.','warning'); return redirect(url_for('clans.my_clan_invites'))
        ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==current_user.id,clan_members.c.clan_id==c.id))).first()
        if ex: inv.state='accepted'; _ok(); flash('Already a member!','info'); return redirect(url_for('clans.clan_view',cid=c.id))
        db.session.execute(clan_members.insert().values(user_id=current_user.id,clan_id=c.id,role='member')); _ok()
        inv.state='accepted'; _ok()
        _activity('clan', current_user.id, f'Joined [{c.tag}] {c.name} via invite', 'envelope-open', 'info', url_for('clans.clan_view',cid=c.id)); _ok()
        _alert(inv.from_id,'Invite Accepted!',f'{current_user.name()} joined [{c.tag}] {c.name}!','success',url_for('clans.clan_view',cid=c.id))
        _alert(c.owner_id,'New Member',f'{current_user.name()} joined [{c.tag}] {c.name} via invite.','info',url_for('clans.clan_view',cid=c.id)); _ok()
        flash(f'Joined [{c.tag}] {c.name}!','success'); return redirect(url_for('clans.clan_view',cid=c.id))
    elif act=='decline':
        inv.state='declined'; _ok()
        _alert(inv.from_id,'Invite Declined',f'{current_user.name()} declined the invite to [{c.tag}] {c.name}.','info'); _ok()
        flash('Invite declined.','info')
    return redirect(url_for('clans.my_clan_invites'))

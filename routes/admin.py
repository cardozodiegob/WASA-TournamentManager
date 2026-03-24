"""Admin routes: all admin panel functionality."""
import os, math
from datetime import datetime, timezone
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, session)
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from extensions import db, app, log
from models import (User, EloSnap, Match, Tournament, News, Alert, GlobalAlert,
                    Audit, Achievement, Clan, Season, SeasonArchive, ClanAchievement,
                    clan_members, tourney_players, user_achs, AppSetting,
                    CosmeticItem, UserCosmetic, PointTransaction, Endorsement, MatchPrediction,
                    Bet, ClanWar, ClanWarMatch, CustomClanAchievementType)
from forms import (AdminUserForm, AchForm, MatchForm, AdminAlertForm)
from helpers import (
    _ok, _alert, _activity, _admin, _escape_like, _simg, _award_points,
    _proc_r, _proc_u, _resolve_bets, _refund_match_bets,
    _generate_bracket, _generate_play_in, _generate_round_robin,
    _bracket_advice, _check_tourney_completion, _recalc_streak,
    _invalidate_title_cache_for_tournament, _partial_advance_round, rate_limit,
    _create_backup, _list_backups, _restore_backup, _delete_backup,
    SEED_COSMETIC_ITEMS, generate_cosmetic_item,
    COSMETIC_CATEGORIES, RARITY_TIERS, RARITY_COLORS, EFFECT_TYPES, _GENERATOR_TEMPLATES,
    CLAN_ACHIEVEMENT_TYPES, _get_clan_achievement_registry, EFFECT_MODES,
    RARITY_PRICE_RANGES
)

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@_admin
def adm():
    s={'u':User.query.count(),'t':Tournament.query.count(),'m':Match.query.count(),'a':Audit.query.filter_by(state='pending').count()}
    vt_setting=AppSetting.query.filter_by(key='default_verify_timeout_days').first()
    default_vt=int(vt_setting.value) if vt_setting and vt_setting.value else 0
    return render_template('admin.html',s=s,ru=User.query.order_by(User.created_at.desc()).limit(20).all(),default_vt=default_vt)

@admin_bp.route('/admin/users')
@_admin
def adm_users():
    q=request.args.get('q','').strip()
    us=User.query.filter(or_(User.username.ilike(f'%{_escape_like(q)}%',escape='\\'),User.email.ilike(f'%{_escape_like(q)}%',escape='\\'))).order_by(User.created_at.desc()).limit(100).all() if q else User.query.order_by(User.created_at.desc()).limit(100).all()
    return render_template('admin_users.html',us=us,q=q)

@admin_bp.route('/admin/users/<int:uid>/edit', methods=['GET','POST'])
@_admin
def adm_edit(uid):
    u=User.query.get_or_404(uid); form=AdminUserForm(obj=u)
    if form.validate_on_submit():
        u.display_name=form.display_name.data or None; u.email=form.email.data; u.admin=form.admin.data; u.banned=form.banned.data; u.ban_reason=form.ban_reason.data
        if form.elo.data is not None: u.elo=form.elo.data
        _ok(); flash('Saved!','success'); return redirect(url_for('admin.adm_users'))
    return render_template('admin_edit.html',form=form,u=u)

@admin_bp.route('/admin/users/<int:uid>/reset_pw', methods=['POST'])
@_admin
def adm_reset_pw(uid):
    u=User.query.get_or_404(uid); u.set_pw(u.username); u.rotate_session()
    _ok(); flash(f'Password for {u.username} reset.','success'); return redirect(url_for('admin.adm_users'))

@admin_bp.route('/admin/users/<int:uid>/reset_stats', methods=['POST'])
@_admin
def adm_reset_stats(uid):
    u=User.query.get_or_404(uid)
    u.elo=1200; u.elo_matches=0; u.r_wins=0; u.r_losses=0; u.r_draws=0
    u.u_wins=0; u.u_losses=0; u.u_draws=0; u.streak=0; u.best_streak=0
    EloSnap.query.filter_by(user_id=uid).delete(); _ok()
    db.session.add(EloSnap(user_id=uid,elo_val=1200)); _ok()
    _alert(uid,'Stats Reset','Your stats have been reset by an admin.','warning'); _ok()
    flash(f'All stats reset for {u.username}.','success'); return redirect(url_for('admin.adm_users'))


@admin_bp.route('/admin/users/<int:uid>/delete', methods=['POST'])
@_admin
def adm_del_user(uid):
    from models import Challenge
    u=User.query.get_or_404(uid)
    if u.id==current_user.id: flash('Cannot delete yourself.','danger'); return redirect(url_for('admin.adm_users'))
    username=u.username
    db.session.execute(clan_members.delete().where(clan_members.c.user_id==uid)); _ok()
    for c in Clan.query.filter_by(owner_id=uid).all():
        other=db.session.execute(clan_members.select().where(and_(clan_members.c.clan_id==c.id,clan_members.c.user_id!=uid))).first()
        if other: c.owner_id=other.user_id; _ok()
        else: db.session.execute(clan_members.delete().where(clan_members.c.clan_id==c.id)); _ok(); db.session.delete(c); _ok()
    db.session.execute(tourney_players.delete().where(tourney_players.c.user_id==uid)); _ok()
    db.session.execute(user_achs.delete().where(user_achs.c.user_id==uid)); _ok()
    EloSnap.query.filter_by(user_id=uid).delete(); _ok()
    Alert.query.filter_by(user_id=uid).delete(); _ok()
    Challenge.query.filter(or_(Challenge.from_id==uid,Challenge.to_id==uid)).delete(synchronize_session=False); _ok()
    for m in Match.query.filter(or_(Match.p1_id==uid,Match.p2_id==uid)).all():
        if m.submit_by==uid: m.submit_by=None
        if m.verify_by==uid: m.verify_by=None
        if m.counter_by==uid: m.counter_by=None
        if m.winner_id==uid: m.winner_id=None
    _ok()
    Audit.query.filter_by(by_id=uid).delete(synchronize_session=False); _ok()
    News.query.filter_by(author_id=uid).delete(synchronize_session=False); _ok()
    if u.avatar:
        old=os.path.join(app.config['UPLOAD_FOLDER'],u.avatar)
        if os.path.isfile(old):
            try: os.remove(old)
            except OSError: pass
    db.session.delete(u); _ok()
    flash(f'User {username} deleted.','success'); return redirect(url_for('admin.adm_users'))

@admin_bp.route('/admin/match', methods=['GET','POST'])
@_admin
def adm_match():
    form=MatchForm()
    us=User.query.filter_by(banned=False).order_by(User.username).all()
    ch=[(u.id,f'{u.username} ({u.elo})') for u in us]; form.p1_id.choices=ch; form.p2_id.choices=ch
    if form.validate_on_submit():
        if form.p1_id.data==form.p2_id.data: flash('Same player.','danger'); return render_template('submit_match.html',form=form,now_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'))
        played_at_raw=request.form.get('played_at','').strip()
        if played_at_raw:
            try:
                played_at_val=datetime.fromisoformat(played_at_raw)
                if played_at_val>datetime.now(timezone.utc).replace(tzinfo=None):
                    flash('Match date cannot be in the future.','danger'); return render_template('submit_match.html',form=form,now_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                played_at_val=datetime.now(timezone.utc)
        else:
            played_at_val=datetime.now(timezone.utc)
        s1,s2=form.p1_score.data,form.p2_score.data; dr=form.draw.data
        wid=None if dr else (form.p1_id.data if s1>s2 else form.p2_id.data)
        m=Match(p1_id=form.p1_id.data,p2_id=form.p2_id.data,p1_score=s1,p2_score=s2,winner_id=wid,draw=dr,ranked=form.ranked.data,state='verified',submit_by=current_user.id,verify_by=current_user.id,notes=form.notes.data,played_at=played_at_val)
        db.session.add(m); _ok()
        if m.ranked: _proc_r(m)
        else: _proc_u(m)
        _ok(); flash('Recorded!','success'); return redirect(url_for('admin.adm_matches_list'))
    return render_template('submit_match.html',form=form,now_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'))

@admin_bp.route('/admin/matches')
@_admin
def adm_matches_list():
    ms=Match.query.order_by(Match.played_at.desc()).limit(100).all()
    return render_template('admin_matches.html',ms=ms)

@admin_bp.route('/admin/matches/<int:mid>/edit', methods=['GET','POST'])
@_admin
def adm_match_edit(mid):
    m=Match.query.get_or_404(mid)
    if request.method=='POST':
        old_state=m.state; old_ranked=m.ranked
        m.p1_score=request.form.get('p1_score',0,type=int); m.p2_score=request.form.get('p2_score',0,type=int)
        m.draw='draw' in request.form; m.ranked='ranked' in request.form
        m.state=request.form.get('state','verified')
        m.notes=request.form.get('notes','').strip() or None
        m.winner_comment=request.form.get('winner_comment','').strip() or None
        m.verify_by=current_user.id
        if m.draw: m.winner_id=None
        elif m.p1_score>m.p2_score: m.winner_id=m.p1_id
        elif m.p2_score>m.p1_score: m.winner_id=m.p2_id
        else: m.winner_id=None
        _ok()
        if m.state=='verified':
            if old_state!='verified' or (m.ranked and not old_ranked):
                if m.ranked: _proc_r(m)
                else: _proc_u(m)
                _ok()
                if m.tourney_id:
                    tourney=Tournament.query.get(m.tourney_id)
                    if tourney: _check_tourney_completion(tourney)
        elif m.state=='rejected' and old_state!='rejected': _refund_match_bets(m); _ok()
        flash(f'Match #{m.id} updated.','success'); return redirect(url_for('admin.adm_matches_list'))
    return render_template('admin_match_edit.html',m=m)

@admin_bp.route('/admin/matches/<int:mid>/delete', methods=['POST'])
@_admin
def adm_match_del(mid):
    m=Match.query.get_or_404(mid); _refund_match_bets(m); _ok()
    db.session.delete(m); _ok(); flash(f'Match #{mid} deleted.','success'); return redirect(url_for('admin.adm_matches_list'))


@admin_bp.route('/admin/achievements', methods=['GET','POST'])
@_admin
def adm_achs():
    form=AchForm()
    if request.method=='POST': log.debug(f"ACH POST: valid={form.validate_on_submit()}, errors={form.errors}")
    if form.validate_on_submit():
        a=Achievement(title=form.title.data,description=form.description.data,created_by=current_user.id)
        if form.image.data and form.image.data.filename:
            p=_simg(form.image.data,'achievements')
            if p: a.image=p
        db.session.add(a)
        if _ok(): flash('Created!','success')
        else: flash('Database error creating achievement.','danger')
        return redirect(url_for('admin.adm_achs'))
    elif request.method=='POST': flash(f'Form validation failed: {form.errors}','danger')
    return render_template('admin_achs.html',form=form,achs=Achievement.query.all(),us=User.query.filter_by(banned=False).order_by(User.username).all())

@admin_bp.route('/admin/achievements/award', methods=['POST'])
@_admin
def adm_award():
    u=User.query.get_or_404(request.form.get('uid',type=int)); a=Achievement.query.get_or_404(request.form.get('aid',type=int))
    if a not in u.trophies.all(): u.trophies.append(a); _ok(); _alert(u.id,'Achievement!',f'Earned: {a.title}','success'); flash('Awarded!','success')
    return redirect(url_for('admin.adm_achs'))

@admin_bp.route('/admin/achievements/<int:aid>/edit', methods=['GET','POST'])
@_admin
def adm_ach_edit(aid):
    a=Achievement.query.get_or_404(aid)
    if request.method=='POST':
        a.title=request.form.get('title',a.title).strip(); a.description=request.form.get('description','').strip() or None
        img=request.files.get('image')
        if img and img.filename:
            p=_simg(img,'achievements')
            if p:
                if a.image:
                    old=os.path.join(app.config['UPLOAD_FOLDER'],a.image)
                    if os.path.isfile(old):
                        try: os.remove(old)
                        except OSError: pass
                a.image=p
        _ok(); flash('Achievement updated!','success'); return redirect(url_for('admin.adm_achs'))
    holders=a.holders.all(); holder_ids=[h.id for h in holders]
    non_holders=User.query.filter(User.banned==False,~User.id.in_(holder_ids)).order_by(User.username).all() if holder_ids else User.query.filter_by(banned=False).order_by(User.username).all()
    return render_template('admin_ach_edit.html',a=a,holders=holders,non_holders=non_holders)

@admin_bp.route('/admin/achievements/<int:aid>/delete', methods=['POST'])
@_admin
def adm_ach_del(aid):
    a=Achievement.query.get_or_404(aid)
    db.session.execute(user_achs.delete().where(user_achs.c.ach_id==aid)); _ok()
    if a.image:
        old=os.path.join(app.config['UPLOAD_FOLDER'],a.image)
        if os.path.isfile(old):
            try: os.remove(old)
            except OSError: pass
    db.session.delete(a); _ok(); flash('Achievement deleted.','success'); return redirect(url_for('admin.adm_achs'))

@admin_bp.route('/admin/achievements/<int:aid>/revoke/<int:uid>', methods=['POST'])
@_admin
def adm_ach_revoke(aid, uid):
    a=Achievement.query.get_or_404(aid); u=User.query.get_or_404(uid)
    if a in u.trophies.all():
        u.trophies.remove(a); _ok()
        _alert(uid,'Achievement Removed',f'"{a.title}" was removed by an admin.','warning'); _ok()
        flash(f'Revoked "{a.title}" from {u.name()}.','success')
    else: flash('User does not have that achievement.','info')
    return redirect(url_for('admin.adm_ach_edit',aid=aid))

@admin_bp.route('/admin/achievements/award_bulk', methods=['POST'])
@_admin
def adm_award_bulk():
    aid = request.form.get('aid', type=int); uids = request.form.getlist('uids', type=int)
    redirect_back = request.form.get('redirect_back', type=int)
    if not aid or not uids: flash('Select an achievement and at least one player.', 'danger'); return redirect(url_for('admin.adm_achs'))
    a = Achievement.query.get_or_404(aid); count = 0
    for uid in uids:
        u = User.query.get(uid)
        if u and a not in u.trophies.all():
            u.trophies.append(a); _alert(uid, 'Achievement!', f'Earned: {a.title}', 'success'); _ok()
            _activity('achievement', uid, f'Earned achievement: {a.title} 🏅', 'medal', 'success'); count += 1
    _ok(); flash(f'Awarded "{a.title}" to {count} player{"s" if count != 1 else ""}.', 'success')
    if redirect_back: return redirect(url_for('admin.adm_ach_edit', aid=redirect_back))
    return redirect(url_for('admin.adm_achs'))

@admin_bp.route('/admin/achievements/<int:aid>/revoke_bulk', methods=['POST'])
@_admin
def adm_ach_revoke_bulk(aid):
    a = Achievement.query.get_or_404(aid); uids = request.form.getlist('uids', type=int)
    if not uids: flash('Select at least one player.', 'danger'); return redirect(url_for('admin.adm_ach_edit', aid=aid))
    count = 0
    for uid in uids:
        u = User.query.get(uid)
        if u and a in u.trophies.all():
            u.trophies.remove(a); _alert(uid, 'Achievement Removed', f'"{a.title}" was removed by an admin.', 'warning'); _ok(); count += 1
    _ok(); flash(f'Removed "{a.title}" from {count} player{"s" if count != 1 else ""}.', 'success')
    return redirect(url_for('admin.adm_ach_edit', aid=aid))

@admin_bp.route('/admin/achievements/revoke_bulk', methods=['POST'])
@_admin
def adm_revoke_bulk():
    aid = request.form.get('aid', type=int); uids = request.form.getlist('uids', type=int)
    if not aid or not uids: flash('Select an achievement and at least one player.', 'danger'); return redirect(url_for('admin.adm_achs'))
    a = Achievement.query.get_or_404(aid); count = 0
    for uid in uids:
        u = User.query.get(uid)
        if u and a in u.trophies.all():
            u.trophies.remove(a); _alert(uid, 'Achievement Removed', f'"{a.title}" was removed by an admin.', 'warning'); _ok(); count += 1
    _ok(); flash(f'Removed "{a.title}" from {count} player{"s" if count != 1 else ""}.', 'success')
    return redirect(url_for('admin.adm_achs'))


@admin_bp.route('/admin/audit')
@_admin
def adm_audit(): return render_template('admin_audit.html',aus=Audit.query.filter_by(state='pending').all())

@admin_bp.route('/admin/audit/<int:aid>/resolve', methods=['POST'])
@_admin
def adm_resolve(aid):
    au=Audit.query.get_or_404(aid); m=au.match; act=request.form.get('act')
    is_noshow = 'No-show' in (au.reason or '') or '⚠️ NO-SHOW' in (m.notes or '')
    if act=='approve':
        m.state='verified'; m.verify_by=current_user.id
        au.state='resolved_approve'; au.resolved_by=current_user.id; au.resolved_at=datetime.now(timezone.utc); _ok()
        if m.ranked: _proc_r(m)
        else: _proc_u(m)
        _resolve_bets(m)
        if m.tourney_id:
            tourney=Tournament.query.get(m.tourney_id)
            if tourney: _check_tourney_completion(tourney)
        if is_noshow:
            winner=db.session.get(User, m.winner_id) if m.winner_id else None
            loser_id=m.p2_id if m.winner_id==m.p1_id else m.p1_id
            if winner: _alert(winner.id, '✅ No-Show Confirmed', f'The no-show report was approved. You win the match!', 'success', url_for('matches.match_view',mid=m.id))
            _alert(loser_id, '⚠️ No-Show Confirmed', f'You were confirmed as no-show. The match was awarded to your opponent.', 'danger', url_for('matches.match_view',mid=m.id)); _ok()
        else:
            _alert(m.p1_id, 'Dispute Resolved', f'Match #{m.id} was approved by admin.', 'success', url_for('matches.match_view',mid=m.id))
            _alert(m.p2_id, 'Dispute Resolved', f'Match #{m.id} was approved by admin.', 'success', url_for('matches.match_view',mid=m.id)); _ok()
        flash('Approved.','success')
    elif act=='reject':
        au.state='resolved_reject'; au.resolved_by=current_user.id; au.resolved_at=datetime.now(timezone.utc)
        _refund_match_bets(m)
        if m.tourney_id: m.state='scheduled'; m.p1_score=0; m.p2_score=0; m.winner_id=None; m.draw=False; m.submit_by=None; m.verify_by=None; m.notes=None; m.winner_comment=None
        else: m.state='rejected'
        _ok()
        if is_noshow:
            reporter_id=au.by_id; other_id=m.p2_id if reporter_id==m.p1_id else m.p1_id
            _alert(reporter_id, '❌ No-Show Rejected', f'Your no-show report was rejected by admin. The match must be replayed.', 'warning', url_for('matches.match_view',mid=m.id))
            _alert(other_id, 'No-Show Rejected', f'A no-show report against you was rejected.', 'info', url_for('matches.match_view',mid=m.id)); _ok()
        else:
            _alert(m.p1_id, 'Dispute Rejected', f'Match #{m.id} was rejected by admin.', 'warning', url_for('matches.match_view',mid=m.id))
            _alert(m.p2_id, 'Dispute Rejected', f'Match #{m.id} was rejected by admin.', 'warning', url_for('matches.match_view',mid=m.id)); _ok()
        flash('Rejected.','info')
    return redirect(url_for('admin.adm_audit'))

@admin_bp.route('/admin/news')
@_admin
def adm_news():
    arts=News.query.order_by(News.created_at.desc()).limit(100).all()
    return render_template('admin_news.html',arts=arts)

@admin_bp.route('/admin/clans')
@_admin
def adm_clans():
    clans=Clan.query.order_by(Clan.created_at.desc()).all()
    return render_template('admin_clans.html',clans=clans)

@admin_bp.route('/admin/clans/<int:cid>/edit', methods=['GET','POST'])
@_admin
def adm_clan_edit(cid):
    c=Clan.query.get_or_404(cid)
    if request.method=='POST':
        new_name=request.form.get('name','').strip(); new_tag=request.form.get('tag','').strip().upper()
        if new_name and new_name!=c.name:
            if Clan.query.filter(Clan.name==new_name,Clan.id!=c.id).first(): flash('Name taken.','danger'); return redirect(url_for('admin.adm_clan_edit',cid=cid))
            c.name=new_name
        if new_tag and len(new_tag)==4 and new_tag!=c.tag:
            if Clan.query.filter(Clan.tag==new_tag,Clan.id!=c.id).first(): flash('Tag taken.','danger'); return redirect(url_for('admin.adm_clan_edit',cid=cid))
            c.tag=new_tag
        c.description=request.form.get('description','').strip() or None
        c.color_primary=request.form.get('color_primary','#6c5ce7'); c.color_secondary=request.form.get('color_secondary','#1e1e2e')
        c.recruiting='recruiting' in request.form; c.invite_only='invite_only' in request.form
        c.active='active' in request.form; c.max_members=request.form.get('max_members',50,type=int)
        sc=request.form.get('score',type=int)
        if sc is not None: c.score=sc
        new_owner=request.form.get('owner_id',type=int)
        if new_owner and new_owner!=c.owner_id:
            ex=db.session.execute(clan_members.select().where(and_(clan_members.c.user_id==new_owner,clan_members.c.clan_id==cid))).first()
            if ex: c.owner_id=new_owner
            else: flash('New owner must be a member.','danger'); return redirect(url_for('admin.adm_clan_edit',cid=cid))
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
        _ok(); flash('Clan updated!','success'); return redirect(url_for('admin.adm_clans'))
    members=c.members.all()
    return render_template('admin_clan_edit.html',c=c,members=members)


@admin_bp.route('/admin/clans/<int:cid>/delete', methods=['POST'])
@_admin
def adm_clan_del(cid):
    c=Clan.query.get_or_404(cid)
    db.session.execute(clan_members.delete().where(clan_members.c.clan_id==cid)); _ok()
    for attr in ['logo','bg_image']:
        img=getattr(c,attr)
        if img:
            old=os.path.join(app.config['UPLOAD_FOLDER'],img)
            if os.path.isfile(old):
                try: os.remove(old)
                except OSError: pass
    db.session.delete(c); _ok(); flash('Clan deleted.','success'); return redirect(url_for('admin.adm_clans'))

@admin_bp.route('/admin/clans/<int:cid>/kick/<int:uid>', methods=['POST'])
@_admin
def adm_clan_kick(cid, uid):
    c=Clan.query.get_or_404(cid)
    if uid==c.owner_id: flash('Cannot kick owner.','danger'); return redirect(url_for('admin.adm_clan_edit',cid=cid))
    db.session.execute(clan_members.delete().where(and_(clan_members.c.user_id==uid,clan_members.c.clan_id==cid))); _ok()
    target=User.query.get(uid)
    _alert(uid,'Removed from Clan',f'Admin removed you from [{c.tag}] {c.name}.','danger'); _ok()
    flash(f'Kicked {target.name() if target else uid}.','success'); return redirect(url_for('admin.adm_clan_edit',cid=cid))

@admin_bp.route('/admin/alerts', methods=['GET','POST'])
@_admin
def adm_alerts():
    form=AdminAlertForm()
    users=User.query.filter_by(banned=False).order_by(User.username).all()
    form.target.choices=[(-2,'📢 Everyone (persistent)'),(-1,'📨 Everyone (one-time)')]+[(u.id,u.username) for u in users]
    if form.validate_on_submit():
        if form.target.data==-2:
            ga=GlobalAlert(title=form.title.data,message=form.message.data,cat=form.cat.data,link=None,created_by=current_user.id)
            db.session.add(ga); _ok(); flash('Global alert created!','success')
        elif form.target.data==-1:
            ct=0
            for u in User.query.filter_by(banned=False).all():
                db.session.add(Alert(user_id=u.id,title=form.title.data,message=form.message.data,cat=form.cat.data)); ct+=1
            _ok(); flash(f'Sent to {ct} users!','success')
        else:
            db.session.add(Alert(user_id=form.target.data,title=form.title.data,message=form.message.data,cat=form.cat.data)); _ok()
            tu=db.session.get(User,form.target.data); flash(f'Sent to {tu.username}!','success')
        return redirect(url_for('admin.adm_alerts'))
    return render_template('admin_alerts.html',form=form,recent=Alert.query.order_by(Alert.created_at.desc()).limit(30).all(),globals=GlobalAlert.query.filter_by(active=True).order_by(GlobalAlert.created_at.desc()).all())

@admin_bp.route('/admin/alerts/global/<int:gid>/del', methods=['POST'])
@_admin
def adm_del_ga(gid):
    ga=GlobalAlert.query.get_or_404(gid); ga.active=False; _ok(); flash('Removed.','success'); return redirect(url_for('admin.adm_alerts'))

@admin_bp.route('/admin/alerts/<int:aid>/del', methods=['POST'])
@_admin
def adm_del_al(aid):
    a=Alert.query.get_or_404(aid); db.session.delete(a); _ok(); flash('Deleted.','success'); return redirect(url_for('admin.adm_alerts'))

@admin_bp.route('/admin/alerts/<int:aid>/edit', methods=['GET','POST'])
@_admin
def adm_edit_al(aid):
    a=Alert.query.get_or_404(aid)
    if request.method=='POST':
        a.title=request.form.get('title',a.title).strip(); a.message=request.form.get('message',a.message).strip()
        a.cat=request.form.get('cat',a.cat); _ok(); flash('Alert updated.','success'); return redirect(url_for('admin.adm_alerts'))
    return render_template('admin_alert_edit.html',a=a)

@admin_bp.route('/admin/alerts/global/<int:gid>/edit', methods=['GET','POST'])
@_admin
def adm_edit_ga(gid):
    ga=GlobalAlert.query.get_or_404(gid)
    if request.method=='POST':
        ga.title=request.form.get('title',ga.title).strip(); ga.message=request.form.get('message',ga.message).strip()
        ga.cat=request.form.get('cat',ga.cat); _ok(); flash('Global alert updated.','success'); return redirect(url_for('admin.adm_alerts'))
    return render_template('admin_galert_edit.html',ga=ga)

@admin_bp.route('/admin/alerts/global/<int:gid>/dismiss', methods=['POST'])
@login_required
def dismiss_global(gid):
    dismissed = session.get('dismissed_globals', [])
    if gid not in dismissed: dismissed.append(gid)
    session['dismissed_globals'] = dismissed
    return redirect(request.referrer or url_for('main.home'))

@admin_bp.route('/admin/alerts/clear_all', methods=['POST'])
@_admin
def adm_clear_all_alerts():
    target=request.form.get('target','all')
    if target=='all_personal': count=Alert.query.count(); Alert.query.delete(); _ok(); flash(f'Deleted {count} personal alerts.','success')
    elif target=='all_global': count=GlobalAlert.query.filter_by(active=True).count(); GlobalAlert.query.filter_by(active=True).update({'active':False}); _ok(); flash(f'Disabled {count} global alerts.','success')
    elif target=='all_unread': count=Alert.query.filter_by(read=False).count(); Alert.query.filter_by(read=False).update({'read':True}); _ok(); flash(f'Marked {count} alerts as read.','success')
    elif target=='everything': ga_count=GlobalAlert.query.count(); a_count=Alert.query.count(); Alert.query.delete(); GlobalAlert.query.delete(); _ok(); flash(f'Nuked everything: {a_count} personal + {ga_count} global alerts deleted.','success')
    else: flash('Unknown target.','danger')
    return redirect(url_for('admin.adm_alerts'))


@admin_bp.route('/admin/tournaments')
@_admin
def adm_tourneys():
    ts=Tournament.query.order_by(Tournament.created_at.desc()).all()
    return render_template('admin_tourneys.html',ts=ts)

@admin_bp.route('/admin/tournaments/<int:tid>/edit', methods=['GET','POST'])
@_admin
def adm_tourney_edit(tid):
    tourney=Tournament.query.get_or_404(tid)
    if request.method=='POST':
        tourney.name=request.form.get('name',tourney.name).strip()
        tourney.description=request.form.get('description','').strip() or None
        tourney.game=request.form.get('game','').strip() or None
        tourney.fmt=request.form.get('fmt',tourney.fmt)
        tourney.max_players=request.form.get('max_players',32,type=int)
        tourney.prize=request.form.get('prize','').strip() or None
        tourney.rules=request.form.get('rules','').strip() or None
        tourney.ranked='ranked' in request.form; tourney.status=request.form.get('status',tourney.status)
        tourney.seeding_mode=request.form.get('seeding_mode','elo')
        tourney.default_series=request.form.get('default_series','bo1')
        tourney.verify_timeout_days=request.form.get('verify_timeout_days',0,type=int)
        tourney.color_primary=request.form.get('color_primary','#6c5ce7')
        tourney.color_secondary=request.form.get('color_secondary','#1e1e2e')
        try: tourney.start_dt=datetime.strptime(request.form.get('start_dt',''),'%Y-%m-%dT%H:%M')
        except ValueError: pass
        try: tourney.reg_deadline=datetime.strptime(request.form.get('reg_deadline',''),'%Y-%m-%dT%H:%M')
        except ValueError: pass
        logo=request.files.get('logo')
        if logo and logo.filename:
            p=_simg(logo,'tournaments',256)
            if p:
                if tourney.logo:
                    old=os.path.join(app.config['UPLOAD_FOLDER'],tourney.logo)
                    if os.path.isfile(old):
                        try: os.remove(old)
                        except OSError: pass
                tourney.logo=p
        banner=request.files.get('banner_image')
        if banner and banner.filename:
            p=_simg(banner,'tournaments',1920)
            if p:
                if tourney.banner_image:
                    old=os.path.join(app.config['UPLOAD_FOLDER'],tourney.banner_image)
                    if os.path.isfile(old):
                        try: os.remove(old)
                        except OSError: pass
                tourney.banner_image=p
        _ok(); flash('Tournament updated!','success'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    all_users=User.query.filter_by(banned=False).order_by(User.username).all()
    bracket={}
    if tourney.bracket_generated:
        rounds = db.session.query(Match.round_num).filter(Match.tourney_id==tid, Match.round_num.isnot(None)).distinct().order_by(Match.round_num).all()
        for (rnd,) in rounds: bracket[rnd]=tourney.matches.filter_by(round_num=rnd).order_by(Match.bracket_pos).all()
    players_sorted=tourney.players.order_by(User.elo.desc()).all()
    advice=_bracket_advice(tourney.player_count) if not tourney.bracket_generated and tourney.player_count>=2 else None
    return render_template('admin_tourney_edit.html',tourney=tourney,all_users=all_users,bracket=bracket,players_sorted=players_sorted,advice=advice)

@admin_bp.route('/admin/tournaments/<int:tid>/generate', methods=['POST'])
@_admin
def adm_tourney_generate(tid):
    tourney=Tournament.query.get_or_404(tid)
    if tourney.bracket_generated: flash('Already generated. Reset first.','warning'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    if tourney.player_count<2: flash('Need 2+ players.','danger'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    bracket_type = request.form.get('bracket_type', 'standard'); success = False
    if bracket_type == 'play_in': success = _generate_play_in(tourney); msg='Play-in round generated! Bottom seeds must play first.'
    elif bracket_type == 'round_robin': success = _generate_round_robin(tourney); msg='Round robin schedule generated!'
    else: success = _generate_bracket(tourney); msg='Standard bracket generated!'
    if success:
        flash(msg,'success')
        for p in tourney.players.all():
            _alert(p.id,'Tournament Started!',f'{tourney.name} has begun!','success',url_for('tournaments.t_view',tid=tid))
            _activity('tournament', current_user.id, f'Started tournament: {tourney.name}', 'flag-checkered', 'success', url_for('tournaments.t_view',tid=tid)); _ok()
    else: flash('Failed to generate bracket.','danger')
    return redirect(url_for('admin.adm_tourney_edit',tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/add_player', methods=['POST'])
@_admin
def adm_tourney_add_player(tid):
    tourney=Tournament.query.get_or_404(tid); uid=request.form.get('user_id',type=int)
    if not uid: flash('No user selected.','danger'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    u=User.query.get_or_404(uid)
    if u in tourney.players.all(): flash('Already registered.','info'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    if tourney.is_full: flash('Tournament full.','warning'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    tourney.players.append(u); _ok(); flash(f'Added {u.name()}.','success'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/remove_player/<int:uid>', methods=['POST'])
@_admin
def adm_tourney_remove_player(tid, uid):
    tourney=Tournament.query.get_or_404(tid)
    if tourney.bracket_generated: flash('Cannot remove players after bracket generated.','danger'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))
    u=User.query.get_or_404(uid)
    if u in tourney.players.all(): tourney.players.remove(u); _ok(); flash(f'Removed {u.name()}.','success')
    return redirect(url_for('admin.adm_tourney_edit',tid=tid))


@admin_bp.route('/admin/tournaments/<int:tid>/edit_match/<int:mid>', methods=['POST'])
@_admin
def adm_tourney_match_edit(tid, mid):
    tourney=Tournament.query.get_or_404(tid); m=Match.query.get_or_404(mid)
    if m.tourney_id!=tid: abort(404)
    old_state=m.state
    m.p1_score=request.form.get('p1_score',0,type=int); m.p2_score=request.form.get('p2_score',0,type=int)
    new_state=request.form.get('state',m.state)
    if m.p1_score>m.p2_score: m.winner_id=m.p1_id; m.draw=False
    elif m.p2_score>m.p1_score: m.winner_id=m.p2_id; m.draw=False
    else: m.draw=True; m.winner_id=None
    m.state=new_state; m.verify_by=current_user.id; _ok()
    if new_state=='verified' and old_state!='verified':
        if m.ranked: _proc_r(m)
        else: _proc_u(m)
    if new_state=='verified': _check_tourney_completion(tourney)
    flash(f'Match #{m.id} updated.','success'); return redirect(url_for('admin.adm_tourney_edit',tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/swap_match/<int:mid>', methods=['POST'])
@_admin
def adm_tourney_match_swap(tid, mid):
    Tournament.query.get_or_404(tid); m=Match.query.get_or_404(mid)
    if m.tourney_id!=tid: abort(404)
    new_p1=request.form.get('p1_id',type=int); new_p2=request.form.get('p2_id',type=int)
    if new_p1 and new_p2 and new_p1!=new_p2 and m.state=='scheduled':
        m.p1_id=new_p1; m.p2_id=new_p2; _ok(); flash(f'Match #{m.id} players swapped.','success')
    else: flash('Cannot swap: match must be scheduled, players must be different.','danger')
    return redirect(url_for('admin.adm_tourney_edit',tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/swap_matches', methods=['POST'])
@_admin
def adm_tourney_swap_matches(tid):
    Tournament.query.get_or_404(tid)
    m1_id = request.form.get('match1_id', type=int); m2_id = request.form.get('match2_id', type=int)
    if not m1_id or not m2_id or m1_id == m2_id:
        flash('Select two different matches to swap.', 'danger'); return redirect(url_for('admin.adm_tourney_edit', tid=tid))
    m1 = Match.query.get_or_404(m1_id); m2 = Match.query.get_or_404(m2_id)
    if m1.tourney_id != tid or m2.tourney_id != tid: abort(404)
    t_p1=m1.p1_id;t_p2=m1.p2_id;t_s1=m1.p1_score;t_s2=m1.p2_score;t_w=m1.winner_id;t_d=m1.draw
    t_st=m1.state;t_sb=m1.submit_by;t_vb=m1.verify_by;t_n=m1.notes;t_wc=m1.winner_comment;t_ed1=m1.elo_d1;t_ed2=m1.elo_d2
    m1.p1_id=m2.p1_id;m1.p2_id=m2.p2_id;m1.p1_score=m2.p1_score;m1.p2_score=m2.p2_score;m1.winner_id=m2.winner_id;m1.draw=m2.draw
    m1.state=m2.state;m1.submit_by=m2.submit_by;m1.verify_by=m2.verify_by;m1.notes=m2.notes;m1.winner_comment=m2.winner_comment;m1.elo_d1=m2.elo_d1;m1.elo_d2=m2.elo_d2
    m2.p1_id=t_p1;m2.p2_id=t_p2;m2.p1_score=t_s1;m2.p2_score=t_s2;m2.winner_id=t_w;m2.draw=t_d
    m2.state=t_st;m2.submit_by=t_sb;m2.verify_by=t_vb;m2.notes=t_n;m2.winner_comment=t_wc;m2.elo_d1=t_ed1;m2.elo_d2=t_ed2
    _ok(); flash('Swapped bracket positions.', 'success')
    return redirect(url_for('admin.adm_tourney_edit', tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/batch_edit/<int:rnd>', methods=['POST'])
@_admin
def adm_tourney_batch_edit(tid, rnd):
    tourney=Tournament.query.get_or_404(tid); match_ids = request.form.getlist('match_ids'); changes = 0
    for mid_str in match_ids:
        mid = int(mid_str); m = Match.query.get(mid)
        if not m or m.tourney_id != tid: continue
        new_p1=request.form.get(f'p1_{mid}',type=int); new_p2=request.form.get(f'p2_{mid}',type=int)
        new_s1=request.form.get(f's1_{mid}',type=int); new_s2=request.form.get(f's2_{mid}',type=int)
        new_st=request.form.get(f'st_{mid}',m.state); old_state=m.state; changed=False
        if new_p1 and new_p2 and new_p1!=new_p2:
            if new_p1!=m.p1_id or new_p2!=m.p2_id:
                if m.state in ['scheduled','pending','disputed']: m.p1_id=new_p1; m.p2_id=new_p2; changed=True
        if new_s1 is not None and new_s2 is not None:
            if new_s1!=m.p1_score or new_s2!=m.p2_score: m.p1_score=new_s1; m.p2_score=new_s2; changed=True
        if m.p1_score>m.p2_score: m.winner_id=m.p1_id; m.draw=False
        elif m.p2_score>m.p1_score: m.winner_id=m.p2_id; m.draw=False
        else: m.draw=True; m.winner_id=None
        if new_st!=m.state: m.state=new_st; changed=True
        if changed:
            m.verify_by=current_user.id; changes+=1
            if new_st=='verified' and old_state!='verified':
                if m.ranked: _proc_r(m)
                else: _proc_u(m)
    _ok()
    if any(request.form.get(f'st_{mid}')=='verified' for mid in match_ids): _check_tourney_completion(tourney)
    flash(f'Saved {changes} change{"s" if changes != 1 else ""} in {tourney.round_name(rnd)}.', 'success')
    return redirect(url_for('admin.adm_tourney_edit', tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/reset_bracket', methods=['POST'])
@_admin
def adm_tourney_reset(tid):
    tourney=Tournament.query.get_or_404(tid)
    for m in tourney.matches.filter_by(state='verified').all():
        if m.notes=='Bye' or m.p1_id==m.p2_id: continue
        p1=db.session.get(User,m.p1_id); p2=db.session.get(User,m.p2_id)
        if not p1 or not p2: continue
        if m.ranked:
            p1.elo-=m.elo_d1; p2.elo-=m.elo_d2; p1.elo_matches=max(0,p1.elo_matches-1); p2.elo_matches=max(0,p2.elo_matches-1)
            if m.draw: p1.r_draws=max(0,p1.r_draws-1); p2.r_draws=max(0,p2.r_draws-1)
            elif m.winner_id==m.p1_id: p1.r_wins=max(0,p1.r_wins-1); p2.r_losses=max(0,p2.r_losses-1)
            elif m.winner_id==m.p2_id: p2.r_wins=max(0,p2.r_wins-1); p1.r_losses=max(0,p1.r_losses-1)
            for p in [p1,p2]:
                ch_=m.elo_d1 if p.id==m.p1_id else m.elo_d2
                if ch_>0:
                    for c in p.clans.all(): c.score=max(0,c.score-ch_)
            EloSnap.query.filter_by(match_id=m.id).delete()
        else:
            if m.draw: p1.u_draws=max(0,p1.u_draws-1); p2.u_draws=max(0,p2.u_draws-1)
            elif m.winner_id==m.p1_id: p1.u_wins=max(0,p1.u_wins-1); p2.u_losses=max(0,p2.u_losses-1)
            elif m.winner_id==m.p2_id: p2.u_wins=max(0,p2.u_wins-1); p1.u_losses=max(0,p1.u_losses-1)
    _ok()
    for m in tourney.matches.all(): _refund_match_bets(m)
    _ok()
    for m in tourney.matches.all(): db.session.delete(m)
    tourney.bracket_generated=False; tourney.current_round=0; tourney.status='upcoming'; _ok()
    for p in tourney.players.all(): _recalc_streak(p)
    flash('Bracket reset. All match results reversed and player stats restored.', 'success')
    return redirect(url_for('admin.adm_tourney_edit', tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/partial_advance', methods=['POST'])
@_admin
def adm_tourney_partial_advance(tid):
    tourney = Tournament.query.get_or_404(tid)
    if tourney.status != 'active':
        flash('Tournament is not active.', 'warning')
        return redirect(url_for('admin.adm_tourney_edit', tid=tid))
    if not tourney.bracket_generated:
        flash('Bracket not generated yet.', 'warning')
        return redirect(url_for('admin.adm_tourney_edit', tid=tid))
    if tourney.fmt == 'round_robin':
        flash('Partial advancement is not available for round robin tournaments.', 'warning')
        return redirect(url_for('admin.adm_tourney_edit', tid=tid))
    cr = tourney.current_round
    verified_count = tourney.matches.filter_by(round_num=cr, state='verified').count()
    if verified_count == 0:
        flash('No verified matches in the current round to advance.', 'danger')
        return redirect(url_for('admin.adm_tourney_edit', tid=tid))
    count = _partial_advance_round(tourney)
    if count > 0:
        _activity('tournament', current_user.id,
                  f'Partial advance: {count} next-round match{"es" if count != 1 else ""} created in {tourney.name}',
                  'forward', 'info', url_for('tournaments.t_view', tid=tourney.id))
        _ok()
        flash(f'Partial advance: {count} next-round match{"es" if count != 1 else ""} created.', 'success')
    else:
        flash('No new matches to create. Either all eligible matches already exist or no completed pairs found.', 'info')
    return redirect(url_for('admin.adm_tourney_edit', tid=tid))

@admin_bp.route('/admin/tournaments/<int:tid>/delete', methods=['POST'])
@_admin
def adm_tourney_del(tid):
    tourney=Tournament.query.get_or_404(tid)
    for m in tourney.matches.filter_by(state='verified').all():
        if m.notes=='Bye' or m.p1_id==m.p2_id: continue
        p1=db.session.get(User,m.p1_id); p2=db.session.get(User,m.p2_id)
        if not p1 or not p2: continue
        if m.ranked:
            p1.elo-=m.elo_d1; p2.elo-=m.elo_d2; p1.elo_matches=max(0,p1.elo_matches-1); p2.elo_matches=max(0,p2.elo_matches-1)
            if m.draw: p1.r_draws=max(0,p1.r_draws-1); p2.r_draws=max(0,p2.r_draws-1)
            elif m.winner_id==m.p1_id: p1.r_wins=max(0,p1.r_wins-1); p2.r_losses=max(0,p2.r_losses-1)
            elif m.winner_id==m.p2_id: p2.r_wins=max(0,p2.r_wins-1); p1.r_losses=max(0,p1.r_losses-1)
            for p in [p1,p2]:
                ch_=m.elo_d1 if p.id==m.p1_id else m.elo_d2
                if ch_>0:
                    for c in p.clans.all(): c.score=max(0,c.score-ch_)
            EloSnap.query.filter_by(match_id=m.id).delete()
        else:
            if m.draw: p1.u_draws=max(0,p1.u_draws-1); p2.u_draws=max(0,p2.u_draws-1)
            elif m.winner_id==m.p1_id: p1.u_wins=max(0,p1.u_wins-1); p2.u_losses=max(0,p2.u_losses-1)
            elif m.winner_id==m.p2_id: p2.u_wins=max(0,p2.u_wins-1); p1.u_losses=max(0,p1.u_losses-1)
    _ok()
    affected_players=list(tourney.players.all())
    for m in tourney.matches.all(): _refund_match_bets(m)
    _ok()
    for m in tourney.matches.all(): db.session.delete(m)
    _ok()
    db.session.execute(tourney_players.delete().where(tourney_players.c.tournament_id==tid)); _ok()
    db.session.delete(tourney); _ok()
    for p in affected_players: _recalc_streak(p)
    flash('Tournament deleted. All match results reversed and player stats restored.', 'success')
    return redirect(url_for('admin.adm_tourneys'))


@admin_bp.route('/admin/settings/verify_timeout', methods=['POST'])
@_admin
def adm_set_verify_timeout():
    val=request.form.get('default_verify_timeout_days',0,type=int)
    if val<0: val=0
    setting=AppSetting.query.filter_by(key='default_verify_timeout_days').first()
    if setting: setting.value=str(val)
    else: db.session.add(AppSetting(key='default_verify_timeout_days',value=str(val)))
    _ok(); flash(f'Default verification timeout set to {val} day(s).','success')
    return redirect(url_for('admin.adm'))

@admin_bp.route('/admin/seasons')
@_admin
def adm_seasons():
    active_season=Season.query.filter_by(active=True).first()
    past_seasons=Season.query.filter_by(active=False).order_by(Season.ended_at.desc()).all()
    stats={'players':0,'matches':0,'tournaments':0,'avg_elo':1200}; top_players=[]
    if active_season:
        players=User.query.filter_by(banned=False).all()
        ranked_players=[p for p in players if p.elo_matches>0]
        stats['players']=len(ranked_players)
        stats['matches']=Match.query.filter(Match.state=='verified',Match.played_at>=active_season.started_at).count()
        stats['tournaments']=Tournament.query.filter(Tournament.created_at>=active_season.started_at).count()
        if ranked_players: stats['avg_elo']=int(sum(p.elo for p in ranked_players)/len(ranked_players))
        top_players=User.query.filter_by(banned=False).order_by(User.elo.desc()).limit(10).all()
    return render_template('admin_seasons.html',active_season=active_season,past_seasons=past_seasons,stats=stats,top_players=top_players)

@admin_bp.route('/admin/seasons/start', methods=['POST'])
@_admin
def adm_season_start():
    if Season.query.filter_by(active=True).first(): flash('A season is already active. End it first.','danger'); return redirect(url_for('admin.adm_seasons'))
    name=request.form.get('name','').strip(); notes=request.form.get('notes','').strip() or None
    if not name: flash('Season name required.','danger'); return redirect(url_for('admin.adm_seasons'))
    last=Season.query.order_by(Season.number.desc()).first(); num=(last.number+1) if last else 1
    s=Season(name=name,number=num,notes=notes,created_by=current_user.id,active=True)
    db.session.add(s); _ok()
    _activity('season', current_user.id, f'Started new season: {name}', 'calendar-alt', 'success', url_for('seasons_bp.seasons')); _ok()
    for u in User.query.filter_by(banned=False).all():
        _alert(u.id, f'🏁 {name} Started!', f'Season {num} has begun! Good luck!', 'success', url_for('seasons_bp.seasons')); _ok()
    flash(f'{name} started!','success'); return redirect(url_for('admin.adm_seasons'))

@admin_bp.route('/admin/seasons/end', methods=['POST'])
@_admin
def adm_season_end():
    active=Season.query.filter_by(active=True).first()
    if not active: flash('No active season.','warning'); return redirect(url_for('admin.adm_seasons'))
    players=User.query.filter_by(banned=False).order_by(User.elo.desc()).all(); pos=0
    for p in players:
        pos+=1
        archive=SeasonArchive(season_id=active.id, user_id=p.id, final_elo=p.elo, final_rank=p.rank_title,
            r_wins=p.r_wins, r_losses=p.r_losses, r_draws=p.r_draws, u_wins=p.u_wins, u_losses=p.u_losses, u_draws=p.u_draws,
            best_streak=p.best_streak, elo_matches=p.elo_matches, leaderboard_pos=pos)
        db.session.add(archive)
    _ok()
    top3=players[:3] if len(players)>=3 else players
    top3_text=', '.join([f'#{i+1} {p.name()} ({p.elo})' for i,p in enumerate(top3)])
    for p in players:
        p.elo=1200; p.elo_matches=0; p.r_wins=0; p.r_losses=0; p.r_draws=0
        p.u_wins=0; p.u_losses=0; p.u_draws=0; p.streak=0; p.best_streak=0
    _ok()
    EloSnap.query.delete(); _ok()
    for p in players: db.session.add(EloSnap(user_id=p.id,elo_val=1200))
    _ok()
    active.active=False; active.ended_at=datetime.now(timezone.utc); _ok()
    n=News(title=f'🏁 {active.name} Has Ended!',summary=f'Season {active.number} is over! Final standings: {top3_text}',
        content=f'<p><strong>{active.name}</strong> has concluded!</p><p>Final top 3: {top3_text}</p><p>All stats have been reset for the next season. Check the <a href="/seasons/{active.id}">full standings</a> to see where you finished.</p>',
        category='tournament', published=True, pinned=True, author_id=current_user.id)
    n.make_slug(); db.session.add(n); _ok()
    _activity('season', current_user.id, f'{active.name} has ended! All stats reset.', 'flag-checkered', 'info', url_for('seasons_bp.season_view',sid=active.id)); _ok()
    for p in players:
        pos_archive=SeasonArchive.query.filter_by(season_id=active.id,user_id=p.id).first()
        pos_text=f' You finished #{pos_archive.leaderboard_pos} with {pos_archive.final_elo} ELO.' if pos_archive else ''
        _alert(p.id, f'🏁 {active.name} Ended!', f'The season is over!{pos_text} All stats have been reset.', 'info', url_for('seasons_bp.season_view',sid=active.id)); _ok()
    flash(f'{active.name} ended! All stats reset. Archives saved.','success'); return redirect(url_for('admin.adm_seasons'))

@admin_bp.route('/admin/seasons/<int:sid>')
@_admin
def adm_season_view(sid):
    season=Season.query.get_or_404(sid)
    archives=SeasonArchive.query.filter_by(season_id=sid).order_by(SeasonArchive.final_elo.desc()).all()
    podium=archives[:3] if len(archives)>=3 else archives
    top_elo=archives[0].final_elo if archives else 0
    total_matches=sum(a.r_wins+a.r_losses+a.r_draws for a in archives)//2 if archives else 0
    avg_elo=int(sum(a.final_elo for a in archives)/len(archives)) if archives else 1200
    return render_template('admin_season_view.html',season=season,archives=archives,podium=podium,top_elo=top_elo,total_matches=total_matches,avg_elo=avg_elo)


# ===========================================================================
# DATABASE BACKUPS
# ===========================================================================
@admin_bp.route('/admin/backups')
@_admin
def adm_backups():
    backups = _list_backups()
    return render_template('admin_backups.html', backups=backups)

@admin_bp.route('/admin/backups/create', methods=['POST'])
@_admin
def adm_backup_create():
    fname = _create_backup()
    if fname:
        flash(f'Backup created: {fname}', 'success')
    else:
        flash('Could not create backup. Database may be in use.', 'danger')
    return redirect(url_for('admin.adm_backups'))

@admin_bp.route('/admin/backups/<filename>/restore', methods=['POST'])
@_admin
def adm_backup_restore(filename):
    if _restore_backup(filename):
        flash(f'Database restored from {filename}. A pre-rollback backup was created.', 'success')
    else:
        flash('Backup file is missing or corrupted.', 'danger')
    return redirect(url_for('admin.adm_backups'))

@admin_bp.route('/admin/backups/<filename>/delete', methods=['POST'])
@_admin
def adm_backup_delete(filename):
    if _delete_backup(filename):
        flash(f'Backup {filename} deleted.', 'success')
    else:
        flash('Could not delete backup.', 'danger')
    return redirect(url_for('admin.adm_backups'))


# ===========================================================================
# COSMETIC ITEMS ADMIN
# ===========================================================================
@admin_bp.route('/admin/cosmetics')
@_admin
def adm_cosmetics():
    page = request.args.get('page', 1, type=int)
    cat = request.args.get('category', '').strip()
    rarity = request.args.get('rarity', '').strip()
    q = CosmeticItem.query
    if cat:
        q = q.filter(CosmeticItem.category == cat)
    if rarity:
        q = q.filter(CosmeticItem.rarity == rarity)
    q = q.order_by(CosmeticItem.created_at.desc())
    pagination = q.paginate(page=page, per_page=25, error_out=False)
    # Build template names per category for the generator UI
    generator_templates = {c: list(_GENERATOR_TEMPLATES.get(c, {}).keys()) for c in COSMETIC_CATEGORIES}
    return render_template('admin_cosmetics.html', items=pagination.items, pagination=pagination,
                           category=cat, rarity=rarity,
                           categories=COSMETIC_CATEGORIES, rarity_tiers=RARITY_TIERS,
                           rarity_colors=RARITY_COLORS, effect_types=EFFECT_TYPES,
                           effect_modes=EFFECT_MODES,
                           generator_templates=generator_templates,
                           rarity_price_ranges=RARITY_PRICE_RANGES)

@admin_bp.route('/admin/cosmetics/create', methods=['POST'])
@_admin
def adm_cosmetic_create():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name is required.', 'danger')
        return redirect(url_for('admin.adm_cosmetics'))
    item = CosmeticItem(
        name=name,
        description=request.form.get('description', '').strip() or None,
        category=request.form.get('category', 'misc').strip(),
        rarity=request.form.get('rarity', 'common').strip(),
        effect_type=request.form.get('effect_type', 'none').strip(),
        effect_mode=request.form.get('effect_mode', 'css').strip(),
        price=request.form.get('price', 0, type=int),
        css_data=request.form.get('css_data', '').strip() or None,
        active='active' in request.form
    )
    img = request.files.get('image')
    if img and img.filename:
        p = _simg(img, 'misc')
        if p:
            item.image = p
    db.session.add(item)
    _ok()
    flash(f'Cosmetic item "{name}" created.', 'success')
    return redirect(url_for('admin.adm_cosmetics'))

@admin_bp.route('/admin/cosmetics/seed', methods=['POST'])
@_admin
def adm_cosmetic_seed():
    inserted = 0
    skipped = 0
    for item_data in SEED_COSMETIC_ITEMS:
        if CosmeticItem.query.filter_by(name=item_data['name']).first():
            skipped += 1
            continue
        item = CosmeticItem(
            name=item_data['name'],
            description=item_data.get('description'),
            category=item_data['category'],
            price=item_data.get('price', 0),
            rarity=item_data.get('rarity', 'common'),
            effect_type=item_data.get('effect_type', 'none'),
            effect_mode=item_data.get('effect_mode', 'css'),
            css_data=item_data.get('css_data'),
            active=True
        )
        db.session.add(item)
        inserted += 1
    _ok()
    flash(f'Seed complete: {inserted} inserted, {skipped} skipped (already exist).', 'success')
    return redirect(url_for('admin.adm_cosmetics'))

@admin_bp.route('/admin/cosmetics/generate', methods=['POST'])
@_admin
def adm_cosmetic_generate():
    category = request.form.get('category', '').strip()
    template = request.form.get('template', '').strip()
    count = request.form.get('count', 1, type=int)
    count = max(1, min(10, count))
    created = 0
    for _ in range(count):
        result = generate_cosmetic_item(category, template)
        if result is None:
            flash(f'Invalid category or template: {category}/{template}', 'danger')
            return redirect(url_for('admin.adm_cosmetics'))
        item = CosmeticItem(
            name=result['name'],
            description=result.get('description'),
            category=result['category'],
            price=result.get('price', 0),
            rarity=result.get('rarity', 'common'),
            effect_type=result.get('effect_type', 'none'),
            effect_mode=result.get('effect_mode', 'css'),
            css_data=result.get('css_data'),
            active=True
        )
        db.session.add(item)
        created += 1
    _ok()
    flash(f'{created} cosmetic item{"s" if created != 1 else ""} generated.', 'success')
    return redirect(url_for('admin.adm_cosmetics'))

@admin_bp.route('/admin/cosmetics/<int:cid>/edit', methods=['GET', 'POST'])
@_admin
def adm_cosmetic_edit(cid):
    item = CosmeticItem.query.get_or_404(cid)
    if request.method == 'POST':
        item.name = request.form.get('name', item.name).strip()
        item.description = request.form.get('description', '').strip() or None
        item.category = request.form.get('category', item.category).strip()
        item.rarity = request.form.get('rarity', item.rarity).strip()
        item.effect_type = request.form.get('effect_type', item.effect_type).strip()
        item.effect_mode = request.form.get('effect_mode', item.effect_mode or 'css').strip()
        item.price = request.form.get('price', item.price, type=int)
        item.css_data = request.form.get('css_data', '').strip() or None
        if 'legacy' in request.form:
            item.active = False
            item.legacy = True
        else:
            item.legacy = False
            item.active = 'active' in request.form
        img = request.files.get('image')
        if img and img.filename:
            p = _simg(img, 'misc')
            if p:
                if item.image:
                    old = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
                    if os.path.isfile(old):
                        try:
                            os.remove(old)
                        except OSError:
                            pass
                item.image = p
        _ok()
        flash(f'Cosmetic item "{item.name}" updated.', 'success')
        return redirect(url_for('admin.adm_cosmetics'))
    owner_count = UserCosmetic.query.filter_by(item_id=cid).count()
    return render_template('admin_cosmetic_edit.html', item=item,
                           categories=COSMETIC_CATEGORIES, rarity_tiers=RARITY_TIERS,
                           rarity_colors=RARITY_COLORS, effect_types=EFFECT_TYPES,
                           effect_modes=EFFECT_MODES, rarity_price_ranges=RARITY_PRICE_RANGES,
                           owner_count=owner_count)

@admin_bp.route('/admin/cosmetics/<int:cid>/delete', methods=['POST'])
@_admin
def adm_cosmetic_del(cid):
    item = CosmeticItem.query.get_or_404(cid)
    name = item.name
    owner_count = UserCosmetic.query.filter_by(item_id=cid).count()
    UserCosmetic.query.filter_by(item_id=cid).delete()
    if item.image:
        old = os.path.join(app.config['UPLOAD_FOLDER'], item.image)
        if os.path.isfile(old):
            try:
                os.remove(old)
            except OSError:
                pass
    db.session.delete(item)
    if not _ok():
        db.session.rollback()
        flash('Failed to delete cosmetic item.', 'danger')
        return redirect(url_for('admin.adm_cosmetics'))
    flash(f'Cosmetic item "{name}" deleted. Removed from {owner_count} inventories.', 'success')
    return redirect(url_for('admin.adm_cosmetics'))


# ===========================================================================
# CLAN ACHIEVEMENTS ADMIN
# ===========================================================================
@admin_bp.route('/admin/clan-achievements')
@_admin
def adm_clan_achs_mgmt():
    achs = ClanAchievement.query.order_by(ClanAchievement.awarded_at.desc()).all()
    clans = Clan.query.order_by(Clan.name).all()
    custom_types = CustomClanAchievementType.query.order_by(CustomClanAchievementType.name).all()
    registry = _get_clan_achievement_registry()
    return render_template('admin_clan_achs_mgmt.html', achs=achs, clans=clans, custom_types=custom_types, registry=registry)

@admin_bp.route('/admin/clan-achievements/create', methods=['POST'])
@_admin
def adm_clan_ach_create():
    clan_id = request.form.get('clan_id', type=int)
    achievement_type = request.form.get('achievement_type', '').strip()
    if not clan_id or not achievement_type:
        flash('Clan and achievement type are required.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    registry = _get_clan_achievement_registry()
    if achievement_type not in registry:
        flash('Invalid achievement type.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    existing = ClanAchievement.query.filter_by(clan_id=clan_id, achievement_type=achievement_type).first()
    if existing:
        flash('This clan already has that achievement type.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    ca = ClanAchievement(clan_id=clan_id, achievement_type=achievement_type)
    db.session.add(ca)
    _ok()
    info = registry.get(achievement_type, {})
    leaders = db.session.execute(
        clan_members.select().where(and_(clan_members.c.clan_id == clan_id, clan_members.c.role.in_(['owner', 'officer'])))).fetchall()
    for ld in leaders:
        _alert(ld.user_id, f'🏆 Achievement Awarded: {info.get("name", achievement_type)}', info.get('desc', ''), 'success')
    _ok()
    flash('Clan achievement awarded.', 'success')
    return redirect(url_for('admin.adm_clan_achs_mgmt'))

@admin_bp.route('/admin/clan-achievements/<int:caid>/delete', methods=['POST'])
@_admin
def adm_clan_ach_del(caid):
    ca = ClanAchievement.query.get_or_404(caid)
    db.session.delete(ca)
    _ok()
    flash('Clan achievement deleted.', 'success')
    return redirect(url_for('admin.adm_clan_achs_mgmt'))

@admin_bp.route('/admin/custom-clan-ach-types/create', methods=['POST'])
@_admin
def adm_custom_clan_ach_type_create():
    key = request.form.get('key', '').strip()
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '').strip() or 'fas fa-award'
    description = request.form.get('description', '').strip()
    if not key or not name:
        flash('Key and name are required.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    if key in CLAN_ACHIEVEMENT_TYPES:
        flash('That key conflicts with a predefined achievement type.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    if CustomClanAchievementType.query.filter_by(key=key).first():
        flash('A custom achievement type with that key already exists.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    ct = CustomClanAchievementType(key=key, name=name, icon=icon, description=description)
    img = request.files.get('image')
    if img and img.filename:
        p = _simg(img, 'achievements', 256)
        if p:
            ct.image = p
    db.session.add(ct)
    _ok()
    flash(f'Custom achievement type "{name}" created.', 'success')
    return redirect(url_for('admin.adm_clan_achs_mgmt'))

@admin_bp.route('/admin/custom-clan-ach-types/<int:tid>/edit', methods=['POST'])
@_admin
def adm_custom_clan_ach_type_edit(tid):
    ct = CustomClanAchievementType.query.get_or_404(tid)
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '').strip()
    description = request.form.get('description', '').strip()
    if not name or not icon:
        flash('Name and icon are required.', 'danger')
        return redirect(url_for('admin.adm_clan_achs_mgmt'))
    ct.name = name
    ct.icon = icon
    ct.description = description
    if request.form.get('remove_image') and ct.image:
        old = os.path.join(app.config['UPLOAD_FOLDER'], ct.image)
        if os.path.isfile(old):
            try: os.remove(old)
            except OSError: pass
        ct.image = None
    img = request.files.get('image')
    if img and img.filename:
        p = _simg(img, 'achievements', 256)
        if p:
            if ct.image:
                old = os.path.join(app.config['UPLOAD_FOLDER'], ct.image)
                if os.path.isfile(old):
                    try: os.remove(old)
                    except OSError: pass
            ct.image = p
    _ok()
    flash(f'Custom achievement type "{name}" updated.', 'success')
    return redirect(url_for('admin.adm_clan_achs_mgmt'))

@admin_bp.route('/admin/custom-clan-ach-types/<int:tid>/delete', methods=['POST'])
@_admin
def adm_custom_clan_ach_type_del(tid):
    ct = CustomClanAchievementType.query.get_or_404(tid)
    usage = ClanAchievement.query.filter_by(achievement_type=ct.key).count()
    if ct.image:
        old = os.path.join(app.config['UPLOAD_FOLDER'], ct.image)
        if os.path.isfile(old):
            try: os.remove(old)
            except OSError: pass
    db.session.delete(ct)
    _ok()
    if usage:
        flash(f'Custom type "{ct.name}" deleted. {usage} clan achievement(s) still reference this key.', 'warning')
    else:
        flash(f'Custom type "{ct.name}" deleted.', 'success')
    return redirect(url_for('admin.adm_clan_achs_mgmt'))


# ===========================================================================
# POINT TRANSACTIONS ADMIN
# ===========================================================================
@admin_bp.route('/admin/transactions')
@_admin
def adm_transactions():
    page = request.args.get('page', 1, type=int)
    username = request.args.get('username', '').strip()
    q = PointTransaction.query
    if username:
        user = User.query.filter(User.username.ilike(f'%{_escape_like(username)}%', escape='\\')).first()
        if user:
            q = q.filter(PointTransaction.user_id == user.id)
        else:
            q = q.filter(PointTransaction.id < 0)  # no results
    q = q.order_by(PointTransaction.created_at.desc())
    pagination = q.paginate(page=page, per_page=25, error_out=False)
    users = User.query.filter_by(banned=False).order_by(User.username).all()
    return render_template('admin_transactions.html', txns=pagination.items, pagination=pagination, username=username, users=users)

@admin_bp.route('/admin/transactions/adjust', methods=['POST'])
@_admin
def adm_point_adjust():
    uid = request.form.get('user_id', type=int)
    amount = request.form.get('amount', type=int)
    reason = request.form.get('reason', '').strip()
    if not uid or amount is None or not reason:
        flash('User, amount, and reason are required.', 'danger')
        return redirect(url_for('admin.adm_transactions'))
    u = User.query.get_or_404(uid)
    if amount < 0 and u.points + amount < 0:
        flash(f'Rejected: {u.username} has {u.points} points, cannot deduct {abs(amount)}.', 'danger')
        return redirect(url_for('admin.adm_transactions'))
    _award_points(uid, amount, f'[Admin] {reason}')
    _ok()
    flash(f'Adjusted {u.username} by {amount:+d} points. New balance: {u.points}.', 'success')
    return redirect(url_for('admin.adm_transactions'))


# ===========================================================================
# ENDORSEMENTS ADMIN
# ===========================================================================
@admin_bp.route('/admin/endorsements')
@_admin
def adm_endorsements():
    page = request.args.get('page', 1, type=int)
    cat = request.args.get('category', '').strip()
    q = Endorsement.query
    if cat:
        q = q.filter(Endorsement.category == cat)
    q = q.order_by(Endorsement.created_at.desc())
    pagination = q.paginate(page=page, per_page=25, error_out=False)
    categories = db.session.query(Endorsement.category).distinct().all()
    categories = sorted([c[0] for c in categories if c[0]])
    return render_template('admin_endorsements.html', endorsements=pagination.items, pagination=pagination, category=cat, categories=categories)

@admin_bp.route('/admin/endorsements/<int:eid>/delete', methods=['POST'])
@_admin
def adm_endorsement_del(eid):
    e = Endorsement.query.get_or_404(eid)
    db.session.delete(e)
    _ok()
    flash('Endorsement deleted.', 'success')
    return redirect(url_for('admin.adm_endorsements'))


# ===========================================================================
# PREDICTIONS ADMIN
# ===========================================================================
@admin_bp.route('/admin/predictions')
@_admin
def adm_predictions():
    page = request.args.get('page', 1, type=int)
    correctness = request.args.get('correctness', '').strip()
    q = MatchPrediction.query
    if correctness == 'correct':
        q = q.filter(MatchPrediction.correct == True)
    elif correctness == 'incorrect':
        q = q.filter(MatchPrediction.correct == False)
    elif correctness == 'pending':
        q = q.filter(MatchPrediction.correct.is_(None))
    q = q.order_by(MatchPrediction.created_at.desc())
    pagination = q.paginate(page=page, per_page=25, error_out=False)
    return render_template('admin_predictions.html', predictions=pagination.items, pagination=pagination, correctness=correctness)

@admin_bp.route('/admin/predictions/<int:pid>/delete', methods=['POST'])
@_admin
def adm_prediction_del(pid):
    p = MatchPrediction.query.get_or_404(pid)
    db.session.delete(p)
    _ok()
    flash('Prediction deleted.', 'success')
    return redirect(url_for('admin.adm_predictions'))


# ===========================================================================
# BETS ADMIN
# ===========================================================================
@admin_bp.route('/admin/bets')
@_admin
def adm_bets():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '').strip()
    q = Bet.query
    if status:
        q = q.filter(Bet.status == status)
    q = q.order_by(Bet.created_at.desc())
    pagination = q.paginate(page=page, per_page=25, error_out=False)
    return render_template('admin_bets.html', bets=pagination.items, pagination=pagination, status=status)

@admin_bp.route('/admin/bets/<int:bid>/refund', methods=['POST'])
@_admin
def adm_bet_refund(bid):
    b = Bet.query.get_or_404(bid)
    if b.status == 'refunded':
        flash('Bet already refunded.', 'info')
        return redirect(url_for('admin.adm_bets'))
    b.status = 'refunded'
    _award_points(b.user_id, b.amount, f'[Admin] Bet #{b.id} refund (Match #{b.match_id})')
    _ok()
    flash(f'Bet #{b.id} refunded. {b.amount} points returned to {b.user.username}.', 'success')
    return redirect(url_for('admin.adm_bets'))


# ===========================================================================
# CLAN WARS ADMIN
# ===========================================================================
@admin_bp.route('/admin/clan-wars')
@_admin
def adm_clan_wars():
    wars = ClanWar.query.order_by(ClanWar.created_at.desc()).all()
    return render_template('admin_clan_wars.html', wars=wars)

@admin_bp.route('/admin/clan-wars/<int:wid>/edit', methods=['GET', 'POST'])
@_admin
def adm_clan_war_edit(wid):
    war = ClanWar.query.get_or_404(wid)
    if request.method == 'POST':
        war.status = request.form.get('status', war.status)
        war.clan1_wins = request.form.get('clan1_wins', war.clan1_wins, type=int)
        war.clan2_wins = request.form.get('clan2_wins', war.clan2_wins, type=int)
        winner_id = request.form.get('winner_clan_id', type=int)
        war.winner_clan_id = winner_id if winner_id else None
        if war.status == 'completed' and not war.completed_at:
            war.completed_at = datetime.now(timezone.utc)
        _ok()
        flash(f'Clan war #{war.id} updated.', 'success')
        return redirect(url_for('admin.adm_clan_wars'))
    matches = war.war_matches.all()
    return render_template('admin_clan_war_edit.html', war=war, matches=matches)

@admin_bp.route('/admin/clan-wars/<int:wid>/delete', methods=['POST'])
@_admin
def adm_clan_war_del(wid):
    war = ClanWar.query.get_or_404(wid)
    ClanWarMatch.query.filter_by(war_id=wid).delete()
    _ok()
    db.session.delete(war)
    _ok()
    flash(f'Clan war #{wid} and all associated matches deleted.', 'success')
    return redirect(url_for('admin.adm_clan_wars'))

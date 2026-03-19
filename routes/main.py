"""Main routes: home, theme, login, register, logout, profile, dashboard, edit profile, avatar, players, compare, activity, hall of fame, favicon, alerts, news, leaderboard."""
import os, math, secrets
from datetime import datetime, timedelta, timezone
from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   abort, jsonify, session, g, Response)
from flask_login import login_required, current_user, login_user, logout_user
from sqlalchemy import or_, and_, case, func

from extensions import db, app, log
from models import (User, EloSnap, Match, Tournament, News, Alert, GlobalAlert,
                    Activity, Achievement, Clan, Challenge, Season, SeasonArchive,
                    Endorsement, UserCosmetic, MVPVote, MatchReaction, MatchSet,
                    CosmeticItem, clan_members, tourney_players, user_achs)
from forms import (LoginForm, RegForm, ProfileForm, ChallengeForm, ResultForm,
                   NewsForm, MatchForm)
from helpers import (
    _ok, _alert, _activity, _escape_like, _alw, _simg, _head_to_head,
    _calc_titles_cached, _calc_form, _get_rivals, _proc_r, _proc_u,
    _resolve_bets, _refund_match_bets, _award_points,
    rate_limit, COUNTRIES, COUNTRY_FLAGS, ALL_RANKS, TITLE_COLORS,
    ENDORSEMENT_CATEGORIES, _check_tourney_completion,
    COSMETIC_CATEGORIES, RARITY_COLORS,
    deserialize_showcase, serialize_showcase, resolve_showcase_metrics, SHOWCASE_METRICS
)

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def home():
    s={'users':User.query.count(),'tourneys':Tournament.query.filter(Tournament.status.in_(['upcoming','active'])).count(),'matches':Match.query.count(),'clans':Clan.query.filter_by(active=True).count()}
    news=News.query.filter_by(published=True,auto=False).order_by(News.pinned.desc(),News.created_at.desc()).limit(6).all()
    top=User.query.filter_by(banned=False).order_by(User.elo.desc()).limit(10).all()
    current_tournaments=Tournament.query.filter(Tournament.status.in_(['upcoming','active'])).order_by(Tournament.start_dt.desc()).all()
    home_alert=None; home_global_alert=None
    try:
        if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
            home_alert=current_user.alerts.order_by(Alert.created_at.desc()).first()
        home_global_alert=GlobalAlert.query.filter_by(active=True).order_by(GlobalAlert.created_at.desc()).first()
    except Exception: pass
    recent_activity=Activity.query.order_by(Activity.created_at.desc()).limit(8).all()
    return render_template('home.html',s=s,news=news,top=top,current_tournaments=current_tournaments,home_alert=home_alert,home_global_alert=home_global_alert,recent_activity=recent_activity)

@main_bp.route('/theme')
def flip_theme():
    n='light' if g.theme=='dark' else 'dark'
    if current_user.is_authenticated: current_user.theme=n; _ok()
    r=redirect(request.referrer or url_for('main.home')); r.set_cookie('theme',n,max_age=365*86400); return r

@main_bp.route('/login', methods=['GET','POST'])
@rate_limit(10, 60, lambda: f"login:{request.remote_addr}")
def login():
    if current_user.is_authenticated: return redirect(url_for('main.home'))
    form=LoginForm()
    if form.validate_on_submit():
        u=User.query.filter_by(username=form.username.data).first()
        if u and u.check_pw(form.password.data):
            if u.banned: flash(f'Banned: {u.ban_reason or ""}','danger'); return redirect(url_for('main.login'))
            u.rotate_session(); _ok()
            session.clear()
            ok=login_user(u,remember=form.remember.data)
            if ok:
                session.permanent = True
                today_utc = datetime.now(timezone.utc).date()
                if u.last_login_bonus != today_utc:
                    _award_points(u.id, 3, 'Daily login bonus')
                    u.last_login_bonus = today_utc; _ok()
                flash('Welcome!','success')
                return redirect(request.args.get('next') or url_for('main.home'))
            flash('Login failed.','danger')
        else: flash('Bad credentials.','danger')
    return render_template('login.html',form=form)

@main_bp.route('/register', methods=['GET','POST'])
@rate_limit(5, 60, lambda: f"reg:{request.remote_addr}")
def register():
    if current_user.is_authenticated: return redirect(url_for('main.home'))
    form=RegForm()
    if form.validate_on_submit():
        u=User(username=form.username.data,email=form.email.data,session_token=secrets.token_hex(32))
        u.set_pw(form.password.data)
        if User.query.count()==0: u.admin=True
        db.session.add(u)
        if _ok():
            db.session.add(EloSnap(user_id=u.id,elo_val=1200)); _ok()
            _activity('join', u.id, f'joined the platform!', 'user-plus', 'info'); _ok()
            flash('Created! Sign in.','success'); return redirect(url_for('main.login'))
        flash('Failed.','danger')
    return render_template('register.html',form=form)


@main_bp.route('/logout')
@login_required
def logout():
    current_user.rotate_session(); _ok(); session.clear(); logout_user()
    flash('Bye!','info'); return redirect(url_for('main.home'))

@main_bp.route('/user/<u>')
def prof(u):
    user=User.query.filter_by(username=u).first_or_404()
    per=request.args.get('period','all')
    q=EloSnap.query.filter_by(user_id=user.id); now=datetime.now(timezone.utc)
    if per=='week': q=q.filter(EloSnap.ts>=now-timedelta(days=7))
    elif per=='month': q=q.filter(EloSnap.ts>=now-timedelta(days=30))
    elif per=='4months': q=q.filter(EloSnap.ts>=now-timedelta(days=120))
    elif per=='year': q=q.filter(EloSnap.ts>=now-timedelta(days=365))
    h=q.order_by(EloSnap.ts.asc()).all()
    elx=[x.ts.strftime('%b %d') for x in h] or ['Start']; ely=[x.elo_val for x in h] or [user.elo]
    matches=Match.query.filter(or_(Match.p1_id==user.id,Match.p2_id==user.id),Match.state=='verified').order_by(Match.played_at.desc()).limit(20).all()
    h2h=None
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated and current_user.id!=user.id:
        h2h=_head_to_head(current_user.id, user.id)
    past_seasons=user.season_history.order_by(SeasonArchive.season_id.desc()).all() if hasattr(user,'season_history') else []
    u_titles=_calc_titles_cached(user)
    equipped_cosmetics={}
    for uc in UserCosmetic.query.filter_by(user_id=user.id,equipped=True).all():
        equipped_cosmetics[uc.item.category]=uc.item
    form=_calc_form(user); rivals=_get_rivals(user)
    endorsement_counts=db.session.query(Endorsement.category,func.count(Endorsement.id)).filter(Endorsement.to_id==user.id).group_by(Endorsement.category).order_by(func.count(Endorsement.id).desc()).all()
    # --- Set-level statistics ---
    set_stats = None
    sets_as_p1 = db.session.query(
        func.count(MatchSet.id),
        func.sum(MatchSet.p1_points),
        func.sum(MatchSet.p2_points),
        func.sum(case((MatchSet.winner_id == user.id, 1), else_=0)),
        func.sum(case((and_(MatchSet.winner_id != None, MatchSet.winner_id != user.id), 1), else_=0))
    ).join(Match, MatchSet.match_id == Match.id).filter(
        Match.p1_id == user.id, Match.state == 'verified'
    ).first()
    sets_as_p2 = db.session.query(
        func.count(MatchSet.id),
        func.sum(MatchSet.p2_points),
        func.sum(MatchSet.p1_points),
        func.sum(case((MatchSet.winner_id == user.id, 1), else_=0)),
        func.sum(case((and_(MatchSet.winner_id != None, MatchSet.winner_id != user.id), 1), else_=0))
    ).join(Match, MatchSet.match_id == Match.id).filter(
        Match.p2_id == user.id, Match.state == 'verified'
    ).first()
    total_sets = (sets_as_p1[0] or 0) + (sets_as_p2[0] or 0)
    if total_sets > 0:
        pts_scored = (sets_as_p1[1] or 0) + (sets_as_p2[1] or 0)
        pts_conceded = (sets_as_p1[2] or 0) + (sets_as_p2[2] or 0)
        sets_won = (sets_as_p1[3] or 0) + (sets_as_p2[3] or 0)
        sets_lost = (sets_as_p1[4] or 0) + (sets_as_p2[4] or 0)
        set_stats = {
            'sets_won': sets_won, 'sets_lost': sets_lost,
            'pts_scored': pts_scored, 'pts_conceded': pts_conceded,
            'avg_pts': round(pts_scored / total_sets, 1), 'total_sets': total_sets
        }
    showcase_keys = deserialize_showcase(user.showcase_config if hasattr(user, 'showcase_config') else None)
    showcase_data = resolve_showcase_metrics(user, showcase_keys, set_stats)
    return render_template('profile.html',u=user,per=per,elx=elx,ely=ely,matches=matches,achs=user.trophies.all(),h2h=h2h,past_seasons=past_seasons,u_titles=u_titles,title_colors=TITLE_COLORS,country_flags=COUNTRY_FLAGS,equipped_cosmetics=equipped_cosmetics,form=form,rivals=rivals,endorsement_counts=endorsement_counts,set_stats=set_stats,showcase_data=showcase_data)

@main_bp.route('/dashboard')
@login_required
def dash():
    from models import Bet, PointTransaction
    pch=Challenge.query.filter(or_(Challenge.from_id==current_user.id,Challenge.to_id==current_user.id),Challenge.state=='pending').all()
    pres=Match.query.filter(or_(Match.p1_id==current_user.id,Match.p2_id==current_user.id),Match.state=='pending').all()
    recent_txns=PointTransaction.query.filter_by(user_id=current_user.id).order_by(PointTransaction.created_at.desc()).limit(5).all()
    active_bets=Bet.query.filter_by(user_id=current_user.id,status='active').order_by(Bet.created_at.desc()).all()
    now_utc=datetime.now(timezone.utc)
    upcoming_matches=Match.query.filter(
        or_(Match.p1_id==current_user.id,Match.p2_id==current_user.id),
        Match.scheduled_at.isnot(None),Match.scheduled_at>now_utc
    ).order_by(Match.scheduled_at).limit(5).all()
    weekly_key=now_utc.strftime('%G-W%V'); monthly_key=now_utc.strftime('%Y-%m')
    weekly_voted=MVPVote.query.filter_by(voter_id=current_user.id,period_type='weekly',period_key=weekly_key).first()
    monthly_voted=MVPVote.query.filter_by(voter_id=current_user.id,period_type='monthly',period_key=monthly_key).first()
    equipped_cosmetics=UserCosmetic.query.filter_by(user_id=current_user.id,equipped=True).all()
    return render_template('dashboard.html',pch=pch,pres=pres,recent_txns=recent_txns,active_bets=active_bets,
             upcoming_matches=upcoming_matches,weekly_key=weekly_key,monthly_key=monthly_key,
             weekly_voted=weekly_voted,monthly_voted=monthly_voted,equipped_cosmetics=equipped_cosmetics)


@main_bp.route('/profile/edit', methods=['GET','POST'])
@login_required
def edit_prof():
    form=ProfileForm()
    user_achs_list=current_user.trophies.all()
    if form.validate_on_submit():
        user = current_user._get_current_object()
        username = user.username
        user.display_name=form.display_name.data or None; user.bio=form.bio.data or None
        user.profile_color=request.form.get('profile_color','#6c5ce7')
        fach=request.form.get('featured_ach_id','')
        user.featured_ach_id=int(fach) if fach and fach.isdigit() else None
        country_code=request.form.get('country','').strip()
        user.country=country_code if country_code else None
        user.country_name=dict(COUNTRIES).get(country_code,'') if country_code else None
        showcase_selected = request.form.getlist('showcase_metrics')
        showcase_selected = [k for k in showcase_selected if k in SHOWCASE_METRICS][:6]
        user.showcase_config = serialize_showcase(showcase_selected) if showcase_selected else None
        new_password=request.form.get('new_password','').strip()
        confirm_password=request.form.get('confirm_password','').strip()
        if new_password:
            if new_password!=confirm_password: flash('Passwords do not match.','danger'); return redirect(url_for('main.edit_prof'))
            if len(new_password)<8: flash('Password must be at least 8 characters.','danger'); return redirect(url_for('main.edit_prof'))
            user.set_pw(new_password); user.rotate_session()
            flash('Password updated!','success')
        _ok()
        if new_password: login_user(user, remember=True)
        flash('Saved!','success'); return redirect(url_for('main.prof',u=username))
    elif request.method=='GET': form.display_name.data=current_user.display_name; form.bio.data=current_user.bio
    # Build cosmetics data for equip section
    owned_cosmetics = current_user.cosmetics.all()
    equipped_by_cat = {}
    owned_by_cat = {}
    for uc in owned_cosmetics:
        cat = uc.item.category
        owned_by_cat.setdefault(cat, []).append(uc)
        if uc.equipped:
            equipped_by_cat[cat] = uc
    cat_labels = {
        'avatar_frame': 'Avatar Frame', 'profile_border': 'Profile Border', 'profile_banner': 'Profile Banner',
        'badge': 'Badge', 'name_color': 'Name Color', 'name_effect': 'Name Effect',
        'chat_flair': 'Chat Flair', 'profile_background': 'Background', 'profile_effect': 'Profile Effect', 'title': 'Title'
    }
    current_showcase = deserialize_showcase(current_user.showcase_config if hasattr(current_user, 'showcase_config') else None)
    return render_template('edit_profile.html', form=form, user_achs=user_achs_list, countries=COUNTRIES,
                           cosmetic_categories=COSMETIC_CATEGORIES, owned_by_cat=owned_by_cat,
                           equipped_by_cat=equipped_by_cat, cat_labels=cat_labels, rarity_colors=RARITY_COLORS,
                           showcase_metrics=SHOWCASE_METRICS, current_showcase=current_showcase)

@main_bp.route('/profile/avatar', methods=['POST'])
@login_required
def up_avatar():
    from flask_wtf.csrf import validate_csrf
    try: validate_csrf(request.form.get('csrf_token', ''))
    except Exception: return jsonify(ok=False, err='CSRF token missing or invalid'), 400
    f=request.files.get('pic')
    if not f or not f.filename: return jsonify(ok=False,err='No file'),400
    if not _alw(f.filename): return jsonify(ok=False,err='Bad type'),400
    crop={k:request.form.get(f'c{k}','0') for k in ['x','y','w','h']}
    p=_simg(f,'profiles',app.config['PIC_MAX'],{'x':crop['x'],'y':crop['y'],'width':crop['w'],'height':crop['h']})
    if not p: return jsonify(ok=False,err='Fail'),500
    if current_user.avatar:
        old=os.path.join(app.config['UPLOAD_FOLDER'],current_user.avatar)
        if os.path.isfile(old):
            try: os.remove(old)
            except OSError: pass
    current_user.avatar=p; _ok(); return jsonify(ok=True)

@main_bp.route('/players')
def find_players():
    q=request.args.get('q','').strip(); frank=request.args.get('rank','')
    fclan=request.args.get('clan','',type=int) if request.args.get('clan') else 0
    elo_min=request.args.get('elo_min','',type=int) if request.args.get('elo_min') else None
    elo_max=request.args.get('elo_max','',type=int) if request.args.get('elo_max') else None
    min_matches=request.args.get('min_matches','',type=int) if request.args.get('min_matches') else None
    sort=request.args.get('sort','elo'); pg=request.args.get('page',1,type=int); pp=25
    query=User.query.filter_by(banned=False)
    if q: query=query.filter(or_(User.username.ilike(f'%{_escape_like(q)}%',escape='\\'),User.display_name.ilike(f'%{_escape_like(q)}%',escape='\\')))
    if elo_min is not None: query=query.filter(User.elo>=elo_min)
    if elo_max is not None: query=query.filter(User.elo<=elo_max)
    if fclan: query=query.filter(User.clans.any(Clan.id==fclan))
    all_users=query.all()
    if frank: all_users=[u for u in all_users if u.rank_title==frank]
    if min_matches is not None: all_users=[u for u in all_users if u.total_matches>=min_matches]
    if sort=='elo': all_users.sort(key=lambda u: u.elo, reverse=True)
    elif sort=='elo_asc': all_users.sort(key=lambda u: u.elo)
    elif sort=='name': all_users.sort(key=lambda u: u.name().lower())
    elif sort=='matches': all_users.sort(key=lambda u: u.total_matches, reverse=True)
    elif sort=='winrate': all_users.sort(key=lambda u: u.ranked_wr, reverse=True)
    elif sort=='unranked': all_users.sort(key=lambda u: u.total_unranked, reverse=True)
    elif sort=='uwinrate': all_users.sort(key=lambda u: u.unranked_wr, reverse=True)
    elif sort=='newest': all_users.sort(key=lambda u: u.created_at, reverse=True)
    total=len(all_users); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    us=all_users[(pg-1)*pp:pg*pp]
    user_forms={u.id:_calc_form(u) for u in us}
    clans=Clan.query.filter_by(active=True).order_by(Clan.name).all()
    return render_template('players.html',us=us,q=q,frank=frank,fclan=fclan,elo_min=elo_min,elo_max=elo_max,
             min_matches=min_matches,sort=sort,total=total,pg=pg,tp=tp,off=(pg-1)*pp,ranks=ALL_RANKS,clans=clans,country_flags=COUNTRY_FLAGS,user_forms=user_forms)


@main_bp.route('/compare')
def compare_players():
    p1_id=request.args.get('p1',type=int); p2_id=request.args.get('p2',type=int)
    players=User.query.filter_by(banned=False).order_by(User.username).all()
    p1=db.session.get(User,p1_id) if p1_id else None
    p2=db.session.get(User,p2_id) if p2_id else None
    h2h=None
    if p1 and p2 and p1.id!=p2.id: h2h=_head_to_head(p1.id,p2.id)
    return render_template('compare.html',players=players,p1=p1,p2=p2,h2h=h2h)

@main_bp.route('/activity')
def activity_feed():
    pg=request.args.get('page',1,type=int); pp=25
    q=Activity.query.order_by(Activity.created_at.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    acts=q.offset((pg-1)*pp).limit(pp).all()
    return render_template('activity.html',acts=acts,pg=pg,tp=tp)

@main_bp.route('/hall-of-fame')
def hall_of_fame():
    from helpers import _calc_rr_standings
    completed = Tournament.query.filter_by(status='completed').order_by(Tournament.created_at.desc()).all()
    champions = []
    for t in completed:
        tr = t.total_rounds
        if tr > 0:
            final = t.matches.filter_by(round_num=tr).first()
            if final and final.winner_id:
                winner = db.session.get(User, final.winner_id)
                if winner: champions.append({'tourney': t, 'winner': winner, 'match': final})
        if t.fmt == 'round_robin':
            standings = _calc_rr_standings(t)
            if standings and not any(c['tourney'].id == t.id for c in champions):
                champions.append({'tourney': t, 'winner': standings[0].user, 'match': None})
    win_counts = {}
    for c in champions:
        uid = c['winner'].id
        if uid not in win_counts: win_counts[uid] = {'user': c['winner'], 'count': 0, 'tourneys': []}
        win_counts[uid]['count'] += 1; win_counts[uid]['tourneys'].append(c['tourney'])
    top_winners = sorted(win_counts.values(), key=lambda x: x['count'], reverse=True)
    return render_template('hall_of_fame.html', champions=champions, top_winners=top_winners)

@main_bp.route('/favicon.png')
def favicon(): return app.send_static_file('favicon.png')

@main_bp.route('/leaderboard')
def board():
    tab=request.args.get('tab','players'); pg=request.args.get('page',1,type=int); pp=25
    if tab=='clans': q=Clan.query.filter_by(active=True).order_by(Clan.score.desc())
    else: q=User.query.filter_by(banned=False).order_by(User.elo.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    return render_template('board.html',items=q.offset((pg-1)*pp).limit(pp).all(),page=pg,total_pages=tp,off=(pg-1)*pp,tab=tab,country_flags=COUNTRY_FLAGS)

@main_bp.route('/news')
def news_list(): return render_template('news_list.html',arts=News.query.filter_by(published=True,auto=False).order_by(News.pinned.desc(),News.created_at.desc()).all())

@main_bp.route('/news/<slug>')
def news_view(slug):
    a=News.query.filter_by(slug=slug,published=True).first_or_404(); a.views+=1; _ok()
    return render_template('news_view.html',a=a)

@main_bp.route('/alerts')
@login_required
def my_alerts():
    atab=request.args.get('tab','unread'); pg=request.args.get('page',1,type=int); pp=25
    if atab=='unread': q=current_user.alerts.filter_by(read=False).order_by(Alert.created_at.desc())
    elif atab=='read': q=current_user.alerts.filter_by(read=True).order_by(Alert.created_at.desc())
    else: q=current_user.alerts.order_by(Alert.created_at.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(max(1,pg),tp)
    als=q.offset((pg-1)*pp).limit(pp).all()
    uc=current_user.alerts.filter_by(read=False).count()
    return render_template('alerts.html',als=als,uc=uc,atab=atab,pg=pg,tp=tp)

@main_bp.route('/alerts/read', methods=['POST'])
@login_required
def read_all():
    current_user.alerts.filter_by(read=False).update({'read':True}); _ok(); return redirect(url_for('main.my_alerts'))

@main_bp.route('/alerts/<int:aid>/dismiss', methods=['POST'])
@login_required
def dismiss_alert(aid):
    a=Alert.query.get(aid)
    if a and a.user_id==current_user.id: a.read=True; _ok()
    return redirect(request.referrer or url_for('main.home'))

@main_bp.route('/challenges')
@login_required
def my_ch(): return render_template('challenges.html',chs=Challenge.query.filter(or_(Challenge.from_id==current_user.id,Challenge.to_id==current_user.id)).order_by(Challenge.created_at.desc()).all())


@main_bp.route('/challenges/new', methods=['GET','POST'])
@login_required
@rate_limit(20, 60, lambda: f"chal:{current_user.id}")
def ch_new():
    form=ChallengeForm()
    form.to_id.choices=[(u.id,u.username) for u in User.query.filter(User.id!=current_user.id,User.banned==False).order_by(User.username).all()]
    if form.validate_on_submit():
        when=None
        try: when=datetime.strptime(request.form.get('when',''),'%Y-%m-%dT%H:%M')
        except ValueError: flash('Invalid date/time.','danger'); return render_template('ch_new.html',form=form)
        if not when: flash('Please select a date/time.','danger'); return render_template('ch_new.html',form=form)
        msg_text = (form.msg.data or '').strip()[:500]
        stake_val = max(0, min(500, form.stake.data or 0))
        c=Challenge(from_id=current_user.id,to_id=form.to_id.data,when=when,msg=msg_text if msg_text else None,ranked=form.ranked.data,stake=stake_val,series_format=form.series_format.data or 'bo1')
        db.session.add(c)
        if _ok():
            ranked_text = ' (Ranked)' if form.ranked.data else ''
            stake_text = f' for {stake_val} PongCoins' if stake_val > 0 else ''
            _alert(form.to_id.data,'Challenge!',f'{current_user.name()} challenged you{ranked_text}{stake_text}{"  — " + msg_text if msg_text else ""}','warning',url_for('main.my_ch'))
            _activity('challenge', current_user.id, f'Challenged {c.receiver.name()}{ranked_text}', 'gamepad', 'info', url_for('main.my_ch')); _ok()
            flash('Sent!','success')
        else: flash('Failed to send challenge.','danger')
        return redirect(url_for('main.my_ch'))
    return render_template('ch_new.html',form=form)

@main_bp.route('/challenges/new/<int:uid>', methods=['GET','POST'])
@login_required
def ch_new_to(uid):
    target=User.query.get_or_404(uid)
    if target.id==current_user.id: flash('Cannot challenge yourself.','warning'); return redirect(url_for('main.prof',u=target.username))
    form=ChallengeForm(); form.to_id.choices=[(target.id,target.username)]; form.to_id.data=target.id
    if form.validate_on_submit():
        when=None
        try: when=datetime.strptime(request.form.get('when',''),'%Y-%m-%dT%H:%M')
        except ValueError: flash('Invalid date/time.','danger'); return render_template('ch_new.html',form=form)
        if not when: flash('Please select a date/time.','danger'); return render_template('ch_new.html',form=form)
        msg_text = (form.msg.data or '').strip()[:500]
        stake_val = max(0, min(500, form.stake.data or 0))
        c=Challenge(from_id=current_user.id,to_id=target.id,when=when,msg=msg_text if msg_text else None,ranked=form.ranked.data,stake=stake_val,series_format=form.series_format.data or 'bo1')
        db.session.add(c)
        if _ok():
            ranked_text = ' (Ranked)' if form.ranked.data else ''
            stake_text = f' for {stake_val} PongCoins' if stake_val > 0 else ''
            _alert(target.id,'Challenge!',f'{current_user.name()} challenged you{ranked_text}{stake_text}{"  — " + msg_text if msg_text else ""}','warning',url_for('main.my_ch'))
            _activity('challenge', current_user.id, f'Challenged {target.name()}{ranked_text}', 'gamepad', 'info', url_for('main.my_ch')); _ok()
            flash('Sent!','success')
        else: flash('Failed to send challenge.','danger')
        return redirect(url_for('main.my_ch'))
    return render_template('ch_new.html',form=form)

@main_bp.route('/challenges/<int:cid>/respond', methods=['POST'])
@login_required
def ch_respond(cid):
    c=Challenge.query.get_or_404(cid)
    if c.to_id!=current_user.id: abort(403)
    act=request.form.get('act')
    if act=='accept':
        sched_raw = request.form.get('scheduled_at', '').strip()
        if sched_raw:
            try: c.when = datetime.fromisoformat(sched_raw)
            except ValueError: pass
        stake = c.stake or 0
        if stake > 0:
            ok1 = _award_points(c.from_id, -stake, f'Challenge stake: vs {current_user.name()} (Challenge #{c.id})')
            ok2 = _award_points(c.to_id, -stake, f'Challenge stake: vs {c.sender.name()} (Challenge #{c.id})')
            if not ok1 or not ok2:
                if ok1: _award_points(c.from_id, stake, f'Challenge stake refund: insufficient funds (Challenge #{c.id})')
                if ok2: _award_points(c.to_id, stake, f'Challenge stake refund: insufficient funds (Challenge #{c.id})')
                c.stake = 0; flash('Stake removed — one or both players have insufficient PongCoins.','warning')
        c.state='accepted'; _ok()
        stake_text = f' (Stake: {c.stake} PongCoins each)' if c.stake > 0 else ''
        _alert(c.from_id,'Accepted!',f'{current_user.name()} accepted{stake_text}','success',url_for('main.my_ch'))
        _activity('challenge', current_user.id, f'Accepted challenge from {c.sender.name()}', 'gamepad', 'info', url_for('main.my_ch')); _ok()
        n=News(title=f"🎮 {c.sender.name()} vs {c.receiver.name()}",summary=f"Scheduled {c.when.strftime('%b %d %H:%M')}",content=f"<p>Match on {c.when.strftime('%B %d, %Y %H:%M')}</p>",category='match',auto=True,author_id=current_user.id)
        n.make_slug(); db.session.add(n); _ok(); c.news_id=n.id; _ok(); flash('Accepted!','success')
    elif act=='decline':
        c.state='declined'; _ok(); _alert(c.from_id,'Declined',f'{current_user.name()} declined','danger'); flash('Declined.','info')
    return redirect(url_for('main.my_ch'))


@main_bp.route('/challenges/<int:cid>/result', methods=['GET','POST'])
@login_required
def ch_result(cid):
    from models import Audit
    c=Challenge.query.get_or_404(cid)
    if current_user.id not in [c.from_id,c.to_id]: abort(403)
    opp=c.receiver if c.from_id==current_user.id else c.sender
    form=ResultForm()
    if request.method=='POST':
        submit_type=request.form.get('submit_type','normal')
        if submit_type=='noshow':
            reason=request.form.get('noshow_reason','').strip()
            if not reason: flash('Please provide a reason.','danger'); return redirect(url_for('main.ch_result',cid=cid))
            m=Match(p1_id=current_user.id,p2_id=opp.id,p1_score=1,p2_score=0,
                    winner_id=current_user.id,draw=False,ranked=c.ranked,state='pending',
                    submit_by=current_user.id,challenge_id=c.id,
                    notes=f'⚠️ NO-SHOW: {reason}',stake=c.stake or 0,series_format=c.series_format or 'bo1',scheduled_at=c.when)
            db.session.add(m); _ok(); c.match_id=m.id; _ok()
            db.session.add(Audit(match_id=m.id, by_id=current_user.id, reason=f'No-show reported: {reason}', state='pending')); _ok()
            _activity('noshow', current_user.id, f'Reported {opp.name()} as no-show', 'user-clock', 'warn', url_for('main.my_ch')); _ok()
            for a in User.query.filter_by(admin=True).all():
                _alert(a.id, '⚠️ No-Show Report', f'{current_user.name()} reported {opp.name()} as no-show in a challenge', 'warning', url_for('admin.adm_audit'))
            _alert(opp.id, '⚠️ No-Show Report', f'{current_user.name()} reported you as no-show. An admin will review.', 'danger', url_for('main.my_ch')); _ok()
            flash('No-show reported. An admin will review.','warning'); return redirect(url_for('main.my_ch'))
        elif form.validate():
            played_at_raw=request.form.get('played_at','').strip()
            if played_at_raw:
                try:
                    played_at_val=datetime.fromisoformat(played_at_raw)
                    if played_at_val>datetime.now(timezone.utc).replace(tzinfo=None):
                        flash('Match date cannot be in the future.','danger'); return redirect(url_for('main.ch_result',cid=cid))
                except (ValueError, TypeError):
                    played_at_val=datetime.now(timezone.utc)
            else:
                played_at_val=datetime.now(timezone.utc)
            ms,os_=form.my_score.data,form.opp_score.data; dr=form.draw.data
            wid=None if dr else (current_user.id if ms>os_ else opp.id)
            wc = form.notes.data if wid == current_user.id else None
            m=Match(p1_id=current_user.id,p2_id=opp.id,p1_score=ms,p2_score=os_,winner_id=wid,draw=dr,ranked=c.ranked,state='pending',submit_by=current_user.id,challenge_id=c.id,notes=form.notes.data,winner_comment=wc,stake=c.stake or 0,series_format=c.series_format or 'bo1',scheduled_at=c.when,played_at=played_at_val)
            db.session.add(m); _ok(); c.match_id=m.id; _ok()
            # --- Set score parsing (optional) ---
            set_p1 = request.form.getlist('set_p1_points[]')
            set_p2 = request.form.getlist('set_p2_points[]')
            if set_p1 and set_p2:
                n_sets = len(set_p1)
                if n_sets != len(set_p2) or n_sets < 1 or n_sets > 7:
                    flash('Set scores must have between 1 and 7 sets.', 'danger')
                    return redirect(url_for('main.ch_result', cid=cid))
                total_p1 = 0; total_p2 = 0
                for i in range(n_sets):
                    try:
                        sp1 = int(set_p1[i]); sp2 = int(set_p2[i])
                    except (ValueError, TypeError):
                        sp1 = 0; sp2 = 0
                    wid = m.p1_id if sp1 > sp2 else (m.p2_id if sp2 > sp1 else None)
                    db.session.add(MatchSet(match_id=m.id, set_number=i+1, p1_points=sp1, p2_points=sp2, winner_id=wid))
                    total_p1 += sp1; total_p2 += sp2
                m.p1_total_points = total_p1; m.p2_total_points = total_p2
                _ok()
            _alert(opp.id,'Result submitted',f'{current_user.name()} submitted {ms}–{os_}','warning',url_for('main.dash')); _ok()
            flash('Submitted!','success'); return redirect(url_for('main.my_ch'))
    return render_template('ch_result.html',form=form,c=c,opp=opp,now_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'))

@main_bp.route('/news/new', methods=['GET','POST'])
def news_new():
    from helpers import _admin
    if not current_user.is_authenticated or not current_user.admin: abort(403)
    form=NewsForm()
    if form.validate_on_submit():
        a=News(title=form.title.data,summary=form.summary.data,content=form.content.data,category=form.category.data,pinned=form.pinned.data,author_id=current_user.id)
        a.make_slug()
        if form.image.data and form.image.data.filename:
            p=_simg(form.image.data,'news')
            if p: a.image=p
        db.session.add(a)
        if _ok(): flash('Published!','success'); return redirect(url_for('main.news_view',slug=a.slug))
        flash('Failed.','danger')
    return render_template('news_new.html',form=form)

@main_bp.route('/news/<int:nid>/edit', methods=['GET','POST'])
def news_edit(nid):
    if not current_user.is_authenticated or not current_user.admin: abort(403)
    a=News.query.get_or_404(nid)
    if request.method=='POST':
        a.title=request.form.get('title',a.title).strip()
        a.summary=request.form.get('summary','').strip() or None
        a.content=request.form.get('content',a.content).strip()
        a.category=request.form.get('category',a.category)
        a.pinned='pinned' in request.form
        img=request.files.get('image')
        if img and img.filename:
            p=_simg(img,'news')
            if p:
                if a.image:
                    old=os.path.join(app.config['UPLOAD_FOLDER'],a.image)
                    if os.path.isfile(old):
                        try: os.remove(old)
                        except OSError: pass
                a.image=p
        _ok(); flash('News updated!','success'); return redirect(url_for('main.news_view',slug=a.slug))
    return render_template('news_edit.html',a=a)

@main_bp.route('/news/<int:nid>/delete', methods=['POST'])
def news_del(nid):
    if not current_user.is_authenticated or not current_user.admin: abort(403)
    n=News.query.get_or_404(nid)
    if n.image:
        old=os.path.join(app.config['UPLOAD_FOLDER'],n.image)
        if os.path.isfile(old):
            try: os.remove(old)
            except OSError: pass
    db.session.delete(n); _ok(); flash('Deleted.','success'); return redirect(url_for('main.news_list'))

@main_bp.route('/export/leaderboard')
def export_leaderboard():
    import csv, io
    si=io.StringIO(); w=csv.writer(si)
    w.writerow(['Rank','Username','Display Name','ELO','Rank Title','R Wins','R Losses','R Draws','Win Rate','U Wins','U Losses','U Draws','Best Streak','Total Matches'])
    players=User.query.filter_by(banned=False).order_by(User.elo.desc()).all()
    for i,p in enumerate(players,1):
        w.writerow([i,p.username,p.name(),p.elo,p.rank_title,p.r_wins,p.r_losses,p.r_draws,p.ranked_wr,p.u_wins,p.u_losses,p.u_draws,p.best_streak,p.total_matches])
    return Response(si.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment;filename=leaderboard.csv'})

@main_bp.route('/export/my-stats')
@login_required
def export_my_stats():
    import csv, io
    si=io.StringIO(); w=csv.writer(si)
    w.writerow(['Date','Opponent','My Score','Opp Score','Result','Type','ELO Change'])
    matches=Match.query.filter(or_(Match.p1_id==current_user.id,Match.p2_id==current_user.id),Match.state=='verified').order_by(Match.played_at.desc()).all()
    for m in matches:
        ip1=(m.p1_id==current_user.id); opp=m.p2 if ip1 else m.p1
        ms=m.p1_score if ip1 else m.p2_score; os_=m.p2_score if ip1 else m.p1_score
        ed=m.elo_d1 if ip1 else m.elo_d2
        result='Draw' if m.draw else ('Win' if m.winner_id==current_user.id else 'Loss')
        w.writerow([m.played_at.strftime('%Y-%m-%d %H:%M'),opp.name(),ms,os_,result,'Ranked' if m.ranked else 'Unranked',ed])
    return Response(si.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment;filename=my_stats.csv'})


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    VALID_THEMES = {'light', 'dark'}
    VALID_FONT_SIZES = {'small', 'medium', 'large'}
    VALID_NAVBAR_POSITIONS = {'top', 'left'}

    if request.method == 'POST':
        theme = request.form.get('theme', '').strip()
        font_size = request.form.get('font_size', '').strip()
        navbar_position = request.form.get('navbar_position', '').strip()

        if theme not in VALID_THEMES:
            flash('Invalid theme value.', 'danger')
            return redirect(url_for('main.user_settings'))
        if font_size not in VALID_FONT_SIZES:
            flash('Invalid font size value.', 'danger')
            return redirect(url_for('main.user_settings'))
        if navbar_position not in VALID_NAVBAR_POSITIONS:
            flash('Invalid navbar position value.', 'danger')
            return redirect(url_for('main.user_settings'))

        current_user.theme = theme
        current_user.font_size = font_size
        current_user.navbar_position = navbar_position
        _ok()
        flash('Settings saved!', 'success')
        return redirect(url_for('main.user_settings'))

    return render_template('settings.html')

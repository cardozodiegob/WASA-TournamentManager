"""Economy routes: points, shop, inventory, cosmetics, betting history."""
import math
from flask import (Blueprint, render_template, request, redirect, url_for, flash, session)
from flask_login import login_required, current_user
from sqlalchemy import or_

from extensions import db
from models import (User, PointTransaction, CosmeticItem, UserCosmetic, Bet, Match)
from helpers import _ok, _award_points, rate_limit, COSMETIC_CATEGORIES, RARITY_COLORS

economy_bp = Blueprint('economy', __name__)

@economy_bp.route('/points')
@login_required
def points_history():
    pg=request.args.get('page',1,type=int); pp=25
    q=PointTransaction.query.filter_by(user_id=current_user.id).order_by(PointTransaction.created_at.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    txns=q.offset((pg-1)*pp).limit(pp).all()
    return render_template('points.html',txns=txns,pg=pg,tp=tp)

@economy_bp.route('/points/leaderboard')
def points_leaderboard():
    pg=request.args.get('page',1,type=int); pp=25
    q=User.query.filter(User.banned==False,User.points>0).order_by(User.points.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    users=q.offset((pg-1)*pp).limit(pp).all()
    return render_template('points_leaderboard.html',users=users,pg=pg,tp=tp,offset=(pg-1)*pp)

@economy_bp.route('/shop')
def shop():
    items=CosmeticItem.query.filter_by(active=True).order_by(CosmeticItem.category,CosmeticItem.price).all()
    grouped={}
    for it in items: grouped.setdefault(it.category,[]).append(it)
    owned_ids=set()
    if hasattr(current_user,'is_authenticated') and current_user.is_authenticated:
        owned_ids={uc.item_id for uc in current_user.cosmetics.all()}
    # Category display metadata
    cat_icons = {
        'avatar_frame': 'circle-user', 'profile_border': 'border-style', 'profile_banner': 'image',
        'badge': 'certificate', 'name_color': 'palette', 'name_effect': 'wand-magic-sparkles',
        'chat_flair': 'comment', 'profile_background': 'fill-drip', 'profile_effect': 'sun', 'title': 'tag'
    }
    cat_labels = {
        'avatar_frame': 'Avatar Frames', 'profile_border': 'Profile Borders', 'profile_banner': 'Profile Banners',
        'badge': 'Badges', 'name_color': 'Name Colors', 'name_effect': 'Name Effects',
        'chat_flair': 'Chat Flairs', 'profile_background': 'Backgrounds', 'profile_effect': 'Profile Effects', 'title': 'Titles'
    }
    return render_template('shop.html', grouped=grouped, owned_ids=owned_ids,
                           categories=COSMETIC_CATEGORIES, cat_icons=cat_icons, cat_labels=cat_labels,
                           rarity_colors=RARITY_COLORS)

@economy_bp.route('/shop/buy/<int:item_id>', methods=['POST'])
@login_required
@rate_limit(10, 60, lambda: f"shop:{current_user.id}")
def shop_buy(item_id):
    it=CosmeticItem.query.get_or_404(item_id)
    if not it.active: flash('Item not available.','danger'); return redirect(url_for('economy.shop'))
    if UserCosmetic.query.filter_by(user_id=current_user.id,item_id=item_id).first():
        flash('You already own this item.','warning'); return redirect(url_for('economy.shop'))
    if not _award_points(current_user.id, -it.price, f'Purchased cosmetic: {it.name}'):
        flash('Insufficient PongCoins.','danger'); return redirect(url_for('economy.shop'))
    db.session.add(UserCosmetic(user_id=current_user.id,item_id=item_id)); _ok()
    flash(f'Purchased {it.name}!','success'); return redirect(url_for('economy.shop'))


@economy_bp.route('/inventory')
@login_required
def inventory():
    cosmetics=current_user.cosmetics.order_by(UserCosmetic.purchased_at.desc()).all()
    return render_template('inventory.html',cosmetics=cosmetics)

@economy_bp.route('/inventory/equip/<int:uc_id>', methods=['POST'])
@login_required
def inventory_equip(uc_id):
    uc=UserCosmetic.query.get_or_404(uc_id)
    if uc.user_id!=current_user.id: flash('Not yours.','danger'); return redirect(url_for('economy.inventory'))
    item_name=uc.item.name
    cat=uc.item.category
    if uc.equipped:
        uc.equipped=False; _ok(); flash(f'Unequipped {item_name}.','info')
    else:
        # Unequip others in same category using direct update to avoid ORM cascade issues
        UserCosmetic.query.filter(
            UserCosmetic.user_id==current_user.id,
            UserCosmetic.id!=uc.id,
            UserCosmetic.equipped==True
        ).filter(
            UserCosmetic.item_id.in_(
                db.session.query(CosmeticItem.id).filter(CosmeticItem.category==cat)
            )
        ).update({UserCosmetic.equipped: False}, synchronize_session='fetch')
        uc.equipped=True; _ok(); flash(f'Equipped {item_name}!','success')
    return redirect(url_for('economy.inventory'))

@economy_bp.route('/bets')
@login_required
def bet_history():
    pg=request.args.get('page',1,type=int); pp=25
    q=Bet.query.filter_by(user_id=current_user.id).order_by(Bet.created_at.desc())
    total=q.count(); tp=max(1,math.ceil(total/pp)); pg=min(pg,tp)
    bets=q.offset((pg-1)*pp).limit(pp).all()
    all_bets=Bet.query.filter_by(user_id=current_user.id).all()
    total_bets=len(all_bets); wins=sum(1 for b in all_bets if b.status=='won')
    losses=sum(1 for b in all_bets if b.status=='lost')
    total_wagered=sum(b.amount for b in all_bets)
    total_payout=sum((b.payout or 0) for b in all_bets if b.status=='won')
    total_lost=sum(b.amount for b in all_bets if b.status=='lost')
    net_profit=total_payout - total_lost - sum(b.amount for b in all_bets if b.status=='won')
    # Open matches available for betting (not your own, not already verified)
    my_bet_match_ids=[b.match_id for b in Bet.query.filter_by(user_id=current_user.id,status='active').all()]
    open_q=Match.query.filter(
        Match.state.in_(['pending','accepted','scheduled']),
        Match.p1_id.isnot(None), Match.p2_id.isnot(None),
        Match.p1_id!=current_user.id, Match.p2_id!=current_user.id
    ).order_by(Match.scheduled_at.asc().nullslast(), Match.played_at.desc()).limit(20).all()
    open_matches=[m for m in open_q if m.id not in my_bet_match_ids]
    return render_template('bets.html',bets=bets,pg=pg,tp=tp,total_bets=total_bets,wins=wins,losses=losses,total_wagered=total_wagered,net_profit=net_profit,open_matches=open_matches)

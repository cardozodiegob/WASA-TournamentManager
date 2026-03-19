from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, render_template, abort, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import and_, or_
import markupsafe

from extensions import db, app, log
from helpers import _ok, _admin, is_chat_muted, _serialize_chat_message, _serialize_dm_message, _limiter
from models import ChatMessage, User, Clan, clan_members, DMConversation, DMMessage

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


# ---------------------------------------------------------------------------
# GET /chat  (redirect to home — widget handles chat now)
# ---------------------------------------------------------------------------
@chat_bp.route('/')
@login_required
def global_chat():
    return redirect(url_for('main.home'), 302)


# ---------------------------------------------------------------------------
# GET /chat/clan/<int:cid>  (redirect to clan page)
# ---------------------------------------------------------------------------
@chat_bp.route('/clan/<int:cid>')
@login_required
def clan_chat(cid):
    return redirect(url_for('clans.clan_view', cid=cid), 302)


# ---------------------------------------------------------------------------
# POST /chat/send
# ---------------------------------------------------------------------------
@chat_bp.route('/send', methods=['POST'])
@login_required
def send():
    if current_user.banned:
        return jsonify(ok=False, error="You are banned from chat"), 403

    if is_chat_muted(current_user):
        exp = current_user.chat_muted_until
        if exp and exp.year == 9999:
            detail = "permanently"
        else:
            detail = exp.isoformat() if exp else "unknown"
        return jsonify(ok=False, error=f"You are muted. Mute expires: {detail}"), 403

    data = request.get_json(force=True, silent=True) or {}
    room = data.get('room', '')
    clan_id = data.get('clan_id')
    content = data.get('content', '')

    if room not in ('global', 'clan'):
        return jsonify(ok=False, error="Invalid room"), 400

    if room == 'clan':
        if not clan_id:
            return jsonify(ok=False, error="clan_id required for clan chat"), 400
        row = db.session.execute(
            clan_members.select().where(
                and_(clan_members.c.user_id == current_user.id,
                     clan_members.c.clan_id == clan_id)
            )
        ).first()
        if not row:
            return jsonify(ok=False, error="You are not a member of this clan"), 403

    content = content.strip()
    if not content:
        return jsonify(ok=False, error="Message cannot be empty"), 400
    if len(content) > 500:
        return jsonify(ok=False, error="Message too long (max 500 characters)"), 400

    # Rate limit: 5 messages per 10 seconds per user
    allowed, retry_after = _limiter.check(f'chat:{current_user.id}', 5, 10)
    if not allowed:
        return jsonify(ok=False, error="Rate limit exceeded", retry_after=retry_after), 429

    content = str(markupsafe.escape(content))

    msg = ChatMessage(
        user_id=current_user.id,
        room_type=room,
        clan_id=clan_id if room == 'clan' else None,
        content=content,
    )
    db.session.add(msg)
    if not _ok():
        return jsonify(ok=False, error="Failed to save message"), 500

    return jsonify(ok=True, message=_serialize_chat_message(msg))


# ---------------------------------------------------------------------------
# GET /chat/poll
# ---------------------------------------------------------------------------
@chat_bp.route('/poll')
@login_required
def poll():
    if current_user.banned:
        return jsonify(ok=False, error="Forbidden"), 403

    room = request.args.get('room', '')
    clan_id = request.args.get('clan_id', type=int)
    since_id = request.args.get('since_id', type=int)

    if room not in ('global', 'clan'):
        return jsonify(ok=False, error="Invalid room"), 400

    if room == 'clan':
        if not clan_id:
            return jsonify(ok=False, error="clan_id required for clan chat"), 400
        row = db.session.execute(
            clan_members.select().where(
                and_(clan_members.c.user_id == current_user.id,
                     clan_members.c.clan_id == clan_id)
            )
        ).first()
        if not row:
            return jsonify(ok=False, error="You are not a member of this clan"), 403

    q = ChatMessage.query.filter_by(room_type=room)
    if room == 'clan':
        q = q.filter_by(clan_id=clan_id)

    if since_id:
        messages = q.filter(ChatMessage.id > since_id).order_by(ChatMessage.id.asc()).all()
    else:
        # Last 50 messages: order desc, limit 50, then reverse
        messages = q.order_by(ChatMessage.id.desc()).limit(50).all()
        messages.reverse()

    return jsonify(ok=True, messages=[_serialize_chat_message(m) for m in messages])


# ---------------------------------------------------------------------------
# POST /chat/delete/<msg_id>  (admin)
# ---------------------------------------------------------------------------
@chat_bp.route('/delete/<int:msg_id>', methods=['POST'])
@_admin
def delete_message(msg_id):
    msg = ChatMessage.query.get(msg_id)
    if not msg:
        return jsonify(ok=False, error="Message not found"), 404
    db.session.delete(msg)
    _ok()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# POST /chat/mute/<uid>  (admin)
# ---------------------------------------------------------------------------
@chat_bp.route('/mute/<int:uid>', methods=['POST'])
@_admin
def mute_user(uid):
    user = User.query.get(uid)
    if not user:
        return jsonify(ok=False, error="User not found"), 404
    data = request.get_json(force=True, silent=True) or {}
    duration = data.get('duration')
    if duration:
        user.chat_muted_until = datetime.now(timezone.utc) + timedelta(minutes=int(duration))
    else:
        user.chat_muted_until = datetime(9999, 12, 31, tzinfo=timezone.utc)
    _ok()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# POST /chat/unmute/<uid>  (admin)
# ---------------------------------------------------------------------------
@chat_bp.route('/unmute/<int:uid>', methods=['POST'])
@_admin
def unmute_user(uid):
    user = User.query.get(uid)
    if not user:
        return jsonify(ok=False, error="User not found"), 404
    user.chat_muted_until = None
    _ok()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# POST /chat/cleanup  (admin)
# ---------------------------------------------------------------------------
@chat_bp.route('/cleanup', methods=['POST'])
@_admin
def cleanup():
    now = datetime.now(timezone.utc)
    global_cutoff = now - timedelta(days=7)
    clan_cutoff = now - timedelta(days=30)

    count = 0
    count += ChatMessage.query.filter(
        ChatMessage.room_type == 'global',
        ChatMessage.created_at < global_cutoff
    ).delete(synchronize_session=False)
    count += ChatMessage.query.filter(
        ChatMessage.room_type == 'clan',
        ChatMessage.created_at < clan_cutoff
    ).delete(synchronize_session=False)

    dm_cutoff = now - timedelta(days=30)
    count += DMMessage.query.filter(
        DMMessage.created_at < dm_cutoff
    ).delete(synchronize_session=False)

    db.session.commit()
    return jsonify(ok=True, deleted=count)


# ---------------------------------------------------------------------------
# POST /chat/dm/start
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/start', methods=['POST'])
@login_required
def dm_start():
    if current_user.banned:
        return jsonify(ok=False, error="You are banned from chat"), 403

    data = request.get_json(force=True, silent=True) or {}
    target_id = data.get('user_id')
    if not target_id:
        return jsonify(ok=False, error="user_id required"), 400

    target_id = int(target_id)

    if target_id == current_user.id:
        return jsonify(ok=False, error="Cannot start a conversation with yourself"), 400

    target = User.query.get(target_id)
    if not target:
        return jsonify(ok=False, error="User not found"), 404

    u1 = min(current_user.id, target_id)
    u2 = max(current_user.id, target_id)

    conv = DMConversation.query.filter_by(user1_id=u1, user2_id=u2).first()
    if not conv:
        conv = DMConversation(user1_id=u1, user2_id=u2)
        db.session.add(conv)
        if not _ok():
            return jsonify(ok=False, error="Failed to create conversation"), 500

    return jsonify(ok=True, conversation={
        'id': conv.id,
        'other_user': {
            'id': target.id,
            'display_name': target.name(),
            'avatar': target.avatar,
        }
    })


# ---------------------------------------------------------------------------
# POST /chat/dm/send
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/send', methods=['POST'])
@login_required
def dm_send():
    if current_user.banned:
        return jsonify(ok=False, error="You are banned from chat"), 403

    if is_chat_muted(current_user):
        exp = current_user.chat_muted_until
        if exp and exp.year == 9999:
            detail = "permanently"
        else:
            detail = exp.isoformat() if exp else "unknown"
        return jsonify(ok=False, error=f"You are muted. Mute expires: {detail}"), 403

    data = request.get_json(force=True, silent=True) or {}
    conversation_id = data.get('conversation_id')
    content = data.get('content', '')

    if not conversation_id:
        return jsonify(ok=False, error="conversation_id required"), 400

    conv = DMConversation.query.get(int(conversation_id))
    if not conv:
        return jsonify(ok=False, error="Conversation not found"), 404

    if current_user.id not in (conv.user1_id, conv.user2_id):
        return jsonify(ok=False, error="Forbidden"), 403

    content = content.strip()
    if not content:
        return jsonify(ok=False, error="Message cannot be empty"), 400
    if len(content) > 500:
        return jsonify(ok=False, error="Message too long (max 500 characters)"), 400

    # Rate limit: 5 messages per 10 seconds per user (same key as global/clan chat)
    allowed, retry_after = _limiter.check(f'chat:{current_user.id}', 5, 10)
    if not allowed:
        return jsonify(ok=False, error="Rate limit exceeded", retry_after=retry_after), 429

    content = str(markupsafe.escape(content))

    msg = DMMessage(
        conversation_id=conv.id,
        sender_id=current_user.id,
        content=content,
    )
    db.session.add(msg)
    conv.last_message_at = datetime.now(timezone.utc)
    if not _ok():
        return jsonify(ok=False, error="Failed to save message"), 500

    # Update sender's last_read so own messages don't trigger unread badge
    if current_user.id == conv.user1_id:
        conv.user1_last_read = msg.id
    else:
        conv.user2_last_read = msg.id
    _ok()

    return jsonify(ok=True, message=_serialize_dm_message(msg))


# ---------------------------------------------------------------------------
# GET /chat/dm/poll
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/poll')
@login_required
def dm_poll():
    if current_user.banned:
        return jsonify(ok=False, error="Forbidden"), 403

    conversation_id = request.args.get('conversation_id', type=int)
    if not conversation_id:
        return jsonify(ok=False, error="conversation_id required"), 400

    conv = DMConversation.query.get(conversation_id)
    if not conv:
        return jsonify(ok=False, error="Conversation not found"), 404

    if current_user.id not in (conv.user1_id, conv.user2_id):
        return jsonify(ok=False, error="Forbidden"), 403

    since_id = request.args.get('since_id', type=int)

    if since_id:
        messages = DMMessage.query.filter(
            DMMessage.conversation_id == conv.id,
            DMMessage.id > since_id
        ).order_by(DMMessage.id.asc()).all()
    else:
        # Last 50 messages: order desc, limit 50, then reverse
        messages = DMMessage.query.filter_by(
            conversation_id=conv.id
        ).order_by(DMMessage.id.desc()).limit(50).all()
        messages.reverse()

    return jsonify(ok=True, messages=[_serialize_dm_message(m) for m in messages])


# ---------------------------------------------------------------------------
# GET /chat/dm/list
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/list')
@login_required
def dm_list():
    if current_user.banned:
        return jsonify(ok=False, error="Forbidden"), 403

    convs = DMConversation.query.filter(
        or_(
            DMConversation.user1_id == current_user.id,
            DMConversation.user2_id == current_user.id,
        )
    ).order_by(DMConversation.last_message_at.desc()).all()

    result = []
    for conv in convs:
        # Determine the other user
        if current_user.id == conv.user1_id:
            other = conv.user2
            last_read = conv.user1_last_read
        else:
            other = conv.user1
            last_read = conv.user2_last_read

        # Unread count: messages with id > user's last_read
        unread_count = DMMessage.query.filter(
            DMMessage.conversation_id == conv.id,
            DMMessage.id > last_read,
        ).count()

        # Last message preview
        last_msg = DMMessage.query.filter_by(
            conversation_id=conv.id
        ).order_by(DMMessage.id.desc()).first()

        result.append({
            'id': conv.id,
            'other_user': {
                'id': other.id,
                'display_name': other.name(),
                'avatar': other.avatar,
            },
            'last_message': last_msg.content if last_msg else None,
            'unread_count': unread_count,
        })

    return jsonify(ok=True, conversations=result)


# ---------------------------------------------------------------------------
# POST /chat/dm/read
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/read', methods=['POST'])
@login_required
def dm_read():
    if current_user.banned:
        return jsonify(ok=False, error="Forbidden"), 403

    data = request.get_json(force=True, silent=True) or {}
    conversation_id = data.get('conversation_id')
    if not conversation_id:
        return jsonify(ok=False, error="conversation_id required"), 400

    conv = DMConversation.query.get(int(conversation_id))
    if not conv:
        return jsonify(ok=False, error="Conversation not found"), 404

    if current_user.id not in (conv.user1_id, conv.user2_id):
        return jsonify(ok=False, error="Forbidden"), 403

    max_msg = db.session.query(db.func.max(DMMessage.id)).filter_by(conversation_id=conv.id).scalar() or 0

    if current_user.id == conv.user1_id:
        conv.user1_last_read = max_msg
    else:
        conv.user2_last_read = max_msg

    _ok()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# POST /chat/dm/delete/<msg_id>  (admin)
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/delete/<int:msg_id>', methods=['POST'])
@_admin
def dm_delete(msg_id):
    msg = DMMessage.query.get(msg_id)
    if not msg:
        return jsonify(ok=False, error="Message not found"), 404
    db.session.delete(msg)
    _ok()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# GET /chat/dm/search-users  (user search for DM)
# ---------------------------------------------------------------------------
@chat_bp.route('/dm/search-users')
@login_required
def dm_search_users():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify(ok=True, users=[])
    from sqlalchemy import or_ as _or
    results = User.query.filter(
        User.banned == False,
        User.id != current_user.id,
        _or(
            User.username.ilike(f'%{q}%'),
            User.display_name.ilike(f'%{q}%'),
        )
    ).limit(10).all()
    return jsonify(ok=True, users=[
        {'id': u.id, 'display_name': u.name(), 'avatar': u.avatar}
        for u in results
    ])

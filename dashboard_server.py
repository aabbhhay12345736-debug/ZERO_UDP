# -*- coding: utf-8 -*-
"""
ZEROTRACE BR MODE - Level Up Control Panel (UPGRADED)
Web Dashboard with Authentication + User Management + Start/Stop Control
+ Global Refresh + Per-Account Refresh + EXP Remaining + Progress Tracking
+ Ownership Verification + Pause/Resume + Uptime Tracking + BULK ADD + BULK DELETE
"""

import asyncio
import json
import os
import time
import hashlib
import secrets
from typing import Dict, List, Any, Optional
from aiohttp import web


# ==================== CONFIG ====================
USERS_FILE = "users.json"
SESSIONS_FILE = "sessions.json"
DEFAULT_ADMIN_USER = "ZEROTRACE"
DEFAULT_ADMIN_PASS = "ZEROTRACE-786"
SESSION_TTL = 3600 * 6   # 🔥 6 hours
ACCOUNTS_FILE = "accounts.json"

# 🔥 Minimum level required to add account
MIN_LEVEL_REQUIRED = 1

# 🔥 Global refresh concurrency (max accounts refresh in parallel)
MAX_CONCURRENT_REFRESHES = 5

# 🔥 Bulk add cap (max accounts per bulk request)
MAX_BULK_SIZE = 500

# 🔥 Bulk delete batch size (10 accounts per batch)
BULK_DELETE_BATCH_SIZE = 10

# 🔥 Max wait for active matches to finish before force delete (seconds)
BULK_DELETE_MATCH_WAIT = 900.0


# ==================== EXP TABLE (Level 1-100) ====================
EXP_TABLE: Dict[int, int] = {
    1: 0, 2: 48, 3: 202, 4: 544, 5: 1012, 6: 1844, 7: 2792, 8: 3800,
    9: 4870, 10: 6004, 11: 7192, 12: 8448, 13: 9760, 14: 11140, 15: 12566,
    16: 14060, 17: 15610, 18: 17224, 19: 18902, 20: 20632, 21: 22424, 22: 24278,
    23: 26192, 24: 28166, 25: 30200, 26: 32294, 27: 34448, 28: 37804, 29: 41274,
    30: 44870, 31: 48582, 32: 53394, 33: 58566, 34: 64096, 35: 69994, 36: 76460,
    37: 83506, 38: 91128, 39: 99322, 40: 108092, 41: 120144, 42: 133266, 43: 147472,
    44: 162760, 45: 179126, 46: 196572, 47: 215368, 48: 235516, 49: 257010, 50: 279860,
    51: 304056, 52: 348318, 53: 394982, 54: 444044, 55: 495508, 56: 549364, 57: 633756,
    58: 721744, 59: 813336, 60: 908522, 61: 1041438, 62: 1180352, 63: 1325266,
    64: 1476184, 65: 1634300, 66: 1840946, 67: 2056594, 68: 2281242, 69: 2514880,
    70: 2757530, 71: 3059506, 72: 3372284, 73: 3699456, 74: 4041030, 75: 4397002,
    76: 4829104, 77: 5282204, 78: 5756304, 79: 6251408, 80: 6776502, 81: 7381324,
    82: 8043154, 83: 8752982, 84: 9510808, 85: 10316338, 86: 11277190, 87: 12291748,
    88: 13360304, 89: 14482858, 90: 15659418, 91: 17026708, 92: 18453950, 93: 19941280,
    94: 21488570, 95: 23095858, 96: 24763138, 97: 26490428, 98: 28378704, 99: 30124996,
    100: 32032884
}


def calculate_level_progress(level: int, current_exp: int) -> Dict[str, Any]:
    """Calculate EXP progress, remaining EXP, and % for a given level."""
    level = max(1, level)
    next_level = min(100, level + 1)
    base_exp = EXP_TABLE.get(level, 0)
    target_exp = EXP_TABLE.get(next_level, base_exp + 50000)

    needed_for_level = max(1, target_exp - base_exp)
    earned_in_level = max(0, current_exp - base_exp)
    remaining_exp = max(0, target_exp - current_exp)
    progress_pct = min(100.0, max(0.0, (earned_in_level / needed_for_level) * 100.0))

    return {
        "next_level": next_level,
        "base_exp": base_exp,
        "target_exp": target_exp,
        "needed_for_level": needed_for_level,
        "earned_in_level": earned_in_level,
        "remaining_exp": remaining_exp,
        "progress_pct": round(progress_pct, 1)
    }


# ==================== BOT STATE ====================
class BotState:
    def __init__(self):
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers: Dict[str, asyncio.Task] = {}
        self.refresh_callbacks: Dict[str, Any] = {}
        self.account_credentials: Dict[str, Dict[str, Any]] = {}

        # 🔥 Pending add requests (async verify flow)
        self.pending_add: Dict[str, Dict[str, Any]] = {}

        # 🔥 Pending BULK add requests (async bulk verify flow)
        self.pending_bulk: Dict[str, Dict[str, Any]] = {}

        # 🔥 Pending BULK DELETE requests
        self.pending_bulk_delete: Dict[str, Dict[str, Any]] = {}

        # 🔥 Owner mapping (account_id -> username)
        self.account_owner: Dict[str, str] = {}

        # 🔥 UID Linking maps
        self.login_uid_to_account_id: Dict[str, str] = {}
        self.account_id_to_login_uid: Dict[str, str] = {}
        self.token_key_to_account_id: Dict[str, str] = {}
        self.account_id_to_token_key: Dict[str, str] = {}

        # 🔥 BACKWARD COMPATIBILITY ALIASES
        self.game_to_auth_id = self.account_id_to_login_uid
        self.auth_to_game_id = self.login_uid_to_account_id
        self.account_token_map = self.token_key_to_account_id

        # 🔥 Pause system
        self.paused_accounts: set = set()

        # 🔥 Active writers (for pause → close socket)
        self.active_writers: Dict[str, set] = {}

        # 🔥 Uptime tracking
        self.account_start_time: Dict[str, float] = {}
        self.account_pause_duration: Dict[str, float] = {}
        self.account_paused_at: Dict[str, float] = {}

    # ---------- Writer Registry ----------
    def register_writer(self, uid: str, writer):
        uid_str = str(uid)
        if uid_str not in self.active_writers:
            self.active_writers[uid_str] = set()
        self.active_writers[uid_str].add(writer)

    def unregister_writer(self, uid: str, writer):
        uid_str = str(uid)
        if uid_str in self.active_writers:
            self.active_writers[uid_str].discard(writer)
            if not self.active_writers[uid_str]:
                self.active_writers.pop(uid_str, None)

    def close_writers_for_account(self, uid: str):
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.login_uid_to_account_id:
            candidates.add(str(self.login_uid_to_account_id[uid_str]))
        if uid_str in self.account_id_to_login_uid:
            candidates.add(str(self.account_id_to_login_uid[uid_str]))
        if uid_str in self.token_key_to_account_id:
            mapped = self.token_key_to_account_id[uid_str]
            candidates.add(str(mapped))
            candidates.add(str(mapped)[:16])

        for c in list(candidates):
            writers = list(self.active_writers.get(c, []))
            for w in writers:
                try:
                    if hasattr(w, "close"):
                        if hasattr(w, "is_closing"):
                            if not w.is_closing():
                                w.close()
                        else:
                            w.close()
                except Exception:
                    pass
            self.active_writers.pop(c, None)

    # ---------- UID Linking ----------
    def link_uids(self, login_uid: str, account_id: str):
        if not login_uid or not account_id:
            return
        login_uid = str(login_uid).strip()
        account_id = str(account_id).strip()
        if not login_uid or not account_id or login_uid == account_id:
            return
        if login_uid.startswith("tok_"):
            self.token_key_to_account_id[login_uid] = account_id
            self.account_id_to_token_key[account_id] = login_uid
        else:
            self.login_uid_to_account_id[login_uid] = account_id
            self.account_id_to_login_uid[account_id] = login_uid

    def get_all_related_uids(self, uid: str) -> set:
        if not uid:
            return set()
        uid = str(uid).strip()
        related = {uid}
        queue = [uid]
        visited = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for mapping in (self.login_uid_to_account_id,
                            self.account_id_to_login_uid,
                            self.token_key_to_account_id,
                            self.account_id_to_token_key):
                if current in mapping:
                    nxt = mapping[current]
                    if nxt not in related:
                        related.add(nxt)
                        queue.append(nxt)
        return related

    # ---------- Logging ----------
    def log(self, message: str, level: str = "info", uid: Optional[str] = None):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "uid": str(uid) if uid else None
        }
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    # ---------- Pause System ----------
    def is_paused(self, uid: str) -> bool:
        uid_str = str(uid)
        if uid_str in self.paused_accounts:
            return True
        game_id = self.login_uid_to_account_id.get(uid_str)
        if game_id and game_id in self.paused_accounts:
            return True
        auth_uid = self.account_id_to_login_uid.get(uid_str)
        if auth_uid and auth_uid in self.paused_accounts:
            return True
        acc = self.accounts.get(uid_str)
        if acc and acc.get("is_paused"):
            return True
        return False

    def toggle_pause(self, uid: str) -> bool:
        uid_str = str(uid)
        candidates = {uid_str}
        if uid_str in self.login_uid_to_account_id:
            candidates.add(self.login_uid_to_account_id[uid_str])
        if uid_str in self.account_id_to_login_uid:
            candidates.add(self.account_id_to_login_uid[uid_str])

        target_acc = None
        target_key = uid_str
        for c in candidates:
            if c in self.accounts:
                target_acc = self.accounts[c]
                target_key = c
                break

        is_now_paused = not self.is_paused(uid_str)
        if is_now_paused:
            for c in candidates:
                self.paused_accounts.add(c)
                self.close_writers_for_account(c)
            if target_acc:
                target_acc["is_paused"] = True
                target_acc["paused_at"] = time.time()
                target_acc["status"] = "PAUSED"
                self.account_paused_at[target_key] = time.time()
            nick = target_acc.get("nickname", target_key) if target_acc else target_key
            self.log(f"⏸ UID {target_key} ({nick}) PAUSED (TCP socket disconnected).", "warning", target_key)
            if "on_pause_toggle" in self.refresh_callbacks:
                try:
                    asyncio.create_task(self.refresh_callbacks["on_pause_toggle"](target_key, True))
                except Exception:
                    pass
        else:
            for c in candidates:
                self.paused_accounts.discard(c)
            if target_acc:
                target_acc["is_paused"] = False
                if target_acc.get("paused_at"):
                    pause_dur = time.time() - target_acc["paused_at"]
                    self.account_pause_duration[target_key] = (
                        self.account_pause_duration.get(target_key, 0.0) + pause_dur
                    )
                    target_acc["paused_at"] = None
                target_acc["status"] = "ONLINE"
                self.account_paused_at.pop(target_key, None)
            nick = target_acc.get("nickname", target_key) if target_acc else target_key
            self.log(f"▶ UID {target_key} ({nick}) RESUMED.", "success", target_key)
            if "on_pause_toggle" in self.refresh_callbacks:
                try:
                    asyncio.create_task(self.refresh_callbacks["on_pause_toggle"](target_key, False))
                except Exception:
                    pass
        return is_now_paused

    def toggle_pause_all(self) -> bool:
        any_active = any(not self.is_paused(k) for k in self.accounts.keys())
        for k in list(self.accounts.keys()):
            current_paused = self.is_paused(k)
            if any_active and not current_paused:
                self.toggle_pause(k)
            elif not any_active and current_paused:
                self.toggle_pause(k)
        return any_active

    def get_account_uptime(self, uid_str: str) -> int:
        acc = self.accounts.get(uid_str)
        if not acc:
            mapped = self.account_id_to_login_uid.get(uid_str) or self.login_uid_to_account_id.get(uid_str)
            if mapped and mapped in self.accounts:
                acc = self.accounts[mapped]
                uid_str = mapped
        if not acc:
            return 0
        start_t = self.account_start_time.get(uid_str, acc.get("start_time", time.time()))
        total_pause = self.account_pause_duration.get(uid_str, 0.0)
        if acc.get("is_paused") and self.account_paused_at.get(uid_str):
            return max(0, int(self.account_paused_at[uid_str] - start_t - total_pause))
        return max(0, int(time.time() - start_t - total_pause))

    # ---------- Account Registration ----------
    def register_account(self, uid, nickname, region, level, exp, likes=0,
                        auth_type="guest", owner=None, token=None, auth_uid=None):
        uid_str = str(uid)
        auth_uid_str = str(auth_uid) if auth_uid else self.account_id_to_login_uid.get(uid_str, "")

        if auth_uid_str:
            self.login_uid_to_account_id[auth_uid_str] = uid_str
            self.account_id_to_login_uid[uid_str] = auth_uid_str
        if token:
            tok_key = f"tok_{token[:20]}"
            self.token_key_to_account_id[tok_key] = uid_str
            self.account_id_to_token_key[uid_str] = tok_key
            if auth_uid_str:
                self.token_key_to_account_id[auth_uid_str] = uid_str

        prog = calculate_level_progress(level or 1, exp or 0)
        lvl_val = level or 1

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str,
                "auth_uid": auth_uid_str or "",
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD",
                "level": lvl_val,
                "next_level": prog["next_level"],
                "mode": "BR",
                "mode_label": "Battle Royale",
                "initial_level": lvl_val,
                "initial_exp": exp or 0,
                "current_exp": exp or 0,
                "gained_exp": 0,
                "level_gained": 0,
                "remaining_exp": prog["remaining_exp"],
                "target_exp": prog["target_exp"],
                "needed_for_level": prog["needed_for_level"],
                "earned_in_level": prog["earned_in_level"],
                "progress_pct": prog["progress_pct"],
                "likes": likes or 0,
                "status": "PAUSED" if self.is_paused(uid_str) else "ONLINE",
                "matches_played": 0,
                "active_matches": 0,
                "last_match_time": None,
                "last_updated": time.strftime("%H:%M:%S"),
                "last_refresh": "Never",
                "added_at": now_str,
                "token": token or "",
                "auth_type": auth_type,
                "start_time": time.time(),
                "is_paused": self.is_paused(uid_str),
                "paused_at": time.time() if self.is_paused(uid_str) else None,
                "total_pause_duration": 0.0,
                "owner": owner
            }
            self.account_start_time[uid_str] = time.time()
        else:
            acc = self.accounts[uid_str]
            if auth_uid_str:
                acc["auth_uid"] = auth_uid_str
            if nickname:
                acc["nickname"] = nickname
            if region:
                acc["region"] = region
            if level:
                acc["level"] = level
                acc["level_gained"] = max(0, level - acc.get("initial_level", level))
            if token:
                acc["token"] = token
            acc["current_exp"] = exp or 0
            acc["gained_exp"] = max(0, (exp or 0) - acc["initial_exp"])
            acc["next_level"] = prog["next_level"]
            acc["remaining_exp"] = prog["remaining_exp"]
            acc["target_exp"] = prog["target_exp"]
            acc["needed_for_level"] = prog["needed_for_level"]
            acc["earned_in_level"] = prog["earned_in_level"]
            acc["progress_pct"] = prog["progress_pct"]
            acc["likes"] = likes or 0
            acc["auth_type"] = auth_type
            if not acc.get("is_paused"):
                acc["status"] = "ONLINE"
            acc["last_updated"] = time.strftime("%H:%M:%S")
            if owner:
                acc["owner"] = owner
        self.recalc_totals()

    def update_exp(self, uid, current_exp, level=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old = acc["current_exp"]
            old_level = acc.get("level", 1)
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
                acc["level_gained"] = max(0, level - acc.get("initial_level", level))
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            prog = calculate_level_progress(acc["level"], current_exp)
            acc["next_level"] = prog["next_level"]
            acc["remaining_exp"] = prog["remaining_exp"]
            acc["target_exp"] = prog["target_exp"]
            acc["needed_for_level"] = prog["needed_for_level"]
            acc["earned_in_level"] = prog["earned_in_level"]
            acc["progress_pct"] = prog["progress_pct"]
            acc["last_updated"] = time.strftime("%H:%M:%S")

            if old_level < acc["level"]:
                self.log(
                    f"🎉 LEVEL UP! {acc['nickname']} reached Level {acc['level']}!",
                    "success", uid_str
                )

            diff = current_exp - old
            if diff > 0:
                self.log(
                    f"{acc['nickname']} gained +{diff:,} EXP | Lv {acc['level']} "
                    f"({prog['progress_pct']}% - {prog['remaining_exp']:,} EXP to Lv {prog['next_level']})",
                    "success", uid_str
                )
            self.recalc_totals()

    def update_status(self, uid, status, active_matches=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid):
        self.total_matches += 1
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")
            self.log(
                f"⚔ Match #{self.accounts[uid_str]['matches_played']} finished for "
                f"{self.accounts[uid_str]['nickname']} ({uid_str})",
                "info", uid_str
            )

    def recalc_totals(self):
        self.total_gained_exp = sum(a.get("gained_exp", 0) for a in self.accounts.values())

    def count_user_accounts(self, username: str) -> int:
        if not username:
            return 0
        count = 0
        for acc in self.accounts.values():
            if acc.get("owner") == username:
                count += 1
        return count


bot_state = BotState()


# ==================== USER MANAGEMENT ====================
def _hash_password(password: str) -> str:
    salt = "zerotrace_salt_v1"
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _load_users() -> Dict:
    if not os.path.exists(USERS_FILE):
        default = {
            DEFAULT_ADMIN_USER: {
                "username": DEFAULT_ADMIN_USER,
                "password_hash": _hash_password(DEFAULT_ADMIN_PASS),
                "role": "admin",
                "max_slots": 999,
                "active_jobs": 0,
                "created_at": time.time(),
                "expires_at": None
            }
        }
        _save_users(default)
        return default
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_users(users: Dict):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        print(f"Failed to save users: {e}")


def _load_sessions() -> Dict:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        active = {k: v for k, v in data.items() if v.get("expires_at", 0) > now}
        if len(active) != len(data):
            _save_sessions(active)
        return active
    except Exception:
        return {}


def _save_sessions(sessions: Dict):
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)
    except Exception:
        pass


def _create_session(username: str) -> str:
    sessions = _load_sessions()

    user_sessions = [(k, v) for k, v in sessions.items() if v.get("username") == username]
    if len(user_sessions) >= 3:
        user_sessions.sort(key=lambda x: x[1].get("created_at", 0))
        for old_token, _ in user_sessions[:len(user_sessions) - 2]:
            del sessions[old_token]

    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "username": username,
        "created_at": time.time(),
        "expires_at": time.time() + SESSION_TTL
    }
    _save_sessions(sessions)
    return token


def _get_session(token: str) -> Optional[Dict]:
    if not token:
        return None
    sessions = _load_sessions()
    return sessions.get(token)


def _destroy_session(token: str):
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)


def _get_user_from_request(request: web.Request) -> Optional[Dict]:
    token = request.cookies.get("session_token")
    session = _get_session(token)
    if not session:
        return None
    users = _load_users()
    username = session.get("username")
    if username not in users:
        return None
    user = users[username]
    if user.get("expires_at") and user["expires_at"] < time.time():
        return None
    return user


def _require_auth(handler):
    async def wrapper(request: web.Request):
        user = _get_user_from_request(request)
        if not user:
            return web.json_response({"error": "Unauthorized"}, status=401)
        request["user"] = user
        return await handler(request)
    return wrapper


def _require_admin(handler):
    async def wrapper(request: web.Request):
        user = _get_user_from_request(request)
        if not user:
            return web.json_response({"error": "Unauthorized"}, status=401)
        if user.get("role") != "admin":
            return web.json_response({"error": "Admin only"}, status=403)
        request["user"] = user
        return await handler(request)
    return wrapper


# ==================== OWNERSHIP CHECK ====================
def _user_owns_account(user: Dict, uid: str) -> bool:
    """Verify that user owns this account (admin bypasses)."""
    if not user or not uid:
        return False
    if user.get("role") == "admin":
        return True
    username = user["username"]
    own_accounts = _get_user_accounts_from_file(username)
    own_uids = set()
    for a in own_accounts:
        if a.get("uid"):
            own_uids.add(str(a["uid"]))
        if a.get("token"):
            own_uids.add(f"tok_{a['token'][:20]}")
    related = bot_state.get_all_related_uids(uid)
    if uid in own_uids:
        return True
    if related & own_uids:
        return True
    return False


# ==================== AUTH HANDLERS ====================
async def handle_login(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        if not username or not password:
            return web.json_response({"success": False, "error": "Username and password required"}, status=400)

        users = _load_users()
        if username not in users:
            return web.json_response({"success": False, "error": "Invalid credentials"}, status=401)

        user = users[username]
        if user["password_hash"] != _hash_password(password):
            return web.json_response({"success": False, "error": "Invalid credentials"}, status=401)

        if user.get("expires_at") and user["expires_at"] < time.time():
            return web.json_response({"success": False, "error": "Account expired. Contact admin."}, status=403)

        token = _create_session(username)
        resp = web.json_response({
            "success": True,
            "user": {
                "username": username,
                "role": user.get("role", "user"),
                "max_slots": user.get("max_slots", 1),
                "active_jobs": user.get("active_jobs", 0),
                "expires_at": user.get("expires_at"),
                "created_at": user.get("created_at")
            }
        })
        resp.set_cookie("session_token", token, max_age=SESSION_TTL, httponly=True, samesite="Lax")
        bot_state.log(f"User '{username}' logged in", "info")
        return resp
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_logout(request: web.Request) -> web.Response:
    token = request.cookies.get("session_token")
    if token:
        _destroy_session(token)
    resp = web.json_response({"success": True})
    resp.del_cookie("session_token")
    return resp


async def handle_me(request: web.Request) -> web.Response:
    user = _get_user_from_request(request)
    if not user:
        return web.json_response({"authenticated": False})
    return web.json_response({
        "authenticated": True,
        "user": {
            "username": user["username"],
            "role": user.get("role", "user"),
            "max_slots": user.get("max_slots", 1),
            "active_jobs": user.get("active_jobs", 0),
            "expires_at": user.get("expires_at"),
            "created_at": user.get("created_at")
        }
    })


@_require_auth
async def handle_change_password(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        old_pass = str(data.get("old_password", ""))
        new_pass = str(data.get("new_password", ""))
        if len(new_pass) < 6:
            return web.json_response({"error": "Password must be at least 6 chars"}, status=400)

        user = request["user"]
        users = _load_users()
        if users[user["username"]]["password_hash"] != _hash_password(old_pass):
            return web.json_response({"error": "Current password incorrect"}, status=400)

        users[user["username"]]["password_hash"] = _hash_password(new_pass)
        _save_users(users)
        bot_state.log(f"User '{user['username']}' changed password", "info")
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== STATS HANDLER ====================
async def handle_get_stats(request: web.Request) -> web.Response:
    user = _get_user_from_request(request)

    if user and user.get("role") == "admin":
        accounts_data = list(bot_state.accounts.values())
    elif user:
        uname = user["username"]
        accounts_data = [a for a in bot_state.accounts.values() if a.get("owner") == uname]
    else:
        accounts_data = []

    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)

    total_matches = sum(a.get("matches_played", 0) for a in accounts_data)
    total_gained = sum(a.get("gained_exp", 0) for a in accounts_data)
    total_active_matches = sum(a.get("active_matches", 0) for a in accounts_data)

    expiry_hours = None
    if user and user.get("expires_at"):
        remaining = user["expires_at"] - time.time()
        expiry_hours = max(0, round(remaining / 3600, 1))

    lean_accounts = []
    for a in accounts_data:
        uid_k = str(a.get("uid", ""))
        lean_accounts.append({
            "uid": uid_k,
            "auth_uid": a.get("auth_uid", ""),
            "nickname": a.get("nickname", "Unknown"),
            "region": a.get("region", "BD"),
            "level": a.get("level", 1),
            "next_level": a.get("next_level", (a.get("level", 1) + 1)),
            "current_exp": a.get("current_exp", 0),
            "gained_exp": a.get("gained_exp", 0),
            "level_gained": a.get("level_gained", 0),
            "remaining_exp": a.get("remaining_exp", 0),
            "progress_pct": a.get("progress_pct", 0.0),
            "status": a.get("status", "ONLINE"),
            "matches_played": a.get("matches_played", 0),
            "active_matches": a.get("active_matches", 0),
            "is_paused": bot_state.is_paused(uid_k),
            "last_match_time": a.get("last_match_time"),
            "added_at": a.get("added_at", "Unknown"),
            "uptime_seconds": bot_state.get_account_uptime(uid_k),
        })

    uptime_sec = max(1, int(time.time() - bot_state.start_time))
    exp_per_hour = int((total_gained / uptime_sec) * 3600) if uptime_sec > 0 else 0

    return web.json_response({
        "total_accounts": len(lean_accounts),
        "total_matches": total_matches,
        "total_active_matches": total_active_matches,
        "total_gained_exp": total_gained,
        "exp_per_hour": exp_per_hour,
        "uptime": uptime_sec,
        "expiry_hours": expiry_hours,
        "used_slots": len(lean_accounts),
        "max_slots": (user.get("max_slots", 1) if user else 0),
        "username": (user["username"] if user else None),
        "role": (user.get("role", "user") if user else None),
        "accounts": lean_accounts,
    })


# ==================== ACCOUNT HELPERS ====================
def _get_user_accounts_from_file(username: str) -> List[Dict]:
    """accounts.json se sirf is user ke accounts nikalo."""
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [a for a in data if a.get("owner") == username]
    except Exception:
        return []


def _get_all_accounts_from_file() -> List[Dict]:
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def _save_all_accounts(accounts: List[Dict]):
    try:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)
    except Exception as e:
        print(f"Failed to save accounts: {e}")


# ==================== ACCOUNT HANDLERS (SINGLE ADD) ====================
@_require_auth
async def handle_add_account(request: web.Request) -> web.Response:
    """
    Flow:
    1. Slot check
    2. Duplicate check
    3. Verify login in BACKGROUND
    4. Level >= 3 check
    5. Save to accounts.json
    """
    try:
        data = await request.json()
        user = request["user"]
        username = user["username"]
        is_admin = user.get("role") == "admin"

        if not is_admin:
            max_slots = user.get("max_slots", 1)
            current_count = len(_get_user_accounts_from_file(username))
            if current_count >= max_slots:
                return web.json_response({
                    "error": f"Slot limit reached ({current_count}/{max_slots}). Contact admin."
                }, status=403)

        payload = {}
        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"error": "UID and Password required"}, status=400)
            payload = {"uid": uid, "password": pwd}
        elif "token" in data and data["token"]:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"error": "Token required"}, status=400)
            payload = {"token": token}
        else:
            return web.json_response({"error": "Invalid payload"}, status=400)

        all_accounts = _get_all_accounts_from_file()
        for a in all_accounts:
            if payload.get("uid") and str(a.get("uid")) == payload["uid"]:
                return web.json_response({"error": "This UID is already added"}, status=400)
            if payload.get("token") and a.get("token") == payload["token"]:
                return web.json_response({"error": "This token is already added"}, status=400)

        verify_id = secrets.token_urlsafe(16)
        bot_state.pending_add[verify_id] = {
            "username": username,
            "payload": payload,
            "created_at": time.time(),
            "status": "verifying",
            "error": None
        }

        bot_state.log(f"Verifying account for {username}...", "info")

        if "on_verify_account" in bot_state.refresh_callbacks:
            asyncio.create_task(
                bot_state.refresh_callbacks["on_verify_account"](verify_id, payload, username)
            )
        else:
            return web.json_response({"error": "Verifier not ready"}, status=500)

        return web.json_response({
            "status": "verifying",
            "verify_id": verify_id
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_auth
async def handle_verify_status(request: web.Request) -> web.Response:
    try:
        verify_id = request.query.get("verify_id", "")
        if not verify_id:
            return web.json_response({"error": "verify_id required"}, status=400)

        entry = bot_state.pending_add.get(verify_id)
        if not entry:
            return web.json_response({"error": "Unknown verify_id"}, status=404)

        user = request["user"]
        if user.get("role") != "admin" and entry.get("username") != user["username"]:
            return web.json_response({"error": "Not yours"}, status=403)

        return web.json_response({
            "status": entry["status"],
            "error": entry.get("error"),
            "account": entry.get("account")
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== ACCOUNT HANDLERS (BULK ADD) ====================
@_require_auth
async def handle_bulk_add(request: web.Request) -> web.Response:
    """
    Bulk add — multiple accounts ek saath.
    Payload: {"accounts": [{"uid": "...", "password": "..."}, ...]}
    """
    try:
        data = await request.json()
        user = request["user"]
        username = user["username"]
        is_admin = user.get("role") == "admin"

        accounts_list = data.get("accounts", [])
        if not isinstance(accounts_list, list) or not accounts_list:
            return web.json_response({"error": "accounts list required"}, status=400)

        # Normalize & filter valid entries
        cleaned = []
        for item in accounts_list:
            if not isinstance(item, dict):
                continue
            uid = str(item.get("uid", "")).strip()
            pwd = str(item.get("password", "")).strip()
            if uid and pwd:
                cleaned.append({"uid": uid, "password": pwd})

        if not cleaned:
            return web.json_response({"error": "No valid uid:password entries"}, status=400)

        # Slot check
        if not is_admin:
            max_slots = user.get("max_slots", 1)
            current_count = len(_get_user_accounts_from_file(username))
            available = max_slots - current_count
            if available <= 0:
                return web.json_response({
                    "error": f"Slot limit reached ({current_count}/{max_slots})"
                }, status=403)
            if len(cleaned) > available:
                cleaned = cleaned[:available]

        # Cap
        if len(cleaned) > MAX_BULK_SIZE:
            cleaned = cleaned[:MAX_BULK_SIZE]

        bulk_id = secrets.token_urlsafe(16)
        bot_state.pending_bulk[bulk_id] = {
            "username": username,
            "total": len(cleaned),
            "created_at": time.time(),
            "status": "verifying",
            "results": [],
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
        }

        bot_state.log(f"Bulk verify started for {username} ({len(cleaned)} accounts)", "info")

        if "on_bulk_verify" in bot_state.refresh_callbacks:
            asyncio.create_task(
                bot_state.refresh_callbacks["on_bulk_verify"](bulk_id, cleaned, username)
            )
        else:
            return web.json_response({"error": "Bulk verifier not ready"}, status=500)

        return web.json_response({
            "status": "verifying",
            "bulk_id": bulk_id,
            "total": len(cleaned)
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_auth
async def handle_bulk_verify_status(request: web.Request) -> web.Response:
    try:
        bulk_id = request.query.get("bulk_id", "")
        if not bulk_id:
            return web.json_response({"error": "bulk_id required"}, status=400)

        entry = bot_state.pending_bulk.get(bulk_id)
        if not entry:
            return web.json_response({"error": "Unknown bulk_id"}, status=404)

        user = request["user"]
        if user.get("role") != "admin" and entry.get("username") != user["username"]:
            return web.json_response({"error": "Not yours"}, status=403)

        return web.json_response({
            "status": entry["status"],
            "total": entry.get("total", 0),
            "success_count": entry.get("success_count", 0),
            "failed_count": entry.get("failed_count", 0),
            "skipped_count": entry.get("skipped_count", 0),
            "results": entry.get("results", []),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== DELETE ACCOUNT (SINGLE) ====================
@_require_auth
async def handle_delete_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        req_auth_uid = str(data.get("auth_uid", "")).strip()
        if not uid and not req_auth_uid:
            return web.json_response({"error": "UID required"}, status=400)

        user = request["user"]
        check_uid = uid or req_auth_uid
        if not _user_owns_account(user, check_uid):
            return web.json_response({"error": "Not your account"}, status=403)

        bot_state.log(f"Deleting account {check_uid}...", "warning", check_uid)
        related_uids = bot_state.get_all_related_uids(check_uid)
        if req_auth_uid:
            related_uids.add(req_auth_uid)

        cancelled_count = 0
        for key in list(bot_state.account_workers.keys()):
            if key in related_uids:
                task = bot_state.account_workers.get(key)
                if task and not task.done():
                    task.cancel()
                    cancelled_count += 1
                del bot_state.account_workers[key]

        for key in list(bot_state.accounts.keys()):
            if key in related_uids:
                del bot_state.accounts[key]

        for key in list(bot_state.account_credentials.keys()):
            if key in related_uids:
                del bot_state.account_credentials[key]
                continue
            cred = bot_state.account_credentials.get(key)
            if cred and isinstance(cred, dict):
                if str(cred.get("account_id", "")) in related_uids:
                    del bot_state.account_credentials[key]
                elif str(cred.get("auth_uid", "")) in related_uids:
                    del bot_state.account_credentials[key]

        existing = _get_all_accounts_from_file()
        new_existing = []
        for acc in existing:
            acc_uid = str(acc.get("uid", "")).strip()
            acc_token = str(acc.get("token", "")).strip()
            if acc_uid in related_uids:
                continue
            if acc_token and f"tok_{acc_token[:20]}" in related_uids:
                continue
            new_existing.append(acc)
        _save_all_accounts(new_existing)

        try:
            cache_file = "token_cache.json"
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                for key in list(cache.keys()):
                    if key in related_uids:
                        del cache[key]
                    else:
                        entry = cache.get(key, {})
                        if str(entry.get("account_id", "")) in related_uids:
                            del cache[key]
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache, f, indent=2)
        except Exception:
            pass

        try:
            dev_file = "devices.json"
            if os.path.exists(dev_file):
                with open(dev_file, "r", encoding="utf-8") as f:
                    devices = json.load(f)
                for key in list(devices.keys()):
                    if key in related_uids:
                        del devices[key]
                with open(dev_file, "w", encoding="utf-8") as f:
                    json.dump(devices, f, indent=2)
        except Exception:
            pass

        for mapping in (bot_state.login_uid_to_account_id,
                        bot_state.account_id_to_login_uid,
                        bot_state.token_key_to_account_id,
                        bot_state.account_id_to_token_key):
            for key in list(mapping.keys()):
                if key in related_uids or mapping[key] in related_uids:
                    del mapping[key]

        for key in list(bot_state.account_owner.keys()):
            if key in related_uids:
                del bot_state.account_owner[key]

        for cid in related_uids:
            bot_state.close_writers_for_account(cid)

        bot_state.recalc_totals()
        bot_state.log(f"Account {check_uid} deleted ({cancelled_count} workers cancelled)", "success", check_uid)
        return web.json_response({"status": "ok", "cancelled": cancelled_count})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== BULK DELETE (10 at a time, wait for matches) ====================
async def _wait_for_account_matches_to_finish(uid: str, max_wait: float = BULK_DELETE_MATCH_WAIT) -> int:
    """Wait until account's active matches finish. Returns remaining match count."""
    related = bot_state.get_all_related_uids(uid)
    start = time.time()
    while time.time() - start < max_wait:
        total_active = 0
        for key in related:
            acc = bot_state.accounts.get(key)
            if acc:
                total_active += acc.get("active_matches", 0)
        if total_active <= 0:
            return 0
        await asyncio.sleep(2.0)
    total_active = 0
    for key in related:
        acc = bot_state.accounts.get(key)
        if acc:
            total_active += acc.get("active_matches", 0)
    return total_active


async def _hard_delete_account(uid: str, req_auth_uid: str = "") -> Dict[str, Any]:
    """
    Fully delete an account from every store:
    - Cancel workers
    - Close writers
    - Remove from accounts, credentials, mappings, owner, pause, uptime
    - Clean accounts.json, token_cache.json, devices.json
    """
    check_uid = uid or req_auth_uid
    related_uids = bot_state.get_all_related_uids(check_uid)
    if req_auth_uid:
        related_uids.add(req_auth_uid)

    cancelled_count = 0

    # 1. Cancel workers
    for key in list(bot_state.account_workers.keys()):
        if key in related_uids:
            task = bot_state.account_workers.get(key)
            if task and not task.done():
                task.cancel()
                cancelled_count += 1
            del bot_state.account_workers[key]

    # 2. Remove from in-memory accounts
    for key in list(bot_state.accounts.keys()):
        if key in related_uids:
            del bot_state.accounts[key]

    # 3. Remove credentials
    for key in list(bot_state.account_credentials.keys()):
        if key in related_uids:
            del bot_state.account_credentials[key]
            continue
        cred = bot_state.account_credentials.get(key)
        if cred and isinstance(cred, dict):
            if str(cred.get("account_id", "")) in related_uids:
                del bot_state.account_credentials[key]
            elif str(cred.get("auth_uid", "")) in related_uids:
                del bot_state.account_credentials[key]

    # 4. Clean accounts.json
    existing = _get_all_accounts_from_file()
    new_existing = []
    for acc in existing:
        acc_uid = str(acc.get("uid", "")).strip()
        acc_token = str(acc.get("token", "")).strip()
        if acc_uid in related_uids:
            continue
        if acc_token and f"tok_{acc_token[:20]}" in related_uids:
            continue
        new_existing.append(acc)
    _save_all_accounts(new_existing)

    # 5. Clean token_cache.json
    try:
        if os.path.exists("token_cache.json"):
            with open("token_cache.json", "r", encoding="utf-8") as f:
                cache = json.load(f)
            for key in list(cache.keys()):
                if key in related_uids:
                    del cache[key]
                else:
                    entry = cache.get(key, {})
                    if str(entry.get("account_id", "")) in related_uids:
                        del cache[key]
            with open("token_cache.json", "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
    except Exception:
        pass

    # 6. Clean devices.json
    try:
        if os.path.exists("devices.json"):
            with open("devices.json", "r", encoding="utf-8") as f:
                devices = json.load(f)
            for key in list(devices.keys()):
                if key in related_uids:
                    del devices[key]
            with open("devices.json", "w", encoding="utf-8") as f:
                json.dump(devices, f, indent=2)
    except Exception:
        pass

    # 7. Clean all UID mappings
    for mapping in (bot_state.login_uid_to_account_id,
                    bot_state.account_id_to_login_uid,
                    bot_state.token_key_to_account_id,
                    bot_state.account_id_to_token_key):
        for key in list(mapping.keys()):
            if key in related_uids or mapping[key] in related_uids:
                del mapping[key]

    # 8. Clean owner mapping
    for key in list(bot_state.account_owner.keys()):
        if key in related_uids:
            del bot_state.account_owner[key]

    # 9. Remove pause / uptime state
    for key in related_uids:
        bot_state.paused_accounts.discard(key)
        bot_state.account_pause_duration.pop(key, None)
        bot_state.account_paused_at.pop(key, None)
        bot_state.account_start_time.pop(key, None)
        bot_state.active_writers.pop(key, None)

    # 10. Close writers
    for cid in related_uids:
        bot_state.close_writers_for_account(cid)

    bot_state.recalc_totals()
    return {"deleted": check_uid, "cancelled": cancelled_count, "related": list(related_uids)}


async def bulk_delete_task(bulk_id: str, uids: List[str], username: str, is_admin: bool):
    """Background task: delete accounts in batches of 10, waiting for matches."""
    entry = bot_state.pending_bulk_delete.get(bulk_id)
    if not entry:
        return

    entry["status"] = "running"
    entry["total"] = len(uids)
    entry["deleted"] = 0
    entry["failed"] = 0
    entry["skipped"] = 0
    entry["results"] = []
    entry["current_batch"] = 0

    # Filter to only owned accounts (non-admin)
    if not is_admin:
        valid_uids = []
        for uid in uids:
            if _user_owns_account({"username": username, "role": "user"}, uid):
                valid_uids.append(uid)
            else:
                entry["results"].append({"uid": uid, "status": "skipped", "error": "Not yours"})
                entry["skipped"] += 1
        uids = valid_uids

    if not uids:
        entry["status"] = "done"
        return

    total_batches = (len(uids) + BULK_DELETE_BATCH_SIZE - 1) // BULK_DELETE_BATCH_SIZE
    bot_state.log(f"Bulk delete started for {username}: {len(uids)} accounts in {total_batches} batches", "warning")

    for batch_idx in range(total_batches):
        start = batch_idx * BULK_DELETE_BATCH_SIZE
        end = min(start + BULK_DELETE_BATCH_SIZE, len(uids))
        batch = uids[start:end]
        entry["current_batch"] = batch_idx + 1

        bot_state.log(f"Bulk delete batch {batch_idx + 1}/{total_batches}: {len(batch)} accounts", "info")

        # Phase 1: Pause all accounts in this batch to stop NEW matches
        for uid in batch:
            try:
                if not bot_state.is_paused(uid):
                    bot_state.toggle_pause(uid)
            except Exception:
                pass

        # Phase 2: Wait for each account's active matches to finish
        for uid in batch:
            try:
                remaining = await _wait_for_account_matches_to_finish(uid, max_wait=BULK_DELETE_MATCH_WAIT)
                if remaining > 0:
                    bot_state.log(
                        f"Bulk delete: {uid} still has {remaining} active matches (timeout, forcing delete)",
                        "warning"
                    )
            except Exception:
                pass

        # Phase 3: Hard delete each account
        for uid in batch:
            try:
                res = await _hard_delete_account(uid, "")
                entry["results"].append({
                    "uid": uid,
                    "status": "success",
                    "deleted": res["deleted"],
                    "cancelled": res["cancelled"],
                })
                entry["deleted"] += 1
            except Exception as e:
                entry["results"].append({"uid": uid, "status": "failed", "error": str(e)})
                entry["failed"] += 1

        # Small delay between batches
        if batch_idx < total_batches - 1:
            await asyncio.sleep(1.0)

    entry["status"] = "done"
    bot_state.log(
        f"Bulk delete done for {username}: {entry['deleted']} deleted, "
        f"{entry['failed']} failed, {entry['skipped']} skipped",
        "success"
    )


@_require_auth
async def handle_bulk_delete(request: web.Request) -> web.Response:
    """
    Bulk delete — deletes accounts in batches of 10.
    Payload: {"uids": ["uid1", "uid2", ...]}
    """
    try:
        data = await request.json()
        user = request["user"]
        username = user["username"]
        is_admin = user.get("role") == "admin"

        uids = data.get("uids", [])
        if not isinstance(uids, list) or not uids:
            return web.json_response({"error": "uids list required"}, status=400)

        # Normalize
        cleaned = []
        seen = set()
        for u in uids:
            s = str(u).strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)

        if not cleaned:
            return web.json_response({"error": "No valid uids"}, status=400)

        if len(cleaned) > MAX_BULK_SIZE:
            cleaned = cleaned[:MAX_BULK_SIZE]

        bulk_id = secrets.token_urlsafe(16)
        bot_state.pending_bulk_delete[bulk_id] = {
            "username": username,
            "total": len(cleaned),
            "created_at": time.time(),
            "status": "starting",
            "deleted": 0,
            "failed": 0,
            "skipped": 0,
            "results": [],
            "current_batch": 0,
        }

        asyncio.create_task(bulk_delete_task(bulk_id, cleaned, username, is_admin))

        return web.json_response({
            "status": "running",
            "bulk_id": bulk_id,
            "total": len(cleaned),
            "batch_size": BULK_DELETE_BATCH_SIZE,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_auth
async def handle_bulk_delete_status(request: web.Request) -> web.Response:
    try:
        bulk_id = request.query.get("bulk_id", "")
        if not bulk_id:
            return web.json_response({"error": "bulk_id required"}, status=400)

        entry = bot_state.pending_bulk_delete.get(bulk_id)
        if not entry:
            return web.json_response({"error": "Unknown bulk_id"}, status=404)

        user = request["user"]
        if user.get("role") != "admin" and entry.get("username") != user["username"]:
            return web.json_response({"error": "Not yours"}, status=403)

        return web.json_response({
            "status": entry["status"],
            "total": entry.get("total", 0),
            "deleted": entry.get("deleted", 0),
            "failed": entry.get("failed", 0),
            "skipped": entry.get("skipped", 0),
            "current_batch": entry.get("current_batch", 0),
            "batch_size": BULK_DELETE_BATCH_SIZE,
            "results": entry.get("results", []),
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== REFRESH (SINGLE + GLOBAL) ====================
@_require_auth
async def handle_refresh_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"error": "UID required"}, status=400)

        user = request["user"]
        if not _user_owns_account(user, uid):
            return web.json_response({"error": "Not your account"}, status=403)

        if "on_refresh_account" not in bot_state.refresh_callbacks:
            return web.json_response({"error": "Refresher not ready"}, status=500)

        result = await bot_state.refresh_callbacks["on_refresh_account"](uid)
        if result and result.get("error"):
            return web.json_response({"status": "error", "error": result["error"]}, status=500)
        return web.json_response({"status": "ok", "data": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_auth
async def handle_refresh_all(request: web.Request) -> web.Response:
    try:
        user = request["user"]
        username = user["username"]
        is_admin = user.get("role") == "admin"

        if "on_refresh_account" not in bot_state.refresh_callbacks:
            return web.json_response({"error": "Refresher not ready"}, status=500)

        if is_admin:
            uids_to_refresh = list(bot_state.accounts.keys())
        else:
            own_accounts = _get_user_accounts_from_file(username)
            uids_to_refresh = []
            for a in own_accounts:
                if a.get("uid"):
                    uids_to_refresh.append(str(a["uid"]))
                elif a.get("token"):
                    uids_to_refresh.append(f"tok_{a['token'][:20]}")

        if not uids_to_refresh:
            return web.json_response({"status": "ok", "total": 0, "success": 0, "failed": 0, "results": []})

        bot_state.log(f"Global refresh started for {username} ({len(uids_to_refresh)} accounts)", "info")

        sem = asyncio.Semaphore(MAX_CONCURRENT_REFRESHES)

        async def _refresh_one(uid: str):
            async with sem:
                try:
                    res = await bot_state.refresh_callbacks["on_refresh_account"](uid)
                    return {"uid": uid, "ok": not (res and res.get("error")), "data": res}
                except Exception as e:
                    return {"uid": uid, "ok": False, "error": str(e)}

        tasks = [asyncio.create_task(_refresh_one(uid)) for uid in uids_to_refresh]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        success = sum(1 for r in results if r.get("ok"))
        failed = len(results) - success

        bot_state.log(f"Global refresh done for {username}: {success} ok, {failed} failed", "success")

        return web.json_response({
            "status": "ok",
            "total": len(results),
            "success": success,
            "failed": failed,
            "results": results
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== START / STOP ACCOUNT ====================
@_require_auth
async def handle_start_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"error": "UID required"}, status=400)

        user = request["user"]
        if not _user_owns_account(user, uid):
            return web.json_response({"error": "Not your account"}, status=403)

        bot_state.log(f"Starting account {uid}...", "info", uid)
        related = bot_state.get_all_related_uids(uid)

        for key in related:
            task = bot_state.account_workers.get(key)
            if task and not task.done():
                return web.json_response({"error": "Already running"}, status=400)

        account_entry = None
        existing = _get_all_accounts_from_file()
        for acc in existing:
            acc_uid = str(acc.get("uid", "")).strip()
            acc_tok = str(acc.get("token", "")).strip()
            if acc_uid == uid or acc_uid in related:
                account_entry = acc
                break
            if acc_tok and f"tok_{acc_tok[:20]}" in related:
                account_entry = acc
                break

        if not account_entry:
            return web.json_response({"error": "Account not found in accounts.json"}, status=404)

        if bot_state.is_paused(uid):
            bot_state.toggle_pause(uid)

        if "on_account_added" in bot_state.refresh_callbacks:
            if account_entry.get("uid") and account_entry.get("password"):
                payload = {"uid": account_entry["uid"], "password": account_entry["password"]}
            elif account_entry.get("token"):
                payload = {"token": account_entry["token"]}
            else:
                return web.json_response({"error": "Invalid account entry"}, status=400)
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](payload))

        for key in related:
            if key in bot_state.accounts:
                bot_state.accounts[key]["status"] = "CONNECTING"

        bot_state.log(f"Account {uid} start requested", "success", uid)
        return web.json_response({"status": "ok", "message": "Account starting..."})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_auth
async def handle_stop_account(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"error": "UID required"}, status=400)

        user = request["user"]
        if not _user_owns_account(user, uid):
            return web.json_response({"error": "Not your account"}, status=403)

        bot_state.log(f"Stopping account {uid}...", "warning", uid)
        related = bot_state.get_all_related_uids(uid)
        cancelled_count = 0

        for key in list(bot_state.account_workers.keys()):
            if key in related:
                task = bot_state.account_workers.get(key)
                if task and not task.done():
                    task.cancel()
                    cancelled_count += 1
                del bot_state.account_workers[key]

        for key in related:
            if key in bot_state.accounts:
                bot_state.accounts[key]["status"] = "STOPPED"
                bot_state.accounts[key]["active_matches"] = 0

        bot_state.log(f"Account {uid} stopped ({cancelled_count} workers cancelled)", "success", uid)
        return web.json_response({"status": "ok", "cancelled": cancelled_count})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== PAUSE / RESUME ====================
@_require_auth
async def handle_toggle_pause(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"error": "UID required"}, status=400)

        user = request["user"]
        if not _user_owns_account(user, uid):
            return web.json_response({"error": "Not your account"}, status=403)

        is_paused = bot_state.toggle_pause(uid)
        return web.json_response({"status": "ok", "is_paused": is_paused})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_auth
async def handle_toggle_pause_all(request: web.Request) -> web.Response:
    try:
        user = request["user"]
        is_admin = user.get("role") == "admin"
        username = user["username"]

        if is_admin:
            paused_state = bot_state.toggle_pause_all()
        else:
            own_accounts = _get_user_accounts_from_file(username)
            own_uids = set()
            for a in own_accounts:
                if a.get("uid"):
                    own_uids.add(str(a["uid"]))
                elif a.get("token"):
                    own_uids.add(f"tok_{a['token'][:20]}")

            any_active = any(not bot_state.is_paused(u) for u in own_uids)
            for u in own_uids:
                current_paused = bot_state.is_paused(u)
                if any_active and not current_paused:
                    bot_state.toggle_pause(u)
                elif not any_active and current_paused:
                    bot_state.toggle_pause(u)
            paused_state = any_active

        return web.json_response({"status": "ok", "all_paused": paused_state})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== ADMIN HANDLERS ====================
@_require_admin
async def handle_admin_list_users(request: web.Request) -> web.Response:
    users = _load_users()
    user_list = []
    for username, u in users.items():
        expiry_hours = None
        if u.get("expires_at"):
            remaining = u["expires_at"] - time.time()
            expiry_hours = max(0, round(remaining / 3600, 1))
        user_list.append({
            "username": username,
            "role": u.get("role", "user"),
            "max_slots": u.get("max_slots", 1),
            "active_jobs": u.get("active_jobs", 0),
            "created_at": u.get("created_at"),
            "expires_at": u.get("expires_at"),
            "expiry_hours": expiry_hours
        })
    user_list.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return web.json_response({"users": user_list})


@_require_admin
async def handle_admin_create_user(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        max_slots = int(data.get("max_slots", 1))
        duration_days = int(data.get("duration_days", 30))

        if not username or not password:
            return web.json_response({"error": "Username and password required"}, status=400)
        if len(password) < 6:
            return web.json_response({"error": "Password must be at least 6 chars"}, status=400)

        users = _load_users()
        if username in users:
            return web.json_response({"error": "Username already exists"}, status=400)

        users[username] = {
            "username": username,
            "password_hash": _hash_password(password),
            "role": "user",
            "max_slots": max(1, max_slots),
            "active_jobs": 0,
            "created_at": time.time(),
            "expires_at": time.time() + (duration_days * 86400)
        }
        _save_users(users)
        bot_state.log(f"Admin created user '{username}' ({max_slots} slots, {duration_days}d)", "success")
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_admin
async def handle_admin_delete_user(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        current = request["user"]["username"]
        if username == current:
            return web.json_response({"error": "Cannot delete yourself"}, status=400)

        users = _load_users()
        if username not in users:
            return web.json_response({"error": "User not found"}, status=404)

        del users[username]
        _save_users(users)
        bot_state.log(f"Admin deleted user '{username}'", "warning")
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_admin
async def handle_admin_extend_user(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        days = int(data.get("days", 30))

        users = _load_users()
        if username not in users:
            return web.json_response({"error": "User not found"}, status=404)

        u = users[username]
        current_expiry = u.get("expires_at") or time.time()
        if current_expiry < time.time():
            current_expiry = time.time()
        u["expires_at"] = current_expiry + (days * 86400)
        _save_users(users)
        bot_state.log(f"Admin extended '{username}' by {days} days", "success")
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_admin
async def handle_admin_reset_password(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        new_pass = str(data.get("new_password", ""))
        if len(new_pass) < 6:
            return web.json_response({"error": "Password must be at least 6 chars"}, status=400)

        users = _load_users()
        if username not in users:
            return web.json_response({"error": "User not found"}, status=404)

        users[username]["password_hash"] = _hash_password(new_pass)
        _save_users(users)
        bot_state.log(f"Admin reset password for '{username}'", "warning")
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@_require_admin
async def handle_admin_set_slots(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        username = str(data.get("username", "")).strip()
        new_slots = int(data.get("max_slots", 1))

        users = _load_users()
        if username not in users:
            return web.json_response({"error": "User not found"}, status=404)

        users[username]["max_slots"] = max(1, new_slots)
        _save_users(users)
        bot_state.log(f"Admin set '{username}' slots to {new_slots}", "success")
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ==================== INDEX ====================
TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "templates",
    "index.html"
)


async def handle_index(request: web.Request) -> web.Response:
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "<h1>templates/index.html not found!</h1>"
    return web.Response(text=content, content_type="text/html", charset="utf-8")


# ==================== START SERVER ====================
async def start_web_dashboard(host: str = "0.0.0.0", port: int = 5000):
    app = web.Application()

    app.router.add_get("/", handle_index)

    # Auth
    app.router.add_post("/api/auth/login", handle_login)
    app.router.add_post("/api/auth/logout", handle_logout)
    app.router.add_get("/api/auth/me", handle_me)
    app.router.add_post("/api/auth/change-password", handle_change_password)

    # Stats
    app.router.add_get("/api/stats", handle_get_stats)

    # Accounts
    app.router.add_post("/api/account/add", handle_add_account)
    app.router.add_get("/api/account/verify-status", handle_verify_status)
    app.router.add_post("/api/account/bulk-add", handle_bulk_add)
    app.router.add_get("/api/account/bulk-verify-status", handle_bulk_verify_status)
    app.router.add_post("/api/account/delete", handle_delete_account)
    app.router.add_post("/api/account/bulk-delete", handle_bulk_delete)
    app.router.add_get("/api/account/bulk-delete-status", handle_bulk_delete_status)
    app.router.add_post("/api/account/refresh", handle_refresh_account)
    app.router.add_post("/api/account/refresh-all", handle_refresh_all)
    app.router.add_post("/api/account/start", handle_start_account)
    app.router.add_post("/api/account/stop", handle_stop_account)
    app.router.add_post("/api/account/pause", handle_toggle_pause)
    app.router.add_post("/api/account/pause_all", handle_toggle_pause_all)

    # Admin
    app.router.add_get("/api/admin/users", handle_admin_list_users)
    app.router.add_post("/api/admin/user/create", handle_admin_create_user)
    app.router.add_post("/api/admin/user/delete", handle_admin_delete_user)
    app.router.add_post("/api/admin/user/extend", handle_admin_extend_user)
    app.router.add_post("/api/admin/user/reset-password", handle_admin_reset_password)
    app.router.add_post("/api/admin/user/set-slots", handle_admin_set_slots)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    _load_users()

    print(f"\033[92m[+] BR Dashboard running on http://localhost:{port}\033[0m")
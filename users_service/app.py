# users_service/app.py
""" This part of the project exposes the HTTP endpoints for the users service. It takes care of  all direct database work to :mod:`database`  
focuses on validation and shaping  the JSON responses. """
import os
from datetime import datetime, timedelta
import logging
from flask_talisman import Talisman

import jwt
from flask import Flask, jsonify, request, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import time  

# ── Authentication config ────────────────────────────────────────────────
AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-change-me")
TOKEN_EXP_MINUTES = 60  # 1 hour tokens

def get_current_user():
    """
    read current user identity, preferring a Bearer token, falling back to headers.

    Priority:
    1) Authorization: Bearer <JWT>  → decode, return (username, role)
    2) Legacy headers X-User-Name / X-User-Role  → used by existing tests
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=["HS256"])
            return payload.get("username"), payload.get("role")
        except jwt.ExpiredSignatureError:
            # Token expired → treated as unauthenticated
            return None, None
        except jwt.InvalidTokenError:
            # Any other token error → unauthenticated
            return None, None


    username = request.headers.get("X-User-Name")
    role = request.headers.get("X-User-Role")
    return username, role

def generate_auth_token(user_row):
    """
    Create a JWT token containing username + role with an expiration time.
    """
    payload = {
        "username": user_row["username"],
        "role": user_row["role"],
        "exp": datetime.utcnow() + timedelta(minutes=TOKEN_EXP_MINUTES),
    }
    token = jwt.encode(payload, AUTH_SECRET_KEY, algorithm="HS256")
    # PyJWT may return bytes or str depending on version
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def require_roles(*allowed_roles):
    """
    Decorator to ensure the current user has one of the allowed roles.
    Returns 401 if role missing, 403 if role not allowed.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            username, role = get_current_user()
            if role is None:
                return jsonify({"error": "missing X-User-Role header"}), 401
            if role not in allowed_roles:
                return (
                    jsonify(
                        {
                            "error": "forbidden: requires one of roles: "
                            + ", ".join(allowed_roles)
                        }
                    ),
                    403,
                )
            return view_func(*args, **kwargs)
        return wrapped
    return decorator

# This import style works both when running directly and when Sphinx imports the package
try:
    # Import when used as a package: users_service.app
    from users_service.database import (
        make_users_table_if_missing,
        insert_user,
        find_user_by_username,
        find_user_by_email,
        list_all_users,
        update_user_row,
        delete_user_row,
    )
except ImportError:
    # Import when running from inside users_service/ with: python app.py
    from database import (
        make_users_table_if_missing,
        insert_user,
        find_user_by_username,
        find_user_by_email,
        list_all_users,
        update_user_row,
        delete_user_row,
    )

USER_CACHE_TTL = 30.0  # seconds
_user_cache = {}       # username -> (data_without_hash, expires_at)


def get_cached_user(username):
    """Return sanitized user dict from cache or DB."""
    now = time.time()
    entry = _user_cache.get(username)
    if entry is not None:
        data, expires_at = entry
        if expires_at > now:
            return data
        # expired -> drop it
        _user_cache.pop(username, None)

    user_row = find_user_by_username(username)
    if not user_row:
        return None

    user_dict = dict(user_row)
    user_dict.pop("password_hash", None)
    _user_cache[username] = (user_dict, now + USER_CACHE_TTL)
    return user_dict


def invalidate_user_cache(username=None):
    """Clear cache for one user or for all users."""
    if username is None:
        _user_cache.clear()
    else:
        _user_cache.pop(username, None)

app = Flask(__name__)
Talisman(app, content_security_policy=None,force_https=False)

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("users_service")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "users_service.log"))
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
@app.before_request
def audit_request():
    try:
        username, role = get_current_user()
    except Exception:
        username, role = None, None

    g.audit_username = username or "anonymous"
    g.audit_role = role or "none"

    logger.info(
        "REQUEST method=%s path=%s user=%s role=%s remote_addr=%s",
        request.method,
        request.path,
        g.audit_username,
        g.audit_role,
        request.remote_addr,
    )


@app.after_request
def audit_response(response):
    username = getattr(g, "audit_username", "anonymous")
    role = getattr(g, "audit_role", "none")
    level = logging.INFO if response.status_code < 400 else logging.WARNING

    logger.log(
        level,
        "RESPONSE method=%s path=%s status=%s user=%s role=%s",
        request.method,
        request.path,
        response.status_code,
        username,
        role,
    )
    return response

@app.route("/users/register", methods=["POST"])
def register_user():
    """ handkes user registration, this endpoint  expects a JSON body with
      "name", "username", "email", "password", and "role" fields. if everything looks good, 
        a new user is inserted into daatabase and  returned ofcourse without password hash.
          returns a JSON response with appropriate status code meaning 4xx/5xx if error  and if user created then status 201."""
    data = request.get_json() or {}
    needed = ["name", "username", "email", "password", "role"]
    missing = [x for x in needed if not data.get(x)]
    if missing:
        return jsonify({"error": f"missing: {', '.join(missing)}"}), 400

    name = data["name"]
    username = data["username"]
    email = data["email"]
    role = data["role"]
    raw_pass = data["password"]

    if find_user_by_username(username):
        return jsonify({"error": "username already used"}), 400

    if find_user_by_email(email):
        return jsonify({"error": "email already used"}), 400

    hashed_pass = generate_password_hash(raw_pass)
    created = insert_user(name, username, email, role, hashed_pass)

    if not created:
        return jsonify({"error": "could not create user"}), 500

    # never send hash back
    created.pop("password_hash", None)
    invalidate_user_cache(created["username"])  # <-- NEW (optional but ok)
    return jsonify({"message": "user registered", "user": created}), 201


@app.route("/users/login", methods=["POST"])
def login_user():
    """User login.

    Expects JSON:
    {
      "username": "...",
      "password": "..."
    }

    If credentials are correct:
    - returns a JWT token in the "token" field
    - returns user info (without password hash)
    """
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user_row = find_user_by_username(username)
    if not user_row:
        return jsonify({"message": "invalid username or password"}), 401

    stored_hash = user_row.get("password_hash")
    if not check_password_hash(stored_hash, password):
        return jsonify({"message": "invalid username or password"}), 401

   
    token = generate_auth_token(user_row)
    user_copy = dict(user_row)
    user_copy.pop("password_hash", None)

    return (
        jsonify(
            {
                "message": "login successful",
                "token": token,
                "user": user_copy,
            }
        ),
        200,
    )



@app.route("/users", methods=["GET"])
@require_roles("admin", "auditor")
def get_all_users():
    """ retrieves all users from database, removes password hashes before returning.
    returns JSON list of user objects. """
    all_people = list_all_users()
    for u in all_people:
        u.pop("password_hash", None)
    return jsonify(all_people), 200



@app.route("/users/<string:username>", methods=["GET"])
def get_user_by_username_route(username):
    current_username, role = get_current_user()
    if role is None:
        return jsonify({"error": "missing X-User-Role header"}), 401
    # admin/auditor can see anyone; others only themselves
    if role not in ("admin", "auditor") and current_username != username:
        return jsonify(
            {"error": "forbidden: you can only view your own user profile"}
        ), 403

    """ retrieves a single user by username, removes password hash before returning.
    returns JSON user object if found with user data, 404 if not found if user doesn't even exist. """
    user_data = get_cached_user(username)  # <-- NEW
    if not user_data:
        return jsonify({"error": "user not found"}), 404

    return jsonify(user_data), 200


@app.route("/users/<string:username>", methods=["PUT"])
def update_user(username):
    current_username, role = get_current_user()
    if role is None:
        return jsonify({"error": "missing X-User-Role header"}), 401
    # admin can update anybody; others only themselves
    if role != "admin" and current_username != username:
        return jsonify(
            {"error": "forbidden: you can only update your own user"}
        ), 403

    """ updates user profile info. 
    Expects JSON body with optional fields: name, email,role , password.(optional; if present, the password is updated)
    not provided fields remain unchanged.
    returns  JSON wiht updated  user or an error message.
    """
    data = request.get_json() or {}

    existing = find_user_by_username(username)
    if not existing:
        return jsonify({"error": "user not found"}), 404

    new_name = data.get("name", existing["name"])
    new_email = data.get("email", existing["email"])
    new_role = data.get("role", existing["role"])

    new_hash = None
    if data.get("password"):
        new_hash = generate_password_hash(data["password"])

    updated = update_user_row(username, new_name, new_email, new_role, new_hash)
    if not updated:
        return jsonify({"error": "could not update user"}), 500

    updated.pop("password_hash", None)
    invalidate_user_cache(username)  # <-- NEW
    return jsonify({"message": "user updated", "user": updated}), 200


@app.route("/users/<string:username>", methods=["DELETE"])
def delete_user(username):
    current_username, role = get_current_user()
    if role is None:
        return jsonify({"error": "missing X-User-Role header"}), 401
    if role != "admin":
        return jsonify(
            {"error": "forbidden: only admin can delete users"}
        ), 403
    """ deletes a user by username as  parameter.
    returns Json with short confirmation message if deleted, 404 if user not found."""
    existing = find_user_by_username(username)
    if not existing:
        return jsonify({"error": "user not found"}), 404

    rows_deleted = delete_user_row(username)
    if rows_deleted == 0:
        return jsonify({"error": "nothing deleted"}), 500

    invalidate_user_cache(username)  # <-- NEW

    return jsonify({"message": f"user {username} deleted"}), 200


@app.route("/users/<string:username>/bookings", methods=["GET"])
def get_user_bookings(username):
    current_username, role = get_current_user()
    if role is None:
        return jsonify({"error": "missing X-User-Role header"}), 401
    # admin/facility_manager can view anyone; regular only themselves
    if role not in ("admin", "facility_manager") and current_username != username:
        return jsonify(
            {"error": "forbidden: you can only view your own bookings"}
        ), 403

    """ reuturns a user's bookings history. this only checks that  user exists and returns empty
    list of bookings for now. it takes  username as parameters and returns json with  user data and a bookings list."""
    existing = find_user_by_username(username)
    if not existing:
        return jsonify({"error": "user not found"}), 404

    existing.pop("password_hash", None)

    # placeholder for now; later you can talk to bookings service
    fake_bookings_list = []

    return jsonify({"user": existing, "bookings": fake_bookings_list}), 200


if __name__ == "__main__":
    make_users_table_if_missing()
    port = int(os.environ.get("USERS_SERVICE_PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)

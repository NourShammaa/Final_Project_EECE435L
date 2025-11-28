"""This part of the project iis just the HTTP endpoints for the rooms service. it is for managing meeting rooms:
creating, updating, deleting, listing, and checking availability.
"""
import os
import logging
from flask_talisman import Talisman
import jwt
from flask import Flask, jsonify, request, g
from functools import wraps
import time   # <-- NEW

AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-change-me")

# --- Simple in-memory cache for rooms (NEW) ------------------------------
ROOMS_CACHE_TTL = 30.0  # seconds

_all_rooms_cache = {"data": None, "expires_at": 0.0}
_available_rooms_cache = {}  # key -> (data, expires_at)

def get_current_user():
    """Read current user identity, preferring Bearer token, then X-User-* headers."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=["HS256"])
            return payload.get("username"), payload.get("role")
        except jwt.ExpiredSignatureError:
            return None, None
        except jwt.InvalidTokenError:
            return None, None

    username = request.headers.get("X-User-Name")
    role = request.headers.get("X-User-Role")
    return username, role


def require_roles(*allowed_roles):
    """Decorator to enforce that current user has one of the allowed roles."""
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

try:
    from room_service.database import (
        make_rooms_table_if_missing,
        insert_room,
        find_room_by_name,
        list_all_rooms,
        update_room_row,
        delete_room_row,
        search_available_rooms,  
    )
except ImportError:
    from database import (
        make_rooms_table_if_missing,
        insert_room,
        find_room_by_name,
        list_all_rooms,
        update_room_row,
        delete_room_row,
        search_available_rooms, 
    )


# --- Caching helpers (NEW) -----------------------------------------------
def _availability_cache_key(min_capacity, location, equipment_contains):
    """Turn query parameters into a deterministic cache key."""
    return f"{min_capacity}|{location}|{equipment_contains}"


def get_cached_all_rooms():
    """Return cached list of all rooms, or refresh cache if expired."""
    now = time.time()
    if (
        _all_rooms_cache["data"] is not None
        and _all_rooms_cache["expires_at"] > now
    ):
        return _all_rooms_cache["data"]

    data = list_all_rooms()
    _all_rooms_cache["data"] = data
    _all_rooms_cache["expires_at"] = now + ROOMS_CACHE_TTL
    return data


def get_cached_available_rooms(min_capacity=None, location=None, equipment_contains=None):
    """Return cached search results for /rooms/available."""
    key = _availability_cache_key(min_capacity, location, equipment_contains)
    now = time.time()
    entry = _available_rooms_cache.get(key)

    if entry is not None:
        data, expires_at = entry
        if expires_at > now:
            return data

    data = search_available_rooms(
        min_capacity=min_capacity,
        location=location,
        equipment_contains=equipment_contains,
    )
    _available_rooms_cache[key] = (data, now + ROOMS_CACHE_TTL)
    return data


def invalidate_rooms_cache():
    """Clear cache after any change to rooms."""
    _all_rooms_cache["data"] = None
    _all_rooms_cache["expires_at"] = 0.0
    _available_rooms_cache.clear()


app = Flask(__name__)
Talisman(app, content_security_policy=None,force_https=False)

# ── Auditing / Logging setup ─────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("room_service")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "room_service.log"))
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
# ── Auditing hooks ───────────────────────────────────────────────────────
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


@app.route("/rooms", methods=["POST"])
@require_roles("admin", "facility_manager")
def create_room():
    """create a new meeting room.
    takes in a JSON body with name, capacity, equipment, location, and optional status( "available" or "booked", defaults to "available").
    returns JSON response with appropriate status code meaning 4xx/5xx if error, 201 if room created.
    """
    data = request.get_json() or {}

    needed = ["name", "capacity", "equipment", "location"]
    missing = [x for x in needed if not data.get(x)]
    if missing:
        return jsonify({"error": f"missing: {', '.join(missing)}"}), 400

    name = data["name"]
    if find_room_by_name(name):
        return jsonify({"error": "room name already exists"}), 400

    try:
        capacity = int(data["capacity"])
    except (TypeError, ValueError):
        return jsonify({"error": "capacity must be an integer"}), 400

    equipment = data["equipment"]
    location = data["location"]
    status = data.get("status", "available")

    created = insert_room(name, capacity, equipment, location, status)
    if not created:
        return jsonify({"error": "could not create room"}), 500

    invalidate_rooms_cache()  # <-- NEW

    return jsonify({"message": "room created", "room": created}), 201


@app.route("/rooms", methods=["GET"])
def get_all_rooms():
    """return all rooms in the system as a JSON list (with simple caching)."""
    all_rooms = get_cached_all_rooms()          # <-- uses cache
    return jsonify(all_rooms), 200


@app.route("/rooms/available", methods=["GET"])
def get_available_rooms():
    """returns available rooms, optionally filtered by capacity, location, equipment."""
    min_capacity = request.args.get("min_capacity")
    location = request.args.get("location")
    equipment_contains = request.args.get("equipment_contains")

    if min_capacity is not None:
        try:
            min_capacity = int(min_capacity)
        except ValueError:
            return jsonify({"error": "min_capacity must be an integer"}), 400

    rooms = get_cached_available_rooms(       # <-- uses cache
        min_capacity=min_capacity,
        location=location,
        equipment_contains=equipment_contains,
    )
    return jsonify(rooms), 200


@app.route("/rooms/<string:name>", methods=["GET"])
def get_room(name):
    """just returns a single room by name."""
    room = find_room_by_name(name)
    if not room:
        return jsonify({"error": "room not found"}), 404
    return jsonify(room), 200


@app.route("/rooms/<string:name>", methods=["PUT"])
@require_roles("admin", "facility_manager")
def update_room(name):
    """update room details or status.
    accepts a JSON body with capacity, equipment, location, and/or status fields to update.
    returns JSON response with appropriate status code 4xx/5xx if error, 200 if room updated.
    """
    data = request.get_json() or {}

    existing = find_room_by_name(name)
    if not existing:
        return jsonify({"error": "room not found"}), 404

    if "capacity" in data:
        try:
            new_capacity = int(data["capacity"])
        except (TypeError, ValueError):
            return jsonify({"error": "capacity must be an integer"}), 400
    else:
        new_capacity = existing["capacity"]

    new_equipment = data.get("equipment", existing["equipment"])
    new_location = data.get("location", existing["location"])
    new_status = data.get("status", existing["status"])

    updated = update_room_row(
        name, new_capacity, new_equipment, new_location, new_status
    )
    if not updated:
        return jsonify({"error": "could not update room"}), 500

    invalidate_rooms_cache()  # <-- NEW

    return jsonify({"message": "room updated", "room": updated}), 200


@app.route("/rooms/<string:name>", methods=["DELETE"])
@require_roles("admin", "facility_manager")
def delete_room(name):
    """delete room by name."""
    existing = find_room_by_name(name)
    if not existing:
        return jsonify({"error": "room not found"}), 404

    rows_deleted = delete_room_row(name)
    if rows_deleted == 0:
        return jsonify({"error": "nothing deleted"}), 500

    invalidate_rooms_cache()  # <-- NEW

    return jsonify({"message": f"room {name} deleted"}), 200


@app.route("/rooms/<string:name>/status", methods=["GET"])
def get_room_status(name):
    """basically return the status of a room: available or booked."""
    room = find_room_by_name(name)
    if not room:
        return jsonify({"error": "room not found"}), 404

    return jsonify({"name": room["name"], "status": room["status"]}), 200


if __name__ == "__main__":
    make_rooms_table_if_missing()
    port = int(os.environ.get("ROOM_SERVICE_PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)
 

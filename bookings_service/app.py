# bookings_service/app.py
"""
This is the file that handles all API routes for bookings.
It calls database fcts from database.py that is in same folder. It focuses on
input validation, checking room availability, and shaping JSON responses.
"""
import os
import logging
from flask_talisman import Talisman

import jwt
from flask import Flask, jsonify, request, g
from functools import wraps

AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-change-me")


# Support both import styles: package import (for Sphinx) and direct run (avoiding error)
try:
    from bookings_service.database import (
        make_bookings_table_if_missing,
        get_all_bookings,
        create_booking,
        update_booking,
        cancel_booking,
        get_bookings_for_user,
        is_room_available,
        get_booking_by_id,
        find_user_by_id,
        find_room_by_id,

    )
except ImportError:
    from database import (
        make_bookings_table_if_missing,
        get_all_bookings,
        create_booking,
        update_booking,
        cancel_booking,
        get_bookings_for_user,
        is_room_available,
        get_booking_by_id,
        find_user_by_id,
        find_room_by_id,

    )

app = Flask(__name__)
Talisman(app, content_security_policy=None)

# ── Auditing / Logging setup ─────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("bookings_service")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "bookings_service.log"))
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def get_current_user():
    """Decode user from token, fallback to X-User-* headers."""
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


def require_roles(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            username, role = get_current_user()
            if role is None:
                return jsonify({"error": "missing X-User-Role header"}), 401
            if role not in allowed_roles:
                return jsonify({
                    "error": f"forbidden: requires one of roles: {', '.join(allowed_roles)}"
                }), 403
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


# Helpers

def require_fields(data, fields):
    """This fct checks that all required fields exist in the input JSON.

    Parameters
    data : dict
        The parsed request body.
    fields : list of str
        The list of fields that must be present.

    Returns
    str or None
        A message listing missing fields, or None if all are there.
    """
    missing = []

    for f in fields:
        if not data.get(f):
            missing.append(f)

    if missing:
        return f"missing: {', '.join(missing)}"
    return None


def valid_time(t):
    """This fct does a simple HH:MM validation to check if a time is well-formatted.

    Parameters
    t : str
        A time string in the form HH:MM.

    Returns
    bool
        True if valid, False otherwise.
    """
    if len(t) != 5 or t[2] != ":":
        return False
    hh, mm = t.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


def valid_date(d):
    """This fct performs a basic YYYY-MM-DD validation.

    Parameters
    d : str
        A date string in the form YYYY-MM-DD.

    Returns
    bool
        True if valid, False otherwise.
    """
    if len(d) != 10 or d[4] != "-" or d[7] != "-":
        return False

    yyyy, mm, dd = d.split("-")

    if not (yyyy.isdigit() and mm.isdigit() and dd.isdigit()):
        return False

    year = int(yyyy)
    month = int(mm)
    day = int(dd)

    return 1 <= month <= 12 and 1 <= day <= 31


# Routes

@app.route("/bookings", methods=["GET"])
@require_roles("admin", "facility_manager", "auditor")
def list_all_bookings():
    """This fct returns all bookings in the system.

    It gets all the bookings from the db, converts each row to a dict, and returns them as JSON.

    Returns
    tuple
        A list of bookings and status code 200.
    """
    rows = get_all_bookings()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/bookings/user/<int:user_id>", methods=["GET"])
@require_roles("admin", "facility_manager", "auditor", "regular")
def get_bookings_for_user_route(user_id):
    """This fct returns all bookings that were made by a specific user.

    Cancelled bookings are included too btw.

    Parameters
    user_id : int
        The user whose bookings are requested.

    Returns
    tuple
        Either a list of bookings and status 200,
        or a 404 if the user does not exist.
    """

    # get current identity from headers
    current_username, role = get_current_user()

    # first check that the target user exists
    user_row = find_user_by_id(user_id)
    if not user_row:
        return jsonify({"error": "user not found"}), 404

    target_username = user_row["username"]

    # ownership rule:
    # - admin, facility_manager, auditor: can view anyone
    # - regular: can only view themselves
    if role == "regular" and current_username != target_username:
        return jsonify({
            "error": "forbidden: you can only view your own bookings"
        }), 403

    rows = get_bookings_for_user(user_id)
    return jsonify([dict(r) for r in rows]), 200


@app.route("/bookings", methods=["POST"])
@require_roles("admin", "regular", "facility_manager")
def make_booking_route():
    """This fct handles the creation of a new booking.

    Expected JSON
    user_id : int
        The user making the booking.
    room_id : int
        The room being booked.
    date : str
        Booking date in YYYY-MM-DD format.
    start_time : str
        Start time in HH:MM format.
    end_time : str
        End time in HH:MM format.

    Returns
    tuple
        A confirmation message and status code.
    """
    data = request.get_json() or {}

    #  RBAC  
    current_username, role = get_current_user()

    # If regular user, they can only create a booking for themself
    if role == "regular":
        user_row = find_user_by_id(data.get("user_id"))
        if not user_row:
            return jsonify({"error": "user not found"}), 404

        # user_row["username"] is the owner of the booking
        if user_row["username"] != current_username:
            return jsonify(
                {"error": "forbidden: you can only create bookings for yourself"}), 403
   

    needed = ["user_id", "room_id", "date", "start_time", "end_time"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    # validate time format
    if not valid_time(data["start_time"]) or not valid_time(data["end_time"]):
        return jsonify({"error": "invalid time format HH:MM"}), 400

    if not valid_date(data["date"]):
        return jsonify({"error": "invalid date format YYYY-MM-DD"}), 400

    if data["end_time"] <= data["start_time"]:
        return jsonify({"error": "end_time must be after start_time"}), 400
    

    # check room exists
    if not find_room_by_id(data["room_id"]):
        return jsonify({"error": "room not found"}), 404

    # check availability
    ok = is_room_available(
        data["room_id"],
        data["date"],
        data["start_time"],
        data["end_time"],
    )
    if not ok:
        return jsonify({
            "error": "Unfortunately =(, the room is not available for this time slot. "
                     "Either choose another room or another time."
        }), 409

    booking_id = create_booking(
        data["user_id"],
        data["room_id"],
        data["date"],
        data["start_time"],
        data["end_time"],
    )

    if not booking_id:
        return jsonify({"error": "could not create booking"}), 500

    return jsonify({"message": "booking created", "booking_id": booking_id}), 201


@app.route("/bookings/<int:booking_id>", methods=["PUT"])
@require_roles("admin", "regular")
def update_booking_route(booking_id):
    """This fct updates an existing booking.

    Expected JSON
    date : str
        New date.
    start_time : str
        New start time.
    end_time : str
        New end time.

    Returns
    tuple
        A message and status code.
    """

    #  RBAC
    current_username, role = get_current_user()

    if role is None:
        return jsonify({"error": "missing X-User-Role header"}), 401

    # booking must exist first, because we need its user_id for ownership check
    row = get_booking_by_id(booking_id)
    if not row:
        return jsonify({"error": "booking not found"}), 404

    # find the booking owner
    booking_user = find_user_by_id(row["user_id"])
    if not booking_user:
        return jsonify({"error": "booking user not found"}), 404

    owner_username = booking_user["username"]

    # admin can update ANY booking
    if role != "admin":
        # regular users can ONLY update their own booking
        if role == "regular":
            if current_username != owner_username:
                return jsonify(
                    {"error": "forbidden: you can only update your own booking"}), 403
        else:
            # all other roles (facility_manager, auditor, moderator, service_account)
            return jsonify(
                {"error": "forbidden: your role cannot modify bookings"}), 403
    

    data = request.get_json() or {}

    needed = ["date", "start_time", "end_time"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    if not valid_time(data["start_time"]) or not valid_time(data["end_time"]):
        return jsonify({"error": "invalid time format HH:MM"}), 400

    if not valid_date(data["date"]):
        return jsonify({"error": "invalid date format YYYY-MM-DD"}), 400

    if data["end_time"] <= data["start_time"]:
        return jsonify({"error": "end_time must be after start_time"}), 400

    # room_id stays fixed
    room_id = row["room_id"]

    # sanity check bcz room should still exist (in case it's deleted)
    if not find_room_by_id(room_id):
        return jsonify({"error": "room not found"}), 404

    # availability check
    ok = is_room_available(
        room_id,
        data["date"],
        data["start_time"],
        data["end_time"],
    )
    if not ok:
        return jsonify({"error": "room's not available for this updated time slot"}), 409

    # perform the update
    update_booking(
        booking_id,
        data["date"],
        data["start_time"],
        data["end_time"],
    )

    return jsonify({"message": "booking updated"}), 200


@app.route("/bookings/<int:booking_id>", methods=["DELETE"])
@require_roles("admin", "regular")
def cancel_booking_route(booking_id):
    """This fct cancels a booking by putting its status as 'cancelled'.

    Parameters
    booking_id : int
        The booking to cancel.

    Returns
    tuple
        Confirmation message and status code.
    """
    current_username, role = get_current_user()

    # check booking exists
    row = get_booking_by_id(booking_id)
    if not row:
        return jsonify({"error": "booking not found"}), 404

    booking_user = find_user_by_id(row["user_id"])

    # regular → only cancel their own
    if role == "regular":
        if booking_user["username"] != current_username:
            return jsonify(
                {"error": "forbidden: you can only cancel your own bookings"}), 403

    # check already cancelled
    if row["status"] == "cancelled":
        return jsonify({"message": "booking already cancelled"}), 200

    cancel_booking(booking_id)
    return jsonify({"message": "booking cancelled"}), 200


@app.route("/rooms/<int:room_id>/availability", methods=["POST"])
def check_room_availability_route(room_id):
    """This fct checks if a room is available for the given date/time.

    Expected JSON:
    date : YYYY-MM-DD
    start_time : HH:MM
    end_time : HH:MM

    Parameters
    room_id : int
        The room being checked.

    Returns
    tuple
        Availability result and status code.
    """
    data = request.get_json() or {}

    date = data.get("date")
    st = data.get("start_time")
    et = data.get("end_time")

    # check room exists
    if not find_room_by_id(room_id):
        return jsonify({"error": "room not found"}), 404


    if not date or not st or not et:
        return jsonify({"error": "date, start_time, end_time are required"}), 400

    if not valid_time(st) or not valid_time(et):
        return jsonify({"error": "invalid time format HH:MM"}), 400

    if not valid_date(date):
        return jsonify({"error": "invalid date format YYYY-MM-DD"}), 400

    if et <= st:
        return jsonify({"error": "end_time must be after start_time"}), 400


    ok = is_room_available(room_id, date, st, et)
    return jsonify({"room_id": room_id, "available": ok}), 200


if __name__ == "__main__":
    make_bookings_table_if_missing()
    port = int(os.environ.get("BOOKINGS_SERVICE_PORT", 5003))
    app.run(host="0.0.0.0", port=port, debug=True)

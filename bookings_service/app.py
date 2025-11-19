# bookings_service/app.py
"""
This module exposes the HTTP endpoints for the bookings service.
It calls database fcts from database.py in the same folder. It focuses on
input validation, checking room availability, and shaping JSON responses.
"""

from flask import Flask, jsonify, request


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
    )

app = Flask(__name__)



# Helpers because I want to avoid being redundant

def require_fields(data, fields):
    """This fct will check that certain fields exist and are not empty in the data that is given."""
    missing = []

    for f in fields:
        if not data.get(f):
            missing.append(f)

    if missing:
        return f"missing: {', '.join(missing)}"
    return None


def valid_time(t):
    """This is just a simple HH:MM validation for times."""
    if len(t) != 5 or t[2] != ":":
        return False
    hh, mm = t.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59

def valid_date(d):
    """This is just a simple YYYY-MM-DD validation for dates."""
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
def list_all_bookings():
    """
    This fct returns all bookings in the system sorted by date/time. It just calls the db fct.
    It returns JSON list of booking objects.
    """
    rows = get_all_bookings()
    return jsonify([dict(r) for r in rows]), 200


@app.route("/bookings/user/<int:user_id>", methods=["GET"])
def get_bookings_for_user_route(user_id):
    """
    This fct returns all of the bookings for the given user (including cancelled ones).
    """
    rows = get_bookings_for_user(user_id)
    return jsonify([dict(r) for r in rows]), 200


@app.route("/bookings", methods=["POST"])
def make_booking_route():
    """
    This fct handles the creation of a new booking.
    It expects a JSON that has: user_id, room_id, date, start_time, end_time.
    It will automatically check the availability too; returns 409 if there's a conflict.
    """
    data = request.get_json() or {}

    needed = ["user_id", "room_id", "date", "start_time", "end_time"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    # validate time format
    if not valid_time(data["start_time"]) or not valid_time(data["end_time"]):
        return jsonify({"error": "invalid time format HH:MM"}), 400
    #same for date
    if not valid_date(data["date"]):
        return jsonify({"error": "invalid date format YYYY-MM-DD"}), 400


    # check room availability
    ok = is_room_available(
        data["room_id"],
        data["date"],
        data["start_time"],
        data["end_time"],
    )
    if not ok:
        return jsonify({"error": "Unfortunately, the room not available for this time slot. Either choose another room or another time"}), 409

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
def update_booking_route(booking_id):
    """
    This fct updates an existing booking.
    It expects input JSON with: date, start_time, end_time, and room_id.
    The room's availability will be checked before updating.
    """
    data = request.get_json() or {}

    needed = ["date", "start_time", "end_time", "room_id"]
    missing_msg = require_fields(data, needed) #calls the helper fct
    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    if not valid_time(data["start_time"]) or not valid_time(data["end_time"]):
        return jsonify({"error": "invalid time format HH:MM"}), 400
    
    if not valid_date(data["date"]):
        return jsonify({"error": "invalid date format YYYY-MM-DD"}), 400


    # availability check
    ok = is_room_available(
        data["room_id"],
        data["date"],
        data["start_time"],
        data["end_time"],
    )
    if not ok:
        return jsonify({"error": "room not available for this updated time slot"}), 409

    update_booking(
        booking_id,
        data["date"],
        data["start_time"],
        data["end_time"],
    )

    return jsonify({"message": "booking updated"}), 200


@app.route("/bookings/<int:booking_id>", methods=["DELETE"])
def cancel_booking_route(booking_id):
    """
    This fct cancels a booking (whos ID is given) by marking its status = 'cancelled'.
    It returns a JSON confirmation message.
    """
    cancel_booking(booking_id)  #simply call db fct
    return jsonify({"message": "booking cancelled"}), 200


@app.route("/rooms/<int:room_id>/availability", methods=["GET"])
def check_room_availability_route(room_id):
    """
    This fct checks whether a room is available for a given date and time period.
    Query parameters required:
      ?date=YYYY-MM-DD&start_time=HH:MM&end_time=HH:MM
    """
    date = request.args.get("date")
    st = request.args.get("start_time")
    et = request.args.get("end_time")

    if not date or not st or not et:
        return jsonify({"error": "date, start_time, end_time are required"}), 400

    if not valid_time(st) or not valid_time(et):
        return jsonify({"error": "invalid time format HH:MM"}), 400
    
    if not valid_date(date):
        return jsonify({"error": "invalid date format YYYY-MM-DD"}), 400


    ok = is_room_available(room_id, date, st, et)
    return jsonify({"room_id": room_id, "available": ok}), 200


if __name__ == "__main__":
    make_bookings_table_if_missing()
    app.run(host="0.0.0.0", port=5003, debug=True)

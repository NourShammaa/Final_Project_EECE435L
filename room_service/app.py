"""This part of the project iis just the HTTP endpoints for the rooms service. it is for managing meeting rooms:
creating, updating, deleting, listing, and checking availability.
"""
from flask import Flask, jsonify, request
from functools import wraps
def get_current_user():
    """Read current user identity from HTTP headers."""
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


app = Flask(__name__)


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

    return jsonify({"message": "room created", "room": created}), 201


@app.route("/rooms", methods=["GET"])
def get_all_rooms():
    """return all rooms in the system as a JSON list."""
    all_rooms = list_all_rooms()
    return jsonify(all_rooms), 200


@app.route("/rooms/available", methods=["GET"])
def get_available_rooms():
    """returns available rooms, optionally filtered by capacity, location, and equipment. takes in as query params min_capacity, location, equipment.
    returns JSON list of matching rooms.
    """
    min_capacity = request.args.get("min_capacity")
    location = request.args.get("location")
    equipment_contains = request.args.get("equipment")

    if min_capacity is not None:
        try:
            min_capacity = int(min_capacity)
        except ValueError:
            return jsonify({"error": "min_capacity must be an integer"}), 400

    rooms = search_available_rooms(
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
    app.run(host="0.0.0.0", port=5002, debug=True)
 
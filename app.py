# users_service/app.py
""" This part of the project exposes the HTTP endpoints for the users service. It takes care of  all direct database work to :mod:`database`  
focuses on validation and shaping  the JSON responses. """
from flask import Flask, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    make_users_table_if_missing,
    insert_user,
    find_user_by_username,
    find_user_by_email,
    list_all_users,
    update_user_row,
    delete_user_row,
)

app = Flask(__name__)


@app.route("/users/register", methods=["POST"])
def register_user():
    """ handkes user registration, this endpoint  expects a JSON bosy with
      "name", "username", "email", "password", and "role" fields. if everything looks good, 
        a new user is inserted into daatabase and  returned ofcourse without password hash.
          returs a JSON response with appropriate status code meaning 4xx/5xx if error  and if user created then status 201."""
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
    return jsonify({"message": "user registered", "user": created}), 201


@app.route("/users/login", methods=["POST"])
def login_user():
    """ handles user login, this endpoint expects a JSON body with "username" and "password" fields.
    password is checked against stored hash. if  credentials are correct, user data is returned.
    reutrns JSON response with appropriate status code 4xx/5xx if error, 200 if login ok."""
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

    user_row.pop("password_hash", None)
    return jsonify({"message": "login ok", "user": user_row}), 200


@app.route("/users", methods=["GET"])
def get_all_users():
    """ retrieves all users from database, removes password hashes before returning.
    returns JSON list of user objects. """
    all_people = list_all_users()
    for u in all_people:
        u.pop("password_hash", None)
    return jsonify(all_people), 200


@app.route("/users/<string:username>", methods=["GET"])
def get_user_by_username_route(username):
    """ retrieves a single user by username, removes password hash before returning.
    returns JSON user object if found with user data, 404 if not found if user doesn't even exist. """
    user_row = find_user_by_username(username)
    if not user_row:
        return jsonify({"error": "user not found"}), 404

    user_row.pop("password_hash", None)
    return jsonify(user_row), 200


@app.route("/users/<string:username>", methods=["PUT"])
def update_user(username):
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
    return jsonify({"message": "user updated", "user": updated}), 200


@app.route("/users/<string:username>", methods=["DELETE"])
def delete_user(username):
    """ deletes a user by username as  parameter.
    returns Json with short confirmation message if deleted, 404 if user not found."""
    existing = find_user_by_username(username)
    if not existing:
        return jsonify({"error": "user not found"}), 404

    rows_deleted = delete_user_row(username)
    if rows_deleted == 0:
        return jsonify({"error": "nothing deleted"}), 500

    return jsonify({"message": f"user {username} deleted"}), 200


@app.route("/users/<string:username>/bookings", methods=["GET"])
def get_user_bookings(username):
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
    app.run(host="0.0.0.0", port=5001, debug=True)

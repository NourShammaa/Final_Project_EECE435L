# reviews_service/app.py
"""
This is the file that handles all API routes for reviews.
It uses db functions from database.py which is  in the same folder, validates user input,
and then returns JSON responses.
"""

import os
import logging
from flask_talisman import Talisman 
import jwt
from flask import Flask, jsonify, request, g
from functools import wraps

AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-change-me")

# Support both import styles: for Sphinx and direct run
try:
    from reviews_service.database import (
        make_reviews_table_if_missing,
        submit_review,
        update_review,
        delete_review,
        get_reviews_for_room,
        flag_review,
        find_user_by_id,
        find_room_by_id,
        find_review_by_id,
    )
except ImportError:
    from database import (
        make_reviews_table_if_missing,
        submit_review,
        update_review,
        delete_review,
        get_reviews_for_room,
        flag_review,
        find_user_by_id,
        find_room_by_id,
        find_review_by_id,
    )

app = Flask(__name__)
Talisman(app, content_security_policy=None)
# ── Auditing / Logging setup ─────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("reviews_service")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "reviews_service.log"))
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
# ── Auditing hooks: log every request & response ─────────────────────────
@app.before_request
def audit_request():
    """
    Log incoming requests:
    - method, path, remote_addr
    - username & role (decoded from token or headers)
    """
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
    """
    Log outgoing responses with status code.
    """
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



# Helper Validation
def require_fields(data, fields):
    """This fct will be used to check if the required fields exist in the incoming JSON.
    It is there to avoid redundancy.

    Parameters
    data : dict
        The parsed JSON body from the request.
    fields : list of str
        The field names that must be present.

    Returns
    str or None
        A message listing missing fields, or None if everything is present.
    """
    missing = []
    for f in fields:
        if not data.get(f):
            missing.append(f)

    if missing:
        return f"missing: {', '.join(missing)}"
    return None


def valid_rating(r):
    """Check that the rating is an integer between 0 and 10.

    Parameters
    r : any
        The rating value provided.

    Returns
    bool
        True if valid, False otherwise.
    """
    try:
        r = int(r)
        return 0 <= r <= 10
    except:
        return False



# Routes
#everyone can read reviews!!
@app.route("/reviews/room/<int:room_id>", methods=["GET"])
def list_reviews_for_room(room_id):
    """Get all reviews for a room, newest first. Everyone can read reviews.

    Parameters
    room_id : int
        The ID of the room for which reviews are requested.

    Returns
    tuple
        A JSON list of reviews and a 200 status code.
    """
    

    # ensure the room exists
    if not find_room_by_id(room_id):
        return jsonify({"error": "room not found"}), 404

    rows = get_reviews_for_room(room_id)
    return jsonify([dict(r) for r in rows]), 200


@app.route("/reviews", methods=["POST"])
@require_roles("admin", "regular", "facility_manager")
def submit_review_route():
    """Create a new review.

    Expected JSON
    user_id : int
        Who wrote the review.
    room_id : int
        Which room is being reviewed.
    rating : int
        A number from 0 to 10.
    comment : str
        A short message expressing the user’s thoughts.

    Returns
    tuple
        JSON containing a success message and the new review_id,
        or an error message with an appropriate status code.
    """
    data = request.get_json() or {}



    current_username, role = get_current_user()

    # If regular → can only create for self
    if role == "regular":
        user_row = find_user_by_id(data.get("user_id"))
        if not user_row:
            return jsonify({"error": "user not found"}), 404

        if user_row["username"] != current_username:
            return jsonify({
                "error": "forbidden: you can only submit reviews as yourself"}), 403


    needed = ["user_id", "room_id", "rating", "comment"]
    missing_msg = require_fields(data, needed)

    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    # validate rating
    if not valid_rating(data["rating"]):
        return jsonify({"error": "rating must be an integer between 0 and 10"}), 400

    # validate comment not empty
    if not data["comment"].strip():
        return jsonify({"error": "comment cannot be empty"}), 400

    # check user exists
    if not find_user_by_id(data["user_id"]):
        return jsonify({"error": "user not found"}), 404

    # check room exists
    if not find_room_by_id(data["room_id"]):
        return jsonify({"error": "room not found"}), 404

    review_id = submit_review(
        data["user_id"],
        data["room_id"],
        int(data["rating"]),
        data["comment"],
    )

    if not review_id:
        return jsonify({"error": "could not create review"}), 500

    return jsonify({"message": "review submitted", "review_id": review_id}), 201



@app.route("/reviews/<int:review_id>", methods=["PUT"])
@require_roles("admin", "regular", "facility_manager")
def update_review_route(review_id):
    """Update the rating and comment of an existing review.

    Expected JSON
    rating : int
        Updated score from 0 to 10.
    comment : str
        Updated written feedback.

    Returns
    tuple
        JSON confirmation and a 200 status code,
        or an error if validation fails.
    """
    data = request.get_json() or {}


    current_username, role = get_current_user()

    row = find_review_by_id(review_id)
    if not row:
        return jsonify({"error": "review not found"}), 404

    review_owner = find_user_by_id(row["user_id"])

    # Regular → only own review
    if role in ("regular", "facility_manager") and review_owner["username"] != current_username:
        return jsonify({
            "error": "forbidden: you can only update your own reviews"}), 403


    needed = ["rating", "comment"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    if not valid_rating(data["rating"]):
        return jsonify({"error": "rating must be an integer between 0 and 10"}), 400

    if not data["comment"].strip():
        return jsonify({"error": "comment cannot be empty"}), 400


    update_review(review_id, int(data["rating"]), data["comment"])

    return jsonify({"message": "review updated"}), 200


@app.route("/reviews/<int:review_id>", methods=["DELETE"])
@require_roles("admin", "regular", "facility_manager", "moderator")
def delete_review_route(review_id):
    """This fct will delete a review forever!

    Parameters
    review_id : int
        The ID of the review to remove.

    Returns
    tuple
        A short confirmation message and status 200.
    """

    # check review exists
    row = find_review_by_id(review_id)
    if not row:
        return jsonify({"error": "review not found"}), 404
    
    current_username, role = get_current_user()

    review_owner = find_user_by_id(row["user_id"])

    # regular/fac manager → only their own
    if role in ("regular", "facility_manager"):
        if review_owner["username"] != current_username:
            return jsonify({
                "error": "forbidden: you can only delete your own reviews"}), 403

    # moderator/admin is  allowed to continue normally


    delete_review(review_id)
    return jsonify({"message": "review deleted"}), 200


@app.route("/reviews/<int:review_id>/flag", methods=["PUT"])
@require_roles("admin", "moderator")
def flag_review_route(review_id):
    """Mark a review as flagged so it can be reviewed by someone human.

    Parameters
    review_id : int
        The ID of the review being flagged.

    Returns
    tuple
        A confirmation message and status 200.
    """

    # check review exists
    row = find_review_by_id(review_id)
    if not row:
        return jsonify({"error": "review not found"}), 404

    flag_review(review_id)
    return jsonify({"message": "review flagged"}), 200


if __name__ == "__main__":
    make_reviews_table_if_missing()
    port = int(os.environ.get("REVIEWS_SERVICE_PORT", 5004))
    app.run(host="0.0.0.0", port=port, debug=True)

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
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import sentry_sdk
sentry_sdk.init(
    dsn="https://48bdf0331a6458ead11b21da3ac3f9ec@o4510444553437184.ingest.de.sentry.io/4510444562481232",
    traces_sample_rate=1.0
)


AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-change-me")

# ADDED FOR TASK 7  Custom Exceptions
class BadRequestError(Exception):
    pass

class UnauthorizedError(Exception):
    pass

class ForbiddenError(Exception):
    pass

class NotFoundError(Exception):
    pass

class ConflictError(Exception):
    pass

class InternalServerError(Exception):
    pass


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
@app.route("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

Talisman(app, content_security_policy=None, force_https=False)

# Global API Version Prefix: /api/v1
class PrefixMiddleware:
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'].startswith(self.prefix):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
        return self.app(environ, start_response)

#app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix="/api/v1")


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
    """This fct decode user from token, fallback to X-User-* headers."""
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=["HS256"])
            return payload.get("username"), payload.get("role")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None, None

    username = request.headers.get("X-User-Name")
    role = request.headers.get("X-User-Role")

    if not username or not role:
        return None, None

    return username, role


# ── Auditing hooks ─────────────────────────────────────────────
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


@app.before_request
def enforce_auth():
    # Allow Prometheus metrics without authentication
    if request.path == "/metrics":
        return
    if request.method == "OPTIONS":
        return

    # Public endpoint: people can read room reviews
    if request.path.startswith("/reviews/room/") and request.method == "GET":
        return

    username, role = get_current_user()

    if username is None or role is None:
        raise UnauthorizedError("authentication required")
        return jsonify({"error": "authentication required"}), 401


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
                raise UnauthorizedError("missing X-User-Role header")
                return jsonify({"error": "missing X-User-Role header"}), 401

            if role not in allowed_roles:
                raise ForbiddenError(
                    f"forbidden: requires one of roles: {', '.join(allowed_roles)}"
                )
                return jsonify({"error": "forbidden"}), 403

            return view_func(*args, **kwargs)
        return wrapped
    return decorator


# Helper Validation
def require_fields(data, fields):
    """This fct will be used to check if the required fields exist in the incoming JSON.
    It is there to avoid redundancy.
    """
    missing = []
    for f in fields:
        if not data.get(f):
            missing.append(f)

    if missing:
        return f"missing: {', '.join(missing)}"
    return None


def valid_rating(r):
    """Check that the rating is an integer between 0 and 10."""
    try:
        r = int(r)
        return 0 <= r <= 10
    except:
        return False


# Routes
@app.route("/reviews/room/<int:room_id>", methods=["GET"])
def list_reviews_for_room(room_id):
    """Get all reviews for a room, newest first. Everyone can read reviews."""
    if not find_room_by_id(room_id):
        raise NotFoundError("room not found")
        return jsonify({"error": "room not found"}), 404

    rows = get_reviews_for_room(room_id)
    return jsonify([dict(r) for r in rows]), 200



@app.route("/reviews", methods=["POST"])
@require_roles("admin", "regular", "facility_manager")
def submit_review_route():
    """Create a new review."""
    data = request.get_json() or {}
    current_username, role = get_current_user()

    # If regular → only create for self
    if role == "regular":
        user_row = find_user_by_id(data.get("user_id"))
        if not user_row:
            raise NotFoundError("user not found")
            return jsonify({"error": "user not found"}), 404

        if user_row["username"] != current_username:
            raise ForbiddenError("forbidden: you can only submit reviews as yourself")
            return jsonify({"error": "forbidden: you can only submit reviews as yourself"}), 403


    needed = ["user_id", "room_id", "rating", "comment"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        raise BadRequestError(missing_msg)
        return jsonify({"error": missing_msg}), 400

    if not valid_rating(data["rating"]):
        raise BadRequestError("rating must be an integer between 0 and 10")
        return jsonify({"error": "rating invalid"}), 400

    if not data["comment"].strip():
        raise BadRequestError("comment cannot be empty")
        return jsonify({"error": "comment empty"}), 400

    if not find_user_by_id(data["user_id"]):
        raise NotFoundError("user not found")
        return jsonify({"error": "user not found"}), 404

    if not find_room_by_id(data["room_id"]):
        raise NotFoundError("room not found")
        return jsonify({"error": "room not found"}), 404

    review_id = submit_review(
        data["user_id"],
        data["room_id"],
        int(data["rating"]),
        data["comment"],
    )

    if not review_id:
        raise InternalServerError("could not create review")
        return jsonify({"error": "could not create review"}), 500

    return jsonify({"message": "review submitted", "review_id": review_id}), 201



@app.route("/reviews/<int:review_id>", methods=["PUT"])
@require_roles("admin", "regular", "facility_manager")
def update_review_route(review_id):
    """Update the rating and comment of an existing review."""
    data = request.get_json() or {}
    current_username, role = get_current_user()

    row = find_review_by_id(review_id)
    if not row:
        raise NotFoundError("review not found")
        return jsonify({"error": "review not found"}), 404

    review_owner = find_user_by_id(row["user_id"])

    # Ownership rule
    if role in ("regular", "facility_manager") and review_owner["username"] != current_username:
        raise ForbiddenError("forbidden: you can only update your own reviews")
        return jsonify({"error": "forbidden: you can only update your own reviews"}), 403


    needed = ["rating", "comment"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        raise BadRequestError(missing_msg)
        return jsonify({"error": missing_msg}), 400

    if not valid_rating(data["rating"]):
        raise BadRequestError("rating must be an integer between 0 and 10")
        return jsonify({"error": "rating invalid"}), 400

    if not data["comment"].strip():
        raise BadRequestError("comment cannot be empty")
        return jsonify({"error": "comment empty"}), 400

    update_review(review_id, int(data["rating"]), data["comment"])
    return jsonify({"message": "review updated"}), 200



@app.route("/reviews/<int:review_id>", methods=["DELETE"])
@require_roles("admin", "regular", "facility_manager", "moderator")
def delete_review_route(review_id):
    """This fct will delete a review forever!"""
    row = find_review_by_id(review_id)
    if not row:
        raise NotFoundError("review not found")
        return jsonify({"error": "review not found"}), 404

    current_username, role = get_current_user()
    review_owner = find_user_by_id(row["user_id"])

    if role in ("regular", "facility_manager") and review_owner["username"] != current_username:
        raise ForbiddenError("forbidden: you can only delete your own reviews")
        return jsonify({"error": "forbidden: you can only delete your own reviews"}), 403


    delete_review(review_id)
    return jsonify({"message": "review deleted"}), 200



@app.route("/reviews/<int:review_id>/flag", methods=["PUT"])
@require_roles("admin", "moderator")
def flag_review_route(review_id):
    """Mark a review as flagged so it can be reviewed by someone human."""
    row = find_review_by_id(review_id)
    if not row:
        raise NotFoundError("review not found")
        return jsonify({"error": "review not found"}), 404

    flag_review(review_id)
    return jsonify({"message": "review flagged"}), 200



@app.before_request
def allow_metrics():
    if request.path == "/metrics":
        return None



# --- Global Error Handlers (pytest-compatible) ---

@app.errorhandler(BadRequestError)
def handle_bad_request(e):
    return jsonify({"error": str(e)}), 400

@app.errorhandler(UnauthorizedError)
def handle_unauthorized(e):
    return jsonify({"error": str(e)}), 401

@app.errorhandler(ForbiddenError)
def handle_forbidden(e):
    return jsonify({"error": str(e)}), 403

@app.errorhandler(NotFoundError)
def handle_not_found(e):
    if request.path == "/metrics":
        return e
    return jsonify({"error": str(e)}), 404

@app.errorhandler(ConflictError)
def handle_conflict(e):
    return jsonify({"error": str(e)}), 409

@app.errorhandler(Exception)
def handle_generic_error(e):
    logger.exception("Unhandled exception: %s", str(e))
    return jsonify({"error": "internal server error"}), 500


if __name__ == "__main__":
    make_reviews_table_if_missing()
    port = int(os.environ.get("REVIEWS_SERVICE_PORT", 5004))
    app.run(host="0.0.0.0", port=port, debug=True)

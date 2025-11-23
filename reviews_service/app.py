# reviews_service/app.py
"""
This is the file that handles all API routes for reviews.
It uses db functions from database.py which is  in the same folder, validates user input,
and then returns JSON responses.
"""

from flask import Flask, jsonify, request

# Support both import styles: for Sphinx and direct run
try:
    from reviews_service.database import (
        make_reviews_table_if_missing,
        submit_review,
        update_review,
        delete_review,
        get_reviews_for_room,
        flag_review,
    )
except ImportError:
    from database import (
        make_reviews_table_if_missing,
        submit_review,
        update_review,
        delete_review,
        get_reviews_for_room,
        flag_review,
    )

app = Flask(__name__)



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

@app.route("/reviews/room/<int:room_id>", methods=["GET"])
def list_reviews_for_room(room_id):
    """Get all reviews for a room, newest first.

    Parameters
    room_id : int
        The ID of the room for which reviews are requested.

    Returns
    tuple
        A JSON list of reviews and a 200 status code.
    """
    rows = get_reviews_for_room(room_id)
    return jsonify([dict(r) for r in rows]), 200


@app.route("/reviews", methods=["POST"])
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

    needed = ["user_id", "room_id", "rating", "comment"]
    missing_msg = require_fields(data, needed)

    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    if not valid_rating(data["rating"]):
        return jsonify(
            {"error": "rating must be an integer between 0 and 10"}), 400

    review_id = submit_review(data["user_id"], data["room_id"], int(data["rating"]), data["comment"],
    )

    if not review_id:
        return jsonify({"error": "could not create review"}), 500

    return jsonify({"message": "review submitted", "review_id": review_id}), 201


@app.route("/reviews/<int:review_id>", methods=["PUT"])
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

    needed = ["rating", "comment"]
    missing_msg = require_fields(data, needed)
    if missing_msg:
        return jsonify({"error": missing_msg}), 400

    if not valid_rating(data["rating"]):
        return jsonify(
            {"error": "rating must be an integer between 0 and 10"}
        ), 400

    update_review(review_id, int(data["rating"]), data["comment"],
    )

    return jsonify({"message": "review updated"}), 200


@app.route("/reviews/<int:review_id>", methods=["DELETE"])
def delete_review_route(review_id):
    """Delete a review forever (no take-backs).

    Parameters
    review_id : int
        The ID of the review to remove.

    Returns
    tuple
        A short confirmation message and status 200.
    """
    delete_review(review_id)
    return jsonify({"message": "review deleted"}), 200


@app.route("/reviews/<int:review_id>/flag", methods=["PUT"])
def flag_review_route(review_id):
    """Mark a review as flagged so it can be reviewed by someone human.

    Parameters
    review_id : int
        The ID of the review being flagged.

    Returns
    tuple
        A confirmation message and status 200.
    """
    flag_review(review_id)
    return jsonify({"message": "review flagged"}), 200



# Launch (local dev)
if __name__ == "__main__":
    make_reviews_table_if_missing()
    app.run(host="0.0.0.0", port=5004, debug=True)

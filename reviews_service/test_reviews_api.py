import os
import sqlite3
import pytest

# Support both package-style and local imports, exactly like bookings
try:
    from reviews_service.app import app
    from reviews_service.database import submit_review
except ImportError:
    from app import app
    from database import submit_review

# Path to the shared SQLite DB (same logic as bookings tests)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")


# FIXTURE to  Clean DB before each test
# ASSUMPTION:
#   - Tables users, rooms, reviews ALREADY EXIST in database.db.
#   - We only delete rows, we DO NOT create tables here.

@pytest.fixture(autouse=True)
def fresh_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF;") 

    # Correct deletion order:
    conn.execute("DELETE FROM reviews;")
    conn.execute("DELETE FROM rooms;")
    conn.execute("DELETE FROM users;")

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.close()





# Helper seeders

def seed_user(name, username, email, role):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (name, username, email, role, password_hash, created_at)
        VALUES (?, ?, ?, ?, 'hash', 'now');
        """,
        (name, username, email, role),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def seed_room(name="NicelyHall", capacity=12):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO rooms (name, capacity, equipment, location, status)
        VALUES (?, ?, 'Projector', 'AUB Beirut', 'active');
        """,
        (name, capacity),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def seed_review(user_id, room_id, rating=8, comment="Nice room!"):
    """Use the REAL DB helper for reviews."""
    return submit_review(user_id, room_id, rating, comment)



# Flask test client

@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


# TEST GROUP 1 GET /reviews/room/<room_id>

def test_list_reviews_room_not_found(client):
    res = client.get("/reviews/room/99999")
    assert res.status_code == 404
    assert "room not found" in res.json["error"]


def test_list_reviews_success(client):
    uid = seed_user("Maya", "maya_beirut", "maya@aub.edu.lb", "regular")
    rid = seed_room()
    seed_review(uid, rid, 9, "Great room!")

    res = client.get(f"/reviews/room/{rid}")

    assert res.status_code == 200
    assert len(res.json) == 1
    assert res.json[0]["comment"] == "Great room!"


# TEST GROUP 2 POST /reviews  (submit_review_route)

def test_submit_review_regular_success(client):
    uid = seed_user("Riwa", "riwaelkari", "riwa@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "rating": 7,
        "comment": "Beautiful place",
    }

    res = client.post(
        "/reviews",
        json=payload,
        headers={"X-User-Role": "regular", "X-User-Name": "riwaelkari"},
    )

    assert res.status_code == 201
    assert "review_id" in res.json


def test_submit_review_regular_wrong_owner(client):
    uid = seed_user("Ali", "ali123", "ali@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "rating": 6,
        "comment": "Nice!",
    }

    # Header user is NOT Ali → should be forbidden
    res = client.post(
        "/reviews",
        json=payload,
        headers={"X-User-Role": "regular", "X-User-Name": "someone_else"},
    )

    assert res.status_code == 403
    assert "forbidden" in res.json["error"]


# TEST GROUP 3 PUT /reviews/<id>  (update_review_route)

def test_update_review_owner_success(client):
    uid = seed_user("Nour", "nour123", "nour@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid, 5, "Okay")

    res = client.put(
        f"/reviews/{rev_id}",
        json={"rating": 9, "comment": "Amazing!"},
        headers={"X-User-Role": "regular", "X-User-Name": "nour123"},
    )

    assert res.status_code == 200
    assert res.json["message"] == "review updated"


def test_update_review_forbidden_other_user(client):
    uid = seed_user("Dana", "dana123", "dana@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid, 8, "Good")

    res = client.put(
        f"/reviews/{rev_id}",
        json={"rating": 1, "comment": "Terrible"},
        headers={"X-User-Role": "regular", "X-User-Name": "not_dana"},
    )

    assert res.status_code == 403
    assert "forbidden" in res.json["error"]



# TEST GROUP 4 DELETE /reviews/<id> (delete_review_route)
def test_delete_review_owner_success(client):
    uid = seed_user("Karim", "karim123", "karim@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid)

    res = client.delete(
        f"/reviews/{rev_id}",
        headers={"X-User-Role": "regular", "X-User-Name": "karim123"},
    )

    assert res.status_code == 200
    assert res.json["message"] == "review deleted"


def test_delete_review_moderator_can_delete_any(client):
    uid = seed_user("Jad", "jad123", "jad@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid)

    res = client.delete(
        f"/reviews/{rev_id}",
        headers={"X-User-Role": "moderator", "X-User-Name": "mod_beirut"},
    )

    assert res.status_code == 200
    assert res.json["message"] == "review deleted"


def test_delete_review_forbidden_regular_other_user(client):
    uid = seed_user("Tala", "tala123", "tala@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid)

    res = client.delete(
        f"/reviews/{rev_id}",
        headers={"X-User-Role": "regular", "X-User-Name": "otheruser"},
    )

    assert res.status_code == 403
    assert "forbidden" in res.json["error"]



# TEST GROUP 5 PUT /reviews/<id>/flag (flag_review_route)
def test_flag_review_success_admin(client):
    uid = seed_user("Layla", "layla123", "layla@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid)

    res = client.put(
        f"/reviews/{rev_id}/flag",
        headers={"X-User-Role": "admin", "X-User-Name": "admin_user"},
    )

    assert res.status_code == 200
    assert res.json["message"] == "review flagged"


def test_flag_review_forbidden_non_moderator(client):
    uid = seed_user("Tony", "tony123", "tony@aub.edu.lb", "regular")
    rid = seed_room()
    rev_id = seed_review(uid, rid)

    res = client.put(
        f"/reviews/{rev_id}/flag",
        headers={"X-User-Role": "regular", "X-User-Name": "tony123"},
    )

    assert res.status_code == 403
    assert "forbidden" in res.json["error"]



# MISSING TESTS

def test_submit_review_missing_fields(client):
    uid = seed_user("Test", "test123", "t@aub.edu.lb", "regular")

    res = client.post(
        "/reviews",
        json={"user_id": uid},   # missing room_id, rating, comment
        headers={"X-User-Role": "regular", "X-User-Name": "test123"}
    )
    assert res.status_code == 400
    assert "missing" in res.json["error"]



def test_submit_review_invalid_rating(client):
    uid = seed_user("Sam", "sam123", "sam@aub.edu.lb", "regular")
    rid = seed_room()

    res = client.post(
        "/reviews",
        json={"user_id": uid, "room_id": rid, "rating": 99, "comment": "ok"},
        headers={"X-User-Role": "regular", "X-User-Name": "sam123"},
    )
    assert res.status_code == 400
    assert "rating" in res.json["error"]


def test_submit_review_empty_comment(client):
    uid = seed_user("Lina", "lina123", "lina@aub.edu.lb", "regular")
    rid = seed_room()

    res = client.post(
        "/reviews",
        json={"user_id": uid, "room_id": rid, "rating": 5, "comment": "  "},
        headers={"X-User-Role": "regular", "X-User-Name": "lina123"},
    )
    assert res.status_code == 400
    assert "comment cannot be empty" in res.json["error"]


def test_update_review_not_found(client):
    res = client.put(
        "/reviews/99999",
        json={"rating": 5, "comment": "test"},
        headers={"X-User-Role": "regular", "X-User-Name": "any"},
    )
    assert res.status_code == 404
    assert "review not found" in res.json["error"]


def test_delete_review_not_found(client):
    res = client.delete(
        "/reviews/99999",
        headers={"X-User-Role": "admin", "X-User-Name": "admin"},
    )
    assert res.status_code == 404
    assert "review not found" in res.json["error"]


def test_flag_review_not_found(client):
    res = client.put(
        "/reviews/99999/flag",
        headers={"X-User-Role": "admin", "X-User-Name": "admin"},
    )
    assert res.status_code == 404
    assert "review not found" in res.json["error"]


def test_submit_review_missing_auth(client):
    res = client.post("/reviews", json={})
    assert res.status_code == 401
    assert "authentication required" in res.json["error"]

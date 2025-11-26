import os
import sqlite3
import pytest
from bookings_service.app import app


# ASSUMPTION:
#   - We manually insert into users + rooms using raw SQL.
#
# WHY RAW SQL?
#   → Because Pytest for BOOKING SERVICE should not depend on
#     other microservices.


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")


# -----------------------------------------------------------
# FIXTURE: Reset DB before every test
# -----------------------------------------------------------
@pytest.fixture(autouse=True)
def fresh_db():
    """Clear tables before each test."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    # Wipe all tables
    conn.execute("DELETE FROM bookings;")
    conn.execute("DELETE FROM users;")
    conn.execute("DELETE FROM rooms;")

    conn.commit()
    conn.close()



# Helper: insert fake user + room
def seed_user(name, username, email, role):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (name, username, email, role, password_hash, created_at)
        VALUES (?, ?, ?, ?, 'hash', 'now');
    """, (name, username, email, role))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def seed_room(name="AUB_Beirut", capacity=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO rooms (name, capacity, equipment, location, status)
        VALUES (?, ?, 'Projector', 'AUB', 'active');
    """, (name, capacity))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid



# FIXTURE: Flask test client
@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()



# TEST 1 — list_all_bookings (RBAC)
def test_list_all_bookings_rbac_forbidden(client):
    res = client.get("/bookings", headers={"X-User-Role": "regular"})
    assert res.status_code == 403


def test_list_all_bookings_ok(client):
    res = client.get("/bookings", headers={"X-User-Role": "admin"})
    assert res.status_code == 200
    assert res.json == []



# TEST 2 — create booking
def test_create_booking_success(client):
    # Seed user + room
    uid = seed_user("Riwa", "riwaelkari", "riwa@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-10",
        "start_time": "10:00",
        "end_time": "11:00",
    }

    res = client.post("/bookings",
                      json=payload,
                      headers={
                          "X-User-Role": "regular",
                          "X-User-Name": "riwaelkari",
                      })

    assert res.status_code == 201
    assert "booking_id" in res.json


def test_create_booking_wrong_owner(client):
    uid = seed_user("Ali", "ali123", "ali@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-10",
        "start_time": "10:00",
        "end_time": "11:00",
    }

    res = client.post("/bookings",
                      json=payload,
                      headers={
                          "X-User-Role": "regular",
                          "X-User-Name": "riwaelkari",    # wrong user
                      })

    assert res.status_code == 403


# TEST 3 — get bookings for a user
def test_get_bookings_for_user_only_their_own(client):
    uid = seed_user("Maya", "maya_beirut", "maya@aub.edu.lb", "regular")
    rid = seed_room()

    # Create a booking directly (raw SQL)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '08:00', '09:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    res = client.get(f"/bookings/user/{uid}",
                     headers={
                         "X-User-Role": "regular",
                         "X-User-Name": "maya_beirut",
                     })

    assert res.status_code == 200
    assert len(res.json) == 1


def test_get_bookings_regular_cannot_view_others(client):
    uid = seed_user("Samer", "samer123", "samer@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '08:00', '09:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    # Another user tries to view
    res = client.get(f"/bookings/user/{uid}",
                     headers={
                         "X-User-Role": "regular",
                         "X-User-Name": "different_user",
                     })

    assert res.status_code == 403


# -----------------------------------------------------------
# TEST 4 — update booking
# -----------------------------------------------------------
def test_update_booking_by_owner(client):
    uid = seed_user("Dana", "dana123", "dana@aub.edu.lb", "regular")
    rid = seed_room()

    # create booking
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.put(
        f"/bookings/{booking_id}",
        json={"date": "2025-01-02", "start_time": "10:00", "end_time": "12:00"},
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "dana123"
        },
    )

    assert res.status_code == 200
    assert res.json["message"] == "booking updated"


def test_update_booking_forbidden_for_non_owner(client):
    uid = seed_user("Nour", "nour123", "nour@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.put(
        f"/bookings/{booking_id}",
        json={"date": "2025-01-02", "start_time": "12:00", "end_time": "13:00"},
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "not_nour"
        },
    )

    assert res.status_code == 403



# TEST 5 — cancel booking
def test_cancel_booking_success(client):
    uid = seed_user("Jad", "jad123", "jad@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.delete(
        f"/bookings/{booking_id}",
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "jad123",
        },
    )

    assert res.status_code == 200
    assert res.json["message"] == "booking cancelled"



def test_cancel_booking_forbidden(client):
    uid = seed_user("Karim", "karim123", "karim@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.delete(
        f"/bookings/{booking_id}",
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "notkarim",
        },
    )

    assert res.status_code == 403


import os
import sqlite3
import pytest
from bookings_service.app import app

# -----------------------------------------------------------
# ASSUMPTION:
#   - We manually insert into users + rooms using raw SQL.
#
# WHY RAW SQL?
#   → Because Pytest for BOOKING SERVICE should not depend on
#     other microservices.
# -----------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")


# -----------------------------------------------------------
# FIXTURE: Reset DB before every test
# -----------------------------------------------------------
@pytest.fixture(autouse=True)
def fresh_db():
    """Clear tables before each test."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    # Wipe all tables
    conn.execute("DELETE FROM bookings;")
    conn.execute("DELETE FROM users;")
    conn.execute("DELETE FROM rooms;")

    conn.commit()
    conn.close()



# Helper: insert fake user + room
def seed_user(name, username, email, role):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (name, username, email, role, password_hash, created_at)
        VALUES (?, ?, ?, ?, 'hash', 'now');
    """, (name, username, email, role))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def seed_room(name="AUB_Beirut", capacity=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO rooms (name, capacity, equipment, location, status)
        VALUES (?, ?, 'Projector', 'AUB', 'active');
    """, (name, capacity))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid



# FIXTURE: Flask test client
@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()



# TEST 1 — list_all_bookings (RBAC)
def test_list_all_bookings_rbac_forbidden(client):
    res = client.get("/bookings", headers={"X-User-Role": "regular"})
    assert res.status_code == 403


def test_list_all_bookings_ok(client):
    res = client.get("/bookings", headers={"X-User-Role": "admin"})
    assert res.status_code == 200
    assert res.json == []



# TEST 2 — create booking
def test_create_booking_success(client):
    # Seed user + room
    uid = seed_user("Riwa", "riwaelkari", "riwa@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-10",
        "start_time": "10:00",
        "end_time": "11:00",
    }

    res = client.post("/bookings",
                      json=payload,
                      headers={
                          "X-User-Role": "regular",
                          "X-User-Name": "riwaelkari",
                      })

    assert res.status_code == 201
    assert "booking_id" in res.json


def test_create_booking_wrong_owner(client):
    uid = seed_user("Ali", "ali123", "ali@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-10",
        "start_time": "10:00",
        "end_time": "11:00",
    }

    res = client.post("/bookings",
                      json=payload,
                      headers={
                          "X-User-Role": "regular",
                          "X-User-Name": "riwaelkari",    # wrong user
                      })

    assert res.status_code == 403


# TEST 3 — get bookings for a user
def test_get_bookings_for_user_only_their_own(client):
    uid = seed_user("Maya", "maya_beirut", "maya@aub.edu.lb", "regular")
    rid = seed_room()

    # Create a booking directly (raw SQL)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '08:00', '09:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    res = client.get(f"/bookings/user/{uid}",
                     headers={
                         "X-User-Role": "regular",
                         "X-User-Name": "maya_beirut",
                     })

    assert res.status_code == 200
    assert len(res.json) == 1


def test_get_bookings_regular_cannot_view_others(client):
    uid = seed_user("Samer", "samer123", "samer@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '08:00', '09:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    # Another user tries to view
    res = client.get(f"/bookings/user/{uid}",
                     headers={
                         "X-User-Role": "regular",
                         "X-User-Name": "different_user",
                     })

    assert res.status_code == 403


# -----------------------------------------------------------
# TEST 4 — update booking
# -----------------------------------------------------------
def test_update_booking_by_owner(client):
    uid = seed_user("Dana", "dana123", "dana@aub.edu.lb", "regular")
    rid = seed_room()

    # create booking
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.put(
        f"/bookings/{booking_id}",
        json={"date": "2025-01-02", "start_time": "10:00", "end_time": "12:00"},
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "dana123"
        },
    )

    assert res.status_code == 200
    assert res.json["message"] == "booking updated"


def test_update_booking_forbidden_for_non_owner(client):
    uid = seed_user("Nour", "nour123", "nour@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.put(
        f"/bookings/{booking_id}",
        json={"date": "2025-01-02", "start_time": "12:00", "end_time": "13:00"},
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "not_nour"
        },
    )

    assert res.status_code == 403



# TEST 5 — cancel booking
def test_cancel_booking_success(client):
    uid = seed_user("Jad", "jad123", "jad@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.delete(
        f"/bookings/{booking_id}",
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "jad123",
        },
    )

    assert res.status_code == 200
    assert res.json["message"] == "booking cancelled"



def test_cancel_booking_forbidden(client):
    uid = seed_user("Karim", "karim123", "karim@aub.edu.lb", "regular")
    rid = seed_room()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-01', '10:00', '11:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.delete(
        f"/bookings/{booking_id}",
        headers={
            "X-User-Role": "regular",
            "X-User-Name": "notkarim",
        },
    )

    assert res.status_code == 403

def test_create_booking_invalid_time_format(client):
    uid = seed_user("Hadi", "hadi123", "hadi@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-01",
        "start_time": "9AM",          # invalid
        "end_time": "11:00"
    }

    res = client.post(
        "/bookings",
        json=payload,
        headers={"X-User-Role": "regular", "X-User-Name": "hadi123"}
    )

    assert res.status_code == 400
    assert "invalid time format" in res.json["error"]

def test_create_booking_conflict(client):
    uid = seed_user("Yara", "yara123", "yara@aub.edu.lb", "regular")
    rid = seed_room()

    # Seed an existing active booking 10:00–11:00
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-02', '10:00', '11:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    # Try to create overlapping booking 10:30–11:30
    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-02",
        "start_time": "10:30",
        "end_time": "11:30",
    }

    res = client.post(
        "/bookings",
        json=payload,
        headers={"X-User-Role": "regular", "X-User-Name": "yara123"}
    )

    assert res.status_code == 409
    assert "not available" in res.json["error"]
def test_room_availability_free(client):
    rid = seed_room("NicelyHall", 20)

    res = client.post(
        f"/rooms/{rid}/availability",
        json={
            "date": "2025-01-10",
            "start_time": "12:00",
            "end_time": "13:00"
        }
    )

    assert res.status_code == 200
    assert res.json["available"] is True

def test_room_availability_conflict(client):
    uid = seed_user("Faris", "faris123", "faris@aub.edu.lb", "regular")
    rid = seed_room("WestHall", 15)

    # seed existing booking 09:00–10:00
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-12', '09:00', '10:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    res = client.post(
        f"/rooms/{rid}/availability",
        json={"date": "2025-01-12", "start_time": "09:30", "end_time": "10:30"}
    )

    assert res.status_code == 200
    assert res.json["available"] is False

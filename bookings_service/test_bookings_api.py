import os
import sqlite3
import pytest
import jwt
from bookings_service.app import app

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database.db")
AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-change-me")

@pytest.fixture(autouse=True)
def fresh_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("DELETE FROM bookings;")
    conn.execute("DELETE FROM users;")
    conn.execute("DELETE FROM rooms;")
    conn.commit()
    conn.close()

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

@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()

def test_list_all_bookings_rbac_forbidden(client):
    res = client.get("/bookings", headers={"X-User-Role": "regular", "X-User-Name": "any"})
    assert res.status_code == 403

def test_list_all_bookings_ok(client):
    res = client.get("/bookings", headers={"X-User-Role": "admin", "X-User-Name": "admin"})
    assert res.status_code == 200
    assert res.json == []

def test_create_booking_success(client):
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
                          "X-User-Name": "riwaelkari",
                      })

    assert res.status_code == 403

def test_get_bookings_for_user_only_their_own(client):
    uid = seed_user("Maya", "maya_beirut", "maya@aub.edu.lb", "regular")
    rid = seed_room()

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

    res = client.get(f"/bookings/user/{uid}",
                     headers={
                         "X-User-Role": "regular",
                         "X-User-Name": "different_user",
                     })

    assert res.status_code == 403

def test_update_booking_by_owner(client):
    uid = seed_user("Dana", "dana123", "dana@aub.edu.lb", "regular")
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
        "start_time": "9AM",
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

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-02', '10:00', '11:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

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
        },
        headers={"X-User-Role": "regular", "X-User-Name": "any"}
    )

    assert res.status_code == 200
    assert res.json["available"] is True

def test_room_availability_conflict(client):
    uid = seed_user("Faris", "faris123", "faris@aub.edu.lb", "regular")
    rid = seed_room("WestHall", 15)

    # seed existing booking 09:00 10:00
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-12', '09:00', '10:00', 'active');
    """, (uid, rid))
    conn.commit()
    conn.close()

    res = client.post(
        f"/rooms/{rid}/availability",
        json={"date": "2025-01-12", "start_time": "09:30", "end_time": "10:30"},
        headers={"X-User-Role": "regular", "X-User-Name": "any"}
    )

    assert res.status_code == 200
    assert res.json["available"] is False



# JWT TESTS 

def test_jwt_missing_token(client):
    res = client.get("/bookings")
    assert res.status_code == 401

def test_jwt_invalid_token(client):
    headers = {"Authorization": "Bearer invalid.token.here"}
    res = client.get("/bookings", headers=headers)
    assert res.status_code == 401

def test_jwt_valid_token_allows_access(client):
    token = jwt.encode({"username": "admin", "role": "admin"}, AUTH_SECRET_KEY, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/bookings", headers=headers)
    assert res.status_code == 200

def test_missing_role_header_returns_401(client):
    res = client.get("/bookings", headers={"X-User-Name": "any"})
    assert res.status_code == 401
    assert "missing X-User-Role" in res.json["error"]

def test_jwt_expired_token(client):
    import jwt, time
    token = jwt.encode(
        {"username": "expired", "role": "regular", "exp": int(time.time()) - 10},
        "dev-secret-key-change-me",
        algorithm="HS256"
    )
    res = client.get("/bookings", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    assert "missing X-User-Role header" in res.json["error"]


def test_update_booking_not_found(client):
    res = client.put(
        "/bookings/9999",
        json={"date": "2025-01-02", "start_time": "10:00", "end_time": "11:00"},
        headers={"X-User-Role": "admin", "X-User-Name": "admin"}
    )
    assert res.status_code == 404

def test_update_booking_room_not_found(client):
    uid = seed_user("Lina", "lina123", "lina@aub.edu.lb", "regular")
    rid = seed_room()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-05', '09:00', '10:00', 'active');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.execute("DELETE FROM rooms WHERE id = ?", (rid,))
    conn.commit()
    conn.close()

    res = client.put(
        f"/bookings/{booking_id}",
        json={"date": "2025-01-06", "start_time": "10:00", "end_time": "11:00"},
        headers={"X-User-Role": "regular", "X-User-Name": "lina123"}
    )
    assert res.status_code == 404
    assert "room not found" in res.json["error"]

def test_cancel_booking_already_cancelled(client):
    uid = seed_user("Nada", "nada123", "nada@aub.edu.lb", "regular")
    rid = seed_room()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, room_id, date, start_time, end_time, status)
        VALUES (?, ?, '2025-01-07', '08:00', '09:00', 'cancelled');
    """, (uid, rid))
    booking_id = cur.lastrowid
    conn.commit()
    conn.close()

    res = client.delete(
        f"/bookings/{booking_id}",
        headers={"X-User-Role": "regular", "X-User-Name": "nada123"}
    )
    assert res.status_code == 200
    assert res.json["message"] == "booking already cancelled"

def test_create_booking_missing_fields(client):
    uid = seed_user("Rami", "rami123", "rami@aub.edu.lb", "regular")
    rid = seed_room()

    payload = {
        "user_id": uid,
        "room_id": rid,
        "date": "2025-01-10",
        "start_time": "10:00"
    }

    res = client.post(
        "/bookings",
        json=payload,
        headers={"X-User-Role": "regular", "X-User-Name": "rami123"}
    )
    assert res.status_code == 400
    assert "missing" in res.json["error"]

def test_room_availability_missing_fields(client):
    rid = seed_room()
    res = client.post(
        f"/rooms/{rid}/availability",
        json={"date": "2025-01-10"},
        headers={"X-User-Role": "regular", "X-User-Name": "any"}
    )
    assert res.status_code == 400
    assert "required" in res.json["error"]

def test_room_availability_invalid_date(client):
    rid = seed_room()
    res = client.post(
        f"/rooms/{rid}/availability",
        json={"date": "10-10-2025", "start_time": "10:00", "end_time": "11:00"},
        headers={"X-User-Role": "regular", "X-User-Name": "any"}
    )
    assert res.status_code == 400

def test_room_availability_room_not_found(client):
    res = client.post(
        "/rooms/9999/availability",
        json={"date": "2025-01-10", "start_time": "10:00", "end_time": "11:00"},
        headers={"X-User-Role": "regular", "X-User-Name": "any"}
    )
    assert res.status_code == 404
    assert "room not found" in res.json["error"]

def test_options_bypasses_auth(client):
    res = client.options("/bookings")
    assert res.status_code in (200, 204)

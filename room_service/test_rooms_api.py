
# room_service/test_rooms_api.py
# room_service/test_rooms_api.py
# room_service/test_rooms_api.py

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))  # make local database.py importable

import json
import database
from app import app

#old bad
#def wipe_rooms_table():
   # """Small helper: removes all rows from rooms before a test."""
  #  database.make_rooms_table_if_missing()
  #  conn = database.get_db_connection()
 #   cur = conn.cursor()
  #  cur.execute("delete from rooms")
  #  conn.commit()
  #  conn.close()
    # Create table once when tests import this file
database.make_rooms_table_if_missing()

def wipe_rooms_table():
    """Small helper: removes all rows from rooms before a test."""
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("delete from rooms")
    conn.commit()
    conn.close()

def test_create_room_ok():
    wipe_rooms_table()
    client = app.test_client()

    body = {
        "name": "KaakeLounge",
        "capacity": 10,
        "equipment": "projector, whiteboard, saj",
        "location": "3rd floor - Hamra view",
        "status": "available",
    }

    resp = client.post(
        "/rooms",
        data=json.dumps(body),
        content_type="application/json",
    )

    assert resp.status_code == 201
    data = resp.get_json()
    assert data["message"] == "room created"
    assert data["room"]["name"] == "KaakeLounge"
    assert data["room"]["capacity"] == 10



def test_create_room_missing_field():
    wipe_rooms_table()
    client = app.test_client()
    body = {
        "capacity": 8,
        "equipment": "tv, nescafe",
        "location": "2nd floor - Man2oushe corner",
        "status": "available",
    }

    resp = client.post(
        "/rooms",
        data=json.dumps(body),
        content_type="application/json",
    )

    assert resp.status_code == 400

def test_get_all_rooms_returns_both():
    wipe_rooms_table()
    client = app.test_client()
    room1 = {
        "name": "MiniMankoushe",
        "capacity": 4,
        "equipment": "tv",
        "location": "1st floor - Gemmayze",
        "status": "available",
    }
    room2 = {
        "name": "BigMansaf",
        "capacity": 20,
        "equipment": "projector",
        "location": "3rd floor - Downtown",
        "status": "booked",
    }

    client.post("/rooms", data=json.dumps(room1), content_type="application/json")
    client.post("/rooms", data=json.dumps(room2), content_type="application/json")
    resp = client.get("/rooms")
    assert resp.status_code == 200
    data = resp.get_json()
    names = {r["name"] for r in data}
    assert "MiniMankoushe" in names
    assert "BigMansaf" in names



def test_get_room_by_name_found_and_not_found():
    wipe_rooms_table()
    client = app.test_client()

    body = {
        "name": "BeirutFocus",
        "capacity": 6,
        "equipment": "screen, coffee machine",
        "location": "2nd floor - Corniche side",
        "status": "available",
    }
    client.post("/rooms", data=json.dumps(body), content_type="application/json")
    # found
    resp_ok = client.get("/rooms/BeirutFocus")
    assert resp_ok.status_code == 200
    info = resp_ok.get_json()
    assert info["name"] == "BeirutFocus"

    # not found
    resp_missing = client.get("/rooms/NoSuchRoomHabibi")
    assert resp_missing.status_code == 404


def test_get_available_rooms_filters_and_skips_booked():
    wipe_rooms_table()
    client = app.test_client()
    majlis_room = {
        "name": "MajlisRoom",
        "capacity": 12,
        "equipment": "projector, whiteboard, Arabic coffee",
        "location": "3rd floor - Achrafieh",
        "status": "available",
    }
    tiny_room = {
        "name": "TinyTaybe",
        "capacity": 3,
        "equipment": "screen",
        "location": "1st floor - Byblos",
        "status": "available",
    }
    booked_room = {
        "name": "BookedSouk",
        "capacity": 15,
        "equipment": "projector",
        "location": "3rd floor - Souk Beirut",
        "status": "booked",
    }

    client.post("/rooms", data=json.dumps(majlis_room), content_type="application/json")
    client.post("/rooms", data=json.dumps(tiny_room), content_type="application/json")
    client.post("/rooms", data=json.dumps(booked_room), content_type="application/json")
    # ask for rooms with capacity >= 10 and projectors
    resp = client.get("/rooms/available?min_capacity=10&equipment=projector")
    assert resp.status_code == 200
    data = resp.get_json()
    names = {r["name"] for r in data}
    # available + matching filters
    assert "MajlisRoom" in names
    # booked room should NOT appear even though it matches capacity/projector
    assert "BookedSouk" not in names
    # tiny room too small
    assert "TinyTaybe" not in names


def test_update_room_changes_capacity_and_status():
    wipe_rooms_table()
    client = app.test_client()

    body = {
        "name": "TeamZa3tar",
        "capacity": 6,
        "equipment": "tv, whiteboard",
        "location": "2nd floor - Hamra",
        "status": "available",
    }
    client.post("/rooms", data=json.dumps(body), content_type="application/json")


    update_body = {
        "capacity": 8,
        "status": "booked",
    }
    resp = client.put(
        "/rooms/TeamZa3tar",
        data=json.dumps(update_body),
        content_type="application/json",
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["room"]["capacity"] == 8
    assert data["room"]["status"] == "booked"
    # and check status endpoint
    status_resp = client.get("/rooms/TeamZa3tar/status")
    assert status_resp.status_code == 200
    status_data = status_resp.get_json()
    assert status_data["status"] == "booked"



def test_delete_room_then_get_404():
    wipe_rooms_table()
    client = app.test_client()
    body = {
        "name": "DeleteMeYa3ne",
        "capacity": 5,
        "equipment": "tv, wifi",
        "location": "1st floor - Tripoli",
        "status": "available",
    }
    client.post("/rooms", data=json.dumps(body), content_type="application/json")
    resp_del = client.delete("/rooms/DeleteMeYa3ne")
    assert resp_del.status_code == 200
    resp_after = client.get("/rooms/DeleteMeYa3ne")
    assert resp_after.status_code == 404
# the follwing is added to try to make it better in terms of coverage 
def test_create_room_duplicate_name():
    """Calling POST /rooms twice with same name should give 400 on the second call."""
    wipe_rooms_table()
    client = app.test_client()

    body = {
        "name": "DuplicateRoom",
        "capacity": 10,
        "equipment": "projector",
        "location": "4th floor",
        "status": "available",
    }

    # first create is OK
    first = client.post("/rooms", data=json.dumps(body), content_type="application/json")
    assert first.status_code == 201

    # second with same name should hit the 'room already exists' branch
    second = client.post("/rooms", data=json.dumps(body), content_type="application/json")
    assert second.status_code == 400


def test_update_room_not_found():
    """PUT /rooms/<name> on a non-existing room should return 404."""
    wipe_rooms_table()
    client = app.test_client()

    resp = client.put(
        "/rooms/NoSuchRoom",
        data=json.dumps({"capacity": 99}),
        content_type="application/json",
    )
    assert resp.status_code == 404


def test_delete_room_not_found():
    """Del /rooms/<name> on a non-existing room should return 404."""
    wipe_rooms_table()
    client = app.test_client()
    resp = client.delete("/rooms/NoSuchRoom")
    assert resp.status_code == 404


def test_get_room_status_not_found():
    """GET /rooms/<name>/status on a non-existing room should return 404."""
    wipe_rooms_table()
    client = app.test_client()
    resp = client.get("/rooms/NoSuchRoom/status")
    assert resp.status_code == 404


def test_create_room_bad_payload():
    """POST /rooms with invalid JSON or empty body should hit the 400 path."""
    wipe_rooms_table()
    client = app.test_client()
    resp = client.post("/rooms", data="{}", content_type="application/json")
    assert resp.status_code == 400

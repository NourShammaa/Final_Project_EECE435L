import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))  # make local database.py importable

import database
from app import app
#old version which gave me less coverage
#def clean_users_table():

   # conn = database.get_db_connection()
  #  cur = conn.cursor()
   # cur.execute("delete from users")
   # conn.commit()
   # conn.close()
def clean_users_table():
    """Clear the users table before each test and make sure it exists."""
    # make_users_table_if_missing gets covered here
    database.make_users_table_if_missing()

    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("delete from users")
    conn.commit()
    conn.close()

def test_register_user_success():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "name": "test user",
        "username": "testuser",
        "email": "test@example.com",
        "password": "secret",
        "role": "regular",
    }

    response = client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["message"] == "user registered"
    assert data["user"]["username"] == "testuser"

def test_register_user_missing_field():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "username": "nouna",
        "email": "nour.shammaa@example.com",
        "password": "makhasknn",
        "role": "regular",
    }

    response = client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "missing" in data["error"]

def test_login_success():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "name": "riwa",
        "username": "roro",
        "email": "riro@example.com",
        "password": "RORARI",
        "role": "admin",
    }
    client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )

    login_body = {"username": "roro", "password": "RORARI"}
    response = client.post(
        "/users/login",
        data=json.dumps(login_body),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["message"] == "login ok"
    assert data["user"]["username"] == "roro"

def test_login_wrong_password():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "name": "Tala",
        "username": "touti",
        "email": "taltol@example.com",
        "password": "titi",
        "role": "admin",
    }
    client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )

    login_body = {"username": "touti", "password": "wrong"}
    response = client.post(
        "/users/login",
        data=json.dumps(login_body),
        content_type="application/json",
    )

    assert response.status_code == 401

def test_get_all_users_returns_list():
    clean_users_table()
    client = app.test_client()

    first = {
        "name": "nour",
        "username": "nour",
        "email": "nour@example.com",
        "password": "abc123",
        "role": "regular",
    }
    second = {
        "name": "hadi",
        "username": "hadi",
        "email": "hadi@example.com",
        "password": "def456",
        "role": "admin",
    }

    client.post("/users/register", data=json.dumps(first), content_type="application/json")
    client.post("/users/register", data=json.dumps(second), content_type="application/json")

    response = client.get("/users")
    assert response.status_code == 200
    data = response.get_json()
    usernames = {u["username"] for u in data}
    assert "nour" in usernames
    assert "hadi" in usernames

def test_get_user_by_username_found_and_not_found():
    clean_users_table()
    client = app.test_client()

    user_body = {
        "name": "someone",
        "username": "somebody",
        "email": "somebody@example.com",
        "password": "pwd",
        "role": "regular",
    }
    client.post(
        "/users/register",
        data=json.dumps(user_body),
        content_type="application/json",
    )

    resp_ok = client.get("/users/somebody")
    assert resp_ok.status_code == 200
    data_ok = resp_ok.get_json()
    assert data_ok["username"] == "somebody"

    resp_missing = client.get("/users/unknownuser")
    assert resp_missing.status_code == 404

def test_update_user_changes_email_and_role():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "name": "update me",
        "username": "upuser",
        "email": "old@example.com",
        "password": "pass",
        "role": "regular",
    }
    client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )

    update_body = {
        "email": "new@example.com",
        "role": "admin",
    }
    response = client.put(
        "/users/upuser",
        data=json.dumps(update_body),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["user"]["email"] == "new@example.com"
    assert data["user"]["role"] == "admin"

def test_delete_user_removes_them():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "name": "delete me",
        "username": "delme",
        "email": "del@example.com",
        "password": "pass",
        "role": "regular",
    }
    client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )

    resp_del = client.delete("/users/delme")
    assert resp_del.status_code == 200

    resp_after = client.get("/users/delme")
    assert resp_after.status_code == 404

def test_get_user_bookings_returns_empty_list():
    clean_users_table()
    client = app.test_client()

    register_body = {
        "name": "booker",
        "username": "booker",
        "email": "booker@example.com",
        "password": "pass",
        "role": "regular",
    }
    client.post(
        "/users/register",
        data=json.dumps(register_body),
        content_type="application/json",
    )
def test_register_user_duplicate_username():
    """Try registering the same username twice and expect a 400 on the second time."""
    clean_users_table()
    client = app.test_client()

    body = {
        "name": "nour",
        "username": "nour",
        "email": "nour@example.com",
        "password": "abc123",
        "role": "regular",
    }
    # first register should be ok
    client.post(
        "/users/register",
        data=json.dumps(body),
        content_type="application/json",
    )

    # second register with same username should fail
    body2 = {
        "name": "nour again",
        "username": "nour",  # same username
        "email": "other@example.com",
        "password": "xyz789",
        "role": "admin",
    }
    resp = client.post(
        "/users/register",
        data=json.dumps(body2),
        content_type="application/json",
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert "username already used" in data["error"]
    

def test_login_missing_fields():
    """call login without password and expect a 400 error."""
    clean_users_table()
    client = app.test_client()

    resp = client.post(
        "/users/login",
        data=json.dumps({"username": "someone"}),  # missing password
        content_type="application/json",
    )

    assert resp.status_code == 400
    data = resp.get_json()
    assert "username and password are required" in data["error"]

def test_update_user_not_found():
    """try update a user that does not exist and expect 404."""
    clean_users_table()
    client = app.test_client()

    body = {"email": "doesnt@exist.com"}
    resp = client.put(
        "/users/not_there",
        data=json.dumps(body),
        content_type="application/json",
    )

    assert resp.status_code == 404
def test_delete_user_not_found():
    """try deleting a non-existing user and expect 404."""
    clean_users_table()
    client = app.test_client()

    resp = client.delete("/users/ghost")
    assert resp.status_code == 404
def test_get_user_bookings_user_not_found():
    """ask for bookings of a non-existing user and expect 404."""
    clean_users_table()
    client = app.test_client()

    resp = client.get("/users/ghost/bookings")
    assert resp.status_code == 404

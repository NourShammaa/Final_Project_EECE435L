from memory_profiler import memory_usage
import json
import os
import sys

# Make sure we can import local app/database even if run from project root
sys.path.insert(0, os.path.dirname(__file__))

import database
from app import app


def exercise_users_api():
    """Exercise main users endpoints with realistic RBAC headers."""
    database.make_users_table_if_missing()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("delete from users")
    conn.commit()
    conn.close()

    client = app.test_client()

    # Create some regular users (register is open, no headers needed)
    for pos in range(5):
        body = {
            "name": f"user {pos}",
            "username": f"user{pos}",
            "email": f"user{pos}@example.com",
            "password": "secret",
            "role": "regular",
        }
        client.post(
            "/users/register",
            data=json.dumps(body),
            content_type="application/json",
        )

    # Log in a couple of them (login is open)
    client.post(
        "/users/login",
        data=json.dumps({"username": "user0", "password": "secret"}),
        content_type="application/json",
    )
    client.post(
        "/users/login",
        data=json.dumps({"username": "user1", "password": "secret"}),
        content_type="application/json",
    )

    # RBAC headers
    admin_headers = {"X-User-Name": "adminuser", "X-User-Role": "admin"}
    user0_headers = {"X-User-Name": "user0", "X-User-Role": "regular"}

    # list all users -> admin / auditor only
    client.get("/users", headers=admin_headers)

    # user0 views own profile
    client.get("/users/user0", headers=user0_headers)

    # user0 updates their own role (allowed by our RBAC rule)
    client.put(
        "/users/user0",
        data=json.dumps({"role": "admin"}),
        content_type="application/json",
        headers=user0_headers,
    )

    # user0 views own bookings (allowed)
    client.get("/users/user0/bookings", headers=user0_headers)

    # admin deletes user1 (only admin allowed)
    client.delete("/users/user1", headers=admin_headers)


def main():
    mem_usage = memory_usage(
        (exercise_users_api, (), {}),
        interval=0.1,
        retval=False,
    )
    print("Memory samples (MiB):", mem_usage)
    print("Peak memory (MiB):", max(mem_usage))


if __name__ == "__main__":
    main()

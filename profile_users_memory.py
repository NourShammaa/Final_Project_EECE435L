from memory_profiler import memory_usage
import json

from app import app
import database

def exercise_users_api():

    database.make_users_table_if_missing()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("delete from users")
    conn.commit()
    conn.close()

    client = app.test_client()

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

    client.get("/users")
    client.get("/users/user0")
    client.put(
        "/users/user0",
        data=json.dumps({"role": "admin"}),
        content_type="application/json",
    )
    client.get("/users/user0/bookings")
    client.delete("/users/user1")

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



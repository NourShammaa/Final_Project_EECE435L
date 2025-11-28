from memory_profiler import memory_usage
import json
import os
import sys

# Ensure local import works
sys.path.insert(0, os.path.dirname(__file__))

# Import reviews service modules
import database
from app import app


def exercise_reviews_api():
    """Exercise the main review endpoints realistically."""
    print("💡 Resetting reviews table...")

    # Reset only the reviews table (users & rooms come from other services)
    database.make_reviews_table_if_missing()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM reviews;")
    conn.commit()
    conn.close()

    client = app.test_client()

    # Prepare some fake IDs (assuming they exist in shared DB)
    user_regular = 401
    user_admin = 999
    room_id = 421

    # RBAC headers (NO JWT — fallback headers)
    regular_headers = {
        "X-User-Name": "riwaelkari",
        "X-User-Role": "regular",
    }
    admin_headers = {
        "X-User-Name": "adminuser",
        "X-User-Role": "admin",
    }
    moderator_headers = {
        "X-User-Name": "modteam",
        "X-User-Role": "moderator",
    }

    # ---- Public endpoint ----
    client.get(f"/reviews/room/{room_id}")

    # ---- Submit a few reviews ----
    for i in range(5):
        review = {
            "user_id": user_regular,
            "room_id": room_id,
            "rating": 7,
            "comment": f"Test review {i}",
        }
        client.post(
            "/reviews",
            data=json.dumps(review),
            content_type="application/json",
            headers=regular_headers,
        )

    # ---- Update a review ----
    client.put(
        "/reviews/1",
        data=json.dumps({"rating": 9, "comment": "Updated review"}),
        content_type="application/json",
        headers=regular_headers,
    )

    # ---- Moderator deletes a review ----
    client.delete("/reviews/2", headers=moderator_headers)

    # ---- Admin flags a review ----
    client.put("/reviews/3/flag", headers=admin_headers)

    print("✔ Finished exercising reviews API")


def main():
    mem_usage = memory_usage(
        (exercise_reviews_api, (), {}),
        interval=0.1,
        retval=False,
    )
    print("Memory samples (MiB):", mem_usage)
    print("Peak memory (MiB):", max(mem_usage))


if __name__ == "__main__":
    main()

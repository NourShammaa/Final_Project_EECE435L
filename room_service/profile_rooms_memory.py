from memory_profiler import memory_usage
import json
import os
import sys

# Make sure we can import local app/database even if run from project root
sys.path.insert(0, os.path.dirname(__file__))

import database
from app import app


def exercise_rooms_api():
    """Call the main endpoints to simulate normal usage."""
    database.make_rooms_table_if_missing()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("delete from rooms")
    conn.commit()
    conn.close()

    client = app.test_client()

    # create a few rooms
    for i in range(5):
        body = {
            "name": f"PerfRoom{i}",
            "capacity": 5 + i,
            "equipment": "projector, whiteboard",
            "location": "3rd floor",
            "status": "available",
        }
        client.post(
            "/rooms",
            data=json.dumps(body),
            content_type="application/json",
        )

    # hit endpoints
    client.get("/rooms")
    client.get("/rooms/PerfRoom0")
    client.get("/rooms/available?min_capacity=6&equipment=projector")
    client.put(
        "/rooms/PerfRoom0",
        data=json.dumps({"status": "booked"}),
        content_type="application/json",
    )
    client.get("/rooms/PerfRoom0/status")
    client.delete("/rooms/PerfRoom1")


def main():
    mem_usage = memory_usage(
        (exercise_rooms_api, (), {}),
        interval=0.1,
        retval=False,
    )
    print("Memory samples (MiB):", mem_usage)
    print("Peak memory (MiB):", max(mem_usage))


if __name__ == "__main__":
    main()

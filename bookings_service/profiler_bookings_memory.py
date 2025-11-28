from memory_profiler import memory_usage
import json
import os
import sys

# Ensure local imports work
sys.path.insert(0, os.path.dirname(__file__))

import database
from app import app


def exercise_bookings_api():
    """Exercise the main booking flows realistically for memory profiling."""

    print("💡 Resetting bookings table...")

    # Reset ONLY bookings table (users & rooms come from other services)
    database.make_bookings_table_if_missing()
    conn = database.get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM bookings;")
    conn.commit()
    conn.close()

    client = app.test_client()

    # existing shared IDs (
    user_regular = 401      # riwa
    user_facman  = 402      # ali 
    user_admin   = 999      # admin
    room_1       = 421      # Nicely Hall
    room_2       = 422      # West Hall

    # ---- RBAC headers (fallback X-User-* headers, no JWT) ----
    regular_headers = {
        "X-User-Name": "riwaelkari",
        "X-User-Role": "regular",
    }
    facman_headers = {
        "X-User-Name": "facman",
        "X-User-Role": "facility_manager",
    }
    admin_headers = {
        "X-User-Name": "adminuser",
        "X-User-Role": "admin",
    }
    auditor_headers = {
        "X-User-Name": "auditguy",
        "X-User-Role": "auditor",
    }

    # Get all bookings (admin/facman/auditor) 
    client.get("/bookings", headers=admin_headers)
    client.get("/bookings", headers=auditor_headers)

    #  Regular user creates bookings 
    for i in range(3):
        payload = {
            "user_id": user_regular,
            "room_id": room_1,
            "date": f"2025-12-0{i+1}",
            "start_time": "10:00",
            "end_time": "11:00",
        }
        client.post(
            "/bookings",
            data=json.dumps(payload),
            content_type="application/json",
            headers=regular_headers,
        )

    #  Facility manager creates booking 
    client.post(
        "/bookings",
        data=json.dumps({
            "user_id": user_facman,
            "room_id": room_2,
            "date": "2025-12-05",
            "start_time": "09:00",
            "end_time": "10:00",
        }),
        content_type="application/json",
        headers=facman_headers,
    )

    # Admin creates a booking 
    client.post(
        "/bookings",
        data=json.dumps({
            "user_id": user_admin,
            "room_id": room_1,
            "date": "2025-12-10",
            "start_time": "14:00",
            "end_time": "15:00",
        }),
        content_type="application/json",
        headers=admin_headers,
    )

    # Get bookings for specific user 
    client.get(f"/bookings/user/{user_regular}", headers=regular_headers)
    client.get(f"/bookings/user/{user_regular}", headers=admin_headers)

    # Update a booking (regular can only update own) 
    client.put(
        "/bookings/1",
        data=json.dumps({
            "date": "2025-12-01",
            "start_time": "12:00",
            "end_time": "13:00"
        }),
        content_type="application/json",
        headers=regular_headers,
    )

    # Admin updates ANY booking 
    client.put(
        "/bookings/2",
        data=json.dumps({
            "date": "2025-12-02",
            "start_time": "17:00",
            "end_time": "18:00"
        }),
        content_type="application/json",
        headers=admin_headers,
    )

    #  Regular cancels their own booking
    client.delete("/bookings/1", headers=regular_headers)

    # Admin cancels booking 
    client.delete("/bookings/2", headers=admin_headers)

    # check availability
    client.post(
        f"/rooms/{room_1}/availability",
        json={"date": "2025-12-01", "start_time": "12:00", "end_time": "13:00"},
    )

    print("✔ Finished exercising bookings API")


def main():
    mem_usage = memory_usage(
        (exercise_bookings_api, (), {}),
        interval=0.1,
        retval=False,
    )
    print("Memory samples (MiB):", mem_usage)
    print("Peak memory (MiB):", max(mem_usage))


if __name__ == "__main__":
    main()

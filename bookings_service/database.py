"""
This file is for database related code for the bookings service. 
Getting db connection, creating bookings table if it's not there, and other db related functions which will be used by app.py.
"""

import sqlite3
import os

db_file_name = "database.db"


def get_db_connection():
    """This fct opens a connection to the bookings database and returns it.
    It uses sqlite3.Row so columns can be accessed by name. It also enables foreign keys.
    """
    conn = sqlite3.connect(db_file_name)
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("pragma foreign_keys = on;")
    return conn


def make_bookings_table_if_missing():
    """This fct will create the bookings table if it does not already exist."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        create table if not exists bookings (
            id integer primary key autoincrement,

            -- user who made the booking (references users.id)
            user_id integer not null,

            -- room being booked (references rooms.id)
            room_id integer not null,

            date text not null,          -- booking date as YYYY-MM-DD
            start_time text not null,    -- start time as HH:MM
            end_time text not null,      -- end time as HH:MM

            status text not null 
                default 'active'
                check (status in ('active', 'cancelled', 'updated')),

            created_at text default current_timestamp,   -- when the booking was created
            updated_at text default current_timestamp,   -- when the booking was last updated

            foreign key(user_id) references users(id),
            foreign key(room_id) references rooms(id)
        );
        """
    )

    conn.commit()
    conn.close()


# Create the table automatically
if not os.path.exists(db_file_name):
    make_bookings_table_if_missing()

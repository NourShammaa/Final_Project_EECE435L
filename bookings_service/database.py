"""
This file has all the database related code for the bookings service.
It manages the database connection, creates the bookings table when needed,
and provides helper functions that app.py depends on.
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
db_file_name = os.path.join(ROOT_DIR, "database.db")


def get_db_connection():
    """This fct opens a connection to the bookings database.

    It configures sqlite3 so rows can be accessed by column name 
    and enables foreign-key constraints.

    Returns
    sqlite3.Connection
        A ready to use SQLite connection.
    """
    conn = sqlite3.connect(db_file_name)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on;")
    return conn


def make_bookings_table_if_missing():
    """This fct creates the bookings table if it does not already exist.

    It is usually called once at service startup so the rest of the
    application can safely assume table is there.

    Returns
    None
    """
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

            created_at text default current_timestamp,
            updated_at text default current_timestamp,

            foreign key(user_id) references users(id),
            foreign key(room_id) references rooms(id)
        );
        """
    )

    conn.commit()
    conn.close()


def get_all_bookings():
    """This fct gets all bookings stored in the database.

    The returned list is sorted by date and starting time to make it easier for the caller to display or process.

    Returns
    list of sqlite3.Row
        All booking records.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        select * from bookings
        order by date, start_time;
        """
    )

    rows = cur.fetchall()
    conn.close()
    return rows


def create_booking(user_id, room_id, date, start_time, end_time):
    """This fct inserts a new booking into the database.

    Parameters
    user_id : int
        ID of the user making the booking.
    room_id : int
        ID of the room being booked.
    date : str
        Booking date in YYYY-MM-DD format.
    start_time : str
        Start time in HH:MM format.
    end_time : str
        End time in HH:MM format.

    Returns
    int
        The ID of the newly created booking.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        insert into bookings (user_id, room_id, date, start_time, end_time)
        values (?, ?, ?, ?, ?);
        """,
        (user_id, room_id, date, start_time, end_time),
    )

    conn.commit()
    booking_id = cur.lastrowid
    conn.close()
    return booking_id


def update_booking(booking_id, date, start_time, end_time):
    """This fct updates the date and/or time of an existing booking.

    It is VIP to check availability first using is_room_available.

    Parameters
    booking_id : int
        ID of the booking to update.
    date : str
        New booking date.
    start_time : str
        New start time.
    end_time : str
        New end time.

    Returns
    None
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        update bookings
        set date = ?, start_time = ?, end_time = ?, updated_at = current_timestamp
        where id = ?;
        """,
        (date, start_time, end_time, booking_id),
    )

    conn.commit()
    conn.close()


def cancel_booking(booking_id):
    """This fct marks a booking as cancelled.

    Parameters
    booking_id : int
        ID of the booking to cancel.

    Returns
    None
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        update bookings
        set status = 'cancelled', updated_at = current_timestamp
        where id = ?;
        """,
        (booking_id,),
    )

    conn.commit()
    conn.close()


def get_bookings_for_user(user_id):
    """This fct gets all the bookings that were made by a specific user whos user id is given.

    It returns both active and cancelled bookings so we can see full booking history.

    Parameters
    ----------
    user_id : int
        The user whose bookings are requested.

    Returns
    -------
    list of sqlite3.Row
        All bookings made by this user.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        select * from bookings
        where user_id = ?
        order by date, start_time;
        """,
        (user_id,),
    )

    rows = cur.fetchall()
    conn.close()
    return rows


def is_room_available(room_id, date, start_time, end_time):
    """This fct checks whether a room is free during a specific time window.

    It looks for overlapping active bookings on the same date.

    Parameters
    room_id : int
        Room to check.
    date : str
        Booking date in YYYY-MM-DD format.
    start_time : str
        Proposed start time.
    end_time : str
        Proposed end time.

    Returns
    bool
        True if the room is available, False if it is already booked.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        select * from bookings
        where room_id = ?
          and date = ?
          and status = 'active'
          and (
                (start_time < ? and end_time > ?)
              );
        """,
        (room_id, date, end_time, start_time),
    )

    conflict = cur.fetchone()
    conn.close()

    return conflict is None


# Create the table automatically
if not os.path.exists(db_file_name):
    make_bookings_table_if_missing()

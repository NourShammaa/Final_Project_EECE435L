"""
This part of the project is the databse of the rooms service.
"""

import sqlite3

import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
db_file_name = os.path.join(BASE_DIR, "database.db")

def get_db_connection():
    """open a connection to the rooms database and return it.
    connection uses ``sqlite3.Row`` so we can access columns by name.
    """
    conn = sqlite3.connect(db_file_name)
    conn.row_factory = sqlite3.Row
    return conn


def make_rooms_table_if_missing():
    """create the ``rooms`` table if not already exist.
    called once at begining so the other code can assume the table is there.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        create table if not exists rooms (
            id integer primary key autoincrement,
            name text not null unique,
            capacity integer not null,
            equipment text not null,
            location text not null,
            status text not null
        );
        """
    )

    conn.commit()
    conn.close()



def insert_room(name, capacity, equipment, location, status="available"):
    """insert a new room and return it as a dict.
    it takes as parameters: name as in name of the room ( unique),capacity(max nb of ppl), equipment (comma separated list), location(floor, building etc), status(available/booked)
    it returns newly inserted row as a dict, or ``None`` if something went wrong.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        insert into rooms (name, capacity, equipment, location, status)
        values (?, ?, ?, ?, ?)
        """,
        (name, capacity, equipment, location, status),
    )
    conn.commit()
    new_id = cur.lastrowid

    cur.execute("select * from rooms where id = ?", (new_id,))
    row = cur.fetchone()

    conn.close()
    return dict(row) if row else None


def find_room_by_name(name):
    """look up one room by its name."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("select * from rooms where name = ?", (name,))
    row = cur.fetchone()

    conn.close()
    return dict(row) if row else None


def list_all_rooms():
    """return all rooms as a list of dicts."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("select * from rooms")
    rows = cur.fetchall()

    conn.close()
    return [dict(r) for r in rows]


def update_room_row(name, new_capacity, new_equipment, new_location, new_status):
    """update a room row and return the updated row. takes in as parameters: name of the room to update, new capacity, new equipment string, new location string, new status string.
    then returns Updated room row, or ``None`` if the room does not exist.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        update rooms
        set capacity = ?, equipment = ?, location = ?, status = ?
        where name = ?
        """,
        (new_capacity, new_equipment, new_location, new_status, name),
    )

    conn.commit()

    cur.execute("select * from rooms where name = ?", (name,))
    row = cur.fetchone()

    conn.close()
    return dict(row) if row else None


def delete_room_row(name):
    """delete a room row by name.
    it simply returns number of deleted rows (0 if none matched).
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("delete from rooms where name = ?", (name,))
    conn.commit()
    rows_deleted = cur.rowcount

    conn.close()
    return rows_deleted


def search_available_rooms(min_capacity=None, location=None, equipment_contains=None):
    """searchs for available rooms with simple filters. the following filters are optional: min_capacity(rooms with capacity >= this value), location(substring that must appear in the location), equipment_contains(substring that must appear in the equipment).
    Only rooms with status = "available" are returned.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    query = "select * from rooms where status = 'available'"
    params = []

    if min_capacity is not None:
        query += " and capacity >= ?"
        params.append(min_capacity)

    if location:
        query += " and location like ?"
        params.append(f"%{location}%")

    if equipment_contains:
        query += " and equipment like ?"
        params.append(f"%{equipment_contains}%")

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows]

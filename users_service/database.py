# users_service/database.py
"""This part of the project is for talking to the users SQLite database.
"""

import sqlite3
import os
from datetime import datetime
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

DEFAULT_DB_FILE = os.path.join(BASE_DIR, "database.db")

DB_FILE = os.environ.get("USERS_DB_PATH", DEFAULT_DB_FILE)
def get_db_connection():
    """open a connection to the users database and return it.
    connection uses ``sqlite3.Row`` so we can access columns by name.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def make_users_table_if_missing():
    """Create the ``users`` table if it does not already exist.

    just called once at startup so the rest of the code can assume  that the table is there and ready to use.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        create table if not exists users (
            id integer primary key autoincrement,
            name text not null,
            username text not null unique,
            email text not null unique,
            role text not null,
            password_hash text not null,
            created_at text not null
        );
        """
    )

    conn.commit()
    conn.close()


def insert_user(name, username, email, role, password_hash):
    """Insert a new user row and return it as a dict.
    it takes  as parameters:
    name : str
        Full name of the user.
    username : str
        Chosen username (must be unique).
    email : str
        Email address (must be unique).
    role : str
        Role string, for example ``"admin"`` or ``"regular"``.
    password_hash : str
        Hashed password, already processed by the caller.
    Returns
    The newly inserted row as a dict, or ``None`` if something went wrong.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    when_str = datetime.utcnow().isoformat()

    cur.execute(
        """
        insert into users (name, username, email, role, password_hash, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        (name, username, email, role, password_hash, when_str),
    )
    conn.commit()
    new_id = cur.lastrowid

    cur.execute("select * from users where id = ?", (new_id,))
    row = cur.fetchone()

    conn.close()
    return dict(row) if row else None

def find_user_by_username(username):
    """Look up one user by username.
    takes as parameters
    username : str
        Username to search for.
    Returns
     Matching user row as a dict, or ``None`` if not found.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("select * from users where username = ?", (username,))
    row = cur.fetchone()

    conn.close()
    return dict(row) if row else None

def find_user_by_email(email):
    """Look up one user by email address.
    takes as parameters:
    email : str
        Email address to search for.
    Returns
        Matching user row as a dict, or ``None`` if not found.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("select * from users where email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def list_all_users():
    """Return all users in the database as a list of dicts."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("select * from users")
    rows = cur.fetchall()

    conn.close()
    return [dict(r) for r in rows]


def update_user_row(username, new_name, new_email, new_role, new_password_hash=None):
    """Update a user row and return the updated row.
    takes as parameters
    username : str
        Username of the user to update.
    new_name : str
        New name to store.
    new_email : str
        New email to store.
    new_role : str
        New role to store.
    new_password_hash : str, optional
        New hashed password. If ``None``, the password is not changed.

    Returns
        Updated user row as a dict, or ``None`` if something went wrong.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        update users
        set name = ?, email = ?, role = ?
        where username = ?
        """,
        (new_name, new_email, new_role, username),
    )

    # only touch the password if a new hash was provided
    if new_password_hash is not None:
        cur.execute(
            "update users set password_hash = ? where username = ?",
            (new_password_hash, username),
        )
    conn.commit()

    cur.execute("select * from users where username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_user_row(username):
    """Delete a user row by username.
    takes as parameters
    username : str
        Username of the user to remove.
    Returns
    Number of rows deleted (0 if nothing matched).
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("delete from users where username = ?", (username,))
    conn.commit()
    rows_deleted = cur.rowcount

    conn.close()
    return rows_deleted

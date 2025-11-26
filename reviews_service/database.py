"""
This file is for database related code for the reviews service.
Getting db connection, creating reviews table if it's not there,
and other db related functions which will be used by app.py.
"""


import sqlite3
import os
import os

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(ROOT_DIR, "database.db")

DB_NAME = os.path.join(ROOT_DIR, "database.db")


def get_connection():
    """Open a connection to the unified reviews database.
    It uses sqlite3.Row so columns can be accessed by name.
    Foreign-key constraints are enabled for safety.

    Returns
    sqlite3.Connection
        An active SQLite connection with row access by column name.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    # This will enable FK constraints 
    conn.execute("pragma foreign_keys = on;")
    return conn


def make_reviews_table_if_missing():
    """Create the ``reviews`` table if it does not already exist.
    
    Takes no parameters.

    Returns
    None
        Simply ensures the table exists in the database.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        create table if not exists reviews (
            id integer primary key autoincrement,

            -- id of the user which is submitting the review
            user_id integer not null,

            -- id of the room that is being reviewed
            room_id integer not null,

            rating integer not null
                check (rating >= 0 and rating <= 10),   -- rating /10
            comment text not null,          -- written feedback by user as text
            flagged integer default 0,      -- review moderation flag, it will be 1 if flagged but default is 0

            created_at text default current_timestamp,   -- when the review was created
            updated_at text default current_timestamp,    -- when the review was last updated

            -- Foreign keys
            foreign key(user_id) references users(id),
            foreign key(room_id) references rooms(id)
        );
        """
    )

    conn.commit()
    conn.close()


def submit_review(user_id, room_id, rating, comment):
    """Insert a new review.

    Parameters
    user_id : int
        ID of the user submitting the review.
    room_id : int
        ID of the room being reviewed.
    rating : int
        Rating score (0-10).
    comment : str
        Free-text comment written by the user.

    Returns
    int
        The auto-generated ID of the newly created review.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        insert into reviews (user_id, room_id, rating, comment)
        values (?, ?, ?, ?);
        """,
        (user_id, room_id, rating, comment),
    )

    conn.commit()
    review_id = cur.lastrowid
    conn.close()
    return review_id


def update_review(review_id, rating, comment):
    """Update an existing review's rating and comment.

    Parameters
    review_id : int
        ID of the review to update.
    rating : int
        New rating score (0–10).
    comment : str
        New free-text comment.

    Returns
    None
        The review row is updated in-place.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        update reviews
        set rating = ?, comment = ?, updated_at = current_timestamp
        where id = ?;
        """,
        (rating, comment, review_id),
    )

    conn.commit()
    conn.close()


def delete_review(review_id):
    """Delete a review permanently.

    Parameters
    review_id : int
        ID of the review to remove.

    Returns
    None
        The review row is removed from the database.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "delete from reviews where id = ?;",
        (review_id,),
    )

    conn.commit()
    conn.close()


def get_reviews_for_room(room_id):
    """Return all reviews for a specific room.

    Parameters
    room_id : int
        ID of the room for which reviews are requested.

    Returns
    list of sqlite3.Row
        A list of rows containing review data for this room.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        select * from reviews
        where room_id = ?
        order by created_at desc;
        """,
        (room_id,),
    )

    rows = cur.fetchall()
    conn.close()
    return rows


def flag_review(review_id):
    """Mark a review as flagged (moderation action).

    Parameters
    review_id : int
        ID of the review to flag.

    Returns
    None
        Updates the 'flagged' field of the given review.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        update reviews
        set flagged = 1, updated_at = current_timestamp
        where id = ?;
        """,
        (review_id,),
    )

    conn.commit()
    conn.close()


def find_review_by_id(review_id):
    """Retrieve a single review row using its ID.

    Parameters
    ----------
    review_id : int
        The ID of the review to look up.

    Returns
    -------
    sqlite3.Row or None
        The review row if it exists, otherwise None.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("select * from reviews where id = ?;", (review_id,))
    row = cur.fetchone()
    conn.close()
    return row


def find_user_by_id(user_id):
    """This fct will retrieve a single user row using the user's ID.

    Parameters
    user_id : int
        The ID of the user to look up.

    Returns
    sqlite3.Row or None
        The user row if found, None otherwise.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("select * from users where id = ?;", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def find_room_by_id(room_id):
    """This fct will retrieve a single room row using the room's ID.

    Parameters
    room_id : int
        The ID of the room to look up.

    Returns
    sqlite3.Row or None
        The room row if found, None otherwise.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("select * from rooms where id = ?;", (room_id,))
    row = cur.fetchone()
    conn.close()
    return row

#make_reviews_table_if_missing()

"""
This file is for database related code for the reviews service.
Getting db connection, creating reviews table if it's not there,
and other db related functions which will be used by app.py.
"""

import sqlite3

DB_NAME = "database.db"


def get_connection():
    """This fct opens a connection to the reviews database and returns it.
    It uses sqlite3.Row so columns can be accessed by name.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def make_reviews_table_if_missing():
    """This fct will create the reviews table if it does not already exist."""
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
            flagged integer default 0,      -- review moderation flag

            created_at text default current_timestamp,   -- when the review was created
            updated_at text default current_timestamp    -- when the review was last updated
        );
        """
    )

    conn.commit()
    conn.close()

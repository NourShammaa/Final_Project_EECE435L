"""
This is the master database initializer. 
It initializes the db by running all table creation functions from all services.
"""

from users_service.database import make_users_table_if_missing
from room_service.database import make_rooms_table_if_missing
from bookings_service.database import make_bookings_table_if_missing
from reviews_service.database import make_reviews_table_if_missing

def initialize_database():

    """This fct will create all required tables for the entire system.

    It runs the diff table creation fcts from each service:
    Users, Rooms, Bookings, and Reviews. It will make sure that the shared
    database file contains every table needed before any service starts.
    """    
    print("Initializing the whole database...")
    make_users_table_if_missing()
    make_rooms_table_if_missing()
    make_bookings_table_if_missing()
    make_reviews_table_if_missing()
    print("Database was initialized successfully!")

if __name__ == "__main__":
    initialize_database()

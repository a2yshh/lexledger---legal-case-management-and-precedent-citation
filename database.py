import mysql.connector
from mysql.connector import Error

def get_db_connection():
    """Create database connection"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            database='legal_case_management',
            user='ayush', 
            password='ayush08'  
        )
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def execute_query(query, params=None):
    """Execute a query and return results"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if query.strip().upper().startswith('SELECT'):
                result = cursor.fetchall()
            else:
                connection.commit()
                result = cursor.lastrowid
            
            cursor.close()
            connection.close()
            return result
        except Error as e:
            print(f"Error executing query: {e}")
            return None
    return None
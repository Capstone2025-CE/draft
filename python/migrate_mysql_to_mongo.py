import mysql.connector
import numpy as np
import pickle
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import Binary
from datetime import datetime  # <--- THIS IS THE FIX

# --- CONFIGURATION ---

# 1. Your OLD MySQL database config
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "cvproj",
}

# 2. Your NEW MongoDB connection string
# (Replace <username>, <password>, and <cluster-url>)
MONGO_URI = "mongodb+srv://dbAdmin:Aditya123@cluster0.fv6ix91.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "capstone_project"
COLLECTION_NAME = "students"

# --- END CONFIGURATION ---

def migrate():
    print("--- Starting Migration: MySQL to MongoDB ---")
    
    # 1. Connect to MongoDB
    try:
        print(f"Connecting to MongoDB Atlas cluster...")
        mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
        mongo_db = mongo_client[DB_NAME]
        mongo_collection = mongo_db[COLLECTION_NAME]
        mongo_client.admin.command('ping')
        print("✅ MongoDB connection successful.")
    except Exception as e:
        print(f"❌ Could not connect to MongoDB: {e}")
        return

    # 2. Connect to MySQL
    try:
        print("Connecting to local MySQL database...")
        mysql_conn = mysql.connector.connect(**DB_CONFIG)
        mysql_cursor = mysql_conn.cursor()
        print("✅ MySQL connection successful.")
    except Exception as e:
        print(f"❌ Could not connect to MySQL: {e}")
        return

    # 3. Fetch all students from MySQL
    print("Fetching student data from MySQL...")
    mysql_cursor.execute("SELECT sap_id, name, rollno, embeddings FROM student")
    students = mysql_cursor.fetchall()
    print(f"Found {len(students)} students to migrate.")

    migrated_count = 0
    skipped_count = 0
    error_count = 0  # <-- Fixed counter

    # 4. Loop, Convert, and Insert into MongoDB
    for (sap_id, name, rollno, embedding_str) in students:
        try:
            # Check if student already exists in MongoDB
            if mongo_collection.find_one({"sap_id": sap_id}):
                print(f"⚠️ Skipping {sap_id} ({name}): Already exists in MongoDB.")
                skipped_count += 1
                continue

            # Convert the embedding string from MySQL back to a numpy array
            embedding_np = np.array(
                list(map(float, embedding_str.split(","))), dtype=np.float32
            )
            
            # Serialize the numpy array to bytes using pickle
            embedding_bson = Binary(pickle.dumps(embedding_np, protocol=pickle.HIGHEST_PROTOCOL))

            # Create the new student document for MongoDB
            new_student_doc = {
                "sap_id": sap_id,
                "name": name,
                "rollno": rollno,
                "embedding": embedding_bson,
                "migrated_at": datetime.now() # <--- This will now work
            }

            # Insert into MongoDB
            mongo_collection.insert_one(new_student_doc)
            print(f"✅ Migrated {sap_id} ({name}).")
            migrated_count += 1

        except Exception as e:
            print(f"❌ Error migrating {sap_id}: {e}")
            error_count += 1  # <-- Fixed counter

    # 5. Clean up
    mysql_cursor.close()
    mysql_conn.close()
    mongo_client.close()
    
    print("\n--- Migration Complete ---")
    print(f"Successfully migrated: {migrated_count}")
    print(f"Skipped (already exist): {skipped_count}")
    print(f"Errors: {error_count}") # <-- Fixed counter

if __name__ == "__main__":
    migrate()
  
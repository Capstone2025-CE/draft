import mysql.connector
import cv2
import numpy as np
import faiss
import os
import random  # Added for create_class
import string  # Added for create_class
import pandas as pd
import tkinter as tk
from tkinter import messagebox
from keras_facenet import FaceNet
from mtcnn import MTCNN
from datetime import datetime, date  # Added 'date' for mark_attendance_server
import threading
import time
import csv

# --- Global variables to hold models for the SERVER ---
# These are loaded by load_models_on_startup()
server_detector = None
server_embedder = None
server_faiss_index = None
server_names_list = None
server_sapids_list = None

# --- Database configuration (used by all functions) ---
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "cvproj",
}

# ==============================================================================
# --- 1. FUNCTIONS FOR THE FASTAPI SERVER ---
# (These are called by backend_cap.py)
# ==============================================================================

def load_models_on_startup():
    """
    Loads models and embeddings from MySQL into global variables at server startup.
    """
    # Assign to global variables
    global server_detector, server_embedder, server_faiss_index, server_names_list, server_sapids_list
    
    print("🔄 Initializing MTCNN and FaceNet models for server...")
    server_detector = MTCNN()
    server_embedder = FaceNet()
    print("✅ Server models initialized.")

    print("🔄 Loading student embeddings from MySQL for FAISS...")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT sap_id, name, rollno, embeddings FROM student")
        rows = cursor.fetchall()
        
        embeddings = []
        sapids = []
        names = []
        rollnos = [] # Added rollnos for consistency
        
        for sap_id, name, rollno, embedding_str in rows:
            if not embedding_str:
                print(f"⚠️ Skipping {sap_id}: empty embedding")
                continue
            try:
                emb = np.array(
                    list(map(float, embedding_str.split(","))), dtype=np.float32
                )
                if emb.size == 0:
                    print(f"⚠️ Skipping {sap_id}: invalid embedding array")
                    continue
                
                embeddings.append(emb)
                sapids.append(sap_id)
                names.append(name)
                rollnos.append(rollno) # Added rollnos
            except Exception as e:
                print(f"⚠️ Failed to parse embedding for {sap_id}: {e}")
                continue

        if len(embeddings) == 0:
            raise ValueError(
                "❌ No valid embeddings found in MySQL. Please run populate_database.py first."
            )

        # Convert list to numpy array for FAISS
        embeddings_np = np.vstack(embeddings).astype("float32")
        
        # Assign loaded data to global variables
        server_faiss_index = faiss.IndexFlatL2(embeddings_np.shape[1])
        server_faiss_index.add(embeddings_np)
        server_names_list = names
        server_sapids_list = sapids

        print(f"✅ Loaded {len(embeddings)} embeddings into FAISS index.")
        # Return statement from your original code, though not strictly needed
        # when using globals.
        return server_faiss_index, sapids, names, rollnos 

    except mysql.connector.Error as db_err:
        print(f"❌ MySQL Error: {db_err}")
        raise
    finally:
        cursor.close()
        conn.close()


# In MODELTESTING.py

def recognize_face_in_frame(frame):
    """
    Recognizes a face in a single frame using the globally loaded server models.
    --- NOW WITH MASTER ERROR HANDLING ---
    """
    # Access the global models
    global server_detector, server_embedder, server_faiss_index, server_names_list, server_sapids_list

    if server_faiss_index is None or server_detector is None:
        return {"name": "Server Error", "sap_id": "Models not loaded"}

    try:
        # --- All your AI logic is now inside this try block ---
        faces = server_detector.detect_faces(frame)
        if not faces:
            # This is a normal return, not an error
            return {"name": "No face detected", "sap_id": "N/A"}

        # Find the largest face
        face = max(faces, key=lambda f: f["box"][2] * f["box"][3])
        x1, y1, w, h = face["box"]
        x1, y1 = abs(x1), abs(y1)
        x2, y2 = x1 + w, y1 + h
        face_img = frame[y1:y2, x1:x2]

        if face_img.size == 0:
            return {"name": "Face too small", "sap_id": "N/A"}

        face_img = cv2.resize(face_img, (160, 160))
        embedding = server_embedder.embeddings([face_img])[0]
        embedding = np.expand_dims(embedding, axis=0).astype("float32")

        distances, indices = server_faiss_index.search(embedding, 1)

        # Threshold for recognition
        if distances[0][0] < 0.77:
            recognized_name = server_names_list[indices[0][0]]
            sapid = server_sapids_list[indices[0][0]]
            
            # Mark attendance (this function should also be safe)
            mark_attendance_server(sapid) 
            
            return {"name": recognized_name, "sap_id": sapid}
        else:
            return {"name": "Unknown", "sap_id": "N/A"}
    
    except Exception as e:
        # --- THIS IS THE CRITICAL FIX ---
        # If anything fails (cv2 error, numpy error, etc.),
        # print the error to your server log and send a clean
        # JSON response to the app so it doesn't crash.
        print(f"!!! CRITICAL ERROR IN RECOGNITION: {e}")
        return {"name": "Recognition Error", "sap_id": "Server-side"}


def mark_attendance_server(sap_id):
    """Logs attendance to the DB. Called by recognize_face_in_frame."""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        today = date.today().strftime("%Y-%m-%d")
        
        # Check if attendance is already marked for this student today
        cursor.execute(
            "SELECT 1 FROM attendance WHERE sap_id = %s AND DATE(timestamp) = %s",
            (sap_id, today),
        )
        if cursor.fetchone():
            print(f"Attendance already marked for {sap_id} today.")
            return True

        # Insert new attendance record
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO attendance (sap_id, class_code, timestamp) VALUES (%s, %s, %s)",
            (sap_id, "mobile_app", timestamp), # Using "mobile_app" as class_code
        )
        conn.commit()
        print(f"ATTENDANCE MARKED for {sap_id} at {timestamp}.")
        return True

    except mysql.connector.Error as err:
        print(f"Error marking attendance from server: {err}")
        return False
    finally:
        conn.close()

# ==============================================================================
# --- 2. FUNCTIONS FOR YOUR LOCAL/TKINTER APP ---
# (These are all your other functions, included as they were)
# ==============================================================================

# Initialize models for local use (Tkinter, etc.)
detector = MTCNN()
embedder = FaceNet()

def add_student_embedding(sap_id, name, rollno, image_path, password):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        img = cv2.imread(image_path)
        if img is None:
            messagebox.showerror("Error", f"Could not load image for: {image_path}")
            return
        faces = detector.detect_faces(img)
        if not faces:
            messagebox.showerror(
                "Error", f"No faces detected in the image for: {image_path}"
            )
            return
        
        for face in faces:
            x1, y1, width, height = face["box"]
            x1, y1 = abs(x1), abs(y1)
            x2, y2 = x1 + width, y1 + height
            face_img = img[y1:y2, x1:x2]
            face_img = cv2.resize(face_img, (160, 160))
            face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
            face_embedding = embedder.embeddings([face_img])[0]
            embedding_str = ",".join(map(str, face_embedding))
            
            try:
                # FIX: Your original query was missing placeholders.
                cursor.execute(
                    "INSERT INTO student (sap_id, name, rollno, embeddings, password) VALUES (%s, %s, %s, %s, %s)",
                    (sap_id, name, rollno, embedding_str, password),
                )
                conn.commit()
                break # Success, exit loop
            except mysql.connector.Error as err:
                print(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()

def add_teacher(T_id, name, password):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO teachers (T_id, name, password) VALUES (%s, %s, %s)",
            (T_id, name, password),
        )
        conn.commit()
        print(f"Teacher {name} added successfully.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()

def create_class(T_id, class_name):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    try:
        cursor.execute(
            "INSERT INTO class (class_code, class_name, T_id) VALUES (%s, %s, %s)",
            (code, class_name, T_id),
        )
        conn.commit()
        # FIX: Your print statement referred to 'name' which doesn't exist here.
        print(f"Class {class_name} created with code {code} for teacher {T_id}.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()
    return code

def code_validation(sapid, class_code):
    # You had 'pass' here, so this is just a placeholder
    # You need to add logic to check if the code is valid
    print(f"Validating code {class_code} for student {sapid}...")
    valid = True # Placeholder
    if valid:
        add_student_to_class(sapid, class_code)

def add_student_to_class(sap_id, class_code):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO class_students (class_code, sap_id) VALUES (%s, %s)",
            (class_code, sap_id),
        )
        conn.commit()
        print(f"Student {sap_id} added to class {class_code} successfully.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()

def mark_attendance(sap_id, class_code):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(
            "INSERT INTO attendance (sap_id, class_code, timestamp) VALUES (%s, %s, %s)",
            (sap_id, class_code, timestamp),
        )
        conn.commit()
        print(f"Attendance marked for {sap_id} in class {class_code} at {timestamp}.")
        return messagebox.showinfo(
            "Success",
            f"Attendance marked for {sap_id} in class {class_code} at {timestamp}.",
        )
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        conn.close()

def load_embeddings(class_code):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        # FIX: Corrected SQL query logic and indexing from your original
        cursor.execute(
            "SELECT sap_id, name, rollno, embeddings from student WHERE sap_id IN (SELECT sap_id FROM class_students WHERE class_code = %s)",
            (class_code,),
        )
        rows = cursor.fetchall()
        embeddings = []
        names = []
        sapids = []
        rollnos = []
        for row in rows:
            try:
                sapid = row[0]
                name = row[1]
                rollno = row[2]
                embedding_str = row[3]
                
                # Use sapid and name for the display name
                display_name = f"{sapid} ({name})"
                
                if not embedding_str:
                    print(f"⚠️ Skipping {sapid}: empty embedding string")
                    continue
                
                embedding = np.array(
                    list(map(float, embedding_str.split(","))), dtype=np.float32
                )
                if embedding.size == 0:
                    print(f"⚠️ Skipping {sapid}: invalid embedding array")
                    continue
                
                embeddings.append(embedding)
                names.append(display_name)
                sapids.append(sapid)
                rollnos.append(rollno)
            except Exception as row_err:
                print(f"⚠️ Error processing row {row}: {row_err}")
                continue

        if len(embeddings) == 0:
            raise ValueError("No valid embeddings found in database for this class.")

        embeddings_np = np.vstack(embeddings).astype("float32")
        index = faiss.IndexFlatL2(embeddings_np.shape[1])
        index.add(embeddings_np)
        
        # Return all the loaded data
        return index, names, sapids, rollnos

    except mysql.connector.Error as db_err:
        print(f"❌ MySQL Error: {db_err}")
        raise
    finally:
        if conn.is_connected():
            conn.close()

def find_closest_match(embedding, faiss_index, names):
    embedding = np.expand_dims(embedding, axis=0).astype("float32")
    distances, indices = faiss_index.search(embedding, 1)
    if distances[0][0] < 0.77:
        return names[indices[0][0]]
    else:
        return "Unknown"

def start_face_recognition(class_code):
    try:
        # Load embeddings for the specific class
        faiss_index, names, sapids, rollnos = load_embeddings(class_code)
    except Exception as e:
        print(f"Failed to load embeddings: {e}")
        return

    cap = cv2.VideoCapture(0)
    log_messages = []
    log_timeout = 100
    attendance_marked = set() # To avoid marking multiple times

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        try:
            faces = detector.detect_faces(frame)
        except Exception as e:
            print(f"Face detection error: {e}")
            continue

        face_images = []
        face_boxes = []
        for face in faces:
            try:
                x1, y1, w, h = face["box"]
                x1, y1 = abs(x1), abs(y1)
                x2, y2 = x1 + w, y1 + h
                face_img = frame[y1:y2, x1:x2]
                if face_img.size == 0:
                    continue
                face_img = cv2.resize(face_img, (160, 160))
                face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
                face_images.append(face_img)
                face_boxes.append((x1, y1, x2, y2))
            except Exception as e:
                print(f"Error processing face box: {e}")
                continue
        
        if face_images:
            embeddings = embedder.embeddings(face_images)
            for i, embedding in enumerate(embeddings):
                try:
                    display_name = find_closest_match(embedding, faiss_index, names)
                    
                    if display_name != "Unknown" and display_name not in attendance_marked:
                        # Extract sapid from display_name "SAPID (Name)"
                        sapid = display_name.split(" ")[0]
                        # Call the local mark_attendance function
                        mark_attendance(sapid, class_code) 
                        attendance_marked.add(display_name) # Add to set
                        log_messages.append((f"Marked: {display_name}", log_timeout))

                    elif display_name == "Unknown":
                        log_messages.append(("Unknown Face", log_timeout))
                    
                    # Draw bounding box and label
                    x1, y1, x2, y2 = face_boxes[i]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        frame,
                        display_name,
                        (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.9,
                        (0, 255, 0),
                        2,
                    )
                except Exception as e:
                    print(f"Error processing embedding: {e}")
                    continue

        # Display log message
        if log_messages:
            msg, timeout = log_messages[0]
            cv2.putText(
                frame, msg, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2
            )
            if timeout <= 1:
                log_messages.pop(0)
            else:
                log_messages[0] = (msg, timeout - 1)
        
        cv2.imshow("Face Recognition", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
import tkinter as tk
from tkinter import messagebox
import pandas as pd
import os
import cv2
import mysql.connector
from keras_facenet import FaceNet
import threading
from mtcnn import MTCNN  # For face detection
from datetime import datetime
import time
import numpy as np 
import faiss  # Import FAISS for similarity search
import csv  # For saving attendance records to a CSV file

# Initialize detector and embedder
detector = MTCNN()
embedder = FaceNet()


# Database configuration
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "cvproj"  # Replace with your MySQL database name
}

# Function to reload the database with new images and embeddings
def reload_database():
        EXCEL_PATH = "C:\captsoneFiles\python\CVPROJECT.xlsx"
        IMAGES_FOLDER = "C:\captsoneFiles\python\images"

        # Load the Excel file
        try:
            df = pd.read_excel(EXCEL_PATH)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load Excel file: {e}")
            return

        # Validate required columns
        if not {'sapid', 'name', 'rollno'}.issubset(df.columns):
            messagebox.showerror("Error", "Excel file must contain 'sapid', 'name', and 'rollno' columns.")
            return

        # Connect to the database
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Iterate through the Excel rows and process images
        for _, row in df.iterrows():
            name = row['name']
            sap_id = row['sapid']
            rollno = row['rollno']
            image_path = os.path.join(IMAGES_FOLDER, f"{sap_id}.jpg")  # Assuming images are named by SAP ID

            # Check if the SAP ID already exists in the database
            cursor.execute("SELECT COUNT(*) FROM face_embeddings WHERE sap_id = %s", (sap_id,))
            if cursor.fetchone()[0] > 0:
                continue  # Skip if the entry already exists

            # Load the image
            img = cv2.imread(image_path)
            if img is None:
                messagebox.showerror("Error", f"Could not load image for SAP ID: {sap_id}")
                continue

            faces = detector.detect_faces(img)
            if faces:
                for face in faces:
                    x1, y1, width, height = face['box']
                    x1, y1 = abs(x1), abs(y1)
                    x2, y2 = x1 + width, y1 + height
                    face_img = img[y1:y2, x1:x2]
                    face_img = cv2.resize(face_img, (160, 160))
                    face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
                    face_embedding = embedder.embeddings([face_img])[0]
                    embedding_str = ",".join(map(str, face_embedding))

                    # Save embedding to the database
                    cursor.execute("INSERT INTO face_embeddings (rollno, name, sap_id, embedding) VALUES (%s, %s, %s, %s)", (rollno, name, sap_id, embedding_str))
                    conn.commit()
                    break
            else:
                messagebox.showerror("Error", f"No faces detected in the image for SAP ID: {sap_id}")

        conn.close()
        messagebox.showinfo("Success", "Database reloaded successfully.")

# Global attendance state
attendance_marked = set()
students_within_one_hour = []


# Function to load embeddings from the specified path
def load_embeddings():
    """
    Load face embeddings from MySQL and create FAISS index.
    Returns: index, names, sapids, rollnos
    Raises: ValueError if no embeddings found
    """
    conn = None
    try:
        # Connect to DB
        conn = mysql.connector.connect(
            host="127.0.0.1",
            port=3306,
            user="root",
            password="root",
            database="cvproj"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT name, sap_id, rollno, embedding FROM face_embeddings")
        rows = cursor.fetchall()

        embeddings = []
        names = []
        sapids = []
        rollnos = []

        for row in rows:
            try:
                name = f"{row[0]} ({row[1]})"
                sapid = row[1]
                rollno = row[2]
                embedding_str = row[3]

                if not embedding_str:
                    print(f"⚠️ Skipping {sapid}: empty embedding string")
                    continue

                embedding = np.array(list(map(float, embedding_str.split(','))), dtype=np.float32)

                if embedding.size == 0:
                    print(f"⚠️ Skipping {sapid}: invalid embedding array")
                    continue

                embeddings.append(embedding)
                names.append(name)
                sapids.append(sapid)
                rollnos.append(rollno)

            except Exception as row_err:
                print(f"⚠️ Error processing row {row}: {row_err}")
                continue

        if len(embeddings) == 0:
            raise ValueError("No valid embeddings found in database. Please reload the database first.")

        # Build FAISS index
        embeddings = np.vstack(embeddings).astype('float32')
        index = faiss.IndexFlatL2(embeddings.shape[1])
        index.add(embeddings)

        return index, names, sapids, rollnos

    except mysql.connector.Error as db_err:
        print(f"❌ MySQL Error: {db_err}")
        raise
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def find_closest_match(embedding, faiss_index, names):
    """Find the closest match using FAISS index."""
    embedding = np.expand_dims(embedding, axis=0).astype('float32')
    distances, indices = faiss_index.search(embedding, 1)
    
    # Distance threshold to decide if it's a valid match
    if distances[0][0] < 0.77:
        return names[indices[0][0]]
    else:
        return "Unknown"

# Function to recognize faces and mark attendance
def start_face_recognition():
    try:
        faiss_index, names, sapids, rollnos = load_embeddings()
    except Exception as e:
        print(f"Failed to load embeddings: {e}")
        return

    cap = cv2.VideoCapture(0)
    log_messages = []      # On-screen log messages
    log_timeout = 100      # Frames to show the message

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
                x1, y1, w, h = face['box']
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
                    name = find_closest_match(embedding, faiss_index, names)
                    sapid = sapids[names.index(name)] if name != "Unknown" else None
                    rollno = rollnos[names.index(name)] if name != "Unknown" else None

                    if name != "Unknown" and name not in attendance_marked:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                        # Insert attendance into MySQL
                        try:
                            conn = mysql.connector.connect(
                                    host="127.0.0.1",
                                    port=3306,
                                    user="root",
                                    password="root",
                                    database="cvproj"
                            )
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO attendance (name, sapid, rollno, timestamp) VALUES (%s, %s, %s, %s)",
                                (name, sapid, rollno, timestamp)
                            )
                            conn.commit()
                            cursor.close()
                            conn.close()
                            print(f"Attendance marked for {name} at {timestamp}.")
                            attendance_marked.add(name)
                            log_messages.append((f"Marked: {name} ({sapid})", log_timeout))
                        except mysql.connector.Error as err:
                            print(f"MySQL Error: {err}")

                    elif name == "Unknown":
                        log_messages.append(("Unknown Face", log_timeout))

                    # Draw bounding box and label
                    x1, y1, x2, y2 = face_boxes[i]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, name, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                except Exception as e:
                    print(f"Error processing embedding: {e}")
                    continue

        # Display log message
        if log_messages:
            msg, timeout = log_messages[0]
            cv2.putText(frame, msg, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            if timeout <= 1:
                log_messages.pop(0)
            else:
                log_messages[0] = (msg, timeout - 1)

        cv2.imshow("Face Recognition", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"Total number of students marked: {len(attendance_marked)}")
    return attendance_marked

#GUI
def start_gui():
    root = tk.Tk()
    root.title("Face Recognition System")

    # Use the actual global reload_database function
    def call_reload_database():
        threading.Thread(target=reload_database).start()

    # GUI Buttons
    tk.Button(root, text="Reload Database", command=call_reload_database).grid(row=0, column=1)

    # Add a placeholder for "Run" button
    def call_run_function():
        threading.Thread(target=start_face_recognition).start()

    tk.Button(root, text="Run", command=call_run_function).grid(row=1, column=1)

    root.mainloop()

start_gui()

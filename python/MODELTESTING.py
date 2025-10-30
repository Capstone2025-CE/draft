from fastapi import FastAPI, UploadFile, File

import uvicorn

import cv2

import numpy as np

# Import the functions from your MODELTESTING file

from MODELTESTING import load_models_on_startup, recognize_face_in_frame


# --- Main Application Setup ---

app = FastAPI()


@app.on_event("startup")
def on_startup():

    """This function will be called by FastAPI when the server starts."""

    print("--- FastAPI server startup event triggered. ---")

    print("--- Attempting to load models... ---")

    load_models_on_startup()

    print("--- Model loading process has finished. Server is ready. ---")


@app.post("/recognize-frame")
async def recognize_frame(frame: UploadFile = File(...)):

    try:

        contents = await frame.read()

        np_arr = np.frombuffer(contents, np.uint8)

        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:

            print("ERROR: Failed to decode image from app.")

            return "Error: Corrupt image"

        recognized_name = recognize_face_in_frame(img)

        print(f"Recognition result: {recognized_name}")

        return recognized_name

    except Exception as e:

        print(f"An error occurred in the recognition endpoint: {e}")

        return "Server Error"


# We no longer need the if __name__ == "__main__" block to run the server,

# as Uvicorn will handle it.


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
    "database": "cvproj",
}


# at login time


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

            # Save embedding to the database

            try:

                cursor.execute(
                    "INSERT INTO student (sap_id, name, rollno, embeddings, password) VALUES (%s, %s)",
                    (sap_id, name, rollno, embedding_str, password),
                )

                conn.commit()

            except mysql.connector.Error as err:

                print(f"Error: {err}")

            else:

                break

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


# create class button


def create_class(T_id, class_name):

    conn = mysql.connector.connect(**DB_CONFIG)

    cursor = conn.cursor()

    # Generate a random code for the class

    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    # check if the same code doesn't already exists

    try:

        cursor.execute(
            "INSERT INTO class (class_code, class_name, T_id) VALUES (%s, %s, %s)",
            (code, class_name, T_id),
        )

        conn.commit()

        print(f"Student {name} added to class {class_name} successfully.")

    except mysql.connector.Error as err:

        print(f"Error: {err}")

    finally:

        cursor.close()

        conn.close()

    return code


# for join class button


def code_validation(sapid, class_code):

    pass

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

    except mysql.connector.Error as err:

        print(f"Error: {err}")

    finally:

        cursor.close()

        conn.close()

        return messagebox.showinfo(
            "Success",
            f"Attendance marked for {sap_id} in class {class_code} at {timestamp}.",
        )


# Function to load embeddings from the specified path


def load_embeddings(sap_id, class_code):

    conn = mysql.connector.connect(**DB_CONFIG)

    cursor = conn.cursor()

    try:

        # Fetch embeddings from the database

        cursor.execute(
            "SELECT sap_id, name, rollno, embeddings from students WHERE sap_id IN (SELECT sap_id FROM class_students WHERE class_code = %s)",
            (class_code,),
        )

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

                embedding = np.array(
                    list(map(float, embedding_str.split(","))), dtype=np.float32
                )

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

            raise ValueError(
                "No valid embeddings found in database. Please reload the database first."
            )

        # Build FAISS index

        embeddings = np.vstack(embeddings).astype("float32")

        index = faiss.IndexFlatL2(embeddings.shape[1])

        index.add(embeddings)

        return index, names, sapids, rollnos, class_code

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

    embedding = np.expand_dims(embedding, axis=0).astype("float32")

    distances, indices = faiss_index.search(embedding, 1)

    # Distance threshold to decide if it's a valid match

    if distances[0][0] < 0.77:

        return names[indices[0][0]]

    else:

        return "Unknown"


# for take attendance button

# Function to recognize faces and mark attendance


def start_face_recognition(class_code):

    try:

        faiss_index, names, sapids, rollnos = load_embeddings()

    except Exception as e:

        print(f"Failed to load embeddings: {e}")

        return

    cap = cv2.VideoCapture(0)

    log_messages = []  # On-screen log messages

    log_timeout = 100  # Frames to show the message

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

                    name = find_closest_match(embedding, faiss_index, names)

                    sapid = sapids[names.index(name)] if name != "Unknown" else None

                    rollno = rollnos[names.index(name)] if name != "Unknown" else None

                    if name != "Unknown" and name not in attendance_marked:

                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        # Insert attendance into MySQL

                        mark_attendance(sapid, class_code)

                    elif name == "Unknown":

                        log_messages.append(("Unknown Face", log_timeout))

                    # Draw bounding box and label

                    x1, y1, x2, y2 = face_boxes[i]

                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    cv2.putText(
                        frame,
                        name,
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


# ==============================================================================

# --- NEW SERVER-SIDE FUNCTIONS ---

# These functions are designed to be called by backend_cap.py

# They are optimized for handling single frames from the Flutter app.

# ==============================================================================


# --- Global variables to hold models and data loaded from local files ---

server_detector = None

server_embedder = None

server_faiss_index = None

server_names_list = None

server_sapids_list = None


# In MODELTESTING.py


# In MODELTESTING.py


# In MODELTESTING.py


def load_models_on_startup():

    """

    Loads student embeddings from MySQL into FAISS index at server startup.

    Returns (faiss_index, sapids, names, rollnos)

    """

    print("🔄 Loading models for server (from MySQL)...")

    conn = mysql.connector.connect(**DB_CONFIG)

    cursor = conn.cursor()

    try:

        cursor.execute("SELECT sap_id, name, rollno, embeddings FROM student")

        rows = cursor.fetchall()

        embeddings = []

        sapids = []

        names = []

        rollnos = []

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

                rollnos.append(rollno)

            except Exception as e:

                print(f"⚠️ Failed to parse embedding for {sap_id}: {e}")

                continue

        if len(embeddings) == 0:

            raise ValueError(
                "❌ No valid embeddings found in MySQL. Please register students first."
            )

        embeddings = np.vstack(embeddings).astype("float32")

        index = faiss.IndexFlatL2(embeddings.shape[1])

        index.add(embeddings)

        print(f"✅ Loaded {len(embeddings)} embeddings into FAISS.")

        return index, sapids, names, rollnos

    except mysql.connector.Error as db_err:

        print(f"❌ MySQL Error: {db_err}")

        raise

    finally:

        cursor.close()

        conn.close()


def mark_attendance_server(sap_id):

    # This function remains the same, it will save the attendance to the database

    # after recognition is successful.

    conn = mysql.connector.connect(**DB_CONFIG)

    cursor = conn.cursor()

    try:

        today = date.today().strftime("%Y-%m-%d")

        cursor.execute(
            "SELECT 1 FROM attendance WHERE sap_id = %s AND DATE(timestamp) = %s",
            (sap_id, today),
        )

        if cursor.fetchone():

            print(f"Attendance already marked for {sap_id} today.")

            return True

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            "INSERT INTO attendance (sap_id, class_code, timestamp) VALUES (%s, %s, %s)",
            (sap_id, "mobile_app", timestamp),
        )

        conn.commit()

        print(f"ATTENDANCE MARKED for {sap_id} at {timestamp}.")

        return True

    except mysql.connector.Error as err:

        print(f"Error marking attendance from server: {err}")

        return False

    finally:

        conn.close()


def recognize_face_in_frame(frame):

    # This function remains the same. It will use the data loaded into memory.

    if server_faiss_index is None:

        return "Error: Models not loaded on server."

    try:

        faces = server_detector.detect_faces(frame)

        if not faces:

            return "No face detected"

        face = max(faces, key=lambda f: f["box"][2] * f["box"][3])

        x1, y1, w, h = face["box"]

        x1, y1 = abs(x1), abs(y1)

        x2, y2 = x1 + w, y1 + h

        face_img = frame[y1:y2, x1:x2]

        if face_img.size == 0:
            return "Face too small"

        face_img = cv2.resize(face_img, (160, 160))

        embedding = server_embedder.embeddings([face_img])[0]

        embedding = np.expand_dims(embedding, axis=0).astype("float32")

        distances, indices = server_faiss_index.search(embedding, 1)

        if distances[0][0] < 0.77:

            recognized_name = server_names_list[indices[0][0]]

            sapid = server_sapids_list[indices[0][0]]

            mark_attendance_server(sapid)

            return recognized_name

        else:

            return "Unknown"

    except Exception as e:

        print(f"Error during recognition: {e}")

        return "Recognition Error"


import pandas as pd

import mysql.connector

import cv2

import numpy as np

import os

from keras_facenet import FaceNet

from mtcnn import MTCNN


# Initialize FaceNet and MTCNN

embedder = FaceNet()

detector = MTCNN()


# Paths

EXCEL_PATH = r"C:/captsoneFiles/python/CVPROJECT.xlsx"

IMAGE_DIR = r"C:/captsoneFiles/python/images"


# Load Excel (must have: sapid, name, rollno)

df = pd.read_excel(EXCEL_PATH, engine="openpyxl")


DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "cvproj",
}


conn = mysql.connector.connect(**DB_CONFIG)

cursor = conn.cursor()


for _, row in df.iterrows():

    sap_id = str(row["sapid"])

    name = row["name"]

    rollno = str(row["rollno"])

    image_path = os.path.join(IMAGE_DIR, f"{sap_id}.jpg")

    if not os.path.exists(image_path):

        image_path = os.path.join(IMAGE_DIR, f"{sap_id}.png")  # fallback

    if not os.path.exists(image_path):

        print(f"⚠️ No image found for {sap_id}, skipping...")

        continue

    # ---- Step 1: Read and detect face ----

    img = cv2.imread(image_path)

    if img is None:

        print(f"⚠️ Could not read image for {sap_id}")

        continue

    results = detector.detect_faces(img)

    if not results:

        print(f"⚠️ No face detected for {sap_id}")

        continue

    x, y, w, h = results[0]["box"]

    face = img[y : y + h, x : x + w]

    # ---- Step 2: Get embedding ----

    embedding = embedder.embeddings([face])[0]

    embedding_str = ",".join(map(str, embedding.tolist()))

    # ---- Step 3: Insert/Update into DB ----

    cursor.execute(
        """

        INSERT INTO student (sap_id, name, rollno, embeddings)

        VALUES (%s, %s, %s, %s)

        ON DUPLICATE KEY UPDATE name=VALUES(name), rollno=VALUES(rollno), embeddings=VALUES(embeddings)

        """,
        (sap_id, name, rollno, embedding_str),
    )

    print(f"✅ {sap_id} ({name}) processed successfully.")


conn.commit()

cursor.close()

conn.close()

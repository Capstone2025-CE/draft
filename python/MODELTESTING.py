import cv2
import numpy as np
import faiss
import os
import random
import string
import pandas as pd
import tkinter as tk
from tkinter import messagebox
from keras_facenet import FaceNet
from mtcnn import MTCNN # <-- REVERTED TO MTCNN
from datetime import datetime, date
import os
from dotenv import load_dotenv
load_dotenv()

# --- NEW: MONGODB IMPORTS ---
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import Binary 
import pickle 

# --- NEW: MONGODB SETUP ---
# 1. Get your connection string from MongoDB Atlas
# NEW CODE
MONGO_URI = os.getenv("MONGO_URI") # Reads from .env

if not MONGO_URI:
    print("="*50)
    print("FATAL ERROR: MONGO_URI environment variable not found.")
    print("Please create a .env file with your MongoDB connection string.")
    print("="*50)
    exit()

client = MongoClient(MONGO_URI)
DB_NAME = "capstone_project"

# Create a new client and connect to the server
try:
    mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    mongo_db = mongo_client[DB_NAME]
    mongo_client.admin.command('ping')
    print("✅ Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"❌ Could not connect to MongoDB: {e}")
    mongo_client = None
    mongo_db = None
    exit()

# --- Global variables to hold models ---
server_detector = None # <-- This will be MTCNN
server_embedder = None
server_faiss_index = None
server_names_list = []
server_sapids_list = []
liveness_net = None

# ==============================================================================
# --- 1. FUNCTIONS FOR THE FASTAPI SERVER ---
# ==============================================================================

def load_models_on_startup():
    global liveness_net
    """
    Loads models (MTCNN) AND embeddings from MongoDB into global variables.
    """
    global server_detector, server_embedder, server_faiss_index, server_names_list, server_sapids_list
    
    if mongo_db is None:
        print("❌ MongoDB client is not initialized.")
        return

    # 1. Load MTCNN model (Your old logic)
    print("🔄 Initializing MTCNN (detection) model...")
    server_detector = MTCNN()
    print("✅ MTCNN model initialized.")
    
    # 2. Load FaceNet model (Unchanged)
    print("🔄 Initializing FaceNet (recognition) model...")
    server_embedder = FaceNet()
    print("✅ FaceNet model initialized.")

    print("--- Loading Liveness Detection model... ---")
    try:
        # Define the paths to your downloaded model files
        proto_path = os.path.join("liveness_model", "liveness.prototxt")
        model_path = os.path.join("liveness_model", "liveness.caffemodel")
        
        liveness_net = cv2.dnn.readNetFromCaffe(proto_path, model_path)
        print("--- Liveness Detection model loaded successfully. ---")
    except Exception as e:
        print(f"!!! CRITICAL ERROR: Failed to load liveness model: {e} !!!")
        print("!!! Server will continue, but LIVENESS CHECK WILL FAIL. !!!")

    # 3. Load Embeddings from MONGODB
    print("🔄 Loading student embeddings from MongoDB for FAISS...")
    students_collection = mongo_db["students"]
    
    embeddings = []
    
    # Reset global lists
    server_names_list = []
    server_sapids_list = []
    
    # Find all students who have an embedding
    for student in students_collection.find({"embedding": {"$exists": True}}):
        try:
            # Deserialize the embedding from BSON Binary
            emb = pickle.loads(student["embedding"])
            
            embeddings.append(emb)
            server_names_list.append(student["name"])
            server_sapids_list.append(student["sap_id"])
            
        except Exception as e:
            print(f"⚠️ Failed to parse embedding for {student['sap_id']}: {e}")
            continue

    if len(embeddings) == 0:
        print("⚠️ No valid embeddings found in MongoDB. Waiting for students to register.")
        # Create a dummy index so the server doesn't crash.
        server_faiss_index = faiss.IndexFlatL2(512) # FaceNet embeddings are 512 dimensions
    else:
        # Build FAISS index from the loaded embeddings
        embeddings_np = np.vstack(embeddings).astype("float32")
        server_faiss_index = faiss.IndexFlatL2(embeddings_np.shape[1])
        server_faiss_index.add(embeddings_np)
        print(f"✅ Loaded {len(embeddings)} embeddings into FAISS index.")


def recognize_face_in_frame(frame):
    """
    Recognizes ALL faces in a single frame (using MTCNN) and returns a LIST of results.
    """
    global server_detector, server_embedder, server_faiss_index, server_names_list, server_sapids_list

    if server_faiss_index is None:
        return [{"name": "Server Error", "sap_id": "Models not loaded"}]

    recognized_faces_list = []
    try:
        # --- REVERTED TO MTCNN ---
        # MTCNN expects RGB, so convert frame from BGR (from cv2.imdecode) to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = server_detector.detect_faces(frame_rgb)
        
        if not faces:
            return [] # Return an empty list if no faces
        
        # --- Loop through ALL detected faces ---
        for face in faces:
            x1, y1, w, h = face["box"]
            x1, y1 = abs(x1), abs(y1)
            x2, y2 = x1 + w, y1 + h
            
            # Crop from the *original* BGR frame for FaceNet embedding
            face_img = frame[y1:y2, x1:x2] 

            if face_img.size == 0:
                continue # Skip this face if it's too small

            face_img = cv2.resize(face_img, (160, 160))
            embedding = server_embedder.embeddings([face_img])[0]
            embedding = np.expand_dims(embedding, axis=0).astype("float32")

            distances, indices = server_faiss_index.search(embedding, 1)

            if distances[0][0] < 0.77: # Match threshold
                recognized_name = server_names_list[indices[0][0]]
                sapid = server_sapids_list[indices[0][0]]
                mark_attendance_server(sapid, recognized_name) 
                recognized_faces_list.append({"name": recognized_name, "sap_id": sapid})
            else:
                recognized_faces_list.append({"name": "Unknown", "sap_id": "N/A"})
        
        return recognized_faces_list
    
    except Exception as e:
        print(f"!!! CRITICAL ERROR IN RECOGNITION: {e}")
        return [{"name": "Recognition Error", "sap_id": "Server-side"}]


def mark_attendance_server(sap_id, name):
    """Logs attendance to MongoDB."""
    if mongo_db is None: return False
    
    try:
        attendance_collection = mongo_db["attendance"]
        today = date.today().strftime("%Y-%m-%d")
        
        existing_record = attendance_collection.find_one({
            "sap_id": sap_id,
            "date": today
        })
        
        if existing_record:
            return True

        timestamp = datetime.now()
        attendance_collection.insert_one({
            "sap_id": sap_id,
            "name": name,
            "date": today,
            "timestamp": timestamp,
            "class_code": "mobile_app"
        })
        
        print(f"ATTENDANCE MARKED for {sap_id} at {timestamp}.")
        return True

    except Exception as e:
        print(f"Error marking attendance in MongoDB: {e}")
        return False

# --- NEW: Function for Student Self-Registration (1 Photo) ---

def register_student_mongo(sap_id, name, email, password, image_bytes):
    """
    Takes student info and 1 image file (as bytes), generates an embedding,
    and saves to MongoDB.
    """
    if mongo_db is None:
        return {"error": "Database not connected"}, 500
        
    students_collection = mongo_db["students"]

    if students_collection.find_one({"sap_id": sap_id}):
        return {"error": "Student with this SAP ID already exists"}, 400

    try:
        # --- REVERTED TO MTCNN ---
        # Initialize models just for this registration
        detector = MTCNN()
        embedder = FaceNet()
        
        # --- THIS IS THE FIX ---
        # The variable 'image_bytes' is ALREADY the data.
        # We no longer call .read()
        np_arr = np.frombuffer(image_bytes, np.uint8) 
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            # We don't have 'file.filename' anymore, so just give a generic error
            return {"error": "Could not read image: Corrupt file"}, 400

        # Convert to RGB for MTCNN
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        faces = detector.detect_faces(img_rgb)

        if not faces:
            # We don't have 'file.filename' anymore
            return {"error": "No face found in image"}, 400

        x1, y1, w, h = faces[0]["box"] # Get first face
        x1, y1 = abs(x1), abs(y1)
        x2, y2 = x1 + w, y1 + h
        
        # Crop from original BGR frame
        face_img = img[y1:y2, x1:x2]
        face_img = cv2.resize(face_img, (160, 160))
        
        embedding = embedder.embeddings([face_img])[0]
        embedding_bson = Binary(pickle.dumps(embedding, protocol=pickle.HIGHEST_PROTOCOL))

    except Exception as e:
        print(f"Error processing registration image: {e}")
        return {"error": "Error processing image"}, 500

    try:
        new_student = {
            "sap_id": sap_id,
            "name": name,
            "password": password,
            "email":email,
            "embedding": embedding_bson,
            "registered_at": datetime.now()
        }
        
        students_collection.insert_one(new_student)
        
        # --- IMPORTANT: Reload the FAISS index ---
        print("New student registered. Reloading FAISS index...")
        load_models_on_startup() 
        
        return {"message": "Student registered successfully"}, 201

    except Exception as e:
        print(f"Error saving student to MongoDB: {e}")
        return {"error": "Database error"}, 500
    
def check_liveness(frame):
    """
    Checks if the face in the frame is real (live) or a spoof (photo/video).
    Returns True if live, False if spoof.
    """
    global liveness_net
    
    if liveness_net is None:
        print("Liveness model not loaded. Skipping check.")
        # Fail open (assume live) to not block the demo if model failed
        # For security, you might 'return False' here.
        return True 

    # We need to preprocess the image to match the model's input
    # These values (300x300 size, mean subtraction) are common
    # but may need to be changed based on the model you downloaded.
    try:
        (h, w) = frame.shape[:2]
        
        # Create a blob from the image
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0,
            (300, 300), (104.0, 177.0, 123.0))

        # Pass the blob through the network
        liveness_net.setInput(blob)
        detections = liveness_net.forward()
        
        # 'detections' now holds the probabilities
        # We assume index 0 is "fake" and index 1 is "real"
        # This might be reversed! You MUST test this.
        fake_prob = detections[0, 0]
        real_prob = detections[0, 1]

        print(f"Liveness check: Real={real_prob:.4f}, Fake={fake_prob:.4f}")

        # Set a confidence threshold
        # If "real" probability is high, return True
        if real_prob > 0.85 and real_prob > fake_prob:
            return True
        else:
            return False
            
    except Exception as e:
        print(f"Error during liveness check: {e}")
        # If detection fails, assume live to not block demo
        return True
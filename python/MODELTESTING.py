import cv2
import numpy as np
import faiss
import os
import random
import string
import pandas as pd
from keras_facenet import FaceNet
from mtcnn import MTCNN
from datetime import datetime, date
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import Binary
import pickle

# --- NEW IMPORTS for Silent-Face-Anti-Spoofing ---
# These imports will work *only* if you completed Step 1
try:
    from src.anti_spoof_predict import AntiSpoofPredict
    from src.generate_patches import CropImage
    from src.utility import parse_model_name
except ImportError:
    print("="*50)
    print("ERROR: Could not import from 'src' folder.")
    print("Please make sure you have copied the 'src' folder from the GitHub repo")
    print("into your Python directory (C:\\captsoneFiles\\python\\).")
    print("="*50)
    exit()

# --- Load Environment Variables ---
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    print("FATAL ERROR: MONGO_URI not found in .env file.")
    exit()

# --- MongoDB Setup ---
DB_NAME = "capstone_project"
mongo_client = None
mongo_db = None

try:
    mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    mongo_db = mongo_client[DB_NAME]
    mongo_client.admin.command('ping')
    print("✅ Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(f"❌ Could not connect to MongoDB: {e}")
    exit()

# --- Global variables to hold models ---
server_detector = None      # MTCNN for face detection
server_embedder = None      # FaceNet for embeddings
server_faiss_index = None   # FAISS for fast search
server_names_list = []      # In-memory list of names for FAISS
server_sapids_list = []     # In-memory list of SAP IDs for FAISS

# --- NEW LIVENESS GLOBALS ---
liveness_model = None       # This will hold the AntiSpoofPredict object
image_cropper = None        # This is a helper class from the repo


# ==============================================================================
# --- 1. FUNCTIONS FOR THE FASTAPI SERVER ---
# ==============================================================================

def load_models_on_startup():
    """
    Loads all models (MTCNN, FaceNet, Liveness) AND embeddings from MongoDB
    into global variables.
    """
    global server_detector, server_embedder, server_faiss_index, server_names_list, server_sapids_list
    global liveness_model, image_cropper # <-- ADDED NEW LIVENESS GLOBALS
    
    if mongo_db is None:
        print("❌ MongoDB client is not initialized.")
        return

    # 1. Load MTCNN model
    print("🔄 Initializing MTCNN (detection) model...")
    server_detector = MTCNN()
    print("✅ MTCNN model initialized.")
    
    # 2. Load FaceNet model
    print("🔄 Initializing FaceNet (recognition) model...")
    server_embedder = FaceNet()
    print("✅ FaceNet model initialized.")

    # --- 3. REPLACED LIVENESS SECTION ---
    print("--- Loading Silent-Face-Anti-Spoofing model... ---")
    try:
        # device_id=0 for GPU, device_id=-1 for CPU
        # We will use CPU (-1) for compatibility
        liveness_model = AntiSpoofPredict(device_id=-1) 
        image_cropper = CropImage()
        print("--- Silent-Face-Anti-Spoofing model loaded successfully. ---")
    except Exception as e:
        print(f"!!! CRITICAL ERROR: Failed to load Silent-Face model: {e} !!!")
        print("!!! Make sure you have the 'src' folder and the model weights in 'resources/anti_spoof_models/' !!!")
        print("!!! LIVENESS CHECK WILL FAIL. !!!")
    # --- END OF REPLACED SECTION ---


    # 4. Load Embeddings from MONGODB into FAISS
    print("🔄 Loading student embeddings from MongoDB for FAISS...")
    students_collection = mongo_db["students"]
    
    embeddings = []
    server_names_list = []
    server_sapids_list = []
    
    for student in students_collection.find({"embedding": {"$exists": True}}):
        try:
            emb = pickle.loads(student["embedding"])
            embeddings.append(emb)
            server_names_list.append(student["name"])
            server_sapids_list.append(student["sap_id"])
        except Exception as e:
            print(f"⚠️ Failed to parse embedding for {student['sap_id']}: {e}")
            continue

    if len(embeddings) == 0:
        print("⚠️ No valid embeddings found in MongoDB.")
        server_faiss_index = faiss.IndexFlatL2(512)
    else:
        embeddings_np = np.vstack(embeddings).astype("float32")
        d = embeddings_np.shape[1] 
        server_faiss_index = faiss.IndexFlatL2(d)
        server_faiss_index.add(embeddings_np)
        print(f"✅ Loaded {len(embeddings)} embeddings into FAISS index (dim={d}).")


def check_liveness(frame):
    """
    Checks if the face in the frame is real (live) or a spoof (photo/video).
    Uses the Silent-Face-Anti-Spoofing model.
    Returns True if live, False if spoof.
    """
    global liveness_model, image_cropper
    
    if liveness_model is None or image_cropper is None:
        print("Liveness model not loaded. Skipping check.")
        return True # Fail open (assume live) to not block the demo

    try:
        # Use the liveness model's built-in face detector
        # This is separate from our MTCNN detector.
        image_bbox = liveness_model.get_bbox(frame)
        
        if image_bbox is None:
            print("Liveness check: No face found by liveness detector.")
            # We return True here so we can "fail open".
            # The *recognition* step later might still find a face.
            return True 

        # The repo's prediction function.
        # This function expects the original frame and the bounding box.
        prediction = liveness_model.predict(frame, image_bbox)
        
        # According to the repo:
        # Label 1 == REAL
        # Label 0 == FAKE
        is_live = (prediction == 1)
        
        print(f"Liveness check: Prediction={prediction} (1=Real, 0=Fake). Result: {is_live}")
        return is_live
            
    except Exception as e:
        print(f"Error during liveness check: {e}")
        # If detection fails, assume live to not block demo
        return True


def recognize_face_in_frame(frame):
    """
    Recognizes ALL faces in a single frame (using MTCNN) and returns a LIST of results.
    """
    global server_detector, server_embedder, server_faiss_index, server_names_list, server_sapids_list

    if server_faiss_index is None or server_faiss_index.ntotal == 0:
        print("FAISS index not loaded or is empty. Cannot recognize.")
        return [] 

    recognized_faces_list = []
    try:
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = server_detector.detect_faces(frame_rgb)
        
        if not faces:
            return [] 
        
        for face in faces:
            x1, y1, w, h = face["box"]
            x1, y1 = abs(x1), abs(y1)
            x2, y2 = x1 + w, y1 + h
            
            face_img = frame[y1:y2, x1:x2] 

            if face_img.size == 0:
                continue 

            face_img = cv2.resize(face_img, (160, 160))
            embedding = server_embedder.embeddings([face_img])[0]
            embedding = np.expand_dims(embedding, axis=0).astype("float32")

            distances, indices = server_faiss_index.search(embedding, 1)
            
            if distances[0][0] < 0.77: 
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
    """Logs attendance to MongoDB, checking for duplicates for the same day."""
    if mongo_db is None: 
        print("Error marking attendance: DB not connected")
        return False
    
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
        detector = MTCNN()
        embedder = FaceNet()
        
        np_arr = np.frombuffer(image_bytes, np.uint8) 
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {"error": "Could not read image: Corrupt file"}, 400

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        faces = detector.detect_faces(img_rgb)

        if not faces:
            return {"error": "No face found in image"}, 400

        x1, y1, w, h = faces[0]["box"] 
        x1, y1 = abs(x1), abs(y1)
        x2, y2 = x1 + w, y1 + h
        
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
            "email": email,
            "embedding": embedding_bson,
            "registered_at": datetime.now()
        }
        
        students_collection.insert_one(new_student)
        
        print("New student registered. Reloading FAISS index...")
        load_models_on_startup() 
        
        return {"message": "Student registered successfully"}, 201

    except Exception as e:
        print(f"Error saving student to MongoDB: {e}")
        return {"error": "Database error"}, 500
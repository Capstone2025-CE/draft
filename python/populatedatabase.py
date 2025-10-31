import pandas as pd
import mysql.connector
import cv2
import numpy as np
import os
from keras_facenet import FaceNet
from mtcnn import MTCNN

# --- NEW HEIC IMPORTS ---
from PIL import Image
from pillow_heif import register_heif_opener
# --------------------------

# --- NEW: Register the HEIC opener ---
register_heif_opener()
# -------------------------------------

# Initialize FaceNet and MTCNN
print("Loading models for database population...")
embedder = FaceNet()
detector = MTCNN()
print("Models loaded.")

# --- CONFIGURE YOUR PATHS HERE ---
EXCEL_PATH = r"C:/captsoneFiles/python/CVPROJECT.xlsx"
IMAGE_DIR = r"C:/captsoneFiles/python/images"
# --- -------------------------- ---

# Database configuration
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "cvproj",
}

try:
    df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
except FileNotFoundError:
    print(f"ERROR: Cannot find Excel file at: {EXCEL_PATH}")
    exit()
except Exception as e:
    print(f"Error reading Excel file: {e}")
    exit()

try:
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    print("Successfully connected to MySQL database.")
except mysql.connector.Error as err:
    print(f"ERROR: Could not connect to MySQL. Is it running? {err}")
    exit()


for _, row in df.iterrows():
    try:
        sap_id = str(row["sapid"])
        name = str(row["name"])
        rollno = str(row["rollno"])
    except KeyError as e:
        print(f"ERROR: Excel file is missing a required column: {e}")
        break

    # --- NEW: Updated file searching logic ---
    image_path = None
    img_rgb = None # This will hold our final RGB image for the model
    
    # Define possible extensions
    extensions = ['.jpg', '.JPG', '.png', '.PNG', '.heic', '.HEIC']
    
    for ext in extensions:
        temp_path = os.path.join(IMAGE_DIR, f"{sap_id}{ext}")
        if os.path.exists(temp_path):
            image_path = temp_path
            break
            
    if not image_path:
        print(f"⚠️ No image found for {sap_id} with any extension, skipping...")
        continue
    # --- --------------------------------- ---


    # ---- Step 1: Read and detect face ----
    
    # --- NEW: Handle HEIC vs JPG/PNG differently ---
    try:
        if image_path.lower().endswith('.heic'):
            # Use Pillow to open HEIC and convert to RGB numpy array
            img_pil = Image.open(image_path)
            img_pil = img_pil.convert('RGB')
            img_rgb = np.array(img_pil)
        else:
            # Use OpenCV for standard formats
            img = cv2.imread(image_path)
            if img is None:
                print(f"⚠️ Could not read image for {sap_id} (path: {image_path})")
                continue
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) # FaceNet expects RGB
            
    except Exception as e:
        print(f"⚠️ Error opening or converting image {image_path}: {e}")
        continue
    # --- ----------------------------------------- ---

    results = detector.detect_faces(img_rgb)

    if not results:
        print(f"⚠️ No face detected for {sap_id} in {image_path}")
        continue

    # Get the first/main face
    x, y, w, h = results[0]["box"]
    x, y = abs(x), abs(y)
    face = img_rgb[y : y + h, x : x + w]
    face = cv2.resize(face, (160, 160)) # Resize to model's expected input

    # ---- Step 2: Get embedding ----
    embedding = embedder.embeddings([face])[0]
    embedding_str = ",".join(map(str, embedding.tolist()))

    # ---- Step 3: Insert/Update into DB ----
    try:
        cursor.execute(
            """
            INSERT INTO student (sap_id, name, rollno, embeddings)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE name=VALUES(name), rollno=VALUES(rollno), embeddings=VALUES(embeddings)
            """,
            (sap_id, name, rollno, embedding_str),
        )
        print(f"✅ {sap_id} ({name}) processed and saved to database.")
    
    except mysql.connector.Error as db_err:
        print(f"❌ DB Error for {sap_id}: {db_err}")


conn.commit()
cursor.close()
conn.close()

print("\n--- Database population complete. ---")
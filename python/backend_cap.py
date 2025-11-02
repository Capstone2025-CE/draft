from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
import uvicorn
import cv2
import numpy as np
from typing import List
from contextlib import asynccontextmanager # <-- NEW IMPORT

# Import the functions from your MODELTESTING file
try:
    from MODELTESTING import load_models_on_startup, recognize_face_in_frame, register_student_mongo
except ImportError:
    print("="*50)
    print("ERROR: Could not import from MODELTESTING.py")
    exit()

# --- NEW: Lifespan Event Handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print("--- FastAPI server startup event triggered. ---")
    print("--- Attempting to load models from MongoDB... ---")
    load_models_on_startup() 
    print("--- Model loading process has finished. Server is ready. ---")
    
    yield # This is where the app runs
    
    # Code to run on shutdown (if any)
    print("--- Server shutting down. ---")

# --- Pass the lifespan handler to your app ---
app = FastAPI(lifespan=lifespan)

# --- REMOVED OLD @app.on_event("startup") ---


@app.post("/recognize-frame")
async def recognize_frame(frame: UploadFile = File(...)):
    """
    Receives a frame, recognizes ALL faces,
    and returns a JSON LIST of results.
    """
    try:
        contents = await frame.read()
        np_arr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            return [{"name": "Error: Corrupt image", "sap_id": "N/A"}]

        json_response_list = recognize_face_in_frame(img)
        
        print(f"Recognition result: {json_response_list}")
        return json_response_list

    except Exception as e:
        print(f"!!! CRITICAL ERROR in /recognize-frame endpoint: {e}")
        return [{"name": "Server Error", "sap_id": str(e)}]


# --- Student Registration Endpoint (1 Photo) ---
# --- Student Registration Endpoint (1 Photo) ---
@app.post("/student/register")
async def register_student(
    sap_id: str = Form(...),
    name: str = Form(...),
    password: str = Form(...), 
    file: UploadFile = File(...) 
):
    """
    Receives student details and 1 image file for face registration.
    """
    
    # --- THIS IS THE FIX ---
    # 1. Read the file contents as bytes asynchronously
    file_contents = await file.read()
    
    # 2. Pass the raw *bytes* (file_contents) to your processing function
    result, status_code = register_student_mongo(sap_id, name, password, file_contents)
    # --- END OF FIX ---

    if status_code != 201:
        # If it failed, return the error message
        raise HTTPException(status_code=status_code, detail=result["error"])
        
    return result

# You must run this file with:
# uvicorn backend_cap:app --host 0.0.0.0 --port 8000
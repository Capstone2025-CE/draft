from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
import uvicorn
import cv2
import numpy as np
from typing import List
from contextlib import asynccontextmanager # For startup/shutdown events

# Import the functions from your MODELTESTING file
try:
    from MODELTESTING import (
        load_models_on_startup, 
        recognize_face_in_frame, 
        register_student_mongo,
        check_liveness
    )
except ImportError:
    print("="*50)
    print("ERROR: Could not import from MODELTESTING.py")
    print("Please make sure MODELTESTING.py is in the same directory.")
    print("="*50)
    exit()

# --- NEW: Lifespan Event Handler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print("--- FastAPI server startup event triggered. ---")
    print("--- Attempting to load all models... ---")
    load_models_on_startup() 
    print("--- Model loading process has finished. Server is ready. ---")
    
    yield # This is where the app runs
    
    # Code to run on shutdown (if any)
    print("--- Server shutting down. ---")

# --- Pass the lifespan handler to your app ---
app = FastAPI(lifespan=lifespan)


@app.post("/recognize-frame")
async def recognize_frame(frame: UploadFile = File(...)):
    """
    Receives a frame, performs liveness check, recognizes ALL faces,
    and returns a JSON LIST of results.
    """
    try:
        contents = await frame.read()
        np_arr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            return [{"name": "Error: Corrupt image", "sap_id": "N/A"}]

        # --- STEP 1: LIVENESS CHECK ---
        is_live = check_liveness(img)
        
        if not is_live:
            print("!!! LIVENESS CHECK FAILED - SPOOF DETECTED !!!")
            return [{"name": "Spoof Detected", "sap_id": "N/A"}]
        # --- END OF LIVENESS CHECK ---

        # --- STEP 2: RECOGNITION ---
        print("--- Liveness check passed. Proceeding with recognition. ---")
        json_response_list = recognize_face_in_frame(img)
        
        print(f"Recognition result: {json_response_list}")
        return json_response_list

    except Exception as e:
        print(f"!!! CRITICAL ERROR in /recognize-frame endpoint: {e}")
        return [{"name": "Server Error", "sap_id": str(e)}]


@app.post("/student/register")
async def register_student(
    sap_id: str = Form(...),
    name: str = Form(...),
    password: str = Form(...), 
    file: UploadFile = File(...) 
):
    """
    Receives student details (NO EMAIL) and 1 image file for face registration.
    """
    
    file_contents = await file.read()
    
    # Call the updated function (no email)
    result, status_code = register_student_mongo(
        sap_id, name, password, file_contents
    )

    if status_code != 201:
        raise HTTPException(status_code=status_code, detail=result["error"])
        
    return result

# --- To run this file ---
if __name__ == "_main_":
    print("Starting FastAPI server...")
    print("Access the API at http://0.0.0.0:8000")
    # Set reload=False for stable production, reload=True for development
    uvicorn.run("backend_cap:app", host="0.0.0.0", port=8000, reload=False)

# uvicorn backend_cap:app --host 0.0.0.0 --port 8000
# tf-standalone\Scripts\Activate.ps1
# ngrok http 8000
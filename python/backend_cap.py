from fastapi import FastAPI, UploadFile, File
import uvicorn
import cv2
import numpy as np
from MODELTESTING import load_models_on_startup, recognize_face_in_frame

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
    """
    Receives a frame from the Flutter app, recognizes the face,
    and returns a JSON response.
    """
    try:
        contents = await frame.read()
        np_arr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            print("ERROR: Failed to decode image from app.")
            # --- FIX: Return valid JSON, not a string ---
            return {"name": "Error: Corrupt image", "sap_id": "N/A"}

        # This function (from MODELTESTING.py) is already safe
        # and returns a JSON dictionary.
        json_response = recognize_face_in_frame(img)
        
        print(f"Recognition result: {json_response}")
        return json_response

    except Exception as e:
        print(f"!!! CRITICAL ERROR in backend_cap.py endpoint: {e}")
        # --- FIX: Return valid JSON on any other crash ---
        return {"name": "Server Error", "sap_id": str(e)}

# No 'if __name__ == "__main__"' block needed
# Run with: uvicorn backend_cap:app --host 0.0.0.0 --port 8000
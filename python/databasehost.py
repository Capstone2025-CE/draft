from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, JSONResponse
import pandas as pd
import os

app = FastAPI()
EXCEL_PATH = "database.xlsx"

@app.get("/download")
def download_excel():
    if os.path.exists(EXCEL_PATH):
        return FileResponse(EXCEL_PATH, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename="database.xlsx")
    return Response("File not found", status_code=404)

@app.get("/data")
def get_data():
    if os.path.exists(EXCEL_PATH):
        df = pd.read_excel(EXCEL_PATH)
        return JSONResponse(df.to_dict(orient="records"))
    return Response("File not found", status_code=404)
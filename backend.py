import os
import json
import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from msal import ConfidentialClientApplication
from azure.storage.blob import BlobServiceClient

from blob_reader import read_metadata_from_blob, extract_worksheets

# =========================================================
# ENV
# =========================================================
load_dotenv()

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
BLOB_INPUT_CONTAINER = os.getenv("BLOB_INPUT_CONTAINER")


RUNTIME_TEMPLATE_BLOB = os.getenv("RUNTIME_TEMPLATE_BLOB")  # runtime_visuals.json



AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
API_ROOT = "https://api.powerbi.com/v1.0/myorg"

# =========================================================
# APP
# =========================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# MODELS
# =========================================================
class EmbedRequest(BaseModel):
    workspaceId: str
    reportId: str


class RuntimeVisualsRequest(BaseModel):
    metadataBlobPath: str


# =========================================================
# POWER BI AUTH
# =========================================================
def get_access_token() -> str:
    app_auth = ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    token = app_auth.acquire_token_for_client(scopes=SCOPE)
    return token["access_token"]


# =========================================================
# LOAD runtime_visuals TEMPLATE
# =========================================================
def load_runtime_template() -> dict:
    if not AZURE_STORAGE_CONNECTION_STRING or not BLOB_INPUT_CONTAINER :
        raise RuntimeError("Blob template configuration missing")

    blob_service = BlobServiceClient.from_connection_string(
        AZURE_STORAGE_CONNECTION_STRING
    )

    blob_client = blob_service.get_blob_client(
        container=BLOB_INPUT_CONTAINER,
        blob="runtime_visuals.json"
    )

    data = blob_client.download_blob().readall()
    return json.loads(data)


# =========================================================
# API 1️⃣ : EMBED TOKEN
# =========================================================
@app.post("/embed-token")
def generate_embed_token(data: EmbedRequest):
    try:
        access_token = get_access_token()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        report_url = f"{API_ROOT}/groups/{data.workspaceId}/reports/{data.reportId}"
        report_res = requests.get(report_url, headers=headers)

        if report_res.status_code != 200:
            raise HTTPException(report_res.status_code, "Failed to fetch report info")

        report_info = report_res.json()
        dataset_id = report_info["datasetId"]

        token_url = f"{API_ROOT}/groups/{data.workspaceId}/reports/{data.reportId}/GenerateToken"
        payload = {
            "accessLevel": "Edit",
            "allowSaveAs": True,
            "datasetId": dataset_id
        }

        token_res = requests.post(token_url, headers=headers, json=payload)

        if token_res.status_code != 200:
            raise HTTPException(token_res.status_code, "Failed to generate embed token")

        return {
            "embedToken": token_res.json()["token"],
            "embedUrl": report_info["embedUrl"],
            "datasetId": dataset_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# API 2️⃣ : GENERATE runtime_visuals.json (JSON ONLY)
# =========================================================
@app.post("/runtime-visuals")
def generate_runtime_visuals(req: RuntimeVisualsRequest):
    try:
        # 1️⃣ Read metadata from Blob
        metadata = read_metadata_from_blob(req.metadataBlobPath)
        worksheets = extract_worksheets(metadata)

        if not worksheets:
            raise ValueError("No worksheets found in metadata")

        # 2️⃣ Load template
        runtime_visuals = load_runtime_template()

        # 3️⃣ Build visuals (logic from main.py)
        visuals = []
        x, y = 40, 40

        for ws in worksheets:
            name = ws.get("name")
            columns = ws.get("columns")

            if not name or not columns:
                continue

            visuals.append({
                "type": "table",
                "title": name,
                "x": x,
                "y": y,
                "width": 600,
                "height": 300,
                "values": columns
            })

            y += 340

        if not visuals:
            raise ValueError("No visuals generated")

        runtime_visuals["visuals"] = visuals

        # ✅ RETURN JSON ONLY
        return {
            "status": "success",
            "visualCount": len(visuals),
            "runtime_visuals": runtime_visuals
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from datetime import datetime


app = FastAPI()

# A "Schema" for database teammates to connect
class ParkingDetection(BaseModel):
    spot_id: int
    license_plate: str
    confidence: float  # We may need to be sure the OCR is reliable before accepting it into our system

# Status of the API - time and date
@app.get("/")
def home():
    return {"status": "Smart Parking API is Online", "system_time": datetime.now()}

# Receiving data from the camera (OpenCV + OCR) and processing it
@app.post("/api/park/detection")

def record_detection(data: ParkingDetection):
    # If the OCR is blurry, reject it! Detection Rate may be too low to be useful
    if data.confidence < 0.6:
        raise HTTPException(status_code = 400, detail = "Plate is blurry, try again.")

    print(f"DEBUG: Spot {data.spot_id} occupied by {data.license_plate}")
    
    # FIXME: Here we would normally interact with the database to record the detection. For example:

    # new_record = TeammateModel(spot = data.spot_id, plate = data.license_plate)
    
    # db.add(new_record)
    
    # db.commit()

    return {
        "message": "Detection Received",

        "processed_at": datetime.now(),
        
        "details": data
    }

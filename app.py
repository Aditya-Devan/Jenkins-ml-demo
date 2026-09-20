"""FastAPI service that serves the trained model.

GET /health              -> {"status": "ok"}
GET /predict?x1=&x2=     -> {"prediction": 0|1, "confidence": float}
"""
import joblib
import numpy as np
from fastapi import FastAPI

app = FastAPI()
model = joblib.load("model.pkl")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/predict")
def predict(x1: float, x2: float):
    X = np.array([[x1, x2]])
    prediction = int(model.predict(X)[0])
    confidence = float(model.predict_proba(X)[0][prediction])
    return {"prediction": prediction, "confidence": round(confidence, 4)}

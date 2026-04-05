"""
MLflow helper utilities shared across model/ and api/.
"""

import os
import mlflow
import mlflow.transformers
from dotenv import load_dotenv

load_dotenv()

REGISTERED_MODEL = "finbert-signalforge"
CHAMPION_ALIAS = "champion"


def get_tracking_uri() -> str:
    return os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")


def load_champion_pipeline():
    """Load the @champion FinBERT pipeline from MLflow Model Registry."""
    mlflow.set_tracking_uri(get_tracking_uri())
    model_uri = f"models:/{REGISTERED_MODEL}@{CHAMPION_ALIAS}"
    return mlflow.transformers.load_model(model_uri)

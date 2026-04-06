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
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification

    mlflow.set_tracking_uri(get_tracking_uri())
    client = mlflow.MlflowClient()
    version = client.get_model_version_by_alias(REGISTERED_MODEL, CHAMPION_ALIAS)
    local_path = mlflow.artifacts.download_artifacts(version.source)
    tokenizer = AutoTokenizer.from_pretrained(local_path)
    model = AutoModelForSequenceClassification.from_pretrained(local_path)
    return pipeline("text-classification", model=model, tokenizer=tokenizer)

"""
Fine-tune ProsusAI/finbert on financial_phrasebank (all-agree split).
Logs every epoch to MLflow and registers the best checkpoint under
the model name 'finbert-signalforge'.

Usage:
    python model/finetune_finbert.py

After completion:
    Open http://localhost:5001 → Model Registry → finbert-signalforge
    → set alias 'champion' on the best run.
"""

import os
import numpy as np
from dotenv import load_dotenv

import mlflow
import mlflow.transformers
from datasets import load_dataset
from sklearn.metrics import f1_score, accuracy_score
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
)

load_dotenv()

MODEL_NAME = "ProsusAI/finbert"
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
REGISTERED_MODEL = "finbert-signalforge"
OUTPUT_DIR = "./model/finbert-finetuned"

# financial_phrasebank label order: negative=0, neutral=1, positive=2
LABEL2ID = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}


def load_data():
    ds = load_dataset("financial_phrasebank", "sentences_allagree", trust_remote_code=True)
    # financial_phrasebank only has a 'train' split — make a validation split
    split = ds["train"].train_test_split(test_size=0.15, seed=42)
    return split["train"], split["test"]


def tokenize(examples, tokenizer):
    return tokenizer(
        examples["sentence"],
        truncation=True,
        padding="max_length",
        max_length=128,
    )


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "f1": f1_score(labels, preds, average="weighted"),
        "accuracy": accuracy_score(labels, preds),
    }


def main():
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("finbert-signalforge")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=True,
    )

    train_ds, eval_ds = load_data()

    # Rename 'label' column to match HF Trainer expectations
    train_ds = train_ds.map(lambda ex: tokenize(ex, tokenizer), batched=True)
    eval_ds = eval_ds.map(lambda ex: tokenize(ex, tokenizer), batched=True)
    train_ds = train_ds.rename_column("label", "labels")
    eval_ds = eval_ds.rename_column("label", "labels")
    train_ds.set_format("torch", columns=["input_ids", "attention_mask", "labels"])
    eval_ds.set_format("torch", columns=["input_ids", "attention_mask", "labels"])

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        warmup_steps=100,
        weight_decay=0.01,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=20,
        report_to="none",  # we handle MLflow manually
        fp16=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    with mlflow.start_run(run_name="finbert-finetune") as run:
        mlflow.log_params({
            "base_model": MODEL_NAME,
            "dataset": "financial_phrasebank/sentences_allagree",
            "epochs": training_args.num_train_epochs,
            "batch_size": training_args.per_device_train_batch_size,
            "warmup_steps": training_args.warmup_steps,
            "weight_decay": training_args.weight_decay,
        })

        trainer.train()

        # Evaluate and log final metrics
        metrics = trainer.evaluate()
        mlflow.log_metrics({
            "eval_f1": metrics["eval_f1"],
            "eval_accuracy": metrics["eval_accuracy"],
            "eval_loss": metrics["eval_loss"],
        })

        print(f"\n{'='*50}")
        print(f"  Final F1:       {metrics['eval_f1']:.4f}  (target > 0.85)")
        print(f"  Final Accuracy: {metrics['eval_accuracy']:.4f}  (target > 0.88)")
        print(f"{'='*50}\n")

        # Log model to MLflow
        pipeline_components = {"model": trainer.model, "tokenizer": tokenizer}
        mlflow.transformers.log_model(
            transformers_model=pipeline_components,
            artifact_path="finbert-signalforge",
            registered_model_name=REGISTERED_MODEL,
            task="text-classification",
        )

        print(f"Model registered as '{REGISTERED_MODEL}' in MLflow.")
        print(f"Run ID: {run.info.run_id}")
        print(f"\nNext step:")
        print(f"  Open http://localhost:5001 → Model Registry → {REGISTERED_MODEL}")
        print(f"  Click the latest version → Set Alias → 'champion'")


if __name__ == "__main__":
    main()

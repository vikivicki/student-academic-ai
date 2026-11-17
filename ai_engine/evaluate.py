
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "evaluation" / "evaluation.csv"

print("Starting RMSE evaluation...")

df = pd.read_csv(CSV_FILE)

expected = pd.to_numeric(df["rule_value"], errors="coerce")
predicted = pd.to_numeric(df["final_answer"], errors="coerce")

if expected.isna().any() or predicted.isna().any():
    raise ValueError("Invalid numeric values in evaluation.csv")

rmse = np.sqrt(np.mean((expected - predicted) ** 2))

print("Number of evaluation records:", len(df))
print("Provisional RMSE:", round(rmse, 4))
print("WARNING: These are test values, not actual agent evaluation results.")

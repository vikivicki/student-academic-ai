from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_ROOT = BASE_DIR / "data" / "colleges"
FILES = ("students", "courses", "assessments", "attendance", "mentors")


def load_datasets(college_id):
    """Load only CSV files belonging to the authenticated college."""
    if not college_id or any(ch not in "0123456789abcdef" for ch in college_id.lower()):
        raise ValueError("Invalid college identifier.")
    data_dir = DATA_ROOT / college_id / "csv"
    if not data_dir.is_dir():
        raise FileNotFoundError("Create this college's data/colleges/<college_id>/csv folder.")
    missing = [f"{name}.csv" for name in FILES if not (data_dir / f"{name}.csv").is_file()]
    if missing:
        raise FileNotFoundError("Missing college CSV files: " + ", ".join(missing))
    return {name: pd.read_csv(data_dir / f"{name}.csv") for name in FILES}

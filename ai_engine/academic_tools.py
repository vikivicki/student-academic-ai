
from datetime import date, datetime
from data_loader import load_datasets


REFERENCE_DATE = date(2025, 1, 15)


def _match(df, column, value):
    """Find matching records without case sensitivity."""

    if column not in df.columns:
        raise ValueError(f"Required column '{column}' is missing.")

    return df[
        df[column].astype(str).str.upper()
        == str(value).upper()
    ]


def _parse_date(value):
    """Convert supported date formats into date objects."""

    if value is None or str(value).strip() == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def _get_cutoff(as_of=None):
    """Use the default date unless another date is specified."""

    if as_of is None:
        return REFERENCE_DATE

    cutoff = _parse_date(as_of)

    if cutoff is None:
        raise ValueError("Invalid evaluation date.")

    return cutoff


def _filter_dataframe(df, date_column, cutoff):
    """
    Filter records up to and including the cutoff date.
    Return records and filtering information.
    """

    if date_column not in df.columns:
        return {
            "records": df.to_dict(orient="records"),
            "date_filter_applied": False,
            "excluded_future_records": 0,
            "warning": (
                f"Cannot apply date filtering: "
                f"'{date_column}' column is missing."
            )
        }

    parsed_dates = df[date_column].apply(_parse_date)

    if parsed_dates.isna().any():
        return {
            "records": [],
            "date_filter_applied": False,
            "excluded_future_records": 0,
            "error": (
                f"Some records have missing or invalid "
                f"dates in '{date_column}'. "
                "Cannot verify the complete date-filtered dataset."
            )
        }

    valid_rows = parsed_dates <= cutoff

    filtered = df.loc[valid_rows]

    return {
        "records": filtered.to_dict(orient="records"),
        "date_filter_applied": True,
        "reference_date": cutoff.isoformat(),
        "excluded_future_records": int((~valid_rows).sum())
    }


def get_student_details(student_id, college_id):
    """Retrieve a student from the authenticated college."""

    data = load_datasets(college_id)

    result = _match(
        data["students"],
        "student_id",
        student_id
    )

    if result.empty:
        return {"error": "Student not found in this college"}

    return result.to_dict(orient="records")[0]


def get_attendance(student_id, college_id, as_of=None):
    """
    Retrieve attendance records.

    Attendance date filtering is possible only if the CSV
    contains an attendance_date column.
    """

    data = load_datasets(college_id)

    result = _match(
        data["attendance"],
        "student_id",
        student_id
    )

    if result.empty:
        return {
            "error": "Attendance record not found in this college"
        }

    cutoff = _get_cutoff(as_of)

    return _filter_dataframe(
        result,
        "attendance_date",
        cutoff
    )


def get_student_marks(student_id, college_id, as_of=None):
    """Retrieve assessment records up to the evaluation date."""

    data = load_datasets(college_id)

    result = _match(
        data["assessments"],
        "student_id",
        student_id
    )

    if result.empty:
        return {
            "error": "Assessment records not found in this college"
        }

    cutoff = _get_cutoff(as_of)

    return _filter_dataframe(
        result,
        "assessment_date",
        cutoff
    )


def get_course_details(course_id, college_id):
    """Retrieve course information from the authenticated college."""

    data = load_datasets(college_id)

    result = _match(
        data["courses"],
        "course_id",
        course_id
    )

    if result.empty:
        return {"error": "Course not found in this college"}

    return result.to_dict(orient="records")[0]


def get_mentor_details(course_id, college_id):
    """Retrieve mentor information from the authenticated college."""

    data = load_datasets(college_id)

    result = _match(
        data["mentors"],
        "course_id",
        course_id
    )

    if result.empty:
        return {"error": "Mentor not found in this college"}

    return result.to_dict(orient="records")


def get_student_count(college_id):
    """Count students in the authenticated college only."""

    data = load_datasets(college_id)

    return {
        "total_students": len(data["students"])
    }

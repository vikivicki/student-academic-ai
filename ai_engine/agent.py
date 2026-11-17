
import os
import json
import re
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage
)
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from academic_tools import (
    get_student_details,
    get_attendance,
    get_student_marks,
    get_course_details,
    get_mentor_details,
    get_student_count
)


# =====================================================
# 1. CONFIGURATION
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
COLLEGES_DIR = BASE_DIR / "data" / "colleges"

REFERENCE_DATE = date(2025, 1, 15)

load_dotenv(BASE_DIR / ".env", override=True)

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError(
        "GROQ_API_KEY not found. Check the backend .env file."
    )

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    temperature=0,
    api_key=api_key
)

_embeddings = None


# =====================================================
# 2. EMBEDDING MODEL
# =====================================================

def get_embeddings():
    """Load the embedding model once and reuse it."""

    global _embeddings

    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

    return _embeddings


# =====================================================
# 3. REFERENCE DATE HANDLING
# =====================================================

def get_cutoff_date(cutoff_date=None):
    """Default to 15 January 2025."""

    if cutoff_date is None or str(cutoff_date).strip() == "":
        return REFERENCE_DATE

    try:
        return date.fromisoformat(str(cutoff_date).strip())
    except ValueError:
        raise ValueError("Invalid date. Use YYYY-MM-DD format.")


# =====================================================
# 4. MAIN AGENT
# =====================================================

def ask_agent(
    question: str,
    college_id: str,
    student_id: str = None
):
    """
    Multi-college Student Academics Agent.

    College ID must come from authenticated college login.
    Student ID must come from authenticated student login.
    """

    # -------------------------------------------------
    # VALIDATE INPUT
    # -------------------------------------------------

    if (
        not college_id
        or not re.fullmatch(r"[0-9a-fA-F]+", college_id)
    ):
        return "Invalid college identity."

    if not question or not question.strip():
        return "Please enter an academic question."

    if student_id is not None and not str(student_id).strip():
        return "Invalid student identity."

    college_dir = COLLEGES_DIR / college_id

    if not college_dir.is_dir():
        return "College data directory not found."

    # -------------------------------------------------
    # LOAD COLLEGE-SPECIFIC FAISS INDEX
    # -------------------------------------------------

    faiss_dir = college_dir / "faiss_index"

    vector_store = None

    if (
        (faiss_dir / "index.faiss").exists()
        and (faiss_dir / "index.pkl").exists()
    ):
        try:
            vector_store = FAISS.load_local(
                str(faiss_dir),
                get_embeddings(),
                allow_dangerous_deserialization=True
            )

        except Exception as exc:
            return (
                "Could not load college policy index: "
                f"{type(exc).__name__}: {exc}"
            )

    # =================================================
    # TOOL 1: COUNT STUDENTS
    # =================================================

    @tool
    def count_registered_students():
        """Count students registered in the authenticated college."""

        return get_student_count(college_id)

    # =================================================
    # TOOL 2: STUDENT DETAILS
    # =================================================

    @tool
    def student_details(student_id_arg: str):
        """Retrieve student details using student ID."""

        if (
            student_id
            and student_id_arg.upper() != student_id.upper()
        ):
            return {
                "error": "You can only access your own student record."
            }

        return get_student_details(
            student_id_arg,
            college_id
        )

    # =================================================
    # TOOL 3: ATTENDANCE DETAILS
    # =================================================

    @tool
    def attendance_details(
        student_id_arg: str,
        cutoff_date: str = "2025-01-15"
    ):
        """Retrieve attendance records up to the evaluation date."""

        if (
            student_id
            and student_id_arg.upper() != student_id.upper()
        ):
            return {
                "error": "You can only access your own student record."
            }

        evaluation_date = get_cutoff_date(cutoff_date)

        return get_attendance(
            student_id_arg,
            college_id,
            evaluation_date
        )

    # =================================================
    # TOOL 4: STUDENT MARKS
    # =================================================

    @tool
    def student_marks(
        student_id_arg: str,
        cutoff_date: str = "2025-01-15"
    ):
        """Retrieve assessment marks up to the evaluation date."""

        if (
            student_id
            and student_id_arg.upper() != student_id.upper()
        ):
            return {
                "error": "You can only access your own student record."
            }

        evaluation_date = get_cutoff_date(cutoff_date)

        return get_student_marks(
            student_id_arg,
            college_id,
            evaluation_date
        )

    # =================================================
    # TOOL 5: COURSE DETAILS
    # =================================================

    @tool
    def course_details(course_id: str):
        """Retrieve course information using course ID."""

        return get_course_details(
            course_id,
            college_id
        )

    # =================================================
    # TOOL 6: MENTOR DETAILS
    # =================================================

    @tool
    def mentor_details(course_id: str):
        """Retrieve mentor information using course ID."""

        return get_mentor_details(
            course_id,
            college_id
        )

    # =================================================
    # TOOL 7: ACADEMIC POLICY SEARCH
    # =================================================

    @tool
    def search_academic_policies(policy_question: str):
        """Search college policies using FAISS MMR retrieval."""

        if vector_store is None:
            return {
                "error": "This college has no available policy index."
            }

        results = vector_store.max_marginal_relevance_search(
            policy_question,
            k=3,
            fetch_k=10,
            lambda_mult=0.5
        )

        if not results:
            return {
                "message": "No relevant academic policy found."
            }

        return "\n\n".join(
            (
                f"Policy source: "
                f"{Path(doc.metadata.get('source', 'Academic policy')).name}\n"
                f"Policy content:\n{doc.page_content}"
            )
            for doc in results
        )

    # =================================================
    # TOOL 8: ATTENDANCE CALCULATION
    # =================================================

    @tool
    def calculate_attendance_percentage(
        classes_attended: float,
        total_classes: float
    ):
        """Calculate attendance percentage."""

        if total_classes <= 0:
            return {
                "error": "Total classes must be greater than zero."
            }

        if (
            classes_attended < 0
            or classes_attended > total_classes
        ):
            return {
                "error": "Invalid attendance values."
            }

        percentage = (
            classes_attended / total_classes
        ) * 100

        return {
            "formula": "(Classes Attended / Total Classes) * 100",
            "classes_attended": classes_attended,
            "total_classes": total_classes,
            "attendance_percentage": round(percentage, 2)
        }

    # =================================================
    # TOOL 9: MARKS CALCULATION
    # =================================================

    @tool
    def calculate_marks_percentage(
        marks_obtained: float,
        total_marks: float
    ):
        """Calculate assessment marks percentage."""

        if total_marks <= 0:
            return {
                "error": "Total marks must be greater than zero."
            }

        if (
            marks_obtained < 0
            or marks_obtained > total_marks
        ):
            return {
                "error": "Invalid marks values."
            }

        percentage = (
            marks_obtained / total_marks
        ) * 100

        return {
            "formula": "(Marks Obtained / Total Marks) * 100",
            "marks_obtained": marks_obtained,
            "total_marks": total_marks,
            "marks_percentage": round(percentage, 2)
        }

    # =================================================
    # TOOL 10: ACADEMIC ELIGIBILITY
    # =================================================

    @tool
    def check_academic_eligibility(
        student_id_arg: str,
        minimum_attendance: float,
        minimum_marks: float,
        cutoff_date: str = "2025-01-15"
    ):
        """
        Evaluate eligibility using attendance, required
        assessments and the college completion policy.
        """

        if (
            student_id
            and student_id_arg.upper() != student_id.upper()
        ):
            return {
                "status": "cannot_determine",
                "reason": "You can only check your own eligibility."
            }

        if not 0 <= minimum_attendance <= 100:
            return {
                "status": "cannot_determine",
                "reason": "Invalid minimum attendance threshold."
            }

        if not 0 <= minimum_marks <= 100:
            return {
                "status": "cannot_determine",
                "reason": "Invalid minimum marks threshold."
            }

        evaluation_date = get_cutoff_date(cutoff_date)

        # 1. Retrieve student information.

        student_data = get_student_details(
            student_id_arg,
            college_id
        )

        if (
            not isinstance(student_data, dict)
            or student_data.get("error")
        ):
            return {
                "status": "cannot_determine",
                "reason": "Student details could not be verified."
            }

        course_id = str(
            student_data.get("course_id", "")
        ).strip()

        if not course_id:
            return {
                "status": "cannot_determine",
                "reason": "Student's enrolled course is unavailable."
            }

        # 2. Read the required assessment inventory.

        policy_file = (
            college_dir
            / "policies"
            / "course_completion_policy.md"
        )

        if not policy_file.is_file():
            return {
                "status": "cannot_determine",
                "reason": "Course completion policy file is missing."
            }

        policy_text = policy_file.read_text(encoding="utf-8")

        inventory = {}

        
    

        for line in policy_text.splitlines():
            match = re.match(
                r"^\s*[-*]\s*([A-Za-z0-9_-]+)\s*[\u2014\u2013-]\s*(.+?)\s*$",
                line
            )

            if match:
                inventory.setdefault(
                    match.group(1).upper(), []
                ).append(match.group(2).strip())

        print("\n===== ELIGIBILITY DEBUG =====")
        print("College ID:", college_id)
        print("College directory:", college_dir)
        print("Policy file:", policy_file)
        print("Policy exists:", policy_file.is_file())
        print("Course ID:", repr(course_id))
        print("Parsed inventory:", repr(inventory))
        print("=============================\n")       

        required_assessments = inventory.get(
            course_id.upper(),
            []
        )

        if not required_assessments:
            return {
                "status": "cannot_determine",
                "reason": (
                    f"No required assessment inventory was found "
                    f"for course {course_id}."
                ),
                "reference_date": evaluation_date.isoformat()
            }

        # 3. Retrieve date-filtered academic records.

        attendance_data = get_attendance(
            student_id_arg,
            college_id,
            evaluation_date
        )

        marks_data = get_student_marks(
            student_id_arg,
            college_id,
            evaluation_date
        )

        if attendance_data.get("error"):
            return {
                "status": "cannot_determine",
                "reason": attendance_data["error"]
            }

        if marks_data.get("error"):
            return {
                "status": "cannot_determine",
                "reason": marks_data["error"]
            }

        if not attendance_data.get("date_filter_applied", False):
            return {
                "status": "cannot_determine",
                "reason": "Attendance date filtering could not be verified."
            }

        if not marks_data.get("date_filter_applied", False):
            return {
                "status": "cannot_determine",
                "reason": "Assessment date filtering could not be verified."
            }

        attendance_records = attendance_data.get("records", [])
        assessment_records = marks_data.get("records", [])

        # 4. Calculate attendance for the enrolled course.

        course_attendance = [
            record
            for record in attendance_records
            if str(record.get("course_id", "")).upper()
            == course_id.upper()
        ]

        total_classes = sum(
            float(record.get("total_classes", 0))
            for record in course_attendance
        )

        attended_classes = sum(
            float(record.get("classes_attended", 0))
            for record in course_attendance
        )

        if total_classes <= 0:
            attendance_percentage = None
        else:
            attendance_percentage = round(
                attended_classes / total_classes * 100,
                2
            )

        # 5. Verify all required assessments.

        assessment_results = []
        missing_assessments = []
        failed_assessments = []

        for required_name in required_assessments:

            matching_records = [
                record
                for record in assessment_records
                if (
                    str(record.get("course_id", "")).upper()
                    == course_id.upper()
                    and " ".join(
                        str(
                            record.get("assessment_name", "")
                        ).casefold().split()
                    )
                    == " ".join(
                        required_name.casefold().split()
                    )
                )
            ]

            if len(matching_records) == 0:
                missing_assessments.append(required_name)
                continue

            if len(matching_records) > 1:
                return {
                    "status": "cannot_determine",
                    "reason": (
                        f"Multiple records found for {required_name}. "
                        "Manual verification is required."
                    ),
                    "reference_date": evaluation_date.isoformat()
                }

            record = matching_records[0]

            try:
                obtained = float(record["marks_obtained"])
                maximum = float(record["total_marks"])
            except (KeyError, TypeError, ValueError):
                return {
                    "status": "cannot_determine",
                    "reason": (
                        f"Invalid marks record for {required_name}."
                    )
                }

            if (
                maximum <= 0
                or obtained < 0
                or obtained > maximum
            ):
                return {
                    "status": "cannot_determine",
                    "reason": (
                        f"Invalid marks values for {required_name}."
                    )
                }

            percentage = round(
                obtained / maximum * 100,
                2
            )

            result = {
                "assessment": required_name,
                "marks_obtained": obtained,
                "total_marks": maximum,
                "percentage": percentage,
                "passed": percentage >= minimum_marks
            }

            assessment_results.append(result)

            if not result["passed"]:
                failed_assessments.append(required_name)

        # 6. Determine eligibility.

        reasons = []

        if attendance_percentage is None:
            reasons.append(
                "Attendance records are missing for the enrolled course."
            )

        elif attendance_percentage < minimum_attendance:
            reasons.append(
                f"Attendance {attendance_percentage}% is below "
                f"the required {minimum_attendance}%."
            )

        if missing_assessments:
            reasons.append(
                "Missing required assessments: "
                + ", ".join(missing_assessments)
            )

        if failed_assessments:
            reasons.append(
                "Failed required assessments: "
                + ", ".join(failed_assessments)
            )

        if (
            attendance_percentage is None
            or missing_assessments
        ):
            eligibility_status = "PENDING"

        elif (
            attendance_percentage < minimum_attendance
            or failed_assessments
        ):
            eligibility_status = "NOT ELIGIBLE"

        else:
            eligibility_status = "ELIGIBLE"

        return {
            "status": "evaluated",
            "eligibility_status": eligibility_status,
            "student_id": student_id_arg,
            "course_id": course_id,
            "reference_date": evaluation_date.isoformat(),
            "attendance": {
                "classes_attended": attended_classes,
                "total_classes": total_classes,
                "percentage": attendance_percentage,
                "minimum_required": minimum_attendance
            },
            "assessments": assessment_results,
            "required_assessments": required_assessments,
            "missing_assessments": missing_assessments,
            "failed_assessments": failed_assessments,
            "minimum_marks": minimum_marks,
            "reasons": reasons
        }

    # =================================================
    # REGISTER ALL TOOLS
    # =================================================

    tools = [
        count_registered_students,
        student_details,
        attendance_details,
        student_marks,
        course_details,
        mentor_details,
        search_academic_policies,
        calculate_attendance_percentage,
        calculate_marks_percentage,
        check_academic_eligibility
    ]

    llm_with_tools = llm.bind_tools(tools)

    # =================================================
    # 5. SYSTEM PROMPT
    # =================================================

    system_text = f"""
You are the Student Academics Agent for SkillBridge EdTech.

AUTHENTICATED COLLEGE:
{college_id}

DEFAULT REFERENCE DATE:
15 January 2025

ACADEMIC DATA RULES:

1. Use only the authenticated college CSV datasets.
2. Use only the authenticated college FAISS policy index.
3. Never access another college's information.
4. Never invent student records, marks, attendance or policies.
5. Use tools to retrieve academic information.
6. Use Python calculation tools for percentages.
7. Retrieve policy thresholds before evaluating eligibility.
8. Explain formulas and calculation results.
9. Never treat missing information as zero.
10. Disclose unavailable information.

REFERENCE DATE RULES:

1. Default date is 15 January 2025.
2. Ignore records after the evaluation date.
3. Never invent dates for records without date fields.
4. Use one consistent date snapshot.
5. Disclose when date filtering cannot be verified.

ELIGIBILITY RULES:

1. Retrieve attendance and assessment policies.
2. Use the policy thresholds.
3. The attendance requirement for this demo is 75%.
4. The minimum assessment marks requirement for this demo is 40%.
5. The eligibility tool reads required assessment inventory
   from the authenticated college policy file.
6. Call check_academic_eligibility with the correct thresholds.
7. Never override the Python eligibility result.
8. Never declare eligibility when the tool returns
   cannot_determine.
9. Explain missing or failed assessments.

STUDENT PRIVACY:

1. Students can access only their own records.
2. Never reveal another student's personal information.
3. Do not accept a different student ID from the user.

POLICY ANSWERS:

1. Search the authenticated college policy index.
2. Mention policy filenames when available.
3. Never invent policy rules.
4. Disclose when no relevant policy is found.

AGENT BEHAVIOUR:

Use tools whenever student records, calculations,
policy retrieval, course details, mentor information
or eligibility decisions are required.

Never claim a tool succeeded unless its output confirms it.
"""

    if student_id:
        system_text += f"""

AUTHENTICATED STUDENT ID:
{student_id}

This student may access only their own academic records.
"""

    messages = [
        SystemMessage(content=system_text),
        HumanMessage(content=question)
    ]

    # =================================================
    # 6. AGENTIC TOOL-CALLING LOOP
    # =================================================

    for _ in range(10):

        response = llm_with_tools.invoke(messages)

        messages.append(response)

        if not response.tool_calls:
            return response.content

        for call in response.tool_calls:

            selected_tool = next(
                (
                    item
                    for item in tools
                    if item.name == call["name"]
                ),
                None
            )

            try:

                if selected_tool is None:
                    result = {
                        "error": "Requested tool not found."
                    }

                else:
                    result = selected_tool.invoke(
                        call["args"]
                    )

            except Exception as exc:

                result = {
                    "error": f"{type(exc).__name__}: {exc}"
                }

            # AUTHORITATIVE ELIGIBILITY RESULT

            if (
                selected_tool is not None
                and selected_tool.name
                == "check_academic_eligibility"
                and isinstance(result, dict)
            ):

                if result.get("status") == "cannot_determine":

                    return (
                        "Eligibility Status: CANNOT DETERMINE\n"
                        "Reason: "
                        + result.get(
                            "reason",
                            "Required information is unavailable."
                        )
                        + "\nReference Date: "
                        + result.get(
                            "reference_date",
                            "Not available"
                        )
                    )

                if result.get("status") == "evaluated":
                    return json.dumps(
                        result,
                        indent=2
                    )

            messages.append(
                ToolMessage(
                    content=json.dumps(
                        result,
                        default=str
                    ) if isinstance(result, (dict, list))
                    else str(result),
                    tool_call_id=call["id"]
                )
            )

    return (
        "The agent reached its maximum tool-call limit. "
        "Please try a more specific question."
    )

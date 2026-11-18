import os
import re
import hmac
import hashlib
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

BASE_DIR = Path(__file__).resolve().parent
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env", override=True)


STORAGE_DIR = Path(os.getenv("STORAGE_DIR", str(BASE_DIR)))

DB_PATH = STORAGE_DIR / "college_portal.db"
LOGO_DIR = STORAGE_DIR / "uploads" / "logos"
DATA_ROOT = BASE_DIR / "data" / "colleges"
TOKEN_TTL = 60 * 60 * 12

app = FastAPI(
    title="Multi-College Student Academics Agent",
    description="College-branded, tenant-isolated academic assistant API",
    version="2.0.0",
)

origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:5000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in origins if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer = HTTPBearer(auto_error=False)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS colleges (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
            logo_path TEXT, created_at INTEGER NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, college_id TEXT NOT NULL,
            full_name TEXT NOT NULL, email TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','student')),
            student_id TEXT, created_at INTEGER NOT NULL,
            UNIQUE(college_id, email),
            FOREIGN KEY(college_id) REFERENCES colleges(id)
        )""")


@app.on_event("startup")
def startup():
    init_db()


def password_hash(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = password_hash(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
        return hmac.compare_digest(candidate, digest_hex)
    except Exception:
        return False


def make_token(user: dict) -> str:
    secret = os.getenv("APP_SECRET_KEY")
    if not secret or len(secret) < 32:
        raise HTTPException(500, "APP_SECRET_KEY must be set to a random value of at least 32 characters.")
    import json, base64
    payload = {
        "sub": user["id"], "college_id": user["college_id"],
        "role": user["role"], "name": user["full_name"],
        "exp": int(time.time()) + TOKEN_TTL,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).digest()
    return raw.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, "Please log in.")
    secret = os.getenv("APP_SECRET_KEY")
    if not secret or len(secret) < 32:
        raise HTTPException(500, "Server authentication is not configured.")
    import json, base64
    try:
        body, signature = credentials.credentials.split(".", 1)
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if payload["exp"] < time.time():
            raise ValueError()
        return payload
    except Exception:
        raise HTTPException(401, "Invalid or expired login token.")


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "College administrator access required.")
    return user


class CollegeSignup(BaseModel):
    college_name: str = Field(min_length=2, max_length=120)
    college_slug: str = Field(
    min_length=2,
    max_length=50,
    pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
)
    admin_name: str = Field(min_length=2, max_length=100)
    admin_email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    college_slug: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    student_id: str = Field(min_length=1, max_length=50)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@app.get("/")
def home():
    return {"message": "Multi-College Student Academics Agent API is running."}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/auth/register-college")
def register_college(data: CollegeSignup):
    """Public first-time setup: creates a college and its first administrator."""
    college_id = secrets.token_hex(8)
    slug = data.college_slug.lower()
    with db() as conn:
        if conn.execute("SELECT 1 FROM colleges WHERE slug=?", (slug,)).fetchone():
            raise HTTPException(409, "That college URL name is already registered.")
        conn.execute(
            "INSERT INTO colleges(id,name,slug,created_at) VALUES(?,?,?,?)",
            (college_id, data.college_name.strip(), slug, int(time.time())),
        )
        conn.execute(
            """INSERT INTO users(college_id,full_name,email,password_hash,role,created_at)
               VALUES(?,?,?,?,?,?)""",
            (college_id, data.admin_name.strip(), data.admin_email.lower(),
             password_hash(data.password), "admin", int(time.time())),
        )
    (DATA_ROOT / college_id / "csv").mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / college_id / "policies").mkdir(parents=True, exist_ok=True)
    return {"message": "College created. Log in with your college URL name and administrator account.",
            "college_id": college_id, "college_slug": slug}


@app.post("/auth/login")
def login(data: LoginRequest):
    with db() as conn:
        row = conn.execute(
            """SELECT u.*, c.name AS college_name, c.slug, c.logo_path
               FROM users u JOIN colleges c ON c.id=u.college_id
               WHERE c.slug=? AND lower(u.email)=lower(?)""",
            (data.college_slug.lower(), data.email),
        ).fetchone()
    if not row or not verify_password(data.password, row["password_hash"]):
        raise HTTPException(401, "College, email, or password is incorrect.")
    user = dict(row)
    token = make_token(user)
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": user["id"], "name": user["full_name"], "email": user["email"],
                 "role": user["role"], "student_id": user["student_id"]},
        "college": {"id": user["college_id"], "name": user["college_name"],
                    "slug": user["slug"], "logo_url": user["logo_path"]},
    }


@app.get("/auth/me")
def me(user=Depends(current_user)):
    with db() as conn:
        college = conn.execute("SELECT name,slug,logo_path FROM colleges WHERE id=?",
                               (user["college_id"],)).fetchone()
    return {"user": user, "college": dict(college) if college else None}


@app.post("/admin/students")
def create_student(data: StudentCreate, admin=Depends(admin_user)):
    with db() as conn:
        try:
            conn.execute(
                """INSERT INTO users(college_id,full_name,email,password_hash,role,student_id,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (admin["college_id"], data.full_name.strip(), data.email.lower(),
                 password_hash(data.password), "student", data.student_id.strip(), int(time.time())),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "A user with this email already exists in this college.")
    return {"message": "Student account created."}


@app.get("/admin/students")
def list_students(admin=Depends(admin_user)):
    with db() as conn:
        rows = conn.execute(
            """SELECT id,full_name,email,student_id,created_at FROM users
               WHERE college_id=? AND role='student' ORDER BY full_name""",
            (admin["college_id"],),
        ).fetchall()
    return {"students": [dict(r) for r in rows]}


@app.post("/college/logo")
async def upload_logo(file: UploadFile = File(...), user=Depends(admin_user)):
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, "Upload a PNG, JPG, JPEG, or WEBP logo.")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(400, "Logo must be 2 MB or smaller.")
    # Check basic file signatures instead of trusting the extension.
    signatures = {
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
    }
    if not signatures[suffix]:
        raise HTTPException(400, "The uploaded file does not match its image type.")
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{user['college_id']}{suffix}"
    path = LOGO_DIR / filename
    path.write_bytes(content)
    url = f"/uploads/logos/{filename}"
    with db() as conn:
        conn.execute("UPDATE colleges SET logo_path=? WHERE id=?", (url, user["college_id"]))
    return {"logo_url": url}


@app.get("/college/profile")
def college_profile(user=Depends(current_user)):
    with db() as conn:
        row = conn.execute("SELECT id,name,slug,logo_path FROM colleges WHERE id=?",
                           (user["college_id"],)).fetchone()
    return dict(row) if row else {}


@app.post("/chat")
def chat(request: ChatRequest, user=Depends(current_user)):
    # Student requests are automatically restricted to the signed-in student's ID.
    try:
        from agent import ask_agent
        answer = ask_agent(
            request.question,
            college_id=user["college_id"],
            student_id=user.get("student_id"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, f"College knowledge base is not ready: {exc}")
    except Exception as exc:
        raise HTTPException(503, f"Academic assistant could not start: {type(exc).__name__}")
    return {"question": request.question, "answer": answer}


# Static logo serving
from fastapi.staticfiles import StaticFiles
LOGO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads/logos", StaticFiles(directory=str(LOGO_DIR)), name="logos")

import json
import hashlib
import secrets
import mimetypes
import sys
import difflib
import re
import unicodedata
import os
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("SQLITE_DB_PATH") or ROOT / "xdu_partner.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        raise RuntimeError("云端 PostgreSQL 模式需要安装 psycopg2-binary") from exc
    DB_ERROR_TYPES = (psycopg2.DatabaseError,)
    DB_INTEGRITY_ERROR_TYPES = (psycopg2.IntegrityError,)
else:
    DB_ERROR_TYPES = (sqlite3.DatabaseError,)
    DB_INTEGRITY_ERROR_TYPES = (sqlite3.IntegrityError,)

TYPE_FIELDS = {
    "meal": ["restaurant", "location", "timeCost", "dish", "budget", "mealTime"],
    "study": ["place", "subject", "studyTime", "style", "duration", "frequency"],
    "run": ["route", "pace", "distance", "runTime", "goal", "intensity"],
    "ball": ["sport", "court", "level", "ballTime", "mode", "equipment"],
}

CONCEPT_ALIASES = {
    "operating_system": ["操作系统", "os", "operating system", "operatingsystem"],
    "computer_network": ["计算机网络", "计网", "computer network", "network", "networks"],
    "data_structure": ["数据结构", "ds", "data structure", "datastructure"],
    "computer_organization": ["计算机组成原理", "组成原理", "计组", "computer organization", "coa"],
    "database": ["数据库", "db", "database", "sql", "mysql", "sqlite"],
    "algorithm": ["算法", "algorithm", "algorithms"],
    "compiler": ["编译原理", "compiler", "compilers"],
    "software_engineering": ["软件工程", "软工", "software engineering", "se"],
    "machine_learning": ["机器学习", "ml", "machine learning"],
    "deep_learning": ["深度学习", "dl", "deep learning"],
    "artificial_intelligence": ["人工智能", "ai", "artificial intelligence"],
    "advanced_math": ["高等数学", "高数", "calculus", "advanced mathematics"],
    "linear_algebra": ["线性代数", "线代", "linear algebra"],
    "probability": ["概率论", "概率统计", "概率论与数理统计", "probability"],
    "discrete_math": ["离散数学", "离散", "discrete math", "discrete mathematics"],
    "college_english": ["大学英语", "英语", "english"],
    "cet4": ["四级", "英语四级", "cet4", "cet-4"],
    "cet6": ["六级", "英语六级", "cet6", "cet-6"],
    "postgraduate_exam": ["考研", "研究生考试", "postgraduate exam"],
    "cs408": ["408", "计算机专业基础综合", "计算机统考"],
    "python": ["python", "py", "Python"],
    "c_language": ["c语言", "c language", "clang"],
    "cpp": ["c++", "cpp", "cplusplus"],
    "java": ["java", "Java"],
    "web": ["web", "前端", "frontend", "html", "css", "javascript", "js"],
    "signal_system": ["信号与系统", "信号系统", "signal and system"],
    "digital_circuit": ["数字电路", "数电", "digital circuit"],
    "analog_circuit": ["模拟电路", "模电", "analog circuit"],
    "basketball": ["篮球", "basketball"],
    "badminton": ["羽毛球", "羽球", "badminton"],
    "table_tennis": ["乒乓球", "乒乓", "table tennis", "pingpong", "ping pong"],
    "football": ["足球", "football", "soccer"],
    "tennis": ["网球", "tennis"],
}

LATIN_SHORT_ALIASES = {
    "os", "ds", "db", "ml", "dl", "ai", "se", "py", "js"
}


def get_db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def sql(query):
    return query.replace("?", "%s") if USE_POSTGRES else query


def db_execute(conn, query, params=()):
    cursor = conn.cursor()
    cursor.execute(sql(query), params)
    return cursor


def db_fetchone(conn, query, params=()):
    cursor = db_execute(conn, query, params)
    return cursor.fetchone()


def db_fetchall(conn, query, params=()):
    cursor = db_execute(conn, query, params)
    return cursor.fetchall()


def created_id(cursor):
    if USE_POSTGRES:
        row = cursor.fetchone()
        return row["id"]
    return cursor.lastrowid


def serialize_time(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def init_db():
    with get_db() as conn:
        if USE_POSTGRES:
            schema = [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    student_id TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    department TEXT NOT NULL,
                    grade TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    nickname TEXT NOT NULL,
                    department TEXT NOT NULL,
                    grade TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    note TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES posts(id),
                    candidate_id INTEGER NOT NULL REFERENCES posts(id),
                    decision TEXT NOT NULL CHECK (decision IN ('accept', 'reject')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(post_id, candidate_id)
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS matches (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES posts(id),
                    candidate_id INTEGER NOT NULL REFERENCES posts(id),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(post_id, candidate_id)
                )
                """,
            ]
            for statement in schema:
                db_execute(conn, statement)
            columns = {
                row["column_name"]
                for row in db_fetchall(
                    conn,
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'posts'
                    """,
                )
            }
        else:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    department TEXT NOT NULL,
                    grade TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    nickname TEXT NOT NULL,
                    department TEXT NOT NULL,
                    grade TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    note TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    candidate_id INTEGER NOT NULL,
                    decision TEXT NOT NULL CHECK (decision IN ('accept', 'reject')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(post_id, candidate_id),
                    FOREIGN KEY(post_id) REFERENCES posts(id),
                    FOREIGN KEY(candidate_id) REFERENCES posts(id)
                );

                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    candidate_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(post_id, candidate_id),
                    FOREIGN KEY(post_id) REFERENCES posts(id),
                    FOREIGN KEY(candidate_id) REFERENCES posts(id)
                );
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(posts)").fetchall()
            }

        if "user_id" not in columns:
            db_execute(conn, "ALTER TABLE posts ADD COLUMN user_id INTEGER")


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000,
    ).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hash_password(password, salt).split("$", 1)[1] == digest


def row_to_user(row):
    return {
        "id": row["id"],
        "studentId": row["student_id"],
        "nickname": row["nickname"],
        "department": row["department"],
        "grade": row["grade"],
        "gender": row["gender"],
        "contact": row["contact"],
        "createdAt": serialize_time(row["created_at"]),
    }


def row_to_post(row):
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "nickname": row["nickname"],
        "department": row["department"],
        "grade": row["grade"],
        "gender": row["gender"],
        "type": row["type"],
        "details": json.loads(row["details"]),
        "note": row["note"] or "",
        "status": row["status"],
        "createdAt": serialize_time(row["created_at"]),
    }


def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"\s+", " ", text).strip()


def compact_text(value):
    text = normalize_text(value)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def text_tokens(value):
    text = normalize_text(value)
    return set(re.findall(r"[a-z]+[0-9]*|[0-9]+|[\u4e00-\u9fff]{2,}", text))


def concept_set(value):
    text = normalize_text(value)
    compact = compact_text(text)
    tokens = text_tokens(text)
    concepts = set()

    for concept, aliases in CONCEPT_ALIASES.items():
        for alias in aliases:
            alias_compact = compact_text(alias)
            if not alias_compact:
                continue
            if alias_compact in LATIN_SHORT_ALIASES:
                if alias_compact in tokens or compact == alias_compact:
                    concepts.add(concept)
            elif alias_compact in compact:
                concepts.add(concept)

    return concepts


def field_similarity(left, right):
    left_compact = compact_text(left)
    right_compact = compact_text(right)
    if not left_compact or not right_compact:
        return 0.0
    if left_compact == right_compact:
        return 1.0

    left_concepts = concept_set(left)
    right_concepts = concept_set(right)
    if left_concepts & right_concepts:
        return 1.0

    scores = []
    if left_compact in right_compact or right_compact in left_compact:
        scores.append(0.72)

    left_tokens = text_tokens(left)
    right_tokens = text_tokens(right)
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        scores.append(overlap / union)

    scores.append(difflib.SequenceMatcher(None, left_compact, right_compact).ratio())
    return max(scores)


def similar(left, right):
    return field_similarity(left, right) >= 0.62


def score(post, candidate):
    if candidate["type"] != post["type"] or candidate["id"] == post["id"]:
        return -1

    total = 44
    fields = TYPE_FIELDS.get(post["type"], [])
    for field in fields:
        post_value = post["details"].get(field, "")
        candidate_value = candidate["details"].get(field, "")
        similarity = field_similarity(post_value, candidate_value)
        if similarity >= 0.35:
            total += round(9 * similarity)

    if candidate["department"] == post["department"]:
        total += 6
    if candidate["grade"] == post["grade"]:
        total += 5
    if post["gender"] == "不公开" or candidate["gender"] == post["gender"]:
        total += 2

    return min(total, 99)


def fetch_post(conn, post_id):
    row = db_fetchone(conn, "SELECT * FROM posts WHERE id = ?", (post_id,))
    return row_to_post(row) if row else None


def find_matches(conn, post_id, limit=2):
    post = fetch_post(conn, post_id)
    if not post:
        return None, []

    rejected = {
        row["candidate_id"]
        for row in db_fetchall(
            conn,
            "SELECT candidate_id FROM decisions WHERE post_id = ? AND decision = 'reject'",
            (post_id,),
        )
    }
    accepted = {
        row["candidate_id"]
        for row in db_fetchall(
            conn,
            "SELECT candidate_id FROM decisions WHERE post_id = ? AND decision = 'accept'",
            (post_id,),
        )
    }
    rows = db_fetchall(
        conn,
        """
        SELECT * FROM posts
        WHERE status = 'open'
        AND type = ?
        AND id != ?
        AND (user_id IS NULL OR user_id != ?)
        """,
        (post["type"], post_id, post["userId"]),
    )

    matches = []
    for row in rows:
        candidate = row_to_post(row)
        if candidate["id"] in rejected or candidate["id"] in accepted:
            continue
        candidate["score"] = score(post, candidate)
        matches.append(candidate)

    matches.sort(key=lambda item: item["score"], reverse=True)
    return post, matches[:limit]


def validate_request(request):
    request_type = request.get("type")
    if request_type not in TYPE_FIELDS:
        return "未知的搭子类型"

    for field in TYPE_FIELDS[request_type]:
        if not str(request.get(field, "")).strip():
            return f"需求信息缺少：{field}"

    return None


class AppHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/me":
            self.get_me()
            return
        if parsed.path.startswith("/api/"):
            self.send_json({"error": "接口不存在"}, 404)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/register":
            self.register()
            return
        if parsed.path == "/api/login":
            self.login()
            return
        if parsed.path == "/api/posts":
            self.create_post()
            return
        if parsed.path == "/api/decisions":
            self.create_decision()
            return
        self.send_json({"error": "接口不存在"}, 404)

    def translate_path(self, path):
        parsed = urlparse(path)
        clean = parsed.path.lstrip("/") or "index.html"
        target = (ROOT / clean).resolve()
        if ROOT not in target.parents and target != ROOT:
            return str(ROOT / "index.html")
        return str(target)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def current_user(self, conn):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.removeprefix("Bearer ").strip()
        row = db_fetchone(
            conn,
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        )
        return row_to_user(row) if row else None

    def issue_session(self, conn, user_id):
        token = secrets.token_urlsafe(32)
        db_execute(
            conn,
            "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
            (token, user_id),
        )
        return token

    def get_me(self):
        with get_db() as conn:
            user = self.current_user(conn)
        if not user:
            self.send_json({"error": "请先登录"}, 401)
            return
        self.send_json({"user": user})

    def register(self):
        try:
            payload = self.read_json()
            required = ["studentId", "password", "nickname", "department", "grade", "gender", "contact"]
            for field in required:
                if not str(payload.get(field, "")).strip():
                    self.send_json({"error": f"注册信息缺少：{field}"}, 400)
                    return
            if len(payload["password"]) < 6:
                self.send_json({"error": "密码至少需要 6 位"}, 400)
                return

            with get_db() as conn:
                insert_user_sql = """
                INSERT INTO users
                (student_id, password_hash, nickname, department, grade, gender, contact)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                if USE_POSTGRES:
                    insert_user_sql += " RETURNING id"
                cursor = db_execute(
                    conn,
                    insert_user_sql,
                    (
                        payload["studentId"].strip(),
                        hash_password(payload["password"]),
                        payload["nickname"].strip(),
                        payload["department"].strip(),
                        payload["grade"].strip(),
                        payload["gender"].strip(),
                        payload["contact"].strip(),
                    ),
                )
                user_id = created_id(cursor)
                token = self.issue_session(conn, user_id)
                row = db_fetchone(conn, "SELECT * FROM users WHERE id = ?", (user_id,))

            self.send_json({"token": token, "user": row_to_user(row)}, 201)
        except DB_INTEGRITY_ERROR_TYPES:
            self.send_json({"error": "该学号已经注册，请直接登录"}, 409)
        except (json.JSONDecodeError, *DB_ERROR_TYPES) as exc:
            self.send_json({"error": f"注册失败：{exc}"}, 500)

    def login(self):
        try:
            payload = self.read_json()
            student_id = str(payload.get("studentId", "")).strip()
            password = str(payload.get("password", ""))
            if not student_id or not password:
                self.send_json({"error": "请输入学号和密码"}, 400)
                return

            with get_db() as conn:
                row = db_fetchone(
                    conn,
                    "SELECT * FROM users WHERE student_id = ?",
                    (student_id,),
                )
                if not row or not verify_password(password, row["password_hash"]):
                    self.send_json({"error": "学号或密码不正确"}, 401)
                    return
                token = self.issue_session(conn, row["id"])

            self.send_json({"token": token, "user": row_to_user(row)})
        except (json.JSONDecodeError, *DB_ERROR_TYPES) as exc:
            self.send_json({"error": f"登录失败：{exc}"}, 500)

    def create_post(self):
        try:
            payload = self.read_json()
            request = payload.get("request", {})
            error = validate_request(request)
            if error:
                self.send_json({"error": error}, 400)
                return

            request_type = request["type"]
            details = {
                field: str(request.get(field, "")).strip()
                for field in TYPE_FIELDS[request_type]
            }

            with get_db() as conn:
                user = self.current_user(conn)
                if not user:
                    self.send_json({"error": "请先注册或登录后再发布"}, 401)
                    return
                insert_post_sql = """
                INSERT INTO posts
                (user_id, nickname, department, grade, gender, type, details, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """
                if USE_POSTGRES:
                    insert_post_sql += " RETURNING id"
                cursor = db_execute(
                    conn,
                    insert_post_sql,
                    (
                        user["id"],
                        user["nickname"],
                        user["department"],
                        user["grade"],
                        user["gender"],
                        request_type,
                        json.dumps(details, ensure_ascii=False),
                        str(request.get("note", "")).strip(),
                    ),
                )
                post_id = created_id(cursor)
                post, matches = find_matches(conn, post_id)

            self.send_json({"post": post, "matches": matches}, 201)
        except (json.JSONDecodeError, *DB_ERROR_TYPES) as exc:
            self.send_json({"error": f"发布失败：{exc}"}, 500)

    def create_decision(self):
        try:
            payload = self.read_json()
            post_id = int(payload.get("postId", 0))
            candidate_id = int(payload.get("candidateId", 0))
            decision = payload.get("decision")
            if decision not in ("accept", "reject") or not post_id or not candidate_id:
                self.send_json({"error": "决策参数不完整"}, 400)
                return

            with get_db() as conn:
                user = self.current_user(conn)
                if not user:
                    self.send_json({"error": "请先登录"}, 401)
                    return
                post = fetch_post(conn, post_id)
                candidate = fetch_post(conn, candidate_id)
                if not post or not candidate:
                    self.send_json({"error": "招募信息不存在"}, 404)
                    return
                if post["userId"] != user["id"]:
                    self.send_json({"error": "只能处理自己发布的招募"}, 403)
                    return

                db_execute(
                    conn,
                    """
                    INSERT INTO decisions (post_id, candidate_id, decision)
                    VALUES (?, ?, ?)
                    ON CONFLICT(post_id, candidate_id) DO UPDATE SET
                    decision = excluded.decision,
                    created_at = CURRENT_TIMESTAMP
                    """,
                    (post_id, candidate_id, decision),
                )

                match_status = None
                if decision == "accept":
                    reverse = db_fetchone(
                        conn,
                        """
                        SELECT 1 FROM decisions
                        WHERE post_id = ? AND candidate_id = ? AND decision = 'accept'
                        """,
                        (candidate_id, post_id),
                    )
                    match_status = "confirmed" if reverse else "pending"
                    db_execute(
                        conn,
                        """
                        INSERT INTO matches (post_id, candidate_id, status)
                        VALUES (?, ?, ?)
                        ON CONFLICT(post_id, candidate_id) DO UPDATE SET
                        status = excluded.status
                        """,
                        (post_id, candidate_id, match_status),
                    )

                post, matches = find_matches(conn, post_id)

            self.send_json({
                "post": post,
                "matches": matches,
                "matchStatus": match_status,
            })
        except (ValueError, json.JSONDecodeError, *DB_ERROR_TYPES) as exc:
            self.send_json({"error": f"操作失败：{exc}"}, 500)


def main():
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("application/javascript", ".js")
    init_db()
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"XDU 搭子已启动：http://{host}:{port}")
    print("数据库：PostgreSQL 云数据库" if USE_POSTGRES else f"SQLite 本地数据库：{DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()

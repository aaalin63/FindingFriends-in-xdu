import json
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402

app = Flask(__name__)
server.init_db()


def current_user(conn):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    row = server.db_fetchone(
        conn,
        """
        SELECT users.* FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (token,),
    )
    return server.row_to_user(row) if row else None


def issue_session(conn, user_id):
    token = server.secrets.token_urlsafe(32)
    server.db_execute(
        conn,
        "INSERT INTO sessions (token, user_id) VALUES (?, ?)",
        (token, user_id),
    )
    return token


def json_payload():
    return request.get_json(silent=True) or {}


@app.get("/")
def home():
    return send_from_directory(ROOT, "index.html")


@app.get("/<path:path>")
def static_files(path):
    if path in {"index.html", "styles.css", "app.js"}:
        return send_from_directory(ROOT, path)
    return jsonify({"error": "资源不存在"}), 404


@app.get("/api/me")
def me():
    with server.get_db() as conn:
        user = current_user(conn)
    if not user:
        return jsonify({"error": "请先登录"}), 401
    return jsonify({"user": user})


@app.post("/api/register")
def register():
    try:
        payload = json_payload()
        required = ["studentId", "password", "nickname", "department", "grade", "gender", "contact"]
        for field in required:
            if not str(payload.get(field, "")).strip():
                return jsonify({"error": f"注册信息缺少：{field}"}), 400
        if len(payload["password"]) < 6:
            return jsonify({"error": "密码至少需要 6 位"}), 400

        with server.get_db() as conn:
            insert_user_sql = """
            INSERT INTO users
            (student_id, password_hash, nickname, department, grade, gender, contact)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            if server.USE_POSTGRES:
                insert_user_sql += " RETURNING id"
            cursor = server.db_execute(
                conn,
                insert_user_sql,
                (
                    payload["studentId"].strip(),
                    server.hash_password(payload["password"]),
                    payload["nickname"].strip(),
                    payload["department"].strip(),
                    payload["grade"].strip(),
                    payload["gender"].strip(),
                    payload["contact"].strip(),
                ),
            )
            user_id = server.created_id(cursor)
            token = issue_session(conn, user_id)
            row = server.db_fetchone(conn, "SELECT * FROM users WHERE id = ?", (user_id,))

        return jsonify({"token": token, "user": server.row_to_user(row)}), 201
    except server.DB_INTEGRITY_ERROR_TYPES:
        return jsonify({"error": "该学号已经注册，请直接登录"}), 409
    except (json.JSONDecodeError, *server.DB_ERROR_TYPES) as exc:
        return jsonify({"error": f"注册失败：{exc}"}), 500


@app.post("/api/login")
def login():
    try:
        payload = json_payload()
        student_id = str(payload.get("studentId", "")).strip()
        password = str(payload.get("password", ""))
        if not student_id or not password:
            return jsonify({"error": "请输入学号和密码"}), 400

        with server.get_db() as conn:
            row = server.db_fetchone(
                conn,
                "SELECT * FROM users WHERE student_id = ?",
                (student_id,),
            )
            if not row or not server.verify_password(password, row["password_hash"]):
                return jsonify({"error": "学号或密码不正确"}), 401
            token = issue_session(conn, row["id"])

        return jsonify({"token": token, "user": server.row_to_user(row)})
    except (json.JSONDecodeError, *server.DB_ERROR_TYPES) as exc:
        return jsonify({"error": f"登录失败：{exc}"}), 500


@app.post("/api/posts")
def create_post():
    try:
        payload = json_payload()
        recruit_request = payload.get("request", {})
        error = server.validate_request(recruit_request)
        if error:
            return jsonify({"error": error}), 400

        request_type = recruit_request["type"]
        details = {
            field: str(recruit_request.get(field, "")).strip()
            for field in server.TYPE_FIELDS[request_type]
        }

        with server.get_db() as conn:
            user = current_user(conn)
            if not user:
                return jsonify({"error": "请先注册或登录后再发布"}), 401

            insert_post_sql = """
            INSERT INTO posts
            (user_id, nickname, department, grade, gender, type, details, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            if server.USE_POSTGRES:
                insert_post_sql += " RETURNING id"
            cursor = server.db_execute(
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
                    str(recruit_request.get("note", "")).strip(),
                ),
            )
            post_id = server.created_id(cursor)
            post, matches = server.find_matches(conn, post_id)

        return jsonify({"post": post, "matches": matches}), 201
    except (json.JSONDecodeError, *server.DB_ERROR_TYPES) as exc:
        return jsonify({"error": f"发布失败：{exc}"}), 500


@app.post("/api/decisions")
def create_decision():
    try:
        payload = json_payload()
        post_id = int(payload.get("postId", 0))
        candidate_id = int(payload.get("candidateId", 0))
        decision = payload.get("decision")
        if decision not in ("accept", "reject") or not post_id or not candidate_id:
            return jsonify({"error": "决策参数不完整"}), 400

        with server.get_db() as conn:
            user = current_user(conn)
            if not user:
                return jsonify({"error": "请先登录"}), 401
            post = server.fetch_post(conn, post_id)
            candidate = server.fetch_post(conn, candidate_id)
            if not post or not candidate:
                return jsonify({"error": "招募信息不存在"}), 404
            if post["userId"] != user["id"]:
                return jsonify({"error": "只能处理自己发布的招募"}), 403

            server.db_execute(
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
                reverse = server.db_fetchone(
                    conn,
                    """
                    SELECT 1 FROM decisions
                    WHERE post_id = ? AND candidate_id = ? AND decision = 'accept'
                    """,
                    (candidate_id, post_id),
                )
                match_status = "confirmed" if reverse else "pending"
                server.db_execute(
                    conn,
                    """
                    INSERT INTO matches (post_id, candidate_id, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT(post_id, candidate_id) DO UPDATE SET
                    status = excluded.status
                    """,
                    (post_id, candidate_id, match_status),
                )

            post, matches = server.find_matches(conn, post_id)

        return jsonify({
            "post": post,
            "matches": matches,
            "matchStatus": match_status,
        })
    except (ValueError, json.JSONDecodeError, *server.DB_ERROR_TYPES) as exc:
        return jsonify({"error": f"操作失败：{exc}"}), 500

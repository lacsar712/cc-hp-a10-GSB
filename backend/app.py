import json
import os
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from rules import fmt_hhmm, in_curfew, judge, parse_hhmm

SECRET = os.environ.get("JWT_SECRET", "herb-process-dev-secret")
DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54393/herb")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)
USERS = {
    "processor": {"role": "writer", "password_hash": pwd.hash("herb123456")},
    "checker": {"role": "reader", "password_hash": pwd.hash("check123456")},
}


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


class LoginIn(BaseModel):
    username: str
    password: str


class StepIn(BaseModel):
    name: str
    temp_c: float
    minutes: float


class BatchIn(BaseModel):
    herb: str = Field(min_length=1, max_length=80)
    steps: list[StepIn]


class CurfewIn(BaseModel):
    start: str
    end: str


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = jwt.decode(credentials.credentials, SECRET, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="无效令牌") from exc
    if payload.get("sub") not in USERS:
        raise HTTPException(status_code=401, detail="无效令牌")
    return {"username": payload["sub"], "role": payload.get("role")}


def require_writer(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "writer":
        raise HTTPException(status_code=403, detail="仅炮制员可写入记录")
    return user


def load_curfew(conn) -> dict:
    return conn.execute(
        "SELECT id, start_min, end_min, updated_by, updated_at FROM curfew_config WHERE id = 1"
    ).fetchone()


def curfew_state(row: dict) -> dict:
    now = datetime.now()  # 服务器本地时钟，禁写判定以此为准
    now_min = now.hour * 60 + now.minute
    return {
        "start": fmt_hhmm(row["start_min"]),
        "end": fmt_hhmm(row["end_min"]),
        "in_curfew": in_curfew(row["start_min"], row["end_min"], now_min),
        "server_time": now.strftime("%H:%M:%S"),
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"],
    }


app = FastAPI(title="饮片炮制记录台")


@app.on_event("startup")
def startup():
    with connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS batches (
                id serial PRIMARY KEY,
                herb text NOT NULL,
                doc jsonb NOT NULL,
                verdict text NOT NULL,
                reason text NOT NULL,
                created_by text NOT NULL,
                created_at timestamptz NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS curfew_config (
                id integer PRIMARY KEY,
                start_min integer NOT NULL,
                end_min integer NOT NULL,
                updated_by text NOT NULL,
                updated_at timestamptz NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS curfew_hits (
                id serial PRIMARY KEY,
                herb text NOT NULL,
                attempted_by text NOT NULL,
                attempted_at timestamptz NOT NULL,
                window_start text NOT NULL,
                window_end text NOT NULL
            )"""
        )
        if conn.execute("SELECT COUNT(*) AS n FROM curfew_config").fetchone()["n"] == 0:
            conn.execute(
                """INSERT INTO curfew_config (id, start_min, end_min, updated_by, updated_at)
                   VALUES (1, %s, %s, %s, %s)""",
                (22 * 60, 6 * 60, "system", datetime.now(timezone.utc)),
            )
        count = conn.execute("SELECT COUNT(*) AS n FROM batches").fetchone()["n"]
        if count == 0:
            now = datetime.now(timezone.utc)
            samples = [
                ("甘草", {"steps": [{"name": "清炒", "temp_c": 120, "minutes": 12}]}),
                ("黄芩", {"steps": [{"name": "清炒", "temp_c": 40, "minutes": 12}]}),
            ]
            for herb, doc in samples:
                verdict, reason = judge(doc)
                conn.execute(
                    """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
                       VALUES (%s, %s::jsonb, %s, %s, %s, %s)""",
                    (herb, json.dumps(doc, ensure_ascii=False), verdict, reason, "processor", now),
                )
        conn.commit()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "herb-process-record"}


@app.post("/api/auth/login")
def login(body: LoginIn):
    user = USERS.get(body.username.strip())
    if not user or not pwd.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({"sub": body.username.strip(), "role": user["role"], "exp": exp}, SECRET, algorithm="HS256")
    return {"access_token": token, "username": body.username.strip(), "role": user["role"]}


@app.get("/api/batches")
def list_batches(_user: dict = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT id, herb, doc, verdict, reason, created_by FROM batches ORDER BY id DESC").fetchall()
    return rows


@app.get("/api/curfew")
def get_curfew(_user: dict = Depends(current_user)):
    with connect() as conn:
        return curfew_state(load_curfew(conn))


@app.put("/api/curfew")
def put_curfew(body: CurfewIn, user: dict = Depends(require_writer)):
    try:
        start_min = parse_hhmm(body.start)
        end_min = parse_hhmm(body.end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with connect() as conn:
        conn.execute(
            """UPDATE curfew_config
               SET start_min = %s, end_min = %s, updated_by = %s, updated_at = %s
               WHERE id = 1""",
            (start_min, end_min, user["username"], datetime.now(timezone.utc)),
        )
        conn.commit()
        return curfew_state(load_curfew(conn))


@app.get("/api/curfew/hits")
def list_curfew_hits(_user: dict = Depends(current_user)):
    with connect() as conn:
        return conn.execute(
            """SELECT id, herb, attempted_by, attempted_at, window_start, window_end
               FROM curfew_hits ORDER BY id DESC"""
        ).fetchall()


@app.post("/api/batches", status_code=201)
def create_batch(body: BatchIn, user: dict = Depends(require_writer)):
    doc = {"steps": [s.model_dump() for s in body.steps]}
    verdict, reason = judge(doc)
    herb = body.herb.strip()
    with connect() as conn:
        curfew = load_curfew(conn)
        now = datetime.now()  # 服务器本地时钟
        if in_curfew(curfew["start_min"], curfew["end_min"], now.hour * 60 + now.minute):
            conn.execute(
                """INSERT INTO curfew_hits (herb, attempted_by, attempted_at, window_start, window_end)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    herb,
                    user["username"],
                    datetime.now(timezone.utc),
                    fmt_hhmm(curfew["start_min"]),
                    fmt_hhmm(curfew["end_min"]),
                ),
            )
            conn.commit()
            raise HTTPException(
                status_code=403,
                detail=f"当前处于夜间禁写窗（{fmt_hhmm(curfew['start_min'])}–{fmt_hhmm(curfew['end_min'])}），禁止开炒写入",
            )
        row = conn.execute(
            """INSERT INTO batches (herb, doc, verdict, reason, created_by, created_at)
               VALUES (%s, %s::jsonb, %s, %s, %s, %s)
               RETURNING id, herb, doc, verdict, reason, created_by""",
            (herb, json.dumps(doc, ensure_ascii=False), verdict, reason, user["username"], datetime.now(timezone.utc)),
        ).fetchone()
        conn.commit()
    return row

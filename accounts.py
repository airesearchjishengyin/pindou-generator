"""图豆账户系统: OAuth 登录 (Google/微软) + 余额 + 充值优惠 + 消费账本。
设计原则: 最简。SQLite 单文件; 余额以"厘"(0.001元)整数存储, 永不用浮点算钱;
登录态 = 签名 Cookie (HMAC, secret 在 .env), 不引入额外会话存储。

充值优惠规则 (对用户透明):
  每 20 元送 3 元, 不足 20 的部分每 10 元送 1 元
  10→送1 (共11), 20→送3 (共23), 30→送4 (共34), 50→送9 (共59)
新用户注册即送 ¥0.9 (一次生成的尝鲜额度)。
"""
import os
import json
import hmac
import hashlib
import sqlite3
import secrets
import time
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "accounts.db")
MILLI = 1000                 # 1 元 = 1000 厘
PRICE_PER_GEN_MILLI = 900    # AI 像素化 ¥0.9/次
SIGNUP_BONUS_MILLI = 900     # 注册赠送 ¥0.9


def _bonus_milli(amount_yuan: int) -> int:
    """充值赠送: 每20元送3元 + 余数每10元送1元 (全部向上取整到元输入)"""
    if amount_yuan <= 0:
        return 0
    return (amount_yuan // 20) * 3000 + ((amount_yuan % 20) // 10) * 1000


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          email TEXT PRIMARY KEY,
          provider TEXT NOT NULL,          -- google / microsoft / manual
          name TEXT DEFAULT '',
          balance_milli INTEGER NOT NULL DEFAULT 0,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ledger(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT NOT NULL,
          delta_milli INTEGER NOT NULL,    -- 正=充值/赠送, 负=消费
          reason TEXT NOT NULL,            -- recharge / bonus / signup / gen / trial / admin
          ref TEXT DEFAULT '',             -- 关联单号/备注
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_email ON ledger(email, id DESC);
        """)


def _now() -> int:
    return int(time.time())


def upsert_user(email: str, provider: str, name: str = "") -> dict:
    """登录时调用。新用户注册送 ¥0.9。返回 {email, balance_milli, is_new}"""
    email = email.strip().lower()
    with db() as c:
        row = c.execute("SELECT email, balance_milli FROM users WHERE email=?",
                        (email,)).fetchone()
        if row:
            if name:
                c.execute("UPDATE users SET name=? WHERE email=?", (name, email))
            return {"email": email, "balance_milli": row["balance_milli"], "is_new": False}
        c.execute("INSERT INTO users(email, provider, name, balance_milli, created_at) "
                  "VALUES(?,?,?,0,?)", (email, provider, name, _now()))
        c.execute("INSERT INTO ledger(email, delta_milli, reason, ref, created_at) "
                  "VALUES(?,?,?,?,?)", (email, SIGNUP_BONUS_MILLI, "signup", "", _now()))
        c.execute("UPDATE users SET balance_milli=balance_milli+? WHERE email=?",
                  (SIGNUP_BONUS_MILLI, email))
        return {"email": email, "balance_milli": SIGNUP_BONUS_MILLI, "is_new": True}


def get_balance(email: str) -> int:
    with db() as c:
        row = c.execute("SELECT balance_milli FROM users WHERE email=?",
                        (email.strip().lower(),)).fetchone()
        return row["balance_milli"] if row else 0


def recharge(email: str, amount_yuan: int, ref: str = "") -> dict:
    """充值 (管理员确认收款后调用)。自动按规则加赠。返回本次入账与余额。"""
    email = email.strip().lower()
    if amount_yuan < 1 or amount_yuan > 5000:
        raise ValueError("单笔充值需在 1–5000 元")
    bonus = _bonus_milli(amount_yuan)
    total = amount_yuan * MILLI + bonus
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users(email, provider, name, balance_milli, created_at) "
                  "VALUES(?, 'manual', '', 0, ?)", (email, _now()))
        c.execute("INSERT INTO ledger(email, delta_milli, reason, ref, created_at) "
                  "VALUES(?,?,?,?,?)", (email, amount_yuan * MILLI, "recharge", ref, _now()))
        if bonus:
            c.execute("INSERT INTO ledger(email, delta_milli, reason, ref, created_at) "
                      "VALUES(?,?,?,?,?)", (email, bonus, "bonus", f"充{amount_yuan}送{bonus//MILLI}", _now()))
        c.execute("UPDATE users SET balance_milli=balance_milli+? WHERE email=?", (total, email))
        bal = c.execute("SELECT balance_milli FROM users WHERE email=?", (email,)).fetchone()
    return {"email": email, "credited_yuan": amount_yuan, "bonus_yuan": bonus // MILLI,
            "balance_milli": bal["balance_milli"]}


def consume(email: str, reason: str = "gen", ref: str = "") -> dict:
    """扣一次生成费。余额不足抛 ValueError。"""
    email = email.strip().lower()
    with db() as c:
        row = c.execute("SELECT balance_milli FROM users WHERE email=?", (email,)).fetchone()
        if not row or row["balance_milli"] < PRICE_PER_GEN_MILLI:
            raise ValueError("余额不足, 请充值 (¥0.9/次)")
        c.execute("INSERT INTO ledger(email, delta_milli, reason, ref, created_at) "
                  "VALUES(?,?,?,?,?)", (email, -PRICE_PER_GEN_MILLI, reason, ref, _now()))
        c.execute("UPDATE users SET balance_milli=balance_milli-? WHERE email=?",
                  (PRICE_PER_GEN_MILLI, email))
        bal = c.execute("SELECT balance_milli FROM users WHERE email=?", (email,)).fetchone()
    return {"balance_milli": bal["balance_milli"], "charged_yuan": PRICE_PER_GEN_MILLI / MILLI}


def ledger_of(email: str, limit: int = 50) -> list:
    with db() as c:
        rows = c.execute("SELECT delta_milli, reason, ref, created_at FROM ledger "
                         "WHERE email=? ORDER BY id DESC LIMIT ?",
                         (email.strip().lower(), limit)).fetchall()
        return [{"delta_milli": r["delta_milli"], "reason": r["reason"],
                 "ref": r["ref"], "at": r["created_at"]} for r in rows]


# ---------------- 签名 Cookie (登录态) ----------------
def _secret() -> str:
    s = os.environ.get("PINDOU_SESSION_SECRET", "")
    if not s:
        s = secrets.token_hex(32)
        os.environ["PINDOU_SESSION_SECRET"] = s   # 进程内兜底; 正式部署配到 .env
    return s


def sign_session(email: str) -> str:
    msg = f"{email}|{_now() + 30*86400}".encode()   # 30 天有效
    sig = hmac.new(_secret().encode(), msg, hashlib.sha256).hexdigest()[:32]
    return f"{msg.decode()}|{sig}"


def verify_session(token: str):
    """有效返回 email, 否则 None"""
    if not token:
        return None
    parts = token.split("|")
    if len(parts) != 3:
        return None
    email, exp, sig = parts
    msg = f"{email}|{exp}".encode()
    want = hmac.new(_secret().encode(), msg, hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, want) or int(exp) < _now():
        return None
    return email

# ============================================================
# 🏓 桌球教室管理與互動系統 - app.py  v1.3
# Ping-Pong Academy Manager
#
# 相較於原版異動：
#   [移除] reportlab / PDF 收據 (generate_receipt_pdf, pdf_path 欄位, 下載按鈕)
#   [移除] RECEIPT_DIR 目錄建立
#   [新增] validate_password()  ─ 密碼強度驗證（≥6碼且含英文字母）
#   [新增] time_to_minutes() / check_table_conflict() ─ 時段重疊衝突比對
#   [新增] get_display_name()  ─ 依角色取顯示姓名
#   [新增] generate_date_options() ─ 今天起往後 7 天下拉選單
#   [修改] Users schema：新增 email, display_name 欄位
#   [修改] ClassSessions schema：新增 created_by 欄位
#   [修改] LeaveRequests schema：新增 session_id, reviewed_by, reviewed_at, reject_reason
#   [修改] Payments schema：新增 paid_time, created_at；移除 pdf_path
#   [修改] page_leave_request()：新增待補課紀錄區塊
#   [修改] page_payment_status()：移除 PDF 下載區塊
#   [修改] page_coach_attendance()：請假聯動（核准請假自動勾選）
#   [修改] page_admin_courses()：桌次衝突改時段重疊比對 + 視覺化改甘特圖 + 移除防呆二次確認
#   [修改] page_admin_payments()：移除 PDF 產生；新增繳費時間欄位
#   [修改] page_admin_accounts()：密碼強度驗證 + 新增 Email 欄位 + 新增報表收件者管理 tab
#   [新增] page_coach_leave_review()  ─ 教練請假審核（F-003-4）
#   [新增] page_weekly_schedule()    ─ 近 7 天課程與桌次查詢（F-008，全角色）
#   [修改] MENUS / main()：加入上述新頁面路由
# ============================================================

import streamlit as st
import sqlite3
import hashlib
import os
import pandas as pd
from datetime import datetime, date, timedelta
import plotly.graph_objects as go
import plotly.express as px

# ── 全域設定 ────────────────────────────────────────────────
DB_PATH = "./pingpong.db"

# ── Streamlit 頁面設定 ──────────────────────────────────────
st.set_page_config(
    page_title="🏓 桌球教室管理系統",
    page_icon="🏓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全域 CSS ────────────────────────────────────────────────
st.markdown("""
<style>
:root { --accent: #FF6B35; --accent-light: #FFF0EB; }
.block-container { padding-top: 1.5rem; }
div[data-testid="metric-container"] {
    background: var(--accent-light);
    border-left: 4px solid var(--accent);
    border-radius: 8px;
    padding: 12px 16px;
}
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
}
.page-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 0.2rem;
}
.section-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #FF6B35;
    margin: 1rem 0 0.5rem 0;
}
.role-badge-admin   { background:#FF6B35; color:white; padding:2px 10px;
                      border-radius:12px; font-size:0.8rem; font-weight:600; }
.role-badge-coach   { background:#2196F3; color:white; padding:2px 10px;
                      border-radius:12px; font-size:0.8rem; font-weight:600; }
.role-badge-student { background:#4CAF50; color:white; padding:2px 10px;
                      border-radius:12px; font-size:0.8rem; font-weight:600; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 🗄️  資料庫工具函式
# ══════════════════════════════════════════════════════════════

def get_conn():
    """取得資料庫連線（row_factory=sqlite3.Row 方便欄位名存取）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ── [新增] 密碼強度驗證 ─────────────────────────────────────
def validate_password(pw: str):
    """最少 6 碼且需包含英文字母，回傳 (是否通過, 錯誤訊息)"""
    if len(pw) < 6 or not any(c.isalpha() for c in pw):
        return False, "密碼需至少 6 碼且包含英文字母"
    return True, ""


# ── [新增] 時段工具 ─────────────────────────────────────────
def time_to_minutes(t: str) -> int:
    """將 'HH:MM' 轉換為分鐘數"""
    h, m = map(int, t.split(":"))
    return h * 60 + m


def check_table_conflict(conn, schedule_day: str, schedule_time: str,
                         duration: int, table_id: int,
                         exclude_id: int = None) -> list:
    """
    時段重疊衝突比對：
      new_start < ex_end  AND  new_end > ex_start
    回傳衝突課程 ID 列表。
    """
    new_start = time_to_minutes(schedule_time)
    new_end   = new_start + duration
    rows = conn.execute(
        "SELECT id, schedule_time, duration FROM Courses "
        "WHERE schedule_day=? AND table_id=?",
        (schedule_day, table_id)
    ).fetchall()
    conflicts = []
    for row in rows:
        if exclude_id and row["id"] == exclude_id:
            continue
        ex_start = time_to_minutes(row["schedule_time"])
        ex_end   = ex_start + row["duration"]
        if new_start < ex_end and new_end > ex_start:
            conflicts.append(row["id"])
    return conflicts


# ── [新增] 顯示姓名 ─────────────────────────────────────────
def get_display_name(conn, user_id: int, role: str) -> str:
    """依角色從對應資料表取得顯示姓名"""
    if role == "student":
        row = conn.execute(
            "SELECT name FROM Students WHERE user_id=?", (user_id,)).fetchone()
    elif role == "coach":
        row = conn.execute(
            "SELECT name FROM Coaches WHERE user_id=?", (user_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT display_name FROM Users WHERE id=?", (user_id,)).fetchone()
    return row[0] if row and row[0] else "未設定"


# ── [新增] 近 7 天日期選單 ───────────────────────────────────
def generate_date_options():
    """回傳 [(顯示文字, date物件), ...] 今天起往後 7 天"""
    labels = ["一", "二", "三", "四", "五", "六", "日"]
    return [
        (f"{(date.today()+timedelta(days=i)).strftime('%Y-%m-%d')}"
         f"（{labels[(date.today()+timedelta(days=i)).weekday()]}）",
         date.today() + timedelta(days=i))
        for i in range(7)
    ]


# 星期文字 → Python weekday()
WEEKDAY_TO_INT = {
    "週一": 0, "週二": 1, "週三": 2, "週四": 3,
    "週五": 4, "週六": 5, "週日": 6,
}


# ══════════════════════════════════════════════════════════════
# 🏗️  資料庫初始化
# ══════════════════════════════════════════════════════════════

def init_db():
    """初始化資料庫：建表（v1.3 schema）+ 插入預設資料"""
    with get_conn() as conn:
        cur = conn.cursor()

        # ── 建立資料表 ──────────────────────────────────────
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS Users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT UNIQUE NOT NULL,
            password     TEXT NOT NULL,
            role         TEXT NOT NULL,
            email        TEXT DEFAULT '',
            display_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS Students (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            name    TEXT NOT NULL,
            phone   TEXT DEFAULT '',
            email   TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES Users(id)
        );
        CREATE TABLE IF NOT EXISTS Coaches (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER UNIQUE,
            name       TEXT NOT NULL,
            phone      TEXT DEFAULT '',
            bio        TEXT DEFAULT '',
            specialty  TEXT DEFAULT '',
            photo_path TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES Users(id)
        );
        CREATE TABLE IF NOT EXISTS Tables (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS Courses (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            course_type   TEXT NOT NULL,
            coach_id      INTEGER NOT NULL,
            schedule_day  TEXT NOT NULL,
            schedule_time TEXT NOT NULL,
            duration      INTEGER NOT NULL,
            table_id      INTEGER NOT NULL,
            fee           REAL DEFAULT 0,
            FOREIGN KEY (coach_id)  REFERENCES Coaches(id),
            FOREIGN KEY (table_id)  REFERENCES Tables(id)
        );
        CREATE TABLE IF NOT EXISTS Enrollments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL,
            course_id     INTEGER NOT NULL,
            enrolled_date TEXT NOT NULL,
            UNIQUE(student_id, course_id),
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        CREATE TABLE IF NOT EXISTS ClassSessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id    INTEGER NOT NULL,
            session_date TEXT NOT NULL,
            session_time TEXT NOT NULL,
            coach_id     INTEGER NOT NULL,
            table_id     INTEGER NOT NULL,
            created_by   TEXT NOT NULL DEFAULT 'system',
            FOREIGN KEY (course_id) REFERENCES Courses(id),
            FOREIGN KEY (coach_id)  REFERENCES Coaches(id),
            FOREIGN KEY (table_id)  REFERENCES Tables(id)
        );
        CREATE TABLE IF NOT EXISTS Attendance (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            status     TEXT NOT NULL,
            note       TEXT DEFAULT '',
            UNIQUE(session_id, student_id),
            FOREIGN KEY (session_id) REFERENCES ClassSessions(id),
            FOREIGN KEY (student_id) REFERENCES Students(id)
        );
        CREATE TABLE IF NOT EXISTS LeaveRequests (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL,
            course_id     INTEGER NOT NULL,
            session_id    INTEGER,
            leave_date    TEXT NOT NULL,
            reason        TEXT DEFAULT '',
            status        TEXT DEFAULT 'pending',
            reviewed_by   INTEGER,
            reviewed_at   TEXT,
            reject_reason TEXT DEFAULT '',
            created_at    TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id),
            FOREIGN KEY (session_id) REFERENCES ClassSessions(id)
        );
        CREATE TABLE IF NOT EXISTS Payments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id  INTEGER NOT NULL,
            amount     REAL NOT NULL,
            paid_date  TEXT,
            paid_time  TEXT,
            is_paid    INTEGER DEFAULT 0,
            period     TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        CREATE TABLE IF NOT EXISTS ReportRecipients (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT UNIQUE NOT NULL,
            display_name TEXT DEFAULT '',
            is_active    INTEGER DEFAULT 1
        );
        """)

        # ── 舊資料庫升級：補齊 v1.3 新增欄位（ALTER TABLE ADD COLUMN 若欄位已存在會丟例外，忽略即可）──
        upgrade_sqls = [
            "ALTER TABLE Users          ADD COLUMN email        TEXT DEFAULT ''",
            "ALTER TABLE Users          ADD COLUMN display_name TEXT DEFAULT ''",
            "ALTER TABLE ClassSessions  ADD COLUMN created_by   TEXT NOT NULL DEFAULT 'system'",
            "ALTER TABLE LeaveRequests  ADD COLUMN session_id   INTEGER",
            "ALTER TABLE LeaveRequests  ADD COLUMN reviewed_by  INTEGER",
            "ALTER TABLE LeaveRequests  ADD COLUMN reviewed_at  TEXT",
            "ALTER TABLE LeaveRequests  ADD COLUMN reject_reason TEXT DEFAULT ''",
            "ALTER TABLE Payments       ADD COLUMN paid_time    TEXT",
            "ALTER TABLE Payments       ADD COLUMN created_at   TEXT NOT NULL DEFAULT ''",
        ]
        for sql in upgrade_sqls:
            try:
                cur.execute(sql)
            except Exception:
                pass  # 欄位已存在時忽略

        # ── 桌次 1~8 ────────────────────────────────────────
        for i in range(1, 9):
            cur.execute("INSERT OR IGNORE INTO Tables(id,name) VALUES(?,?)", (i, f"桌{i}"))

        # ── 預設帳號（各角色僅 1 筆，其餘請由管理者手動新增）──
        for username, pw, role, dname in [
            ("admin",   hash_pw("admin123"), "admin",   "系統管理員"),
            ("coach01", hash_pw("coach123"), "coach",   ""),
            ("stu01",   hash_pw("stu123"),   "student", ""),
        ]:
            cur.execute(
                "INSERT OR IGNORE INTO Users(username,password,role,display_name) VALUES(?,?,?,?)",
                (username, pw, role, dname))

        # ── 教練資料（1 筆）────────────────────────────────
        coach_user = cur.execute(
            "SELECT id FROM Users WHERE role='coach' ORDER BY id LIMIT 1").fetchone()
        if coach_user:
            cur.execute(
                "INSERT OR IGNORE INTO Coaches(user_id,name,phone,bio,specialty) VALUES(?,?,?,?,?)",
                (coach_user["id"], "示範教練", "", "請至個人簡介頁面更新資料。", ""))

        # ── 學員資料（1 筆）────────────────────────────────
        stu_user = cur.execute(
            "SELECT id FROM Users WHERE role='student' ORDER BY id LIMIT 1").fetchone()
        if stu_user:
            cur.execute(
                "INSERT OR IGNORE INTO Students(user_id,name,phone,email) VALUES(?,?,?,?)",
                (stu_user["id"], "示範學員", "", ""))

        # ── 預設課程（1 筆）────────────────────────────────
        coach = cur.execute("SELECT id FROM Coaches ORDER BY id LIMIT 1").fetchone()
        if coach:
            cur.execute(
                "INSERT OR IGNORE INTO Courses"
                "(course_type,coach_id,schedule_day,schedule_time,duration,table_id,fee)"
                " VALUES(?,?,?,?,?,?,?)",
                ("團體班", coach["id"], "週一", "10:00", 90, 1, 2000))

        # ── 預設報名與繳費（各 1 筆）──────────────────────
        student = cur.execute("SELECT id FROM Students ORDER BY id LIMIT 1").fetchone()
        course  = cur.execute("SELECT id FROM Courses  ORDER BY id LIMIT 1").fetchone()
        today_str = date.today().isoformat()
        now_str   = datetime.now().isoformat()
        period    = date.today().strftime("%Y-%m")
        if student and course:
            cur.execute(
                "INSERT OR IGNORE INTO Enrollments(student_id,course_id,fee,enrolled_date)"
                " VALUES(?,?,?,?)",
                (student["id"], course["id"], 2000, today_str))
            exists = cur.execute(
                "SELECT id FROM Payments WHERE student_id=? AND course_id=? AND period=?",
                (student["id"], course["id"], period)).fetchone()
            if not exists:
                cur.execute(
                    "INSERT INTO Payments(student_id,course_id,amount,period,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (student["id"], course["id"], 2000, period, now_str))

        conn.commit()


# ══════════════════════════════════════════════════════════════
# 🔐  認證
# ══════════════════════════════════════════════════════════════

def login_page():
    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            '<div class="page-title" style="text-align:center;">'
            '🏓 桌球教室管理與互動系統</div>',
            unsafe_allow_html=True)
        st.markdown(
            '<p style="text-align:center;color:#888;">Ping-Pong Academy Manager</p>',
            unsafe_allow_html=True)
        st.divider()

        st.markdown("#### 請登入您的帳號")
        username = st.text_input("帳號", placeholder="請輸入帳號")
        password = st.text_input("密碼", type="password", placeholder="請輸入密碼")

        if st.button("🔑 登入系統", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("帳號與密碼不可為空")
                return
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM Users WHERE username=? AND password=?",
                    (username, hash_pw(password))).fetchone()
            if row:
                st.session_state["user_id"]  = row["id"]
                st.session_state["username"] = row["username"]
                st.session_state["role"]     = row["role"]
                with get_conn() as conn:
                    if row["role"] == "student":
                        s = conn.execute(
                            "SELECT id,name FROM Students WHERE user_id=?",
                            (row["id"],)).fetchone()
                        if s:
                            st.session_state["profile_id"]   = s["id"]
                            st.session_state["profile_name"] = s["name"]
                    elif row["role"] == "coach":
                        c = conn.execute(
                            "SELECT id,name FROM Coaches WHERE user_id=?",
                            (row["id"],)).fetchone()
                        if c:
                            st.session_state["profile_id"]   = c["id"]
                            st.session_state["profile_name"] = c["name"]
                    else:
                        st.session_state["profile_id"]   = 0
                        st.session_state["profile_name"] = get_display_name(
                            conn, row["id"], "admin")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新輸入")

        st.markdown("---")
        st.caption(
            "預設帳號：admin / admin123　｜　coach01 / coach123　｜　stu01 / stu123")


def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# ══════════════════════════════════════════════════════════════
# 🎛️  側邊欄
# ══════════════════════════════════════════════════════════════

MENUS = {
    "student": ["📚 我的課程", "🙏 請假申請", "💳 繳費狀況",
                "📋 出勤紀錄", "📅 近期課程查詢"],
    "coach":   ["👤 個人簡介編輯", "👥 課程學員名單",
                "✅ 課堂點名", "🙏 請假審核", "📅 近期課程查詢"],
    "admin":   ["📅 課程管理", "📊 出勤總表", "💰 繳費管理",
                "📈 報表查詢", "🔑 帳號管理", "📅 近期課程查詢"],
}

ROLE_LABEL = {"student": "學員", "coach": "教練", "admin": "管理者"}
ROLE_BADGE = {
    "student": "role-badge-student",
    "coach":   "role-badge-coach",
    "admin":   "role-badge-admin",
}


def sidebar():
    role = st.session_state.get("role", "")
    name = st.session_state.get("profile_name", "")

    with st.sidebar:
        st.markdown("## 🏓 Ping-Pong Academy")
        st.divider()
        st.markdown(
            f"**{name}**　"
            f'<span class="{ROLE_BADGE.get(role,"")}">'
            f'{ROLE_LABEL.get(role,"")}</span>',
            unsafe_allow_html=True)
        st.markdown(
            f"<small style='color:#888;'>帳號："
            f"{st.session_state.get('username','')}</small>",
            unsafe_allow_html=True)
        st.divider()

        selected = st.radio("功能選單", MENUS.get(role, []),
                            label_visibility="collapsed")
        st.divider()
        if st.button("🚪 登出", use_container_width=True):
            logout()

        st.markdown("""
---
<small>
📢 <b>注意事項</b><br>
本系統供桌球教室內部管理使用。<br>
所有學員資料依個資保護原則處理，<br>
請勿將帳號密碼提供他人使用。
</small>
""", unsafe_allow_html=True)

    return selected


# ══════════════════════════════════════════════════════════════
# 👤  學員功能頁面
# ══════════════════════════════════════════════════════════════

def page_my_courses():
    st.markdown('<div class="page-title">📚 我的課程</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")

    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT c.id, c.course_type AS 課程類型, c.schedule_day AS 星期,
                   c.schedule_time AS 上課時間, c.duration AS 時長_分鐘,
                   t.name AS 桌次, co.name AS 教練, c.fee AS 費用_元
            FROM Enrollments e
            JOIN Courses c  ON e.course_id  = c.id
            JOIN Coaches co ON c.coach_id   = co.id
            JOIN Tables  t  ON c.table_id   = t.id
            WHERE e.student_id = ?
            ORDER BY c.schedule_day, c.schedule_time
        """, conn, params=(sid,))

    if df.empty:
        st.info("目前尚未報名任何課程，請聯繫管理者報名。")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("已報名課程數",   len(df))
    col2.metric("每月課程費用合計", f"NT$ {df['費用_元'].sum():,.0f}")
    col3.metric("平均課程時長",   f"{df['時長_分鐘'].mean():.0f} 分鐘")
    st.divider()
    st.dataframe(df.drop(columns=["id"]), use_container_width=True, height=300)


def page_leave_request():
    st.markdown('<div class="page-title">🙏 請假申請</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")

    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT c.id,
                   c.course_type || ' ' || c.schedule_day || ' ' || c.schedule_time AS label,
                   c.schedule_day
            FROM Enrollments e JOIN Courses c ON e.course_id=c.id
            WHERE e.student_id=?
        """, conn, params=(sid,))

    if courses.empty:
        st.warning("您尚未報名任何課程，無法申請請假。")
        return

    course_map = dict(zip(courses["label"], courses["id"]))
    day_map    = dict(zip(courses["id"], courses["schedule_day"]))

    st.markdown('<div class="section-title">📝 申請請假</div>', unsafe_allow_html=True)
    with st.form("leave_form"):
        selected_course = st.selectbox("選擇課程", list(course_map.keys()))
        leave_date      = st.date_input("請假日期", min_value=date.today())
        reason          = st.text_area("請假原因（選填）", height=80)
        submitted       = st.form_submit_button("📨 送出請假申請", type="primary")

    if submitted:
        cid = course_map[selected_course]
        # 提示日期與排定上課日不符（不阻擋送出）
        course_weekday = WEEKDAY_TO_INT.get(day_map[cid], -1)
        if leave_date.weekday() != course_weekday:
            wd = ["一","二","三","四","五","六","日"]
            st.warning(
                f"所選日期（{wd[leave_date.weekday()]}）非該課程上課日"
                f"（{day_map[cid]}），確定已送出。")
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO LeaveRequests"
                    "(student_id,course_id,leave_date,reason,status,created_at)"
                    " VALUES(?,?,?,?,'pending',?)",
                    (sid, cid, leave_date.isoformat(), reason,
                     datetime.now().isoformat()))
                conn.commit()
            st.success("✅ 請假申請已送出，等待教練審核中。")
        except Exception as e:
            st.error(f"申請失敗：{e}")

    st.divider()
    st.markdown('<div class="section-title">📋 歷史請假紀錄</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        hist = pd.read_sql_query("""
            SELECT lr.leave_date AS 請假日期,
                   c.course_type || ' ' || c.schedule_day AS 課程,
                   lr.reason AS 原因,
                   CASE lr.status
                     WHEN 'pending'  THEN '⏳ 審核中'
                     WHEN 'approved' THEN '✅ 已核准'
                     WHEN 'rejected' THEN '❌ 已拒絕'
                   END AS 狀態,
                   COALESCE(lr.reject_reason,'') AS 駁回原因,
                   lr.created_at AS 申請時間
            FROM LeaveRequests lr
            JOIN Courses c ON lr.course_id=c.id
            WHERE lr.student_id=?
            ORDER BY lr.leave_date DESC
        """, conn, params=(sid,))
    if hist.empty:
        st.info("尚無請假紀錄。")
    else:
        st.dataframe(hist, use_container_width=True, height=280)

    # [新增] 待補課紀錄
    st.divider()
    st.markdown('<div class="section-title">🔄 待補課紀錄</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        makeup = pd.read_sql_query("""
            SELECT cs.session_date AS 課堂日期,
                   c.course_type || ' ' || c.schedule_day AS 課程,
                   lr.leave_date AS 請假日期
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id = cs.id
            JOIN Courses c        ON cs.course_id  = c.id
            JOIN LeaveRequests lr ON lr.student_id = a.student_id
                                  AND lr.course_id  = cs.course_id
                                  AND lr.leave_date  = cs.session_date
                                  AND lr.status      = 'approved'
            WHERE a.student_id=? AND a.status='leave'
            ORDER BY cs.session_date DESC
        """, conn, params=(sid,))
    if makeup.empty:
        st.info("目前無待補課紀錄。")
    else:
        st.dataframe(makeup, use_container_width=True, height=200)
        st.caption("補課安排請線下與教練協調。")


def page_payment_status():
    # [修改] 移除 PDF 下載區塊，新增 paid_time 欄位顯示
    st.markdown('<div class="page-title">💳 繳費狀況</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")

    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT p.id, c.course_type || ' ' || c.schedule_day AS 課程,
                   p.period AS 期別, p.amount AS 金額,
                   COALESCE(p.paid_date,'—') AS 繳費日期,
                   COALESCE(p.paid_time,'—') AS 繳費時間,
                   p.is_paid, p.created_at AS 建立時間
            FROM Payments p JOIN Courses c ON p.course_id=c.id
            WHERE p.student_id=?
            ORDER BY p.period DESC
        """, conn, params=(sid,))

    if df.empty:
        st.info("目前無繳費紀錄。")
        return

    paid_total   = df[df["is_paid"]==1]["金額"].sum()
    unpaid_total = df[df["is_paid"]==0]["金額"].sum()
    total        = paid_total + unpaid_total
    rate         = paid_total / total * 100 if total > 0 else 0
    paid_count   = (df["is_paid"]==1).sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("已繳總額",   f"NT$ {paid_total:,.0f}")
    col2.metric("未繳總額",   f"NT$ {unpaid_total:,.0f}")
    col3.metric("繳費完成率", f"{rate:.1f}%")
    st.divider()

    df["狀態"] = df["is_paid"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
    display = df[["課程","期別","金額","建立時間","繳費日期","繳費時間","狀態"]].copy()
    display["金額"] = display["金額"].apply(lambda x: f"NT$ {x:,.0f}")
    st.dataframe(display, use_container_width=True, height=350)


def page_attendance_record():
    st.markdown('<div class="page-title">📋 出勤紀錄</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")

    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT cs.session_date AS 日期,
                   c.course_type || ' ' || c.schedule_day AS 課程,
                   CASE a.status
                     WHEN 'present' THEN '✅ 出席'
                     WHEN 'absent'  THEN '❌ 缺席'
                     WHEN 'leave'   THEN '🟡 請假'
                   END AS 狀態,
                   a.status AS _status
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses c        ON cs.course_id=c.id
            WHERE a.student_id=?
            ORDER BY cs.session_date DESC
        """, conn, params=(sid,))

    if df.empty:
        st.info("目前尚無出勤紀錄。")
        return

    present = (df["_status"]=="present").sum()
    absent  = (df["_status"]=="absent").sum()
    leave   = (df["_status"]=="leave").sum()
    total   = len(df)
    rate    = present / total * 100 if total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("出席次數", present)
    col2.metric("缺席次數", absent)
    col3.metric("請假次數", leave)
    col4.metric("出席率",   f"{rate:.1f}%")
    st.divider()

    st.dataframe(df.drop(columns=["_status"]), use_container_width=True, height=320)

    st.markdown('<div class="section-title">📊 近 3 個月出勤統計</div>',
                unsafe_allow_html=True)
    with get_conn() as conn:
        chart_df = pd.read_sql_query("""
            SELECT substr(cs.session_date,1,7) AS 月份, a.status, COUNT(*) AS 次數
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            WHERE a.student_id=?
              AND cs.session_date >= date('now','-3 months')
            GROUP BY 月份, a.status
        """, conn, params=(sid,))

    if not chart_df.empty:
        pivot = chart_df.pivot_table(
            index="月份", columns="status", values="次數", fill_value=0)
        color_map = {"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
        label_map = {"present":"出席","absent":"缺席","leave":"請假"}
        fig = go.Figure()
        for col in pivot.columns:
            fig.add_trace(go.Bar(
                name=label_map.get(col, col), x=pivot.index, y=pivot[col],
                marker_color=color_map.get(col, "#999")))
        fig.update_layout(barmode="group", height=300,
                          margin=dict(l=0,r=0,t=20,b=0),
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 🏫  教練功能頁面
# ══════════════════════════════════════════════════════════════

def page_coach_profile():
    st.markdown('<div class="page-title">👤 個人簡介編輯</div>', unsafe_allow_html=True)
    st.divider()
    uid = st.session_state.get("user_id")

    with get_conn() as conn:
        coach = conn.execute(
            "SELECT * FROM Coaches WHERE user_id=?", (uid,)).fetchone()

    if not coach:
        st.error("找不到教練資料，請聯繫管理者。")
        return

    col1, col2 = st.columns(2)
    col1.info(f"**姓名：** {coach['name']}\n\n"
              f"**電話：** {coach['phone']}\n\n"
              f"**專長：** {coach['specialty']}")
    col2.info(f"**個人簡介：**\n\n{coach['bio']}")
    st.divider()

    st.markdown('<div class="section-title">✏️ 編輯資料</div>', unsafe_allow_html=True)
    with st.form("coach_profile_form"):
        name      = st.text_input("姓名",             value=coach["name"])
        phone     = st.text_input("聯絡電話",          value=coach["phone"])
        bio       = st.text_area("個人簡介 / 教學經歷", value=coach["bio"], height=120)
        specialty = st.text_input("專長",             value=coach["specialty"])
        saved     = st.form_submit_button("💾 儲存變更", type="primary")

    if saved:
        if not name.strip():
            st.error("姓名不可為空。")
            return
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE Coaches SET name=?,phone=?,bio=?,specialty=? WHERE user_id=?",
                    (name, phone, bio, specialty, uid))
                conn.commit()
            st.session_state["profile_name"] = name
            st.success("✅ 個人簡介已更新！")
            st.rerun()
        except Exception as e:
            st.error(f"更新失敗：{e}")


def page_coach_students():
    st.markdown('<div class="page-title">👥 課程學員名單</div>', unsafe_allow_html=True)
    st.divider()
    cid_coach = st.session_state.get("profile_id")

    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT id,
                   course_type || ' ' || schedule_day || ' ' || schedule_time AS label
            FROM Courses WHERE coach_id=? ORDER BY schedule_day, schedule_time
        """, conn, params=(cid_coach,))

    if courses.empty:
        st.info("您目前沒有負責的課程。")
        return

    course_map = dict(zip(courses["label"], courses["id"]))
    selected   = st.selectbox("選擇課程", list(course_map.keys()))
    cid        = course_map[selected]

    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT s.name AS 學員姓名, s.phone AS 電話, s.email AS Email,
                   e.enrolled_date AS 報名日期
            FROM Enrollments e JOIN Students s ON e.student_id=s.id
            WHERE e.course_id=? ORDER BY s.name
        """, conn, params=(cid,))

    st.metric("報名人數", len(df))
    st.divider()
    if df.empty:
        st.info("此課程尚無學員報名。")
    else:
        st.dataframe(df, use_container_width=True, height=350)


def page_coach_attendance():
    # [修改] 新增請假聯動：已核准請假自動帶入「請假」並顯示標籤
    st.markdown('<div class="page-title">✅ 課堂點名</div>', unsafe_allow_html=True)
    st.divider()
    cid_coach = st.session_state.get("profile_id")

    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT c.id,
                   c.course_type || ' ' || c.schedule_day || ' ' || c.schedule_time AS label,
                   c.schedule_day, c.schedule_time, c.table_id
            FROM Courses c WHERE c.coach_id=? ORDER BY c.schedule_day, c.schedule_time
        """, conn, params=(cid_coach,))

    if courses.empty:
        st.info("您目前沒有負責的課程。")
        return

    course_map  = dict(zip(courses["label"], courses["id"]))
    course_info = courses.set_index("id")
    col1, col2  = st.columns(2)
    with col1:
        selected_label = st.selectbox("選擇課程", list(course_map.keys()))
    with col2:
        session_date = st.date_input("上課日期", value=date.today())

    cid = course_map[selected_label]
    row = course_info.loc[cid]

    # 上課日驗證提示
    course_weekday = WEEKDAY_TO_INT.get(str(row["schedule_day"]), -1)
    if session_date.weekday() != course_weekday:
        wd = ["一","二","三","四","五","六","日"]
        st.warning(
            f"⚠️ 所選日期（{wd[session_date.weekday()]}）"
            f"與課程排定上課日（{row['schedule_day']}）不符，請確認。")

    with get_conn() as conn:
        students = pd.read_sql_query("""
            SELECT s.id, s.name FROM Enrollments e
            JOIN Students s ON e.student_id=s.id
            WHERE e.course_id=? ORDER BY s.name
        """, conn, params=(cid,))

    if students.empty:
        st.warning("此課程尚無學員，無法點名。")
        return

    # 取得或建立 ClassSession
    with get_conn() as conn:
        sess = conn.execute(
            "SELECT id FROM ClassSessions WHERE course_id=? AND session_date=?",
            (cid, session_date.isoformat())).fetchone()
        if sess is None:
            cur = conn.execute(
                "INSERT INTO ClassSessions"
                "(course_id,session_date,session_time,coach_id,table_id,created_by)"
                " VALUES(?,?,?,?,?,'coach_點名')",
                (cid, session_date.isoformat(),
                 str(row["schedule_time"]), cid_coach, int(row["table_id"])))
            conn.commit()
            session_id = cur.lastrowid
        else:
            session_id = sess["id"]

    # 取得現有出勤紀錄與已核准請假名單
    with get_conn() as conn:
        existing        = conn.execute(
            "SELECT student_id, status FROM Attendance WHERE session_id=?",
            (session_id,)).fetchall()
        approved_leaves = set(
            r["student_id"] for r in conn.execute("""
                SELECT student_id FROM LeaveRequests
                WHERE course_id=? AND leave_date=? AND status='approved'
            """, (cid, session_date.isoformat())).fetchall())

    exist_map      = {r["student_id"]: r["status"] for r in existing}
    status_opts    = ["出席","缺席","請假"]
    status_map_rev = {"出席":"present","缺席":"absent","請假":"leave"}
    status_map_fwd = {"present":"出席","absent":"缺席","leave":"請假"}

    st.markdown(f'<div class="section-title">👥 點名列表（共 {len(students)} 位學員）</div>',
                unsafe_allow_html=True)

    selections = {}
    for _, stu in students.iterrows():
        # 已核准請假 → 預設請假並顯示標籤
        if stu["id"] in approved_leaves:
            default = "請假"
            suffix  = "　🏷️ 已核准請假"
        else:
            default = status_map_fwd.get(exist_map.get(stu["id"], "present"), "出席")
            suffix  = ""
        val = st.radio(
            f"**{stu['name']}**{suffix}", status_opts,
            index=status_opts.index(default),
            horizontal=True, key=f"att_{session_id}_{stu['id']}")
        selections[stu["id"]] = val

    if st.button("📝 送出點名結果", type="primary", use_container_width=True):
        try:
            with get_conn() as conn:
                for sid_s, status_label in selections.items():
                    conn.execute("""
                        INSERT INTO Attendance(session_id,student_id,status)
                        VALUES(?,?,?)
                        ON CONFLICT(session_id,student_id)
                        DO UPDATE SET status=excluded.status
                    """, (session_id, sid_s, status_map_rev[status_label]))
                conn.commit()
            present_count = sum(1 for v in selections.values() if v=="出席")
            absent_count  = sum(1 for v in selections.values() if v=="缺席")
            st.success(f"✅ 點名完成！出席：{present_count} 人，缺席：{absent_count} 人")
        except Exception as e:
            st.error(f"點名失敗：{e}")


# ── [新增] 教練請假審核（F-003-4）──────────────────────────

def page_coach_leave_review():
    st.markdown('<div class="page-title">🙏 請假審核</div>', unsafe_allow_html=True)
    st.divider()
    cid_coach = st.session_state.get("profile_id")
    uid       = st.session_state.get("user_id")

    # 待審核列表
    st.markdown('<div class="section-title">⏳ 待審核申請</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        pending = pd.read_sql_query("""
            SELECT lr.id, s.name AS 學員,
                   c.course_type || ' ' || c.schedule_day AS 課程,
                   lr.leave_date AS 請假日期, lr.reason AS 原因,
                   lr.created_at AS 申請時間
            FROM LeaveRequests lr
            JOIN Students s ON lr.student_id=s.id
            JOIN Courses  c ON lr.course_id=c.id
            WHERE lr.status='pending' AND c.coach_id=?
            ORDER BY lr.leave_date
        """, conn, params=(cid_coach,))

    if pending.empty:
        st.info("目前無待審核的請假申請。")
    else:
        for _, row in pending.iterrows():
            with st.expander(
                    f"⏳ {row['學員']} ｜ {row['課程']} ｜ 請假日：{row['請假日期']}"):
                st.write(f"**申請時間：** {row['申請時間']}")
                st.write(f"**請假原因：** {row['原因'] or '（未填寫）'}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ 核准", key=f"approve_{row['id']}", type="primary"):
                        with get_conn() as conn:
                            conn.execute("""
                                UPDATE LeaveRequests
                                SET status='approved', reviewed_by=?, reviewed_at=?
                                WHERE id=?
                            """, (uid, datetime.now().isoformat(), int(row["id"])))
                            conn.commit()
                        st.success("已核准！")
                        st.rerun()
                with col2:
                    rr = st.text_input("駁回原因", key=f"rr_{row['id']}",
                                       placeholder="請填寫駁回原因")
                    if st.button("❌ 駁回", key=f"reject_{row['id']}"):
                        if not rr.strip():
                            st.warning("請填寫駁回原因後再送出。")
                        else:
                            with get_conn() as conn:
                                conn.execute("""
                                    UPDATE LeaveRequests
                                    SET status='rejected', reviewed_by=?,
                                        reviewed_at=?, reject_reason=?
                                    WHERE id=?
                                """, (uid, datetime.now().isoformat(),
                                      rr, int(row["id"])))
                                conn.commit()
                            st.success("已駁回。")
                            st.rerun()

    st.divider()
    st.markdown('<div class="section-title">📋 歷史審核紀錄</div>', unsafe_allow_html=True)
    filter_status = st.selectbox("篩選狀態", ["全部","已核准","已駁回"],
                                 key="leave_review_filter")
    status_fmap   = {"全部": None, "已核准": "approved", "已駁回": "rejected"}
    fval          = status_fmap[filter_status]

    q      = """
        SELECT s.name AS 學員,
               c.course_type || ' ' || c.schedule_day AS 課程,
               lr.leave_date AS 請假日期, lr.reason AS 原因,
               CASE lr.status
                 WHEN 'approved' THEN '✅ 已核准'
                 WHEN 'rejected' THEN '❌ 已駁回'
               END AS 狀態,
               COALESCE(lr.reject_reason,'') AS 駁回原因,
               lr.reviewed_at AS 審核時間
        FROM LeaveRequests lr
        JOIN Students s ON lr.student_id=s.id
        JOIN Courses  c ON lr.course_id=c.id
        WHERE c.coach_id=? AND lr.status != 'pending'
    """
    params = [cid_coach]
    if fval:
        q += " AND lr.status=?"
        params.append(fval)
    q += " ORDER BY lr.reviewed_at DESC"

    with get_conn() as conn:
        hist = pd.read_sql_query(q, conn, params=params)

    if hist.empty:
        st.info("尚無歷史審核紀錄。")
    else:
        st.dataframe(hist, use_container_width=True, height=300)


# ══════════════════════════════════════════════════════════════
# 🔧  管理者功能頁面
# ══════════════════════════════════════════════════════════════

def page_admin_courses():
    # [修改] 衝突比對改時段重疊；視覺化改甘特圖；新增課程移除防呆（二次確認）
    st.markdown('<div class="page-title">📅 課程管理</div>', unsafe_allow_html=True)
    st.divider()
    tab_list, tab_add, tab_enroll, tab_visual = st.tabs(
        ["📋 課程總表", "➕ 新增課程", "🎓 學員報名管理", "🏓 桌次視覺化"])

    # ── 課程總表 + 移除 ─────────────────────────────────────
    with tab_list:
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT c.id AS 課程ID, c.course_type AS 課程類型, co.name AS 教練,
                       c.schedule_day AS 星期, c.schedule_time AS 開始時間,
                       c.duration AS 時長_分鐘, t.name AS 桌次, c.fee AS 費用_元,
                       COUNT(e.id) AS 報名人數
                FROM Courses c
                JOIN Coaches co ON c.coach_id=co.id
                JOIN Tables  t  ON c.table_id=t.id
                LEFT JOIN Enrollments e ON e.course_id=c.id
                GROUP BY c.id
                ORDER BY c.schedule_day, c.schedule_time
            """, conn)

        if df.empty:
            st.info("目前無課程資料。")
        else:
            # 計算結束時間
            def calc_end(r):
                try:
                    sm = time_to_minutes(str(r["開始時間"]))
                    em = sm + int(r["時長_分鐘"])
                    return f"{em//60:02d}:{em%60:02d}"
                except Exception:
                    return "—"
            df["結束時間"] = df.apply(calc_end, axis=1)
            st.dataframe(
                df[["課程ID","課程類型","教練","星期","開始時間","結束時間",
                    "時長_分鐘","桌次","費用_元","報名人數"]],
                use_container_width=True, height=360)

            st.divider()
            st.markdown('<div class="section-title">🗑️ 移除課程</div>',
                        unsafe_allow_html=True)
            remove_options = {
                f"{r['課程ID']} - {r['課程類型']} {r['星期']} {r['開始時間']}": r["課程ID"]
                for _, r in df.iterrows()
            }
            sel_remove = st.selectbox("選擇要移除的課程", list(remove_options.keys()),
                                      key="remove_course_sel")
            remove_cid = remove_options[sel_remove]

            # 顯示關聯資料筆數（防呆）
            with get_conn() as conn:
                enroll_cnt = conn.execute(
                    "SELECT COUNT(*) FROM Enrollments WHERE course_id=?",
                    (remove_cid,)).fetchone()[0]
                attend_cnt = conn.execute("""
                    SELECT COUNT(*) FROM Attendance a
                    JOIN ClassSessions cs ON a.session_id=cs.id
                    WHERE cs.course_id=?
                """, (remove_cid,)).fetchone()[0]
                unpaid_cnt = conn.execute(
                    "SELECT COUNT(*) FROM Payments WHERE course_id=? AND is_paid=0",
                    (remove_cid,)).fetchone()[0]

            if enroll_cnt or attend_cnt or unpaid_cnt:
                st.warning(
                    f"此課程有關聯資料（報名人數：{enroll_cnt}、"
                    f"出勤紀錄：{attend_cnt} 筆、未繳費：{unpaid_cnt} 筆），"
                    "確認移除將一併刪除所有關聯紀錄。")

            confirm_del = st.checkbox("確認刪除", key="confirm_del_course")
            if st.button("🗑️ 執行移除", key="do_remove_course"):
                if not confirm_del:
                    st.warning("請先勾選「確認刪除」後再執行。")
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                "DELETE FROM Enrollments WHERE course_id=?", (remove_cid,))
                            for s in conn.execute(
                                    "SELECT id FROM ClassSessions WHERE course_id=?",
                                    (remove_cid,)).fetchall():
                                conn.execute(
                                    "DELETE FROM Attendance WHERE session_id=?", (s["id"],))
                            conn.execute(
                                "DELETE FROM ClassSessions WHERE course_id=?", (remove_cid,))
                            conn.execute(
                                "DELETE FROM LeaveRequests WHERE course_id=?", (remove_cid,))
                            conn.execute(
                                "DELETE FROM Payments WHERE course_id=?", (remove_cid,))
                            conn.execute(
                                "DELETE FROM Courses WHERE id=?", (remove_cid,))
                            conn.commit()
                        st.success("✅ 課程已移除。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"移除失敗：{e}")

    # ── 新增課程 ─────────────────────────────────────────────
    with tab_add:
        with get_conn() as conn:
            coaches = pd.read_sql_query(
                "SELECT id, name FROM Coaches ORDER BY name", conn)

        if coaches.empty:
            st.warning("尚無教練資料，請先新增教練帳號。")
        else:
            coach_map = dict(zip(coaches["name"], coaches["id"]))
            with st.form("add_course_form"):
                col1, col2 = st.columns(2)
                with col1:
                    c_type    = st.selectbox("課程類型",
                                             ["團體班","個人班","寒假班","暑假班"])
                    coach_sel = st.selectbox("選擇教練", list(coach_map.keys()))
                    day       = st.selectbox("上課星期",
                                             ["週一","週二","週三","週四","週五","週六","週日"])
                    time_val  = st.time_input(
                        "上課時間",
                        value=datetime.strptime("09:00","%H:%M").time())
                with col2:
                    duration = st.selectbox("課程時長（分鐘）", [60, 90, 120])
                    table_no = st.selectbox("使用桌次", list(range(1, 9)))
                    fee      = st.number_input("費用（元）", min_value=0,
                                              value=2000, step=100)
                submitted = st.form_submit_button("✅ 新增課程", type="primary")

            if submitted:
                time_str = time_val.strftime("%H:%M")
                # [修改] 時段重疊比對
                with get_conn() as conn:
                    conflicts = check_table_conflict(
                        conn, day, time_str, duration, table_no)
                if conflicts:
                    with get_conn() as conn:
                        for conf_id in conflicts:
                            c = conn.execute(
                                "SELECT schedule_time, duration FROM Courses WHERE id=?",
                                (conf_id,)).fetchone()
                            em = time_to_minutes(c["schedule_time"]) + c["duration"]
                            st.error(
                                f"⚠️ 桌次 {table_no} 已被佔用"
                                f"（衝突課程 ID：{conf_id}，"
                                f"時段：{c['schedule_time']}～{em//60:02d}:{em%60:02d}），"
                                "請選擇其他桌次或時段。")
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute("""
                                INSERT INTO Courses
                                (course_type,coach_id,schedule_day,
                                 schedule_time,duration,table_id,fee)
                                VALUES(?,?,?,?,?,?,?)
                            """, (c_type, coach_map[coach_sel], day,
                                  time_str, duration, table_no, fee))
                            conn.commit()
                        st.success("✅ 課程新增成功！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗：{e}")

    # ── 學員報名管理 ─────────────────────────────────────────
    with tab_enroll:
        with get_conn() as conn:
            all_courses  = pd.read_sql_query("""
                SELECT c.id,
                       c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label
                FROM Courses c ORDER BY label
            """, conn)
            all_students = pd.read_sql_query(
                "SELECT id, name FROM Students ORDER BY name", conn)

        if all_courses.empty or all_students.empty:
            st.info("請先建立課程與學員資料。")
        else:
            cmap = dict(zip(all_courses["label"], all_courses["id"]))
            smap = dict(zip(all_students["name"], all_students["id"]))

            col1, col2 = st.columns(2)
            with col1:
                sel_course = st.selectbox("選擇課程", list(cmap.keys()),
                                          key="enroll_course")
                cid_enroll = cmap[sel_course]
                with get_conn() as conn:
                    enrolled_ids = [r["student_id"] for r in conn.execute(
                        "SELECT student_id FROM Enrollments WHERE course_id=?",
                        (cid_enroll,)).fetchall()]
                already = [s for s in all_students["name"] if smap[s] in enrolled_ids]
                not_yet = [s for s in all_students["name"] if smap[s] not in enrolled_ids]

                st.markdown(f"**已報名學員（{len(already)} 人）**")
                for nm in already:
                    c1, c2 = st.columns([3, 1])
                    c1.write(nm)
                    if c2.button("移除", key=f"rm_{smap[nm]}_{cid_enroll}"):
                        with get_conn() as conn:
                            # 1. 先刪除繳費紀錄（避免外鍵衝突）
                            conn.execute(
                                "DELETE FROM Payments WHERE student_id=? AND course_id=?",
                                (smap[nm], cid_enroll))
                            # 2. 刪除出勤紀錄
                            sessions = conn.execute(
                                "SELECT id FROM ClassSessions WHERE course_id=?",
                                (cid_enroll,)).fetchall()
                            for sess in sessions:
                                conn.execute(
                                    "DELETE FROM Attendance WHERE session_id=? AND student_id=?",
                                    (sess["id"], smap[nm]))
                            # 3. 刪除請假申請
                            conn.execute(
                                "DELETE FROM LeaveRequests WHERE student_id=? AND course_id=?",
                                (smap[nm], cid_enroll))
                            # 4. 最後刪除報名紀錄
                            conn.execute(
                                "DELETE FROM Enrollments WHERE student_id=? AND course_id=?",
                                (smap[nm], cid_enroll))
                            conn.commit()
                        st.success(f"✅ 已移除 {nm} 的報名紀錄（含繳費與出勤資料）。")
                        st.rerun()

            with col2:
                st.markdown("**新增學員報名**")
                if not_yet:
                    add_stu = st.selectbox("選擇學員", not_yet, key="add_stu")
                    if st.button("➕ 加入報名", type="primary"):
                        try:
                            with get_conn() as conn:
                                conn.execute("""
                                    INSERT INTO Enrollments
                                    (student_id,course_id,enrolled_date)
                                    VALUES(?,?,?)
                                """, (smap[add_stu], cid_enroll,
                                      date.today().isoformat()))
                                conn.commit()
                            st.success(f"✅ {add_stu} 已加入課程！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"報名失敗：{e}")
                else:
                    st.info("所有學員皆已報名此課程。")

    # ── [修改] 桌次視覺化 → 甘特圖 ──────────────────────────
    with tab_visual:
        st.markdown('<div class="section-title">🏓 選定星期的桌次佔用狀況（甘特圖）</div>',
                    unsafe_allow_html=True)
        sel_day = st.selectbox(
            "選擇星期",
            ["週一","週二","週三","週四","週五","週六","週日"],
            key="table_visual_day")

        with get_conn() as conn:
            day_courses = pd.read_sql_query("""
                SELECT c.id, c.table_id, c.schedule_time, c.duration,
                       c.course_type, co.name AS coach_name
                FROM Courses c JOIN Coaches co ON c.coach_id=co.id
                WHERE c.schedule_day=?
            """, conn, params=(sel_day,))

        fig = go.Figure()
        for _, tc in day_courses.iterrows():
            sm = time_to_minutes(str(tc["schedule_time"]))
            em = sm + int(tc["duration"])
            fig.add_trace(go.Bar(
                x=[int(tc["duration"]) / 60],
                y=[f"桌{tc['table_id']}"],
                base=[sm / 60],
                orientation="h",
                marker_color="#FF6B35",
                hovertemplate=(
                    f"<b>桌{tc['table_id']}</b><br>"
                    f"課程：{tc['course_type']}<br>"
                    f"教練：{tc['coach_name']}<br>"
                    f"時段：{tc['schedule_time']}～{em//60:02d}:{em%60:02d}<br>"
                    "<extra></extra>"),
                showlegend=False))

        fig.update_layout(
            barmode="overlay", height=380,
            xaxis=dict(
                title="時間", range=[8, 22],
                tickvals=list(range(8, 23)),
                ticktext=[f"{h:02d}:00" for h in range(8, 23)]),
            yaxis=dict(
                title="桌次", categoryorder="array",
                categoryarray=[f"桌{i}" for i in range(8, 0, -1)]),
            margin=dict(l=40,r=20,t=20,b=40),
            plot_bgcolor="#F5F5F5")
        st.plotly_chart(fig, use_container_width=True)


def page_admin_attendance():
    st.markdown('<div class="page-title">📊 出勤總表</div>', unsafe_allow_html=True)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("起始日期", value=date.today()-timedelta(days=30))
    with col2:
        end_date   = st.date_input("結束日期",  value=date.today())

    if start_date > end_date:
        st.error("起始日期不可晚於結束日期。")
        return

    with st.spinner("資料載入中..."):
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT cs.session_date AS 日期,
                       c.course_type || ' ' || c.schedule_day AS 課程,
                       co.name AS 教練, s.name AS 學員,
                       CASE a.status
                         WHEN 'present' THEN '✅ 出席'
                         WHEN 'absent'  THEN '❌ 缺席'
                         WHEN 'leave'   THEN '🟡 請假'
                       END AS 狀態,
                       a.status AS _status
                FROM Attendance a
                JOIN ClassSessions cs ON a.session_id=cs.id
                JOIN Courses  c       ON cs.course_id=c.id
                JOIN Coaches  co      ON cs.coach_id=co.id
                JOIN Students s       ON a.student_id=s.id
                WHERE cs.session_date BETWEEN ? AND ?
                ORDER BY cs.session_date DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))

    if df.empty:
        st.info("此區間無出勤紀錄。")
        return

    total   = len(df)
    present = (df["_status"]=="present").sum()
    absent  = (df["_status"]=="absent").sum()
    rate    = present / total * 100 if total > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總紀錄筆數", total)
    col2.metric("出席人次",   present)
    col3.metric("缺席人次",   absent)
    col4.metric("整體出席率", f"{rate:.1f}%")
    st.divider()

    display = df.drop(columns=["_status"])
    st.dataframe(display, use_container_width=True, height=380)
    csv = display.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ 匯出 CSV", data=csv,
                       file_name=f"出勤總表_{start_date}_{end_date}.csv",
                       mime="text/csv")
    st.divider()

    st.markdown('<div class="section-title">📊 每日出勤統計</div>', unsafe_allow_html=True)
    daily       = df.groupby(["日期","_status"]).size().reset_index(name="count")
    daily_pivot = daily.pivot_table(
        index="日期", columns="_status", values="count", fill_value=0)
    color_map = {"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
    label_map = {"present":"出席","absent":"缺席","leave":"請假"}
    fig = go.Figure()
    for col in daily_pivot.columns:
        fig.add_trace(go.Bar(
            name=label_map.get(col,col), x=daily_pivot.index, y=daily_pivot[col],
            marker_color=color_map.get(col,"#999")))
    fig.update_layout(barmode="stack", height=320,
                      margin=dict(l=0,r=0,t=20,b=0),
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)


def page_admin_payments():
    # [修改] 移除 PDF；新增 paid_time 欄位；改 tab 結構
    st.markdown('<div class="page-title">💰 繳費管理</div>', unsafe_allow_html=True)
    st.divider()

    tab_gen, tab_manage = st.tabs(["📋 產生繳費單", "💳 繳費紀錄管理"])

    # ── 批次產生繳費單 ────────────────────────────────────────
    with tab_gen:
        st.markdown('<div class="section-title">📋 批次產生繳費單</div>',
                    unsafe_allow_html=True)
        with get_conn() as conn:
            all_c = pd.read_sql_query("""
                SELECT c.id,
                       c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label,
                       c.fee
                FROM Courses c ORDER BY label
            """, conn)

        if all_c.empty:
            st.info("目前無課程資料。")
        else:
            cmap    = dict(zip(all_c["label"], all_c["id"]))
            fee_map = dict(zip(all_c["id"], all_c["fee"]))
            col1, col2 = st.columns(2)
            with col1:
                period_input = st.text_input(
                    "繳費期別（YYYY-MM）",
                    value=date.today().strftime("%Y-%m"))
            with col2:
                sel_c   = st.selectbox("選擇課程", list(cmap.keys()), key="gen_pay_c")
            cid_gen = cmap[sel_c]

            if st.button("📋 產生繳費單", type="primary"):
                if len(period_input) != 7:
                    st.error("請輸入正確的期別格式（YYYY-MM）。")
                else:
                    with get_conn() as conn:
                        enrolled = conn.execute(
                            "SELECT student_id FROM Enrollments WHERE course_id=?",
                            (cid_gen,)).fetchall()
                        created = 0
                        now_str = datetime.now().isoformat()
                        for e in enrolled:
                            ex = conn.execute(
                                "SELECT id FROM Payments "
                                "WHERE student_id=? AND course_id=? AND period=?",
                                (e["student_id"], cid_gen, period_input)).fetchone()
                            if not ex:
                                conn.execute(
                                    "INSERT INTO Payments"
                                    "(student_id,course_id,amount,period,created_at)"
                                    " VALUES(?,?,?,?,?)",
                                    (e["student_id"], cid_gen,
                                     fee_map[cid_gen], period_input, now_str))
                                created += 1
                        conn.commit()
                    st.success(
                        f"✅ 已產生 {created} 筆繳費單"
                        f"（{len(enrolled)-created} 筆已存在，跳過）。")

    # ── 繳費紀錄管理 ─────────────────────────────────────────
    with tab_manage:
        filter_opt = st.radio("篩選", ["全部","未繳費","已繳費"], horizontal=True)
        filter_map = {"全部": None, "未繳費": 0, "已繳費": 1}
        fval       = filter_map[filter_opt]

        q      = """
            SELECT p.id, s.name AS 學員,
                   c.course_type || ' ' || c.schedule_day AS 課程,
                   p.period AS 期別, p.amount AS 金額,
                   p.created_at AS 建立時間,
                   COALESCE(p.paid_date,'—') AS 繳費日期,
                   COALESCE(p.paid_time,'—') AS 繳費時間,
                   p.is_paid
            FROM Payments p
            JOIN Students s ON p.student_id=s.id
            JOIN Courses  c ON p.course_id=c.id
        """
        params = []
        if fval is not None:
            q += " WHERE p.is_paid=?"
            params.append(fval)
        q += " ORDER BY p.is_paid ASC, s.name"

        with get_conn() as conn:
            df = pd.read_sql_query(q, conn, params=params)

        if df.empty:
            st.info("沒有符合條件的繳費紀錄。")
        else:
            total_amt  = df["金額"].sum()
            paid_amt   = df[df["is_paid"]==1]["金額"].sum()
            unpaid_amt = df[df["is_paid"]==0]["金額"].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("總應收金額", f"NT$ {total_amt:,.0f}")
            col2.metric("已收金額",   f"NT$ {paid_amt:,.0f}")
            col3.metric("未收金額",   f"NT$ {unpaid_amt:,.0f}")
            st.divider()

            for _, row in df.iterrows():
                icon = "✅" if row["is_paid"] else "❌"
                with st.expander(
                        f"{icon} {row['學員']} ｜ {row['課程']} ｜ "
                        f"{row['期別']} ｜ NT$ {row['金額']:,.0f}"):
                    c1, c2 = st.columns(2)
                    c1.write(f"**建立時間：** {row['建立時間']}")
                    c1.write(f"**繳費日期：** {row['繳費日期']}")
                    c2.write(f"**繳費時間：** {row['繳費時間']}")
                    if not row["is_paid"]:
                        mc1, mc2 = st.columns(2)
                        pay_date = mc1.date_input(
                            "繳費日期", value=date.today(),
                            key=f"pdate_{row['id']}")
                        pay_time = mc2.time_input(
                            "繳費時間", value=datetime.now().time(),
                            key=f"ptime_{row['id']}")
                        if st.button("💳 標記為已繳費",
                                     key=f"pay_{row['id']}", type="primary"):
                            try:
                                with get_conn() as conn:
                                    conn.execute("""
                                        UPDATE Payments
                                        SET is_paid=1, paid_date=?, paid_time=?
                                        WHERE id=?
                                    """, (pay_date.isoformat(),
                                          pay_time.strftime("%H:%M"),
                                          int(row["id"])))
                                    conn.commit()
                                st.success("✅ 繳費狀態已更新！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"操作失敗：{e}")


def page_admin_reports():
    st.markdown('<div class="page-title">📈 報表查詢</div>', unsafe_allow_html=True)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("起始日期", value=date.today().replace(day=1))
    with col2:
        end_date   = st.date_input("結束日期",  value=date.today())

    if start_date > end_date:
        st.error("起始日期不可晚於結束日期。")
        return

    tab1, tab2, tab3 = st.tabs(["📅 課程報表","👥 出勤統計報表","💰 繳費統計報表"])

    with tab1:
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT cs.session_date AS 日期, c.course_type AS 課程類型,
                       co.name AS 教練, t.name AS 桌次,
                       c.schedule_time AS 時間, c.duration AS 時長_分,
                       COUNT(a.id) AS 出席學員數
                FROM ClassSessions cs
                JOIN Courses  c  ON cs.course_id=c.id
                JOIN Coaches  co ON cs.coach_id=co.id
                JOIN Tables   t  ON cs.table_id=t.id
                LEFT JOIN Attendance a ON a.session_id=cs.id AND a.status='present'
                WHERE cs.session_date BETWEEN ? AND ?
                GROUP BY cs.id ORDER BY cs.session_date DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))

        if df.empty:
            st.info("此區間無上課紀錄。")
        else:
            c1, c2 = st.columns(2)
            c1.metric("上課總堂數",   len(df))
            c2.metric("平均出席人數", f"{df['出席學員數'].mean():.1f}")
            st.dataframe(df, use_container_width=True, height=350)
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 匯出 CSV", csv,
                               file_name=f"課程報表_{start_date}_{end_date}.csv",
                               mime="text/csv")

    with tab2:
        with get_conn() as conn:
            df2 = pd.read_sql_query("""
                SELECT s.name AS 學員,
                       SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS 出席,
                       SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END) AS 缺席,
                       SUM(CASE WHEN a.status='leave'   THEN 1 ELSE 0 END) AS 請假,
                       COUNT(*) AS 總次數
                FROM Attendance a
                JOIN ClassSessions cs ON a.session_id=cs.id
                JOIN Students s       ON a.student_id=s.id
                WHERE cs.session_date BETWEEN ? AND ?
                GROUP BY s.id ORDER BY 出席 DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))

        if df2.empty:
            st.info("此區間無出勤資料。")
        else:
            df2["出席率"] = (df2["出席"]/df2["總次數"]*100).round(1).astype(str)+"%"
            st.dataframe(df2, use_container_width=True, height=300)
            fig = px.bar(df2, x="學員", y="出席",
                         color_discrete_sequence=["#4CAF50"], title="學員出席次數")
            fig.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig, use_container_width=True)
            csv2 = df2.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 匯出 CSV", csv2,
                               file_name=f"出勤統計_{start_date}_{end_date}.csv",
                               mime="text/csv")

    with tab3:
        period_start = start_date.strftime("%Y-%m")
        period_end   = end_date.strftime("%Y-%m")
        with get_conn() as conn:
            df3 = pd.read_sql_query("""
                SELECT p.period AS 期別, s.name AS 學員,
                       c.course_type AS 課程類型,
                       p.amount AS 金額, p.is_paid AS 已繳,
                       COALESCE(p.paid_date,'—') AS 繳費日期
                FROM Payments p
                JOIN Students s ON p.student_id=s.id
                JOIN Courses  c ON p.course_id=c.id
                WHERE p.period BETWEEN ? AND ?
                ORDER BY p.period, s.name
            """, conn, params=(period_start, period_end))

        if df3.empty:
            st.info("此區間無繳費資料。")
        else:
            total_fee  = df3["金額"].sum()
            paid_fee   = df3[df3["已繳"]==1]["金額"].sum()
            unpaid_fee = df3[df3["已繳"]==0]["金額"].sum()
            pay_rate   = paid_fee / total_fee * 100 if total_fee > 0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("總應收", f"NT$ {total_fee:,.0f}")
            col2.metric("已收",   f"NT$ {paid_fee:,.0f}")
            col3.metric("未收",   f"NT$ {unpaid_fee:,.0f}")
            col4.metric("繳費率", f"{pay_rate:.1f}%")

            fig = go.Figure(go.Pie(
                labels=["已繳費","未繳費"],
                values=[paid_fee, unpaid_fee], hole=0.4,
                marker_colors=["#4CAF50","#F44336"]))
            fig.update_layout(height=300, margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)

            df3["已繳"] = df3["已繳"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
            df3["金額"] = df3["金額"].apply(lambda x: f"NT$ {x:,.0f}")
            st.dataframe(df3, use_container_width=True, height=300)
            csv3 = df3.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 匯出 CSV", csv3,
                               file_name=f"繳費統計_{start_date}_{end_date}.csv",
                               mime="text/csv")


def page_admin_accounts():
    # [修改] 密碼強度驗證 + display_name/email 欄位 + 報表收件者管理 tab
    st.markdown('<div class="page-title">🔑 帳號管理</div>', unsafe_allow_html=True)
    st.divider()

    with get_conn() as conn:
        users = pd.read_sql_query("""
            SELECT u.id, u.username AS 帳號,
                   CASE u.role WHEN 'admin' THEN '管理者'
                               WHEN 'coach' THEN '教練'
                               ELSE '學員' END AS 角色,
                   COALESCE(s.name, co.name, u.display_name, '—') AS 姓名,
                   COALESCE(u.email,'') AS Email
            FROM Users u
            LEFT JOIN Students s  ON u.id=s.user_id  AND u.role='student'
            LEFT JOIN Coaches  co ON u.id=co.user_id AND u.role='coach'
            ORDER BY u.role, u.username
        """, conn)

    st.markdown('<div class="section-title">👥 使用者清單</div>', unsafe_allow_html=True)
    st.dataframe(users.drop(columns=["id"]), use_container_width=True, height=260)
    st.divider()

    tab_add, tab_reset, tab_recip = st.tabs(
        ["➕ 新增帳號","🔒 重設密碼","📧 報表收件者管理"])

    with tab_add:
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("帳號")
                new_password = st.text_input("密碼", type="password",
                                             help="最少 6 碼且需包含英文字母")
            with col2:
                new_role = st.selectbox(
                    "角色", ["student","coach","admin"],
                    format_func=lambda x: {"student":"學員","coach":"教練","admin":"管理者"}[x])
                new_name  = st.text_input("姓名（顯示名稱）")
                new_email = st.text_input("Email（選填）")
            submitted = st.form_submit_button("✅ 建立帳號", type="primary")

        if submitted:
            if not new_username or not new_password or not new_name:
                st.error("帳號、密碼與姓名皆為必填。")
            else:
                pw_ok, pw_msg = validate_password(new_password)
                if not pw_ok:
                    st.error(pw_msg)
                else:
                    try:
                        with get_conn() as conn:
                            cur = conn.execute(
                                "INSERT INTO Users"
                                "(username,password,role,email,display_name)"
                                " VALUES(?,?,?,?,?)",
                                (new_username, hash_pw(new_password),
                                 new_role, new_email, new_name))
                            conn.commit()
                            uid = cur.lastrowid
                            if new_role == "student":
                                conn.execute(
                                    "INSERT INTO Students(user_id,name,email) VALUES(?,?,?)",
                                    (uid, new_name, new_email))
                            elif new_role == "coach":
                                conn.execute(
                                    "INSERT INTO Coaches(user_id,name) VALUES(?,?)",
                                    (uid, new_name))
                            conn.commit()
                        st.success(f"✅ 帳號 '{new_username}' 建立成功！")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("帳號已存在，請使用其他帳號名稱。")
                    except Exception as e:
                        st.error(f"建立失敗：{e}")

    with tab_reset:
        user_options = dict(zip(users["帳號"], users["id"]))
        with st.form("reset_pw_form"):
            sel_user = st.selectbox("選擇帳號", list(user_options.keys()))
            new_pw1  = st.text_input("新密碼",   type="password",
                                     help="最少 6 碼且需包含英文字母")
            new_pw2  = st.text_input("確認新密碼", type="password")
            reset_ok = st.form_submit_button("🔒 重設密碼", type="primary")

        if reset_ok:
            if not new_pw1:
                st.error("密碼不可為空。")
            elif new_pw1 != new_pw2:
                st.error("兩次輸入的密碼不一致。")
            else:
                pw_ok, pw_msg = validate_password(new_pw1)
                if not pw_ok:
                    st.error(pw_msg)
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                "UPDATE Users SET password=? WHERE id=?",
                                (hash_pw(new_pw1), user_options[sel_user]))
                            conn.commit()
                        st.success(f"✅ 帳號 '{sel_user}' 的密碼已重設。")
                    except Exception as e:
                        st.error(f"重設失敗：{e}")

    # ── 報表收件者管理（手動寄送參考清單）────────────────────
    with tab_recip:
        st.markdown('<div class="section-title">📧 報表收件者清單</div>',
                    unsafe_allow_html=True)
        st.caption("此清單供管理者手動寄送報表時參考，系統不自動寄送。")

        with get_conn() as conn:
            recip_df = pd.read_sql_query("""
                SELECT id, email AS Email, display_name AS 顯示名稱,
                       CASE is_active WHEN 1 THEN '✅ 啟用' ELSE '⏸️ 停用' END AS 狀態
                FROM ReportRecipients ORDER BY email
            """, conn)

        if not recip_df.empty:
            st.dataframe(recip_df.drop(columns=["id"]),
                         use_container_width=True, height=200)
            tog_opts = {
                f"{r['Email']}（{r['狀態']}）": r["id"]
                for _, r in recip_df.iterrows()
            }
            sel_tog = st.selectbox("切換啟用狀態", list(tog_opts.keys()),
                                   key="recip_toggle")
            if st.button("🔄 切換"):
                rid = tog_opts[sel_tog]
                with get_conn() as conn:
                    cur_state = conn.execute(
                        "SELECT is_active FROM ReportRecipients WHERE id=?",
                        (rid,)).fetchone()["is_active"]
                    conn.execute(
                        "UPDATE ReportRecipients SET is_active=? WHERE id=?",
                        (0 if cur_state else 1, rid))
                    conn.commit()
                st.rerun()

        st.divider()
        with st.form("add_recip_form"):
            nr_email = st.text_input("Email")
            nr_name  = st.text_input("顯示名稱")
            r_sub    = st.form_submit_button("➕ 新增收件者")
        if r_sub:
            if not nr_email:
                st.error("Email 不可為空。")
            else:
                try:
                    with get_conn() as conn:
                        conn.execute(
                            "INSERT INTO ReportRecipients(email,display_name) VALUES(?,?)",
                            (nr_email, nr_name))
                        conn.commit()
                    st.success(f"✅ 已新增收件者 {nr_email}。")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("此 Email 已存在。")
                except Exception as e:
                    st.error(f"新增失敗：{e}")


# ══════════════════════════════════════════════════════════════
# 📅  F-008：近 7 天課程與桌次查詢（全角色）
# ══════════════════════════════════════════════════════════════

def page_weekly_schedule():
    """
    下拉選單：今天起往後 7 天
    甘特圖：每桌一列、時段色塊
      - 管理者：全部課程橘色 #FF6B35
      - 教練：本人課程橘色，其他灰色「已佔用」
      - 學員：本人課程橘色，其他灰色「已佔用」
    下方：課程明細表格（教練/學員僅顯示本人課程列）
    """
    st.markdown('<div class="page-title">📅 近期課程查詢</div>', unsafe_allow_html=True)
    st.divider()

    role      = st.session_state.get("role","")
    pid       = st.session_state.get("profile_id")   # coach_id 或 student_id

    # 日期下拉
    date_options = generate_date_options()
    labels       = [opt[0] for opt in date_options]
    dates_list   = [opt[1] for opt in date_options]
    sel_label    = st.selectbox("選擇查詢日期", labels, index=0)
    sel_date     = dates_list[labels.index(sel_label)]
    sel_weekday  = ["週一","週二","週三","週四","週五","週六","週日"][sel_date.weekday()]

    st.markdown(
        f"<small style='color:#888;'>查詢日期：{sel_date.isoformat()}"
        f"（{sel_weekday}）</small>",
        unsafe_allow_html=True)
    st.divider()

    # 取得當日所有課程
    with get_conn() as conn:
        all_courses = pd.read_sql_query("""
            SELECT c.id, c.course_type, c.schedule_time, c.duration,
                   c.table_id, c.coach_id,
                   co.name AS coach_name,
                   COUNT(e.id) AS enrolled_count
            FROM Courses c
            JOIN Coaches co ON c.coach_id=co.id
            LEFT JOIN Enrollments e ON e.course_id=c.id
            WHERE c.schedule_day=?
            GROUP BY c.id
            ORDER BY c.table_id, c.schedule_time
        """, conn, params=(sel_weekday,))

        # 本人課程 ID 集合
        if role == "coach":
            my_ids = set(pd.read_sql_query(
                "SELECT id FROM Courses WHERE coach_id=?",
                conn, params=(pid,))["id"].tolist())
        elif role == "student":
            my_ids = set(pd.read_sql_query(
                "SELECT course_id FROM Enrollments WHERE student_id=?",
                conn, params=(pid,))["course_id"].tolist())
        else:
            my_ids = None  # admin：全部視為本人

    if all_courses.empty:
        st.info("📭 所選日期無排定課程。")
        return

    # ── 甘特圖 ─────────────────────────────────────────────
    st.markdown('<div class="section-title">🏓 桌次甘特圖</div>', unsafe_allow_html=True)

    fig = go.Figure()
    for _, c in all_courses.iterrows():
        sm         = time_to_minutes(str(c["schedule_time"]))
        em         = sm + int(c["duration"])
        is_mine    = (my_ids is None or c["id"] in my_ids)
        bar_color  = "#FF6B35" if is_mine else "#CCCCCC"
        hover_body = (
            f"<b>桌{c['table_id']}</b><br>"
            f"課程：{c['course_type']}<br>"
            f"教練：{c['coach_name']}<br>"
            f"時段：{c['schedule_time']}～{em//60:02d}:{em%60:02d}<br>"
            f"報名人數：{c['enrolled_count']}<br>"
            if is_mine else
            f"<b>桌{c['table_id']}</b><br>已佔用<br>"
        )
        fig.add_trace(go.Bar(
            x=[int(c["duration"]) / 60],
            y=[f"桌{c['table_id']}"],
            base=[sm / 60],
            orientation="h",
            marker_color=bar_color,
            hovertemplate=hover_body + "<extra></extra>",
            showlegend=False))

    fig.update_layout(
        barmode="overlay", height=360,
        xaxis=dict(
            title="時間", range=[8, 22],
            tickvals=list(range(8, 23)),
            ticktext=[f"{h:02d}:00" for h in range(8, 23)]),
        yaxis=dict(
            title="桌次", categoryorder="array",
            categoryarray=[f"桌{i}" for i in range(8, 0, -1)]),
        margin=dict(l=40,r=20,t=20,b=40),
        plot_bgcolor="#F9F9F9")

    if my_ids is not None:
        st.caption("🟠 本人課程　⬜ 其他已佔用")
    st.plotly_chart(fig, use_container_width=True)

    # ── 課程明細表格 ─────────────────────────────────────────
    st.markdown('<div class="section-title">📋 課程明細</div>', unsafe_allow_html=True)

    if my_ids is not None:
        show_df     = all_courses[all_courses["id"].isin(my_ids)].copy()
        other_count = len(all_courses) - len(show_df)
    else:
        show_df     = all_courses.copy()
        other_count = 0

    if show_df.empty:
        st.info("📭 您在所選日期無排定課程。")
    else:
        def calc_end(r):
            sm = time_to_minutes(str(r["schedule_time"]))
            em = sm + int(r["duration"])
            return f"{em//60:02d}:{em%60:02d}"

        show_df = show_df.copy()
        show_df["結束時間"] = show_df.apply(calc_end, axis=1)
        show_df["桌次"]    = show_df["table_id"].apply(lambda x: f"桌{x}")
        disp = show_df[["桌次","id","course_type","coach_name",
                        "schedule_time","結束時間","duration","enrolled_count"]].copy()
        disp.columns = ["桌次","課程ID","課程類型","教練",
                        "開始時間","結束時間","時長（分鐘）","報名人數"]
        st.dataframe(disp.sort_values("桌次").reset_index(drop=True),
                     use_container_width=True, height=280)

    if other_count > 0:
        st.caption(f"（另有 {other_count} 個其他課程已佔用桌次，詳見甘特圖灰色區塊）")


# ══════════════════════════════════════════════════════════════
# 🚀  主程式
# ══════════════════════════════════════════════════════════════

def main():
    init_db()

    if "user_id" not in st.session_state:
        login_page()
        return

    selected = sidebar()
    role     = st.session_state.get("role","")

    if role == "student":
        page_map = {
            "📚 我的課程":     page_my_courses,
            "🙏 請假申請":     page_leave_request,
            "💳 繳費狀況":     page_payment_status,
            "📋 出勤紀錄":     page_attendance_record,
            "📅 近期課程查詢": page_weekly_schedule,
        }
    elif role == "coach":
        page_map = {
            "👤 個人簡介編輯": page_coach_profile,
            "👥 課程學員名單": page_coach_students,
            "✅ 課堂點名":    page_coach_attendance,
            "🙏 請假審核":    page_coach_leave_review,
            "📅 近期課程查詢": page_weekly_schedule,
        }
    elif role == "admin":
        page_map = {
            "📅 課程管理":     page_admin_courses,
            "📊 出勤總表":     page_admin_attendance,
            "💰 繳費管理":     page_admin_payments,
            "📈 報表查詢":     page_admin_reports,
            "🔑 帳號管理":     page_admin_accounts,
            "📅 近期課程查詢": page_weekly_schedule,
        }
    else:
        st.error("未知角色，請重新登入。")
        return

    if selected in page_map:
        page_map[selected]()
    else:
        list(page_map.values())[0]()


if __name__ == "__main__":
    main()

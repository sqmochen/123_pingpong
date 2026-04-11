# ============================================================
# 🏓 桌球教室管理與互動系統 - app.py  v1.4
# Ping-Pong Academy Manager
# ============================================================

import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime, date, timedelta
import plotly.graph_objects as go
import plotly.express as px

DB_PATH = "./pingpong.db"

st.set_page_config(
    page_title="🏓 桌球教室管理系統",
    page_icon="🏓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { --accent: #FF6B35; --accent-light: #FFF0EB; }
.block-container { padding-top: 1.5rem; }
div[data-testid="metric-container"] {
    background: var(--accent-light);
    border-left: 4px solid var(--accent);
    border-radius: 8px; padding: 12px 16px;
}
.stButton > button { border-radius: 8px; font-weight: 600; }
.page-title { font-size:1.6rem; font-weight:700; color:#1a1a2e; margin-bottom:0.2rem; }
.section-title { font-size:1.1rem; font-weight:600; color:#FF6B35; margin:1rem 0 0.5rem 0; }
.role-badge-admin   { background:#FF6B35; color:white; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
.role-badge-coach   { background:#2196F3; color:white; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
.role-badge-student { background:#4CAF50; color:white; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 🗄️  資料庫工具
# ══════════════════════════════════════════════════════════════

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def validate_password(pw):
    if len(pw) < 6 or not any(c.isalpha() for c in pw):
        return False, "密碼需至少 6 碼且包含英文字母"
    return True, ""

def time_to_minutes(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m

def calc_end_time(start, duration):
    em = time_to_minutes(start) + int(duration)
    return f"{em//60:02d}:{em%60:02d}"

def check_table_conflict(conn, schedule_day, schedule_time, duration, table_id, exclude_id=None):
    new_start = time_to_minutes(schedule_time)
    new_end   = new_start + int(duration)
    rows = conn.execute(
        "SELECT id, schedule_time, duration FROM Courses WHERE schedule_day=? AND table_id=?",
        (schedule_day, table_id)).fetchall()
    conflicts = []
    for row in rows:
        if exclude_id and row["id"] == exclude_id:
            continue
        ex_start = time_to_minutes(row["schedule_time"])
        ex_end   = ex_start + row["duration"]
        if new_start < ex_end and new_end > ex_start:
            conflicts.append(row)
    return conflicts

def make_course_code(schedule_day, table_id, schedule_time, duration):
    day_map = {"週一":"1","週二":"2","週三":"3","週四":"4","週五":"5","週六":"6","週日":"7"}
    hhmm    = schedule_time.replace(":", "")
    return f"{day_map[schedule_day]}-{table_id}-{hhmm}-{str(duration).zfill(3)}"

def get_display_name(conn, user_id, role):
    if role == "student":
        r = conn.execute("SELECT name FROM Students WHERE user_id=?", (user_id,)).fetchone()
    elif role == "coach":
        r = conn.execute("SELECT name FROM Coaches WHERE user_id=?", (user_id,)).fetchone()
    else:
        r = conn.execute("SELECT display_name FROM Users WHERE id=?", (user_id,)).fetchone()
    return r[0] if r and r[0] else "未設定"

def generate_date_options():
    wd = ["一","二","三","四","五","六","日"]
    result = []
    for i in range(7):
        d = date.today() + timedelta(days=i)
        result.append((f"{d.strftime('%Y-%m-%d')}（{wd[d.weekday()]}）", d))
    return result

WEEKDAY_TO_INT = {"週一":0,"週二":1,"週三":2,"週四":3,"週五":4,"週六":5,"週日":6}


# ══════════════════════════════════════════════════════════════
# 🏗️  資料庫初始化
# ══════════════════════════════════════════════════════════════

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            role TEXT NOT NULL, email TEXT DEFAULT '', display_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS Students (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
            name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES Users(id)
        );
        CREATE TABLE IF NOT EXISTS Coaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
            name TEXT NOT NULL, phone TEXT DEFAULT '', bio TEXT DEFAULT '',
            specialty TEXT DEFAULT '', photo_path TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES Users(id)
        );
        CREATE TABLE IF NOT EXISTS Tables (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS Courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT UNIQUE,
            course_type TEXT NOT NULL, coach_id INTEGER NOT NULL,
            schedule_day TEXT NOT NULL, schedule_time TEXT NOT NULL,
            duration INTEGER NOT NULL, table_id INTEGER NOT NULL,
            FOREIGN KEY (coach_id) REFERENCES Coaches(id),
            FOREIGN KEY (table_id) REFERENCES Tables(id)
        );
        CREATE TABLE IF NOT EXISTS Enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            fee REAL NOT NULL DEFAULT 0, enrolled_date TEXT NOT NULL,
            UNIQUE(student_id, course_id),
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        CREATE TABLE IF NOT EXISTS ClassSessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL, session_date TEXT NOT NULL,
            session_time TEXT NOT NULL, coach_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL, created_by TEXT NOT NULL DEFAULT 'system',
            FOREIGN KEY (course_id) REFERENCES Courses(id),
            FOREIGN KEY (coach_id)  REFERENCES Coaches(id),
            FOREIGN KEY (table_id)  REFERENCES Tables(id)
        );
        CREATE TABLE IF NOT EXISTS Attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
            status TEXT NOT NULL, note TEXT DEFAULT '',
            UNIQUE(session_id, student_id),
            FOREIGN KEY (session_id) REFERENCES ClassSessions(id),
            FOREIGN KEY (student_id) REFERENCES Students(id)
        );
        CREATE TABLE IF NOT EXISTS LeaveRequests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            session_id INTEGER, leave_date TEXT NOT NULL,
            reason TEXT DEFAULT '', status TEXT DEFAULT 'pending',
            reviewed_by INTEGER, reviewed_at TEXT,
            reject_reason TEXT DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        CREATE TABLE IF NOT EXISTS Payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            amount REAL NOT NULL, paid_date TEXT, paid_time TEXT,
            is_paid INTEGER DEFAULT 0, period TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        """)

        # 舊版升級
        for sql in [
            "ALTER TABLE Users         ADD COLUMN email        TEXT DEFAULT ''",
            "ALTER TABLE Users         ADD COLUMN display_name TEXT DEFAULT ''",
            "ALTER TABLE Courses       ADD COLUMN course_code  TEXT",
            "ALTER TABLE Enrollments   ADD COLUMN fee          REAL NOT NULL DEFAULT 0",
            "ALTER TABLE ClassSessions ADD COLUMN created_by   TEXT NOT NULL DEFAULT 'system'",
            "ALTER TABLE LeaveRequests ADD COLUMN session_id   INTEGER",
            "ALTER TABLE LeaveRequests ADD COLUMN reviewed_by  INTEGER",
            "ALTER TABLE LeaveRequests ADD COLUMN reviewed_at  TEXT",
            "ALTER TABLE LeaveRequests ADD COLUMN reject_reason TEXT DEFAULT ''",
            "ALTER TABLE Payments      ADD COLUMN paid_time    TEXT",
            "ALTER TABLE Payments      ADD COLUMN created_at   TEXT NOT NULL DEFAULT ''",
        ]:
            try:
                cur.execute(sql)
            except Exception:
                pass

        for i in range(1, 9):
            cur.execute("INSERT OR IGNORE INTO Tables(id,name) VALUES(?,?)", (i, f"桌{i}"))

        for username, pw, role, dname in [
            ("admin",     hash_pw("admin123"), "admin",   "系統管理員"),
            ("coach01",   hash_pw("coach123"), "coach",   ""),
            ("coach02",   hash_pw("coach123"), "coach",   ""),
            ("student01", hash_pw("stu123"),   "student", ""),
            ("student02", hash_pw("stu123"),   "student", ""),
            ("student03", hash_pw("stu123"),   "student", ""),
        ]:
            cur.execute(
                "INSERT OR IGNORE INTO Users(username,password,role,display_name) VALUES(?,?,?,?)",
                (username, pw, role, dname))

        coach_users = cur.execute("SELECT id FROM Users WHERE role='coach' ORDER BY id").fetchall()
        if len(coach_users) >= 2:
            for uid, name, phone, bio, spec in [
                (coach_users[0]["id"], "王教練", "0912-345-678",
                 "國家乙級桌球教練，執教 15 年，專精正手攻球與多球訓練。", "正手攻球、步法訓練"),
                (coach_users[1]["id"], "李教練", "0923-456-789",
                 "前縣市代表隊選手，擅長防守與旋轉球技巧教學。", "防守技術、旋轉球"),
            ]:
                cur.execute(
                    "INSERT OR IGNORE INTO Coaches(user_id,name,phone,bio,specialty) VALUES(?,?,?,?,?)",
                    (uid, name, phone, bio, spec))

        stu_users = cur.execute("SELECT id FROM Users WHERE role='student' ORDER BY id").fetchall()
        if len(stu_users) >= 3:
            for uid, name, phone, email in [
                (stu_users[0]["id"], "陳小明", "0933-111-222", "ming@example.com"),
                (stu_users[1]["id"], "林小華", "0944-222-333", "hua@example.com"),
                (stu_users[2]["id"], "張小英", "0955-333-444", "ying@example.com"),
            ]:
                cur.execute(
                    "INSERT OR IGNORE INTO Students(user_id,name,phone,email) VALUES(?,?,?,?)",
                    (uid, name, phone, email))

        coaches = cur.execute("SELECT id FROM Coaches ORDER BY id").fetchall()
        if coaches:
            for c_type, cidx, day, stime, dur, tbl in [
                ("團體班", 0, "週一", "14:00",  90, 1),
                ("個人班", 0, "週三", "10:00",  60, 2),
                ("團體班", 1, "週二", "16:00",  90, 3),
                ("暑假班", 1, "週五", "09:00", 120, 4),
            ]:
                code = make_course_code(day, tbl, stime, dur)
                if not cur.execute("SELECT id FROM Courses WHERE course_code=?", (code,)).fetchone():
                    cur.execute("""
                        INSERT INTO Courses(course_code,course_type,coach_id,schedule_day,
                            schedule_time,duration,table_id)
                        VALUES(?,?,?,?,?,?,?)
                    """, (code, c_type, coaches[cidx]["id"], day, stime, dur, tbl))

        students = cur.execute("SELECT id FROM Students ORDER BY id").fetchall()
        courses  = cur.execute("SELECT id FROM Courses  ORDER BY id").fetchall()
        today_str = date.today().isoformat()
        now_str   = datetime.now().isoformat()
        period    = date.today().strftime("%Y-%m")
        if students and courses:
            for sid, cid, fee in [
                (students[0]["id"], courses[0]["id"], 2000),
                (students[0]["id"], courses[1]["id"], 1500),
                (students[1]["id"], courses[0]["id"], 2000),
                (students[1]["id"], courses[2]["id"], 2000),
                (students[2]["id"], courses[2]["id"], 2000),
                (students[2]["id"], courses[3]["id"], 3000),
            ]:
                if not cur.execute("SELECT id FROM Enrollments WHERE student_id=? AND course_id=?",
                                   (sid, cid)).fetchone():
                    cur.execute(
                        "INSERT INTO Enrollments(student_id,course_id,fee,enrolled_date) VALUES(?,?,?,?)",
                        (sid, cid, fee, today_str))
                    if not cur.execute(
                            "SELECT id FROM Payments WHERE student_id=? AND course_id=? AND period=?",
                            (sid, cid, period)).fetchone():
                        cur.execute(
                            "INSERT INTO Payments(student_id,course_id,amount,period,created_at) VALUES(?,?,?,?,?)",
                            (sid, cid, fee, period, now_str))
        conn.commit()


# ══════════════════════════════════════════════════════════════
# 🔐  認證
# ══════════════════════════════════════════════════════════════

def login_page():
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="page-title" style="text-align:center;">🏓 桌球教室管理與互動系統</div>',
                    unsafe_allow_html=True)
        st.markdown('<p style="text-align:center;color:#888;">Ping-Pong Academy Manager v1.4</p>',
                    unsafe_allow_html=True)
        st.divider()
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
                st.session_state.update({
                    "user_id": row["id"], "username": row["username"], "role": row["role"]
                })
                with get_conn() as conn:
                    if row["role"] == "student":
                        s = conn.execute("SELECT id,name FROM Students WHERE user_id=?",
                                         (row["id"],)).fetchone()
                        if s:
                            st.session_state["profile_id"]   = s["id"]
                            st.session_state["profile_name"] = s["name"]
                    elif row["role"] == "coach":
                        c = conn.execute("SELECT id,name FROM Coaches WHERE user_id=?",
                                         (row["id"],)).fetchone()
                        if c:
                            st.session_state["profile_id"]   = c["id"]
                            st.session_state["profile_name"] = c["name"]
                    else:
                        st.session_state["profile_id"]   = 0
                        st.session_state["profile_name"] = get_display_name(conn, row["id"], "admin")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新輸入")
        st.markdown("---")
        st.caption("預設帳號：admin/admin123 ｜ coach01/coach123 ｜ student01/stu123")

def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# ══════════════════════════════════════════════════════════════
# 🎛️  側邊欄
# ══════════════════════════════════════════════════════════════

MENUS = {
    "student": ["📚 我的課程","🙏 請假申請","💳 繳費狀況","📋 出勤紀錄","📅 近期課程查詢"],
    "coach":   ["👤 個人簡介編輯","👥 課程學員名單","✅ 課堂點名","🙏 請假審核","📅 近期課程查詢"],
    "admin":   ["📅 課程管理","📊 出勤總表","💰 繳費管理","📈 報表查詢","🔑 帳號管理","📅 近期課程查詢"],
}
ROLE_LABEL = {"student":"學員","coach":"教練","admin":"管理者"}
ROLE_BADGE = {"student":"role-badge-student","coach":"role-badge-coach","admin":"role-badge-admin"}

def sidebar():
    role = st.session_state.get("role","")
    name = st.session_state.get("profile_name","")
    with st.sidebar:
        st.markdown("## 🏓 Ping-Pong Academy")
        st.divider()
        st.markdown(
            f"**{name}**　<span class='{ROLE_BADGE.get(role,'')}'>{ROLE_LABEL.get(role,'')}</span>",
            unsafe_allow_html=True)
        st.markdown(f"<small style='color:#888;'>帳號：{st.session_state.get('username','')}</small>",
                    unsafe_allow_html=True)
        st.divider()
        selected = st.radio("功能選單", MENUS.get(role,[]), label_visibility="collapsed")
        st.divider()
        if st.button("🚪 登出", use_container_width=True):
            logout()
        st.markdown("---\n<small>📢 本系統供桌球教室內部使用。</small>",
                    unsafe_allow_html=True)
    return selected


# ══════════════════════════════════════════════════════════════
# 👤  學員功能
# ══════════════════════════════════════════════════════════════

def page_my_courses():
    st.markdown('<div class="page-title">📚 我的課程</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")
    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT COALESCE(c.course_code,'—') AS 課程ID, c.course_type AS 課程類型,
                   c.schedule_day AS 星期, c.schedule_time AS 上課時間,
                   c.duration AS 時長_分鐘, t.name AS 桌次,
                   co.name AS 教練, e.fee AS 費用_元
            FROM Enrollments e
            JOIN Courses c  ON e.course_id=c.id
            JOIN Coaches co ON c.coach_id=co.id
            JOIN Tables  t  ON c.table_id=t.id
            WHERE e.student_id=? ORDER BY c.schedule_day, c.schedule_time
        """, conn, params=(sid,))
    if df.empty:
        st.info("目前尚未報名任何課程，請聯繫管理者報名。")
        return
    c1,c2,c3 = st.columns(3)
    c1.metric("已報名課程數",   len(df))
    c2.metric("每月費用合計",   f"NT$ {df['費用_元'].sum():,.0f}")
    c3.metric("平均課程時長",   f"{df['時長_分鐘'].mean():.0f} 分鐘")
    st.divider()
    st.dataframe(df, use_container_width=True, height=320)


def page_leave_request():
    st.markdown('<div class="page-title">🙏 請假申請</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")
    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT c.id, c.schedule_day,
                   COALESCE(c.course_code,'—')||' '||c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label
            FROM Enrollments e JOIN Courses c ON e.course_id=c.id WHERE e.student_id=?
        """, conn, params=(sid,))
    if courses.empty:
        st.warning("您尚未報名任何課程，無法申請請假。")
        return
    course_map = dict(zip(courses["label"], courses["id"]))
    day_map    = dict(zip(courses["id"], courses["schedule_day"]))
    st.markdown('<div class="section-title">📝 申請請假</div>', unsafe_allow_html=True)
    with st.form("leave_form"):
        sel    = st.selectbox("選擇課程", list(course_map.keys()))
        ldate  = st.date_input("請假日期", min_value=date.today())
        reason = st.text_area("請假原因（選填）", height=80)
        submit = st.form_submit_button("📨 送出請假申請", type="primary")
    if submit:
        cid = course_map[sel]
        if ldate.weekday() != WEEKDAY_TO_INT.get(day_map[cid], -1):
            wd = ["一","二","三","四","五","六","日"]
            st.warning(f"所選日期（{wd[ldate.weekday()]}）非該課程上課日（{day_map[cid]}），確定已送出。")
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO LeaveRequests(student_id,course_id,leave_date,reason,status,created_at)"
                    " VALUES(?,?,?,?,'pending',?)",
                    (sid, cid, ldate.isoformat(), reason, datetime.now().isoformat()))
                conn.commit()
            st.success("✅ 請假申請已送出，等待教練審核中。")
        except Exception as e:
            st.error(f"申請失敗：{e}")
    st.divider()
    st.markdown('<div class="section-title">📋 歷史請假紀錄</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        hist = pd.read_sql_query("""
            SELECT lr.leave_date AS 請假日期, c.course_type||' '||c.schedule_day AS 課程,
                   lr.reason AS 原因,
                   CASE lr.status WHEN 'pending' THEN '⏳ 審核中'
                     WHEN 'approved' THEN '✅ 已核准' WHEN 'rejected' THEN '❌ 已拒絕' END AS 狀態,
                   COALESCE(lr.reject_reason,'') AS 駁回原因, lr.created_at AS 申請時間
            FROM LeaveRequests lr JOIN Courses c ON lr.course_id=c.id
            WHERE lr.student_id=? ORDER BY lr.leave_date DESC
        """, conn, params=(sid,))
    if hist.empty:
        st.info("尚無請假紀錄。")
    else:
        st.dataframe(hist, use_container_width=True, height=260)
    st.divider()
    st.markdown('<div class="section-title">🔄 待補課紀錄</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        makeup = pd.read_sql_query("""
            SELECT cs.session_date AS 課堂日期, c.course_type||' '||c.schedule_day AS 課程,
                   lr.leave_date AS 請假日期
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses c        ON cs.course_id=c.id
            JOIN LeaveRequests lr ON lr.student_id=a.student_id AND lr.course_id=cs.course_id
                                  AND lr.leave_date=cs.session_date AND lr.status='approved'
            WHERE a.student_id=? AND a.status='leave' ORDER BY cs.session_date DESC
        """, conn, params=(sid,))
    if makeup.empty:
        st.info("目前無待補課紀錄。")
    else:
        st.dataframe(makeup, use_container_width=True, height=200)
        st.caption("補課安排請線下與教練協調。")


def page_payment_status():
    st.markdown('<div class="page-title">💳 繳費狀況</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")
    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT c.course_type||' '||c.schedule_day AS 課程,
                   p.period AS 期別, p.amount AS 金額,
                   p.created_at AS 建立時間,
                   COALESCE(p.paid_date,'—') AS 繳費日期,
                   COALESCE(p.paid_time,'—') AS 繳費時間, p.is_paid
            FROM Payments p JOIN Courses c ON p.course_id=c.id
            WHERE p.student_id=? ORDER BY p.period DESC
        """, conn, params=(sid,))
    if df.empty:
        st.info("目前無繳費紀錄。")
        return
    paid_amt   = df[df["is_paid"]==1]["金額"].sum()
    unpaid_amt = df[df["is_paid"]==0]["金額"].sum()
    rate       = (df["is_paid"]==1).sum() / len(df) * 100 if len(df) > 0 else 0
    c1,c2,c3 = st.columns(3)
    c1.metric("已繳總額",   f"NT$ {paid_amt:,.0f}")
    c2.metric("未繳總額",   f"NT$ {unpaid_amt:,.0f}")
    c3.metric("繳費完成率", f"{rate:.1f}%")
    st.divider()
    df["狀態"] = df["is_paid"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
    df["金額"] = df["金額"].apply(lambda x: f"NT$ {x:,.0f}")
    st.dataframe(df[["課程","期別","金額","建立時間","繳費日期","繳費時間","狀態"]],
                 use_container_width=True, height=350)


def page_attendance_record():
    st.markdown('<div class="page-title">📋 出勤紀錄</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")
    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT cs.session_date AS 日期, c.course_type||' '||c.schedule_day AS 課程,
                   CASE a.status WHEN 'present' THEN '✅ 出席'
                     WHEN 'absent' THEN '❌ 缺席' WHEN 'leave' THEN '🟡 請假' END AS 狀態,
                   a.status AS _status
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses c        ON cs.course_id=c.id
            WHERE a.student_id=? ORDER BY cs.session_date DESC
        """, conn, params=(sid,))
    if df.empty:
        st.info("目前尚無出勤紀錄。")
        return
    present = (df["_status"]=="present").sum()
    absent  = (df["_status"]=="absent").sum()
    leave   = (df["_status"]=="leave").sum()
    total   = len(df)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("出席次數", present)
    c2.metric("缺席次數", absent)
    c3.metric("請假次數", leave)
    c4.metric("出席率",   f"{present/total*100:.1f}%" if total else "0%")
    st.divider()
    st.dataframe(df.drop(columns=["_status"]), use_container_width=True, height=320)
    st.markdown('<div class="section-title">📊 近 3 個月出勤統計</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        chart = pd.read_sql_query("""
            SELECT substr(cs.session_date,1,7) AS 月份, a.status, COUNT(*) AS 次數
            FROM Attendance a JOIN ClassSessions cs ON a.session_id=cs.id
            WHERE a.student_id=? AND cs.session_date >= date('now','-3 months')
            GROUP BY 月份, a.status
        """, conn, params=(sid,))
    if not chart.empty:
        pivot = chart.pivot_table(index="月份", columns="status", values="次數", fill_value=0)
        color_map = {"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
        label_map = {"present":"出席","absent":"缺席","leave":"請假"}
        fig = go.Figure()
        for col in pivot.columns:
            fig.add_trace(go.Bar(name=label_map.get(col,col), x=pivot.index, y=pivot[col],
                                 marker_color=color_map.get(col,"#999")))
        fig.update_layout(barmode="group", height=300,
                          margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 🏫  教練功能
# ══════════════════════════════════════════════════════════════

def page_coach_profile():
    st.markdown('<div class="page-title">👤 個人簡介編輯</div>', unsafe_allow_html=True)
    st.divider()
    uid = st.session_state.get("user_id")
    with get_conn() as conn:
        coach = conn.execute("SELECT * FROM Coaches WHERE user_id=?", (uid,)).fetchone()
    if not coach:
        st.error("找不到教練資料，請聯繫管理者。")
        return
    c1,c2 = st.columns(2)
    c1.info(f"**姓名：** {coach['name']}\n\n**電話：** {coach['phone']}\n\n**專長：** {coach['specialty']}")
    c2.info(f"**個人簡介：**\n\n{coach['bio']}")
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
        with get_conn() as conn:
            conn.execute("UPDATE Coaches SET name=?,phone=?,bio=?,specialty=? WHERE user_id=?",
                         (name, phone, bio, specialty, uid))
            conn.commit()
        st.session_state["profile_name"] = name
        st.success("✅ 個人簡介已更新！")
        st.rerun()


def page_coach_students():
    st.markdown('<div class="page-title">👥 課程學員名單</div>', unsafe_allow_html=True)
    st.divider()
    cid_coach = st.session_state.get("profile_id")
    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT id, COALESCE(course_code,'—')||' '||course_type||' '||schedule_day||' '||schedule_time AS label
            FROM Courses WHERE coach_id=? ORDER BY schedule_day, schedule_time
        """, conn, params=(cid_coach,))
    if courses.empty:
        st.info("您目前沒有負責的課程。")
        return
    course_map = dict(zip(courses["label"], courses["id"]))
    cid = course_map[st.selectbox("選擇課程", list(course_map.keys()))]
    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT s.name AS 學員姓名, s.phone AS 電話, s.email AS Email,
                   e.fee AS 費用_元, e.enrolled_date AS 報名日期
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
    st.markdown('<div class="page-title">✅ 課堂點名</div>', unsafe_allow_html=True)
    st.divider()
    cid_coach = st.session_state.get("profile_id")
    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT c.id, c.schedule_day, c.schedule_time, c.table_id,
                   COALESCE(c.course_code,'—')||' '||c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label
            FROM Courses c WHERE c.coach_id=? ORDER BY c.schedule_day, c.schedule_time
        """, conn, params=(cid_coach,))
    if courses.empty:
        st.info("您目前沒有負責的課程。")
        return
    course_map  = dict(zip(courses["label"], courses["id"]))
    course_info = courses.set_index("id")
    c1,c2 = st.columns(2)
    sel_label    = c1.selectbox("選擇課程", list(course_map.keys()))
    session_date = c2.date_input("上課日期", value=date.today())
    cid = course_map[sel_label]
    row = course_info.loc[cid]
    if session_date.weekday() != WEEKDAY_TO_INT.get(str(row["schedule_day"]), -1):
        wd = ["一","二","三","四","五","六","日"]
        st.warning(f"⚠️ 所選日期（{wd[session_date.weekday()]}）與課程排定上課日（{row['schedule_day']}）不符，請確認。")
    with get_conn() as conn:
        students = pd.read_sql_query("""
            SELECT s.id, s.name FROM Enrollments e JOIN Students s ON e.student_id=s.id
            WHERE e.course_id=? ORDER BY s.name
        """, conn, params=(cid,))
    if students.empty:
        st.warning("此課程尚無學員，無法點名。")
        return
    with get_conn() as conn:
        sess = conn.execute("SELECT id FROM ClassSessions WHERE course_id=? AND session_date=?",
                            (cid, session_date.isoformat())).fetchone()
        if sess is None:
            cur = conn.execute(
                "INSERT INTO ClassSessions(course_id,session_date,session_time,coach_id,table_id,created_by)"
                " VALUES(?,?,?,?,?,'coach_點名')",
                (cid, session_date.isoformat(), str(row["schedule_time"]),
                 cid_coach, int(row["table_id"])))
            conn.commit()
            session_id = cur.lastrowid
        else:
            session_id = sess["id"]
        existing        = conn.execute("SELECT student_id,status FROM Attendance WHERE session_id=?",
                                       (session_id,)).fetchall()
        approved_leaves = set(r["student_id"] for r in conn.execute("""
            SELECT student_id FROM LeaveRequests
            WHERE course_id=? AND leave_date=? AND status='approved'
        """, (cid, session_date.isoformat())).fetchall())
    exist_map   = {r["student_id"]: r["status"] for r in existing}
    status_opts = ["出席","缺席","請假"]
    status_rev  = {"出席":"present","缺席":"absent","請假":"leave"}
    status_fwd  = {"present":"出席","absent":"缺席","leave":"請假"}
    st.markdown(f'<div class="section-title">👥 點名列表（共 {len(students)} 位學員）</div>',
                unsafe_allow_html=True)
    selections = {}
    for _, stu in students.iterrows():
        if stu["id"] in approved_leaves:
            default, suffix = "請假", "　🏷️ 已核准請假"
        else:
            default, suffix = status_fwd.get(exist_map.get(stu["id"], "present"), "出席"), ""
        val = st.radio(f"**{stu['name']}**{suffix}", status_opts,
                       index=status_opts.index(default), horizontal=True,
                       key=f"att_{session_id}_{stu['id']}")
        selections[stu["id"]] = val
    if st.button("📝 送出點名結果", type="primary", use_container_width=True):
        with get_conn() as conn:
            for sid_s, slabel in selections.items():
                conn.execute("""
                    INSERT INTO Attendance(session_id,student_id,status) VALUES(?,?,?)
                    ON CONFLICT(session_id,student_id) DO UPDATE SET status=excluded.status
                """, (session_id, sid_s, status_rev[slabel]))
            conn.commit()
        p = sum(1 for v in selections.values() if v=="出席")
        a = sum(1 for v in selections.values() if v=="缺席")
        st.success(f"✅ 點名完成！出席：{p} 人，缺席：{a} 人")


def page_coach_leave_review():
    st.markdown('<div class="page-title">🙏 請假審核</div>', unsafe_allow_html=True)
    st.divider()
    cid_coach = st.session_state.get("profile_id")
    uid       = st.session_state.get("user_id")
    st.markdown('<div class="section-title">⏳ 待審核申請</div>', unsafe_allow_html=True)
    with get_conn() as conn:
        pending = pd.read_sql_query("""
            SELECT lr.id, s.name AS 學員, c.course_type||' '||c.schedule_day AS 課程,
                   lr.leave_date AS 請假日期, lr.reason AS 原因, lr.created_at AS 申請時間
            FROM LeaveRequests lr JOIN Students s ON lr.student_id=s.id
            JOIN Courses c ON lr.course_id=c.id
            WHERE lr.status='pending' AND c.coach_id=? ORDER BY lr.leave_date
        """, conn, params=(cid_coach,))
    if pending.empty:
        st.info("目前無待審核的請假申請。")
    else:
        for _, row in pending.iterrows():
            with st.expander(f"⏳ {row['學員']} ｜ {row['課程']} ｜ 請假日：{row['請假日期']}"):
                st.write(f"**申請時間：** {row['申請時間']}")
                st.write(f"**原因：** {row['原因'] or '（未填寫）'}")
                col1,col2 = st.columns(2)
                with col1:
                    if st.button("✅ 核准", key=f"approve_{row['id']}", type="primary"):
                        with get_conn() as conn:
                            conn.execute("""
                                UPDATE LeaveRequests SET status='approved',reviewed_by=?,reviewed_at=?
                                WHERE id=?
                            """, (uid, datetime.now().isoformat(), int(row["id"])))
                            conn.commit()
                        st.success("已核准！")
                        st.rerun()
                with col2:
                    rr = st.text_input("駁回原因", key=f"rr_{row['id']}", placeholder="請填寫駁回原因")
                    if st.button("❌ 駁回", key=f"reject_{row['id']}"):
                        if not rr.strip():
                            st.warning("請填寫駁回原因後再送出。")
                        else:
                            with get_conn() as conn:
                                conn.execute("""
                                    UPDATE LeaveRequests
                                    SET status='rejected',reviewed_by=?,reviewed_at=?,reject_reason=?
                                    WHERE id=?
                                """, (uid, datetime.now().isoformat(), rr, int(row["id"])))
                                conn.commit()
                            st.success("已駁回。")
                            st.rerun()
    st.divider()
    st.markdown('<div class="section-title">📋 歷史審核紀錄</div>', unsafe_allow_html=True)
    filter_status = st.selectbox("篩選狀態", ["全部","已核准","已駁回"], key="leave_review_filter")
    fval          = {"全部":None,"已核准":"approved","已駁回":"rejected"}[filter_status]
    q = """
        SELECT s.name AS 學員, c.course_type||' '||c.schedule_day AS 課程,
               lr.leave_date AS 請假日期, lr.reason AS 原因,
               CASE lr.status WHEN 'approved' THEN '✅ 已核准' WHEN 'rejected' THEN '❌ 已駁回' END AS 狀態,
               COALESCE(lr.reject_reason,'') AS 駁回原因, lr.reviewed_at AS 審核時間
        FROM LeaveRequests lr JOIN Students s ON lr.student_id=s.id
        JOIN Courses c ON lr.course_id=c.id
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
# 🔧  管理者功能
# ══════════════════════════════════════════════════════════════

def page_admin_courses():
    st.markdown('<div class="page-title">📅 課程管理</div>', unsafe_allow_html=True)
    st.divider()
    tab_list, tab_add, tab_enroll, tab_visual = st.tabs(
        ["📋 課程總表", "➕ 新增課程", "🎓 學員報名管理", "🏓 桌次視覺化"])

    # ── Tab 1：課程總表 + 多筆批次刪除 ──────────────────────
    with tab_list:
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT c.id AS _id, COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, co.name AS 教練,
                       c.schedule_day AS 星期, c.schedule_time AS 開始時間,
                       c.duration AS 時長_分鐘, t.name AS 桌次,
                       COUNT(e.id) AS 報名人數
                FROM Courses c
                JOIN Coaches co ON c.coach_id=co.id
                JOIN Tables  t  ON c.table_id=t.id
                LEFT JOIN Enrollments e ON e.course_id=c.id
                GROUP BY c.id ORDER BY c.schedule_day, c.schedule_time
            """, conn)
        if df.empty:
            st.info("目前無課程資料。")
        else:
            df["結束時間"] = df.apply(
                lambda r: calc_end_time(str(r["開始時間"]), int(r["時長_分鐘"])), axis=1)
            st.dataframe(
                df[["課程ID","課程類型","教練","星期","開始時間","結束時間","時長_分鐘","桌次","報名人數"]],
                use_container_width=True, height=300)
            st.divider()
            st.markdown('<div class="section-title">🗑️ 批次刪除課程</div>', unsafe_allow_html=True)
            st.caption("勾選欲刪除的課程，確認後系統將一併刪除所有關聯資料（無法還原）。")
            selected_ids = []
            for _, row in df.iterrows():
                label = f"{row['課程ID']} — {row['課程類型']} {row['星期']} {row['開始時間']}"
                if st.checkbox(label, key=f"del_chk_{row['_id']}"):
                    selected_ids.append(int(row["_id"]))

            if selected_ids and st.button("🔍 查看關聯資料並確認刪除", type="primary"):
                st.session_state["pending_delete_ids"] = selected_ids

            if "pending_delete_ids" in st.session_state:
                del_ids = st.session_state["pending_delete_ids"]
                with get_conn() as conn:
                    total_enroll = sum(conn.execute(
                        "SELECT COUNT(*) FROM Enrollments WHERE course_id=?", (c,)).fetchone()[0]
                        for c in del_ids)
                    total_attend = sum(conn.execute("""
                        SELECT COUNT(*) FROM Attendance a
                        JOIN ClassSessions cs ON a.session_id=cs.id WHERE cs.course_id=?
                    """, (c,)).fetchone()[0] for c in del_ids)
                    total_unpaid = sum(conn.execute(
                        "SELECT COUNT(*) FROM Payments WHERE course_id=? AND is_paid=0", (c,)).fetchone()[0]
                        for c in del_ids)
                st.warning(
                    f"⚠️ 已選 **{len(del_ids)}** 筆課程，關聯資料：\n\n"
                    f"- 合計報名人數：{total_enroll} 筆\n"
                    f"- 合計出勤紀錄：{total_attend} 筆\n"
                    f"- 合計未繳費紀錄：{total_unpaid} 筆\n\n"
                    "確認後將一併刪除所有關聯紀錄，此操作**無法還原**。")
                confirm = st.checkbox("確認刪除以上所有勾選課程", key="confirm_batch_del")
                if st.button("🗑️ 執行批次刪除", key="do_batch_del"):
                    if not confirm:
                        st.warning("請先勾選「確認刪除以上所有勾選課程」。")
                    else:
                        with get_conn() as conn:
                            for cid in del_ids:
                                conn.execute("DELETE FROM Enrollments WHERE course_id=?", (cid,))
                                for s in conn.execute(
                                        "SELECT id FROM ClassSessions WHERE course_id=?",
                                        (cid,)).fetchall():
                                    conn.execute("DELETE FROM Attendance WHERE session_id=?", (s["id"],))
                                conn.execute("DELETE FROM ClassSessions WHERE course_id=?", (cid,))
                                conn.execute("DELETE FROM LeaveRequests WHERE course_id=?", (cid,))
                                conn.execute("DELETE FROM Payments WHERE course_id=?", (cid,))
                                conn.execute("DELETE FROM Courses WHERE id=?", (cid,))
                            conn.commit()
                        del st.session_state["pending_delete_ids"]
                        st.success(f"✅ 已成功刪除 {len(del_ids)} 筆課程。")
                        st.rerun()

    # ── Tab 2：新增課程（無費用欄位，含課程代號預覽）────────
    with tab_add:
        with get_conn() as conn:
            coaches = pd.read_sql_query("SELECT id,name FROM Coaches ORDER BY name", conn)
        if coaches.empty:
            st.warning("尚無教練資料，請先新增教練帳號。")
        else:
            coach_map = dict(zip(coaches["name"], coaches["id"]))
            with st.form("add_course_form"):
                c1,c2 = st.columns(2)
                with c1:
                    c_type    = st.selectbox("課程類型", ["團體班","個人班","寒假班","暑假班"])
                    coach_sel = st.selectbox("選擇教練", list(coach_map.keys()))
                    day       = st.selectbox("上課星期", ["週一","週二","週三","週四","週五","週六","週日"])
                    time_val  = st.time_input("上課時間",
                                              value=datetime.strptime("09:00","%H:%M").time())
                with c2:
                    duration = st.selectbox("課程時長（分鐘）", [60, 90, 120])
                    table_no = st.selectbox("使用桌次", list(range(1,9)))
                    time_str = time_val.strftime("%H:%M")
                    st.markdown("**課程ID 預覽**")
                    st.code(make_course_code(day, table_no, time_str, duration))
                submitted = st.form_submit_button("✅ 新增課程", type="primary")
            if submitted:
                course_code = make_course_code(day, table_no, time_str, duration)
                with get_conn() as conn:
                    if conn.execute("SELECT id FROM Courses WHERE course_code=?",
                                    (course_code,)).fetchone():
                        st.error(f"⚠️ 課程代號 `{course_code}` 已存在，請確認是否重複。")
                    else:
                        conflicts = check_table_conflict(conn, day, time_str, duration, table_no)
                        if conflicts:
                            for c in conflicts:
                                st.error(
                                    f"⚠️ 桌次 {table_no} 時段衝突"
                                    f"（{c['schedule_time']}～{calc_end_time(c['schedule_time'], c['duration'])}），"
                                    "請重新選擇。")
                        else:
                            try:
                                conn.execute("""
                                    INSERT INTO Courses(course_code,course_type,coach_id,
                                        schedule_day,schedule_time,duration,table_id)
                                    VALUES(?,?,?,?,?,?,?)
                                """, (course_code, c_type, coach_map[coach_sel],
                                      day, time_str, duration, table_no))
                                conn.commit()
                                st.success(f"✅ 課程新增成功！課程ID：`{course_code}`")
                                st.rerun()
                            except Exception as e:
                                st.error(f"新增失敗：{e}")

    # ── Tab 3：學員報名管理（選單格式 + 費用欄位）───────────
    with tab_enroll:
        with get_conn() as conn:
            all_courses = pd.read_sql_query("""
                SELECT c.id, c.schedule_day, c.schedule_time, c.duration,
                       COALESCE(c.course_code,'—') AS code, co.name AS coach_name
                FROM Courses c JOIN Coaches co ON c.coach_id=co.id
                ORDER BY c.schedule_day, c.schedule_time
            """, conn)
            all_students = pd.read_sql_query("SELECT id,name FROM Students ORDER BY name", conn)
        if all_courses.empty or all_students.empty:
            st.info("請先建立課程與學員資料。")
        else:
            def course_label(row):
                end = calc_end_time(str(row["schedule_time"]), int(row["duration"]))
                return f"{row['code']}_{row['coach_name']}_{row['schedule_day']} {row['schedule_time']}～{end}"
            all_courses["label"] = all_courses.apply(course_label, axis=1)
            cmap = dict(zip(all_courses["label"], all_courses["id"]))
            smap = dict(zip(all_students["name"], all_students["id"]))
            sel_course = st.selectbox("選擇課程", list(cmap.keys()), key="enroll_course")
            cid_enroll = cmap[sel_course]
            with get_conn() as conn:
                enrolled = pd.read_sql_query("""
                    SELECT s.id, s.name, e.fee AS 費用_元
                    FROM Enrollments e JOIN Students s ON e.student_id=s.id
                    WHERE e.course_id=? ORDER BY s.name
                """, conn, params=(cid_enroll,))
                enrolled_ids = enrolled["id"].tolist()
            not_yet = [s for s in all_students["name"] if smap[s] not in enrolled_ids]
            c1,c2 = st.columns(2)
            with c1:
                st.markdown(f"**已報名學員（{len(enrolled)} 人）**")
                if enrolled.empty:
                    st.info("此課程尚無學員報名。")
                else:
                    for _, erow in enrolled.iterrows():
                        rc1,rc2,rc3 = st.columns([3,2,1])
                        rc1.write(erow["name"])
                        rc2.write(f"NT$ {erow['費用_元']:,.0f}")
                        if rc3.button("移除", key=f"rm_{erow['id']}_{cid_enroll}"):
                            with get_conn() as conn:
                                conn.execute("DELETE FROM Enrollments WHERE student_id=? AND course_id=?",
                                             (erow["id"], cid_enroll))
                                conn.execute("""
                                    UPDATE LeaveRequests SET status='rejected',reject_reason='已退課'
                                    WHERE student_id=? AND course_id=? AND status='pending'
                                """, (erow["id"], cid_enroll))
                                conn.commit()
                            st.rerun()
            with c2:
                st.markdown("**新增學員報名**")
                if not_yet:
                    add_stu = st.selectbox("選擇學員", not_yet, key="add_stu")
                    add_fee = st.number_input("費用（元）", min_value=0, value=2000, step=100,
                                              key="add_fee")
                    if st.button("➕ 加入報名", type="primary"):
                        try:
                            now_str = datetime.now().isoformat()
                            period  = date.today().strftime("%Y-%m")
                            with get_conn() as conn:
                                conn.execute("""
                                    INSERT INTO Enrollments(student_id,course_id,fee,enrolled_date)
                                    VALUES(?,?,?,?)
                                """, (smap[add_stu], cid_enroll, add_fee, date.today().isoformat()))
                                conn.execute("""
                                    INSERT INTO Payments(student_id,course_id,amount,period,created_at)
                                    VALUES(?,?,?,?,?)
                                """, (smap[add_stu], cid_enroll, add_fee, period, now_str))
                                conn.commit()
                            st.success(f"✅ {add_stu} 已加入課程，費用 NT$ {add_fee:,}！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"報名失敗：{e}")
                else:
                    st.info("所有學員皆已報名此課程。")

    # ── Tab 4：桌次甘特圖（色塊標註課程類別與教練）──────────
    with tab_visual:
        st.markdown('<div class="section-title">🏓 選定星期的桌次甘特圖</div>', unsafe_allow_html=True)
        sel_day = st.selectbox("選擇星期",
                               ["週一","週二","週三","週四","週五","週六","週日"],
                               key="table_visual_day")
        with get_conn() as conn:
            day_courses = pd.read_sql_query("""
                SELECT c.id, c.table_id, c.schedule_time, c.duration,
                       c.course_type, co.name AS coach_name,
                       COALESCE(c.course_code,'—') AS course_code,
                       COUNT(e.id) AS enrolled_count
                FROM Courses c JOIN Coaches co ON c.coach_id=co.id
                LEFT JOIN Enrollments e ON e.course_id=c.id
                WHERE c.schedule_day=? GROUP BY c.id
            """, conn, params=(sel_day,))
        fig = go.Figure()
        for _, tc in day_courses.iterrows():
            sm    = time_to_minutes(str(tc["schedule_time"]))
            em    = sm + int(tc["duration"])
            dur_h = int(tc["duration"]) / 60
            bar_text = (f"{tc['course_type']}<br>{tc['coach_name']}"
                        if int(tc["duration"]) >= 90 else tc["coach_name"])
            fig.add_trace(go.Bar(
                x=[dur_h], y=[f"桌{tc['table_id']}"], base=[sm / 60],
                orientation="h", marker_color="#FF6B35",
                text=bar_text, textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color="white", size=11),
                hovertemplate=(
                    f"<b>桌{tc['table_id']}</b><br>"
                    f"課程ID：{tc['course_code']}<br>"
                    f"課程類型：{tc['course_type']}<br>"
                    f"教練：{tc['coach_name']}<br>"
                    f"時段：{tc['schedule_time']}～{em//60:02d}:{em%60:02d}<br>"
                    f"報名人數：{tc['enrolled_count']}<br><extra></extra>"),
                showlegend=False))
        fig.update_layout(
            barmode="overlay", height=400,
            xaxis=dict(title="時間", range=[8,22],
                       tickvals=list(range(8,23)),
                       ticktext=[f"{h:02d}:00" for h in range(8,23)]),
            yaxis=dict(title="桌次", categoryorder="array",
                       categoryarray=[f"桌{i}" for i in range(8,0,-1)]),
            margin=dict(l=40,r=20,t=20,b=40), plot_bgcolor="#F5F5F5")
        if day_courses.empty:
            st.info("此星期無排定課程。")
        else:
            st.plotly_chart(fig, use_container_width=True)


def page_admin_attendance():
    st.markdown('<div class="page-title">📊 出勤總表</div>', unsafe_allow_html=True)
    st.divider()
    c1,c2 = st.columns(2)
    start_date = c1.date_input("起始日期", value=date.today()-timedelta(days=30))
    end_date   = c2.date_input("結束日期",  value=date.today())
    if start_date > end_date:
        st.error("起始日期不可晚於結束日期。")
        return
    with st.spinner("資料載入中..."):
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT cs.session_date AS 日期, c.course_type||' '||c.schedule_day AS 課程,
                       co.name AS 教練, s.name AS 學員,
                       CASE a.status WHEN 'present' THEN '✅ 出席'
                         WHEN 'absent' THEN '❌ 缺席' WHEN 'leave' THEN '🟡 請假' END AS 狀態,
                       a.status AS _status
                FROM Attendance a
                JOIN ClassSessions cs ON a.session_id=cs.id
                JOIN Courses  c       ON cs.course_id=c.id
                JOIN Coaches  co      ON cs.coach_id=co.id
                JOIN Students s       ON a.student_id=s.id
                WHERE cs.session_date BETWEEN ? AND ? ORDER BY cs.session_date DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))
    if df.empty:
        st.info("此區間無出勤紀錄。")
        return
    total   = len(df)
    present = (df["_status"]=="present").sum()
    absent  = (df["_status"]=="absent").sum()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("總紀錄筆數", total)
    c2.metric("出席人次",   present)
    c3.metric("缺席人次",   absent)
    c4.metric("整體出席率", f"{present/total*100:.1f}%" if total else "0%")
    st.divider()
    display = df.drop(columns=["_status"])
    st.dataframe(display, use_container_width=True, height=380)
    st.download_button("⬇️ 匯出 CSV", data=display.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"出勤總表_{start_date}_{end_date}.csv", mime="text/csv")
    st.divider()
    st.markdown('<div class="section-title">📊 每日出勤統計</div>', unsafe_allow_html=True)
    daily = df.groupby(["日期","_status"]).size().reset_index(name="count")
    pivot = daily.pivot_table(index="日期", columns="_status", values="count", fill_value=0)
    color_map = {"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
    label_map = {"present":"出席","absent":"缺席","leave":"請假"}
    fig = go.Figure()
    for col in pivot.columns:
        fig.add_trace(go.Bar(name=label_map.get(col,col), x=pivot.index, y=pivot[col],
                             marker_color=color_map.get(col,"#999")))
    fig.update_layout(barmode="stack", height=320,
                      margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)


def page_admin_payments():
    st.markdown('<div class="page-title">💰 繳費管理</div>', unsafe_allow_html=True)
    st.divider()
    filter_opt = st.radio("篩選", ["全部","未繳費","已繳費"], horizontal=True)
    fval       = {"全部":None,"未繳費":0,"已繳費":1}[filter_opt]
    q = """
        SELECT p.id, s.name AS 學員, c.course_type AS 課程類別,
               co.name AS 教練, c.schedule_day||' '||c.schedule_time AS 上課時間,
               p.amount AS 繳交費用, p.period AS 期別,
               COALESCE(p.paid_date,'—') AS 繳費日期,
               COALESCE(p.paid_time,'—') AS 繳費時間, p.is_paid
        FROM Payments p
        JOIN Students s ON p.student_id=s.id
        JOIN Courses  c ON p.course_id=c.id
        JOIN Coaches  co ON c.coach_id=co.id
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
        return
    total_amt  = df["繳交費用"].sum()
    paid_amt   = df[df["is_paid"]==1]["繳交費用"].sum()
    unpaid_amt = df[df["is_paid"]==0]["繳交費用"].sum()
    c1,c2,c3 = st.columns(3)
    c1.metric("總應收金額", f"NT$ {total_amt:,.0f}")
    c2.metric("已收金額",   f"NT$ {paid_amt:,.0f}")
    c3.metric("未收金額",   f"NT$ {unpaid_amt:,.0f}")
    st.divider()
    # 表格顯示
    display = df.copy()
    display["狀態"]   = display["is_paid"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
    display["繳交費用"] = display["繳交費用"].apply(lambda x: f"NT$ {x:,.0f}")
    st.dataframe(display.drop(columns=["id","is_paid"]),
                 use_container_width=True, height=360)
    # 未繳費逐筆標記
    unpaid_df = df[df["is_paid"]==0]
    if not unpaid_df.empty:
        st.divider()
        st.markdown('<div class="section-title">💳 標記繳費</div>', unsafe_allow_html=True)
        for _, row in unpaid_df.iterrows():
            with st.expander(
                    f"❌ {row['學員']} ｜ {row['課程類別']} {row['上課時間']} ｜ "
                    f"{row['期別']} ｜ NT$ {row['繳交費用']:,.0f}"):
                mc1,mc2 = st.columns(2)
                pay_date = mc1.date_input("繳費日期", value=date.today(),
                                          key=f"pdate_{row['id']}")
                pay_time = mc2.time_input("繳費時間", value=datetime.now().time(),
                                          key=f"ptime_{row['id']}")
                if st.button("💳 標記為已繳費", key=f"pay_{row['id']}", type="primary"):
                    with get_conn() as conn:
                        conn.execute("UPDATE Payments SET is_paid=1,paid_date=?,paid_time=? WHERE id=?",
                                     (pay_date.isoformat(), pay_time.strftime("%H:%M"), int(row["id"])))
                        conn.commit()
                    st.success("✅ 繳費狀態已更新！")
                    st.rerun()


def page_admin_reports():
    st.markdown('<div class="page-title">📈 報表查詢</div>', unsafe_allow_html=True)
    st.divider()
    c1,c2 = st.columns(2)
    start_date = c1.date_input("起始日期", value=date.today().replace(day=1))
    end_date   = c2.date_input("結束日期",  value=date.today())
    if start_date > end_date:
        st.error("起始日期不可晚於結束日期。")
        return
    tab1,tab2,tab3 = st.tabs(["📅 課程報表","👥 出勤統計報表","💰 繳費統計報表"])

    with tab1:
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT cs.session_date AS 日期, c.course_type AS 課程類型,
                       co.name AS 教練, t.name AS 桌次, c.schedule_time AS 時間,
                       c.duration AS 時長_分,
                       COUNT(CASE WHEN a.status='present' THEN 1 END) AS 出席學員數
                FROM ClassSessions cs
                JOIN Courses  c  ON cs.course_id=c.id
                JOIN Coaches  co ON cs.coach_id=co.id
                JOIN Tables   t  ON cs.table_id=t.id
                LEFT JOIN Attendance a ON a.session_id=cs.id
                WHERE cs.session_date BETWEEN ? AND ?
                GROUP BY cs.id ORDER BY cs.session_date DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))
        if df.empty:
            st.info("此區間無上課紀錄。")
        else:
            c1,c2 = st.columns(2)
            c1.metric("上課總堂數", len(df))
            c2.metric("平均出席人數", f"{df['出席學員數'].mean():.1f}")
            st.dataframe(df, use_container_width=True, height=350)
            st.download_button("⬇️ 匯出 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"課程報表_{start_date}_{end_date}.csv", mime="text/csv")

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
            fig = px.bar(df2, x="學員", y="出席", color_discrete_sequence=["#4CAF50"],
                         title="學員出席次數排名")
            fig.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig, use_container_width=True)
            st.download_button("⬇️ 匯出 CSV", df2.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"出勤統計_{start_date}_{end_date}.csv", mime="text/csv")

    with tab3:
        ps = start_date.strftime("%Y-%m")
        pe = end_date.strftime("%Y-%m")
        with get_conn() as conn:
            df3 = pd.read_sql_query("""
                SELECT p.period AS 期別, s.name AS 學員, c.course_type AS 課程類型,
                       p.amount AS 金額, p.is_paid AS 已繳,
                       COALESCE(p.paid_date,'—') AS 繳費日期
                FROM Payments p JOIN Students s ON p.student_id=s.id
                JOIN Courses c ON p.course_id=c.id
                WHERE p.period BETWEEN ? AND ? ORDER BY p.period, s.name
            """, conn, params=(ps, pe))
        if df3.empty:
            st.info("此區間無繳費資料。")
        else:
            total_f  = df3["金額"].sum()
            paid_f   = df3[df3["已繳"]==1]["金額"].sum()
            unpaid_f = df3[df3["已繳"]==0]["金額"].sum()
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("總應收", f"NT$ {total_f:,.0f}")
            c2.metric("已收",   f"NT$ {paid_f:,.0f}")
            c3.metric("未收",   f"NT$ {unpaid_f:,.0f}")
            c4.metric("繳費率", f"{paid_f/total_f*100:.1f}%" if total_f else "0%")
            fig = go.Figure(go.Pie(labels=["已繳費","未繳費"], values=[paid_f,unpaid_f],
                                   hole=0.4, marker_colors=["#4CAF50","#F44336"]))
            fig.update_layout(height=300, margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)
            df3["已繳"] = df3["已繳"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
            df3["金額"] = df3["金額"].apply(lambda x: f"NT$ {x:,.0f}")
            st.dataframe(df3, use_container_width=True, height=300)
            st.download_button("⬇️ 匯出 CSV", df3.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"繳費統計_{start_date}_{end_date}.csv", mime="text/csv")


def page_admin_accounts():
    st.markdown('<div class="page-title">🔑 帳號管理</div>', unsafe_allow_html=True)
    st.divider()
    with get_conn() as conn:
        users = pd.read_sql_query("""
            SELECT u.id, u.username AS 帳號,
                   CASE u.role WHEN 'admin' THEN '管理者' WHEN 'coach' THEN '教練' ELSE '學員' END AS 角色,
                   COALESCE(s.name, co.name, u.display_name, '—') AS 姓名,
                   COALESCE(u.email,'') AS Email, u.role
            FROM Users u
            LEFT JOIN Students s  ON u.id=s.user_id AND u.role='student'
            LEFT JOIN Coaches  co ON u.id=co.user_id AND u.role='coach'
            ORDER BY u.role, u.username
        """, conn)
    tab_mgr, tab_reset = st.tabs(["👤 帳號管理（新增 / 移除）","🔒 重設密碼"])

    # ── Tab 1：新增 + 移除帳號 ───────────────────────────────
    with tab_mgr:
        st.markdown('<div class="section-title">👥 使用者清單</div>', unsafe_allow_html=True)
        st.dataframe(users[["帳號","角色","姓名","Email"]], use_container_width=True, height=260)
        st.divider()

        # 新增
        st.markdown('<div class="section-title">➕ 新增帳號</div>', unsafe_allow_html=True)
        with st.form("add_user_form"):
            c1,c2 = st.columns(2)
            with c1:
                new_username = st.text_input("帳號")
                new_password = st.text_input("密碼", type="password",
                                             help="最少 6 碼且需包含英文字母")
            with c2:
                new_role  = st.selectbox("角色", ["student","coach","admin"],
                                         format_func=lambda x: {"student":"學員","coach":"教練","admin":"管理者"}[x])
                new_name  = st.text_input("姓名（顯示名稱）")
                new_email = st.text_input("Email（選填）")
            add_sub = st.form_submit_button("✅ 建立帳號", type="primary")
        if add_sub:
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
                                "INSERT INTO Users(username,password,role,email,display_name) VALUES(?,?,?,?,?)",
                                (new_username, hash_pw(new_password), new_role, new_email, new_name))
                            conn.commit()
                            uid = cur.lastrowid
                            if new_role == "student":
                                conn.execute("INSERT INTO Students(user_id,name,email) VALUES(?,?,?)",
                                             (uid, new_name, new_email))
                            elif new_role == "coach":
                                conn.execute("INSERT INTO Coaches(user_id,name) VALUES(?,?)",
                                             (uid, new_name))
                            conn.commit()
                        st.success(f"✅ 帳號 '{new_username}' 建立成功！")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("帳號已存在，請使用其他帳號名稱。")
                    except Exception as e:
                        st.error(f"建立失敗：{e}")

        st.divider()
        # 移除
        st.markdown('<div class="section-title">🗑️ 移除帳號</div>', unsafe_allow_html=True)
        current_uid = st.session_state.get("user_id")
        admin_count = (users["role"] == "admin").sum()
        removable   = users[users["id"] != current_uid].copy()

        if removable.empty:
            st.info("目前無可移除的帳號。")
        else:
            remove_options = {
                f"{r['帳號']}（{r['角色']} / {r['姓名']}）": r["id"]
                for _, r in removable.iterrows()
            }
            sel_remove = st.selectbox("選擇要移除的帳號", list(remove_options.keys()),
                                      key="remove_user_sel")
            remove_uid = remove_options[sel_remove]
            remove_row = users[users["id"] == remove_uid].iloc[0]

            # 關聯資料提示
            with get_conn() as conn:
                if remove_row["role"] == "student":
                    sid_r = conn.execute("SELECT id FROM Students WHERE user_id=?",
                                         (remove_uid,)).fetchone()
                    if sid_r:
                        enroll_cnt = conn.execute("SELECT COUNT(*) FROM Enrollments WHERE student_id=?",
                                                  (sid_r["id"],)).fetchone()[0]
                        attend_cnt = conn.execute("SELECT COUNT(*) FROM Attendance WHERE student_id=?",
                                                  (sid_r["id"],)).fetchone()[0]
                        unpaid_cnt = conn.execute(
                            "SELECT COUNT(*) FROM Payments WHERE student_id=? AND is_paid=0",
                            (sid_r["id"],)).fetchone()[0]
                        st.info(
                            f"此學員關聯資料：報名課程 {enroll_cnt} 筆、"
                            f"出勤紀錄 {attend_cnt} 筆、未繳費 {unpaid_cnt} 筆。\n\n"
                            "⚠️ 刪除後對應資料需另行處理（報名/出勤/繳費不會自動刪除）。")
                elif remove_row["role"] == "coach":
                    cid_r = conn.execute("SELECT id FROM Coaches WHERE user_id=?",
                                          (remove_uid,)).fetchone()
                    if cid_r:
                        course_cnt = conn.execute("SELECT COUNT(*) FROM Courses WHERE coach_id=?",
                                                  (cid_r["id"],)).fetchone()[0]
                        if course_cnt > 0:
                            st.warning(
                                f"⚠️ 此教練仍負責 **{course_cnt}** 筆課程，"
                                "建議先至「課程管理」移除相關課程後再刪除帳號。")
                        else:
                            st.info("此教練目前無負責課程，可安全刪除。")
                elif remove_row["role"] == "admin":
                    if admin_count <= 1:
                        st.error("⛔ 系統至少需保留一個管理者帳號，無法刪除此帳號。")
                        st.stop()
                    else:
                        st.info("注意：刪除後請確認仍有其他管理者可登入。")

            confirm_remove = st.checkbox("確認刪除此帳號", key="confirm_user_del")
            if st.button("🗑️ 執行移除帳號", key="do_remove_user"):
                if not confirm_remove:
                    st.warning("請先勾選「確認刪除此帳號」。")
                else:
                    try:
                        with get_conn() as conn:
                            if remove_row["role"] == "student":
                                conn.execute("DELETE FROM Students WHERE user_id=?", (remove_uid,))
                            elif remove_row["role"] == "coach":
                                conn.execute("DELETE FROM Coaches WHERE user_id=?", (remove_uid,))
                            conn.execute("DELETE FROM Users WHERE id=?", (remove_uid,))
                            conn.commit()
                        st.success(f"✅ 帳號 '{remove_row['帳號']}' 已移除。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"移除失敗：{e}")

    # ── Tab 2：重設密碼 ──────────────────────────────────────
    with tab_reset:
        user_options = dict(zip(users["帳號"], users["id"]))
        with st.form("reset_pw_form"):
            sel_user = st.selectbox("選擇帳號", list(user_options.keys()))
            new_pw1  = st.text_input("新密碼",    type="password",
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
                    with get_conn() as conn:
                        conn.execute("UPDATE Users SET password=? WHERE id=?",
                                     (hash_pw(new_pw1), user_options[sel_user]))
                        conn.commit()
                    st.success(f"✅ 帳號 '{sel_user}' 的密碼已重設。")


# ══════════════════════════════════════════════════════════════
# 📅  F-008：近 7 天課程查詢（全角色）
# ══════════════════════════════════════════════════════════════

def page_weekly_schedule():
    st.markdown('<div class="page-title">📅 近期課程查詢</div>', unsafe_allow_html=True)
    st.divider()
    role = st.session_state.get("role","")
    pid  = st.session_state.get("profile_id")

    date_options = generate_date_options()
    labels       = [opt[0] for opt in date_options]
    dates_list   = [opt[1] for opt in date_options]
    sel_label    = st.selectbox("選擇查詢日期", labels, index=0)
    sel_date     = dates_list[labels.index(sel_label)]
    sel_weekday  = ["週一","週二","週三","週四","週五","週六","週日"][sel_date.weekday()]

    st.markdown(f"<small style='color:#888;'>查詢日期：{sel_date.isoformat()}（{sel_weekday}）</small>",
                unsafe_allow_html=True)
    st.divider()

    with get_conn() as conn:
        all_courses = pd.read_sql_query("""
            SELECT c.id, c.course_type, c.schedule_time, c.duration, c.table_id,
                   COALESCE(c.course_code,'—') AS course_code,
                   co.name AS coach_name, COUNT(e.id) AS enrolled_count
            FROM Courses c JOIN Coaches co ON c.coach_id=co.id
            LEFT JOIN Enrollments e ON e.course_id=c.id
            WHERE c.schedule_day=?
            GROUP BY c.id ORDER BY c.table_id, c.schedule_time
        """, conn, params=(sel_weekday,))
        if role == "coach":
            my_ids = set(pd.read_sql_query(
                "SELECT id FROM Courses WHERE coach_id=?", conn, params=(pid,))["id"].tolist())
        elif role == "student":
            my_ids = set(pd.read_sql_query(
                "SELECT course_id FROM Enrollments WHERE student_id=?",
                conn, params=(pid,))["course_id"].tolist())
        else:
            my_ids = None

    if all_courses.empty:
        st.info("📭 所選日期無排定課程。")
        return

    st.markdown('<div class="section-title">🏓 桌次甘特圖</div>', unsafe_allow_html=True)
    fig = go.Figure()
    for _, c in all_courses.iterrows():
        sm        = time_to_minutes(str(c["schedule_time"]))
        em        = sm + int(c["duration"])
        dur_h     = int(c["duration"]) / 60
        is_mine   = (my_ids is None or c["id"] in my_ids)
        bar_color = "#FF6B35" if is_mine else "#CCCCCC"
        hover_body = (
            f"<b>桌{c['table_id']}</b><br>課程ID：{c['course_code']}<br>"
            f"課程類型：{c['course_type']}<br>教練：{c['coach_name']}<br>"
            f"時段：{c['schedule_time']}～{em//60:02d}:{em%60:02d}<br>"
            f"報名人數：{c['enrolled_count']}<br>"
            if is_mine else
            f"<b>桌{c['table_id']}</b><br>已佔用<br>"
        )
        fig.add_trace(go.Bar(
            x=[dur_h], y=[f"桌{c['table_id']}"], base=[sm / 60],
            orientation="h", marker_color=bar_color,
            hovertemplate=hover_body + "<extra></extra>",
            showlegend=False))
    fig.update_layout(
        barmode="overlay", height=360,
        xaxis=dict(title="時間", range=[8,22],
                   tickvals=list(range(8,23)),
                   ticktext=[f"{h:02d}:00" for h in range(8,23)]),
        yaxis=dict(title="桌次", categoryorder="array",
                   categoryarray=[f"桌{i}" for i in range(8,0,-1)]),
        margin=dict(l=40,r=20,t=20,b=40), plot_bgcolor="#F9F9F9")
    if my_ids is not None:
        st.caption("🟠 本人課程　⬜ 其他已佔用課程")
    st.plotly_chart(fig, use_container_width=True)

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
        show_df = show_df.copy()
        show_df["結束時間"] = show_df.apply(
            lambda r: calc_end_time(str(r["schedule_time"]), int(r["duration"])), axis=1)
        show_df["桌次"]    = show_df["table_id"].apply(lambda x: f"桌{x}")
        disp = show_df[["桌次","course_code","course_type","coach_name",
                         "schedule_time","結束時間","duration","enrolled_count"]].copy()
        disp.columns = ["桌次","課程ID","課程類型","教練","開始時間","結束時間","時長（分鐘）","報名人數"]
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

# ============================================================
# 🏓 桌球教室管理與互動系統 - app.py
# Ping-Pong Academy Manager
# ============================================================

import streamlit as st
import sqlite3
import hashlib
import os
import io
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import plotly.graph_objects as go
import plotly.express as px

# ── ReportLab PDF ──────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ── 全域設定 ────────────────────────────────────────────────
DB_PATH    = "./pingpong.db"
RECEIPT_DIR = "./receipts"
os.makedirs(RECEIPT_DIR, exist_ok=True)

# 嘗試登錄中文字型（使用 CID 字型作為最穩定備援）
try:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    PDF_FONT      = 'STSong-Light'
    PDF_FONT_BOLD = 'STSong-Light'
except Exception:
    PDF_FONT      = 'Helvetica'
    PDF_FONT_BOLD = 'Helvetica-Bold'

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


def init_db():
    """初始化資料庫：建表 + 插入預設帳號與基礎資料"""
    with get_conn() as conn:
        cur = conn.cursor()

        # ── 建立資料表 ─────────────────────────────────────
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS Users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role     TEXT NOT NULL
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
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id  INTEGER NOT NULL,
            leave_date TEXT NOT NULL,
            reason     TEXT DEFAULT '',
            status     TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        CREATE TABLE IF NOT EXISTS Payments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            course_id  INTEGER NOT NULL,
            amount     REAL NOT NULL,
            paid_date  TEXT,
            is_paid    INTEGER DEFAULT 0,
            period     TEXT NOT NULL,
            pdf_path   TEXT DEFAULT '',
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (course_id)  REFERENCES Courses(id)
        );
        """)

        # ── 桌次 1~8 ───────────────────────────────────────
        for i in range(1, 9):
            cur.execute("INSERT OR IGNORE INTO Tables(id,name) VALUES(?,?)", (i, f"桌{i}"))

        # ── 預設帳號 ────────────────────────────────────────
        accounts = [
            ("admin",      hash_pw("admin123"),  "admin"),
            ("coach01",    hash_pw("coach123"),   "coach"),
            ("coach02",    hash_pw("coach123"),   "coach"),
            ("student01",  hash_pw("stu123"),     "student"),
            ("student02",  hash_pw("stu123"),     "student"),
            ("student03",  hash_pw("stu123"),     "student"),
        ]
        for username, pw, role in accounts:
            cur.execute("INSERT OR IGNORE INTO Users(username,password,role) VALUES(?,?,?)",
                        (username, pw, role))

        # ── 教練資料 ────────────────────────────────────────
        coach_users = cur.execute(
            "SELECT id FROM Users WHERE role='coach' ORDER BY id").fetchall()
        coach_details = [
            (coach_users[0]["id"], "王教練", "0912-345-678",
             "國家乙級桌球教練，執教 15 年，專精正手攻球與多球訓練。", "正手攻球、步法訓練"),
            (coach_users[1]["id"], "李教練", "0923-456-789",
             "前縣市代表隊選手，擅長防守與旋轉球技巧教學。", "防守技術、旋轉球"),
        ]
        for (uid, name, phone, bio, spec) in coach_details:
            cur.execute(
                "INSERT OR IGNORE INTO Coaches(user_id,name,phone,bio,specialty) VALUES(?,?,?,?,?)",
                (uid, name, phone, bio, spec))

        # ── 學員資料 ────────────────────────────────────────
        stu_users = cur.execute(
            "SELECT id FROM Users WHERE role='student' ORDER BY id").fetchall()
        stu_details = [
            (stu_users[0]["id"], "陳小明", "0933-111-222", "ming@example.com"),
            (stu_users[1]["id"], "林小華", "0944-222-333", "hua@example.com"),
            (stu_users[2]["id"], "張小英", "0955-333-444", "ying@example.com"),
        ]
        for (uid, name, phone, email) in stu_details:
            cur.execute(
                "INSERT OR IGNORE INTO Students(user_id,name,phone,email) VALUES(?,?,?,?)",
                (uid, name, phone, email))

        # ── 預設課程 ────────────────────────────────────────
        coaches = cur.execute("SELECT id FROM Coaches ORDER BY id").fetchall()
        if coaches:
            demo_courses = [
                ("團體班", coaches[0]["id"], "週一", "14:00", 90,  1, 2000),
                ("個人班", coaches[0]["id"], "週三", "10:00", 60,  2, 1500),
                ("團體班", coaches[1]["id"], "週二", "16:00", 90,  3, 2000),
                ("暑假班", coaches[1]["id"], "週五", "09:00", 120, 4, 3000),
            ]
            for c in demo_courses:
                cur.execute("""INSERT OR IGNORE INTO Courses
                    (course_type,coach_id,schedule_day,schedule_time,duration,table_id,fee)
                    VALUES(?,?,?,?,?,?,?)""", c)

        # ── 預設報名 ────────────────────────────────────────
        students = cur.execute("SELECT id FROM Students ORDER BY id").fetchall()
        courses  = cur.execute("SELECT id FROM Courses ORDER BY id").fetchall()
        today_str = date.today().isoformat()
        if students and courses:
            enroll_pairs = [(students[0]["id"], courses[0]["id"]),
                            (students[0]["id"], courses[1]["id"]),
                            (students[1]["id"], courses[0]["id"]),
                            (students[1]["id"], courses[2]["id"]),
                            (students[2]["id"], courses[2]["id"]),
                            (students[2]["id"], courses[3]["id"])]
            for (sid, cid) in enroll_pairs:
                cur.execute("""INSERT OR IGNORE INTO Enrollments(student_id,course_id,enrolled_date)
                    VALUES(?,?,?)""", (sid, cid, today_str))

        # ── 預設繳費紀錄 ────────────────────────────────────
        period = date.today().strftime("%Y-%m")
        if students and courses:
            payment_data = [
                (students[0]["id"], courses[0]["id"], 2000, period),
                (students[0]["id"], courses[1]["id"], 1500, period),
                (students[1]["id"], courses[0]["id"], 2000, period),
                (students[1]["id"], courses[2]["id"], 2000, period),
                (students[2]["id"], courses[2]["id"], 2000, period),
                (students[2]["id"], courses[3]["id"], 3000, period),
            ]
            for (sid, cid, amt, per) in payment_data:
                cur.execute("""INSERT OR IGNORE INTO Payments(student_id,course_id,amount,period)
                    SELECT ?,?,?,? WHERE NOT EXISTS
                    (SELECT 1 FROM Payments WHERE student_id=? AND course_id=? AND period=?)""",
                    (sid, cid, amt, per, sid, cid, per))

        conn.commit()


# ══════════════════════════════════════════════════════════════
# 📄  PDF 收據產生
# ══════════════════════════════════════════════════════════════

def generate_receipt_pdf(payment_id: int, student_name: str, course_type: str,
                         schedule_day: str, schedule_time: str,
                         period: str, amount: float, paid_date: str) -> str:
    """產生繳費收據 PDF，回傳檔案路徑"""
    filename  = f"PAY-{payment_id:04d}_{student_name}.pdf"
    filepath  = os.path.join(RECEIPT_DIR, filename)
    doc       = SimpleDocTemplate(filepath, pagesize=A4,
                                  rightMargin=2*cm, leftMargin=2*cm,
                                  topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', fontName=PDF_FONT_BOLD, fontSize=18,
                                 alignment=1, spaceAfter=6)
    sub_style   = ParagraphStyle('sub',   fontName=PDF_FONT,      fontSize=11,
                                 alignment=1, spaceAfter=4, textColor=colors.grey)
    body_style  = ParagraphStyle('body',  fontName=PDF_FONT,      fontSize=12,
                                 spaceAfter=6, leading=20)
    foot_style  = ParagraphStyle('foot',  fontName=PDF_FONT,      fontSize=10,
                                 alignment=1, textColor=colors.grey)

    story = []
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("🏓 桌球教室繳費收據", title_style))
    story.append(Paragraph("Ping-Pong Academy Receipt", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#FF6B35")))
    story.append(Spacer(1, 0.5*cm))

    data = [
        ["收據編號", f"PAY-{payment_id:04d}"],
        ["學員姓名", student_name],
        ["課程名稱", f"{course_type}（{schedule_day} {schedule_time}）"],
        ["繳費期別", period],
        ["繳費金額", f"NT$ {amount:,.0f}"],
        ["繳費日期", paid_date],
    ]
    t = Table(data, colWidths=[4*cm, 12*cm])
    t.setStyle(TableStyle([
        ('FONTNAME',    (0,0), (-1,-1), PDF_FONT),
        ('FONTSIZE',    (0,0), (-1,-1), 12),
        ('FONTNAME',    (0,0), (0,-1),  PDF_FONT_BOLD),
        ('BACKGROUND',  (0,0), (0,-1),  colors.HexColor("#FFF0EB")),
        ('TEXTCOLOR',   (0,0), (0,-1),  colors.HexColor("#FF6B35")),
        ('GRID',        (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [colors.white, colors.HexColor("#FAFAFA")]),
        ('TOPPADDING',  (0,0), (-1,-1), 8),
        ('BOTTOMPADDING',(0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t)
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph("感謝您的繳費，祝您練球愉快！", foot_style))
    story.append(Paragraph("桌球教室 敬上", foot_style))

    doc.build(story)
    return filepath


# ══════════════════════════════════════════════════════════════
# 🔐  認證
# ══════════════════════════════════════════════════════════════

def login_page():
    """登入頁面"""
    col_l, col_c, col_r = st.columns([1, 1.4, 1])
    with col_c:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="page-title" style="text-align:center;">🏓 桌球教室管理與互動系統</div>',
                    unsafe_allow_html=True)
        st.markdown('<p style="text-align:center;color:#888;">Ping-Pong Academy Manager</p>',
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
                    (username, hash_pw(password))
                ).fetchone()
            if row:
                st.session_state["user_id"]  = row["id"]
                st.session_state["username"] = row["username"]
                st.session_state["role"]     = row["role"]
                # 取得對應角色 id
                with get_conn() as conn:
                    if row["role"] == "student":
                        s = conn.execute(
                            "SELECT id,name FROM Students WHERE user_id=?", (row["id"],)).fetchone()
                        if s:
                            st.session_state["profile_id"]   = s["id"]
                            st.session_state["profile_name"] = s["name"]
                    elif row["role"] == "coach":
                        c = conn.execute(
                            "SELECT id,name FROM Coaches WHERE user_id=?", (row["id"],)).fetchone()
                        if c:
                            st.session_state["profile_id"]   = c["id"]
                            st.session_state["profile_name"] = c["name"]
                    else:
                        st.session_state["profile_id"]   = 0
                        st.session_state["profile_name"] = "系統管理員"
                st.rerun()
            else:
                st.error("帳號或密碼錯誤，請重新輸入")

        st.markdown("---")
        st.caption("預設測試帳號：admin / admin123 ｜ coach01 / coach123 ｜ student01 / stu123")


def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# ══════════════════════════════════════════════════════════════
# 🎛️  側邊欄
# ══════════════════════════════════════════════════════════════

MENUS = {
    "student": ["📚 我的課程", "🙏 請假申請", "💳 繳費狀況", "📋 出勤紀錄"],
    "coach":   ["👤 個人簡介編輯", "👥 課程學員名單", "✅ 課堂點名"],
    "admin":   ["📅 課程管理", "📊 出勤總表", "💰 繳費管理", "📈 報表查詢", "🔑 帳號管理"],
}

ROLE_LABEL = {"student": "學員", "coach": "教練", "admin": "管理者"}
ROLE_BADGE = {"student": "role-badge-student", "coach": "role-badge-coach", "admin": "role-badge-admin"}


def sidebar():
    role  = st.session_state.get("role", "")
    name  = st.session_state.get("profile_name", "")

    with st.sidebar:
        st.markdown("## 🏓 Ping-Pong Academy")
        st.divider()
        badge_cls = ROLE_BADGE.get(role, "")
        st.markdown(
            f"**{name}**　"
            f'<span class="{badge_cls}">{ROLE_LABEL.get(role,"")}</span>',
            unsafe_allow_html=True)
        st.markdown(f"<small style='color:#888;'>帳號：{st.session_state.get('username','')}</small>",
                    unsafe_allow_html=True)
        st.divider()

        menu_items = MENUS.get(role, [])
        selected   = st.radio("功能選單", menu_items, label_visibility="collapsed")

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
    col1.metric("已報名課程數", len(df))
    col2.metric("每月課程費用合計", f"NT$ {df['費用_元'].sum():,.0f}")
    col3.metric("平均課程時長", f"{df['時長_分鐘'].mean():.0f} 分鐘")
    st.divider()

    display = df.drop(columns=["id"])
    st.dataframe(display, use_container_width=True, height=300)


def page_leave_request():
    st.markdown('<div class="page-title">🙏 請假申請</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")

    with get_conn() as conn:
        courses = pd.read_sql_query("""
            SELECT c.id, c.course_type || ' ' || c.schedule_day || ' ' || c.schedule_time AS label
            FROM Enrollments e JOIN Courses c ON e.course_id=c.id
            WHERE e.student_id=?
        """, conn, params=(sid,))

    if courses.empty:
        st.warning("您尚未報名任何課程，無法申請請假。")
        return

    course_map = dict(zip(courses["label"], courses["id"]))

    st.markdown('<div class="section-title">📝 申請請假</div>', unsafe_allow_html=True)
    with st.form("leave_form"):
        selected_course = st.selectbox("選擇課程", list(course_map.keys()))
        leave_date      = st.date_input("請假日期", min_value=date.today())
        reason          = st.text_area("請假原因（選填）", height=80)
        submitted       = st.form_submit_button("📨 送出請假申請", type="primary")

    if submitted:
        cid = course_map[selected_course]
        try:
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO LeaveRequests(student_id,course_id,leave_date,reason,status,created_at)
                    VALUES(?,?,?,?,'pending',?)
                """, (sid, cid, leave_date.isoformat(), reason, datetime.now().isoformat()))
                conn.commit()
            st.success("✅ 請假申請已送出，等待審核中。")
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
                   lr.created_at AS 申請時間
            FROM LeaveRequests lr
            JOIN Courses c ON lr.course_id=c.id
            WHERE lr.student_id=?
            ORDER BY lr.leave_date DESC
        """, conn, params=(sid,))
    if hist.empty:
        st.info("尚無請假紀錄。")
    else:
        st.dataframe(hist, use_container_width=True, height=300)


def page_payment_status():
    st.markdown('<div class="page-title">💳 繳費狀況</div>', unsafe_allow_html=True)
    st.divider()
    sid = st.session_state.get("profile_id")

    with get_conn() as conn:
        df = pd.read_sql_query("""
            SELECT p.id, c.course_type || ' ' || c.schedule_day AS 課程,
                   p.period AS 期別, p.amount AS 金額,
                   COALESCE(p.paid_date,'—') AS 繳費日期,
                   p.is_paid, p.pdf_path
            FROM Payments p JOIN Courses c ON p.course_id=c.id
            WHERE p.student_id=?
            ORDER BY p.period DESC
        """, conn, params=(sid,))

    if df.empty:
        st.info("目前無繳費紀錄。")
        return

    paid_total   = df[df["is_paid"]==1]["金額"].sum()
    unpaid_total = df[df["is_paid"]==0]["金額"].sum()
    rate         = paid_total/(paid_total+unpaid_total)*100 if (paid_total+unpaid_total)>0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("已繳總額", f"NT$ {paid_total:,.0f}")
    col2.metric("未繳總額", f"NT$ {unpaid_total:,.0f}")
    col3.metric("繳費完成率", f"{rate:.1f}%")
    st.divider()

    df["狀態"] = df["is_paid"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
    display = df[["課程","期別","金額","繳費日期","狀態"]].copy()
    display["金額"] = display["金額"].apply(lambda x: f"NT$ {x:,.0f}")
    st.dataframe(display, use_container_width=True, height=350)

    # PDF 下載
    paid_df = df[(df["is_paid"]==1) & (df["pdf_path"] != "")]
    if not paid_df.empty:
        st.markdown('<div class="section-title">📄 下載繳費收據</div>', unsafe_allow_html=True)
        for _, row in paid_df.iterrows():
            if row["pdf_path"] and os.path.exists(row["pdf_path"]):
                with open(row["pdf_path"], "rb") as f:
                    st.download_button(
                        f"⬇️ 下載 {row['課程']} {row['期別']} 收據",
                        data=f.read(),
                        file_name=os.path.basename(row["pdf_path"]),
                        mime="application/pdf",
                        key=f"dl_{row['id']}"
                    )


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
                   END AS 狀態
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses c        ON cs.course_id=c.id
            WHERE a.student_id=?
            ORDER BY cs.session_date DESC
        """, conn, params=(sid,))

    if df.empty:
        st.info("目前尚無出勤紀錄。")
        return

    raw_df = pd.read_sql_query("""
        SELECT a.status FROM Attendance a
        JOIN ClassSessions cs ON a.session_id=cs.id
        WHERE a.student_id=?
    """, get_conn(), params=(sid,))

    present = (raw_df["status"]=="present").sum()
    absent  = (raw_df["status"]=="absent").sum()
    leave   = (raw_df["status"]=="leave").sum()
    total   = len(raw_df)
    rate    = present/total*100 if total>0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("出席次數", present)
    col2.metric("缺席次數", absent)
    col3.metric("請假次數", leave)
    col4.metric("出席率",   f"{rate:.1f}%")
    st.divider()

    st.dataframe(df, use_container_width=True, height=320)

    # 近 3 個月出勤圖表
    st.markdown('<div class="section-title">📊 近期出勤統計</div>', unsafe_allow_html=True)
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
        pivot = chart_df.pivot_table(index="月份", columns="status", values="次數", fill_value=0)
        fig = go.Figure()
        color_map = {"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
        label_map = {"present":"出席","absent":"缺席","leave":"請假"}
        for col in pivot.columns:
            fig.add_trace(go.Bar(name=label_map.get(col,col), x=pivot.index,
                                 y=pivot[col], marker_color=color_map.get(col,"#999")))
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

    st.markdown("**目前簡介**")
    col1, col2 = st.columns(2)
    col1.info(f"**姓名：** {coach['name']}\n\n**電話：** {coach['phone']}\n\n**專長：** {coach['specialty']}")
    col2.info(f"**個人簡介：**\n\n{coach['bio']}")
    st.divider()

    st.markdown('<div class="section-title">✏️ 編輯資料</div>', unsafe_allow_html=True)
    with st.form("coach_profile_form"):
        name      = st.text_input("姓名",   value=coach["name"])
        phone     = st.text_input("聯絡電話", value=coach["phone"])
        bio       = st.text_area("個人簡介 / 教學經歷", value=coach["bio"], height=120)
        specialty = st.text_input("專長",    value=coach["specialty"])
        saved     = st.form_submit_button("💾 儲存變更", type="primary")

    if saved:
        if not name.strip():
            st.error("姓名不可為空。")
            return
        try:
            with get_conn() as conn:
                conn.execute("""
                    UPDATE Coaches SET name=?,phone=?,bio=?,specialty=? WHERE user_id=?
                """, (name, phone, bio, specialty, uid))
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
            SELECT id, course_type || ' ' || schedule_day || ' ' || schedule_time AS label
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
            WHERE e.course_id=?
            ORDER BY s.name
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
            SELECT c.id, c.course_type || ' ' || c.schedule_day || ' ' || c.schedule_time AS label,
                   c.schedule_time, c.table_id
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

    with get_conn() as conn:
        students = pd.read_sql_query("""
            SELECT s.id, s.name FROM Enrollments e JOIN Students s ON e.student_id=s.id
            WHERE e.course_id=? ORDER BY s.name
        """, conn, params=(cid,))

    if students.empty:
        st.warning("此課程尚無學員，無法點名。")
        return

    # 取得或建立 session
    with get_conn() as conn:
        sess = conn.execute("""
            SELECT id FROM ClassSessions
            WHERE course_id=? AND session_date=?
        """, (cid, session_date.isoformat())).fetchone()
        if sess is None:
            cur = conn.execute("""
                INSERT INTO ClassSessions(course_id,session_date,session_time,coach_id,table_id)
                VALUES(?,?,?,?,?)
            """, (cid, session_date.isoformat(), str(row["schedule_time"]),
                  cid_coach, int(row["table_id"])))
            conn.commit()
            session_id = cur.lastrowid
        else:
            session_id = sess["id"]

    # 取得現有出勤
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT student_id, status FROM Attendance WHERE session_id=?",
            (session_id,)).fetchall()
    exist_map = {r["student_id"]: r["status"] for r in existing}

    st.markdown(f'<div class="section-title">👥 點名列表（共 {len(students)} 位學員）</div>',
                unsafe_allow_html=True)
    status_options = ["出席", "缺席", "請假"]
    status_map_rev = {"出席":"present","缺席":"absent","請假":"leave"}
    status_map_fwd = {"present":"出席","absent":"缺席","leave":"請假"}

    selections = {}
    for _, stu in students.iterrows():
        cur_status = status_map_fwd.get(exist_map.get(stu["id"], "present"), "出席")
        val = st.radio(f"**{stu['name']}**", status_options,
                       index=status_options.index(cur_status),
                       horizontal=True, key=f"att_{session_id}_{stu['id']}")
        selections[stu["id"]] = val

    if st.button("📝 送出點名結果", type="primary", use_container_width=True):
        try:
            with get_conn() as conn:
                for sid_s, status_label in selections.items():
                    conn.execute("""
                        INSERT INTO Attendance(session_id,student_id,status)
                        VALUES(?,?,?)
                        ON CONFLICT(session_id,student_id) DO UPDATE SET status=excluded.status
                    """, (session_id, sid_s, status_map_rev[status_label]))
                conn.commit()
            present_count = sum(1 for v in selections.values() if v=="出席")
            absent_count  = sum(1 for v in selections.values() if v=="缺席")
            st.success(f"✅ 點名完成！出席：{present_count} 人，缺席：{absent_count} 人")
        except Exception as e:
            st.error(f"點名失敗：{e}")


# ══════════════════════════════════════════════════════════════
# 🔧  管理者功能頁面
# ══════════════════════════════════════════════════════════════

def page_admin_courses():
    st.markdown('<div class="page-title">📅 課程管理</div>', unsafe_allow_html=True)
    st.divider()
    tab_list, tab_add, tab_enroll = st.tabs(["📋 課程總表", "➕ 新增課程", "🎓 學員報名管理"])

    # ── 課程總表 ───────────────────────────────────────────
    with tab_list:
        with get_conn() as conn:
            df = pd.read_sql_query("""
                SELECT c.id AS 課程ID, c.course_type AS 課程類型, co.name AS 教練,
                       c.schedule_day AS 星期, c.schedule_time AS 時間,
                       c.duration AS 時長_分鐘, t.name AS 桌次,
                       c.fee AS 費用_元
                FROM Courses c
                JOIN Coaches co ON c.coach_id=co.id
                JOIN Tables  t  ON c.table_id=t.id
                ORDER BY c.schedule_day, c.schedule_time
            """, conn)
        if df.empty:
            st.info("目前無課程資料。")
        else:
            st.dataframe(df, use_container_width=True, height=380)

            # 桌次佔用視覺化
            st.markdown('<div class="section-title">🏓 桌次佔用概況</div>',
                        unsafe_allow_html=True)
            used_tables = set(
                pd.read_sql_query("SELECT table_id FROM Courses", get_conn())["table_id"].tolist()
            )
            fig = go.Figure()
            colors_list = ["#FF6B35" if i+1 in used_tables else "#E8F5E9" for i in range(8)]
            text_list   = [f"桌{i+1}<br>{'使用中' if i+1 in used_tables else '空閒'}"
                           for i in range(8)]
            fig.add_trace(go.Bar(
                x=[f"桌{i+1}" for i in range(8)],
                y=[1]*8,
                marker_color=colors_list,
                text=text_list,
                textposition="inside",
                showlegend=False,
            ))
            fig.update_layout(height=180, yaxis_visible=False,
                              margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig, use_container_width=True)

    # ── 新增課程 ───────────────────────────────────────────
    with tab_add:
        with get_conn() as conn:
            coaches = pd.read_sql_query("SELECT id, name FROM Coaches ORDER BY name", conn)

        if coaches.empty:
            st.warning("尚無教練資料，請先新增教練帳號。")
        else:
            coach_map  = dict(zip(coaches["name"], coaches["id"]))
            days       = ["週一","週二","週三","週四","週五","週六","週日"]
            types      = ["團體班","個人班","寒假班","暑假班"]
            durations  = [60, 90, 120]

            with st.form("add_course_form"):
                col1, col2 = st.columns(2)
                with col1:
                    c_type    = st.selectbox("課程類型", types)
                    coach_sel = st.selectbox("選擇教練", list(coach_map.keys()))
                    day       = st.selectbox("上課星期", days)
                    time_val  = st.time_input("上課時間", value=datetime.strptime("09:00","%H:%M").time())
                with col2:
                    duration  = st.selectbox("課程時長（分鐘）", durations)
                    table_no  = st.selectbox("使用桌次", list(range(1,9)))
                    fee       = st.number_input("費用（元）", min_value=0, value=2000, step=100)
                submitted = st.form_submit_button("✅ 新增課程", type="primary")

            if submitted:
                time_str = time_val.strftime("%H:%M")
                # 衝突檢查
                with get_conn() as conn:
                    conflict = conn.execute("""
                        SELECT id FROM Courses
                        WHERE schedule_day=? AND schedule_time=? AND table_id=?
                    """, (day, time_str, table_no)).fetchone()
                if conflict:
                    st.error(f"⚠️ 該時段（{day} {time_str}）桌次 {table_no} 已被佔用，請選擇其他桌次或時段。")
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute("""
                                INSERT INTO Courses(course_type,coach_id,schedule_day,
                                    schedule_time,duration,table_id,fee)
                                VALUES(?,?,?,?,?,?,?)
                            """, (c_type, coach_map[coach_sel], day,
                                  time_str, duration, table_no, fee))
                            conn.commit()
                        st.success("✅ 課程新增成功！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增失敗：{e}")

    # ── 學員報名管理 ───────────────────────────────────────
    with tab_enroll:
        with get_conn() as conn:
            all_courses  = pd.read_sql_query("""
                SELECT c.id, c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label
                FROM Courses c ORDER BY label
            """, conn)
            all_students = pd.read_sql_query("SELECT id, name FROM Students ORDER BY name", conn)

        if all_courses.empty or all_students.empty:
            st.info("請先建立課程與學員資料。")
            return

        cmap  = dict(zip(all_courses["label"], all_courses["id"]))
        smap  = dict(zip(all_students["name"], all_students["id"]))

        col1, col2 = st.columns(2)
        with col1:
            sel_course  = st.selectbox("選擇課程", list(cmap.keys()), key="enroll_course")
            cid_enroll  = cmap[sel_course]
            with get_conn() as conn:
                enrolled_ids = [r["student_id"] for r in conn.execute(
                    "SELECT student_id FROM Enrollments WHERE course_id=?", (cid_enroll,)).fetchall()]

            already_enrolled = [s for s in all_students["name"] if smap[s] in enrolled_ids]
            not_enrolled     = [s for s in all_students["name"] if smap[s] not in enrolled_ids]

            st.markdown(f"**已報名學員（{len(already_enrolled)} 人）**")
            for nm in already_enrolled:
                c1, c2 = st.columns([3,1])
                c1.write(nm)
                if c2.button("移除", key=f"rm_{smap[nm]}_{cid_enroll}"):
                    with get_conn() as conn:
                        conn.execute("DELETE FROM Enrollments WHERE student_id=? AND course_id=?",
                                     (smap[nm], cid_enroll))
                        conn.commit()
                    st.rerun()

        with col2:
            st.markdown("**新增學員報名**")
            if not_enrolled:
                add_stu = st.selectbox("選擇學員", not_enrolled, key="add_stu")
                if st.button("➕ 加入報名", type="primary"):
                    try:
                        with get_conn() as conn:
                            conn.execute("""
                                INSERT INTO Enrollments(student_id,course_id,enrolled_date)
                                VALUES(?,?,?)
                            """, (smap[add_stu], cid_enroll, date.today().isoformat()))
                            conn.commit()
                        st.success(f"✅ {add_stu} 已加入課程！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"報名失敗：{e}")
            else:
                st.info("所有學員皆已報名此課程。")


def page_admin_attendance():
    st.markdown('<div class="page-title">📊 出勤總表</div>', unsafe_allow_html=True)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("起始日期", value=date.today() - timedelta(days=30))
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
                JOIN Courses c        ON cs.course_id=c.id
                JOIN Coaches co       ON cs.coach_id=co.id
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
    leave   = (df["_status"]=="leave").sum()
    rate    = present/total*100 if total>0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總紀錄筆數", total)
    col2.metric("出席人次",   present)
    col3.metric("缺席人次",   absent)
    col4.metric("整體出席率", f"{rate:.1f}%")
    st.divider()

    display = df.drop(columns=["_status"])
    st.dataframe(display, use_container_width=True, height=380)

    # CSV 匯出
    csv = display.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ 匯出 CSV", data=csv,
                       file_name=f"出勤總表_{start_date}_{end_date}.csv",
                       mime="text/csv")
    st.divider()

    # 每日出席圖
    st.markdown('<div class="section-title">📊 每日出勤統計</div>', unsafe_allow_html=True)
    daily = df.groupby(["日期","_status"]).size().reset_index(name="count")
    daily_pivot = daily.pivot_table(index="日期", columns="_status", values="count", fill_value=0)

    fig = go.Figure()
    color_map = {"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
    label_map = {"present":"出席","absent":"缺席","leave":"請假"}
    for col in daily_pivot.columns:
        fig.add_trace(go.Bar(name=label_map.get(col,col), x=daily_pivot.index,
                             y=daily_pivot[col], marker_color=color_map.get(col,"#999")))
    fig.update_layout(barmode="stack", height=320,
                      margin=dict(l=0,r=0,t=20,b=0),
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)


def page_admin_payments():
    st.markdown('<div class="page-title">💰 繳費管理</div>', unsafe_allow_html=True)
    st.divider()

    filter_opt = st.radio("篩選", ["全部","未繳費","已繳費"], horizontal=True)
    filter_map = {"全部": None, "未繳費": 0, "已繳費": 1}
    fval = filter_map[filter_opt]

    query = """
        SELECT p.id, s.name AS 學員,
               c.course_type || ' ' || c.schedule_day AS 課程,
               p.period AS 期別, p.amount AS 金額,
               COALESCE(p.paid_date,'—') AS 繳費日期,
               p.is_paid, p.pdf_path, p.student_id,
               c.course_type, c.schedule_day, c.schedule_time
        FROM Payments p
        JOIN Students s ON p.student_id=s.id
        JOIN Courses  c ON p.course_id=c.id
    """
    params = ()
    if fval is not None:
        query += " WHERE p.is_paid=?"
        params = (fval,)
    query += " ORDER BY p.is_paid ASC, s.name"

    with get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=params)

    total_amt  = df["金額"].sum()
    paid_amt   = df[df["is_paid"]==1]["金額"].sum()
    unpaid_amt = df[df["is_paid"]==0]["金額"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("總應收金額", f"NT$ {total_amt:,.0f}")
    col2.metric("已收金額",   f"NT$ {paid_amt:,.0f}")
    col3.metric("未收金額",   f"NT$ {unpaid_amt:,.0f}")
    st.divider()

    if df.empty:
        st.info("沒有符合條件的繳費紀錄。")
        return

    # 逐筆顯示可操作的繳費紀錄
    display_cols = ["學員","課程","期別","金額","繳費日期","狀態"]
    show_df = df.copy()
    show_df["狀態"] = show_df["is_paid"].apply(lambda x: "✅ 已繳" if x else "❌ 未繳")
    show_df["金額_顯示"] = show_df["金額"].apply(lambda x: f"NT$ {x:,.0f}")

    for _, row in show_df.iterrows():
        with st.expander(f"{'✅' if row['is_paid'] else '❌'} {row['學員']} ｜ {row['課程']} ｜ {row['期別']} ｜ NT$ {row['金額']:,.0f}"):
            c1, c2, c3 = st.columns([2,2,2])
            c1.write(f"**繳費狀態：** {row['狀態']}")
            c2.write(f"**繳費日期：** {row['繳費日期']}")

            if not row["is_paid"]:
                pay_date = c3.date_input("繳費日期", value=date.today(),
                                         key=f"pdate_{row['id']}")
                if st.button("💳 標記為已繳費並產生收據", key=f"pay_{row['id']}", type="primary"):
                    with st.spinner("正在產生繳費收據..."):
                        try:
                            pdf_path = generate_receipt_pdf(
                                payment_id   = int(row["id"]),
                                student_name = row["學員"],
                                course_type  = row["course_type"],
                                schedule_day = row["schedule_day"],
                                schedule_time= row["schedule_time"],
                                period       = row["期別"],
                                amount       = row["金額"],
                                paid_date    = pay_date.strftime("%Y年%m月%d日")
                            )
                            with get_conn() as conn:
                                conn.execute("""
                                    UPDATE Payments SET is_paid=1, paid_date=?, pdf_path=?
                                    WHERE id=?
                                """, (pay_date.isoformat(), pdf_path, int(row["id"])))
                                conn.commit()
                            st.success("✅ 繳費完成，PDF 已產生！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"操作失敗：{e}")
            else:
                if row["pdf_path"] and os.path.exists(str(row["pdf_path"])):
                    with open(row["pdf_path"], "rb") as f:
                        st.download_button("⬇️ 下載收據 PDF", data=f.read(),
                                           file_name=os.path.basename(row["pdf_path"]),
                                           mime="application/pdf",
                                           key=f"dlpdf_{row['id']}")


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

    tab1, tab2, tab3 = st.tabs(["📅 課程報表", "👥 出勤統計報表", "💰 繳費統計報表"])

    # ── 課程報表 ───────────────────────────────────────────
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
                GROUP BY cs.id
                ORDER BY cs.session_date DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))

        if df.empty:
            st.info("此區間無上課紀錄。")
        else:
            col1, col2 = st.columns(2)
            col1.metric("上課總堂數", len(df))
            col2.metric("平均出席人數", f"{df['出席學員數'].mean():.1f}")
            st.dataframe(df, use_container_width=True, height=350)
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 匯出 CSV", csv,
                               file_name=f"課程報表_{start_date}_{end_date}.csv",
                               mime="text/csv")

    # ── 出勤統計報表 ────────────────────────────────────────
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
                GROUP BY s.id
                ORDER BY 出席 DESC
            """, conn, params=(start_date.isoformat(), end_date.isoformat()))

        if df2.empty:
            st.info("此區間無出勤資料。")
        else:
            df2["出席率"] = (df2["出席"]/df2["總次數"]*100).round(1).astype(str) + "%"
            st.dataframe(df2, use_container_width=True, height=300)

            fig = px.bar(df2, x="學員", y="出席",
                         color_discrete_sequence=["#4CAF50"],
                         title="學員出席次數")
            fig.update_layout(height=300, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig, use_container_width=True)

            csv2 = df2.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ 匯出 CSV", csv2,
                               file_name=f"出勤統計_{start_date}_{end_date}.csv",
                               mime="text/csv")

    # ── 繳費統計報表 ────────────────────────────────────────
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
            pay_rate   = paid_fee/total_fee*100 if total_fee>0 else 0

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("總應收",   f"NT$ {total_fee:,.0f}")
            col2.metric("已收",     f"NT$ {paid_fee:,.0f}")
            col3.metric("未收",     f"NT$ {unpaid_fee:,.0f}")
            col4.metric("繳費率",   f"{pay_rate:.1f}%")

            fig = go.Figure(go.Pie(
                labels=["已繳費","未繳費"],
                values=[paid_fee, unpaid_fee],
                hole=0.4,
                marker_colors=["#4CAF50","#F44336"]
            ))
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
    st.markdown('<div class="page-title">🔑 帳號管理</div>', unsafe_allow_html=True)
    st.divider()

    with get_conn() as conn:
        users = pd.read_sql_query("""
            SELECT u.id, u.username AS 帳號,
                   CASE u.role WHEN 'admin' THEN '管理者'
                               WHEN 'coach' THEN '教練'
                               ELSE '學員' END AS 角色,
                   COALESCE(s.name, co.name, '—') AS 姓名
            FROM Users u
            LEFT JOIN Students s ON u.id=s.user_id AND u.role='student'
            LEFT JOIN Coaches  co ON u.id=co.user_id AND u.role='coach'
            ORDER BY u.role, u.username
        """, conn)

    st.dataframe(users.drop(columns=["id"]), use_container_width=True, height=280)
    st.divider()

    tab_add, tab_reset = st.tabs(["➕ 新增帳號", "🔒 重設密碼"])

    with tab_add:
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("帳號")
                new_password = st.text_input("密碼", type="password")
            with col2:
                new_role = st.selectbox("角色", ["student","coach","admin"],
                                        format_func=lambda x: {"student":"學員","coach":"教練","admin":"管理者"}[x])
                new_name = st.text_input("姓名")
            submitted = st.form_submit_button("✅ 建立帳號", type="primary")

        if submitted:
            if not new_username or not new_password or not new_name:
                st.error("帳號、密碼與姓名皆為必填。")
            else:
                try:
                    with get_conn() as conn:
                        cur = conn.execute(
                            "INSERT INTO Users(username,password,role) VALUES(?,?,?)",
                            (new_username, hash_pw(new_password), new_role))
                        conn.commit()
                        uid = cur.lastrowid
                        if new_role == "student":
                            conn.execute(
                                "INSERT INTO Students(user_id,name) VALUES(?,?)", (uid, new_name))
                        elif new_role == "coach":
                            conn.execute(
                                "INSERT INTO Coaches(user_id,name) VALUES(?,?)", (uid, new_name))
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
            new_pw1  = st.text_input("新密碼",   type="password")
            new_pw2  = st.text_input("確認新密碼", type="password")
            reset_ok = st.form_submit_button("🔒 重設密碼", type="primary")

        if reset_ok:
            if not new_pw1:
                st.error("密碼不可為空。")
            elif new_pw1 != new_pw2:
                st.error("兩次輸入的密碼不一致。")
            else:
                try:
                    with get_conn() as conn:
                        conn.execute("UPDATE Users SET password=? WHERE id=?",
                                     (hash_pw(new_pw1), user_options[sel_user]))
                        conn.commit()
                    st.success(f"✅ 帳號 '{sel_user}' 的密碼已重設。")
                except Exception as e:
                    st.error(f"重設失敗：{e}")


# ══════════════════════════════════════════════════════════════
# 🚀  主程式
# ══════════════════════════════════════════════════════════════

def main():
    # 初始化資料庫
    init_db()

    # 未登入 → 顯示登入頁
    if "user_id" not in st.session_state:
        login_page()
        return

    # 側邊欄
    selected = sidebar()
    role     = st.session_state.get("role","")

    # 路由
    if role == "student":
        page_map = {
            "📚 我的課程":   page_my_courses,
            "🙏 請假申請":   page_leave_request,
            "💳 繳費狀況":   page_payment_status,
            "📋 出勤紀錄":   page_attendance_record,
        }
    elif role == "coach":
        page_map = {
            "👤 個人簡介編輯": page_coach_profile,
            "👥 課程學員名單": page_coach_students,
            "✅ 課堂點名":    page_coach_attendance,
        }
    elif role == "admin":
        page_map = {
            "📅 課程管理":   page_admin_courses,
            "📊 出勤總表":   page_admin_attendance,
            "💰 繳費管理":   page_admin_payments,
            "📈 報表查詢":   page_admin_reports,
            "🔑 帳號管理":   page_admin_accounts,
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

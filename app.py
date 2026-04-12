# ============================================================
# 🏓 桌球教室管理與互動系統
# 規格版本：v1.5  |  技術架構：Streamlit + SQLite
# 預設資料：各情境僅 1 筆，其餘由管理者手動新增
# ============================================================

import streamlit as st
import sqlite3, hashlib
import pandas as pd
from datetime import datetime, date, timedelta
import plotly.graph_objects as go
import plotly.express as px

DB_PATH = "./pingpong.db"

st.set_page_config(page_title="🏓 桌球教室管理系統", page_icon="🏓",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root{--accent:#FF6B35;--accent-light:#FFF0EB;}
.block-container{padding-top:1.5rem;}
div[data-testid="metric-container"]{
    background:var(--accent-light);border-left:4px solid var(--accent);
    border-radius:8px;padding:12px 16px;}
.stButton>button{border-radius:8px;font-weight:600;}
.page-title{font-size:1.6rem;font-weight:700;color:#1a1a2e;margin-bottom:.2rem;}
.section-title{font-size:1.1rem;font-weight:600;color:#FF6B35;margin:1rem 0 .5rem 0;}
.role-badge-admin  {background:#FF6B35;color:#fff;padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600;}
.role-badge-coach  {background:#2196F3;color:#fff;padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600;}
.role-badge-student{background:#4CAF50;color:#fff;padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600;}
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 🗄️  資料庫工具
# ══════════════════════════════════════════════════════════════

def get_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def validate_pw(pw):
    if len(pw) < 6 or not any(c.isalpha() for c in pw):
        return False, "密碼需至少 6 碼且包含至少一個英文字母"
    return True, ""

def t2m(t):
    h, m = map(int, t.split(":")); return h*60+m

def m2t(m): return f"{m//60:02d}:{m%60:02d}"

def end_t(start, dur): return m2t(t2m(start)+int(dur))

def make_code(day, tbl, stime, dur):
    dm={"週一":"1","週二":"2","週三":"3","週四":"4","週五":"5","週六":"6","週日":"7"}
    return f"{dm[day]}-{tbl}-{stime.replace(':','')}-{str(dur).zfill(3)}"

def check_conflict(conn, day, stime, dur, tbl, excl=None):
    ns, ne = t2m(stime), t2m(stime)+int(dur)
    rows = conn.execute(
        "SELECT id,schedule_time,duration FROM Courses WHERE schedule_day=? AND table_id=?",
        (day, tbl)).fetchall()
    return [r for r in rows
            if (excl is None or r["id"]!=excl)
            and ns < t2m(r["schedule_time"])+r["duration"]
            and ne > t2m(r["schedule_time"])]

def date_opts():
    wd=["一","二","三","四","五","六","日"]
    return [(f"{(date.today()+timedelta(days=i)).strftime('%Y-%m-%d')}"
             f"（{wd[(date.today()+timedelta(days=i)).weekday()]}）",
             date.today()+timedelta(days=i)) for i in range(7)]

WD = {"週一":0,"週二":1,"週三":2,"週四":3,"週五":4,"週六":5,"週日":6}


# ══════════════════════════════════════════════════════════════
# 🏗️  資料庫初始化（v1.5 schema）
# ══════════════════════════════════════════════════════════════

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS Users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            role TEXT NOT NULL, email TEXT DEFAULT '', display_name TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS Students(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
            name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES Users(id));
        CREATE TABLE IF NOT EXISTS Coaches(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
            name TEXT NOT NULL, phone TEXT DEFAULT '', bio TEXT DEFAULT '',
            specialty TEXT DEFAULT '', photo_path TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES Users(id));
        CREATE TABLE IF NOT EXISTS Tables(id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS Courses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT UNIQUE,
            course_type TEXT NOT NULL, coach_id INTEGER NOT NULL,
            schedule_day TEXT NOT NULL, schedule_time TEXT NOT NULL,
            duration INTEGER NOT NULL, table_id INTEGER NOT NULL,
            FOREIGN KEY(coach_id) REFERENCES Coaches(id),
            FOREIGN KEY(table_id) REFERENCES Tables(id));
        CREATE TABLE IF NOT EXISTS Enrollments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            fee REAL NOT NULL DEFAULT 0, enrolled_date TEXT NOT NULL,
            UNIQUE(student_id,course_id),
            FOREIGN KEY(student_id) REFERENCES Students(id),
            FOREIGN KEY(course_id)  REFERENCES Courses(id));
        CREATE TABLE IF NOT EXISTS ClassSessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL, session_date TEXT NOT NULL,
            session_time TEXT NOT NULL, coach_id INTEGER NOT NULL,
            table_id INTEGER NOT NULL, created_by TEXT NOT NULL DEFAULT 'system',
            FOREIGN KEY(course_id) REFERENCES Courses(id),
            FOREIGN KEY(coach_id)  REFERENCES Coaches(id),
            FOREIGN KEY(table_id)  REFERENCES Tables(id));
        CREATE TABLE IF NOT EXISTS Attendance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
            status TEXT NOT NULL, note TEXT DEFAULT '',
            UNIQUE(session_id,student_id),
            FOREIGN KEY(session_id) REFERENCES ClassSessions(id),
            FOREIGN KEY(student_id) REFERENCES Students(id));
        CREATE TABLE IF NOT EXISTS LeaveRequests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            session_id INTEGER, leave_date TEXT NOT NULL,
            reason TEXT DEFAULT '', status TEXT DEFAULT 'pending',
            reviewed_by INTEGER, reviewed_at TEXT,
            reject_reason TEXT DEFAULT '', created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES Students(id),
            FOREIGN KEY(course_id)  REFERENCES Courses(id));
        CREATE TABLE IF NOT EXISTS Payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            amount REAL NOT NULL, paid_date TEXT, paid_time TEXT,
            is_paid INTEGER DEFAULT 0, period TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES Students(id),
            FOREIGN KEY(course_id)  REFERENCES Courses(id));
        """)

        # 舊版 schema 升級
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
            try: cur.execute(sql)
            except: pass

        # 桌次 1~8
        for i in range(1,9):
            cur.execute("INSERT OR IGNORE INTO Tables(id,name) VALUES(?,?)",(i,f"桌{i}"))

        # ── 預設資料：各情境僅留 1 筆，其餘由管理者手動新增 ──
        # 帳號：admin / coach01 / stu01（各 1 個）
        for u,p,r,d in [
            ("admin",   hash_pw("admin123"), "admin",   "系統管理員"),
            ("coach01", hash_pw("coach123"), "coach",   ""),
            ("stu01",   hash_pw("stu123"),   "student", ""),
        ]:
            cur.execute(
                "INSERT OR IGNORE INTO Users(username,password,role,display_name) VALUES(?,?,?,?)",
                (u,p,r,d))

        # 教練資料（1 筆）
        cu = cur.execute("SELECT id FROM Users WHERE role='coach' LIMIT 1").fetchone()
        if cu:
            cur.execute(
                "INSERT OR IGNORE INTO Coaches(user_id,name,phone,bio,specialty) VALUES(?,?,?,?,?)",
                (cu["id"],"示範教練","","請至個人簡介頁面更新資料。",""))

        # 學員資料（1 筆）
        su = cur.execute("SELECT id FROM Users WHERE role='student' LIMIT 1").fetchone()
        if su:
            cur.execute(
                "INSERT OR IGNORE INTO Students(user_id,name,phone,email) VALUES(?,?,?,?)",
                (su["id"],"示範學員","",""))

        # 課程（1 筆）
        coach = cur.execute("SELECT id FROM Coaches LIMIT 1").fetchone()
        if coach:
            code = make_code("週一",1,"10:00",90)
            if not cur.execute("SELECT id FROM Courses WHERE course_code=?",(code,)).fetchone():
                cur.execute(
                    "INSERT INTO Courses(course_code,course_type,coach_id,"
                    "schedule_day,schedule_time,duration,table_id) VALUES(?,?,?,?,?,?,?)",
                    (code,"團體班",coach["id"],"週一","10:00",90,1))

        # 報名（1 筆）+ 繳費單（1 筆）
        stu = cur.execute("SELECT id FROM Students LIMIT 1").fetchone()
        crs = cur.execute("SELECT id FROM Courses  LIMIT 1").fetchone()
        if stu and crs:
            if not cur.execute(
                    "SELECT id FROM Enrollments WHERE student_id=? AND course_id=?",
                    (stu["id"],crs["id"])).fetchone():
                cur.execute(
                    "INSERT INTO Enrollments(student_id,course_id,fee,enrolled_date)"
                    " VALUES(?,?,?,?)",
                    (stu["id"],crs["id"],2000,date.today().isoformat()))
            period = date.today().strftime("%Y-%m")
            if not cur.execute(
                    "SELECT id FROM Payments WHERE student_id=? AND course_id=? AND period=?",
                    (stu["id"],crs["id"],period)).fetchone():
                cur.execute(
                    "INSERT INTO Payments(student_id,course_id,amount,period,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (stu["id"],crs["id"],2000,period,datetime.now().isoformat()))
        conn.commit()


# ══════════════════════════════════════════════════════════════
# 🔐  認證
# ══════════════════════════════════════════════════════════════

def login_page():
    _,col,_ = st.columns([1,1.4,1])
    with col:
        st.markdown("<br>",unsafe_allow_html=True)
        st.markdown('<div class="page-title" style="text-align:center;">🏓 桌球教室管理與互動系統</div>',
                    unsafe_allow_html=True)
        st.markdown('<p style="text-align:center;color:#888;">Ping-Pong Academy Manager v1.5</p>',
                    unsafe_allow_html=True)
        st.divider()
        username = st.text_input("帳號", placeholder="請輸入帳號")
        password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
        if st.button("🔑 登入系統", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("帳號與密碼不可為空"); return
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM Users WHERE username=? AND password=?",
                    (username, hash_pw(password))).fetchone()
            if not row:
                st.error("帳號或密碼錯誤，請重新輸入"); return
            st.session_state.update({"user_id":row["id"],"username":row["username"],"role":row["role"]})
            with get_conn() as conn:
                if row["role"]=="student":
                    s=conn.execute("SELECT id,name FROM Students WHERE user_id=?",
                                   (row["id"],)).fetchone()
                    if s:
                        st.session_state["profile_id"]=s["id"]
                        st.session_state["profile_name"]=s["name"]
                elif row["role"]=="coach":
                    c=conn.execute("SELECT id,name FROM Coaches WHERE user_id=?",
                                   (row["id"],)).fetchone()
                    if c:
                        st.session_state["profile_id"]=c["id"]
                        st.session_state["profile_name"]=c["name"]
                else:
                    st.session_state["profile_id"]=0
                    dn=conn.execute("SELECT display_name FROM Users WHERE id=?",
                                    (row["id"],)).fetchone()
                    st.session_state["profile_name"]=(dn["display_name"] or "管理者") if dn else "管理者"
            st.rerun()
        st.markdown("---")
        st.caption("預設帳號：admin / admin123　｜　coach01 / coach123　｜　stu01 / stu123")

def logout():
    for k in list(st.session_state.keys()): del st.session_state[k]
    st.rerun()


# ══════════════════════════════════════════════════════════════
# 🎛️  側邊欄
# ══════════════════════════════════════════════════════════════

MENUS = {
    "student":["📚 我的課程","🙏 請假申請","💳 繳費狀況","📋 出勤紀錄","📅 近期課程查詢"],
    "coach"  :["👤 個人簡介編輯","👥 課程學員名單","✅ 課堂點名","🙏 請假審核","📅 近期課程查詢"],
    "admin"  :["📅 課程管理","📊 出勤總表","💰 繳費管理","📈 報表查詢","🔑 帳號管理","📅 近期課程查詢"],
}
RLABEL={"student":"學員","coach":"教練","admin":"管理者"}
RBADGE={"student":"role-badge-student","coach":"role-badge-coach","admin":"role-badge-admin"}

def sidebar():
    role=st.session_state.get("role",""); name=st.session_state.get("profile_name","")
    with st.sidebar:
        st.markdown("## 🏓 Ping-Pong Academy"); st.divider()
        badge = RBADGE.get(role, "")
        label = RLABEL.get(role, "")
        st.markdown(f"**{name}**　<span class='{badge}'>{label}</span>", unsafe_allow_html=True)
        st.markdown(f"<small style='color:#888;'>帳號：{st.session_state.get('username','')}</small>",
                    unsafe_allow_html=True)
        st.divider()
        sel = st.radio("功能選單", MENUS.get(role,[]), label_visibility="collapsed")
        st.divider()
        if st.button("🚪 登出", use_container_width=True): logout()
        st.markdown("---\n<small>📢 本系統供桌球教室內部使用。</small>",unsafe_allow_html=True)
    return sel


# ══════════════════════════════════════════════════════════════
# 👤  學員功能
# ══════════════════════════════════════════════════════════════

def page_my_courses():
    st.markdown('<div class="page-title">📚 我的課程</div>',unsafe_allow_html=True); st.divider()
    sid=st.session_state.get("profile_id")
    with get_conn() as conn:
        df=pd.read_sql_query("""
            SELECT COALESCE(c.course_code,'—') AS 課程ID, c.course_type AS 課程類型,
                   c.schedule_day AS 星期, c.schedule_time AS 上課時間,
                   c.duration AS 時長_分鐘, t.name AS 桌次,
                   co.name AS 教練, e.fee AS 費用_元
            FROM Enrollments e
            JOIN Courses c  ON e.course_id=c.id
            JOIN Coaches co ON c.coach_id=co.id
            JOIN Tables  t  ON c.table_id=t.id
            WHERE e.student_id=? ORDER BY c.schedule_day, c.schedule_time
        """,conn,params=(sid,))
    if df.empty: st.info("目前尚未報名任何課程，請聯繫管理者報名。"); return
    c1,c2,c3=st.columns(3)
    c1.metric("已報名課程數",len(df))
    c2.metric("每月費用合計",f"NT$ {df['費用_元'].sum():,.0f}")
    c3.metric("平均課程時長",f"{df['時長_分鐘'].mean():.0f} 分鐘")
    st.divider(); st.dataframe(df,use_container_width=True,height=320)


def page_leave_request():
    st.markdown('<div class="page-title">🙏 請假申請</div>',unsafe_allow_html=True); st.divider()
    sid=st.session_state.get("profile_id")
    with get_conn() as conn:
        courses=pd.read_sql_query("""
            SELECT c.id, c.schedule_day,
                   COALESCE(c.course_code,'—')||' '||c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label
            FROM Enrollments e JOIN Courses c ON e.course_id=c.id WHERE e.student_id=?
        """,conn,params=(sid,))
    if courses.empty: st.warning("您尚未報名任何課程，無法申請請假。"); return
    cmap=dict(zip(courses["label"],courses["id"]))
    dmap=dict(zip(courses["id"],courses["schedule_day"]))
    st.markdown('<div class="section-title">📝 申請請假</div>',unsafe_allow_html=True)
    with st.form("leave_form"):
        sel   =st.selectbox("選擇課程",list(cmap.keys()))
        ldate =st.date_input("請假日期",min_value=date.today())
        reason=st.text_area("請假原因（選填）",height=80)
        submit=st.form_submit_button("📨 送出請假申請",type="primary")
    if submit:
        cid=cmap[sel]
        if ldate.weekday()!=WD.get(dmap[cid],-1):
            wd=["一","二","三","四","五","六","日"]
            st.warning(f"所選日期（{wd[ldate.weekday()]}）非該課程上課日（{dmap[cid]}），確定已送出。")
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO LeaveRequests(student_id,course_id,leave_date,reason,status,created_at)"
                    " VALUES(?,?,?,?,'pending',?)",
                    (sid,cid,ldate.isoformat(),reason,datetime.now().isoformat()))
                conn.commit()
            st.success("✅ 請假申請已送出，等待教練審核中。")
        except Exception as e: st.error(f"申請失敗：{e}")
    st.divider()
    st.markdown('<div class="section-title">📋 歷史請假紀錄</div>',unsafe_allow_html=True)
    with get_conn() as conn:
        hist=pd.read_sql_query("""
            SELECT lr.leave_date AS 請假日期, c.course_type||' '||c.schedule_day AS 課程,
                   lr.reason AS 原因,
                   CASE lr.status WHEN 'pending' THEN '⏳ 審核中'
                     WHEN 'approved' THEN '✅ 已核准' WHEN 'rejected' THEN '❌ 已拒絕' END AS 狀態,
                   COALESCE(lr.reject_reason,'') AS 駁回原因, lr.created_at AS 申請時間
            FROM LeaveRequests lr JOIN Courses c ON lr.course_id=c.id
            WHERE lr.student_id=? ORDER BY lr.leave_date DESC
        """,conn,params=(sid,))
    if hist.empty: st.info("尚無請假紀錄。")
    else: st.dataframe(hist,use_container_width=True,height=260)
    st.divider()
    st.markdown('<div class="section-title">🔄 待補課紀錄</div>',unsafe_allow_html=True)
    with get_conn() as conn:
        makeup=pd.read_sql_query("""
            SELECT cs.session_date AS 課堂日期, c.course_type||' '||c.schedule_day AS 課程,
                   lr.leave_date AS 請假日期
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses c ON cs.course_id=c.id
            JOIN LeaveRequests lr ON lr.student_id=a.student_id AND lr.course_id=cs.course_id
                                  AND lr.leave_date=cs.session_date AND lr.status='approved'
            WHERE a.student_id=? AND a.status='leave' ORDER BY cs.session_date DESC
        """,conn,params=(sid,))
    if makeup.empty: st.info("目前無待補課紀錄。")
    else:
        st.dataframe(makeup,use_container_width=True,height=200)
        st.caption("補課安排請線下與教練協調。")


def page_payment_status():
    st.markdown('<div class="page-title">💳 繳費狀況</div>',unsafe_allow_html=True); st.divider()
    sid=st.session_state.get("profile_id")
    with get_conn() as conn:
        df=pd.read_sql_query("""
            SELECT c.course_type||' '||c.schedule_day AS 課程,
                   p.period AS 期別, p.amount AS 金額, p.created_at AS 建立時間,
                   COALESCE(p.paid_date,'—') AS 繳費日期,
                   COALESCE(p.paid_time,'—') AS 繳費時間, p.is_paid
            FROM Payments p JOIN Courses c ON p.course_id=c.id
            WHERE p.student_id=? ORDER BY p.period DESC
        """,conn,params=(sid,))
    if df.empty: st.info("目前無繳費紀錄。"); return
    paid=df[df["is_paid"]==1]["金額"].sum(); unpaid=df[df["is_paid"]==0]["金額"].sum()
    rate=(df["is_paid"]==1).sum()/len(df)*100 if len(df) else 0
    c1,c2,c3=st.columns(3)
    c1.metric("已繳總額",f"NT$ {paid:,.0f}")
    c2.metric("未繳總額",f"NT$ {unpaid:,.0f}")
    c3.metric("繳費完成率",f"{rate:.1f}%")
    st.divider()
    df["狀態"]=df["is_paid"].apply(lambda x:"✅ 已繳" if x else "❌ 未繳")
    df["金額"]=df["金額"].apply(lambda x:f"NT$ {x:,.0f}")
    st.dataframe(df[["課程","期別","金額","建立時間","繳費日期","繳費時間","狀態"]],
                 use_container_width=True,height=350)


def page_attendance_record():
    st.markdown('<div class="page-title">📋 出勤紀錄</div>',unsafe_allow_html=True); st.divider()
    sid=st.session_state.get("profile_id")
    with get_conn() as conn:
        df=pd.read_sql_query("""
            SELECT cs.session_date AS 日期, c.course_type||' '||c.schedule_day AS 課程,
                   CASE a.status WHEN 'present' THEN '✅ 出席'
                     WHEN 'absent' THEN '❌ 缺席' WHEN 'leave' THEN '🟡 請假' END AS 狀態,
                   a.status AS _st
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses c ON cs.course_id=c.id
            WHERE a.student_id=? ORDER BY cs.session_date DESC
        """,conn,params=(sid,))
    if df.empty: st.info("目前尚無出勤紀錄。"); return
    pre=(df["_st"]=="present").sum(); abs_=(df["_st"]=="absent").sum()
    lv=(df["_st"]=="leave").sum(); tot=len(df)
    c1,c2,c3,c4=st.columns(4)
    c1.metric("出席次數",pre); c2.metric("缺席次數",abs_)
    c3.metric("請假次數",lv); c4.metric("出席率",f"{pre/tot*100:.1f}%" if tot else "0%")
    st.divider(); st.dataframe(df.drop(columns=["_st"]),use_container_width=True,height=320)
    st.markdown('<div class="section-title">📊 近 3 個月出勤統計</div>',unsafe_allow_html=True)
    with get_conn() as conn:
        ch=pd.read_sql_query("""
            SELECT substr(cs.session_date,1,7) AS 月份, a.status, COUNT(*) AS 次數
            FROM Attendance a JOIN ClassSessions cs ON a.session_id=cs.id
            WHERE a.student_id=? AND cs.session_date>=date('now','-3 months')
            GROUP BY 月份, a.status
        """,conn,params=(sid,))
    if not ch.empty:
        pv=ch.pivot_table(index="月份",columns="status",values="次數",fill_value=0)
        cm={"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
        lm={"present":"出席","absent":"缺席","leave":"請假"}
        fig=go.Figure()
        for col in pv.columns:
            fig.add_trace(go.Bar(name=lm.get(col,col),x=pv.index,y=pv[col],marker_color=cm.get(col,"#999")))
        fig.update_layout(barmode="group",height=300,margin=dict(l=0,r=0,t=20,b=0),legend=dict(orientation="h"))
        st.plotly_chart(fig,use_container_width=True)


# ══════════════════════════════════════════════════════════════
# 🏫  教練功能
# ══════════════════════════════════════════════════════════════

def page_coach_profile():
    st.markdown('<div class="page-title">👤 個人簡介編輯</div>',unsafe_allow_html=True); st.divider()
    uid=st.session_state.get("user_id")
    with get_conn() as conn:
        coach=conn.execute("SELECT * FROM Coaches WHERE user_id=?", (uid,)).fetchone()
    if not coach: st.error("找不到教練資料，請聯繫管理者。"); return
    c1,c2=st.columns(2)
    c1.info(f"**姓名：** {coach['name']}\n\n**電話：** {coach['phone']}\n\n**專長：** {coach['specialty']}")
    c2.info(f"**個人簡介：**\n\n{coach['bio']}")
    st.divider()
    st.markdown('<div class="section-title">✏️ 編輯資料</div>',unsafe_allow_html=True)
    with st.form("coach_profile_form"):
        name     =st.text_input("姓名",value=coach["name"])
        phone    =st.text_input("聯絡電話",value=coach["phone"])
        bio      =st.text_area("個人簡介 / 教學經歷",value=coach["bio"],height=120)
        specialty=st.text_input("專長",value=coach["specialty"])
        saved    =st.form_submit_button("💾 儲存變更",type="primary")
    if saved:
        if not name.strip(): st.error("姓名不可為空。"); return
        with get_conn() as conn:
            conn.execute("UPDATE Coaches SET name=?,phone=?,bio=?,specialty=? WHERE user_id=?",
                         (name,phone,bio,specialty,uid)); conn.commit()
        st.session_state["profile_name"]=name; st.success("✅ 個人簡介已更新！"); st.rerun()


def page_coach_students():
    st.markdown('<div class="page-title">👥 課程學員名單</div>',unsafe_allow_html=True); st.divider()
    cid_c=st.session_state.get("profile_id")
    with get_conn() as conn:
        courses=pd.read_sql_query("""
            SELECT id, COALESCE(course_code,'—')||' '||course_type||' '||schedule_day||' '||schedule_time AS label
            FROM Courses WHERE coach_id=? ORDER BY schedule_day, schedule_time
        """,conn,params=(cid_c,))
    if courses.empty: st.info("您目前沒有負責的課程。"); return
    cmap=dict(zip(courses["label"],courses["id"]))
    cid=cmap[st.selectbox("選擇課程",list(cmap.keys()))]
    with get_conn() as conn:
        df=pd.read_sql_query("""
            SELECT s.name AS 學員姓名, s.phone AS 電話, s.email AS Email,
                   e.fee AS 費用_元, e.enrolled_date AS 報名日期
            FROM Enrollments e JOIN Students s ON e.student_id=s.id
            WHERE e.course_id=? ORDER BY s.name
        """,conn,params=(cid,))
    st.metric("報名人數",len(df)); st.divider()
    if df.empty: st.info("此課程尚無學員報名。")
    else: st.dataframe(df,use_container_width=True,height=350)


def page_coach_attendance():
    st.markdown('<div class="page-title">✅ 課堂點名</div>',unsafe_allow_html=True); st.divider()
    cid_c=st.session_state.get("profile_id")
    with get_conn() as conn:
        courses=pd.read_sql_query("""
            SELECT c.id, c.schedule_day, c.schedule_time, c.table_id,
                   COALESCE(c.course_code,'—')||' '||c.course_type||' '||c.schedule_day||' '||c.schedule_time AS label
            FROM Courses c WHERE c.coach_id=? ORDER BY c.schedule_day, c.schedule_time
        """,conn,params=(cid_c,))
    if courses.empty: st.info("您目前沒有負責的課程。"); return
    cmap=dict(zip(courses["label"],courses["id"]))
    cinfo=courses.set_index("id")
    c1,c2=st.columns(2)
    sel=c1.selectbox("選擇課程",list(cmap.keys()))
    sess_date=c2.date_input("上課日期",value=date.today())
    cid=cmap[sel]; row=cinfo.loc[cid]
    if sess_date.weekday()!=WD.get(str(row["schedule_day"]),-1):
        wd=["一","二","三","四","五","六","日"]
        st.warning(f"⚠️ 所選日期（{wd[sess_date.weekday()]}）與課程上課日（{row['schedule_day']}）不符，請確認。")
    with get_conn() as conn:
        stus=pd.read_sql_query("""
            SELECT s.id, s.name FROM Enrollments e JOIN Students s ON e.student_id=s.id
            WHERE e.course_id=? ORDER BY s.name
        """,conn,params=(cid,))
    if stus.empty: st.warning("此課程尚無學員，無法點名。"); return
    with get_conn() as conn:
        sess=conn.execute("SELECT id FROM ClassSessions WHERE course_id=? AND session_date=?",
                          (cid,sess_date.isoformat())).fetchone()
        if not sess:
            cur=conn.execute(
                "INSERT INTO ClassSessions(course_id,session_date,session_time,coach_id,table_id,created_by)"
                " VALUES(?,?,?,?,?,'coach_點名')",
                (cid,sess_date.isoformat(),str(row["schedule_time"]),cid_c,int(row["table_id"])))
            conn.commit(); sess_id=cur.lastrowid
        else:
            sess_id=sess["id"]
        existing=conn.execute("SELECT student_id,status FROM Attendance WHERE session_id=?",
                              (sess_id,)).fetchall()
        approved=set(r["student_id"] for r in conn.execute("""
            SELECT student_id FROM LeaveRequests
            WHERE course_id=? AND leave_date=? AND status='approved'
        """,(cid,sess_date.isoformat())).fetchall())
    em={r["student_id"]:r["status"] for r in existing}
    opts=["出席","缺席","請假"]; rev={"出席":"present","缺席":"absent","請假":"leave"}
    fwd={"present":"出席","absent":"缺席","leave":"請假"}
    st.markdown(f'<div class="section-title">👥 點名列表（共 {len(stus)} 位學員）</div>',unsafe_allow_html=True)
    sels={}
    for _,stu in stus.iterrows():
        if stu["id"] in approved: dflt,sfx="請假","　🏷️ 已核准請假"
        else: dflt,sfx=fwd.get(em.get(stu["id"],"present"),"出席"),""
        sels[stu["id"]]=st.radio(f"**{stu['name']}**{sfx}",opts,
                                  index=opts.index(dflt),horizontal=True,
                                  key=f"att_{sess_id}_{stu['id']}")
    if st.button("📝 送出點名結果",type="primary",use_container_width=True):
        with get_conn() as conn:
            for sid,sl in sels.items():
                conn.execute("""
                    INSERT INTO Attendance(session_id,student_id,status) VALUES(?,?,?)
                    ON CONFLICT(session_id,student_id) DO UPDATE SET status=excluded.status
                """,(sess_id,sid,rev[sl]))
            conn.commit()
        p=sum(1 for v in sels.values() if v=="出席"); a=sum(1 for v in sels.values() if v=="缺席")
        lv=sum(1 for v in sels.values() if v=="請假")
        # ✅ 點名完成：顯示通知後自動返回主畫面
        st.session_state["att_done_msg"] = (
            f"✅ 點名完成！課程：{sel}　日期：{sess_date.isoformat()}　"
            f"出席：{p} 人　缺席：{a} 人　請假：{lv} 人"
        )
        st.rerun()

    # 顯示上一次點名完成通知（rerun 後在頁面頂部顯示）
    if "att_done_msg" in st.session_state:
        st.success(st.session_state.pop("att_done_msg"))


def page_coach_leave_review():
    st.markdown('<div class="page-title">🙏 請假審核</div>',unsafe_allow_html=True); st.divider()
    cid_c=st.session_state.get("profile_id"); uid=st.session_state.get("user_id")
    st.markdown('<div class="section-title">⏳ 待審核申請</div>',unsafe_allow_html=True)
    with get_conn() as conn:
        pending=pd.read_sql_query("""
            SELECT lr.id, s.name AS 學員, c.course_type||' '||c.schedule_day AS 課程,
                   lr.leave_date AS 請假日期, lr.reason AS 原因, lr.created_at AS 申請時間
            FROM LeaveRequests lr JOIN Students s ON lr.student_id=s.id
            JOIN Courses c ON lr.course_id=c.id
            WHERE lr.status='pending' AND c.coach_id=? ORDER BY lr.leave_date
        """,conn,params=(cid_c,))
    if pending.empty: st.info("目前無待審核的請假申請。")
    else:
        for _,row in pending.iterrows():
            with st.expander(f"⏳ {row['學員']} ｜ {row['課程']} ｜ 請假日：{row['請假日期']}"):
                st.write(f"**申請時間：** {row['申請時間']}　**原因：** {row['原因'] or '（未填寫）'}")
                col1,col2=st.columns(2)
                with col1:
                    if st.button("✅ 核准",key=f"ap_{row['id']}",type="primary"):
                        with get_conn() as conn:
                            conn.execute(
                                "UPDATE LeaveRequests SET status='approved',reviewed_by=?,reviewed_at=? WHERE id=?",
                                (uid,datetime.now().isoformat(),int(row["id"]))); conn.commit()
                        st.success("已核准！"); st.rerun()
                with col2:
                    rr=st.text_input("駁回原因",key=f"rr_{row['id']}",placeholder="請填寫駁回原因")
                    if st.button("❌ 駁回",key=f"rj_{row['id']}"):
                        if not rr.strip(): st.warning("請填寫駁回原因後再送出。")
                        else:
                            with get_conn() as conn:
                                conn.execute("""
                                    UPDATE LeaveRequests
                                    SET status='rejected',reviewed_by=?,reviewed_at=?,reject_reason=?
                                    WHERE id=?
                                """,(uid,datetime.now().isoformat(),rr,int(row["id"]))); conn.commit()
                            st.success("已駁回。"); st.rerun()
    st.divider()
    st.markdown('<div class="section-title">📋 歷史審核紀錄</div>',unsafe_allow_html=True)
    filt=st.selectbox("篩選狀態",["全部","已核准","已駁回"],key="lrv_filt")
    fval={"全部":None,"已核准":"approved","已駁回":"rejected"}[filt]
    q="""SELECT s.name AS 學員, c.course_type||' '||c.schedule_day AS 課程,
               lr.leave_date AS 請假日期, lr.reason AS 原因,
               CASE lr.status WHEN 'approved' THEN '✅ 已核准' WHEN 'rejected' THEN '❌ 已駁回' END AS 狀態,
               COALESCE(lr.reject_reason,'') AS 駁回原因, lr.reviewed_at AS 審核時間
         FROM LeaveRequests lr JOIN Students s ON lr.student_id=s.id
         JOIN Courses c ON lr.course_id=c.id
         WHERE c.coach_id=? AND lr.status!='pending'"""
    params=[cid_c]
    if fval: q+=" AND lr.status=?"; params.append(fval)
    q+=" ORDER BY lr.reviewed_at DESC"
    with get_conn() as conn:
        hist=pd.read_sql_query(q,conn,params=params)
    if hist.empty: st.info("尚無歷史審核紀錄。")
    else: st.dataframe(hist,use_container_width=True,height=300)


# ══════════════════════════════════════════════════════════════
# 🔧  管理者功能
# ══════════════════════════════════════════════════════════════

def _del_course_batch(del_ids):
    """批次刪除課程及所有關聯資料（正確順序避免外鍵衝突）"""
    with get_conn() as conn:
        for cid in del_ids:
            # 1. 先刪出勤紀錄（透過場次）
            sess=conn.execute("SELECT id FROM ClassSessions WHERE course_id=?",(cid,)).fetchall()
            for s in sess:
                conn.execute("DELETE FROM Attendance WHERE session_id=?",(s["id"],))
            # 2. 刪繳費紀錄
            conn.execute("DELETE FROM Payments WHERE course_id=?",(cid,))
            # 3. 刪請假申請
            conn.execute("DELETE FROM LeaveRequests WHERE course_id=?",(cid,))
            # 4. 刪上課場次
            conn.execute("DELETE FROM ClassSessions WHERE course_id=?",(cid,))
            # 5. 刪報名紀錄
            conn.execute("DELETE FROM Enrollments WHERE course_id=?",(cid,))
            # 6. 最後刪課程
            conn.execute("DELETE FROM Courses WHERE id=?",(cid,))
        conn.commit()


def page_admin_courses():
    st.markdown('<div class="page-title">📅 課程管理</div>',unsafe_allow_html=True); st.divider()
    t1,t2,t3,t4=st.tabs(["📋 課程總表","➕ 新增課程","🎓 學員報名管理","🏓 桌次視覺化"])

    # ── Tab 1：課程總表 + 全選 + 三層防呆批次刪除 ────────────
    with t1:
        with get_conn() as conn:
            df=pd.read_sql_query("""
                SELECT c.id AS _id, COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, co.name AS 教練,
                       c.schedule_day AS 星期, c.schedule_time AS 開始時間,
                       c.duration AS 時長_分鐘, t.name AS 桌次, COUNT(e.id) AS 報名人數
                FROM Courses c
                JOIN Coaches co ON c.coach_id=co.id
                JOIN Tables  t  ON c.table_id=t.id
                LEFT JOIN Enrollments e ON e.course_id=c.id
                GROUP BY c.id ORDER BY c.schedule_day, c.schedule_time
            """,conn)
        if df.empty: st.info("目前無課程資料。")
        else:
            df["結束時間"]=df.apply(lambda r:end_t(str(r["開始時間"]),int(r["時長_分鐘"])),axis=1)
            st.dataframe(
                df[["課程ID","課程類型","教練","星期","開始時間","結束時間","時長_分鐘","桌次","報名人數"]],
                use_container_width=True,height=280)
            st.divider()
            st.markdown('<div class="section-title">🗑️ 批次刪除課程</div>',unsafe_allow_html=True)
            st.caption("勾選欲刪除的課程，通過三層確認後執行（不可復原）。")

            all_ids=df["_id"].tolist()
            cur_chks=[st.session_state.get(f"chk_{i}",False) for i in all_ids]
            all_chked=all(cur_chks) and len(all_ids)>0

            sel_all=st.checkbox(f"☑️ 全選 / 取消全選（共 {len(all_ids)} 筆）",
                                value=all_chked,key="sel_all_c")
            if sel_all!=all_chked:
                for i in all_ids: st.session_state[f"chk_{i}"]=sel_all

            sel_ids=[]
            for _,row in df.iterrows():
                lbl=(f"{row['課程ID']} — {row['課程類型']} "
                     f"{row['星期']} {row['開始時間']}～{row['結束時間']} "
                     f"（{row['教練']} / {row['桌次']}）")
                if st.checkbox(lbl,key=f"chk_{row['_id']}"):
                    sel_ids.append(int(row["_id"]))
            st.markdown("---")

            if st.button("🔍 查看關聯資料並確認刪除",type="primary"):
                if not sel_ids: st.warning("⚠️ 請至少選取一筆課程後再執行。")
                else: st.session_state["pending_del"]=sel_ids

            if "pending_del" in st.session_state:
                dids=st.session_state["pending_del"]
                with get_conn() as conn:
                    te=sum(conn.execute("SELECT COUNT(*) FROM Enrollments WHERE course_id=?",(c,)).fetchone()[0] for c in dids)
                    ta=sum(conn.execute("SELECT COUNT(*) FROM Attendance a JOIN ClassSessions cs ON a.session_id=cs.id WHERE cs.course_id=?",(c,)).fetchone()[0] for c in dids)
                    tu=sum(conn.execute("SELECT COUNT(*) FROM Payments WHERE course_id=? AND is_paid=0",(c,)).fetchone()[0] for c in dids)
                st.warning(
                    f"⚠️ **刪除警告** — 已選 **{len(dids)}** 筆課程，關聯資料：\n\n"
                    f"- 合計報名人數：**{te}** 筆\n"
                    f"- 合計出勤紀錄：**{ta}** 筆\n"
                    f"- 合計未繳費紀錄：**{tu}** 筆\n\n"
                    "確認後將**永久刪除**所有關聯紀錄，此操作**無法還原**。")
                # 第二層：核取方塊
                l2=st.checkbox("✅ 我已了解刪除後關聯資料將一併清除，且此操作無法復原",key="l2_chk")
                # 第三層：文字輸入
                l3i=st.text_input("🔐 請輸入「確認刪除」以解鎖執行按鈕",placeholder="確認刪除",key="l3_txt")
                l3ok=(l3i.strip()=="確認刪除")
                if not l2: st.caption("👆 請先勾選上方確認核取方塊（第二層）")
                elif not l3ok: st.caption("👆 請輸入「確認刪除」解鎖按鈕（第三層）")
                ca,cb=st.columns(2)
                with ca:
                    if st.button("🗑️ 執行批次刪除",key="do_del",
                                 disabled=not(l2 and l3ok),type="primary"):
                        _del_course_batch(dids)
                        del st.session_state["pending_del"]
                        for i in all_ids:
                            if f"chk_{i}" in st.session_state: del st.session_state[f"chk_{i}"]
                        st.success(f"✅ 已成功刪除 {len(dids)} 筆課程。"); st.rerun()
                with cb:
                    if st.button("❌ 取消",key="cancel_del"):
                        del st.session_state["pending_del"]; st.rerun()

    # ── Tab 2：新增課程 ─────────────────────────────────────
    with t2:
        with get_conn() as conn:
            coaches=pd.read_sql_query("SELECT id,name FROM Coaches ORDER BY name",conn)
        if coaches.empty: st.warning("尚無教練資料，請先新增教練帳號。")
        else:
            cmap=dict(zip(coaches["name"],coaches["id"]))
            with st.form("add_course"):
                ca,cb=st.columns(2)
                with ca:
                    ctype=st.selectbox("課程類型",["團體班","個人班","寒假班","暑假班"])
                    csel =st.selectbox("選擇教練",list(cmap.keys()))
                    day  =st.selectbox("上課星期",["週一","週二","週三","週四","週五","週六","週日"])
                    tv   =st.time_input("上課時間",value=datetime.strptime("09:00","%H:%M").time())
                with cb:
                    dur  =st.selectbox("課程時長（分鐘）",[60,90,120])
                    tbl  =st.selectbox("使用桌次",list(range(1,9)))
                    ts   =tv.strftime("%H:%M")
                    st.markdown("**課程ID 預覽**"); st.code(make_code(day,tbl,ts,dur))
                sub=st.form_submit_button("✅ 新增課程",type="primary")
            if sub:
                code=make_code(day,tbl,ts,dur)
                with get_conn() as conn:
                    if conn.execute("SELECT id FROM Courses WHERE course_code=?",(code,)).fetchone():
                        st.error(f"⚠️ 課程代號 `{code}` 已存在，請確認是否重複。")
                    else:
                        cf=check_conflict(conn,day,ts,dur,tbl)
                        if cf:
                            for c in cf:
                                st.error(f"⚠️ 桌次 {tbl} 時段衝突（{c['schedule_time']}～{end_t(c['schedule_time'],c['duration'])}），請重新選擇。")
                        else:
                            try:
                                conn.execute(
                                    "INSERT INTO Courses(course_code,course_type,coach_id,"
                                    "schedule_day,schedule_time,duration,table_id) VALUES(?,?,?,?,?,?,?)",
                                    (code,ctype,cmap[csel],day,ts,dur,tbl)); conn.commit()
                                st.success(f"✅ 課程新增成功！課程ID：`{code}`"); st.rerun()
                            except Exception as e: st.error(f"新增失敗：{e}")

    # ── Tab 3：學員報名管理 ─────────────────────────────────
    with t3:
        with get_conn() as conn:
            acs=pd.read_sql_query("""
                SELECT c.id, c.schedule_day, c.schedule_time, c.duration,
                       COALESCE(c.course_code,'—') AS code, co.name AS cname
                FROM Courses c JOIN Coaches co ON c.coach_id=co.id
                ORDER BY c.schedule_day, c.schedule_time
            """,conn)
            astus=pd.read_sql_query("SELECT id,name FROM Students ORDER BY name",conn)
        if acs.empty or astus.empty: st.info("請先建立課程與學員資料。")
        else:
            def clabel(r):
                return f"{r['code']}_{r['cname']}_{r['schedule_day']} {r['schedule_time']}～{end_t(str(r['schedule_time']),int(r['duration']))}"
            acs["label"]=acs.apply(clabel,axis=1)
            cmap2=dict(zip(acs["label"],acs["id"]))
            smap=dict(zip(astus["name"],astus["id"]))
            sel_c=st.selectbox("選擇課程",list(cmap2.keys()),key="enr_c")
            cid_e=cmap2[sel_c]
            with get_conn() as conn:
                enrolled=pd.read_sql_query("""
                    SELECT s.id, s.name, e.fee AS 費用_元
                    FROM Enrollments e JOIN Students s ON e.student_id=s.id
                    WHERE e.course_id=? ORDER BY s.name
                """,conn,params=(cid_e,))
            eids=enrolled["id"].tolist()
            notenr=[s for s in astus["name"] if smap[s] not in eids]
            ca,cb=st.columns(2)
            with ca:
                st.markdown(f"**已報名學員（{len(enrolled)} 人）**")
                if enrolled.empty: st.info("此課程尚無學員報名。")
                else:
                    for _,er in enrolled.iterrows():
                        r1,r2,r3=st.columns([3,2,1])
                        r1.write(er["name"]); r2.write(f"NT$ {er['費用_元']:,.0f}")
                        if r3.button("移除",key=f"rm_{er['id']}_{cid_e}"):
                            with get_conn() as conn:
                                # ✅ 正確移除順序（避免外鍵衝突）
                                # 1. 刪出勤紀錄
                                sess=conn.execute("SELECT id FROM ClassSessions WHERE course_id=?",(cid_e,)).fetchall()
                                for s in sess:
                                    conn.execute("DELETE FROM Attendance WHERE session_id=? AND student_id=?",(s["id"],er["id"]))
                                # 2. 刪繳費紀錄
                                conn.execute("DELETE FROM Payments WHERE student_id=? AND course_id=?",(er["id"],cid_e))
                                # 3. 刪請假申請
                                conn.execute("DELETE FROM LeaveRequests WHERE student_id=? AND course_id=?",(er["id"],cid_e))
                                # 4. 最後刪報名紀錄
                                conn.execute("DELETE FROM Enrollments WHERE student_id=? AND course_id=?",(er["id"],cid_e))
                                conn.commit()
                            st.success(f"✅ 已移除 {er['name']} 的報名紀錄。"); st.rerun()
            with cb:
                st.markdown("**新增學員報名**")
                if notenr:
                    add_s=st.selectbox("選擇學員",notenr,key="add_s")
                    add_f=st.number_input("費用（元）",min_value=0,value=2000,step=100,key="add_f")
                    if st.button("➕ 加入報名",type="primary"):
                        try:
                            now=datetime.now().isoformat(); per=date.today().strftime("%Y-%m")
                            with get_conn() as conn:
                                conn.execute(
                                    "INSERT INTO Enrollments(student_id,course_id,fee,enrolled_date) VALUES(?,?,?,?)",
                                    (smap[add_s],cid_e,add_f,date.today().isoformat()))
                                conn.execute(
                                    "INSERT INTO Payments(student_id,course_id,amount,period,created_at) VALUES(?,?,?,?,?)",
                                    (smap[add_s],cid_e,add_f,per,now))
                                conn.commit()
                            st.success(f"✅ {add_s} 已加入課程，費用 NT$ {add_f:,}！"); st.rerun()
                        except Exception as e: st.error(f"報名失敗：{e}")
                else: st.info("所有學員皆已報名此課程。")

            # ── 新功能：人工輸入課程堂數 + 推估預計上課日期 ────────────────
            st.divider()
            st.markdown('<div class="section-title">📅 預計上課日期推估</div>',unsafe_allow_html=True)
            st.caption("依課程排定星期，從指定起始日往後推算預計上課日期。")

            # 取得所選課程的上課星期
            with get_conn() as conn:
                crs_info = conn.execute(
                    "SELECT schedule_day, schedule_time FROM Courses WHERE id=?", (cid_e,)
                ).fetchone()

            if crs_info:
                wd_label = str(crs_info["schedule_day"])
                wd_time  = str(crs_info["schedule_time"])
                target_wd = WD.get(wd_label, 0)  # 0=週一

                col_a, col_b = st.columns(2)
                with col_a:
                    total_lessons = st.number_input(
                        "課程總堂數",
                        min_value=1, max_value=200, value=12, step=1,
                        key="est_lessons",
                        help="輸入這堂課共有幾堂，系統將自動推算每堂預計日期"
                    )
                with col_b:
                    start_from = st.date_input(
                        "起始日期（從哪天開始算）",
                        value=date.today(),
                        key="est_start",
                        help="通常填報名日或第一堂課日期"
                    )

                if st.button("🔍 推算預計上課日期", key="calc_schedule"):
                    # 計算從 start_from 起，找到 total_lessons 個對應星期的日期
                    result_dates = []
                    cursor_date = start_from
                    while len(result_dates) < total_lessons:
                        if cursor_date.weekday() == target_wd:
                            result_dates.append(cursor_date)
                        cursor_date += timedelta(days=1)

                    # 組成 DataFrame 顯示
                    df_sched = pd.DataFrame({
                        "堂次": range(1, len(result_dates)+1),
                        "預計上課日期": [d.strftime("%Y-%m-%d") for d in result_dates],
                        "星期": [["一","二","三","四","五","六","日"][d.weekday()] for d in result_dates],
                        "上課時間": wd_time,
                    })
                    st.dataframe(df_sched, use_container_width=True, height=300)
                    st.caption(f"共 {total_lessons} 堂，課程星期：{wd_label}，每週上課時間：{wd_time}")
                    # 儲存推算結果供下載
                    st.download_button(
                        "⬇️ 下載預計上課日期表",
                        data=df_sched.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"預計上課日期_{cid_e}_{start_from}.csv",
                        mime="text/csv"
                    )

    # ── Tab 4：桌次視覺化甘特圖 ────────────────────────────
    with t4:
        st.markdown('<div class="section-title">🏓 選定星期的桌次甘特圖</div>',unsafe_allow_html=True)
        sel_d=st.selectbox("選擇星期",["週一","週二","週三","週四","週五","週六","週日"],key="tviz_d")
        with get_conn() as conn:
            dc=pd.read_sql_query("""
                SELECT c.id, c.table_id, c.schedule_time, c.duration,
                       c.course_type, co.name AS cname,
                       COALESCE(c.course_code,'—') AS code, COUNT(e.id) AS ecnt
                FROM Courses c JOIN Coaches co ON c.coach_id=co.id
                LEFT JOIN Enrollments e ON e.course_id=c.id
                WHERE c.schedule_day=? GROUP BY c.id
            """,conn,params=(sel_d,))
        fig=go.Figure()
        for _,tc in dc.iterrows():
            sm=t2m(str(tc["schedule_time"])); em=sm+int(tc["duration"])
            bt=(f"{tc['course_type']}<br>{tc['cname']}" if int(tc["duration"])>=90 else tc["cname"])
            fig.add_trace(go.Bar(
                x=[int(tc["duration"])/60], y=[f"桌{tc['table_id']}"], base=[sm/60],
                orientation="h", marker_color="#FF6B35",
                text=bt, textposition="inside", insidetextanchor="middle",
                textfont=dict(color="white",size=11),
                hovertemplate=(f"<b>桌{tc['table_id']}</b><br>課程ID：{tc['code']}<br>"
                               f"類型：{tc['course_type']}<br>教練：{tc['cname']}<br>"
                               f"時段：{tc['schedule_time']}～{em//60:02d}:{em%60:02d}<br>"
                               f"報名人數：{tc['ecnt']}<br><extra></extra>"),
                showlegend=False))
        fig.update_layout(
            barmode="overlay", height=400,
            xaxis=dict(title="時間",range=[8,22],tickvals=list(range(8,23)),
                       ticktext=[f"{h:02d}:00" for h in range(8,23)]),
            yaxis=dict(title="桌次",categoryorder="array",
                       categoryarray=[f"桌{i}" for i in range(8,0,-1)]),
            margin=dict(l=40,r=20,t=20,b=40), plot_bgcolor="#F5F5F5")
        if dc.empty: st.info("此星期無排定課程。")
        else: st.plotly_chart(fig,use_container_width=True)


def page_admin_attendance():
    st.markdown('<div class="page-title">📊 出勤總表</div>',unsafe_allow_html=True); st.divider()
    ca,cb=st.columns(2)
    sd=ca.date_input("起始日期",value=date.today()-timedelta(days=30))
    ed=cb.date_input("結束日期",value=date.today())
    if sd>ed: st.error("起始日期不可晚於結束日期。"); return
    with get_conn() as conn:
        df=pd.read_sql_query("""
            SELECT cs.session_date AS 日期, c.course_type||' '||c.schedule_day AS 課程,
                   co.name AS 教練, s.name AS 學員,
                   CASE a.status WHEN 'present' THEN '✅ 出席'
                     WHEN 'absent' THEN '❌ 缺席' WHEN 'leave' THEN '🟡 請假' END AS 狀態,
                   a.status AS _st
            FROM Attendance a
            JOIN ClassSessions cs ON a.session_id=cs.id
            JOIN Courses  c  ON cs.course_id=c.id
            JOIN Coaches  co ON cs.coach_id=co.id
            JOIN Students s  ON a.student_id=s.id
            WHERE cs.session_date BETWEEN ? AND ? ORDER BY cs.session_date DESC
        """,conn,params=(sd.isoformat(),ed.isoformat()))
    if df.empty: st.info("此區間無出勤紀錄。"); return
    tot=len(df); pre=(df["_st"]=="present").sum(); abs_=(df["_st"]=="absent").sum()
    c1,c2,c3,c4=st.columns(4)
    c1.metric("總紀錄筆數",tot); c2.metric("出席人次",pre)
    c3.metric("缺席人次",abs_); c4.metric("整體出席率",f"{pre/tot*100:.1f}%" if tot else "0%")
    st.divider()
    disp=df.drop(columns=["_st"])
    st.dataframe(disp,use_container_width=True,height=380)
    st.download_button("⬇️ 匯出 CSV",data=disp.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"出勤總表_{sd}_{ed}.csv",mime="text/csv")
    st.divider()
    st.markdown('<div class="section-title">📊 每日出勤統計</div>',unsafe_allow_html=True)
    dly=df.groupby(["日期","_st"]).size().reset_index(name="cnt")
    pv=dly.pivot_table(index="日期",columns="_st",values="cnt",fill_value=0)
    cm={"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
    lm={"present":"出席","absent":"缺席","leave":"請假"}
    fig=go.Figure()
    for col in pv.columns:
        fig.add_trace(go.Bar(name=lm.get(col,col),x=pv.index,y=pv[col],marker_color=cm.get(col,"#999")))
    fig.update_layout(barmode="stack",height=320,margin=dict(l=0,r=0,t=20,b=0),legend=dict(orientation="h"))
    st.plotly_chart(fig,use_container_width=True)


def page_admin_payments():
    st.markdown('<div class="page-title">💰 繳費管理</div>',unsafe_allow_html=True); st.divider()
    fopt=st.radio("篩選",["全部","未繳費","已繳費"],horizontal=True)
    fval={"全部":None,"未繳費":0,"已繳費":1}[fopt]
    q="""SELECT p.id, s.name AS 學員, c.course_type AS 課程類別,
               co.name AS 教練, c.schedule_day||' '||c.schedule_time AS 上課時間,
               p.amount AS 繳交費用, p.period AS 期別,
               COALESCE(p.paid_date,'—') AS 繳費日期,
               COALESCE(p.paid_time,'—') AS 繳費時間, p.is_paid
         FROM Payments p
         JOIN Students s  ON p.student_id=s.id
         JOIN Courses  c  ON p.course_id=c.id
         JOIN Coaches  co ON c.coach_id=co.id"""
    params=[]
    if fval is not None: q+=" WHERE p.is_paid=?"; params.append(fval)
    q+=" ORDER BY p.is_paid ASC, s.name"
    with get_conn() as conn:
        df=pd.read_sql_query(q,conn,params=params)
    if df.empty: st.info("沒有符合條件的繳費紀錄。"); return
    ta=df["繳交費用"].sum(); pa=df[df["is_paid"]==1]["繳交費用"].sum(); ua=df[df["is_paid"]==0]["繳交費用"].sum()
    c1,c2,c3=st.columns(3)
    c1.metric("總應收金額",f"NT$ {ta:,.0f}"); c2.metric("已收金額",f"NT$ {pa:,.0f}"); c3.metric("未收金額",f"NT$ {ua:,.0f}")
    st.divider()
    disp=df.copy()
    disp["狀態"]=disp["is_paid"].apply(lambda x:"✅ 已繳" if x else "❌ 未繳")
    disp["繳交費用"]=disp["繳交費用"].apply(lambda x:f"NT$ {x:,.0f}")
    st.dataframe(disp.drop(columns=["id","is_paid"]),use_container_width=True,height=300)

    # ── 標記繳費（未繳費項目）───────────────────────────────────
    unpaid=df[df["is_paid"]==0]
    if not unpaid.empty:
        st.divider()
        st.markdown('<div class="section-title">💳 標記繳費</div>',unsafe_allow_html=True)
        for _,row in unpaid.iterrows():
            with st.expander(f"❌ {row['學員']} ｜ {row['課程類別']} {row['上課時間']} ｜ {row['期別']} ｜ NT$ {row['繳交費用']:,.0f}"):
                m1,m2=st.columns(2)
                pd_=m1.date_input("繳費日期",value=date.today(),key=f"pd_{row['id']}")
                pt_=m2.time_input("繳費時間",value=datetime.now().time(),key=f"pt_{row['id']}")
                if st.button("💳 標記為已繳費",key=f"pay_{row['id']}",type="primary"):
                    with get_conn() as conn:
                        conn.execute("UPDATE Payments SET is_paid=1,paid_date=?,paid_time=? WHERE id=?",
                                     (pd_.isoformat(),pt_.strftime("%H:%M"),int(row["id"]))); conn.commit()
                    st.success("✅ 繳費狀態已更新！"); st.rerun()

    # ── 新功能：修改繳費金額與期別 ──────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">✏️ 修改繳費紀錄</div>',unsafe_allow_html=True)
    st.caption("可修改應繳金額與期別，修改後同步更新 Enrollments.fee。")
    # 重新讀取完整清單（不受篩選影響）供修改/移除
    with get_conn() as conn:
        df_all = pd.read_sql_query("""
            SELECT p.id, s.name AS 學員, c.course_type AS 課程類別,
                   c.schedule_day||' '||c.schedule_time AS 上課時間,
                   p.amount AS 繳交費用, p.period AS 期別,
                   p.student_id, p.course_id, p.is_paid
            FROM Payments p
            JOIN Students s  ON p.student_id=s.id
            JOIN Courses  c  ON p.course_id=c.id
            ORDER BY p.is_paid ASC, s.name
        """, conn)
    if not df_all.empty:
        edit_opts = {
            f"{r['學員']} ｜ {r['課程類別']} {r['上課時間']} ｜ {r['期別']} ｜ NT${r['繳交費用']:,.0f} ({'已繳' if r['is_paid'] else '未繳'})": int(r["id"])
            for _, r in df_all.iterrows()
        }
        e_sel = st.selectbox("選擇要修改的繳費紀錄", list(edit_opts.keys()), key="edit_pay_sel")
        e_pid = edit_opts[e_sel]
        e_row = df_all[df_all["id"]==e_pid].iloc[0]
        col_ea, col_eb = st.columns(2)
        new_amount = col_ea.number_input(
            "新金額（元）", min_value=0, value=int(e_row["繳交費用"]), step=100, key="edit_pay_amt"
        )
        new_period = col_eb.text_input(
            "期別（YYYY-MM）", value=str(e_row["期別"]), key="edit_pay_period", help="格式：2026-04"
        )
        if st.button("💾 儲存修改", key="do_edit_pay", type="primary"):
            import re as _re
            if not _re.match(r"^\d{4}-\d{2}$", new_period.strip()):
                st.error("期別格式錯誤，請輸入 YYYY-MM，例：2026-04")
            else:
                try:
                    with get_conn() as conn:
                        # 更新 Payments.amount 與 period
                        conn.execute(
                            "UPDATE Payments SET amount=?, period=? WHERE id=?",
                            (new_amount, new_period.strip(), e_pid))
                        # 同步更新 Enrollments.fee（同學員同課程）
                        conn.execute(
                            "UPDATE Enrollments SET fee=? WHERE student_id=? AND course_id=?",
                            (new_amount, int(e_row["student_id"]), int(e_row["course_id"])))
                        conn.commit()
                    st.success(f"✅ 已更新：金額 NT$ {new_amount:,}，期別 {new_period.strip()}")
                    st.rerun()
                except Exception as e:
                    st.error(f"修改失敗：{e}")

    # ── 新功能：移除繳費紀錄 ─────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-title">🗑️ 移除繳費紀錄</div>',unsafe_allow_html=True)
    st.caption("⚠️ 移除後無法復原，請謹慎操作。僅移除繳費單，不影響報名紀錄。")
    if not df_all.empty:
        del_opts = {
            f"{r['學員']} ｜ {r['課程類別']} {r['上課時間']} ｜ {r['期別']} ｜ NT${r['繳交費用']:,.0f}": int(r["id"])
            for _, r in df_all.iterrows()
        }
        d_sel = st.selectbox("選擇要移除的繳費紀錄", list(del_opts.keys()), key="del_pay_sel")
        d_pid = del_opts[d_sel]
        d_conf = st.checkbox("確認移除此繳費紀錄（此操作不可復原）", key="del_pay_conf")
        if st.button("🗑️ 執行移除", key="do_del_pay", type="primary", disabled=not d_conf):
            try:
                with get_conn() as conn:
                    conn.execute("DELETE FROM Payments WHERE id=?", (d_pid,))
                    conn.commit()
                st.success("✅ 繳費紀錄已移除。"); st.rerun()
            except Exception as e:
                st.error(f"移除失敗：{e}")


def page_admin_reports():
    st.markdown('<div class="page-title">📈 報表查詢</div>',unsafe_allow_html=True); st.divider()
    ca,cb=st.columns(2)
    sd=ca.date_input("起始日期",value=date.today().replace(day=1),key="rpt_sd")
    ed=cb.date_input("結束日期",value=date.today(),key="rpt_ed")
    if sd>ed: st.error("起始日期不可晚於結束日期。"); return

    t1,t2,t3,t4,t5=st.tabs(["📅 課程報表","👥 出勤統計報表","💰 繳費統計報表",
                              "🏫 教練上課查詢","🎓 學員上課與繳費查詢"])

    # Tab 1
    with t1:
        with get_conn() as conn:
            df=pd.read_sql_query("""
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
            """,conn,params=(sd.isoformat(),ed.isoformat()))
        if df.empty: st.info("此區間無上課紀錄。")
        else:
            c1,c2=st.columns(2); c1.metric("上課總堂數",len(df)); c2.metric("平均出席人數",f"{df['出席學員數'].mean():.1f}")
            st.dataframe(df,use_container_width=True,height=350)
            st.download_button("⬇️ 匯出 CSV",df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"課程報表_{sd}_{ed}.csv",mime="text/csv")

    # Tab 2
    with t2:
        with get_conn() as conn:
            df2=pd.read_sql_query("""
                SELECT s.name AS 學員,
                       SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS 出席,
                       SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END) AS 缺席,
                       SUM(CASE WHEN a.status='leave'   THEN 1 ELSE 0 END) AS 請假,
                       COUNT(*) AS 總次數
                FROM Attendance a
                JOIN ClassSessions cs ON a.session_id=cs.id
                JOIN Students s ON a.student_id=s.id
                WHERE cs.session_date BETWEEN ? AND ?
                GROUP BY s.id ORDER BY 出席 DESC
            """,conn,params=(sd.isoformat(),ed.isoformat()))
        if df2.empty: st.info("此區間無出勤資料。")
        else:
            df2["出席率"]=(df2["出席"]/df2["總次數"]*100).round(1).astype(str)+"%"
            st.dataframe(df2,use_container_width=True,height=300)
            fig=px.bar(df2,x="學員",y="出席",color_discrete_sequence=["#4CAF50"],title="學員出席次數排名")
            fig.update_layout(height=300,margin=dict(l=0,r=0,t=40,b=0)); st.plotly_chart(fig,use_container_width=True)
            st.download_button("⬇️ 匯出 CSV",df2.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"出勤統計_{sd}_{ed}.csv",mime="text/csv")

    # Tab 3
    with t3:
        ps=sd.strftime("%Y-%m"); pe=ed.strftime("%Y-%m")
        with get_conn() as conn:
            df3=pd.read_sql_query("""
                SELECT p.period AS 期別, s.name AS 學員, c.course_type AS 課程類型,
                       p.amount AS 金額, p.is_paid AS 已繳,
                       COALESCE(p.paid_date,'—') AS 繳費日期
                FROM Payments p JOIN Students s ON p.student_id=s.id
                JOIN Courses c ON p.course_id=c.id
                WHERE p.period BETWEEN ? AND ? ORDER BY p.period, s.name
            """,conn,params=(ps,pe))
        if df3.empty: st.info("此區間無繳費資料。")
        else:
            tf=df3["金額"].sum(); pf=df3[df3["已繳"]==1]["金額"].sum(); uf=df3[df3["已繳"]==0]["金額"].sum()
            c1,c2,c3,c4=st.columns(4)
            c1.metric("總應收",f"NT$ {tf:,.0f}"); c2.metric("已收",f"NT$ {pf:,.0f}")
            c3.metric("未收",f"NT$ {uf:,.0f}"); c4.metric("繳費率",f"{pf/tf*100:.1f}%" if tf else "0%")
            fig=go.Figure(go.Pie(labels=["已繳費","未繳費"],values=[pf,uf],hole=0.4,
                                 marker_colors=["#4CAF50","#F44336"]))
            fig.update_layout(height=300,margin=dict(l=0,r=0,t=20,b=0)); st.plotly_chart(fig,use_container_width=True)
            df3["已繳"]=df3["已繳"].apply(lambda x:"✅ 已繳" if x else "❌ 未繳")
            df3["金額"]=df3["金額"].apply(lambda x:f"NT$ {x:,.0f}")
            st.dataframe(df3,use_container_width=True,height=300)
            st.download_button("⬇️ 匯出 CSV",df3.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"繳費統計_{sd}_{ed}.csv",mime="text/csv")

    # Tab 4：教練上課查詢（v1.5 新增）
    with t4:
        st.markdown('<div class="section-title">🏫 教練上課查詢</div>',unsafe_allow_html=True)
        with get_conn() as conn:
            cl=pd.read_sql_query("SELECT id,name FROM Coaches ORDER BY name",conn)
        if cl.empty: st.info("目前無教練資料。")
        else:
            copts=["全部教練"]+cl["name"].tolist()
            cidmap=dict(zip(cl["name"],cl["id"]))
            selc=st.selectbox("選擇教練",copts,key="t4_c")
            is_all_c=(selc=="全部教練")
            q4="""
                SELECT cs.session_date AS 上課日期,
                       COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, c.schedule_day AS 星期,
                       cs.session_time AS 上課時間, t.name AS 桌次, co.name AS 教練,
                       SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS 出席人數,
                       SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END) AS 缺席人數,
                       SUM(CASE WHEN a.status='leave'   THEN 1 ELSE 0 END) AS 請假人數
                FROM ClassSessions cs
                JOIN Courses  c  ON cs.course_id=c.id
                JOIN Coaches  co ON cs.coach_id=co.id
                JOIN Tables   t  ON cs.table_id=t.id
                LEFT JOIN Attendance a ON a.session_id=cs.id
                WHERE cs.session_date BETWEEN ? AND ?
            """
            p4=[sd.isoformat(),ed.isoformat()]
            if not is_all_c: q4+=" AND cs.coach_id=?"; p4.append(cidmap[selc])
            q4+=" GROUP BY cs.id ORDER BY cs.session_date DESC"
            with get_conn() as conn:
                df4=pd.read_sql_query(q4,conn,params=p4)
            if df4.empty: st.info("此區間無上課紀錄。")
            else:
                c1,c2,c3=st.columns(3)
                c1.metric("負責課程數",df4["課程ID"].nunique())
                c2.metric("上課總堂數",len(df4))
                c3.metric("平均每堂出席人數",f"{df4['出席人數'].mean():.1f}")
                st.divider()
                sc4=["上課日期","課程ID","課程類型","星期","上課時間","桌次","出席人數","缺席人數","請假人數"]
                if is_all_c: sc4.insert(3,"教練")
                st.dataframe(df4[sc4],use_container_width=True,height=320)
                st.markdown('<div class="section-title">📈 每日出席人數趨勢</div>',unsafe_allow_html=True)
                dly4=df4.groupby("上課日期")["出席人數"].sum().reset_index()
                fig4=go.Figure(go.Scatter(x=dly4["上課日期"],y=dly4["出席人數"],
                                          mode="lines+markers",line=dict(color="#FF6B35",width=2),marker=dict(size=6)))
                fig4.update_layout(height=260,xaxis_title="上課日期",yaxis_title="出席人數",margin=dict(l=0,r=0,t=10,b=0))
                st.plotly_chart(fig4,use_container_width=True)
                st.download_button("⬇️ 匯出 CSV",df4[sc4].to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"教練上課查詢_{selc}_{sd}_{ed}.csv",mime="text/csv")

    # Tab 5：學員上課與繳費查詢（v1.5 新增，v1.6 強化）
    with t5:
        st.markdown('<div class="section-title">🎓 學員上課與繳費查詢</div>',unsafe_allow_html=True)
        with get_conn() as conn:
            sl=pd.read_sql_query("SELECT id,name FROM Students ORDER BY name",conn)
        if sl.empty: st.info("目前無學員資料。")
        else:
            sopts=["全部學員"]+sl["name"].tolist()
            sidmap=dict(zip(sl["name"],sl["id"]))
            sels=st.selectbox("選擇學員",sopts,key="t5_s")
            is_all_s=(sels=="全部學員")
            # 出勤查詢（受日期區間限制）
            qa="""
                SELECT cs.session_date AS 上課日期,
                       COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, co.name AS 教練,
                       cs.session_time AS 上課時間, s.name AS 學員,
                       CASE a.status WHEN 'present' THEN '✅ 出席'
                         WHEN 'absent' THEN '❌ 缺席' WHEN 'leave' THEN '🟡 請假' END AS 出勤狀態,
                       a.status AS _st
                FROM Attendance a
                JOIN ClassSessions cs ON a.session_id=cs.id
                JOIN Courses  c  ON cs.course_id=c.id
                JOIN Coaches  co ON cs.coach_id=co.id
                JOIN Students s  ON a.student_id=s.id
                WHERE cs.session_date BETWEEN ? AND ?
            """
            pa=[sd.isoformat(),ed.isoformat()]
            if not is_all_s: qa+=" AND a.student_id=?"; pa.append(sidmap[sels])
            qa+=" ORDER BY cs.session_date DESC, s.name"

            # 歷史出勤查詢（不受日期限制，用於累計統計）
            qa_all="""
                SELECT cs.session_date AS 上課日期,
                       COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, co.name AS 教練,
                       cs.session_time AS 上課時間, s.name AS 學員,
                       a.status AS _st
                FROM Attendance a
                JOIN ClassSessions cs ON a.session_id=cs.id
                JOIN Courses  c  ON cs.course_id=c.id
                JOIN Coaches  co ON cs.coach_id=co.id
                JOIN Students s  ON a.student_id=s.id
            """
            pa_all=[]
            if not is_all_s: qa_all+=" WHERE a.student_id=?"; pa_all.append(sidmap[sels])
            qa_all+=" ORDER BY cs.session_date DESC, s.name"

            # 繳費查詢（不受日期限制）
            qp="""
                SELECT p.period AS 期別, COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, co.name AS 教練,
                       s.name AS 學員, p.amount AS 應繳金額,
                       COALESCE(p.paid_date,'—') AS 繳費日期,
                       COALESCE(p.paid_time,'—') AS 繳費時間, p.is_paid
                FROM Payments p
                JOIN Students s  ON p.student_id=s.id
                JOIN Courses  c  ON p.course_id=c.id
                JOIN Coaches  co ON c.coach_id=co.id
            """
            pp=[]
            if not is_all_s: qp+=" WHERE p.student_id=?"; pp.append(sidmap[sels])
            qp+=" ORDER BY p.period DESC, s.name"

            # 報名課程資訊（用於推算預計上課日期）
            q_enr="""
                SELECT e.student_id, s.name AS 學員, c.id AS course_id,
                       COALESCE(c.course_code,'—') AS 課程ID,
                       c.course_type AS 課程類型, c.schedule_day AS 星期,
                       c.schedule_time AS 上課時間, e.enrolled_date AS 報名日期
                FROM Enrollments e
                JOIN Courses c ON e.course_id=c.id
                JOIN Students s ON e.student_id=s.id
            """
            pe=[]
            if not is_all_s: q_enr+=" WHERE e.student_id=?"; pe.append(sidmap[sels])
            q_enr+=" ORDER BY s.name, c.schedule_day"

            with get_conn() as conn:
                dfa=pd.read_sql_query(qa,conn,params=pa)
                dfa_all=pd.read_sql_query(qa_all,conn,params=pa_all)
                dfp=pd.read_sql_query(qp,conn,params=pp)
                df_enr=pd.read_sql_query(q_enr,conn,params=pe)
                ecnt=conn.execute("SELECT COUNT(*) FROM Enrollments"+(
                    " WHERE student_id=?" if not is_all_s else ""),
                    ([sidmap[sels]] if not is_all_s else [])).fetchone()[0]

            # 累計出席次數（不受日期限制）
            total_present_all = (dfa_all["_st"]=="present").sum() if not dfa_all.empty else 0
            pre5=(dfa["_st"]=="present").sum() if not dfa.empty else 0
            tot5=len(dfa); ar5=pre5/tot5*100 if tot5 else 0
            pt5=dfp[dfp["is_paid"]==1]["應繳金額"].sum() if not dfp.empty else 0
            ut5=dfp[dfp["is_paid"]==0]["應繳金額"].sum() if not dfp.empty else 0

            # 統計指標（6 欄）
            c1,c2,c3,c4,c5,c6=st.columns(6)
            c1.metric("報名課程數",ecnt)
            c2.metric("累計上課次數",total_present_all)  # 新增：累計出席次數（不受日期限制）
            c3.metric("區間出席次數",pre5)
            c4.metric("出席率",f"{ar5:.1f}%")
            c5.metric("已繳費總額",f"NT$ {pt5:,.0f}")
            c6.metric("未繳費總額",f"NT$ {ut5:,.0f}")
            st.divider()

            # ── ① 歷史上課紀錄（全部，不受日期限制）──────────────
            st.markdown('<div class="section-title">① 歷史上課紀錄（全部）</div>',unsafe_allow_html=True)
            st.caption("顯示所有已點名的上課紀錄，不受上方日期區間限制。")
            if dfa_all.empty: st.info("目前無任何上課紀錄。")
            else:
                dfa_all_disp = dfa_all.copy()
                dfa_all_disp["出勤狀態"] = dfa_all_disp["_st"].map(
                    {"present":"✅ 出席","absent":"❌ 缺席","leave":"🟡 請假"})
                ac_all=["上課日期","課程ID","課程類型","教練","上課時間","出勤狀態"]
                if is_all_s: ac_all.insert(2,"學員")
                st.dataframe(dfa_all_disp[ac_all],use_container_width=True,height=260)
                st.download_button(
                    "⬇️ 匯出歷史上課紀錄 CSV",
                    dfa_all_disp[ac_all].to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"歷史上課紀錄_{sels}.csv", mime="text/csv"
                )

            # ── ② 出勤紀錄（日期區間內）────────────────────────────
            st.divider()
            st.markdown('<div class="section-title">② 區間出勤紀錄</div>',unsafe_allow_html=True)
            if dfa.empty: st.info("此區間無出勤紀錄。")
            else:
                ac=["上課日期","課程ID","課程類型","教練","上課時間","出勤狀態"]
                if is_all_s: ac.insert(2,"學員")
                st.dataframe(dfa[ac],use_container_width=True,height=220)
                st.download_button("⬇️ 匯出區間出勤 CSV",dfa[ac].to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"學員出勤查詢_{sels}_{sd}_{ed}.csv",mime="text/csv")
                # 近 6 個月出勤長條圖
                with get_conn() as conn:
                    ch5=pd.read_sql_query("""
                        SELECT substr(cs.session_date,1,7) AS 月份, a.status, COUNT(*) AS 次數
                        FROM Attendance a JOIN ClassSessions cs ON a.session_id=cs.id
                        WHERE cs.session_date>=date('now','-6 months')
                        """+(f" AND a.student_id=?" if not is_all_s else "")+"""
                        GROUP BY 月份, a.status
                    """,conn,params=([sidmap[sels]] if not is_all_s else []))
                if not ch5.empty:
                    pv5=ch5.pivot_table(index="月份",columns="status",values="次數",fill_value=0)
                    cm5={"present":"#4CAF50","absent":"#F44336","leave":"#FF9800"}
                    lm5={"present":"出席","absent":"缺席","leave":"請假"}
                    fig5=go.Figure()
                    for col in pv5.columns:
                        fig5.add_trace(go.Bar(name=lm5.get(col,col),x=pv5.index,y=pv5[col],marker_color=cm5.get(col,"#999")))
                    fig5.update_layout(barmode="group",height=260,margin=dict(l=0,r=0,t=10,b=0),legend=dict(orientation="h"))
                    st.plotly_chart(fig5,use_container_width=True)

            # ── ③ 預計上課日期 ──────────────────────────────────────
            st.divider()
            st.markdown('<div class="section-title">③ 預計上課日期</div>',unsafe_allow_html=True)
            st.caption("依課程排定星期，從報名日起推算未來上課日期。預計上課日期 < 3 堂時顯示繳費通知。")

            if df_enr.empty:
                st.info("目前無報名課程。")
            else:
                # 每個課程分別計算預計日期
                sched_rows = []
                notice_rows = []  # 需要繳費通知的項目

                for _, enr in df_enr.iterrows():
                    target_wd = WD.get(str(enr["星期"]), 0)
                    # 計算該學員在此課程的歷史出勤次數（累計出席）
                    with get_conn() as conn:
                        done_cnt = conn.execute("""
                            SELECT COUNT(*) FROM Attendance a
                            JOIN ClassSessions cs ON a.session_id=cs.id
                            WHERE cs.course_id=? AND a.student_id=? AND a.status='present'
                        """, (int(enr["course_id"]),
                              (sidmap[sels] if not is_all_s else int(enr["student_id"])))).fetchone()[0]

                    # 從今天起推算未來 10 堂預計日期
                    future_dates = []
                    cursor = date.today()
                    while len(future_dates) < 10:
                        if cursor.weekday() == target_wd:
                            future_dates.append(cursor)
                        cursor += timedelta(days=1)

                    # 繳費通知判斷：預計上課日期 < 3 堂
                    notice = "🔔 繳費通知" if len(future_dates) < 3 else ""

                    for i, fd in enumerate(future_dates):
                        row_data = {
                            "學員": enr["學員"],
                            "課程ID": enr["課程ID"],
                            "課程類型": enr["課程類型"],
                            "星期": enr["星期"],
                            "上課時間": enr["上課時間"],
                            "第幾堂": done_cnt + i + 1,
                            "預計上課日期": fd.strftime("%Y-%m-%d"),
                            "備註": notice if i == 0 else "",  # 只在第一行顯示通知
                        }
                        sched_rows.append(row_data)
                        if notice and i == 0:
                            notice_rows.append(row_data)

                if sched_rows:
                    df_sched = pd.DataFrame(sched_rows)
                    show_cols = ["預計上課日期","課程ID","課程類型","星期","上課時間","第幾堂","備註"]
                    if is_all_s: show_cols.insert(0, "學員")

                    # 繳費通知警示（預計日期 < 3 堂的項目）
                    if notice_rows:
                        notice_df = pd.DataFrame(notice_rows)
                        affected = notice_df["課程ID"].tolist()
                        st.warning(
                            f"🔔 **繳費通知**：以下課程預計上課堂數不足 3 堂，請提醒學員續費：\n\n" +
                            "\n".join([f"- {r['學員']} ｜ {r['課程ID']} {r['課程類型']} {r['星期']} {r['上課時間']}"
                                       for r in notice_rows])
                        )

                    st.dataframe(df_sched[show_cols],use_container_width=True,height=300)
                    st.download_button(
                        "⬇️ 匯出預計上課日期 CSV",
                        df_sched[show_cols].to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"預計上課日期_{sels}.csv", mime="text/csv"
                    )

            # ── ④ 繳費紀錄（全期別）────────────────────────────────
            st.divider()
            st.markdown('<div class="section-title">④ 繳費紀錄（全期別）</div>',unsafe_allow_html=True)
            if dfp.empty: st.info("目前無繳費紀錄。")
            else:
                dpd=dfp.copy()
                dpd["狀態"]=dpd["is_paid"].apply(lambda x:"✅ 已繳" if x else "❌ 未繳")
                dpd["應繳金額"]=dpd["應繳金額"].apply(lambda x:f"NT$ {x:,.0f}")
                pc=["期別","課程ID","課程類型","教練","應繳金額","繳費日期","繳費時間","狀態"]
                if is_all_s: pc.insert(2,"學員")
                st.dataframe(dpd[pc],use_container_width=True,height=260)
                st.download_button("⬇️ 匯出繳費 CSV",dpd[pc].to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"學員繳費查詢_{sels}.csv",mime="text/csv")



def page_admin_accounts():
    st.markdown('<div class="page-title">🔑 帳號管理</div>',unsafe_allow_html=True); st.divider()
    with get_conn() as conn:
        users=pd.read_sql_query("""
            SELECT u.id, u.username AS 帳號,
                   CASE u.role WHEN 'admin' THEN '管理者' WHEN 'coach' THEN '教練' ELSE '學員' END AS 角色,
                   COALESCE(s.name,co.name,u.display_name,'—') AS 姓名,
                   COALESCE(u.email,'') AS Email, u.role
            FROM Users u
            LEFT JOIN Students s  ON u.id=s.user_id AND u.role='student'
            LEFT JOIN Coaches  co ON u.id=co.user_id AND u.role='coach'
            ORDER BY u.role, u.username
        """,conn)
    ta,tb=st.tabs(["👤 帳號管理（新增 / 移除）","🔒 重設密碼"])

    with ta:
        st.markdown('<div class="section-title">👥 使用者清單</div>',unsafe_allow_html=True)
        st.dataframe(users[["帳號","角色","姓名","Email"]],use_container_width=True,height=240)

        # ── 新功能：修改使用者資料 ──────────────────────────────────
        st.divider()
        st.markdown('<div class="section-title">✏️ 修改使用者資料</div>',unsafe_allow_html=True)
        edit_u_opts = {f"{r['帳號']}（{r['角色']} / {r['姓名']}）": r["id"]
                       for _, r in users.iterrows()}
        eu_sel = st.selectbox("選擇要修改的帳號", list(edit_u_opts.keys()), key="edit_u_sel")
        eu_id  = edit_u_opts[eu_sel]
        eu_row = users[users["id"]==eu_id].iloc[0]

        with st.form("edit_user_form"):
            eu_c1, eu_c2 = st.columns(2)
            with eu_c1:
                eu_name  = st.text_input("姓名",  value=str(eu_row["姓名"]))
                eu_email = st.text_input("Email", value=str(eu_row["Email"]))
            with eu_c2:
                # 管理者顯示 display_name 說明
                if eu_row["role"] == "admin":
                    st.caption("管理者：姓名存入 Users.display_name")
                elif eu_row["role"] == "student":
                    st.caption("學員：姓名同步更新 Students.name")
                elif eu_row["role"] == "coach":
                    st.caption("教練：姓名同步更新 Coaches.name")
            eu_sub = st.form_submit_button("💾 儲存修改", type="primary")

        if eu_sub:
            if not eu_name.strip():
                st.error("姓名不可為空。")
            else:
                try:
                    with get_conn() as conn:
                        # 更新 Users 的 email 和 display_name（管理者）
                        conn.execute(
                            "UPDATE Users SET email=?, display_name=? WHERE id=?",
                            (eu_email.strip(), eu_name.strip(), eu_id))
                        # 依角色同步更新對應資料表的 name 欄位
                        if eu_row["role"] == "student":
                            conn.execute(
                                "UPDATE Students SET name=?, email=? WHERE user_id=?",
                                (eu_name.strip(), eu_email.strip(), eu_id))
                        elif eu_row["role"] == "coach":
                            conn.execute(
                                "UPDATE Coaches SET name=? WHERE user_id=?",
                                (eu_name.strip(), eu_id))
                        conn.commit()
                    st.success(f"✅ 帳號 '{eu_row['帳號']}' 資料已更新！")
                    st.rerun()
                except Exception as e:
                    st.error(f"修改失敗：{e}")
        st.divider()
        st.markdown('<div class="section-title">➕ 新增帳號</div>',unsafe_allow_html=True)
        with st.form("add_user"):
            ca,cb=st.columns(2)
            with ca:
                nu=st.text_input("帳號"); np=st.text_input("密碼",type="password",help="最少 6 碼且需包含英文字母")
            with cb:
                nr=st.selectbox("角色",["student","coach","admin"],
                                format_func=lambda x:{"student":"學員","coach":"教練","admin":"管理者"}[x])
                nn=st.text_input("姓名（顯示名稱）"); ne=st.text_input("Email（選填）")
            asub=st.form_submit_button("✅ 建立帳號",type="primary")
        if asub:
            if not nu or not np or not nn: st.error("帳號、密碼與姓名皆為必填。")
            else:
                ok,msg=validate_pw(np)
                if not ok: st.error(msg)
                else:
                    try:
                        with get_conn() as conn:
                            if conn.execute("SELECT id FROM Users WHERE username=?",(nu,)).fetchone():
                                st.error("帳號已存在，請使用其他帳號名稱。")
                            else:
                                cur=conn.execute(
                                    "INSERT INTO Users(username,password,role,email,display_name) VALUES(?,?,?,?,?)",
                                    (nu,hash_pw(np),nr,ne,nn)); conn.commit(); uid=cur.lastrowid
                                if nr=="student":
                                    conn.execute("INSERT INTO Students(user_id,name,email) VALUES(?,?,?)",(uid,nn,ne))
                                elif nr=="coach":
                                    conn.execute("INSERT INTO Coaches(user_id,name) VALUES(?,?)",(uid,nn))
                                conn.commit()
                                st.success(f"✅ 帳號 '{nu}' 建立成功！"); st.rerun()
                    except Exception as e: st.error(f"建立失敗：{e}")
        st.divider()
        st.markdown('<div class="section-title">🗑️ 移除帳號</div>',unsafe_allow_html=True)
        cuid=st.session_state.get("user_id"); adm_cnt=(users["role"]=="admin").sum()
        removable=users[users["id"]!=cuid].copy()
        if removable.empty: st.info("目前無可移除的帳號。")
        else:
            ropts={f"{r['帳號']}（{r['角色']} / {r['姓名']}）":r["id"] for _,r in removable.iterrows()}
            rsel=st.selectbox("選擇要移除的帳號",list(ropts.keys()),key="rm_user_sel")
            ruid=ropts[rsel]; rrow=users[users["id"]==ruid].iloc[0]
            with get_conn() as conn:
                if rrow["role"]=="student":
                    sr=conn.execute("SELECT id FROM Students WHERE user_id=?",(ruid,)).fetchone()
                    if sr:
                        ec=conn.execute("SELECT COUNT(*) FROM Enrollments WHERE student_id=?",(sr["id"],)).fetchone()[0]
                        ac=conn.execute("SELECT COUNT(*) FROM Attendance WHERE student_id=?",(sr["id"],)).fetchone()[0]
                        uc=conn.execute("SELECT COUNT(*) FROM Payments WHERE student_id=? AND is_paid=0",(sr["id"],)).fetchone()[0]
                        st.info(f"此學員關聯資料：報名課程 {ec} 筆、出勤紀錄 {ac} 筆、未繳費 {uc} 筆。\n\n"
                                "⚠️ 刪除後對應資料需另行處理。")
                elif rrow["role"]=="coach":
                    cr=conn.execute("SELECT id FROM Coaches WHERE user_id=?",(ruid,)).fetchone()
                    if cr:
                        cc=conn.execute("SELECT COUNT(*) FROM Courses WHERE coach_id=?",(cr["id"],)).fetchone()[0]
                        if cc>0: st.warning(f"⚠️ 此教練仍負責 **{cc}** 筆課程，建議先至「課程管理」移除後再刪除帳號。")
                        else: st.info("此教練目前無負責課程，可安全刪除。")
                elif rrow["role"]=="admin":
                    if adm_cnt<=1: st.error("⛔ 系統至少需保留一個管理者帳號，無法刪除。"); st.stop()
                    else: st.info("注意：刪除後請確認仍有其他管理者可登入。")
            conf=st.checkbox("確認刪除此帳號",key="conf_rm_user")
            if st.button("🗑️ 執行移除帳號",key="do_rm_user"):
                if not conf: st.warning("請先勾選「確認刪除此帳號」。")
                else:
                    try:
                        with get_conn() as conn:
                            if rrow["role"]=="student":
                                conn.execute("DELETE FROM Students WHERE user_id=?",(ruid,))
                            elif rrow["role"]=="coach":
                                conn.execute("DELETE FROM Coaches WHERE user_id=?",(ruid,))
                            conn.execute("DELETE FROM Users WHERE id=?",(ruid,))
                            conn.commit()
                        st.success(f"✅ 帳號 '{rrow['帳號']}' 已移除。"); st.rerun()
                    except Exception as e: st.error(f"移除失敗：{e}")

    with tb:
        uopts=dict(zip(users["帳號"],users["id"]))
        with st.form("reset_pw"):
            su=st.selectbox("選擇帳號",list(uopts.keys()))
            p1=st.text_input("新密碼",type="password",help="最少 6 碼且需包含英文字母")
            p2=st.text_input("確認新密碼",type="password")
            rok=st.form_submit_button("🔒 重設密碼",type="primary")
        if rok:
            if not p1: st.error("密碼不可為空。")
            elif p1!=p2: st.error("兩次輸入的密碼不一致。")
            else:
                ok,msg=validate_pw(p1)
                if not ok: st.error(msg)
                else:
                    with get_conn() as conn:
                        conn.execute("UPDATE Users SET password=? WHERE id=?",(hash_pw(p1),uopts[su])); conn.commit()
                    st.success(f"✅ 帳號 '{su}' 的密碼已重設。")


# ══════════════════════════════════════════════════════════════
# 📅  F-008：近 7 天課程查詢（全角色）
# ══════════════════════════════════════════════════════════════

def page_weekly_schedule():
    st.markdown('<div class="page-title">📅 近期課程查詢</div>',unsafe_allow_html=True); st.divider()
    role=st.session_state.get("role",""); pid=st.session_state.get("profile_id")
    opts=date_opts(); labels=[o[0] for o in opts]; dates=[o[1] for o in opts]
    sel=st.selectbox("選擇查詢日期",labels,index=0)
    sdate=dates[labels.index(sel)]
    swd=["週一","週二","週三","週四","週五","週六","週日"][sdate.weekday()]
    st.markdown(f"<small style='color:#888;'>查詢日期：{sdate.isoformat()}（{swd}）</small>",unsafe_allow_html=True)
    st.divider()
    with get_conn() as conn:
        ac=pd.read_sql_query("""
            SELECT c.id, c.course_type, c.schedule_time, c.duration, c.table_id,
                   COALESCE(c.course_code,'—') AS code, co.name AS cname, COUNT(e.id) AS ecnt
            FROM Courses c JOIN Coaches co ON c.coach_id=co.id
            LEFT JOIN Enrollments e ON e.course_id=c.id
            WHERE c.schedule_day=?
            GROUP BY c.id ORDER BY c.table_id, c.schedule_time
        """,conn,params=(swd,))
        if role=="coach":
            my_ids=set(pd.read_sql_query("SELECT id FROM Courses WHERE coach_id=?",conn,params=(pid,))["id"].tolist())
        elif role=="student":
            my_ids=set(pd.read_sql_query("SELECT course_id FROM Enrollments WHERE student_id=?",conn,params=(pid,))["course_id"].tolist())
        else:
            my_ids=None
    if ac.empty: st.info("📭 所選日期無排定課程。"); return
    st.markdown('<div class="section-title">🏓 桌次甘特圖</div>',unsafe_allow_html=True)
    if my_ids is not None: st.caption("🟠 本人課程　⬜ 其他已佔用課程")
    fig=go.Figure()
    for _,c in ac.iterrows():
        sm=t2m(str(c["schedule_time"])); em=sm+int(c["duration"]); dh=int(c["duration"])/60
        mine=(my_ids is None or c["id"] in my_ids)
        clr="#FF6B35" if mine else "#CCCCCC"
        hov=(f"<b>桌{c['table_id']}</b><br>課程ID：{c['code']}<br>"
             f"類型：{c['course_type']}<br>教練：{c['cname']}<br>"
             f"時段：{c['schedule_time']}～{em//60:02d}:{em%60:02d}<br>"
             f"報名人數：{c['ecnt']}<br>" if mine else
             f"<b>桌{c['table_id']}</b><br>已佔用<br>")
        fig.add_trace(go.Bar(x=[dh],y=[f"桌{c['table_id']}"],base=[sm/60],
                             orientation="h",marker_color=clr,
                             hovertemplate=hov+"<extra></extra>",showlegend=False))
    fig.update_layout(
        barmode="overlay",height=360,
        xaxis=dict(title="時間",range=[8,22],tickvals=list(range(8,23)),
                   ticktext=[f"{h:02d}:00" for h in range(8,23)]),
        yaxis=dict(title="桌次",categoryorder="array",categoryarray=[f"桌{i}" for i in range(8,0,-1)]),
        margin=dict(l=40,r=20,t=20,b=40),plot_bgcolor="#F9F9F9")
    st.plotly_chart(fig,use_container_width=True)
    st.markdown('<div class="section-title">📋 課程明細</div>',unsafe_allow_html=True)
    show=(ac[ac["id"].isin(my_ids)].copy() if my_ids is not None else ac.copy())
    other=(len(ac)-len(show)) if my_ids is not None else 0
    if show.empty: st.info("📭 您在所選日期無排定課程。")
    else:
        show=show.copy()
        show["結束時間"]=show.apply(lambda r:end_t(str(r["schedule_time"]),int(r["duration"])),axis=1)
        show["桌次"]=show["table_id"].apply(lambda x:f"桌{x}")
        disp=show[["桌次","code","course_type","cname","schedule_time","結束時間","duration","ecnt"]].copy()
        disp.columns=["桌次","課程ID","課程類型","教練","開始時間","結束時間","時長（分鐘）","報名人數"]
        st.dataframe(disp.sort_values("桌次").reset_index(drop=True),use_container_width=True,height=260)
    if other>0:
        st.caption(f"（另有 {other} 個其他課程已佔用桌次，詳見甘特圖灰色區塊）")


# ══════════════════════════════════════════════════════════════
# 🚀  主程式
# ══════════════════════════════════════════════════════════════

def main():
    init_db()
    if "user_id" not in st.session_state:
        login_page(); return
    sel=sidebar(); role=st.session_state.get("role","")
    if role=="student":
        pages={"📚 我的課程":page_my_courses,"🙏 請假申請":page_leave_request,
               "💳 繳費狀況":page_payment_status,"📋 出勤紀錄":page_attendance_record,
               "📅 近期課程查詢":page_weekly_schedule}
    elif role=="coach":
        pages={"👤 個人簡介編輯":page_coach_profile,"👥 課程學員名單":page_coach_students,
               "✅ 課堂點名":page_coach_attendance,"🙏 請假審核":page_coach_leave_review,
               "📅 近期課程查詢":page_weekly_schedule}
    elif role=="admin":
        pages={"📅 課程管理":page_admin_courses,"📊 出勤總表":page_admin_attendance,
               "💰 繳費管理":page_admin_payments,"📈 報表查詢":page_admin_reports,
               "🔑 帳號管理":page_admin_accounts,"📅 近期課程查詢":page_weekly_schedule}
    else:
        st.error("未知角色，請重新登入。"); return
    (pages.get(sel) or list(pages.values())[0])()

if __name__=="__main__":
    main()

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote_plus
from uuid import uuid4

import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


APP_TITLE = "Goals Planner"
LOCAL_FILE = Path(__file__).with_name("done_app_state.json")
SHEET_TAB = "done_app_state"
GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/u/0/r"


def today_key() -> str:
    return date.today().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def default_state() -> dict:
    return {
        "goals": [
            {"id": "goal_coursework", "name": "Coursework Reassessment", "color": "#E24B4A", "icon": "📚"},
            {"id": "goal_fitness", "name": "Fitness & Weight Loss", "color": "#1D9E75", "icon": "💪"},
            {"id": "goal_solar", "name": "Solar Tech YouTube", "color": "#BA7517", "icon": "☀️"},
            {"id": "goal_trading", "name": "Stock & Options Trading", "color": "#534AB7", "icon": "📈"},
        ],
        "tasks": [
            {
                "id": "task_cw_outline",
                "title": "Coursework 1 outline & draft",
                "goal_id": "goal_coursework",
                "time": "8:30 PM",
                "note": "Focus block: 8:30-10:00 PM",
                "subtasks": ["Outline", "Draft", "Review"],
                "done_dates": [],
            },
            {
                "id": "task_youtube_script",
                "title": "Draft one Solar Tech video idea",
                "goal_id": "goal_solar",
                "time": "8:30 PM",
                "note": "Keep it short and practical.",
                "subtasks": ["Hook", "3 talking points", "CTA"],
                "done_dates": [],
            },
            {
                "id": "task_trade_journal",
                "title": "Review trading lesson or paper trade",
                "goal_id": "goal_trading",
                "time": "8:30 PM",
                "note": "Log what you learned.",
                "subtasks": ["Study", "Journal"],
                "done_dates": [],
            },
        ],
        "habits": [
            {
                "id": "habit_exercise",
                "title": "Exercise",
                "goal_id": "goal_fitness",
                "cadence": "Daily",
                "category": "Health",
                "done_dates": [],
            },
            {
                "id": "habit_study",
                "title": "Study block",
                "goal_id": "goal_coursework",
                "cadence": "Weekdays",
                "category": "Focus",
                "done_dates": [],
            },
            {
                "id": "habit_water",
                "title": "Drink enough water",
                "goal_id": "goal_fitness",
                "cadence": "Daily",
                "category": "Health",
                "done_dates": [],
            },
        ],
        "daily_notes": {},
        "history": {},
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def google_sheet_configured() -> bool:
    return (
        gspread is not None
        and Credentials is not None
        and "gcp_service_account" in st.secrets
        and "google_sheet_id" in st.secrets
    )


def get_worksheet():
    if not google_sheet_configured():
        return None
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes,
    )
    client = gspread.authorize(credentials)
    workbook = client.open_by_key(st.secrets["google_sheet_id"])
    try:
        worksheet = workbook.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        worksheet = workbook.add_worksheet(title=SHEET_TAB, rows=20, cols=3)
        worksheet.update("A1:C1", [["key", "payload_json", "updated_at"]])
    return worksheet


def load_from_sheet() -> dict | None:
    worksheet = get_worksheet()
    if worksheet is None:
        return None
    rows = worksheet.get_all_records()
    for row in rows:
        if row.get("key") == "app_state" and row.get("payload_json"):
            return merge_state(json.loads(row["payload_json"]))
    return None


def save_to_sheet(state: dict) -> bool:
    worksheet = get_worksheet()
    if worksheet is None:
        return False
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    worksheet.clear()
    worksheet.update(
        "A1:C2",
        [
            ["key", "payload_json", "updated_at"],
            ["app_state", json.dumps(state, ensure_ascii=False), state["updated_at"]],
        ],
    )
    return True


def merge_state(saved: dict) -> dict:
    state = default_state()
    for key in ["goals", "tasks", "habits", "daily_notes", "history", "updated_at"]:
        if key in saved:
            state[key] = saved[key]
    return state


def load_state() -> tuple[dict, str, str]:
    try:
        sheet_state = load_from_sheet()
        if sheet_state:
            return sheet_state, "Google Sheets", ""
    except Exception as exc:
        sheet_error = f"Google Sheets load failed: {exc}"
    else:
        sheet_error = ""

    if LOCAL_FILE.exists():
        try:
            return merge_state(json.loads(LOCAL_FILE.read_text(encoding="utf-8"))), "Local JSON", sheet_error
        except (OSError, json.JSONDecodeError) as exc:
            return default_state(), "Local JSON", f"Local save could not be read: {exc}"
    return default_state(), "Local JSON", sheet_error


def save_state() -> None:
    state = st.session_state["app_state"]
    state["history"][today_key()] = daily_summary(state)
    try:
        if save_to_sheet(state):
            st.session_state["storage_backend"] = "Google Sheets"
            st.session_state["storage_error"] = ""
            st.session_state["last_saved"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
            return
    except Exception as exc:
        st.session_state["storage_error"] = f"Google Sheets save failed: {exc}"

    try:
        LOCAL_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        st.session_state["storage_backend"] = "Local JSON"
        st.session_state["last_saved"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    except OSError as exc:
        st.session_state["storage_error"] = f"Local save failed: {exc}"


def goal_map(state: dict) -> dict:
    return {goal["id"]: goal for goal in state["goals"]}


def is_done_today(item: dict) -> bool:
    return today_key() in item.get("done_dates", [])


def set_done_today(collection: str, item_id: str, done: bool) -> None:
    state = st.session_state["app_state"]
    for item in state[collection]:
        if item["id"] == item_id:
            dates = set(item.get("done_dates", []))
            if done:
                dates.add(today_key())
            else:
                dates.discard(today_key())
            item["done_dates"] = sorted(dates)
            break
    save_state()


def daily_summary(state: dict) -> dict:
    tasks_done = sum(1 for task in state["tasks"] if today_key() in task.get("done_dates", []))
    habits_done = sum(1 for habit in state["habits"] if today_key() in habit.get("done_dates", []))
    total = len(state["tasks"]) + len(state["habits"])
    done = tasks_done + habits_done
    return {
        "date": today_key(),
        "tasks_done": tasks_done,
        "tasks_total": len(state["tasks"]),
        "habits_done": habits_done,
        "habits_total": len(state["habits"]),
        "done_total": done,
        "item_total": total,
        "percent": round((done / total) * 100) if total else 0,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def streak_count(item: dict) -> int:
    done_dates = set(item.get("done_dates", []))
    current = date.today()
    streak = 0
    while current.isoformat() in done_dates:
        streak += 1
        current = date.fromordinal(current.toordinal() - 1)
    return streak


def parse_task_time(value: str | None) -> time:
    if not value:
        return time(20, 30)
    clean = value.strip().upper().replace(".", "")
    for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            return datetime.strptime(clean, fmt).time()
        except ValueError:
            continue
    return time(20, 30)


def google_calendar_event_url(title: str, event_date: date, start_value: str | None, details: str = "") -> str:
    start_time = parse_task_time(start_value)
    start_dt = datetime.combine(event_date, start_time)
    end_dt = start_dt + timedelta(minutes=60)
    dates = f"{start_dt.strftime('%Y%m%dT%H%M%S')}/{end_dt.strftime('%Y%m%dT%H%M%S')}"
    return (
        "https://calendar.google.com/calendar/render?action=TEMPLATE"
        f"&text={quote_plus(title)}"
        f"&dates={dates}"
        f"&details={quote_plus(details)}"
    )


def week_dates(anchor: date) -> list[date]:
    monday = anchor - timedelta(days=anchor.weekday())
    return [monday + timedelta(days=index) for index in range(7)]


def planned_items_for_day(state: dict, day: date) -> list[dict]:
    weekday = day.weekday()
    items = []
    for task in state["tasks"]:
        items.append(
            {
                "type": "Task",
                "title": task["title"],
                "goal_id": task.get("goal_id"),
                "time": task.get("time") or "8:30 PM",
                "note": task.get("note", ""),
                "done": day.isoformat() in task.get("done_dates", []),
                "url": google_calendar_event_url(task["title"], day, task.get("time"), task.get("note", "")),
            }
        )
    for habit in state["habits"]:
        cadence = habit.get("cadence", "Daily")
        should_show = cadence == "Daily" or (cadence == "Weekdays" and weekday < 5) or cadence in {"Weekly", "Monthly"}
        if should_show:
            items.append(
                {
                    "type": "Habit",
                    "title": habit["title"],
                    "goal_id": habit.get("goal_id"),
                    "time": "6:00 AM" if "exercise" in habit["title"].lower() else "8:30 PM",
                    "note": f"{cadence} habit",
                    "done": day.isoformat() in habit.get("done_dates", []),
                    "url": google_calendar_event_url(habit["title"], day, "6:00 AM" if "exercise" in habit["title"].lower() else "8:30 PM", f"{cadence} habit"),
                }
            )
    return sorted(items, key=lambda item: parse_task_time(item["time"]))


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #fbfaf7; color: #20242c; }
        .block-container { max-width: 1040px; padding-top: 2rem; padding-bottom: 3rem; }
        div[data-testid="stMetric"] {
            background: #fff;
            border: 1px solid #ece7df;
            border-radius: 18px;
            padding: 14px 16px;
            box-shadow: 0 8px 24px rgba(38, 32, 24, 0.04);
        }
        .hero {
            background: #ffffff;
            border: 1px solid #ece7df;
            border-radius: 22px;
            padding: 24px 26px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            gap: 16px;
        }
        .hero-title { font-size: 2rem; line-height: 1.05; font-weight: 850; margin-bottom: 8px; }
        .muted { color: #7d8290; }
        .card {
            background: #fff;
            border: 1px solid #ece7df;
            border-radius: 18px;
            padding: 16px;
            margin-bottom: 12px;
            box-shadow: 0 8px 24px rgba(38, 32, 24, 0.035);
        }
        .task-row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 12px;
            align-items: center;
        }
        .pill {
            display: inline-flex;
            border-radius: 999px;
            padding: 4px 9px;
            background: #f4f1eb;
            font-size: 0.78rem;
            color: #666b75;
            margin-right: 5px;
        }
        .goal-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 7px;
        }
        .section-title { font-weight: 800; font-size: 1.25rem; margin: 18px 0 10px; }
        @media (max-width: 720px) {
            .hero { flex-direction: column; }
            .hero-title { font-size: 1.55rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "app_state" not in st.session_state:
        state, backend, error = load_state()
        st.session_state["app_state"] = state
        st.session_state["storage_backend"] = backend
        st.session_state["storage_error"] = error
        st.session_state["last_saved"] = state.get("updated_at", "Not saved yet")
    st.session_state.setdefault("view", "Today")


def render_header() -> None:
    state = st.session_state["app_state"]
    summary = daily_summary(state)
    st.markdown(
        f"""
        <div class="hero">
            <div>
                <div class="hero-title">Goals Planner</div>
                <div class="muted">Plan tasks, build habits, track goals, and record daily progress.</div>
            </div>
            <div class="muted">
                Storage: <strong>{st.session_state.get("storage_backend", "Local JSON")}</strong><br>
                Today: <strong>{summary["done_total"]}/{summary["item_total"]}</strong> done
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.session_state.get("storage_error"):
        st.warning(st.session_state["storage_error"])
    views = ["Today", "Calendar", "Tasks", "Habits", "Goals", "Stats", "Settings"]
    st.session_state["view"] = st.segmented_control(
        "View",
        views,
        default=st.session_state["view"],
        selection_mode="single",
        label_visibility="collapsed",
    )


def render_quick_add() -> None:
    state = st.session_state["app_state"]
    goals = goal_map(state)
    with st.expander("Quick add", expanded=False):
        tab_task, tab_habit, tab_goal = st.tabs(["Task", "Habit", "Goal"])
        with tab_task:
            with st.form("add_task", clear_on_submit=True):
                title = st.text_input("Task title")
                goal_label = st.selectbox("Goal", [goal["name"] for goal in state["goals"]])
                time = st.text_input("Time", placeholder="8:30 PM")
                note = st.text_area("Note")
                subtasks = st.text_input("Subtasks", placeholder="Separate with commas")
                if st.form_submit_button("Add task"):
                    goal_id = next(goal["id"] for goal in state["goals"] if goal["name"] == goal_label)
                    state["tasks"].append(
                        {
                            "id": new_id("task"),
                            "title": title.strip() or "Untitled task",
                            "goal_id": goal_id,
                            "time": time.strip(),
                            "note": note.strip(),
                            "subtasks": [part.strip() for part in subtasks.split(",") if part.strip()],
                            "done_dates": [],
                        }
                    )
                    save_state()
                    st.rerun()
        with tab_habit:
            with st.form("add_habit", clear_on_submit=True):
                title = st.text_input("Habit title")
                goal_label = st.selectbox("Goal", [goal["name"] for goal in state["goals"]], key="habit_goal")
                cadence = st.selectbox("Cadence", ["Daily", "Weekdays", "Weekly", "Monthly"])
                category = st.text_input("Category", placeholder="Health, Focus, Learning")
                if st.form_submit_button("Add habit"):
                    goal_id = next(goal["id"] for goal in state["goals"] if goal["name"] == goal_label)
                    state["habits"].append(
                        {
                            "id": new_id("habit"),
                            "title": title.strip() or "Untitled habit",
                            "goal_id": goal_id,
                            "cadence": cadence,
                            "category": category.strip() or "General",
                            "done_dates": [],
                        }
                    )
                    save_state()
                    st.rerun()
        with tab_goal:
            with st.form("add_goal", clear_on_submit=True):
                name = st.text_input("Goal name")
                icon = st.text_input("Icon", value="🎯")
                color = st.color_picker("Color", value="#534AB7")
                if st.form_submit_button("Add goal"):
                    state["goals"].append({"id": new_id("goal"), "name": name.strip() or "New goal", "color": color, "icon": icon})
                    save_state()
                    st.rerun()


def render_task_card(task: dict, goals: dict, collection: str = "tasks") -> None:
    goal = goals.get(task.get("goal_id"), {"name": "No goal", "color": "#999", "icon": "•"})
    done = is_done_today(task)
    cols = st.columns([0.08, 0.72, 0.2])
    with cols[0]:
        checked = st.checkbox("done", value=done, key=f"done_{collection}_{task['id']}_{today_key()}", label_visibility="collapsed")
        if checked != done:
            set_done_today(collection, task["id"], checked)
            st.rerun()
    with cols[1]:
        st.markdown(
            f"""
            <div>
                <strong>{task['title']}</strong><br>
                <span class="pill"><span class="goal-dot" style="background:{goal['color']};"></span>{goal['name']}</span>
                {f'<span class="pill">{task.get("time")}</span>' if task.get("time") else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if task.get("note"):
            st.caption(task["note"])
        if task.get("subtasks"):
            st.caption("Steps: " + " · ".join(task["subtasks"]))
    with cols[2]:
        st.caption("Done today" if done else "Open")


def render_habit_card(habit: dict, goals: dict) -> None:
    goal = goals.get(habit.get("goal_id"), {"name": "No goal", "color": "#999", "icon": "•"})
    done = is_done_today(habit)
    cols = st.columns([0.08, 0.72, 0.2])
    with cols[0]:
        checked = st.checkbox("done", value=done, key=f"done_habit_{habit['id']}_{today_key()}", label_visibility="collapsed")
        if checked != done:
            set_done_today("habits", habit["id"], checked)
            st.rerun()
    with cols[1]:
        st.markdown(
            f"""
            <div>
                <strong>{habit['title']}</strong><br>
                <span class="pill">{habit.get('cadence', 'Daily')}</span>
                <span class="pill">{habit.get('category', 'General')}</span>
                <span class="pill"><span class="goal-dot" style="background:{goal['color']};"></span>{goal['name']}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.metric("Streak", streak_count(habit))


def render_today() -> None:
    state = st.session_state["app_state"]
    goals = goal_map(state)
    summary = daily_summary(state)
    cols = st.columns(4)
    cols[0].metric("Today done", f"{summary['done_total']}/{summary['item_total']}")
    cols[1].metric("Progress", f"{summary['percent']}%")
    cols[2].metric("Tasks", f"{summary['tasks_done']}/{summary['tasks_total']}")
    cols[3].metric("Habits", f"{summary['habits_done']}/{summary['habits_total']}")

    render_quick_add()

    st.markdown("<div class='section-title'>Today’s tasks</div>", unsafe_allow_html=True)
    for task in sorted(state["tasks"], key=lambda item: item.get("time") or "99:99"):
        with st.container(border=False):
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            render_task_card(task, goals)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Today’s habits</div>", unsafe_allow_html=True)
    for habit in state["habits"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        render_habit_card(habit, goals)
        st.markdown("</div>", unsafe_allow_html=True)

    note = st.text_area("Daily note", value=state["daily_notes"].get(today_key(), ""), placeholder="What worked today? What got in the way?")
    if st.button("Save daily note", use_container_width=True):
        state["daily_notes"][today_key()] = note
        save_state()
        st.success("Daily note saved.")
        st.rerun()


def render_tasks() -> None:
    state = st.session_state["app_state"]
    goals = goal_map(state)
    render_quick_add()
    for task in state["tasks"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        render_task_card(task, goals)
        st.markdown("</div>", unsafe_allow_html=True)


def render_habits() -> None:
    state = st.session_state["app_state"]
    goals = goal_map(state)
    render_quick_add()
    for habit in state["habits"]:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        render_habit_card(habit, goals)
        st.markdown("</div>", unsafe_allow_html=True)


def render_goals() -> None:
    state = st.session_state["app_state"]
    render_quick_add()
    for goal in state["goals"]:
        tasks = [task for task in state["tasks"] if task.get("goal_id") == goal["id"]]
        habits = [habit for habit in state["habits"] if habit.get("goal_id") == goal["id"]]
        done = sum(1 for item in tasks + habits if is_done_today(item))
        total = len(tasks) + len(habits)
        pct = round((done / total) * 100) if total else 0
        st.markdown(
            f"""
            <div class="card">
                <h3>{goal['icon']} {goal['name']}</h3>
                <p class="muted">{done}/{total} items done today · {pct}%</p>
                <div style="height:8px;background:#f0ece4;border-radius:999px;overflow:hidden;">
                    <div style="height:8px;width:{pct}%;background:{goal['color']};border-radius:999px;"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_stats() -> None:
    state = st.session_state["app_state"]
    state["history"][today_key()] = daily_summary(state)
    save_state()
    st.subheader("Progress statistics")
    st.caption("Target is the number of tasks and habits planned for the day. Achievement is what you completed.")

    history_rows = []
    for day, row in sorted(state["history"].items()):
        target = row.get("item_total", 0)
        achievement = row.get("done_total", 0)
        history_rows.append(
            {
                "Date": day,
                "Target": target,
                "Achievement": achievement,
                "Completion %": row.get("percent", round((achievement / target) * 100) if target else 0),
                "Tasks Done": row.get("tasks_done", 0),
                "Tasks Target": row.get("tasks_total", 0),
                "Habits Done": row.get("habits_done", 0),
                "Habits Target": row.get("habits_total", 0),
            }
        )

    if not history_rows:
        st.info("No progress history yet. Complete a task or habit to start the graph.")
        return

    latest = history_rows[-1]
    average_completion = round(sum(row["Completion %"] for row in history_rows) / len(history_rows))
    cols = st.columns(4)
    cols[0].metric("Today achievement", f"{latest['Achievement']}/{latest['Target']}")
    cols[1].metric("Today completion", f"{latest['Completion %']}%")
    cols[2].metric("Average completion", f"{average_completion}%")
    cols[3].metric("Days recorded", len(history_rows))

    st.write("")
    chart_rows = [
        {"Date": row["Date"], "Metric": "Target", "Value": row["Target"]}
        for row in history_rows
    ] + [
        {"Date": row["Date"], "Metric": "Achievement", "Value": row["Achievement"]}
        for row in history_rows
    ]

    st.markdown("**Target vs achievement**")
    st.bar_chart(chart_rows, x="Date", y="Value", color="Metric", use_container_width=True)

    st.markdown("**Completion trend**")
    st.line_chart(history_rows, x="Date", y="Completion %", use_container_width=True)

    st.markdown("**Tasks and habits achievement**")
    category_rows = []
    for row in history_rows:
        category_rows.extend(
            [
                {"Date": row["Date"], "Metric": "Tasks Done", "Value": row["Tasks Done"]},
                {"Date": row["Date"], "Metric": "Tasks Target", "Value": row["Tasks Target"]},
                {"Date": row["Date"], "Metric": "Habits Done", "Value": row["Habits Done"]},
                {"Date": row["Date"], "Metric": "Habits Target", "Value": row["Habits Target"]},
            ]
        )
    st.bar_chart(category_rows, x="Date", y="Value", color="Metric", use_container_width=True)

    with st.expander("Daily records"):
        st.dataframe(history_rows, use_container_width=True, hide_index=True)


def render_calendar() -> None:
    state = st.session_state["app_state"]
    goals = goal_map(state)
    st.subheader("Calendar")
    st.caption("View your planned tasks and habits by week, then open or add items to Google Calendar.")

    top_cols = st.columns([0.45, 0.25, 0.3])
    selected_day = top_cols[0].date_input("Week of", value=date.today())
    top_cols[1].link_button("Open Google Calendar", GOOGLE_CALENDAR_URL, use_container_width=True)
    top_cols[2].caption("Links create 1-hour Google Calendar events using each item's planned time.")

    st.write("")
    for day in week_dates(selected_day):
        day_items = planned_items_for_day(state, day)
        with st.expander(f"{day.strftime('%A, %d %b')} · {len(day_items)} items", expanded=(day == date.today())):
            if not day_items:
                st.caption("No items planned.")
            for item in day_items:
                goal = goals.get(item.get("goal_id"), {"name": "No goal", "color": "#999"})
                status = "Done" if item["done"] else "Planned"
                cols = st.columns([0.12, 0.58, 0.15, 0.15])
                cols[0].markdown(f"**{item['time']}**")
                cols[1].markdown(
                    f"""
                    <div>
                        <strong>{item['title']}</strong><br>
                        <span class="pill">{item['type']}</span>
                        <span class="pill"><span class="goal-dot" style="background:{goal['color']};"></span>{goal['name']}</span>
                        <span class="pill">{status}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                cols[2].link_button("Add event", item["url"], use_container_width=True)
                if day == date.today():
                    cols[3].caption("Track in Today")
                else:
                    cols[3].caption(day.strftime("%a"))


def render_settings() -> None:
    state = st.session_state["app_state"]
    st.subheader("Settings & backup")
    st.info(
        f"Storage backend: {st.session_state.get('storage_backend', 'Local JSON')}\n\n"
        f"Last saved: {st.session_state.get('last_saved', 'Not saved yet')}"
    )
    if st.session_state.get("storage_error"):
        st.warning(st.session_state["storage_error"])
    st.download_button(
        "Download app backup",
        data=json.dumps(state, indent=2, ensure_ascii=False),
        file_name=f"done_style_backup_{today_key()}.json",
        mime="application/json",
        use_container_width=True,
    )
    if st.button("Save now", use_container_width=True):
        save_state()
        st.success("Saved.")
        st.rerun()


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="✅", layout="wide")
    init_state()
    inject_css()
    render_header()
    view = st.session_state["view"]
    if view == "Today":
        render_today()
    elif view == "Calendar":
        render_calendar()
    elif view == "Tasks":
        render_tasks()
    elif view == "Habits":
        render_habits()
    elif view == "Goals":
        render_goals()
    elif view == "Stats":
        render_stats()
    else:
        render_settings()


if __name__ == "__main__":
    main()

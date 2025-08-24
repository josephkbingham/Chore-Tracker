# Streamlit app: Thomas Bingham — Weekly Responsibility Tracker
# --------------------------------------------------------------
# How to run:
#   1) pip install streamlit pandas openpyxl xlsxwriter
#   2) streamlit run streamlit_app_thomas_tracker.py
#
# Features:
# - Editable weekly tracker for Mon–Sun with the exact columns from the family agreement
# - Per-day Score (0–3) and auto-calculated Daily Earning = ROUND(Base × Score/3, 2)
# - Settings for Base daily amount and Weekly bonus (>= threshold compliant days)
# - Summary: compliant days (Score==3), sum of earnings, weekly payout
# - Import/export CSV or Excel (Excel export includes formulas & a Settings sheet)
# - Optional suggested-score helper (off by default)

import io
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Thomas — Weekly Responsibility Tracker",
    layout="wide",
)

# -----------------------------
# Helpers
# -----------------------------

def week_start(d: date, week_starts_on_monday: bool = True) -> date:
    """Return the date for the start of the week (Mon or Sun)."""
    if week_starts_on_monday:
        return d - timedelta(days=(d.weekday()))  # Monday=0
    # Week starts on Sunday
    return d - timedelta(days=((d.weekday() + 1) % 7))


def week_dates(start: date) -> List[date]:
    return [start + timedelta(days=i) for i in range(7)]


def money_round(x: float) -> float:
    return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


DAY_NAMES_MON_FIRST = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES_SUN_FIRST = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

DEFAULT_COLUMNS = [
    "Day",
    "Date",
    "HW Done Before Play",
    "Football Practice",
    "Trash Taken Out",
    "Bathroom Clothes Picked Up",
    "Run w/ Mom",
    "Reading (min)",
    "Unity Lessons Done",
    "Notes",
    "Score (0-3)",
    "Daily Earning ($)",
]

YES_NO = ["Yes", "No"]
YES_NO_NA = ["Yes", "No", "N/A"]


def empty_week_dataframe(start: date, week_starts_on_monday: bool = True) -> pd.DataFrame:
    days = DAY_NAMES_MON_FIRST if week_starts_on_monday else DAY_NAMES_SUN_FIRST
    dates = week_dates(start)
    # If Sunday-first, rotate names to match actual dates order
    if not week_starts_on_monday:
        # start is a Sunday in this case
        days = DAY_NAMES_SUN_FIRST
    df = pd.DataFrame({
        "Day": days,
        "Date": [d.isoformat() for d in dates],
        "HW Done Before Play": "",
        "Football Practice": "",
        "Trash Taken Out": "",
        "Bathroom Clothes Picked Up": "",
        "Run w/ Mom": "",
        "Reading (min)": 0,
        "Unity Lessons Done": 0,
        "Notes": "",
        "Score (0-3)": 0,
        "Daily Earning ($)": 0.00,
    })
    return df


def recompute_earnings(df: pd.DataFrame, base_amount: float) -> pd.DataFrame:
    scores = pd.to_numeric(df["Score (0-3)"], errors="coerce").fillna(0)
    earnings = (scores / 3.0) * base_amount
    df["Daily Earning ($)"] = earnings.apply(money_round)
    return df


def compute_summary(df: pd.DataFrame, bonus_amount: float, compliant_threshold: int) -> dict:
    compliant_days = int((pd.to_numeric(df["Score (0-3)"], errors="coerce") == 3).sum())
    sum_earnings = float(pd.to_numeric(df["Daily Earning ($)"], errors="coerce").fillna(0).sum())
    bonus = bonus_amount if compliant_days >= compliant_threshold else 0.0
    payout = money_round(sum_earnings + bonus)
    return {
        "compliant_days": compliant_days,
        "sum_earnings": money_round(sum_earnings),
        "bonus": money_round(bonus),
        "weekly_payout": payout,
    }


def export_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def export_excel_with_formulas(df: pd.DataFrame, base_amount: float, bonus_amount: float, compliant_threshold: int) -> bytes:
    """Create an Excel file that mirrors the app and includes formulas & a Settings sheet."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Settings sheet
        settings_df = pd.DataFrame({
            "Setting": ["Base daily amount", "Weekly bonus", "Compliant threshold (days)"] ,
            "Value": [base_amount, bonus_amount, compliant_threshold],
        })
        settings_df.to_excel(writer, index=False, sheet_name="Settings")

        # Weekly Tracker sheet
        df_to_write = df.copy()
        # We'll put a formula for Daily Earning that references Settings!B2 (base)
        df_to_write.to_excel(writer, index=False, sheet_name="Weekly Tracker", startrow=1)
        wb = writer.book
        ws = writer.sheets["Weekly Tracker"]

        # Formats
        hdr_fmt = wb.add_format({"bold": True, "align": "center", "valign": "vcenter", "border": 1})
        currency_fmt = wb.add_format({"num_format": "$#,##0.00", "border": 1})
        title_fmt = wb.add_format({"bold": True, "font_size": 14})

        # Title & week label
        ws.write(0, 0, "Week of:")
        try:
            first_date = pd.to_datetime(df_to_write["Date"].iloc[0]).date().isoformat()
        except Exception:
            first_date = ""
        ws.write(0, 1, first_date)
        ws.merge_range(0, 2, 0, 6, "Thomas Bingham — Weekly Responsibility Tracker", title_fmt)

        # Header styling
        for col_idx, col_name in enumerate(df_to_write.columns):
            ws.write(1, col_idx, col_name, hdr_fmt)

        # Column widths
        ws.set_column("A:A", 8)
        ws.set_column("B:B", 12)
        ws.set_column("C:F", 22)
        ws.set_column("G:G", 14)
        ws.set_column("H:H", 20)
        ws.set_column("I:I", 28)
        ws.set_column("J:J", 12)
        ws.set_column("K:K", 16)

        # Daily earning formula referencing Settings!B2 (base)
        # Data starts at row=2 (0-indexed) so the first data row is Excel row 3
        n_rows = len(df_to_write)
        for r in range(n_rows):
            excel_row = r + 3  # 1-based + header offset
            formula = f"=ROUND(Settings!$B$2*(J{excel_row}/3),2)"
            ws.write_formula(r + 2, 11, formula, currency_fmt)

        # Summary block on the right
        ws.write(0, 15, "Summary", title_fmt)
        ws.write(1, 15, "Compliant days (Score=3)")
        ws.write_formula(1, 16, f'=COUNTIF(J3:J{n_rows+2},3)')
        ws.write(2, 15, "Sum of daily earnings")
        ws.write_formula(2, 16, f'=SUM(L3:L{n_rows+2})', currency_fmt)
        ws.write(3, 15, "Weekly bonus (if compliant days ≥ Settings!B3)")
        ws.write_formula(3, 16, f'=IF(Q2>=Settings!$B$3,Settings!$B$2*0+Settings!$B$2*0+Settings!$B$2*0+Settings!$B$2*0+{bonus_amount},0)', currency_fmt)
        ws.write(4, 15, "Weekly payout")
        ws.write_formula(4, 16, f'=Q3+Q4', currency_fmt)

        # Print layout
        ws.set_landscape()
        ws.fit_to_pages(1, 1)
        ws.set_margins(left=0.5, right=0.5, top=0.5, bottom=0.5)
        ws.repeat_rows(1, 1)

    return output.getvalue()


# ----------------------------------
# Sidebar — Settings & File I/O
# ----------------------------------
with st.sidebar:
    st.header("Settings")
    week_start_mode = st.radio("Week starts on", ["Monday", "Sunday"], index=0, horizontal=True)
    week_starts_on_monday = (week_start_mode == "Monday")

    today = date.today()
    default_week = week_start(today, week_starts_on_monday)
    week_of = st.date_input("Week of", value=default_week, help="Select the Monday/Sunday for this week.")

    base_amount = st.number_input("Base daily amount ($)", min_value=0.0, step=0.25, value=5.00, format="%0.2f")
    compliant_threshold = st.number_input("Compliant threshold (days)", min_value=1, max_value=7, value=6)
    weekly_bonus = st.number_input("Weekly bonus ($)", min_value=0.0, step=0.25, value=2.00, format="%0.2f")

    st.markdown("---")
    st.subheader("Import / Export")
    uploaded = st.file_uploader("Import CSV or Excel", type=["csv", "xlsx"])
    export_format = st.radio("Export format", ["CSV", "Excel"], index=1, horizontal=True)

    if "trackers" not in st.session_state:
        st.session_state.trackers = {}

    key = f"{week_of.isoformat()}|{'mon' if week_starts_on_monday else 'sun'}"

    if key not in st.session_state.trackers:
        st.session_state.trackers[key] = empty_week_dataframe(week_of, week_starts_on_monday)

    if uploaded is not None:
        if uploaded.name.lower().endswith(".csv"):
            df_in = pd.read_csv(uploaded)
        else:
            df_in = pd.read_excel(uploaded)
        # Basic column alignment
        missing = [c for c in DEFAULT_COLUMNS if c not in df_in.columns]
        for c in missing:
            df_in[c] = "" if c not in ["Reading (min)", "Unity Lessons Done", "Score (0-3)", "Daily Earning ($)"] else 0
        df_in = df_in[DEFAULT_COLUMNS]
        st.session_state.trackers[key] = df_in
        st.success("Imported successfully.")


# -----------------------------
# Main — Editor & Summary
# -----------------------------
st.title("Thomas Bingham — Weekly Responsibility Tracker")
col_a, col_b, col_c = st.columns([2, 1, 1])
with col_a:
    st.write(f"**Week of:** {week_of.isoformat()}  |  **Week starts on:** {'Monday' if week_starts_on_monday else 'Sunday'}")
with col_b:
    st.metric("Base ($/day)", f"${base_amount:0.2f}")
with col_c:
    st.metric("Bonus (>= days)", f"${weekly_bonus:0.2f} (≥{compliant_threshold})")

# Pull df for this week
tracker_df = st.session_state.trackers[key].copy()

# Recompute earnings before showing (keeps numbers consistent)
tracker_df = recompute_earnings(tracker_df, base_amount)

# Column configuration for data editor
col_cfg = {
    "Day": st.column_config.TextColumn(disabled=True, width=80),
    "Date": st.column_config.TextColumn(disabled=True, width=120),
    "HW Done Before Play": st.column_config.SelectboxColumn(options=YES_NO, width=160),
    "Football Practice": st.column_config.SelectboxColumn(options=YES_NO_NA, width=160),
    "Trash Taken Out": st.column_config.SelectboxColumn(options=YES_NO, width=160),
    "Bathroom Clothes Picked Up": st.column_config.SelectboxColumn(options=YES_NO, width=200),
    "Run w/ Mom": st.column_config.SelectboxColumn(options=YES_NO_NA, width=130),
    "Reading (min)": st.column_config.NumberColumn(min_value=0, step=1, width=120),
    "Unity Lessons Done": st.column_config.NumberColumn(min_value=0, step=1, width=140),
    "Notes": st.column_config.TextColumn(width=220),
    "Score (0-3)": st.column_config.NumberColumn(min_value=0, max_value=3, step=1, width=110),
    "Daily Earning ($)": st.column_config.NumberColumn(disabled=True, format="$%0.2f", width=140),
}

st.caption("Fill out each day. Score is manual (0–3). Daily earning is auto-calculated.")
edited_df = st.data_editor(
    tracker_df,
    hide_index=True,
    use_container_width=True,
    column_config=col_cfg,
    num_rows="fixed",
    key=f"editor_{key}",
)

# After editing, recompute earnings again and store
edited_df = recompute_earnings(edited_df, base_amount)
st.session_state.trackers[key] = edited_df.copy()

# Summary metrics
summary = compute_summary(edited_df, weekly_bonus, compliant_threshold)
sm1, sm2, sm3, sm4 = st.columns(4)
sm1.metric("Compliant days (Score=3)", summary["compliant_days"]) 
sm2.metric("Sum of daily earnings", f"${summary['sum_earnings']:0.2f}")
sm3.metric("Bonus added", f"${summary['bonus']:0.2f}")
sm4.metric("Weekly payout (Fun Friday)", f"${summary['weekly_payout']:0.2f}")

# Export buttons
st.markdown("### Export this week")
if export_format == "CSV":
    csv_bytes = export_csv(edited_df)
    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=f"Thomas_Weekly_Tracker_{week_of.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    xlsx_bytes = export_excel_with_formulas(edited_df, base_amount, weekly_bonus, compliant_threshold)
    st.download_button(
        label="Download Excel",
        data=xlsx_bytes,
        file_name=f"Thomas_Weekly_Tracker_{week_of.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# Optional: suggested score helper
with st.expander("Optional: Suggested score helper (purely informational)"):
    st.caption("This suggests a score based on daily fields. You still control the official score.")
    hw_weight = st.slider("Homework weight", 0.0, 1.0, 0.4, 0.05)
    chores_weight = st.slider("Trash + Bathroom weight", 0.0, 1.0, 0.4, 0.05)
    run_weight = st.slider("Run with Mom weight", 0.0, 1.0, 0.1, 0.05)
    read_weight = st.slider("Reading weight", 0.0, 1.0, 0.1, 0.05)

    def suggest_score(row: pd.Series) -> int:
        score = 0.0
        if str(row.get("HW Done Before Play", "")).strip() == "Yes":
            score += 3 * hw_weight
        # chores: trash + bathroom
        if str(row.get("Trash Taken Out", "")).strip() == "Yes":
            score += 1.5 * chores_weight
        if str(row.get("Bathroom Clothes Picked Up", "")).strip() == "Yes":
            score += 1.5 * chores_weight
        # run with mom (N/A => 0.5 credit)
        r = str(row.get("Run w/ Mom", "")).strip()
        if r == "Yes":
            score += 3 * run_weight
        elif r == "N/A":
            score += 1.5 * run_weight
        # reading (>=20 min)
        try:
            mins = int(row.get("Reading (min)", 0))
        except Exception:
            mins = 0
        if mins >= 20:
            score += 3 * read_weight
        # Clamp & round to nearest int in [0,3]
        score = max(0, min(3, int(round(score))))
        return score

    tmp = edited_df.copy()
    tmp["Suggested Score (0-3)"] = tmp.apply(suggest_score, axis=1)
    st.dataframe(tmp[["Day", "Date", "Suggested Score (0-3)"]], use_container_width=True, hide_index=True)

st.success("Ready. Track daily, then pay out on Fun Friday based on the summary above.")

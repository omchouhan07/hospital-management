"""Streamlit dashboard.  Run:  python -m streamlit run dashboard.py"""
from datetime import date

import pandas as pd
import streamlit as st

from analytics import (SLOTS, HospitalError, admit_patient, avg_length_of_stay, bed_occupancy,
                       book_appointment, complete_appointment, department_revenue, discharge_patient,
                       doctor_workload, monthly_visits, readmission_rate)
from db import connect, init_db
from seed import seed

st.set_page_config(page_title="Hospital Dashboard", page_icon="🏥", layout="wide")
conn = connect()
init_db(conn)
seed(conn)


def df(rows):
    return pd.DataFrame([dict(r) for r in rows])


def act(fn, *args, ok):
    """Action chalao; success message rerun ke baad bhi dikhe (session_state)."""
    try:
        res = fn(conn, *args)
        st.session_state["msg"] = ok.format(res)
        st.rerun()
    except HospitalError as exc:
        st.error(str(exc))


st.title("🏥 Hospital Management Dashboard")
if "msg" in st.session_state:
    st.success(st.session_state.pop("msg"))

# ---------- KPIs ----------
occ = conn.execute("SELECT 100.0*SUM(occupied)/COUNT(*) FROM beds").fetchone()[0]
rev = conn.execute("SELECT COALESCE(SUM(amount),0) FROM bills").fetchone()[0]
rr = readmission_rate(conn)
c = st.columns(5)
c[0].metric("Patients", conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0])
c[1].metric("Revenue", f"₹{rev:,.0f}")
c[2].metric("Bed Occupancy", f"{occ:.0f}%")
c[3].metric("Avg Stay (days)", avg_length_of_stay(conn) or 0)
c[4].metric("30-day Readmission", f"{rr['rate_pct'] or 0}%")
st.divider()

# ---------- Charts ----------
l, r = st.columns(2)
with l:
    st.subheader("Monthly Visits")
    m = df(monthly_visits(conn))
    if not m.empty:
        st.line_chart(m.set_index("month")["visits"])
        st.dataframe(m, hide_index=True)
with r:
    st.subheader("Department Revenue")
    d = df(department_revenue(conn))
    if not d.empty:
        st.bar_chart(d.set_index("department")["revenue"])
        st.dataframe(d, hide_index=True)
a, b = st.columns(2)
with a:
    st.subheader("👨‍⚕️ Doctor Workload")
    st.dataframe(df(doctor_workload(conn)), hide_index=True)
with b:
    st.subheader("🛏️ Bed Occupancy by Ward")
    st.dataframe(df(bed_occupancy(conn)), hide_index=True)
    st.dataframe(df(conn.execute("SELECT * FROM v_bed_status").fetchall()), hide_index=True)
st.divider()

# ---------- Actions ----------
patients = {f"{r['name']} (#{r['id']})": r["id"] for r in conn.execute("SELECT id, name FROM patients")}
doctors = {f"{r['name']} - {r['department']}": r["id"] for r in conn.execute(
    "SELECT d.id, d.name, dep.name AS department FROM doctors d JOIN departments dep ON dep.id=d.department_id")}
t1, t2, t3, t4 = st.tabs(["📅 Appointment Book", "✅ Appointment Complete", "🛏️ Admit", "🚪 Discharge"])
with t1:
    x = st.columns(4)
    p = x[0].selectbox("Patient", list(patients), key="bp")
    dr = x[1].selectbox("Doctor", list(doctors))
    dt = x[2].date_input("Date", date.today())
    sl = x[3].selectbox("Slot", SLOTS)
    if st.button("Book Karo", type="primary"):
        act(book_appointment, patients[p], doctors[dr], dt.isoformat(), sl, ok="Appointment #{} book ho gayi!")
with t2:
    pend = {f"#{r['id']} {r['patient']} / {r['doctor']} ({r['appt_date']})": r["id"] for r in conn.execute(
        "SELECT * FROM v_appointments WHERE status='Booked' ORDER BY appt_date DESC LIMIT 50")}
    if pend:
        s = st.selectbox("Pending appointment", list(pend))
        if st.button("Complete + Bill Banao"):
            act(complete_appointment, pend[s], ok="Appointment complete, bill ₹{:,.0f}")
    else:
        st.info("Koi pending appointment nahi.")
with t3:
    free = {f"{r['ward']} #{r['bed_no']} (₹{r['daily_rate']:,.0f}/day)": r["id"] for r in conn.execute(
        "SELECT id, ward, bed_no, daily_rate FROM beds WHERE occupied=0")}
    deps = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM departments")}
    x = st.columns(4)
    p = x[0].selectbox("Patient", list(patients), key="ap")
    bd = x[1].selectbox("Free bed", list(free)) if free else None
    dp = x[2].selectbox("Department", list(deps))
    dg = x[3].text_input("Diagnosis")
    if st.button("Admit Karo", type="primary", disabled=not free):
        act(admit_patient, patients[p], free[bd], deps[dp], dg, ok="Admission #{} ho gaya!")
with t4:
    cur = {f"#{r['id']} {r['name']} (admit: {r['admit_date']})": r["id"] for r in conn.execute(
        "SELECT a.id, p.name, a.admit_date FROM admissions a JOIN patients p ON p.id=a.patient_id "
        "WHERE a.discharge_date IS NULL")}
    if cur:
        s = st.selectbox("Admitted patient", list(cur))
        if st.button("Discharge + Bill"):
            act(discharge_patient, cur[s], ok="Discharge ho gaya, bill ₹{:,.0f}")
    else:
        st.info("Abhi koi patient admit nahi hai.")
st.divider()

# ---------- Export ----------
bills = df(conn.execute("SELECT * FROM v_billing ORDER BY bill_date").fetchall())
st.download_button("⬇️ Billing CSV download", bills.to_csv(index=False).encode("utf-8"),
                   "billing_export.csv", "text/csv")
conn.close()

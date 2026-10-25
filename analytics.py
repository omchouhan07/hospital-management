"""Business logic (atomic transactions) + advanced SQL (CTE, window functions)."""
import sqlite3
from datetime import date
from db import transaction

SLOTS = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00",
         "14:00", "14:30", "15:00", "15:30", "16:00"]


class HospitalError(Exception):
    pass


def book_appointment(conn, patient_id, doctor_id, appt_date, slot):
    try:
        with transaction(conn):
            cur = conn.execute(
                "INSERT INTO appointments(patient_id, doctor_id, appt_date, slot) VALUES (?,?,?,?)",
                (patient_id, doctor_id, appt_date, slot))
            return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise HospitalError("Doctor ka ye slot pehle se booked hai.") from exc
        raise HospitalError(f"Booking fail hui: {exc}") from exc


def complete_appointment(conn, appt_id):
    """Appointment complete + consultation bill, ek saath."""
    with transaction(conn):
        r = conn.execute(
            "SELECT a.status, a.patient_id, a.appt_date, d.fee, d.department_id "
            "FROM appointments a JOIN doctors d ON d.id = a.doctor_id WHERE a.id = ?",
            (appt_id,)).fetchone()
        if r is None:
            raise HospitalError("Appointment exist nahi karti.")
        if r["status"] != "Booked":
            raise HospitalError(f"Appointment already {r['status']} hai.")
        conn.execute("UPDATE appointments SET status='Completed' WHERE id=?", (appt_id,))
        conn.execute("INSERT INTO bills(patient_id, department_id, bill_date, kind, amount) "
                     "VALUES (?,?,?,'Consultation',?)",
                     (r["patient_id"], r["department_id"], r["appt_date"], r["fee"]))
    return r["fee"]


def prescribe(conn, appt_id, medicine_id, qty):
    """Prescription + stock kam + pharmacy bill. Stock kam ho to sab rollback."""
    try:
        with transaction(conn):
            r = conn.execute(
                "SELECT a.patient_id, a.appt_date, d.department_id, m.price "
                "FROM appointments a JOIN doctors d ON d.id = a.doctor_id, medicines m "
                "WHERE a.id = ? AND m.id = ?", (appt_id, medicine_id)).fetchone()
            if r is None:
                raise HospitalError("Appointment ya medicine exist nahi karti.")
            conn.execute("INSERT INTO prescriptions(appointment_id, medicine_id, qty) VALUES (?,?,?)",
                         (appt_id, medicine_id, qty))
            conn.execute("INSERT INTO bills(patient_id, department_id, bill_date, kind, amount) "
                         "VALUES (?,?,?,'Pharmacy',?)",
                         (r["patient_id"], r["department_id"], r["appt_date"], r["price"] * qty))
    except sqlite3.IntegrityError as exc:
        raise HospitalError("Medicine ka stock kam hai (ya qty galat hai).") from exc


def admit_patient(conn, patient_id, bed_id, department_id, diagnosis="", admit_date=None):
    admit_date = admit_date or date.today().isoformat()
    try:
        with transaction(conn):
            if conn.execute("SELECT 1 FROM admissions WHERE patient_id=? AND discharge_date IS NULL",
                            (patient_id,)).fetchone():
                raise HospitalError("Patient pehle se admit hai.")
            cur = conn.execute(
                "INSERT INTO admissions(patient_id, bed_id, department_id, admit_date, diagnosis) "
                "VALUES (?,?,?,?,?)", (patient_id, bed_id, department_id, admit_date, diagnosis))
            return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        if "occupied" in str(exc):
            raise HospitalError("Ye bed already occupied hai.") from exc
        raise HospitalError(f"Admission fail hua: {exc}") from exc


def discharge_patient(conn, admission_id, discharge_date=None):
    """Discharge + bed free (trigger) + bill = days x bed rate (kam se kam 1 din)."""
    discharge_date = discharge_date or date.today().isoformat()
    with transaction(conn):
        r = conn.execute(
            "SELECT a.patient_id, a.department_id, a.admit_date, a.discharge_date, b.daily_rate "
            "FROM admissions a JOIN beds b ON b.id = a.bed_id WHERE a.id = ?",
            (admission_id,)).fetchone()
        if r is None:
            raise HospitalError("Admission exist nahi karti.")
        if r["discharge_date"]:
            raise HospitalError("Patient pehle hi discharge ho chuka hai.")
        days = (date.fromisoformat(discharge_date) - date.fromisoformat(r["admit_date"])).days
        if days < 0:
            raise HospitalError("Discharge date admit date se pehle nahi ho sakti.")
        amount = max(1, days) * r["daily_rate"]
        conn.execute("UPDATE admissions SET discharge_date=? WHERE id=?", (discharge_date, admission_id))
        conn.execute("INSERT INTO bills(patient_id, department_id, bill_date, kind, amount) "
                     "VALUES (?,?,?,'Admission',?)",
                     (r["patient_id"], r["department_id"], discharge_date, amount))
    return amount


# ---------------- Analytics ----------------
def doctor_workload(conn):
    return conn.execute("""
    WITH w AS (
        SELECT d.id, d.name AS doctor, dep.name AS department,
               COUNT(a.id) AS appointments,
               COALESCE(SUM(a.status = 'Completed'), 0) AS completed
        FROM doctors d JOIN departments dep ON dep.id = d.department_id
        LEFT JOIN appointments a ON a.doctor_id = d.id GROUP BY d.id)
    SELECT doctor, department, appointments, completed,
           RANK() OVER (ORDER BY appointments DESC) AS rnk
    FROM w ORDER BY rnk, doctor""").fetchall()


def department_revenue(conn):
    return conn.execute("""
    SELECT dep.name AS department, ROUND(SUM(b.amount), 2) AS revenue,
           ROUND(100.0 * SUM(b.amount) / SUM(SUM(b.amount)) OVER (), 1) AS share_pct
    FROM bills b JOIN departments dep ON dep.id = b.department_id
    GROUP BY dep.id ORDER BY revenue DESC""").fetchall()


def bed_occupancy(conn):
    return conn.execute("""
    SELECT ward, COUNT(*) AS beds, SUM(occupied) AS occupied,
           ROUND(100.0 * SUM(occupied) / COUNT(*), 1) AS occupancy_pct
    FROM beds GROUP BY ward ORDER BY ward""").fetchall()


def avg_length_of_stay(conn):
    return conn.execute(
        "SELECT ROUND(AVG(julianday(discharge_date) - julianday(admit_date)), 1) "
        "FROM admissions WHERE discharge_date IS NOT NULL").fetchone()[0]


def readmission_rate(conn):
    """30 din ke andar dobara admit hone wale patients (LAG window)."""
    return conn.execute("""
    WITH g AS (
        SELECT patient_id, admit_date,
               LAG(discharge_date) OVER (PARTITION BY patient_id ORDER BY admit_date) AS prev_dis
        FROM admissions)
    SELECT COUNT(*) AS admissions,
           COALESCE(SUM(prev_dis IS NOT NULL AND julianday(admit_date) - julianday(prev_dis) <= 30), 0) AS readmitted,
           ROUND(100.0 * SUM(prev_dis IS NOT NULL AND julianday(admit_date) - julianday(prev_dis) <= 30)
                 / COUNT(*), 1) AS rate_pct
    FROM g""").fetchone()


def monthly_visits(conn):
    return conn.execute("""
    WITH m AS (SELECT substr(appt_date, 1, 7) AS month, COUNT(*) AS visits
               FROM appointments WHERE status != 'Cancelled' GROUP BY month)
    SELECT month, visits,
           ROUND(100.0 * (visits - LAG(visits) OVER (ORDER BY month))
                 / LAG(visits) OVER (ORDER BY month), 1) AS growth_pct
    FROM m ORDER BY month""").fetchall()

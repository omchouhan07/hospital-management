"""Demo data (fixed random seed => har baar same data)."""
import random
from datetime import date, timedelta
from analytics import SLOTS, HospitalError, admit_patient, book_appointment, \
    complete_appointment, discharge_patient, prescribe

DEPTS = ["Cardiology", "Orthopedics", "Pediatrics", "Neurology", "General Medicine"]
DOCTORS = ["Dr. Sharma", "Dr. Verma", "Dr. Khan", "Dr. Iyer", "Dr. Gupta",
           "Dr. Mehta", "Dr. Joshi", "Dr. Nair", "Dr. Singh", "Dr. Patel"]
FIRST = ["Aarav", "Riya", "Kabir", "Ananya", "Vivaan", "Isha", "Rohan", "Meera",
         "Arjun", "Sneha", "Dev", "Kavya", "Om", "Pooja", "Nikhil", "Tanvi"]
LAST = ["Jain", "Rao", "Yadav", "Das", "Kapoor", "Bose", "Chauhan", "Pillai"]
CITIES = ["Bhopal", "Indore", "Delhi", "Mumbai", "Pune", "Jaipur"]
MEDS = [("Paracetamol", 20), ("Amoxicillin", 90), ("Cetirizine", 35),
        ("Pantoprazole", 60), ("Metformin", 45), ("Atorvastatin", 110)]
DIAG = ["Fever", "Fracture", "Chest pain", "Migraine", "Infection", "Checkup"]


def seed(conn, n_appts=200, n_adm=60):
    if conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]:
        return 0
    rnd = random.Random(42)
    conn.executemany("INSERT INTO departments(name) VALUES (?)", [(d,) for d in DEPTS])
    conn.executemany("INSERT INTO doctors(name, department_id, fee) VALUES (?,?,?)",
                     [(n, i % len(DEPTS) + 1, rnd.choice([500, 700, 1000, 1500]))
                      for i, n in enumerate(DOCTORS)])
    conn.executemany("INSERT INTO patients(name, gender, phone, city) VALUES (?,?,?,?)",
                     [(f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", rnd.choice("MF"),
                       f"9{rnd.randint(10**8, 10**9 - 1)}", rnd.choice(CITIES)) for _ in range(40)])
    beds = [("General", i, 1500) for i in range(1, 9)] + [("ICU", i, 6000) for i in range(1, 5)] \
        + [("Private", i, 3500) for i in range(1, 7)]
    conn.executemany("INSERT INTO beds(ward, bed_no, daily_rate) VALUES (?,?,?)", beds)
    conn.executemany("INSERT INTO medicines(name, price, stock) VALUES (?,?,?)",
                     [(n, p, rnd.randint(500, 1000)) for n, p in MEDS])
    conn.commit()

    today, start = date.today(), date.today() - timedelta(days=150)
    made = 0
    for _ in range(n_appts):
        d = (start + timedelta(days=rnd.randint(0, 149))).isoformat()
        try:
            aid = book_appointment(conn, rnd.randint(1, 40), rnd.randint(1, 10), d, rnd.choice(SLOTS))
        except HospitalError:
            continue
        made += 1
        x = rnd.random()
        if x < 0.85:
            complete_appointment(conn, aid)
            if rnd.random() < 0.4:
                prescribe(conn, aid, rnd.randint(1, 6), rnd.randint(1, 3))
        elif x < 0.95:
            conn.execute("UPDATE appointments SET status='Cancelled' WHERE id=?", (aid,))
    conn.commit()

    last_out = {}
    for i in range(n_adm):
        d = start + timedelta(days=i * 2 + rnd.randint(0, 1))
        pid = rnd.randint(1, 20)  # chhota pool => readmissions bhi banenge
        if d.isoformat() < last_out.get(pid, ""):
            continue
        free = [r[0] for r in conn.execute("SELECT id FROM beds WHERE occupied = 0")]
        if not free:
            continue
        try:
            adm = admit_patient(conn, pid, rnd.choice(free), rnd.randint(1, 5),
                                rnd.choice(DIAG), d.isoformat())
        except HospitalError:
            continue
        out = d + timedelta(days=rnd.randint(1, 10))
        if out <= today:  # baaki kuch patients abhi admit rehne do
            discharge_patient(conn, adm, out.isoformat())
            last_out[pid] = out.isoformat()
        else:
            last_out[pid] = "9999"
    return made

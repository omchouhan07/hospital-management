PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    fee REAL NOT NULL CHECK (fee > 0));
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL,
    phone TEXT, city TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS beds (
    id INTEGER PRIMARY KEY, ward TEXT NOT NULL, bed_no INTEGER NOT NULL,
    daily_rate REAL NOT NULL CHECK (daily_rate > 0),
    occupied INTEGER NOT NULL DEFAULT 0 CHECK (occupied IN (0,1)),
    UNIQUE (ward, bed_no));
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    doctor_id  INTEGER NOT NULL REFERENCES doctors(id),
    appt_date TEXT NOT NULL, slot TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Booked' CHECK (status IN ('Booked','Completed','Cancelled')),
    UNIQUE (doctor_id, appt_date, slot));   -- double booking yahin rukti hai
CREATE TABLE IF NOT EXISTS admissions (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    bed_id INTEGER NOT NULL REFERENCES beds(id),
    department_id INTEGER NOT NULL REFERENCES departments(id),
    admit_date TEXT NOT NULL, discharge_date TEXT, diagnosis TEXT);
CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    department_id INTEGER NOT NULL REFERENCES departments(id),
    bill_date TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('Consultation','Admission','Pharmacy')),
    amount REAL NOT NULL CHECK (amount >= 0));
CREATE TABLE IF NOT EXISTS medicines (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    price REAL NOT NULL CHECK (price > 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0));
CREATE TABLE IF NOT EXISTS prescriptions (
    id INTEGER PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES appointments(id),
    medicine_id INTEGER NOT NULL REFERENCES medicines(id),
    qty INTEGER NOT NULL CHECK (qty > 0));
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (datetime('now')),
    action TEXT NOT NULL, detail TEXT);

CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments(appt_date);
CREATE INDEX IF NOT EXISTS idx_adm_patient ON admissions(patient_id);
CREATE INDEX IF NOT EXISTS idx_bills_dept ON bills(department_id);

-- Occupied bed par admission nahi hogi
CREATE TRIGGER IF NOT EXISTS trg_bed_check BEFORE INSERT ON admissions
WHEN (SELECT occupied FROM beds WHERE id = NEW.bed_id) = 1
BEGIN SELECT RAISE(ABORT, 'Bed already occupied'); END;
CREATE TRIGGER IF NOT EXISTS trg_bed_occupy AFTER INSERT ON admissions
BEGIN
    UPDATE beds SET occupied = 1 WHERE id = NEW.bed_id;
    INSERT INTO audit_log(action, detail) VALUES ('ADMIT', 'patient ' || NEW.patient_id || ' bed ' || NEW.bed_id);
END;
-- Discharge hote hi bed free
CREATE TRIGGER IF NOT EXISTS trg_bed_free AFTER UPDATE OF discharge_date ON admissions
WHEN OLD.discharge_date IS NULL AND NEW.discharge_date IS NOT NULL
BEGIN
    UPDATE beds SET occupied = 0 WHERE id = NEW.bed_id;
    INSERT INTO audit_log(action, detail) VALUES ('DISCHARGE', 'admission ' || NEW.id);
END;
-- Medicine stock apne aap kam; kam pada to CHECK error + rollback
CREATE TRIGGER IF NOT EXISTS trg_reduce_med BEFORE INSERT ON prescriptions
BEGIN UPDATE medicines SET stock = stock - NEW.qty WHERE id = NEW.medicine_id; END;
CREATE TRIGGER IF NOT EXISTS trg_audit_appt AFTER INSERT ON appointments
BEGIN INSERT INTO audit_log(action, detail)
      VALUES ('BOOK', 'doctor ' || NEW.doctor_id || ' ' || NEW.appt_date || ' ' || NEW.slot); END;

CREATE VIEW IF NOT EXISTS v_appointments AS
SELECT a.id, a.appt_date, a.slot, a.status, p.name AS patient, d.name AS doctor, dep.name AS department
FROM appointments a JOIN patients p ON p.id = a.patient_id
JOIN doctors d ON d.id = a.doctor_id JOIN departments dep ON dep.id = d.department_id;
CREATE VIEW IF NOT EXISTS v_bed_status AS
SELECT b.id, b.ward, b.bed_no, b.daily_rate, b.occupied, p.name AS patient, a.admit_date
FROM beds b LEFT JOIN admissions a ON a.bed_id = b.id AND a.discharge_date IS NULL
LEFT JOIN patients p ON p.id = a.patient_id;
CREATE VIEW IF NOT EXISTS v_billing AS
SELECT b.id, b.bill_date, p.name AS patient, dep.name AS department, b.kind, b.amount
FROM bills b JOIN patients p ON p.id = b.patient_id JOIN departments dep ON dep.id = b.department_id;

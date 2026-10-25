import unittest
from analytics import (HospitalError, admit_patient, avg_length_of_stay, bed_occupancy,
                       book_appointment, department_revenue, discharge_patient, doctor_workload,
                       monthly_visits, prescribe, readmission_rate)
from db import connect, init_db
from seed import seed


class HospitalTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_db(self.conn)
        seed(self.conn)

    def q(self, sql, *a):
        return self.conn.execute(sql, a).fetchone()[0]

    def free_patients(self, n):
        return [r[0] for r in self.conn.execute(
            "SELECT id FROM patients WHERE id NOT IN "
            "(SELECT patient_id FROM admissions WHERE discharge_date IS NULL) LIMIT ?", (n,))]

    def test_double_booking_blocked(self):
        book_appointment(self.conn, 1, 1, "2099-01-01", "10:00")
        with self.assertRaises(HospitalError):
            book_appointment(self.conn, 2, 1, "2099-01-01", "10:00")

    def test_bed_occupied_and_discharge(self):
        p1, p2 = self.free_patients(2)
        bed = self.q("SELECT id FROM beds WHERE occupied = 0 LIMIT 1")
        adm = admit_patient(self.conn, p1, bed, 1, "Test", "2099-01-01")
        self.assertEqual(self.q("SELECT occupied FROM beds WHERE id=?", bed), 1)
        with self.assertRaises(HospitalError):
            admit_patient(self.conn, p2, bed, 1, "Test", "2099-01-01")
        amount = discharge_patient(self.conn, adm, "2099-01-04")
        rate = self.q("SELECT daily_rate FROM beds WHERE id=?", bed)
        self.assertEqual(amount, 3 * rate)
        self.assertEqual(self.q("SELECT occupied FROM beds WHERE id=?", bed), 0)

    def test_stock_reduces_and_rolls_back(self):
        aid = book_appointment(self.conn, 1, 1, "2099-02-01", "09:00")
        before = self.q("SELECT stock FROM medicines WHERE id=1")
        prescribe(self.conn, aid, 1, 2)
        self.assertEqual(self.q("SELECT stock FROM medicines WHERE id=1"), before - 2)
        n_bills = self.q("SELECT COUNT(*) FROM bills")
        with self.assertRaises(HospitalError):
            prescribe(self.conn, aid, 1, 10 ** 6)
        self.assertEqual(self.q("SELECT stock FROM medicines WHERE id=1"), before - 2)
        self.assertEqual(self.q("SELECT COUNT(*) FROM bills"), n_bills)

    def test_readmission(self):
        c = self.conn
        c.execute("DELETE FROM admissions"); c.execute("UPDATE beds SET occupied=0"); c.commit()
        a = admit_patient(c, 1, 1, 1, "x", "2090-01-01"); discharge_patient(c, a, "2090-01-05")
        a = admit_patient(c, 1, 1, 1, "x", "2090-01-20"); discharge_patient(c, a, "2090-01-22")
        a = admit_patient(c, 1, 1, 1, "x", "2090-06-01"); discharge_patient(c, a, "2090-06-02")
        r = readmission_rate(c)
        self.assertEqual((r["admissions"], r["readmitted"]), (3, 1))

    def test_reports(self):
        self.assertTrue(doctor_workload(self.conn))
        self.assertAlmostEqual(sum(r["share_pct"] for r in department_revenue(self.conn)), 100, delta=0.5)
        self.assertTrue(bed_occupancy(self.conn) and monthly_visits(self.conn))
        self.assertIsNotNone(avg_length_of_stay(self.conn))


if __name__ == "__main__":
    unittest.main()

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestAnalisis(MurabahahCommon):
    """Feasibility analysis (DSR) and conflict-of-interest rules for approvals."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.murabahah_max_dsr = 40.0
        cls.company.murabahah_pengurus_limit = 0.0
        cls.user_pengurus2 = new_test_user(cls.env, login='kt_pengurus2', groups='koperasi_base.group_koperasi_pengurus')
        # A board member who is also a member of the cooperative, linked to his Odoo account
        cls.pengurus_member = cls.env['res.partner'].create({
            'name': 'TEST Pengurus', 'koperasi_status': 'anggota', 'koperasi_member_no': 'KTAGG02',
            'koperasi_is_pengurus': True, 'koperasi_user_id': cls.user_pengurus.id})

    def test_dsr(self):
        akad = self.create_akad()  # installment 900.000
        akad.write({'monthly_income': 3000000, 'other_obligations': 300000})
        self.assertEqual(akad.total_monthly_obligation, 1200000)
        self.assertAlmostEqual(akad.dsr, 40.0, places=1)
        self.assertFalse(akad.dsr_over_limit)
        self.activate(self.create_akad())  # another active contract of the same member: 900.000 / month
        akad.invalidate_recordset()
        self.assertEqual(akad.existing_installments, 900000)
        self.assertAlmostEqual(akad.dsr, 70.0, places=1)
        self.assertTrue(akad.dsr_over_limit)

    def test_approval_requires_analysis_and_reasons(self):
        akad = self.create_akad()
        akad.write({'monthly_income': 0, 'officer_recommendation': False})
        with self.assertRaises(UserError):  # no analysis
            akad.with_user(self.user_pengurus).action_approve()
        akad.write({'monthly_income': 1500000, 'officer_recommendation': 'layak'})  # DSR 60%
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).action_approve()
        akad.write({'approval_note': 'Disetujui rapat pengurus 1/1/2026: ada penghasilan tambahan dari usaha.'})
        akad.with_user(self.user_pengurus).action_approve()
        self.assertEqual((akad.state, akad.approved_by_id), ('disetujui', self.user_pengurus))
        self.assertTrue(akad.approval_date and akad.analysis_date)
        with self.assertRaises(UserError):  # analysis fixed once approved
            akad.with_user(self.user_pengurus).write({'monthly_income': 5000000})
        akad.with_user(self.user_pengurus).action_reset_draft()
        self.assertFalse(akad.approved_by_id)
        akad.write({'monthly_income': 5000000})

    def test_not_feasible_needs_reason(self):
        akad = self.create_akad()
        akad.officer_recommendation = 'tidak_layak'
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).action_approve()
        akad.approval_note = 'Ada penjamin.'
        akad.with_user(self.user_pengurus).action_approve()

    def test_conflict_of_interest(self):
        akad = self.create_akad(partner=self.pengurus_member)
        self.assertTrue(akad.is_pengurus_financing)
        akad.approval_note = 'Keputusan rapat pengurus dan pengawas tanggal 5/1/2026.'
        with self.assertRaises(UserError):  # own financing
            akad.with_user(self.user_pengurus).action_approve()
        akad.approval_note = False
        with self.assertRaises(UserError):  # board member's financing needs a basis
            akad.with_user(self.user_pengurus2).action_approve()
        akad.approval_note = 'Keputusan rapat pengurus dan pengawas tanggal 5/1/2026.'
        akad.with_user(self.user_pengurus2).action_approve()
        self.assertEqual(akad.approved_by_id, self.user_pengurus2)
        akad.with_user(self.user_petugas)._record_down_payment(akad.date_akad, self.journal_cash)
        akad.with_user(self.user_petugas)._record_purchase(akad.date_akad, 'kas', self.journal_cash)
        with self.assertRaises(UserError):  # cannot sign his own contract either
            akad.with_user(self.user_pengurus).action_activate()
        akad.with_user(self.user_pengurus2).action_activate()
        with self.assertRaises(UserError):  # no discount on own financing
            akad.with_user(self.user_pengurus)._register_payment(
                date(2026, 2, 10), self.journal_cash, amount=850000, discount=50000,
                discount_type='tepat_waktu', discount_note='x')
        with self.assertRaises(UserError):  # no rescheduling of own financing
            akad.with_user(self.user_pengurus)._reschedule(date(2026, 2, 1), date(2026, 3, 1), 'x', count=6)
        # paying his own installment is fine
        self.pay(akad, 900000)
        self.assert_invariants(akad)

    def test_own_contact_is_detected(self):
        akad = self.create_akad(partner=self.user_pengurus.partner_id)
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).action_approve()

    def test_pengurus_limit(self):
        self.company.murabahah_pengurus_limit = 15000000
        note = 'Keputusan rapat pengurus.'
        first = self.create_akad(partner=self.pengurus_member)  # debt 10.800.000
        first.approval_note = note
        first.with_user(self.user_pengurus2).action_approve()
        second = self.create_akad(partner=self.pengurus_member)
        second.approval_note = note
        with self.assertRaises(UserError):  # 10.800.000 + 10.800.000 > 15.000.000
            second.with_user(self.user_pengurus2).action_approve()
        small = self.create_akad(partner=self.pengurus_member, cost=4000000, dp=0)  # debt 4.800.000 -> 15.600.000
        small.approval_note = note
        with self.assertRaises(UserError):
            small.with_user(self.user_pengurus2).action_approve()
        self.company.murabahah_pengurus_limit = 16000000
        small.with_user(self.user_pengurus2).action_approve()

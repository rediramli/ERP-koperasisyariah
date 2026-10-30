from datetime import date

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestMurabahahFlow(MurabahahCommon):

    def test_activation_journal(self):
        akad = self.activate(self.create_akad())
        self.assertEqual(akad.state, 'aktif')
        move = akad.akad_move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.journal_general)
        by_account = {}
        for line in move.line_ids:
            by_account.setdefault(line.account_id, 0.0)
            by_account[line.account_id] += line.balance
        # Dr Piutang 11.450.000 - Cr Piutang (uang muka) 650.000
        self.assertEqual(by_account[self.acc_receivable], 10800000)
        self.assertEqual(by_account[self.acc_inventory], -9650000)
        self.assertEqual(by_account[self.acc_deferred], -1800000)
        self.assertEqual(by_account[self.acc_down_payment], 650000)
        # Purchase and down payment cleared: inventory and down payment liability back to zero
        self.assertEqual(self.ledger(akad, self.acc_inventory), 0)
        self.assertEqual(self.ledger(akad, self.acc_down_payment), 0)
        self.assert_invariants(akad)

    def test_activation_requires_goods_and_down_payment(self):
        akad = self.create_akad()
        akad.with_user(self.user_pengurus).action_approve()
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).action_activate()
        akad.with_user(self.user_petugas)._record_purchase(akad.date_akad, 'kas', self.journal_cash)
        with self.assertRaises(UserError):
            # down payment not received yet
            akad.with_user(self.user_pengurus).action_activate()

    def test_vendor_bill_purchase(self):
        akad = self.activate(self.create_akad(), purchase_mode='utang')
        bill = akad.purchase_move_id
        self.assertEqual(bill.move_type, 'in_invoice')
        self.assertEqual(bill.amount_total, 9650000)
        self.assertEqual(self.ledger(akad, self.acc_inventory), 0)

    def test_installments_oldest_first_until_paid(self):
        akad = self.activate(self.create_akad())
        lines = akad.line_ids.sorted('sequence')
        payment = self.pay(akad, 900000)
        self.assertEqual(payment.amount_principal, 750000)
        self.assertEqual(payment.amount_margin, 150000)
        self.assertEqual(lines[0].state, 'lunas')
        # Cash entry and margin recognition entry
        self.assertEqual(payment.move_id.journal_id, self.journal_cash)
        self.assertEqual(self.ledger(akad, self.acc_cash) - (-9650000 + 650000), 900000)
        self.assertEqual(-sum(payment.margin_move_id.line_ids.filtered(
            lambda l: l.account_id == self.acc_income).mapped('balance')), 150000)
        self.assert_invariants(akad)

        # Partial payment: margin recognised proportionally
        payment = self.pay(akad, 450000)
        self.assertEqual(lines[1].state, 'sebagian')
        self.assertEqual(payment.amount_margin, 75000)
        self.assert_invariants(akad)

        # Payment over two installments: finishes the 2nd, then the 3rd
        payment = self.pay(akad, 1350000)
        self.assertEqual(payment.line_ids.mapped('angsuran_id'), lines[1] | lines[2])
        self.assertEqual(lines[1].state, 'lunas')
        self.assertEqual(lines[2].state, 'lunas')
        self.assert_invariants(akad)

        # Pay the rest one by one
        for line in lines[3:]:
            self.pay(akad, line.residual)
            self.assert_invariants(akad)
        self.assertEqual(akad.state, 'lunas')
        self.assertEqual(akad.remaining_receivable, 0)
        self.assertEqual(akad.remaining_margin, 0)
        self.assertEqual(-self.ledger(akad, self.acc_income), 1800000)
        self.assert_invariants(akad)

    def test_uneven_schedule_paid_off(self):
        # Example: 12.500.000 over 15 months (833.333 + remainder)
        akad = self.activate(self.create_akad(cost=13000000, dp=3000000, pct=25.0, tenor=15,
                                              partner=self.non_member))
        self.assertEqual(akad.installment_amount, 833333)
        while akad.state == 'aktif':
            self.pay(akad, min(833333, akad.remaining_receivable))
        self.assertEqual(-self.ledger(akad, self.acc_income), 2500000)
        self.assert_invariants(akad)

    def test_overpayment_rejected(self):
        akad = self.activate(self.create_akad())
        with self.assertRaises(UserError):
            self.pay(akad, akad.remaining_receivable + 1)

    def test_tazir_goes_to_charity(self):
        akad = self.create_akad()
        akad.tazir_terms = 'Rp 25.000 per angsuran yang terlambat lebih dari 7 hari.'
        self.activate(akad)
        payment = self.pay(akad, 900000, tazir=25000)
        self.assertEqual(payment.amount_cash, 925000)
        self.assertEqual(self.ledger(akad, self.acc_charity), -25000)
        self.assertEqual(-self.ledger(akad, self.acc_income), 150000)
        self.assert_invariants(akad)

    def test_early_payoff_with_discount(self):
        akad = self.activate(self.create_akad())
        self.pay(akad, 900000 * 3)
        remaining_margin = akad.remaining_margin
        self.assertEqual(remaining_margin, 1800000 - 450000)
        # Petugas may not do an early payoff
        with self.assertRaises(UserError):
            akad.with_user(self.user_petugas).action_open_payoff_wizard()
        wizard = self.env['koperasi.murabahah.payoff.wizard'].with_user(self.user_pengurus).create({
            'akad_id': akad.id, 'date': date(2026, 5, 10), 'journal_id': self.journal_cash.id,
            'discount_policy': 'manual', 'manual_discount': 500000, 'discount_note': 'Disetujui rapat pengurus'})
        self.assertEqual(wizard.amount_to_pay, akad.remaining_receivable - 500000)
        wizard.action_confirm()
        self.assertEqual(akad.state, 'lunas')
        payment = akad.payment_ids.filtered(lambda p: p.payment_type == 'pelunasan')
        self.assertEqual(payment.amount_discount, 500000)
        self.assertEqual(payment.amount, 10800000 - 2700000 - 500000)
        # Income = all margin except the discount
        self.assertEqual(-self.ledger(akad, self.acc_income), 1800000 - 500000)
        self.assert_invariants(akad)

    def test_early_payoff_discount_limited(self):
        akad = self.activate(self.create_akad())
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus)._register_payment(
                date(2026, 2, 10), self.journal_cash, payoff=True, discount=akad.remaining_margin + 1)

    def test_active_numbers_locked(self):
        akad = self.activate(self.create_akad())
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).write({'cost_price': 1})
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).write({'tenor': 24})
        with self.assertRaises(UserError):
            akad.line_ids[0].with_user(self.user_pengurus).write({'amount_margin': 1})

    def test_group_rights(self):
        akad = self.create_akad()
        with self.assertRaises(UserError):
            akad.with_user(self.user_petugas).action_approve()
        with self.assertRaises(AccessError):
            akad.with_user(self.user_akuntan).write({'note': 'x'})
        akad.with_user(self.user_akuntan).read(['name', 'remaining_receivable'])

    def test_cancel_payment_and_akad(self):
        akad = self.activate(self.create_akad())
        first = self.pay(akad, 900000)
        second = self.pay(akad, 900000, pay_date=date(2026, 3, 10))
        with self.assertRaises(UserError):
            first.with_user(self.user_pengurus).action_cancel()  # newer payment exists
        second.with_user(self.user_pengurus).action_cancel()
        self.assertEqual(second.state, 'cancel')
        self.assertEqual(akad.remaining_receivable, 10800000 - 900000)
        self.assert_invariants(akad)
        first.with_user(self.user_pengurus).action_cancel()
        self.assert_invariants(akad)
        akad.with_user(self.user_pengurus).action_cancel()
        self.assertEqual(akad.state, 'batal')
        self.assertEqual(self.ledger(akad, self.acc_receivable), 0)
        self.assertEqual(self.ledger(akad, self.acc_deferred), 0)

    def test_payment_wizard_preview(self):
        # Contract signed today: nothing overdue, so the default amount is the first installment
        akad = self.activate(self.create_akad(date_akad=fields.Date.today()))
        wizard = self.env['koperasi.murabahah.payment.wizard'].with_user(self.user_petugas).with_context(
            default_akad_id=akad.id).create({'date': date(2026, 2, 10)})
        self.assertEqual(wizard.journal_id, self.journal_cash)
        self.assertEqual(wizard.amount, 900000)
        self.assertEqual(wizard.preview_margin, 150000)
        wizard.action_confirm()
        self.assertEqual(akad.amount_paid, 900000)

    def test_arrears_and_collectibility(self):
        akad = self.activate(self.create_akad(date_akad=date(2026, 1, 10)))
        akad = akad.with_context(tz='Asia/Jakarta')
        # First due 10 Feb 2026; on 15 Apr 2026 three installments are due, the oldest 64 days late
        with self.patch_today('2026-04-15'):
            akad.invalidate_recordset()
            self.assertEqual(akad.arrears_count, 3)
            self.assertEqual(akad.arrears_amount, 2700000)
            self.assertEqual(akad.arrears_days, 64)
            self.assertEqual(akad.collectibility, 'dpk')
            self.assertIn(akad, akad.search([('arrears_amount', '>', 0)]))

    def patch_today(self, day):
        from unittest.mock import patch
        return patch.object(fields.Date, 'context_today', lambda *a, **k: fields.Date.to_date(day))

    def test_report_renders(self):
        akad = self.activate(self.create_akad())
        self.pay(akad, 900000)
        html, _type = self.env['ir.actions.report']._render_qweb_html(
            'koperasi_murabahah.report_kartu_angsuran', akad.ids)
        self.assertIn(akad.name.encode(), html)
        html, _type = self.env['ir.actions.report']._render_qweb_html(
            'koperasi_murabahah.report_akad_list', akad.ids)
        self.assertIn(b'Daftar Akad', html)

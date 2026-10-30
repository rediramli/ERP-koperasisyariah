from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestWakalahAndDownPayment(MurabahahCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acc_real_cost = cls.env['account.account'].create({
            'code': 'KT811001', 'name': 'TEST Pendapatan Biaya Riil', 'account_type': 'income_other',
            'company_ids': [(6, 0, cls.company.ids)]})
        cls.company.murabahah_real_cost_account_id = cls.acc_real_cost

    def html(self, report, akad):
        content, _type = self.env['ir.actions.report']._render_qweb_html('koperasi_murabahah.%s' % report, akad.ids)
        return content.decode()

    # ------------------------------------------------------------------ cost breakdown
    def test_cost_breakdown(self):
        # Example: price 13.000.000 - discount 1.200.000 = acquisition cost 11.800.000
        with Form(self.env['koperasi.murabahah.akad'].with_user(self.user_petugas)) as form:
            form.partner_id = self.member
            form.product_desc = 'iPhone 15'
            form.purchase_price = 13000000
            form.supplier_discount = 1200000
            form.down_payment = 3000000
            form.tenor = 10
            form.monthly_income = 8000000
            form.officer_recommendation = 'layak'
            self.assertEqual(form.cost_price, 11800000)
        akad = form.save()
        self.assertEqual((akad.cost_price, akad.margin_amount, akad.sale_price), (11800000, 1760000, 13560000))
        html = self.html('report_akad_murabahah', akad)
        self.assertIn('Harga pokok pembelian', html)
        self.assertIn('-Rp 1.200.000', html)
        with self.assertRaises(ValidationError):
            akad.write({'direct_cost': 50000})  # no longer adds up to the acquisition cost
        akad.write({'direct_cost': 50000, 'cost_price': 11850000})
        akad.with_user(self.user_pengurus).action_approve()
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).write({'supplier_discount': 0})  # contract numbers fixed

    def test_no_breakdown_keeps_single_cost(self):
        akad = self.create_akad()
        self.assertFalse(akad._has_cost_breakdown())
        self.assertEqual(akad.cost_price, 9650000)
        self.assertNotIn('Harga pokok pembelian', self.html('report_akad_murabahah', akad))

    # ------------------------------------------------------------------ wa'd / wakalah
    def test_wakalah_order(self):
        akad = self.create_akad()
        akad.write({'purchase_method': 'wakalah', 'wad_date': date(2026, 1, 5)})
        akad.with_user(self.user_pengurus).action_approve()
        with self.assertRaises(UserError):   # no wakalah yet
            akad.with_user(self.user_petugas)._record_purchase(date(2026, 1, 8), 'kas', self.journal_cash)
        akad.write({'wakalah_date': date(2026, 1, 9), 'wakil_id': self.member.id})
        with self.assertRaises(UserError):   # wakalah after the purchase
            akad.with_user(self.user_petugas)._record_purchase(date(2026, 1, 8), 'kas', self.journal_cash)
        akad.write({'wakalah_max_price': 9000000})
        with self.assertRaises(UserError):   # above the price limit given to the agent
            akad.with_user(self.user_petugas)._record_purchase(date(2026, 1, 9), 'kas', self.journal_cash)
        akad.write({'wakalah_max_price': 10000000})
        akad.with_user(self.user_petugas)._record_down_payment(date(2026, 1, 9), self.journal_cash)
        akad.with_user(self.user_petugas)._record_purchase(date(2026, 1, 9), 'kas', self.journal_cash)
        akad.with_user(self.user_pengurus).action_activate()
        self.assertEqual(akad.state, 'aktif')
        self.assert_invariants(akad)
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).write({'wakalah_scope': 'ubah'})

        html = self.html('report_wakalah', akad)
        for text in ['AKAD WAKALAH PEMBELIAN BARANG', '%s/WKL' % akad.name, 'TEST Anggota', 'Rp 10.000.000',
                     'TEST Pemasok', '9 Januari 2026']:
            self.assertIn(text, html)
        self.assertNotIn('tidak memakai wakalah', html)
        html = self.html('report_wad', akad)
        for text in ['SURAT JANJI PEMBELIAN', '5 Januari 2026', 'biaya riil', 'Rp 650.000']:
            self.assertIn(text, html)
        html = self.html('report_akad_murabahah', akad)
        self.assertIn('sebagai wakil KOPERASI berdasarkan Akad Wakalah tanggal 9 Januari 2026', html)
        self.assertIn('pada tanggal 5 Januari 2026', html)

    def test_goods_owned_before_contract(self):
        akad = self.create_akad(date_akad=date(2026, 1, 10))
        akad.with_user(self.user_pengurus).action_approve()
        akad.with_user(self.user_petugas)._record_down_payment(date(2026, 1, 10), self.journal_cash)
        akad.with_user(self.user_petugas)._record_purchase(date(2026, 1, 12), 'kas', self.journal_cash)
        with self.assertRaises(UserError):  # bought after the contract date
            akad.with_user(self.user_pengurus).action_activate()

    def test_wad_before_contract(self):
        akad = self.create_akad(date_akad=date(2026, 1, 10))
        akad.write({'wad_date': date(2026, 1, 11)})
        with self.assertRaises(UserError):
            self.activate(akad)

    def test_direct_purchase_report_note(self):
        akad = self.create_akad()
        self.assertIn('tidak memakai wakalah', self.html('report_wakalah', akad))

    # ------------------------------------------------------------------ down payment refund
    def cancelled_with_down_payment(self, activate=False):
        akad = self.create_akad()
        akad.with_user(self.user_pengurus).action_approve()
        akad.with_user(self.user_petugas)._record_down_payment(date(2026, 1, 8), self.journal_cash)
        if activate:
            akad.with_user(self.user_petugas)._record_purchase(date(2026, 1, 9), 'kas', self.journal_cash)
            akad.with_user(self.user_pengurus).action_activate()
        akad.with_user(self.user_pengurus).action_cancel()
        self.assertEqual(akad.state, 'batal')
        self.assertEqual(akad.dp_held, 650000)
        return akad

    def test_refund_with_real_cost(self):
        akad = self.cancelled_with_down_payment()
        with self.assertRaises(UserError):
            akad.with_user(self.user_petugas)._refund_down_payment(date(2026, 1, 20), self.journal_cash)
        with self.assertRaises(UserError):  # real cost above the down payment
            akad.with_user(self.user_pengurus)._refund_down_payment(date(2026, 1, 20), self.journal_cash, 700000, 'x')
        with self.assertRaises(UserError):  # real cost without details
            akad.with_user(self.user_pengurus)._refund_down_payment(date(2026, 1, 20), self.journal_cash, 50000)
        move = akad.with_user(self.user_pengurus)._refund_down_payment(
            date(2026, 1, 20), self.journal_cash, 50000, 'Ongkos kirim pemesanan')
        by_account = {l.account_id: l.balance for l in move.line_ids}
        self.assertEqual(by_account[self.acc_down_payment], 650000)
        self.assertEqual(by_account[self.acc_cash], -600000)
        self.assertEqual(by_account[self.acc_real_cost], -50000)
        self.assertEqual((akad.dp_refund_amount, akad.dp_real_cost), (600000, 50000))
        akad.invalidate_recordset()
        self.assertEqual(akad.dp_held, 0)
        with self.assertRaises(UserError):  # only once
            akad.with_user(self.user_pengurus)._refund_down_payment(date(2026, 1, 21), self.journal_cash)

    def test_refund_full_after_active_contract_cancelled(self):
        # Cancelling an active contract reverses the offset of the down payment: it is held again
        akad = self.cancelled_with_down_payment(activate=True)
        wizard = self.env['koperasi.murabahah.dp.refund.wizard'].with_user(self.user_pengurus).with_context(
            default_akad_id=akad.id).create({'date': date(2026, 1, 20)})
        self.assertEqual(wizard.journal_id, self.company.murabahah_cash_journal_id)
        self.assertEqual(wizard.refund_amount, 650000)
        wizard.action_confirm()
        self.assertEqual(akad.dp_refund_amount, 650000)
        self.assertEqual(self.ledger(akad, self.acc_down_payment), 0)

    def test_refund_requires_cancelled(self):
        akad = self.activate(self.create_akad())
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus)._refund_down_payment(date(2026, 1, 20), self.journal_cash)

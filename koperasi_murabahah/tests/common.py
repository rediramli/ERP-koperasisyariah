from datetime import date

from odoo.tests import TransactionCase, new_test_user


class MurabahahCommon(TransactionCase):
    """Own accounts and journals, so the tests do not depend on the chart of accounts of the database."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Account = cls.env['account.account']

        def account(code, name, account_type, reconcile=False):
            return Account.create({'code': code, 'name': name, 'account_type': account_type,
                                   'reconcile': reconcile, 'company_ids': [(6, 0, cls.company.ids)]})

        cls.acc_cash = account('KT111001', 'TEST Kas', 'asset_cash')
        cls.acc_receivable = account('KT113101', 'TEST Piutang Murabahah', 'asset_receivable', True)
        cls.acc_deferred = account('KT113102', 'TEST Margin Ditangguhkan', 'asset_current')
        cls.acc_inventory = account('KT114001', 'TEST Persediaan Murabahah', 'asset_current')
        cls.acc_down_payment = account('KT218001', 'TEST Uang Muka Murabahah', 'liability_current')
        cls.acc_charity = account('KT219001', 'TEST Dana Kebajikan', 'liability_current')
        cls.acc_income = account('KT411001', 'TEST Pendapatan Margin', 'income')
        Journal = cls.env['account.journal']
        cls.journal_general = Journal.create({'name': 'TEST Murabahah', 'code': 'KTMR', 'type': 'general',
                                              'company_id': cls.company.id})
        cls.journal_cash = Journal.create({'name': 'TEST Kas', 'code': 'KTKS', 'type': 'cash',
                                           'default_account_id': cls.acc_cash.id, 'company_id': cls.company.id})
        cls.company.write({
            'murabahah_journal_id': cls.journal_general.id,
            'murabahah_cash_journal_id': cls.journal_cash.id,
            'murabahah_receivable_account_id': cls.acc_receivable.id,
            'murabahah_deferred_margin_account_id': cls.acc_deferred.id,
            'murabahah_inventory_account_id': cls.acc_inventory.id,
            'murabahah_down_payment_account_id': cls.acc_down_payment.id,
            'murabahah_charity_account_id': cls.acc_charity.id,
            'murabahah_income_account_id': cls.acc_income.id,
            'murabahah_installment_rounding': 1.0,
            # Older tests create akads directly; the application flow is tested in test_pengajuan
            'murabahah_require_application': False,
            'murabahah_non_member_policy': 'boleh',
        })
        cls.member = cls.env['res.partner'].create({
            'name': 'TEST Anggota', 'koperasi_status': 'anggota', 'koperasi_member_no': 'KTAGG01'})
        cls.non_member = cls.env['res.partner'].create({'name': 'TEST Nasabah'})
        cls.supplier = cls.env['res.partner'].create({'name': 'TEST Pemasok'})
        cls.user_petugas = new_test_user(cls.env, login='kt_petugas', groups='koperasi_base.group_koperasi_petugas')
        cls.user_pengurus = new_test_user(cls.env, login='kt_pengurus', groups='koperasi_base.group_koperasi_pengurus')
        cls.user_akuntan = new_test_user(cls.env, login='kt_akuntan', groups='koperasi_base.group_koperasi_akuntan')

    def create_akad(self, cost=9650000, dp=650000, pct=20.0, tenor=12, partner=None, date_akad=date(2026, 1, 10)):
        return self.env['koperasi.murabahah.akad'].with_user(self.user_petugas).create({
            'partner_id': (partner or self.member).id,
            'product_desc': 'Motor',
            'supplier_id': self.supplier.id,
            'cost_price': cost,
            'down_payment': dp,
            'margin_pct': pct,
            'tenor': tenor,
            'date_akad': date_akad,
            'monthly_income': 10000000,
            'officer_recommendation': 'layak',
        })

    def activate(self, akad, purchase_mode='kas'):
        akad.with_user(self.user_pengurus).action_approve()
        if akad.down_payment:
            akad.with_user(self.user_petugas)._record_down_payment(akad.date_akad, self.journal_cash)
        akad.with_user(self.user_petugas)._record_purchase(akad.date_akad, purchase_mode, self.journal_cash)
        akad.with_user(self.user_pengurus).action_activate()
        return akad

    def pay(self, akad, amount, pay_date=date(2026, 2, 10), tazir=0.0, user=None):
        return akad.with_user(user or self.user_petugas)._register_payment(
            pay_date, self.journal_cash, amount=amount, tazir=tazir, tazir_confirmed=bool(tazir))

    def ledger(self, akad, account):
        lines = self.env['account.move.line'].search([
            ('murabahah_akad_id', '=', akad.id), ('parent_state', '=', 'posted'), ('account_id', '=', account.id)])
        return sum(lines.mapped('balance'))

    def assert_invariants(self, akad):
        """CLAUDE.md section 6."""
        akad.invalidate_recordset()
        lines = akad.line_ids
        # Schedule: principal + margin = sale price - down payment, to the rupiah
        self.assertEqual(sum(lines.mapped('amount_principal')) + sum(lines.mapped('amount_margin')),
                         akad.sale_price - akad.down_payment)
        self.assertEqual(sum(lines.mapped('amount_margin')), akad.margin_amount)
        paid = sum(lines.mapped('paid_total'))
        recognized = sum(lines.mapped('paid_margin'))
        discount = sum(lines.mapped('discount_margin'))
        # Receivable per contract = sale price - down payment - installments received - discount
        expected_receivable = akad.sale_price - akad.down_payment - paid - discount
        expected_margin = akad.margin_amount - recognized - discount
        self.assertEqual(akad.remaining_receivable, expected_receivable)
        self.assertEqual(akad.remaining_margin, expected_margin)
        # ... and the ledger agrees
        self.assertEqual(self.ledger(akad, self.company.murabahah_receivable_account_id), expected_receivable)
        self.assertEqual(-self.ledger(akad, self.company.murabahah_deferred_margin_account_id), expected_margin)
        self.assertFalse(akad.ledger_mismatch)
        if akad.state == 'lunas':
            self.assertEqual(akad.remaining_receivable, 0)
            self.assertEqual(akad.remaining_margin, 0)
        for move in akad.move_ids.filtered(lambda m: m.state == 'posted'):
            self.assertEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))
            self.assertIn(akad.name, move.ref)

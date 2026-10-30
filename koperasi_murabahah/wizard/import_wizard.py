import csv
import io
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, Command
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

from ..models.akad import GROUP_PENGURUS, round_rp, split_schedule

REQUIRED_COLUMNS = [
    'no_akad', 'anggota', 'barang', 'tanggal_akad', 'harga_perolehan', 'uang_muka', 'margin_pct', 'margin',
    'harga_jual', 'tenor', 'angsuran_per_bulan', 'angsuran_dibayar', 'sisa_piutang', 'sisa_margin_ditangguhkan',
]


class KoperasiMurabahahImportWizard(models.TransientModel):
    """Import running contracts whose balances are already in an opening-balance entry.

    Nothing is posted: the contract, its schedule and a 'saldo awal' payment (allocation only)
    are created, and the existing opening-balance lines are tagged with the contract so the
    ledger check per contract works. This avoids posting the receivable twice.
    """
    _name = 'koperasi.murabahah.import.wizard'
    _description = 'Import Akad Murabahah Berjalan'

    file = fields.Binary(string='File CSV', required=True)
    filename = fields.Char()
    opening_move_id = fields.Many2one(
        'account.move', string='Jurnal Saldo Awal', required=True,
        domain="[('state', '=', 'posted'), ('move_type', '=', 'entry')]",
        help="Jurnal yang sudah berisi sisa piutang dan margin ditangguhkan tiap akad "
             "(baris berlabel '<no_akad> ...').")
    result = fields.Text(string='Hasil', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'opening_move_id' in fields_list:
            move = self.env['account.move'].search(
                [('state', '=', 'posted'), ('move_type', '=', 'entry'), ('ref', 'ilike', 'SALDO AWAL')],
                order='date, id', limit=1)
            res['opening_move_id'] = move.id
        return res

    @staticmethod
    def _parse_amount(value):
        value = (value or '').strip().replace('Rp', '').replace(' ', '')
        if not value:
            return 0.0
        return float(value.replace('.', '').replace(',', '.')) if value.count('.') > 1 or ',' in value else float(value)

    @staticmethod
    def _parse_date(value):
        value = (value or '').strip()
        for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        raise UserError("Format tanggal tidak dikenali: %r (pakai DD/MM/YYYY)" % value)

    def _read_rows(self):
        # Odoo 20: binary fields hold a BinaryValue with the raw (not base64) content
        content = self.file.content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise UserError(self.env._("Kolom CSV tidak lengkap: %s", ", ".join(missing)))
        return [row for row in reader if (row.get('no_akad') or '').strip()]

    def _find_partner(self, name):
        partners = self.env['res.partner'].search([('name', '=ilike', name.strip())])
        if len(partners) != 1:
            partners = self.env['res.partner'].search([('ref', '=', name.strip())])
        if len(partners) != 1:
            raise UserError(self.env._("Kontak %r tidak ditemukan atau lebih dari satu.", name))
        return partners

    def _opening_line(self, company, account, number, partner):
        lines = self.opening_move_id.line_ids.filtered(
            lambda l: l.account_id == account and l.partner_id == partner
            and (l.name or '').startswith(number + ' ') and not l.murabahah_akad_id)
        if len(lines) > 1:
            raise UserError(self.env._("Baris saldo awal %(no)s di akun %(acc)s lebih dari satu.",
                                       no=number, acc=account.code))
        return lines

    def action_import(self):
        self.ensure_one()
        akad_model = self.env['koperasi.murabahah.akad']
        akad_model._check_group(GROUP_PENGURUS)
        company = self.env.company
        receivable = company.murabahah_receivable_account_id
        deferred = company.murabahah_deferred_margin_account_id
        if not receivable or not deferred:
            raise UserError(self.env._("Isi akun Piutang Murabahah dan Margin Ditangguhkan di Pengaturan."))
        messages = []
        for row in self._read_rows():
            number = row['no_akad'].strip()
            if akad_model.search_count([('name', '=', number), ('company_id', '=', company.id)]):
                messages.append("%s: dilewati, sudah ada." % number)
                continue
            messages.append(self._import_row(row, company, receivable, deferred))
        self.result = "\n".join(messages)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _import_row(self, row, company, receivable, deferred):
        number = row['no_akad'].strip()
        partner = self._find_partner(row['anggota'])
        cost = self._parse_amount(row['harga_perolehan'])
        dp = self._parse_amount(row['uang_muka'])
        margin = self._parse_amount(row['margin'])
        sale = self._parse_amount(row['harga_jual'])
        tenor = int(self._parse_amount(row['tenor']))
        installment = self._parse_amount(row['angsuran_per_bulan'])
        paid_count = int(self._parse_amount(row['angsuran_dibayar']))
        rest = self._parse_amount(row['sisa_piutang'])
        rest_margin = self._parse_amount(row['sisa_margin_ditangguhkan'])
        pct = self._parse_amount(row['margin_pct'].replace('%', ''))
        date_akad = self._parse_date(row['tanggal_akad'])
        first_due = self._parse_date(row['tanggal_angsuran_pertama']) if (row.get('tanggal_angsuran_pertama') or '').strip() \
            else date_akad + relativedelta(months=1)

        financed = sale - dp
        paid = round_rp(financed - rest)
        paid_margin = round_rp(margin - rest_margin)
        # Consistency checks: the CSV must describe the same contract the opening entry holds
        if float_compare(sale, cost + margin, precision_digits=2):
            raise UserError(self.env._("%s: harga jual bukan harga perolehan + margin.", number))
        if not float_is_zero(margin - round_rp(pct / 100.0 * (cost - dp)), precision_digits=2):
            raise UserError(self.env._("%s: margin tidak sama dengan %% x (harga perolehan - uang muka).", number))
        if (row.get('sisa_pokok') or '').strip() and float_compare(
                rest - rest_margin, self._parse_amount(row['sisa_pokok']), precision_digits=2):
            raise UserError(self.env._("%s: sisa piutang - sisa margin tidak sama dengan sisa pokok.", number))
        if paid < 0 or paid_margin < 0 or rest <= 0 or rest_margin < 0 or rest_margin > rest:
            raise UserError(self.env._("%s: sisa piutang/margin tidak masuk akal.", number))
        if paid_count >= tenor or (paid_count == 0) != float_is_zero(paid, precision_digits=2):
            raise UserError(self.env._("%s: jumlah angsuran dibayar tidak cocok dengan sisa piutang.", number))

        rec_line = self._opening_line(company, receivable, number, partner)
        def_line = self._opening_line(company, deferred, number, partner)
        if not rec_line or float_compare(rec_line.balance, rest, precision_digits=2):
            raise UserError(self.env._(
                "%(no)s: baris piutang di %(move)s tidak ada atau nilainya bukan %(rest)s.",
                no=number, move=self.opening_move_id.name, rest=rest))
        if rest_margin and (not def_line or float_compare(-def_line.balance, rest_margin, precision_digits=2)):
            raise UserError(self.env._(
                "%(no)s: baris margin ditangguhkan di %(move)s tidak ada atau nilainya bukan %(rest)s.",
                no=number, move=self.opening_move_id.name, rest=rest_margin))

        # Schedule: the paid part and the remaining part are each split with the normal rule,
        # so the remaining schedule matches the balances in the opening entry exactly.
        paid_parts = split_schedule(paid, paid_margin, paid_count, installment) if paid_count else []
        remaining_count = tenor - paid_count
        try:
            rest_parts = split_schedule(rest, rest_margin, remaining_count, installment)
        except UserError:
            rest_parts = split_schedule(rest, rest_margin, remaining_count, round_rp(rest / remaining_count))
        parts = paid_parts + rest_parts
        akad = self.env['koperasi.murabahah.akad'].create({
            'name': number,
            'company_id': company.id,
            'partner_id': partner.id,
            'product_desc': row['barang'].strip(),
            'date_request': date_akad,
            'date_akad': date_akad,
            'cost_price': cost,
            'down_payment': dp,
            'margin_pct': pct,
            'margin_amount': margin,
            'tenor': tenor,
            'installment_amount': installment,
            'first_due_date': first_due,
            'state': 'aktif',
            'is_migrated': True,
            'opening_move_id': self.opening_move_id.id,
            'line_ids': [Command.create({
                'sequence': i + 1,
                'date_due': first_due + relativedelta(months=i),
                'amount_principal': principal,
                'amount_margin': line_margin,
            }) for i, (principal, line_margin) in enumerate(parts)],
        })
        if paid_count:
            lines = akad.line_ids.sorted('sequence')[:paid_count]
            self.env['koperasi.murabahah.payment'].create({
                'akad_id': akad.id,
                'date': self.opening_move_id.date,
                'payment_type': 'saldo_awal',
                'amount': paid,
                'memo': self.env._("Angsuran sebelum migrasi (sudah tercermin di %s)", self.opening_move_id.name),
                'line_ids': [Command.create({
                    'angsuran_id': line.id,
                    'amount_principal': line.amount_principal,
                    'amount_margin': line.amount_margin,
                }) for line in lines],
            })
        (rec_line | def_line).sudo().write({'murabahah_akad_id': akad.id})
        akad.message_post(body=self.env._(
            "Diimpor dari %(file)s. Saldo awal sudah ada di %(move)s, tidak dijurnal ulang.",
            file=self.filename or 'CSV', move=self.opening_move_id.name))
        return "%s: OK, %s angsuran (%s sudah dibayar), sisa piutang %s, sisa margin %s." % (
            number, tenor, paid_count, rest, rest_margin)

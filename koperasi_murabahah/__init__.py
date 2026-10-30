from . import models
from . import wizard

# Default accounts/journals by code. Only used once at install as a convenience;
# everything stays configurable in Koperasi > Konfigurasi > Pengaturan.
DEFAULT_ACCOUNT_CODES = {
    'murabahah_receivable_account_id': '11310010',
    'murabahah_deferred_margin_account_id': '11310020',
    'murabahah_inventory_account_id': '11400010',
    'murabahah_down_payment_account_id': '21800010',
    'murabahah_charity_account_id': '21900010',
    'murabahah_income_account_id': '41100010',
}


def _post_init_hook(env):
    for company in env['res.company'].search([]):
        vals = {}
        for field_name, code in DEFAULT_ACCOUNT_CODES.items():
            if company[field_name]:
                continue
            account = env['account.account'].with_company(company).search(
                [('code', '=', code), ('company_ids', 'in', company.id)], limit=1)
            if account:
                vals[field_name] = account.id
        journals = env['account.journal'].search([('company_id', '=', company.id)])
        if not company.murabahah_journal_id:
            general = journals.filtered(lambda j: j.type == 'general' and j.code == 'MISC')[:1] \
                or journals.filtered(lambda j: j.type == 'general')[:1]
            if general:
                vals['murabahah_journal_id'] = general.id
        if not company.murabahah_cash_journal_id:
            cash = journals.filtered(lambda j: j.type == 'cash')[:1] or journals.filtered(lambda j: j.type == 'bank')[:1]
            if cash:
                vals['murabahah_cash_journal_id'] = cash.id
        if vals:
            company.write(vals)

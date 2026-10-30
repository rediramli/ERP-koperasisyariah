from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    murabahah_akad_id = fields.Many2one(
        'koperasi.murabahah.akad', string='Akad Murabahah', index='btree_not_null', copy=False, readonly=True)
    murabahah_payment_id = fields.Many2one(
        'koperasi.murabahah.payment', string='Pembayaran Murabahah', index='btree_not_null', copy=False, readonly=True)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Set on every line the module posts, and on the opening-balance lines of imported contracts,
    # so the ledger balance of each contract can be checked against its schedule.
    # copy=True keeps the tag on reversal entries.
    murabahah_akad_id = fields.Many2one(
        'koperasi.murabahah.akad', string='Akad Murabahah', index='btree_not_null', copy=True)

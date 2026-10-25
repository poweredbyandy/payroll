# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class PayrollEmployeeLoanType(models.Model):
    _name = "payroll.employee.loan.type"
    _description = "Employee Loan Type"

    name = fields.Char(required=True, translate=True)
    loan_term = fields.Integer(string="Default Term", default=12)
    interest_rate = fields.Float(string="Interest Rate (%)", default=0.0)
    interest_type = fields.Selection(
        [("linear", "Linear"), ("reduce", "Reducing")],
        default="linear",
        required=True,
    )
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        check_company=True,
        help="Default bank or cash journal when disbursing loans of this type.",
    )
    disbursement_account_id = fields.Many2one(
        "account.account",
        string="Loan Receivable Account",
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help="Debit account for the loan disbursement (employee loan receivable).",
    )

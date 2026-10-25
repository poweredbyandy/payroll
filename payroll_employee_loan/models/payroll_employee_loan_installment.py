# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class PayrollEmployeeLoanInstallment(models.Model):
    _name = "payroll.employee.loan.installment"
    _description = "Employee Loan Installment"
    _order = "date_due, id"

    loan_id = fields.Many2one(
        "payroll.employee.loan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True)
    date_due = fields.Date(required=True)
    principal_amount = fields.Monetary(currency_field="currency_id")
    interest_amount = fields.Monetary(currency_field="currency_id")
    amount = fields.Monetary(
        string="Total",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
    )
    currency_id = fields.Many2one(related="loan_id.currency_id", store=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("skipped", "Skipped"),
        ],
        default="pending",
        required=True,
    )
    payslip_id = fields.Many2one("hr.payslip", string="Payslip", copy=False)
    auto_add_to_payslip = fields.Boolean(default=True)
    company_id = fields.Many2one(related="loan_id.company_id", store=True)

    @api.depends("principal_amount", "interest_amount")
    def _compute_amount(self):
        for line in self:
            line.amount = line.principal_amount + line.interest_amount

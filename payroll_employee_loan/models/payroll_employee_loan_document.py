# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class PayrollEmployeeLoanDocument(models.Model):
    _name = "payroll.employee.loan.document"
    _description = "Employee Loan Document"

    name = fields.Char(required=True)
    loan_id = fields.Many2one(
        "payroll.employee.loan", required=True, ondelete="cascade"
    )
    attachment = fields.Binary(attachment=True)
    filename = fields.Char()

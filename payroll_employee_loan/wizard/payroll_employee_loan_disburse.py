# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PayrollEmployeeLoanDisburse(models.TransientModel):
    _name = "payroll.employee.loan.disburse"
    _description = "Disburse Employee Loan"

    loan_id = fields.Many2one(
        "payroll.employee.loan",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="loan_id.company_id")
    currency_id = fields.Many2one(related="loan_id.currency_id")
    company_currency_id = fields.Many2one(related="company_id.currency_id")
    amount = fields.Monetary(related="loan_id.amount")
    amount_company = fields.Monetary(
        string="Amount in Company Currency",
        compute="_compute_amount_company",
        currency_field="company_currency_id",
    )
    display_amount_company = fields.Boolean(
        compute="_compute_amount_company",
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Journal",
        required=True,
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    available_payment_method_line_ids = fields.Many2many(
        "account.payment.method.line",
        compute="_compute_available_payment_method_line_ids",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        required=True,
        domain="[('id', 'in', available_payment_method_line_ids)]",
    )
    payment_date = fields.Date(
        string="Disbursement Date",
        required=True,
        default=fields.Date.context_today,
    )

    @api.depends(
        "loan_id.amount",
        "loan_id.currency_id",
        "company_id.currency_id",
        "payment_date",
    )
    def _compute_amount_company(self):
        for wizard in self:
            loan = wizard.loan_id
            company_currency = wizard.company_currency_id
            if not loan or not company_currency:
                wizard.amount_company = 0.0
                wizard.display_amount_company = False
                continue
            wizard.display_amount_company = loan.currency_id != company_currency
            if not wizard.display_amount_company:
                wizard.amount_company = loan.amount
                continue
            wizard.amount_company = loan.currency_id._convert(
                loan.amount,
                company_currency,
                wizard.company_id,
                wizard.payment_date or fields.Date.context_today(wizard),
            )

    @api.depends("journal_id")
    def _compute_available_payment_method_line_ids(self):
        for wizard in self:
            wizard.available_payment_method_line_ids = (
                wizard.journal_id.outbound_payment_method_line_ids
            )

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        methods = self.journal_id.outbound_payment_method_line_ids
        if self.payment_method_line_id not in methods:
            self.payment_method_line_id = methods[:1]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        loan = self.env["payroll.employee.loan"].browse(
            self.env.context.get("active_id")
        )
        if not loan:
            return res
        if loan.state != "hr_approved":
            raise UserError(
                _("Only HR-approved loans can be disbursed.")
            )
        res["loan_id"] = loan.id
        res["journal_id"] = (
            loan.journal_id.id
            or loan.loan_type_id.journal_id.id
            or False
        )
        res["payment_date"] = loan.date or fields.Date.context_today(self)
        journal = self.env["account.journal"].browse(res.get("journal_id"))
        method = loan.payment_method_line_id
        if not method or (journal and method.journal_id != journal):
            method = journal.outbound_payment_method_line_ids[:1]
        res["payment_method_line_id"] = method.id if method else False
        return res

    def action_confirm_disburse(self):
        self.ensure_one()
        loan = self.loan_id
        if loan.state != "hr_approved":
            raise UserError(
                _("Only HR-approved loans can be disbursed.")
            )
        if loan.move_id:
            raise UserError(
                _("Loan %s already has a disbursement entry.") % loan.name
            )
        receivable = loan._get_disbursement_account()
        vals = {
            "journal_id": self.journal_id.id,
            "payment_method_line_id": self.payment_method_line_id.id,
            "date": self.payment_date,
        }
        if receivable and not loan.disbursement_account_id:
            vals["disbursement_account_id"] = receivable.id
        loan.write(vals)
        loan._create_disbursement_move()
        loan.write({"state": "disbursed"})
        return {
            "type": "ir.actions.act_window",
            "res_model": "payroll.employee.loan",
            "res_id": loan.id,
            "view_mode": "form",
            "target": "current",
        }

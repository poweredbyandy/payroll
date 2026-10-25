# Part of Odoo. See LICENSE file for full copyright and licensing details.

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class PayrollEmployeeLoan(models.Model):
    _name = "payroll.employee.loan"
    _description = "Employee Loan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc, id desc"

    name = fields.Char(
        required=True,
        copy=False,
        default="/",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("requested", "Requested"),
            ("dept_approved", "Department Approved"),
            ("hr_approved", "HR Approved"),
            ("disbursed", "Disbursed"),
            ("done", "Done"),
            ("closed", "Closed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    employee_id = fields.Many2one("hr.employee", required=True, tracking=True)
    department_id = fields.Many2one(
        "hr.department", related="employee_id.department_id", store=True
    )
    manager_id = fields.Many2one("hr.employee", string="Department Manager")
    job_id = fields.Many2one(related="employee_id.job_id", store=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    date = fields.Date(default=fields.Date.context_today, required=True)
    date_start = fields.Date(
        string="Start Date",
        default=fields.Date.context_today,
        required=True,
    )
    date_end = fields.Date(compute="_compute_date_end", store=True)
    term = fields.Integer(string="Number of Installments", required=True, default=12)
    loan_type_id = fields.Many2one("payroll.employee.loan.type", required=True)
    payment_method = fields.Selection(
        [("payslip", "Payslip")],
        string="Installment Deduction",
        default="payslip",
        required=True,
        help="How installments are recovered (currently only via payslip).",
    )
    amount = fields.Monetary(required=True, currency_field="currency_id")
    paid_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id"
    )
    remaining_amount = fields.Monetary(
        compute="_compute_amounts", store=True, currency_field="currency_id"
    )
    installment_amount = fields.Monetary(
        compute="_compute_installment_amount",
        store=True,
        currency_field="currency_id",
    )
    apply_interest = fields.Boolean(default=False)
    interest_type = fields.Selection(
        [("linear", "Linear"), ("reduce", "Reducing")],
        default="linear",
    )
    interest_rate = fields.Float(string="Interest Rate (%)", default=0.0)
    interest_amount = fields.Monetary(
        compute="_compute_interest_amount",
        store=True,
        currency_field="currency_id",
    )
    installment_ids = fields.One2many(
        "payroll.employee.loan.installment", "loan_id", string="Installments"
    )
    document_ids = fields.One2many(
        "payroll.employee.loan.document", "loan_id", string="Documents"
    )
    notes = fields.Text(string="Reason")
    move_id = fields.Many2one(
        "account.move",
        string="Disbursement Entry",
        copy=False,
        readonly=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Disbursement Journal",
        check_company=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help="Bank or cash journal used to pay out the loan.",
    )
    available_payment_method_line_ids = fields.Many2many(
        "account.payment.method.line",
        compute="_compute_available_payment_method_line_ids",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('id', 'in', available_payment_method_line_ids)]",
        help="Outbound payment method of the selected journal (e.g. Manual, Check).",
    )
    disbursement_account_id = fields.Many2one(
        "account.account",
        string="Loan Receivable Account",
        check_company=True,
        domain="[('deprecated', '=', False)]",
    )
    installment_count = fields.Integer(compute="_compute_installment_count")

    @api.depends("date_start", "term")
    def _compute_date_end(self):
        for loan in self:
            if loan.date_start and loan.term:
                loan.date_end = loan.date_start + relativedelta(months=loan.term)
            else:
                loan.date_end = False

    @api.depends("installment_ids.state", "installment_ids.amount")
    def _compute_amounts(self):
        for loan in self:
            paid = sum(
                loan.installment_ids.filtered(lambda i: i.state == "paid").mapped(
                    "amount"
                )
            )
            loan.paid_amount = paid
            loan.remaining_amount = loan.amount + loan.interest_amount - paid

    @api.depends("amount", "term")
    def _compute_installment_amount(self):
        for loan in self:
            loan.installment_amount = (
                loan.amount / loan.term if loan.term else 0.0
            )

    @api.depends("amount", "interest_rate", "apply_interest", "term")
    def _compute_interest_amount(self):
        for loan in self:
            if not loan.apply_interest or not loan.interest_rate:
                loan.interest_amount = 0.0
            else:
                loan.interest_amount = loan.amount * (loan.interest_rate / 100.0)

    @api.depends("installment_ids")
    def _compute_installment_count(self):
        for loan in self:
            loan.installment_count = len(loan.installment_ids)

    @api.depends("journal_id")
    def _compute_available_payment_method_line_ids(self):
        for loan in self:
            loan.available_payment_method_line_ids = (
                loan.journal_id.outbound_payment_method_line_ids
            )

    @api.onchange("loan_type_id")
    def _onchange_loan_type_id(self):
        if self.loan_type_id:
            self.term = self.loan_type_id.loan_term
            self.interest_rate = self.loan_type_id.interest_rate
            self.interest_type = self.loan_type_id.interest_type
            self.apply_interest = bool(self.loan_type_id.interest_rate)
            self.journal_id = self.loan_type_id.journal_id
            self.disbursement_account_id = self.loan_type_id.disbursement_account_id
            self._l10n_loan_set_default_payment_method_line()

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        self._l10n_loan_set_default_payment_method_line()

    def _l10n_loan_set_default_payment_method_line(self):
        for loan in self:
            methods = loan.journal_id.outbound_payment_method_line_ids
            if loan.payment_method_line_id not in methods:
                loan.payment_method_line_id = methods[:1]

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            self.manager_id = self.employee_id.parent_id
            contract = self.employee_id.contract_id
            if contract and contract.currency_id:
                self.currency_id = contract.currency_id

    @api.model_create_multi
    def create(self, vals_list):
        LoanType = self.env["payroll.employee.loan.type"]
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("payroll.employee.loan")
                    or "/"
                )
            loan_type = LoanType.browse(vals.get("loan_type_id"))
            if loan_type:
                vals.setdefault("journal_id", loan_type.journal_id.id or False)
                vals.setdefault(
                    "disbursement_account_id",
                    loan_type.disbursement_account_id.id or False,
                )
            journal = self.env["account.journal"].browse(vals.get("journal_id"))
            if journal and not vals.get("payment_method_line_id"):
                method = journal.outbound_payment_method_line_ids[:1]
                if method:
                    vals["payment_method_line_id"] = method.id
        return super().create(vals_list)

    def action_request(self):
        self.write({"state": "requested"})

    def action_dept_approve(self):
        self.write({"state": "dept_approved"})

    def action_hr_approve(self):
        for loan in self:
            loan._generate_installments()
        self.write({"state": "hr_approved"})

    def action_disburse(self):
        self.ensure_one()
        if self.state != "hr_approved":
            raise UserError(
                _("Loan %s must be HR approved before disbursement.") % self.name
            )
        if self.move_id:
            raise UserError(
                _("Loan %s already has a disbursement entry.") % self.name
            )
        return {
            "name": _("Disburse Loan"),
            "type": "ir.actions.act_window",
            "res_model": "payroll.employee.loan.disburse",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "payroll.employee.loan",
                "active_id": self.id,
                "default_loan_id": self.id,
            },
        }

    def action_done(self):
        self.write({"state": "done"})

    def action_close(self):
        for loan in self:
            if loan.remaining_amount > 0:
                raise UserError(
                    _("Cannot close loan %s while remaining amount is positive.")
                    % loan.name
                )
        self.write({"state": "closed"})

    def action_reject(self):
        self.write({"state": "rejected"})

    def action_cancel(self):
        for loan in self:
            loan._cancel_disbursement_move()
        self.write({"state": "cancelled"})

    def action_reset_draft(self):
        for loan in self:
            loan._cancel_disbursement_move()
        self.installment_ids.unlink()
        self.write({"state": "draft", "move_id": False})

    def action_open_disbursement_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("This loan has no disbursement entry yet."))
        return {
            "name": _("Disbursement Entry"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _get_disbursement_journal(self):
        self.ensure_one()
        return self.journal_id or self.loan_type_id.journal_id

    def _get_disbursement_payment_method_line(self):
        self.ensure_one()
        return self.payment_method_line_id

    def _get_disbursement_account(self):
        self.ensure_one()
        return (
            self.disbursement_account_id or self.loan_type_id.disbursement_account_id
        )

    def _get_disbursement_liquidity_account(self):
        self.ensure_one()
        method = self._get_disbursement_payment_method_line()
        if method and method.payment_account_id:
            return method.payment_account_id
        journal = self._get_disbursement_journal()
        return journal.default_account_id if journal else False

    def _get_disbursement_partner(self):
        self.ensure_one()
        return self.employee_id.work_contact_id

    def _get_disbursement_amount_company(self):
        self.ensure_one()
        company_currency = self.company_id.currency_id
        if self.currency_id == company_currency:
            return self.currency_id.round(self.amount)
        return self.currency_id._convert(
            self.amount,
            company_currency,
            self.company_id,
            self.date or fields.Date.context_today(self),
        )

    def _create_disbursement_move(self):
        self.ensure_one()
        journal = self._get_disbursement_journal()
        method = self._get_disbursement_payment_method_line()
        receivable = self._get_disbursement_account()
        liquidity = self._get_disbursement_liquidity_account()
        if not journal:
            raise UserError(
                _("Select a disbursement journal on loan %s.") % self.name
            )
        if not method:
            raise UserError(
                _("Select a payment method on loan %s.") % self.name
            )
        if journal and method.journal_id and method.journal_id != journal:
            raise UserError(
                _(
                    "Payment method %(method)s does not belong to journal %(journal)s."
                )
                % {
                    "method": method.display_name,
                    "journal": journal.display_name,
                }
            )
        if not receivable:
            raise UserError(
                _(
                    "Configure a loan receivable account for loan %s "
                    "(company settings, loan, or loan type)."
                )
                % self.name
            )
        if not liquidity:
            raise UserError(
                _(
                    'No liquidity account found for journal "%(journal)s" '
                    '/ payment method "%(method)s".'
                )
                % {
                    "journal": journal.display_name,
                    "method": method.display_name,
                }
            )
        amount = self._get_disbursement_amount_company()
        if self.company_id.currency_id.is_zero(amount):
            raise UserError(_("Cannot disburse a loan with zero amount."))
        partner = self._get_disbursement_partner()
        label = _("Loan disbursement %s (%s)") % (self.name, method.display_name)
        move_vals = {
            "move_type": "entry",
            "date": self.date or fields.Date.context_today(self),
            "journal_id": journal.id,
            "ref": self.name,
            "narration": self.notes or label,
            "company_id": self.company_id.id,
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "name": label,
                        "account_id": receivable.id,
                        "partner_id": partner.id if partner else False,
                        "debit": amount,
                        "credit": 0.0,
                    },
                ),
                (
                    0,
                    0,
                    {
                        "name": label,
                        "account_id": liquidity.id,
                        "partner_id": partner.id if partner else False,
                        "debit": 0.0,
                        "credit": amount,
                    },
                ),
            ],
        }
        if self.currency_id != self.company_id.currency_id:
            move_vals["line_ids"][0][2].update(
                {
                    "currency_id": self.currency_id.id,
                    "amount_currency": self.amount,
                }
            )
            move_vals["line_ids"][1][2].update(
                {
                    "currency_id": self.currency_id.id,
                    "amount_currency": -self.amount,
                }
            )
        move = self.env["account.move"].create(move_vals)
        move.action_post()
        self.move_id = move.id
        return move

    def _cancel_disbursement_move(self):
        self.ensure_one()
        move = self.move_id
        if not move:
            return
        if move.state == "posted":
            move.button_draft()
        if move.state != "cancel":
            move.button_cancel()
        self.move_id = False

    def _generate_installments(self):
        Installment = self.env["payroll.employee.loan.installment"]
        for loan in self:
            loan.installment_ids.unlink()
            if loan.term <= 0:
                raise ValidationError(_("Loan term must be positive."))
            principal_each = loan.amount / loan.term
            interest_each = (
                loan.interest_amount / loan.term if loan.apply_interest else 0.0
            )
            remaining_principal = loan.amount
            lines = []
            for index in range(loan.term):
                if loan.interest_type == "reduce" and loan.apply_interest:
                    interest = remaining_principal * (loan.interest_rate / 100.0) / 12.0
                    principal = principal_each
                    remaining_principal -= principal
                else:
                    interest = interest_each
                    principal = principal_each
                date_due = loan.date_start + relativedelta(months=index)
                lines.append(
                    {
                        "loan_id": loan.id,
                        "name": _("Installment %s") % (index + 1),
                        "date_due": date_due,
                        "principal_amount": principal,
                        "interest_amount": interest,
                        "auto_add_to_payslip": True,
                    }
                )
            Installment.create(lines)

    def get_pending_installments(self, date_to):
        self.ensure_one()
        return self.installment_ids.filtered(
            lambda i: i.state == "pending"
            and i.auto_add_to_payslip
            and i.date_due <= date_to
        )

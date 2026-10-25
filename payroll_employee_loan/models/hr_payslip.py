# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    loan_installment_ids = fields.One2many(
        "payroll.employee.loan.installment",
        "payslip_id",
        string="Loan Installments",
    )

    def _get_employee_pending_loan_installments(self):
        self.ensure_one()
        if not self.employee_id or not self.date_to:
            return self.env["payroll.employee.loan.installment"]
        Loan = self.env["payroll.employee.loan"]
        loans = Loan.search(
            [
                ("employee_id", "=", self.employee_id.id),
                ("state", "in", ("disbursed", "done")),
                ("payment_method", "=", "payslip"),
                ("company_id", "=", self.company_id.id),
            ]
        )
        installments = self.env["payroll.employee.loan.installment"]
        for loan in loans:
            installments |= loan.get_pending_installments(self.date_to)
        return installments

    def _prepare_loan_input_lines(self):
        """Ensure LOAN input reflects pending installments before compute."""
        for payslip in self:
            pending = payslip._get_employee_pending_loan_installments()
            payslip.loan_installment_ids.filtered(
                lambda installment: installment.state == "pending"
            ).write({"payslip_id": False})
            loan_inputs = payslip.input_line_ids.filtered(
                lambda line: line.code == "LOAN"
            )
            if not pending:
                loan_inputs.unlink()
                continue
            pending.write({"payslip_id": payslip.id})
            amount = sum(pending.mapped("amount"))
            if loan_inputs:
                loan_inputs[0].amount = amount
            elif payslip.contract_id:
                payslip.write(
                    {
                        "input_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "name": "Loan Installment",
                                    "code": "LOAN",
                                    "amount": amount,
                                    "contract_id": payslip.contract_id.id,
                                },
                            )
                        ]
                    }
                )

    def compute_sheet(self):
        self._prepare_loan_input_lines()
        return super().compute_sheet()

    def action_payslip_done(self):
        res = super().action_payslip_done()
        for payslip in self:
            payslip.loan_installment_ids.filtered(
                lambda installment: installment.state == "pending"
            ).write({"state": "paid"})
        return res

    def action_payslip_cancel(self):
        for payslip in self:
            payslip.loan_installment_ids.filtered(
                lambda installment: installment.state == "paid"
            ).write({"state": "pending", "payslip_id": False})
        return super().action_payslip_cancel()

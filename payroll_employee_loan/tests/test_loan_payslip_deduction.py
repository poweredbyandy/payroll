# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.fields import Date
from odoo.tests import tagged

from odoo.addons.payroll.tests.common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestLoanPayslipDeduction(TestPayslipBase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param(
            "payroll.allow_cancel_payslips", True
        )
        company = self.env.company
        account_receivable = self.env["account.account"].create(
            {
                "name": "Payslip Loan Receivable",
                "code": "1310PSL",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [(6, 0, [company.id])],
            }
        )
        account_bank = self.env["account.account"].create(
            {
                "name": "Payslip Loan Bank",
                "code": "1110PSL",
                "account_type": "asset_cash",
                "company_ids": [(6, 0, [company.id])],
            }
        )
        journal = self.env["account.journal"].create(
            {
                "name": "Payslip Loan Bank",
                "code": "PLNB",
                "type": "bank",
                "company_id": company.id,
                "default_account_id": account_bank.id,
            }
        )
        self.loan_type = self.env["payroll.employee.loan.type"].create(
            {
                "name": "Payslip loan",
                "loan_term": 2,
                "interest_rate": 0.0,
                "interest_type": "linear",
                "journal_id": journal.id,
                "disbursement_account_id": account_receivable.id,
            }
        )

        # Deduction rule reading LOAN input
        self.rule_loan = self.SalaryRule.create(
            {
                "name": "Loan Deduction",
                "code": "LOANDED",
                "sequence": 180,
                "category_id": self.categ_ded.id,
                "condition_select": "none",
                "amount_select": "code",
                "amount_python_compute": (
                    "result = -(inputs.LOAN.amount if inputs.LOAN else 0.0)"
                ),
            }
        )
        self.developer_pay_structure.write({"rule_ids": [(4, self.rule_loan.id)]})
        self.RuleInput.create(
            {
                "name": "Loan",
                "code": "LOAN",
                "input_id": self.rule_loan.id,
            }
        )

    def test_payslip_deducts_and_marks_paid(self):
        loan = self.env["payroll.employee.loan"].create(
            {
                "employee_id": self.richard_emp.id,
                "loan_type_id": self.loan_type.id,
                "amount": 200.0,
                "term": 2,
                "date_start": Date.today().replace(day=1),
                "notes": "Test loan",
                "currency_id": self.richard_contract.currency_id.id,
            }
        )
        loan.action_request()
        loan.action_dept_approve()
        loan.action_hr_approve()
        method = (
            loan.payment_method_line_id
            or loan.journal_id.outbound_payment_method_line_ids[:1]
        )
        self.env["payroll.employee.loan.disburse"].with_context(
            active_id=loan.id
        ).create(
            {
                "loan_id": loan.id,
                "journal_id": loan.journal_id.id,
                "payment_method_line_id": method.id,
                "disbursement_account_id": loan.disbursement_account_id.id,
                "payment_date": Date.today(),
            }
        ).action_confirm_disburse()

        payslip = self.Payslip.create(
            {
                "employee_id": self.richard_emp.id,
                "contract_id": self.richard_contract.id,
                "struct_id": self.developer_pay_structure.id,
                "date_from": Date.today().replace(day=1),
                "date_to": Date.today(),
            }
        )
        payslip.onchange_employee()
        payslip.compute_sheet()
        loan_line = payslip.line_ids.filtered(lambda l: l.code == "LOANDED")
        self.assertTrue(loan_line)
        self.assertTrue(payslip.loan_installment_ids)
        payslip.action_payslip_done()
        self.assertTrue(
            all(i.state == "paid" for i in payslip.loan_installment_ids)
        )
        payslip.action_payslip_cancel()
        pending = loan.installment_ids.filtered(lambda i: i.state == "pending")
        self.assertTrue(pending)

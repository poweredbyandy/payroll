# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEmployeeLoan(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Loan Employee"})
        cls.company = cls.env.company
        cls.account_receivable = cls.env["account.account"].create(
            {
                "name": "Employee Loans",
                "code": "1310EMPL",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.account_bank = cls.env["account.account"].create(
            {
                "name": "Bank Disburse",
                "code": "1110EMPL",
                "account_type": "asset_cash",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Bank Emp Loan",
                "code": "BELN",
                "type": "bank",
                "company_id": cls.company.id,
                "default_account_id": cls.account_bank.id,
            }
        )
        cls.loan_type = cls.env["payroll.employee.loan.type"].create(
            {
                "name": "Standard",
                "loan_term": 3,
                "interest_rate": 0.0,
                "interest_type": "linear",
                "journal_id": cls.journal.id,
                "disbursement_account_id": cls.account_receivable.id,
            }
        )

    def test_loan_approval_and_installments(self):
        loan = self.env["payroll.employee.loan"].create(
            {
                "employee_id": self.employee.id,
                "loan_type_id": self.loan_type.id,
                "amount": 300.0,
                "term": 3,
                "date_start": fields.Date.today(),
                "notes": "Advance",
            }
        )
        loan.action_request()
        loan.action_dept_approve()
        loan.action_hr_approve()
        self.assertEqual(len(loan.installment_ids), 3)
        self.assertAlmostEqual(sum(loan.installment_ids.mapped("amount")), 300.0, places=2)
        action = loan.action_disburse()
        self.assertEqual(action["res_model"], "payroll.employee.loan.disburse")
        wizard = (
            self.env["payroll.employee.loan.disburse"]
            .with_context(active_id=loan.id)
            .create(
                {
                    "loan_id": loan.id,
                    "journal_id": self.journal.id,
                    "payment_method_line_id": loan.payment_method_line_id.id
                    or self.journal.outbound_payment_method_line_ids[:1].id,
                    "disbursement_account_id": self.account_receivable.id,
                    "payment_date": fields.Date.today(),
                }
            )
        )
        wizard.action_confirm_disburse()
        self.assertEqual(loan.state, "disbursed")
        self.assertTrue(loan.move_id)
        self.assertEqual(loan.move_id.state, "posted")

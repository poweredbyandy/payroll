# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoanDisbursementAccount(TransactionCase):
    """Disbursement wizard posts Dr receivable / Cr bank for the loan amount."""

    LOAN_AMOUNT = 1500.0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env["hr.employee"].create({"name": "Loan Disburse Emp"})
        cls.account_receivable = cls.env["account.account"].create(
            {
                "name": "Employee Loans Receivable",
                "code": "1310LOAN",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.account_bank = cls.env["account.account"].create(
            {
                "name": "Bank Loan Out",
                "code": "1110LOAN",
                "account_type": "asset_cash",
                "company_ids": [(6, 0, [cls.company.id])],
            }
        )
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Bank Loan Disburse",
                "code": "BLND",
                "type": "bank",
                "company_id": cls.company.id,
                "default_account_id": cls.account_bank.id,
            }
        )
        cls.loan_type = cls.env["payroll.employee.loan.type"].create(
            {
                "name": "Cash Advance",
                "loan_term": 3,
                "interest_rate": 0.0,
                "journal_id": cls.journal.id,
                "disbursement_account_id": cls.account_receivable.id,
            }
        )

    def _approve_to_hr(self, loan):
        loan.action_request()
        loan.action_dept_approve()
        loan.action_hr_approve()

    def _disburse(self, loan, **wizard_vals):
        action = loan.action_disburse()
        self.assertEqual(action["res_model"], "payroll.employee.loan.disburse")
        method = (
            loan.payment_method_line_id
            or self.journal.outbound_payment_method_line_ids[:1]
        )
        vals = {
            "loan_id": loan.id,
            "journal_id": self.journal.id,
            "payment_method_line_id": method.id,
            "payment_date": loan.date or fields.Date.today(),
        }
        vals.update(wizard_vals)
        wizard = (
            self.env["payroll.employee.loan.disburse"]
            .with_context(active_id=loan.id, active_model="payroll.employee.loan")
            .create(vals)
        )
        return wizard.action_confirm_disburse()

    def test_disburse_creates_posted_move(self):
        loan = self.env["payroll.employee.loan"].create(
            {
                "employee_id": self.employee.id,
                "loan_type_id": self.loan_type.id,
                "amount": self.LOAN_AMOUNT,
                "term": 3,
                "date": fields.Date.to_date("2026-09-15"),
                "date_start": fields.Date.to_date("2026-09-15"),
            }
        )
        self.assertEqual(loan.journal_id, self.journal)
        self.assertTrue(loan.payment_method_line_id)
        self._approve_to_hr(loan)
        self._disburse(loan)

        self.assertEqual(loan.state, "disbursed")
        self.assertTrue(loan.move_id)
        self.assertEqual(loan.move_id.state, "posted")
        self.assertEqual(loan.move_id.journal_id, self.journal)

        lines = loan.move_id.line_ids
        debit = lines.filtered(lambda line: line.debit)
        credit = lines.filtered(lambda line: line.credit)
        self.assertEqual(debit.account_id, self.account_receivable)
        self.assertEqual(credit.account_id, self.account_bank)
        self.assertEqual(debit.debit, self.LOAN_AMOUNT)
        self.assertEqual(credit.credit, self.LOAN_AMOUNT)

    def test_cancel_reverses_disbursement_move(self):
        loan = self.env["payroll.employee.loan"].create(
            {
                "employee_id": self.employee.id,
                "loan_type_id": self.loan_type.id,
                "amount": self.LOAN_AMOUNT,
                "term": 3,
                "date_start": fields.Date.today(),
            }
        )
        self._approve_to_hr(loan)
        self._disburse(loan)
        move = loan.move_id
        loan.action_cancel()
        self.assertEqual(loan.state, "cancelled")
        self.assertFalse(loan.move_id)
        self.assertEqual(move.state, "cancel")

    def test_wizard_shows_company_amount_other_currency(self):
        foreign = self.env["res.currency"].search(
            [("name", "=", "USD"), ("active", "in", [True, False])],
            limit=1,
        )
        if not foreign:
            self.skipTest("USD currency not available")
        foreign.active = True
        if foreign == self.company.currency_id:
            self.skipTest("Company currency is already USD")
        self.env["res.currency.rate"].create(
            {
                "currency_id": foreign.id,
                "name": fields.Date.to_date("2026-09-01"),
                "rate": 0.02,
                "company_id": self.company.id,
            }
        )
        loan = self.env["payroll.employee.loan"].create(
            {
                "employee_id": self.employee.id,
                "loan_type_id": self.loan_type.id,
                "amount": 100.0,
                "currency_id": foreign.id,
                "term": 2,
                "date": fields.Date.to_date("2026-09-15"),
                "date_start": fields.Date.to_date("2026-09-15"),
            }
        )
        self._approve_to_hr(loan)
        method = self.journal.outbound_payment_method_line_ids[:1]
        wizard = (
            self.env["payroll.employee.loan.disburse"]
            .with_context(active_id=loan.id, active_model="payroll.employee.loan")
            .create(
                {
                    "loan_id": loan.id,
                    "journal_id": self.journal.id,
                    "payment_method_line_id": method.id,
                    "payment_date": loan.date,
                }
            )
        )
        self.assertTrue(wizard.display_amount_company)
        expected = foreign._convert(
            100.0,
            self.company.currency_id,
            self.company,
            loan.date,
        )
        self.assertEqual(wizard.amount_company, expected)

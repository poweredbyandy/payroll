# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.tests import tagged

from .test_payroll_account import TestPayrollAccount


@tagged("post_install", "-at_install")
class TestPayrollAccountMulticurrency(TestPayrollAccount):
    def setUp(self):
        super().setUp()
        self.usd = self.env.ref("base.USD")
        self.ves = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "in", ("VES", "VEF"))], limit=1)
        )
        if not self.ves:
            self.ves = self.env["res.currency"].create(
                {"name": "VES", "symbol": "Bs.", "rounding": 0.01, "active": True}
            )
        else:
            self.ves.active = True
        self.env.company.currency_id = self.ves
        self.exchange_rate = 100.0
        self.hr_contract_john.write(
            {
                "currency_id": self.usd.id,
                "wage": 1000.0,
            }
        )

    def test_company_currency_totals_on_lines(self):
        self._update_account_in_rule(self.account_debit, self.account_credit)
        payslip = self._prepare_payslip(self.hr_employee_john)
        payslip.exchange_rate = self.exchange_rate
        payslip.compute_sheet()
        self.assertTrue(payslip.is_multicurrency)
        for line in payslip.line_ids:
            self.assertAlmostEqual(
                line.total_company_currency,
                line.total * self.exchange_rate,
                places=2,
            )

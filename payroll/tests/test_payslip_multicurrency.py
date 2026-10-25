# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TestPayslipBase


@tagged("post_install", "-at_install")
class TestPayslipMulticurrency(TestPayslipBase):
    EXCHANGE_RATE = 627.34

    def setUp(self):
        super().setUp()
        self.usd = self.env.ref("base.USD")
        self.eur = self.env.ref("base.EUR")
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

        self.company = self.env.company
        self.company.currency_id = self.ves

        today = fields.Date.today()
        for currency in (self.usd, self.eur):
            self.env["res.currency.rate"].create(
                {
                    "name": today,
                    "currency_id": currency.id,
                    "company_id": self.company.id,
                    "rate": 1.0 / self.EXCHANGE_RATE
                    if currency == self.usd
                    else 1.0 / (self.EXCHANGE_RATE * 1.1),
                }
            )

        self.richard_contract.write(
            {
                "currency_id": self.usd.id,
                "wage": 1000.0,
            }
        )

    def _create_payslip(self, employee=None, contract=None, exchange_rate=None):
        employee = employee or self.richard_emp
        contract = contract or self.richard_contract
        vals = {
            "employee_id": employee.id,
            "contract_id": contract.id,
            "struct_id": contract.struct_id.id,
            "date_from": fields.Date.to_string(fields.Date.today().replace(day=1)),
            "date_to": fields.Date.today(),
        }
        if exchange_rate is not None:
            vals["exchange_rate"] = exchange_rate
        return self.Payslip.create(vals)

    def test_contract_currency_differs_from_company(self):
        self.assertEqual(self.company.currency_id, self.ves)
        self.assertEqual(self.richard_contract.currency_id, self.usd)
        self.assertEqual(self.richard_contract.wage, 1000.0)

    def test_compute_sheet_sets_exchange_rate_and_company_total(self):
        payslip = self._create_payslip(exchange_rate=self.EXCHANGE_RATE)
        payslip.compute_sheet()
        self.assertTrue(payslip.is_multicurrency)
        self.assertAlmostEqual(payslip.exchange_rate, self.EXCHANGE_RATE, places=4)
        basic = payslip.line_ids.filtered(lambda line: line.code == "BASIC")
        self.assertTrue(basic)
        self.assertAlmostEqual(basic.total, 1000.0, places=2)
        self.assertAlmostEqual(
            basic.total_company_currency, 1000.0 * self.EXCHANGE_RATE, places=2
        )

    def test_missing_exchange_rate_raises(self):
        other = self.env["res.currency"].create(
            {"name": "XTS", "symbol": "X", "rounding": 0.01, "active": True}
        )
        self.richard_contract.currency_id = other
        payslip = self._create_payslip(exchange_rate=0.0)
        with self.assertRaises(UserError):
            payslip.compute_sheet()

    def test_same_currency_rate_is_one(self):
        self.richard_contract.currency_id = self.ves
        self.richard_contract.wage = 50000.0
        payslip = self._create_payslip()
        payslip.compute_sheet()
        self.assertFalse(payslip.is_multicurrency)
        self.assertAlmostEqual(payslip.exchange_rate, 1.0, places=4)

    def test_batch_propagates_exchange_rate(self):
        batch = self.env["hr.payslip.run"].create(
            {
                "name": "Batch multicurrency",
                "exchange_rate": self.EXCHANGE_RATE,
            }
        )
        payslip = self._create_payslip()
        payslip.payslip_run_id = batch
        payslip._onchange_exchange_rate()
        self.assertAlmostEqual(payslip.exchange_rate, self.EXCHANGE_RATE, places=4)

    def test_usd_and_eur_contracts_same_company(self):
        eur_emp = self.env["hr.employee"].create({"name": "Euro Emp"})
        eur_contract = self.Contract.create(
            {
                "name": "EUR contract",
                "employee_id": eur_emp.id,
                "wage": 900.0,
                "struct_id": self.developer_pay_structure.id,
                "date_start": fields.Date.today(),
                "kanban_state": "done",
            }
        )
        eur_contract.write({"currency_id": self.eur.id})
        self.assertEqual(eur_contract.currency_id, self.eur)
        payslip_usd = self._create_payslip(exchange_rate=self.EXCHANGE_RATE)
        payslip_eur = self._create_payslip(
            employee=eur_emp,
            contract=eur_contract,
            exchange_rate=self.EXCHANGE_RATE * 1.1,
        )
        payslip_usd.compute_sheet()
        payslip_eur.compute_sheet()
        self.assertEqual(payslip_usd.currency_id, self.usd)
        self.assertEqual(payslip_eur.currency_id, self.eur)
        self.assertEqual(payslip_usd.company_currency_id, self.ves)
        self.assertEqual(payslip_eur.company_currency_id, self.ves)

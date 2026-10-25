from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression


class HrPayslipEmployees(models.TransientModel):
    _name = "hr.payslip.employees"
    _description = "Generate payslips for all selected employees"

    employee_ids = fields.Many2many(
        "hr.employee",
        "hr_employee_group_rel",
        "payslip_id",
        "employee_id",
        string="Employees",
        default=lambda self: self._get_employees(),
    )

    def _get_payslip_run(self):
        return self.env["hr.payslip.run"].browse(self.env.context.get("active_id"))

    def _get_available_contracts_domain(self):
        """Employees with an open/closed contract overlapping the batch period."""
        payslip_run = self._get_payslip_run()
        contract_domain = [("state", "in", ("open", "close"))]
        if payslip_run:
            contract_domain = expression.AND(
                [
                    contract_domain,
                    [
                        ("date_start", "<=", payslip_run.date_end),
                        "|",
                        ("date_end", "=", False),
                        ("date_end", ">=", payslip_run.date_start),
                    ],
                ]
            )
            if payslip_run.struct_id:
                contract_domain = expression.AND(
                    [contract_domain, [("struct_id", "=", payslip_run.struct_id.id)]]
                )
            if payslip_run.company_id:
                contract_domain = expression.AND(
                    [
                        contract_domain,
                        [("company_id", "=", payslip_run.company_id.id)],
                    ]
                )
        return [
            ("contract_ids", "any", contract_domain),
            ("company_id", "=", self.env.company.id),
        ]

    def _get_employees(self):
        active_employee_ids = self.env.context.get("active_employee_ids")
        if active_employee_ids:
            return self.env["hr.employee"].browse(active_employee_ids)
        employees = self.env["hr.employee"].search(self._get_available_contracts_domain())
        payslip_run = self._get_payslip_run()
        if payslip_run:
            employees -= payslip_run.slip_ids.employee_id
        return employees

    def compute_sheet(self):
        self.ensure_one()
        active_id = self.env.context.get("active_id")
        if not active_id:
            raise UserError(_("Payslip batch is required to generate payslips."))
        run = self.env["hr.payslip.run"].browse(active_id)
        employees = self.employee_ids
        if not employees:
            raise UserError(_("You must select employee(s) to generate payslip(s)."))
        # Avoid duplicate payslips for the same employee in the batch.
        employees -= run.slip_ids.employee_id
        if not employees:
            raise UserError(
                _(
                    "All selected employees already have a payslip in this batch."
                )
            )
        from_date = run.date_start
        to_date = run.date_end
        struct_id = run.struct_id.ids if run.struct_id else False
        payslips = self.env["hr.payslip"]
        for employee in employees:
            slip_data = self.env["hr.payslip"].get_payslip_vals(
                from_date, to_date, employee.id, contract_id=False, struct_id=struct_id
            )
            contract_id = slip_data["value"].get("contract_id")
            structure_id = slip_data["value"].get("struct_id")
            if not contract_id or not structure_id:
                continue
            res = {
                "employee_id": employee.id,
                "name": slip_data["value"].get("name"),
                "struct_id": structure_id,
                "contract_id": contract_id,
                "payslip_run_id": active_id,
                "input_line_ids": [
                    (0, 0, x) for x in slip_data["value"].get("input_line_ids")
                ],
                "worked_days_line_ids": [
                    (0, 0, x) for x in slip_data["value"].get("worked_days_line_ids")
                ],
                "date_from": from_date,
                "date_to": to_date,
                "credit_note": run.credit_note,
                "company_id": employee.company_id.id,
            }
            if run.exchange_rate:
                res["exchange_rate"] = run.exchange_rate
            payslips += self.env["hr.payslip"].create(res)
        if not payslips:
            raise UserError(
                _(
                    "No payslip could be generated. Check that selected employees "
                    "have an open contract with a salary structure for this period."
                )
            )
        payslips._compute_name()
        payslips.compute_sheet()
        return {"type": "ir.actions.act_window_close"}

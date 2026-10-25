# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Payroll Employee Loan",
    "version": "18.0.1.4.0",
    "category": "Payroll",
    "website": "https://github.com/OCA/payroll",
    "license": "LGPL-3",
    "summary": "Employee loans with installments deducted from payslips",
    "author": "andyengit, Odoo Community Association (OCA)",
    "maintainers": ["andyengit"],
    "depends": ["payroll", "mail", "account"],
    "data": [
        "security/payroll_employee_loan_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/payroll_employee_loan_type_views.xml",
        "views/payroll_employee_loan_views.xml",
        "views/hr_payslip_views.xml",
        "wizard/payroll_employee_loan_disburse_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}

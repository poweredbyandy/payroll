1. Configure loan types (term, interest) and optional default disbursement
   journal (used only to prefill the wizard). The loan receivable account comes
   from company settings (or an optional override on the loan / loan type).
2. Create the loan and follow approvals until **HR Approved**.
3. Click **Disburse**: choose **Journal**, **Payment Method** and date in the
   wizard (not on the loan form). When the loan currency differs from the
   company currency, the wizard also shows the converted company amount, then
   posts `Dr Loan receivable / Cr Bank-Cash` on `move_id`.
4. On payslip compute, pending installments are added as input code LOAN
   (Installment Deduction = Payslip).
5. Confirming the payslip marks installments as paid; cancel reverts them.
6. Cancelling the loan cancels the disbursement entry if it exists.

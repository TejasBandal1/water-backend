from datetime import datetime
from app.models.invoice import Invoice


def update_overdue_status(invoice: Invoice):
    if (
        invoice.status == "pending" and
        invoice.due_date and
        invoice.due_date < datetime.utcnow()
    ):
        invoice.status = "overdue"

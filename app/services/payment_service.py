from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from app.models.invoice import Invoice
from app.models.payment import Payment


def record_payment(invoice_id: int, amount: float, db: Session):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == "draft":
        raise HTTPException(status_code=400, detail="Confirm invoice first")

    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="Invoice already paid")

    remaining = invoice.total_amount - invoice.amount_paid

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    if amount > remaining:
        raise HTTPException(status_code=400, detail="Payment exceeds remaining balance")

    # Create payment
    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        created_at=datetime.utcnow()
    )

    db.add(payment)

    # Update invoice
    invoice.amount_paid += amount

    if invoice.amount_paid == invoice.total_amount:
        invoice.status = "paid"
    elif invoice.amount_paid > 0:
        invoice.status = "partial"
    else:
        invoice.status = "pending"

    db.commit()

    return {
        "message": "Payment recorded successfully",
        "new_status": invoice.status
    }

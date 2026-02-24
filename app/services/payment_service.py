from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from app.models.invoice import Invoice
from app.models.payment import Payment


ALLOWED_METHODS = {"CASH", "UPI", "CASH_UPI"}


def _round_money(value: float) -> float:
    return round(float(value or 0), 2)


def record_payment(
    invoice_id: int,
    amount: float,
    db: Session,
    method: str = "CASH",
    cash_amount: float | None = None,
    upi_amount: float | None = None,
    upi_account: str | None = None,
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == "draft":
        raise HTTPException(status_code=400, detail="Confirm invoice first")

    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="Invoice already paid")

    remaining = _round_money(invoice.total_amount - invoice.amount_paid)
    amount = _round_money(amount)

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid payment amount")

    if amount > remaining:
        raise HTTPException(status_code=400, detail="Payment exceeds remaining balance")

    method = (method or "").strip().upper()
    if method not in ALLOWED_METHODS:
        raise HTTPException(
            status_code=400,
            detail="Invalid payment method. Use CASH, UPI, or CASH_UPI",
        )

    normalized_upi_account = (upi_account or "").strip() or None

    normalized_cash = 0.0
    normalized_upi = 0.0

    if method == "CASH":
        normalized_cash = amount
    elif method == "UPI":
        if not normalized_upi_account:
            raise HTTPException(
                status_code=400,
                detail="UPI account is required for UPI payments",
            )
        normalized_upi = amount
    else:
        normalized_cash = _round_money(cash_amount or 0)
        normalized_upi = _round_money(upi_amount or 0)

        if normalized_cash <= 0 or normalized_upi <= 0:
            raise HTTPException(
                status_code=400,
                detail="Both cash and UPI amounts are required for CASH_UPI payments",
            )

        if _round_money(normalized_cash + normalized_upi) != amount:
            raise HTTPException(
                status_code=400,
                detail="Cash + UPI split must equal total payment amount",
            )

        if not normalized_upi_account:
            raise HTTPException(
                status_code=400,
                detail="UPI account is required when UPI amount is used",
            )

    # Create payment
    payment = Payment(
        invoice_id=invoice.id,
        amount=amount,
        method=method,
        cash_amount=normalized_cash,
        upi_amount=normalized_upi,
        upi_account=normalized_upi_account,
        created_at=datetime.utcnow()
    )

    db.add(payment)

    # Update invoice
    invoice.amount_paid = _round_money(invoice.amount_paid + amount)

    if invoice.amount_paid >= _round_money(invoice.total_amount):
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

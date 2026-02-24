from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_role
from app.services.payment_service import record_payment
from app.services.audit_service import log_action
from app.schemas.payment import PaymentRecordRequest

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/record/{invoice_id}")
def add_payment(
    invoice_id: int,
    amount: float | None = Query(default=None),
    payload: PaymentRecordRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    payment_amount = payload.amount if payload else amount
    payment_method = payload.method if payload else "CASH"
    payment_cash = payload.cash_amount if payload else None
    payment_upi = payload.upi_amount if payload else None
    payment_upi_account = payload.upi_account if payload else None

    result = record_payment(
        invoice_id=invoice_id,
        amount=payment_amount or 0,
        db=db,
        method=payment_method,
        cash_amount=payment_cash,
        upi_amount=payment_upi,
        upi_account=payment_upi_account,
    )

    details = (
        f"Payment added: {payment_amount} | Method: {payment_method} | "
        f"Cash: {payment_cash or 0} | UPI: {payment_upi or 0} | "
        f"UPI Account: {payment_upi_account or 'N/A'}"
    )

    log_action(
        db=db,
        user_id=user.id,
        action="ADD_PAYMENT",
        entity_type="Invoice",
        entity_id=invoice_id,
        details=details
    )

    return result

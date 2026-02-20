from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import get_db, require_role
from app.services.payment_service import record_payment
from app.services.audit_service import log_action

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/record/{invoice_id}")
def add_payment(
    invoice_id: int,
    amount: float,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    result = record_payment(invoice_id, amount, db)

    log_action(
        db=db,
        user_id=user.id,
        action="ADD_PAYMENT",
        entity_type="Invoice",
        entity_id=invoice_id,
        details=f"Payment added: {amount}"
    )

    return result

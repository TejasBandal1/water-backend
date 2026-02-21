from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.services.container_balance_service import get_client_container_balance


router = APIRouter(prefix="/client", tags=["Client"])


def _require_client_link(user):
    if not user.client_id:
        raise HTTPException(
            status_code=400,
            detail="Client account not properly linked",
        )


@router.get("/my-balance", include_in_schema=False)
def my_balance(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"])),
):
    _require_client_link(user)
    return get_client_container_balance(user.client_id, db)


@router.get("/invoices")
def get_my_invoices(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"])),
):
    _require_client_link(user)

    invoices = (
        db.query(Invoice)
        .filter(Invoice.client_id == user.client_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )

    return invoices


@router.get("/payments")
def get_my_payments(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"])),
):
    _require_client_link(user)

    payments = (
        db.query(Payment)
        .join(Invoice)
        .filter(Invoice.client_id == user.client_id)
        .all()
    )

    return payments


@router.get("/balance")
def get_my_balance(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"])),
):
    _require_client_link(user)
    return get_client_container_balance(user.client_id, db)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.dependencies import require_role, get_db
from app.services.container_balance_service import get_client_container_balance
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import require_role, get_db
from app.models.invoice import Invoice
from app.models.payment import Payment

router = APIRouter(prefix="/client", tags=["Client"])


@router.get("/my-balance")
def my_balance(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"]))
):
    return get_client_container_balance(user.id, db)


@router.get("/invoices")
def get_my_invoices(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"]))
):
    # 🔐 Multi-tenant isolation
    if not user.client_id:
        raise HTTPException(
            status_code=400,
            detail="Client account not properly linked"
        )

    invoices = db.query(Invoice).filter(
        Invoice.client_id == user.client_id
    ).order_by(Invoice.created_at.desc()).all()

    return invoices

@router.get("/payments")
def get_my_payments(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"]))
):
    if not user.client_id:
        raise HTTPException(
            status_code=400,
            detail="Client account not properly linked"
        )

    payments = db.query(Payment).join(Invoice).filter(
        Invoice.client_id == user.client_id
    ).all()

    return payments
from app.services.container_balance_service import get_client_container_balance

@router.get("/balance")
def get_my_balance(
    db: Session = Depends(get_db),
    user=Depends(require_role(["client"]))
):
    if not user.client_id:
        raise HTTPException(
            status_code=400,
            detail="Client account not properly linked"
        )

    return get_client_container_balance(user.client_id, db)

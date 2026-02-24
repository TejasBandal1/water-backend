from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.dependencies import require_role, get_db
from app.services.analytics_service import (
    revenue_per_client,
    outstanding_summary,
    monthly_revenue,
    container_loss_report,
    payment_breakdown,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/revenue-per-client")
def get_revenue_per_client(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    return revenue_per_client(db, from_date, to_date)


@router.get("/outstanding")
def get_outstanding(
    client_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    return outstanding_summary(db, client_id)


@router.get("/monthly-revenue")
def get_monthly_revenue(
    period: str = Query("month"),  # day, week, month, year
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    client_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    return monthly_revenue(db, period, from_date, to_date, client_id)


@router.get("/container-loss")
def get_container_loss(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    client_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    return container_loss_report(db, from_date, to_date, client_id)


@router.get("/payment-breakdown")
def get_payment_breakdown(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    client_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    return payment_breakdown(db, from_date, to_date, client_id)

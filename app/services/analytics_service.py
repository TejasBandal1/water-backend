from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from app.models.invoice import Invoice
from app.models.trip_container import TripContainer
from app.models.trip import Trip


# =====================================================
# REVENUE PER CLIENT (with optional date filtering)
# =====================================================

def revenue_per_client(db: Session, from_date: str | None, to_date: str | None):

    query = (
        db.query(
            Invoice.client_id,
            func.sum(Invoice.total_amount).label("total_revenue")
        )
        .filter(Invoice.status == "paid")
    )

    if from_date:
        query = query.filter(
            Invoice.confirmed_at >= datetime.fromisoformat(from_date)
        )

    if to_date:
        query = query.filter(
            Invoice.confirmed_at <= datetime.fromisoformat(to_date)
        )

    results = query.group_by(Invoice.client_id).all()

    return [
        {
            "client_id": r.client_id,
            "total_revenue": float(r.total_revenue or 0)
        }
        for r in results
    ]


# =====================================================
# OUTSTANDING + PROFESSIONAL KPIs
# =====================================================

def outstanding_summary(db: Session):

    total_billed = db.query(
        func.sum(Invoice.total_amount)
    ).scalar() or 0

    total_paid = db.query(
        func.sum(Invoice.amount_paid)
    ).scalar() or 0

    total_outstanding = (
        db.query(func.sum(Invoice.total_amount - Invoice.amount_paid))
        .filter(Invoice.status.in_(["pending", "overdue"]))
        .scalar()
    ) or 0

    collection_rate = (
        (total_paid / total_billed) * 100
        if total_billed > 0 else 0
    )

    return {
        "total_billed": float(total_billed),
        "total_paid": float(total_paid),
        "total_outstanding": float(total_outstanding),
        "collection_rate": round(collection_rate, 2)
    }


# =====================================================
# MONTHLY / DAILY / WEEKLY / YEARLY REVENUE
# =====================================================

def monthly_revenue(
    db: Session,
    period: str,
    from_date: str | None,
    to_date: str | None
):

    # Map frontend values to postgres date_trunc
    period_map = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "yearly": "year"
    }

    trunc_value = period_map.get(period, "month")

    query = db.query(
        func.date_trunc(trunc_value, Invoice.confirmed_at).label("label"),
        func.sum(Invoice.total_amount).label("revenue")
    ).filter(Invoice.status == "paid")

    if from_date:
        query = query.filter(
            Invoice.confirmed_at >= datetime.fromisoformat(from_date)
        )

    if to_date:
        query = query.filter(
            Invoice.confirmed_at <= datetime.fromisoformat(to_date)
        )

    results = (
        query
        .group_by("label")
        .order_by("label")
        .all()
    )

    return [
        {
            "label": str(r.label),
            "revenue": float(r.revenue or 0)
        }
        for r in results
    ]


# =====================================================
# CONTAINER LOSS REPORT (with filters + extra metrics)
# =====================================================

def container_loss_report(
    db: Session,
    from_date: str | None,
    to_date: str | None
):

    query = (
        db.query(
            TripContainer.container_id,
            func.sum(TripContainer.delivered_qty).label("delivered"),
            func.sum(TripContainer.returned_qty).label("returned")
        )
        .join(Trip, Trip.id == TripContainer.trip_id)
    )

    if from_date:
        query = query.filter(
            Trip.created_at >= datetime.fromisoformat(from_date)
        )

    if to_date:
        query = query.filter(
            Trip.created_at <= datetime.fromisoformat(to_date)
        )

    results = query.group_by(
        TripContainer.container_id
    ).all()

    report = []

    for r in results:
        delivered = r.delivered or 0
        returned = r.returned or 0
        net_outstanding = delivered - returned

        utilization_rate = (
            (returned / delivered) * 100
            if delivered > 0 else 0
        )

        report.append({
            "container_id": r.container_id,
            "delivered": delivered,
            "returned": returned,
            "net_outstanding": net_outstanding,
            "utilization_rate": round(utilization_rate, 2)
        })

    return report

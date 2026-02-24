from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, time
from app.models.invoice import Invoice
from app.models.trip_container import TripContainer
from app.models.trip import Trip
from app.models.container import ContainerType

ACTIVE_BILLING_STATUSES = ["pending", "partial", "overdue", "paid"]
OUTSTANDING_STATUSES = ["pending", "partial", "overdue"]


def _parse_from_date(date_value: str | None) -> datetime | None:
    if not date_value:
        return None

    parsed = datetime.fromisoformat(date_value)
    if "T" not in date_value:
        return datetime.combine(parsed.date(), time.min)
    return parsed


def _parse_to_date(date_value: str | None) -> datetime | None:
    if not date_value:
        return None

    parsed = datetime.fromisoformat(date_value)
    if "T" not in date_value:
        return datetime.combine(parsed.date(), time.max)
    return parsed


# =====================================================
# REVENUE PER CLIENT (with optional date filtering)
# =====================================================

def revenue_per_client(db: Session, from_date: str | None, to_date: str | None):
    from_dt = _parse_from_date(from_date)
    to_dt = _parse_to_date(to_date)

    query = (
        db.query(
            Invoice.client_id,
            func.sum(Invoice.total_amount).label("total_revenue")
        )
        .filter(Invoice.status == "paid")
    )

    if from_dt:
        query = query.filter(
            Invoice.confirmed_at >= from_dt
        )

    if to_dt:
        query = query.filter(
            Invoice.confirmed_at <= to_dt
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

def outstanding_summary(db: Session, client_id: int | None = None):

    billed_query = db.query(func.sum(Invoice.total_amount)).filter(
        Invoice.status.in_(ACTIVE_BILLING_STATUSES)
    )

    paid_query = db.query(func.sum(Invoice.amount_paid)).filter(
        Invoice.status.in_(ACTIVE_BILLING_STATUSES)
    )

    outstanding_query = db.query(
        func.sum(Invoice.total_amount - Invoice.amount_paid)
    ).filter(
        Invoice.status.in_(OUTSTANDING_STATUSES)
    )

    if client_id is not None:
        billed_query = billed_query.filter(Invoice.client_id == client_id)
        paid_query = paid_query.filter(Invoice.client_id == client_id)
        outstanding_query = outstanding_query.filter(Invoice.client_id == client_id)

    total_billed = billed_query.scalar() or 0

    total_paid = paid_query.scalar() or 0

    total_outstanding = outstanding_query.scalar() or 0

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
    to_date: str | None,
    client_id: int | None = None
):
    from_dt = _parse_from_date(from_date)
    to_dt = _parse_to_date(to_date)

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

    if client_id is not None:
        query = query.filter(Invoice.client_id == client_id)

    if from_dt:
        query = query.filter(
            Invoice.confirmed_at >= from_dt
        )

    if to_dt:
        query = query.filter(
            Invoice.confirmed_at <= to_dt
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
    to_date: str | None,
    client_id: int | None = None
):
    from_dt = _parse_from_date(from_date)
    to_dt = _parse_to_date(to_date)

    query = (
        db.query(
            TripContainer.container_id,
            func.sum(TripContainer.delivered_qty).label("delivered"),
            func.sum(TripContainer.returned_qty).label("returned")
        )
        .join(Trip, Trip.id == TripContainer.trip_id)
        .join(ContainerType, ContainerType.id == TripContainer.container_id)
        .filter(ContainerType.is_returnable == True)
    )

    if client_id is not None:
        query = query.filter(Trip.client_id == client_id)

    if from_dt:
        query = query.filter(
            Trip.created_at >= from_dt
        )

    if to_dt:
        query = query.filter(
            Trip.created_at <= to_dt
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

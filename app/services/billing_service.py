from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
from app.models.trip import Trip
from app.models.trip_container import TripContainer
from app.models.client_price import ClientContainerPrice
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from datetime import datetime


def generate_draft_invoice(client_id: int, db: Session):

    # ✅ Calculate quantity using ONLY delivered_qty
    trip_data = (
        db.query(
            TripContainer.container_id,
            func.sum(
                TripContainer.delivered_qty   # 🔥 FIXED (no subtraction)
            ).label("total_qty")
        )
        .join(Trip, Trip.id == TripContainer.trip_id)
        .filter(
            Trip.client_id == client_id,
            Trip.invoice_id.is_(None)
        )
        .group_by(TripContainer.container_id)
        .all()
    )

    # 🔥 Remove zero or null quantities
    trip_data = [
        row for row in trip_data
        if row.total_qty and row.total_qty > 0
    ]

    if not trip_data:
        raise HTTPException(
            status_code=400,
            detail="No billable deliveries found for this client"
        )

    # 🔒 Validate pricing BEFORE creating invoice
    for row in trip_data:
        price = (
            db.query(ClientContainerPrice)
            .filter(
                ClientContainerPrice.client_id == client_id,
                ClientContainerPrice.container_id == row.container_id
            )
            .order_by(ClientContainerPrice.effective_from.desc())
            .first()
        )

        if not price:
            raise HTTPException(
                status_code=400,
                detail=f"Price not set for container ID {row.container_id}"
            )

    # ✅ Create invoice
    invoice = Invoice(
        client_id=client_id,
        status="draft",
        total_amount=0,
        amount_paid=0,
        created_at=datetime.utcnow()
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    total_invoice_amount = 0

    # 🔁 Create invoice items
    for row in trip_data:

        price = (
            db.query(ClientContainerPrice)
            .filter(
                ClientContainerPrice.client_id == client_id,
                ClientContainerPrice.container_id == row.container_id
            )
            .order_by(ClientContainerPrice.effective_from.desc())
            .first()
        )

        total = row.total_qty * price.price
        total_invoice_amount += total

        item = InvoiceItem(
            invoice_id=invoice.id,
            container_id=row.container_id,
            quantity=row.total_qty,
            price_snapshot=price.price,
            total=total
        )

        db.add(item)

    invoice.total_amount = total_invoice_amount
    db.commit()

    # 🔒 Lock trips to this invoice
    trips = (
        db.query(Trip)
        .filter(
            Trip.client_id == client_id,
            Trip.invoice_id.is_(None)
        )
        .all()
    )

    for trip in trips:
        trip.invoice_id = invoice.id

    db.commit()

    return invoice



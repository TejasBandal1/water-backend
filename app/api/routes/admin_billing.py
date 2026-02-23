from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_db, require_role
from app.models.client import Client
from app.models.client_price import ClientContainerPrice
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.trip import Trip
from app.services.audit_service import log_action
from app.services.billing_service import generate_draft_invoice

router = APIRouter(prefix="/admin/billing", tags=["Billing"])


class InvoiceActionReason(BaseModel):
    reason: str = Field(..., min_length=3, max_length=300)


# =========================
# GENERATE SINGLE INVOICE
# =========================
@router.post("/generate/{client_id}")
def generate_invoice(
    client_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    invoice = generate_draft_invoice(client_id, db)

    log_action(
        db=db,
        user_id=user.id,
        action="GENERATE_DRAFT_INVOICE",
        entity_type="Invoice",
        entity_id=invoice.id,
        details=f"Draft invoice generated for client {client_id}"
    )

    return invoice


# =========================
# CONFIRM INVOICE
# =========================
@router.post("/confirm/{invoice_id}")
def confirm_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "draft":
        raise HTTPException(status_code=400, detail="Invoice already processed")

    invoice.status = "pending"
    invoice.confirmed_at = datetime.utcnow()
    invoice.due_date = datetime.utcnow() + timedelta(days=7)

    db.commit()

    log_action(
        db=db,
        user_id=user.id,
        action="CONFIRM_INVOICE",
        entity_type="Invoice",
        entity_id=invoice.id,
        details=f"Invoice confirmed with total {invoice.total_amount}"
    )

    return {"message": "Invoice confirmed and locked"}


# =========================
# CANCEL INVOICE
# =========================
@router.post("/cancel/{invoice_id}")
def cancel_invoice(
    invoice_id: int,
    payload: InvoiceActionReason,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status not in ["draft", "pending"]:
        raise HTTPException(
            status_code=400,
            detail="Only draft or pending invoices can be cancelled"
        )

    if invoice.amount_paid and invoice.amount_paid > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel invoice with recorded payments"
        )

    invoice.status = "cancelled"
    db.commit()

    log_action(
        db=db,
        user_id=user.id,
        action="CANCEL_INVOICE",
        entity_type="Invoice",
        entity_id=invoice_id,
        details=f"Invoice cancelled. Reason: {payload.reason.strip()}"
    )

    return {"message": "Invoice cancelled successfully"}


# =========================
# VOID + REISSUE INVOICE
# =========================
@router.post("/void-reissue/{invoice_id}")
def void_reissue_invoice(
    invoice_id: int,
    payload: InvoiceActionReason,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status not in ["draft", "pending"]:
        raise HTTPException(
            status_code=400,
            detail="Only draft or pending invoices can be voided and reissued"
        )

    if invoice.amount_paid and invoice.amount_paid > 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot void and reissue invoice with recorded payments"
        )

    old_items = (
        db.query(InvoiceItem)
        .filter(InvoiceItem.invoice_id == invoice.id)
        .all()
    )

    if not old_items:
        raise HTTPException(
            status_code=400,
            detail="Cannot reissue invoice without line items"
        )

    reason = payload.reason.strip()

    try:
        new_invoice = Invoice(
            client_id=invoice.client_id,
            status="draft",
            total_amount=0,
            amount_paid=0,
            created_at=datetime.utcnow()
        )
        db.add(new_invoice)
        db.flush()

        new_total = 0

        for item in old_items:
            latest_price = (
                db.query(ClientContainerPrice)
                .filter(
                    ClientContainerPrice.client_id == invoice.client_id,
                    ClientContainerPrice.container_id == item.container_id
                )
                .order_by(ClientContainerPrice.effective_from.desc())
                .first()
            )

            effective_price = latest_price.price if latest_price else item.price_snapshot
            line_total = item.quantity * effective_price
            new_total += line_total

            db.add(
                InvoiceItem(
                    invoice_id=new_invoice.id,
                    container_id=item.container_id,
                    quantity=item.quantity,
                    price_snapshot=effective_price,
                    total=line_total
                )
            )

        trips = db.query(Trip).filter(Trip.invoice_id == invoice.id).all()
        for trip in trips:
            trip.invoice_id = new_invoice.id

        invoice.status = "cancelled"
        new_invoice.total_amount = new_total

        db.commit()
        db.refresh(new_invoice)

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to void and reissue invoice")

    log_action(
        db=db,
        user_id=user.id,
        action="VOID_REISSUE_INVOICE",
        entity_type="Invoice",
        entity_id=new_invoice.id,
        details=(
            f"Old invoice {invoice.id} voided and reissued as "
            f"{new_invoice.id}. Reason: {reason}"
        )
    )

    return {
        "message": "Invoice voided and reissued successfully",
        "old_invoice_id": invoice.id,
        "new_invoice_id": new_invoice.id
    }


# =========================
# GENERATE ALL DRAFTS
# =========================
@router.post("/generate-all")
def generate_all_invoices(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    clients = db.query(Client).filter(Client.is_active == True).all()

    if not clients:
        raise HTTPException(
            status_code=400,
            detail="No active clients found"
        )

    generated = []
    skipped = []

    for client in clients:
        try:
            invoice = generate_draft_invoice(client.id, db)

            generated.append({
                "client_id": client.id,
                "client_name": client.name,
                "invoice_id": invoice.id
            })

        except Exception as e:
            skipped.append({
                "client_id": client.id,
                "client_name": client.name,
                "reason": str(e)
            })

    return {
        "generated": generated,
        "skipped": skipped
    }


# =========================
# GET ALL INVOICES
# =========================
@router.get("/all")
def get_all_invoices(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    invoices = (
        db.query(Invoice)
        .options(joinedload(Invoice.client))
        .order_by(Invoice.id.desc())
        .all()
    )

    result = []

    for inv in invoices:
        status = inv.status

        # Overdue logic (ignore cancelled)
        if (
            inv.status == "pending"
            and inv.due_date
            and datetime.utcnow() > inv.due_date
        ):
            status = "overdue"

        items = (
            db.query(InvoiceItem)
            .options(joinedload(InvoiceItem.container))
            .filter(InvoiceItem.invoice_id == inv.id)
            .all()
        )

        container_summary = [
            {
                "container_name": item.container.name,
                "quantity": item.quantity
            }
            for item in items
        ]

        result.append({
            "id": inv.id,
            "client_id": inv.client_id,
            "client_name": inv.client.name if inv.client else None,
            "total_amount": inv.total_amount,
            "amount_paid": inv.amount_paid,
            "status": status,
            "created_at": inv.created_at,
            "due_date": inv.due_date,
            "containers": container_summary
        })

    return result


# =========================
# GET INVOICE DETAIL
# =========================
@router.get("/{invoice_id}")
def get_invoice_detail(
    invoice_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client))
        .filter(Invoice.id == invoice_id)
        .first()
    )

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    status = invoice.status

    if (
        invoice.status == "pending"
        and invoice.due_date
        and datetime.utcnow() > invoice.due_date
    ):
        status = "overdue"

    items = (
        db.query(InvoiceItem)
        .options(joinedload(InvoiceItem.container))
        .filter(InvoiceItem.invoice_id == invoice_id)
        .all()
    )

    payments = (
        db.query(Payment)
        .filter(Payment.invoice_id == invoice_id)
        .order_by(Payment.created_at.desc())
        .all()
    )

    return {
        "invoice": {
            "id": invoice.id,
            "client": invoice.client,
            "total_amount": invoice.total_amount,
            "amount_paid": invoice.amount_paid,
            "status": status,
            "created_at": invoice.created_at,
            "due_date": invoice.due_date
        },
        "items": items,
        "payments": payments
    }

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta

from app.core.dependencies import require_role, get_db
from app.services.billing_service import generate_draft_invoice
from app.services.audit_service import log_action

from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.trip import Trip
from app.models.client import Client

router = APIRouter(prefix="/admin/billing", tags=["Billing"])


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
# CANCEL INVOICE (ERP STYLE)
# =========================
@router.post("/cancel/{invoice_id}")
def cancel_invoice(
    invoice_id: int,
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

    # 🔒 DO NOT unlock trips
    # 🔒 DO NOT delete items
    # Just mark as cancelled

    invoice.status = "cancelled"
    db.commit()

    log_action(
        db=db,
        user_id=user.id,
        action="CANCEL_INVOICE",
        entity_type="Invoice",
        entity_id=invoice_id,
        details="Invoice cancelled (voided)"
    )

    return {"message": "Invoice cancelled successfully"}


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

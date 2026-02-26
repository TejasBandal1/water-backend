from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract
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
from app.services.payment_service import record_payment

router = APIRouter(prefix="/admin/billing", tags=["Billing"])


class InvoiceActionReason(BaseModel):
    reason: str = Field(..., min_length=3, max_length=300)


class MonthlyPaymentRequest(BaseModel):
    client_id: int
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    amount: float = Field(..., gt=0)
    method: Literal["CASH", "UPI", "CASH_UPI"] = "CASH"
    cash_amount: float | None = None
    upi_amount: float | None = None
    upi_account: str | None = None


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

    return {
        "message": "Draft invoice generated successfully",
        "invoice": {
            "id": invoice.id,
            "client_id": invoice.client_id,
            "status": invoice.status,
            "total_amount": invoice.total_amount,
            "amount_paid": invoice.amount_paid,
            "created_at": invoice.created_at,
        }
    }


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

    log_action(
        db=db,
        user_id=user.id,
        action="GENERATE_ALL_DRAFT_INVOICES",
        entity_type="InvoiceBatch",
        details=(
            f"Generated: {len(generated)} | Skipped: {len(skipped)}"
        )
    )

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


def _to_money(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def _resolved_status(invoice: Invoice) -> str:
    if (
        invoice.status == "pending"
        and invoice.due_date
        and datetime.utcnow() > invoice.due_date
    ):
        return "overdue"

    return invoice.status


# =========================
# MONTHLY BILLING SUMMARY
# =========================
@router.get("/monthly")
def get_monthly_billing_summary(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    now = datetime.utcnow()
    selected_year = year or now.year
    selected_month = month or now.month

    invoice_query = (
        db.query(Invoice)
        .options(joinedload(Invoice.client))
        .filter(
            extract("year", Invoice.created_at) == selected_year,
            extract("month", Invoice.created_at) == selected_month,
            Invoice.status.in_(["pending", "partial", "overdue", "paid"])
        )
        .order_by(Invoice.created_at.asc(), Invoice.id.asc())
    )

    if search and search.strip():
        term = f"%{search.strip()}%"
        invoice_query = invoice_query.join(Client, Client.id == Invoice.client_id).filter(
            Client.name.ilike(term)
        )

    invoices = invoice_query.all()

    by_client: dict[int, dict] = {}
    total_monthly_billed = 0.0
    total_monthly_paid = 0.0
    total_monthly_outstanding = 0.0
    total_pending_invoices = 0

    for invoice in invoices:
        if not invoice.client:
            continue

        status = _resolved_status(invoice)
        total_amount = _to_money(invoice.total_amount)
        paid_amount = _to_money(invoice.amount_paid)
        outstanding = _to_money(max(total_amount - paid_amount, 0))
        invoice_day = (
            invoice.created_at.strftime("%Y-%m-%d")
            if invoice.created_at
            else None
        )

        if invoice.client_id not in by_client:
            by_client[invoice.client_id] = {
                "client_id": invoice.client_id,
                "client_name": invoice.client.name,
                "invoice_count": 0,
                "pending_invoice_count": 0,
                "total_monthly_bill": 0.0,
                "total_paid": 0.0,
                "total_outstanding": 0.0,
                "pending_invoices": [],
                "daily_map": {}
            }

        client_entry = by_client[invoice.client_id]
        client_entry["invoice_count"] += 1
        client_entry["total_monthly_bill"] = _to_money(
            client_entry["total_monthly_bill"] + total_amount
        )
        client_entry["total_paid"] = _to_money(
            client_entry["total_paid"] + paid_amount
        )
        client_entry["total_outstanding"] = _to_money(
            client_entry["total_outstanding"] + outstanding
        )

        if outstanding > 0 and status in {"pending", "partial", "overdue"}:
            client_entry["pending_invoice_count"] += 1
            client_entry["pending_invoices"].append({
                "id": invoice.id,
                "status": status,
                "invoice_date": invoice_day,
                "due_date": invoice.due_date,
                "total_amount": total_amount,
                "amount_paid": paid_amount,
                "outstanding_amount": outstanding
            })

        if invoice_day:
            if invoice_day not in client_entry["daily_map"]:
                client_entry["daily_map"][invoice_day] = {
                    "date": invoice_day,
                    "invoice_count": 0,
                    "invoice_ids": [],
                    "billed_amount": 0.0,
                    "paid_amount": 0.0,
                    "outstanding_amount": 0.0
                }

            day_entry = client_entry["daily_map"][invoice_day]
            day_entry["invoice_count"] += 1
            day_entry["invoice_ids"].append(invoice.id)
            day_entry["billed_amount"] = _to_money(day_entry["billed_amount"] + total_amount)
            day_entry["paid_amount"] = _to_money(day_entry["paid_amount"] + paid_amount)
            day_entry["outstanding_amount"] = _to_money(
                day_entry["outstanding_amount"] + outstanding
            )

        total_monthly_billed = _to_money(total_monthly_billed + total_amount)
        total_monthly_paid = _to_money(total_monthly_paid + paid_amount)
        total_monthly_outstanding = _to_money(
            total_monthly_outstanding + outstanding
        )

        if outstanding > 0 and status in {"pending", "partial", "overdue"}:
            total_pending_invoices += 1

    rows = []
    for entry in by_client.values():
        daily_rows = sorted(entry["daily_map"].values(), key=lambda row: row["date"])
        pending_invoices = sorted(
            entry["pending_invoices"],
            key=lambda inv: (inv["invoice_date"] or "", inv["id"])
        )

        rows.append({
            "client_id": entry["client_id"],
            "client_name": entry["client_name"],
            "invoice_count": entry["invoice_count"],
            "pending_invoice_count": entry["pending_invoice_count"],
            "total_monthly_bill": entry["total_monthly_bill"],
            "total_paid": entry["total_paid"],
            "total_outstanding": entry["total_outstanding"],
            "daily_details": daily_rows,
            "pending_invoices": pending_invoices
        })

    rows = sorted(
        rows,
        key=lambda row: (-row["total_outstanding"], row["client_name"].lower())
    )

    return {
        "year": selected_year,
        "month": selected_month,
        "rows": rows,
        "summary": {
            "clients_count": len(rows),
            "pending_invoices_count": total_pending_invoices,
            "total_monthly_bill": total_monthly_billed,
            "total_paid": total_monthly_paid,
            "total_outstanding": total_monthly_outstanding
        }
    }


# =========================
# MONTHLY CLIENT PAYMENT
# =========================
@router.post("/monthly/pay")
def record_monthly_client_payment(
    payload: MonthlyPaymentRequest,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    payment_amount = _to_money(payload.amount)
    payment_method = (payload.method or "CASH").strip().upper()

    invoices = (
        db.query(Invoice)
        .filter(
            Invoice.client_id == payload.client_id,
            extract("year", Invoice.created_at) == payload.year,
            extract("month", Invoice.created_at) == payload.month,
            Invoice.status.in_(["pending", "partial", "overdue"])
        )
        .order_by(Invoice.created_at.asc(), Invoice.id.asc())
        .all()
    )

    if not invoices:
        raise HTTPException(
            status_code=404,
            detail="No pending monthly invoices found for this client"
        )

    invoice_remaining_map: dict[int, float] = {}
    monthly_outstanding = 0.0

    for invoice in invoices:
        remaining = _to_money(invoice.total_amount - invoice.amount_paid)
        if remaining <= 0:
            continue

        invoice_remaining_map[invoice.id] = remaining
        monthly_outstanding = _to_money(monthly_outstanding + remaining)

    if monthly_outstanding <= 0:
        raise HTTPException(
            status_code=400,
            detail="No outstanding amount left for selected month"
        )

    if payment_amount > monthly_outstanding:
        raise HTTPException(
            status_code=400,
            detail="Payment exceeds selected month outstanding amount"
        )

    normalized_upi_account = (payload.upi_account or "").strip() or None
    total_cash_component = 0.0
    total_upi_component = 0.0

    if payment_method == "CASH":
        total_cash_component = payment_amount
    elif payment_method == "UPI":
        if not normalized_upi_account:
            raise HTTPException(status_code=400, detail="UPI account is required")

        total_upi_component = payment_amount
    elif payment_method == "CASH_UPI":
        if not normalized_upi_account:
            raise HTTPException(status_code=400, detail="UPI account is required")

        total_cash_component = _to_money(payload.cash_amount)
        total_upi_component = _to_money(payload.upi_amount)

        if total_cash_component <= 0 or total_upi_component <= 0:
            raise HTTPException(
                status_code=400,
                detail="Cash and UPI amounts are required for CASH_UPI"
            )

        if _to_money(total_cash_component + total_upi_component) != payment_amount:
            raise HTTPException(
                status_code=400,
                detail="Cash + UPI must equal total monthly payment amount"
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid payment method. Use CASH, UPI, or CASH_UPI"
        )

    remaining_amount = payment_amount
    remaining_cash = total_cash_component
    remaining_upi = total_upi_component
    applied = []

    billable_invoices = [inv for inv in invoices if inv.id in invoice_remaining_map]
    billable_invoice_ids = [inv.id for inv in billable_invoices]

    for idx, invoice in enumerate(billable_invoices):

        if remaining_amount <= 0:
            break

        invoice_remaining = invoice_remaining_map[invoice.id]
        apply_amount = _to_money(min(invoice_remaining, remaining_amount))

        cash_component = None
        upi_component = None

        if payment_method == "CASH_UPI":
            is_last_application = (
                idx == len(billable_invoices) - 1 or apply_amount == remaining_amount
            )

            if is_last_application:
                cash_component = _to_money(max(remaining_cash, 0))
                upi_component = _to_money(max(remaining_upi, 0))
            else:
                ratio = remaining_cash / remaining_amount if remaining_amount > 0 else 0
                cash_component = _to_money(apply_amount * ratio)
                upi_component = _to_money(apply_amount - cash_component)

                if cash_component > remaining_cash:
                    cash_component = _to_money(remaining_cash)
                    upi_component = _to_money(apply_amount - cash_component)

                if upi_component > remaining_upi:
                    upi_component = _to_money(remaining_upi)
                    cash_component = _to_money(apply_amount - upi_component)

                if cash_component < 0:
                    cash_component = 0.0
                if upi_component < 0:
                    upi_component = 0.0

                component_total = _to_money(cash_component + upi_component)
                if component_total != apply_amount:
                    diff = _to_money(apply_amount - component_total)
                    if diff != 0:
                        if remaining_upi >= remaining_cash:
                            upi_component = _to_money(upi_component + diff)
                        else:
                            cash_component = _to_money(cash_component + diff)

        record_payment(
            invoice_id=invoice.id,
            amount=apply_amount,
            db=db,
            method=payment_method,
            cash_amount=cash_component,
            upi_amount=upi_component,
            upi_account=normalized_upi_account,
            allow_zero_split=True
        )

        remaining_amount = _to_money(remaining_amount - apply_amount)

        if payment_method == "CASH_UPI":
            remaining_cash = _to_money(remaining_cash - (cash_component or 0))
            remaining_upi = _to_money(remaining_upi - (upi_component or 0))

        applied.append({
            "invoice_id": invoice.id,
            "applied_amount": apply_amount
        })

    if remaining_amount > 0:
        raise HTTPException(
            status_code=500,
            detail="Monthly payment allocation failed. Please retry."
        )

    log_action(
        db=db,
        user_id=user.id,
        action="ADD_MONTHLY_PAYMENT",
        entity_type="Client",
        entity_id=payload.client_id,
        details=(
            f"Monthly payment {payment_amount} recorded for "
            f"{payload.year}-{str(payload.month).zfill(2)} | "
            f"Method: {payment_method} | Invoices: {billable_invoice_ids}"
        )
    )

    return {
        "message": "Monthly payment recorded successfully",
        "client_id": payload.client_id,
        "year": payload.year,
        "month": payload.month,
        "total_applied": payment_amount,
        "applied_invoices": applied,
        "remaining_month_outstanding": _to_money(monthly_outstanding - payment_amount)
    }


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

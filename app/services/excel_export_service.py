from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
from typing import Literal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session, joinedload

from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.payment import Payment
from app.models.trip import Trip
from app.models.trip_container import TripContainer

ExportReportType = Literal["invoices", "billing", "payments", "full"]

ALLOWED_STATUSES = {"draft", "pending", "partial", "overdue", "paid", "cancelled"}


def _to_money(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def _resolved_status(invoice: Invoice) -> str:
    if (
        invoice.status == "pending"
        and invoice.due_date
        and datetime.utcnow() > invoice.due_date
    ):
        return "overdue"

    return (invoice.status or "").strip().lower()


def _to_datetime_range(
    from_date: date | None,
    to_date: date | None
) -> tuple[datetime | None, datetime | None]:
    start_dt = datetime.combine(from_date, time.min) if from_date else None
    end_dt = datetime.combine(to_date, time.max) if to_date else None
    return start_dt, end_dt


def _write_sheet(ws, headers: list[str], rows: list[list]):
    ws.append(headers)
    for row in rows:
        ws.append(row)

    header_fill = PatternFill("solid", fgColor="1E293B")
    header_font = Font(color="FFFFFF", bold=True)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for col_cells in ws.columns:
        max_len = 0
        for cell in col_cells:
            text = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(text))
        column_letter = col_cells[0].column_letter
        ws.column_dimensions[column_letter].width = min(max(max_len + 2, 12), 48)


def _build_invoices_data(
    db: Session,
    start_dt: datetime | None,
    end_dt: datetime | None,
    client_id: int | None,
    driver_id: int | None,
    status: str | None,
    include_cancelled: bool
) -> tuple[list[Invoice], list[list], list[list]]:
    invoices_query = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.client),
            joinedload(Invoice.trips).joinedload(Trip.driver)
        )
    )

    if start_dt:
        invoices_query = invoices_query.filter(Invoice.created_at >= start_dt)
    if end_dt:
        invoices_query = invoices_query.filter(Invoice.created_at <= end_dt)
    if client_id:
        invoices_query = invoices_query.filter(Invoice.client_id == client_id)
    if driver_id:
        invoices_query = invoices_query.filter(Invoice.trips.any(Trip.driver_id == driver_id))
    if not include_cancelled:
        invoices_query = invoices_query.filter(Invoice.status != "cancelled")
    if status and status != "overdue":
        invoices_query = invoices_query.filter(Invoice.status == status)

    invoices = (
        invoices_query
        .order_by(Invoice.created_at.desc(), Invoice.id.desc())
        .all()
    )

    if status:
        invoices = [inv for inv in invoices if _resolved_status(inv) == status]

    invoice_rows: list[list] = []
    for invoice in invoices:
        driver_names = sorted({
            (trip.driver.name or "").strip()
            for trip in (invoice.trips or [])
            if trip.driver and (trip.driver.name or "").strip()
        })
        total_amount = _to_money(invoice.total_amount)
        amount_paid = _to_money(invoice.amount_paid)
        outstanding = _to_money(max(total_amount - amount_paid, 0))

        invoice_rows.append([
            invoice.id,
            invoice.client_id,
            invoice.client.name if invoice.client else None,
            ", ".join(driver_names) if driver_names else None,
            _resolved_status(invoice),
            invoice.created_at.isoformat() if invoice.created_at else None,
            invoice.due_date.isoformat() if invoice.due_date else None,
            invoice.confirmed_at.isoformat() if invoice.confirmed_at else None,
            total_amount,
            amount_paid,
            outstanding,
            len(invoice.trips or [])
        ])

    invoice_ids = [invoice.id for invoice in invoices]
    invoice_item_rows: list[list] = []

    if invoice_ids:
        item_query = (
            db.query(InvoiceItem, Invoice)
            .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
            .options(
                joinedload(InvoiceItem.container),
                joinedload(Invoice.client)
            )
            .filter(InvoiceItem.invoice_id.in_(invoice_ids))
            .order_by(InvoiceItem.invoice_id.asc(), InvoiceItem.id.asc())
        )

        for item, invoice in item_query.all():
            invoice_item_rows.append([
                item.invoice_id,
                invoice.client_id if invoice else None,
                invoice.client.name if invoice and invoice.client else None,
                item.container_id,
                item.container.name if item.container else None,
                int(item.quantity or 0),
                _to_money(item.price_snapshot),
                _to_money(item.total)
            ])

    return invoices, invoice_rows, invoice_item_rows


def _build_trips_data(
    db: Session,
    start_dt: datetime | None,
    end_dt: datetime | None,
    client_id: int | None,
    driver_id: int | None,
    status: str | None,
    include_cancelled: bool
) -> list[list]:
    trips_query = (
        db.query(Trip)
        .options(
            joinedload(Trip.client),
            joinedload(Trip.driver),
            joinedload(Trip.invoice)
        )
    )

    if start_dt:
        trips_query = trips_query.filter(Trip.created_at >= start_dt)
    if end_dt:
        trips_query = trips_query.filter(Trip.created_at <= end_dt)
    if client_id:
        trips_query = trips_query.filter(Trip.client_id == client_id)
    if driver_id:
        trips_query = trips_query.filter(Trip.driver_id == driver_id)

    trips = trips_query.order_by(Trip.created_at.desc(), Trip.id.desc()).all()

    trip_ids = [trip.id for trip in trips]
    trip_container_map: dict[int, list[TripContainer]] = {}

    if trip_ids:
        trip_containers = (
            db.query(TripContainer)
            .options(joinedload(TripContainer.container))
            .filter(TripContainer.trip_id.in_(trip_ids))
            .all()
        )

        for trip_container in trip_containers:
            trip_container_map.setdefault(trip_container.trip_id, []).append(trip_container)

    trip_rows: list[list] = []

    for trip in trips:
        invoice = trip.invoice
        invoice_status = _resolved_status(invoice) if invoice else None

        if status:
            if not invoice_status or invoice_status != status:
                continue

        if not include_cancelled and invoice_status == "cancelled":
            continue

        containers = trip_container_map.get(trip.id, [])
        delivered_total = sum(int(tc.delivered_qty or 0) for tc in containers)
        returned_total = sum(int(tc.returned_qty or 0) for tc in containers)

        container_breakdown = "; ".join(
            f"{tc.container.name if tc.container else f'Container {tc.container_id}'} "
            f"(D:{int(tc.delivered_qty or 0)} R:{int(tc.returned_qty or 0)})"
            for tc in sorted(
                containers,
                key=lambda x: (x.container.name.lower() if x.container and x.container.name else "")
            )
        )

        trip_rows.append([
            trip.id,
            trip.created_at.isoformat() if trip.created_at else None,
            trip.client_id,
            trip.client.name if trip.client else None,
            trip.driver_id,
            trip.driver.name if trip.driver else None,
            trip.invoice_id,
            invoice_status,
            delivered_total,
            returned_total,
            container_breakdown
        ])

    return trip_rows


def _build_payments_data(
    db: Session,
    start_dt: datetime | None,
    end_dt: datetime | None,
    client_id: int | None,
    driver_id: int | None,
    status: str | None,
    payment_method: str | None,
    include_cancelled: bool
) -> list[list]:
    payments_query = (
        db.query(Payment)
        .options(
            joinedload(Payment.invoice)
            .joinedload(Invoice.client),
            joinedload(Payment.invoice)
            .joinedload(Invoice.trips)
            .joinedload(Trip.driver)
        )
    )

    if start_dt:
        payments_query = payments_query.filter(Payment.created_at >= start_dt)
    if end_dt:
        payments_query = payments_query.filter(Payment.created_at <= end_dt)
    if payment_method:
        payments_query = payments_query.filter(Payment.method == payment_method)
    if client_id:
        payments_query = payments_query.join(Invoice, Payment.invoice_id == Invoice.id).filter(
            Invoice.client_id == client_id
        )

    payments = (
        payments_query
        .order_by(Payment.created_at.desc(), Payment.id.desc())
        .all()
    )

    payment_rows: list[list] = []

    for payment in payments:
        invoice = payment.invoice
        invoice_status = _resolved_status(invoice) if invoice else None

        if status:
            if not invoice_status or invoice_status != status:
                continue

        if not include_cancelled and invoice_status == "cancelled":
            continue

        if driver_id:
            invoice_driver_ids = {
                trip.driver_id
                for trip in (invoice.trips or [])
            } if invoice else set()
            if driver_id not in invoice_driver_ids:
                continue

        payment_rows.append([
            payment.id,
            payment.created_at.isoformat() if payment.created_at else None,
            payment.invoice_id,
            invoice.client_id if invoice else None,
            invoice.client.name if invoice and invoice.client else None,
            invoice_status,
            payment.method,
            _to_money(payment.amount),
            _to_money(payment.cash_amount),
            _to_money(payment.upi_amount),
            payment.upi_account
        ])

    return payment_rows


def build_excel_export(
    db: Session,
    report_type: ExportReportType = "full",
    from_date: date | None = None,
    to_date: date | None = None,
    client_id: int | None = None,
    driver_id: int | None = None,
    status: str | None = None,
    payment_method: str | None = None,
    include_cancelled: bool = False
) -> tuple[bytes, str, dict]:
    normalized_status = (status or "").strip().lower() or None
    if normalized_status and normalized_status not in ALLOWED_STATUSES:
        raise ValueError("Invalid status filter")

    start_dt, end_dt = _to_datetime_range(from_date, to_date)

    invoices, invoice_rows, invoice_item_rows = _build_invoices_data(
        db=db,
        start_dt=start_dt,
        end_dt=end_dt,
        client_id=client_id,
        driver_id=driver_id,
        status=normalized_status,
        include_cancelled=include_cancelled
    )

    trip_rows = _build_trips_data(
        db=db,
        start_dt=start_dt,
        end_dt=end_dt,
        client_id=client_id,
        driver_id=driver_id,
        status=normalized_status,
        include_cancelled=include_cancelled
    )

    payment_rows = _build_payments_data(
        db=db,
        start_dt=start_dt,
        end_dt=end_dt,
        client_id=client_id,
        driver_id=driver_id,
        status=normalized_status,
        payment_method=payment_method,
        include_cancelled=include_cancelled
    )

    total_invoiced_amount = _to_money(sum(row[8] for row in invoice_rows))
    total_paid_amount = _to_money(sum(row[9] for row in invoice_rows))
    total_outstanding_amount = _to_money(sum(row[10] for row in invoice_rows))
    total_payment_amount = _to_money(sum(row[7] for row in payment_rows))
    total_delivered_jars = int(sum(row[8] for row in trip_rows))
    total_returned_jars = int(sum(row[9] for row in trip_rows))

    wb = Workbook()
    summary_ws = wb.active
    summary_ws.title = "Summary"

    summary_headers = ["Metric", "Value"]
    summary_rows = [
        ["Generated At (UTC)", datetime.utcnow().isoformat()],
        ["Report Type", report_type],
        ["From Date", from_date.isoformat() if from_date else "All"],
        ["To Date", to_date.isoformat() if to_date else "All"],
        ["Client ID", client_id if client_id else "All"],
        ["Driver ID", driver_id if driver_id else "All"],
        ["Invoice Status Filter", normalized_status or "All"],
        ["Payment Method Filter", payment_method or "All"],
        ["Include Cancelled", "Yes" if include_cancelled else "No"],
        ["Invoices Count", len(invoices)],
        ["Invoice Items Count", len(invoice_item_rows)],
        ["Trips Count", len(trip_rows)],
        ["Payments Count", len(payment_rows)],
        ["Total Invoiced Amount", total_invoiced_amount],
        ["Total Invoice Paid Amount", total_paid_amount],
        ["Total Invoice Outstanding", total_outstanding_amount],
        ["Total Payments Amount", total_payment_amount],
        ["Total Delivered Jars", total_delivered_jars],
        ["Total Returned Jars", total_returned_jars],
    ]
    _write_sheet(summary_ws, summary_headers, summary_rows)

    if report_type in {"invoices", "full"}:
        invoices_ws = wb.create_sheet("Invoices")
        _write_sheet(
            invoices_ws,
            [
                "Invoice ID",
                "Client ID",
                "Client Name",
                "Driver Name(s)",
                "Status",
                "Created At (UTC)",
                "Due Date (UTC)",
                "Confirmed At (UTC)",
                "Total Amount",
                "Amount Paid",
                "Outstanding Amount",
                "Trip Count"
            ],
            invoice_rows
        )

        invoice_items_ws = wb.create_sheet("Invoice_Items")
        _write_sheet(
            invoice_items_ws,
            [
                "Invoice ID",
                "Client ID",
                "Client Name",
                "Container ID",
                "Container Name",
                "Quantity",
                "Price Snapshot",
                "Line Total"
            ],
            invoice_item_rows
        )

    if report_type in {"billing", "full"}:
        trips_ws = wb.create_sheet("Bills_Trips")
        _write_sheet(
            trips_ws,
            [
                "Trip ID",
                "Trip DateTime (UTC)",
                "Client ID",
                "Client Name",
                "Driver ID",
                "Driver Name",
                "Invoice ID",
                "Invoice Status",
                "Delivered Jars",
                "Returned Jars",
                "Container Breakdown"
            ],
            trip_rows
        )

    if report_type in {"payments", "full"}:
        payments_ws = wb.create_sheet("Payments")
        _write_sheet(
            payments_ws,
            [
                "Payment ID",
                "Payment DateTime (UTC)",
                "Invoice ID",
                "Client ID",
                "Client Name",
                "Invoice Status",
                "Payment Method",
                "Amount",
                "Cash Amount",
                "UPI Amount",
                "UPI Account"
            ],
            payment_rows
        )

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    exported_at = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"rivarich_{report_type}_export_{exported_at}.xlsx"

    export_meta = {
        "invoices_count": len(invoices),
        "invoice_items_count": len(invoice_item_rows),
        "trips_count": len(trip_rows),
        "payments_count": len(payment_rows),
        "total_invoiced": total_invoiced_amount,
        "total_outstanding": total_outstanding_amount,
        "total_payments": total_payment_amount
    }

    return output.getvalue(), filename, export_meta

from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
from typing import Optional


def log_action(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: str,
    entity_id: int = None,
    details: str = None
):
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details
        )

        db.add(log)
        db.commit()
    except Exception:
        # Audit logging must never block primary application flows.
        db.rollback()


def log_auth_event(
    db: Session,
    action: str,
    email: str,
    user_id: Optional[int] = None,
    details: str = None
):
    message = f"Email: {email}"
    if details:
        message = f"{message} | {details}"

    log_action(
        db=db,
        user_id=user_id,
        action=action,
        entity_type="Auth",
        entity_id=user_id,
        details=message
    )

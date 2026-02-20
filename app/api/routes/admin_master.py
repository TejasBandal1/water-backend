from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import require_role, get_db
from app.core.security import hash_password

from app.models.container import ContainerType
from app.models.client import Client
from app.models.client_price import ClientContainerPrice
from app.models.user import User
from app.models.role import Role
from app.models.audit_log import AuditLog

from app.schemas.container import ContainerCreate
from app.schemas.client import ClientCreate
from app.schemas.client_price import ClientPriceCreate
from app.schemas.user import UserCreate

from app.services.container_balance_service import get_client_container_balance
from app.services.audit_service import log_action
from datetime import datetime
from sqlalchemy.orm import joinedload

from app.schemas.user import UserResponse
router = APIRouter(prefix="/admin", tags=["Admin Master"])


# ---------------- CONTAINERS ----------------

@router.post("/containers")
def create_container(
    container: ContainerCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    new_container = ContainerType(**container.dict())
    db.add(new_container)
    db.commit()
    db.refresh(new_container)

    log_action(
        db=db,
        user_id=user.id,
        action="CREATE_CONTAINER",
        entity_type="Container",
        entity_id=new_container.id,
        details=f"Container '{new_container.name}' created"
    )

    return new_container


@router.get("/containers")
def get_containers(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return db.query(ContainerType).all()


# ---------------- CLIENTS ----------------

@router.post("/clients")
def create_client(
    client: ClientCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    new_client = Client(**client.dict())
    db.add(new_client)
    db.commit()
    db.refresh(new_client)

    log_action(
        db=db,
        user_id=user.id,
        action="CREATE_CLIENT",
        entity_type="Client",
        entity_id=new_client.id,
        details=f"Client '{new_client.name}' created"
    )

    return new_client


@router.get("/clients")
def get_clients(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return db.query(Client).all()


# ---------------- CLIENT PRICING ----------------

@router.post("/client-prices")
def set_client_price(
    price_data: ClientPriceCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):

    # If admin does NOT send effective_from → use now
    new_effective_date = price_data.effective_from or datetime.utcnow()

    existing_prices = (
        db.query(ClientContainerPrice)
        .filter(
            ClientContainerPrice.client_id == price_data.client_id,
            ClientContainerPrice.container_id == price_data.container_id
        )
        .order_by(ClientContainerPrice.effective_from.desc())
        .all()
    )

    # 🚫 Prevent duplicate effective date
    for p in existing_prices:
        if p.effective_from == new_effective_date:
            raise HTTPException(
                status_code=400,
                detail="A price already exists for this effective date."
            )

    # 🚫 Prevent backdating
    if existing_prices:
        latest_price = existing_prices[0]

        if new_effective_date <= latest_price.effective_from:
            raise HTTPException(
                status_code=400,
                detail="New price must have a later effective date than current price."
            )

    # ✅ Create price
    new_price = ClientContainerPrice(
        client_id=price_data.client_id,
        container_id=price_data.container_id,
        price=price_data.price,
        effective_from=new_effective_date
    )

    db.add(new_price)
    db.commit()
    db.refresh(new_price)

    log_action(
        db=db,
        user_id=user.id,
        action="SET_CLIENT_PRICE",
        entity_type="ClientContainerPrice",
        entity_id=new_price.id,
        details=f"Price set to {new_price.price} for client {new_price.client_id} and container {new_price.container_id}"
    )

    return {"message": "Price set successfully"}

@router.get("/client-prices")
def get_client_prices(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    return db.query(ClientContainerPrice).all()


# ---------------- CLIENT BALANCE ----------------

@router.get("/clients/{client_id}/balance")
def view_client_balance(
    client_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin", "manager"]))
):
    return get_client_container_balance(client_id, db)


# ---------------- USERS ----------------

@router.get("/users", response_model=list[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    users = db.query(User).all()

    return [
        UserResponse(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role.name,
            client_id=u.client_id
        )
        for u in users
    ]

@router.post("/users")
def create_user_admin(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    role = db.query(Role).filter(Role.name == user_data.role).first()

    if not role:
        raise HTTPException(status_code=400, detail="Invalid role")

    # 🔥 NEW VALIDATION LOGIC
    if user_data.role == "client":
        if not user_data.client_id:
            raise HTTPException(
                status_code=400,
                detail="Client ID is required for client role"
            )

        # Check client exists
        client = db.query(Client).filter(
            Client.id == user_data.client_id
        ).first()

        if not client:
            raise HTTPException(
                status_code=404,
                detail="Client not found"
            )
    else:
        # Ensure non-client roles don't attach to client
        user_data.client_id = None

    new_user = User(
        name=user_data.name,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        role_id=role.id,
        client_id=user_data.client_id  # 🔥 NEW FIELD
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_action(
        db=db,
        user_id=admin.id,
        action="CREATE_USER",
        entity_type="User",
        entity_id=new_user.id,
        details=f"User '{new_user.email}' created with role {user_data.role}"
    )

    return new_user



@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    new_role: str,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    user = db.query(User).filter(User.id == user_id).first()
    role = db.query(Role).filter(Role.name == new_role).first()

    if not user or not role:
        raise HTTPException(status_code=404, detail="User or role not found")

    user.role_id = role.id
    db.commit()

    log_action(
        db=db,
        user_id=admin.id,
        action="UPDATE_USER_ROLE",
        entity_type="User",
        entity_id=user.id,
        details=f"Role changed to {new_role}"
    )

    return {"message": "Role updated successfully"}


# ---------------- AUDIT LOGS ----------------

# ---------------- AUDIT LOGS ----------------

@router.get("/audit-logs")
def get_audit_logs(
    db: Session = Depends(get_db),
    user=Depends(require_role(["admin"]))
):
    logs = (
        db.query(AuditLog)
        .options(
            joinedload(AuditLog.user).joinedload(User.role)
        )
        .order_by(AuditLog.timestamp.desc())
        .all()
    )

    result = []

    for log in logs:
        result.append({
            "id": log.id,
            "timestamp": log.timestamp,
            "user": {
                "id": log.user_id,
                "name": log.user.name if log.user else "Deleted User",
                "role": log.user.role.name if log.user and log.user.role else None
            },
            "action": log.action,
            "entity": {
                "type": log.entity_type,
                "id": log.entity_id
            },
            "details": log.details
        })

    return result


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    log_action(
        db=db,
        user_id=admin.id,
        action="DELETE_USER",
        entity_type="User",
        entity_id=user_id,
        details=f"User deleted"
    )

    return {"message": "User deleted successfully"}

@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    user_data: UserCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = db.query(Role).filter(Role.name == user_data.role).first()

    if not role:
        raise HTTPException(status_code=400, detail="Invalid role")

    user.name = user_data.name
    user.email = user_data.email
    user.role_id = role.id

    if user_data.password:
        user.hashed_password = hash_password(user_data.password)

    # Handle client assignment
    if user_data.role == "client":
        user.client_id = user_data.client_id
    else:
        user.client_id = None

    db.commit()

    log_action(
        db=db,
        user_id=admin.id,
        action="UPDATE_USER",
        entity_type="User",
        entity_id=user.id,
        details="User details updated"
    )

    return {"message": "User updated successfully"}

# UPDATE CLIENT
@router.put("/clients/{client_id}")
def update_client(
    client_id: int,
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.name = client_data.name
    client.email = client_data.email
    client.phone = client_data.phone
    client.address = client_data.address
    client.billing_type = client_data.billing_type
    client.billing_interval = client_data.billing_interval

    db.commit()

    return {"message": "Client updated successfully"}


# DELETE CLIENT
@router.delete("/clients/{client_id}")
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    db.delete(client)
    db.commit()

    return {"message": "Client deleted successfully"}

# UPDATE CONTAINER
@router.put("/containers/{container_id}")
def update_container(
    container_id: int,
    container_data: ContainerCreate,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    container = db.query(ContainerType).filter(
        ContainerType.id == container_id
    ).first()

    if not container:
        raise HTTPException(status_code=404, detail="Container not found")

    container.name = container_data.name
    container.description = container_data.description

    db.commit()

    return {"message": "Container updated successfully"}


# DELETE CONTAINER
@router.delete("/containers/{container_id}")
def delete_container(
    container_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    container = db.query(ContainerType).filter(
        ContainerType.id == container_id
    ).first()

    if not container:
        raise HTTPException(status_code=404, detail="Container not found")

    container.is_active = False  # SOFT DELETE
    db.commit()

    return {"message": "Container deactivated successfully"}


from datetime import datetime
from fastapi import Query

@router.get("/delivery-matrix")
def get_delivery_matrix(
    start_date: str = Query(...),
    end_date: str = Query(...),
    db: Session = Depends(get_db),
    admin=Depends(require_role(["admin"]))
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        # make end date inclusive
        end = end.replace(hour=23, minute=59, second=59)

    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format")

    from sqlalchemy import func
    from app.models.trip import Trip
    from app.models.trip_container import TripContainer
    from app.models.client import Client

    results = (
        db.query(
            Client.name.label("name"),
            func.date(Trip.created_at).label("date"),
            func.sum(TripContainer.delivered_qty).label("total_delivered")
        )
        .join(TripContainer, Trip.id == TripContainer.trip_id)
        .join(Client, Client.id == Trip.client_id)
        .filter(Trip.created_at >= start, Trip.created_at <= end)
        .group_by(Client.name, func.date(Trip.created_at))
        .all()
    )

    return [
        {
            "name": r.name,
            "date": r.date,
            "total_delivered": r.total_delivered or 0
        }
        for r in results
    ]

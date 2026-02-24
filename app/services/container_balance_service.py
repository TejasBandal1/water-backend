from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.trip import Trip
from app.models.trip_container import TripContainer
from app.models.container import ContainerType
from app.models.client import Client


def get_client_container_balance(client_id: int, db: Session):
    results = (
        db.query(
            TripContainer.container_id,
            ContainerType.name,
            func.sum(TripContainer.delivered_qty).label("total_delivered"),
            func.sum(TripContainer.returned_qty).label("total_returned"),
        )
        .join(Trip, Trip.id == TripContainer.trip_id)
        .join(ContainerType, ContainerType.id == TripContainer.container_id)
        .filter(
            Trip.client_id == client_id,
            ContainerType.is_returnable == True,
        )
        .group_by(TripContainer.container_id, ContainerType.name)
        .all()
    )

    balance_data = []

    for row in results:
        balance = (row.total_delivered or 0) - (row.total_returned or 0)

        balance_data.append({
            "container_id": row.container_id,
            "container_name": row.name,
            "total_delivered": row.total_delivered or 0,
            "total_returned": row.total_returned or 0,
            "balance": balance
        })

    return balance_data


def get_clients_pending_returns(db: Session, search: str | None = None):
    query = (
        db.query(
            Trip.client_id.label("client_id"),
            Client.name.label("client_name"),
            TripContainer.container_id.label("container_id"),
            ContainerType.name.label("container_name"),
            func.sum(TripContainer.delivered_qty).label("total_delivered"),
            func.sum(TripContainer.returned_qty).label("total_returned"),
        )
        .join(Trip, Trip.id == TripContainer.trip_id)
        .join(Client, Client.id == Trip.client_id)
        .join(ContainerType, ContainerType.id == TripContainer.container_id)
        .filter(
            Client.is_active == True,
            ContainerType.is_returnable == True,
        )
    )

    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(Client.name).like(pattern))

    rows = (
        query
        .group_by(
            Trip.client_id,
            Client.name,
            TripContainer.container_id,
            ContainerType.name,
        )
        .all()
    )

    by_client: dict[int, dict] = {}

    for row in rows:
        pending_qty = (row.total_delivered or 0) - (row.total_returned or 0)
        if pending_qty <= 0:
            continue

        if row.client_id not in by_client:
            by_client[row.client_id] = {
                "client_id": row.client_id,
                "client_name": row.client_name,
                "total_pending_return": 0,
                "containers": [],
            }

        by_client[row.client_id]["total_pending_return"] += pending_qty
        by_client[row.client_id]["containers"].append(
            {
                "container_id": row.container_id,
                "container_name": row.container_name,
                "pending_qty": pending_qty,
            }
        )

    result = list(by_client.values())

    for client in result:
        client["containers"].sort(
            key=lambda container: container["pending_qty"],
            reverse=True,
        )

    result.sort(
        key=lambda client: client["total_pending_return"],
        reverse=True,
    )

    return result

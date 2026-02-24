from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.trip import Trip
from app.models.trip_container import TripContainer
from app.models.container import ContainerType


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

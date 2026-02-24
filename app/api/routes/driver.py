from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.models.client import Client
from app.models.container import ContainerType
from app.models.trip import Trip
from app.models.trip_container import TripContainer
from app.schemas.trip import TripCreate
from app.services.audit_service import log_action


router = APIRouter(prefix="/driver", tags=["Driver"])


@router.post("/trips")
def create_trip(
    trip_data: TripCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(["driver"])),
):
    container_ids = {item.container_id for item in trip_data.containers}
    containers = (
        db.query(ContainerType)
        .filter(ContainerType.id.in_(container_ids))
        .all()
    )
    container_map = {c.id: c for c in containers}
    missing_ids = sorted(container_ids - set(container_map.keys()))
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid container IDs: {missing_ids}",
        )

    new_trip = Trip(
        client_id=trip_data.client_id,
        driver_id=user.id,
    )

    db.add(new_trip)
    db.commit()
    db.refresh(new_trip)

    total_delivered = 0
    total_returned = 0

    for item in trip_data.containers:
        container = container_map[item.container_id]
        returned_qty = item.returned_qty

        if not container.is_returnable:
            returned_qty = 0

        if item.delivered_qty == 0 and returned_qty == 0:
            continue

        if item.delivered_qty < 0 or returned_qty < 0:
            raise HTTPException(
                status_code=400,
                detail="Quantities cannot be negative",
            )

        total_delivered += item.delivered_qty
        total_returned += returned_qty

        trip_container = TripContainer(
            trip_id=new_trip.id,
            container_id=item.container_id,
            delivered_qty=item.delivered_qty,
            returned_qty=returned_qty,
        )

        db.add(trip_container)

    db.commit()

    log_action(
        db=db,
        user_id=user.id,
        action="CREATE_TRIP",
        entity_type="Trip",
        entity_id=new_trip.id,
        details=(
            f"Trip created for client {trip_data.client_id} | "
            f"Delivered: {total_delivered} | Returned: {total_returned}"
        ),
    )

    return {"message": "Trip recorded successfully"}


@router.get("/clients")
def get_clients_for_driver(
    db: Session = Depends(get_db),
    user=Depends(require_role(["driver"])),
):
    return db.query(Client).filter(Client.is_active == True).all()


@router.get("/containers")
def get_containers_for_driver(
    db: Session = Depends(get_db),
    user=Depends(require_role(["driver"])),
):
    return db.query(ContainerType).filter(ContainerType.is_active == True).all()


@router.get("/trips")
def get_driver_trips(
    db: Session = Depends(get_db),
    driver=Depends(require_role(["driver"])),
):
    trips = (
        db.query(Trip)
        .filter(Trip.driver_id == driver.id)
        .order_by(Trip.created_at.desc())
        .all()
    )

    enriched = []

    for trip in trips:
        trip_containers = db.query(TripContainer).filter(
            TripContainer.trip_id == trip.id
        ).all()

        total_delivered = sum(tc.delivered_qty for tc in trip_containers)
        total_returned = sum(tc.returned_qty for tc in trip_containers)

        enriched.append(
            {
                "id": trip.id,
                "created_at": trip.created_at,
                "client": trip.client,
                "total_delivered": total_delivered,
                "total_returned": total_returned,
            }
        )

    return enriched


@router.get("/orders")
@router.get("/driver/orders", include_in_schema=False)
def get_driver_orders(
    db: Session = Depends(get_db),
    driver=Depends(require_role(["driver"])),
):
    orders = (
        db.query(TripContainer)
        .join(Trip)
        .filter(Trip.driver_id == driver.id)
        .all()
    )

    return orders

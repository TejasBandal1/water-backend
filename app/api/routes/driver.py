from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import require_role, get_db
from app.models.trip import Trip
from app.models.trip_container import TripContainer
from app.schemas.trip import TripCreate
from app.models.client import Client
from app.models.container import ContainerType
from app.services.audit_service import log_action  # 🔥 ADD THIS

router = APIRouter(prefix="/driver", tags=["Driver"])


@router.post("/trips")
def create_trip(
    trip_data: TripCreate,
    db: Session = Depends(get_db),
    user=Depends(require_role(["driver"]))
):

    new_trip = Trip(
        client_id=trip_data.client_id,
        driver_id=user.id
    )

    db.add(new_trip)
    db.commit()
    db.refresh(new_trip)

    total_delivered = 0
    total_returned = 0

    for item in trip_data.containers:

        # 🔥 Skip zero entries (important)
        if item.delivered_qty == 0 and item.returned_qty == 0:
            continue

        if item.delivered_qty < 0 or item.returned_qty < 0:
            raise HTTPException(
                status_code=400,
                detail="Quantities cannot be negative"
            )

        total_delivered += item.delivered_qty
        total_returned += item.returned_qty

        trip_container = TripContainer(
            trip_id=new_trip.id,
            container_id=item.container_id,
            delivered_qty=item.delivered_qty,
            returned_qty=item.returned_qty
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
        )
    )

    return {"message": "Trip recorded successfully"}

@router.get("/clients")
def get_clients_for_driver(
    db: Session = Depends(get_db),
    user=Depends(require_role(["driver"]))
):
    return db.query(Client).filter(Client.is_active == True).all()
@router.get("/containers")
def get_containers_for_driver(
    db: Session = Depends(get_db),
    user=Depends(require_role(["driver"]))
):
    return db.query(ContainerType).filter(ContainerType.is_active == True).all()

@router.get("/trips")
def get_driver_trips(
    db: Session = Depends(get_db),
    driver=Depends(require_role(["driver"]))
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

        # Example price logic (you can improve later)
        total_amount = total_delivered * 50  

        enriched.append({
            "id": trip.id,
            "created_at": trip.created_at,
            "client": trip.client,
            "total_delivered": total_delivered,
            "total_returned": total_returned,
            "total_amount": total_amount
        })

    return enriched


@router.get("/orders")
def get_driver_orders(
    db: Session = Depends(get_db),
    driver=Depends(require_role(["driver"]))
):
    orders = (
        db.query(TripContainer)
        .join(Trip)
        .filter(Trip.driver_id == driver.id)
        .all()
    )

    return orders

@router.get("/driver/orders")
def get_driver_orders(
    db: Session = Depends(get_db),
    driver=Depends(require_role(["driver"]))
):
    orders = (
        db.query(TripContainer)
        .join(Trip)
        .filter(Trip.driver_id == driver.id)
        .all()
    )

    return orders

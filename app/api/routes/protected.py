from fastapi import APIRouter, Depends
from app.core.dependencies import require_role

router = APIRouter(prefix="/protected", tags=["Protected"])


@router.get("/admin")
def admin_dashboard(user=Depends(require_role(["admin"]))):
    return {"message": f"Welcome Admin {user.name}"}


@router.get("/manager")
def manager_dashboard(user=Depends(require_role(["manager"]))):
    return {"message": f"Welcome Manager {user.name}"}


@router.get("/driver")
def driver_dashboard(user=Depends(require_role(["driver"]))):
    return {"message": f"Welcome Driver {user.name}"}


@router.get("/client")
def client_dashboard(user=Depends(require_role(["client"]))):
    return {"message": f"Welcome Client {user.name}"}

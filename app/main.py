from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import engine
from app.db.base import Base

# 🔥 Import all route modules once
from app.api.routes import (
    auth,
    protected,
    admin_master,
    driver,
    admin_billing,
    payments,
    analytics,
    client
)

app = FastAPI(title="Water Management System")

# ===============================
# CORS CONFIGURATION
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Use specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# CREATE DATABASE TABLES
# ===============================
Base.metadata.create_all(bind=engine)

# ===============================
# INCLUDE ROUTERS
# ===============================
app.include_router(auth.router)
app.include_router(protected.router)
app.include_router(admin_master.router)
app.include_router(driver.router)
app.include_router(admin_billing.router)   # ✅ Include only once
app.include_router(payments.router)
app.include_router(analytics.router)
app.include_router(client.router)

# ===============================
# ROOT ENDPOINT
# ===============================
@app.get("/")
def root():
    return {"status": "Backend running successfully"}

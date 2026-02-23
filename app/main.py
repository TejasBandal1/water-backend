from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app = FastAPI(title="Riva Rich Operations API")

# ===============================
# CORS CONFIGURATION
# ===============================
origins = [
    "http://localhost:5173",
    "https://water-frontend-beta.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# INCLUDE ROUTERS
# ===============================
app.include_router(auth.router)
app.include_router(protected.router)
app.include_router(admin_master.router)
app.include_router(driver.router)
app.include_router(admin_billing.router)
app.include_router(payments.router)
app.include_router(analytics.router)
app.include_router(client.router)

# ===============================
# ROOT ENDPOINT
# ===============================
@app.get("/")
def root():
    return {"status": "Backend running successfully"}

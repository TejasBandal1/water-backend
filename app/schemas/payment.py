from typing import Literal, Optional

from pydantic import BaseModel


PaymentMethod = Literal["CASH", "UPI", "CASH_UPI"]


class PaymentRecordRequest(BaseModel):
    amount: float
    method: PaymentMethod = "CASH"
    cash_amount: Optional[float] = None
    upi_amount: Optional[float] = None
    upi_account: Optional[str] = None

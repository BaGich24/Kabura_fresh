# schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class OrderCreate(BaseModel):
    user_id: int
    total_amount: float  # This should match your model's 'amount'
    customer_phone: str  # Changed from phone_number to match model
    customer_name: str   # Added to match model requirements
    delivery_address: Optional[str] = None  # Changed from shipping_address
    payment_id: Optional[str] = None
    status: Optional[str] = 'new'
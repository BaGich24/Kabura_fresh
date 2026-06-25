from yookassa import Configuration, Payment, Refund
from datetime import datetime
import uuid
import traceback
from typing import Dict, Optional, Literal, Tuple, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from .shema import OrderCreate
from .database import Order, CartItem, OrderItem, Product, User

PaymentStatus = Literal["pending", "waiting_for_capture", "succeeded", "canceled"]

class PaymentSystem:
    def __init__(self, shop_id: str, secret_key: str):
        """Initialize payment system with credentials"""
        if not shop_id or not secret_key:
            raise RuntimeError("Payment credentials are not configured")

        if not (secret_key.startswith("test_") or secret_key.startswith("live_")):
            raise RuntimeError(
                "YooKassa secret key has wrong format. Use the Secret key from Merchant Profile, "
                "it should start with test_ or live_."
            )

        try:
            Configuration.account_id = shop_id
            Configuration.secret_key = secret_key
        except Exception as e:
            raise RuntimeError("Payment system authorization failed") from e

    async def create_payment(
        self, 
        amount: float, 
        user_id: int,
        description: str = "Order payment",
        return_url: str = "https://t.me/kaburaf_bot"
    ) -> Optional[Dict[str, str]]:
        """Create payment with proper receipt configuration"""
        try:
            idempotence_key = str(uuid.uuid4())
            
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": return_url
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat()
                },
                "receipt": {
                    "customer": {
                        "email": f"user_{user_id}@temp.mail"  # Заглушка для email
                    },
                    "items": [
                        {
                            "description": description[:128],
                            "quantity": "1.00",
                            "amount": {
                                "value": f"{amount:.2f}",
                                "currency": "RUB"
                            },
                            "vat_code": "1",
                            "payment_subject": "service",
                            "payment_mode": "full_payment"
                        }
                    ]
                }
            }
            
            payment = Payment.create(payment_data, idempotence_key)
            
            return {
                "id": payment.id,
                "status": payment.status,
                "confirmation_url": payment.confirmation.confirmation_url,
                "amount": float(payment.amount.value)
            }
        except Exception as e:
            print(f"PaymentSystem.create_payment error: {type(e).__name__}: {e}")
            traceback.print_exc()
            return None

    async def check_payment_status(self, payment_id: str) -> Optional[PaymentStatus]:
        """Check payment status with proper error handling"""
        try:
            payment = Payment.find_one(payment_id)
            return payment.status
        except Exception as e:
            return None
    
    async def verify_payment_success(self, payment_id: str) -> bool:
        """Verify payment completion with error handling"""
        try:
            status = await self.check_payment_status(payment_id)
            return status == "succeeded"
        except Exception as e:
            return False

    async def refund_payment(self, payment_id: str) -> bool:
        """Attempt to refund a payment"""
        try:
            payment = Payment.find_one(payment_id)
            if payment.status == "succeeded":
                refund = Refund.create({
                    "payment_id": payment_id,
                    "amount": payment.amount
                })
                return refund.status == "succeeded"
            return False
        except Exception as e:
            return False

    async def create_order_after_payment(
        self,
        user_id: int,
        state_data: dict,
        session: AsyncSession
    ) -> Tuple[Order, List[CartItem]]:
        """Create order after successful payment with full validation"""
        try:
            async with session.begin():
                # Get and validate cart items
                cart_items = await self._get_and_validate_cart_items(user_id, session)
                
                # Calculate total amount
                total_amount = self._calculate_total_amount(cart_items)
                
                # Create order record
                order = await self._create_order_record(
                    user_id=user_id,
                    total_amount=total_amount,
                    state_data=state_data,
                    session=session
                )
                
                # Create order items
                await self._create_order_items(
                    order_id=order.id,
                    cart_items=cart_items,
                    session=session
                )
                
                # Clear cart only after successful order creation
                await self._clear_user_cart(user_id, session)
                
                return order, cart_items
                
        except Exception as e:
            await self._handle_order_failure(state_data.get('payment_id'))
            raise RuntimeError(f"Order creation failed: {str(e)}") from e

    async def _get_and_validate_cart_items(self, user_id: int, session: AsyncSession) -> List[CartItem]:
        """Get cart items with full validation"""
        # Get cart items with product information
        result = await session.execute(
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .options(selectinload(CartItem.product)))
        cart_items = result.scalars().all()
        
        if not cart_items:
            raise ValueError("Your cart is empty")
        
        # Validate each item
        for item in cart_items:
            # First check if we have a direct price in CartItem
            if item.price is None:
                # If not, try to get it from product
                if item.product is None:
                    raise ValueError(f"Product {item.product_id} not found")
                
                # Use retail_price as the default price
                if hasattr(item.product, 'retail_price') and item.product.retail_price is not None:
                    item.price = item.product.retail_price
                else:
                    raise ValueError(f"Product {item.product_id} has no retail price set")
            
            if item.quantity is None or item.quantity <= 0:
                raise ValueError(f"Invalid quantity for product {item.product_id}")
        
        return cart_items

    def _calculate_total_amount(self, cart_items: List[CartItem]) -> float:
        """Calculate total amount with validation"""
        try:
            return sum(item.price * item.quantity for item in cart_items)
        except TypeError as e:
            raise ValueError("Could not calculate total amount due to invalid cart items") from e
        
    async def _create_order_record(self, user_id: int, total_amount: float, state_data: dict, session: AsyncSession) -> Order:
        """Create the order record in database"""
        try:
            # Validate required fields
            required = {
                'customer_phone': state_data.get('customer_phone'),
                'customer_name': state_data.get('customer_name')
            }
            
            if None in required.values():
                missing = [k for k, v in required.items() if v is None]
                raise ValueError(f"Missing required fields: {', '.join(missing)}")
            
            order_data = {
                "user_id": user_id,
                "amount": total_amount,
                **required,
                "status": "new"
            }
            
            # Optional fields
            if delivery_address := state_data.get('delivery_address'):
                order_data["delivery_address"] = delivery_address
                
            if payment_id := state_data.get('payment_id'):
                order_data["payment_id"] = payment_id
                
            order = Order(**order_data)
            session.add(order)
            await session.flush()
            return order
            
        except Exception as e:
            raise
        
    async def _create_order_items(
        self,
        order_id: int,
        cart_items: List[CartItem],
        session: AsyncSession
    ):
        """Create order items from cart items"""
        for item in cart_items:
            order_item = OrderItem(
                order_id=order_id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else f"Product {item.product_id}",
                quantity=item.quantity,
                price=item.price  # Use the price from CartItem
            )
            session.add(order_item)
            
    async def _clear_user_cart(self, user_id: int, session: AsyncSession):
        """Clear user's cart after successful order creation"""
        await session.execute(
            delete(CartItem).where(CartItem.user_id == user_id))

    async def _handle_order_failure(self, payment_id: Optional[str]):
        """Handle order creation failure including refund attempt"""
        if payment_id:
            refund_success = await self.refund_payment(payment_id)
            if refund_success:
                pass # No logging for refund success
            else:
                pass # No logging for refund failure
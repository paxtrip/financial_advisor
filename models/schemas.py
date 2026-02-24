from pydantic import BaseModel
from typing import Optional


class TransactionItem(BaseModel):
    name: str
    quantity: float = 1.0
    price: float
    total: float
    category: Optional[str] = None
    tags: list[str] = []


class ParsedExpense(BaseModel):
    intent: str  # add_expense, add_income, report, edit, question, unclear
    type: Optional[str] = None  # expense / income
    amount: Optional[float] = None
    currency: str = "RUB"
    category: Optional[str] = None
    store_name: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    items: list[TransactionItem] = []
    tags: list[str] = []
    confidence: float = 0.0
    clarification_needed: Optional[str] = None


class ParsedReceipt(BaseModel):
    store_name: Optional[str] = None
    store_address: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    total: float
    items: list[TransactionItem] = []
    tags: list[str] = []
    payment_method: Optional[str] = None
    warnings: list[str] = []
    error: Optional[str] = None


class ReportRequest(BaseModel):
    intent: str = "report"
    period: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    category_filter: Optional[str] = None
    tag_filter: Optional[str] = None
    report_type: str = "summary"


class EditRequest(BaseModel):
    intent: str = "edit"
    action: str  # "delete", "update"
    target: str = "last"  # "last", "last_n"
    field: Optional[str] = None  # что менять: "amount", "category", "description"
    new_value: Optional[str] = None  # новое значение
    amount_filter: Optional[float] = None  # фильтр по сумме
    clarification_needed: Optional[str] = None

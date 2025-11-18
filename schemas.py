"""
Database Schemas for the Appointment App

Each Pydantic model represents a MongoDB collection (lowercased class name).
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class Service(BaseModel):
    title: str = Field(..., description="Service title")
    description: Optional[str] = Field(None, description="Service description")
    price: Optional[float] = Field(None, ge=0, description="Price in euros")
    duration: Optional[int] = Field(None, ge=0, description="Duration in minutes")

class Request(BaseModel):
    name: str = Field(..., description="Client full name")
    email: EmailStr = Field(..., description="Client email")
    phone: str = Field(..., description="Client phone number")
    service_id: Optional[str] = Field(None, description="Linked service ID")
    message: Optional[str] = Field(None, description="Optional message")
    status: str = Field("Nouveau", description="Status: Nouveau | Confirmé | Annulé")
    created_at: Optional[datetime] = None

class User(BaseModel):
    name: str
    email: EmailStr
    password: str  # stored as hashed

class Business(BaseModel):
    owner_name: str
    métier: str
    localisation: str
    services: List[str]
    horaires: str
    intro_paragraph: Optional[str] = None
    faq: Optional[List[dict]] = None  # {q, a}
    service_descriptions: Optional[List[dict]] = None  # {title, description}
    assistant_responses: Optional[List[str]] = None

import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from bson.objectid import ObjectId
from datetime import datetime, timezone

from database import db, create_document, get_documents
from schemas import Service, Request as RequestSchema, User as UserSchema, Business

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers
class IDModel(BaseModel):
    id: str

def to_public(doc):
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id"))
    # Convert datetimes to iso
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

# Onboarding payload for content generation
class OnboardingPayload(BaseModel):
    nom: str
    metier: str
    localisation: str
    services: List[str]
    horaires: str

# Simple text generators (rule-based placeholders)

def generate_intro(nom, metier, localisation):
    return f"{nom}, {metier} à {localisation}. Prenez rendez-vous facilement : nous répondons vite et organisons tout pour vous. Des prestations de qualité avec un accueil soigné."


def generate_service_descriptions(services: List[str]):
    out = []
    for s in services:
        out.append({
            "title": s,
            "description": f"Prestations {s.lower()} réalisées avec soin. Conseils personnalisés, durée adaptée, et devis transparent."
        })
    return out


def generate_faq(nom, metier, localisation, horaires):
    return [
        {"q": "Quels sont vos horaires ?", "a": f"{horaires}. N'hésitez pas à nous écrire pour un créneau spécifique."},
        {"q": "Où êtes-vous situé ?", "a": f"Nous sommes à {localisation}. L'adresse exacte sera confirmée lors de la prise de rendez-vous."},
        {"q": "Quels services proposez-vous ?", "a": f"{metier} — nous proposons des formules adaptées et des prestations sur mesure."},
        {"q": "Quels sont les tarifs ?", "a": "Nos tarifs sont indiqués pour chaque service et confirmés par email."}
    ]


def generate_assistant_responses(metier):
    return [
        "Bonjour ! Comment puis-je vous aider aujourd'hui ?",
        f"Vous cherchez un {metier}? Je peux vous guider et réserver un créneau.",
        "Pour confirmer une demande, partagez votre nom, email et téléphone.",
    ]

@app.get("/")
def root():
    return {"message": "Backend up"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# --------- Services ---------
@app.post("/api/services", response_model=dict)
def create_service(payload: Service):
    service_id = create_document("service", payload)
    return {"id": service_id}

@app.get("/api/services", response_model=List[dict])
def list_services():
    docs = get_documents("service")
    return [to_public(d) for d in docs]

# --------- Requests (leads) ---------
@app.post("/api/requests", response_model=dict)
def create_request(payload: RequestSchema):
    data = payload.model_dump()
    data["created_at"] = datetime.now(timezone.utc)
    rid = create_document("request", data)
    # Simple email hooks simulated by logs
    try:
        print(f"[EMAIL] Nouvelle demande: {data['name']} - {data.get('email')}")
    except Exception:
        pass
    return {"id": rid}

@app.get("/api/requests", response_model=List[dict])
def list_requests(status: Optional[str] = None):
    filt = {"status": status} if status else {}
    res = [to_public(d) for d in get_documents("request", filt)]
    # sort desc by created_at
    res.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return res

@app.get("/api/requests/{req_id}")
def get_request(req_id: str):
    doc = db["request"].find_one({"_id": ObjectId(req_id)})
    if not doc:
        raise HTTPException(404, "Demande introuvable")
    return to_public(doc)

class StatusUpdate(BaseModel):
    status: str

@app.post("/api/requests/{req_id}/status")
def update_status(req_id: str, payload: StatusUpdate):
    if payload.status not in ["Nouveau", "Confirmé", "Annulé"]:
        raise HTTPException(400, "Statut invalide")
    result = db["request"].update_one({"_id": ObjectId(req_id)}, {"$set": {"status": payload.status, "updated_at": datetime.now(timezone.utc)}})
    if result.matched_count == 0:
        raise HTTPException(404, "Demande introuvable")
    # Log history
    db["request_log"].insert_one({
        "request_id": ObjectId(req_id),
        "status": payload.status,
        "timestamp": datetime.now(timezone.utc)
    })
    if payload.status == "Confirmé":
        try:
            doc = db["request"].find_one({"_id": ObjectId(req_id)})
            print(f"[EMAIL] Confirmation envoyée à {doc.get('email')}")
        except Exception:
            pass
    return {"ok": True}

@app.get("/api/requests/{req_id}/history")
def get_history(req_id: str):
    logs = list(db["request_log"].find({"request_id": ObjectId(req_id)}))
    return [to_public(l) for l in logs]

# --------- Auth (very simple) ---------
class LoginPayload(BaseModel):
    email: EmailStr
    password: str

@app.post("/api/auth/login")
def login(payload: LoginPayload):
    user = db["user"].find_one({"email": payload.email})
    if not user or user.get("password") != payload.password:
        raise HTTPException(401, "Identifiants invalides")
    return {"token": "demo-token", "user": {"name": user.get("name"), "email": user.get("email")}}

# --------- Onboarding & content generation ---------
@app.post("/api/onboarding")
def onboarding(payload: OnboardingPayload):
    # Store business profile and generated content
    intro = generate_intro(payload.nom, payload.metier, payload.localisation)
    service_desc = generate_service_descriptions(payload.services)
    faq = generate_faq(payload.nom, payload.metier, payload.localisation, payload.horaires)
    assistant_res = generate_assistant_responses(payload.metier)

    biz = Business(
        owner_name=payload.nom,
        métier=payload.metier,
        localisation=payload.localisation,
        services=payload.services,
        horaires=payload.horaires,
        intro_paragraph=intro,
        faq=faq,
        service_descriptions=service_desc,
        assistant_responses=assistant_res,
    )
    bid = create_document("business", biz)
    return {"id": bid, "intro": intro, "faq": faq, "services": service_desc, "assistant": assistant_res}

@app.get("/api/content")
def get_content():
    biz = db["business"].find_one(sort=[("_id", -1)])
    if not biz:
        return {"intro": generate_intro("Votre Nom", "Votre métier", "Votre ville"),
                "faq": generate_faq("", "", "", "Lun-Ven 9h-18h"),
                "services": generate_service_descriptions(["Consultation", "Accompagnement", "Séance"])}
    biz = to_public(biz)
    return {
        "intro": biz.get("intro_paragraph"),
        "faq": biz.get("faq", []),
        "services": biz.get("service_descriptions", []),
        "horaires": biz.get("horaires"),
        "localisation": biz.get("localisation"),
        "metier": biz.get("métier"),
        "owner": biz.get("owner_name"),
    }

# --------- Assistant (rule-based) ---------
class ChatMessage(BaseModel):
    message: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    service: Optional[str] = None

@app.post("/api/assistant")
def assistant(msg: ChatMessage):
    content = (get_content())
    text = msg.message.lower()
    reply = None

    # FAQ lookup
    for item in content.get("faq", []):
        if any(k in text for k in ["horaire", "heures", "ouvert"]):
            reply = next((f["a"] for f in content.get("faq", []) if "horaire" in f["q"].lower()), None)
            break
        if any(k in text for k in ["prix", "tarif"]):
            reply = "Nos tarifs varient selon le service. Dites-moi le service souhaité et je vous oriente."
            break
        if any(k in text for k in ["où", "adresse", "localisation", "lieu"]):
            reply = next((f["a"] for f in content.get("faq", []) if "où" in f["q"].lower() or "situ" in f["a"].lower()), None)
            break

    if not reply:
        # service suggestion
        services = [s.get("title") for s in content.get("services", [])]
        if "service" in text or "choisir" in text or "conseil" in text:
            reply = "Voici nos services: " + ", ".join(services) + ". Quel vous intéresse ?"

    if not reply:
        reply = content.get("assistant", ["Je suis là pour vous aider !"])[0]

    # Auto create request if contact provided
    created_id = None
    if msg.name and msg.email and msg.phone:
        req = RequestSchema(name=msg.name, email=msg.email, phone=msg.phone, service_id=None, message=msg.message)
        created_id = create_document("request", req)

    return {"reply": reply, "created_request_id": created_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

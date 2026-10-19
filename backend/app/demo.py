"""Dados FICTÍCIOS apenas para demonstração visual da interface.

Todos os registros são marcados com is_fictitious=True, têm o prefixo "[FICTÍCIO]" no nome,
usam telefones na faixa 0000 e domínios reservados (*.example). Nunca são misturados a
resultados de pesquisas reais e podem ser removidos com `python -m app.demo --remove`.

Uso: python -m app.demo [--email demo@prospecia.local --password demo12345]
"""

from __future__ import annotations

import argparse
import random
from datetime import timedelta

from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import Business, Organization, Role, User, Verification, utcnow
from app.security import hash_password
from app.services.scoring import compute_score
from app.verification.normalize import normalize_name

CITIES = [("Curitiba", "PR", -25.4284, -49.2733), ("Porto Alegre", "RS", -30.0346, -51.2177),
          ("Belo Horizonte", "MG", -19.9167, -43.9345)]
SEGMENTS = ["Consultório odontológico", "Restaurante", "Barbearia", "Pet shop", "Oficina mecânica", "Salão de beleza"]
NAMES = ["Aurora", "Horizonte", "Bem-Estar", "Primavera", "Central", "Vila Nova", "Estrela", "Jardim", "Boa Vista",
         "Recanto", "Sol Nascente", "Pinheiros"]
STATUSES = [
    ("SEM_SITE_IDENTIFICADO", 80, "Nenhum site próprio encontrado após busca por nome e telefone (dado fictício)."),
    ("SITE_NAO_INFORMADO_NO_MAPS", 40, "Cadastro de origem não informa site; busca web não executada (dado fictício)."),
    ("POSSUI_SITE", 90, "Site oficial confirmado por telefone na página (dado fictício)."),
    ("SITE_INDISPONIVEL", 85, "Domínio informado não resolve no DNS (dado fictício)."),
    ("SITE_SUSPEITO", 50, "Domínio com nome semelhante, sem telefone/endereço compatível (dado fictício)."),
    ("VERIFICACAO_PENDENTE", 0, "Aguardando verificação (dado fictício)."),
]


def seed(email: str, password: str, count: int = 36) -> None:
    rnd = random.Random(42)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            org = Organization(name="Organização de demonstração")
            db.add(org)
            db.flush()
            user = User(org_id=org.id, email=email, name="Usuário Demo", password_hash=hash_password(password),
                        role=Role.admin.value)
            db.add(user)
            db.flush()
        db.execute(delete(Business).where(Business.org_id == user.org_id, Business.is_fictitious.is_(True)))
        for i in range(count):
            city, uf, lat, lng = CITIES[i % len(CITIES)]
            seg = SEGMENTS[i % len(SEGMENTS)]
            status, conf, reason = STATUSES[i % len(STATUSES)]
            name = f"[FICTÍCIO] {seg} {NAMES[i % len(NAMES)]} {i + 1}"
            slug = f"demo{i + 1}.example"
            b = Business(
                org_id=user.org_id, name=name, normalized_name=normalize_name(name), category=seg,
                address=f"Rua Exemplo, {100 + i} — endereço fictício", city=city, state=uf, country="Brasil",
                neighborhood="Centro", lat=lat + rnd.uniform(-0.04, 0.04), lng=lng + rnd.uniform(-0.04, 0.04),
                phone=f"+55 41 0000-{i:04d}", phone_normalized=f"55410000{i:04d}",
                maps_url=None, source_website=f"https://{slug}" if status in ("POSSUI_SITE", "SITE_INDISPONIVEL") else None,
                official_website=f"https://{slug}" if status == "POSSUI_SITE" else None,
                official_domain=slug if status in ("POSSUI_SITE", "SITE_INDISPONIVEL") else None,
                candidate_website=f"https://{slug}" if status == "SITE_SUSPEITO" else None,
                rating=round(rnd.uniform(3.5, 5.0), 1), reviews_count=rnd.randint(0, 400),
                business_status="operational", sources=["demo"], digital_status=status, confidence=conf,
                classification_reason=reason, social_only=(i % 5 == 0 and status == "SEM_SITE_IDENTIFICADO"),
                social_links=["https://instagram.com/exemplo.ficticio"] if i % 5 == 0 else None,
                verification_state="done" if status != "VERIFICACAO_PENDENTE" else "pending",
                last_verified_at=utcnow() - timedelta(days=rnd.randint(0, 20)) if status != "VERIFICACAO_PENDENTE" else None,
                is_fictitious=True,
            )
            b.lead_score, b.score_breakdown = compute_score(b, None)
            db.add(b)
            db.flush()
            if status != "VERIFICACAO_PENDENTE":
                db.add(Verification(business_id=b.id, status=status, confidence=conf, reason=reason,
                                    evidence=[{"type": "demo", "source": "Demonstração", "detail": "Evidência fictícia para demonstração da interface.", "polarity": "0", "url": None}],
                                    sources_consulted=["Dados fictícios"]))
        db.commit()
        print(f"{count} empresas FICTÍCIAS criadas para {email} (org {user.org_id}).")


def remove() -> None:
    with SessionLocal() as db:
        n = db.execute(delete(Business).where(Business.is_fictitious.is_(True))).rowcount
        db.commit()
        print(f"{n} registros fictícios removidos.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="demo@prospecia.local")
    ap.add_argument("--password", default="demo12345")
    ap.add_argument("--remove", action="store_true")
    args = ap.parse_args()
    remove() if args.remove else seed(args.email, args.password)

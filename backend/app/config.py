"""Configuração central carregada de variáveis de ambiente.

Nenhuma chave secreta é exposta ao frontend: o navegador só conversa com esta API.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Aplicação ---
    app_env: str = "development"  # development | production | test
    secret_key: str = "change-me-in-production"
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool = False
    allow_registration: bool = True
    log_level: str = "INFO"

    # --- Infra ---
    database_url: str = "postgresql+psycopg://prospec:prospec@localhost:5432/prospecia"
    redis_url: str | None = None
    run_worker_in_api: bool = False  # útil em dev: processa a fila dentro do processo da API
    worker_concurrency: int = 4
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 4
    job_stale_minutes: int = 10

    # --- Fontes de empresas ---
    google_places_api_key: str | None = None
    google_places_language: str = "pt-BR"
    google_places_rps: float = 5.0
    # Termos da Google Maps Platform restringem cache de conteúdo; padrão: sem cache (place_id é armazenado).
    google_places_cache_hours: int = 0
    # Dados vindos do Google ficam com expires_at; o job de retenção remove o payload bruto.
    google_places_retention_days: int = 30

    osm_enabled: bool = True
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    osm_contact_email: str | None = None  # exigido pela política de uso do Nominatim (User-Agent identificável)
    osm_rps: float = 0.5
    osm_cache_hours: int = 24 * 7

    # --- Busca web autorizada (verificação de sites) ---
    brave_search_api_key: str | None = None
    brave_search_rps: float = 1.0
    google_cse_api_key: str | None = None  # Programmable Search: encerra em 01/01/2027 para clientes existentes
    google_cse_cx: str | None = None
    web_search_cache_hours: int = 24
    web_search_results_per_query: int = 10

    # --- Verificação de sites ---
    site_check_timeout_seconds: float = 10.0
    site_check_max_bytes: int = 600_000
    site_check_user_agent: str = "ProspecIA-SiteChecker/1.0 (+verificacao de disponibilidade; respeita robots.txt)"
    enable_domain_guessing: bool = True
    verification_ttl_days: int = 30
    allow_private_network_checks: bool = False  # nunca habilite em produção (proteção SSRF)

    # --- IA (opcional) ---
    ai_provider: str = "none"  # none | anthropic
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5-5"
    ai_effort: str = "low"
    ai_input_price_per_mtok: float = 4.0
    ai_output_price_per_mtok: float = 20.0
    ai_use_server_fallbacks: bool = True

    # --- Custos (USD, editáveis: confira a página de preços de cada provedor) ---
    cost_google_text_search_per_request: float = 0.035  # Text Search Enterprise (site/telefone/avaliação)
    cost_brave_search_per_request: float = 0.005
    cost_google_cse_per_request: float = 0.005
    cost_osm_per_request: float = 0.0

    # --- Limites padrão por usuário ---
    default_monthly_budget_usd: float = 25.0
    default_max_results_per_search: int = 200
    hard_max_results_per_search: int = 2000

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_enabled(self) -> bool:
        return self.ai_provider == "anthropic" and bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()

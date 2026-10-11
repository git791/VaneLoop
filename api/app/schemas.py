from datetime import datetime

from pydantic import BaseModel, Field


class EngineStatus(BaseModel):
    dataset: str
    unit: int
    cycle: int
    state: str = Field(..., description="Nominal, Warning, Critical")
    rul_p10: float | None = None
    rul_p50: float | None = None
    rul_p90: float | None = None
    health_index: float | None = None
    warmup: bool | None = False
    model_version: str | None = None
    updated_at: str | None = None


class FleetCounts(BaseModel):
    nominal: int = 0
    warning: int = 0
    critical: int = 0


class FleetResponse(BaseModel):
    counts: FleetCounts
    engines: list[EngineStatus]


class Reading(BaseModel):
    cycle: int
    op1: float
    op2: float
    op3: float
    s1: float
    s2: float
    s3: float
    s4: float
    s5: float
    s6: float
    s7: float
    s8: float
    s9: float
    s10: float
    s11: float
    s12: float
    s13: float
    s14: float
    s15: float
    s16: float
    s17: float
    s18: float
    s19: float
    s20: float
    s21: float
    rul_true: int | None = None


class ReadingsResponse(BaseModel):
    dataset: str
    unit: int
    readings: list[Reading]
    next_page_token: int | None = None


class SensorTrendPoint(BaseModel):
    cycle: int
    unit: int
    value: float


class SensorTrendResponse(BaseModel):
    dataset: str
    sensor: str
    points: list[SensorTrendPoint]


class MetaData(BaseModel):
    provenance: str
    license: str
    citation: str


class AlertItem(BaseModel):
    unit: int
    cycle: int
    rule: str
    severity: str
    sensor: str | None = None
    message: str


class AlertsResponse(BaseModel):
    dataset: str
    alerts: list[AlertItem]


class PredictionsResponse(BaseModel):
    dataset: str
    unit: int
    predictions: list[EngineStatus]


class BenchmarkResult(BaseModel):
    datetime: datetime
    dataset: str
    engine_count: int
    total_rows: int
    ingest_time_sec: float
    query_time_sec: float
    memory_mb: float
    cpu_load: float

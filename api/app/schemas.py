from typing import List, Optional, Any
from pydantic import BaseModel, Field

class EngineStatus(BaseModel):
    dataset: str
    unit: int
    cycle: int
    state: str = Field(..., description="Nominal, Warning, Critical")
    rul_p10: Optional[float] = None
    rul_p50: Optional[float] = None
    rul_p90: Optional[float] = None
    health_index: Optional[float] = None
    warmup: Optional[bool] = False
    model_version: Optional[str] = None
    updated_at: Optional[str] = None

class FleetCounts(BaseModel):
    nominal: int = 0
    warning: int = 0
    critical: int = 0

class FleetResponse(BaseModel):
    counts: FleetCounts
    engines: List[EngineStatus]

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
    rul_true: Optional[int] = None

class ReadingsResponse(BaseModel):
    dataset: str
    unit: int
    readings: List[Reading]
    next_page_token: Optional[int] = None

class SensorTrendPoint(BaseModel):
    cycle: int
    unit: int
    value: float

class SensorTrendResponse(BaseModel):
    dataset: str
    sensor: str
    points: List[SensorTrendPoint]

class MetaData(BaseModel):
    provenance: str
    license: str
    citation: str

class AlertItem(BaseModel):
    unit: int
    cycle: int
    rule: str
    severity: str
    sensor: Optional[str] = None
    message: str

class AlertsResponse(BaseModel):
    dataset: str
    alerts: List[AlertItem]

class BenchmarkResult(BaseModel):
    datetime: datetime
    dataset: str
    engine_count: int
    total_rows: int
    ingest_time_sec: float
    query_time_sec: float
    memory_mb: float
    cpu_load: float

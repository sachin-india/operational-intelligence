"""SECOM Track B — FastAPI action service.

Run:
    uv run uvicorn demos.secom.track_b.api:app --reload --port 8001

Endpoints:
    GET  /health
    GET  /lots/{lot_id}/risk      — compute yield risk for one lot
    POST /actions/hold-lot        — place lot on hold (requires engineer role)
    GET  /audit                   — recent audit log entries
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from core.governance.db import SessionLocal
from core.governance.permissions import register_actor
from core.ontology.graph import GraphSession
from demos.secom.track_b.actions import HoldLot
from demos.secom.track_b.functions import PredictYieldRisk

app = FastAPI(
    title="SECOM Track B — Operational Context Graph",
    description="Governed actions and yield risk scoring for the SECOM demo.",
    version="0.1.0",
)

_risk_fn = PredictYieldRisk()


class HoldLotRequest(BaseModel):
    lot_id: str
    actor: str
    role: str = "engineer"
    reason: str


class RiskResponse(BaseModel):
    lot_id: str
    risk_score: float
    risk_level: str
    risk_factors: dict[str, Any]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/lots/{lot_id}/risk", response_model=RiskResponse)
def get_lot_risk(lot_id: str) -> RiskResponse:
    with GraphSession.from_env() as g:
        rows = g.run(
            """
            MATCH (lot:Lot {lot_id: $lot_id})
            OPTIONAL MATCH (lot)-[r:TRIGGERED_ALARM]->(:SPCAlarm)
            RETURN lot.n_spc_alarms   AS n_spc_alarms,
                   lot.sensor_na_rate AS sensor_na_rate,
                   max(abs(r.sigma_deviation)) AS max_sigma_dev
            """,
            lot_id=lot_id,
        )
    if not rows or rows[0]["n_spc_alarms"] is None:
        raise HTTPException(status_code=404, detail=f"Lot '{lot_id}' not found")

    row = rows[0]
    result = _risk_fn.compute({
        "n_spc_alarms": row["n_spc_alarms"] or 0,
        "sensor_na_rate": row["sensor_na_rate"] or 0.0,
        "max_sigma_dev": row["max_sigma_dev"] or 0.0,
    })
    return RiskResponse(lot_id=lot_id, **result)


@app.post("/actions/hold-lot")
def hold_lot(req: HoldLotRequest) -> dict:
    register_actor(req.actor, req.role)
    action = HoldLot(lot_id=req.lot_id)
    try:
        from core.actions.base import PreconditionError
        result = action.run(actor=req.actor, reason=req.reason)
        return {"status": "success", "result": result}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except PreconditionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/audit")
def get_audit(limit: int = 20) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT id, action_name, actor, reason, outcome, error, created_at "
                "FROM audit_log ORDER BY id DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()
    return [dict(r._mapping) for r in rows]

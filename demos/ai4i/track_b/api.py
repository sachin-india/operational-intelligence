"""AI4I Track B — FastAPI action service.

Exposes governed actions and risk scoring over HTTP.
Authentication is simulated: actor + role are passed as request fields.

Run:
    uv run uvicorn demos.ai4i.track_b.api:app --reload --port 8000

Endpoints:
    GET  /health
    GET  /runs/{run_id}/risk         — compute failure risk for one run
    POST /actions/trigger-maintenance — schedule maintenance (requires engineer role)
    GET  /audit                       — recent audit log entries
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from core.governance.db import SessionLocal
from core.governance.permissions import register_actor
from core.ontology.graph import GraphSession
from demos.ai4i.track_b.actions import TriggerMaintenance
from demos.ai4i.track_b.functions import PredictFailureRisk

app = FastAPI(
    title="AI4I Track B — Operational Context Graph",
    description="Governed actions and derived context for the AI4I demo.",
    version="0.1.0",
)

_risk_fn = PredictFailureRisk()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class TriggerMaintenanceRequest(BaseModel):
    run_id: str
    actor: str
    role: str = "engineer"
    reason: str


class RiskResponse(BaseModel):
    run_id: str
    risk_score: float
    risk_level: str
    risk_factors: dict[str, Any]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/runs/{run_id}/risk", response_model=RiskResponse)
def get_run_risk(run_id: str) -> RiskResponse:
    with GraphSession.from_env() as g:
        rows = g.run(
            """
            MATCH (r:ToolRun {run_id: $run_id})
            RETURN r.air_temp_k             AS air_temp_k,
                   r.process_temp_k         AS process_temp_k,
                   r.rotational_speed_rpm   AS rotational_speed_rpm,
                   r.torque_nm              AS torque_nm,
                   r.tool_wear_min          AS tool_wear_min,
                   r.machine_id             AS machine_id
            """,
            run_id=run_id,
        )
    if not rows:
        raise HTTPException(status_code=404, detail=f"ToolRun '{run_id}' not found")

    result = _risk_fn.compute(rows[0])
    return RiskResponse(run_id=run_id, **result)


@app.post("/actions/trigger-maintenance")
def trigger_maintenance(req: TriggerMaintenanceRequest) -> dict:
    register_actor(req.actor, req.role)

    action = TriggerMaintenance(run_id=req.run_id)
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

"""Structured, Semantic Security Logging for WebSecSim Campaigns."""
import json
import os
import time
from typing import Any, Dict, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DEFAULT_LOG = os.path.join(LOG_DIR, "security_events.jsonl")

def _path() -> str:
    return os.environ.get("WEBSECSIM_SECURITY_LOG", DEFAULT_LOG)

def log_rich_event(
    actor: str, 
    phase: str, 
    action_desc: str, 
    mitre_t_code: str = "N/A",
    raw_command: str = "",
    detection_hint: str = "",
    mitigation_hint: str = "",
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Logs a fully contextualized event for the Analyst UI Timeline.
    Actors: 'attacker', 'defender', 'system'
    """
    os.makedirs(os.path.dirname(_path()), exist_ok=True)
    
    record = {
        "timestamp": time.time(),
        "actor": actor.lower(),
        "phase": phase.upper(),
        "action": action_desc,
        "mitre_id": mitre_t_code,
        "technical_details": {
            "raw_command": raw_command,
            "metadata": metadata or {}
        },
        "educational": {
            "detection": detection_hint,
            "mitigation": mitigation_hint
        }
    }
    
    with open(_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# Keep the old function for backwards compatibility with your token/login system
def log_security_event(event_type: str, fields: dict = None) -> None:
    log_rich_event(
        actor="system",
        phase="SYSTEM_EVENT",
        action_desc=event_type,
        metadata=fields
    )
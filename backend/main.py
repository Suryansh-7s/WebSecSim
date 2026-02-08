from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
import docker
import time
import os
import sys

# Ensure database is found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import database

app = FastAPI()

# --- CONFIGURATION ---
SECRET_KEY = "super-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
VICTIM_IMAGE = "websecsim-victim:ready"
ATTACKER_IMAGE = "websecsim-attacker"
NETWORK_NAME = "websecsim-net"
VICTIM_NAME = "websecsim-victim"
ATTACKER_NAME = "websecsim-attacker"

client = docker.from_env()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPER FUNCTIONS ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return {"username": username, "role": role}

# --- ENDPOINTS ---

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_data = database.get_user(form_data.username)
    if not user_data:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    db_username, db_hash, db_role = user_data
    if not database.verify_password(form_data.password, db_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": db_username, "role": db_role})
    return {"access_token": access_token, "token_type": "bearer", "role": db_role}

@app.post("/api/system/start")
async def start_system(current_user: dict = Depends(get_current_user)):
    try:
        # Ensure Network
        try:
            client.networks.get(NETWORK_NAME)
        except docker.errors.NotFound:
            client.networks.create(NETWORK_NAME)

        # START VICTIM (Target)
        try:
            victim = client.containers.get(VICTIM_NAME)
            if victim.status != "running":
                victim.start()
                time.sleep(3) # Give it a moment to wake up
            
            # --- THE "NUCLEAR" FIX ---
            print("🔧 Applying Runtime Fixes (VNC + SSH + Password)...")

            # 0. CLEAN VNC LOCK FILES (Crucial for Video)
            victim.exec_run("rm -rf /tmp/.X1-lock /tmp/.X11-unix /var/run/dbus/pid", detach=False)
            victim.exec_run("mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix", detach=False)
            
            # 1. Enable Root Login in SSH Config
            
            victim.exec_run("sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config", detach=False)
            victim.exec_run("sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config", detach=False)
            
            # 2. Force Set Root Password to 'password'
            victim.exec_run("bash -c 'echo root:password | chpasswd'", detach=False)
            
            # 3. Restart SSH to apply changes
            victim.exec_run("service ssh restart", detach=False)
            
            print("✅ Victim fixes applied.")
            # --------------------------------
            
        except docker.errors.NotFound:
            # If container doesn't exist, create it
            client.containers.run(
                VICTIM_IMAGE, name=VICTIM_NAME, detach=True,
                network=NETWORK_NAME, hostname="victim-machine",
                ports={'80/tcp': 6081}, environment=["RESOLUTION=1280x720"]
            )
            time.sleep(5) # Wait for first boot
            
            # Apply same fixes to the new container
            try:
                vm = client.containers.get(VICTIM_NAME)
                vm.exec_run("service ssh start", detach=False)
                vm.exec_run("bash -c 'echo root:password | chpasswd'", detach=False)
            except:
                pass

        # START ATTACKER (Weapon)
        try:
            attacker = client.containers.get(ATTACKER_NAME)
            if attacker.status != "running":
                attacker.start()
        except docker.errors.NotFound:
            print("Spawning GPU-Accelerated Attacker...")
            client.containers.run(
                ATTACKER_IMAGE, name=ATTACKER_NAME, detach=True,
                network=NETWORK_NAME, tty=True,
                device_requests=[
                    docker.types.DeviceRequest(count=-1, capabilities=[['gpu']])
                ]
            )

        return {"status": "started", "url": "http://127.0.0.1:6081", "user": current_user['username']}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
#  CRITICAL: SPECIFIC ROUTES MUST BE DEFINED FIRST!
# =========================================================

@app.post("/api/attack/scan") 
async def run_scan(current_user: dict = Depends(get_current_user)):
    try:
        attacker = client.containers.get(ATTACKER_NAME)
        # Use the full path for nmap as verified
        cmd = "/usr/bin/nmap -F victim-machine"
        result = attacker.exec_run(cmd)
        return {"status": "success", "scan_output": result.output.decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
#  GENERIC ROUTE (CATCH-ALL) GOES SECOND
# =========================================================

@app.post("/api/attack/{t_code}")
async def execute_t_code(t_code: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Permission Denied: Admins Only")
    
    try:
        attacker = client.containers.get(ATTACKER_NAME)
        
        # --- PATH 1: LOCAL ATTACK (Run tool ON Attacker, Target IS Victim) ---
        if t_code.startswith("T1110"):  # Hydra
            # Hydra is installed on Attacker. We run it directly here.
            cmd = "/usr/bin/hydra -l root -P /usr/share/wordlists/rockyou.txt -t 4 ssh://victim-machine -I -s 22 -f"
            
            print(f"🚀 Executing Local Attack: {cmd}")
            result = attacker.exec_run(f"bash -c \"{cmd}\"")
            return {
                "status": "success", 
                "method": "Hardcoded (Hydra)",
                "t_code": t_code,
                "command": cmd,
                "output": result.output.decode()
            }

        # --- PATH 2: REMOTE ATTACK (Run command ON Victim via SSH) ---
        else:
            # 1. Determine the Payload
            if t_code == "T1059": # Persistence
                real_command = "mkdir -p /home/ubuntu/Desktop && touch /root/Desktop/HACKED_BY_ADMIN.txt && touch /home/ubuntu/Desktop/HACKED_BY_ADMIN.txt && chmod 777 /home/ubuntu/Desktop/HACKED_BY_ADMIN.txt"
                method = "Hardcoded (Persistence)"
            
            else: # Dynamic Parser (T1087, etc.)
                fetch_cmd = f"python3 payload_loader.py {t_code}"
                fetch_result = attacker.exec_run(fetch_cmd)
                output_str = fetch_result.output.decode().strip()
                
                if "ERROR" in output_str or fetch_result.exit_code != 0:
                     raise HTTPException(status_code=404, detail=f"Could not load T-Code: {output_str}")
                     
                # Extract command from last line
                real_command = output_str.split('\n')[-1]
                method = "Dynamic YAML Parsing"

            # 2. Wrap it in SSH (Send execution to Victim)
            print(f"🚀 Sending Payload via SSH: {real_command}")
            # Note: Used standard sshpass here as it is usually in path, 
            # but if it fails, use /usr/bin/sshpass like you did in Reset.
            ssh_wrapper = f"sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine '{real_command}'"
            
            result = attacker.exec_run(f"bash -c \"{ssh_wrapper}\"")
            
            return {
                "status": "success", 
                "method": method,
                "t_code": t_code,
                "command": real_command,
                "output": result.output.decode()
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/system/reset")
async def reset_system(current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="Permission Denied: Admins Only")
    try:
        attacker = client.containers.get(ATTACKER_NAME)
        # Using sshpass to clean up
        cmd = "sshpass -p password ssh -o StrictHostKeyChecking=no root@victim-machine 'rm -f /root/Desktop/HACKED_BY_ADMIN.txt /home/ubuntu/Desktop/HACKED_BY_ADMIN.txt'"
        attacker.exec_run(f"bash -c \"{cmd}\"")
        return {"status": "success", "message": "System Reset: Artifacts removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
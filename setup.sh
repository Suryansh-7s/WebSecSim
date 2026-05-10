#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}   WebSecSim Automated Setup for WSL      ${NC}"
echo -e "${GREEN}==========================================${NC}"

echo -e "\n${YELLOW}[1/6] Cleaning up transferred Windows files...${NC}"
rm -rf venv
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null
echo -e "${GREEN}[✓] Cleaned old environments and cache.${NC}"

echo -e "\n${YELLOW}[2/6] Verifying Project Paths...${NC}"
if [ ! -d "backend" ] || [ ! -d "infrastructure/attacker" ] || [ ! -d "infrastructure/victim" ]; then
    echo -e "${RED}[X] ERROR: Missing core folders. Ensure you unzipped the whole project and are running this from inside the WebSecSim directory.${NC}"
    exit 1
fi
echo -e "${GREEN}[✓] Paths verified.${NC}"

echo -e "\n${YELLOW}[3/6] Checking Docker & WSL Integration...${NC}"
if ! docker ps > /dev/null 2>&1; then
    echo -e "${RED}[X] ERROR: Docker is not running or WSL cannot communicate with it.${NC}"
    echo "    -> FIX: Open Docker Desktop on Windows."
    echo "    -> FIX: Go to Settings -> Resources -> WSL Integration."
    echo "    -> FIX: Turn ON the toggle for Ubuntu, then restart this terminal."
    exit 1
fi
echo -e "${GREEN}[✓] Docker is live and connected.${NC}"

echo -e "\n${YELLOW}[4/6] Checking Port Availability...${NC}"
if ss -tuln | grep -q ":8000 " || ss -tuln | grep -q ":6081 "; then
    echo -e "${RED}[X] ERROR: Port 8000 (API) or Port 6081 (VNC) is currently blocked by another application.${NC}"
    echo "    -> FIX: Close other web servers, projects, or apps using these ports before continuing."
    exit 1
fi
echo -e "${GREEN}[✓] Required ports are free.${NC}"

echo -e "\n${YELLOW}[5/6] GPU mode (optional)...${NC}"
echo -e "${GREEN}[✓] Attacker containers start WITHOUT GPU by default (safe for laptops).${NC}"
echo "    -> To enable NVIDIA GPU passthrough: export WEBSECSIM_ENABLE_GPU=1 before starting uvicorn."

echo -e "\n${YELLOW}[6/6] Building Linux Python Environment...${NC}"
if ! command -v python3 &> /dev/null || ! python3 -c "import venv" &> /dev/null; then
    echo -e "${RED}[X] ERROR: Python3/venv is missing. Run: sudo apt update && sudo apt install python3 python3-venv python3-pip -y${NC}"
    exit 1
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
echo -e "${GREEN}[✓] Dependencies installed.${NC}"

echo -e "\n${YELLOW}>>> Compiling Docker Images (This will take a minute) <<<${NC}"
cd infrastructure/attacker && docker build -t websecsim-attacker . && cd ../..
cd infrastructure/victim && docker build -t websecsim-victim:ready . && cd ../..

echo -e "\n${GREEN}==========================================${NC}"
echo -e "${GREEN}   SETUP COMPLETE! YOU ARE READY TO RUN.  ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo -e "To start the presentation, run these exact commands:"
echo -e "${YELLOW}  source venv/bin/activate${NC}"
echo -e "${YELLOW}  cd backend${NC}"
echo -e "${YELLOW}  uvicorn main:app --reload --host 0.0.0.0${NC}"
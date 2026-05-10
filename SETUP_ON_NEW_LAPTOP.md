# WebSecSim Setup on a New Laptop

This guide helps you run the project from scratch on another machine.

## 1) Prerequisites

Install the following first:

- Git
- Docker Engine (and Docker Compose plugin)
- Python 3.10+
- Node.js 18+ and npm

Optional (for GPU support in attacker container):

- NVIDIA drivers
- NVIDIA Container Toolkit

## 2) Clone the repository

```bash
git clone https://github.com/<your-username>/WebSecSim.git
cd WebSecSim
```

## 3) Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The backend should be available at `http://localhost:8000`.

## 4) Frontend setup

In a new terminal:

```bash
cd WebSecSim/frontend
npm install
npm run dev
```

The frontend should be available at `http://localhost:5173`.

## 5) Infrastructure (attacker/victim containers)

From project root, use your existing orchestration flow (backend endpoints/scripts) to build and start the attacker/victim environment.

If you use Docker directly, first verify Docker is running:

```bash
docker ps
docker compose version
```

## 6) Default access

- Dashboard: `http://localhost:5173`
- Default login: `admin` / `admin123` (if unchanged in your code/config)

## 7) Common troubleshooting

- If Docker commands fail with permission denied, add your user to the `docker` group and re-login.
- If frontend cannot reach backend, verify backend is running on port `8000`.
- If VNC/noVNC fails to appear, restart related containers and check backend logs.
- If ports are busy, stop old processes/containers using the same ports.

## 8) Recommended run order

1. Start Docker
2. Start backend
3. Start frontend
4. Start attacker/victim infrastructure
5. Open dashboard and run simulation

# WebSecSim: Automated Adversary Emulation Platform 🛡️

**WebSecSim** is a containerized, service-oriented Cyber Range designed to simulate and visualize cyberattacks in a controlled, isolated environment. Unlike heavy virtual machine labs, WebSecSim utilizes **Docker containers** to create a lightweight "Attacker vs. Victim" architecture orchestrated by Python and visualized via React.

The infrastructure is **GPU-ready**, utilizing the NVIDIA Container Toolkit to support accelerated penetration testing workloads without modifying the control plane.

---

## 🏗️ System Architecture

The project follows a **Containerized Service Architecture** consisting of three layers:



1.  **Control Plane (Frontend):** React + Tailwind CSS dashboard.
2.  **Orchestration Engine (Backend):** Python FastAPI + Docker SDK.
3.  **Range Infrastructure:**
    * **Attacker:** Kali-style container (Hydra, Nmap) with GPU passthrough enabled.
    * **Victim:** Ubuntu Desktop container (VNC, SSH) on an isolated bridge network.

---

## 🚀 Key Features

### 1. MITRE ATT&CK® Mapped Execution
Attacks are not random scripts; they are mapped to specific enterprise techniques to provide educational context:

* **Reconnaissance:** Automated network scanning via **Nmap**.
* **Credential Access (T1110):** SSH Brute Force via **Hydra**.
* **Discovery (T1087):** Post-exploitation user enumeration.
* **Persistence (T1059):** Payload injection (`HACKED_BY_ADMIN.txt`) as an explicit verification step.



### 2. Real-Time Visualization
The dashboard embeds a **noVNC** stream, allowing users to watch the victim's desktop in real-time to verify the impact of attacks (e.g., seeing files appear on the desktop).

### 3. Deterministic Environment
Includes a "Nuclear Fix" routine that runs at boot to:
* Reset SSH configurations (`PermitRootLogin`).
* Clear VNC lock files (`.X1-lock`).
* Ensure a clean, reproducible state for every session.

---

## 🛠️ Technology Stack

| Component | Tech |
| :--- | :--- |
| **Frontend** | React (Vite), Tailwind CSS |
| **Backend** | Python FastAPI, Docker SDK |
| **Infrastructure** | Docker, NVIDIA Container Toolkit |
| **Tools** | Nmap, Hydra, sshpass, noVNC |

---

## ⚡ Quick Start

### Prerequisites
* Docker & Docker Compose installed.
* Node.js & npm installed.
* Python 3.10+ installed.

### Installation

1.  **Clone the Repository**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/WebSecSim.git](https://github.com/YOUR_USERNAME/WebSecSim.git)
    cd WebSecSim
    ```

2.  **Start the Backend**
    ```bash
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    python3 -m uvicorn main:app --reload
    ```

3.  **Start the Frontend**
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

4.  **Access the Dashboard**
    * Open `http://localhost:5173`
    * Login: `admin` / `admin123`

---

## 🔧 Engineering Challenges

This project solves several complex system integration challenges:
* **SSH Permission Denied:** Solved via runtime injection of `sshd_config` settings to force root login in secure containers.
* **VNC Crashes:** Solved via an automated "Lock File Cleaner" script during the boot sequence.
* **FastAPI Route Traps:** Solved by enforcing strict route ordering (Static > Dynamic) to prevent API crashes.

---

## 📜 License
This project is for educational purposes only.
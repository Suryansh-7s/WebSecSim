import { useState } from 'react';
import axios from 'axios';

function App() {
  // --- STATE MANAGEMENT ---
  const [token, setToken] = useState(localStorage.getItem('token')); // Check if already logged in
  const [role, setRole] = useState(localStorage.getItem('role'));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  
  // Dashboard State
  const [vncUrl, setVncUrl] = useState(null);
  const [status, setStatus] = useState("Idle");
  const [logs, setLogs] = useState([]);

  // --- LOGGING HELPER ---
  const addLog = (msg) => setLogs(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev]);

  // --- ACTIONS ---

  // 1. LOGIN FUNCTION
  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      // OAuth2 expects form data, not JSON
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);

      const response = await axios.post('http://localhost:8000/token', formData);
      
      // Save the Key
      const access_token = response.data.access_token;
      const user_role = response.data.role;
      
      localStorage.setItem('token', access_token);
      localStorage.setItem('role', user_role);
      setToken(access_token);
      setRole(user_role);
      
      addLog(`User '${username}' logged in successfully.`);
    } catch (error) {
      alert("Login Failed: Check credentials");
    }
  };

  // 2. LOGOUT FUNCTION
  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    setToken(null);
    setRole(null);
    setVncUrl(null);
  };

  // 3. START LAB (Authenticated)
  const startLab = async () => {
    setStatus("Booting Environment...");
    addLog("Initializing Cyber Range...");
    try {
      const response = await axios.post('http://localhost:8000/api/system/start', {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      // --- THE FIX: ADD VIEWER PARAMETERS HERE ---
      const baseUrl = response.data.url;
      setVncUrl(`${baseUrl}/?path=websockify&resize=scale&autoconnect=true`);
      // -------------------------------------------

      setStatus("System Online");
      addLog("Victim & GPU-Attacker Started.");
    } catch (error) {
      console.error(error);
      setStatus("Error");
      addLog("Failed to start system (Are you authorized?).");
    }
  };

  // 4. LAUNCH T-CODE (Dynamic Engine)
  const launchTCode = async (tCode, description) => {
    addLog(`⚠️ EXECUTING MITRE ATT&CK: ${tCode}...`);
    try {
      const response = await axios.post(`http://localhost:8000/api/attack/${tCode}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      addLog(`✅ ${tCode} [${description}] EXECUTED.`);
      addLog(`Method: ${response.data.method}`); // Shows "Dynamic YAML Parsing" in logs
      
      const output = response.data.output;
      if (output && output.length < 1000) {
        addLog("--- CAPTURED OUTPUT ---");
        output.split('\n').forEach(line => { if(line.trim()) addLog(`> ${line}`); });
        addLog("-----------------------");
      } else {
        addLog("Check VNC for visual confirmation.");
      }
    } catch (error) {
      addLog(`❌ ${tCode} FAILED: ${error.message}`);
    }
  };

  // 5. RESET LAB
  const resetLab = async () => {
    addLog("🔄 Resetting Victim Machine...");
    try {
      await axios.post('http://localhost:8000/api/system/reset', {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      addLog("✅ Cleanup Complete. Victim is ready for new attacks.");
    } catch (error) {
      addLog("❌ Reset Failed: Permission Denied.");
    }
  };

  // 6. RUN NETWORK SCAN (Nmap)
  const runScan = async () => {
    addLog("🔍 Initiating Network Reconnaissance (Nmap)...");
    try {
      const response = await axios.post('http://localhost:8000/api/attack/scan', {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      addLog("--- SCAN RESULTS ---");
      response.data.scan_output.split('\n').forEach(line => {
        if (line.trim()) addLog(line);
      });
      addLog("--- END SCAN ---");
    } catch (error) {
      addLog("❌ Scan Failed.");
    }
  };

  // --- RENDER: LOGIN SCREEN ---
  if (!token) {
    return (
      <div className="h-screen w-screen bg-gray-900 flex items-center justify-center font-mono text-white">
        <div className="bg-gray-800 p-8 rounded shadow-lg border border-gray-700 w-96">
          <h1 className="text-2xl font-bold mb-6 text-center text-red-500">WebSecSim Login</h1>
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm mb-1">Username</label>
              <input 
                type="text" 
                className="w-full p-2 bg-gray-900 border border-gray-600 rounded"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Password</label>
              <input 
                type="password" 
                className="w-full p-2 bg-gray-900 border border-gray-600 rounded"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button type="submit" className="w-full py-2 bg-blue-600 hover:bg-blue-700 rounded font-bold">
              ACCESS CONSOLE
            </button>
          </form>
          <div className="mt-4 text-xs text-gray-500">
            <p>Admin: admin / admin123</p>
            <p>Student: student / student123</p>
          </div>
        </div>
      </div>
    );
  }

  // --- RENDER: DASHBOARD (If Logged In) ---
  return (
    <div className="h-screen w-screen bg-gray-900 text-white flex flex-col font-mono">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-800">
        <h1 className="text-xl font-bold text-red-500">
          WebSecSim <span className="text-white text-sm">| Logged in as: {role}</span>
        </h1>
        <div className="space-x-4 flex items-center">
          <span className="text-sm">Status: <span className={status === "System Online" ? "text-green-400" : "text-yellow-400"}>{status}</span></span>
          <button onClick={handleLogout} className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs">LOGOUT</button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* Left: Controls & Logs */}
        <div className="w-1/4 bg-gray-800 p-4 flex flex-col border-r border-gray-700">
          <div className="space-y-4 mb-6">
            <button onClick={startLab} className="w-full py-2 bg-blue-600 hover:bg-blue-700 rounded font-bold transition text-sm">
              BOOT ENVIRONMENT
            </button>
            
            {status === "System Online" && (
              <>
                {/* RECON BUTTON (For Everyone) */}
                <button 
                  onClick={runScan} 
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 rounded font-bold transition text-sm"
                >
                  🔍 SCAN NETWORK (NMAP)
                </button>

                {/* ATTACK ARSENAL (Admin Only) */}
                {role === 'admin' && (
                  <div className="space-y-3 pt-4 border-t border-gray-700">
                    <p className="text-xs text-red-400 font-bold uppercase tracking-widest">
                      MITRE ATT&CK® Library
                    </p>
                    
                    {/* T1059: Payload */}
                    <button 
                      onClick={() => launchTCode("T1059", "Payload Delivery")} 
                      className="w-full py-2 bg-red-900/50 hover:bg-red-800 border border-red-600 rounded text-xs font-mono text-left px-3 flex justify-between items-center group"
                    >
                      <span>T1059.004</span>
                      <span className="text-gray-400 group-hover:text-white">Payload</span>
                    </button>

                    {/* T1087: Discovery */}
                    <button 
                      onClick={() => launchTCode("T1087.001", "Account Discovery")} 
                      className="w-full py-2 bg-red-900/50 hover:bg-red-800 border border-red-600 rounded text-xs font-mono text-left px-3 flex justify-between items-center group"
                    >
                      <span>T1087.001</span>
                      <span className="text-gray-400 group-hover:text-white">Users &gt;</span>
                    </button>

                    {/* T1110: Brute Force */}
                    <button 
                      onClick={() => launchTCode("T1110", "SSH Brute Force")} 
                      className="w-full py-2 bg-red-900/50 hover:bg-red-800 border border-red-600 rounded text-xs font-mono text-left px-3 flex justify-between items-center group"
                    >
                      <span>T1110.001</span>
                      <span className="text-gray-400 group-hover:text-white">Hydra &gt;</span>
                    </button>

                    {/* RESET BUTTON */}
                    <button 
                      onClick={resetLab} 
                      className="w-full py-2 rounded font-bold text-xs border border-gray-500 hover:bg-gray-700 mt-4"
                    >
                      🔄 RESET VICTIM
                    </button>
                  </div>
                )}
              </>
            )}
          </div>

          <div className="flex-1 bg-black p-2 rounded border border-gray-600 overflow-y-auto text-xs font-mono text-green-400">
            {logs.map((log, i) => <div key={i}>{log}</div>)}
          </div>
        </div>

        {/* Right: The Cyber Range */}
        <div className="flex-1 bg-gray-900 relative">
          {vncUrl ? (
            <iframe 
              src={vncUrl} 
              title="Victim VM"
              allow="fullscreen"
              className="w-full h-full border-none"
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              [ AWAITING TARGET INITIALIZATION ]
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
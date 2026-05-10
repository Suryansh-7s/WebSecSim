import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Terminal, Power, Activity, LogOut, Radar, Skull, ShieldAlert, Cpu, TerminalSquare, FileText, Download, Target, ShieldCheck } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer, YAxis, XAxis, Tooltip, AreaChart, Area } from 'recharts';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import html2canvas from 'html2canvas';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const api = axios.create({ baseURL: API_BASE });

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [role, setRole] = useState(localStorage.getItem('role'));
  const [username, setUsername] = useState(localStorage.getItem('username') || '');
  const [password, setPassword] = useState(localStorage.getItem('password') || '');

  const [vncUrl, setVncUrl] = useState(null);
  const [status, setStatus] = useState('Idle'); 
  const [activeMode, setActiveMode] = useState('RED'); 
  
  const [terminalHistory, setTerminalHistory] = useState([
    { type: 'system', text: 'WebSecSim Integrated Shell v2.0' },
    { type: 'system', text: 'Reverse Shell Active: target=victim-machine' }
  ]);
  const [commandInput, setCommandInput] = useState('');
  const [currentDir, setCurrentDir] = useState('/root');
  const terminalEndRef = useRef(null);

  const [telemetryEvents, setTelemetryEvents] = useState([]);
  const [graphData, setGraphData] = useState([]);
  
  // Ref for capturing the graph for the PDF
  const graphRef = useRef(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [terminalHistory]);

  useEffect(() => {
    if (activeMode !== 'BLUE' || !token) return;
    
    const fetchTelemetry = async () => {
      try {
        const res = await api.get('/api/telemetry/events', { headers: { Authorization: `Bearer ${token}` } });
        setTelemetryEvents(res.data.events);
        
        const bucketed = res.data.events.reduce((acc, ev) => {
          const date = new Date(ev.timestamp * 1000);
          const timeKey = `${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`;
          const existing = acc.find(item => item.time === timeKey);
          if (existing) {
            existing.attacks += (ev.actor === 'attacker' ? 1 : 0);
          } else {
            acc.push({ time: timeKey, attacks: ev.actor === 'attacker' ? 1 : 0 });
          }
          return acc;
        }, []);
        setGraphData(bucketed.reverse()); 
      } catch (e) {
        console.error("Failed to fetch telemetry");
      }
    };

    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 3000); 
    return () => clearInterval(interval);
  }, [activeMode, token]);

  const addLog = (text, type = 'info') => {
    setTerminalHistory(prev => [...prev, { type, text: `[${new Date().toLocaleTimeString()}] ${text}` }]);
  };

  const handleCommandSubmit = async (e) => {
    e.preventDefault();
    const cmd = commandInput.trim();
    if (!cmd) return;

    setTerminalHistory(prev => [...prev, { type: 'input', text: `root@victim:${currentDir}# ${cmd}` }]);
    setCommandInput('');

    if (cmd.toLowerCase() === 'clear') {
      setTerminalHistory([]);
      return;
    }

    if (cmd.startsWith('cd ')) {
      const targetDir = cmd.substring(3).trim();
      const resolveCmd = `cd ${currentDir} && cd ${targetDir} && pwd`;
      try {
        const response = await api.post('/api/system/exec', { command: resolveCmd }, { headers: { Authorization: `Bearer ${token}` } });
        if (response.data.output) setCurrentDir(response.data.output.trim());
        else setTerminalHistory(prev => [...prev, { type: 'error', text: 'Directory not found' }]);
      } catch (err) {
        setTerminalHistory(prev => [...prev, { type: 'error', text: 'Directory resolution failed' }]);
      }
      return;
    }

    const wrappedCommand = `cd ${currentDir} && ${cmd}`;
    try {
      const response = await api.post('/api/system/exec', { command: wrappedCommand }, { headers: { Authorization: `Bearer ${token}` } });
      if (response.data.output) setTerminalHistory(prev => [...prev, { type: 'output', text: response.data.output }]);
      else if (response.data.error) setTerminalHistory(prev => [...prev, { type: 'error', text: response.data.error }]);
    } catch (error) {
      setTerminalHistory(prev => [...prev, { type: 'error', text: `Execution failed: ${error.message}` }]);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);
      localStorage.setItem('username', username);
      localStorage.setItem('password', password);
      const response = await api.post('/token', formData);
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('role', response.data.role);
      setToken(response.data.access_token);
      setRole(response.data.role);
    } catch {
      alert('Authentication failed.');
    }
  };

  const handleLogout = () => {
    localStorage.clear();
    setToken(null);
    setRole(null);
    setVncUrl(null);
    setStatus('Idle');
  };

  const startLab = async () => {
    setStatus('Booting…');
    addLog('Provisioning Data Plane via Docker socket...', 'system');
    try {
      const response = await api.post('/api/system/start', {}, { headers: { Authorization: `Bearer ${token}` } });
      setVncUrl(`${response.data.url}/?path=websockify&resize=scale&autoconnect=true`);
      setStatus('Online');
      addLog('Infrastructure online. noVNC stream bound to UI.', 'success');
    } catch (error) {
      setStatus('Error');
      addLog('Boot sequence failed.', 'error');
    }
  };

  const executeCampaign = async (campaignName) => {
    addLog(`Initiating Campaign: ${campaignName}...`, 'warning');
    try {
      await api.post('/api/campaign/run', { campaign_name: campaignName }, { headers: { Authorization: `Bearer ${token}` } });
      addLog('Campaign orchestrated. Switch to BLUE TEAM view to analyze telemetry.', 'success');
    } catch (error) {
      addLog('Campaign orchestration failed.', 'error');
    }
  };

  // 📄 THE ENTERPRISE PDF GENERATOR 📄
  const generatePDFReport = async () => {
    const doc = new jsPDF('p', 'mm', 'a4');
    const pageWidth = doc.internal.pageSize.getWidth();
    
    // 1. Title & Header
    doc.setFillColor(10, 10, 10);
    doc.rect(0, 0, pageWidth, 40, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(22);
    doc.text("WebSecSim Security Range", 15, 20);
    doc.setFontSize(12);
    doc.setTextColor(16, 185, 129); // Emerald green
    doc.text("EXECUTIVE PENETRATION TEST REPORT", 15, 30);
    
    // 2. Metadata
    doc.setTextColor(50, 50, 50);
    doc.setFontSize(10);
    doc.text(`Generated: ${new Date().toLocaleString()}`, 15, 50);
    doc.text(`Target Environment: victim-machine (172.18.0.2)`, 15, 56);
    doc.text(`Assessing Operator: ${username}`, 15, 62);
    
    // 3. Embed the Graph
    if (graphRef.current) {
      doc.text("Attack Frequency Analysis:", 15, 75);
      const canvas = await html2canvas(graphRef.current, { backgroundColor: '#0a0a0a' });
      const imgData = canvas.toDataURL('image/png');
      doc.addImage(imgData, 'PNG', 15, 80, 180, 60);
    }

    // 4. Incident Timeline Table (AutoTable)
    doc.text("Detailed MITRE ATT&CK Incident Log:", 15, 155);
    
    const tableData = telemetryEvents
      .filter(ev => ev.actor === 'attacker') // Only show actual attacks in the report
      .map(ev => [
        new Date(ev.timestamp * 1000).toLocaleTimeString(),
        ev.phase,
        ev.mitre_id,
        ev.action,
        ev.educational?.mitigation || "N/A"
      ]);

    autoTable(doc, {
      startY: 160,
      head: [['Time', 'Phase', 'MITRE ID', 'Attacker Action', 'Recommended Mitigation']],
      body: tableData,
      theme: 'striped',
      headStyles: { fillColor: [37, 99, 235] }, // Blue Team color
      styles: { fontSize: 8, cellPadding: 3 },
      columnStyles: {
        0: { cellWidth: 20 },
        1: { cellWidth: 25 },
        2: { cellWidth: 20 },
        3: { cellWidth: 60 },
        4: { cellWidth: 60 }
      }
    });

    // 5. Footer
    const pageCount = doc.internal.getNumberOfPages();
    for (let i = 1; i <= pageCount; i++) {
      doc.setPage(i);
      doc.setFontSize(8);
      doc.setTextColor(150);
      doc.text(`WebSecSim Academic Engine - Page ${i} of ${pageCount}`, 15, doc.internal.pageSize.getHeight() - 10);
    }

    // Trigger Download
    doc.save(`WebSecSim_Report_${new Date().getTime()}.pdf`);
  };

  // --- LOGIN SCREEN ---
  if (!token) {
    return (
      <div className="min-h-screen w-full bg-[#09090b] flex items-center justify-center font-sans">
        <div className="w-full max-w-sm rounded-xl border border-white/10 bg-[#121214] p-8 shadow-2xl">
          <div className="flex items-center gap-3 mb-8">
            <ShieldAlert className="w-6 h-6 text-emerald-500" />
            <h1 className="text-xl font-semibold tracking-tight text-zinc-100">WebSecSim Academy</h1>
          </div>
          <form onSubmit={handleLogin} className="space-y-4">
            <input type="text" placeholder="Operator ID" className="w-full rounded border border-white/10 bg-black/50 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-emerald-500 transition-all" value={username} onChange={(e) => setUsername(e.target.value)} required />
            <input type="password" placeholder="Passphrase" className="w-full rounded border border-white/10 bg-black/50 px-3 py-2.5 text-sm text-zinc-100 outline-none focus:border-emerald-500 transition-all" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <button type="submit" className="w-full rounded bg-emerald-600 text-white font-semibold py-2.5 text-sm transition-all hover:bg-emerald-500 active:scale-[0.98]">Authenticate</button>
          </form>
        </div>
      </div>
    );
  }

  // --- MAIN APP UI ---
  return (
    <div className="h-screen w-screen flex flex-col bg-[#050505] text-zinc-100 font-sans overflow-hidden">
      
      <header className="h-14 shrink-0 flex items-center justify-between border-b border-white/10 bg-[#0a0a0a] px-6 shadow-md z-20">
        <div className="flex items-center gap-4">
          <ShieldAlert className="w-5 h-5 text-emerald-500" />
          <span className="text-sm font-semibold tracking-wide text-zinc-100">WebSecSim <span className="text-zinc-600 font-normal">| Cyber Range</span></span>
        </div>
        
        <div className="flex bg-[#111] p-1 rounded-lg border border-white/10">
          <button onClick={() => setActiveMode('RED')} className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-bold transition-all ${activeMode === 'RED' ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'text-zinc-500 hover:text-zinc-300'}`}>
            <Target className="w-3.5 h-3.5" /> RED TEAM (C2)
          </button>
          <button onClick={() => setActiveMode('BLUE')} className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-xs font-bold transition-all ${activeMode === 'BLUE' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'text-zinc-500 hover:text-zinc-300'}`}>
            <ShieldCheck className="w-3.5 h-3.5" /> BLUE TEAM (SIEM)
          </button>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${status === 'Online' ? 'bg-emerald-500 shadow-[0_0_8px_#10b981]' : 'bg-red-500'}`}></span>
            <span className="text-xs font-medium text-zinc-300 uppercase">{status}</span>
          </div>
          <button onClick={handleLogout} className="text-xs font-medium text-zinc-400 hover:text-white transition-colors flex items-center gap-2"><LogOut className="w-3.5 h-3.5"/> Exit</button>
        </div>
      </header>

      {/* 🔴 RED TEAM WORKSPACE 🔴 */}
      {activeMode === 'RED' && (
        <div className="flex flex-1 min-h-0">
          <aside className="w-64 shrink-0 border-r border-white/10 bg-[#0a0a0a] flex flex-col p-4 gap-6 overflow-y-auto">
            <div>
              <h2 className="text-[10px] uppercase tracking-widest text-zinc-500 font-semibold mb-3 flex items-center gap-2"><Cpu className="w-3.5 h-3.5" /> Infrastructure</h2>
              <button onClick={startLab} className="w-full flex items-center justify-between rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400 hover:bg-emerald-500/20 transition-all">Boot Range <Power className="w-4 h-4" /></button>
            </div>
            {role === 'admin' && status === 'Online' && (
              <div>
                <h2 className="text-[10px] uppercase tracking-widest text-red-500 font-semibold mb-3 flex items-center gap-2"><Skull className="w-3.5 h-3.5" /> Automated Campaigns</h2>
                <div className="space-y-2">
                  <button onClick={() => executeCampaign("Web-to-Root Playbook")} className="w-full text-left rounded border border-red-500/30 bg-red-500/10 p-3 transition-all hover:bg-red-500/20 active:scale-[0.98]">
                    <span className="block font-mono text-xs font-bold text-red-400 mb-1">Web-to-Root</span>
                    <span className="block text-[10px] text-zinc-400 leading-tight">Standard external compromise and escalation.</span>
                  </button>
                  <button onClick={() => executeCampaign("Data Exfiltration (Insider Threat)")} className="w-full text-left rounded border border-red-500/30 bg-red-500/10 p-3 transition-all hover:bg-red-500/20 active:scale-[0.98]">
                    <span className="block font-mono text-xs font-bold text-red-400 mb-1">Data Exfiltration</span>
                    <span className="block text-[10px] text-zinc-400 leading-tight">Insider threat collecting and exfiltrating /etc data.</span>
                  </button>
                  <button onClick={() => executeCampaign("Ransomware Deployment")} className="w-full text-left rounded border border-red-500/30 bg-red-500/10 p-3 transition-all hover:bg-red-500/20 active:scale-[0.98]">
                    <span className="block font-mono text-xs font-bold text-red-400 mb-1">Ransomware Sim</span>
                    <span className="block text-[10px] text-zinc-400 leading-tight">Encrypts desktop files and drops a GUI ransom note.</span>
                  </button>
                  <button onClick={() => executeCampaign("Advanced Exfiltration (Email & Shred)")} className="w-full text-left rounded border border-red-500/30 bg-red-500/10 p-3 transition-all hover:bg-red-500/20 active:scale-[0.98]">
                    <span className="block font-mono text-xs font-bold text-red-400 mb-1">Email Exfiltration</span>
                    <span className="block text-[10px] text-zinc-400 leading-tight">Stages files, exfiltrates via SMTP, and forensically shreds evidence.</span>
                  </button>
                </div>
              </div>
            )}
          </aside>

          <main className="flex-1 flex flex-row min-w-0 p-4 gap-4 bg-[#000]">
            <div className="flex-[7] rounded-lg border border-white/10 bg-[#0a0a0a] overflow-hidden flex flex-col shadow-lg">
              <div className="h-7 border-b border-white/10 bg-[#111] flex items-center px-3 gap-2 shrink-0">
                <span className="text-[11px] text-zinc-400 font-mono">TARGET: victim_desktop [172.18.0.2]</span>
              </div>
              <div className="flex-1 relative">
                {vncUrl ? <iframe src={vncUrl} title="Victim Desktop" className="absolute inset-0 w-full h-full border-0 bg-black" /> : <div className="absolute inset-0 flex items-center justify-center text-zinc-600 text-sm font-mono">Stream Offline</div>}
              </div>
            </div>

            <div className="flex-[3] rounded-lg border border-white/10 bg-[#0a0a0a] flex flex-col overflow-hidden shadow-lg min-w-[350px]">
              <div className="h-7 border-b border-white/10 bg-[#111] flex items-center px-3 gap-2 shrink-0">
                <TerminalSquare className="w-3.5 h-3.5 text-zinc-400" />
                <span className="text-[11px] text-zinc-400 font-mono">C2_SHELL // VICTIM_NODE</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 font-mono text-[12px] leading-relaxed bg-[#050505]">
                {terminalHistory.map((line, i) => (
                  <div key={i} className={`whitespace-pre-wrap mb-1 break-words ${line.type === 'input' ? 'text-emerald-400 font-semibold mt-2' : line.type === 'error' ? 'text-red-400' : line.type === 'warning' ? 'text-amber-400' : line.type === 'system' ? 'text-blue-400' : 'text-zinc-300'}`}>
                    {line.text}
                  </div>
                ))}
                <div ref={terminalEndRef} />
              </div>
              <form onSubmit={handleCommandSubmit} className="min-h-[40px] border-t border-white/10 bg-[#0a0a0a] flex items-start px-3 py-2 shrink-0">
                <span className="text-emerald-500 font-mono text-[12px] mr-2 font-bold whitespace-nowrap mt-0.5">root@victim:{currentDir}#</span>
                <input type="text" autoFocus value={commandInput} onChange={(e) => setCommandInput(e.target.value)} className="flex-1 bg-transparent border-none outline-none text-zinc-100 font-mono text-[12px] leading-tight" spellCheck="false" autoComplete="off" />
              </form>
            </div>
          </main>
        </div>
      )}

      {/* 🔵 BLUE TEAM WORKSPACE (SIEM & EDUCATION) 🔵 */}
      {activeMode === 'BLUE' && (
        <div className="flex flex-1 flex-col min-h-0 bg-[#050505] overflow-y-auto p-6 gap-6">
          
          <div className="flex justify-between items-end">
            <div>
              <h1 className="text-2xl font-bold text-zinc-100">Incident Analysis Dashboard</h1>
              <p className="text-sm text-zinc-400 mt-1">Reviewing semantic telemetry and automated campaign logs.</p>
            </div>
            
            {/* 🚨 THE NEW PDF EXPORT BUTTON 🚨 */}
            <button onClick={generatePDFReport} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-md text-sm font-semibold transition-all shadow-[0_0_15px_rgba(37,99,235,0.3)]">
              <Download className="w-4 h-4" /> Export Assessment Report
            </button>
          </div>

          {/* Graph Section (Now with graphRef attached) */}
          <div ref={graphRef} className="h-64 bg-[#0a0a0a] border border-white/10 rounded-xl p-4 shadow-lg">
            <h2 className="text-xs uppercase tracking-widest text-zinc-500 font-bold mb-4 flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400" /> Attack Frequency (Timeline)
            </h2>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={graphData} margin={{ top: 20, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="time" stroke="#52525b" fontSize={12} tickMargin={10} />
                {/* We un-hid the Y-Axis so the graph scales properly! */}
                <YAxis stroke="#52525b" fontSize={12} allowDecimals={false} />
                <Tooltip contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', color: '#fff' }} />
                <Area 
                  type="step" 
                  dataKey="attacks" 
                  stroke="#ef4444" 
                  strokeWidth={3} 
                  fill="#ef4444" 
                  fillOpacity={0.2} 
                  isAnimationActive={false} 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-[#0a0a0a] border border-white/10 rounded-xl p-6 shadow-lg flex-1">
             <h2 className="text-xs uppercase tracking-widest text-zinc-500 font-bold mb-6 flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-400" /> Incident Timeline & Mitigation Strategies
            </h2>
            
            <div className="space-y-4 border-l-2 border-white/10 pl-4 ml-2">
              {telemetryEvents.map((ev, i) => (
                <div key={i} className="relative group">
                  <div className={`absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full ring-4 ring-[#0a0a0a] ${ev.actor === 'attacker' ? 'bg-red-500' : 'bg-blue-500'}`}></div>
                  <div className="bg-[#111] border border-white/5 rounded-lg p-4 transition-all hover:border-white/20">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider mr-2 ${ev.actor === 'attacker' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                          {ev.phase || 'EVENT'}
                        </span>
                        <span className="text-xs text-zinc-500 font-mono">
                          {new Date(ev.timestamp * 1000).toLocaleTimeString()}
                        </span>
                      </div>
                      {ev.mitre_id !== "N/A" && (
                        <span className="text-[10px] font-mono font-bold text-zinc-400 bg-white/5 px-2 py-1 rounded">
                          MITRE: {ev.mitre_id}
                        </span>
                      )}
                    </div>
                    
                    <p className="text-sm text-zinc-200 font-medium mb-3">{ev.action}</p>
                    
                    {ev.technical_details?.raw_command && (
                      <div className="bg-black border border-white/10 rounded p-2 mb-3">
                        <span className="text-[10px] text-zinc-500 font-bold block mb-1">RAW EXECUTION</span>
                        <code className="text-xs text-red-400 font-mono break-all">{ev.technical_details.raw_command}</code>
                      </div>
                    )}

                    {(ev.educational?.detection || ev.educational?.mitigation) && (
                      <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-white/5">
                        {ev.educational.detection && (
                          <div>
                            <span className="text-[10px] uppercase tracking-widest text-blue-400 font-bold flex items-center gap-1 mb-1"><Radar className="w-3 h-3"/> Detection Hint</span>
                            <p className="text-xs text-zinc-400 leading-relaxed">{ev.educational.detection}</p>
                          </div>
                        )}
                        {ev.educational.mitigation && (
                          <div>
                            <span className="text-[10px] uppercase tracking-widest text-emerald-400 font-bold flex items-center gap-1 mb-1"><ShieldCheck className="w-3 h-3"/> Mitigation Strategy</span>
                            <p className="text-xs text-zinc-400 leading-relaxed">{ev.educational.mitigation}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {telemetryEvents.length === 0 && (
                <div className="text-sm text-zinc-500 py-10 text-center">No telemetry data found. Run a campaign in RED TEAM mode.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
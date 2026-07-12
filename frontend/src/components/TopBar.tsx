import { useState, useEffect } from 'react';
import { Activity, DollarSign, Clock, Play, Square, Key, ShieldCheck, Server, RefreshCw } from 'lucide-react';

interface TopBarProps {
  costUsd: number;
  isRunning: boolean;
  onStart: (task: string, mode: string, apiKey?: string, captchaToken?: string, powerMode?: string) => void;
  onStop: () => void;
  startTime: number | null;
}

export const TopBar: React.FC<TopBarProps> = ({ costUsd, isRunning, onStart, onStop, startTime }) => {
  const [task, setTask] = useState('fix the calculator bug in math_lib');
  const [mode, setMode] = useState('demo');
  const [apiKey, setApiKey] = useState('');
  const [isHuman, setIsHuman] = useState(false);
  const [powerMode, setPowerMode] = useState('low');
  const [elapsed, setElapsed] = useState(0);
  const [backendState, setBackendState] = useState<'waking' | 'online'>('waking');

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/runs');
        if (res.ok && mounted) {
          setBackendState('online');
          return true;
        }
      } catch (e) {
        // network error when backend is completely down/waking
      }
      return false;
    };

    const poll = async () => {
      if (await checkHealth()) return;
      if (!mounted) return;
      setTimeout(poll, 3000);
    };
    poll();
    
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let interval: any;
    if (isRunning && startTime) {
      interval = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } else if (!isRunning) {
      if (!startTime) setElapsed(0);
    }
    return () => clearInterval(interval);
  }, [isRunning, startTime]);

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const handleStart = () => {
    let captchaToken = undefined;
    if (mode === 'demo') {
      if (!isHuman) {
        alert("Please complete the CAPTCHA");
        return;
      }
      captchaToken = "valid_mock_token_12345";
    }
    onStart(task, mode, mode === 'byo' ? apiKey : undefined, captchaToken, powerMode);
  };

  return (
    <div className="flex flex-wrap items-center gap-4 p-4 bg-background/80 backdrop-blur-md border-b border-border shadow-sm z-10 sticky top-0">
      <div className="flex flex-1 min-w-[300px] items-center gap-2">
        <input 
          value={task} 
          onChange={e => setTask(e.target.value)}
          placeholder="Enter a task..."
          disabled={isRunning}
          className="flex-1 px-3 py-2 bg-input/50 border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring transition-all disabled:opacity-50"
        />
        
        <select 
          value={mode} 
          onChange={e => setMode(e.target.value)}
          disabled={isRunning}
          className="px-3 py-2 bg-input/50 border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 cursor-pointer"
        >
          <option value="demo">Demo Mode (Fenced)</option>
          <option value="byo">BYO Key Mode</option>
          <option value="replay">Replay Mode (Free)</option>
        </select>

        <button
          onClick={() => setPowerMode(p => p === 'low' ? 'high' : 'low')}
          disabled={isRunning}
          className={`px-3 py-2 border rounded-md text-sm font-medium transition-colors disabled:opacity-50 shadow-sm ${
            powerMode === 'high' 
              ? 'bg-orange-500/20 text-orange-400 border-orange-500/50 hover:bg-orange-500/30' 
              : 'bg-input/50 text-foreground border-border hover:bg-input/70'
          }`}
          title="High power uses the 70B model, Low uses the 8B model"
        >
          {powerMode === 'high' ? '⚡ High Power' : '🔋 Low Power'}
        </button>

        {isRunning ? (
          <button 
            onClick={onStop} 
            className="flex items-center gap-2 px-4 py-2 bg-destructive/80 hover:bg-destructive text-destructive-foreground rounded-md text-sm font-medium transition-colors shadow-sm"
          >
            <Square size={14} /> Stop
          </button>
        ) : (
          <button 
            onClick={handleStart}
            className="flex items-center gap-2 px-4 py-2 bg-primary/90 hover:bg-primary text-primary-foreground rounded-md text-sm font-medium transition-colors shadow-sm"
          >
            <Play size={14} /> Run
          </button>
        )}
      </div>

      <div className="flex items-center gap-4">
        {mode === 'byo' && (
          <div className="flex items-center gap-2">
            <Key size={16} className="text-yellow-500" />
            <input 
              type="password" 
              placeholder="sk-ant-api..." 
              value={apiKey} 
              onChange={e => setApiKey(e.target.value)}
              className="px-3 py-1.5 bg-input/50 border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring w-48 transition-all"
            />
          </div>
        )}
        
        {mode === 'demo' && (
          <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-md border border-white/10">
            <ShieldCheck size={16} className="text-green-400" />
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input 
                type="checkbox" 
                checked={isHuman} 
                onChange={e => setIsHuman(e.target.checked)} 
                className="rounded border-border bg-input/50 focus:ring-ring cursor-pointer" 
              />
              <span className="text-muted-foreground hover:text-foreground transition-colors">I am human (Turnstile)</span>
            </label>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-secondary/50 rounded-full border border-border text-sm">
          <Server size={14} className={backendState === 'online' ? "text-green-400" : "text-muted-foreground"} />
          <span className="text-muted-foreground">Backend:</span>
          {backendState === 'waking' ? (
            <div className="flex items-center gap-1.5 px-2 py-0.5 bg-yellow-500/10 text-yellow-500 rounded-full">
              <RefreshCw size={12} className="animate-spin" />
              <span className="font-medium text-xs">Waking up...</span>
            </div>
          ) : (
            <span className="font-medium text-green-400">Online</span>
          )}
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-secondary/50 rounded-full border border-border text-sm">
          <Activity size={14} className={isRunning ? "text-green-400 animate-pulse" : "text-muted-foreground"} />
          <span className="text-muted-foreground">Status:</span>
          <span className="font-medium">{isRunning ? 'Running' : 'Idle'}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-secondary/50 rounded-full border border-border text-sm">
          <DollarSign size={14} className="text-yellow-500" />
          <span className="text-muted-foreground">Cost:</span>
          <span className="font-medium">${costUsd.toFixed(4)}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-secondary/50 rounded-full border border-border text-sm">
          <Clock size={14} className="text-blue-400" />
          <span className="text-muted-foreground">Time:</span>
          <span className="font-medium tracking-wider tabular-nums">{formatTime(elapsed)}</span>
        </div>
      </div>
    </div>
  );
};

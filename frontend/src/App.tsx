import { useState, useEffect, useRef } from 'react';
import { useAgentStore } from './store';
import { TopBar } from './components/TopBar';
import { GraphPane } from './components/GraphPane';
import { TranscriptPane } from './components/TranscriptPane';
import { Scrubber } from './components/Scrubber';
import { ApprovalModal } from './components/ApprovalModal';
import { AlertCircle, ShieldCheck } from 'lucide-react';

export default function App() {
  const { events, activeNode, costUsd, isRunning, isPaused, startRun, cancelRun, resumeRun, startTime } = useAgentStore();
  const [scrubIndex, setScrubIndex] = useState(-1);

  const prevLengthRef = useRef(0);
  
  // Auto-advance scrubber when new events arrive and we were previously at the end
  useEffect(() => {
    const prevLength = prevLengthRef.current;
    if (scrubIndex === -1 || scrubIndex >= prevLength) {
      setScrubIndex(events.length);
    }
    prevLengthRef.current = events.length;
  }, [events.length, scrubIndex]);

  const visibleEvents = events.slice(0, scrubIndex === -1 ? events.length : scrubIndex);

  // Recalculate active node and cost based on visible events
  let scrubbedActiveNode: string | null = null;
  let scrubbedCost = 0;
  
  for (const ev of visibleEvents) {
    if (ev.raw.type === 'agent_start') scrubbedActiveNode = ev.raw.agent;
    else if (ev.raw.type === 'handoff') scrubbedActiveNode = ev.raw.next;
    else if (ev.raw.type === 'usage') scrubbedCost = ev.raw.cost_usd;
    else if (ev.raw.type === 'done') scrubbedActiveNode = 'done';
  }

  // If we are showing the latest, use real live state for snappiness
  const isLatest = scrubIndex === -1 || scrubIndex >= events.length;
  const displayActiveNode = isLatest ? activeNode : scrubbedActiveNode;
  const displayCost = isLatest ? costUsd : scrubbedCost;

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
        // network error, backend still waking
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

  if (backendState === 'waking') {
    return (
      <div className="flex flex-col h-screen w-screen bg-background items-center justify-center relative overflow-hidden">
        {/* Background glow effects */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/20 rounded-full blur-[100px] pointer-events-none opacity-50" />
        
        <div className="z-10 flex flex-col items-center max-w-md text-center space-y-6 p-8 bg-card/30 backdrop-blur-xl border border-border/50 rounded-2xl shadow-2xl">
          <div className="relative">
            <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
            <div className="relative bg-background p-4 rounded-full border border-primary/30">
              <ShieldCheck size={48} className="text-primary animate-pulse" />
            </div>
          </div>
          
          <div className="space-y-2">
            <h1 className="text-2xl font-bold text-foreground tracking-tight">Waking up AEGIS</h1>
            <p className="text-muted-foreground text-sm leading-relaxed">
              We are spinning up the free-tier cloud environment. This usually takes about <strong className="text-primary/80">30 to 50 seconds</strong>. Please hold on!
            </p>
          </div>

          <div className="flex items-center gap-3 px-4 py-2 bg-secondary/50 rounded-full border border-border">
            <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <span className="text-sm font-medium text-foreground tracking-wide">Connecting to Backend...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-background text-foreground overflow-hidden">
      <div className="bg-yellow-500/10 border-b border-yellow-500/20 text-yellow-200/90 text-sm py-2 px-4 flex items-center justify-center gap-2 shadow-sm z-20 shrink-0">
        <AlertCircle size={16} className="text-yellow-500 shrink-0" />
        <p>
          <strong>Notice:</strong> Demo Mode runs on a shared free-tier API, which may occasionally error due to rate limits. For the full, uninterrupted experience, please use <strong>BYO Key Mode</strong> with your own NVIDIA API key.
        </p>
      </div>
      <TopBar 
        costUsd={displayCost} 
        isRunning={isRunning} 
        onStart={startRun} 
        onStop={cancelRun} 
        startTime={startTime}
      />
      
      <div className="flex flex-1 overflow-hidden">
        <GraphPane activeNode={displayActiveNode} />
        <TranscriptPane events={visibleEvents} />
      </div>

      <Scrubber 
        totalEvents={events.length} 
        scrubIndex={scrubIndex === -1 ? events.length : scrubIndex} 
        onScrub={setScrubIndex} 
      />

      {isPaused && (
        <ApprovalModal onDecision={resumeRun} />
      )}
    </div>
  );
}

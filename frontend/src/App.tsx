import { useState, useEffect, useRef } from 'react';
import { useAgentStore } from './store';
import { TopBar } from './components/TopBar';
import { GraphPane } from './components/GraphPane';
import { TranscriptPane } from './components/TranscriptPane';
import { Scrubber } from './components/Scrubber';
import { ApprovalModal } from './components/ApprovalModal';
import { AlertCircle } from 'lucide-react';

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

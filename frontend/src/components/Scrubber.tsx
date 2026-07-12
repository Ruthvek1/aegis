import React from 'react';
import { History } from 'lucide-react';

interface ScrubberProps {
  totalEvents: number;
  scrubIndex: number;
  onScrub: (index: number) => void;
}

export const Scrubber: React.FC<ScrubberProps> = ({ totalEvents, scrubIndex, onScrub }) => {
  return (
    <div className="flex items-center gap-4 px-6 py-3 bg-background border-t border-border shadow-[0_-4px_20px_rgba(0,0,0,0.2)] z-10">
      <div className="flex items-center gap-2 font-semibold text-blue-400 min-w-[120px]">
        <History size={16} />
        Time Travel
      </div>
      <div className="flex-1 px-4">
        <input 
          type="range" 
          className="w-full h-2 bg-secondary rounded-lg appearance-none cursor-pointer accent-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50" 
          min={0} 
          max={totalEvents} 
          value={scrubIndex} 
          onChange={(e) => onScrub(parseInt(e.target.value, 10))}
        />
      </div>
      <div className="text-xs font-medium text-muted-foreground tabular-nums min-w-[100px] text-right">
        {scrubIndex} / {totalEvents} events
      </div>
    </div>
  );
};

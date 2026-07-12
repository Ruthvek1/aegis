import React, { useState } from 'react';

interface ApprovalModalProps {
  onDecision: (action: string) => void;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({ onDecision }) => {
  const [feedback, setFeedback] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-card border border-border shadow-2xl rounded-xl w-full max-w-md p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-200">
        <div>
          <h2 className="text-lg font-semibold text-blue-400 m-0">Human in the Loop</h2>
          <p className="text-sm text-muted-foreground mt-1">The agent has paused and requires your approval to continue.</p>
        </div>
        
        <textarea 
          placeholder="Optional feedback for the agent..."
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          className="w-full h-24 bg-input/50 border border-border rounded-lg text-foreground p-3 text-sm font-sans resize-none focus:outline-none focus:ring-2 focus:ring-ring transition-all placeholder:text-muted-foreground"
        />

        <div className="flex justify-end gap-3 mt-2">
          <button 
            className="px-4 py-2 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/30 rounded-md text-sm font-medium transition-colors"
            onClick={() => onDecision(`Reject. ${feedback}`)}
          >
            Reject
          </button>
          <button 
            className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md text-sm font-medium transition-colors"
            onClick={() => onDecision(`Approve. ${feedback}`)}
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { X, Wrench, AlertTriangle, Sparkles, Copy, Check } from 'lucide-react';
import type { ParsedEvent } from '../types';

interface TranscriptPaneProps {
  events: ParsedEvent[];
}

const CodeBlock = ({ inline, className, children, ...props }: any) => {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || '');
  const code = String(children).replace(/\n$/, '');

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!inline) {
    const lang = match ? match[1] : 'text';
    return (
      <div className="relative group my-4 rounded-xl overflow-hidden border border-border bg-black/50 shadow-sm">
        <div className="flex items-center justify-between px-4 py-2 bg-secondary/30 border-b border-border text-xs text-muted-foreground font-sans">
          <span className="uppercase tracking-wider">{lang}</span>
          <button 
            onClick={handleCopy}
            className="flex items-center gap-1.5 hover:text-foreground transition-colors p-1 rounded-md hover:bg-secondary/50"
          >
            {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <SyntaxHighlighter
          {...props}
          style={vscDarkPlus}
          language={lang}
          PreTag="div"
          className="!m-0 !bg-transparent text-sm p-4"
        >
          {code}
        </SyntaxHighlighter>
      </div>
    );
  }
  return (
    <code {...props} className={className + " bg-secondary/50 px-1.5 py-0.5 rounded-md text-primary font-mono text-[0.9em]"}>
      {children}
    </code>
  );
};

export const TranscriptPane: React.FC<TranscriptPaneProps> = ({ events }) => {
  const [selectedToolEvent, setSelectedToolEvent] = useState<ParsedEvent | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  return (
    <div className="flex flex-col flex-[0.6] min-w-[400px] h-full bg-background relative">
      <div className="px-4 py-3 border-b border-border bg-card/50 text-sm font-semibold text-muted-foreground uppercase tracking-wider sticky top-0 z-10 backdrop-blur-sm">
        Terminal Stream
      </div>
      
      <div className="flex flex-1 overflow-hidden">
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth">
          {(() => {
            const grouped = [];
            let currentTokens: any = null;
            for (const ev of events) {
              if (ev.raw.type === 'token') {
                if (!currentTokens) {
                  currentTokens = { id: ev.id, type: 'text_block', content: ev.raw.content };
                  grouped.push(currentTokens);
                } else {
                  currentTokens.content += ev.raw.content;
                }
              } else {
                currentTokens = null;
                grouped.push(ev);
              }
            }
            return grouped.map((ev) => {
              if (ev.type === 'text_block') {
                return (
                  <div key={ev.id} className="prose prose-invert prose-sm max-w-none text-foreground/90 font-mono">
                    <ReactMarkdown
                      components={{
                        code: CodeBlock as any
                      }}
                    >
                      {ev.content}
                    </ReactMarkdown>
                  </div>
                );
              }
              if (ev.raw.type === 'agent_start') {
                return (
                  <div key={ev.id} className="text-xs font-semibold text-muted-foreground uppercase tracking-wider py-2">
                    [{ev.raw.agent} Started]
                  </div>
                );
              }
              if (ev.raw.type === 'tool_call') {
                return (
                  <div key={ev.id} className="mb-4">
                    <div className="text-xs font-semibold text-muted-foreground mb-1">System</div>
                    <div 
                      className="bg-secondary/30 border border-secondary p-3 rounded-lg cursor-pointer hover:bg-secondary/50 transition-colors shadow-sm group"
                      onClick={() => setSelectedToolEvent(ev)}
                    >
                      <div className="flex items-center gap-2 text-primary font-medium text-sm">
                        <Wrench size={16} className="text-blue-400 group-hover:rotate-12 transition-transform" />
                        Tool Call: {ev.raw.tool}
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-1.5 opacity-80 group-hover:opacity-100 transition-opacity">
                        Click to inspect arguments
                      </div>
                    </div>
                  </div>
                );
              }
              if (ev.raw.type === 'error') {
                return (
                  <div key={ev.id} className="mb-4">
                    <div className="text-xs font-semibold text-muted-foreground mb-1">System</div>
                    <div className="bg-destructive/10 border border-destructive/30 p-3 rounded-lg shadow-sm">
                      <div className="flex items-center gap-2 text-destructive font-medium text-sm">
                        <AlertTriangle size={16} /> Error
                      </div>
                      <div className="text-sm text-destructive/90 mt-1.5 font-mono">
                        {ev.raw.error}
                      </div>
                    </div>
                  </div>
                );
              }
              if (ev.raw.type === 'final_result') {
                return (
                  <div key={ev.id} className="my-6 p-4 bg-green-500/10 border border-green-500/30 rounded-xl shadow-sm">
                    <div className="flex items-center gap-2 text-green-400 font-bold text-sm mb-3">
                      <Sparkles size={16} /> Final Output
                    </div>
                    <div className="prose prose-invert prose-sm max-w-none text-foreground/90">
                      <ReactMarkdown
                        components={{
                          code: CodeBlock as any
                        }}
                      >
                        {ev.raw.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                );
              }
              return null;
            });
          })()}
        </div>
        
        {selectedToolEvent && (
          <div className="w-[40%] min-w-[300px] border-l border-border bg-card/80 backdrop-blur-md shadow-2xl flex flex-col absolute right-0 top-[45px] bottom-0 z-20 transition-all">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-background/50">
              <span className="font-semibold text-sm">Tool Inspector</span>
              <button 
                onClick={() => setSelectedToolEvent(null)}
                className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-md hover:bg-secondary"
              >
                <X size={16} />
              </button>
            </div>
            <div className="p-4 overflow-y-auto flex-1 font-mono text-sm space-y-4">
              <div>
                <strong className="text-muted-foreground block mb-1">Tool Name:</strong>
                <span className="text-blue-400 font-medium">{(selectedToolEvent.raw as any).tool}</span>
              </div>
              <div>
                <strong className="text-muted-foreground block mb-1">Arguments:</strong>
                <pre className="bg-black/40 p-3 rounded-lg text-xs overflow-x-auto text-green-300 border border-white/5">
                  {JSON.stringify((selectedToolEvent.raw as any).input, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

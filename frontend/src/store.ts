import { create } from 'zustand';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { AgentEvent, ParsedEvent } from './types';

const API_BASE = 'http://127.0.0.1:8000';

interface AgentState {
  events: ParsedEvent[];
  activeNode: string | null;
  costUsd: number;
  isRunning: boolean;
  isPaused: boolean;
  currentRunId: string | null;
  ctrl: AbortController | null;
  startTime: number | null;

  startRun: (task: string, mode?: string, apiKey?: string, captchaToken?: string) => Promise<void>;
  cancelRun: () => Promise<void>;
  resumeRun: (action: string) => Promise<void>;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  events: [],
  activeNode: null,
  costUsd: 0,
  isRunning: false,
  isPaused: false,
  currentRunId: null,
  ctrl: null,
  startTime: null,

  startRun: async (task, mode = 'replay', apiKey, captchaToken) => {
    set({
      events: [],
      costUsd: 0,
      activeNode: null,
      isRunning: true,
      isPaused: false,
      startTime: Date.now(),
    });

    try {
      const payload: any = { task, mode };
      if (apiKey) payload.api_key = apiKey;
      if (captchaToken) payload.captcha_token = captchaToken;

      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || `Server Error ${res.status}`;
        set((state) => ({
          events: [...state.events, {
            id: Math.random().toString(36).substring(7),
            raw: { type: 'error', error: errMsg, agent: 'system' } as any,
            timestamp: Date.now()
          }]
        }));
        throw new Error(errMsg);
      }

      const data = await res.json();
      const runId = data.run_id;
      const ctrl = new AbortController();
      
      set({ currentRunId: runId, ctrl });

      await fetchEventSource(`${API_BASE}/runs/${runId}/stream`, {
        method: 'GET',
        signal: ctrl.signal,
        onmessage(msg) {
          if (!msg.data) return;
          try {
            const ev = JSON.parse(msg.data) as AgentEvent;
            
            set((state) => ({
              events: [...state.events, {
                id: Math.random().toString(36).substring(7),
                raw: ev,
                timestamp: Date.now()
              }]
            }));

            if (ev.type === 'agent_start') {
              set({ activeNode: ev.agent });
            } else if (ev.type === 'handoff') {
              set({ activeNode: ev.next });
            } else if (ev.type === 'usage') {
              set({ costUsd: ev.cost_usd });
            } else if (ev.type === 'done') {
              set({ isRunning: false, activeNode: 'done' });
            } else if (ev.type === 'error') {
              set({ isRunning: false });
              if (ev.error.includes("Interrupt")) {
                set({ isPaused: true });
              }
            }
          } catch (e) {
            console.error('Failed to parse event', e);
          }
        },
        onerror(err) {
          console.error('SSE Error', err);
          set((state) => {
            const lastEv = state.events[state.events.length - 1];
            if (lastEv && lastEv.raw.type === 'done') {
              return state; // Ignore benign disconnect after completion
            }
            return {
              ...state,
              events: [...state.events, {
                id: Math.random().toString(36).substring(7),
                raw: { type: 'error', error: String(err) || "SSE Connection Lost", agent: 'system' } as any,
                timestamp: Date.now()
              }],
              isRunning: false
            };
          });
          throw err;
        }
      });
    } catch (e: any) {
      console.error(e);
      set((state) => ({
        events: [...state.events, {
          id: Math.random().toString(36).substring(7),
          raw: { type: 'error', error: e.message || String(e), agent: 'system' } as any,
          timestamp: Date.now()
        }],
        isRunning: false
      }));
    }
  },

  cancelRun: async () => {
    const { ctrl, currentRunId } = get();
    if (ctrl) ctrl.abort();
    if (currentRunId) {
      await fetch(`${API_BASE}/runs/${currentRunId}/cancel`, { method: 'POST' });
    }
    set({ isRunning: false, isPaused: false });
  },

  resumeRun: async (action) => {
    const { currentRunId } = get();
    if (!currentRunId) return;
    
    set({ isPaused: false, isRunning: true });
    
    await fetch(`${API_BASE}/runs/${currentRunId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });

    const ctrl = new AbortController();
    set({ ctrl });

    fetchEventSource(`${API_BASE}/runs/${currentRunId}/stream`, {
      method: 'GET',
      signal: ctrl.signal,
      onmessage(msg) {
        if (!msg.data) return;
        try {
          const ev = JSON.parse(msg.data) as AgentEvent;
          set((state) => ({
            events: [...state.events, {
              id: Math.random().toString(36).substring(7),
              raw: ev,
              timestamp: Date.now()
            }]
          }));

          if (ev.type === 'agent_start') set({ activeNode: ev.agent });
          else if (ev.type === 'handoff') set({ activeNode: ev.next });
          else if (ev.type === 'usage') set({ costUsd: ev.cost_usd });
          else if (ev.type === 'done') { set({ isRunning: false, activeNode: 'done' }); }
        } catch (e) {}
      }
    });
  }
}));

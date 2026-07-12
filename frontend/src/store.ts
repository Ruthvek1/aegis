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

  startRun: (task: string, mode?: string, apiKey?: string, captchaToken?: string, powerMode?: string) => Promise<void>;
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

  startRun: async (task, mode = 'replay', apiKey, captchaToken, powerMode = 'low') => {
    set({
      events: [],
      costUsd: 0,
      activeNode: null,
      isRunning: true,
      isPaused: false,
      startTime: Date.now(),
    });

    try {
      const payload: any = { task, mode, power_mode: powerMode };
      if (apiKey) payload.api_key = apiKey;
      if (captchaToken) payload.captcha_token = captchaToken;

      const res = await fetch(`${API_BASE}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server Error ${res.status}`);
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
              get().ctrl?.abort();
            } else if (ev.type === 'error') {
              set({ isRunning: false });
              if (ev.error.includes("Interrupt")) {
                set({ isPaused: true });
              }
              get().ctrl?.abort();
            }
          } catch (e) {
            console.error('Failed to parse event', e);
          }
        },
        onerror(err) {
          console.error('SSE Error', err);
          const state = get();
          const lastEv = state.events[state.events.length - 1];
          if (lastEv && lastEv.raw.type === 'done') {
            throw new Error('SILENT_ABORT');
          }
          throw err;
        }
      });
    } catch (e: any) {
      if (e.name === 'AbortError') return; // User aborted
      if (e.message === 'SILENT_ABORT') return; // Benign disconnect
      
      console.error(e);
      let errMsg = e.message || String(e);
      if (errMsg.toLowerCase().includes('failed to fetch') || errMsg.toLowerCase().includes('network error')) {
        errMsg = 'Cannot connect to backend. Is Uvicorn running on port 8000?';
      }
      
      set((state) => {
        const lastEv = state.events[state.events.length - 1];
        if (lastEv && lastEv.raw.type === 'error' && lastEv.raw.error === errMsg) {
          return { isRunning: false };
        }
        return {
          events: [...state.events, {
            id: Math.random().toString(36).substring(7),
            raw: { type: 'error', error: errMsg, agent: 'system' } as any,
            timestamp: Date.now()
          }],
          isRunning: false
        };
      });
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
        } catch (e) {
          console.error('Failed to parse event', e);
        }
      },
      onerror(err) {
          console.error('SSE Error', err);
          set((state) => {
            const lastEv = state.events[state.events.length - 1];
            if (lastEv && lastEv.raw.type === 'done') return state;
            
            let errMsg = err instanceof Error ? err.message : String(err);
            if (errMsg.toLowerCase().includes('failed to fetch') || errMsg.toLowerCase().includes('network error')) {
              errMsg = 'Connection to backend lost.';
            }

            if (lastEv && lastEv.raw.type === 'error' && lastEv.raw.error === errMsg) return state;

            return {
              ...state,
              events: [...state.events, {
                id: Math.random().toString(36).substring(7),
                raw: { type: 'error', error: errMsg, agent: 'system' } as any,
                timestamp: Date.now()
              }],
              isRunning: false
            };
          });
          throw err;
        }
    });
  }
}));

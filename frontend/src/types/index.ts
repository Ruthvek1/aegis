export type AgentEvent =
  | { type: 'agent_start'; agent: string }
  | { type: 'agent_end'; agent: string }
  | { type: 'token'; content: string }
  | { type: 'tool_call'; tool: string; input: any }
  | { type: 'tool_result'; tool: string; output: any }
  | { type: 'handoff'; next: string }
  | { type: 'usage'; cost_usd: number }
  | { type: 'error'; error: string }
  | { type: 'final_result'; content: string }
  | { type: 'done' };

export interface ParsedEvent {
  id: string;
  raw: AgentEvent;
  timestamp: number;
}

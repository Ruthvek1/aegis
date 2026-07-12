import React, { useMemo } from 'react';
import { ReactFlow, Background, Controls } from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface GraphPaneProps {
  activeNode: string | null;
}

const initialNodes: Node[] = [
  { id: 'supervisor', position: { x: 250, y: 50 }, data: { label: 'Supervisor' } },
  { id: 'planner', position: { x: 50, y: 150 }, data: { label: 'Planner' } },
  { id: 'researcher', position: { x: 250, y: 150 }, data: { label: 'Researcher' } },
  { id: 'coder', position: { x: 450, y: 150 }, data: { label: 'Coder' } },
  { id: 'critic', position: { x: 450, y: 250 }, data: { label: 'Critic' } },
  { id: 'synthesizer', position: { x: 250, y: 350 }, data: { label: 'Synthesizer' } },
];

const initialEdges: Edge[] = [
  { id: 'e-sup-plan', source: 'supervisor', target: 'planner', animated: true },
  { id: 'e-sup-res', source: 'supervisor', target: 'researcher', animated: true },
  { id: 'e-sup-code', source: 'supervisor', target: 'coder', animated: true },
  { id: 'e-code-crit', source: 'coder', target: 'critic', animated: true },
  { id: 'e-crit-code', source: 'critic', target: 'coder', animated: true, style: { stroke: '#ef4444' } }, // Veto edge
  { id: 'e-sup-synth', source: 'supervisor', target: 'synthesizer', animated: true },
];

export const GraphPane: React.FC<GraphPaneProps> = ({ activeNode }) => {
  const nodes = useMemo(() => {
    return initialNodes.map(node => {
      const isActive = activeNode === node.id || (activeNode === 'done' && node.id === 'synthesizer');
      
      let color = '#888';
      if (node.id === 'supervisor') color = '#a855f7'; // purple
      if (node.id === 'planner') color = '#3b82f6'; // blue
      if (node.id === 'coder') color = '#eab308'; // yellow
      if (node.id === 'critic') color = '#ef4444'; // red
      if (node.id === 'researcher') color = '#06b6d4'; // cyan
      if (node.id === 'synthesizer') color = '#22c55e'; // green

      return {
        ...node,
        style: {
          background: 'hsl(var(--card))',
          color: 'hsl(var(--card-foreground))',
          border: isActive ? `2px solid ${color}` : '1px solid hsl(var(--border))',
          boxShadow: isActive ? `0 0 20px ${color}` : 'none',
          borderRadius: '8px',
          padding: '12px',
          fontWeight: 600,
          opacity: (activeNode && !isActive) ? 0.6 : 1,
        }
      };
    });
  }, [activeNode]);

  return (
    <div className="flex-[0.4] min-w-[300px] border-r border-border bg-card/50">
      <ReactFlow nodes={nodes} edges={initialEdges} fitView attributionPosition="bottom-right">
        <Background color="hsl(var(--muted-foreground))" gap={16} />
        <Controls className="bg-card border-border fill-foreground" />
      </ReactFlow>
    </div>
  );
};

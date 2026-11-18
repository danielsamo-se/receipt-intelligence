import type { ComponentType } from 'react'
import { Ban, Check, CircleHelp, Layers3, PencilLine } from 'lucide-react'
import type { Decision, Outcome } from './types'

export type StatusDecision = Pick<Decision, 'outcome' | 'specificity' | 'node_label' | 'availability'>
type Props = { decision: StatusDecision }

const Leaf = () => <span className="status status-leaf"><Check size={14} aria-hidden="true" />Specific category</span>
const Parent = () => <span className="status status-parent"><Layers3 size={14} aria-hidden="true" />Parent only</span>
const Unresolved = ({ decision }: Props) => <span className="status status-unresolved"><CircleHelp size={14} aria-hidden="true" />{decision.availability === 'complete' ? 'Needs review' : 'Cache unavailable'}</span>
const Outside = () => <span className="status status-scope"><Ban size={14} aria-hidden="true" />Outside scope</span>
const Corrected = () => <span className="status status-override"><PencilLine size={14} aria-hidden="true" />Merchant-corrected</span>

// Schema-driven adaptive UI. Models never create or execute frontend code.
export const decisionRegistry: Record<Outcome, ComponentType<Props>> = {
  leaf: Leaf, parent_only: Parent, unidentifiable: Unresolved, out_of_scope: Outside, override: Corrected,
}
export function DecisionStatus({ decision }: Props) {
  const Component = decisionRegistry[decision.outcome]
  return <Component decision={decision} />
}

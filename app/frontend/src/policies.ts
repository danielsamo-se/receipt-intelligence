import type { Policy } from './types'

export const policyLabel: Record<Policy,string> = {
  ONE_SHOT:'One-shot Hierarchical', TWO_STAGE:'Two-stage Hierarchical',
  FORCED:'Naive Forced Baseline', SAFE:'Historical SAFE · 0.85 heuristic',
}

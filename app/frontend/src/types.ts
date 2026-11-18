export type Policy = 'FORCED' | 'SAFE'
export type Outcome = 'leaf' | 'parent_only' | 'unidentifiable' | 'out_of_scope' | 'override'
export type Scope = 'pilot' | 'holdout' | 'all'
export interface TaxonomyNode {
  id: string; label: string; parent_id: string | null; level: 'leaf' | 'parent';
  kind: 'merchandise' | 'receipt_adjustment'; description: string
}
export interface Assessment {
  stage: string; available: boolean; choice?: string; probabilities?: Record<string, number>;
  confidence?: number | null; model?: string; cache_file?: string; cache_sha256?: string;
  error?: string; reason?: string; response?: unknown; latency_seconds?: number; usage?: unknown
}
export interface Correction {
  event_id: number; node_id: string; note: string; created_at: string; policy: Policy;
  scope: string; independent_ground_truth: false
}
export interface Decision {
  line_id: string; merchant_id: string; raw_text: string; price_cents: number; merchant_type: string;
  dataset: string; policy: Policy; node_id: string | null; node_label: string | null;
  parent_id: string | null; specificity: 'leaf' | 'parent' | 'none'; outcome: Outcome;
  availability: 'complete' | 'partial' | 'unavailable'; review_required: boolean;
  assessments: Assessment[]; scores: Record<string, number>;
  applied_rules: { code: string; explanation: string }[]; provenance: Record<string, unknown>;
  correction: Correction | null; underlying_model: Decision | null
  product_memory: ProductMemory | null
}
export interface LineSummary extends Omit<Decision, 'assessments' | 'underlying_model' | 'applied_rules' | 'provenance'> {
  quantity: number; value_cents: number; record_type: string; reason: string
}
export interface Totals {
  sales_value_cents: number; leaf_value_cents: number; parent_value_cents: number;
  unresolved_value_cents: number; adjustment_value_cents: number; net_receipt_value_cents: number
}
export interface Category {
  id: string; label: string; leaf_value_cents: number; parent_value_cents: number; corrected_value_cents: number
}
export interface Report {
  merchant_id: string; policy: Policy; dataset: Scope; revision: number; notice: string; period_label: string;
  mode: 'weekly' | 'replay'; totals: Totals; unresolved_breakdown: Record<string, number>;
  categories: Category[]; review_queue: LineSummary[]; lines: LineSummary[]; line_count: number;
  correction_count: number; safe_threshold: number;
  comparison: { other_policy: Policy; totals: Totals; changed_line_count: number }
  replay: ReplaySession | null
}
export interface ReplaySession {
  id: string; merchant_id: string; policy: Policy; status: 'running' | 'complete' | 'interrupted' | 'stopped';
  generation: number; line_ids: string[]; processed_count: number; total_count: number; sequence: string[]
}
export interface Bootstrap {
  merchant_id: string; merchant_name: string; notice: string; period_label: string; taxonomy_version: string;
  nodes: TaxonomyNode[]; line_count: number; scopes: { value: Scope; label: string }[]
}
export interface AuditEvent {
  id: number; action: 'set' | 'undo'; node_id: string | null; created_at: string; note: string;
  original_classification: { node_id?: string; outcome?: string }; original_model_decision: Decision
}
export interface InspectorData {
  decision: Decision; sales_assumption: { weekly_quantity: number; record_type: string }; audit: AuditEvent[];
  included_in_weekly_analytics: boolean
}

export interface MemoryProduct {
  product_id: string; name: string; node_id: string; attributes: Record<string,string>;
  source: { kind: string; notice?: string }; created_at: string
}
export interface MemoryCandidate {
  product: MemoryProduct; lexical_score: number; semantic_cosine: number | null;
  ranking_score: number; eligible_for_confirmation: boolean; blocked_reasons: string[]; rejected: boolean
}
export interface MemoryEvent {
  id: number; action: 'confirm' | 'reject' | 'reverse'; product_id: string;
  created_at: string; reversible: boolean; note: string; evidence: unknown
}
export interface ProductMemory {
  status: 'known_mapping' | 'suggested' | 'no_mapping' | 'line_override_precedence';
  namespace: string; normalized_alias: string; identifier: string | null;
  match: { product: MemoryProduct; method: string; alias_provenance: {event_id: number | null; created_at: string; source: {kind: string}} | null } | null;
  candidates: MemoryCandidate[]; blocked_reasons: string[]; model_stage_bypassed: boolean;
  embedding: { model?: string; revision?: string; available: boolean; error: string | null; network_access?: boolean };
  retrieval_mode: string; audit: MemoryEvent[]
}
export interface EvaluationMetric {
  method?: string; threshold?: number | null; correct_leaf: number; correct_parent: number;
  incorrect_category: number; overclaim: number; abstention: number; taxonomy_coverage: number;
  classification_accuracy: number; incorrect_scope_rejection: number; correct_scope_rejection: number;
  median_receipt_latency_seconds?: number;
  usage?: { cost: { available_sum: number }; requests: number }
}
export interface EvaluationData {
  notice: string; pilot: EvaluationMetric[];
  followup: Record<string, { dataset_size: number; methods: Record<string, EvaluationMetric> }>;
  forced_examples: { id: string; raw_text: string; ground_truth: string; prediction: string; score: number; outcome: string }[];
  sources: string[]; limitations: string[]
}

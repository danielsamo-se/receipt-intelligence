import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Database, FileText, LoaderCircle, PencilLine, Undo2, X } from 'lucide-react'
import { api, money, percent, stamp } from './api'
import { DecisionStatus } from './decisionRegistry'
import { ProductMemory } from './ProductMemory'
import type { Assessment, InspectorData, Policy, TaxonomyNode } from './types'

interface Props { lineId: string; merchantId: string; policy: Policy; nodes: TaxonomyNode[]; onClose: () => void; onChanged: () => Promise<void> }

export function Inspector({ lineId, merchantId, policy, nodes, onClose, onChanged }: Props) {
  const [data, setData] = useState<InspectorData | null>(null)
  const [selected, setSelected] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(busy)
  busyRef.current = busy
  const drawer = useRef<HTMLElement>(null)
  const endpoint = `/api/merchants/${merchantId}/lines/${encodeURIComponent(lineId)}`
  const names = Object.fromEntries(nodes.map(n => [n.id, n.label]))
  const specialNames: Record<string, string> = { unidentifiable: 'Unidentifiable', unspecified_child: 'No specific child', out_of_scope: 'Outside supported taxonomy' }
  const label = (key: string) => names[key] || specialNames[key] || key

  useEffect(() => {
    const controller = new AbortController()
    setData(null); setError(''); setMessage(''); setNote('')
    api<InspectorData>(`${endpoint}?policy=${policy}`, { signal: controller.signal }).then(value => { setData(value); setSelected(value.decision.node_id || '') }).catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [endpoint, policy])

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    drawer.current?.querySelector<HTMLButtonElement>('button')?.focus()
    const handle = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busyRef.current) onClose()
      if (event.key !== 'Tab') return
      const controls = drawer.current?.querySelectorAll<HTMLElement>('button:not(:disabled), select, input, textarea, summary, [href]')
      if (!controls?.length) return
      const first = controls[0], last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handle)
    return () => { document.removeEventListener('keydown', handle); document.body.style.overflow = oldOverflow; previous?.focus() }
  }, [onClose])

  async function mutate(action: 'corrections' | 'undo') {
    if (action === 'corrections' && !selected) return
    setBusy(true); setError(''); setMessage('')
    try {
      const value = await api<InspectorData>(`${endpoint}/${action}`, { method: 'POST', body: JSON.stringify(action === 'undo' ? { policy } : { node_id: selected, policy, note }) })
      setData(value); setSelected(value.decision.node_id || ''); setNote('')
      await onChanged()
      setMessage(action === 'undo' ? 'Correction undone. Report updated.' : 'Correction saved. Report updated.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save the correction.') }
    finally { setBusy(false) }
  }

  async function memoryAction(path: string, body: Record<string,unknown>, success: string) {
    setBusy(true); setError(''); setMessage('')
    try {
      const value=await api<InspectorData>(`${endpoint}/${path}`,{method:'POST',body:JSON.stringify({...body,policy})})
      setData(value);setSelected(value.decision.node_id || '')
      await onChanged()
      setMessage(success)
    }catch(e){setError(e instanceof Error?e.message:'Product memory review failed.')}
    finally{setBusy(false)}
  }

  const decision = data?.decision
  const original = decision?.underlying_model || decision
  const parents = nodes.filter(n => n.level === 'parent' && n.kind === (data?.sales_assumption.record_type === 'sale' ? 'merchandise' : 'receipt_adjustment'))

  function AssessmentCard({ evidence }: { evidence: Assessment }) {
    if (!evidence.available) return <div className="assessment unavailable"><strong>Assessment unavailable</strong><p>{evidence.error}</p></div>
    const probability = evidence.choice ? evidence.probabilities?.[evidence.choice] : undefined
    return <div className="assessment">
      <div className="assessment-top"><span className="eyebrow">{evidence.stage === 'flat' ? 'FLAT question' : `${evidence.stage} question`}</span><span className="probability">{probability === undefined ? 'Not returned' : percent(probability)}</span></div>
      <strong>{label(evidence.choice || '')}</strong>
      <span className="muted small">Returned confidence: {evidence.confidence == null ? 'not returned' : percent(evidence.confidence)}</span>
      <details className="distribution"><summary>All {Object.keys(evidence.probabilities || {}).length} option probabilities</summary><div className="distribution-table">
        {Object.entries(evidence.probabilities || {}).sort((a,b) => b[1]-a[1]).map(([key,value]) => <div key={key}><span>{label(key)}</span><strong>{percent(value)}</strong></div>)}
      </div></details>
      <details className="technical"><summary>Cached response & provenance</summary><p>{evidence.model}</p><code>{evidence.cache_file}</code><p className="small">SHA-256: {evidence.cache_sha256}</p><pre>{JSON.stringify(evidence.response, null, 2)}</pre></details>
    </div>
  }

  return <div className="drawer-backdrop" onMouseDown={e => { if (e.target === e.currentTarget && !busy) onClose() }}>
    <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="inspector-title" ref={drawer}>
      <header className="drawer-header"><div><span className="eyebrow">Decision inspector</span><h2 id="inspector-title">{decision?.raw_text || 'Receipt decision'}</h2></div><button className="icon-button" aria-label="Close decision inspector" onClick={onClose} disabled={busy}><X size={20}/></button></header>
      <div className="drawer-body">
        {!data && !error && <div className="loading"><LoaderCircle className="spin" size={22}/>Loading the cached decision…</div>}
        {error && <div className="error" role="alert">{error}</div>}
        {data && decision && original && <>
          <div className="pipeline-intro">Receipt input → Product memory → Jev if needed → Final outcome</div>
          <section className="pipeline-step"><div className="step-label"><FileText size={17}/><h3>Receipt input</h3></div>
            <div className="receipt-input"><span className="receipt-raw">{decision.raw_text}</span><div><span>{money(decision.price_cents)} per printed line</span><span>{decision.merchant_type}</span></div></div>
            <p className="muted small">{lineId} · {data.included_in_weekly_analytics ? `${data.sales_assumption.weekly_quantity} modeled weekly occurrences. Quantities are synthetic assumptions.` : 'Synthetic one-off input. Excluded from the frozen weekly analytics.'}</p>
          </section>
          {decision.product_memory && <ProductMemory key={lineId} memory={decision.product_memory} busy={busy} names={names} expanded={!data.included_in_weekly_analytics}
            onReview={(productId,action,checked)=>memoryAction('memory-review',{product_id:productId,action,identity_checked:checked},action==='confirm'?'Alias confirmed. Future exact matches reuse Product Memory.':'Suggestion rejected. No classification was propagated.')}
            onReverse={eventId=>memoryAction(`memory-reviews/${eventId}/reverse`,{},'Product memory review reversed. The alias is no longer trusted by that review.')}/>}
          <section className="pipeline-step"><div className="step-label"><Database size={17}/><h3>Jev assessment</h3><span className="tag">{decision.product_memory?.model_stage_bypassed?'Bypassed':'Cached results only'}</span></div>
            <p className="muted small">{decision.product_memory?.model_stage_bypassed?'Product memory supplied the classification. Any cache below is an inspection-only comparison, not part of this decision.':'These are returned choices and scores, not a generated explanation of the model’s reasoning.'}</p>
            {(decision.assessments.length>0?decision.assessments:original.assessments).map(e => <AssessmentCard key={e.stage} evidence={e}/>)}
            {decision.assessments.length===0&&original.assessments.length===0&&<p className="muted small">No Jev response exists for this input. No API call was made.</p>}
          </section>
          <section className="pipeline-step"><div className="step-label"><ChevronDown size={17}/><h3>Classification policy</h3><span className={`tag ${policy === 'FORCED' ? 'tag-warning' : ''}`}>{policy}</span></div>
            <ul className="rules">{(decision.product_memory?.model_stage_bypassed?decision:original).applied_rules.filter(r => r.code !== 'CACHE_ONLY').map(r => <li key={r.code}>{r.explanation}</li>)}</ul>
          </section>
          <section className="pipeline-step final-step"><div className="step-label"><Check size={17}/><h3>Final outcome</h3></div><DecisionStatus decision={decision}/>
            <h3 className="final-category">{decision.node_label || (decision.outcome === 'out_of_scope' ? 'Outside supported categories' : 'No category assigned')}</h3>
            {decision.node_id && <p className="muted small">{decision.specificity === 'parent' ? 'Parent-level information only. No specific child is asserted.' : 'Specific category assignment; not an independently verified product identity.'}</p>}
            {decision.correction && <div className="correction-note"><PencilLine size={16}/><div>Merchant correction · {stamp(decision.correction.created_at)}<p>{decision.correction.note || 'Applies to this merchant and exact receipt line only.'}</p><span className="small">Operational feedback, not independent evaluation ground truth.</span></div></div>}
            <details className="audit"><summary>Audit trail ({data.audit.length})</summary>{data.audit.length === 0 ? <p className="muted small">No merchant corrections yet.</p> : data.audit.map(event => <div className="audit-entry" key={event.id}><strong>{event.action === 'set' ? `Set ${label(event.node_id || '')}` : event.node_id ? `Undo · restored ${label(event.node_id)}` : 'Undo · returned to cached policy'}</strong><span>{stamp(event.created_at)}</span>{event.note && <p>{event.note}</p>}<span className="small">Previously: {label(event.original_classification.node_id || event.original_classification.outcome || 'unresolved')}</span></div>)}</details>
          </section>
        </>}
      </div>
      {data && <form className="correction-form" onSubmit={e => { e.preventDefault(); void mutate('corrections') }}>
        <div className="form-heading"><PencilLine size={16}/><strong>Review & correct</strong><span className="small muted">Exact line · this merchant</span></div>
        <label htmlFor="correction-category" className="sr-only">Corrected category</label>
        <select id="correction-category" value={selected} onChange={e => setSelected(e.target.value)} disabled={busy} required>
          <option value="">Choose a category…</option>
          {parents.map(parent => <optgroup key={parent.id} label={parent.label}><option value={parent.id}>{parent.label} (parent only)</option>{nodes.filter(n => n.parent_id === parent.id).map(n => <option key={n.id} value={n.id}>{n.label}</option>)}</optgroup>)}
        </select>
        <details className="correction-extra"><summary>Add a correction note</summary><textarea aria-label="Correction note" value={note} onChange={e => setNote(e.target.value)} placeholder="What did you check? (optional)" maxLength={500} rows={2}/></details>
        <div className="form-actions"><button className="primary-button" type="submit" disabled={!selected || busy}>{busy ? <LoaderCircle className="spin" size={16}/> : <Check size={16}/>}Apply correction</button>{decision?.correction && <button className="secondary-button" type="button" onClick={() => void mutate('undo')} disabled={busy}><Undo2 size={16}/>Undo correction</button>}</div>
        {message && <div className="success-message" role="status">{message}</div>}
      </form>}
    </aside>
  </div>
}

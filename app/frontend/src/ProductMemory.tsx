import { useState } from 'react'
import { BookCheck, Check, Search, Undo2, X } from 'lucide-react'
import { stamp } from './api'
import type { ProductMemory as MemoryData } from './types'

interface Props {
  memory: MemoryData; busy: boolean; names: Record<string,string>; expanded: boolean;
  onReview: (productId: string, action: 'confirm' | 'reject', checked: boolean) => Promise<void>;
  onReverse: (eventId: number) => Promise<void>
}

export function ProductMemory({ memory, busy, names, expanded, onReview, onReverse }: Props) {
  const [checked,setChecked]=useState<string|null>(null)
  const known=memory.status==='known_mapping' && memory.match
  return <section className="pipeline-step memory-step" data-testid="product-memory">
    <div className="step-label"><BookCheck size={17}/><h3>Merchant product memory</h3><span className={`tag ${known?'':'tag-warning'}`}>{known?'Known mapping':memory.status==='line_override_precedence'?'Line correction first':'No trusted mapping'}</span></div>
    {known ? <div className="known-product" data-testid="known-product"><strong>{known.product.name}</strong><span>{known.product.product_id} · {names[known.product.node_id]}</span><p>{known.method==='confirmed_identifier'?'Confirmed product identifier':'Exact confirmed receipt alias'} in this merchant’s <code>{memory.namespace}</code> scope. Jev classification bypassed.</p><span className="small muted">{known.alias_provenance?.source.kind==='merchant_identity_confirmation'?'Merchant confirmed this alias': 'Explicitly synthetic catalog assumption'} · {stamp(known.alias_provenance?.created_at || known.product.created_at)}</span></div>
      : <p className="muted small">{memory.status==='line_override_precedence'?'An exact receipt-line correction takes precedence over product memory.': 'Similarity can suggest a product; it cannot establish identity. Jev remains the fallback when a matching cache exists.'}</p>}
    {memory.blocked_reasons.length>0 && <div className="match-warning" role="status">{memory.blocked_reasons.map(reason=><p key={reason}>{reason}</p>)}</div>}
    {!known && memory.candidates.length>0 && <details className="memory-suggestions" open={expanded || undefined}>
      <summary><Search size={14}/>Suggested catalog matches ({memory.candidates.length})<span>{memory.retrieval_mode==='hybrid'?'Lexical + semantic':'Lexical only'}</span></summary>
      <p className="muted small">Check the actual merchant catalog before confirming. These scores rank candidates; they are not identity probabilities.</p>
      {memory.candidates.map(candidate=><article className={`memory-candidate ${candidate.eligible_for_confirmation?'':'candidate-blocked'}`} key={candidate.product.product_id} data-testid={`candidate-${candidate.product.product_id}`}>
        <strong>{candidate.product.name}</strong><span className="small muted">{candidate.product.product_id} · {names[candidate.product.node_id]}</span>
        <div className="match-scores"><span>Lexical {candidate.lexical_score.toFixed(2)}</span><span>Semantic cosine {candidate.semantic_cosine===null?'unavailable':candidate.semantic_cosine.toFixed(2)}</span></div>
        {candidate.blocked_reasons.length>0 && <ul className="match-blocks">{candidate.blocked_reasons.map(reason=><li key={reason}>{reason}</li>)}</ul>}
        {candidate.eligible_for_confirmation && <label className="identity-check"><input type="checkbox" checked={checked===candidate.product.product_id} onChange={e=>setChecked(e.target.checked?candidate.product.product_id:null)} disabled={busy}/>I checked this exact product in the merchant catalog</label>}
        <div className="match-actions"><button type="button" className="secondary-button" disabled={busy || !candidate.eligible_for_confirmation || checked!==candidate.product.product_id} onClick={()=>{setChecked(null);void onReview(candidate.product.product_id,'confirm',true)}}><Check size={14}/>Confirm product</button><button type="button" className="text-button" disabled={busy || candidate.rejected} onClick={()=>void onReview(candidate.product.product_id,'reject',false)}><X size={13}/>{candidate.rejected?'Rejected':'Not this product'}</button></div>
      </article>)}
    </details>}
    {!known && memory.candidates.length===0 && memory.status!=='line_override_precedence' && <p className="small muted">No useful catalog candidates for this description.</p>}
    {memory.embedding.error && <p className="small match-warning">{memory.embedding.error}</p>}
    <details className="technical"><summary>Matching scope & provenance</summary><p className="small">Merchant-scoped · POS namespace <code>{memory.namespace}</code> · exact normalized alias <code>{memory.normalized_alias}</code>{memory.identifier && <> · identifier <code>{memory.identifier}</code></>}</p><p className="small">{memory.embedding.model} · {memory.embedding.revision || 'revision unavailable'}. Embeddings execute locally. No retrieved content is sent to Jev.</p>{known && <pre>{JSON.stringify(known.product.source,null,2)}</pre>}</details>
    {memory.audit.length>0 && <details className="audit" open={known ? true : undefined}><summary>Product memory audit ({memory.audit.length})</summary>{memory.audit.map(event=><div className="audit-entry" key={event.id}><strong>{event.action==='confirm'?'Confirmed alias':event.action==='reject'?'Rejected suggestion':'Reversed review'} · {event.product_id}</strong><span>{stamp(event.created_at)}</span>{event.note&&<p>{event.note}</p>}{event.reversible && <button type="button" className="text-button" disabled={busy} onClick={()=>void onReverse(event.id)}><Undo2 size={13}/>{event.action==='confirm'?'Reverse confirmation':'Undo rejection'}</button>}<details className="technical"><summary>Recorded evidence</summary><pre>{JSON.stringify(event.evidence,null,2)}</pre></details></div>)}</details>}
  </section>
}

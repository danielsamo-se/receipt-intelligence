import { useEffect, useState } from 'react'
import { api } from './api'

interface Metric {
  exact_product_matches:number; incorrect_product_matches:number; correct_leaf:number; correct_parent:number;
  review_required:number; jev_stage_bypasses:number; abstentions:number
}
interface Evidence {
  notice:string; policy:string; summary:Record<string,Metric>; scripted_accepted_suggestions:number;
  existing_jev_cache_inputs:number; unseen_inputs_without_jev_cache:number; limitations:string[];
  source_sha256:Record<string,string>; embedding:{model:string;revision:string};
  cases:{id:string;raw_text:string;group:string;memory_before_review:{matched_product_id:string|null};
    candidate_products:{id:string;semantic_cosine:number|null;blocked_reasons:string[]}[]}[]
}

export function MemoryEvaluation(){
  const [data,setData]=useState<Evidence|null>(null)
  const [error,setError]=useState('')
  useEffect(()=>{const controller=new AbortController();api<Evidence>('/api/product-memory/evaluation',{signal:controller.signal}).then(setData).catch(e=>{if(!controller.signal.aborted)setError(e.message)});return()=>controller.abort()},[])
  const labels:Record<string,string>={model_only:'Cached model only',memory_before_review:'Product memory · initial',memory_after_scripted_review:'Repeat after scripted review'}
  return <section className="panel evidence-panel"><h2>Merchant Product Memory</h2>
    {error?<p className="error">{error}</p>:!data?<p className="muted">Loading the local retrieval check…</p>:<>
      <p className="muted">{data.notice}</p><p className="small muted">Historical configuration: {data.policy}. This preserved Product Memory check uses the former thresholded policy, separately from the raw-choice method comparison above.</p><div className="table-scroll"><table><thead><tr><th>Pipeline</th><th>Exact identities</th><th>Wrong identities</th><th>Correct leaf</th><th>Correct parent</th><th>Needs review</th><th>Jev stage bypasses</th></tr></thead><tbody>{Object.entries(data.summary).map(([key,value])=><tr key={key}><td>{labels[key]||key}</td><td>{value.exact_product_matches}</td><td>{value.incorrect_product_matches}</td><td>{value.correct_leaf}</td><td>{value.correct_parent}</td><td>{value.review_required}</td><td>{value.jev_stage_bypasses}</td></tr>)}</tbody></table></div>
      <p className="small muted">{data.scripted_accepted_suggestions} suggestions were accepted by a scripted oracle using stipulated catalog labels, not by observed merchants. Only {data.existing_jev_cache_inputs} inputs have existing Jev responses; {data.unseen_inputs_without_jev_cache} have no cache. Both pipelines made zero model calls; actual avoided API calls and API costs are zero.</p>
      <details><summary>Misleading near-matches & safety checks</summary>{data.cases.filter(c=>c.group==='misleading').map(item=><div className="audit-entry" key={item.id}><strong>{item.raw_text}</strong><span>{item.memory_before_review.matched_product_id?'Matched identity':'No identity propagated'}</span>{item.candidate_products.slice(0,1).map(candidate=><span className="small" key={candidate.id}>Top suggestion {candidate.id} · semantic cosine {candidate.semantic_cosine?.toFixed(2) ?? 'unavailable'} · {candidate.blocked_reasons.join(' ')||'Unconfirmed similarity requires review.'}</span>)}</div>)}</details>
      <details><summary>Evaluation scope & reproducibility</summary><ul className="limitations">{data.limitations.map(item=><li key={item}>{item}</li>)}</ul><p className="small">Local embedding: {data.embedding.model} · {data.embedding.revision}</p>{Object.entries(data.source_sha256).map(([file,hash])=><p className="small" key={file}><code>{file}</code><br/><code>{hash}</code></p>)}</details>
    </>}
  </section>
}

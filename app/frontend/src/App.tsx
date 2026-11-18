import { useCallback, useEffect, useMemo, useState } from 'react'
import { BarChart3, Beaker, Building2, Check, ChevronDown, CircleHelp, Database, FileText, Info, Layers3, LoaderCircle, ReceiptText, Search, ShieldCheck } from 'lucide-react'
import { api, money, percent } from './api'
import { DecisionStatus } from './decisionRegistry'
import { Evaluation } from './Evaluation'
import { Inspector } from './Inspector'
import type { Bootstrap, LineSummary, Policy, Report, Scope } from './types'

const initialPolicy = (): Policy => localStorage.getItem('receipt-policy') === 'SAFE' ? 'SAFE' : 'FORCED'
const initialScope = (): Scope => { const value=localStorage.getItem('receipt-scope'); return value==='all'||value==='holdout'?value:'pilot' }

export default function App() {
  const [bootstrap,setBootstrap]=useState<Bootstrap|null>(null)
  const [report,setReport]=useState<Report|null>(null)
  const [policy,setPolicy]=useState<Policy>(initialPolicy)
  const [dataset,setDataset]=useState<Scope>(initialScope)
  const [view,setView]=useState<'analytics'|'evaluation'>('analytics')
  const [selectedLine,setSelectedLine]=useState<string|null>(null)
  const [search,setSearch]=useState('')
  const [showAll,setShowAll]=useState(false)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const closeInspector=useCallback(()=>setSelectedLine(null),[])

  useEffect(()=>{const c=new AbortController();api<Bootstrap>('/api/bootstrap',{signal:c.signal}).then(setBootstrap).catch(e=>{if(!c.signal.aborted){setError(e.message);setLoading(false)}});return()=>c.abort()},[])
  useEffect(()=>{localStorage.setItem('receipt-policy',policy)},[policy])
  useEffect(()=>{localStorage.setItem('receipt-scope',dataset);setSearch('');setShowAll(false)},[dataset])

  const refresh=useCallback(async(signal?:AbortSignal)=>{
    if(!bootstrap)return
    setLoading(true)
    try{
      const value=await api<Report>(`/api/merchants/${bootstrap.merchant_id}/report?policy=${policy}&dataset=${dataset}`,{signal})
      setReport(value);setError('')
    }catch(e){if(!signal?.aborted){setError(e instanceof Error?e.message:'Report unavailable');throw e}}
    finally{if(!signal?.aborted)setLoading(false)}
  },[bootstrap,policy,dataset])
  useEffect(()=>{const c=new AbortController();void refresh(c.signal).catch(()=>{});return()=>c.abort()},[refresh])

  const candidates=useMemo(()=>{
    if(!report)return[]
    return search.trim()?report.review_queue.filter(r=>r.raw_text.toLocaleLowerCase().includes(search.toLocaleLowerCase().trim())):report.review_queue
  },[report,search])
  const visible=candidates.slice(0,showAll||search?candidates.length:3)
  const totals=report?.totals
  const saleLines=report?.lines.filter(r=>r.record_type==='sale')||[]
  const total=totals?.sales_value_cents||0
  const leafCount=saleLines.filter(r=>r.specificity==='leaf').length
  const parentCount=saleLines.filter(r=>r.specificity==='parent').length
  const unresolvedCount=saleLines.filter(r=>r.specificity==='none').length
  const extraLeaf=totals&&report?totals.leaf_value_cents-report.comparison.totals.leaf_value_cents:0

  function queueExplanation(line:LineSummary){
    if(line.availability!=='complete')return 'No matching cache available for this policy.'
    if(line.outcome==='parent_only')return `${line.node_label} supported · specific child not assigned.`
    if(line.outcome==='unidentifiable')return 'No category retained by this policy.'
    if(line.outcome==='out_of_scope')return 'Identifiable item outside the supported taxonomy.'
    if(line.outcome==='override')return 'Merchant correction for this exact receipt line.'
    return line.review_required?'Forced leaf assignment with weak or conflicting evidence.':line.node_label||'Specific category assigned.'
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e=>{e.preventDefault();setView('analytics')}}><span className="brand-icon"><ReceiptText size={23}/></span><span>Receipt<span className="brand-second">Intelligence</span></span></a>
      <div className="workspace-label">MERCHANT WORKSPACE</div>
      <nav aria-label="Main navigation"><button className={view==='analytics'?'nav-item active':'nav-item'} onClick={()=>setView('analytics')}><BarChart3 size={18}/>Category Analytics</button><button className={view==='evaluation'?'nav-item active':'nav-item'} onClick={()=>setView('evaluation')}><Beaker size={18}/>Evaluation evidence</button></nav>
      <div className="sidebar-bottom"><span className="offline-mark"><Database size={16}/>Cached Jev · offline-ready</span><p>Tech & AI product case study</p><p>Taxonomy v{bootstrap?.taxonomy_version||'2.0'}</p></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div className="breadcrumb">Merchant workspace<span>/</span>{view==='analytics'?'Category Analytics':'Evaluation evidence'}</div><div className="merchant"><span className="merchant-avatar"><Building2 size={18}/></span><div><strong>{bootstrap?.merchant_name||'Demo merchant'}</strong><span>Local demonstration</span></div></div></header>
      <main>
        <div className="synthetic-banner"><Info size={16}/><span>{bootstrap?.notice||'Synthetic demonstration data — not actual anybill merchant data.'}</span></div>
        {view==='evaluation'?<Evaluation onInspect={id=>{setView('analytics');setDataset('pilot');setPolicy('FORCED');setSelectedLine(id)}}/>:<>
          <div className="page-heading"><div><h1>Category Analytics</h1><p>Category reporting from imperfect POS data, with uncertainty visible.</p></div><div className="period-select"><span>Source examples</span><select aria-label="Source examples" value={dataset} onChange={e=>setDataset(e.target.value as Scope)}>{(bootstrap?.scopes||[{value:'pilot',label:'Initial examples · 30'}]).map(s=><option key={s.value} value={s.value}>{s.label}</option>)}</select></div></div>
          <div className="policy-bar"><div className="policy-controls"><span className="control-label">Classification policy</span><div className="segmented" aria-label="Classification policy"><button data-testid="policy-forced" aria-pressed={policy==='FORCED'} className={policy==='FORCED'?'selected':''} onClick={()=>setPolicy('FORCED')}><Beaker size={15}/>FORCED</button><button data-testid="policy-safe" aria-pressed={policy==='SAFE'} className={policy==='SAFE'?'selected':''} onClick={()=>setPolicy('SAFE')}><ShieldCheck size={15}/>SAFE</button></div><span className="policy-description">{policy==='FORCED'?'Comparison baseline · always picks a leaf':'Review-aware · 85% per-stage threshold'}</span></div><span className="refresh-status" role="status">{loading?<><LoaderCircle className="spin" size={14}/>Updating</>:<><Check size={14}/>Report reconciled</>}</span></div>
          {error&&<div className="error" role="alert">{error}. {report?'Showing the last loaded report.':'Start the local FastAPI backend to load this workspace.'}<button className="text-button" onClick={()=>void refresh().catch(()=>{})}>Retry</button></div>}
          {policy==='FORCED'&&<div className="baseline-note"><Beaker size={16}/><span>FORCED is a comparison baseline. It assigns specific categories even when the cached model abstains.</span></div>}
          {policy==='FORCED'&&dataset!=='pilot'&&<div className="baseline-note">The forced FLAT baseline exists only for the initial 30 examples. Additional examples remain unavailable in this mode; no substitute model result is invented.</div>}
          <section className="kpi-grid" aria-label="Synthetic sales value by classification specificity">
            {[{title:'Specific category',key:'leaf_value_cents',count:leafCount,color:'leaf',Icon:Check,sub:'Leaf-level category assigned'},{title:'Parent category only',key:'parent_value_cents',count:parentCount,color:'parent',Icon:Layers3,sub:'Useful information, less specific'},{title:'Unresolved / outside scope',key:'unresolved_value_cents',count:unresolvedCount,color:'unresolved',Icon:CircleHelp,sub:'Not included in category totals'}].map(({title,key,count,color,Icon,sub})=>{
              const value=totals?totals[key as keyof typeof totals]:0
              return <article key={key} className={`kpi kpi-${color}`}><div className="kpi-label"><span>{title}</span><Icon size={17}/></div><strong className="kpi-value" data-testid={key}>{report?money(value):'—'}</strong><div className="kpi-detail"><strong>{total?percent(value/total):'0%'}</strong><span>· {count} lines</span></div><p>{sub}</p></article>
            })}
          </section>
          <div className="policy-impact" data-testid="policy-impact">{report&&<><span className="impact-label">Compared with {report.comparison.other_policy}</span><span>{money(Math.abs(extraLeaf))} {extraLeaf>=0?'more':'less'} assigned to specific categories</span><span className="impact-divider">·</span><span>{report.comparison.changed_line_count} different decisions</span></>}</div>
          <div className="main-grid">
            <section className="panel chart-panel" aria-label="Category sales visualization"><div className="panel-heading"><div><h2>Where the value lands</h2><p>{report?.period_label||bootstrap?.period_label||'Illustrative week'}</p></div><span className="tag">{report?.line_count||0} receipt patterns</span></div>
              <div className="chart-legend"><span><i className="swatch leaf"/>Specific category</span><span><i className="swatch parent"/>Parent only</span><span><i className="swatch unresolved"/>Unresolved</span></div>
              <div className="category-chart" data-testid="category-chart">
                {report?.categories.map(c=><div className="category-row" key={c.id}><div className="category-name">{c.label}{c.corrected_value_cents>0&&<span title="Includes merchant corrections" className="correction-dot"/>}</div><div className="bar-track" aria-label={`${c.label}: ${money(c.leaf_value_cents)} specific, ${money(c.parent_value_cents)} parent only`}><div className="bar-segment leaf" style={{width:`${c.leaf_value_cents/Math.max(total,1)*100}%`}}/><div className="bar-segment parent" style={{width:`${c.parent_value_cents/Math.max(total,1)*100}%`}}/></div><strong>{money(c.leaf_value_cents+c.parent_value_cents)}</strong></div>)}
                <div className="category-row unresolved-row"><div className="category-name">Unresolved / outside</div><div className="bar-track"><div className="bar-segment unresolved" style={{width:`${(totals?.unresolved_value_cents||0)/Math.max(total,1)*100}%`}}/></div><strong>{report?money(totals?.unresolved_value_cents||0):'—'}</strong></div>
              </div>
              <div className="chart-footer"><span>Share of modeled sales value</span><strong>{report?money(total):'—'} total</strong></div>
              <div className="adjustment-note"><Info size={15}/><span>Deposits and discounts: <strong>{money(totals?.adjustment_value_cents||0)}</strong> net, excluded from product-category sales.</span></div>
            </section>
            <section className="panel queue-panel"><div className="panel-heading"><div><h2>Review queue <span className="count-badge" data-testid="review-count">{report?.review_queue.length||0}</span></h2><p>Prioritized by modeled sales impact</p></div></div><div className="queue-search"><Search size={16}/><input aria-label="Find a receipt line" placeholder="Find a receipt line…" value={search} onChange={e=>setSearch(e.target.value)}/></div>
              <div className="queue-list">{visible.map(line=><button className="queue-item" data-testid={`review-row-${line.line_id}`} key={line.line_id} onClick={()=>setSelectedLine(line.line_id)}><div className="queue-item-top"><strong>{line.raw_text}</strong><strong>{money(line.value_cents)}</strong></div><p>{queueExplanation(line)}</p><DecisionStatus decision={line}/></button>)}{!loading&&visible.length===0&&<div className="queue-empty"><Check size={24}/><strong>{search?'No matching descriptions':'No lines require review in this view'}</strong><span>AI category assignments remain reviewable.</span></div>}</div>
              {!search&&candidates.length>3&&<button className="queue-expand" onClick={()=>setShowAll(!showAll)}>{showAll?'Show highest-impact lines':`View all ${candidates.length} review items`}<ChevronDown size={15}/></button>}
            </section>
          </div>
          <div className="data-footer"><span><Database size={14}/>Real cached Jev 1.14 assessments</span><span>{report?.correction_count||0} merchant-corrected lines</span><span>Net modeled receipt value: <strong>{money(totals?.net_receipt_value_cents||0)}</strong></span></div>
          <details className="panel all-lines"><summary><FileText size={17}/>Inspect all {report?.line_count||0} receipt lines<span>Includes adjustments and scope rejections</span></summary><div className="table-scroll"><table><thead><tr><th>POS description</th><th>Occurrences</th><th>Value</th><th>Outcome</th><th>Category</th></tr></thead><tbody>{report?.lines.map(line=><tr key={line.line_id}><td><button className="line-link" onClick={()=>setSelectedLine(line.line_id)}>{line.raw_text}</button><span className="row-meta">{line.line_id} · {line.record_type==='sale'?'Modeled sale':line.record_type.replaceAll('_',' ')}</span></td><td>{line.quantity}</td><td>{money(line.value_cents)}</td><td><DecisionStatus decision={line}/></td><td>{line.node_label||'—'}</td></tr>)}</tbody></table></div></details>
        </>}
      </main>
    </div>
    {selectedLine&&bootstrap&&<Inspector lineId={selectedLine} merchantId={bootstrap.merchant_id} policy={policy} nodes={bootstrap.nodes} onClose={closeInspector} onChanged={async()=>{await refresh()}}/>}
  </div>
}

import { useState } from 'react'
import { BookCheck, LoaderCircle, Play } from 'lucide-react'
import { api } from './api'
import type { InspectorData, Policy } from './types'

const examples=[
  {name:'Unknown yogurt alias',text:'ERDBEER JOGHURT NM 150 G',price:'0.79',identifier:''},
  {name:'Known merchant SKU',text:'ART 123456',price:'0.79',identifier:'SKU-104'},
  {name:'Misleading pack size',text:'ERDBEER JOGHURT 500G',price:'1.69',identifier:''},
  {name:'Identifier / variant conflict',text:'CC ZERO 1L',price:'1.49',identifier:'SKU-106'},
]

export function MemoryInput({merchantId,policy,onInspect}:{merchantId:string;policy:Policy;onInspect:(id:string)=>void}){
  const [text,setText]=useState(examples[0].text)
  const [price,setPrice]=useState(examples[0].price)
  const [identifier,setIdentifier]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  return <details className="panel memory-entry">
    <summary><BookCheck size={17}/>Process a new POS description<span>Merchant Product Memory · synthetic demo</span></summary>
    <div className="memory-entry-body"><p>Check confirmed product knowledge before the Jev fallback. Unconfirmed similarity requests verification; a confirmed exact alias can be reused next time.</p>
      <label className="memory-example-label">Synthetic scenario<select aria-label="Synthetic product memory scenario" defaultValue="0" onChange={e=>{const example=examples[Number(e.target.value)];setText(example.text);setPrice(example.price);setIdentifier(example.identifier);setError('')}}>{examples.map((example,i)=><option key={example.name} value={i}>{example.name}</option>)}</select></label>
      <form className="memory-input-form" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const response=await api<InspectorData>(`/api/merchants/${merchantId}/memory/receipts`,{method:'POST',body:JSON.stringify({raw_text:text,price_cents:Math.round(Number(price)*100),merchant_type:'supermarket',pos_namespace:'demo-pos',identifier:identifier.trim()||null,policy})});onInspect(response.decision.line_id)}catch(e){setError(e instanceof Error?e.message:'Could not process input')}finally{setBusy(false)}}}>
        <label>POS description<input aria-label="New POS description" required maxLength={160} value={text} onChange={e=>setText(e.target.value)} disabled={busy}/></label>
        <label>Price (€)<input aria-label="New POS price" type="number" min="0.01" max="1000" step="0.01" required value={price} onChange={e=>setPrice(e.target.value)} disabled={busy}/></label>
        <label>Merchant SKU (optional)<input aria-label="Merchant product identifier" maxLength={80} placeholder="e.g. SKU-104" value={identifier} onChange={e=>setIdentifier(e.target.value)} disabled={busy}/></label>
        <button className="primary-button" disabled={busy||!text.trim()}>{busy?<LoaderCircle className="spin" size={15}/>:<Play size={15}/>}Process description</button>
      </form>{error&&<div className="error" role="alert">{error}</div>}
      <p className="small muted">Fictional catalog · supermarket · demo-pos. One-off inputs are persisted separately and do not add sales to the weekly report. No new Jev calls.</p>
    </div>
  </details>
}

import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AlertTriangle, CloudRain, Clock3, ChevronRight, Plane, Radio, ShieldCheck, SlidersHorizontal, Users } from 'lucide-react';
import './styles.css';
import './timeline.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const fmt = t => new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
const fmtNum = n => Number(n || 0).toLocaleString();

function App() {
  const [weather, setWeather] = useState(38), [congestion, setCongestion] = useState(62);
  const [closed, setClosed] = useState([]), [state, setState] = useState(null), [result, setResult] = useState(null);
  const [selected, setSelected] = useState('f2'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => { fetch(`${API_URL}/api/state`).then(r => { if (!r.ok) throw Error('API unavailable'); return r.json(); }).then(setState).catch(e => setError(`${e.message}. Start the SkyFlow API to load the deterministic demo operations feed.`)); }, []);
  const run = async (scenario = false) => {
    setBusy(true); setError('');
    try {
      const endpoint = scenario ? '/api/scenarios/simulate' : '/api/optimize';
      const response = await fetch(`${API_URL}${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ weather, congestion, gate_closures: closed, flights: state.flights.map(({ risk, ...flight }) => flight), name: 'Weather and congestion scenario' }) });
      const body = await response.json();
      if (!response.ok) throw Error(body.detail || 'Optimization request failed');
      setResult(body); if (!body.feasible) setError(body.error);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const rows = result?.feasible ? result.assignments : (result?.baseline?.assignments || state?.flights || []);
  const active = rows.find(f => f.id === selected) || rows[0];
  const metrics = result?.feasible ? result.optimized.metrics : result?.baseline?.metrics;
  const audit = result?.feasible ? result.optimized.audit : result?.baseline?.audit;
  const gates = state?.gates || [];
  const lanes = useMemo(() => gates.map(g => ({ ...g, flights: rows.filter(f => f.gate === g.id) })), [gates, rows]);
  if (!state) return <div className="loading"><b>SkyFlow</b><p>{error || 'Loading deterministic operations feed…'}</p></div>;
  return <div className="app"><aside><div className="brand"><span className="logo"><Plane size={20}/></span>Sky<span>Flow</span></div>
    <div className="airport">DEL · INDIRA GANDHI INTL.<small>Terminal Operations Control</small></div>
    <nav><a className="active"><Radio/> Command Center</a><a><Plane/> Flight Intelligence</a><a><SlidersHorizontal/> Gate Optimizer</a><a><ShieldCheck/> Disruption Playbooks</a></nav>
    <div className="operator"><div className="avatar">RK</div><span>R. Kumar<small>Ops Controller</small></span></div></aside>
    <main><header><div><p className="eyebrow">AIRPORT DIGITAL TWIN / 24 SEP 2026</p><h1>Keep every turn moving.</h1><p className="subtitle">Predict taxi delay risk. Protect connections. Optimize the gate plan.</p></div>
      <div className="headerRight"><span className="pulse"><i/> {result?.solver || state.mode}</span><button disabled={busy} onClick={() => run(false)}>{busy ? 'Optimizing…' : 'Run optimization'} <ChevronRight size={16}/></button></div></header>
      <div className="modeBanner">SIMULATION / SYNTHETIC OPERATIONS FEED <span>Deterministic offline demo data · DEL</span></div>
      {error && <div className="errorBanner"><AlertTriangle size={16}/>{error}</div>}
      <section className="metrics"><Metric icon={<Clock3/>} label="Mean predicted delay" value={`${metrics?.averageDelayMinutes ?? mean(rows, f => f.risk?.expectedMinutes)} min`} note="Scikit-learn regression"/>
        <Metric icon={<AlertTriangle/>} label="Flights at risk" value={`${rows.filter(f => f.risk?.probability >= .5).length} / ${rows.length}`} note="Classifier probability > 50%" amber/>
        <Metric icon={<Users/>} label="Passengers protected" value={result?.feasible ? fmtNum(result.passengersProtected) : '—'} note="Estimated reduction in disruption"/>
        <Metric icon={<ShieldCheck/>} label="Constraint audit" value={audit ? `${audit.percentage}%` : 'Pending'} note={audit ? `${audit.passed} / ${audit.total} checks passed` : 'Run optimization'} green/></section>
      {result?.comparison && <section className="comparison panel"><div className="panelHead"><div><h2>Baseline vs optimized</h2><p>Calculated operational impact for this run</p></div><span className="chip">{result.feasible ? 'Feasible plan' : 'Infeasible'}</span></div>
        <div className="compareGrid">{[['Average delay', 'averageDelayMinutes', ' min'], ['Delay exposure', 'delayExposure', ' pax·min'], ['Remote stands', 'remoteStands', ''], ['Connection exposure', 'connectionExposure', ' pax·min']].map(([label,key,unit]) => <div key={key}><small>{label}</small><b>{fmtNum(result.comparison.baseline[key])} → {fmtNum(result.comparison.optimized[key])}{unit}</b><em>Improvement {fmtNum(result.comparison.improvement[key])}{unit}</em></div>)}</div>
        <p className="objective">Objective {fmtNum(result.optimized.metrics.objectiveValue)} · delay {fmtNum(result.optimized.metrics.breakdown.delayExposure)} · remote {fmtNum(result.optimized.metrics.breakdown.remoteStand)} · connections {fmtNum(result.optimized.metrics.breakdown.connectionRisk)} · gate change {fmtNum(result.optimized.metrics.breakdown.gateChange)} · walking {fmtNum(result.optimized.metrics.breakdown.walkingDistance)}</p></section>}
      <section className="grid"><div className="panel timeline"><div className="panelHead"><div><h2>Gate timeline</h2><p>{result ? 'Current recommended assignment' : 'Baseline schedule · run optimizer for recommendations'}</p></div><span className="chip">15 min safety buffer</span></div>
        {lanes.map(g => <div className={'lane '+(closed.includes(g.id)?'closed':'')} key={g.id}><button onClick={() => { setClosed(c => c.includes(g.id) ? c.filter(x => x !== g.id) : [...c, g.id]); setResult(null); }}>{g.id}<small>{closed.includes(g.id)?'Closed':'Operational'} · T{g.terminal.slice(-1)}</small></button><div className="track">{g.flights.map(f => { const scheduled = new Date(f.scheduled); const minutes = scheduled.getHours()*60+scheduled.getMinutes(); return <div className={'flight '+(f.risk?.probability >= .5?'risk':'')} onClick={() => setSelected(f.id)} key={f.id} title={`${f.flight} · ${fmt(f.scheduled)}`} style={{'--flight-left':`${Math.max(0,(minutes-480)/3)}%`,'--flight-width':`${Math.max(14,f.duration/3)}%`}}><strong>{f.flight}</strong><span>{fmt(f.scheduled)} · {f.direction}</span></div>; })}</div></div>)}<p className="hint">Click a gate to simulate its closure, then rerun the optimizer.</p></div>
        <div className="panel insight"><p className="eyebrow">FLIGHT INTELLIGENCE</p>{active ? <><div className="flightTitle"><div className="flightIcon"><Plane size={22}/></div><div><h2>{active.flight}</h2><p>{active.airline} · {active.direction} · {fmt(active.scheduled)}</p></div><span className={active.risk?.probability >= .5?'badge high':'badge'}>{Math.round((active.risk?.probability || 0)*100)}% risk</span></div>
          <div className="riskNumber"><strong>+{active.risk?.expectedMinutes ?? '—'}</strong><span>min expected<br/>delay · P(delay &gt; 15 min) from classifier</span></div>
          <div className="drivers"><h3>Risk drivers · model inputs</h3>{(active.risk?.drivers || []).map(d => <div key={d.name}><span>{d.name}<small>{d.value} contribution units</small></span><div className="bar"><i style={{width:`${Math.min(100,d.share)}%`}}/></div><b>{d.share}%</b></div>)}</div>
          <div className="recommend"><AlertTriangle size={18}/><p><b>{result?.feasible ? 'Recommended assignment' : 'Current assignment'}</b><br/>Gate <strong>{active.gate || 'Pending optimization'}</strong> · {fmtNum(active.connecting_passengers)} connecting passengers.</p></div></> : <p>No flight selected.</p>}</div></section>
      <section className="lower"><div className="panel table"><div className="panelHead"><div><h2>Flight decision queue</h2><p>Prediction, connection load and gate recommendation</p></div><span className="chip">{rows.length} flights</span></div><div className="tableHead"><span>FLIGHT</span><span>SCHEDULE</span><span>RISK</span><span>GATE</span><span>STATUS</span></div>
        {rows.map(f => <div className={'row '+(selected===f.id?'chosen':'')} onClick={() => setSelected(f.id)} key={f.id}><span><b>{f.flight}</b><small>{f.airline} · {f.direction}</small></span><span>{fmt(f.scheduled)}</span><span><i className={f.risk?.probability>=.5?'dot red':'dot'}/> {Math.round((f.risk?.probability||0)*100)}%</span><span><b>{f.gate || '—'}</b></span><span className={f.gate==='REMOTE'?'exception':'optimized'}>{f.status || 'Scheduled'}</span></div>)}</div>
        <div className="panel scenario"><div className="panelHead"><div><h2>Scenario lab</h2><p>Recalculate every affected plan metric</p></div></div><Control icon={<CloudRain size={17}/>} title="Weather severity" value={weather} onChange={v=>{setWeather(v);setResult(null)}}/><Control icon={<Radio size={17}/>} title="Surface congestion" value={congestion} onChange={v=>{setCongestion(v);setResult(null)}}/>
          <button className="scenarioButton" disabled={busy} onClick={() => run(true)}>Simulate scenario <ChevronRight size={15}/></button>
          <div className="simResult"><span>PLAN STATUS</span><b>{result?.feasible ? 'Feasible · hard constraints audited' : result ? 'Infeasible · no invalid plan returned' : 'Baseline schedule loaded'}</b><p>{metrics ? `${metrics.remoteStands} remote stands · ${metrics.gateUtilization}% gate utilization` : 'Weather and closure changes are applied on optimization'}</p></div>
          {audit && <div className="auditList"><b>Constraint checks</b>{audit.checks.map(c=><div key={c.name}><span>{c.name}</span><strong>{c.passed}/{c.total}</strong></div>)}</div>}</div></section>
    </main></div>;
}
function mean(rows, fn) { return rows.length ? Math.round(rows.reduce((s,f)=>s+(fn(f)||0),0)/rows.length) : 0; }
function Metric({icon,label,value,note,amber,green}) { return <div className={'metric '+(amber?'amber ':'')+(green?'green':'')}><div className="metricIcon">{icon}</div><div><p>{label}</p><strong>{value}</strong><small>{note}</small></div></div>; }
function Control({icon,title,value,onChange}) { return <div className="control"><div><i>{icon}</i><span>{title}<small>{value}% intensity</small></span></div><input type="range" min="0" max="100" value={value} onChange={e=>onChange(+e.target.value)}/></div>; }
createRoot(document.getElementById('root')).render(<App/>);

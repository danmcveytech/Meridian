"use strict";
const $ = id => document.getElementById(id);
const nf = new Intl.NumberFormat("en-GH",{maximumFractionDigits:1});
let report;
function elem(tag, text) {
  const n=document.createElement(tag); n.textContent=text; return n;
}
async function api(path,options={}) {
  const response=await fetch(path,{...options,headers:{"X-Meridian":"workspace"}});
  const data=await response.json();
  if(!response.ok) throw Object.assign(new Error(data.detail||"Request failed."),{status:response.status});
  return data;
}
function monthName(value) {
  return new Intl.DateTimeFormat("en-GB",{month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(value+"-01T00:00:00Z"));
}
function chart(node,rows,key) {
  const data=rows.filter(r=>r[key]!=null);
  if(!data.length){node.textContent="No observations available.";return;}
  const percent=key==="late_pct";
  const unit=percent?"%":"";
  const peak=Math.max(1,...data.map(r=>r[key]));
  const step=10**Math.floor(Math.log10(peak));
  const ceiling=Math.ceil(peak/step)*step;
  const ns="http://www.w3.org/2000/svg";
  function shape(tag,attrs,value=""){
    const n=document.createElementNS(ns,tag);
    for(const [k,v] of Object.entries(attrs)) n.setAttribute(k,v);
    n.textContent=value;return n;
  }
  const svg=shape("svg",{viewBox:"0 0 400 156",role:"img","aria-label":percent?"Monthly late-payment rate":"Monthly units ordered"});
  const x=i=>49+i*338/Math.max(1,data.length-1), y=v=>125-109*v/ceiling;
  [0,.5,1].forEach(f=>{
    const level=f*ceiling;
    svg.append(shape("line",{x1:49,x2:389,y1:y(level),y2:y(level),stroke:"#dce2e8","stroke-dasharray":"3 4"}));
    svg.append(shape("text",{x:41,y:y(level)+4,"text-anchor":"end"},new Intl.NumberFormat("en",{notation:"compact"}).format(level)+unit));
  });
  const points=data.map((r,i)=>x(i)+","+y(r[key])).join(" ");
  svg.append(shape("polygon",{points:"49,125 "+points+" "+x(data.length-1)+",125",fill:"#eaf0f9"}));
  svg.append(shape("polyline",{points,fill:"none",stroke:"#30589a","stroke-width":2.5,"stroke-linejoin":"round"}));
  data.forEach((r,i)=>{
    const dot=shape("circle",{cx:x(i),cy:y(r[key]),r:i===data.length-1?4:2.5,fill:i===data.length-1?"#ae4727":"#30589a"});
    dot.append(shape("title",{},monthName(r.month)+" · "+nf.format(r[key])+unit));svg.append(dot);
  });
  for(const i of new Set([0,Math.floor((data.length-1)/2),data.length-1])){
    svg.append(shape("text",{x:x(i),y:150,"text-anchor":i===0?"start":i===data.length-1?"end":"middle"},monthName(data[i].month)));
  }
  node.replaceChildren(svg);
}
function cards(node,items){
  node.replaceChildren(...items.map(([name,value])=>{
    const item=elem("div","");item.className="card";item.append(elem("small",name),elem("b",value));return item;
  }));
}
function pairs(node,items){
  const dl=elem("dl","");items.forEach(([key,val])=>dl.append(elem("dt",key),elem("dd",val)));node.replaceChildren(dl);
}
function tab(id){
  document.querySelectorAll(".panel").forEach(p=>p.hidden=p.id!==id);
  document.querySelectorAll("[data-tab]").forEach(b=>{b.classList.toggle("active",b.dataset.tab===id);b.setAttribute("aria-pressed",b.dataset.tab===id);});
}
function display(r){
  report=r; const risk=r.objective==="collections";
  $("welcome").hidden=true;$("desk").hidden=false;$("switch").value=r.objective;
  $("headerLabel").textContent=r.name;$("context").textContent=r.source+"   /   "+monthName(r.latest)+" close";
  $("title").textContent=r.title;$("subtitle").textContent=risk?"Focus follow-up on accounts most likely to pay late next month.":"Estimate next month’s order volume for each active account.";
  cards($("kpis"),[[risk?"Expected late accounts":"Forecast units",nf.format(r.estimate)],["Accounts scored",nf.format(r.accounts)],["Outstanding balance (GHS)",r.balance.toLocaleString("en-GH",{minimumFractionDigits:2,maximumFractionDigits:2})]]);
  const key=risk?"late_pct":"units", data=r.trends.filter(x=>x[key]!=null), last=data.at(-1);
  $("chartTitle").textContent=risk?"Late-payment history":"Monthly units ordered";
  chart($("trend"),data,key);
  $("trendText").textContent=risk?'Of accounts with known outcomes for '+monthName(last.month)+', '+last.late_pct+'% paid late the following month.':'Accounts ordered '+nf.format(last.units)+' units in '+monthName(last.month)+'.';
  $("queueTitle").textContent=risk?"Collections queue":"Account demand forecast";
  $("queueText").textContent="Highest "+(risk?"estimated probabilities":"forecast volumes")+" first. Showing "+Math.min(10,r.accounts)+" of "+r.accounts+" accounts.";
  if(!risk) $("queueText").textContent+=" Forecast method: "+r.forecast_method+".";
  $("scoreLabel").textContent=risk?"Late probability":"Forecast units";
  $("scores").replaceChildren(...r.predictions.slice(0,10).map((p,index)=>{
    const tr=elem("tr","");
    const rank=elem("td",String(index+1).padStart(2,"0")); rank.className="rank";
    const value=elem("td",""); const track=elem("span","");track.className="track";
    const fill=elem("i","");fill.style.width=(100*p.prediction/(risk?1:Math.max(1,r.predictions[0].prediction)))+"%";track.append(fill);
    value.append(track,elem("span",risk?nf.format(p.prediction*100)+"%":nf.format(p.prediction)));
    tr.append(rank,elem("td",p.account),elem("td",p.region),value);return tr;
  }));
  pairs($("comparison"),[[r.metric,r.score],["Baseline",r.baseline]]);
  const better=risk?r.score>r.baseline:r.forecast_method==="Ridge regression";
  $("verdict").textContent=better?"The model beat the baseline on the held-out months.":"The baseline matched or beat the model on the held-out months.";
  $("evaluation").textContent=r.train+" earlier snapshots trained the evaluation model. "+r.test+" later snapshots from "+r.first_test+" through "+r.last_test+" tested it. "+(risk?"Higher average precision is better.":"Lower error in units per account is better.");
  if(!risk) $("evaluation").textContent+=" Forecast method for the dashboard and CSV: "+r.forecast_method+".";
  cards($("metrics"),[[r.metric,r.score],[risk?"Historical late-rate baseline":"Last-month units baseline",r.baseline]]);
  $("driverHelp").textContent="Change in holdout performance after shuffling each input. Larger positive values indicate greater reliance on that input.";
  if(!risk) $("driverHelp").textContent+=" These values describe the ridge model.";
  pairs($("drivers"),r.drivers.map(d=>[d.name,d.value]));
  pairs($("quality"),[["Imported rows",r.quality.raw_rows],["Duplicate rows",r.quality.duplicate_rows],["Missing prior days (raw)",r.quality.missing_days],["Invalid volume or balance (raw)",r.quality.invalid_rows],["Usable snapshots",r.quality.clean_rows]]);
  $("evidence").replaceChildren(...Object.entries(r.evidence).map(([key,v])=>elem("p",key+" · "+Object.entries(v).map(([k,val])=>k.replaceAll("_"," ")+": "+val).join(" / "))));
  $("brief").textContent=r.brief||"";
  $("agentStatus").textContent=r.brief?"Agent draft · review against the evidence below.":"No agent brief generated for this objective.";
  $("saved").hidden=!!r.brief || !risk || r.source!=="Synthetic demo";$("generate").hidden=!!r.brief; $("error").textContent="";tab("overview");
}
$("source").onchange=()=>{$("import").hidden=$("source").value!=="custom";$("file").required=!$("import").hidden;};
$("setup").onsubmit=async e=>{
  e.preventDefault();const custom=$("source").value==="custom";$("create").disabled=true;$("create").textContent="Preparing analysis…";$("setupError").textContent="";
  try{const q=new URLSearchParams({name:$("business").value,objective:$("objective").value,custom});
    const {objective}=await api("/api/workspace?"+q,{method:"POST",body:custom?$("file").files[0]:null});display(await api("/api/report?objective="+objective));
  }catch(err){$("setupError").textContent=err.message;}finally{$("create").disabled=false;$("create").textContent="Create workspace →";}
};
$("switch").onchange=async()=>{const s=$("switch");s.disabled=true;try{display(await api("/api/report?objective="+s.value));}catch(e){$("error").textContent=e.message;s.value=report.objective;}finally{s.disabled=false;}};
document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>tab(b.dataset.tab));
$("generate").onclick=async()=>{const b=$("generate"), current=report, obj=report.objective;b.disabled=true;$("agentStatus").textContent="Requesting management brief…";
  try{const res=await api("/api/brief?objective="+obj,{method:"POST"});if(report===current){report.brief=res.brief;$("brief").textContent=res.brief;$("agentStatus").textContent="Agent draft · review against the evidence below.";b.hidden=true;}}
  catch(e){if(report===current)$("agentStatus").textContent=e.message;}finally{b.disabled=false;}
};
$("print").onclick=()=>window.print();
$("new").onclick=()=>{$("desk").hidden=true;$("welcome").hidden=false;$("headerLabel").textContent="Business analytics";$("business").focus();};
$("export").onclick=()=>{
  const cell=v=>'"'+String(v).replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')+'"';
  const csv=["account,region,prediction",...report.predictions.map(p=>[p.account,p.region,p.prediction].map(cell).join(","))].join("\r\n");
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv"})),link=elem("a","");link.href=url;link.download=report.objective+"-"+report.latest+".csv";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
fetch("/assets/sample-trend.json").then(r=>r.json()).then(r=>chart($("previewChart"),r,"units"));
api("/api/report").then(display).catch(e=>{if(e.status!==401)$("setupError").textContent=e.message;});

$("saved").onclick=async()=>{try{const r=report,res=await api("/api/sample-brief");if(report===r){$("brief").textContent=res.brief;$("agentStatus").textContent="Saved Snwolley draft for this demo dataset.";}}catch(e){$("agentStatus").textContent=e.message;}};

$("inspect").onclick=()=>{tab("model");$("model").scrollIntoView({block:"start"});};

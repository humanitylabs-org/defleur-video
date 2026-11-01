/* DeFleur house components: state-pure, spoken-pivot driven, no random/clock/loop.
   Geometry and mechanisms derive from Conversation first v3/v3.1, Two Futures
   and Information Diet. Labels stay above native caption.safe_rect. */
(() => {
  'use strict';
  const plan = JSON.parse(document.querySelector('#house-plan').textContent);
  const root = document.querySelector('#house');
  const C = plan.neutral ? {white:'#f3ece2',gold:'#f3ece2',red:'#6b6258',dim:'#6b6258',blue:'#f3ece2'} : {white:'#f3ece2',gold:'#e9b45c',red:'#e5533d',dim:'#6b6258',blue:'#8fb0de'};
  const clamp = n => Math.max(0, Math.min(1, n));
  const ease = n => { n = clamp(n); return n*n*(3-2*n); };
  const safe = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text = (x,y,s,size=52,color=C.white) => `<text x="${x}" y="${y}" style="font-size:${size}px;fill:${color}">${safe(s || '')}</text>`;
  const line = (x,y,x2,y2,color=C.gold,w=6) => `<line x1="${x}" y1="${y}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${w}" stroke-linecap="round"/>`;
  const circle = (x,y,r,color=C.gold) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}"/>`;
  const box = (x,y,w,h,color=C.dim,fill='none') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="16" fill="${fill}" stroke="${color}" stroke-width="4"/>`;
  // Outline people maintain their identities as positions/relationships change.
  const person = (x,y,color=C.white) => `<g transform="translate(${x} ${y})"><circle cx="0" cy="-18" r="10" fill="none" stroke="${color}" stroke-width="4"/><path d="M-14 24V4Q0-12 14 4V24M0 4V38M0 38L-12 58M0 38L12 58" fill="none" stroke="${color}" stroke-width="4"/></g>`;
  const components = {
    lifeline(b,p) {
      const end = 800 + 480*p, g=b.color || C.gold;
      return text(540,380,b.labels[0] || 'LIFESPAN',76) + line(180,840,end,840,p>.8?C.red:C.white,10) + circle(180,840,12) + text(180,915,b.labels[1] || 'BIRTH',38) + `<g opacity="${1-p}">${line(800+480*p,800,800+480*p,880)}${text(800+480*p,945,'END',44)}</g><g opacity="${p}">${text(540,710,'∞',200,p>.8?C.red:g)}</g>` + (b.labels[2] && p>.8 ? text(540,1050,b.labels[2],62,C.red):'');
    },
    meter(b,p) {
      const a=(-70+140*Math.min(p*1.6,1))*(1-Math.max(0,(p-.62)/.38));
      const needle=`<g transform="rotate(${a} 540 900)">${line(540,900,540,590,C.white,12)}</g>`;
      return text(540,380,b.labels[0],70)+`<path d="M180 900A360 360 0 0 1 900 900" fill="none" stroke="${C.dim}" stroke-width="30"/><path d="M400 568A360 360 0 0 1 680 568" fill="none" stroke="${C.gold}" stroke-width="30"/>`+needle+circle(540,900,24)+text(260,1010,b.labels[1] || 'TRUST ALL',42)+text(820,1010,b.labels[2] || 'DOUBT ALL',42)+text(540,1120,b.labels[3] || 'HEALTHY',60,C.gold);
    },
    'stacked-moves'(b,p) {
      let out=text(540,350,b.labels[0],70)+box(300,480,480,140,p>.2?C.red:C.gold)+text(540,575,p>.2?'?':'✓',76,p>.2?C.red:C.gold);
      b.labels.slice(1).forEach((s,i)=>{const q=clamp(p*3-i);out+=`<g opacity="${q}" transform="translate(${(1-q)*-50} 0)">${text(540,770+i*125,s,64)}</g>`;});return out;
    },
    population(b,p) {
      let out=text(540,350,b.labels[0],70);const pts=Array.from({length:12},(_,i)=>{const a=2*Math.PI*i/12;return [540+Math.cos(a)*330,750+Math.sin(a)*260];});
      pts.forEach(([x,y],i)=>{const [nx,ny]=pts[(i+1)%12];out+=`<g opacity="${1-p}">${line(x,y,540,750,C.dim,3)}</g><g opacity="${p}">${line(x,y,nx,ny,C.gold,4)}</g>`+person(x,y,i===0&&p>.7?C.red:C.white);});
      return out+`<g opacity="${1-p}">${circle(540,750,26)}</g>`+text(540,1120,b.labels[1],54,C.gold);
    },
    reservoir(b,p) {
      let out=text(540,350,b.labels[0],70)+box(310,530,460,550,C.white);
      out+=`<rect x="315" y="${1075-530*p}" width="450" height="${530*p}" rx="12" fill="${C.gold}" opacity=".65"/>`;
      for(let i=0;i<5;i++){const x=190+i*175;out+=line(x,440,540,550,C.dim,4)+circle(x+(540-x)*p,440+110*p,10,C.gold);}
      return out+text(540,1150,b.labels[1],48);
    },
    'routing-chain'(b,p) {
      let out=text(540,350,b.labels[0],68);const xs=[230,540,850];
      xs.forEach((x,i)=>{out+=box(x-100,620,200,210,i<=p*3?C.gold:C.dim)+text(x,745,b.labels[i+1] || '',40);if(i<2)out+=line(x+105,725,x+205,725,p*3>i+1?C.gold:C.dim,8);});
      return out+circle(230+620*p,915,18,C.gold);
    },
    'path-target'(b,p) {
      const x=200+600*p,y=960-320*p;
      return text(540,350,b.labels[0],70)+`<path d="M200 960Q540 960 800 640" fill="none" stroke="${C.dim}" stroke-width="8" stroke-dasharray="16 16"/>`+circle(800,640,60,C.gold)+circle(800,640,40,'#08080a')+circle(x,y,22,C.white)+text(540,1120,b.labels[1],52);
    },
    'comparison-split'(b,p) {
      return text(540,350,b.labels[0],70)+line(540,470,540,1100,C.dim,3)+box(140,560,330,480,C.dim)+box(610,560,330,480,C.gold)+`<rect x="620" y="${1030-450*p}" width="310" height="${450*p}" fill="${C.gold}" opacity=".3"/>`+text(305,1100,b.labels[1],44)+text(775,1100,b.labels[2],44);
    },
    'routine-grid'(b,p) {
      let out=text(540,350,b.labels[0],72);const count=1+Math.floor(15*p);
      for(let i=0;i<count;i++){const x=180+(i%4)*190,y=460+Math.floor(i/4)*145;out+=box(x,y,150,120)+circle(x+40,y+60,20,C.dim)+text(x+105,y+76,'8:30',36);}
      if(p>.8)for(let i=0;i<7;i++)out+=`<rect x="${162+i*123}" y="425" width="24" height="650" rx="6" fill="${C.dim}"/>`;
      return out+text(540,1140,b.labels[1] || (p>.8?'A SENTENCE':''),62,C.gold);
    },
    'quality-area'(b,p) {
      return text(540,350,b.labels[0],72)+line(220,1050,880,1050,C.white)+line(220,1050,220,500,C.white)+`<rect x="225" y="${1045-490*p}" width="620" height="${Math.max(6,490*p)}" fill="${C.gold}" opacity=".55"/>`+text(540,1150,b.labels[1] || 'TIME',44)+text(540,780,p>.6?b.labels[2]:'',66);
    },
    'source-frame'(b,p) {return text(540,280,b.labels[0],60)+`<rect x="140" y="${560+300*p}" width="800" height="65" fill="${C.gold}" opacity=".2"/>`+text(540,1170,b.attribution,36);}
  };
  const assetURL=value=>{
    if(typeof value!=='string'||!/^assets\/[a-z0-9][a-z0-9_-]*\.(?:png|jpe?g)$/i.test(value))throw new Error('House images must be local packaged assets');
    return 'assets/'+encodeURIComponent(value.slice(7));
  };
  const scenes=plan.beats.map(b=>{
    const el=document.createElement('section');el.className='house-scene'+(b.component==='image-beat'?' image':'');
    el.dataset.component=b.component;el.dataset.beat=b.id;
    if(b.component==='image-beat'){
      const img=document.createElement('img');img.className='illustration';img.src=assetURL(b.asset);img.alt='Generated conceptual illustration, not documentary evidence';el.append(img);
      const scrim=document.createElement('div');scrim.className='image-scrim';el.append(scrim);
    } else {
      if(b.component==='source-frame'){const img=document.createElement('img');img.className='source';img.src=assetURL(b.source_asset);img.alt=b.attribution;el.append(img);}
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 1080 1920');el.append(svg);
    }
    root.append(el);return {b,el};
  });
  window.renderFrame=t=>{
    for(const {b,el} of scenes){
      const on=t>=b.start&&t<b.end;
      el.style.visibility=on?'visible':'hidden';el.style.opacity=on?String(Math.min(1,(t-b.start)/.25,(b.end-t)/.25)):'0';
      if(!on)continue;
      // Each pivot advances one substantive state. Reverse seeks reconstruct it.
      const p=b.phases.reduce((sum,phase)=>sum+ease((t-phase.at)/.65),0)/b.phases.length;
      if(b.component==='image-beat')el.querySelector('img').style.transform=`scale(${1+.055*p})`;
      else {
        const svg=el.querySelector('svg');svg.innerHTML=components[b.component](b,p);svg.style.fontFamily=b.font || 'Anton';
        for(const label of svg.querySelectorAll('text')) {
          const width=label.getComputedTextLength();
          if(width>840) {
            const size=parseFloat(label.style.fontSize)*840/width;
            if(size<36)throw new Error('House label too dense for phone size: '+label.textContent);
            label.style.fontSize=`${size}px`;
          }
        }
      }
    }
  };
  window.visualMode=t=>plan.beats.some(b=>t>=b.start&&t<b.end)?'motion':'live';
  window.captionSuppressed=()=>false;
  window.renderFrame(0);
})();

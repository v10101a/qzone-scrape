"""Cut the museum's Frutiger-Aero chrome into transparent PNG stickers.

Loads the real pages, empties the content out of each piece of UI, then renders
it four times: backdrop alone, over the sky, over black, over white. The
black/white pair yields exact per-pixel alpha; the sky render yields the colour
the glass actually has on the site, which is baked into the piece's body so it
still reads as glass with nothing behind it.

Writes ui-stickers/ (baked) and ui-stickers/alpha/ (true translucency).
Drives the installed Google Chrome, so no playwright browser download is needed.
"""

import pathlib, io, numpy as np
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

WEB   = pathlib.Path("/Users/lh1783/web-scrape/web")
OUT   = WEB/"assets"/"ui-stickers"
ALPHA = OUT/"alpha"
for d in (OUT, ALPHA): d.mkdir(parents=True, exist_ok=True)
S = 3

# the pale lower half of the site's own sky — what the glass reads best against
WIN = (800, 600)   # 4:3 windows
BAR = 1.5          # title-bar zoom: text legible when the frame is used card-sized
DIA_URL = (17, 14)      # 黄钻 slot beside qzone2000.com (huangzuan_plain.png's native size)
DIA_SPACE = (30, 25)    # 黄钻 slot beside 我的空间 — a chunkier badge
LOC_SHIFT = 13          # pull the whole left group in by one CJK character (bar units)
SKY = "linear-gradient(180deg,#9cc4f5 0%,#c1d9fa 45%,#e0edfd 100%)"

PREP = """
document.head.appendChild(Object.assign(document.createElement('style'),{textContent:`
  body::before,body::after{display:none!important}
  *{animation:none!important;transition:none!important}
  ::-webkit-scrollbar{width:0!important;height:0!important;display:none!important}
`}));
document.body.style.background='transparent';
window.__bg=(css)=>{let t=document.getElementById('__bg');
  if(!t){t=document.createElement('style');t.id='__bg';document.head.appendChild(t);}
  t.textContent='html{background:'+css+'!important;background-attachment:fixed!important}';};
const PROPS=['visibility','background','boxShadow','borderColor','backdropFilter','webkitBackdropFilter'];
let touched=[];
window.__unIso=()=>{ touched.forEach(([n,saved])=>PROPS.forEach((p,i)=>n.style[p]=saved[i])); touched=[]; };
window.__iso=(sel)=>{
  window.__unIso();
  const el=document.querySelector(sel);
  const anc=new Set(); let p=el.parentElement; while(p){anc.add(p);p=p.parentElement;}
  const inside=new Set([el,...el.querySelectorAll('*')]);
  document.querySelectorAll('body, body *').forEach(n=>{
    if(inside.has(n)) return;
    touched.push([n, PROPS.map(p=>n.style[p])]);
    if(anc.has(n)){ n.style.background='none'; n.style.boxShadow='none';
      n.style.borderColor='transparent'; n.style.backdropFilter='none';
      n.style.webkitBackdropFilter='none'; }
    else n.style.visibility='hidden';
  });
};
window.__rect=(sel)=>{const e=document.querySelector(sel),r=e.getBoundingClientRect(),cs=getComputedStyle(e);
  return {x:r.x,y:r.y,w:r.width,h:r.height,r:parseFloat(cs.borderTopLeftRadius)||0};};
"ready";
"""

def rrect(size, box, rad, square_top=False):
    m = Image.new("L", size, 0); d = ImageDraw.Draw(m)
    x0,y0,x1,y1 = box
    rad = max(0, min(rad, (x1-x0)/2, (y1-y0)/2))
    d.rounded_rectangle([x0,y0,x1-1,y1-1], radius=rad, fill=255)
    if square_top and rad > 0: d.rectangle([x0,y0,x1-1,y0+rad], fill=255)
    return m

def slot_box(page, clip):
    """Where the empty 黄钻 slot lands inside the PNG just cut, in output pixels."""
    return page.evaluate("""({cx,cy,S}) => {
      const d=document.querySelector('.dia-slot'); if(!d) return null;
      const r=d.getBoundingClientRect();
      return [(r.x-cx)*S,(r.y-cy)*S,r.width*S,r.height*S].map(Math.round).join(','); }""",
      {"cx": clip["x"], "cy": clip["y"], "S": S})

def cut(page, sel, name, margin=60, hole=None, opaque=True):
    r = page.evaluate(f"window.__rect({sel!r})")
    clip = {"x":max(0,r["x"]-margin), "y":max(0,r["y"]-margin),
            "width":r["w"]+margin*2, "height":r["h"]+margin*2}
    def snap(bg, hide=False):
        page.evaluate(f"window.__bg({bg!r})")
        if hide: page.evaluate(f"document.querySelector({sel!r}).style.visibility='hidden'")
        page.wait_for_timeout(110)
        buf = page.screenshot(clip=clip)
        if hide: page.evaluate(f"document.querySelector({sel!r}).style.visibility='visible'")
        return np.asarray(Image.open(io.BytesIO(buf)).convert("RGB")).astype(np.float64)

    base, sky = snap(SKY, hide=True), snap(SKY)
    blk, wht  = snap("#000"), snap("#fff")

    a = np.clip(255.0 - (wht-blk).mean(axis=2), 0, 255)
    af = a[...,None]/255.0
    with np.errstate(divide="ignore", invalid="ignore"):
        col = np.where(a[...,None] > 2, (sky - base*(1-af))/np.maximum(af,1e-6), 0)
    col = np.clip(col, 0, 255)

    H,W = sky.shape[0], sky.shape[1]   # trust the real raster, not clip*S rounding
    if opaque:
        ox,oy = (r["x"]-clip["x"])*S, (r["y"]-clip["y"])*S
        body = rrect((W,H), (ox,oy,ox+r["w"]*S,oy+r["h"]*S), r["r"]*S)
        if hole:
            hr = page.evaluate(f"window.__rect({hole!r})")
            hx,hy = (hr["x"]-clip["x"])*S, (hr["y"]-clip["y"])*S
            hm = rrect((W,H), (hx,hy,hx+hr["w"]*S,hy+hr["h"]*S), r["r"]*S, square_top=True)
            body = Image.fromarray(np.minimum(np.asarray(body), 255-np.asarray(hm)))
        bm = np.asarray(body).astype(np.float64)
        out_col = np.where(bm[...,None] > 127, sky, col)      # glass baked inside the body
        out_a   = np.maximum(a, bm)
    else:
        out_col, out_a = col, a

    Image.fromarray(np.dstack([out_col,out_a]).astype(np.uint8),"RGBA").save(OUT/f"{name}.png")
    Image.fromarray(np.dstack([col,a]).astype(np.uint8),"RGBA").save(ALPHA/f"{name}.png")
    print(f"  {name}.png  {W}x{H}")
    return clip

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--force-color-profile=srgb"])

    # ============ QZone: the browser window ============
    pg = b.new_page(viewport={"width":1500,"height":1150}, device_scale_factor=S)
    pg.goto((WEB/"site"/"index.html").as_uri()); pg.wait_for_timeout(4000)
    pg.evaluate(PREP)
    pg.evaluate("""({W,H,Z,DW,DH,SH}) => {
      document.head.appendChild(Object.assign(document.createElement('style'),
        {textContent:'.viewer-bar{zoom:'+Z+'}'
          +'.dia-slot{display:inline-block;flex:none}'
          +'.viewer-loc{margin-left:-'+SH+'px}'}));
      document.querySelector('.topbar')?.remove();
      document.querySelector('.viewer').style.cssText+=';max-height:none;overflow:visible;padding:90px 0 0;align-items:flex-start';
      document.querySelector('.viewer-frame').style.cssText+=
        ';max-height:none;margin:0 auto;width:'+W+'px;height:'+H+'px';
      document.querySelector('#skinBg')?.remove();
      document.querySelector('#stageWrap').style.cssText+=';background:transparent;overflow:hidden;flex:1 1 auto';
      document.querySelector('.browser').style.cssText+=
        ';background:transparent;width:'+W+'px;min-width:'+W+'px';
      const bb=document.querySelector('.browser-body');
      bb.innerHTML=''; bb.style.cssText+=';background:transparent;height:'+H+'px';
      document.querySelector('.viewer-loc').innerHTML =     // empty slot keeps room for the 黄钻
        '<span class="dia-slot" style="width:'+DW+'px;height:'+DH+'px"></span><span>qzone2000.com</span>';
      const tools=document.querySelector('.viewer-tools');
      ['#randomBtn','#clearBtn','#editBtn'].forEach(q=>tools.querySelector(q)?.remove());
      document.querySelector('#marketToggle').textContent='我的空间';  // keeps its ▸ toggle caret
      window.__iso('.viewer-frame');
    }""", {"W": WIN[0], "H": WIN[1], "Z": BAR, "DW": DIA_URL[0], "DH": DIA_URL[1], "SH": LOC_SHIFT})
    pg.wait_for_timeout(500)
    cut(pg, ".viewer-frame", "browser-window-glass", 70)                     # frosted pane inside
    pg.evaluate("document.querySelector('.viewer-frame').style.background='transparent'")
    frame_clip = cut(pg, ".viewer-frame", "browser-frame", 70, hole="#stageWrap")  # cut-out interior
    bar_clip = cut(pg, ".viewer-bar", "titlebar", 50)
    slots = [("browser-frame", slot_box(pg, frame_clip)), ("titlebar", slot_box(pg, bar_clip))]

    pg.evaluate("document.querySelector('.viewer-loc').innerHTML='';")
    pg.wait_for_timeout(200)
    cut(pg, ".viewer-frame", "browser-frame-nourl", 70, hole="#stageWrap")
    cut(pg, ".viewer-bar", "titlebar-nourl", 50)
    # 我的空间 on the left (no dot, no slot), 装扮空间 + 分享 on the right
    pg.evaluate("""({DW,DH}) => {
      document.querySelector('.viewer-loc').innerHTML =
        '<span class="dia-slot" style="width:'+DW+'px;height:'+DH+'px"></span><span>我的空间</span>';
      document.querySelector('#marketToggle').textContent='装扮空间';
    }""", {"DW": DIA_SPACE[0], "DH": DIA_SPACE[1]})
    pg.wait_for_timeout(200)
    my_clip  = cut(pg, ".viewer-frame", "browser-frame-myspace", 70, hole="#stageWrap")
    myb_clip = cut(pg, ".viewer-bar", "titlebar-myspace", 50)
    slots += [("browser-frame-myspace", slot_box(pg, my_clip)),
              ("titlebar-myspace", slot_box(pg, myb_clip))]
    for n, box in slots:
        print(f"  ({n}: 黄钻 slot x,y,w,h = {box})")

    pg.evaluate("document.querySelector('.viewer-loc').innerHTML='';document.querySelector('.viewer-tools').innerHTML='';")
    pg.wait_for_timeout(200)
    cut(pg, ".viewer-frame", "browser-frame-blank", 70, hole="#stageWrap")
    cut(pg, ".viewer-bar", "titlebar-blank", 50)
    pg.close()

    # ============ Museum: deck, card, gels, drops ============
    pg = b.new_page(viewport={"width":1500,"height":1150}, device_scale_factor=S)
    pg.goto((WEB/"index.html").as_uri())
    pg.wait_for_selector(".cell", timeout=25000); pg.wait_for_timeout(2500)
    pg.evaluate(PREP)

    for sel, name, m in [("#nav-qzone","gel-pill",34), ("#nav-archive","gel-pill-on",34),
                         ("#random","gel-dice",34), (".search","search-pill",34),
                         ("#f-hue","hue-drops",34), ("#f-type","tab-row",34)]:
        pg.evaluate(f"window.__iso({sel!r})"); pg.wait_for_timeout(150)
        cut(pg, sel, name, m)

    pg.evaluate("""
      window.__unIso();
      const g=document.querySelector('.grid'), c=g.querySelector('.cell');
      document.querySelector('#sentinel')?.remove();
      g.appendChild=()=>null;                       // stop the infinite-scroll refilling the grid
      [...g.children].forEach(n=>{if(n!==c)n.remove();});
      c.innerHTML=''; c.style.cssText+=';width:260px;height:260px;aspect-ratio:auto';
      g.style.cssText+=';display:block;padding:60px';
      window.__iso('.cell');
    """)
    pg.wait_for_timeout(400)
    cut(pg, ".cell", "card-glass", 46)
    pg.evaluate("""document.head.appendChild(Object.assign(document.createElement('style'),{textContent:
      '.cell{border-color:rgba(110,175,250,.9)!important;box-shadow:inset 0 1px 0 #fff,0 12px 26px rgba(22,100,175,.3),0 0 0 1px #2f7fe6,0 0 18px rgba(55,130,240,.5)!important}'}));""")
    pg.wait_for_timeout(250)
    cut(pg, ".cell", "card-glass-glow", 46)

    pg.evaluate("""({W}) => {
      window.__unIso();
      document.querySelector('.brand').innerHTML='';
      document.querySelector('.topnav').innerHTML='';
      document.querySelector('.filters')?.remove();
      document.querySelector('.topbar').style.cssText+=';width:'+W+'px;margin:0 auto;position:static';
      window.__iso('.topbar');
    }""", {"W": WIN[0]})
    pg.wait_for_timeout(300)
    cut(pg, ".topbar", "topbar-deck", 50)

    pg.evaluate("""({W,H}) => {
      window.__unIso();
      const d=document.querySelector('#detail'); d.hidden=false;
      d.querySelector('.detail-scrim')?.remove();
      const c=d.querySelector('.detail-card');
      c.innerHTML=''; c.style.cssText+=';width:'+W+'px;height:'+H+'px;max-width:none;max-height:none';
      window.__iso('.detail-card');
    }""", {"W": WIN[0], "H": WIN[1]})
    pg.wait_for_timeout(450)
    cut(pg, ".detail-card", "window-frosted", 70)
    pg.close()
    b.close()
print("done ->", OUT)

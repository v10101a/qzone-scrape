# Tencent CDN map — where the URLs come from

How the QZone 装扮 mall was actually wired, which URLs survive, and how to find more.
Everything marked **LIVE** was re-verified 2026-08-17 by direct fetch.

---

## 1. The one-paragraph answer

There is no single "API" to point at. The mall was a **three-layer system**, and each layer
lives on a different host with a different lifetime:

| Layer | Example | Alive today? |
|---|---|---|
| **Page** — the HTML you browsed | `mall.qzone.qq.com/...` | ✗ dead (host 503s) |
| **Catalog** — JSONP data files on the static CDN | `imgcache.qq.com/qzone/mall/static/json/itemlist_51_1_v5.json` | ✓ **LIVE** |
| **Assets** — the actual gifs/swf/ani | `qzonestyle.gtimg.cn/qzone/space_item/orig/5/21_bg.jpg` | ✓ **LIVE** |

The **page** is gone, so you can't "browse to" anything. But the page was only ever a thin
shell: it fetched the catalog JSONP, read item ids out of it, and computed asset URLs with a
formula. Both of those bottom layers are static files on a CDN that Tencent never purged.

So the scraping model is: **skip the dead page, read the catalog directly, compute the asset
URLs yourself.** The formula for that last step is what `malllib.js` gives you.

### Worked example: one floaty, end to end

This is where the links come from. Nothing here is guessed — every step is a real fetch.

**Step 1 — ask the catalog for a category.** 漂浮物 (floaty) is mall category `32`. The URL is
built by hand from the family pattern in §5, `itemlist_<cat>_<page>_v5.json`:

```
GET https://imgcache.qq.com/qzone/mall/static/json/itemlist_32_1_v5.json     -> 7,851 bytes
```

**Step 2 — unwrap it.** The bytes start `1f 8b` = **gzipped**, and once inflated the text is
**GBK**, and the whole thing is **JSONP** wrapped in `g_mallStaticWeb.getItemData(`. Strip all
three and you get 24 records, every one with `Ftype_id:'5'` — confirming cat 32 is exactly the
floaty type. First few:

```
  45748  花城之美          45583  明日之星          45584  水之缘
  45354  可爱时候          45355  美味关系          45178  甜蜜之夏
```

**That is where item ids come from.** No guessing — you read them out of a live file.

**Step 3 — compute the shard.** `getPrePaths` in `malllib.js` (§2) says the directory is
`id % 16`:

```
45748 % 16 = 4          10007 % 16 = 7
```

**Step 4 — build the asset URL.** Floaty items are *numbered animation frames*, so the pattern
is `<id>_<n>.gif`, counting up until you hit a 404:

```
https://qzonestyle.gtimg.cn/qzone/space_item/orig/4/45748_1.gif   200   1,737 B  ✓
https://qzonestyle.gtimg.cn/qzone/space_item/orig/4/45748_2.gif   200   1,063 B  ✓
https://qzonestyle.gtimg.cn/qzone/space_item/orig/4/45748_3.gif   200     935 B  ✓
https://qzonestyle.gtimg.cn/qzone/space_item/orig/4/45748_4.gif   404     816 B  ← stop
```

Three frames. The 404 is the **constant 816-byte** body, which is how the crawler knows to stop
counting rather than needing a manifest.

Same thing for id `10007` (already in `web/library/floaty/` as `_1/_2/_3.gif`, so this
independently confirms the recovered library):

```
https://qzonestyle.gtimg.cn/qzone/space_item/pre/7/10007.gif      200   3,787 B  ← thumbnail
https://qzonestyle.gtimg.cn/qzone/space_item/orig/7/10007_1.gif   200     709 B
https://qzonestyle.gtimg.cn/qzone/space_item/orig/7/10007_2.gif   200     460 B
https://qzonestyle.gtimg.cn/qzone/space_item/orig/7/10007_3.gif   200   1,097 B
https://qzonestyle.gtimg.cn/qzone/space_item/orig/7/10007_4.gif   404     816 B  ← stop
```

**The whole chain:** `category number` → catalog JSON → `Fitem_id` → `% 16` → `orig/<shard>/<id>_<n>.<ext>`.
The only per-type variation is that last filename shape (§4) — skins are `_bg`/`_top`, cursors
are a bare `.ani`, floaties are numbered frames.

---

## 2. Where `malllib.js` fits

`malllib.js` is the **client-side library the dead mall page loaded**. It is still sitting on
the CDN even though the page that used it is gone. It matters because it contains the
*URL-building functions* — the rules that turn an item id into an asset path.

```
https://imgcache.qq.com/qzone/mall/v6/js/lib/malllib.js     LIVE, 34 KB
```

It is minified onto ~108 lines and built on **QZFL** (`QZFL.*`), Tencent's in-house JS
framework — think their jQuery. Roughly the first half of the file is generic QZFL utilities
(`QZFL.lang`, `QZFL.string`, `QZFL.media`, `QZFL.widget`); the mall-specific code lives in the
`M.*` namespace in the second half.

### Namespaces, by frequency

| Namespace | What it is | Useful to you? |
|---|---|---|
| `M.util` | JSONP loader + stats pings | ✓ shows how catalogs were fetched |
| `M.items` | the item model — add/remove/search, **path building** | ✓✓ **the payload** |
| `M.db` / `M.CP` / `M.FP` | three-tier local cache (page / frame / top) | ✗ browser-local only |
| `M.key` | localStorage **key namer** (prefix `mall_`) | ✗ *not* URLs — see trap below |
| `M.shopLib` | the live-preview "shop" that renders your 空间 | ~ shows the save format |
| `M.suits` | 套装 (bundle) add/remove | ~ confirms bundles are id lists |
| `QZONE.FP` | msgbox / loading UI | ✗ |

### ⚠️ The trap: `_KEY_HASH` / `M.key` is **not** a URL table

It reads like one and it is not. It's the localStorage key namer:

```js
M.key=(function(){
  var _PREFIX='mall_';
  var _KEY_HASH={ITEM_FILE:{'mix':'item_file_mix','mix_full':'item_file_mix'},
                 TOPIC_FILE:'topicFile', ITEM:'', SUIT_HAS_ITEM:'suitHasItem',
                 DRESS_UP_HISTORY:'dressUpHistory', SAVED_HISTORY:'savedHistory',
                 COMM_DATA:'commData', DNA_KEY:'dnaKey'};
  ...
  ITEM_FILE:function(key,opt){
    return opt.isFull ? _KEY_HASH[key][opt.type+'_full'] || 'item_file_'+opt.type+'_full'
                      : _KEY_HASH[key][opt.type]         || 'item_file_'+opt.type;}
  ...
  res=_PREFIX+res; return res;                    // -> "mall_item_file_1"
```

`ITEM_FILE` produces strings like `mall_item_file_1`. Those are **cache keys**, not paths.
Chasing them at the CDN gets you nothing.

### ✓ The real prize: `M.items.getPrePaths`

This is the actual URL builder, verbatim from the live file:

```js
getPrePaths:function(itemno){
  var _p = '/qzone/space_item/pre/' + itemno%16 + '/';
  return { full:  _p + itemno + '.gif',       // catalog thumbnail
           mini:  _p + itemno + '_1.gif',     // larger preview (despite the name)
           other: _p + itemno + '_1.gif' };
}
```

Three things you can only learn by reading this:

1. **The `%16` shard is real and it is written down here.** Not a guess — this is the source.
2. There is a **`_1.gif` variant** alongside the plain `.gif`. In practice `_1` is the *bigger*
   image (id 21: `.gif` = 3.5 KB, `_1.gif` = 14 KB), so `mini` is a misnomer in Tencent's own code.
3. It's a **host-relative** path, which is why it works on more than one CDN host (see §4).

Verified 8/8 across item types today — skin `21`, suit `45917`, 信纸 `85632`, flower `38542`,
each in both `.gif` and `_1.gif` form, all HTTP 200.

### `M.util.loadJson` — how catalogs were fetched

```js
M.util.loadJson({ url:'/qzone/mall/static/mallv6/magic_cube_'+mallid+'.js',
                  callbackName:'_Callback',
                  onSuccess:function(data){...} });
```

Plain JSONP: inject a `<script>`, the file calls a global. **This is why every catalog file is
wrapped in a function call rather than being bare JSON** — you must strip the wrapper before
parsing. The callback name differs per family (see §5), and it's the fastest way to identify an
unknown file: fetch it and look at the first token.

### `M.items.getSavedItemList` — the save format

```js
items = saved.split('|');  item = items[i].split('_');
tmp.typeid=item[0]; tmp.id=item[1];
tmp.style={x:item[2], y:item[3], z:item[4], w:item[5], h:item[6], f:item[7]};
```

A whole 装扮 is `type_id_x_y_z_w_h_flag`, pipe-joined. Note the **order is x, y, z, w, h** in
this v6 file. If you ever recover a saved-scenario string, this decodes it.

### Other live loaders worth grepping

Same trick, different files. Grep each for quoted strings containing `.json`, `/json/`, `cgi`, `.swf`:

```
imgcache.qq.com/qzone/mall/v6/js/lib/malllib.js     ← the one above
imgcache.qq.com/qzone/mall/v6/js/home.js            LIVE  27 KB
imgcache.qq.com/qzone/mall/v5/js/mall.js            LIVE  76 KB  (largest)
imgcache.qq.com/qzone/mall/v5/js/mall_item.js       LIVE  17 KB
imgcache.qq.com/qzone/mall/static/home/home.js      LIVE  76 KB
imgcache.qq.com/qzone/mall/static/mallv6/home_v6.js LIVE 120 KB
imgcache.qq.com/qzone/mall/static/qxty/priority.js  LIVE  11 KB
```

---

## 3. The tree

```
imgcache.qq.com  ─┬─ /qzone/
qzonestyle.gtimg.cn│   (these two hosts are INTERCHANGEABLE for /qzone/space_item/*
 (same bytes)      │    — byte-identical responses; qzs.qq.com is NOT)
                   │
                   ├── space_item/                    ← THE ASSETS
                   │   ├── pre/<id%16>/<id>.gif       LIVE  catalog thumbnail
                   │   │   └─────────  <id>_1.gif     LIVE  bigger preview
                   │   ├── orig/<id%16>/<id>*.<ext>   LIVE  the real asset
                   │   │     skin    -> <id>_bg.jpg + <id>_top.jpg
                   │   │     pendant -> <id>.gif        (animated)
                   │   │     floaty  -> <id>_1.gif … _N.gif
                   │   │     cursor  -> <id>.ani        (RIFF)
                   │   │     player  -> <id>.swf
                   │   │     frame   -> <id>/mod_wrap_hd.css + PNGs
                   │   ├── mallpic/                   archive only  (124 urls)
                   │   ├── packitem/                  archive only
                   │   └── mallv6/index/pic_cube/     archive only  cubeN_M.gif promo art
                   │
                   └── mall/                          ← THE CATALOG + THE CODE
                       ├── static/
                       │   ├── json/                  ★ THE CATALOG (see §5)
                       │   ├── htm/itemlist_<c>_<p>.htm      archive only — rendered listings
                       │   ├── mallv6/magic_cube_<mallid>.js LIVE  JSONP `_Callback`
                       │   ├── home/home.js · mallv6/home_v6.js · qxty/ · viphome/
                       │   └── mallitem/ · vip_portal/ · team/ · ri/ · giftitem/
                       ├── v5/js/{mall,mall_item,suit,style_data}.js   LIVE
                       ├── v6/js/{home,util}.js · v6/js/lib/malllib.js LIVE
                       └── v6/_default.js                              LIVE

imgcache.qq.com ─── /club/item/decorate/          ← SECOND, NEWER decoration tree
                    ├── res/static/<shard>/<id>/<id>_thm.png  LIVE  (diff. sharding!)
                    │        _eff.png / newthm.png -> 302 = gone
                    ├── webdec/json_v2/<type>/<page>_<type>.js  LIVE **type 1 only**
                    │        types 2/4/5/6 now 302
                    └── webdec/{dec_sort,auto_sort}.html?category=…  archive only

mall.qzone.qq.com ── /cgi-bin/… · /fcg-bin/…      ← THE API — ALL DEAD (503)
pay.qzone.qq.com  ── /fcg-bin/fcg_mall_save_v5    ← DEAD
```

**Read signals like this:** `200` + a body that isn't exactly **816 bytes** = real hit.
`404` returns a constant ~816 B page. `302` = the file is gone but the CDN redirects — treat as
a miss, never follow it. There are **no directory listings anywhere** (every bare dir 404s), which
is exactly why enumeration has to come from CDX or from reading the JS.

---

## 4. Asset URLs — the recipe

Given any item id, both hosts work; pick either:

```
https://qzonestyle.gtimg.cn/qzone/space_item/pre/{id % 16}/{id}.gif      thumbnail
https://qzonestyle.gtimg.cn/qzone/space_item/pre/{id % 16}/{id}_1.gif    bigger preview
https://qzonestyle.gtimg.cn/qzone/space_item/orig/{id % 16}/{id}…        real asset
https://imgcache.qq.com/qzone/space_item/pre/{id % 16}/{id}.gif          identical bytes
```

**Send an `Accept` header that excludes webp** or the CDN transcodes your GIFs (kills animation)
and PNGs:

```
Accept: image/png,image/gif,image/*;q=0.9,*/*;q=0.8
```

The `pre` → `orig` swap is the trick: the mall preview path and the real asset path differ only
in that one segment. `pre` is uniform (always `.gif`), `orig` varies by type — so use `pre` to
*test whether an id exists*, then go to `orig` for the goods.

Worked example, id `45917`: `45917 % 16 = 13` → `pre/13/45917.gif` (4,930 B ✓)
and `pre/13/45917_1.gif` (10,132 B ✓).

---

## 5. Catalog URLs — the JSONP families

All under `https://imgcache.qq.com/qzone/mall/static/json/`. All **GBK-encoded** (not UTF-8) and
some are gzipped. Each is wrapped in a different callback, which is how you tell them apart:

| File | Callback wrapper | Contents | Status |
|---|---|---|---|
| `itemlist_<cat>_<page>_v5.json` | `g_mallStaticWeb.getItemData` | main 装扮 catalog, 24/page, server caps ~60 pages | LIVE |
| `itemlist_new_mall_normal.json` | `_Callback` | default/landing listing, 17 KB | **LIVE** |
| `mallpaper_<cat>_<page>.json` | `mallpaperdealdata` | type 21 信纸/壁纸 — **only cat 259 exists**, pages ≥20 | **LIVE** |
| `flower_<cat>_<page>_v5.json` | `flowerlist` | type 23 花 w/ prices — only cat 427, only `_v5` | **LIVE** |
| `special_topic_<n>.json` | `special_callback` | **curated editorial topics** — Ftitle, Fcontent curator prose, Fauthor QQ, Fnick | **LIVE** |
| `gift_…` / `ogift_…` | ? | appear truncated in CDX; no naming guess resolved | unknown |

Record fields are consistent across families: `Fitem_id`, `Fitem_name` (中文), `Fprice` /
`Fvip_price`, `Ftype_id`, `Fupload_time`, `Fdesc` (asset ext — but a packed int for `mallpaper`),
`Fitem_remark` (套装 piece list), `Fitem_tag` (色系/主题/性别).

`special_topic_1.json` is the odd one out and the most interesting: it's human-written curatorial
text, not machine metadata — `Ftitle:'校园LOMO风，狂暴来袭！'`, a paragraph of `Fcontent`, and a
credited author (`Fnick:'空间精灵'`).

### Parsing gotchas
- **GBK**, so `.decode('gbk')` — UTF-8 will mojibake the 中文.
- Some responses are **gzipped** regardless of headers; sniff for `\x1f\x8b`.
- Records are formatted `{\n\tFitem_id:'…'` — a regex anchored on `{` alone will miss them.
- Strip the JSONP wrapper before any JSON parse; these are not valid JSON as served.

---

## 6. The dead API (documented so you stop trying)

`mall.qzone.qq.com` returns 503 — the whole host is retired. Recorded here because the names map
the feature surface, and because archived *responses* may still be recoverable via Wayback even
though the endpoints are dead:

```
/cgi-bin/cgi_search_item?            item search (the post-2009 catalog gap lives behind this)
/cgi-bin/cgi_diy_save_scenario?      save a 装扮 layout
/cgi-bin/cgi_show_useritem?type=N    a user's owned items
/cgi-bin/cgi_qzone_mall_buy?         purchase
/cgi-bin/cgi_scenario_admin?item_list=
/cgi-bin/cgi_show_userflower · cgi_show_userbig
/fcg-bin/v3/fcg_get_usertask   ·  /cgi-bin/v3/cgi_mall_sign
pay.qzone.qq.com/fcg-bin/fcg_mall_save_v5?change_scenario=0&cbf=_Callback
```

All of these were **login-gated** (`g_tk` + cookie), so Wayback never crawled authenticated
responses. Asset bytes are fully recoverable; per-user *arrangement* generally is not.

---

## 7. Finding more — the method

In yield order:

**1. Mine loader JS for builder functions.** Highest yield by far. You want the *template*, not a
URL. Fetch the files in §2 and grep for quoted strings:

```bash
grep -ohE "['\"][^'\"]*(cgi-bin|fcg-bin|/json/|\.json|space_item|/static/)[^'\"]*['\"]" *.js | sort -u
```

That single command is what produced `space_item/pre/`, `magic_cube_`, `top_picad/adpic_`, and the
whole CGI list above.

**2. CDX prefix-enumerate, then collapse digits → `N`.** Turns one known URL into a map of
*file families* and *sibling directories*:

```
http://web.archive.org/cdx/search/cdx?url=<prefix>&matchType=prefix&fl=original&collapse=urlkey&limit=20000
```

⚠️ CDX emits **both `host` and `host:80`** forms. Strip the port before parsing or your sibling
counts are garbage. Add `filter=original:.*\.js$` to find loaders specifically.

Note that CDX also surfaces **typo directories** from other people's web pages — under
`space_item/` you'll see `oirg/`, `oring/`, `irog/`, `orij/`, `0rig/`. Those are misspellings in
blog posts, not real paths. Real siblings there are `pre/`, `orig/`, `mallpic/`, `packitem/`.

**3. Ladder-probe** the shape you found across catid / page / `vN`. This is how we established
that `mallpaper` exists only for cat 259, and `flower` only for `_v5` (`v1`–`v8` all 404).

**Tool:** `recon.py` implements all three as `tree` / `climb` / `ladder` subcommands. Currently in
the session scratchpad, not yet in `pipeline/`.

---

## 8. The same pattern elsewhere

The thing that makes QZone scrapable is a **shape**, not a Tencent quirk:

> a public **catalog file** (ids + a name/revision field) + a **deterministic path formula**
> from that field to the original asset, on a CDN nobody ever purged.

Anywhere that shape exists, you get a whole library. Probed 2026-08-17:

### ✓ Habbo Hotel — the strongest match, fully verified

The catalog is a public, unauthenticated file:

```
https://www.habbo.com/gamedata/furnidata_json/1     LIVE  9.6 MB
    -> roomitemtypes.furnitype  17,200 records
    -> wallitemtypes.furnitype     835 records
    each: {id, classname, revision, category, name, description, xdim, ydim, partcolors…}
```

`classname` + `revision` feed straight into the asset path:

```
https://images.habbo.com/dcr/hof_furni/{revision}/{classname}.swf        ✓ 200
https://images.habbo.com/dcr/hof_furni/{revision}/{classname}_icon.png   ✓ 200
```

Verified: `shelves_norja` rev `61856` → 6,050 B SWF + 303 B icon. The `revision` segment is
**required** — dropping it 404s, which is the same "shard segment" idea as QZone's `%16`.
`.nitro` (the modern Unity format) 404s on this build; SWF is what's there.

Clothing — the direct QQ秀 analog — is a second catalog:

```
https://www.habbo.com/gamedata/figuredata/1     LIVE  425 KB XML
    all clothing parts + the color palettes, by body slot
```

And Habbo exposes a **server-side compositor** that renders a full avatar from a figure string:

```
https://www.habbo.com/habbo-imaging/avatarimage?figure=hr-100-7.hd-180-2.ch-215-66.lg-270-82.sh-290-80&size=l   ✓ 200
```

That is worth a close look for the QQShow side of this project — it's the thing our layer
compositor is reimplementing by hand, done as a URL.

⚠️ `www.habbo.com` is behind a WAF that returns **463** to a bare `curl`. Send a full browser
`User-Agent` and it returns 200. `images.habbo.com` doesn't care.

### ✓ Neopets — live, deterministic, no catalog

```
https://images.neopets.com/items/{name}.gif     ✓ 200   e.g. mall_bg_faeriecity.gif
```

Paths are by *name*, not id, and the directory 403s — so there's no enumeration from the CDN
itself. Get the name list from **Dress to Impress** (`impress.openneo.net`, live), a
community item database that has been cataloguing Neopets wearables for ~20 years.

### ✓ GeoCities — mirrors preserve original paths

`oocities.org` and `geocities.restorativland.org` are both live and keep the original
`/<neighborhood>/<street>/<number>/` structure, so old URLs translate mechanically. The
Archive Team torrent dump (~900 GB) is the complete version if you want it offline.

### ✗ Dead from here
Club Penguin (`media1.clubpenguin.com` — DNS gone), Cyworld (the Korean minihompy, the closest
cultural analog to QZone — no DNS from this network; may need a KR route), Renren/校内
(`img.xiaonei.com` gone, host 502s), Baidu 空间, iGoogle themes, `cdn.winamp.com`,
`maplestory.io` (500s — community API, may just be down rather than dead).

### Where to look next
The pattern predicts its own hunting ground: any **game or social platform with a client that
had to download an asset manifest**. The manifest is usually still served unauthenticated
because it predates anyone caring. Candidates not yet probed: Gaia Online, Stardoll, Poptropica,
Webkinz, Toontown, Ameba Pigg / mixi (JP), 51.com and 开心网 (CN), MSN/WLM winks and emoticon packs,
Nokia/Symbian theme portals, Yahoo Widgets.

---

## 9. Open threads

- `gift_` / `ogift_` families — CDX shows them truncated; need a wider pull to get real filenames.
- `mallpaper` swept only cats 250–270; only 259 hit. Worth a wider sweep.
- The `res/static/<shard>/…` sharding rule for the `club/item/decorate` tree is **not** `%16` —
  observed ids are all multiples of 10 with shard `0`. The rule is presumably written down in
  `webdec/js/{dec_sort,new_sort,zb}.js`, which nobody has read yet.
- `special_topic_<n>` — only `_1` confirmed; ladder it.

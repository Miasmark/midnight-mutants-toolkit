/* Midnight Mutants cartridge editor -- browser side.
 *
 * The server sends the same three things the game itself uses to draw a room:
 * the 1000-byte character grid, the area bank's character set, and the palette
 * block. Rendering here from those bytes means the editor shows exactly what
 * the cartridge will, rather than a second interpretation that could drift.
 */
'use strict';

const ITEMS = {
  1:'cross', 2:'crypt key', 3:'necklace', 4:'heart', 5:'plasmic pumpkin',
  6:'red potion', 7:'blue potion', 8:'diamond', 9:'lantern', 11:'screen gate',
  12:'knife', 13:'axe', 14:'blaster', 15:'mega blaster'
};
// Creature kinds the special-actor slot can place. Names come from the
// bestiary, not from sprite order -- the two do not agree.
const KINDS = {
  0:'zombie', 1:'Bignose', 2:'Longneck', 3:'Hunchback', 4:'kind 4', 5:'kind 5',
  6:'Pumpkin-head', 7:'Headless', 8:'Lab-pair zombie', 9:'Dr Evil zombie',
  10:'kind 10 (inert)', 11:'kind 11 (inert)', 12:'Humpback'
};
const CHAR_W = 8, CHAR_H = 16, BANDS = 10, COLS = 100;

let rooms = [], room = null, grid = null, chars = null, pal = null;
let tool = 'paint', sel = 0x00, zoom = 3, drawing = false, dragging = false;
let ink = 1, palBand = 5, ntsc = null, pxdraw = false;   // tile + colour editors
let src = null, spritePages = null, spriteNames = {};    // what the Draw tab edits
const GREY = [[120,116,140],[188,184,205],[245,243,250]];
const rgb = c => `rgb(${c[0]},${c[1]},${c[2]})`;

const $ = s => document.querySelector(s);
const hex = (v, n = 2) => '$' + (v >>> 0).toString(16).toUpperCase().padStart(n, '0');
const b64 = s => { const b = atob(s), a = new Uint8Array(b.length);
  for (let i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a; };

async function api(path, body) {
  const opt = body ? {method:'POST', headers:{'Content-Type':'application/json'},
                      body:JSON.stringify(body)} : {};
  const r = await fetch(path, opt);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || 'request failed');
  return j;
}

/* Optional sections use this: a panel that depends on a newer server should
   degrade to a note rather than throwing and leaving the whole tab empty. */
let staleWarned = false;
async function apiSoft(path) {
  try {
    return await api(path);
  } catch (err) {
    if (!staleWarned) {
      staleWarned = true;
      toast('Some panels need a newer server — restart the editor.', 'bad');
    }
    return null;
  }
}

function toast(msg, kind) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'toast ' + (kind || ''); t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3800);
}

/* ------------------------------------------------------------------ rooms */
async function loadRooms() {
  const d = await api('/api/rooms');
  rooms = d.rooms;
  $('#file').textContent = d.file;
  const v = (d.version || 'ntsc').toUpperCase();
  $('#ver').textContent = v;
  $('#ver').classList.toggle('pal', v === 'PAL');
  drawRoomList();
  if (rooms.length) selectRoom(rooms[0].kind);
}

/* Adding or clearing an item changes the sidebar dot and the searchable label,
   so pull that one room's summary again rather than reloading everything. */
async function refreshRoomEntry(kind) {
  const d = await api('/api/rooms');
  rooms = d.rooms;
  await selectRoom(kind);
  drawRoomList();
}

function drawRoomList() {
  const q = $('#filter').value.trim().toLowerCase();
  const box = $('#rooms'); box.innerHTML = '';
  let region = null;
  for (const r of rooms) {
    const label = r.name + ' ' + r.region + (r.item ? ' ' + (ITEMS[r.item.id]||'') : '');
    if (q && !label.toLowerCase().includes(q)) continue;
    if (r.region !== region) {
      region = r.region;
      const h = document.createElement('div');
      h.className = 'reg'; h.textContent = region; box.appendChild(h);
    }
    const el = document.createElement('div');
    el.className = 'room' + (room && room.kind === r.kind ? ' on' : '');
    el.innerHTML = `<span class="dot ${r.item ? '' : 'none'}"></span><span>${r.name}</span>` +
                   `<span class="tag">${r.segments}seg${r.dark ? ' · dark' : ''}</span>`;
    el.onclick = () => selectRoom(r.kind);
    box.appendChild(el);
  }
}

async function selectRoom(kind) {
  room = await api('/api/room/' + kind.toString(16));
  grid = b64(room.grid);
  chars = b64(room.charset);
  pal = room.palette;
  $('#empty').hidden = true;
  // the toggle is only meaningful where the area is flagged dark
  $('#darkwrap').hidden = !room.dark;
  if (!room.dark) $('#asplayed').checked = false;
  drawRoomList(); render(); drawTiles(); showProps(); showExits(); showActors();
  showPixels(); showColours(); showItems(); showBosses();
  showProps2(); showDoors(); showTexts(); showMusic();
}


/* Where an exit tile actually goes. Three events name no destination: they
   defer to the room's own header, and the north and south tables are per
   segment, so the answer depends on which column the tile sits in. */
function exitTarget(ev, col) {
  if (!ev) return null;
  if (ev.dest !== undefined) return {to: ev.dest, how: 'fixed'};
  if (ev.pair) return {to: null, how: 'paired ' + ev.pair.map(hex).join(' / ')};
  const seg = Math.floor(col / 20);
  if (ev.via === 'west')  return {to: room.west, how: 'header west'};
  if (ev.via === 'north') return {to: (room.north || [])[seg], how: 'north table, seg ' + seg};
  if (ev.via === 'south') return {to: (room.south || [])[seg], how: 'south table, seg ' + seg};
  return null;
}

/* --------------------------------------------------------------- painting */
function glyphLine(ch, ln) {                 // two bytes = eight 2-bit pixels
  const o = (ch * CHAR_H + ln) * 2;
  return [chars[o], chars[o + 1]];
}

function render() {
  if (!room) return;
  const w = room.width * CHAR_W, h = BANDS * CHAR_H;
  const off = render.buf || (render.buf = document.createElement('canvas'));
  off.width = w; off.height = h;
  const ctx = off.getContext('2d');
  const img = ctx.createImageData(w, h);
  const px = img.data;

  const dark = $('#asplayed').checked && room.palette_dark;
  const shown = dark ? room.palette_dark : pal;
  for (let band = 0; band < BANDS; band++) {
    const colours = shown[band];
    for (let col = 0; col < room.width; col++) {
      const ch = grid[band * COLS + col];
      if (!ch) continue;
      for (let ln = 0; ln < CHAR_H; ln++) {
        const y = band * CHAR_H + ln, pair = glyphLine(ch, ln);
        for (let half = 0; half < 2; half++) {
          const byte = pair[half];
          if (!byte) continue;
          for (let i = 0; i < 4; i++) {
            const v = (byte >> (6 - 2 * i)) & 3;
            if (!v) continue;                       // index 0 is transparent
            const c = colours[v - 1];
            const p = (y * w + col * CHAR_W + half * 4 + i) * 4;
            px[p] = c[0]; px[p+1] = c[1]; px[p+2] = c[2]; px[p+3] = 255;
          }
        }
      }
    }
  }
  ctx.putImageData(img, 0, 0);

  const view = $('#view');
  view.width = w * zoom; view.height = h * zoom;
  const v = view.getContext('2d');
  v.imageSmoothingEnabled = false;
  v.drawImage(off, 0, 0, view.width, view.height);

  if ($('#showseg').checked) {
    v.strokeStyle = 'rgba(232,132,60,.55)'; v.lineWidth = 1;
    v.font = '10px monospace'; v.fillStyle = 'rgba(232,132,60,.9)';
    room.seg_offsets.forEach((o, i) => {
      const x = o * CHAR_W * zoom + .5;
      v.beginPath(); v.moveTo(x, 0); v.lineTo(x, view.height); v.stroke();
      v.fillText('seg ' + i + '  ' + hex(room.ids[i]), x + 4, 12);
    });
  }
  if ($('#showgrid').checked) {
    v.strokeStyle = 'rgba(255,255,255,.10)'; v.lineWidth = 1;
    for (let c = 0; c <= room.width; c++) {
      const x = c * CHAR_W * zoom + .5;
      v.beginPath(); v.moveTo(x, 0); v.lineTo(x, view.height); v.stroke();
    }
    for (let b = 0; b <= BANDS; b++) {
      const y = b * CHAR_H * zoom + .5;
      v.beginPath(); v.moveTo(0, y); v.lineTo(view.width, y); v.stroke();
    }
  }
  // Terrain overlays. The grid holds a character number and the property table
  // is indexed by (cell >> 1), so two adjacent characters always share one
  // entry: bits 0-1 are the collision class, bit 2 marks water, bit 7 a
  // scripted tile -- which the collision test never reaches, AND #$03 only.
  const wantCol = $('#showcol').checked, wantWater = $('#showwater').checked;
  $('#collegend').hidden = !(wantCol || wantWater || $('#showexits').checked);
  if ((wantCol || wantWater) && room.props) {
    const cw = CHAR_W * zoom, chh = CHAR_H * zoom;
    for (let band = 0; band < BANDS; band++) {
      for (let col = 0; col < room.width; col++) {
        const cell = grid[band * 100 + col];
        if (!cell) continue;
        const p = room.props[(cell >> 1) & 0x7F];
        if (p === undefined) continue;
        const x = col * cw, y = band * chh;
        if (wantWater && (p & 0x04) && !(p & 0x80)) {
          v.fillStyle = 'rgba(64,164,232,.42)';
          v.fillRect(x, y, cw, chh);
        }
        if (!wantCol) continue;
        if (p & 0x80) {                            // scripted: an event tile
          v.fillStyle = 'rgba(196,92,232,.34)';
          v.fillRect(x, y, cw, chh);
          continue;
        }
        const k = p & 3;
        if (!k) continue;
        v.fillStyle = 'rgba(232,60,60,.38)';
        if (k === 3) {
          v.fillRect(x, y, cw, chh);
        } else {
          v.beginPath();
          if (k === 1) {                           // blocks the lower right
            v.moveTo(x + cw, y); v.lineTo(x + cw, y + chh); v.lineTo(x, y + chh);
          } else {                                 // blocks the upper left
            v.moveTo(x, y); v.lineTo(x + cw, y); v.lineTo(x, y + chh);
          }
          v.closePath(); v.fill();
        }
      }
    }
  }

  // Exit layer: the scripted tiles, tinted and labelled with where they lead.
  if ($('#showexits').checked && room.props && room.events) {
    const cw = CHAR_W * zoom, chh = CHAR_H * zoom;
    const seen = [];
    for (let band = 0; band < BANDS; band++) {
      for (let col = 0; col < room.width; col++) {
        const cell = grid[band * 100 + col];
        if (!cell) continue;
        const p = room.props[(cell >> 1) & 0x7F];
        const ev = room.events[String(p)];
        if (!ev) continue;
        const x = col * cw, y = band * chh;
        const tone = ev.kind === 'boss' ? 'rgba(232,60,60,.45)'
                   : ev.kind === 'hazard' ? 'rgba(232,140,40,.45)'
                   : ev.kind === 'win' ? 'rgba(232,208,60,.5)'
                   : ev.kind === 'well' ? 'rgba(64,164,232,.45)'
                   : 'rgba(96,220,140,.45)';
        v.fillStyle = tone; v.fillRect(x, y, cw, chh);
        v.strokeStyle = 'rgba(255,255,255,.35)'; v.lineWidth = 1;
        v.strokeRect(x + .5, y + .5, cw - 1, chh - 1);
        // one label per contiguous run, so a wide doorway is not written over
        const key = band + ':' + p;
        if (!seen.includes(key)) {
          seen.push(key);
          const t = exitTarget(ev, col);
          let txt = ev.boss ? ev.boss
                  : ev.kind === 'win' ? 'win'
                  : ev.kind === 'well' ? 'well'
                  : ev.kind === 'hazard' ? 'hurts'
                  : t && t.to ? '\u2192 ' + hex(t.to)
                  : t ? t.how : ev.label;
          v.font = '10px monospace';
          v.fillStyle = 'rgba(0,0,0,.65)';
          v.fillText(txt, x + 2, y - 1);
          v.fillStyle = '#eaffe8';
          v.fillText(txt, x + 1, y - 2);
        }
      }
    }
  }

  if (room.item) {
    const x = room.item.x * zoom, y = (room.item.y - CHAR_H) * zoom;
    // Draw the icon itself, from the same character and palette the game uses.
    const ic = room.item_icon;
    if (ic) {
      for (let ln = 0; ln < ic.h; ln++) {
        for (let px = 0; px < ic.w; px++) {
          const c = ic.px[ln][px];
          if (!c) continue;                       // colour 0 is transparent
          v.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
          v.fillRect(x + px * zoom, y + ln * zoom, zoom, zoom);
        }
      }
    }
    if ($('#showitem').checked) {
      v.strokeStyle = '#e8843c'; v.lineWidth = 1;
      v.strokeRect(x - .5, y - .5, CHAR_W * zoom + 1, CHAR_H * zoom + 1);
      v.fillStyle = '#e8843c'; v.font = '11px monospace';
      v.fillText(ITEMS[room.item.id] || hex(room.item.id), x, y - 4);
    }
  }
}

function cellAt(ev) {
  const r = $('#view').getBoundingClientRect();
  const col = Math.floor((ev.clientX - r.left) / (CHAR_W * zoom));
  const band = Math.floor((ev.clientY - r.top) / (CHAR_H * zoom));
  if (col < 0 || col >= room.width || band < 0 || band >= BANDS) return null;
  return {col, band};
}

async function paint(c) {
  if (grid[c.band * COLS + c.col] === sel) return;
  try {
    const r = await api('/api/paint', {kind:room.kind, col:c.col, band:c.band, cell:sel});
    const g = await api('/api/grid/' + room.kind.toString(16));
    grid = b64(g.grid); render(); refreshDiff();
    const w = $('#warn');
    if (r.also_affects.length) {
      w.hidden = false;
      w.innerHTML = `That tile lives in shared slice <b>${r.slices.map(s=>hex(s)).join(', ')}</b> &mdash; ` +
        `the same bytes also draw room${r.also_affects.length>1?'s':''} ` +
        `<b>${r.also_affects.map(k=>hex(k)).join(', ')}</b>, which changed too.`;
    } else { w.hidden = true; }
  } catch (e) { toast(e.message, 'bad'); }
}

/* ------------------------------------------------------------ tile picker */
function drawTiles() {
  const cv = $('#tiles'), z = 3, per = 8, n = 128;   // even characters only
  const cols = per, rowsN = Math.ceil(n / per);
  cv.width = cols * (CHAR_W * z + 1) + 1;
  cv.height = rowsN * (CHAR_H * z + 1) + 1;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#14110f'; ctx.fillRect(0, 0, cv.width, cv.height);
  const colours = pal[Math.min(BANDS - 1, 5)];
  for (let i = 0; i < n; i++) {
    const ch = i * 2;
    const gx = (i % per) * (CHAR_W * z + 1) + 1, gy = Math.floor(i / per) * (CHAR_H * z + 1) + 1;
    for (let ln = 0; ln < CHAR_H; ln++) {
      const pair = glyphLine(ch, ln);
      for (let half = 0; half < 2; half++) {
        for (let p = 0; p < 4; p++) {
          const v = (pair[half] >> (6 - 2 * p)) & 3;
          if (!v) continue;
          const c = colours[v - 1];
          ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
          ctx.fillRect(gx + (half * 4 + p) * z, gy + ln * z, z, z);
        }
      }
    }
    if (ch === sel) {
      ctx.strokeStyle = '#e8843c'; ctx.lineWidth = 2;
      ctx.strokeRect(gx - 1, gy - 1, CHAR_W * z + 2, CHAR_H * z + 2);
    }
  }
  cv.onclick = ev => {
    const r = cv.getBoundingClientRect();
    const cx = Math.floor((ev.clientX - r.left) / (CHAR_W * z + 1));
    const cy = Math.floor((ev.clientY - r.top) / (CHAR_H * z + 1));
    const i = cy * per + cx;
    if (i >= 0 && i < n) { sel = i * 2; $('#selchar').textContent = hex(sel); drawTiles(); }
  };
  $('#selchar').textContent = hex(sel);
}

/* ------------------------------------------------------------- properties */
function row(k, v) { return `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`; }

function showProps() {
  const r = room;
  let h = row('kind', hex(r.kind)) + row('header', hex(r.addr, 4)) +
          row('area bank', 'b' + r.bank) + row('charset', hex(r.charbase)) +
          row('width', r.width + ' cols');
  h += `<div class="row"><span class="k">segments</span>` +
       `<input id="f_segs" value="${r.segments}" style="max-width:56px">` +
       `<span class="v" style="font-size:11px;color:var(--faint)">1&ndash;5, ` +
       `header is 25 + 5n bytes</span></div>`;
  h += `<div class="row"><span class="k">map limit</span>` +
       `<input id="f_limit" value="${hex(r.limit, 4)}"></div>`;
  h += `<p class="note"><b>Segments are the room's width.</b> The header is a
    <code>$00</code>-terminated list of slice ids followed by four exit arrays,
    so changing the count resizes the record &mdash; and the shipped headers are
    packed with none to spare, five of them overlapping a neighbour by a byte or
    three. Widening therefore <em>moves</em> the header into free space above
    the block and repoints <code>f7:$F32A</code>; the original bytes stay put,
    which is what the overlapping rooms need. Going back to the shipped count
    moves it home again. New segments repeat the last slice and arrive with no
    vertical exits.</p>
  <p class="note"><b>Five is the ceiling.</b> The map builder at
    <code>f7:$F243</code> lays each segment 20 columns into a 100&times;10
    buffer at <code>$2400</code>, so five fill it exactly &mdash; and fourteen
    shipped rooms use five. A sixth would start at column 100, which is the
    second band, and its last row would run past <code>$27E7</code> over
    <code>score_digits</code>.</p>
  <p class="note"><b>Map limit</b> is the base at header +3; the loader adds
    <code>$AE</code>. It is where the east exit triggers and where the clamp at
    <code>f6:$53A6</code> stops the player, so it wants to match the width.</p>`;
  h += `<div class="row"><span class="k">dark</span>` +
       `<input type="checkbox" id="f_dark" ${r.dark?'checked':''} style="width:auto"></div>`;
  if (r.dark) h += `<p class="note">Darkness collapses every colour to $00 or $02
    at <b>f7:$F134</b>, so the artwork is all but invisible without the lantern &mdash;
    holding it clears the flag outright. Use <b>as played</b> above to see which.</p>`;
  h += `<div class="row"><span class="k">palette</span>` +
       `<input id="f_stream" value="${hex(r.stream)}"></div>`;

  h += '<h4>Item</h4>';
  if (r.item) {
    const opts = Object.entries(ITEMS).map(([id, nm]) =>
      `<option value="${id}" ${+id===r.item.id?'selected':''}>${hex(+id)} ${nm}</option>`).join('');
    h += `<div class="row"><span class="k">item</span><select id="f_item">${opts}</select></div>`;
    h += row('position', `x ${r.item.x}  y ${r.item.y}`);
    h += row('pending', r.item.pending ? 'yes -- until cleared' : 'no');
    h += `<p class="note">Choose the Item tool and drag it on the map to move it.</p>`;
    h += `<div class="row"><span class="k">remove</span>` +
         `<button id="f_delitem" class="minor">clear header +7</button></div>`;
  } else {
    const opts = Object.entries(ITEMS).filter(([id]) => +id > 0).map(([id, nm]) =>
      `<option value="${id}">${hex(+id)} ${nm}</option>`).join('');
    h += `<div class="row"><span class="k">add one</span>` +
         `<select id="f_newitem"><option value="">-- none --</option>${opts}</select></div>`;
    h += `<p class="note">Header +7 is <code>$00</code>, which is the only thing
      making this room itemless &mdash; every header carries the item fields and
      the room loader copies +7 straight through without testing it. Adding one
      places it where rooms <code>$0B</code> and <code>$0C</code> keep theirs
      unless this header already remembers a position; drag it with the Item
      tool afterwards.</p>`;
  }

  h += '<h4>Terrain slices</h4>';
  r.ids.forEach((s, i) => {
    h += `<div class="row"><span class="k">seg ${i} @${r.seg_offsets[i]}</span>` +
         `<input class="f_sel" data-seg="${i}" value="${hex(s)}">` +
         `<span class="shared" id="sh${i}"></span></div>`;
  });
  $('#roomprops').innerHTML = h;

  $('#f_dark').onchange = e => setField('dark', e.target.checked ? 1 : 0);
  $('#f_limit').onchange = e =>
    setField('limit', parseInt(e.target.value.replace('$',''), 16));
  $('#f_segs').onchange = async e => {
    try {
      await api('/api/segments', {kind:room.kind, n:+e.target.value});
      await selectRoom(room.kind); refreshDiff();
      toast('Room is now ' + e.target.value + ' segments wide.', 'good');
    } catch (err) { toast(err.message, 'bad'); await selectRoom(room.kind); }
  };
  $('#f_stream').onchange = e => setField('stream', parseInt(e.target.value.replace('$',''), 16));
  if (r.item) {
    $('#f_item').onchange = async e => {
      await api('/api/item', {kind:r.kind, id:+e.target.value});
      await selectRoom(r.kind); refreshDiff();
    };
    $('#f_delitem').onclick = async () => {
      try { await api('/api/removeitem', {kind:r.kind});
            await refreshRoomEntry(r.kind); refreshDiff(); }
      catch (err) { toast(err.message, 'bad'); }
    };
  } else {
    $('#f_newitem').onchange = async e => {
      if (!e.target.value) return;
      try { await api('/api/additem', {kind:r.kind, id:+e.target.value});
            await refreshRoomEntry(r.kind); refreshDiff();
            toast('Item added to the header.', 'good'); }
      catch (err) { toast(err.message, 'bad'); }
    };
  }
  document.querySelectorAll('.f_sel').forEach(inp => {
    inp.onchange = async e => {
      try {
        await api('/api/slicesel', {kind:r.kind, seg:+e.target.dataset.seg,
                                    sel:parseInt(e.target.value.replace('$',''), 16)});
        await selectRoom(r.kind); refreshDiff();
      } catch (err) { toast(err.message, 'bad'); }
    };
  });
  r.ids.forEach(async (s, i) => {
    const u = await api('/api/sliceusers', {bank:r.bank, sel:s});
    const others = [...new Set(u.users.map(x => x.room))].filter(k => k !== r.kind);
    const el = $('#sh' + i);
    if (el && others.length) el.textContent = 'shared with ' + others.map(k => hex(k)).join(' ');
  });
}

async function setField(field, value) {
  try { await api('/api/field', {kind:room.kind, field, value});
        await selectRoom(room.kind); refreshDiff(); }
  catch (e) { toast(e.message, 'bad'); }
}

function showExits() {
  const r = room;
  let h = `<p class="note">North and south are per segment; east and west are one
    destination for the whole room. <b>$00</b> means that edge is a wall.</p>`;
  h += '<h4>North</h4>';
  r.north.forEach((d, i) => {
    h += `<div class="row"><span class="k">seg ${i}</span>` +
         `<input class="f_ex" data-edge="north" data-seg="${i}" data-f="dest" value="${hex(d)}">` +
         `<input class="f_ex" data-edge="north" data-seg="${i}" data-f="arrive" value="${hex(r.north_scr[i])}" title="arrival screen">` +
         `</div>`;
  });
  h += '<h4>South</h4>';
  r.south.forEach((d, i) => {
    h += `<div class="row"><span class="k">seg ${i}</span>` +
         `<input class="f_ex" data-edge="south" data-seg="${i}" data-f="dest" value="${hex(d)}">` +
         `<input class="f_ex" data-edge="south" data-seg="${i}" data-f="arrive" value="${hex(r.south_scr[i])}" title="arrival screen">` +
         `</div>`;
  });
  h += '<h4>Long axis</h4>';
  h += `<div class="row"><span class="k">west</span><input id="f_west" value="${hex(r.west)}"></div>`;
  h += `<div class="row"><span class="k">east</span><input id="f_east" value="${hex(r.east)}"></div>`;
  // The doors that live in the terrain rather than at an edge. These carry the
  // conditions -- a weapon, a selected item, a boss beaten -- and three of them
  // take their destination from the tables above.
  if (room.props && room.events) {
    const found = new Map();
    for (let band = 0; band < BANDS; band++) {
      for (let col = 0; col < room.width; col++) {
        const cell = grid[band * 100 + col];
        if (!cell) continue;
        const p = room.props[(cell >> 1) & 0x7F];
        const ev = room.events[String(p)];
        if (ev && !found.has(p)) found.set(p, {ev, col, band});
      }
    }
    h += '<h4>Doors in the terrain</h4>';
    if (!found.size) {
      h += `<p class="note">This room has none &mdash; every way out is an edge.</p>`;
    } else {
      for (const [p, {ev, col, band}] of found) {
        const t = exitTarget(ev, col);
        const to = t && t.to ? hex(t.to) : t && t.to === 0 ? 'nowhere ($00)' : '&mdash;';
        h += `<div class="row"><span class="k">${hex(p)} ${ev.kind}</span>` +
             `<span class="v">${ev.boss ? ev.boss : to}` +
             `<span style="font-size:11px;color:var(--faint)"> &middot; ` +
             `col ${col}, band ${band}${t ? ' &middot; ' + t.how : ''}</span></span></div>`;
        if (ev.needs)
          h += `<p class="note">Needs ${ev.needs}.</p>`;
      }
      h += `<p class="note">Turn on <b>exits</b> above the room picture to see
        where these sit. A door that defers to a table resolves per segment, so
        the same tile in a different column can lead somewhere else.</p>`;
    }
  }

  $('#exitprops').innerHTML = h;

  document.querySelectorAll('.f_ex').forEach(inp => {
    inp.onchange = async e => {
      const d = e.target.dataset, v = parseInt(e.target.value.replace('$',''), 16);
      const body = {kind:r.kind, edge:d.edge, seg:+d.seg};
      body[d.f] = v;
      try { await api('/api/exit', body); await selectRoom(r.kind); refreshDiff(); }
      catch (err) { toast(err.message, 'bad'); }
    };
  });
  $('#f_west').onchange = e => setField('west', parseInt(e.target.value.replace('$',''), 16));
  $('#f_east').onchange = e => setField('east', parseInt(e.target.value.replace('$',''), 16));
}

function showActors() {
  const sp = room.spawns, k = sp.special;
  let h = `<p class="note">Six placement budgets, one byte each. The high nibble
    is how many, the low nibble a rate mask &mdash; and the mask is the reciprocal
    of the rate, so <b>$00</b> fires every frame and <b>$FF</b> is rare.</p>`;

  h += '<h4>Budgets</h4>';
  for (const b of sp.budgets) {
    h += `<div class="row"><span class="k">${b.spawns}</span>` +
         `<input class="f_sp" data-slot="${b.slot}" value="${hex(b.raw)}">` +
         `<span class="v" style="font-size:11px;color:var(--faint)">` +
         (b.raw ? `${b.amount === 255 ? '&infin;' : b.amount} @ ${hex(b.rate)}` : 'none') +
         `</span></div>`;
    if (b.cross_marker) h += `<p class="note">$EF is a marker, not a count: it
      becomes <b>$22</b> (two, one chance in 64) when the player carries the cross
      and <b>$FF</b> (unbounded, every frame) when they do not. This is the only
      way a room responds to the cross.</p>`;
  }

  const t = room.throwing;
  h += `<div class="row"><span class="k">throw rate</span>` +
       `<input id="f_throw" value="${hex(t.raw)}">` +
       `<span class="v" style="font-size:11px;color:var(--faint)">` +
       (t.enabled ? `1 in ${t.one_in}` : 'never') + `</span></div>`;
  h += `<p class="note">Whether this area's enemies throw projectiles
    (<code>throw_enable</code>, header +$0F) &mdash; and how often. <b>Not a
    flag</b>: $00 disables throwing, and otherwise the shot fires only when
    <code>throw_enable AND $8D</code> is zero, so every set bit halves the rate.
    Only 10 rooms of 76 throw at all. A thrown hit costs 5 blood purity &mdash;
    or <b>9 while the necklace is held</b>, which enters the drain ladder four
    calls early.</p>`;

  h += '<h4>Special actor</h4>';
  if (k.fixed === null) {
    h += row('kind', `random &amp; ${hex(k.mask)} &rarr; ${k.range.join(', ')}`);
    h += `<p class="note">A negative entry is a mask: the kind is
      <code>Random AND ${hex(k.mask)}</code>, so this room draws from a range.</p>`;
  } else {
    h += row('kind', `${hex(k.fixed)} &mdash; ${KINDS[k.fixed] || 'unknown'}`);
  }
  h += `<div class="row"><span class="k">table byte</span>` +
       `<input id="f_kind" value="${hex(k.raw)}"></div>`;
  if (k.dead) h += `<p class="note" style="color:var(--accent)">This kind seeds
    <code>sactor_damage</code> with $00, which the per-frame walk reads as an empty
    slot &mdash; so it is placed and then ignored. Nothing from this budget can
    ever appear.</p>`;
  $('#actorprops').innerHTML = h;

  document.querySelectorAll('.f_sp').forEach(inp => inp.onchange = async e => {
    try { await api('/api/spawn', {kind:room.kind, slot:e.target.dataset.slot,
                                   value:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  $('#f_throw').onchange = async e => {
    try { await api('/api/throwing', {kind:room.kind,
                                      value:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };

  showToughness();
  showRules();
  showReticle();

  $('#f_kind').onchange = async e => {
    try { await api('/api/screenkind', {kind:room.kind,
                                        value:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
}

async function showToughness() {
  const d = await api('/api/toughness');
  let h = `<h4>Toughness &mdash; global</h4>
    <p class="note">The seed written into <code>sactor_damage</code> when a
    creature is placed. Death is an 8-bit overflow, so a seed <b>S</b> costs
    <b>256 &minus; S</b> points and a weapon lands its own level per hit &mdash;
    axe 1, blaster 2, mega 3. <b>This table is shared by the whole game</b>:
    changing a kind changes it in every room that places it.</p>`;
  for (const t of d.kinds) {
    const name = KINDS[t.kind] || ('kind ' + t.kind);
    h += `<div class="row"><span class="k" title="${name}">${t.kind} ${name}</span>` +
         `<input class="f_tough" data-kind="${t.kind}" value="${hex(t.seed)}">` +
         `<span class="v" style="font-size:11px;color:var(--faint)">` +
         (t.inert ? 'inert' : `${t.points} pts · ${t.hits.axe} axe`) +
         `</span>` +
         (t.rooms.length ? `<span class="shared">${t.rooms.length} rm</span>` : '') +
         `</div>`;
    if (t.inert) h += `<p class="note" style="color:var(--accent)">Seed $00 reads
      as an empty slot, so this kind is placed and ignored on the next frame.
      ${t.rooms.length ? 'Rooms ' + t.rooms.map(k => hex(k)).join(', ') +
      ' ask for it and get nothing.' : 'No room places it.'}
      Give it any non-zero seed to bring it to life.</p>`;
  }
  $('#actorprops').insertAdjacentHTML('beforeend', h);
  document.querySelectorAll('.f_tough').forEach(inp => inp.onchange = async e => {
    try { await api('/api/toughness', {kind:+e.target.dataset.kind,
                                       seed:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
}

async function showRules() {
  const d = await api('/api/rules');
  let h = `<h4>Damage rules &mdash; global</h4>
    <p class="note">Each of these is the immediate operand of one instruction.
    Blood purity is deliberately absent: the engine has no "drain N" argument,
    it calls the drain repeatedly, so a purity cost is a count of instructions
    rather than a number. Which item grants each protection lives in the
    <b>Items</b> tab, alongside every other item reference.</p>`;
  for (const r of d.rules) {
    h += `<div class="row"><span class="k" title="${r.at}">${r.label}</span>` +
         `<input class="f_rule" data-name="${r.name}" value="${hex(r.value)}"` +
         (r.anchored ? '' : ' disabled title="opcode moved -- editing refused"') + `>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${r.at}` +
         (r.value !== r.default ? ` \u00b7 was ${hex(r.default)}` : '') + `</span></div>`;
    h += `<p class="note">${r.note}</p>`;
  }
  $('#actorprops').insertAdjacentHTML('beforeend', h);
  document.querySelectorAll('.f_rule').forEach(inp => inp.onchange = async e => {
    try { await api('/api/rule', {name:e.target.dataset.name,
                                  value:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
}

/* ------------------------------------------------------- the draw editor */
/* One editor for two kinds of artwork, because they are the same format: a
   terrain character is 2 bytes x 16 lines in an area bank, a sprite cell is
   4 bytes x 16 lines on bank 7 page $C0 or $E0. Both are line-planar with the
   zone offset counting down, and both are 2 bits per pixel. */
async function showPixels() {
  if (!spritePages) {
    const d = await api('/api/spritepages');
    spritePages = d.pages; spriteNames = d.names;
  }
  if (!src) src = {kind:'chars'};

  const chars_ = src.kind === 'chars';
  const width = chars_ ? 2 : 4;
  const space = chars_ ? ('b' + room.bank) : src.space;
  const page  = chars_ ? room.charbase : src.page;
  const low   = chars_ ? sel : (src.low || 0);
  // sprites carry no palette of their own -- their colours come from the
  // composite record at draw time -- so they preview on the sheet's grey ramp
  const cols = chars_ ? pal[palBand] : GREY;

  let h = `<div class="row"><span class="k">artwork</span>
    <select id="f_src">
      <option value="chars" ${chars_?'selected':''}>room characters (b${room.bank} ${hex(room.charbase)})</option>
      ${spritePages.map(p => `<option value="${p.page}" ${!chars_ && src.page===p.page?'selected':''}>sprites ${p.label}</option>`).join('')}
    </select></div>`;

  if (chars_) {
    h += `<p class="note">Character <b>${hex(sel)}</b>, eight pixels by sixteen
      lines. Pick a tile in the Tiles tab to change which. A pixel is two bits,
      so it is transparent or one of three colours &mdash; and which three
      depends on the band it is drawn in.</p>`;
    h += `<div class="row"><span class="k">preview band</span>
      <select id="f_band">${pal.map((_, i) =>
        `<option value="${i}" ${i===palBand?'selected':''}>band ${i}</option>`).join('')}</select></div>`;
  } else {
    const key = hex(page).slice(1) + ':' + hex(low).slice(1);
    const nm = spriteNames[key];
    h += `<div class="row"><span class="k">cell</span>
      <select id="f_cell">${Array.from({length:64}, (_, i) => i * 4).map(l => {
        const n = spriteNames[hex(page).slice(1) + ':' + hex(l).slice(1)];
        return `<option value="${l}" ${l===low?'selected':''}>${hex(l)}${n ? ' — ' + n.name : ''}</option>`;
      }).join('')}</select></div>`;
    h += `<p class="note">${nm ? `<b>${nm.name}</b>${nm.how ? ` — identified from ${nm.how}` : ''}. ` : ''}
      Sixteen pixels by sixteen lines. Sprites store no colour of their own: the
      composite record picks a palette when it draws, so this previews on a
      neutral ramp. A 16-pixel cell often holds two 8-pixel sprites side by
      side &mdash; the item icons are packed that way.</p>`;
  }

  h += `<div class="inks">` + [0,1,2,3].map(v =>
    `<button class="ink ${v===ink?'on':''}" data-v="${v}" title="${v?('colour '+v):'transparent'}"
       style="${v ? 'background:'+rgb(cols[v-1]) : ''}">${v ? v : '&empty;'}</button>`).join('') +
    `</div>`;
  h += `<canvas id="px" width="200" height="400"></canvas>`;

  if (chars_) {
    const r0 = await api('/api/char', {bank:room.bank, charbase:room.charbase, ch:sel});
    const others = r0.rooms.filter(k => k !== room.kind);
    h += others.length
      ? `<p class="note" style="color:var(--accent)">This character set is drawn by
         ${others.length} other room${others.length>1?'s':''}
         (${others.slice(0,10).map(k=>hex(k)).join(' ')}${others.length>10?' &hellip;':''}).
         Editing a character changes it everywhere.</p>`
      : `<p class="note">No other room draws this character set.</p>`;
  } else {
    h += `<p class="note" style="color:var(--accent)">Sprite pages are global.
      Every room that shows this creature, item or screen shows the edit.</p>`;
  }
  $('#pixelprops').innerHTML = h;

  $('#f_src').onchange = e => {
    src = e.target.value === 'chars'
      ? {kind:'chars'}
      : {kind:'sprite', space:'f7', page:+e.target.value, low:0};
    showPixels();
  };
  if ($('#f_band')) $('#f_band').onchange = e => { palBand = +e.target.value; showPixels(); };
  if ($('#f_cell')) $('#f_cell').onchange = e => { src.low = +e.target.value; showPixels(); };
  document.querySelectorAll('.ink').forEach(b => b.onclick = () => {
    ink = +b.dataset.v; showPixels();
  });

  const got = await api('/api/cell', {space, page, low, width, lines:16});
  paintChar(got.rows, {space, page, low, width, cols, chars_});
}

function paintChar(rows, ctx0) {
  const cv = $('#px'), cols = ctx0.cols, W = ctx0.width * 4;
  const z = W > 8 ? 14 : 24;
  cv.width = W * z + 1; cv.height = 16 * z + 1;
  const ctx = cv.getContext('2d');
  const draw = () => {
    ctx.fillStyle = '#14110f'; ctx.fillRect(0, 0, cv.width, cv.height);
    for (let y = 0; y < 16; y++) for (let x = 0; x < W; x++) {
      const v = rows[y][x];
      if (v) { ctx.fillStyle = rgb(cols[v - 1]); ctx.fillRect(x*z+1, y*z+1, z-1, z-1); }
      else {                                  // transparent reads as a checker
        ctx.fillStyle = ((x + y) & 1) ? '#241f1b' : '#1b1714';
        ctx.fillRect(x*z+1, y*z+1, z-1, z-1);
      }
    }
    ctx.strokeStyle = 'rgba(255,255,255,.07)';
    for (let x = 0; x <= W; x++) { ctx.beginPath(); ctx.moveTo(x*z+.5,0); ctx.lineTo(x*z+.5,cv.height); ctx.stroke(); }
    for (let y = 0; y <= 16; y++) { ctx.beginPath(); ctx.moveTo(0,y*z+.5); ctx.lineTo(cv.width,y*z+.5); ctx.stroke(); }
  };
  draw();

  const at = ev => {
    const b = cv.getBoundingClientRect();
    const x = Math.floor((ev.clientX - b.left) / z), y = Math.floor((ev.clientY - b.top) / z);
    return (x >= 0 && x < W && y >= 0 && y < 16) ? {x, y} : null;
  };
  const put = async p => {
    if (!p || rows[p.y][p.x] === ink) return;
    rows[p.y][p.x] = ink; draw();                    // optimistic, then confirm
    try {
      const res = await api('/api/cellpixel', {space:ctx0.space, page:ctx0.page,
        low:ctx0.low, width:ctx0.width, lines:16, line:p.y, x:p.x, value:ink});
      rows = res.rows; draw(); refreshDiff();
      if (ctx0.chars_) refreshGrid();      // the room is drawn from the charset
    } catch (e) { toast(e.message, 'bad'); }
  };
  cv.onmousedown = ev => { pxdraw = true; put(at(ev)); };
  cv.onmousemove = ev => { if (pxdraw) put(at(ev)); };
  window.addEventListener('mouseup', () => { pxdraw = false; });
}

// the room picture is drawn from the character set, so a pixel edit changes it
async function refreshGrid() {
  const g = await api('/api/room/' + room.kind.toString(16));
  chars = b64(g.charset); grid = b64(g.grid); render(); drawTiles();
}

/* ----------------------------------------------------- the colour editor */
async function showColours() {
  if (!ntsc) ntsc = (await api('/api/ntsc')).rgb;
  const st = room.stream, raw = room.palette_raw;
  const box = $('#colourprops');
  if (!raw) { box.innerHTML = '<p class="note">This room has no palette block.</p>'; return; }

  let h = `<p class="note">Palette block for stream <b>${hex(st)}</b>: ten bands
    of three colours, one row per band of the room. A 2-bit pixel picks one of
    the three; value 0 is transparent and has no entry.</p>`;
  if (room.palette_rooms > 1) h += `<p class="note" style="color:var(--accent)">
    ${room.palette_rooms} rooms share this block. Recolouring changes all of them.</p>`;

  for (let b = 0; b < raw.length; b++) {
    h += `<div class="row"><span class="k">band ${b}</span>` +
      raw[b].map((v, i) =>
        `<button class="sw" data-band="${b}" data-index="${i+1}"
           style="background:${rgb(ntsc[v])}" title="index ${i+1} = ${hex(v)}"></button>`).join('') +
      `<span class="v" style="font-size:11px;color:var(--faint)">${raw[b].map(v=>hex(v)).join(' ')}</span></div>`;
  }
  const blocks = (await api('/api/blocks')).blocks;
  for (const b of blocks) {
    h += `<h4>${b.label} <span style="color:var(--faint)">${b.at}</span></h4>`;
    if (b.note) h += `<p class="note">${b.note}</p>`;
    for (const p of b.palettes) {
      h += `<div class="row"><span class="k">${b.name === 'grampa' ? 'palette ' : 'band '}${p.index}</span>` +
        p.colours.map((v, i) =>
          `<button class="sw blk" data-block="${b.name}" data-index="${p.index}"
             data-slot="${i+1}" style="background:${rgb(ntsc[v])}"
             title="slot ${i+1} = ${hex(v)}"></button>`).join('') +
        `<span class="v" style="font-size:11px;color:var(--faint)">` +
        p.colours.map(v => hex(v)).join(' ') +
        (p.used_by.length ? ` &middot; ${p.used_by.join(', ')}` : '') +
        `</span></div>`;
    }
  }

  h += `<div id="picker" hidden><h4>Pick a colour</h4>
        <p class="note">The whole 7800 space: sixteen hues across, sixteen
        luminances down. Hue 0 is the grey column.</p>
        <canvas id="swatches" width="272" height="272"></canvas></div>`;
  box.innerHTML = h;

  let target = null;
  document.querySelectorAll('.sw').forEach(b => b.onclick = () => {
    target = b.dataset.block
      ? {block:b.dataset.block, index:+b.dataset.index, slot:+b.dataset.slot}
      : {band:+b.dataset.band, index:+b.dataset.index};
    document.querySelectorAll('.sw').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    $('#picker').hidden = false;
    $('#picker').scrollIntoView({block:'nearest'});
  });

  const cv = $('#swatches'), z = 17, ctx = cv.getContext('2d');
  for (let lum = 0; lum < 16; lum++) for (let hue = 0; hue < 16; hue++) {
    ctx.fillStyle = rgb(ntsc[(hue << 4) | lum]);
    ctx.fillRect(hue*z, lum*z, z-1, z-1);
  }
  cv.onclick = async ev => {
    if (!target) { toast('Pick a band colour first.'); return; }
    const b = cv.getBoundingClientRect();
    const hue = Math.floor((ev.clientX - b.left) / z);
    const lum = Math.floor((ev.clientY - b.top) / z);
    if (hue < 0 || hue > 15 || lum < 0 || lum > 15) return;
    const value = (hue << 4) | lum;
    try {
      if (target.block) {
        await api('/api/blockcolour', {name:target.block, index:target.index,
                                        slot:target.slot, value});
      } else {
        await api('/api/palette', {stream:st, band:target.band,
                                   index:target.index, value});
      }
      await selectRoom(room.kind); refreshDiff();
    } catch (e) { toast(e.message, 'bad'); }
  };
}


/* --------------------------------------------------------- item references */
/* Every instruction in the cartridge that names one inventory slot, grouped by
   the item it currently names. Repointing one is a one- or two-byte write,
   because the inventory is flat: slot = $1F3D + id. */
async function showItems() {
  const d = await api('/api/itemrefs');
  const byItem = {};
  for (const r of d.refs) (byItem[r.item] = byItem[r.item] || []).push(r);

  const hp = await api('/api/health-rules');
  let h = `<h4>Health ceiling</h4>
    <p class="note">One mechanic in five constants. <code>hp_max</code> starts at
    ${hex(hp.values[0].value)}; the diamond is the only thing that raises it and
    the ghost the only thing that lowers it. Together with the revival threshold
    they decide what a second life costs.</p>`;
  for (const v of hp.values) {
    h += `<div class="row"><span class="k" title="${v.at}">${v.label}</span>` +
         `<input class="f_hp" data-name="${v.name}" value="${hex(v.value)}"` +
         (v.anchored ? '' : ' disabled title="opcode moved -- editing refused"') + `>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${v.value}` +
         (v.value !== v.default ? ` · was ${hex(v.default)}` : '') + `</span></div>`;
    h += `<p class="note">${v.note}</p>`;
  }
  h += `<p class="note" style="color:var(--accent)">As set: ` +
    (hp.diamonds_to_revive === null
      ? `nothing raises <code>hp_max</code>, so revival is unreachable.`
      : hp.diamonds_to_revive === 0
        ? `you start above the threshold, so revival needs no diamonds at all.`
        : `a second life costs <b>${hp.diamonds_to_revive} diamond${hp.diamonds_to_revive>1?'s':''}</b>.`) +
    ` Blood loss is terminal either way.</p>`;

  const mt = await api('/api/musictiming');
  const pu = await apiSoft('/api/purity');
  if (pu) {
  h += `<h4>Blood purity</h4>
    <p class="note">There is no "drain N" argument &mdash; the routine takes one
    point per call, so a bigger loss is written as more <code>JSR</code>s in a
    row. Seven runs, seventeen calls. A call and three <code>NOP</code>s are
    both three bytes, so a point can be removed without moving anything.</p>`;
  for (const st of pu.sites) {
    h += `<div class="row"><span class="k">${st.label}</span>` +
         `<input class="f_purity" data-space="${st.space}" data-addr="${st.addr}" ` +
         `value="${st.active}" style="max-width:56px" ${st.intact ? '' : 'disabled'}>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${st.at} &middot; ` +
         `up to ${st.slots}${st.intact ? '' : ' &middot; altered'}</span></div>`;
  }
  const L = pu.ladder;
  h += `<p class="note">The projectile ladder is the only one with a
    conditional entry point: holding the necklace enters at the top and takes
    all nine, otherwise the branch at ${L.branch_at} skips ahead. Its rung count
    is the "enemy projectile" box above; where the branch lands is here.</p>
    <div class="row"><span class="k">holding the necklace</span>
      <span class="v">${L.with} point${L.with === 1 ? '' : 's'}</span></div>
    <div class="row"><span class="k">without it</span>
      <input id="f_without" value="${L.without}" style="max-width:56px"
        ${L.aligned ? '' : 'disabled'}></div>
    <div class="row"><span class="k">check the necklace at all
      <em class="cost free">3 bytes</em></span>
      <input type="checkbox" id="f_necklace" ${L.checks_necklace ? 'checked' : ''}
        style="width:auto" ${L.gate === 'modified' ? 'disabled' : ''}>
      <span class="v" style="font-size:11px;color:var(--faint)">${L.gate_at} &middot; ${L.gate}</span></div>
    <p class="note">Unticking it replaces <code>LDA itm_necklace</code> with
    <code>LDA #$00 / NOP</code>, so the branch is always taken and the necklace
    costs nothing extra &mdash; both cases become the number above. The callee
    reloads the accumulator immediately, so nothing else depends on what that
    <code>LDA</code> fetched.</p>`;
  }

  h += `<h4>Music timing</h4>
    <p class="note">A note's duration is a count of frames and the engine ticks
    once per frame, so tempo follows the machine. This cartridge is
    <b>${mt.version.toUpperCase()}</b>${mt.relevant
      ? ' &mdash; it was never retimed, so everything plays at <b>83.3% speed</b>.'
      : ', which is the speed the durations were written for.'}</p>
    <div class="row"><span class="k" title="${mt.at}">rescale durations <em class="cost free">in place</em></span>
      <input type="checkbox" id="f_music" ${mt.retimed ? 'checked' : ''}
        ${mt.relevant || mt.retimed ? '' : 'disabled'} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${mt.state}</span></div>
    <p class="note"><b>Rescale</b> multiplies all sixteen duration entries by 5/6.
    Data only, nothing else moves. Long notes land within 1.3% of the intended
    length; the shortest are coarse, and the melody's clean 2:1 (16 and 8 frames)
    becomes 13:7, about 7% off. Doing nothing leaves every note 20% too long.</p>
    <div class="row"><span class="k" title="${mt.retick.at}">extra tick, 6 per 5 <em class="cost">16 b</em></span>
      <input type="checkbox" id="f_retick" ${mt.retick.on ? 'checked' : ''}
        ${mt.retick.relevant || mt.retick.on ? '' : 'disabled'} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${mt.retick.state}</span></div>
    <p class="note">The exact alternative: an 18-byte shim on the music entry
    vector <code>${mt.retick.vector}</code> that runs one extra tick every fifth
    frame, giving 59.90 Hz against NTSC's 59.958 &mdash; 0.1% out, and every note
    ratio preserved because the clock changes rather than the data. Counter is
    inventory slot <code>${mt.retick.counter}</code>, which nothing in the game
    reads or writes after boot. <b>Use one or the other, not both.</b></p>`;

  const ph = await api('/api/pumpkinhint');
  h += `<h4>The pumpkin's missing pickup line</h4>
    <p class="note">Kind ${ph.kind} is the only inventory item that grants in
    silence &mdash; the chain at <code>${ph.site}</code> has no link for it.
    This adds one, pointing at dead table slot <code>${ph.slot}</code>, and
    writes a record for it to name.</p>
    <div class="row"><span class="k">add the line
      <em class="cost">${ph.bytes || 66} bytes</em></span>
      <input type="checkbox" id="f_hint" ${ph.on ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${ph.state}</span></div>
    <div class="row"><span class="k">the line</span>
      <input type="text" id="f_hinttext" maxlength="${ph.max}"
        value="${(ph.text || ph.default).replace(/"/g,'&quot;')}"
        ${ph.on ? '' : 'disabled'}></div>
    <p class="note">Up to ${ph.max} characters; <code>|</code> breaks the line
    and no line may exceed 39. Letters, digits, space and
    <code>! ? . , -</code> only &mdash; the font has nothing else.</p>`;

  const ad = await apiSoft('/api/actordeath');
  if (ad) {
  h += `<h4>Death animations that read past their table</h4>
    <p class="note">Two animations pick a frame by using a countdown as an
    index, and both are seeded one higher than their table is long &mdash; so
    the <b>first</b> frame of each reads whatever follows the table, which in
    both cases is the <code>$A5</code> opcode of the next routine. Every later
    frame is correct.</p>
    <div class="row"><span class="k">crows, bats and ground enemies
      <em class="cost free">${ad.bytes} byte</em></span>
      <input type="checkbox" id="f_actordeath" ${ad.fixed ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${ad.at} &middot; seed ${ad.seed}` +
      (ad.overruns.length ? ` &middot; <b>${ad.overruns.length} bad frame</b>` : '') +
      `</span></div>`;
  }

  const gh = await apiSoft('/api/ghostdeath');
  if (gh) {
  h += `<p class="note">A dying ghost picks its picture with
    <code>LDA state : LSR A : TAY : LDA dat_6219,Y</code> &mdash; the index is
    the state halved. The kill seeds the state with <code>${gh.seed}</code>, and
    <code>$10&nbsp;&gt;&gt;&nbsp;1</code> is <b>8</b>, but the table at
    ${gh.table} holds ${gh.entries} entries and <code>sub_6221</code> begins
    immediately after. So the first frame reads that routine's
    <code>$A5</code> opcode and draws sprite <code>$A5</code> &mdash; a
    misaligned slice of the mega blaster's orb over a misaligned slice of the
    AWESOME lettering, because the ghost is drawn as a top half plus
    <code>top + $20</code>.</p>
    <div class="row"><span class="k">keep it inside the table
      <em class="cost free">${gh.bytes} byte</em></span>
      <input type="checkbox" id="f_ghost" ${gh.fixed ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${gh.at} &middot; ${gh.state}` +
      (gh.overruns.length ? ` &middot; <b>${gh.overruns.length} bad frame</b>` : '') +
      `</span></div>
    <p class="note">Seeding <code>$0F</code> keeps every index at 7 or below.
    Nothing else tests the value &mdash; the four other reads are sign or zero
    tests &mdash; so the only other effect is that the animation is one tick
    shorter.</p>`;
  }

  const mg = await apiSoft('/api/megaframes');
  if (mg) {
  h += `<h4>The mega blaster's lost frames</h4>
    <p class="note">It asks for four phases but its run reads
    <code>${mg.run.join(' ')}</code> &mdash; two pictures shown twice. Cells
    <code>$A8</code> and <code>$AA</code> hold two more frames of the same
    glowing orb, with the bright core in a different place, and <b>nothing on
    page $E0 names them</b>. The animation was drawn and never wired.</p>
    <div class="row"><span class="k">restore them
      <em class="cost free">${mg.bytes} bytes</em></span>
      <input type="checkbox" id="f_mega" ${mg.on ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${mg.at} &middot; ${mg.state}</span></div>`;
  }

  const ax = await apiSoft('/api/axespin');
  if (ax) {
  h += `<h4>The axe never turns over</h4>
    <p class="note">A projectile draws
    <code>dat_4FAE[dat_4F9E[type] + phase]</code>, and the phase counts down
    from <code>dat_4FD2[type]</code> &mdash; a <b>frame count</b>, not a
    graphic. The knife asks for 6, both blasters for 4, and the axe for
    <b>one</b>, so it shows a single sprite for its whole flight and appears to
    slide.</p>
    <div class="row"><span class="k">make it tumble
      <em class="cost free">${ax.bytes} bytes</em></span>
      <input type="checkbox" id="f_axe" ${ax.on ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${ax.at} &middot; ${ax.state}</span></div>
    <p class="note">The art is already there: the axe's four entries sit
    together as ${ax.poses.join(' ')} &mdash; three orientations, one per facing
    with down and right sharing. Pointing every facing at that run and asking
    for four phases makes it turn over, with nothing new drawn. The cost is the
    per-facing orientation: an axe thrown left then tumbles like one thrown up,
    because the other facings cannot keep their own window &mdash; base
    <code>$19</code> plus three phases runs off the end into the blaster's
    <code>$A0</code>.</p>
    <p class="note">It also moves the step gate from <code>$44</code>, which
    counts every frame, to <code>$45</code>, which counts every other &mdash; so
    a pose holds ${ax.step} frames instead of 2. That byte is <b>shared</b>:
    the knife and both blasters slow with it, which suits them.</p>`;
  const a4 = await apiSoft('/api/axefourth');
  if (a4) {
    h += `<div class="row"><span class="k">give it a fourth pose
        <em class="cost free">${a4.bytes} bytes</em></span>
        <input type="checkbox" id="f_axe4" ${a4.on ? 'checked' : ''} style="width:auto">
        <span class="v" style="font-size:11px;color:var(--faint)">${a4.at} &middot; ${a4.state}</span></div>
      <p class="note">The run is <code>${a4.run.join(' ')}</code> &mdash; four
      phases over three drawings, so one pose shows twice. Page <code>$E0</code>
      has room: the six bytes at <code>$88</code> are referenced by nothing, and
      an axe sprite is two bytes wide. This mirrors <code>$CE</code> into that
      slot and points the repeated phase at it, giving four distinct
      orientations. <b>Only visible with the tumble on</b> &mdash; without it the
      phase never leaves 0.</p>`;
  }
  }

  const ps = await apiSoft('/api/pickupshimmer');
  if (ps) {
    h += `<h4>Pickups that never shimmer</h4>
      <p class="note">A record's terminator decides whether the banner pulses:
      <code>$FE</code> makes it shimmer, <code>$FF</code> holds it still. Four
      pickup messages end <code>$FF</code> while everything around them ends
      <code>$FE</code>.</p>`;
    for (const e of ps.entries) {
      h += `<div class="row"><span class="k">${e.name}</span>` +
           `<span class="v" style="font-size:11px;color:var(--faint)">record ` +
           `${e.record} &middot; ${e.at} &middot; ${e.value}` +
           (e.on ? ' &middot; shimmers' : '') + `</span></div>`;
    }
    h += `<div class="row"><span class="k">make them shimmer
        <em class="cost free">${ps.bytes} bytes</em></span>
        <input type="checkbox" id="f_pickshim" ${ps.on ? 'checked' : ''} style="width:auto">
        <span class="v" style="font-size:11px;color:var(--faint)">${ps.state}</span></div>
      <p class="note">The knife's own four messages shimmer, as do both potions,
      the crypt key, necklace, heart, lantern and all four diamond variants
      &mdash; so these four are the odd ones out rather than a house style.</p>`;
  }

  const ic = await api('/api/iconfixes');
  h += `<h4>The selected-item icon</h4>
    <p class="note">The status bar shows whatever is selected, from two tables
    indexed by <code>sel_item</code>. Three entries are wrong, and it shows
    during play.</p>`;
  for (const e of ic.entries) {
    h += `<div class="row"><span class="k">${e.name}</span>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${e.at} &middot; ` +
         `${hex(e.stock)} &rarr; ${hex(e.fixed)} &middot; ${e.why}</span></div>`;
  }
  h += `<div class="row"><span class="k">repair the icons <em class="cost free">4 bytes</em></span>
      <input type="checkbox" id="f_icons" ${ic.fixed ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${ic.state}</span></div>
    <p class="note">MARIA palette 5 has <b>$00</b> as its first colour, pure
    black. The crypt key's lit pixels are <em>all</em> that colour, so it renders
    invisible; the necklace is mostly that colour and reads as a smudge. The
    weapons in the same tables use palette 4, whose first colour is a light gold,
    and they are perfectly legible &mdash; so the repair moves them across.
    The pumpkin has a second fault: its graphics entry names the <em>heart's</em>
    icon instead of its own. Its world sprite flashes on an animated palette,
    which the status strip cannot do, so it takes the same static palette 4 and
    reads as an orange pumpkin.</p>`;

  const cf = await api('/api/compactflip');
  const fs = await api('/api/freespace');
  h += `<h4>More space</h4>
    <p class="note">The display double-buffer flip writes ten display-list bytes
    per branch as ten load/store pairs, though the value changes only twice.
    Loading each value once frees <b>${cf.frees} bytes</b> at ${cf.pocket},
    without altering a single write. Patches below prefer that pocket, which
    leaves the tail of bank 6 whole for test builds.</p>
    <div class="row"><span class="k" title="${cf.at}">compact the flip <em class="cost free">frees ${cf.frees}</em></span>
      <input type="checkbox" id="f_flip" ${cf.on ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${cf.state}</span></div>
    <p class="note">Played for 22,215 frames against the stock cartridge: the
    display list stays valid, the buffers alternate, and nothing writes into the
    freed bytes. Cycle count does change, so the random sequence differs from
    stock &mdash; a different game, not a broken one.</p>`;
  const left = fs.contiguous;
  const pct = Math.round(100 * (fs.total - left) / fs.total);
  h += `<h4>Space for code patches</h4>
    <p class="note">Bank 6 ends with a run of unused bytes at <b>${fs.at}</b>,
    and everything that appends code shares it &mdash; the two patches below and
    the test-build patcher. Edits that only change an existing operand cost
    nothing here, which is most of this editor.</p>
    <div class="budget">
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="bnums"><b>${left}</b> of ${fs.total} bytes free</div>
    </div>`;
  for (const o of fs.occupants) {
    h += `<div class="row"><span class="k">${o.name}</span>` +
         `<span class="v" style="font-size:11px">${o.bytes} bytes` +
         (o.installed ? ` at ${o.at}` : '') +
         `<span style="color:${o.installed ? 'var(--accent)' : 'var(--faint)'}"> &middot; ${
            o.installed ? 'installed' : 'not installed'}</span></span></div>`;
  }
  h += `<p class="note">A test build needs <b>${fs.patcher_min}</b> bytes plus
    5 per item and 5 for boss flags, so ${left} leaves room for
    <b>${Math.max(0, Math.floor((left - fs.patcher_min) / 5))}</b> granted items.
    Starting health and purity are free.</p>`;

  const ww = await api('/api/waterwalk');
  h += `<h4>Water walk</h4>
    <p class="note">Bit 2 of a terrain byte marks water, and the engine never
    tests it &mdash; the collision check is only <code>AND #$03</code>. The
    necklace crossing is a hardcoded rectangle in room <b>$01</b> instead, so
    the fountain there is passable and identical water in
    <b>$02 $03 $07 $0F $11</b> is not.</p>
    <div class="row"><span class="k" title="${ww.at}">read bit 2 instead <em class="cost">21 b</em></span>
      <input type="checkbox" id="f_water" ${ww.on ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${ww.state}</span></div>
    <p class="note">Gives the bit its obvious meaning: a 21-byte shim at
    ${ww.at} asks, where terrain has decided to block, whether the square is
    water and whether the necklace is the <em>selected</em> item. The original
    rectangle still works, so nothing that used to be crossable stops being.</p>`;

  const dbg = await api('/api/debughook');
  h += `<h4>Debug hook</h4>
    <p class="note"><code>DbgPauseHook</code> counts presses of the first button
    while the console <b>PAUSE</b> switch is held, and at four refills blood
    purity and grants +8 maximum health. <b>As shipped it can never get there</b>:
    steps 1 and 2 branch into data, and so do both wrong-button exits. The IRQ
    vector is the reset entry, so each is a soft reboot &mdash; the counter can be
    advanced exactly once before the game restarts.</p>
    <div class="row"><span class="k">repair it <em class="cost free">in place</em></span>
      <input type="checkbox" id="f_dbg" ${dbg.repaired ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:${dbg.state === 'modified' ? 'var(--accent)' : 'var(--faint)'}">${dbg.state}</span></div>
    <p class="note">Four branch operands, nothing else: steps 1 and 2 join the
    button reader, and the wrong-button exits go to the routine's own RTS.
    ${dbg.repaired ? 'Hold PAUSE and tap the first button four times, with the other buttons released.' : ''}</p>`;

  const st = await api('/api/start');
  h += `<h4>New game</h4>
    <p class="note">What a fresh run begins with. Both are the operand of an
    immediate the reset already executes, so changing them <b>costs no space</b>
    &mdash; a test build asking only for these appends no code at all.</p>`;
  for (const v of st.start) {
    h += `<div class="row"><span class="k" title="${v.at}">${v.label}</span>` +
         `<input class="f_start" data-name="${v.name}" value="${hex(v.value)}"` +
         (v.anchored ? '' : ' disabled') + `>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${v.value}` +
         (v.value !== v.default ? ` · was ${hex(v.default)}` : '') + `</span></div>`;
    if (v.note) h += `<p class="note">${v.note}</p>`;
  }

  h += `<h4>Fire rate</h4>
    <p class="note">Frames between shots, by weapon level. <b>Lower is faster</b>,
    so the weapon progression is partly a fire-rate upgrade &mdash; the mega
    blaster does the same damage per hit as the axe and simply lands three times
    as often.</p>`;
  for (const w of d.weapons) {
    h += `<div class="row"><span class="k">${w.name}</span>` +
         `<input class="f_delay" data-level="${w.level}" value="${hex(w.delay)}">` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${w.delay} frames</span></div>`;
  }

  h += `<h4>Item references</h4>
    <p class="note">Every instruction that names one inventory slot, and what it
    decides. The inventory is flat (<code>$1F3D + id</code>), so pointing one at a
    different item is a one-byte change. <b>sel</b> entries test the item that is
    <em>selected</em> on the Grampa screen rather than merely carried.</p>`;

  for (const id of Object.keys(byItem).sort((x, y) => x - y)) {
    const name = ITEMS[id] || ('slot ' + hex(+id));
    h += `<h4 style="color:var(--dim)">${hex(+id)} ${name} &mdash; ${byItem[id].length}</h4>`;
    for (const r of byItem[id]) {
      const opts = Object.entries(ITEMS).map(([i, nm]) =>
        `<option value="${i}" ${+i === r.item ? 'selected' : ''}>${hex(+i)} ${nm}</option>`).join('');
      h += `<div class="row"><span class="k" title="${r.mn} ${r.kind}">${r.at}` +
           (r.kind === 'sel' ? ' <b>sel</b>' : '') +
           (r.writes ? ' <b>w</b>' : '') + `</span>` +
           `<select class="f_ref" data-at="${r.at}"` +
           (r.anchored ? '' : ' disabled title="opcode moved -- editing refused"') +
           `>${opts}</select></div>`;
      if (r.note) h += `<p class="note">${r.note}</p>`;
    }
  }
  h += `<p class="note"><b>w</b> marks a write rather than a test &mdash;
    repointing one of those redirects where a count is stored, not what is read.
    The diamond and the mega blaster appear nowhere: nothing in the cartridge
    ever reads either slot.</p>`;
  $('#itemprops').innerHTML = h;

  document.querySelectorAll('.f_ref').forEach(sel => sel.onchange = async e => {
    try { await api('/api/itemref', {at:e.target.dataset.at, item:+e.target.value});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  $('#f_retick').onchange = async e => {
    try { await api('/api/setmusicretick', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  $('#f_music').onchange = async e => {
    try { await api('/api/setmusictiming', {retime:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  document.querySelectorAll('.f_purity').forEach(inp => inp.onchange = async e => {
    try {
      await api('/api/setpurity', {space:e.target.dataset.space,
                addr:+e.target.dataset.addr, n:+e.target.value});
      showItems(); refreshDiff();
    } catch (err) { toast(err.message, 'bad'); showItems(); }
  });
  $('#f_without').onchange = async e => {
    try { await api('/api/setpuritynecklace', {without:+e.target.value});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  $('#f_necklace').onchange = async e => {
    try { await api('/api/setpuritynecklace', {checks:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  $('#f_hint').onchange = async e => {
    try { await api('/api/setpumpkinhint',
                    {on:e.target.checked, text:$('#f_hinttext').value});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  $('#f_hinttext').onchange = async e => {
    try { await api('/api/setpumpkinhint', {on:true, text:e.target.value});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  const adb = $('#f_actordeath');
  if (adb) adb.onchange = async e => {
    try { await api('/api/setactordeath', {fix:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  const ghb = $('#f_ghost');
  if (ghb) ghb.onchange = async e => {
    try { await api('/api/setghostdeath', {fix:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  const mgb = $('#f_mega');
  if (mgb) mgb.onchange = async e => {
    try { await api('/api/setmegaframes', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  const a4b = $('#f_axe4');
  if (a4b) a4b.onchange = async e => {
    try { await api('/api/setaxefourth', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  const axb = $('#f_axe');
  if (axb) axb.onchange = async e => {
    try { await api('/api/setaxespin', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  const psb = $('#f_pickshim');
  if (psb) psb.onchange = async e => {
    try { await api('/api/setpickupshimmer', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showItems(); }
  };
  $('#f_icons').onchange = async e => {
    try { await api('/api/seticonfixes', {fix:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  $('#f_flip').onchange = async e => {
    try { await api('/api/setcompactflip', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  $('#f_water').onchange = async e => {
    try { await api('/api/setwaterwalk', {on:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  $('#f_dbg').onchange = async e => {
    try { await api('/api/setdebughook', {repair:e.target.checked});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
  document.querySelectorAll('.f_start').forEach(inp => inp.onchange = async e => {
    try { await api('/api/setstart', {name:e.target.dataset.name,
                                       value:parseInt(e.target.value.replace('$',''), 16)});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  document.querySelectorAll('.f_hp').forEach(inp => inp.onchange = async e => {
    try { await api('/api/healthrule', {name:e.target.dataset.name,
                                         value:parseInt(e.target.value.replace('$',''), 16)});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  document.querySelectorAll('.f_delay').forEach(inp => inp.onchange = async e => {
    try { await api('/api/weapondelay', {level:+e.target.dataset.level,
                                          delay:parseInt(e.target.value.replace('$',''), 16)});
          showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
}


/* ---------------------------------------------------------------- bosses */
async function showBosses() {
  const d = await api('/api/bosses');
  let h = `<p class="note">Each fight is a 32-byte setup record. Health is a hit
    count rather than a pool: every weapon takes exactly <b>one point per hit</b>,
    so the axe and the mega blaster differ only in how often they land &mdash; and
    the knife is refused outright.</p>`;

  for (const b of d.bosses) {
    h += `<h4>${b.n} ${b.name} <span style="color:var(--faint)">${b.at}</span></h4>`;
    h += `<div class="row"><span class="k">contact damage</span>` +
         `<input class="f_boss" data-n="${b.n}" data-f="contact" value="${hex(b.contact)}">` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${b.contact} health</span></div>`;
    for (const f of b.fields) {
      h += `<div class="row"><span class="k">${f.label}</span>` +
           `<input class="f_boss" data-n="${b.n}" data-f="${f.key}" value="${hex(f.value)}">` +
           `<span class="v" style="font-size:11px;color:var(--faint)">${f.value}</span></div>`;
      if (f.note) h += `<p class="note">${f.note}</p>`;
    }
  }

  const wk = await apiSoft('/api/bossbox');
  if (wk) {
  h += `<h4>The weak spot</h4>
    <p class="note">Four bytes of the setup record are the hitbox:
    <code>+2/+3</code> are the long-axis edges as offsets from
    <code>boss_pos</code>, <code>+4/+5</code> the cross-axis edges.
    <code>BossVsProjectiles</code> tests a shot against exactly those, so this
    <em>is</em> the weak spot.</p>
    <p class="note">Only Dr Evil's marks can be tied to the picture from the ROM
    alone &mdash; the other two portraits are narrower than the screen, so the
    window origin is not the blit column and their horizontal placement on the
    reference page is observation, not derivation. Everything here is therefore
    shown as the raw byte and its <b>distance from stock</b>: shift what is
    there rather than aiming at a screen coordinate.</p>`;
  for (const b of wk.boxes) {
    h += `<h4>${b.n} ${b.name} &mdash; ${b.size.long} &times; ${b.size.cross}` +
         (b.live ? ` <span style="color:var(--faint)">long edges overwritten every frame</span>` : '') +
         `</h4>`;
    for (const f of b.fields) {
      h += `<div class="row"><span class="k">${f.label}</span>` +
           `<input class="f_bbox" data-n="${b.n}" data-k="${f.key}" value="${hex(f.value)}">` +
           `<span class="v" style="font-size:11px;color:var(--faint)">${f.at} &middot; ` +
           `stock ${hex(f.stock)}${f.shift ? ` &middot; <b>${f.shift > 0 ? '+' : ''}${f.shift}</b>` : ''}</span></div>`;
    }
    for (const ax of ['long', 'cross']) {
      h += `<div class="row"><span class="k">shift ${ax} axis</span>` +
           `<button class="minor f_bshift" data-n="${b.n}" data-a="${ax}" data-by="-1">&minus;1</button>` +
           `<button class="minor f_bshift" data-n="${b.n}" data-a="${ax}" data-by="1">+1</button>` +
           `<button class="minor f_bshift" data-n="${b.n}" data-a="${ax}" data-by="-8">&minus;8</button>` +
           `<button class="minor f_bshift" data-n="${b.n}" data-a="${ax}" data-by="8">+8</button></div>`;
    }
  }

  h += `<h4>Dr Evil's two windows</h4>
    <p class="note">He is the only boss that moves his own hitbox: bit 7 of
    <code>$45</code> picks a base, and the width is added to it. The shot leaves
    whichever ear is currently weak, so a window and its shot offset want moving
    together &mdash; the tell and the threat are the same thing.</p>`;
  for (const e of wk.ears) {
    h += `<div class="row"><span class="k">${e.label}</span>` +
         `<input class="f_bear" data-k="${e.key}" value="${hex(e.value)}"` +
         (e.anchored ? '' : ' disabled title="opcode moved -- editing refused"') + `>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${e.at} &middot; ` +
         `stock ${hex(e.stock)}${e.shift ? ` &middot; <b>${e.shift > 0 ? '+' : ''}${e.shift}</b>` : ''}</span></div>`;
    if (e.note) h += `<p class="note">${e.note}</p>`;
  }

  h += `<h4>The portraits</h4>
    <p class="note">There is no arena: the only thing blitted is the boss
    itself, one large picture pasted into the character map. Each cell is a
    character number; <code>$00</code> is empty. Pick a character from the
    tray, then paint on the portrait &mdash; drag to fill, right-click to
    erase.</p>`;
  for (const a of wk.art) {
    h += `<div class="row"><span class="k">${a.n} ${a.name}</span>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${a.w}&times;${a.h} ` +
         `at ${a.data}, blitted to column ${a.col} row ${a.row}</span></div>`;
    h += `<div class="bossart" id="bossart${a.n}"></div>`;
  }
  }

  h += `<h4>Victory</h4>
    <p class="note">What winning a fight is worth, applied by
    <code>BossSequenceReward</code>.</p>`;
  for (const w of d.win) {
    h += `<div class="row"><span class="k" title="${w.at}">${w.label}</span>` +
         `<input class="f_bosswin" data-name="${w.name}" value="${hex(w.value)}"` +
         (w.anchored ? '' : ' disabled title="opcode moved -- editing refused"') + `>` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${w.value}` +
         (w.value !== w.default ? ` · was ${hex(w.default)}` : '') + `</span></div>`;
    h += `<p class="note">${w.note}</p>`;
  }
  $('#bossprops').innerHTML = h;

  document.querySelectorAll('.f_boss').forEach(inp => inp.onchange = async e => {
    try { await api('/api/boss', {n:+e.target.dataset.n, field:e.target.dataset.f,
                                   value:parseInt(e.target.value.replace('$',''), 16)});
          showBosses(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  document.querySelectorAll('.f_bbox').forEach(inp => inp.onchange = async e => {
    try { await api('/api/setbossbox', {n:+e.target.dataset.n, key:e.target.dataset.k,
                    value:parseInt(e.target.value.replace('$',''), 16)});
          showBosses(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showBosses(); }
  });
  document.querySelectorAll('.f_bshift').forEach(b => b.onclick = async () => {
    try { await api('/api/setbossbox', {n:+b.dataset.n, axis:b.dataset.a,
                                        shift:+b.dataset.by});
          showBosses(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  document.querySelectorAll('.f_bear').forEach(inp => inp.onchange = async e => {
    try { await api('/api/setbossear', {key:e.target.dataset.k,
                    value:parseInt(e.target.value.replace('$',''), 16)});
          showBosses(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); showBosses(); }
  });
  for (const a of (wk.art || [])) mountBossArt(a.n);
  document.querySelectorAll('.f_bosswin').forEach(inp => inp.onchange = async e => {
    try { await api('/api/bosswin', {name:e.target.dataset.name,
                                      value:parseInt(e.target.value.replace('$',''), 16)});
          showBosses(); showItems(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
}


/* ------------------------------------------------------ terrain properties */
/* Painting changes how a tile looks; this changes what it does. The grid holds
   a character number and the property table is indexed by (cell >> 1), so two
   adjacent characters always share one property. */
async function showProps2() {
  const p = await api('/api/props', {kind:room.kind});
  const live = p.rows.filter(r => r.chars.length);
  let h = `<h4>Terrain properties</h4>
    <p class="note">Table <b>${hex(p.addr, 4)}</b>, shared by <b>${p.rooms} rooms</b>.
    Bits 0-1 are the collision class &mdash; <b>3</b> blocks everywhere, 1 and 2
    block only their half of the cell diagonal, 0 is open ground. Bit 7 makes the
    square scripted instead: a door, the well, the hurting ground or the win.
    Two adjacent characters share one entry, so this is coarser than the painter.</p>
    <p class="note">${live.length} of 128 entries are reached by tiles in this room.</p>`;
  for (const r of live) {
    h += `<div class="prow">` +
         `<span class="ptiles" data-chars="${r.chars.join(',')}"></span>` +
         `<input class="f_prop" data-index="${r.index}" value="${hex(r.value)}">` +
         `<span class="pwhat">${r.event || r.collision}` +
         (r.water ? ` <b class="wet">water</b>` : '') +
         `<span class="pidx">${hex(r.index)}</span></span></div>`;
  }
  $('#roomprops').insertAdjacentHTML('beforeend', h);
  drawPropTiles();
  document.querySelectorAll('.f_prop').forEach(inp => inp.onchange = async e => {
    try { await api('/api/setprop', {kind:room.kind, index:+e.target.dataset.index,
                                      value:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
}


/* Each property governs a pair of characters, so show the tiles it actually
   controls in this room rather than their numbers -- the grid stores character
   numbers and the property index is that number shifted right, which is hard to
   hold in your head while painting. */
function drawPropTiles(z) {
  z = z || 2;
  const cols = pal[Math.min(BANDS - 1, 5)];
  document.querySelectorAll('.ptiles').forEach(host => {
    const chars = (host.dataset.chars || '').split(',').filter(x => x !== '')
                    .map(Number).slice(0, 2);
    host.innerHTML = '';
    for (const ch of chars) {
      const cv = document.createElement('canvas');
      cv.width = CHAR_W * z; cv.height = CHAR_H * z;
      cv.title = 'character ' + hex(ch);
      const ctx = cv.getContext('2d');
      ctx.fillStyle = '#14110f';
      ctx.fillRect(0, 0, cv.width, cv.height);
      for (let ln = 0; ln < CHAR_H; ln++) {
        const pair = glyphLine(ch, ln);
        for (let half = 0; half < 2; half++) {
          for (let p = 0; p < 4; p++) {
            const v = (pair[half] >> (6 - 2 * p)) & 3;
            if (!v) continue;
            const c = cols[v - 1];
            ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
            ctx.fillRect((half * 4 + p) * z, ln * z, z, z);
          }
        }
      }
      host.appendChild(cv);
    }
  });
}

/* ------------------------------------------------------------------ doors */
async function showDoors() {
  const d = await api('/api/doors');
  let h = `<h4>Scripted doors</h4>
    <p class="note">A door is a terrain property with bit 7 set; these are the
    destinations it jumps to, and the conditions on them. Which squares are doors
    at all is set in the <b>Room</b> tab's property table.</p>`;
  for (const x of d.doors) {
    h += `<div class="row"><span class="k" title="${x.at}">${hex(x.code)} ${x.where}</span>` +
         `<input class="f_door" data-at="${x.at}" value="${hex(x.dest)}"` +
         (x.anchored ? '' : ' disabled') + `></div>`;
    if (x.note) h += `<p class="note">${x.note}</p>`;
  }
  h += `<h4>Door gates</h4>`;
  for (const g of d.gates) {
    h += `<div class="row"><span class="k" title="${g.at}">${g.label}</span>` +
         `<input class="f_dgate" data-name="${g.name}" value="${hex(g.value)}"` +
         (g.anchored ? '' : ' disabled') + `></div>`;
    h += `<p class="note">${g.note}</p>`;
  }
  h += `<p class="note">The three boss doors are gated on <code>boss_flags</code>
    too, and stop working once their boss is beaten &mdash; that is why a cleared
    boss room cannot be re-entered.</p>`;
  $('#exitprops').insertAdjacentHTML('beforeend', h);

  document.querySelectorAll('.f_door').forEach(inp => inp.onchange = async e => {
    try { await api('/api/door', {at:e.target.dataset.at,
                                   dest:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
  document.querySelectorAll('.f_dgate').forEach(inp => inp.onchange = async e => {
    try { await api('/api/doorgate', {name:e.target.dataset.name,
                                       value:parseInt(e.target.value.replace('$',''), 16)});
          await selectRoom(room.kind); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  });
}

/* ------------------------------------------------------------------- text */
let allTexts = null;
async function showTexts() {
  if (!allTexts) allTexts = (await api('/api/texts')).texts;
  const q = ($('#textfilter').value || '').trim().toUpperCase();
  const list = q ? allTexts.filter(t => t.text.toUpperCase().includes(q)) : allTexts;

  let h = `<p class="note">${allTexts.length} records. Records are packed end to
    end, so replacement text may be <b>shorter but never longer</b> &mdash; a short
    one is padded with spaces. Control codes: <code>|</code> newline,
    <code>&amp;</code> new page, <code>^</code> apostrophe, <code>*</code> glyph.</p>
    <p class="note"><b>Shimmer</b> is the record's terminator byte.
    <code>$FE</code> puts <code>$FF</code> in the mask the display interrupt
    ANDs the frame counter with before writing the banner's colour, so the words
    pulse; <code>$FF</code> leaves the mask at zero and they sit still. Every
    stock item pickup shimmers. Framing A records are not drawn by that routine,
    so they have none.</p>
    <p class="note"><b>Hold</b> is the record's second parameter byte. It lands
    in <code>ram_1E7A</code>, which <code>f6:$40CF</code> counts down once every
    32 frames &mdash; so each step is a little over half a second, and
    <code>$00</code> means the banner gives way as soon as anything else asks
    for it. The pickups use <code>$96</code>.</p>`;
  if (q) h += `<p class="note">${list.length} matching.</p>`;
  for (const t of list.slice(0, 120)) {
    const hold = `<label class="shim">hold <input type="text" class="f_hold"
           data-space="${t.space}" data-addr="${t.addr}"
           value="${hex(t.p2 || 0)}" style="max-width:56px"></label>`;
    const shim = (t.framing === 'B' && t.term !== undefined
      ? `<label class="shim"><input type="checkbox" class="f_shim"
           data-space="${t.space}" data-addr="${t.addr}"
           ${t.shimmer ? 'checked' : ''}> shimmer
           <em>$${(t.term || 0).toString(16).toUpperCase()}</em></label>`
      : `<span class="shim off">framing A &mdash; no shimmer</span>`) + hold;
    h += `<div class="trec"><div class="thead">${t.at} · ${t.framing} · ${t.capacity} chars${shim}</div>` +
         `<textarea class="f_text" data-space="${t.space}" data-addr="${t.addr}" ` +
         `maxlength="${t.capacity}" rows="2">${t.text.replace(/</g,'&lt;')}</textarea></div>`;
  }
  if (list.length > 120) h += `<p class="note">Showing the first 120 &mdash; use the filter.</p>`;
  $('#textprops').innerHTML = h;

  document.querySelectorAll('.f_hold').forEach(inp => inp.onchange = async e => {
    try {
      await api('/api/settextparam', {space:e.target.dataset.space,
                addr:+e.target.dataset.addr,
                p2:parseInt(e.target.value.replace('$',''), 16)});
      allTexts = null; showTexts(); refreshDiff();
    } catch (err) { toast(err.message, 'bad'); allTexts = null; showTexts(); }
  });

  document.querySelectorAll('.f_shim').forEach(cb => cb.onchange = async e => {
    try {
      await api('/api/settextshimmer', {space:e.target.dataset.space,
                addr:+e.target.dataset.addr, shimmer:e.target.checked});
      allTexts = null; showTexts(); refreshDiff();
    } catch (err) { toast(err.message, 'bad'); allTexts = null; showTexts(); }
  });

  document.querySelectorAll('.f_text').forEach(ta => ta.onchange = async e => {
    try {
      await api('/api/settext', {space:e.target.dataset.space,
                                  addr:+e.target.dataset.addr, text:e.target.value});
      allTexts = null; showTexts(); refreshDiff();
      toast('Saved into the record.', 'good');
    } catch (err) { toast(err.message, 'bad'); }
  });
}


/* ------------------------------------------------------------------ music */
/* Three levels: songs hold two voice tracks, tracks hold patterns, patterns
   hold two-byte notes. Byte 1 carries waveform and pitch together because AUDF
   is a five-bit register -- the chip keeps the low five and the engine reads
   the discarded top three as the timbre. */
let songs = null, curSong = 4;
const WAVES = ['0 saw-ish', '1 pure', '2 buzz', '3 poly4', '4 poly5', '5 poly9',
               '6 div31', '7 low'];

async function showMusic() {
  if (!songs) songs = (await api('/api/songs')).songs;
  const s = songs[curSong];

  let h = `<div class="row"><span class="k">song</span>
    <select id="f_song">${songs.map(x =>
      `<option value="${x.song}" ${x.song===curSong?'selected':''}>${x.song} &mdash; ${x.name}</option>`).join('')}</select></div>`;
  h += `<p class="note">Table entry ${s.at}${s.bank !== null ? `, patterns in bank b${s.bank}` : ''}.
    A note is two bytes: instrument and duration index in the first, waveform and
    pitch in the second. <b>Patterns are packed</b>, so values can change but the
    note count cannot.</p>`;
  h += `<div class="row"><span class="k">preview</span>
    <button id="f_play" class="primary" style="padding:4px 12px">Play</button>
    <span class="v" style="font-size:11px;color:var(--faint)">renders from your edits</span></div>
    <audio id="f_audio" style="display:none"></audio>`;

  s.voices.forEach((v, vi) => {
    h += `<h4>Voice ${vi}${v.ptr ? ` &mdash; $${v.ptr.toString(16).toUpperCase()}` : ''}</h4>`;
    if (v.error) { h += `<p class="note">${v.error}</p>`; return; }
    if (!v.ptr) { h += `<p class="note">This voice is silent in this song.</p>`; return; }
    v.patterns.forEach((p, pi) => {
      h += `<div class="thead">pattern ${pi} at ${p.at} &middot; ${p.count} notes</div>`;
      h += `<div class="notes">` + p.notes.map((n, ni) =>
        `<button class="note-cell${n.rest ? ' rest' : ''}" data-space="${n.space}"
           data-addr="${n.at}" data-v="${vi}" data-p="${pi}" data-n="${ni}"
           title="b0 $${hex(n.b0).slice(1)} b1 $${hex(n.b1).slice(1)}">${
             n.rest ? '&middot;' : n.pitch}</button>`).join('') + `</div>`;
    });
    if (v.terminator !== null) {
      const t = v.terminator;
      h += `<p class="note">Terminator ${hex(t)} &mdash; ${
        t === 0 ? 'loop from the top' : t >= 0x80 ? 'stop' : `chain to song ${t - 1}`}.</p>`;
    }
  });
  h += `<div id="noteedit"></div><div id="sfxbox"></div>`;
  $('#musicprops').innerHTML = h;
  showSfx();

  $('#f_song').onchange = e => { curSong = +e.target.value; showMusic(); };
  $('#f_play').onclick = () => {
    const au = $('#f_audio');
    au.src = '/api/songwav/' + curSong + '?t=' + Date.now();
    au.play().catch(err => toast('Could not play: ' + err.message, 'bad'));
    toast('Rendering song ' + curSong + '\u2026');
  };
  document.querySelectorAll('.note-cell').forEach(b => b.onclick = () => {
    document.querySelectorAll('.note-cell').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    editNote(+b.dataset.v, +b.dataset.p, +b.dataset.n);
  });
}


/* ---------------------------------------------------------- sound effects */
/* Writing an id to sfx_request is the whole interface: the tick looks it up in
   a pointer table and plays the stream. So there are two things to edit --
   which id each event asks for, and what each stream sounds like. */
async function showSfx() {
  const refs = (await api('/api/sfxrefs')).refs;
  const d = await api('/api/sfx');

  let h = `<h4>Sound effects</h4>
    <p class="note">An effect is a byte stream in ${d.block}, played one byte
    per frame on channel&nbsp;0. <code>$00</code> ends it, a byte under
    <code>$10</code> sets the waveform and costs no frame, and anything else is
    one frame &mdash; the whole byte is the pitch and its top four bits are the
    volume. Requests replace whatever is playing; there is no mixing.</p>`;

  if (d.orphans.length) {
    h += `<p class="note"><b>${d.orphans.length} streams nothing points at</b>
      &mdash; ${d.orphans.join(', ')}. They are shaped like the rest and sit
      between the ones in use, so a neighbouring effect may grow over them.</p>`;
  }

  h += `<h4>What each event asks for</h4>`;
  for (const r of refs) {
    h += `<div class="row"><span class="k">${r.what || r.at}</span>` +
         `<input class="f_sfxref" data-space="${r.space}" data-addr="${r.addr}" ` +
         `value="${hex(r.id)}" style="max-width:66px">` +
         `<span class="v" style="font-size:11px;color:var(--faint)">${r.at}</span></div>`;
  }
  h += `<p class="note">Weapon fire is not here: <code>f6:$5046</code> computes
    its id as <code>weapon_level + 1</code> rather than naming one, which is why
    ids <code>$01</code>-<code>$04</code> all point at the same stream.</p>`;

  h += `<h4>The streams</h4>`;
  for (const st of d.streams) {
    const who = st.used_by.length
      ? st.used_by.map(i => hex(i)).join(' ')
      : '<em>nothing</em>';
    h += `<div class="trec"><div class="thead">${st.at} · ${st.length} bytes ·
      room for ${st.capacity} · played by ${who}</div>` +
      `<input class="f_sfx" data-addr="${st.addr}" ` +
      `value="${st.bytes.map(b => b.toString(16).toUpperCase().padStart(2,'0')).join(' ')}"></div>`;
  }
  $('#sfxbox').innerHTML = h;

  document.querySelectorAll('.f_sfxref').forEach(inp => inp.onchange = async e => {
    try {
      await api('/api/setsfxref', {space:e.target.dataset.space,
                addr:+e.target.dataset.addr,
                id:parseInt(e.target.value.replace('$',''), 16)});
      showSfx(); refreshDiff();
    } catch (err) { toast(err.message, 'bad'); showSfx(); }
  });

  document.querySelectorAll('.f_sfx').forEach(inp => inp.onchange = async e => {
    const bytes = e.target.value.trim().split(/[\s,]+/)
                    .filter(x => x).map(x => parseInt(x.replace('$',''), 16));
    if (bytes.some(isNaN)) { toast('Bytes must be hex, space separated.', 'bad');
                             return showSfx(); }
    try {
      await api('/api/setsfx', {addr:+e.target.dataset.addr, bytes});
      showSfx(); refreshDiff();
    } catch (err) { toast(err.message, 'bad'); showSfx(); }
  });
}

function editNote(vi, pi, ni) {
  const n = songs[curSong].voices[vi].patterns[pi].notes[ni];
  const dur = [96,72,64,48,36,32,24,18,16,12,9,8,6,4,3,2];
  let h = `<h4>Note ${ni} &mdash; ${n.space}:${hex(n.at,4)}</h4>
    <div class="row"><span class="k">rest</span>
      <input type="checkbox" id="n_rest" ${n.rest?'checked':''} style="width:auto"></div>
    <div class="row"><span class="k">pitch</span>
      <input type="range" id="n_pitch" min="0" max="31" value="${n.pitch}" style="width:120px">
      <span class="v" id="n_pitchv">${n.pitch}</span></div>
    <div class="row"><span class="k">waveform</span>
      <select id="n_wave">${WAVES.map((w,i)=>
        `<option value="${i}" ${i===n.wave?'selected':''}>${w}</option>`).join('')}</select></div>
    <div class="row"><span class="k">instrument</span>
      <input id="n_instr" value="${n.instrument}" style="width:50px"></div>
    <div class="row"><span class="k">duration</span>
      <select id="n_dur">${dur.map((f,i)=>
        `<option value="${i}" ${i===n.dur?'selected':''}>${i} &mdash; ${f} frames</option>`).join('')}</select></div>
    <p class="note">Pitch is five bits because that is all AUDF holds; the
    waveform is the three bits above it in the same byte.</p>`;
  $('#noteedit').innerHTML = h;

  $('#n_pitch').oninput = e => { $('#n_pitchv').textContent = e.target.value; };
  const send = async extra => {
    try {
      await api('/api/setnote', Object.assign(
        {space:n.space, addr:n.at}, extra));
      songs = null; await showMusic(); refreshDiff();
    } catch (e) { toast(e.message, 'bad'); }
  };
  $('#n_rest').onchange  = e => send({rest:e.target.checked});
  $('#n_pitch').onchange = e => send({pitch:+e.target.value, rest:false});
  $('#n_wave').onchange  = e => send({wave:+e.target.value, rest:false});
  $('#n_instr').onchange = e => send({instrument:+e.target.value});
  $('#n_dur').onchange   = e => send({dur:+e.target.value});
}

async function showReticle() {
  const r = await api('/api/reticleleg');
  const h = `<h4>The reticle leg</h4>
    <p class="note">The last frame of a special actor's death draws four
    eight-pixel fragments, and the fourth names <b>gfx $EE</b> &mdash; which is
    the same eight pixels the Grampa screen uses for its item-select reticle. A
    targeting bracket appears briefly as the corpse's right leg. It is in the
    data at ${r.at}, not a rendering mistake.</p>
    <div class="row"><span class="k">use a melt fragment <em class="cost free">1 byte</em></span>
      <input type="checkbox" id="f_retic" ${r.fixed ? 'checked' : ''} style="width:auto">
      <span class="v" style="font-size:11px;color:var(--faint)">${r.state}</span></div>
    <p class="note">The artwork has no fourth fragment: <code>$EC</code> and
    <code>$EE</code> are the two halves of one 16-pixel cell and the right half
    <em>is</em> the reticle. So the repair points the fourth fragment at
    <code>$EC</code> too, giving the corpse two of the same melt piece rather
    than a bracket. Nothing moves; only which eight pixels are fetched.</p>`;
  $('#actorprops').insertAdjacentHTML('beforeend', h);
  $('#f_retic').onchange = async e => {
    try { await api('/api/setreticleleg', {fix:e.target.checked});
          showActors(); refreshDiff(); }
    catch (err) { toast(err.message, 'bad'); }
  };
}

/* ------------------------------------------------------------------ diff */
/* ----------------------------------------------------------------- patches */
function patchPanel(d) {
  return `<h4>Patch file</h4>
    <p class="note">A patch carries only the bytes that differ &mdash; a handful
    against a 128K cartridge &mdash; plus a CRC32 of the ROM it was made from,
    the ROM it produces, and itself. The format is <b>BPS</b>, which Floating
    IPS, RomPatcher.js and beat all read, so a patch from here works with them
    and theirs works here.</p>
    <p class="note">Patches are made against the <b>cartridge data alone</b>,
    with the 128-byte <code>.a78</code> header left out. The same dump ships
    behind different headers &mdash; the Europe file and Trebor's PAL hold
    identical data but declare different cart types &mdash; and including the
    header would make a patch from one refuse the other for no reason that
    matters. One patch now fits either, and the header of whatever you apply it
    to is kept. A patch still only fits its own region, because NTSC and PAL
    genuinely differ.</p>
    <div class="row"><span class="k">note</span>
      <input id="p_note" placeholder="what this changes" style="width:150px"></div>
    <div class="row"><span class="k">write</span>
      <button id="p_save" ${d.count ? '' : 'disabled'}>Export .bps</button>
      <span class="v" style="font-size:11px;color:var(--faint)">${
        d.count ? d.count + ' bytes' : 'nothing changed yet'}</span></div>
    <div class="row"><span class="k">read</span>
      <button id="p_load">Load .bps&hellip;</button></div>
    <p class="note">Loading a patch applies it over the cartridge <b>as it is on
    disk</b>, replacing anything unsaved. If its checksum does not match this
    ROM you are told what it expects and can apply anyway, at your own risk.</p>
    <div id="p_result"></div>`;
}

function wirePatch() {
  const el = $('#p_save');
  if (el) el.onclick = async () => {
    const p = prompt('Write the patch to:', '');
    if (p === null) return;
    try {
      const r = await api('/api/exportpatch',
                          Object.assign({note: $('#p_note').value}, p ? {path: p} : {}));
      toast(`Wrote ${r.size} bytes covering ${r.changed} changed bytes.`, 'good');
      $('#p_result').innerHTML = `<p class="note">${r.path}</p>`;
    } catch (e) { toast(e.message, 'bad'); }
  };
  const ld = $('#p_load');
  if (ld) ld.onclick = async () => {
    const p = prompt('Patch file to load:', '');
    if (!p) return;
    let info;
    try { info = await api('/api/patchinfo', {path: p}); }
    catch (e) { toast(e.message, 'bad'); return; }
    $('#p_result').innerHTML =
      `<p class="note">${info.size} bytes${info.note ? ' &mdash; ' + info.note : ''}<br>
       expects a ${info.source_size}-byte ROM, CRC32 ${info.source_crc}<br>
       yours is ${info.your_crc} &mdash; <b style="color:${info.matches
         ? 'var(--ok)' : 'var(--accent)'}">${info.matches ? 'matches' : 'does NOT match'}</b></p>`;
    if (!info.matches &&
        !confirm('This patch was made against a different ROM.\n\n' +
                 'It expects CRC32 ' + info.source_crc + ' and yours is ' +
                 info.your_crc + '.\n\nApply it anyway?')) return;
    try {
      const r = await api('/api/importpatch', {path: p, force: !info.matches});
      (r.warnings || []).forEach(w => toast(w, 'bad'));
      await selectRoom(room.kind); refreshDiff();
      toast(`Applied: ${r.changed} bytes differ from the file on disk.`, 'good');
    } catch (e) { toast(e.message, 'bad'); }
  };
}

async function refreshDiff() {
  const d = await api('/api/changes');
  $('#diffcount').textContent = d.count;
  $('#diffbox').classList.toggle('dirty', d.count > 0);
  $('#save').disabled = $('#revert').disabled = d.count === 0;
  $('#difflist').innerHTML = patchPanel(d) + '<h4>Changed bytes</h4>' +
    d.bytes.map(b =>
      `<div><span>rom+${hex(b.off,5)}</span><span>${hex(b.from)}</span>` +
      `<span class="to">&rarr; ${hex(b.to)}</span></div>`).join('') +
    (d.truncated ? '<div>&hellip; and more</div>' : '');
  wirePatch();
  const room_ = rooms.find(r => room && r.kind === room.kind);
  if (room_) drawRoomList();
}

/* ------------------------------------------------------------------ wire */
function init() {
  $('#filter').oninput = drawRoomList;
  $('#textfilter').oninput = () => showTexts();
  $('#zoom').oninput = e => { zoom = +e.target.value; $('#zoomval').textContent = zoom + '×'; render(); };
  $('#disasm').onclick = async () => {
    const b = $('#disasm');
    b.disabled = true; b.textContent = 'Disassembling…';
    try {
      const d = await api('/api/disassemble', {});
      toast(`${d.files.length} listings written to ${d.path}`, 'good');
    } catch (err) { toast(err.message, 'bad'); }
    b.disabled = false; b.textContent = 'Disassemble';
  };

  $('#showgrid').onchange = $('#showseg').onchange = $('#showitem').onchange =
    $('#showcol').onchange = $('#showwater').onchange = $('#showexits').onchange =
    $('#asplayed').onchange = render;

  document.querySelectorAll('.tool').forEach(b => b.onclick = () => {
    document.querySelectorAll('.tool').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); tool = b.dataset.tool;
    $('#view').style.cursor = tool === 'item' ? 'move' : 'crosshair';
  });
  // Tabs are addressable: #bosses opens that panel, and switching tabs keeps
  // the hash in step, so a panel can be linked to and survives a reload.
  function selectTab(name, push) {
    const b = document.querySelector(`.tab[data-tab="${name}"]`);
    const body = document.querySelector(`[data-body="${name}"]`);
    if (!b || !body) return false;
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
    document.querySelectorAll('.tabbody').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    body.classList.add('on');
    if (push && location.hash.slice(1) !== name) location.hash = name;
    if (name === 'diff') refreshDiff();
    return true;
  }
  window.selectTab = selectTab;
  document.querySelectorAll('.tab').forEach(b =>
    b.onclick = () => selectTab(b.dataset.tab, true));
  window.addEventListener('hashchange', () => selectTab(location.hash.slice(1), false));
  if (location.hash.length > 1) selectTab(location.hash.slice(1), false);

  const view = $('#view');
  view.onmousedown = ev => {
    if (!room) return;
    const c = cellAt(ev); if (!c) return;
    if (tool === 'pick') { sel = grid[c.band * COLS + c.col]; drawTiles(); return; }
    if (tool === 'item') { dragging = !!room.item; return; }
    drawing = true; paint(c);
  };
  view.onmousemove = ev => {
    if (!room) return;
    const c = cellAt(ev);
    $('#hint').textContent = c ? `col ${c.col}  band ${c.band}  tile ${hex(grid[c.band*COLS+c.col])}` : '';
    if (drawing && c) paint(c);
  };
  window.onmouseup = async ev => {
    drawing = false;
    if (dragging && room && room.item) {
      dragging = false;
      const r = view.getBoundingClientRect();
      const x = Math.round((ev.clientX - r.left) / zoom);
      const y = Math.round((ev.clientY - r.top) / zoom) + CHAR_H;
      try { await api('/api/item', {kind:room.kind, x, y});
            await selectRoom(room.kind); refreshDiff(); }
      catch (e) { toast(e.message, 'bad'); }
    }
  };

  $('#revert').onclick = async () => {
    if (!confirm('Discard every change and reload the cartridge as it is on disk?')) return;
    await api('/api/revert', {}); await selectRoom(room.kind); refreshDiff();
    $('#warn').hidden = true; toast('Reverted to the file on disk.', 'good');
  };
  $('#save').onclick = async () => {
    const p = prompt('Save the edited cartridge as:', '');
    if (p === null) return;
    try {
      const r = await api('/api/save', p ? {path:p} : {});
      toast(`Saved ${r.changed} changed bytes to ${r.path}`, 'good');
    } catch (e) { toast(e.message, 'bad'); }
  };

  loadRooms().then(refreshDiff).catch(e => toast(e.message, 'bad'));
}

init();

// ---------------------------------------------------------------- boss art
// A portrait is a character grid, exactly like a room's terrain -- so it is
// drawn the same way: decode each cell through the arena's character set and
// colour it from the palette band it lands in. The band matters: the picture
// is pasted into the 100x10 map at (col,row), so a tall boss crosses bands and
// changes colour partway down, which is how the game gets a gradient for free.
const bossArt = {};                    // n -> {a, cs, pick}

function bossGlyph(cs, ch, ln) {
  const o = (ch * CHAR_H + ln) * 2;
  return [cs[o], cs[o + 1]];
}

function paintBossCanvas(cv, a, cs, z) {
  const w = a.w * CHAR_W, h = a.h * CHAR_H;
  cv.width = w * z; cv.height = h * z;
  const ctx = cv.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  const off = document.createElement('canvas');
  off.width = w; off.height = h;
  const octx = off.getContext('2d');
  const img = octx.createImageData(w, h);
  const px = img.data;
  for (let y = 0; y < a.h; y++) {
    // the band this row lands in once blitted at (col,row)
    const band = Math.min(a.palette.length - 1, a.row + y);
    const colours = a.palette[band];
    for (let x = 0; x < a.w; x++) {
      const ch = a.cells[y * a.w + x];
      if (!ch) continue;
      for (let ln = 0; ln < CHAR_H; ln++) {
        const pair = bossGlyph(cs, ch, ln);
        for (let half = 0; half < 2; half++) {
          const byte = pair[half];
          if (!byte) continue;
          for (let i = 0; i < 4; i++) {
            const v = (byte >> (6 - 2 * i)) & 3;
            if (!v) continue;
            const c = colours[v - 1];
            const p = ((y * CHAR_H + ln) * w + x * CHAR_W + half * 4 + i) * 4;
            px[p] = c[0]; px[p + 1] = c[1]; px[p + 2] = c[2]; px[p + 3] = 255;
          }
        }
      }
    }
  }
  octx.putImageData(img, 0, 0);
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.drawImage(off, 0, 0, cv.width, cv.height);
  ctx.strokeStyle = 'rgba(255,255,255,.13)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= a.w; x++) {
    ctx.beginPath(); ctx.moveTo(x * CHAR_W * z + 0.5, 0);
    ctx.lineTo(x * CHAR_W * z + 0.5, cv.height); ctx.stroke();
  }
  for (let y = 0; y <= a.h; y++) {
    ctx.beginPath(); ctx.moveTo(0, y * CHAR_H * z + 0.5);
    ctx.lineTo(cv.width, y * CHAR_H * z + 0.5); ctx.stroke();
  }
}

const BOSS_TRAY_PER = 16;

function paintBossTray(cv, a, cs, sel, z) {
  const per = BOSS_TRAY_PER, n = a.nchars, rows = Math.ceil(n / per);
  cv.width = per * (CHAR_W * z + 1) + 1;
  cv.height = rows * (CHAR_H * z + 1) + 1;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = '#14110f'; ctx.fillRect(0, 0, cv.width, cv.height);
  const colours = a.palette[Math.min(a.palette.length - 1, a.row)];
  for (let ch = 0; ch < n; ch++) {
    const gx = (ch % per) * (CHAR_W * z + 1) + 1;
    const gy = Math.floor(ch / per) * (CHAR_H * z + 1) + 1;
    for (let ln = 0; ln < CHAR_H; ln++) {
      const pair = bossGlyph(cs, ch, ln);
      for (let half = 0; half < 2; half++) {
        for (let i = 0; i < 4; i++) {
          const v = (pair[half] >> (6 - 2 * i)) & 3;
          if (!v) continue;
          const c = colours[v - 1];
          ctx.fillStyle = 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
          ctx.fillRect(gx + (half * 4 + i) * z, gy + ln * z, z, z);
        }
      }
    }
    if (ch === sel) {
      ctx.strokeStyle = '#e8b04b'; ctx.lineWidth = 2;
      ctx.strokeRect(gx - 1, gy - 1, CHAR_W * z + 2, CHAR_H * z + 2);
    }
  }
}

async function mountBossArt(n) {
  const host = $('#bossart' + n);
  if (!host) return;
  const a = await apiSoft('/api/bossart/' + n);
  if (!a) { host.innerHTML = '<p class="note">Could not load this portrait.</p>'; return; }
  const cs = b64(a.charset);
  const st = bossArt[n] = bossArt[n] || {pick: 0};
  st.a = a; st.cs = cs;

  host.innerHTML =
    '<div class="bossrow">' +
      '<div>' +
        '<canvas id="bcv' + n + '" class="bcv"></canvas>' +
        '<p class="bhint">Click to paint &middot; drag to fill &middot; ' +
          'right-click erases to <code>$00</code></p>' +
      '</div>' +
      '<div class="btrayside">' +
        '<div class="bpick">character <b id="bsel' + n + '">$00</b>' +
          '<button class="bclear" data-n="' + n + '">clear</button></div>' +
        '<div class="btraywrap"><canvas id="btray' + n + '" class="btray"></canvas></div>' +
      '</div>' +
    '</div>';

  // The side panel is narrow and the three portraits are 9, 16 and 20 cells
  // wide, so a fixed zoom would make Dr Evil overflow. Fit to the panel and
  // keep it whole -- fractional pixels would blur a character grid.
  // ...but never below 2, or Dr Evil's twenty columns give 8x16 cells that
  // are too small to aim at. Below that the canvas scrolls instead.
  const avail = Math.max(160, host.clientWidth - 20);
  const Z = Math.max(2, Math.min(3, Math.floor(avail / (a.w * CHAR_W))));
  const TZ = 2;
  const cv = $('#bcv' + n), tray = $('#btray' + n);
  const redraw = () => paintBossCanvas(cv, st.a, cs, Z);
  const redrawTray = () => paintBossTray(tray, st.a, cs, st.pick, TZ);
  redraw(); redrawTray();
  $('#bsel' + n).textContent = hex(st.pick);

  tray.onclick = e => {
    const r = tray.getBoundingClientRect();
    const cx = Math.floor((e.clientX - r.left) / (CHAR_W * TZ + 1));
    const cy = Math.floor((e.clientY - r.top) / (CHAR_H * TZ + 1));
    const ch = cy * BOSS_TRAY_PER + cx;
    if (ch < 0 || ch >= st.a.nchars) return;
    st.pick = ch;
    $('#bsel' + n).textContent = hex(ch);
    redrawTray();
  };

  // Painting is optimistic on the canvas and batched into one request per
  // value per stroke, so dragging across forty cells is two calls, not forty.
  let drawing = false, erase = false, touched = new Map();
  const cellAt = e => {
    const r = cv.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left) / (CHAR_W * Z));
    const y = Math.floor((e.clientY - r.top) / (CHAR_H * Z));
    if (x < 0 || y < 0 || x >= st.a.w || y >= st.a.h) return -1;
    return y * st.a.w + x;
  };
  const put = i => {
    if (i < 0) return;
    const v = erase ? 0 : st.pick;
    if (st.a.cells[i] === v) return;
    st.a.cells[i] = v;
    touched.set(i, v);
    redraw();
  };
  const commit = async () => {
    if (!touched.size) return;
    const byValue = new Map();
    for (const [i, v] of touched) {
      if (!byValue.has(v)) byValue.set(v, []);
      byValue.get(v).push(i);
    }
    touched = new Map();
    try {
      for (const [v, idx] of byValue) {
        await api('/api/setbossart', {n: n, index: idx, value: v});
      }
      refreshDiff();
    } catch (err) {
      toast(err.message, 'bad');
      mountBossArt(n);
    }
  };
  cv.oncontextmenu = e => e.preventDefault();
  cv.onmousedown = e => {
    drawing = true; erase = (e.button === 2);
    put(cellAt(e)); e.preventDefault();
  };
  cv.onmousemove = e => { if (drawing) put(cellAt(e)); };
  cv.onmouseup = () => { if (drawing) { drawing = false; commit(); } };
  cv.onmouseleave = () => { if (drawing) { drawing = false; commit(); } };

  host.querySelector('.bclear').onclick = async () => {
    const live = st.a.cells.map((_, i) => i).filter(i => st.a.cells[i] !== 0);
    if (!live.length) return;
    if (!confirm('Clear ' + st.a.name + "'s portrait? " + live.length + ' cells.')) return;
    try {
      await api('/api/setbossart', {n: n, index: live, value: 0});
      mountBossArt(n); refreshDiff();
    } catch (err) { toast(err.message, 'bad'); }
  };
}

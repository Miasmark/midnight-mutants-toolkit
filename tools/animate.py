#!/usr/bin/env python3
"""
Build animated actor strips for the bestiary page.

Each animation is emitted as one horizontal strip PNG with every frame at the
same cell size, driven by a CSS steps() animation on background-position. That
keeps the page self-contained, keeps the pixels sharp, and lets a reduced-motion
preference freeze the first frame -- none of which a GIF gives you.

Frames must be composited onto a common canvas before trimming, or each one
crops to its own bounding box and the sprite jitters as it plays.
"""
import base64
import io

from PIL import Image


def strip(frames, pad=2):
    """frames: list of RGBA images already on a shared canvas. -> (uri, w, h, n)"""
    w = max(f.width for f in frames) + pad * 2
    h = max(f.height for f in frames) + pad * 2
    sheet = Image.new("RGBA", (w * len(frames), h), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * w + (w - f.width) // 2, (h - f.height) // 2), f)
    buf = io.BytesIO()
    sheet.save(buf, "PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return uri, w, h, len(frames)


def markup(frames, dur="0.6s", label="", cap=""):
    if len(frames) == 1:
        uri, w, h, _ = strip(frames)
        img = ('<span class="sprite" style="--fw:%dpx;--fh:%dpx;'
               'background-image:url(%s)" role="img" aria-label="%s"></span>'
               % (w, h, uri, label))
    else:
        uri, w, h, n = strip(frames)
        img = ('<span class="sprite play" style="--fw:%dpx;--fh:%dpx;--n:%d;'
               '--dur:%s;background-image:url(%s)" role="img" aria-label="%s"></span>'
               % (w, h, n, dur, uri, label))
    return ('<figure>%s%s</figure>'
            % (img, '<figcaption>%s</figcaption>' % cap if cap else ""))


CSS = """
  .sprite{display:block;width:var(--fw);height:var(--fh);
          background-repeat:no-repeat;image-rendering:pixelated}
  .sprite.play{animation:spriteplay var(--dur,.6s) steps(var(--n)) infinite}
  @keyframes spriteplay{from{background-position:0 0}
                        to{background-position:calc(var(--fw) * var(--n) * -1) 0}}
  @media (prefers-reduced-motion:reduce){
    .sprite.play{animation:none;background-position:0 0}}
"""

"""Atari 7800 hardware symbols and memory-map helpers."""

# --- TIA (7800 only uses a handful of the 2600 TIA registers) -----------------
TIA = {
    0x01: "INPTCTRL",   # write: bit0 2600/7800 mode, bit1 BIOS/cart map, bit2 MARIA en
    0x08: "INPT0", 0x09: "INPT1", 0x0A: "INPT2", 0x0B: "INPT3",
    0x0C: "INPT4", 0x0D: "INPT5",
    0x15: "AUDC0", 0x16: "AUDC1",
    0x17: "AUDF0", 0x18: "AUDF1",
    0x19: "AUDV0", 0x1A: "AUDV1",
}

# --- MARIA -------------------------------------------------------------------
MARIA = {
    0x20: "BACKGRND", 0x21: "P0C1", 0x22: "P0C2", 0x23: "P0C3",
    0x24: "WSYNC",    0x25: "P1C1", 0x26: "P1C2", 0x27: "P1C3",
    0x28: "MSTAT",    0x29: "P2C1", 0x2A: "P2C2", 0x2B: "P2C3",
    0x2C: "DPPH",     0x2D: "P3C1", 0x2E: "P3C2", 0x2F: "P3C3",
    0x30: "DPPL",     0x31: "P4C1", 0x32: "P4C2", 0x33: "P4C3",
    0x34: "CHARBASE", 0x35: "P5C1", 0x36: "P5C2", 0x37: "P5C3",
    0x38: "OFFSET",   0x39: "P6C1", 0x3A: "P6C2", 0x3B: "P6C3",
    0x3C: "CTRL",     0x3D: "P7C1", 0x3E: "P7C2", 0x3F: "P7C3",
}

# --- RIOT (6532) -------------------------------------------------------------
RIOT = {
    0x0280: "SWCHA",  0x0281: "SWACNT", 0x0282: "SWCHB", 0x0283: "SWBCNT",
    0x0284: "INTIM",  0x0285: "INTFLG",
    0x0294: "TIM1T",  0x0295: "TIM8T",  0x0296: "TIM64T", 0x0297: "T1024T",
}

HW = {}
HW.update(TIA)
HW.update(MARIA)
HW.update(RIOT)
# TIA/MARIA are mirrored at $0100 and $0200
for _base in (0x0100, 0x0200):
    for _a, _n in list(TIA.items()) + list(MARIA.items()):
        HW[_base + _a] = _n + "_m%d" % (_base >> 8)

MARIA_CTRL_BITS = """CTRL: b7 ColorKill  b6-5 DMA(00=?,01=?,10=on,11=off)
      b4 CharWidth(1=1byte)  b3 Border(0=bg,1=black)  b2 Kangaroo
      b1-0 ReadMode(00=160x2/4, 10=320A/320D, 11=320B/320C)"""


def region_of(addr):
    """Coarse classification of a 7800 CPU address."""
    if addr <= 0x001F:
        return "TIA"
    if addr <= 0x003F:
        return "MARIA"
    if addr <= 0x00FF:
        return "RAM_ZP"          # mirror of $2040-$20FF
    if addr <= 0x011F:
        return "TIA"
    if addr <= 0x013F:
        return "MARIA"
    if addr <= 0x01FF:
        return "RAM_STACK"       # mirror of $2140-$21FF
    if addr <= 0x021F:
        return "TIA"
    if addr <= 0x023F:
        return "MARIA"
    if 0x0280 <= addr <= 0x02FF:
        return "RIOT_IO"
    if 0x0480 <= addr <= 0x04FF:
        return "RIOT_RAM"
    if 0x1800 <= addr <= 0x27FF:
        return "RAM"
    if 0x2800 <= addr <= 0x3FFF:
        return "RAM_MIRROR"
    if addr >= 0x4000:
        return "CART"
    return "UNMAPPED"


def sym(addr, width=None):
    """Return a symbolic name for a hardware address, or None."""
    return HW.get(addr)

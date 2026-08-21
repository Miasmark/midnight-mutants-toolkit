# Page $E0 cell identifications.
#   code      -- established from the disassembly
#   play      -- identified visually against the running game
#   code+play -- named by the code and confirmed on screen
#   guess     -- a reading, not a finding
E0 = {
 0x00:("death frame 1","code"), 0x04:("death frame 2","code"),
 0x08:("death frame 3","code"), 0x0C:("death frame 4","code"),
 0x10:("bat","code"), 0x14:("bat, alt","code"),
 0x18:("crow","code+play"), 0x1C:("crow, alt","code+play"),
 0x20:("ghost death, top","play"), 0x24:("ghost death, top","play"),
 0x30:("Grampa, win screen","play"), 0x34:("Grampa, win screen","play"),
 0x38:("ghost, top","play"), 0x3C:("ghost, top","play"),
 0x40:("ghost death, bottom","play"), 0x44:("ghost death, bottom","play"),
 0x50:("Grampa, win screen","play"), 0x54:("Grampa, win screen","play"),
 0x58:("ghost, bottom","play"), 0x5C:("ghost, bottom","play"),
 0x60:("spider walk 1 of 3, dat_5EF9","code+play"),
 0x64:("spider walk 2 of 3, dat_5EF9","code+play"),
 0x68:("spider walk 3 of 3, dat_5EF9","code+play"),
 0x6C:("wolf run, top","play"), 0x70:("wolf run, top","play"),
 0x74:("wolf run, top","play"), 0x78:("wolf run, top (two halves)","play"),
 0x7C:("wolf run, top","play"),
 0x80:("thrown pumpkin","play"), 0x84:("thrown pumpkin","play"),
 0x88:("unreferenced legs; the editor's 4th axe pose","code"),
 0x8C:("wolf run, bottom ($8E on); $8C-$8D unreferenced","code"), 0x90:("wolf run, bottom","play"),
 0x94:("wolf run, bottom","play"), 0x98:("wolf run, bottom (two halves)","play"),
 0x9C:("wolf run, bottom","play"),
 0xA0:("blaster shot","code"), 0xA4:("mega blaster shot","code"),
 0xA8:("mega blaster, frames 3-4, unused ($A8 $AA)","code"),
 0xAC:("knife shot, 1 of 8","code"), 0xB0:("knife shot, 3 of 8","code"),
 0xB4:("knife shot, 5 of 8","code"), 0xB8:("knife shot, 7 of 8","code"),
 0xBC:("axe shot: $BC down/right, $BE left","code"),
 0xC0:("speech bubble: AWE","play"), 0xC4:("speech bubble: SOME","play"),
 0xC8:("bubble edge ($C8) / Grampa's leg ($CA)","play"),
 0xCC:("Grampa's leg ($CC) / axe shot, up ($CE)","code"),
 0xD0:("icons: heart, necklace","play"), 0xD4:("icons: cross, crypt key","play"),
 0xD8:("GA","code"), 0xDC:("ME","code"),
 0xEC:("special-actor melt ($EC) / item-select reticle ($EE)","code"),
 0xF0:("icons: diamond, potion","play"), 0xF4:("icons: pumpkin, lantern","play"),
 0xF8:("OV","code"), 0xFC:("ER","code"),
}
# Resolved from the composite records: the wolf's death is $E0-$EA, and the
# special actors' death records $64/$65 borrow $E4-$EE from the same run.
E0.update({
 0xE0:("wolf, records $47-$48","code"),
 0xE4:("wolf + special-actor melt, records $49-$4A, $64","code"),
 0xE8:("wolf + special-actor melt, records $4B-$4C, $64-$65","code"),
})

# The undead death: dat_455C resolves the player's sprite selector $5E, and for
# $10/$20 -- blood death without the cross -- it names page $E0 cells $10/$14
# plus $28. So this is drawn over the bat, not a loose guess. See PLAYER.md.
E0.update({
 0x28:("your head on the bat: head + shoulders, +3,-8","code"),
})

# Page $C0 is the player and the zombies. The player is built from a top half
# and a set of legs, and the legs are reused for the zombies -- which is why one
# page covers both.
C0 = {}
for a in range(0x00,0x20,4): C0[a]=("player, vertical move, top","play")
for a in range(0x20,0x34,4): C0[a]=("legs, vertical (reused by zombies)","play")
for a in range(0x34,0x40,4): C0[a]=("player attack, vertical, top","play")
for a in range(0x40,0x50,4): C0[a]=("player, horizontal move, top","play")
for a in range(0x50,0x5C,4): C0[a]=("player attack, horizontal, top","play")
C0[0x5C]=("player attack, horizontal, top -- facing left","play")
for a in range(0x60,0x80,4): C0[a]=("legs, horizontal (reused by zombies)","play")
for a in range(0x80,0x90,4): C0[a]=("player death / wolf knockdown","play")
C0[0x80]=("player death / knockdown","code+play")
C0[0x90]=("zombie head","play"); C0[0x94]=("zombie head","play")
C0[0x98]=("player standing, top","play"); C0[0x9C]=("player standing, top","play")
for a in range(0xA0,0xC0,4): C0[a]=("zombie head","play")
C0[0xB0]=("zombie head / pumpkin-head (right half)","play")
C0[0xB8]=("zombie head / pumpkin-head (right half)","play")
for a in range(0xC0,0xE0,4): C0[a]=("zombie torso","play")
C0[0xE0]=("zombie head -- Dr Evil area","play")
C0[0xE4]=("zombie head -- Dr Evil area","play")
C0[0xE8]=("zombie head -- pair outside the lab","play")
C0[0xEC]=("zombie head -- pair outside the lab","play")
for a in range(0xF0,0x100,4): C0[a]=("humpbacked zombie head","play")


# Cells on page $C0 that hold TWO 8-pixel sprite halves rather than one 16-pixel
# sprite. A cell is 4 bytes = 16 pixels; these pack a left sprite in bytes 0-1
# and a right sprite in bytes 2-3, so the head groups contain twice as many
# distinct heads as there are cells.
SPLIT_C0 = set()
for a in range(0x20, 0x38, 4): SPLIT_C0.add(a)      # $20-$34
for a in range(0x3C, 0x54, 4): SPLIT_C0.add(a)      # $3C-$50
SPLIT_C0.add(0x58)
SPLIT_C0.update({0x90, 0x94})
for a in range(0xA0, 0xC0, 4): SPLIT_C0.add(a)      # $A0-$BC
SPLIT_C0.update({0xE0, 0xE4, 0xE8, 0xEC})


# Head runs are NOT uniform. Most zombie types carry four heads -- up, down,
# left and right -- but two types have a single head that serves every facing,
# and the pumpkin-head has two. So the head block is a series of variable-length
# runs, not a grid, and a cell boundary does not mean a type boundary.
#
# Keys are (low, half) with half in "LR"; these override the per-cell labels.
# $A0-$BC decoded. Two cells (four halves) per facing, and within each group the
# order is fixed: bignose, [odd slot], longneck, hunchback. Three of those types
# carry all four facings; the odd slot is reused for the types that do not need
# four, so nothing is wasted:
#
#   facing      cells      L        R (odd)              L         R
#   right       $A0 $A4    bignose  headless             longneck  hunchback
#   left        $A8 $AC    bignose  bulb-head            longneck  hunchback
#   towards     $B0 $B4    bignose  pumpkin, facing away longneck  hunchback
#   away        $B8 $BC    bignose  pumpkin, facing you  longneck  hunchback
#
# The pumpkin-head's two heads sit in the towards/away groups but face the
# opposite way to the group they are packed with.
HALF_C0 = {}
_ORDER = ["bignose", None, "longneck", "hunchback"]
_ODD = {0xA0: "headless zombie -- one head, all facings",
        0xA8: "bulb-head zombie -- one head, all facings",
        0xB0: "pumpkin-head, facing away",
        0xB8: "pumpkin-head, facing you"}
for _base, _dir in ((0xA0, "right"), (0xA8, "left"),
                    (0xB0, "towards"), (0xB8, "away")):
    for _i, _slot in enumerate(_ORDER):
        _low = _base + (_i // 2) * 4
        _half = "L" if _i % 2 == 0 else "R"
        if _slot is None:
            HALF_C0[(_low, _half)] = _ODD[_base]
        else:
            HALF_C0[(_low, _half)] = "%s, %s" % (_slot, _dir)
HEAD_NOTE = ("most types carry four heads for up, down, left and right; "
             "the headless and bulb-head types have one apiece and the "
             "pumpkin-head has two")

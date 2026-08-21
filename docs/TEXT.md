# Midnight Mutants -- text records

Record format `$FF <p1> <p2> '@' text '#'`.  Control codes are decoded;
`[NEW PAGE]` is `&` ($26) and newlines are `|` ($7C).

## How a record is chosen

`sub_687E` (`f6:$687E`) takes a message number in A and looks it up in a table of
16-bit pointers at `f6:$69A7`, 73 entries covering `$00`-`$48`. The pointer aims
at the record's **p1** byte: p2 (the frame count the banner stays up) is read
from p1+1, and the text begins at p1+2, running until a byte with bit 7 set.

There are 15 call sites and between them they reach every index except five.

**`$24`, `$25`, `$26`, `$27` and `$32` have no code path that can produce them.**
Each points at a neighbour's record -- the first four at `$700E`, which `$23`
legitimately uses for room `$17`, and `$32` at `$71BC`, which `$31` uses. No text
is stranded by this; the slots are simply spare, which is what makes `$24`
available to the pumpkin repair below.

## The terminator decides whether the banner shimmers

`sub_687E` scans forward to the first byte with bit 7 set -- the byte that ends
the text -- and if it is **`$FE`** it puts `$FF` in `ram_1E7B`, otherwise that
stays zero. The display interrupt then does, at `f6:$4121`:

```
LDA ram_0044      ; free-running frame counter
AND ram_1E7B      ; the shimmer mask
STA P0C2          ; the banner's text colour
```

So with a `$FE` terminator the frame counter walks the text colour one step per
frame and the words pulse; with `$FF` the mask is zero, the text sits on colour
0, and it is static. The banner is **palette 0** (its display-list entries are
five-byte extended ones, so the palette is in the fourth byte, not the second).

Nearly every item pickup ends `$FE`. Walking all 73 records and reading the byte
each one stops on gives four exceptions, and they are all pickups:

| record | pickup | terminator | shimmers |
|---|---|---|---|
| `$3A`, `$3B` | potions | `$FE` | yes |
| `$3C`, `$3D`, `$3E`, `$3F` | crypt key, heart, necklace, lantern | `$FE` | yes |
| `$34`-`$37` | diamond, all four | `$FE` | yes |
| `$2B`-`$2E` | knife, all four | `$FE` | yes |
| **`$33`** | **cross** | **`$FF`** | **no** |
| **`$2F`, `$30`, `$31`** | **axe, blaster, mega blaster** | **`$FF`** | **no** |
| title, stuck door, pause, Grampa | -- | `$FF` | no |

The terminators sit at `f6:$7236` (cross), `$717E`, `$71BB` and `$71F9`. The
knife's own four lines shimmer, so the three weapons above it are not a
deliberate distinction between weapons and everything else -- there is no rule
under which the knife shimmers and the axe does not. The editor offers the flip
as a repair.

A new record must end `$FE` to match the pickups. This is the one thing about a
text record that is not visible in its text.

## Why the knife has four messages and the other weapons have one

`sub_50C4`, the weapon half of the pickup chain, branches on the new weapon
level before it picks a message:

```
50CF: TXA                 ; X = weapon level
50D0: BNE L_50DD          ; anything but the knife
50D2: JSR sub_D018        ; the knife: random
50D5: AND #$03            ; 0-3
50D8: ADC #$2B            ; -> $2B, $2C, $2D or $2E
L_50E6:
50E6: ADC #$2E            ; the rest: level + $2E -> $2F, $30, $31
```

Level 0 draws one of four flavour lines at random; levels 1-3 index a message
each. But the four are a pool for an event that happens **once**: the knife is
placed in exactly one room (`$43`, as kind `$0C`), and the per-room collected
bit stops a second pickup, so three of the four are unreachable in any single
run. The same four-message treatment on the diamond does pay off -- that one is
placed in fourteen rooms.

Whether the knife's pool is a deliberate lottery or the remains of a design
where the knife could be re-acquired, the code does not say.

## The pumpkin has no pickup line

The pickup chain at `f6:$527A` links an item kind to a message:

| kind | item | message |
|---|---|---|
| 1 | cross | `$33` |
| 2 | crypt key | `$3C` |
| 3 | necklace | `$3E` |
| 4 | heart | `$3D` |
| 6, 7 | potions | `$3A`, `$3B` |
| 8 | diamond | `$34`-`$37`, chosen at random |
| 9 | lantern | `$3F` |
| >= `$0C` | weapons | `$2B`-`$31`, see below |
| **5** | **plasmic pumpkin** | **none -- falls through to the `RTS` at `$5298`** |

Kind 5 is the only inventory item that grants in silence. It is not a broken
pointer or a lost record: the case was never written. The one other place the
item is named is `b0:$BA46`, `THIS PLASMIC PUMPKIN SMELLS ROTTEN`, and that is a
Grampa hint in the bank-0 pool -- wrong bank, wrong framing, and not in the
pointer table, so it could never have served as a pickup line.

The item matters: with the pumpkin selected, stepping on the terrain whose
property is `$EF` wins the game, and exactly one room places it -- **room `$1A`,
in the pumpkin fields**. Nothing in the shipped game says so.

## bank 0 (`b0`, mapped at $8000) -- 45 records

### `$A6A3`  p1=$02 p2=$02  (59 bytes, framing A)

```
SOMETIMES A TREASURE CAN NOT BE SEEN TILL EVIL IS DESTROYED
```

### `$A6E3`  p1=$05 p2=$02  (33 bytes, framing A)

```
YOU KNOW I CAN'T DO THIS FOR YOU!
```

### `$A709`  p1=$05 p2=$02  (37 bytes, framing A)

```
WHY DO YOU WASTE PRECIOUS DARK HOURS?
```

### `$A733`  p1=$05 p2=$02  (31 bytes, framing A)

```
DON'T BE COWARDLY,*


GET THEM!
```

### `$A757`  p1=$00 p2=$02  (32 bytes, framing A)

```
BARNABAS IS HIDING IN THE FOREST
```

### `$A77C`  p1=$00 p2=$02  (87 bytes, framing A)

```
THE NECKLACE FROM THE SHIPWRECK WILL SLOW DAMAGE AS WELL AS ALLOW YOU TO WALK ON WATER.
```

### `$A7D8`  p1=$00 p2=$03  (55 bytes, framing A)

```
THE MEGA BLASTER IS HIDDEN IN A DEAD END IN THE CAVERNS
```

### `$A814`  p1=$00 p2=$02  (66 bytes, framing A)

```
IF YOU ENTER THE CAVERNS FROM THE CABIN, YOU WILL BE NEAR THE WELL
```

### `$A85B`  p1=$01 p2=$02  (54 bytes, framing A)

```
YOUR BLOOD IS NOT VERY PURE!  SOON YOU WILL BE UNDEAD!
```

### `$A896`  p1=$00 p2=$02  (56 bytes, framing A)

```
YOUR BLOOD IS ALMOST POISONED!!!!!

DO SOMETHING QUICK!!
```

### `$A8D3`  p1=$00 p2=$02  (50 bytes, framing A)

```
GUESS WHAT?*

YOU'RE DEAD!


HIT RESET TO RESTART!
```

### `$A90A`  p1=$01 p2=$02  (57 bytes, framing A)

```
BUMMER,

YOU'RE ONE OF THE UNDEAD.**


WELL, THAT'S LIFE.
```

### `$A948`  p1=$05 p2=$00  (172 bytes, framing A)

```
OH WHAT A RELIEF!

   YOU SAVED ME!

AND YOU WASTED THE WICKED DOCTOR EVIL.

   VERY RAD.

NOW I CAN GET BACK TO RAISING PUMPKINS. ****


BY THE WAY, WHAT TOOK YOU SO LONG?
```

### `$A9F9`  p1=$04 p2=$02  (129 bytes, framing A)

```
SO YOU WANT TO BE RAISED FROM THE DEAD?

 OK.

THE BEST I CAN DO IS BRING BACK SOME OF YOUR HEALTH AND I CAN'T PURIFY YOUR BLOOD.
```

### `$AA7F`  p1=$03 p2=$04  (121 bytes, framing A)

```
GET THE KNIFE FIRST. IT CAN BE FOUND IN THE WEST OF THE MANSION.

UNTIL YOU FIND IT, YOU ARE HELPLESS. SO AVOID MONSTERS!
```

### `$AAFD`  p1=$00 p2=$04  (175 bytes, framing A)

```
GO NORTH FROM THE POND, AND LEFT AS SOON AS YOU ENTER THE MANSION.  THERE YOU WILL FIND THE KNIFE.\xFF\x04\x04@WHY WOULD A MORTUARY BE LOCKED?
*
***BECAUSE PEOPLE ARE DYING TO GET IN!!
```

### `$ABB1`  p1=$04 p2=$04  (82 bytes, framing A)

```
GOING TO THE CHAPEL AND WE'RE**
GONNA GET BURIED!**

GOING TO THE CHAPEL OF BLOOD!
```

### `$AC08`  p1=$01 p2=$00  (246 bytes, framing A)

```
HELP!!!!

 THE WICKED DR. EVIL HAS RISEN FROM THE GRAVE AND IMPRISONED ME INSIDE A PLASMIC PUMPKIN!!!

 I CAN'T BE WITH YOU, BUT I CAN GIVE YOU CLUES WHICH MAY HELP!

 WHENEVER YOU NEED ME PRESS THE RIGHT BUTTON AND I MIGHT HAVE SOME GOOD ADVICE.
```

### `$AD03`  p1=$00 p2=$01  (73 bytes, framing A)

```
USE THIS MENU TO SELECT ITEMS EARNED. FIRST FIND THE ITEMS, THEN SAVE ME.
```

### `$AD51`  p1=$00 p2=$01  (65 bytes, framing A)

```
THE KEY TO THE CRYPT CAN BE FOUND IN THE UPSTAIRS OF THE MANSION.
```

### `$AD97`  p1=$04 p2=$02  (35 bytes, framing A)

```
A CROSS WILL PROTECT YOU FROM BATS.
```

### `$ADBF`  p1=$04 p2=$05  (67 bytes, framing A)

```
THERE IS A CABIN IN THE SOUTH WOODS, I REMEMBER AN AXE BEING THERE.
```

### `$AE07`  p1=$02 p2=$05  (71 bytes, framing A)

```
FROM THE CLIFFS, GO ALL THE WAY UP, THEN LEFT.THE WELL OF HEALTH WAITS!
```

### `$AE53`  p1=$02 p2=$05  (68 bytes, framing A)

```
YOU CAN ENTER THE STABLES BY FINDING THE BUSH WHICH CASTS NO SHADOW.
```

### `$AE9C`  p1=$00 p2=$04  (73 bytes, framing A)

```
WITH THE AXE, YOU CAN DEFEAT THE HIDEOUS MUTANT BEAST HIDING IN THE BARN.
```

### `$AEEA`  p1=$00 p2=$04  (102 bytes, framing A)

```
YOU ARE DOING PRETTY GOOD, FOR A MORTAL.  NOW EXPLORE THE MANSION FOR THE KEY TO THE MYSTERIOUS CRYPT!
```

### `$AF55`  p1=$00 p2=$04  (49 bytes, framing A)

```
AN AWESOME WEAPON CAN BE FOUND BELOW THE KITCHEN!
```

### `$AF8B`  p1=$00 p2=$04  (37 bytes, framing A)

```
YOU HAVE THE POWER TO ENTER THE CRYPT
```

### `$AFB5`  p1=$00 p2=$04  (53 bytes, framing A)

```
THE LANTERN IN THE PUMPKIN FIELD WILL LIGHT YOUR WAY.
```

### `$AFEF`  p1=$02 p2=$01  (534 bytes, framing A)

```
DUE TO A MIXUP OF A GENETIC EXPERIMENT IN OCTOBER, 1950, SIMON YAGER WAS MYSTERIOUSLY TRANSFORMED INTO A RAM.

HIS EVIL COMPANION LED HIM TO BELIEVE THAT DRINKING PURE HUMAN BLOOD WOULD RETURN HIM TO NORMAL.

[NEW PAGE]
SIMON KILLED RAVAGELY, AND DRANK THE BLOOD. HE WAS CHANGING, BUT NOT AS EXPECTED. HE WAS LOSING THE FLESH OF HIS RAMS BODY.

IT BECAME OBVIOUS THAT THE RICH RED BLOOD HE OBTAINED UPON EACH KILL ONLY MADE HIM THIRST FOR MORE.

[NEW PAGE]



AS HIS ANGER AND CRAVING FOR HUMAN LIFE GREW, SIMON BECAME A SKELETAL RAMS HEAD STALKING HIS PREY!
```

### `$B20A`  p1=$03 p2=$00  (626 bytes, framing A)

```
IN THE FALL OF 1890 THERE WAS A GREATLY FEARED OPTOMETRIST NAMED DAMON MOHLER AND HIS ASSISTANT, EDWARD EVIL.
DAMON USED NO ANESTHESIA AS HE PLUCKED THE EYEBALLS FROM HIS VICTIMS.  THE EYEBALLS WERE KEPT IN A TANK FILLED WITH THE VICTIMS BLOOD.

[NEW PAGE]
DAMON SUFFERED AN ACCIDENT IN WHICH HIS SIGHT WAS LOST.
EDWARD INSERTED A NEW PAIR OF EYEBALLS INTO DAMON.
DAMON SOON FELL ILL AND DISCOVERED THE EYEBALLS HAD BEEN SOAKED IN TAINTED BLOOD. DAMON DIED A PAINFUL DEATH.  EDWARD BURIED DAMON AND HIS EYEBALL COLLECTION IN THE CRYPT.

[NEW PAGE]



LEGENDS SAY DAMON'S SKULL STILL HAUNTS THE CRYPT AT NIGHT, SEEKING VENGEANCE ON THE SIGHTED LIVING.
```

### `$B481`  p1=$03 p2=$00  (719 bytes, framing A)

```
IN THE EARLY NINETEENTH CENTURY, PROFESSOR VON ADAMS WAS SHUNNED FOR HIS UNGODLY EXPERIMENTS ON HUMAN CORPSES.  HIS SMALL ARMY OF MUTANT ZOMBIES WAS THE RESULT OF YEARS OF CAREFUL RESEARCH WITHIN HIS SECRET LAB.  TO CONTROL THE MONSTERS, HE DEVELOPED A BLASTER WHICH WOULD BE AN EXCELLENT WEAPON AGAINST THE CREATURES.

[NEW PAGE]


IN THE BASEMENT OF HIS MANSION, THE PROFESSOR UNVEILED HIS LIVING CORPSES TO A DOZEN DISTINGUISHED SCIENTISTS.  THE CREATURES, FRIGHTENED AND CONFUSED, WENT BERSERK.  THEY BLINDLY GRABBED SCIENTISTS AND TORE THEM IN PIECES.

[NEW PAGE]



AS PROFESSOR VON ADAMS GRASPED THE BLASTER TO STOP THEM, ONE CREATURE GRABBED HIM AND RIPPED OFF HIS HEAD.

THE CREATURES STILL WANDER THESE HALLS SEARCHING FOR THE LIVING
```

### `$B755`  p1=$03 p2=$00  (331 bytes, framing B)

```
DURING THE LATE EIGHTEENTH CENTURY, THERE WERE SIX HOLY NUNS PRAYING IN THIS BEAUTIFUL CHAPEL.  GREAT PEACE AND TRANQUILITY SURROUNDED THEM.

[NEW PAGE]
SUDDENLY A RAVING LUNATIC BURST THROUGH A STAINED GLASS WINDOW AND BEGAN SLAUGHTERING THE NUNS ONE BY ONE.  UPON HIS DEPARTURE HE LEFT ONLY A BLOODY SIGNATURE THAT READ @EDWARD WILL RETURN#.
```

### `$B8A3`  p1=$03 p2=$00  (46 bytes, framing A)

```
IT TAKES MORE THAN A KNIFE TO KILL THE UNDEAD!
```

### `$B8D6`  p1=$00 p2=$04  (84 bytes, framing A)

```
SOME PLACES IN THE CAVERNS SEEM TO GO ON FOREVER.

DON'T LET THE DOCTOR DECEIVE YOU!
```

### `$B92F`  p1=$00 p2=$04  (55 bytes, framing A)

```
CERTAIN TREASURES CAN'T BE FOUND TILL EVIL IS DESTROYED
```

### `$B96B`  p1=$00 p2=$04  (81 bytes, framing A)

```
WITH PERSISTENCE, YOU CAN BECOME POWERFUL ENOUGH TO DESTROY THE SINISTER DR. EVIL
```

### `$B9C1`  p1=$00 p2=$04  (25 bytes, framing A)

```
HAVE YOU BEEN A GOOD BOY?
```

### `$B9DF`  p1=$00 p2=$04  (47 bytes, framing A)

```
YOU CAN ONLY HOLD ONE OF EACH POTION AT A TIME.
```

### `$BA13`  p1=$03 p2=$00  (46 bytes, framing A)

```
IT TAKES MORE THAN A KNIFE TO KILL THE UNDEAD!
```

### `$BA46`  p1=$03 p2=$00  (34 bytes, framing A)

```
THIS PLASMIC PUMPKIN SMELLS ROTTEN
```

### `$BA6D`  p1=$03 p2=$00  (37 bytes, framing A)

```
GHOSTS WILL DRAIN THE LIFE FROM YOU!!
```

### `$BA97`  p1=$03 p2=$00  (312 bytes, framing B)

```
HUNDREDS OF YEARS HAVE FADED BY AND STILL DR. EVIL RETURNS TO RULE THE NIGHT.  BY INFLUENCING ANY ACCOMPLICE OF HIS CHOOSING, HE HAS TERRORIZED HUMANKIND FOR CENTURIES.

[NEW PAGE]
NOW THAT HE HAS TAKEN BACK HIS HUMAN FORM, HE SEEKS TO DESTROY THE LIVING AND REEK HAVOC.  ANY SOUL THAT IS TOUCHED BY HIM SHALL SURELY PERISH.
```

### `$BBD2`  p1=$00 p2=$04  (45 bytes, framing A)

```
SET ASIDE YOUR FEAR,**


AND TRASH THE FREAK!
```

### `$BC04`  p1=$00 p2=$04  (29 bytes, framing A)

```
IMPRESSIVE,**


FOR A MORTAL.
```

## bank 6 (`f6`, mapped at $4000) -- 68 records

One further record sits in this bank and is not listed below: **`$6A6C`**, 79
bytes, framing B -- the status-bar template, `BLOOD / PURE SCORE HEALTH:`. The
two framing scans here run independently and it falls between them; the editor's
combined scan finds it.

### `$6A39`  p1=$00 p2=$54  (48 bytes, framing B)

```
HE ULTIMATE HALLOWEEN NIGHTMARE
MIDNIGHT MUTANTS
```

### `$6ABE`  p1=$01 p2=$0A  (30 bytes, framing B)

```
A STRANGE CHILL COMES OVER YOU
```

### `$6ADF`  p1=$01 p2=$0A  (31 bytes, framing B)

```
YOU FEEL PRESSURE ON YOUR BRAIN
```

### `$6B01`  p1=$01 p2=$0A  (22 bytes, framing B)

```
THE AIR SMELLS OF DOOM
```

### `$6B1A`  p1=$01 p2=$0A  (25 bytes, framing B)

```
THIS PLACE REEKS OF DEATH
```

### `$6B36`  p1=$01 p2=$0A  (44 bytes, framing B)

```
SOME TREASURES APPEAR
AT THE ABSENCE OF EVIL
```

### `$6B65`  p1=$01 p2=$0A  (31 bytes, framing B)

```
THE WOLVES HOWL IN THE DISTANCE
```

### `$6B87`  p1=$01 p2=$0A  (19 bytes, framing B)

```
I WANT MY
MUTANT TV
```

### `$6B9D`  p1=$01 p2=$0A  (31 bytes, framing B)

```
ICY SHIVERS
RUN DOWN YOUR SPINE
```

### `$6BBF`  p1=$01 p2=$0A  (26 bytes, framing A)

```
THIS PLACE DRIVES ME BATTY
```

### `$6BDE`  p1=$01 p2=$0A  (45 bytes, framing B)

```
DR. EVIL LIVED ON THIS
ESTATE MANY YEARS AGO.
```

### `$6C0E`  p1=$01 p2=$0A  (33 bytes, framing B)

```
DOCTOR EVIL DABBLED IN THE OCCULT
```

### `$6C32`  p1=$01 p2=$0A  (48 bytes, framing A)

```
PROFESSOR VON ADAMS MOVED
TO THE MANSION IN 1813
```

### `$6C67`  p1=$01 p2=$0A  (51 bytes, framing A)

```
PROFESSOR VON ADAMS WAS
EXILED FROM AUSTRIA IN 1811
```

### `$6C9F`  p1=$01 p2=$0A  (45 bytes, framing A)

```
A ZOMBIE DANCING ON A TABLE
IS QUITE A SIGHT!
```

### `$6CD1`  p1=$01 p2=$0A  (34 bytes, framing A)

```
A CROSS WILL PROTECT YOU FROM BATS
```

### `$6CF8`  p1=$01 p2=$0A  (24 bytes, framing B)

```
SIMON DETESTS ALL HUMANS
```

### `$6D13`  p1=$01 p2=$0A  (53 bytes, framing B)

```
SIMONS EXPERIMENTS INVOLVED BODY FLUIDS
FROM HIS RAMS
```

### `$6D4B`  p1=$01 p2=$0A  (38 bytes, framing B)

```
SIMON YAGER WANTED
TO PURIFY HIS BLOOD
```

### `$6D74`  p1=$01 p2=$0A  (40 bytes, framing B)

```
SIMON YAGER'S
EXPERIMENTS WERE DANGEROUS
```

### `$6D9F`  p1=$01 p2=$0A  (32 bytes, framing B)

```
SIMON YAGER WORKED WITH DR. EVIL
```

### `$6DC2`  p1=$01 p2=$0A  (45 bytes, framing B)

```
SOME PROCLAIM THAT
SIMON HATES THE HUMAN RACE
```

### `$6DF2`  p1=$01 p2=$0A  (37 bytes, framing B)

```
DAMON MOHLER WAS A FEARED OPTOMETRIST
```

### `$6E1A`  p1=$01 p2=$0A  (42 bytes, framing B)

```
DAMON KEPT A COLLECTION
 OF HUMAN EYEBALLS
```

### `$6E47`  p1=$01 p2=$0A  (34 bytes, framing B)

```
DAMON SPENT MUCH TIME IN THE CRYPT
```

### `$6E6C`  p1=$01 p2=$0A  (33 bytes, framing B)

```
RUMORS SAY DAMON MOHLER WAS BLIND
```

### `$6E90`  p1=$01 p2=$0A  (36 bytes, framing B)

```
BEWARE!
DR. EVIL MAY BE WATCHING YOU
```

### `$6EB7`  p1=$01 p2=$0A  (40 bytes, framing B)

```
USE YOUR WEAPONS WISELY
OR YOU WILL FAIL
```

### `$6EE2`  p1=$01 p2=$0A  (56 bytes, framing B)

```
THE DEAD WILL RISE TO GREET YOU
 AT THE DOCTOR'S COMMAND
```

### `$6F1D`  p1=$01 p2=$0A  (35 bytes, framing B)

```
THERE IS A WEAPON IN THE LABORATORY
```

### `$6F43`  p1=$01 p2=$FF  (43 bytes, framing B)

```
TALK TO GRAMPA BY
PRESSING THE RIGHT BUTTON
```

### `$6F71`  p1=$01 p2=$0A  (19 bytes, framing B)

```
BEWARE OF THE CRYPT
```

### `$6F87`  p1=$01 p2=$0A  (29 bytes, framing B)

```
WALKING DEAD DON'T NEED SHOES
```

### `$6FA7`  p1=$64 p2=$14  (57 bytes, framing B)

```
GRAMPA CAN REVIVE YOU!
PRESS THE RIGHT BUTTON TO CONTINUE
```

### `$6FE3`  p1=$29 p2=$0F  (39 bytes, framing B)

```
EVER FEEL LIKE
YOUR WALKING IN CIRCLES?
```

### `$700D`  p1=$01 p2=$0A  (25 bytes, framing B)

```
THIS PLACE REEKS OF DEATH
```

### `$7029`  p1=$01 p2=$0A  (17 bytes, framing B)

```
THE DOOR IS STUCK
```

### `$703D`  p1=$01 p2=$0A  (39 bytes, framing B)

```
PERHAPS YOU COULD
PRY IT WITH SOMETHING
```

### `$7067`  p1=$01 p2=$0A  (33 bytes, framing B)

```
YOU OPEN THE DOOR WITH YOUR KNIFE
```

### `$708B`  p1=$01 p2=$0A  (33 bytes, framing B)

```
YOU NOW POSSESS RAZOR SHARP POWER
```

### `$70AF`  p1=$01 p2=$0A  (50 bytes, framing B)

```
YOU MARVEL AT THE CUTTING FORCE
 WITHIN YOUR GRASP
```

### `$70E4`  p1=$01 p2=$0A  (56 bytes, framing B)

```
MOONLIGHT RADIATES THE BRILLIANCE
 OF THE PIERCING BLADE
```

### `$711F`  p1=$01 p2=$0A  (21 bytes, framing B)

```
TIME TO FIGHT BACK!!!
```

### `$7137`  p1=$01 p2=$0A  (68 bytes, framing B)

```
WITH THE AXE IN YOUR POSSESSION,
YOU FEEL STURDY, FORCEFUL, PREPARED
```

### `$717F`  p1=$01 p2=$0A  (57 bytes, framing B)

```
GRASPING THE SMALL BLASTER
 YOU FELL VIBRANT AND UNAFRAID
```

### `$71BB`  p1=$01 p2=$0A  (59 bytes, framing B)

```
WITH THIS POWERFUL BLASTER
YOU GAIN CONTROL OF YOUR DESTINY
```

### `$71F9`  p1=$01 p2=$0A  (58 bytes, framing B)

```
YOU FOUND THE CROSS
BATS WILL THINK TWICE BEFORE ATTACKING
```

### `$7236`  p1=$01 p2=$0A  (25 bytes, framing B)

```
YOU FEEL
A BURST OF POWER
```

### `$7252`  p1=$01 p2=$0A  (20 bytes, framing B)

```
YOU FEEL REALLY TUFF
```

### `$7269`  p1=$01 p2=$0A  (33 bytes, framing B)

```
THE STRENGTH WITHIN YOU
INCREASES
```

### `$728D`  p1=$01 p2=$0A  (59 bytes, framing B)

```
AN ULTIMATE SURGE OF POWER
 AND STRENGTH WELL UP WITHIN YOU
```

### `$72CB`  p1=$29 p2=$0A  (44 bytes, framing B)

```
YOU MAY NOT ENTER HERE
WITHOUT USING THE KEY
```

### `$72FA`  p1=$29 p2=$0A  (38 bytes, framing B)

```
NOT JUST ANY PUNK
CAN ENTER ENTER HERE
```

### `$7323`  p1=$29 p2=$96  (30 bytes, framing B)

```
THIS POTION WILL PURIFY BLOOD!
```

### `$7344`  p1=$29 p2=$96  (28 bytes, framing B)

```
A POTION TO RESTORE HEALTH!!
```

### `$7363`  p1=$29 p2=$96  (25 bytes, framing B)

```
THAT KEY OPENS THE CRYPT!
```

### `$737F`  p1=$29 p2=$96  (33 bytes, framing B)

```
NOW YOUR BLOOD
WILL NEVER FALTER!
```

### `$73A3`  p1=$29 p2=$96  (46 bytes, framing B)

```
YOU FEEL THE POWER
RADIATING FROM THE NECKLACE
```

### `$73D4`  p1=$29 p2=$96  (32 bytes, framing B)

```
THIS LANTERN
WILL LIGHT YOUR WAY
```

### `$73F7`  p1=$29 p2=$08  (32 bytes, framing B)

```
PRODUCED BY
RADIOACTIVE SOFTWARE
```

### `$741A`  p1=$29 p2=$08  (45 bytes, framing B)

```
COPYRIGHT 1990 ATARI CORP
ALL RIGHTS RESERVED
```

### `$744A`  p1=$29 p2=$08  (33 bytes, framing B)

```
PROGRAM AND DESIGN BY
PETER ADAMS
```

### `$746E`  p1=$29 p2=$08  (22 bytes, framing B)

```
STORIES BY
TAMMY MOORE
```

### `$7487`  p1=$29 p2=$08  (28 bytes, framing B)

```
MUSIC AND SOUND BY
PAUL WEBB
```

### `$74A6`  p1=$29 p2=$08  (47 bytes, framing B)

```
SPECIAL THANKS TO
ADAM CLAYTON AND RICH ROBBINS
```

### `$74D8`  p1=$29 p2=$08  (17 bytes, framing B)

```
ART BY
LES PARDUE
```

### `$74EC`  p1=$64 p2=$01  (25 bytes, framing B)

```
TIME SEEMS
TO STAND STILL
```

### `$7508`  p1=$64 p2=$01  (32 bytes, framing B)

```
TIME AND SPACE
BECOME INTERWOVEN
```


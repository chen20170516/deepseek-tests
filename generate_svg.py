#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate an animated SVG of Sun Wukong riding a bicycle through a cloud sea.

The bicycle is a real little rig: one crank revolution carries both pedals
around a true circle, each boot counter-rotates inside the crank to stay level,
and both legs are solved with two-bone IK at 24 crank angles.  The base state
of the SVG is a complete still, so the illustration survives SVG viewers that
ignore animation as well as respects a reduced-motion pause.
"""
from __future__ import annotations

import io
import math
import re
import sys
from pathlib import Path

W, H = 1200, 800
GROUND = 720.0
HUB_Y = 594.0
REAR = (438.0, HUB_Y)
FRONT = (918.0, HUB_Y)
WHEEL_R = 126.0
BB = (658.0, 628.0)
CRANK_R = 50.0
ANKLE_UP = 32.0
HIP_N = (578.0, 394.0)
HIP_F = (558.0, 386.0)
L1, L2 = 140.0, 160.0
CADENCE = 3.2
WHEEL_DUR = 1.6
START_PHASE = 25.0
KEYS = 24

INK = "#3a2720"
INK_SOFT = "#5a3b2b"
PAPER = "#f7ecd7"


def fm(v: float | int) -> str:
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p):
    return f"{fm(p[0])},{fm(p[1])}"


def polar(c, r, deg):
    a = math.radians(deg)
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))


def arc_path(c, r, a0, a1):
    p0, p1 = polar(c, r, a0), polar(c, r, a1)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M {pt(p0)} A {fm(r)} {fm(r)} 0 {large} 1 {pt(p1)}"


def ik_knee(hip, ankle, l1=L1, l2=L2):
    dx, dy = ankle[0] - hip[0], ankle[1] - hip[1]
    d = math.hypot(dx, dy)
    d = max(min(d, l1 + l2 - 1e-6), abs(l1 - l2) + 1e-6)
    a = (l1 * l1 - l2 * l2 + d * d) / (2.0 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    ux, uy = dx / d, dy / d
    bx, by = hip[0] + a * ux, hip[1] + a * uy
    # forward-folding knee (positive x, above the hip-ankle line)
    return (bx + h * uy, by - h * ux), d


def foot_target(deg, side):
    """World position of the ankle joint for a pedal at crank angle `deg`."""
    return (
        BB[0] + side * CRANK_R * math.cos(math.radians(deg)),
        BB[1] + side * CRANK_R * math.sin(math.radians(deg)) - ANKLE_UP,
    )


def leg_pose(hip, deg, side, base=False):
    ankle = foot_target(deg, side)
    knee, d = ik_knee(hip, ankle)
    return knee, ankle, d


def leg_paths(hip, deg, side):
    k, a, _ = leg_pose(hip, deg, side)
    return (f"M {pt(hip)} L {pt(k)}", f"M {pt(k)} L {pt(a)}")


def leg_values(hip, side, start=0.0, keys=KEYS):
    thigh, shank = [], []
    for i in range(keys + 1):
        deg = start + 360.0 * i / keys
        t, s = leg_paths(hip, deg, side)
        thigh.append(t)
        shank.append(s)
    return thigh, shank


def leg_base(hip, deg, side):
    return leg_paths(hip, deg, side)


def anim_d(values, dur=CADENCE):
    n = len(values) - 1
    kt = ";".join(fm(i / n) for i in range(n + 1))
    return (f'<animate attributeName="d" values="{";".join(values)}" '
            f'keyTimes="{kt}" dur="{fm(dur)}s" repeatCount="indefinite" '
            f'calcMode="linear"/>')


def anim_rot_values(values, dur, key_times=None, splines=None, begin=None):
    attrs = [f'attributeName="transform"', 'type="rotate"',
             f'values="{values}"', f'dur="{fm(dur)}s"',
             'repeatCount="indefinite"']
    if key_times:
        attrs.append(f'keyTimes="{key_times}"')
    if splines:
        attrs.append('calcMode="spline"')
        attrs.append(f'keySplines="{splines}"')
    else:
        attrs.append('calcMode="linear"')
    if begin:
        attrs.append(f'begin="{begin}"')
    return "<animateTransform " + " ".join(attrs) + "/>"


def anim_translate(values, dur, key_times=None, splines=None, begin=None):
    attrs = [f'attributeName="transform"', 'type="translate"',
             f'values="{values}"', f'dur="{fm(dur)}s"',
             'repeatCount="indefinite"']
    if key_times:
        attrs.append(f'keyTimes="{key_times}"')
    if splines:
        attrs.append('calcMode="spline"')
        attrs.append(f'keySplines="{splines}"')
    else:
        attrs.append('calcMode="linear"')
    if begin:
        attrs.append(f'begin="{begin}"')
    return "<animateTransform " + " ".join(attrs) + "/>"


def anim_scale(values, dur, key_times, splines=None, begin=None):
    attrs = [f'attributeName="transform"', 'type="scale"',
             f'values="{values}"', f'dur="{fm(dur)}s"',
             'repeatCount="indefinite"', f'keyTimes="{key_times}"']
    if splines:
        attrs += ['calcMode="spline"', f'keySplines="{splines}"']
    else:
        attrs.append('calcMode="linear"')
    if begin:
        attrs.append(f'begin="{begin}"')
    return "<animateTransform " + " ".join(attrs) + "/>"


def anim_opacity(values, dur, key_times=None, begin=None):
    attrs = [f'attributeName="opacity"', f'values="{values}"',
             f'dur="{fm(dur)}s"', 'repeatCount="indefinite"']
    if key_times:
        attrs.append(f'keyTimes="{key_times}"')
    if begin:
        attrs.append(f'begin="{begin}"')
    return "<animate " + " ".join(attrs) + "/>"


def pivot_group(px, py, base_angle, anim, content):
    return (
        f'<g transform="translate({fm(px)} {fm(py)})">'
        f'<g transform="rotate({fm(base_angle)})">{anim}'
        f'<g transform="translate({fm(-px)} {fm(-py)})">'
        f'{content}</g></g></g>')


def pivot_local(px, py, base_angle, anim, content):
    """Pivot around a point in the current, already-local, coordinates."""
    return (
        f'<g transform="translate({fm(px)} {fm(py)})">'
        f'<g transform="rotate({fm(base_angle)})">{anim}'
        f'<g transform="translate({fm(-px)} {fm(-py)})">'
        f'{content}</g></g></g>')


SINE = "0.42 0 0.58 1"
SOFT = "0.33 0 0.33 1"

# --------------------------------------------------------------------------
# Background
# --------------------------------------------------------------------------


def sun_and_sky():
    stars = [
        (84, 500, 1.8, .35), (1030, 430, 1.4, .3), (1120, 310, 2.0, .28),
        (670, 360, 1.3, .35), (240, 300, 1.5, .25),
    ]
    stars_markup = "".join(
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="#f5cf8d" opacity="{o}"/>'
        for x, y, r, o in stars)
    birds = (
        '<g fill="none" stroke="#59443a" stroke-width="2.2" '
        'stroke-linecap="round" opacity=".46">'
        '<path d="M 1030,329 C 1037,322 1042,322 1048,327 C 1054,321 1060,322 1067,329"/>'
        '<path d="M 1068,305 C 1074,299 1078,299 1083,304 C 1088,299 1093,300 1098,305"/>'
        '<path d="M 1003,290 C 1008,286 1011,286 1015,289 C 1019,285 1023,286 1027,290"/>'
        '</g>')
    return f"""
<rect x="0" y="0" width="{W}" height="{H}" fill="url(#paper)"/>
<g id="sun">
  <circle cx="982" cy="207" r="205" fill="url(#sunHalo)" opacity=".5"/>
  <circle cx="982" cy="207" r="170" fill="none" stroke="#eec17b" stroke-width="1.4" opacity=".45"/>
  <circle cx="982" cy="207" r="151" fill="url(#sunG)"/>
  <circle cx="982" cy="207" r="151" fill="none" stroke="#f0c57b" stroke-width="2" opacity=".6"/>
  <path d="M 892,262 C 930,279 972,285 1010,277 C 1048,269 1071,254 1091,234"
    fill="none" stroke="#f7d8a1" stroke-width="7" stroke-linecap="round" opacity=".12"/>
</g>
{birds}
{stars_markup}
""".strip()


def mountains():
    return f"""
<g id="far-mountains" opacity=".65">
  <path d="M -40,566 L -40,468
    C 37,453 82,406 143,404 C 196,403 223,438 270,443
    C 322,448 338,395 383,375 C 431,353 462,401 509,425
    C 560,451 610,412 664,405 C 721,397 760,438 810,457
    C 861,477 905,422 958,413 C 1019,402 1059,446 1107,446
    C 1151,446 1191,421 1240,411 L 1240,640 L -40,640 Z"
    fill="url(#mtFar)"/>
  <path d="M -40,509 C 60,465 116,459 184,481 C 246,501 281,468 340,450
    C 401,432 443,467 498,485 C 561,506 606,472 672,461
    C 742,449 787,479 853,496 C 917,513 968,476 1027,472
    C 1095,467 1157,489 1240,477"
    fill="none" stroke="#f1d2aa" stroke-width="2" opacity=".26"/>
</g>
<g id="mid-mountains">
  <path d="M -40,613 L -40,537
    C 36,511 97,522 154,542 C 218,565 263,527 329,511
    C 392,496 432,532 492,552 C 557,574 600,523 668,515
    C 734,507 781,546 843,558 C 916,572 954,527 1019,525
    C 1083,522 1141,552 1240,542 L 1240,670 L -40,670 Z"
    fill="url(#mtMid)"/>
  <path d="M 29,576 C 101,555 153,568 205,584 C 265,603 307,570 362,558"
    fill="none" stroke="#f3d9b7" stroke-width="1.5" opacity=".22"/>
  <g id="pagoda" transform="translate(286 498) scale(.72)" opacity=".62">
    <path d="M -1,-93 L -4,-25 L 4,-25 L 2,-93 Z" fill="#294647"/>
    <g fill="#294647">
      <path d="M -34,-83 C -22,-90 22,-90 34,-83 L 26,-72 C 15,-77 -15,-77 -26,-72 Z"/>
      <path d="M -30,-66 C -19,-73 19,-73 30,-66 L 23,-55 C 13,-60 -13,-60 -23,-55 Z"/>
      <path d="M -26,-49 C -16,-56 16,-56 26,-49 L 19,-38 C 10,-43 -10,-43 -19,-38 Z"/>
      <path d="M -21,-33 C -13,-39 13,-39 21,-33 L 15,-23 C 8,-27 -8,-27 -15,-23 Z"/>
      <path d="M -16,-18 C -9,-23 9,-23 16,-18 L 11,-9 L -11,-9 Z"/>
      <path d="M -16,-9 L 16,-9 L 23,1 L -23,1 Z"/>
    </g>
    <path d="M 0,-94 L 0,-108" stroke="#294647" stroke-width="2"/>
    <circle cx="0" cy="-110" r="3" fill="#294647"/>
  </g>
</g>
<g id="near-mountains" opacity=".9">
  <path d="M -40,642 L -40,596
    C 33,580 91,610 156,613 C 226,616 278,583 349,585
    C 423,587 470,619 538,620 C 604,621 648,593 716,594
    C 790,595 837,622 902,615 C 967,608 1001,585 1069,592
    C 1139,599 1182,616 1240,605 L 1240,700 L -40,700 Z"
    fill="url(#mtNear)"/>
  <g fill="none" stroke="#38524d" stroke-width="2" opacity=".18">
    <path d="M -10,566 C 92,548 180,558 267,572 C 363,587 451,575 540,558"/>
    <path d="M 884,552 C 956,532 1030,536 1110,553 C 1160,564 1200,563 1240,555"/>
    <path d="M 54,616 C 114,600 177,602 240,615"/>
  </g>
  <g fill="#24413e" opacity=".45">
    <g transform="translate(151 590) scale(.7)">
      <path d="M 0,-57 L -17,-17 L -7,-20 L -23,9 L -4,4 L -7,20 L 7,20 L 4,4 L 23,9 L 7,-20 L 17,-17 Z"/>
      <rect x="-3" y="18" width="6" height="18"/>
    </g>
    <g transform="translate(183 595) scale(.45)">
      <path d="M 0,-57 L -17,-17 L -7,-20 L -23,9 L -4,4 L -7,20 L 7,20 L 4,4 L 23,9 L 7,-20 L 17,-17 Z"/>
      <rect x="-3" y="18" width="6" height="18"/>
    </g>
    <g transform="translate(1122 582) scale(.55)">
      <path d="M 0,-57 L -17,-17 L -7,-20 L -23,9 L -4,4 L -7,20 L 7,20 L 4,4 L 23,9 L 7,-20 L 17,-17 Z"/>
      <rect x="-3" y="18" width="6" height="18"/>
    </g>
  </g>
</g>
<g id="mountain-mist" fill="none" stroke="#fae9cd" stroke-linecap="round">
  <path d="M -20,507 C 103,491 203,507 318,503 C 459,498 563,512 699,501
    C 847,489 984,503 1220,486" stroke-width="13" opacity=".2"/>
  <path d="M -20,558 C 132,543 274,558 395,552 C 543,543 664,562 795,552
    C 947,540 1071,553 1220,540" stroke-width="7" opacity=".18"/>
</g>
""".strip()


def high_clouds():
    """Thin, wind-drawn clouds, plus a veil drifting across the sun."""
    return """
<g id="high-clouds" opacity=".62">
  <g>
    <animateTransform attributeName="transform" type="translate"
      values="0 0;18 2;0 0" dur="31s" repeatCount="indefinite"
      calcMode="spline" keyTimes="0;0.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
    <g fill="#f9e9cf" opacity=".55">
      <path d="M 63,263 C 93,245 126,243 154,254 C 181,240 214,246 230,262
        C 255,251 282,259 294,277 C 271,288 245,285 220,280
        C 198,292 168,292 145,281 C 117,289 84,281 63,263 Z"/>
      <path d="M 294,270 C 306,261 320,262 327,269
        C 333,264 345,266 349,273 C 340,280 326,281 316,277 C 308,281 298,278 294,270 Z" opacity=".7"/>
    </g>
    <g fill="none" stroke="#c49b66" stroke-width="1.8" stroke-linecap="round" opacity=".35">
      <path d="M 96,270 C 85,262 88,253 98,254 C 107,255 110,264 102,268
        C 97,271 92,266 95,261"/>
      <path d="M 250,276 C 244,269 249,261 256,263 C 263,265 264,272 258,275"/>
    </g>
  </g>
  <g opacity=".55">
    <animateTransform attributeName="transform" type="translate"
      values="0 0;-14 1;0 0" dur="37s" repeatCount="indefinite"
      calcMode="spline" keyTimes="0;0.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
    <g fill="#f8e8cf">
      <path d="M 367,187 C 385,172 409,171 424,181 C 441,171 464,177 474,191
        C 490,185 506,192 512,205 C 493,214 474,211 458,205
        C 441,216 417,215 401,206 C 383,211 368,202 367,187 Z"/>
    </g>
    <g fill="none" stroke="#c49b66" stroke-width="1.6" stroke-linecap="round" opacity=".3">
      <path d="M 486,203 C 480,197 483,190 489,191 C 495,192 497,199 491,202"/>
    </g>
  </g>
  <g opacity=".42">
    <g fill="#faead2">
      <path d="M 1082,333 C 1104,316 1131,319 1147,332 C 1163,325 1181,331 1188,344
        C 1204,340 1218,350 1220,364 C 1197,373 1174,366 1158,359
        C 1139,369 1112,364 1096,352 C 1083,349 1075,341 1082,333 Z"/>
    </g>
  </g>
</g>
<g id="near-birds" fill="none" stroke="#5c4538" stroke-width="2.6"
  stroke-linecap="round" opacity=".55">
  <path d="M 315,294 C 327,281 340,283 349,294 C 358,282 371,285 382,296"/>
  <path d="M 381,250 C 391,240 401,242 407,251 C 414,241 424,244 432,253"/>
  <path d="M 357,269 C 364,262 372,264 377,270 C 382,264 390,266 396,272" opacity=".72"/>
</g>
<g id="sun-veil">
  <path d="M 759,301 C 806,281 852,283 894,300
    C 930,314 972,320 1015,308 C 1057,296 1098,296 1139,313
    C 1101,333 1053,339 1009,330 C 967,322 926,328 887,337
    C 842,348 789,330 759,301 Z"
    fill="#f9e8c9" opacity=".38"/>
  <path d="M 786,310 C 834,295 872,299 908,312
    C 944,325 986,326 1027,315 C 1059,306 1091,306 1119,316"
    fill="none" stroke="#fdF2d9" stroke-width="3" stroke-linecap="round" opacity=".55"/>
  <path d="M 794,310 C 784,301 786,289 797,287 C 807,285 814,295 808,302
    C 805,306 799,304 800,299" fill="none" stroke="#e7c28c"
    stroke-width="2" stroke-linecap="round" opacity=".45"/>
</g>
""".strip()

def title_and_border():
    return """
<g id="title" fill="#3d2b23">
  <g font-family="KaiTi, STKaiti, 'Kaiti SC', 'Noto Serif SC', 'Songti SC', serif">
    <text x="91" y="156" font-size="60" letter-spacing="3" opacity=".95">齐</text>
    <text x="91" y="222" font-size="60" letter-spacing="3" opacity=".95">天</text>
    <text x="91" y="288" font-size="60" letter-spacing="3" opacity=".95">大</text>
    <text x="91" y="354" font-size="60" letter-spacing="3" opacity=".95">圣</text>
  </g>
  <path d="M 165,119 L 165,366" stroke="#b74131" stroke-width="2" opacity=".62"/>
  <circle cx="165" cy="111" r="3.5" fill="#b74131" opacity=".78"/>
  <circle cx="165" cy="374" r="3.5" fill="#b74131" opacity=".78"/>
  <text x="188" y="153" font-family="KaiTi, STKaiti, 'Kaiti SC', serif"
    font-size="20" fill="#6d4d38" letter-spacing="4" opacity=".92">云海骑行</text>
  <path d="M 188,170 L 302,170" stroke="#9c7957" stroke-width="1" opacity=".42"/>
  <text x="188" y="190" font-family="Georgia, 'Times New Roman', serif"
    font-size="9.5" fill="#86664d" letter-spacing="2.6" opacity=".8">A CLOUD-RIDE TALE</text>
  <g transform="rotate(-1.5 110 432)">
    <rect x="84" y="407" width="47" height="47" rx="4" fill="#b73a2d"/>
    <rect x="89" y="412" width="37" height="37" rx="2" fill="none"
      stroke="#f6dfb5" stroke-width="1.2" opacity=".8"/>
    <text x="107.5" y="440" text-anchor="middle"
      font-family="KaiTi, STKaiti, 'Kaiti SC', serif" font-size="28"
      fill="#f8e8c8">悟</text>
  </g>
</g>
<g id="wind-speed" fill="none" stroke-linecap="round">
  <path d="M 343,477 C 474,461 565,472 679,459" stroke="#f8e9ca" stroke-width="3.2"
    stroke-dasharray="14 30" opacity=".47">
    <animate attributeName="stroke-dashoffset" values="0;-88" dur="1.8s"
      repeatCount="indefinite" calcMode="linear"/>
  </path>
  <path d="M 322,527 C 445,515 533,522 628,510" stroke="#e9c690" stroke-width="2.1"
    stroke-dasharray="8 27" opacity=".4">
    <animate attributeName="stroke-dashoffset" values="0;-70" dur="2.2s"
      repeatCount="indefinite" calcMode="linear"/>
  </path>
  <path d="M 742,502 C 825,494 883,502 963,492" stroke="#f8e8c6" stroke-width="2.4"
    stroke-dasharray="10 32" opacity=".38">
    <animate attributeName="stroke-dashoffset" values="0;-84" dur="2s"
      repeatCount="indefinite" calcMode="linear"/>
  </path>
</g>
""".strip()


def cloud_road_front():
    """Layered cloud sea behind the bicycle, with carved billows and 祥云 curls."""
    top_main = ("M -60,738 C 16,718 55,704 101,710 "
                "C 144,716 169,735 206,740 C 245,746 272,724 305,708 "
                "C 339,692 368,697 398,712 C 429,727 456,737 488,728 "
                "C 522,719 547,697 585,694 C 624,691 651,709 682,724 "
                "C 715,740 749,735 783,717 C 818,699 847,687 881,696 "
                "C 917,706 946,724 979,733 C 1012,742 1042,731 1074,713 "
                "C 1107,695 1139,692 1173,701 C 1205,710 1229,719 1250,713")
    top_back = ("M -60,698 C 12,675 66,665 122,676 "
                "C 174,687 214,681 257,661 C 301,640 349,641 396,662 "
                "C 440,682 479,685 522,670 C 564,655 600,639 646,644 "
                "C 694,649 730,668 772,677 C 814,686 849,669 887,652 "
                "C 927,635 966,638 1005,654 C 1045,671 1084,676 1125,662 "
                "C 1164,648 1206,649 1250,662")
    return f"""
<g id="cloud-sea-distant" opacity=".65">
  <path d="M -60,670 C 20,646 80,645 135,658 C 190,671 230,658 279,641
    C 328,624 381,629 430,646 C 478,663 523,661 570,645
    C 622,627 670,631 721,647 C 773,664 818,666 865,651
    C 915,635 959,638 1008,651 C 1058,664 1109,663 1163,649
    C 1197,640 1227,643 1250,651 L 1250,800 L -60,800 Z"
    fill="#dcc0a0" opacity=".55"/>
</g>
<g id="cloud-sea-back">
  <path d="{top_back} L 1250,860 L -60,860 Z" fill="url(#cloudBankFar)"/>
  <path d="{top_back}" fill="none" stroke="#cfa781" stroke-width="1.8" opacity=".45"/>
  <path d="M -60,709 C 26,694 82,699 132,714 C 181,729 224,729 264,716
    C 309,702 341,693 383,698 C 428,703 453,725 494,734
    C 534,743 570,732 607,715 C 650,695 686,687 728,693
    C 773,699 809,721 852,730 C 896,739 936,724 976,708
    C 1018,691 1059,690 1103,704 C 1145,718 1185,724 1250,716
    L 1250,860 L -60,860 Z" fill="#e7c9a2" opacity=".26"/>
</g>
<g id="cloud-sea-main">
  <path d="{top_main} L 1250,870 L -60,870 Z" fill="url(#cloudBank)"/>
  <path d="{top_main}" fill="none" stroke="#c69b6b" stroke-width="2.3"
    stroke-linecap="round" opacity=".56"/>
  <path d="M -54,742 C 24,722 62,710 104,716 C 146,722 169,739 205,744
    C 243,749 270,730 303,714 C 337,698 366,703 397,718
    C 430,733 457,742 489,733 C 521,725 548,703 584,699
    C 623,695 650,714 681,729 C 714,745 750,740 785,722
    C 820,704 848,693 883,703 C 918,713 947,730 979,738
    C 1011,746 1040,737 1071,719 C 1105,700 1138,698 1172,707
    C 1205,716 1230,724 1252,718" fill="none" stroke="#fff7e6"
    stroke-width="6.5" stroke-linecap="round" opacity=".72"/>
  <!-- folds that give the bank volume -->
  <g fill="#c9a57c" opacity=".27">
    <path d="M 100,717 C 143,722 173,738 206,742 C 177,754 136,749 103,736 Z"/>
    <path d="M 392,717 C 426,727 455,738 488,731 C 454,746 417,742 389,733 Z"/>
    <path d="M 678,730 C 714,742 749,738 784,721 C 748,754 709,752 674,742 Z"/>
    <path d="M 975,738 C 1010,744 1041,735 1072,718 C 1048,750 1010,756 973,750 Z"/>
    <path d="M 1170,708 C 1200,716 1226,721 1250,716 C 1213,740 1187,736 1161,725 Z"/>
  </g>
  <g fill="#aeb8ae" opacity=".17">
    <path d="M 202,744 C 235,751 264,733 304,710 C 281,746 244,761 203,757 Z"/>
    <path d="M 782,723 C 815,711 846,698 883,704 C 850,731 811,744 776,737 Z"/>
    <path d="M 1072,719 C 1103,702 1137,699 1171,708 C 1135,729 1105,737 1073,733 Z"/>
  </g>
  <path d="M 782,719 C 817,701 848,693 883,700 C 919,708 949,724 980,731"
    fill="none" stroke="#eac083" stroke-width="2.6" stroke-linecap="round" opacity=".55"/>
  <path d="M 1128,660 C 1159,646 1192,648 1224,658"
    fill="none" stroke="#efc98d" stroke-width="3" stroke-linecap="round" opacity=".4"/>
  <!-- carved cloud curls -->
  <g fill="none" stroke-linecap="round">
    <g stroke="#b78b57" stroke-width="3.2" opacity=".44">
      <path d="M 76,761 C 54,748 60,722 83,723 C 104,724 110,746 94,754
        C 84,759 77,751 82,744"/>
      <path d="M 362,738 C 348,728 352,711 368,712 C 383,713 387,730 374,737"/>
      <path d="M 640,742 C 625,731 630,711 648,713 C 663,715 666,733 652,740
        C 645,743 640,738 644,732"/>
      <path d="M 1054,746 C 1037,734 1042,715 1060,717 C 1075,719 1079,737 1064,744
        C 1057,747 1052,741 1056,735"/>
      <path d="M 1144,762 C 1129,750 1134,733 1151,735 C 1165,737 1168,752 1156,759"/>
    </g>
    <g stroke="#f9e9cf" stroke-width="3.4" opacity=".5">
      <path d="M 152,743 C 166,730 187,733 193,748 C 197,758 188,766 179,762"/>
      <path d="M 864,733 C 878,719 898,722 904,738 C 908,748 900,755 891,750"/>
      <path d="M 1128,730 C 1142,717 1161,721 1166,736 C 1169,745 1161,751 1154,747"/>
    </g>
  </g>
  <g fill="#fff3da" opacity=".34">
    <ellipse cx="248" cy="738" rx="86" ry="25"/>
    <ellipse cx="550" cy="721" rx="96" ry="24"/>
    <ellipse cx="893" cy="719" rx="87" ry="23"/>
    <ellipse cx="1165" cy="738" rx="88" ry="22"/>
  </g>
</g>
<g id="cloud-sea-mist" fill="none" stroke-linecap="round">
  <path d="M -30,660 C 96,644 200,651 304,667 C 416,685 526,681 642,660
    C 761,638 875,638 988,654 C 1096,670 1180,670 1240,661"
    stroke="#faead0" stroke-width="26" opacity=".24"/>
  <path d="M -20,684 C 112,670 220,679 328,693 C 432,707 540,708 653,690
    C 771,671 886,669 1000,682 C 1106,694 1186,694 1236,685"
    stroke="#f8e6c8" stroke-width="12" opacity=".24"/>
</g>
""".strip()

def wheel(cx, cy, base_angle=0.0):
    spokes = []
    for i in range(16):
        a = i * 22.5
        inner = polar((0, 0), 12, a + 13)
        outer = polar((0, 0), 101, a)
        sw = 2.8 if i % 4 == 0 else 1.55
        col = "#f1d79f" if i % 4 == 0 else "#b98d53"
        spokes.append(
            f'<path d="M {pt(inner)} L {pt(outer)}" stroke="{col}" '
            f'stroke-width="{sw}" opacity="{0.94 if i % 4 == 0 else .8}"/>')
    spokes = "\n".join(spokes)
    return f"""
<g transform="translate({fm(cx)} {fm(cy)})">
  <g transform="rotate({fm(base_angle)})">
    <animateTransform attributeName="transform" type="rotate" values="0;360"
      dur="{fm(WHEEL_DUR)}s" repeatCount="indefinite" calcMode="linear"/>
    <circle r="120" fill="none" stroke="#27322e" stroke-width="13"/>
    <circle r="112.5" fill="none" stroke="#e8d2a3" stroke-width="3.4" opacity=".92"/>
    <circle r="105" fill="none" stroke="#c39959" stroke-width="2.7"/>
    <g fill="none" stroke-linecap="round">{spokes}</g>
    <circle r="13" fill="#c79a54" stroke="#4b3b29" stroke-width="2.2"/>
    <circle r="6" fill="#3b3329"/>
    <path d="M 0,-104 L 0,-116" stroke="#d8b16e" stroke-width="3.2" stroke-linecap="round"/>
    <path d="M 89,-57 C 94,-51 96,-44 95,-37" fill="none" stroke="#d6aa62"
      stroke-width="2" stroke-linecap="round"/>
    <g transform="translate(75 -72) rotate(45)">
      <rect x="-7" y="-3.2" width="14" height="6.4" rx="3.2" fill="#c44931" stroke="#4d2c24" stroke-width="1"/>
      <rect x="-5" y="-1.5" width="7" height="3" rx="1.4" fill="#f4b06a" opacity=".7"/>
    </g>
  </g>
</g>""".strip()


def fender(cx, cy, a0, a1, scale=1.0):
    d = arc_path((cx, cy), 132 * scale, a0, a1)
    # small rolled mudflap at the rear-facing end
    end = polar((cx, cy), 132 * scale, a0)
    return f"""
<g>
  <path d="{d}" fill="none" stroke="#102e2c" stroke-width="10.5" stroke-linecap="round" opacity=".52"/>
  <path d="{d}" fill="none" stroke="url(#fenderG)" stroke-width="7.4" stroke-linecap="round"/>
  <path d="{d}" fill="none" stroke="#e6bf77" stroke-width="1.25" stroke-linecap="round" opacity=".9"/>
  <path d="M {pt(end)} C {end[0]-9:.1f},{end[1]+12:.1f} {end[0]-14:.1f},{end[1]+23:.1f} {end[0]-17:.1f},{end[1]+34:.1f}"
    fill="none" stroke="#1a4741" stroke-width="6.4" stroke-linecap="round"/>
  <path d="M {pt(end)} C {end[0]-9:.1f},{end[1]+12:.1f} {end[0]-14:.1f},{end[1]+23:.1f} {end[0]-17:.1f},{end[1]+34:.1f}"
    fill="none" stroke="#dfb870" stroke-width="1.5" stroke-linecap="round" opacity=".65"/>
  <path d="M {cx},{cy} L {end[0]:.1f},{end[1]:.1f}" stroke="#b9955e"
    stroke-width="1.8" opacity=".8"/>
  <path d="M {cx},{cy} L {polar((cx,cy),132*scale,a1)[0]:.1f},{polar((cx,cy),132*scale,a1)[1]:.1f}"
    stroke="#b9955e" stroke-width="1.4" opacity=".55"/>
  <circle cx="{end[0]:.1f}" cy="{end[1]:.1f}" r="2.2" fill="#e0b86f" stroke="#4c3926" stroke-width="1"/>
</g>""".strip()


def frame():
    tubes = {
        "chainstay": f"M {pt(REAR)} L {pt(BB)}",
        "seatstay": f"M {pt(REAR)} L 584,434",
        "seattube": f"M {pt(BB)} L 584,434",
        "toptube": "M 584,434 L 836,412",
        "downtube": f"M {pt(BB)} L 851,445",
        "headtube": "M 836,412 L 859,449",
        "fork": "M 857,445 C 874,488 895,543 918,594",
    }
    under = "\n".join(
        f'<path d="{d}" fill="none" stroke="#26322c" stroke-width="13" '
        f'stroke-linecap="round" stroke-linejoin="round" opacity=".5"/>'
        for d in tubes.values())
    over = "\n".join(
        f'<path d="{d}" fill="none" stroke="url(#frameG)" stroke-width="8.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        for d in tubes.values())
    return f"""
<g id="frame">
  {under}
  {over}
  <path d="M 592,427 L 827,406" fill="none" stroke="#d9ab63" stroke-width="1.5"
    stroke-linecap="round" opacity=".9"/>
  <path d="M 667,619 L 844,447" fill="none" stroke="#d9ab63" stroke-width="1.3"
    stroke-linecap="round" opacity=".72"/>
  <path d="M 457,579 C 517,595 594,616 648,624" fill="none" stroke="#84b39c"
    stroke-width="1.6" stroke-linecap="round" opacity=".35"/>
  <!-- lugs, badge and little brass details -->
  <g fill="#cba260" stroke="#4b3928" stroke-width="1.5">
    <circle cx="584" cy="434" r="7.2"/>
    <circle cx="836" cy="412" r="6.2"/>
    <circle cx="851" cy="445" r="5"/>
    <circle cx="658" cy="628" r="8.5"/>
  </g>
  <circle cx="584" cy="434" r="2.6" fill="#6a4b2d"/>
  <circle cx="836" cy="412" r="2.4" fill="#6a4b2d"/>
  <g transform="translate(846 432) rotate(-15)">
    <ellipse rx="8.5" ry="12.5" fill="#cba260" stroke="#4f3b27" stroke-width="1.6"/>
    <ellipse rx="4.8" ry="8.5" fill="#b83d2d"/>
    <path d="M -2,-4 L 1,0 L -1,4" fill="none" stroke="#f5d99c" stroke-width="1.2"/>
  </g>
  <circle cx="438" cy="594" r="7" fill="#c79a54" stroke="#4c3a29" stroke-width="2"/>
  <circle cx="438" cy="594" r="2.4" fill="#40382d"/>
  <circle cx="918" cy="594" r="7" fill="#c79a54" stroke="#4c3a29" stroke-width="2"/>
  <circle cx="918" cy="594" r="2.4" fill="#40382d"/>
  <path d="M 844,451 C 836,470 830,485 827,499" fill="none" stroke="#c49a5b"
    stroke-width="2" stroke-linecap="round" opacity=".55"/>
</g>""".strip()


def saddle_and_bars():
    return """
<g id="saddle">
  <path d="M 584,434 L 564,412" stroke="#b68e59" stroke-width="7" stroke-linecap="round"/>
  <path d="M 584,434 L 564,412" stroke="#e5c890" stroke-width="2.4" stroke-linecap="round" opacity=".8"/>
  <path d="M 517,405 C 527,392 551,388 570,391
    C 585,393 599,389 611,394 C 620,398 609,408 593,410
    L 551,417 C 532,419 515,414 517,405 Z"
    fill="#70422e" stroke="#3d2b22" stroke-width="3.4"/>
  <path d="M 526,402 C 539,394 560,395 577,397 C 589,399 599,396 606,398"
    fill="none" stroke="#a56d47" stroke-width="3" stroke-linecap="round" opacity=".8"/>
  <g fill="#e0b76d">
    <circle cx="532" cy="408" r="1.7"/><circle cx="548" cy="408" r="1.7"/>
    <circle cx="594" cy="402" r="1.7"/>
  </g>
  <path d="M 530,415 L 534,426 M 540,414 L 543,425" stroke="#9f7748"
    stroke-width="2.2" stroke-linecap="round" opacity=".8"/>
</g>
<g id="handlebars">
  <path d="M 836,412 L 826,388" fill="none" stroke="#3a3127" stroke-width="10"
    stroke-linecap="round"/>
  <path d="M 836,412 L 826,388" fill="none" stroke="#d0aa68" stroke-width="5.2"
    stroke-linecap="round"/>
  <circle cx="836" cy="412" r="5.2" fill="#c79b58" stroke="#493a28" stroke-width="1.7"/>
  <path d="M 800,400 C 805,378 822,369 842,375 C 853,378 861,384 867,391"
    fill="none" stroke="#3c3027" stroke-width="9" stroke-linecap="round"/>
  <path d="M 800,400 C 805,378 822,369 842,375 C 853,378 861,384 867,391"
    fill="none" stroke="#d5b276" stroke-width="4.8" stroke-linecap="round"/>
  <path d="M 849,374 C 861,376 870,383 874,392" fill="none" stroke="#70452f"
    stroke-width="9.5" stroke-linecap="round"/>
  <path d="M 849,374 C 861,376 870,383 874,392" fill="none" stroke="#9c6846"
    stroke-width="3" stroke-linecap="round" opacity=".7"/>
  <path d="M 807,398 C 802,407 791,410 784,407" fill="none" stroke="#a7793c"
    stroke-width="2.2" stroke-linecap="round"/>
  <g id="handlebar-bell" transform="translate(816 378)">
    <circle r="7.4" fill="#cda35f" stroke="#4d3926" stroke-width="2"/>
    <path d="M -4,-2 C -3,-6 3,-6 4,-2" fill="none" stroke="#f3dba4" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="0" cy="2" r="1.7" fill="#5f432b"/>
  </g>
  <g transform="translate(799 397)">
    <g transform="rotate(-3)">
      <animateTransform attributeName="transform" type="rotate"
        values="-4;4;-1;5;-4" dur="1.9s" repeatCount="indefinite"
        calcMode="spline" keyTimes="0;0.25;0.5;0.75;1"
        keySplines="0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1;0.42 0 0.58 1"/>
      <path d="M 0,0 C -4,13 -13,21 -19,27" fill="none" stroke="#b83b2c" stroke-width="3"
        stroke-linecap="round"/>
      <path d="M -19,27 L -22,42 M -18,28 L -16,43 M -20,27 L -25,39"
        stroke="#c34b37" stroke-width="2.2" stroke-linecap="round"/>
      <circle cx="-1" cy="1" r="3.1" fill="#cba15a" stroke="#503a28" stroke-width="1.4"/>
    </g>
  </g>
  <path d="M 793,406 C 813,420 843,432 865,449" fill="none" stroke="#6f4b35"
    stroke-width="1.2" opacity=".7"/>
</g>""".strip()


def chain_and_crank(base_phase):
    # two tangent-ish strands between the rear cog and the chainring
    return f"""
<g id="chain">
  <path d="M 438,581 C 504,580 590,586 658,596" fill="none" stroke="#3b3d35"
    stroke-width="3.1" stroke-dasharray="4 5"/>
  <path d="M 438,607 C 504,633 593,652 658,660" fill="none" stroke="#3b3d35"
    stroke-width="3.1" stroke-dasharray="4 5"/>
  <path d="M 438,581 C 504,580 590,586 658,596" fill="none" stroke="#b8a06a"
    stroke-width="1" stroke-dasharray="1 8" opacity=".6">
    <animate attributeName="stroke-dashoffset" values="0;-18" dur=".8s"
      repeatCount="indefinite" calcMode="linear"/>
  </path>
  <circle cx="438" cy="594" r="13" fill="#5b4b35" stroke="#2f2b22" stroke-width="2.2"/>
  <circle cx="438" cy="594" r="5.5" fill="#b69355"/>
</g>
<g id="crank" transform="translate({fm(BB[0])} {fm(BB[1])})">
  <g transform="rotate({fm(base_phase)})">
    <animateTransform attributeName="transform" type="rotate"
      values="{fm(base_phase)};{fm(base_phase + 360)}"
      dur="{fm(CADENCE)}s" repeatCount="indefinite" calcMode="linear"/>
    <g id="chainring">
      <circle r="35" fill="none" stroke="#3b4038" stroke-width="2"/>
      <circle r="35" fill="none" stroke="#c79a52" stroke-width="7.5"
        stroke-dasharray="3.4 3.8" opacity=".95"/>
      <circle r="27.5" fill="none" stroke="#b48b50" stroke-width="3.2"/>
      <g fill="none" stroke="#8d6c3f" stroke-width="2.2">
        <circle cx="17" cy="0" r="3.7"/><circle cx="8.5" cy="14.7" r="3.7"/>
        <circle cx="-8.5" cy="14.7" r="3.7"/><circle cx="-17" cy="0" r="3.7"/>
        <circle cx="-8.5" cy="-14.7" r="3.7"/><circle cx="8.5" cy="-14.7" r="3.7"/>
      </g>
      <circle r="4.6" fill="#d4ac68" stroke="#41372a" stroke-width="1.5"/>
    </g>
    <path d="M 0,0 L -{fm(CRANK_R)},0" stroke="#484238" stroke-width="7.5"
      stroke-linecap="round"/>
    <path d="M 0,0 L {fm(CRANK_R)},0" stroke="#b8955b" stroke-width="7.5"
      stroke-linecap="round"/>
    <g transform="translate(-{fm(CRANK_R)} 0)">
      <g transform="rotate({fm(-base_phase)})">
        <animateTransform attributeName="transform" type="rotate"
          values="{fm(-base_phase)};{fm(-base_phase - 360)}"
          dur="{fm(CADENCE)}s" repeatCount="indefinite" calcMode="linear"/>
        <rect x="-16" y="-3.2" width="32" height="6.4" rx="3.2" fill="#4a4337"
          stroke="#2c2a23" stroke-width="1.2"/>
        <circle cx="14" cy="0" r="2.2" fill="#c05437"/>
      </g>
    </g>
    <g transform="translate({fm(CRANK_R)} 0)">
      <g transform="rotate({fm(-base_phase)})">
        <animateTransform attributeName="transform" type="rotate"
          values="{fm(-base_phase)};{fm(-base_phase - 360)}"
          dur="{fm(CADENCE)}s" repeatCount="indefinite" calcMode="linear"/>
        <rect x="-17" y="-3.4" width="34" height="6.8" rx="3.4" fill="#cba463"
          stroke="#41362a" stroke-width="1.4"/>
        <circle cx="-12" cy="0" r="2.1" fill="#d8bd88"/>
      </g>
    </g>
    <circle r="6.4" fill="#cda460" stroke="#3f3528" stroke-width="1.8"/>
  </g>
</g>""".strip()


def bike(base_phase):
    return f"""
<g id="bike-under-shadow" fill="#40534a" opacity=".12" filter="url(#blurSoft)">
  <ellipse cx="680" cy="738" rx="300" ry="25"/>
</g>
<g id="wheel-shadows" fill="#3b4e45" opacity=".17" filter="url(#blurSoft)">
  <ellipse cx="{fm(REAR[0])}" cy="726" rx="116" ry="12"/>
  <ellipse cx="{fm(FRONT[0])}" cy="726" rx="116" ry="12"/>
</g>
<g id="rear-wheel">{wheel(*REAR)}</g>
<g id="front-wheel">{wheel(*FRONT)}</g>
<g id="rear-fender">{fender(*REAR, 196, 344)}</g>
<g id="front-fender">{fender(*FRONT, 202, 338, .96)}</g>
{frame()}
{chain_and_crank(base_phase)}
{saddle_and_bars()}
""".strip()


# --------------------------------------------------------------------------
# Sun Wukong
# --------------------------------------------------------------------------


def boot(side, base_phase):
    far = side == "far"
    near_col = {
        "main": "#4b3027", "shade": "#31201d", "lip": "#201715",
        "trim": "#e2b665", "red": "#a93729", "sole": "#d8c099",
    }
    far_col = {
        "main": "#3a2722", "shade": "#261a18", "lip": "#191210",
        "trim": "#b38c4e", "red": "#7e2b22", "sole": "#ad9676",
    }
    c = far_col if far else near_col
    off = -CRANK_R if far else CRANK_R
    opacity = ".94" if far else "1"
    detail = "url(#bootG)" if not far else "url(#bootGFar)"
    return f"""
<g transform="translate({fm(BB[0])} {fm(BB[1])})">
  <g transform="rotate({fm(base_phase)})">
    <animateTransform attributeName="transform" type="rotate"
      values="{fm(base_phase)};{fm(base_phase + 360)}"
      dur="{fm(CADENCE)}s" repeatCount="indefinite" calcMode="linear"/>
    <g transform="translate({fm(off)} 0)">
      <g transform="rotate({fm(-base_phase)})">
        <animateTransform attributeName="transform" type="rotate"
          values="{fm(-base_phase)};{fm(-base_phase - 360)}"
          dur="{fm(CADENCE)}s" repeatCount="indefinite" calcMode="linear"/>
        <g opacity="{opacity}">
          <path d="M -30,-44
            C -35,-26 -30,-9 -21,-5
            L 22,-5
            C 38,-5 51,-12 55,-22
            C 58,-28 52,-31 46,-29
            C 42,-42 29,-53 13,-57
            L 10,-67
            L -2,-59
            C -14,-57 -25,-52 -30,-44 Z"
            fill="{detail}" stroke="#2d1d18" stroke-width="4"/>
          <path d="M -25,-7 L 24,-7 C 39,-7 49,-13 55,-22 C 51,-12 40,-2 24,-2
            L -20,-2 C -26,-2 -28,-4 -25,-7 Z"
            fill="{c['sole']}" opacity=".9"/>
          <path d="M -27,-43 C -13,-51 5,-55 12,-56 L 15,-47
            C 5,-48 -12,-44 -23,-36 Z" fill="{c['red']}" stroke="#2d1d18" stroke-width="2.2"/>
          <path d="M -24,-36 C -14,-44 3,-47 15,-46" fill="none" stroke="{c['trim']}"
            stroke-width="3.2" stroke-linecap="round"/>
          <path d="M 47,-27 C 54,-31 59,-37 59,-43 C 59,-48 54,-51 49,-48
            C 44,-45 47,-39 51,-40" fill="none" stroke="{c['trim']}" stroke-width="3"
            stroke-linecap="round"/>
          <path d="M -3,-58 L -1,-45 M 7,-58 L 7,-47" stroke="{c['trim']}"
            stroke-width="2" stroke-linecap="round" opacity=".8"/>
          <path d="M 15,-54 C 28,-50 37,-41 40,-32" fill="none" stroke="{c['shade']}"
            stroke-width="2" stroke-linecap="round" opacity=".55"/>
          <circle cx="45" cy="-37" r="2.2" fill="{c['trim']}" opacity=".9"/>
          <g fill="{"#d99f45" if not far else "#b88943"}" stroke="#2d1d18" stroke-width="1.5">
            <path d="M -21,-57 C -27,-61 -27,-67 -21,-71 C -21,-66 -17,-62 -12,-60 Z"/>
            <path d="M 9,-62 C 8,-67 12,-72 17,-72 C 16,-67 18,-63 21,-59 Z"/>
          </g>
        </g>
      </g>
    </g>
  </g>
</g>""".strip()


def legs(base_phase):
    nv_t, nv_s = leg_values(HIP_N, 1, base_phase)
    fv_t, fv_s = leg_values(HIP_F, -1, base_phase)
    nb_t, nb_s = leg_base(HIP_N, base_phase, 1)
    fb_t, fb_s = leg_base(HIP_F, base_phase, -1)
    nt_anim, ns_anim = anim_d(nv_t), anim_d(nv_s)
    ft_anim, fs_anim = anim_d(fv_t), anim_d(fv_s)

    def pair(td, sd, ta, sa, far=False):
        if far:
            outer = "#32231c"
            inner = "url(#legFarG)"
            width_out, width_in = 34.0, 26.0
        else:
            outer = "#3a2920"
            inner = "url(#legG)"
            width_out, width_in = 37.0, 29.5
        return f"""
<g id="{'far' if far else 'near'}-leg" stroke-linecap="round" stroke-linejoin="round">
  <g fill="none" stroke="{outer}" stroke-width="{width_out}" opacity=".96">
    <path d="{td}">{ta}</path>
    <path d="{sd}">{sa}</path>
  </g>
  <g fill="none" stroke="{inner}" stroke-width="{width_in}">
    <path d="{td}">{ta}</path>
    <path d="{sd}">{sa}</path>
  </g>
</g>"""

    # Build the far leg + boot, then the near one.  Each boot has its own
    # counter-rotating rider inside the crank so the sole stays level.
    far_leg = pair(fb_t, fb_s, ft_anim, fs_anim, far=True)
    near_leg = pair(nb_t, nb_s, nt_anim, ns_anim, far=False)
    return far_leg, boot("far", base_phase), near_leg, boot("near", base_phase)


def staff():
    """The Ruyi Jingu Bang, slung behind the rider from the left shoulder."""
    tassel_swing = anim_rot_values("-4.2;3.1;-1.6;4.4;-4.2", 2.3,
                                   "0;0.25;0.5;0.75;1",
                                   ";".join([SINE] * 4))
    return f"""
<g id="staff" transform="translate(596 288) rotate(-124.0)">
  <g>
    <rect x="-172" y="-9" width="344" height="18" rx="9"
      fill="#5f4024" opacity=".2" transform="translate(3 5)"/>
    <rect x="-172" y="-8" width="344" height="16" rx="8"
      fill="url(#staffG)" stroke="#4b3321" stroke-width="2.3"/>
    <g fill="none" stroke="#6d4a24" stroke-width="2" opacity=".75">
      <path d="M -140,-8 L -140,8"/><path d="M -132,-8 L -132,8"/>
      <path d="M 132,-8 L 132,8"/><path d="M 140,-8 L 140,8"/>
    </g>
    <g fill="none" stroke="#f7e0a5" stroke-width="1.5" stroke-linecap="round" opacity=".55">
      <path d="M -121,-3 C -117,-1 -117,2 -120,4"/>
      <path d="M -30,-4 C -25,-2 -25,3 -30,5"/>
      <path d="M 52,-4 C 57,-1 57,3 52,5"/>
      <path d="M -156,-3 L 156,-3"/>
    </g>
    <rect x="-172" y="-8" width="28" height="16" rx="8"
      fill="#a52f25" stroke="#4c2a22" stroke-width="2"/>
    <rect x="144" y="-8" width="28" height="16" rx="8"
      fill="#a52f25" stroke="#4c2a22" stroke-width="2"/>
    <path d="M -164,-4 C -161,-2 -161,2 -164,4 M 164,-4 C 167,-2 167,2 164,4"
      fill="none" stroke="#f0d08a" stroke-width="1.2" opacity=".8"/>
    <path d="M -160,0 L -151,0 M 151,0 L 160,0" stroke="#5b2f24"
      stroke-width="1.4" opacity=".6"/>
  </g>
</g>
<g id="staff-tassel" transform="translate(500 146)">
  <g transform="rotate(-16)">
    <animateTransform attributeName="transform" type="rotate"
      values="-18;-12;-20;-13;-18" dur="2.3s" repeatCount="indefinite"
      calcMode="spline" keyTimes="0;0.25;0.5;0.75;1"
      keySplines="{";".join([SINE] * 4)}"/>
    <path d="M 0,0 C -12,13 -16,29 -12,46
      C -3,33 5,24 9,10 Z" fill="#b83b2c" stroke="#54281f" stroke-width="2"/>
    <path d="M 1,7 C -6,18 -8,31 -6,42" fill="none" stroke="#e7b258"
      stroke-width="1.9" stroke-linecap="round" opacity=".8"/>
    <path d="M -12,46 L -17,58 M -10,48 L -11,60 M -7,46 L -3,58"
      stroke="#c34a36" stroke-width="2.1" stroke-linecap="round"/>
    <circle cx="1" cy="-1" r="4.2" fill="#d9aa56" stroke="#4c3320" stroke-width="1.5"/>
  </g>
</g>"""

def tail_and_cape():
    cape_swing = anim_rot_values("-2.1;1.1;-0.7;2.3;-2.1", 1.65,
                                 "0;0.25;0.5;0.75;1",
                                 ";".join([SOFT] * 4))
    cape2_swing = anim_rot_values("-1.3;2.0;0.2;1.2;-1.3", 1.95,
                                  "0;0.25;0.5;0.75;1",
                                  ";".join([SINE] * 4))
    tail_swing = anim_rot_values("-4.0;2.0;-2.4;3.1;-4.0", 2.8,
                                 "0;0.25;0.5;0.75;1",
                                 ";".join([SINE] * 4))
    cape = f"""
<g id="cape-under" opacity=".96">
  {pivot_local(674, 312, 0, cape2_swing, '''
    <path d="M 670,311 C 634,333 585,347 536,350 C 563,366 602,367 637,352
      C 651,344 663,332 674,322 Z" fill="#7f211e" stroke="#4f1d1a" stroke-width="3.5"/>
    <path d="M 635,350 C 611,359 584,362 565,357" fill="none" stroke="#d6aa5f"
      stroke-width="2.2" stroke-linecap="round" opacity=".7"/>
  ''')}
</g>
<g id="cape">
  {pivot_local(700, 302, 0, cape_swing, '''
    <path d="M 702,294
      C 666,268 607,264 555,281
      C 505,297 461,324 404,328
      C 440,347 482,349 520,333
      C 534,354 564,360 591,346
      C 609,360 640,357 662,340
      C 680,348 699,332 708,313 Z"
      fill="url(#capeG)" stroke="#4e1b18" stroke-width="4"/>
    <path d="M 688,301 C 648,279 598,281 552,295 C 510,308 470,329 429,334"
      fill="none" stroke="#d9ae65" stroke-width="2" opacity=".55"/>
    <path d="M 652,310 C 618,309 580,316 545,328 C 569,334 600,329 627,319
      C 645,313 656,316 663,320 Z" fill="#8d241e" opacity=".7"/>
    <path d="M 604,340 C 590,347 570,350 551,348" fill="none" stroke="#d9a75c"
      stroke-width="3.4" stroke-linecap="round"/>
    <path d="M 544,331 C 526,339 506,343 486,342" fill="none" stroke="#d9a75c"
      stroke-width="3" stroke-linecap="round" opacity=".8"/>
    <g fill="none" stroke="#ecc47b" stroke-width="1.7" stroke-linecap="round" opacity=".7">
      <path d="M 582,315 C 574,308 579,298 590,299 C 599,300 601,309 594,312
        C 589,314 585,310 587,305"/>
      <path d="M 628,307 C 622,300 628,291 638,293 C 646,295 646,304 639,306"/>
    </g>
  ''')}
</g>
<g id="tail">
  {pivot_local(548, 438, 0, tail_swing, '''
    <path d="M 548,438 C 519,465 484,467 455,447
      C 429,429 421,397 440,378 C 458,359 484,367 491,387
      C 498,405 484,417 470,411 C 460,407 458,395 463,387"
      fill="none" stroke="#3a281f" stroke-width="24" stroke-linecap="round"/>
    <path d="M 548,438 C 519,465 484,467 455,447
      C 429,429 421,397 440,378 C 458,359 484,367 491,387
      C 498,405 484,417 470,411 C 460,407 458,395 463,387"
      fill="none" stroke="url(#tailG)" stroke-width="17.5" stroke-linecap="round"/>
    <path d="M 538,442 C 507,466 476,461 452,443" fill="none" stroke="#f2c871"
      stroke-width="2.4" stroke-linecap="round" opacity=".4"/>
    <path d="M 459,398 C 449,389 448,374 456,365
      C 459,374 466,379 474,378 C 471,389 466,398 460,406 Z"
      fill="#e7b45a" stroke="#3a281f" stroke-width="2.2"/>
    <path d="M 431,402 C 422,392 423,378 431,369 C 433,379 439,385 447,386
      C 441,393 437,400 434,410 Z" fill="#eab85d" stroke="#3a281f" stroke-width="2"/>
    <path d="M 449,450 C 457,442 467,440 474,444 C 467,449 462,454 458,459 Z"
      fill="#eab85d" stroke="#3a281f" stroke-width="2"/>
    <path d="M 472,410 C 465,400 467,391 473,384" fill="none" stroke="#f0c46e"
      stroke-width="2" stroke-linecap="round" opacity=".55"/>
  ''')}
</g>"""
    return cape.strip()


def pelt_and_sash():
    """A proper tiger-skin wrap that closes the gap between jacket and legs."""
    tail_ribbon = anim_rot_values("-3.2;2.2;-1.4;3.0;-3.2", 2.2,
                                  "0;0.25;0.5;0.75;1",
                                  ";".join([SINE] * 4))
    left_ribbon = anim_rot_values("-4.0;2.5;-1.0;3.5;-4.0", 1.8,
                                  "0;0.25;0.5;0.75;1",
                                  ";".join([SOFT] * 4))
    return f"""
<g id="pelvis" transform="translate(0 106.4) scale(1 .72)">
  <path d="M 536,384 C 558,374 590,377 616,385
    C 644,393 668,392 691,380 C 702,400 699,428 681,446
    C 662,465 635,471 612,458 C 589,470 555,460 540,438
    C 529,421 528,400 536,384 Z"
    fill="#8c562b" stroke="#39261e" stroke-width="3.8"/>
  <path d="M 663,382 C 679,382 690,378 698,372 C 704,383 703,398 696,410"
    fill="none" stroke="#b47433" stroke-width="2" opacity=".55"/>
  <g id="tiger-pelt">
    <path d="M 526,388
      C 555,374 587,379 616,386
      C 648,394 675,390 701,375
      L 709,396 L 692,405 L 700,421 L 681,422 L 684,441
      L 661,436 L 663,456 L 639,449 L 637,468
      L 612,456 L 599,473 L 582,457 L 562,467
      L 557,447 L 537,452 L 543,432 L 521,431 L 530,412 Z"
      fill="url(#peltG)" stroke="#36251d" stroke-width="3.8" stroke-linejoin="round"/>
    <path d="M 533,394 C 560,384 589,390 616,395
      C 647,401 673,398 696,383" fill="none" stroke="#f5d48b"
      stroke-width="4.6" stroke-linecap="round" opacity=".9"/>
    <path d="M 528,415 C 546,437 565,452 589,462
      C 612,471 636,461 653,445 C 676,425 693,406 705,390"
      fill="none" stroke="#f0c476" stroke-width="5.2" stroke-linecap="round"
      opacity=".6" stroke-dasharray="2 18"/>
    <!-- bold tiger bars -->
    <g fill="#36271f" opacity=".94">
      <path d="M 549,388 C 556,402 559,421 557,443
        C 551,436 544,432 539,431 C 544,415 545,401 541,391 Z"/>
      <path d="M 578,385 C 587,403 591,426 590,452
        C 583,449 577,450 572,455 C 575,434 572,412 564,392 Z"/>
      <path d="M 610,389 C 619,408 624,431 624,456
        C 617,452 610,453 604,458 C 608,436 605,414 598,394 Z"/>
      <path d="M 644,391 C 653,406 658,424 660,442
        C 653,438 647,440 642,444 C 644,427 640,410 633,394 Z"/>
      <path d="M 676,385 C 684,397 689,410 690,424
        C 684,421 679,422 675,426 C 677,412 672,399 666,389 Z"/>
    </g>
    <g fill="#f5dfb3" opacity=".7">
      <path d="M 586,466 C 591,461 598,459 603,460 C 598,464 594,467 590,469 Z"/>
      <path d="M 651,449 C 656,446 661,445 665,447 C 661,451 657,454 653,456 Z"/>
      <path d="M 531,423 C 536,420 541,421 545,424 C 541,427 537,429 534,431 Z"/>
    </g>
  </g>
  <g id="sash">
    <path d="M 526,379 C 558,373 592,384 626,389
      C 658,394 681,389 704,377 L 711,396
      C 681,409 649,411 615,405 C 580,399 550,398 519,400 Z"
      fill="url(#sashG)" stroke="#45311f" stroke-width="3.4" stroke-linejoin="round"/>
    <path d="M 529,384 C 560,379 591,389 625,394
      C 655,398 678,394 699,385" fill="none" stroke="#f9e2a7"
      stroke-width="2.1" stroke-linecap="round" opacity=".8"/>
    <path d="M 521,395 C 548,394 577,398 611,403 C 645,409 677,406 707,392"
      fill="none" stroke="#9b6829" stroke-width="2.4" stroke-linecap="round"
      opacity=".6"/>
    <g transform="translate(566 391)">
      <path d="M -13,0 C -9,-13 8,-15 14,0 C 9,12 -8,13 -13,0 Z"
        fill="#cba15d" stroke="#483421" stroke-width="2"/>
      <path d="M 0,-8 C 6,-2 6,5 0,9 C -6,4 -6,-2 0,-8 Z" fill="#f5d797"/>
      <circle cx="0" cy="0" r="2.4" fill="#337068"/>
    </g>
    {pivot_local(540, 396, 0, left_ribbon, '''
      <path d="M 540,394 C 520,404 505,420 504,438
        L 495,435 C 499,416 515,398 534,388 Z"
        fill="#b73a2c" stroke="#4b231d" stroke-width="2.4"/>
      <path d="M 526,405 C 514,414 508,426 508,436" fill="none"
        stroke="#e9b45f" stroke-width="1.8" stroke-linecap="round" opacity=".75"/>
      <path d="M 504,438 L 498,451 M 504,438 L 509,452 M 504,438 L 500,457"
        stroke="#c54a35" stroke-width="2" stroke-linecap="round"/>
    ''')}
    <path d="M 576,400 C 570,413 565,424 563,436
      M 585,401 C 583,414 582,426 584,438"
      fill="none" stroke="#b73a2d" stroke-width="3" stroke-linecap="round"/>
    <path d="M 563,436 L 557,448 M 563,436 L 570,447
      M 584,438 L 577,449 M 584,438 L 591,446"
      stroke="#c54a35" stroke-width="2" stroke-linecap="round"/>
  </g>
</g>"""

def torso_and_arms():
    return """
<g id="torso">
  <path d="M 558,392
    C 556,364 575,335 607,315
    C 634,298 666,286 695,290
    C 716,292 730,306 729,322
    C 728,337 716,350 701,357
    C 689,363 681,372 674,385
    C 665,400 646,410 623,412
    C 594,414 567,407 558,398 Z"
    fill="url(#tunicG)" stroke="#3a2720" stroke-width="4.4"/>
  <path d="M 567,385 C 574,363 593,341 619,324 C 643,308 670,297 690,296"
    fill="none" stroke="#ebbf78" stroke-width="2.1" stroke-linecap="round" opacity=".42"/>
  <path d="M 666,400 C 677,382 688,369 704,360 C 713,355 720,348 725,341"
    fill="none" stroke="#7b211b" stroke-width="8" stroke-linecap="round" opacity=".34"/>
  <!-- neck opening and cloud-edged collar -->
  <path d="M 688,297 C 709,300 724,311 730,326 C 714,333 699,327 687,316 Z"
    fill="#f2d6a0" stroke="#3a2720" stroke-width="2.8"/>
  <path d="M 695,304 C 710,308 719,315 724,323" fill="none" stroke="#bd8d43"
    stroke-width="2.2" stroke-linecap="round"/>
  <path d="M 690,316 C 700,320 711,322 721,320" fill="none" stroke="#b73a2d"
    stroke-width="4" stroke-linecap="round"/>
  <!-- saffron sash edge and tunic hem -->
  <path d="M 558,401 C 584,415 617,422 660,410" fill="none" stroke="#d6a250"
    stroke-width="2.1" stroke-linecap="round" opacity=".7"/>
  <path d="M 664,400 C 653,415 632,424 611,427" fill="none" stroke="#6c1d19"
    stroke-width="3" stroke-linecap="round" opacity=".5"/>
  <!-- gold cloud embroidery, kept large enough to read at poster size -->
  <g fill="none" stroke="#e6bc70" stroke-width="2.1" stroke-linecap="round" opacity=".7">
    <path d="M 626,348 C 618,338 624,326 636,327 C 646,328 649,339 642,344
      C 636,348 630,344 633,338"/>
    <path d="M 649,333 C 651,322 665,321 671,330"/>
    <path d="M 612,365 C 605,359 607,350 615,349 C 623,348 626,357 621,361"/>
  </g>
  <g transform="translate(672 367)">
    <circle r="9.2" fill="#cfa45d" stroke="#4c3524" stroke-width="2.1"/>
    <circle r="5.6" fill="#2f6860"/>
    <path d="M -3,-3 C 0,-5 3,-3 3,0 C 2,3 -2,3 -2,0" fill="none" stroke="#d8c590"
      stroke-width="1.2"/>
  </g>
  <!-- leather harness that carries the staff on his back -->
  <path d="M 656,313 C 671,334 686,356 696,383" fill="none" stroke="#422a20"
    stroke-width="13" stroke-linecap="round"/>
  <path d="M 656,313 C 671,334 686,356 696,383" fill="none" stroke="#6a4230"
    stroke-width="8" stroke-linecap="round"/>
  <g transform="translate(681 348) rotate(64)">
    <rect x="-9" y="-12" width="18" height="24" rx="4" fill="#cba15a"
      stroke="#463221" stroke-width="1.8"/>
    <rect x="-4" y="-7" width="8" height="14" rx="2" fill="#8e2d22"/>
    <circle cx="0" cy="0" r="2.1" fill="#eac77e"/>
  </g>
  <circle cx="661" cy="322" r="3.1" fill="#d0a45d" stroke="#4b3422" stroke-width="1.5"/>
  <circle cx="691" cy="372" r="2.6" fill="#d0a45d" stroke="#4b3422" stroke-width="1.4"/>
  <!-- a little shoulder armour, then the near arm -->
  <path d="M 676,303 C 688,294 708,292 720,301 C 713,313 692,319 677,313 Z"
    fill="#6d3828" stroke="#35231d" stroke-width="3.2"/>
  <path d="M 682,305 C 692,299 705,298 714,302" fill="none" stroke="#d2a45d"
    stroke-width="2.4" stroke-linecap="round"/>
</g>
<g id="far-arm" opacity=".88">
  <path d="M 669,310 C 701,326 730,348 767,360" fill="none" stroke="#3a281f"
    stroke-width="29" stroke-linecap="round"/>
  <path d="M 669,310 C 701,326 730,348 767,360" fill="none" stroke="url(#furFarG)"
    stroke-width="22" stroke-linecap="round"/>
</g>
<g id="near-arm">
  <path d="M 699,308 C 731,319 758,341 790,357 C 807,366 822,373 836,378"
    fill="none" stroke="#3a281f" stroke-width="38" stroke-linecap="round"/>
  <path d="M 699,308 C 731,319 758,341 790,357 C 807,366 822,373 836,378"
    fill="none" stroke="url(#furG)" stroke-width="31" stroke-linecap="round"/>
  <path d="M 711,313 C 738,327 765,348 793,363" fill="none" stroke="#f5ce7c"
    stroke-width="2.7" stroke-linecap="round" opacity=".5"/>
  <!-- fur tufts at the elbow -->
  <path d="M 744,345 C 735,353 735,363 744,369 C 747,361 753,355 760,353 Z"
    fill="#d1943f" stroke="#3a281f" stroke-width="2.2"/>
  <g transform="translate(789 357) rotate(28)">
    <rect x="-10" y="-17" width="20" height="34" rx="8" fill="#6e3d2a"
      stroke="#35231d" stroke-width="2.6"/>
    <path d="M -8,-10 L 8,-10 M -8,0 L 8,0 M -8,10 L 8,10" stroke="#d7ae66"
      stroke-width="1.8" stroke-linecap="round"/>
    <circle cx="0" cy="0" r="2.2" fill="#d7ae66"/>
  </g>
  <path d="M 824,371 C 835,369 847,374 851,383 C 854,391 847,398 837,398
    C 827,397 820,389 824,383 C 827,378 834,378 838,382
    C 842,386 840,391 835,392"
    fill="#e0a24c" stroke="#3a281f" stroke-width="3"/>
  <path d="M 836,380 C 841,382 843,387 840,390" fill="none" stroke="#7d4c24"
    stroke-width="1.8" stroke-linecap="round"/>
</g>""".strip()


def head_group():
    """The Monkey King's head, authored around local (0, 0).

    Two tapered pheasant plumes, a cloud-scroll circlet and a broad golden
    mane do the recognisability work; the face is kept long and a little
    narrow so the silhouette reads as a monkey rather than a teddy bear.
    """
    blink = anim_scale("1 1;1 1;1 .08;1 .08;1 1;1 1", 5.4,
                       "0;.78;.81;.84;.87;1",
                       "0 0 1 1;0.3 0 0.2 1;0 0 1 1;0.3 0 0.2 1;0.3 0 0.2 1")
    glare = anim_opacity("0;0.8;0;0.55;0;0", 4.4, "0;0.18;0.3;0.55;0.68;1")
    ear_swing = anim_rot_values("-4;3;-1;4;-4", 3.4,
                                "0;0.25;0.5;0.75;1",
                                ";".join([SINE] * 4))

    def feather(pid, root, base, path, bands, dur, vals):
        clip_id = f"plumeClip{pid}"
        band_markup = "".join(
            f'<path d="{b}" fill="none" stroke="#2f211c" stroke-width="9" '
            f'stroke-linecap="butt"/>' for b in bands)
        return f"""
<defs>
  <clipPath id="{clip_id}" clipPathUnits="userSpaceOnUse">
    <path d="{path}"/>
  </clipPath>
</defs>
<g transform="translate({fm(root[0])} {fm(root[1])})">
  <g transform="rotate({fm(base)})">
    <animateTransform attributeName="transform" type="rotate"
      values="{vals}" dur="{dur}s" repeatCount="indefinite"
      calcMode="spline" keyTimes="0;0.25;0.5;0.75;1"
      keySplines="{";".join([SINE] * 4)}"/>
    <path d="{path}" fill="url(#plumeG)" stroke="#40251e" stroke-width="2.7"
      stroke-linejoin="round"/>
    <g clip-path="url(#{clip_id})">{band_markup}</g>
    <path d="{path}" fill="none" stroke="#e9b85d" stroke-width="1.4"
      stroke-linejoin="round" opacity=".8"/>
    <path d="M -7,3 C -49,-33 -102,-70 -156,-78 C -181,-82 -202,-77 -218,-67"
      fill="none" stroke="#f4cf7c" stroke-width="2.1" stroke-linecap="round"
      opacity=".5"/>
    <path d="M 2,-2 C -13,5 -24,8 -36,11" fill="none" stroke="#6e2a21"
      stroke-width="2" stroke-linecap="round" opacity=".6"/>
  </g>
</g>"""

    big_plume = feather(
        "A", (-51, -64), 0,
        "M 0,-7 C -45,-50 -104,-83 -162,-90 C -192,-94 -214,-88 -233,-76 "
        "C -208,-74 -184,-66 -164,-52 C -118,-21 -60,-4 -5,13 "
        "C -7,6 -5,1 0,-7 Z",
        ["M -97,-94 C -100,-79 -103,-66 -107,-54",
         "M -140,-90 C -145,-74 -148,-61 -151,-50",
         "M -180,-84 C -186,-71 -189,-60 -191,-52"],
        4.6, "-1.4;0.7;1.3;0.2;-1.4")
    small_plume = feather(
        "B", (-34, -43), 0,
        "M 0,-5 C -38,-30 -88,-47 -137,-47 C -159,-47 -177,-42 -192,-33 "
        "C -170,-33 -150,-26 -133,-15 C -96,9 -49,21 -5,18 "
        "C -5,10 -3,3 0,-5 Z",
        ["M -80,-44 C -83,-33 -85,-24 -87,-16",
         "M -120,-43 C -123,-32 -124,-24 -125,-17",
         "M -157,-36 C -160,-28 -161,-23 -162,-17"],
        5.4, "1.1;-0.8;-0.2;1.4;1.1")

    left_eye = f"""
<g transform="translate(-23 -14) scale(.95 .77)">
  <g>{blink}
    <path d="M -18,-1 C -12,-12 8,-14 16,-3 C 10,8 -8,12 -18,-1 Z"
      fill="#fff3d2" stroke="#35211b" stroke-width="2.6"/>
    <path d="M -16,-4 C -9,-13 7,-13 14,-4" fill="none" stroke="#45271e"
      stroke-width="3.3" stroke-linecap="round"/>
    <ellipse cx="3.2" cy="-2" rx="7.8" ry="8.6" fill="url(#irisG)"
      stroke="#74421e" stroke-width="1.3"/>
    <ellipse cx="4.5" cy="-3.2" rx="3" ry="4.5" fill="#231611"/>
    <circle cx="0.7" cy="-6.1" r="2" fill="#fff8e8"/>
    <circle cx="6" cy="1.3" r="1.1" fill="#f5ce7d" opacity=".9"/>
    <path d="M -9,7 C -3,10 4,9 9,5" fill="none" stroke="#b16848"
      stroke-width="1.4" stroke-linecap="round" opacity=".75"/>
  </g>
</g>"""

    right_eye = f"""
<g transform="translate(36 -17) scale(.95 .77)">
  <g>{blink}
    <path d="M -16,-3 C -6,-14 15,-14 21,-1 C 14,10 -7,13 -16,-3 Z"
      fill="#fff3d2" stroke="#35211b" stroke-width="2.6"/>
    <path d="M -14,-5 C -6,-13 13,-13 19,-3" fill="none" stroke="#45271e"
      stroke-width="3.3" stroke-linecap="round"/>
    <ellipse cx="3.2" cy="-2.5" rx="7.7" ry="8.5" fill="url(#irisG)"
      stroke="#74421e" stroke-width="1.3"/>
    <ellipse cx="4.4" cy="-3.8" rx="3" ry="4.4" fill="#231611"/>
    <circle cx="0.7" cy="-6.7" r="1.9" fill="#fff8e8"/>
    <circle cx="5.7" cy="1" r="1.1" fill="#f5ce7d" opacity=".9"/>
    <path d="M -7,7 C -1,10 6,9 11,5" fill="none" stroke="#b16848"
      stroke-width="1.4" stroke-linecap="round" opacity=".75"/>
  </g>
</g>"""

    head = f"""
<g id="head" transform="translate(758 216)">
  <g transform="translate(0 82)">
    <g transform="rotate(2.2)">
      <animateTransform attributeName="transform" type="rotate"
        values="2.0;3.6;2.8;1.4;2.0" dur="4.8s" repeatCount="indefinite"
        calcMode="spline" keyTimes="0;0.25;0.5;0.75;1"
        keySplines="{";".join([SINE] * 4)}"/>
      <g transform="translate(0 -82)">
        {big_plume}
        {small_plume}
        <!-- mane silhouette: irregular, swept back, never a halo -->
        <path d="M -83,59
          C -104,34 -110,1 -98,-28
          C -111,-49 -107,-77 -89,-98
          C -73,-83 -56,-78 -39,-83
          C -43,-104 -25,-119 -3,-121
          C 8,-107 23,-98 41,-94
          C 46,-108 64,-112 82,-104
          C 82,-90 92,-76 106,-65
          C 117,-57 122,-43 122,-29
          C 108,-33 97,-25 90,-13
          C 103,1 108,17 102,32
          C 92,57 67,76 40,88
          C 8,101 -26,95 -48,79
          C -64,68 -77,68 -83,59 Z"
          fill="url(#hairG)" stroke="#35231d" stroke-width="4.4"/>
        <!-- a few wind-swept locks, deliberately off-centre -->
        <g fill="url(#hairG)" stroke="#35231d" stroke-width="3.2">
          <path d="M -69,-61 C -96,-84 -98,-111 -78,-129
            C -70,-107 -54,-90 -31,-79 Z"/>
          <path d="M -84,-4 C -112,-15 -129,-2 -132,22
            C -113,10 -96,17 -83,35 C -82,18 -75,6 -64,-1 Z"/>
          <path d="M 103,-30 C 123,-38 135,-24 130,-4
            C 116,-15 104,-9 94,4 Z"/>
          <path d="M -87,39 C -107,48 -111,65 -98,78
            C -92,63 -80,58 -67,61 Z"/>
          <path d="M 84,38 C 100,48 101,64 90,76
            C 83,62 73,58 61,60 Z"/>
        </g>
        <g fill="none" stroke="#f1c36d" stroke-width="2.2" stroke-linecap="round" opacity=".5">
          <path d="M -55,-66 C -42,-75 -26,-78 -12,-74"/>
          <path d="M 38,-91 C 54,-96 70,-89 78,-77"/>
          <path d="M -75,10 C -68,0 -57,-6 -46,-3"/>
          <path d="M 62,-57 C 74,-52 82,-42 84,-31"/>
        </g>
        <path d="M 99,-42 C 111,-18 111,14 101,40 C 92,62 74,78 54,86"
          fill="none" stroke="#f5cf86" stroke-width="2.6" stroke-linecap="round"
          opacity=".34"/>
        <!-- ears, set back and partly buried in the mane -->
        <g transform="translate(-94 9) rotate(-14)">
          <ellipse rx="21" ry="27" fill="#d69a44" stroke="#35231d" stroke-width="4"/>
          <ellipse rx="9" ry="15" fill="#d98b67" stroke="#763c2e" stroke-width="2"/>
          <path d="M 0,-12 C 6,-4 6,6 0,13" fill="none" stroke="#b06b44"
            stroke-width="1.7" opacity=".7"/>
        </g>
        <g transform="translate(91 1) rotate(12)">
          <ellipse rx="16.5" ry="22" fill="#cd903b" stroke="#35231d" stroke-width="4"/>
          <ellipse rx="7" ry="12" fill="#dc9069" stroke="#763c2e" stroke-width="1.9"/>
        </g>
        <!-- hoop earring -->
        <g transform="translate(-104 42)">
          <g transform="rotate(-3)">
            <animateTransform attributeName="transform" type="rotate"
              values="-4;3;-1;4;-4" dur="3.4s" repeatCount="indefinite"
              calcMode="spline" keyTimes="0;0.25;0.5;0.75;1"
              keySplines="{";".join([SINE] * 4)}"/>
            <ellipse rx="10.5" ry="14" cy="7" fill="none" stroke="#e4b65b"
              stroke-width="3.4"/>
            <circle cy="21.5" r="4.5" fill="#b83b2c" stroke="#57291f" stroke-width="1.4"/>
            <circle cx="-1.4" cy="20" r="1.1" fill="#f8d894" opacity=".85"/>
          </g>
        </g>
        <!-- the face itself -->
        <path d="M -2,-87 C 31,-92 60,-73 71,-41
          C 81,-8 74,29 52,50 C 29,71 -3,77 -29,65
          C -54,52 -67,22 -63,-10 C -59,-44 -34,-82 -2,-87 Z"
          fill="url(#faceG)" stroke="#39251e" stroke-width="4.2"/>
        <!-- just a little light on the brow, not a pale mask -->
        <path d="M -29,-50 C -12,-59 16,-59 33,-47
          C 44,-37 47,-21 42,-8 C 31,6 4,8 -14,0
          C -31,-8 -38,-39 -29,-50 Z" fill="#f8dfb2" opacity=".24"/>
        <!-- a smaller, warmer muzzle -->
        <path d="M -25,17 C -11,4 11,-1 32,5
          C 49,10 57,23 53,36 C 49,50 32,56 15,52
          C -3,48 -18,38 -24,28 C -27,23 -27,20 -25,17 Z"
          fill="#efc58b" stroke="#bd8758" stroke-width="1.5"/>
        <path d="M -38,24 C -45,36 -39,48 -28,54" fill="none" stroke="#dfa36e"
          stroke-width="1.8" stroke-linecap="round" opacity=".55"/>
        <ellipse cx="-48" cy="25" rx="11" ry="7.5" fill="#e58e64" opacity=".2"/>
        <ellipse cx="52" cy="17" rx="12" ry="7.5" fill="#e58e64" opacity=".18"/>
        <!-- flat monkey nose -->
        <path d="M 5,8 C 10,3 20,2 27,5
          C 35,8 39,13 37,18 C 35,23 29,24 24,22
          C 20,20 18,20 15,22 C 10,23 4,19 3,14 C 3,12 4,10 5,8 Z"
          fill="#a95e42" stroke="#3c251e" stroke-width="2.2"/>
        <ellipse cx="14" cy="13" rx="2.5" ry="1.35" fill="#4e261c" opacity=".85"/>
        <ellipse cx="26" cy="12.5" rx="2.5" ry="1.35" fill="#4e261c" opacity=".85"/>
        <path d="M 1,-13 C 6,-6 9,1 11,8" fill="none" stroke="#d18f61"
          stroke-width="8" stroke-linecap="round" opacity=".35"/>
        <path d="M 0,-2 C 5,2 9,6 11,10" fill="none" stroke="#96583d"
          stroke-width="2.1" stroke-linecap="round" opacity=".75"/>
        <!-- lopsided grin with one sharp fang -->
        <path d="M -8,34 C 6,41 30,41 47,33 C 50,32 52,30 54,27
          C 49,43 33,51 15,47 C 4,45 -6,40 -8,34 Z"
          fill="#481b19" stroke="#331c17" stroke-width="2.3" stroke-linejoin="round"/>
        <path d="M 21,46 C 28,44 35,45 41,48 C 33,53 26,53 21,46 Z" fill="#c66b59"/>
        <path d="M 2,36 L 7,38 L 5,45 L 0,41 Z" fill="#fae4b7" stroke="#7b4b31"
          stroke-width="1"/>
        <path d="M -7,42 C -2,46 3,48 9,49" fill="none" stroke="#97563f"
          stroke-width="1.9" stroke-linecap="round" opacity=".7"/>
        <path d="M 53,34 C 61,32 66,27 69,19" fill="none" stroke="#7d4b33"
          stroke-width="2" stroke-linecap="round" opacity=".7"/>
        <path d="M -16,56 C -10,60 -3,61 2,59" fill="none" stroke="#bf835b"
          stroke-width="1.7" stroke-linecap="round" opacity=".7"/>
        <!-- cheek fur softens the face edge and makes the jaw monkey-wide -->
        <g fill="#c18434" stroke="#35231d" stroke-width="2.3">
          <path d="M -60,16 C -78,18 -90,30 -94,46
            C -79,38 -69,41 -60,51 C -62,39 -58,27 -52,18 Z"/>
          <path d="M 66,16 C 82,20 92,33 93,48
            C 79,39 71,43 62,51 C 64,38 60,26 55,17 Z"/>
          <path d="M -30,64 C -20,74 -7,77 2,72 C -8,69 -15,63 -20,55 Z"/>
          <path d="M -74,42 C -86,50 -88,61 -82,70 C -76,60 -68,57 -59,60 Z"/>
          <path d="M 77,38 C 88,46 89,57 83,66 C 77,56 69,54 61,56 Z"/>
        </g>
        <path d="M -2,68 C 2,78 12,82 20,76 C 13,74 8,69 7,62 Z"
          fill="#d3953f" stroke="#35231d" stroke-width="2.1"/>
        <!-- opera-red eye wings -->
        <path d="M -42,-26 C -52,-34 -57,-46 -55,-57
          C -45,-49 -37,-40 -34,-31 Z" fill="#a6382b" opacity=".84"/>
        <path d="M 49,-30 C 59,-38 64,-50 61,-60
          C 51,-52 44,-43 41,-34 Z" fill="#a6382b" opacity=".8"/>
        <path d="M -49,-17 C -58,-23 -64,-32 -66,-42" fill="none" stroke="#c2543b"
          stroke-width="3.3" stroke-linecap="round"/>
        <path d="M 55,-22 C 64,-28 70,-37 72,-47" fill="none" stroke="#c2543b"
          stroke-width="3.3" stroke-linecap="round"/>
        <!-- heavy, angled brows: focused, not surprised -->
        <g transform="translate(0 2.5)">
        <path d="M -47,-37 C -35,-44 -18,-42 -8,-32
          C -20,-36 -34,-35 -45,-29 Z" fill="#4e2b1d" stroke="#4e2b1d"
          stroke-width="1.8" stroke-linejoin="round"/>
        <path d="M 15,-36 C 30,-45 49,-42 62,-30
          C 48,-35 32,-34 20,-28 Z" fill="#4e2b1d" stroke="#4e2b1d"
          stroke-width="1.8" stroke-linejoin="round"/>
        <path d="M -43,-38 C -32,-42 -22,-41 -14,-36" fill="none" stroke="#b67530"
          stroke-width="1.5" stroke-linecap="round" opacity=".65"/>
        <path d="M 20,-38 C 32,-42 44,-40 54,-34" fill="none" stroke="#b67530"
          stroke-width="1.4" stroke-linecap="round" opacity=".6"/>
        </g>
        {left_eye}
        {right_eye}
        <!-- fringe locks under the circlet -->
        <g fill="#a36128" stroke="#35231d" stroke-width="2.3">
          <path d="M -42,-69 C -34,-90 -10,-101 10,-92
            C -3,-84 -9,-72 -10,-57 L -27,-61 Z"/>
          <path d="M 23,-86 C 38,-98 57,-94 66,-80
            C 51,-79 43,-68 39,-54 L 25,-61 Z"/>
        </g>
        <!-- golden circlet -->
        <g id="circlet">
          <path d="M -64,-36 C -42,-57 -7,-66 28,-62
            C 50,-60 67,-51 78,-40"
            fill="none" stroke="#563a1c" stroke-width="10.6" stroke-linecap="round"/>
          <path d="M -64,-36 C -42,-57 -7,-66 28,-62
            C 50,-60 67,-51 78,-40"
            fill="none" stroke="url(#goldG)" stroke-width="7.4" stroke-linecap="round"/>
          <path d="M -63,-38 C -43,-58 -8,-68 28,-64" fill="none"
            stroke="#ffe6a6" stroke-width="1.7" stroke-linecap="round" opacity=".82"/>
          <!-- small earpiece curls rather than ram horns -->
          <path d="M -66,-36 C -75,-38 -81,-46 -77,-53
            C -73,-58 -66,-54 -67,-47"
            fill="none" stroke="#563a1c" stroke-width="6.4" stroke-linecap="round"/>
          <path d="M -66,-36 C -75,-38 -81,-46 -77,-53
            C -73,-58 -66,-54 -67,-47"
            fill="none" stroke="#e6b45a" stroke-width="3.8" stroke-linecap="round"/>
          <path d="M 80,-40 C 90,-43 95,-52 90,-59
            C 85,-64 78,-59 80,-52"
            fill="none" stroke="#563a1c" stroke-width="6.4" stroke-linecap="round"/>
          <path d="M 80,-40 C 90,-43 95,-52 90,-59
            C 85,-64 78,-59 80,-52"
            fill="none" stroke="#e6b45a" stroke-width="3.8" stroke-linecap="round"/>
          <!-- a compact cloud setting with a ruby -->
          <path d="M -8,-59 C -3,-68 12,-69 18,-59
            C 11,-51 -1,-51 -8,-59 Z"
            fill="url(#goldG)" stroke="#563a1c" stroke-width="2"/>
          <path d="M 5,-67 L 12,-59 L 5,-51 L -2,-59 Z"
            fill="#b7352c" stroke="#56241e" stroke-width="1.8"/>
          <path d="M -6,-59 C -1,-63 4,-63 9,-59" fill="none" stroke="#f9db8e"
            stroke-width="1.7" stroke-linecap="round" opacity=".8"/>
          <circle cx="38" cy="-62" r="2.1" fill="#f1cb77"/>
          <circle cx="57" cy="-55" r="1.6" fill="#f1cb77"/>
          <g transform="translate(20 -74)">
            <path d="M 0,-8 C 2,-2 2,-2 8,0 C 2,2 2,2 0,8
              C -2,2 -2,2 -8,0 C -2,-2 -2,-2 0,-8 Z"
              fill="#fff4cf" opacity=".55">{glare}</path>
          </g>
        </g>
        <!-- little clasp where the plumes leave the mane -->
        <g transform="translate(-50 -56) rotate(-22)">
          <ellipse rx="8" ry="5" fill="#d8a74d" stroke="#49331e" stroke-width="1.8"/>
          <ellipse rx="4" ry="2.5" fill="#7b3a27"/>
          <circle cx="0" cy="-7" r="2.4" fill="#b83b2c" stroke="#56291f" stroke-width="1"/>
        </g>
      </g>
    </g>
  </g>
</g>"""
    return head

def neck_and_upper_groups(base_phase):
    bob = anim_translate("0 0;0 -1.7;0 0", 1.6,
                         "0;0.5;1", f"{SINE};{SINE}")
    head = head_group()
    cape = tail_and_cape()
    pelt = pelt_and_sash()
    torso = torso_and_arms()
    return f"""
<g id="upper-bob">
  {bob}
  {staff()}
  {cape}
  {torso}
  {pelt}
  <g id="neck">
    <path d="M 701,300 C 708,278 724,265 741,268
      C 752,279 751,298 739,313 L 713,313 Z"
      fill="url(#furG)" stroke="#3a281f" stroke-width="3.8"/>
    <path d="M 714,290 C 721,281 733,279 742,283" fill="none" stroke="#f1c973"
      stroke-width="2.2" stroke-linecap="round" opacity=".45"/>
    <path d="M 704,305 C 718,311 734,309 746,300" fill="none" stroke="#b73a2d"
      stroke-width="4.5" stroke-linecap="round" opacity=".85"/>
  </g>
  <g transform="translate(758 296) scale(.94) translate(-758 -296)">
    {head}
  </g>
</g>"""


# --------------------------------------------------------------------------
# Foreground details, petals, grain and close
# --------------------------------------------------------------------------


def foreground_puffs():
    """Cloud crests and spray layered in front of the bicycle."""
    return f"""
<g id="cloud-contact">
  <g transform="translate(432 722)">
    <path d="M -111,7 C -116,-12 -98,-30 -72,-26
      C -63,-50 -31,-57 -8,-41 C 16,-61 51,-50 50,-26
      C 75,-29 96,-10 86,9 C 76,28 50,33 29,20
      C 12,36 -23,34 -39,17 C -66,28 -102,22 -111,7 Z"
      fill="url(#cloudSoft)" stroke="#cfa477" stroke-width="2.1"/>
    <path d="M -86,8 C -96,0 -90,-14 -76,-13 C -65,-12 -59,0 -65,8
      C -71,17 -84,16 -86,8 Z" fill="#e4c39b" opacity=".55"/>
    <path d="M -46,-14 C -53,-29 -40,-43 -25,-42 C -12,-41 -4,-28 -9,-18
      C -14,-8 -29,-6 -36,-13 Z" fill="#e2bf96" opacity=".45"/>
    <path d="M 22,-33 C 27,-48 47,-55 61,-45 C 73,-37 70,-22 58,-17
      C 46,-11 31,-19 22,-33 Z" fill="#e8cba2" opacity=".5"/>
    <path d="M -92,16 C -98,6 -91,-4 -81,-3 C -72,-2 -68,9 -74,16
      C -79,23 -89,23 -92,16 Z" fill="none" stroke="#bb8c59" stroke-width="2.1"
      stroke-linecap="round" opacity=".5"/>
    <path d="M 68,4 C 77,-5 89,0 89,10 C 89,20 77,24 70,18"
      fill="none" stroke="#bb8c59" stroke-width="2.1" stroke-linecap="round" opacity=".5"/>
  </g>
  <g transform="translate(920 721)">
    <path d="M -97,9 C -103,-8 -86,-26 -62,-22
      C -53,-46 -22,-53 2,-36 C 22,-55 56,-45 54,-20
      C 77,-24 98,-4 86,14 C 75,32 49,35 28,23
      C 11,38 -24,34 -40,18 C -65,28 -91,22 -97,9 Z"
      fill="url(#cloudSoft)" stroke="#cfa477" stroke-width="2.1"/>
    <path d="M -78,7 C -86,-2 -81,-13 -70,-12 C -61,-11 -56,-1 -62,6
      C -67,13 -77,13 -78,7 Z" fill="#e5c59d" opacity=".5"/>
    <path d="M 14,-31 C 18,-47 39,-52 51,-41 C 62,-32 57,-18 45,-15
      C 33,-11 20,-19 14,-31 Z" fill="#e6c9a1" opacity=".45"/>
    <path d="M -80,19 C -86,10 -80,1 -71,2 C -63,3 -59,13 -64,19"
      fill="none" stroke="#bb8c59" stroke-width="2" stroke-linecap="round" opacity=".5"/>
    <path d="M 65,10 C 75,0 88,5 89,16 C 90,26 78,29 71,23"
      fill="none" stroke="#bb8c59" stroke-width="2" stroke-linecap="round" opacity=".5"/>
  </g>
  <path d="M 512,747 C 520,733 542,728 558,736 C 574,727 596,733 601,747
    C 617,750 620,760 607,765 C 589,772 567,766 558,758
    C 544,767 523,760 518,752 C 508,750 508,749 512,747 Z"
    fill="url(#cloudSoft)" opacity=".88"/>
  <path d="M 1014,746 C 1021,733 1042,728 1057,737 C 1071,728 1093,733 1098,747
    C 1111,750 1114,760 1103,765 C 1086,772 1067,766 1058,759
    C 1045,768 1024,762 1020,754 C 1011,752 1010,749 1014,746 Z"
    fill="url(#cloudSoft)" opacity=".8"/>
</g>
<g id="cloud-spray" fill="none" stroke-linecap="round">
  <path d="M 345,706 C 310,691 281,694 255,710" stroke="#fff2da" stroke-width="11"
    opacity=".88">
    <animate attributeName="d"
      values="M 345,706 C 310,691 281,694 255,710;
      M 347,707 C 312,704 281,698 250,690;
      M 345,706 C 310,691 281,694 255,710"
      dur="3.2s" repeatCount="indefinite" calcMode="spline"
      keyTimes="0;0.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
  </path>
  <path d="M 330,724 C 300,728 273,719 253,704" stroke="#f5e1c0" stroke-width="5.4"
    opacity=".7">
    <animate attributeName="d"
      values="M 330,724 C 300,728 273,719 253,704;
      M 332,722 C 300,718 274,726 250,739;
      M 330,724 C 300,728 273,719 253,704"
      dur="4.1s" repeatCount="indefinite" calcMode="spline"
      keyTimes="0;0.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
  </path>
  <path d="M 1018,709 C 1047,694 1076,697 1099,711" stroke="#fff2da" stroke-width="9"
    opacity=".82">
    <animate attributeName="d"
      values="M 1018,709 C 1047,694 1076,697 1099,711;
      M 1016,712 C 1047,705 1076,700 1106,691;
      M 1018,709 C 1047,694 1076,697 1099,711"
      dur="3.8s" repeatCount="indefinite" calcMode="spline"
      keyTimes="0;0.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
  </path>
  <path d="M 390,731 C 376,719 359,717 342,723" stroke="#f9e8ca" stroke-width="4"
    opacity=".6"/>
  <path d="M 948,733 C 965,720 986,718 1004,726" stroke="#f9e8ca" stroke-width="4.2"
    opacity=".6"/>
  <g fill="#fff6e5" opacity=".8">
    <circle cx="257" cy="696" r="2.6"/>
    <circle cx="239" cy="711" r="1.8"/>
    <circle cx="1109" cy="705" r="2.2"/>
  </g>
</g>
<g id="foreground-cloud" fill="url(#cloudFront)">
  <path d="M -50,773 C 14,754 68,752 116,767 C 169,783 211,777 254,762
    C 302,746 346,753 392,770 C 437,787 481,778 526,762
    C 576,744 621,751 667,770 C 714,789 760,784 806,766
    C 852,748 897,752 945,770 C 993,788 1043,778 1093,761
    C 1140,745 1194,750 1250,768 L 1250,860 L -50,860 Z"/>
  <path d="M -50,773 C 14,754 68,752 116,767 C 169,783 211,777 254,762
    C 302,746 346,753 392,770 C 437,787 481,778 526,762
    C 576,744 621,751 667,770 C 714,789 760,784 806,766
    C 852,748 897,752 945,770 C 993,788 1043,778 1093,761
    C 1140,745 1194,750 1250,768" fill="none" stroke="#be9365"
    stroke-width="2.3" stroke-linecap="round" opacity=".45"/>
  <path d="M -50,786 C 40,768 104,775 165,792 C 226,810 278,794 339,784
    C 402,774 443,792 507,802 C 573,812 621,790 687,780
    C 757,770 799,789 864,802 C 931,815 977,792 1044,781
    C 1109,770 1168,777 1250,796" fill="none" stroke="#e6c498"
    stroke-width="8" stroke-linecap="round" opacity=".35"/>
  <g fill="none" stroke="#b88c56" stroke-width="3" stroke-linecap="round" opacity=".42">
    <path d="M 138,790 C 122,777 129,758 147,760 C 164,762 169,783 152,790
      C 142,795 134,786 138,777"/>
    <path d="M 701,793 C 686,780 692,763 709,765 C 725,767 729,785 714,792
      C 704,797 697,789 701,781"/>
    <path d="M 1085,793 C 1070,781 1076,764 1092,766 C 1108,768 1112,785 1098,792"/>
  </g>
</g>
<g id="foreground-scrolls" fill="none" stroke-linecap="round">
  <g stroke="#b78a55" stroke-width="4" opacity=".33">
    <path d="M 188,758 C 158,744 165,712 195,714 C 220,716 227,743 207,752
      C 195,758 184,748 191,738"/>
    <path d="M 1101,761 C 1072,748 1078,718 1107,719 C 1131,720 1138,746 1119,755
      C 1108,761 1097,752 1104,742"/>
  </g>
  <g stroke="#f6e3c2" stroke-width="7" opacity=".5">
    <path d="M 158,742 C 174,726 197,731 199,750 C 201,763 186,770 176,762"/>
    <path d="M 1134,743 C 1147,726 1169,729 1172,748 C 1174,760 1161,767 1152,759"/>
  </g>
</g>
<g id="gold-motes" fill="#eac078">
  <circle cx="327" cy="660" r="2.2" opacity=".55">
    <animate attributeName="opacity" values=".15;.7;.15" dur="3.1s"
      repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
  </circle>
  <circle cx="1024" cy="655" r="1.6" opacity=".4">
    <animate attributeName="opacity" values=".1;.55;.1" dur="4.2s"
      repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;1" keySplines="0.42 0 0.58 1;0.42 0 0.58 1"/>
  </circle>
  <circle cx="766" cy="164" r="1.8" opacity=".6">
    <animate attributeName="opacity" values=".1;.8;.2;.6;.1" dur="3.6s"
      repeatCount="indefinite" calcMode="spline" keyTimes="0;.3;.5;.75;1"
      keySplines="0.33 0 0.33 1;0.33 0 0.33 1;0.33 0 0.33 1;0.33 0 0.33 1"/>
  </circle>
</g>
""".strip()
def petals():
    specs = [
        (1108, 156, 1.00, 11.5, -2.0, 42, "#efb6a1", "-2"),
        (1008, 442, .72, 14.0, 3.0, -64, "#e9a48e", "-7"),
        (1088, 318, .58, 12.4, -6.0, 28, "#f4c2ad", "-4"),
        (560, 170, .66, 10.8, 4.0, -36, "#e9a68d", "-9"),
        (1152, 545, .86, 13.0, -3.0, 72, "#efb49c", "-6"),
        (330, 590, .55, 15.0, 2.0, -54, "#f0b9a1", "-11"),
        (378, 362, .48, 12.0, 1.0, 34, "#f1bda7", "-3"),
    ]
    out = []
    for x, y, s, dur, rot, dx, col, begin in specs:
        out.append(f"""
<g transform="translate({x} {y}) rotate({rot}) scale({s})">
  <g>
    <animateTransform attributeName="transform" type="translate"
      values="0 0;{dx} 64;{dx*1.55} 118" dur="{dur}s" begin="{begin}s"
      repeatCount="indefinite" calcMode="linear"/>
    <g>
      <animateTransform attributeName="transform" type="rotate"
        values="0;{18 if dx > 0 else -22};{46 if dx > 0 else -50}"
        dur="{dur}s" begin="{begin}s" repeatCount="indefinite" calcMode="linear"/>
      <path d="M 0,-13 C 8,-6 8,6 0,13 C -8,6 -8,-6 0,-13 Z"
        fill="{col}" stroke="#b66f58" stroke-width="1" opacity=".82"/>
      <path d="M 0,-9 C 2,-3 2,3 0,7" fill="none" stroke="#f9ddc9"
        stroke-width="1" opacity=".55"/>
    </g>
    <animate attributeName="opacity" values="0;.9;.9;0" dur="{dur}s" begin="{begin}s"
      repeatCount="indefinite" calcMode="linear" keyTimes="0;.12;.82;1"/>
  </g>
</g>""")
    return "".join(out)


def defs():
    return """
<defs>
  <linearGradient id="paper" x1="0" y1="0" x2="0.92" y2="1">
    <stop offset="0" stop-color="#faf1dd"/>
    <stop offset=".4" stop-color="#f7e7cb"/>
    <stop offset=".75" stop-color="#f1d5b1"/>
    <stop offset="1" stop-color="#e9c69f"/>
  </linearGradient>
  <radialGradient id="sunHalo" cx=".5" cy=".5" r=".5">
    <stop offset="0" stop-color="#f3c17e" stop-opacity=".85"/>
    <stop offset=".52" stop-color="#efb46e" stop-opacity=".25"/>
    <stop offset="1" stop-color="#efb46e" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="sunG" x1="0.18" y1="0.05" x2="0.8" y2="0.95">
    <stop offset="0" stop-color="#ea7049"/>
    <stop offset=".55" stop-color="#dd5438"/>
    <stop offset="1" stop-color="#c33d2e"/>
  </linearGradient>
  <linearGradient id="mtFar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#c49a84" stop-opacity=".72"/>
    <stop offset=".7" stop-color="#a78072" stop-opacity=".28"/>
    <stop offset="1" stop-color="#9c7b70" stop-opacity=".08"/>
  </linearGradient>
  <linearGradient id="mtMid" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#7b9182" stop-opacity=".82"/>
    <stop offset=".62" stop-color="#58736a" stop-opacity=".64"/>
    <stop offset="1" stop-color="#47615c" stop-opacity=".34"/>
  </linearGradient>
  <linearGradient id="mtNear" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#345451"/>
    <stop offset=".64" stop-color="#274541"/>
    <stop offset="1" stop-color="#1f3634"/>
  </linearGradient>
  <linearGradient id="cloudSoft" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fff8e8"/>
    <stop offset=".72" stop-color="#f7e7ca"/>
    <stop offset="1" stop-color="#e5c49c"/>
  </linearGradient>
  <linearGradient id="cloudBank" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fdf5e3"/>
    <stop offset=".5" stop-color="#f5e1c1"/>
    <stop offset="1" stop-color="#e3c49b"/>
  </linearGradient>
  <linearGradient id="cloudBankFar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ead0aa"/>
    <stop offset="1" stop-color="#d2b187"/>
  </linearGradient>
  <linearGradient id="cloudBankNear" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#faecd2"/>
    <stop offset="1" stop-color="#e4c195"/>
  </linearGradient>
  <linearGradient id="cloudFront" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#f7e8ce"/>
    <stop offset=".55" stop-color="#e8c99f"/>
    <stop offset="1" stop-color="#d2aa7c"/>
  </linearGradient>
  <linearGradient id="fenderG" x1="0" y1="0" x2="0.25" y2="1">
    <stop offset="0" stop-color="#35756a"/>
    <stop offset=".55" stop-color="#20564f"/>
    <stop offset="1" stop-color="#153e3a"/>
  </linearGradient>
  <linearGradient id="frameG" x1="0" y1="0" x2="0.35" y2="1">
    <stop offset="0" stop-color="#3d8374"/>
    <stop offset=".5" stop-color="#266257"/>
    <stop offset="1" stop-color="#143f3a"/>
  </linearGradient>
  <linearGradient id="staffG" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#f5dc9d"/>
    <stop offset=".32" stop-color="#d5a854"/>
    <stop offset=".7" stop-color="#b88639"/>
    <stop offset="1" stop-color="#e7c270"/>
  </linearGradient>
  <linearGradient id="capeG" x1="0" y1="0" x2="0.7" y2="1">
    <stop offset="0" stop-color="#d54b35"/>
    <stop offset=".55" stop-color="#b73328"/>
    <stop offset="1" stop-color="#8b241f"/>
  </linearGradient>
  <linearGradient id="tailG" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#f0bd61"/>
    <stop offset=".6" stop-color="#cf8b35"/>
    <stop offset="1" stop-color="#a9672a"/>
  </linearGradient>
  <linearGradient id="tunicG" x1="0.1" y1="0" x2="0.8" y2="1">
    <stop offset="0" stop-color="#cb4732"/>
    <stop offset=".55" stop-color="#ab3026"/>
    <stop offset="1" stop-color="#81231e"/>
  </linearGradient>
  <linearGradient id="peltG" x1="0" y1="0" x2="0.2" y2="1">
    <stop offset="0" stop-color="#f0b456"/>
    <stop offset=".65" stop-color="#dd9637"/>
    <stop offset="1" stop-color="#bc7528"/>
  </linearGradient>
  <linearGradient id="sashG" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#edc875"/>
    <stop offset=".55" stop-color="#d6a34b"/>
    <stop offset="1" stop-color="#b47e31"/>
  </linearGradient>
  <linearGradient id="furG" x1="0" y1="0" x2="0.5" y2="1">
    <stop offset="0" stop-color="#f0c365"/>
    <stop offset=".55" stop-color="#d99c42"/>
    <stop offset="1" stop-color="#b8782d"/>
  </linearGradient>
  <linearGradient id="furFarG" x1="0" y1="0" x2="0.5" y2="1">
    <stop offset="0" stop-color="#d6a24e"/>
    <stop offset="1" stop-color="#a36d2d"/>
  </linearGradient>
  <linearGradient id="legG" x1="0" y1="0" x2="0.6" y2="1">
    <stop offset="0" stop-color="#e7ad4f"/>
    <stop offset=".55" stop-color="#cf8d32"/>
    <stop offset="1" stop-color="#ac6c27"/>
  </linearGradient>
  <linearGradient id="legFarG" x1="0" y1="0" x2="0.6" y2="1">
    <stop offset="0" stop-color="#c9913c"/>
    <stop offset="1" stop-color="#96602b"/>
  </linearGradient>
  <linearGradient id="hairG" x1="0.1" y1="0" x2="0.8" y2="1">
    <stop offset="0" stop-color="#dda24a"/>
    <stop offset=".5" stop-color="#b8772f"/>
    <stop offset="1" stop-color="#88521f"/>
  </linearGradient>
  <linearGradient id="faceG" x1="0.1" y1="0" x2="0.8" y2="1">
    <stop offset="0" stop-color="#f3c489"/>
    <stop offset=".55" stop-color="#e9ac6c"/>
    <stop offset="1" stop-color="#ce8450"/>
  </linearGradient>
  <linearGradient id="goldG" x1="0" y1="0" x2="0.4" y2="1">
    <stop offset="0" stop-color="#f9e3a2"/>
    <stop offset=".32" stop-color="#e9bd61"/>
    <stop offset=".72" stop-color="#c28c36"/>
    <stop offset="1" stop-color="#a87428"/>
  </linearGradient>
  <linearGradient id="plumeG" x1="0" y1="0" x2="1" y2=".4">
    <stop offset="0" stop-color="#d9563c"/>
    <stop offset=".55" stop-color="#b9382b"/>
    <stop offset="1" stop-color="#8f231f"/>
  </linearGradient>
  <radialGradient id="irisG" cx=".4" cy=".35" r=".72">
    <stop offset="0" stop-color="#f8d77f"/>
    <stop offset=".5" stop-color="#dda23e"/>
    <stop offset="1" stop-color="#a66a26"/>
  </radialGradient>
  <linearGradient id="bootG" x1="0" y1="0" x2="0.5" y2="1">
    <stop offset="0" stop-color="#5c3a2b"/>
    <stop offset=".6" stop-color="#422a23"/>
    <stop offset="1" stop-color="#2e1f1c"/>
  </linearGradient>
  <linearGradient id="bootGFar" x1="0" y1="0" x2="0.5" y2="1">
    <stop offset="0" stop-color="#463027"/>
    <stop offset="1" stop-color="#241b19"/>
  </linearGradient>
  <filter id="blurSoft" x="-30%" y="-100%" width="160%" height="300%">
    <feGaussianBlur stdDeviation="5"/>
  </filter>
  <filter id="grain" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency=".82" numOctaves="2" seed="7" result="n"/>
    <feColorMatrix in="n" type="saturate" values="0"/>
  </filter>
  <radialGradient id="vignette" cx=".5" cy=".45" r=".72">
    <stop offset=".55" stop-color="#6d472d" stop-opacity="0"/>
    <stop offset="1" stop-color="#6d472d" stop-opacity=".15"/>
  </radialGradient>
</defs>""".strip()


def build_svg(base_phase=0.0):
    far_leg, far_boot, near_leg, near_boot = legs(base_phase)
    sections = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-labelledby="ttl desc">',
        '<title id="ttl">孙悟空骑自行车 · 云海骑行</title>',
        '<desc id="desc">齐天大圣孙悟空骑着一辆青绿色自行车穿过暖金色的云海。'
        '车轮匀速转动，双腿随脚踏屈伸，红披风、虎皮裙、猴尾与雉鸡翎随风轻摆，'
        '桃花瓣在身侧飘落，云气从轮下涌起。</desc>',
        defs(),
        sun_and_sky(),
        mountains(),
        high_clouds(),
        title_and_border(),
        cloud_road_front(),
        f"""
<g id="rider-and-bike">
  {bike(base_phase)}
  {far_leg}
  {far_boot}
  {near_leg}
  {near_boot}
  {neck_and_upper_groups(base_phase)}
</g>""",
        foreground_puffs(),
        petals(),
        '<rect x="0" y="0" width="1200" height="800" filter="url(#grain)" opacity=".035"/>',
        '<rect x="0" y="0" width="1200" height="800" fill="url(#vignette)"/>',
        '<rect x="22" y="22" width="1156" height="756" fill="none" stroke="#806044" stroke-width="1.5" opacity=".38"/>',
        '<rect x="28" y="28" width="1144" height="744" fill="none" stroke="#806044" stroke-width=".7" opacity=".24"/>',
    ]
    # gentle reduced-motion handling.  Base state is already a complete still.
    sections.append("""
<script><![CDATA[
(function () {
  var m = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  function apply() {
    if (!document.documentElement.pauseAnimations) return;
    if (m && m.matches) document.documentElement.pauseAnimations();
    else document.documentElement.unpauseAnimations();
  }
  apply();
  if (m && m.addEventListener) m.addEventListener('change', apply);
})();
]]></script>""")
    sections.append("</svg>")
    return "\n".join(sections)


def strip_animations(svg: str) -> str:
    # For raster stills: the static base state already contains the first pose.
    svg = re.sub(r"<animateTransform\b[^>]*/>\s*", "", svg)
    svg = re.sub(r"<animate\b[^>]*/>\s*", "", svg)
    svg = re.sub(r"<script>.*?</script>\s*", "", svg, flags=re.S)
    return svg


def main():
    out = Path(__file__).with_name("sun-wukong-bicycle.svg")
    svg = build_svg(START_PHASE)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out.name}: {len(svg.encode('utf-8')):,} bytes")
    # report the rig's health
    for name, hip, side in (("near", HIP_N, 1), ("far", HIP_F, -1)):
        worst = 0.0
        for i in range(KEYS * 4):
            deg = 360.0 * i / (KEYS * 4)
            k, a, _ = leg_pose(hip, deg, side)
            l1 = math.dist(hip, k)
            l2 = math.dist(k, a)
            worst = max(worst, abs(l1 - L1), abs(l2 - L2))
        print(f"  {name} leg bone drift: {worst:.6f} px")
    if len(sys.argv) > 1 and sys.argv[1] == "--still":
        still = Path(__file__).with_name("_wukong_tmp") / "still.svg"
        still.parent.mkdir(exist_ok=True)
        still.write_text(strip_animations(svg), encoding="utf-8")
        print(f"wrote {still}")


if __name__ == "__main__":
    main()

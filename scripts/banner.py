"""Generate assets/banner.svg: the name as bricks, a self-playing breakout loop."""
import random

FONT = {
    "P": ["11110", "10001", "11110", "10000", "10000"],
    "R": ["11110", "10001", "11110", "10010", "10001"],
    "A": ["01110", "10001", "11111", "10001", "10001"],
    "S": ["01111", "10000", "01110", "00001", "11110"],
    "U": ["10001", "10001", "10001", "10001", "01110"],
    "N": ["10001", "11001", "10101", "10011", "10001"],
    "K": ["10001", "10010", "11100", "10010", "10001"],
    "M": ["10001", "11011", "10101", "10001", "10001"],
}
INVADER = ["00100000100", "00010001000", "00111111100", "01101110110",
           "11111111111", "10111111101", "10100000101", "00011011000"]
W, H, PAD_Y, PAD_W = 64, 22, 20, 7
FRAMES, HOLD, FPS = 150, 14, 14


def word(cells, text, x, y):
    for ch in text:
        cells |= {(x + c, y + r) for r, row in enumerate(FONT[ch]) for c, b in enumerate(row) if b == "1"}
        x += 6
    return x


def bricks():
    cells = set()
    word(cells, "PRASUN", 4, 3)
    end = word(cells, "KUMAR", 4, 11)
    cells |= {(46 + c, 6 + r) for r, row in enumerate(INVADER) for c, b in enumerate(row) if b == "1"}
    return cells, end


def simulate(cells):
    rng = random.Random(7)
    alive = set(cells)
    x, y, vx, vy, pad = 20, 18, 1, -1, 20
    frames, hits = [], {}
    for f in range(FRAMES):
        frames.append((x, y, pad))
        nx, ny = x + vx, y + vy
        if not 0 <= nx < W:
            vx = -vx
            nx = x + vx
        if ny < 0:
            vy = 1
            ny = y + vy
        if (nx, ny) in alive:
            alive.discard((nx, ny))
            hits[(nx, ny)] = f + 1
            vy = -vy
            ny = y + vy
        if ny >= PAD_Y:
            h = rng.randint(-3, 3)
            pad = max(3, min(W - 4, nx - h))
            vx = -1 if h < 0 else 1 if h > 0 else vx
            vy, ny = -1, PAD_Y - 1
        else:
            pad = max(3, min(W - 4, pad + max(-2, min(2, nx - pad))))
        x, y = nx, ny
    return frames, hits


def main():
    cells, cursor_x = bricks()
    frames, hits = simulate(cells)
    total = FRAMES + HOLD
    dur = f"{total / FPS:.2f}s"
    pct = lambda f: f"{f / total * 100:.3f}%"
    restore = pct(FRAMES + HOLD // 2)

    css = ["@keyframes ball{" + "".join(
        f"{pct(f)}{{transform:translate({x}px,{y}px);opacity:1}}" for f, (x, y, _) in enumerate(frames))
        + f"{pct(FRAMES)}{{opacity:0}}}}",
        "@keyframes pad{" + "".join(
        f"{pct(f)}{{transform:translateX({p}px);opacity:1}}" for f, (_, _, p) in enumerate(frames))
        + f"{pct(FRAMES)}{{opacity:0}}}}"]
    rects = []
    for i, (x, y) in enumerate(sorted(cells)):
        style = ""
        if (x, y) in hits:
            css.append(f"@keyframes b{i}{{0%{{opacity:1}}{pct(hits[(x, y)])}{{opacity:0}}{restore}{{opacity:1}}}}")
            style = f' style="animation:b{i} {dur} step-end infinite"'
        rects.append(f'<rect class="p" x="{x + .07}" y="{y + .07}" width=".86" height=".86" rx=".12"{style}/>')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Prasun Kumar">
<style>
:root{{--bg:#f6f8fa;--on:#1f2328;--dim:#d0d7de}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0d1117;--on:#7ee787;--dim:#161b22}}}}
.bg{{fill:var(--bg)}}.g{{fill:var(--dim)}}.p,.c,.k{{fill:var(--on)}}
.c{{animation:blink 1.1s steps(1) infinite}}
.k{{opacity:0;animation-duration:{dur};animation-timing-function:step-end;animation-iteration-count:infinite}}
.ball{{animation-name:ball}}.pad{{animation-name:pad}}
@keyframes blink{{50%{{opacity:0}}}}
{chr(10).join(css)}
@media(prefers-reduced-motion:reduce){{.p,.c,.k{{animation:none!important}}.k{{display:none}}}}
</style>
<defs><pattern id="d" width="1" height="1" patternUnits="userSpaceOnUse"><rect class="g" x=".42" y=".42" width=".16" height=".16"/></pattern></defs>
<rect class="bg" width="{W}" height="{H}" rx="1"/>
<rect fill="url(#d)" width="{W}" height="{H}"/>
{"".join(rects)}
<rect class="c" x="{cursor_x + .07}" y="11.07" width=".86" height="4.86" rx=".12"/>
<rect class="k pad" x="-3" y="{PAD_Y}.07" width="{PAD_W}" height=".86" rx=".12"/>
<rect class="k ball" x=".07" y=".07" width=".86" height=".86" rx=".43"/>
</svg>'''
    open("assets/banner.svg", "w").write(svg)
    print(f"{len(svg) // 1024} KB, {len(hits)} bricks hit, {dur} loop")


if __name__ == "__main__":
    main()

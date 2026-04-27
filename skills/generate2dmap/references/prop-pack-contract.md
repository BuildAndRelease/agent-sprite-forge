# Prop Pack Contract

Prop packs batch multiple small static map props into one generated sheet, then extract each cell into a transparent prop PNG.

Use prop packs to reduce repeated image-generation calls and prompt overhead. They trade per-prop control for speed, so use them only when the props can share one style, scale, perspective, and quality bar.

## When To Use

Good candidates:

- rocks, shrubs, flowers, mushrooms, logs
- crates, barrels, sacks, pots
- small signs, lamps, lanterns, fences, posts
- floor ornaments, small statues, ruins, debris
- repeated environmental dressing for one biome

Avoid prop packs for:

- buildings, gates, trees with wide canopies, bridges
- hero objects, key story artifacts, readable statues
- animated props or props with multiple states
- props requiring exact silhouette, scale, or identity
- props that are too wide/tall for equal cells

## Sheet Size Selection

- `2x2`: 4 props, safest batch size.
- `3x3`: 9 props, best default for small/medium environmental sets.
- `4x4`: 16 props, only for very simple small props with strong margins.

Use `3x3` by default when the user asks for a set of map props and does not specify count.

## Prompt Pattern

```text
Create exactly one <ROWS>x<COLS> pixel-art prop sheet for a top-down 2D RPG map.
Each cell contains one separate static environmental prop from this list, in row-major order:
1. <prop>
2. <prop>
...
All props share the same biome, palette, camera angle, and pixel scale.
3/4 view from slightly above, full object visible, centered in its own cell, crisp dark pixel outlines.
Each prop must fit fully inside its cell with generous magenta margin on all sides.
No prop, branch, roof, sign, smoke, sparkle, shadow, or fragment may touch or cross a cell edge.
Background must be 100% solid flat #FF00FF magenta in every cell, no gradients, no texture, no shadows, no floor plane.
No text, labels, UI, watermark, numbers, arrows, borders, or grid lines.
```

If a cell should stay empty, explicitly say `empty magenta cell`.

## Extraction

Use `scripts/extract_prop_pack.py`:

```bash
python skills/generate2dmap/scripts/extract_prop_pack.py \
  --input assets/props/raw/forest-props-sheet.png \
  --rows 3 \
  --cols 3 \
  --labels mossy-rock,shrub,fallen-log,small-lantern,wooden-sign,flower-patch,stump,crate,grass-tuft \
  --output-dir assets/props \
  --manifest assets/props/forest-prop-pack.json \
  --component-mode largest \
  --component-padding 8 \
  --min-component-area 200 \
  --reject-edge-touch
```

Output shape:

```text
assets/props/<label>/prop.png
assets/props/forest-prop-pack.json
```

The manifest contains source cell coordinates, crop boxes, alpha bounds, extracted image size, component counts, and `edge_touch` flags.

## Placement

After extraction, create placement JSON:

```json
{
  "props": [
    {
      "id": "mossy-rock-1",
      "image": "assets/props/mossy-rock/prop.png",
      "x": 420,
      "y": 512,
      "w": 96,
      "h": 72,
      "sortY": 512,
      "layer": "props"
    }
  ]
}
```

Then compose a QA preview with `scripts/compose_layered_preview.py`.

## QC Rules

Reject or regenerate the pack when:

- any accepted prop has `edge_touch: true`
- labels do not match the requested cells
- a prop has text, UI, shadows, or floor baked in
- prop identity drifts into character/NPC-like art
- a prop is too large for the intended placement scale

For noisy particles or edge debris, reprocess with `--component-mode largest`. For intentional multi-part props, use `--component-mode all` and increase the prompt margin.

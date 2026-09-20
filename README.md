# Normal Map Lab

Turn a sprite into a normal map — from luminance, from alpha, or bevelled from the silhouette — and light it live with a draggable light before you export. Runs entirely in your browser.

**Live:** <https://normal-map-lab.slippylabs.com/>

## What it does

- Four ways to get a height field out of a sprite: luminance, inverted luminance, alpha, or a **bevel from the silhouette**.
- Height scale in pixels, Gaussian smoothing, Sobel or central-difference gradients, and a strength multiplier.
- Invert X and invert Y, for the OpenGL and DirectX green-channel conventions.
- Four views side by side — source, height, normal map and a lit preview with a draggable (or orbiting) light, ambient and specular.
- Export the normal map and the height map as PNGs at the source size.

## How it works

A normal map stores a direction per pixel packed into colour: x and y from −1..1 into 0..255 with 128 as zero, z from 0..1 into 128..255. A flat surface is therefore (128, 128, 255) — the famous lavender — and a normal map that is not mostly lavender is either very bumpy or wrong.

Height is kept in **pixels** throughout, so the gradient is a real slope and `n = normalize(−dh/dx, −dh/dy, 1)` needs no fudge factor. That is also what makes it testable against a surface whose normals are known.

The bevel is the mode that makes a flat sprite read as a solid object: take the distance from each opaque pixel to the nearest transparent one and use a quarter-circle of that distance as the height. It ignores the painted detail entirely, which is usually what you want for flat-coloured art.

That distance has to be a **true Euclidean** distance. A chamfer approximation puts visible diagonal creases around every bevel, and the sweeping vector-propagation transforms (4SED, 8SSEDT) are cheap but only *almost* exact — measured against an exact transform they are out by a few hundredths of a pixel, which is small but permanent and silent. So this uses Felzenszwalb and Huttenlocher's transform: an exact 1D transform down every column and then across every row, exact because squared Euclidean distance is separable, and still linear time.

## Verification

`verify_normal.py` feeds the pipeline surfaces whose normals are known in closed form:

- A **hemisphere**: worst normal error **0.0003** (central difference) over 12,476 interior pixels.
- A **tilted plane**: every normal is the same and known — error **1.3e-06**.
- A **cone**: every point tilts 19.290° from vertical, worst deviation **0.11°**.
- A flat field gives exactly (0, 0, 1), encoding to exactly (128, 128, 255).
- Inverting the height flips X and Y and leaves Z alone; each axis switch flips exactly one channel.
- The blur against `scipy.ndimage.gaussian_filter` (1.1e-09), mass-preserving, with a border clamp that does not darken the edges.
- The distance transform against `scipy.ndimage.distance_transform_edt`, an exact Euclidean transform: worst error **9.3e-07**. A control confirms a chamfer transform on the same mask is off by up to 8.28 px, so "exact" is a claim with teeth.
- The bevel profile over scipy's own distance field: **2.9e-08**, and it differs from a linear chamfer by 0.414 — so it is a curve, not a bevel.

**85 checks**, plus a browser test that confirms the normals are unit length and facing the viewer in a real canvas.

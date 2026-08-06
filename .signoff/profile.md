# Repo-local interview profile (Phase 3e dogfood)

This repository dogfoods its own repo-local profile mechanism (SKILL.md
Section 1 step 5): every `/signoff` run on this repo resolves this file ahead
of the embedded `software-general` default, announces the source, and stamps
the block's digest into the `interview=` token. Per repo convention the
emphases use earth/atmospheric science; the mechanics stay domain-neutral.

<!-- INTERVIEW-PROFILE:BEGIN (sole customization point — replace only this block) -->
### Interview Profile: atmos-science-dogfood
Profile-ID: atmos-science-dogfood

Domain emphases — weight probes within the universal axes; never remove axes
or lower pass criteria:
- **Unit & coordinate discipline:** every unit-bearing quantity the diff
  touches (hPa vs. Pa, kg/kg specific humidity vs. g/kg mixing ratio),
  vertical coordinate direction (surface-to-top vs. top-to-surface pressure
  ordering), and physical-constant provenance.
- **Column-physics validity:** integration/quadrature choices over model or
  pressure levels, boundary treatment at the surface and model top, and the
  atmospheric regimes (e.g. very moist tropical columns, steep topography)
  where the discretization degrades before it visibly fails.
- **Plausible-but-invalid outputs:** for each computed diagnostic, the
  physically expected magnitude range and the check that would catch a
  silently wrong result (e.g. column water vapor far outside 0–80 kg/m²).
- **Reproducibility:** seeds for any synthetic/demo data, environment
  pinning, and provenance of any reference values used in checks.
<!-- INTERVIEW-PROFILE:END -->

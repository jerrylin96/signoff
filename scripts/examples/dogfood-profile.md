# Archived Phase 3e dogfood profile (formerly `.signoff/profile.md`)

This file was this repository's repo-local interview profile for the Phase 3e
live dogfood: placed at `.signoff/profile.md`, it was resolved ahead of the
embedded `software-general` default and produced attestation `0c54122` with
`interview=standard/atmos-science-dogfood/sha256:5fd075753d5b`. It was then
deliberately retired from the live resolution path — an atmospheric-science
emphasis set should not silently govern a software repo's future signoffs —
and is preserved here, alongside `ciwv.py`, as the reproducible fixture and a
worked example of a custom profile. To reuse it, copy it to
`<your-repo>/.signoff/profile.md`. Per repo convention the emphases use
earth/atmospheric science; the mechanics stay domain-neutral.

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

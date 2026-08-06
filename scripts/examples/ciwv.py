"""Column-integrated water vapor (CIWV / precipitable water) from specific humidity.

Phase 3e dogfood fixture: a small but genuinely scientific diff so the
science-detection escalation guard (skills/signoff/SKILL.md, Interview
Intensity Levels → Guards) has real signals to fire on — scientific-stack
imports, RNG seeding, unit-bearing constants, pressure-level coordinates.

Physics: CIWV = (1/g) * integral of q dp over the column, with q in kg/kg and
p in Pa, giving kg/m^2 (equivalently mm of liquid water). Levels are supplied
in hPa, as reanalysis products conventionally do, and converted here — the
hPa-vs-Pa slip is exactly the kind of silent factor-of-100 error the
interview probes for.
"""

import numpy as np

G0 = 9.80665  # standard gravity, m s^-2 (CODATA conventional value)
HPA_TO_PA = 100.0

# Physically plausible CIWV bounds, kg m^-2: dry polar columns sit near 0,
# extreme tropical columns approach ~80; values outside this range indicate
# a unit or ordering bug, not weather.
CIWV_MIN, CIWV_MAX = 0.0, 100.0


def ciwv_from_q(q, levels_hpa):
    """Trapezoidal column integral of specific humidity on pressure levels.

    Parameters
    ----------
    q : array_like, shape (..., nlev)
        Specific humidity in kg/kg on the given pressure levels (last axis).
    levels_hpa : array_like, shape (nlev,)
        Pressure levels in hPa, strictly monotonic (either direction).

    Returns
    -------
    ndarray
        CIWV in kg m^-2 over the leading dimensions of ``q``.
    """
    q = np.asarray(q, dtype=np.float64)
    p = np.asarray(levels_hpa, dtype=np.float64) * HPA_TO_PA

    if p.ndim != 1 or p.size < 2:
        raise ValueError("levels_hpa must be 1-D with at least two levels")
    dp = np.diff(p)
    if not (np.all(dp > 0) or np.all(dp < 0)):
        raise ValueError("levels_hpa must be strictly monotonic")
    if q.shape[-1] != p.size:
        raise ValueError(f"q last axis ({q.shape[-1]}) must match levels ({p.size})")

    # Integrate top-of-column -> surface regardless of input ordering.
    if dp[0] < 0:
        q, p = q[..., ::-1], p[::-1]

    layer_mean_q = 0.5 * (q[..., 1:] + q[..., :-1])
    ciwv = np.sum(layer_mean_q * np.diff(p), axis=-1) / G0

    # Fail loudly on plausible-but-invalid output (unit slips scale by ~100).
    if np.any(ciwv < CIWV_MIN) or np.any(ciwv > CIWV_MAX):
        raise ValueError(
            f"CIWV outside physical bounds [{CIWV_MIN}, {CIWV_MAX}] kg/m^2: "
            f"min={np.min(ciwv):.3g}, max={np.max(ciwv):.3g} — check units (hPa vs Pa) and level ordering"
        )
    return ciwv


def ciwv_dataarray(q_da, level_dim="level"):
    """xarray wrapper: CIWV from a DataArray of specific humidity.

    ``q_da`` must carry a ``level_dim`` coordinate in hPa. Returns a
    DataArray in kg m^-2 with the level dimension reduced.
    """
    import xarray as xr

    q_t = q_da.transpose(..., level_dim)
    out = ciwv_from_q(q_t.values, q_t[level_dim].values)
    dims = [d for d in q_t.dims if d != level_dim]
    coords = {d: q_t.coords[d] for d in dims if d in q_t.coords}
    return xr.DataArray(out, dims=dims, coords=coords, name="ciwv", attrs={"units": "kg m-2"})


def _self_test():
    # Constant-q column has the closed form CIWV = q * (p_sfc - p_top) / g.
    levels = np.array([1000.0, 850.0, 700.0, 500.0, 300.0, 100.0])  # hPa
    q_const = np.full(levels.size, 5e-3)  # kg/kg
    expected = 5e-3 * (1000.0 - 100.0) * HPA_TO_PA / G0
    got = ciwv_from_q(q_const, levels)
    assert np.isclose(got, expected), (got, expected)

    # Ordering invariance: top-down and bottom-up level orderings agree.
    rng = np.random.default_rng(seed=42)
    q_rand = np.clip(rng.normal(4e-3, 1e-3, size=(8, levels.size)), 0.0, None)
    assert np.allclose(ciwv_from_q(q_rand, levels), ciwv_from_q(q_rand[..., ::-1], levels[::-1]))

    # A forgotten hPa->Pa conversion (values already in Pa passed as hPa)
    # inflates CIWV ~100x and must fail loudly, not return plausibly.
    try:
        ciwv_from_q(q_const, levels * HPA_TO_PA)
    except ValueError:
        pass
    else:
        raise AssertionError("unit-slip case did not fail loudly")

    print(f"self-test passed: constant-q CIWV = {got.item():.3f} kg/m^2 (expected {expected:.3f})")


if __name__ == "__main__":
    _self_test()

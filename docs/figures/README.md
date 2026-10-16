# Flood-depth-from-SAR papers, illustrated

One schematic explainer per paper: the big idea, four steps, and what each method needs, gives, achieves and gets wrong.
All drawings are schematic (no satellite imagery). Regenerate with `python docs/figures/make_figures.py`.


## Family A — fit a water line along the river

### REFIX — Schumann et al. 2007

![REFIX — Schumann et al. 2007](papers/01_schumann2007_refix.svg)

### Cross-section fitting — Zwenzner & Voigt 2009

![Cross-section fitting — Zwenzner & Voigt 2009](papers/02_zwenzner_voigt2009.svg)

### Change detection + boundary statistics — Cian et al. 2018

![Change detection + boundary statistics — Cian et al. 2018](papers/03_cian2018.svg)


## Family B — spread flood-edge elevation inward

### FwDET v1 — Cohen et al. 2018

![FwDET v1 — Cohen et al. 2018](papers/04_cohen2018_fwdet.svg)

### FwDET v2.0 (coastal) — Cohen et al. 2019

![FwDET v2.0 (coastal) — Cohen et al. 2019](papers/05_cohen2019_fwdet_v2.svg)

### FwDET v2.1 (edge cleaning) — Cohen et al. 2022

![FwDET v2.1 (edge cleaning) — Cohen et al. 2022](papers/06_cohen2022_fwdet_v21.svg)

### FLEXTH — Betterle & Salamon 2024

![FLEXTH — Betterle & Salamon 2024](papers/07_betterle_salamon2024_flexth.svg)


## Family C — height above nearest drainage (HAND)

### HAND / GeoFlood — Nobre 2011; Zheng et al. 2018

![HAND / GeoFlood — Nobre 2011; Zheng et al. 2018](papers/08_hand_nobre2011_geoflood2018.svg)

### NWM-HAND evaluation — Johnson et al. 2019

![NWM-HAND evaluation — Johnson et al. 2019](papers/09_johnson2019_nwm_hand.svg)

### RICorDE — Bryant et al. 2022

![RICorDE — Bryant et al. 2022](papers/10_bryant2022_ricorde.svg)


## Family D — comparisons & machine learning

### HAND vs TVD vs FwDET — Teng et al. 2022

![HAND vs TVD vs FwDET — Teng et al. 2022](papers/11_teng2022_comparison.svg)

### End-to-end SAR benchmark — Travert et al. 2025/26

![End-to-end SAR benchmark — Travert et al. 2025/26](papers/12_travert2025_benchmark.svg)

### Machine-learning depth — Elkhrachy 2022

![Machine-learning depth — Elkhrachy 2022](papers/13_elkhrachy2022_ml.svg)


## Operational product (NASA)

### HydroSAR (NASA SERVIR) — Meyer et al. 2024

![HydroSAR (NASA SERVIR) — Meyer et al. 2024](papers/14_hydrosar_meyer2024.svg)

## Which to use with ICEYE + USGS 3DEP?

Flood extent by change detection / local thresholding with slope, HAND and permanent-water masks → depth with **FLEXTH** and **FwDET v2.1** (v2.0 coast rule for Florida) → **HAND/RICorDE** cross-check → validate with USGS high-water marks and gauges.

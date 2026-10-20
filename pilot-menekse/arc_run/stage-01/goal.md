> **Note (Stage 01 — unverified draft):** Benchmark names and SOTA claims in this file are LLM-generated estimates. They will be verified during the literature search stage.

# SMART Research Goal

## Topic
Computational aesthetics of the sublime in the Anthropocene: formalizing and measuring the scale/immersion shift from Caspar David Friedrich's Romantic landscapes to algorithmically generated "digital nature" ecosystems (e.g., Refik Anadol's data-driven installations, Quayola's procedural landscapes). The machine-learning framing is: can learned representations capture and quantify the perceptual-aesthetic dimensions ("vastness," "immersion," "threat/awe," "intelligibility") that art theory attributes to the sublime, and do these dimensions systematically differ between human-painted Romantic sublime and machine-generated digital sublime?

## Novel Angle
Most ML work on art touches three well-trodden areas: (1) **style transfer / generation** of landscape imagery, (2) **style/genre classification** (e.g., WikiArt genre/style prediction), and (3) **computational aesthetics** that predicts a single scalar "beauty/aesthetic score." All three are saturated, and a reviewer would call them well-known. The sublime, crucially, is **not** reducible to "beauty" — in Kant/Burke it is defined by the tension between overwhelming magnitude (vastness, formlessness, potential threat) and the viewer's comprehension. This specific, theory-grounded, *multi-dimensional* construct has **not** been operationalized as a measurable representational axis in vision models, and the **diachronic comparison** (Romantic human sublime → algorithmic/generative digital sublime) has not been quantified at all.

The timely opportunity comes from three recent developments that make this feasible now and that prior art-ML work could not exploit:
1. **Vision-language models (CLIP-family) as zero-shot perceptual probes.** We can score images along *named* aesthetic/affective axes (vastness, immersion, awe, formlessness) via text prompts without training a labeled sublime classifier — turning a humanistic construct into a measurable embedding-space direction. This "prompt-as-dimension" use for a contested art-historical concept is unexplored.
2. **Interpretability of embedding geometry.** Instead of a black-box score, we can test whether "the sublime" corresponds to a *linear direction* or a low-dimensional subspace in CLIP space, and whether human-Romantic and machine-generated sublime images occupy *different regions/trajectories* along that subspace — a concept-direction analysis, not another classifier.
3. **Proliferation of generative "digital nature."** Diffusion models now let us *generate* controlled digital-sublime stimuli and measure how scale/immersion cues shift, enabling a counterfactual study (prompt a scene toward "vast/immersive" and track movement along the learned axis) rather than a passive corpus study.

How this differs from standard approaches: we are **not** predicting an aesthetic score, **not** doing style transfer, and **not** classifying genre. We are (a) *operationalizing a specific art-theoretic construct* as a probed, validated dimension, (b) *measuring a historical/medium shift* between human and algorithmic landscape art along that dimension, and (c) *validating* the axis against a small human-rating study. The contribution is a **measurement method + a quantified humanities claim**, which is the kind of "method applied to an underexplored domain + challenges an assumption" angle that avoids the "already known" critique. The assumption being challenged: that the digital sublime is merely the Romantic sublime at higher resolution — we test whether the *immersion* axis (not just the *vastness* axis) is what actually shifts.

## Scope
Single-paper scope, deliberately narrow:
- **One construct, decomposed into 3–4 sub-axes**: vastness/scale, immersion/enclosure, awe-threat valence, formlessness/intelligibility.
- **Two corpora**: (i) Romantic/landscape sublime from public art datasets; (ii) a curated set of algorithmic/generative "digital nature" images (public installation documentation + diffusion-generated stimuli under controlled prompts).
- **Three analyses**: (1) probe construction + human validation, (2) diachronic comparison of corpus positions along the axes, (3) a generative counterfactual showing which axis moves when scenes are steered toward "sublime."
- Out of scope: training new generative models, video/temporal immersion, VR/physiological measurement, full art-historical periodization.

## SMART Goal
**Specific:** Build a CLIP-based, human-validated multi-axis probe for the sublime and use it to quantify whether and how the "vastness" vs. "immersion" balance differs between Romantic human-painted landscapes and algorithmic/generative digital-nature imagery, including a diffusion counterfactual.

**Measurable:**
- Probe validity: Spearman correlation ≥ 0.5 between each probe axis score and human ratings on a held-out validation set (≥ 300 image–rating pairs, ≥ 3 raters/image).
- Diachronic effect: report standardized mean differences (Cohen's d) with bootstrap CIs on each axis between corpora, with a pre-registered primary hypothesis (immersion axis shows larger Romantic→digital shift than vastness axis).
- Counterfactual: measure average displacement (effect size) along each axis when diffusion prompts are steered toward sublime descriptors.

**Achievable:** Zero-shot/frozen CLIP probing + logistic/linear concept directions + a modest diffusion generation set — all run on a single consumer GPU in hours. No large-scale training.

**Relevant:** Bridges ML interpretability (concept directions in VLMs), computational aesthetics, and digital humanities — directly addresses the stated topic's "scale and immersion shift."

**Time-bound:** 8 weeks — Wk 1–2 corpus assembly + probe design; Wk 3–4 human validation study; Wk 5–6 diachronic analysis; Wk 7 diffusion counterfactual; Wk 8 writing.

## Constraints
- **Compute:** Single GPU (e.g., one 12–24 GB card). Frozen CLIP inference for embeddings; linear probes train in minutes on CPU/GPU. Diffusion stimulus generation limited to a few hundred images (hours, not days). No model pretraining.
- **Tools:** Open CLIP / vision-language encoders (frozen); an open text-to-image diffusion model for counterfactual stimuli; scikit-learn / PyTorch for linear probes; standard stats (bootstrap, mixed-effects for rater variance); a lightweight crowd or in-lab rating interface.
- **Data access:** Public art datasets for landscape/Romantic imagery; publicly available documentation images of algorithmic installations (used for analysis/criticism, with provenance tracked and licensing noted — generated stimuli used where licensing is restrictive); human ratings collected under a short IRB-exempt/consented protocol.

## Success Criteria
Publishable (threshold ≥ 4.0) if:
1. **Validated probe:** The sublime axes correlate with human ratings above the pre-registered threshold and outperform a single-scalar "aesthetic score" baseline and a naive "landscape vs. not" baseline at recovering sublime ratings.
2. **A quantified humanities claim:** A statistically significant, effect-sized difference between Romantic and digital-sublime corpora, with the *direction* of the shift (which axis moves) reported — ideally supporting or refuting the "immersion, not just vastness" hypothesis with CIs.
3. **Counterfactual consistency:** Diffusion steering toward sublime descriptors moves images predominantly along the predicted axis, cross-validating the probe independently of the corpus.
4. **Interpretability result:** Evidence on whether the sublime is approximately linear/low-dimensional in embedding space (variance explained, direction stability under bootstrap).
5. **Reproducibility:** Released probe prompts, code, corpus manifests, and rating protocol. A negative/nuanced result (e.g., axes entangled) is still publishable if the measurement method and validation are sound.

## Benchmark
There is **no** standard benchmark for "the sublime," so evaluation is grounded in a constructed, human-validated measurement with documented baselines:
- **Primary image sources:**
  - **WikiArt** (and/or comparable public painting corpora) — source for Romantic/landscape sublime imagery; metadata: style, genre, artist, date.
  - **AVA (Aesthetic Visual Analysis)** — reference corpus for the *aesthetic-score baseline* and general computational-aesthetics comparison; typical metrics: mean aesthetic score, rating distribution.
  - **Curated digital-nature set** — public installation documentation plus diffusion-generated stimuli (controlled prompts); this is a new, released artifact, not a pre-existing benchmark.
- **Human-validation set (new, released):** ≥ 300 images rated on the sublime sub-axes (multiple raters each) — serves as ground truth for probe validity.
- **Typical metrics:** Spearman/Pearson correlation (probe vs. human ratings), inter-rater reliability (ICC / Krippendorff's α), Cohen's d with bootstrap CIs (corpus comparison), classification/ranking metrics (AUC, ranking accuracy) vs. baselines, and variance-explained for the linearity analysis.
- **SOTA tracking:** Aesthetic-quality prediction *is* commonly tracked on AVA (leaderboards exist for mean-score prediction), so the aesthetic-score baseline sits on an established, tracked task; however, the *sublime-axis* measurement itself is novel and not tracked, which is the paper's contribution rather than a leaderboard climb. (No specific model names or performance numbers asserted here — to be established in the literature-search stage.)

## Generated
2026-10-20T00:00:00Z
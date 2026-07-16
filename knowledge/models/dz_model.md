# DZ Model — AI Model Knowledge File

**Model:** DZ (Drusen size grading)
**GitHub Repository:** [dz_model](https://github.com/Toku-Eyes/dz_model)
**Local Path:** `Models\dz_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image and preprocessing pipeline)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `dz_compile.py`, `dz_model_launching.py`, `dz_image_preprocessing.py`, `dz_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: `efficientnet==1.1.1`.
- Model type: **Classification, 3 classes** ([AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11) — drusen size grading.
- Not named in the source report as a multi-grader parallel-inference model — runs sequential jury inference by default.

## 2. Image Processing Steps

DZ is explicitly named as one of the models using the **NW500 camera variant** in addition to the standard pipeline (`common/image_preprocessing.py`):

**Standard pipeline** (`preprocess_image()`, used for `camera != NW500`):
1. Read image (disk or memory, per `save_to_disk`)
2. Resolution check (≥800px)
3. `crop_img()` — crop blank background, pad to square
4. Resolution check (≥100px, post-crop)
5. Resize to 1200×1200
6. Write/read normalization cycle
7. Resize to 800×800
8. `enhance_img_native()` unsharp-mask enhancement via the native OpenCV 4.1.2 `GaussianBlur` extension
9. Save enhanced 800×800 image for inference

**NW500 camera variant** (`preprocess_image_nw500_v2()`, used when `camera == NW500`):
1. Read → resolution check → `crop_img()` → resize to 1200×1200
2. Apply salt-and-pepper noise (`apply_noise`)
3. Apply median filter (`apply_filter`)
4. Save filtered image (no unsharp-mask enhancement step — no native OpenCV 4.1.2 dependency in this branch)

- `dz_image_preprocessing.py` wraps both branches, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode; branch selection is driven by the `camera` field in the request (see [common_ai_library.md](common_ai_library.md) §2).
- `dz_model_launching.py`'s `predict_preload_jury()` decodes from the in-memory dict in memory mode.
- Input image size to the model: **800×800** (both branches).

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2. The `camera` field (`NW400`/`NW500`/`OPTOS`/other) selects the preprocessing branch (§2).
- **Response key**: `dz_results` — standard classification envelope.
- **Classes (3)**: `grade_type='dz'` maps `{0: 'none/small', 1: 'medium', 2: 'large'}`.
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "dz_results": {
    "patient": { "prediction": "none/small", "grade": null },
    "left_eye": { "prediction": "none/small", "grade": null },
    "right_eye": { "prediction": "none/small", "grade": null },
    "images": [
      { "id": "...", "left_right": "right", "prediction": "none/small",
        "probability": [[0.767, 0.220, 0.013]], "embedding": null }
    ],
    "version": "0.0.0"
  }
  ```
  Note `grade` is `null` here (unlike R/M's `Mild NPDR`-style human labels) — DZ surfaces only the raw label string.
**Input attributes:** `Sex`, `DOB`, `camera` (selects standard vs NW500 preprocessing branch), `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `patient.prediction` / `left_eye.prediction` / `right_eye.prediction` — aggregated drusen-size class label
- `images[].id`, `images[].left_right` — per-image identifiers
- `images[].prediction` — per-image predicted class (`none/small`/`medium`/`large`)
- `images[].probability` — jury-mean 3-class probability row
- `images[].embedding` — always null
## 4. Number of Graders (Jury Size)

- The example response shows **a single probability row** (`[[0.767, 0.220, 0.013]]`) per image — this is the **jury-mean** probability vector already aggregated by `postprocess_inference()` (unlike R/M which expose the raw per-jury-member rows). The underlying jury count is therefore not directly countable from the wrapper output; check `_models/{grader}/` in the `dz_model` repo for the exact jury size (typically 3–5 per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2).
- Aggregation: `eye_max_jury_mean()` — `max(mean_across_jury(argmax(per_image)))` per eye.

## 5. Model Details

- **Keras 3 compatibility layer:** `dz_compile.py` / `dz_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** the size of drusen (small yellow deposits of lipids/proteins under the retina) — the earliest hallmark of Age-related Macular Degeneration (AMD), one of the leading causes of vision loss in older adults.
- **Clinical rationale:** drusen size is a core criterion in standard AMD staging systems (e.g. AREDS severity scale) — larger and more numerous drusen indicate higher risk of progression to intermediate/advanced AMD (geographic atrophy or neovascular AMD).
- **Grading scale:** 3-class severity (`none/small`, `medium`, `large`).
- **How it predicts:** an EfficientNet-based classifier (`efficientnet==1.1.1`) analyzes the preprocessed fundus image; DZ additionally uses the NW500 camera-specific preprocessing variant (noise + median filtering instead of unsharp-mask enhancement) since certain camera sources require different image normalization to preserve drusen texture detail.
- **Clinical use:** supports AMD risk stratification and monitoring, flagging patients who may need referral for closer AMD surveillance or treatment (e.g. AREDS2 supplementation).

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`dz-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/dz_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/dz_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper only.
- readinessProbe/livenessProbe gate traffic until model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

14 tests, 86% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v22, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

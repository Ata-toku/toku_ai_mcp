# TCHDL Model — AI Model Knowledge File

**Model:** TCHDL (Total Cholesterol / HDL)
**GitHub Repository:** [tchdl_model](https://github.com/Toku-Eyes/tchdl_model)
**Local Path:** `Models\tchdl_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image and preprocessing pipeline)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `tchdl_compile.py`, `tchdl_model_launching.py`, `tchdl_image_preprocessing.py`, `tchdl_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: `efficientnet==1.1.1`.
- Model type: **Regression + Embedding** ([AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11) — predicts the Total Cholesterol / HDL ratio plus an embedding vector per image.
- Not named in the source report as a multi-grader parallel-inference model — runs sequential jury inference by default.

## 2. Image Processing Steps

Uses the shared **standard pipeline** from `common/image_preprocessing.py` (full detail in [common_ai_library.md](common_ai_library.md) §3):
1. Read image (disk or memory, per `save_to_disk`)
2. Resolution check (≥800px)
3. `crop_img()` — crop blank background, pad to square
4. Resolution check (≥100px, post-crop)
5. Resize to 1200×1200
6. Write/read normalization cycle
7. Resize to 800×800
8. `enhance_img_native()` unsharp-mask enhancement via the native OpenCV 4.1.2 `GaussianBlur` extension
9. Save enhanced 800×800 image for inference

- `tchdl_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `tchdl_model_launching.py` uses `infer_embed_models()` → `predict_preload_embed_jury()` (dual-output embedding + regression path) to decode from the in-memory dict in memory mode.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `tchdl_results` — **regression + embedding envelope** (`format_regression_embedding_outbound_message()`).
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "tchdl_results": {
    "patient": { "prediction": "3.8098007678985595", "grade": null },
    "left_eye": { "prediction": "3.7959048748016357", "grade": null },
    "right_eye": { "prediction": "3.823696660995483", "grade": null },
    "images": [
      { "id": "...", "left_right": "right", "prediction": "3.823696660995483",
        "probability": null, "embedding": [-0.395, -0.418, 0.192, 0.482, -0.184, -0.166, 0.505, 0.128] }
    ],
    "version": "0.0.0"
  }
  ```
- `prediction` is the TC/HDL ratio as a numeric string (mean regression value across jury); `embedding` is the mean 8-dimensional embedding vector across jury; `probability` is always `null`.
**Input attributes:** `Sex`, `DOB`, `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `patient.prediction` / `left_eye.prediction` / `right_eye.prediction` — mean predicted TC/HDL ratio as numeric strings
- `images[].id`, `images[].left_right` — per-image identifiers
- `images[].prediction` — per-image predicted ratio
- `images[].embedding` — mean 8-dimensional feature embedding across jury
- `images[].probability` — always null
## 4. Number of Graders (Jury Size)

- Not directly observable from the jury-averaged embedding in the example response. Per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2, jury ensembles are typically **3–5 trained models**, loaded from `_models/{grader}/` — confirm exact count against the `tchdl_model` repo's `_models/` directory.
- Aggregation: `postprocess_regression_embedding_inference()` averages regression + embedding outputs across the jury, per image then per eye.

## 5. Model Details

- **Keras 3 compatibility layer:** `tchdl_compile.py` / `tchdl_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** Total Cholesterol / HDL ratio — a standard lipid-panel-derived cardiovascular risk marker normally obtained from a fasting blood test.
- **Clinical rationale:** dyslipidemia contributes to retinal vascular changes (e.g. lipid deposition contributing to arteriolar changes) that correlate with systemic lipid profile; this model applies the oculomics approach to estimate a lipid biomarker from a fundus photo rather than blood work.
- **How it predicts:** an EfficientNet-based embedding network (`efficientnet==1.1.1`) extracts a per-image feature vector; a jury of regression heads (`predict_preload_embed_jury()`) each estimate the TC/HDL ratio + embedding, averaged across jury and eyes.
- **Clinical use:** intended as a non-invasive screening/adjunct signal for lipid-related cardiovascular risk, not a replacement for a fasting lipid panel.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`tchdl-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/tchdl_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/tchdl_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper only.
- readinessProbe/livenessProbe gate traffic until jury embedding/regression model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

14 tests, 95% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v15, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

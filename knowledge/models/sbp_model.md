# SBP Model — AI Model Knowledge File

**Model:** SBP (Systolic Blood Pressure)
**GitHub Repository:** [sbp_model](https://github.com/Toku-Eyes/sbp_model)
**Local Path:** `Models\sbp_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image and preprocessing pipeline)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `sbp_compile.py`, `sbp_model_launching.py`, `sbp_image_preprocessing.py`, `sbp_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: `efficientnet==1.1.1`.
- Model type: **Regression + Embedding** ([AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11) — predicts Systolic Blood Pressure plus an embedding vector per image.
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

- `sbp_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `sbp_model_launching.py` uses `infer_embed_models()` → `predict_preload_embed_jury()` (dual-output embedding + regression path) to decode from the in-memory dict in memory mode.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `sbp_results` — **regression + embedding envelope** (`format_regression_embedding_outbound_message()`).
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "sbp_results": {
    "patient": { "prediction": "128.97907257080078", "grade": null },
    "left_eye": { "prediction": "129.98094329833984", "grade": null },
    "right_eye": { "prediction": "127.97720184326172", "grade": null },
    "images": [
      { "id": "...", "left_right": "right", "prediction": "127.97720184326172",
        "probability": null, "embedding": [-2.644, -11.269, 1.651, -22.309, -52.603, -8.568, 7.338, -31.780] }
    ],
    "version": "0.0.0"
  }
  ```
- `prediction` is mmHg as a numeric string (mean regression value across jury); `embedding` is the mean 8-dimensional embedding vector across jury; `probability` is always `null`.
**Input attributes:** `Sex`, `DOB`, `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `patient.prediction` / `left_eye.prediction` / `right_eye.prediction` — mean predicted systolic blood pressure (mmHg) as numeric strings
- `images[].id`, `images[].left_right` — per-image identifiers
- `images[].prediction` — per-image predicted SBP value
- `images[].embedding` — mean 8-dimensional feature embedding across jury
- `images[].probability` — always null
## 4. Number of Graders (Jury Size)

- Not directly observable from the jury-averaged embedding in the example response. Per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2, jury ensembles are typically **3–5 trained models**, loaded from `_models/{grader}/` — confirm exact count against the `sbp_model` repo's `_models/` directory.
- Aggregation: `postprocess_regression_embedding_inference()` averages regression + embedding outputs across the jury, per image then per eye.

## 5. Model Details

- **Keras 3 compatibility layer:** `sbp_compile.py` / `sbp_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default (the `PARALLEL_INFERENCE` mechanism in `common/model_inference.py` is available but only documented for R, M, CVD, HbA1c).
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** Systolic Blood Pressure (SBP, mmHg) from a fundus photograph — an oculomics estimate of a vital sign normally measured with a cuff sphygmomanometer.
- **Clinical rationale:** chronic hypertension produces measurable retinal microvascular changes — generalized arteriolar narrowing, increased arteriole-to-venule (AV) ratio changes, and vessel tortuosity — collectively "hypertensive retinopathy" signs that a deep network can learn to correlate with SBP even before clinically overt retinopathy.
- **How it predicts:** an EfficientNet-based embedding network (`efficientnet==1.1.1`) extracts a per-image feature vector; a jury of regression heads (`predict_preload_embed_jury()`) each estimate SBP + embedding, averaged across jury and eyes.
- **Clinical use:** intended as a non-invasive screening/adjunct signal for blood pressure estimation from a retinal photo, not a replacement for direct cuff-based measurement.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`sbp-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/sbp_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/sbp_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper only.
- readinessProbe/livenessProbe gate traffic until jury embedding/regression model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

14 tests, 95% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v18, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

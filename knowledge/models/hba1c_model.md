# HbA1c Model — AI Model Knowledge File

**Model:** HbA1c (jury grader)
**GitHub Repository:** [hba1c_model](https://github.com/Toku-Eyes/hba1c_model)
**Local Path:** `Models\hba1c_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image, preprocessing, jury inference engine)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `hba1c_compile.py`, `hba1c_model_launching.py`, `hba1c_image_preprocessing.py`, `hba1c_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: `efficientnet==1.1.1`.
- Model type: **Regression + Embedding** ([AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11) — dual-output model producing both an HbA1c value and an embedding vector per image.
- HbA1c is one of the models explicitly called out as using a **jury of multiple graders**.

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

- `hba1c_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `hba1c_model_launching.py` uses `infer_embed_models()` → `predict_preload_embed_jury()` (dual-output embedding + regression path, distinct from the plain classification `predict_preload_jury()` used by R/M/DZ/PA/Ethnicity/QC/QC2), decoding from the in-memory dict in memory mode.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `hba1c_results` — **regression + embedding envelope** (`format_regression_embedding_outbound_message()`).
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "hba1c_results": {
    "patient": { "prediction": "77.4407527923584", "grade": null },
    "left_eye": { "prediction": "77.90041885375976", "grade": null },
    "right_eye": { "prediction": "76.98108673095703", "grade": null },
    "images": [
      { "id": "...", "left_right": "right", "prediction": "76.98108673095703",
        "probability": null, "embedding": [6.585, -15.256, -2.478, 8.704, -1.177, 12.974, -12.645, -10.906] }
    ],
    "version": "0.0.0"
  }
  ```
- `prediction` is the **mean regression value across jury** (returned as a numeric string); `embedding` is the **mean embedding vector across jury** (8-dimensional in the example payload); `probability` is always `null` for this model type.
**Input attributes:** `Sex`, `DOB`, `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2 (this model does not consume `DiabetesStatus`/`SmokingStatus` directly, unlike CVD).

**Output attributes:**
- `patient.prediction` / `left_eye.prediction` / `right_eye.prediction` — mean predicted HbA1c value (%) as numeric strings
- `images[].id`, `images[].left_right` — per-image identifiers
- `images[].prediction` — per-image predicted HbA1c value
- `images[].embedding` — mean 8-dimensional feature embedding across jury
- `images[].probability` — always null (regression model, no class probabilities)
## 4. Number of Graders (Jury Size)

- Not directly observable from a single embedding row in the example response (only the jury-averaged embedding is surfaced, unlike R/M which expose per-jury-member probability rows). Per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2, jury ensembles are typically **3–5 trained models**, loaded from `_models/{grader}/` — confirm exact count against the `hba1c_model` repo's `_models/` directory.
- Aggregation: `postprocess_regression_embedding_inference()` averages regression + embedding outputs across the jury per image, then per eye.

## 5. Model Details

- **Keras 3 compatibility layer:** `hba1c_compile.py` / `hba1c_model_launching.py` use the `tf_keras` fallback pattern.
- **Jury / Parallel Inference:** HbA1c is one of the four explicitly-named jury models (R, M, CVD, HbA1c):

  | Environment Variable | Default | Description |
  |----------------------|---------|--------------|
  | `PARALLEL_INFERENCE` | `false` | Enable concurrent jury grader execution |
  | `PARALLEL_INFERENCE_THREADS` | `min(jury size, cpu_count())` | Max concurrent threads |

  Implemented via `ThreadPoolExecutor` in shared `common/model_inference.py`; ~20% inference-time reduction, higher peak memory as trade-off; sequential remains default fallback.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** HbA1c (glycated hemoglobin) level — the standard clinical marker of average blood glucose control over the preceding 2–3 months, normally measured via a blood draw.
- **Clinical rationale:** chronic hyperglycemia produces measurable microvascular changes in the retina (vessel caliber, tortuosity, texture) even before overt diabetic retinopathy appears; this is an oculomics application estimating a systemic metabolic biomarker from a fundus photo instead of a blood test.
- **How it predicts:** an EfficientNet-based embedding network (`efficientnet==1.1.1`) extracts a feature vector per image; a jury of independently trained regression heads (`predict_preload_embed_jury()`) each output an HbA1c estimate + embedding, averaged across the jury and across eyes for the final patient-level value.
- **Clinical use:** intended as a non-invasive, photograph-based screening signal for glycemic control, complementing (not replacing) laboratory HbA1c testing — useful in settings without easy blood-draw access.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`hba1c-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/hba1c_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/hba1c_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper only.
- readinessProbe/livenessProbe gate traffic until jury embedding/regression model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

20 tests, 95% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v23, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

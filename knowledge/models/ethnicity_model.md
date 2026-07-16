# Ethnicity Model — AI Model Knowledge File

**Model:** Ethnicity
**GitHub Repository:** [ethnicity_model](https://github.com/Toku-Eyes/ethnicity_model)
**Local Path:** `Models\ethnicity_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image and preprocessing pipeline)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `ethnicity_compile.py`, `ethnicity_model_launching.py`, `ethnicity_image_preprocessing.py`, `ethnicity_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: `efficientnet==1.1.1`.
- Model type: **Classification, 2 classes** ([AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11) — ethnicity classification, consumed internally by `cvd_model` to compute `CVDRiskScore_nonblack`.
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

- `ethnicity_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `ethnicity_model_launching.py`'s `predict_preload_jury()` decodes from the in-memory dict in memory mode.
- Input image size to the model: **800×800**.
- Unlike other classification models, Ethnicity aggregates only to **patient level** — `left_eye`/`right_eye` are `null` in the response (no per-eye left/right tagging in `postprocess_inference()` for this model).

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `ethnicity_results` — standard classification envelope, but **patient-level only**.
- **Classes (2)**: `non-black` / `black`.
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "ethnicity_results": {
    "patient": { "prediction": "non-black", "grade": null },
    "left_eye": { "prediction": null, "grade": null },
    "right_eye": { "prediction": null, "grade": null },
    "images": [
      { "id": "...", "left_right": null, "prediction": "non-black",
        "probability": [[0.649, 0.351]], "embedding": null }
    ],
    "version": "0.0.0"
  }
  ```
  Note `left_right` is `null` per image too — Ethnicity does not track left/right eye position.
**Input attributes:** `Sex`, `DOB`, `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `patient.prediction` — aggregated `non-black`/`black` label (patient-level only)
- `left_eye.prediction` / `right_eye.prediction` — always null for this model
- `images[].id`, `images[].prediction` — per-image identifier and predicted class
- `images[].left_right` — always null (no per-eye tracking)
- `images[].probability` — jury-mean 2-class probability row
- `images[].embedding` — always null
## 4. Number of Graders (Jury Size)

- The example response shows **a single probability row** per image — the jury-mean 2-class probability vector, already aggregated. Underlying jury size not directly countable from the wrapper output; check `_models/{grader}/` in the `ethnicity_model` repo (typically 3–5 per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2).
- Aggregation: patient-level `mean(across jury)` → `argmax`, without the left/right eye split used by other classification models.

## 5. Model Details

- **Keras 3 compatibility layer:** `ethnicity_compile.py` / `ethnicity_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** an image-derived ethnicity proxy (`non-black`/`black`) from the fundus photograph itself — not a diagnostic output in its own right, but an auxiliary classifier that recalibrates another model's prediction.
- **Clinical rationale:** retinal-image-derived CVD risk relationships (vessel caliber, pigmentation of the fundus background, etc.) have been shown in some populations to differ by ethnicity; rather than relying on (often missing or unreliable) self-reported ethnicity, this model infers an ethnicity signal directly from the image to support a fairer, recalibrated risk estimate.
- **How it predicts:** an EfficientNet-based classifier (`efficientnet==1.1.1`) analyzes overall fundus pigmentation/appearance patterns; jury-mean probability determines the binary label at the patient level (not per-eye, since ethnicity is a patient-level attribute, not an eye-level one).
- **Clinical use:** consumed exclusively by the CVD model to compute `CVDRiskScore_nonblack`/`CVDRiskConfidence_nonblack` — it is not returned to clinicians as a standalone diagnostic finding.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`ethnicity-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/ethnicity_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/ethnicity_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; the model-wrapper calls this model first (or in parallel) so its output is available before CVD's ethnicity-adjusted risk fields are computed.
- readinessProbe/livenessProbe gate traffic until model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

10 tests, 87% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v19, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

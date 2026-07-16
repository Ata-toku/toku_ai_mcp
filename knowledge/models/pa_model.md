# PA Model — AI Model Knowledge File

**Model:** PA (Pigmentary Abnormality)
**GitHub Repository:** [pa_model](https://github.com/Toku-Eyes/pa_model)
**Local Path:** `Models\pa_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image and preprocessing pipeline)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `pa_compile.py`, `pa_model_launching.py`, `pa_image_preprocessing.py`, `pa_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: `efficientnet==1.1.1`.
- Model type: **Classification, 2 classes** ([AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11) — pigmentary abnormality detection.
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

- `pa_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `pa_model_launching.py`'s `predict_preload_jury()` decodes from the in-memory dict in memory mode.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `pa_results` — standard classification envelope.
- **Classes (2)**: `negative` / `positive` (raw labels, no `grade_type` human-readable mapping applied — `grade` is `null`).
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "pa_results": {
    "patient": { "prediction": "negative", "grade": null },
    "left_eye": { "prediction": "negative", "grade": null },
    "right_eye": { "prediction": "negative", "grade": null },
    "images": [
      { "id": "...", "left_right": "right", "prediction": "negative",
        "probability": [[0.771, 0.229]], "embedding": null }
    ],
    "version": "0.0.0"
  }
  ```

**Input attributes:** `Sex`, `DOB`, `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `patient.prediction` / `left_eye.prediction` / `right_eye.prediction` — aggregated `negative`/`positive` label
- `images[].id`, `images[].left_right` — per-image identifiers
- `images[].prediction` — per-image predicted class
- `images[].probability` — jury-mean 2-class probability row
- `images[].embedding` — always null

## 4. Number of Graders (Jury Size)

- The example response shows **a single probability row** per image — the jury-mean 2-class probability vector, already aggregated by `postprocess_inference()`. Underlying jury size not directly countable from the wrapper output; check `_models/{grader}/` in the `pa_model` repo (typically 3–5 per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2).
- Aggregation: `eye_max_jury_mean()` — `max(mean_across_jury(argmax(per_image)))` per eye.

## 5. Model Details

- **Keras 3 compatibility layer:** `pa_compile.py` / `pa_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** pigmentary abnormalities of the retinal pigment epithelium (RPE) — clumping, mottling, or depigmentation patterns visible in the fundus photo.
- **Clinical rationale:** RPE pigmentary changes are an early structural sign associated with AMD progression and other retinal degenerative conditions (e.g. retinitis pigmentosa presents with characteristic pigment patterns); detecting them supports earlier risk flagging before more advanced structural damage occurs.
- **Grading scale:** binary `negative`/`positive` classification.
- **How it predicts:** an EfficientNet-based classifier (`efficientnet==1.1.1`) analyzes the preprocessed 800×800 fundus image for pigment-pattern texture features; jury-mean probability determines the final label.
- **Clinical use:** contributes an additional structural-risk signal alongside DZ (drusen) as part of a broader AMD/retinal-degeneration risk assessment.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`pa-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/pa_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/pa_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper only.
- readinessProbe/livenessProbe gate traffic until model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

14 tests, 85% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v18, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

# R Model — AI Model Knowledge File

**Model:** R (Retinopathy jury grader)
**GitHub Repository:** [r_model](https://github.com/Toku-Eyes/r_model)
**Local Path:** `Models\r_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image, preprocessing, jury inference engine)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image (`ARG BASE_IMAGE=...common-ai-library:buildid-13`); no local `pip install` or `common/` folder.
- Model-specific files replacing the old shared ones:
  - `r_compile.py` (replaces shared `compile.py`)
  - `r_model_launching.py` (replaces shared `common/model_launching.py`)
  - `r_image_preprocessing.py`
  - `r_pipeline.py` — orchestrates disk/memory mode selection and cleanup
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/` (was `/root/`).
- Uses a **jury of multiple graders** run against the same image — R is one of the models explicitly called out for multi-grader parallel inference.

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

- `r_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `r_model_launching.py`'s `predict_preload_model()`/`predict_preload_jury()` decodes images from the in-memory dict instead of `ImageDataGenerator` file reads when in memory mode.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2 (`FirstName`, `LastName`, `Sex`, `camera`, `DOB`, `DiabetesStatus`, `SmokingStatus`, `batchimages[]`).
- **Response key**: `r_result` (standard classification envelope), also folded into `rm_overall_results.rModel` alongside the M model for a combined CLAiR traffic-light result (`result`, `risk`).
- **Classes**: 6-class retinopathy grading (e.g. `R1` = "Mild NPDR" per the example response) — `R0`–`R5`-style severity scale.
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "r_result": {
    "patient": { "prediction": "R1", "grade": "Mild NPDR" },
    "left_eye": { "prediction": "R1", "grade": "Mild NPDR" },
    "right_eye": { "prediction": "R1", "grade": "Mild NPDR" },
    "images": [ { "id": "...", "left_right": "right", "prediction": "R1",
      "probability": [[6 class-prob values], "...5 rows total..."], "embedding": null } ],
    "version": "0.0.0"
  }
  ```

**Input attributes** (fundus image + patient context, per [common_ai_library.md](common_ai_library.md) §2): `Sex`, `DOB`, `camera`, `batchimages[].ImageName`, `batchimages[].Image64` (base64 fundus photograph). `DiabetesStatus`/`SmokingStatus` are accepted but not consumed by this model directly.

**Output attributes:**
- `patient.prediction` / `patient.grade` — patient-level severity label + human-readable grade name
- `left_eye.prediction` / `right_eye.prediction` — per-eye aggregated label
- `images[].id` — source image filename/UID
- `images[].left_right` — left/right eye tag
- `images[].prediction` — per-image predicted class
- `images[].probability` — jury probability matrix (5 rows x 6 class-probabilities)
- `images[].embedding` — always null (classification model, no embedding output)

## 4. Number of Graders (Jury Size)

- Observed directly in the example response: **5 probability rows per image** → jury size = **5** graders voting per image, each producing a 6-class probability vector; aggregation is `mean(across jury)` → `argmax` per [inference_postprocesssing.py](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §4.5 / §7.2/§7.3.
- Weights loaded from `_models/{grader}/` — one SavedModel/`.h5` directory per jury member.

## 5. Model Details

- **Keras 3 compatibility layer:** `r_compile.py` / `r_model_launching.py` use the `tf_keras` → `tensorflow.keras` fallback pattern (TF 2.20 ships Keras 3).
- **Jury / Parallel Inference:** R is one of the four models (R, M, CVD, HbA1c) explicitly named as using a jury of multiple graders. Parallel inference is opt-in via:

  | Environment Variable | Default | Description |
  |----------------------|---------|--------------|
  | `PARALLEL_INFERENCE` | `false` | Enable concurrent jury grader execution |
  | `PARALLEL_INFERENCE_THREADS` | `min(jury size, cpu_count())` | Max concurrent threads |

  Implemented in shared `common/model_inference.py` via `ThreadPoolExecutor`; ~20% inference-time reduction observed, at the cost of higher peak memory (each thread holds its own batch/generator).
- **Inference enhancements:** returns `pred.tolist(), pred_prob.tolist()` (class + full probability array); optional `enable_timing` param logs `[TIMING]` markers; `printEnvVariables()` / `printOpenCVExtensionStatus()` run at startup.
- Runs on the shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`, `gpu-entrypoint.sh` hardware detection) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** Diabetic Retinopathy (DR) severity from a fundus (retinal) photograph — the leading cause of preventable blindness in working-age adults with diabetes.
- **Clinical signs the model learns to detect:** microaneurysms, dot-and-blot hemorrhages, hard exudates, cotton-wool spots, venous beading, intraretinal microvascular abnormalities (IRMA), and neovascularization — the lesions ophthalmologists look for under the ETDRS/ICDR (International Clinical Diabetic Retinopathy) severity scale.
- **Grading scale:** 6-class severity ladder (e.g. `R1` = Mild NPDR in the example) spanning no DR → mild/moderate/severe non-proliferative DR (NPDR) → proliferative DR (PDR), mirroring standard clinical grading used to decide referral urgency.
- **How it predicts:** a convolutional neural network (jury of 5 independently trained models) classifies the preprocessed 800×800 fundus image directly from pixel data — no hand-engineered lesion segmentation step; each jury member votes a class-probability vector, and the mean vote (argmax) becomes the final grade.
- **Clinical use:** feeds into `rm_overall_results` (combined with the M model) to produce a CLAiR traffic-light referral recommendation (e.g. refer to ophthalmologist vs. routine re-screen).

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`r-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5 for full cluster/CI-CD detail.
- Container image: `tokueyesproduction.azurecr.io/models/r_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/r_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper, never directly by external clients.
- readinessProbe/livenessProbe gate traffic until all 5 jury model weights are loaded via `gpu-entrypoint.sh` hardware-detection startup — important here given the larger jury size increases model-load time.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

12 tests, 91% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v8, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full CycloneDX/Dependency-Track scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6 (Python 3.8→3.12, TF 2.9.1→2.20.0, Keras 2.9→3.13.2, OpenCV 4.1.2→4.12.0, CUDA 11.7→12.6.0, Ubuntu 20.04→24.04).

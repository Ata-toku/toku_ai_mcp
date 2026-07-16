# M Model — AI Model Knowledge File

**Model:** M (Maculopathy jury grader)
**GitHub Repository:** [m_model](https://github.com/Toku-Eyes/m_model)
**Local Path:** `Models\m_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image, preprocessing, jury inference engine)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `m_compile.py`, `m_model_launching.py`, `m_image_preprocessing.py`, `m_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- M is one of the models explicitly called out as using a **jury of multiple graders**.

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

- `m_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `m_model_launching.py`'s `predict_preload_model()`/`predict_preload_jury()` decodes from the in-memory dict in memory mode instead of `ImageDataGenerator` file reads.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `m_result` (standard classification envelope), also folded into `rm_overall_results.mModel` alongside the R model for a combined CLAiR traffic-light result (`result`, `risk`).
- **Classes**: 6-class maculopathy grading (e.g. `M1` = "Mild Maculopathy" per the example response).
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "m_result": {
    "patient": { "prediction": "M1", "grade": "Mild Maculopathy" },
    "left_eye": { "prediction": "M1", "grade": "Mild Maculopathy" },
    "right_eye": { "prediction": "M1", "grade": "Mild Maculopathy" },
    "images": [ { "id": "...", "left_right": "right", "prediction": "M1",
      "probability": [[6 class-prob values], "...5 rows total..."], "embedding": null } ],
    "version": "0.0.0"
  }
  ```

**Input attributes:** `Sex`, `DOB`, `camera`, `batchimages[].ImageName`, `batchimages[].Image64` (base64 fundus photograph) — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `patient.prediction` / `patient.grade` — patient-level severity label + human-readable grade name
- `left_eye.prediction` / `right_eye.prediction` — per-eye aggregated label
- `images[].id`, `images[].left_right`, `images[].prediction` — per-image identifiers and predicted class
- `images[].probability` — jury probability matrix (5 rows x 6 class-probabilities)
- `images[].embedding` — always null

## 4. Number of Graders (Jury Size)

- Observed directly in the example response: **5 probability rows per image** → jury size = **5** graders voting per image, each producing a 6-class probability vector; aggregation is `mean(across jury)` → `argmax`.
- Weights loaded from `_models/{grader}/` — one SavedModel/`.h5` directory per jury member.

## 5. Model Details

- **Keras 3 compatibility layer:** `m_compile.py` / `m_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Jury / Parallel Inference:** M is one of the four explicitly-named jury models (R, M, CVD, HbA1c):

  | Environment Variable | Default | Description |
  |----------------------|---------|--------------|
  | `PARALLEL_INFERENCE` | `false` | Enable concurrent jury grader execution |
  | `PARALLEL_INFERENCE_THREADS` | `min(jury size, cpu_count())` | Max concurrent threads |

  Implemented via `ThreadPoolExecutor` in shared `common/model_inference.py`; ~20% inference-time reduction, higher peak memory as trade-off; sequential remains default fallback.
- **Inference enhancements:** returns class + full probability array (`pred.tolist(), pred_prob.tolist()`); optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** Diabetic Maculopathy severity — swelling/exudation affecting the macula (the central, high-acuity part of the retina), a leading cause of vision loss in diabetic eye disease even when peripheral retinopathy is mild.
- **Clinical signs the model learns to detect:** hard exudates, retinal thickening, and hemorrhages within one disc-diameter of the fovea — hallmarks of clinically significant macular edema (CSME).
- **Grading scale:** 6-class severity ladder (e.g. `M1` = Mild Maculopathy in the example), analogous to standard maculopathy grading protocols used to flag central-vision-threatening disease distinct from peripheral retinopathy severity.
- **How it predicts:** convolutional neural network jury (5 members) classifies the preprocessed 800×800 fundus image directly from pixel data; jury-mean probability vector determines the final grade.
- **Clinical use:** combined with the R model's output in `rm_overall_results` to produce the CLAiR traffic-light referral recommendation — maculopathy findings can escalate referral urgency even when overall retinopathy grade is otherwise mild.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`m-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/m_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/m_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper only.
- readinessProbe/livenessProbe gate traffic until all 5 jury model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

12 tests, 91% code coverage. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v7, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

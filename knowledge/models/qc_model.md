# QC Model — AI Model Knowledge File

**Model:** QC (Quality Control)
**GitHub Repository:** [qc_model](https://github.com/Toku-Eyes/qc_model)
**Local Path:** `Models\qc_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image, preprocessing pipeline, native OpenCV 4.1.2 extension)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `qc_compile.py`, `qc_model_launching.py`, `qc_image_preprocessing.py`, `qc_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: none (empty, like `m_model`/`r_model`/`qc2_model`).
- Model type: **Classification** — image quality grade (e.g. `A-good`), fed into the shared `QC_Grade` wrapper array alongside QC2 and OptosCropping (see §3).
- Not named in the source report as a multi-grader parallel-inference model — runs sequential jury inference by default.

## 2. Image Processing Steps ⚠️ Requires Native OpenCV 4.1.2 Extension

**Critical detail:** QC relies on `GaussianBlur` for image enhancement, and the internal blur algorithm changed between OpenCV 4.1.2 and 4.12.0. Even sub-pixel differences in blur output produce different AI predictions, so QC **cannot** use the stock modern OpenCV Gaussian blur.

Uses the shared **standard pipeline** from `common/image_preprocessing.py` (full detail in [common_ai_library.md](common_ai_library.md) §3):
1. Read image (disk or memory, per `save_to_disk`)
2. Resolution check (≥800px)
3. `crop_img()` — crop blank background, pad to square
4. Resolution check (≥100px, post-crop)
5. Resize to 1200×1200
6. Write/read normalization cycle
7. Resize to 800×800
8. `enhance_img_native()` — unsharp-mask enhancement via `get_enhance_function()`, which loads the native C++ extension that replicates the exact OpenCV 4.1.2 `GaussianBlur` algorithm, compiled for Python 3.12:
   - `gaussian_blur_412_native.cpython-312-x86_64-linux-gnu.so` (Linux)
   - `gaussian_blur_412_native.cp312-win_amd64.pyd` (Windows)
   - Links against bundled `libopencv_core.so.4.1.2` and `libopencv_imgproc.so.4.1.2`
9. Save enhanced 800×800 image for inference

- All other OpenCV operations use modern OpenCV 4.12.0 (`opencv-python-headless`); only the blur-based enhancement step (step 8) uses the native legacy extension.
- Pixel-level equivalence with original OpenCV 4.1.2 was validated with 30+ dedicated test scripts (`important_files_for_upgrade_process/`).
- `qc_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `qc_model_launching.py`'s `predict_preload_jury()` decodes from the in-memory dict in memory mode.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `QC_Grade` — a **shared array** combining QC, QC2, and OptosCropping output as one entry per image (not split into separate response keys per model):
  ```json
  "QC_Grade": [
    {
      "id": "...png",
      "grade": "A-good",
      "position": "right",
      "centered": "fovea",
      "qcoptoscropping": { "Croppable": "yes", "Status": "ok", "Error": "" }
    }
  ]
  ```
- `grade` (e.g. `A-good`) is produced by this model (QC); `centered` (e.g. `fovea`) is produced by QC2 (see [qc2_model.md](qc2_model.md)); the nested `qcoptoscropping` object is produced by [optos_cropping_model.md](optos_cropping_model.md).
- No `probability`/`embedding`/`images[]` fields at this level — `QC_Grade` is a flat per-image quality-gate array, not the classification/regression envelope used by the diagnostic models.

**Input attributes:** `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2 (QC does not consume patient demographic fields).

**Output attributes** (within each `QC_Grade[]` entry):
- `id` — source image filename/UID
- `grade` — image quality label produced by this model (e.g. `A-good`)
- `position` — left/right eye position tag
- `centered` — produced by QC2, not this model (see [qc2_model.md](qc2_model.md))
- `qcoptoscropping` — produced by OptosCropping, not this model (see [optos_cropping_model.md](optos_cropping_model.md))

## 4. Number of Graders (Jury Size)

- The `QC_Grade` wrapper output does not surface per-jury probability rows (only a final `grade` string per image), so jury size is not observable from the example response. Per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2, jury ensembles are typically **3–5 trained models**; confirm the exact count against `_models/{grader}/` in the `qc_model` repo.
- Uses the plain classification jury path (`predict_preload_jury()`), not the embedding path.

## 5. Model Details

- **Keras 3 compatibility layer:** `qc_compile.py` / `qc_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` and `printOpenCVExtensionStatus()` (the latter specifically important here to confirm the native 4.1.2 extension loaded correctly).
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical / Functional Concept & Prediction

- **What it predicts:** overall image quality of the fundus photograph (e.g. `A-good`) — not a medical/diagnostic prediction, but a technical gatekeeping classification that determines whether an image is usable for the downstream diagnostic models (R, M, DZ, PA, CVD, HbA1c, SBP, TCHDL, Ethnicity).
- **Why it matters clinically:** diagnostic models trained on well-focused, well-illuminated, artifact-free fundus photos degrade in accuracy on blurry, over/under-exposed, or artifact-laden images; QC prevents low-quality images from silently producing unreliable diagnostic outputs.
- **How it predicts:** a convolutional neural network classifies image sharpness/illumination/artifact characteristics on the preprocessed 800×800 image, using the pixel-perfect native OpenCV 4.1.2 unsharp-mask enhancement (§2) so its quality assessment remains consistent with the original model's training distribution.
- **Clinical use:** images graded poor quality can trigger a re-capture request before the diagnostic pipeline runs, avoiding false-negative/false-positive diagnostic results caused by unusable source images.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`qc-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/qc_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/qc_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; the model-wrapper typically calls QC/QC2/OptosCropping before or in parallel with the diagnostic models so quality gating can occur early in the pipeline.
- readinessProbe/livenessProbe gate traffic until model weights AND the native OpenCV 4.1.2 extension are loaded (`printOpenCVExtensionStatus()` confirms the latter).
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

8 tests, 86% code coverage. Includes baseline comparison tests verifying pixel-perfect enhancement output and inference output parity with the pre-upgrade model.

## 9. Security

SBOM v13, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

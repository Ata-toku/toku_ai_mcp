# QC2 Model — AI Model Knowledge File

**Model:** QC2 (Quality Control v2)
**GitHub Repository:** [qc2_model](https://github.com/Toku-Eyes/qc2_model)
**Local Path:** `Models\qc2_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image, preprocessing pipeline, native OpenCV 4.1.2 extension)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `qc2_compile.py`, `qc2_model_launching.py`, `qc2_image_preprocessing.py`, `qc2_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: none (empty).
- Model type: **Classification** — image centering/framing grade (e.g. `fovea`), fed into the shared `QC_Grade` wrapper array alongside QC and OptosCropping (see §3).
- Not named in the source report as a multi-grader parallel-inference model — runs sequential jury inference by default.

## 2. Image Processing Steps ⚠️ Requires Native OpenCV 4.1.2 Extension

**Critical detail:** Like QC, QC2 relies on `GaussianBlur` for image enhancement, and the algorithm changed between OpenCV 4.1.2 and 4.12.0 — sub-pixel blur differences alter AI predictions, so QC2 **cannot** use the stock modern OpenCV Gaussian blur.

Uses the shared **standard pipeline** from `common/image_preprocessing.py` (full detail in [common_ai_library.md](common_ai_library.md) §3):
1. Read image (disk or memory, per `save_to_disk`)
2. Resolution check (≥800px)
3. `crop_img()` — crop blank background, pad to square
4. Resolution check (≥100px, post-crop)
5. Resize to 1200×1200
6. Write/read normalization cycle
7. Resize to 800×800
8. `enhance_img_native()` — unsharp-mask enhancement via `get_enhance_function()`, loading the native C++ extension that replicates the exact OpenCV 4.1.2 `GaussianBlur` algorithm, compiled for Python 3.12:
   - `gaussian_blur_412_native.cpython-312-x86_64-linux-gnu.so` (Linux)
   - `gaussian_blur_412_native.cp312-win_amd64.pyd` (Windows)
   - Links against bundled `libopencv_core.so.4.1.2` and `libopencv_imgproc.so.4.1.2`
9. Save enhanced 800×800 image for inference

- All other OpenCV operations use modern OpenCV 4.12.0 (`opencv-python-headless`); only the blur-based enhancement step (step 8) uses the native legacy extension.
- Pixel-level equivalence with original OpenCV 4.1.2 was validated with 30+ dedicated test scripts.
- `qc2_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `qc2_model_launching.py`'s `predict_preload_jury()` decodes from the in-memory dict in memory mode.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2.
- **Response key**: `QC_Grade` — shared array combining QC, QC2, and OptosCropping output per image (see [qc_model.md](qc_model.md) §3 for the full shape):
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
- `centered` (e.g. `fovea`) is produced by this model (QC2); `grade` is produced by QC (see [qc_model.md](qc_model.md)); `qcoptoscropping` is produced by [optos_cropping_model.md](optos_cropping_model.md).
- No `probability`/`embedding`/`images[]` fields at this level.

**Input attributes:** `camera`, `batchimages[].Image64` fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes** (within each `QC_Grade[]` entry):
- `id` — source image filename/UID
- `centered` — image centering/framing label produced by this model (e.g. `fovea`)
- `grade` — produced by QC, not this model (see [qc_model.md](qc_model.md))
- `position` — left/right eye position tag
- `qcoptoscropping` — produced by OptosCropping, not this model (see [optos_cropping_model.md](optos_cropping_model.md))

## 4. Number of Graders (Jury Size)

- The `QC_Grade` wrapper output does not surface per-jury probability rows (only a final `centered` string per image), so jury size is not observable from the example response. Per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2, jury ensembles are typically **3–5 trained models**; confirm the exact count against `_models/{grader}/` in the `qc2_model` repo.
- Uses the plain classification jury path (`predict_preload_jury()`), not the embedding path.

## 5. Model Details

- **Keras 3 compatibility layer:** `qc2_compile.py` / `qc2_model_launching.py` use the `tf_keras` fallback pattern for TF 2.20/Keras 3.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` and `printOpenCVExtensionStatus()` (confirms the native 4.1.2 extension loaded correctly).
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical / Functional Concept & Prediction

- **What it predicts:** whether the fundus photograph is correctly centered/framed (e.g. macula-centered `fovea` vs. optic-disc-centered vs. off-center) — a technical gatekeeping check, not a medical diagnosis.
- **Why it matters clinically:** each diagnostic model (R, M, DZ, PA, CVD, HbA1c, SBP, TCHDL) expects a specific anatomical field of view (e.g. macula-centered for maculopathy/AMD-related findings); an incorrectly framed image can miss the pathology entirely even if image quality (per QC) is otherwise good.
- **How it predicts:** a convolutional neural network classifies retinal landmark position (fovea, optic disc) in the preprocessed 800×800 image, again relying on the pixel-perfect native OpenCV 4.1.2 enhancement (§2) for consistency with training data.
- **Clinical use:** incorrectly centered images can trigger a re-capture request or be excluded from diagnostic scoring for models sensitive to field of view.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`qc2-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/qc2_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/qc2_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; runs alongside QC and OptosCropping as part of the pre-diagnostic quality-gating stage.
- readinessProbe/livenessProbe gate traffic until model weights AND the native OpenCV 4.1.2 extension are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

18 tests, 86% code coverage. Includes baseline comparison tests verifying pixel-perfect enhancement output and inference output parity with the pre-upgrade model.

## 9. Security

SBOM v9, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

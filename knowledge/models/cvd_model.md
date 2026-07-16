# CVD Model — AI Model Knowledge File

**Model:** CVD (Cardiovascular Disease risk, jury grader)
**GitHub Repository:** [cvd_model](https://github.com/Toku-Eyes/cvd_model)
**Local Path:** `Models\cvd_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image, preprocessing, jury inference engine)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files: `cvd_compile.py`, `cvd_model_launching.py`, `cvd_image_preprocessing.py`, `cvd_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- `extra-requirements.txt`: **`shap==0.50.0`** — the only model in the fleet with this dependency, used for model explainability/feature-attribution behind the cardiovascular risk score.
- Model type: **Regression + Embedding** (per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §11 Model Inventory), but unlike HbA1c/SBP/TCHDL its wrapper output is a **custom risk-score schema**, not the standard regression+embedding envelope (see §3).
- CVD is one of the models explicitly called out as using a **jury of multiple graders**.

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

- `cvd_image_preprocessing.py` wraps this pipeline, accepting `img_data_dict` and `save_to_disk` for the dual disk/memory mode.
- `cvd_model_launching.py`'s `predict_preload_model()`/`predict_preload_embed_jury()` decodes from the in-memory dict in memory mode.
- Also consumes **non-image** patient metadata directly from the request (`Sex`, `DOB`→age, `SmokingStatus`, `DiabetesStatus`) to compute the final risk score — see §3.
- Input image size to the model: **800×800**.

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2. CVD is the model that actually consumes `Sex`, `DOB`, `DiabetesStatus`, `SmokingStatus` (not just images).
- **Response key**: `cvd_results` — a **custom patient-level schema**, not the standard classification or regression+embedding envelope used by other models (no `images[]` array in the wrapper output).
- **Example** (from [modelwrapper_response_example.json](../templates/modelwrapper_response_example.json)):
  ```json
  "cvd_results": {
    "CVDRiskScore": 0.0115616955,
    "CVDRiskConfidence": 99.75208,
    "CVDRiskScore_nonblack": 0.0115616955,
    "CVDRiskConfidence_nonblack": 99.75208,
    "Bioage": "31.152139657203215",
    "Bioage_after_filter": "31.152139657203215",
    "PatientData": {
      "Sex": "M", "Age": 35, "SmokingStatus": "no",
      "DiabetesStatus": "no", "Diabetes": null
    },
    "version": "0.0.0"
  }
  ```
- `CVDRiskScore_nonblack` / `CVDRiskConfidence_nonblack` are ethnicity-adjusted variants, cross-referencing `ethnicity_model`'s output internally in the wrapper.
- Internally the model still produces per-image embeddings/regression via `predict_preload_embed_jury()` (same mechanism as HbA1c/SBP/TCHDL — see [common_ai_library.md](common_ai_library.md) §2), but the wrapper's `cvd_results` surfaces only the derived risk score/Bioage, not the raw per-image embedding vectors.

**Input attributes:** `Sex`, `DOB`→`Age`, `SmokingStatus`, `DiabetesStatus` (patient metadata consumed directly), plus `batchimages[].Image64` fundus photographs — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes:**
- `CVDRiskScore` / `CVDRiskConfidence` — predicted cardiovascular risk probability + model confidence
- `CVDRiskScore_nonblack` / `CVDRiskConfidence_nonblack` — ethnicity-recalibrated risk variants
- `Bioage` / `Bioage_after_filter` — estimated retinal biological age (raw and filtered/smoothed)
- `PatientData.Sex`, `PatientData.Age`, `PatientData.SmokingStatus`, `PatientData.DiabetesStatus`, `PatientData.Diabetes` — echoed patient metadata used in the risk calculation
- `version` — wrapper schema version

## 4. Number of Graders (Jury Size)

- Not directly observable from the wrapper's `cvd_results` output (no per-image probability/embedding rows are surfaced at that layer). Per [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) §7.2, jury ensembles are typically **3–5 trained models** loaded from `_models/{grader}/`; exact CVD jury size should be confirmed against the `cvd_model` repo's `_models/` directory.
- Uses `infer_embed_models()` / `predict_preload_embed_jury()` (dual-output: embedding + regression) rather than the plain classification jury path.

## 5. Model Details

- **Keras 3 compatibility layer:** `cvd_compile.py` / `cvd_model_launching.py` use the `tf_keras` fallback pattern.
- **Jury / Parallel Inference:** CVD is one of the four explicitly-named jury models (R, M, CVD, HbA1c):

  | Environment Variable | Default | Description |
  |----------------------|---------|--------------|
  | `PARALLEL_INFERENCE` | `false` | Enable concurrent jury grader execution |
  | `PARALLEL_INFERENCE_THREADS` | `min(jury size, cpu_count())` | Max concurrent threads |

  Implemented via `ThreadPoolExecutor` in shared `common/model_inference.py`; ~20% inference-time reduction, higher peak memory as trade-off; sequential remains default fallback.
- **Inference enhancements:** returns class + full probability array; optional `enable_timing` for `[TIMING]` logs; startup diagnostics via `printEnvVariables()` / `printOpenCVExtensionStatus()`.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical Concept & Prediction

- **What it predicts:** cardiovascular disease (CVD) risk score and retinal biological age (Bioage) from fundus photographs plus patient demographics — an application of oculomics, the science of using the retina as a non-invasive window into systemic vascular health.
- **Clinical rationale:** the retina is the only place in the body where microvasculature can be directly imaged non-invasively; retinal vessel caliber, arteriolar narrowing, tortuosity, and arteriovenous (AV) nicking correlate with systemic atherosclerosis and vascular aging, both established cardiovascular risk markers.
- **How it predicts:** a deep embedding network (jury) extracts a learned feature vector per fundus image (`predict_preload_embed_jury()`), which a downstream regression head converts into `CVDRiskScore` and `Bioage`; `shap==0.50.0` is used for explainability/feature-attribution on top of this pipeline.
- **Ethnicity adjustment:** `CVDRiskScore_nonblack` recalibrates the score using the `ethnicity_model`'s black/non-black classification, since retinal-vascular-to-CVD-risk relationships are known to vary by ethnicity in the underlying training/validation cohorts.
- **Patient metadata fusion:** `Sex`, `Age` (from `DOB`), `SmokingStatus`, and `DiabetesStatus` are combined with the image-derived features, mirroring how traditional CVD risk calculators (e.g. Framingham, QRISK) blend clinical risk factors with additional biomarkers — here the biomarker is retinal-image-derived rather than a blood test.
- **Clinical use:** intended as a non-invasive, camera-based adjunct/screening signal for cardiovascular risk stratification, not a replacement for laboratory-based risk scores.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`cvd-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5.
- Container image: `tokueyesproduction.azurecr.io/models/cvd_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/cvd_model` (CPU-only, Xeon `Standard_D16s_v6`/`Standard_D32s_v6`).
- Exposes `POST /api/inference` on container port 80; called internally by the model-wrapper, which also passes it `ethnicity_model`'s output for the nonblack risk variant.
- readinessProbe/livenessProbe gate traffic until jury embedding/regression model weights are loaded.
- CI/CD: `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow`.

## 8. Testing & Quality

28 tests, 98% code coverage — highest per-model coverage of the 12 repos. Includes baseline comparison tests verifying inference output parity with the pre-upgrade model.

## 9. Security

SBOM v16, 0 vulnerabilities, risk score 0, last scan 4 Mar 2026. CycloneDX 1.6 SBOM generated by the shared `sbom.sh` and uploaded to Dependency-Track — see [common_ai_library.md](common_ai_library.md) §7 for the full scanning process.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

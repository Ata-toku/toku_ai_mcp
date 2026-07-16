# OptosCropping Model — AI Model Knowledge File

**Model:** OptosCropping
**GitHub Repository:** [optos_cropping_model](https://github.com/Toku-Eyes/optos_cropping_model)
**Local Path:** `Models\optos_cropping_model`
**Depends on:** [common_ai_library.md](common_ai_library.md) (shared base image and preprocessing pipeline)

---

## 1. Structure

- Inherits from the shared `common-ai-library` base image; no local `pip install` or `common/` folder.
- Model-specific files follow the same pattern as other models: `optos_cropping_compile.py`, `optos_cropping_model_launching.py`, `optos_cropping_image_preprocessing.py`, `optos_cropping_pipeline.py`.
- `ENTRYPOINT ["/app/gpu-entrypoint.sh"]`, working directory `/app/`.
- A `optos_cropping_model_request_example.json` template exists under [knowledge/templates/optos_cropping_model_request_example.json](../templates/optos_cropping_model_request_example.json) for reference on request payload shape.
- Not named in the source report as a multi-grader parallel-inference model — runs sequential jury inference by default.
- **Note:** This model is the 13th added to the epic (Section 14, row 13) but was **not** included in the Section 11 (Security/SBOM) or Section 13 (Testing/Coverage) tables in the source [CLBA-2339-Complete-Report.md](../CLBA-2339-Complete-Report.md); it is also absent from the §11 Model Inventory table in [AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md) — those metrics are not yet available for this repo.

## 2. Image Processing Steps

- Determines whether an OPTOS-camera image can be safely cropped to the standard fundus field of view before it is handed to QC/QC2 and the diagnostic models — the OPTOS ultra-widefield camera captures a much larger field than NW400/NW500, so a dedicated crop/validity check is needed.
- Preprocessing functions are expected to accept `img_data_dict` and `save_to_disk`, feeding the shared dual-mode pipeline (`fetch_base64_json_images()` in `common/image_preprocessing.py`):
  - **Disk mode** (default): intermediate images written to disk.
  - **Memory mode** (`SAVE_IMAGES_TO_DISK=false`): images stay as in-memory byte buffers throughout.
- Uses standard OpenCV 4.12.0 (`opencv-python-headless`) — no native legacy Gaussian blur extension required (unlike QC/QC2, this model performs geometric cropping/validity checks rather than blur-sensitive enhancement).

## 3. Input / Output Schema

- **Request**: shared model-wrapper contract — see [common_ai_library.md](common_ai_library.md) §2; consumes images where `camera == OPTOS`. See [optos_cropping_model_request_example.json](../templates/optos_cropping_model_request_example.json) for a dedicated standalone request example.
- **Response**: nested `qcoptoscropping` object inside each entry of the shared `QC_Grade` array (see [qc_model.md](qc_model.md) §3 for the full array shape):
  ```json
  "qcoptoscropping": { "Croppable": "yes", "Status": "ok", "Error": "" }
  ```
- `Croppable`: `yes`/`no` — whether the OPTOS image could be cropped to the standard field of view; `Status`: `ok` or an error state; `Error`: human-readable error string (empty on success).
- This model does not contribute the `grade` or `centered` fields in `QC_Grade` (those come from QC and QC2 respectively) — only the `qcoptoscropping` sub-object.

**Input attributes:** `camera` (must be `OPTOS`), `batchimages[].Image64` ultra-widefield fundus photograph — see [common_ai_library.md](common_ai_library.md) §2.

**Output attributes** (within `qcoptoscropping`, nested inside each `QC_Grade[]` entry):
- `Croppable` — `yes`/`no`, whether the image can be safely cropped to the standard field of view
- `Status` — `ok` or an error state
- `Error` — human-readable error string (empty on success)

## 4. Number of Graders (Jury Size)

- Not documented in either source document. Given its narrower scope (geometric crop validity, not a diagnostic classifier), this may be a single-model check rather than a jury ensemble — confirm against `_models/` in the `optos_cropping_model` repo.

## 5. Model Details

- **Keras 3 compatibility layer:** expected to follow the same `tf_keras` fallback pattern as other models for TF 2.20/Keras 3, if the crop-validity check uses a trained model rather than pure geometric/heuristic logic.
- **Parallel inference:** not called out for this model in the source report; runs sequential inference by default.
- **Inference enhancements:** expected to follow the shared pattern (probability outputs, `enable_timing`, startup diagnostics) but was not individually documented in the source report.
- Runs on shared Intel Xeon-optimized runtime (`TF_ENABLE_ONEDNN_OPTS=1`) — see [common_ai_library.md](common_ai_library.md) §3.

## 6. Medical / Functional Concept & Prediction

- **What it predicts:** whether an ultra-widefield OPTOS camera image can be validly cropped to the standard fundus field of view expected by the diagnostic models — a geometric/technical gatekeeping check, not a medical diagnosis.
- **Why it matters clinically:** the OPTOS camera captures a much wider retinal field than standard NW400/NW500 cameras; feeding an uncropped ultra-widefield image directly into models trained on standard-field photographs would distort scale and anatomical framing, degrading diagnostic accuracy.
- **How it predicts:** performs geometric/heuristic (and possibly model-based) validity checks on the OPTOS image to determine crop feasibility before standard preprocessing and diagnostic inference proceed.
- **Clinical use:** images marked non-croppable (`Croppable: no`) can be excluded from, or flagged as lower-confidence for, the standard-field diagnostic models.

## 7. Deployment & Services

- Deployed as an independent Kubernetes Deployment + Service (`optos-cropping-model`) in both `staging` and `production` namespaces — see [common_ai_library.md](common_ai_library.md) §5 (deployment configuration for this model has not been individually documented in the source materials; assumed to follow the same pattern as other model repos).
- Container image: expected at `tokueyesproduction.azurecr.io/models/optos_cropping_model:buildid-N` (GPU) or `tokuairegistry.azurecr.io/cpudistro/optos_cropping_model` (CPU-only) — not confirmed in source documents.
- Exposes `POST /api/inference` on container port 80 (assumed, consistent with other models); runs alongside QC/QC2 as part of the pre-diagnostic quality-gating stage for OPTOS-camera images specifically.
- CI/CD: assumed to use the same `staging-build-and-push.yaml` → `staging-deploy-to-k8.yaml` / `production-build-and-push.yaml` reusable workflows from `Toku-Eyes/central-workflow` as other models, though not individually confirmed.

## 8. Testing & Quality

Not reported in the source epic report (Section 13 covers only the other 12 repos). Follow up with the model owner to confirm test count and coverage.

## 9. Security

Not reported in the source epic report (Section 11 SBOM table covers only the other 12 repos). Follow up to confirm Dependency-Track scan status. See [common_ai_library.md](common_ai_library.md) §7 for the general CycloneDX/Dependency-Track scanning process that would apply once this repo is onboarded.

## 10. Platform & Runtime Upgrade

Same stack-wide upgrade as all models — see [common_ai_library.md](common_ai_library.md) §6.

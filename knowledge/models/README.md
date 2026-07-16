# AI Model Knowledge Files

Per-model knowledge files extracted from [../CLBA-2339-Complete-Report.md](../CLBA-2339-Complete-Report.md) and [../AI_INFRASTRUCTURE_ARCHITECTURE.md](../AI_INFRASTRUCTURE_ARCHITECTURE.md). Each file covers: **Structure**, **Image Processing Steps** (full 9-step pipeline / NW500 variant), **Input/Output Schema** (request + response JSON and explicit input/output attribute lists, sourced from the [templates](../templates/) folder), **Number of Graders (Jury Size)**, **Medical/Functional Concept & Prediction**, **Model Details**, **Deployment & Services** (Kubernetes), **Testing & Quality**, **Security** (SBOM/CycloneDX/Dependency-Track), and **Platform & Runtime Upgrade**.

| Model | File | Notes |
|-------|------|-------|
| common_ai_library (shared base) | [common_ai_library.md](common_ai_library.md) | Shared base image, hardware entrypoint, Xeon/oneDNN, parallel inference engine |
| R | [r_model.md](r_model.md) | Jury model, parallel inference |
| M | [m_model.md](m_model.md) | Jury model, parallel inference |
| SBP | [sbp_model.md](sbp_model.md) | |
| DZ | [dz_model.md](dz_model.md) | |
| TCHDL | [tchdl_model.md](tchdl_model.md) | |
| PA | [pa_model.md](pa_model.md) | |
| Ethnicity | [ethnicity_model.md](ethnicity_model.md) | |
| CVD | [cvd_model.md](cvd_model.md) | Jury model, parallel inference |
| HbA1c | [hba1c_model.md](hba1c_model.md) | Jury model, parallel inference |
| QC | [qc_model.md](qc_model.md) | Requires native OpenCV 4.1.2 Gaussian blur extension |
| QC2 | [qc2_model.md](qc2_model.md) | Requires native OpenCV 4.1.2 Gaussian blur extension |
| OptosCropping | [optos_cropping_model.md](optos_cropping_model.md) | Security/testing metrics not reported in source epic |

All models depend on `common_ai_library.md` for the base image, hardware-detection entrypoint, shared preprocessing pipeline, Kubernetes deployment topology, and SBOM/security scanning process.

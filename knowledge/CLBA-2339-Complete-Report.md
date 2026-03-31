# CLBA-2339 — Upgrade AI Models and Migration to GitHub

**Epic:** [CLBA-2339](https://tokueyes.atlassian.net/browse/CLBA-2339)  
**Project:** CLAiR/BioAge (CLBA)  
**Assignee:** Ata Moradi  
**Scope:** 11 AI Models + 1 Shared Base Library (`common_ai_library`)  
**Timeline:** November 2025 — March 2026  
**Status:** Ready For Test

---

## Table of Contents

1. [Platform & Runtime Upgrade](#1-platform--runtime-upgrade)
2. [Shared Base Image Architecture](#2-shared-base-image-architecture)
3. [Keras 3 Compatibility Layer](#3-keras-3-compatibility-layer)
4. [Native OpenCV 4.1.2 C++ Extension](#4-native-opencv-412-c-extension)
5. [Hardware Detection & Optimization Entrypoint](#5-hardware-detection--optimization-entrypoint)
6. [Intel Xeon CPU Optimization](#6-intel-xeon-cpu-optimization)
7. [Memory Mode / Disk I/O Optimization](#7-memory-mode--disk-io-optimization)
8. [Inference Enhancements](#8-inference-enhancements)
9. [Parallel Inference for Multi-Grader Models](#9-parallel-inference-for-multi-grader-models)
10. [Docker Architecture Changes](#10-docker-architecture-changes)
11. [Security & Vulnerability Remediation](#11-security--vulnerability-remediation)
12. [Source Control Migration — Bitbucket to GitHub](#12-source-control-migration--bitbucket-to-github)
13. [Testing & Quality](#13-testing--quality)
14. [Models & Jira Tracking](#14-models--jira-tracking)
15. [Repository Locations](#15-repository-locations)

---

## 1. Platform & Runtime Upgrade

The entire AI platform stack was upgraded from an aging NVIDIA-supplied container to a purpose-built base image.

| Component | Before | After |
|-----------|--------|-------|
| Base Image | `nvcr.io/nvidia/tensorflow:22.08-tf2-py3` (pre-built NVIDIA container) | Custom `common-ai-library` (built from `nvidia/cuda`) |
| Ubuntu | 20.04 | 24.04 |
| Python | 3.8 | 3.12 |
| CUDA / cuDNN | 11.7 / 8.x | 12.6.0 / 9.x |
| TensorFlow | 2.9.1 (bundled) | 2.20.0 |
| Keras | 2.9 (bundled inside TF) | 3.13.2 (standalone via `tf-keras==2.20.0`) |
| OpenCV | 4.1.2.30 | 4.12.0.88 (`opencv-python-headless`) |
| NumPy | 1.x (bundled) | 1.26.4 |
| Flask / Werkzeug | 2.3.2 / 2.3.7 | 3.1.3 / 3.1.4+ |
| Waitress | 3.0.0 | 3.0.2 |
| scikit-image | 0.21.0 | Removed (no longer needed) |

---

## 2. Shared Base Image Architecture

**Before:** Each of the 11 model repositories contained its own duplicate copy of a `common/` folder (7 Python modules), its own `requirements.txt`, test scripts, and build utilities. Any bug fix or dependency update required changing all 11 repos individually.

**After:** A new centralized repository (`common_ai_library`) was created. It builds a single Docker base image (`common-ai-library`) that contains:

- All shared Python modules (expanded from 7 to 10, plus a native C++ extension package)
- All Python dependencies pre-installed
- Test tooling (`pytest`, `coverage`, `conftest.py`) pre-installed
- Shared scripts (`runtests.sh`, `sbom.sh`, `gpu-entrypoint.sh`) pre-installed

Each model Dockerfile went from ~60 lines with full dependency installation to ~50 lines with `FROM ${BASE_IMAGE}` — no more `pip install`, no more duplicated `common/` folder.

**Files removed from every model repo:**
- `common/` folder (7 files)
- `requirements.txt`
- `runtests.sh`, `sbom.sh`, `sbom_post.sh`
- `compile.py` (replaced by model-specific `{model}_compile.py` using `tf_keras`)

**New shared modules added in `common_ai_library`** (did not exist in old `common/`):
- `inference_postprocesssing.py` — shared postprocessing logic
- `model_inference.py` — shared inference utilities
- `outbound_message_writing.py` — shared output formatting
- `opencv41_files/` — native C++ OpenCV 4.1.2 Gaussian blur extension (see Section 4)

---

## 3. Keras 3 Compatibility Layer

TensorFlow 2.20 ships with Keras 3, which has breaking API changes from Keras 2.x. To maintain backward compatibility without rewriting all model code:

- Added `tf-keras==2.20.0` as a compatibility shim
- All model compilation and launching files were updated to use:
  ```python
  try:
      import tf_keras
      from tf_keras.models import load_model
      from tf_keras.preprocessing.image import ImageDataGenerator
  except ImportError:
      from tensorflow.keras.models import load_model
      from tensorflow.keras.preprocessing.image import ImageDataGenerator
  ```
- Each model now has a dedicated `{model}_compile.py` and `{model}_model_launching.py` with this compatibility layer, replacing the old shared `compile.py` and `common/model_launching.py`.

---

## 4. Native OpenCV 4.1.2 C++ Extension

**Problem:** OpenCV upgraded from 4.1.2 to 4.12.0, but the internal Gaussian blur algorithm changed between these versions. The QC and QC2 models rely on `GaussianBlur` for image enhancement, and even sub-pixel differences in blur output produce different AI predictions — making the models output wrong results with OpenCV 4.12.

**Solution:** A native C++ extension was built that replicates the exact OpenCV 4.1.2 Gaussian blur algorithm, compiled for Python 3.12:
- `gaussian_blur_412_native.cpython-312-x86_64-linux-gnu.so` (Linux)
- `gaussian_blur_412_native.cp312-win_amd64.pyd` (Windows)
- Links against bundled `libopencv_core.so.4.1.2` and `libopencv_imgproc.so.4.1.2`

This ensures pixel-perfect enhancement output identical to the original OpenCV 4.1.2, while all other OpenCV operations use the modern 4.12.0 version. The extension is loaded automatically via `get_enhance_function()` in `common/image_preprocessing.py`.

**Validation:** Extensive testing (30+ test scripts in `important_files_for_upgrade_process/`) verified pixel-level equivalence between the native extension and original OpenCV 4.1.2.

---

## 5. Hardware Detection & Optimization Entrypoint

A new `gpu-entrypoint.sh` script was added to the base image, used as the Docker `ENTRYPOINT` for all models. It automatically:

- Detects CPU architecture (Intel XEON, AMD, generic) and core count
- Detects GPU availability via `nvidia-smi` and TensorFlow
- Sets optimization strategy:
  - **GPU mode:** Minimal CPU threads (OMP/MKL/OpenBLAS = 2), TensorFlow GPU memory growth enabled
  - **CPU mode:** All cores available, TensorFlow intra/inter-op threads auto-detected, oneDNN enabled
- Handles the `OMP_NUM_THREADS=0` edge case that crashes libgomp
- Respects any user-set environment variable overrides

**Before:** No hardware detection. GPU memory growth was set in Python code (`common/os_setup.py`) with no CPU optimization. Thread counts were never configured.

---

## 6. Intel Xeon CPU Optimization

### Target Hardware

Models are deployed on **Azure Dsv6-series** nodes — 5th Generation **Intel Xeon Platinum 8573C (Emerald Rapids)** processors with all-core turbo up to 3.0 GHz, full **AVX-512** and **AVX-VNNI** instruction set support, and no local temp disk (pure remote SSD).

| Node Type | vCPUs | RAM | Use Case |
|-----------|-------|-----|----------|
| `Standard_D16s_v6` | 16 | 64 GiB | Standard inference pods |
| `Standard_D32s_v6` | 32 | 128 GiB | High-throughput / parallel inference pods |

Kubernetes deployment manifests use `nodeAffinity` selectors to hard-pin AI model pods exclusively to these instance types, ensuring consistent hardware across all deployments.

### Old Approach (TF ≤ 2.15) vs New Approach (TF 2.20)

**Old approach:** Required installing `intel-extension-for-tensorflow` (ITEX) as a separate Python package. ITEX injected Intel-specific kernels, the oneDNN graph compiler, and low-level operator fusions (Conv+Bias+ReLU, MatMul+BatchNorm, etc.) into TensorFlow at runtime via its plugin API. Its env vars — including `ITEX_ONEDNN_GRAPH` — were only recognised when the ITEX package was loaded. ITEX's last stable release (v2.15.0.1) targeted TF 2.15 and explicitly does not support TF 2.17 or above.

**New approach:** ITEX is incompatible with TF 2.20. TensorFlow 2.20 ships with oneDNN deeply integrated natively — the same operator-level and graph-level optimisations ITEX previously injected are now part of the stock TF build. The single control is `TF_ENABLE_ONEDNN_OPTS=1`, which is **enabled by default** on modern Intel x86 CPUs. Testing confirmed that TF 2.20 with `TF_ENABLE_ONEDNN_OPTS=1` delivers equivalent efficiency to the ITEX-enabled older image — no extra package, no compatibility shim.

### How gpu-entrypoint.sh Enables This

At container startup, `gpu-entrypoint.sh` reads `/proc/cpuinfo` and classifies the CPU:

```
"xeon"  → CPU_TYPE = "Intel XEON"
"intel" → CPU_TYPE = "Intel"
"amd"   → CPU_TYPE = "AMD"
```

When no GPU is detected (CPU-only mode), the entrypoint switches to `CPU-OPTIMIZED` strategy: all thread-count limits are unset, allowing MKL and OpenMP to auto-use all available vCPUs, and `TF_ENABLE_ONEDNN_OPTS=1` is confirmed active.

### Practical Impact of oneDNN on Xeon

The Emerald Rapids architecture's AVX-512 instruction set allows oneDNN to run fused kernel operations in a single pass across 512-bit wide registers:

- **Conv2D + Bias + ReLU** fused into a single oneDNN primitive — eliminates intermediate memory writes between layers
- **MatMul + Bias** and **BatchNormalization** kernel fusion — reduces memory bandwidth pressure in the jury grader dense layers
- **BF16 math mode** available when explicitly enabled — can halve memory bandwidth for weights while maintaining FP32 accumulation accuracy
- Measured result: inference throughput on `Standard_D16s_v6` with oneDNN enabled matches the performance previously only achievable with ITEX on TF 2.15

A dedicated CPU distribution build pipeline (`build_push_cpudistro_vc1.sh`) builds and pushes optimised images for all 12 models to a separate ACR registry (`tokuairegistry.azurecr.io/cpudistro`), enabling Xeon-only deployments without CUDA runtime overhead.

---

## 7. Memory Mode / Disk I/O Optimization

**Before:** All image processing was disk-based. Every image was decoded, processed, and written to disk as intermediate files, then re-read from disk during inference.

**After:** A dual-mode pipeline was implemented:
- **Disk mode** (`SAVE_IMAGES_TO_DISK=true`, default): Original behavior, writes intermediate images to disk
- **Memory mode** (`SAVE_IMAGES_TO_DISK=false`): Images are kept as in-memory byte buffers throughout the entire pipeline — no disk writes between preprocessing and inference

This was implemented across the pipeline:
- `common/image_preprocessing.py` → `fetch_base64_json_images()` accepts `save_to_disk` parameter
- Each model's `{model}_image_preprocessing.py` → preprocessing functions accept `img_data_dict` and `save_to_disk`
- Each model's `{model}_model_launching.py` → `predict_preload_model()` decodes images from memory dict instead of using `ImageDataGenerator` file reads
- Each model's `{model}_pipeline.py` → orchestrates mode selection and cleanup

---

## 8. Inference Enhancements

- **Probability outputs:** Model inference now returns both class predictions and full probability arrays (`pred.tolist(), pred_prob.tolist()`), enabling confidence scoring. Previously only class labels were returned.
- **Timing instrumentation:** An optional `enable_timing` parameter logs per-model and per-step timing (batch preparation, `model.predict()`, argmax) with `[TIMING]` markers for performance analysis.
- **Startup diagnostics:** Each model now calls `printEnvVariables()` and `printOpenCVExtensionStatus()` at startup, logging environment variables and OpenCV extension status for easier debugging.

---

## 9. Parallel Inference for Multi-Grader Models

Several AI models (R, M, CVD, HbA1c, and others) use a **jury of multiple graders** — multiple neural network models run independently on the same image and their results are aggregated. Previously, these jury graders always ran sequentially.

A parallel inference mode was added to `common/model_inference.py` using Python's `ThreadPoolExecutor`, allowing all jury graders to run concurrently across multiple CPU threads. The feature is fully opt-in:

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `PARALLEL_INFERENCE` | `false` | Set to `true` to enable parallel jury inference |
| `PARALLEL_INFERENCE_THREADS` | `min(jury size, cpu_count())` | Max number of concurrent threads |

**How it works:** When `PARALLEL_INFERENCE=true`, each jury grader is dispatched to a separate thread via `ThreadPoolExecutor`, with each thread owning an independent `ImageDataGenerator` to avoid shared-state issues. Thread count defaults to `min(jury size, cpu_count())` but can be overridden. After inference completes, all generators and DataFrames are explicitly deleted and `gc.collect()` is called. Sequential execution remains the default fallback with identical behavior.

**Pros:**
- ~20% reduction in inference time observed in testing for multi-grader models
- Thread count is fully configurable per deployment via environment variable
- Zero behavior change when disabled — safe to roll out incrementally

**Cons:**
- Higher memory usage under parallel mode — each thread holds its own image batch and generator in memory simultaneously
- More threads means more concurrent TensorFlow sessions competing for GPU/CPU resources, which can reduce gains on memory-constrained nodes

---

## 10. Docker Architecture Changes

### Before (per-model Dockerfile)
```dockerfile
FROM nvcr.io/nvidia/tensorflow:22.08-tf2-py3 as base
RUN pip install --upgrade pip setuptools
RUN pip install -r requirements.txt
ADD common /root/common/
...
CMD [ "python3", "./main.py" ]
```

### After (per-model Dockerfile)
```dockerfile
ARG BASE_IMAGE=tokueyesproduction.azurecr.io/models/common-ai-library:buildid-13
FROM ${BASE_IMAGE} AS base
...
ENTRYPOINT ["/app/gpu-entrypoint.sh"]
CMD ["python3", "./main.py"]
```

Key changes:
- No more `pip install` in model Dockerfiles — all dependencies come from base image
- No more `ADD common/` — shared code comes from base image
- Working directory changed from `/root/` to `/app/`
- Added `ENTRYPOINT` for hardware detection (see Section 5)
- Added `Dockerfile.standalone` for independent builds without base image dependency
- Production stage unsets all threading environment variables to let the entrypoint decide based on hardware

---

## 11. Security & Vulnerability Remediation

**Before:** Each AI model container carried approximately **150 known vulnerabilities** (CVEs) originating from outdated Python packages, the aging NVIDIA base image, and system-level OS packages bundled with Ubuntu 20.04.

**After:** All 12 repositories report **zero vulnerabilities** as verified by Dependency-Track SBOM scans (CycloneDX 1.6 format, 4 Mar 2026). Risk score across all projects: **0**.

Key actions taken:

- **Python package upgrades** — All direct dependencies upgraded to patched versions: Keras 3.13.2, Flask 3.1.3, Werkzeug ≥3.1.4, cryptography ≥44.0.0, PyJWT ≥2.10.0, urllib3 ≥2.6.3, zipp ≥3.21.0
- **OS-level package remediation** — Ubuntu 24.04's apt pre-installs older versions of `cryptography`, `PyJWT`, `oauthlib`, `zipp`, and `httplib2` as system Python packages. These are explicitly removed during Docker build (`rm -rf /usr/lib/python3/dist-packages/...`) and replaced with pinned secure versions via pip
- **Base image replacement** — Moved from the NVIDIA-supplied `tensorflow:22.08-tf2-py3` image (which bundled hundreds of unpatched OS and Python packages) to a purpose-built image from `nvidia/cuda:12.6.0-cudnn-runtime-ubuntu24.04` with only the required packages installed
- **SBOM generation** — Every CI build produces a CycloneDX 1.6 Software Bill of Materials, automatically imported into Dependency-Track for continuous vulnerability monitoring
- **Policy compliance** — All 12 projects pass policy checks with 2 policy evaluations each and 0 policy violations

| Project | SBOM Version | Vulnerabilities | Risk Score | Last Scan |
|---------|-------------|-----------------|------------|-----------|
| common_ai_library | 5 | 0 | 0 | 3 Mar 2026 |
| r_model | 8 | 0 | 0 | 4 Mar 2026 |
| m_model | 7 | 0 | 0 | 4 Mar 2026 |
| sbp_model | 18 | 0 | 0 | 4 Mar 2026 |
| tchdl_model | 15 | 0 | 0 | 4 Mar 2026 |
| dz_model | 22 | 0 | 0 | 4 Mar 2026 |
| pa_model | 18 | 0 | 0 | 4 Mar 2026 |
| ethnicity_model | 19 | 0 | 0 | 4 Mar 2026 |
| cvd_model | 16 | 0 | 0 | 4 Mar 2026 |
| hba1c_model | 23 | 0 | 0 | 4 Mar 2026 |
| qc_model | 13 | 0 | 0 | 4 Mar 2026 |
| qc2_model | 9 | 0 | 0 | 4 Mar 2026 |

---

## 12. Source Control Migration — Bitbucket to GitHub

### 12.1 Repository Migration

All 11 AI model repositories and the `common_ai_library` were migrated from Bitbucket to GitHub (Toku-Eyes organisation). The migration preserved the complete history:

- **Full Git history** mirrored from Bitbucket to GitHub, including all branches and tags
- **Git LFS objects** migrated using `git lfs migrate import --everything` to ensure all large binary files (model weights `.data*`, `.pb`, `.hdf5`, `.index`, `.weights`, and native libraries `.dll`) were properly transferred
- **LFS re-import** was performed across all branches (`--everything` flag) to convert any files that had been committed directly into proper LFS-tracked objects
- All LFS objects were fetched from Bitbucket origin and pushed to the new GitHub remotes with `git lfs push github --all`
- Default branch renamed from `master` to `main` during migration

### 12.2 Removed — Bitbucket Pipelines & SonarQube

Each model repository previously contained a `bitbucket-pipelines.yml` (~211 lines) that defined the entire CI/CD pipeline on Bitbucket's self-hosted runners. This included steps for Docker builds, running tests, uploading test results to Azure Blob Storage, SonarQube code analysis, SBOM generation, and multi-step deployment pipelines for staging and production using Azure CLI and Bitbucket OIDC.

Also removed from each repo:
- `sonar-project.properties` — SonarQube project configuration (project key, Python version, coverage report paths, exclusions)
- `sbom_post.sh` — post-build SBOM upload script tied to Bitbucket artifacts

### 12.3 Added — GitHub Actions Workflows

A new set of GitHub Actions workflows was created for all AI model repositories. These workflows follow a centralized pattern: each model repo contains lightweight workflow files that call **reusable workflows** from the `Toku-Eyes/central-workflow` repository, keeping CI/CD logic DRY and centrally managed.

Five workflow files were added to each model repo:

1. **`pr.yaml`** — Pull Request Pipeline
   - Triggers on: pull request open/sync/reopen, push to non-main branches, manual dispatch
   - Runs code quality checks (flake8 linting, black formatting)
   - Calls central workflow `aimodel-build-test-codecoverage-sbom.yaml` to build the Docker image, run tests, generate code coverage, and produce SBOM — all in a single reusable job

2. **`staging-build-and-push.yaml`** — Staging Build & Push
   - Manual trigger with optional custom image tag (defaults to `buildid-{run_number}`)
   - Calls central workflow `docker-build-push-dev.yaml` to build and push the Docker image to the staging Azure Container Registry (ACR)

3. **`staging-deploy-to-k8.yaml`** — Staging Deploy to Kubernetes
   - Manual trigger with required version input
   - Auto-derives the Kubernetes deployment name from the repo name (e.g., `qc2_model` → `qc2model-deployment`)
   - Calls central workflow `staging-deploy-to-k8.yaml` to update the staging Kubernetes deployment

4. **`production-build-and-push.yaml`** — Production Build & Push
   - Triggers on: manual dispatch with version, or Git tag push matching `v*.*.*`
   - Calls central workflow `docker-build-push.yaml` to build and push to the production ACR
   - Automatically creates a GitHub Release with auto-generated release notes after successful build

5. **`fast-deploy-to-staging.yaml`** — Fast Deploy to Staging
   - Manual trigger with optional image tag
   - Combines build + deploy in one workflow: calls `docker-build-push-dev.yaml` then immediately calls `staging-deploy-to-k8.yaml`
   - Designed for rapid iteration during development — one click to build, push, and deploy

### 12.4 Central Workflow Architecture

Unlike the old Bitbucket approach where each repo contained the full CI/CD logic inline (211+ lines), the new GitHub setup uses the `Toku-Eyes/central-workflow` repository as a single source of truth. Model repos contain only thin workflow callers (10–30 lines each) that pass parameters and inherit secrets. This means CI/CD changes (e.g., updating the Docker build process, adding a new deployment step) are made once in the central repo and automatically apply to all 12 AI model repositories.

---

## 13. Testing & Quality

Comprehensive test suites were written or expanded for all 12 repositories. All tests run inside Docker containers using the same base image as production. Unit tests include baseline comparison tests that verify inference outputs match pre-upgrade results, ensuring zero regression from the platform changes.

| Repository | Tests | Coverage |
|------------|-------|----------|
| common_ai_library | 193 | 96% |
| cvd_model | 28 | 98% |
| hba1c_model | 20 | 95% |
| sbp_model | 14 | 95% |
| tchdl_model | 14 | 95% |
| m_model | 12 | 91% |
| r_model | 12 | 91% |
| ethnicity_model | 10 | 87% |
| dz_model | 14 | 86% |
| qc_model | 8 | 86% |
| qc2_model | 18 | 86% |
| pa_model | 14 | 85% |

All 12 repositories achieve >85% code coverage.

---

## 14. Models & Jira Tracking

All tasks are linked to epic [CLBA-2339](https://tokueyes.atlassian.net/browse/CLBA-2339) and assigned to Ata Moradi.

| # | Model | Parent Task | Subtask | GitHub Repository | Branch |
|---|-------|-------------|---------|-------------------|--------|
| 1 | common_ai_library | [CLBA-2461](https://tokueyes.atlassian.net/browse/CLBA-2461) | [CLBA-2462](https://tokueyes.atlassian.net/browse/CLBA-2462) | [common_ai_library](https://github.com/Toku-Eyes/common_ai_library) | `main` (merged) |
| 2 | R | [CLBA-2400](https://tokueyes.atlassian.net/browse/CLBA-2400) | [CLBA-2401](https://tokueyes.atlassian.net/browse/CLBA-2401) | [r_model](https://github.com/Toku-Eyes/r_model) | `CLBA-2401-update-r-model-subtask-github` |
| 3 | M | [CLBA-2410](https://tokueyes.atlassian.net/browse/CLBA-2410) | [CLBA-2411](https://tokueyes.atlassian.net/browse/CLBA-2411) | [m_model](https://github.com/Toku-Eyes/m_model) | `CLBA-2411-update-m-model-subtask-github` |
| 4 | SBP | [CLBA-2412](https://tokueyes.atlassian.net/browse/CLBA-2412) | [CLBA-2420](https://tokueyes.atlassian.net/browse/CLBA-2420) | [sbp_model](https://github.com/Toku-Eyes/sbp_model) | `CLBA-2420-update-sbp-model-subtask-github` |
| 5 | DZ | [CLBA-2413](https://tokueyes.atlassian.net/browse/CLBA-2413) | [CLBA-2425](https://tokueyes.atlassian.net/browse/CLBA-2425) | [dz_model](https://github.com/Toku-Eyes/dz_model) | `CLBA-2425-update-dz-model-subtask-github` |
| 6 | TCHDL | [CLBA-2414](https://tokueyes.atlassian.net/browse/CLBA-2414) | [CLBA-2427](https://tokueyes.atlassian.net/browse/CLBA-2427) | [tchdl_model](https://github.com/Toku-Eyes/tchdl_model) | `CLBA-2427-update-tchdl-model-subtask-github` |
| 7 | PA | [CLBA-2415](https://tokueyes.atlassian.net/browse/CLBA-2415) | [CLBA-2426](https://tokueyes.atlassian.net/browse/CLBA-2426) | [pa_model](https://github.com/Toku-Eyes/pa_model) | `CLBA-2426-update-pa-model-subtask-github` |
| 8 | Ethnicity | [CLBA-2416](https://tokueyes.atlassian.net/browse/CLBA-2416) | [CLBA-2423](https://tokueyes.atlassian.net/browse/CLBA-2423) | [ethnicity_model](https://github.com/Toku-Eyes/ethnicity_model) | `CLBA-2423-update-ethnicity-model-subtask-github` |
| 9 | CVD | [CLBA-2417](https://tokueyes.atlassian.net/browse/CLBA-2417) | [CLBA-2424](https://tokueyes.atlassian.net/browse/CLBA-2424) | [cvd_model](https://github.com/Toku-Eyes/cvd_model) | `CLBA-2424-update-cvd-model-subtask-github` |
| 10 | HbA1c | [CLBA-2418](https://tokueyes.atlassian.net/browse/CLBA-2418) | [CLBA-2421](https://tokueyes.atlassian.net/browse/CLBA-2421) | [hba1c_model](https://github.com/Toku-Eyes/hba1c_model) | `main` (merged) |
| 11 | QC | [CLBA-2419](https://tokueyes.atlassian.net/browse/CLBA-2419) | [CLBA-2422](https://tokueyes.atlassian.net/browse/CLBA-2422) | [qc_model](https://github.com/Toku-Eyes/qc_model) | `CLBA-2422-update-qc-model-subtask-github` |
| 12 | QC2 | [CLBA-2340](https://tokueyes.atlassian.net/browse/CLBA-2340) | [CLBA-2341](https://tokueyes.atlassian.net/browse/CLBA-2341) | [qc2_model](https://github.com/Toku-Eyes/qc2_model) | `CLBAXX-update-qc2-model-subtask-github` |
| 13 | OptosCropping | [CLBA-2433](https://tokueyes.atlassian.net/browse/CLBA-2433) | [CLBA-2434](https://tokueyes.atlassian.net/browse/CLBA-2434) | [optos_cropping_model](https://github.com/Toku-Eyes/optos_cropping_model) | `CLBA-2434-update-optoscropping-model-subtask-github` |

Additionally: [CLBA-2386](https://tokueyes.atlassian.net/browse/CLBA-2386) — *Investigation on Generalised AI Repository Structure* (completed — informed the shared base image design).

---

## 15. Repository Locations

All model repositories are located at:
```
C:\Users\AtaMoradi\Desktop\Tokueyes\Projects\Models\
```

| Repository | Local Path |
|------------|-----------|
| common_ai_library | `Models\common_ai_library` |
| r_model | `Models\r_model` |
| m_model | `Models\m_model` |
| sbp_model | `Models\sbp_model` |
| dz_model | `Models\dz_model` |
| tchdl_model | `Models\tchdl_model` |
| pa_model | `Models\pa_model` |
| ethnicity_model | `Models\ethnicity_model` |
| cvd_model | `Models\cvd_model` |
| hba1c_model | `Models\hba1c_model` |
| qc_model | `Models\qc_model` |
| qc2_model | `Models\qc2_model` |
| optos_cropping_model | `Models\optos_cropping_model` |

---

**Created:** January 23, 2026  
**Last Updated:** March 10, 2026

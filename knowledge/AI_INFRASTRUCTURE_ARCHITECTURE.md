# TokuEyes AI Infrastructure — Architecture Knowledge Document

> **Version**: 1.0  
> **Last Updated**: July 2025  
> **Scope**: common_ai_library base image, 11 model repositories, shared modules, Docker build strategy, testing infrastructure

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Base Image: common_ai_library](#3-base-image-common_ai_library)
   - [3.1 Multi-Stage Docker Build](#31-multi-stage-docker-build)
   - [3.2 Technology Stack](#32-technology-stack)
   - [3.3 Package Management (requirements.txt)](#33-package-management-requirementstxt)
   - [3.4 What Ships in the Base Image](#34-what-ships-in-the-base-image)
4. [Shared Common Modules](#4-shared-common-modules)
   - [4.1 webserver.py — Flask + Waitress + Prometheus](#41-webserverpy--flask--waitress--prometheus)
   - [4.2 model_launching.py — Model Loading & Jury Prediction](#42-model_launchingpy--model-loading--jury-prediction)
   - [4.3 model_inference.py — Inference Orchestration](#43-model_inferencepy--inference-orchestration)
   - [4.4 image_preprocessing.py — Image Pipeline](#44-image_preprocessingpy--image-pipeline)
   - [4.5 inference_postprocesssing.py — Prediction Aggregation](#45-inference_postprocesssingpy--prediction-aggregation)
   - [4.6 outbound_message_writing.py — Response Formatting](#46-outbound_message_writingpy--response-formatting)
   - [4.7 os_setup.py — OS & GPU Configuration](#47-os_setuppy--os--gpu-configuration)
   - [4.8 directory_setup.py — Working Directory Creation](#48-directory_setuppy--working-directory-creation)
   - [4.9 logging.py — Structured Logging with Correlation ID](#49-loggingpy--structured-logging-with-correlation-id)
   - [4.10 version.py — Version & Environment Reporting](#410-versionpy--version--environment-reporting)
   - [4.11 OpenCV 4.1.2 Native Extension](#411-opencv-412-native-extension)
5. [Shared Scripts](#5-shared-scripts)
   - [5.1 gpu-entrypoint.sh — Hardware Detection & Optimization](#51-gpu-entrypointsh--hardware-detection--optimization)
   - [5.2 compile.py — SavedModel → H5 Conversion](#52-compilepy--savedmodel--h5-conversion)
   - [5.3 runtests.sh — Generic Test Runner](#53-runtestssh--generic-test-runner)
   - [5.4 runtests_library.sh — Library Test Runner](#54-runtests_librarysh--library-test-runner)
   - [5.5 sbom.sh — Software Bill of Materials](#55-sbomsh--software-bill-of-materials)
6. [Model Repository Pattern](#6-model-repository-pattern)
   - [6.1 Standard Directory Layout](#61-standard-directory-layout)
   - [6.2 Model Dockerfile Multi-Stage Build](#62-model-dockerfile-multi-stage-build)
   - [6.3 Model-Specific Customization Points](#63-model-specific-customization-points)
   - [6.4 Pipeline Execution Flow](#64-pipeline-execution-flow)
7. [Inference Architecture](#7-inference-architecture)
   - [7.1 Request Lifecycle](#71-request-lifecycle)
   - [7.2 Jury Ensemble System](#72-jury-ensemble-system)
   - [7.3 Eye-Level Aggregation](#73-eye-level-aggregation)
   - [7.4 Parallel Inference](#74-parallel-inference)
8. [Testing Infrastructure](#8-testing-infrastructure)
   - [8.1 Docker-Based Testing](#81-docker-based-testing)
   - [8.2 Coverage Configuration](#82-coverage-configuration)
   - [8.3 Test Results](#83-test-results)
9. [Environment Variables Reference](#9-environment-variables-reference)
10. [Security Practices](#10-security-practices)
11. [Model Inventory](#11-model-inventory)
12. [Data Flow Diagram](#12-data-flow-diagram)

---

## 1. Executive Summary

TokuEyes operates an AI platform that analyzes retinal fundus images for medical screening. The infrastructure follows a **shared base image** pattern:

- **`common_ai_library`** produces a Docker **base image** containing all shared Python dependencies, common modules, scripts, and a native OpenCV 4.1.2 C++ extension.
- **11 model repositories** each build `FROM` this base image, adding only model-specific weights, pipeline code, and `extra-requirements.txt` packages.
- All models serve predictions via a standardized **Flask + Waitress** web server with **Prometheus** metrics, exposed on port 80 (API) and port 8888 (metrics).
- Models use a **jury ensemble** system (multiple trained models vote) with image→eye→patient level aggregation.

This architecture ensures consistent dependencies, minimal image size duplication, and uniform deployment patterns across all AI models.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Container Registry (ACR)                     │
│  tokueyesproduction.azurecr.io/models/common-ai-library:buildid-N │
└────────────────────────────┬────────────────────────────────────┘
                             │  FROM ${BASE_IMAGE}
        ┌────────┬───────────┼───────────┬────────────┬──────────┐
        ▼        ▼           ▼           ▼            ▼          ▼
   ┌─────────┐┌────────┐┌────────┐┌──────────┐┌──────────┐┌─────────┐
   │dz_model ││hba1c   ││cvd     ││ethnicity ││sbp_model ││ ... x11 │
   │(drusen) ││(HbA1c) ││(cardio)││(ethnic)  ││(bloodpr) ││ models  │
   └─────────┘└────────┘└────────┘└──────────┘└──────────┘└─────────┘
        │         │          │          │           │           │
        └─────────┴──────────┴──────────┴───────────┴───────────┘
                    All inherit from common_ai_library:
                    • common/ Python modules
                    • gpu-entrypoint.sh
                    • runtests.sh + compile.py
                    • OpenCV 4.1.2 native extension
                    • Flask/Waitress/Prometheus stack
```

---

## 3. Base Image: common_ai_library

### 3.1 Multi-Stage Docker Build

The base image uses a **4-stage** Docker build strategy:

| Stage | Base Image | Purpose |
|-------|-----------|---------|
| **builder** | `nvidia/cuda:12.6.0-cudnn-devel-ubuntu24.04` | Install Python packages + build tools (discarded in final image) |
| **base** | `nvidia/cuda:12.6.0-cudnn-runtime-ubuntu24.04` | Runtime image — copies packages from builder, installs common code |
| **sbom** | extends `base` | Generates CycloneDX Software Bill of Materials |
| **test** | extends `base` | Adds `runtests_library.sh` + `tests/`, runs with `gpu-entrypoint.sh` |

The **builder** stage uses the `devel` CUDA variant (includes headers/compilers), while the **base** stage uses the much smaller `runtime` variant. Python packages compiled in builder are copied to base via:

```dockerfile
COPY --from=builder /usr/local/lib/python3.12/dist-packages /usr/local/lib/python3.12/dist-packages
COPY --from=builder /usr/local/bin /usr/local/bin
```

**Key optimization**: Build tools and headers stay in the builder stage and never enter the production image.

### 3.2 Technology Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Ubuntu | 24.04 (Noble) | Base OS |
| CUDA | 12.6.0 + cuDNN | GPU acceleration |
| Python | 3.12 | Runtime (default in Ubuntu 24.04) |
| TensorFlow | 2.20.0 | Deep learning framework |
| tf-keras | 2.20.0 | Legacy Keras 2 API (model compatibility) |
| Keras | 3.13.2 | Keras 3 API |
| NumPy | 1.26.4 | Numerical computing |
| Pandas | 2.3.3 | Data manipulation |
| OpenCV | 4.12.0.88 (headless) | Image processing (runtime) |
| OpenCV | 4.1.2 (native C++) | Pixel-perfect GaussianBlur via compiled extension |
| scikit-image | 0.25.2 | Additional image processing |
| Flask | 3.1.3 | HTTP web framework |
| Waitress | 3.0.2 | Production WSGI server |
| Prometheus | 0.21.0 + exporter 0.23.1 | Metrics collection |

### 3.3 Package Management (requirements.txt)

All shared Python dependencies are centrally managed in `common_ai_library/requirements.txt`. This single file drives the entire dependency tree for all 11 models:

```
# ML Core
tensorflow==2.20.0
tf-keras==2.20.0
keras==3.13.2
numpy==1.26.4
pandas==2.3.3
h5py==3.15.1

# Web Server
Flask==3.1.3
Flask-Cors==6.0.0
waitress==3.0.2
prometheus-client==0.21.0
prometheus-flask-exporter==0.23.1

# Serialization
marshmallow-dataclass==8.7.1
protobuf>=6.33.5

# Security (pinned minimums)
cryptography>=44.0.0
PyJWT>=2.10.0
httplib2>=0.22.0
zipp>=3.21.0
importlib-metadata>=8.0.0
oauthlib>=3.2.2
urllib3>=2.6.3
Werkzeug>=3.1.4
```

Additionally, the Dockerfile installs these outside requirements.txt (with `--no-deps` to avoid overwriting pinned transitive deps):
- `opencv-python-headless==4.12.0.88`
- `scikit-image==0.25.2`

**Model-specific packages** are handled via `extra-requirements.txt` in each model repo (see §6.3).

### 3.4 What Ships in the Base Image

The base stage (`--target base`) includes:

| Asset | Path | Purpose |
|-------|------|---------|
| Python packages | `/usr/local/lib/python3.12/dist-packages/` | All from requirements.txt |
| Common modules | `/app/common/` | 10 Python modules (see §4) |
| OpenCV 4.1.2 libs | `/usr/local/lib/libopencv_*.so.4.1.2` | C++ shared objects for native extension |
| Native extension | `/usr/local/lib/python3.12/dist-packages/gaussian_blur_412_native.*.so` | Compiled Python→C++ bridge |
| gpu-entrypoint.sh | `/app/gpu-entrypoint.sh` | Hardware detection & thread optimization |
| runtests.sh | `/app/runtests.sh` | Generic test runner (inherited by model images) |
| sbom.sh | `/app/sbom.sh` | SBOM generation script |
| compile.py | `/app/compile.py` | SavedModel→H5 converter |
| pytest + coverage | installed via pip | Test framework (shared across all model test stages) |

**NOT in base stage** (test only): `runtests_library.sh`, `tests/`

---

## 4. Shared Common Modules

All modules live in `/app/common/` inside the base image. Every model inherits them automatically.

### 4.1 webserver.py — Flask + Waitress + Prometheus

**Location**: `common/webserver.py`

Provides a standardized HTTP server pattern used identically by all 11 models.

**Routes**:
| Route | Method | Purpose |
|-------|--------|---------|
| `/healthz` | GET | Kubernetes liveness probe |
| `/startup` | GET | Kubernetes startup probe |
| `/` | GET | Basic health check |
| `/api/inference` | POST | Main inference endpoint |

**Key function**: `initWebserver(func_process_json, iPort, prefix)`
- **`func_process_json`**: Model-specific callback that receives JSON and returns results
- **`iPort`**: Port for Windows development (Linux always uses 80)
- **`prefix`**: Prometheus metric prefix (e.g., `dz`, `hba1c`)

**Prometheus Metrics** (exposed on port 8888):
| Metric | Type | Description |
|--------|------|-------------|
| `{prefix}_processed_seconds` | Summary | Time spent processing requests |
| `{prefix}_processed` | Counter | Total requests processed |
| `{prefix}_current` | Gauge | Currently processing requests |
| `{prefix}_waitress_task_queue_size_total` | Gauge | Waitress task queue depth |
| `{prefix}_waitress_task_active_total` | Gauge | Active Waitress tasks |
| `{prefix}_waitress_task_threads_total` | Gauge | Waitress thread count |

**Implementation detail**: Waitress's `create_server` function is monkey-patched to extract task dispatcher metrics.

**Request lifecycle in `/api/inference`**:
1. Increment `current` gauge
2. Set correlation ID from `CorrelationID` header
3. Deserialize JSON body
4. Call model-specific `process_json()` callback
5. Observe request time, increment processed counter, decrement current gauge
6. Run `gc.collect()` to free memory
7. Return results

**Utility**: `cleanSingleFolder(img_dir, folder)` — cleans up generated image files after inference.

### 4.2 model_launching.py — Model Loading & Jury Prediction

**Location**: `common/model_launching.py`

Core module for loading TensorFlow/Keras models and running jury-based predictions.

#### Custom Layers

**`SafeLambda`** (extends `Lambda`):
- Handles `bad marshal data (unknown type code)` errors from cross-Python-version `.h5` files
- Specifically targets InceptionResNetV2 models with `scaled_residual` Lambda layers
- Re-creates the Lambda with inline `lambda x: x * 0.1` when deserialization fails

**`FixedDropout`**:
- EfficientNet compatibility layer
- Imports from `efficientnet.model.FixedDropout` when available
- Falls back to manual implementation that properly handles `noise_shape`

#### `load_model_from_tf_model_files(model_path, embedding_layer=None)`

Loads a model from disk with cross-version compatibility:

1. Determines format: `.h5`/`.hdf5` (HDF5) or directory (SavedModel)
2. Loads with `custom_objects={'SafeLambda': SafeLambda, 'FixedDropout': FixedDropout}`
3. Uses `tf_keras.models.load_model()` (falls back to `tf.keras.models.load_model()`)
4. If `embedding_layer` is specified → extracts a sub-model from input to the named layer, cleans up full model via `gc.collect()`
5. Calls `model.predict(np.zeros(...))` as warmup to compile the computation graph

#### `predict_preload_jury(models, img_list, img_dir, img_size, mini_batch_size)`

Ensemble prediction using a list of loaded models (the "jury"):

1. Creates `ImageDataGenerator(rescale=1./255)` and `flow_from_dataframe`
2. Allocates `pred_conf[jury_count, image_count, class_count]` numpy array
3. **Sequential mode** (default): Each model predicts in turn with `generator.reset()` between models
4. **Parallel mode** (`PARALLEL_INFERENCE=true`): Uses `ThreadPoolExecutor` with per-thread generators
5. Returns the 3D array `[jury_index, image_index, class_index]`

#### `predict_preload_model(model, img_list, img_dir, img_size, mini_batch_size)`

Single-model prediction returning `argmax` class labels as a list.

### 4.3 model_inference.py — Inference Orchestration

**Location**: `common/model_inference.py`

Higher-level wrappers that coordinate the model launching functions.

#### `infer_models(model_grader_jury, img_name_list, img_dir, img_size, mini_batch_size)`
- Calls `predict_preload_jury()` for standard classification models
- Returns `pred_conf` array or empty array if no images

#### `infer_embed_models(model_grader_jury, img_name_list, img_dir, img_size, mini_batch_size)`
- For models with **dual outputs** (embedding + classification)
- Calls `predict_preload_embed_jury()` which handles multi-output models
- Returns `(embed_conf, pred_conf)` — embeddings and predictions separately
- Includes explicit `gc.collect()` after prediction to prevent memory leaks

#### `predict_preload_embed_jury(models, img_list, img_dir, img_size, mini_batch_size)`
- Allocates separate arrays: `embed_conf[jury, images, embedding_dim]` and `pred_conf[jury, images, classes]`
- Supports both parallel and sequential inference (same pattern as `predict_preload_jury`)
- Cleans up generators via `del generator, data_gen, df; gc.collect()`

### 4.4 image_preprocessing.py — Image Pipeline

**Location**: `common/image_preprocessing.py`

Comprehensive retinal image preprocessing module.

#### `fetch_base64_json_images(request_json_batch, img_dir, save_to_disk=True)`

Decodes base64-encoded images from the API request JSON:

- Iterates `request_json_batch['batch']` elements
- Each element has: `Image64` (base64 string), `ImageName`, `ImagePosition` (left/right)
- `ImagePosition`: `"left"` → 0, else → 1
- **Disk mode** (`save_to_disk=True`): Writes PNG to `img_dir['img_dir']`
- **Memory mode** (`save_to_disk=False`): Stores PNG bytes in `img_data_dict`
- Returns: `(img_name_list, id_dict, img_position_list)` or `(..., img_data_dict)` in memory mode

#### `crop_img(img, threshold=30)`

Crops blank/black background from retinal fundus images:
- Converts to grayscale, thresholds to find non-black region
- Finds bounding rectangle of non-zero pixels
- Crops and pads to square

#### `pass_image_resolution_check(img, threshold)`

Gates images by minimum resolution (typically 800px or 100px).

#### `enhance_img_native(src_img, alpha=4, beta=-4, gamma=128, scale_ratio=10)`

Unsharp mask enhancement using native OpenCV 4.1.2 GaussianBlur:

1. Calculates kernel size: `ksize = ceil(scale_ratio * 3) * 2 + 1`
2. Applies `GaussianBlur_412_Native(src_img, ksize, scale_ratio)` via C++ extension
3. Applies `cv2.addWeighted(src_img, alpha, blurred_img, beta, gamma)` for unsharp mask

#### `get_enhance_function()`

Factory that returns the enhancement function. Requires native C++ extension — raises `ImportError` if unavailable.

#### `preprocess_image(img_name_list, img_dir, read_type, img_data_dict, save_to_disk)`

Standard preprocessing pipeline used by most models:

1. Read image (from disk or memory)
2. Resolution check (800px minimum)
3. Crop blank background
4. Resolution check (100px minimum — post-crop)
5. Resize to 1200×1200
6. Write/read cycle (disk or memory — simulates JPEG compression normalization)
7. Resize to 800×800
8. Apply GaussianBlur enhancement via native OpenCV 4.1.2
9. Save enhanced 800×800 image for model inference

#### `preprocess_image_nw500_v2(img_name_list, img_dir, read_type, img_data_dict)`

NW500 camera variant (used by dz_model and others for specific camera types):

1. Read → resolution check → crop → resize to 1200×1200
2. Apply salt-and-pepper noise (`apply_noise`)
3. Apply median filter (`apply_filter`)
4. Save filtered image

**Debug mode** (`DEBUG_SAVE_STEPS=true`): Saves intermediate images at each step for comparison.

### 4.5 inference_postprocesssing.py — Prediction Aggregation

**Location**: `common/inference_postprocesssing.py`

Aggregates image-level predictions to eye-level and patient-level results.

#### `postprocess_inference(pred_conf, left_right, img_name_list, grade_type=None)`

Standard classification post-processing:

1. Groups images by patient visit + left/right eye
2. For each eye: takes **mean across jury** then **argmax** for each image
3. Eye prediction = **max** of image-level predictions
4. Returns `[eye_predictions, visit_groups, eye_lr_mapping, ...]`

#### `eye_max_jury_mean(pred_conf, left_right_list)`

Helper function: For each eye (left/right), calculates `max(mean_across_jury(argmax(per_image)))`.

#### `postprocess_classification_embedding_inference(...)`

Same aggregation as above but also extracts **mean embeddings** per eye from the embedding model output.

#### `postprocess_regression_embedding_inference(...)`

For regression models (e.g., HbA1c, SBP): aggregates regression values + embeddings per eye.

### 4.6 outbound_message_writing.py — Response Formatting

**Location**: `common/outbound_message_writing.py`

Formats inference results into the JSON response contract.

#### `format_outbound_message(id_dict, img_name_list, lr_list, pred, pred_conf, grade_type)`

Standard classification response:
- `grade_type` options: `'aamd'`, `'dz'`, `'pa'` → maps numeric predictions to labels (e.g., `{0: 'none/small', 1: 'medium', 2: 'large'}` for dz)
- If `grade_type` is None → returns raw numeric values
- Response structure:
  ```json
  {
    "patient": {"prediction": "medium"},
    "left_eye": {"prediction": "none/small"},
    "right_eye": {"prediction": "large"},
    "images": [
      {"id": "...", "left_right": "left", "prediction": "medium", "probability": [[...]]}
    ],
    "version": "1.2.3"
  }
  ```

#### `format_regression_embedding_outbound_message(id_dict, img_name_list, lr_list, pred, regression_pred, embedding_pred)`

For regression + embedding models:
- Image `prediction` = mean regression value across jury
- Image `embedding` = mean embedding vector across jury (as list)

### 4.7 os_setup.py — OS & GPU Configuration

**Location**: `common/os_setup.py`

#### `load_set_os_config_para(is_test=False)`

1. Determines `base_path` from `__file__` parent directory
2. Windows (`os.name == 'nt'`): Sets `CUDA_VISIBLE_DEVICES=-1` (forces CPU), `path_split = '\\'`
3. Linux (`os.name == 'posix'`): Enables GPU memory growth via `tf.config.experimental.set_memory_growth(gpu, True)` for each GPU, `path_split = '/'`
4. Returns `(os_name, base_path, path_split)`

### 4.8 directory_setup.py — Working Directory Creation

**Location**: `common/directory_setup.py`

#### `create_path_if_not_exists(path)`
Creates a directory (and parents) if it doesn't exist.

#### `create_working_directory(directory)`
Takes a dictionary of `{name: path}` and creates all directories. Used by each model's `*_directory_setup.py` to create the image processing directory tree.

### 4.9 logging.py — Structured Logging with Correlation ID

**Location**: `common/logging.py`

#### `InitLogging()`
- Configures Python logging with `StreamHandler(sys.stdout)` for Docker compatibility
- Format: `MM/DD/YYYY HH:MM:SS  PID     module               correlationid message`
- Installs a custom `LogRecordFactory` that injects `correlationid` into every log record

#### `setCorrellationID(id)`
- Sets a module-level correlation ID that appears in all subsequent log messages
- Called per-request in `webserver.py` from the `CorrelationID` HTTP header
- Enables request tracing across distributed systems

### 4.10 version.py — Version & Environment Reporting

**Location**: `common/version.py`

#### `setVersion(results)`
Adds `results["version"]` from `TERELEASE` environment variable (set at Docker build time via `BUILD_TERELEASE` arg).

#### `printVersion()`
Logs the container version at startup.

#### `printEnvVariables()`
Logs the state of all runtime configuration environment variables:
- `ENABLE_TIMING_LOGS`, `SAVE_IMAGES_TO_DISK`, `DEBUG_SAVE_STEPS`
- `PARALLEL_INFERENCE`, `PARALLEL_INFERENCE_THREADS`

#### `printOpenCVExtensionStatus()`
Checks and logs whether the native OpenCV 4.1.2 C++ extension loaded successfully, including extension version and OpenCV version.

### 4.11 OpenCV 4.1.2 Native Extension

**Location**: `common/opencv41_files/`

**Why this exists**: The AI models were trained with OpenCV 4.1.2's GaussianBlur implementation. Newer OpenCV versions produce slightly different floating-point results (due to kernel coefficient calculation differences). Even 1-pixel differences compound through the enhancement pipeline and can degrade model accuracy. The native extension ensures **100% pixel-perfect** compatibility with training-time preprocessing.

**Files**:

| File | Platform | Purpose |
|------|----------|---------|
| `gaussian_blur_412_native.cpython-312-x86_64-linux-gnu.so` | Linux | Compiled C++ extension (production) |
| `gaussian_blur_412_native.cp312-win_amd64.pyd` | Windows | Compiled C++ extension (development) |
| `libopencv_core.so.4.1.2` | Linux | OpenCV 4.1.2 core shared library |
| `libopencv_imgproc.so.4.1.2` | Linux | OpenCV 4.1.2 image processing shared library |
| `opencv_world412.dll` | Windows | OpenCV 4.1.2 monolithic DLL |
| `gaussian_blur_412_native_wrapper.py` | All | Python wrapper with validation |
| `gaussian_blur_412_fixedpoint.py` | All | Pure-Python fallback (not used in production) |

**Wrapper API**: `GaussianBlur_412_Native(src, ksize, sigma)` → validates input (uint8, 2D/3D, odd ksize, positive sigma) → calls native `gaussian_blur()`.

**Docker integration**: The base image copies `.so` files to `/usr/local/lib/` and the `.so` Python extension to `dist-packages/`, then runs `ldconfig` to register the shared libraries.

---

## 5. Shared Scripts

### 5.1 gpu-entrypoint.sh — Hardware Detection & Optimization

**Location**: `/app/gpu-entrypoint.sh`  
**Used as**: `ENTRYPOINT` in both test and production Docker stages

Runs before the main command (`CMD`) to detect hardware and set optimal threading:

**Detection steps**:
1. **CPU**: Reads `/proc/cpuinfo` — detects vendor (Intel XEON/Intel/AMD), core count, architecture
2. **Memory**: Reads `free -h` for total RAM
3. **GPU**: Checks `nvidia-smi`, then verifies TensorFlow GPU access via `tf.config.list_physical_devices('GPU')`

**Optimization strategy**:

| Mode | Thread Strategy | OMP_NUM_THREADS | TF_NUM_INTRAOP_THREADS |
|------|----------------|-----------------|------------------------|
| **GPU** | Minimal CPU threads (GPU does heavy lifting) | 2 | 2 |
| **CPU** | All cores available | unset (auto-detect) | 0 (auto-detect all) |

**Safety**: Detects `OMP_NUM_THREADS=0` (causes libgomp crash) and unsets it.

**Environment variables set**: `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, `TF_NUM_INTRAOP_THREADS`, `TF_NUM_INTEROP_THREADS`, `TF_ENABLE_ONEDNN_OPTS=1`

### 5.2 compile.py — SavedModel → H5 Conversion

**Location**: `/app/compile.py`

**Purpose**: Converts TensorFlow SavedModel directories to `.h5` format during Docker build. This is a build-time optimization — loading `.h5` is faster than loading SavedModel at runtime.

**`convert_models()`**:
1. Walks `_models/` looking for directories containing a `saved_model.pb` file
2. Loads via `load_model_from_tf_model_files()` (from `common/model_launching.py`)
3. Saves as `.h5` with `save_format='h5'` to `_models_compiled/` directory
4. Clears TF session + `gc.collect()` between each model to prevent memory buildup
5. Uses `tf_keras` with fallback to `tf.keras`

**Docker usage**: A dedicated `compile` stage in model Dockerfiles runs this before the development stage:
```dockerfile
FROM base AS compile
COPY _models /app/_models/
COPY *.py /app/
RUN python3 compile.py
```

### 5.3 runtests.sh — Generic Test Runner

**Location**: `/app/runtests.sh`  
**Used by**: All 11 model repositories (inherited from base image)

```bash
coverage run --omit 'common/*,main.py,*compile.py,tests/*,config*.py' \
    --source=./ -m pytest -l tests/test.py -v
```

**Coverage omissions**:
- `common/*` — common library code (tested separately in common_ai_library)
- `main.py` — entry point wrapper (pragma: no cover)
- `*compile.py` — build-time only code (covers both `compile.py` and model-specific variants like `qc_compile.py`)
- `tests/*` — test code itself
- `config*.py` — configuration files

Generates JUnit XML for CI, coverage XML, and coverage HTML report.

### 5.4 runtests_library.sh — Library Test Runner

**Location**: `/app/runtests_library.sh`  
**Used by**: `common_ai_library` test stage only

```bash
coverage run --omit 'tests/*' --source=./ -m pytest tests/ -v
```

Differs from `runtests.sh`:
- Includes `common/*` and `compile.py` in coverage (they're the code under test)
- Runs all test files in `tests/` directory (not just `test.py`)

### 5.5 sbom.sh — Software Bill of Materials

**Location**: `/app/sbom.sh`

1. Installs `cyclonedx-bom` pip package
2. Generates CycloneDX XML SBOM from installed Python packages
3. Copies SBOM to `/app/results/` for extraction

Used via `--target sbom` Docker build.

---

## 6. Model Repository Pattern

### 6.1 Standard Directory Layout

Every model repository follows this structure:

```
{model_name}_model/
├── Dockerfile              # Multi-stage build FROM base image
├── Dockerfile.standalone   # Self-contained version (fallback)
├── main.py                 # Entry point — loads models, starts webserver
├── launch_models.py        # Model loading + warmup
├── {model}_pipeline.py     # Full inference pipeline
├── {model}_directory_setup.py  # Working directory definitions
├── extra-requirements.txt  # Model-specific pip packages
├── compile.py              # (optional) Model-specific compile overrides
├── _models/                # TensorFlow SavedModel weights (binary)
│   ├── {grader}/           # One or more jury model directories
│   └── warmup_images/      # Pre-baked images for model warmup
├── tests/
│   └── test.py             # pytest tests
└── mytests/                # Developer integration tests
```

### 6.2 Model Dockerfile Multi-Stage Build

Every model Dockerfile has **5 stages** that extend the base image:

```dockerfile
ARG BASE_IMAGE=tokueyesproduction.azurecr.io/models/common-ai-library:buildid-N

FROM ${BASE_IMAGE} AS base

# Stage 1: compile — Convert SavedModel to .h5
FROM base AS compile
COPY _models /app/_models/
COPY *.py /app/
RUN python3 compile.py

# Stage 2: development — Copy compiled models + code + extra deps
FROM base AS development
COPY --from=compile /app/_models_compiled/ /app/_models/
ADD _models/warmup_images /app/_models/warmup_images
COPY *.py /app/
COPY extra-requirements.txt /app/
RUN pip install --break-system-packages -r /app/extra-requirements.txt
ARG BUILD_TERELEASE=TEST
ENV TERELEASE=$BUILD_TERELEASE

# Stage 3: sbom
FROM development AS sbom
CMD ["/app/sbom.sh"]

# Stage 4: test
FROM development AS test
COPY tests /app/tests/
ENTRYPOINT ["/app/gpu-entrypoint.sh"]
CMD ["/app/runtests.sh"]

# Stage 5: production
FROM development AS production
ENV OMP_NUM_THREADS= MKL_NUM_THREADS= ...  # Unset all — let entrypoint decide
ENTRYPOINT ["/app/gpu-entrypoint.sh"]
CMD ["python3", "./main.py"]
```

**Build targets**:
```bash
docker build --target test    -t model:test .      # Run tests
docker build --target sbom    -t model:sbom .      # Generate SBOM
docker build --target production -t model:prod .   # Production image
```

### 6.3 Model-Specific Customization Points

Each model customizes these areas:

#### extra-requirements.txt
Model-specific Python packages not in the base image:

| Model(s) | Extra Packages |
|-----------|---------------|
| dz, hba1c, sbp, tchdl, ethnicity, pa | `efficientnet==1.1.1` |
| cvd | `shap==0.50.0` |
| m, r, qc, qc2 | *(empty — no extra deps)* |

#### {model}_directory_setup.py
Declares the working directory tree as a Python dictionary. Example from `dz_model`:
```python
dz_dir = {
    'model_dir':              base_path/_models,
    'warmup_dz_images_dir':   base_path/_models/warmup_dz_images,
    'img_dir':                base_path/images,
    'gen_dir':                base_path/generated,
    'preprocessed_dir':       base_path/generated/preprocessed,
    'cropped_1200_dir':       base_path/generated/preprocessed/cropped_1200,
    'cropped_800_dir':        base_path/generated/preprocessed/cropped_800,
    'cropped_enhanced_800_dir': base_path/generated/preprocessed/cropped_enhanced_800,
    ...
}
```

#### launch_models.py
Loads model-specific jury ensemble + runs warmup predictions:
```python
# Load jury models
model_jury = []
for weight in os.listdir(grader_weights_dir):
    model = load_model_from_tf_model_files(os.path.join(dir, weight, weight))
    model_jury.append(model)

# Warmup prediction (first prediction is slow — do it during startup)
warmup_pred = predict_preload_jury(model_jury, warmup_images, ...)
```

### 6.4 Pipeline Execution Flow

Every model follows this pipeline pattern (example from `dz_pipeline.py`):

```
1. fetch_base64_json_images()      → Decode base64 images from API request
2. preprocess_image()              → Crop, resize, enhance retinal images
3. infer_models()                  → Run jury ensemble prediction
4. postprocess_inference()         → Aggregate image→eye→patient predictions
5. format_outbound_message()       → Format JSON response
6. setVersion()                    → Stamp version from TERELEASE env var
```

---

## 7. Inference Architecture

### 7.1 Request Lifecycle

```
Client POST /api/inference
    │
    ▼
┌─────────────┐
│  webserver   │  Flask + Waitress
│  (port 80)   │  Set CorrelationID, parse JSON
└──────┬──────┘
       │ process_json(request_json)
       ▼
┌─────────────┐
│  pipeline    │  Model-specific (e.g., dz_pipeline)
│              │  
│  1. Fetch    │  base64 → PNG images
│  2. Preproc  │  crop → resize → enhance
│  3. Infer    │  jury ensemble prediction
│  4. Postproc │  image → eye → patient
│  5. Format   │  JSON response
└──────┬──────┘
       │ JSON result
       ▼
┌─────────────┐
│  webserver   │  Record metrics, gc.collect()
│  response    │  Return to client
└─────────────┘

Prometheus metrics ← port 8888
```

### 7.2 Jury Ensemble System

All models use an ensemble of multiple trained models ("jury") for robust predictions:

1. **Loading**: 3–5 identical architecture models with different trained weights are loaded from `_models/{grader}/` subdirectories
2. **Prediction**: Each jury member independently predicts on the same preprocessed images
3. **Aggregation**: Predictions are combined — typically `mean(across_jury)[argmax]`

```
Jury Member 1 ──┐
Jury Member 2 ──┤──→ pred_conf[jury, images, classes] ──→ mean(axis=0).argmax()
Jury Member 3 ──┤
Jury Member N ──┘
```

The `pred_conf` array has shape `[jury_count, image_count, class_count]`.

### 7.3 Eye-Level Aggregation

Retinal images are per-eye (left/right), but clinical decisions are per-patient:

```
Image 1 (left eye)  ─┐
Image 2 (left eye)  ─┤──→ Left Eye Prediction  = max(image predictions)
                      │
Image 3 (right eye) ─┤──→ Right Eye Prediction = max(image predictions)
Image 4 (right eye) ─┘
                           Patient Prediction = max(left, right) or mean
```

### 7.4 Parallel Inference

When `PARALLEL_INFERENCE=true`:
- Uses `ThreadPoolExecutor` with `max_workers = min(jury_count, cpu_count)`
- Each thread gets its own `ImageDataGenerator` instance (thread safety)
- Configurable via `PARALLEL_INFERENCE_THREADS` environment variable

---

## 8. Testing Infrastructure

### 8.1 Docker-Based Testing

Tests run inside Docker containers to match the production environment exactly:

```bash
# Build and run tests for a model
docker build --target test --build-arg BASE_IMAGE=ai-model-base:local -t model:test .
docker run --rm model:test

# Build and run tests for common_ai_library
docker build --target test -t common:test .
docker run --rm common:test
```

The test stage:
1. Inherits everything from the development stage (compiled models, code, deps)
2. Copies `tests/` directory
3. Sets `ENTRYPOINT` to `gpu-entrypoint.sh` (hardware detection)
4. Sets `CMD` to `runtests.sh` (or `runtests_library.sh` for the library)

### 8.2 Coverage Configuration

| Repository | Runner | Source | Omit | Min Target |
|------------|--------|--------|------|------------|
| common_ai_library | `runtests_library.sh` | `./` | `tests/*` | 96% |
| All 11 models | `runtests.sh` | `./` | `common/*,main.py,*compile.py,tests/*,config*.py` | 80% |

### 8.3 Test Results

| Model | Tests Passed | Coverage |
|-------|-------------|----------|
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

---

## 9. Environment Variables Reference

### Build-Time Variables

| Variable | Set In | Purpose |
|----------|--------|---------|
| `BASE_IMAGE` | Dockerfile ARG | Base image reference (ACR URL or local tag) |
| `BUILD_TERELEASE` | Dockerfile ARG | Version string stamped into container |
| `TERELEASE` | Dockerfile ENV | Runtime version (from BUILD_TERELEASE) |

### Runtime Threading Variables

| Variable | GPU Mode | CPU Mode | Purpose |
|----------|----------|----------|---------|
| `OMP_NUM_THREADS` | 2 | unset (auto) | OpenMP threads |
| `MKL_NUM_THREADS` | 2 | unset (auto) | Intel MKL threads |
| `OPENBLAS_NUM_THREADS` | 2 | unset (auto) | OpenBLAS threads |
| `NUMEXPR_NUM_THREADS` | 2 | unset (auto) | NumExpr threads |
| `VECLIB_MAXIMUM_THREADS` | 2 | unset (auto) | macOS Accelerate threads |
| `TF_NUM_INTRAOP_THREADS` | 2 | 0 (all cores) | TensorFlow intra-op parallelism |
| `TF_NUM_INTEROP_THREADS` | 2 | 0 (all cores) | TensorFlow inter-op parallelism |

### Runtime Feature Flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_TIMING_LOGS` | `false` | Log pipeline step durations |
| `SAVE_IMAGES_TO_DISK` | `true` | Save intermediate images to disk vs. memory |
| `DEBUG_SAVE_STEPS` | `false` | Save intermediate preprocessing steps for debugging |
| `PARALLEL_INFERENCE` | `false` | Enable parallel jury inference |
| `PARALLEL_INFERENCE_THREADS` | auto-detect | Thread count for parallel inference |

### TensorFlow Configuration

| Variable | Value | Purpose |
|----------|-------|---------|
| `TF_ENABLE_ONEDNN_OPTS` | `1` | Enable oneDNN optimizations |
| `TF_CPP_MIN_LOG_LEVEL` | `2` | Suppress TF INFO/WARNING logs |
| `TF_FORCE_GPU_ALLOW_GROWTH` | `true` | Don't pre-allocate all GPU memory |
| `SCIKIT_IMAGE_LAZY_LOADING` | `0` | Fix lazy_loader lambda pickle errors |
| `NVIDIA_VISIBLE_DEVICES` | `all` | Expose all GPUs to container |
| `NVIDIA_DRIVER_CAPABILITIES` | `compute,utility` | Required GPU capabilities |
| `NVIDIA_REQUIRE_CUDA` | `cuda>=12.6` | Minimum CUDA version |

---

## 10. Security Practices

### Vulnerability Management

- **Requirements pinning**: Security-sensitive packages use `>=` minimum versions to automatically pick up patches:
  - `cryptography>=44.0.0`, `PyJWT>=2.10.0`, `urllib3>=2.6.3`, `Werkzeug>=3.1.4`
- **System Python upgrade**: The base image upgrades system Python packages (`/usr/lib/python3/dist-packages/`) to prevent CVEs from old `apt`-installed versions
- **Proactive patching**: Known CVEs tracked and patched (e.g., Keras GHSA-3m4q, Flask GHSA-68rp)

### SBOM Generation

Every Docker build can generate a CycloneDX Software Bill of Materials:
```bash
docker build --target sbom -t model:sbom .
docker run --rm -v ./results:/app/results model:sbom
```

### Container Hardening

- Non-root-compatible (no hardcoded root operations at runtime)
- `PYTHONUNBUFFERED=1` for reliable logging in Docker
- Minimal runtime image (no build tools/compilers)
- GPU memory growth enabled (prevents OOM from pre-allocation)

---

## 11. Model Inventory

| Model | Description | Image Size | Type | Extra Packages |
|-------|-------------|-----------|------|----------------|
| **dz_model** | Drusen size grading | 800×800 | Classification (3 classes) | efficientnet |
| **hba1c_model** | HbA1c estimation | 800×800 | Regression + Embedding | efficientnet |
| **cvd_model** | Cardiovascular disease risk | 800×800 | Regression + Embedding | shap |
| **ethnicity_model** | Ethnicity classification | 800×800 | Classification | efficientnet |
| **m_model** | Myopia detection | 800×800 | Classification | — |
| **pa_model** | Pigmentary abnormality | 800×800 | Classification | efficientnet |
| **r_model** | Retinopathy grading | 800×800 | Classification | — |
| **sbp_model** | Systolic blood pressure | 800×800 | Regression + Embedding | efficientnet |
| **tchdl_model** | TC/HDL cholesterol ratio | 800×800 | Regression + Embedding | efficientnet |
| **qc_model** | Quality control | varies | Classification | — |
| **qc2_model** | Quality control v2 | varies | Classification | — |

---

## 12. Data Flow Diagram

```
                    ┌──────────────────────────────────┐
                    │       common_ai_library           │
                    │                                    │
                    │  requirements.txt ──→ pip install  │
                    │  common/*.py    ──→ /app/common/  │
                    │  cv412_native   ──→ /usr/local/   │
                    │  gpu-entrypoint ──→ /app/         │
                    │  runtests.sh    ──→ /app/         │
                    │  compile.py     ──→ /app/         │
                    └───────────┬──────────────────────┘
                                │
                    Push to ACR as:
                    common-ai-library:buildid-N
                                │
      ┌─────────────────────────┼─────────────────────────┐
      ▼                         ▼                         ▼
┌──────────┐           ┌──────────────┐           ┌──────────┐
│ dz_model │           │  hba1c_model │           │  ...x11  │
│          │           │              │           │          │
│ FROM base│           │  FROM base   │           │ FROM base│
│ + _models│           │  + _models   │           │ + _models│
│ + *.py   │           │  + *.py      │           │ + *.py   │
│ + extra  │           │  + extra     │           │ + extra  │
│   reqs   │           │    reqs      │           │   reqs   │
└────┬─────┘           └──────┬───────┘           └────┬─────┘
     │                        │                        │
     │ docker build           │                        │
     │ --target production    │                        │
     ▼                        ▼                        ▼
┌──────────┐           ┌──────────────┐           ┌──────────┐
│ K8s Pod  │           │   K8s Pod    │           │ K8s Pod  │
│ port 80  │◄── API ──►│   port 80    │◄── API ──►│ port 80  │
│ port 8888│ metrics   │   port 8888  │ metrics   │ port 8888│
└──────────┘           └──────────────┘           └──────────┘
```

---

## Appendix A: Module Dependency Graph

```
main.py
├── common/logging.py          → InitLogging()
├── common/version.py          → printVersion(), printEnvVariables(), printOpenCVExtensionStatus()
├── common/webserver.py        → initWebserver(process_json, port, prefix)
└── {model}_pipeline.py
    ├── common/os_setup.py     → load_set_os_config_para()
    ├── common/directory_setup.py → create_working_directory()
    ├── {model}_directory_setup.py → declare_{model}_working_directory()
    ├── launch_models.py
    │   └── common/model_launching.py → load_model_from_tf_model_files(), predict_preload_jury()
    ├── common/image_preprocessing.py → fetch_base64_json_images(), preprocess_image()
    ├── common/model_inference.py → infer_models() / infer_embed_models()
    │   └── common/model_launching.py → predict_preload_jury()
    ├── common/inference_postprocesssing.py → postprocess_inference()
    ├── common/outbound_message_writing.py → format_outbound_message()
    └── common/version.py → setVersion()
```

---

## Appendix B: Adding a New Model

1. **Create repository** following the standard layout (§6.1)
2. **Create `extra-requirements.txt`** with model-specific packages (can be empty)
3. **Create `{model}_directory_setup.py`** defining the working directory dict
4. **Create `launch_models.py`** to load jury models + run warmup
5. **Create `{model}_pipeline.py`** following the standard pipeline (§6.4)
6. **Create `main.py`** calling `InitLogging()`, `printVersion()`, `load_models()`, `initWebserver()`
7. **Copy the standard Dockerfile** and update warmup image paths
8. **Place trained models** in `_models/{grader}/` as SavedModel directories
9. **Write tests** in `tests/test.py` targeting ≥80% coverage
10. **Build and test**:
    ```bash
    docker build --target test -t newmodel:test .
    docker run --rm newmodel:test
    ```

---

*This document was generated from analysis of the complete codebase as of July 2025.*

"""MCP tool + prompt: answer questions about TokuEyes AI models & infrastructure.

Knowledge is pre-baked from:
  - AI_INFRASTRUCTURE_ARCHITECTURE.md
  - CLBA-2339-Complete-Report.md
  - Architecture diagram

Only document-sourced facts are returned. Nothing is invented.
"""

# ── Structured knowledge base ────────────────────────────────────────────────
# Each entry: keywords (for matching) + content (returned verbatim).
# Content is kept compact — no markdown filler — to save tokens.

_KB = {
    "overview": {
        "keywords": [
            "overview", "summary", "what is", "platform", "tokueyes",
            "toku", "explain", "describe", "about", "introduction",
        ],
        "content": (
            "TokuEyes AI Platform — Overview\n"
            "• Analyses retinal fundus images for medical screening.\n"
            "• Shared base image pattern: `common_ai_library` produces a Docker "
            "base image; 11 model repos build FROM it.\n"
            "• All models serve predictions via Flask + Waitress on port 80, "
            "Prometheus metrics on port 8888.\n"
            "• Jury ensemble system: 3–5 trained models vote per prediction.\n"
            "• Aggregation: image → eye (left/right) → patient.\n"
            "• Tech: Python 3.12, TensorFlow 2.20, CUDA 12.6, Ubuntu 24.04.\n"
            "• Deployed on Azure Kubernetes (Dsv6 Intel Xeon nodes).\n"
            "• All 12 repos: 0 CVEs, >85 % test coverage, GitHub Actions CI/CD."
        ),
    },

    "models": {
        "keywords": [
            "model", "models", "list", "inventory", "which model",
            "how many", "all model", "model name",
        ],
        "content": (
            "Model Inventory (11 models + shared base)\n\n"
            "| Model | Description | Input | Type | Extra Packages |\n"
            "|-------|-------------|-------|------|----------------|\n"
            "| dz_model | Drusen size grading | 800×800 | Classification (3 classes: none/small, medium, large) | efficientnet |\n"
            "| hba1c_model | HbA1c estimation | 800×800 | Regression + Embedding | efficientnet |\n"
            "| cvd_model | Cardiovascular disease risk | 800×800 | Regression + Embedding | shap |\n"
            "| ethnicity_model | Ethnicity classification | 800×800 | Classification | efficientnet |\n"
            "| m_model | Myopia detection | 800×800 | Classification | — |\n"
            "| pa_model | Pigmentary abnormality | 800×800 | Classification | efficientnet |\n"
            "| r_model | Retinopathy grading | 800×800 | Classification | — |\n"
            "| sbp_model | Systolic blood pressure | 800×800 | Regression + Embedding | efficientnet |\n"
            "| tchdl_model | TC/HDL cholesterol ratio | 800×800 | Regression + Embedding | efficientnet |\n"
            "| qc_model | Quality control | varies | Classification | — |\n"
            "| qc2_model | Quality control v2 | varies | Classification | — |\n"
            "| optos_cropping_model | Optos image cropping | varies | — | — |\n\n"
            "Shared base: `common_ai_library` — contains all shared modules, "
            "scripts, native OpenCV 4.1.2 extension, and Python dependencies."
        ),
    },

    "pipeline_flow": {
        "keywords": [
            "pipeline", "flow", "diagram", "architecture diagram",
            "how does it work", "process", "steps", "lifecycle",
            "request", "end to end", "e2e", "data flow",
        ],
        "content": (
            "Architecture Flow (from architecture diagram)\n\n"
            "1. Captured fundus images enter the system.\n"
            "2. FILTERING STAGE (pink):\n"
            "   • QC model — quality control gate\n"
            "   • Left-Right model — eye laterality detection\n"
            "   • Fovea-Location model — fovea positioning\n"
            "3. CLAIR PIPELINE (yellow — biomarker extraction):\n"
            "   • Pigment abnormality grader (PA)\n"
            "   • Drusen grader (DZ)\n"
            "   • AAMD grader\n"
            "   • R grader (retinopathy)\n"
            "   • M grader (myopia)\n"
            "   • Cholesterol predictor (TCHDL)\n"
            "   • HbA1c predictor\n"
            "   • Blood pressure predictor (SBP)\n"
            "   • Smoking level predictor\n"
            "4. CVD PREDICTION (blue):\n"
            "   • Combines biomarker outputs + patient meta-info → CVD risk\n"
            "5. BIOAGE (teal):\n"
            "   • Biological age estimation from combined outputs.\n\n"
            "Per-model request lifecycle:\n"
            "  POST /api/inference → webserver (Flask+Waitress) → "
            "fetch_base64_json_images → preprocess_image (crop→resize→enhance) → "
            "infer_models (jury ensemble) → postprocess_inference (image→eye→patient) → "
            "format_outbound_message → JSON response + gc.collect()"
        ),
    },

    "inference": {
        "keywords": [
            "inference", "jury", "ensemble", "prediction", "how predict",
            "aggregat", "eye level", "parallel inference", "grader",
        ],
        "content": (
            "Inference Architecture\n\n"
            "JURY ENSEMBLE:\n"
            "• Each model loads 3–5 identical-architecture networks with different trained weights.\n"
            "• All jury members predict independently on the same preprocessed images.\n"
            "• Result: pred_conf[jury_count, image_count, class_count].\n"
            "• Aggregation: mean across jury → argmax per image.\n\n"
            "EYE-LEVEL AGGREGATION:\n"
            "• Images grouped by patient visit + left/right eye.\n"
            "• Eye prediction = max of image-level predictions for that eye.\n"
            "• Patient prediction = max(left_eye, right_eye) or mean.\n\n"
            "PARALLEL INFERENCE (opt-in):\n"
            "• Env: PARALLEL_INFERENCE=true, PARALLEL_INFERENCE_THREADS=N.\n"
            "• Uses ThreadPoolExecutor; each thread owns its own ImageDataGenerator.\n"
            "• ~20 % inference time reduction observed.\n"
            "• Trade-off: higher memory usage (concurrent image batches in memory)."
        ),
    },

    "preprocessing": {
        "keywords": [
            "preprocess", "image processing", "crop", "enhance",
            "gaussian", "blur", "opencv", "resize", "image pipeline",
        ],
        "content": (
            "Image Preprocessing Pipeline\n\n"
            "Standard pipeline (preprocess_image):\n"
            "1. Read image (from disk or memory buffer).\n"
            "2. Resolution check: ≥800 px minimum.\n"
            "3. crop_img: remove black/blank background, pad to square.\n"
            "4. Resolution check: ≥100 px post-crop.\n"
            "5. Resize to 1200×1200.\n"
            "6. Write/read cycle (JPEG compression normalisation).\n"
            "7. Resize to 800×800.\n"
            "8. enhance_img_native: unsharp mask via native OpenCV 4.1.2 GaussianBlur.\n"
            "   ksize = ceil(scale_ratio × 3) × 2 + 1, then addWeighted(alpha=4, beta=−4, gamma=128).\n"
            "9. Save enhanced 800×800 image for model inference.\n\n"
            "NW500 variant (preprocess_image_nw500_v2):\n"
            "  Read → crop → resize 1200 → salt-and-pepper noise → median filter → save.\n\n"
            "NATIVE OPENCV 4.1.2 EXTENSION:\n"
            "• Why: OpenCV 4.12 produces different GaussianBlur output vs 4.1.2. "
            "Sub-pixel differences degrade model accuracy.\n"
            "• C++ extension compiled for Python 3.12 (Linux .so + Windows .pyd).\n"
            "• Links against bundled libopencv_core/imgproc.so.4.1.2.\n"
            "• Ensures 100 % pixel-perfect compatibility with training-time preprocessing."
        ),
    },

    "tech_stack": {
        "keywords": [
            "tech", "stack", "version", "python", "tensorflow",
            "cuda", "ubuntu", "keras", "numpy", "flask",
            "dependency", "dependencies", "requirements", "package",
        ],
        "content": (
            "Technology Stack\n\n"
            "| Component | Version |\n"
            "|-----------|--------|\n"
            "| Ubuntu | 24.04 |\n"
            "| CUDA / cuDNN | 12.6.0 / 9.x |\n"
            "| Python | 3.12 |\n"
            "| TensorFlow | 2.20.0 |\n"
            "| tf-keras | 2.20.0 (Keras 2 compat shim) |\n"
            "| Keras | 3.13.2 |\n"
            "| NumPy | 1.26.4 |\n"
            "| Pandas | 2.3.3 |\n"
            "| OpenCV | 4.12.0.88 (headless) + 4.1.2 native extension |\n"
            "| Flask | 3.1.3 |\n"
            "| Waitress | 3.0.2 |\n"
            "| Prometheus client | 0.21.0 + exporter 0.23.1 |\n"
            "| scikit-image | 0.25.2 |\n\n"
            "Base Docker image: nvidia/cuda:12.6.0-cudnn-runtime-ubuntu24.04\n"
            "Builder stage uses nvidia/cuda:12.6.0-cudnn-devel-ubuntu24.04 (discarded)."
        ),
    },

    "docker": {
        "keywords": [
            "docker", "dockerfile", "container", "build", "image",
            "stage", "multi-stage", "acr", "registry",
        ],
        "content": (
            "Docker Architecture\n\n"
            "BASE IMAGE (common_ai_library) — 4 stages:\n"
            "  builder (devel CUDA) → base (runtime CUDA) → sbom → test\n"
            "  Packages compiled in builder, copied to base via COPY --from=builder.\n\n"
            "MODEL IMAGES — 5 stages:\n"
            "  FROM ${BASE_IMAGE} AS base\n"
            "  → compile (SavedModel → .h5 conversion)\n"
            "  → development (code + compiled models + extra-requirements.txt)\n"
            "  → sbom (CycloneDX SBOM generation)\n"
            "  → test (pytest + coverage via runtests.sh)\n"
            "  → production (ENTRYPOINT gpu-entrypoint.sh, CMD python3 main.py)\n\n"
            "Build targets:\n"
            "  docker build --target test -t model:test .       # run tests\n"
            "  docker build --target sbom -t model:sbom .       # generate SBOM\n"
            "  docker build --target production -t model:prod . # production\n\n"
            "Registry: tokueyesproduction.azurecr.io/models/\n"
            "CPU distro: tokuairegistry.azurecr.io/cpudistro/ (no CUDA overhead)"
        ),
    },

    "modules": {
        "keywords": [
            "module", "common", "shared", "webserver", "model_launching",
            "model_inference", "postprocess", "outbound", "logging",
            "os_setup", "directory", "version",
        ],
        "content": (
            "Shared Common Modules (in /app/common/)\n\n"
            "1. webserver.py — Flask + Waitress + Prometheus.\n"
            "   Routes: /healthz, /startup, /, /api/inference (POST).\n"
            "   initWebserver(func_process_json, iPort, prefix).\n"
            "   Prometheus metrics: {prefix}_processed_seconds, _processed, _current, waitress queue/active/threads.\n\n"
            "2. model_launching.py — Model loading + jury prediction.\n"
            "   SafeLambda: handles cross-Python-version .h5 deserialization errors.\n"
            "   FixedDropout: EfficientNet compatibility layer.\n"
            "   load_model_from_tf_model_files(path, embedding_layer): loads .h5 or SavedModel, runs warmup.\n"
            "   predict_preload_jury(models, ...): ensemble prediction → pred_conf[jury, images, classes].\n\n"
            "3. model_inference.py — Higher-level orchestration.\n"
            "   infer_models(): classification jury inference.\n"
            "   infer_embed_models(): dual-output (embedding + classification).\n\n"
            "4. image_preprocessing.py — Full image pipeline (see 'preprocessing' topic).\n\n"
            "5. inference_postprocesssing.py — Image→eye→patient aggregation.\n"
            "   postprocess_inference(): groups by patient+eye, mean across jury, argmax, max per eye.\n\n"
            "6. outbound_message_writing.py — JSON response formatting.\n"
            "   format_outbound_message(): maps numeric predictions to labels (e.g. dz: none/small, medium, large).\n"
            "   format_regression_embedding_outbound_message(): for regression + embedding models.\n\n"
            "7. os_setup.py — GPU memory growth (Linux), CPU fallback (Windows).\n"
            "8. directory_setup.py — Creates working directory trees.\n"
            "9. logging.py — Structured logging with correlation ID (from CorrelationID header).\n"
            "10. version.py — Stamps TERELEASE version into responses."
        ),
    },

    "env_vars": {
        "keywords": [
            "env", "environment", "variable", "config", "flag",
            "parallel", "thread", "omp", "onednn", "timing",
            "save_images", "debug",
        ],
        "content": (
            "Environment Variables Reference\n\n"
            "BUILD-TIME:\n"
            "  BASE_IMAGE — base image ACR URL\n"
            "  BUILD_TERELEASE — version string\n\n"
            "THREADING (set by gpu-entrypoint.sh):\n"
            "  GPU mode: OMP/MKL/OPENBLAS/NUMEXPR/VECLIB = 2, TF intra/inter-op = 2\n"
            "  CPU mode: all unset (auto-detect all cores)\n\n"
            "FEATURE FLAGS:\n"
            "  ENABLE_TIMING_LOGS (false) — log per-step durations\n"
            "  SAVE_IMAGES_TO_DISK (true) — disk vs memory pipeline mode\n"
            "  DEBUG_SAVE_STEPS (false) — save intermediate preprocessing images\n"
            "  PARALLEL_INFERENCE (false) — enable parallel jury inference\n"
            "  PARALLEL_INFERENCE_THREADS (auto) — thread count for parallel inference\n\n"
            "TENSORFLOW:\n"
            "  TF_ENABLE_ONEDNN_OPTS=1 — oneDNN optimizations (default on Intel Xeon)\n"
            "  TF_CPP_MIN_LOG_LEVEL=2 — suppress INFO/WARNING\n"
            "  TF_FORCE_GPU_ALLOW_GROWTH=true — no GPU memory pre-allocation\n"
            "  NVIDIA_VISIBLE_DEVICES=all, NVIDIA_DRIVER_CAPABILITIES=compute,utility\n"
            "  NVIDIA_REQUIRE_CUDA=cuda>=12.6"
        ),
    },

    "testing": {
        "keywords": [
            "test", "coverage", "pytest", "quality", "qa",
        ],
        "content": (
            "Testing Infrastructure\n\n"
            "All tests run inside Docker containers matching production environment.\n"
            "Runner: docker build --target test → docker run → runtests.sh (pytest + coverage).\n\n"
            "| Repository | Tests | Coverage |\n"
            "|------------|-------|----------|\n"
            "| common_ai_library | 193 | 96 % |\n"
            "| cvd_model | 28 | 98 % |\n"
            "| hba1c_model | 20 | 95 % |\n"
            "| sbp_model | 14 | 95 % |\n"
            "| tchdl_model | 14 | 95 % |\n"
            "| m_model | 12 | 91 % |\n"
            "| r_model | 12 | 91 % |\n"
            "| ethnicity_model | 10 | 87 % |\n"
            "| dz_model | 14 | 86 % |\n"
            "| qc_model | 8 | 86 % |\n"
            "| qc2_model | 18 | 86 % |\n"
            "| pa_model | 14 | 85 % |\n\n"
            "All 12 repos: >85 % coverage. Unit tests include baseline comparison tests "
            "verifying inference outputs match pre-upgrade results."
        ),
    },

    "security": {
        "keywords": [
            "security", "cve", "vulnerability", "sbom", "remediat",
            "hardening",
        ],
        "content": (
            "Security & Vulnerability Remediation\n\n"
            "BEFORE: ~150 CVEs per container (old NVIDIA base + Ubuntu 20.04 + outdated packages).\n"
            "AFTER: 0 CVEs across all 12 repositories (verified by Dependency-Track, CycloneDX 1.6, 4 Mar 2026).\n\n"
            "Key actions:\n"
            "• Security-sensitive packages pinned with >= minimums: "
            "cryptography>=44.0.0, PyJWT>=2.10.0, urllib3>=2.6.3, Werkzeug>=3.1.4.\n"
            "• Ubuntu 24.04 system Python packages explicitly removed and replaced with pip-pinned versions.\n"
            "• Base image replaced: NVIDIA pre-built → purpose-built from nvidia/cuda runtime.\n"
            "• Every CI build generates CycloneDX SBOM, auto-imported into Dependency-Track.\n"
            "• Container hardening: non-root compatible, PYTHONUNBUFFERED=1, minimal runtime image (no compilers).\n"
            "• GPU memory growth enabled (prevents OOM from pre-allocation)."
        ),
    },

    "upgrade": {
        "keywords": [
            "upgrade", "migration", "clba-2339", "before after",
            "what changed", "old", "new", "platform upgrade",
        ],
        "content": (
            "CLBA-2339 Platform Upgrade (Nov 2025 – Mar 2026)\n\n"
            "| Component | Before | After |\n"
            "|-----------|--------|-------|\n"
            "| Base Image | nvcr.io/nvidia/tensorflow:22.08-tf2-py3 | Custom common-ai-library |\n"
            "| Ubuntu | 20.04 | 24.04 |\n"
            "| Python | 3.8 | 3.12 |\n"
            "| CUDA | 11.7 | 12.6.0 |\n"
            "| TensorFlow | 2.9.1 | 2.20.0 |\n"
            "| Keras | 2.9 (bundled) | 3.13.2 (standalone via tf-keras) |\n"
            "| OpenCV | 4.1.2.30 | 4.12.0.88 + native 4.1.2 extension |\n\n"
            "Key changes:\n"
            "• Shared base image pattern replaced 11× duplicated common/ folders.\n"
            "• tf-keras compatibility shim for Keras 3 backward compatibility.\n"
            "• Native OpenCV 4.1.2 C++ extension for pixel-perfect GaussianBlur.\n"
            "• gpu-entrypoint.sh: hardware detection + thread optimization.\n"
            "• Intel Xeon optimization: oneDNN replaces ITEX (deprecated at TF 2.17).\n"
            "• Memory mode: optional in-memory pipeline (SAVE_IMAGES_TO_DISK=false).\n"
            "• Parallel inference: ThreadPoolExecutor for jury graders.\n"
            "• 0 CVEs (was ~150 per container).\n"
            "• Bitbucket → GitHub migration with central-workflow CI/CD.\n"
            "• All models: >85 % test coverage.\n\n"
            "Epic: CLBA-2339 | Assignee: Ata Moradi | Status: Ready For Test"
        ),
    },

    "github_cicd": {
        "keywords": [
            "github", "ci", "cd", "cicd", "workflow", "action",
            "bitbucket", "deploy", "pipeline", "central",
        ],
        "content": (
            "CI/CD — GitHub Actions (migrated from Bitbucket Pipelines)\n\n"
            "Each model repo has 5 workflow files calling reusable workflows from "
            "Toku-Eyes/central-workflow:\n\n"
            "1. pr.yaml — PR pipeline: flake8 + black + build + test + coverage + SBOM.\n"
            "2. staging-build-and-push.yaml — Manual: build + push to staging ACR.\n"
            "3. staging-deploy-to-k8.yaml — Manual: deploy to staging Kubernetes.\n"
            "4. production-build-and-push.yaml — On tag push (v*.*.*): build + push to prod ACR + GitHub Release.\n"
            "5. fast-deploy-to-staging.yaml — Manual: build + push + deploy in one step.\n\n"
            "Central workflow architecture: model repos contain thin callers (10–30 lines), "
            "all CI/CD logic lives in central-workflow repo. Changes apply to all 12 repos automatically.\n\n"
            "Removed: bitbucket-pipelines.yml (~211 lines each), sonar-project.properties, sbom_post.sh."
        ),
    },

    "hardware": {
        "keywords": [
            "hardware", "gpu", "cpu", "xeon", "intel", "azure",
            "kubernetes", "k8s", "node", "dsv6", "avx",
            "onednn", "entrypoint",
        ],
        "content": (
            "Hardware & Deployment\n\n"
            "TARGET HARDWARE:\n"
            "  Azure Dsv6-series nodes — Intel Xeon Platinum 8573C (Emerald Rapids).\n"
            "  Standard_D16s_v6: 16 vCPUs, 64 GiB RAM (standard inference).\n"
            "  Standard_D32s_v6: 32 vCPUs, 128 GiB RAM (high-throughput / parallel).\n"
            "  Full AVX-512 + AVX-VNNI support.\n\n"
            "GPU-ENTRYPOINT.SH:\n"
            "  Reads /proc/cpuinfo → classifies CPU (Intel XEON / Intel / AMD).\n"
            "  GPU mode: minimal CPU threads (2), GPU does heavy lifting.\n"
            "  CPU mode: all cores available, TF auto-detect, oneDNN enabled.\n"
            "  Safety: detects OMP_NUM_THREADS=0 (crashes libgomp) and unsets it.\n\n"
            "INTEL XEON OPTIMIZATION:\n"
            "  TF 2.20 ships oneDNN natively (ITEX deprecated at TF 2.17).\n"
            "  TF_ENABLE_ONEDNN_OPTS=1 enables Conv2D+Bias+ReLU fusion, MatMul+Bias fusion, BatchNorm fusion.\n"
            "  AVX-512 registers: 512-bit wide → fused kernel ops in single pass.\n"
            "  CPU distro build: tokuairegistry.azurecr.io/cpudistro/ (no CUDA overhead).\n\n"
            "K8S: nodeAffinity selectors pin AI pods to Dsv6 instance types."
        ),
    },

    "repositories": {
        "keywords": [
            "repo", "repository", "github url", "where", "location",
            "local path", "jira", "task",
        ],
        "content": (
            "Repository Locations\n\n"
            "GitHub org: Toku-Eyes\n"
            "Local: C:\\Users\\AtaMoradi\\Desktop\\Tokueyes\\Projects\\Models\\\n\n"
            "| # | Model | GitHub |\n"
            "|---|-------|--------|\n"
            "| 1 | common_ai_library | github.com/Toku-Eyes/common_ai_library |\n"
            "| 2 | r_model | github.com/Toku-Eyes/r_model |\n"
            "| 3 | m_model | github.com/Toku-Eyes/m_model |\n"
            "| 4 | sbp_model | github.com/Toku-Eyes/sbp_model |\n"
            "| 5 | dz_model | github.com/Toku-Eyes/dz_model |\n"
            "| 6 | tchdl_model | github.com/Toku-Eyes/tchdl_model |\n"
            "| 7 | pa_model | github.com/Toku-Eyes/pa_model |\n"
            "| 8 | ethnicity_model | github.com/Toku-Eyes/ethnicity_model |\n"
            "| 9 | cvd_model | github.com/Toku-Eyes/cvd_model |\n"
            "| 10 | hba1c_model | github.com/Toku-Eyes/hba1c_model |\n"
            "| 11 | qc_model | github.com/Toku-Eyes/qc_model |\n"
            "| 12 | qc2_model | github.com/Toku-Eyes/qc2_model |\n"
            "| 13 | optos_cropping_model | github.com/Toku-Eyes/optos_cropping_model |"
        ),
    },

    "new_model": {
        "keywords": [
            "add model", "new model", "create model", "adding",
            "scaffold", "template",
        ],
        "content": (
            "Adding a New Model — Steps\n\n"
            "1. Create repository following the standard layout.\n"
            "2. Create extra-requirements.txt with model-specific packages (can be empty).\n"
            "3. Create {model}_directory_setup.py defining working directory dict.\n"
            "4. Create launch_models.py to load jury models + run warmup.\n"
            "5. Create {model}_pipeline.py following the standard pipeline:\n"
            "   fetch_base64_json_images → preprocess_image → infer_models → "
            "postprocess_inference → format_outbound_message → setVersion.\n"
            "6. Create main.py calling InitLogging(), printVersion(), load_models(), initWebserver().\n"
            "7. Copy the standard Dockerfile and update warmup image paths.\n"
            "8. Place trained models in _models/{grader}/ as SavedModel directories.\n"
            "9. Write tests in tests/test.py targeting ≥80 % coverage.\n"
            "10. Build and test:\n"
            "    docker build --target test -t newmodel:test .\n"
            "    docker run --rm newmodel:test"
        ),
    },

    "specific_dz": {
        "keywords": ["drusen", "dz_model", "dz model"],
        "content": (
            "dz_model — Drusen Size Grading\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Classification (3 classes).\n"
            "• Labels: 0 = none/small, 1 = medium, 2 = large.\n"
            "• Extra packages: efficientnet.\n"
            "• Uses standard preprocessing + NW500 variant for specific camera types.\n"
            "• Tests: 14 passed, 86 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/dz_model"
        ),
    },

    "specific_hba1c": {
        "keywords": ["hba1c", "hba1c_model"],
        "content": (
            "hba1c_model — HbA1c Estimation\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Regression + Embedding (dual output).\n"
            "• Uses infer_embed_models() for separate embedding + prediction arrays.\n"
            "• Extra packages: efficientnet.\n"
            "• Tests: 20 passed, 95 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/hba1c_model"
        ),
    },

    "specific_cvd": {
        "keywords": ["cvd", "cardiovascular", "cvd_model"],
        "content": (
            "cvd_model — Cardiovascular Disease Risk\n"
            "• Input: 800×800 retinal fundus image + patient meta-info.\n"
            "• Type: Regression + Embedding.\n"
            "• Combines biomarker outputs from other models (PA, DZ, TCHDL, HbA1c, SBP, etc.).\n"
            "• Extra packages: shap (for SHAP explainability).\n"
            "• Tests: 28 passed, 98 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/cvd_model"
        ),
    },

    "specific_r": {
        "keywords": ["retinopathy", "r_model", "r model"],
        "content": (
            "r_model — Retinopathy Grading\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Classification.\n"
            "• No extra packages required.\n"
            "• Tests: 12 passed, 91 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/r_model"
        ),
    },

    "specific_m": {
        "keywords": ["myopia", "m_model", "m model"],
        "content": (
            "m_model — Myopia Detection\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Classification.\n"
            "• No extra packages required.\n"
            "• Tests: 12 passed, 91 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/m_model"
        ),
    },

    "specific_pa": {
        "keywords": ["pigment", "pa_model", "pa model", "pigmentary"],
        "content": (
            "pa_model — Pigmentary Abnormality\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Classification.\n"
            "• Extra packages: efficientnet.\n"
            "• Tests: 14 passed, 85 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/pa_model"
        ),
    },

    "specific_sbp": {
        "keywords": ["blood pressure", "sbp_model", "sbp model", "systolic"],
        "content": (
            "sbp_model — Systolic Blood Pressure Estimation\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Regression + Embedding.\n"
            "• Extra packages: efficientnet.\n"
            "• Tests: 14 passed, 95 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/sbp_model"
        ),
    },

    "specific_tchdl": {
        "keywords": ["cholesterol", "tchdl", "tc/hdl"],
        "content": (
            "tchdl_model — TC/HDL Cholesterol Ratio\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Regression + Embedding.\n"
            "• Extra packages: efficientnet.\n"
            "• Tests: 14 passed, 95 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/tchdl_model"
        ),
    },

    "specific_qc": {
        "keywords": ["quality control", "qc_model", "qc model", "qc2"],
        "content": (
            "qc_model / qc2_model — Quality Control\n"
            "• Input: retinal fundus images (variable size).\n"
            "• Type: Classification (pass/fail gate).\n"
            "• No extra packages.\n"
            "• QC is the first stage in the pipeline — filters out poor-quality images.\n"
            "• qc_model: 8 tests, 86 % coverage. qc2_model: 18 tests, 86 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/qc_model, github.com/Toku-Eyes/qc2_model"
        ),
    },

    "specific_ethnicity": {
        "keywords": ["ethnicity", "ethnicity_model"],
        "content": (
            "ethnicity_model — Ethnicity Classification\n"
            "• Input: 800×800 retinal fundus image.\n"
            "• Type: Classification.\n"
            "• Extra packages: efficientnet.\n"
            "• Tests: 10 passed, 87 % coverage.\n"
            "• GitHub: github.com/Toku-Eyes/ethnicity_model"
        ),
    },

    "keras_compat": {
        "keywords": [
            "keras", "tf-keras", "compatibility", "keras 3",
            "keras 2", "import", "breaking change",
        ],
        "content": (
            "Keras 3 Compatibility Layer\n\n"
            "TF 2.20 ships Keras 3 (breaking API changes from Keras 2.x).\n"
            "Solution: tf-keras==2.20.0 as compatibility shim.\n\n"
            "All model code uses:\n"
            "  try:\n"
            "      import tf_keras\n"
            "      from tf_keras.models import load_model\n"
            "      from tf_keras.preprocessing.image import ImageDataGenerator\n"
            "  except ImportError:\n"
            "      from tensorflow.keras.models import load_model\n"
            "      from tensorflow.keras.preprocessing.image import ImageDataGenerator\n\n"
            "Custom layers (SafeLambda, FixedDropout) handle cross-version .h5 deserialization."
        ),
    },

    "memory_mode": {
        "keywords": [
            "memory mode", "disk mode", "save_images_to_disk",
            "in-memory", "disk io",
        ],
        "content": (
            "Memory Mode / Disk I/O Optimization\n\n"
            "DISK MODE (default, SAVE_IMAGES_TO_DISK=true):\n"
            "  Images decoded → written to disk as intermediate files → re-read for inference.\n\n"
            "MEMORY MODE (SAVE_IMAGES_TO_DISK=false):\n"
            "  Images kept as in-memory byte buffers; no disk writes between preprocessing and inference.\n"
            "  Implemented across: image_preprocessing.py, model-specific preprocessing, "
            "model launching, and pipeline orchestration.\n"
            "  predict_preload_model() decodes from memory dict instead of ImageDataGenerator file reads."
        ),
    },
}

# ── Section index: flat list of (lowercase_keyword, section_key) ─────────────
_INDEX = []
for _key, _sec in _KB.items():
    for _kw in _sec["keywords"]:
        _INDEX.append((_kw.lower(), _key))


def _match(question: str, max_sections: int = 3) -> list[str]:
    """Return up to `max_sections` section keys ranked by keyword hits."""
    q = question.lower()
    scores: dict[str, int] = {}
    for kw, key in _INDEX:
        if kw in q:
            scores[key] = scores.get(key, 0) + 1
    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
    return ranked[:max_sections]


# ── Tool registration ────────────────────────────────────────────────────────

def register(mcp):
    @mcp.tool()
    def query_ai_knowledge(question: str) -> str:
        """Answer questions about TokuEyes AI models, infrastructure, and architecture.

        Covers: model inventory, inference pipeline, preprocessing, tech stack,
        Docker builds, shared modules, environment variables, testing, security,
        CI/CD, hardware/deployment, Keras compatibility, and the CLBA-2339 upgrade.

        Returns ONLY facts from the official documentation. If the question is
        outside scope, says so explicitly.

        Args:
            question: Natural-language question about TokuEyes AI models or infrastructure.
        """
        matched = _match(question)

        if not matched:
            return (
                "This question is outside the scope of the TokuEyes AI knowledge base.\n"
                "Covered topics: models, inference, preprocessing, tech stack, Docker, "
                "shared modules, env vars, testing, security, CI/CD, hardware, "
                "Keras compatibility, platform upgrade, repositories."
            )

        parts = [_KB[key]["content"] for key in matched]
        return "\n\n---\n\n".join(parts)

    @mcp.prompt()
    def ai_architecture_context() -> str:
        """Provide TokuEyes AI architecture context as a system prompt.

        Use this prompt to prime the conversation with a compact overview of the
        TokuEyes AI platform before answering detailed questions.
        """
        return (
            "You are answering questions about the TokuEyes AI platform. "
            "Use ONLY the following facts.\n\n"
            + _KB["overview"]["content"]
            + "\n\n"
            + _KB["models"]["content"]
            + "\n\n"
            + _KB["pipeline_flow"]["content"]
        )

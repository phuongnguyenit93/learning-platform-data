# Model Registry and Model Version Management

> **Chapter:** Vertex AI and Machine Learning  
> **Module:** CLOUD_PROVIDERS_GCP

A team builds an order fraud detection model. This week, a new version scores higher F1 than the currently serving version, yet merely changing the training data or feature ordering can drastically alter production outcomes. If the team only saves a `model.pkl` file and overwrites it each training run, operations cannot answer: **which model is running, which dataset/commit trained it, who approved it, and what to roll back to if an incident occurs?**

**Vertex AI Model Registry** organizes model versions and connects them to evaluation, deployment, and monitoring workflows. In newer Google Cloud documentation, the same capability may appear under **Gemini Enterprise Agent Platform Model Registry**; the underlying API still uses `aiplatform.googleapis.com` resources and `gcloud ai` commands. This lesson focuses on **custom-trained/AutoML models registered in Model Registry**, without equating them to the API version lifecycle of Gemini foundation models.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, connecting project/IAM, Cloud Storage, Artifact Registry, Cloud Run/GKE, deployment, and monitoring with the MLOps lifecycle.

**Learning outcomes:**

1. Distinguish **Model resource**, **model version**, **version ID**, **alias**, **labels**, **Endpoint**, and **DeployedModel**.
2. Register an initial version and append new versions under the same model via Console, `gcloud`, or the Python SDK.
3. Design metadata proving **artifact, training data, code, evaluation, and container provenance**.
4. Use aliases such as `candidate`/`production-approved` and understand the special role of `default`.
5. Select explicit versions during online/batch inference deployment; roll out canaries and roll back using **DeployedModel IDs**, not version IDs.
6. Separate train/upload/approve/deploy/predict permissions and avoid exposing data/credentials.
7. Identify how to monitor drift, quality, cost, and safely clean up unused versions.
8. Complete a simulated lab and safe verification steps in a sandbox project.

## 1. Why Do We Need Model Registry?

Model Registry is a **governance repository for model metadata and versions**, not merely a place to hold weights. It lets the team trace the chain **Train → Evaluate → Register → Approve → Deploy → Monitor → Retire**.

~~~mermaid
flowchart LR
  DATA["Training data + feature schema"] --> TRAIN["Vertex AI Training\nor pipeline"]
  CODE["Git commit + container digest"] --> TRAIN
  TRAIN --> ART["Model artifacts\nCloud Storage"]
  ART --> REG["Model Registry\nModel + versions"]
  REG --> QA["Evaluation / approval\ncandidate → approved"]
  QA --> EP["Endpoint\nDeployedModel IDs"]
  EP --> OBS["Monitoring + business KPIs"]
  OBS --> DEC{"Keep, retrain,\nor rollback?"}
  DEC --> TRAIN
  DEC --> EP
~~~

**Pitfall:** Registering a model does **not** mean an endpoint has deployed it. Assigning the `production-approved` alias also does **not** mean requests have shifted to that version. Consider a model "live" only after checking the **Endpoint/DeployedModel configuration and traffic split**.

### 1.1. Should Every Model Use Model Registry?

| Scenario | Management Approach |
| --- | --- |
| Team-trained sklearn/PyTorch/TensorFlow model | Registry + artifacts + serving container |
| AutoML model on Vertex AI | Read/register/deploy via Registry per supported type |
| BigQuery ML models | Can link/register with Registry via corresponding BigQuery ML mechanisms |
| Open Model Garden models | Product-dependent: upload/deploy or use managed API; do not assume a single lifecycle |
| Gemini API models like Gemini Flash | Managed foundation-model API with its **own model identifiers/release lifecycle**, not uploaded per-version as custom models |
| One-off notebook experiment | May not need deployment yet, but still record training config and evaluation if reproducibility is needed |

**Do not substitute Artifact Registry for Model Registry.** Artifact Registry stores **container images/dependencies**; Model Registry manages **model versions, provenance, and deployment relationships**. Both should be used together.

## 2. Getting Resource Names Right

~~~mermaid
flowchart TD
  PROJ["Google Cloud project + location"] --> M["Model: fraud-detector\nprojects/.../models/MODEL_ID"]
  M --> V1["Version ID: 1\nalias: stable, default"]
  M --> V2["Version ID: 2\nalias: candidate"]
  M --> V3["Version ID: 3\nalias: experimental"]
  EP["Endpoint: fraud-api"] --> D1["DeployedModel ID: 111\nmodelVersionId: 1"]
  EP --> D2["DeployedModel ID: 222\nmodelVersionId: 2"]
  V1 -. "model@1" .-> D1
  V2 -. "model@2" .-> D2
  D1 --> TS["Traffic split:\n90% → 111; 10% → 222"]
  D2 --> TS
~~~

### 2.1. Resource Paths and Version Selectors

Example with project `LAB_PROJECT_ID`, location `us-central1`, parent model ID `1234567890123456789`:

~~~text
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789

projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@1
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@2
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@candidate
projects/LAB_PROJECT_ID/locations/us-central1/models/1234567890123456789@default
~~~

- **Parent model ID** identifies a model family/resource.
- **Version ID** is assigned by Vertex AI (e.g., `1`, `2`), pointing to a specific version.
- **Alias** is a **movable** pointer name for a version. A model version can hold multiple aliases.
- If `@version` or `@alias` is omitted on certain Model APIs, they resolve **`default`**.
- **Endpoint ID** differs from model ID; **DeployedModel ID** differs from both and is used in `traffic_split`.

**All IDs above are illustrative.** After uploading, always obtain the real model ID/version ID from the response or `gcloud ai models list-version`.

### 2.2. How Do Aliases Differ from Labels?

| Concept | Example | Meaning |
| --- | --- | --- |
| Version ID | `2` | Identifier of a registered version |
| `default` alias | Points to v1 or v2 | Default version when no version is specified |
| Custom alias | `candidate`, `reviewed` | Convenient workflow pointer |
| Labels | `team=fraud`, `env=lab` | Metadata for filtering/governance/cost allocation |
| Version description | `features-v4, training dataset 2026-11` | Human-readable context |
| Endpoint deployed model | `id=222; modelVersionId=2` | Running prediction instance inside an endpoint |

**Alias rules:**

- Within each **Model**, an alias points to **at most one version** at a time; moving an alias detaches it from the prior version.
- **`default`** is assigned to the first version and **there is always exactly one** default per model.
- Custom aliases are non-numeric strings of lowercase letters/digits/hyphens; avoid numeric aliases like `123` which invite confusion with version IDs.
- API formatting rule: `[a-z][a-z0-9-]{0,126}[a-z0-9]`. Use `candidate` or `production-ready`, not `v_2`.
- Aliases are **mutable pointers**, not immutable approvals. Audit alias changes and require separate approval.

**Example:** `candidate` might point to v2 today and v3 next week. For reproducible deployments, record explicit `model@2` and artifact/container digests in the release manifest rather than only `model@candidate`.

## 3. What Does a Model Version Contain?

A version represents **a set of artifacts and serving configuration** alongside metadata enabling reproduction of how the model was created. Typically needed:

| Component | Example/Source | Why Record |
| --- | --- | --- |
| Parent model & version | `fraud-detector@2` | Exact release identification |
| Artifact URI | `gs://YOUR_BUCKET/models/fraud/v2/` | Weights, vocabulary, preprocessing assets |
| Artifact checksum/manifest | Per-file SHA-256 + object version | Prevent overwritten GCS paths serving different bytes |
| Serving container image | `REGION-docker.pkg.dev/.../predictor@sha256:DIGEST` | Reproducible runtime code/libraries |
| Training code | Git commit SHA | Know exact algorithm and preprocessing |
| Training dataset | Snapshot/version ID, BigQuery snapshot, hash | Distinguish retraining runs |
| Feature schema | `schema-v4` with names/types/order | Prevent prediction/serving skew |
| Hyperparameters & seed | Learning rate, class weights, seed | Reproduce results closely |
| Evaluation | PR-AUC, precision/recall, p95 latency, slice fairness | Compare/approve |
| Security & ownership | Owner, classification, approval, expiration | Governance |
| Deployment manifest | Endpoint/DeployedModel IDs, traffic, timestamp | Verifiable rollback |

**Distinguish clearly:**

- **Model artifact**: actual model files in storage; Registry does not guarantee object URI immutability if the bucket allows overwrites.
- **Serving container**: image satisfying the prediction contract (health/predict routes, port, runtime). Uploading a container **does not** prove the container starts cleanly.
- **Experiment**: a training run with metrics/params; not every run belongs as a production version.
- **Model evaluation**: comparison against baselines and standard datasets; metrics belong to a specific dataset/split and version.
- **Model card**: document detailing intended limits, risks, owner, training data, fairness, and security. Registry does not write a complete model card automatically.

### 3.1. When Should You Create a New Version?

Create a **new version** whenever changes can affect predictions or runtime, such as weights, algorithm, preprocessing, feature order, training dataset/version, serving image, or output contract. Editing a description/alias to mark status **does not** replace creating a model version when artifacts change.

**Never overwrite the same `gs://.../model.pkl`** to pretend it is a new version. Use immutable/object-versioned artifact paths, record checksums, and pin serving containers by digest instead of tags like `latest`.

## 4. Governance Model Across Stages

Example promotion workflow:

| Business State | Permissions / Gate | Suggested Alias |
| --- | --- | --- |
| Training complete | Pipeline uploads artifacts, schema/unit tests pass | `candidate` |
| Evaluated | Offline metrics and quality checks approved | `reviewed` |
| Staging | Smoke tests, integration, latency verified | `staging-ready` |
| Production approved | Human/CI approval, model card finalized | `production-ready` |
| Serving canary | One DeployedModel receives 5–10% traffic | Do not infer from alias |
| Serving stable | Endpoint shifts 100% to approved version | `default` may point here if policy dictates |
| Retired | Undeploy, keep metadata per retention, controlled delete | Clear old alias/update state per policy |

**Model Registry does not enforce these stages automatically**: aliases are just mutable metadata, not an approval workflow engine. You need CI/CD, IAM, audit logs, runbooks, and separation of duties between model publishers and production approvers.

### 4.1. Recommended Release Pipeline

~~~mermaid
flowchart TD
  TRAIN["Train + evaluate\nVertex AI Pipeline"] --> GATE{"Metrics / fairness /\nschema / security pass?"}
  GATE -- "No" --> HOLD["Save experiment artifact\nDo not promote"]
  GATE -- "Yes" --> REG["Upload new version\nRegistry + provenance"]
  REG --> APPROVE["Approval + reviewed alias"]
  APPROVE --> STAGING["Deploy explicit version to staging\nSmoke + load tests"]
  STAGING --> CANARY["Production Endpoint\n5% candidate / 95% stable"]
  CANARY --> HEALTH{"Latency, errors,\nquality, drift OK?"}
  HEALTH -- "No" --> RB["Traffic rollback\nstable 100%"]
  HEALTH -- "Yes" --> PROMOTE["Gradually increase 20% → 100%\nrecord exact version"]
~~~

**Promotion must never break traceability:** record full version ID, metrics snapshot, Git SHA, dataset version, and an approval record. Never auto-approve based solely on a single metric that fluctuates across datasets.

## 5. Safe Lab Preparation

| Detail | Illustrative Value |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Region | `us-central1` (use only if supported for lab model/serving) |
| Display name | `fraud-detector-lab` |
| Parent model ID | `MODEL_ID_FROM_UPLOAD` |
| Model artifact | `gs://YOUR_BUCKET/models/fraud/v1/` |
| Serving image | `us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST` |
| Alias | `candidate` / `production-ready` / `default` |
| Endpoint ID | `ENDPOINT_ID_FROM_CREATE` |
| DeployedModel IDs | `DEPLOYED_V1_ID`, `DEPLOYED_V2_ID` |

Uppercase strings are placeholders, **not existing resources**. GCP IAM, billing, Artifact Registry access, Cloud Storage, region, and quotas must be confirmed before creating models/endpoints. **Deploying online prediction consumes billable compute** even with low traffic; labs without budget should run only the simulation section.

### 5.1. Read-Only Preflight with gcloud

~~~bash
# Makes no changes; run with an authorized test identity
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

gcloud ai models list \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai endpoints list \
  --project=LAB_PROJECT_ID --region=us-central1

# If a model already exists, substitute actual MODEL_ID:
gcloud ai models list-version MODEL_ID \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai models describe MODEL_ID@2 \
  --project=LAB_PROJECT_ID --region=us-central1

# If an endpoint already exists:
gcloud ai endpoints describe ENDPOINT_ID \
  --project=LAB_PROJECT_ID --region=us-central1
~~~

`describe MODEL_ID@2` may return `NOT_FOUND` before version 2 exists; that just means lab data is not there yet, not a system failure requiring Project Owner. Check `aiplatform.models.list/get` and `aiplatform.endpoints.get/list` permissions at the right scope.

### 5.2. IAM Permissions and Identity

| Principal | Typical Permissions | Recommendation |
| --- | --- | --- |
| Training/pipeline SA | `aiplatform.customJobs.create`, model upload/get, GCS artifact write | Allow train/upload, **not** direct prod deploy |
| Model reviewer | model get/list, evaluation/metadata read | No model delete needed |
| Release operator | `aiplatform.endpoints.deploy` and traffic updates, model get | Scope strictly to assigned project endpoints |
| Prediction caller | `aiplatform.endpoints.predict` | No model upload/admin needed |
| Serving runtime SA | Read artifacts/secrets needed by container | Dedicated service account, never embed keys |
| Cleanup operator | Approved model delete/undeploy | Never delete actively serving models |
| Auditor | Read-only IAM/metadata, logging/approval | No mutable permissions |

Predefined role `roles/aiplatform.user` grants broader permissions than read/predict in several workflows; production can use **custom roles** and Resource Manager IAM Conditions where supported. Cloud Storage buckets, Artifact Registry images, and Vertex AI Model resources are **three distinct permission surfaces**.

**Do not grant service-agent roles to users or arbitrary runtime SAs.** Use ADC on Cloud Run/GKE, Workload Identity Federation, and product-managed service identities. Never upload service account JSON keys into notebooks.

## 6. Registering the First Version in Model Registry

To upload a **custom model**, prepare **model artifacts** and a **serving container** supported by Vertex AI. A lone `model.pkl` file cannot serve predictions if the container lacks matching preprocessing, libraries, and an endpoint handler.

### 6.1. Preparing Verifiable Artifacts

~~~text
gs://YOUR_BUCKET/models/fraud/v1/
  model.joblib
  feature_schema.json
  preprocessing.json
  model_manifest.json

Serving image:
  us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST
~~~

Example `model_manifest.json` generated by CI:

~~~json
{
  "model_family": "fraud-detector",
  "release": "candidate-20261119",
  "training_git_sha": "EXAMPLE_GIT_SHA",
  "dataset_snapshot": "bq-snapshot-20261117",
  "feature_schema_version": "4",
  "artifact_sha256": "EXAMPLE_SHA256",
  "serving_image_digest": "sha256:EXAMPLE_DIGEST",
  "evaluation_id": "eval-20261119-01",
  "owner": "ml-platform-team"
}
~~~

`EXAMPLE_*` values are placeholders only. Store manifests and checksums with each release; simply having a manifest **does not make the entire GCS bucket immutable**. Protect artifacts with IAM, retention/object versioning, and avoid overwriting released paths.

### 6.2. Uploading a Model with gcloud

~~~bash
# MODIFIES Vertex AI Model Registry: LAB project only, requires real artifacts/image.
# Model resource region and artifact read permissions must be valid.
gcloud ai models upload \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --display-name=fraud-detector-lab \
  --artifact-uri=gs://YOUR_BUCKET/models/fraud/v1/ \
  --container-image-uri=us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST \
  --version-description="baseline features-v4, evaluation approved for lab" \
  --version-aliases=baseline
~~~

Without `--parent-model`, this command **creates a new Model resource**, giving its first version the `default` alias. It may run as a long-running operation; capture the **actual MODEL_ID** from the response/Model Registry. `--version-aliases=baseline` is an optional alias alongside `default`.

If the image uses only a mutable tag or the artifact path does not exist, upload may fail. The serving container contract (health/predict routes, port, artifact loading) must match framework/Vertex AI prediction requirements. **Upload success does not prove the model can serve predictions.**

### 6.3. Reading Back Model ID and Version ID

~~~bash
# Read-only, creates/deploys nothing
gcloud ai models list \
  --project=LAB_PROJECT_ID --region=us-central1

# Replace MODEL_ID obtained from registry
gcloud ai models list-version MODEL_ID \
  --project=LAB_PROJECT_ID --region=us-central1

gcloud ai models describe MODEL_ID@1 \
  --project=LAB_PROJECT_ID --region=us-central1
~~~

Metadata fields to confirm: model resource name, version ID, version aliases, `artifactUri`, container image, description, timestamps, and linked training/evaluation metadata if present. **Display names are not guaranteed unique**: two distinct model resources can share the same display name. Always record full resource IDs.

## 7. Creating a New Version Instead of a New Model Family

When retraining the fraud detector on fresh data or a new feature schema, register **version 2 under the same parent model** so versions can be compared and managed as one family.

### 7.1. Uploading Version 2 with gcloud

~~~bash
# MODIFIES: appends a version under an existing Model resource.
# MODEL_ID and artifact URI must be verified beforehand.
gcloud ai models upload \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --parent-model=projects/LAB_PROJECT_ID/locations/us-central1/models/MODEL_ID \
  --display-name=fraud-detector-lab \
  --artifact-uri=gs://YOUR_BUCKET/models/fraud/v2/ \
  --container-image-uri=us-central1-docker.pkg.dev/LAB_PROJECT_ID/ml-images/predictor@sha256:REAL_DIGEST_V2 \
  --version-aliases=candidate \
  --version-description="candidate: new training data, threshold calibration v2"
~~~

**The key difference is `--parent-model`**. Without it, the command creates a brand-new Model resource instead of version 2 in the same family. The actual version ID is API-generated—**never assume it is always 2** (for example, if an earlier version was deleted).

If a training job auto-registers versions into Model Registry, the parent model parameter must also be passed in that training workflow. Do not upload twice manually.

### 7.2. Doing the Same via Python SDK

Example using the `google-cloud-aiplatform` SDK, authenticated via ADC with artifacts already staged:

~~~python
from google.cloud import aiplatform

PROJECT = "LAB_PROJECT_ID"
LOCATION = "us-central1"
MODEL_ID = "MODEL_ID"   # Replace with actual ID after registering v1

aiplatform.init(project=PROJECT, location=LOCATION)

model = aiplatform.Model.upload(
    display_name="fraud-detector-lab",
    artifact_uri="gs://YOUR_BUCKET/models/fraud/v2/",
    serving_container_image_uri=(
        "us-central1-docker.pkg.dev/LAB_PROJECT_ID/"
        "ml-images/predictor@sha256:REAL_DIGEST_V2"
    ),
    parent_name=(
        f"projects/{PROJECT}/locations/{LOCATION}/models/{MODEL_ID}"
    ),
    version_aliases=["candidate"],
    version_description="features-v4; calibrated threshold; lab test",
    is_default_version=False,
)

print("Registered model resource:", model.resource_name)
~~~

`parent_name` attaches the new version under the existing model; `is_default_version=False` **does not move `default`** away from the currently chosen version. This call **creates a real version**, so do not run it against a production project without approval.

### 7.3. Listing Versions via Python SDK

~~~python
from google.cloud import aiplatform

aiplatform.init(project="LAB_PROJECT_ID", location="us-central1")
registry = aiplatform.models.ModelRegistry(model="MODEL_ID")

versions = registry.list_versions()
for item in versions:
    print(item)

# Replace VERSION_ID from list output:
version_info = registry.get_version_info(version="VERSION_ID")
print(version_info)
~~~

This snippet only **reads Model Registry** but requires the package, ADC, and permissions. Never print entire model artifacts or sensitive training data to logs.

## 8. Aliases, Switching Default, and Approval Workflows

### 8.1. Aliases Are Not a Production Safety Lock

Suppose initially:

| Model Version | Aliases | Business State |
| --- | --- | --- |
| v1 | `default`, `production-ready` | Currently approved |
| v2 | `candidate` | Under testing |
| v3 | `experimental` | Below target metrics |

After offline evaluation, an authorized owner may **move `production-ready` to v2**. That only updates **registry metadata**. If the endpoint is running `DeployedModel ID 111` (v1), traffic **does not automatically shift** to v2 just because the alias moved.

**Safe sequence:** approve v2 → deploy explicit v2 → canary → measure → 100% v2 → update `default/production-ready` per policy → update release manifest. You may set `production-ready` after approval and before deployment if your contract defines it as "ready," but **never call it "serving."**

### 8.2. Console Operations

1. Open **Model Registry** in Google Cloud Console (UI may appear under Agent Platform).
2. Select the right **project/region** and **Model resource**, and open the versions list.
3. Select the evaluated version and use **Edit alias / Add alias** to add `reviewed` or move `candidate`.
4. When permitted, click **Set as default** to point `default` to the approved version.
5. Re-read the versions list and audit events; do not rely solely on a "Saved" toast.
6. Inspect the endpoint separately to see which version actually receives prediction traffic.

**Warning:** `default` must always exist and be unique within a Model resource. Moving `default` can cause **future unpinned deploy commands** to pick a different version; therefore CI/CD should always pin `@VERSION_ID`.

### 8.3. Distinguishing Alias Changes from Real Rollback

~~~text
Registry:
  default  ──> v2
  candidate ──> v3

Endpoint:
  DeployedModel 111 ──> v1, 90% traffic
  DeployedModel 222 ──> v2, 10% traffic
~~~

If you move the `default` alias back to v1 while the **traffic split stays 90/10**, the endpoint keeps serving v1/v2 at that split. **A true rollback means shifting Endpoint traffic** back to the verified DeployedModel, and only then updating aliases/metadata if process requires. This state is reflected in `Endpoint.deployedModels[*].modelVersionId` and `Endpoint.trafficSplit`.

## 9. Evaluating Versions Before Serving Traffic

A model with higher F1 is not automatically worth deploying: it might add latency, lack explainability, raise false positives on a critical segment, or depend on features unavailable in production.

### 9.1. Reference Quality Gate

| Metric | v1 Baseline (hypothetical) | v2 Candidate (hypothetical) | Condition |
| --- | ---: | ---: | --- |
| Holdout PR-AUC | 0.81 | 0.84 | No regression |
| Recall at precision ≥ 0.95 | 0.64 | 0.68 | Improves or meets threshold |
| False positive rate for risk group | 1.4% | 1.2% | Within fairness limit |
| Predict latency p95 | 110 ms | 138 ms | ≤ 160 ms |
| Memory/container | 1.2 GiB | 1.8 GiB | Fits machine/replicas |
| Feature schema | v3 | v4 | Backend already deployed v4 |
| PII compliance | PASS | PASS | Non-negotiable |
| Training reproducibility | PASS | PASS | Manifest + dataset snapshot |

**These are not mandatory Vertex AI standards.** Thresholds must be set by business and ML owners based on fraud prevalence, false positive cost, drift, and SLOs. High accuracy alone on an imbalanced dataset is insufficient.

### 9.2. Pre-Deploy Tests

- **Unit/schema tests:** input/output shapes, missing values, unknown categories, timezones, numeric ranges.
- **Offline tests:** time-split holdout free of training leakage; PR-AUC, calibration, class-weighted metrics.
- **Slice/fairness tests:** by customer type, region, or meaningful business group, respecting privacy policies.
- **Security tests:** serving image vulnerabilities, dependencies, secret handling, IAM.
- **Integration tests:** compatible API/feature store/serving container versions.
- **Load tests:** throughput, p95/p99, cold start, autoscaling, memory/GPU quota.
- **Approval record:** approver, timestamp, version, metrics report URI, ticket ID.

Store evaluations using Vertex AI Model Evaluation and Vertex AI Experiments/ML Metadata where supported by the model type and infrastructure. Never paste test metrics into a description without recording the **evaluation dataset and methodology**, since numbers from different samples cannot be compared.

## 10. Deploying an Explicit Version to an Endpoint

An **Endpoint** is the resource receiving prediction requests. Deploying a model version to an endpoint creates a **DeployedModel** with its own ID; an endpoint can host multiple DeployedModels concurrently when supported and compute quota allows.

### 10.1. Creating an Endpoint (Lab, Deployment Incurs Charges)

~~~bash
# MODIFIES resources, lab project only
gcloud ai endpoints create \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --display-name=fraud-detector-lab-endpoint
~~~

Capture the actual `ENDPOINT_ID` from the output; never assume the display name is the ID.

### 10.2. Deploying v1 by Version ID

~~~bash
# CREATES DeployedModel and provisions serving machines (BILLABLE).
# MODEL_ID@1 is illustrative; use an actual approved VERSION_ID.
gcloud ai endpoints deploy-model ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --model=MODEL_ID@1 \
  --display-name=fraud-v1 \
  --machine-type=n1-standard-4 \
  --min-replica-count=1 \
  --max-replica-count=2
~~~

Verify that the custom model/container supports `n1-standard-4`, machine quota, and region. Some models require different GPUs/memory/images. **An endpoint with an active deployment generally incurs compute costs even with minimal requests.**

### 10.3. Deploying v2 Without Sending Production Traffic Yet

~~~bash
# MODIFIES endpoint: adds candidate DeployedModel (BILLABLE).
# Verify deploy/traffic flags on your installed gcloud version first.
gcloud ai endpoints deploy-model ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --model=MODEL_ID@2 \
  --display-name=fraud-v2-candidate \
  --machine-type=n1-standard-4 \
  --min-replica-count=1 \
  --max-replica-count=2 \
  --traffic-split=DEPLOYED_V1_ID=100
~~~

**Note:** `DEPLOYED_V1_ID` must be the **existing DeployedModel ID** (not the model version ID), and the endpoint must already host v1. The traffic split flag on a deploy call can **overwrite the existing map**; inspect the endpoint and verify CLI/API behavior before using in production. To hold v2 at 0% before canarying, confirm the endpoint allows deployments **receiving zero traffic** and test explicit routing by DeployedModel ID where supported.

### 10.4. Verifying Deployed Version IDs

~~~bash
# Read-only
gcloud ai endpoints describe ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1
~~~

Look for these fields in the output:

~~~yaml
# ILLUSTRATIVE EXAMPLE, not a real project response
deployedModels:
  - id: "111"
    displayName: fraud-v1
    model: projects/LAB_PROJECT_ID/locations/us-central1/models/MODEL_ID
    modelVersionId: "1"
  - id: "222"
    displayName: fraud-v2-candidate
    model: projects/LAB_PROJECT_ID/locations/us-central1/models/MODEL_ID
    modelVersionId: "2"
trafficSplit:
  "111": 100
  "222": 0
~~~

**The source of truth for online releases is `modelVersionId` inside DeployedModel and `trafficSplit`**, not the `default` alias. This is a structural example; real API responses include machine/resource specs, state, and annotations.

## 11. Canary Rollouts and Rollbacks via Traffic Split

A common strategy:

| Stage | v1 Deployed ID 111 | v2 Deployed ID 222 | Gate to Advance |
| --- | ---: | ---: | --- |
| Stable | 100% | 0% | v2 ready |
| Canary 1 | 95% | 5% | Latency, errors, skew verified |
| Canary 2 | 80% | 20% | No SLO regression |
| Promote | 0% | 100% | Approval and metrics met |
| Rollback | 100% | 0% | Stop condition/alert triggered |

### 11.1. Shifting Traffic at the Endpoint Level

~~~bash
# MODIFIES PRODUCTION TRAFFIC if the endpoint is production.
# Substitute exact DeployedModel IDs from endpoint describe.
gcloud ai endpoints update ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --traffic-split=111=95,222=5
~~~

The syntax uses **DeployedModel IDs**, here `111/222`. Do not pass `@1`, `@candidate`, or Model Registry version IDs instead. Percentages must sum to **100**. Record the prior split before changing so you can roll back quickly.

### 11.2. Rollback Must Work When Needed

~~~bash
# MODIFIES traffic; only if v1 remains deployed, healthy, and has capacity
gcloud ai endpoints update ENDPOINT_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1 \
  --traffic-split=111=100,222=0
~~~

After rollback:

1. Re-read `Endpoint.trafficSplit` and `deployedModels[*].modelVersionId`.
2. Send a **synthetic inference** through the endpoint and check response/error/latency.
3. Inspect dashboards and metrics broken down by **DeployedModel**.
4. Account for in-flight requests; do not assume every call prior to the switch used v1.
5. Log the incident/canary outcome; keep v2 briefly for investigation rather than deleting hastily.
6. Optionally move `default`/`production-ready` aliases back to v1 per policy **after** traffic stabilizes.

**Never undeploy v1 the moment a canary begins.** It is your rollback target. Equally, do not leave both models serving 24/7 indefinitely without reason, since both consume serving resources.

### 11.3. Version Aliases Are Deploy Inputs, Not Traffic Routers

Google Cloud Model APIs accept `model@2` or `model@golden` when accessing or deploying a version. Once deployed, the API exposes **`DeployedModel.modelVersionId`** as an output-only field showing the actual version ID. Therefore:

- Identify releases by **version ID** in manifests.
- You may use an alias to locate a candidate, but **resolve the alias before deploying** and verify the output.
- Do not assume moving an alias makes a deployed runtime hot-swap weights or redirect requests to another version.
- Rolling back to an already-undeployed version requires **redeploying** it, costing provisioning time and quota; moving an alias does not recreate compute resources.

## 12. Post-Deployment Model Observability

A model with strong offline metrics can still fail in production due to **feature skew**, seasonal shifts, schema mismatches, timeouts, or missing dependencies in the serving image. Monitoring must cover **both infrastructure and model quality**.

### 12.1. Three Signal Categories

| Category | Metrics / Evidence | Action |
| --- | --- | --- |
| **Serving SLO** | Requests/s, 4xx/5xx, p50/p95/p99 latency, CPU/memory, accelerator utilization, autoscaling | Inform canary/rollback |
| **Data quality/skew/drift** | Null/unknown feature rate, schema mismatch, feature distribution vs training/reference | Check input pipeline/retrain |
| **Business/model quality** | Precision/recall/F1, calibration, false positive cost, fairness slices once ground truth arrives | Assess quality/version promotion |

**Skew differs from drift:** skew compares **training vs serving** data/features; drift measures input distribution shifts **over time**. They are related but distinct; without ground-truth labels, drift scores **cannot prove** whether the model is accurate or wrong.

### 12.2. Statistically Meaningful Canaries

If v2 gets 5% traffic totaling only 10 requests, seeing zero errors is insufficient to promote. Design requires:

- Minimum duration/sample size scaled to traffic volume and baseline failure rate.
- Comparison per **DeployedModel ID**, not just endpoint aggregates.
- Inspection across key user segments and peak/off-peak hours.
- Defined p95/p99 and error budgets prior to rollout.
- **Delayed labels:** fraud detection may take days to collect ground truth; never use a few minutes of canary traffic to claim superior production PR-AUC.
- If routing is non-random (e.g., canary limited to internal users), note selection bias in conclusions.

When deploying a new version on the same endpoint, ensure dashboards/observability distinguish version IDs and traffic weights. Prediction logging can capture customer data; enable it per **retention/PII policies** and sample appropriately.

### 12.3. Quality Degradation Runbook

~~~text
Alert: production model degradation
  1. Identify which Endpoint ID and DeployedModel ID are affected.
  2. Check recent rollouts, feature schema changes, or source data changes.
  3. Classify: serving error/latency, drift, or business metric drop.
  4. If rollback gate breached: shift traffic back to deployed stable.
  5. Verify trafficSplit, inference responses, p95, and 5xx rates.
  6. Save metrics and version manifest; do not delete the candidate immediately.
  7. Root cause → fix data/code → create a new version to re-evaluate.
~~~

Never silently **overwrite artifacts at the same URI** to "hot-patch a live model." That destroys release verifiability and causes inconsistent behavior across replicas/caches.

## 13. Cost and Security in the Model Registry Lifecycle

### 13.1. Total Cost Extends Beyond the Registry

| Layer | Cost Item | Cost Control |
| --- | --- | --- |
| Training/tuning | Custom training CPU/GPU/TPU, pipelines | Scheduled/on-demand runs, quota limits |
| Artifacts | GCS bytes, object versions, network egress | Approved retention, avoid unbounded duplication |
| Container images | Artifact Registry storage/scanning | Pin digests, retention, and image cleanup |
| Online inference | Dedicated endpoint replicas/machines/accelerators | SLO-based autoscaling, undeploy unused models |
| Batch prediction | Job compute/output storage | Scheduled batches with deadlines, avoid redundant runs |
| Evaluation/monitoring | Model Monitoring, BigQuery logs, metadata, alerts | Sampling, retention, budgets |
| Networking | Cross-region traffic, private networking, egress | Co-locate with data/clients, check residency |

Do not assume "only switching an alias is free" if you previously deployed an extra DeployedModel holding serving machines. Conversely, a version **only registered and not deployed** generally incurs no online serving compute; storage and related component charges still apply.

### 13.2. Sensitive Data Surfaces

- **Training data:** PII/secrets, consent, data residency, and retention.
- **Feature logs:** request/response payloads may contain customer data; apply masking/sampling.
- **Model artifacts:** can memorize or leak training patterns; restrict GCS access and downloads.
- **Containers:** control dependencies, image provenance, malware/vulnerability scans.
- **Registry metadata:** version descriptions, experiment links, and labels must never contain credentials.
- **Serving endpoints:** enforce IAM authentication, network restrictions, and rate limits; never leave APIs public outside policy.

**IAM distinction:** someone permitted to list/read model metadata does not automatically get access to read the training dataset or download all GCS objects. Each layer has separate IAM; conversely, granting broad `roles/storage.objectViewer` on the artifact bucket can bypass Registry access intent.

## 14. Retention, Archiving, and Safe Version Deletion

Never delete a version serving as a rollback target before the canary and support window conclude. Equally, do not keep every endpoint deployment running forever as it incurs ongoing costs.

### 14.1. Retirement Workflow

1. Identify the version ID, aliases, and **all endpoints deploying that version**.
2. Ensure live traffic to the version being retired is **0%** and a stable replacement is active.
3. **Undeploy** the DeployedModel from endpoints within a change window; verify zero dependent callers remain.
4. Archive the model card, training/eval provenance, and release manifests per retention rules.
5. Confirm the model version is **not** needed for batch prediction, scheduled jobs, or rollback.
6. Delete the version only after approval; check side effects on evaluation records/aliases.
7. Audit GCS artifacts, container images, logs/monitoring, and IAM separately; **deleting a registry version does not prove all artifact copies were deleted**.

### 14.2. Destructive Command — Example Only

~~~bash
# WARNING: DELETES VERSION, DO NOT RUN IN PRODUCTION
# Only after undeploying, confirming VERSION_ID, and obtaining approval.
gcloud ai models delete-version MODEL_ID@VERSION_ID \
  --project=LAB_PROJECT_ID \
  --region=us-central1
~~~

Deleting an **entire Model resource** removes all associated versions/evaluations, and a currently deployed model cannot be deleted before undeploying. Deleting a version holding the `default` alias may cause the service to reassign `default` to another remaining version; never rely on this behavior for promotion. **Never** delete a version as a way to roll back traffic.

## 15. Simulation Lab — Zero Cloud Resources Required

This simulation clarifies the independence between **aliases** and **Endpoint traffic** before touching real infrastructure. Run with standard Python in a lab environment if permitted; **calls no Google Cloud APIs and creates no billable machines**.

### 15.1. Scenario

- Registry holds `fraud-detector` with v1/v2.
- `default` points to v1, `candidate` points to v2.
- Endpoint hosts DeployedModel ID 111 = v1; ID 222 = v2.
- Initial traffic is 90% v1 and 10% v2.
- An approver moves `default` from v1 to v2 without touching the endpoint.

**Question:** What percentage of requests continue hitting v1? **Answer: 90%**.

### 15.2. Standalone Python Simulation Code

~~~python
# Does not use Vertex AI SDK; simulates pointers only.
from dataclasses import dataclass

@dataclass(frozen=True)
class ModelVersion:
    version_id: int
    pr_auc: float

versions = {
    1: ModelVersion(version_id=1, pr_auc=0.81),
    2: ModelVersion(version_id=2, pr_auc=0.84),
}
aliases = {"default": 1, "candidate": 2}
deployed_models = {111: 1, 222: 2}  # DeployedModelID -> versionID
traffic_split = {111: 90, 222: 10}

def serving_distribution(split):
    assert sum(split.values()) == 100, "Traffic must sum to 100%"
    return {
        deployed_models[deployment_id]: percent
        for deployment_id, percent in split.items()
    }

print("Before:", serving_distribution(traffic_split))
aliases["default"] = 2
print("After moving default:", serving_distribution(traffic_split))

# Canary approved -> change traffic on Endpoint (not Registry)
traffic_split = {111: 80, 222: 20}
print("Canary:", serving_distribution(traffic_split))

# Serving error -> rollback Endpoint
traffic_split = {111: 100, 222: 0}
print("Rollback:", serving_distribution(traffic_split))
~~~

Expected output:

~~~text
Before: {1: 90, 2: 10}
After moving default: {1: 90, 2: 10}
Canary: {1: 80, 2: 20}
Rollback: {1: 100, 2: 0}
~~~

**Simulation limits:** Does not model provisioning, real request routing, rolling-window traffic weights, or endpoint API consistency. The goal is verifying **the right identifier types and state-transition logic**.

### 15.3. Optional Vertex AI Sandbox Lab

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Verify project, region, Vertex AI API, billing/quota | Read-only screenshot or command output |
| 2 | List Models/versions with `gcloud ai models list/list-version` | Actual Model ID, version IDs |
| 3 | Compare v1/v2 metadata | Artifact URIs, serving image, descriptions |
| 4 | Review model card and approval | Explicit metrics + dataset/slice details |
| 5 | Assign `candidate` then move `default` in **lab** | Alias table before/after |
| 6 | If approved, create Endpoint + two deployments | DeployedModel IDs and `modelVersionId` |
| 7 | Canary 95/5, then 80/20 once metrics hold | Actual `trafficSplit` and dashboards |
| 8 | Simulate hypothetical fault, rollback 100/0 | Config readback after rollback |
| 9 | Calculate endpoint/GCS/Artifact Registry cost | Estimate and Billing |
| 10 | Clean up after approval; never delete shared models | Zero idle billable deployments left |

**Never intentionally break an endpoint or send excessive fuzz/load traffic just to trigger errors.** Without a sandbox, completing the simulation in Section 15.2 and the evaluation table suffices.

## 16. Common Error Matrix

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| `PERMISSION_DENIED` on upload | Missing `aiplatform.models.upload` or GCS/image access | Runtime SA, bucket IAM, Artifact Registry |
| Upload creates new model instead of version | Forgot `--parent-model`/`parent_name` | Actual Model ID, upload request |
| Model list shows duplicate names | Display names are not unique | Use resource ID, project/region |
| Using numeric alias like `2` | Confused version ID and alias format | Use alphabetic custom aliases; use `@2` when targeting version |
| Moved alias but predictions unchanged | Endpoint DeployedModel unchanged | `Endpoint.trafficSplit`, `modelVersionId` |
| Deployed unexpected version | Omitted `@version` so `default` was used | Pin `model@VERSION_ID` and read back |
| DeployedModel 403 | Caller lacks `endpoints.predict` | Caller IAM; do not grant upload rights |
| Container unhealthy | Wrong health/predict route, missing dependency/artifact | Container logs, serving contract |
| p95 error/latency spikes in canary | v2 heavier, insufficient CPU/GPU, slow feature fetch | Per-version/replica p95 and quotas |
| Good offline metrics, prod failures | Feature schema/skew, leakage, or drift | Dataset snapshots, serving input validation |
| Cannot delete model/version | Still deployed on an endpoint | Describe endpoint, undeploy with approval |
| Rolled back to wrong version | Passed Model version ID instead of DeployedModel ID | Endpoint describe and ID mapping |
| Costs rise after promotion | Two deployments left running concurrently for days | Billing, min replicas, cleanup |
| GCS artifact URI changed silently | Overwrote object/tag without checksum | Manifest, object generation, image digest |

**Investigation order:** project/region → Model resource/version ID → alias/default → artifact/container → Endpoint/DeployedModel ID → traffic split → IAM/network → metrics/data quality → cost.

## 17. Review Questions

1. **What is Model Registry used for?** Managing model version collections, metadata, evaluations, and deployment readiness.
2. **How do Model resource and model version differ?** The resource is the parent/family; a version is a distinct artifact/config snapshot inside it.
3. **Why not overwrite `model.pkl`?** Destroys reproducibility, breaks rollback and auditing.
4. **How do Version ID and alias differ?** Version ID permanently identifies a version; an alias can be moved to another version.
5. **Does `default` always point to the latest version?** No; it can be moved and must be verified.
6. **How many `default` aliases can one model have?** Exactly one.
7. **Can two versions of the same Model hold the same alias simultaneously?** No, not at the same time.
8. **Is Model version ID `2` the same as DeployedModel ID `222`?** No.
9. **Does moving an alias shift online traffic automatically?** No.
10. **Which field shows the version deployed by an Endpoint?** `deployedModels[*].modelVersionId`.
11. **Which field shows request percentages?** `Endpoint.trafficSplit`.
12. **How do you register a new version under an existing parent?** `--parent-model` or SDK `parent_name`.
13. **Why record Git SHA and dataset snapshot?** Reproduces training and explains metric differences.
14. **Why pin container digests?** Prevents mutable image tags from changing contents on redeploy.
15. **Is a higher model F1 enough to promote?** No; evaluate data, fairness, calibration, latency, and cost.
16. **Why is drift alone insufficient to judge quality?** Drift does not directly measure ground-truth correctness.
17. **What is needed to roll back if v1 was already undeployed?** Redeploying it, requiring quota/capacity and provisioning time.
18. **Can a still-deployed version be deleted?** Must undeploy first.
19. **Who should be allowed to update a production endpoint?** Approved release operators, not every training SA.
20. **Does a Model Garden model update auto-update an uploaded version?** Not by default; check/register/deploy new versions per product rules.

## 18. Production Checklist and Official Documentation

- [ ] Model family, project, region, and version IDs clearly managed.
- [ ] Artifacts stored at versioned paths with checksums/object generation; containers pinned by digest.
- [ ] Training code commit, data snapshot, feature schema, hyperparameters, and evaluation ID attached.
- [ ] Meaningful Model Registry versions and descriptions/aliases maintained; never use `default` as an immutable release ID.
- [ ] Data leakage, drift, fairness, input/output schemas, and compliance reviewed before approval.
- [ ] CI/CD separates train/register/approve/deploy/predict permissions.
- [ ] Release manifest pins `model@VERSION_ID` and logs actual `DeployedModel ID`.
- [ ] Staging deployment + smoke/load tests completed before production.
- [ ] Canary has traffic percentages, sample size/observation window, and p95/error/quality gates.
- [ ] Rollback target remains deployed with sufficient capacity through the change window.
- [ ] Monitoring tracks per-version serving, feature skew/drift, and delayed labels.
- [ ] Endpoint IAM/network, serving image credentials, and logging privacy reviewed.
- [ ] Costs accounted for: training, GCS artifacts, image storage, serving replicas, monitoring, and logs.
- [ ] No Model/version/aliases/deployments deleted without reconciling dependencies and retention.
- [ ] Backup/provenance/rollback evidence, release owner, and incident runbook in place.

**Official Google Cloud sources:**

- [Introduction to Model Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/introduction) — managing custom/AutoML/BigQuery ML models.
- [Model versioning with Model Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/versioning) — upload/train/list versions.
- [How to use model version aliases](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/model-alias) — default/custom aliases and switching.
- [Delete a model or version](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/model-registry/delete-model) — undeploy, retention, and deletion risks.
- [REST: models.get](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.models/get) — `model@version`, `model@alias` syntax.
- [REST: Endpoint DeployedModel](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.endpoints) — `modelVersionId`/`trafficSplit`.
- [gcloud ai models upload](https://docs.cloud.google.com/sdk/gcloud/reference/ai/models/upload) — `--parent-model`, `--version-aliases`.
- [gcloud ai models list-version](https://docs.cloud.google.com/sdk/gcloud/reference/ai/models/list-version) — listing versions.
- [gcloud ai endpoints deploy-model](https://docs.cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model) — deploying a model version.
- [gcloud ai endpoints update](https://docs.cloud.google.com/sdk/gcloud/reference/ai/endpoints/update) — updating traffic split.
- [Vertex AI IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/aiplatform) — model/endpoint permissions.
- [Vertex AI Model Monitoring](https://docs.cloud.google.com/vertex-ai/docs/model-monitoring/overview) — skew/drift and observability.
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) — training/inference/monitoring.

**Takeaway:** **Model Registry manages versions and aliases; Endpoints manage DeployedModels and traffic.** Register non-overwritten versioned artifacts, capture complete training/evaluation provenance, pin versions on deployment, promote strictly through quality gates, and roll back via the **endpoint traffic split**. Assigning `default` or `production-ready` never substitutes for deploying or verifying which version is actually serving.

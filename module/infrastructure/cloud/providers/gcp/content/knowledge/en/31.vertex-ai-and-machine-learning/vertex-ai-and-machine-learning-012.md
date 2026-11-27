# MLOps with Artifact Registry and CI/CD on GCP

A team builds a Java `fraud-api` service on Cloud Run to detect anomalous orders. Data scientists train a Python model on Vertex AI, but after every code change, the team manually installs libraries, builds images, runs training, copies model files, and swaps the serving version. As a result, it is hard to know **which commit, data, libraries, and config** produced the production model, hard to roll back, and risky to release underperforming models.

**MLOps** unifies data management, training code, model artifacts, testing, releases, and monitoring. On Google Cloud, a common architecture is **Git → Cloud Build → Artifact Registry → Vertex AI training/pipelines → Model Registry → prediction endpoint or batch prediction**. Within this, **Artifact Registry stores containers and pipeline templates**, whereas **Vertex AI Model Registry manages model resources and versions**. They do not replace one another.

This lesson belongs to the **Vertex AI and Machine Learning** chapter of module `CLOUD_PROVIDERS_GCP`, connecting project/IAM/VPC organization with Cloud Storage, BigQuery, Cloud Run, GKE, Compute Engine, and release automation, reliability, and cost. Examples use **Python 3.11, scikit-learn, Cloud Build, and Vertex AI CustomJob**; the Java app is simply a prediction consumer. Cloud resource creation examples are strictly for a **budgeted lab project** and were not executed while writing this lesson.

## Learning Objectives

After this lesson, you can:

1. Distinguish **CI of code/model containers**, **CD of models**, **CT (continuous training)**, and **monitoring**.
2. Understand the roles of **Artifact Registry, Cloud Build, Vertex AI Pipelines, Model Registry, and Endpoints**.
3. Write tests, a Dockerfile, and `cloudbuild.yaml` to build traceable training images.
4. Use **tags to identify builds** and **image digests to execute exact vetted bytes**.
5. Grant separate permissions to the build service account, training runtime service account, and deployer.
6. Launch a **CustomJob from a built image**, saving model and metrics to Cloud Storage.
7. Design **quality gates, manual approvals, canary rollouts, and rollbacks**.
8. Monitor lineage, drift, logs, model SLOs, and **total costs** across the ML lifecycle.

## 1. End-to-End MLOps Architecture

~~~mermaid
flowchart LR
    GIT["Git commit / PR"] --> CI["Cloud Build CI<br/>test, scan, build"]
    CI --> AR["Artifact Registry<br/>training image @sha256"]
    AR --> TRAIN["Vertex AI CustomJob<br/>or Pipelines"]
    DATA[("GCS / BigQuery<br/>versioned dataset")] --> TRAIN
    TRAIN --> ART[("GCS model artifacts<br/>metrics + model")]
    ART --> GATE{"Evaluation / quality gate"}
    GATE -->|Pass + approval| REG["Vertex AI Model Registry"]
    REG --> DEPLOY["Staging → canary → production<br/>Endpoint / batch"]
    GATE -->|Fail| STOP["Do not release<br/>review/retrain"]
    DEPLOY --> MON["Monitoring: latency / drift / KPI"]
    MON -->|retrain needed| TRAIN
~~~

**Four distinct output assets to manage:**

| Asset | Typical Storage | Version Identifier |
| --- | --- | --- |
| Training code | Git | **Commit SHA** and review |
| Training/serving container | **Artifact Registry Docker repo** | Image **digest `sha256:...`** |
| Model files and metrics | **Cloud Storage** | Immutable URI, checksum, run ID, dataset version |
| Registered model | **Vertex AI Model Registry** | Model resource + **version ID/alias** |
| Pipeline template (if using KFP) | Git and **Artifact Registry KFP repository** | Template version/digest |

**Never use `trainer:latest` as a production identifier.** A tag can move to another image if the repository permits mutable tags. A digest pins exact image contents; meanwhile **model artifacts and datasets still require separate versioning**.

## 2. CI, CD, and CT: When to Trigger Each?

| Stage | Trigger | What to Do | What Not to Assume |
| --- | --- | --- | --- |
| **CI** | Pull request, merge, commit | Lint, unit tests, schema tests, build, dependency/vulnerability scan | Train expensive GPU models on every PR |
| **CD – training** | Approved merge, release tag, schedule, or controlled data drift | Run Vertex AI CustomJob/Pipeline, save metrics/model | Auto-deploy simply because job `SUCCEEDED` |
| **CD – serving** | Quality gate + human/workflow approval | Register, deploy staging, smoke test, canary, promote | Shift 100% traffic immediately |
| **CT** | New data/labels, schedule, or performance drop | Train on new snapshot, evaluate against baseline | Retrain continuously without criteria |
| **Monitoring** | Continuous | p95/p99, 5xx, skew/drift, business KPIs, costs | Assume prediction drift = model is definitely wrong |

**Cloud Build** orchestrates testing/builds/automation on Git events. **Vertex AI Pipelines** orchestrates ML stages (data prep → train → evaluate → register). **Cloud Deploy** excels at deploying applications to supported targets like Cloud Run/GKE, and **does not natively deploy Vertex Endpoint models**; for endpoints use Vertex AI APIs/CLI or a controlled pipeline.

## 3. Defining Quality and Safety Before Writing YAML

A release is accepted only when explicit gates pass:

| Gate | Example Criteria | On Failure |
| --- | --- | --- |
| Source/code | PR review, static checks, unit tests pass | Stop build |
| Data | Valid schema, non-empty data, valid labels, zero leakage | Do not train |
| Build | Container builds cleanly, dependency scan has no errors above threshold | Block promotion |
| Model | Macro-F1 ≥ approved threshold, beats baseline, tested on holdout | Keep incumbent |
| Security | Least-privilege service account, zero PII/secrets in artifacts/logs | Block deploy |
| Serving | Health, latency, error rate, and input/output schemas verified | Halt rollout |
| Business | Fraud detection uplift / false-positive impact acceptable | Hold canary or roll back |

**Never pick thresholds from test results and still claim the test set is independent.** Pick thresholds from validation/baselines and business requirements; evaluate once on the held-out test set without iterating tuning on it.

Models used in sensitive decisions also require fairness/privacy/bias evaluations, human review, and compliance checks beyond the tests shown here.

## 4. Minimal Lab Repo

This lab uses the **`digits` dataset** bundled with scikit-learn, needing no real customer data. Its purpose is learning CI/CD and artifact generation, **not proving the model is good enough for real fraud detection**.

~~~text
mlops-digits-lab/
├── src/
│   ├── __init__.py
│   └── train.py
├── tests/
│   └── test_train.py
├── requirements.txt
├── Dockerfile
├── cloudbuild.yaml
└── customjob.yaml
~~~

Each file has one job:

- `src/train.py`: train, evaluate, and export model/metrics.
- `tests/test_train.py`: test the training pipeline and output properties.
- `Dockerfile`: reproducible training environment.
- `cloudbuild.yaml`: **CI** test → build → push, without automatically launching billable training.
- `customjob.yaml`: approved **CD-training**, referencing an exact digest.

This lesson uses one training image. Production typically has a **separate serving image** to load artifacts and expose a prediction interface.

## 5. Writing Testable Training Code

`requirements.txt`:

~~~text
scikit-learn==1.5.2
joblib==1.4.2
google-cloud-storage==2.18.2
~~~

These versions are **dependency-pinning examples** for the lab; real systems must verify Python compatibility, check security advisories, and apply approved updates. Pin base-image digests and lockfiles too when strict reproducibility is required.

`src/train.py`:

~~~python
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import joblib
from google.cloud import storage
from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split


def train_once():
    features, labels = load_digits(return_X_y=True)
    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2,
        stratify=labels, random_state=42
    )
    model = RandomForestClassifier(
        n_estimators=80, random_state=42, n_jobs=2
    )
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "macro_f1": float(f1_score(
            y_test, predicted, average="macro"
        )),
        "train_rows": int(len(y_train)),
        "test_rows": int(len(y_test)),
        "seed": 42
    }
    return model, metrics


def upload_artifacts(directory: Path, gcs_uri: str):
    parsed = urlparse(gcs_uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError("AIP_MODEL_DIR must be a gs:// URI")

    bucket = storage.Client().bucket(parsed.netloc)
    prefix = parsed.path.strip("/")
    for name in ("model.joblib", "metrics.json"):
        object_name = f"{prefix}/{name}" if prefix else name
        bucket.blob(object_name).upload_from_filename(
            str(directory / name)
        )


def main():
    model, metrics = train_once()
    print(json.dumps(metrics, sort_keys=True))
    out = Path("/tmp/digits-artifacts")
    out.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, out / "model.joblib")
    (out / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    target = os.getenv("AIP_MODEL_DIR")
    if target:
        upload_artifacts(out, target)
    else:
        print("Local mode: artifacts in", out)


if __name__ == "__main__":
    main()
~~~

**Why structure it this way?** `train_once()` has zero cloud side effects and can be unit-tested cleanly. `main()` exports the model and metrics only when needed. Vertex AI CustomJob with `baseOutputDirectory` sets `AIP_MODEL_DIR`; locally this variable is unset, so nothing writes to Cloud Storage.

On real data, **never load arbitrary mutable data on every training run**: save dataset snapshots/generations and lock feature schemas, labels, time cutoffs, and preprocessing versions. The `digits` dataset here is purely a demo dataset bundled with scikit-learn.

**Artifact security:** `joblib`/`pickle` can execute code on deserialization. Load models only from trusted sources, restrict artifact read IAM, scan dependencies, and pin training–serving versions.

## 6. Unit Tests and Quality Gates Must Be Separate

`tests/test_train.py`:

~~~python
from src.train import train_once


def test_train_produces_valid_model_and_metrics():
    model, metrics = train_once()

    assert len(model.classes_) == 10
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["macro_f1"] <= 1.0
    assert metrics["train_rows"] > metrics["test_rows"] > 0
    assert metrics["seed"] == 42
~~~

CI checks the **code contract**, not ML business performance from a single unit test. A **post-training quality gate** evaluates metrics from the actual model artifact:

~~~json
{
  "metric": "macro_f1",
  "minimum": 0.85,
  "baseline_model": "approved-baseline-v1",
  "must_pass_data_contract": true,
  "approval_required_for_production": true
}
~~~

This is an **illustrative policy JSON**, not a file Vertex AI reads and enforces automatically. An evaluator step in Vertex AI Pipelines/Workflows/Cloud Build release pipelines must **actually parse metrics**, check thresholds, compare against baseline, and fail on violations. Never equate `CustomJob: SUCCEEDED` with `MODEL_APPROVED`.

### 6.1. Why Must Test Data Remain Independent?

Datasets used for tuning, parameter selection, or threshold picking must not be reused as final unbiased evidence. This lab trains **one** RandomForest config with one holdout. Production requires validation (tuning) and test (final), sliced by time/user groups, plus out-of-distribution checks where appropriate.

## 7. Dockerfile: Packaging the Training Environment

`Dockerfile`:

~~~dockerfile
FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY src ./src
ENTRYPOINT ["python", "-m", "src.train"]
~~~

CI uses the Dockerfile to build the image. The training container:

- Runs the entrypoint and exits; it is **not a serving container**.
- Receives workload identity provisioned by Vertex AI—no service account key needed inside the image.
- Writes artifacts to `AIP_MODEL_DIR` when Vertex AI passes this variable.
- Must not rely on local `/tmp` files after job completion: it must upload to GCS.

**Production:** pin base images by **digest**, manage SBOMs/dependencies, scan vulnerabilities, restrict build provenance, and check licenses. Never use `:latest` images or unpinned `pip install` on production paths.

## 8. Preflight: Inspecting Project and Existing Resources

Run only on a **lab project with Billing** and granted permissions. We pick `us-central1` for the example using public/built-in data; for real data, verify **residency** and regions across GCS/BigQuery/training.

~~~bash
gcloud auth list
gcloud config get-value project

gcloud artifacts repositories list \
  --location=us-central1 --project=PROJECT_ID

gcloud builds list \
  --region=us-central1 --project=PROJECT_ID --limit=10

gcloud ai custom-jobs list \
  --region=us-central1 --project=PROJECT_ID

gcloud ai models list \
  --region=us-central1 --project=PROJECT_ID
~~~

These are **read-only** commands. Never use a production project to create a new repo/container/Vertex job for the first time without approval and budget.

### 8.1. Enabling Billable Services

~~~bash
gcloud services enable \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  --project=PROJECT_ID

gcloud artifacts repositories create mlops-train \
  --repository-format=docker \
  --location=us-central1 \
  --description="ML training containers for lab" \
  --project=PROJECT_ID

gcloud storage buckets create \
  gs://PROJECT_ID-mlops-artifacts-UNIQUE \
  --location=us-central1 \
  --project=PROJECT_ID
~~~

Replace `UNIQUE` with a suffix so the **bucket name is globally unique**. If a repo/bucket already exists, check owner/IAM/location first; never delete or overwrite. Artifact Registry, Cloud Build, Vertex AI, and GCS can incur charges and consume quotas.

## 9. IAM Design Separating Three Identities

| Identity | Purpose | Minimum Permissions to Consider |
| --- | --- | --- |
| **Build SA** | Run CI, push images | Artifact Registry **Writer** on repo, Cloud Logging/log write, build source access |
| **Training SA** | Vertex AI worker reading data/writing artifacts | GCS read on exact dataset, **Storage Object Creator/Writer** on artifacts bucket |
| **Release SA** | Create CustomJob, register/deploy models | Appropriate Vertex AI rights, `iam.serviceAccounts.actAs` on Training SA |
| **Prediction runtime SA** | Serving container reading needed resources | Inference-time access only; no build/train rights |
| **Cloud Build/Vertex service agents** | Google-managed tasks | Keep service-agent roles scoped properly; never grant to users/apps |

Create an example Training SA for the lab:

~~~bash
gcloud iam service-accounts create mlops-training-sa \
  --display-name="MLOps training runtime" \
  --project=PROJECT_ID

gcloud storage buckets add-iam-policy-binding \
  gs://PROJECT_ID-mlops-artifacts-UNIQUE \
  --member=serviceAccount:mlops-training-sa@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator
~~~

`roles/storage.objectCreator` allows creating new objects; if code must **read, overwrite, or delete** artifacts, add scoped permissions on the target bucket/prefix. Whoever launches the CustomJob needs `iam.serviceAccounts.actAs` on Training SA. **Artifact Registry Reader** must be granted to the exact identity that **pulls the container** (which may be the Vertex AI service agent, especially for cross-project repos), not indiscriminately to every runtime.

With Cloud Build triggers, select a **dedicated Build SA** in the UI/CLI; triggers can **ignore `serviceAccount` declared in the build config** and use the trigger-configured service account instead. **Never assume the default Cloud Build SA automatically has Writer permissions**, as org policies often disable auto-grants.

## 10. `cloudbuild.yaml`: Unit Test → Build → Push Image

Place `cloudbuild.yaml` at the repo root:

~~~yaml
steps:
  - id: unit-tests
    name: python:3.11-slim
    entrypoint: bash
    args:
      - -ceu
      - |
        python -m pip install --no-cache-dir -r requirements.txt
        python -m pip install --no-cache-dir pytest==8.3.4
        python -m pytest -q tests/

  - id: docker-build
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - us-central1-docker.pkg.dev/$PROJECT_ID/mlops-train/digits-trainer:${_IMAGE_TAG}
      - .

images:
  - us-central1-docker.pkg.dev/$PROJECT_ID/mlops-train/digits-trainer:${_IMAGE_TAG}

substitutions:
  _IMAGE_TAG: lab-v1

options:
  logging: CLOUD_LOGGING_ONLY
~~~

**Common pitfalls explained:**

- Build steps run **sequentially** by default. If unit tests fail, build/push never execute.
- `images` tells Cloud Build to **push the image and record it in the build result** on success; no duplicate `docker push` step is needed.
- `$PROJECT_ID` is a built-in substitution; `${_IMAGE_TAG}` is a **user-defined substitution**. The actual YAML string must have `$` immediately before `{`, like `$` + `{_IMAGE_TAG}`, without `¤`. When saved in Markdown, these symbols are preserved verbatim.
- `CLOUD_LOGGING_ONLY` requires the Build SA to have Cloud Logging write permissions; for a custom SA, grant `roles/logging.logWriter` along with required build permissions.
- `python:3.11-slim` in CI installs dependencies to run tests; the Dockerfile installs dependencies independently inside the training image.
- Never pass **secrets** through substitutions; use Secret Manager integration if builds need tokens.

**CI does not run Vertex AI training yet.** Separating them prevents draft commits or PRs from unexpectedly spinning up VMs/GPUs.

## 11. Running CI Manually and Checking the Image Digest

In the lab folder containing `Dockerfile` and `cloudbuild.yaml`:

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --region=us-central1 \
  --project=PROJECT_ID \
  --substitutions=_IMAGE_TAG=lab-v1

gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/PROJECT_ID/mlops-train/digits-trainer \
  --include-tags \
  --project=PROJECT_ID
~~~

**Expected:** tests pass, build/push succeed, and Artifact Registry contains an image version with digest `sha256:<64-hex>`. **Never type an example digest** into production: copy the **real** digest from Console or CLI output.

Three distinct identifiers:

~~~text
Build commit:  6cba... (Git SHA)
Image tag:     digits-trainer:lab-v1  (human-readable, potentially mutable)
Image digest:  digits-trainer@sha256:... (exact image bytes)
~~~

To promote, record the **image digest** along with **source commit, test run, scan result, training config, and data version** in the release manifest/metadata. When images are scanned after push, CI/CD must **read scan results and enforce policy**; merely enabling scanning does not block deployments automatically.

## 12. Automating with Cloud Build Triggers

In **Cloud Build → Triggers**, connect your GitHub/Git repository per organizational policy. Create two paths:

1. **Pull request CI:** runs lint/unit tests/schema checks and test builds if needed. For fork PRs, never grant builds access to production secrets or broad project permissions.
2. **Protected main/release trigger:** runs only after review/merge; builds an image with a unique commit/release tag, recording digest and provenance. **Never auto-deploy to production** on every commit.

Key fields:

| Field | Suggested Value |
| --- | --- |
| Event | Pull request or push/tag on protected branch |
| Config | `cloudbuild.yaml` |
| Service account | Dedicated Build SA with repo Writer and logging permissions |
| Substitutions | `_IMAGE_TAG` = unique release ID or `SHORT_SHA` from vetted trigger |
| Included files | `src/**`, `tests/**`, `Dockerfile`, `requirements.txt` |
| Approval | Enabled for **release/promote** paths where required |
| Logs | Cloud Logging or approved dedicated bucket |

Cloud Build provides built-in variables like `$COMMIT_SHA` and `$SHORT_SHA` on **Git triggers**. During manual submissions without a Git commit, those variables may be empty; this lab uses `_IMAGE_TAG` intentionally to avoid empty image tags.

**Safe setup:** PR CI must never run as the Release SA or hold deployer credentials. Release triggers require **approval** and grant only permissions needed to launch the workflow, never permissions to modify IAM policies.

## 13. Securing Artifact Registry and the Supply Chain

Artifact Registry stores OCI/Docker images and, with the matching repo format, **Kubeflow Pipelines templates**. It is an **artifact registry**, not a model version store.

| Control | Meaning |
| --- | --- |
| **Artifact Registry IAM** | Build SA gets Writer; job runners/agents get Reader |
| **Immutable tags** | Tags cannot be repointed to another digest after push |
| **Digest pinning** | CustomJob/serving uses the exact vetted image |
| **Artifact Analysis** | Scans OS/Python packages for vulnerabilities per repo/config |
| **SBOM/build provenance** | Traces components and build origin |
| **Binary Authorization where supported** | Enforces deployment policies on supported targets; **not automatically enforced across all Vertex AI training/endpoints** |
| **Cleanup/retention policy** | Purges old images by age while preserving digests needed for rollback |

**Note:** Artifact Analysis supports **automatic** and **on-demand scanning**; scanning is not enabled identically on every repo by default. CI should check scan findings by **digest** and block vulnerabilities above approved severity thresholds. Passing a scan today does not guarantee no new CVE will appear next month; continuous vulnerability review is required.

Never delete an image still referenced by a CustomJob or serving model. If you pinned a digest and Artifact Registry cleans it up, **reproduction/redeployment/rollback can fail**.

## 14. CD-Training: Running a CustomJob with the Vetted Image Digest

The `customjob.yaml` (**CustomJobSpec**) template below must be populated with the real digest from Section 11:

~~~yaml
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-4
    replicaCount: 1
    containerSpec:
      imageUri: us-central1-docker.pkg.dev/PROJECT_ID/mlops-train/digits-trainer@sha256:REPLACE_WITH_REAL_DIGEST
baseOutputDirectory:
  outputUriPrefix: gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID
serviceAccount: mlops-training-sa@PROJECT_ID.iam.gserviceaccount.com
~~~

Pick a **unique `RUN_ID`**, e.g., combining release ID and date, and **never reuse an output prefix** from an earlier run to avoid overwriting artifacts. `baseOutputDirectory` configures output location; Vertex AI passes `AIP_MODEL_DIR` to custom training accordingly. Code from Section 5 uploads `model.joblib` and `metrics.json` to that folder.

Once **costs and permissions are approved**:

~~~bash
gcloud ai custom-jobs create \
  --region=us-central1 \
  --project=PROJECT_ID \
  --display-name=digits-train-release-lab \
  --config=customjob.yaml

gcloud ai custom-jobs list \
  --region=us-central1 \
  --project=PROJECT_ID

# Replace JOB_ID with the real ID.
gcloud ai custom-jobs describe JOB_ID \
  --region=us-central1 \
  --project=PROJECT_ID
~~~

**Expected:** job reaches `JOB_STATE_SUCCEEDED`, GCS contains `model.joblib` and `metrics.json`; record **job ID + image digest + output GCS URI**. A `SUCCEEDED` job only proves the container exited cleanly—**it does not prove the model passed the quality gate**.

**Do not raise `replicaCount` just to speed up arbitrary Python scripts:** if the code is not distributed, workers train redundantly and overwrite artifacts. This lab uses one CPU worker.

## 15. Post-Training Quality Gate: Checking the Exact Model Artifact

The release workflow must **read `metrics.json` from that exact CustomJob's output**, compare against baseline and release policy, and decide.

Illustrative decision logic:

~~~text
input: run_id, image_digest, artifact_uri, dataset_version

1. Confirm CustomJob SUCCEEDED and artifacts exist.
2. Read metrics.json; validate schema and finite values.
3. Compare macro_f1 against approved threshold.
4. Compare against benchmark/baseline on the SAME dataset snapshot/metric.
5. Check security scan + provenance + model access permissions.
6. If failed: mark REJECTED; do not register or deploy.
7. If passed: save evidence + wait for approval before registering.
~~~

An evaluator step on Cloud Run, a Vertex AI Pipelines component, or a Cloud Build release stage can implement this logic. If using Cloud Build, configure a **separate release trigger**—never give PR triggers permission to upload or deploy models.

**Record complete metadata:**

~~~yaml
release:
  source_commit: GIT_COMMIT_SHA
  training_image: us-central1-docker.pkg.dev/PROJECT_ID/mlops-train/digits-trainer@sha256:REAL_DIGEST
  vertex_custom_job: JOB_ID
  dataset_version: sklearn-digits-versioned-by-dependencies
  model_artifact_uri: gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID/model/
  metrics_uri: gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID/model/metrics.json
  evaluation_status: PENDING_APPROVAL
~~~

This manifest is a **governance example**, not a schema Vertex AI deploys natively. The `model/` path illustrates the `AIP_MODEL_DIR` directory: capture the real URI from post-run logs/metadata rather than guessing paths if system configs differ.

### 15.1. Avoiding Data Drift Between CI Builds and Models

If every build fetches "latest data" without a snapshot, two models built from the **same image digest** can still differ because the data changed. A release must pin **source object generation/BigQuery snapshot**, preprocessing, label definitions, feature schema, seed, and training config. Reproducibility is a property **of the entire ML system**, not just the Docker image.

## 16. Vertex AI Pipelines and Artifact Registry Pipeline Templates

A CustomJob handles only one step. For multi-step pipelines, use **Vertex AI Pipelines** (which may appear in newer docs as **Gemini Enterprise Agent Platform Pipelines**) to orchestrate:

~~~mermaid
flowchart TD
    SNAP["Data snapshot / validation"] --> TRAIN["CustomTrainingJobOp"]
    TRAIN --> EVAL["Evaluation component"]
    EVAL --> GATE{"Policy pass?"}
    GATE -->|Yes| UPLOAD["ModelUploadOp / Registry"]
    GATE -->|No| REJECT["Reject + notify"]
    UPLOAD --> STAGE["Staging evaluation"]
    STAGE --> APPROVE["Manual/automated approval"]
    APPROVE --> DEPLOY["Controlled rollout"]
~~~

A pipeline built with **Kubeflow Pipelines SDK v2** **compiles to YAML**. Templates can be versioned in Git and an **Artifact Registry KFP repository**; each run references a **template version**, parameter values, and a **pipeline root** on GCS. Components use **Google Cloud Pipeline Components (GCPC)** such as `CustomTrainingJobOp` and `ModelUploadOp` per supported SDK versions.

There is no need to write another long duplicate Python pipeline here—define clear contracts across steps:

| Component | Primary Input | Primary Output |
| --- | --- | --- |
| Data validation | Dataset URI/version | Contract pass/fail, snapshot |
| Training | Image digest, snapshot, params | CustomJob ID, artifacts URI |
| Evaluation | Model artifacts, test snapshot | Metrics, threshold verdict |
| Register | Approved artifact, serving image | Model resource + version ID |
| Staging/deploy | Model version, serving contract | Endpoint/`deployedModelId` |
| Monitor | Logs, labels, inference data | Alerts and retrain proposals |

**Note on newer APIs:** Agent Platform Pipelines docs currently describe launching runs via **SDK, REST, or Console**, not necessarily a `gcloud ai pipeline-jobs submit` command. Use the interface supported by your **current project/API version**. Pipelines can use execution caching; if a component depends on mutating external data, lock the dataset version or disable caching on that step.

## 17. Model Registry Is Not Where the Training Dockerfile Lives

Once gates pass, register the model:

- `model.joblib` and metadata sit in an accessible GCS path.
- **Vertex AI Model Registry** manages model resources, versions, aliases, labels, and deployment history.
- The **serving container** must **load the exact artifact** and expose a prediction API matching the Vertex AI prediction contract, including health/predict routes for custom containers.

The training `Dockerfile` in Section 7 **merely runs `src.train` and exits**—it **cannot be deployed directly as an inference server**.

Example command **only when a tested serving container already exists**:

~~~bash
gcloud ai models upload \
  --project=PROJECT_ID \
  --region=us-central1 \
  --display-name=digits-classifier-candidate \
  --artifact-uri=gs://PROJECT_ID-mlops-artifacts-UNIQUE/runs/RUN_ID/model \
  --container-image-uri=us-central1-docker.pkg.dev/PROJECT_ID/mlops-serving/digits-predictor@sha256:APPROVED_SERVING_DIGEST
~~~

**Do not run this command with just the trainer image**: `mlops-serving/digits-predictor` does not exist in this lab. You must build/test a separate prediction container or use a prebuilt serving container **compatible with the model format** as documented.

Model aliases like `candidate`, `staging`, and `approved` are **mutable pointers**; for rollback, know the exact **model version ID and serving image digest**, not just an alias.

## 18. CD-Serving: Staging, Canary, and Rollback

Safe release progression:

1. Register a model version with **evaluation evidence**.
2. Deploy to staging using the **prediction container**, running schema checks, smoke tests, and performance tests.
3. After approval, deploy the new version on the production endpoint at **low traffic**, e.g., 5%.
4. Watch latency, 5xx, input errors, model skew, and KPIs; ramp 5 → 25 → 50 → 100% if healthy.
5. If gates fail, shift traffic back to the old `deployedModelId`, and only then consider undeploying the bad version.

Example **only effective in an approved environment** once an endpoint already hosts two deployed models:

~~~bash
# Verify before altering routing:
gcloud ai endpoints describe ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1

# Share of total endpoint traffic: 95% old, 5% new.
gcloud ai endpoints update ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1 \
  --traffic-split=OLD_DEPLOYED_ID=95,NEW_DEPLOYED_ID=5

# Roll back routing if canary breaches SLO:
gcloud ai endpoints update ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1 \
  --traffic-split=OLD_DEPLOYED_ID=100

# ONLY AFTER traffic has returned to the healthy version and been approved:
gcloud ai endpoints undeploy-model ENDPOINT_ID \
  --project=PROJECT_ID --region=us-central1 \
  --deployed-model-id=NEW_DEPLOYED_ID
~~~

**`deployedModelId` is not `Model Registry modelId`.** Retrieve real `deployedModels[].id` values from `endpoints describe`. Endpoint traffic splits specify deployed IDs whose percentages must sum as required. If no healthy prior version remains deployed, **do not blindly copy the rollback snippet**—follow a dedicated incident/restore plan.

**Rolling back a model does not roll back data or business side effects.** If the new model auto-rejected or flagged transactions, you need an audit, reconciliation, and remediation workflow for affected decisions. Never shift traffic based solely on one metrics chart while ignoring business impact.

## 19. Security, Networking, Secrets, and Compliance

- **Source control:** protected branches, PR approvals, dependency lockfiles, zero committed service account JSONs.
- **Cloud Build:** dedicated service account, restricted PR trigger rights, Secret Manager, zero tokens in logs.
- **Artifact Registry:** private repositories, Writer only for CI, Reader for required runtimes, provenance/scanning, and retention.
- **Vertex AI:** separate permissions for training, registering, and deploying using dedicated service accounts; avoid granting `roles/aiplatform.admin` to every consumer.
- **Cloud Storage/BigQuery:** buckets/datasets in compliant regions, data residency enforcement, least-privilege IAM, CMEK if policy requires.
- **Networking:** CustomJobs need network paths to private Cloud SQL/BigQuery sources; check VPC/PSC/Private Service Access, never confusing IAM with networking.
- **VPC Service Controls:** evaluate perimeters spanning Cloud Build, Artifact Registry, Vertex AI, Cloud Storage, and service agents as supported.
- **Supply chain:** image digests, SBOMs, vulnerability scanning; accept model artifacts only from trusted pipelines.
- **Privacy:** log only metrics/IDs; never log raw PII, sensitive model features, or full prediction payloads without approval.

**Never use a service agent role** (intended for Google-managed identities) as a shortcut for a human user or normal service account. On permission errors, identify the exact **principal and resource** (source repo, image, bucket, model, endpoint).

## 20. Observability, Investigation, and Cost Control

| Component | Metrics to Track | Question Answered |
| --- | --- | --- |
| Git/Cloud Build | Trigger, Build ID, test result, duration, image digest | Which build produced the image? |
| Artifact Registry | Scan findings, image age/size, retention | Does the image have new CVEs or face cleanup? |
| Training jobs | Job state, duration, worker type, failures | Did training succeed cleanly? |
| Evaluation | Metrics vs baseline, data slices, drift, policy verdict | Is it qualified for promotion? |
| Registry | Model/version/alias, approval | Which version is active? |
| Endpoint | p50/p95/p99 latency, 4xx/5xx, replica count, traffic split | Is the canary hurting users? |
| Business | Fraud false positives, conversion, support tickets | Is the model actually helping the business? |
| Billing | Cloud Build, Artifact Registry, Vertex workers, GCS, endpoint machines | Where are costs coming from? |

**CI/CD costs extend beyond Cloud Build:** Artifact Registry storage/scanning, Cloud Build CPU/time/logs, Vertex AI training VMs/GPUs, GCS model artifacts, BigQuery feature queries, Vertex AI Pipelines orchestration, endpoint CPU/GPU/min-replicas, and log retention are all billable.

**Online endpoints incur charges while idle** if replicas remain deployed. Finished training jobs do not shut down endpoints automatically. Use Cloud Billing budgets, labels, and exports; **budget alerts do not automatically freeze billing**. Clean up lab projects after confirming no dependencies remain.

## 21. Stage-by-Stage Troubleshooting

| Symptom | Common Causes | How to Check |
| --- | --- | --- |
| CI unit tests fail | Imports/versions/schema/test regression | Build logs, CI env vs local |
| Build push returns `PERMISSION_DENIED` | Build SA lacks repo Writer | IAM on Artifact Registry repo |
| Build logs missing | Custom SA lacks Logging Writer or log bucket config | Cloud Build options/logs policy |
| Image tag updated, yet CustomJob runs old code | Job pinned old digest | Compare digest URI in job spec |
| CustomJob cannot pull image | Missing Artifact Registry Reader/service agent/cross-project | Check image-pulling identity |
| `AIP_MODEL_DIR` empty | `baseOutputDirectory` omitted | `CustomJobSpec`/runtime env |
| Job `SUCCEEDED` yet model missing | Code skipped upload or wrong output path | GCS objects/logs, verify artifacts |
| Metric gate fails | Data/labels shifted, overfit/underfit | Dataset version, split, baseline |
| Model Registry has no version | CustomJob does not auto-upload models | Model upload step/training pipeline |
| Endpoint deploy fails | Serving image runs no prediction server | Container logs, model format, health |
| Canary 5xx spikes | Schema mismatch/timeout/resource exhaustion | Endpoint metrics, roll back traffic |
| Rolled back yet KPI still wrong | Side effects from past predictions persisted | Audit/reconciliation runbook |
| Bill rises without training | Deployed endpoints, stored images, logs | Billing SKUs, cleanup plan |

During incidents, preserve **Build ID, Git SHA, image digest, CustomJob ID, dataset snapshot, model version, and endpoint `deployedModelId`**. These identifiers resolve issues far faster than writing "release v2 broke."

## 22. Capstone Scenario: Fraud Model for Commerce API

**Context:** a fraud detection model is updated weekly; a Java API on Cloud Run calls a Vertex AI endpoint before confirming orders. The team operates three environments: `dev/staging/prod`.

**Proposed design:**

~~~mermaid
flowchart TD
    PR["PR / merge code"] --> CI["Cloud Build CI"]
    CI --> IMAGE["Artifact Registry image digest"]
    IMAGE --> T["Release trigger / approval"]
    T --> TRAIN["Vertex training on snapshot"]
    TRAIN --> METRIC["Evaluation & security gate"]
    METRIC -->|Pass| REG["Model Registry version"]
    METRIC -->|Fail| REJECT["Reject / investigate"]
    REG --> STAGE["Staging smoke + load tests"]
    STAGE --> CANARY["Prod 5% canary"]
    CANARY -->|"Metrics healthy"| FULL["25% → 50% → 100%"]
    CANARY -->|"Error / KPI regression"| ROLLBACK["Traffic 100% old model"]
~~~

**Separation of responsibilities:**

| Role | Decision |
| --- | --- |
| Data engineer | Do data, schema, labels, and snapshots match? |
| ML engineer | Are model metrics/feature drift and training code sound? |
| Platform engineer | Are builds/images/IAM/networking/endpoints secure? |
| Product/compliance | Are false positives, fairness, privacy, and business KPIs acceptable? |
| SRE | Are canary SLOs, rollback, observability, and runbooks ready? |

Release only when **all required gates** pass. If a new model boosts recall yet spikes false positives so valid customers get blocked, **keep the incumbent version** even though the training job and API both run cleanly.

## 23. Practical Exercises and Self-Check

**Exercise 1 — CI lab.** From the repo in Sections 4–10, run unit tests and Cloud Build in an approved lab project.

*Pass criteria:* build has a Build ID, tests pass, Artifact Registry records the digest; no CustomJob is launched automatically.

**Exercise 2 — CD-training.** Create `customjob.yaml` with the **real digest**, run one CPU worker, and inspect artifacts.

*Pass criteria:* Job `SUCCEEDED`, GCS contains model/metrics, and source commit – image digest – run ID are linked.

**Exercise 3 — Blocking a bad model.** Simulate `macro_f1` below the release threshold.

*Pass criteria:* release pipeline holds the model in **REJECTED** state without deploying an endpoint; logs state the reason.

**Exercise 4 — Canary.** On a staging endpoint with two deployed models, calculate a 95/5 split and rollback.

*Pass criteria:* distinguish model ID from `deployedModelId`; rollback changes traffic only without erasing data/side effects.

**Question 5.** Is Artifact Registry the same as Model Registry?

*Answer:* No. Artifact Registry stores containers/KFP templates; Vertex AI Model Registry manages model resources/versions.

**Question 6.** Does the `latest` image tag guarantee immutable contents?

*Answer:* No if tags are mutable; use image digests or enforce immutable tags.

**Question 7.** Should a Cloud Build PR trigger be permitted to deploy to production?

*Answer:* No. PR CI needs restricted permissions, with release approvals separated.

**Question 8.** Do passing unit tests prove strong business model performance?

*Answer:* No. Validation/test metrics and business evaluation are required.

**Question 9.** Does a finished `CustomJob` register a model in Model Registry automatically?

*Answer:* Not by default; requires an upload step or supporting TrainingPipeline.

**Question 10.** If you keep the same image digest while training data changes, is the resulting model guaranteed identical?

*Answer:* No. You must version datasets, seeds, parameters, and preprocessing.

**Question 11.** Can a Dockerfile that only runs `train.py` be deployed directly as an inference endpoint?

*Answer:* No. You need a serving container implementing predict/health protocols.

**Question 12.** Where does `OLD_DEPLOYED_ID` in a traffic split come from?

*Answer:* From `deployedModels[].id` on the Vertex AI Endpoint; distinct from Registry `modelId`.

**Question 13.** Does shifting 100% traffic back to the old model undo past decisions made by the new model?

*Answer:* No. Side effects require auditing and reconciliation.

**Question 14.** Why doesn't an ML budget equal just training VM costs?

*Answer:* You must include builds, Artifact Registry, scanning, storage, orchestration, inference, networking, and monitoring.

## 24. Production Checklist and Conclusion

- [ ] Git PR reviews, CI tests, and separate release approvals are enforced.
- [ ] Training images use digests; source SHA and dependency versions are recorded.
- [ ] Build SA, Training SA, Release SA, and serving identities have **separated permissions**.
- [ ] Artifact Registry is private, with vulnerability scanning and controlled retention.
- [ ] Dataset snapshots/labels/splits are versioned and checked for leakage.
- [ ] Model evaluation gates run on holdout, comparing baselines and business KPIs.
- [ ] Zero registration or deployment occurs when quality/security gates fail.
- [ ] Model artifact GCS URI, checksum, metrics, run ID, and model version have lineage.
- [ ] Dedicated serving container is compatible with model and input/output schemas.
- [ ] Staging smoke/load tests pass before production.
- [ ] Canary/rollback use the exact **`deployedModelId`**.
- [ ] IAM, VPC/PSC, organization policies, secrets, and data residency verified.
- [ ] Monitoring for p95/5xx, drift, fraud false positives, costs, and alerts is active.
- [ ] Rebuild/retrain/rollback runbooks exist and required artifacts are retained.
- [ ] Budgets, quotas, and cleanup plans cover jobs, endpoints, and registries.

**Conclusion:** Good MLOps does not mean "every Git push auto-trains and auto-deploys." A reliable workflow is **CI tests and publishes an immutable training image → CD trains on versioned data → quality/security gates → register model → staging/canary/rollback → monitoring**. Artifact Registry establishes **which code ran**, Vertex AI manages **training and model versions**, and quality and access policies govern **whether a model belongs in production**.

## Official Reference Documentation

- [Artifact Registry: Repository and image names](https://cloud.google.com/artifact-registry/docs/docker/names)
- [Artifact Registry: Push and pull images](https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Artifact Registry: Connect Cloud Build](https://cloud.google.com/artifact-registry/docs/configure-cloud-build)
- [Cloud Build: Build and push container](https://cloud.google.com/build/docs/build-push-docker-image)
- [Cloud Build: Automated build triggers](https://cloud.google.com/build/docs/automate-builds)
- [Cloud Build: Build substitutions](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Cloud Build: User-managed service account](https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Artifact Analysis: Container vulnerability scanning](https://cloud.google.com/artifact-analysis/docs/container-scanning-overview)
- [Vertex AI: Create custom training job](https://cloud.google.com/vertex-ai/docs/training/create-custom-job)
- [gcloud ai custom-jobs create reference](https://cloud.google.com/sdk/gcloud/reference/ai/custom-jobs/create)
- [Vertex AI Pipelines: Build a pipeline](https://cloud.google.com/vertex-ai/docs/pipelines/build-pipeline)
- [Vertex AI Pipelines: Run a pipeline](https://cloud.google.com/vertex-ai/docs/pipelines/run-pipeline)
- [Vertex AI: Pipeline templates in Artifact Registry](https://cloud.google.com/vertex-ai/docs/pipelines/create-pipeline-template)
- [Vertex AI Model Registry: Model aliases](https://cloud.google.com/vertex-ai/docs/model-registry/model-alias)
- [Vertex AI: Deploy model to endpoint](https://cloud.google.com/vertex-ai/docs/general/deployment)
- [gcloud ai models upload reference](https://cloud.google.com/sdk/gcloud/reference/ai/models/upload)
- [gcloud ai endpoints update traffic split](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/update)
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)

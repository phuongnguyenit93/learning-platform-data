# Training, Registering, and Deploying Models in Azure Machine Learning

An enterprise wants to predict which customers are at risk of churning. A prototype model on a laptop looks promising, yet the engineering team cannot tell **which dataset, code commit, and dependencies** produced it; if a production API returns wrong predictions, nobody can verify which model version is running or roll back cleanly. When the model needs retraining, manual steps risk pulling the wrong data, losing experiment history, and deploying a different artifact than the one evaluated.

**Azure Machine Learning (Azure ML)** provides a platform for managing the ML lifecycle on Azure—from **data assets, environments, compute, training jobs, experiment tracking, and model assets** to **online/batch deployments, monitoring, and MLOps**. Production workflows take more than `model.fit()`. They require **reproducibility, validation, approval, controlled deployment, monitoring, and rollback capability** for clearly versioned models.

This lesson belongs to the **AI and Machine Learning on Azure** chapter of the **CLOUD_PROVIDERS_AZURE** module, connecting to Microsoft Azure architecture from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, security, monitoring, and cost control. Examples use **Azure ML CLI/SDK v2** and a scikit-learn Iris classification model so learners grasp the entire lifecycle before applying it to enterprise datasets.

> **Scope:** Azure ML v2 schema names, Python SDK/CLI versions, container environments, compute SKUs, regions, supported permissions, and pricing may change. Illustrative code must be tested inside an authorized lab workspace and should not be treated as turnkey production commands. Generative models carry additional safety, prompt/grounding evaluation, and specialized deployment requirements outside this scikit-learn example.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the lifecycle **data → training → evaluation → registration → deployment → monitoring**.
2. Distinguish between Azure ML workspace, compute, data asset, datastore, environment, job, experiment, registry, endpoint, and deployment.
3. Design train/validation/test splits to prevent leakage and pick business-aligned metrics.
4. Submit command training jobs via YAML CLI v2 or Python SDK v2 and persist model/metrics outputs.
5. Inspect logs/metrics and enforce **quality gates** before registering a model.
6. Register artifacts by **model name/version** and record lineage.
7. Deploy custom models to managed online endpoints, author scoring scripts, and validate inference contracts.
8. Distinguish online vs. batch endpoints and design blue/green rollouts and rollbacks.
9. Protect training data, secrets, and endpoints with Entra ID, RBAC, managed identity, and private networking.
10. Plan MLOps, drift/performance monitoring, incident triage, and Azure ML cost management.

## 2. End-to-End Lifecycle

~~~mermaid
flowchart LR
  DATA["SQL / ADLS / Cosmos DB"] --> ASSET["Versioned data asset"]
  ASSET --> TRAIN["Azure ML training job"]
  CODE["Code + environment + compute"] --> TRAIN
  TRAIN --> EVAL["Evaluation metrics / artifacts"]
  EVAL --> GATE{"Quality + security gate"}
  GATE -->|Pass| MODEL["Model asset name/version"]
  GATE -->|Fail| FIX["Fix data / model"]
  MODEL --> DEPLOY["Online / Batch deployment"]
  DEPLOY --> OBS["Telemetry, drift, ground truth"]
  OBS --> RETRAIN["Retrain / review / rollback"]
  RETRAIN --> TRAIN
~~~

Every arrow must have explicit inputs, outputs, and owners. A training job reaching **`Completed`** does not prove the model passed evaluation, and a registered model asset **is not automatically authorized** for production deployment.

### Key Boundaries

- **Management/control plane:** creates workspaces, compute, jobs, assets, endpoints, and role assignments.
- **Data plane:** training compute reads data and writes artifacts; serving endpoints accept inference requests.
- **Lineage:** tracks data snapshot, code commit, environment, hyperparameters, training job, and model version.
- **Governance:** approval policies, rollback, retention, privacy, data residency, and auditing.

## 3. Core Objects in Azure ML

| Component | Function | Example |
|---|---|---|
| **Workspace** | ML governance boundary, metadata, assets, permissions | `mlw-commerce-lab` |
| **Experiment** | Groups runs for a given problem | `iris-classification` |
| **Job** | Single training/evaluation run with logs, status, outputs | `train-iris-001` |
| **Compute instance** | Interactive workstation / notebook VM | `ds-workstation` |
| **Compute cluster** | Autoscaling compute for queued jobs | `cpu-cluster` |
| **Environment** | Container image + pinned dependencies/version | `iris-train-env:1` |
| **Datastore** | Connection reference to source/target storage | ADLS Gen2 |
| **Data asset** | Named, versioned, typed data reference | `customer-churn-data:4` |
| **Model asset** | Registered artifact under name/version | `iris-logreg:1` |
| **Registry** | Shared cross-workspace asset space per policy/features | Team-shared models |
| **Endpoint** | Logical address serving online or batch scoring | `iris-demo-endpoint` |
| **Deployment** | Model + code + env + compute under an endpoint | `blue` and `green` |

An **Azure ML model asset** is different from a raw `.joblib` file on disk: an asset is a tracked resource with identity, name, version, metadata, and a URI to artifacts. An **environment asset** is not a model; it defines the runtime conditions for training or scoring code.

## 4. Start from Business Requirements

A churn prediction problem needs clear definitions:

- **Prediction target:** customer churns within 30 days of the prediction timestamp.
- **Input availability:** use only features available prior to the prediction timestamp.
- **Decision:** prioritize retention outreach; never trigger uncontrolled adverse decisions automatically.
- **Output:** probability/class, schema, model version, and timestamp.
- **Service objective:** batch finishes before 06:00, or online meets a specific p95 latency SLO.
- **Business risk:** false positives waste outreach spend; false negatives miss high-value customers.
- **Privacy/fairness:** whether sensitive attributes are permitted and whether human review is required.

Picking a high-accuracy model that misses inference latency targets, cannot be audited, or introduces cohort bias **is not a production-ready model**.

### Metrics by Problem Type

| Problem | Common Metrics | Watch-Outs |
|---|---|---|
| Classification | Precision, recall, F1, ROC-AUC, PR-AUC, calibration | Class imbalance, thresholds, error costs |
| Regression | MAE, RMSE, $R^2$, quantile errors | Outliers, per-segment drift |
| Ranking | NDCG, MAP, recall@k | Label quality and feedback bias |
| Forecasting | WAPE, MAE, backtest error | Time leakage, forecast horizon |
| Anomaly detection | Detection recall, false alert rate | Scarce labels, human review |

Evaluate **by segment and business impact**; never rely on a single accuracy number as the sole release gate.

## 5. Dataset Splitting and Preventing Data Leakage

**Leakage** happens when a model accidentally uses "future" information or evaluation-set information during training.

Examples:

- Using a `"contract_terminated"` column to predict churn.
- Fitting normalization across train and test together before splitting.
- Records from the same customer appearing in both train and test when evaluating generalization across customers.
- Randomly splitting time-series data, leaking post-prediction dates into training.
- Repeatedly tuning hyperparameters on the holdout test set while still calling it an independent test.

### Rules

- **Train set:** fit preprocessing and model weights.
- **Validation set:** select hyperparameters, model families, and thresholds.
- **Test set:** evaluate the chosen candidate once; never tune further against test results.
- **Time-series:** split chronologically with appropriate horizons and embargoes.
- **Grouped records:** use group splits when multiple rows share a subject.
- **Feature transformations:** fit exclusively on train, then apply to validation, test, and serving.

The scikit-learn Iris example below uses a random stratified split because it is a tiny standalone lab; **never copy that split blindly to real-world churn**.

## 6. Data Assets, Datastores, and Immutable Snapshots

In production, data assets store references by name, version, and type/format (such as `uri_file`, `uri_folder`, `mltable` in SDK v2).

~~~text
Data asset: churn-training-data:4
Source: ADLS curated/churn/snapshot_2026-11-20/
Schema: features-v7
Labels: churn within next 30d
Owner: Data Platform
Permissions: least privilege
Checksum/table commit: recorded
~~~

**A data asset version does not make underlying files immutable** if someone overwrites the same storage path. True reproducibility requires immutable snapshots/paths, lake table versions, or file manifests/hashes paired with access policies.

### Data-Plane Permissions

Someone holding Azure RBAC on the workspace can still hit Storage `403` if the compute/job identity lacks **`Storage Blob Data Reader`** or matching ADLS Gen2 ACLs. A Private Endpoint is only networking—**it does not grant authorization**.

## 7. Workspace and Associated Resources

~~~mermaid
flowchart TD
  ENTRA["Microsoft Entra ID + Azure RBAC"] --> WS["Azure ML Workspace"]
  WS --> STORE["Storage / Data Assets"]
  WS --> KV["Key Vault"]
  WS --> REG["Container Registry / Images"]
  WS --> COMP["Compute clusters/jobs"]
  WS --> EP["Online / Batch endpoints"]
  COMP --> MON["Azure Monitor / App Insights"]
  EP --> MON
~~~

A workspace links to Storage, Key Vault, Container Registry, and Application Insights per supported topology. Verify identities, subscriptions, policies, regions, and managed networking.

### Separating Dev / Staging / Prod

- **Dev:** flexible experimentation, small/anonymized datasets, capped compute.
- **Staging:** tests deployments, security, load, feature contracts, and migrations.
- **Prod:** approved models, tight access controls, autoscaling, alerts, and rollback runbooks.

Use **managed identities or federated identities** for automation, keep secrets in Key Vault/secret managers per policy, and never commit subscription credentials into notebooks.

## 8. Compute Instances and Compute Clusters

A **compute instance** supports notebooks and interactive development; leaving it running incurs ongoing cost. An **AmlCompute cluster** executes jobs and scales nodes per configuration.

Example `compute.yml`:

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/amlCompute.schema.json
name: cpu-cluster
type: amlcompute
size: Standard_DS3_v2
min_instances: 0
max_instances: 2
idle_time_before_scale_down: 120
~~~

Create with CLI v2:

~~~bash
az ml compute create --file compute.yml
az ml compute show --name cpu-cluster
~~~

**Caution:** the SKU must exist and be permitted by subscription/region quotas and policies; property names and autoscaling follow the active schema. `min_instances: 0` cuts idle compute spend between jobs, though storage, image, and monitoring charges remain.

Never assume GPUs are always better than CPUs; for logistic regression or Iris, CPUs suffice—GPUs only add cost and quota friction.

## 9. Environments: Versioning Libraries

A training environment requires compatible Python, scikit-learn, and preprocessing libraries. This lab uses Python 3.10 and pinned dependencies for repeatability.

### `conda-train.yml`

~~~yaml
name: iris-train
channels:
  - conda-forge
dependencies:
  - python=3.10
  - pip
  - pip:
      - scikit-learn==1.5.2
      - numpy==1.26.4
      - joblib==1.4.2
~~~

### `train-env.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: iris-train-env
version: "1"
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
conda_file: ./conda-train.yml
description: "Training environment for Iris lab"
~~~

~~~bash
az ml environment create --file train-env.yml
az ml environment show --name iris-train-env --version 1
~~~

**Limitations of this example:** the `:latest` container tag can shift over time; production must pin an approved image digest/tag, scan for vulnerabilities, and verify compatibility. Library versions shown are illustrative, **not latest security recommendations**. In production, evaluate Azure-curated environments or custom images with dependency lockfiles.

## 10. Lab Project Layout

~~~text
azureml-iris/
  compute.yml
  conda-train.yml
  train-env.yml
  src/
    train.py
  job.yml
  conda-infer.yml
  infer-env.yml
  score/
    score.py
  endpoint.yml
  deployment-blue.yml
  sample-request.json
~~~

These files are part of a **hands-on exercise learners can create inside a lab workspace**, not files generated inside this repository.

## 11. Training Code: Scikit-Learn Classification

Iris has 150 samples, 4 features, and 3 classes. The dataset ships inside scikit-learn and contains no enterprise data. Code:

~~~python
# src/train.py
import argparse
import json
from pathlib import Path

import joblib
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--metrics_dir", required=True)
    args = parser.parse_args()

    iris = load_iris()
    X_train, X_test, y_train, y_test = train_test_split(
        iris.data,
        iris.target,
        test_size=0.2,
        stratify=iris.target,
        random_state=42,
    )

    # Fit scaler strictly on train to prevent leakage.
    model = Pipeline([
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(
            max_iter=500,
            random_state=42
        )),
    ])
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "f1_macro": float(f1_score(y_test, predictions, average="macro")),
        "confusion_matrix": confusion_matrix(
            y_test, predictions
        ).tolist(),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "classes": list(iris.target_names),
        "seed": 42
    }

    model_dir = Path(args.model_dir)
    metrics_dir = Path(args.metrics_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_dir / "model.joblib")
    (metrics_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "accuracy": metrics["accuracy"],
        "f1_macro": metrics["f1_macro"],
        "model_file": str(model_dir / "model.joblib")
    }))


if __name__ == "__main__":
    main()
~~~

Notes:

- Wrap scaler and classifier in a `Pipeline` so preprocessing travels inside the artifact, preventing serving skew.
- Fixing `random_state` aids repeatability, though it does not guarantee bit-identical results across all hardware/libraries.
- With a tiny dataset, metrics fluctuate with splits; production requires robust validation/test design.
- `joblib` is strictly for trusted artifacts—never deserialize files from untrusted sources.
- Separating the two output folders simplifies collection and auditing.

## 12. Submitting a Command Job with Azure ML CLI v2

Example `job.yml`:

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/commandJob.schema.json
code: ./src
command: >-
  python train.py
  --model_dir ${{outputs.model}}
  --metrics_dir ${{outputs.metrics}}
environment: azureml:iris-train-env:1
compute: azureml:cpu-cluster
experiment_name: iris-lab
display_name: train-iris-logreg
outputs:
  model:
    type: uri_folder
  metrics:
    type: uri_folder
~~~

The two expressions `${{outputs.model}}` and `${{outputs.metrics}}` are **Azure ML CLI v2 named output bindings**, mapped by the service to job output directories at runtime rather than hard-coded local paths. The CLI commands below assume default workspace/resource-group settings are configured or passed explicitly. Check the active `commandJob` schema and CLI version before running.

~~~bash
az ml job create --file job.yml
~~~

**Submitting a job does not mean the job `Completed`.** Wait for completion and inspect logs and outputs:

~~~bash
JOB_NAME="<JOB_NAME_RETURNED_BY_CREATE>"

az ml job show --name "$JOB_NAME" --output json
az ml job stream --name "$JOB_NAME"
~~~

If the job fails due to container build errors, quotas, Storage `403`, or code exceptions, never register a model just because the CLI returned a job ID.

### Reading Outputs

The job declares named outputs `model` and `metrics`; output storage should contain `model.joblib` and `metrics.json`. If the script writes to `./model` while the job declares a different output binding, registration will miss the artifact. Always use **Azure ML output bindings** to avoid path mismatches.

## 13. Python SDK v2: Equivalent Approach

~~~python
from azure.ai.ml import MLClient, command, Output
from azure.ai.ml.constants import AssetTypes
from azure.identity import DefaultAzureCredential

ml_client = MLClient(
    DefaultAzureCredential(),
    subscription_id="<SUBSCRIPTION_ID>",
    resource_group_name="<RESOURCE_GROUP>",
    workspace_name="<WORKSPACE_NAME>",
)

job = command(
    code="./src",
    command=(
        "python train.py "
        "--model_dir ${{outputs.model}} "
        "--metrics_dir ${{outputs.metrics}}"
    ),
    environment="azureml:iris-train-env:1",
    compute="cpu-cluster",
    experiment_name="iris-lab",
    outputs={
        "model": Output(type=AssetTypes.URI_FOLDER),
        "metrics": Output(type=AssetTypes.URI_FOLDER),
    },
)

submitted = ml_client.jobs.create_or_update(job)
print("Training job:", submitted.name)
~~~

Just like the YAML CLI example, the `command` string uses **named output bindings** `${{outputs.model}}` and `${{outputs.metrics}}`. In the lab, install compatible versions of `azure-ai-ml` and `azure-identity`. `DefaultAzureCredential` picks up identity from the environment (developer or workload/managed identity per config) and does not grant workspace/Storage permissions on its own.

### When to Use CLI, SDK, or Studio?

- **YAML / CLI v2:** easy to review and govern through CI/CD for declarative resources.
- **SDK v2:** convenient for programmatically generating jobs, sweeps, and pipeline components.
- **Azure ML Studio:** visual inspection for debugging, viewing jobs/metrics, and comparing models.
- **IaC:** controlled governance of subscriptions, workspaces, networking, and policies.

Never mix SDK v1 code (e.g., legacy `ScriptRunConfig` workflows) with SDK v2 without converting objects and schemas.

## 14. Training Metrics, Experiment Tracking, and MLflow

Every job should record:

~~~text
Experiment = iris-lab
Training job = train-iris-001
Data asset or source snapshot = iris built-in
Code commit SHA = ...
Environment = iris-train-env:1
Compute = cpu-cluster / SKU
Hyperparameters = LogisticRegression(max_iter=500, seed=42)
Metrics = accuracy, f1_macro, confusion matrix
Artifacts = model/model.joblib, metrics/metrics.json
Start/end/status = ...
~~~

Azure ML integrates **MLflow tracking** in supported environments and SDKs. Once tracking URI and packages are configured, you can log parameters and metrics:

~~~python
import mlflow

mlflow.log_param("model_family", "logistic_regression")
mlflow.log_param("random_state", 42)
mlflow.log_metric("accuracy", metrics["accuracy"])
mlflow.log_metric("f1_macro", metrics["f1_macro"])
~~~

This fragment belongs in training code after computing `metrics`, and **has no effect unless MLflow/Azure ML integration is configured properly** (some environments require `azureml-mlflow`). Logging run artifacts and **registering a model asset for deployment** can connect together, yet they are distinct steps.

## 15. Quality Gate: Completed ≠ Approved

Example lab gate conditions:

~~~text
Training job status == Completed
model.joblib exists and can load
metrics.json exists and parseable
accuracy >= 0.85
f1_macro >= 0.80
model.predict smoke test passes
security + provenance checks pass
~~~

The `0.85` and `0.80` thresholds are purely illustrative. For production churn, require:

- Model selection on the validation set.
- Comparison against the **champion model**, not just static thresholds.
- Per-class precision/recall and business error-cost evaluation.
- Data leakage checks, segment fairness, and probability calibration.
- Risk-proportionate security and privacy review/approval.
- Verification that the **exact evaluated artifact** is the one registered.
- Serialization/deserialization tests inside the inference environment.

If evaluation fails, block promotion. A model with high accuracy can still be rejected for PII leakage, fairness violations, or excessive endpoint latency.

## 16. Registering a Model Asset

Training artifacts live in Azure ML job outputs. **Model registration** assigns a name and version for governance, deployment, rollback, and auditing:

~~~text
Name: iris-logreg
Version: 1
Type: custom_model
Path: exact approved training job output
Tags: owner, code commit, data version, experiment
Description: lab classification model
~~~

### Retrieving the Output URI from a Job

~~~bash
az ml job show --name "$JOB_NAME" --query outputs --output json
~~~

With a named output `model`, the URI typically references the job output:

~~~text
azureml://jobs/<JOB_NAME>/outputs/model
~~~

**Always use the actual output URI accepted by the service** rather than guessing paths across all job types. If URI formats or SDK versions differ, inspect job metadata or construct the model asset path per current schema.

### Creating a Model Asset via CLI

~~~bash
MODEL_OUTPUT_URI="azureml://jobs/<JOB_NAME>/outputs/model"

az ml model create \
  --name iris-logreg \
  --version 1 \
  --type custom_model \
  --path "$MODEL_OUTPUT_URI" \
  --description "Iris candidate from approved Azure ML training job"
~~~

Run this only after the job is `Completed` and passes the gate. `<JOB_NAME>` is a placeholder. In real projects, never silently overwrite artifact bytes under an existing version; increment the version and record provenance per policy.

### Custom Model vs. MLflow Model

| Type | Artifacts | Deployment |
|---|---|---|
| **`custom_model`** | Joblib/ONNX/PyTorch files or artifact directory | Usually requires a scoring script and inference environment |
| **`mlflow_model`** | MLflow flavor structure with metadata/signature | Can leverage MLflow no-code deployment where supported |

Never declare a bare `model.joblib` file as `mlflow_model` if the directory lacks a valid MLflow model structure.

## 17. Model Lineage and Governance

Every model version should trace back to:

- The training job and experiment that created it.
- Data version/snapshot, feature schema, and label definition.
- Source commit, dependencies, image digest, and hyperparameters.
- Evaluation metrics, per-class scores, and test sample counts.
- Model artifact hashes/provenance and SBOM/container security scans where applicable.
- Owner, approver, registration timestamp, and retention policy.
- Active deployments running that version and traffic history.
- Rollback plan and responsible owner.

**Tags are not an automated approval system.** If anyone with edit rights can attach `approved=true`, tags do not protect production. Enforce controls via RBAC, external approval gates, immutable artifacts, and auditing.

### Security Note on `joblib`

`joblib.load()` and `pickle` can execute arbitrary code when loading untrusted files. Load model artifacts strictly from trusted pipelines and registries—never allow users to upload arbitrary model files and deserialize them inside an endpoint.

## 18. Online Inference vs. Batch Inference

| Property | Managed Online Endpoint | Batch Endpoint |
|---|---|---|
| Pattern | HTTP request/response | Triggers batch scoring jobs |
| Latency | Low latency; p95 SLOs | Minutes/hours depending on volume |
| Use case | Real-time transaction classification API | Nightly scoring of millions of customers |
| Compute | Dedicated serving instances with baseline cost | Job compute scaled per workload |
| Outputs | JSON prediction response | Files or tables at destination |
| Testing versions | Blue/green traffic splits, canary | Job/batch IDs and versioned outputs |
| Error handling | Timeouts, 429, 5xx, schema errors | Retries, partial batches, idempotency |
| Cost | Compute bills even while idle | Compute/job runtime plus storage |

Never keep an online endpoint running 24/7 for a weekly batch job that does not need low-latency HTTP responses.

## 19. Scoring Script for a Managed Online Endpoint

For a `custom_model`, write a scoring script that accepts JSON, validates features, runs the trained preprocessing pipeline, and returns predictions.

### `score/score.py`

~~~python
import json
import os
from pathlib import Path

import joblib
import numpy as np

model = None


def init():
    global model
    model_root = Path(os.environ["AZUREML_MODEL_DIR"])
    model = joblib.load(model_root / "model.joblib")


def run(raw_data):
    if model is None:
        raise RuntimeError("Model is not initialized")

    request = json.loads(raw_data)
    rows = np.asarray(request["data"], dtype=float)

    if rows.ndim != 2 or rows.shape[1] != 4:
        raise ValueError("Expected 4 features per row")
    if rows.shape[0] < 1 or rows.shape[0] > 128:
        raise ValueError("Invalid batch size")
    if not np.isfinite(rows).all():
        raise ValueError("All features must be finite")

    labels = model.predict(rows)
    return {"predictions": labels.astype(int).tolist()}
~~~

**Illustrative notes:**

- `init()` loads the model when the scoring worker starts up per runtime.
- `run(raw_data)` parses the JSON body and validates exactly 4 features.
- `AZUREML_MODEL_DIR` is the artifact path injected by the Azure ML runtime per deployment scheme; verify packaging layout when the endpoint boots.
- Never allow callers to inject model file paths in payloads.
- Enforce input shape, batch size, finite-value checks, and clean error mapping so stack traces never leak.
- For sensitive workloads, log anonymized metadata/metrics—never PII or raw payloads.
- Scoring code lacks authorization logic; endpoint authentication and networking must still be configured separately.

### `sample-request.json`

~~~json
{
  "data": [
    [5.1, 3.5, 1.4, 0.2],
    [6.0, 2.2, 4.0, 1.0]
  ]
}
~~~

## 20. Inference Environment

Inference requires scikit-learn/joblib versions matching the trained artifact plus a supported HTTP inference server package.

### `conda-infer.yml`

~~~yaml
name: iris-infer
channels:
  - conda-forge
dependencies:
  - python=3.10
  - pip
  - pip:
      - scikit-learn==1.5.2
      - numpy==1.26.4
      - joblib==1.4.2
      - azureml-inference-server-http
~~~

### `infer-env.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: iris-infer-env
version: "1"
image: mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest
conda_file: ./conda-infer.yml
~~~

~~~bash
az ml environment create --file infer-env.yml
~~~

Production must pin a compatible `azureml-inference-server-http` version for Azure ML managed online endpoints, pin and scan the OS/image, and test the build. MLflow or curated deployments package differently. Never assume a training environment can serve online traffic without an inference server.

## 21. Creating a Managed Online Endpoint

An **endpoint** is the logical resource; a **deployment** binds the model + code + environment + compute that executes inference.

### `endpoint.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineEndpoint.schema.json
name: iris-lab-endpoint-unique
auth_mode: key
description: "Online endpoint for Iris lab"
~~~

~~~bash
az ml online-endpoint create --file endpoint.yml
az ml online-endpoint show --name iris-lab-endpoint-unique
~~~

Choose a valid endpoint name unique within the scope required by the service. `auth_mode: key` is strictly for lab illustration; in production, evaluate Entra token-based authentication as supported by your endpoint. Never print credentials or keys in logs or code.

### `deployment-blue.yml`

~~~yaml
$schema: https://azuremlschemas.azureedge.net/latest/managedOnlineDeployment.schema.json
name: blue
endpoint_name: iris-lab-endpoint-unique
model: azureml:iris-logreg:1
code_configuration:
  code: ./score
  scoring_script: score.py
environment: azureml:iris-infer-env:1
instance_type: Standard_DS3_v2
instance_count: 1
~~~

~~~bash
az ml online-deployment create \
  --file deployment-blue.yml \
  --all-traffic

az ml online-deployment show \
  --endpoint-name iris-lab-endpoint-unique \
  --name blue
~~~

**Warning:** `--all-traffic` shifts active traffic straight to `blue` as supported; in production, that can trigger an unintended cutover. In the lab, there are no live users. Verify VM SKU/quotas, container build, networking, and model artifact path beforehand. A deployment with `instance_count=1` **keeps accruing charges even with zero incoming requests**.

## 22. Invoking and Validating the Contract

~~~bash
az ml online-endpoint invoke \
  --name iris-lab-endpoint-unique \
  --request-file sample-request.json
~~~

CLI `invoke` uses managed client credentials; **never assume a production application can call the endpoint until its auth path is explicitly designed**.

### Minimum Verification Tests

| Test | Expectation |
|---|---|
| Valid payload with 4 numeric features | Predictions match schema |
| Missing `data` field | Clear input error; no internal trace leaked |
| Wrong dimensions or `NaN`/`Infinity` | Rejected cleanly |
| Artifact fails to load | Deployment unhealthy; logs sufficient to diagnose |
| Oversized request | Rejected within limits |
| Invalid token/key | Access denied |
| p95 latency under lab load | Meets defined SLO |
| New model version | Traceable to active serving version |
| Endpoint with no deployment | Never treated as ready to serve |

Never equate HTTP 200 with a **high-quality model**. Prediction accuracy requires ground truth and domain metrics.

## 23. Blue/Green, Canary, and Rollback

~~~mermaid
flowchart LR
  C["Clients"] --> E["Managed online endpoint"]
  E -->|90%| B["Blue model v1"]
  E -->|10%| G["Green model v2"]
  B --> MON["Metrics, logs, quality"]
  G --> MON
  MON --> D{"Gates pass?"}
  D -->|Yes| RAMP["Increase green traffic"]
  D -->|No| ROLLBACK["Route back to blue"]
~~~

### Workflow

1. Deploy `green` alongside `blue` receiving 0% production traffic.
2. Test `green` directly via supported mechanisms for schema, latency, and auth.
3. Shift a small canary percentage per approval and risk level.
4. Monitor 5xx/429s, p95/p99 latency, resource usage, prediction distributions, and business signals.
5. Ramp traffic gradually if healthy.
6. On regression, route traffic back to `blue` before conducting deep investigation.
7. Keep `blue` and its artifacts warm long enough to cover the rollback window.
8. Log deployment, version, approver, timestamp, and decision.

Conceptual traffic split config:

~~~yaml
traffic:
  blue: 90
  green: 10
~~~

This is not a full endpoint YAML; follow the exact endpoint schema. **Rolling back traffic does not undo business actions** already taken from earlier predictions. High-risk decisions require decision logging, human review, and remediation plans.

## 24. Batch Endpoints and Offline Scoring

When 2 million customers must be scored nightly, a **batch endpoint** fits far better than an online HTTP endpoint. It launches jobs, reads versioned inputs, writes outputs, and exposes job progress.

~~~mermaid
flowchart LR
  DATA["ADLS input snapshot"] --> B["Azure ML batch endpoint"]
  B --> JOB["Batch scoring job"]
  JOB --> OUT["ADLS predictions staging"]
  OUT --> V["Validate/dedup/publish"]
  V --> BI["BI / campaign / app"]
~~~

Batch design requires:

- Fixed batch ID, input data version, and model version.
- Mini-batch size and concurrency tuned to compute and model.
- Retries and checkpoints to prevent duplicate predictions.
- Output schema validation, row counts, and failed-record quarantine.
- Data permissions and network routes on compute.
- Completion deadline ahead of downstream consumption.
- Scaling compute down to 0 after jobs finish where supported.

Invoking a batch endpoint does not mean the batch is done; wait for job completion and validate outputs. Never reuse online `run(raw_data)` verbatim for mini-batch workloads if the batch scoring contract differs.

## 25. Pipeline Jobs and Workflow Automation

Stages are typically split into:

~~~text
Validate input snapshot
  -> Prepare / feature transform
  -> Train candidate
  -> Evaluate against champion
  -> Quality/security approval
  -> Register model
  -> Deploy staging
  -> Integration/load tests
  -> Promote/canary production
  -> Monitor/drift/retrain review
~~~

**Azure ML pipeline jobs** wire components and output bindings across prepare/train/evaluate steps. Registration and promotion still require gates: a `Completed` pipeline job does not automatically satisfy security or ethical approvals.

### Why Componentize?

- Reuse code and environments across runs.
- Quickly re-run failed steps and compare outputs.
- Reproduce runs from data snapshots and component versions.
- Simplify CI/CD quality-gate checks.
- Maintain clear lineage between inputs and model artifacts.
- Enforce per-stage permissions and auditing.

For automated retraining, **a drift alert should trigger an evaluation workflow**, never blind auto-deployment to production without review.

## 26. Training-Serving Skew and Feature Contracts

A model trained on one preprocessing definition hits production with different rules:

- Training uses `total_spend_30d`; serving passes `total_spend_7d`.
- Training converts currency to VND; the API sends USD.
- Training uses UTC timestamps; the API passes local timezone.
- Training drops nulls; the API passes the string `"null"`.
- Training fits a scaler on the train set; serving fits a fresh scaler at request time.
- The order of 4 features is swapped.

This is **training-serving skew**, which silently corrupts predictions without raising exceptions.

Mitigations:

1. Define an explicit feature schema: names, order, units, nullability, ranges.
2. Package preprocessing inside the model or versioned shared components.
3. Test identical inputs through offline evaluation and online serving.
4. Track feature snapshots and drift in the data pipeline.
5. Block deployments with contract mismatches.
6. Use canary rollouts and monitor feature distributions.
7. Never include future-derived features in training.

## 27. Production Monitoring: Metrics, Logs, and Quality

Signals to monitor:

| Group | Metrics |
|---|---|
| Endpoint health | Ready instances, request count, 5xx, timeouts |
| SLO latency | p50/p95/p99 latency, model load/startup time |
| Inference errors | Input schema errors, auth failures, 429s |
| Data quality | Missing values, outlier rates, range breaches |
| Prediction distributions | Class/probability distributions over time |
| Actual model quality | F1, precision, recall, calibration against ground truth |
| Drift | Data drift, concept drift, prediction drift |
| Fairness | Quality/disparity across cohorts where policy permits |
| Batch | Job status, input/output counts, freshness, failure rate |
| Cost | Training compute, idle online compute, storage/egress/logs |

**Data drift does not automatically mean the model is broken**; it can reflect seasonality, product changes, or upstream pipeline bugs. **Prediction drift is not ground truth.** Compute true model performance only once reliable labels arrive, accounting for label delay and sampling bias.

### Actionable Alerts

- Endpoint 5xx or p95 breaches baseline over sufficient duration and volume.
- Model load failures during deployment startup.
- Spikes in input schema mismatches after a release.
- Drops in per-class recall once ground truth arrives.
- Late batch deadlines, stale data, or high rejected-record rates.
- Unusual compute cost spikes or prolonged idle endpoints.
- Model drift exceeding thresholds, routed to an assigned owner.

### Azure Monitor and Application Insights

Azure ML integrates metrics, logs, and diagnostic settings with **Azure Monitor, Application Insights, and Log Analytics** per supported resources and features. Log table schemas vary by export mode and resource; verify actual table names before authoring production KQL queries so you do not reference nonexistent columns.

Safe log example:

~~~json
{
  "timestampUtc": "2026-11-20T10:00:00Z",
  "endpoint": "iris-lab-endpoint-unique",
  "deployment": "blue",
  "modelVersion": "iris-logreg:1",
  "requestId": "example-001",
  "durationMs": 34,
  "featureSchema": "iris-v1",
  "status": "success"
}
~~~

Never log personal data, raw payloads, tokens, keys, or sensitive feature values unless explicitly permitted by legal/consent policy with appropriate protections.

## 28. Security: Identity, Network, Registry

### Identity / RBAC

- **Microsoft Entra ID + Azure RBAC** for workspaces, jobs, assets, and endpoints.
- **Managed identity** for compute/deployments reading Storage and Key Vault where supported.
- **Storage data-plane RBAC/ACLs** managed independently from workspace permissions.
- **Least privilege** across Data Scientist, ML Engineer, Approver, and Security/Operator roles.
- **CI/CD federated identity / OIDC** where supported, avoiding long-lived client secrets.
- Online endpoint authentication per mode; never keep keys or tokens in source code.

### Network

- Verify Private Endpoints, VNet, DNS, NSGs/Firewalls, and egress across workspace, compute, registry/Storage, container images, and telemetry.
- Private Link never grants roles or data-read permissions on its own.
- Training compute blocked from reaching package or image registries fails during environment builds.
- Private endpoints may require dedicated client network paths (VPN/ExpressRoute).
- Restrict cross-region data egress per residency policies.

### Supply-Chain Risk

- Load `joblib`/pickle artifacts exclusively from trusted pipelines.
- Pin dependencies, scan base images/packages, and verify provenance.
- Never let arbitrary user inputs specify model file paths or shell commands.
- Maintain model rollback and revocation procedures if data or model poisoning is discovered.
- Govern dataset licenses, PII, bias/fairness, and retention.

## 29. CI/CD and MLOps Promotion

~~~mermaid
flowchart TD
  PR["PR: code/env/data schema"] --> CHECK["Unit/data/security tests"]
  CHECK --> TRAIN["Azure ML train job"]
  TRAIN --> EVAL["Offline evaluation"]
  EVAL --> Q{"Gates pass?"}
  Q -->|No| BLOCK["Block promotion"]
  Q -->|Yes| REG["Register versioned asset"]
  REG --> STAGE["Staging deployment + load tests"]
  STAGE --> APP{"Approval?"}
  APP -->|No| BLOCK
  APP -->|Yes| CANARY["Canary green"]
  CANARY --> MON["Monitor SLO + quality"]
  MON -->|Regress| RB["Rollback blue"]
  MON -->|Pass| PROD["Scale traffic green"]
~~~

For an auditable pipeline:

1. Store pipeline specs and code in Git; stamp commit SHAs onto jobs.
2. Version data snapshots with immutability or manifests.
3. Version environments and container images with locked dependencies.
4. Run unit, data schema, leakage, performance, security, and serving-contract tests.
5. Evaluate against the champion model and business risk thresholds.
6. Enforce approval controls so developers cannot self-promote high-risk models.
7. Test auth, networking, and latency in staging.
8. Tie canaries and rollbacks to explicit model versions.
9. Retain audit decision records and downstream impact logs.
10. Align archival/retention for reproducibility with data-deletion obligations.

**Never assume an `approved=true` tag alone suffices.** Enforce approvals through permissions and workflows, especially for models impacting people.

## 30. Troubleshooting Azure ML Training and Deployment

| Symptom | Cause | What to Check |
|---|---|---|
| Job queued too long | Compute quota, regional capacity, autoscale startup | Cluster size, quotas, job state |
| Environment build failed | Image, network, or dependency conflict | Build logs, pinned versions, registry reachability |
| Input Storage 403 | Identity lacks data-plane role or ACL | Managed identity, Storage ACLs, DNS |
| Training accuracy suspiciously high | Leakage, bad split, duplicate rows | Feature timing, holdout set |
| Job `Completed` yet model missing | Wrong output binding or path | Job outputs and file structure |
| Model registration URI error | Wrong job/output name or missing output | Job metadata and actual URI |
| Deployment unhealthy | `score.py` import error, missing model file, server env | Container and startup logs |
| Invoke 401/403 | Auth/key/token or network permission | Endpoint auth mode and RBAC |
| Invoke 400 | Bad input JSON schema or shape | Payload validation |
| Invoke 5xx | Scoring exception, OOM, or downstream fault | Runtime logs and traces |
| Endpoint returns 200 yet predictions skew | Feature skew, drift, artifact mismatch | Data contract and ground truth |
| New model is slow | VM quota/resources, batch size, code | Latency, CPU, and memory profiling |
| Idle endpoint still costs money | Serving compute instances still running | Deployment list and Cost Management |
| Duplicate batch predictions | Non-idempotent retries | Batch ID, staging/deduplication |
| Azure Monitor logs missing | Misconfigured diagnostics or table name | Destination, category, and schema |

### Inference Incident Runbook

1. Capture endpoint, deployment, model version, UTC timestamp, and impact scope.
2. Check auth, payload/schema, 4xx/5xx rates, and p95 latency.
3. Compare the new deployment against the prior stable version.
4. Inspect startup logs, model paths, and environment/registry permissions.
5. If a canary regression is confirmed, shift traffic back to `blue` per runbook before lengthy debugging.
6. Check whether bad predictions already drove business actions requiring remediation.
7. Fix the root cause, run integration tests, and re-verify policies before promoting again.
8. Record the incident timeline, owner, preventive actions, and cost impact.

## 31. Cost Management

~~~text
ML platform cost =
  Compute instances + Training clusters/jobs
  + Image/environment builds
  + Model/data storage
  + Online deployment instances + network
  + Batch inference jobs
  + Logging/monitoring
  + Retraining/reprocessing/operational overhead
~~~

### Easily Forgotten Costs

- Notebook compute instances left running overnight.
- Clusters with `min_instances > 0` when no jobs are running.
- Managed online endpoints keeping 1–2 serving instances running continuously.
- Keeping both `blue` and `green` compute provisioned during drawn-out rollouts.
- Expensive GPUs used for small models that run fine on CPUs.
- Raw datasets, checkpoints, artifacts, and logs without retention limits.
- Cross-region data transfers and private networking resources.
- Drift alerts triggering unbounded retraining loops without budgets.

### Mitigations

- Right-size VMs and enable scale-to-zero where appropriate.
- Set budgets, quotas, and tags for owner, cost center, and environment.
- Choose batch vs. online based on real business latency requirements.
- Trigger training on schedules or governed gates—never infinite retrain loops.
- Measure cost per **valid and useful prediction**, not just compute hours.
- Delete **lab endpoints/deployments** when finished per permissions; never delete shared workspaces or shared data.
- Retain artifacts/versions needed for rollback and audits within retention policies.

Never hard-code a fixed unit rate since pricing depends on VM SKU, region, time, and billing model.

## 32. Case Study: Nightly Churn Scoring

A SaaS company holds transactions in Azure SQL and events in ADLS Gen2. Every day before 06:00, customer care needs a churn-risk list.

**Design:**

- ADF prepares curated data and versioned snapshots.
- A weekly Azure ML training pipeline enforces time-based splits, feature contracts, and metrics.
- Candidates are evaluated against the champion model with fairness/privacy reviews where required.
- Approved model asset `v12` is deployed to a batch endpoint.
- Batch scoring writes outputs keyed by batch ID into ADLS staging.
- Data validation runs prior to publishing; retries are idempotent.
- Full lineage connects jobs, data, and artifacts.
- SLOs monitor data freshness, cost, and quality.

### Hypothetical Incident

A team changes `usage_30d` to `usage_7d` in the feature pipeline without updating training code. The batch endpoint completes without technical errors, yet the prediction distribution shifts sharply.

Response workflow:

1. Block publishing when the feature contract fails validation.
2. Retain the previously approved dataset or flag the dataset as unavailable.
3. Fix the feature pipeline and test offline/online parity.
4. Re-run the batch with the same batch ID without duplicating records.
5. Verify ground-truth quality once labels arrive.
6. Add schema regression checks to CI/CD promotion gates.

## 33. Hands-On Lab: From Iris Training to Endpoint Invoke

> **Safety:** use only an authorized lab Azure ML workspace/resource group with capped budgets and permissions. Training and managed endpoints provision billable compute. This guide describes files learners can create themselves and requires no real customer data.

### Part A — Preparation

1. Confirm subscription/tenant with `az account show`.
2. Verify the workspace and the CLI `ml` extension.
3. Check quotas, VM SKUs, networking, and Storage RBAC.
4. Create the directory structure from Section 10.
5. Create `compute.yml`, `conda-train.yml`, and `train-env.yml`.
6. Create the compute cluster and environment asset.

### Part B — Training

1. Write `src/train.py` with `StandardScaler` inside a `Pipeline`.
2. Write `job.yml` using schema-valid output bindings.
3. Submit the job and capture the job ID.
4. Stream job logs and verify `Completed` status.
5. Inspect the output model, metrics, and confusion matrix.
6. Run the quality gate; if it fails, do not register.
7. Record data, code, environment, and compute provenance.

### Part C — Registry

1. Retrieve the actual URI of the named output.
2. Create model asset `iris-logreg:1` of type `custom_model`.
3. Verify model path, tags, and version.
4. Never overwrite artifacts of a previously used version.

### Part D — Deployment

1. Create `score.py` and the inference environment.
2. Create the lab managed online endpoint.
3. Deploy `blue` with model `v1`.
4. Wait for endpoint and deployment to reach Healthy.
5. Invoke with `sample-request.json`.
6. Test invalid payloads, invalid auth, latency, and model metadata.
7. Record p95/5xx and serving cost.
8. Shut down/delete the lab endpoint per approval.

### Part E — Advanced MLOps

1. Train candidate model `v2` with a justified change.
2. Compare offline quality while keeping the holdout test independent.
3. Register `v2` after passing the gate.
4. Deploy `green` with zero traffic and run integration tests.
5. Shift a small canary percentage and watch monitoring.
6. Practice rolling traffic back to `blue` after injecting a controlled lab failure.
7. Design batch scoring for large datasets.
8. Define a feature-drift/quality alert with an assigned owner.
9. Review RBAC, Private Endpoints, secrets, and data retention.
10. Summarize total costs and operational runbooks.

## 34. Self-Check Questions

**Question 1.** How do workspace, compute, data asset, environment, model asset, and endpoint differ?

**Question 2.** Why is a `Completed` training job insufficient to conclude a model is ready for release?

**Question 3.** Does a data asset version automatically make its storage path immutable?

**Question 4.** Why must `StandardScaler` be fit on `train` only, rather than across `train+test`?

**Question 5.** When should you split by time or by group instead of randomly?

**Question 6.** Why can accuracy be misleading on rare-class problems?

**Question 7.** How does a v2 command job specify code, environment, compute, and output bindings?

**Question 8.** How does a `custom_model` differ from an `mlflow_model`?

**Question 9.** Why must you register the exact artifact that passed evaluation?

**Question 10.** Why should `joblib`/pickle models only be loaded from trusted sources?

**Question 11.** How do an online endpoint and a deployment differ?

**Question 12.** When do you choose batch inference over online inference?

**Question 13.** What checks should `score.py` run before calling `model.predict`?

**Question 14.** Why can training-serving skew degrade quality while HTTP still returns 200?

**Question 15.** How do blue/green rollouts and rollbacks protect production?

**Question 16.** Does rolling back traffic automatically undo business decisions already executed?

**Question 17.** How do data drift, concept drift, and prediction drift differ?

**Question 18.** Before ground truth arrives, what can you observe and what must you avoid claiming?

**Question 19.** Does a compute's managed identity automatically get read access to Blob/ADLS?

**Question 20.** Does a Private Endpoint automatically provide authentication/authorization for an endpoint?

**Question 21.** Why can an online deployment keep incurring charges while idle?

**Question 22.** What must be stored so a model version is reproducible and auditable?

**Question 23.** Why should a drift alert never automatically retrain and promote directly to production?

**Question 24.** When a batch job retries, how do you prevent duplicate predictions?

**Completion criteria:** the learner can articulate the end-to-end Azure ML lifecycle, author command training jobs outputting models and metrics, enforce quality gates, register model versions, deploy and invoke managed online endpoints, distinguish batch workloads, and design security, monitoring, rollback, and cost controls.

## Conclusion

**Training, registering, and deploying models in Azure Machine Learning** is a controlled lifecycle from raw data to business outcomes. Training jobs tie together **code, data, environments, and compute**; evaluation proves quality within design bounds; the model registry preserves **named, versioned artifacts with lineage**; and online or batch deployments serve applications within SLOs.

Building trustworthy MLOps on Azure requires adding **data versioning and leakage prevention, quality/security gates, environment provenance, Entra/RBAC and private networking, blue/green rollouts, drift and ground-truth monitoring, batch idempotency, auditing, and cost controls**. A model running on a laptop is only the starting point; long-term value comes from reproducibility, deploying only approved models, operating safely, and rolling back cleanly whenever needed.

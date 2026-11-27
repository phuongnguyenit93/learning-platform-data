# AutoML and Custom Training on Vertex AI

A Java service on Cloud Run collects orders, while BigQuery stores features such as purchase frequency, cart value, and transaction history. The team wants to train a model predicting repeat purchase likelihood, but must decide: **use AutoML so Google Cloud chooses the training process automatically, or write custom training code to control the algorithm?**

**Vertex AI** provides managed machine learning lifecycle infrastructure on Google Cloud. In newer documentation and UIs, some capabilities may appear under **Gemini Enterprise Agent Platform / Agent Platform**; training APIs still use `aiplatform.googleapis.com`. This lesson focuses on **AutoML and custom training**, without equating them to calling Gemini models via API or fine-tuning language models.

This lesson belongs to the **Vertex AI and Machine Learning** chapter, module `CLOUD_PROVIDERS_GCP`. It connects ML choices with project/IAM/VPC organization, Cloud Storage, BigQuery, Compute Engine, GKE, Cloud Run, data protection, releases, quality monitoring, and costs. Any examples that may incur charges are strictly for a **lab project** using public or synthetic data.

## Learning Objectives

After this lesson, you can:

1. Distinguish **AutoML**, **custom training**, **training pipeline**, **CustomJob**, **Model Registry**, and **Endpoint**.
2. Select a training approach based on data type, algorithm, level of control, engineering capability, and cost.
3. Design **train/validation/test** datasets, avoid label leakage, and select appropriate metrics.
4. Create an **AutoML tabular classification** workflow on public data.
5. Package a scikit-learn program into a container and run **custom training on Vertex AI**.
6. Write model artifacts and metrics to Cloud Storage, and evaluate results before registering/deploying a model.
7. Configure service accounts/IAM, resource limits, and observe training jobs.
8. Plan data/model monitoring, retraining, and cleanup of billable resources.

## 1. Core Mindset: Data, Training, Evaluation, and Deployment

~~~mermaid
flowchart LR
    RAW["Cloud Storage / BigQuery<br/>data and labels"] --> PREP["Validation / split<br/>train-val-test"]
    PREP --> CHOICE{"Training approach?"}
    CHOICE --> A["AutoML<br/>managed search & training"]
    CHOICE --> B["Custom training<br/>source code + container"]
    A --> EVAL["Evaluation<br/>metrics + slices"]
    B --> EVAL
    EVAL --> APPROVE{"Meets criteria?"}
    APPROVE -->|Yes| REG["Model Registry"]
    REG --> PRED["Online Endpoint<br/>or Batch Prediction"]
    APPROVE -->|No| ITER["Data/feature/model iteration"]
    ITER --> PREP
~~~

Resources to distinguish:

| Resource | Role |
| --- | --- |
| **Dataset** | References or manages a training dataset according to data type/supported capabilities |
| **AutoML training pipeline** | Manages the AutoML training process and typically creates a managed model |
| **CustomJob** | Runs training code across one or more worker pools; **does not register a model by default** |
| **Custom training pipeline** | Wraps a CustomJob and can **upload a model** after training once artifacts/serving container are declared |
| **Model Registry** | Manages model resources, versions, metadata, and artifact sources |
| **Endpoint** | Resource serving **online prediction**; deployment may keep machines running and incur charges |
| **Batch Prediction Job** | Runs predictions on data in batches without needing a 24/7 endpoint |
| **Vertex AI Pipelines** | Orchestrates multi-step ML workflows; distinct from a single training job |

**Successful training does not mean the model is production-ready.** You must verify data, metrics, user cohorts, security, costs, and deployment behavior.

## 2. How Does AutoML Differ from Custom Training?

| Criterion | AutoML | Custom Training |
| --- | --- | --- |
| Algorithm selection / tuning | Automated across many steps by the service | Controlled directly by the ML team |
| Training code | Little or none to write | Must provide scripts/packages/containers |
| Data format | Follows supported AutoML dataset types and schemas | Flexible according to your framework/code |
| Preprocessing and feature engineering | Automated support per data type | Self-implemented or via pipelines/frameworks |
| Specialized frameworks/architectures | Limited control | TensorFlow, PyTorch, scikit-learn, XGBoost, custom code... |
| GPU/distributed training | Managed by the service per AutoML capabilities | Choose worker pools, GPUs, and distribution yourself |
| Detailed algorithm debugging | Limited | Full logs, checkpoints, profilers, custom code |
| Starting with a lean MLOps team | Usually faster | Requires pipeline setup effort, offers flexibility |
| Billing | Training budget in AutoML units and related tasks | VM/GPU/worker runtime, storage/network/artifacts |

**Selection rule:** if you need a fast baseline for an AutoML-supported task, try **AutoML**; if you need custom algorithms/features, dependency/hyperparameter control, multi-worker distribution, or full code ownership, choose **custom training**. Both require good data and empirical evaluation.

### 2.1. What Should Not Be Called AutoML

- Calling the Gemini API to summarize text **is not** an AutoML training job.
- Increasing `n_estimators` in scikit-learn **does not automatically turn** a script into AutoML.
- Training once and leaving a model unchanged forever **is not MLOps**; monitoring/drift/retraining are needed as the business evolves.

## 3. Supported AutoML Tasks and Selection Conditions

AutoML offerings may include **tabular classification/regression**, image tasks, and certain other data types depending on service, region, and version. **Do not assume AutoML supports every text/video/forecasting type with the same API, dataset, and UI.** Check the feature matrix before designing.

Primary exercise selects **tabular classification**:

~~~text
Goal: predict the Deposit variable (whether a customer subscribes to a term deposit)
Public sample source: gs://cloud-ml-tables-data/bank-marketing.csv
Target column: Deposit
Problem type: supervised classification
~~~

This is Google's public tutorial dataset. In real enterprise scenarios, remove or strictly control sensitive fields and attributes only known **after the outcome occurs**.

### 3.1. Basic Data Conditions

For AutoML tabular classification/regression, current documentation specifies that datasets typically require **at least 1,000 rows**, **at least two columns** (target + feature), no more than **1,000 columns**, and size/row-count limits. The target must suit the problem and must not be empty.

**A 10–20 row CSV can only explain schema**, and is insufficient to train AutoML tabular. Use valid public data or a vetted larger dataset; do not duplicate synthetic rows and treat accuracy as proof of quality.

## 4. Splitting Datasets and Preventing Data Leakage

Data splits:

| Split | Goal | When Used |
| --- | --- | --- |
| **Training** | Learn model parameters | During training |
| **Validation** | Model selection, tuning, and thresholds | During model selection |
| **Test (holdout)** | Final evaluation on data untouched by tuning | After locking choices |
| **Production shadow/canary** | Validate real-world behavior and drift | After model passes offline gates |

AutoML tabular offers a default random split of roughly **80% train / 10% validation / 10% test**, while also supporting **manual** and **chronological** splits depending on problem type. Pick the split suited to your goal; do not assume random is always right.

Examples of preventing leakage:

- **Predicting if a customer will cancel tomorrow:** use only features known **before** prediction time; never include final cancellation status as a feature.
- **Time-series data:** use chronological splits by cutoff; never train on future data.
- **Multiple records per customer:** use group splits if evaluating generalization to brand-new customers.
- **Class imbalance:** use stratified splits for custom classification and measure precision/recall, not just accuracy.
- **Target leakage from IDs:** drop `order_id`, post-event labels, or fields that directly encode the target.

**Do not reuse the test set to repeatedly tune the model.** Tuning on test destroys its independence as a measurement.

## 5. Evaluating Models with Appropriate Metrics

| Problem | Metric | When Useful |
| --- | --- | --- |
| Binary classification | ROC-AUC | Overall ranking across threshold ranges |
| Binary, rare positive class | **PR-AUC, precision, recall** | When false positives/false negatives matter |
| Binary, operational decision | F1, confusion matrix, calibration | Choosing thresholds by error cost |
| Multi-class classification | Macro/micro F1, per-class recall | Prevent common classes from masking rare ones |
| Regression | MAE | Easily interpretable absolute error |
| Regression | RMSE | Penalizes large errors more heavily |
| Business KPI | Revenue uplift, conversion, manual-review rate | Measure real value beyond ML metrics alone |

For example, in a fraud system where only 1% of transactions are fraudulent: a model always predicting "not fraud" gets **99% accuracy** yet **0 fraud recall**. Therefore, tie criteria to business cost, measure metrics per region/segment, and compare against a **baseline**.

**Model evaluation is not a complete fairness/privacy review.** Sensitive data types require threat modeling, bias checks, policy reviews, and dedicated sign-off.

## 6. Preflight: Project, APIs, Region, and IAM

The commands below are for **Cloud Shell/Bash**. Pick `us-central1` for the lab because it is common in AutoML documentation; synthetic/public data has no residency requirements. When using real data, **regions must comply with laws, VPCs, and data residency**.

Read-only inspection of current state:

~~~bash
gcloud auth list
gcloud config get-value project

gcloud ai custom-jobs list \
  --project=PROJECT_ID --region=us-central1

gcloud ai models list \
  --project=PROJECT_ID --region=us-central1
~~~

Once you have a lab project and billing approval:

~~~bash
gcloud services enable \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  --project=PROJECT_ID
~~~

The service may require **Compute Engine API** and service agents depending on the training flow. Recommended permissions:

| Principal | Permissions to Consider |
| --- | --- |
| Job creator | `aiplatform.customJobs.create`, appropriate read/list permissions, `iam.serviceAccounts.actAs` when specifying a runtime SA |
| Dataset/AutoML creator | Appropriate Vertex AI dataset/training pipeline permissions |
| Training runtime service account | Read access only to training data and **write access only to required artifact bucket** |
| Container image pull | Artifact Registry Reader for the identity actually pulling the image |
| Cloud Build | Permissions to build and push images to the repository |
| Model deployer | Permissions to upload/deploy models and configure endpoints appropriately |
| Inference application | Predict permission only on the target endpoint/model per architecture |

**Do not grant Owner/Editor to every identity.** Google-managed **service agents** hold special permissions; never grant service-agent roles to runtime apps or users. Use **Application Default Credentials** locally, and Cloud Run/GKE/VM service accounts in deployed systems.

## 7. Lab A: Training AutoML Tabular via Console

This lab uses public data `gs://cloud-ml-tables-data/bank-marketing.csv` without writing custom model code. The product UI may show **Vertex AI** or **Agent Platform**; field ordering may vary by version.

1. Open **Vertex AI / Agent Platform → Datasets → Create**.
2. Choose **Tabular → Classification/Regression**, region `us-central1`, name `bank-automl-lab`.
3. Select **Cloud Storage CSV** data `gs://cloud-ml-tables-data/bank-marketing.csv` as supported by the UI.
4. Inspect schema/target, row count, and missing values. Select **Train new model → AutoML**.
5. Pick **Classification**, target column `Deposit`; exclude features causing leakage or disallowed for use.
6. Pick **80/10/10 random** split for the lab; for real-time/churn data, use an appropriate split.
7. Pick an optimization objective aligned with business cost, such as ROC-AUC or another supported objective; set a **valid low training budget**, without confusing the budget with a fixed total bill cap.
8. Start training; monitor job state, training metrics, and the resulting model resource upon completion.
9. Inspect **confusion matrix, precision/recall/AUC**, compare with baseline, and determine decision thresholds.
10. Deploy an online endpoint only if truly needed; for batch needs, consider **batch prediction** instead of keeping inference machines running continuously.

**Cost warning:** AutoML can run for hours and incur charges **even if you close the browser**. The training budget caps *training in applicable units* and **does not cover all charges** such as data, batch/online prediction, or artifacts. Check billing before clicking **Start Training**.

### 7.1. What to Record in Your Lab Report

~~~text
Dataset: bank-automl-lab
Target: Deposit
Region: us-central1
Split: random 80/10/10 (lab)
Training budget: [chosen value]
Training state: [succeeded/failed]
Test metrics: [ROC-AUC, precision/recall, or displayed metrics]
Baseline: [comparison]
Deployment: [not deployed if offline evaluation only]
~~~

Do not fill in a metric like "0.95" without actually running training. Only report **observed** results, noting timestamp, data version, and model.

## 8. AutoML Training Pipeline in the API

At the API level, AutoML tabular uses a **`TrainingPipeline`** with the appropriate task definition and inputs:

~~~json
{
  "displayName": "bank-classifier-lab",
  "trainingTaskDefinition": "gs://google-cloud-aiplatform/schema/trainingjob/definition/automl_tabular_1.0.0.yaml",
  "trainingTaskInputs": {
    "targetColumn": "Deposit",
    "predictionType": "classification",
    "trainBudgetMilliNodeHours": 1000,
    "transformations": [
      { "categorical": { "column_name": "job" } },
      { "numeric": { "column_name": "age" } }
    ]
  },
  "modelToUpload": { "displayName": "bank-classifier-lab-model" },
  "inputDataConfig": { "datasetId": "DATASET_ID" }
}
~~~

This is a **structural template**, **not a complete ready-to-run payload** for every dataset version. You must declare transformations for used columns, target config, label/feature types matching the imported schema, and verify valid budget values. `trainBudgetMilliNodeHours=1000` means **1,000 milli-node-hours = 1 node-hour** in the API, not 1,000 hours.

**Do not use `CustomJob` as a substitute for an AutoML task definition.** A managed AutoML `TrainingPipeline` is distinct from a custom self-training Python program.

## 9. Custom Training: From Source Code to CustomJob

With custom training, **you own the code and environment**; Vertex AI manages worker resources, scheduling, logging, and job results. A CustomJob defines **workerPoolSpecs**, each with `machineSpec`, `replicaCount`, and `containerSpec` or `pythonPackageSpec`.

~~~mermaid
flowchart LR
    CODE["train.py + requirements/Dockerfile"] --> BUILD["Artifact Registry image"]
    BUILD --> JOB["Vertex AI CustomJob<br/>1 CPU worker"]
    JOB --> TRAIN["scikit-learn training"]
    TRAIN --> GCS["Cloud Storage artifacts<br/>model.joblib + metrics.json"]
    GCS -. "when approved" .-> REG["Model Registry"]
~~~

Packaging options:

- **Prebuilt training container:** uses a prebuilt image with code as a Python package or script.
- **Custom container:** choose your own OS, dependencies, and entrypoint. Ideal when custom libraries or complex configurations are required.
- **Autopackaging:** tooling that packages local code into an image when parameters fit.
- **Distributed training:** multiple worker pools/replicas plus framework synchronization strategies; **simply raising replicaCount does not make every script train in distributed mode**.

This lesson uses a **single-worker CPU** custom container; no GPU is needed to learn how to create a job.

## 10. Lab B: scikit-learn Training Code and Artifact Export

We use the built-in scikit-learn `digits` dataset to **avoid uploading personal data** while keeping the lab small. This is a **digit image classification task** with numeric features, distinct from the AutoML bank dataset; the goal is to learn custom training infrastructure, **not to compare AUC across two different datasets to decide which approach is superior**.

Lab folder structure **on the learner's machine**:

~~~text
vertex-custom-lab/
├── train.py
├── requirements.txt
├── Dockerfile
└── customjob.yaml
~~~

`requirements.txt`:

~~~text
scikit-learn==1.5.2
joblib==1.4.2
google-cloud-storage==2.18.2
~~~

Versions are pinned for lab reproducibility. Production requires vulnerability scanning/updates and aligning **training–serving** versions; never let untrusted model artifacts pass into `joblib.load()`.

### 10.1. File train.py

~~~python
import json
import os

import joblib
from google.cloud import storage
from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

X, y = load_digits(return_X_y=True)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

model = RandomForestClassifier(
    n_estimators=100, n_jobs=2, random_state=42
)
model.fit(X_train, y_train)
pred = model.predict(X_test)

metrics = {
    "accuracy": float(accuracy_score(y_test, pred)),
    "macro_f1": float(f1_score(y_test, pred, average="macro")),
    "confusion_matrix": confusion_matrix(y_test, pred).tolist(),
    "train_rows": int(len(y_train)),
    "test_rows": int(len(y_test)),
    "seed": 42
}
print(json.dumps(metrics, ensure_ascii=False))

joblib.dump(model, "model.joblib")
with open("metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics, f, indent=2)

model_dir = os.environ.get("AIP_MODEL_DIR", "").rstrip("/")
if not model_dir.startswith("gs://"):
    raise RuntimeError("AIP_MODEL_DIR must be set to a gs:// directory")

client = storage.Client()
for name in ("model.joblib", "metrics.json"):
    uri = f"{model_dir}/{name}"
    storage.Blob.from_string(uri, client=client).upload_from_filename(name)
    print(f"Uploaded: {uri}")
~~~

**Engineering note:** we use a seed and `stratify=y` so the split is reproducible; metrics are measured on a holdout untouched during fitting. This demo omits a separate validation/tuning step because it intentionally trains **one fixed configuration**; if tuning multiple configurations, separate a validation set and reserve test for final evaluation.

### 10.2. Dockerfile

~~~dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY train.py .
ENTRYPOINT ["python", "train.py"]
~~~

**Never embed Cloud JSON credentials or PII datasets in a Docker image.** Vertex AI attaches workload identity to the container via the job's `serviceAccount`. The container accesses Cloud Storage using Application Default Credentials.

## 11. Building the Image and Preparing the Output Bucket

Run only after the lab project has Billing, quota, Cloud Build/Artifact Registry permissions, and budget. Pick `us-central1`, replacing `PROJECT_ID` and `UNIQUE` with assigned values. **Bucket names must be globally unique.**

~~~bash
gcloud artifacts repositories create vertex-training-lab \
  --repository-format=docker \
  --location=us-central1 \
  --description="Lab Vertex training images" \
  --project=PROJECT_ID

gcloud storage buckets create \
  gs://PROJECT_ID-vertex-models-UNIQUE \
  --location=us-central1 \
  --project=PROJECT_ID

# From the vertex-custom-lab/ directory containing Dockerfile and train.py.
gcloud builds submit \
  --region=us-central1 \
  --tag=us-central1-docker.pkg.dev/PROJECT_ID/vertex-training-lab/digits-trainer:v1 \
  --project=PROJECT_ID .
~~~

**Cloud Build has its own costs/quotas and permissions.** If the build fails with `PERMISSION_DENIED` on Artifact Registry, inspect the exact **Cloud Build execution service account**, image creation permissions, and org policies; **do not grant Project Owner**. Never overwrite a tag currently serving production; production pins **image digests** for reproducibility.

Create a runtime service account for the job:

~~~bash
gcloud iam service-accounts create vertex-trainer-lab \
  --display-name="Vertex custom training lab" \
  --project=PROJECT_ID

gcloud storage buckets add-iam-policy-binding \
  gs://PROJECT_ID-vertex-models-UNIQUE \
  --member=serviceAccount:vertex-trainer-lab@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator
~~~

The execution SA needs permission to **write artifacts** to the bucket; if code reads training data from GCS/BigQuery, grant **read permission on the exact sources** as well. The job submitter needs `iam.serviceAccounts.actAs` on this SA. If image pull fails, check Artifact Registry permissions for the **identity pulling the image** and the corresponding service agent.

## 12. Creating a CustomJob from a Config File

File `customjob.yaml`, replacing `PROJECT_ID` and `UNIQUE`:

~~~yaml
workerPoolSpecs:
  - machineSpec:
      machineType: n1-standard-4
    replicaCount: 1
    containerSpec:
      imageUri: us-central1-docker.pkg.dev/PROJECT_ID/vertex-training-lab/digits-trainer:v1
baseOutputDirectory:
  outputUriPrefix: gs://PROJECT_ID-vertex-models-UNIQUE/digits-run
serviceAccount: vertex-trainer-lab@PROJECT_ID.iam.gserviceaccount.com
~~~

This is a **CustomJobSpec** without root fields like `displayName`; the CLI supplies the display name separately. `baseOutputDirectory.outputUriPrefix` causes Vertex AI to set environment variables such as `AIP_MODEL_DIR` pointing to a GCS subdirectory (typically under the corresponding run folder). The script in Section 10 uploads artifacts there.

Run **only with cost approval**:

~~~bash
gcloud ai custom-jobs create \
  --project=PROJECT_ID \
  --region=us-central1 \
  --display-name=digits-custom-lab \
  --config=customjob.yaml

gcloud ai custom-jobs list \
  --project=PROJECT_ID --region=us-central1

# Replace JOB_ID with the ID from list/create output.
gcloud ai custom-jobs describe JOB_ID \
  --project=PROJECT_ID --region=us-central1
~~~

**Expected outcome:** the job transitions through provisioning/running states and ends in `JOB_STATE_SUCCEEDED`. Logs show JSON metrics and upload paths; GCS contains `model.joblib` and `metrics.json` inside the run's model directory.

**Do not predict a specific accuracy number:** that measurement must come from an actual run. This sample model **has not been automatically created in Model Registry**, because we ran a standalone `CustomJob` rather than a `TrainingPipeline` declaring `modelToUpload`.

### 12.1. When GPU or Distributed Training Is Needed

Worker pool specs require `machineSpec.acceleratorType`, `acceleratorCount`, and a GPU-enabled image/framework, appropriate quota, and matching runtime/cuDNN. Some machine types require GPUs; availability varies by region.

Distributed training requires **appropriate code** (PyTorch DDP, TensorFlow distributed strategy...) and coordination among workers. **Do not simply set `replicaCount=4` on a `load_digits` script and call it distributed training**: four workers would independently train and overwrite each other's artifacts.

## 13. Choosing CustomJob vs Training Pipeline with Model Registration

| Execution Mode | Natural Output | Additional Steps Needed |
| --- | --- | --- |
| **CustomJob** | Workers execute code; artifacts depend on code | Register model manually or in a later pipeline |
| **Custom TrainingPipeline + modelToUpload** | Trains and can create a Model resource on success | Properly formatted artifacts + valid **serving container** |
| **AutoML TrainingPipeline** | AutoML training + managed model per supported flow | Evaluation, review, and online/batch selection |
| **Vertex AI Pipelines** | Orchestrates prep/train/evaluate/register/deploy steps | Components, pipeline metadata, governance |

For scikit-learn `model.joblib`, serving inference requires a **prediction container compatible** with the training version or a **custom prediction container**. The training Dockerfile in Section 10 cannot serve as an endpoint container directly: it runs `train.py` and exits without **exposing an HTTP inference endpoint**.

**Production gate:** register/deploy a model only after checking metrics, input/output schemas, vulnerability scans, IAM, and model reproducibility.

## 14. Evaluating AutoML and Custom Training Fairly

Do not compare AutoML on bank marketing data against RandomForest on digits; the tasks and datasets are completely different. For a real benchmark, hold constant:

1. **Same dataset snapshot** at training time, with valid access permissions.
2. **Same train/validation/test split** or comparable split rule.
3. **Same label definition and feature availability** (preventing leakage).
4. **Same metrics and validation-chosen thresholds**, compared on an untouched test set.
5. **End-to-end training costs**: data prep, tuning, compute, artifacts, and operations.
6. **Inference latency/cost** on CPU/GPU/endpoints or batch.
7. **Fairness/slice evaluation** across authorized geographic, device, or user segments.
8. Debuggability, retraining ease, CI/CD integration, drift tracking, and auditability.

| Experiment Outcome | Recommended Decision |
| --- | --- |
| AutoML baseline is strong, operations simple | Use AutoML and build monitoring/gates |
| Custom clearly wins on business KPIs | Use custom when gains outweigh added complexity |
| Both perform similarly, SLA/latency differ | Choose based on serving and maintenance cost |
| Insufficient data/bad labels | **Fix the data** before spending more on training |
| Fairness/PII/leakage risks present | **Do not deploy**; re-evaluate data/policies |

## 15. Minimum MLOps After Training

Training once is only the beginning. A production flow should include:

~~~mermaid
flowchart TD
    DATA["Data version + contracts"] --> TRAIN["AutoML / CustomJob"]
    TRAIN --> EVAL["Holdout + slice metrics"]
    EVAL --> GATE{"Metric / policy gates passed?"}
    GATE -->|Yes| REG["Register model + version"]
    REG --> DEPLOY["Batch / canary endpoint"]
    DEPLOY --> MON["Drift, latency, cost, quality"]
    MON --> RETRAIN["Trigger retrain when needed"]
    RETRAIN --> DATA
    GATE -->|No| FIX["Review features, labels, bias"]
    FIX --> DATA
~~~

Post-deployment signals to track:

- **Data/feature drift**: feature distributions diverge from the training set.
- **Prediction drift**: output distributions shift.
- **Quality drift**: when delayed ground-truth labels arrive, precision/recall/MAE shift.
- **Operational SLO**: p95/p99 inference latency, throughput, availability, errors.
- **Business SLO**: whether decisions improve conversion/losses.
- **Cost**: GPU/CPU/endpoint uptime, batch jobs, model registry artifacts.

**Drift does not mean you must retrain immediately.** Inspect what changed, verify labels, and check model effectiveness. For a Java app on Cloud Run, invoke the model via Vertex AI endpoint/batch output using a least-privilege **runtime service account**; never embed credential keys in container images or frontends.

## 16. Security, Sensitive Data, and Networking

- **IAM:** separate training job creators, training runtime SA, model approvers, and inference callers.
- **Data locality:** pick regions for datasets, buckets, training jobs, artifact registries, and endpoints complying with data residency rules.
- **GCS/BQ:** grant read access on training snapshots and write access on artifacts at the narrowest bucket/dataset scope; enable logging/auditing as required.
- **Secrets:** use Secret Manager or workload identity; never hardcode keys/tokens in `train.py`, Dockerfiles, or container args.
- **Private connectivity:** if training needs Cloud SQL private IPs/on-prem data, configure networking/PSC/VPC/private service access matching the Vertex training job type; **IAM does not replace network routing**.
- **PII:** minimize sensitive fields, control labels/features and log/artifact viewer permissions; never log raw records containing PII.
- **Supply chain:** pin base image/dependency versions and digests, scan vulnerabilities, sign/approve containers per policy.
- **Model artifacts:** `joblib`/`pickle` can execute code on deserialization; **never load artifacts from untrusted sources**.
- **Fairness/safety:** evaluate slices, privacy exposure, and explainability appropriate to the decision type. Finance/credit requires dedicated regulatory compliance.

**Use only public samples/synthetic data in labs**; sending real data to AI services must follow permissions, contracts, and organizational policies.

## 17. Training Costs: Budget Comprehensively

| Component | When Charges Occur |
| --- | --- |
| AutoML | Compute/node-hour units or model training budget per task type |
| Custom training | Machine type × worker replicas × duration, plus GPU/accelerators when used |
| Hyperparameter tuning | **Multiple training trials**, total cost higher than a single job |
| Cloud Storage | Dataset snapshots, checkpoints, model artifacts, logs |
| BigQuery/Dataflow | Data prep, feature queries, materialization |
| Cloud Build/Artifact Registry | Building and storing images |
| Online prediction | Deployed endpoint machines/accelerators billed over time, even with low traffic |
| Batch prediction | Compute executing batch predictions |
| Network/Logging/Monitoring | Egress, logs, metrics, and supporting services |

Example **rough** estimate for custom training:

~~~text
Approximate training cost =
  worker replicas × hours run × machine price/hour
  + GPU (if any)
  + storage/artifacts + build/log/network

1 CPU replica × 0.5 hours is only 0.5 machine-hours;
it does NOT mean total system cost equals just that VM price.
~~~

**Do not copy hardcoded prices from old docs:** check [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) and Billing SKUs in your region. Budget alerts **do not automatically stop training jobs or endpoints**. Undeploy/delete endpoints when unused; clean up model artifacts deliberately after confirming no other pipeline depends on them.

## 18. Observing and Troubleshooting Training Jobs

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| `PERMISSION_DENIED` reading GCS | Runtime SA lacks appropriate Object Viewer/Reader | Check principal and bucket IAM |
| Cannot pull image | Repo wrong region/tag, missing Artifact Registry Reader | Check URI and image pull identity |
| `AIP_MODEL_DIR` empty | `baseOutputDirectory` not configured on job | Check `customjob.yaml` and env vars |
| Job stays RUNNING without training | Image/cluster/data startup or quota wait | Inspect job details and Cloud Logging |
| GPU OOM | Batch size/model too large | Reduce batch size, use mixed precision if suitable, scale capacity |
| More replicas not faster | Code lacks distributed training support | Use a distributed framework/strategy |
| Model missing from Registry | Standalone `CustomJob` does not auto-register | Upload model or use TrainingPipeline |
| AutoML refuses to train | Too few rows/missing target, unsupported location/objective | Check schema, min rows, region |
| Unusually high accuracy | Leakage or flawed split | Check feature chronology/group splits |
| High accuracy but poor positive class | Imbalanced classes | Inspect PR-AUC/recall/slice metrics |
| Training differs from last run | Changed seed, snapshot, image/dependency | Pin data/image/code/seed |
| Bill rises after training | Endpoint still deployed or artifacts retained | Check Billing, endpoints, storage |

**Read logs by job ID/training pipeline ID**; never log user data or secrets to debug. Store Git commit, image digest, data snapshot, training parameters, metrics, and cost for traceability.

## 19. Practical Exercises and Self-Check

**Exercise 1 — Choosing an approach.** You need a baseline predicting labels on 50,000 tabular rows with few engineers writing ML code.

*Suggested answer:* Try AutoML tabular first, then compare against a simple baseline and evaluate cost.

**Exercise 2 — Leakage check.** Field `refund_completed_at` only appears after a refund finishes; the team wants to predict refund likelihood at checkout.

*Answer:* Exclude it from features at prediction time and enforce a temporal cutoff.

**Exercise 3 — CustomJob.** Build the container per Sections 10–12, running only in an approved lab project.

*Success criteria:* Job `SUCCEEDED`, GCS contains `model.joblib`/`metrics.json`, logs record metrics and image/dataset versions.

**Exercise 4 — Fair comparison.** Comparing AutoML with custom XGBoost.

*Success criteria:* Same dataset snapshot, splits, labels, metrics, accounting for both training and inference costs.

**Question 5.** Does AutoML eliminate the need for data quality checks?

*Answer:* No. Flawed data/labels produce poor or biased models.

**Question 6.** Does a `CustomJob` automatically create a model in Model Registry upon completion?

*Answer:* Not by default; you need an explicit model upload or a TrainingPipeline with `modelToUpload`.

**Question 7.** Where should training callbacks or containers write models for durable storage?

*Answer:* Cloud Storage, commonly via `AIP_MODEL_DIR` when `baseOutputDirectory` is specified.

**Question 8.** Is the AutoML training budget a cap on your entire bill?

*Answer:* No. Data prep, prediction, storage, and networking are billed separately.

**Question 9.** Is 99% accuracy on a dataset with 1% positive labels good enough?

*Answer:* No. Predicting all negative achieves 99% too; you need recall/PR-AUC/business impact.

**Question 10.** Can the training Dockerfile that runs a script and exits be deployed directly as an endpoint serving container?

*Answer:* No. A serving container requires an inference server/protocol and compatible artifacts.

**Question 11.** Does raising `replicaCount` from 1 to 4 turn the RandomForest script into distributed training?

*Answer:* No. You need code and a framework that support distributed training.

**Question 12.** Should you bake a service-account JSON key into the training image?

*Answer:* No. Use a runtime service account/ADC with least-privilege IAM.

**Question 13.** During tuning, can you inspect test accuracy every round to pick the next hyperparameters?

*Answer:* No; that leaks test information into model selection.

**Question 14.** Will a model trained well a year ago remain accurate automatically when customer behavior shifts?

*Answer:* No. Monitor drift, track metrics on fresh labels, and run validated retraining.

## 20. Production Checklist and Conclusion

- [ ] Problem/label/metric tied to error costs and business SLOs.
- [ ] AutoML/custom compared against a simple baseline.
- [ ] Dataset meets row minimums, schema/target are valid, and data leakage is removed.
- [ ] Train/validation/test split fits time/group structure and preserves a holdout test set.
- [ ] Evaluation includes overall + slice metrics, fairness/privacy, and calibration where needed.
- [ ] Training code, container digests, datasets, seeds, parameters, and outputs are versioned.
- [ ] Runtime SA IAM is least-privilege, artifact buckets are private, and no PII/secrets are logged.
- [ ] CustomJob/TrainingPipeline has GCS output and error/timeout handling.
- [ ] Model Registry/deployment happens only after approval, with a serving container compatible with artifacts.
- [ ] Online/batch prediction chosen based on latency and cost.
- [ ] Retraining pipeline, validation gates, model rollback, and drift monitoring are in place.
- [ ] Data residency/VPC/CMEK/organization policies verified as required.
- [ ] Billing accounts for training, tuning, inference, storage, network, and logs.
- [ ] Lab cleanup executed carefully without deleting shared artifacts.

**Conclusion:** **AutoML** delivers a fast baseline for supported data types and objectives; **custom training** gives you ownership of algorithms, environments, resource sizing, and custom logic. Both generate value only when **data is accurate, evaluation is leak-free, registration/deployment is safe, and cost and quality are monitored continuously**.

## Official Reference Documentation

- [Train tabular classification/regression with AutoML](https://cloud.google.com/vertex-ai/docs/tabular-data/classification-regression/train-model)
- [Prepare tabular classification/regression data](https://cloud.google.com/vertex-ai/docs/tabular-data/classification-regression/prepare-data)
- [Data splits for tabular models](https://cloud.google.com/vertex-ai/docs/tabular-data/data-splits)
- [Vertex AI custom training overview](https://cloud.google.com/vertex-ai/docs/training/overview)
- [Create a custom training job](https://cloud.google.com/vertex-ai/docs/training/create-custom-job)
- [Custom training code requirements](https://cloud.google.com/vertex-ai/docs/training/code-requirements)
- [Export scikit-learn model artifacts](https://cloud.google.com/vertex-ai/docs/training/exporting-model-artifacts)
- [Create a training pipeline](https://cloud.google.com/vertex-ai/docs/training/create-training-pipeline)
- [Configure compute for custom training](https://cloud.google.com/vertex-ai/docs/training/configure-compute)
- [gcloud ai custom-jobs create](https://cloud.google.com/sdk/gcloud/reference/ai/custom-jobs/create)
- [Vertex AI IAM and service agents](https://cloud.google.com/vertex-ai/docs/general/access-control)
- [Vertex AI training and inference pricing](https://cloud.google.com/vertex-ai/pricing)

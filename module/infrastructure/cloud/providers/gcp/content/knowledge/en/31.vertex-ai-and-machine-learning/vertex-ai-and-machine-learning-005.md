# Hyperparameter Tuning and Experiment Management

An online learning platform predicts students at risk of dropping out of a course to offer timely support. The ML team trained an initial model, but does not yet know which `learning_rate`, `regularization`, or tree count gives good results; each person tries a configuration in a notebook and records results in a spreadsheet. That workflow is hard to reproduce, easily **misuses the test set for optimization**, loses track of which model was trained on which dataset version, and can burn substantial GPU budget without meaningful gains.

**Vertex AI hyperparameter tuning** automatically runs experiments (*trials*) with selected parameters and optimizes against a declared **validation metric**. **Vertex AI Experiments** logs parameters, metrics, and artifacts for comparison, traceability, and evidence-based decisions. This lesson belongs to the **Vertex AI and Machine Learning** chapter of module **CLOUD_PROVIDERS_GCP**, connecting Cloud Storage/BigQuery, IAM, VPC, Cloud Logging, Pipelines, and cost; examples use **scikit-learn models on synthetic data** with no real student information.

**After this lesson, you can:**

1. Distinguish **model parameters**, **hyperparameters**, **trial**, **study/tuning job**, and **experiment run**.
2. Design a search space, target metric, budget, concurrent trial count, and stopping criteria.
3. Prepare a custom training script that accepts CLI parameters and reports metrics to the tuning service.
4. Log/compare experiment runs using the Vertex AI SDK; distinguish summary metrics from TensorBoard time series.
5. Select configurations based on validation, retrain and evaluate **once on the holdout test set**, and manage lineage and permissions.
6. Investigate failed trials, prevent data leakage, and estimate the cost of an experimentation campaign.

## 1. Two Loops: Parameter Optimization and Evidence Management

~~~mermaid
flowchart LR
    DATA["Versioned dataset"] --> SPLIT["Train / Validation / Test"]
    SPLIT --> HPT["HyperparameterTuningJob<br/>study + search space"]
    HPT --> T1["Trial 1"]
    HPT --> T2["Trial 2"]
    HPT --> TN["Trial N"]
    T1 --> METRIC["Validation metric<br/>returned to optimizer"]
    T2 --> METRIC
    TN --> METRIC
    METRIC --> BEST["Select candidate config"]
    BEST --> FINAL["Retrain + evaluate<br/>holdout test once"]
    HPT -. "Trial IDs / parameters<br/>and metrics" .-> EXP["Vertex AI Experiments<br/>run tracking when integrated"]
    FINAL --> REG["Model Registry / deployment<br/>after approval"]
~~~

| Concept | Purpose | Example |
| --- | --- | --- |
| **Model parameters** | Weights **learned** from data during `fit()` | Logistic Regression coefficients |
| **Hyperparameters** | Settings chosen **before** training or via tuning | `C`, `max_iter`, learning rate, batch size |
| **Trial** | One training execution with one hyperparameter combination | `C=0.1`, `max_iter=200` |
| **Tuning job / study** | Orchestrates multiple trials and uses metrics to suggest configs | 12 trials, max 3 concurrent trials |
| **Validation metric** | Metric the service optimizes during parameter search | `val_auc` to **maximize** |
| **Experiment** | Shared group to compare multiple runs | `dropout-risk-v1` |
| **Experiment run** | A named record with parameters, metrics, and optional artifacts/lineage | `baseline-001`, `candidate-002` |
| **Model Registry** | Manages artifacts/model versions and deployment lifecycle | Model version that passed validation/test |

**Important:** a `HyperparameterTuningJob` stores trial info and optimization metrics; that **does not mean** the service automatically creates a separate ExperimentRun for every trial. To compare alongside other baselines/trials or trace code/datasets in **Vertex AI Experiments**, integrate logging or sync metadata by design.

### 1.1. Hyperparameter Tuning Is Not Fine-Tuning a Foundation Model

The word "tuning" has multiple meanings. Here we optimize **hyperparameters of a custom training model** across trials. It differs from **supervised fine-tuning of a foundation model/Gemini** or prompt tuning, which have different APIs, permissions, data formats, and pricing. Do not extrapolate Gemini fine-tuning workflows from the `HyperparameterTuningJob` configurations below.

### 1.2. Avoiding Optimization on the Test Set

~~~text
Deduplicated and split data
  ├─ Train: fit model and all statistical preprocessing steps
  ├─ Validation: compute metric for each trial; choose hyperparameters
  └─ Test (holdout): used only after locking configuration/method
~~~

For **time-ordered** data (students studying earlier/later), split train/validation/test by **time cutoffs** when forecasting the future; when multiple rows belong to the same student, consider a **group split by `student_id`** to prevent the same person from appearing in both train and validation. Normalization/encoding/balancing steps must fit within the training fold without peeking at validation/test statistics.

A higher val AUC does not guarantee product value: you must also verify calibration, fairness, data distribution shifts, inference latency, and cost.

## 2. Designing the Search Space and Objective

### 2.1. Choosing Metrics Tied to Product Goals

| Problem | Candidate Metric | Notes |
| --- | --- | --- |
| Dropout risk classification | ROC AUC or PR AUC, **MAXIMIZE** | If positives are very rare, PR AUC/recall@precision may fit better than accuracy |
| Completion time regression | MAE/RMSE, **MINIMIZE** | Watch units and outlier impact |
| Content ranking | NDCG@K, **MAXIMIZE** | Validation must represent queries/user cohorts |
| Demand forecasting | WAPE/sMAPE/MAE per SLA | Avoid metrics unstable when actuals are 0 |

**Metric names must match identically** between the tuning job spec and the `report_hyperparameter_tuning_metric` call. Tuning gets no valid signal if code reports `auc` while `metric_spec` declares `val_auc`, or if training only calls `print()` instead of reporting via the supported protocol.

### 2.2. Hyperparameter Types and Sampling

| Type | Example | When to Use |
| --- | --- | --- |
| **Double / continuous** | `learning_rate ∈ [1e-5, 1e-1]` | Continuous parameters; use **log scale** if spanning orders of magnitude |
| **Integer** | `max_depth ∈ [3, 15]` | Integer values within a range |
| **Discrete** | `batch_size ∈ {16, 32, 64, 128}` | Only a finite set of numeric values is allowed |
| **Categorical** | `optimizer ∈ {"adam", "sgd"}` | Selecting an unordered category |

Start with **2–5 high-impact hyperparameters** informed by model understanding. Spreading across `learning_rate`, `batch_size`, `depth`, `dropout`, `activation`, `optimizer`, and `weight_decay` with only 6 trials cannot effectively explore a large combinatorial space.

### 2.3. Search Algorithms

- **Default/Bayesian optimization:** uses completed trial results to suggest subsequent configurations, typically efficient when budgets are costly.
- **Random search:** tests broad space baselines, simple and easy to compare.
- **Grid search:** evaluates a deliberate finite grid; in Vertex AI, use only with parameter specs supporting grid search. Avoid huge grids since combinations grow exponentially.

No algorithm guarantees finding the **global optimum** under a finite budget and noisy metrics. Use repeated validation/cross-validation or multiple seeds when variance affects decisions.

## 3. Managing Trial Budget, Concurrency, and Early Stopping

A Vertex AI HyperparameterTuningJob specifies **trial count**, **parallel count**, search algorithm, parameter space, objective, and a **trial job spec** (machine/worker/container) used for each training run.

| Setting | Meaning | Trade-offs |
| --- | --- | --- |
| `max_trial_count` | Desired maximum number of trials | Increases exploration opportunity but increases machine-hours and cost |
| `parallel_trial_count` | Number of trials that can run concurrently | Cuts wall-clock time but raises peak resource/quota needs and uses less feedback from prior trials |
| `max_failed_trial_count` | Threshold of failed trials triggering tuning job stop | Should not be set high enough to ignore widespread misconfiguration |
| `measurement_selection` | Pick best or last metric when a trial reports multiple measurements | `best` can bias on noisy metrics; `last` suits steady progression |
| Machine type/accelerator | Resources **per trial** | Concurrent trials multiply CPU/GPU demand |
| Search algorithm | Rule suggesting hyperparameters | Bayesian leverages feedback better with fewer parallel trials |

**Capacity estimate:** 12 trials, each running 20 minutes on 1 VM, with `parallel_trial_count=3`. Total **VM-minutes ≈ 12 × 20 = 240**, while ideal wall-clock time is around **80 minutes** assuming uniform trials, zero provisioning delay, and sufficient quota. Running three concurrent trials does not cut total compute to a third; it only shortens waiting time.

If each trial uses 1 GPU, peak demand requires **3 corresponding GPUs** plus quota/availability in the region, aside from storage, data loading, and overhead. Pick limits based on budget, quota, deadlines, trial count, and expected learning from early trials.

### 3.1. Early Stopping and Measurement

When training over many epochs, clearly underperforming trials can be **stopped early via supported policies/algorithms** or self-stopped via early stopping in the script to save compute. When reporting multiple measurements, Vertex AI uses `measurement_selection="best"` or `"last"` to pick the representative measurement.

**Do not confuse the two mechanisms:** stopping training when validation stops improving is ML logic in your script or an HPT policy; `measurement_selection` merely determines which reported measurement ranks the trial. If early epochs score well then degrade from overfitting, `best` yields a higher score; picking `best` on noisy metrics invites the **winner's curse**. Check algorithm docs and reported steps before enabling auto-stopping.

### 3.2. Budget Control Rules

1. Run an untuned **baseline**, measuring metric + time/cost.
2. Run 4–8 small trials to validate metrics, parameter ranges, and repeatability.
3. Only after reviewing results, expand trial count/parallelism within quota.
4. Set **timeouts, alerts, and cost thresholds** so jobs do not fail/loop endlessly.
5. Stop if metric gains do not justify cost/complexity or remain unstable outside validation.

**Budget alerts are not hard spending caps.** When running multiple concurrent jobs, sum **total CPU/GPU-hours** across all trials, logs, Cloud Storage artifacts, networking, and supporting services.

## 4. scikit-learn Example: Running a Trial and Reporting Metrics

To separate orchestration from model complexity, this lab uses **LogisticRegression on synthetic data** generated by `sklearn.datasets.make_classification`. The script accepts two HPT-supplied parameters and **reports `val_auc`** to Vertex AI via `cloudml-hypertune`. No real Cloud Storage/BigQuery data is required.

### 4.1. File `train.py`

~~~python
import argparse
import json
import numpy as np
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--c", type=float, default=1.0)
    parser.add_argument("--max_iter", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report_hpt", action="store_true")
    args = parser.parse_args()

    if args.c <= 0 or args.max_iter < 1:
        raise ValueError("c must be > 0; max_iter must be >= 1")

    x, y = make_classification(
        n_samples=3000, n_features=20,
        n_informative=10, n_redundant=3,
        weights=[0.8, 0.2], flip_y=0.02,
        random_state=args.seed,
    )
    # Split test FIRST; during HPT use only train/validation.
    x_dev, _, y_dev, _ = train_test_split(
        x, y, test_size=0.2, stratify=y, random_state=args.seed
    )
    x_train, x_val, y_train, y_val = train_test_split(
        x_dev, y_dev, test_size=0.25,
        stratify=y_dev, random_state=args.seed
    )
    model = make_pipeline(
        StandardScaler(),  # fit ONLY on x_train to avoid leakage
        LogisticRegression(
            C=args.c, max_iter=args.max_iter, random_state=args.seed
        ),
    )
    model.fit(x_train, y_train)
    auc = roc_auc_score(y_val, model.predict_proba(x_val)[:, 1])
    if not np.isfinite(auc):
        raise ValueError("Validation AUC must be finite")

    print(json.dumps({
        "validation_auc": float(auc),
        "c": args.c, "max_iter": args.max_iter, "seed": args.seed
    }))

    # Trial reports metric via HPT protocol, not just printing to stdout.
    if args.report_hpt:
        import hypertune  # pip package: cloudml-hypertune
        hypertune.HyperTune().report_hyperparameter_tuning_metric(
            hyperparameter_metric_tag="val_auc",
            metric_value=float(auc),
            global_step=1,
        )


if __name__ == "__main__":
    main()
~~~

**Note:** this illustrates **custom training/hyperparameter optimization**, not a deployable student-risk prediction model. The dataset is generated with a fixed seed so trials compare fairly. The test set is split off but **not used** to report objectives to HPT; an independent final evaluation is required after locking the configuration.

Run **locally** to verify logic with zero cloud cost:

~~~bash
python -m pip install scikit-learn numpy
python train.py --c 0.1 --max_iter 200 --seed 42
~~~

The local run **omits** `--report_hpt`, so `hypertune` is not required for this step. If the script fails, fix parsing/schema/model issues before spending Vertex AI resources.

### 4.2. Flag Names and Metric Reporting Must Match

The tuning service appends search-space-selected parameters to the trial's command line, for example:

~~~text
python train.py --report_hpt --c 0.03 --max_iter 100
~~~

Thus `parameter_spec` must have keys `c` and `max_iter`, and the script must accept `--c` and `--max_iter`. If the job objective declares `val_auc`, the script must call `report_hyperparameter_tuning_metric(hyperparameter_metric_tag="val_auc", ...)`. On mismatch, trials may run to completion yet the optimizer receives no valid metric.

## 5. Creating a HyperparameterTuningJob with Vertex AI SDK

### 5.1. Prerequisites Before Submitting a Real Job

Use only an **approved lab project** with billing, Vertex AI API enabled, and a region supporting custom training. Required:

- Permissions to create/read Vertex AI **CustomJobs/HyperparameterTuningJobs**, and Cloud Logging access to view errors.
- **Dedicated training service account** with minimal permissions on artifact buckets/data sources if any; submitter has `iam.serviceAccounts.actAs` on that SA.
- **Cloud Storage staging bucket** in a matching location, IAM for source upload and runtime; verified image with compatible Python/scikit-learn.
- Machine quota (CPU/GPU if used), trial/parallelism limits, and budget alerts.
- Do not put real data, credentials, or student identities into source code, console logs, or experiment parameters.

In enterprise environments with VPC Service Controls, private egress, Artifact Registry, CMEK, or custom networks, configure networking/service agents per policy. Commands in this lesson are **documentation**, and do not automatically create/run GCP jobs.

### 5.2. File `submit_tuning.py`

SDK example using `CustomJob.from_local_script` to package the Section 4 script into a training job template per trial:

~~~python
import os
from google.cloud import aiplatform
from google.cloud.aiplatform import hyperparameter_tuning as hpt

PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ["LOCATION"]
STAGING_BUCKET = os.environ["STAGING_BUCKET"]  # gs://...
TRAINING_SA = os.environ["TRAINING_SA"]        # email of granted SA
TRAINING_IMAGE = os.environ["TRAINING_IMAGE"]  # approved Python image

aiplatform.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=STAGING_BUCKET,
)

custom_job = aiplatform.CustomJob.from_local_script(
    display_name="student-risk-trial-lab",
    script_path="train.py",
    container_uri=TRAINING_IMAGE,
    requirements=["numpy", "scikit-learn", "cloudml-hypertune"],
    args=["--report_hpt", "--seed", "42"],
    machine_type="n1-standard-4",
    replica_count=1,
)

hp_job = aiplatform.HyperparameterTuningJob(
    display_name="student-risk-hpt-lab",
    custom_job=custom_job,
    metric_spec={"val_auc": "maximize"},
    parameter_spec={
        "c": hpt.DoubleParameterSpec(
            min=0.001, max=100.0, scale="log"
        ),
        "max_iter": hpt.DiscreteParameterSpec(
            values=[100, 200, 300], scale="linear"
        ),
    },
    max_trial_count=6,
    parallel_trial_count=2,
    search_algorithm=None,        # Default optimization
    measurement_selection="last",
    labels={"purpose": "learning-lab"},
)

# BILLABLE OPERATION: run only on an approved project/budget.
hp_job.run(service_account=TRAINING_SA, sync=True)

print("Job:", hp_job.resource_name)
for trial in hp_job.trials:
    print("Trial:", trial.id, "State:", trial.state,
          "Parameters:", trial.parameters,
          "Final:", trial.final_measurement)
~~~

**Prerequisites to run:** `TRAINING_IMAGE` must be a **real image URI compatible with the SDK/runtime**, not a placeholder. Choose an image from the supported [prebuilt containers list](https://cloud.google.com/vertex-ai/docs/training/pre-built-containers) or a custom image in Artifact Registry. For production, **pin library versions and image digests** rather than using `latest`/unpinned `requirements`; parameters here are kept simple to focus on HPT.

The SDK creates **up to 6 trials**, **up to 2 parallel trials**, using a single `n1-standard-4` worker template per trial. Because the script uses synthetic data, it requires no GPU or database connection. For real workloads, specify exact `base_output_dir`, Cloud Storage permissions, network/region, encryption, and workload identity per policy.

**Important boundaries:**

- `max_trial_count=6` is the experimentation budget, not 6 top models auto-registered in Model Registry.
- `hp_job.trials` contains trial parameters and final measurements **once the job has data/finishes**; check terminal/failed states before picking.
- `metric_spec={"val_auc":"maximize"}` optimizes **validation**; it does not evaluate test or fairness.
- `parallel_trial_count=2` raises concurrent resource usage but does not guarantee 2x completion speed.
- `hp_job.run(sync=True)` blocks until completion and can fail on trial, quota, network, or IAM issues; application scripts must log errors and never treat "submitted" as "model selected."

### 5.3. gcloud and REST Options

If a project uses infrastructure automation instead of the Python SDK, jobs can be submitted via the corresponding Vertex AI API using:

~~~bash
# Inspect command help before creating billable resources:
gcloud ai hp-tuning-jobs create --help

# BILLABLE OPERATION; use an owner-reviewed config file:
# gcloud ai hp-tuning-jobs create \
#   --region="$LOCATION" \
#   --display-name="student-risk-hpt-lab" \
#   --max-trial-count=6 --parallel-trial-count=2 \
#   --config="hpt-config.yaml"
~~~

The config must define **study metrics, search parameters, and trial job spec** (image/worker machine/args). Do not copy `gcloud ai custom-jobs create` and assume you have an optimizer; that creates a single training job. With the `google-cloud-aiplatform` SDK, HPT jobs use the `HyperparameterTuningJob` class, not `CustomJob.run` called 6 times in a loop.

### 5.4. Reading Trial Results Properly

Once the job completes, compare trials with a **succeeded state** and **valid metrics**, then choose one or a few candidate configurations. Do not pick `trial 1` merely because it ran first; nor assume an optimizer always beats a well-tuned baseline.

| Trial (hypothetical) | `C` | `max_iter` | `val_auc` | Observation |
| --- | ---: | ---: | ---: | --- |
| T01 | 0.001 | 100 | 0.841 | Strong regularization, likely underfitting |
| T02 | 0.03 | 200 | 0.886 | Candidate |
| T03 | 0.3 | 200 | **0.893** | Top on validation |
| T04 | 10 | 100 | 0.871 | Check convergence |
| T05 | 0.1 | 300 | 0.889 | Very close to T03 |
| T06 | 50 | 300 | 0.865 | No improvement |

**These are hypothetical numbers for decision practice**, not actual script outputs. When margins are tight and validation is noisy, compare across additional seeds/folds and check standard deviation; a trial with `val_auc=0.893` does **not** guarantee the same test AUC or business impact.

## 6. Experiment Management with Vertex AI Experiments

Hyperparameter tuning **searches parameters**; experiment tracking answers: *who ran it, with what code/data, using which parameters, how well did it perform, where are the models/artifacts, and can it be reproduced?*

### 6.1. Experiments, Runs, and Metrics

| Logged Content | Where Recorded | Example |
| --- | --- | --- |
| **Run parameters** | Vertex AI Experiments | `c=0.3`, `max_iter=200`, `dataset_version=v20261118` |
| **Summary metrics** | Experiment Run | `val_auc=0.893`, `test_auc=0.880` (final run only) |
| **Time series metrics** | Experiment Run + **Vertex AI TensorBoard backing resource** | `train_loss`/`val_loss` per epoch |
| **Artifacts/metadata** | Vertex ML Metadata/Experiments and artifact store | GCS model URI, dataset digest, model version |
| **Pipeline run/lineage** | Vertex AI Pipelines/Metadata when integrated | Data validation → train → evaluate → register |

**Summary metrics** are single scalar values representing a run; **time series** log sequences over steps and require a backing **TensorBoard instance**. Calling `log_metrics` repeatedly with the same key generally **overwrites** previous values; do not use it to plot epoch-by-epoch loss curves. `cloudml-hypertune` reports metrics to the optimizer and **does not replace** `aiplatform.log_params/log_metrics` for recording runs per team conventions.

### 6.2. Code to Log an Experiment Run (Not an HPT Submission)

The snippet below records a run for a baseline/candidate with known metrics; it **does not train a model itself**:

~~~python
import os
from google.cloud import aiplatform

aiplatform.init(
    project=os.environ["PROJECT_ID"],
    location=os.environ["LOCATION"],
    experiment="student-risk-lab",
)

# Each attempt uses a distinct run ID without overwriting others.
with aiplatform.start_run(run="baseline-001") as run:
    run.log_params({
        "algorithm": "logistic_regression",
        "c": 1.0, "max_iter": 200, "seed": 42,
        "dataset_version": "synthetic-v1",
        "code_revision": "REPLACE_WITH_GIT_COMMIT",
    })
    run.log_metrics({
        "val_auc": 0.87,
        "fit_seconds": 2.1,
    })

# Read comparison table (requires Experiment read permission).
df = aiplatform.get_experiment_df(
    experiment="student-risk-lab",
    include_time_series=False,
)
print(df[["run_name", "param.c", "metric.val_auc"]].head())
~~~

**Note:** `0.87` and `2.1` are illustrative placeholders and must be replaced with **measured metrics** when used as evidence. `REPLACE_WITH_GIT_COMMIT` must be replaced with the actual code revision. Never record passwords, tokens, URLs with signed tokens, or student lists in params/tags/logs. For real experiments, pass `aiplatform.start_run(run=..., resume=True)` only when **intentionally continuing that exact run**; avoid accidental overwrites that erase history.

### 6.3. Time Series, TensorBoard, and Autologging

~~~python
# Conceptual pattern when experiment is linked to Vertex AI TensorBoard:
# aiplatform.init(project=..., location=...,
#                 experiment="student-risk-lab",
#                 experiment_tensorboard="projects/.../tensorboards/...")
# with aiplatform.start_run(run="train-epochs-001"):
#     for epoch, loss in enumerate(epoch_losses):
#         aiplatform.log_time_series_metrics(
#             {"train_loss": float(loss)}, step=epoch
#         )
~~~

Without a **backing TensorBoard instance**, do not call `log_time_series_metrics` and assume data was persisted. The SDK also offers `aiplatform.autolog()` for certain frameworks; it is a **framework-specific helper** and does not automatically log every custom metric, dataset version, or artifact. For HPT, integrate tracking **inside each trial** or sync the trials table → experiment runs with consistent naming after job completion; do **not** collapse multiple trials into a single run.

## 7. Selecting the Final Model and Reproducibility

### 7.1. Safe Promotion Workflow

1. **Conclude the HPT campaign** once budgeted trials finish, verify trial states/measurements, and compare against baseline.
2. Pick **a few candidates** based on validation metric, stability across folds/seeds, training duration, and inference cost—not solely the highest raw number.
3. **Freeze hyperparameters, code revision, data/feature definitions, and preprocessing.**
4. **Retrain** the chosen configuration on train + validation (per evaluation policy) and evaluate **once on the holdout test set not used for selection**.
5. Check cohort-level quality, calibration, robustness, privacy/bias, latency, and operational requirements.
6. Only after passing all gates, store the **model artifact**, register in **Vertex AI Model Registry**/version, and consider controlled deployment via endpoint/batch prediction.
7. Record lineage metadata: `experiment_run_id`, `hpt_job_id`, `trial_id`, data/model checksums, code version, and approver.

**Never auto-deploy the "best trial."** The best HPT trial on `val_auc` may not be best on business KPIs, fairness, or inference cost. Whenever data drifts or feature pipelines change, re-evaluate even if hyperparameters stayed identical.

### 7.2. Experiment Reproducibility Checklist

| Information | Why Keep It |
| --- | --- |
| `dataset_uri`, version/snapshot, schema, and checksum | Inputs must stay invariant across trials, or changes must be explicit |
| Train/validation/test split policy + seed | Avoid skewed comparisons and data leakage |
| Docker image **digest**, dependency lock, Python/framework versions | Models can behave differently if runtimes/libraries change |
| Code commit, feature engineering, preprocessing | Ensures scripts and transforms are reusable |
| Hyperparameters, trial state, optimizer version/algorithm | Explains outcomes and costs |
| Summary metrics, validation learning curves if any | Compares quality and overfitting |
| Training resources, region, GPU/CPU-hours, cost | Informs trade-offs and budgets |
| Model artifact URI/hash + evaluation report | Traces exactly which model was deployed |

Fixing a seed provides **partial** reproducibility, yet GPUs, distributed training, non-deterministic kernels, and data ordering can prevent bit-for-bit identical results. For a tiny 0.001 AUC difference, do not claim a definitive win without assessing variance.

### 7.3. Multi-Metric Evaluation and Business Constraints

Vertex AI HPT supports configuring metric objectives per supported features, yet **one optimization number** cannot capture every requirement. For example, a high-AUC model with >200 ms inference latency or low precision may still be unacceptable.

Illustrative decision rule:

~~~text
Minimum criteria:
  validation PR-AUC >= 0.55
  p95 inference latency <= 150 ms at realistic batch size
  zero data policy or fairness gate violations
Then:
  prefer lowest cost per 1,000 predictions
  among candidates meeting all criteria above
~~~

These thresholds are **hypothetical**; base real thresholds on product needs, user cohorts, and project scientific review. Never treat a tuning metric as the sole deployment contract.

## 8. Security, IAM, Networking, and Cost Management

### 8.1. Separating Submission and Execution Permissions

| Role | Recommended IAM Scope | Risk If Over-Privileged |
| --- | --- | --- |
| ML engineer/CI submitting jobs | Create/read HPT and CustomJobs in approved project/region | Project-wide `Vertex AI Admin` when only job submission is needed |
| User attaching custom SA | `iam.serviceAccounts.actAs` on the **approved training SA** | Could impersonate stronger SAs if granted project-wide |
| **Training service account** | Read train/validation data, write artifacts/logs; BigQuery jobs/data if needed | Access to all buckets/datasets containing PII |
| Experiment/metadata consumer | Write/view Vertex AI Experiments/metadata per role | Deleting/modifying others' metadata |
| Deployer/model owner | Register/deploy models **after approval** | Giving deployment rights to everyone running HPT |

**Code inside the training container does not inherit permissions** simply because the submitter is logged into `gcloud`. When specifying a custom SA via `hp_job.run(service_account=...)`, Cloud Storage/BigQuery/Artifact Registry access must be granted to the **actual runtime identity** and relevant service agents. Never store service account JSON keys in notebooks, source code, Docker images, or environment logs.

### 8.2. Protecting Student Data

- Learning/payment records may contain PII and sensitive info. Use only **approved features**, encryption, anonymization/pseudonymization, and comply with data residency/retention.
- In BigQuery, apply IAM and row/column policies as needed. In Cloud Storage, restrict buckets/prefixes and logs.
- Never write raw feature rows/labels, access tokens, signed URLs, or individual prediction outputs into Vertex AI Experiments, TensorBoard, or stdout.
- Select regions for training/models/artifacts matching data residency requirements; private networking, CMEK, and VPC Service Controls must align with supported capabilities and policy.
- When sharing experiment dashboards, remember that **metric/parameter names and values** can also leak sensitive details or data paths.

### 8.3. Optimizing the Tuning Budget

Example campaign with **20 trials**, averaging 25 minutes each on one billable machine:

\[
20 \times \frac{25}{60} \approx 8.33\ \text{machine-hours}
\]

This is **equivalent machine-hours**, not currency; if a trial uses multiple workers/GPUs, multiply each resource by its rate and actual runtime. `parallel_trial_count=4` finishes faster in wall time, but demands higher peak capacity; total machine-hours **do not shrink automatically** from running in parallel.

| Component | What to Budget For |
| --- | --- |
| Custom training compute | CPU/GPU machine-hours per trial, retries, and failed trials |
| Cloud Storage / BigQuery | Input reads, artifacts, logs/checkpoints, data egress |
| Vertex AI Experiments/TensorBoard/metadata | Provisioned resources, retention, metric storage, and current billing |
| Network & security | Egress, private networking, CMEK/KMS if used |
| Retraining/evaluation/deployment | Final training run, batch prediction, or continuously running online endpoint |

**Practical cost optimization:** start with a baseline, run a small smoke-test trial to verify plumbing, constrain the search space, use CPU for light models, enable GPUs only when warranted, apply validated early stopping, set artifact retention, and shut down/avoid accidentally leaving test endpoints running. Pricing and quotas vary by region/machine/accelerator; verify [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) and Cloud Billing to finalize budgets.

## 9. Observing HPT and Diagnosing Failures

### 9.1. Useful Observation Sources

| Source | What to Inspect |
| --- | --- |
| **HyperparameterTuningJob / Trials** | Job state, trial IDs, suggested parameters, final/intermediate measurements, errors |
| **Cloud Logging** | Python/import errors, metric reporting, container startup, IAM/permission errors |
| **Cloud Monitoring** | CPU/GPU/network utilization, training job metrics, quota, and latency |
| **Vertex AI Experiments** | Baseline vs candidate metrics, params, artifacts, run details |
| **Vertex AI TensorBoard** | Learning curves over epochs/steps when backed by a resource |
| **BigQuery/Cloud Storage metrics** | Data source throughput/latency, permission errors, cost |

**Do not rely solely on "job succeeded"**: tuning can produce trials with non-comparable metrics, optimize the wrong validation split, or run code that fit preprocessing on the test set. Inspect scripts and numbers as well as trial states.

### 9.2. Layered Troubleshooting Runbook

| Symptom | Likely Cause | Remediation |
| --- | --- | --- |
| HPT job creation fails | Missing `aiplatform.hyperparameterTuningJobs.create`, API/quota, or invalid params | Check submitter principal, IAM, and config; do not blindly grant Owner |
| `Permission denied` attaching custom SA | Missing `iam.serviceAccounts.actAs` | Verify permissions on that exact SA |
| Container starts then fails import | Mismatched image/dependencies/Python version | Pin image digest and package versions; run local smoke test |
| Trial finishes without objective | Wrong `metric_tag`, missing hypertune call, exception before reporting | Match `metric_spec` with script; inspect driver logs and measurements |
| Job parameters ignored by model | Mismatched `--flag`/`argparse`, script ignores args | Print **non-sensitive** param values, assert ranges, and test locally |
| Trials run very slowly | Provisioning, GPU quota, data loading, CPU/I/O bottleneck | Separate scheduling vs training time; inspect machine utilization |
| Many trials FAILED | Common bug, bad dataset path, IAM, out of memory | Halt campaign and fix script before burning more budget |
| High validation AUC, low test | Data leakage, validation overfitting, bad split, noisy metric | Audit pipeline/splits, narrow search space, evaluate unbiased test |
| Experiments missing trial metrics | HPT does not auto-sync to ExperimentRuns | Add explicit param/metric logging or sync trials → runs |
| Cannot log learning curves | Missing TensorBoard backing resource or permissions | Check `experiment_tensorboard`, IAM, and SDK version |
| Cost exceeds forecast | Too many trials × machines/GPUs, retries, artifacts/logs | Reduce budget/parallelism; inspect quotas and billing |

**6-step workflow:** identify project/region/job ID → check trial states and errors → read training logs → compare script/metric flags → verify data/VM/quota/IAM → retry **one small config** under a new run ID. Never change IAM, image, seed, data, and search space simultaneously, or you will not isolate the root cause.

## 10. Tiered Lab: Local First, Cloud Second

**Goal:** understand a single training run, hyperparameter effects, trial selection, and logging an ExperimentRun. The lab needs no real data and **does not require creating an online endpoint**.

### 10.1. Level A — Zero GCP Resources Created

In a local Python environment **where package installation is allowed**, create a lab folder with `train.py` from Section 4 and run:

~~~bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install numpy scikit-learn

python train.py --c 0.001 --max_iter 100 --seed 42
python train.py --c 0.1 --max_iter 200 --seed 42
python train.py --c 10 --max_iter 300 --seed 42
~~~

**Record in a table** the parameters, validation AUC, and runtime for the three runs. Keep the seed fixed during the initial comparison. If a `ConvergenceWarning` appears, do not ignore it: it may reflect too low a `max_iter`; try increasing iterations or adjusting regularization intentionally.

| Run | `C` | `max_iter` | Val AUC (measured) | Notes |
| --- | ---: | ---: | --- | --- |
| Local-01 | 0.001 | 100 | ... | Strong regularization |
| Local-02 | 0.1 | 200 | ... | Compare to baseline |
| Local-03 | 10 | 300 | ... | Check overfitting/convergence |

This tests the **script/metric contract**; never draw production tuning conclusions from three small runs. Synthetic data intentionally includes noise.

### 10.2. Level B — Optional on an Approved Lab Project

Only after **billing, Vertex AI API, staging bucket, training SA, and budget** are approved:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export LOCATION="us-central1"
export STAGING_BUCKET="gs://YOUR_APPROVED_LAB_STAGING_BUCKET"
export TRAINING_SA="YOUR_APPROVED_TRAINING_SA@YOUR_PROJECT.iam.gserviceaccount.com"
export TRAINING_IMAGE="YOUR_VERIFIED_PYTHON_TRAINING_IMAGE_URI"

# READ-ONLY: verify project, API, and quota before incurring charges.
gcloud config set project "$PROJECT_ID"
gcloud services list --enabled --filter="aiplatform.googleapis.com"
gcloud storage buckets describe "$STAGING_BUCKET"
gcloud ai hp-tuning-jobs list --region="$LOCATION"
~~~

Once the owner verifies all prerequisites, `google-cloud-aiplatform` is installed locally, and `train.py` passed smoke testing, run:

~~~bash
# BILLABLE: creates an HPT job with up to 6 trials.
python -m pip install google-cloud-aiplatform
python submit_tuning.py
~~~

If image, bucket, SA, or quota is not ready, **do not run** and complete the paper lab in Section 10.3 instead. Never use a fake service account email just to test "if it works"; never grant `Vertex AI Admin` to the whole team just to silence a 403 error.

Once the job gets an ID, check status in Console or via:

~~~bash
# READ-ONLY: replace with actual HPT job ID.
gcloud ai hp-tuning-jobs describe "YOUR_HPT_JOB_ID" \
  --region="$LOCATION" --project="$PROJECT_ID"
~~~

In Console, open **Vertex AI → Training → Hyperparameter tuning jobs** (UI labels may vary across product updates) to view trial parameters/metrics and logs. Do not assume "6 trials submitted" means every trial succeeded; verify each trial's state and measurement.

### 10.3. Level C — Paper Lab Requiring No GCP

Given the trial table in Section 5.4 and a baseline val AUC of **0.870**, complete the following:

1. Select a candidate configuration based on validation, specifying the trial and delta over baseline.
2. Assess the significance if T03/T05 differ by only **0.004 AUC** while bootstrap validation error is roughly ±0.01.
3. Propose a verification step **without touching the holdout test set**.
4. Write the minimum experiment run record to log, including `trial_id`, dataset version, and cost.
5. State when the **holdout test set** may be evaluated.

**Guidance:** T03 leads validation (0.893), +0.023 over baseline; the T03–T05 gap is tiny relative to ±0.01 error, warranting multiple seeds/folds or proper extra validation. The holdout test set is used **only after locking method/configuration**, never repeatedly queried to tweak the search space.

### 10.4. Cleaning Up Data and Stopping Costs

Do not create an Endpoint in this lab; if you created an HPT job, confirm all trials are **terminal** and inspect log permissions/records before deleting metadata per retention policy. To cancel a running job, do so via Console/API with owner confirmation; cancellation may **not take effect immediately**, and charges incurred up to stop time still apply. Delete **only files/artifacts under your own staging prefix**, never run recursive deletes on shared buckets.

## 11. Scenario Exercises

### Scenario A — Overfitting to Validation

A team evaluates 2,000 combinations on the same 1,000 validation rows and picks a trial with 0.99 AUC. On holdout test, AUC drops to 0.77.

**Task:** distinguish **model** overfitting from overfitting caused by **selecting across too many trials on the same validation set**.

**Solution:** picking among 2,000 trials on a tiny validation set lets the optimizer exploit noise and causes **selection bias**; it does not necessarily mean the model trained too many epochs. You need a more representative validation set, nested CV if appropriate, a smaller search budget, single-use holdout testing, and student/time leakage checks.

### Scenario B — Parallelism and GPU Quota

One trial needs 2 GPUs and takes 45 minutes. The plan is 16 trials with `parallel_trial_count=8`; regional quota has only 8 GPUs free.

**Task:** can 8 trials run simultaneously? Propose a reasonable upper bound.

**Solution:** 8 trials × 2 GPUs = **16 GPUs peak**, exceeding quota of 8; GPU-wise, at most **4 trials can run concurrently**, aside from other machine quotas. Pick ≤4 and evaluate Bayesian search efficiency/cost. Lowering parallelism keeps ideal total GPU-hours at `16 × 2 × 0.75 = 24 GPU-hours`—changing concurrency does not reduce total compute.

### Scenario C — Job Metric Differs from Script

`metric_spec={"val_auc": "maximize"}`, yet code sends `hyperparameter_metric_tag="auc"`. The job starts and trial logs print AUC, yet no valid final measurements appear.

**Task:** where to fix?

**Solution:** use the **exact same name** in config and `report_hyperparameter_tuning_metric`, then run a single-trial smoke test before scaling the campaign; `print()` to stdout does not replace metric reporting.

### Scenario D — Non-Reproducible Results

T03 won, yet nobody knows the training data, library versions, or seed; someone updated the source BigQuery table before rerunning.

**Task:** what must be added to ExperimentRun and the pipeline?

**Solution:** log dataset snapshot/version or checksum, split policy/seed, image digest, dependency lock, code commit, trial ID, hyperparameters, artifacts, metrics, and job ID. Never use a mutable `latest` table name as a version; once data changes, it is a different experiment, not an identical rerun.

### Scenario E — Budget Overrun

A team runs 40 trials, 1 GPU each, 30 minutes each; due to quota, only 2 trials run concurrently. The owner mistakenly thinks "2 at a time" means paying for only 1 GPU-hour total.

**Task:** calculate ideal total GPU-hours and explain.

**Solution:** `40 × 0.5 × 1 = 20 GPU-hours`, excluding retries/provisioning/other resources. Parallelism of 2 makes ideal **wall-clock duration** around `40 / 2 × 30 = 600 minutes`, without eliminating the remaining 38 trials. Check actual pricing, quotas, and stop criteria.

### Scenario F — Experiment vs Production Model

One trial tops `val_auc`, yet hurts recall for new students, triples p95 inference latency, and requires data in another region.

**Task:** should it deploy automatically?

**Solution:** **no**; evaluate segment fairness/recall, latency/cost, compliance, and data residency. The HPT objective is a **technical criterion**, not a substitute for deployment gates. Pick a balanced candidate or redesign objectives/constraints and re-evaluate through the proper process.

### Quantitative Exercise — Budget vs Wall-Clock Time

Three options for **24 trials**, 15 minutes each on **1 identical VM**:

| Option | Parallel Trials | Ideal VM-Hours | Ideal Wall-Clock |
| --- | ---: | ---: | ---: |
| A | 1 | 6 | 360 minutes |
| B | 4 | 6 | 90 minutes |
| C | 8 | 6 | 45 minutes |

**Questions:**

1. Why are VM-hours nearly identical? — All three run **24 × 15 minutes = 360 VM-minutes**, before overhead/retries.
2. Why might C not yield the **best model**? — Bayesian optimization receives less feedback from trials running simultaneously.
3. If quota permits only 4 VMs, which options stay within quota? — A or B, assuming one trial uses exactly one VM.
4. If the report is due in 1 hour, do A/B/C guarantee completion? — No; B takes 90 min ideally, C takes 45 min ideally yet exceeds quota here and excludes provisioning overhead. You must adjust resources, optimize the script, or request approved quota.

### Self-Check

1. **How do hyperparameters differ from model parameters?** — Hyperparameters are chosen via config/search; model parameters are learned during training.
2. **Is every trial automatically an ExperimentRun?** — No, unless tracking integration is implemented.
3. **Why not use the test set for HPT?** — Causes overfitting to test and overly optimistic final evaluations.
4. **Must `metric_spec` names match the script's reported tag?** — Yes.
5. **Does a larger `parallel_trial_count` reduce total compute automatically?** — No.
6. **Is `measurement_selection="best"` always good on noisy metrics?** — No; it can pick noise spikes.
7. **How do summary metrics differ from time series?** — Summaries store a single value; time series store per-step sequences requiring TensorBoard.
8. **Does a fixed seed guarantee bit-for-bit reproducible GPU training?** — Not guaranteed.
9. **Why use a dedicated training SA?** — Enforces least privilege, separating submitters from data access permissions.
10. **Can the best validation trial be deployed straight to production?** — No; requires retraining/testing and production gates.

## 12. Pre-Campaign Review Checklist for Production Tuning

| Item | Pass Criteria |
| --- | --- |
| **Problem** | Clear baseline, business KPI, target metric, and `maximize`/`minimize` direction |
| **Data** | Proper time/group splits, zero leakage, versioned, and permissions verified |
| **Script correctness** | Local smoke test passed, all hyperparameter flags parsed, valid metric reported with exact tag |
| **Search space** | Meaningful parameters, valid ranges/scales, not overly wide for the trial budget |
| **Cost/quota** | Max/parallel trials, machine/GPU quota, timeout, budget, and alerts approved |
| **IAM/network** | Submitter, runtime SA, Artifact Registry, Cloud Storage/BigQuery, and VPC follow least privilege |
| **Reproducibility** | Code commit, image digest, dependency lock, seed, dataset version, and input artifacts logged |
| **Tracking** | Trial ID ↔ HPT job ID ↔ ExperimentRun ID, metrics, timing, cost, and artifacts traceable |
| **Evaluation** | Validation for selection, single-use holdout test, confidence intervals, and slices checked |
| **Promotion** | Retraining, inference latency/fairness/compliance verified, model version, and approver recorded |
| **Operations** | Failure/quota/permission runbooks, resource cleanup/retention, no out-of-process auto-deploy |

### Experiment Report Template for ML Engineers

~~~text
Experiment:        student-risk-lab
Objective:         maximize val_auc
Dataset/version:   synthetic-v1 / checksum: ...
Split policy:      train/validation/test; group/time policy: ...
Training image:    digest: ...
Code revision:     commit: ...
HPT job ID:        projects/.../hyperparameterTuningJobs/...
Trials:            6 max; 2 concurrent; 0-6 completed
Best candidates:   trial ID + hyperparameters + val metric
Uncertainty:       folds/seeds + confidence interval
Cost:              actual machine-hours + storage/network
Test result:       only after selecting candidate, with method fixed
Decision:          approve / reject / investigate
Owner and date:    ...
~~~

If an important field is unknown, mark it **unverified** rather than fabricating values. Any changes to data, code, or splits must be logged as a separate experiment run/campaign to preserve trustworthy history.

## 13. Official Google Cloud Documentation

- [Overview of hyperparameter tuning](https://cloud.google.com/vertex-ai/docs/training/hyperparameter-tuning-overview) — trials, metrics, search optimization, and limits.
- [Create a hyperparameter tuning job](https://cloud.google.com/vertex-ai/docs/training/using-hyperparameter-tuning) — reporting objectives, configuring jobs, trial specs.
- [Vertex AI Python SDK: HyperparameterTuningJob](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.HyperparameterTuningJob) — `metric_spec`, `parameter_spec`, trial count, parallelism, and `run()`.
- [Vertex AI Python SDK: CustomJob](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.CustomJob) — `from_local_script`, image, requirements, and runtime identity.
- [Vertex AI training containers](https://cloud.google.com/vertex-ai/docs/training/pre-built-containers) — supported images/runtimes.
- [Vertex AI Experiments overview](https://cloud.google.com/vertex-ai/docs/experiments/intro-vertex-ai-experiments) — experiments, runs, metrics, artifacts, and ML Metadata.
- [Log data to experiment runs](https://cloud.google.com/vertex-ai/docs/experiments/log-data) — `log_params`, `log_metrics`, and TensorBoard time series.
- [Autolog data](https://cloud.google.com/vertex-ai/docs/experiments/autolog-data) — conditions and frameworks supporting autologging.
- [Compare and analyze runs](https://cloud.google.com/vertex-ai/docs/experiments/compare-analyze-runs) — retrieving comparison tables and reading results.
- [Training metrics](https://cloud.google.com/vertex-ai/docs/general/monitoring-metrics) — monitoring custom training/compute.
- [Vertex AI access control](https://cloud.google.com/vertex-ai/docs/general/access-control) — IAM and training job permissions.
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing) — current unit rates for training/experiments/related resources.

**Conclusion:** hyperparameter tuning automates trying multiple configurations but **does not replace sound ML evaluation methodology**. Define the right search space, validation metric, and trial budget, report metrics accurately to the optimizer, and use **Vertex AI Experiments** to record parameters, metrics, dataset/code versions, and artifacts. Promote a model to production only after **holdout testing, cohort quality checks, latency, data permissions, and cost** all meet requirements.

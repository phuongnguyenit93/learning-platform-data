# BigQuery ML and Near-Data Inference on Google Cloud

> **Chapter:** BigQuery  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost.

**BigQuery ML (BQML)** lets you build, evaluate, predict with, and explain machine learning models using **GoogleSQL directly inside BigQuery**. Data engineers do not need to export millions of rows to a local machine just to run a classification or forecasting workflow. Models are stored as resources inside a BigQuery dataset; inference can participate directly in SQL queries, SQL pipelines, or scheduled jobs.

This hands-on lesson builds a **customer churn prediction** model on synthetic data using **`LOGISTIC_REG`, `ML.EVALUATE`, `ML.PREDICT`, and `ML.EXPLAIN_PREDICT`**. Afterward, we examine **remote models** connecting AI services such as Vertex AI/Gemini to distinguish "near-data inference" from processing that actually executes outside BigQuery. **No real customer data** is used in any example.

**Cost warning:** BigQuery queries, model training, remote inference, storage, and connected AI platforms can incur charges. Run only in an authorized lab project, and check estimates and cost caps before executing. Resource-mutating statements are clearly marked; never run them against production data.

## Learning Objectives

1. Distinguish BigQuery ML local models, remote models, feature engineering, training, evaluation, and inference.
2. Choose a model type for the problem: regression, classification, clustering, forecasting, or generative AI.
3. Write GoogleSQL to generate synthetic data and split train/evaluation/holdout sets without label leakage.
4. Train a `LOGISTIC_REG` model with `CREATE MODEL`, evaluate with `ML.EVALUATE`, and inspect the confusion matrix.
5. Use `ML.PREDICT` for batch scoring, understanding predicted labels and probabilities.
6. Apply `ML.EXPLAIN_PREDICT` / `ML.WEIGHTS` within their proper scope.
7. Understand BigQuery connections and remote inference to Vertex AI, including data paths and costs.
8. Design schedules, model versioning, drift monitoring, IAM, and rollback plans for real-world operations.

## 1. What Does "Near-Data Inference" Mean?

Data platforms typically involve multiple stages: application events land in BigQuery, SQL transforms them into features, a model generates predictions, and business systems consume the outputs.

~~~mermaid
flowchart LR
    SRC["Cloud Run / GKE / apps"] --> INGEST["Batch / streaming ingestion"]
    INGEST --> TABLE["BigQuery feature tables"]
    TABLE --> TRAIN["CREATE MODEL\nBigQuery ML"]
    TRAIN --> MODEL["BigQuery model resource"]
    TABLE --> SCORE["ML.PREDICT / ML.EVALUATE"]
    MODEL --> SCORE
    SCORE --> OUT["Prediction table"]
    OUT --> JOB["Scheduled query / dashboard / API service"]
    TABLE --> REMOTE["Remote model via BigQuery connection"]
    REMOTE --> VAI["Vertex AI / Gemini endpoint"]
    VAI --> REMOTE
~~~

For **BQML models executed natively inside BigQuery**, features and SQL workflows stay inside the same analytics platform, avoiding exporting files to external training scripts. However, **"near the data" does not automatically mean all compute happens on the same machine, in the same network boundary, or with zero egress**. With **remote models**, BigQuery **sends requests containing selected input data to an external AI service** and receives responses, requiring separate IAM, residency, data governance, and cost evaluation.

| Component | Role | Example |
|---|---|---|
| BigQuery dataset | Container holding tables/models in the same data location | bqml_lab |
| Training table/query | Features and label used for training | churn_features |
| Local BQML model | Managed resource storing algorithm and weights | churn_logreg_v1 |
| ML.EVALUATE | Measures model quality with metrics | precision, recall, ROC AUC |
| ML.PREDICT | Scores new data | churn score per customer |
| ML.EXPLAIN_PREDICT | Feature attributions for predictions | Why a sample received a high score |
| Remote model | Represents an AI endpoint via connection | gemini_remote |
| Prediction table | Output table consumed by batch jobs | churn_scores_yyyymmdd |

### 1.1. Choosing a Model Type

| Problem | Example BQML Model Type | Output |
|---|---|---|
| Predict revenue from features | `LINEAR_REG`, `BOOSTED_TREE_REGRESSOR` | Numeric value |
| Will a customer churn? | `LOGISTIC_REG`, `BOOSTED_TREE_CLASSIFIER` | Label + probability |
| Segment user cohorts | `KMEANS` | Cluster/centroid |
| Time-series forecasting | `ARIMA_PLUS`, `ARIMA_PLUS_XREG` | Forecast and confidence intervals |
| Anomaly detection | Supported models via `ML.DETECT_ANOMALIES` | Anomaly score/flag |
| Text summarization | Remote model + `AI.GENERATE_TEXT` | LLM-generated text |
| Embeddings / vector search | Supported embedding model/function | Vectors for similarity search |

The model type determines valid syntax and functions. **`ML.FEATURE_IMPORTANCE`** applies to tree-based models, whereas **`ML.WEIGHTS`** suits linear/logistic models—do not swap them across model types. Support varies by service, location, edition, and feature availability. Reference: <https://docs.cloud.google.com/bigquery/docs/bqml-introduction>

### 1.2. BigQuery ML Differs from a Real-Time Serving Endpoint

An **`ML.PREDICT`** query excels at batch scoring integrated with SQL and persisted to tables. It is not a **low-latency API endpoint** for per-request HTTP inference. When millisecond latency, autoscaling, and strict online SLOs are required, evaluate **Vertex AI endpoints**, supported model export/registration, feature serving, or a dedicated online serving architecture.

## 2. Preparing the Project, Dataset, Permissions, and Budget

### 2.1. Environment Check (Read-Only)

Learners use **Google Cloud Console → BigQuery Studio**, or **Cloud Shell** with the `bq`/`gcloud` CLIs. SQL snippets below use the **GoogleSQL** dialect. Select a lab project with billing/quotas enabled and a location matching data policies.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
BQ_LOCATION="US"
DATASET="bqml_lab"

# READ-ONLY.
gcloud auth list
gcloud config list project
gcloud projects describe "$PROJECT_ID"
gcloud services list --enabled --project="$PROJECT_ID"
bq --project_id="$PROJECT_ID" ls
~~~

**Data location:** choose a location that supports BigQuery ML and keep dataset, model, and query jobs aligned. Examples use the **US multi-region** for convenience; do not copy this choice into workloads bound by residency rules in Vietnam or another specific region. Datasets in **EU** cannot be arbitrarily joined with datasets in **US**.

### 2.2. Role-Based IAM

| Principal | Task | Permissions to Check |
|---|---|---|
| Dataset creator | Manage lab dataset | Scoped BigQuery dataset create/admin |
| Model author | Create models/train and tables | BigQuery Data Editor on dataset; `jobs.create` on project |
| Analyst | Read data, evaluate/predict | Dataset/table/model read/`getData` and job creation |
| Scheduled job identity | Write daily scoring table | `jobs.create`, read features/model, write output table |
| Remote connection SA | Call Vertex AI endpoint | Vertex AI User / endpoint role per API |
| Auditor/FinOps | View metadata and Billing | Appropriate read-only access without raw data access |

**Avoid granting project-wide BigQuery Admin/Owner** to users who only run queries. For remote models, besides caller query permissions, the **service account managed by the BigQuery connection** needs permissions on the target AI platform. Creating a model does not automatically grant everyone access to its underlying training data.

### 2.3. Create a Dedicated Dataset (Mutates, May Incur Charges)

~~~bash
# MUTATING: only in an approved lab project.
bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" mk \
  --dataset "$PROJECT_ID:$DATASET"

# READ-ONLY verify dataset location.
bq --project_id="$PROJECT_ID" show "$PROJECT_ID:$DATASET"
~~~

If the dataset already exists, **do not recreate it** or alter permissions/retention on shared datasets. Subsequent SQL assumes you **replaced every `PROJECT_ID`** with your real project ID. Keep the backticks around fully qualified table/model names per BigQuery syntax.

### 2.4. Cost Considerations Before Training

- **`CREATE MODEL`** incurs training charges depending on model type, edition, and billing model.
- **SQL scans, `ML.PREDICT`, `ML.EVALUATE`**, table creation, and storing outputs consume BigQuery resources; some features carry distinct pricing.
- **Remote models** additionally incur AI service request/token/endpoint charges plus retries/batch overhead.
- Start with **3,000 synthetic rows**—never train on production customer tables.
- Use **Query dry run** where supported, **maximum bytes billed**, query plans, and Cloud Billing budget alerts; **dry runs do not guarantee exact estimates for training or remote AI fees**.
- Per current documentation, **BigQuery ML is not available in BigQuery Standard edition**. Verify edition/reservation entitlements and pricing before committing to an approach.

## 3. Selecting Data and Avoiding Future Leakage

**Illustrative problem:** as of a snapshot date, predict whether a customer will churn within the **next 30 days**. In reality, **the label is only known 30 days later**; all features must be aggregated strictly from data available before the snapshot.

| Feature | Type | Example | Risk to Avoid |
|---|---|---|---|
| `monthly_spend` | INT64 | 79 | Must be captured prior to snapshot |
| `tenure_months` | INT64 | 18 | Do not use tenure updated after churn |
| `tickets_90d` | INT64 | 4 | Count only tickets created before snapshot |
| `days_since_login` | INT64 | 12 | Never leak login timestamps occurring after snapshot |
| `plan` | STRING | basic | Categorical feature |
| `churned_next_30d` | STRING: yes/no | yes | **Label**, not a feature |
| `customer_id` | INT64 | 1001 | Join key, **exclude from model features** |

The demo dataset synthesizes labels using a formula correlated with features, so results illustrate workflow only. They **do not represent** the difficulty, class balance, fairness, or performance of real-world churn data.

### 3.1. Data Leakage and Split Strategies

- **Leakage:** including events known only after the snapshot in features, or computing aggregates across the test period.
- **Random split:** works for independent observations, yet can leak across time or repeated customer records.
- **Entity split:** the same customer must not appear in both train and test if production predicts unseen customers.
- **Time split:** for production forecasting/churn, train on older snapshots and validate/test on newer snapshots, respecting the **label maturity gap**.
- **Holdout:** a dataset untouched during feature, hyperparameter, and threshold tuning; used strictly for final evaluation.

**Lab:** with one row per customer, we split **80% development** (60% train, 20% validation) and **20% holdout** by `customer_id`. Modulo splitting is deterministic for this lab, **not** a recommendation for real time-series data.

## 4. Lab A — Generate Synthetic Churn Data with SQL

In **BigQuery Studio**, select the right **PROJECT_ID** and location **US** per the example, and run the **GoogleSQL** below. Each learner creates tables only inside their own lab dataset.

### 4.1. Generate 3,000 Customer Rows

~~~sql
-- MUTATING: writes/overwrites LAB TABLE; never use production table names.
CREATE OR REPLACE TABLE `PROJECT_ID.bqml_lab.churn_features`
OPTIONS (
  expiration_timestamp = TIMESTAMP_ADD(
      CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
) AS
WITH base AS (
  SELECT
    customer_id,
    30 + MOD(customer_id * 37, 160) AS monthly_spend,
    1 + MOD(customer_id * 17, 48) AS tenure_months,
    MOD(customer_id * 13, 6) AS tickets_90d,
    MOD(customer_id * 7, 45) AS days_since_login,
    ['basic', 'plus', 'team'][OFFSET(MOD(customer_id, 3))] AS plan,
    MOD(customer_id * 19, 29) / 29.0 AS noise
  FROM UNNEST(GENERATE_ARRAY(1, 3000)) AS customer_id
)
SELECT
  customer_id,
  monthly_spend,
  tenure_months,
  tickets_90d,
  days_since_login,
  plan,
  IF(
    0.70 * tickets_90d
    + 0.05 * days_since_login
    - 0.024 * tenure_months
    - 0.014 * monthly_spend
    + 0.90 * noise > 1.80,
    'yes',
    'no'
  ) AS churned_next_30d
FROM base;
~~~

**Why materialize a table instead of running `GENERATE_ARRAY` inline every time?** It fixes a consistent dataset across training/evaluation runs and simplifies leakage checks. The table has a **7-day expiration**, reducing forgotten cleanup; models are separate resources and must be dropped independently if no longer needed.

### 4.2. Verify Size, Labels, and Split Distribution

~~~sql
-- READ-ONLY.
SELECT
  COUNT(*) AS customers,
  COUNT(DISTINCT customer_id) AS unique_customers,
  COUNTIF(churned_next_30d = 'yes') AS positive_labels,
  COUNTIF(churned_next_30d = 'no') AS negative_labels,
  MIN(monthly_spend) AS min_spend,
  MAX(monthly_spend) AS max_spend
FROM `PROJECT_ID.bqml_lab.churn_features`;

-- Distribution across partitions reserved for evaluation and holdout.
SELECT
  CASE
    WHEN MOD(customer_id, 10) < 6 THEN 'TRAIN'
    WHEN MOD(customer_id, 10) < 8 THEN 'VALIDATION'
    ELSE 'HOLDOUT'
  END AS dataset_partition,
  COUNT(*) AS row_count,
  ROUND(AVG(IF(churned_next_30d = 'yes', 1, 0)), 3)
    AS churn_rate
FROM `PROJECT_ID.bqml_lab.churn_features`
GROUP BY 1
ORDER BY 1;
~~~

Expect **3,000 customers** with zero duplicate `customer_id`s, and both label classes represented in every split so the model can train and evaluate cleanly. **Never pre-assume a specific ROC AUC or accuracy value**: run the actual queries to observe results.

### 4.3. Freezing Snapshot Data in Production

In real workloads, replace the synthetic formula with a reproducible pipeline:

~~~text
feature_snapshot_time = 2026-10-01 00:00:00 UTC
features                = strictly data existing prior to snapshot
label_window            = 2026-10-01 through 2026-10-31
label_matured_at        = after the 30-day window closes
entity_key              = customer_id
dataset_partition       = time-based train/validation/holdout
~~~

**Never include columns** such as future `cancellation_date`, post-churn refunds, or post-snapshot support outcomes as features. Labels necessarily reflect future outcomes as **ground truth**, yet must never enter inference inputs.

## 5. Lab B — Training a Logistic Regression Model

### 5.1. `CREATE MODEL` with Custom Split

BQML supports **`CUSTOM`** data splitting. For models without hyperparameter tuning, the split column must be **`BOOL`**: **`FALSE` = train**, **`TRUE`/`NULL` = evaluation**. This differs from hyperparameter-tuned models that use `STRING` labels (`TRAIN`/`EVAL`/`TEST`). We exclude the final 20% entirely as an **external holdout outside `CREATE MODEL`**.

~~~sql
-- MUTATING: creates or overwrites model in the lab dataset.
CREATE OR REPLACE MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['churned_next_30d'],
  data_split_method = 'CUSTOM',
  data_split_col = 'is_eval',
  max_iterations = 30
) AS
SELECT
  monthly_spend,
  tenure_months,
  tickets_90d,
  days_since_login,
  plan,
  churned_next_30d,
  MOD(customer_id, 10) IN (6, 7) AS is_eval
FROM `PROJECT_ID.bqml_lab.churn_features`
WHERE MOD(customer_id, 10) < 8;
~~~

**Breakdown of each clause:**

- **`model_type='LOGISTIC_REG'`**: binary classification for **yes/no** labels.
- **`input_label_cols`**: explicitly identifies the target label instead of relying on a default column named `label`.
- **`data_split_method='CUSTOM'` / `is_eval`**: 6/10 rows train, 2/10 validate.
- **`WHERE MOD(customer_id,10)<8`**: holds out 2/10 rows completely from training as a true **holdout**.
- **`customer_id` is omitted from the input `SELECT`** so it cannot leak as a feature.
- **`plan`** is a `STRING` feature; BQML encodes categorical features automatically per model type.
- **`max_iterations`** caps the maximum iterations; training may converge earlier without using all 30.

**`CREATE OR REPLACE MODEL`** mutates a live model resource and can affect jobs referencing it. In production, **never overwrite a serving `v1` model**: train `v2` under a new name, evaluate, switch consumers, and retain `v1` for rollback.

### 5.2. Inspect Model Metadata and Training History

~~~bash
# READ-ONLY model metadata; not BigQuery INFORMATION_SCHEMA.MODELS.
bq --project_id="$PROJECT_ID" show --model \
  "$PROJECT_ID:bqml_lab.churn_logreg_v1"
~~~

~~~sql
-- READ-ONLY iterations/loss/training status.
SELECT *
FROM ML.TRAINING_INFO(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
)
ORDER BY iteration;
~~~

BigQuery does not currently expose model metadata via an **`INFORMATION_SCHEMA.MODELS`** view; use **`bq show --model`**, BigQuery Studio → Model Details, or the BigQuery `models.get` API. **`ML.TRAINING_INFO`** is the dedicated function for inspecting training iterations.

**Never treat training loss as a substitute for out-of-sample evaluation.** Lower training loss can coincide with overfitting; always evaluate on validation/holdout sets and tune features/thresholds against false-positive and false-negative business costs.

## 6. Lab C — Evaluating Quality on Unseen Data

### 6.1. Metrics on Internal Evaluation Split

~~~sql
SELECT *
FROM ML.EVALUATE(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
);
~~~

For binary classification, output includes **precision, recall, accuracy, f1_score, log_loss, roc_auc**. Meaning:

| Metric | Question Answered | Limitation |
|---|---|---|
| Accuracy | Share of correct predictions | Misleading under class imbalance |
| Precision | Of predicted churners, how many truly churned? | Can be inflated with a high threshold |
| Recall | How many actual churners were caught? | Raising recall often raises false positives |
| F1 score | Balance of precision and recall | Does not directly encode business costs |
| ROC AUC | Separability across thresholds | Does not verify probability calibration |
| Log loss | Quality of predicted probabilities | Penalizes overconfident wrong predictions |

### 6.2. Evaluating Separately on the Holdout Set

**Important:** when passing a custom query to `ML.EVALUATE` and `ML.CONFUSION_MATRIX`, the input must include **features and the true label**. This is the **20% excluded from `CREATE MODEL`**, providing a cleaner out-of-sample check than training metrics alone.

~~~sql
SELECT *
FROM ML.EVALUATE(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan,
      churned_next_30d
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  )
);
~~~

Metrics on synthetic data **must never be reported as production performance**. A model scoring high ROC AUC on synthetic rules can still fail in production due to feature drift, seasonality, label noise, and class imbalance.

### 6.3. Confusion Matrix and Thresholds

~~~sql
-- Predict labels at threshold 0.35 to examine trade-offs.
SELECT *
FROM ML.CONFUSION_MATRIX(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan,
      churned_next_30d
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  ),
  STRUCT(0.35 AS threshold)
);
~~~

A threshold below **0.5** predicts positive more often (catching more churners while increasing false positives). **Never pick thresholds by intuition**: choose them on a validation set using business cost ratios, then **report the holdout once at the end**. Repeatedly adjusting the threshold after viewing holdout results turns the holdout into a tuning set and compromises independence.

### 6.4. Metrics Across Multiple Thresholds

~~~sql
SELECT
  threshold,
  recall,
  true_positives,
  false_positives,
  true_negatives,
  false_negatives
FROM ML.ROC_CURVE(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      monthly_spend, tenure_months, tickets_90d,
      days_since_login, plan, churned_next_30d
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  ),
  GENERATE_ARRAY(0.20, 0.80, 0.10)
)
ORDER BY threshold;
~~~

This query is for **learning how thresholds behave**, not for production tuning on a holdout set. In production, use a separate **validation/threshold-selection split** and freeze the threshold before scoring holdout.

## 7. Lab D — Near-Data Batch Prediction

### 7.1. `ML.PREDICT` on the Holdout Set

**Do not pass `churned_next_30d` into prediction inputs**; labels exist only for post-hoc evaluation once real outcomes mature. Scoring inputs need the features the model trained on. **`customer_id`** is a pass-through identifier column for joining predictions back to applications, not a feature used in `CREATE MODEL`.

~~~sql
SELECT
  customer_id,
  predicted_churned_next_30d,
  predicted_churned_next_30d_probs
FROM ML.PREDICT(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      customer_id,
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
  )
)
LIMIT 10;
~~~

**`ML.PREDICT`** appends two columns for binary classification:

- **`predicted_churned_next_30d`:** chosen label, e.g., **`yes`** or **`no`**.
- **`predicted_churned_next_30d_probs`:** array of structs pairing each **label** with its **probability**. Never assume the first array element is always the positive class.

### 7.2. Extracting the `"yes"` Class Probability Explicitly

~~~sql
WITH scored AS (
  SELECT
    customer_id,
    predicted_churned_next_30d,
    predicted_churned_next_30d_probs
  FROM ML.PREDICT(
    MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
    (
      SELECT
        customer_id,
        monthly_spend,
        tenure_months,
        tickets_90d,
        days_since_login,
        plan
      FROM `PROJECT_ID.bqml_lab.churn_features`
      WHERE MOD(customer_id, 10) >= 8
    )
  )
)
SELECT
  customer_id,
  predicted_churned_next_30d,
  (SELECT probability
   FROM UNNEST(predicted_churned_next_30d_probs)
   WHERE label = 'yes') AS churn_probability
FROM scored
ORDER BY churn_probability DESC
LIMIT 20;
~~~

**`churn_probability`** lies in [0,1] as output by the classifier and is **not automatically calibrated**. For high-stakes actions like suspending accounts or issuing monetary incentives, evaluate calibration, bias, and human/policy approval.

### 7.3. Writing Scoring Outputs to a BigQuery Table

A batch job can materialize predictions so apps, backends, or dashboards read scores **without invoking `ML.PREDICT` on every request**:

~~~sql
-- MUTATING: overwrites LAB TABLE only; expires after 7 days.
CREATE OR REPLACE TABLE `PROJECT_ID.bqml_lab.churn_scores_lab`
OPTIONS (
  expiration_timestamp = TIMESTAMP_ADD(
      CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
) AS
WITH scored AS (
  SELECT
    customer_id,
    predicted_churned_next_30d,
    predicted_churned_next_30d_probs
  FROM ML.PREDICT(
    MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
    (
      SELECT
        customer_id, monthly_spend, tenure_months,
        tickets_90d, days_since_login, plan
      FROM `PROJECT_ID.bqml_lab.churn_features`
      WHERE MOD(customer_id, 10) >= 8
    )
  )
)
SELECT
  customer_id,
  predicted_churned_next_30d,
  (SELECT probability
   FROM UNNEST(predicted_churned_next_30d_probs)
   WHERE label = 'yes') AS churn_probability,
  'churn_logreg_v1' AS model_version,
  CURRENT_TIMESTAMP() AS scored_at
FROM scored;
~~~

**In production:** never blindly overwrite historical scores. Teams typically **partition by scoring date**, track stable job IDs, and use keyed **`MERGE`** or append patterns `(model_version, snapshot_date, customer_id)` to support safe reruns, auditing, and rollback. Set **retention/expiration** per real data contracts.

## 8. Model Explainability and Feature Engineering

### 8.1. Explaining Sample Predictions

~~~sql
SELECT
  customer_id,
  predicted_churned_next_30d,
  top_feature_attributions
FROM ML.EXPLAIN_PREDICT(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`,
  (
    SELECT
      customer_id,
      monthly_spend,
      tenure_months,
      tickets_90d,
      days_since_login,
      plan
    FROM `PROJECT_ID.bqml_lab.churn_features`
    WHERE MOD(customer_id, 10) >= 8
    LIMIT 10
  ),
  STRUCT(3 AS top_k_features)
);
~~~

**`top_feature_attributions`** shows each feature's contribution to that prediction under the supported attribution method; it **does not prove causality**. A high-attribution feature does not mean artificially changing that input will retain the customer.

### 8.2. Inspecting Logistic Model Weights

~~~sql
SELECT *
FROM ML.WEIGHTS(
  MODEL `PROJECT_ID.bqml_lab.churn_logreg_v1`
);
~~~

**`ML.WEIGHTS`** displays weights for linear/logistic models and categorical weight info per schema; unstandardized coefficients across features on vastly different scales cannot be ranked purely by magnitude. Standardize features when appropriate or use `ML.EXPLAIN_PREDICT` on representative examples.

**Do not call `ML.FEATURE_IMPORTANCE` on `LOGISTIC_REG`:** that function is for boosted trees and random forests. Switching `model_type` requires reviewing the matching explanation functions, training behavior, costs, and evaluation metrics.

### 8.3. Preprocessing During Training and Prediction

BigQuery ML applies certain **automatic preprocessing** steps by model type (such as encoding categoricals and handling missing values), and supports a **`TRANSFORM` clause** to bundle feature transformations inside the model itself, preventing training-serving skew. Documentation: <https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create>

**Rules:**

1. Define feature logic once and version SQL, migrations, and metadata.
2. Never normalize statistics across holdout/test data before training (leakage).
3. Never let inference queries change the semantic definition of columns like **`monthly_spend`** or **`days_since_login`**.
4. Handle `NULL`s, unseen categories, outliers, and timestamp boundaries deliberately.
5. When using `TRANSFORM`, verify the required input column names for **`ML.PREDICT`** and avoid transforming features twice.
6. Evaluate fairness and drift across permitted customer cohorts; never infer sensitive attributes without explicit requirement and legal basis.

### 8.4. When the Problem Is Not Classification

- **`LINEAR_REG`:** predicts a continuous numeric target; evaluate with MAE/RMSE/R² instead of precision/recall.
- **`KMEANS`:** unsupervised clustering with centroids and distances; no churn confusion matrix.
- **`ARIMA_PLUS`:** time-series forecasting using `ML.FORECAST`; never split randomly across future timestamps.
- **`BOOSTED_TREE_CLASSIFIER`:** captures nonlinear relationships better, though training cost, explainability, and generalization must be compared.
- **`AUTO_CLASS_WEIGHTS`:** helps handle class imbalance in logistic regression; does not replace defining false-positive vs. false-negative costs.

Do not pick algorithms based on accuracy hype. Start with a **simple baseline**, verify SLOs and costs, and only then test more complex models.

## 9. Remote Inference: Connecting BigQuery to Vertex AI / Gemini

A **remote** BQML model is a BigQuery resource pointing to an AI model/service **outside BigQuery**. It does not mean BigQuery downloaded model weights into the data warehouse. BQML sends selected input rows to the authorized endpoint and returns predictions or generated text.

~~~mermaid
sequenceDiagram
    participant Q as BigQuery SQL job
    participant R as BigQuery remote model
    participant C as BigQuery connection SA
    participant V as Vertex AI / Gemini service
    Q->>R: AI.GENERATE_TEXT(model, prompts)
    R->>C: Request auth/delegation
    C->>V: Requests containing prompt data
    V-->>R: Responses / errors / usage
    R-->>Q: Table-valued results
    Note over Q,V: Separate quotas, pricing, and data governance apply
~~~

### 9.1. Prerequisites

- The dataset and BigQuery **Cloud resource connection** must reside in compatible locations per documentation.
- The **connection service account** needs appropriate permissions on Vertex AI/the endpoint (e.g., Vertex AI User per model type).
- The API/service, endpoint, and model version must be supported in the chosen location.
- Data leaves BigQuery to the AI endpoint; **never send PII, secrets, or raw customer messages** without policy and legal approval.
- Workloads incur **BigQuery query charges + remote model token/endpoint charges + retry/capacity costs**.
- For newer generative models, Google recommends **`AI.GENERATE_TEXT`** over `ML.GENERATE_TEXT` in new queries because of cleaner output column names.

### 9.2. Create a Remote Model — Optional, Approved Lab Project Only

This is a **sample template**—do not run verbatim. First, an admin must create the proper Cloud resource connection, grant IAM to the connection service account, and confirm model endpoint availability. Replace **`PROJECT_ID`, `us`, `bqml_ai_connection`, and `MODEL_ID_DUOC_HO_TRO`** with authorized values.

~~~sql
-- MUTATING: creates a remote model bound to a billable AI endpoint.
CREATE OR REPLACE MODEL `PROJECT_ID.bqml_lab.text_remote_lab`
REMOTE WITH CONNECTION `PROJECT_ID.us.bqml_ai_connection`
OPTIONS (
  ENDPOINT = 'MODEL_ID_DUOC_HO_TRO'
);
~~~

Check supported endpoints/models in [remote models over LLMs](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-remote-model). **Never pick a model ID solely because it appeared in an older article**; supported versions and locations change over time.

### 9.3. `AI.GENERATE_TEXT` on Sample Prompts

~~~sql
-- May issue billable requests to the AI service.
-- Point MODEL to a successfully created remote model above.
SELECT *
FROM AI.GENERATE_TEXT(
  MODEL `PROJECT_ID.bqml_lab.text_remote_lab`,
  (
    SELECT 101 AS review_id,
      'Summarize in one sentence: The product was delivered on time and well packaged.'
        AS prompt
    UNION ALL
    SELECT 102 AS review_id,
      'Summarize in one sentence: Support system response was slow.'
        AS prompt
  ),
  STRUCT(128 AS max_output_tokens, 0.2 AS temperature)
);
~~~

**Never treat LLM output as verified fact.** Inspect output columns and per-row status/error fields per the function version's schema, and handle empty responses, safety blocks, rate limits, and retries. Over millions of rows, **filter, `LIMIT`, and materialize a small prompt subset table first** to avoid accidentally firing millions of billable requests.

### 9.4. How Remote Models Differ from Native BQML

| Dimension | Local BigQuery ML | Remote Model via Connection |
|---|---|---|
| Model weights/compute | Managed by BigQuery ML per model type | External AI endpoint outside BigQuery |
| Input | BigQuery table/query | BigQuery query → remote service |
| Auth | BigQuery roles for model/data/jobs | Plus connection SA + AI endpoint IAM |
| Location | BigQuery model/dataset | Plus endpoint/residency/location support |
| Billing | BigQuery ML/model/query/storage | BigQuery + external endpoint/token/compute fees |
| Output | Predicted labels/numbers/metrics | Output schema of remote model / AI function |
| SLO | Warehouse/query performance | Also depends on remote endpoint quota and latency |
| Privacy | Governed by BigQuery access controls | Must evaluate data sent to the AI service |

## 10. Operationalizing BQML in Governed Recurring Pipelines

A newly trained model does not automatically become a production feature. Separate the **training pipeline** from the **scoring pipeline** and version them like software artifacts.

~~~mermaid
flowchart TD
    A["Validated event sources"] --> F["Feature snapshots\ndaily partitioned"]
    F --> T["Periodic training job\nmodel vN"]
    T --> E["Evaluation + approval gate"]
    E -->|"PASS"| M["Model registry / approved version"]
    M --> S["Scheduled scoring job"]
    F --> S
    S --> O["Partitioned predictions table"]
    O --> D["Dashboard / downstream activation"]
    O --> MON["Monitoring: data drift + label metrics"]
    MON -. "Retrain trigger" .-> T
    E -->|"FAIL"| HOLD["Keep serving model"]
~~~

### 10.1. Separating Three Datasets

| Dataset / Artifact | Purpose | Rule |
|---|---|---|
| **Feature snapshot** | Customer state at an eligible cutoff time | Never mutate frozen snapshots if reproducibility matters |
| **Training/evaluation** | Train and select model and threshold | Keep holdout untouched during tuning cycles |
| **Scoring snapshot** | Current customer features | Exclude future labels; match training schema |
| **Ground truth after 30 days** | Measure real-world accuracy | Join on `customer_id` + `snapshot_date`, handle late labels |
| **Prediction table** | Output for BI and apps | Stamp `model_version`, scoring time, feature snapshot ID |

### 10.2. Model Release Workflow

1. **Data quality gate:** row counts, null rates, label maturity, out-of-range checks, PII checks.
2. **Train:** create **`churn_logreg_v2`** without overwriting **`v1`** used by downstream jobs.
3. **Evaluate:** compare ROC AUC/precision/recall on validation, calibration, and business action cost.
4. **Holdout:** run once after locking features and threshold; record results.
5. **Approve:** sign-off from model owner, data owner, SQL revision, schema version, and reviewer.
6. **Canary:** run v2 on a small batch slice and reconcile scores and downstream behavior.
7. **Promote:** point scheduled scoring query to v2; keep v1 and historical outputs for rollback.
8. **Observe:** monitor input drift, prediction distributions, errors, query runtime, and costs.
9. **Rollback:** revert the scoring job's model reference to v1; never delete published data without a reconciliation plan.

Orchestrate with **BigQuery scheduled queries**, **Dataform**, **Cloud Composer/Workflows**, or a CI/CD pipeline based on complexity. Store SQL in Git—never manage production by manually editing console queries with no change history.

### 10.3. Using Scheduled Queries Safely

When creating a daily scoring scheduled query:

- Assign a **dedicated service account** with read permissions on features/model and write permissions on the destination table.
- Match **location** to the dataset/model, and schedule it after feature snapshot jobs finish.
- Pass an explicit **partition/snapshot date** rather than scattering `CURRENT_DATE()` across multiple steps.
- Record **`model_version`, `run_id`, `feature_snapshot_date`, and `scored_at`** for traceability.
- Prevent duplicate rows on reruns with keyed **`MERGE`** or approved write dispositions.
- Alert on **failed jobs, anomalous row counts, rising NULLs, latency, and cost spikes**.
- **Never schedule a job that runs `CREATE OR REPLACE MODEL v1`** while v1 serves active consumers.

### 10.4. Batch or Online Inference?

| Requirement | Implementation Pattern |
|---|---|
| Score 1 million customers nightly | Scheduled BigQuery `ML.PREDICT` into a partitioned table |
| Daily churn dashboard | BigQuery table → Looker/BI |
| API reads precomputed scores | Cloud Run service reads serving table/store per SLO |
| Real-time inference on button click | Dedicated serving endpoint / Vertex AI, caching, and load testing |
| 30-day forecast using fresh streaming events | Evaluate feature freshness, microbatching, online feature stores, and SLAs |

**Do not query BigQuery synchronously inside every user HTTP request** unless you have measured latency, quotas, and costs and explicitly accepted those trade-offs.

## 11. Post-Deployment Model Monitoring

### 11.1. What Should a Monitoring Dashboard Include?

| Category | Metrics | Why It Matters |
|---|---|---|
| **Data quality** | row count, missing/null ratios, schema changes | Broken inputs produce meaningless scores |
| **Feature drift** | distributions of spend, tickets, plan, `days_since_login` | Model may no longer fit shifting customer cohorts |
| **Prediction drift** | `% predicted yes`, score histogram | Detects abnormal output shifts |
| **Ground-truth quality** | label availability, late-arriving labels | Cannot evaluate accuracy until labels mature |
| **Model accuracy** | precision, recall, ROC AUC by cohort/time | Confirms out-of-sample stability |
| **Fairness/impact** | metrics across permitted evaluation cohorts | Prevents unmonitored disparate impact |
| **Query reliability** | failed jobs, duration, bytes scanned, slot usage | Ensures batch jobs finish within SLA |
| **Remote inference** | output status, rate limits, token usage, latency | Prevents silent failures and runaway AI bills |
| **Cost** | BigQuery ML training/inference, storage, Vertex AI | Budget tracking and optimization |

### 11.2. Drift Is Not Just Accuracy

**Feature drift** happens when input distributions shift (e.g., new signups heavily favor the `team` plan), whereas **concept drift** occurs when the relationship between features and churn shifts (e.g., a promotion alters cancellation behavior). A pipeline can succeed 100% technically while making poor predictions due to drift.

Because **`churned_next_30d`** takes 30 days to mature, you cannot compute "real-time accuracy" immediately after scoring. While waiting for labels, monitor drift, invalid rows, prediction distributions, and user feedback; evaluate model quality once labels mature.

### 11.3. Inspecting Executed Jobs and Resource Usage

~~~sql
-- READ-ONLY BigQuery job metadata; requires appropriate INFORMATION_SCHEMA permissions.
-- Dataset/model reside in US multi-region; region qualifier must match.
SELECT
  creation_time,
  job_id,
  user_email,
  statement_type,
  total_bytes_processed,
  total_slot_ms
FROM `PROJECT_ID.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 100;
~~~

**Interpret limits accurately:** **`bytes processed`** and **`slot-ms`** measure execution work, yet **do not map directly to exact bills** across every model type and billing mode. Reconcile against **Cloud Billing** / pricing SKUs and reservations; remote model fees also appear under the external AI service.

### 11.4. Safety Checks Before Every Retrain

- Snapshot table schema and permissions are intact.
- Labels come from a complete observation window with zero future leakage.
- Train/validation/test splits do not overlap by customer/time improperly.
- Rare cohorts or key business segments are not accidentally dropped.
- Compare against baseline: if the new version does not improve, keep the current serving model.
- Maintain traceable SQL/data/model versions and rollback criteria.
- Plan controls for false positives (wasted incentive budget) and false negatives (missed at-risk customers).

## 12. Security and Data/AI Governance

### 12.1. Four Distinct Authorization Surfaces

~~~mermaid
flowchart LR
    USER["Analyst / job SA"] -->|"BigQuery jobs.create"| JOB["BigQuery query job"]
    JOB -->|"Tables/model read"| BQ["BigQuery features + model"]
    JOB -->|"Connection use"| CONN["BigQuery connection service account"]
    CONN -->|"AI endpoint IAM"| AI["Vertex AI / Gemini"]
    BQ -->|"Output table IAM"| DOWN["Scores for approved consumers"]
~~~

- **BigQuery job permission:** permits creating jobs; does not grant table read access.
- **Dataset/model data permissions:** queries need read access to tables/models; training needs scoped model-creation rights.
- **Connection permission:** remote models require permission to use the connection per policy; the connection service account calls the AI service.
- **Endpoint IAM:** the connection SA needs authorized roles on Vertex AI / remote endpoints; never use personal end-user credentials to mask missing service config.
- **Output privacy:** predictions can constitute sensitive personal/inferred data even when raw inputs lack direct PII. Publish only to consumers with a valid business purpose.

### 12.2. Data Flow and Residency

Running SQL on a **US** BigQuery dataset does not guarantee remote inference executes inside the same dataset or country. For remote models, verify:

1. Locations of the dataset, BigQuery connection, and model endpoint.
2. The AI provider's prompt/input handling policies.
3. Which fields are transmitted (data minimization).
4. Logging and retention policies on both BigQuery and the AI service.
5. CMEK, VPC Service Controls, organization policies, and compatibility if required.
6. Applicable contracts and data protection regulations.

**Never pass access tokens, database passwords, full customer transcripts, or payment cards into prompts** just because `AI.GENERATE_TEXT` makes it convenient.

### 12.3. ML Governance and Human Accountability

Never automatically suspend accounts, deny services, vary pricing, or take sensitive actions solely from an example model's **`churn_probability`**. Models serve as **decision support** and require quality, fairness, risk controls, and appeal paths when deployed in customer-impacting workflows.

## 13. Costs, Quotas, and Optimization Strategies

| Cost Source | Trigger | Control |
|---|---|---|
| BigQuery training | `CREATE MODEL`, hyperparameter tuning | Cap input rows, favor simpler models, schedule retrains |
| BigQuery analysis/inference | `SELECT`, `ML.EVALUATE/PREDICT`, CTAS | Partition pruning, row filtering, select needed columns |
| Storage | Feature/score tables, model storage, snapshots | Enforced expirations and retention policies |
| Remote AI | Model requests, input/output tokens, serving compute | Pre-filter rows, pre-aggregate, quota/token budgets |
| Query orchestration | Scheduled queries, retries | Error alerts, run IDs, prevent duplicate reruns |
| Monitoring | Log/metric retention | Sampling; avoid logging large prompts or PII |
| Data movement | Cross-region queries/transfers/egress per topology | Co-locate datasets, connections, and endpoints |

### 13.1. Estimating AI Request Counts — Not a Price Sheet

Suppose 100,000 feedback rows exist and a remote model fires one request per row. Without filtering, that triggers **100,000 inference requests**, plus extra charges for retries. If you only need 1,000 representative feedback samples, materialize a **1,000-row sample table first**, check coverage, and then invoke the remote model.

For churn scoring, a daily partitioned table avoids scanning years of historical features when scoring only today's snapshot. **A BigQuery dry run does not reveal full training or remote inference charges**; always check [BigQuery pricing](https://cloud.google.com/bigquery/pricing), [BigQuery ML pricing](https://cloud.google.com/bigquery/pricing#bqml), and [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing).

### 13.2. On-Demand and Capacity Pricing

BigQuery supports on-demand or capacity billing depending on the organization. **Slots/editions/reservations** govern ML job execution capacity—they are not a "free inference endpoint." On large datasets or busy scheduled workloads, measure **time-to-result, slot consumption, wall time, and cost per successfully scored row** in a realistic environment.

**Operational warning:** a complex model with marginally higher metrics that costs many times more to train or score may yield negative business ROI. Optimize for total business value, not ROC AUC alone.

## 14. Troubleshooting: Isolating the Failing Layer

| Symptom | Common Cause | Resolution Steps |
|---|---|---|
| **Access Denied** on `SELECT` | Missing dataset/table read permissions | Identify job principal and dataset IAM |
| **Permission denied / `models.create`** | Missing permission to create models in dataset | Grant scoped model/data editor |
| **Location mismatch** | Dataset, model, connection, or job in different regions | Align US/EU/region and query settings |
| **`CREATE MODEL` label error** | Wrong `INPUT_LABEL_COLS` name/type, or single class | Check schema and class distribution |
| **Invalid `CUSTOM` split** | Non-tuned model requires `BOOL` split column | Change `is_eval` to `BOOL`, not `TRAIN`/`EVAL` `STRING` |
| **Model not found** | Wrong project/dataset/model name or training incomplete | Check `INFORMATION_SCHEMA` / job status and model name |
| **`ML.PREDICT` missing feature** | Inference query lacks column or mismatches type | Compare against training input schema |
| **Skewed predictions despite clean execution** | Leakage, drift, changed feature semantics, bias | Audit data contract, holdout, and drift monitors |
| **Suspiciously high accuracy** | Synthetic labels, trivial class imbalance, or leakage | Audit pre- vs. post-snapshot SQL |
| **Cost spike after retraining** | Wide scans, hyperparameter trials, reruns | Inspect bytes, Billing SKUs, and schedules |
| **Remote model 403** | Connection SA lacks endpoint role or missing connection IAM | Check connection resource + Vertex AI IAM |
| **Remote 429 / `RESOURCE_EXHAUSTED`** | Quota, token, or endpoint capacity limits | Rate limit, reduce batch size, apply backoff |
| **Empty/errored remote rows** | Safety blocks, invalid prompts, transient service errors | Inspect row status fields and retry policy |
| **Remote model region unsupported** | Endpoint does not support the BigQuery dataset location | Pick supported location/model per docs |
| **Scheduled query finds no new data** | Job ran before feature snapshot, or SA lacks permissions | Fix dependency ordering, `run_id`, and logs |

### 14.1. Investigation Sequence

1. Verify project, dataset, **job location**, model name, and GoogleSQL dialect.
2. Separate table-read errors, model permissions, BigQuery job permissions, and **connection SA → AI endpoint IAM**.
3. For schema errors: compare training vs. inference feature names/types; labels are needed only for evaluation.
4. For poor quality: audit train/eval/holdout splits, time leakage, label maturity, and cohort distributions.
5. For high costs: inspect BigQuery Job Information, Billing SKUs, partition pruning, remote token counts, and retry counts.
6. If a new model underperforms the old one: **roll back the scheduled query's model reference** per change log rather than immediately deleting published tables.
7. Never include raw PII, secret-bearing prompts, access tokens, or SQL credentials in support tickets.

### 14.2. Reading Model Details via CLI

~~~bash
# READ-ONLY; substitute real project/dataset/model, never print sensitive data.
bq --project_id="$PROJECT_ID" show \
  --model "$PROJECT_ID:bqml_lab.churn_logreg_v1"

bq --project_id="$PROJECT_ID" ls --models \
  "$PROJECT_ID:bqml_lab"
~~~

If CLI flags differ across SDK versions, check **BigQuery Studio → dataset → Models → Model Details/Training** to inspect resources and permissions. A model resource appearing in the catalog does not mean it is ready for consumers before the training job completes.

## 15. Case Study: Customer Retention Campaign

**Illustrative scenario:** a Java app on Cloud Run writes orders to Cloud SQL, publishes events via Pub/Sub, and aggregates analytics in BigQuery. The product team wants to score churn risk and send retention offers through a marketing platform to opted-in users.

### 15.1. Design

~~~mermaid
flowchart LR
    APP["Cloud Run / Java"] --> EVT["Pub/Sub / ingest"]
    EVT --> WH["BigQuery feature snapshots"]
    WH --> BQML["BQML churn v1/v2"]
    BQML --> SCORES["Daily scores table"]
    SCORES --> RULES["Business eligibility + consent rules"]
    RULES --> ACT["Approved campaign system"]
    SCORES --> QA["Quality/drift dashboard"]
    QA -. "Retrain review" .-> BQML
~~~

**Policy choices:**

- Features use only pre-snapshot data; labels mature over a full **30-day** window.
- Training and threshold selection use train/validation only, keeping holdout unseen.
- Model v2 must beat baseline on business metrics, not accuracy alone.
- Scores are written **by date + model version**, with TTL/retention and scoped consumer IAM.
- Campaigns consume scores only after checking **consent, contact frequency caps, and marketing policies**.
- Scores are never turned into adverse automated actions or sensitive inferences beyond approved scope.

### 15.2. Incident and Analysis

One day, training ROC AUC remains high, yet campaign response rates drop sharply. The team wants to retrain hourly immediately.

**Proper diagnosis:** check whether a new marketing campaign shifted baseline churn rates, whether feature snapshots were incomplete, whether labels had matured 30 days, how score distributions drifted, and whether the messaging system changed routing. **Frequent retraining** will not fix label leakage or a shifted business definition.

### 15.3. Acceptance Criteria

| Requirement | Evidence |
|---|---|
| Reproducible training | Versioned SQL, model, and data snapshots |
| Independent holdout | Audited split logic and label maturity window |
| Responsible model use | Precision/recall, calibration, and impact review |
| Least-privilege IAM | Query job SA and dataset/model/connection IAM |
| Operational observability | Job success, drift metrics, and score distributions |
| No unintended remote calls | Explicit model type and service billing tracking |
| Rollback readiness | v1 retained and scheduled job change record documented |
| Controlled costs | Cloud Billing reports reconciled by SKU |

## 16. Hands-On Exercises and Answers

### 16.1. Exercise A — Train, Evaluate, and Predict

In an authorized lab project:

1. Create a dedicated dataset and run the SQL generating 3,000 rows.
2. Verify both label classes exist and splits match train/validation/holdout.
3. Train **`churn_logreg_v1`** with a **CUSTOM BOOL split**.
4. Run **`ML.EVALUATE`** on holdout and record all 6 metrics.
5. Run **`ML.PREDICT`** and select the **top 20 customers with highest `yes` probability**.
6. Persist scores to a table with `model_version` and `scored_at`.
7. Never alter labels or data formulas after reporting results without versioning the table.

**Pass criteria:** model trains cleanly; holdout was excluded from `CREATE MODEL`; predictions include labels and probabilities without leaking `customer_id` into features.

### 16.2. Exercise B — Data Leakage

A team adds **`cancellation_date`** and **`last_login_at_after_snapshot`** to the training query, and ROC AUC jumps dramatically.

**Question:** should they ship it right away?

**Answer:** no. This is **future leakage**: at prediction time, those values do not exist yet. Remove post-snapshot columns, build an as-of feature snapshot, align splits to deployment reality, and re-evaluate.

### 16.3. Exercise C — Precision and Recall

Suppose the holdout has 100 actual churners. The model flags 80 customers, 60 of whom actually churn.

\[
\text{Precision} = 60/80 = 0.75;\qquad
\text{Recall} = 60/100 = 0.60.
\]

**If retention offers are expensive**, which threshold direction should you test? **Guided answer:** evaluate a higher threshold on the **validation set** to boost precision if the business accepts lower recall; there is no universal optimal threshold, and never tune on the final holdout.

### 16.4. Exercise D — Local vs. Remote Inference

One analyst trains a BQML logistic regression model and runs **`ML.PREDICT`**; another creates a remote Gemini model and calls **`AI.GENERATE_TEXT`**.

**Answer:** (1) Where do code/models execute, (2) what extra IAM identity is needed, (3) which services bill, and (4) what data leaves BigQuery?

**Answer:** logistic regression is managed inside BigQuery ML; the remote LLM calls an external AI endpoint via the BigQuery connection SA, adding AI endpoint/quota/token charges and sending prompt inputs to the AI service. Never treat both as identical compute just because both use SQL.

### 16.5. Exercise E — Designing a Production Pipeline

Propose a **nightly** scoring job for 5 million customers. What ensures rerunning the scheduled job twice does not corrupt outputs?

**Answer:** dated feature snapshots, a dedicated scheduled job service account, date-partitioned outputs, **`model_version`/`run_id`**, idempotent `MERGE` or write disposition, job monitoring, quotas/budgets, and a rollback plan. Never overwrite a single unversioned scores table.

### 16.6. Exercise F — Remote AI Costs

100,000 product reviews need summaries; each row triggers a remote request. An analyst tests a query over the full table while intending to inspect only **100 samples**.

**Answer:** filter and materialize a 100-row sample table **before calling `AI.GENERATE_TEXT`**, budget tokens/requests, and inspect output/status columns—never rely on an outer `LIMIT` outside the function assuming it caps remote calls at 100.

### 16.7. Sample Lab Report

~~~text
PROJECT_ID / LOCATION / DATASET:
DATA_SOURCE / SNAPSHOT_TIME:
ROW_COUNT / CLASS_DISTRIBUTION:
TRAIN_SPLIT / EVAL_SPLIT / HOLDOUT_SPLIT:
FEATURE_SCHEMA / LABEL_DEFINITION:
MODEL_NAME / MODEL_TYPE / TRAINING_JOB_ID:
EVAL_ACCURACY / PRECISION / RECALL / F1 / ROC_AUC / LOG_LOSS:
THRESHOLD_SELECTION_POLICY:
PREDICT_OUTPUT / SCORE_TABLE / MODEL_VERSION:
EXPLAIN_PREDICT_NOTES:
REMOTE_MODEL_USED? / CONNECTION_SA / AI_ENDPOINT:
IAM_REVIEW / DATA_RESIDENCY_REVIEW:
QUERY_BYTES / REMOTE_TOKEN_COST / BILLING_CHECK:
CLEANUP / OPEN_ISSUES:
~~~

Mark **PASS** only if actually executed and verified. If no authorized BigQuery project is available, mark **NOT_EXECUTED** rather than claiming training or inference succeeded.

## 17. Lab Cleanup and References

### 17.1. Controlled Cleanup

**Delete only the dataset and resources you created, after confirming no consumers or scheduled jobs reference them.** The SQL below **permanently deletes objects**:

~~~sql
-- MUTATING/DESTRUCTIVE: lab project only, after owner approval.
DROP TABLE IF EXISTS `PROJECT_ID.bqml_lab.churn_scores_lab`;
DROP MODEL IF EXISTS `PROJECT_ID.bqml_lab.churn_logreg_v1`;
DROP TABLE IF EXISTS `PROJECT_ID.bqml_lab.churn_features`;

-- Only if a remote model was created and is no longer used:
-- DROP MODEL IF EXISTS `PROJECT_ID.bqml_lab.text_remote_lab`;
~~~

Never drop an entire shared dataset. If you created a dedicated **Cloud resource connection** for the remote lab, inventory any other models/tasks using it before deleting; the connection SA's IAM and endpoints have separate lifecycles. Dropping a BQML model **does not erase data previously sent to endpoints, logs, or billing records**.

### 17.2. Official Sources

- [BigQuery ML introduction](https://docs.cloud.google.com/bigquery/docs/bqml-introduction)
- [Model creation with BigQuery ML](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create)
- [CREATE MODEL for logistic/linear regression](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-glm)
- [ML.EVALUATE](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-evaluate)
- [ML.PREDICT](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-predict)
- [ML.CONFUSION_MATRIX](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-confusion)
- [ML.ROC_CURVE](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-roc)
- [ML.EXPLAIN_PREDICT](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-explain-predict)
- [ML.WEIGHTS](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-weights)
- [Remote models over LLMs](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-remote-model)
- [AI.GENERATE_TEXT](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-ai-generate-text)
- [BigQuery scheduled queries](https://docs.cloud.google.com/bigquery/docs/scheduling-queries)
- [BigQuery INFORMATION_SCHEMA jobs metadata](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)
- [BigQuery security overview](https://docs.cloud.google.com/bigquery/docs/security-overview)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)

**Final checklist:** define labels and snapshots → audit for leakage → split train/eval/holdout → `CREATE MODEL` → `ML.EVALUATE` → select threshold on validation → `ML.PREDICT` → explainability/model governance → versioned scoring tables → monitor drift and costs → review remote AI IAM/residency if used → clean up under clear ownership.

**Connection to the CLOUD_PROVIDERS_GCP track:** BigQuery ML brings machine learning **directly into SQL analytics workflows**, integrating data from Cloud Run/GKE/Compute Engine and storage services. Results remain valuable only when **features are point-in-time accurate, evaluation is out-of-sample, IAM is tightly scoped, endpoints/costs are governed, and business decisions are monitored**.

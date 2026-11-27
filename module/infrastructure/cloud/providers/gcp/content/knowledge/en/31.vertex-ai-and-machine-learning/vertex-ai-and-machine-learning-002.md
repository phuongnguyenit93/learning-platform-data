# Managing Datasets and Preparing Training Data on Vertex AI

A retail business operates an order API on **Cloud Run**, processes data with **Dataflow**, stores history in **Cloud Storage/BigQuery**, and wants to train a model to predict **whether an order is likely to request a return within 30 days after successful delivery**. Having data does not mean a **training set** is ready: labels may be missing, records duplicated, customer IDs exposing PII, or features containing information that only appears *after prediction time*. In such cases, a model can achieve high test scores yet fail in production.

This lesson belongs to the **Vertex AI and Machine Learning** chapter, module **CLOUD_PROVIDERS_GCP**. The focus is on choosing where to store data, managing managed datasets, checking data quality, constructing labels, splitting datasets, preventing data leakage, and reproducing training versions. Examples tie into IAM, Cloud Storage, BigQuery, CI/CD, reliability, and cost; in-depth training algorithms are not yet covered here.

**2026 Product Naming:** Google Cloud renamed **Vertex AI Platform** to **Gemini Enterprise Agent Platform** (Agent Platform). In current documentation/APIs, datasets/training features may appear under Agent Platform, while the Python SDK `google-cloud-aiplatform`, `aiplatform.googleapis.com`, and many resource names retain the old prefix. This lesson uses "Vertex AI/Agent Platform" for compatibility with the syllabus and current guides. See the [official rename table](https://docs.cloud.google.com/gemini-enterprise-agent-platform/vertex-ai-name-changes).

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish **raw data**, **curated training table**, **managed Dataset resource**, **data snapshot**, and **model artifact**.
2. Choose **BigQuery**, **Cloud Storage**, or a managed dataset depending on **AutoML** versus **custom training**.
3. Design a label/feature contract at **prediction time**, and detect target leakage, temporal leakage, entity leakage, and training-serving skew.
4. Standardize numeric, categorical, text, and image data; check missing values, duplicates, label noise, imbalance, and data usage permissions.
5. Split **train/validation/test** randomly, chronologically, or by entity group, and keep the test set out of tuning.
6. Use BigQuery SQL to prepare tables, Python SDK to link a managed tabular dataset to a BigQuery source, and CLI to verify sources.
7. Record versions, lineage, access permissions, data regions, SLOs, and costs to reproduce experiments.

## 2. Where Do Datasets Fit in the ML Lifecycle?

~~~mermaid
flowchart LR
    SRC["Cloud SQL / Spanner / Pub/Sub / GCS"] --> RAW["Raw events + source snapshots"]
    RAW --> CLEAN["BigQuery/Dataflow: validate, join, dedupe"]
    CLEAN --> CUR["Curated feature-label dataset"]
    CUR --> SPLIT["Train / validation / test"]
    SPLIT --> MAN["Managed Dataset (when needed)"]
    SPLIT --> CUSTOM["Custom training reads BQ/GCS directly"]
    MAN --> TRAIN["AutoML or suitable training"]
    CUSTOM --> TRAIN
    TRAIN --> REG["Model Registry + evaluation"]
    META["Metadata/version/lineage + IAM"] -.-> CUR
    META -.-> MAN
    META -.-> TRAIN
~~~

| Component | What Does It Contain? | Is It a "Dataset Resource" on Agent Platform? |
| --- | --- | --- |
| **Transactional source** | Orders, payments, delivery timestamps, returns. | No; data lives in source systems. |
| **Raw layer** | Original events plus ingest timestamps, IDs, schema versions. | No; typically resides in GCS/BigQuery. |
| **Curated table** | One row per example, verified features and labels. | No; this is the **actual table** for training. |
| **Managed Dataset** | Resource describing the dataset, objective, and import/link source. | **Yes**, used in AutoML and where appropriate. |
| **Training snapshot** | Input set frozen for a run. | Can be a snapshot taken at training start or a separately pinned artifact. |
| **Model artifact** | Weights, metrics, and metadata from a run. | Not a dataset; managed by Model Registry/artifact store. |

**Do not equate "creating a dataset" with "copying and freezing data."** For a **tabular managed dataset**, Agent Platform **links** a BigQuery table/view or GCS CSV; when the source changes, *later* training runs may use the new data. The service creates a snapshot for training **when the run starts**, not immutably by default from when the dataset resource was created. For **image datasets**, data/annotations are imported and managed differently. To reproduce a run months later, manage **pinned sources** (BigQuery table snapshot/version, GCS object generation, or immutable paths), code, cutoff timestamps, and split configurations. [Source: create tabular dataset](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/create-dataset).

## 3. Choosing Dataset Source and Type

### 3.1. Tabular, Image, Text, and Video Have Different Workflows

| Problem | Data Format | Suitable Source and Management |
| --- | --- | --- |
| Return prediction | Tabular: one row/order, label 0/1 | BigQuery table/view or GCS CSV, managed tabular dataset for AutoML. |
| SKU demand forecasting | Time series: SKU×day, target and covariates | BigQuery/CSV; check frequency, historical windows, and forecasting constraints. |
| Product image classification | Images + category labels | GCS objects and CSV/JSONL manifest per objective's **import schema**. |
| Defect detection in images | Images + bounding boxes | GCS, labels, and annotation manifest matching detection schema. |
| Customer feedback classification | Text + label/class | Text dataset/manifest or custom training pipeline. |
| Custom model training | Tensors/chunks/features per framework | Custom training reading BigQuery, GCS, TFRecord/Parquet/...; managed Dataset is **not required**. |

**AutoML** generally requires a managed dataset for supported objectives; **custom training** can use a managed dataset or read sources directly in code. You do not have to import everything into a managed dataset if the training container already has a versioned data pipeline. Availability of an objective, import format, region, and SDK may change; check [managed datasets overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/datasets/overview).

### 3.2. BigQuery or Cloud Storage?

| Criterion | BigQuery | Cloud Storage |
| --- | --- | --- |
| Querying, joining, cleaning tabular data | Very suitable with GoogleSQL, partitions, quality SQL. | Suitable for CSV, Parquet, TFRecord files; needs an engine to read/transform. |
| Versioning | Snapshot tables, per-run materialized tables, query control. | Object generations or immutable prefixes + manifests/checksums. |
| Schema | Table schema, constraints verified via queries. | Depends on individual file format/schema. |
| Unstructured data | Can store references/metadata. | Typically stores image/video/text files and annotations. |
| Primary costs | Storage + query/slot processing. | Storage + operations/egress + compute during processing. |
| Governance | BigQuery IAM, row/column policies, authorized views. | Bucket/object IAM, VPC SC, encryption/retention. |

For personal/sensitive data, consider **reducing input fields**, limiting raw PII exports, and separating permissions for data prep, training, analysts, and service agents; keep data regions compliant with policy.

## 4. Defining Labels and Features at Prediction Time

### 4.1. Example Model: Return Request Within 30 Days

Suppose predictions are made **immediately when an order is successfully delivered**. Therefore:

- **Unit of example (grain):** one row per successfully delivered `order_id`.
- **Prediction time:** `delivered_at`.
- **Target:** `return_within_30d = 1` if there is a valid return request within `[delivered_at, delivered_at + 30 days]`; otherwise 0 **only after a full 30 days of observation**.
- **Valid features at prediction time:** order total, item count, shipping method, delivery zone, delivery duration, historical info prior to `delivered_at`.
- **Invalid features:** `return_requested_at`, `refund_issued`, post-delivery customer support status, or any statistic looking into the future.

| Field | Role | Use as Feature? |
| --- | --- | --- |
| `order_id` | ID for reconciliation/dedup | Not as a default predictive signal. |
| `delivered_at` | Prediction timestamp and time split | May extract suitable date/hour without leakage. |
| `customer_id` | Grouping/audit if needed | Do not blindly drop PII/high-cardinality IDs into AutoML. |
| `item_count`, `subtotal_vnd` | Features known before/at delivery | Yes, with consistent schema and units. |
| `shipping_method`, `region` | Categorical features | Yes, check unseen/missing categories. |
| `delivery_duration_days` | Feature known at delivery | Yes if inference runs at delivery. |
| `return_requested_at` | Build target for historical data | **Must not** be included as a feature. |
| `return_within_30d` | Label (target) | Target only, never both target and predictor. |
| `split` | TRAIN/VALIDATE/TEST | Split metadata, not a feature. |

**Sanity-check rule:** for every feature, ask *"if the system had to predict right at `delivered_at`, did this value already exist and was it accessible?"* If the answer is uncertain, exclude it or rebuild it using a **point-in-time join**.

### 4.2. Avoiding Immature Labels

If the pipeline runs on `2026-11-01`, an order delivered on `2026-10-25` can still be returned in November. **Do not assign 0 just because no return request has appeared by today**. Pick a fixed `as_of`, include only orders delivered **at least 30 days before the cutoff**, and consider adding a buffer for late-arriving event systems. For cancelled/undelivered orders, clearly define whether they are **out of scope** or a separate label.

### 4.3. Common Forms of Leakage

| Leakage | Example | How to Prevent |
| --- | --- | --- |
| **Target leakage** | Column `refund_status` used as a predictor for returns. | Separate features and target at prediction time. |
| **Temporal leakage** | Using total complaints *up to now* to predict an order delivered last month. | Point-in-time features, join with `event_time <= delivered_at`. |
| **Entity leakage** | Nearly identical person/device in both train and test when targeting new users. | Group split by customer/device if matching the evaluation goal. |
| **Duplicate leakage** | Same order appearing twice with different IDs. | Deduplicate by business key before splitting. |
| **Preprocessing leakage** | Mean/std, vocabulary, imputers fit across all of train+test. | Fit preprocessing **only on TRAIN**, apply to VAL/TEST and inference. |
| **Pipeline label leakage** | Data prep joins refund data and accidentally keeps refund columns in features. | Whitelist feature columns and automate schema checks. |

**Training-serving skew** is the difference between how a feature is computed during training and during inference. For example, using a 90-day spend average in training vs 7 days during serving; model quality can degrade even without direct leakage. Share feature definitions, cutoff logic, and transformations, or write equivalence tests.

## 5. Cleaning and Validating Data Before Ingestion

### 5.1. Minimum Data Contract

| Check | Example | Response |
| --- | --- | --- |
| **Schema/type** | `subtotal_vnd` is `NUMERIC`, `delivered_at` is `TIMESTAMP`, label is 0/1. | Block schema drift or route through an approved normalization step. |
| **Completeness** | `order_id`, delivery time, label non-null; `shipping_method` may be null. | Drop, impute, or add a missing flag depending on the field. |
| **Uniqueness** | One `order_id` must not produce multiple training rows. | Deduplicate using business rules, not blind `DISTINCT`. |
| **Validity** | `item_count > 0`, `subtotal_vnd >= 0`, `created_at <= delivered_at`. | Quarantine invalid values and reconcile with source. |
| **Consistency** | Currency VND, timezone UTC, consistent category codes. | Convert using versioned rules; do not "guess" currencies. |
| **Distribution** | Positive label rate, delivery zones, peak seasons. | Monitor imbalance and sample-selection bias. |
| **Freshness** | Data has matured for full 30 days to assign labels. | Do not treat unobserved labels as 0. |
| **Privacy/consent** | Omit full address, email, identifiers without justification. | Data minimization, masked views, policy reviews. |

Perform **profiling on raw data first**, then store **test results on curated data**, rather than silently dropping all invalid rows without tracking drop rates. Dropping data can introduce bias: for instance, dropping all undelivered orders might leave the training set with only good experiences.

### 5.2. Missing Values, Outliers, and Categorical Features

- **Numeric:** measure null %, value ranges, percentiles, outliers; do not blindly clamp all large orders to the mean. For models requiring imputation, fit median/mean on TRAIN or use AutoML transformations.
- **Categorical:** standardize spellings/codes, separate `UNKNOWN` from real values, handle unseen categories at inference; avoid manual one-hot encoding if AutoML already manages suitable transformations.
- **Time:** distinguish timezones and daylight saving; `DATE` may lose important hours/minutes, so keep original timestamps when needed.
- **Text:** strip secrets, personal info, and sensitive boilerplate; check language, encoding, and labels.
- **Class imbalance:** always measure **positive/negative ratio per split**; accuracy can mislead if only 2% of orders request returns. Use precision/recall, PR-AUC, and confusion matrices weighted by business costs instead of accuracy alone.

In **tabular AutoML**, many categorical/numeric/text transformations are handled by the system; avoid over-preprocessing in ways that lose signal. However, **removing PII, fixing labels, preventing leakage, and preserving the prediction-time contract** remain the data team's responsibility. [Tabular data best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/bp-tabular).

### 5.3. Label Quality for Images and Text

Example of classifying product images into `shoe`, `shirt`, `bag`:

- Decide whether labels are **mutually exclusive** (single-label) or one image can have multiple labels (multi-label).
- Write **annotation guidelines** with boundary cases, blurry photos, multiple objects, and occluded items.
- Sample dual-annotator reviews; measure disagreement and refine guidelines before labeling tens of thousands of images.
- Detect identical/near-duplicate images across train and test to prevent inflated evaluations.
- Check representativeness across devices, lighting, and regions; test data must resemble deployment data.
- For object detection, **bounding boxes** matching the objective format are required; classification labels alone are not enough.

A managed image dataset uses **GCS URIs and CSV/JSONL manifests** per the import schema. Example three-column CSV for **single-label image classification**:

~~~csv
training,gs://REPLACE_BUCKET/images/shoe-001.jpg,shoe
validation,gs://REPLACE_BUCKET/images/shirt-101.jpg,shirt
test,gs://REPLACE_BUCKET/images/bag-090.jpg,bag
~~~

This is an **illustrative format**—these objects do not exist; do not use company/customer photos without authorization. The first column is the split per the objective format, not `customer_id`; verify the image/classification schema and URL data before importing. For JSONL imports, field structure and `annotation_set_name` differ from CSV. [Prepare image classification data](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/image-data/classification/prepare-data).

## 6. Train, Validation, and Test: How to Split Properly?

### 6.1. Purpose of Each Split

| Split | What Is It Used For? | What to Avoid? |
| --- | --- | --- |
| **TRAIN** | Fit model parameters and preprocessing statistics. | Containing future data or test labels. |
| **VALIDATION** | Select features, model/hyperparameters, and thresholds. | Tuning too many times and overfitting to validation. |
| **TEST** | Final evaluation on data not involved in selection. | Using it to pick a model and then claiming the test is independent. |

For tabular AutoML classification/regression, tools default to an **80%/10%/10% random split**, and also allow **manual/timestamp splits**. That is a **service default**, not the optimal ratio for every problem. [Data splits](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/data-splits).

### 6.2. Three Strategies

| Strategy | Suitable For | Watch Out For |
| --- | --- | --- |
| **Random split** | Nearly independent samples and data stable over time. | Leakage across users or time; duplicate images/documents. |
| **Chronological split** | Predicting on the **future**: returns, demand, delivery. | Preserve label maturity and gap; test contains only timestamps after train. |
| **Group/entity split** | Evaluating on **unseen** customers, devices, patients, or sellers. | Group ID must not appear in both train and test; class distribution may skew. |

**The evaluation goal dictates the split strategy.** If production predicts **new orders from existing returning customers**, a chronological split is fundamental. If deploying to **brand-new customers**, test a group split by customer, or combine with time. For time series and forecasting, train on the past and validate/test on non-overlapping future windows; avoid computing rolling features across invalid boundaries.

### 6.3. A Completely Self-Contained SQL Example

Run in the **BigQuery SQL editor**; `WITH` generates data **only within the query**, without writing tables or using real data. Labels are assumed to have matured sufficiently:

~~~sql
WITH samples AS (
  SELECT 'O-01' AS order_id, DATE '2026-05-01' AS delivered_date,
         120000 AS subtotal_vnd, 0 AS return_within_30d UNION ALL
  SELECT 'O-02', DATE '2026-05-18', 240000, 1 UNION ALL
  SELECT 'O-03', DATE '2026-06-07', 90000, 0 UNION ALL
  SELECT 'O-04', DATE '2026-06-25', 330000, 0 UNION ALL
  SELECT 'O-05', DATE '2026-07-12', 510000, 1 UNION ALL
  SELECT 'O-06', DATE '2026-07-29', 78000, 0 UNION ALL
  SELECT 'O-07', DATE '2026-08-09', 425000, 1 UNION ALL
  SELECT 'O-08', DATE '2026-08-26', 150000, 0
),
split_data AS (
  SELECT *,
    CASE
      WHEN delivered_date < DATE '2026-07-01' THEN 'TRAIN'
      WHEN delivered_date < DATE '2026-08-01' THEN 'VALIDATE'
      ELSE 'TEST'
    END AS data_split
  FROM samples
)
SELECT data_split, COUNT(*) AS rows,
       COUNTIF(return_within_30d = 1) AS positive_labels,
       ROUND(AVG(return_within_30d), 3) AS positive_rate
FROM split_data
GROUP BY data_split
ORDER BY data_split;
~~~

Expected result: **TRAIN 4 rows/1 positive; VALIDATE 2 rows/1 positive; TEST 2 rows/1 positive**. This is an **8-row toy dataset to illustrate logic**, completely insufficient for training a real model; time-based splitting yields differing class rates, requiring representative evaluation on larger datasets. `data_split` must not be passed as a feature.

### 6.4. Preventing the Test Set from Changing Across Runs

- Record the **exact cutoff timestamp**, list of test entity IDs, or an immutable split table.
- A random seed makes a random split reproducible **only when the source and ordering/algorithm are fixed**; it does not replace data versioning.
- Keep duplicate events or records sharing the same entity in the same split when needed to prevent leakage.
- Do not tune on the test set; if test fails and you decide to redesign the model, consider **a fresh evaluation set** if you have "peeked" many times.
- Normalization statistics, target encoding, and feature selection must be fit from TRAIN (or use the system's built-in pipeline transformations).

## 7. Preparing a BigQuery Table for a Managed Tabular Dataset

### 7.1. SQL Pipeline with Cutoff and Feature List

Suppose a **lab dataset already has** two source tables:

- `retail-lab.raw.orders`: `order_id`, `customer_id`, `created_at`, `delivered_at`, `item_count`, `subtotal_vnd`, `shipping_method`, `destination_zone`, `order_state`.
- `retail-lab.raw.return_requests`: `order_id`, `requested_at`, `request_status`.

The goal is one example per *delivered* order, with prediction time at `delivered_at`. The SQL below is a **template that writes a real table**; run only after verifying schema/permissions, getting approval, and ensuring **source data is lab-only**—never copy verbatim to production:

~~~sql
-- WRITE: creates/replaces standardized training table, may incur BigQuery charges.
DECLARE as_of TIMESTAMP DEFAULT TIMESTAMP '2026-11-01 00:00:00+00';

CREATE OR REPLACE TABLE `retail-lab.ml_data.return_training_v1`
PARTITION BY DATE(delivered_at)
CLUSTER BY data_split
AS
WITH first_return AS (
  SELECT order_id,
         MIN(requested_at) AS first_request_at
  FROM `retail-lab.raw.return_requests`
  WHERE request_status = 'VALID'
    AND requested_at <= as_of
  GROUP BY order_id
),
eligible_orders AS (
  SELECT order_id, customer_id, created_at, delivered_at,
         item_count, subtotal_vnd, shipping_method, destination_zone
  FROM `retail-lab.raw.orders`
  WHERE order_state = 'DELIVERED'
    AND delivered_at IS NOT NULL
    AND delivered_at <= TIMESTAMP_SUB(as_of, INTERVAL 35 DAY)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id ORDER BY delivered_at DESC
  ) = 1
)
SELECT
  o.order_id,                  -- audit ID; not used as feature
  o.customer_id,               -- split/group ID; not used as default feature
  o.delivered_at,              -- prediction timestamp
  o.item_count,
  o.subtotal_vnd,
  o.shipping_method,
  o.destination_zone,
  TIMESTAMP_DIFF(o.delivered_at, o.created_at, HOUR)
    AS delivery_duration_hours,
  IF(r.first_request_at BETWEEN o.delivered_at
       AND TIMESTAMP_ADD(o.delivered_at, INTERVAL 30 DAY), 1, 0)
    AS return_within_30d,
  CASE
    WHEN DATE(o.delivered_at) < DATE '2026-07-01' THEN 'TRAIN'
    WHEN DATE(o.delivered_at) < DATE '2026-08-01' THEN 'VALIDATE'
    ELSE 'TEST'
  END AS data_split
FROM eligible_orders AS o
LEFT JOIN first_return AS r USING (order_id)
WHERE o.item_count > 0
  AND o.subtotal_vnd >= 0;
~~~

**Limitations of this example:** it assumes `order_state`, `delivered_at`, valid returns, and delivery events have synced before `as_of`; the **35-day** buffer is a lab convention (30-day label + 5-day ingest lag). If `order_state` can change after delivery, filtering `order_state='DELIVERED'` at current time could **wrongly exclude orders that were delivered and then completed a return**. In production, pull from **immutable historical delivery-success events**, rather than filtering by mutable current state which skews sample selection. Similarly, `MIN(requested_at)` is only accurate if business logic defines the first valid return as the criterion; multiple events/cancellations require separate modeling.

`CREATE OR REPLACE TABLE` can overwrite data, permissions/resource metadata, or downstream dependencies; prefer **creating a newly versioned table** (`return_training_20261101_v1`) or an approved snapshot rather than overwriting a table used by another training job.

### 7.2. Testing Data After Table Creation

~~~sql
-- READ-ONLY: all queries use the created lab table.
SELECT data_split, COUNT(*) AS n,
       COUNTIF(return_within_30d=1) AS positives,
       COUNTIF(item_count IS NULL) AS missing_item_count
FROM `retail-lab.ml_data.return_training_v1`
GROUP BY data_split ORDER BY data_split;

-- READ-ONLY: one row per order.
SELECT COUNT(*) - COUNT(DISTINCT order_id) AS duplicate_order_rows
FROM `retail-lab.ml_data.return_training_v1`;

-- READ-ONLY: identify bad data and check columns with leakage risk.
SELECT COUNTIF(delivery_duration_hours < 0) AS bad_delivery_duration,
       COUNTIF(subtotal_vnd < 0) AS bad_amount,
       COUNTIF(return_within_30d NOT IN (0, 1)) AS bad_label
FROM `retail-lab.ml_data.return_training_v1`;
~~~

For real data, also test for **NULL labels, empty IDs, class ratios by month/zone, outliers, and feature timestamps**, and verify that the feature set does not contain `return_requested_at` or `refund_status`. Even if SQL tests pass, the pipeline still needs source schema verification, PII provenance checks, and point-in-time correctness.

## 8. Creating a Managed Tabular Dataset on Vertex AI/Agent Platform

### 8.1. Console Workflow

1. In Google Cloud console, open **Agent Platform → Datasets → Create**.
2. Choose **Tabular → Regression/Classification**, enter a versioned dataset name, and select a **supported region**.
3. Link the BigQuery table/view `retail-lab.ml_data.return_training_v1` or a CSV from Cloud Storage.
4. Verify that the dataset/source shows the expected row count, schema, and NULL rates; check that the service agent has **read access to the source data**.
5. When starting AutoML training, pick `return_within_30d` as the **target**, select `data_split` as the **predefined/manual split column** (or configure a timestamp split per goal), and **exclude IDs, the split column, and all label-derived fields from the feature list**.
6. Record the model/training job ID, dataset resource ID, BigQuery snapshot identifier, label/version, data extraction timestamp, and evaluation metrics.

**A managed dataset does not automatically identify which features leak**. `return_within_30d` is the label, while `order_id`, `customer_id`, and `data_split` must be treated as metadata or excluded columns when selecting features. Creating a Dataset resource and **training a model** are two distinct operations, and both can create resources/charges.

### 8.2. Python SDK with BigQuery

This is **sample code, not executed in the course repository**. Install an organization-tested version of `google-cloud-aiplatform` and set up **Application Default Credentials (ADC)**. The lab BigQuery table must exist; the source region must satisfy the service's dataset location requirements.

~~~python
from google.cloud import aiplatform

PROJECT = "retail-lab"
REGION = "us-central1"  # Pick an actually supported region, check data location.
SOURCE = "bq://retail-lab.ml_data.return_training_v1"

aiplatform.init(project=PROJECT, location=REGION)

# WRITE: creates a managed Dataset resource linked to the BigQuery table.
# Does not train a model yet, but may incur service/source charges.
dataset = aiplatform.TabularDataset.create(
    display_name="returns-30d-20261101-v1",
    bq_source=SOURCE,
    labels={"env": "lab", "source": "bq", "version": "v1"},
)

print("Dataset resource:", dataset.resource_name)
print("Display name:", dataset.display_name)
~~~

**This is a resource-writing command**; replace project, region, and source with an approved environment. `bq_source` uses the URI **`bq://project.dataset.table`**, not SQL backticks or `gs://`. Creating this dataset **does not lock a static copy of the source**: if upstream alters the table, later runs may see different data. For reproducible workflows, use a **versioned/immutable source table or snapshot** and record that ID in training run metadata. Check [Python `TabularDataset.create`](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.TabularDataset).

### 8.3. Read-Only Source Checks Before Creating Resources

~~~bash
PROJECT_ID="retail-lab"

# READ-ONLY: confirm gcloud identity.
gcloud auth list
gcloud config get-value project

# READ-ONLY: inspect schema and metadata of the source table.
bq show --format=prettyjson \
  "${PROJECT_ID}:ml_data.return_training_v1"

# READ-ONLY: estimate query cost without executing a full scan.
bq query --use_legacy_sql=false --dry_run \
  'SELECT item_count, subtotal_vnd, return_within_30d
   FROM `retail-lab.ml_data.return_training_v1`'
~~~

Permission to run BigQuery queries and permission to create an Agent Platform Dataset are **two separate permission sets**. A successful `bq show` does not prove the Agent Platform service agent can read the table, especially when the source is in **another project**. Verify project/region and IAM before escalating permissions.

## 9. Data Versioning, Lineage, and Experiment Reproducibility

### 9.1. "Dataset v1" Is Just a Name Without Pinning Content

To answer "what data was this model trained on?", record:

| Metadata | Example |
| --- | --- |
| `dataset_version` | `returns-20261101-v1` |
| `source_uri` | `bq://retail-lab.ml_data.return_training_20261101_v1` |
| `as_of` and label horizon | `2026-11-01T00:00:00Z`, 30 days + 5-day buffer |
| `feature_contract_version` | `returns-feature-schema-v3` |
| `split_policy` | Delivered-time chronological cutoffs, train/validate/test |
| `preprocessing_version` | Git commit/container image digest, SQL/Dataflow config |
| `quality_report` | Duplicate count, null %, class balance, and errors |
| `source_snapshot` | BigQuery snapshot/immutable table or GCS generations/checksums |
| `training_run` | Training job ID, run ID, model artifact ID, hyperparameters |
| `owner` and `access_policy` | Data owner/steward, permissions, and retention |

**BigQuery table snapshots** are one way to preserve source data at a point in time; `CREATE SNAPSHOT TABLE` has its own conditions/quotas/retention and costs. For GCS, **object versioning** or write-locked prefixes + manifests/checksums help make files reproducible; do not assume a `gs://bucket/latest.csv` path is immutable.

### 9.2. Why Data Lineage/ML Metadata Matters

~~~mermaid
flowchart LR
    RAW["raw.orders + raw.returns"] --> SQL["BigQuery SQL commit abc123"]
    SQL --> SNAP["training data snapshot v1"]
    SNAP --> DATA["Managed Dataset ref"]
    DATA --> RUN["Training pipeline run #41"]
    RUN --> MODEL["Model Registry: returns-model v5"]
    QA["Data quality report"] -.-> SNAP
    GIT["Code + config + split policy"] -.-> RUN
~~~

**Agent Platform Pipelines** can store metadata of pipeline executions and artifacts via **Vertex ML Metadata**; **Knowledge Catalog** can assist discovery/lineage at the level of assets mapped with FQNs. However, lineage **does not automatically understand** business label rules if the pipeline fails to record metadata. For example, you must record the SQL version/cutoff, not merely "read orders table." [Lineage of pipeline artifacts](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/pipelines/lineage).

### 9.3. Dataset Drift vs Model Drift

- **Data drift:** production feature distributions change compared to training (e.g., delivery zones, higher order values).
- **Label drift:** actual return rate shifts due to seasons or policies.
- **Schema drift:** feature names/types/missing rates change, breaking pipelines.
- **Training-serving skew:** the same feature is computed differently between training and inference.
- **Model quality drift:** precision/recall drops on labels *after sufficient observation time*, not inferred solely from request volume.

Save baseline statistics by **split and time period**, then monitor serving data. Because labels take 30 days to mature, **quality monitoring has natural latency**; use label-free signals (feature drift, null %, inference failures) for early warnings without claiming final accuracy.

## 10. IAM, Security, Data Regions, and Usage Control

### 10.1. Separating Principals by Function

| Identity | Task | Permissions to Consider |
| --- | --- | --- |
| Data engineer SA | Run standardization SQL and create training tables. | BigQuery Job User on job project, Data Viewer on source, Data Editor on target dataset. |
| Agent Platform user/deployer | Create/list managed datasets, run approved training. | `roles/aiplatform.user` or scoped custom role, `iam.serviceAccounts.actAs` when running with a custom SA. |
| **Agent Platform Service Agent** | Access data managed by the service during dataset creation/training. | Default service permissions plus **additional read permissions on cross-project GCS/BQ** when needed. |
| Custom training SA | Read curated data to run training container. | `Storage Object Viewer`/`BigQuery Data Viewer` at exact locations, logging/artifact write as needed. |
| Data steward/auditor | Inspect schema, quality, and data usage permissions. | Minimal Metadata/Viewer/Logging; no default PII access. |

The Agent Platform Service Agent typically takes the form `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com` with the internal role `roles/aiplatform.serviceAgent`. **Do not grant this Service Agent role to users or arbitrary custom SAs**. If a BigQuery table resides in another project, grant appropriate source permissions to the **exact principal required by documentation**, rather than making the entire dataset public. [Agent Platform IAM](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/general/access-control).

### 10.2. Customer Data and Governance

- Practice **data minimization**: extract only features serving the task; avoid emails, phone numbers, exact addresses, and free-text containing PII.
- Use **authorized views**, policy tags, row/column access policies, masking, and separate service accounts per step.
- Verify **VPC Service Controls, Private Google Access/PSC, DNS, and egress** matching your network topology if Dataflow/training jobs access Google APIs from private environments.
- **CMEK, region/location, bucket location, and retention** must align with organizational policy; do not assume the Dataset resource region automatically moves BigQuery/GCS data into the same region.
- ML documentation, annotation reviewers, labels, or metadata **may also contain sensitive data**; log sample IDs instead of raw payloads.
- When using third-party data, verify training rights, retention limits, permitted purposes, and contractual data deletion requirements.

**A successfully trained model does not prove the training data was authorized for use.** Technical permissions and legal/ethical responsibilities are two independent layers to evaluate.

## 11. Data CI/CD, Testing, and Monitoring

### 11.1. Data Preparation Is a Controlled Deployment Step

~~~text
Source update (BigQuery / GCS / Dataflow)
  → schema contract & freshness checks
  → point-in-time joins + dedup + label generation
  → data quality and privacy gates
  → immutable/versioned training data
  → split assignment + feature selection
  → managed Dataset reference (if AutoML)
  → training job + evaluation
  → review / approval / promotion
~~~

Do not generate training tables via "a researcher hand-edits a notebook and reruns it." Store SQL/code in Git, query parameters (`as_of`, label horizon), pipeline job identities, schema versions, logs, and artifacts. With **Agent Platform Pipelines**, you can manage dependencies across components and record lineage; for smaller workflows, CI/CD can call BigQuery/Dataflow and the SDK directly, while still requiring idempotency and rollback.

### 11.2. Quality Gates That Should Block Releases

| Data Quality Gate | Illustrative Threshold Example | Why |
| --- | --- | --- |
| Uniqueness | 0 duplicate `order_id` rows. | Prevent duplicate leakage and implicit up-weighting. |
| Feature availability | 100% of features computable at `delivered_at`. | Prevent temporal leakage. |
| Label maturity | 100% of examples have full 30 days + buffer. | Avoid false negatives. |
| Required field null | `order_id`, target null = 0. | Data cannot serve as a supervised example if missing. |
| Data loss | Drop rate tracked and within approved threshold. | Prevent selection bias. |
| Class distribution | Positive labels present in every split; measure PR metrics. | Avoid empty classes in test or unstable metric reports. |
| Split contamination | 0 duplicate business IDs across splits; group leakage checked per goal. | Test must remain independent by design. |
| Privacy | No raw email/phone/token in feature tables. | Reduce risk of misuse. |
| Reproducibility | Snapshot ID + code version + config recorded. | Enable rebuilding, auditing, and rollback. |

Thresholds in this table are **illustrative internal policy examples**, not default Google Cloud SLAs. Gates must be tailored to the business; for instance, a very small customer segment might lack enough positive labels in test if the time window is split too narrowly.

### 11.3. Signals to Monitor

- **Data prep:** input/output record counts, duplicates, invalid values, data age, BigQuery/Dataflow job latency.
- **Training input:** class balance, missing rate per feature, file count, data volume, snapshot creation time, source URI/version.
- **Inference/serving:** unknown category rate, null feature rates, data/feature drift, train-serving skew.
- **Evaluation:** precision, recall, PR-AUC, and per-segment performance; account for label delay before measuring model quality.
- **Ops/cost:** BigQuery bytes billed/slots, GCS storage/operations, training compute, autoscaling, egress, logs, and dataset/artifact retention.

Set alerts for **schema drift or poor data quality**, not only when training jobs fail. A model can finish training successfully on bad data.

## 12. Costs and Commonly Overlooked Trade-offs

| Decision | Cost/Impact |
| --- | --- |
| Repeatedly scanning large raw BigQuery tables | Increases query bytes/slot usage; use partition pruning/materialized curated data. |
| Creating a snapshot/table version per run | Increases storage and retention management overhead, but enables reproducibility/audits. |
| Keeping many copies of raw images/video | Storage, annotation processing, GCS replication, and data transfer costs. |
| Reimporting a managed dataset when labels change | Consumes import/indexing time and may trigger processing/labeling costs. |
| Training experiments across many configs | Increases compute, training time, and artifact storage. |
| Putting every column into Feature Store | Adds operational/sync/online serving costs; use only when reuse/serving consistency is needed. |
| Feeding cross-region data into training | Risks location constraints, network transfer charges, and data residency issues. |

**Feature Store** (now under Agent Platform) manages features for reuse and offline/online sync when needed; it is **not** the same resource as a managed training Dataset. For a simple model running batch scoring on a versioned BigQuery table, Feature Store may not be necessary. Decide based on **training-serving skew, online latency requirements, and how many teams share features**.

Evaluate **cost per reproducible experiment and per model meeting SLOs**, not just dataset creation fees. Clean up trial tables, GCS staging, training endpoints/jobs, and objects once retention/approval expires; **do not delete sources still referenced by managed Datasets or other pipelines**.

## 13. Practical Scenario: 30-Day Return Model

### 13.1. A Verifiable Plan

| Stage | Tasks | Gate to Advance |
| --- | --- | --- |
| **Problem framing** | Predict return requests within 30 days **from delivery time**. | Label definition and inference timestamp finalized. |
| **Source inventory** | Verify `orders`, return events, and data owners. | IAM, legal validity, and ingestion timestamps in place. |
| **Label construction** | Use fixed as-of, 30-day maturity + ingest buffer. | Never assign 0 to orders lacking full observation. |
| **Feature contract** | Use only facts available at delivery. | No refund/return columns in the feature list. |
| **Quality checks** | Dedupe, null/negative durations, class ratio, missing categories. | Quality report generated, errors handled. |
| **Split** | By delivery time; design group tests if generalizing to new customers. | No leakage and test period is in the future. |
| **Version** | Immutable BigQuery table or snapshot, code digest, and run config. | Rows/splits are reproducible. |
| **Dataset & training** | Agent Platform managed dataset if AutoML; or custom training from BQ/GCS. | Dataset/job/model IDs and metrics recorded. |
| **Evaluation** | PR-AUC, precision/recall at threshold, metrics by region/seller. | Meets business/fairness requirements and latency. |
| **Monitoring** | Production feature data, labels arriving after 30 days. | Alerts and appropriate retraining schedule configured. |

### 13.2. Two Common Mistakes

**Mistake A — Extremely high AUC but undeployable:** the training set included `return_requested_at` as a numerical/timestamp feature. When running inference right at delivery time, that field does not exist yet. Fix by **whitelisting features available at delivery**, retraining, and evaluating on the locked test set.

**Mistake B — Model always predicts "no return":** data engineering treated orders delivered last week without a return event as label 0; many orders are returned later, mislabeling the dataset. Fix using a maturity cutoff, preserving raw history, and running a late-event reconciliation pipeline.

## 14. Symptom-Based Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Dataset created, yet training reads different data than yesterday | Tabular Dataset **links the source**; upstream table/CSV changed. | Dataset source URI, training snapshot/version, cutoff, and code. |
| Dataset creation fails with `PERMISSION_DENIED` | Caller or Agent Platform Service Agent lacks source permissions. | ADC principal, project/location, cross-project BigQuery/GCS IAM. |
| Table exists in BigQuery, yet Dataset creation fails | Unsupported source location or invalid URI/schema. | `bq://project.dataset.table`, region, data types, and source shape. |
| Image import fails | GCS URI/manifest/split label violates import schema. | Objective, schema URI, file permissions, CSV/JSONL format. |
| 99% accuracy but poor precision | Class imbalance, inappropriate evaluation metric. | Confusion matrix, prevalence, PR-AUC, threshold. |
| Train score much higher than test | Overfitting, drift, or train/test leakage. | Splits, duplicates, feature timing, data distribution. |
| Unusually high test score followed by production failure | Target/temporal leakage or training-serving skew. | Feature availability, point-in-time joins, serving transformations. |
| Many null labels | Orders under 30 days old, missing return events, or bad join. | As-of, maturity buffer, late data, and label rules. |
| Non-reproducible results with same Dataset ID | Mutable source data, changing split/random seed, or code changes. | Snapshot/generation, run parameters, preprocessing version. |
| One segment performs poorly | Non-representative dataset, noisy labels, insufficient samples. | Metrics by region/device/season, consent, and sample balance. |
| High data prep cost | Full BigQuery table scans every run, many trial/staging files. | Partition filters, dry runs, Billing, retention. |
| Model rejects new features | Schema drift or incompatible inference preprocessing. | Feature contract version, training-serving tests. |

**Runbook:** confirm goal and prediction time → check source/label maturity → read quality gates → compare feature list and splits → reconcile snapshot/code version → verify IAM/region → test on an approved sample → only then consider retraining. Never fix `PERMISSION_DENIED` by granting Project Owner or making a bucket public.

## 15. Exercises

### Exercise 1 — Choosing Dataset Storage

Classify four cases: (a) one million orders with tabular features; (b) 40,000 product images with labels; (c) custom PyTorch pipeline reading TFRecords from GCS; (d) data in BigQuery using AutoML. For each case, choose the **storage source** and state whether a **managed Dataset resource is required**.

### Exercise 2 — Feature Availability

A model predicts return requests **right at successful delivery**. Among the following fields, which must not be used as features: `subtotal_vnd`, `shipping_method`, `delivery_duration`, `return_requested_at`, `refund_status`, `item_count`? Explain using a timeline.

### Exercise 3 — Immature Labels

The pipeline runs on 2026-11-01, targeting returns within 30 days from delivery. Should orders delivered on 2026-10-25 be assigned label 0? If upstream typically lags by another 5 days, how should you choose the sample cutoff?

### Exercise 4 — Data Validation

A table has 10,000 rows, 300 duplicate `order_id` values, 100 negative `subtotal_vnd` rows, and 600 rows missing `shipping_method`. Write SQL/profiling to measure each error rate, then choose **block, quarantine, impute**, or **keep missing category** per field; state the risk of dropping all 600 rows.

### Exercise 5 — Chronological and Customer Splits

Write a BigQuery query assigning TRAIN before July, VALIDATE in July, and TEST from August onward. If the new goal is predicting brand-new customers, design an additional group split and verify that the same `customer_id` never appears across two splits.

### Exercise 6 — SQL for the Returns Problem

Based on the template in Section 7, identify two potential sources of leakage/selection bias, add a query checking duplicate `order_id`s, and add a test detecting features generated after `delivered_at`. Why is a **historical delivery events** source needed instead of current order state?

### Exercise 7 — BigQuery Source vs Managed Dataset

You create a managed tabular dataset `returns-v1` linked to `bq://retail-lab.ml_data.return_training_v1`. Later, upstream overwrites the table while the Dataset resource ID stays unchanged. Can the next training run differ from the previous run? Propose three metadata/artifacts to ensure reproducibility.

### Exercise 8 — Images and Annotation Quality

A shirt/shoe/bag classification image set has 5% identical photos shared between train/test, and human annotators disagree on many images. Fix the annotation guidelines, duplicates, and split before training; explain how single-label differs from multi-label.

### Exercise 9 — Cross-Project IAM

An Agent Platform Dataset is created in project A, while the training table resides in project B. Local `bq show` succeeds, yet import/training returns 403. Which **principals**, which roles in B, and which region/location settings must you check?

### Exercise 10 — Cost Optimization and Evaluation

A team runs 20 training experiments, each scanning an entire 3 TB raw table and making a GCS copy; model quality barely improves. Propose a curated table/snapshot, partition pruning, preprocessing caching, artifact retention, and metrics to monitor. Why must test/quality checks never be skipped just to cut costs?

## 16. Production Checklist and Official Documentation

| Item | Verification Question |
| --- | --- |
| **Task/label** | Are prediction time and target horizon clearly defined? |
| **Sources** | Are BigQuery/GCS sources valid, with proper IAM, region, and provenance? |
| **Managed dataset** | Is an AutoML Dataset needed or does custom training read directly? Does the resource link a mutable source? |
| **Features** | Do features use only info available at inference; consistent with serving code? |
| **Quality** | Have deduplication, missingness, validation, class balance, and sample-selection bias been checked? |
| **Split** | Is random/chronological/group aligned with evaluation goal; is test kept out of tuning? |
| **Versioning** | Are immutable sources, snapshot/object generation, `as_of`, code digest, and split policy recorded? |
| **Labels** | Are orders under 30 days protected from false negatives; are late returns handled? |
| **Security** | Are data engineer, training SA, Agent Platform Service Agent, and auditor separated; PII/consent compliant? |
| **Lineage** | Are dataset, SQL version, and training job/model IDs logged? |
| **Cost** | Are queries/slots, storage, training, transfer, annotation, and retention estimated? |
| **Operations** | Are quality gates, drift alerts, approval, rollback, and safe cleanup in place? |

Official references to verify products, APIs, and quotas by version:

- [Vertex AI → Gemini Enterprise Agent Platform: new product names](https://docs.cloud.google.com/gemini-enterprise-agent-platform/vertex-ai-name-changes)
- [Managed datasets overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/datasets/overview)
- [Prepare tabular classification/regression data](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/prepare-data)
- [Create tabular datasets; BigQuery/GCS association and training snapshot](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/classification-regression/create-dataset)
- [Best practices for tabular data: leakage/skew/bias](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/bp-tabular)
- [Data splits for tabular models](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/tabular-data/data-splits)
- [Image classification: prepare data and annotations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/image-data/classification/prepare-data)
- [Agent Platform SDK Python: TabularDataset](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest/google.cloud.aiplatform.TabularDataset)
- [Agent Platform IAM and service agents](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/general/access-control)
- [Track lineage of pipeline artifacts](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/pipelines/lineage)
- [BigQuery table snapshots](https://docs.cloud.google.com/bigquery/docs/table-snapshots-intro)
- [BigQuery cost best practices](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)

**Takeaway:** managing datasets is not merely creating a resource in Vertex AI/Agent Platform. Model quality depends on **point-in-time accurate labels, features that never look into the future, splits that mirror production, and pinned data sources for reproducibility**. BigQuery/GCS store the actual data; a managed Dataset connects data to training workflows when needed. IAM, versioning, quality, and costs must be verified **before clicking Train**, not only after a model shows impressive metrics.

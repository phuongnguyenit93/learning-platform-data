# Vertex AI Feature Store and Feature Serving on Google Cloud

> **Chapter:** Vertex AI and Machine Learning  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, secure resources, automate releases, and monitor reliability alongside cost.

A churn prediction model needs the exact same **feature** definitions during training and inference: 30-day spend, logins over the past 7 days, current subscription plan. If the data team computes them with SQL in BigQuery while the Cloud Run API writes separate Java logic to compute them in real time, the system suffers **training-serving skew**, discrepancies in timestamps, NULL handling, timezones, and data normalization.

**Vertex AI Feature Store**—now presented in Google Cloud documentation as **Feature Store on Gemini Enterprise Agent Platform**—lets you use **BigQuery as an offline feature source**, register and manage features, and sync serving values to a **FeatureOnlineStore**. Applications on **Cloud Run/GKE/Compute Engine** call the online serving API to look up features by **entity ID** before running model inference.

This lesson uses **Bigtable online serving** as the primary deployment option. **Optimized online serving was deprecated on May 17, 2026, with scheduled sunset on February 17, 2027**, so do not build new systems on it. Examples use synthetic customers and a tiny BigQuery table; never use real personal data.

**Safety and cost:** creating a Bigtable-backed FeatureOnlineStore can incur compute/storage costs even with low traffic. Never run store create/delete commands or modify IAM in production. Deployment steps are strictly for a lab project with billing/quota and owner approval.

## Learning Objectives

1. Distinguish **feature**, **entity**, **offline store**, **Feature Registry**, **FeatureOnlineStore**, **FeatureView**, **sync**, and **online fetch**.
2. Design a BigQuery feature table with a **unique entity ID** when creating a feature view directly from a source.
3. Prevent future data leakage using **point-in-time joins** when building training sets.
4. Create a **Bigtable** online store, a feature view, and read features by entity ID via REST/Python.
5. Explain scheduled sync, continuous sync, refresh lag, NULL semantics, and UPDATE/DELETE limitations.
6. Design separated IAM permissions across BigQuery sources, Vertex AI Feature Store, runtime callers, and service agents.
7. Verify data correctness, p95/p99 latency, drift, quotas, storage, and costs.
8. Evaluate when Feature Store is better than querying BigQuery directly, self-managed caches, or Vector Search.

## 1. Offline → Online → Inference Architecture

~~~mermaid
flowchart LR
    SRC["Cloud SQL / Pub/Sub / app"] --> PIPE["ELT / Dataflow / scheduled SQL"]
    PIPE --> BQ["BigQuery offline features\nlatest + history"]
    BQ --> REG["Feature Registry\noptional"]
    BQ --> FV["FeatureView"]
    REG -. "Feature definitions" .-> FV
    FV --> SYNC["Scheduled / Continuous sync\nwhen supported"]
    SYNC --> STORE["FeatureOnlineStore\nBigtable serving"]
    API["Cloud Run Java API"] --> FETCH["fetchFeatureValues(entity ID)"]
    STORE --> FETCH
    FETCH --> MODEL["Vertex AI / custom model"]
    MODEL --> APP["Prediction/decision\nwith business controls"]
    BQ --> TRAIN["Point-in-time training data"]
    TRAIN --> EXP["Training / evaluation / model registry"]
~~~

**Distinguish three planes:**

| Component | Role | Common Misconception |
|---|---|---|
| **BigQuery feature tables** | Offline data, history, features for batch/training | Not a low-latency online per-entity lookup endpoint by itself |
| **Feature Registry** | Metadata/declarations for feature groups and feature columns | Does not store an online copy of data itself |
| **FeatureOnlineStore + FeatureView** | Materializes BigQuery data and serves latest values | Does not replace model training engines or model endpoints |

**Feature Store does not predict labels.** Online fetch returns feature values; model-serving code then invokes the model for inference. If the model needs additional real-time features not yet synced, design a proper merging architecture rather than assuming Feature Store already reflects every transaction instantly.

### 1.1. Entity, Feature, and Feature View

| Concept | Example | Responsibility |
|---|---|---|
| **Entity** | Customer **cust-101** | Lookup key for an object's data |
| **Feature** | **spend_30d**, **sessions_7d**, **plan** | Value with SQL definition, type, owner, and freshness SLA |
| **Feature group** | **customer_behavior** | Registers BigQuery source and metadata; can hold time-series history |
| **Feature Registry** | Catalog of feature groups/features | Feature reuse and governance |
| **FeatureOnlineStore** | **customer-features-lab** | Compute/storage backing online reads |
| **FeatureView** | **churn-inputs-lab** | Set of features synced/served under one configuration |
| **Feature timestamp** | 2026-11-18T10:00:00Z | Event time when a feature value took effect |
| **Sync schedule** | Hourly | Freshness of the online view, not the source update rate |

For a **FeatureView directly from BigQuery**, each source row must have a unique entity ID and **only current values**; never point a direct source table containing multiple historical rows per entity or a column named **`feature_timestamp`**. If you need history, time series, or multi-source features, use **Feature Registry/feature groups** where supported.

### 1.2. Why Doesn't an Online Store Replace BigQuery History?

BigQuery preserves historical values to reconstruct features at **decision time**. An online store typically serves the **latest value** per entity for fast inference. When an online API is called at 12:00, you cannot pull 09:00 values to train a historical model simply by querying the online store at 12:00.

Offline history and online latest values can originate from the same pipeline, provided they share **time semantics, version/schema contracts, and quality gates**.

## 2. Choosing the Right Online Serving Option for Your Product Lifecycle

| Option | Status / Characteristics | When to Use |
|---|---|---|
| **Bigtable online serving** | Current direction; supports scheduled and conditional continuous sync | High-durability, high-volume per-entity feature serving |
| **Optimized online serving** | **Deprecated May 17, 2026**, sunset **February 17, 2027** | Only maintain/migrate legacy workloads; **do not build new systems on it** |
| **Direct BigQuery SQL** | No materialized online store needed | Batch predictions/SQL joins; higher latency than online key lookups |
| **Self-managed Redis/Memorystore cache** | Flexible, but you manage sync/expiry/schemas yourself | Simple caching use cases without Feature Registry needs |
| **Vector Search** | Built for nearest-neighbor search over embeddings | Retrieval/semantic search; Bigtable online serving does not manage embeddings |
| **Vertex AI endpoint** | Accepts features to run model inference | Model serving, not feature storage |

**Important as of November 2026:** do not present Optimized online serving as a recommended choice for new designs, even if older docs/APIs still show examples. Google Cloud recommends **migrating to Bigtable online serving** and using **Vector Search** for embedding retrieval. See [Online serving types](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/online-serving-types).

## 3. Two Ways to Declare a FeatureView

### 3.1. Directly from BigQuery — Primary Lab Path

~~~text
BigQuery table:
bq://PROJECT_ID.feature_lab.customer_features_latest

customer_id STRING | spend_30d FLOAT64 | sessions_7d INT64 | plan STRING
------------------ | ---------------- | ----------------- | -----------
cust-101           | 520000.0         | 9                 | plus
cust-102           | 120000.0         | 2                 | basic
cust-103           | 930000.0         | 15                | team
~~~

When creating the **FeatureView**: specify **`big_query_source.uri`** and **`entity_id_columns=["customer_id"]`**. The table has one row per customer and needs no Feature Registry. This is the easiest path to practice, though **it does not support storing historical feature records per ID inside that direct FeatureView source table**.

### 3.2. Via Feature Registry — When Governance and Time-Series Are Needed

~~~text
BigQuery feature history
       ↓
FeatureGroup customer_behavior
  source URI / entity IDs / time-series column
       ↓
Feature definitions (spend_30d, sessions_7d, plan)
       ↓
FeatureView linked to feature group
       ↓
Bigtable online serving
~~~

Registering feature groups/features pays off when **one BigQuery entity has multiple timestamps**, when combining features across multiple feature groups, or for feature monitoring and metadata reuse. In a time-series model, **`feature_timestamp`** must be `TIMESTAMP` and declared properly; Feature Store generally serves the **latest non-null value** by timestamp, unless configured with supported **dense + Bigtable + scheduled sync** settings to retain latest NULLs. Never treat NULL as equivalent to DELETE.

**Watch out with continuous sync:** supported only when the FeatureView sources from **Feature Registry**, the online store is **Bigtable**, and the BigQuery source resides in a supported location (e.g., **us, eu, us-central1**). It syncs **new records only**, does not propagate UPDATEs or DELETEs on existing records, and prevents editing that feature view config after creation. Details: [Create a feature view](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-featureview).

## 4. Preparing Lab Environment and Resources

### 4.1. Read-Only Preflight

Assumes **Cloud Shell (Bash)**, organization-approved BigQuery/Vertex AI APIs, and a project with billing, quota, and permissions.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="us-central1"
DATASET="feature_lab"
ONLINE_STORE="customer-features-lab"
FEATURE_VIEW="churn-inputs-lab"

gcloud auth list
gcloud config list project
gcloud projects describe "$PROJECT_ID"

# READ-ONLY: check enabled APIs and existing datasets/resources.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="NAME:(aiplatform.googleapis.com OR bigquery.googleapis.com)"

bq --project_id="$PROJECT_ID" ls
~~~

**Location:** BigQuery datasets and Feature Store resources must use **compatible locations**—do not arbitrarily mix US multi-region with `us-central1`. This lab uses **`us-central1`** for both. If your project has different data residency requirements, verify [supported locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/locations) before deploying.

### 4.2. Enable APIs If Approved

~~~bash
# MODIFIES PROJECT CONFIG — requires sufficient IAM and owner approval.
gcloud services enable aiplatform.googleapis.com bigquery.googleapis.com \
  --project="$PROJECT_ID"
~~~

**Never create JSON service account keys** to call Feature Store; locally use authorized `gcloud`/ADC, and on Cloud Run or GKE use workload identity. IAM for the BigQuery source and FeatureView may span separate projects; permissions do not automatically propagate across projects.

### 4.3. Create the Lab's Own BigQuery Dataset

~~~bash
# WRITES: create only if non-existent and approved.
bq --project_id="$PROJECT_ID" --location="$LOCATION" mk \
  --dataset "$PROJECT_ID:$DATASET"

# READ-ONLY: confirm dataset location.
bq --project_id="$PROJECT_ID" show "$PROJECT_ID:$DATASET"
~~~

If **`feature_lab`** already belongs to another team, never overwrite its tables or alter IAM; request a dedicated dataset. The SQL queries below use the **`PROJECT_ID`** placeholder: replace it with your lab project ID before running.

## 5. Lab A — Preparing the Latest Feature Table in BigQuery

### 5.1. Generate Synthetic Data Without PII

In **BigQuery Studio**, select GoogleSQL, your lab project/location, and run:

~~~sql
-- MODIFIES/REPLACES: lab table only.
CREATE OR REPLACE TABLE `PROJECT_ID.feature_lab.customer_features_latest`
OPTIONS (
  expiration_timestamp =
    TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
) AS
SELECT *
FROM UNNEST([
  STRUCT('cust-101' AS customer_id,
         520000.0 AS spend_30d,
         9 AS sessions_7d,
         'plus' AS plan),
  STRUCT('cust-102', 120000.0, 2, 'basic'),
  STRUCT('cust-103', 930000.0, 15, 'team')
]);
~~~

**Feature semantics:**

- **`spend_30d` (`FLOAT64`):** total spend over the past 30 days under an agreed timezone and rounding rule.
- **`sessions_7d` (`INT64`):** valid active sessions over the past 7 days.
- **`plan` (`STRING`):** current subscription tier; handle unknown categories consistently between train and predict.
- **`customer_id` (`STRING`):** serving lookup key, **not automatically a model input feature** without a valid reason.

This is a **latest** table with one row per customer and **no `feature_timestamp` column**, making it valid for creating a FeatureView directly from BigQuery. Never use this table as multi-timestamp training history.

### 5.2. Verify Key Uniqueness, Schema, and NULLs

~~~sql
-- READ-ONLY.
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT customer_id) AS unique_ids,
  COUNTIF(customer_id IS NULL OR customer_id = '') AS missing_ids,
  COUNTIF(spend_30d IS NULL OR sessions_7d IS NULL) AS missing_features
FROM `PROJECT_ID.feature_lab.customer_features_latest`;

-- Ensure no duplicate entity IDs.
SELECT customer_id, COUNT(*) AS occurrences
FROM `PROJECT_ID.feature_lab.customer_features_latest`
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

**Expected:** `row_count=3`, `unique_ids=3`, `missing_ids=0`, `missing_features=0`; duplicate query returns 0 rows. On real data, enforce a **quality gate** prior to sync; never expect the online store to guess which row to keep on duplicate keys.

### 5.3. Latest Data May Not Be Fresh Enough for Business Needs

A table with one row per customer might have last been refreshed 12 hours ago. Every feature needs a **contract** covering source timestamp, freshness, and refresh schedule. If you add a **`computed_at`** field for observability, it becomes a feature/metadata column; verify policies on exposed columns and **never name it `feature_timestamp`** when using a direct BigQuery source.

**Data deletion:** deleting a customer from the BigQuery source **does not automatically delete the corresponding entity from a Bigtable FeatureView during sync**. Never treat a BigQuery row DELETE as guaranteeing deletion from the online store; you need a view deletion/recreation runbook or appropriate serving access/retention controls.

## 6. Point-in-Time Correctness — Preventing Training-Serving Skew

### 6.1. Two Timestamps You Must Know

For any feature built from transactional events, distinguish:

- **`feature_timestamp` / event time:** when the event occurred or state took effect.
- **`available_at` / ingestion time:** when the feature actually became available in the pipeline.
- **`prediction_time`:** when the model is allowed to observe features to make a prediction.
- **`label_window`:** future window defining ground truth; must never appear in features.

**Minimum condition:** `feature_timestamp` **not after** `prediction_time` **and** `available_at` **not after** `prediction_time`. Filtering on event time alone leaks data if late-arriving events are backfilled as though they had been ready at event time.

### 6.2. Complete Point-in-Time Join Example in GoogleSQL

The query below **reads only inline synthetic data** (creates zero resources) and intentionally tests two prediction timestamps for one customer.

~~~sql
WITH feature_history AS (
  SELECT *
  FROM UNNEST([
    STRUCT(
      'cust-101' AS customer_id,
      TIMESTAMP('2026-10-01T09:00:00Z') AS feature_timestamp,
      TIMESTAMP('2026-10-01T09:03:00Z') AS available_at,
      100000.0 AS spend_30d,
      2 AS sessions_7d
    ),
    STRUCT(
      'cust-101',
      TIMESTAMP('2026-10-02T09:00:00Z'),
      TIMESTAMP('2026-10-02T09:10:00Z'),
      200000.0,
      5
    ),
    -- Past event that arrived late: must NOT be used on Oct 01.
    STRUCT(
      'cust-101',
      TIMESTAMP('2026-10-01T10:00:00Z'),
      TIMESTAMP('2026-10-03T00:00:00Z'),
      999999.0,
      99
    )
  ])
),
prediction_samples AS (
  SELECT *
  FROM UNNEST([
    STRUCT(
      'sample-1' AS sample_id,
      'cust-101' AS customer_id,
      TIMESTAMP('2026-10-01T12:00:00Z') AS prediction_time
    ),
    STRUCT(
      'sample-2',
      'cust-101',
      TIMESTAMP('2026-10-02T12:00:00Z')
    )
  ])
)
SELECT
  p.sample_id,
  p.customer_id,
  p.prediction_time,
  f.feature_timestamp,
  f.spend_30d,
  f.sessions_7d
FROM prediction_samples p
LEFT JOIN feature_history f
  ON p.customer_id = f.customer_id
 AND f.feature_timestamp <= p.prediction_time
 AND f.available_at <= p.prediction_time
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY p.sample_id
  ORDER BY f.feature_timestamp DESC, f.available_at DESC
) = 1
ORDER BY p.sample_id;
~~~

**Expected result:** `sample-1` gets `spend_30d=100000`, `sessions_7d=2`; `sample-2` gets `200000` and `5`. The `999999` record became available after both prediction timestamps and **is excluded from both samples**, even though its event time was in the past.

At scale, apply time partitioning/filtering, handle multiple versions and late-arriving events, cluster by entity key, and optimize joins. BigQuery also provides **`ML.FEATURES_AT_TIME`** and **`ML.ENTITY_FEATURES_AT_TIME`** functions for point-in-time feature lookups; see [BigQuery feature serving](https://docs.cloud.google.com/bigquery/docs/feature-serving).

### 6.3. Common Sources of Skew

| Discrepancy | Consequence | How to Avoid |
|---|---|---|
| SQL computes **7 rolling days** while Java computes **calendar week** | Feature definitions diverge | Single feature contract and tests |
| Training uses UTC timestamps, serving uses local time | Shifted windows | Explicit UTC/as-of rules |
| Backfill uses data arriving after snapshot | Data leakage | Enforce `available_at` checks |
| Offline is NULL while online returns prior non-null value | Model receives stale value | Configure explicit NULL semantics |
| Categorical values differ in casing | Mapping mismatch | Shared preprocessing/versioned schema |
| Offline latest updated, yet FeatureView sync hasn't run | Stale online values | Freshness SLO and sync monitoring |
| Model v2 expects new feature while FeatureView stays on schema v1 | Missing feature | Contract tests prior to rollout |

**Never claim Feature Store "automatically eliminates all skew."** The service standardizes feature reuse and per-entity serving; correctness of feature computation, timestamps, availability, types/schemas, and model versions remains the pipeline's responsibility.

## 7. Lab B — Creating a FeatureOnlineStore with Bigtable Online Serving

### 7.1. Checking Cost and Permissions Before Creation

**`FeatureOnlineStore` is a separate online resource:** a tiny BigQuery table does not make online serving free. Create it only in an owner-approved lab project. If your team already owns a shared store, reuse it when permitted; **never spin up a new one just to test an API**.

The creator needs Vertex AI Feature Store management permissions, and the service agent must be configured to read the BigQuery source. The commands below use **REST v1** in Cloud Shell/Bash:

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
LOCATION="us-central1"
ONLINE_STORE="customer-features-lab"
FEATURE_VIEW="churn-inputs-lab"

API_ROOT="https://$LOCATION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$LOCATION"

# READ-ONLY: returns existing store or 404 if not yet created.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"
~~~

### 7.2. Creating a Bigtable Online Store (Mutating, Billable)

In a separate lab folder, never placing IAM configs or secrets into the course repository:

~~~bash
# Create example JSON locally; does not call Cloud API yet.
cat > online-store.json <<'JSON'
{
  "bigtable": {
    "auto_scaling": {
      "min_node_count": 1,
      "max_node_count": 3,
      "cpu_utilization_target": 50
    }
  }
}
JSON

# BILLABLE MUTATION: POST only if store does not exist and owner approved.
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @online-store.json \
  "$API_ROOT/featureOnlineStores?feature_online_store_id=$ONLINE_STORE"
~~~

**The response is typically a long-running operation:** a successful POST does not mean the resource is ready for feature views yet. Check operation status and online store details in Console or REST. Min/max node counts and CPU target here are illustrative only—**do not treat them as default production sizing**. [Create an online store](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-onlinestore).

### 7.3. Choose Bigtable, Not Optimized

Bigtable online serving supports **CMEK** when required; it **does not support embedding management**. For approximate nearest neighbors, evaluate **Vector Search**. Do not copy an Optimized configuration into JSON for new stores just because an old blog post uses it. The online serving type **cannot be changed after store creation**; switching types requires migrating to a new resource.

## 8. Lab C — Creating a FeatureView from a BigQuery Table

### 8.1. Declaring Direct Source and Sync Schedule

Proceed only after the **`FeatureOnlineStore` is ready** and **`customer_features_latest`** passes uniqueness checks.

~~~bash
# Uses environment variables from Section 7.
# Lab file contains no credentials, only resource names.
cat > feature-view.json <<EOF
{
  "big_query_source": {
    "uri": "bq://$PROJECT_ID.feature_lab.customer_features_latest",
    "entity_id_columns": ["customer_id"]
  },
  "sync_config": {
    "cron": "0 * * * *"
  }
}
EOF

# MUTATES: creates FeatureView with hourly sync schedule.
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @feature-view.json \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews?feature_view_id=$FEATURE_VIEW"
~~~

**Semantics:** FeatureView keys by **`customer_id`** and serves the remaining feature columns. Cron **`0 * * * *`** schedules sync **once per hour**—it does not update the online store the instant BigQuery changes. Check cron/sync limits and BigQuery scan costs before choosing a production cadence. [Create a feature view](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-featureview).

### 8.2. Triggering Manual Sync and Checking Status

For a feature view using **scheduled sync**, you can trigger an immediate sync instead of waiting for cron:

~~~bash
# MUTATES: triggers sync, may incur BigQuery/Feature Store charges.
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data '' \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW:sync"

# READ-ONLY: view details and sync history.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW/featureViewSyncs"
~~~

The **sync** response may return only a **`FeatureViewSync` resource name**, not proof that materialization finished. Inspect the operation's **`finalStatus`**, errors, start/end timestamps, and record counts. **Do not trigger sync repeatedly** while one is already in flight; subsequent requests may be queued.

**Continuous sync** cannot be manually triggered; nor does it **apply** to direct BigQuery FeatureViews like this lab. [Start a data sync](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/sync-data).

### 8.3. Checking IAM During Sync

When the BigQuery source resides in another project or uses a **dedicated feature view service account**, the principal Feature Store uses to query the table needs matching BigQuery permissions. Retrieve the service account email from the FeatureView details API if configured as dedicated; grant permissions on the **source dataset/table** plus BigQuery job creation rights per docs.

On Access Denied errors, identify the **principal in sync logs**, **dataset IAM**, and **BigQuery job permissions**—never grant Project Owner. Sync can be blocked by a location mismatch or BigQuery job quota even when the source table has only three rows.

## 9. Lab D — Online Fetch by Entity ID

The FeatureView must have **synced successfully at least once** before online reads return data.

~~~bash
# READ-ONLY feature values (though online requests may be billed).
curl -f -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data '{"data_key":{"key":"cust-101"},"data_format":"KEY_VALUE"}' \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW:fetchFeatureValues"
~~~

**Expected:** output contains **`spend_30d=520000`**, **`sessions_7d=9`**, **`plan=plus`** in actual `KEY_VALUE`/protobuf JSON format. Never hardcode response parsing into a business DTO without verifying field names and types; validate on parse.

### 9.1. Non-Existent Entity

~~~bash
# READ-ONLY; observe not-found/empty behavior of the active API.
curl -i -sS -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data '{"data_key":{"key":"cust-does-not-exist"},"data_format":"KEY_VALUE"}' \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW:fetchFeatureValues"
~~~

**Never** silently map every 404/permission/timeout error to **`0`** or **`plan=basic`** and keep running the model. The application must distinguish a missing entity, an unsynced online view, denied permissions, and transient errors. Any fallback requires an explicit contract and monitoring.

### 9.2. Composite Entity Key

With two key columns (**`tenant_id`**, **`customer_id`**), FeatureView can declare both; when fetching, pass **`data_key.composite_key.parts`** in the exact order.

~~~json
{
  "data_key": {
    "composite_key": {
      "parts": ["tenant-a", "cust-101"]
    }
  },
  "data_format": "KEY_VALUE"
}
~~~

Never concatenate keys with an unescaped delimiter like **`tenant#customer`** if IDs might contain that character, and never trust unvalidated user input as a multi-tenant key.

### 9.3. Verifying Online Freshness After BigQuery Changes

~~~sql
-- MODIFIES LAB TABLE, never use a production table.
UPDATE `PROJECT_ID.feature_lab.customer_features_latest`
SET sessions_7d = 11
WHERE customer_id = 'cust-101';
~~~

Fetching immediately after `UPDATE` may still return **`9`** because the scheduled sync hasn't run yet. Trigger a manual **sync** on the scheduled FeatureView, confirm completion, and fetch again—expect **`11`**. If it still returns `9`, inspect sync status, source URI, permissions, and any read caches rather than misdiagnosing the service before sync completes.

### 9.4. Deleting an Entity Does Not Delete Online Features

If **`cust-102`** is deleted from BigQuery, **a Bigtable FeatureView does not automatically delete `cust-102` during sync**. Google Cloud documentation requires **deleting the FeatureView** to purge retained records. Systems subject to data deletion obligations must maintain a **deletion runbook** and verify the entire chain, not just a BigQuery `DELETE`.

In production apps, add a **consent/active-entity policy** or block serving upon deletion requests even while the online store still awaits cleanup. Deleting/recreating views can cause downtime and requires owner approval.

## 10. Using Feature Store from a Java/Cloud Run Application

Like Cloud Tasks/BigQuery, a Cloud Run Java API can call **`featureViews.fetchFeatureValues`** over HTTPS. The **Cloud Run runtime service account** token is obtained via **Application Default Credentials (ADC)**—never embed API keys or service account JSON files in code.

### 10.1. Maven Dependency

In a Java 21 Maven application:

~~~xml
<!-- Example: pick an auth library version tested compatible in your project BOM. -->
<dependency>
  <groupId>com.google.auth</groupId>
  <artifactId>google-auth-library-oauth2-http</artifactId>
  <version>1.40.0</version>
</dependency>
~~~

The version shown is a fixed example for illustration, not permanently latest; production systems must audit versions, JDK compatibility, CVEs, and the dependency tree.

### 10.2. Java 21 HTTP Client Calling Feature Store

~~~java
package lab;

import com.google.auth.oauth2.GoogleCredentials;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;

public final class FeatureReadExample {
    public static void main(String[] args) throws Exception {
        String project = required("PROJECT_ID");
        String location = required("LOCATION");
        String store = required("ONLINE_STORE");
        String view = required("FEATURE_VIEW");
        String customerId = args.length > 0 ? args[0] : "cust-101";

        // Lab: allowlist ID pattern; production: validate tenant/ownership.
        if (!customerId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid entity ID");
        }

        String endpoint = "https://" + location
                + "-aiplatform.googleapis.com/v1/projects/"
                + project + "/locations/" + location
                + "/featureOnlineStores/" + store
                + "/featureViews/" + view + ":fetchFeatureValues";

        GoogleCredentials credentials = GoogleCredentials
                .getApplicationDefault()
                .createScoped(List.of(
                    "https://www.googleapis.com/auth/cloud-platform"));
        credentials.refreshIfExpired();

        // Validation above makes interpolating customerId into JSON safe
        // in this lab. Production: use a JSON library to serialize payloads.
        String json = "{\"data_key\":{\"key\":\"" + customerId
                + "\"},\"data_format\":\"KEY_VALUE\"}";

        HttpRequest request = HttpRequest.newBuilder(URI.create(endpoint))
                .timeout(Duration.ofSeconds(5))
                .header("Authorization", "Bearer "
                        + credentials.getAccessToken().getTokenValue())
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json))
                .build();

        try (HttpClient client = HttpClient.newHttpClient()) {
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException(
                    "Feature fetch HTTP " + response.statusCode());
            }

            // Demo only with synthetic data; never log raw production PII.
            System.out.println(response.body());
        }
    }

    private static String required(String name) {
        String v = System.getenv(name);
        if (v == null || v.isBlank()) {
            throw new IllegalArgumentException("Missing " + name);
        }
        return v;
    }
}
~~~

**Additions needed for production:** reuse **`HttpClient`** and credential providers across the application lifecycle (never create per request), handle SDK access-token refresh caching properly, parse typed responses, measure latency, enforce deadlines and retry budgets; never retry 401/403 or 404 unconditionally. Load endpoints/IDs from trusted config to prevent SSRF via user-supplied URLs.

### 10.3. Integration with Model Serving

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant API as Cloud Run Java service
    participant F as FeatureView Bigtable
    participant M as Vertex AI model endpoint
    U->>API: POST /predict customerId
    API->>API: Authenticate + authorize tenant/customer
    API->>F: fetchFeatureValues(customerId)
    F-->>API: spend_30d / sessions_7d / plan
    API->>API: Validate schema, freshness, missing values
    API->>M: Predict with feature vector
    M-->>API: probability/label
    API-->>U: Business-approved result
~~~

**Never forward the raw Feature Store response straight into a model** if the model schema expects different preprocessing or versioning. Map features according to the **model signature**, validate types and units, log model/feature version metadata, and never log tokens or PII.

### 10.4. Offline and Online Must Share a Contract

Suppose model v2 requires **`refunds_90d`**, while FeatureView v1 does not sync that feature yet. Before shifting production traffic to model v2, deploy the feature pipeline/schema, sync, verify **`refunds_90d`** on test entities, run canary inference, and only then cut over. During rollback, keep the FeatureView/model versions needed by any callers still on the old version.

## 11. Syncing Features: Scheduled, Continuous, and Direct Write

### 11.1. Semantics You Cannot Ignore

| Capability | Scheduled Sync | Continuous Sync | Direct Write |
|---|---|---|---|
| Online store | Bigtable (and legacy Optimized) | **Bigtable** | **Bigtable** |
| FeatureView source | Direct BigQuery or Feature Registry | **Feature Registry + feature groups** | Written directly to FeatureView |
| Scheduling | Cron or manual trigger | Driven by supported source updates | Driven by writer requests |
| BigQuery source | Valid table/view | Table in supported region | Does not require updating BigQuery first |
| UPDATE/DELETE from BigQuery | UPDATEs apply after sync per rules; entity DELETEs **are not auto-purged** | **New records only**; UPDATE/DELETE not synced | Does not support entity/feature deletion |
| Freshness | Depends on schedule + job duration | Depends on pipeline and source conditions | Can be low latency, but Preview |
| Support level | GA per configuration | Specific documented constraints | **Preview**, requires risk assessment |

**Direct write** to a Bigtable online FeatureView is currently in **Preview**, does not automatically write back to BigQuery tables, and offers no API to delete existing entities. If an application requires offline–online consistency, design primary source updates and reconciliation as well. [Update features in a feature view](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/featureview-direct-write).

### 11.2. NULL Values and Latest-Value Logic

For feature groups with **`feature_timestamp`**, Feature Store normally serves the **latest non-null value**: if a newer snapshot contains NULL, an older non-null historical value may still be served. That is intentional semantics, though it can clash with a business contract stating **"NULL means no current info."**

When you want latest-value semantics to preserve NULLs, documentation requires the matching configuration—such as **Feature Registry `dense=true` + Bigtable online serving + scheduled sync**. Never blindly fill NULLs with `0` across all models, since **`0`** is a valid numeric measurement whereas **NULL** indicates missing data.

### 11.3. Calculating the Freshness Budget

Suppose the feature pipeline from Cloud SQL/BigQuery finishes in **4 minutes**, sync runs every **15 minutes**, and the sync job takes up to **3 minutes** in a hypothetical setup:

\[
\text{Approximate worst-case lag}
\leq 4+15+3 = 22\ \text{minutes}
\]

This is an **estimate, not a Google Cloud SLA**. If the business needs features under 30 seconds old, this sync setup fails even if online **lookup latency** is tens of milliseconds. Define **end-to-end freshness** from source event to online store, not just fetch latency.

### 11.4. Monitoring Sync Per FeatureView

- **Sync success/failure:** did the operation finish with zero `finalStatus` errors?
- **Last successful sync time:** has it breached the freshness SLO?
- **Source data timestamp/availability:** were the latest BigQuery records processed?
- **Online sampled values:** read the same entity before/after sync and compare hash/types/NULLs.
- **Schema drift:** columns renamed, dropped, or type-changed between source and FeatureView.
- **Deleted entities:** records removed at source yet remaining online; requires a separate deletion runbook.

Never treat HTTP 200 on fetch as proof features are fresh; the response may return **stale data materialized from the last sync**.

## 12. IAM, Security, and Data Permissions

### 12.1. Identities to Distinguish

| Principal | Responsibility | Permission Type to Verify |
|---|---|---|
| Dataset owner | Create tables/features in BigQuery | BigQuery dataset/table write/schema management |
| Feature Store admin | Create online store/feature view/sync | Vertex AI Feature Store Admin or custom permissions |
| FeatureView service agent | Read BigQuery table during sync | BigQuery Data Viewer/`jobs.create` per setup |
| Cloud Run Java runtime SA | Fetch feature values | FeatureView online fetch permission in Vertex AI |
| Model-serving SA | Call model endpoint | Vertex AI endpoint predict permission |
| Auditor | Inspect metadata/logs/cost | Read-only permissions, no raw data access needed |

**Sync permissions differ from fetch permissions.** Granting BigQuery read to the runtime SA does not let FeatureView sync; granting Vertex AI read to the service agent does not let it query BigQuery tables. When resources span projects, configure IAM on the **exact target resource/project** and verify the real caller identity in logs.

### 12.2. Tenant Isolation and Sensitive Data

- **`customer_id` is not proof of ownership.** A service accepting IDs from HTTP clients must enforce tenant/user authorization before fetching.
- Never log full feature payloads containing customer info or sensitive inferences.
- Features touching health, credit, or sensitive behaviors need appropriate policies/consent, retention, fairness, and human review.
- Enforce schema/data minimization: expose only features the model genuinely requires.
- Connect to APIs over TLS with OAuth2 access tokens via ADC; never hardcode tokens or service account keys.
- If CMEK is required, check support on **Bigtable online stores**, KMS service agent permissions, and extra costs.
- Never assume deleting a BigQuery table purges all online copies, logs, and backups.

### 12.3. Environment Separation

Maintain separate online stores/feature views for **dev, staging, and prod**, tracking dataset/region/owner and data classification. When testing schema or feature ID changes, never touch a production view called by model serving. Feature Store serves production data; altering one column can break the entire inference path even while the model endpoint reports healthy.

## 13. Operations: Latency, Monitoring, Quotas, and Cost

### 13.1. Recommended Metrics/SLOs

| Metric | Purpose | Example Alert |
|---|---|---|
| **Online fetch p50/p95/p99** | Keep model requests fast | p95 exceeds SLO threshold |
| **QPS and HTTP error rate** | Catch traffic spikes, quota limits | Rising 429/5xx/timeouts |
| **Sync status and duration** | Ensure views refresh reliably | 2 consecutive sync failures |
| **Feature age / data freshness** | Avoid predicting on stale data | Source-to-online lag > budget |
| **Missing-feature ratio** | Validate entities/schemas | Abnormally high missing rate |
| **Feature distribution/drift** | Detect input shifts vs training | Spend/plan distribution diverges from baseline |
| **Online store CPU/nodes/storage** | Size Bigtable backend | Rapidly climbing capacity/billing |
| **Model inference p95/errors** | Measure full serving path | Model endpoint failing while feature fetch succeeds |
| **Billing by SKU** | Spot serving and BigQuery sync costs | Lab/team budget threshold exceeded |

**Low online read latency does not mean features are fresh or the model is accurate.** Dashboards should show at least three signals: source feature age, last successful sync, and online request latency.

### 13.2. Capacity and Scale Planning

Suppose Cloud Run receives **120 requests/second**, each needing one entity fetch and model inference. If Feature Store fetch averages **20 ms**, average in-flight fetches by Little's Law:

\[
L = \lambda W = 120 \times 0.02 = 2.4
\]

That is **average concurrency**, not headroom for spikes or p99 latency. Beyond Feature Store, requests also spend time in **auth, model inference, networking, serialization, and retries**. Load testing must measure end-to-end p99; never size Bigtable node counts from this formula alone.

### 13.3. Cost Surfaces

| Service | Cost Drivers | Optimization |
|---|---|---|
| BigQuery offline data | Storage, SQL queries/scans, historical snapshots | Partitioning/clustering, appropriate retention |
| Feature sync | BigQuery jobs and synced data volume | Schedule per freshness need, include only needed columns |
| FeatureOnlineStore Bigtable | Compute nodes/autoscaling, storage/reads per pricing | Rightsize min/max nodes, watch idle costs |
| Vertex AI/API | Feature serving ops and Vertex AI infra per SKU | Batching/budgets/quotas, avoid retry storms |
| Cloud Run/API service | Requests/CPU/memory/concurrency | Connection reuse, scale limits, timeouts |
| Model endpoint | Predict compute/endpoint usage | Cache where valid, autoscaling |
| Cloud Monitoring/KMS/network | Metrics, logs, encryption, traffic | Sampling, regional locality, data minimization |

**There is no fixed "per-feature" price across all architectures.** Bigtable online stores incur baseline costs when idle; scheduled syncs run BigQuery queries on cron. Check [Feature Store pricing](https://cloud.google.com/vertex-ai/pricing#featurestore), [BigQuery pricing](https://cloud.google.com/bigquery/pricing), and actual Cloud Billing.

### 13.4. Sync Schedule Change Runbook

1. Baseline end-to-end freshness, sync duration, online p95, and BigQuery cost.
2. Confirm source data update cadence; never sync every minute if features refresh daily.
3. Test the new cron on staging while watching BigQuery job quotas.
4. Change the schedule in isolation—never alter schedule + schema + model together.
5. Monitor source-to-online lag and sampled entity values across 2–3 sync cycles.
6. If costs spike or freshness misses targets, roll back config per the change record.
7. Document SLOs, owner, retention, missing-value policy, and deletion procedure.

## 14. Troubleshooting and Restoring Feature Services

### 14.1. Pinpointing Where the Fault Lies

~~~mermaid
flowchart TD
    A["Prediction API fails or features are stale"] --> B{"HTTP fetch error?"}
    B -->|"401 / 403"| C["Check ADC, runtime SA, Vertex AI IAM"]
    B -->|"404 / empty"| D["Check entity ID, view, sync, and data source"]
    B -->|"429 / 5xx"| E["Check quotas, store capacity, API logs; backoff"]
    B -->|"HTTP 200"| F{"Feature age/schema OK?"}
    F -->|"No"| G["Check BigQuery source, sync status, feature definitions"]
    F -->|"Yes"| H["Check model signature, preprocessing, and inference"]
    G --> I["Fix root cause, sync/rollback, re-canary"]
    H --> I
    C --> I
    D --> I
    E --> I
~~~

| Symptom | Common Cause | Verification / Fix |
|---|---|---|
| BigQuery source fails to sync | View service agent lacks BigQuery data/job rights | Dataset IAM, job permissions, identity |
| FeatureOnlineStore create 403 | Operator lacks Vertex AI permissions | IAM admin/custom role on exact project |
| Online fetch 403 | Cloud Run runtime SA lacks fetch permission | Runtime identity/permissions, API auth scope |
| Resource 404 | Wrong location/store/view or not Ready yet | Verify resource path and creation operation |
| Fetch returns nothing for entity | Key missing in BigQuery latest source | Entity ID, source rows, last sync |
| Fetch returns old value after UPDATE | Scheduled sync hasn't run or is failing | `FeatureViewSync` status and source |
| BigQuery row deleted, online still serves | **Bigtable FeatureView does not auto-delete entities** | Approved deletion runbook/view recreation |
| Direct source table has duplicate keys | Entity ID not unique | Pre-sync quality gate |
| Direct source has `feature_timestamp` and history | Violates direct source rules | Use Feature Registry, not direct source |
| Continuous sync skips UPDATEs | Syncs **new records only** | Use scheduled sync/recreate properly |
| Online NULL differs from offline NULL | Returns latest non-null historical value | Configure explicit dense/NULL policy |
| High online request latency | Store capacity, auth/network, load/QPS | p95/p99, node counts, quotas, retries |
| Bill rises despite low QPS | Online nodes/sync jobs keep running | Billing, min-node, and cron review |
| Model scores shift after sync | Feature version/types/units changed | Feature contract, model version, canary |
| Optimized store still running | Deprecated legacy option | Plan migration to Bigtable before sunset |

### 14.2. Read-Only Diagnostics

~~~bash
# Run after setting API_ROOT, ONLINE_STORE, FEATURE_VIEW.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW/featureViewSyncs"
~~~

Also inspect the source table in **BigQuery Studio** for **`customer_id`** and expected values. With real data, never paste raw features, tokens, or identifying IDs into support tickets. Record **correlation ID, timestamp, resource path, HTTP status, missing-field count, and model version**.

### 14.3. Runbook When Stale Features Corrupt Model Predictions

1. **Halt high-risk automated actions** or engage an approved fallback; never assume predictions remain valid.
2. Record **last successful sync**, source update timestamp, and online values for test entities.
3. Isolate whether the bug is in the BigQuery source pipeline, FeatureView sync, or model preprocessing.
4. If scheduled sync failed, fix IAM/quotas/source schema, trigger sync, and wait for success.
5. If business requires deleting an entity, block serving first; handle online deletion via the dedicated runbook.
6. Canary test entities, compare offline–online values, and inspect inference outputs.
7. Restore traffic and document incident/root cause plus guardrails to prevent recurrence.

**Never "fix" an incident by spinning up a second production online store** without knowing how clients will route traffic, absorb added cost, and clean up stale online data.

## 15. Case Study: Customer Support Recommendations on Cloud Run

### 15.1. Context

A SaaS business runs a Java backend on **Cloud Run**, stores login/spend data in **Cloud SQL**, streams events via **Pub/Sub**, and computes feature aggregations in **BigQuery**. The system predicts each account's support needs upon user login. SLOs: online feature fetch **p95 under 100 ms** (hypothetical target), features reflecting source within **30 minutes**, and model responses within API budgets.

**Design:**

- BigQuery stores **`customer_features_history`** for point-in-time training and **`customer_features_latest`** for serving.
- **Bigtable** Feature Store hosts a FeatureView with **scheduled sync** every 15 minutes as permitted by the BigQuery pipeline and freshness budget.
- Cloud Run runtime SA holds only fetch permission; a separate model-serving principal holds Vertex AI predict permission.
- Feature schema **`spend_30d`, `sessions_7d`, `plan`** is versioned with offline–online parity tests.
- API refuses predictions or uses a standardized fallback if feature age/missingness breaches thresholds.
- Dashboards track syncs, request latency, drift, model quality, and Cloud Billing.

### 15.2. Incident

On v2 rollout day, the model expects **`tickets_90d`**, yet FeatureView still returns only the three old features. Feature fetch returns HTTP **200**, while model prediction returns **400** due to a missing column.

**Analysis:** the online store is healthy; the fault is a **model–feature schema contract mismatch**. The fix is updating source pipelines/tables, creating or updating FeatureView v2, syncing, and canary-verifying the schema before shifting model traffic. Neither scaling Bigtable nodes nor granting Project Owner solves this.

### 15.3. Acceptance Criteria

| Criterion | Evidence |
|---|---|
| Point-in-time data correctness | Golden SQL tests across event/availability times |
| Valid entity keys | Unique IDs, no unexpected NULLs, tenant authorization |
| Stable sync | Zero sync failures, last sync within freshness budget |
| Online read meets SLO | p95/p99 + error rate/QPS under representative load |
| Schema matches model signature | Type/unit/feature-name/version tests |
| Offline–online values match | Sampling reconciliation after sync catch-up |
| Data deletion procedure exists | Serving blocked and cleanup verified |
| Least-privilege permissions | Read-only runtime, exact feature sync agent |
| Rollback ready | Active feature view/model versions retained |
| Costs within budget | BigQuery/Bigtable/Vertex AI/Cloud Run verified in Billing |

## 16. Practice Exercises and Answers

### 16.1. Exercise A — Comparing Feature Storage Options

**Question:** Choose the implementation for three cases: (a) train a model from 12 months of history, (b) fetch features by customer ID before online model inference, (c) find the 20 nearest documents by embedding.

**Answer:** (a) BigQuery history with point-in-time joins; (b) Bigtable FeatureOnlineStore/FeatureView; (c) Vertex AI Vector Search. An online FeatureView does not replace training history or ANN retrieval.

### 16.2. Exercise B — SQL Creating the Latest Source

Create three customers as in Section 5 and check count/unique IDs. If you insert **`customer_id=cust-101`** a second time with a different spend, what requirement breaks?

**Answer:** A direct BigQuery FeatureView source requires **unique entity IDs**; upstream must use **`MERGE`/`QUALIFY` by business timestamp** to produce a deduplicated latest table, never feeding multiple rows per customer to a direct source.

### 16.3. Exercise C — Point-in-Time and Late-Arriving Features

Customer **`cust-101`** makes a transaction at **09:00**, and the pipeline finishes computing it at **13:00**; the model predicts at **10:00**.

**Answer:** despite the 09:00 event time, the feature **must not be used at 10:00** because `available_at=13:00`. Point-in-time queries must enforce both `feature_timestamp` and `available_at` not after `prediction_time`.

### 16.4. Exercise D — Scheduled Sync and Lag

The BigQuery pipeline takes **5 minutes**, scheduled sync runs every **20 minutes**, and finishes in **3 minutes**. What is the approximate worst-case lag (ignoring failures)?

\[
5 + 20 + 3 = 28\ \mathrm{minutes}
\]

**Answer:** roughly **28 minutes**, excluding retries, queueing, and traffic spikes. For a sub-10-minute requirement, this architecture falls short; never merely lower the online fetch timeout and pretend freshness improved.

### 16.5. Exercise E — DELETEs Are Not Propagated

Delete **`cust-102`** from the BigQuery latest table and run a manual sync. What might the online FeatureView still return?

**Answer:** the **stale cached values** of `cust-102`, because Bigtable online serving does not purge entity records when syncing from BigQuery. Apply the deletion runbook and enforce serving access controls; BigQuery `DELETE` alone is insufficient.

### 16.6. Exercise F — Continuous Sync

A FeatureView uses continuous sync via Feature Registry. An operator updates a value on an existing BigQuery record and expects an online update.

**Answer:** wrong expectation: continuous sync syncs **new records only**, not updates/deletes to existing records. If updates/NULLs must propagate, pick scheduled sync/recreation with matching source config or evaluate direct write while accounting for Preview constraints.

### 16.7. Exercise G — Access Permissions

The Cloud Run SA has online fetch permission, yet FeatureView sync reports BigQuery Access Denied. Should you grant Vertex AI Admin to the Cloud Run SA?

**Answer:** no. The failure is on **sync identity → BigQuery source**. Identify the dedicated/default FeatureView service account and grant BigQuery data/job permissions; changing the Cloud Run SA will not fix sync.

### 16.8. Exercise H — Total Cost

An online store keeps Bigtable nodes running for only 10 requests/day; sync runs every minute executing BigQuery queries even though source data refreshes only every 6 hours.

**Answer:** review min nodes and whether an online store is even needed, lower sync frequency to match the actual freshness SLO, use BigQuery batch if online SLAs are unnecessary, and inspect Billing by SKU. Never delete a production store while apps still depend on it.

### 16.9. Sample Lab Report

~~~text
PROJECT_ID / LOCATION / DATASET / OWNER:
FEATURE_SOURCE_TABLE / ENTITY_ID_COLUMNS:
UNIQUE_ID_CHECK / NULL_CHECK:
POINT_IN_TIME_SQL_RESULT:
ONLINE_STORE_ID / TYPE / NODE_BUDGET:
FEATURE_VIEW_ID / SOURCE_URI / SYNC_CRON:
FEATURE_VIEW_SA / BIGQUERY_IAM / FETCH_IAM:
FIRST_SYNC_ID / FINAL_STATUS / LAST_SUCCESS:
FETCH_CUST_101 / FETCH_UNKNOWN_ENTITY:
BIGQUERY_UPDATE_VALUE / ONLINE_AFTER_SYNC:
FRESHNESS_SLO / ONLINE_P95 / MISSING_RATIO:
MODEL_SCHEMA_VERSION / CANARY_RESULT:
DELETION_RUNBOOK / RETENTION_POLICY:
COST_BREAKDOWN / CLEANUP / OPEN_ISSUES:
~~~

Report PASS only with real execution evidence. Without an authorized project, record **NOT_EXECUTED** for Cloud API steps rather than claiming online serving was deployed.

## 17. Lab Cleanup, Pre-Delete Checks, and References

### 17.1. Verifying Ownership

The example BigQuery table has a **7-day** expiration, yet **FeatureView and FeatureOnlineStore do not automatically disappear when the source table expires**. If your lab created a Bigtable online store, online compute/storage continues incurring charges. Never leave a store behind assuming BigQuery expiration will clean it up.

Before cleaning up, inspect:

~~~bash
# READ-ONLY: use exact lab project/location/online store/view.
curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"

curl -f -sS \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

bq --project_id="$PROJECT_ID" show \
  "$PROJECT_ID:feature_lab.customer_features_latest"
~~~

**Stop model-serving clients and scheduled sync consumers** before deleting a view, verify no other team shares the online store, and review retention/deletion policies.

### 17.2. Deleting Only Resources You Created (Destructive)

The commands below illustrate cleanup **on an owner-approved lab project**—never run in production. Record exact resource names and confirm before each step:

~~~bash
# REALLY DELETES the lab FeatureView and its online data.
curl -f -sS -X DELETE \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE/featureViews/$FEATURE_VIEW"

# ONLY after the view is completely deleted and the store has zero other views:
curl -f -sS -X DELETE \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "$API_ROOT/featureOnlineStores/$ONLINE_STORE"
~~~

Delete APIs can return **long-running operations**; poll until completion rather than assuming request acceptance purged online data immediately. Afterward, the DBA/data owner can delete the BigQuery table **`customer_features_latest`** and lab dataset if no dependencies remain. Never delete shared datasets, other teams' registry/feature groups, service agents, or shared KMS keys.

**Deletion note:** when fulfilling customer data deletion rights, verify BigQuery history, backups, other FeatureViews, model logs, serving caches, and legal policies—**never** rely solely on a `DELETE` against one resource.

### 17.3. Official Documentation

- [Feature Store overview — Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/overview)
- [Prepare BigQuery feature data source](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/prepare-data-source)
- [Online serving types and Optimized deprecation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/online-serving-types)
- [Create a FeatureOnlineStore](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-onlinestore)
- [Create a FeatureView and sync modes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/create-featureview)
- [Start a manual sync](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/sync-data)
- [List FeatureView sync operations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/list-data-syncs)
- [Serve feature values using Bigtable](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/serve-feature-values)
- [Direct write feature values — Preview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/featurestore/latest/featureview-direct-write)
- [BigQuery feature serving and point-in-time correctness](https://docs.cloud.google.com/bigquery/docs/feature-serving)
- [Vertex AI IAM access control](https://docs.cloud.google.com/vertex-ai/docs/general/access-control)
- [BigQuery security overview](https://docs.cloud.google.com/bigquery/docs/security-overview)
- [Google Cloud Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)

**Wrap-up checklist:** define feature contract → offline history + latest table → verify entity uniqueness → point-in-time training joins → choose **Bigtable online serving** → FeatureView + sync IAM → successful sync → fetch/validate schema → measure freshness and p95/p99 → establish deletion/rollback policies → monitor Billing → clean up by ownership.

**Connecting to the CLOUD_PROVIDERS_GCP track:** this lesson uses **BigQuery as the offline source**, **Vertex AI Feature Store** to materialize/serve features, **Bigtable** for online reads, and **Cloud Run Java API/Vertex AI model endpoints** for inference. IAM, VPC/secure access, Cloud Monitoring, and Cloud Billing form the cross-cutting operational layers. **Feature Store standardizes feature delivery, yet cannot fix skew, bad source data, wrong permissions, or missing deletion runbooks on its own.**

# Data Quality Rules and Data Quality Checking

A Java system on Cloud Run receives order events via Pub/Sub and pushes data into Cloud Storage and BigQuery for reporting. If the analytics table contains **duplicate order IDs**, **negative revenue violating business rules**, **missing sales regions**, or **late-arriving data**, dashboards still render—but business metrics are wrong.

**Data quality (DQ)** is the set of measurable criteria determining whether data is **complete, accurate, consistent, and timely for its intended use**. On Google Cloud, it can be implemented with **GoogleSQL on BigQuery**, **Dataform assertions**, or **Knowledge Catalog automatic data quality scans (Dataplex DataScan)**. These tools *detect and measure violations*; only when a workflow enforces a **quality gate** is bad data blocked from downstream steps.

This lesson belongs to the **Data Governance and Analytics** chapter of the `CLOUD_PROVIDERS_GCP` module. Examples connect project/IAM/VPC, Cloud Run, GKE, Cloud Storage, Pub/Sub, and BigQuery to design safe checks, release automation, SLO-driven operations, and cost management. Hands-on exercises use **mock data** in a lab project and never overwrite production tables.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **completeness, validity, uniqueness, consistency, timeliness/freshness**, and business reconciliation checks.
2. Translate business requirements into a **rule with an owner, scope, threshold, and failure action**.
3. Write GoogleSQL to validate data at row and table levels.
4. Configure **Dataplex DataScan data-quality** with built-in rules and pass thresholds.
5. Use **Dataform assertions** as quality gates in SQL workflows.
6. Design **quarantine, rerun/idempotency, schema drift, and freshness alerts**.
7. Protect bad records, service accounts, and scan results with IAM, auditing, and PII limits.
8. Measure defect rates vs. cost to decide when to sample versus full-scan.

## 1. Quality Checking Architecture in a Pipeline

~~~mermaid
flowchart LR
    SOURCE["Cloud Run / Cloud SQL<br/>Pub/Sub / GCS"] --> RAW[("BigQuery raw/landing")]
    RAW --> DQ["Quality rules<br/>SQL / DataScan / Dataform"]
    DQ -->|"Pass"| CURATED[("BigQuery curated")]
    DQ -->|"Fail"| HOLD["Quarantine + alert<br/>owner investigates"]
    CURATED --> BI["BI / ML / API"]
    DQ --> OBS["Run results + scores<br/>Knowledge Catalog / logs"]
~~~

Three concepts must remain distinct:

- **Validation:** checking whether a record or dataset satisfies a rule.
- **Profiling:** observing statistics such as NULL rates, value distributions, and min/max to *propose* rules; it does not infer business rules automatically.
- **Enforcement/gating:** deciding to **halt**, **quarantine**, or **warn** based on validation outcomes and severity.

A **passing scan** does not prove data is fit for every purpose. For instance, negative revenue might be invalid for `OrderCreated` yet valid for `RefundIssued`. Rules must be anchored to **business semantics and an owner**.

## 2. Quality Dimensions and Corresponding Rule Types

| Dimension | Question | Example Check |
| --- | --- | --- |
| **Completeness** | Are required fields missing? | `order_id IS NOT NULL` |
| **Validity** | Do values match type, range, and allowed sets? | `amount_vnd > 0`, region in APAC/EMEA/AMER |
| **Uniqueness** | Is a business key duplicated? | `COUNT(*) BY order_id <= 1` |
| **Consistency** | Do fields obey cross-field rules? | `paid_at IS NOT NULL` when `status='PAID'` |
| **Integrity** | Are references and relationships valid? | `customer_id` exists in customers table |
| **Timeliness/Freshness** | Does data arrive within the SLA? | Ingestion lag under 2 hours |
| **Accuracy** | Does data reflect real-world truth? | Reconciliation against source systems/payment records |
| **Volume/Anomaly** | Did row counts spike or drop abnormally? | Daily order count stays within expected bounds |

Accuracy **cannot be deduced** from a single table: an incorrect positive number passes `amount_vnd > 0`. You must reconcile against an **authoritative source** or independent verification process.

### 2.1. Every Rule Needs an Explicit Contract

Each production rule should record:

| Attribute | Example |
| --- | --- |
| ID and version | `orders.amount.positive.v1` |
| Owner / point of contact | Commerce Data Steward |
| Source / scope | `raw.orders`, single partition/day or full table |
| Expression | `amount_vnd > 0` |
| Threshold | **100%** for strict financial transactions |
| Severity | **BLOCKER** on violation; **WARN** for observational signals |
| Schedule / SLO | After every batch, prior to publishing curated |
| Failure handling | Halt publish, log metrics, notify owner, quarantine |
| Evidence | Run ID, query/job ID, violation count, rule version |

**A 99% threshold is not "good enough" for every case.** For transaction keys or security controls, even one violation may be unacceptable; for optional attributes, a softer threshold can make sense.

## 3. Row-Level Rules vs. Table-Level Aggregate Rules

**Row-level** rules evaluate each row individually, e.g., `amount_vnd > 0`, `region IN (...)`. Pass rate works as:

~~~text
pass_rate = passing_rows / total_rows
threshold = 1.0   → requires 100% of checked rows to pass
threshold = 0.98  → tolerates at most ~2% failing rows
~~~

**Aggregate/table-level** rules evaluate the whole dataset, e.g., `COUNT(*) > 0`, `MAX(ingested_at)` within SLA, or source-to-target row-count balance. Do not apply `passing_rows/total_rows` directly to every aggregate rule: pass/fail is determined at the **table level**.

Two common pitfalls:

1. **Empty input:** `COUNTIF(valid)=0` does not prove clean data if `COUNT(*)=0`. Add an explicit `COUNT(*) > 0` rule whenever data is expected.
2. **Wrong scan scope:** checking one day and concluding the whole table passed. Record the exact filter, partition, sampling, and run timestamp.

## 4. Lab: Mock Orders Table with Intentional Errors

Assume an approved lab project with billing and a dataset in `asia-southeast1`. In **BigQuery Studio**, set **Processing location = asia-southeast1**, and replace `PROJECT_ID` with your real project. Table identifiers in the SQL are backtick-quoted.

~~~sql
CREATE SCHEMA IF NOT EXISTS `PROJECT_ID.dq_lab`
OPTIONS (location = "asia-southeast1");

-- LAB ONLY: use a new table, never modify production tables.
CREATE TABLE IF NOT EXISTS `PROJECT_ID.dq_lab.orders_raw` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  event_date DATE,
  ingested_at TIMESTAMP
);

INSERT INTO `PROJECT_ID.dq_lab.orders_raw`
  (order_id, sales_region, amount_vnd, event_date, ingested_at)
VALUES
('o-1001', 'APAC', 120000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1002', 'EMEA',  95000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1003', 'APAC',  -5000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1004', 'APAC',  50000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
('o-1004', 'APAC',  50000, DATE '2026-11-18', CURRENT_TIMESTAMP()),
(NULL,     NULL,    30000, DATE '2026-11-18', CURRENT_TIMESTAMP());
~~~

The dataset intentionally has **6 rows** with three defect classes: missing `order_id` and `sales_region` in the last row, negative amount for `o-1003`, and duplicate key `o-1004` appearing twice. Values are illustrative; **do not repeat the `INSERT`** if you want to compare against expected counts.

| Check | Expected |
| --- | --- |
| Total rows | 6 |
| `order_id IS NULL` | 1 row |
| `amount_vnd <= 0` | 1 row |
| `sales_region` null / outside set | 1 row |
| Duplicate `order_id` key (excluding NULL) | `o-1004` has 2 rows |
| Fully valid and unique by `order_id` | Failed |

**Warning:** `CREATE TABLE IF NOT EXISTS` does not guarantee an empty table; re-running `INSERT` will inflate duplicates. Use a fresh lab dataset/table or clean up data in a controlled manner.

## 5. GoogleSQL: Aggregate Checks and Locating Invalid Records

Measure completeness and validity:

~~~sql
SELECT
  COUNT(*) AS total_rows,
  COUNTIF(order_id IS NULL) AS missing_order_id,
  COUNTIF(amount_vnd IS NULL OR amount_vnd <= 0) AS invalid_amount,
  COUNTIF(sales_region IS NULL
    OR sales_region NOT IN ('APAC', 'EMEA', 'AMER')) AS invalid_region,
  SAFE_DIVIDE(COUNTIF(order_id IS NOT NULL), COUNT(*)) AS id_completeness_rate
FROM `PROJECT_ID.dq_lab.orders_raw`;
~~~

Expected: `total_rows=6`, all three error counters equal `1`, `id_completeness_rate≈0.8333`. `SAFE_DIVIDE` prevents division by zero, though **NULL on empty tables must still be caught**.

Find duplicate keys:

~~~sql
SELECT order_id, COUNT(*) AS occurrences
FROM `PROJECT_ID.dq_lab.orders_raw`
WHERE order_id IS NOT NULL
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Expected: `o-1004 / 2`. To surface rows violating single-row conditions:

~~~sql
SELECT order_id, sales_region, amount_vnd, event_date
FROM `PROJECT_ID.dq_lab.orders_raw`
WHERE order_id IS NULL
   OR amount_vnd IS NULL OR amount_vnd <= 0
   OR sales_region IS NULL
   OR sales_region NOT IN ('APAC', 'EMEA', 'AMER');
~~~

The last query only detects **completeness/validity** errors; the two `o-1004` rows will not appear since both have valid amounts and regions. **Uniqueness must be checked separately** or combined using an analytic function.

### 5.1. Detecting Duplicates with a Window Function

~~~sql
WITH flagged AS (
  SELECT *,
    COUNT(*) OVER (PARTITION BY order_id) AS key_occurrences
  FROM `PROJECT_ID.dq_lab.orders_raw`
)
SELECT
  order_id, sales_region, amount_vnd,
  key_occurrences
FROM flagged
WHERE order_id IS NULL
   OR key_occurrences > 1
   OR amount_vnd IS NULL OR amount_vnd <= 0
   OR sales_region IS NULL
   OR sales_region NOT IN ('APAC','EMEA','AMER');
~~~

In the lab dataset, output includes `o-1003`, both `o-1004` rows, and the missing-ID row. If a team needs to **quarantine**, choosing "which row to keep" must rely on **event version, update timestamp, and trusted source**, never arbitrarily picking the higher amount.

## 6. BigQuery Constraints Do Not Replace Data Quality Checks

BigQuery supports declaring **NOT NULL** on schema columns, as well as **PRIMARY KEY / FOREIGN KEY NOT ENFORCED**. The difference:

- Column `NOT NULL` can block NULL inserts when enforced in a matching schema.
- `PRIMARY KEY ... NOT ENFORCED` and `FOREIGN KEY ... NOT ENFORCED` are metadata hints for query optimization; **BigQuery does not enforce uniqueness or referential integrity**.
- Pipelines, load jobs, transformations, or staging tables can still contain rule-violating values even when the schema is valid.

**Never declare an unverified primary key** and expect BigQuery to stop duplicates. You still need data quality tests, transformation/gating, and schema management.

## 7. Knowledge Catalog / Dataplex Automatic Data Quality

Google Cloud provides **automatic data quality** in **Knowledge Catalog** (APIs and CLI commands still use `dataplex`). A **DataScan** defines:

1. **Source:** typically a supported standard BigQuery table in the same location.
2. **Rules:** built-in (non-null, uniqueness, set/range, regex) or custom SQL.
3. **Scope:** full table, row filter, sampling, or incremental scan.
4. **Execution:** on-demand or scheduled.
5. **Results:** per-rule pass/fail, dimension scores, scan job history; optionally exported to BigQuery and published to Knowledge Catalog with appropriate permissions.

~~~mermaid
flowchart LR
    TABLE["BigQuery orders_raw"] --> SCAN["Dataplex DataScan<br/>rule YAML + scope"]
    SCAN --> JOB["Scan job"]
    JOB --> RESULTS["Pass/fail + quality scores"]
    RESULTS --> CAT["Knowledge Catalog scorecard"]
    RESULTS --> EXPORT["BigQuery results table"]
    RESULTS --> ALERT["Cloud Logging / alerts"]
~~~

**A DataScan does not automatically delete or fix bad rows.** Deciding whether to load `curated`, write to quarantine, or halt reporting belongs to the **pipeline/orchestrator**.

### 7.1. Built-In Rules vs. Custom SQL

| Rule Type | Example | Evaluation Scope |
| --- | --- | --- |
| `nonNullExpectation` | `order_id` required | Per row |
| `uniquenessExpectation` | `order_id` unique | Across column/rows |
| `setExpectation` | Region in allowed set | Per row |
| `rangeExpectation` | `amount_vnd` within bounds | Per row |
| `regexExpectation` | Code matches valid format | Per row |
| `rowConditionExpectation` | `amount_vnd > 0` | GoogleSQL boolean per row |
| `tableConditionExpectation` | `COUNT(*) > 0` | Single boolean at table level |
| `sqlAssertion` | Query returns invalid rows | Fails if **any row** is returned |

**About `threshold`:** applies only to **row-level rules** as the minimum passing ratio. `1.0` = 100%; omitting or setting `0` per API defaults to **1.0**, not "let every row pass."

## 8. Lab: Defining Rules in YAML

Create `dq-rules.yaml` **on your learner machine** (not in a project repository currently edited by another worker):

~~~yaml
rules:
  - name: id-not-null
    dimension: COMPLETENESS
    column: order_id
    nonNullExpectation: {}
    threshold: 1.0

  - name: unique-order-id
    dimension: UNIQUENESS
    column: order_id
    uniquenessExpectation: {}
    ignoreNull: true
    threshold: 1.0

  - name: positive-amount
    dimension: VALIDITY
    rowConditionExpectation:
      sqlExpression: "amount_vnd > 0"
    threshold: 1.0

  - name: allowed-region
    dimension: VALIDITY
    column: sales_region
    setExpectation:
      values: ["APAC", "EMEA", "AMER"]
    threshold: 1.0

  - name: has-rows
    dimension: COMPLETENESS
    tableConditionExpectation:
      sqlExpression: "COUNT(*) > 0"
~~~

**Expected:** `id-not-null`, `unique-order-id`, `positive-amount`, and `allowed-region` fail on the lab table, while `has-rows` passes. `ignoreNull` on a uniqueness rule does not replace a separate non-null rule.

To test **independently of wall-clock time**, use the mock table from Section 4 without adding "must be today" conditions. In production, add SLA-based freshness rules and account for timezones and late arrivals.

### 8.1. Creating and Running a Scan with `gcloud`

**Prerequisites:** a billed lab project, permissions to create/run DataScans, BigQuery/Dataplex APIs enabled, and an execution identity permitted to query the data.

~~~bash
gcloud services enable \
  dataplex.googleapis.com bigquery.googleapis.com \
  --project=PROJECT_ID

gcloud dataplex datascans create data-quality orders-dq-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --data-source-resource="//bigquery.googleapis.com/projects/PROJECT_ID/datasets/dq_lab/tables/orders_raw" \
  --data-quality-spec-file=dq-rules.yaml

gcloud dataplex datascans run orders-dq-lab \
  --project=PROJECT_ID --location=asia-southeast1

gcloud dataplex datascans jobs list \
  --datascan=orders-dq-lab \
  --project=PROJECT_ID --location=asia-southeast1
~~~

Take the **real `JOB_ID`** from `jobs list`:

~~~bash
gcloud dataplex datascans jobs describe JOB_ID \
  --datascan=orders-dq-lab \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --view=FULL
~~~

These commands **create resources/run scans with real charges** and are meant only for lab environments. If a scan with the same name exists from another exercise, verify its owner/config before overwriting. The `gcloud dataplex datascans ...` CLI still uses the Dataplex name even when Console labels it **Knowledge Catalog → Data profiling & quality**.

**Read results in two layers:** scan job **SUCCEEDED** only means the scan execution finished; **data quality `passed=false`** indicates that one or more rules failed. Never treat exit code 0 from `run` as proof that data quality passed.

## 9. Sampling, Incremental Scans, and Freshness

Full-table scans maximize coverage but can be costly on multi-billion-row tables.

| Scope | Benefit | Risk |
| --- | --- | --- |
| **Full scan** | Detects errors across all existing data | High scan volume, compute cost, and duration |
| **Row filter / partition** | Focuses on the batch/date ready for release | Does not verify historical data quality |
| **Sampling** | Lower cost and faster on large tables | Can miss rare errors or duplicate keys |
| **Incremental scan** | Checks new data via increasing timestamp/date | Misses backfills or edits to older rows unless accounted for |

Example rule scope on a date-partitioned table:

~~~yaml
# Add to data-quality spec when checking only a single lab day batch:
rowFilter: "event_date = DATE '2026-11-18'"
# samplingPercent: 25   # Do not use when strict uniqueness checks are required.
~~~

**This is a partial configuration snippet**, not a full replacement for `dq-rules.yaml`. `rowFilter` takes a **GoogleSQL WHERE** expression. Under sampling, uniqueness rules can miss duplicates; never loosen production thresholds arbitrarily based on samples.

### 9.1. Freshness and Completeness Are Separate SLOs

For continuous pipelines, you can write a freshness check:

~~~sql
SELECT
  COUNT(*) > 0 AS non_empty,
  MAX(ingested_at) >= TIMESTAMP_SUB(
    CURRENT_TIMESTAMP(), INTERVAL 2 HOUR
  ) AS fresh_enough
FROM `PROJECT_ID.dq_lab.orders_raw`;
~~~

`ingested_at` must reflect **actual arrival time** stamped by the ingestion system; do not trust client-editable timestamps from external sources. Because the lab table is inserted when doing the exercise, it can appear fresh even with an old `event_date`—that is **ingestion freshness**, not event timeliness.

**Distinguish:**

- **Data arrival freshness:** has new data landed in the warehouse recently?
- **Event timeliness:** how late is data arriving relative to when the business event occurred?
- **Processing completeness:** did all expected events/records arrive per manifest, offsets, or source counts?

A table with a recent `MAX(ingested_at)` could still be **missing 90% of records**; check volume and reconciliation separately.

## 10. Dataform Assertions: Quality Gates for SQL Workflows

**Dataform** fits teams modeling BigQuery in SQLX who want quality checks tied directly into the dependency graph. Common built-in assertions:

- `nonNull`: prevents required columns from being NULL.
- `uniqueKey` or `uniqueKeys`: prevents duplicate keys.
- `rowConditions`: logical expressions checked per row.
- **Manual assertion**: a query that returns **0 rows** when valid; returning any row **fails** the assertion.

Example in `definitions/orders_curated.sqlx` inside a **configured** Dataform workspace:

~~~sql
config {
  type: "table",
  assertions: {
    nonNull: ["order_id"],
    uniqueKey: ["order_id"],
    rowConditions: [
      "amount_vnd > 0",
      "sales_region IN ('APAC','EMEA','AMER')"
    ]
  }
}

SELECT order_id, sales_region, amount_vnd, event_date
FROM ${ref("orders_stage")}
~~~

`ref("orders_stage")` requires a source action/declaration in the **Dataform repository**; do not run this raw SQLX block directly in BigQuery Studio. When the workflow runs, Dataform generates assertions and can record failures in BigQuery assertion views; **assertions do not fix rows automatically** and do not turn BigQuery tables into enforced unique constraints.

### 10.1. Manual Assertion for Cross-Table Integrity

Create `definitions/order_customer_integrity.sqlx`:

~~~sql
config { type: "assertion" }

SELECT o.order_id
FROM ${ref("orders_curated")} o
LEFT JOIN ${ref("customers")} c USING (customer_id)
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
~~~

**This is an architectural example** requiring real `orders_curated(customer_id)` and `customers(customer_id)` tables. Any row returned fails the assertion. If the source has late-arriving customers, add a grace window or intentionally downgrade to WARN.

**Choosing tools:** Dataform assertions fit **SQLX BigQuery transformation pipelines**; Dataplex DataScan fits **centralized rule governance and data quality scorecards** even outside Dataform pipelines. You can combine both, while avoiding redundant full scans without clear purpose.

## 11. Building Quality Gates in Orchestration

~~~mermaid
flowchart TD
    INGEST["Ingest batch → staging"] --> SCAN["Run DQ checks"]
    SCAN --> CHECK{"BLOCKER rules pass?"}
    CHECK -->|Yes| RELEASE["Publish / MERGE into curated"]
    CHECK -->|No| HOLD["Halt downstream<br/>quarantine + alert"]
    HOLD --> FIX["Investigate / fix source"]
    FIX --> REPLAY["Rerun with original batch ID"]
    REPLAY --> SCAN
~~~

**Pipelines do not automatically "halt" just because a DataScan rule fails.** Gating requires explicit orchestration logic in **Workflows, Composer, Cloud Run, or Dataform dependencies**:

1. Run ingestion and record **batch ID, input object generation, and run ID**.
2. Trigger DQ scans/assertions and **wait for completion**.
3. Inspect **per-rule quality results**, separating blockers from warnings rather than reading only job status.
4. If a blocker fails, stop publishing to curated; store a safe report and raise an alert.
5. If checks pass, run idempotent transformations/`MERGE` into curated.
6. Support **backfills/reruns** keyed by business ID and traceable rule versions.

**Data quality gates do not replace upstream data contracts.** Early schema validation in Cloud Run or Pub/Sub consumers reduces defective records downstream.

## 12. Quarantine and Remediation: Never Silently Drop Data

A quarantine table can store **record keys, batch ID, source, error reason, and detection timestamp**, including payloads only when strict access controls apply. Never log raw PII or tokens into logs or DQ exports.

Simple lab example isolating violating rows:

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.dq_lab.orders_quarantine` (
  order_id STRING,
  sales_region STRING,
  amount_vnd INT64,
  event_date DATE,
  reason STRING
);

INSERT INTO `PROJECT_ID.dq_lab.orders_quarantine`
SELECT order_id, sales_region, amount_vnd, event_date,
  CASE
    WHEN order_id IS NULL THEN 'MISSING_ORDER_ID'
    WHEN amount_vnd IS NULL OR amount_vnd <= 0 THEN 'INVALID_AMOUNT'
    ELSE 'INVALID_REGION'
  END AS reason
FROM `PROJECT_ID.dq_lab.orders_raw`
WHERE order_id IS NULL
   OR amount_vnd IS NULL OR amount_vnd <= 0
   OR sales_region IS NULL
   OR sales_region NOT IN ('APAC','EMEA','AMER');
~~~

**This snippet does not automatically resolve duplicate `o-1004`.** Before publishing curated, run uniqueness checks and select the canonical record using reliable version/source timestamps.

Quarantine data needs **authorization, TTL/retention, and a clear remediation workflow**. After fixing, replay using a **consistent business ID/batch ID** so retries do not create duplicates. Never delete raw inputs prior to reconciliation and recovery readiness.

## 13. Monitoring Quality Scores, Failures, and Trends

With Knowledge Catalog DataScan, you can track:

- **Job history:** history of scan runs, durations, and execution statuses.
- **Rule-level results:** per-rule pass/fail and dimension scores.
- **Published quality scorecard** in Knowledge Catalog when enabled and permitted.
- **Exported results to BigQuery** for multi-period trend dashboards.
- **Cloud Logging/Monitoring alerts** when scans fail or quality scores/rules fail per supported setup.

**An aggregate score alone is not enough to publish data.** For instance, 99.9% quality with **one duplicated payment transaction** can still be a release blocker. Always track **critical rules** separately from averages.

| Signal | Example Action |
| --- | --- |
| DQ scan job FAILED | Investigate IAM/BigQuery quotas/network/API; do not assume bad data |
| DQ scan SUCCEEDED, quality FAILED | Investigate violating rows and ingestion source |
| Completeness drops from 99.9% to 90% | Halt curated publish or alert per severity |
| Uniqueness fails | Block `MERGE`; investigate duplicate publishers or retries |
| Freshness breaches SLA | Check source schedule/offsets, backlog, and ingestion progress |
| Volume drops 80% suddenly | Check missing partitions, schema drift, upstream outages |
| DQ score stable but row count tiny | Add non-empty/volume SLA to prevent "false greens" |

Use **Cloud Audit Logs** to track who edits rules, scan schedules, IAM, and schemas. When inspecting failing rows, query as an **authorized principal** honoring RLS/CLS/data masking; permission to view DataScan results does not authorize exporting raw PII into public reports.

## 14. IAM, Data Residency, and Information Protection

| Component | Permissions to Consider |
| --- | --- |
| Scan manager | `dataplex.datascans.create/update/delete` scoped appropriately |
| Scan runner | `dataplex.datascans.run` |
| Metadata/rule/result viewer | `dataplex.datascans.get` and `dataplex.datascans.getData` as needed |
| Execution identity reading BigQuery | `bigquery.jobs.create`, `bigquery.tables.get/getData` |
| Exporting results to BigQuery | Write permissions on destination dataset/table |
| Publishing scorecard to Knowledge Catalog | `bigquery.tables.update` and permission to use quality scorecard aspects |
| GCS external table sources | Appropriate bucket/object read permissions |

**Never grant project-wide `Owner/Editor` just because a scan throws `PERMISSION_DENIED`.** Identify the exact principal: the DataScan creator and **execution service account** can differ. Separate scan operations roles from sensitive data viewing, use managed service accounts on Cloud Run/GKE, and never bake JSON keys into source code.

**Data residency:** DataScans and BigQuery sources must align with supported regions/locations; export results to datasets matching location and residency rules. VPC Service Controls and organization policies may restrict access paths; never use public buckets or copy PII across regions to bypass controls.

## 15. Costs and Optimizing Scan Scope

DQ costs encompass both data-scanning compute and supporting overhead:

- **Knowledge Catalog/Dataplex automatic DQ** uses a **Dataplex Compute Unit (DCU)** model based on processing volume with minimum billing durations; using a **custom execution identity** may shift compute/storage charges to the **BigQuery project** per product rules.
- **BigQuery queries/Dataform assertions** bill under BigQuery on-demand bytes processed or slot reservations, plus storage.
- **Exported results, logs, and alerts** can incur storage, Logging, and Monitoring charges.
- **Multi-region/large-table scans** are affected by partitioning, clustering, sampling, rule complexity, and schedule frequency.

Example cadence choices:

| Dataset | Checks | Reasonable Cadence to Test |
| --- | --- | --- |
| New transactions every 5 minutes | Non-null, positive amount, uniqueness within new batch | After each batch, gating publication |
| Multi-billion-row table | Freshness, per-partition volume | Each new partition; periodic full scans |
| Customer master | Schema, email format, cross-references | On change and daily scan |
| Monthly financial close | Source-to-target reconciliation, sums/uniqueness | Before close, requiring 100% |

**Do not default to sampling for uniqueness or financial reconciliation:** checking 1% of data can easily miss rare defects. Before running full scans over tens of TB, inspect pricing, BigQuery byte estimates, quotas, and budgets. **Billing budget alerts are not hard spending caps.**

## 16. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Create DataScan fails | Missing `dataplex.datascans.create`, API disabled, wrong location | Verify project/region and permissions |
| Run DataScan fails with `PERMISSION_DENIED` | Execution SA lacks BigQuery job/table permissions | Check IAM of the execution principal |
| Scan job succeeds but rules fail | Data violates thresholds | Inspect rule results and failing-rows query |
| Scan scores high despite empty data | Missing `COUNT(*) > 0` / volume rule | Add table condition + source reconciliation |
| Uniqueness passes on sample | Sampling missed duplicates | Full/partition scan logic and business key |
| DQ SQL sees unexpected NULL behavior | `COUNTIF`, 3-valued SQL logic, NULL handling | Use explicit `IS NULL` checks |
| Accidentally scanned full table | Missing row filter/partition predicate | Set scope, verify bytes processed |
| Dataform assertion passes, report wrong | Rules too narrow or semantic mismatch | Add source reconciliation and owner review |
| Quality rules don't halt downstream | Quality gate not wired | Orchestration reads per-rule statuses |
| Rerun inserts duplicate rows | Append sink instead of idempotent MERGE | Batch ID/version + deduplication |
| Failing rows expose sensitive data | Debug query returns all columns | Restrict projection, IAM, masking/logging policies |
| Costs rise | Scans too frequent, full scans, too many query rules | Controlled partitioning/incrementals/sampling |

**Important:** DataScan can provide a **`failingRowsQuery`** for investigation, which may select **all columns** of the table. Never paste results into unprotected tickets or Slack channels; project only necessary columns when PII is present.

## 17. End-to-End Scenario: Trustworthy Revenue Reporting

**Context:** Java Order API → Pub/Sub → Dataflow/Cloud Storage → BigQuery raw. A finance dashboard reads a curated table every morning. Yesterday a provider sent duplicate records during retries; the pipeline still reported SUCCEEDED.

Improvement plan:

1. **Data contract:** enforce mandatory `order_id`, `amount_vnd > 0` for `OrderCreated`, valid regions, and stable event versions.
2. **Source validation:** API validates schemas; subscribers handle retries idempotently while retaining raw data for investigation.
3. **Daily DataScan:** run on newly arrived partitions checking non-null, validity, uniqueness, non-empty, and freshness.
4. **Quality gate:** if any finance-critical rule fails, block updates to curated/BI; alert with RunID/batch ID.
5. **Quarantine:** isolate invalid rows; resolve duplicate events using trusted source/event version rather than `MAX(amount)`.
6. **Dataform:** assertions on curated tables verifying totals, row counts, and referential integrity against primary sources.
7. **Observability:** report per-rule scores, freshness lag, quarantined row counts, and scan costs.
8. **Recovery:** fix source/logic, rerun with the same batch ID using `MERGE` to prevent duplicates, and retain audit records.

**Acceptance criteria:** zero duplicate records in curated, totals reconciled against source systems, data arriving within SLA, and every violation assigned an owner and remediation evidence. A "green" dashboard simply because SQL finished running **fails these criteria**.

## 18. Exercises and Self-Check

**Exercise 1 — SQL checks.** Run the three queries in Section 5 on the lab table.

*Pass:* 6 rows, 1 missing ID, 1 negative amount, 1 null region, `o-1004` appearing twice.

**Exercise 2 — Dataplex DataScan.** Create the YAML rules in Section 8 and run a scan in the lab project.

*Pass:* obtain `JOB_ID`; distinguish **job SUCCEEDED** from **data quality failed**, and identify which rules failed.

**Exercise 3 — Thresholds.** Change `positive-amount` threshold to `0.80`. What changes?

*Answer:* 5/6 rows have positive amounts so the rule can pass at 80%; the bad record still exists—only the **acceptance threshold** changed. Never apply this threshold by default in production finance.

**Exercise 4 — Quality gate.** Design Workflows/Composer so curated `MERGE` runs only after all BLOCKER rules pass.

*Pass:* both scan failures and data quality failures block publication, and logs record batch/run IDs.

**Question 5.** Does data profiling prove all values are business-valid?

*Answer:* No. Profiling describes distributions; rules and owners decide which values are acceptable.

**Question 6.** Does BigQuery `PRIMARY KEY NOT ENFORCED` automatically eliminate duplicates?

*Answer:* No. You must check and deduplicate in pipelines.

**Question 7.** Does DataScan automatically move bad rows to quarantine?

*Answer:* No. Scans measure and report violations; separate pipeline logic must enforce quarantine/gating.

**Question 8.** Do `nonNullExpectation` and `uniquenessExpectation` serve the same purpose?

*Answer:* No. One forbids missing values; the other forbids duplicate keys.

**Question 9.** Why can sampling be dangerous for uniqueness checks?

*Answer:* Duplicate occurrences may fall outside the sample, causing a false pass.

**Question 10.** Is there any contradiction between a scan job `SUCCEEDED` and a quality score `FAIL`?

*Answer:* No. The scan mechanics completed; the data violated the rules.

**Question 11.** Why doesn't freshness based on `ingested_at` prove events arrived on time?

*Answer:* It only reflects warehouse arrival time; you must also measure business timestamps and source-to-target latency.

**Question 12.** When does a Dataform manual assertion pass?

*Answer:* When the check query returns **0 violating rows**.

**Question 13.** Why might a high aggregate quality score still require a BLOCK?

*Answer:* A critical rule such as duplicate payments carries unacceptable risk that cannot be averaged away by other rules.

**Question 14.** Who should be permitted to view `failingRowsQuery` on a table containing PII?

*Answer:* Only principals with necessary data access; restrict outputs/logs and enforce masking/RLS.

## 19. Pre-Production Checklist

- [ ] Every critical dataset has an **owner, contract, schema/version, and freshness SLA**.
- [ ] Every rule has an ID, dimension, logic, threshold, severity, and failure action.
- [ ] Rules check **non-empty/volume** to prevent false passes on empty datasets.
- [ ] Critical uniqueness/reconciliation checks do not rely solely on sampling.
- [ ] DataScan scope, location, execution identity, and schedule are verified.
- [ ] Dataform assertions are wired into workflow/table dependencies when using SQLX.
- [ ] Quality gates distinguish **scan execution failures** from **data quality failures**.
- [ ] Quarantine has IAM, PII protection, TTL, and fix/rerun workflows.
- [ ] Reruns/backfills use business keys, batch IDs, and idempotent `MERGE`.
- [ ] Schema drift, late events, CDC/replays, and delayed data are handled.
- [ ] Alerts exist for critical rules, scan schedules, scores, and freshness.
- [ ] Failing-rows queries project only needed columns; never log secrets/PII.
- [ ] Rule/schema/IAM changes are audited, retaining rule versions and result history.
- [ ] DCU/BigQuery/Logging costs are measured against scan frequency and partitioning.
- [ ] Staging tests cover bad data, missing inputs, duplicates, NULLs, outages, and rollbacks.

## 20. Conclusion

**Data quality rules** turn "good data" from an opinion into **verifiable criteria**. On Google Cloud, use **BigQuery SQL** for precise investigation, **Dataform assertions** to guard SQL workflow models, and **Knowledge Catalog/Dataplex DataScan** to manage, scan, and track quality across tables at scale.

The concise production formula is: **data contracts → owned rules with thresholds → scoped scans → quality gates → quarantine/reconciliation → monitoring and cost optimization**. Never equate **job succeeded** with **data meets quality**.

## Official References

- [Knowledge Catalog: Automatic data quality](https://cloud.google.com/dataplex/docs/use-auto-data-quality)
- [BigQuery: Scan for data quality issues](https://cloud.google.com/bigquery/docs/data-quality-scan)
- [Dataplex DataQualityRule REST reference](https://cloud.google.com/dataplex/docs/reference/rest/v1/DataQualityRule)
- [Dataplex DataQualitySpec REST reference](https://cloud.google.com/dataplex/docs/reference/rest/v1/DataQualitySpec)
- [gcloud dataplex datascans create data-quality](https://cloud.google.com/sdk/gcloud/reference/dataplex/datascans/create/data-quality)
- [gcloud dataplex datascans run](https://cloud.google.com/sdk/gcloud/reference/dataplex/datascans/run)
- [gcloud dataplex datascans jobs list](https://cloud.google.com/sdk/gcloud/reference/dataplex/datascans/jobs/list)
- [Dataform: Test data with assertions](https://cloud.google.com/dataform/docs/test-data)
- [Dataform core reference](https://cloud.google.com/dataform/docs/reference/dataform-core-reference)
- [BigQuery constraints: NOT ENFORCED](https://cloud.google.com/bigquery/docs/primary-foreign-keys)
- [BigQuery GoogleSQL COUNTIF and SAFE_DIVIDE](https://cloud.google.com/bigquery/docs/reference/standard-sql/aggregate_functions)
- [Knowledge Catalog pricing](https://cloud.google.com/products/knowledge-catalog/pricing)
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing)

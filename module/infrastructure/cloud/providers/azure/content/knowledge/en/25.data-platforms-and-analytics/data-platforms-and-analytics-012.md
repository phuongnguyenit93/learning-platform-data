# Designing Data Quality, Partitioning, and Analytics Cost Optimization

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data services. The goal is to deploy, monitor, protect, and control the cost of an application architecture on Azure. Within the **Data Platforms and Analytics** chapter, this lesson connects three problems that always go together: **data quality**, **partitioning and storage layout for analytics**, and **processing/query cost (analytics cost)**.

Imagine an e-commerce company. Orders originate in Azure SQL Database, clickstream events arrive from the web application, and product details come from partner APIs. Data lands in **Azure Data Lake Storage Gen2 (ADLS Gen2)**, is cleansed and unified by a processing engine such as Azure Databricks, Spark/Synapse, or a compatible Azure/Fabric platform, and then powers revenue dashboards, refund reports, and model training datasets. Even a single `order_amount` column containing the string `"1,200"` instead of a decimal, a late event landing under the wrong date, or a query scanning the entire lake can simultaneously cause **wrong reports, missed SLAs, and inflated cloud bills**.

After completing this lesson, you will be able to:

- Design **data contracts**, checking schema, completeness, validity, uniqueness, consistency, freshness, and source traceability.
- Structure a **bronze → silver → gold** flow, deciding where to run quality checks and quarantine bad records.
- Handle **event time vs. ingestion time**, late-arriving events, CDC, duplicate events, and incremental/idempotent upserts.
- Choose **Parquet, Delta Lake, or an appropriate table format**; understand partition pruning, predicate pushdown, clustering, statistics, and file compaction.
- Select partition keys and granularity around real query patterns, avoiding over-partitioning, small files, and skew.
- Read/write partitions with **PySpark**, query with **SQL**, and distinguish general techniques from engine- or tier-specific features.
- Estimate **storage, compute, data scanned, pipeline orchestration, networking, monitoring, and retention costs** on Azure.
- Establish data quality gates, dashboards, alerts, runbooks, regression tests, and cost governance workflows.

## 1. Three Goals That Always Need Balance

A strong analytics platform is not merely fast at running queries. It must answer three questions at once:

| Goal | Question | Risk if ignored |
|---|---|---|
| **Correct data** | Are revenue, orders, and customer counts accurate and trustworthy? | Wrong dashboards, poor business decisions, loss of auditability |
| **Timely data** | Does the 08:00 report include all transactions up to the cutoff? | Missed SLAs, stale data, decisions made on incomplete snapshots |
| **Proportionate cost** | How much compute, bytes scanned, and storage does a report consume? | Full-lake scans, idle clusters running continuously, redundant copies |

These three goals can pull against one another: retaining all raw data forever aids auditing but consumes storage; partitioning per minute sounds great for filtering yet generates millions of small files; validating every field prior to ingestion can discard original evidence if the pipeline drops invalid data too early.

**Design principle:** raw data should be preserved per retention/compliance policy; quality should be validated at appropriate boundaries; serving tables should be tuned for specific query workloads; and costs must be measurable at every layer.

### 1.1. Reference Architecture

```text
Azure SQL Database       Web events        Partner API / files
      |                       |                     |
      +-----------------------+---------------------+
                              |
                              v
               Ingestion (ADF / Event Hubs / jobs)
                              |
                              v
               ADLS Gen2 — BRONZE (raw, replayable)
                              |
                    Schema/lineage checkpoints
                              |
                              v
             SILVER (typed, deduplicated, validated)
                    |                   |
                    | valid             | invalid
                    v                   v
            Clean Delta/Parquet       Quarantine
                    |
                    v
             GOLD (curated marts, aggregates)
                    |
           +--------+----------+
           |                   |
        SQL analytics       Power BI/ML/Apps
           |                   |
           +--------+----------+
                    |
             Azure Monitor + DQ + Cost Management
```

The names **bronze, silver, and gold** describe a logical organization (the medallion pattern), not a mandatory single SKU or engine. Azure offers multiple processing, querying, and reporting services; specific capabilities across Azure Databricks, Azure Synapse Analytics, Microsoft Fabric, ADF, Azure SQL, and table formats differ. Always verify **product, runtime version, tier, and region** before putting a command or optimization into production.

### 1.2. Business KPI Example

A `daily_paid_revenue` metric might require:

- Including only orders genuinely in **PAID** status, excluding PENDING.
- Applying the right **currency** and versioned FX conversion rules.
- Never double-counting the same `order_id` or payment event.
- Deducting refunds under an agreed accounting rule.
- Reporting by **business date** and a defined timezone.
- Having an explicit **data cutoff** timestamp and period finalization state.

Casting `amount` cleanly does not solve all of those requirements alone. You also need **metric contracts, data quality, time semantics, and lineage**.

## 2. Roles of Bronze, Silver, and Gold Layers

| Layer | Purpose | Characteristics | Example |
|---|---|---|---|
| **Bronze** | Capture raw evidence for replay/audit | Near-original payload, source metadata, batch ID, ingestion timestamp | Raw JSON/Avro/CSV events from Event Hubs |
| **Silver** | Standardize and enforce quality | Explicit data types, dedup, business keys, CDC/upserts, quarantine | `orders_clean` with `order_amount DECIMAL` |
| **Gold** | Serve consumer datasets and metrics | Aggregates, dimensional models, SCDs, BI data contracts | `daily_revenue_by_region` |

### 2.1. Why Avoid Editing Bronze Directly?

If a pipeline overwrites raw events in place, fixing a faulty v2 schema parser later makes replaying or proving the original input difficult. Bronze should be **append/immutable by design where possible**, backed by security, retention, and provenance policies. Do not store raw data indefinitely if privacy regulations require deletion or expiration; immutability must be designed alongside data lifecycle and data subject rights.

### 2.2. Silver Is More Than Renaming Columns

Silver typically performs:

1. Parsing payloads according to schema and version.
2. Standardizing `decimal`, `timestamp`, and business key types.
3. Distinguishing valid nulls from malformed-value nulls.
4. Deduplicating by event ID or appropriate business key + version.
5. Applying CDC/upsert/delete logic in proper version order.
6. Routing invalid records to **quarantine** with reason codes.
7. Emitting metrics and checkpoints for row counts, freshness, and error rates.

Never silently coerce an invalid numeric value to `0`: doing so fabricates revenue figures while erasing the error trail.

### 2.3. Gold Is the Serving Contract

Gold can contain daily/weekly aggregates, star schemas, semantic models, or feature tables. Rules for refunds, taxes, FX rates, and timezones must align with business owners. Changing a KPI definition requires **versioning, lineage, testing, and consumer notification**.

### 2.4. Replay and Repeatability

A well-designed pipeline can replay the `2026-11-19` batch **without doubling counts**. Raw events should carry an identity, offset, or ingestion batch ID; silver upserts should rely on keys and versions; gold writes should use transactions, partition overwrites, or merges appropriately. Never treat “job succeeded” as proof that no rows were duplicated.

## 3. What Is Data Quality? Key Measurement Dimensions

**Data quality (DQ)** means data meets the conditions required for its intended use. Checks cannot be applied identically to every table: an email in a marketing table and an amount in an accounting ledger have different requirements.

| Quality dimension | Definition | Check example |
|---|---|---|
| **Completeness** | Required records and fields are present | Share of `order_id IS NOT NULL`; all reporting-period partitions exist |
| **Validity** | Values match format, range, and domain rules | `amount >= 0` on sales rows per business rule |
| **Uniqueness** | No duplicates on keys meant to be unique | Unique `order_id` in current orders snapshot |
| **Consistency** | No contradictions across sources, tables, or rules | Item sums match order total within tolerance |
| **Accuracy** | Values match real-world/authoritative sources | `paid_amount` matches the reconciled payment ledger |
| **Timeliness/Freshness** | Data arrives fast enough for its purpose | Today’s partition updated within 15 minutes |
| **Referential integrity** | Foreign keys exist within valid scope | Every `order_item.product_id` maps to a valid product |
| **Integrity/Lineage** | Origin and transformations are traceable | `source_file`, `run_id`, `schema_version` |

**Accuracy** usually cannot be verified by a SQL expression against a single table: it requires comparing against an independent source, performing reconciliation, or conducting sample reviews with business owners.

### 3.1. Every DQ Rule Needs an Owner and Severity

Example:

| Rule | Severity | Action |
|---|---|---|
| `order_id` null | Blocker for silver orders | Quarantine row, do not publish to gold |
| Unparseable amount string | Blocker for financial transactions | Quarantine + open incident |
| Unsupported `currency` | Contract blocker | Quarantine / reconcile |
| Missing `country_code` in clickstream | Warning if fallback exists | Record metric, monitor |
| Freshness > 30 minutes | SLA breach | Alert; hold period close until complete |
| Regional order distribution shifts 40% from baseline | Anomaly | Investigate; never auto-delete data |

Include **rule ID, version, owner, logic, threshold, severity, action, affected dataset, and recovery procedure**. A data test with no defined failure action merely produces colorful charts.

### 3.2. Data Quality Is Context-Dependent

In a `payments` table, a negative amount might be invalid. In a `ledger_entries` table, negative amounts may legitimately represent debits or refunds. Never copy `amount >= 0` blindly across every table without checking the business contract.

### 3.3. Distinguishing Data Bugs from Market Shifts

A sudden 40% revenue drop could stem from:

- Dropped ingestion data.
- Changed business logic or filters.
- Timezone mismatches.
- The end of a promotional campaign.
- A real operational or economic event.

Anomaly detection requires **context and drill-down capability**, never automatically adjusting figures to match a “historical average.”

## 4. Data Contracts and Schema Evolution

A **data contract** is an agreement between producer and consumer covering structure, semantics, quality expectations, and update schedules.

Example order contract:

```yaml
dataset: orders_events
contractVersion: 2
owner: commerce-platform
businessTimezone: Asia/Ho_Chi_Minh
primaryEventId: event_id
eventTimeColumn: event_time_utc
fields:
  event_id: string_not_null
  order_id: string_not_null
  event_type: enum[OrderCreated,OrderPaid,OrderRefunded]
  amount: decimal_18_2_nullable
  currency: iso_currency_code
  event_time_utc: timestamp_utc
freshnessSlaMinutes: 30
retentionPolicy: follow_dataset_governance
```

This is a **conceptual contract template**, not a standard schema natively interpreted by an Azure service. In production systems, rules must be translated into executable schemas/validations and versioned in the appropriate repository or catalog.

### 4.1. Schema Drift and Breaking Changes

| Change | Common impact | Handling strategy |
|---|---|---|
| Add optional field | Potentially backward-compatible | Update schema, test consumers |
| Change `amount` from decimal to string | Likely breaking | Version contract and run migration |
| Rename `order_id` without alias | Breaking for consumers | Provide deprecation window |
| Change timezone without updating contract | Wrong date partitions | Update contract + run verified backfill |
| Add new event type | Consumer may fail to handle it | Define explicit unknown-type handling |
| Remove required field | Breaking | Coordinate producer/consumer rollout |

**Table-format schema evolution does not equal business compatibility.** Just because an engine allows adding a column does not guarantee Power BI measures, downstream jobs, or historical comparisons remain valid.

### 4.2. Schema Validation Before or After Ingest?

If you validate too early and **drop invalid events before writing raw**, auditing becomes difficult. Usually it is safer to land bronze per policy, tag the schema parse status, and validate strictly into silver. However, malicious, oversized, or secret-bearing payloads should not be ingested unconditionally; **ingress security and PII protection** still apply prior to storage.

### 4.3. Time Contracts: UTC and Business Date

Store `event_time_utc` as a UTC timestamp with explicit timezone semantics. When reporting in Vietnam time:

```text
event_time_utc = 2026-11-19 17:30:00Z
business_time  = 2026-11-20 00:30:00 Asia/Ho_Chi_Minh
business_date  = 2026-11-20
```

Never slice a date by substringing a raw timestamp string and assuming it represents the business day. Account for timezones and daylight-saving transitions where applicable in other markets.

## 5. Metadata, Lineage, and Ownership

Every critical dataset should define:

- **Owner:** team accountable for accuracy and source data.
- **Steward:** person/process approving business definitions and classifications.
- **Schema/contract version:** change tracking.
- **Lineage:** source → job → table → dashboard.
- **Freshness and retention:** SLA needs and lifecycle rules.
- **Classification:** PII, confidential, public, financial.
- **Quality scores and incidents:** trust level, incident dates, and root causes.

Tools such as **Microsoft Purview** and platform-native catalog/metadata features can support cataloging, lineage, and policy within their supported integration scope. Do not assume custom pipelines are automatically traced end-to-end simply by enabling a catalog.

### 5.1. Raw Data Also Needs Access Controls

Bronze may hold PII, malformed payloads, and sensitive partner data. Enforce:

1. **Entra ID/RBAC and ADLS Gen2 ACLs** scoped to actual access paths.
2. Private networking/TLS and encryption at rest per policy.
3. Least-privilege managed identities or service principals for pipelines.
4. Retention, deletion/data subject requests, and access auditing.
5. Never writing credentials into notebook or job logs.

Never copy raw data into a wide-open analytics workspace just for convenience during a quality investigation.

## 6. Turning DQ Rules into “Quality Gates”

A **quality gate** is a checkpoint with an explicit decision on whether data may proceed downstream:

```text
Incoming batch
     |
     v
Bronze ingest + source metadata
     |
     v
Schema validation
     |
     +-- Parse fail --> quarantine/error log
     |
     v
Type + domain checks
     |
     +-- Invalid --> quarantine + row-level reason
     |
     v
Uniqueness + reconciliation
     |
     +-- Fail threshold --> halt publish or warn
     |
     v
Silver commit
     |
     v
Gold aggregate + cross-table tests
     |
     v
Publish dashboard / watermark only after PASS
```

### 6.1. Fail-Closed or Warn-Only?

| Dataset | Recommendation | Rationale |
|---|---|---|
| Official payments/revenue | Fail/hold partition on severe errors | Prevent publishing incorrect financial figures |
| Exploratory clickstream | Quarantine invalid events while letting valid rows proceed | Avoid letting a few broken records block all telemetry |
| Customer privacy flags | Fail-closed for sensitive data/consent | Prevent missing consent from causing unauthorized usage |
| Real-time “estimated” dashboard | Publish with freshness/completeness badge per contract | Inform users that numbers are not yet final |

Thresholds must reflect **business impact**. For example, “allow 1% errors” is unsafe if that 1% consists entirely of high-value orders.

### 6.2. Row-Level and Batch-Level Checks

- **Row-level:** nulls, regex, enums, ranges, timestamp parsing.
- **Batch-level:** sufficient record count, uniqueness rate, max timestamp, source completeness.
- **Cross-dataset:** order totals match payments/refunds across the reconciliation window.
- **Temporal:** order count distribution, late event rate, anomalous shifts.

Store **valid/invalid counts, denominators, rule versions, `run_id`, data date, and source files**. A 99.9% pass rate without sample size is easily misleading.

### 6.3. Quarantine Instead of Losing Data

```text
quarantine/orders_events/
  ingest_date=2026-11-20/
    invalid-records-00001.parquet
```

Quarantined records should include `reason_code`, `source_identifier`, `ingest_time`, `raw_event_id`, and replay metadata per policy. Avoid dumping full PII into error traces; quarantine storage needs security equal to or stricter than bronze.

## 7. Checking Data Quality with SQL

Assume a silver table with schema:

```text
orders_clean(
  order_id STRING,
  customer_id STRING,
  status STRING,
  amount DECIMAL(18,2),
  currency STRING,
  event_time_utc TIMESTAMP,
  business_date DATE,
  source_version BIGINT
)
```

These SQL snippets illustrate **conceptual analytics SQL**. Column/function names, table qualifiers, and `DATE`/`CAST` syntax must be adapted to Spark SQL, Synapse SQL, Azure SQL, or your target warehouse engine.

### 7.1. Checking Completeness

```sql
SELECT
  COUNT(*) AS total_rows,
  SUM(CASE WHEN order_id IS NULL THEN 1 ELSE 0 END) AS null_order_ids,
  SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END) AS null_customers
FROM orders_clean
WHERE business_date = DATE '2026-11-20';
```

If `total_rows=0`, never report 100% completeness by defaulting zero division to zero errors. **Mark the state as `NO_DATA`**, and cross-check source expected counts, batch arrival, and business schedules.

### 7.2. Checking Uniqueness

```sql
SELECT order_id, COUNT(*) AS row_count
FROM orders_clean
WHERE business_date = DATE '2026-11-20'
GROUP BY order_id
HAVING COUNT(*) > 1;
```

**Verify the business grain:** if the dataset is an **event history**, an `order_id` validly appears multiple times across status transitions; uniqueness should instead check `event_id` or `(order_id, source_version)`. If it is a **current snapshot**, `order_id` may need to be unique across the whole table, not just within a single day.

### 7.3. Checking Domain and Range

```sql
SELECT COUNT(*) AS invalid_rows
FROM orders_clean
WHERE status NOT IN ('CREATED', 'PAID', 'REFUNDED', 'CANCELLED')
   OR currency NOT IN ('VND', 'USD', 'EUR')
   OR amount IS NULL
   OR (status = 'PAID' AND amount < 0);
```

This is an illustrative rule only. `REFUNDED` might be stored as a negative number or a positive refund amount depending on the ledger model. Business owners must sign off before enabling hard gates.

### 7.4. Detecting Missing Foreign References

```sql
SELECT o.order_id, o.customer_id
FROM orders_clean o
LEFT JOIN customers_clean c
  ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

If customer records arrive later than orders, referential mismatches may be **temporary**. Define allowed lag, watermarks, gate timing, and reconciliation workflows rather than deleting orders immediately.

### 7.5. Reconciling Totals and Counts

```sql
SELECT
  business_date,
  COUNT(*) AS order_count,
  SUM(amount) AS gross_amount
FROM orders_clean
WHERE status = 'PAID'
  AND business_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-20'
GROUP BY business_date
ORDER BY business_date;
```

Reconcile against the authoritative source using matching **metric definitions, FX, tax, refunds, timezone, and cutoff**. Row counts from a source CDC feed naturally differ from a current snapshot table; never compare two incompatible concepts and assume a bug.

### 7.6. Measuring Late-Arriving Data

If both `event_time_utc` and `ingest_time_utc` exist:

```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE
      WHEN ingest_time_utc > event_time_utc + INTERVAL 30 MINUTES
      THEN 1 ELSE 0 END) AS late_over_30m
FROM bronze_order_events
WHERE ingest_date = DATE '2026-11-20';
```

`INTERVAL` syntax varies by engine. What matters is measuring the **distribution of lateness** and setting source-appropriate thresholds rather than treating late events as corrupt by default.

## 8. PySpark: Normalizing, Splitting Invalid Rows, and Emitting Metrics

This example can run on a compatible **Spark runtime** (Azure Databricks, Synapse Spark, or another authorized Spark environment with storage access). It illustrates analytical logic; update source paths, schemas, timezones, dependencies, and security controls for your workspace.

### 8.1. Sample Input

```json
{"event_id":"evt-001","order_id":"ORD-1","amount":"120000.50","currency":"VND","status":"PAID","event_time_utc":"2026-11-20T01:23:00Z"}
{"event_id":"evt-002","order_id":null,"amount":"abc","currency":"VND","status":"PAID","event_time_utc":"2026-11-20T01:24:00Z"}
{"event_id":"evt-003","order_id":"ORD-2","amount":"90000","currency":"USD","status":"CREATED","event_time_utc":"2026-11-20T01:25:00Z"}
```

The second record contains two errors. The pipeline must not coerce `abc` into `0` and silently feed it into revenue.

### 8.2. PySpark Transformation

```python
from pyspark.sql import functions as F, types as T

# Spark session already initialized in an authorized environment.
spark.conf.set("spark.sql.session.timeZone", "UTC")

input_path = "abfss://bronze@STORAGE_ACCOUNT.dfs.core.windows.net/orders/events/"

schema = T.StructType([
    T.StructField("event_id", T.StringType(), True),
    T.StructField("order_id", T.StringType(), True),
    T.StructField("amount", T.StringType(), True),
    T.StructField("currency", T.StringType(), True),
    T.StructField("status", T.StringType(), True),
    T.StructField("event_time_utc", T.StringType(), True),
])

raw = spark.read.schema(schema).json(input_path)

typed = (
    raw
    .withColumn("amount_decimal", F.expr("try_cast(amount as decimal(18,2))"))
    .withColumn("event_ts", F.to_timestamp("event_time_utc"))
    .withColumn("business_date",
                F.to_date(F.from_utc_timestamp("event_ts", "Asia/Ho_Chi_Minh")))
    .withColumn(
        "reason_code",
        F.when(F.col("event_id").isNull(), F.lit("MISSING_EVENT_ID"))
         .when(F.col("order_id").isNull(), F.lit("MISSING_ORDER_ID"))
         .when(F.col("amount_decimal").isNull(), F.lit("INVALID_AMOUNT"))
         .when(F.col("event_ts").isNull(), F.lit("INVALID_TIMESTAMP"))
         .when(~F.col("currency").isin("VND", "USD", "EUR"),
               F.lit("UNKNOWN_CURRENCY"))
         .when(~F.col("status").isin("CREATED", "PAID",
                                    "REFUNDED", "CANCELLED"),
               F.lit("UNKNOWN_STATUS"))
    )
)

valid = (
    typed.filter(F.col("reason_code").isNull())
    .select("event_id", "order_id",
            F.col("amount_decimal").alias("amount"),
            "currency", "status",
            F.col("event_ts").alias("event_time_utc"),
            "business_date")
)
invalid = typed.filter(F.col("reason_code").isNotNull())

print("valid_rows =", valid.count())
print("invalid_rows =", invalid.count())
```

**Portability note:** `try_cast` and ISO-8601 timestamp parsing require a compatible Spark SQL version; some runtimes behave differently under ANSI mode. Always test against real source values, malformed strings, and timezones rather than assuming identical behavior across every PySpark runtime.

`reason_code` in this snippet stores only **the first failing rule** in priority order. A complete DQ framework can capture an array of all failed rules and separate record-level quarantine from batch-level gate failures.

### 8.3. Writing Silver and Quarantine

```python
silver_path = "abfss://silver@STORAGE_ACCOUNT.dfs.core.windows.net/orders_clean"
quarantine_path = (
    "abfss://quarantine@STORAGE_ACCOUNT.dfs.core.windows.net/orders_events"
)

# Illustrative append only for already-deduplicated event data.
# Production requires idempotent merge/checkpointing by event_id/source_version.
valid.write.format("parquet").mode("append").partitionBy(
    "business_date"
).save(silver_path)

invalid.write.format("parquet").mode("append").save(quarantine_path)
```

**Never re-run this append snippet repeatedly on the same batch without idempotency**: it will create duplicate records. In production, use source offsets/checkpoints or `MERGE` on a suitable transactional table format with transaction logs and batch deduplication.

### 8.4. Publish Gate Based on Invalid Ratio

```python
total_rows = typed.count()
invalid_rows = invalid.count()

if total_rows == 0:
    raise RuntimeError("NO_DATA: expected batch has zero rows")

invalid_ratio = invalid_rows / total_rows
threshold = 0.005  # 0.5% is an illustrative threshold only

if invalid_ratio > threshold:
    raise RuntimeError(
        f"DATA_QUALITY_GATE_FAILED invalid_ratio={invalid_ratio:.4f}"
    )
```

**Production execution order must be engineered carefully:** the snippet above writes outputs before running the gate, so **do not use it verbatim to control publishing**. Compute quality metrics and evaluate the gate **before committing/publishing to silver/gold**, or write to staging and perform an **atomic promote/swap/merge** only when the gate PASSES. If a gate fails after partial writes, you need checkpoints, rollback, or replay so low-quality data is never exposed.

### 8.5. Optimizing the Cost of DQ Checks Themselves

Calling `count()` multiple times in the snippet triggers repeated Spark jobs and scans. Production pipelines should:

- Compute multiple rule metrics in **a single aggregation pass** whenever possible.
- Cache/persist an intermediate DataFrame **only when beneficial**, and remember to unpersist it.
- Inspect the Spark execution plan and input scan size.
- Separate lightweight schema checks from heavyweight reconciliations where practical.
- Publish only after gating instead of re-scanning the entire lake endlessly for the same batch.

Data quality checks should never become an uncontrolled cost driver.

## 9. Event Time, Processing Time, and Late-Arriving Data

**Event time** is when an action occurred; **ingestion/processing time** is when the pipeline saw the data. The two can diverge due to offline mobile apps, queue backlogs, retries, API batch imports, or network outages.

```text
Event A occurred:     2026-11-19 23:58 +07
Event A ingested:     2026-11-20 00:10 +07

event_business_date   = 2026-11-19
ingestion_date        = 2026-11-20
```

If you partition by `ingestion_date` while reporting by `business_date`, late events from an earlier day land inside newer folders. Understand clearly **which predicates your partition key prunes against** and define a strategy for backfilling or restating prior periods.

### 9.1. Watermarks in Stream Processing

A stream processor can use a **watermark** to bound how long state is retained for event-time operations and handle late events per policy. Example:

```python
from pyspark.sql import functions as F

events = (
    input_stream
    .withWatermark("event_time_utc", "30 minutes")
)
```

This is a **code fragment** assuming `input_stream` is a streaming DataFrame with a valid timestamp column. A watermark does not automatically guarantee every event delayed over 30 minutes is dropped across all operators; exact behavior depends on **the operator, stateful aggregation/dedup, and microbatch progression**. Read your runtime’s semantics and test with late and out-of-order events.

### 9.2. Do Not Close the Day Too Early

A daily revenue report can adopt explicit states:

- **Preliminary:** provisional figures before all late events arrive.
- **Finalized:** period closed after the business-approved watermark/cutoff.
- **Restated:** closed period updated after delayed refunds/adjustments with report versioning.

Dashboards should display **data-as-of/cutoff timestamps and finality status**, rather than silently rewriting history and puzzling consumers over shifting numbers.

### 9.3. Aligning Partitioning and Late Adjustments

If partitioned by `business_date`, a refund arriving next month for an order placed last month could either:

- Be booked as a **current-day** refund event in the ledger.
- Or update the historical order snapshot for the old date.

This is a **semantic model decision**, not a single technical default for every report. Partitioning rules, gold metrics, and backfills must align with accounting definitions.

## 10. CDC, Incremental Loads, and Deduplication

**Change Data Capture (CDC)** captures insert/update/delete changes from sources such as databases (per supported features). A typical CDC pipeline looks like:

```text
source_database
   |
   | change log/CDC connector
   v
Bronze change events (op, PK, sequence, timestamp)
   |
   v
Dedup/order + schema validation
   |
   v
Silver current snapshot (upsert/delete)
   |
   v
Gold aggregates / change propagation
```

### 10.1. Event ID and Source Sequence

A CDC change payload might look like:

```json
{
  "source_table": "orders",
  "pk": "ORD-1042",
  "operation": "UPDATE",
  "source_sequence": 881243,
  "source_commit_time": "2026-11-20T10:15:00Z",
  "status": "PAID"
}
```

`source_sequence` is only meaningful within the **ordering scope** guaranteed by the connector (database, table, partition, or log stream). Never assume every source gives a globally monotonic sequence. When updating snapshots, compare version/sequence carefully so an older delayed event **never overwrites a newer state**.

### 10.2. Duplicate Delivery Is Normal

An ingestion job may retry after a timeout and re-emit an event already written to bronze. Therefore:

- Bronze may contain duplicates with the same `event_id` for audit/replay.
- Silver should deduplicate by event ID or key + version appropriately.
- Gold should perform **idempotent** incremental aggregation so revenue is never counted twice.
- Checkpoints should advance only after the batch write commits safely.

Never apply `dropDuplicates(["order_id"])` blindly to an event history table, as it will discard legitimate state transitions for the same order.

### 10.3. Deletes and Tombstones Must Be Handled

CDC streams can emit `DELETE` / tombstone records. If a pipeline only upserts INSERTs and UPDATEs, gold tables retain deleted rows or violate privacy deletion obligations. Define explicitly:

- Hard vs. soft delete semantics.
- Retention, time travel, and vacuum policies.
- How deletions propagate to downstream tables, caches, search indexes, and BI.
- Ownership and workflows for handling data subject deletion requests.

**Deleting a row in gold does not prove raw copies, backups, or time-travel versions were handled properly**; full lifecycle policies are required.

## 11. Idempotent Batch Processing

Suppose ADF/Spark re-runs the `2026-11-20` batch because a previous run timed out after writing files but before signaling completion. If writes are un-deduplicated appends, order counts can double.

### 11.1. Batch ID Tracking Pattern

```text
source: orders-events
batch_id: 2026-11-20T10:00Z-batch-0042
file_manifest: [file-a, file-b, file-c]
checkpoint: source offset/version
target: silver.orders_clean
status: PENDING -> VALIDATED -> COMMITTED
```

Persist batch/control state **durably** with unique keys so any batch replay converges cleanly without duplicating results.

### 11.2. Transactional Table Formats

Table formats like **Delta Lake** (where supported by the engine) provide a transaction log alongside `MERGE`/overwrite semantics for atomic commits and upserts. However, **the table format does not know logical event identity automatically** or eliminate all duplicates on its own. You still must define primary/business keys, deduplication rules, concurrent write isolation, and checkpoints.

### 11.3. Running Backfills Without Breaking Fresh Data

Backfilling 6 months of data requires:

1. Defining target partition scope and transformation code version.
2. Understanding how live incremental/streaming updates touch the dataset.
3. Avoiding overwrites that wipe out live events arriving during the backfill.
4. Using staging, validation, and atomic swap/merge patterns.
5. Recomputing dependent gold metrics or materialized views where required.
6. Tracking backfill costs separately so they do not skew daily job baselines.
7. Recording audit run IDs, before/after row counts, and a rollback plan.

Never run a full-table `overwrite` in production just to fix one historical partition.

## 12. What Is Data Partitioning and Why Use It?

In a data lake, **partitioning** logically divides data by the values of one or more columns, organizing files into directories or table partition metadata so query engines can **skip irrelevant portions when reading**.

Example for `orders_clean`:

```text
abfss://silver@storage.dfs.core.windows.net/orders/
  business_date=2026-11-18/
    part-0000.snappy.parquet
    part-0001.snappy.parquet
  business_date=2026-11-19/
    part-0000.snappy.parquet
  business_date=2026-11-20/
    part-0000.snappy.parquet
    part-0001.snappy.parquet
```

When querying `2026-11-20`, an engine supporting **partition pruning** scans only the matching partition files instead of reading every date. Proper metadata/paths/layout and optimizer-friendly predicates are required.

### 12.1. Three Commonly Confused Optimization Mechanisms

| Mechanism | At what level does it skip? | Example |
|---|---|---|
| **Partition pruning** | Skips entire partitions not matching the filter | Reads only `business_date=2026-11-20` |
| **File/data skipping** | Skips files via min/max statistics, bloom filters, or engine indexes | Within one day, skips files whose `customer_id` range excludes target |
| **Predicate pushdown / column pruning** | Pushes filters and selective column reads into the reader/storage format | Parquet reads only `order_id` and `amount`; filters early on `status` |

These three work together, but **they are not the same thing**. A daily-partitioned dataset may still scan many files inside a single day without effective clustering or file statistics. Running `SELECT *` forces the engine to read unnecessary columns even when date pruning succeeds.

### 12.2. Logical vs. Physical Partitions

Not every system uses the word “partition” the same way:

- **Spark/Delta/Parquet on ADLS:** table partitions/directory layouts as well as Spark execution partitions in memory/shuffle.
- **Azure SQL Database:** SQL Server engine table partitioning with its own metadata, indexes, and storage semantics.
- **Synapse dedicated SQL pool:** distributions/partitions and columnstore segments differ from lake file folders.
- **Microsoft Fabric Warehouse/Lakehouse:** engines, table formats, and optimizations vary by SKU and workload.

Never confuse Spark’s `df.repartition(20)` (changing execution task partitions) with `write.partitionBy("business_date")` (creating physical table partition layout by column), even though both influence output file counts.

## 13. Choosing Partition Keys Around Query Patterns

A **good partition key** appears frequently in query filters, has balanced cardinality, distributes data reasonably evenly, and avoids generating excessive tiny partitions.

Suppose an events table holds 2 TB across 24 months, and analysts usually run:

```sql
SELECT country, SUM(revenue)
FROM orders_clean
WHERE business_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-20'
GROUP BY country;
```

Partitioning by `business_date` scans just 20 days; partitioning by `order_id` would create a massive, unmanageable number of partitions and yield no benefit for date filtering.

### 13.1. Comparing Common Keys

| Partition key | Benefit | Risk |
|---|---|---|
| `business_date` (day) | Fits daily/monthly reports and period backfills | Peak-day skew |
| `ingestion_date` | Simplifies ingestion, backfill, and retention | Event-date reports must handle late data |
| `event_hour` | Suited for high-volume streaming and intra-day queries | Over-partitioning if volume is modest |
| `country` | Useful for regional filters with moderate cardinality | Dominant countries create large skew |
| `tenant_id` | Enables pruning for single-tenant isolation | High tenant counts create tiny partitions/skew |
| `order_id` | Distinct point lookups | Usually **unsuitable** as a lake partition key |
| `year/month/day` | Can narrow scans by time | Deeper hierarchy and risk of date/timezone bugs |

Ask the decisive question: **what percentage of queries actually filter on this column?** If BI almost always queries by date and country, partition by date and use clustering/data skipping for country rather than creating an explosion of `date × country × tenant` folders.

### 13.2. Overly High Cardinality

Suppose you have 200,000 tenants, each producing 20 KB/day. Partitioning by `(tenant_id, business_date)` creates **hundreds of thousands of tiny partitions/files daily**, making metadata listing and query planning slower than any pruning gain.

For multi-tenant workloads, consider:

- Partitioning by day or hour sized appropriately to total volume.
- Clustering/ordering by `tenant_id` or leveraging engine statistics/data skipping.
- Physically isolating by tenant only when driven by **isolation, retention, or compliance** requirements and real sizing.
- Benchmarking against **skewed large tenants**, not just small sample tenants.

### 13.3. Overly Low Cardinality

Partitioning solely by `status` with four values does nothing to prune time-range queries: the `PAID` partition still grows unbounded across years. Choose partition keys based on real filter selectivity and data growth, not just low distinct count.

### 13.4. Skew

If country `VN` accounts for 90% of orders, a country partition creates one huge directory alongside tiny ones. Execution workers suffer stragglers: one task runs slowly while all others sit idle.

Mitigations include daily partitioning, bucketing/clustering where supported, adaptive query execution or join salting when appropriate, or redesigning layout. **Adding more Spark executors does not eliminate skew** if a single data partition still forces one giant task.

## 14. Choosing Daily, Hourly, or Monthly Granularity

There is no rule saying “smaller partitions are always faster.”

### 14.1. Estimating Partition Counts

Across two years of data:

```text
Monthly partitions: ~24
Daily partitions:   ~730
Hourly partitions:  ~17,520
Per-minute partitions: ~1,051,200
```

If each hour produces only 2 MB, hourly partitioning generates thousands of tiny folders and files. Conversely, if each day produces 5 TB and dashboards inspect only the latest hour, daily partitioning may still scan excessive data without data skipping or clustering.

### 14.2. Decision Matrix

| Data rate / volume | Primary query pattern | Candidate partition to benchmark |
|---|---|---|
| 5 GB/day | Daily/monthly reports | Day |
| 2 TB/day | Hourly/near-real-time analytics | Day or hour (benchmark both) |
| 500 MB/month | Monthly reports | Month, or unpartitioned if table is small |
| 100 GB/day, 200k tenants | Tenant + date filters | Day + clustering on tenant instead of tenant folders |
| 20 GB/day, 30-day retention | Daily expiration | Day helps lifecycle/backfills |

These are **starting design heuristics**, not hard engine rules. Verify **bytes per partition, files per partition, cost per query, query frequency, and metadata overhead** before finalizing.

### 14.3. Business Date or UTC Date?

If consumers report in `Asia/Ho_Chi_Minh`, partitioning by `business_date` aligns well with dashboard filters. Meanwhile, ingestion/streaming often operates in UTC to avoid timezone ambiguity. You can store **both `event_time_utc` and `business_date`**, choose physical partitions per dominant workload, and keep mappings explicit.

## 15. Designing ADLS Gen2 Directory Layouts

A practical layout:

```text
lake/
  bronze/
    source=orders-api/
      ingest_date=2026-11-20/
        batch-00042/
          event-part-0001.json
  silver/
    orders_clean/
      business_date=2026-11-20/
        part-00000.parquet
  gold/
    daily_revenue/
      business_month=2026-11/
        part-00000.parquet
  quarantine/
    orders_events/
      ingest_date=2026-11-20/
        invalid-part-0001.parquet
```

In Delta Lake, the table root path and `_delta_log` are managed by the transaction log; never move or delete data files manually just because you see them in partition folders. For plain Hive-style Parquet without a transaction log, atomic publishing, reader consistency, and metadata discovery vary by engine.

### 15.1. Choosing Stable Path Conventions

Include:

- Clear environment/zone/dataset separation to avoid mixing dev and prod writes.
- Consistent partition key naming and formatting such as `business_date=YYYY-MM-DD`.
- Run/batch provenance in dedicated metadata where appropriate.
- Zero emails, access tokens, secrets, or raw personal identifiers in path names.
- Storage account and container names compliant with Azure naming rules.

### 15.2. Layered Access Controls

Bronze containing raw PII may need tighter access groups than gold aggregates. ADLS Gen2 supports RBAC and ACL mechanisms matching its namespace and access paths. Never grant `Storage Blob Data Owner` across the entire storage account to a dashboard that only reads gold aggregates; use managed identities and least privilege.

### 15.3. Storage Lifecycle and Periodic Deletion

Daily partitioning helps identify expiring data, yet Blob Storage lifecycle policies operate based on **prefixes, filters, tiers**, and object-storage semantics. Do not assume creating a `business_date` folder automatically handles retention or safely purges transactional table files. For Delta tables, `VACUUM` and retention settings must stay compatible with time travel, concurrent jobs, streaming readers, and compliance; manually deleting physical files is hazardous.

## 16. Parquet, CSV, JSON, and Table Formats

### 16.1. Columnar vs. Row-Oriented

| Format | Characteristics | Best fit |
|---|---|---|
| **CSV** | Easy to exchange, weak type/schema enforcement, quoting/escaping hazards | Ingestion/interchange under strict contracts |
| **JSON/JSON Lines** | Flexible, handles nested events and schema evolution | Raw/bronze and streaming payloads |
| **Parquet** | Columnar, compressed, embedded statistics, selective column reads | Silver/gold analytics on the lake |
| **Delta Lake** | Table format over Parquet + transaction log and engine-backed features | Incremental upserts, schema enforcement/evolution, table governance |
| **Other table formats** | Iceberg/Hudi with distinct metadata/transaction designs | Where platform/engine support and use cases align |

Do not claim `Parquet` natively provides transaction isolation or ACID `MERGE`: those are capabilities of a **table format and engine**, not standalone Parquet files.

### 16.2. Column Pruning

If a Parquet table has 100 columns yet a query only needs `order_id` and `amount`:

```sql
SELECT order_id, amount
FROM orders_clean
WHERE business_date = DATE '2026-11-20';
```

A good Parquet reader avoids scanning the unneeded columns unlike `SELECT *`. Real savings depend on serialization, compression, statistics, engine behavior, and nested structures; nested fields have specific pushdown limits.

### 16.3. Compression Codecs

Common codecs include Snappy, ZSTD, and engine-specific options. **Snappy** typically balances read/write speed well; **ZSTD** often achieves higher compression ratios at different CPU costs depending on level and dataset. Measure **storage $/GB + bytes scanned + compute CPU + latency** instead of blindly optimizing for minimum file size.

### 16.4. Schema Enforcement and Type Safety

Parquet enforces physical column types, yet pipelines still must validate **logical and business rules**. A type-valid `DECIMAL` `amount` column can still be off by 1,000x due to a unit or FX bug. DQ checks complement schemas rather than replacing them.

## 17. Small Files: The Enemy of Data Lake Analytics

A 1 TB table fragmented into 2 million 0.5 MB files can run drastically slower than fewer well-sized files because:

- Metadata/directory listing and task scheduling overhead skyrocket.
- Each file incurs multiple I/O operations and storage requests.
- Data skipping/statistics lose effectiveness when layouts are fragmented.
- Table transaction logs and metadata bloat from excessive file entries.
- Storage transaction billing and job orchestration overhead climb.

**Conversely, a single giant file** can bottleneck parallelism or trigger memory/latency spikes in some workloads. The goal is a **practical file size tuned to your engine and queries**.

### 17.1. File Size Benchmarks

A common starting target for many Spark analytics workloads is on the order of **hundreds of MiB** (such as 128–512 MiB), though it is not a rigid rule. Low-latency streaming may accept smaller files as a trade-off, while heavy batch scans benefit from larger ones.

### 17.2. Compaction

**Compaction** coalesces many small files into fewer larger ones per partition and table-format semantics. In Delta Lake with supporting runtimes, `OPTIMIZE` may be available; for plain Parquet, Spark can rewrite datasets/partitions.

Illustrative Delta example in a runtime supporting the command:

```sql
OPTIMIZE silver.orders_clean
WHERE business_date >= DATE '2026-11-01';
```

**Do not treat `OPTIMIZE` as universal SQL across all Synapse, Fabric, or Databricks runtimes.** Before running it, confirm engine support, table format, permissions, maintenance windows, and rewrite compute costs.

### 17.3. Compaction Pitfalls

- Compaction consumes compute and writes new data files; running it too often can **cost more than query savings**.
- Streaming writers and concurrent readers require compatible table-format transaction isolation.
- Do not compact the entire historical table hourly when only today’s partition is mutating.
- Account for retention, time travel, and `VACUUM` after compaction.
- Keep data quality gates enforced; compaction **does not repair bad records**.

### 17.4. How Over-Partitioning Causes Small Files

Suppose a 5-minute batch produces 20 MB and uses `partitionBy("business_date","country","tenant_id")`. If a batch touches 500 tenants, it fragments into hundreds of tiny partition folders. Rather than piling on partition columns, tune writer buffers, microbatch size, clustering, compaction, and partition granularity.

## 18. PySpark `partitionBy`, `repartition`, and `coalesce`

### 18.1. Writing Parquet by Business Date

```python
clean_orders = (
    source_orders
    .withColumn("business_date",
                F.to_date(F.from_utc_timestamp(
                    "event_time_utc", "Asia/Ho_Chi_Minh")))
)

(
    clean_orders.write
    .mode("append")
    .format("parquet")
    .partitionBy("business_date")
    .save("abfss://silver@STORAGE_ACCOUNT.dfs.core.windows.net/orders_clean")
)
```

This fragment assumes `source_orders` and `F` are already defined; it illustrates **physical layout**, not idempotency or atomic table commits. Never replay the same batch with plain append without checkpoints and deduplication.

### 18.2. `repartition` vs. `partitionBy`

```python
balanced = clean_orders.repartition(32, "business_date")

(
    balanced.write
    .mode("append")
    .partitionBy("business_date")
    .parquet("abfss://silver@STORAGE_ACCOUNT.dfs.core.windows.net/orders_clean")
)
```

`repartition(32, "business_date")` hash-partitions rows across Spark execution tasks via a shuffle; it **does not guarantee** exactly 32 output files or one file per date. Actual file counts also depend on writers, active tasks, `maxRecordsPerFile`, and data skew.

### 18.3. When to Use `coalesce`

`df.coalesce(n)` typically reduces Spark execution partitions without a full shuffle when shrinking down. It helps after selective filters, but forcing `coalesce(1)` across large datasets bottlenecks everything onto one task, spiking latency and executor memory pressure.

### 18.4. Counting Files Before and After Optimization

Track these metrics per batch/partition:

```text
dataset_id
business_date / partition
row_count
bytes_written
file_count
average_file_size
p50/p95 file_size
max_file_size
write_duration / compute cost
downstream scan cost / latency
```

Never optimize blindly for fewer files (`file_count`) while ignoring write costs and downstream read latency.

## 19. Delta Lake: Transaction Logs, `MERGE`, and Partitioning

**Delta Lake** is a table format combining Parquet data files with a transaction log; when supported by an engine, it enables schema enforcement, ACID table transactions, upserts/deletes, and time travel per configuration.

```text
silver/orders_clean/
  _delta_log/
    00000000000000000000.json
    00000000000000000001.json
    ...
  business_date=2026-11-19/
    part-....snappy.parquet
  business_date=2026-11-20/
    part-....snappy.parquet
```

Never **read all raw Parquet files directly** inside a Delta folder and treat them as the current table snapshot: obsolete files evicted by the transaction log remain physically on disk until vacuumed for time-travel retention.

### 19.1. Creating a Partitioned Delta Table

In a Delta-compatible SQL engine:

```sql
CREATE TABLE IF NOT EXISTS silver.orders_clean (
  order_id STRING,
  customer_id STRING,
  amount DECIMAL(18,2),
  status STRING,
  event_time_utc TIMESTAMP,
  business_date DATE,
  source_version BIGINT
)
USING DELTA
PARTITIONED BY (business_date);
```

This is **Delta/Spark SQL syntax**, not Azure SQL Database or universal warehouse SQL. When creating managed or external tables, configure location, catalog, and credentials per workspace governance.

### 19.2. Upserting the Latest Version

Example:

```sql
MERGE INTO silver.orders_clean AS target
USING staging.orders_latest AS source
ON target.order_id = source.order_id
WHEN MATCHED
  AND source.source_version > target.source_version
THEN UPDATE SET
  target.customer_id = source.customer_id,
  target.amount = source.amount,
  target.status = source.status,
  target.event_time_utc = source.event_time_utc,
  target.business_date = source.business_date,
  target.source_version = source.source_version
WHEN NOT MATCHED THEN INSERT (
  order_id, customer_id, amount, status,
  event_time_utc, business_date, source_version
) VALUES (
  source.order_id, source.customer_id, source.amount, source.status,
  source.event_time_utc, source.business_date, source.source_version
);
```

**Precondition:** `staging.orders_latest` must contain **at most one row per `order_id`** in the batch with reliable version ordering. If the source yields multiple matching rows, `MERGE` can fail or exhibit undesired runtime behavior. Deduplicate beforehand and handle deletes/tombstones explicitly.

### 19.3. Watch Out When Partition Keys Change

If an order’s `business_date` changes due to a timezone fix, `MERGE` may rewrite files across **both old and new partitions**. If a table is partitioned by event date while updates frequently shift dates, rewrite overhead rises. Evaluate whether current snapshots should be date-partitioned or instead clustered by lookup keys.

### 19.4. Table Transactions Do Not Span External Systems

A Delta commit is not automatically atomic with:

- An upstream Azure SQL commit.
- Emitting a Service Bus message.
- Updating an external search index.
- Refreshing a Power BI semantic model.

You still need orchestration, idempotent checkpoints, and cross-system reconciliation. **Table-format ACID guarantees apply only within transactions supported by that engine and table.**

## 20. Clustering, Z-ORDER, Liquid Clustering, and Data Skipping

**Partitioning** shines when queries filter on the partition key. If a single day holds 500 million rows and most queries filter on `customer_id`, **data clustering** may be needed to co-locate similar rows so the optimizer skips irrelevant files efficiently.

### 20.1. Clustering vs. Partitioning

- **Partitioning:** divides a table into explicit metadata/directory partitions.
- **Clustering/ordering:** co-locates rows by selected columns to boost file skipping without creating a directory per key value.
- **Statistics:** min/max, null counts, cardinality, or engine-specific metadata enabling segment/file pruning.

### 20.2. Z-ORDER

Some **Azure Databricks/Delta** environments support optimizing layouts with `ZORDER BY` per supported API/runtime. Illustrative example:

```sql
OPTIMIZE silver.orders_clean
WHERE business_date >= DATE '2026-11-01'
ZORDER BY (customer_id);
```

This is an **engine-specific** optimization carrying compute/rewrite costs. If most queries never filter `customer_id`, returns may be minimal, and frequent subsequent writes degrade the ordering.

### 20.3. Liquid Clustering and Newer Features

Some Databricks/Delta runtimes offer **liquid clustering**, which manages physical layout differently from Z-ORDER and traditional Hive partitioning. Feature support and compatibility vary by runtime and table properties; **never mix Z-ORDER and liquid clustering on the same table based on assumptions**. Pick one runtime-supported strategy and validate write/read workloads, maintenance cost, and benchmarks.

### 20.4. When a Filtered Query Still Scans Too Much

```sql
SELECT COUNT(*)
FROM silver.orders_clean
WHERE customer_id = 'C-1042'
  AND business_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-20';
```

With daily partitioning, non-matching days are pruned; clustering/data skipping on `customer_id` can skip many files within those days. Yet if `C-1042` appears across nearly every file due to unclustered ingestion or wide min/max statistics, the query still reads excessive bytes.

### 20.5. Never Cluster on Twenty Columns

Clustering across too many columns spikes sorting costs and weakens data locality for each individual column. Select a small set of **frequently filtered, selective columns** grounded in query logs, and re-evaluate as workloads shift.

## 21. Partition Pruning and Optimizer-Friendly SQL

### 21.1. Filter Directly on the Partition Column

Good example:

```sql
SELECT SUM(amount)
FROM silver.orders_clean
WHERE business_date >= DATE '2026-11-01'
  AND business_date <  DATE '2026-12-01';
```

When partitioned on `business_date` and metadata is intact, the optimizer eliminates partitions outside November.

### 21.2. Avoid Wrapping Partition Columns Unnecessarily

Expressions like:

```sql
-- Do not assume every engine optimizer prunes this cleanly:
WHERE YEAR(business_date) = 2026
  AND MONTH(business_date) = 11
```

can inhibit direct partition predicate matching. **Not every function on a partition column breaks pruning**: some engines perform expression rewriting or constant folding. The practical rule is to **inspect `EXPLAIN` / query plans / bytes scanned**, preferring simple range predicates when semantics allow.

### 21.3. Timezone Conversion Inside `WHERE`

Approach with care:

```sql
WHERE TO_DATE(FROM_UTC_TIMESTAMP(event_time_utc, 'Asia/Ho_Chi_Minh'))
      = DATE '2026-11-20'
```

If the table is partitioned on `business_date`, filtering on a computed expression over `event_time_utc` may fail to prune partitions. Instead, persist a normalized `business_date` column and write:

```sql
WHERE business_date = DATE '2026-11-20'
```

Just ensure the stored column strictly uses the approved business timezone and is backfilled whenever rules change.

### 21.4. Dynamic Partition Pruning in JOINs

Some Spark/SQL engines support **dynamic partition pruning** when joining against a small filtered key set. Effectiveness depends on table statistics, join strategy, and optimizer settings. Never use it as an excuse for poor partition keys; inspect `EXPLAIN` and scan metrics.

### 21.5. `EXPLAIN` Is Mandatory When Optimizing

In Spark SQL:

```sql
EXPLAIN FORMATTED
SELECT SUM(amount)
FROM silver.orders_clean
WHERE business_date = DATE '2026-11-20';
```

Depending on runtime, the plan shows `PartitionFilters`, `PushedFilters`, `DataFilters`, and scan nodes. **Never conclude a query scans a single partition solely from SQL text** without verifying the plan; views, CTEs, timezone casts, or stale metadata can alter execution.

## 22. Partition Pruning in Serverless Analytics

In **Azure Synapse serverless SQL pool** and engines querying storage files directly, billing can scale directly with **data processed/read** under the pricing model. Physical layout and filtering therefore directly drive cost.

### 22.1. Reading Parquet with `OPENROWSET`

**Illustrative T-SQL** for Synapse serverless SQL:

```sql
SELECT TOP 100
    order_id, amount, business_date
FROM OPENROWSET(
    BULK 'https://STORAGE_ACCOUNT.dfs.core.windows.net/silver/orders_clean/business_date=2026-11-20/*.parquet',
    FORMAT = 'PARQUET'
) AS rows;
```

This snippet uses a sample path and assumes appropriate workspace/identity storage permissions; wildcard support, credentials/auth, schema inference, and partition column reading must be verified against the **serverless SQL engine**. Never assume `business_date` resides inside the Parquet file payload if the writer stored it solely in folder partition metadata; you may need `filepath()` extraction or external table definitions.

### 22.2. Targeting Date Paths Instead of the Whole Lake

If a query only needs November 20, scoping `BULK` to that exact partition prefix cuts files and bytes scanned. Querying `BULK .../**` across two years and filtering afterward costs far more.

For views or external tables over partitioned folders, verify how the engine performs **partition elimination**, predicate pushdown, and `filepath()` filtering. Never assume `WHERE business_date = ...` eliminates files if `business_date` is treated as an unoptimized virtual expression.

### 22.3. Serverless and Dedicated Have Different Cost Models

- **Synapse serverless SQL:** pay-per-query by data processed, with minimum thresholds and rules active at usage time.
- **Synapse dedicated SQL pool:** capacity/DWU compute, pause/resume, and storage per configuration; tune distributions and columnstore indexes rather than file paths alone.
- **Azure Databricks:** compute/DBUs and cloud resources per cluster/serverless/SQL warehouse modality plus storage.
- **Microsoft Fabric:** capacity/consumption units and OneLake/warehouse workloads per product pricing rules.

**Never apply a single bytes-scanned formula across all engines.** Estimate using official pricing models, runtime telemetry, and actual invoices.

### 22.4. `SELECT *` Can Be Expensive

```sql
-- Read only the three columns needed for the KPI
SELECT business_date, country, SUM(amount) AS revenue
FROM gold.daily_orders
WHERE business_date >= DATE '2026-11-01'
  AND business_date <  DATE '2026-12-01'
GROUP BY business_date, country;
```

With columnar storage, skipping hundreds of unneeded columns reduces I/O. Serving frequent workloads from pre-aggregated gold tables can also be far cheaper than repeatedly scanning raw silver.

## 23. Columnstore, Distribution, and Materialization

When data resides in a **SQL warehouse or dedicated pool** instead of raw lake files, key techniques include:

- **Columnstore indexes/segments:** columnar compression and fast scan/aggregate execution.
- **Data distribution/sharding:** minimizing data movement during joins/aggregations via well-chosen distribution keys.
- **Statistics:** helping optimizers pick efficient plans.
- **Materialized views/aggregations:** avoiding recomputing large KPI aggregations.
- **SQL table partitioning:** partition elimination, partition switching, and maintenance per engine.

Capabilities and syntax differ across Azure SQL Database, Synapse dedicated SQL pool, and Fabric Warehouse. Never equate Synapse dedicated `HASH` distribution with Delta Lake `PARTITIONED BY`: **distribution spreads rows across compute nodes**, whereas table partitioning addresses layout and maintenance lifecycle.

### 23.1. Choosing a Distribution Key

For a large fact table frequently joined on `customer_id`, distributing by a high-cardinality, evenly spread key can cut data movement where the engine supports it. Yet if a handful of customers generate most rows, skew overloads a single node. Check distribution skew and explain plans instead of guessing from column names.

### 23.2. Pre-Aggregation

A dashboard querying daily revenue 10,000 times a day should generally read a `daily_revenue` gold table rather than scanning billions of `order_events` 10,000 times. However, that gold aggregate must refresh cleanly upon:

- Late events.
- Refunds or adjustments.
- FX rate or business-logic updates.
- Source backfills.

Materialization saves read compute while introducing **refresh costs and staleness risk**. Evaluate total workload cost rather than query latency alone.

### 23.3. Partition Pruning vs. Result Caching

Many engines include **query result caching** or automatic materialization. Cache hits can make benchmarks look artificially fast while masking true cold-scan costs; performance testing must separate cold vs. warm cache states and metadata conditions across diverse query patterns.

## 24. Quantifying Partitioning Gains

A simplified model:

\[
ScanReduction=1-\frac{BytesReadAfter}{BytesReadBefore}
\]

Suppose:

```text
Dataset: 1,200 GB Parquet
Query: reads only 2026-11-20
Before optimization: 1,200 GB processed/scanned
After pruning + column skipping: 24 GB

ScanReduction = 1 - 24/1200 = 98%
```

**Do not automatically conclude the bill dropped 98%**: minimum billing floors, compute startup, metadata/listing I/O, result caching, ETL transforms, maintenance jobs, and SKU pricing models all factor in. Even so, bytes scanned remains a primary optimization signal.

### 24.1. Why Bytes Read ≠ Table Size

A query can read less than table size via partition/column pruning, or process far more due to repeated scans, shuffles, and uncompressed intermediate spills. Telemetry labels like “bytes read,” “data processed,” “shuffle bytes,” and “input size” carry distinct meanings—**standardize definitions and sources** before comparing.

### 24.2. Before/After Benchmarking

Record:

```text
query_id / workload
engine/runtime/version
date range/filter
table snapshot/version
data format/compression
partition key/number of partitions
file count and size distribution
bytes scanned / rows read
query duration p50/p95
compute consumption and billed cost estimate
result cache condition
result correctness checksum/row counts
```

An optimization is acceptable **only if query outputs remain accurate**, without dropping late records or shifting timezones.

## 25. Total Analytics Cost Model on Azure

**Analytics cost** extends well beyond ADLS Gen2 storage fees. Costs span multiple layers and behave differently across engines:

```text
Total Cost of Ownership (TCO)
  |
  +-- Ingestion: Event Hubs, Data Factory, connectors, networking
  +-- Storage: ADLS/OneLake, replicas, tiers, operations, snapshots
  +-- Compute: Spark jobs, SQL warehouses, Synapse, Fabric capacity
  +-- Query: data scanned / compute time / capacity usage per product
  +-- Optimization: compaction, clustering, statistics, refresh
  +-- Observability: Log Analytics, data profiling, alerting
  +-- Governance/Security: catalog, encryption, private endpoints
  +-- Data movement: cross-region egress, inter-service transfers
  +-- People/operations: incidents, backfills, maintenance
```

### 25.1. Conceptual Cost Formula

\[
C_{month}=C_{ingest}+C_{storage}+C_{compute}
 +C_{queries}+C_{network}+C_{monitoring}+C_{maintenance}
\]

**Avoid double-counting** overlapping components: in serverless query engines, query compute may already be bundled into the per-query scan price; in dedicated clusters, compute accrues while running even between queries. Calibrate the model to your actual SKU invoice structure.

### 25.2. Measurable Units

| Component | Measurable unit | Watch out for |
|---|---|---|
| Data lake storage | GB/TB-month by tier | Replication, versioning, retention, and storage operations |
| Pipeline orchestration | Job/pipeline/activity runs or compute usage | Activity type, data movement, integration runtimes |
| Spark compute | VM/node hours, DBUs, or service-specific units | Driver/executor runtime, idle time, auto-termination |
| Serverless SQL | Data processed/scanned per query per pricing sheet | Minimum billing/rounding and query plan efficiency |
| Dedicated SQL/warehouse | DWU/vCore/capacity-time and storage | Pause/resume and auto-stop/scaling by service |
| Streaming | Throughput/capacity-time, retention/checkpoints | Backlogs, ingress/egress, consumer fan-out |
| Monitoring | Log ingestion, retention, query/alert charges | Never log raw payloads for every event |
| Networking | Egress/zone/region transfers, gateways | Data locality and DR topology |

### 25.3. Scan Comparison Example

Suppose a system runs 2,000 queries/day, each scanning 100 GB unpruned. After partitioning and converting to Parquet, the average query reads 8 GB:

```text
Before: 2,000 × 100 GB = 200,000 GB/day
After:  2,000 ×   8 GB =  16,000 GB/day
Modeled scan reduction = 92%
```

On a **data-processed** billing engine, this yields strong cost savings; on an always-on 24/7 hourly cluster, scan savings reduce latency and capacity pressure, yet **compute bills may stay flat** until autoscaling or auto-stop actually trims idle capacity.

### 25.4. Write and Maintenance Costs Count Too

Rewriting 100 TB daily for clustering just to speed up 20 rare queries can cost more than it saves. Evaluate:

\[
NetBenefit=QueryCostSaved-(RewriteCost+MaintenanceCost+AddedStorageCost)
\]

Never optimize layout around a single rare benchmark query; rely on **actual query frequencies** and growth plans.

## 26. Choosing the Right Compute: Batch, Streaming, Serverless, Dedicated

### 26.1. Batch Jobs

When data only needs updating at 01:00 daily, spinning up Spark/SQL jobs for a few minutes and terminating afterward is typically far cheaper than keeping a cluster alive all day. Factor in startup overhead, job dependencies, runtime availability, and peak SLAs.

### 26.2. Streaming

Near-real-time streaming often requires continuous compute plus state/checkpoints, raising baseline spend over batch. Choose sub-second or second-level latency only when genuinely required by the business; many dashboards work fine on 5–15 minute micro-batches.

### 26.3. Serverless Query

Strengths: no persistent cluster operations and flexible ad-hoc analytics. Trade-offs: variable cost per scanned query, concurrency/quotas, cold-start/cache behavior, and storage security policies.

### 26.4. Dedicated Warehouse/Cluster

Strengths: predictable capacity and consistent performance under steady workloads. Trade-offs: idle compute charges if left unpaused/unscaled, plus concurrency and workload-isolation management. Note that **pause/resume/auto-stop** capabilities vary by product and tier—never assume every Azure service auto-pauses.

### 26.5. Separating Interactive BI from Heavy ETL

If a 6-month Spark backfill shares compute with peak-hour dashboards, interactive queries stall. Use **workload isolation**, separate SQL warehouses/compute pools, and resource quotas—recognizing that extra compute pools also raise baseline spend and require budgeting.

### 26.6. Smallest Capacity Is Not Always Cheapest

A tiny cluster running for 9 hours can cost as much as or more than a larger cluster finishing in 1 hour depending on pricing and parallel scaling. Optimize for **cost per successful workload**, not raw cost per node-hour.

## 27. Managing Storage Lifecycle, Retention, and Data Temperature

Not all lake data belongs on hot storage tiers forever.

### 27.1. Classifying by Access Frequency

| Layer | Typical access | Design guidance |
|---|---|---|
| Recent Bronze (30 days) | Frequent debugging/replay | Keep on standard hot access tier matching SLA |
| Historical Bronze (2 years) | Rarely read, retained for policy audits | Evaluate cool/archive tiering and restore latency |
| Active Silver (90 days) | Incremental merges and BI | Prioritize query performance and contracts |
| Gold aggregates | Heavily queried | Storage/access paths tuned for serving |
| Quarantine | Controlled investigation/replay only | Strict TTL/retention and tight access controls |

This is a reference pattern, not a default policy. Azure Blob/ADLS tiering and lifecycle rules carry **compatibility constraints, minimum retention periods, rehydration delays, and operation fees** per tier; table-format transaction logs and metadata require extra care.

### 27.2. Never Archive Active Delta Files Indiscriminately

A live Delta table under active queries/updates requires its transaction log and current data files to stay readable by the engine. Moving active files into archive/inaccessible tiers without planning breaks table snapshots and time travel. Apply tiering at the level of **retired datasets or closed historical partitions** after verifying compatibility, backup/restore, and query behavior.

### 27.3. Time Travel and `VACUUM`

A Delta table retains superseded data files to power time travel and recovery per retention configuration. `VACUUM` deletes unreferenced files older than the retention threshold:

- Run only after accounting for concurrent readers and streaming lag.
- Never set an ultra-short retention threshold just to trim storage if active jobs still read older snapshots.
- Never treat `VACUUM` as a complete legal/privacy deletion workflow.
- Enforce PII removal consistently across raw, silver, gold, checkpoints, and backups per compliance rules.

### 27.4. Data Lake Replication and Cost

Storage redundancy options such as LRS, ZRS, or GRS (where offered by region/account) affect durability and cost; **GRS does not automatically make secondary-region data queryable as an active analytics source** or guarantee application RTOs. Disaster recovery requires testing actual failover/read access, compute availability, DNS, and identities.

## 28. Optimizing Ingestion and Orchestration

Even with fast queries, pipelines waste money when copying duplicate data or running unnecessary full refreshes.

### 28.1. Full Load vs. Incremental

| Approach | When appropriate | Limitations |
|---|---|---|
| Full refresh | Small datasets, simple logic, infrequent updates | Repeatedly scans and rewrites unchanged history |
| Incremental append | Immutable event logs | Requires dedup, late-event handling, checkpoints |
| CDC upsert | Continuously mutating current snapshots | Ordering sequences, deletes, merge cost |
| Micro-batch | Near-real-time without strict per-event latency | Windowing, checkpoints, latency trade-offs |
| Streaming | Low-latency SLOs, continuous ingestion | Compute/state/ops overhead and complex recovery |

### 28.2. Eliminating Empty Polling Loops

Running a pipeline every minute when the source only drops files hourly creates dozens of empty runs and startup overhead. Use event triggers where supported or align polling cadences—while still guarding against **missed events** with fallback sweeps.

### 28.3. Right-Sizing Ingestion Chunks

Micro-batches that are too small breed small files; batches that are too large hurt latency. Tune microbatch intervals and target file sizes based on ingest velocity, lag, partition granularity, SLA, and cluster startup overhead.

### 28.4. Data Movement and Region Placement

Shuffling terabytes cross-region for daily ETL increases network charges and latency. Co-locate compute with storage/warehouses subject to security and data residency; when multi-region transfers are unavoidable for DR or collaboration, quantify egress charges and obtain privacy approvals first.

### 28.5. Retries Can Multiply Pipeline Costs

If an ADF/Spark job scans 1 TB, times out near the end, and retries 5 times, compute and read/scan expenses multiply roughly per attempt; even with idempotent writes, **retries still cost money**. Implement:

- Partition- or batch-level checkpoints.
- Backoff/retry policies scoped strictly to transient failures.
- Max retry caps and cost guardrails.
- Partial progress recovery where supported by the engine.
- Alerts when a batch retries repeatedly or exceeds budgets.

## 29. Data Quality Must Also Be Cost-Effective

DQ validation can become heavy: running `COUNT DISTINCT` across a 50 TB table, joining massive datasets, or scanning full history every run. The answer is not skipping DQ, but designing **incremental, risk-based validation**.

### 29.1. Tiered Validation Layers

| Check layer | When it runs | Examples |
|---|---|---|
| **Fast gate** | Every batch/microbatch | Schema, nulls, ranges, intra-batch event ID dedup |
| **Partition gate** | Prior to partition publish | Cross-batch duplicates, source count reconciliation |
| **Cross-domain gate** | Reporting cutoffs/closes | Orders vs. payments vs. refunds |
| **Deep audit** | Scheduled or anomaly-triggered | Full-history consistency, source sampling |
| **Backfill validation** | Post-remediation | Before/after checksums and row counts per partition |

### 29.2. Incremental Uniqueness

If `order_id` must be unique across an entire current-state snapshot, intra-batch checks alone are insufficient. Rely on **database unique constraints/indexes** where enforced, or transactional `MERGE` paired with source dedup and conflict detection. When the engine cannot physically enforce uniqueness, maintain compensating gate checks and document the limitation.

### 29.3. Sampling Does Not Replace Hard Constraints

Sampling works well for spotting clickstream anomalies, but it is **insufficient** to guarantee no duplicate or missing invoice out of 1 million financial rows. Critical invariants require exhaustive checks or storage/database-enforced semantics.

### 29.4. Reusing In-Flight Profiling Metrics

When a pipeline already computes row counts, min/max event times, nulls, and invalid counts during writes, persist those batch metrics directly so downstream dashboards do not re-scan every file just to render DQ stats.

### 29.5. Avoid Masking Severe Bugs Behind a “Quality Score”

A dataset boasting 99.99% completeness while silently dropping **10 high-value orders** is unsafe despite looking near 100%. Use **critical rules, weighted impact, and absolute failure thresholds** backed by explicit PASS/WARN/FAIL states.

## 30. Observability: Monitoring Pipeline Health and Data Quality

**Pipeline succeeded** does not guarantee trustworthy data. A job can finish green while capturing only 20% of source records, misapplying timezones, or dropping refunds. Observe the **data plane** alongside job/process health.

### 30.1. Observability Stack

```text
Data Sources
   |
   +--> source counts / max source timestamp / CDC lag
   |
   v
Ingestion & Orchestration
   |
   +--> run status / duration / retries / bytes copied
   |
   v
Bronze -> Silver -> Gold
   |
   +--> DQ metrics / quarantine / reconciliation / freshness
   +--> partition/file metrics / bytes scanned / compaction
   |
   v
Consumers
   |
   +--> report freshness / query latency / failed refresh / cost
   |
   v
Azure Monitor / Log Analytics / data catalog / Cost Management
```

### 30.2. Minimal DQ Telemetry

| Metric | Measurement | Meaning |
|---|---|---|
| `rows_ingested` | Source row count per batch/partition | Is data arriving? |
| `rows_valid` / `rows_invalid` | Row-level rule aggregation | What is the defect rate? |
| `dq_rule_failures` | Count by rule ID/severity | Which rules are failing? |
| `max_event_time` | Max event timestamp | Is data time advancing? |
| `source_to_silver_lag` | Silver watermark minus source/clock per semantics | End-to-end pipeline delay |
| `reconciliation_delta` | Source vs. target difference under shared contract | Missing/duplicate rows or metric drift |
| `quarantine_backlog` | Unresolved rows/batches | Operational data debt |
| `partition_count` / `file_count` | Table metadata / output manifest | Small-file and metadata pressure |
| `query_bytes_scanned` | Engine telemetry | Are pruning and column skipping working? |
| `compute_cost_per_run` | Job cost attribution | Optimization or cost regression? |

### 30.3. Freshness Formula Needs Schedule Context

One way to measure lag:

\[
FreshnessLag=NowUTC-MaxAvailableEventTimeUTC
\]

However, if a source only generates transactions during business hours, zero new events overnight is not necessarily an incident. Pair freshness metrics with **source schedules and expected arrival policies**, or track watermark progress against SLAs. Never configure a 15-minute freshness alert on a source that drops a single daily batch at 02:00.

### 30.4. Never Use Raw Keys or IDs as Metric Labels

Never emit Prometheus or Log Analytics dimensions per `order_id` or per individual file path where cardinality explodes. Keep labels bounded (`dataset, rule_id, environment, layer, severity, source_type`) and store specific IDs safely inside secured quarantine records or tickets.

### 30.5. Structured Pipeline Logging

```json
{
  "timestamp": "2026-11-20T10:30:00Z",
  "environment": "production",
  "pipeline": "orders-silver-daily",
  "run_id": "run-20261120-0042",
  "dataset": "orders_clean",
  "partition": "2026-11-20",
  "rows_in": 250000,
  "rows_valid": 249975,
  "rows_quarantined": 25,
  "quality_status": "WARN",
  "schema_version": 2,
  "duration_seconds": 173,
  "bytes_read": 1342177280
}
```

This log format is **illustrative**, not auto-generated by Azure. Never log raw events, credentials, PII, or sensitive query results. Set log retention and access permissions according to data classification.

## 31. Azure Monitor, Cost Management, and Operational Telemetry

### 31.1. Monitoring Data Sources

Each Azure service exposes different telemetry mechanisms:

- **Azure Data Factory:** pipeline/activity/trigger run status, duration, and failures via diagnostic settings where supported.
- **Azure Databricks:** job/run telemetry, Spark metrics, and cluster/SQL warehouse usage depending on workspace/runtime.
- **Azure Synapse Analytics:** pipeline/Spark/SQL monitoring and query statistics per workload.
- **ADLS Gen2:** storage capacity, availability, transactions, ingress/egress, and server latency dimensions.
- **Azure SQL Database:** CPU, sessions, waits, I/O, and Query Store/telemetry per feature tier.
- **Power BI/Fabric:** refresh and capacity workload metrics per license/capacity model.
- **Azure Cost Management:** subscription/resource-group/tag costs, budgets/alerts, and chargeback/showback.

Do not assume every metric flows into a single default Log Analytics table automatically. Enable **diagnostic settings**, configure export/ingestion from each source, and inspect schemas before authoring KQL.

### 31.2. Example KQL for Application-Emitted Pipeline Logs

If a workspace contains a **custom table `DataQualityRuns_CL`** populated by your structured log ingestion pipeline (with verified schema), a **sample query** looks like:

```kusto
DataQualityRuns_CL
| where TimeGenerated > ago(24h)
| summarize
    Runs=count(),
    Failed=countif(QualityStatus_s == "FAIL"),
    Quarantined=sum(tolong(RowsQuarantined_d))
    by Dataset_s
| order by Failed desc
```

**This table and its columns do not exist in Azure by default.** You must build the ingestion pipeline and verify `DataQualityRuns_CL` and actual column names; `_s`/`_d` suffixes may differ in modern DCR-based custom tables. Never run this query and claim an environment lacks data quality monitoring simply because the custom table is absent.

### 31.3. Cost Tagging

Tag resources and jobs with metadata such as:

```text
environment = prod
business_unit = commerce
data_product = orders
cost_center = analytics-042
owner = data-platform
criticality = high
```

Tags enable **cost allocation across taggable resources**, though not every serverless query or shared job separates charges by tag automatically. For shared workspaces or clusters, layer on usage attribution by job, query, user, or warehouse per internal policy.

### 31.4. Budgets and Anomaly Alerts

A budget should include:

- Monthly/quarterly spending limits and an accountable owner.
- Threshold alerts against actual percentage and forecasted spend.
- Separation between steady-state run costs and one-off approved backfills.
- Drill-down by service, environment, workload, and tags.
- A runbook specifying what to throttle first and the associated SLA trade-off.

**Budget alerts do not automatically stop Azure resources.** Any automated compute throttling or job cancellation must be explicitly designed and approved—never auto-delete storage or abruptly kill critical pipelines over temporary budget spikes.

## 32. Runbook 1: Revenue Dashboard Diverges from Source

### 32.1. Scenario

The gold dashboard for Nov 20 reports revenue 7% lower than the source Azure SQL report. The pipeline shows “Success” with zero Spark errors.

### 32.2. Structured Investigation

1. Verify the **KPI definition**: paid vs. created, refunds, VAT, currency, timezone, and FX rates.
2. Check **source cutoff vs. target data-as-of**: are end-of-day events still waiting to be ingested?
3. Inspect `rows_ingested`, `rows_valid`, `rows_quarantined`, and partition quality gates.
4. Check CDC lag, source watermarks, batch retries, and idempotent dedup logic.
5. Check whether silver placed boundary records into the wrong date partition due to timezones.
6. Reconcile aggregates layer-by-layer (bronze → silver → gold) under the exact same semantic contract.
7. Review schema changes or transformation edits from recent deployments.
8. Check whether duplicate source events slipped through or legitimate order updates were mistakenly deduplicated away.
9. If backfill is required, execute via staging + validation + controlled promotion.
10. Document the incident, root cause, affected reports, and data restatement/annotation.

### 32.3. What Never to Do

- Never insert manual adjustment rows directly into gold without audit trails.
- Never purge quarantine records just to make a quality gate pass.
- Never alter production timezone rules without evaluating historical partitions.
- Never run a full-table overwrite when only one date range failed.
- Never declare an incident resolved merely because the job re-ran green while metric reconciliation still diverges.

### 32.4. Incident Closure Criteria

Both systems agree **within business-owner-approved tolerance**, row counts and event-time lags are accounted for, affected partitions pass re-validation, dashboards display accurate data-as-of/status indicators, and backfill runs carry clean audits with zero duplicates.

## 33. Runbook 2: Queries Suddenly Too Expensive or Slow

### 33.1. Symptoms

A monthly revenue report that normally took 20 seconds now runs for 6 minutes; query billing jumps and warehouse/DB load spikes.

### 33.2. Procedure

1. Capture the **query ID**, engine/runtime, execution plan, and exact regression timestamp.
2. Diff query text, partition filters, result cache status, and before/after table snapshots.
3. Verify partition pruning actually occurred: inspect `EXPLAIN`, scanned files, and bytes read.
4. Check for `SELECT *`, implicit type casts, UDFs/functions on partition keys, or overly broad path wildcards.
5. Inspect files per partition, file size distributions, and any recent small-file bursts.
6. Check for data skew, hot partitions, join strategies, shuffles, and stale statistics.
7. Check storage throttling/region locality, compute saturation, concurrency, and cluster auto-termination.
8. Test optimizations **in staging or replay tests**, measuring correctness, p50/p95 latency, and cost.
9. Apply targeted compaction, clustering, or partition adjustments rather than rewriting the whole lake blindly.
10. Monitor post-change maintenance overhead alongside query spend and document the new baseline.

### 33.3. Common Misguided Fixes

**Scaling up cluster size** cuts latency yet inflates compute bills; **partitioning by tenant** speeds single-tenant filters while spawning millions of files; running **`OPTIMIZE` on the entire table hourly** can burn more compute than queries save. Base decisions on **query frequency and net cost**.

### 33.4. Auditable Optimization Report

```text
Before:
  Queries/day = 1500
  Avg scan = 80 GB
  Query p95 = 95 s
  Quality results: verified

After:
  Avg scan = 12 GB
  Query p95 = 24 s
  Compaction/maintenance = 40 compute-min/day
  Quality results: same verified aggregation

Decision:
  Keep optimization only if total recurring savings
  exceed maintenance cost and SLO improves.
```

These numbers are synthetic illustrations, not performance guarantees or pricing for any specific Azure SKU.

## 34. Runbook 3: Small Files and Partition Skew

### 34.1. Scenario

A streaming job generates 2 million small files over 30 days. Directory listing and query planning drag while storage metadata operations climb, even though total data size is only a few hundred GB.

### 34.2. Steps

1. Measure file counts and file size distributions **per dataset and partition**.
2. Inspect the writer producing small files: microbatch interval, Spark task partitions, `partitionBy` cardinality, and rollover settings.
3. Check whether a single partition holds excessive files or the entire table is fragmented.
4. Tune microbatch intervals and physical partition granularity.
5. Run compaction on **affected recent partitions** respecting table-format semantics.
6. Verify concurrency behavior with active stream writers, readers, and checkpoints.
7. Track small-file creation rates after deploying writer fixes.
8. Benchmark query scan time, planning latency, and total cost.
9. Trigger maintenance schedules by data volume/fragmentation metrics rather than rigid fixed clocks regardless of activity.

### 34.3. What Never to Do on Delta Tables

Never run custom file scripts to move `part-...parquet` files or delete old files inside a Delta table directory—doing so corrupts the transaction log. Use runtime-compatible `OPTIMIZE`/maintenance commands, and verify retention and active snapshots before running `VACUUM`.

### 34.4. Skew vs. Small Files

Skew can occur even with ideal file sizes: one tenant holding 80% of rows forces a single shuffle task or node to do most of the work. Inspect **task durations, shuffle read/write bytes, and skew distributions** alongside execution plans rather than assuming compaction solves everything.

## 35. Runbook 4: Backfilling Late-Arriving Data

### 35.1. Scenario

A source delivers 200,000 late events for Nov 17 on Nov 20. Gold already finalized reporting for Nov 17.

### 35.2. Key Decisions

- Are these **legitimate late events** or a duplicate replay?
- Does the KPI contract allow **restating** closed periods?
- Which silver and gold partitions require updates?
- Do downstream consumers need restatement notices?
- Can we run a targeted partial rebuild instead of scanning the entire table?

### 35.3. Procedure

1. Record run/event IDs, source watermarks, and affected business dates.
2. Validate schemas/rules and deduplicate by logical event identity and sequence.
3. Route valid records to staging silver and invalid ones to quarantine.
4. Execute an idempotent merge or atomic partition rewrite under table transactions.
5. Recompute affected gold partitions and cross-table reconciliations.
6. Run post-transform DQ gates and reconcile against source totals.
7. Publish or restate per business-owner approval.
8. Refresh downstream caches/semantic models or notify consumers per contract.
9. Track backfill spend separately and compare bytes scanned/written.
10. Monitor ongoing late events and adjust watermarks only when justified.

### 35.4. Protect Real-Time SLAs

A 2-year backfill must never starve compute pools serving live streaming pipelines or interactive BI dashboards. Enforce workload isolation, throttling, off-peak scheduling windows, or platform compute quotas.

## 36. Security, Data Governance, and Privacy in Analytics

Cost and performance tuning must **never weaken data access controls**. Partitioning, compaction, clustering, and storage tiering alter physical locations and access patterns; security policies must follow data across every layer.

### 36.1. Permissions by Layer

| Component | Principle example |
|---|---|
| Bronze raw/PII | Restricted to producers/ingestion pipelines and approved investigators |
| Silver clean | Limited to downstream jobs, data owners, and required service principals |
| Gold aggregates | Role- and data-product-scoped read access; sensitive fields masked |
| Quarantine | Minimal privileges with strict auditing, as error payloads may hold PII |
| Catalog/lineage | Allows metadata discovery without implicitly granting data read rights |
| Compute identity | Managed identities / service principals with least-privilege scope |
| Diagnostics/logs | Never capture raw sensitive payloads; enforce strict retention and RBAC |

For **ADLS Gen2**, effective access may depend on both Azure RBAC and POSIX-like ACLs under hierarchical namespaces. Test **effective access** directly under the job’s managed identity rather than relying solely on portal RBAC views.

### 36.2. Encryption and Network Isolation

- Ensure encryption at rest across storage and warehouses; evaluate customer-managed keys when compliance requires and SKUs support them.
- Enforce TLS in transit.
- Configure private endpoints, VNet integration, and proper DNS routing per service.
- Never open public endpoints or issue unrestricted SAS tokens simply to bypass connectivity issues.
- Maintain plans for key rotation, access revocation, and network rollback.
- Enforce regional data residency aligned with legal and contractual obligations.

### 36.3. Column-Level and Row-Level Security

Multi-team gold layers often require granular access rules:

- Regional sales reps see only their assigned territory’s revenue.
- Analysts cannot read customer email addresses or phone numbers.
- BI service principals hold read-only rights on gold tables.
- Cross-tenant queries strictly enforce tenant isolation.

Row-level, column-level, and dynamic masking controls **depend on the query engine or semantic layer**—they do not live inside raw Parquet files if a user has direct storage access. **Never rely on a Power BI visual filter to secure raw storage** when users can read ADLS directly.

### 36.4. Retention and Data Subject Deletion

A customer data deletion request can span:

```text
Bronze raw events
  -> Silver cleaned tables
  -> Gold marts
  -> Feature stores / ML training snapshots
  -> BI caches / exports
  -> Backups, table time travel, quarantine
```

Maintain catalog lineage and privacy-compliant deletion/retention workflows; long backup or time-travel windows can conflict with erasure mandates unless designed together. Never run `DELETE FROM silver` alone and assume all copies are gone.

### 36.5. Preventing Data Exfiltration in Notebooks

A Spark notebook can `display()` thousands of PII rows, export local CSVs, or print sensitive logs. Restrict:

- Who can attach to compute and read data sources.
- When exports to external storage are permitted.
- Notebook revision history, sharing, and access auditing.
- Secret scopes / Key Vault references and output redaction.
- Access policies covering job artifacts, caches, and saved notebook outputs.

**Partitioning folders by tenant does not isolate tenant data** if a principal holds container-wide list/read access.

## 37. Quality-as-Code and CI/CD for Pipelines

### 37.1. Three Testing Tiers

| Tier | When it runs | What it tests |
|---|---|---|
| **Unit tests** | Every pull request | Schema parsing, timezones, decimals, DQ rules, mappings |
| **Integration tests** | Dev/staging post-deploy | Storage permissions, MERGE/checkpoints, orchestration, quarantine |
| **Data regression tests** | Per batch or release | Row counts, aggregates, partition pruning, correctness, and cost |

### 37.2. Compact Yet Edge-Case-Rich Test Fixtures

Include test cases for:

1. Standard valid row.
2. Null `order_id`.
3. `amount="abc"` and decimal precision overflow.
4. Event timestamp right around 00:00 local time.
5. Duplicate event ID.
6. Stale `source_version` update arriving after a newer version.
7. CDC delete/tombstone.
8. Missing customer reference arriving late.
9. Late event beyond watermark.
10. Refund/negative adjustment matching the contract.
11. Unsupported tenant or currency.
12. Empty batch and malformed character encoding.

Never validate pipelines exclusively on “happy-path” samples and assume production readiness.

### 37.3. PySpark Unit Test Example

```python
# Pytest/PySpark pseudocode, assuming transform_orders
# accepts a source DataFrame and returns (valid, invalid).

def test_invalid_amount_goes_to_quarantine(spark):
    source = spark.createDataFrame(
        [("evt-1", "ORD-1", "not-a-number", "VND", "PAID")],
        ["event_id", "order_id", "amount", "currency", "status"]
    )
    valid, invalid = transform_orders(source)

    assert valid.count() == 0
    assert invalid.count() == 1
    assert invalid.select("reason_code").first()[0] == "INVALID_AMOUNT"
```

This is a **unit-test pseudocode snippet**; it cannot execute standalone since `transform_orders` is undefined and production tests need timestamps, schemas, and metadata fixtures. The goal is separating transformations into modular, testable functions rather than burying all business logic inside monolithic notebook cells.

### 37.4. Testing Query Correctness After Layout Optimization

After modifying partitioning, clustering, or compaction:

- Verify row counts and distinct business keys match.
- Confirm monetary sums/checksums by date and region remain unchanged.
- Confirm no rows were lost to mis-scoped `overwrite` operations.
- Confirm date-filtered queries return the identical record set.
- Benchmark bytes scanned and latency against the exact same snapshot and range.
- Verify cross-tenant access policies still hold.

**Making a query faster by dropping records is never an optimization.**

### 37.5. Promoting Through Environments

```text
Pull request (schema/rules/SQL/PySpark)
       |
       v
Static checks + unit tests + secret scan
       |
       v
Dev pipeline + synthetic dataset
       |
       v
Integration: Bronze -> Silver -> Gold + DQ gates
       |
       v
Staging: realistic volume/partition layout + cost benchmark
       |
       v
Review / approval
       |
       v
Production deploy (canary/shadow/backfill plan)
       |
       v
Monitor DQ, freshness, cost, query latency
```

Use Azure DevOps or GitHub Actions with IaC to deploy resources and jobs, keeping CI service principals least-privileged. Granting a CI pipeline subscription-wide admin rights with hardcoded storage secrets creates unnecessary risk.

### 37.6. Avoid Simultaneous Breaking Rollouts

When a producer introduces a breaking field change, first deploy consumers supporting both versions, then roll out the producer update, run any needed backfills, and finally deprecate the old schema. Uncoordinated cutovers spike quarantine volume and break reports even when every CI build stays green.

## 38. Reference Architecture: E-Commerce Analytics on Azure

### 38.1. Requirements

A platform handles:

- 50 million clickstream events/day.
- 1 million order/payment state changes/day.
- Revenue dashboards sliced by date, market, and channel.
- Near-real-time reporting within 15 minutes; official revenue books finalized after the late-data window.
- Raw data retained under audit/privacy policy; gold serves Power BI.
- Goal: minimize query bytes scanned without sacrificing accuracy.

### 38.2. Proposed Diagram

```text
                 Azure SQL orders/payment
                         |
                      CDC/ETL
                         |
  Web/mobile -- Event Hubs -- Partner API
        |              |          |
        +--------------+----------+
                       |
                 Ingest jobs
                       |
                       v
             ADLS Gen2 Bronze (source/ingest_date)
                       |
            validate schema + provenance
                       |
                       v
              Silver Delta/Parquet
         event_id dedup, CDC merge, quarantine
                       |
            DQ checks + source reconciliation
                       |
                       v
              Gold reporting marts
         daily_paid_revenue, funnel, retention
                       |
         +-------------+---------------+
         |                             |
      SQL analytics                 Power BI
         |                             |
         +---------- Observability ----+
                       |
     Azure Monitor + catalog/lineage + Cost Management
```

### 38.3. Dataset Design

| Dataset | Layer | Physical design | Quality controls |
|---|---|---|---|
| `click_events_raw` | Bronze | Ingestion date/hour sized to volume | Event ID and source timestamps present |
| `click_events_clean` | Silver | Event date or ingestion date per query pattern | Parsed, deduped, consent-filtered |
| `orders_cdc_raw` | Bronze | Source/batch/ingestion date | Complete CDC sequence and operation fields |
| `orders_current` | Silver | Delta merge; partitioning/clustering tuned to size and queries | Latest version wins; zero duplicate current orders |
| `daily_paid_revenue` | Gold | Business date/market if distribution is balanced | Reconciled, carries freshness/cutoff status |
| `dq_quarantine` | Quarantine | Source/ingestion date with restricted access | Reason code, owner, replay status |

### 38.4. Intentional Partitioning

With 50 million daily clickstream events and primarily daily/weekly dashboards, start with daily partitions; move to hourly only if scan, ingestion, or latency benchmarks prove net value. For `orders_current` snapshots, partitioning by `business_date` **can make merges costly** when updates shift order dates; evaluate clustering by business keys and dominant filters instead.

### 38.5. Sample DQ Contract

```text
silver.orders_current:
  critical:
    order_id present
    one current row per order_id
    latest source_version wins
    valid status transition
    amount/currency parsable
  warning:
    country optional missing rate < threshold
  freshness:
    latest event age <= 15 minutes during operating hours
  reconciliation:
    paid total vs payment ledger per daily cutoff
  publish:
    no critical FAIL; warnings visible
```

This is a sample policy, not executable engine rules. **Valid status transitions** require an explicit business state machine accounting for refund/chargeback exceptions—never compare status strings alphabetically.

### 38.6. Cost Optimization Decisions

- Write bronze raw data in balanced batches to avoid millions of tiny files.
- Use incremental dedup/merges in silver instead of full refreshes.
- Pre-aggregate hot gold marts for high-frequency BI queries.
- Isolate interactive BI compute from heavy historical backfills where needed.
- Enable auto-stop/pause on intermittent compute where supported.
- Leverage data skipping and partition pruning; inspect `EXPLAIN` plans.
- Avoid unnecessary full-lake DQ scans by persisting incremental batch metrics.
- Track cost per successful pipeline run and per report/query.

### 38.7. Data Recovery

When pipeline v2 ships a bug:

1. Halt publishing on affected partitions; never delete raw data.
2. Identify impacted source/batch IDs, table versions, and date ranges.
3. Fix the transform and add regression DQ tests in CI.
4. Backfill from bronze using stable event IDs and source sequences.
5. Reconcile silver and gold, then obtain business-owner sign-off.
6. Release and issue a restatement notice if closed periods changed.

Never simply roll back to an old Delta time-travel snapshot and silently discard valid events that arrived after that snapshot.

## 39. Hands-On Exercises

### Exercise A — Orders Data Quality

You ingest 100,000 order events: 100 lack `order_id`, 50 have `amount="abc"`, and 20 have both defects. Perform the following:

1. Design validation rules and reason-code assignment order/format.
2. Calculate the exact unique invalid row count accounting for overlap.
3. Decide FAIL vs. WARN based on business impact rather than raw percentage alone.
4. Write SQL/PySpark logic to split out quarantine records.
5. Specify metadata required to replay records after remediation.

**Solution guide:** unique invalid rows equal `100 + 50 - 20 = 130`, yet a 0.13% rate **does not automatically imply PASS** because missing order IDs or corrupt financial amounts can be critical failures.

### Exercise B — Daily vs. Tenant Partitioning

A dataset holds 100,000 tenants at 30 GB of events/day, and queries mostly filter by date + tenant. Compare:

- `partitionBy("business_date","tenant_id")`.
- `partitionBy("business_date")` combined with clustering/data skipping on `tenant_id`.

**Solution guide:** partitioning by tenant creates high cardinality and tiny files; daily partitioning plus clustering is the stronger candidate to benchmark, factoring in tenant skew and query frequencies.

### Exercise C — Full-Lake Scan Query

A dashboard query runs:

```sql
SELECT *
FROM orders_clean
WHERE YEAR(business_date) = 2026
  AND MONTH(business_date) = 11;
```

Propose a range filter and explicit column projection, then verify via `EXPLAIN` and bytes scanned. Explain why you should never claim every function automatically breaks partition pruning.

**Solution guide:** rewrite using `business_date >= DATE '2026-11-01' AND business_date < DATE '2026-12-01'`; benchmark both plan and query cost on the exact same snapshot.

### Exercise D — Small Files

A streaming job commits 1,440 microbatches/day, each writing 200 tiny files across partitions—totaling 288,000 files/day.

**Task:** design microbatch interval, target file size, partition granularity, and compaction policy; weigh maintenance compute against query savings; explain how to avoid corrupting Delta tables with manual file moves.

**Solution guide:** reduce writer fragmentation at the source and compact recent partitions with table-aware maintenance; benchmark file listing, scheduling latency, and bytes scanned instead of merely throwing larger clusters at the problem.

### Exercise E — Late Events and Business Date

An order occurs at 23:58 on Nov 19 (`Asia/Ho_Chi_Minh`) and lands in the analytics ingestion pipeline at 00:10 on Nov 20.

**Task:** determine `business_date`, `ingestion_date`, partitioning choices, watermark settings, and gold restatement policy if Nov 19 already closed.

**Solution guide:** `business_date` derived from event time and timezone is Nov 19; `ingestion_date` is Nov 20; handle restatement/backfill per contract rather than slicing UTC timestamps arbitrarily.

### Exercise F — Choosing Compute Pricing Models

A batch workload runs 30 minutes daily with zero queries outside that window, currently provisioned on a 24/7 dedicated compute cluster.

**Task:** quantify idle time, propose pause/auto-stop or ephemeral job compute per supported capabilities, and evaluate startup overhead, SLAs, and auxiliary cost components.

**Solution guide:** idle overhead is huge; evaluate ephemeral job clusters or serverless options where appropriate, while noting not every service or tier supports auto-pause.

### Exercise G — DQ and Cost Observability

Design a dashboard displaying quality scores, invalid row counts, source watermarks, partition counts, file counts, scanned bytes, and compute costs sliced by dataset and layer. Define one alert for **critical DQ failure** and one for **cost regression**, specifying owner, window, threshold, and runbook.

**Solution guide:** critical quality gates can halt publishing; cost regressions must compare against baselines at equivalent workload/query volume to avoid false alarms during approved backfills.

### Exercise H — Backfill and Idempotency

The Nov 18 order batch ran 3 times after timeouts. Silver uses plain `append` and gold sums `amount`.

**Task:** describe the outcome, redesign using batch IDs, checkpoints, dedup/merges, or atomic partition replacement, reconcile against source totals, and write a duplicate-run test.

**Solution guide:** repeated appends cause double/triple counting; outputs must be idempotent rather than retrying blindly until a job turns green.

### Exercise I — Security and Retention

Quarantine contains customer emails and raw bronze is kept for 5 years, yet privacy policy mandates deleting a user within a defined SLA.

**Task:** design a lineage/deletion workflow spanning bronze, silver, gold, quarantine, and backups/time travel; define access controls, auditing, and retention policy alignment.

**Solution guide:** inventory sensitive fields and all derived copies, coordinate legal/privacy retention rules, and never assume deleting one gold row completes erasure.

## 40. Self-Check Questions

**1. How does data quality differ from schema validation?** Schema validation checks structure and types; DQ also covers completeness, uniqueness, validity, consistency, accuracy, freshness, lineage, and business rules.

**2. Must bronze, silver, and gold be three separate Azure services?** No. They are three logical layers; they can live in one storage account or span distinct storage and query engines depending on governance and architecture.

**3. Why should unparseable amounts never default silently to 0?** It injects false figures into revenue while hiding the root defect, making reconciliation harder.

**4. What should quarantined records store?** Record/source reference, rule failure reason, run/batch ID, schema version, ingest timestamp, and strict security/retention controls.

**5. Does uniqueness on `order_id` always apply to an events table?** No. One order can emit multiple legitimate events; uniqueness should check `event_id` or key/version matching the dataset’s grain.

**6. Does a 30-minute freshness rule mean firing an alert after any 30 minutes without events?** No. Account for source operating schedules and expected arrivals to avoid false alarms during quiet periods.

**7. How does event time differ from ingestion time?** Event time is when the event happened; ingestion time is when the pipeline received it—diverging under backlogs, offline devices, or late arrivals.

**8. Why enforce explicit UTC and business timezones?** To avoid assigning midnight-boundary events to the wrong business date, especially across regions.

**9. Where must CDC duplicate deliveries be handled?** Via checkpoints and bronze provenance, silver deduplication/upserts, and idempotent gold aggregations.

**10. What is partition pruning?** Skipping irrelevant partitions when the engine matches query predicates against partition metadata.

**11. How do partitioning and clustering differ?** Partitioning splits tables into discrete partition slices; clustering orders/co-locates rows/files for data skipping without creating directories per distinct key.

**12. Why avoid partitioning a lake table by `order_id`?** Extreme cardinality spawns excessive tiny partitions/files and metadata overhead unsuitable for analytical scans.

**13. Is hourly always better than daily because pruning is finer?** No. At modest volumes it breeds excessive tiny partitions/files; always benchmark.

**14. Are `df.repartition(32)` and `write.partitionBy("business_date")` the same?** No. The first reshapes Spark execution partitions in flight; the second defines the physical storage partition layout by column.

**15. How does Parquet differ from Delta Lake?** Parquet is a columnar file format; Delta adds a transaction log, table semantics, and engine-backed ACID features over Parquet files.

**16. Can you read a Delta table accurately by globbing all `*.parquet` files?** No; old files evicted by the transaction log remain physically on disk prior to vacuuming.

**17. Why do small files slow down queries?** They multiply metadata listing, file-open I/O, task scheduling, and management overhead.

**18. Should every batch call `coalesce(1)` to minimize file counts?** No. It bottlenecks parallelism and creates oversized files.

**19. Does Z-ORDER work on every SQL engine?** No. It is a Delta/Databricks-runtime optimization requiring compatibility checks.

**20. Does a function over a partition column always prevent pruning?** Not always; some optimizers rewrite or fold expressions. Prefer direct predicates and verify `EXPLAIN` and scanned bytes.

**21. Why can `SELECT *` inflate scan costs?** Columnar engines must read unnecessary columns; projecting only needed columns reduces I/O.

**22. Do serverless SQL and dedicated SQL share the same cost model?** No. Serverless typically bills per data processed, whereas dedicated bills by provisioned capacity/compute time.

**23. Does a 90% drop in bytes scanned guarantee a 90% smaller cloud bill?** No. Minimum billing floors, compute charges, maintenance, storage, and SKU rules also apply.

**24. Why do gold pre-aggregations save money?** Frequent BI queries read compact summary tables instead of repeatedly scanning billions of raw rows, trading off against refresh and consistency overhead.

**25. Should `OPTIMIZE` run across the entire table every hour?** Not by default. Compaction burns compute and only pays off when read savings exceed rewrite/maintenance costs.

**26. What must be considered before running Delta `VACUUM`?** Retention thresholds, active readers/streaming jobs, time travel, privacy deletions, and transaction log semantics.

**27. Is 99.99% data quality always good enough to publish financial reports?** Not automatically. A tiny share of missing/corrupt rows can represent millions in revenue error.

**28. Do incremental DQ checks replace full audits?** No. Pair fast batch gates with periodic or risk-based deep reconciliations.

**29. Does “Pipeline Success” guarantee correct numbers?** No. A job can succeed technically while dropping rows or miscalculating KPIs.

**30. Do resource cost tags automatically split every serverless query in a shared workspace?** No. You need job/query/user/capacity usage attribution where supported.

**31. Why does every batch need an idempotency key or checkpoint?** Retries after timeouts will duplicate records if writes simply append.

**32. What should you prepare before running a 6-month backfill?** Target partition scope, coexistence with live streams, staging/validation, budget allowance, and a rollback plan.

**33. Why avoid deleting bronze to fix gold bugs?** Bronze supports replay, auditing, and root-cause analysis; removing it destroys provenance unless mandated by retention/privacy policy.

**34. Does enabling a catalog automatically produce complete lineage?** No. Connector support, instrumentation, and custom pipeline integrations must still be verified.

**35. Can a query optimizer fix broken business-date semantics?** No. A fast query still returns wrong dates if timezone conversion logic is flawed.

**36. Why assign an owner to every DQ rule and alert?** When a rule fails, someone must be accountable for blocking, reconciling, and fixing—not just displaying red metrics.

## 41. Production Deployment Checklist

### 41.1. Data Contracts and Quality

- [ ] Every dataset has an owner, consumer list, business grain, and documented purpose.
- [ ] Data contracts, schema versions, and schema evolution policies are defined.
- [ ] Event IDs, business keys, source versions, and timezones are explicit.
- [ ] Tests cover completeness, validity, uniqueness, consistency, accuracy, and freshness.
- [ ] Critical rules trigger fail/hold-publish gates rather than passive logging.
- [ ] Quarantine captures reasons, provenance, replay workflows, and tight access/retention controls.
- [ ] Row, batch, and cross-table checks record accurate denominators and sample sizes.
- [ ] Financial metrics reconcile against source ledgers at defined business cutoffs.
- [ ] Invalid amounts never silently coerce to zero, and raw events are never dropped without audit.
- [ ] KPIs expose data-as-of, finalized, and restated states when late data arrives.

### 41.2. Ingestion, CDC, and Incremental Correctness

- [ ] Bronze retains complete source metadata and replay semantics per policy.
- [ ] Source/CDC streams carry sequences or offsets reliable within their scope.
- [ ] Silver deduplicates at the proper grain without erasing legitimate state transitions.
- [ ] CDC inserts, updates, deletes, and tombstones are handled explicitly.
- [ ] Checkpoints advance only after durable target commits.
- [ ] Re-running the same batch never duplicates silver or gold rows.
- [ ] Backfills run through staging/tests and coexist safely with live streaming jobs.
- [ ] Late events and watermarks are tested around midnight boundary timestamps.
- [ ] Schema and KPI updates follow staged producer/consumer compatibility rollouts.
- [ ] Data subject deletion traces lineage across all derived copies.

### 41.3. Partitioning and File Layout

- [ ] Query workloads, common filter predicates, and data growth have been profiled.
- [ ] Partition keys and granularity match read query patterns rather than writer convenience alone.
- [ ] Cardinality, skew, hot partitions, and tiny-partition risk have been checked.
- [ ] Physical table partitioning is clearly distinguished from Spark execution repartitioning.
- [ ] Parquet, Delta, or another table format fits engine capabilities and transaction needs.
- [ ] File sizes and files-per-partition counts are monitored.
- [ ] Compaction and maintenance policies are backed by clear cost-benefit analysis.
- [ ] Partition pruning and column pushdown are verified via explain plans and scan metrics.
- [ ] Clustering / Z-ORDER / liquid clustering is applied only where runtime-supported.
- [ ] Physical files inside transactional tables are never moved or deleted manually.
- [ ] Time travel, `VACUUM`, and retention align with streaming readers and compliance.

### 41.4. Compute and Cost Optimization

- [ ] Pricing model of the exact Azure service and tier is verified.
- [ ] Baselines exist for bytes scanned, query latency, job duration, and recurring spend.
- [ ] Common queries filter/project explicitly and avoid unnecessary `SELECT *`.
- [ ] Gold aggregates/materializations serve hot BI paths where justified.
- [ ] Spark and dedicated compute use auto-stop, pause, or schedules where supported and SLA-safe.
- [ ] Incremental processing is preferred over full refreshes when unnecessary.
- [ ] Compaction, backfills, and DQ checks include maintenance costs in ROI tracking.
- [ ] Cross-region data movement and network egress are quantified.
- [ ] Storage lifecycle policies never break live data lake or table transaction logs.
- [ ] Budgets, cost tags/usage attribution, and cost anomaly alerts have assigned owners.
- [ ] Query benchmarks confirm identical output correctness on the same snapshot.

### 41.5. Security, Operations, and Recovery

- [ ] ADLS, catalogs, and compute identities follow least-privilege RBAC and ACLs.
- [ ] Secrets, tokens, and PII are excluded from logs, notebooks, and metric labels.
- [ ] Networking, encryption, private endpoints, and data residency are reviewed.
- [ ] Row- and column-level controls are enforced at the actual data access layer.
- [ ] Catalog and lineage identify downstream reports affected by schema or quality issues.
- [ ] Observability connects source → bronze → silver → gold → consumers.
- [ ] DQ, freshness, and cost-regression alerts specify thresholds, windows, owners, and runbooks.
- [ ] Runbooks exist for report mismatches, slow queries, small files, and backfills.
- [ ] Pipelines have unit/integration/regression tests, release approvals, and rollback plans.
- [ ] Tests cover missing sources, empty batches, duplicate CDC, late events, and corrupt files.
- [ ] Data failing critical quality gates is confirmed blocked from publishing.
- [ ] Replay/backfill drills are practiced for failures occurring after partial writes.

## 42. Conclusion

**Data quality, partitioning, and analytics cost optimization** form three pillars of one unified design. Data contracts, **quality gates**, quarantine workflows, reconciliation, and lineage keep silver and gold layers trustworthy for business decisions. **Partitioning, Parquet, Delta Lake, clustering, data skipping, and compaction** pay off only when tailored to real query patterns and data volumes—without spawning millions of tiny files or destroying historical provenance. Likewise, incremental processing, pre-aggregation, auto-stopping compute, and storage lifecycle policies must be judged on **total cost**, not isolated micro-benchmarks.

On Azure, match the capabilities of **ADLS Gen2, Azure Data Factory, Azure Synapse Analytics, Azure Databricks, Microsoft Fabric, or equivalent services** to each workload and tier. Track **result accuracy, data readiness timestamps, bytes scanned, run cost, query latency, and quality incidents** together. When pipelines replay safely, every rule has an owner, dashboards advertise data-as-of/cutoff clearly, and spend is attributed by data product, your analytics platform can scale while remaining trustworthy and auditable.

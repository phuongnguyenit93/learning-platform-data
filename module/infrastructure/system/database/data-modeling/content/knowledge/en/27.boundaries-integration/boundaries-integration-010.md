# Tracking the Lineage of Replicated or Aggregated Data

A report displays **net sales of 800,000 VND** for an enterprise customer for the day. Where did that number come from? How many order lines and refund transactions contributed to it? Was it calculated by order date, payment date, or refund date? At the time the report ran, which data sources had finished syncing? If a transaction is corrected or a calculation rule changes, can we determine **which downstream metrics and target tables are affected**?

That is the problem of **data lineage / data provenance**: describing **where data came from, which steps it passed through, under which rules and versions, at what time, and where it ended up**. When data is replicated across services, moved from OLTP to an analytical warehouse, normalized from multiple sources, or aggregated into a dashboard, knowing only the target table name is not enough to explain or audit the results.

This lesson belongs to the **Boundaries and Integration** chapter of the **DATABASE_DATA_MODELING** module. The goal is to design data boundaries with clear grain, keys, sources of truth, history, and constraints; store evidence for replication and transformation operations; trace backward from an aggregated metric to source records; and avoid conflating **lineage**, **audit logs**, **request tracing**, and **guarantees that data has synced completely**.

## 1. Why Replication and Aggregation Obscure Origin

In a small system, a single table might serve as both the place of entry and the place of display. As the system grows, information typically crosses multiple boundaries:

~~~text
Order Service (PostgreSQL)
    -> outbox / CDC / batch export
    -> landing / raw zone
    -> normalized table
    -> fact table
    -> daily aggregation
    -> dashboard / API / shared file
~~~

Each step can change how data is represented:

- **Renaming and type changes:** the source has column **amount_minor_units**, while the warehouse stores **amount_vnd**.
- **Grain changes:** many order lines become a single row of **sales by tenant–day**.
- **Filtering:** excluding canceled events, out-of-domain records, or unverified data.
- **Deduplication:** multiple retried messages for the same event are counted only once.
- **Enrichment:** joining transaction lines with customer, product, region, or exchange rate data.
- **Conversion and calculation:** rounding, applying refund policies, adding/subtracting, and period classification.
- **State changes over time:** the source updates information, but the replica or dashboard has not received it yet.

Without recording the **relationship between inputs and outputs**, consumers of the numbers only see the final result and cannot tell how that result was formed.

### 1.1. Example of a Hard-to-Explain Discrepancy

Two dashboards both pull sales data yet return different numbers:

| Dashboard | Result | Actual Calculation |
| --- | ---: | --- |
| A: ordered sales | 900,000 VND | Sum of confirmed order lines on Nov 20 |
| B: net sales after refunds | 800,000 VND | 900,000 VND minus 100,000 VND in refunds recorded the same day |

Both results can **both be correct** if their metric definitions and recognition timestamps differ. The bug is not necessarily in SQL; the bug may be that both dashboards share an ambiguous **revenue** label without definitions or lineage metadata.

### 1.2. Three Questions That Must Be Answered

1. **Source:** Which systems, datasets, versions, and records were used?
2. **Transformation:** Which rules ran, under which job/version, with what parameters and data cutoff timestamp?
3. **Target:** Which records, metrics, dashboards, or APIs depend on that result?

Querying **from source to dependent targets** helps assess the impact of correcting data or changing schemas (*impact analysis*). Querying **from target back to contributing sources** helps explain a number (*root cause / audit trail*). Both directions matter.

## 2. Distinguishing Lineage, Provenance, Audit Logs, and Distributed Tracing

| Concept | Focus | Example Question |
| --- | --- | --- |
| **Data lineage** | Path and dependency relationships of data across datasets/columns/processing steps | Which source tables does this reporting table depend on? |
| **Data provenance** | Concrete evidence explaining how a piece of data or result was produced | Which exact events and formula produced the 800,000 sales row? |
| **Audit log** | Who/which system read, modified, deleted, or approved something; and when | Who adjusted the refund amount at 15:00? |
| **Distributed trace** | Which services a request traversed and how long each took | How did the order creation HTTP request flow through Order, Payment, and Notification? |
| **Data observability** | Quality, freshness, volume, schema, pipeline failures | Is the replica 30 minutes late or missing 500 rows? |
| **Data catalog / contract** | Meaning, owner, grain, schema, and usage policy | Who defines, owns, and refreshes the **net_sales_vnd** field? |

These tools can be combined, but they are **not identical**:

- A **trace_id** proves which services participated in handling a request; it **does not by itself prove** that every record in a report originated from that request.
- An **audit log** records who edited an amount; it **does not automatically link** that amount to every summary table that needs recalculation.
- A pipeline DAG showing table A → B → C is **not enough** to explain specifically which rows of C depend on which rows of A.
- An **ingested_at** timestamp tells when the replica was received; it **does not confirm** that the source has delivered all events.

In this lesson, we use **lineage** in the broad sense, which can include metadata at the dataset, job, column, and record levels; we use **provenance** when we need exact evidence for a specific result.

## 3. Locking Down Source of Truth, Grain, and Boundaries Before Choosing Tools

### 3.1. Source of Truth per Fact

A system can have multiple sources of truth, **each owning one kind of fact**:

| Fact | Example Owner | Replicated Data |
| --- | --- | --- |
| Confirmed order line, finalized price | **Order Service** | CDC/raw orders, fact sale |
| Settled refund | **Payment/Refund Service** | raw refunds, fact refund |
| Current customer name | **Customer Service** | current dim_customer |
| Historical customer segment | Customer source with SCD policy | dim_customer versions |
| Daily net sales | **Approved analytical rule** | Summary/reporting table |

An aggregated table is **derived** from source facts. It can be the **serving source** for a dashboard, but it does not become the authority on whether an original order line amount is right or wrong.

When a replica appears to differ from the source, you must know:

- How much lag is it allowed to have?
- Is it storing a **historical snapshot** instead of the current value?
- Does it apply different filtering or normalization rules?
- Is it waiting on records from another system to be complete?

You should not assume “an older replica is wrong” when it represents **as-of** data at a published point in time.

### 3.2. What Does One Row Represent?

Accurate lineage starts with the **grain** of each layer:

~~~text
raw_sale_events:
    one source version of a confirmed sale line

raw_refund_events:
    one source version of a settled refund event

run_financial_events:
    one normalized financial event in a pipeline run

daily_tenant_sales:
    one tenant on a report date, belonging to a pipeline run
~~~

If you omit **run_id** from the result identifier while still wanting to keep multiple historical runs, separate runs can **overwrite one another**. If you omit **source_event_id**, you cannot deduplicate retried events or trace back accurately. If you use the **ingested_at** date instead of the business date without confirmation, metrics can be booked into the wrong period.

### 3.3. Minimum Information for a Replicated Record

A replica can store or link to:

| Metadata | Purpose |
| --- | --- |
| **source_system / source_dataset** | Identifies the owning source and original table/stream |
| **source_record_id** | Stable record key within the source's scope |
| **source_version / source_sequence** | Distinguishes versions and edit order of the same record |
| **occurred_at / effective_at** | Business timestamp when the event occurred or took effect |
| **ingested_at** | Timestamp when the target system received the replica |
| **run_id** | Which job/batch produced the record |
| **transform_version** | Version of rules, code, or configuration applied |
| **source_cutoff / watermark** | Point up to which data is allowed to be read, and source completeness level |
| **quality_status / rejection_reason** | Whether the record was accepted, quarantined, or rejected and why |

Not every fact table needs **every field** stored directly on every row. You can link via a job-run metadata table or a dedicated lineage store. The key requirement is **being able to retrieve the information consistently at an acceptable cost**.

## 4. Lineage Granularity Levels and Their Costs

| Level | Example | Can Answer | Limitations |
| --- | --- | --- | --- |
| **Dataset/table-level** | raw_sales → financial_events → daily_sales | Which datasets depend on which datasets? | Cannot tell which rows contributed to a specific number |
| **Column-level** | raw_sales.gross_vnd → signed_amount_vnd → gross_vnd | Which source columns calculate a target column? | Does not fully describe filter conditions or records |
| **Job/run-level** | run 9001, transform v1.0, cutoff 00:00 | Which run produced this report version? | Does not replace per-row source IDs |
| **Record-level** | (raw_sales, O1001-L1, rev1) → event E → daily row T01/20-11 | Which records affected a report row? | Storage and ID management overhead |
| **Contribution-level** | event E contributes +300,000 VND to gross | Why does the total have this value? | Must preserve formulas, filters, signs, and allocations |
| **Field/value-level** | currency, FX rate, rounding policy produce amount_vnd | How was this specific value converted? | Requires detailed metadata and testing |

**Record-level lineage is not needed for all data.** Dataset-level lineage combined with run/version tracking and reconciliation checks may be sufficient for an anonymized experimental summary table. Conversely, if a financial report must explain every transaction or detect the impact of a single refund, recording only the DAG name is insufficient.

### 4.1. Source–Target Relationships Are Often Many-to-Many

One source record can contribute to many tables/metrics; one aggregated row usually draws from many sources. You can model lineage as a **directed graph**:

~~~mermaid
flowchart LR
    SALES[("Order Service: sale lines")]
    REFUNDS[("Refund Service: refund events")]
    RAW1[("Raw sales: immutable versions")]
    RAW2[("Raw refunds: immutable versions")]
    RUN["Transform v1.0 / run 9001"]
    EVENTS[("Normalized financial events")]
    DAILY[("Daily tenant sales")]
    DASH["Dashboard"]
    AUDIT["Lineage / run metadata"]
    SALES --> RAW1
    REFUNDS --> RAW2
    RAW1 --> RUN
    RAW2 --> RUN
    RUN --> EVENTS
    EVENTS --> DAILY
    DAILY --> DASH
    RUN -. "version, cutoff" .-> AUDIT
    EVENTS -. "source ID / revision" .-> AUDIT
    DAILY -. "run ID / grain" .-> AUDIT
~~~

Solid lines show transformation/read flows; metadata links store evidence. If a pipeline performs **JOINs**, **dedup**, or **filtering**, the dataset graph is only part of the story: you must also record the **record selection and exclusion rules**.

## 5. End-to-End Scenario: Net Sales by Tenant and Day

Suppose a SaaS platform processes transactions for multiple **tenants**. We need an analytical metric:

> **net_sales_vnd** of a tenant on a Vietnam local date = sum of **confirmed** sale line values occurring on that date, minus the sum of **settled refund events** occurring on the same date.

This is an **illustrative definition of event-based net sales**; it is **not automatically accounting revenue**. A refund on Nov 21 for an order sold on Nov 20 is subtracted **on Nov 21**, because the metric uses the date the refund occurred. If the business wants to adjust back to the original sale date, the calculation rule and lineage must change.

Confirmed design decisions for the example:

1. **Order Service** owns confirmed sale lines. Each line has a unique **source_event_id** within the source and a **source_version** that increments on edits.
2. **Refund Service** owns settled refund events. Each refund event has its own ID and revision.
3. Both sources use **VND**, and every monetary amount is a positive integer in VND. No foreign currency conversion is performed in this example.
4. The raw replica retains **immutable source versions** instead of keeping only the latest value.
5. Each pipeline run has a fixed **run_id**, **transform_version**, and **source_cutoff_at**.
6. The pipeline selects the **highest version ingested before the cutoff** for each source event, and then keeps only versions that are **not deleted**.
7. **Sales** contribute positive amounts; **refunds** contribute negative amounts. The normalized grain is **one selected source event within one run**.
8. The aggregated table has grain **(run_id, tenant_id, report_date)**; multiple runs are retained to explain previously published results.

Data flow:

~~~mermaid
flowchart TD
    OS["Order Service: sale lines"]
    RS["Refund Service: refunds"]
    RAW_S[("raw_sale_versions")]
    RAW_R[("raw_refund_versions")]
    SELECT["Select revision by cutoff"]
    NORMALIZE["Normalize VND, sign, and date"]
    LEDGER[("run_financial_events")]
    GROUP["GROUP BY tenant, report_date"]
    DAILY[("daily_tenant_sales")]
    REPORT["Dashboard / data API"]
    RUN[("etl_runs: run_id + version + cutoff")]
    OS --> RAW_S
    RS --> RAW_R
    RAW_S --> SELECT
    RAW_R --> SELECT
    SELECT --> NORMALIZE
    NORMALIZE --> LEDGER
    LEDGER --> GROUP
    GROUP --> DAILY
    DAILY --> REPORT
    RUN -. "config" .-> SELECT
    RUN -. "trace" .-> LEDGER
    RUN -. "version" .-> DAILY
~~~

### 5.1. Why Do We Need an Intermediate Normalized Events Layer?

If **daily_tenant_sales** only contains totals, we still know which tenant/date a result belongs to, but it is hard to determine **which source events contributed how much**. The **run_financial_events** table keeps one row per selected event, along with its source dataset, ID, revision, run, and contributed amount.

With that in place:

- You can trace **total → normalized events → exact raw revision**.
- You can recompute the totals with SQL to verify them.
- You can determine **which aggregated row** a source event contributes to.
- You can compare two runs with the same or different cutoffs/versions.

The trade-off is that the normalized events table can grow large. In systems with billions of events, consider partitioning, retention, indexing, storing metadata at a different granularity, or retrieving raw records from object storage. Do not duplicate entire source records into every table just to “have lineage”.

## 6. PostgreSQL DDL: Immutable Raw Sources and Run Metadata

The SQL snippets in Sections 6–9 form **one consistent example** meant to run in sequence on a PostgreSQL database or an empty practice schema. To avoid depending on external data, the code uses fixed dataset names **raw_sales** and **raw_refunds**; each source ID is assumed unique within **each dataset**.

### 6.1. Storing Sale Line Versions

~~~sql
CREATE TABLE raw_sale_versions (
    source_event_id TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version > 0),
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    gross_vnd NUMERIC(20, 0) NOT NULL CHECK (gross_vnd > 0),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'VND'),
    ingested_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (source_event_id, source_version)
);
~~~

**Grain:** one version published by Order Service for a sale line event. Two versions of the same source_event_id may differ in amount or effective timestamp when a correction occurs.

**is_deleted** in this example is a cancellation marker on the source record following a correction/tombstone mechanism. This illustrative model assumes tombstones still carry all required fields; real source systems may emit tombstones containing only the key and revision, in which case staging/normalization must be designed accordingly. **Do not** turn commercial order cancellations into arbitrary raw deletions: the rule for recording adjustment events must be explicitly confirmed.

### 6.2. Storing Refund Event Versions

~~~sql
CREATE TABLE raw_refund_versions (
    source_event_id TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version > 0),
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    refund_vnd NUMERIC(20, 0) NOT NULL CHECK (refund_vnd > 0),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'VND'),
    ingested_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (source_event_id, source_version)
);
~~~

One sale line can have **multiple partial refund events**. Do not use order_id as the refund event key. If the source emits a distinct event ID per refund, refunds R01 and R02 must be uniquely identified and not duplicated on retries.

**Note on uniqueness:** in this example, source_event_id is unique **within the dataset**. If a source service only guarantees uniqueness **per tenant** or per stream partition, the raw key must include tenant_id/stream_id accordingly; do not enforce a global UNIQUE constraint that rejects valid events.

### 6.3. Pipeline Run Metadata Table

~~~sql
CREATE TABLE etl_runs (
    run_id BIGINT PRIMARY KEY,
    transform_name TEXT NOT NULL,
    transform_version TEXT NOT NULL,
    source_cutoff_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);
~~~

In production, you can also store **code_commit_sha**, image/container digest, calculation configuration, list of datasets/versions, idempotency key, triggering user/flow, schema version, and **per-source** checkpoints/watermarks. A single shared **source_cutoff_at** in this example only restricts rows ingested before that timestamp; **it does not prove that both sources have finished syncing up to the same business timestamp**.

### 6.4. Normalized Events Table with Source Provenance

~~~sql
CREATE TABLE run_financial_events (
    run_id BIGINT NOT NULL REFERENCES etl_runs(run_id),
    source_dataset TEXT NOT NULL
        CHECK (source_dataset IN ('raw_sales', 'raw_refunds')),
    source_event_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    source_ingested_at TIMESTAMPTZ NOT NULL,
    event_kind TEXT NOT NULL
        CHECK (event_kind IN ('SALE', 'REFUND')),
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    report_date DATE NOT NULL,
    signed_amount_vnd NUMERIC(20, 0) NOT NULL,
    PRIMARY KEY (run_id, source_dataset, source_event_id),
    CHECK (
        (event_kind = 'SALE' AND signed_amount_vnd > 0)
        OR
        (event_kind = 'REFUND' AND signed_amount_vnd < 0)
    )
);
~~~

The key **(run_id, source_dataset, source_event_id)** ensures **each source event is selected at most once within the same run**. **source_version** records the exact revision selected. Because data comes from **two different raw tables**, a polymorphic FOREIGN KEY keyed by source_dataset cannot be automatically enforced by a standard SQL FK; revision matching is verified during ingestion and reconciliation queries. If full declarative FKs are required, you can use a shared source registry table or two separate lineage tables.

### 6.5. Run-Versioned Aggregated Table

~~~sql
CREATE TABLE daily_tenant_sales (
    run_id BIGINT NOT NULL REFERENCES etl_runs(run_id),
    tenant_id TEXT NOT NULL,
    report_date DATE NOT NULL,
    gross_vnd NUMERIC NOT NULL CHECK (gross_vnd >= 0),
    refund_vnd NUMERIC NOT NULL CHECK (refund_vnd >= 0),
    net_vnd NUMERIC
        GENERATED ALWAYS AS (gross_vnd - refund_vnd) STORED,
    PRIMARY KEY (run_id, tenant_id, report_date)
);

CREATE INDEX idx_financial_events_run_day
ON run_financial_events (run_id, tenant_id, report_date);
~~~

**net_vnd** can be negative on a day when refunds exceed new sales; do not add a **net_vnd >= 0** constraint just because no negative values appear in sample data. Using **NUMERIC** for totals avoids machine-integer overflow limits, in exchange for its own storage/compute cost.

Keeping **run_id in the primary key** allows multiple report versions for the same tenant/day. A **latest_successful_report** table or view serving dashboards can point to the published version according to policy; it does not replace run records or source evidence.

## 7. Sample Data: Two Source Systems, Two Event Types

Load five sale events and two refund events. All are at revision 1 and ingested before the sample run cutoff:

~~~sql
INSERT INTO raw_sale_versions (
    source_event_id, source_version, tenant_id, order_id,
    occurred_at, gross_vnd, currency_code, ingested_at
) VALUES
    ('O1001-L1', 1, 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-20 09:00:00+07', 300000, 'VND',
     TIMESTAMPTZ '2026-11-20 09:01:00+07'),
    ('O1001-L2', 1, 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-20 09:00:00+07', 200000, 'VND',
     TIMESTAMPTZ '2026-11-20 09:02:00+07'),
    ('O1002-L1', 1, 'T01', 'O1002',
     TIMESTAMPTZ '2026-11-20 11:00:00+07', 400000, 'VND',
     TIMESTAMPTZ '2026-11-20 11:02:00+07'),
    ('O1003-L1', 1, 'T01', 'O1003',
     TIMESTAMPTZ '2026-11-21 09:00:00+07', 150000, 'VND',
     TIMESTAMPTZ '2026-11-21 09:04:00+07'),
    ('O2001-L1', 1, 'T02', 'O2001',
     TIMESTAMPTZ '2026-11-20 14:00:00+07', 700000, 'VND',
     TIMESTAMPTZ '2026-11-20 14:03:00+07');

INSERT INTO raw_refund_versions (
    source_event_id, source_version, tenant_id, order_id,
    occurred_at, refund_vnd, currency_code, ingested_at
) VALUES
    ('RF1001', 1, 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-20 16:00:00+07', 100000, 'VND',
     TIMESTAMPTZ '2026-11-20 16:01:00+07'),
    ('RF1002', 1, 'T01', 'O1002',
     TIMESTAMPTZ '2026-11-21 15:00:00+07', 50000, 'VND',
     TIMESTAMPTZ '2026-11-21 15:01:00+07');
~~~

The sources in this example have confirmed that sale and refund amounts are the final figures for **each event**. If Order Service also emits DRAFT/CONFIRMED status update events for the same line, you must not sum all status transitions as separate transactions. You must define which event types represent financial contributions and how to select the current revision.

### 7.1. Expected Results Before Running ETL

| tenant_id | report_date | Sale Amount | Refund Amount | Net Sales |
| --- | --- | ---: | ---: | ---: |
| T01 | 2026-11-20 | 900,000 | 100,000 | 800,000 |
| T01 | 2026-11-21 | 150,000 | 50,000 | 100,000 |
| T02 | 2026-11-20 | 700,000 | 0 | 700,000 |

This is **calculated by sale/refund occurrence date** in the **Asia/Ho_Chi_Minh** timezone. The example excludes taxes, shipping, currency conversion, and accounting revenue recognition. In real reports, these conditions must be captured in the **data contract and calculation version**.

## 8. Traceable Pipeline: From Raw to Normalized Events

To make each report reproducible, a run must freeze **at least** the logic version and the input scope. In the example:

~~~text
run_id             = 9001
transform_name     = daily_net_sales
transform_version  = v1.0
source_cutoff_at   = 2026-11-22 00:00:00 +07
report timezone    = Asia/Ho_Chi_Minh
~~~

**source_cutoff_at** bounds the time the system **ingested** the raw event; it is not the transaction occurrence time. A line transacted on Nov 20 but ingested on Nov 23 **does not belong** to run 9001. This allows viewers to explain why two runs with different cutoffs produce different numbers.

### 8.1. Selecting the Right Source Event Version

If a source_event_id has revisions 1, 2, and 3, we must select the **highest revision ingested before the cutoff**. In PostgreSQL, we can use **DISTINCT ON** with explicit ordering:

~~~sql
SELECT DISTINCT ON (source_event_id)
    source_event_id,
    source_version,
    gross_vnd,
    ingested_at,
    is_deleted
FROM raw_sale_versions
WHERE ingested_at <= TIMESTAMPTZ '2026-11-22 00:00:00+07'
ORDER BY
    source_event_id,
    source_version DESC,
    ingested_at DESC;
~~~

**Do not filter is_deleted = FALSE before selecting the revision.** If the latest version is a tombstone, filtering out tombstones first will cause an older revision of the same event to be resurrected incorrectly. Select the revision first, then exclude events whose **selected revision** is marked deleted.

This rule assumes **source_version increases monotonically per source_event_id**; if the source does not guarantee this, use the source sequence/commit log position or another reliable ordering. Relying solely on ingestion time to pick “latest” can fail when events arrive out of order.

### 8.2. Running Normalization and Aggregation in One Transaction

The following snippet continues from the sample data in Section 7. It creates the run, selects versions from both sources, maps them into signed event amounts, aggregates by **tenant_id and report_date**, and marks the run as succeeded:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

INSERT INTO etl_runs (
    run_id, transform_name, transform_version,
    source_cutoff_at, started_at, status
) VALUES (
    9001, 'daily_net_sales', 'v1.0',
    TIMESTAMPTZ '2026-11-22 00:00:00+07',
    CURRENT_TIMESTAMP, 'RUNNING'
);

WITH config AS (
    SELECT run_id, source_cutoff_at
    FROM etl_runs
    WHERE run_id = 9001
),
sales_latest AS (
    SELECT DISTINCT ON (s.source_event_id)
        s.*
    FROM raw_sale_versions AS s
    CROSS JOIN config AS c
    WHERE s.ingested_at <= c.source_cutoff_at
    ORDER BY
        s.source_event_id,
        s.source_version DESC,
        s.ingested_at DESC
),
refunds_latest AS (
    SELECT DISTINCT ON (r.source_event_id)
        r.*
    FROM raw_refund_versions AS r
    CROSS JOIN config AS c
    WHERE r.ingested_at <= c.source_cutoff_at
    ORDER BY
        r.source_event_id,
        r.source_version DESC,
        r.ingested_at DESC
)
INSERT INTO run_financial_events (
    run_id, source_dataset, source_event_id, source_version,
    source_ingested_at, event_kind, tenant_id, order_id,
    occurred_at, report_date, signed_amount_vnd
)
SELECT
    c.run_id,
    'raw_sales',
    s.source_event_id,
    s.source_version,
    s.ingested_at,
    'SALE',
    s.tenant_id,
    s.order_id,
    s.occurred_at,
    (s.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
    s.gross_vnd
FROM sales_latest AS s
CROSS JOIN config AS c
WHERE NOT s.is_deleted

UNION ALL

SELECT
    c.run_id,
    'raw_refunds',
    r.source_event_id,
    r.source_version,
    r.ingested_at,
    'REFUND',
    r.tenant_id,
    r.order_id,
    r.occurred_at,
    (r.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
    -r.refund_vnd
FROM refunds_latest AS r
CROSS JOIN config AS c
WHERE NOT r.is_deleted;

INSERT INTO daily_tenant_sales (
    run_id, tenant_id, report_date, gross_vnd, refund_vnd
)
SELECT
    run_id,
    tenant_id,
    report_date,
    SUM(
        CASE WHEN event_kind = 'SALE'
             THEN signed_amount_vnd ELSE 0 END
    ) AS gross_vnd,
    SUM(
        CASE WHEN event_kind = 'REFUND'
             THEN -signed_amount_vnd ELSE 0 END
    ) AS refund_vnd
FROM run_financial_events
WHERE run_id = 9001
GROUP BY run_id, tenant_id, report_date;

UPDATE etl_runs
SET status = 'SUCCEEDED',
    completed_at = clock_timestamp()
WHERE run_id = 9001;

COMMIT;
~~~

Because raw data is loaded beforehand and the transaction uses **REPEATABLE READ**, the queries see a consistent snapshot as of the start of the transaction. **Reproducibility across runs still requires immutable raw sources, sufficient retention, and stable revision-selection rules.** Recording a cutoff while allowing in-place updates to raw records or backdating ingested_at is not sufficient.

**Important notes:**

- **UNION ALL** is appropriate because sales and refunds are two distinct sets of events; using UNION to deduplicate unintentionally could drop an event.
- **source_dataset** accompanies **source_event_id** to prevent collisions if two systems generate identical IDs.
- **source_version** and **source_ingested_at** are preserved so you can look up the exact raw version.
- **report_date** is derived from **occurred_at** in the confirmed timezone, not inferred from **ingested_at**.
- **run_id** is placed on both normalized events and aggregated rows so two runs are never mixed.
- In the sample, all monetary values are already in VND; if multiple currencies exist, you must attach **currency, fx_rate_id, rate_timestamp, round_policy/version** and never sum different currencies directly.
- **status = SUCCEEDED** means the SQL step completed; **it does not prove** that inputs from both sources were complete. Additional checks and publishing rules are covered in Section 11.

If the transaction fails before COMMIT, the run/event/aggregate records created by this transaction are rolled back. In pipelines spanning multiple systems or object storage, a single SQL transaction cannot cover all steps; you must use staging, checkpoints, and controlled publish mechanisms instead of assuming free distributed transactions.

### 8.3. Viewing Results of a Run

~~~sql
SELECT
    d.run_id,
    d.tenant_id,
    d.report_date,
    d.gross_vnd,
    d.refund_vnd,
    d.net_vnd,
    r.transform_version,
    r.source_cutoff_at
FROM daily_tenant_sales AS d
JOIN etl_runs AS r ON r.run_id = d.run_id
WHERE d.run_id = 9001
  AND r.status = 'SUCCEEDED'
ORDER BY d.tenant_id, d.report_date;
~~~

Expected output:

| run_id | tenant | date | gross_vnd | refund_vnd | net_vnd |
| ---: | --- | --- | ---: | ---: | ---: |
| 9001 | T01 | 2026-11-20 | 900000 | 100000 | 800000 |
| 9001 | T01 | 2026-11-21 | 150000 | 50000 | 100000 |
| 9001 | T02 | 2026-11-20 | 700000 | 0 | 700000 |

In total there are **7 records in run_financial_events** (5 sales, 2 refunds), producing **3 rows in daily_tenant_sales**. These numbers are derived from the sample dataset; this lesson does not claim to have executed them against a live database instance.

## 9. Tracing Lineage Backward and Forward with SQL

### 9.1. From an Aggregate Total Back to Contributing Events

Because aggregated rows carry **run_id, tenant_id, report_date**, we can join back to the exact grain of normalized events:

~~~sql
SELECT
    d.run_id,
    d.tenant_id,
    d.report_date,
    e.source_dataset,
    e.source_event_id,
    e.source_version,
    e.event_kind,
    e.order_id,
    e.signed_amount_vnd,
    e.source_ingested_at
FROM daily_tenant_sales AS d
JOIN run_financial_events AS e
  ON e.run_id = d.run_id
 AND e.tenant_id = d.tenant_id
 AND e.report_date = d.report_date
WHERE d.run_id = 9001
  AND d.tenant_id = 'T01'
  AND d.report_date = DATE '2026-11-20'
ORDER BY e.source_dataset, e.source_event_id;
~~~

The result returns four events:

| source_dataset | source_event_id | source_version | event_kind | signed_amount_vnd |
| --- | --- | ---: | --- | ---: |
| raw_refunds | RF1001 | 1 | REFUND | -100000 |
| raw_sales | O1001-L1 | 1 | SALE | 300000 |
| raw_sales | O1001-L2 | 1 | SALE | 200000 |
| raw_sales | O1002-L1 | 1 | SALE | 400000 |

Direct reconciliation:

~~~text
Gross     = 300000 + 200000 + 400000 = 900000
Refund    = 100000
Net sales = 300000 + 200000 + 400000 - 100000 = 800000
~~~

This is **simple contribution-level lineage**: each event contributes one whole signed amount to a single tenant/date. If a pipeline allocates a single event across **multiple dimensions or target rows** (such as splitting an order discount proportionally across line items), you need a detailed contribution table or sufficient metadata on **allocation ratios/rounding**; joining by date alone is not valid proof.

### 9.2. From Normalized Events to Exact Raw Revisions

~~~sql
SELECT
    e.source_dataset,
    e.source_event_id,
    e.source_version,
    e.signed_amount_vnd,
    s.gross_vnd AS original_sale_vnd,
    r.refund_vnd AS original_refund_vnd
FROM run_financial_events AS e
LEFT JOIN raw_sale_versions AS s
  ON e.source_dataset = 'raw_sales'
 AND s.source_event_id = e.source_event_id
 AND s.source_version = e.source_version
LEFT JOIN raw_refund_versions AS r
  ON e.source_dataset = 'raw_refunds'
 AND r.source_event_id = e.source_event_id
 AND r.source_version = e.source_version
WHERE e.run_id = 9001
  AND e.tenant_id = 'T01'
  AND e.report_date = DATE '2026-11-20'
ORDER BY e.source_dataset, e.source_event_id;
~~~

For sales, the positive value of **signed_amount_vnd** must match **gross_vnd** from raw. For refunds, the negative value must equal **-refund_vnd**. If the query cannot locate the matching raw record, the raw data may have been purged too early, the lineage key may be wrong, or the source may have moved without preserving location capability.

**Rule:** **(source_dataset, source_event_id, source_version)** is the evidence identity. Storing only order_id is insufficient because an order can have multiple sale lines, multiple refunds, and multiple revisions.

### 9.3. From a Source Record to Affected Reports

Suppose Refund Service reports an issue with event **RF1001**. Query downstream impact:

~~~sql
SELECT
    e.source_dataset,
    e.source_event_id,
    e.source_version,
    d.run_id,
    d.tenant_id,
    d.report_date,
    d.net_vnd,
    r.transform_version
FROM run_financial_events AS e
JOIN daily_tenant_sales AS d
  ON d.run_id = e.run_id
 AND d.tenant_id = e.tenant_id
 AND d.report_date = e.report_date
JOIN etl_runs AS r ON r.run_id = d.run_id
WHERE e.source_dataset = 'raw_refunds'
  AND e.source_event_id = 'RF1001'
ORDER BY d.run_id, d.report_date;
~~~

With the sample data containing only run 9001, we find row **T01 / 2026-11-20 / run 9001**. When multiple runs exist, a source event can affect **multiple report versions**, depending on revisions and the selection rules in each run.

The query above only lists **summary rows in the sample schema**. In an organization with downstream dashboards, data marts, and exported files, you also need to record **dataset-level edges** and **publish metadata** to know where the final output was shared.

### 9.4. Reconciling Aggregated Results Against Evidence

Do not trust a summary table solely because its job is marked SUCCEEDED. You can detect totals that no longer match events in the same run:

~~~sql
WITH recalculated AS (
    SELECT
        run_id,
        tenant_id,
        report_date,
        SUM(CASE WHEN event_kind = 'SALE'
                 THEN signed_amount_vnd ELSE 0 END) AS gross_vnd,
        SUM(CASE WHEN event_kind = 'REFUND'
                 THEN -signed_amount_vnd ELSE 0 END) AS refund_vnd
    FROM run_financial_events
    GROUP BY run_id, tenant_id, report_date
)
SELECT
    d.run_id,
    d.tenant_id,
    d.report_date,
    d.gross_vnd,
    d.refund_vnd,
    c.gross_vnd AS recalculated_gross_vnd,
    c.refund_vnd AS recalculated_refund_vnd
FROM daily_tenant_sales AS d
JOIN recalculated AS c
  ON c.run_id = d.run_id
 AND c.tenant_id = d.tenant_id
 AND c.report_date = d.report_date
WHERE d.gross_vnd <> c.gross_vnd
   OR d.refund_vnd <> c.refund_vnd;
~~~

On the sample data, this query **returns no rows**. Because it uses an INNER JOIN, it **does not detect** a group that exists only in the events table and not in the summary table, or vice versa. For a complete check, use a **FULL OUTER JOIN** on the group key, or reconcile key sets with a **two-way EXCEPT**; do not compare values only for matching groups.

Example checking for missing or extra group rows:

~~~sql
WITH source_groups AS (
    SELECT DISTINCT run_id, tenant_id, report_date
    FROM run_financial_events
)
SELECT run_id, tenant_id, report_date
FROM source_groups
EXCEPT
SELECT run_id, tenant_id, report_date
FROM daily_tenant_sales;

SELECT run_id, tenant_id, report_date
FROM daily_tenant_sales
EXCEPT
SELECT DISTINCT run_id, tenant_id, report_date
FROM run_financial_events;
~~~

Both queries must return empty results for a completed run if the summary table is accurately defined by those events. Passing this reconciliation **does not by itself prove** that all source events were ingested completely or that the business formula is right; those are separate checks.

## 10. Replicating Across Service Boundaries: Event Contracts and Trace Points

At the Order Service → analytical warehouse boundary, you may choose **batch export**, **outbox**, **CDC**, or an event stream consumer. None of these techniques solves lineage automatically if messages lack the required identity and semantics.

### 10.1. Message Envelope Fields Worth Preserving

Example source event:

~~~json
{
  "event_id": "O1001-L1",
  "event_type": "OrderLineConfirmed",
  "schema_version": 2,
  "aggregate_id": "O1001",
  "aggregate_version": 1,
  "tenant_id": "T01",
  "occurred_at": "2026-11-20T09:00:00+07:00",
  "published_at": "2026-11-20T09:00:01+07:00",
  "payload": {
    "line_no": 1,
    "currency_code": "VND",
    "gross_vnd": 300000
  }
}
~~~

This is only an **illustrative event contract**. In many systems, **event_id is the immutable ID of a single event**, while business changes emit a **new adjustment event** rather than multiple revisions under the same event_id. Our SQL example uses **source_event_id + source_version** for a versioned source; if you use an immutable event-sourcing architecture, adapt the source selection logic accordingly rather than mechanically assigning new versions to old events.

| Field | Role |
| --- | --- |
| event_id | Idempotency/deduplication within the scope guaranteed by the source |
| event_type | Determines whether this event contributes to the metric |
| schema_version | Payload decoding and compatibility management |
| aggregate_id, aggregate_version | Links to parent entity and controls ordering per aggregate |
| tenant_id | Routing, authorization, and per-customer analytics |
| occurred_at | Business occurrence timestamp |
| published_at | Timestamp when the service emitted the event; not always equal to occurred_at |
| source log position / partition / offset | Stream position evidence and checkpoint recovery if available |
| correlation_id / trace_id | Links processing flows; useful but does not replace event_id |

You do not have to cram **every field** into the business payload. Metadata can reside in the envelope/header or a suitable registry, as long as consumers **can read and preserve the link** to the source event.

### 10.2. Batch, CDC, and Outbox Have Different Lineage Requirements

| Mechanism | Traces to Keep | Risks to Handle |
| --- | --- | --- |
| **Batch export** | dataset, file/object path, checksum, snapshot ID, extract time, run ID | Duplicate files, partial exports, source mutating between pages |
| **CDC** | table/primary key, operation, source commit position, transaction ID, schema version | Ordering, tombstones, initial snapshot vs CDC catch-up, log retention |
| **Transactional outbox** | outbox event ID, aggregate ID/version, source transaction, publish checkpoint | Duplicate delivery, consumer retries, failure after commit before publish |
| **Event stream** | topic, partition, offset, event ID, producer/schema version, consumer checkpoint | Consumer replay, cross-partition reordering, schema evolution |
| **API polling** | resource ID/version, ETag or change token, page cursor, collected_at | Invisible deletes, missed updates between polls, API rate limits |

**Transactional outbox** writes business state and outbox messages in the same source transaction, reducing the risk of “recording an order without emitting an event”. It does **not** make the system end-to-end exactly-once: publishers and consumers can still process duplicates, so downstream needs event keys and idempotent ingestion.

**CDC** captures database changes, but an UPDATE on an operational table is not necessarily **a new business event to add to sales**. You must understand source semantics: use CDC to build snapshots/current state, or rely on distinct confirmed financial events rather than SUMming every row version.

### 10.3. Conditions to Prevent Double-Counting the Same Record

Define an **immutable key** and update order:

~~~text
source identity = (source_dataset, source_event_id)
source revision = source_version
selected version for run = highest accepted revision by cutoff
normalized grain = (run_id, source_dataset, source_event_id)
~~~

In ETL, verify:

1. Retries with the **same ID + same revision + same payload** must not create duplicate raw records.
2. **Same ID + same revision but different payload** is a data quality conflict; do not silently pick whichever arrived last.
3. Higher revisions must be processed according to correction rules, including tombstones.
4. Mapping errors, negative amounts, or unexpected currencies must be quarantined or raise clear errors.
5. Each event contributes **once** per run; if it belongs to multiple metrics, each metric has its own defined sum/count logic.

**Idempotency** is a property that must hold across any possible replay/retry paths. Running **SELECT DISTINCT** at the end of a pipeline is not an integrity strategy if duplicate records carry two different amounts or semantically distinct updates.

## 11. Cutoff, Watermark, Snapshot, and Completeness

### 11.1. Four Types of Timestamps Not to Mix

| Time Field | Answers | Example |
| --- | --- | --- |
| **occurred_at** | When did the transaction happen? | Sale line confirmed on Nov 20 |
| **source_committed_at / source_sequence** | When/at what position did the source commit the change? | Transaction log or sequence 581 |
| **published_at / ingested_at** | When was the message emitted and the replica received? | Event ingested on Nov 23 |
| **report_generated_at / published_at** | Since when could users view the result? | Report published morning of Nov 24 |

A transaction with **occurred_at = Nov 20** but **ingested_at = Nov 23** is **late-arriving data**. If reporting is by occurrence date, after catching up you must recalculate the impact for **Nov 20**, not book it into **Nov 23** just because that was the ingestion date.

### 11.2. Cutoff Is Not Equivalent to a Complete Source Watermark

The **cutoff** in the sample SQL:

~~~text
Only include raw records with ingested_at <= 2026-11-22 00:00 +07.
~~~

It answers **“what had we seen before this ingestion timestamp?”**. It does **not** answer **“have all source transactions occurring before this timestamp been completely received?”**.

For a complete report, a pipeline may need:

- **CDC checkpoint/offset** processed up to a trusted source position.
- **Event-time watermark** per source/partition and an allowed lateness policy.
- A **source complete** status for the file/batch or business date.
- Row counts, checksums, or monetary totals reconciled against a source export at the same grain.
- A **late-arrival window** policy and republishing procedure when late corrections arrive.

With two sources—Sales and Refunds—**watermarks must be evaluated for both**. If sales are updated through the end of the day while refunds lag by a day, you cannot call the report “complete” based on one source alone.

### 11.3. A Consistent Snapshot Differs from Reading Tables at Different Times

A pipeline might read **orders** at 10:00 and **refunds** at 10:10. New refunds may arrive in between: the numbers may not correspond to a single common point in time without a freeze policy. Options depend on the system:

- Consistent transaction snapshot within the same database.
- Per-source CDC/log checkpoints combined with completeness thresholds.
- Versioned object snapshots and a manifest specifying input datasets/versions.
- Defining the report **as-of each source**, explicitly disclosing that the two timestamps are not strictly simultaneous.

Across **two independent databases**, a PostgreSQL transaction in the analytical warehouse **does not create a distributed snapshot** at the same point in time across sources. If the business requires strong cross-service consistency, you must build an appropriate protocol or business policy rather than assuming it exists by default.

### 11.4. “Late-Arriving Data” and “Past Corrections” Are Two Distinct Cases

**Late-arriving event:** event RF1003 occurred on Nov 20 but was only ingested on Nov 23; previously the report did not contain that event.

**Correction/revision:** event RF1001 was already ingested with a refund of 100,000, and later the source emitted revision 2 correcting it to 120,000. The new version **replaces the old version** under this lesson's snapshot-version model; you must not sum 100,000 + 120,000 as two separate refunds.

Both situations lead to recalculating the same date, but deduplication works differently. To support traceability, you need to know whether a record is **newly arrived** or a **new revision of an existing record**.

## 12. Corrections, Backfills, and Rule Versioning

### 12.1. Example of an Amended Refund Event

After run 9001 is published, Refund Service sends a correction:

~~~sql
INSERT INTO raw_refund_versions (
    source_event_id, source_version, tenant_id, order_id,
    occurred_at, refund_vnd, currency_code, ingested_at
) VALUES (
    'RF1001', 2, 'T01', 'O1001',
    TIMESTAMPTZ '2026-11-20 16:00:00+07', 120000, 'VND',
    TIMESTAMPTZ '2026-11-23 09:00:00+07'
);
~~~

Run 9001 had cutoff **2026-11-22 00:00 +07**, so it **still references revision 1** and preserves **800,000 VND** for T01 on Nov 20. A new run **9002** with a cutoff after **Nov 23 09:00 +07**, using the same transform v1.0, selects **revision 2** and computes:

~~~text
T01, 2026-11-20:
  Gross  = 900000
  Refund = 120000
  Net    = 780000
~~~

To re-run on the illustrative schema, execute the same SQL workflow from Section 8.2 while **changing run_id = 9001 to 9002 and source_cutoff_at to the new timestamp**. Do not re-run the script with the same run_id because the primary key will reject it; do not UPDATE/DELETE run 9001 rows to hide previously published figures.

**Note:** if the source uses immutable events with separate adjustment events, do not use “select highest revision” instead of summing adjustment events. Clarify **event vs snapshot change** right in the source contract.

### 12.2. Result Differences Must Be Explainable

A variance report between two runs should answer:

~~~text
Report: tenant T01 / date 2026-11-20
Old run: 9001, v1.0, cutoff 22/11 00:00, net 800000
New run: 9002, v1.0, cutoff 24/11 00:00, net 780000

Delta: -20000 VND
Source: raw_refunds / RF1001
Old revision selected: 1, refund 100000
New revision selected: 2, refund 120000
Reason: correction ingested on 23/11
~~~

Do not store only a **last_updated_at** column on the report: it does not tell which run, source, revision, or rule caused the change.

A query comparing totals across runs:

~~~sql
SELECT
    old.tenant_id,
    old.report_date,
    old.net_vnd AS net_run_9001,
    new.net_vnd AS net_run_9002,
    new.net_vnd - old.net_vnd AS delta_vnd
FROM daily_tenant_sales AS old
JOIN daily_tenant_sales AS new
  ON new.tenant_id = old.tenant_id
 AND new.report_date = old.report_date
WHERE old.run_id = 9001
  AND new.run_id = 9002;
~~~

This compares **groups present in both runs**. If new data introduces a new group or removes one due to a tombstone, use a **FULL OUTER JOIN** with a policy for handling NULLs/scope changes, rather than letting an INNER JOIN hide new groups.

### 12.3. Formula Changes Differ from Source Corrections

Suppose version v1.0 uses the **actual refund date**, whereas v2.0 switches to attributing refunds back to the **original sale date**. Report results differ even though every raw record is unchanged. In this case, provenance must preserve:

- **transform_version** and deployed code/config version.
- Business definition and the approver of the change.
- Input sources and cutoff used for a fair comparison.
- JOIN rules for refund → original sale and allocation rules when a refund spans multiple lines.
- Rules for handling refunds missing references, multiple currencies, or mismatched timestamps.

**Never reuse the name “v1.0” for two different formulas.** In strict operations, bind **code SHA/image digest** and policy version to each run so you can reproduce the deployment itself, not just a human-assigned version label.

### 12.4. Controlled Backfills

When recalculating a historical window:

1. Identify the **reason**: late event, correction, formula change, or pipeline bug fix.
2. Freeze the **input set by version and cutoff**.
3. Scope the **blast radius**: tenant, date, order, partition, or entire dataset.
4. Run into **staging/a new version** without overwriting published reports before reconciliation.
5. Compare source keys, event counts, checksums/totals, and per-group deltas.
6. Record metadata: **run, transform_version, cutoff, approver, and reason**.
7. **Publish** the new version only after passing checks and source completeness gates.
8. Retain the ability to **roll back to the previously published version** per retention policy.

Lineage both helps **find the exact slices needing backfill** and helps users explain why a historical metric changed.

## 13. Storing Lineage Metadata at Dataset, Column, and Record Levels

A data catalog or pipeline orchestrator can record a **dataset dependencies** graph. At a simplified level, use a table:

~~~sql
CREATE TABLE dataset_lineage_edges (
    run_id BIGINT NOT NULL REFERENCES etl_runs(run_id),
    input_dataset TEXT NOT NULL,
    output_dataset TEXT NOT NULL,
    relation_kind TEXT NOT NULL
        CHECK (relation_kind IN ('COPY', 'NORMALIZE', 'AGGREGATE')),
    PRIMARY KEY (run_id, input_dataset, output_dataset)
);

INSERT INTO dataset_lineage_edges
    (run_id, input_dataset, output_dataset, relation_kind)
VALUES
    (9001, 'raw_sale_versions', 'run_financial_events',
     'NORMALIZE'),
    (9001, 'raw_refund_versions', 'run_financial_events',
     'NORMALIZE'),
    (9001, 'run_financial_events', 'daily_tenant_sales',
     'AGGREGATE');
~~~

These edges record **which tables fed into which tables during run 9001**; they do not replace the **source_event_id + source_version** pair stored on the event table. If you have downstream dashboards, data marts, and exported files, continue recording edges from **daily_tenant_sales** to the published dataset/artifact versions.

### 13.1. Querying Dependency Steps by Run

~~~sql
WITH RECURSIVE downstream AS (
    SELECT
        input_dataset,
        output_dataset,
        1 AS hop,
        ARRAY[input_dataset, output_dataset] AS path
    FROM dataset_lineage_edges
    WHERE run_id = 9001
      AND input_dataset = 'raw_refund_versions'

    UNION ALL

    SELECT
        d.input_dataset,
        e.output_dataset,
        d.hop + 1,
        d.path || e.output_dataset
    FROM downstream AS d
    JOIN dataset_lineage_edges AS e
      ON e.run_id = 9001
     AND e.input_dataset = d.output_dataset
    WHERE NOT e.output_dataset = ANY(d.path)
)
SELECT DISTINCT output_dataset, hop, path
FROM downstream
ORDER BY hop, output_dataset;
~~~

With the sample data, the path traverses **raw_refund_versions → run_financial_events → daily_tenant_sales**. The cycle-prevention check on `path` prevents infinite loops if metadata is misconfigured with a cycle. In production tooling, also store **dataset version**, environment, namespace, owner, and relation type; bare table names can collide across systems.

### 13.2. Column-Level Lineage Needs Both Conditions and Formulas

Example rule metadata:

| Target Column | Direct Source | Transformation |
| --- | --- | --- |
| run_financial_events.signed_amount_vnd | raw_sale_versions.gross_vnd | **Positive** sign, after revision selection and tombstone exclusion |
| run_financial_events.signed_amount_vnd | raw_refund_versions.refund_vnd | Multiply by **-1**, after revision selection and tombstone exclusion |
| run_financial_events.report_date | raw.*.occurred_at | Convert to **Asia/Ho_Chi_Minh** timezone and extract date |
| daily_tenant_sales.gross_vnd | run_financial_events.signed_amount_vnd | **SUM** where event_kind = SALE for same run/tenant/date |
| daily_tenant_sales.refund_vnd | run_financial_events.signed_amount_vnd | **-SUM** where event_kind = REFUND for same run/tenant/date |
| daily_tenant_sales.net_vnd | gross_vnd, refund_vnd | **gross_vnd - refund_vnd** |

If you only record **source column → target column** pairs while omitting **event_kind** filters, **revision selection**, **JOIN keys**, and **date rules**, column-level lineage still cannot explain the result. An expression depending on multiple sources or a source record allocated proportionally may require richer metadata.

### 13.3. When Do You Need a Contribution Bridge Table?

In our example, each normalized event belongs to exactly **one tenant/date**; you can reconstruct the list of contributors from **run_financial_events** with a JOIN as shown in Section 9. Therefore, an extra lineage bridge table is **not strictly required**.

Suppose later an order-level discount is allocated across multiple lines, products, or cost centers. Then **one source event contributes to multiple target rows**. You can use a contribution table:

~~~text
report_contributions(
    run_id,
    report_dataset,
    report_row_key,
    source_dataset,
    source_event_id,
    source_version,
    allocation_rule_version,
    contribution_vnd
)
~~~

Each row states **which source record contributed how much to which target record and under which rule**. This table can grow huge: one event appearing in 10 reports creates at least 10 links. Evaluate storage cost, retention, and strategies to recompute from immutable source data.

If you do not store a detailed bridge, at minimum keep the **input snapshot manifest, code/config version, and stable source identifiers** so contributions can be reconstructed when needed. Promising “we can recompute it” after raw data has expired past retention fails auditability.

### 13.4. Dataset Identity, Versioning, and Publish Time

The name **daily_tenant_sales** can point to many different outputs: v1.0/run9001, v1.0/run9002, v2.0/run9003. A data product must distinguish:

~~~text
dataset_id       = analytics.daily_tenant_sales
logical_version  = v1.0
physical_version = run_id 9001
published_at     = timestamp when the result is published
valid_for        = tenant/date scope and metric definition
source_manifest  = list of sources/versions/cutoffs
~~~

A **publish** step can update a view or pointer to the verified version in an atomic operation supported by the platform. This prevents dashboards from mixing part of an old run with part of a new run during the same read.

## 14. Measuring Pipeline Quality, Freshness, and Completeness

### 14.1. Minimum Pre-Publish Checks

| Layer | Check | On Failure |
| --- | --- | --- |
| **Raw** | Supported schema, valid ID/revision, valid currency | Quarantine and alert source owner |
| **Raw** | No two conflicting payloads for the same ID/revision | Do not arbitrarily pick a “lucky” row |
| **Source** | Checkpoints/watermarks meet policy | Do not publish as complete data |
| **Normalize** | Positive sales, negative refunds, report_date in right timezone | Check mapping/rule version |
| **Normalize** | Each event selected once per run | Check deduplication/source identity |
| **Normalize** | Every event retains source_dataset, source_event_id, source_version | Check provenance links |
| **Aggregate** | Sum of events matches group gross/refund/net | Reject publish if unreconciled |
| **Aggregate** | No missing or extra groups per definition | Check two-way key sets |
| **Publish** | Published version matches verified run | Block partial publish |
| **Monitoring** | Freshness, lag, rejected rows, p95/p99 job duration | Alert and determine blast radius |

Checks must have a **failure policy**. For instance, 50 records missing currency mappings cannot be silently dropped while still calling the report “complete” if they contain material financial transactions. Some systems allow publishing **partial** data with a warning, but consumers of the figures must understand and accept that approach.

### 14.2. Checking for Events Past the Cutoff

~~~sql
SELECT
    e.run_id,
    e.source_dataset,
    e.source_event_id,
    e.source_ingested_at,
    r.source_cutoff_at
FROM run_financial_events AS e
JOIN etl_runs AS r ON r.run_id = e.run_id
WHERE e.source_ingested_at > r.source_cutoff_at;
~~~

This query must return empty under the stated cutoff policy. It does **not** prove that events before the cutoff were ingested completely or that every raw event selected the right revision; those are separate checks.

### 14.3. Checking That Normalized Rows Still Trace to Raw

~~~sql
SELECT
    e.run_id,
    e.source_dataset,
    e.source_event_id,
    e.source_version
FROM run_financial_events AS e
LEFT JOIN raw_sale_versions AS s
  ON e.source_dataset = 'raw_sales'
 AND s.source_event_id = e.source_event_id
 AND s.source_version = e.source_version
LEFT JOIN raw_refund_versions AS r
  ON e.source_dataset = 'raw_refunds'
 AND r.source_event_id = e.source_event_id
 AND r.source_version = e.source_version
WHERE (e.source_dataset = 'raw_sales'
       AND s.source_event_id IS NULL)
   OR (e.source_dataset = 'raw_refunds'
       AND r.source_event_id IS NULL);
~~~

If rows are returned, data has lost its link to the source or lineage keys are broken. An organization may move raw data to cold storage; when doing so, preserve **accessible URIs/checksums/manifests** and adapt the reconciliation workflow rather than keeping raw records in hot tables forever.

### 14.4. Run-Wide Total Reconciliation

On sample run 9001:

~~~sql
SELECT
    COUNT(*) AS normalized_events,
    COUNT(*) FILTER (WHERE event_kind = 'SALE') AS sale_events,
    COUNT(*) FILTER (WHERE event_kind = 'REFUND') AS refund_events,
    SUM(CASE WHEN event_kind = 'SALE'
             THEN signed_amount_vnd ELSE 0 END) AS gross_vnd,
    SUM(CASE WHEN event_kind = 'REFUND'
             THEN -signed_amount_vnd ELSE 0 END) AS refund_vnd,
    SUM(signed_amount_vnd) AS net_vnd
FROM run_financial_events
WHERE run_id = 9001;
~~~

Expected:

| normalized_events | sale_events | refund_events | gross_vnd | refund_vnd | net_vnd |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 5 | 2 | 1750000 | 150000 | 1600000 |

Totals can match even when **one line is missing and another is duplicated for the exact same amount**. Therefore, reconcile **event keys** and versions, not just monetary totals or row counts.

### 14.5. Missing/Mismatched Source Checks Must Account for Scope

An important question is:

> Were all **eligible** source events within the manifest/cutoff included in the run?

To answer this, first select the **latest valid revision set** on raw and apply the same time, status, currency, and filter rules as the ETL; then use an **anti-join on (source_dataset, source_event_id)** to find omitted events. You cannot simply compare **COUNT(*) raw** against **COUNT(*) normalized**, because raw may contain **multiple revisions for the same ID**, tombstones, or ineligible events.

Source quality rules should be defined and independently testable. In some streams, a new refund may not yet find its parent order because the order event arrived late; the right choice may be **defer/quarantine** and retry, rather than silently dropping the refund.

### 14.6. Operational Metrics Should Be Scoped

Track **freshness** at multiple levels:

~~~text
Last successful run: when did the job finish?
Last source checkpoint: up to which offset has been processed?
Event-time watermark: up to what time does the source consider data complete?
Last reported business date: up to which date can reports be published?
Quarantine backlog: how many source records are rejected?
Version published: which run is the dashboard displaying?
~~~

A pipeline succeeding every five minutes while the **Refund source stopped sending since morning** will still produce wrong numbers. Watching **job success rate** alone will not catch a stalled source.

## 15. Data Governance: Access Control, Security, and Evidence Lifecycle

Lineage is valuable for tracing, yet lineage metadata itself is **data that requires governance**. A source ID, order ID, or path to a raw object can expose customer transactions; if everyone can browse that graph, the system may unintentionally open a data leakage channel.

### 15.1. Permission to View Results Does Not Imply Permission to View Source Evidence

For example:

- A business manager can view **daily total sales** for their own tenant.
- A reconciliation specialist can view **the source transactions contributing to totals** for their own tenant.
- A pipeline administrator can view **jobs/runs, schemas, and ingestion errors**, without necessarily needing customer names, addresses, or payment details.
- An auditor has access to source data scoped to an approved case, timeframe, and purpose.

If an aggregated table is **anonymized or aggregated across tenants**, drilling down to detailed source IDs may require higher privileges than viewing the summary table. Enforce **authorization at every drill-down step**, not only on the top-level dashboard.

### 15.2. Data Minimization in Lineage Metadata

Prefer storing:

~~~text
dataset identifier
scoped source record key with access policy
source version / checkpoint
transform version / run ID
report row key / contribution
timestamp and quality status
~~~

Avoid copying unnecessary payload fields into the lineage registry such as **full names, emails, phone numbers, addresses, tokens, or sensitive payment details**. When inspecting original content is necessary, metadata can point to a secured raw store with access checks rather than creating a second PII copy just for convenience.

If you hash or tokenize source IDs, define the purpose clearly: **hashing does not automatically anonymize data** when the ID domain is small or linkable. Also account for reconciliation across key/token rotation and retrieval policies for authorized personnel.

### 15.3. Privacy and Data Deletion Requests

Suppose a user exercises a right to delete personal data under applicable policy. That data may have been replicated to:

~~~text
operational source
  -> event / outbox
  -> raw files
  -> normalized tables
  -> dimensions
  -> reports / materialized views
  -> exports / downstream consumers
  -> backups and lineage metadata
~~~

The lineage graph helps locate **places that may contain personal data or derived information needing review**. However, deletion/retention rules vary by data category, purpose, and statutory retention obligations. You cannot claim that all derived data must be deleted immediately or that every audit log can be kept forever: concrete legal and operational policies are required.

What matters is **the ability to assess impact and prove actions taken**, without automatically exposing sensitive copies to every catalog viewer.

### 15.4. Retention Must Preserve Reproducibility for the Required Horizon

If raw sources are purged after 7 days while reports require transaction traceability for 7 years, storing only **source_event_id + run_id** is insufficient once the evidence is gone. Establish policies for:

| Data | Retention Question |
| --- | --- |
| Raw payload / CDC | How long is full data kept? Are there archives or immutable object snapshots? |
| Source manifest | Are file IDs, checksums, offsets, schemas, and versions enough to reconstruct? |
| Pipeline run | Should metadata be kept for all runs or only published runs? |
| Record/contribution lineage | How long must individual transactions remain traceable? |
| Published reports | Should snapshots be kept to explain figures users saw? |
| Access audits | Who may view/modify and for how long? |

When raw data cannot be kept long-term, you can store **minimal auditable evidence**, checksums, protected snapshots, or policy-compliant archives. However, a checksum **only supports verification** when comparison data exists; it **cannot reconstruct deleted content**.

## 16. Storage Cost and Engineering Lineage at Scale

### 16.1. Choose Granularity by Risk, Not Slogans

| Context | Minimum Lineage to Consider | When to Add More |
| --- | --- | --- |
| Replicating slowly changing lookup tables | Dataset/source ID, sync version, run timestamp | Record-level when investigating item-level edits |
| Syncing order status multiple times/day | Source record ID, source version, ingestion/checkpoint, run | Transition evidence and audit when status affects transactions |
| Aggregating non-sensitive operational KPIs | Dataset-level, column rules, run/version/cutoff, quality checks | Contribution-level if users need group explanations |
| Financial reports requiring line-item reconciliation | Event ID/revision, contribution, rule version, published report | Source snapshots/checksums and correction history |
| Predictive models / feature stores | Dataset/version, feature transformation, training window, model run | Record/feature lineage to investigate decision discrepancies per policy |

**Not every source needs to double its row count** to have lineage. If normalized events already retain full source identity and version, tracing backward from a group via JOIN may be enough. When a transformation loses traceability to source records (e.g., many-to-many allocation, deduplication without logging discarded rows), increase granularity or store evidence manifests.

### 16.2. Indexing for Both Trace Directions

Querying **report → event** in Section 9 uses:

~~~sql
CREATE INDEX idx_run_financial_report_lookup
ON run_financial_events (run_id, tenant_id, report_date);
~~~

An equivalent index was already created in Section 6.5 named **idx_financial_events_run_day**, so **do not execute this duplicate index on the existing example**. The snippet above simply reiterates the index shape helpful for backward tracing.

Conversely, querying **source → affected reports** typically needs a different key order:

~~~sql
CREATE INDEX idx_run_financial_source_impact
ON run_financial_events (
    source_dataset,
    source_event_id,
    run_id
);
~~~

Index choices must be driven by row counts, selectivity, query plans, and access frequency. With multi-billion-row tables, you can partition by **run_id/date**, build local indexes, or maintain a dedicated lookup registry; partitioning schemes must respect the engine's UNIQUE/PK constraints. Do not add every index just because a query can be written.

### 16.3. Immutable Raw Storage and Replay

Some systems maintain:

~~~text
raw source event / version (append-only, with archive)
    +
input snapshot manifest
    +
transform code/config version
    +
run metadata
    =
controlled replay capability
~~~

The equation above expresses **necessary evidence conditions**, not an automatic guarantee that replay yields bit-for-bit identical bytes. Results can also depend on:

- Runtime libraries and system versions.
- Timezone, locale, holiday calendars, and rounding behavior.
- Exchange rates, lookup tables, and dimensions as-of that time.
- Processing order when operations are non-associative or non-deterministic.
- Non-deterministic functions such as random(), current_timestamp, and live API calls.
- Policies for handling NULLs, malformed data, late events, and retries.

To reproduce **exactly**, you must identify and pin inputs that are not pure source data. Good practice treats a transform as a function of **input snapshot + rule/config version + reference snapshot**, avoiding queries that “fetch current state” and silently alter historical results.

### 16.4. Automated Lineage vs. Specified Lineage

Lineage can be extracted automatically from **SQL parsers**, query plans, orchestrators, and execution metadata. This is useful for capturing dataset/column dependencies, but has limitations:

- Logic inside UDFs, Java/Python services, API calls, or stored procedures can be hard to analyze statically.
- Dynamic SQL, schema drift, or SELECT * can render column lineage incomplete.
- A JOIN statement shows which columns interact, not the **business semantics** of the join.
- A job may read a table but use only a narrow subset via predicates; table-level dependencies can be overly broad for impact analysis.
- A record dropped by a filter may still require an exclusion reason to audit completeness.

Therefore, combine **automatically collected metadata** with **approved data contracts and business rules**, and periodically test critical lineage edges rather than blindly trusting a DAG diagram.

### 16.5. Protecting Tenant Boundaries in Lineage Queries

In multi-tenant systems, an ID like **O1001** can appear under two tenants if the source only guarantees per-tenant uniqueness. When drilling down:

~~~sql
SELECT e.*
FROM run_financial_events AS e
WHERE e.run_id = 9001
  AND e.tenant_id = 'T01'
  AND e.order_id = 'O1001';
~~~

Never query by **order_id** alone and return records across all tenants. If source IDs are only unique **within a tenant**, the lineage schema and joins back to raw must include **tenant_id** in the identifying key. Beyond SQL predicates, the system may require **row-level security or authorization policies** at the serving layer; callers must never be trusted merely because they passed a tenant_id in the request.

## 17. Designing Provenance from Requirements to Operations

1. **Define facts and owners:** what constitutes an event, what is the source of truth, where is the source ID unique, and are there revisions?
2. **Lock down the grain of each layer:** raw versions, normalized events, facts, aggregates, and published datasets; prevent miscounting rows after JOINs.
3. **Separate timestamps:** occurred/effective, committed, published, ingested, and report as-of.
4. **Define the source contract:** event ID/version, event type, schema, currency, tenant, deletion/correction, ordering, and replayability.
5. **Choose the required lineage level:** dataset, column, run, record, or contribution; weigh risk and retention.
6. **Store run metadata and manifests:** code/config version, sources, snapshot/cutoff, checkpoints/watermarks, status, and approver.
7. **Design explainable transformations:** filters, dedup, JOINs, conversions, allocations, timezones, and rounding; unit-test pure logic.
8. **Separate staging and published data:** immutable raw data, normalized tables with provenance, versioned aggregates, and a publish pointer.
9. **Test both directions:** from report back to events/raw and from events forward to targets; reconcile row counts, keys, and measures.
10. **Handle late arrivals/corrections/backfills:** preserve old runs, create new runs, diff deltas, and publish under control.
11. **Enforce access control and retention:** protect sensitive data in both payloads and metadata; execute deletion/archive policies.
12. **Monitor and improve:** quality, per-source freshness, quarantine backlog, lineage completeness, query cost, and recomputation time.

### 17.1. Verifiable Acceptance Question

> When someone asks “Why did the Nov 20 dashboard show 800,000 VND for T01?”, can the data team answer within the committed operational SLA?

A strong answer should provide:

~~~text
report row:
  dataset = daily_tenant_sales
  run_id = 9001
  tenant = T01
  report_date = 2026-11-20
  net_vnd = 800000

transformation:
  transform = daily_net_sales / v1.0
  source_cutoff = 2026-11-22 00:00 +07
  timezone = Asia/Ho_Chi_Minh
  formula = gross SALE - settled REFUND by occurred_at date

contributions:
  raw_sales/O1001-L1@v1 = +300000
  raw_sales/O1001-L2@v1 = +200000
  raw_sales/O1002-L1@v1 = +400000
  raw_refunds/RF1001@v1 = -100000

quality:
  source versions traceable
  totals reconciled
  published version and source completeness status available
~~~

Knowing only “the job finished at 1 AM” or “the number came from daily_sales” is not enough to explain origin and calculation.

## 18. Practice Exercises

### Exercise 1. Tracing a Total Back to Source

In run 9001, tenant T01 on Nov 20 has:

~~~text
SALE:   O1001-L1 = +300000
SALE:   O1001-L2 = +200000
SALE:   O1002-L1 = +400000
REFUND: RF1001   = -100000
~~~

**Tasks:**

1. Compute gross_vnd, refund_vnd, and net_vnd.
2. State the **grain** of the summary table and the grain of run_financial_events.
3. To look up the exact raw record for event RF1001, what fields are minimally required?
4. Why is storing only **order_id = O1001** on the summary table insufficient to explain the entire result?

<details>
<summary>Solution hints for Exercise 1</summary>

- **gross_vnd = 900000**, **refund_vnd = 100000**, **net_vnd = 800000**.
- **daily_tenant_sales** has grain **(run_id, tenant_id, report_date)**; **run_financial_events** has grain **(run_id, source_dataset, source_event_id)**.
- To locate the raw revision, you need **source_dataset = raw_refunds**, **source_event_id = RF1001**, **source_version = 1**, plus source/namespace info in a real environment. run_id tells **which report** selected that revision.
- An order can have multiple lines and refunds; moreover, T01's daily report also includes **O1002-L1**, so order_id O1001 does not represent the full set of contributing events.

</details>

### Exercise 2. Amending a Source Record While Preserving Report History

Run 9001 had cutoff Nov 22 00:00 +07 and used refund **RF1001@v1 = 100000**. On Nov 23, the source sends **RF1001@v2 = 120000**, with the same occurred_at on Nov 20. No other sources changed.

**Tasks:**

1. Should run 9001's net figure be edited in place to 780000?
2. If run 9002 executes with the same formula and a cutoff after v2 arrived, what is T01's net result for Nov 20?
3. If a job sums both RF1001@v1 and RF1001@v2, what kind of bug is that?
4. Which metadata explains the difference between the two runs?

<details>
<summary>Solution hints for Exercise 2</summary>

- **Do not** edit run 9001 in place: it is the result computed under the older snapshot/cutoff and holds audit value.
- Run 9002 selects the **highest received revision**, so refund = 120000 and **net = 900000 - 120000 = 780000**.
- Summing 100000 + 120000 is **double-counting versions of a single source event**, violating revision selection rules; they are not two independent refunds.
- You need **source_dataset, source_event_id, source_version**, cutoff, run ID, transform version, and the ingestion time of the new revision to explain the **-20000** delta.

</details>

### Exercise 3. Event-Time vs. Ingestion-Time

A 50,000 VND refund occurred at **Nov 20 23:50 +07**, but due to a network outage was only ingested into the warehouse at **Nov 23 08:00 +07**. Report run 9001 had cutoff **Nov 22 00:00 +07**.

**Tasks:**

1. Does that refund belong to run 9001?
2. When recalculating with a cutoff after Nov 23, should the refund affect **Nov 20 or Nov 23** under this lesson's rules?
3. If the Nov 20 dashboard was already published, what steps are needed to explain the changed number?
4. Why is recording only **updated_at** in the summary table insufficient?

<details>
<summary>Solution hints for Exercise 3</summary>

The refund **does not belong to run 9001** because its **ingested_at** is after the cutoff. Under the event-occurrence-date rule, it affects **Nov 20** when picked up in the new run, not Nov 23.

You must record the source and event ID, the new run/cutoff, verify the refund is valid, recalculate affected groups, reconcile the delta, publish a new version noting the late-arriving data, and preserve the history of the old run. **updated_at** only tells when the row was modified; it does not tell **which event, revision, formula, or cutoff** changed the result.

</details>

### Exercise 4. Is a Dataset Graph Enough to Audit Every Row?

A team stores a DAG:

~~~text
orders -> raw_orders -> normalized_sales -> daily_sales
refunds -> raw_refunds -> normalized_sales -> daily_sales
~~~

The team claims that having this diagram proves every monetary amount contributing to a **daily_sales** row.

**Tasks:**

1. What level of lineage does this diagram actually provide?
2. What is missing when a user asks why a row equals 800000?
3. If a refund must be allocated across three order lines, what additional information must be recorded?
4. Give one scenario where dataset/job-level lineage alone is reasonable.

<details>
<summary>Solution hints for Exercise 4</summary>

A DAG provides **dataset-level lineage**, helping locate upstream and downstream tables. Proving the 800000 figure requires **run/version/cutoff**, source record IDs/revisions, filter rules, contribution signs, dates, and the aggregation formula. If a refund is allocated across three lines, you need **allocation ratios/amounts, target row keys, and the rounding rule version** to guarantee that contributions sum back to the original refund.

Dataset/job-level lineage may suffice for a pipeline replicating a small reference table for internal use, when row-level auditing is not required and the table can be rebuilt from saved snapshots.

</details>

### Exercise 5. SQL to Find Events Missing Their Raw Records

The **run_financial_events** table has source_dataset values **raw_sales** or **raw_refunds**. Write a query to find events in run 9001 whose **source_event_id + source_version** does not match any record in the corresponding raw table.

**Bonus question:** why not JOIN the two raw tables solely on **order_id**?

<details>
<summary>Solution hints for Exercise 5</summary>

One way uses two conditional LEFT JOINs:

~~~sql
SELECT e.source_dataset, e.source_event_id, e.source_version
FROM run_financial_events AS e
LEFT JOIN raw_sale_versions AS s
  ON e.source_dataset = 'raw_sales'
 AND s.source_event_id = e.source_event_id
 AND s.source_version = e.source_version
LEFT JOIN raw_refund_versions AS r
  ON e.source_dataset = 'raw_refunds'
 AND r.source_event_id = e.source_event_id
 AND r.source_version = e.source_version
WHERE e.run_id = 9001
  AND (
      (e.source_dataset = 'raw_sales'
       AND s.source_event_id IS NULL)
      OR
      (e.source_dataset = 'raw_refunds'
       AND r.source_event_id IS NULL)
  );
~~~

**order_id does not uniquely identify a source event**: an order can have multiple lines, multiple refunds, and multiple revisions. Joining on order_id can produce false combinations, corrupting traceability or double-counting amounts.

</details>

### Exercise 6. Source Completeness Checks and Delayed Numbers

Order Service delivered complete data through the end of Nov 21. Refund Service has only delivered up to **12:00 on Nov 21**. The daily_sales job runs and reports **SUCCEEDED** at 00:30 on Nov 22.

**Tasks:**

1. Can the Nov 21 report be called **complete** just because the job succeeded?
2. What metadata/checkpoints are needed from both sources?
3. If displaying the report is still allowed, how should the dashboard communicate data status?
4. Why cannot source_cutoff_at in the target database replace a source watermark?

<details>
<summary>Solution hints for Exercise 6</summary>

No. Job success only means the processing step finished over **the records it had seen**. You need checkpoints or watermarks from **both Order and Refund sources**, a lateness policy, reconciliation totals, or per-period completion status.

If the business permits previewing, the dashboard should display **preliminary/partial**, the latest data timestamp per source, and a warning that numbers may update. **source_cutoff_at** only bounds ingested data; it does not guarantee that all business events from Refund Service have finished transferring.

</details>

### Exercise 7. Blast Radius and Privacy

A sales summary table is widely shared among managers. An employee discovers that a drill-down link can download full customer personal details from raw records without additional authentication.

**Task:** propose at least four design or operational changes to preserve audit-grade lineage while reducing data exposure risk.

**Solution guide:** separate permissions for viewing summaries from viewing records/raw data, enforce **tenant scope and authorization** at every step, minimize PII in metadata, link to an evidence store with separate access control, audit sensitive access, apply policy-based retention/deletion, tokenize identifiers where appropriate, and test that tenant A users cannot view tenant B records. **Having lineage** does not mean every user may access every data layer.

## 19. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| “Knowing the source table is enough to trace any metric.” | Dataset-level lineage alone cannot identify records/revisions and contribution amounts. |
| “Having trace_id means we definitely know a record's origin.” | Distributed tracing tracks request paths; you still need source IDs and data mappings. |
| “Job SUCCEEDED means data from all source systems is complete.” | Checkpoints, watermarks, and quality must be verified **per source**. |
| “ingested_at is the business occurrence date.” | Event time and ingestion time can differ by days. |
| “Identical source IDs in two services refer to the same event.” | IDs must be paired with **source/namespace** and uniqueness scope. |
| “Summing all revisions in raw gives the right number.” | Revisions may **supersede** each other; pick latest or follow adjustment-event rules. |
| “Keeping only the latest report is enough; no need for old runs.” | You lose the ability to explain numbers published before corrections or rule changes. |
| “Running the same SQL always yields the same result.” | Input snapshots, cutoffs, reference data, versions, and non-deterministic functions can vary. |
| “Counting rows and matching totals is sufficient reconciliation.” | Offsetting errors can make totals match; compare IDs/revisions and key sets. |
| “Fixing one refund does not require finding affected reports.” | You may need to backfill multiple dates, groups, dashboards, and data marts. |
| “No event in the warehouse means no event in the source.” | It may be uningested, rejected, purged by retention, or delayed in transit. |
| “Lineage must store every payload in the catalog.” | Store minimal metadata and link to secured sources when needed. |
| “Hashing IDs automatically anonymizes lineage data.” | Hashed IDs can still be linked or guessed; security policies are still required. |
| “Automated SQL lineage understands all business logic.” | Parsers see column dependencies but do not understand refunds, FX rates, or policies. |
| “Updating the summary row is enough to fix a number.” | You must know the root cause, run/version, source data, and downstream impact. |

## 20. Lineage and Provenance Acceptance Checklist

| Question | Required Evidence |
| --- | --- |
| How is a source row identified and within what scope is it unique? | Source namespace, record ID, revision/sequence, data contract |
| Which source owns which fact? | Source-of-truth registry and designated owners |
| Are the grains of raw, normalized, and aggregate layers clear? | One-row definitions, candidate keys, relationships |
| Are event time, ingestion time, and report as-of separated? | Explicit timestamps and date/timezone policies |
| Which logic version did the job run? | Run ID, transform version, code/config digest |
| How was the input set frozen? | Snapshot manifest, cutoff, checkpoint/watermark |
| Can you locate the exact source revision for a target row? | Source dataset + ID + version and raw access path |
| Can you trace contributing events for an aggregated total? | Contribution query/bridge, sign/rounding formulas |
| Can you identify affected downstream targets when a source is fixed? | Dataset edges and published artifact versions |
| Are retries, revisions, tombstones, and late data handled properly? | Idempotency, tests, quarantine, and reprocessing policy |
| Are missing/extra rows, amounts, and schemas checked? | Automated tests, reconciliation report |
| Do you distinguish job success from source completeness? | Per-source watermarks, freshness, and backlog |
| Can report history be preserved/corrected without deleting evidence? | Versioned runs, backfill, publish pointer, rollback |
| Who may view raw data and lineage information? | Authorization, tenant isolation, audit, retention |
| Can results be reproduced within the committed SLA? | Raw/reference snapshots, code version, and replay procedure |
| Is metadata storage cost appropriate for scale? | Lineage granularity policy, indexing/partitioning, and archiving |

## 21. Key Takeaways

**Tracking data lineage** is more than drawing an arrow between two tables. For data replicated across service boundaries, you must know the **source of truth, source keys and versions, business timestamp, ingestion timestamp, sync status, and the run that created the replica**. For aggregated data, you must add **grain, filtering/deduplication/JOIN rules, contribution formulas, transform version, and how the input set was bounded**.

The net sales example demonstrates how a report row of **800,000 VND** can be explained by **three sale events** and **one refund event**, together with **run 9001**, calculation version, and cutoff. When a refund is amended, create a **new run and compare deltas** instead of silently mutating old results; when a source arrives late, evaluate completeness via checkpoints/watermarks rather than relying solely on job success.

A reliable design supports both directions: **from report back to the exact source** for explanation, auditing, and reconciliation; and **from source forward to dependent targets** for impact analysis, data fixes, and backfills. Every step must respect **grain, keys, consistency, history, tenant boundaries, and privacy**. A practical execution order is **define facts → lock down grain/keys/versions → preserve traces across boundaries → build reproducible transforms → reconcile → publish by version → monitor and govern lifecycle**.

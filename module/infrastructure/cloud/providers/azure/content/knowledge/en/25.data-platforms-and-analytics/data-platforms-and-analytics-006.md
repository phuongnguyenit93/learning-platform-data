# Copy Activity, Incremental Load, and Pipeline Orchestration

## 1. Real-World Problem: Moving Data Without Losing or Duplicating It

An e-commerce company has an operational SQL Server database containing an **Orders** table with millions of rows. The analytics team needs to bring data into **Azure Data Lake Storage Gen2 (ADLS Gen2)** to preserve raw copies and into **Azure SQL Database** to populate reporting tables.

The simplest approach is copying the entire table every hour. This quickly runs into problems:

- A 500 GB table gets read and transferred repeatedly even when only 1,000 orders changed.
- Heavy `SELECT`/scan load degrades the transactional application.
- Copy duration exceeds the schedule interval, causing pipeline runs to overlap.
- If a run fails partway through and reruns, the destination can receive duplicate rows.
- If the read checkpoint advances too early, some changes are permanently missed.

**Copy activity** handles transferring data between source and sink. **Incremental load** determines *which new or changed data needs to be copied*. **Pipeline orchestration** coordinates sequencing, triggers, dependencies, retries, validation, and progress updates.

This lesson belongs to the **Data Platforms and Analytics** chapter in the module exploring the Microsoft Azure ecosystem. It connects resource group governance, networking, Microsoft Entra ID identities, ADLS, Azure SQL, monitoring, and cost into an operationally viable data ingestion workflow.

### End-to-End Scenario Goal

A pipeline named **pl_orders_incremental** must:

1. Read the checkpoint or watermark from the last successful run.
2. Lock the upper boundary for the current run.
3. Copy only the changed data into a staging area.
4. Validate row counts and data quality.
5. Idempotently upsert or merge into the reporting table.
6. Update the watermark only once the target state is durable.
7. Log run ID, row counts, duration, RU/compute if relevant, status, and errors.
8. Be safely re-runnable on failure without corrupting data.

## 2. Learning Objectives

After completing this lesson, you will be able to:

1. Explain Azure Data Factory (ADF), pipelines, activities, linked services, datasets, triggers, and Integration Runtimes.
2. Design Copy activities for SQL, Azure Storage, and supported connectors.
3. Distinguish full load, append-only incremental, update-aware incremental, and CDC.
4. Choose watermarks based on timestamps, monotonic IDs, change versions, or log sequences appropriately.
5. Design control tables and rules so watermarks update only after destination data is safe.
6. Construct `(last, upper]` windows to read an exact interval.
7. Handle tied timestamps, late-arriving data, commit races, deletes, and schema drift.
8. Use staging, upsert/MERGE, deduplication, and idempotent reruns.
9. Orchestrate Lookup, Copy, Stored Procedure, If Condition, ForEach, and Execute Pipeline activities.
10. Use schedule, tumbling-window, and storage-event triggers appropriately.
11. Understand retries, timeouts, concurrency, dependencies, and recovery/backfills.
12. Choose Azure Integration Runtime, self-hosted Integration Runtime, VNet/private connectivity, and secure authentication.
13. Monitor `rowsRead`, `rowsCopied`, duration, throughput, failures, data consistency, and cost.
14. Execute a lab simulating incremental loads with SQL Server/Azure SQL and ADLS.

## 3. Azure Data Factory and Key Concepts

**Azure Data Factory** is a data orchestration and integration service. It manages pipeline definitions, activity execution, connection metadata, monitoring, and triggers. Pipeline features in **Azure Synapse Analytics** share similar concepts, though you should not assume every connector, UI screen, or setting is identical; examples here focus on **ADF**.

| Component | Role | Example |
|---|---|---|
| **Factory** | Azure resource managing pipelines | `adf-commerce-prod` |
| **Pipeline** | Workflow composed of multiple activities | `pl_orders_incremental` |
| **Activity** | A specific execution step | Lookup, Copy, Stored Procedure |
| **Linked service** | Connection config to a data store/compute | `ls_sql_source`, `ls_adls` |
| **Dataset** | Reference defining source/sink structure and location | `ds_orders_sql`, `ds_stage_parquet` |
| **Integration Runtime (IR)** | Infrastructure executing transfer/compute/connectivity per activity | Azure IR or self-hosted IR |
| **Trigger** | Starts pipelines on schedules, events, or windows | Schedule, tumbling window |
| **Parameter** | Input value passed to a pipeline/dataset | `windowStart`, `windowEnd` |
| **Variable** | Simple transient state inside a pipeline | `status`, `currentFile` |
| **Monitor** | Observability for pipeline/activity runs | Rows copied, failure details |

### 3.1. Execution Flow Map

~~~mermaid
flowchart LR
    T[Trigger / Manual run] --> P[Pipeline]
    P --> L[Lookup watermark]
    L --> U[Determine upper bound]
    U --> C[Copy activity]
    C --> V[Validate]
    V --> M[Apply staging / merge]
    M --> W[Commit watermark]
    W --> O[Monitoring / alert]
~~~

In the diagram, arrows denote **orchestration dependencies**; they do not imply that every activity participates in a single distributed database transaction.

### 3.2. Control Plane vs. Data Movement

ADF orchestrates. Data is copied via connectors and the Integration Runtime, not necessarily through the machine running the browser or ADF Studio.

This matters for networking and permissions: **being able to open ADF Studio does not mean the Integration Runtime can read the SQL source** or write to the Storage sink.

## 4. What Does Copy Activity Actually Do?

**Copy activity** reads data from a source, streams it through the Integration Runtime using connector semantics, and writes to a sink. It supports tabular data, files, binary data, and more depending on source/sink.

Example:

~~~text
SQL Server Orders
      |
      | Source query
      v
Copy Activity
      |
      +----> ADLS Gen2 /raw/orders/...
      |
      +----> Azure SQL staging table
~~~

A Copy activity has **one logical source and one logical sink** per configuration; the branching above represents two architectural options or two separate activities, **not a single Copy writing to two sinks simultaneously**.

### 4.1. Common Settings

- **Source**: table, query, file path, wildcard, partitioned read if supported.
- **Sink**: table/file path, write behavior, mapping, output format.
- **Dataset/linked service**: structural and connection details.
- **Mapping**: column and data-type mappings.
- **Performance**: parallel copies, data integration units, staging, and copy partitioning per connector/tier.
- **Fault tolerance**: handling of bad rows, skip/error logging per connector capabilities.
- **Retry/timeout**: activity-level orchestration settings.

### 4.2. Copy Does Not Understand Business Semantics on Its Own

If the source has record `orderId=1001` with an updated status, Copy activity does not automatically decide:

- Whether the sink needs an INSERT or UPDATE.
- Whether a source deletion should delete at the sink or mark deleted.
- Whether duplicate writes are allowed.
- Whether conditions are met to commit the watermark.
- Whether multiple updates within one window must be collapsed.

Those decisions belong to your **incremental strategy, staging, and business logic**.

## 5. Choosing an Integration Runtime (IR)

Integration Runtime handles data movement/dispatching depending on the activity and connection.

| IR | Best Suited For | Notes |
|---|---|---|
| **Azure IR** | Copying between cloud stores reachable under network policy | Region, data movement, networking, DIUs |
| **Azure IR with Managed VNet** | Requiring managed private endpoints per supported features/connectors | Private endpoint approval, DNS, cold-start/queueing |
| **Self-hosted IR (SHIR)** | Connecting to on-prem SQL or sources in private networks | Customer-managed Windows nodes, versions, credentials, HA, outbound |
| **Azure-SSIS IR** | Running compatible SSIS packages | Not the default choice merely to run Copy activity |

### 5.1. On-Premises SQL Server Source

SHIR runs in a network able to reach SQL Server and connect outbound to Azure service endpoints per policy. **Do not expose SQL Server directly to the Internet just for ADF Copy.**

### 5.2. Private Sinks in Azure

Verify VNets, private endpoints, DNS, firewalls, IAM, and the chosen IR. Confirm the actual connector network path rather than inferring connectivity simply because the ADF resource has a managed identity.

### 5.3. Scaling and HA for SHIR

For critical workloads, consider multiple nodes in one self-hosted IR under supported models, monitoring CPU, memory, queues, connectivity, and host software. Nodes must be operated and patched per organizational policy.

## 6. Linked Services, Datasets, and Managed Identity

A **Linked service** declares *where and how to connect*. A **Dataset** specifies *what data and where* inside that data store.

Example:

~~~text
Linked service: ls_azure_sql
  endpoint / database / authentication

Dataset: ds_orders_staging
  linkedService = ls_azure_sql
  schema = dbo
  table = OrdersStage
~~~

### 6.1. Authentication

Managed identities or service principals can be used where supported by connectors. With SQL sources and ADLS sinks, grant appropriate data-plane permissions:

- Azure SQL: Entra principal/database user and required SQL grants.
- ADLS Gen2: Azure RBAC data roles paired with ACLs where applicable.
- Azure Key Vault: secret read rights for the factory identity or connecting identity.
- On-prem SQL: credentials stored and protected via approved mechanisms.

**The Contributor role on a resource group does not automatically grant `SELECT` on SQL or file writes on ADLS.**

### 6.2. Parameterizing Datasets

Datasets can accept parameters like **schemaName**, **tableName**, and **folderPath** for reuse. However, table/schema parameters are SQL identifiers: use a trusted internal allowlist rather than concatenating unvalidated HTTP input directly.

### 6.3. Secret Rotation

Never write SQL passwords, storage keys, or SAS tokens into expressions or logs. Use managed identities and Key Vault references wherever supported. Rotation procedures must include connection verification and rollback.

## 7. How Full Load, Incremental Load, and CDC Differ

| Strategy | Data Extracted | Best When | Risks |
|---|---|---|---|
| **Full refresh** | Entire dataset or partition to refresh | Small datasets, reference tables | Expensive scans/transfers, downtime, or overwrites |
| **Append-only by ID** | Records with ID greater than last recorded ID | Insert-only data with strictly monotonic IDs | Misses UPDATEs, DELETEs, and lower IDs committed late |
| **Timestamp watermark** | Rows with `modifiedAt` inside window | Sources with a reliable modification timestamp | Ties, late commits, clock skew, DELETEs |
| **Change Tracking (CT)** | Primary keys changed since a version | SQL Server/Azure SQL with CT enabled and adequate retention | Lacks full before/after history; requires reading current rows and deletes |
| **Change Data Capture (CDC)** | Inserts/updates/deletes from change logs | Need full ordered/LSN change history | Retention, schema evolution, source support, operational overhead |
| **File modification/listing** | New/modified files by metadata | File landing zones | Timestamps and eventual delivery may lack row-level semantics |

**Incremental does not mean reading only INSERTs.** Explicitly decide whether UPDATEs, DELETEs, and late-arriving records must be captured.

### 7.1. Two Illustrative Branches

~~~text
Append-only events  -> LastEventId / sequence
Mutable Orders       -> UpdatedAt + safety overlap or CT/CDC
~~~

If a table undergoes meaningful UPDATEs or DELETEs, incremental loading by **`created_at`** is insufficient.

## 8. What Is a Watermark?

A **Watermark** is a progress marker representing data processed safely so far. It can be:

- A **`lastModifiedAtUtc`** timestamp.
- A monotonically increasing **`lastId`**.
- A SQL change tracking version.
- A CDC log sequence number (LSN).
- Another source-specific offset or checkpoint.

Example:

~~~text
Committed watermark: 2026-11-19T10:00:00.000Z
Current run upper bound: 2026-11-19T10:30:00.000Z

Read:
    updated_at > 10:00:00
AND updated_at <= 10:30:00
~~~

The mathematical notation for the window is **`(lastWatermark, upperWatermark]`**: open on the left, closed on the right.

### 8.1. A Watermark Is Not Pipeline Execution Time

If a pipeline starts at 10:32 while the source database has not yet committed all transactions with `modified_at <= 10:30`, picking `upper=10:30` without commit-visibility guarantees risks missing records. Understand timestamp semantics and source isolation.

### 8.2. Never Advance the Watermark Before Copying

If Copy fails after advancing the watermark, the next run skips uncopied data. **Commit the watermark only after data is safely applied and validated.**

## 9. Watermark Control Tables and Run Logs

T-SQL example on **Azure SQL Database** serving as a control store:

~~~sql
CREATE TABLE dbo.EtlWatermark (
    PipelineName      nvarchar(200) NOT NULL PRIMARY KEY,
    LastWatermarkUtc  datetime2(7) NOT NULL,
    UpdatedAtUtc      datetime2(7) NOT NULL
        CONSTRAINT DF_EtlWatermark_Updated
        DEFAULT SYSUTCDATETIME()
);

CREATE TABLE dbo.EtlRunLog (
    RunId             nvarchar(100) NOT NULL PRIMARY KEY,
    PipelineName      nvarchar(200) NOT NULL,
    StartWatermarkUtc datetime2(7) NOT NULL,
    UpperWatermarkUtc datetime2(7) NOT NULL,
    StartedAtUtc      datetime2(7) NOT NULL,
    CompletedAtUtc    datetime2(7) NULL,
    Status            nvarchar(30) NOT NULL,
    RowsCopied        bigint NULL,
    ErrorMessage      nvarchar(2000) NULL
);
~~~

Initialize a pipeline:

~~~sql
INSERT INTO dbo.EtlWatermark (PipelineName, LastWatermarkUtc)
VALUES ('pl_orders_incremental', '2000-01-01T00:00:00.0000000');
~~~

Run once or use a conditional upsert during IaC setup. The year-2000 value is just an illustrative sentinel; in production, base the initial watermark on your full-seeding/historical-backfill policy.

### 9.1. Why Separate Watermarks from Run Logs?

- The watermark represents **committed progress**.
- The run log records **every execution**, including failures, retries, cancellations, and reruns.
- A failed run must leave an audit trail **without advancing** the watermark.
- Rerunning the same window needs visibility into how much data was applied.

### 9.2. Concurrency Control

If two pipeline runs read the same old watermark and write simultaneously, windows overlap. Configure appropriate pipeline concurrency, or use locks/leases, a serializing controller, or stored procedure transactions to claim windows. **Never assume a plain watermark table alone prevents concurrent runs.**

## 10. Capturing the Upper Bound and Querying Source Data

Example **SQL Server** source, table **dbo.Orders**:

~~~sql
CREATE TABLE dbo.Orders (
    OrderId        bigint PRIMARY KEY,
    CustomerId     bigint NOT NULL,
    Status         nvarchar(30) NOT NULL,
    Amount         decimal(18,2) NOT NULL,
    ModifiedAtUtc  datetime2(7) NOT NULL
);
~~~

Illustrative way to read upper bound:

~~~sql
SELECT SYSUTCDATETIME() AS UpperWatermarkUtc;
~~~

With reliable timestamp tracking, a source query can be:

~~~sql
SELECT OrderId, CustomerId, Status, Amount, ModifiedAtUtc
FROM dbo.Orders
WHERE ModifiedAtUtc > @lastWatermark
  AND ModifiedAtUtc <= @upperWatermark;
~~~

**`@lastWatermark`** and **`@upperWatermark`** must be supplied safely via connector/query parameters or a stored procedure where supported. If only dynamic SQL text is available, strictly validate UTC formatting and all identifiers/values.

### 10.1. Commit Race Risk

A transaction starts at 10:29, sets `ModifiedAtUtc=10:29`, yet commits at 10:31. The pipeline locks `upper=10:30` and scans at 10:30:30, missing the uncommitted row. The next run filters `> 10:30`, permanently skipping the 10:29 row.

**Conclusion:** relying solely on a wall-clock upper bound over `modified_at` is unsafe in systems with long transactions, application-assigned timestamps, or late commits.

### 10.2. Ways to Mitigate Risk

- Use CT/CDC/log sequences when strict correctness is needed and supported by the source.
- Add a **safety delay**: set the upper bound slightly behind current time based on observed commit-latency distributions.
- Use an **overlap window** paired with idempotent deduplication/upsert—though never assume overlap covers arbitrarily long transactions.
- Ensure `ModifiedAtUtc` is updated consistently by the database/application on every change.
- Run periodic reconciliations comparing source and sink to catch missed records.

### 10.3. Clock Skew

If timestamps come from multiple app servers with drifting clocks, a newer record may carry an older timestamp. Prefer consistent source-side timestamps/versions or commit-based tracking over trusting client clocks blindly.

## 11. Tied Timestamps and Composite Watermarks

Suppose multiple rows share the exact timestamp **10:30:00.000**:

~~~text
OrderId 101 | ModifiedAt=10:30:00.000
OrderId 102 | ModifiedAt=10:30:00.000
OrderId 103 | ModifiedAt=10:30:00.000
~~~

If a pipeline advances the watermark to 10:30 and later filters **`> 10:30`**, any unread rows sharing that timestamp are skipped.

### 11.1. When Does Timestamp-Only Still Work?

When the pipeline copies the **entire window up to upper** in one go and timestamp/commit semantics are trustworthy; all rows at the upper timestamp are processed together rather than split mid-batch. Even then, late commits must still be addressed.

### 11.2. Composite Watermark `(timestamp, primary key)`

A seek pagination pattern:

~~~sql
SELECT TOP (1000)
    OrderId, CustomerId, Status, Amount, ModifiedAtUtc
FROM dbo.Orders
WHERE ModifiedAtUtc > @lastTimestamp
   OR (
       ModifiedAtUtc = @lastTimestamp
       AND OrderId > @lastOrderId
   )
ORDER BY ModifiedAtUtc, OrderId;
~~~

In this model, the checkpoint after each page is **`(lastTimestamp, lastOrderId)`** of the last durably processed row. Checkpointing only timestamp without `OrderId` risks dropping tied rows across page boundaries.

**Commit races can still occur** if a late transaction commits with an older timestamp and smaller key than the checkpoint; composite watermarks do not replace CDC or commit tracking.

## 12. Watermark-Based Copy Pipeline: Step-by-Step Diagram

~~~mermaid
flowchart TD
    START([Trigger]) --> L[Lookup last committed watermark]
    L --> U[Determine stable upper boundary]
    U --> CLAIM[Claim unique run/window]
    CLAIM --> COPY[Copy source delta to staging]
    COPY --> CHECK{Copy/validation successful?}
    CHECK -->|No| FAIL[Log failure, retain old watermark]
    CHECK -->|Yes| APPLY[Idempotent merge/upsert into destination]
    APPLY -->|Failure| FAIL
    APPLY -->|Success| COMMIT[Commit watermark after durable apply]
    COMMIT --> LOG[Record rows, duration and run status]
    LOG --> DONE([Success])
~~~

### 12.1. Why Is Staging Needed?

Copying source deltas straight into reporting tables risks:

- Duplicate rows on reruns.
- Changes not applied cleanly by business key.
- Partial Copy writes leaving half-applied state.
- Difficulty validating row counts and schemas.
- Difficulty identifying which run produced which rows.

**Staging** lets you load the delta, validate, deduplicate, and then apply idempotently. Depending on sink and workload, use an **Azure SQL staging table** or **ADLS landing files**.

### 12.2. Data Correctness Matters More Than Activity Success

Copy status **Succeeded** proves the connector executed the copy step; it does not prove downstream tables are accurate. Validation, constraints, and business reconciliations remain essential.

## 13. Organizing Data in ADLS Gen2

One layering layout:

~~~text
adls-account/
  landing/orders/
    ingest_date=2026-11-20/
      run_id=<pipeline-run-id>/
        part-0001.parquet
  bronze/orders/
  silver/orders_current/
  gold/daily_order_revenue/
~~~

This structure is illustrative; actual paths must follow naming, retention, and partitioning standards.

### 13.1. Raw/Landing

Retain the run's input data and metadata such as source system, `runId`, extraction window, and ingestion timestamp. Avoid overwriting older files when auditability or replay is needed.

### 13.2. Silver/Current State

Transform, deduplicate, process UPDATEs/DELETEs, and produce a clean state per business key.

### 13.3. Gold/Marts

Analytics/BI-ready tables governed by aggregation rules and quality checks.

### 13.4. Do Not Assume Copy Activity Creates Delta Lake Transactions

Copying into Parquet or CSV moves files; maintaining a **Delta Lake** table with transaction logs, MERGE, and schema enforcement requires a compatible engine/tool—simply writing `.parquet` files does not give you Delta ACID semantics.

## 14. Copy Activity: Source and Sink Configuration

Design example:

| Property | Illustrative Value |
|---|---|
| Source linked service | SQL Server/Azure SQL connection |
| Source dataset | `dbo.Orders` |
| Source query | Reads `(last, upper]` |
| Sink linked service | Azure SQL Database |
| Sink dataset | `dbo.OrdersStage` |
| Mapping | `OrderId`, `CustomerId`, `Status`, `Amount`, `ModifiedAtUtc` |
| Run marker | `RunId` and pipeline metadata |
| IR | Azure IR or self-hosted IR per networking |
| Error handling | Fail activity if copy cannot guarantee accurate data |
| Monitoring | `rowsRead`, `rowsCopied`, duration, throughput, errors |

### 14.1. Choosing Sink Write Behavior

- **Insert/append** fits `runId`-scoped staging or append-only history.
- **Upsert** may be supported by the connector with a key column and sink-specific constraints.
- **Post-copy stored procedure/merge** fits complex business logic, deduplication, version checks, and atomic watermark commits.

Never assume every sink connector offers identical upsert, transaction, or schema handling. Check the exact connector and IR documentation.

### 14.2. Copy Parallelism

Copy activity supports partitioned source/sink reads and `parallelCopies`/DIUs per connector. Increasing parallelism does not automatically increase source DB throughput or sink capacity; it can trigger lock pressure, DTU/vCore exhaustion, or network bottlenecks.

### 14.3. Staging + Validation

Track per-run metadata: `runId`, window bounds, expected source rows (if available), `rowsCopied`, `schemaVersion`, and validation status. Prefer explicit schema mapping over auto-mapping when data contracts matter.

## 15. ADF Expressions and Dynamic Content

ADF allows referencing parameters, variables, and activity outputs.

Examples:

~~~text
@pipeline().RunId
@pipeline().parameters.windowStart
@pipeline().parameters.windowEnd
@activity('LookupWatermark').output.firstRow.LastWatermarkUtc
@activity('LookupUpper').output.firstRow.UpperWatermarkUtc
~~~

These expressions assume:

- The pipeline defines **`windowStart`/`windowEnd`** parameters when referenced.
- The Lookup activity name matches exact spelling and **`firstRowOnly=true`**.
- The Lookup SQL query returns exact column aliases.
- Activity output shapes match; if **`firstRowOnly=false`**, rows appear under **`output.value`** instead of `firstRow`.

### 15.1. Lookup Watermark

Example Lookup SQL:

~~~sql
SELECT LastWatermarkUtc
FROM dbo.EtlWatermark
WHERE PipelineName = 'pl_orders_incremental';
~~~

### 15.2. Lookup Upper Bound

Illustrative source timestamp check:

~~~sql
SELECT SYSUTCDATETIME() AS UpperWatermarkUtc;
~~~

For strict correctness, upper bounds should rely on **CT/CDC versions, snapshot/commit sequences**, or safety policies as discussed—never blindly assuming wall-clock upper bounds cannot miss rows.

### 15.3. Safe Dynamic SQL

ADF supports **`@concat(...)`** expressions to assemble SQL text. However, string concatenation easily introduces quoting bugs or SQL injection, especially with dynamic schema/table names. Prefer parameterized queries or stored procedures with typed parameters wherever supported. For metadata-driven table names, enforce a trusted internal allowlist.

## 16. Example Pipeline with Parameters and Activity Dependencies

In ADF Studio, create pipeline **`pl_orders_incremental`** with ordered activities:

~~~text
LookupWatermark
       |
LookupUpper
       |
CopyOrdersToStage
       |
ValidateStage
       |
ApplyOrdersAndCommitWatermark
       |
NotifySuccess
~~~

Illustrative JSON fragment showing **pipeline parameters** (not a complete deployable ARM template):

~~~json
{
  "name": "pl_orders_incremental",
  "properties": {
    "parameters": {
      "sourceTable": {
        "type": "String",
        "defaultValue": "dbo.Orders"
      },
      "runMode": {
        "type": "String",
        "defaultValue": "incremental"
      }
    }
  }
}
~~~

In real resources, **activity JSON must also include linked services, datasets, source/sink types, policies, and dependencies**. The snippet above shows only how parameters are declared.

### 16.1. Lookup Output

Lookup SQL:

~~~sql
SELECT LastWatermarkUtc
FROM dbo.EtlWatermark
WHERE PipelineName = 'pl_orders_incremental';
~~~

After successful execution, reference:

~~~text
@activity('LookupWatermark').output.firstRow.LastWatermarkUtc
~~~

If Lookup returns zero rows, the expected `firstRow` property will not exist. Seed the control record beforehand or add a branch handling **no watermark** rather than letting the pipeline fail cryptically.

### 16.2. Lock the Upper Bound Once

The upper boundary must be computed **once per run** and persisted in run metadata. Never recompute the upper bound after a Copy failure and partial rerun, as that shifts the window.

### 16.3. Pass `runId` Down Through Steps

Use:

~~~text
@pipeline().RunId
~~~

Pass `runId` into staging tables, audit logs, file paths, or stored procedure parameters. When ADF retries an **activity within the same pipeline run**, `runId` normally stays the same; a new pipeline run or backfill gets a new `runId`, which must still remain idempotent by business key and window.

### 16.4. Dependencies

Each activity must wire **Succeeded, Failed, Skipped, or Completed** according to ADF control-flow rules. For instance, **ApplyOrdersAndCommitWatermark must run only when ValidateStage Succeeded**, not merely when Copy activity Completed.

## 17. SQL Staging Table for Incremental Load

Example staging on Azure SQL Database:

~~~sql
CREATE TABLE dbo.OrdersStage (
    RunId          nvarchar(100) NOT NULL,
    OrderId        bigint NOT NULL,
    CustomerId     bigint NOT NULL,
    Status         nvarchar(30) NOT NULL,
    Amount         decimal(18,2) NOT NULL,
    ModifiedAtUtc  datetime2(7) NOT NULL,
    CONSTRAINT PK_OrdersStage
        PRIMARY KEY (RunId, OrderId)
);

CREATE TABLE dbo.OrdersCurrent (
    OrderId        bigint NOT NULL PRIMARY KEY,
    CustomerId     bigint NOT NULL,
    Status         nvarchar(30) NOT NULL,
    Amount         decimal(18,2) NOT NULL,
    ModifiedAtUtc  datetime2(7) NOT NULL
);
~~~

**Assumption of this example:** each `OrderId` has one current row in the window. If the source is a multi-version log for the same `OrderId`, select the latest version per commit sequence/business rule before loading into staging with primary key `(RunId, OrderId)`.

### 17.1. Why Include `RunId`?

- Clearly identifies which run owns each staged row.
- Enables pre-apply validation at the sink.
- Prevents a failed run from polluting another run's data.
- Supports retries, diagnostics, and retention cleanup.

### 17.2. Staging Rerun Mechanism

Before copying into staging, run **`DELETE FROM dbo.OrdersStage WHERE RunId = @RunId`** in a controlled step, or isolate staging per attempt. Never `TRUNCATE` a shared staging table across concurrent runs without serialization.

### 17.3. `RunId` and Attempts

Some engines perform **activity retries** without changing the pipeline `RunId`, risking partial rows from the prior attempt remaining in staging. Clean up the **attempt's** staged rows before retrying or use an idempotent staging sink. Never let Copy throw primary-key duplicate errors expecting retries to heal themselves.

## 18. Applying Deltas via Conditional Upsert

Definition of **idempotent upsert**: applying the same delta multiple times produces the exact same final state as applying it once, respecting defined business ordering.

In SQL Server/Azure SQL, you can execute `UPDATE` followed by `INSERT` inside a transaction. Simple example:

~~~sql
DECLARE @RunId nvarchar(100) = N'RUN-DEMO-001';

BEGIN TRANSACTION;

UPDATE target
SET target.CustomerId = stage.CustomerId,
    target.Status = stage.Status,
    target.Amount = stage.Amount,
    target.ModifiedAtUtc = stage.ModifiedAtUtc
FROM dbo.OrdersCurrent AS target
JOIN dbo.OrdersStage AS stage
  ON stage.OrderId = target.OrderId
WHERE stage.RunId = @RunId
  AND stage.ModifiedAtUtc >= target.ModifiedAtUtc;

INSERT INTO dbo.OrdersCurrent (
    OrderId, CustomerId, Status, Amount, ModifiedAtUtc
)
SELECT stage.OrderId,
       stage.CustomerId,
       stage.Status,
       stage.Amount,
       stage.ModifiedAtUtc
FROM dbo.OrdersStage AS stage
WHERE stage.RunId = @RunId
  AND NOT EXISTS (
      SELECT 1
      FROM dbo.OrdersCurrent AS target WITH (UPDLOCK, HOLDLOCK)
      WHERE target.OrderId = stage.OrderId
  );

COMMIT TRANSACTION;
~~~

**Run only on lab tables.** In production, encapsulate in a stored procedure with tested **TRY/CATCH, XACT_ABORT, transaction isolation/locking policies, validation, versioning, and error logging**.

### 18.1. Why Compare `ModifiedAtUtc`?

If an older run replays after a newer run, it must not overwrite current state with stale values. Still, timestamps are not always perfect versions; if a reliable **source change sequence, `rowversion`, or `aggregateVersion`** exists, prefer it for state ordering.

### 18.2. `MERGE` Is an Option, Not Magic

T-SQL offers **`MERGE`**, though concurrency, duplicate source rows, and SQL version behaviors need careful handling. Never assume a bare `MERGE` without locking or transactions is automatically idempotent and safe under all loads.

### 18.3. Pure `INSERT` Can Suffice for Append-Only Data

If every source event is immutable and UPDATEs/DELETEs never happen, the sink can append with a unique constraint guarding against duplicates. Avoid overcomplicating pipelines when the contract is genuinely append-only.

## 19. Committing the Watermark in the Same Transaction When Possible

When both the target table and watermark table live in the **same Azure SQL Database**, a stored procedure can apply the delta and advance the watermark inside **one database transaction**.

Illustrative T-SQL pseudocode:

~~~sql
CREATE OR ALTER PROCEDURE dbo.usp_CommitOrderWindow
    @RunId nvarchar(100),
    @PipelineName nvarchar(200),
    @ExpectedOldUtc datetime2(7),
    @UpperUtc datetime2(7)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @ActualOldUtc datetime2(7);

        SELECT @ActualOldUtc = LastWatermarkUtc
        FROM dbo.EtlWatermark WITH (UPDLOCK, HOLDLOCK)
        WHERE PipelineName = @PipelineName;

        IF @ActualOldUtc IS NULL
           OR @ActualOldUtc <> @ExpectedOldUtc
        BEGIN
            THROW 51000,
                  'Watermark changed or not initialized',
                  1;
        END;

        -- Execute idempotent upsert from OrdersStage
        -- by @RunId into OrdersCurrent here.
        -- Validate row counts and business constraints before committing.

        UPDATE dbo.EtlWatermark
        SET LastWatermarkUtc = @UpperUtc,
            UpdatedAtUtc = SYSUTCDATETIME()
        WHERE PipelineName = @PipelineName;

        UPDATE dbo.EtlRunLog
        SET Status = N'SUCCEEDED',
            CompletedAtUtc = SYSUTCDATETIME()
        WHERE RunId = @RunId;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;
~~~

**Very important:** the procedure above is an **illustrative skeleton**, omitting the actual upsert and validation SQL. Never deploy the skeleton directly to advance watermarks in production: insert and thoroughly test the real apply and validation logic inside the transaction before permitting the watermark `UPDATE`.

### 19.1. When the Control Database and Sink Are Separate

No automatic atomic transaction spans across:

- Copying files into ADLS.
- Upserting into an Azure SQL database.
- Updating a watermark in a separate database.
- Publishing messages over Service Bus.

In such topologies, design for **at-least-once delivery + idempotent sinks**:

1. Copy/apply durably.
2. Validate.
3. Advance the watermark only after success.
4. If updating the watermark fails, rerunning the same window re-copies data while sink upsert/deduplication prevents duplicates.
5. Use manifests/commit markers for file sinks where needed.

### 19.2. Watermarks Alone Do Not Prevent Missed Records

An exact watermark still relies on the source providing a trustworthy change signal. If source timestamps are wrong or late, even a flawless apply transaction will miss the uncaptured row.

## 20. Validation: More Than Counting `rowsCopied`

Copy activity reports metrics like **`rowsRead`**, **`rowsCopied`**, bytes, and duration per connector/output. These aid observability but do not prove business accuracy.

Validation checks can include:

- Window source row count vs. staging count.
- Unique `OrderId` within the run.
- Zero nulls in mandatory columns.
- No negative `Amount` where prohibited by business rules.
- Schema/version within supported bounds.
- Zero duplicate `OrderId`s in destination.
- Expected distribution across statuses/tenants.
- Partition/window monetary totals or checksums where reliably measurable.
- Source UPDATEs/DELETEs reflected per contract.
- Spot-check reconciliation on sample keys.

### 20.1. Source Counts Are Not Always Static

If the source receives writes during Copy, a `COUNT` before Copy and the Copy query itself see two different snapshots. For strict reconciliation, align snapshot/isolation levels or use CDC/change windows with versions.

### 20.2. Zero Count Is Not Automatically an Error

An hour with no changes legitimately produces a **zero-row delta**. Pipelines must distinguish "no changes occurred" from source read failures or miscalculated bounds.

### 20.3. Never Advance Watermarks on Data Quality Failures

If 1,000 rows are copied and 100 fail validation without being handled by an approved quarantine policy, never advance the watermark past the window if doing so prevents reprocessing.

## 21. SQL Change Tracking: Version-Based Incremental Loads

**SQL Server/Azure SQL Change Tracking** (where supported and enabled) records **which primary keys changed** since a given change version. It helps on mutable tables with INSERT, UPDATE, and DELETE when timestamps are unreliable.

Concept:

~~~sql
SELECT CHANGE_TRACKING_CURRENT_VERSION()
    AS UpperVersion;
~~~

Fetch keys changed since the last version:

~~~sql
SELECT
    CT.OrderId,
    CT.SYS_CHANGE_VERSION,
    CT.SYS_CHANGE_OPERATION,
    S.CustomerId,
    S.Status,
    S.Amount,
    S.ModifiedAtUtc
FROM CHANGETABLE(
    CHANGES dbo.Orders, @LastVersion
) AS CT
LEFT JOIN dbo.Orders AS S
    ON S.OrderId = CT.OrderId
WHERE CT.SYS_CHANGE_VERSION <= @UpperVersion;
~~~

**This is an illustrative pattern**: verify CT is enabled and permissions exist; the join reflects current row state at query time rather than every intermediate version. When the source changes during reads, use snapshot isolation or an equivalent consistency mechanism.

### 21.1. Handling `DELETE`

When **`SYS_CHANGE_OPERATION = 'D'`**, the row may no longer exist in the source table; apply a tombstone or delete operation at the sink per contract.

### 21.2. Retention and Minimum Valid Version

CT enforces retention and automatic cleanup. Before reading, check:

~~~sql
SELECT CHANGE_TRACKING_MIN_VALID_VERSION(
    OBJECT_ID('dbo.Orders')
) AS MinValidVersion;
~~~

If your checkpoint version is **older than the min valid version**, changes may have been purged. Perform a planned reinitialization/full resync—**never advance the version blindly and skip history**.

### 21.3. CT Is Not Full Event History

CT tracks which rows changed, not every before/after transaction payload like CDC logs. Choose CT when you need current-state replication and understand its boundaries.

## 22. Change Data Capture (CDC): Capturing INSERT, UPDATE, and DELETE

**CDC** captures changes from the transaction log via source-supported mechanisms. It fits when you need to:

- Track `DELETE`s.
- Preserve multiple intermediate changes between runs.
- Rely on log sequences/checkpoints rather than application timestamps.
- Build downstream change streams or full audit history.
- Maintain ordering within supported log semantics.

### 22.1. The LSN Concept

A **Log Sequence Number (LSN)** marks a log position in SQL Server CDC solutions. Incremental windows must carefully align LSN bounds to avoid overlaps or gaps due to inclusive/exclusive semantics of CDC functions.

### 22.2. Do Not Confuse CDC with an Activity Name

Some services/connectors provide native CDC or managed pipelines under specific conditions; others require change tables, log connectors, or specialized engines. **Picking Copy activity does not automatically enable CDC.** Verify connector, source version, permissions, and retention.

### 22.3. Operational Prerequisites

- Log/change retention exceeds the longest outage/backlog recovery target.
- Permissions to read change tables/logs.
- Schema evolution handling.
- Commit-based checkpointing.
- Consumers apply changes idempotently and in order.
- Reinitialization procedure when retention windows expire.

### 22.4. Choosing Watermark, CT, or CDC?

| Need | Recommendation |
|---|---|
| Simple append-only | ID/timestamp with clear semantics |
| Small mutable table, easy reconciliation | `ModifiedAtUtc` + overlap/checked idempotent upsert |
| SQL current-state replication | Change Tracking |
| Audit/history with INSERT/UPDATE/DELETE | CDC / log-based mechanism |
| Source lacks change signals | Periodic full or snapshot-diff within capacity |

Do not pick CDC just because it sounds "enterprise"; each option brings distinct cost and operational complexity.

## 23. Handling `DELETE`s and Tombstones

A pipeline copying only currently existing rows cannot tell which rows were deleted from the source.

Example:

~~~text
Source 09:00: OrderId=1001 exists
Source 09:30: OrderId=1001 is DELETED

Incremental copy by ModifiedAt:
    No row 1001 returned to copy
    -> Sink keeps 1001 forever
~~~

Solutions:

- Use **soft deletes**: update `IsDeleted`/`DeletedAt` columns so incremental queries pick them up.
- Use **CT/CDC** with delete markers.
- Use periodic full reconciliations/diffs for small enough datasets.
- Emit tombstone events from domain services.

### 23.1. Soft Delete Example

~~~sql
UPDATE dbo.Orders
SET IsDeleted = 1,
    ModifiedAtUtc = SYSUTCDATETIME()
WHERE OrderId = 1001;
~~~

Execute only if the source schema includes `IsDeleted` and the business agrees to soft deletes. Otherwise treat this SQL strictly as illustrative.

### 23.2. Choosing Sink Policy

- Hard delete on a mirror table.
- Soft delete in the sink.
- Store event/tombstone history and compute current state downstream.
- Retain records under compliance holds where required.

Align deletion rules with data owners and retention policies.

## 24. What Is Pipeline Orchestration?

**Orchestration** coordinates activities across dependencies and conditions, handles timeouts/retries, passes parameters, logs run states, routes success/failure branches, manages concurrency, and schedules triggers.

Example:

~~~mermaid
flowchart TD
    START[Schedule/tumbling trigger] --> P[Prepare run]
    P --> L[Lookup watermark]
    L --> C[Copy delta]
    C --> V{Validation passed?}
    V -->|Yes| A[Apply delta]
    V -->|No| F[Record failure and alert]
    A --> W[Commit watermark]
    W --> S[Audit success]
    C -. Failure .-> F
    A -. Failure .-> F
    W -. Failure .-> F
~~~

### 24.1. Pipelines Are Branching DAGs

ADF pipelines use a control-flow graph with dependencies, ForEach/Until loops, and branching; not every workflow is a linear SQL script.

### 24.2. Activity Success vs. Pipeline Success

If you wire a Failure branch whose final notification activity returns Succeeded, overall pipeline status can appear green depending on the dependency graph. Ensure error branches **explicitly fail the pipeline** or report failure whenever the business load did not complete—never mask failures.

### 24.3. Do Not Use Pipeline Variables as Distributed Locks

Variables hold state local to a single pipeline run, not a global database lock preventing two runs from colliding. Use pipeline concurrency controls or atomic claims in a control store.

## 25. Lookup, Get Metadata, and Stored Procedure Activities

| Activity | Used For | Example |
|---|---|---|
| **Lookup** | Reading small query/config results | `LastWatermarkUtc` |
| **Get Metadata** | Retrieving file/field metadata from datasets | File existence, child items list |
| **Copy** | Moving data | SQL delta to staging |
| **Stored Procedure** | Executing SQL stored procs on supported connectors | Apply delta / commit progress |
| **Script** | Running SQL scripts on supported connectors | Control table updates/validation |
| **If Condition** | Conditional branching | `rowsCopied > 0` |
| **Set Variable** | Setting transient state | `currentBatchIndex` |
| **Execute Pipeline** | Invoking child pipelines | `pl_load_one_table` |
| **Web** | Calling HTTP endpoints | Alerting an approved webhook |

### 25.1. Do Not Use Lookup to Load Millions of Rows

Lookup targets metadata and small result sets, with service-enforced output size and timeout limits. Move bulk data with Copy activity or a compute engine.

### 25.2. Get Metadata File Listings Have Limits

In folders with vast file counts, Get Metadata hits output and cost limits. Use partitioned folder layouts, file manifests, or event-driven ingestion instead of scanning an entire filesystem each run.

### 25.3. Stored Procedures Require Permissions

Data Factory's connected identity needs `EXECUTE` and whatever permissions the procedure invokes under the security model. Never grant `db_owner` when permissions on a single procedure suffice.

## 26. If Condition and Handling Zero-Row Deltas

Suppose Copy returns **`rowsCopied`** (exact field names vary by connector/copy mode). A dynamic expression could be:

~~~text
@greater(activity('CopyOrdersToStage').output.rowsCopied, 0)
~~~

In ADF, use If Condition:

- **True**: run validation/apply because rows arrived.
- **False**: skip applying rows, while still deciding safely whether to advance the watermark once you confirm the source genuinely had zero changes for a valid window.

**Zero rows is valid** when the source truly had no changes. However, zero rows caused by a buggy query, filtered permissions, wrong dynamic path, or silent read error must never count as business success.

### 26.1. Do Not Use `rowsCopied` as a Watermark

`rowsCopied` counts rows transferred, not the **position of processed data**. Watermarks require timestamps, sequences, LSNs, or IDs.

### 26.2. Always Inspect Actual Output Fields

Before hard-coding expressions, run a test and inspect **Activity Output JSON**. Output schemas vary across connectors; referencing non-existent properties fails at runtime.

## 27. ForEach and Metadata-Driven Pipelines

A data platform often syncs multiple tables:

~~~text
dbo.Orders
dbo.Customers
dbo.Products
dbo.Payments
~~~

Instead of cloning four nearly identical pipelines, build a **metadata/control table**:

~~~sql
CREATE TABLE dbo.EtlTableConfig (
    SourceSchema    sysname NOT NULL,
    SourceTable     sysname NOT NULL,
    SinkTable       sysname NOT NULL,
    WatermarkColumn sysname NULL,
    IsEnabled       bit NOT NULL,
    PRIMARY KEY (SourceSchema, SourceTable)
);
~~~

The parent pipeline uses Lookup to fetch enabled tables, then **ForEach** iterates and calls child pipeline **`pl_load_one_table`** with parameters.

### 27.1. Safe Parameterization

Schema, table, and column names must come from a vetted internal allowlist. When constructing dynamic SQL, quote identifiers with SQL-dialect functions and never accept arbitrary HTTP user input.

### 27.2. Parallel ForEach and Variables

When ForEach runs in parallel, never use a shared pipeline variable to hold per-table watermarks or run results without isolation. Concurrent iterations overwrite variables. **Passing parameters and persisting per-table state in a control DB** is far safer.

### 27.3. Concurrency and `batchCount`

ForEach supports sequential or parallel execution up to service limits. Choose concurrency based on source and sink capacity, not guesswork. Excessive concurrency can overwhelm an on-prem SQL Server or exhaust sink capacity.

### 27.4. Failure Isolation

If one table fails, decide explicitly whether to:

- Fail the entire parent pipeline.
- Record the per-table error and continue independent tables.
- Retry only failed tables later.
- Gate downstream gold transforms so they run only when required dependency tables succeeded.

Run statuses must distinguish partial success from full success.

## 28. Execute Pipeline and Layered Orchestration

An operable hierarchy:

~~~text
pl_daily_analytics
  |
  +-- pl_ingest_orders
  +-- pl_ingest_customers
  +-- pl_ingest_products
  |
  +-- pl_validate_curated
  |
  +-- pl_build_marts
  |
  +-- pl_publish_reporting
~~~

Use **Execute Pipeline** to invoke child pipelines with parameters. Depending on dependencies, wait for child completion before running downstream stages.

### 28.1. Do Not Equate Parent Start with Child Completion

If Execute Pipeline does not wait for child completion or error branches fail to propagate errors, the parent pipeline can report completion before reporting data is ready. Configure wait and dependency semantics properly.

### 28.2. Layered Idempotency

- Ingestion idempotent by source keys and windows.
- Curated merges idempotent by versions.
- Mart publishing keyed by version/batch markers.
- Downstream consumers blocked from reading unpublished or unvalidated data.

### 28.3. Separation of Concerns

Ingestion pipelines capture and store raw/staged data. Transform pipelines handle quality and business mappings. Publish pipelines control consumer readiness. Never stuff complex business logic into brittle Copy expressions.

## 29. Schedule Triggers: Time-Based Execution

A **Schedule trigger** launches pipelines on a fixed cadence, e.g., hourly:

~~~text
00:00  Pipeline run A
01:00  Pipeline run B
02:00  Pipeline run C
~~~

### 29.1. Risk When Runs Exceed the Schedule Interval

If run A takes 90 minutes, run B may start before A finishes unless concurrency is capped. Two runs reading the same watermark can collide or overwrite outputs.

Mitigations:

- Cap pipeline **concurrency** as needed (e.g., 1 for single sequential streams).
- Use control-table claims/locks to protect against manual reruns or overlapping pipelines.
- Maintain queueing/backlogs when throughput lags.
- Never silently skip intervals without a catch-up plan.

### 29.2. Timezone and DST

Local timezone schedules can shift or repeat hours during Daylight Saving Time. For predictable pipeline windows, standardize timestamps and watermarks in **UTC**, converting to business timezones in the reporting layer.

### 29.3. Schedule Is Not a Commit Checkpoint

A trigger firing on time does not mean source data arrived on time or the prior run succeeded. Watermarks must remain independent of trigger cadence.

## 30. Tumbling Window Triggers: Stateful Time Windows

A **Tumbling window trigger** models contiguous, non-overlapping time intervals with stateful tracking, backfills, and window dependencies per service support.

Example half-hour windows:

~~~text
[00:00, 00:30)
[00:30, 01:00)
[01:00, 01:30)
[01:30, 02:00)
~~~

In queries, use **`>= start AND < end`** to align directly with half-open windows. This convention differs from the **`(last, upper]`** watermark pattern, yet both are valid if applied **consistently** without dropping or duplicating boundary rows.

### 30.1. Define Boundary Conventions Explicitly

- Standard tumbling window: **`[start, end)`**.
- High-water watermark pattern: **`(last, upper]`**.
- Never mix both conventions without verifying boundary timestamps.

### 30.2. Backfills

Tumbling windows simplify re-running historical windows within service support. However, **backfills are safe only if the sink is idempotent**, windows are tracked, and source retention still holds historical data.

### 30.3. Window Dependencies

Downstream windows can wait for upstream dependency windows to complete per trigger capabilities. Never confuse schedule start times with downstream pipelines having clean data.

### 30.4. Trigger Windows Do Not Solve Late Commits

If the source writes late rows into an already closed event-time window, you still need a late-arrival policy, overlap, CT/CDC, or reconciliations.

## 31. Storage Event Triggers: Running When Files Arrive

For supported Azure Storage file sources, **storage event triggers** backed by Event Grid can start pipelines upon file creation or matching events.

Example:

~~~text
Producer uploads file -> ADLS container
     |
     v
BlobCreated event
     |
     v
ADF storage event trigger
     |
     v
Pipeline validates/copies/processes file
~~~

### 31.1. Not Automatically Exactly-Once

Event-driven systems can deliver duplicate notifications or reprocess files on retries. Use **file ID/path + ETag/version/run manifest** as an idempotency key per connector capabilities rather than assuming "each file emits one event."

### 31.2. Is the File Ready?

For multipart uploads or external transfers, define how file completion is confirmed:

- Upload to a temporary path then publish/rename/commit a marker.
- Deliver a manifest listing expected files and counts.
- Trigger only on completion events guaranteed by the service/producer.
- Validate file size, schema, and row count before applying.

Never assume an event trigger natively understands arbitrary producer upload lifecycles.

### 31.3. When Not to Use Event Triggers

When ingesting fixed windows that aggregate multiple files arriving asynchronously, tumbling windows/schedules paired with manifests fit better.

## 32. Timeouts, Retries, and Error Handling

ADF activities support **`retry`, `retryInterval`, and `timeout`** policies per activity type. Retries overcome transient glitches, yet risk duplicate writes if sinks lack idempotency.

### 32.1. Error Classification

| Error Type | Example | Remediation |
|---|---|---|
| Transient | HTTP 429/503, network timeout, Azure SQL throttling | Bounded retries + backoff; check capacity |
| Authentication | Expired credential, wrong managed identity | Fix permissions/secrets; do not retry infinitely |
| Authorization | SQL permission denied, ADLS ACL 403 | Verify data-plane permissions |
| Data/schema | Type conversion, missing column, invalid JSON | Validate/quarantine; update mappings |
| Data correctness | Duplicate key, bad watermark, row count mismatch | Halt commit; investigate / idempotent rerun |
| Capacity | High SHIR CPU, SQL DTU/vCore saturation | Lower concurrency, scale, or reschedule |
| Source retention | CDC/CT checkpoint expired | Controlled reinitialization/resync |

### 32.2. Retries and Duplicates

Suppose Copy writes partial data and hits a network timeout. If the activity retries on an **append** sink, duplicate rows or files can appear. Safeguards:

- Stage by run/attempt.
- Clean the attempt's staging before retrying, or use deterministic output names with controlled overwrites.
- Upsert/deduplicate by business key during apply.
- Hold watermarks until after durable commits.

### 32.3. Timeouts Do Not Roll Back the Sink

Activity timeouts/cancellations are not distributed rollbacks spanning source, IR, and sink. After a timeout, inspect what landed at the sink before rerunning.

### 32.4. Failure Branches

Log errors, emit alerts, and retain the old watermark. Ensure the pipeline ends in an explicit failed state; if error handlers swallow errors and leave the pipeline marked Succeeded, monitoring may fail to page on-call.

## 33. Idempotency on Pipeline Reruns

**Idempotency** means running the same window/run multiple times yields the exact same destination state and side effects.

Example:

~~~text
Run A:
  Copy 1,000 rows succeeds
  Apply 1,000 rows succeeds
  Update watermark fails
  -> Pipeline Failed

Run B:
  Reads old watermark
  Re-copies 1,000 rows
  Idempotent apply
  Watermark commits
  -> Pipeline Succeeded
~~~

If the sink blindly appends without deduplication, Run B produces 2,000 rows. If the sink upserts by `OrderId + version`, final state stays accurate.

### 33.1. Techniques

- Business keys / unique constraints.
- Version-guarded upserts/replacements.
- Manifests or commit markers for batch files.
- Identifiers for window, run, and source change sequence.
- Atomic transactions for apply + watermark when inside the same database.
- Failure testing at every operational boundary.

### 33.2. Not Automatic End-to-End Exactly-Once

ADF Copy activity + pipeline control flow do not create an automatic ACID transaction across two separate services. You can achieve **effectively-once business outcomes** via idempotent sinks, verified through testing.

### 33.3. Deletes, Events, and Side Effects

If a pipeline also sends emails or Service Bus messages after copying, reruns can replay them. Use outboxes, message deduplication keys, or downstream idempotency.

## 34. Concurrency: Across Runs and Across Tables

There are at least three concurrency levels:

1. **Pipeline-run concurrency**: concurrent runs of the same pipeline.
2. **ForEach parallelism**: concurrent tables/branches inside a run.
3. **Copy internal parallelism**: parallel copy streams/DIUs per connector.

When all three are set high, SQL sources and sinks can face unexpected load spikes.

### 34.1. Risk Example

~~~text
Pipeline concurrency: 2 runs
ForEach: 10 tables concurrently
Each Copy: multiple parallel reader/writer tasks

Total load hitting SQL can be far higher
than simply thinking "10 tables".
~~~

### 34.2. Limiting Strategy

- Serialize incremental runs per table when sharing a watermark.
- Run independent tables in parallel with a sensible `batchCount`.
- Shift heavy batch loads outside OLTP peak hours.
- Cap max connections/queries on the source.
- Monitor SHIR queue times, source CPU, SQL waits, and ADLS throughput.
- Prioritize loads by SLA/SLO when multiple teams ingest simultaneously.

### 34.3. Do Not Optimize Copy Throughput in Isolation

If fast ingestion stalls the transactional application, the solution fails overall requirements. Set SLOs covering both OLTP source health and analytics availability.

## 35. Performance Tuning Copy Activity

Measure before tuning:

- Data read throughput and write throughput.
- Rows/bytes read and copied.
- Source query execution time.
- IR provisioning/queueing time.
- Network transfer duration.
- Sink staging/commit duration.
- Parallel reader/writer counts.
- Azure SQL/ADLS throughput capacity.
- SQL locks, DTU/vCore usage, I/O, and SHIR health.

### 35.1. Partitioned Source Reads

Some SQL connectors support partitioned reads by range or physical partition. This boosts throughput on large tables while issuing multiple concurrent queries.

Check:

- Indexes on partition keys/read ranges.
- Zero overlaps or gaps across ranges.
- Snapshot/read consistency.
- Source tolerance for parallel scans.
- Sufficient network/IR capacity.

### 35.2. Sink Bulk Ingestion

Relational sinks may support batch sizes, write behaviors, or native bulk loaders. Setting batch sizes too large can increase locking, transaction log pressure, or timeouts.

### 35.3. Compression and File Sizes

For ADLS Parquet, partition by date/system or appropriate keys. Avoid writing millions of tiny files, which inflate file listing, metadata operations, and downstream scan costs.

### 35.4. Controlled Load Testing

Benchmark with production-like data, measuring end-to-end throughput and source impact. Never crank DIUs/`parallelCopies` to maximum while ignoring cost and source latency.

## 36. Schema Drift, Mapping, and Data Contracts

Sources can add, rename, or alter column types. Pipelines lacking data contracts easily suffer from:

- Type conversion Copy failures.
- Silently ignored new columns.
- Data shifted into wrong columns.
- Silent null writes.
- Broken downstream marts.

### 36.1. Separating Three Change Types

| Change | Example | Response |
|---|---|---|
| Backward-compatible | Adding a nullable column | Update mapping through standard process |
| Breaking | Changing `CustomerId` bigint to string with new semantics | Migration plan / schema version |
| Bad data | `Amount` contains unparseable text | Quarantine or fail validation |

### 36.2. Explicit Mapping and Validation

For critical pipelines, define explicit mappings, test per-column conversions, and verify schema versions. Auto-mapping is convenient for labs yet can mask structural source changes.

### 36.3. Parquet/JSON Do Not Fix Logical Schema Drift Automatically

Flexible file formats handle some structural shifts, yet downstream SQL/analytics still depend on known data types, mandatory fields, and versioning rules.

### 36.4. Data Contract Ownership

Each source table/stream needs an owner, documented primary key, watermark semantics, deletion policy, timezone, SLAs, and a breaking-change notification process.

## 37. Monitoring Pipelines and Copy Activity

ADF Monitor and Azure Monitor provide pipeline/activity status, duration, errors, and connector-reported Copy metrics. Applications should add custom **business/data-quality metrics**.

| Area | Metric / Check | Meaning |
|---|---|---|
| Scheduling | Trigger fires, start delay | Is the pipeline running on cadence? |
| Pipeline state | Succeeded/Failed/Cancelled | Are orchestration failures occurring? |
| Copy | Rows read/copied, throughput, duration | Is data transfer healthy? |
| Data completeness | Source/destination counts, hashes, missing keys | Was any data missed? |
| Incremental lag | Source latest commit − committed watermark | Is the pipeline falling behind? |
| Retries | Attempts/timeouts/throttling | Is something overloaded? |
| IR | SHIR CPU/queue/offline, Azure IR wait | Is transfer infrastructure bottlenecked? |
| SQL/Storage | CPU/I/O, transactions, requests | Do source/sink have headroom? |
| Cost | Activity runs, DIU hours, storage/compute | Is spend within budget? |

### 37.1. Distinguish Monitoring from Watermarks

A **Succeeded** pipeline does not prove the watermark is right or destination data is complete. Conversely, a pipeline that failed after apply may have committed destination data while the watermark stayed behind.

### 37.2. Correlation

Log these fields in your run log:

~~~text
PipelineName
PipelineRunId
TriggerName / WindowId
SourceTable
SinkObject
StartWatermark
UpperWatermark
RowsRead
RowsCopied
RowsApplied
StartedAtUtc / CompletedAtUtc
Status / ErrorCode
~~~

### 37.3. Alerting on Data Freshness

If data has a 15-minute SLO to appear in a mart, alert on **watermark age / data freshness**, not merely "pipeline run started."

## 38. Security and Private Networking for Data

A data pipeline crosses several trust boundaries:

~~~text
Source SQL Server (on-prem / Azure VM)
       |
Self-hosted IR / Azure IR + private connectivity
       |
ADLS Gen2 landing / Azure SQL staging
       |
Curated analytics / reporting
~~~

Principles:

- Never expose SQL Server publicly for quick lab testing.
- Prefer managed identities and least privilege wherever connectors support them.
- Store secrets in Key Vault—never in ARM JSON or logs.
- Scope source `SELECT`, sink `INSERT/UPDATE/EXECUTE`, and Storage ACLs tightly.
- Enforce TLS/encryption in transit and encryption at rest per policy.
- Use private endpoints, VNet integration, or SHIR matching your network topology.
- Verify DNS resolution from the **executing IR**, not just an admin workstation.
- Separate dev/test/prod identities, databases, and storage containers.
- Protect PII: masking, column-level access, auditing, retention, and purging.
- Review data residency and cross-region outbound transfers.

### 38.1. Key Vault References

ADF Linked Services can reference secrets per feature support. The factory's managed identity needs secret read permissions under Key Vault's access policy/RBAC model alongside reachable networking.

### 38.2. ADLS Gen2 RBAC and ACLs

With hierarchical namespace enabled, Azure RBAC data roles and POSIX-like ACLs govern distinct access paths. Management-plane `Reader` does not grant permission to create files in folders.

### 38.3. On-Prem SHIR and Credentials

Manage SHIR nodes as critical infrastructure: OS patching, local service accounts, secret protection, outbound rules, HA, and monitoring. Never embed cleartext passwords in pipeline expressions.

## 39. Git, CI/CD, and Multiple Environments

ADF supports authoring/publishing workflows and Git integration per service capabilities. Production pipelines require:

- Code reviews for pipeline definitions.
- Parameterized linked services and datasets.
- Environment-specific endpoints, resource groups, and storage paths.
- Secrets sourced via Key Vault/identities.
- Infrastructure as Code and release approvals.
- Automated post-deployment validation/smoke tests.
- Rollback strategies for pipeline or schema changes.
- Trigger management to avoid accidental runs during cutovers.

### 39.1. Definitions in Git Are Not Automatically Live

In ADF Git integration, the authoring branch/repository and **published/live factory artifacts** require separate sync/publish/deployment steps. Always verify what is actually running rather than assuming a Git commit immediately updates production triggers.

### 39.2. Never Store Secrets in Linked Service JSON

Git repositories are readable by many team members; store references and parameters only—never passwords or connection strings containing credentials.

### 39.3. Deploying Pipelines Differs from Deploying Data/Schemas

Updating pipeline JSON does not migrate Azure SQL schemas or create indexes. Coordinate database migrations, permissions, and release ordering.

## 40. Data Factory and Related Service Costs

Costs extend beyond the ADF resource itself:

| Category | Example Billing Drivers |
|---|---|
| ADF orchestration | Activity executions/runs per pricing model |
| Data movement | DIUs/data movement compute and duration |
| Data flow | Compute consumed when using Mapping Data Flows |
| Self-hosted IR | VM/on-prem hosts, operations, and networking |
| Azure SQL | vCore/DTU/storage/transaction logs from source reads and sink writes |
| ADLS Gen2 | Capacity, transactions, tiers, and egress |
| Monitoring | Azure Monitor/Log Analytics ingestion and retention |
| Networking | Egress, Private Link, NAT/Firewalls, and inter-region transfers |
| Backfill/retries | Re-reading/re-writing data and extra pipeline runs |
| Downstream compute | Synapse, Databricks, Spark, or BI engines |

Rates vary by region, execution type, time, and contract; never quote fixed unit prices without checking current Azure pricing.

### 40.1. Incremental Usually Saves Over Full Copy

If only 1% of a table changes daily, incremental loads dramatically reduce transfer volume. However, if an incremental query triggers a full table scan due to a missing index, the source SQL server still pays high compute cost despite copying few rows.

### 40.2. Avoid Wasteful Micro-Activities

In metadata-driven workloads, tens of thousands of tiny activities generate orchestration overhead and cost. Batch or group work sensibly around SLOs, monitoring, and cost.

### 40.3. Do Not Use Retries as a Scaling Strategy

Retrying endlessly when SQL is throttled or IR queues are backed up inflates executions and latency. Locate the bottleneck and adjust concurrency, scheduling, or capacity systematically.

## 41. Runbook: Incremental Pipeline Fails Mid-Run

An execution trace:

~~~text
10:00  Watermark = 09:30
10:01  Upper = 10:00
10:02  Copy to staging starts
10:05  Copy writes partial rows, then times out
10:06  Pipeline Failed
~~~

Procedure:

1. Capture `RunId`, window start/upper, and activity outputs.
2. Verify the control-table watermark is still 09:30.
3. Inspect partial data landed in staging/landing.
4. Identify whether the fault is source, network, IR, sink, or mapping.
5. Clean up only the **run/attempt's partial staging** per policy; never `TRUNCATE` shared staging.
6. Rerun the claimed window or restart from the committed watermark per design.
7. Apply idempotently; verify duplicates, updates, and deletes.
8. Advance the watermark only after validation.
9. Log the new run status and reconcile counts.
10. Alert if latency breaches SLA.

### 41.1. Failure After Target Commit

Target data is already updated, yet the watermark update failed. Rerunning may re-copy rows; the sink/upsert must absorb this safely. Never manually bump the watermark without verifying every record in the window was applied.

### 41.2. Watermark Committed Yet Downstream Mart Failed

Know whether the watermark tracks **ingestion** or the **full business pipeline**. Separate stage checkpoints (bronze/silver/gold) let you retry marts without re-ingesting from the source.

### 41.3. When CT/CDC Retention Has Expired

Purged changes cannot always be replayed from CT/CDC logs. Execute a controlled full resync/reseed or recover from archives and reconcile. Never bump checkpoints to current version just to hide a gap.

## 42. Lab 1: Full Load and Watermark-Based Incremental Load

**Prerequisites:** use an authorized lab Azure subscription/resource group, a sample Azure SQL/SQL Server, and an ADLS Gen2 or Azure SQL sink. Never run destructive SQL on production data.

### A. Prepare the Source

Create a sample `Orders` table with `OrderId, CustomerId, Status, Amount, ModifiedAtUtc`. Insert rows with distinct `ModifiedAtUtc` values, explicitly documented in UTC.

~~~sql
INSERT INTO dbo.Orders (
    OrderId, CustomerId, Status, Amount, ModifiedAtUtc
)
VALUES
(101, 1, N'CREATED', 120.00, '2026-11-20T09:01:00'),
(102, 2, N'PAID',    90.00, '2026-11-20T09:02:00'),
(103, 1, N'CREATED', 300.00, '2026-11-20T09:03:00');
~~~

Run only if the lab table exists and `OrderId` values do not collide.

### B. Create Linked Services and Datasets

1. Source SQL linked service.
2. Staging sink linked service and dataset.
3. Network-aligned Integration Runtime.
4. Source `SELECT`, staging `INSERT`, and procedure `EXECUTE` permissions if used.
5. Optional ADLS landing if preserving raw copies.

### C. Run the Initial Full Seed

1. Choose an initial watermark prior to the earliest record.
2. Copy seed data into staging/target.
3. Validate row counts and sample business keys.
4. Set the initial watermark matching **fully applied** state.
5. Record `RunId` and seed metadata.

### D. Run Incremental

1. Look up the old watermark.
2. Determine a valid upper bound.
3. Copy rows within the window.
4. Inspect staging.
5. Run idempotent upsert into `OrdersCurrent`.
6. Commit the watermark.
7. Compare source and target.

### E. Generate a New `UPDATE`

~~~sql
UPDATE dbo.Orders
SET Status = N'SHIPPED',
    ModifiedAtUtc = '2026-11-20T09:15:00'
WHERE OrderId = 102;
~~~

In the lab, assume the new window covers 09:15 and the prior watermark precedes it. Rerun and confirm row 102 updates in place at the sink rather than producing two rows.

### F. Test Retries

1. Perform a controlled Copy stop or simulate a sink failure.
2. Confirm the watermark did not advance.
3. Rerun the exact same window.
4. Verify the target contains zero duplicate `OrderId`s.
5. Record logs and recovery duration.

## 43. Lab 2: Metadata-Driven Orchestration Across Multiple Tables

Create a config table covering several lab sources:

~~~text
dbo.Orders    -> dbo.OrdersStage
dbo.Customers -> dbo.CustomersStage
dbo.Products  -> dbo.ProductsStage
~~~

Practice:

1. Look up tables where `IsEnabled=1`.
2. Run ForEach **sequentially** first for easy inspection.
3. Invoke the child pipeline passing `sourceSchema/sourceTable/sinkTable`.
4. Maintain an independent watermark per table in the control DB.
5. Log `RunId`, rows copied, status, and errors per table.
6. Increase parallelism slightly and observe SQL/IR capacity.
7. Simulate a single-table failure to verify partial failure reporting and alerts.
8. Never share one watermark across multiple tables that mutate independently.

### 43.1. Success Criteria

- Succeeded tables hold accurate checkpoints.
- Failed tables retain old checkpoints.
- Parent pipeline reports partial/failure state transparently.
- Rerunning failed tables does not duplicate succeeded tables.
- Raising parallelism does not overload the OLTP source.

## 44. Lab 3: Triggers, Backfills, and Runbooks

### A. Schedule Trigger

1. Create a lab schedule with enough cadence headroom to finish.
2. Set low pipeline-run concurrency, such as 1 per watermark stream.
3. Inspect Monitor → Trigger runs and Pipeline runs.
4. Check schedule delay vs. completion time.

### B. Tumbling Window

1. Create synthetic 15- or 30-minute windows.
2. Pass `windowStart/windowEnd` into pipeline parameters.
3. Apply **`[start, end)`** consistently across SQL/file partitioning.
4. Simulate backfilling one window.
5. Verify reruns create no duplicates.
6. Never enable two triggers covering the same range without concurrency control.

### C. Failure and Recovery

1. Simulate a network or permission error in the lab.
2. Verify the pipeline reports Failed and fires alerts.
3. Confirm the watermark did not advance.
4. Fix the root cause.
5. Rerun the failed window.
6. Reconcile final data.
7. Write a 1-page runbook stating owners and when a full resync is required.

### D. Cleanup

1. Stop/disable lab triggers.
2. Confirm no pipeline runs are actively writing.
3. Verify no linked services point to production.
4. Delete only approved lab resources per authorization.
5. Check Azure Cost Management to ensure no compute/storage lingers.

## 45. Production Checklist

- [ ] Source/target owners and data contracts defined.
- [ ] Selected full, watermark, CT, or CDC matching UPDATE/DELETE semantics.
- [ ] Source watermark is trustworthy with explicit timezone and precision.
- [ ] Evaluated commit races, late arrivals, and timestamp ties.
- [ ] CT/CDC retention and expired-checkpoint runbooks documented.
- [ ] Composite cursor or pagination strategy implemented where needed.
- [ ] Control watermark separated from run logs with concurrency coordination.
- [ ] Upper boundary locked once per run and audited.
- [ ] Copy reads consistent window conventions without mixing bounds.
- [ ] Staging/landing isolated by run or attempt.
- [ ] Partial writes do not break retries.
- [ ] Sink apply is idempotent by business keys/versions.
- [ ] Watermarks commit only after durable apply and validation.
- [ ] Tested failures before, during, and after Copy, apply, and watermark steps.
- [ ] Reconciliation checks catch missed records.
- [ ] DELETEs/tombstones handled per policy.
- [ ] Schema drift/mappings versioned and approved.
- [ ] Lookup outputs and expressions tested against real output shapes.
- [ ] ForEach parallelism does not race on pipeline variables.
- [ ] Pipeline-run concurrency/locks prevent competing runs on watermarks.
- [ ] Triggers chosen to fit schedule/window/event needs.
- [ ] Backfills/reruns introduce zero duplicate records.
- [ ] Error branches propagate failures and fire alerts.
- [ ] Retries/timeouts bounded without infinite loops.
- [ ] Azure IR/SHIR have proper networking, DNS, and quotas.
- [ ] Linked services use secrets/identities under least privilege.
- [ ] Azure SQL/ADLS RBAC and ACLs verified.
- [ ] Zero credentials or PII leaked into logs.
- [ ] Monitoring covers freshness, rows, bytes, throughput, and errors.
- [ ] Monitoring tracks SHIR queues/health and SQL source load.
- [ ] Final data SLOs and target reconciliations defined.
- [ ] CI/CD parameterized across separated dev/test/prod environments.
- [ ] Triggers safely managed during deployments.
- [ ] Cost budgets set and DIUs/activity executions tuned.
- [ ] Procedures exist for lab cleanup and secret rotation.

## 46. Self-Check Questions

1. What does Copy activity do, and what does it not solve automatically?
2. How do linked services and datasets differ?
3. Which data sources fit Azure IR vs. self-hosted IR?
4. How does a full load differ from an incremental load?
5. Why does incremental loading by `created_at` miss `UPDATE`s?
6. Must a watermark always be a timestamp?
7. What does a `(last, upper]` window mean?
8. Why must watermarks never advance prior to Copy/apply?
9. What is a commit race, and why might a safety delay still fall short?
10. What risk do tied timestamps pose during pagination?
11. When should you use a `(timestamp, primaryKey)` cursor?
12. How do CT and CDC differ in the change history they capture?
13. What must you do when a CT checkpoint is older than `min valid version`?
14. If a source deletes a row, what happens with an incremental load reading only current rows?
15. How does staging by `RunId` aid recovery?
16. Why doesn't `rowsCopied` prove report accuracy?
17. How do upserts/idempotency help when committing a watermark fails?
18. Are ADF Copy to ADLS and updating a SQL watermark atomic together by default?
19. What output shape does Lookup return when `firstRowOnly=false`?
20. Why shouldn't Lookup load millions of rows?
21. How can parallel ForEach cause race conditions on pipeline variables?
22. When should Execute Pipeline wait for child completion?
23. Does a schedule trigger prevent two runs from overlapping?
24. Which boundary convention do tumbling windows typically use?
25. Does a storage event trigger guarantee exactly-once processing?
26. What risk does retrying an append Copy after a partial write carry?
27. If Copy times out, are you guaranteed zero rows landed in the sink?
28. Why can setting `parallelCopies` too high slow down an OLTP source?
29. When is explicit column mapping needed?
30. How does a data freshness SLO differ from pipeline execution status?
31. Does a managed identity automatically grant `SELECT` on Azure SQL?
32. Why isn't a Git commit automatically live in production?
33. How should CI/CD pipelines coordinate with schema migrations?
34. What cost drivers exist beyond ADF orchestration itself?
35. How should a runbook handle failures occurring after apply but before watermark commit?

## 47. Summary

In **Azure Data Factory**, **Copy activity** handles moving data from source to sink through linked services, datasets, and an Integration Runtime. Yet system correctness depends on far more than counting copied rows.

**Incremental loads** must select the right changes using a **trustworthy watermark/checkpoint**: timestamps or IDs for simple cases, and **Change Tracking or CDC** when `UPDATE`/`DELETE` tracking and commit-based capture are needed. Data windows need clear boundaries handling timestamp ties and late commits; watermarks must update **only after data is safely applied and validated**.

**Pipeline orchestration** chains Lookup, Copy, validation, stored procedures, ForEach, Execute Pipeline, and triggers into workflows with explicit dependencies, retries, timeouts, concurrency, and observability. Across separate services lacking a shared distributed transaction, design for **at-least-once delivery and idempotent sinks** so reruns neither duplicate nor drop records.

In production, combine **managed identities/Key Vault, Azure IR or self-hosted IR, VNet/private networking, Azure SQL/ADLS, Azure Monitor, CI/CD, recovery runbooks, and Cost Management**. The ultimate measure of success is not a green Copy activity badge, but **complete, accurate, timely destination data that reruns safely at predictable cost**.

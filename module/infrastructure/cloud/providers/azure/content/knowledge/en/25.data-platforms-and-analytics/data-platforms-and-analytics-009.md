# Azure Data Explorer and Analyzing Logs or Telemetry with KQL

An e-commerce system running on **Azure App Service**, **Azure Container Apps**, **AKS**, **Azure SQL Database**, and **Azure Service Bus** can generate millions of events daily: HTTP requests, exceptions, job processing, error messages, SQL query traces, security events, and device metrics. When users report "the checkout page was slow at 09:15," the operations team must answer **which service slowed down, when it started, which deployment caused errors, which tenant or region was impacted, and what evidence confirms recovery**.

Reading logs manually across individual machines cannot handle that volume. **Azure Data Explorer (ADX)** is a large-scale analytics platform built for logs, telemetry, events, clickstream, and time-series data, enabling interactive queries via **Kusto Query Language (KQL)** across structured and semi-structured datasets.

This lesson belongs to the **Data Platforms and Analytics** chapter in the **CLOUD_PROVIDERS_AZURE** module. Within the Azure ecosystem—from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and databases—ADX adds the ability to **ingest, organize, query, and operate observability data** at scale. The focus is on **hands-on KQL for analyzing logs and telemetry**, alongside building ingestion pipelines, authorization, performance tuning, and cost governance. This lesson does not assume you already have a production cluster or production logs.

After this lesson, you will be able to:

- Distinguish **ADX/Kusto**, **Azure Monitor Logs/Log Analytics**, **Application Insights**, **Event Hubs**, **Azure SQL**, and other analytics platforms.
- Describe the **cluster → database → table → extents** architecture, ingestion flows, and query endpoints.
- Design a telemetry schema with **event time, operation, status, duration, trace ID, dimensions**, and `dynamic` fields.
- Write KQL using `where`, `project`, `extend`, `summarize`, `bin()`, `percentile()`, `dcount()`, `join`, `parse_json()`, `mv-expand`, and `make-series`.
- Analyze **HTTP 5xx/4xx, per-deployment errors, p95/p99 latency, traffic spikes, retries, and dependency failures**, tracing via correlation IDs.
- Optimize queries by filtering time early, projecting needed columns, controlling cardinality, choosing joins, materialized views, and caching appropriately.
- Protect data with **Microsoft Entra ID, RBAC/data-plane roles, row-level security**, private networking, and PII/retention governance.
- Build a KQL lab workflow using **inline synthetic data** without requiring access to a production tenant.
- Evaluate ingestion lag, reliability, monitoring, costs, and pick the right solution for the problem.

## 1. What Problem Does Azure Data Explorer Solve?

**ADX** (also known as **Kusto**) is a near-real-time analytics service for high-volume event data. It excels on **append-heavy** workloads: every request, log line, sensor reading, or business event appends a new record. The query engine is optimized for time filtering, grouping events, detecting anomaly patterns, and multi-dimensional aggregations.

### 1.1. Example from a Real Incident

The SRE team receives an alert:

~~~text
2026-11-20 09:15 UTC
Orders API p95 latency > 900 ms
HTTP 503 rate jumped from 0.2% to 8%
Deployment v42 rolled out minutes earlier
~~~

An investigation workflow can:

1. Filter telemetry to a **time window** around 09:15.
2. Chart requests/second and error rates by `Service` and `Region`.
3. Compare p95/p99 across `Deployment` before and after the release.
4. Filter `StatusCode >= 500` to pinpoint which `Operation` has high failure rates.
5. Use `TraceId` to correlate HTTP requests with database and dependency logs.
6. Inspect the latest records to confirm recovery after a rollback.

ADX executes these set-based analyses across massive record counts via KQL instead of reading individual logs manually.

### 1.2. When Is ADX a Good Fit?

| Need | Value ADX Delivers |
|---|---|
| Querying huge volumes of time-stamped logs/events | Column-oriented analytics, indexing/partitioning, and the Kusto query engine |
| Telemetry with flexible attributes | `dynamic` for JSON, paired with fixed columns for fast filtering and grouping |
| Near real-time visibility | Ingestion pipelines from Event Hubs/Blob/SDKs queried shortly after arrival |
| Incident investigation | `where`, `summarize`, `join`, time series, and correlation IDs |
| Analytics dashboards/alerts | KQL queries via UI, APIs, workbooks, Grafana, or BI integrations |
| Billions of long-lived events | Governed retention/caching policies and append storage scaled by capacity/compute |
| IoT/clickstream/cyber telemetry | Multi-dimensional aggregation and pattern discovery |

**ADX is not an OLTP database** for placing orders with row-level transactional updates. Nor does it automatically replace a **SIEM, alerting platform, or message broker**; each service owns distinct responsibilities.

### 1.3. Reference Data Flow

~~~mermaid
flowchart LR
    APPS[App Service / AKS / Container Apps] -->|Structured logs/events| HUB[Azure Event Hubs]
    IOT[IoT sensors] -->|Telemetry| HUB
    STORAGE[Blob Storage / Data Lake] -->|Files / Event Grid| ING[Ingestion service]
    HUB --> ING
    ING --> ADX[(Azure Data Explorer cluster)]
    ADX --> DB[(Database / Tables / Extents)]
    DB --> KQL[KQL queries]
    KQL --> SRE[SRE investigations]
    KQL --> DASH[Dashboards / reporting]
    KQL --> ALERT[Alerts / automation when configured]
    MON[Azure Monitor] -. Platform and pipeline metrics .-> ADX
~~~

Not every application must send logs **via Event Hubs**. Multiple ingestion paths exist; choosing one depends on throughput, data format, latency, replay, networking, and cost. **This pipeline is an illustrative model** for the lesson, not a live Azure resource.

## 2. ADX vs. Azure Monitor Logs, Application Insights, and Azure SQL

A common point of confusion: **Azure Monitor Logs also uses KQL**, yet **a Log Analytics workspace is not automatically your Azure Data Explorer database**. They share the Kusto query language foundation, but differ in scope, schemas, ingestion, permissions, and billing.

| Technology | Primary Role | When to Prefer |
|---|---|---|
| **Azure Data Explorer** | Large-scale event/log analytics store with team-governed schemas and ingestion | Custom telemetry analytics, controlled ingestion/queries, deep data exploration |
| **Azure Monitor Logs / Log Analytics** | Integrated Azure resource monitoring log platform with KQL queries and alert rules | Azure infrastructure/app monitoring, resource logs, operational alerting |
| **Application Insights** | Application Performance Monitoring (requests, dependencies, traces, exceptions) | Investigating app performance and distributed tracing |
| **Azure Event Hubs** | High-throughput event stream ingestion and buffering | Decoupling producers from consumers, temporary buffering; not a KQL analytics store |
| **Azure SQL Database** | OLTP transactions, relational constraints, per-record updates | System of record for orders, payments, and users |
| **Azure Data Lake / Blob** | Cost-effective file/object storage | Raw events, archives, export/replay, and downstream processing |
| **Microsoft Fabric Real-Time Intelligence** | Real-time analytics platform and Eventhouse/KQL in Fabric | Organizations using Fabric needing unified data/BI; check separate features/pricing |

### 2.1. Same Language, Not Identical Features

Some KQL operators work across both ADX and Azure Monitor Logs, for instance:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| summarize Requests=count() by bin(Timestamp, 5m)
~~~

Yet this query runs only when **table `ApiTelemetry` exists** in the target environment. In Log Analytics, you may query tables like `AppRequests`, `AppTraces`, or `AzureDiagnostics` with **different column names**. Management commands such as `.create table`, ingestion mappings, and ADX data retention policies do not apply directly to a Log Analytics workspace.

**Never copy a Log Analytics query using `TimeGenerated` and run it against an ADX custom table that only has `Timestamp`, expecting automatic translation.** Always inspect the schema first.

### 2.2. Quick Selection Rules

- To inspect built-in **Application Insights requests/dependencies/exceptions**, start in Azure Monitor/Application Insights before spinning up ADX.
- To govern **multi-source event pipelines**, custom schemas, retention, and flexible analytics over massive datasets, ADX fits well.
- For SQL transactions, foreign keys, isolation, and point updates, use an OLTP database.
- To buffer message streams with bounded replay, use Event Hubs/Service Bus per semantics; ADX is an **analytics store**, not a traditional queue worker.

Add ADX only when **analytical, retention, and performance benefits** outweigh ingestion + compute + storage + operational costs.

## 3. Kusto Architecture: Cluster, Database, Table, and Extents

An ADX deployment uses these building blocks:

~~~text
Azure subscription
└── Resource group
    └── Azure Data Explorer cluster: adx-observability-prod
        ├── Database: Telemetry
        │   ├── Table: ApiTelemetry
        │   ├── Table: DependencyTelemetry
        │   ├── Table: DeploymentEvents
        │   ├── Functions / Materialized views
        │   └── Ingestion mappings / retention / caching policies
        └── Database: SecurityEvents
            ├── Table: AuditEvents
            └── Table: AuthFailures
~~~

### 3.1. Concepts to Distinguish

| Concept | Meaning | What to Watch |
|---|---|---|
| **Cluster** | Kusto compute/engine exposing query and ingestion endpoints | SKU, scaling, networking, Azure RBAC/control plane |
| **Database** | Logical container for tables, functions, and policies | Data-plane roles, read/ingest/admin permissions |
| **Table** | Columnar records with an explicit schema | Data types, mappings, retention, and queries |
| **Extent** | Columnar storage shard, typically immutable in the ingestion architecture | Ingest batches, background merges/optimization, caching |
| **Ingestion mapping** | Maps JSON/CSV/Parquet fields to table columns | Schema evolution and ingestion failures |
| **Function** | Named, reusable query logic | Governance, permissions, version testing |
| **Materialized view** | Precomputed aggregation updated from a source table per policy | Lowers query cost; adds ingest/compute overhead |
| **Retention policy** | How long data remains before policy-driven purge | Compliance, storage cost, investigation window |
| **Caching policy** | How much recent data stays in fast engine cache | Recent-query speed vs. compute/cache cost |

### 3.2. Why Is ADX Strong at Time-Series Data?

ADX organizes data in columnar extents with rich metadata. When querying:

~~~kusto
ApiTelemetry
| where Timestamp between (ago(1h) .. now())
| where Service == "orders-api" and StatusCode >= 500
| project Timestamp, Operation, StatusCode, DurationMs, TraceId
~~~

The engine skips extents outside the time window and reads only projected columns rather than parsing raw JSON end-to-end. **Schema design, ingestion timing, data distribution, and query shape** affect pruning and scan efficiency; never claim every query runs in constant time regardless of dataset.

### 3.3. Query Endpoint and Ingestion Endpoint

For a standard ADX cluster, the query endpoint typically looks like:

~~~text
https://<cluster>.<region>.kusto.windows.net
~~~

The ingestion endpoint typically carries a prefix:

~~~text
https://ingest-<cluster>.<region>.kusto.windows.net
~~~

**These are illustrative patterns**, varying by Azure Data Explorer resource and deployment type. Read exact URIs from the Portal or resource properties—especially on free environments or integrated services. Never assume an ingestion URL supports every query SDK call or vice versa.

## 4. Schema Design for Logs and Telemetry

Query quality starts with a **log contract**. If an app logs plain text `Something failed` without timestamps, operations, status codes, or trace IDs, KQL can search text yet cannot reliably aggregate, compare, or trace.

### 4.1. What Should a Telemetry Record Contain?

~~~json
{
  "timestamp": "2026-11-20T09:15:14.221Z",
  "service": "orders-api",
  "environment": "prod",
  "operation": "GET /orders/{id}",
  "statusCode": 503,
  "durationMs": 946.4,
  "region": "southeastasia",
  "traceId": "trace-cc42",
  "spanId": "span-001",
  "severity": "Error",
  "properties": {
    "deployment": "v42",
    "dependency": "sql-orders",
    "errorCategory": "SqlTimeout"
  }
}
~~~

**The payload above is synthetic**, containing no real users or systems. Never store raw access tokens, passwords, session cookies, payment card data, or PII in logs just for query convenience.

### 4.2. Assumed ADX Schema for Examples

| Column | KQL Type | Meaning |
|---|---|---|
| `Timestamp` | `datetime` | **Event time** (UTC) emitted by the source |
| `Service` | `string` | Workload name such as `orders-api` |
| `Environment` | `string` | `prod`/`staging`/`dev` |
| `Operation` | `string` | HTTP route template or task type |
| `StatusCode` | `int` | HTTP status or standardized status code |
| `DurationMs` | `real` | Duration in milliseconds |
| `Region` | `string` | Azure region or logical location, not end-user location |
| `TraceId` | `string` | Correlation ID for request/distributed trace |
| `SpanId` | `string` | Span ID when tracing is enabled |
| `Severity` | `string` | `Info`, `Warning`, `Error` |
| `Properties` | `dynamic` | Additional JSON fields: deployment, dependency, error category |

Store `Timestamp` as a real **`datetime`** column—never store timestamps as strings and run `todatetime` across billions of rows. Standardize column names and values (e.g., `prod` vs. `production`) at ingestion. Keep frequently filtered/grouped fields as **typed top-level columns** instead of stuffing everything into dynamic JSON.

### 4.3. Event Time Differs from Ingestion Time

~~~text
Source event time:  09:15:14.221 UTC
Event Hubs enqueue: 09:15:14.310 UTC
ADX ingestion time: 09:15:20.800 UTC
Query time:         09:15:22.000 UTC
~~~

Events can arrive late due to batching, network delays, retries, or offline devices. **API latency analysis must use event time and `DurationMs`**, whereas **pipeline lag** compares event time against ingestion time. KQL `ingestion_time()` works only when ingestion-time policy/metadata is enabled and populated; otherwise it can return null. For strict observability, consider recording `ReceivedAtUtc` or pipeline ingest metadata explicitly.

### 4.4. Cardinality and Information Security

**High cardinality** means huge numbers of distinct values: `orderId`, `requestId`, `userId`. It is vital for tracing a single request, yet terrible for dashboard tables grouped by every ID (producing massive result sets). Instead:

- Aggregate by `Service`, `Region`, `Operation`, `StatusCode`, and `Deployment` first.
- Use `TraceId` strictly to drill down during investigations.
- Redact or hash identifiers where permitted and required—never treat hashing as guaranteed irreversible anonymization.
- Never log raw URL paths containing user IDs or PII when a **route template** works.
- Set retention by data class; audit logs differ from debug traces.

**Schema goal:** enable accurate analytics without accidentally turning your log platform into an ungoverned store of personal data.

## 5. Ingestion: Getting Logs and Events into Azure Data Explorer

KQL can only answer questions over **data ingested with an accurate schema**. An ingestion pipeline must define **sources, formats, transport, mappings, retries, checkpoints, duplicate handling, validation, retention**, and lag monitoring.

### 5.1. Common Data Sources

| Source | Typical Integration Path | When to Use |
|---|---|---|
| **Azure Event Hubs** | ADX data connection reading stream from a consumer group | Continuous request/event streams needing buffering and low latency |
| **Azure Blob Storage / ADLS** | Queued ingest, Event Grid data connection, or ingestion SDK | NDJSON/CSV/Parquet files, historical backfills |
| **Application/ETL SDK** | Ingestion SDK/API with batching | Pre-standardized data or custom integrations |
| **Kafka / connectors** | Kafka Connect or compatible bridges | Existing Kafka streaming pipelines |
| **Azure IoT Hub** | Service/feature-backed data connection | IoT telemetry routed into Azure |
| **Monitoring systems** | Supported export or streaming pipelines | Centralized analytics over authorized exported data |

**Do not assume Azure Monitor or Application Insights logs flow into ADX automatically.** You must configure exports, streaming, or ingestion pipelines explicitly if copying data. That creates **new costs and data copies**, requiring access and retention controls.

### 5.2. Streaming Ingestion vs. Queued Ingestion

| Property | Queued Ingestion | Streaming Ingestion |
|---|---|---|
| Goal | High throughput, batch/cost efficiency | Low end-to-end arrival latency |
| Processing | Batches events into extents via pipeline | Exposes newly arrived records faster via service mechanisms |
| Cost/compute | Best fit for most high-volume ingest workloads | Incurs overhead and feature restrictions |
| Best suited for | 100 GB logs/day without sub-second query needs | Near-real-time operational telemetry |
| Risks | Ingestion lag climbs during backlogs | Should not be toggled blindly for unsuitable event sizes/volumes |

**"Near real time" does not mean zero lag or exactly-once delivery.** End-to-end latency spans producer, Event Hubs, connector, ingestion batching, and KQL query execution. Measure real **ingestion lag** per source.

### 5.3. Event Hubs → ADX Pipeline

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant EH as Azure Event Hubs
    participant CONN as ADX Data Connection
    participant T as ADX ApiTelemetry
    participant SRE as KQL Analyst
    API->>EH: Publish JSON event with event time and trace ID
    EH-->>CONN: Read batch from consumer group / partition
    CONN->>T: Apply ingestion mapping and ingest
    T-->>CONN: Ingestion status / checkpoint workflow
    SRE->>T: Query recent window
    T-->>SRE: Aggregated results
~~~

Implementation checklist:

1. **Event Hub namespace/topic and partition capacity** sized for throughput.
2. Dedicated **consumer group for the ADX connector** to isolate it from other consumers.
3. Permissions to read Event Hubs and ingest into ADX, preferring managed identities where supported.
4. Correct **target database/table, data format, and ingestion mapping**.
5. Observability for bad records, mapping failures, and ingestion lag.
6. Event Hubs retention long enough to cover outages/backfills per plan—not permanent storage.
7. Handling **at-least-once/duplicate events** by key when exact business counts are required.

If a producer retries and sends each event 10 times, ADX cannot identify duplicates without an `EventId` or deduplication logic. `count()` will count all duplicates; decide whether to deduplicate pre-ingest or at query time.

### 5.4. Table and JSON Ingestion Mapping (Reference)

In an **authorized ADX database**, create a table with a Kusto management command:

~~~kusto
// Administrative command: run only in an authorized lab database.
.create table ApiTelemetry (
    Timestamp: datetime,
    Service: string,
    Environment: string,
    Operation: string,
    StatusCode: int,
    DurationMs: real,
    Region: string,
    TraceId: string,
    SpanId: string,
    Severity: string,
    Properties: dynamic
)
~~~

Illustrative **JSON ingestion mapping**:

~~~kusto
// Maps JSON source paths to table columns.
.create table ApiTelemetry ingestion json mapping 'ApiTelemetryJson'
'[
  {"column":"Timestamp","path":"$.timestamp","datatype":"datetime"},
  {"column":"Service","path":"$.service","datatype":"string"},
  {"column":"Environment","path":"$.environment","datatype":"string"},
  {"column":"Operation","path":"$.operation","datatype":"string"},
  {"column":"StatusCode","path":"$.statusCode","datatype":"int"},
  {"column":"DurationMs","path":"$.durationMs","datatype":"real"},
  {"column":"Region","path":"$.region","datatype":"string"},
  {"column":"TraceId","path":"$.traceId","datatype":"string"},
  {"column":"SpanId","path":"$.spanId","datatype":"string"},
  {"column":"Severity","path":"$.severity","datatype":"string"},
  {"column":"Properties","path":"$.properties","datatype":"dynamic"}
]'
~~~

**Important:**

- Commands starting with a dot (`.create`, `.show`, `.alter`) are **management commands**, not regular KQL queries. They require database/table admin permissions.
- Never run `.create` on a production database without change approval; a self-contained **lab `datatable` exercise requiring no table creation** appears later.
- Mappings must match real JSON payloads. Missing or mistyped JSON fields can produce nulls or ingestion failures depending on the pipeline; test schema changes.
- Event data should be formatted as NDJSON/stream records per supported ingestion format rather than one huge JSON array assuming connectors split it automatically.
- Mapping references and data connection permissions are also required for live ingestion; creating a table alone does not ingest data.

### 5.5. Ingestion-Time Validation and Dead-Letter Strategy

If a producer emits:

~~~json
{
  "timestamp": "not-a-date",
  "service": "orders-api",
  "durationMs": "very slow"
}
~~~

mapping into `datetime` and `real` will fail or null out fields. Systems should:

- Validate payloads/schemas at the producer or ingestion tier.
- Include `schemaVersion` for compatible rollouts.
- Track **ingestion failures** via monitoring and connector statuses.
- Retain raw events safely in Event Hubs/Blob under appropriate retention for replay.
- Maintain runbooks for fixing mappings, backfilling, and isolating poison records.
- Never let a bad batch silently drop an entire day of telemetry without alerts.

ADX does not automatically create a dedicated "dead-letter queue" for every ingestion source; error reporting and quarantine depend on the ingestion mechanism and must be designed explicitly.

### 5.6. Ingestion Time, Idempotency, and Ordering

ADX excels at **append-only** event data. Due to network retries or replays, events may:

- Arrive late relative to `Timestamp`.
- Arrive out of order.
- Be delivered more than once.
- Carry multiple versions of the same logical event.

When deduplicating:

~~~kusto
// Illustrative only when schema includes EventId and ReceivedAtUtc.
ApiTelemetry
| where Timestamp > ago(1d)
| summarize arg_max(ReceivedAtUtc, *) by EventId
~~~

**Do not copy this query onto tables lacking `EventId`/`ReceivedAtUtc`.** It also selects the latest record **among rows present at query time**, rather than guaranteeing exactly-once ingestion. To protect revenue or transactions, authoritative uniqueness must reside in the transactional system.

## 6. KQL Fundamentals: Pipeline-Style Querying

**Kusto Query Language** chains expressions as **`Table | operator | operator | ...`**. Each operator consumes the preceding output, filters/transforms/groups it, and passes results to the next stage. KQL differs from SQL in syntax and flow-oriented thinking, even though both share tables and aggregates.

### 6.1. A Simple Query

~~~kusto
ApiTelemetry
| where Timestamp > ago(30m)
| where Environment == "prod"
| project Timestamp, Service, Operation, StatusCode, DurationMs
| order by Timestamp desc
| take 100
~~~

Reading top to bottom:

1. Take records from `ApiTelemetry`.
2. Keep events from the **last 30 minutes**.
3. Keep only production environment records.
4. Project only five relevant columns.
5. Sort newest first.
6. Return 100 rows.

KQL is **case-sensitive** for table and column names; `Timestamp` differs from `timestamp` if the schema defines one over the other. The string operator `==` is case-sensitive; `=~` performs case-insensitive comparisons per Kusto semantics.

### 6.2. Core Operators

| Operator | Purpose | Example |
|---|---|---|
| `where` | Filter rows | `where StatusCode >= 500` |
| `project` | Select/rename columns | `project Timestamp, DurationMs` |
| `extend` | Add calculated columns | `extend IsError = StatusCode >= 500` |
| `summarize` | Group and aggregate | `summarize Events=count() by Service` |
| `order by` / `sort by` | Sort rows | `order by DurationMs desc` |
| `top` | Return top N rows by criteria | `top 10 by DurationMs desc` |
| `take` / `limit` | Return N arbitrary rows (no ordering guarantee without sort) | `take 20` |
| `distinct` | Unique values/combinations | `distinct Service, Region` |
| `join` | Combine tables by key | `join kind=leftouter ... on TraceId` |
| `union` | Combine rows across compatible tables | `union ApiTelemetry, DependencyTelemetry` |
| `mv-expand` | Expand dynamic array/bag elements into rows | `mv-expand ErrorTags` |
| `render` | Visualize output as a chart in supported UIs | `render timechart` |

### 6.3. Scalar Syntax and Data Types

~~~kusto
print
    QueryTime = now(),
    WindowStart = ago(1h),
    Threshold = 500,
    Success = true,
    Ratio = 1.5,
    Region = "southeastasia",
    Tags = dynamic({"env":"prod","service":"orders-api"})
~~~

Common types include `bool`, `int`, `long`, `real`, `decimal`, `string`, `datetime`, `timespan`, `dynamic`, and `guid`. Standardize timestamps in **UTC** rather than mixing local times in logs and misreporting incident timings.

### 6.4. KQL `let` and Semicolons

`let` binds a name to an expression or query fragment within **the scope of a single query**:

~~~kusto
let Window = 1h;
let TargetEnvironment = "prod";
ApiTelemetry
| where Timestamp > ago(Window)
| where Environment == TargetEnvironment
| summarize Events=count() by Service
~~~

`let` statements end with semicolons (`;`). A `let` in one query tab **does not persist** into another tab or separate SDK calls; for long-lived reuse, use **stored functions** or query templates.

### 6.5. `has` vs. `contains`

~~~kusto
// When filtering message text (assuming table has Message:string):
ApiTelemetry
| where Timestamp > ago(1h)
| where tostring(Properties.errorMessage) has "timeout"
~~~

`has` matches indexed **terms/tokens** per Kusto tokenization, usually running much faster than `contains` when searching whole words. `contains` searches **substrings** (including inside longer words), useful yet scanning more broadly. Case-sensitive variants `has_cs` and `contains_cs` are also available.

**Example:** `has "error"` may not match `errorsomething`; `contains "error"` matches the substring. Pick operators by semantics first, then optimize.

## 7. First KQL Lab: Inline Synthetic Data, No Production Cluster Needed

Learners can open the Kusto query editor in the **Azure Data Explorer Web UI** or an authorized KQL playground and paste a `datatable` containing synthetic events. This example is **self-contained**, touching no production tables and persisting no data.

### 7.1. Sample Dataset

~~~kusto
let Demo = datatable(
    Timestamp:datetime, Service:string, Environment:string,
    Operation:string, StatusCode:int, DurationMs:real,
    Region:string, TraceId:string, Properties:dynamic)
[
    datetime(2026-11-20T09:00:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  82.0, "southeastasia", "tr-001", dynamic({"deployment":"v41","dependency":"sql"}),
    datetime(2026-11-20T09:01:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  75.0, "southeastasia", "tr-002", dynamic({"deployment":"v41","dependency":"sql"}),
    datetime(2026-11-20T09:02:00Z), "orders-api", "prod", "POST /orders",      201, 180.0, "southeastasia", "tr-003", dynamic({"deployment":"v41","dependency":"sql"}),
    datetime(2026-11-20T09:10:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  95.0, "southeastasia", "tr-004", dynamic({"deployment":"v42","dependency":"sql"}),
    datetime(2026-11-20T09:11:00Z), "orders-api", "prod", "GET /orders/{id}", 503, 950.0, "southeastasia", "tr-005", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:12:00Z), "orders-api", "prod", "POST /orders",      500, 820.0, "southeastasia", "tr-006", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:13:00Z), "orders-api", "prod", "GET /orders/{id}", 503, 991.0, "southeastasia", "tr-007", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:14:00Z), "orders-api", "prod", "GET /orders/{id}", 429,  18.0, "southeastasia", "tr-008", dynamic({"deployment":"v42","errorCategory":"RateLimit"}),
    datetime(2026-11-20T09:15:00Z), "orders-api", "prod", "GET /orders/{id}", 200,  91.0, "eastasia",      "tr-009", dynamic({"deployment":"v42","dependency":"sql"}),
    datetime(2026-11-20T09:16:00Z), "orders-api", "prod", "GET /orders/{id}", 503, 978.0, "southeastasia", "tr-010", dynamic({"deployment":"v42","errorCategory":"SqlTimeout"}),
    datetime(2026-11-20T09:17:00Z), "catalog-api","prod", "GET /products",    200,  37.0, "southeastasia", "tr-011", dynamic({"deployment":"v13","dependency":"redis"}),
    datetime(2026-11-20T09:18:00Z), "catalog-api","prod", "GET /products",    200,  41.0, "southeastasia", "tr-012", dynamic({"deployment":"v13","dependency":"redis"}),
    datetime(2026-11-20T09:19:00Z), "orders-api", "staging", "POST /orders",    500, 500.0, "southeastasia", "tr-013", dynamic({"deployment":"v42-test","errorCategory":"TestFault"})
];
Demo
| where Environment == "prod"
| project Timestamp, Service, Operation, StatusCode, DurationMs, Region
| order by Timestamp asc
~~~

The dataset holds **13 synthetic records**, including one **staging** event to test environment filtering. It intentionally simulates deployment `v42` triggering SQL errors in `southeastasia`. Do not compare numbers from this tiny table against production SLOs; percentiles on tiny samples merely illustrate syntax.

### 7.2. Self-Contained Aggregation Query

~~~kusto
let Demo = datatable(Service:string, StatusCode:int, DurationMs:real)
[
  "orders-api", 200, 82.0,
  "orders-api", 503, 950.0,
  "orders-api", 500, 820.0,
  "orders-api", 429, 18.0,
  "catalog-api", 200, 37.0,
  "catalog-api", 200, 41.0
];
Demo
| summarize
    Requests = count(),
    ServerErrors = countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms = percentile(DurationMs, 95)
  by Service
| extend ServerErrorRatePct = round(100.0 * ServerErrors / Requests, 2)
| order by ServerErrorRatePct desc
~~~

**Expected output:** `orders-api` has 4 requests, 2 HTTP 5xx → **50% server error rate**; `catalog-api` has 2 requests, 0 HTTP 5xx → **0%**. `429` is client throttling and is **not** counted as HTTP 5xx. Kusto computes percentiles using its estimation algorithms; never extrapolate production latency percentiles from 6 sample rows.

### 7.3. Key Difference: Fixed Dates vs. `ago()`

The dataset above uses **2026-11-20**. If you practice on a much later date, adding:

~~~kusto
| where Timestamp > ago(1h)
~~~

will return **0 rows**—not because KQL or ADX is broken. For fixed historical lab datasets, use `between (datetime(...) .. datetime(...))`; for live telemetry, use `ago(1h)`.

### 7.4. Safe Lab Practice

`datatable` exists only for the duration of one query. Never grant create-table, ingest, or delete permissions just to run this exercise. When using a Free cluster or organizational lab environment, respect quotas and terms, and never paste real user data into examples.

## 8. Filtering Logs by Time, Service, and Text in KQL

On large log tables, **filtering by time early** is one of the highest-impact performance optimizations. Never scan years of telemetry just to filter down to the last minute during aggregation.

**Convention for subsequent queries:** assume table `ApiTelemetry` is populated with the schema from Section 4.2. These queries are **templates for a prepared ADX table**, not runnable directly where no table exists. When practicing without ADX, replace `ApiTelemetry` with `Demo` after declaring `let Demo=datatable(...)` inside the **same query**.

### 8.1. Relative Time Ranges

~~~kusto
ApiTelemetry
| where Timestamp >= ago(1h) and Timestamp < now()
| where Environment == "prod"
| project Timestamp, Service, StatusCode, DurationMs
| order by Timestamp desc
~~~

`ago(1h)` is relative to query execution time, not a fixed "incident start time." When investigating a historical incident, specify **absolute UTC start/end bounds**:

~~~kusto
let StartUtc = datetime(2026-11-20T09:00:00Z);
let EndUtc = datetime(2026-11-20T10:00:00Z);
ApiTelemetry
| where Timestamp between (StartUtc .. EndUtc)
| where Service == "orders-api"
| order by Timestamp asc
~~~

**Nuance:** `between` is inclusive on both ends per KQL semantics; across adjacent time windows, avoid double-counting boundary events by writing **`Timestamp >= StartUtc and Timestamp < EndUtc`**.

### 8.2. Filtering Multiple Services or Statuses

~~~kusto
ApiTelemetry
| where Timestamp >= ago(6h)
| where Environment == "prod"
| where Service in ("orders-api", "payments-api", "catalog-api")
| where StatusCode >= 500 and StatusCode < 600
| project Timestamp, Service, Operation, StatusCode, TraceId
~~~

`in` is case-sensitive for strings; `in~` performs case-insensitive comparisons in Kusto. With standardized telemetry, **enforce one canonical naming convention** rather than compensating for messy data in queries.

### 8.3. Filtering Text Inside `dynamic`

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| where Service == "orders-api"
| extend ErrorCategory = tostring(Properties.errorCategory)
| where ErrorCategory has "Timeout"
| project Timestamp, Operation, StatusCode, ErrorCategory, TraceId
~~~

If `errorCategory` is logged as `SqlTimeout`, `has "Timeout"` **may not match as expected** because `has` matches tokenized terms; for CamelCase error codes, prefer **exact matching**:

~~~kusto
| where ErrorCategory == "SqlTimeout"
~~~

or use substring matching during exploration:

~~~kusto
| where ErrorCategory contains "Timeout"
~~~

**Choose operators by semantics.** `has` leverages term indexes efficiently; `contains` scans more broadly yet matches arbitrary substrings.

### 8.4. Filtering Errors Separately from All 4xx

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| extend IsServerError = StatusCode between (500 .. 599),
         IsClientError = StatusCode between (400 .. 499)
| summarize
    Requests=count(),
    ServerErrors=countif(IsServerError),
    ClientErrors=countif(IsClientError)
  by Service
~~~

**HTTP 401/403/404/429** can reflect proper security enforcement or client bugs rather than server availability outages like 5xx. Still, a spike in 429s degrades user experience; track **throttled rate** separately. For non-HTTP workloads, normalize `StatusCode`/`Success` cleanly rather than forcing every failure into status 500.

## 9. Aggregations: Requests, Error Rates, and p95/p99 Latency

`summarize` is the centerpiece of telemetry analytics. It groups records across dimensions, computes aggregates, and returns compact summaries for trend analysis.

### 9.1. Requests in 5-Minute Buckets

~~~kusto
ApiTelemetry
| where Timestamp > ago(24h)
| where Environment == "prod"
| summarize Requests=count() by Service, bin(Timestamp, 5m)
| order by Timestamp asc, Service asc
| render timechart
~~~

**`bin(Timestamp, 5m)` floors timestamps into 5-minute buckets** rather than altering raw events arbitrarily. In Kusto UIs supporting `render timechart`, this renders one time series per service; SDKs and automation read the tabular output without rendering charts.

### 9.2. Error Rate by Service and Region

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Environment == "prod"
| summarize
    Requests = count(),
    Http5xx = countif(StatusCode >= 500 and StatusCode < 600),
    Http429 = countif(StatusCode == 429)
  by Service, Region, bin(Timestamp, 5m)
| extend
    ErrorRatePct = round(100.0 * todouble(Http5xx) / Requests, 2),
    ThrottledRatePct = round(100.0 * todouble(Http429) / Requests, 2)
| order by Timestamp asc, ErrorRatePct desc
~~~

Because `summarize` emits buckets only when records exist, intervals with zero traffic disappear; to plot **empty intervals as 0**, use `make-series` in the time-series section. Remember `Requests` counts ingested events; if ingestion lags or sampling is active, it does not necessarily equal total real traffic.

### 9.3. Latency Percentiles

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Environment == "prod"
| where DurationMs >= 0
| summarize
    Requests = count(),
    AverageMs = round(avg(DurationMs), 1),
    P50Ms = round(percentile(DurationMs, 50), 1),
    P95Ms = round(percentile(DurationMs, 95), 1),
    P99Ms = round(percentile(DurationMs, 99), 1),
    MaxMs = max(DurationMs)
  by Service, Operation
| top 20 by P95Ms desc
~~~

**Why track p95/p99?** If 95% of requests are fast while 5% are very slow, **averages** hide tail latency pain. Percentiles in distributed engines can be **approximate**, especially across small buckets. Never sum or average pre-aggregated p95 values to compute an overall p95; compute percentiles over raw distributions or use mergeable digest structures.

### 9.4. SLOs and Minimum Sample Size

Suppose an internal SLO defines:

~~~text
Successful authorized GET /orders/{id}:
  p95 latency < 500 ms per 5-minute window
  availability target >= 99.9%
~~~

Query:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| where Environment == "prod"
| where Service == "orders-api"
| where Operation == "GET /orders/{id}"
| summarize
    Samples = count(),
    P95Ms = percentile(DurationMs, 95),
    Http5xx = countif(StatusCode >= 500 and StatusCode < 600)
  by bin(Timestamp, 5m)
| extend
    ErrorRatePct = round(100.0 * Http5xx / Samples, 3),
    LatencySloMiss = P95Ms >= 500,
    AvailabilitySloMiss = ErrorRatePct > 0.1
| where Samples >= 100
| order by Timestamp asc
~~~

**This is only an SLO example**, not an SLA of Azure Data Explorer or Orders API. Define **eligible requests**, excluded client errors, maintenance windows, and sampling rates. Filtering `Samples >= 100` avoids noisy alerts on tiny buckets, yet could miss a total outage where traffic drops to zero—pair with synthetic health/availability probes.

### 9.5. Distinct Users/Clients and Cardinality

Suppose your app logs a standardized, approved `ClientId`:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| summarize
    Requests=count(),
    UniqueClients=dcount(ClientId)
  by Service
~~~

**Run only if the table has `ClientId`.** `dcount()` is an **approximate distinct count**, suited for large-scale analytics; never use it where exact unique transaction counts are legally required. For smaller datasets needing exact counts, use `count_distinct()` within system limits; for personal identifiers, prefer policy-approved pseudonymous or hashed IDs.

## 10. Incident Investigation: Which Service Caused the HTTP 5xx Spike?

We want to answer "which service and release triggered the errors?" rather than just "backend returned 500."

### 10.1. Top Failing Operations

~~~kusto
let WindowStart = datetime(2026-11-20T09:00:00Z);
let WindowEnd = datetime(2026-11-20T09:30:00Z);
ApiTelemetry
| where Timestamp >= WindowStart and Timestamp < WindowEnd
| where Environment == "prod"
| summarize
    TotalRequests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs, 95)
  by Service, Operation, Region
| extend ErrorRatePct=round(100.0 * todouble(Http5xx) / TotalRequests, 2)
| where TotalRequests >= 50
| top 15 by Http5xx desc
~~~

**Do not sort solely by error rate**: an operation with 1 failure out of 1 request hits 100%, yet impacts far fewer users than an operation with 5,000 failures out of 100,000 requests. Weigh **volume, rate, business criticality, and baselines**.

### 10.2. Comparing Before and After a Deployment

`Deployment` resides inside `Properties`:

~~~kusto
ApiTelemetry
| where Timestamp > ago(6h)
| where Environment == "prod"
| extend Deployment=tostring(Properties.deployment)
| where isnotempty(Deployment)
| summarize
    Requests=count(),
    Error5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs, 95)
  by Service, Deployment, Region
| extend ErrorPct=round(100.0 * Error5xx / Requests, 2)
| order by Service asc, Deployment asc
~~~

**Interpretation risk:** `v41` and `v42` might serve different regions or tenants; differing error rates alone do not prove **causality**. Compare time windows, traffic mix, service regions, dependencies, and deployment timestamps—or use canary/control cohorts.

### 10.3. Grouping Error Categories

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Service == "orders-api"
| where StatusCode >= 500 and StatusCode < 600
| extend ErrorCategory=tostring(Properties.errorCategory)
| summarize
    Errors=count(),
    LastSeen=max(Timestamp)
  by ErrorCategory, Region
| top 20 by Errors desc
~~~

To prevent uncategorized errors from collapsing silently into blanks:

~~~kusto
| extend ErrorCategory = iff(
    isempty(tostring(Properties.errorCategory)),
    "Unclassified",
    tostring(Properties.errorCategory))
~~~

This standalone `extend` block is a **pipeline snippet**, not a complete query on its own.

### 10.4. Analyzing Retries During an Incident

If the log schema includes `RequestId`, `Attempt`, and `Success`:

~~~kusto
// Pattern: use only after ingesting these exact 3 columns.
ApiTelemetry
| where Timestamp > ago(1h)
| summarize
    Attempts=count(),
    AnySuccess=countif(Success == true),
    LastSeen=max(Timestamp)
  by RequestId
| where Attempts > 1
| top 20 by Attempts desc
~~~

Seeing the same ID multiple times is not always a bug: it could represent **multiple trace spans** or legitimate retries. Know your event contract—is one row a request, a span, or a log line? Never deduplicate solely on `TraceId` when an investigation needs every span.

### 10.5. Plotting HTTP 5xx and 429 Together

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Service == "orders-api" and Environment == "prod"
| summarize
    Http5xx=countif(StatusCode between (500 .. 599)),
    Http429=countif(StatusCode == 429)
  by bin(Timestamp, 1m)
| order by Timestamp asc
| render timechart
~~~

If 429s climb before 5xxs, the service may have hit rate limits and triggered downstream retry storms; still, verify against rate-limit policies, load, and logs. **Correlation alone does not prove causality.**

## 11. KQL `dynamic`: JSON, Arrays, and Flexible Fields

Logs frequently carry service-specific attributes, such as:

~~~json
{
  "deployment": "v42",
  "dependency": "sql-orders",
  "tags": ["checkout", "priority"],
  "error": {
    "category": "SqlTimeout",
    "code": "DB_CONN_TIMEOUT"
  }
}
~~~

ADX provides the `dynamic` type for JSON-like structures. **Cast extracted values to explicit scalar types** before comparing or grouping.

### 11.1. Accessing Dynamic Fields

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| extend
    Deployment = tostring(Properties.deployment),
    Dependency = tostring(Properties.dependency),
    ErrorCategory = tostring(Properties.error.category)
| project Timestamp, Service, Deployment, Dependency, ErrorCategory, TraceId
~~~

Records lacking `Properties.error.category` yield empty/null values when cast; never assume every event carries all nested attributes. **Never dump every critical column into `dynamic` just to avoid schema management.**

### 11.2. When JSON Arrives as a String

If a pipeline ingests raw JSON into a string column `RawPayload:string`:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| extend Payload = parse_json(RawPayload)
| extend Deployment = tostring(Payload.deployment)
| summarize Events=count() by Deployment
~~~

**Run only if the schema has `RawPayload`.** When `Properties` is already `dynamic`, access `Properties.deployment` directly without calling `parse_json(Properties)`. Nested JSON strings inside fields require explicit layered parsing.

### 11.3. `mv-expand` Multiplies Row Counts

Illustrated with inline synthetic data:

~~~kusto
let Demo = datatable(
    TraceId:string, Tags:dynamic)
[
    "tr-001", dynamic(["checkout","priority"]),
    "tr-002", dynamic(["catalog"]),
    "tr-003", dynamic(["checkout","retry","sql"])
];
Demo
| mv-expand Tag=Tags to typeof(string)
| summarize Traces=dcount(TraceId) by Tag
| order by Traces desc
~~~

`mv-expand` turns every array element into a separate row; expanding 1,000 tags across 1 million events explodes intermediate memory. **Filter by time/service before expanding**, limit cardinality, or aggregate differently where appropriate.

### 11.4. `bag_unpack` and Flexible Schemas

ADX offers the `bag_unpack` plugin to unpack `dynamic` object keys into columns:

~~~kusto
// Illustrative only; Properties must contain matching object keys.
ApiTelemetry
| where Timestamp > ago(10m)
| evaluate bag_unpack(Properties)
| take 20
~~~

Unpacking all keys across heterogeneous schemas can spawn vast column counts and overhead. In production queries, prefer **extracting only needed fields** or defining explicit output schemas and column naming controls when using the plugin.

### 11.5. JSON Does Not Override Data Permissions

If `Properties` inadvertently captures `email`, `token`, or request bodies, KQL exposes them to anyone with table read access. **Never ingest unnecessary sensitive data** simply because `dynamic` accepts arbitrary JSON. Apply field-level redaction at producer/ingestion alongside roles and retention.

## 12. `join`, `lookup`, and Tracing a Request Across Services

A single HTTP request can trigger multiple dependency calls: Azure SQL queries, Redis lookups, Service Bus publishes, and downstream HTTP calls. Looking only at the API request table shows latency without revealing **which dependency** stalled.

### 12.1. Standardizing Distributed Traces

When apps emit OpenTelemetry / W3C Trace Context, records carry:

~~~text
TraceId:       trace-cc42
Request span:  span-api-001
Child span 1:  span-sql-001
Child span 2:  span-redis-001
Deployment:    v42
~~~

`TraceId` groups **one trace**, while `SpanId` and `ParentSpanId` (when present) capture parent–child relationships. Having **multiple rows per trace** is normal; **never** deduplicate all logs by `TraceId` leaving a single row.

### 12.2. Assumed Dependency Table

For illustration, assume a `DependencyTelemetry` table:

| Column | Type | Contents |
|---|---|---|
| `Timestamp` | `datetime` | Event time |
| `TraceId` | `string` | Trace ID propagated from request |
| `Target` | `string` | `sql-orders`, `redis-catalog`, `payments-api` |
| `DurationMs` | `real` | Dependency latency |
| `Success` | `bool` | Whether dependency call succeeded |
| `Region` | `string` | Region |

**This schema is illustrative**, not pre-created in every ADX cluster. Create corresponding ingestion mappings or adapt queries to your real tables.

### 12.3. Joining Requests with Dependencies

~~~kusto
let WindowStart = ago(1h);
let Requests =
    ApiTelemetry
    | where Timestamp > WindowStart
    | where Service == "orders-api"
    | project
        TraceId,
        RequestTime = Timestamp,
        RequestStatus = StatusCode,
        RequestMs = DurationMs,
        Operation;
let DepPerTrace =
    DependencyTelemetry
    | where Timestamp > WindowStart
    | summarize
        DependencyCalls = count(),
        FailedDependencies = countif(Success == false),
        SlowestDependencyMs = max(DurationMs),
        DependencyTargets = make_set(Target, 20)
      by TraceId;
Requests
| join kind=leftouter (DepPerTrace) on TraceId
| project RequestTime, TraceId, Operation, RequestStatus,
          RequestMs, DependencyCalls, FailedDependencies,
          SlowestDependencyMs, DependencyTargets
| top 20 by RequestMs desc
~~~

**Why aggregate dependencies before `join`?** One request can make 20 dependency calls; a raw join turns **one request into 20 rows**. Subsequent `count()` calls would count that request 20 times. Summarizing by `TraceId` first preserves one row per trace **assuming the request table holds one root event per trace**.

In complex distributed traces, **multiple root/request spans may share one trace**. In that case, join on a finer key such as `TraceId + SpanId` or filter specifically to root request spans before joining. Never assume `TraceId` is globally 1:1 with every HTTP request.

### 12.4. `lookup` for Small Dimension Tables

Suppose you enrich team names from a small dimension table:

~~~kusto
let Teams = datatable(Service:string, OwnerTeam:string)
[
  "orders-api", "Commerce",
  "catalog-api", "Catalog",
  "payments-api", "Payments"
];
ApiTelemetry
| where Timestamp > ago(1h)
| summarize Errors=countif(StatusCode >= 500) by Service
| lookup kind=leftouter Teams on Service
| project Service, OwnerTeam, Errors
~~~

`lookup` fits when one side is a **small dimension table**, not billions of rows. If the team table contains duplicate `Service` keys, `lookup` multiplies rows—validate uniqueness and test. When both sides are large, evaluate `join` strategies and query plans.

### 12.5. Inspecting Call Graphs from Logs

If schemas carry `ParentSpanId` and `SpanId`, trace spans within a trace:

~~~kusto
// Use only when the table includes ParentSpanId / SpanId.
let TraceEvents =
    ApiTelemetry
    | where Timestamp > ago(1d)
    | where TraceId == "trace-cc42"
    | project TraceId, SpanId, ParentSpanId, Service, Timestamp, DurationMs;
TraceEvents
| order by Timestamp asc
~~~

To render a full **trace tree**, reconstruct the parent-child graph or use dedicated distributed tracing tools. `order by Timestamp` orders events chronologically without drawing causal hierarchy automatically.

### 12.6. `union` Across Multiple Tables

~~~kusto
union withsource=SourceTable ApiTelemetry, DependencyTelemetry
| where Timestamp > ago(30m)
| project SourceTable, Timestamp, TraceId, Service, Target
| take 100
~~~

`union` across tables with differing schemas leaves missing columns null on non-matching rows. Seeing nulls in `Service` or `Target` is expected. Use `union` to **merge timelines**, never as a substitute for key-based `join`s.

## 13. Time Series, Spikes, and Anomaly Detection with KQL

To monitor requests/second, you need evenly spaced time buckets. `make-series` builds **numeric arrays over regular time bins**, unlocking Kusto's time-series functions.

### 13.1. Building Uniform Time Series

~~~kusto
let StartUtc = ago(24h);
let EndUtc = now();
ApiTelemetry
| where Timestamp >= StartUtc and Timestamp < EndUtc
| where Environment == "prod"
| make-series Requests=count() default=0
    on Timestamp from StartUtc to EndUtc step 5m
    by Service
| render timechart
~~~

**Caveat on `default=0`:** "zero events in a bucket" does not necessarily mean **zero HTTP traffic**. It could reflect an ingestion outage, Event Hubs disconnect, sampling, or pipeline delay. Correlate with ingestion health and synthetic probes before declaring zero traffic.

### 13.2. Detecting Anomalies

KQL offers time-series functions including `series_decompose_anomalies()`:

~~~kusto
let StartUtc = ago(7d);
let EndUtc = now();
ApiTelemetry
| where Timestamp >= StartUtc and Timestamp < EndUtc
| where Environment == "prod"
| where Service == "orders-api"
| make-series Requests=count() default=0
    on Timestamp from StartUtc to EndUtc step 10m
| extend (AnomalyFlags, Scores, Baseline) =
    series_decompose_anomalies(Requests, 1.5)
| mv-expand
    Timestamp to typeof(datetime),
    Requests to typeof(long),
    AnomalyFlags to typeof(long),
    Scores to typeof(real),
    Baseline to typeof(real)
| where AnomalyFlags != 0
| project Timestamp, Requests, Baseline, Scores, AnomalyFlags
| order by Timestamp asc
~~~

This detects statistical outliers relative to a **computed baseline**—not definitive proof of a security event or business incident. For daily/weekly seasonal traffic, supply adequate history and understand seasonality. A Black Friday surge can be legitimate traffic; the query does not know marketing calendars.

### 13.3. Distinguishing Traffic Spikes from Error Spikes

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by bin(Timestamp, 5m), Service
| extend ErrorPct=round(100.0 * Http5xx / Requests,2)
| order by Timestamp asc
~~~

If traffic jumps 5× while error rate stays 0.1% and p95 stays steady, the system is scaling well. If requests stay flat while 5xx spikes, suspect a bad release or dependency outage. If requests drop to zero, verify **ingestion health and user-facing availability** before assuming users disappeared.

### 13.4. Baselines and Day-Over-Day Comparisons

To compare against the same hour yesterday using `ago(1d)`:

~~~kusto
let NowUtc = now();
let Today =
    ApiTelemetry
    | where Timestamp >= NowUtc - 1h and Timestamp < NowUtc
    | summarize RequestsToday=count() by Service;
let Yesterday =
    ApiTelemetry
    | where Timestamp >= NowUtc - 25h and Timestamp < NowUtc - 24h
    | summarize RequestsYesterday=count() by Service
    | project PreviousService=Service, RequestsYesterday;
Today
| join kind=fullouter (Yesterday)
    on $left.Service == $right.PreviousService
| extend
    ServiceName=coalesce(Service, PreviousService),
    TodayCount=coalesce(RequestsToday, 0),
    YesterdayCount=coalesce(RequestsYesterday, 0)
| project ServiceName, TodayCount, YesterdayCount
~~~

**Note:** the example aliases keys to `Service` and `PreviousService` to avoid relying on automatic duplicate-column renaming; this compares two 1-hour aggregates. For minute-by-minute aligned overlays, adjust time offsets/binning explicitly. Holidays, releases, and timezones can skew baselines.

## 14. KQL `let`, `materialize()`, Stored Functions, and Materialized Views

When dashboards repeat the same 20 filter lines everywhere, logic drifts easily. ADX provides several ways to reuse logic and precompute results, each serving **a distinct purpose**.

### 14.1. `let` — Naming Within One Query

~~~kusto
let ProductionErrors =
    ApiTelemetry
    | where Timestamp > ago(1h)
    | where Environment == "prod"
    | where StatusCode >= 500 and StatusCode < 600;
ProductionErrors
| summarize Errors=count() by Service
| order by Errors desc
~~~

`let` is scoped to the current query; separate queries must redeclare it. Use `let` for readability, not to create persistent materialized data.

### 14.2. `materialize()` — Caching a Subquery Within One Query

When a subquery is referenced multiple times in the **same request**, consider:

~~~kusto
let Recent = materialize(
    ApiTelemetry
    | where Timestamp > ago(1h) and Environment == "prod"
    | project Service, StatusCode, DurationMs
);
let Totals =
    Recent
    | summarize Requests=count(), P95Ms=percentile(DurationMs,95)
      by Service;
let Failures =
    Recent
    | where StatusCode >= 500 and StatusCode < 600
    | summarize Http5xx=count() by Service;
Totals
| join kind=leftouter (Failures) on Service
| extend Http5xx=coalesce(Http5xx, 0)
| project Service, Requests, Http5xx, P95Ms
~~~

`materialize()` has **finite cache memory** and can raise memory pressure if intermediate results are huge. Push `where` and `project` early **inside** the subquery and benchmark before/after. Never wrap every table in `materialize()` as a blanket habit.

### 14.3. Stored Functions — Named Logic in the Database

A Kusto function stores shared query logic in the database:

~~~kusto
// Management command, for DBAs/Kusto admins in lab databases only.
.create-or-alter function with (folder = "Observability",
    docstring = "HTTP 5xx by service in a lookback window")
ErrorsByService(Lookback:timespan) {
    ApiTelemetry
    | where Timestamp > ago(Lookback)
    | where Environment == "prod"
    | summarize Http5xx=countif(StatusCode >= 500 and StatusCode < 600)
      by Service
}
~~~

Once deployed with appropriate privileges:

~~~kusto
ErrorsByService(1h)
| order by Http5xx desc
~~~

**Manage function versions** in source control/IaC, document contracts, and run regression tests. Functions do not run ingestion or build dashboards automatically. A database `Viewer` cannot necessarily create or alter functions.

### 14.4. Materialized Views — Precomputing Aggregates

For dashboards continuously running:

~~~kusto
ApiTelemetry
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600)
  by Service, bin(Timestamp, 5m)
~~~

a **materialized view** (when supported by engine rules and aggregate types) persists incrementally updated aggregates from the source table, cutting read costs. However:

- Not every KQL query or operator is supported inside materialized view definitions.
- They incur **ingestion/maintenance compute**, backfill, and storage costs.
- Result freshness depends on pipeline/materialization lag and query syntax.
- Late arrivals and updates/dedup can affect semantics.
- Monitor materialization health, source retention, and schema changes.

**Do not create materialized views for every dashboard**: for queries run once daily, continuous view maintenance may cost more than scanning on demand. When querying both materialized and unmaterialized recent data, verify Kusto's view query semantics.

### 14.5. Update Policies Are Not an ETL Transaction Engine

ADX **update policies** trigger transformations upon source table ingestion to populate derived tables. Helpful for early normalization, yet evaluate:

- Ingestion failures when mappings or transforms fail.
- Duplicates and idempotency.
- CPU/latency and consistency policies between source and target.
- Schema evolution and policy modification permissions.
- Monitoring when ingesting millions of events.

Never use update policies as a cross-table database transaction guaranteeing order correctness.

## 15. Optimizing KQL at Scale

On a multi-billion-row table, the difference between a good and bad query can be **seconds versus minutes**, or negligible usage versus starving other teams' dashboards. ADX is fast, yet queries are never free.

### 15.1. Rule 1: Filter Time as Early as Possible

**Avoid:**

~~~kusto
ApiTelemetry
| summarize Total=count() by Service
~~~

This query may have to scan data across the **entire retention window**.

**Prefer:**

~~~kusto
ApiTelemetry
| where Timestamp >= ago(1h)
| where Environment == "prod"
| summarize Total=count() by Service
~~~

If all-time totals are needed, build a materialized view or summary table rather than rescanning years of data every 10 seconds.

### 15.2. Rule 2: Project Only Needed Columns

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Service == "orders-api"
| project Timestamp, StatusCode, DurationMs, TraceId
| top 100 by DurationMs desc
~~~

`project` drops heavy columns like `Properties:dynamic` when unneeded, shrinking data movement and responses. Columnar storage already optimizes column access, yet trimming outputs early remains good practice.

### 15.3. Rule 3: Avoid Unnecessary `parse_json`, Regex, and Substring Scans

**Inefficient on frequently queried fields:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| extend Parsed = parse_json(RawPayload)
| where tostring(Parsed.service) == "orders-api"
~~~

If `service` is always present, ingest it into a typed `Service:string` column and query:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| where Service == "orders-api"
~~~

**Use the first pattern only if the table holds `RawPayload`.** Promoting hot fields to typed columns adds mapping/schema work yet saves massive CPU on repeated queries.

### 15.4. Rule 4: Aggregate Before Joining

If dependency telemetry has 500 million rows and requests have 100 million rows:

~~~text
Naive join raw requests × raw dependencies
    → Explodes intermediate row counts.

Filter both sides to the exact time window
    → Aggregate dependencies by TraceId
    → Join compact results
    → Project only needed fields
~~~

`join` strategies (`broadcast`, `shuffle`, `lookup`) depend on table sizes and distributions. **Never add join hints blindly** without checking query plans; wrong hints can slow queries down.

### 15.5. Rule 5: Bound `summarize` Cardinality

~~~kusto
// Caution: returning one row per TraceId can produce huge outputs.
ApiTelemetry
| where Timestamp > ago(1d)
| summarize Requests=count() by TraceId
~~~

For dashboards, group by `Service`, `Region`, `Operation`, and time buckets. Drill into `TraceId` only for small subsets during investigations. To count unique traces, use `dcount(TraceId)` (approximate).

### 15.6. Query Outputs, Sampling, and Resource Limits

Returning 30 days of raw logs hits result-size limits and exhausts client memory. Best practices:

- Return **aggregates** first, then drill down into details.
- Use `top N by ...` when deterministic ranking is required.
- Avoid `take N` if you expect "latest N records" without sorting.
- Use sampling for exploration, **never** treating random samples as exact billing or security evidence.
- Monitor query diagnostics, CPU/memory consumption, concurrency, and throttling.
- Cap concurrency and deadlines in dashboards/SDKs so thousands of heavy queries never flood the cluster.

### 15.7. Retention and Hot Caching Are Two Distinct Policies

**Retention** governs how long data survives; **caching policy** governs how much recent data resides in fast cache for high query speed. Example:

~~~text
Soft-delete retention: 90 days
Hot cache period:      14 days

Query last 2h  → typically benefits from hot cache
Query last 60d → older slices may read from slower storage tiers
~~~

This is an **illustrative model**; query speed depends on cluster size, ingestion, and partitioning. Never confuse "aged out of hot cache" with "deleted." Retention fulfills deletion obligations; caching balances speed against capacity.

**Read-only** policy inspection commands when authorized:

~~~kusto
.show table ApiTelemetry policy retention

.show table ApiTelemetry policy caching
~~~

These are **Kusto management commands**, not KQL `SELECT` queries. Policies can inherit from database defaults; inspect effective policies at the target scope. Never `.alter` production retention arbitrarily just to speed up queries.

### 15.8. KQL Performance Checklist

| Question | If "No" |
|---|---|
| Is time filtered at the start of the query? | Add `where Timestamp ...` |
| Are service/env/operation filtered early? | Trim rows prior to aggregation |
| Does `project` keep only needed columns? | Drop unused dynamic payloads |
| Grouping by high-cardinality IDs? | Use `dcount` or scoped drill-downs |
| Are both sides of a `join` filtered and matched in cardinality? | Aggregate first, check for duplicate keys |
| Does `mv-expand` explode row counts? | Filter and constrain expansion |
| Does the query run 1,000×/hour? | Evaluate functions, materialized views, or caching |
| Does the query demand strict exactness? | Never substitute approximate `dcount`/percentiles for ledgers |

## 16. Azure Data Explorer Security and KQL Permissions

ADX logs can reveal internal paths, application IDs, identifiers, and security events. Powerful KQL search requires **strictly governing who can query what**.

### 16.1. Permission Layers

| Layer | Example Permissions | Does Not Mean |
|---|---|---|
| **Azure control-plane RBAC** | Contributor/Reader on the cluster ARM resource | Automatic read access to all Kusto tables |
| **ADX database data-plane roles** | Viewer, User, Ingestor, Admin per Kusto model | Ability to alter cluster VNets/Private Endpoints |
| **Table/function security** | Narrow access policies, RLS/restricted views where supported | Automatically protects data once exported to CSV |
| **Producer/ingestion identity** | Managed identity reading Event Hubs and ingesting into tables | Read access to all analytics datasets |
| **Consumer query identity** | Entra principal granted query rights | Permission to export/copy PII outside the org |

**Least privilege** principle: dashboard readers query approved tables/aggregates, ingestion connectors hold only ingest rights, and only platform admins modify retention, policies, and permissions.

### 16.2. Authentication with Microsoft Entra ID

Kusto clients typically authenticate via **Microsoft Entra** through SDKs, Azure CLI login (labs), or managed identities/service principals (runtime). After obtaining a valid token, the principal still needs **database/table permissions**.

~~~text
Developer / app
    ↓ Acquire Entra token for ADX cluster
ADX query endpoint
    ↓ Authorize database/table/function access
KQL query execution
    ↓ Return only permitted results
~~~

**Azure Contributor on a resource group does not make you a Kusto database Viewer.** When Kusto denies access, verify tenant, query endpoint, database, data-plane role assignments, and managed identity—never escalate to subscription Owner to test.

### 16.3. Row-Level Security (RLS) and Multi-Tenant Data

Suppose telemetry includes `TenantId`. A dashboard for Partner A must never expose Partner B's events. Options:

- Ingest into **separate databases/tables** by data classification where warranted.
- Enforce **row-level security policies**, restricted views, or supported ADX data-protection features.
- Expose only governed **stored functions/views** with scoped permissions.
- Separate application credentials and govern export/query access.

**Crucial rule:** putting `where TenantId == "A"` in a dashboard query **is not a security boundary** if users can run arbitrary KQL against the underlying table. Enforce isolation at the **data plane, database, or row-level security**, never solely in UI filters.

### 16.4. Never Ingest Secrets

For logs and telemetry:

- Never store `Authorization: Bearer ...`, API keys, connection strings, passwords, cookies, or session tokens.
- Redact PII such as emails, phone numbers, and addresses unless explicitly justified.
- Never store payment card details or unnecessary raw request bodies.
- Use correlation/route templates instead of raw user-ID URLs wherever possible.
- Separate security/audit logs from debug logs with distinct retention policies.
- Evaluate cross-region ingest/exports and customer-managed keys/encryption per compliance rules.

**A 30-day retention policy does not erase data already exported to laptops, Power BI, or Blob backups.** Deletion and incident response must account for exports and downstream copies.

### 16.5. Private Networking

ADX supports network isolation and private endpoints depending on deployment model and features. A private architecture might look like:

~~~mermaid
flowchart LR
    PROD[Producers / Event Hubs] --> ING[ADX ingestion path]
    CLIENT[SRE / Dashboard in approved network] --> DNS[Private DNS / resolver]
    DNS --> PE[ADX Private Endpoint]
    PE --> QUERY[ADX query endpoint]
    ING --> DATA[(Kusto tables)]
    QUERY --> DATA
    ID[Microsoft Entra ID] -. Authentication .-> QUERY
~~~

**Ingestion** and **query** paths may require distinct endpoints, DNS entries, and identities depending on configuration. Creating an inbound Private Endpoint for ADX **does not automatically provide outbound connectivity from ADX to Event Hubs, Storage, or Key Vault** in every topology. Check managed private endpoints, egress rules, VNets, Private DNS, and routing per service.

Always:

1. Map inbound data sources, query clients, and outbound dependencies.
2. Use official FQDNs from the resource and verify DNS resolves to private IPs from the runtime.
3. Verify HTTPS/TLS ports and certificate hostnames.
4. Grant distinct ingest and query identities/permissions.
5. Under private-only policies, **disable public exposure only after every client is tested**.
6. Monitor failed ingestions and query logins after network changes.

**Never reuse Azure SQL or Storage Private DNS zone names for ADX.** Private DNS zone names and zone groups differ by service and region; read resource-provided configuration when deploying.

### 16.6. Governing Expensive Queries

Users authorized to query large databases can inadvertently trigger **query cost and performance impacts** for others. Configure workload groups, query limits, concurrency caps, and budgets using ADX governance features. Never grant unrestricted access to external partners or unmonitored dashboards; monitor resource consumption and audits.

## 17. Monitoring ADX: Separate Ingestion Health from Query Health

A system can return KQL results instantaneously **while ingestion stopped two hours ago**. Conversely, ingestion may be healthy while queries crawl due to cluster CPU or bad query patterns. These are two distinct reliability dimensions.

### 17.1. Ingestion Observability

| KPI | Question Answered |
|---|---|
| **Ingestion volume/events per second** | Keeping pace with expected producer traffic? |
| **Ingestion latency** | How quickly do events become queryable in ADX? |
| **Ingestion failures** | Failing JSON mappings, schemas, permissions, or throttling? |
| **Event Hubs lag/backlog** | Is the connector keeping up with partitions/consumer groups? |
| **Last event time per source** | Did a source stop emitting or did the pipeline stall? |
| **Duplicates/late arrivals** | Are retries multiplying rows or arriving late? |
| **Storage/retention growth** | Is data growing faster than forecast? |

KQL example to detect silent sources (observes only already-ingested data):

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| summarize LastEventUtc=max(Timestamp), Events=count() by Service
| extend MinutesSinceLastEvent=datetime_diff("minute", now(), LastEventUtc)
| order by MinutesSinceLastEvent desc
~~~

**If a service emitted zero records all day, it will not appear in this output at all.** To alert on missing services, maintain an **expected-services inventory** and `join kind=leftouter`, or run independent synthetic probes. Also remember event timestamps can reflect skewed client clocks; monitor pipeline/ingestion metrics too.

### 17.2. Query Observability

| KPI | Impact |
|---|---|
| Query duration p50/p95 | Analyst and dashboard responsiveness |
| Query CPU/memory/resource usage | Cluster sizing or query anti-patterns |
| Query failures/timeouts | Syntax, permissions, capacity, result limits |
| Concurrent queries | Workload contention |
| Data scanned / cache hits | Retention/hot cache and filter efficiency |
| Throttling / admission control | Workload optimization or compute scaling needed |

Kusto emits query diagnostics alongside Azure Monitor metrics depending on deployment. Never declare a "healthy cluster" solely from average CPU under 50%; heavy concurrent queries can still hit memory limits or throttling while average CPU looks modest.

### 17.3. Inspecting Ingestion Failures

With appropriate admin privileges, Kusto provides management commands to inspect ingestion operations and failures, such as:

~~~kusto
// Read-only administrative diagnostics where permission allows.
.show ingestion failures
~~~

Correlate with Azure Monitor metrics, Event Hubs diagnostic logs, connector health, and producer logs. **A failed ingestion status does not tell you which individual records to replay unless you preserve event IDs or raw sources.**

### 17.4. Four Immediate Alerts to Configure

1. **Ingestion lag breaching SLO**, e.g., lag exceeding 5 minutes continuously.
2. **Rising ingestion failure rates** by database, table, or source.
3. **Query p95 or failure spikes** on critical dashboards.
4. **Cluster utilization or storage growth exceeding budget**, with an owner and runbook.

Depending on workloads, also alert on silent sources, permission changes, retention edits, unhealthy materialized views, Event Hubs backlogs, and telemetry error spikes. **Alerts lacking clear owners and actions** create only noise.

## 18. Reliability, Late Data, Recovery, and Data Lifecycle

A reliable logging platform does more than ingest cleanly on normal days. During Event Hubs outages, cluster overload, or bad mappings, operations must know **which data was lost, which was duplicated, and where to replay from**.

### 18.1. Availability vs. Freshness

Two distinct SLOs:

~~~text
Query availability:
  Analyst can execute a query and receive a result.

Telemetry freshness:
  Newly produced events become queryable within a target delay.
~~~

A KQL dashboard may load cleanly yet show events only up to **09:00** when it is **09:30**. Never monitor query success alone; track **last observed event time** and ingestion lag.

### 18.2. Buffered Ingestion and Replay

Event Hubs or raw files in Blob/Data Lake provide a **replay window** bounded by configured retention. When the ADX connector stalls for 20 minutes:

1. Confirm Event Hubs or source storage still retains the uningested events.
2. Check current consumer group checkpoints and the missing time gap.
3. Resolve root cause (permissions, mapping, cluster saturation).
4. Let the connector catch up or backfill via supported mechanisms.
5. Check for duplicates/late arrivals and reconcile counts against the source.
6. Monitor ingestion lag and alerts during catch-up.

**Once Event Hubs retention expires without raw archives, uningested events may be unrecoverable.** "ADX manages internal replicas" never creates copies of data **that never reached ADX**.

### 18.3. Deduplication and Ordering in Analytics

Because telemetry delivery is often **at-least-once**:

- Include `EventId` or source sequence IDs when deduplication is needed.
- Keep `Timestamp` as event time alongside `ReceivedAtUtc` to measure lag accurately.
- Never apply `arg_max(Timestamp, *)` by business key without understanding semantics.
- When events mutate across versions, define explicit latest-version rules.
- Never deduplicate away multiple spans sharing one `TraceId`, or you lose the call graph.

For billing/financial reconciliation, rely on authoritative ledgers and **exact IDs**. `dcount()` and sampled telemetry are not accounting evidence.

### 18.4. Retention and Deletion Policies

An organization might adopt:

| Data Type | Illustrative Retention | Rationale |
|---|---:|---|
| Debug traces | 7–14 days | High volume, high detail/PII exposure |
| API request metrics | 30–90 days | SLO analysis and release trends |
| Security audit | Per policy/compliance | Requires longer investigation retention and stricter protection |
| Raw telemetry archive | Per contract and storage | Backfill and reprocessing when needed |

These intervals **are not default legal mandates**; organizations must decide per contracts, jurisdictions, and security policy. ADX retention and Blob/Event Hubs/Log Analytics retention are **independent policies** that must be governed together.

### 18.5. Exports, Backups, and Disaster Recovery

ADX provides service-managed durability/recovery mechanisms and data export capabilities, yet **never treat query caches or extent replicas as an application backup you can restore arbitrarily to any point**. A complete strategy needs:

- Raw source retention (Blob/Event Hubs) long enough for critical data.
- **Exports/backups** per service capabilities and defined recovery targets.
- Mappings, functions, materialized views, and roles tracked in IaC/source control.
- Regional failure evaluation and recovery topology matched to SKU/capabilities.
- **Backfill drills on a lab table/database**, verifying counts, checksums, and query compatibility.
- Measured RPO/RTO—never claim "zero data loss" untested.

**Accidentally dropping a table or shortening retention** purges data per policy and will not be cured by restarting the cluster. Destructive admin operations require approvals, backup/retention plans, and audit trails.

### 18.6. Pipeline Evolution

When a producer introduces `schemaVersion=2` or changes `DurationMs` from numeric to string:

1. Test updated mappings in staging.
2. Roll out table schema / ingestion transform updates carefully.
3. Maintain backward compatibility with older versions during transition.
4. Re-test stored functions and dashboards.
5. Watch mapping failures closely post-deploy.
6. Maintain a backfill plan if records were dropped.

Even with `dynamic` JSON, new fields ingest easily yet **inconsistent names or types** still break queries. Schema evolution is more than "JSON loaded without error."

## 19. FinOps: Where Do ADX Queries and Ingestion Cost Money?

When estimating ADX cost, look at the **entire pipeline**, not just cluster node hourly rates. A dashboard polling unbounded queries every 5 seconds can burn more compute than ingestion itself.

### 19.1. Cost Components

| Component | Cost Driver |
|---|---|
| **ADX compute** | Cluster SKU/cores/nodes, scaling, and uptime |
| **Data storage** | Ingested/retained data size, compression, and policies |
| **Hot caching** | SSD/cache capacity and required query performance |
| **Streaming/ingestion** | Event rates, batching, connectors, and auxiliary services |
| **Event Hubs** | Partitions, throughput, and retention per tier |
| **Blob/Data Lake archive** | Raw logs, exports, replays, network transfers |
| **Networking** | Private Endpoints, DNS Resolver, VNet/Firewall/egress if used |
| **Monitoring** | Azure Monitor, Log Analytics, dashboards/alerts, retention |
| **Human/operations** | Incidents, backfills, schema governance, DR drills |

Pricing depends on **region, SKU, provisioning model, and timing**. Reserved/commitment pricing may exist for certain capacities, though you should benchmark steady-state demand before committing.

### 19.2. Rough Volume Sizing

Suppose:

~~~text
Producers:              10 services
Events/service/second:   1,000
Average event size:      800 bytes (raw)
Seconds/day:             86,400
~~~

Daily raw input:

\[
10 \times 1{,}000 \times 800 \times 86{,}400
=691{,}200{,}000{,}000\ \text{bytes}
\approx 691.2\ \text{GB/day}.
\]

Retaining 30 days yields a theoretical raw source volume around:

\[
691.2 \times 30 = 20{,}736\ \text{GB}
\approx 20.7\ \text{TB}.
\]

**This is not ADX's billed storage GB**: columnar compression, metadata, replicas, retention, ingestion errors, and data shapes change actual stored size substantially. Still, the math shows why stretching retention from 30 to 365 days sharply shifts both cost and compliance exposure.

### 19.3. Reducing Cost Without Losing Needed Signal

- **Structured logs over uncontrolled verbose strings.**
- **Sampling** debug traces when business/security rules do not require 100% capture, explicitly recording the sampling rate.
- Avoid ingesting multi-KB raw request/response bodies when key dimensions suffice.
- Tailor retention by data class and hot cache windows to actual query lookbacks.
- Lower dashboard refresh frequencies or add materialized aggregates where justified.
- Use `project` and `where` early to trim scanned data and query compute.
- Separate bursty ingestion demand from interactive query compute.
- Tag owner, team, environment, and `costCenter` to compare volume and spend per service.
- Watch budget alerts and scale capacity around SLOs.

**Sampling is inappropriate when exact counts of every security action or financial event are required.** Sample performance traces while retaining audit events per policy. Never present a pretty dashboard as proof of 100% compliance if 90% of requests were sampled out.

### 19.4. Query Value vs. Query Cost

Suppose a dashboard has 20 charts, each querying 30 days of raw logs every 10 seconds: 120 queries/minute over massive data. Improvements:

1. Scope operational charts to **last 15m / 1h**.
2. Precompute 1m/5m aggregates via supported materialized views where warranted.
3. Refresh every 30–60 seconds where appropriate.
4. Let analysts drill down into raw logs only when anomalies appear.
5. Use query diagnostics to benchmark before and after.

Never create materialized views for every query blindly to "save money": write-side maintenance and storage also cost money.

## 20. IaC, Source Control, and KQL Change Governance

ADX comprises **infrastructure** (clusters, databases, networking) and **data logic** (tables, mappings, functions, policies, permissions). Both require versioned deployments rather than letting developers edit production schemas directly during live traffic.

### 20.1. Clear Ownership Boundaries

| Team | Owns | Guardrails |
|---|---|---|
| **Cloud Platform** | Cluster SKU, VNet/private endpoints, availability, resource RBAC | Change approvals, IaC, cost governance |
| **Data Engineering** | Ingestion connectors, mappings, schema evolution, retention | Replay strategy, schema tests, source ownership |
| **SRE/Observability** | Dashboards, alerts, query SLOs, incident runbooks | Query reviews, metric definitions, on-call |
| **Security/Privacy** | Data classification, RLS, permissions, retention, exports | Least privilege, auditing, compliance |
| **Application team** | Structured events/trace IDs, schema contracts, sampling | Zero secrets/PII, correlation consistency |

### 20.2. Reference Repository Layout

~~~text
adx-observability/
├── infrastructure/
│   ├── main.bicep
│   └── environments/
│       ├── dev.params.json
│       └── prod.params.json
├── schemas/
│   ├── api-telemetry-table.kql
│   └── api-telemetry-mapping.kql
├── functions/
│   └── errors-by-service.kql
├── dashboards/
│   ├── requests-by-region.kql
│   └── p95-latency.kql
├── tests/
│   ├── schema-contract/
│   ├── query-golden-data/
│   └── security-negative-tests/
└── runbooks/
    ├── ingestion-backlog.md
    └── trace-query-slow.md
~~~

This is an **illustrative layout**, not a requirement to create separate files in this lesson. Production setups can deploy Bicep/ARM/Terraform alongside Kusto commands under gated pipelines. **Never commit connection strings with secrets, Entra tokens, or production PII exports.**

### 20.3. Suggested CI/CD Pipeline

~~~mermaid
flowchart LR
    PR[Pull request] --> LINT[Review KQL + mapping/schema]
    LINT --> TEST[Run on synthetic golden dataset]
    TEST --> SEC[Security/PII + RBAC review]
    SEC --> PLAN[Check IaC/management command diff]
    PLAN --> DEPLOY[Deploy to staging ADX]
    DEPLOY --> INGEST[Ingest sample + verify counts/latency]
    INGEST --> APPROVE[Production approval]
    APPROVE --> PROD[Apply compatible changes]
    PROD --> WATCH[Monitor ingestion/query health + rollback]
~~~

### 20.4. High-Risk Changes

- Changing ingestion mappings in ways that alter types or timestamps.
- Extending or shortening retention outside policy.
- Dropping or recreating tables or databases.
- Editing update policies in ways that break ingestion.
- Creating materialized views that trigger massive backfills.
- Altering database roles/RLS, risking data leaks or broken dashboards.
- Changing Event Hubs consumer groups/checkpoints, causing duplicates or gaps.
- Switching public/private networking before CI/consumers have the new path.

**Never edit production directly in the Portal and forget source control.** After break-glass fixes, capture audit logs and reconcile back into IaC/KQL repos immediately.

## 21. End-to-End Lab: From Azure Portal to KQL and the Query SDK

The lab has two tiers: **A. querying inline `datatable` only** with zero persistent resources, and **B. querying an `ApiTelemetry` table inside a lab ADX**. All examples are instructional only and **must not be executed automatically while authoring**. Provisioning clusters/ingestion incurs costs and requires admin privileges; ensure approved budgets, owners, and sandbox environments.

### 21.1. Preparation

- An Azure/Entra ID account with access to a **test environment**.
- Azure Data Explorer Web UI: `https://dataexplorer.azure.com` or an approved query interface.
- If using a lab ADX cluster: query endpoint, **database name**, and required data-plane Viewer/User role.
- If practicing ingestion: dedicated lab cluster/database/table, table/mapping creation rights, synthetic Event Hubs/Blob source, and cost controls.
- Never use real tokens, keyed connection strings, or real customer logs.
- Learners understand `datatable` lives solely inside the current query execution.

### 21.2. Lab A — No Table Creation Required

1. Open the Kusto query editor in an authorized KQL environment.
2. Copy the `let Demo=datatable(...)` query from **Section 7.1**.
3. Run it and confirm **12 prod rows + 1 staging row before filtering**, leaving **12 rows** after `Environment=="prod"`.
4. Replace the trailing pipeline:

~~~kusto
Demo
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by Service, Region
| extend ErrorRatePct=round(100.0 * Http5xx / Requests,2)
| order by ErrorRatePct desc
~~~

**Execution note:** the snippet above **replaces the tail** after `let Demo=datatable(...)` in the **same query tab**; running these lines alone in an empty tab fails with unknown table `Demo`.

5. Replace the time filter with absolute UTC bounds `2026-11-20T09:00:00Z .. 2026-11-20T09:30:00Z`.
6. Extract deployment via `tostring(Properties.deployment)` and compare `v41` vs. `v42`.
7. Distinguish `503/500` from `429` and `200/201`.
8. Explain why p95 over 13 records is not a valid production SLO.

### 21.3. Lab B — Using an Authorized ADX Database/Table

When the platform team provides a lab ADX:

1. Verify cluster/database endpoint, tenant, role, and budget.
2. Create the table and mapping from **Section 5.4** if permitted and not yet created.
3. Ingest **synthetic JSON records** matching Section 4.2 via an appropriate ingestion mechanism.
4. Verify the ingestion mapping and row count:

~~~kusto
ApiTelemetry
| summarize Events=count(), FirstEvent=min(Timestamp), LastEvent=max(Timestamp)
~~~

5. Run queries for 5xx rate and p95 by service/operation and deployment.
6. Measure ingestion lag by comparing event time and ingestion time.
7. Add a trace/dependency table **only after validating its schema**, then join by `TraceId`.
8. Build a KQL dashboard distinguishing requests, 5xx, 429, p95, and ingestion lag.
9. Confirm ingested synthetic data contains **zero PII or secrets**.
10. Keep policy management rights restricted to DB/platform admins rather than granting broadly to all analysts.

### 21.4. Measuring Ingestion Lag with KQL

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| extend IngestedAtUtc=ingestion_time()
| where isnotnull(IngestedAtUtc)
| extend LagSeconds=datetime_diff("second", IngestedAtUtc, Timestamp)
| summarize
    Events=count(),
    MedianLagSeconds=percentile(LagSeconds,50),
    P95LagSeconds=percentile(LagSeconds,95),
    MaxLagSeconds=max(LagSeconds)
  by Service
~~~

**Prerequisites:** `ingestion_time()` requires appropriate metadata/policy enabled; if null, the filter drops all rows. Skewed client clocks or backfilled historical events distort apparent lag vs. real pipeline latency. For strict SLOs, measure with controlled producer/connector timestamps and track Event Hubs backlogs separately.

### 21.5. SDK Queries: Python and Azure CLI Credentials (Lab)

An analyst can use the **Python Azure Data Explorer SDK** to query ADX. On an authorized dev machine:

~~~bash
az login
python -m pip install azure-kusto-data

export KUSTO_CLUSTER="https://<cluster>.<region>.kusto.windows.net"
export KUSTO_DATABASE="Telemetry"
~~~

Reference Python snippet:

~~~python
import os

from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

cluster = os.environ["KUSTO_CLUSTER"]
database = os.environ["KUSTO_DATABASE"]

# Development-only login from az login; not a production credential plan.
kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(cluster)
client = KustoClient(kcsb)

query = """
ApiTelemetry
| where Timestamp > ago(1h) and Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600)
  by Service
| order by Http5xx desc
"""

try:
    result = client.execute(database, query)
    for row in result.primary_results[0]:
        print(row["Service"], row["Requests"], row["Http5xx"])
finally:
    client.close()
~~~

**Prerequisites:** `ApiTelemetry` exists, the user ran `az login` in the right tenant, holds a **data-plane query role**, and networking/DNS reaches the cluster. In production, use an **approved managed identity, workload identity, or service principal**—never stick a developer `az login` inside a 24/7 container. SDK APIs and versions evolve; check current package docs at implementation time.

### 21.6. When No Cluster Is Available in the Lab

Do not provision an expensive production ADX SKU just to test `summarize`. Use an organization-provided demo/free/lab environment **if features match**, noting terms and quotas vary. The `datatable` exercises and analytical scenarios are sufficient to master KQL without live ingestion permissions.

### 21.7. Lab Acceptance Checklist

| Check | Passing Criterion |
|---|---|
| Schema/query editor | `datatable` query executes cleanly without error |
| Environment filtering | 12 prod rows, 1 staging row in base data |
| Error definitions | 500–599 counted as 5xx; 429 tracked separately |
| Percentiles | Computes p95 by service/operation and explains sample-size caveats |
| Structured JSON | Extracts `Properties.deployment` |
| Traceability | Drills down by trace ID without collapsing spans wrongly |
| Security | Zero production PII/tokens; scoped roles |
| Ingestion (if available) | Synthetic JSON maps cleanly and lag is measured |
| Performance | Time/column filtering early with bounded output size |
| Cost | Clear owner, budget, and cleanup plan |

## 22. Case Study: Investigating an Orders API Incident After Deployment

**Scenario:** Orders API emits structured logs to Event Hubs, ingested into ADX `ApiTelemetry`. Release `v42` deployed in `southeastasia` at **09:10 UTC on 2026-11-20**, succeeding `v41`. The API began returning frequent `503`s due to Azure SQL timeouts. The `Demo` records in Section 7 simulate this scenario.

### 22.1. Expected Chain of Evidence

~~~mermaid
flowchart LR
    ALERT[Alert: p95 + 5xx spike] --> TIME[Locate time window]
    TIME --> SVC[Break down by service and region]
    SVC --> DEPLOY[Compare v41 / v42]
    DEPLOY --> TRACE[Drill down TraceId]
    TRACE --> DEP[Dependency evidence SQL timeout]
    DEP --> FIX[Rollback or fix backend]
    FIX --> VERIFY[Verify 5xx/p95 and ingestion health]
~~~

Never start by declaring `v42` the sole culprit: Azure SQL, private DNS/networking, or another dependency could have degraded simultaneously. **Gather evidence first, conclude second.**

### 22.2. Step 1: Isolate the Time Window

~~~kusto
let StartUtc = datetime(2026-11-20T09:00:00Z);
let EndUtc = datetime(2026-11-20T09:30:00Z);
ApiTelemetry
| where Timestamp >= StartUtc and Timestamp < EndUtc
| where Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by Service, Region, bin(Timestamp, 5m)
| extend ErrorPct=round(100.0 * Http5xx / Requests,2)
| order by Timestamp asc, ErrorPct desc
~~~

Results should highlight `orders-api`/`southeastasia` diverging from `catalog-api` and `orders-api` in other regions (given sufficient volume). **A handful of sample rows cannot prove causal impact**; production investigations require adequate sample sizes and traffic-mix checks.

### 22.3. Step 2: Deployment Split

~~~kusto
ApiTelemetry
| where Timestamp >= datetime(2026-11-20T09:00:00Z)
  and Timestamp < datetime(2026-11-20T09:30:00Z)
| where Service == "orders-api" and Environment == "prod"
| extend Deployment=tostring(Properties.deployment)
| summarize
    Requests=count(),
    Error5xx=countif(StatusCode >= 500 and StatusCode < 600),
    P95Ms=percentile(DurationMs,95)
  by Deployment, Region
| extend ErrorRatePct=round(100.0 * Error5xx / Requests,2)
| order by ErrorRatePct desc
~~~

Even if `v42` shows higher errors than `v41`, verify **regions, request volume, traffic distribution**, and exact release timestamps. Releases often bundle code, feature flags, configs, and DB migrations; KQL narrows the blast radius rather than naming the code fix automatically.

### 22.4. Step 3: Specific Error Categories

~~~kusto
ApiTelemetry
| where Timestamp >= datetime(2026-11-20T09:10:00Z)
  and Timestamp < datetime(2026-11-20T09:30:00Z)
| where Service == "orders-api" and StatusCode >= 500
| extend ErrorCategory=tostring(Properties.errorCategory)
| summarize
    Failures=count(),
    P95Ms=percentile(DurationMs,95),
    ExampleTrace=take_any(TraceId)
  by ErrorCategory, Region
| order by Failures desc
~~~

`take_any(TraceId)` grabs an arbitrary sample ID **not guaranteed to be the slowest trace**. Use it as a drill-down starting point, not a scientifically representative sample. To find the **slowest** trace, filter by `DurationMs` or use `arg_max(DurationMs, ...)` with appropriate grouping.

### 22.5. Step 4: Drill Down by Trace

~~~kusto
let TargetTrace="tr-005";
ApiTelemetry
| where Timestamp >= datetime(2026-11-20T09:00:00Z)
  and Timestamp < datetime(2026-11-20T10:00:00Z)
| where TraceId == TargetTrace
| project Timestamp, Service, Operation, StatusCode,
          DurationMs, SpanId, Properties
| order by Timestamp asc
~~~

With full OpenTelemetry, correlate `TraceId` across **dependency logs** and backend traces. If only the HTTP request event exists, you only know a 503 happened; `errorCategory=SqlTimeout` is an **app-emitted label** that must be corroborated against real SQL performance, connectivity, and timeout logs.

### 22.6. Step 5: Verify Recovery

After rolling back or tuning the connection pool, compare 15 minutes before and 15 minutes after:

~~~kusto
let FixTime=datetime(2026-11-20T09:30:00Z);
let Before =
    ApiTelemetry
    | where Timestamp >= FixTime-15m and Timestamp < FixTime
    | where Service == "orders-api" and Environment == "prod"
    | summarize
        Requests=count(),
        Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
        P95Ms=percentile(DurationMs,95)
    | extend Phase="Before";
let After =
    ApiTelemetry
    | where Timestamp >= FixTime and Timestamp < FixTime+15m
    | where Service == "orders-api" and Environment == "prod"
    | summarize
        Requests=count(),
        Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
        P95Ms=percentile(DurationMs,95)
    | extend Phase="After";
union (Before), (After)
| extend ErrorPct=round(100.0 * Http5xx / Requests,2)
| project Phase, Requests, Http5xx, ErrorPct, P95Ms
~~~

Caveat: `FixTime` is illustrative; in production, use the **actual deployment/remediation timestamp**. `After` events may arrive late, so check ingestion lag and wait for adequate samples. **Recovering p95 alone is insufficient** if SQL data integrity or business transactions were impacted.

### 22.7. Writing an Evidence-Based Postmortem

A concise postmortem includes:

- UTC timeline: alert, first bad request, deployment, mitigation, recovery.
- Impact: affected services, operations, regions, and client cohorts.
- Metrics: requests, 5xx rates, p95/p99, ingestion freshness.
- Evidence: trace IDs, dependency error categories, Azure SQL/Application Insights logs.
- Evidence-backed root cause—not simply "`v42` deployed around the same time."
- Corrective actions: tests, rollout gates, tracing, circuit breakers, SQL pool tuning, monitoring.
- RPO/RTO or business reconciliation if data was affected.

**KQL surfaces the evidence**, while remediation decisions rest on SRE/app/database owners and change-management processes.

## 23. Beyond HTTP Logs: IoT Telemetry and Time Series

ADX is not limited to HTTP status codes. A logistics system may emit **temperature, humidity, vibration, and device health** via IoT Hub or Event Hubs. These records carry `DeviceId` and timestamps, without `StatusCode` or `DurationMs`.

### 23.1. Self-Contained Sensor Sample Data

~~~kusto
let Sensors = datatable(
    Timestamp:datetime, DeviceId:string, Region:string, TemperatureC:real)
[
    datetime(2026-11-20T08:00:00Z), "sensor-01", "warehouse-a", 24.0,
    datetime(2026-11-20T08:05:00Z), "sensor-01", "warehouse-a", 24.5,
    datetime(2026-11-20T08:10:00Z), "sensor-01", "warehouse-a", 31.2,
    datetime(2026-11-20T08:15:00Z), "sensor-01", "warehouse-a", 35.4,
    datetime(2026-11-20T08:00:00Z), "sensor-02", "warehouse-b", 22.1,
    datetime(2026-11-20T08:05:00Z), "sensor-02", "warehouse-b", 22.0,
    datetime(2026-11-20T08:10:00Z), "sensor-02", "warehouse-b", 22.2,
    datetime(2026-11-20T08:15:00Z), "sensor-02", "warehouse-b", 22.0
];
Sensors
| summarize
    Samples=count(),
    AvgC=round(avg(TemperatureC),1),
    PeakC=max(TemperatureC)
  by Region, DeviceId
| order by PeakC desc
~~~

**Expected result:** `sensor-01` peaks at **35.4°C**, exceeding `sensor-02` at **22.2°C**. This is synthetic practice data, not live sensor readings. For safety-critical temperatures, enforce edge/device-level rules and alerting rather than relying solely on analytics dashboards.

### 23.2. Comparing Consecutive Readings

~~~kusto
let Sensors = datatable(
    Timestamp:datetime, DeviceId:string, TemperatureC:real)
[
    datetime(2026-11-20T08:00:00Z), "sensor-01", 24.0,
    datetime(2026-11-20T08:05:00Z), "sensor-01", 24.5,
    datetime(2026-11-20T08:10:00Z), "sensor-01", 31.2,
    datetime(2026-11-20T08:15:00Z), "sensor-01", 35.4
];
Sensors
| sort by DeviceId asc, Timestamp asc
| serialize
| extend
    PreviousDevice=prev(DeviceId),
    PreviousC=prev(TemperatureC)
| where DeviceId == PreviousDevice
| extend DeltaC=TemperatureC-PreviousC
| project Timestamp, DeviceId, TemperatureC, PreviousC, DeltaC
| order by DeltaC desc
~~~

`prev()` depends on **serialized row order**. Never call it on unsorted large tables or interleaved `DeviceId` streams without checking device boundaries. When sensor data arrives late, sort by event `Timestamp` rather than ingestion order.

### 23.3. Missing Telemetry and Disconnected Devices

A sensor silent for 30 minutes could mean:

- Power or network outage.
- Device stopped transmitting.
- Event Hubs connector lag.
- Mapping failure dropping records.
- `DeviceId` legitimately decommissioned.

**Querying the telemetry table alone cannot reveal completely silent devices** without an **expected device inventory**. Join an authorized device dimension via `leftouter join` against last-seen timestamps, thresholding by each device's cadence. Never treat "missing record" as temperature 0.

### 23.4. IoT Time-Series Considerations

- Filter by time prior to aggregating.
- Account for sensor sampling intervals and source clock skew.
- Separate hardware malfunctions from ingestion failures.
- Across billions of device IDs, avoid unbounded all-time grouping by ID.
- For anomaly detection, use `make-series` and series functions once sufficient history exists.
- Never use a KQL dashboard alone to drive real-time safety actuators; control loops demand bounded-latency edge/control systems.

## 24. Troubleshooting: Wrong KQL, Missing Data, or Very Slow Queries

### 24.1. Symptom Matrix

| Symptom | Common Cause | How to Check |
|---|---|---|
| `Failed to resolve table or column` | Wrong table/database/schema/case | `.show tables`, check schema and permissions |
| Query uses `TimeGenerated` yet table has `Timestamp` | Copied from Azure Monitor Logs to custom ADX table | Use exact column names from the real table |
| `0 rows` after `ago(1h)` | Historical lab dataset or silent source | Check min/max `Timestamp`, use absolute window |
| `0 rows` despite producer sending | Ingestion lag, connector failure, bad mapping | Event Hubs backlog, ingestion failures, table count |
| Fields from `Properties` always blank | Wrong JSON path, missing field, wrong type | `take 5` on authorized data, inspect sample schema |
| Very high p95 despite low average | Real tail latency, outliers, mixed samples | Break down by bucket/service/operation, inspect slow events |
| `dcount` differs from exact ID count | Approximate algorithm or duplicates | Use exact `count_distinct` where appropriate |
| Join returns multiplied request counts | Many-to-many keys, duplicate trace/span IDs | Aggregate/dedup to right grain before joining |
| `mv-expand` times out query | Huge dynamic arrays without early filtering | Constrain expansion, filter time and service early |
| Query painfully slow | Multi-year scans, string parsing, high cardinality, huge joins | Explain/resource stats, early time filters/projection |
| Query throttled/timed out | Concurrency/cluster load, query limits | Workload metrics, optimize heavy queries, scale with evidence |
| 403/access denied | Entra principal lacks database/table role | Check tenant, cluster, data-plane roles |
| Has cluster Reader yet cannot query tables | Azure control plane differs from Kusto data plane | Grant appropriate database role |
| `ingestion_time()` always null | Metadata/policy disabled or unsupported source | Inspect ingest policy and source timestamps |
| Dashboard shows only stale data | Ingestion halted, wrong window, cache/freshness issue | Last `EventUtc`, ingestion lag, connector health |
| Missing time buckets read as 0 traffic | No events or ingestion gap | `make-series` + source health probes |
| No 429s shown on error dashboard | Only counting 5xx via `countif` | Track throttled 429s and security events separately |
| TLS/private endpoint query error | Wrong DNS, routing, or identity | Test from real runtime, HTTPS/TLS, data permissions |

### 24.2. Eight-Step Diagnostic Runbook

**Step 1 — Verify scope:** are cluster URI, database, table, time range, environment, and resource group/subscription correct?

**Step 2 — Inspect schema:** does the table have `Timestamp`, `Service`, `StatusCode`? Is `Properties` `dynamic` or `string`?

**Step 3 — Run a minimal query:**

~~~kusto
ApiTelemetry
| take 5
~~~

This checks only whether rows exist; `take` **does not return the latest 5 rows**. To inspect recent rows:

~~~kusto
ApiTelemetry
| where Timestamp > ago(1d)
| top 5 by Timestamp desc
~~~

**Step 4 — Check time bounds and freshness:**

~~~kusto
ApiTelemetry
| summarize
    Rows=count(),
    MinTimestamp=min(Timestamp),
    MaxTimestamp=max(Timestamp)
~~~

Interpret `MaxTimestamp` carefully against source clocks; a future-dated event can make last-seen appear artificially fresh.

**Step 5 — Check ingestion:** connector/consumer group, Event Hubs backlog, failures, mappings, permissions, and resource metrics.

**Step 6 — Check query plan:** early time filtering, minimal column projection, proper join cardinality, and bounded dynamic parsing/cardinality?

**Step 7 — Check security/network:** Entra/data-plane roles, private DNS, TLS, and resource policies. Never escalate to subscription Owner to fix a `SELECT`-equivalent permission.

**Step 8 — Verify resolution:** compare source counts, ingestion lag, query latency, output accuracy, and synthetic business checks; update runbooks.

### 24.3. The "Post-Deploy Error Rate = 0%" Trap

A dashboard query:

~~~kusto
ApiTelemetry
| where Timestamp > ago(15m)
| summarize ErrorPct=100.0 * countif(StatusCode>=500) / count()
~~~

returns `0%`. Yet the Event Hubs connector stopped ingesting 30 minutes ago. **Zero ingested events does not mean zero errors.** With empty input, `count()=0`, yielding null/NaN depending on context; if the UI coerces nulls to 0, dashboards actively mislead responders.

Fix: SLO dashboards must assert **data freshness/ingestion health and minimum sample thresholds** before reporting green status.

### 24.4. The "Fast Query, Wrong Answer" Trap

Suppose `DependencyTelemetry` records 5 SQL calls per request; joining raw rows to `ApiTelemetry` and calling `count()` inflates request counts 5×. The query runs fast and draws pretty charts—with completely wrong numbers.

Fix: define **grain** explicitly (request vs. dependency call), pre-aggregate on matching keys, and test against golden datasets. **KQL accuracy matters just as much as speed.**

## 25. Capstone Practice: From Raw Logs to Evidence-Backed Conclusions

**Prompt:** A system runs `orders-api`, `catalog-api`, and `payments-api`, emitting JSON events into Event Hubs ingested into ADX. You are the SRE investigating a post-deployment error spike. If you lack a lab ADX cluster, use the `datatable` from Section 7 and explain your reasoning; **no production access is required**.

### 25.1. Technical Questions

1. **Architecture:** Diagram Application/IoT → Event Hubs/Blob → ADX → KQL dashboard. Explain why Event Hubs alone does not provide KQL analytics.
2. **Service selection:** When should you prefer Application Insights/Log Analytics over provisioning an ADX cluster?
3. **Schema:** Design `Timestamp`, `Service`, `Environment`, `Operation`, `StatusCode`, `DurationMs`, `TraceId`, and `Properties`.
4. **Ingestion:** Explain JSON ingestion mappings and what happens if `durationMs` arrives as a non-numeric string.
5. **Event vs. ingest time:** Source event at 09:15, ADX ingests at 09:22; what is ingestion lag and which timestamp measures API execution latency?
6. **Basic KQL:** Write a query fetching the latest 100 HTTP 5xx errors for `orders-api` in the past 6 hours.
7. **Environment:** Why filter `Environment=="prod"` before calculating production SLOs?
8. **Time bins:** Write a query for 5-minute request counts by region; explain missing buckets.
9. **Error rate:** Write a query calculating 5xx rate and 429 rate separately per service.
10. **Latency:** Write a query for p50/p95/p99 by operation; why is average insufficient?
11. **Deployment:** Compare `v41`/`v42` across the same time window and region.
12. **Dynamic:** Extract `errorCategory` from `Properties` and group by category.
13. **Text search:** When use `has` instead of `contains`? Give a CamelCase example.
14. **Trace joins:** Join requests and dependencies by `TraceId` without double-counting requests.
15. **Distinct:** How does `dcount` differ from `count_distinct`, and when is approximation unacceptable?
16. **Time series:** Use `make-series`/`series_decompose_anomalies` to detect traffic spikes; list false-positive risks.
17. **Query performance:** Optimize a query scanning a year of logs with `mv-expand`/`join` and `project *`.
18. **Security:** Why is `where TenantId=="partner-a"` inside a dashboard query insufficient for tenant isolation?
19. **Reliability:** Event Hubs suffers a 45-minute outage with 30-minute retention; what data can be lost and what mitigates it?
20. **FinOps:** Estimate daily raw volume for 10 services × 1,000 events/s × 800 bytes/event.
21. **Monitoring:** Design alerts for ingestion lag, last event time, query p95, and cluster resource usage.
22. **Incident:** 503s drop after rollback while ingestion actually stopped earlier; why can't you declare recovery from KQL error rate alone?
23. **IoT:** Write a query finding peak temperature per `DeviceId` over 24 hours and evaluate clock skew risks.
24. **Governance:** List schema, retention, and role changes requiring IaC/CI review.

### 25.2. Answers and Reference KQL Snippets

**Question 5 — ingestion lag:** 09:22 − 09:15 = **7 minutes**. To report API execution latency, use instrumented `DurationMs`. To measure pipeline lag, compare verified source vs. ingestion timestamps. Never subtract ingestion time from event time and call it "HTTP latency."

**Question 6 — latest 100 errors:**

~~~kusto
ApiTelemetry
| where Timestamp >= ago(6h)
| where Environment == "prod"
| where Service == "orders-api"
| where StatusCode >= 500 and StatusCode < 600
| top 100 by Timestamp desc
| project Timestamp, Service, Operation, StatusCode,
          DurationMs, TraceId, Properties
~~~

**Question 8 — requests by bucket and region:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Environment == "prod"
| summarize Requests=count() by Region, bin(Timestamp, 5m)
| order by Timestamp asc, Region asc
~~~

**Question 9 — 5xx and 429:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(1h)
| where Environment == "prod"
| summarize
    Requests=count(),
    Http5xx=countif(StatusCode >= 500 and StatusCode < 600),
    Http429=countif(StatusCode == 429)
  by Service
| extend
    ServerErrorPct=round(100.0*Http5xx/Requests,2),
    ThrottlePct=round(100.0*Http429/Requests,2)
~~~

**Question 10 — latency percentiles:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where Environment == "prod"
| summarize
    Samples=count(),
    P50=percentile(DurationMs,50),
    P95=percentile(DurationMs,95),
    P99=percentile(DurationMs,99)
  by Operation
| order by P95 desc
~~~

**Question 12 — error categories:**

~~~kusto
ApiTelemetry
| where Timestamp > ago(2h)
| where StatusCode >= 500 and StatusCode < 600
| extend Category=tostring(Properties.errorCategory)
| summarize Errors=count() by Category
| order by Errors desc
~~~

**Question 14 — joining at the right grain:** confirm one row per request, pre-aggregate dependencies via `summarize ... by TraceId`, then `join kind=leftouter`. If a trace holds multiple request spans, include span/root operation IDs to distinguish them. Never use `count()` after a raw many-to-many join as total requests.

**Question 15 — distinct:** `dcount` is approximate and great for dashboards; `count_distinct` computes exact counts within system limits at higher resource cost. Financial ledgers rely on exact event IDs and transactions in authoritative stores, not telemetry alone.

**Question 18 — security:** UI filters can be edited or bypassed if users hold query rights on the raw table. Enforce database permissions, RLS, or data-plane isolation alongside audits and export controls.

**Question 19 — lost events:** during a 45-minute outage with 30-minute source retention and no archive, data outside the retention window can be unrecoverable. Maintain raw Blob archives with sufficient retention, lag monitoring, and tested backfills.

**Question 20 — volume:** **691.2 GB/day** raw before compression, replication, and overhead, as computed in Section 19.2. Do not equate this directly with billable stored GB.

**Question 22 — unverified recovery:** if the pipeline stalled, KQL is inspecting stale data. Verify ingestion lag, source activity, synthetic probes, and App Insights/backend health before declaring 503s resolved.

### 25.3. Evaluation Rubric

| Criterion | Passing Standard |
|---|---|
| **Data accuracy** | Distinguishes event time vs. ingestion time, request vs. span grain |
| **KQL accuracy** | Time `where`, `summarize`, `bin`, p95, `dynamic`, `join` |
| **Statistical rigor** | Denominators in error rates, 429 separated from 5xx, understands sampling |
| **Operational rigor** | Checks pipeline freshness, ingestion failures, and query health |
| **Security rigor** | Zero PII/tokens in logs, data-plane roles/RLS, governed retention |
| **Performance rigor** | Early time filters/projection, avoids unbounded cardinality/expands/joins |
| **Evidence rigor** | Corroborates multiple sources, avoids equating correlation with causation |
| **Financial rigor** | Calculates raw volume and weighs compute/storage/ingestion costs |

## 26. Azure Data Explorer Deployment and Operations Checklist

### 26.1. Before Choosing ADX

- [ ] Does the problem truly need large-scale log/telemetry analytics rather than existing Log Analytics/App Insights?
- [ ] Identified data sources, peak ingest rates, schemas, retention, and query SLOs.
- [ ] Defined UTC event time, ingestion time, `EventId`/`TraceId`, route templates, and schema versions.
- [ ] Classified data, PII/secrets, export policies, and retention rules.
- [ ] Selected cluster SKU, capacity, region, and networking matching needs and budget.
- [ ] Distinguished ADX database query endpoint from ingestion endpoint.
- [ ] Assigned owners for pipelines, KQL dashboards, Azure resources, and data quality.
- [ ] Defined raw source retention/backfill for recovering lost data.

### 26.2. When Designing Pipelines

- [ ] Event Hubs/Blob/SDK connectors use least-privilege identities and permissions.
- [ ] Ingestion mappings match JSON/CSV/Parquet source payloads.
- [ ] Validations cover timestamps, durations, statuses, trace IDs, and unknown fields.
- [ ] Monitored connector failures, ingestion lag, backpressure, and raw backlogs.
- [ ] Tested replay/backfills, deduplication assumptions, and dead-letter/quarantine strategies.
- [ ] Reviewed table retention and caching policies against compliance, SLOs, and cost.
- [ ] Configured Private Endpoints, networking, DNS, and TLS where required.
- [ ] Zero raw PII, tokens, or credentials ingested into telemetry.

### 26.3. When Writing Production KQL

- [ ] Filter time windows early using the exact `Timestamp`/`TimeGenerated` column from schema.
- [ ] Filter environment, service, and operation before `summarize` or `join`.
- [ ] Project only required columns, avoiding returning huge dynamic payloads unnecessarily.
- [ ] Confirm grain: does one row represent an HTTP request, span, dependency, or log line?
- [ ] Include denominators in error rates and separate HTTP 5xx, 4xx, and 429 cleanly.
- [ ] Compute p95/p99 percentiles over raw observations rather than averaging percentiles.
- [ ] Verify `join`s do not multiply event counts unintentionally and dimension keys are unique.
- [ ] Constrain cardinality and memory in `mv-expand` and `parse_json`.
- [ ] Treat `dcount` and anomaly scores as approximate/statistical measures.
- [ ] Even when using `render`, ensure queries output clean tables usable by SDKs/automation.
- [ ] Validate against synthetic/golden datasets and benchmark resource consumption.

### 26.4. When Publishing Dashboards and Alerts

- [ ] Display **ingestion freshness/lag** right alongside request/error charts.
- [ ] Chart requests, 5xx, 429, and p95/p99 by service, region, and operation.
- [ ] Every alert has an owner, severity, window, minimum traffic threshold, and runbook.
- [ ] Queries never scan full retention unnecessarily on frequent refreshes.
- [ ] Enforce reader/admin roles and RLS where needed—never rely solely on UI filters for tenant isolation.
- [ ] Data exports are controlled and diagnostics store zero secrets.
- [ ] Dashboards and queries are versioned, reviewed, and rollback-ready.
- [ ] Budget alerts and query/compute capacities are tracked.

### 26.5. During Incidents

- [ ] Confirm exact cluster, database, table, and UTC time window.
- [ ] Check ingestion pipeline health and last event time before declaring "zero errors."
- [ ] Verify actual schemas and data types.
- [ ] Analyze error volume, rate, and p95 across regions, operations, and deployments.
- [ ] Drill down by `TraceId` without deduplicating away spans.
- [ ] Check dependencies, networking, databases, and application logs independently.
- [ ] If queries crawl, apply early filters/projections and inspect joins, expands, and cardinality.
- [ ] If data is missing, check ingestion failures, Event Hubs retention, and backfill plans.
- [ ] After rollbacks/recovery, verify freshness, SLOs, and business correctness.
- [ ] Document evidence, root cause, and preventive actions.

## 27. Lab Cleanup and Resource Cost Governance

`datatable` creates no persistent tables, so practicing KQL with inline synthetic data **requires zero Azure resource cleanup**. If you provisioned a lab ADX cluster, Event Hubs namespace, Blob storage, databases/tables, or Private Endpoints, costs continue accruing after the session.

### 27.1. Before Deleting

1. Confirm subscription, resource group, and resource ownership.
2. Inventory lab resources (ADX cluster, databases, ingestion connectors, Event Hubs, Blob, network/DNS, monitoring).
3. Check retention/backup policies; never delete real audit or security events.
4. Confirm no downstream dashboards, alerts, or other teams depend on the cluster/database.
5. On shared ADX clusters, **never delete the entire cluster or resource group** just because you created a test table.
6. Stop lab producers and connectors cleanly, ensuring no scheduled jobs remain active.
7. Delete only approved lab resources; verify remaining spend in Azure Cost Management.

**Read-only** Azure CLI commands to verify scope:

~~~bash
az account show --query "{id:id,name:name,tenantId:tenantId}" -o table

az resource list \
  --resource-group "<approved-lab-resource-group>" \
  --output table
~~~

**Never run** `az group delete` on a resource group without full inventory and approval. Deleting an ADX database, table, or cluster can destroy other teams' dashboards, data retention, and compliance evidence. This is an analytics lab—you do not need destructive commands to learn KQL.

## 28. References and Key Takeaways

Technical documentation to consult during implementation, especially as Azure Data Explorer, SDKs, RBAC, and networking evolve across versions and tiers:

- [Azure Data Explorer documentation](https://learn.microsoft.com/azure/data-explorer/) — cluster overview, ingestion, administration, and operations.
- [Azure Data Explorer overview](https://learn.microsoft.com/azure/data-explorer/data-explorer-overview) — purpose and architecture.
- [Kusto Query Language documentation](https://learn.microsoft.com/kusto/query/) — operators, data types, functions, and query semantics.
- [`summarize` operator](https://learn.microsoft.com/kusto/query/summarize-operator) — aggregations by dimensions.
- [`join` operator](https://learn.microsoft.com/kusto/query/join-operator) — join kinds and strategy options.
- [`make-series` operator](https://learn.microsoft.com/kusto/query/make-series-operator) — time series.
- [`series_decompose_anomalies()`](https://learn.microsoft.com/kusto/query/series-decompose-anomalies-function) — anomaly detection.
- [KQL Python client SDK](https://learn.microsoft.com/azure/data-explorer/python-query-data) — authentication and query execution.

**Key takeaways to remember:**

1. **ADX is an analytics platform for events, logs, and telemetry**, not a replacement for transactional databases or message brokers.
2. **ADX and Azure Monitor Logs both speak KQL**, yet schemas, permissions, ingestion, query endpoints, and billing differ.
3. **Good schemas drive good queries:** UTC event times, typed dimensions, statuses, durations, trace/span IDs, and `dynamic` reserved for flexible attributes.
4. **Ingestion is a governable pipeline:** Event Hubs/Blob/SDKs, mappings, validation, late events, replay, and ingestion lag.
5. **KQL's strength is its pipeline flow:** `where` → `project/extend` → `summarize` → `join/make-series` → chart or drill-down.
6. **Error rates and p95/p99 demand sound statistics:** separate 5xx, 429, and 4xx, check sample sizes, sampling, and duplicate events.
7. **Correlation is not causality:** trace IDs establish relationships; confirming root cause requires deployment, dependency, network, and business evidence.
8. **Optimize systematically:** filter time early, project minimal columns, control cardinality, bound joins/expands, and apply materialization/caching thoughtfully.
9. **Secure at the data plane:** Entra ID, Kusto roles, RLS, and private networking—never rely on UI filters or Azure Contributor as data authorization.
10. **Healthy dashboards require fresh data:** a query returning 200 does not prove ingestion is running.
11. **Operations must plan for failure:** clear monitoring, retention, backfills, backups/exports, IaC, and cost tracking.
12. **Let sources and requirements guide decisions:** if App Insights/Log Analytics already meets SLOs and logging needs, do not spin up ADX without clear business value.

A KQL log and telemetry analytics platform is truly valuable only when it can answer **what happened, when it happened, across which services and users/regions, whether data is complete and fresh, whether conclusions rest on independent evidence, and how costs and access are governed**.

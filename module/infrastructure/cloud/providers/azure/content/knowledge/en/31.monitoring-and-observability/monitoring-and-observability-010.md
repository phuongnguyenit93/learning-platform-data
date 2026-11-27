# Dashboards, Azure Monitor Workbooks, and Operational Reports

In the **CLOUD_PROVIDERS_AZURE** module, learners explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; learning how to deploy, monitor, protect, and control the cost of application architectures on Azure. Part of the **Monitoring and Observability** chapter, this lesson focuses on the three primary deliverables of observability operations: **monitoring dashboards**, **interactive Azure Monitor Workbooks**, and **operational reports with context, owners, and action items**.

Running example: a team operates an ordering platform consisting of Java applications on Azure App Service or AKS, Azure SQL Database, Azure Service Bus, and Key Vault. During an on-call shift, they need to know immediately **whether orders are being processed, where failures are occurring, and what to do**. Meanwhile, leadership wants a weekly summary: SLO attainment, customer-impacting incidents, cost, and remediation actions. A single chart page cannot serve both purposes.

After completing this lesson, you will be able to:

- Distinguish **Azure portal dashboards**, **Azure Monitor Workbooks**, **Azure Managed Grafana**, **Power BI**, and **operational reports** by purpose.
- Choose data sources—**Azure Monitor Metrics, Log Analytics/KQL, Application Insights, resource diagnostics, Activity Log, and Azure Resource Graph**—with the right semantics.
- Design metrics for **SLI/SLO, error rate, availability, p95/p99 latency, saturation, freshness, queue backlog, and cost** with clear denominators, time windows, and owners.
- Build Workbooks with **time range and resource/subscription/environment parameters**, charts, drill-down tables, investigation links, and helpful annotations.
- Write **time-bounded, cost-efficient, and data-safe KQL queries**; distinguish workspace-based schemas from legacy tables.
- Build **daily/weekly operational reports, incident reviews, and executive summaries** using the same metric definitions as dashboards.
- Manage Workbooks under **RBAC/IaC/version control**, design dedicated alerts/action groups, and avoid confusing dashboards with alerting systems.
- Validate data and query results, and establish runbooks for common failures: empty panels, delayed data, cost anomalies, or false "green" dashboards.

## 1. What Problems Do Dashboards, Workbooks, and Operational Reports Solve?

A system can emit millions of telemetry points per day and still fail to help on-call engineers if there is no **operational picture organized around questions**.

```text
Java applications + Azure resources
             |
      metrics / logs / traces / events
             |
             v
 Azure Monitor / Log Analytics / Application Insights
             |
      Query + aggregation + context
             |
       +-----+---------------+-----------------+
       |                     |                 |
       v                     v                 v
   Dashboard              Workbook        Report / Review
   "Now" view             "Investigate"   "What happened,
   service health         interactive     why, what next?"
       |                     |                 |
       +-----------+---------+-----------------+
                   |
             Owner / action
                   |
        Incident response + learning
```

### 1.1. Three Output Layers

| Output | Primary Question | Audience | Cadence | Examples |
|---|---|---|---|---|
| **Operational Dashboard** | *Is there an issue requiring immediate action?* | On-call, SRE, NOC | Minutes/hours | Error rate, p95 latency, queue backlog, alert status |
| **Azure Monitor Workbook** | *Which component is failing, since when, and on which resource?* | Engineers, incident commanders, platform | Interactive investigation | Select cluster/namespace, KQL drill-down, resource table |
| **Operational Report** | *Did we meet targets, what caused issues, and who fixes them?* | Engineering managers, product, security, FinOps | Daily/weekly/monthly | 99.94% SLO achieved, 2 incidents, budget, action items |

A Workbook can serve as an on-call shift dashboard, and an Azure portal dashboard can pin selected Workbook visualizations. However, you should **design around the user's job**, rather than forcing every chart and report onto a single page.

### 1.2. The "Signal-to-Decision" Principle

Every critical panel should answer:

1. **What** is being measured and **which objective** does it serve?
2. **Which source** does the data come from, and which service/region does it belong to?
3. What are the time range, time zone, aggregation, and units?
4. What constitutes **normal / warning / critical** against an SLO or capacity limit?
5. If an anomaly occurs, **where do you drill down** and **what is the runbook/owner**?
6. If data disappears, does the panel clearly display **no data**?

A "CPU 80%" chart is insufficient if the workload consistently runs healthy at 80% CPU. Conversely, showing 0 errors when log ingestion has stopped can mislead operators.

## 2. Where Azure Tools Fit in the Observability Architecture

| Tool | Characteristics | Best Used For | What Not to Assume |
|---|---|---|---|
| **Azure portal Dashboard** | Tiles pinned/composed from supported views, with sharing/management controls | Concise wallboards and health overviews | Being an alert engine or immutable historical report |
| **Azure Monitor Workbook** | Interactive canvas combining parameters, text, queries, charts, tables, and links | Multi-resource investigation and context-aware dashboards | Having the exact same features/UX as Power BI or Grafana |
| **Azure Monitor Metrics** | Low-latency time-series platform/custom metrics by resource/namespace | Latency, CPU, request rate, saturation at low latency | Every log automatically being queryable like a metric |
| **Log Analytics** | KQL over logs in workspaces/tables containing ingested data | Error details, joins, traces, investigation, and trends | Identical table names across all workspaces/schemas |
| **Application Insights** | App telemetry: requests, dependencies, exceptions, traces | Java API performance and distributed traces | Sampling never skewing raw-count-based SLIs |
| **Azure Managed Grafana** | Dashboards built across multiple data sources via connectors | Multi-series/multi-team views, Kubernetes/Prometheus, and Grafana interactivity | Automatically granting all Azure RBAC permissions |
| **Power BI** | Analytical/business reporting models, sharing, and governance | Executive reporting and multi-period trends | Default live operational alerting or near-real-time querying |
| **Azure Monitor Alerts** | Rules, evaluation schedules, action groups, and automated responses | Incident notification with SLA/owner | Requiring someone to open a dashboard to fire an alert |

### 2.1. A "Dashboard" Is Not an Alerting System

A dashboard only displays data when someone looks at it. **Alert rules** evaluate signals on a schedule/query/metric basis with thresholds, action groups, and routing. When a metric breaches its threshold, the **incident system** creates a ticket/page; the dashboard helps determine impact and investigate. Never rely on red colors in a Workbook as your sole mechanism for waking up on-call engineers.

### 2.2. A "Workbook" Is Not a Telemetry Store

A Workbook **stores visualization definitions, queries, parameters, and layout**. The underlying data resides in Log Analytics, Azure Monitor Metrics, Resource Graph, or supported sources. Once log retention expires, a Workbook saved a year ago **does not retain last year's data on its own**.

### 2.3. A "Report" Is Not an Ad-Hoc Dashboard Screenshot

A report has a **data cutoff period**, an owner/team, KPI definitions, source references, caveats for incomplete data, and assigned action items. A dashboard screenshot lacking timestamps, query/filter definitions, and sample completeness is inadequate for audits.

## 3. Data Flow from Java Applications and Azure Resources

A reference stack:

```text
Java API / Spring Boot (App Service or AKS)
       |
       +--> OpenTelemetry / Application Insights instrumentation
       |       requests, exceptions, dependencies, traces
       |
       +--> application structured logs
       |
Azure SQL / Service Bus / Key Vault / App Service / AKS
       |
       +--> Azure Monitor platform metrics
       +--> Diagnostic settings -> Log Analytics / other destinations
       +--> Activity Log (control-plane events)
       |
       v
Azure Monitor / Log Analytics workspaces
       |
       +--> Metrics Explorer -> chart / alert
       +--> Logs (KQL) -> Workbook / scheduled query alert
       +--> Workbooks -> interactive incident view
       +--> dashboards -> operations overview
       |
       v
Daily/weekly reporting pipeline (approved query/export)
       |
       v
Operations review + incident action tracker
```

### 3.1. Not All Telemetry Flows into the Same Workspace Automatically

Each Azure resource has different **metric namespaces and diagnostic settings**. Some logs route into **resource-specific tables**, others into **AzureDiagnostics** (legacy), while Application Insights uses dedicated tables/schemas depending on whether it is workspace-based or classic. If a KQL query returns no results, check **resource scope, table name, ingestion, and retention**—do not assume the resource produced zero errors.

### 3.2. Metrics and Logs Have Different Freshness

- **Metrics:** typically optimized for numerical time series and alerting/charting with predefined aggregations.
- **Logs:** useful for event-level detail, correlation, filtering, and joins; ingestion latency depends on the source/pipeline and may involve sampling/transformations.
- **Traces:** show request → dependency → exception relationships; sampling may omit granular request details.
- **Activity Log:** records management-plane changes and service health/control events, not order-processing logs.

Do not set a "no errors in the last 5 minutes" rule on logs without monitoring **ingestion freshness**, because zero events may mean either zero traffic or a broken telemetry pipeline.

### 3.3. What Telemetry Should Be Enabled in Java?

A Java API should emit:

- Request count, duration, result, route template, and HTTP status.
- Dependency timing/duration/errors (SQL, Service Bus, Key Vault) as supported by instrumentation.
- Exceptions with **redacted** stack contexts.
- Trace/span IDs to correlate logs; exclude passwords, access tokens, and customer PII from attributes.
- Business metrics such as **orders accepted, payment confirmed, and backlog age** with clearly defined units.

When using an OpenTelemetry/Java agent or the Azure Monitor OpenTelemetry distribution, verify **versions, exporters, sampling, and SDK compatibility**. Never treat "SDK initialized without error" as proof that all telemetry types are arriving in panels; validate end-to-end against a real workspace.

## 4. From Operational Objectives to SLIs/SLOs

A good dashboard starts with **what customers experience**, not with "which CPU metrics happen to be available."

### 4.1. What Is an SLI?

A **Service-Level Indicator (SLI)** measures actual service quality, for example:

- **Availability SLI:** proportion of eligible requests completed successfully.
- **Latency SLI:** proportion of requests served within a latency threshold.
- **Freshness SLI:** proportion of orders processed/recorded before a deadline.
- **Correctness SLI:** proportion of transactions requiring no manual reconciliation/rollback.

A **Service-Level Objective (SLO)** sets the target for an SLI over a time window. For example: "99.9% of eligible requests succeed over a rolling 30-day window" or "99% of orders complete within 2 minutes."

### 4.2. Availability Is Not "HTTP 200 on the Health Endpoint"

For example, an API may return HTTP 200 on `/health` while checkout consistently returns 500 or order processing stalls. Health probe availability is a **component** signal and cannot replace an **end-user request SLI**. Clarify:

- Which requests are **eligible** in the denominator? Are client bad requests (4xx) excluded?
- What counts as failures: 5xx, timeouts, business errors, 429 due to overload?
- Can you distinguish an API receiving zero traffic, a blackhole, or lost telemetry?
- Is the time window a rolling 1h/24h/30d window or a calendar month?

### 4.3. Core Formulas

Given `eligibleRequests` as total eligible requests and `goodRequests` as those meeting the contract:

```text
Availability (%) = 100 * goodRequests / eligibleRequests
Error rate (%)   = 100 * badRequests  / eligibleRequests
```

Suppose a day has 100,000 eligible requests and 99,920 meet the criteria: availability is **99.92%**. If the SLO is **99.9%**, that single day meets the SLO; however, you cannot conclude the rolling 30-day SLO is met without checking all 30 days.

### 4.4. Percentile Latency

`p95 = 800 ms` means **approximately 95% of samples took no longer than 800 ms** in the measured set/window—not "95% of requests are faster than an average of 800 ms." **Never average per-node p95 values** and call that service-wide p95; compute percentiles across the combined distribution/samples or appropriate metric aggregation.

### 4.5. Error Budget

A 99.9% SLO permits roughly **0.1% bad events** within the defined denominator. For an always-available time-based SLO over a 30-day month, 0.1% of time equals **43.2 minutes**—but that is a *time-based budget*; do not apply that minute figure directly to a request-based SLO without assuming uniform traffic distribution.

### 4.6. Owner-Backed KPI Dictionary

| KPI | Minimum Definition | Purpose | Owner |
|---|---|---|---|
| Availability | Good/eligible requests; 30-day window | SLO | API owner/SRE |
| API p95 | Percentile latency; 5 min/1 hr | User experience | Backend |
| API error rate | 5xx + timeouts per contract, divided by eligible | Alert | On-call |
| Queue oldest message age | Wait time of oldest message per supported telemetry source | Backlog | Worker owner |
| Database connections | Active/limit; unit/count | Saturation | Data owner |
| Job completion | Completed jobs / eligible jobs | Business workflow | Operations |
| Telemetry freshness | Now - last confirmed event ingestion | Data quality | Platform |
| Cost per transaction | Allocated cost / completed transactions | FinOps | Service owner |

Document the source, query, latency, retention, units, excluded cases, and owner **before** building panels. Whenever a definition changes, version the dashboard/report.

## 5. Selecting Signals Using RED, USE, and Golden Signals

### 5.1. RED for Request/Response Services

**RED = Rate, Errors, Duration.**

| Signal | Example | Goal |
|---|---|---|
| Rate | Requests/second of the Java API | Detect traffic loss/bursts |
| Errors | 5xx ratio/timeout rate | User impact |
| Duration | p50/p95/p99 latency | Slowdowns and tail latency |

Do not just pick metrics that are easy to display; for synchronous workloads, RED is a useful starting point.

### 5.2. USE for Resources

**USE = Utilization, Saturation, Errors.** Examples:

| Component | Utilization | Saturation | Errors |
|---|---|---|---|
| AKS node | CPU/memory utilization | CPU throttling, pod scheduling pressure | Node NotReady, OOMKill |
| App Service Plan | CPU/memory per supported metric | Queue/concurrent requests per appropriate source | App restarts, HTTP errors |
| Azure SQL | CPU/DTU/vCore/memory per tier | Connections, waits, storage pressure | Connection failures, deadlocks |
| Service Bus | Message/throughput/capacity metrics | Backlog, active messages, age per instrumentation | Dead-letter, send/receive failures |

A service with low CPU can still fail because of database locks or stopped queue consumers. **Saturation and user-impact SLIs** should sit alongside resource utilization.

### 5.3. "Business" Signals

In an ordering system, "API request succeeded" is not enough if orders are never delivered to workers. Add:

```text
orders_accepted
orders_persisted
orders_published_to_queue
orders_completed
orders_failed
oldest_unprocessed_order_age
```

These are **sample metric/event names**, not built-in Azure metrics. Implement them via OpenTelemetry/custom metrics/logs with appropriate dimension cardinality and permissions. Dashboards should show the **order journey**, not just container health.

## 6. Designing an Operations Overview Dashboard

### 6.1. Recommended Layout Sketch

```text
+---------------------------------------------------------------------+
| ORDERS PLATFORM — PROD / Southeast Asia — Last 60 min              |
| Owner: Orders SRE | Last telemetry: 11:25 UTC | Runbook | On-call  |
+--------------------+-------------------+----------------------------+
| Availability SLI   | Failed orders     | Critical open incidents    |
| 99.94%             | 87                | 1                          |
+--------------------+-------------------+----------------------------+
| Requests/s                    | API p95 & p99 latency                |
| Errors / good traffic         | Target p95 < 800ms                   |
+-------------------------------+-------------------------------------+
| Queue backlog / oldest age    | Worker throughput and failures       |
+-------------------------------+-------------------------------------+
| SQL saturation / connections  | AKS/App Service capacity            |
+-------------------------------+-------------------------------------+
| Deployment annotations        | Data freshness / missing telemetry  |
+-------------------------------+-------------------------------------+
| Drill-down: Workbook / Traces / Logs / Incident board / Cost       |
+---------------------------------------------------------------------+
```

This is an **illustrative layout**, not an Azure Portal screenshot. Adapt it to screen size and audience: wallboards only need top-line signals and links; investigative Workbooks contain more detailed tables.

### 6.2. The First Row Must Answer "Who Needs to Be Paged?"

Prioritize **business SLIs, critical incidents, and data freshness**, followed by dependency indicators. Do not let 20 CPU charts occupy half the screen before showing the error rate. Every panel should include a short title, units, target line, and runbook link if available.

### 6.3. Meaningful Colors

- **Normal:** target met, data is fresh.
- **Warning:** elevated risk, requires observation/triage.
- **Critical:** SLO/error budget breached or user impact detected.
- **No data / unknown:** never color green or coerce to 0.

Use **text labels, icons, or explicit thresholds** alongside color so viewers do not rely solely on color perception; keep accessibility in mind.

### 6.4. Never Hide Context

A chart showing "p95 = 1,200" must state **ms**, **range last 1h**, **environment production**, **region**, **aggregation**, and **last refresh**. Avoid mixing dev and prod data via empty filters or mixing time zones across ranges.

## 7. Azure Monitor Metrics Explorer and Portal Dashboards

### 7.1. When to Use Metrics Explorer

Use it to inspect platform metrics for one or more Azure resources where supported, choosing namespace/metric, aggregation, time range, dimension splitting, and chart type. Metrics Explorer lets you quickly build a visualization and **pin** it to an Azure portal dashboard when supported by the current feature set.

### 7.2. Portal Workflow

1. Open **Azure Monitor → Metrics**, or open a resource → **Monitoring → Metrics**.
2. Select the right subscription/resource scope, **metric namespace**, and metric name.
3. Choose the **Avg/Sum/Count/Min/Max** aggregation based on the metric's semantics—do not default to Avg for a counter that requires Sum.
4. Set a time range and granularity aligned with collection frequency.
5. Use dimensions to split by instance/region/status if the metric supports them.
6. Verify the chart renders data with the correct units.
7. Pin the visualization to an **Azure portal dashboard** if the UI/metric supports it.
8. Share the dashboard with operations teams using RBAC and underlying data-source permissions.

### 7.3. How Does Sum Differ from Average?

If a metric represents request counts per interval, **Sum** across multiple time bins represents total requests; **Average** represents the mean of collected samples. For CPU percentage, **Average** is usually more informative than Sum; however, p95 latency cannot be computed by taking the Average of percentiles. Read the **metric definition/unit/supported aggregations** before using it.

### 7.4. Resource-Specific Schemas

One resource may expose a metric named `Requests`, while another exposes `TotalRequests` or uses a different namespace. **Do not hard-code metric names from memory** across services. Use Portal Metrics Explorer or CLI `az monitor metrics list-definitions` to retrieve exact names from the monitored resource.

### 7.5. Dashboard Sharing

Personal and shared dashboards differ in storage and access control. Shared dashboards can be managed as Azure resources subject to user access controls; beyond read access to the dashboard itself, viewers **also need read permissions on the Azure resources/queries behind the tiles**. Seeing the layout does not guarantee seeing the data.

## 8. What Is an Azure Monitor Workbook?

**Azure Monitor Workbooks** provide an interactive canvas to combine **guidance text, parameters, queries, charts, grids, metrics, and links** into a single operational investigation page. A Workbook is ideal when operators must navigate **environment → service → resource → time → error detail** instead of juggling a dozen disconnected browser tabs.

### 8.1. Common Building Blocks

| Block | Role | Example |
|---|---|---|
| **Text/Markdown** | Instructions, assumptions, runbook links | "Data source lag up to 5 minutes" |
| **Parameters** | Time range, resource, environment, region, service | Select `prod` and `last 1h` |
| **Metrics** | Azure Monitor metrics from permitted resources | CPU % by App Service Plan |
| **Logs queries** | KQL against Log Analytics/Application Insights | Request failures and p95 latency |
| **Resource Graph** | List/inspect resource metadata across permitted scopes | Map resource IDs to subscriptions |
| **Grid / chart / tiles** | Readable data presentation | Top 10 failing routes, trend over time |
| **Links / drill-down** | Navigate to trace details, Portal, or tickets | Link to Application Insights transaction search |
| **Conditional visibility/formatting** | Show relevant blocks based on parameters/results | Warning runbook shown when data is missing |

Capabilities of each data source, visualization, and parameter type depend on the **Azure Monitor Workbook editor/region/version**. Do not assume every tile can be pinned outside the Portal or that every chart type shares identical options.

### 8.2. How Does a Workbook Differ from a Dashboard Tile?

A Workbook supports a **multi-step investigative flow**: a time picker drives queries, a resource picker sets scope, and a top-errors grid drills down into details. A Portal dashboard suits a **fixed overview** with a small set of core signals. When both are needed, **pin or link to the Workbook** from the dashboard using supported features instead of copying 30 standalone queries onto a wallboard.

### 8.3. An Empty Workbook Is Not Always a Broken Workbook

Viewers may lack workspace read permissions, have selected the wrong resource or a time range with no telemetry, hit an incorrect KQL schema, or query before Log Analytics ingestion completes. Workbooks do not store telemetry. Therefore, the top of the page should display **data source status/freshness** and explicitly document required permissions.

## 9. Creating an Azure Monitor Workbook from the Portal

Example: building a Workbook named **Orders Platform — Operations & Troubleshooting**.

### 9.1. Creating the Workbook

1. Go to **Azure Portal → Monitor → Workbooks**, or open an Application Insights/Log Analytics resource → **Workbooks**.
2. Click **New** or choose an organization-approved template.
3. Add a **Text** block describing scope, SLOs, owner, runbook URL, and caveats.
4. Add a **Time range parameter** for the whole Workbook or individual steps.
5. Add **Resource/Subscription/Environment parameters**.
6. Add a Logs query retrieving request rate, error rate, and p95 from the right Application Insights/Log Analytics scope.
7. Select an appropriate **time chart** or **tiles/grid** visualization.
8. Add a top failing routes table with drill-down links to traces/exceptions.
9. Add SQL/Service Bus/AKS metrics targeting their respective resource scopes.
10. Preview across parameter combinations, checking no-data states and viewer permissions.
11. **Save/Save as** into a governed subscription/resource group/location and choose the sharing model.
12. Grant operator permissions and store the JSON template/version in a repository if your workflow supports it.

Menu names may change across Portal updates. These steps represent **design logic**, not a rigid pixel-by-pixel guide for every account.

### 9.2. Setting Workbook Metadata

An operable Workbook needs:

```text
Title       : Orders Platform — Operations & Troubleshooting
Environment : production
Owner       : orders-sre
Revision    : 2026-11-20.1
Data source : workspace-app-prod and selected Azure resources
Scope       : subscriptions/resource group IDs governed by team
Time zone   : UTC for queries; user-local rendering documented
SLO         : 99.9% availability / 30 days (example)
Runbook     : internal approved documentation link
Last review : date when queries and permissions were revalidated
```

This is a **descriptive template**, not a Workbooks API JSON object. **Workspace names and SLOs are examples only** and must be replaced with real sources.

### 9.3. Start with a Small Set of Useful Panels

Starting with **6–10 connected panels** is far easier to validate than 40 unowned panels. Separate **Overview**, **Requests & Latency**, **Dependencies**, **Queues & Data**, **Deployments & Changes**, and **Troubleshooting** using sections/text or supported editor layouts.

### 9.4. Saved Workbook vs. Template

A saved Workbook acts as a personal or shared dashboard. **Workbook templates** help standardize and reuse designs across teams and resources. Avoid editing a shared production Workbook directly during an incident without versioning/rollback; manage layouts and queries as code and review before deployment.

## 10. Parameters: The Key to an Interactive Workbook

### 10.1. Three Minimum Parameters

| Parameter | Suggested Type | Sample Values | Effect |
|---|---|---|---|
| `TimeRange` | Time range | Last 60 minutes | Synchronizes queries |
| `Environment` | Dropdown | dev, staging, prod | Filters logs/metric resources |
| `Resource` | Resource picker | App Insights resource or workspace | Targets the right data source |

You can add **Subscription**, **Region**, **Service**, **AKS cluster**, **Namespace**, **ErrorCode**, or **Application version**. Keep parameter counts and valid options bounded so the Workbook stays usable.

### 10.2. Distinguishing Resource Scope from KQL Filters

A resource picker selects data within scopes the query engine is permitted to read, whereas `Environment` can be a telemetry **dimension/column filter**. Never rely on `AppRoleName contains "prod"` as a security boundary; telemetry names can be misconfigured or spoofed. **Workspace/resource read access** must be enforced at the Azure IAM/data access layer.

### 10.3. Passing Parameters into Queries

The Workbook editor supports parameter reference syntax depending on data source and control type; conceptually:

```kusto
// Illustrates KQL using placeholders resolved by the Workbook editor.
AppRequests
| where TimeGenerated between (datetime({TimeRange:start})
                               .. datetime({TimeRange:end}))
| where AppRoleName == '{ServiceName}'
| summarize RequestCount=count()
    by bin(TimeGenerated, 5m)
```

**This illustrates parameter binding**, not a standalone KQL query you can paste directly into Log Analytics. In Workbooks, verify substitution syntax and **parameter/time-range data types** inside the editor (many queries can use the query step's **Time Range** setting rather than manually injecting datetime literals). Never interpolate arbitrary raw user input into KQL due to **query injection, escaping, and syntax errors**.

### 10.4. Use the UI Time Range When Possible

A less error-prone pattern is binding the query step's **Time range** configuration to the parameter so the editor applies the time scope; inside KQL you only write:

```kusto
AppRequests
| summarize Requests=count()
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

However, whenever a query step manages its own time range, verify it **does not accidentally scan full retention**; well-written KQL should still include an appropriate `TimeGenerated` bound, especially when run directly in Logs or by reporting schedules.

### 10.5. Time and Time Zones

KQL `TimeGenerated` is typically stored in **UTC**; the Portal may render charts in the browser's or user's configured time zone. Reports using Asia/Ho_Chi_Minh business dates must **convert explicitly at day boundaries**, rather than confusing local chart axis labels with UTC query filters.

### 10.6. Parameter Defaults Must Not Trigger Oversized Queries

Defaulting to `Last 1h`/`Last 24h` is much safer than `All time`. Opening a Workbook that automatically runs multiple queries over two years of logs can be slow and expensive. Start with a **narrow scope** and expand only during investigation.

## 11. KQL for Overview: Request Rate, Error Rate, and p95

The examples below assume **workspace-based Application Insights** with an **`AppRequests`** table in Log Analytics and columns `TimeGenerated`, `Success`, `DurationMs`, `AppRoleName`, and `ResultCode`. This is a common schema, **not** guaranteed on every Application Insights deployment. In Logs, verify table/column names with the schema explorer before copying.

### 11.1. 5-Minute Trend

```kusto
let startTime = ago(24h);
let endTime = now();
AppRequests
| where TimeGenerated between (startTime .. endTime)
| where AppRoleName == "orders-api"
| summarize
    Requests = count(),
    Failed = countif(Success == false),
    P50_ms = percentile(DurationMs, 50),
    P95_ms = percentile(DurationMs, 95),
    P99_ms = percentile(DurationMs, 99)
    by bin(TimeGenerated, 5m)
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * todouble(Failed) / Requests, real(null))
| order by TimeGenerated asc
| render timechart
```

**Important:** `Success` is an instrumentation telemetry flag and may not match your business definition of **good/eligible requests**. If your user SLO excludes client 4xx responses or if unrecorded timeouts occur, build a dedicated SLI query instead of treating `countif(Success == false)` as a permanent SLO policy.

### 11.2. KQL Notes

- `bin(TimeGenerated, 5m)` groups events into 5-minute buckets; buckets with no data may **not appear**.
- `percentile(DurationMs, 95)` computes over samples present in the table/window, which may be affected by **sampling/ingestion**.
- `render timechart` works in Logs; in a Workbook, you can also pick the chart visualization in the editor instead of locking chart rendering inside KQL.
- `real(null)` represents **no denominator**, avoiding reporting "0% error" when zero requests occurred.

### 11.3. Approximate Server-Error SLI

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| extend StatusCode = toint(ResultCode)
| where isnotnull(StatusCode)
| summarize
    Eligible = countif(StatusCode < 400 or StatusCode >= 500),
    Bad = countif(StatusCode >= 500)
| extend AvailabilityPct =
    iff(Eligible > 0,
        100.0 * (Eligible - Bad) / todouble(Eligible),
        real(null))
```

**This is an example SLI, not a universal standard**: 4xx requests are excluded, 429 remains a 4xx and would be excluded, and 408/timeouts without responses might not be counted; adjust to your service contract. If sampling is enabled, raw event counts may not reflect total requests; check unsampled metrics, `ItemCount`/weights, and calibrate against your instrumentation.

### 11.4. Top Failing Endpoints

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize
    Requests = count(),
    Failures = countif(Success == false),
    P95_ms = percentile(DurationMs, 95)
    by Name
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * todouble(Failures) / Requests, real(null))
| where Requests >= 20
| top 15 by Failures desc
```

`Name` should be a normalized **route template** (such as `POST /orders/{id}`) emitted by instrumentation, not raw URIs with millions of order IDs. Otherwise, cardinality explodes and top-N becomes diluted.

## 12. KQL for Dependencies, Exceptions, and Traces

### 12.1. Dependency Failures

```kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| where AppRoleName == "orders-api"
| summarize
    Calls = count(),
    Failed = countif(Success == false),
    P95_ms = percentile(DurationMs, 95)
    by Target, Type
| extend FailurePct =
    iff(Calls > 0, 100.0 * todouble(Failed) / Calls, real(null))
| order by Failed desc
```

This helps detect SQL connection errors or Key Vault latency. However, dependency telemetry may be missing if an SDK/client is uninstrumented; **absence of rows does not mean the dependency is healthy**.

### 12.2. Exception Trends

```kusto
AppExceptions
| where TimeGenerated >= ago(24h)
| where AppRoleName == "orders-api"
| summarize
    Occurrences = count(),
    FirstSeen = min(TimeGenerated),
    LastSeen = max(TimeGenerated)
    by ExceptionType, ProblemId
| top 20 by Occurrences desc
```

Avoid exposing **raw stack traces containing secrets/PII** in broadly shared Workbooks. Display exception type, problem ID, and a drill-down link restricted to authorized teams.

### 12.3. Tracing by OperationId

```kusto
let op = "trace-id-from-approved-incident";
union isfuzzy=true AppRequests, AppDependencies, AppTraces, AppExceptions
| where TimeGenerated >= ago(2h)
| where OperationId == op
| project TimeGenerated, Type, OperationId, AppRoleName,
          _ResourceId
| order by TimeGenerated asc
```

**This is a sketch query**: when `union`-ing multiple tables, schemas may differ; `Type` often reflects the table name in many union contexts, but you may need `withsource=SourceTable` to identify origin explicitly, and columns like `OperationId` might vary across table versions. Prefer writing:

```kusto
let op = "trace-id-from-approved-incident";
union isfuzzy=true withsource=SourceTable
    AppRequests, AppDependencies, AppTraces, AppExceptions
| where TimeGenerated >= ago(2h)
| where OperationId == op
| project TimeGenerated, SourceTable, OperationId,
          AppRoleName, _ResourceId
| order by TimeGenerated asc
```

If a trace ID does not appear, check sampling, cross-component correlation, resource scopes, and whether trace context was propagated. A trace missing spans does not prove the request never called that dependency.

### 12.4. Project Only Needed Columns

`project` only the columns you need; avoid `project *` over wide log tables. Workbook KQL queries may hit row/size limits imposed by the service/UI; use **summarize → top N → drill-down** rather than loading 100,000 raw exception rows into the browser.

## 13. KQL for Operational Business Metrics and Late-Arriving Data

### 13.1. Business Telemetry Must Have an Instrumented Source

If the application writes a custom table `OrderWorkflow_CL` (for example, ingested into Log Analytics), you can query:

```kusto
OrderWorkflow_CL
| where TimeGenerated >= ago(24h)
| summarize
    Accepted = countif(State_s == "ACCEPTED"),
    Completed = countif(State_s == "COMPLETED"),
    Failed = countif(State_s == "FAILED")
    by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
```

**`OrderWorkflow_CL` and `State_s` represent a hypothetical organization-defined custom schema**, not a built-in Azure Monitor table. If each state emits an event, `Accepted` and `Completed` in the same hour do not necessarily belong to the same cohort, so **do not divide Completed/Accepted directly and call it a conversion rate**. Computing a cohort completion SLI requires a business key, start time, cutoff/watermark, and deduplication.

### 13.2. Backlog and Oldest Message Age

Azure Service Bus provides platform metrics such as active/dead-letter message counts per supported namespace/entity/metric definitions. **Oldest-message age** may require custom telemetry or querying from the application/work queue rather than assuming a default built-in platform metric exists with that exact behavior. Distinguish:

```text
Backlog count = number of queued messages per metric snapshot
Oldest age    = now - enqueue timestamp of the oldest unprocessed work item
Drain rate    = messages processed/second per business logic
```

A dropping backlog count can result from **expired/dead-lettered messages** rather than successful processing; pair it with business completion/error signals.

### 13.3. Log Ingestion Freshness

For custom log sources that emit events steadily:

```kusto
OrderWorkflow_CL
| where TimeGenerated > ago(2h)
| summarize LastSeen=max(TimeGenerated), Records=count()
| extend
    LagMinutes = iff(isnotnull(LastSeen),
                     datetime_diff('minute', now(), LastSeen),
                     long(null))
```

Because `datetime_diff('minute', now(), LastSeen)` subtracts event time from current time, the result is positive when `LastSeen` is in the past. If a source has **legitimate idle periods**, do not alert merely on zero orders; use an independent **heartbeat** or pipeline freshness SLO.

### 13.4. Ingestion Time Differs from Event Time

`TimeGenerated` in Log Analytics can reflect the event timestamp supplied by the collector rather than when the record arrived in the workspace. KQL provides `ingestion_time()` under supported tables/conditions to assess ingestion latency, though ingestion metadata has specific characteristics and limits. Always **compare `event timestamp`, `ingestion time`, and `now()`** when diagnosing "delayed dashboards."

### 13.5. Never Conflate Missing Data with Zero

| Situation | Correct Interpretation |
|---|---|
| 1,000 requests, 0 failures | Evidence of zero errors in the source |
| No request rows | Either zero traffic or broken instrumentation/ingestion |
| No metric samples | Data unavailable, metric unsupported, or resource stopped |
| Rows exist but many columns are null | Schema/transform/dimension mismatch |
| Empty query result due to permissions | Never assume the system is healthy |

## 14. Azure Monitor Metrics: Querying and Combining with Logs

### 14.1. Discovering Metric Definitions via CLI

```bash
az login
az account set --subscription "<approved-subscription-id>"

RESOURCE_ID="<full-azure-resource-id>"

az monitor metrics list-definitions \
  --resource "$RESOURCE_ID" \
  --output table
```

After verifying metric name/namespace/aggregations, retrieve data:

```bash
METRIC_NAME="<name-listed-by-definition>"
az monitor metrics list \
  --resource "$RESOURCE_ID" \
  --metric "$METRIC_NAME" \
  --output json
```

Select `--interval`/`--aggregation`/`--dimension` according to your CLI version and metric definition. **Never invent metric names or assume every metric supports 1-minute granularity**.

### 14.2. Metrics Do Not Automatically Become KQL Tables

The Azure Monitor Metrics API/metric store and Log Analytics tables are **distinct data sources**. To query metrics with KQL, you must configure a pipeline to **export/ingest them into logs**, or use the Metrics data source directly in a Workbook. Seeing a CPU metric in Metrics Explorer does not mean Log Analytics automatically has a `CPU_CL` table.

### 14.3. Metrics or Logs in a Workbook?

- Use **Metrics** for CPU%, memory, capacity, transactions, and throttles as exposed by the resource.
- Use **Logs** for route breakdowns, exceptions, dependencies, user-impact events, joins, and triage.
- Use **Azure Resource Graph** to list governance context such as resource IDs/tags/locations where supported.
- Use **dashboard summaries** over pre-aggregated figures instead of running dozens of raw KQL queries.

Never split a `Requests` metric by customer email/customer ID if the service dimension does not support it or if doing so creates excessive cardinality and PII exposure.

## 15. Workbook Visualizations: Tiles, Charts, Grids, and Drill-Downs

### 15.1. Overview Tiles

A row of **tiles**:

```text
Availability: 99.94% / target 99.9%
Error rate:   0.06% (last 1h)
p95 latency:  740 ms / target 800 ms
Queue age:    91 sec / target 120 sec
Telemetry:    fresh (last 2 min)
```

**Numbers are illustrative only.** Attach units, time range, and source, and never mix a 30-day SLI with a 1-hour error rate without explicit labels.

### 15.2. Time Charts and Annotations

Plotting 5-minute p95 alongside deployment markers reveals **which release preceded a latency spike**. Deployment events can come from CI/CD logs, Application Insights/custom events, Activity Log, or release tracking records. **Do not assume portal dashboards automatically know every app's deployment schedule** unless you instrument or ingest it.

### 15.3. Top-Errors Grid

A grid should include:

| Route/Dependency | Request count | Failure count | Rate | p95 | Drill-down |
|---|---:|---:|---:|---:|---|
| POST /orders | 12,500 | 180 | 1.44% | 920 ms | Traces |
| GET /orders/{id} | 48,000 | 24 | 0.05% | 140 ms | Logs |
| ServiceBus send | 12,100 | 60 | 0.50% | 180 ms | Dependency events |

**Figures are illustrative.** With `top N`, always show sample size/denominator; a route with 1 error out of 1 request has a 100% rate, which has a very different absolute impact than 1,000 errors out of 100,000 requests.

### 15.4. Drilling from Summary to Incident

A clean investigative flow:

```text
Error rate increased
       |
       v
Select service, region and last 30 minutes
       |
       v
Top failing route/dependency table
       |
       v
Click request/operation ID
       |
       v
Application Insights transaction details / traces / logs
       |
       v
Incident runbook + mitigation action
```

Context-built links need **URL encoding, permission checks, and care to avoid leaking sensitive query fragments**. Never embed bearer tokens or secrets in URL query strings.

### 15.5. Limiting Panel and Query Counts

A Workbook that triggers 30 KQL queries concurrently on every parameter change can slow page loads and drive up query/ingestion-related costs. Group panels into tabs/sections/conditional visibility where supported by the editor, write efficient queries, set intentional cache/refresh policies, and test against real data volumes.

## 16. Azure Resource Graph in Workbooks: Inventory and Context

**Azure Resource Graph** queries metadata across Azure resources in subscriptions the principal can access, answering questions like "which cluster belongs to which team?", "how many Key Vaults are deployed?", or "which region is this resource in?". It is not a store for application requests, and **Resource Graph** KQL supports a different set of functions and limits than Log Analytics.

### 16.1. Illustrative Resource Graph Query

```kusto
Resources
| where type =~ 'microsoft.insights/components'
| project
    id,
    name,
    resourceGroup,
    subscriptionId,
    location,
    tags
| order by name asc
```

This targets the **Application Insights** resource type. It only returns resources the identity has access to that Resource Graph has indexed; **it does not prove telemetry exists in Log Analytics**. For queries such as "all production resources," filtering by tags like `tags.environment` is only reliable when organizational tagging governance is enforced.

### 16.2. Combining Inventory with Signals

A Workbook can use a resource picker or inventory query to list App Insights resources, then fetch metrics/logs from the selected resource. Never assume you can **directly join Resource Graph `Resources` with Log Analytics `AppRequests`** in one KQL query; they are **two separate data sources/query engines**. Use Workbook parameter plumbing and supported cross-resource features, and verify permissions on each source.

### 16.3. Owner/Criticality Using Tags

An ideal asset tag set:

```text
service=orders-api
environment=production
owner=orders-team
criticality=tier-1
costCenter=commerce
runbook=internal-link
```

Tags are **governance metadata**, not proof that a workload is healthy or its data is secure. Never put account numbers or PII in tags; restrict who can edit tags if dashboards use them for routing or ownership.

## 17. Sharing Workbooks and Azure RBAC

A Workbook is only useful when the right team can open it and view the **right data**, without holding higher privileges than necessary.

### 17.1. Three Permission Layers

| Layer | Required Permission | Common Mistake |
|---|---|---|
| **Workbook definition/resource** | Read access on the Workbook resource and shared scope | Assuming having the URL alone is enough |
| **Data source** | Read access to Application Insights/Log Analytics/metrics/resources per the data access model | Granting Viewer on the Workbook without workspace read access |
| **Edit/deploy Workbook** | Appropriate write permission on the Workbook/resource group | Giving all on-call engineers subscription Contributor just to tweak layout |

A user with read access to the Workbook but lacking **Log Analytics workspace permissions** will see the layout while query panels report access denied or no data. A user permitted to query logs does not automatically have permission to save changes to a shared Workbook.

### 17.2. Data Scope and Cross-Tenant/Cross-Subscription Access

If a Workbook exposes a multi-subscription parameter, include only approved sources. **Never treat a dropdown filter as a security boundary**: users can still modify queries or access underlying sources directly if IAM grants broad permissions. Enforce separation across **Azure tenants, data-source RBAC, resource contexts**, and sensitive log tables.

### 17.3. Application Insights / Log Analytics Data Access

Application Insights can use **workspace-based resources**, and Log Analytics supports workspace-context or resource-context access under supported mechanisms. Verify the exact access model, cross-resource query rules, and table-level/granular RBAC when required. Avoid granting a blanket Log Analytics Contributor role to everyone just to view errors; on-call engineers typically only need **read** access to logs for their assigned services.

### 17.4. Sharing Does Not Mean Automated Report Distribution

A shared Workbook has a stable URL for a team, but it does **not automatically email weekly reports** or persist point-in-time snapshots without a dedicated workflow. Distributing reports via Teams/email/Power BI/Storage requires separate governance and permissions.

### 17.5. Secrets and PII in Dashboards

Exclude:

- SQL connection strings, SAS tokens, bearer tokens, database credentials.
- Plaintext customer email/phone/order data unnecessary for on-call triage.
- Full exception payloads containing sensitive request headers.
- Internal resource connection metadata not intended for wider teams.

Default to **route templates, anonymized identifiers, sanitized error codes, and aggregate counts**. Detailed drill-downs require tighter access controls.

## 18. Storing Workbooks as Resources, Templates, and Version Control

A saved Workbook contains **query and layout definitions** that teams should treat as a configuration artifact. Under the Azure resource model, resource types such as **`Microsoft.Insights/workbooks`** and **`Microsoft.Insights/workbooktemplates`** exist in supported APIs/versions; exact creation and deployment capabilities depend on the tooling and API version.

### 18.1. What Belongs in the Repository

```text
workbook/
  # Reference repository structure illustration; not files created in this task.
  orders-operations.workbook.json
  orders-operations.parameters.json
  README-for-operators.md
  CHANGELOG.md
  tests/
    query-contracts.md
```

When saving exported Portal templates, **redact** sensitive resource IDs, tenant IDs, and query literals containing tokens/PII, and replace environment-specific scopes with parameters or IaC substitutions. Never commit secret values into JSON.

### 18.2. Pseudo-IaC, Not Executable Bicep

```yaml
# Logical deployment contract; not an ARM/Bicep/Terraform schema.
workbook:
  name: orders-platform-operations
  owner: orders-sre
  scope:
    subscription: non-production-or-production-approved
    resourceGroup: rg-observability
  source:
    applicationInsights: appinsights-orders-prod
    logAnalytics: law-orders-prod
  parameters:
    timeRange: last-1h
    environment: production
    service: orders-api
  sections:
    - service-health
    - latency-and-requests
    - dependencies
    - queues-and-database
    - deployments-and-incidents
  access:
    readers: operations-oncall
    editors: observability-maintainers
  review:
    queryTests: required
    approvedBy: service-owner
```

For real deployments, use the resource provider API and properly **versioned** serialized Workbook JSON containing the GUID/name, `serializedData`/template fields, and required metadata per provider documentation. Do not treat pseudo-YAML as deployable code.

### 18.3. Versioning a Workbook

Minimum workflow:

1. Export the working Workbook definition.
2. Edit KQL/layout in a separate branch.
3. Test queries against a **staging workspace or test resource** with fixtures.
4. Verify permissions, time ranges, no-data behavior, and cost.
5. Have the service owner or on-call team review.
6. Deploy as a new revision and verify results.
7. Retain a rollback path to the prior definition.

Changing one KQL filter can make a dashboard show "100% healthy" by silently dropping a service. Review **data semantics**, not just the JSON diff.

### 18.4. Standardizing Multiple Environments with Workbook Templates

A single template can serve dev/staging/prod via parameters. **Templates only succeed when telemetry schemas and metric definitions are standardized**; if teams use inconsistent table names, cloning a template produces empty panels. Maintain a shared **telemetry contract**: field names, units, service identity, trace IDs, and retention.

## 19. Optimizing Workbook KQL and Controlling Query Costs

### 19.1. Five Principles

1. Filter `TimeGenerated` **early** to reduce scan volume.
2. Filter by authorized service/resource/tenant before heavy `summarize` and `join` steps.
3. `project` only displayed columns and drop PII.
4. `summarize` then apply `top N` before returning large payloads.
5. Benchmark query duration, bytes scanned/cost, and accuracy across multiple time ranges.

### 19.2. Avoid Scanning Full Retention on Page Load

Do not write:

```kusto
AppRequests
| summarize count() by Name
```

in an auto-running Workbook without a time scope; it may scan far more data than needed. Write:

```kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where AppRoleName == "orders-api"
| summarize Requests=count() by Name
| top 20 by Requests desc
```

In a real Workbook, bind this window to the time range parameter rather than hardcoding 1 hour if users need multi-day or weekly views.

### 19.3. Joins and High Cardinality

A KQL `join` on raw customer IDs or operation IDs across tens of millions of records can be expensive, especially cross-workspace. Prefer pre-aggregating or filtering by service + time + operation ID first, and check join cardinality. Avoid using **raw user identifiers** as chart series due to PII risk and series explosion.

### 19.4. Query Execution and Workbooks Are Not Free

Saving a Workbook generally does not consume log-lake-scale storage, but every query run consumes query capacity and incurs **direct or indirect costs depending on Log Analytics plan, query features, retention, ingestion, and pricing**. Auto-refresh across heavy queries amplifies load. Use **query optimization and sensible refresh intervals**—never force 5-second auto-refresh on a 30-day trend chart.

### 19.5. Aggregations Must Preserve Semantics

To compute a full-day error rate, never take the **arithmetic mean of 24 hourly error rates** when hourly traffic varies. Use:

```text
Daily error rate =
  sum(failed eligible requests across hours)
  / sum(all eligible requests across hours)
```

Similarly, never average per-node p95 values. For overall SLOs, recompute from complete data or weighted distributions supported by your model.

## 20. Separating Dashboards, Alerts, and Reports into Distinct Lifecycles

### 20.1. One Signal Can Serve Three Purposes

Take `orders_completed`:

- **Dashboard:** completion count and 5-minute trend.
- **Alert:** completion rate drop over 15 minutes at sufficient volume, evaluated by a tested rule.
- **Weekly report:** completed/accepted by cohort, reconciled against the source ledger and business SLA.

Sharing a metric name does not mean sharing the same **time window, aggregation, or denominator**.

### 20.2. Alert Rules Require Dedicated Design

| Alert Component | Example |
|---|---|
| Signal | 5xx error rate for orders-api |
| Window | Rolling 10 minutes |
| Minimum volume | At least 100 eligible requests in window |
| Threshold | Error rate > 2% |
| Evaluation | Every 5 minutes per alert rule capability |
| Severity | Sev2 if user-impacting; align with policy |
| Action | Action group → incident routing/on-call |
| Suppression | Audited maintenance/scheduled mute |
| Owner | Orders SRE |
| Runbook | Link to Workbook "Errors" tab |

This configuration is **illustrative** and must be calibrated to your SLO and traffic volume. "Choosing a 2% threshold" is not an Azure Monitor default.

### 20.3. Missing-Data Alerts

Having zero order logs for 15 minutes might mean low traffic or stalled ingestion. Emit heartbeats from workers/ingestion pipelines and alert on **data availability/freshness** so empty panels do not stay green. Metric alerts and log alerts handle **no data**, "fired/resolved" state, and query evaluation differently; test them by simulating source loss.

### 20.4. Action Groups and Recipients

Azure Monitor action groups can notify recipients or invoke supported endpoints/workflows, but they **do not replace an incident management system by default**. Ensure:

- Correct owner/on-call rotation and severity mapping.
- Paging-storm protection via deduplication/suppression policies.
- Alert payloads containing service, environment, region, symptom, and chart/runbook links.
- Escalation if the owner does not acknowledge.
- Post-incident feedback loops to tune thresholds.

### 20.5. Dashboards Do Not Replace Service Health

During regional or platform-wide outages, combine application SLIs with **Azure Resource Health/Service Health** and official advisories. A normal CPU chart on one resource does not prove every dependent Azure service is healthy.

## 21. Building Daily Operational Reports

### 21.1. Goals

A daily handover report supports shift transitions by answering:

- Did the platform breach any SLO or suffer an incident in the past 24 hours?
- How many users were affected, over what timeframe, and on which services?
- Which alerts/tickets remain open?
- Were there notable deployment, capacity, or traffic changes?
- Are there resource cost anomalies or upcoming quota/certificate/secret expirations?
- What must the next shift do, who owns each task, and by what deadline?

### 21.2. Concise Template

```markdown
# Daily Operations Handover — Orders Platform

**Period:** 2026-11-19 00:00–23:59 Asia/Ho_Chi_Minh
**Prepared at:** 2026-11-20 08:30 +07:00
**Telemetry cutoff:** 2026-11-20 08:15 +07:00
**Owner:** Orders on-call
**Sources:** App Insights, Log Analytics, Azure Monitor, incidents

## Health and SLO
- Availability (24h): 99.94% (target 99.9%, example)
- API p95: 720 ms (target 800 ms, example)
- Failed orders: 87 (source reconciled: pending)
- Critical active incidents: 1

## Significant events
| Time | Event | Customer impact | Owner |
|---|---|---|---|
| 14:12 | SQL connection errors after deployment | Checkout delay | API lead |

## Outstanding risks
- Queue backlog age peaked at 4m; watch worker scaling.
- Nightly order reconciliation not yet finalized.

## Actions for next shift
- [ ] Validate SQL connection pool rollback — API lead — 10:00
- [ ] Reconcile 87 failed orders — Data ops — 12:00
```

**All figures and timestamps in this template are illustrative.** Never send this sample as real operational data. Always record sources, queries/windows, late-data caveats, and reviewers.

### 21.3. Daily "Snapshots" Differ from Live Workbooks

A handover report must **close its time window**: 00:00–23:59 in the agreed time zone, with a cutoff to account for late logs. A live Workbook filtered to "last 24 hours" changes every time it is opened; never use a live URL as an immutable record when audits require a snapshot.

### 21.4. Incomplete Data

If telemetry ingestion lags or workers are backfilling, state so explicitly:

```text
Reconciliation status: PRELIMINARY
Latest source watermark: 2026-11-19 23:40 +07:00
Missing data window: 20 minutes
Expected finalization: after source backfill
```

Never report 0 failed orders for a window that has not finished ingesting. When numbers are later restated, save a **report revision and reason for change**.

## 22. Weekly and Monthly Operational Reports

### 22.1. Information Categories

| Category | Metrics | Decision Question |
|---|---|---|
| Reliability | SLO, error budget consumed, incident minutes | Should feature rollouts slow down to stabilize? |
| Performance | p95/p99 latency, top slow dependencies | Is SQL optimization or scaling needed? |
| Capacity | CPU/memory, queue backlog, DB utilization | Scaling and quota forecasting |
| Changes | Releases, config drift, deployment failures | Is the release process safe? |
| Security | High-severity alerts, cert expiry, access anomalies | Are there unmitigated risks? |
| Cost | Budget variance, cost/service and cost/transaction | Where to optimize first? |
| Delivery/operations | Open action items, overdue incidents, toil | Who needs to do what next week? |

### 22.2. Select Only Actionable KPIs

A 100-metric table overwhelms readers. A weekly report should focus on **5–10 core KPIs**, period-over-period trends, explanations for major shifts, **owners/ETAs**, and evidence links. Never simply report "CPU dropped 10%" without a target or impact context.

### 22.3. Sample Executive Summary Format

```text
Overall service status: At risk
SLO 30-day rolling: 99.86% (target 99.9%)
Customer impact: checkout API errors in Region A, 42 minutes
Root cause: connection pool exhaustion after release
Mitigation: rollback and temporary pool limit
Corrective action: load-test and connection metrics
Owner / deadline: Payments & Platform teams / next sprint
Cost trend: +8% vs baseline (driven by SQL scaling)
Data quality: finalized through specified UTC cutoff
```

These fictional values serve as **report-writing practice**. In real reports, attach incident IDs and appropriately permissioned query links, and state **confidence level and unfinalized data**.

### 22.4. Do Not Force Every Audience onto One Page

On-call engineers need latency, errors, and traces. CTOs need SLO trends, risk/cost, and remediation commitments. Security needs access anomalies. FinOps needs capacity/cost attribution. Maintain **one KPI dictionary** while producing tailored views—preventing five reports from computing availability five different ways.

## 23. Linking Reports to Incidents and Post-Incident Reviews

### 23.1. Reports Must Say More Than "An Error Happened"

An incident review includes:

1. **Impact:** who was affected, transaction count, and duration.
2. **Detection:** which signal fired, and how fast or slow the alert was.
3. **Timeline:** UTC or explicit time zone, including related deployments/changes.
4. **Root cause:** evidence-backed cause, distinguished from symptoms.
5. **Mitigation/Recovery:** actions taken and when service recovered.
6. **Contributing factors:** missing alerts, dashboards, runbooks, rollbacks, or tests.
7. **Actions:** owner, priority, deadline, and issue link.
8. **Validation:** what was tested/monitored after the fix.

### 23.2. Connecting Workbooks to the Incident Timeline

Record the **UTC time window, query text/links, resource IDs, and Workbook revision** used during investigation. If a Workbook query is edited next week, live results may no longer match the incident due to retention or backfill; for audit purposes, preserve **snapshot aggregates and authorized evidence artifacts**, not just URLs.

### 23.3. MTTD, MTTA, MTTR

| Metric | Meaning |
|---|---|
| **MTTD** | Mean Time To Detect – from incident start to detection |
| **MTTA** | Mean Time To Acknowledge – from alert firing to owner acknowledgment |
| **MTTR** | Mean Time To Restore/Recover – per organizational definition |

Acronyms vary (MTTR can mean "Repair" or "Resolve"); **define them explicitly** before comparing month over month. Never use ticket-close time as service recovery time if customers stopped experiencing impact much earlier.

### 23.4. Continuous Improvement

If an incident went undetected by alerts, add an **SLI/alert** before adding 10 CPU charts. If an alert fired but operators could not diagnose it, add **drill-downs, runbooks, and owners**. If a dashboard showed wrong numbers, fix the **telemetry contract** instead of tweaking table colors.

## 24. Operational Report Generation and Publishing Workflow

**Live Workbooks** and **period-closed reports** must be managed separately. A reporting pipeline can combine Log Analytics queries or approved exports, an aggregation engine, artifact storage, and organizational sharing tools. Azure Monitor Workbooks **are not a built-in weekly PDF/email scheduler**, and subscribing to a Workbook URL does not automatically capture point-in-time snapshots.

### 24.1. Report Generation Pipeline

```text
Scheduled run after agreed data cutoff
          |
          v
Validate data source freshness and coverage
          |
          v
Execute versioned KPI queries (Azure Monitor/other source)
          |
          v
Reconcile business figures and SLO denominators
          |
          v
Assemble Markdown/HTML/PDF/BI report (approved workflow)
          |
          v
Review exceptions, incidents, owners and action items
          |
          v
Publish to access-controlled destination
          |
          v
Record report version, generatedAt and query/model revision
```

### 24.2. Metadata That Must Accompany Each Report

```yaml
# Sample report metadata; not an Azure API schema.
reportId: orders-platform-weekly-2026w47
periodStartUtc: "2026-11-16T00:00:00Z"
periodEndUtc: "2026-11-23T00:00:00Z"
generatedAtUtc: "2026-11-23T02:15:00Z"
dataCutoffUtc: "2026-11-23T02:00:00Z"
status: preliminary
metricsDefinitionRevision: "slo-orders-4"
queryRevision: "kql-ops-16"
workbookRevision: "workbook-2026-11-20.1"
sources:
  - azure-monitor-apprequests
  - operations-incident-system
owner: orders-sre
approver: operations-lead
```

This is an **illustrative sample**, not a generated user report or live data. Future dates simply demonstrate period framing; in production systems, schedules and periods must follow the organization's time zone and billing calendar.

### 24.3. Late Reports Still Require Explicit Status

If log ingestion or billing exports lag, publish `PRELIMINARY` with caveats and an expected finalization time, or **withhold publication** if a critical quality gate fails. Never use silence or 0 as a stand-in for missing data. If figures must be revised, issue a **report revision** with diffs/explanations rather than silently overwriting artifacts.

### 24.4. Publication Access Control

Incident and security reports may contain user/resource names, network details, or outage specifics. Distribute through channels with proper **RBAC/retention**; executive summaries should favor aggregations and anonymization. If storing PDF/CSV reports in Blob Storage, enforce identity-based auth, encryption, private access, and lifecycle policies—never distribute unrestricted public SAS URLs.

### 24.5. Approval and Quality

Never let an automated job conclude "Root cause = SQL" solely because a SQL dependency logged high error counts. Machine-generated metrics provide **facts**, whereas root causes and decisions require **human review** when evidence is incomplete. Weekly reports require owner sign-off on significant changes before reaching leadership.

## 25. FinOps Dashboards/Reports: Cost and Serving Capacity

The goal is not merely watching the total bill, but understanding **how many resources each completed order or transaction requires** and when cost increases are justified.

### 25.1. Key Metrics

| Category | Metric | Interpretation |
|---|---|---|
| Cost | Actual cost by subscription/resource group/tag | Budget consumed |
| Unit economics | Cost/1,000 completed orders | Operational unit efficiency |
| Capacity | AKS/App Service CPU & memory, DB capacity | Can resources handle traffic? |
| Messaging | Service Bus operations/backlog/dead letters | Queue efficiency and errors |
| Monitoring | Log ingestion/retention, query volume, sampling | Observability cost |
| Events | Deployments/scale events | Explain cost spikes |

### 25.2. Cost Data Does Not Update at the Same Cadence as Metrics

Azure Cost Management/Exports have **data freshness and billing adjustment behavior** distinct from Azure Monitor Metrics. Cost data may be unfinalized and subject to reservations, savings plans, tags, and attribution lags. **Do not plot cost on a "current-minute" axis and pretend it is real-time.** Reports must state the billing period and data refresh timestamp, comparing regions/cost centers under matching definitions.

### 25.3. Do Not Assume Metrics Exist Directly in Cost Management

Workbooks support certain data sources and links, but **they do not provide a default query connector to read every Cost Management table directly**. To combine cost and SLIs, use **Cost Management exports/APIs** or an approved data pipeline, ingest into an appropriate store (accounting for retention and billing), or link to Cost Analysis. Never invent `AzureCosts_CL` and assume that table exists out of the box.

### 25.4. Cost per Completed Order

```text
Cost per completed order =
  total attributable service cost in period
  / number of completed orders in same period
```

Align on **cost allocation, time zone/cutoff period, workload boundaries, credits/discounts, and denominators**. If completed orders drop sharply during an outage, cost/order rises even without infrastructure scaling—an operational anomaly to explain rather than simply "cloud spend went up."

### 25.5. Cost Anomaly Alerts

Budget alerts, cost anomaly alerts, and available Cost Management mechanisms support FinOps; they **do not replace** SLO/error alerts and carry different data latencies. On-call engineers should not be paged every minute over expected billing fluctuations from an approved batch job. Assign owners and thresholds per product.

## 26. Security and Data Governance for Workbooks and Reports

### 26.1. Sensitive Data in Queries

Application logs can contain emails, IP addresses, order IDs, exception bodies, and query parameters. Workbooks can join tables and surface details via links. Therefore:

- Use **structured logging with redaction** at the source.
- Query only necessary display fields, using `project-away` on unnecessary PII.
- Separate broadly visible aggregate internal dashboards from tightly scoped incident drill-downs.
- Restrict workspace/table read permissions via Azure IAM and supported data access controls.
- Manage snapshots/exports under data classification and retention policies.
- Audit Workbook editors and privileged role assignments.

### 26.2. Parameter Injection

Allowing free-text string parameters and interpolating them straight into queries can cause **KQL syntax failures or unintended scope expansion**. Use supported parameter types and quoting, allowlist service/environment/region values, and test queries against inputs containing quotes or slashes. **Never treat a parameter filter as authorization**; IAM must enforce data access.

### 26.3. Cardinality and PII in Metrics

Attaching `customerEmail` or `orderId` as a metric dimension can create millions of series, inflate cost/overhead, and leak PII through dashboards. Dimensions like **service, region, route template, status class, and deployment ring** are far more useful; keep trace and order IDs in role-protected logs.

### 26.4. Auditing Workbook Changes

Modifying a production Workbook query to filter out `5xx` errors produces false health reports. Practice:

1. Version-control serialized definitions.
2. Review query logic and KPI dictionary changes.
3. Separate editor permissions from operator viewer roles.
4. Enable Azure Activity Log / resource change auditing where appropriate.
5. Require deployment approvals and rollback procedures.
6. Test snapshot expected query outputs after changes.

### 26.5. Never Embed Access Tokens in Workbook URLs

Drill-down links must never include secret query strings, broad SAS tokens, access tokens, or restricted internal resource metadata beyond policy. Links should rely on the viewer's **Azure identity access** to target resources/queries. If a user lacks access, grant the proper governed scope rather than sending screenshots of sensitive data as a workaround.

## 27. Designing Data Quality for Observability

**Telemetry is also data**: it can be missing, duplicated, timestamp-skewed, or schema-drifted. Dashboards need their own data-quality checks, especially when evaluating SLOs or billing.

### 27.1. Five Core Checks

| Quality Dimension | Question | How to Check |
|---|---|---|
| **Freshness** | How old is the newest record? | LastSeen and ingestion lag |
| **Completeness** | Are any clusters, routes, or regions missing? | Resource inventory vs. reporting sources |
| **Schema** | Are DurationMs, ResultCode, AppRoleName still present? | Schema validation / query contract |
| **Consistency** | Do request totals align with platform ingress? | Cross-check within sampling tolerance |
| **Correctness** | Do KPIs share identical good/bad definitions? | Unit tests for aggregations/KQL |

### 27.2. Sampling and Statistical Representativeness

Application Insights/OTel may sample traces and requests, meaning raw `count()` does not necessarily equal actual request volume. Some schemas support weighting fields like `ItemCount` or pre-aggregated metrics; using them must match **telemetry type and instrumentation semantics**. Never multiply every row by a fixed factor when sampling rates vary dynamically.

### 27.3. Timestamps and Late-Arriving Data

Suppose an error occurs at 23:58 local time and the log is ingested at 00:08 the next day. Daily reports require an **event-time cutoff and allowed lateness**, or must be marked preliminary/restated. Never assign an error to the next day simply because ingestion arrived after midnight when the KPI is event-time based.

### 27.4. A Valid Query on the Wrong Scope Still Produces Wrong Data

A Workbook targeting `law-dev` with syntactically valid queries tells you nothing about production SLOs. Before accepting any report, verify **subscription/resource IDs, environment filters, regions, telemetry schema version, and query revision**.

### 27.5. No Data Is a Managed State

For SLOs:

```text
RequestCount == 0:
  show NO_DATA / NOT_APPLICABLE as agreed
  do not show availability 100%

LogIngestionLate == true:
  show DATA_DELAYED with last watermark
  do not finalize incident statistics
```

These are sample business/reporting rules; each service may have **legitimate idle periods** or distinct traffic baselines.

## 28. Validation: Testing Workbooks Before Sharing

### 28.1. Test Cases to Run

| Test | Expected Result |
|---|---|
| Time range 1h/24h/7d | Queries run cleanly; time bins/labels remain accurate |
| Switch environment dev/prod | Data never mixes |
| Select an unauthorized resource | Clearly displays access denied, never turns green |
| Log source has zero events | Shows NO_DATA rather than Success=100% |
| High 5xx data | Error-rate/SLI matches formula |
| Sampled queries | Appropriate caveats/weights applied |
| One region loses telemetry | Freshness/completeness flags anomaly |
| Viewer holds read-only role | Views expected data; cannot edit Workbook |
| Editor updates KQL | Version review and rollback path exist |
| Large time range selected | Queries avoid unreasonable timeouts or cost spikes |
| Mobile/large wallboard layout | Labels/units are unclipped and accessible |

### 28.2. Golden Dataset

Build a small fixture dataset:

```text
100 eligible requests
96 good
4 bad (HTTP 5xx)
latencies: known sorted values
2 simulated dependency errors
1 simulated missing telemetry window
```

Calculate expected availability = **96%** by hand and verify it matches KQL, dashboards, and reports. Never use real production PII data to test reporting query logic. For p95, verify the query engine's **percentile algorithm/interpolation**; do not assert an exact value on tiny sample sizes without checking the calculation method.

### 28.3. Comparing Dashboards Against Reports

Run both the Workbook and reporting pipeline over the exact same fixed time range and filters. **Good/bad counts, request totals, and date boundaries** should match within expected tolerance; if they diverge, inspect sampling, ingestion lateness, time-zone conversion, query definitions, and scope.

### 28.4. Testing After SDK/Agent Upgrades

Upgrading the Java Azure Monitor OpenTelemetry agent/SDK can alter span attributes, operation names, service IDs, or sampling behavior. KQL hardcoding `AppRoleName == "orders-api"` can suddenly return empty results if a new deployment changes the role name. After any SDK/agent upgrade, **smoke-test actual telemetry tables/schemas** and critical dashboard panels.

## 29. Designing Reporting Without Causing Alert Fatigue

### 29.1. Make Alerts Actionable

Promote a signal to an alert only when **a specific owner and remediation action** exist; if it is only for trend tracking, keep it in a dashboard or report. Base alerts on customer impact, SLO/error budgets, or resource saturation predicting an outage—avoid paging on harmless fluctuations.

### 29.2. SLO Burn Rate

For a 99.9% request-based SLO, the error budget fraction is 0.001. You can define a conceptual **burn rate**:

```text
burn rate = observed bad fraction / allowed bad fraction

Example:
  observed bad fraction = 0.004 (0.4%)
  allowed bad fraction  = 0.001 (0.1%)
  burn rate = 4x
```

A burn-rate alert should evaluate **multiple time windows** to reduce noise, tuned to volume and SLA. Thresholds and windows must be calibrated per SLO rather than reusing one default pair across every service.

### 29.3. Clear Ownership and Escape Hatches

Every alert should include:

- Service/owner and escalation routing.
- Signal/unit/window and a Workbook link scoped to the incident time context.
- A 3–5 step triage guide in the runbook.
- Instructions to verify user impact, roll back, or mitigate.
- Criteria proving actual **recovery**, not merely "alert resolved."
- Post-incident review of false positives.

### 29.4. Reporting False Positives

Track **page volume, actionable rate, false positives, and MTTD/MTTA** in monthly reviews; if an alert repeatedly wakes people without requiring action, fix its signal/threshold or downgrade it to a non-paging notification.

## 30. Integrating Dashboards with Change and Operations Systems

### 30.1. Placing Deployments and Incidents on the Same Timeline

When p95 spikes at 10:15, engineers need to know whether a release, scale event, config change, RBAC drift, or database migration happened around 10:00. Combine:

- Application Insights/`AppTraces` or custom deployment events.
- Azure Activity Log for resource/control-plane changes.
- CI/CD deployment history with securely recorded release IDs/commit SHAs.
- Incident trackers and maintenance windows.

### 30.2. Never Infer Causation from Correlation Alone

"Latency increased after deploy" is a **hypothesis**, not a root cause. Workbooks should enable drill-down by route/region, SQL dependencies, exception types, saturation, and traces. Root-cause reports must rest on solid evidence.

### 30.3. Release Annotations Require a Schema

```json
{
  "eventType": "deployment",
  "service": "orders-api",
  "environment": "production",
  "region": "southeastasia",
  "releaseId": "release-20261120-3",
  "commit": "example-sha",
  "startedAtUtc": "2026-11-20T10:00:00Z",
  "completedAtUtc": "2026-11-20T10:05:00Z",
  "result": "SUCCEEDED"
}
```

This is an **illustrative application/CI event contract**; Azure Monitor does not emit this exact JSON automatically. A `SUCCEEDED` CI/CD status does not prove the application is healthy; enforce post-deploy SLI/health gates.

### 30.4. Change Calendars and Maintenance

Dashboards can display planned maintenance/deployment banners; alert suppression/muting requires an owner, expiration time, and audit trail. Never disable all alerts indefinitely simply because a database migration is running.

## 31. Case Study: Workbook for a Java + Azure Platform

### 31.1. Context

The **Orders Platform** consists of:

- **Azure Front Door / Application Gateway** in front of the API, depending on architecture.
- **Java 21 / Spring Boot** on AKS or Azure App Service.
- **Azure SQL Database** storing orders.
- **Azure Service Bus** for background jobs and retries.
- **Azure Key Vault** supplying secrets via managed/workload identity.
- **Application Insights + Log Analytics** monitoring requests, dependencies, exceptions, and structured logs.
- **Azure Monitor Metrics/Alerts** for infrastructure, DB, queues, and saturation.
- **Azure Cost Management** for period-based operational spend.

Business requirements:

1. Eligible API traffic must achieve **99.9% good requests / rolling 30 days**.
2. 95% of requests must complete within **800 ms** (hypothetical target only).
3. 99% of orders must finish processing within **120 seconds** of acceptance.
4. P1/P2 incidents must be detected within on-call policy timeframes.
5. Weekly reports must provide traceable numbers without mixing staging and production.

### 31.2. Operational Workbook Architecture

```text
                            Azure Monitor Workbook
                  Parameters: time / env / region / role
                                   |
        +--------------------------+--------------------------+
        |                          |                          |
        v                          v                          v
   Java API panel             Dependency panel           Backlog panel
   AppRequests                AppDependencies            Service Bus metrics
   requests/errors/p95        SQL/Key Vault/HTTP         and worker telemetry
        |                          |                          |
        +--------------------------+--------------------------+
                                   |
                            Drill-down links
                                   |
                  Traces / Logs / Alerts / Runbook
                                   |
                                   v
                      Daily / Weekly Ops Review
                  (approved aggregation + snapshots)
```

### 31.3. Designing 7 Core Panels

| Panel | Source | Query/Aggregation | Meaning |
|---|---|---|---|
| 1. Availability | AppRequests or SLI source | Good/eligible over selected period | SLO |
| 2. Request throughput | AppRequests | Requests/min, trend | Traffic |
| 3. p95 latency | AppRequests/latency metric | Percentile on requests | Tail latency |
| 4. Dependencies | AppDependencies | Failure count/p95 by target | Bottlenecks |
| 5. Queue backlog | Service Bus Metrics + worker event | Active/dead-letter, oldest age | Async pressure |
| 6. DB health | Azure SQL Metrics | CPU/DTU/vCore/connection/wait signals | Saturation |
| 7. Data quality | Instrumentation heartbeat/source reconciliation | Last event and freshness | Prevent green-with-no-data |

To keep the main page uncluttered, place top exceptions, slow queries, pod restarts, and release history inside **drill-down sections**.

### 31.4. Shift Summary KQL

A query retrieving **requests, failures, and p95 by role over the last 24h**:

```kusto
AppRequests
| where TimeGenerated >= ago(24h)
| where AppRoleName in ("orders-api", "orders-worker")
| summarize
    Requests=count(),
    Failures=countif(Success == false),
    P95_ms=percentile(DurationMs, 95),
    FirstSeen=min(TimeGenerated),
    LastSeen=max(TimeGenerated)
    by AppRoleName
| extend ErrorRatePct =
    iff(Requests > 0, 100.0 * todouble(Failures) / Requests, real(null))
| order by AppRoleName asc
```

**Warning:** do not label `orders-worker` as HTTP "availability" if it primarily processes queue jobs rather than serving HTTP requests. Worker SLIs should be grounded in business job events/lag; the query above only covers request telemetry if the worker has request instrumentation.

### 31.5. Adding a Release-to-Error Correlation Table

Configure the Workbook to overlay deployment annotations when a release-event schema/log source exists; otherwise link to CI history scoped to the time range. An incident summary should capture **before/after release**:

- Traffic and error rate with denominators.
- p95 latency and dependencies.
- Queue depth/lag and worker completion.
- SQL saturation.
- Rollback timestamp and user-impact duration.

Never declare root cause solely from temporal proximity.

### 31.6. When the Service Bus Backlog Spikes

Example:

```text
12:00 orders accepted ~300/min
12:00 orders completed ~290/min
12:15 orders accepted ~300/min
12:15 orders completed ~120/min
12:20 queue backlog = 5,000 messages
12:20 oldest message age = 11 min
```

These are **illustrative figures**. Dashboards should contrast **incoming rate vs. processing rate** alongside saturation and worker failures; looking only at backlog count cannot distinguish a legitimate traffic surge from a worker crash.

### 31.7. Acceptance Criteria

- On-call can assess **whether users are impacted within roughly 30 seconds** from the dashboard (a UX goal, not an Azure SLA).
- The Workbook filters by production/region/time and exposes top errors plus trace details.
- No-data panels explicitly signal lost telemetry.
- Operators have read-only access while Workbook editors hold separate roles.
- KQL queries include time filters and validated p95/availability semantics.
- SLOs and reports share the same KPI dictionary and query revisions.
- Alerts include action groups, runbooks, owners, thresholds, and verified tests.
- Weekly reports include source cutoffs, incidents, action items, and cost context.

## 32. Runbook 1: Empty Workbook or "No Data"

**Symptom:** request charts are blank even though the application is serving live traffic.

### 32.1. Initial Triage Categories

1. **Zero traffic:** the service is genuinely idle or paused.
2. **Missing instrumentation:** Java agent, SDK, or log exporter failed.
3. **Un-ingested data:** pipeline lag, DCR/transformation drop, or diagnostic misconfiguration.
4. **Faulty query:** wrong time range, table, `AppRoleName`, or schema/column name.
5. **Wrong scope:** Workbook points to a dev workspace or different resource.
6. **Insufficient permissions:** viewer lacks read access on workspace or Azure resource.
7. **Expired retention:** querying outside the configured retention window.

### 32.2. Procedure

1. Record the Workbook URL/revision, active parameters, time range, and affected panels.
2. Verify which **Application Insights resource and Log Analytics workspace** are targeted.
3. Run a minimal KQL check against the exact workspace:

   ```kusto
   AppRequests
   | where TimeGenerated > ago(2h)
   | summarize Rows=count(), LastSeen=max(TimeGenerated)
   ```

4. If rows exist, inspect `AppRoleName` values, filters, and timestamps.
5. If no rows exist, inspect application instrumentation/exporters, sampling, and ingestion health.
6. Check user permissions; test using a representative reader account with the intended scope.
7. For cross-resource queries, validate source parameters and resource IDs.
8. Re-test charts against the selected scope/time; never replace missing results with `0` to "avoid blank panels."
9. Document root cause and add a freshness alert if none exists.

### 32.3. What Not to Do

- Never promote everyone to subscription Contributor because one Workbook panel returned access denied.
- Never widen the time range to `All time` to mask broken instrumentation.
- Never replace `null`/empty with 0% failure if business rules require a no-data indicator.
- Never copy production logs into a public workspace for "easier viewing."

### 32.4. Recovery Verification

Queries return expected event counts and timestamps, charts display accurate units and time ranges, data freshness stays within thresholds, and viewers hold least-privilege read access.

## 33. Runbook 2: Green Dashboard While Customers Are Failing

**Symptom:** support reports customers cannot place orders, yet the dashboard shows 100% availability and zero critical alerts.

### 33.1. Common Causes

- The dashboard only probes `/health` instead of end-user order flows.
- Wrong environment/resource scope (displaying staging).
- KQL accidentally filters out 5xx responses or counts only successful requests.
- Sampling, dropped telemetry, or empty sources are coerced into "good."
- The service is blackholed so **zero requests** arrive to compute a failure rate.
- Async queue/workers are failing while the API still returns HTTP 202 Accepted.
- Overly wide aggregation windows smooth out a short incident.

### 33.2. Procedure

1. Inspect user-impact signals from ingress/client-side logs and business events.
2. Check traffic numerator/denominator counts, no-data indicators, and last ingestion time.
3. Query logs using a **fixed time range covering the incident**, not a shifting "last 5 min."
4. Check live SQL/Service Bus dependencies and worker completion/lag metrics.
5. Review deployment timelines and recent configuration changes.
6. Compare the KPI contract against deployed KQL to spot erroneous exclusion filters.
7. Define a valid business SLI (e.g., orders completed within 2 minutes).
8. Fix alert thresholds/evaluation logic if it missed user impact.
9. Test simulated failure and zero-traffic scenarios before publishing Workbook updates.
10. Document the incident, including detection gaps and remediation owners.

### 33.3. Lesson Learned

Monitoring must **measure end-to-end user journey completion**, not just individual API liveness probes. "Zero error logs" does not mean "zero errors" if the log exporter lost connectivity.

## 34. Runbook 3: Slow Workbook and Rising Log Costs

**Symptom:** opening the Workbook takes tens of seconds; Log Analytics or compute charges rise after adding panels.

### 34.1. Assessment

1. Record **Workbook revision**, default time range, query/panel count, and viewer count.
2. Identify queries scanning large log volumes, returning huge row counts, or running cross-workspace `join` operations.
3. Verify whether `TimeGenerated` and resource/service filters are applied early.
4. Check whether queries return 100,000 raw rows instead of aggregations/top N.
5. Inspect auto-refresh intervals, query frequency, and parameter-change triggers.
6. Check ingestion growth, retention settings, table plans, and pricing changes.
7. Check resource quotas and service performance rather than blaming the Workbook alone.

### 34.2. Remediation

- Narrow the default time range (e.g., `1h`/`24h`).
- Separate overview panels from deep-dive tabs so heavy queries run only on demand.
- Pre-aggregate meaningful metrics for frequently queried patterns.
- Eliminate high-cardinality dimensions and PII.
- Minimize cross-resource joins and keep query payload sizes bounded.
- Relax refresh intervals in line with operational needs and freshness SLIs.
- Run before/after performance benchmarks over the same time range and workspace.
- Add regression checks on query duration and targeted tables.

### 34.3. Do Not "Fix" Cost by Blindly Deleting Useful Logs

Arbitrarily slashing retention or disabling audit logs can violate incident, security, and compliance requirements. Evaluate **log value, sampling, table plans, archival, retention, and cost** through governance—never sacrifice investigative capability simply to make a dashboard load faster.

## 35. Runbook 4: Weekly Report Disagrees with Dashboard Numbers

**Symptom:** the weekly report states 99.6% availability, whereas selecting the same week in the Workbook shows 99.9%.

### 35.1. Dimension-by-Dimension Comparison

| Check | Potential Cause of Drift |
|---|---|
| Time period | Rolling 7d vs. calendar week; UTC vs. local time zone |
| Data cutoff | Report closed before late events finished ingesting |
| Resource scope | Dashboard covers prod region A; report covers all regions |
| Business eligibility | 4xx/429/timeouts classified differently |
| Sampling | Weighted query vs. raw event counts |
| Aggregation | Average of hourly rates vs. ratio of sums |
| Denominator | API requests vs. completed orders |
| Query revision | Workbook updated while report still runs an older version |
| Retention/reprocessing | Data restated or expired |

### 35.2. Reconciliation Procedure

1. Lock identical **UTC start/end timestamps, workspace/resource IDs, and service lists** on both sides.
2. Extract **raw numerators and denominators** per day/hour—never compare percentages alone.
3. Check sampling weights and telemetry completeness.
4. Diff query text, revisions, and filters.
5. Recompute `sum(good)/sum(eligible)` over the identical window.
6. Reconcile late arrivals, backfills, and cutoff boundaries.
7. Determine the authoritative version and archive reconciliation evidence.
8. Publish a corrected report revision with an explanation and owner.

### 35.3. Never "Pick the Better-Looking Number"

When two sources disagree, never cherry-pick the higher number for reporting. Determine the authoritative KPI from the **data contract and business owner**, then align both outputs.

## 36. Practical Exercises

### Exercise A — Design an Operations Overview

A Java application on Azure App Service serves 2 million requests/day with an Azure SQL database and a Service Bus worker. Sketch an on-call dashboard with at most **8 panels** containing:

- User-impact and SLO signals.
- Latency/errors/traffic.
- SQL and queue saturation.
- Telemetry freshness.
- Drill-down link + owner.

**Solution guide:** put availability/error budget, error rate, and p95 at the top; follow with backlog/worker completion/SQL saturation; include a no-data status indicator, environment/time filters, and a runbook link. Do not let CPU charts fill the page.

### Exercise B — Choose Dashboard or Workbook

Three stakeholders: NOC wants a wallboard, SRE wants Pod/region investigation, and the CTO wants a weekly summary.

**Task:** assign Azure portal dashboard, Monitor Workbook, and weekly report to each group; explain the difference between a live view and a period-closed report.

**Solution guide:** NOC = overview dashboard, SRE = drill-down Workbook, CTO = period-closed report with review/snapshot. Link them where helpful without conflating their roles.

### Exercise C — Write a KQL Request Trend

Suppose `AppRequests` has 10,000 rows in 1 hour, of which 300 have `Success == false`. Write KQL aggregating `Requests`, `Failed`, and `ErrorRatePct` in 5-minute bins for `orders-api`; explain what `bin` does and how empty buckets behave.

**Solution guide:** use `where TimeGenerated >= ago(1h)`, `where AppRoleName == "orders-api"`, `summarize count()/countif() by bin`, and `extend ErrorRatePct`. If the denominator is 0, return no-data/null rather than dividing by 0.

### Exercise D — SLO with Denominator

Over 30 days there are 10,000,000 eligible requests and 9,992,000 good requests. The SLO is 99.9%.

**Task:** compute availability and bad events against the budget. Explain why a 0.1% budget does not automatically equal a fixed number of outage minutes.

**Solution guide:** availability = 99.92%; bad requests = 8,000; budget = 10,000; 2,000 bad requests remain before breaching the SLO. Request-based budgets are not automatically equivalent to time-based budgets.

### Exercise E — Weighted Error Rate

Hour 1: 10 requests, 5 failures → 50%. Hour 2: 9,990 requests, 5 failures → roughly 0.05%.

**Task:** compute the 2-hour overall error rate. Why should you not average `(50% + 0.05%)/2`?

**Solution guide:** failures = 10 / total = 10,000 → **0.1%**. Averaging hourly percentages weights every hour equally despite vastly different traffic volumes.

### Exercise F — Application Insights Sampling

Java instrumentation sends only a fraction of request events; the dashboard uses raw `count()` as total requests.

**Task:** describe potential distortion, how to inspect sampling mode/`ItemCount` or suitable metric sources, and what data is needed for an SLO.

**Solution guide:** never treat raw sampled rows as total traffic; use properly defined metrics/weighted events and validate against ingress or known test workloads.

### Exercise G — Workbook Parameters

Design `TimeRange`, `Environment`, `Resource`, and `Region` for a Workbook shared across dev/staging/prod.

**Task:** specify default values, allowed-value constraints, query scope, viewer permissions, and no-data handling.

**Solution guide:** narrow default time window; prod filters must map to actual resource bindings rather than simple strings; never use dropdowns as IAM; unauthorized resources must surface access denied.

### Exercise H — KQL Exceptions and Dependencies

Write KQL to find the top 10 failing `Target` values in `AppDependencies` over 2 hours and top 10 `ExceptionType` values in `AppExceptions`. Explain how to verify table schema and sampling before trusting results.

**Solution guide:** filter time early, use `summarize countif(Success == false)` and `top 10`, and omit sensitive raw stack traces. For `AppExceptions`, use `summarize count() by ExceptionType`.

### Exercise I — Missing Telemetry

A service receives zero requests for 15 minutes. The dashboard shows a 0% error rate and the operator concludes the system is healthy.

**Task:** design a **NO_DATA** state, heartbeat source, independent platform ingress signal, and log ingestion outage alert.

**Solution guide:** when eligible count = 0, availability/error rate per contract should evaluate to null/not applicable; distinguish legitimate idle periods from telemetry outages.

### Exercise J — Least-Privilege Workbook Sharing

An operator has read access to the Workbook, yet charts return forbidden. A developer wants to grant subscription Contributor.

**Task:** identify the three permission layers (Workbook definition, data sources, edit) and propose least privilege.

**Solution guide:** grant read permissions on the relevant Log Analytics/Application Insights/metrics sources; never grant broad Azure resource write access just to view charts.

### Exercise K — Slow Workbook After Release

After adding 20 raw KQL queries auto-refreshing every 10 seconds, a Workbook takes 40 seconds to open and query costs rise.

**Task:** design optimizations for time range, summarization, query scope, conditional panels, and refresh interval, and specify before/after measurements.

**Solution guide:** eliminate full-retention scans, return summaries/top N, move deep queries to on-demand drill-downs, and avoid refreshing 30-day charts every few seconds.

### Exercise L — Weekly Operational Report

Suppose a week saw 2 incidents, one post-deploy rollback, and a 12% cost rise driven by SQL scaling. Draft a report covering:

- Executive summary and UTC/local period.
- SLO/error budget and user impact.
- Incident timeline and root-cause investigation status.
- Capacity/cost trend.
- Data freshness/cutoff.
- Action items with owners/ETAs.

**Solution guide:** never paste charts alone; include denominators, sources, caveats, and concrete action items.

### Exercise M — Comparing a Workbook with a Report

A "last 7 days" Workbook shows 99.90% availability while the calendar-week report shows 99.86%.

**Task:** reconcile UTC start/end times, business time zone, ingestion cutoff, eligible/bad counts, sampling, scope, and query revision.

**Solution guide:** extract identical numerators/denominators over the exact same time range; if late logs changed totals, issue a report revision explaining why.

### Exercise N — Queue Worker Dashboard

A Service Bus queue has an 8,000-message backlog; an hour later, active message count drops sharply.

**Task:** explain why this does **not automatically** indicate success, and recommend complementary metrics.

**Solution guide:** messages may have expired or moved to dead-letter rather than being processed; pair with incoming/outgoing rates, dead-letter count, business completions, oldest message age, and worker errors.

### Exercise O — Incident Postmortem

A 20-minute application outage failed to trigger an alert because the Workbook/query filtered on the wrong `AppRoleName`.

**Task:** construct the timeline, customer impact, detection gap, root-cause hypothesis, corrective actions, and dashboard integration tests.

**Solution guide:** write schema/agent telemetry contract tests, monitor missing data, version-control KQL/Workbooks, and add post-deploy production smoke checks.

## 37. Self-Check Questions

**1. What is an Azure portal dashboard best used for?** Concise health overviews and wallboards; it is not an alert engine or snapshot report store.

**2. What is an Azure Monitor Workbook best used for?** Interactive investigation pages combining parameters, queries, charts, and multi-source drill-downs.

**3. How does an operational report differ from a dashboard?** Reports include a closed period, cutoff, owner, review, commentary, and action items; dashboards typically show live data.

**4. Do Workbooks store raw logs?** No; they store definitions, queries, and layouts while reading from underlying data sources.

**5. Are Azure Monitor Metrics and Log Analytics logs identical?** No; time-series metrics and log tables differ in schema, query APIs, and behavior.

**6. Is KQL `AppRequests` present in every Azure workspace?** No; it depends on workspace-based Application Insights and instrumentation/schema configuration.

**7. Can Activity Log replace application request logs?** No; Activity Log primarily captures control-plane and resource operations.

**8. How does an SLI differ from an SLO?** An SLI is the measured service indicator; an SLO is the target value over a time window.

**9. Does 99.9% availability always equal 43.2 minutes of downtime per 30 days?** Only in a time-based availability model; do not equate that directly to a request-based SLO.

**10. Why do we need a denominator?** Failure rates cannot be interpreted without total eligible requests and classification rules.

**11. What is p95 latency?** The 95th percentile of request durations within the measured dataset/window—not average latency.

**12. Should you average p95 across multiple instances?** No, not for system-wide p95; use combined histograms/distributions or raw samples/appropriate aggregations.

**13. What is RED?** Rate, Errors, and Duration for request-handling workloads.

**14. What is USE?** Utilization, Saturation, and Errors for resources.

**15. Does low Pod CPU mean the system has no bottlenecks?** No; DB locks, queue lag, I/O, thread pools, or dependency errors can still cause outages.

**16. How can a dashboard show 0 errors during an active incident?** Missing telemetry, wrong scope, zero traffic, flawed SLI definition, or async failures.

**17. Why shouldn't no data be displayed as 100% availability?** There is no denominator or evidence; null/unknown needs its own state.

**18. Why does a Workbook's time range matter?** It determines data scope, metric semantics, and query cost.

**19. Is a resource picker a security boundary?** No. Access to data sources and Workbooks is enforced by Azure IAM and data-source permissions.

**20. Why might someone see a Workbook layout while charts return 403?** They have read access to the Workbook definition but lack read access to Log Analytics/Application Insights/resources.

**21. Is `render timechart` mandatory inside a Workbook?** No; visualizations can be selected in the editor depending on the query step/data source.

**22. What does `bin(TimeGenerated, 5m)` do?** Buckets timestamps into 5-minute intervals for summarization.

**23. Does `countif(Success == false)` automatically equal the SLO bad-request count?** No; business SLIs and sampling rules may differ.

**24. Why must `AppRoleName` be standardized?** So filters do not silently drop services after deployments or agent upgrades.

**25. Why might traces be missing spans?** Sampling, broken instrumentation/context propagation, or incomplete resource query scopes.

**26. Does a shrinking Service Bus backlog prove workers succeeded?** No; messages may have expired or moved to the dead-letter queue.

**27. Does Azure Monitor Metrics Explorer automatically create `CPU_CL` in Log Analytics?** No; it only exists if exported/ingested as logs via a configured pipeline.

**28. What is Resource Graph used for?** Querying Azure resource metadata, not application request log payloads.

**29. Do Azure Resource Graph and Log Analytics share the exact same full KQL engine?** No; the two sources and query engines differ.

**30. What should you optimize first in a slow Workbook query?** Time filters, scope, summarize/top N, panel count, and auto-refresh settings.

**31. Why not average hourly error rates to compute a daily error rate?** Hourly traffic varies; divide summed numerators by summed denominators instead.

**32. How can sampling affect a dashboard?** Raw sampled counts and percentiles can skew; apply weights or appropriate unsampled metric sources.

**33. Why must daily reports specify time zone and cutoff?** To clarify window boundaries, late-arriving events, and figure-restatement history.

**34. Can a weekly report rely on a live Workbook URL as a snapshot?** No, not when reproducibility is required; live query results can shift over time.

**35. Is cost data always as real-time as Metrics?** No; Cost Management/billing exports have their own latency and adjustments.

**36. Should customer email be used as a metric dimension?** No; it causes high cardinality and PII exposure.

**37. Do alerts need Action Groups?** For routing notifications/automation appropriately, Action Groups are the standard supported mechanism and require owner/escalation design.

**38. Does a dashboard replace alert rules?** No. Dashboards visualize; alert rules evaluate conditions and notify on breaches.

**39. What are MTTD and MTTR?** Mean Time To Detect and Mean Time To Restore/Recover/Repair, which must be defined consistently by the organization.

**40. What is the ultimate test of a good Workbook?** It helps authorized responders quickly determine customer impact and failure origin, surfaces data freshness, uses consistent KPIs, provides drill-downs/runbooks, and avoids cost or security risks.

## 38. Production Readiness Checklist

### 38.1. Objectives/KPIs and Data Sources

- [ ] Assign an owner, service boundary, and target audience for every dashboard, Workbook, and report.
- [ ] Document each KPI's **definition, source, units, denominator, aggregation, and time window**.
- [ ] Have business/service owners approve SLIs/SLOs along with eligibility rules.
- [ ] Define clear error budgets or performance targets for evaluation.
- [ ] Never substitute CPU or health-endpoint probes for end-user/business SLIs.
- [ ] Apply RED for user-facing APIs and USE for resource saturation where appropriate.
- [ ] Emit events/metrics tracking async business workflows (accepted/completed/failed).
- [ ] Smoke-test Java OpenTelemetry/Application Insights instrumentation end-to-end.
- [ ] Discover Log Analytics tables and metric definitions directly from target resources.
- [ ] Enable required log categories and destinations in Diagnostic Settings.
- [ ] Evaluate sampling, ingestion latency, and retention impacts.
- [ ] Never assume Azure Monitor Metrics appear automatically as KQL tables.

### 38.2. Overview Dashboards

- [ ] Top panels show **availability, errors, p95, and critical incident/data freshness status**.
- [ ] Traffic, error, and latency panels state explicit units, time windows, and sources.
- [ ] Clearly label environment, region, resource/service scope, and last refresh.
- [ ] Never mix dev/staging/prod or unintended regions.
- [ ] Distinguish no-data/unknown from zero errors or 100% success.
- [ ] Plot/annotate SLO targets and baselines rather than decorative colors.
- [ ] Provide drill-down links from overview panels to Workbooks, traces, and logs.
- [ ] Display owner/on-call/runbook info without relying solely on color.
- [ ] Ensure dashboard viewers hold read access on data sources without unnecessary edit rights.
- [ ] Verify layout readability across operations monitors and accessibility needs.

### 38.3. Azure Monitor Workbooks

- [ ] Include practical `TimeRange`, `Environment`, and `Resource` parameters.
- [ ] Set a narrow default time window to prevent scanning full retention automatically.
- [ ] Allowlist/escape parameters properly and never use them for authorization.
- [ ] Target accurate resource scopes using verified existing fields/schemas.
- [ ] Apply early time filters, resource filters, and `summarize/top N` in KQL.
- [ ] Ensure request/availability queries specify denominators and handle sampling.
- [ ] Compute percentiles over proper distributions, never averaging per-node p95s.
- [ ] Include units, sample sizes, and drill-down paths on charts and tables.
- [ ] Pair critical panels with no-data/freshness checks or companion telemetry.
- [ ] Include dedicated sections for dependencies, queues/DB, deployments/changes, and incident details.
- [ ] Store Workbook sources/templates under version control with query tests.
- [ ] Separate viewer/editor/deployer roles and maintain definition rollback procedures.
- [ ] Keep cross-subscription/resource queries aligned with IAM and data classification policies.

### 38.4. Alerts and On-Call Operations

- [ ] Create alerts **independently** rather than relying on red Workbook tiles.
- [ ] Ground thresholds, windows, severities, and action groups in SLOs and risk.
- [ ] Configure minimum traffic volume thresholds and no-data handling where appropriate.
- [ ] Assign owners, on-call escalations, and audited suppression policies.
- [ ] Link incident alerts straight to the relevant Workbook tab and time window.
- [ ] Test fired/resolved alert transitions and notification routing.
- [ ] Distinguish external user-impact alerts from internal infrastructure warnings.
- [ ] Capture release/deployment annotations and change history for investigation.
- [ ] Maintain runbooks for missing data, false-green dashboards, and cost regressions.
- [ ] Review alert fatigue, MTTD, MTTA, and MTTR periodically.

### 38.5. Shift, Daily, and Weekly Reports

- [ ] Specify fixed start/end periods, time zone, and **data cutoff** in every report.
- [ ] Record Report ID, owner, approver, query revision, and sources.
- [ ] Flag reports as **PRELIMINARY/FINAL/RESTATED** when data is unfinalized.
- [ ] Reconcile SLO numerators and denominators against Workbooks over identical windows.
- [ ] Ensure incident summaries cover impact, timeline, evidence, mitigation, and root-cause status.
- [ ] Include deployment/capacity/traffic changes and business workflow health.
- [ ] State billing period, attribution rules, and data-freshness caveats on cost figures.
- [ ] Track action items with owners, priorities, ETAs, and issue links.
- [ ] Distribute sensitive reports exclusively through RBAC- and retention-governed channels.
- [ ] Archive snapshots/evidence for audits rather than relying on live Workbook URLs.
- [ ] Version any updates to published figures and document restatement reasons.

### 38.6. Data Quality, Security, and Cost

- [ ] Use synthetic tests to validate KQL queries and expected aggregates.
- [ ] Maintain golden datasets covering error rates, percentiles, and empty windows when needed.
- [ ] Ensure missing/stale telemetry never turns into false 0 errors or 100% good.
- [ ] Monitor completeness across clusters/regions alongside ingestion lag.
- [ ] Keep PII, tokens, and connection strings out of shared dashboard query results.
- [ ] Track log ingestion/export/query spend against budgets.
- [ ] Never use high-cardinality customer or order IDs as metric dimensions.
- [ ] Gate Workbook revision changes behind PRs, reviews, and deploy approvals.
- [ ] Run regression checks on dashboards, alerts, and reports after agent/SDK updates.
- [ ] Validate Azure RBAC, workspace permissions, and query sources using real principals.
- [ ] Enforce retention/archival policies aligned with incident and legal obligations.
- [ ] Maintain runbooks and owners for cost anomalies, report mismatches, and missing telemetry.

## 39. Conclusion

**Dashboards, Azure Monitor Workbooks, and operational reports** are three complementary views of the same system—not three names for a single chart. **Dashboards** give on-call responders immediate visibility into service health; **Workbooks** let engineers filter time ranges and resources, query **Azure Monitor Metrics, Log Analytics/KQL, and Application Insights**, and drill down to root causes; **operational reports** close a reporting period to review **SLOs, incidents, risks, costs, and follow-up actions**.

For Java applications and Azure services such as AKS/App Service, Azure SQL, Service Bus, and Key Vault, start with **well-denominated SLIs/SLOs and trustworthy telemetry** before choosing layouts or visualizations. Every panel needs explicit scope, units, time range, and **no-data** states. Workbooks and reports must share a single **KPI dictionary, query versioning, access controls, and data cutoffs**, backed by runbooks and alerts that operate independently of anyone watching a screen.

A well-run observability practice produces more than pretty charts: it answers **whether customers are impacted, since when, why, who owns the response, and what change prevents recurrence**. Combined with **RBAC governance, data protection, cost control, and regular reviews**, Azure Monitor becomes a foundation for verifiable operational decisions and continuous improvement.

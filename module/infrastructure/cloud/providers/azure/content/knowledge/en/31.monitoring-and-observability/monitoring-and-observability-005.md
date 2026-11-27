# Writing KQL Queries to Investigate Applications and Infrastructure

At 10:15, a Java/Spring Boot application on Azure begins returning HTTP 500s, latency climbs, and several Azure Kubernetes Service (AKS) Pods restart. The dashboard shows an incident is underway, yet fails to answer **where the failure started, which versions are affected, which dependency is slow, which Pod is unhealthy, and whether an infrastructure change occurred right beforehand**. Instead of opening log files one by one and searching manually, engineers can use **Kusto Query Language (KQL)** in **Azure Monitor Logs / Log Analytics** to narrow scope, aggregate, cross-check telemetry, and test hypotheses.

This lesson belongs to the **Monitoring and Observability** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Azure from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data; while building skills to deploy, monitor, secure, and control the cost of Azure application architectures. KQL is the investigative tool linking application symptoms to infrastructure, deployment, and dependency traces.

> **Scope and notes:** This lesson focuses on KQL in **Azure Monitor Logs**, **Log Analytics workspaces**, and **workspace-based Application Insights**, alongside Azure Activity, Container Insights, and resource diagnostic data when collected. Schemas, table/column names, and query capabilities may vary by Application Insights type, legacy tables, collection solutions, storage modes, tenants, and time. All examples use **common table names and hypothetical data**; always verify against your workspace's actual schema before running. These queries are **read-only**; still, reading logs can incur query charges, expose sensitive information if permissions are overly broad, or return unauthorized production data.

## Learning Objectives

After this lesson, learners can:

1. Explain where telemetry is stored and the roles of Azure Monitor, Log Analytics, Application Insights, and Container Insights.
2. Verify **scope**, **time range**, tables, and schemas before querying.
3. Write KQL using **where, project, extend, order by, take, summarize, bin, countif, dcount, and percentile**.
4. Investigate error rates, p95/p99 latency, request failures, dependency failures, and exceptions.
5. Link requests, dependencies, and traces via **OperationId** properly without duplicating rows during joins.
6. Analyze AKS logs via **ContainerLogV2** and **KubePodInventory**, and hosts/VMs via **Heartbeat**, **Perf**, and **InsightsMetrics** where present.
7. Locate Azure resource changes in **AzureActivity** and diagnostics in **AzureDiagnostics** or resource-specific tables.
8. Handle **dynamic JSON**, nulls, type conversions, UTC timestamps, ingestion lag, and sampling.
9. Optimize KQL to reduce scanning/cost and avoid flawed dashboards or alerts.
10. Execute an end-to-end incident investigation workflow with evidence, hypotheses, and clear conclusion boundaries.

## 1. What Is KQL and Where Is It Used?

**KQL (Kusto Query Language)** is a pipeline-based analytical query language. It is used across Azure Monitor Logs, Azure Data Explorer, and other Microsoft products as applicable. This lesson focuses on **log analytics**, not SQL DML or modifying production state.

~~~text
Spring Boot / AKS / Azure SQL / Gateway / VMs
                     |
                     | Logs, metrics, traces, diagnostics
                     v
        Azure Monitor collection pipeline
                     |
             +-------+-------+
             |               |
             v               v
       Log Analytics     Metrics store
       workspace         (separate metrics)
             |
             v
     Tables: AppRequests, AppDependencies,
     ContainerLogV2, AzureActivity, ...
             |
             v
         KQL in Logs
             |
             v
       Triage / Workbooks / Alerts
~~~

Not every Azure metric lives in a KQL table. **Azure Monitor Metrics** and **Azure Monitor Logs** use distinct storage and collection paths; querying metrics via KQL requires that corresponding data be routed into a supported table such as **AzureMetrics**, **Perf**, or **InsightsMetrics** per configuration.

## 2. The Three Observability Signals: Logs, Metrics, Traces

| Signal | Question Answered | Example |
|---|---|---|
| **Logs** | What event or error happened? | Exceptions, Pod restart logs, Activity |
| **Metrics** | How is the system changing over time? | CPU, request rate, p95 latency |
| **Distributed traces** | Which services did a request pass through? | API → Redis → SQL → Service Bus |

In Application Insights, request and dependency tables include correlation fields enabling **operation-level tracing**, yet **KQL cannot manufacture distributed traces** if the application lacks instrumentation or loses context propagation.

**Never infer root cause from a single metric.** Rising CPU could be either the cause or the effect of a retry storm, database failure, or traffic surge.

## 3. Related Azure Components

| Component | Role |
|---|---|
| **Azure Monitor** | Platform for monitoring, collection, querying, and alerting |
| **Log Analytics workspace** | Stores log tables with configured retention and permissions |
| **Application Insights** | Application telemetry: requests, dependencies, exceptions, traces |
| **Azure Monitor Agent / DCR** | Collection and log routing pipelines on VMs or supported resources |
| **Container Insights** | Collects status, logs, and metrics from Kubernetes per configuration |
| **Diagnostic settings** | Routes resource logs/metrics of Azure resources to supported destinations |
| **Azure Activity log** | Control-plane operations on Azure resources |
| **Logs query interface** | Runs KQL scoped to a workspace/resource and time range |

### Crucial Pitfall

An empty table **does not prove the absence of incidents**. Collection may be disabled, diagnostic settings may target another workspace, retention may have expired, RBAC may be missing, or ingestion may be lagging.

## 4. Pick the Right Scope Before Querying

When opening **Logs** from a workspace or resource, **scope** determines which data is accessible:

~~~text
Subscription
  |
  +-- Log Analytics workspace "ops-prod"
  |      +-- AppRequests from multiple apps
  |      +-- ContainerLogV2 from multiple clusters
  |      +-- AzureActivity / resource diagnostics
  |
  +-- Application Insights resource "checkout-prod"
  |
  +-- AKS cluster "aks-prod"
~~~

### Workflow

1. Confirm **tenant, subscription, resource group, and resource name**.
2. Verify whether Application Insights is **workspace-based** and which workspace it targets.
3. Confirm whether AKS, VMs, and resource diagnostic logs feed into that same workspace.
4. Check the UI **time picker** and timezone.
5. If a workspace serves multiple applications, filter by **AppRoleName** or **_ResourceId** where those columns exist.
6. If a resource points to a different workspace, do not jump to assuming logs were lost.

**A KQL query cannot join data that was never ingested or that the caller lacks permission to read.** Cross-resource and cross-workspace queries are subject to permissions, feature support, and cost; define scope upfront.

## 5. Table Names: Workspace-Based vs. Legacy Application Insights

In **workspace-based Application Insights**, common tables include:

| Telemetry Type | Workspace-Based (Common) | Legacy / Application Insights Context (Common) |
|---|---|---|
| HTTP requests | **AppRequests** | **requests** |
| Dependencies | **AppDependencies** | **dependencies** |
| Exceptions | **AppExceptions** | **exceptions** |
| Application traces/logs | **AppTraces** | **traces** |
| Page views | **AppPageViews** | **pageViews** |
| Custom events | **AppEvents** | **customEvents** |

Table names, casing, and columns **differ**. Specifically:

~~~text
AppRequests:
  TimeGenerated, Name, Success, ResultCode,
  DurationMs, OperationId, AppRoleName, ItemCount ...

requests (legacy context):
  timestamp, name, success, resultCode,
  duration, operation_Id, cloud_RoleName, itemCount ...
~~~

**Do not run an `AppRequests` query against `requests` by swapping only the table name.** You must adjust column names, units, and types. For example, **DurationMs** is in milliseconds in `AppRequests`, whereas **duration** in legacy tables is often a timespan or different scale—never compare it directly as raw milliseconds without checking.

## 6. Common Infrastructure Tables

| Table | Data Type and Preconditions |
|---|---|
| **AzureActivity** | Azure control-plane administrative events routed to Logs |
| **AzureDiagnostics** | Shared resource diagnostics when using AzureDiagnostics destination mode |
| **Resource-specific tables** | Dedicated names per service/log category when configured for resource-specific mode |
| **ContainerLogV2** | Container stdout/stderr logs per Container Insights / collection config |
| **KubePodInventory** | Collected Kubernetes Pod status and metadata |
| **KubeNodeInventory** | Node status and metadata if ingested |
| **Heartbeat** | Machine/agent heartbeats when collected |
| **Perf** | Performance counters per agent/DCR/config |
| **InsightsMetrics** | Metrics from supported monitoring solutions |
| **AzureMetrics** | Metrics exported/ingested into logs per configuration |

Never assume every table exists in every workspace. Azure resource logs may flow into **resource-specific tables** instead of `AzureDiagnostics`, and some signals live only in the Metrics backend rather than Log Analytics.

## 7. Start from the Schema, Not Copied Queries

In the Azure Portal, open **Log Analytics workspace → Logs** or Application Insights → Logs and inspect the schema browser for real tables and columns.

Minimal probe query:

~~~kusto
AppRequests
| take 5
~~~

Inspect column structure if the environment supports the operator:

~~~kusto
AppRequests
| getschema
~~~

### Operational Safety

**`take 5` does not guarantee zero cost**, especially without a time filter on huge workspaces. During real investigations, apply time range and column/resource filters first:

~~~kusto
AppRequests
| where TimeGenerated >= ago(30m)
| project TimeGenerated, AppRoleName, Name, ResultCode, Success, DurationMs
| take 10
~~~

**Do not assume `.show tables` works in Azure Monitor Logs:** Azure Data Explorer control commands are not generally supported in the Log Analytics query interface. Use the schema pane and Logs-supported query operators.

## 8. The KQL Pipeline: Table Followed by Operators

KQL reads left-to-right (top-to-bottom) across **|** pipes:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where Success == false
| project TimeGenerated, AppRoleName, Name, ResultCode, DurationMs
| order by TimeGenerated desc
| take 20
~~~

Explanation:

1. **AppRequests**: data source.
2. **where**: filters time and failures.
3. **project**: keeps only needed columns.
4. **order by**: sorts newest first.
5. **take**: caps returned rows.

### `take` vs. `top`

**`take 20`** returns an arbitrary 20 rows with **no ordering guarantee** unless sorted. **`top 20 by TimeGenerated desc`** is a concise shorthand for fetching the newest records:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| top 20 by TimeGenerated desc
~~~

## 9. Time Filtering: UTC and Incident Windows

In Log Analytics, **TimeGenerated** is normally a UTC datetime. When an operator reports "the incident started at 10:15," confirm the timezone.

~~~text
10:15 Vietnam time (UTC+7)
= 03:15 UTC same day
~~~

Illustrative UTC window query:

~~~kusto
let IncidentStart = datetime(2026-11-20T03:15:00Z);
let IncidentEnd = datetime(2026-11-20T04:00:00Z);
AppRequests
| where TimeGenerated >= IncidentStart
  and TimeGenerated < IncidentEnd
| summarize Requests = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Why Use a Half-Open Interval?

Using **>= start and < end** allows consecutive windows to tile seamlessly without double-counting boundary events.

### Time Picker vs. `where`

The Logs UI has its own time picker. Both the **`where TimeGenerated`** filter in your query and the UI time picker constrain the query window depending on execution mode. Check both if a query returns zero rows when you expect data.

## 10. The `where` Operator: Filter Precisely Instead of Full-Scanning

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| where AppRoleName == "checkout-api"
| where Success == false
| project TimeGenerated, OperationId, Name, ResultCode, DurationMs
~~~

### Common Filter Predicates

| Expression | Meaning |
|---|---|
| **==** | Equals, type-matched comparison |
| **!=** | Not equal |
| **in (...)** | Matches any value in a set |
| **between (a .. b)** | Within range (watch inclusive bounds) |
| **contains** | Case-insensitive substring match |
| **has** | Term match using Kusto tokenization |
| **startswith** | Starts with prefix |
| **isnotempty(x)** | Not null and not empty string |
| **isnull(x)** | Null check |

### `contains` vs. `has`

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| where Message has "timeout"
| project TimeGenerated, AppRoleName, Message
| take 50
~~~

**`has`** leverages term indexing in many scenarios; **`contains`** scans substrings and is generally more expensive. Choose based on semantics: matching `"order"` as a standalone token differs from matching `"preorder"` as a substring.

## 11. `project`, `extend`, `project-away`, and `rename`

**`project`** selects and renames output columns:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| project
    TimeGenerated,
    Service = AppRoleName,
    RequestName = Name,
    LatencyMs = DurationMs
| take 20
~~~

**`extend`** adds computed columns while keeping existing ones:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| extend SlowRequest = DurationMs > 1000.0
| project TimeGenerated, Name, DurationMs, SlowRequest
| take 30
~~~

### `project` Early or Late?

Filter **TimeGenerated** and resources first, then **`project`** only required columns to shrink data passed to heavier operators—while making sure you do not drop **OperationId** before joins or calculations. The KQL optimizer can push projections/filters down; the goal remains readable queries handling minimal data.

## 12. Aggregating with `summarize`, `count`, and `bin`

Query total requests in 5-minute buckets:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| summarize RequestRows = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

By service:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| summarize RequestRows = count()
    by AppRoleName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Reading the Output

- Each row represents one **TimeGenerated** bucket and **AppRoleName**.
- **`count()`** counts rows stored in the table, which may not equal original request volume if sampling is active.
- **`bin(TimeGenerated, 5m)`** rounds timestamps down to the start of each 5-minute bucket.

For brief incidents, use `1m` or `5m` depending on traffic; overly small bins on low-traffic services cause wild swings, while huge bins hide short error bursts.

## 13. Computing HTTP Request Error Rates

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Total = count(),
    Failed = countif(Success == false)
    by AppRoleName, bin(TimeGenerated, 5m)
| extend FailureRatePct = iff(
    Total == 0,
    0.0,
    round(100.0 * todouble(Failed) / todouble(Total), 2)
)
| order by TimeGenerated asc
~~~

### Why Not Count Only HTTP 500?

**`Success`** in Application Insights follows SDK/telemetry semantics and may classify status codes differently from business expectations. If you want strictly HTTP server errors, filter explicitly:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Requests = count(),
    Http5xx = countif(toint(ResultCode) between (500 .. 599))
    by AppRoleName
| extend Http5xxPct = round(
    100.0 * todouble(Http5xx) / todouble(Requests), 2)
~~~

### Interpret Results Responsibly

One group showing **1 error / 2 requests = 50%** is very different from another showing **200 errors / 100,000 requests = 0.2%**. Always evaluate both the percentage and the denominator rather than sorting blindly by `FailureRatePct`.

## 14. Application Insights Sampling and `ItemCount`

Application Insights can use **sampling** to reduce volume and cost. In matching tables, **`ItemCount`** (when present) reflects how many telemetry items a stored sample represents per SDK/ingestion behavior.

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    StoredRows = count(),
    EstimatedRequests = sum(ItemCount),
    EstimatedFailed = sumif(ItemCount, Success == false)
    by AppRoleName
| extend EstimatedFailurePct = round(
    100.0 * todouble(EstimatedFailed)
    / todouble(EstimatedRequests), 2)
~~~

### Avoid Naive Comparisons

- **`count()`** counts ingested rows.
- **`sum(ItemCount)`** approximates original events when sampling and field semantics apply.
- Some telemetry may be dropped pre-ingestion, throttled by quotas, non-uniformly sampled, or altered by custom instrumentation.
- **`percentile(DurationMs, 95)`** over sampled rows is not automatically weighted by `ItemCount`.
- If a table lacks `ItemCount`, adapt the query rather than assuming `ItemCount=1` everywhere.

In formal reports, state clearly whether numbers reflect **stored events or estimated original events**, along with sampling settings and confidence level.

## 15. Latency: `avg` and `percentile` p50/p95/p99

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| summarize
    Requests = count(),
    AvgMs = round(avg(DurationMs), 1),
    P50Ms = round(percentile(DurationMs, 50), 1),
    P95Ms = round(percentile(DurationMs, 95), 1),
    P99Ms = round(percentile(DurationMs, 99), 1)
    by AppRoleName, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Why Does p95 Matter?

A 100 ms average can disguise 5% of requests taking 3 seconds. **p95** is the threshold below which roughly 95% of observed requests fall (per the engine's approximate percentile algorithm); **p99** examines the steeper latency tail.

### Caveats

- Small sample sizes make p99 noisy.
- KQL `percentile()` computes approximate percentiles algorithmically.
- Sampling and missing telemetry skew distributions.
- Separate distinct endpoints: checkout and health probes have completely different latency profiles.
- **`DurationMs`** measures server-side request telemetry duration, not full browser-to-origin round-trip time across CDNs and gateways.

## 16. Analyzing Top Failing and Slow Endpoints

Most failing endpoints:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Total = count(),
    Failed = countif(Success == false),
    P95Ms = percentile(DurationMs, 95)
    by AppRoleName, Name
| where Total >= 20
| extend FailurePct = round(100.0 * todouble(Failed) / Total, 2)
| top 20 by Failed desc
~~~

### Why Use `Name` Instead of Raw URL?

Application Insights typically normalizes **`Name`** to route templates like **`GET /orders/{id}`**. Grouping by raw URLs containing `orderId` or `customerId` explodes group cardinality, drives up query costs, and risks exposing sensitive data.

**`Total >= 20` is an illustrative filter**; tune it to real traffic. A low-volume, revenue-critical endpoint still warrants investigation after just 1–2 errors.

## 17. Distinguishing `ResultCode`, `Success`, and Business Failures

An HTTP 200 response might return:

~~~json
{
  "status": "PAYMENT_DECLINED",
  "reason": "BUSINESS_RULE"
}
~~~

At the HTTP layer, the request succeeded; at the business layer, payment did not complete. KQL querying **`AppRequests.Success`** cannot know business rules automatically.

### Telemetry Design

- Emit standardized **outcome codes** in logs/custom events.
- Never put card data, auth tokens, emails, or raw PII into traces.
- Include **`OperationId`/`traceId`** to link requests with business events.
- Keep semantics clear: **technical failures** differ from **business rejections**.

**Never treat every HTTP 4xx as a server incident.** 401/403 indicates auth/permission issues, 429 indicates throttling, and 404 indicates missing resources—classify by endpoint and client behavior.

## 18. `let`: Define Scope Once, Reuse Cleanly

KQL supports **`let`** to bind expressions, scalars, or tabular views.

~~~kusto
let StartTime = ago(2h);
let Service = "checkout-api";
AppRequests
| where TimeGenerated >= StartTime
| where AppRoleName == Service
| summarize Requests = count(),
    Failures = countif(Success == false)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Notes on `let`

**`let`** binds a name to an expression rather than always eagerly evaluating a constant. For non-deterministic expressions or large subqueries reused multiple times, consider **`toscalar()`** or **`materialize()`** where appropriate and supported by the engine. Never materialize huge datasets blindly without measuring.

## 19. Interpreting Results in the Right Order

A dashboard shows rising HTTP 500s:

~~~text
10:10  API deployment completed
10:12  AppRequests p95 rises
10:13  AppDependencies SQL failures rise
10:15  AppExceptions timeout increase
10:18  AKS restarts some Pods
~~~

These events are **temporally correlated**, which does not by itself prove the deployment caused the SQL timeout. KQL shows which signal appeared first, on which version/Pod, and which requests hit dependency failures. Root cause must be verified with logs, traces, deployment diffs, and occasionally controlled reproductions.

**Sound workflow:** define time window → quantify impact → segment by group → inspect dependencies → cross-check infrastructure/changes → test hypothesis → take rollback-ready action.

## 20. `AppDependencies`: Which Dependency Is Slow?

**`AppDependencies`** holds instrumented outbound calls—HTTP, databases, or other dependency types depending on the SDK/agent:

~~~kusto
AppDependencies
| where TimeGenerated >= ago(2h)
| summarize
    Calls = count(),
    Failed = countif(Success == false),
    AvgMs = round(avg(DurationMs), 1),
    P95Ms = round(percentile(DurationMs, 95), 1)
    by AppRoleName, Type, Target
| top 20 by Failed desc
~~~

If **`Target=sql-prod.database.windows.net`** shows rising failures, check SQL availability, query timeouts, connection pools, TLS, firewalls, and identity. **`Target` does not always map 1:1 to a single Azure resource.**

Not every SDK or call is auto-instrumented. Zero dependency telemetry does not prove the application made no outbound calls.

## 21. Dependency Errors and p95 Over Time

~~~kusto
AppDependencies
| where TimeGenerated >= ago(3h)
| where AppRoleName == "checkout-api"
| summarize
    Total=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by Target, bin(TimeGenerated, 5m)
| extend FailurePct=round(
    100.0 * todouble(Failed) / todouble(Total), 2)
| order by TimeGenerated asc
~~~

When dependency **`Type`** is SQL, Service Bus, or another non-HTTP protocol, **`ResultCode`** is not guaranteed to be an HTTP status; do not apply `toint(ResultCode) >= 500` uniformly to all dependencies. Rely on **`Success`**, **`Type`**, and service-specific diagnostics and error codes.

## 22. `AppExceptions`: Group Errors Instead of Reading Stack Traces One by One

~~~kusto
AppExceptions
| where TimeGenerated >= ago(2h)
| summarize
    ExceptionRows=count(),
    LastSeen=max(TimeGenerated)
    by AppRoleName, ProblemId,
       ExceptionType=column_ifexists("ExceptionType", "")
| top 20 by ExceptionRows desc
~~~

To inspect a specific failure:

~~~kusto
AppExceptions
| where TimeGenerated >= ago(1h)
| where AppRoleName == "checkout-api"
| project TimeGenerated, OperationId, ProblemId,
    ExceptionType=column_ifexists("ExceptionType", ""),
    Message=column_ifexists("Message", "")
| top 30 by TimeGenerated desc
~~~

The presence and naming of **`ExceptionType`, `Message`, and `ProblemId`** depend on the table schema. **`Details`** may hold the full exception hierarchy; do not assume `Message` contains the entire stack trace. Never paste raw exceptions containing PII or secrets into public tickets or chat.

## 23. `AppTraces`: Searching Application Signals

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| where AppRoleName == "checkout-api"
| where Message has "timeout"
| project TimeGenerated, SeverityLevel, OperationId,
    AppRoleName, Message
| top 50 by TimeGenerated desc
~~~

Free-form text logs are hard to aggregate and can leak data:

~~~text
checkout failed for customer 12345 with auth token ...
~~~

Prefer **structured logging** with meaningful fields while avoiding PII and tokens:

~~~json
{
  "event": "checkout_failed",
  "failure_category": "dependency_timeout",
  "trace_id": "synthetic-id",
  "dependency": "azure-sql",
  "elapsed_ms": 1200
}
~~~

Fields may populate **`Properties`/`customDimensions`** depending on instrumentation; never assume every key appears automatically unless the logger and telemetry pipeline are configured for it.

## 24. Dynamic JSON and `Properties`

In many tables, **`Properties`** is a **`dynamic`** column holding key-value pairs:

~~~kusto
AppTraces
| where TimeGenerated >= ago(2h)
| extend
    Category=tostring(Properties["failure_category"]),
    Dependency=tostring(Properties["dependency"]),
    ElapsedMs=todouble(Properties["elapsed_ms"])
| where Category == "dependency_timeout"
| summarize
    Events=count(),
    P95ElapsedMs=percentile(ElapsedMs, 95)
    by AppRoleName, Dependency
~~~

When a field is a **JSON-encoded string**, use **`parse_json()`**:

~~~kusto
AppTraces
| where TimeGenerated >= ago(30m)
| extend PayloadText=tostring(Properties["payload_summary"])
| extend Parsed=parse_json(PayloadText)
| project TimeGenerated,
    EventType=tostring(Parsed["event_type"]),
    Outcome=tostring(Parsed["outcome"])
| take 30
~~~

When `Properties` is already `dynamic`, index directly via **`Properties["key"]`**. Never parse or expose sensitive payloads on dashboards without authorization.

## 25. Nulls, Empty Strings, and Type Conversions

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| extend ParsedDuration=todouble(Properties["duration_ms"])
| summarize
    Total=count(),
    Valid=countif(isnotnull(ParsedDuration)),
    Invalid=countif(isnull(ParsedDuration))
    by AppRoleName
~~~

- **`toint()`/`tolong()`/`todouble()`** return null when parsing fails.
- **`coalesce()`** picks the first non-null value; never silently replace missing errors with `0` if `0` has real meaning.
- **`isnull()`** and **`isempty()`/`isnotempty()`** test different states.
- A missing `DurationMs` does not mean the request finished in 0 ms.

Never coerce missing latency values to `0` and conclude that p95 improved.

## 26. Regex and Extracting Fields from Unstructured Logs

~~~kusto
AppTraces
| where TimeGenerated >= ago(1h)
| where Message contains "traceId="
| extend ExtractedTraceId=
    extract(@"traceId=([A-Za-z0-9_-]+)", 1, Message)
| where isnotempty(ExtractedTraceId)
| project TimeGenerated, AppRoleName, ExtractedTraceId
| take 50
~~~

Regex is brittle when log formats change, expensive to evaluate, and can accidentally surface PII. **`OperationId`** from standard instrumentation is far more reliable than parsing free-form trace IDs when context propagation works properly.

## 27. `OperationId`: Linking a Single Transaction

~~~text
HTTP /checkout (OperationId=op-42)
      |
      +-- SQL dependency    (OperationId=op-42)
      +-- Service Bus call  (OperationId=op-42)
      +-- Trace             (OperationId=op-42)
      +-- Exception         (OperationId=op-42)
~~~

Example tracing a known operation:

~~~kusto
let Op = "<OPERATION_ID_FROM_INCIDENT>";
union isfuzzy=true
    (AppRequests | project TimeGenerated, OperationId,
        Kind="request", Detail=Name, AppRoleName),
    (AppDependencies | project TimeGenerated, OperationId,
        Kind="dependency", Detail=Name, AppRoleName),
    (AppTraces | project TimeGenerated, OperationId,
        Kind="trace", Detail=Message, AppRoleName),
    (AppExceptions | project TimeGenerated, OperationId,
        Kind="exception",
        Detail=tostring(column_ifexists("Message", "")), AppRoleName)
| where TimeGenerated >= ago(2h)
| where OperationId == Op
| order by TimeGenerated asc
~~~

**Replace the placeholder** with a real ID. If a table does not exist, adapt to your schema; `union isfuzzy` does not grant permissions or invent missing tables. Telemetry sampling, broken context propagation, or async background jobs can cause some spans to be absent.

## 28. Joining Failed Requests with Dependencies

Constrain time **on both sides** and pre-aggregate dependencies before joining to avoid row multiplication:

~~~kusto
let FailedRequests =
    AppRequests
    | where TimeGenerated >= ago(1h)
    | where AppRoleName == "checkout-api"
    | where Success == false
    | where isnotempty(OperationId)
    | project RequestAt=TimeGenerated, OperationId,
        RequestName=Name, RequestCode=ResultCode;
let DependencyRollup =
    AppDependencies
    | where TimeGenerated >= ago(1h)
    | where isnotempty(OperationId)
    | summarize
        DepCount=count(),
        FailedDeps=countif(Success == false),
        MaxDepMs=max(DurationMs)
        by OperationId;
FailedRequests
| join kind=leftouter (DependencyRollup) on OperationId
| project RequestAt, OperationId, RequestName, RequestCode,
    DepCount, FailedDeps, MaxDepMs
| top 30 by RequestAt desc
~~~

One operation can execute multiple dependencies: **joining directly and calling `count()`** inflates request counts. Always roll up the right side first when you want one summary row per operation.

A single **`OperationId`** can also span multiple `AppRequests` across a distributed transaction; to reconstruct exact parent-child trees, inspect **`Id`, `ParentId`/span IDs**, schemas, and timestamps rather than treating `OperationId` as a unique request row key.

## 29. Choosing the Right `join` Kind

| Kind | Question |
|---|---|
| **inner** | Which keys match on both left and right? |
| **innerunique** | Join deduplicating the left side by key (easy to drop details if misunderstood) |
| **leftouter** | Keep all left rows even without a right match |
| **leftsemi** | Which left rows have at least one match? |
| **leftanti** | Which left rows have no match? |
| **fullouter** | Which rows are unmatched on either side? |

Finding failed requests missing dependency telemetry:

~~~kusto
let R =
    AppRequests
    | where TimeGenerated >= ago(30m)
    | where Success == false
    | where isnotempty(OperationId)
    | project TimeGenerated, OperationId, Name;
let D =
    AppDependencies
    | where TimeGenerated >= ago(30m)
    | where isnotempty(OperationId)
    | distinct OperationId;
R
| join kind=leftanti (D) on OperationId
| top 30 by TimeGenerated desc
~~~

Missing dependency telemetry does not prove the failure involved no dependencies: instrumentation, sampling, scope, or ingestion may be incomplete.

## 30. `arg_max`: Fetching the Latest State of an Object

Inventory tables emit periodic snapshots. To find the latest Pod state:

~~~kusto
KubePodInventory
| where TimeGenerated >= ago(2h)
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| project TimeGenerated, ClusterName, Namespace, PodName=Name, PodStatus
| order by TimeGenerated desc
~~~

**`arg_max(TimeGenerated, PodStatus)`** returns the `PodStatus` from the row with the largest `TimeGenerated`, not the alphabetically highest status string.

### Things to Watch

Kubernetes Pods sharing a name across recreations are not necessarily the same instance; include Pod UID if present and instance identity matters. Inventory snapshots are periodic captures, not a complete event log of every container crash.

## 31. `dcount`: Approximate Distinct IDs

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Requests=count(),
    DistinctOperations=dcount(OperationId)
    by AppRoleName
~~~

**`dcount()`** computes an approximate distinct count suited to large datasets. **`OperationId`** is not a user ID. Never group directly by customer ID or session ID without authorization, privacy review, and an analytical need; high cardinality makes queries costly and risks exposing sensitive data.

## 32. Before/After Deployment Comparison

Suppose a deployment ran at **03:20 UTC**:

~~~kusto
let DeployAt = datetime(2026-11-20T03:20:00Z);
AppRequests
| where TimeGenerated >= DeployAt - 30m
  and TimeGenerated < DeployAt + 30m
| where AppRoleName == "checkout-api"
| extend Phase = iff(TimeGenerated < DeployAt, "before", "after")
| summarize
    Requests=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by Phase
| extend FailurePct=round(100.0 * todouble(Failed) / Requests, 2)
| order by Phase asc
~~~

### Why Is This Not Conclusive Alone?

- Traffic mix and peak hours may differ.
- Rolling deployments span multiple Pods over an extended period.
- Old and new versions run concurrently during canary rollouts.
- Azure SQL, Redis, or infrastructure may experience an unrelated issue simultaneously.
- You must inspect endpoints, versions, dependencies, and **`AzureActivity`/deployment events** to verify.

## 33. Comparing by Application Version

If the application attaches its version in **`Properties`**:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| extend AppVersion=tostring(Properties["app_version"])
| where isnotempty(AppVersion)
| summarize
    Requests=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by AppRoleName, AppVersion
| extend FailurePct=round(
    100.0 * todouble(Failed) / Requests, 2)
| order by AppRoleName asc, FailurePct desc
~~~

**`app_version` is an illustrative custom property**, not a guaranteed built-in column. You can use deployment revision, image digest, cloud role instance, or release ID if your pipeline supplies that dimension. Never group by individual URLs or request IDs in place of a release version.

## 34. `make-series` and `timechart` Visualizations

~~~kusto
AppRequests
| where TimeGenerated >= ago(3h)
| where AppRoleName == "checkout-api"
| make-series RequestCount=count() default=0
    on TimeGenerated from ago(3h) to now() step 5m
| render timechart
~~~

**`make-series`** generates evenly spaced time buckets; **`render timechart`** is a visualization directive for supported UIs. When calling query APIs/SDKs, the returned data arrays are what your code processes.

**`default=0` does not prove traffic was zero** if the agent or ingestion broke. Avoid creating series across thousands of groups or multi-second steps over months of data without estimating cost.

## 35. Anomaly Detection and Seasonality

KQL provides time-series functions depending on backend and version to detect trends and anomalies. However:

- Weekday vs. weekend traffic creates natural seasonality.
- Marketing campaigns or scheduled batches create legitimate spikes.
- Sampling, log loss, and ingestion delays produce artificial spikes or gaps.
- Low traffic makes statistical anomalies noisy.

A straightforward rule like **5xx rate > threshold for 10 minutes with min 100 requests** is often easier to explain than an unvalidated anomaly algorithm. Treat anomaly detection as a supplementary signal rather than a replacement for root-cause investigation.

## 36. Ingestion Lag and Event Time

When the backend supports **`ingestion_time()`**, you can inspect the gap between event generation and ingestion:

~~~kusto
AppRequests
| where TimeGenerated >= ago(2h)
| extend IngestedAt=ingestion_time()
| where isnotnull(IngestedAt)
| extend LagSeconds=
    datetime_diff("second", IngestedAt, TimeGenerated)
| summarize
    Samples=count(),
    P95LagSeconds=percentile(LagSeconds, 95),
    MaxLagSeconds=max(LagSeconds)
    by AppRoleName
~~~

`ingestion_time()` does not behave identically or exist in every table and solution; clock skew, buffering, and transforms create offsets. If today's rows are missing, inspect the ingestion pipeline and agent before claiming the application stopped serving requests.

### Event Time vs. Ingestion Time

**`TimeGenerated`** reflects event time per schema; **`ingestion_time()`** (when available) reflects when the backend ingested the record. They differ and may not advance monotonically together. When checking 10:15, standardize on UTC and specify which timestamp you mean.

## 37. `ContainerLogV2`: Finding Java Errors in AKS

When Container Insights collects container stdout/stderr into **`ContainerLogV2`**:

~~~kusto
ContainerLogV2
| where TimeGenerated >= ago(1h)
| where PodNamespace == "checkout"
| extend Text=tostring(LogMessage)
| where Text has "Exception" or Text has "ERROR"
| project TimeGenerated, PodNamespace, PodName,
    ContainerName, LogLevel, Text
| top 50 by TimeGenerated desc
~~~

**`LogLevel`** is parsed depending on configuration; do not rely solely on `LogLevel` if the app logs in an unstructured format where the field stays empty. These columns match `ContainerLogV2`; if your workspace uses legacy **`ContainerLog`**, the schema differs—do not just swap table names.

### Watch Out for Multi-Line Java Exceptions

A multi-line Java stack trace can split into separate log records or be stitched together depending on agent multiline configuration. Adjacent rows from the same Pod and timestamp **do not guarantee every line belongs to the same exception**. Structured JSON logging with `traceId` and proper newline handling makes investigations far more accurate.

## 38. Grouping Errors by Pod in AKS

~~~kusto
ContainerLogV2
| where TimeGenerated >= ago(2h)
| where PodNamespace == "checkout"
| extend Text=tostring(LogMessage)
| where Text has "OutOfMemoryError" or Text has "TimeoutException"
| summarize MatchingLines=count(), LastSeen=max(TimeGenerated)
    by PodNamespace, PodName, ContainerName
| top 20 by MatchingLines desc
~~~

### Counting Caveats

**`MatchingLines`** counts log lines containing the terms, not distinct incidents or restarts. One exception can emit dozens of lines, and one Pod can repeat logs during retries. Cross-check metrics, status inventory, and Kubernetes events.

## 39. `KubePodInventory`: Which Pods Are Unhealthy?

~~~kusto
KubePodInventory
| where TimeGenerated >= ago(1h)
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| where PodStatus !in ("Running", "Succeeded")
| project TimeGenerated, ClusterName, Namespace,
    PodName=Name, PodStatus
| top 30 by TimeGenerated desc
~~~

### Avoid Over-Interpreting

A **`Pending`** Pod may stem from image pulls, scheduling/quotas, PVCs, admission webhooks, taints, or node capacity. A **`Succeeded`** Pod may simply be a completed Job, not a broken service. Status semantics also depend on snapshot cadence; `CrashLoopBackOff` is typically a container waiting reason rather than a raw `PodStatus`.

To verify exact restarts and waiting reasons, check **Kubernetes events, `kubectl describe`, and container state** per authorized access, paired with logs if ingested.

## 40. `KubeNodeInventory`: Node Perspective

~~~kusto
KubeNodeInventory
| where TimeGenerated >= ago(2h)
| summarize LastSeen=max(TimeGenerated)
    by ClusterName, Computer
| order by LastSeen desc
~~~

`KubeNodeInventory` columns and formats vary by schema; if **`Computer`** is absent, use `NodeName` or the matching column in your schema.

### Questions to Check

- Did any node stop reporting snapshots?
- Are Pod failures concentrated on a specific node?
- Is the node experiencing CPU, memory, or disk pressure?
- Did an AKS node pool autoscale or upgrade near the incident window?

**A node with no new rows** is not automatically dead; ingestion, agent, or workspace settings may have dropped data. Confirm cluster status from the control plane.

## 41. `Heartbeat`: Did a VM or Agent Stop Sending Telemetry?

~~~kusto
Heartbeat
| where TimeGenerated >= ago(3h)
| summarize LastHeartbeat=max(TimeGenerated) by Computer
| extend MinutesSinceLastHeartbeat =
    datetime_diff("minute", now(), LastHeartbeat)
| order by MinutesSinceLastHeartbeat desc
~~~

### How to Interpret

**`Heartbeat`** is a periodic agent/host signal sent to Logs per collection configuration. It is not an HTTP ping to your application API. A running VM with a stopped agent, broken DCR, or delayed ingestion will show a stale `LastHeartbeat`.

Conversely, a fresh VM heartbeat does not prove the API or SQL inside is healthy. Combine with **`Perf`, service logs, Azure Metrics, and synthetic probes**.

## 42. `Perf`: Analyzing CPU and Memory via Counters

If the workspace collects **`Perf`**:

~~~kusto
Perf
| where TimeGenerated >= ago(2h)
| summarize
    Samples=count(),
    LastSeen=max(TimeGenerated)
    by Computer, ObjectName, CounterName
| top 30 by Samples desc
~~~

Once real counter names are confirmed, query a specific counter:

~~~kusto
Perf
| where TimeGenerated >= ago(1h)
| where CounterName == "% Processor Time"
| summarize AvgValue=avg(CounterValue),
    P95Value=percentile(CounterValue, 95)
    by Computer, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Notes

- **`CounterName`** and **`ObjectName`** differ across Windows, Linux, and collection rules.
- `% Processor Time` may include per-core, per-process, or `_Total` in `InstanceName`.
- Pod/Kubernetes CPU metrics do not necessarily live in `Perf`.
- Never conclude VM CPU is 90% if your query reads only a subset of counter instances.

## 43. `InsightsMetrics`: Exploring Metric Schemas

An **`InsightsMetrics`** table may include columns such as **`Namespace`**, **`Name`**, **`Val`**, **`Tags`**, and **`TimeGenerated`** depending on the solution:

~~~kusto
InsightsMetrics
| where TimeGenerated >= ago(2h)
| summarize Samples=count()
    by Namespace, Name
| top 30 by Samples desc
~~~

Once the real metric is identified:

~~~kusto
InsightsMetrics
| where TimeGenerated >= ago(1h)
| where Namespace == "<ACTUAL_NAMESPACE>"
  and Name == "<ACTUAL_METRIC_NAME>"
| summarize AvgValue=avg(Val)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

**Replace placeholders with values from your actual schema.** Similarly named metrics can differ in units: nanocores, bytes, percentages, or rates. Never scale units without verifying the metric definition.

## 44. `AzureMetrics`: Resource Metrics Exported to Logs

If diagnostic settings route metrics into Log Analytics:

~~~kusto
AzureMetrics
| where TimeGenerated >= ago(2h)
| summarize Samples=count()
    by ResourceProvider, MetricName
| top 30 by Samples desc
~~~

Metadata and aggregation fields like **`MetricName`, `Average`, `Total`, `Maximum`** depend on the schema and metric. The **Azure Metrics backend** is generally the primary source for service metrics; `AzureMetrics` appears only when data is exported/ingested via a supported path.

If the table is missing, do not assume the Azure service has no metrics. Check the **Metrics blade**, diagnostic settings, resource scope, and permissions.

## 45. `AzureActivity`: Did Anyone Change Infrastructure Around the Error?

**`AzureActivity`** is useful for inspecting **management/control-plane** operations (creating, updating, deleting, or writing resources). Depending on schema/collection, common columns include **`TimeGenerated`, `OperationNameValue`, `ActivityStatusValue`, `Caller`, `CorrelationId`, `ResourceGroup`, `_ResourceId`**.

~~~kusto
AzureActivity
| where TimeGenerated >= ago(4h)
| where ActivityStatusValue in ("Succeeded", "Failed")
| project TimeGenerated, OperationNameValue, ActivityStatusValue,
    Caller, ResourceGroup, _ResourceId, CorrelationId
| top 50 by TimeGenerated desc
~~~

### Why Filter Resource Scope?

A central workspace may ingest activity across many subscriptions. Querying "every operation in 4 hours" returns thousands of noisy rows. Narrow by resource group, resource ID, or operation:

~~~kusto
AzureActivity
| where TimeGenerated >= ago(4h)
| where ResourceGroup =~ "rg-checkout-prod"
| where OperationNameValue contains "write"
| project TimeGenerated, Caller, OperationNameValue,
    ActivityStatusValue, _ResourceId, CorrelationId
| top 30 by TimeGenerated desc
~~~

**`AzureActivity` does not log all data-plane operations** such as Blob reads or SQL `SELECT` queries. Use Azure resource diagnostic logs, database auditing, or app telemetry for those. Likewise, CI/CD container image rollouts may leave traces outside `AzureActivity`.

## 46. `AzureDiagnostics`: Filtering by `ResourceProvider` and `Category`

**`AzureDiagnostics`** is a shared table for many resource diagnostic logs when configured for **`AzureDiagnostics` destination mode**:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(1h)
| summarize Records=count()
    by ResourceProvider, ResourceType, Category
| top 30 by Records desc
~~~

Once the exact Category is known:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(1h)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| summarize Events=count()
    by Category, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Schema Caveats

- This table mixes columns across resources/categories; typed suffixes like **`_s`, `_d`, `_g`** or JSON strings may appear.
- **`AzureDiagnostics` is not universal**: many services use **resource-specific tables** when configured accordingly.
- Never depend on a field like **`resultType_s`** before verifying it exists in your data.
- **`ResourceProvider`** may appear uppercase depending on log formatting; verify actual values before exact equality filtering.

Never switch production diagnostic destination modes simply because a sample query didn't find a table. Evaluate retention, historical data, query rewrites, access controls, and cost first.

## 47. Resource-Specific Tables vs. `AzureDiagnostics`

A service may write logs to dedicated tables named for its log categories:

~~~text
Azure resource diagnostic settings
       |
       +-- Destination mode: AzureDiagnostics
       |       |
       |       v
       |    AzureDiagnostics shared schema
       |
       +-- Destination mode: resource-specific
               |
               v
         Service-specific tables
         (names/columns vary by category)
~~~

### When Investigating Key Vault or Application Gateway

1. Open diagnostic settings on the exact resource to verify categories and destination workspace.
2. Open the workspace schema browser.
3. Confirm the actual mode and table names.
4. Use **`TimeGenerated`**, **`_ResourceId`**, and that table's status/error fields.
5. Cross-check against application requests and `AzureActivity`.

Never hardcode a single service table name and claim it applies across all regions and tiers. Legacy and newer tables can coexist during collection transitions.

## 48. `_ResourceId`: Scoping to the Exact Azure Resource

In many tables, **`_ResourceId`** ties records to a specific Azure resource. Filtering by resource cuts noise and prevents mixing environments:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| where _ResourceId =~
    "/subscriptions/<SUB_ID>/resourcegroups/<RG>/providers/microsoft.insights/components/<APP_NAME>"
| summarize Requests=count() by AppRoleName
~~~

**Replace ID placeholders** with the exact resource ID. `_ResourceId` is not guaranteed to be populated in every table—custom logs, migrated data, or agent-generated rows may differ.

### Resource Filtering Does Not Replace RBAC

A KQL filter is not a tenant-isolation control. Users with workspace-wide query permissions can remove the filter; enforce access via workspace/resource/table RBAC, redaction, and data classification.

## 49. Resource IDs and Environment Metadata

To avoid mixing staging and prod:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| summarize
    Requests=count(),
    Failures=countif(Success == false)
    by _ResourceId, AppRoleName
| order by Failures desc
~~~

An **`AppRoleName`** like **`api`** is often reused across environments. Omitting **`_ResourceId`** blends environments together and skews metrics. If the app does not emit environment metadata, add a governed **deployment/environment dimension** instead of guessing from raw URL hostnames without solid evidence.

## 50. Combining Infrastructure Changes with Errors on a Timeline

A practical technique is interleaving **events onto a single timeline**, rather than joining records solely on a 5-minute bucket and claiming causation:

~~~kusto
let RequestErrors =
    AppRequests
    | where TimeGenerated >= ago(3h)
    | where AppRoleName == "checkout-api"
    | where Success == false
    | project TimeGenerated, Kind="request_failure",
        Detail=Name;
let Changes =
    AzureActivity
    | where TimeGenerated >= ago(3h)
    | where ResourceGroup =~ "rg-checkout-prod"
    | where OperationNameValue contains "write"
    | project TimeGenerated, Kind="azure_resource_change",
        Detail=OperationNameValue;
union RequestErrors, Changes
| top 100 by TimeGenerated desc
~~~

### Interpretation

- A `write` operation preceding 500 errors is a **clue**, not proof of root cause.
- `AzureActivity` does not record every app container rollout or database schema migration.
- Align timestamps to UTC and watch for ingestion lag across sources.
- When unioning tables with differing permissions or retention, missing rows from one source do not prove nothing happened there.

**Joining on `bin(TimeGenerated, 5m)`** only shows co-occurrence in the same bucket, not dependency or causality.

## 51. Investigating 401/403 Errors and Throttling

Status codes require grouping because remediation differs:

~~~kusto
AppRequests
| where TimeGenerated >= ago(1h)
| extend Status=toint(ResultCode)
| extend Category=case(
    Status == 401, "unauthorized",
    Status == 403, "forbidden",
    Status == 429, "throttled",
    Status between (500 .. 599), "server_error",
    Status between (400 .. 499), "other_4xx",
    Status between (200 .. 399), "2xx_3xx",
    "other"
)
| summarize Requests=count()
    by AppRoleName, Category
| order by Requests desc
~~~

### What to Check

| Code | Investigation Direction |
|---|---|
| **401** | JWT/credentials, token audience/expiry, auth policies |
| **403** | Authorization, Entra roles, Key Vault/Storage data-plane RBAC, firewalls |
| **429** | App rate limits, backend quotas, retry behavior |
| **5xx** | Exceptions, dependencies, infrastructure, capacity |

A 403 from a Key Vault dependency does not necessarily surface as an **HTTP 403 in `AppRequests`** on the API: the app may catch it and return HTTP 500. Inspect `AppDependencies` and `AppExceptions` via `OperationId`.

## 52. Investigating Source IP Anomalies: Privacy Precautions

Application telemetry may contain client IP or geolocation fields depending on instrumentation and settings. However, Application Insights includes IP masking/privacy features, and geolocation is often approximate.

**Never casually query `ClientIP` to enumerate users.** Security investigations require:

- Valid authorization to access sensitive telemetry.
- Data minimization and clear retention boundaries.
- Never pasting raw IPs, emails, bearer tokens, or full URL query strings into public tickets.
- Recognizing proxies, CDNs, and NATs that alter observed client IPs.
- Checking application and edge logs before attributing traffic to real users or attacks.

KQL aids event investigation, yet **does not replace SIEM/detection/forensics processes** or personal-data processing approvals.

## 53. Optimizing KQL: Filter Early, Project Narrowly, Avoid Wide Scans

An inefficient query:

~~~kusto
// Anti-pattern example only; avoid running on large workspaces:
AppTraces
| where Message contains "timeout"
| order by TimeGenerated desc
~~~

Targeted query:

~~~kusto
AppTraces
| where TimeGenerated >= ago(30m)
| where AppRoleName == "checkout-api"
| where Message has "timeout"
| project TimeGenerated, OperationId, AppRoleName, Message
| top 50 by TimeGenerated desc
~~~

### Priorities

1. Apply **`TimeGenerated`** and a sensible UI time picker.
2. Filter **`_ResourceId`/`AppRoleName`/`Namespace`/`Computer`** early.
3. Project only needed columns.
4. Use **`summarize`** or **`top N`** instead of returning raw records.
5. Prefer **`has`** over `contains` or regex when appropriate.
6. Filter both sides of **`join`/`union`** independently.
7. Avoid **`search *`** across the whole workspace by default.
8. Perform dynamic JSON parsing **after** filtering.
9. Check execution stats where available and verify results.

### Huge Join Anti-Pattern

Joining 30 days of `AppRequests` with 30 days of `AppTraces` on `OperationId` scans massive volume, consumes memory, and multiplies rows. When investigating a 30-minute incident, scope to **30 minutes + resource filters** first.

## 54. KQL and Log Analytics Costs

Overall observability costs can include:

- Ingestion volume by table/data plan and current pricing.
- Retention, archiving/restoring, or extended retention.
- Query/scanning/analytics charges depending on workspace/table plan and features.
- Scheduled query alert rule evaluations per pricing.
- Workbooks and related integrations.
- Data exports, cross-region transfers, and automation.

### Effective Cost-Control Mechanisms

- Instrument only needed fields; suppress valueless verbose logs.
- Design sampling aligned with SLO and security requirements.
- Use **Data Collection Rules / ingestion transforms** where supported and reviewed.
- Match table plans and retention to actual query needs.
- Optimize KQL rather than blindly expanding limits and time windows.
- Weigh trade-offs between trimming ingestion and losing investigative evidence.

**Never treat fixed USD/GB rates or table plan capabilities as immutable rules**: Azure Monitor pricing, plan features, and supported KQL operators vary by service, region, and time.

## 55. Table Plans and Query Limitations

Log Analytics offers **table plans** such as Analytics, Basic, and Auxiliary depending on timing, region, and features. Some plans have **different query, retention, access, or alerting capabilities**.

Before writing a multi-table query:

1. Check the plan of each table in the workspace.
2. Verify whether **`join`/`union`/cross-table search** is supported in that experience.
3. Check retention, queryable time ranges, ingestion lag, and permissions.
4. Check whether scheduled query alerts support that table and plan.
5. Avoid switching plans solely to run one query without analyzing cost and coverage impacts.

A query that is syntactically valid in **Azure Data Explorer** will not necessarily behave identically across every Log Analytics table plan.

## 56. Retention, Archival, and Historical Incidents

If you need to investigate an incident from 90 days ago when a table keeps interactive data for a shorter window:

- Empty query results in that window may be due to **retention**.
- Data may reside in long-term retention/archive per policy, requiring a separate search/restore workflow.
- Authorized external archives, backups, or audit records may be needed.
- Never raise retention workspace-wide without forecasting costs and checking data policy.

### KQL Cannot Recreate Lost Data

If a collector was disabled for 12 hours or sampling dropped records, no KQL syntax can restore raw records that were never ingested. Explicitly document **coverage gaps** in incident reports rather than fabricating data.

## 57. Using KQL as the Basis for Scheduled Query Alerts

A good alert defines **target, time window, trigger condition, minimum volume threshold, and owner/on-call**. Example tracking checkout API failures over 10 minutes:

~~~kusto
AppRequests
| where TimeGenerated >= ago(10m)
| where AppRoleName == "checkout-api"
| summarize
    Total=count(),
    Failed=countif(Success == false)
| extend FailurePct=iff(
    Total == 0,
    0.0,
    100.0 * todouble(Failed) / todouble(Total)
)
| where Total >= 100 and FailurePct > 5.0
| project Total, Failed, FailurePct
~~~

### This Is Only the KQL Portion

A scheduled query alert also requires configuring **frequency, evaluation period, threshold/condition, action group, scope, severity, managed identity, and dimensions** per Azure Monitor alert capabilities. Never paste raw KQL into production and assume an alert rule exists.

### Avoid the Low-Traffic Trap

1 failure out of 2 requests is 50%, yet rarely warrants paging on-call. **`Total >= 100`** is an illustrative guardrail; tune it to SLOs, traffic, critical endpoints, and observation windows. For critical payment or security errors, an alert may still be required even at low traffic.

### Avoid Relying on a Single Alert

Separate **high error rate, low availability, dependency latency, ingestion silence, Pod failures, and TLS errors** as needed. A query watching only `AppRequests` cannot detect a broken ingestion pipeline while the application keeps running.

## 58. KQL Alerts for Missing Telemetry: A Tricky Problem

If a system expects at least one request per interval, a query might look like:

~~~kusto
AppRequests
| where TimeGenerated >= ago(10m)
| where AppRoleName == "checkout-api"
| summarize ObservedRequests=count()
| where ObservedRequests == 0
~~~

### High Risk of False Alarms

- Applications may legitimately have zero traffic overnight.
- The agent/SDK might be disabled or ingestion delayed.
- `AppRoleName` may have changed after a release.
- Workspace scope changed, or tracing was sampled/dropped.

For **availability**, combine independent **synthetic tests / availability probes** with health metrics. A query showing zero logs is **insufficient** to distinguish a dead service from a broken observability pipeline.

## 59. Workbooks, Dashboards, and SLOs

KQL powers **Azure Monitor Workbooks** and supported dashboards:

~~~text
Service health workbook
   |
   +-- Requests/5 min
   +-- Failure rate (technical)
   +-- p95 latency
   +-- Top dependency targets/errors
   +-- AppExceptions by ProblemId
   +-- AKS Pod status/log categories
   +-- AzureActivity changes
   +-- Telemetry ingestion freshness
~~~

### Dashboards Differ from SLOs

A **dashboard** provides visibility; an **SLO** is a measurable objective, such as 99.9% of requests for a defined API set succeeding over a defined window.

Before encoding an SLO in KQL:

- Define which requests belong in the denominator.
- Specify which HTTP 4xx client errors are excluded from the SLI.
- Account for sampling, health probes, and endpoint mix.
- Decide how to segment by region and version.
- Align time windows and data sources.

Never define an SLO as **`Success==true`** without understanding your application's SDK and response-code semantics.

## 60. Managing Log Read Access and Sensitive Data

Logs can contain tenant IDs, resource paths, exception messages, IP/network metadata, or user details. Even though KQL is **read-only**, returning sensitive data to unauthorized users is still a security incident.

### Principles

1. Enforce **Azure RBAC** at workspace/resource/table scope under supported access modes.
2. Separate dev/test/prod workspaces and query scopes where needed.
3. Never grant workspace-wide log access just because a team needs health visibility for one app.
4. Redact secrets, tokens, passwords, connection strings, and payment/PII data at instrumentation time.
5. Restrict query exports, CSV downloads, workbook sharing, and screenshots.
6. Govern retention, auditing, and data residency.
7. Never use plain KQL filters as multi-tenant data isolation.

### Why Filters Are Not Authorization

If a user holds permissions across the whole workspace, they can simply delete **`where AppRoleName == "service-A"`**. Access boundaries must be enforced by the **platform**, not by query templates users voluntarily leave intact.

## 61. KQL Query Parameters and Query Safety

When embedding queries in APIs or automation instead of Portal copy-paste:

- Prefer **query parameters** or SDK/API-supported parameter binding.
- Validate resource scopes, start/end times, and maximum lookback limits.
- Never concatenate unvalidated user input directly into KQL strings.
- Cap query timeouts, row counts, and payload sizes per SLA/cost.
- Use a dedicated read-only identity with least privilege.
- Avoid logging full queries if they contain sensitive IDs.

### Fixed `let` Example for Learning

~~~kusto
let WindowStart = ago(1h);
let Role = "checkout-api";
AppRequests
| where TimeGenerated >= WindowStart
| where AppRoleName == Role
| summarize Events=count()
~~~

**`let` is just a KQL declaration**, not a defense against query injection if your Java code concatenates strings beforehand. Application code must enforce safe parameterization using the Azure Monitor Query SDK and service APIs.

## 62. Lab A: Learning KQL Entirely with `datatable`

**Goal:** run KQL over synthetic data inside any supported Logs/Kusto environment, **without needing real Azure tables**. This works well when workspaces are empty or learners lack production access.

### Sample Data

~~~kusto
let SampleRequests = datatable(
    TimeGenerated:datetime,
    AppRoleName:string,
    Name:string,
    Success:bool,
    DurationMs:real,
    ResultCode:string,
    OperationId:string
)
[
    datetime(2026-11-20T03:00:00Z), "checkout-api", "POST /checkout", true, 120.0, "200", "op1",
    datetime(2026-11-20T03:01:00Z), "checkout-api", "POST /checkout", true, 145.0, "200", "op2",
    datetime(2026-11-20T03:02:00Z), "checkout-api", "POST /checkout", false, 1800.0, "500", "op3",
    datetime(2026-11-20T03:03:00Z), "checkout-api", "POST /checkout", false, 2200.0, "503", "op4",
    datetime(2026-11-20T03:04:00Z), "checkout-api", "GET /health", true, 15.0, "200", "op5",
    datetime(2026-11-20T03:05:00Z), "catalog-api", "GET /items", true, 65.0, "200", "op6",
    datetime(2026-11-20T03:06:00Z), "catalog-api", "GET /items", true, 70.0, "200", "op7",
    datetime(2026-11-20T03:07:00Z), "catalog-api", "GET /items", false, 540.0, "500", "op8",
    datetime(2026-11-20T03:08:00Z), "checkout-api", "POST /checkout", true, 140.0, "200", "op9",
    datetime(2026-11-20T03:09:00Z), "checkout-api", "POST /checkout", false, 1900.0, "500", "op10"
];
SampleRequests
| summarize
    Total=count(),
    Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by AppRoleName
| extend FailureRate=round(
    100.0 * todouble(Failed) / todouble(Total), 1)
| order by FailureRate desc
~~~

### Exercises

1. Run the entire KQL block (`datatable` and query together).
2. Verify **`checkout-api` has 7 requests, 3 failed**; `catalog-api` has **3 requests, 1 failed**.
3. Add **`where Name != "GET /health"`** before `summarize` to see how health probes affect rates.
4. Change `summarize` to **`by bin(TimeGenerated, 5m), AppRoleName`** and inspect the buckets.
5. Add **`top 1 by P95Ms desc`** to identify the slowest service in the synthetic dataset.
6. Test **`project AppRoleName, Total, Failed, FailureRate`** to return only required columns.

### Key Takeaway

A p95 over 3–7 rows is purely illustrative. Never feed synthetic outputs into a production SLO dashboard. If a KQL editor requires table context before running `datatable`, verify syntax and the workspace query experience; `datatable` is an inline tabular constructor requiring no ingested records.

## 63. Lab B: Investigating Application Insights in a Lab Workspace

**Goal:** diagnose an application failure using `AppRequests`, `AppDependencies`, `AppExceptions`, and `AppTraces`.

### Preparation

- A **lab** workspace-based Application Insights instance populated with synthetic telemetry.
- Authorized query permissions; never pull production data without approval.
- `AppRoleName`/service identity confirmed in the schema.
- An incident time window provided by the learner/instructor.

### Steps

1. Open Logs with the right workspace/scope and select 1–2 hours around the incident.
2. Run **`AppRequests | take 5`** after a time filter to inspect the schema.
3. Summarize Requests, Failed, and p95 in 5-minute buckets.
4. Find the endpoint with the highest failed requests and check sample size.
5. Identify dependency targets with elevated failures or latency.
6. Group exceptions by **`ProblemId`**.
7. Pick an **`OperationId`** from a failed request.
8. Use a time-filtered `union` or `join` to inspect request, dependency, trace, and exception records.
9. Record **hypothesis + supporting evidence + missing telemetry**.
10. Never modify resources or databases from KQL; hand off remediation through an approved runbook.

### Acceptance Criteria

| Criterion | PASS When |
|---|---|
| Scope | Right Application Insights and workspace selected |
| Time | UTC window matches the incident |
| Request errors | Reports request count, failures, rate, p95, and denominator |
| Dependencies | Reports Target/Type/Success or notes missing instrumentation |
| Correlation | `OperationId` traced with limitations noted |
| Security | Zero tokens, PII, or raw request bodies exposed |
| Conclusion | Clearly separates observed facts from hypotheses |

## 64. Lab C: Investigating AKS and Azure Activity

**Goal:** determine whether an app failed due to container, cluster, or nearby resource changes without needing production write access.

### Preparation

- Lab AKS cluster with Container Insights / appropriate collection enabled.
- `ContainerLogV2`/`KubePodInventory` or equivalent tables populated.
- `AzureActivity` ingested/available within scope.
- Learner holds log read permissions.

### Steps

1. Identify the target namespace and time range.
2. Search **`ContainerLogV2`** for Java error, timeout, or OOM records.
3. Group by **`PodName`/`ContainerName`** to find which Pod emits the most errors.
4. Query **`KubePodInventory`** for the latest Pod status.
5. If `KubeNodeInventory`/`InsightsMetrics` exist, inspect anomalous nodes/metrics.
6. Query **`AzureActivity`** for write operations in the same window.
7. Build a UTC timeline comparing app errors, Pod states, and change events.
8. Distinguish **correlation** from **causation**.
9. If data collection is missing, document the absent tables and check agent/DCR/diagnostic settings per permissions—without escalating privileges or altering settings unilaterally.

### Question

If container logs show `OutOfMemoryError` yet `KubePodInventory` shows no restart evidence, can you conclude AKS OOM-killed the Pod?

**No.** A JVM **`OutOfMemoryError`** can occur inside the process without the OS/kernel OOM-killing the container; inspect Pod status, container termination reasons, memory limits, metrics, and timelines to confirm.

## 65. Lab D: Working with Missing Data and Different Schemas

**Goal:** avoid wrong guesses when queries return empty or fail on missing fields.

### Scenario 1

You paste an **`AppRequests`** query into a legacy Application Insights experience that only has **`requests`**. Do:

1. Open the schema browser.
2. Change the table to **`requests`**.
3. Map **`TimeGenerated → timestamp`**, **`AppRoleName → cloud_RoleName`**, **`OperationId → operation_Id`**, etc.
4. Check the data type of **`duration`** (timespan) before comparing against milliseconds.
5. Never blindly rewrite **`DurationMs > 1000`** as **`duration > 1000`**.

### Scenario 2

A workspace has **`ContainerLog`** instead of **`ContainerLogV2`**. Do:

1. Read the actual schema.
2. Find the text, `ContainerID`, and namespace columns in the right table.
3. Check the Container Insights collection version/configuration.
4. Never write queries mixing fields that do not exist.

### Scenario 3

`AzureDiagnostics` has zero rows for Azure SQL, yet the service emits diagnostics:

1. Check resource-specific tables.
2. Inspect diagnostic categories and destination workspace.
3. Check retention, collection gaps, and RBAC.
4. Never conclude SQL emitted no events.

## 66. Case Study 1: Checkout Latency Spikes After Deployment

**Context:** A Spring Boot checkout API runs on AKS, queries Azure SQL Database, publishes Service Bus messages, and receives traffic through Application Gateway.

~~~text
Browser
   |
   v
Application Gateway
   |
   v
AKS ingress -> checkout-api (Java)
                  |
                  +--> Azure SQL Database
                  |
                  +--> Service Bus
~~~

At **03:20 UTC**, version **v2** begins rolling out; shortly after, p95 jumps from under 300 ms to over 1,500 ms and 5xx errors climb. On-call needs the cause:

### Step 1: Quantify Impact

~~~kusto
AppRequests
| where TimeGenerated >= datetime(2026-11-20T03:00:00Z)
  and TimeGenerated < datetime(2026-11-20T04:00:00Z)
| where AppRoleName == "checkout-api"
| summarize
    Requests=count(), Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

### Step 2: Isolate Dependencies

~~~kusto
AppDependencies
| where TimeGenerated >= datetime(2026-11-20T03:00:00Z)
  and TimeGenerated < datetime(2026-11-20T04:00:00Z)
| where AppRoleName == "checkout-api"
| summarize
    Calls=count(), Failed=countif(Success == false),
    P95Ms=percentile(DurationMs, 95)
    by Type, Target
| order by Failed desc
~~~

### Step 3: Check Infrastructure

- `KubePodInventory`: are new Pods Pending/Failed in any node pool?
- `ContainerLogV2`: connection pool timeouts, SQL auth errors, or OOMs?
- `AzureActivity`: any storage, SQL, AKS, or network resource updates?
- AKS deployment/audit: did v2 roll out at the expected time and image digest?
- Azure SQL Metrics: did CPU, DTU/vCore, or connection counts surge?

### Two Hypotheses to Distinguish

**Hypothesis A:** v2 increased the JDBC pool size, and scaling to 30 Pods created a connection storm against SQL.

**Hypothesis B:** A network or identity change caused SQL requests to time out, and Pod retries amplified load afterward.

KQL reveals only the **matching traces and timeline**; confirm using code/config diffs, connection pool metrics, SQL diagnostics, and deployment events. Never roll back or scale the database based on a single chart alone.

## 67. Case Study 2: AKS Reports Errors While the App Still Returns HTTP 200

**Context:** A Java service's liveness endpoint keeps returning 200 while background consumers reading Service Bus stop processing. The HTTP Success dashboard looks green, yet the queue backlog grows.

### Why Request Queries Are Not Enough

~~~text
GET /health -> HTTP 200
                    |
                    v
             AppRequests.Success = true

Service Bus consumer loop stopped
                    |
                    v
             Business work not progressing
~~~

### KQL and Supplementary Data Needed

1. **`AppTraces`** for consumer started/stopped events and errors.
2. **`AppExceptions`** from the message-processing loop.
3. **`AppDependencies`** for Service Bus failures if instrumented.
4. **`ContainerLogV2`** for crashes, restarts, and timeouts.
5. **Azure Monitor Metrics** for Service Bus queue backlog and active messages.
6. **`KubePodInventory`** for Pod state instead of relying solely on HTTP health checks.

### Better Telemetry Design

Track **`last_message_processed_at`**, **`messages_processed_total`**, **`processing_failure_count`**, and **queue lag** via standardized metrics/logs, and alert when processing stalls even while Pods remain Ready.

**A passing liveness probe does not mean business processing is healthy.** KQL is only as good as the telemetry instrumented and shipped into the system.

## 68. 15-Step KQL Incident Investigation Runbook

A repeatable workflow prevents unbounded scans and premature conclusions.

### Phase A — Identify and Scope

1. **Confirm the incident:** symptoms, impacted users, SLO, severity, and timestamps reported by on-call.
2. **Normalize to UTC:** convert local reported times to UTC; record exact start/end bounds.
3. **Select subscription/workspace/resources:** Application Insights, Log Analytics, AKS, VMs, diagnostic settings.
4. **Verify telemetry availability:** populated tables, schemas, retention, sampling, ingestion lag, and RBAC.

### Phase B — Quantify Symptoms

5. **Request overview:** counts, failures, p95/p99 in 1–5 minute bins by `AppRoleName`.
6. **Narrow routes/releases:** `Name`, `ResultCode`, app version, or role instance if available.
7. **Dependency overview:** `Type`, `Target`, failures, and duration.
8. **Exceptions/traces:** `ProblemId`, error categories, and sample `OperationId` values.

### Phase C — Inspect Infrastructure

9. **AKS:** `ContainerLogV2`, `KubePodInventory`, nodes/metrics per actual tables.
10. **VMs/agents:** `Heartbeat`, `Perf`, or Azure Metrics where collected.
11. **Control plane:** `AzureActivity` and deployment/IaC logs.
12. **Resource diagnostics:** `AzureDiagnostics` or service-specific tables for SQL, Key Vault, Application Gateway, Service Bus, Storage, etc.

### Phase D — Verify and Conclude

13. **Build a timeline:** observed events and time windows, explicitly noting gaps.
14. **Validate hypotheses:** combine telemetry, release/config diffs, service metrics, and approved reproductions.
15. **Handoff:** write incident summary, owner-approved mitigation/rollback, and follow-up instrumentation/alert/retention improvements.

### Evidence Log Template

| Field | Example |
|---|---|
| Incident | checkout-incident-001 |
| First observed UTC | 2026-11-20T03:20Z |
| Scope | checkout-api / production workspace |
| User impact | Checkout failures rising; measured separately |
| Request evidence | FailurePct and p95 in 5m bins |
| Dependency evidence | Rising SQL target timeouts |
| Infrastructure evidence | Pod/connection metrics and deployment activity |
| Correlation | `OperationId`/`traceId` of sample requests |
| Missing data | No Service Bus consumer lag metric available |
| Hypothesis | Pool pressure post-rollout, unconfirmed |
| Action owner | SRE / service owner |
| Validation | Canary metrics and customer-facing health |

**Timestamps and incident IDs are illustrative examples**, not real incidents. Reports must distinguish **evidence-backed observations**, **hypotheses**, and **actions**.

## 69. Common KQL Mistakes

| Mistake | Consequence | Right Approach |
|---|---|---|
| Selecting the wrong workspace | Looks like zero data exists | Verify Application Insights/Log Analytics linkage |
| Omitting time filters | Slow queries, heavy scans | Filter `TimeGenerated` upfront |
| Ignoring timezones | Misreading incident timing | Standardize on UTC and state timezones |
| Using `requests` columns on `AppRequests` | Query errors or flawed logic | Check current schema |
| Using `count()` instead of sampling-aware totals | Wrong traffic estimates | Account for `ItemCount`/sampling |
| Grouping by raw URL/PII | Cardinality blowup and data exposure | Group by normalized `Name`/route |
| Using `avg` instead of p95 | Hides tail latency | Use percentiles with sufficient samples |
| Calling 1 error / 2 requests a 50% crisis | False alarm | Combine rate, volume, and business impact |
| Unbounded join across two huge tables | Row explosion and high cost | Filter, project, and roll up before joining |
| Treating `OperationId` as a unique row ID | Bad joins, double counting | Use `Id`/`ParentId`/span context |
| Unioning unneeded tables | Higher cost and noise | Union only required sources |
| Regex across every log | Expensive and brittle queries | Instrument structured fields |
| Replacing missing Duration with 0 | Artificially low p95 | Keep nulls and measure coverage |
| Assuming missing `AppDependencies` means no calls | Misses root cause | Check instrumentation |
| Treating `ContainerLogV2` ERROR as Pod restart | Wrong diagnosis | Check Pod termination/state/events |
| Treating `AzureActivity` as all data-plane ops | Misses SQL/Blob actions | Use resource diagnostics/audits |
| Assuming `AzureDiagnostics` is universal | Can't find logs | Check resource-specific tables |
| Treating `AppRequests` 200 as healthy business flow | Misses backlogs/worker failures | Track business metrics, queues, background workers |
| Treating `TimeGenerated` as ingestion time | Skewed timeline | Distinguish event time vs. ingestion time |
| Assuming zero rows equals zero errors | Missing telemetry/permissions/retention | Verify collection and freshness |
| Running ADX control commands in Logs | Unsupported command errors | Use Azure Monitor Logs operators/schemas |
| Pasting full exceptions/URLs into tickets | Leaks PII/secrets | Redact and enforce access control |
| Treating query filters as authorization | Callers can remove `where` | Enforce real RBAC/table/resource access |
| Treating correlation charts as root cause | Wrong mitigation | Verify across independent sources |
| Not versioning queries/runbooks | Hard to reproduce investigations | Version-control secret-free KQL |

### Focus While Learning KQL

The core skill is not memorizing syntax—it is **asking testable investigative questions**, choosing the right data, knowing telemetry limits, and recognizing when **you cannot yet conclude**.

## 70. Checklist Before Using Queries in Production

| Area | Check |
|---|---|
| Scope | Tenant, subscription, workspace, and resource confirmed |
| Tables | Existing tables, right schemas/columns, legacy vs. workspace-based checked |
| Timezone | UTC reference and UI time picker aligned |
| Time filter | Bounded window matching the incident |
| Resource filter | `AppRoleName`/`_ResourceId`/namespace applied where present |
| Data types | String/datetime/duration/dynamic conversions verified |
| Telemetry coverage | Instrumentation, sampling, drops, and ingestion lag checked |
| Counts | Row counts, `ItemCount` estimates, and distinct operations distinguished |
| Latency | p95/p99 units in ms with adequate sample size |
| Joins | Join keys, deduplication/rollups, and time filters on both sides |
| Dependencies | `Type`/`Target`/status interpreted per backend |
| AKS | Container logs not confused with Pod inventory/events |
| VMs | `Heartbeat` distinguished from availability and service health |
| Diagnostics | `AzureDiagnostics` vs. resource-specific tables verified |
| Activity | Control-plane changes separated from data-plane actions |
| Cost | Avoided full scans, `search *`, and oversized joins/unions |
| Table plan | Supported KQL operators, retention, and query limits checked |
| Privacy | Zero PII, tokens, or connection strings in query output |
| Authorization | Least-privilege workspace/resource/table Reader roles |
| Alerts | Volume threshold, frequency, false-positive checks, action group set |
| SLOs | Denominator, endpoint mix, sampling, and success definition clear |
| Dashboards | Missing telemetry never displayed as zero incidents |
| Correlation | `RequestId`/`OperationId`/trace propagation verified |
| Validation | Tested with synthetic/test incidents before production alerting |
| Handoff | Facts, hypotheses, gaps, UTC timeline, and action owner documented |
| Reproducibility | Queries versioned with parameters and schema assumptions |

## 71. Self-Check Questions

1. What is KQL, and how does Azure Monitor Logs differ from Azure Monitor Metrics?
2. What role does a Log Analytics workspace play in Azure monitoring?
3. Which table does workspace-based Application Insights typically use for requests?
4. Which columns differ between legacy Application Insights **`requests`** and **`AppRequests`**?
5. When `AppRequests` does not exist, what is the first thing to check?
6. Why constrain `TimeGenerated` before parsing text or JSON?
7. How does UTC affect incidents reported in Vietnam local time?
8. How do **`take 20`** and **`top 20 by TimeGenerated desc`** differ?
9. Distinguish **`has`**, **`contains`**, and exact equality matching.
10. How does **`project`** differ from **`extend`**?
11. What does **`summarize count() by bin(TimeGenerated, 5m)`** output?
12. Why is a 50% error rate across 2 requests insufficient to judge system health?
13. Does **`AppRequests.Success`** always represent business outcome?
14. Should an SQL dependency's **`ResultCode`** be treated as an HTTP status code?
15. How do average latency and p95/p99 differ operationally?
16. How does sampling create a difference between **`count()`** and **`sum(ItemCount)`**?
17. Why can p95 over sampled requests be skewed if sampling is ignored?
18. How do you find the top 10 failing endpoints while excluding health probes?
19. Is **`AppDependencies.Target`** guaranteed to be a unique Azure resource ID?
20. When should you query **`AppExceptions`** instead of searching `"ERROR"` in `AppTraces`?
21. How do dynamic `Properties` differ from JSON-encoded strings?
22. If `todouble()` fails to parse a value, what does KQL return and how should you handle it?
23. What are the drawbacks of using regex on unstructured logs?
24. What is `OperationId` used for, and is it a unique key for a single request row?
25. Why can joining `AppRequests` with `AppDependencies` multiply request counts?
26. How do **`leftouter`**, **`leftanti`**, and **`leftsemi`** differ?
27. What does **`arg_max(TimeGenerated, PodStatus)`** return?
28. Does **`dcount()`** produce an exact count of individual users?
29. Why is a before/after deployment comparison insufficient to prove causality?
30. How do you compare failure rates across application versions stored as a custom property?
31. What is the benefit of **`make-series`**, and what risk does `default=0` introduce?
32. How do event time and ingestion time differ?
33. What telemetry does **`ContainerLogV2`** typically hold?
34. Does a Java `OutOfMemoryError` automatically prove Kubernetes `OOMKilled`?
35. How do `KubePodInventory` snapshots differ from Kubernetes events?
36. Does a VM `Heartbeat` prove a REST API is healthy?
37. Do `Perf` and `InsightsMetrics` use identical columns and metric units across every OS?
38. When does `AzureMetrics` appear in Log Analytics?
39. Does `AzureActivity` primarily reflect the data plane or the management plane?
40. How do resource-specific tables differ from `AzureDiagnostics`?
41. Can `_ResourceId` separate prod from staging, and does it replace RBAC?
42. Why does joining events simply because they fall in the same 5-minute bucket not prove causation?
43. What should an optimized query do before joining two large tables?
44. When do log retention or table plans prevent a query from returning historical data?
45. Which components beyond KQL does a scheduled query alert require?
46. Does zero `AppRequests` over 10 minutes prove the application is down?
47. Why isn't an SLO just an undefined "Success Rate" chart?
48. In the checkout case study, which three data sources at minimum are needed to verify the failure?
49. In the Service Bus case study, why is HTTP 200 insufficient for service health?
50. How do you write an incident report separating **observed facts**, **hypotheses**, and **unknowns**?

## References

- Microsoft Learn — *Azure Monitor overview*: https://learn.microsoft.com/azure/azure-monitor/overview
- Microsoft Learn — *Log Analytics workspace overview*: https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-workspace-overview
- Microsoft Learn — *Log Analytics tutorial*: https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-tutorial
- Microsoft Learn — *Kusto Query Language overview*: https://learn.microsoft.com/kusto/query/?view=microsoft-fabric
- Microsoft Learn — *KQL tutorial*: https://learn.microsoft.com/kusto/query/tutorials/learn-common-operators?view=microsoft-fabric
- Microsoft Learn — *where operator*: https://learn.microsoft.com/kusto/query/where-operator?view=microsoft-fabric
- Microsoft Learn — *summarize operator*: https://learn.microsoft.com/kusto/query/summarize-operator?view=microsoft-fabric
- Microsoft Learn — *join operator*: https://learn.microsoft.com/kusto/query/join-operator?view=microsoft-fabric
- Microsoft Learn — *make-series operator*: https://learn.microsoft.com/kusto/query/make-series-operator?view=microsoft-fabric
- Microsoft Learn — *parse_json function*: https://learn.microsoft.com/kusto/query/parse-json-function?view=microsoft-fabric
- Microsoft Learn — *Azure Monitor Logs table reference*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/tables-category
- Microsoft Learn — *AppRequests table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/apprequests
- Microsoft Learn — *AppDependencies table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/appdependencies
- Microsoft Learn — *AppExceptions table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/appexceptions
- Microsoft Learn — *AppTraces table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/apptraces
- Microsoft Learn — *ContainerLogV2 table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/containerlogv2
- Microsoft Learn — *KubePodInventory table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/kubepodinventory
- Microsoft Learn — *AzureActivity table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/azureactivity
- Microsoft Learn — *AzureDiagnostics table*: https://learn.microsoft.com/azure/azure-monitor/reference/tables/azurediagnostics
- Microsoft Learn — *Azure Monitor Logs and metrics*: https://learn.microsoft.com/azure/azure-monitor/data-platform
- Microsoft Learn — *Application Insights telemetry model*: https://learn.microsoft.com/azure/azure-monitor/app/data-model-complete
- Microsoft Learn — *Application Insights sampling*: https://learn.microsoft.com/azure/azure-monitor/app/sampling-classic-api
- Microsoft Learn — *Azure Monitor Container Insights*: https://learn.microsoft.com/azure/azure-monitor/containers/container-insights-overview
- Microsoft Learn — *Azure Monitor diagnostic settings*: https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings
- Microsoft Learn — *Azure Monitor log alerts*: https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-create-log-alert-rule
- Microsoft Learn — *Azure Monitor Logs permissions*: https://learn.microsoft.com/azure/azure-monitor/logs/manage-access
- Microsoft Learn — *Azure Monitor Logs table plans*: https://learn.microsoft.com/azure/azure-monitor/logs/data-platform-logs
- Microsoft Learn — *Azure Monitor Logs query optimization*: https://learn.microsoft.com/azure/azure-monitor/logs/query-optimization
- Microsoft Learn — *Azure Monitor pricing*: https://azure.microsoft.com/pricing/details/monitor/
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/

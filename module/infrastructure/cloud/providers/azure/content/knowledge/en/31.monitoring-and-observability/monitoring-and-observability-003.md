# Log Analytics Workspaces and Log Retention Design

## 1. The Real-World Problem: How Long, Where, and Why Keep Logs?

A Java/Spring Boot application running on Azure App Service and AKS generates millions of records per day: HTTP access logs, application errors, container stdout, audit events, resource change notifications, and security events. Operations teams need to find incident root causes in minutes; security teams need to investigate across months; compliance auditors may need to retain certain evidence even longer.

If you dump all data into one place and keep every table forever, storage costs, query overhead, access complexity, and data leak risks all rise. If you delete logs too early, you lose the ability to investigate incidents or satisfy audit obligations. **Log Analytics Workspace** is a core component of **Azure Monitor Logs** that centralizes structured log data, enables querying via **Kusto Query Language (KQL)**, enforces access controls, supports alerting, and manages retention policies.

This lesson belongs to the **Monitoring and Observability** chapter of the **CLOUD_PROVIDERS_AZURE** module: spanning subscriptions/resource groups and Microsoft Entra ID through networking, compute, storage, data, monitoring, security, and cost management for Azure applications.

**Running scenario:** an ordering system comprising **orders-api** (Spring Boot on AKS), **payment-worker** (Azure Container Apps), Azure SQL, Storage, and Azure Key Vault. We design workspaces, classify logs, define retention periods, route sources, use KQL for investigations, and control costs. Numbers, resource names, and durations in this lesson are **illustrative assumptions**, not actual enterprise policy.

## 2. Learning Objectives

After studying this lesson, you will be able to:

1. Explain the roles of Azure Monitor, Log Analytics Workspaces, tables, and KQL.
2. Distinguish logs, metrics, traces, audit/security events, and archival evidence.
3. Choose between a centralized workspace model and splitting by environment, data class, region, and permissions.
4. Design ingestion with Azure Monitor Agent (AMA), Data Collection Rules (DCR), diagnostic settings, Application Insights, and the Logs Ingestion API.
5. Understand workspace-level retention, table-level retention, and the difference between **interactive/analytics retention** and **total/long-term retention**.
6. Classify table plans such as **Analytics, Basic, and Auxiliary** according to currently supported service capabilities and query requirements.
7. Propose a log retention matrix aligned with operational, legal, security, and budget goals.
8. Calculate ingestion throughput, GB/day, retained volume, and billing drivers.
9. Write KQL queries to find errors, compute p95 latency, filter by resource, and estimate data volume.
10. Design access control using Azure RBAC, resource-context/workspace-context modes, and query scopes.
11. Manage secrets/PII, redaction, data minimization, data residency, and immutable evidence exports.
12. Set up alerts, self-monitoring of the logging pipeline, and runbooks for missing logs, slow ingestion, and cost spikes.
13. Provision sample resources via Portal/CLI/IaC while modifying only authorized resources.
14. Complete labs on DCR/diagnostic settings, KQL, retention, and cost control.

## 3. Where Do Azure Monitor and Log Analytics Workspaces Sit?

~~~mermaid
flowchart LR
    AKS[AKS / Container Apps] --> AMA[Container Insights / AMA + DCR]
    VM[Azure VMs] --> DCR[AMA + Data Collection Rule]
    P[Azure SQL / Key Vault / Storage] --> DS[Diagnostic settings]
    JAVA[Java / Spring Boot] --> AI[Application Insights / OTel]
    CUSTOM[Custom application logs] --> ING[Logs Ingestion API + DCR]
    AMA --> LAW[(Log Analytics Workspace)]
    DCR --> LAW
    DS --> LAW
    AI --> LAW
    ING --> LAW
    LAW --> KQL[KQL queries]
    LAW --> ALERT[Azure Monitor alerts]
    LAW --> DASH[Workbooks / Dashboards]
    LAW --> RET[Table plans / Retention policy]
~~~

**Azure Monitor** is Azure's observability platform encompassing metrics, logs, alerts, and related components. A **Log Analytics Workspace** is the resource that stores log tables and serves as the management boundary for queries, access, costs, and retention. **Log Analytics** also refers to the KQL query experience in the Azure Portal; do not confuse the query UI with the workspace resource itself.

### 3.1. A Workspace Is Not a Log Folder

A workspace does not just store raw text files. Data is ingested into **tables** with typed column schemas; queries operate on table names, time ranges, fields, and KQL. Common fields include:

- **TimeGenerated**: event timestamp according to the source's semantics.
- **_ResourceId**: Azure resource identifier when supplied by the source.
- **_BilledSize**: record size measured in certain ingestion estimates.
- **_IsBillable**: indicates whether the record counts as billable under table semantics.
- Specific columns such as **Message**, **SeverityLevel**, **OperationId**, **ResultCode**, **Computer**, and **PodName**.

Not every table includes all of these columns; always inspect the actual schema before writing queries.

### 3.2. Metrics and Logs Do Not Replace Each Other

- **Metrics** fit high-frequency time-series tracking and alerting on aggregated numerical signals.
- **Logs** fit detailed investigations and joining/aggregating events with rich context.
- **Distributed traces** link spans across services using trace/correlation IDs.
- **Audit logs** record actions and actors/targets under dedicated retention and protection policies.

There is no need to push all available metrics into logs just to render a CPU chart; doing so increases ingestion and duplicates data.

## 4. From Event to Queryable Record

An event passes through multiple stages:

~~~text
Application generates event
   |
Logger / OpenTelemetry instrumentation
   |
Collector / Agent / Azure service diagnostic export
   |
Filter / transformation / schema mapping (if supported)
   |
Ingestion into the right workspace and table
   |
Interactive queries / alerts / workbooks
   |
Long-term retention / export / expiration
~~~

Each stage can drop, delay, or alter fields. Never assume that because an application printed a line to stdout, that line is guaranteed to be in the workspace.

### 4.1. Different Timestamps

- **Event time:** when the event occurred.
- **Collection time:** when the agent/collector received the data.
- **Ingestion time:** when the workspace received the data.
- **Query time:** when the operator runs a search.

These differences matter during backlogs or offline periods. KQL **TimeGenerated** typically reflects event time, while **ingestion_time()** helps measure ingestion latency on tables that support it.

### 4.2. Never Alter Timestamps Arbitrarily

If a logger writes local time without a timezone offset, cross-region incident investigations can misorder events. Standardize timestamps to UTC, preserve offsets when needed, and verify clock synchronization.

### 4.3. Event Identity and Duplicates

Collectors and retries can produce duplicates in some scenarios. If an audit event requires deduplication or verification, the application should emit a consistent **eventId/operationId**; the workspace does not inherently provide exactly-once business semantics for every source.

## 5. Classify Data Before Deciding Retention Periods

A key principle: **do not design retention with one blanket number for all logs**. Group logs by value and risk first.

| Group | Examples | Characteristics |
|---|---|---|
| Application diagnostics | Exceptions, failed HTTP calls, retries | Needs fast querying during incident response |
| Performance & telemetry | Request durations, dependencies, counters | High record count; eligible for sampling/aggregation |
| Container/host logs | stdout/stderr, syslog, Windows events | High volume; uneven signal-to-noise ratio |
| Azure platform diagnostics | Azure SQL, Key Vault, Storage | Depends on categories and resource settings |
| Control-plane activity | VM create/delete, policy edits, role assignments | Critical for audits and investigations |
| Security & access | Auth failures, policy denials, suspicious activity | Sensitive; requires restricted access |
| Compliance evidence | Permission changes, critical data access | May need long retention and immutability guarantees |
| Business events | OrderCreated/PaymentAuthorized | Not equivalent to technical logs; canonical state belongs in business systems |

### 5.1. Logs Are Not Business Systems of Record

An "OrderCreated" log line does not replace an Orders/outbox database table. Logs can be filtered, sampled, expired, or delayed; never use a Log Analytics Workspace as your primary transactional ledger.

### 5.2. Sensitive Data

Never log passwords, API keys, bearer tokens, SAS URLs, connection strings, full credit card numbers, or unnecessary personal data. **The best approach is never generating sensitive logs in the first place**, rather than relying solely on downstream masking.

### 5.3. Retention Policies Must Have Owners

Policies should specify: data category, owner, purpose, storage location, authorized readers, interactive horizon, total retention duration, deletion method, and legal hold mechanisms if applicable.

## 6. One Workspace or Many Workspaces?

No single workspace partitioning layout fits every organization. Decision factors include:

1. **Data residency/region:** where the data is legally allowed to reside.
2. **Access boundaries:** which teams are permitted to see which logs.
3. **Environment isolation:** whether dev/test/prod should share a workspace.
4. **Operational ownership:** one SRE team vs. multiple independent units.
5. **Cost ownership:** chargeback by subscription, team, or workload.
6. **Query experience:** how many resources must be joined during investigations.
7. **Retention/table plans:** whether log classes need distinct policies.
8. **Compliance/security:** whether audit logs require tighter access than application diagnostics.

### 6.1. Centralized Workspace Model

~~~text
Subscription A: App Service -----+
Subscription B: AKS ------------+--> central-ops-law
Subscription C: Azure SQL -------+
~~~

**Pros:** straightforward cross-resource correlation, querying, and unified governance. **Cons:** access control and chargeback become more complex; potential conflicts over region, retention, and security boundaries.

### 6.2. Environment- or Trust-Boundary Split Model

~~~text
dev subscriptions  --> law-dev
prod app resources  --> law-prod-ops
prod security logs  --> law-prod-security (when separate boundary is needed)
~~~

**Pros:** strong isolation of permissions and environments. **Cons:** cross-workspace querying and managing DCRs, dashboards, and IaC require more coordination.

### 6.3. Practical Guidelines

Do not create a separate workspace per Pod or per microservice merely because you have many deployments; one workspace can hold logs from many resources and filter by **_ResourceId**, table, service, and environment fields. However, if regulations or organizational policy mandate data separation, access boundaries outweigh unified-query convenience.

### 6.4. Cross-Workspace Queries Are Not Free

KQL can query across multiple workspaces and resources where supported, but doing so requires permissions at each scope and introduces latency, limits, billing, and security considerations. Never use cross-workspace queries as an excuse to ignore data residency rules.

## 7. Inside a Workspace

A workspace contains:

- **Tables:** schemas and data; some created by Azure per source, others custom.
- **Workspace settings:** default interactive retention, access control mode, replication, or other supported options.
- **Table-level settings:** plan and retention settings for eligible tables.
- **Data collection rules and associations:** routing and filtering for supported streams before entering tables.
- **Access permissions:** Azure RBAC on the workspace, resources, and associated query scopes.
- **Query & alert layer:** KQL, alert rules, workbooks/dashboards.
- **Network controls:** how sources and users connect, potentially including Azure Monitor Private Link Scope.

### 7.1. Workspace-Level vs. Table-Level Retention

A workspace has a **default retention** applied per service rules to tables without overrides. Eligible tables can configure dedicated retention. **Do not assume every table type supports the same limits or parameters.**

### 7.2. A Table Is Not a Storage Container

A workspace table holds data inside Azure Monitor Logs, not an Azure Storage container or Cosmos DB container. Do not apply Azure Storage lifecycle rules expecting them to manage Log Analytics retention.

### 7.3. Not Every Table Is User-Configurable

Some Azure-managed tables enforce limits on table plans, retention, or schema settings. Before configuring via ARM or CLI, verify table and service capabilities.

## 8. Common Tables in Azure Monitoring

| Table / Potential Source | Meaning | Notes |
|---|---|---|
| **AzureActivity** | Subscription control-plane events | Collected via activity log export / diagnostic settings |
| **AzureDiagnostics** | Some resource diagnostic logs | Legacy/shared mode can produce sparse wide columns; dedicated tables differ |
| **ContainerLogV2** | Container stdout/stderr via compatible collection | Useful for AKS Container Insights when configured |
| **KubePodInventory** | Kubernetes Pod inventory | Present when corresponding collection is enabled |
| **Heartbeat** | Machine/agent heartbeat data | Source/scope depends on configuration |
| **Perf** | Performance counters | Absent unless collected |
| **AppRequests** | Request telemetry in workspace-based Application Insights | Not all apps automatically write here |
| **AppDependencies** | Dependency telemetry | Tied to instrumentation and workspace-based mode |
| **AppTraces** | Application trace messages | Subject to sampling and filters |
| **CustomTable_CL** | Custom logs schema | Name/schema defined by design and Logs Ingestion API support |

### 8.1. Is a Missing Table Always an Error?

Not necessarily. A table may not exist yet because the source has emitted no data, the diagnostic category is disabled, or the service writes to dedicated resource-specific tables instead of **AzureDiagnostics**.

### 8.2. Use the Schema Explorer

In Log Analytics, inspect **Tables**, column schemas, and sample records. Never copy a KQL query referencing a **Computer** column onto **AppRequests** and assume that column exists.

### 8.3. Keep Table Names Aligned with Sources

If a category offers a standard resource-specific table, prefer it over dumping logs into an arbitrary catch-all custom table. Consistent schemas simplify parsing, alerting, and query cost control.

## 9. Ingestion Path 1: Azure Resource Diagnostic Settings

Many Azure services provide **Diagnostic settings** to route supported log/metric categories to destinations such as:

- Log Analytics Workspace.
- Azure Storage account.
- Azure Event Hubs.

Actual supported destinations and categories depend on the service and policy.

~~~mermaid
flowchart LR
    SQL[Azure SQL] --> SET[Diagnostic settings]
    KV[Azure Key Vault] --> SET
    STORAGE[Azure Storage] --> SET
    SET --> LAW[(Log Analytics)]
    SET --> ARCH[(Storage archive when configured)]
    SET --> HUB[Event Hubs / downstream]
~~~

### 9.1. Choose Categories Intentionally

A resource may expose many diagnostic categories. Enabling every category across every resource generates high ingestion volume without improving SLOs. Choose based on the questions you must answer: failed queries, denied secret reads, policy changes, or audit trails.

### 9.2. Resource-Specific vs. AzureDiagnostics

Some services allow dedicated/resource-specific tables instead of the shared **AzureDiagnostics** table, depending on the diagnostic setting and category. Choose based on current support, query schemas, and migration impact if switching modes.

### 9.3. Diagnostic Settings Are Not Retroactive

Creating a diagnostic setting typically captures events emitted after configuration. Do not expect historical events from before setup to appear in the workspace.

### 9.4. Separate Destinations for Different Goals

You can use Log Analytics for operational queries and a Storage account with appropriate retention/immutability for evidence archiving. Verify completeness, cost, permissions, and retention independently on each path; one does not substitute for the other.

## 10. Ingestion Path 2: Azure Monitor Agent and Data Collection Rules

For Azure VMs and supported hosts, **Azure Monitor Agent (AMA)** works with **Data Collection Rules (DCRs)** to collect and route data such as events, syslog, and performance counters.

~~~text
Azure VM / supported host
        |
Azure Monitor Agent
        |
Data Collection Rule (source + streams + destination)
        |
Log Analytics Workspace / target table
~~~

### 10.1. What Does a DCR Contain?

Depending on type, a DCR typically defines:

- **Data sources**: which streams/logs to collect.
- **Streams**: named data flows with defined schemas.
- **Destinations**: workspace or other supported targets.
- **Data flows**: mapping streams to destinations/tables, with KQL transformations where supported.
- **Associations**: linking the DCR to target resources/agents via supported mechanisms.

### 10.2. DCR Does Not Mean Every Table Supports Arbitrary KQL Transforms

Ingestion-time transformations have limits by stream, schema, table, and plan; only a subset of KQL operators and behaviors are supported. Do not paste an arbitrary investigation query into a DCR transform and expect it to deploy.

### 10.3. Legacy Agent vs. AMA

Older models like Log Analytics Agent/MMA exist historically; for new architectures, prefer **Azure Monitor Agent and DCR** per current guidance. When migrating, reconcile data coverage, table names, field names, and policies; avoid leaving both collectors active and causing duplicate ingestion.

### 10.4. Resources and DCRs Must Be Linked Properly

Installing AMA alone is not enough: the DCR must have a valid association or connection to the source, destination/table, and required permissions. A "healthy" agent does not guarantee syslog or Windows events are reaching the workspace.

## 11. Ingestion Path 3: AKS and Container Logs

For AKS, enable compatible monitoring integrations (such as Container Insights / Azure Monitor agent-based collection) to send container logs and Kubernetes telemetry to the workspace.

Common data includes:

- Container stdout/stderr.
- Pod/container metadata.
- Inventory and selected Kubernetes metrics/events.
- Application messages if the process writes to stdout/stderr.
- Additional streams depending on profile and configuration.

### 11.1. Do Not Log Every Request Body from Java

A Spring Boot service might emit one structured JSON line per failed request or a small sample of successful requests; logging full HTTP request bodies and auth headers on every request burns gigabytes and creates privacy risk.

### 11.2. Standardizing a JSON Log Event

~~~json
{
  "timestamp": "2026-11-20T10:15:00Z",
  "service": "orders-api",
  "environment": "prod",
  "level": "ERROR",
  "operation": "submitOrder",
  "correlationId": "req-7f21",
  "tenantHash": "t-2e1d",
  "errorCode": "DEPENDENCY_TIMEOUT",
  "durationMs": 2160
}
~~~

**Never** include card numbers, access tokens, secrets, or full customer profiles in log events. Hashing a tenant ID is only pseudonymization and does not by itself guarantee full anonymization.

### 11.3. Never Casually Sample Audit Logs

High-volume diagnostics and traces can be sampled when partial loss is acceptable. For audit and security evidence, define completeness requirements explicitly and avoid sampling if policy mandates full capture.

### 11.4. Evaluating ContainerLogV2 and the Logging Pipeline

Configure collection for the right namespaces, pods, and log levels. Check the real schema before writing queries, especially when migrating from older Container Insights tables/generations.

## 12. Ingestion Path 4: Workspace-Based Application Insights

**Application Insights** monitors application requests, dependencies, traces, exceptions, and distributed traces. With **workspace-based Application Insights**, application data links to a Log Analytics Workspace and becomes queryable in the corresponding tables.

### 12.1. Do Not Conflate Application Insights with Raw Service Loggers

Application Insights/OTel instrumentation captures request and dependency telemetry, while Java loggers capture business/application trace messages. Use both together by linking **traceId/operationId**, while avoiding double instrumentation and duplicate log ingestion.

### 12.2. Sampling and Retention

High-volume application telemetry can use appropriate sampling to control costs; never apply that sampling to audit records requiring completeness. Verify retention on the linked tables according to workspace-based settings and table-specific limits.

### 12.3. Trace Correlation

When a request travels through orders-api → payment-worker → Azure SQL, trace context connects the spans. If logs omit correlation identifiers, combining app logs with distributed traces becomes difficult and forces unreliable heuristics.

### 12.4. PII in Traces

Do not attach request headers containing Authorization tokens, passwords, or full URL query strings with secrets to span attributes. Observability must not become an unintended collector of sensitive data.

## 13. Ingestion Path 5: Logs Ingestion API and Custom Tables

When applications or external systems need to send custom logs, the **Azure Monitor Logs Ingestion API** (combining DCRs/streams, destinations, authentication, and custom tables) is a supported option per service configuration.

~~~text
Custom log producer
    |
JSON payload / batch
    |
Entra-protected Logs Ingestion API endpoint
    |
DCR stream + transformation
    |
Custom table, e.g. OrderAudit_CL
    |
KQL + retention / access control
~~~

### 13.1. Do Not Send Arbitrary API Keys

The Logs Ingestion API uses Azure Monitor's authentication and authorization model, typically built on Microsoft Entra ID and scoped roles. Do not confuse this API with legacy workspace shared-key ingestion.

### 13.2. Designing a Custom Table Schema

Minimal fields might include:

| Field | Type | Reason |
|---|---|---|
| TimeGenerated | datetime | Timeline |
| EventId | string | Correlation / deduplication |
| Service | string | Filtering |
| Environment | string | Filtering |
| TenantHash | string | Avoid direct identification |
| EventType | string | Classification |
| Result | string | Success / failure |
| DurationMs | real/int | Performance |
| CorrelationId | string | Trace linking |

### 13.3. Avoid Unbounded Dynamic Fields

A document with thousands of arbitrary attribute names makes schemas unmanageable, queries slow, and overhead high. Standardize naming, data types, and schema versions.

### 13.4. Ingestion Throttling and Retries

Custom producers should use sensible batching, bounded queues, `Retry-After` handling where applicable, deduplication by `eventId` if required by business logic, and dead-lettering when delivery fails. Never allow unbounded log buffering to trigger out-of-memory crashes when an endpoint is temporarily unavailable.

## 14. Table Plan Thinking: Analytics, Basic, and Auxiliary

Azure Monitor Logs offers **table plans** to balance query capabilities and cost. Common plan names include **Analytics**, **Basic**, and **Auxiliary**; features, retention/alert/query limits, per-table availability, and pricing can change over time.

| Criterion | Analytics | Basic | Auxiliary |
|---|---|---|---|
| Purpose | Observability/troubleshooting, interactive queries | High-volume logs with simpler query needs | Infrequently accessed, high-volume data |
| Queries | Richer KQL capabilities | Different query capabilities/limits than Analytics | Distinct limits and query models depending on features |
| Alerting | Generally suits supported log alert types | Verify current alert types and support | Verify support before relying on alerts |
| Retention | Supports interactive/total retention within limits | Do not assume identical to Analytics | Do not assume identical to Analytics |
| Cost | Balances query richness with ingest/retention | Different billing/query model | Dedicated billing model |
| When to use | App errors, requests, security investigations needing KQL | Verbose diagnostics and occasional lookups | Large volumes rarely queried immediately |

### 14.1. Plans Are Table Properties, Not Just Workspace Properties

Saying "the workspace has 30-day retention" does not mean all data shares the same query capability or price. Check the **table plan** and settings of each individual table.

### 14.2. Plan Changes Have Limits

Some built-in tables cannot switch to every plan; limits apply to update frequency, supported features, and retention settings. **Check table capabilities** before modifying production.

### 14.3. Do Not Pick Basic/Auxiliary for Security Detection Without Testing

If your SOC requires complex correlation, near-real-time alerting, or specific hunting capabilities, a cheaper plan with restricted query/alert features may break security requirements. Choose based on tested use cases.

### 14.4. Separate Retention from Plan

The table plan governs storage, query capabilities, and pricing model; retention governs how long data exists and how it is accessed in each phase. Decide both together, but do not treat them as the same setting.

## 15. Interactive Retention and Long-Term Retention: Two Time Layers

When designing Log Analytics retention, distinguish:

1. **Interactive/analytics retention:** the period during which data stays within interactive query scope according to the table's plan and query support.
2. **Long-term retention:** the extended period beyond the interactive window where supported by the feature/table; access may require search jobs, restore, or other service-specific workflows.
3. **Total retention:** the configured total lifespan, which may combine the interactive period plus the long-term portion.

~~~text
Event Time                                              Expiration
    |--- Interactive/analytics retention ---|
                                              |--- Long-term period ---|
    |---------------- Total retention ------------------------------|
~~~

### 15.1. Hypothetical Design Example

- Incident troubleshooting requires frequent lookups over **30 days**.
- Security investigations require **180 days** total retention.
- A subset of audit records must be kept under specific regulations, e.g., **365 days** or longer if approved.

**These are illustrative business horizons, not a claim that every table/plan supports these exact numbers.** Minimum/maximum bounds and actual billing vary by plan and product.

### 15.2. How Is Data Queried After the Interactive Period?

Do not assume a record in long-term retention can still be queried directly with every KQL operator or alert rule as if it were interactive. Depending on the table plan and features, it may require a **search job**, **restore**, or another supported mechanism—with distinct costs, delays, quotas, and permissions.

### 15.3. Long-Term Retention Is Not Immutability

Keeping a record for 365 days does not automatically provide **write-once-read-many (WORM)**/immutability or legal hold guarantees. If an audit demands tamper-proof storage and chain-of-custody evidence, use dedicated evidence storage, such as exporting to Azure Storage with an immutable blob policy where appropriate.

### 15.4. Reducing Retention Can Be Irreversible

Lowering retention can cause older data to be purged under service rules after the change takes effect. Before changing settings, review legal holds, regulatory retention, backups/exports, and the impact window. Never run a production CLI command just to "test" deleting data.
## 16. Designing a Retention Matrix for the Sample System

Do not start with "keep everything in the workspace for 180 days." Classify each data category by **investigative questions**, **access frequency**, and **compliance requirements**.

| Hypothetical Data Group | Potential Source/Table | Interactive Query Need | Total Retention Goal | Approach |
|---|---|---:|---:|---|
| Application error | AppTraces or table per logging pipeline | 30 days | 90 days | Analytics with table override if supported |
| HTTP request telemetry | AppRequests | 30 days | 60 days | Analytics with appropriate sampling |
| Container verbose log | ContainerLogV2 | 7–30 days | 30 days | Reduce volume pre-ingest; evaluate plan by feature |
| VM syslog/Windows events | Syslog/Event | 30 days | 180 days | DCR filtering by severity/category |
| Platform control-plane | AzureActivity | 90 days | 365 days | Check table capabilities and parallel audit source |
| Key Vault access audit | Corresponding diagnostic table | 90 days | 365 days | Isolate access; optionally export evidence |
| Custom business audit | OrderAudit_CL | 90 days | Per legal policy | Design schema/retention and immutable evidence if needed |

**The durations in this table are hypothetical requirements.** When applying them, verify retention/table plan limits, billing, privacy, data residency, and organizational policies. Never assume "must keep 365 days" applies universally to every company.

### 16.1. Add Owner and Disposal Action Columns

A production retention document should include:

~~~text
Data category | Owner | Source | Table
Interactive days | Total days | Allowed roles
Legal basis | Residency | Export requirement
Deletion method | Budget | Review date
~~~

### 16.2. When Logs Serve Multiple Purposes

One log stream might serve SRE for 30 days and security for 1 year. If the two groups have very different permission boundaries, consider separate pipelines/workspaces or an evidence export with separate ACLs instead of granting every developer read access to all security data.

### 16.3. Retention Does Not Guarantee Complete Data Collection

A 365-day retention goal means nothing if diagnostic settings were turned off for 20 days. Monitor ingestion health, coverage, and loss detection alongside table configuration.

## 17. Retention Horizons: A Timeline Example

Suppose an event occurs on **Jan 01** and the table is configured with 30 days interactive retention and 180 days total retention where supported.

~~~text
Jan 01                   Around Jan 31                Around late Jun
  |--------------------------|------------------------------|
      Interactive queries          Long-term retention
      (per table plan)             (different access method)
  |---------------------------------------------------------|
                       Total retention
~~~

### 17.1. Total Retention Is Not Simply Adding Two Numbers Mechanically

If **total retention = 180 days** and interactive = 30 days, the illustrative long-term portion spans roughly the remaining 150 days, not **30 + 180 = 210 days**. Verify actual API/Portal parameter meanings for your table and plan.

### 17.2. Timestamps and Expiration

The service may execute housekeeping and expiration on periodic schedules using specific ingestion/`TimeGenerated` semantics. Do not treat Workspace retention as a second-accurate deletion timer for strictly regulated data. When exact-day deletion is mandated, build verification procedures on the actual system and retain records.

### 17.3. Accessing Historical Data

If an investigation requires querying data past the interactive period but still inside total retention, operators must know the **search/restore procedure**, wait times, permissions, and costs. Runbooks need owners and verification steps. Do not wait for an incident to discover a table is on a plan that lacks the needed query capability.

### 17.4. Retaining Longer Than Table Limits

Consider an architecture that **exports logs to Azure Storage or another evidence store** with dedicated immutability and retention policies tailored to the source and requirements. That is a distinct system with its own permissions, costs, and retrieval procedures—not just bumping `retentionInDays`.

## 18. An Auditable Retention Selection Process

An 8-step method:

1. **Inventory**: list sources, tables, schemas, sizes, owners, data regions, and sensitivity labels.
2. **Use cases**: operational troubleshooting, alerting, threat hunting, audits, and legal.
3. **Interactive horizon**: how far back do you need fast query responses?
4. **Total horizon**: how long must data survive, including infrequently accessed data?
5. **Technical feasibility**: what retention, search, and alerts does the plan/table support?
6. **Access controls**: who can query per scope? Is a separate workspace needed?
7. **Cost model**: ingest GB, interactive retention, long-term retention, search/restore/export.
8. **Approval & review**: approve, deploy via IaC, verify, and review periodically.

### 18.1. Resolving Conflicting Requirements

Suppose SOC wants detailed logs for a year, while privacy policy limits identifiable data to 30 days. Do not arbitrarily pick the larger number. Align with legal, privacy, and SOC on purpose, redaction, access, required fields, and legal basis; aggregated metrics or redacted records can often replace raw identifiable payloads.

### 18.2. Retention Does Not Cover the Entire System Data Lifecycle

Azure Storage archives, SQL audits, Event Hubs Capture, Application Insights, and Log Analytics maintain independent policies. Maintain a **data map** tracking all existing copies instead of checking only one workspace.

### 18.3. Retention by Table or by Category?

Governance is simplest when each table holds data with relatively uniform retention and access requirements. If one table mixes categories with conflicting retention rules, table-level policies become awkward to optimize; consider splitting or routing appropriately.

## 19. Workspace Default Retention vs. Table Overrides

Workspace-level retention is a **baseline**, not a substitute for per-table policy. Suggested layout:

~~~text
Workspace: law-prod-ops
  Default interactive retention: 30 days (illustrative)

Tables:
  AppRequests        -> follow baseline or approved override
  AppTraces          -> independent total retention when supported
  ContainerLogV2     -> approved plan/retention
  AzureActivity      -> retention and compliance-specific controls
  OrderAudit_CL      -> policy-driven retention, secure access
~~~

### 19.1. Inspect Both `retentionInDays` and `totalRetentionInDays`

Interfaces and APIs may expose fields equivalent to **retentionInDays** (interactive) and **totalRetentionInDays** (total), though behavior and configurability depend on the table. Always read back settings after deployment rather than trusting that the IaC template took effect as assumed.

### 19.2. If a Table Follows the Workspace Default

Do not document in policy that a table is guaranteed to retain 30 days merely because the workspace default is 30. Individual table overrides or service-specific behavior may differ. Inventory settings directly from Azure resources to verify reality.

### 19.3. Planning Retention Changes

- Estimate affected volume, cost, and data that could expire.
- Check legal holds and impact on alerts and queries.
- Verify any associated plan changes.
- Back up or export per policy before shortening retention.
- Deploy with approval and audit logging.
- Read back settings after deployment.
- Monitor queries, alerts, and billing afterward.

## 20. Sizing Log Volume Before Committing to Retention

Suppose the illustrative system generates:

- **15 GB/day** of application/container logs before filtering.
- **5 GB/day** of platform/security logs.
- After valid sampling/filtering, application diagnostics drop to **8 GB/day**.
- Total ingestion becomes **13 GB/day**.

Rough order-of-magnitude estimate:

\[
\text{Volume}_{30d} \approx 13 \times 30 = 390\ \text{GB}
\]

\[
\text{Volume}_{180d} \approx 13 \times 180 = 2340\ \text{GB}
\]

**This is traffic arithmetic, not an Azure billing formula.** Azure Monitor has specific rules for billed data volume, plans/tiers, table retention, free data categories, compression/metadata, and pricing models.

### 20.1. Do Not Multiply Every Log Type by 180 Days

If 8 GB/day of app logs are kept for 30 days and 5 GB/day of security logs are kept for 180 days, simple steady-state logical data volume is roughly:

\[
8 \times 30 + 5 \times 180 = 1140\ \text{GB}
\]

This illustrates logical stored volume only—not interactive vs. long-term splits, index/storage overhead, or actual Azure billing.

### 20.2. Bursts and Growth

An incident can spike error logs 10x for hours. Cost forecasts must account for peak scenarios, release growth, container autoscaling, retry storms, and export duplication.

### 20.3. Measure Actual Ingestion

Never multiply logger line counts by average line size as an official bill estimate. Check workspace usage/billing metrics and actual tables, and reconcile against Cost Management invoices.

## 21. Cost Components to Include in Your Model

| Cost Driver | Why It Occurs | Reasonable Mitigation |
|---|---|---|
| **Data ingestion** | Records ingested into Azure Monitor Logs per table plan | Pre-ingest filtering, permitted sampling, concise structured logs |
| **Interactive/analytics retention** | Retaining data in fast-query scope past included allowances | Pick right-sized retention horizons |
| **Long-term retention** | Keeping data beyond interactive period where supported | Apply only to categories that require it |
| **Query charges** | Certain table plans, query modes, and search jobs incur per-scan fees | Narrow time ranges and improve selectivity |
| **Restore/search jobs** | Accessing long-term data per feature | Forecast investigative and recovery frequency |
| **Data export** | Exporting records to Storage/Event Hubs via supported features | Export only truly needed categories |
| **Storage archive** | Storing immutable/long-retention evidence | Lifecycle tiers and access policies |
| **Network/egress** | Cross-region transfers and destinations | Co-locate in the same region where appropriate |
| **Compute/agents** | AMA, OTel collectors, Java runtime overhead | Monitor CPU, heap, and pipeline load |
| **Dashboards/alerts** | Rule evaluations and telemetry ingestion per pricing | Optimize polling and queries |

### 21.1. Analytics vs. Basic/Auxiliary Is Not Just About Ingest Price

Different plans carry different query/alert/retention limits and separate query charges. Compare total cost based on **use case**, never on per-GB ingest price alone.

### 21.2. Retention and Reserved Capacity / Commitment Tiers

Some pricing options offer commitment tiers with usage discounts; evaluate them against workload stability, minimum/commitment terms, and traffic variance. Never assume a commitment tier is always cheaper than pay-as-you-go.

### 21.3. Development Data Volume

Debug logs in dev can be extremely noisy; isolating workspaces or using strict filters and short horizons prevents dev chatter from eating production operations budgets.

## 22. DCR Transformations: Dropping Noise Before Ingestion

For streams and tables supporting **ingestion-time transformations**, a KQL subset can filter records, scrub fields, or map schemas before data lands in the workspace.

**Conceptual logic example**, not ready-to-deploy DCR JSON for an arbitrary stream:

~~~kusto
source
| where Level in ("Error", "Critical", "Warning")
| project TimeGenerated, Level, Service, Message, CorrelationId
~~~

### 22.1. Benefits

- Drop unnecessary debug/verbose records.
- Trim long or useless fields.
- Standardize fields for querying.
- Reduce sensitive data exposure when transformations are supported and designed properly.

### 22.2. Limitations

- Not every data source or table supports transformations at the same stage.
- Only a subset of KQL operators is supported; syntax and stream names must match.
- Ingestion/processing charges follow specific pricing semantics.
- Over-aggressive transforms can drop records needed for forensic investigations.
- Changing a DCR can cause post-change logs to differ in schema from historical records.

### 22.3. Transforms Are Not a Standalone Security Control

If an upstream event already contains a secret, it may still sit in buffers, intermediate collectors, or elsewhere. Removing secrets **at the application source** takes higher priority.

### 22.4. Test Before Broad Rollout

Capture a lab sample stream, verify before/after event counts, schemas, KQL queries, and downstream alerts; roll out as a canary with rollback capability and confirm no critical sources lose data.

## 23. KQL Basics: Filtering Time, Tables, and Fields

KQL is a pipeline query language where stages connect via **|**. Example searching for errors in application traces:

~~~kusto
AppTraces
| where TimeGenerated >= ago(24h)
| where SeverityLevel >= 3
| project TimeGenerated, Message, OperationId, _ResourceId
| order by TimeGenerated desc
| take 100
~~~

**Preconditions:** workspace-based Application Insights actually contains the **AppTraces** table and the columns above. Verify severity numeric semantics against your source/SDK.

### 23.1. Filter Time Range First

Constraining time early reduces scanned data and latency. An un-scoped "all time" query can be slow and costly, especially on table plans with per-GB query charges.

### 23.2. Project Minimal Columns

Never run **project \*** to export entire records, PII, and custom dimensions when you only need `Message` and `OperationId`. Query outputs often get pasted into tickets, spreading sensitive data.

### 23.3. Do Not Confuse Message Text with Event Type

Searching with `contains` in log text works for ad-hoc exploration but is hard to standardize; for key events, emit dedicated **EventType**, **ErrorCode**, or **OperationName** columns for reliable aggregation.

## 24. KQL: Computing p95 Latency and Application Error Rates

Workspace-based Application Insights example:

~~~kusto
AppRequests
| where TimeGenerated >= ago(24h)
| summarize
    Requests = count(),
    Failures = countif(Success == false),
    P95LatencyMs = percentile(DurationMs, 95)
  by Name
| extend FailureRatePct = 100.0 * Failures / Requests
| order by P95LatencyMs desc
~~~

### 24.1. What Are p95 and p99 Used For?

- **p95**: 95% of requests finish at or below this latency.
- **p99**: inspects the tail latency of the slowest 1% of requests.
- **Average** can mask severe slowness affecting a subset of users.

If telemetry is sampled or missing records, interpret computed values carefully; never assume raw counts automatically equal all production requests.

### 24.2. Dimension Cardinality

Grouping by **Name** suits endpoint/operation names, whereas grouping by raw URLs containing user IDs or order IDs spawns millions of groups and exposes data. Normalize URL routes to **/orders/{id}** before emitting telemetry.

### 24.3. Inspect Real Schemas Before Editing Queries

**DurationMs**, **Success**, and **Name** belong to the corresponding Application Insights table/model; if querying a custom table, adapt to its actual column names. Never assume Application Insights is always running in workspace-based mode.

## 25. KQL: Investigating Resource Changes with AzureActivity

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| summarize Events = count()
  by OperationNameValue, ActivityStatusValue
| order by Events desc
~~~

### 25.1. Finding High-Risk Changes

Focus on operations such as RBAC modifications, resource deletions, network/firewall changes, or policy edits using the columns emitted by the source. Confirm exact operation names and categories on your actual subscription.

### 25.2. Control-Plane Does Not Cover All Data Access

**AzureActivity** does not log every secret read or SQL query row access. For data-plane auditing, enable the appropriate diagnostic categories on Key Vault, SQL, Storage, and related resources.

### 25.3. Audit Query Permissions

Those permitted to inspect changes and audit events often differ from developers debugging apps. Enforce RBAC and controlled audit exports; never share public query links containing sensitive details.

## 26. KQL: Observing Container Errors on AKS

~~~kusto
ContainerLogV2
| where TimeGenerated >= ago(1h)
| summarize Events = count()
  by PodName, LogLevel
| order by Events desc
~~~

**Note:** column names depend on the table schema and data collection version. If **LogLevel** is absent in your environment, substitute the actual field or parse the message per approved schema.

### 26.1. Pod Failures Are Not Always in Stdout

An OOMKilled Pod or scheduling failure often requires Kubernetes events/metrics and inventory, not just `ContainerLogV2`. Strong observability combines metrics + events + logs.

### 26.2. Multiple Replicas and Correlation

Search logs by service, namespace, pod, and request correlation ID. Never rely solely on `PodName`, as Pods are recreated frequently; include deployment labels, namespaces, and time ranges.

### 26.3. Container Restarts

When a Pod restarts, logs can be lost if the collector hasn't shipped them or the runtime rotates logs. Workspace retention applies only to ingested data—it does not protect uncollected stdout on the node.

## 27. KQL: Estimating Ingested Data Volume

On a table supporting **_BilledSize**:

~~~kusto
AppTraces
| where TimeGenerated >= ago(7d)
| summarize
    Records = count(),
    ApproxGB = sum(_BilledSize) / 1024.0 / 1024.0 / 1024.0
  by bin(TimeGenerated, 1d)
| order by TimeGenerated asc
~~~

This is a **column-based estimate over queried records**, not an official invoice. Differences arise from billable status, latency/time boundaries, data plans, and tables lacking `_BilledSize`.

### 27.1. Measure Total Workspace Consumption with Billing Telemetry

For chargeback and cost reconciliation, compare Azure Monitor usage metrics, the `Usage` table where applicable, table-level ingestion stats, and Azure Cost Management. Never extrapolate total workspace GB from a single 7-day query on `AppTraces`.

### 27.2. Mismatch Between TimeGenerated and Ingestion Date

If logs arrive late (for example, an agent offline for two days), filtering by `TimeGenerated` may not match the day ingestion was billed. When diagnosing pipeline issues, inspect **ingestion_time()** and service usage via supported methods.

### 27.3. Not Every GB Costs the Same

Analytics, Basic, and Auxiliary plans have different pricing dimensions; summing raw GB ignores query, retention, and export charges.

## 28. KQL: Measuring Ingestion Latency on a Supported Table

~~~kusto
AppTraces
| where TimeGenerated >= ago(24h)
| extend IngestedAt = ingestion_time()
| where isnotnull(IngestedAt)
| extend IngestionDelayMin =
    datetime_diff("minute", IngestedAt, TimeGenerated)
| summarize
    P50DelayMin = percentile(IngestionDelayMin, 50),
    P95DelayMin = percentile(IngestionDelayMin, 95)
  by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
~~~

### 28.1. Interpret Carefully

With **datetime_diff("minute", later, earlier)**, the result is **later - earlier** in minutes. Here, `IngestedAt` is expected after `TimeGenerated`. Clock skew, delayed batches, or bad timestamps can yield negative or anomalous values.

### 28.2. When `ingestion_time()` Is Unavailable

Not every table or plan populates `ingestion_time()` as expected. Use Azure Monitor ingestion metrics, collector health, or timestamps from both source and pipeline as supported.

### 28.3. Alerting on Latency

If security events must be queryable within 10 minutes, monitor ingestion latency and missing-event coverage—not merely whether the workspace exists or a query executes without syntax errors.

## 29. KQL: Avoiding Expensive Query Anti-Patterns

Common anti-patterns:

- Queries without a **TimeGenerated** filter.
- Running **search \*** across all tables/workspaces unnecessarily.
- Exporting all columns/text containing PII to CSV.
- Joining massive tables without filtering early.
- Summarizing by ultra-high-cardinality fields like `requestId`.
- Running complex alert evaluations too frequently.
- Querying a table plan with unsupported operators or alert rules.
- Treating KQL query results like a guaranteed-complete database transaction log.

### 29.1. Systematic Optimization

1. Filter time ranges and resources as early as possible.
2. Target only the tables holding the needed signal.
3. Project only necessary fields.
4. Aggregate on dimensions with moderate cardinality.
5. Limit output rows.
6. Measure execution time and scanned volume.
7. Test alert rules with synthetic events and historical data.

### 29.2. KQL Does Not Turn Logs into Immutable Proof

A query returning "0 failures" could mean data wasn't ingested, the table doesn't exist, the time window is wrong, or logs were filtered out. Always verify data completeness before declaring zero errors.

## 30. Queries and Alert Design Must Align with Retention

Suppose SREs need an alert when the app hits high failure counts in 5 minutes. A **scheduled query alert** using supported KQL might look like:

~~~kusto
AppRequests
| where TimeGenerated >= ago(5m)
| summarize Failed = countif(Success == false)
| where Failed >= 20
~~~

This is an **illustrative query**; actual thresholds, evaluation frequency, dimensions, and rule permissions are configured in the Azure Monitor alert rule per table plan and resource capabilities.

### 30.1. Retention Does Not Substitute for Alert Evaluation Windows

Keeping logs for 180 days does not mean an alert can evaluate a 180-day window or scan all history. Alerts normally evaluate short windows relying on high-quality telemetry and acceptable ingestion lag.

### 30.2. Long-Term Data Is Not for Real-Time Alerts by Default

If logs age into a long-term stage lacking interactive alerting, ensure threat detections run while the data is still in the supported interactive phase. Long-term retention for forensics serves a different purpose than early detection.

### 30.3. Verify Alerts with Failure Injection

Generate a safe synthetic test event or controlled lab fault, verify it lands in the table, matches KQL, fires the alert, and triggers the right action group/notification channel. Never stop at checking KQL syntax alone.

### 30.4. Alert Cost and Cardinality

An alert scanning broad logs every minute can drive up query costs or throttling. Align scopes, filters, and evaluation frequency with SLOs and capacity.
## 31. Azure RBAC: Who Can View Whose Logs?

A workspace may hold sensitive logs from many Azure resources. Access control must cover not only "who can open the workspace," but also **query scope**, **resource permissions**, **table restrictions** where available, and sensitive fields inside records.

### 31.1. Workspace-Context and Resource-Context

Azure Monitor Logs supports access models tied to workspace context and resource context:

- **Workspace-context:** users with appropriate workspace permissions can query data across the granted scope.
- **Resource-context:** depending on configuration and Azure Monitor capabilities, permissions on a resource can allow querying logs associated with that resource without granting broad access to the entire workspace.
- **Access control mode:** workspace settings govern how resource vs. workspace permissions apply.

**Do not assume resource-context safely filters every custom row of every table.** Records require valid resource association metadata and supporting table/query modes. Never rely on `WHERE tenantId = ...` in KQL as a tenant-isolation boundary if the user can query the raw table.

### 31.2. Which Role Fits?

Built-in roles such as **Log Analytics Reader**, **Log Analytics Contributor**, **Monitoring Reader**, or custom roles grant different permissions across scopes. Check exact **actions/data actions** against job duties: viewing logs, editing retention, changing diagnostic settings, creating alerts, or exporting data.

### 31.3. Separating Investigators from Administrators

| Organizational Role | Required Permissions | Avoid |
|---|---|---|
| SRE | Query app logs, view alerts/workbooks | Modifying workspace retention |
| Developer | View logs for assigned services | Reading org-wide secrets/audits |
| Security analyst | Query security/audit logs, investigate incidents | Altering ingestion pipelines by default |
| Platform admin | Manage workspaces/DCRs/IaC | Viewing all raw PII |
| Compliance auditor | Retrieve evidence per procedure | Editing or deleting event data |
| CI/CD identity | Deploy assigned resources | Subscription-wide Owner unless required |

### 31.4. Test Actual Access

Create test principals representing SREs, developers, security, CI/CD, and an unauthorized user; test queries in both workspace and resource contexts. Verify **access is denied** to out-of-scope tables/resources, not just that authorized cases succeed.

## 32. Microsoft Entra ID, Managed Identity, and Ingestion Permissions

Multiple principals are involved:

1. **Query users** in Portal/KQL.
2. **Application/collector managed identities** sending custom logs.
3. **Identities or service configurations** used by Diagnostic settings to export logs.
4. **IaC deployment identities** creating workspaces, DCRs, and permissions.
5. **Automation/runbook identities** querying, exporting, or auditing retention.

### 32.1. Never Use One Identity for Everything

A Java workload that only ingests custom logs should never have permissions to change workspace retention or grant RBAC to others. IAM principles: **least privilege, separation of duties, and auditing**.

### 32.2. Logs Ingestion API

Custom log ingestion requires authentication and authorization matching the DCR / Logs Ingestion API contract; roles and scopes must target the authorized DCR/destination. When using managed identity, never store long-lived tokens in source code or hardcode secrets in collector configs.

### 32.3. IaC and RBAC Are Two Separate Plans

A deployment might create a workspace cleanly yet fail to query logs because the identity lacks read permissions. Conversely, query permissions do not allow altering retention. Document caller principals and scopes for every step.

### 32.4. Token and Log Leakage

Never log bearer tokens or Key Vault secret values while "debugging HTTP headers." Even if logs only last 7 days, sensitive credentials entering the monitoring system constitute a security incident.

## 33. Network Security, Private Link, and Data Residency

A private architecture may involve **Azure Monitor Private Link Scope (AMPLS)**, Private Endpoints, DNS, and configurations spanning workspaces, data collection endpoints, and query endpoints depending on ingestion paths.

~~~mermaid
flowchart LR
    APP[Azure VMs / AKS collectors] --> VNET[Private VNet / DNS]
    VNET --> SCOPE[Azure Monitor Private Link Scope]
    SCOPE --> LAW[(Log Analytics Workspace)]
    USER[Secured analyst network] --> VNET
    LAW --> POLICY[Workspace/table retention]
~~~

### 33.1. Enabling One Private Endpoint Does Not Finish Everything

Azure platform Diagnostic settings, AMA/DCR, the Logs Ingestion API, and query clients use different networking paths. Verify the actual data path and supported features for each source type. Never assume all services "flow through the same private IP."

### 33.2. Data Collection Endpoint (DCE)

Some ingestion/DCR flows and Private Link scenarios use a **Data Collection Endpoint** or DCR-provided endpoints depending on API and source. Keep AMPLS, DCR, DCE, and DNS aligned; consult documentation for the exact API version and service.

### 33.3. DNS/TLS Troubleshooting

- Does the FQDN resolve to the expected public or private IP per network policy?
- Do proxies, NAT, and firewalls allow required traffic?
- Is the TLS trust chain intact?
- Are outbound restrictions or private DNS zones missing?
- Does the agent/collector have valid permissions and DCR associations?

Never disable TLS verification or open unrestricted public ingress as a workaround for missing logs.

### 33.4. Residency and Cross-Region Considerations

Workspaces live in specific regions, potentially different from log-producing resources; exports and cross-workspace queries can cross regions. Check data residency policies and data transfer costs before centralizing logs into another region.

## 34. Governance: Privacy, PII, and Data Deletion Lifecycle

A solid retention policy explains **what not to ingest**, **who can view it**, and **when to delete it**.

### 34.1. Data Classification

Example tiers:

- **Public telemetry**: request counts, aggregate latency.
- **Internal operational**: error codes, deployment metadata.
- **Confidential business**: tenant event payloads, customer IDs.
- **Restricted**: authentication material, sensitive personal data.

For restricted secrets, the default rule is **do not log them**. For correlation identifiers, consider pseudonymization/tokenization, short retention, and tight ACLs.

### 34.2. Multi-Layer Redaction

1. Redact in the Java logger/instrumentation.
2. Strip headers/query parameters at ingress/collectors.
3. Apply DCR transformations where streams support them.
4. Restrict query and export permissions.
5. Monitor for accidental secret leaks and maintain an incident response plan.

**Downstream redaction does not erase upstream copies** in app stdout buffers, collector files, or exported audit pipelines.

### 34.3. Personal Data Deletion Requests

Regulations may require deleting or restricting personal data. Map every system holding copies, check Azure Monitor's purge/delete capabilities, timing limits, and legal holds. **Never assume lowering retention to one day immediately fulfills a specific deletion request.**

### 34.4. Retention Reviews

Every 3–6 months (or per policy), review tables, owners, volumes, permissions, use cases, legal bases, costs, and historical retrieval readiness. Record outcomes with approver sign-off.

## 35. Audit Evidence, Long-Term Export, and Immutability

Certain events (role changes, secret access, critical financial actions) may require long-term tamper-evident retention.

### 35.1. Why Isn't Log Analytics a WORM System by Default?

Table retention controls how long logs remain stored. It does not by itself deliver audit-grade **write-once-read-many (WORM)** guarantees, legal holds, or chain-of-custody verification.

### 35.2. Reference Evidence Architecture

~~~mermaid
flowchart LR
    SOURCE[Security / audit events] --> QUERY[(Log Analytics)]
    SOURCE --> EXPORT[Authorized export path]
    EXPORT --> STORE[(Azure Storage)]
    STORE --> WORM[Immutability policy / Legal hold]
    QUERY --> DETECT[Detections / Investigations]
    WORM --> AUDIT[Compliance retrieval]
~~~

Depending on the service, you can use **Diagnostic settings** to export directly to Storage/Event Hubs or **Log Analytics data export** for supported tables. Export capabilities, fees, table compatibility, and start times vary; do not assume export retroactively includes historical records.

### 35.3. Azure Storage Immutable Blob Storage

Azure Storage provides **time-based retention/immutability policies and legal holds** on compatible accounts and containers. Evaluate:

- Policy scope.
- Who can set, remove, or lock policies.
- Required retention duration.
- Encryption, access logs, and backups.
- Retrieval process for audits.
- Cost and inability to delete early once properly locked.

### 35.4. Chain of Custody

For legal evidence, record export timestamps, sources, file hashes, manifests, owners, access history, and integrity verification steps. A CSV sitting in Storage does not become reliable legal evidence simply by being named "audit."

### 35.5. Never Treat Exports as Comprehensive Backups Without Testing Restore

Test locating the exact time window, schema, source, event counts, timestamps, and re-querying capability. If you expect to search or restore after 9 months, prove the supported workflow in a lab first.

## 36. Creating a Workspace via Azure Portal and CLI

Before making changes, use an authorized lab subscription, resource group, region, and budget. Never run administrative commands in production without approval.

### 36.1. Portal Workflow

1. Create or select resource group **rg-observability-lab**.
2. Create a **Log Analytics Workspace** named **law-observability-lab** in an approved region.
3. Verify workspace identity/resource ID, region, pricing, and baseline retention.
4. Configure appropriate access control and assign RBAC.
5. Connect data sources: diagnostic settings, DCR/AMA, or App Insights.
6. Verify at least one table receives data.
7. Open Logs and run a time-scoped query.
8. Set up lab alerts and budgets.
9. Document cleanup requirements.

### 36.2. Sample Azure CLI for a Workspace

Bash/WSL example; variables and commands are for running only in an **authorized lab account**:

~~~bash
RG="rg-observability-lab"
LAW="law-observability-lab"
LOCATION="southeastasia"

az account show --query "{subscription:id,name:name}" -o table

az group create \
  --name "$RG" \
  --location "$LOCATION"

az monitor log-analytics workspace create \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --location "$LOCATION" \
  --sku PerGB2018 \
  --retention-time 30

az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --query "{id:id,retention:retentionInDays,location:location}" \
  -o json
~~~

**`southeastasia` is an illustrative region, not universally optimal for every organization.** CLI extensions, versions, and SKU capabilities change: before automating, check `az monitor log-analytics workspace create -h` and compatibility in your actual environment. **This is not output from an executed command.**

### 36.3. Do Not Assume the Workspace Immediately Contains Data

Right after creation, a workspace has no log sources connected. Wire diagnostic settings or DCRs, emit a test event, and wait for ingestion; an empty workspace is expected before pipelines exist.

### 36.4. Never Delete Resource Groups Blindly

During cleanup, confirm it is an isolated lab RG with no shared resources and has approval. Deleting the wrong RG can destroy unrelated Azure resources.

## 37. Inspecting and Configuring Table Retention via CLI

When a table exists and its plan supports configuration, Log Analytics workspace table CLI commands can read and update settings.

~~~bash
RG="rg-observability-lab"
LAW="law-observability-lab"

az monitor log-analytics workspace table list \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --query "[].{name:name,plan:plan,interactive:retentionInDays,total:totalRetentionInDays}" \
  -o table
~~~

Example **illustrating how to request a change** on a retention-configurable table:

~~~bash
az monitor log-analytics workspace table update \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --name AppTraces \
  --retention-time 30 \
  --total-retention-time 180
~~~

### 37.1. Key Constraints

- The **AppTraces** table must exist in the workspace.
- The table must support the requested retention and plan settings.
- Appropriate administrative permissions on the workspace are required.
- CLI/API versions may change flag names and limits.
- Lowering retention on a populated system can trigger data deletion.
- 30/180 are hypothetical lab policy numbers.

**Never run an update command in production without reviewing retention policy, data age, legal holds, and approvals.**

### 37.2. Readback After Changing

~~~bash
az monitor log-analytics workspace table show \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --name AppTraces \
  -o json
~~~

Verify **plan**, **retentionInDays**, **totalRetentionInDays**, table name, and effective settings. If the table does not allow overrides, stop and report the blocker rather than switching to another table to bypass the check.

### 37.3. Do Not Rely on a Dashboard Setting to Represent Retention

A workbook or dashboard may reflect intended config rather than actual resource state. For audits, read settings directly from Azure resources or APIs and archive evidence with the change record.

## 38. Infrastructure as Code: Baseline Workspace with Bicep

Illustrative Bicep resource:

~~~bicep
param location string = resourceGroup().location
param workspaceName string = 'law-observability-lab'

resource law 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

output workspaceResourceId string = law.id
~~~

### 38.1. Watch the API Version

The API version in this example is an illustrative contract, not guaranteed to be the newest or support every feature at runtime. **Verify ARM/Bicep schemas and regional capabilities before deploying**, adjusting versions to organizational standards.

### 38.2. DCRs and Diagnostic Settings Are Also IaC Resources

Beyond the workspace, a complete setup declares:

- DCRs and associations for AMA.
- Diagnostic settings on each resource.
- Workspace-based Application Insights linkage if used.
- RBAC assignments and networking/private-link resources.
- Table retention/plan policies where supported by API.
- Alert rules, action groups, and workbooks.
- Budgets, tags, and self-monitoring alerts.

### 38.3. Table Retention Changes Need Change Control

Because lowering retention can make data unqueryable or expire records permanently, require separate approvals for retention policies compared to routine Java app releases. IaC drift detection should distinguish justified emergency operator changes from unapproved drift.

### 38.4. Do Not Treat IaC State as Proof of Log Collection

IaC can provision a DCR cleanly while the collector sits offline or lacks permissions. Verify end-to-end with a synthetic event and KQL readback.

## 39. Monitoring the Workspace and Ingestion Pipeline Itself

This is **observability of observability**: if a collector dies, operators must know before a major outage hits.

### 39.1. Health Signals

| Signal | Interpretation |
|---|---|
| Latest event timestamp by source | Is the source still sending data? |
| Ingestion delay p95 | Are logs arriving late? |
| Collector/AMA health | Is the agent connected with the right DCR? |
| Record count by category | Did event counts drop abnormally? |
| Error/retry/drop counters | Is the pipeline losing data? |
| Workspace ingestion volume | Did volume spike unexpectedly? |
| Table schema changes | Did a pipeline transform/SDK break KQL? |
| Query/alert execution failures | Are alerts still running? |
| Export destination health | Is long-term evidence still being written? |
| Daily cost estimate | Are we breaching budget? |

### 39.2. Missing-Data Alerts

If `payment-worker` normally emits heartbeats or synthetic events every few minutes, alerting after 15 minutes of silence can catch a broken pipeline. Carefully distinguish **an application legitimately emitting no events** from **pipeline data loss**.

### 39.3. Preventing Blind Spots

If an ingestion failure alert depends solely on the same workspace losing data, it may fail to fire. Consider independent health signals (Azure metrics, agent health, resource alerts, external synthetic checks, or a secondary monitor) for critical systems.

### 39.4. Noisy Logging Is Also an Operational Incident

An exception loop multiplying logs 50x can exhaust budgets and bury vital signals in noise. Use rate-limited loggers, appropriate deduplication/sampling, and upstream retry-storm controls.

## 40. Security Operations and Incident Response Log Retention

An investigation process must define:

1. **Time window** needed for retention and querying.
2. **Evidence sources** and completeness levels.
3. **Permissions** for investigators.
4. **Preservation steps** before retention expiration.
5. **Export capability** and integrity verification.
6. **Privacy boundaries** when sharing incident data.
7. **Disposal plan** once legal holds and retention obligations end.

### 40.1. When an Incident Happens Near Expiration

Investigators must know the interactive/long-term horizons and approved preservation/export workflows. Emergency retention increases require permissions, propagation time, and cost approval; never assume expired records can be "resurrected."

### 40.2. Log Completeness Defines Evidence Quality

A handful of events does not prove an entire attack or failure chain. Cross-check `AzureActivity`, Key Vault audits, `AppRequests`, Service Bus telemetry, or other relevant sources, and document any gaps explicitly.

### 40.3. View Permissions vs. Export Permissions

Exporting logs to CSV files or screenshots spreads data outward; govern recipients, retention, and auditing. Policies may restrict moving logs outside the tenant or region.

### 40.4. Documenting a Historical Log Retrieval Runbook

Document steps for inspecting table settings, selecting query ranges, running search/restore jobs where supported, extracting results, verifying sources, and cleaning up temporary investigation artifacts.
## 41. Runbook: Logs Missing in Workspace

**Scenario:** `orders-api` returns HTTP 500 errors, yet no matching `AppTraces` appear in Log Analytics.

### Step 1 — Confirm Events Were Emitted

Check application logger/tracer config, log levels, sampling, and container stdout. Were records dropped at the source by a filter or host log rotation?

### Step 2 — Confirm the Right Source and Table

- Does the app use workspace-based Application Insights or a custom collector?
- Do logs land in **AppTraces**, **ContainerLogV2**, **AzureDiagnostics**, or a custom table?
- Is the investigator querying the right workspace ID and region?
- Did a recent DCR or diagnostic setting change the destination?

### Step 3 — Check Timestamps

Compare **TimeGenerated**, UTC offsets, ingestion time, and query filters. An agent coming back online may deliver delayed batches.

### Step 4 — Inspect Collectors and Configuration

Check AMA/DCR associations, Container Insights config, OpenTelemetry exporters, service identities, network/DNS/firewalls, and Logs Ingestion endpoints. For diagnostics, verify enabled categories and exact resource IDs.

### Step 5 — Check KQL Permissions

The user may lack workspace/table query permissions or be scoped to a resource context excluding those logs. Test with an appropriately authorized principal rather than granting broad admin rights as a workaround.

### Step 6 — Check Volume, Drops, and Retries

Does the collector show errors or full queues? Is the workspace/ingestion API throttling? Is a transformation dropping severities/categories or altering schema so queries miss records?

### Step 7 — Emit a Safe Synthetic Event

Send one test log with a unique `EventId` and zero PII from the real source; record the UTC timestamp and search the target table by correlation ID. If the synthetic event does not appear, narrow down the failing pipeline hop.

### Step 8 — Document the Incident

Record the outage window, scope of affected data, root cause, recovery steps, whether backfilling is possible, and any investigative blind spots. **Never say "zero errors" merely because logs are missing.**

## 42. Runbook: Sudden Spike in Ingestion Volume and Cost

**Scenario:** Workspace jumps from 10 GB/day to 70 GB/day after a release.

### Step 1 — Verify the Signal

Cross-check Azure Monitor usage/billing metrics and Cost Management by day/hour, workspace, and table. Rule out day-count differences, delayed ingestion catch-up, and billing windows.

### Step 2 — Locate the Growing Source

Check top tables, Azure resource IDs, services, environments, and severity categories. Was a new diagnostic setting enabled or a duplicate collector introduced?

### Step 3 — Inspect Application Changes

Check for debug/trace logging left on in production, exception retry loops, large request body logging, duplicate OpenTelemetry exporters, excessive container restarts, or batch replays.

### Step 4 — Trim with Control

Suppress noisy logging at the source, tune sampling for application diagnostics, fix retry loops, and refine DCR filters on supported streams. **Never disable required audit/security categories** or legal/compliance-approved retention.

### Step 5 — Review Table Plans and Retention

Does a more suitable table plan exist for high-volume data? Do existing queries or alerts depend on that table? Any retention change requires change approval and historical data review.

### Step 6 — Put Guardrails in Place

Configure daily budget alerts, ingestion thresholds, clear owners, and policy-as-code/IaC drift checks. If configuring a daily ingestion cap, account for the risk of **dropping critical data**—never use a cap as a substitute for logging hygiene.

### Step 7 — Post-Change Verification

Re-measure GB/day, operational visibility, alert coverage, error rates, and cost forecasts. Declare optimization successful only if required signals remain intact and incident investigations still work.

## 43. Runbook: Mandatory Retention Reduction

A request to shorten retention from 180 days to 30 days can affect live data and legal investigations.

1. Confirm the exact **workspace, table, region, and owner**.
2. Read current policies and active regulatory/legal holds.
3. Verify current interactive retention, total retention, and table plan.
4. Estimate data falling outside the new threshold, including open investigations.
5. Check all copies (exports, Storage, backups) and delete rights.
6. Obtain approvals from SRE, security, privacy/legal, and the owner.
7. Prepare a rollback plan **before data expires**; rolling back configuration will not restore purged records.
8. Test on a lab or representative table where feasible.
9. Deploy via reviewed IaC/CLI and record the activity ID/changelog.
10. Read back plan/interactive/total retention after deployment.
11. Verify alerts, KQL, search/restore workflows, and billing.
12. Document effective timestamps and compliance evidence.

**Never casually run data purge/deletion tools in production**—purge follows separate semantics and constraints and is not equivalent to adjusting retention policy.

## 44. Lab 1: Create a Workspace and Collect Platform Diagnostics

**Preconditions:** use authorized lab Azure resources with controlled billing. Never enable categories containing PII on production resources just for testing.

### A. Create the Workspace

1. Pick your lab subscription and resource group.
2. Create a Log Analytics Workspace in an approved region.
3. Set an illustrative lab default retention within service limits.
4. Record the workspace resource ID, region, and access control settings.
5. Grant minimal query-read permissions to the test operator.
6. Record the pricing SKU and cost budget.

### B. Enable Diagnostic Settings

1. Choose a lab resource supporting diagnostic logs, such as a lab Key Vault or lab Azure SQL.
2. Open **Monitoring → Diagnostic settings**.
3. Inspect the actual supported **log categories** on that resource.
4. Select only the category to test, targeting the lab workspace.
5. Save and verify the setting attaches to the right resource.
6. Perform an appropriate test action (without exposing secrets or PII).
7. Wait for ingestion per service behavior and confirm the table appears.

### C. KQL

Depending on the schema/destination in use, query the actual table:

~~~kusto
AzureDiagnostics
| where TimeGenerated >= ago(2h)
| summarize Events = count() by Category
| order by Events desc
~~~

Use this query only if the category writes to **AzureDiagnostics**. If the service uses a resource-specific table, adapt the table name and schema. Do not treat a 0-row result as a failure until you verify log emission and ingestion.

### D. Verification

| Check | Value to Record |
|---|---|
| Workspace in approved region | Actual region |
| Diagnostic setting on right source | Resource ID |
| Category enabled | Category name |
| Log table receiving events | Table name |
| First/last event UTC | Timestamp |
| Time delay | Measured latency |
| Permissions | Who can/cannot query |

### E. Cleanup

Disable test diagnostic settings, remove lab resources **only when authorized**, and verify billing so no orphaned workspaces, storage, or compute remain.

## 45. Lab 2: KQL, Alerts, and Measuring Ingestion

### A. Data

Use workspace-based Application Insights for a lab app or an already populated log table. Do not generate millions of real events.

### B. Three Core Queries

**Find errors:**

~~~kusto
AppTraces
| where TimeGenerated >= ago(1d)
| where SeverityLevel >= 3
| summarize Errors = count() by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
~~~

**Measure request p95:**

~~~kusto
AppRequests
| where TimeGenerated >= ago(1d)
| summarize Requests=count(),
            P95Ms=percentile(DurationMs, 95)
  by bin(TimeGenerated, 1h)
| order by TimeGenerated asc
~~~

**Estimate billed size by table:**

~~~kusto
AppTraces
| where TimeGenerated >= ago(1d)
| summarize ApproxGB =
    sum(_BilledSize) / 1024.0 / 1024.0 / 1024.0
~~~

These queries require existing tables and columns. If a table does not exist, query the table corresponding to your enabled source; never inject dummy production data just to "make queries return rows."

### C. Alert

1. Pick a metric or scheduled KQL query supported by the table plan.
2. Configure evaluation window, threshold, severity, and a test action group.
3. Trigger a safe synthetic error event in the lab environment.
4. Confirm the alert fires as expected without PII in notifications.
5. Disable the alert after the lab to avoid spam notifications.

### D. Results

Measure record counts, query latency, ingestion delay, p95 request latency, approximate volume, and alert detection delay. Compare event timestamps against when records appear in the workspace.

## 46. Lab 3: Modeling Table-Level Retention Policies

### A. Build a Sample Policy Matrix

~~~text
Table              Interactive     Total
AppTraces          30 days         90 days
AppRequests        30 days         60 days
ContainerLogV2     30 days         30 days
Security audit     90 days         365 days
~~~

**Numbers are illustrative requirements only.** Verify whether each table supports these values and how the current service applies retention and plans.

### B. Inspect Existing Tables

1. Open Workspace → Tables.
2. Record table name, current plan, interactive retention, and total retention.
3. Check table capabilities and limits.
4. Compare against requirements and identify gaps.
5. If a table does not exist yet, do not assume it can be pre-configured immediately.
6. Identify who holds authority to approve and apply changes.

### C. Lab Experiment

1. Pick a lab table holding synthetic data that allows retention edits.
2. Read the current plan/retention via Portal or CLI.
3. Modify one parameter **strictly per approved plan**.
4. Read back and log before/after values.
5. Verify query behavior and alerts.
6. Revert per change plan if safe and no data was lost.
7. Never test lowering retention on real compliance data.

### D. Historical Investigation

Simulate a scenario where events are past the interactive window yet still inside total retention. Document the steps to access them via search job/restore (if supported) and estimate delay and cost. Never fabricate query outputs if you lack actual data spanning that horizon.

### E. Deliverable

Each group submits a policy matrix with table capabilities, roles, estimated volume/GB, and a change approval record.

## 47. Lab 4: Access Verification and Evidence Protection

### A. RBAC

Create test personas/identities with scoped permissions:

- Developer can view only relevant application diagnostics.
- SRE can query the operational scope.
- Security analyst can investigate security logs.
- IaC identity manages only the assigned scope.
- Unprivileged test identity cannot query sensitive data.

Test both access attempts that **must succeed** and attempts that **must be denied**. Verify workspace-context and resource-context behavior as designed.

### B. Data Minimization

1. Have the app emit a synthetic event with a tokenized customer identifier.
2. Verify logs contain no emails, passwords, or access tokens.
3. If DCR transforms are supported, test filtering debug logs or projecting fields in the lab.
4. Compare before/after event counts.
5. Ensure filtering does not drop required audit evidence.

### C. Evidence Export

1. Select one **synthetic** audit event.
2. Export the record and manifest via an approved method.
3. Verify source ID, timestamp, event count, and checksum.
4. If the lab includes an approved immutable Storage policy, test retention locking on dedicated lab storage.
5. Verify read/download rights and post-retention cleanup procedures.
6. Note that storing an exported copy does not automatically alter Log Analytics retention.

### D. Cost and Security Review

Compile a summary table of ingest GB/day, table plans, total retention, exports, access roles, and logs dropped at the source. Assess the balance between investigation coverage, privacy exposure, and cost.

## 48. Production Deployment Checklist

- [ ] Owners and use cases identified for every log group.
- [ ] Mapped which Azure resources emit logs and which use DCR/AMA/Diagnostic settings/App Insights.
- [ ] Diagrammed ingestion paths from applications to tables.
- [ ] Reconciled completeness and ingestion latency.
- [ ] Workspace topology aligns with region, data residency, and trust boundaries.
- [ ] Dev/test/prod logs have separated permissions and budgets.
- [ ] Avoided creating a separate workspace per Pod without justification.
- [ ] Schemas and correlation IDs standardized across services.
- [ ] No passwords, keys, bearer tokens, SAS URLs, or unnecessary PII logged.
- [ ] Logging levels and sampling reviewed per category.
- [ ] Critical audit/security events are not arbitrarily sampled.
- [ ] Table plans (Analytics/Basic/Auxiliary) chosen based on real query, alert, and retention capabilities.
- [ ] Checked per-table support and limits before switching plans.
- [ ] Workspace default retention inspected and documented.
- [ ] Table overrides and total retention verified.
- [ ] Policy separates interactive horizon from total horizon.
- [ ] Owner, retention basis, review date, and disposal workflow defined.
- [ ] Legal hold/compliance evidence does not rely on a single log query.
- [ ] Where WORM is required, an export path and Azure Storage immutability policy exist.
- [ ] Exported data verified for completeness, schema, and checksums.
- [ ] IAM separates workspace readers, developers, security, and admins.
- [ ] Resource-context access is not mistaken for row-level tenant isolation.
- [ ] Azure Monitor Private Link Scope / DCR / DCE / DNS verified where private networking is needed.
- [ ] Managed identities have scoped ingest permissions without extra admin rights.
- [ ] DCR transformations used only on supported streams with regression tests.
- [ ] Diagnostic settings free of unintended duplicate ingestion.
- [ ] KQL queries constrain time/resource/table and avoid dumping PII.
- [ ] Scheduled alerts match plan/table support and are tested with synthetic events.
- [ ] Alerts exist for silent data sources and ingestion lag.
- [ ] Independent health monitoring exists for critical logging pipelines.
- [ ] Table-level volume and daily cost monitored.
- [ ] Peak logging bursts and export/long-term search costs estimated.
- [ ] Budget alerts and ingestion spike runbooks in place.
- [ ] Retention changes follow IaC, approvals, and readback checks.
- [ ] Backups/exports completed before reducing retention if required by policy.
- [ ] Team understands IaC rollback cannot recover expired logs.
- [ ] Runbooks ready for missing logs, query failures, 429/ingest delays, and schema changes.
- [ ] DR and historical data retrieval tested against SLOs and product capabilities.
- [ ] Safe lab cleanup procedures keep production data isolated.

## 49. Self-Check Questions

1. How do Azure Monitor and a Log Analytics Workspace differ in role?
2. How does a workspace table differ from a plain text file or an Azure Storage container?
3. Can metrics, logs, and distributed traces fully replace one another?
4. Why choose retention per category instead of setting one global number?
5. How does interactive retention differ from total retention?
6. If interactive = 30 days and total = 180 days, how long is the illustrative long-term period?
7. Do all table plans support the same queries and alerts as Analytics?
8. Are Basic/Auxiliary suitable for real-time security detections without verification?
9. Why can lowering production retention be irreversible?
10. Does Log Analytics total retention automatically provide WORM/legal hold?
11. When should logs be exported to Azure Storage immutable storage?
12. What are the pros and cons of sharing one workspace across multiple subscriptions?
13. When should workspaces be split by region or trust boundary?
14. Does `AzureActivity` capture every Key Vault secret read?
15. How do diagnostic settings differ from Azure Monitor Agent/DCR?
16. What role does a DCR association play?
17. Can ingestion-time transformations execute any arbitrary KQL query?
18. If you create a workspace without DCRs or diagnostic settings, will logs appear?
19. How does workspace-based Application Insights differ from logging to stdout?
20. Why standardize `correlationId` and UTC timestamps?
21. How does sampling application diagnostics differ from sampling audit events?
22. Why never log `Authorization` headers or SAS URLs?
23. Does resource-context querying inherently isolate `tenantId` at row level?
24. How does Azure management RBAC differ from log query permissions?
25. What permissions should a managed identity that only ingests logs hold?
26. What roles do AMPLS and DCE play in private logging scenarios?
27. Why might the `AzureDiagnostics` table not exist even with diagnostic settings enabled?
28. Why filter `TimeGenerated` early in KQL queries?
29. Which operator computes p95 latency on `AppRequests`?
30. Does `_BilledSize` from one table equal the bill for the whole workspace?
31. What is the significance of `TimeGenerated` vs. `ingestion_time()`?
32. If a logger emits a log yet the workspace shows nothing, which stages should you inspect?
33. How do you detect a dead collector before an incident hits?
34. Why shouldn't monitoring of a logging pipeline depend solely on that same pipeline?
35. If ingestion jumps 7x after a release, what is your first investigation step?
36. How do retention costs differ from ingestion, query, and export costs?
37. Who must approve lowering retention on security logs?
38. Does a successful IaC apply prove the log stream is healthy?
39. Should you test purge or retention reductions in production to learn?
40. What makes a complete log policy from collection through disposal?

## 50. Summary

**Log Analytics Workspace** is where log data is organized and queried in **Azure Monitor Logs**. To build solid observability, operators must understand **data sources, log paths, table schemas, KQL, access controls, alerting, and data completeness**. DCR/AMA, Diagnostic settings, workspace-based Application Insights, and the Logs Ingestion API are distinct ingestion paths with their own purposes and constraints.

**Log retention design** starts from data classification and use cases: application errors need fast querying, verbose telemetry can be kept short, and security/audit events may need longer and stricter retention. You must distinguish **workspace defaults from table overrides**, **interactive/analytics retention from total/long-term retention**, and check the limits of **Analytics, Basic, and Auxiliary plans** before applying them. Long-term retention does not automatically equal immutable evidence; when regulations demand WORM/chain-of-custody, add appropriate evidence storage.

A production architecture requires **least-privilege Entra RBAC, private networking where needed, data minimization, controlled KQL/alerts, ingestion health monitoring, IaC retention with readback, cost forecasting, and recovery runbooks**. The end goal is not hoarding logs—it is having **enough signal to detect and investigate, retrieving it when needed, protecting sensitive data, and staying within budget and retention obligations**.




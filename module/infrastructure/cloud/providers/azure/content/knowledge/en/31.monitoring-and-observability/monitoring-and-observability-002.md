# Diagnostic Settings and Monitoring Export Destinations

Suppose a Spring Boot order service runs on Azure App Service, using Azure SQL Database and Azure Key Vault. When HTTP 500 errors appear, the SRE team wants to know **which service emitted the errors, whether any Azure resource configuration changed, whether Key Vault denied access, and how long the data must be retained for investigation**. The Azure Portal displays some built-in charts, but those charts do not create a centralized log store, guarantee regulatory audit retention, or automatically stream data to a SIEM.

**Azure Monitor diagnostic settings** solve a core part of this problem: **selecting supported log categories and metrics from an Azure resource and routing them to one or more destinations** such as a Log Analytics workspace, Azure Storage, Azure Event Hubs, or a supported partner integration. This is a **platform telemetry export mechanism**, not a self-healing tool, an alerting engine, an agent collecting arbitrary log files, or a source of data that the underlying service does not emit.

The lesson **"Diagnostic Settings and Monitoring Export Destinations"** belongs to the **Monitoring and Observability** chapter of the **CLOUD_PROVIDERS_AZURE** module. It connects knowledge of subscriptions, resource groups, Microsoft Entra ID, networking, compute, storage, and data with how to **collect, analyze, protect, operate, and control the cost of observability data** in an Azure application architecture.

After studying this lesson, you will be able to:

- Distinguish **resource logs, platform metrics, subscription Activity Log, application telemetry, and guest OS logs**.
- Explain the anatomy of a diagnostic setting: **resource scope, categories/category groups, metrics, destination IDs, and Log Analytics table modes**.
- Choose **Log Analytics, Storage Account, Event Hubs, or partner integrations** based on investigation, retention, streaming, and governance goals.
- Understand the relationship between **diagnostic settings, Data Collection Rules (DCR), Azure Monitor Agent (AMA), Application Insights, and Azure Monitor alerts**.
- Configure settings via **Azure Portal, Azure CLI**, and declarative **Bicep/IaC** without granting unnecessary permissions.
- Verify data delivery using **KQL, metrics, Storage, and Event Hubs consumers**.
- Design **RBAC, data residency, Private Endpoints/firewalls, encryption, retention, cost, and reliability**.
- Troubleshoot common issues such as **wrong log category, wrong resource ID, missing destination permissions, missing KQL tables, and events not reaching Event Hubs**.

> **Scope:** Examples are instructional templates and do not create or modify Azure resources as written. Category names, category groups, supported metric types, destination tables, CLI options, and destination constraints **vary by resource provider and service version**; always query the resource's actual capabilities before applying.

## 1. Why Are Diagnostic Settings Needed?

An Azure resource can emit **platform metrics** (e.g., request counts, CPU/IO, connection counts) and **resource logs** (e.g., data-plane activity, audits, access failures). These signals are distinct from application logs written by Spring Boot itself.

### 1.1. Not All Telemetry Is Exported Automatically

| Question | Origin | If Unconfigured |
|---|---|---|
| Did Key Vault deny a secret access request? | Key Vault resource logs/audit categories | Data may not exist in the Log Analytics workspace |
| Did App Service have platform/web-server HTTP 5xx errors? | App Service resource logs/metrics | Metrics may be visible on the resource; logs are not centralized |
| Who modified an NSG or deleted a resource group? | Subscription Activity Log | History exists in Azure; long-term export/storage requires proper configuration |
| Which class threw `NullPointerException` in Spring Boot? | Application logs/traces | App Service diagnostic settings do not automatically instrument application source code |
| What events are in `/var/log/syslog` on a Linux VM? | Guest OS syslog | Requires Azure Monitor Agent + DCR or an appropriate collector |
| Does the backend API have p95 traces and dependency spans? | Application Insights/OpenTelemetry | Requires dedicated SDK/agent/instrumentation |
| Does Azure SQL have CPU spikes or deadlocks? | Azure SQL platform metrics/resource logs and DB diagnostics | Select supported categories and collection mechanisms |

Diagnostic settings **route telemetry from existing sources**, rather than generating all kinds of data on their own. Choosing the right collection mechanism matters more than "checking every checkbox."

### 1.2. Business and Operational Goals

- **Incident investigation:** query logs by resource, time, operation, and correlation ID.
- **Audit/compliance:** retain required events per policy, with access controls and retention governance.
- **Anomaly detection:** stream telemetry to analytics pipelines or a SIEM.
- **Cross-service analysis:** consolidate logs across App Service, Key Vault, Storage, SQL, and networking.
- **Cost control:** collect only necessary categories/metrics, set retention, and route intentionally.
- **Evidence preservation:** store archives with lifecycle and immutability policies when required.

**A successfully created diagnostic setting does not prove the system is well observed.** You must verify that the source actually emits events, the destination receives them, timestamps/tables match expectations, and someone actively uses the data for monitoring.

## 2. Azure Monitor Diagnostic Settings Architecture

~~~mermaid
flowchart LR
    subgraph SRC[Azure data sources]
      APP[App Service]
      KV[Key Vault]
      DB[Azure SQL Database]
      NSG[Network resources]
    end
    APP --> DS[Diagnostic settings on source resource]
    KV --> DS
    DB --> DS
    NSG --> DS
    DS -->|Queryable logs| LA[(Log Analytics workspace)]
    DS -->|Retention / archive| STORAGE[(Azure Storage Account)]
    DS -->|Stream near-real-time| EH[Azure Event Hubs]
    DS -->|Supported integration| PARTNER[Partner solution]
    LA --> KQL[KQL / Workbooks / Alerts]
    STORAGE --> ARCHIVE[Lifecycle / audit archive]
    EH --> CONSUMERS[SIEM / Functions / stream consumers]
    DCR[Azure Monitor Agent + Data Collection Rule] --> LA
    APM[Application Insights / OpenTelemetry] --> LA
~~~

**Logical diagram:** each resource normally has its **own diagnostic setting attached to that resource**; the diagram groups those settings into a single node for readability. DCR/AMA and Application Insights belong to **separate pipelines**; they do not automatically become categories inside a diagnostic setting.

### 2.1. What Makes Up a Diagnostic Setting?

| Field / Concept | Role |
|---|---|
| **Resource scope** | Azure resource emitting logs/metrics; a diagnostic setting is an extension resource |
| **Name** | Setting name, e.g., `diag-to-operations-law` |
| **Log categories** | Individual log types supported by the provider |
| **Category groups** | Groups such as `allLogs`/`audit` when supported by the provider |
| **Metric categories** | E.g., `AllMetrics` if the resource allows export via diagnostic settings |
| **workspaceId** | Resource ID of the destination Log Analytics workspace |
| **storageAccountId** | Resource ID of the destination Azure Storage Account |
| **eventHubAuthorizationRuleId** | Resource ID of the authorization rule used to send to Event Hubs |
| **eventHubName** | Target hub name when using Event Hubs |
| **marketplacePartnerId** | Appropriate partner integration if available |
| **logAnalyticsDestinationType** | Selects resource-specific table mode when supported |

**Do not confuse the source resource ID with the destination resource ID.** One setting can point to multiple supported destinations, but you must verify each destination receives the right log/metric types and valid configuration. On many Azure resources, the service allows up to **5 diagnostic settings per resource**; verify applicable limits and avoid creating dozens of duplicate settings.

### 2.2. A Diagnostic Setting Is a Data Path, Not a Replica of Metrics Explorer

Metrics shown in Metrics Explorer **are not necessarily** exported verbatim via diagnostic settings. Some metrics do not support export, metrics have different dimensions, and their representation once written to a workspace does not retain all drill-down capabilities of the native metrics API. Before enabling metric export:

1. Verify which metrics/categories are actually supported.
2. Assess whether dimensions (region, status code, operation) are needed.
3. Compare using a **direct metric alert** against exporting metrics as logs.
4. Define retention and query goals, since converting metrics into logs can incur ingestion costs.

### 2.3. Emission Flow, Latency, and Duplicate Records

~~~mermaid
sequenceDiagram
    participant SOURCE as Azure resource
    participant MON as Azure Monitor pipeline
    participant LA as Log Analytics
    participant EH as Event Hubs
    participant SIEM as Consumer
    SOURCE->>MON: Generate resource event
    MON->>MON: Apply enabled categories/settings
    par Deliver to destinations
      MON->>LA: Ingest supported record
    and
      MON->>EH: Publish diagnostic event
    end
    EH-->>SIEM: Consumer receives batch
    SIEM-->>SIEM: Validate / parse / deduplicate
~~~

Delivery **does not guarantee zero latency or exactly-once semantics across all destinations**. Data may arrive late, carry different processing timestamps, or require an Event Hubs consumer to reprocess after retries. Never use diagnostic settings as a transactional outbox for mandatory business events that must never be lost.

## 3. Distinguishing Data Types in Azure Monitor

### 3.1. Resource Logs

Events emitted by the resource provider itself, for example:

- Azure Key Vault: operations/audit events per supported categories.
- Azure Storage: Blob/File/Queue/Table activity per child resource and categories.
- Azure SQL Database: audit/errors/timeout/diagnostic categories per database.
- Azure App Service: HTTP/application/web-server logs where supported by the resource type.
- Azure Firewall and certain networking services: network/application threat and decision logs.

Category names **are not uniform** across all resource types. Do not hardcode `AuditEvent` in automation for every resource and assume all of them will emit audit logs.

### 3.2. Platform Metrics

Metrics are typically aggregated time series such as:

~~~text
Time:       2026-11-20T09:00:00Z
Metric:     Requests
Aggregation: Total
Value:      1250
Dimensions: resource / region / status (if supported)
~~~

Metrics Explorer and Metric Alerts read platform metrics directly via the metrics API. If you need to store or query them as logs in a workspace or stream them to another pipeline, enable export **only when the diagnostic setting supports the metric category**. Do not enable metric export if the same question can be answered by direct metric alerts without duplicating data.

### 3.3. Azure Activity Log

Activity Log records **control-plane** events, such as creating/deleting a resource, changing role assignments, or updating configuration. It is **subscription-level**; export Activity Log via a diagnostic setting at **subscription scope**, rather than assuming enabling logs on each SQL Database will capture who changed an NSG in the subscription.

An Activity Log event differs from a resource audit event:

~~~text
Activity Log:
  User changes Key Vault network rules via ARM.

Key Vault resource audit log:
  Application attempts to read a secret.
~~~

Investigations need both to correlate configuration changes with data access failures.

### 3.4. Microsoft Entra ID Logs

Sign-in logs, audit logs, and Entra identity events have **separate diagnostic settings/export configurations at the Entra tenant scope** with appropriate permissions and licensing. Creating a diagnostic setting on a VM, database, or App Service will never export Entra sign-in logs.

### 3.5. Application Insights and OpenTelemetry

To see Java exception traces, HTTP dependencies, or custom business events, the application needs the **Application Insights Java agent, Azure Monitor OpenTelemetry, or compatible instrumentation**. Azure App Service diagnostic settings can export platform logs, but do not replace instrumenting Spring Boot. Both data sources can be sent to the same or separate workspaces depending on architecture.

### 3.6. Guest OS Logs, VM Insights, and DCRs

Collecting `Windows Event Logs`, Linux `syslog`, performance counters, or custom text logs from a VM normally involves **Azure Monitor Agent + Data Collection Rule (DCR)**, not checking an arbitrary category in the VM's diagnostic settings. A single resource can use diagnostic settings for platform signals alongside AMA/DCR for guest OS signals.

### 3.7. Which Tool Fits Which Goal?

| Goal | Preferred Mechanism |
|---|---|
| Azure SQL/Key Vault resource audit logs | Appropriate diagnostic setting category |
| Subscription resource change events | Activity Log export at subscription scope |
| Linux syslog / Windows Event Logs | AMA + DCR |
| Spring Boot application traces/dependencies | Application Insights / OpenTelemetry |
| Immediate alert when CPU breaches threshold | Azure Monitor metric alert |
| Centralized KQL querying for errors/audits | Log Analytics workspace |
| Long-term archive with lifecycle/immutability | Diagnostic setting → Storage (when supported) |
| Streaming to SIEM / custom processor | Diagnostic setting → Event Hubs |

**Multiple tools can be used together**; the goal is a clear data contract and ownership, not turning everything on everywhere.

## 4. Choosing Export Destinations: Decision Matrix

| Destination | Primary Purpose | Strengths | Limitations to Remember |
|---|---|---|---|
| **Log Analytics workspace** | KQL investigation, dashboards, log alerts | Querying, joins, RBAC/retention, Azure Monitor integration | Ingestion/query/retention costs, differing table schemas |
| **Azure Storage Account** | Archival, long-term retention, compliance | Lifecycle, blob access tiers, immutability when configured | Not a KQL workspace; requires separate parser/analytics to read |
| **Azure Event Hubs** | Streaming to SIEM/processing | Consumer groups, buffering, event processing | Quota/throughput, consumer lag, retries, finite retention |
| **Partner solution** | Third-party monitoring integration | Consolidates existing workflows | Availability, features, permissions, and pricing depend on partner |

### 4.1. Three Questions to Choose a Destination

**Do you need immediate KQL querying?** Choose Log Analytics. **Do you need long-term raw log retention?** Consider Storage with lifecycle and immutability. **Do you need a near-real-time SIEM pipeline?** Consider Event Hubs, along with lag and consumer health monitoring.

Example policy:

~~~text
Critical audit:
  Log Analytics for recent incident investigation.
  Storage Account with lifecycle and protected retention for archive.

Operational network events:
  Log Analytics for KQL and alerts.
  Event Hubs for central SIEM/stream processing.

Noisy debug categories:
  Export only if value, sampling, owner and budget justify them.
~~~

Not every service or category supports this exact combination; check support first. **Exporting to two destinations is not free**, and it does not provide an independent backup if both destinations can be deleted by an over-privileged account.

### 4.2. When to Choose Log Analytics?

- SREs frequently query the last 7–90 days of logs.
- KQL joins across `_ResourceId`, category, operation, and correlation/timestamps are needed.
- Workbooks and log alerts are required.
- Appropriate RBAC/query access and data classification are in place.

Do not use Log Analytics as a primary transactional database. Query results and ingestion incur latency; real-time control loops and SLO enforcement should not rely solely on it.

### 4.3. When to Choose Storage?

- Audits/archives require retention longer than the hot query window.
- Lowering historical storage costs by reading old data selectively is desired.
- Immutable/WORM policies, lifecycle rules, storage ownership, and eDiscovery apply.
- The organization has a pipeline to read Blobs and parse diagnostic records when needed.

**Raw Storage exports do not come with a KQL index.** If an investigation is needed 2 years later, you must have tooling to locate the right blob/time partition and handle older schemas.

### 4.4. When to Choose Event Hubs?

- A SIEM ingests events on a short-latency feed.
- Events need enrichment, routing, or filtering via Functions, stream processors, or custom consumers.
- An owner manages partitions, throughput, retention, consumer groups, and replay.

A slow consumer can cause Event Hubs data to age past retention; do not treat "exported to Event Hubs" as permanent archival.

### 4.5. When to Choose a Partner Destination?

The organization already standardizes on a third-party observability/SIEM platform and Azure Monitor supports the specific integration. Check **provider/region/cost/permission/network support**, third-party data terms, retention on the partner side, and recovery procedures if the integration stops.

## 5. Categories and Category Groups: Selecting What Data Is Exported

Each Azure resource provider defines the **log categories** and **metric categories** supported by its resources. An Azure Key Vault has a different list than Azure SQL Database; a Storage sub-resource has a different list than the parent Storage Account.

### 5.1. A Category Is Not an Application Log Level

| Concept | Meaning | Example |
|---|---|---|
| **Log category** | A specific resource log type emitted by the provider | `AuditEvent` on Key Vault, when available |
| **Category group** | A group of categories exposed by the provider | `allLogs` or `audit` if supported by the resource |
| **Metric category** | Group of exportable metrics | `AllMetrics` when available |
| **App log severity** | Log level written by application code | `ERROR`/`WARN` in Spring Boot, not a resource diagnostic category by default |

The word `allLogs` does not mean "every kind of data in Azure." It represents **the resource log categories covered by that group on that specific resource/provider**. It does not pull Entra sign-ins, VM guest syslog, application traces, or unsupported metrics.

### 5.2. Discover Instead of Guessing Names

Proper workflow before applying:

1. Identify the **exact source resource ID**, including child resources if needed.
2. Query Azure Monitor for the **supported categories/category groups** on that resource.
3. Map categories against security, incident, and business requirements.
4. Choose the `audit` group when only audit data is needed and supported; choose `allLogs` when broader scope and budget justify it.
5. Configure `AllMetrics` **only if listed and backed by a specific use case**.
6. Read back the setting after applying and verify at least one record/metric at the destination.

Note: category groups can expand when a provider introduces new categories; that helps future coverage in `allLogs` but also introduces **unexpected cost/PII exposure risk**. If strict governance is required, track the category catalog and enable only needed categories.

### 5.3. Choosing `audit` vs. `allLogs`

Key Vault example:

~~~text
Goal A: audit access to secrets/keys/certificates
  → Discover audit category/group.
  → Enable supported audit logs to central workspace.

Goal B: broader operational diagnostics
  → Discover all supported resource log categories.
  → Assess volume, sensitivity, cost, retention.
  → Enable allLogs only if necessary and supported.
~~~

**Do not assume both groups exist on every resource.** If a resource only lists individual categories, specify those categories instead of passing an invalid group.

### 5.4. How Does Selecting Metrics Differ from Logs?

`AllMetrics` can export supported metric types on a resource, but not every metric in Azure Monitor exports through diagnostic settings with full dimensions and aggregations. If the goal is alerting on high CPU:

~~~text
Preferred simple path:
  Azure Monitor metric alert directly on supported metric.

If analytics/history/export is required:
  Confirm diagnostic metric export support,
  enable category and validate destination schema.
~~~

Do not use **metric-to-log export** as the sole mechanism for low-latency alerts when a direct metric alert works better.

## 6. Log Analytics: Workspaces, Tables, and KQL

A **Log Analytics workspace** is the destination for ingesting logs into Azure Monitor Logs and querying them with KQL. Creating a workspace does not automatically populate tables from resources emitting logs.

### 6.1. A Workspace Is an Operational and Data Boundary

Before using a workspace as a destination, decide:

- **Environment:** shared or separate for prod and non-prod?
- **Tenant/subscription:** who can ingest/query? Under what conditions are cross-subscription setups permitted?
- **Region/data residency:** where is data stored, and what compliance/cross-region rules apply?
- **Retention and archival:** how long is interactive data kept, and what long-term retention is needed?
- **RBAC/table access:** which tables can SRE, security, developers, and audit teams view?
- **Budget:** ingestion, retention, query, and alert costs.
- **Query workload:** real-time dashboards, forensic investigations, or infrequent queries.

Split workspaces by **environment/boundary** when compliance or access rules demand it, but over-fragmenting complicates correlation, spreads monitoring across too many places, and adds overhead. No single workspace layout fits every organization.

### 6.2. Legacy AzureDiagnostics vs. Resource-Specific Tables

Some diagnostic settings offer a **destination table mode** for Log Analytics:

| Mode | Result | When to Watch Out |
|---|---|---|
| **Azure diagnostics** | Records from many providers go into the shared `AzureDiagnostics` table | Wide/sparse schema; queries typically filter by Category/ResourceProvider |
| **Resource specific** | Records go into **dedicated tables** if supported by the resource/provider | Cleaner table schemas; must know actual table names |

In ARM/Bicep, selecting resource-specific mode may use:

~~~json
{
  "logAnalyticsDestinationType": "Dedicated"
}
~~~

**Not every resource, provider, or log type supports Dedicated mode.** Selecting resource-specific does not guarantee every log category automatically gets a new self-named table. Check the Azure Monitor resource log table mappings and verify **which tables actually received data**. For Activity Log, metrics, or Entra logs, table names differ; do not try querying `AzureDiagnostics` for everything.

### 6.3. Example KQL on `AzureDiagnostics`

Run only when the workspace **has already received logs into this table**:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| summarize Events=count()
    by ResourceProvider, Category
| order by Events desc
~~~

To view events for a specific resource:

~~~kusto
let SourceResourceId =
  "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault>";
AzureDiagnostics
| where TimeGenerated between (ago(2h) .. now())
| where _ResourceId =~ SourceResourceId
| project TimeGenerated, _ResourceId, ResourceProvider, Category,
          OperationName, ResultType
| top 100 by TimeGenerated desc
~~~

Column names depend on the schema and provider. `OperationName` and `ResultType` exist in some records but not all tables; inspect the schema first. `<sub-id>` is a placeholder, not a real URL or ID. `=~` performs **case-insensitive** string matching, which helps when resource IDs vary in casing; still, prefer canonical IDs.

### 6.4. Resource-Specific Table Example

For a resource/provider with a dedicated table, a name like `KeyVaultAuditEvents` is strictly an **example for a confirmed scenario**:

~~~kusto
KeyVaultAuditEvents
| where TimeGenerated > ago(1h)
| summarize Events=count() by OperationName, ResultType
| order by Events desc
~~~

**This query is valid only if the workspace actually has that exact table and columns.** If data lands in `AzureDiagnostics` or a different dedicated table, adapt the query to the real schema. KQL cannot query a table that has not been created just because a diagnostic setting exists.

### 6.5. Example Platform Metrics Exported to a Workspace

In some metric export setups, you can query the `AzureMetrics` table:

~~~kusto
AzureMetrics
| where TimeGenerated > ago(1d)
| summarize Samples=count() by MetricName
| order by Samples desc
~~~

This example applies **only when Metric diagnostic export and the `AzureMetrics` table are actually active**. It does not replace metric alerts, and exported dimensions/aggregations may differ from native metric APIs. Do not claim that enabling `AllMetrics` puts every metric into `AzureMetrics`.

### 6.6. Activity Log in a Workspace

When properly exported, the subscription Activity Log can appear in the `AzureActivity` table:

~~~kusto
AzureActivity
| where TimeGenerated > ago(7d)
| summarize Changes=count() by OperationNameValue, ActivityStatusValue
| top 20 by Changes desc
~~~

**This is the Activity Log**, not Key Vault resource logs, and requires a **subscription-level diagnostic setting**. Verify table and column names in the workspace before relying on them in automation.

### 6.7. A Missing Table Does Not Immediately Mean a Broken Diagnostic Setting

Possible reasons include:

1. No events of that category have occurred yet.
2. Data is still awaiting ingestion; the query ran too early.
3. Looking at the wrong workspace or lacking KQL read permissions on the table.
4. Log Analytics destination/table mode differs from expectations.
5. The resource category/diagnostic setting is ineffective or attached to the wrong scope.
6. The query uses the wrong time range or resource ID.

Generate a **valid, low-risk test event** on a lab resource and measure the time from event emission to ingestion. Never trigger security incidents or delete production resources just to force a log to appear.

## 7. Storage Account: Retention, Lifecycle, and Audit Archive

A diagnostic setting can send **supported logs/metrics** to Azure Storage for longer retention, auditing, lookups, or reprocessing. Azure Monitor typically writes blobs organized by service/category/time; **do not assume one CSV file per event**.

### 7.1. Key Decisions

| Decision | Question |
|---|---|
| Storage account | Use a dedicated account for audits or share with application data? |
| Region | Must the destination be in the same region as the source resource per service rules? |
| Network access | Can Azure Monitor write when storage firewalls/private networking are enabled? |
| Redundancy | LRS/ZRS/GRS aligned with RPO and data residency? |
| Lifecycle | After how long to transition Hot → Cool/Cold/Archive/Delete? |
| Immutability | Do audits require WORM/retention locks/legal holds? |
| Encryption | Microsoft-managed or customer-managed keys per policy? |
| Access control | Who can list, download, or delete blobs? |
| Monitoring | Will you know if exports stop or storage hits quota? |

### 7.2. File Format and Partitioning

Data export may create containers and log paths structured by category and time. One logical model:

~~~text
<storage-account>/
  diagnostic-data/
    <resource-type>/
      <resource-id>/
        <log-category>/
          yyyy/MM/dd/HH/
            <hourly or batched records>
~~~

**This is not an exact default Azure Monitor path.** Actual paths depend on the service and destination; usually the service creates category-named containers and time partitions. Inspect real blobs with Storage Explorer or an SDK and build parsers around the actual emitted envelope/schema; never hardcode an illustrative path and run cleanup jobs against it.

### 7.3. Lifecycle and Retention

An illustrative tiering plan:

~~~text
First 30 days:  hot/cool as required for occasional reads
Days 31–365:   lower-access tier if compatible with read needs
After 365d:    remove only when policy/legal holds permit
~~~

These durations are **learning assumptions**, not universal legal mandates. Before enabling lifecycle auto-deletion, review retention rules, legal holds, recovery procedures, and retrieval/tier-transition charges. For Archive tier, reads may require rehydration with significant latency; if SREs need answers in seconds, Storage Archive cannot replace hot Log Analytics tables.

### 7.4. Immutability and Delete Permissions

If audits require tamper protection, use **immutable blob storage (WORM)**, policy/retention locks, and proper RBAC. However:

- Enabling the wrong policy can prevent purging data before expiration.
- Over-privileged users on the subscription/storage account can affect other settings, requiring separation of duties.
- Encryption is not the same as immutability.
- Copies in other destinations still need governance.
- Never test permanent retention locks on production storage during a lab.

### 7.5. Storage Networking and Trusted Services

When a Storage firewall or Private Endpoint is enabled, diagnostic export may require a path for the **Azure Monitor platform service** via product-supported trusted-service exceptions/permissions. An application Private Endpoint **does not automatically guarantee** the diagnostic pipeline can write to storage. Verify specific **network rules, trusted Microsoft services settings, resource instance rules, and regional requirements**, rather than opening public access to the entire Internet.

### 7.6. Testing Whether an Archive Is Actually Usable

An audit archive only has value if it can be **located and read back**:

1. Emit a valid event on a lab resource.
2. Wait for export and inspect the container/time partition.
3. Read the JSON/envelope and check event time, resource ID, and category.
4. Test **read-only archive reader** permissions.
5. Test querying/parsing across multiple files spanning an hour range.
6. Test lifecycle/restore on approved test storage.

Do not declare archival successful merely because the storage account exists.

## 8. Event Hubs: Streaming Logs to a SIEM or Pipeline

Event Hubs handles **event ingestion and fan-out to consumers** with configurable throughput, retention, and replay. The diagnostic setting publishes selected records; consumers read via consumer groups and partition offsets.

### 8.1. Event Hubs Flow

~~~mermaid
flowchart LR
    DB[Azure SQL / Key Vault / Firewall resource] --> DS[Diagnostic setting]
    DS --> EH[Event Hubs namespace and hub]
    EH --> S1[SIEM consumer group]
    EH --> S2[Analytics consumer group]
    S1 --> ALERTS[Detection rules / incidents]
    S2 --> STORE[Data lake / ADX / other sink]
    OPS[Operations] -. Monitor lag / throttling .-> EH
~~~

**Consumers are not diagnostic setting destinations.** The diagnostic setting only sends to Event Hubs; getting alerts in a SIEM or landing data in Data Lake/ADX requires separately configured consumers or connectors.

### 8.2. What Needs to Be Prepared?

- **Event Hubs namespace + event hub** sized for throughput and partition requirements.
- **Authorization rule** with appropriate permissions for Azure Monitor diagnostic settings to publish; permission requirements depend on mechanism/configuration. Avoid casually using `RootManageSharedAccessKey`.
- Namespace/hub in a **valid region** relative to the source resource.
- Firewall/Private Endpoint/trusted-service configuration for diagnostic delivery if restricted networking is enabled.
- Dedicated **consumer group per consuming application**, checkpoint store, and replay plan.
- Retention long enough to absorb consumer outages and ingestion lag.
- Alerts for throttling, backlog, and quota, plus Event Hubs and consumer cost tracking.

If the provider or portal requires a policy with `Manage`/`Send`/`Listen` permissions to configure diagnostics, follow the current Azure Monitor permission contract and security review; do not conflate namespace management policies with the credentials a SIEM consumer needs. Separate **publisher access** from **consumer listen access** whenever features and processes allow.

### 8.3. Message Format

Event Hubs may receive diagnostic records wrapped in a JSON envelope containing a `records` array or a structure matching the log type. Illustrative example:

~~~json
{
  "records": [
    {
      "time": "2026-11-20T09:20:00Z",
      "resourceId": "/subscriptions/example/resourceGroups/rg-observe/providers/Microsoft.KeyVault/vaults/kv-lab",
      "category": "AuditEvent",
      "operationName": "SecretGet",
      "resultType": "Success"
    }
  ]
}
~~~

This is a **composite illustrative event**, not a universal schema contract for all Azure resource logs. Consumers must handle variable batch sizes, schema versions, missing fields, different payload types, retries, duplicates, and late arrivals. Never write a parser assuming one Event Hubs message always equals one Azure resource log row.

### 8.4. What Does a Resilient Consumer Need?

~~~text
Event Hubs
  → read partitions in consumer group
  → parse envelope and validate source/category
  → apply schema/version mapping
  → redact sensitive fields if policy permits processing
  → write to durable downstream store/SIEM
  → checkpoint only after processing outcome is recorded
  → retry transient faults; quarantine poison messages
~~~

**At-least-once processing** can produce duplicates around checkpoints and retries. Use stable IDs/timestamps and an appropriate deduplication strategy rather than calling raw `count()` and treating every record as unique. Event Hubs retention is finite; if a consumer outage exceeds retention, data loss can occur unless a parallel archive exists.

### 8.5. Event Hubs Does Not Automatically Receive Every Provider's Resource Logs

Only enabled categories emitted by the provider are sent. Do not debug missing messages by scaling up consumer throughput before verifying:

- Is the **resource scope** right?
- Is the event category actually emitting?
- Does the diagnostic setting point to the **right Event Hub authorization rule and name**?
- Is there a network, firewall, or permission issue?
- Are Event Hubs incoming messages increasing?
- Is the consumer group/offset checkpoint reading from the start or end?

### 8.6. When Should You Avoid Event Hubs?

If you only need to inspect a few audit events per day in KQL, Event Hubs adds unnecessary infrastructure and consumer operations. If the goal is a 7-year immutable archive, Event Hubs retention does not replace Storage with compliance policies. Choose Event Hubs when you have a **specific stream consumer, owner, replay SLO, and budget**.

## 9. Partner Destinations: Controlled Integration

Azure Monitor offers partner integrations within supported service boundaries. A partner destination can forward events directly into an external analytics/SIEM system already used by the organization.

### 9.1. Checklist Before Adopting

1. Does the partner solution support the current **resource provider/category** and region?
2. Does data leave the Azure tenant/region, and under what permissions and contract?
3. Are there external ingest/retention/egress/seat licensing fees outside Azure?
4. Is there a way to verify received event counts, latency, errors, duplicates, and schema mapping?
5. What scope of Azure RBAC/partner principal permissions does the integration require?
6. If the partner has a 24-hour outage, can logs be replayed or archived to Storage in parallel?
7. Is there an audit and approval process to stop routing or revoke partner access?

Do not create a partner integration simply because the marketplace shows an option. A partner must not automatically be granted access to every subscription or Log Analytics workspace if the use case only covers one group of resources.

### 9.2. Evaluating Vendor Lock-In

Document:

- The list of exported categories and providers.
- Key schema fields, such as resource ID, operation, time, and status.
- The partner's normalization and retention rules.
- An exit plan for "migrating from this partner to another SIEM" via Event Hubs or Storage archives.

If legal requirements demand independently accessible evidence after a SIEM contract ends, maintain an organization-controlled archive.

## 10. Scope, Subscriptions, Regions, and Source–Destination Boundaries

### 10.1. Resource-Level Diagnostic Settings

Example Key Vault resource ID:

~~~text
/subscriptions/<sub-id>
 /resourceGroups/rg-application-prod
 /providers/Microsoft.KeyVault/vaults/kv-orders-prod
~~~

A diagnostic setting for Key Vault attaches to **this exact resource**, not "all Vaults in the resource group." If an application has a Key Vault, App Service, and Azure SQL, it normally needs **one diagnostic setting per resource** (or a policy deploying per resource) to collect the respective logs.

### 10.2. Subscription Activity Log Differs from Resource-Level Scope

~~~text
Subscription:
  /subscriptions/<sub-id>
  └── Activity Log diagnostic setting
      → AzureActivity in Log Analytics

Resource:
  /subscriptions/<sub-id>/resourceGroups/<rg>/providers/<type>/<name>
  └── Resource diagnostic setting
      → AzureDiagnostics / resource-specific tables
~~~

Do not configure Azure Activity Log by copying Key Vault's `AuditEvent`; Activity Log categories have different names and scopes. For management groups or tenants, check the separately supported diagnostic export types.

### 10.3. Azure Storage Child Resources

For many Azure Storage logging scenarios, the source may be a **subservice resource scope** such as Blob service rather than the parent Storage Account:

~~~text
Microsoft.Storage/storageAccounts/<account>/blobServices/default
Microsoft.Storage/storageAccounts/<account>/fileServices/default
Microsoft.Storage/storageAccounts/<account>/queueServices/default
Microsoft.Storage/storageAccounts/<account>/tableServices/default
~~~

Do not create a diagnostic setting on the parent Storage Account and assume it captures all Blob read/write logs. Discover supported categories on the **exact resource scope** you want to collect and verify records with a safe test operation.

### 10.4. Region Compatibility

For many **regional resources**, destination **Storage Accounts and Event Hubs** often must satisfy a **same-region** constraint with the source resource for diagnostic settings to work. For **global resources**, different rules may apply. A Log Analytics workspace can reside in another region when supported by the service, though that introduces **data residency and data transfer considerations**.

Before creating the configuration:

1. Check the `location` of the source and destinations.
2. Determine whether the source is **regional or global**.
3. Verify export support for the chosen destination.
4. Evaluate residency, compliance, and egress costs.
5. Test a single setting on a lab resource before rolling out policy fleet-wide.

**Do not assume "a cross-region workspace works technically" means data is legally permitted to cross borders.** Legal and contractual constraints can be stricter than Azure's technical capabilities.

### 10.5. Cross-Subscription and Cross-Tenant

A destination in another subscription may work depending on the service and permissions, provided:

- The deployer has write permissions on the source and appropriate permissions on the destination.
- Cross-tenant setups may have special restrictions or delegation requirements; never assume all cross-tenant scenarios are supported.
- Workspace/Storage/Event Hubs ownership and billing may sit with a different team.
- Access auditing, change approval, data residency, resource locks, and naming standards are aligned.

In organizations with many subscriptions, a common pattern is **application subscriptions sending logs to a central observability workspace/archive** managed by the platform/security team. That still requires individual diagnostic settings at each source, not one magic setting on the central workspace "pulling" every log.

## 11. RBAC Permissions, Data Security, and Destination Networking

Diagnostic exports can contain **resource identifiers, IPs, operation names, error messages, user/object identifiers**, and sometimes sensitive metadata depending on the provider. Treat this data as a governed organizational asset.

### 11.1. Who Is Allowed to Create Diagnostic Settings?

Creating or modifying diagnostic settings typically requires control-plane permissions such as `Microsoft.Insights/diagnosticSettings/write` on the source (via an appropriate role, e.g., Monitoring Contributor at the matching scope) **plus permissions related to the destination** to link the workspace, storage account, or Event Hubs. Having only Reader on the source is usually insufficient.

Never grant Owner across the whole subscription as a knee-jerk "fix" when deployment hits access denied. Inspect the denied action and grant least privilege at the exact scope.

### 11.2. Separated Permission Roles

| Role | Permissions to Consider | Not Equivalent To |
|---|---|---|
| **Resource operator** | View source/categories, create diagnostic settings when delegated | Reading all archived data |
| **Log Analytics analyst** | Query permitted tables | Modifying resource networks/firewalls |
| **Archive reader** | Read audit blobs under least privilege | Deleting/altering retention policies |
| **Security administrator** | Manage audit exports/retention/privileged access | Using app secrets as production principals |
| **Event Hubs consumer** | Read via assigned consumer group | Managing namespace or altering diagnostic settings |
| **IaC service principal** | Deploy settings at the target scope | Owner across all subscriptions |

Permission to read logs should be separated from permission to alter source configuration. For instance, an app team can read App Service logs without having permission to change immutable audit retention.

### 11.3. Data Minimization and PII

Do not enable every log or metric purely for hypothetical diagnostic value. For each category, ask:

- Which fields are included—are there IPs, user IDs, or sensitive metadata?
- Can identifiers be pseudonymized/redacted **at the source** if business policy allows?
- Who is authorized to view/export?
- What is the retention period per data class?
- Is data transferred to third parties or across regions?
- Is there duplication across Log Analytics + Storage + Event Hubs?
- When users request deletion under policy, how are exported copies governed?

**Encryption at rest/in transit does not authorize collecting arbitrary sensitive data.** If logs accidentally capture an access token, fix the producer/provider config and follow incident response; deleting a dashboard chart does not remove already exported records.

### 11.4. Trusted Services, Firewalls, and Private Endpoints

Common failure pattern:

~~~text
Source resource emits logs
     ↓
Diagnostic pipeline attempts destination write
     ↓
Storage / Event Hubs firewall blocks platform service
     ↓
No blob / no Event Hub message
~~~

When a destination enforces network restrictions, check **Azure Monitor diagnostic service trusted-services bypass, network rules, supported identity/permissions, resource instance rules, and regional constraints**. Do not assume an application Private Endpoint grants network access to the diagnostic pipeline backend. Nor should you disable the entire firewall just because events are missing.

### 11.5. Key Management, Encryption, and Compliance

Log Analytics, Storage, and Event Hubs have distinct encryption models, Microsoft-managed vs. customer-managed keys (CMK), permissions, and retention controls. If using customer-managed keys:

- Identify Key Vault/Managed HSM dependencies.
- Plan key rotation and revocation procedures.
- Monitor key access failures that could interrupt ingestion.
- Isolate break-glass principals and audit key policy changes.
- Ensure DR/backup plans do not depend on an unrecoverable key.

Do not cite a diagnostic setting showing `Succeeded` in the console as proof of compliance; compliance requires **retention/immutability, access reviews, and verifiable audit log retrieval**.

## 12. Configuring via the Azure Portal: A Lab Resource

**Preconditions:** a test resource (e.g., a lab Key Vault) and an approved Log Analytics workspace exist, and the operator holds required permissions. Portal labels may vary across versions.

### 12.1. Preparation

- Record the exact **subscription/resource group/resource name/resource ID**.
- Confirm the workspace/Storage/EH destination, region, and data classification.
- Review the categories supported by the resource itself.
- Obtain owner approval for log volume, retention, and budget.
- Pick a clear setting name, such as `diag-kv-lab-to-law`.

### 12.2. Portal Steps

1. Open the Azure Portal → navigate to the target resource.
2. Under **Monitoring**, select **Diagnostic settings**.
3. Review existing settings to avoid creating duplicate destinations/categories.
4. Click **Add diagnostic setting**.
5. Enter a descriptive name (environment, destination, log type).
6. Select supported **Log categories/category groups**; do not check everything out of habit.
7. Select a metrics category only if supported and genuinely needed.
8. Enable **Send to Log Analytics workspace**, **Archive to a storage account**, **Stream to an event hub**, or a supported partner.
9. Pick the **exact destination** (subscription, resource, workspace/hub/storage) and table mode if offered.
10. Review cost, region, access, and configuration, then click **Save** per change approval.
11. **Read back the setting**, generate a valid test event on the lab resource, and verify the destination actually receives it.

### 12.3. Verify Immediately After Saving

A well-configured resource-level setting should answer:

~~~text
SOURCE:
  /subscriptions/.../providers/Microsoft.KeyVault/vaults/kv-lab

DIAGNOSTIC SETTING:
  diag-kv-lab-to-law
  enabled logs: discovered and approved audit category/group
  metrics: only if supported and approved

DESTINATION:
  /subscriptions/.../providers/Microsoft.OperationalInsights/workspaces/law-lab

VALIDATION:
  settings GET matches desired state
  generated event was actually received
  KQL table and timestamp match expected output
~~~

**Never mark PASS merely because the Portal says "saved successfully."** If no events appear, distinguish between "source emitted nothing" and "export failed."

## 13. Azure CLI: Discovering, Reading, and Creating a Setting to Log Analytics

### 13.1. Read-Only Commands — Verify Scope

Bash example with placeholders:

~~~bash
az login
az account set --subscription "<approved-subscription-id>"
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" \
  -o table

RESOURCE_GROUP="<approved-resource-group>"
VAULT_NAME="<approved-key-vault-name>"
WORKSPACE_RG="<approved-workspace-resource-group>"
WORKSPACE_NAME="<approved-law-name>"

SOURCE_ID=$(az keyvault show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VAULT_NAME" \
  --query id -o tsv)

WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group "$WORKSPACE_RG" \
  --workspace-name "$WORKSPACE_NAME" \
  --query id -o tsv)

printf "Source: %s\nWorkspace: %s\n" "$SOURCE_ID" "$WORKSPACE_ID"
~~~

`SOURCE_ID` is the **source resource**, and `WORKSPACE_ID` is the **destination**. In PowerShell, variable assignment syntax differs from Bash; do not paste `$(...)` assignment syntax into an incompatible shell.

### 13.2. Discover Categories

~~~bash
az monitor diagnostic-settings categories list \
  --resource "$SOURCE_ID" \
  --output json

az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" \
  --output json
~~~

Inspect the output to confirm the real `logs`/`metrics` categories and category groups. `categories list` is read-only, making it suitable as an early CI lint step. **Do not hardcode `allLogs` or `AllMetrics` if the current resource output does not support them.**

### 13.3. Create a Log Analytics Diagnostic Setting

**Only on an approved lab resource** and when the `allLogs` category group is actually supported by the provider:

~~~bash
SETTING_NAME="diag-kv-lab-to-law"

az monitor diagnostic-settings create \
  --name "$SETTING_NAME" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"categoryGroup":"allLogs","enabled":true}]'
~~~

This example intentionally **omits metrics** because you must verify whether the source supports metric export and confirm its purpose. If you only want auditing, replace `allLogs` with the `audit` group **if listed**, or specify an individual category:

~~~bash
# Select only if the source lists the "AuditEvent" category.
az monitor diagnostic-settings create \
  --name "diag-kv-lab-audit-to-law" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

**Do not run both examples on the same resource just for practice**: it can export duplicate records for the same category to the same workspace, inflating data and complexity unnecessarily. Pick one configuration matching requirements and respect setting limits.

### 13.4. Configuring a Metric Category When Supported

~~~bash
# Use only when the metrics category list includes "AllMetrics".
az monitor diagnostic-settings create \
  --name "diag-resource-metrics-to-law" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --metrics '[{"category":"AllMetrics","enabled":true}]'
~~~

**Do not assume every resource has `AllMetrics` or that Log Analytics preserves full metric dimensions.** For simple metric alerting, prefer direct metric alerts instead of turning metrics into logs.

### 13.5. Read Back the Setting After Creation

~~~bash
az monitor diagnostic-settings show \
  --name "$SETTING_NAME" \
  --resource "$SOURCE_ID" \
  --output json
~~~

Verify:

- `id` references the right source resource.
- `workspaceId` points to the right destination.
- `logs[].category` or `logs[].categoryGroup` and `enabled` are accurate.
- `metrics[]` is present only if intentionally enabled.
- No unexpected destinations or categories outside the change request exist.

**Caution:** `az monitor diagnostic-settings create` is a **write operation**; an existing setting with the same name can be overwritten. Read existing settings first so you do not overwrite another team's configuration. Having a distinct setting name does not prevent duplicate records across overlapping settings.

### 13.6. CLI in PowerShell Environments

The Bash examples above use single-quoted JSON, which works in most Bash shells. In Windows PowerShell, passing JSON quotes to native commands may require different escaping/serialization depending on the version. You can construct payloads with PowerShell's `ConvertTo-Json -Compress` and inspect how Azure CLI parses the arguments; **do not manually hack quotes and run directly in production**. The goal is passing a valid JSON array matching the current CLI `--help`.

## 14. CLI for Storage, Event Hubs, and Multi-Destination Settings

### 14.1. Storage Export

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "<approved-storage-rg>" \
  --name "<approved-storage-name>" \
  --query id -o tsv)

# WRITE: run only after verifying region/permissions/categories.
az monitor diagnostic-settings create \
  --name "diag-kv-lab-to-archive" \
  --resource "$SOURCE_ID" \
  --storage-account "$STORAGE_ID" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

This example uses `AuditEvent` only for **sources that support that category**, and not every resource supports Storage as a destination. After applying, inspect actual Blob containers and data rather than stopping at the setting. If a storage firewall is active, test delivery against supported trusted-services/network rules.

### 14.2. Event Hubs Export

~~~bash
# Resource ID of an authorized Event Hubs authorization rule.
EVENT_HUB_RULE_ID="<authorized-event-hubs-rule-resource-id>"
EVENT_HUB_NAME="<approved-event-hub-name>"

# WRITE: run only after verifying regional/network/permissions constraints.
az monitor diagnostic-settings create \
  --name "diag-kv-lab-to-eventhubs" \
  --resource "$SOURCE_ID" \
  --event-hub-rule "$EVENT_HUB_RULE_ID" \
  --event-hub "$EVENT_HUB_NAME" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

Do not confuse an **authorization rule resource ID** with an **Event Hubs connection string containing a secret**. Check `az monitor diagnostic-settings create --help` at deployment time, as CLI extensions/API versions may change parameter names. Consumers must be set up separately; without an Event Hub consumer, logs may land in the hub with nothing processing them.

### 14.3. One Setting with Multiple Destinations

Azure diagnostic settings allow a single configuration to target multiple destinations when supported by the service. Illustrative command:

~~~bash
az monitor diagnostic-settings create \
  --name "diag-kv-lab-multi-dest" \
  --resource "$SOURCE_ID" \
  --workspace "$WORKSPACE_ID" \
  --storage-account "$STORAGE_ID" \
  --event-hub-rule "$EVENT_HUB_RULE_ID" \
  --event-hub "$EVENT_HUB_NAME" \
  --logs '[{"category":"AuditEvent","enabled":true}]'
~~~

**This is not a recommendation to enable all three destinations by default.** Account for duplicated traffic, ingestion/storage/Event Hubs costs, and compliance. Some teams prefer **separate settings per destination** to isolate ownership and change control, within the per-resource setting limit. Either way, verify all destination IDs and actual delivery.

### 14.4. When a Resource Has Different Category Groups

Replace `AuditEvent` with an actual category returned by `categories list`. To select only a group:

~~~json
[
  {"categoryGroup": "audit", "enabled": true}
]
~~~

**This fragment is only the `logs` payload**, not a complete diagnostic setting. Do not send both the `AuditEvent` category and the `audit` group if it causes category overlap or validation errors; follow the schema supported by the API.

## 15. Infrastructure as Code: Bicep and Declarative Design

The Portal is great for learning, but an enterprise with many subscriptions cannot rely on humans remembering to open Diagnostic settings and tick checkboxes. **IaC** keeps configurations versioned, peer-reviewed, repeatable, and drift-checked.

### 15.1. Bicep for an Existing Key Vault

An illustrative Bicep template:

~~~bicep
targetScope = 'resourceGroup'

@description('Name of an existing Key Vault in this resource group.')
param keyVaultName string

@description('Full ARM resource ID of the approved Log Analytics workspace.')
param logAnalyticsWorkspaceId string

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource keyVaultDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-to-central-log-analytics'
  scope: keyVault
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
  }
}
~~~

**Conditions for using this template:**

- The current provider/resource supports the `allLogs` group and `Dedicated` mode for the selected categories.
- The workspace ID must be the **full ARM resource ID**, not the Log Analytics Workspace GUID/customer ID or ingestion endpoint URL.
- The deployer has required permissions on both the source resource and destination workspace.
- The Bicep API version remains supported; validate against your current toolchain.
- This attaches a setting to an **existing Key Vault**, without provisioning a new Vault.
- It **does not generate data**, only routes future events if emitted.

If only auditing is required, use the `audit` group when supported or specify individual categories. If the resource does not support `Dedicated`, remove that property or use a supported mode, and align KQL queries with the actual destination table.

### 15.2. Watch Out for `allLogs` in CI/CD

When an Azure resource provider adds a new log type to `allLogs`, your deployment template does not change, yet emitted data volume can jump. IaC workflows need:

- Budget and quota alerts.
- Periodic reviews of the supported category catalog.
- Data classification and retention reviews.
- Schema tests for downstream SIEMs/parsers.
- Configuration rollback mechanisms if volume or PII risk spikes.

Never use `allLogs` as a shortcut to skip cost and PII reviews.

### 15.3. Subscription Activity Log Bicep at a Different Scope

Separate example at **subscription scope**:

~~~bicep
targetScope = 'subscription'

@description('Full ARM resource ID of the central workspace.')
param logAnalyticsWorkspaceId string

resource subscriptionActivityDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'activity-to-central-log-analytics'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        category: 'Administrative'
        enabled: true
      }
      {
        category: 'Security'
        enabled: true
      }
      {
        category: 'Policy'
        enabled: true
      }
    ]
  }
}
~~~

**This is a standalone subscription-scope template** and does not automatically run inside the resource-group template above. Categories must be verified against supported Activity Log configurations. The deployer needs subscription-scope permissions; do not drop this template into a pipeline restricted to resource-group Contributor and then grant unbounded Owner to fix errors.

### 15.4. Azure Policy Scenario

Across many subscriptions and resource groups, Azure Policy can use **DeployIfNotExists** to enforce baseline diagnostic settings on targeted resource types:

~~~text
Policy assignment (approved scope)
  → Identify resources without expected diagnostic setting
  → Deploy diagnostic configuration via managed identity
  → Remediation task for existing non-compliant resources
  → Compliance dashboard
  → Continuous validation of destination data
~~~

Distinguish between:

- **Policy compliance**: whether the setting configuration exists per policy rules.
- **Data delivery health**: whether logs/metrics actually arrive at the destination and can be queried/read.

Policy can report compliant even while a source emits nothing or destination networking blocks delivery. Add end-to-end delivery tests and alerts.

### 15.5. Ownership Strategy Between App Teams and Platform/Security

| Layer | Primary Owner | Responsibilities / Deliverables |
|---|---|---|
| Source resource | Application/resource owner | Knows categories and business meaning |
| Diagnostic policy/IaC | Cloud platform | Naming, category baselines, destination IDs |
| Log Analytics workspace | Observability/SRE | Tables, KQL, alerts, access, cost |
| Archive Storage | Security/compliance | Retention, immutability, recovery |
| Event Hubs pipeline | Data/SIEM platform | Throughput, consumer groups, lag, replay |
| Privileged access | IAM/security | RBAC, identities, periodic access reviews |
| Data classification | Privacy/data owner | PII, residency, retention policy |

A central workspace must not give application teams permission to delete audit blobs or alter organization-wide monitoring policies.

## 16. Verifying the Log Analytics Destination: From Event to KQL

A solid rollout includes **post-deployment verification** instead of stopping at an Azure CLI exit code.

### 16.1. Testing with a Controlled Event

Lab Key Vault example:

1. Verify the source resource ID and setting `diag-kv-lab-to-law`.
2. Perform an authorized, harmless audited operation, such as **reading a test secret** with an authorized client or performing a logged action.
3. Record the **UTC event time, operation, resource ID, and test identity**.
4. Wait for ingestion according to service characteristics; do not expect instant visibility.
5. Query the right Log Analytics workspace and actual table.
6. Match the event/operation and distinguish the real record from unrelated logs.
7. Document the outcome, arrival latency, verifier, and any failures.

**Never attempt unauthorized reads of production secrets, provoke security errors, delete resources, or alter firewalls** to force logs to appear. Always use authorized, low-risk test events.

### 16.2. KQL to Confirm the Resource ID

When logs land in `AzureDiagnostics`:

~~~kusto
let TargetResource =
  "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault>";
AzureDiagnostics
| where TimeGenerated > ago(2h)
| where _ResourceId =~ TargetResource
| summarize Events=count(), LastEventUtc=max(TimeGenerated)
    by Category
| order by Events desc
~~~

**The `AzureDiagnostics` table may not exist at all** if the resource/provider writes to a dedicated table. In that case, query the verified dedicated table instead of creating fake tables to make a query "turn green."

### 16.3. Data Freshness and Ingestion Latency

Some Log Analytics tables expose ingestion-time metadata, though fields and behavior vary. If a table supports `ingestion_time()`, you can measure lag:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(1d)
| extend IngestedAt = ingestion_time()
| where isnotnull(IngestedAt)
| extend LagMinutes =
    datetime_diff("minute", IngestedAt, TimeGenerated)
| summarize P95LagMinutes=percentile(LagMinutes, 95)
    by Category
~~~

**Interpretation warning:** `TimeGenerated` is the event time from the source/record; `ingestion_time()` may be null or have different semantics depending on table and ingestion path. Clock skew, buffering, and provider delays affect observed lag. If metadata is unavailable, measure lag using a test event with a known UTC timestamp and checking when it becomes queryable.

### 16.4. When Metric Export Populates `AzureMetrics`

~~~kusto
AzureMetrics
| where TimeGenerated > ago(24h)
| summarize Samples=count(), LastSample=max(TimeGenerated)
    by MetricName
| top 20 by Samples desc
~~~

Verify the actual resource/provider metric schema; many metrics exist only in Metrics Explorer or the metrics API and never write to `AzureMetrics` via diagnostic settings. If `AzureMetrics` is empty, do not conclude "CPU is 0."

### 16.5. When a Source Emits No Events at All

A query like:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(15m)
| summarize Events=count()
~~~

can return 0 because no matching events occurred, the filter is wrong, ingestion is delayed, or export failed. **0 logs does not equal 0 errors or 100% availability.** Combine metric alerts, synthetic tests, per-source last-seen checks, and diagnostic configuration status checks.

### 16.6. Cross-Resource Correlation

Once logs exist for Key Vault, App Service, and SQL:

~~~kusto
AzureDiagnostics
| where TimeGenerated between (
    datetime(2026-11-20T09:00:00Z)
    ..
    datetime(2026-11-20T09:30:00Z)
  )
| summarize Events=count()
    by ResourceProvider, Category, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

This is **a temporal comparison across categories**. It does not prove causation between App Service 500s and Key Vault 403s; you still need trace/correlation IDs, resource logs, identity/audit evidence, and deployment records. Always use **UTC** when correlating logs across services.

## 17. Verifying Storage, Event Hubs, and Partner Destinations

### 17.1. Storage Export Acceptance Test

In the destination Storage account:

1. Confirm the account, region, permissions, and diagnostic setting ID.
2. Trigger an **authorized** event on the lab resource.
3. After an appropriate wait, list new containers/blobs by category and time.
4. Read the exported JSON and verify resource ID, event time, and operation.
5. Verify lifecycle and immutability policies match requirements.
6. Confirm a **read-only auditor** can read the blobs while application principals cannot delete archives.

Example **metadata read command** given appropriate permissions and auth mode:

~~~bash
az storage container list \
  --account-name "<approved-storage-account>" \
  --auth-mode login \
  --query "[].name" \
  --output table
~~~

This command only lists container names; it does not prove all log events were archived. With firewalls and Entra RBAC, even an Azure Resource Reader does not hold **Storage Blob Data Reader** by default.

### 17.2. Event Hubs Acceptance Test

Verify across three layers:

~~~text
1. Diagnostic setting:
   source + category + namespace rule + event hub name correct.

2. Event Hubs namespace/hub:
   incoming messages/bytes, throttling and partition health.

3. SIEM/consumer:
   consumer group offset/checkpoint advances,
   schema parsed, dedup and downstream persistence verified.
~~~

If Event Hubs `IncomingMessages` rises while the SIEM dashboard stays blank, the problem likely sits in the **consumer, subscription offset, or parser** rather than the diagnostic setting. If Event Hubs shows zero incoming messages, troubleshoot source category, permissions, networking, and region before debugging SIEM queries.

### 17.3. Partner Destination Acceptance Test

- Confirm the partner integration is provisioned in the right tenant and region.
- Verify the diagnostic setting points to the right partner resource.
- Trigger an authorized audit/log test event per policy.
- Match the original source event ID/timestamp against the partner dashboard.
- Document latency, filtering, parsing errors, and support escalation paths.
- Test revoking the integration without disrupting other logging destinations.

Never rely solely on "Partner connector connected" to claim every event reaches the SIEM. Both sides require independent monitoring and reconciliation.

## 18. Alerting on Logs and Metrics

Diagnostic settings only forward data; **alert rules** must be created separately. Distinguish:

### 18.1. Direct Metric Alert

~~~text
Azure SQL CPU percent > 80%
for a defined evaluation window
    ↓
Metric alert → Action Group
    ↓
On-call / automation with approvals
~~~

Metric alerts can respond without waiting for logs to be ingested into a workspace, where supported by the metric and resource. Choose aggregation, window, and severity carefully and check for false positives; 80% is an illustrative threshold, not a universal SLO.

### 18.2. Log Search Alert

~~~text
Key Vault audit category exported to Log Analytics
    ↓
KQL detects repeated failed access events
    ↓
Scheduled query rule / log alert
    ↓
Action Group / incident runbook
~~~

Example KQL when the workspace has `AzureDiagnostics` and the expected columns:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(15m)
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where Category == "AuditEvent"
| summarize Events=count() by ResultType
| order by Events desc
~~~

**This is an exploratory query, not a production-ready detection rule.** You must incorporate real failure/`ResultType` semantics for the table, baseline thresholds/behavior, suppression schedules, and data freshness. If data lands in a dedicated table, update the query schema accordingly. Never attach an Action Group that automatically disables all identities on a single error event.

### 18.3. Action Groups and Automation

An alert is only useful if it has an **owner and a runbook**. An Action Group can send emails/notifications/webhooks or invoke supported workflows, but automation that alters firewalls, revokes credentials, or deletes resources requires strict RBAC and approvals; never let alert noise trigger destructive actions automatically.

### 18.4. Missing Telemetry Alerts

If audit events or heartbeats are expected on a regular cadence, the system should alert when a **source goes silent**. However, a low-traffic resource may legitimately emit no logs for hours. Therefore, missing-log alerts need:

- **Expected active sources/inventory**.
- Authorized synthetic events or alternative health checks.
- Last-seen tracking and query ingestion lag awareness.
- Distinction between idle periods and delivery failures.

Never turn an infrequently triggered audit category into a naive "0 logs = outage" alert.

## 19. Data Collection Rules, Transformations, and Data Normalization

### 19.1. Diagnostic Settings vs. DCRs

**Diagnostic settings** are standard for platform resource logs and metric exports. **Data Collection Rules (DCRs)** define how to collect, transform, and route supported data streams, especially with **Azure Monitor Agent** and custom/agent ingestion paths.

~~~text
Azure resource platform logs/metrics
  → Diagnostic setting
  → Log Analytics / Storage / Event Hubs / partner

VM guest logs/performance counters
  → Azure Monitor Agent
  → Data Collection Rule
  → Azure Monitor Logs / other supported destinations

Application SDK / agent telemetry
  → Azure Monitor / Application Insights pipeline
  → Workspace-based monitoring as configured
~~~

Do not assume you can attach a DCR to any diagnostic setting for arbitrary **ingestion-time transformations**. Transformation support depends on **data source, stream, table, and plan**, so check product-specific capabilities; some resource logs and workspace modes do not support the transformations you might expect.

### 19.2. Schema Normalization When Streaming to Event Hubs

A SIEM consumer may receive records from Key Vault, App Service, Firewall, and Azure SQL with varying fields. Use a **normalized envelope** downstream:

~~~json
{
  "sourceResourceId": "/subscriptions/example/resourceGroups/rg-a/providers/Microsoft.KeyVault/vaults/kv-a",
  "provider": "Microsoft.KeyVault",
  "category": "AuditEvent",
  "eventTimeUtc": "2026-11-20T09:20:00Z",
  "ingestedAtUtc": "2026-11-20T09:22:10Z",
  "operation": "SecretGet",
  "outcome": "Success",
  "schemaVersion": 1
}
~~~

**This is a downstream design schema**, not a fixed output of diagnostic settings. If the consumer stamps `ingestedAtUtc` upon receipt, that represents **consumer ingestion time**, not necessarily when the Azure Monitor log was emitted. Retain raw records and mapping versions for investigations.

### 19.3. Data Deduplication and Replay

Not every record carries a provider-issued unique stable event ID. With Event Hubs:

- Use provider-provided IDs/correlation fields where available.
- Otherwise, define a composite key (**source + category + event time + operation + properties**) after assessing collision probability.
- Store the original source timestamp and stream offset.
- Checkpoint only after durable downstream processing.
- Build DLQ/quarantine handling inside your **consumer pipeline**, rather than assuming Azure Monitor provides a built-in dead-letter queue for all delivery failures.

For legally significant audits, never infer exact event counts from `dcount()` or a consumer lacking a deduplication and reconciliation strategy.

## 20. FinOps: Costs When Routing One Source to Multiple Destinations

Creating a diagnostic setting typically carries no standalone "per-setting" fee in most use cases, yet **destinations, processing, and retention usually incur charges**. Do not interpret "enabling Azure Monitor Diagnostic settings is free" to mean the whole pipeline is free.

### 20.1. Cost Drivers Table

| Component | Potential Billing Drivers |
|---|---|
| **Log Analytics ingestion** | Volume of logs ingested, pricing plan, and data type |
| **Log Analytics retention/query** | Interactive/long-term retention, search/queries per plan |
| **Storage** | Blob capacity, transactions, replication, lifecycle transitions, rehydration |
| **Event Hubs** | Tier, capacity/throughput units, partitions, retention, and extras |
| **Partner/SIEM** | Vendor ingestion, seats, retention, and licensing |
| **Networking** | Cross-region transfer, egress, private networking per design |
| **Azure Monitor alerts** | Scheduled query alerts, metric alerts, and notifications per pricing |
| **Engineering operations** | Consumer maintenance, compliance, incident response, backfills |

**Verify current pricing by region, Azure Monitor workspace plan, and data type.** Some Azure logs/metrics have distinct rate cards or free ingestion allowances/benefits; do not treat the illustrative model below as an actual invoice.

### 20.2. Data Volume Example

Suppose a group of resources emits on average:

~~~text
15 GB diagnostic resource logs / day
30 days
Destinations:
  Log Analytics workspace
  Storage archive
  Event Hubs → SIEM
~~~

Monthly logical source volume:

\[
15\ \text{GB/day}\times30\ \text{days}=450\ \text{GB/month}.
\]

Sending that stream to three destinations means all three must **process roughly 450 GB of logical source payload per month**, though you cannot simply compute `450 × 3` as exact billable bytes:

- Log Analytics bills according to **plan units and record types**.
- Storage involves **encoding, compression, metadata, and replication** differing from raw payload size.
- Event Hubs bills by **throughput/capacity/retention** with batching overhead.
- A SIEM may bill separately by records, bytes, or field count.
- Network egress/cross-region charges may apply.

The goal of this example is recognizing that **fan-out multiplies processed volume across destinations**, not replacing the Azure Pricing Calculator.

### 20.3. Volume Spike When Enabling `allLogs`

Before enabling:

~~~text
Audit category:       2 GB/day
Operational category: 13 GB/day

Required use case:
  Security team only needs audit.
~~~

Turning on `allLogs` for "convenience" forces the workspace to ingest **15 GB/day** instead of **2 GB/day**. That extra 13 GB/day impacts retention, cost, and PII exposure. Conversely, if SREs genuinely need operational categories, cutting them blindly to save money blinds investigations; decisions require **data value + owner + budget**.

### 20.4. Tiered Retention by Data Class

Illustrative strategy:

| Data Class | Log Analytics Interactive | Storage Archive | Condition |
|---|---:|---:|---|
| Frequent operational logs | 30 days | Based on business need | Frequently queried by SREs |
| Security audit | 90 days | 1–3 years or actual policy | SOC and compliance reviews |
| Debug/noisy telemetry | 7–14 days | Do not retain long-term unnecessarily | Cost/PII risk |
| Financial/legal audit | Per actual regulations | Approved immutability/retention | Organizational policy |

These thresholds are **not mandatory rules for every country or industry**. Retention across Log Analytics, Storage, Event Hubs, and partners is **independent**; shortening retention in Log Analytics does not purge logs already streamed to a SIEM.

### 20.5. Checking Ingestion Volume

In Log Analytics, the `Usage` table (when available and authorized) helps estimate volume by data type:

~~~kusto
Usage
| where TimeGenerated >= ago(30d)
| summarize UsageQuantity=sum(Quantity) by DataType
| order by UsageQuantity desc
~~~

**Do not treat `Usage.Quantity` as a standardized invoice across all pricing plans and tables.** Record units, coverage, and visibility depend on the workspace. When reconciling actual bills, use **Azure Cost Management + workspace usage/cost details** and record the exact billing period and plan.

### 20.6. Controlling Costs Without Sacrificing Compliance

- Enable only categories backed by approved needs and SLOs.
- Use the `audit` group or specific categories when only auditing is needed.
- Use direct metric alerts instead of exporting metrics into logs unnecessarily.
- Separate Log Analytics retention from Storage archive retention by data class.
- Avoid routing the same logs to the **same destination twice** via overlapping settings.
- Scrutinize high-volume providers (networking, Firewall, Storage data plane).
- Maintain ingestion/query dashboards, budget alerts, and clear cost owners.
- Evaluate DCR transformations **only where streams/tables support them**, rather than assuming any diagnostic category can be filtered by a DCR.
- When long-term retention is mandated, never delete audit logs to hit a cost target.

## 21. Monitoring the Diagnostic Export Pipeline Itself

A diagnostic setting is a **data transport path**, so the pipeline itself requires health monitoring. Lack of visibility into the export pipeline creates a "monitoring blind spot": when log export breaks, error dashboards can falsely make the system appear healthy.

### 21.1. Layers to Monitor

| Layer | Key Signals / Questions | Source of Evidence |
|---|---|---|
| **Source resource** | Is it emitting the expected logs/metrics? | Resource activity, test events, category docs |
| **Configuration** | Does the setting still exist with the right categories/destinations? | ARM GET, IaC, Policy compliance |
| **Log Analytics** | Last event time, table volume, ingestion lag? | KQL, usage/workspace metrics |
| **Storage archive** | Are containers/blobs growing and readable? | Storage inventory/metrics, test reads |
| **Event Hubs** | Incoming messages, throttling, consumer lag? | Event Hubs metrics, consumer checkpoints |
| **Partner** | Are events arriving with valid schema and timeliness? | Partner status/ingest metrics |
| **Governance** | Were permissions, retention, or network rules modified? | Activity Log, Policy, audits |

### 21.2. Last-Seen by Resource

Assuming `AzureDiagnostics` receives regular logs:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| summarize
    LastEventUtc=max(TimeGenerated),
    Events=count()
  by _ResourceId
| extend MinutesSinceLastEvent =
    datetime_diff("minute", now(), LastEventUtc)
| order by MinutesSinceLastEvent desc
~~~

**A resource missing from the output** does not mean it ceased to exist. It may simply have emitted no events in 24 hours, been blocked in routing, or switched to a resource-specific table. Missing-source alerts require an inventory of **expected resources** to compare against, rather than querying only resources that happened to emit data.

### 21.3. Expected Inventory to Detect Silent Resources

Pattern using a synthetic inventory table:

~~~kusto
let Expected = datatable(_ResourceId:string)
[
  "/subscriptions/example/resourceGroups/rg-lab/providers/Microsoft.KeyVault/vaults/kv-a",
  "/subscriptions/example/resourceGroups/rg-lab/providers/Microsoft.KeyVault/vaults/kv-b"
];
let Observed =
    AzureDiagnostics
    | where TimeGenerated > ago(1d)
    | summarize LastEventUtc=max(TimeGenerated)
      by _ResourceId;
Expected
| join kind=leftouter (Observed) on _ResourceId
| extend HasRecentEvent=isnotnull(LastEventUtc)
| project _ResourceId, LastEventUtc, HasRecentEvent
~~~

**This is a reference query when `AzureDiagnostics` exists.** It only indicates "had an event within a day," not that export failed; an idle Key Vault having zero requests all day is normal. Pair it with authorized synthetic tests or Policy compliance and Activity Log checks.

### 21.4. Do Not Monitor Only the Workspace

Healthy Log Analytics ingestion does not guarantee:

- Storage archive is receiving audit blobs;
- The Event Hubs SIEM consumer is still reading;
- A critical Key Vault didn't have its diagnostic setting deleted;
- PII isn't being sent to a partner against policy.

If using **three destinations**, enforce **at least one meaningful delivery check per destination** with a named owner.

### 21.5. Alerting on Diagnostic Setting Changes

Resource control-plane changes appear in **Activity Log** when the operation/provider and scope are logged. Configure alerts/Policy compliance when:

- A diagnostic setting is deleted or a critical category is disabled.
- The destination workspace, storage account, or Event Hub is changed.
- Public network access or destination firewalls are altered.
- Audit archive retention or immutability is weakened.
- Privileged RBAC changes grant permission to delete audit data.

**Avoid circular dependencies:** if alerts about deleting diagnostic settings depend exclusively on logs flowing through that very diagnostic setting, you may receive no alert. Use Activity Log/Policy and independent paths for critical monitoring.

## 22. Troubleshooting: Setting Created Successfully, Yet No Data Appears

### 22.1. Symptom Matrix

| Symptom | Common Cause | Investigation Path |
|---|---|---|
| `categories list` is empty/unsupported | Wrong resource type/scope or provider has no categories | Verify ARM resource ID and API/provider capabilities |
| CLI reports invalid `categoryGroup` | Resource does not support `allLogs`/`audit` | Use individual supported categories |
| CLI reports invalid `AllMetrics` | Metric export unsupported | Discover metrics; use metric alerts |
| Setting saved, no table in workspace | No events yet, ingestion delay, different table mode | Test event, workspace ID, tables/schema |
| `AzureDiagnostics` does not exist | Resource-specific tables or zero ingestion | Check destination type and actual tables |
| KQL returns 0 rows | Wrong time range, resource ID, or Category | UTC, `_ResourceId`, time filter |
| Activity Log not reaching workspace | Only resource-level setting created | Create subscription-level Activity Log export |
| VM syslog not exported | Confusing platform diagnostics with guest collection | AMA + DCR |
| Logs reach Storage, missing in KQL | Storage does not auto-feed Log Analytics | Separate ingest/query pipeline |
| Storage has no blobs | Region, firewall, permissions, or silent source | Destination rules, trusted services, source event |
| Event Hubs IncomingMessages stays flat | Wrong rule, hub, region, network, or categories | Delivery config and source validation |
| Event Hubs has messages, SIEM is blank | Consumer, offset, parser, or lag | Consumer groups, checkpoints, DLQ |
| Cross-region destination rejected | Regional source export constraint | Deploy same-region destination or supported option |
| Insufficient permissions to create/update | Missing `diagnosticSettings/write` or destination rights | Review RBAC on both sides |
| SIEM duplicates or delayed logs | Retries, checkpoints, partition behavior | Idempotency, lag, batch/schema validation |
| Log ingestion cost spikes | `allLogs`, data volume, new categories, duplicate paths | Workspace usage, categories, Cost Management |
| Security alert disappears after setting deletion | Alert relied solely on exported logs | Independent Activity Log/Policy alert |
| Metrics in Metrics Explorer, absent in `AzureMetrics` | Metric non-exportable or schema mismatch | Metric category support / destination mapping |

### 22.2. 10-Step Runbook

1. **Verify scope:** are you inspecting the exact subscription, resource group, type, resource ID, or child resource?
2. **Confirm signal type:** Activity Log, resource log, platform metric, application telemetry, or guest OS?
3. **Discover categories:** does the provider expose the needed category/group/metric export?
4. **Read actual configuration:** setting name, enabled categories, destination resource IDs, and table mode?
5. **Generate a safe test event:** did the source emit the expected signal at a recorded timestamp?
6. **Check region and permissions:** source/destination regions, Azure RBAC, networking/trusted services?
7. **Check destination health:** workspace ingestion, blob writes, EH IncomingMessages/consumer lag?
8. **Check parser/query:** correct table, column, category, resourceId, UTC range, envelope?
9. **Check cost, PII, and duplicates:** redundant settings or duplicated/late records?
10. **Verify the fix:** new events reach every destination, alerts/workbooks work, document evidence/runbook.

### 22.3. Scenario 1 — App Service HTTP 500 Not Found in Key Vault Logs

Do not look for Spring Boot HTTP 500 exceptions inside `KeyVaultAuditEvents`. App Service/Spring Boot 500s are **application/web-server signals**, whereas Key Vault audit events record which clients read secrets or were denied. Combine them:

~~~text
Spring Boot / Application Insights → HTTP 500 / exception trace
App Service resource logs        → web platform details (if supported)
Key Vault audit logs            → SecretGet/permission failures
Azure Activity Log              → config changes / deployments
~~~

Logs sharing a 09:20 timestamp do not automatically prove causation. You need request trace/correlation and a timeline.

### 22.4. Scenario 2 — Storage Has a Private Endpoint, Yet Receives No Logs

An application inside a VNet reads blobs over a Private Endpoint fine, while Azure Monitor diagnostic export writes zero new blobs. The destination firewall may be blocking Azure Monitor delivery under trusted-services rules, or there may be a region/permission mismatch. **The network path from app to storage differs from the path from the Azure Monitor platform to storage.**

Never disable the entire storage firewall. Check supported networking and service exceptions, RBAC/permissions, and source events; test on a lab Storage account.

### 22.5. Scenario 3 — Event Hubs Lagging

The diagnostic setting emits 5,000 records/second while the SIEM consumer processes 1,000 records/second. Backlog grows and risks exceeding retention. Adding more diagnostic settings **will not fix a consumer bottleneck**; scale consumer throughput/partitions per architecture, optimize parsers/checkpoints, trim duplicate/unneeded categories, and establish an archive/replay strategy.

### 22.6. Scenario 4 — KQL Uses the Wrong Table Mode

IaC deploys:

~~~bicep
logAnalyticsDestinationType: 'Dedicated'
~~~

Yet the analyst runs:

~~~kusto
AzureDiagnostics
| where Category == "AuditEvent"
~~~

The query returns empty because records go into a **resource-specific table**. Fix: identify the actual table created by the resource/provider, adopt its schema, update dashboards/alerts, and migrate existing queries. Never switch back to `AzureDiagnostics` just to hide outdated queries.

### 22.7. Scenario 5 — Policy Compliant, Yet Zero Audit Records

Azure Policy confirms the diagnostic setting exists with the right categories, yet the resource had zero audit events all day or the destination network blocks writes. **Setting compliance ≠ proof of delivery.** Use authorized synthetic tests and measure end-to-end delivery from source to workspace/archive/SIEM independently.

## 23. Case Study: Order Failures After a Key Vault Configuration Change

### 23.1. Context

An e-commerce company operates:

~~~text
Subscription:  production-commerce
Resources:
  App Service: orders-api
  Azure SQL Database: orders-db
  Key Vault: kv-orders
  Azure Firewall / network resources

Central observability:
  Log Analytics workspace: law-platform-prod
  Storage account: protected audit archive
  Event Hubs: streaming to SIEM
~~~

**Hypothetical incident:** At 09:10 UTC, a change alters Key Vault permissions or network rules. Starting at 09:20, the Spring Boot app receives 403s when reading secrets and emits HTTP 500s due to poor exception handling. The dashboard only shows rising request errors.

### 23.2. Recommended Collection Architecture

~~~mermaid
flowchart TB
    APP[App Service orders-api] --> APPDS[App Service diagnostic settings]
    KV[Key Vault kv-orders] --> KVDS[Key Vault diagnostic settings]
    SQL[Azure SQL Database] --> SQLDS[SQL diagnostic settings]
    SUB[Subscription Activity Log] --> SUBDS[Subscription diagnostic setting]
    APPDS --> LA[(Log Analytics)]
    KVDS --> LA
    SQLDS --> LA
    SUBDS --> LA
    KVDS --> ARCH[(Storage protected archive)]
    KVDS --> EH[Event Hubs]
    EH --> SIEM[Security SIEM]
    APM[Spring Boot Application Insights] --> LA
    LA --> KQL[Incident KQL / workbook]
~~~

**The Application Insights node is a separate application telemetry pipeline.** The diagram does not claim an App Service diagnostic setting automatically captures full Java traces. Destinations may reside in appropriate scopes/regions per policy and service support.

### 23.3. Selecting Specific Logs

| Source | Required Signals | Destinations |
|---|---|---|
| **Key Vault resource logs** | Access/audit operations, denied accesses emitted by provider | Log Analytics + Storage + SIEM via Event Hubs |
| **Subscription Activity Log** | Who changed configuration/roles/networking | Log Analytics, archive if required by policy |
| **App Service resource logs/metrics** | Supported HTTP request/response categories | Log Analytics |
| **Spring Boot Application Insights** | Exception stack traces, dependency calls, trace ID | App Insights workspace/telemetry pipeline |
| **Azure SQL logs/metrics** | DB failures/performance/diagnostics when supported | Log Analytics / metric alerts |

Never expect Key Vault audit logs to record plaintext **secret values**, and never log secret values into diagnostic pipelines. Audits describe requests, operations, principals, and results—not secret backups.

### 23.4. Investigation Timeline

~~~text
09:10 UTC  Activity Log: network/role change involving Key Vault
09:19 UTC  Key Vault audit: increase in denied SecretGet operations
09:20 UTC  App Insights: dependency failure and HTTP 500 spike
09:22 UTC  KQL dashboard: signals correlated by resource/time
09:26 UTC  SRE validates configuration and reaches on-call owner
09:35 UTC  Approved mitigation restores access
09:42 UTC  Error rate and freshness verified after deployment change
~~~

These timestamps are **instructional scenarios**, not real Azure measurements. Two events happening close in time **do not prove root cause**; inspect operation details, request traces, principal/network identities, and approved change records.

### 23.5. Log Volume Observation Query

Assuming data flows into `AzureDiagnostics`:

~~~kusto
let StartUtc = datetime(2026-11-20T09:00:00Z);
let EndUtc = datetime(2026-11-20T10:00:00Z);
AzureDiagnostics
| where TimeGenerated >= StartUtc and TimeGenerated < EndUtc
| summarize Events=count()
    by ResourceProvider, Category, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Read the result as an **event count table**; do not equate Key Vault log counts with HTTP 500 counts. If using Dedicated table mode, adapt the query to the actual table. For application trace correlation, query the Application Insights tables containing trace/dependency data with the proper correlation key.

### 23.6. Evidence Reaching Archive and SIEM

**Do not inspect only Log Analytics.** Security and compliance must verify:

1. Do audit blobs for 09:10–09:30 exist, parse cleanly, and have intact retention/immutability?
2. Did Event Hubs `IncomingMessages` rise during that window?
3. Did the SIEM consumer ingest and parse the records without drops or unmanaged duplicates?
4. Are timestamps and resource IDs consistent across destinations at the required schema level?
5. If the SIEM pauses temporarily, is there an archive/replay plan?

### 23.7. Remediation and Recurrence Prevention

- Roll back the faulty change via approved workflow; never grant permanent blanket Key Vault access.
- Handle `SecretGet` failures gracefully in Spring Boot without leaking internal details to clients.
- Add Alerts/Policy checks when Key Vault network/role settings or diagnostic settings change.
- Create KQL alerts for denied operations using the real schema, baseline, and safety checks.
- Archive audit logs per policy with restricted delete permissions.
- Add regression checks before network/identity changes in CI.
- Verify the telemetry pipeline **still works after mitigation**; never treat "HTTP 500 dropped to 0" as proof that audit logs are flowing again.

## 24. End-to-End Lab: Key Vault → Log Analytics → Storage/Event Hubs

The lab has two tiers: **A. read-only/design** when no Azure resources are available, and **B. hands-on execution on approved resources**. Never create resources or modify production networks/firewalls without authorization.

### 24.1. Preflight

| Variable | Meaning | Sensitivity |
|---|---|---|
| `SOURCE_ID` | ARM ID of the lab Key Vault | Metadata, not a key |
| `WORKSPACE_ID` | ARM ID of Log Analytics workspace | Metadata |
| `STORAGE_ID` | ARM ID of Storage archive if used | Metadata |
| `EVENT_HUB_RULE_ID` | ARM ID of Event Hubs authorization rule | Metadata; not a key value |
| `EVENT_HUB_NAME` | Hub receiving diagnostic records | Metadata |
| `SETTING_NAME` | Diagnostic setting name | Metadata |
| `SPRING_APP_ID` | App resource referenced during investigation | Metadata |

Never place **Storage account keys, Event Hubs connection strings, or Key Vault secret values** in READMEs, pipeline outputs, or logs. The variables above are resource IDs and names, not credentials.

### 24.2. Lab A — Without Modifying Azure

1. Diagram the data flow covering Key Vault resource logs, Activity Log, App Insights, Log Analytics, Storage, and Event Hubs.
2. Label each source as platform logs/metrics, Activity Log, application, or guest OS.
3. Choose destinations matching KQL, audit archive, and SIEM goals.
4. Define the resource-level diagnostic setting separately from the subscription-level Activity Log setting.
5. Draft Azure CLI `categories list`, `diagnostic-settings show/list`, and `create` commands, **without running write commands**.
6. Assess data residency, regional constraints, permissions, and networking.
7. Write `AzureDiagnostics` and `AzureActivity` KQL queries and define expected evidence.
8. Estimate volume, budget, and retention.

**Learning outcome:** understand exact sources, scopes, categories, and destinations before touching production permissions.

### 24.3. Lab B — Applying on a Lab Key Vault

**Only with approval and dedicated provisioned resources:**

1. Use `az account show` and the Portal to confirm the subscription and resource ID.
2. Run `az monitor diagnostic-settings categories list --resource ...` to discover categories.
3. List existing settings to avoid duplicates.
4. Choose **one** supported audit category or group.
5. Use the Portal or CLI `create` to export to the lab workspace.
6. Read back the setting with `show`.
7. Trigger a safe, authorized Key Vault test operation.
8. Query the workspace using the right table mode and UTC range.
9. Record **time to first visible record** and verified fields.
10. If Storage is approved, add the archive destination and verify real blobs.
11. If Event Hubs is approved, add the stream destination and verify incoming messages/consumer.
12. Cross-check resource IDs and operations across destinations.
13. Review cost and PII exposure.
14. Clean up **only lab configuration** per owner approval.

### 24.4. Copy-Ready Read-Back Commands

~~~bash
az account show --query "{id:id,name:name}" -o table

az monitor diagnostic-settings categories list \
  --resource "$SOURCE_ID" -o json

az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" -o json

az monitor diagnostic-settings show \
  --name "$SETTING_NAME" \
  --resource "$SOURCE_ID" -o json
~~~

These commands are **read-only**, though they require an authenticated token/role with access to the resource. They do not generate test data or prove delivery, so pair them with Portal/KQL/Storage/EH verification.

### 24.5. Acceptance Tests

| Test | Passing Criteria |
|---|---|
| Source scope | `SOURCE_ID` matches the exact resource/child resource |
| Categories | Listed as supported by the API |
| Setting | GET returns expected enabled logs/metrics and destination IDs |
| Log Analytics | Actual table contains at least one matching test event |
| KQL | UTC time, operation, resource ID, and category validate |
| Storage (if used) | New blob exists, parses cleanly, retention policy matches |
| Event Hubs (if used) | Incoming messages rise and consumer processes them |
| Partner (if used) | SIEM receives event with matching schema |
| RBAC | Analysts/auditors read within scope without unnecessary delete rights |
| Networking | Destination private/firewall restrictions still satisfy policy |
| Cost | Estimated ingestion + storage + streaming documented with owner |
| Monitoring | Detection strategy exists if export stops or goes silent |

### 24.6. Controlled Negative Testing Lab

When testing failure modes:

- Run a KQL query against the wrong table mode on the **lab** workspace and verify how to identify the real table.
- Query a time window containing no events and explain why 0 rows appear.
- Query as a user **without data-plane permissions** on the lab workspace and verify access denied.
- Test a mis-checkpointed Event Hubs consumer on the lab hub and explain lag and retries.

**Never test by deleting audit settings, revoking production RBAC, opening firewalls to the whole Internet, or deleting a production Key Vault.** Negative tests must stay tightly scoped with a recovery plan.

## 25. Comprehensive Exercises and Guiding Answers

### 25.1. Practice Questions

1. What problem do diagnostic settings solve, and what do they **not** solve?
2. Distinguish platform resource logs, metrics, Activity Log, app traces, and VM guest syslog.
3. When should you choose Log Analytics instead of Storage?
4. Why is Event Hubs not a long-term archive?
5. Do you need a separate diagnostic setting on each Azure resource?
6. Does resource category group `allLogs` include Entra sign-ins?
7. When should you pick the `audit` group or an individual category?
8. Metrics Explorer displays CPU, yet `AzureMetrics` is empty: what should you investigate?
9. What data requirements might arise if a workspace sits in a different region than the source?
10. How can Storage/Event Hubs regions be constrained relative to the source?
11. Why doesn't an App Service inbound Private Endpoint enable log exports from Azure Monitor?
12. State the CLI command to discover categories.
13. State the CLI command to list existing diagnostic settings.
14. Distinguish `SOURCE_ID` from `WORKSPACE_ID`.
15. Compare `AzureDiagnostics` with resource-specific tables.
16. Why can `logAnalyticsDestinationType='Dedicated'` break legacy KQL queries?
17. Why is the Activity Log diagnostic setting configured at subscription scope?
18. Why are AMA/DCR required to collect syslog from a VM?
19. If you need a 3-year immutable audit retention, which destination fits best?
20. If you need near-real-time streaming to a SIEM, which destination fits best?
21. Is fanning out one diagnostic setting to three destinations free?
22. How can you reduce volume without losing audits?
23. If `AzureDiagnostics` is missing in the workspace after 10 minutes, what should you check?
24. If Storage receives no blobs when a firewall is enabled, how do you troubleshoot?
25. If Event Hubs shows messages yet the SIEM is blank, where could the issue be?
26. Why should you avoid log alerts based solely on zero events?
27. Calculate monthly logical source data when logs average 15 GB/day over 30 days.
28. Describe the Policy `DeployIfNotExists` workflow for a fleet of resources.
29. How do you detect if someone deletes a diagnostic setting?
30. How do you prove an audit archive remains readable over the long term?

### 25.2. Sample Answers

**Q2:** Resource logs come from the resource provider, metrics are numeric series, Activity Log records subscription control-plane events, App Insights/OTel records application traces, and AMA+DCR collects guest OS data.

**Q6:** `allLogs` covers resource log categories **for that specific provider/resource**; it does not automatically capture Entra logs, application traces, or VM syslog.

**Q12:**

~~~bash
az monitor diagnostic-settings categories list \
  --resource "$SOURCE_ID" --output json
~~~

**Q13:**

~~~bash
az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" --output json
~~~

**Q16:** Dedicated mode routes logs to resource-specific tables; KQL queries hardcoded to `AzureDiagnostics` may fail to see new records.

**Q19:** A Storage Account with appropriate lifecycle and immutability policies; never treat Event Hubs or short-retention KQL tables as legal archives.

**Q23:** Check supported categories, exact resource ID/destination, whether a test event occurred, ingestion latency, dedicated vs. shared table mode, KQL time range/permissions, and network/region requirements.

**Q25:** Check consumer group, checkpoint/offset, consumer health, parser/schema mismatches, and downstream SIEM ingestion/retention.

**Q27:** 15 × 30 = **450 GB raw source volume** under the stated assumptions; do not multiply by destination count and call that exact billable bytes.

**Q29:** Use Azure Activity Log / Policy compliance and a monitoring channel independent of the diagnostic setting being protected.

### 25.3. Rubric

| Criterion | Passing Standard |
|---|---|
| **Signal classification** | Does not confuse resource/platform, Activity, app, and guest logs |
| **Destination choice** | Selects workspace/archive/EH/partner according to use case |
| **Scope and categories** | Correct ARM resource ID and supported categories |
| **IaC/CLI** | Separates read vs. write commands, resource vs. subscription scope |
| **Verification** | Executes real event tests and confirms arrival at every destination |
| **Security** | Addresses RBAC, TLS/network/firewalls, data residency/PII |
| **Cost** | Accounts for multi-destination fan-out, volume, retention, and cost owner |
| **Reliability** | Monitors the pipeline itself, lag, duplicates/replay, and runbooks |

## 26. Production Checklist for Diagnostic Settings

### 26.1. Before Creating or Modifying a Setting

- [ ] Exact data source identified: **resource logs, metrics, Activity Log, Entra logs, application, or guest OS**.
- [ ] ARM resource ID, subscription, child-resource scope, and resource owner confirmed.
- [ ] Supported log categories/category groups and metric export capabilities queried from the source.
- [ ] Clear business use case documented per category; `allLogs` is not enabled blindly.
- [ ] Log Analytics/Storage/Event Hubs/partner chosen based on query, archive, stream, and security needs.
- [ ] Source/destination region constraints, data residency, and cross-subscription rights verified.
- [ ] Existing diagnostic settings reviewed to prevent duplicates or overwriting others.
- [ ] Destination ownership, retention, budget, and on-call owner defined.
- [ ] Access model defined: who edits settings, queries logs, deletes archives, and reads the SIEM.

### 26.2. Log Analytics Configuration

- [ ] Workspace ID is a valid ARM resource ID and query access is configured.
- [ ] Table mode (**AzureDiagnostics/Dedicated**) chosen based on provider support.
- [ ] KQL dashboards and alerts target the actual deployed table/schema.
- [ ] Retention, pricing plan, and cost aligned with data class and policy.
- [ ] Real test event verified from a lab/staging resource after deployment.
- [ ] Ingestion delay measured; 0-record queries are not treated as proof of health.
- [ ] Workspace RBAC/table access restricted and unnecessary PII excluded.
- [ ] Query/usage monitoring active for high-volume categories.

### 26.3. Storage Archive Configuration

- [ ] Account sits in a valid region relative to the source and satisfies data residency.
- [ ] Firewall/trusted service/network policy verified for diagnostic export.
- [ ] Storage RBAC separates archive readers from retention admins.
- [ ] Lifecycle, replication, encryption, and immutability policies reviewed.
- [ ] Tested blob creation, JSON parsing, and retrieval by partition and time range.
- [ ] Auto-delete never set shorter than legal/compliance retention policy.
- [ ] Alerts configured if the archive pipeline stops or storage hits anomalies.

### 26.4. Event Hubs or Partner Configuration

- [ ] Namespace/hub/authorization rule IDs verified, with no plaintext SAS keys in IaC.
- [ ] Region, trusted services, network firewalls, and quotas verified.
- [ ] Consumer groups, checkpoints, replay, and poison-message handling have an owner.
- [ ] Verified both incoming messages **and** SIEM/downstream persistence.
- [ ] Retention covers expected downtime, backed by long-term archive if required.
- [ ] Schema/versioning, deduplication, and data classification validated.
- [ ] Partner contract, permissions, data residency, and egress approved.

### 26.5. IaC and Governance

- [ ] Diagnostic settings managed via Bicep/Terraform/ARM/Policy.
- [ ] PR reviews inspect scope, destinations, categories, and retention impact.
- [ ] Policy assignments use remediation identities with least privilege.
- [ ] Compliance dashboards **do not replace end-to-end data delivery tests**.
- [ ] Activity Log/Policy alerts fire when critical settings are modified or deleted.
- [ ] Change records, affected resource inventory, and rollback plans maintained.
- [ ] New resource provisioning automatically receives the baseline monitoring config.
- [ ] Scopes, destinations, or table modes are never changed without updating KQL queries.

### 26.6. After Making Changes

- [ ] Setting GET confirms expected categories, metrics, and destination IDs.
- [ ] A test event is verified arriving at **every required destination**.
- [ ] KQL/Blobs/consumers show matching timestamps, category, and resource ID.
- [ ] No destination failures, Event Hubs backlog/throttling, or quota issues occur.
- [ ] SRE/SOC teams have runbooks and appropriate read permissions.
- [ ] Cost Management and data volume checked in the following billing cycle.
- [ ] Audit/change approval evidence and owner sign-off recorded.

## 27. Safe Lab Cleanup Without Losing Audit Logs

A diagnostic setting and its destination can serve multiple teams. Deleting the wrong setting can **interrupt audit evidence**; deleting a Storage account or workspace can wipe data relied upon by multiple systems.

### 27.1. Before Deleting

1. Confirm the subscription, source resource ID, and setting name.
2. Read the setting and check whether the destination is shared.
3. Check whether Azure Policy or CI will recreate the setting if deleted.
4. Confirm the source has no active audit, compliance, or incident hold requirements.
5. If evidence must be preserved, export/retain via an approved mechanism before changing anything.
6. Obtain owner approval and a change ticket.
7. Confirm cleanup will not spill into shared resource groups or workspaces.

### 27.2. Read-Only Commands Before Cleanup

~~~bash
az account show --query "{id:id,name:name}" -o table

az monitor diagnostic-settings list \
  --resource "$SOURCE_ID" \
  --output json

az monitor diagnostic-settings show \
  --resource "$SOURCE_ID" \
  --name "$SETTING_NAME" \
  --output json
~~~

These commands only read metadata without touching data. To inspect a Storage archive, use Storage Blob Data Reader or equivalent permissions rather than granting subscription Owner just to list blobs.

### 27.3. Destructive Command Examples — Do Not Run Without Approval

~~~bash
# COMMENTED EXAMPLE ONLY.
# Deleting a diagnostic setting stops export from the source for that configuration.
# az monitor diagnostic-settings delete \
#   --resource "$SOURCE_ID" \
#   --name "$SETTING_NAME"

# NEVER delete an entire resource group, shared workspace, or storage account
# just to clean up a lab exercise.
# az group delete --name "<approved-lab-rg>" --yes
~~~

Never delete `AzureDiagnostics`, resource-specific tables, or Storage containers holding production audits to "save costs." With immutable retention, deletions are rightly blocked by policy; never attempt to bypass guardrails.

### 27.4. Cleanup Outcomes to Confirm

| Item | Expectation |
|---|---|
| **Lab-only** diagnostic setting | Removed/updated per approval without affecting other sources |
| Central workspace | Intact, still receiving logs from other resources |
| Archive Storage | Only lab data/policies adjusted per retention rules |
| Event Hubs/SIEM | Shared consumers remain uninterrupted |
| Azure Policy | Compliance impact assessed and remediation controlled |
| Budget | No orphaned lab resources left running |
| Evidence | Report logs actions taken, approver, and post-cleanup state |

## 28. References and Key Takeaways

### 28.1. Technical Sources to Verify During Implementation

- [Azure Monitor diagnostic settings](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings) — destination types, constraints, setting configuration.
- [Diagnostic settings destination information](https://learn.microsoft.com/azure/azure-monitor/essentials/diagnostic-settings#destinations) — notes on Log Analytics, Storage, Event Hubs.
- [Azure Monitor resource logs](https://learn.microsoft.com/azure/azure-monitor/essentials/resource-logs) — categories and data emitted by resource providers.
- [Azure Monitor platform metrics](https://learn.microsoft.com/azure/azure-monitor/essentials/data-platform-metrics) — metrics, aggregations, dimensions.
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log) — subscription-level control-plane logs.
- [Azure Monitor Logs and Log Analytics](https://learn.microsoft.com/azure/azure-monitor/logs/data-platform-logs) — workspaces, tables, queries, retention.
- [Kusto Query Language](https://learn.microsoft.com/kusto/query/) — writing KQL and querying ingested tables.
- [Data Collection Rules](https://learn.microsoft.com/azure/azure-monitor/data-collection/data-collection-rule-overview) — data sources, transformations, and routing distinct from diagnostic settings.
- [Azure Monitor Agent](https://learn.microsoft.com/azure/azure-monitor/agents/azure-monitor-agent-overview) — guest OS collection.
- [Azure Monitor alerts](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-overview) — metric/log alerts and action groups.
- [Azure Event Hubs overview](https://learn.microsoft.com/azure/event-hubs/event-hubs-about) — consumers, partitions, throughput, retention.
- [Azure Storage immutable blob storage](https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview) — WORM/retention.
- [Azure Monitor pricing](https://azure.microsoft.com/pricing/details/monitor/) — ingestion, retention, alerts, and related charges.
- [Azure CLI diagnostic settings commands](https://learn.microsoft.com/cli/azure/monitor/diagnostic-settings) — command syntax and supported versions.

Table names, commands, categories, partner integrations, API versions, and regional features evolve over time. In production design, verify **current documentation, supported categories queried directly from the resource, and your tenant's pricing/RBAC/network constraints**, rather than assuming one illustrative example applies uniformly to every resource.

### 28.2. Twelve Core Takeaways

1. **Diagnostic settings route supported Azure platform logs and metrics**; they do not automatically collect all application, guest OS, or identity telemetry.
2. **Scope is critical**: resource logs live on resources/child resources; Activity Log lives at the subscription; Entra logs have separate configurations.
3. **Category names must be discovered**: `allLogs`/`audit`/`AllMetrics` are not universally available on every resource.
4. **Log Analytics is for KQL**, Storage is for archiving, Event Hubs is for streaming, and partners are for approved third-party integrations.
5. **One setting can target multiple destinations**, but doing so increases duplication, cost, and governance complexity.
6. **`AzureDiagnostics` is not the only table**: Dedicated/resource-specific tables, `AzureActivity`, and `AzureMetrics` have distinct semantics.
7. **Private networking does not automatically open Azure Monitor delivery paths**; check regions, firewalls/trusted services, and permissions per destination.
8. **Azure RBAC for editing settings differs from data-plane rights to read logs, archives, or Event Hubs.**
9. **Successful configuration does not prove data arrived**: test with a source event and verify each destination.
10. **Logs can arrive late, duplicate, or go unemitted**: never equate 0 events with 0 errors or 100% availability.
11. **Security, retention, and cost move together**: never enable `allLogs` or retain every payload indefinitely without a policy.
12. **Manage diagnostic settings via IaC/Policy and monitor the pipeline itself**: track setting changes, data freshness, delivery failures, SIEM consumer lag, and archive integrity.

### 28.3. Conclusion

An Azure **Diagnostic Settings and Monitoring Export Destinations** architecture only works reliably when it uses **the right source and scope, verified supported categories, the right Log Analytics/Storage/Event Hubs or partner destination, proper permissions and network paths, end-to-end delivery verification from source event to consumer, and clear policies for retention, auditing, alerting, cost, recovery, and change governance**.

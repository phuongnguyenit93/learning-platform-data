# Collecting Data with Azure Monitor Agent and Data Collection Rules

An application system runs on three Azure Windows VMs and two Linux VMs. The operations team wants to know: are there unusual login failures, which Windows Event Logs report service errors, when did CPU spike, and did Linux services log Syslog warnings? Another team wants to collect custom application logs while keeping only useful records to avoid inflating Log Analytics costs. If every VM is configured manually without collection standards, centralized updates, or post-installation data-flow checks, you quickly hit **agent installed yet Log Analytics stays empty**, or **over-collection driving up costs**.

**Azure Monitor Agent (AMA)** is the data-collection component running on supported machines. A **Data Collection Rule (DCR)** is an Azure resource configuration specifying **which data sources to collect, how to process/transform them, and which destinations to send them to**. A **Data Collection Rule Association (DCRA)** binds a DCR to a target resource, such as a VM, so the agent receives the intended configuration.

```text
Azure VM / Azure Arc-enabled server
   |
   | Azure Monitor Agent (AMA)
   |   - receives configuration from DCR associations
   |   - collects declared sources
   v
Data Collection Rule (DCR)
   |
   +-- Data sources: Windows Events, Linux Syslog, performance counters,
   |                 custom text/JSON logs as supported
   |
   +-- Transform KQL (when configured and supported)
   |
   +-- Data flows: stream -> destination
   |
   v
Destination: Log Analytics workspace / other supported targets
   |
   v
Azure Monitor Logs
   |
   +-- KQL: Event / Syslog / Perf / Custom tables
   +-- Workbooks, alerts, dashboards, investigations
```

Key takeaway: **AMA, DCR, DCRA, DCE, and Log Analytics workspace are not five names for the same object.** They handle distinct responsibilities with separate lifecycles, permissions, and networking requirements.

This lesson belongs to the **Monitoring and Observability** chapter of the `CLOUD_PROVIDERS_AZURE` module. This module explores the Microsoft Azure ecosystem from subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and data through deploying, monitoring, securing, and controlling the cost of an application architecture. Accordingly, the lesson moves from **designing signals to collect** to **configuring agents/rules, verifying arriving data, securing telemetry, optimizing ingestion cost, and troubleshooting**.

> Examples use common architectures for Azure VMs/Arc-enabled servers and Azure Monitor Logs. Features, Azure CLI extension/API versions, data source types, endpoint models, regions, pricing, quotas, defaults, and private link requirements can change. Always verify against your actual environment, organizational policy, and product documentation before deploying to Production. Commands and templates with placeholders must be populated with real resource IDs, and all create/modify/delete operations must run only in approved environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish Azure Monitor, Azure Monitor Logs, Log Analytics workspaces, AMA, DCR, DCRA, and DCE.
2. Describe the **data path** from Windows/Linux VMs to Log Analytics tables.
3. Select collection settings for **Windows Event Logs, Linux Syslog, and performance counters** based on monitoring requirements.
4. Understand support scope for **custom log files**, DCR stream declarations, and ingestion-time transformations.
5. Build DCRs with well-defined data sources, destinations, and data flows.
6. Attach DCRs to machines via **DCR associations** and verify that the AMA extension is healthy.
7. Distinguish **Azure Activity Log**, VM guest logs, diagnostic settings, metrics, and application telemetry.
8. Recognize when a **Data Collection Endpoint (DCE)** is involved in configuration/ingestion and Azure Monitor Private Link.
9. Design consistent fleet deployments using Azure Policy, IaC, and change governance.
10. Use KQL to query `Heartbeat`, `Event`, `Syslog`, and `Perf`.
11. Isolate failures across **agent**, **association**, **DCR**, **workspace**, **network/identity**, and **query**.
12. Optimize ingestion volume, transformations, retention, and cost by source.
13. Protect log data against PII/secret leakage and enforce least-privilege administrative access.
14. Build a Production checklist, lab exercises, and troubleshooting runbooks.

## 2. Which Signals Does System Observability Need?

Observability lets you infer the internal state of a system from operational outputs. Three signal groups are commonly used:

| Signal | Question Answered | Example |
|---|---|---|
| **Logs** | What happened and why? | Windows Events, Linux Syslog, application logs. |
| **Metrics** | How much or how fast is something changing? | CPU, memory, disk I/O, requests/sec. |
| **Traces** | Which services did a request pass through? | Distributed traces in Application Insights/OpenTelemetry. |

Azure Monitor Agent primarily participates in **collecting supported guest OS data types**, not replacing full distributed tracing. Traces from Java/.NET apps usually rely on Application Insights/OpenTelemetry and separate telemetry export paths.

### Define Questions Before Collecting

For instance, operators may want to:

- Detect Windows service failures within 5 minutes.
- Investigate failed logins within an approved scope and permission boundary.
- Track 5-minute average CPU across processing hosts.
- Alert if a VM stops sending heartbeats for more than 15 minutes.
- Analyze Syslog messages related to SSH or application daemons.
- Forecast Log Analytics ingestion to prevent unexpected budget overruns.

Every requirement should specify **source, fields, acceptable latency, storage target, permissions, retention, alert, and cost**. Never collect all Debug-level logs first and go looking for a use case afterward.

## 3. Map of Key Resources

| Component | Role | Where It Lives |
|---|---|---|
| **Azure Monitor Agent (AMA)** | Reads supported guest OS/agent data sources and forwards per rules. | Extension/agent on Azure VMs, Arc-enabled servers, and supported environments. |
| **DCR (Data Collection Rule)** | Declares data sources, stream routing, transformations, and destinations. | Azure resource `Microsoft.Insights/dataCollectionRules`. |
| **DCRA (Data Collection Rule Association)** | Attaches a DCR to a source resource such as a VM. | Association resource attached to the monitored resource. |
| **DCE (Data Collection Endpoint)** | Endpoint for configuration/ingestion scenarios requiring it, including some private-link setups. | Dedicated Azure resource per service conditions. |
| **Log Analytics workspace** | Stores and queries log tables; enforces governance and retention. | `Microsoft.OperationalInsights/workspaces`. |
| **Azure Policy** | Automatically deploys agents/DCRs to matching sources at scale. | Assignments, definitions, and remediation tasks. |
| **Azure Monitor Logs / KQL** | Queries, alerts on, and analyzes ingested data. | Workspace, tables, and query engine. |
| **Diagnostic settings** | Routes resource/platform logs and metrics where supported by the resource. | Configuration attached to each Azure resource. |

### Three Separate Actions

1. **Install AMA** on the machine.
2. **Create a DCR** describing collection.
3. **Create a DCRA** linking the machine to the DCR.

Missing any one of the three steps can result in no expected data arriving. Conversely, a DCR can exist without being associated with any machine yet.

## 4. Distinguishing Guest Log Sources from Azure Platform Logs

A frequent design mistake is assuming AMA is responsible for every Azure log.

| Source | Typical Mechanism | Table / Destination |
|---|---|---|
| **Windows Event Logs inside guest OS** | AMA + Windows Event Logs DCR. | `Event` in Log Analytics when routed to a workspace. |
| **Linux Syslog inside guest OS** | AMA + Syslog DCR; requires an active syslog daemon/source. | `Syslog`. |
| **OS performance counters** | AMA + Performance Counters DCR. | `Perf` or another supported stream/destination per config. |
| **Custom text logs on VM** | AMA custom logs + DCR for supported file formats. | Configured custom table. |
| **Azure subscription Activity Log** | Activity Log export / diagnostic settings by scope. | E.g., `AzureActivity` if sent to a workspace. |
| **Azure resource logs** | Diagnostic settings or dedicated platform pipelines. | Resource-specific or legacy tables per configuration. |
| **Application Insights traces** | App instrumentation/SDK/OTel. | Application telemetry tables per workspace/service. |
| **AKS Container Insights** | Supported container monitoring agent/pipeline. | Corresponding Container Insights tables. |

**A DCR for AMA does not automatically collect the subscription Activity Log.** To investigate ARM changes to resource groups or VMs, design a separate Activity Log export path.

## 5. AMA Replaces Legacy Collectors in Many Scenarios

Older documentation or systems may still run the **Log Analytics agent / Microsoft Monitoring Agent (MMA)** or Linux OMS agent. Those are legacy components; check their support status and migration plan in active environments.

AMA moves collection configuration into **centrally managed DCRs** with fine-grained source selection and routing, though not every legacy scenario has an exact 1:1 replacement.

### What to Check Before Migrating

- Is the machine OS/distribution supported by AMA?
- Which sources and tables were previously collected?
- Are legacy workspace agent configurations still active?
- Is the host an Azure VM or an Arc-enabled machine?
- Do custom app logs require changing source paths, formats, or tables?
- Which tables do existing alerts and workbooks query?
- Is another collector capturing the same events and causing duplicates?
- Do permissions, networking, and data ingestion paths change?
- Is running agents in parallel needed during a canary phase?
- When will the legacy collector be removed to prevent duplicate ingestion?

Never remove the legacy agent until you have evidence that **the new AMA data is complete and alerts still fire properly**.

## 6. Collection Architecture from an Azure VM

Simplified flow:

```text
Azure VM (Windows/Linux)
   |
   +-- OS emits events/counters
   |
   +-- AMA extension runs in guest OS
   |     |
   |     +-- gets effective collection config
   |     |    from DCR association(s)
   |     |
   |     +-- selects requested records
   |     +-- sends streams to monitoring pipeline
   |
   v
Azure Monitor ingestion
   |
   v
Log Analytics workspace
   |
   +-- Event / Syslog / Perf
   +-- Alerts, Workbooks, KQL
```

In standard management workflows, DCRs are not "manually copied into an agent config file." The agent pulls its effective configuration through Azure resources and associations.

### One Machine Can Participate in Multiple Rules

A single VM can be linked to multiple DCRs within feature limits. For example:

- DCR A: Windows Event Logs.
- DCR B: Performance counters.
- DCR C: Custom application logs.

This helps split ownership across teams, yet can **collect the same data twice** if multiple rules overlap on sources, streams, and destinations. Never treat attaching two identical DCRs as free redundancy.

## 7. DCR: Four Configuration Layers

An AMA DCR can declare:

```text
DCR
 |
 +-- dataSources
 |     +-- windowsEventLogs
 |     +-- syslog
 |     +-- performanceCounters
 |     +-- logFiles / supported extensions
 |
 +-- streamDeclarations (when custom streams are needed)
 |
 +-- destinations
 |     +-- logAnalytics
 |     +-- other supported destinations as applicable
 |
 +-- dataFlows
       +-- from stream(s)
       +-- optional transformKql / outputStream
       +-- to named destination(s)
```

**Not every DCR contains all of these blocks.** A Windows Events–only rule needs no Syslog section. Custom streams add schema declarations. Transformation support can depend on source/destination types and API versions.

### Relationship Between Streams and Tables

- **Stream**: the logical data shape in the pipeline, e.g., `Microsoft-WindowsEvent`.
- **Destination**: the target sink, e.g., a Log Analytics workspace.
- **Table**: where records appear after ingestion, e.g., `Event`.

Do not confuse the stream name `Microsoft-WindowsEvent` with the table name `Event` when writing KQL.

## 8. DCR Association: Applying Rules to the Right Machines

Suppose you have:

```text
dcr-windows-baseline
    |
    +-- associated with vm-win-01
    +-- associated with vm-win-02

dcr-linux-baseline
    |
    +-- associated with vm-linux-01
    +-- associated with arc-linux-02
```

A DCRA links a monitored resource to a rule. Attaching a Linux-specific DCR to a Windows VM by mistake will fail to produce expected data.

### Rules of Thumb

1. Creating a DCR is not enough: verify the **actual association**.
2. The association's resource ID must point to the exact VM or Arc machine.
3. The agent must be present and healthy on the source.
4. The DCR and its data sources must match the OS.
5. The destination must point to the right workspace and environment.
6. Resource/location constraints between the DCR and monitored machine must satisfy current rules.
7. Azure Policy assignments/remediations may create associations automatically; check to avoid overlapping actions.
8. After updating a DCR, the agent needs time to pull and apply the config; verify changes with telemetry rather than expecting instant results.

**A DCRA is not a network path.** It is an Azure resource binding; the agent still requires valid connectivity, identity, permissions, and routing.

## 9. DCE: Is a Data Collection Endpoint Always Required?

**No.** A common misconception is that every DCR requires a user-created DCE.

A DCE is an endpoint used in **configuration or ingestion scenarios** that require one—such as certain architectures using **Azure Monitor Private Link Scope (AMPLS)**, private networking requirements, or specific data ingestion paths. Newer DCRs and APIs may provide their own ingestion paths/endpoints depending on features.

### Decision Matrix

| Scenario | What to Verify |
|---|---|
| AMA on Azure VM collecting Windows Events/Perf over standard supported network paths. | May not need a manually created DCE; follow actual DCR/network requirements. |
| AMA with Azure Monitor Private Link / AMPLS. | Check DCE, configuration associations, and private DNS/network rules per current docs. |
| Direct Logs Ingestion API from an application. | Endpoint and DCR configuration for the API, authorization, and stream schema; do not confuse with AMA. |
| Arc-enabled server behind a firewall/proxy. | Agent/service endpoint connectivity, Arc prerequisites, and DCE/private networking constraints. |

A DCE does not store logs; data is still routed to destinations. **Do not create a DCE merely because you saw the word "endpoint,"** nor skip a DCE when your private link architecture actually requires one.

## 10. Selecting the Log Analytics Workspace and Governance Scope

The workspace governs several factors:

- Region and data residency per service rules.
- Access control and RBAC model.
- Data retention and table plans.
- KQL queries, workbooks, and alerts.
- Ingestion, billing, and commitment tiers if applicable.
- Cross-team and multi-tenant governance.
- Private networking/Private Link and exports.
- Incident forensics and auditing.

### One Workspace or Several?

**One shared workspace** simplifies correlation and centralized governance. **Multiple workspaces** enforce boundaries across environments, business units, or regulatory jurisdictions, at the cost of more complex cross-workspace queries and operations.

A DCR can route streams to Log Analytics destinations as supported by the API, but **do not treat a workspace as an isolated per-VM data silo**. Govern which workspace receives which streams and who can query them.

### Scope Discipline

Never mix Production logs containing PII into a lab workspace just to save money. Decisions must follow **data classification, roles, retention, residency, performance, and budget**.

## 11. Preparation Before Installing AMA and Creating a DCR

Checklist:

1. Select the right Azure tenant, subscription, and resource group.
2. Verify Windows/Linux OS versions and VM/Arc support.
3. Identify whether targets are Azure VMs, VM Scale Sets, or Arc-enabled servers.
4. Decide the workspace and region.
5. Specify only needed signals: Event, Syslog, Perf, custom logs.
6. Estimate daily data volume and required latency.
7. Check managed identity and agent prerequisites in the environment.
8. Verify network routes, TLS, DNS, firewalls, and private link.
9. Structure DCRs by OS and operational needs.
10. Define who can create/edit DCRs and DCRAs, and who can query logs.
11. Establish tags, owners, naming, IaC, and rollout plans.
12. Prepare verification queries and approved test events.
13. Prepare rollback to the previous DCR if a new rule filters incorrectly.
14. Establish policies for sensitive data, retention, and anomaly alerts.

**Crucial preflight check:** a machine managed by another collector may already forward Syslog or Windows Events to a workspace. Adding AMA without accounting for the old collector can double your bill.

## 12. Installing Azure Monitor Agent on a Windows VM

A common workflow in the Azure Portal:

1. Open the lab Windows VM.
2. Navigate to Extensions / Monitoring or the supported Azure Monitor collection flow.
3. Install or verify the **Azure Monitor Windows Agent** extension.
4. Confirm extension provisioning status and health.
5. Create a Windows DCR with Windows Event Logs / Perf data sources.
6. Create an association from the exact VM to the DCR.
7. Verify workspace, permissions, and network connectivity.
8. Generate a non-sensitive lab test event if needed.
9. Query `Event`/`Perf` tables and heartbeat records.
10. Observe ingestion latency.

The extension name in the Azure VM API is typically `AzureMonitorWindowsAgent` under publisher `Microsoft.Azure.Monitor`; **verify supported parameters, versions, and regions before codifying in IaC**.

Not every Portal flow installs the agent in the exact same step as creating the DCR; always **verify actual extension status** rather than guessing.

## 13. Installing AMA on Linux and Azure Arc

Linux hosts can send Syslog and Perf data through AMA when the OS and agent are supported. For servers outside Azure, Azure Arc-enabled Servers provide a resource identity to manage extensions and DCR associations.

```text
Azure Linux VM / Arc-enabled Linux server
      |
      +-- AMA Linux agent
      +-- OS syslog daemon and logs
      +-- DCR association for Linux sources
      |
      v
Azure Monitor Logs
      |
      v
Syslog / Perf / supported custom tables
```

### Key Considerations

- On Linux, the **Syslog** source must actually be generated/forwarded by the system daemon per OS config.
- Check `rsyslog`/`syslog-ng` or the distro's logging pipeline; do not blindly alter every OS setting just to "force logs out."
- Linux performance counter names and OS support may differ from Windows.
- The AMA Linux extension is commonly named `AzureMonitorLinuxAgent`.
- Arc machines require Arc connectivity, the Arc agent, and matching policies/associations.
- A DCR only captures data **after** the agent and source are active; it cannot recover unretained historical logs.
- Agents transmit over supported network paths; proxies and private links may require explicit configuration.

## 14. Windows Event Logs: Picking the Right Channels and Levels

On Windows, common event channels include:

- **Application**: application and service errors.
- **System**: service, driver, and OS events.
- **Security**: logins, audits, and sensitive events requiring strict access controls.
- **Custom application/provider channels**: depending on installed software.

AMA/DCR Windows Event Logs can select events using **XPath expressions** matching the data source contract.

Conceptual example:

```text
Application!*[System[(Level=1 or Level=2 or Level=3)]]
```

In many Windows Event Log schemas:

- Level 1: Critical.
- Level 2: Error.
- Level 3: Warning.

This is an XPath query for the **Windows Event Log source**, not KQL run against Log Analytics.

### Why Not Collect Every Event?

Security audits and verbose application events can generate massive volume, impacting cost and privacy. Select event IDs, channels, and severities tailored to your use cases and retention policies.

### Warnings

- Validate event log levels and IDs against the specific provider and monitoring goal.
- Never stream Security logs into a workspace accessible by unauthorized users.
- Use channel/XPath syntax supported by AMA; do not assume any arbitrary Windows event query expression is valid.
- For Windows Events from AMA, the Log Analytics table is typically `Event`, though other pipelines may write to `WindowsEvent`. Query the actual table produced by your source.

## 15. Performance Counters: Metrics and Sampling Frequency

Performance counters capture CPU, memory, disk, and other guest OS signals.

Windows examples:

```text
\Processor(_Total)\% Processor Time
\Memory\Available MBytes
\LogicalDisk(_Total)\% Free Space
```

The data source normally specifies:

- A list of `counterSpecifiers`.
- `samplingFrequencyInSeconds`.
- Matching stream/output, e.g., `Microsoft-Perf`.
- Destination and data flow.

### Choosing Sampling Frequency by Use Case

- 60 seconds is often sufficient for capacity trends and many operational alerts.
- 10–15 seconds helps catch very short bursts but increases volume.
- 5 minutes lowers cost but can miss brief spikes.

This is an **engineering trade-off**, not a fixed service default. Beyond counter names, verify OS, locale, and agent support.

**Perf Logs** and **Azure Monitor Metrics** can follow different storage and monitoring paths. Do not assume every counter in a DCR lands in the `Perf` table if the DCR routes it to another stream or destination.

## 16. Linux Syslog: Facilities and Severities

Syslog messages carry structured metadata including:

- **Facility**: source category such as `auth`, `authpriv`, `daemon`, `syslog`, `local0`, etc.
- **Severity/level**: Debug, Info, Notice, Warning, Error, Critical, Alert, Emergency per standard definitions.
- **ProcessName**/source and message text.
- Timestamp, host, and metadata.

Example matrix:

| Facility | Monitoring Goal | Suggested Trial Level |
|---|---|---|
| `authpriv` | SSH/login authentication. | Warning/Error and above, or dedicated audit policy. |
| `daemon` | Background services. | Warning/Error/Critical. |
| `local0` | Application syslog directed to this facility. | Based on application SLO. |
| `syslog` | Daemon/system logging. | Warning/Error and above. |

This is purely a design example. Facility and level choices must reflect **the real event-producing sources**; Linux distributions vary, and some logging pipelines bypass traditional syslog.

**Do not assume filtering for Error alone is enough for security:** important authentication events sometimes carry other severities; verify against organizational audit requirements.

## 17. Illustrative DCR JSON for a Windows VM

Example **DCR resource body** for a lab Windows VM. This is structured JSON showing data sources and destinations for learning—not a complete ARM template or copy-paste deployment command.

```json
{
  "location": "eastus",
  "properties": {
    "dataSources": {
      "windowsEventLogs": [
        {
          "name": "application-critical-errors",
          "streams": ["Microsoft-WindowsEvent"],
          "xPathQueries": [
            "Application!*[System[(Level=1 or Level=2 or Level=3)]]"
          ]
        }
      ],
      "performanceCounters": [
        {
          "name": "cpu-and-memory",
          "streams": ["Microsoft-Perf"],
          "samplingFrequencyInSeconds": 60,
          "counterSpecifiers": [
            "\\Processor(_Total)\\% Processor Time",
            "\\Memory\\Available MBytes"
          ]
        }
      ]
    },
    "destinations": {
      "logAnalytics": [
        {
          "name": "la-ops",
          "workspaceResourceId": "/subscriptions/SUBSCRIPTION_ID/resourceGroups/RG_MONITOR/providers/Microsoft.OperationalInsights/workspaces/LAW_OPS"
        }
      ]
    },
    "dataFlows": [
      {
        "streams": [
          "Microsoft-WindowsEvent",
          "Microsoft-Perf"
        ],
        "destinations": ["la-ops"]
      }
    ]
  }
}
```

### Reading This Configuration

1. `windowsEventLogs` selects only Application Critical/Error/Warning events.
2. `performanceCounters` samples CPU and memory roughly every 60 seconds.
3. Both streams flow into the named destination `la-ops`.
4. The workspace resource ID must be a valid, authorized ID.
5. A deployable DCR still requires a resource name, Azure API version, and associations for agents to use it.
6. Validate configuration against the current resource provider and DCR service version.
7. This DCR **fits Windows Event Logs only**; associating it with Linux will not produce expected data.
8. Updating a DCR can change ingested volume and downstream alerts.

**The JSON contains no workspace shared keys, tokens, or connection strings.** The DCR/resource platform handles configuration using supported identity and network models.

## 18. Illustrative Syslog DCR for Linux

A `dataSources` snippet for Linux:

```json
{
  "dataSources": {
    "syslog": [
      {
        "name": "security-and-daemon",
        "streams": ["Microsoft-Syslog"],
        "facilityNames": [
          "auth",
          "authpriv",
          "daemon",
          "syslog"
        ],
        "logLevels": [
          "Warning",
          "Error",
          "Critical",
          "Alert",
          "Emergency"
        ]
      }
    ]
  }
}
```

A complete DCR also requires:

- `location` and appropriate resource metadata.
- `destinations`, such as Log Analytics.
- `dataFlows` mapping the `Microsoft-Syslog` stream to the destination.
- Associations to supported Linux/Arc machines.
- Healthy Linux AMA and an active syslog source.

**Do not copy this snippet and assume a complete DCR resource was created.** The JSON above illustrates only the Syslog data source selection.

### Impact of Facility Selection

A DCR collecting only `daemon` will miss `authpriv` events. Likewise, if an app writes to `local0` while the rule omits `local0`, KQL cannot retrieve events that were never ingested.

## 19. Data Flows: Routing from Stream to Destination

A DCR data flow describes the path:

```text
source windowsEventLogs
     -> stream Microsoft-WindowsEvent
     -> dataFlow
     -> destination la-ops
     -> table Event

source performanceCounters
     -> stream Microsoft-Perf
     -> dataFlow
     -> destination la-ops
     -> table Perf
```

When using custom streams, `streamDeclarations` and `outputStream` may be needed to map input fields to the target schema and table.

### Easy to Confuse

- **Source name**: e.g., `cpu-and-memory`.
- **Stream name**: `Microsoft-Perf`.
- **Destination name**: `la-ops` inside the DCR.
- **Workspace resource name**: `law-operations-prod`.
- **Log Analytics table**: `Perf`.

These are five distinct identifiers serving different roles. Mixing up stream and destination names can cause ingestion rejections or data landing in the wrong place.

## 20. Ingestion-Time Transformations with KQL

A DCR can apply a **KQL transformation at ingestion time** for supported streams and destinations. Purposes:

- Filter out unneeded events.
- Project only permitted fields.
- Normalize or trim data to match target schemas.
- Reduce volume and protect sensitive fields before storage where supported.

Example **expression pattern** for Windows Events with an `EventID` field:

```kusto
source
| where EventID in (1000, 1001)
```

Inside a DCR data flow, configuration might include:

```json
{
  "streams": ["Microsoft-WindowsEvent"],
  "destinations": ["la-ops"],
  "transformKql": "source | where EventID in (1000, 1001)"
}
```

**Important notes:**

1. This uses an **ingestion-time KQL subset/contract**; not every query-time KQL operator is accepted.
2. Input columns must exist in the corresponding stream schema.
3. Output fields/types must match the output stream/table; custom tables require matching schema declarations.
4. Transformations apply to **new data passing through the pipeline**, never modifying previously ingested records.
5. Never strip fields required for incident investigations or audit obligations.
6. Transformations may carry specific pricing or capability rules depending on tier and table plan.
7. Before rolling out, test which events are dropped and verify downstream alert impact.

**Filter as early as possible when backed by solid evidence**, but never drop security/compliance data purely to cut bills without approval.

## 21. DCR Transformations and Privacy

Some application logs accidentally capture:

```text
2026-11-20T12:00:00Z INFO Login succeeded user=user@example.test
2026-11-20T12:01:00Z ERROR Payment failed card=4111-.... token=<redacted>
```

The best approach is **never logging secrets or PII at the source**. If an application already has a logging bug, ingestion transformations can help drop or mask fields where supported, though they are not a standalone security control.

### Why Transforms Alone Are Insufficient

- Raw data already exists in VM/app log files.
- The agent still reads and transmits messages toward the pipeline.
- New fields or changed message formats can bypass regex patterns.
- A buggy transformation can erase forensic evidence.
- Some log paths may bypass the DCR you expected.
- Data may have already been forwarded to other services before transformation.

Control **source logging, data classification, RBAC, networking, retention, and auditing** together. Never rely on a single `replace_regex` to claim compliance.

## 22. Custom Log Files: Different from Built-In Streams

For applications writing custom text or JSON files on a VM, AMA provides DCR-based **custom text/JSON log collection** where supported.

Mental model:

```text
Application writes file
  /var/log/myapp/events.log
        |
        v
AMA custom log file source
        |
        +-- file path patterns
        +-- record boundaries / timestamp format
        +-- stream schema
        |
        v
DCR transformation
        |
        v
Log Analytics custom table
        |
        v
KQL query
```

### Custom Logs Checklist

1. Does AMA have read permissions on the file and directory?
2. Do file path patterns match exact locations and case sensitivity?
3. How do files rotate? Does the agent keep tailing new files properly?
4. How does each record start (timestamp/delimiter format)?
5. Do multiline stack traces require record stitching where supported?
6. Have the custom table and schema been created cleanly in the pipeline?
7. Where is `TimeGenerated` parsed from, and is it converted to UTC properly?
8. Do transformation output fields and types match the table schema?
9. Does the file contain PII/secrets that must be removed at the source?
10. Are log volume limits, budgets, and retention configured?
11. Is the DCR associated with the right VM?
12. Test on a single VM before rolling out to hundreds of machines.

**Do not assume every binary log or arbitrary format can be read directly by AMA.** Containers writing to stdout or apps sending HTTP telemetry may need different pipelines.

## 23. Custom Tables, Logs Ingestion API, and Key Differences

Two workflows are easily confused:

**A. AMA custom file collection**

```text
VM file → AMA → DCR file source → transformation → workspace table
```

**B. Logs Ingestion API**

```text
Application/client → authenticated HTTP ingestion endpoint
                   → DCR/stream mapping → workspace table
```

Both can leverage **DCR concepts**, yet:

- **AMA** requires the agent and a DCR association on the machine.
- **Logs Ingestion API** pushes data directly over HTTP, requiring its own endpoint, authorization, and schema, without requiring AMA.
- Some APIs and deployment models require a DCE; newer setups may expose an ingestion endpoint directly via the DCR.
- Permissions to create DCRs, call the Logs Ingestion API, and query the workspace can be separate.

**Do not assume installing AMA is mandatory for every custom table**, and do not assume the Logs Ingestion API reads files off a VM by itself.

## 24. DCR and Azure Policy for Rolling Out Across Hundreds of Machines

An organization with 500 Azure VMs should never configure each host by hand. Azure Policy can help:

- Audit machines missing the AMA extension.
- Deploy the required extension via appropriate policies.
- Create DCR associations for machines by scope, tags, or OS.
- Track compliance.
- Execute remediation tasks using appropriately scoped managed identities/roles.
- Maintain baseline configuration automatically as new VMs are provisioned.

```text
Management group / subscription
       |
       v
Azure Policy assignment
       |
       +-- Identify matching machines
       +-- Deploy AMA extension if required
       +-- Associate correct DCR
       |
       v
Compliance + remediation + monitoring
```

### Crucial Conditions

- Policy definitions/initiatives must match the exact resource type and OS.
- Scopes, exclusions, and tags must never mix lab and Production.
- The policy identity must hold permissions to deploy extensions and associations.
- The guest machine/Arc resource's managed identity must satisfy agent requirements.
- A `Compliant` status does not substitute for verifying **actual data reaching the workspace**.
- Policy remediation can lag or fail; audit execution results.
- Another policy could create overlapping associations and duplicate streams.

**IaC/Azure Policy manages desired state; KQL and telemetry confirm real collection.**

## 25. Naming, Tags, and Ownership

A clean naming convention:

```text
dcr-win-prod-baseline
dcr-linux-prod-security
dcr-win-staging-perf
law-platform-prod
dce-monitor-private-prod
```

Recommended tags:

- `environment`, `owner`, `costCenter`.
- `dataClassification` and `retentionPolicy`.
- `ruleVersion` or IaC commit hash.
- `ticketId` or change request.
- `sourceOS` and workload group.

**Never place usernames, access tokens, service passwords, or PII in tags.** Tags and resource names are visible in inventories and audits with broader access than log contents.

### Ownership

Define team boundaries clearly:

- Platform team owns base AMA extensions and networking.
- Observability team owns baseline DCRs and Log Analytics schemas.
- Application team owns custom log formats.
- Security team approves Security logs, PII controls, and retention.
- Finance/FinOps tracks ingestion volume and cost anomalies.

## 26. Deploying via Azure Portal: Lab Workflow

In an approved subscription:

1. Create or select a lab **Log Analytics workspace**.
2. Pick a lab **Windows/Linux Azure VM** generating events.
3. Verify OS support and install the AMA extension if absent.
4. Navigate to **Azure Monitor → Data Collection Rules**.
5. Create a DCR targeting the appropriate Windows or Linux platform.
6. Select a small data source (Windows Application errors or Linux daemon Syslog).
7. Choose the environment-appropriate workspace destination.
8. Link the machine via DCR association in the wizard/workflow.
9. If private networking requires DCE/AMPLS, configure and verify DNS/network per documentation.
10. Inspect Azure resource status, AMA extension provisioning, and associations.
11. Wait a reasonable ingestion window; do not treat the first few seconds without logs as a guaranteed failure.
12. Query the right workspace and table with KQL to verify arrival.
13. Record data volume and set early alerts if volume exceeds expectations.
14. Review permissions, retention, and PII compliance.
15. Expand the rule only after the canary passes.

**Never alter Production data or configs just to generate a "test event."** Use lab VMs and approved event types.

## 27. Azure CLI: Inspecting DCRs, Workspaces, and AMA Extensions

The commands below **only read metadata** in the authenticated session; they do not create or modify resources.

```bash
RG="rg-observability-lab"
VM="vm-win-lab"
DCR="dcr-win-lab"
LAW="law-lab"

az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table

az monitor data-collection rule list \
  --resource-group "$RG" \
  --output table

az monitor data-collection rule show \
  --resource-group "$RG" \
  --name "$DCR" \
  --query "{location:location,properties:properties}" \
  --output json

az vm extension list \
  --resource-group "$RG" \
  --vm-name "$VM" \
  --output table

az monitor log-analytics workspace show \
  --resource-group "$RG" \
  --workspace-name "$LAW" \
  --query "{Name:name,Location:location,Id:id}" \
  --output json
```

Subcommands and flags require an **Azure CLI / Azure Monitor extension** version supported in your environment. If a command is missing, inspect CLI help/capabilities approved by your organization; never run unvetted installation scripts on Production hosts.

### Checking DCRAs

DCR associations are **child resources attached to the monitored VM/Arc resource**, not an array inside the DCR's `properties.dataSources`. Inspect them via the Portal or association CLI/API commands supported by your CLI version, using the exact **VM resource ID**.

**Never conclude a DCR has no consumers simply because the DCR listing does not print VM names.** Always inspect associations.

## 28. IaC Concepts for DCRs and DCRAs

IaC dependency graph:

```text
Resource group
   |
   +-- Log Analytics workspace
   |
   +-- Data Collection Rule
   |      +-- dataSources
   |      +-- destinations
   |      +-- dataFlows
   |
   +-- VM extension AMA (on target VM)
   |
   +-- Data Collection Rule Association (on VM resource)
   |
   +-- optional DCE/AMPLS networking
```

DCRs and DCRAs should be declared via **ARM/Bicep/Terraform** or approved policy. IaC should enforce:

1. Exact resource IDs for the target subscription and resource group.
2. Supported regions and constraints.
3. Scoped managed identities and role assignments.
4. Matching source OS, streams, and schemas.
5. Exact DCRA parent resource IDs.
6. Proper dependency ordering or readiness checks.
7. Zero workspace keys or secrets in repositories.
8. Plan/diff previews and code reviews.
9. Rollback procedures and drift policies.
10. Post-deployment KQL smoke tests.

**Deployment success does not prove data ingestion success**; IaC only applies desired configuration.

## 29. KQL to Verify Heartbeat

In AMA environments with supported Heartbeat data, run:

```kusto
Heartbeat
| where TimeGenerated > ago(1h)
| summarize LastHeartbeat=max(TimeGenerated) by Computer, OSType
| order by LastHeartbeat desc
```

### Reading the Results

- `Computer`: machine sending heartbeats per ingested records.
- `LastHeartbeat`: latest `TimeGenerated` received by the workspace.
- `OSType`: OS label when populated.

**Heartbeat does not prove every DCR stream is working.** A VM can send Heartbeat yet emit zero `Event` rows if the XPath filter matches nothing or the DCRA/data source is misconfigured.

### Avoid False Alarms

A lab VM may be deallocated or newly created and therefore have no Heartbeat yet. A 1-hour query window may be too short or too long depending on the workload. For absence alerts, maintain an **expected-alive inventory** independent of Heartbeat itself; querying only machines present in `Heartbeat` causes vanished machines to drop out of results instead of showing `count=0`.

## 30. KQL to Verify Windows Events

```kusto
Event
| where TimeGenerated > ago(2h)
| project TimeGenerated, Computer, EventLog, EventID,
          EventLevel, Source, RenderedDescription
| order by TimeGenerated desc
| take 50
```

For aggregation:

```kusto
Event
| where TimeGenerated > ago(24h)
| summarize EventCount=count() by Computer, EventLog, EventLevel
| order by EventCount desc
```

**An empty table has multiple possible explanations**:

- No events matched the XPath filter during that window.
- DCRA is not attached to the VM.
- AMA extension is unhealthy.
- Data flow or destination is misconfigured.
- Wrong workspace or query time range.
- Ingestion is delayed.
- Logs are routed to a different workspace.
- Different table/columns if using a non-AMA pipeline.

Never turn on all Security Events permanently just to "make the table show data."

## 31. KQL to Verify Linux Syslog

```kusto
Syslog
| where TimeGenerated > ago(2h)
| project TimeGenerated, Computer, Facility,
          SeverityLevel, ProcessName, SyslogMessage
| order by TimeGenerated desc
| take 50
```

Group by facility and severity:

```kusto
Syslog
| where TimeGenerated > ago(24h)
| summarize Events=count() by Computer, Facility, SeverityLevel
| order by Events desc
```

If Syslog is missing:

1. Is the VM running Linux with a compatible AMA?
2. Is the syslog daemon generating/forwarding messages?
3. Does `facilityNames` include the facility used by the log source?
4. Is `logLevels` filtering out the severity under test?
5. Does the DCR data flow map `Microsoft-Syslog` properly?
6. Is the DCRA attached to the machine's resource ID?
7. Are there connectivity, identity, or network failures?
8. Are you querying the right workspace and `TimeGenerated` range?

## 32. KQL to Verify Performance Counters

```kusto
Perf
| where TimeGenerated > ago(4h)
| where CounterName == "% Processor Time"
| summarize AvgCpuPct=avg(CounterValue)
    by Computer, bin(TimeGenerated, 5m)
| order by TimeGenerated desc
```

To inspect which counters are actually being ingested:

```kusto
Perf
| where TimeGenerated > ago(2h)
| summarize Samples=count() by ObjectName, CounterName,
          InstanceName, Computer
| order by Samples desc
```

The columns and queries above apply to the `Perf` table per its schema. If the DCR routes performance metrics to another stream or destination, query where the data lands.

### CPU Interpretation Pitfalls

- `% Processor Time` may have `_Total` or per-core instances depending on the source.
- Windows and Linux counters are not 1:1 equivalents.
- VM CPU in Azure Monitor platform metrics can differ from guest OS measurements because they measure at different layers.
- Check `CounterValue` units and instance names before setting alert thresholds.
- A 5-minute average can hide a 10-second spike.

## 33. Ingestion Latency and TimeGenerated

An event occurring at `10:00` may appear in Log Analytics at `10:03` due to:

- Agent batching and buffering.
- Configuration sync delay or network latency.
- Data collection pipeline queuing.
- Source timestamps not aligned with UTC/timezones.
- Workload overload or backpressure.

Distinguish clearly:

- **Event time / TimeGenerated**: when the event was recorded per source schema/logic.
- **Ingestion time**: when the platform received and stored it in the workspace.
- **Query time**: when the operator runs the query.

Example KQL to measure ingestion lag:

```kusto
Event
| where TimeGenerated > ago(2h)
| extend IngestionLagSeconds =
    datetime_diff('second', ingestion_time(), TimeGenerated)
| summarize P95LagSeconds=percentile(IngestionLagSeconds, 95)
    by Computer
```

**Caution:** `datetime_diff` subtracts arguments in order; verify signs and real timestamp behavior. Records with clock skew can produce negative or anomalous lag and require special handling. Do not assume `ingestion_time()` is populated identically across every table, pipeline, and query.

### A Simpler Alternative

To avoid sign confusion, use:

```kusto
Event
| where TimeGenerated > ago(2h)
| extend Lag = ingestion_time() - TimeGenerated
| summarize P95Lag = percentile(Lag, 95) by Computer
```

When building latency alerts, verify `timespan` handling and query/alert engine support.

## 34. Optimizing Cost via Collection Scope

Factors driving volume:

1. How many VMs/agents are collecting?
2. How many DCR associations does each VM have?
3. How broad are Windows channels and XPath filters?
4. Which Syslog facilities and levels are retained?
5. Is Perf sampling every 10, 60, or 300 seconds?
6. How fast do custom log files grow per day?
7. Are DCR transformations filtering/trimming records?
8. Are legacy collectors/agents duplicating ingestion?
9. What are the Log Analytics table plans and retention periods?
10. Are logs ingested into multiple workspaces?
11. Which tables and queries are actually used by alerts?
12. Did Debug log spikes occur after a deployment?

### Design Principles

- **Measure volume first**: inspect 24–72 hours of representative data if permitted.
- **Filter with purpose**: keep events needed for SLOs, security, and forensics.
- **Pick sensible frequencies**: 10-second CPU sampling is not always necessary.
- **Avoid double collection**: audit overlapping DCRs and legacy agents.
- **Tailor retention by purpose**: do not give every table the same retention.
- **Minimize sensitive data**: keep secrets and PII out at the source.
- **Balance cost against investigation capability**: cheap but blind telemetry leads to costlier incidents.

**Never cut costs by dropping mandatory security logs without Security/Compliance approval.**

## 35. Sizing Volume and Cost

Illustrative estimation model:

- 50 Windows VMs.
- Each VM produces 200 MB/day of candidate logs before filtering.
- DCR filtering retains 25% based on workload benchmarks.
- Assume zero duplication and negligible overhead.

```text
Raw candidate volume = 50 × 200 MB = 10,000 MB/day
Filtered estimate    = 10,000 × 25% = 2,500 MB/day
                     ≈ 2.5 GB/day (decimal units)

Monthly estimate for 30 days ≈ 75 GB
```

**This is an illustrative exercise, not an accurate billing quote.** Actual billed volume depends on tables, ingestion formats, transformations, workspace plans, free/billable columns, regions, and current pricing meters.

### Cost Review Table

| Line Item | Billing Dimension to Check |
|---|---|
| Log Analytics ingestion | Ingested data / billing plan per table and workspace. |
| Retention | Retention duration and archive/restore options per plan. |
| Transformations | Supported capability and processing charges where applicable. |
| Azure Monitor Agent | Check service pricing; destination data volume is typically the main driver. |
| Azure Monitor Alerts / queries | Alert rule evaluations and related charges by type. |
| Networking / Private Link | DCE/AMPLS/networking/egress where applicable. |
| Diagnostics | Log volume and Log Analytics workspace consumption. |

Never assume "AMA is free, so collecting unlimited logs is free."

## 36. Retention and Table Plans

Log Analytics workspaces and tables support retention settings and **table plans** (such as plans matching Analytics, Basic, and Auxiliary capabilities) with differing query, alert, ingestion, and retention behavior.

Decide:

- Which event/security logs need fast interactive lookups?
- Which custom application debug logs are only checked occasionally?
- Do logs require incident correlation and KQL joins?
- Are 90-day or 1-year audit retention policies mandated?
- Are archive/restore/search jobs supported?
- Do data residency or legal holds apply?
- Do analytics/AI jobs need to read historical data?

**Never choose Basic or Auxiliary plans solely for the lower per-GB price** without checking query/alert limitations and incident detection needs. Conversely, never leave every table at maximum retention out of habit.

## 37. RBAC: Who Can Create DCRs vs. Who Can Read Logs?

Two permission layers:

| Layer | Example Actions | Permissions to Review |
|---|---|---|
| **Control plane DCR** | Create/edit/delete Data Collection Rules. | Role/resource scope on `Microsoft.Insights/dataCollectionRules`. |
| **Control plane association** | Attach DCRA to VM/Arc resource. | Permissions on the monitored resource and DCRA type. |
| **Agent extension** | Install/update VM extensions. | VM extension permissions; Azure Policy managed identity if automated. |
| **Workspace management** | Create/edit workspaces and retention. | Azure resource/workspace management roles. |
| **Log query / data access** | Read Event/Syslog/Perf tables. | Log Analytics data access/RBAC and resource-context vs. workspace-context design. |
| **Private networking** | Manage DCE/AMPLS/Private Endpoints. | Network/resource permissions. |
| **Security incidents** | Query sensitive logs and audits. | Least privilege and periodic access reviews. |

**Never grant subscription-wide Owner/Contributor to an app or user just to read logs.** Permissions to deploy/modify DCRs are separate from permissions to view ingested data.

### Least Privilege

- Agents and data flows use service-designed authentication; avoid distributing workspace shared keys manually to servers when unnecessary.
- IaC identities need permissions only on the target resources and scopes.
- Security Event logs should have stricter access policies than application metrics.
- Secrets/PII in logs are a source bug; RBAC only limits blast radius.

## 38. Networking, Private Link, and DCE

An agent cannot ingest data if the network or identity path is blocked.

```text
VM AMA / Arc machine
     |
     +-- configuration/control path
     |
     +-- data ingestion path
     |
     v
Azure Monitor service endpoints
     |
     v
Log Analytics workspace

Private scenario:
  VNet/Private Endpoint/Private DNS
  + Azure Monitor Private Link Scope (AMPLS)
  + DCE association/config where required
```

Checklist:

1. Does the Azure VM or Arc machine have a valid outbound route?
2. Does DNS resolve service hostnames properly from the **actual host**?
3. Are NSGs, UDRs, Azure Firewall, or proxies blocking traffic?
4. Is TLS trust or inspection breaking connections?
5. Are the Private Link Scope, Private Endpoint, and DCE in the right region and properly configured?
6. Are the DCR and agent supported under the chosen private networking model?
7. Is the workspace linked to the right AMPLS and network access mode?
8. Are Arc connectivity prerequisites satisfied?
9. Are logs leaking to another workspace or over public paths unexpectedly?
10. Do alerts fire if ingestion fails after firewall or DNS changes?

**A Private Endpoint does not automatically create a DCR association or fix bad XPath**, just as installing AMA does not open firewalls.

## 39. Security, Compliance, and Sensitive Data

Guest logs can contain:

- Usernames, email addresses, IP addresses.
- File paths, machine hostnames, and internal app details.
- Accidentally logged tokens, session IDs, or connection strings.
- Payment details and access histories.
- Audit events carrying employee identities.
- Stack traces with URLs containing sensitive query strings.

Defense-in-depth layers:

1. **Source logging policy**: never log unnecessary secrets or PII.
2. **DCR source selection**: drop out-of-scope data early.
3. **Transformations**: where needed and supported, though never as the sole defense.
4. **Network encryption** and private networking per policy.
5. **Workspace access control** and query auditing.
6. **Retention and deletion** aligned with data classification.
7. **Log ingestion validation** against spoofed formats or identities.
8. **SIEM/incident response** for anomalous access.
9. **Separate workspaces/tables** when trust boundaries must be split.
10. **Export/backup policies** preventing sensitive data copies into weaker stores.

**Never pass credentials into `logger` commands or Windows Event Logs to test AMA.** Use synthetic strings containing zero secrets.

## 40. Runbook: AMA Installed, Yet Log Analytics Is Empty

**Symptom:** extension provisioning succeeded, yet querying `Event` or `Syslog` returns zero records.

### Ordered Investigation

1. Confirm you are querying the **right workspace** and time range.
2. Is the VM or Arc machine actually online?
3. Is the AMA extension healthy, running, and compatible with the OS?
4. Does the DCR exist with valid JSON and OS-matching stream sources?
5. **Is the DCRA attached to the exact VM resource ID?**
6. Do XPath, facility, and level filters match real events?
7. Do the DCR destination and data flow map to the right workspace?
8. Are required DCE/AMPLS/private networking components missing?
9. Are there identity or agent configuration errors?
10. Is ingestion lagging or configuration sync still propagating?
11. Is a transformation filtering out all events?
12. For custom logs, is there a custom table or schema mismatch?
13. Is another collector/route landing data in a different table?
14. Can you emit **one safe lab event** to verify the path end-to-end?

### What Not to Do

- Never leave all Security Event logs open indefinitely just to see rows appear.
- Never delete and recreate a Production workspace as a first debugging step.
- Never grant subscription Owner to fix a 403 error.
- Never flip all network rules at once, making root cause impossible to isolate.

## 41. Runbook: Windows Events Arrive, Yet `Perf` Is Empty

**Symptom:** `Event` has records for the VM, while `Perf` is empty.

Analysis steps:

1. AMA and part of the DCR are working (Windows Events are arriving).
2. Is `performanceCounters` declared in the DCR?
3. Does `streams` include `Microsoft-Perf` and map to Log Analytics in `dataFlows`?
4. Are counter specifiers spelled accurately for the OS and locale?
5. Is the sampling interval valid under service constraints?
6. Is `transformKql` dropping all Performance events?
7. Are Perf records routed to another stream or destination?
8. Does the `Perf` query use the right time range and `Computer` filter?
9. Did the VM just restart or change instance names before samples arrived?
10. Check IAM/networking—though unlikely if `Event` uses the same path and arrives.

**Lesson:** a healthy agent does not prove **every data source in a rule** is healthy.

## 42. Runbook: Sudden Syslog Volume Spike

**Symptom:** billing/ingestion triples after rolling out a Linux DCR.

Investigation:

1. Does the new DCR specify `facilityNames=["*"]` or broad Debug/Info `logLevels`?
2. Are multiple DCRs collecting the same facility/stream into the workspace?
3. Are AMA and a legacy collector running side by side?
4. Did an application recently enable verbose logging?
5. Is a daemon stuck in a log loop or retry storm?
6. Did machine counts, tags, or Policy remediations change?
7. In KQL `Syslog`, group by `Computer`, `Facility`, and `ProcessName` to pinpoint the top producer.
8. Is a custom table ingesting duplicates outside `Syslog`?
9. Did an ingestion-time transform fail or get disabled?
10. Is a real security incident causing the volume spike?

### Remediation

- First evaluate the **security relevance** of the volume surge.
- Narrow facilities/severities and establish application logging policies with owners.
- Remove duplicate DCR associations and legacy routes.
- Preserve mandatory audit logs.
- Create cost anomaly alerts and per-source dashboards.
- Test changes on a canary VM before scaling out.

Never "cut costs" by silencing signals of an active incident.

## 43. Runbook: Custom Logs Not Reaching the Target Table

**Symptom:** `/var/log/myapp/events.log` keeps growing, yet `MyApp_CL` has zero records.

Investigation:

1. Does AMA have permission to read the directory and file?
2. Is the DCR custom log data source watching the exact path pattern?
3. Do file format, record boundaries, and timestamps match supported capabilities?
4. Does log rotation (rename/truncate) cause the agent to lose its read offset?
5. Do stream declarations match the input fields?
6. Does the destination table/schema exist and match the output stream?
7. Is `transformKql` dropping rows or throwing conversion errors?
8. Is the DCR associated with the right VM/Arc resource?
9. Is the destination workspace in a valid region/name with working connectivity?
10. Are log lines exceeding length or ingestion limits?
11. Are you querying the right table, workspace, and time range?
12. Are there agent diagnostics or errors regarding file ingestion?

Fix the exact **break in the pipeline** rather than creating another differently named table "just to see if logs show up."

## 44. Lab Exercise: Collecting Windows Events, Linux Syslog, and Perf

**Lab context:** one Windows VM, one Linux VM, and one Log Analytics workspace. Neither machine processes real data; you are authorized to install AMA and create DCRs/DCRAs in the lab Azure subscription.

### Expected Architecture

```text
vm-win-lab ── AMA ── dcr-win-lab ──┐
                                  |
                                  v
                            law-ops-lab
                                  ^
                                  |
vm-linux-lab ─ AMA ─ dcr-linux-lab┘
                                  |
                           KQL + Workbook
```

### Tasks

1. Document VM IDs, OS versions, owners, and workspace region.
2. Choose a security-approved Windows Application event filter.
3. Select Windows CPU and memory counters at 60-second sampling for the lab.
4. Select Linux Syslog facilities `daemon` and `authpriv` compatible with the distro.
5. Create the Windows DCR with data sources, streams, destination, and data flows.
6. Create the Linux DCR with Syslog source and the same workspace destination.
7. Install or verify AMA extensions on both machines.
8. Create a DCRA linking the Windows VM to the Windows DCR.
9. Create a DCRA linking the Linux VM to the Linux DCR.
10. Verify Azure resource states, OS support, DCE requirements, and networking.
11. Emit a few **non-sensitive** lab events if no natural events exist yet.
12. Query `Heartbeat` to check `lastSeen` for both hosts.
13. Query `Event` by `Computer` and `EventLog`.
14. Query `Syslog` by `Facility` and `SeverityLevel`.
15. Query `Perf` by `Computer` and `CounterName`.
16. Measure the elapsed time from event creation to visibility in the workspace.
17. Test a modified DCR filter on a canary and observe the volume change.
18. Add a simple `transformKql` in the lab where supported; verify essential records are not dropped.
19. Temporarily remove one lab machine's association to observe controlled impact; restore it immediately.
20. Test querying the right workspace with the wrong time range to practice troubleshooting.
21. Simulate a Syslog facility mismatch and correct the selection.
22. Document the RBAC permissions needed to create DCRs, install extensions, and query the workspace.
23. Estimate MB/day and monthly billing based on measured table volume.
24. Create at least one meaningful lab alert (e.g., error count).
25. Clean up lab DCRs, DCRAs, and VMs per authorization without deleting shared workspaces or resources.

### Acceptance Evidence

| Criterion | PASS When |
|---|---|
| AMA installed | Both machines show healthy extension/agent status. |
| DCRA association | Windows/Linux VMs link to OS-matching DCRs. |
| DCR streams | WindowsEvent, Syslog, and Perf route to the right destination. |
| Workspace data | Tables contain matching records for the test window. |
| KQL | Queries return expected Computer, source, and metric fields. |
| Alert | Thresholds and logic avoid excessive false positives. |
| Security | Zero test secrets or PII appear in logs. |
| Cost | Report includes volume, retained data, and cost estimate. |
| Cleanup | No impact on Production machines or workspaces. |

## 45. Exercise: Designing DCRs for 100 Virtual Machines

**Prompt:** 60 Windows VMs and 40 Linux VMs across dev, staging, and prod. Security needs audit events; SRE needs CPU, memory, and process errors; FinOps sets an ingestion budget.

### Reference Design

| Group | DCR | Association Scope | Destination |
|---|---|---|---|
| Windows Production | `dcr-win-prod-core` | Prod Windows machines via Azure Policy. | `law-prod-ops`. |
| Linux Production | `dcr-linux-prod-core` | Prod Linux machines via Azure Policy. | `law-prod-ops`. |
| Security signals | Separately approved rule/stream. | Machines within security scope. | Workspace with policy-compliant RBAC and retention. |
| Dev/Staging | `dcr-nonprod-lite` split by OS as needed. | Dev/staging machines. | `law-nonprod`. |

### Questions to Answer

1. How do you prevent collecting the same Windows Events twice if the core and security DCRs overlap?
2. Why shouldn't dev/staging automatically share prod's retention period?
3. How does Azure Policy distinguish Windows vs. Linux so it never attaches the wrong DCR?
4. What check reveals when Policy reports `Compliant` yet VMs still send zero data?
5. Who holds permission to modify security audit filters?
6. How do you detect a billing spike after an app enables DEBUG logging?
7. With Private Link in place, which components must be verified?
8. What is the rollback plan for a faulty new DCR version?
9. How do you ensure newly provisioned VMs are automatically monitored?
10. How do you alert on a VM losing heartbeat without ignoring hosts that vanish from query results?

**Guiding answer:** split rules by owner, OS, and environment; avoid overlapping filters; use Azure Policy to attach AMA/DCRs; verify end-to-end with KQL and application metrics; require Security approval for mandatory audit logs; control costs per workspace/table; and verify network/identity paths.

## 46. Production Checklist

**Signal Design**

- [ ] Clear use cases defined for WindowsEvent/Syslog/Perf/custom logs.
- [ ] Appropriate fields, sampling frequencies, severities, and data classifications chosen.
- [ ] Azure Activity Log is not confused with VM guest logs.
- [ ] SLOs defined for ingestion latency and alert freshness.
- [ ] No duplicate collection between AMA and legacy agents or overlapping DCRs.
- [ ] Unnecessary secrets and PII excluded at the source.

**Agent and DCR**

- [ ] AMA extensions match OS/version and report healthy.
- [ ] DCR `dataSources`, `streams`, `dataFlows`, and `destinations` are intentionally scoped.
- [ ] DCRAs attach exact resource IDs with no missed VMs or Arc servers.
- [ ] DCE/AMPLS applied only where actually required by architecture.
- [ ] KQL transformations, schemas, and custom tables tested.
- [ ] Azure Policy/IaC and safe drift remediation in place.
- [ ] DCR changes require PRs, owners, canary testing, and rollback plans.
- [ ] Deploy succeeded is never equated with ingestion succeeded.

**Security and Networking**

- [ ] RBAC for deploying DCRs/agents is separated from workspace query access.
- [ ] Workspace data access and retention align with classification.
- [ ] VM/Arc/agent identities and network requirements verified.
- [ ] TLS, DNS, NSGs, firewalls, and Private Link tested from real machines.
- [ ] No tokens or workspace keys stored in YAML, repos, or logs.
- [ ] Access auditing, permission change tracking, and incident runbooks exist.
- [ ] Data residency and legal retention confirmed.

**Observability and Cost**

- [ ] Smoke tests verify `Heartbeat` and source tables.
- [ ] Alerts exist for missing agents, ingestion lag, and volume spikes.
- [ ] KQL dashboards break down data by Computer, Facility, and CounterName.
- [ ] Ingestion volume, retention/table plans, and billing actively monitored.
- [ ] Alerts catch duplicate collection and Debug log growth.
- [ ] Runbooks ready for empty tables, missing Perf, Syslog spikes, and custom logs.
- [ ] Operational owner and budget assigned for Log Analytics.

## 47. Self-Check Questions

**Q1.** How do Azure Monitor Agent and a Data Collection Rule differ?

**Answer:** AMA is the collection component running on supported sources; a DCR is the configuration defining sources, transformations, and destinations.

**Q2.** If a DCR is created without associating it to a VM, will the VM automatically apply the rule?

**Answer:** No. You need a DCRA/association or appropriate source binding, plus an installed and running agent.

**Q3.** Is a DCRA a workspace or a log storage endpoint?

**Answer:** No. A DCRA is the link between a source resource and a DCR.

**Q4.** Is a DCE always mandatory for every AMA DCR?

**Answer:** No. It is used in specific scenarios that require it, such as certain private-link, configuration, or ingestion architectures.

**Q5.** Which table is normally queried for Windows Event Log data collected by AMA?

**Answer:** `Event`, when the data flow routes AMA's standard stream into Log Analytics.

**Q6.** Which table typically receives Linux Syslog?

**Answer:** `Syslog`.

**Q7.** Which table typically receives Windows performance counters via `Microsoft-Perf`?

**Answer:** `Perf`, when routed to Log Analytics via the matching data flow.

**Q8.** Does installing AMA automatically send the Azure subscription Activity Log to the workspace?

**Answer:** No. Activity Log export uses a separate mechanism such as diagnostic settings.

**Q9.** Does a VM having a `Heartbeat` mean all logs and `Perf` are being collected?

**Answer:** No. `Heartbeat` only verifies the agent/host signal; each stream and source must be verified independently.

**Q10.** Is XPath for Windows Events the same as KQL?

**Answer:** No. XPath filters events at the Windows Event Log source; KQL queries ingested data.

**Q11.** Does a DCR transformation retroactively modify events already stored in the workspace from last week?

**Answer:** No. Ingestion-time transformations apply only to new data passing through the pipeline.

**Q12.** Can you use every KQL function when writing `transformKql`?

**Answer:** No. Transformations use a supported subset/contract and must match input and output schemas.

**Q13.** Will a Syslog DCR selecting only `daemon` collect `authpriv`?

**Answer:** No, unless that facility is selected by the rule or another collection source.

**Q14.** Why shouldn't DEBUG logs be collected from every VM by default?

**Answer:** They can cause excessive volume, cost, noise, and data exposure risk; they require a clear use case and approval.

**Q15.** Is AMA required to send data directly via the Logs Ingestion API?

**Answer:** Not necessarily; they are two distinct pipelines even though both can use DCRs.

**Q16.** If a custom log file is not reaching its table, what must you check?

**Answer:** File permissions/path/format, AMA, DCR/DCRA, stream declarations, table schema/transform, networking, and query scope.

**Q17.** If Azure Policy reports `Compliant`, is the workspace guaranteed to have `Event` records?

**Answer:** No. You must query the data and verify source, agent, and ingestion end-to-end.

**Q18.** What is the risk of attaching multiple DCRs to one VM?

**Answer:** Overlapping streams/sources/destinations can double-collect data, inflating volume, cost, and duplicates.

**Q19.** Why can `Perf` be empty even when `Event` has data?

**Answer:** `performanceCounters` or its `dataFlow` may be missing, or counter specifiers, streams, transformations, or query time ranges may be wrong.

**Q20.** Can a DCR store log data inside itself?

**Answer:** No. A DCR describes collection and routing; destinations such as a workspace store the data.

**Q21.** How does `TimeGenerated` differ from `ingestion_time()`?

**Answer:** One represents the log event timestamp per schema, while the other records when the data was ingested (where supported).

**Q22.** Does a role managing DCRs automatically grant read access to all Log Analytics workspace tables?

**Answer:** No. Control-plane management and log data access are separate permission layers.

**Q23.** Can a Private Endpoint replace a DCRA?

**Answer:** No. Private networking handles connectivity, while a DCRA handles rule association.

**Q24.** When the AMA Linux agent hits a network error, what is the first step?

**Answer:** Check VM/agent status, DNS/TLS/proxy/firewall/routes, and DCE/AMPLS if used; never tweak source filters to mask a network failure.

**Q25.** Why is a retention policy necessary?

**Answer:** To manage cost, legal obligations, privacy, and historical query/investigation readiness.

**Q26.** Does an ingestion-time filter replace avoiding logging secrets in applications?

**Answer:** No. Sensitive data already sits on the source host and may flow through other pipelines.

**Q27.** Why can 10-second performance counter sampling cost much more than 60-second sampling?

**Answer:** It multiplies the number of measurements, records, and ingested volume over the same duration.

**Q28.** Can Azure Monitor Logs be treated as an unlimited, free raw telemetry store?

**Answer:** No. Billing rules, retention/table plans, quotas, and service costs apply.

**Q29.** What is the best way to confirm a successful AMA/DCR rollout?

**Answer:** Verify **extension health + DCRA + DCR contents + connectivity + real KQL data + alerts/volume** together.

**Q30.** What is the core principle of this lesson?

**Answer:** **Collect the right data via AMA, configure via DCR, bind accurately with DCRA, choose destinations/frequencies/transforms intentionally, verify with KQL, and govern permissions, networking, retention, and cost.**

## 48. Summary and Practical Direction

In an Azure environment with many Windows and Linux VMs, **Azure Monitor Agent** provides the host-level collection layer, **Data Collection Rules** define **data sources, streams, transforms, and destinations**, and **Data Collection Rule Associations** bind the right machines to each rule. A **Data Collection Endpoint** participates only when specific networking, configuration, or ingestion requirements call for it, rather than being mandatory for every DCR.

Keep your rollout order disciplined:

1. Define observability questions and SLOs.
2. Select sources while protecting sensitive data.
3. Provision workspaces and DCRs matching OS, streams, and tables.
4. Install AMA and bind DCRAs through governed configuration.
5. Verify networking, identities, and any DCE/private-link prerequisites.
6. Query real data with KQL for acceptance verification.
7. Monitor freshness, duplication, costs, and data governance.
8. Scale consistently with Azure Policy and IaC.
9. Maintain runbooks and rollback plans for missing data or cost spikes.

**A reliable observability system is not measured by how many gigabytes of logs it ingests, but by its ability to answer the right operational questions during an incident within agreed security, latency, and cost boundaries.**

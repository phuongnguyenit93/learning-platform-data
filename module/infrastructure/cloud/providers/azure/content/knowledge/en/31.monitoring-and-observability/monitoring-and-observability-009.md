# Metric Alerts, Log Alerts, and Action Groups

A Spring Boot app on Azure Container Apps still returns HTTP 200 on its home page while 15% of payment transactions fail. Meanwhile, an Azure Virtual Machine hovers near 95% CPU and a data pipeline stops writing new records for half an hour. Dashboards show these conditions, yet operators cannot stare at screens 24/7. Conversely, firing an email every time CPU spikes for a few seconds triggers **alert fatigue** and hides real outages.

In **Azure Monitor**, a **metric alert** watches numerical time series; a **log alert** evaluates a log query—typically as a **scheduled query rule**; and an **action group** determines who or what gets notified or invoked when an alert triggers. A solid design defines **reliable signals, scope, aggregation, thresholds, windows, evaluation frequency, missing-data handling, alert lifecycle, ownership, and safe actions**. This lesson teaches how to build the chain from observation to response, not just how to click buttons in the portal.

This lesson belongs to the **Monitoring and Observability** chapter of the **CLOUD_PROVIDERS_AZURE** module: exploring Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, then deploying, monitoring, securing, and controlling the cost of application architectures. Examples rely on Azure Monitor, Azure Metrics, Log Analytics, workspace-based Application Insights, and Azure Resource Manager (ARM).

> **Scope and versions:** Azure Monitor also offers Activity Log alerts, Prometheus rule groups, availability tests, and other signal types; this lesson focuses on metric alerts, scheduled-query log alerts, and action groups. Metric names, KQL tables, supported aggregations/dimensions, Azure CLI/Bicep schemas, limits, and billing vary by resource, region, configuration, and time. Commands are lab examples, not outputs from a live subscription. Never target real webhooks or emails outside authorized scope.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish metrics, logs, traces, Activity Log, and Azure Monitor events.
2. Choose between a metric alert and a log alert based on signals and SLOs.
3. Configure scope, signal, aggregation, thresholds, dimensions, window size, evaluation frequency, and severity.
4. Distinguish static vs. dynamic thresholds, stateful vs. stateless alerts, and Fired vs. Resolved states.
5. Write KQL to detect counts, error rates, missing heartbeats, and delayed data.
6. Understand log alerts based on **row count** vs. **numeric measure**.
7. Create an action group with receivers, the common alert schema, and delivery testing.
8. Distinguish an action group from an **alert processing rule** and suppression.
9. Build metric alert, log alert, and action group examples via Portal, CLI, and Bicep.
10. Design 401/403 controls and identity permissions for deployers and automation.
11. Reduce false positives, duplicate notifications, and cardinality explosions.
12. Calculate SLOs/error budgets, test end-to-end, and troubleshoot alert issues.
13. Track latency/availability, log ingestion, cost/retention, and notification reliability.
14. Establish runbooks, ownership, escalation, and rollbacks for production.

## 2. End-to-End Model: Data, Conditions, Actions

~~~mermaid
flowchart LR
  RES["VM / App / Storage / Database"] --> MET["Azure Monitor Metrics"]
  RES --> LOG["Resource logs / App Insights"]
  MET --> MA["Metric alert rule"]
  LOG --> LA["Log Analytics / KQL"]
  LA --> SQ["Scheduled query rule"]
  MA --> INST["Alert instance: Fired / Resolved"]
  SQ --> INST
  INST --> PROCESS["Alert processing rule"]
  PROCESS --> AG["Action group"]
  AG --> EMAIL["Email / SMS"]
  AG --> WORK["Webhook / Logic App / Function"]
  INST --> PORTAL["Alerts UI / incidents"]
~~~

**Four layers to keep distinct:**

- **Telemetry:** a VM emits CPU metrics; Spring Boot sends request/exception logs to a workspace.
- **Alert rule:** a configuration evaluated periodically by Azure Monitor against a telemetry source.
- **Alert instance:** an individual condition breach with its own lifecycle and metadata.
- **Action delivery:** action groups and alert processing rules govern notifications and automation.

**An action group does not generate telemetry or define thresholds.** A rule firing does not guarantee an email reached an inbox; receiver delivery must be tested separately. Likewise, an alert processing rule suppressing notifications does not mean the underlying condition is healthy.

## 3. Metrics, Logs, and Other Signals

| Signal | Data Shape | Strengths | Limitations |
|---|---|---|---|
| **Platform metrics** | Numeric time series with dimensions | Fast tracking of CPU, request counts, saturation | Lacks full business context |
| **Application/custom metrics** | Measurements emitted by the app | SLOs and business indicators | Depends on instrumentation |
| **Resource logs** | Timestamped records with fields | Detailed 4xx/5xx analysis and diagnostics | Ingestion delay, KQL, retention, and cost |
| **Application Insights** | Requests, dependencies, exceptions, traces | End-to-end application diagnostics | Sampling, instrumentation/ingest, schema |
| **Activity Log** | Subscription control-plane events | Who modified resources, roles, or policies | Does not replace application data-plane logs |
| **Prometheus metrics** | Prometheus series from AKS/containers | Kubernetes workloads | Separate rule groups and metric pipeline |

**Do not confuse Azure Monitor Logs with Azure Activity Log.** For "who deleted a resource group?", an Activity Log alert fits better than a scheduled KQL query. For "does the payment endpoint emit 5xx errors with a correlation ID?", Application Insights / Log Analytics gives the required detail.

## 4. When to Use a Metric Alert

Choose a **metric alert** when the Azure resource already exposes a suitable metric name and aggregation and you want fast threshold detection:

- Sustained high VM `Percentage CPU`.
- Queue backlog growing past a limit.
- Storage latency/availability on built-in metrics.
- HTTP requests / 5xx counts or duration metrics emitted by a resource.
- Disk free space / memory metrics when provided by an agent or custom metrics (not present out of the box on every VM).

### CPU Example

~~~text
Scope: vm-monitor-lab
Metric: Percentage CPU
Aggregation: Average
Operator: Greater than
Threshold: 80 (%)
Window size: 5 minutes
Evaluation frequency: 1 minute
Severity: Sev2
Action group: ag-platform-oncall-lab
~~~

The rule inspects metric data over a 5-minute window on schedule. **Average > 80** does not require every single minute to exceed 80, and **Greater than** differs from **Greater than or equal to**.

### Differences Between Aggregations

~~~text
CPU samples over five minutes: 65, 77, 82, 91, 95 (%)
Average = (65+77+82+91+95) / 5 = 82%
Maximum = 95%
Minimum = 65%
~~~

`Average > 80` reflects sustained load across the window. `Maximum > 80` fires on a single brief spike. For a **Requests** metric, check what `Total` counts over the window rather than taking an arbitrary `Average`.

## 5. Anatomy of a Metric Alert

| Field | Role | Common Mistake |
|---|---|---|
| `scopes` | Target Azure resource IDs being monitored | Picking the wrong workspace, VM, or region |
| `metricName` | Specific available metric | Name does not exist in that namespace |
| `metricNamespace` | Metric namespace | Confusing service vs. agent metrics |
| `timeAggregation` | `Average`, `Total`, `Maximum`, `Minimum`, `Count`, etc. | Incompatible with the metric's unit/meaning |
| `operator` | `GreaterThan`, `LessThan`, etc. | Wrong comparison direction |
| `threshold` | Trigger value | Chosen without checking baselines |
| `windowSize` | Aggregation window duration | Too short, causing flapping alerts |
| `evaluationFrequency` | Evaluation interval | Faster than collection cadence |
| `dimensions` | Filters/splits by region, instance, etc. | Too many time series |
| `severity` | `Sev0`–`Sev4` | Marking every alert `Sev0` |
| `enabled` | Enables/disables the rule | Forgetting to enable |
| `actions` | Action group references | Unconfigured receivers |

Additional dynamic criteria, `targetResourceType`/`targetResourceRegion`, `autoMitigate`, and API-version fields may apply. **Choose only aggregations supported by the metric source.** Use Metrics Explorer or metric definitions to verify exact units and dimension names.

## 6. Choosing Aggregations and Windows by Goal

| Goal | Metric | Reference Choice |
|---|---|---|
| CPU saturation | CPU % | Average over 5–15 minutes |
| Disk nearly full | Free space if available | Minimum over window |
| Queue backlog | Active messages | Maximum or Average |
| 5xx error count | Failed requests | Total |
| Unusual request surge | Request count | Total, compared against traffic baseline |
| Tail latency | p95/p99 metric if available | Never substitute Average for p95 |
| Availability | Probe success metric if available | Require multiple failed results |
| Freshness | Last success timestamp / custom metric | Needs dedicated no-data logic |

**What `windowSize` means:** the time span aggregated during each evaluation—not necessarily "the condition must stay true every single second." A rule with a 5-minute window and 1-minute frequency evaluates overlapping windows. Do not multiply evaluations by sample counts assuming they represent N disjoint points.

### Choosing Severity

- **Sev0:** emergency, widespread outage, immediate incident command.
- **Sev1:** major impact requiring immediate on-call response.
- **Sev2:** significant degradation with noticeable impact.
- **Sev3:** operational issue needing attention, not an emergency.
- **Sev4:** informational / review item.

This is an illustrative operational scale; real severities must reflect **incident policy and user impact**, not raw CPU thresholds alone.

## 7. Static Thresholds vs. Dynamic Thresholds

### Static Thresholds

~~~text
CPU Average > 80%
Queue active messages > 1,000
Disk free < 10 GiB
HTTP 5xx rate > 5% with minimum sample count
~~~

Well suited to concrete technical or budget limits. However, day-vs-night traffic swings can produce false positives.

### Dynamic Thresholds

For supported metrics and features, Azure Monitor learns historical baselines and alerts when behavior deviates from normal patterns. Settings can include **sensitivity**, violation direction, violation counts, and baseline learning windows.

Limitations:

- Requires sufficient clean history; brand-new alerts lack reliable baselines immediately.
- Seasonal events, holidays, and releases affect baselines.
- "Historically normal" does not guarantee the SLO is being met.
- Not supported on every metric or dimension.
- When hard limits exist (e.g., disk full), static thresholds are easier to explain.

Never use dynamic thresholds as a substitute for capacity planning or SLOs. Measure false positives and false negatives before and after enabling them.

## 8. Dimensions, Multi-Resource Scope, and Cardinality

Suppose a requests metric carries dimensions:

~~~text
region = eastasia, southeastasia       (2)
status = 200, 400, 401, 404, 500, 503 (6)
instance = 1..20                       (20)
Theoretical combinations: 2 * 6 * 20 = 240 series
~~~

Actual series count depends on which combinations occur, yet alerting per dimension can spawn many **independent alert instances**, raising costs and notification noise.

Principles:

1. Split by a dimension only if different owners or runbooks **take different actions**.
2. Never use `userId`, `requestId`, or order ID as default dimensions due to extreme cardinality.
3. Monitor service-level SLOs first; use region/instance splits for diagnosis.
4. For multi-resource alerts, verify resource types, regions, and `targetResourceType`/`targetResourceRegion` support.
5. Avoid per-Pod alerts on Kubernetes where Pods churn constantly; monitor service health instead.
6. Check **metric time-series pricing** and limits before enabling splits.

## 9. Stateful, Stateless, Fired, and Resolved

A **stateful alert** tracks problem state: breaching the threshold transitions to **Fired**; recovering and passing evaluation transitions to **Resolved**. A single Fired state can span multiple evaluation cycles.

A **stateless alert** can re-notify on every matching evaluation depending on rule type and config—useful for event-style conditions, though prone to noise.

~~~mermaid
stateDiagram-v2
  [*] --> Healthy
  Healthy --> Fired: threshold breached
  Fired --> Fired: condition still true
  Fired --> Resolved: recovery condition
  Resolved --> Healthy: next cycle
~~~

**Never assume Azure resolves an alert instantly the moment a query returns 0.** Resolution state, timing, `autoMitigate`, and suppression vary across metric rules, scheduled query rules, and API versions.

### Alert Condition vs. User Acknowledgement

- **Monitor condition** (`Fired`/`Resolved`): reflects telemetry state.
- **User state** (`New`/`Acknowledged`/`Closed` where supported): reflects human incident handling.

Marking an incident "acknowledged" does not lower CPU. Likewise, a metric returning to normal does not prove the root cause was permanently fixed.

## 10. Creating a Metric Alert in the Azure Portal

Lab VM monitoring example:

1. Open **Azure Portal → Monitor → Alerts → Create alert rule**, or open Alerts on the VM.
2. Target the exact **VM resource ID** and subscription.
3. Select the `Percentage CPU` signal.
4. Choose `Average`, operator `Greater than`, threshold `80%`.
5. Set window size `5 minutes` and evaluation frequency `1 minute` if supported.
6. Set severity `Sev2`, and document **owner, user impact, and runbook URL** in the description.
7. Attach the lab on-call action group.
8. Verify resource group and tags, then Review + Create.
9. After creation, verify the rule is Enabled with the right scopes, condition, and actions.
10. Verify firing with **controlled** load or traffic.

Never push production CPU to 100% just to test an alert. Use a sandbox VM or temporarily adjust the threshold on a **dedicated test rule**, then revert.

## 11. Azure CLI: Inspecting Metric Sources Before Creating Rules

~~~bash
az account show \
  --query "{subscription:name,subscriptionId:id,tenantId:tenantId}" \
  -o json

RG="rg-observability-lab"
VM_NAME="vm-monitor-lab"

VM_ID=$(az vm show -g "$RG" -n "$VM_NAME" --query id -o tsv)

az monitor metrics list-definitions \
  --resource "$VM_ID" \
  --query "[].{name:name.value,unit:unit}" \
  -o table

az monitor metrics list \
  --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --aggregation Average \
  --interval PT1M \
  -o json
~~~

These commands are read-only; metric definitions and data availability vary by resource type, region, and CLI version. If samples are empty, verify time range and sampling interval before building rules.

### Illustrative Metric Alert Creation

~~~bash
AG_ID="<ACTION_GROUP_RESOURCE_ID>"

az monitor metrics alert create \
  --name "alert-vm-cpu-high-lab" \
  --resource-group "$RG" \
  --scopes "$VM_ID" \
  --condition "avg Percentage CPU > 80" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 2 \
  --action "$AG_ID" \
  --description "VM CPU average >80% over 5m"
~~~

This is a **common CLI pattern**; verify `az monitor metrics alert create -h` on your installed CLI version—especially `--condition` syntax, resource type/region, and `--action`. A successful `create` **does not prove** the rule has fired or notifications work.

### Inspecting Configuration

~~~bash
az monitor metrics alert show \
  --resource-group "$RG" \
  --name "alert-vm-cpu-high-lab" \
  -o json
~~~

Verify scopes, criteria, severity, frequency, window size, `actionGroupId`, and `enabled` against your design.

## 12. What Is an Action Group?

An **action group** is an Azure Monitor resource defining receivers and actions: email, SMS/voice/push (where supported), webhooks, Logic Apps, Azure Functions, Event Hubs, ITSM, or other integrations.

~~~mermaid
flowchart TD
  AL["Azure alert Fired"] --> AG["Action group"]
  AG --> EMAIL["On-call email"]
  AG --> SMS["SMS / push if supported"]
  AG --> LOGIC["Logic App router"]
  AG --> HOOK["Webhook / incident service"]
  LOGIC --> TICKET["Ticket / escalation"]
~~~

An action group can be reused across many alert rules. It **does not pick signals or evaluate thresholds**; it runs only when an alert rule or processing flow invokes it.

### Four Design Questions

1. **Who receives it:** on-call team, service owner, security, or data team.
2. **Urgency:** email, paging, incident ticket, or automation.
3. **Payload:** Common Alert Schema vs. receiver-specific schema.
4. **Reliability:** authentication, retries, idempotency, logging, and failover.

Never route `Sev4` informational alerts to midnight SMS pages like `Sev0`.

## 13. Action Group Receiver Types and Safety

| Receiver | Use Case | Risks / Design Decisions |
|---|---|---|
| Email | Low-urgency alerts / team inboxes | Ownership drift, spam filters, stale aliases |
| SMS / Voice | Critical incident paging | Regional support, cost, user consent |
| Push | Supported devices/apps | Device enrollment and coverage |
| Webhook | Incident platforms / custom handlers | HTTPS, authentication, idempotency |
| Logic App | Routing, escalation, ticketing | Permissions, workflow costs/retries |
| Azure Function | Custom remediation | Over-privileging, infinite loops, secret safety |
| Event Hubs | Event streaming pipelines | Consumer lag, replay, retention |
| ITSM | Third-party ticketing | Duplicate tickets, connector credentials |
| Automation Runbook | Conditional playbooks | Approvals, allowlisted actions, rollback |

**An HTTPS webhook alone does not prove a request came from Azure Monitor.** Authenticate receivers using supported mechanisms, keep long-lived URLs/keys out of code and logs, and restrict IPs/identities or place a gateway in front where appropriate. Never grant an alert receiver subscription-wide Owner.

## 14. Common Alert Schema

**Common Alert Schema** standardizes payloads across alert types and supported receivers, letting automation parse consistent top-level fields. Condensed example:

~~~json
{
  "schemaId": "azureMonitorCommonAlertSchema",
  "data": {
    "essentials": {
      "alertId": "<ALERT_INSTANCE_ID>",
      "alertRule": "alert-vm-cpu-high-lab",
      "severity": "Sev2",
      "signalType": "Metric",
      "monitorCondition": "Fired",
      "firedDateTime": "2026-11-20T11:00:00Z",
      "alertTargetIDs": ["<AZURE_RESOURCE_ID>"]
    },
    "alertContext": {
      "conditionType": "SingleResourceMultipleMetricCriteria"
    }
  }
}
~~~

This is **illustrative**, not the complete schema for every alert. `alertContext` varies by metric, log, activity type, API version, and signal. Never assume a mandatory `metricValue` field exists on log alerts.

### Receivers Must Be Idempotent

- Deduplicate by `alertId` + condition/correlation so webhook retries do not open 10 identical incidents.
- When `Resolved` arrives, update the matching incident instead of creating a new one.
- If context is incomplete, query an authorized API/CMDB rather than guessing tenants.
- Never write raw queries containing PII or secrets into public tickets.
- Handle failures with retries and dead-lettering, avoiding alert → remediation → alert loops.

## 15. Creating an Action Group in Portal and CLI

Portal: **Monitor → Alerts → Action groups → Create**. Pick subscription and resource group, set name and short name, add an **authorized lab** email receiver, enable Common Alert Schema if appropriate, review/create, then click **Test action group** and verify delivery.

Example CLI creating an initial action group resource:

~~~bash
RG="rg-observability-lab"

az monitor action-group create \
  --name "ag-platform-oncall-lab" \
  --resource-group "$RG" \
  --short-name "platform"

az monitor action-group show \
  --name "ag-platform-oncall-lab" \
  --resource-group "$RG" -o json
~~~

**Without receivers, no emails are sent.** Add receivers via CLI, API, or Portal per current schema. For automation, prefer Bicep declaring concrete receivers rather than manual UI edits missing from Git.

Fetch its ARM ID:

~~~bash
AG_ID=$(az monitor action-group show \
  --name "ag-platform-oncall-lab" -g "$RG" \
  --query id -o tsv)
~~~

**Testing an action group does not test alert trigger conditions.** Test both rule firing and notification delivery.

## 16. What Is a Log Alert?

A **scheduled query rule** executes a **KQL** query against a Log Analytics workspace or supported resource scope and compares the result to a threshold. Use it for patterns absent from platform metrics:

- Too many failed `checkout` requests.
- Concurrent `status=500` errors across multiple dependencies.
- Missing `payment-succeeded` records during an expected interval.
- Repeated `Key Vault SecretGet` denials.
- Post-deployment failures isolated to specific tenants.
- Business/transaction rule violations detectable via queries.

~~~mermaid
flowchart LR
  APP["Spring Boot / Azure resource"] --> DIAG["App Insights / diagnostic settings"]
  DIAG --> LA["Log Analytics workspace"]
  LA --> KQL["Scheduled KQL query"]
  KQL --> TEST{"Count/measure threshold?"}
  TEST -->|Yes| ALERT["Log alert fired"]
  ALERT --> AG["Action group"]
  TEST -->|No| NEXT["Next evaluation"]
~~~

Log alerts require **data ingestion**. If logs haven't reached the workspace or sampling dropped failing requests, queries can return zero rows even while the app fails.

## 17. KQL: Verify Tables Before Creating an Alert

Suppose workspace-based Application Insights populates `AppRequests`. Open Log Analytics Logs and confirm table and columns:

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| project TimeGenerated, OperationName, ResultCode, Success, DurationMs, _ResourceId
| take 20
~~~

Not every workspace contains `AppRequests`. For legacy Application Insights or other resource-specific logs, adjust to the real table (e.g., `requests` in classic context). **Never build rules on tables not receiving data.**

Azure resource logs may land in the legacy `AzureDiagnostics` table or **resource-specific tables** depending on diagnostic settings. Those tables have different schemas than `AppRequests`: verify exact table names, columns, categories, and workspace data before writing log alerts; swapping table names mechanically without updating KQL breaks rules.

### Counting Failed Requests

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| where _ResourceId =~ "<APP_INSIGHTS_RESOURCE_ID>"
| where Success == false
| project TimeGenerated, OperationName, ResultCode
~~~

This query returns **one row per failed request**. Matching against **`number of rows > 20`** works logically here. Ensure filters scope to the right app/resource; one workspace often holds logs from many resources.

## 18. Row Count vs. Numeric Measure

### Row-Count Alert

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| where Success == false
~~~

With 42 matching records, **row count = 42**.

### Numeric-Measure Alert

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| summarize FailedRequests = countif(Success == false)
~~~

This query returns **a single row** with `FailedRequests=42`. A rule checking `row count > 20` will never fire because there is only **1 row**. You must configure **measure column = `FailedRequests`** with the matching aggregation, operator, and threshold.

### Error Rate

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| summarize Total=count(), Failed=countif(Success == false)
| extend FailureRatePct =
    iff(Total == 0, real(null), 100.0 * todouble(Failed) / todouble(Total))
| where Total >= 100
| project FailureRatePct
~~~

`Total >= 100` guards against low-traffic noise: 1 failure out of 1 request equals 100%, rarely proving a wide outage. **However, 0 requests can itself be an outage**, requiring separate availability, heartbeat, or no-data alerts.

### Window Size and Evaluation Schedule

For a **15-minute window and 5-minute evaluation frequency**, overlapping windows evaluate the same records multiple times. Stateful alerts suppress repeat notifications, yet each evaluation must not be treated as a separate incident. Align frequency with **ingestion lag**.

## 19. Scheduled Query Rules: Configuring Conditions Properly

A **scheduled query log alert** typically includes:

| Property | Meaning |
|---|---|
| **Scope** | Log Analytics workspace or supported resource with query access |
| **Query** | KQL producing rows or numeric measures |
| **Measure** | Number of rows or a specific measurement column |
| **Operator/threshold** | Compares result against threshold |
| **Evaluation frequency** | E.g., every 5 minutes |
| **Window size** | E.g., lookback over 15 minutes |
| **Failing periods** | How many recent evaluations must breach before firing |
| **Severity** | Operational priority |
| **State / auto mitigation** | Fired/Resolved behavior per rule type and config |
| **Actions** | Action group(s) |
| **Identity/permissions** | Query read rights and managed identity if required by rule type |
| **Dimensions** | Splits alerts by query column when supported |

Never write an alert query returning millions of rows: queries must **filter early, project minimally, and compute efficiently**. Queries must finish within service limits; timeouts or permission failures cause evaluation errors.

### What Are Failing Periods?

Suppose evaluation runs every 5 minutes:

~~~text
Window size: 15m
Evaluation frequency: 5m
Number of evaluation periods: 3
Minimum failing periods to alert: 2

Last 3 evaluation results: True, False, True
=> 2/3 periods breached; rule fires under this condition.
~~~

This illustrates the logic of **failing periods** on supported scheduled query rules. Verify current schema/version defaults when omitted. It **does not** multiply the query's row count by 3; window size and evaluation history are separate axes.

## 20. Creating a Log Alert in the Azure Portal

Example: "over 15 minutes, failed requests > 20":

1. Open **Monitor → Alerts → Create alert rule**.
2. Select the Log Analytics workspace containing `AppRequests`.
3. Select **Custom log search** or **Log search** depending on Portal version.
4. Paste the 15-minute failed-requests KQL from Section 17.
5. Choose measure **Table rows / Number of results** (not a numeric column).
6. Choose operator **Greater than**, threshold **20**.
7. Choose evaluation frequency **5 minutes** and window size **15 minutes**.
8. Set failing periods and stateful behavior where supported.
9. Choose **Sev2**, the app team's action group, and add owner/runbook details.
10. Review cost and query coverage, create the rule, and confirm it is Enabled.
11. Inject a controlled test log and verify ingestion, rule firing, and delivery.
12. Delete or revert test alerts and thresholds afterward.

**Never assume Preview results guarantee production firing.** Previews may query different windows or user permissions than the scheduled evaluator. Verify workspace, window, permissions, ingestion, and end-to-end firing.

## 21. Azure CLI: Inspecting the Scheduled Query Command Surface

Azure CLI manages **scheduled-query rules** via:

~~~bash
az monitor scheduled-query --help
az monitor scheduled-query create --help
az monitor scheduled-query list \
  --resource-group "rg-observability-lab" -o table
~~~

Parameters for log alerts have evolved across CLI and API generations. Never blindly copy legacy `--condition "count ... > N"` snippets when current schemas expect separate flags for **scope**, `evaluation-frequency`, `window-size`, `failing-periods`, `action-groups`, and measure/row-count settings. Check **Bicep/ARM** in Section 22 for the declarative model, or run `az monitor scheduled-query create -h` before deploying.

### Why Not Cram Every KQL Query into One CLI Condition String?

- Scheduled query rules v2 define structured criteria.
- Returning rows vs. aggregated measures alters rule semantics.
- Dimension splits and `failingPeriods` do not map cleanly to legacy syntax.
- KQL pipes, quotes, and `$` signs easily break in Bash/PowerShell quoting.
- Bicep/YAML templates are far easier to review, version-control, and validate than a giant one-liner.

**Bottom line:** check your installed CLI extension schema and exact IDs/tenant/resource group before running. A syntactically valid command targeting the wrong workspace still creates a broken alert.

## 22. Bicep: One Action Group, One Metric Alert, One Log Alert

This is an **illustrative declarative template** using common ARM/Bicep resource types; validate it against your deployment toolchain schema and scoped permissions. Use only lab mailboxes you control.

~~~bicep
@description('Azure VM resource ID (metric scope)')
param vmResourceId string

@description('Azure VM region, e.g. southeastasia')
param vmRegion string

@description('Log Analytics workspace ARM resource ID')
param workspaceResourceId string

@description('Workspace region for scheduled query rule')
param workspaceRegion string

@description('Application Insights ARM resource ID for AppRequests filter')
param appInsightsResourceId string

@description('Authorized testing mailbox only')
param oncallEmail string

resource ag 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-platform-oncall-lab'
  location: 'global'
  properties: {
    groupShortName: 'platform'
    enabled: true
    emailReceivers: [
      {
        name: 'lab-email'
        emailAddress: oncallEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource cpuHigh 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-vm-cpu-high-lab'
  location: 'global'
  properties: {
    description: 'VM CPU average over 80 percent'
    severity: 2
    enabled: true
    scopes: [
      vmResourceId
    ]
    targetResourceType: 'Microsoft.Compute/virtualMachines'
    targetResourceRegion: vmRegion
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'HighCpu'
          metricNamespace: 'Microsoft.Compute/virtualMachines'
          metricName: 'Percentage CPU'
          timeAggregation: 'Average'
          operator: 'GreaterThan'
          threshold: 80
        }
      ]
    }
    actions: [
      {
        actionGroupId: ag.id
      }
    ]
  }
}

resource errorLog 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'alert-app-requests-failed-lab'
  location: workspaceRegion
  properties: {
    displayName: 'App requests failed in 15m'
    description: 'Count of failed requests above threshold'
    enabled: true
    severity: 2
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [
      workspaceResourceId
    ]
    criteria: {
      allOf: [
        {
          query: 'AppRequests | where TimeGenerated >= ago(15m) | where _ResourceId =~ "${appInsightsResourceId}" | where Success == false'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 20
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
    actions: {
      actionGroups: [
        ag.id
      ]
    }
  }
}

output actionGroupId string = ag.id
output metricRuleId string = cpuHigh.id
output logRuleId string = errorLog.id
~~~

### Explanation

- **Action group** is a separate resource with `location: 'global'` and an email receiver.
- **Metric alert** watches the VM resource ID for `Percentage CPU`, static threshold > 80.
- **Log alert** queries `AppRequests` filtered to a specific **Application Insights resource ID** (via `_ResourceId`) inside the workspace.
- The query returns **failing rows**, so `timeAggregation: 'Count'` evaluates row count per schema.
- `actions.actionGroups` wires the log alert to the action group above.
- `evaluationFrequency: 'PT5M'` and `windowSize: 'PT15M'` use ISO 8601 durations.
- `autoMitigate` controls stateful recovery per API version; do not assume instant resolution.
- Bicep infers deployment ordering via `ag.id`.

### Before Deploying

1. Verify Bicep resource API versions are supported in your region and tenant.
2. Verify permissions to create `Microsoft.Insights/*`, required role assignments, and scopes.
3. Confirm the workspace holds `AppRequests` data with matching `_ResourceId` and `Success` columns.
4. Run `az bicep build` / validation in **your own** pipeline and inspect what-if output.
5. Confirm lab mailboxes have owner consent and never email external parties.
6. If the workspace sits in another RG/subscription, verify cross-scope permissions and limits.
7. Never deploy test rules in prod or `Sev0` alerts in a lab.
8. Test first firing, recovery, notification delivery, and cost post-deployment.

Fields may need adjustment for newer ARM schemas and feature limits. Never claim this example is "deployed and verified in production" without actually testing it.

## 23. Alert Processing Rules: Routing and Suppression

An **alert processing rule** acts on fired alert instances matching its filters and can:

- Add an **action group** to matching alerts.
- **Suppress** actions during planned maintenance windows or schedules where supported.
- Scope by subscription, resource group, or resource, and filter by severity, monitor condition, alert rule ID/name, or resource type.

~~~mermaid
flowchart LR
  A["Fired alert"] --> MATCH{"Processing rule matches?"}
  MATCH -->|No| DEFAULT["Original action group(s)"]
  MATCH -->|Yes, add| EXTRA["Add escalation group"]
  MATCH -->|Yes, suppress| QUIET["No notification for matching period"]
  DEFAULT --> OPS["On-call / incident"]
  EXTRA --> OPS
  QUIET --> RECORD["Alert still visible in Alerts UI"]
~~~

**Note:** suppression in an alert processing rule stops **notifications/actions**; it does not cancel the telemetry condition or **modify the underlying alert rule query/metric**. Alerts still appear in Azure Monitor and rules still evaluate.

### Use Case

During a 01:00–02:00 UTC maintenance window, a backend team suppresses expected `Sev3` alerts while **never suppressing `Sev0` regional outage alerts**. When the window expires, the schedule ends automatically without relying on someone remembering to re-enable rules.

### Guardrails

- Record UTC start/end, owner, and change ticket.
- Minimize scope (avoid subscription-wide unless required).
- Never suppress "all severities" without understanding impact.
- Audit creation and edits of processing rules.
- Review fired alerts in the Alerts UI even when notifications were suppressed.

## 24. Missing Data: NoData Does Not Mean Healthy

One of the deadliest failure modes:

~~~text
App crashes -> stops emitting request telemetry
Log query "errors > 20" -> returns 0 rows
Alert stays silent -> on-call assumes system is healthy
~~~

**Zero logs does not prove zero errors.**

### Independent Signals to Maintain

1. External **availability tests / probes**.
2. **Heartbeats** from agents, apps, or scheduled markers.
3. **Data freshness:** when did the last successful event arrive?
4. **Ingestion health:** are sources sending and workspaces ingesting on time?
5. **Traffic anomalies:** request count dropping to zero during active business hours.
6. **Dependency state:** queue backlog rising while consumers emit zero logs.
7. **Platform metrics** independent of the log pipeline where available.

### KQL Alert for Missing Heartbeat

Suppose `AppTraces` receives a `batch_completed` marker from an hourly job:

~~~kusto
AppTraces
| where TimeGenerated >= ago(2h)
| where Message == "batch_completed"
| summarize LastSeen = max(TimeGenerated)
| where isnull(LastSeen) or LastSeen < ago(90m)
~~~

A `summarize` without a `by` clause normally returns one row with `LastSeen = null` when no rows match, letting the query output a row when missing. Trigger on **row-count > 0**; note this logic assumes `AppTraces` exists and is instrumented. If the job runs only on weekdays, schedule appropriately to avoid weekend false alarms.

### `TimeGenerated` Differs from Ingestion Time

`TimeGenerated` is the event timestamp; records can arrive late. When alerts use `ago(15m)`, account for **ingestion latency**, delayed delivery, clock skew, and window alignment. Kusto exposes `ingestion_time()` in supported contexts, though not every table provides identical ingestion metadata. If log lag exceeds your evaluation window, widen windows, add evaluation delays, or monitor ingestion separately.

## 25. SLOs, Burn Rate, and Customer-Meaningful Alerts

CPU thresholds spot **busy resources**, which do not always correlate with user pain. **SLO alerts** track Service Level Indicators such as:

- Availability: share of valid requests succeeding.
- Latency: share of requests faster than the SLO target.
- Data freshness: share of batches finishing on time.
- Transaction quality: share of checkouts free of business errors.

### Error Budget

With a **99.9%** availability SLO, the error budget is **0.1%** of requests or minutes depending on definition. **Burn rate** measures how fast the budget is being consumed relative to the sustainable pace.

Illustrative example:

~~~text
SLO success: 99.9% -> allowed error fraction 0.001
Observed error fraction: 0.020 (2%)
Burn rate = 0.020 / 0.001 = 20x
~~~

Under this hypothetical window, the error budget is burning 20 times faster than the steady-state allowance. Still, paging decisions require minimum sample counts, short/long windows, traffic patterns, business impact, and no-data handling.

### Multi-Window, Multi-Burn-Rate

Better than "5xx > 5 everywhere":

- Short window + high burn rate → page fast on sharp outages.
- Long window + moderate burn rate → open a ticket or review capacity.
- Combine error rates with minimum sample volume.
- Exclude non-SLI traffic where defined validly (e.g., user-caused 4xx).

Never mix request counts and error fractions incompatibly. Drive severity from user impact and SLOs, not raw log row counts alone.

## 26. Dimension Splits and Log Alert Cardinality

KQL can group by `Region` or `OperationName`:

~~~kusto
AppRequests
| where TimeGenerated >= ago(15m)
| summarize Failed = countif(Success == false),
            Total = count()
    by OperationName
| extend FailurePct = iff(Total == 0, real(null),
                          100.0 * todouble(Failed)/todouble(Total))
| where Total >= 100 and FailurePct > 5
~~~

Splitting alerts per `OperationName` spawns a separate alert instance per operation. That works when different endpoints have different owners, but **never** split by `requestId` or `customerId`.

### Schema Caveats

Log alerts using **split-by dimensions** require supported column types in the rule schema; merely writing `summarize by` in KQL does not automatically make Azure Monitor split rows into dimensions as you might expect. Declare dimensions explicitly in the rule schema and verify output shapes. For some queries, alerting when **result row count > 0** is simpler than per-row splitting.

### Cost and Noise

If one shared bug breaks 100 operations simultaneously, opening 100 tickets slows response. Deduplicate/group in incident routing, analyze dimensions on dashboards, and page a single **service-level incident** when appropriate.

## 27. Designing Reliable Action Group Delivery

An action group may call a webhook or Logic App. For production incident workflows:

~~~mermaid
sequenceDiagram
  participant M as Azure Monitor
  participant G as Action group
  participant W as Webhook / Logic App
  participant I as Incident platform
  M->>G: Alert Fired event
  G->>W: Common alert schema payload
  W->>W: Validate authentication & schema
  W->>W: Dedup alertId / condition
  W->>I: Create or update incident
  I-->>W: Incident ID
  Note over W,I: Safe retry on downstream 429/503
  M->>G: Resolved event
  G->>W: Same alert lifecycle (when emitted)
  W->>I: Resolve/update matching incident
~~~

### Assumptions to Design For

- HTTP callbacks can fail or be retried.
- Events can arrive delayed or out of order across systems.
- Duplicate deliveries must **never** trigger duplicate irreversible actions.
- Store receiver auth secrets/tokens in Key Vault or use managed identities where supported.
- Validate incoming payloads rather than trusting arbitrary Internet traffic.
- Separate **notifications** from **automated remediation**: opening a ticket is far safer than auto-deleting or restarting resources.
- Never equate sending an email with human acknowledgement.
- Include correlation IDs, alert IDs, affected resource IDs, and runbook URLs.

### Webhook Security

Use HTTPS, sender validation/OAuth or authenticated endpoints as supported, secret rotation, and network restrictions. Never embed raw long-lived webhook secrets inside query descriptions or Log Analytics. Scope Logic App / Function permissions tightly: a service-restart runbook needs rights on that specific resource, not subscription Owner.

## 28. Alert Routing by Ownership and Severity

Example table:

| Alert | Severity | Owner | Action |
|---|---|---|---|
| Checkout 5xx rate breaches SLO | Sev1 | Commerce on-call | Page + incident |
| VM CPU high for 10 min | Sev2 | Platform | On-call/email + capacity check |
| Batch missing success event | Sev2 | Data platform | Job ticket + retry review |
| Key Vault 403 spike | Sev2 | Security/platform | Security ticket + config review |
| Certificate expires in 30 days | Sev3 | PKI team | Scheduled ticket |
| Dev environment CPU high | Sev4 | Dev owner | Business-hours email |
| Cross-region dependency outage | Sev0 | Incident commander | Multi-team escalation |

**Azure Monitor severity does not automatically route to the right person.** Alert rules link to action groups; alert processing rules or downstream workflows add routing. Maintain owner/resource/service tags in CMDB/IaC so alerts never go to abandoned mailboxes.

### Avoid Duplicate Paging

One database outage can trigger:

- Database CPU/availability alert.
- Application dependency failure alert.
- API 5xx alert.
- Queue backlog alert.

These are **multiple symptoms of one root cause**—do not blindly spawn four disconnected incidents without correlation. At the same time, do not suppress every symptom if they represent distinct impacts. Deduplicate and correlate in the **incident platform** while keeping full evidence on dashboards.

## 29. Permissions to Create Alerts and Action Groups

Azure Monitor alerts are Azure resources; creators need ARM write permissions at the target scope plus **telemetry read rights** per resource/workspace authorization.

| Role / Task | Permissions to Evaluate |
|---|---|
| View VM metrics | Appropriate Azure Monitor / Reader role on the VM |
| Query workspace logs | Log Analytics query permissions & scope per access control mode |
| Create/edit metric alerts | `Microsoft.Insights/metricAlerts/write` at target scope |
| Create/edit scheduled query rules | `Microsoft.Insights/scheduledQueryRules/write` and query identity/permissions |
| Create/edit action groups | `Microsoft.Insights/actionGroups/write` |
| Grant rights to automation identity | ARM role assignment write within approved scope |
| Webhook remediation | Managed identity + minimal role on target resource |
| View incident action logs | Read access to workflow/diagnostics logs |

**Contributor** at resource-group scope covers many monitor resources, yet should never be granted subscription-wide by default. Use roles like Monitoring Contributor, Monitoring Reader, or Log Analytics Reader where appropriate, checking **actual role definitions** and policies.

For humans performing high-privilege monitoring or remediation edits, use **Privileged Identity Management (PIM)** just-in-time activation where supported by tenant licensing. PIM does not replace scope limits, approvals, and auditing—never grant a webhook or Logic App subscription Owner just to send notifications.

### Log Alert Identity

Some scheduled query configs require a managed identity or service permissions to query workspaces/resources, especially in cross-resource, cross-tenant, or advanced scenarios. Do not assume the creating user's query access persists forever; check current query authorization and service identity requirements.

## 30. Security and Compliance in Alerting

An alert can expose sensitive information inside:

- Rule names, descriptions, and queries.
- KQL result columns.
- Alert context and dimensions.
- Webhook payloads.
- Email subjects and bodies.
- Incident/ticket comments.
- Application logs and metrics.

**Never place** access tokens, raw database connection strings, customer PII, passwords, or secrets into query results or alert descriptions. Point authorized responders to the access-controlled workspace using correlation IDs.

### Guardrails for Automated Actions

A 5xx alert **must never delete a resource group**. When automation restarts instances or scales compute:

1. Define the runbook, owner, risk, and blast radius.
2. Restrict actions to an explicit resource allowlist.
3. Check current state before acting to avoid restart loops.
4. Enforce concurrency limits, cooldowns, and idempotency keys.
5. Maintain logging/auditing, notifications, and rollback.
6. Require human approval for destructive production actions.
7. If remediation fails, open/escalate an incident instead of retrying forever.

## 31. Azure Monitor Log Alerts: KQL Performance and Cost

Frequently evaluating heavy log queries over large datasets increases query costs and risks hitting service limits.

### Writing Economical KQL

- Filter `TimeGenerated` early and tightly to the needed window.
- Filter `_ResourceId` or service identifiers to avoid workspace-wide scans.
- Project only columns required by the condition.
- Avoid `parse_json`/regex across raw messages when structured columns exist.
- Avoid unnecessary wide `join` or `union` queries.
- Keep `summarize` cardinality bounded.
- Account for sampling and accuracy when querying Application Insights.
- Match evaluation frequency to SLOs and ingestion lag.
- Avoid duplicate alert rules running the same query across overlapping scopes.

### Impact of Sampling

If Application Insights sampling drops 90% of requests, `count()` undercounts true traffic unless sampling weights / `ItemCount` are handled properly per schema. For error rates or business-critical metrics, understand sampling semantics and prefer dedicated metrics when exactness matters.

**Never assume `countif(Success == false)` equals total HTTP failures across the system** when logs are sampled, dropped during ingestion, or partitioned.

## 32. Reliability: The Alert Pipeline Must Also Be Monitored

Monitoring an application without monitoring the alert pipeline leaves **blind spots**.

~~~text
Application healthy?
   ↓
Telemetry emitted?
   ↓
Ingested/available?
   ↓
Rule evaluated successfully?
   ↓
Alert fired?
   ↓
Action group invoked?
   ↓
Receiver delivered?
   ↓
Human acknowledged?
   ↓
Incident resolved?
~~~

Runbook checklist:

- Is the agent or OpenTelemetry exporter running?
- Do diagnostic settings route to the right workspace?
- Are there ingestion delays, retention cuts, or sampling changes?
- Is the rule Enabled with the right scope and query?
- Are rule evaluations erroring or disabled due to lost permissions?
- Does the action group have active receivers, the right schema flag, and valid addresses?
- Is an alert processing rule suppressing notifications on schedule?
- Is the webhook/Logic App returning 401, 429, 5xx, or hitting expired credentials?
- Is the on-call schedule up to date?
- Did telemetry drop during a peak outage, making dashboards look misleadingly "clean"?

### Synthetic Canaries for Alert Delivery

Teams can schedule **approved** periodic test alerts or action group tests and verify delivery. Because test deliveries carry cost and noise, target lab or training receivers—never page production on-call without context.

## 33. Costs: Metric Alerts, Log Alerts, and Action Groups

Total cost can include:

~~~text
Monitoring cost =
  Alert rules / monitored metric series
  + scheduled query rule evaluations and data/query usage
  + telemetry ingestion into Log Analytics/Application Insights
  + retention/export
  + action-group channel delivery / integration charges
  + Logic Apps/Functions/ITSM automation
  + human operational overhead
~~~

There is no single flat price across all Azure Monitor signals. Pricing depends on resource types, monitored time-series counts, alert rule types, evaluation frequency, log query plans, workspace ingestion, delivery channels, regions, and service agreements.

### Cost Traps

- Splitting alerts per instance × per error code × per customer explodes cardinality.
- Running a heavy KQL query every minute unnecessarily.
- Logging full raw request bodies (driving ingestion cost and privacy risk).
- Duplicating identical rules across overlapping workspace and resource scopes.
- Action group webhooks triggering Logic Apps that charge per retry.
- Mailing/SMSing dev-environment alerts, exhausting operations staff.
- Retaining data longer than needed.
- Forgetting to clean up lab alert rules and action groups after testing.

### FinOps Checklist

1. Use clear severity tiers and ownership to cut noise.
2. Separate **safety-critical** monitoring from informational alerts.
3. Measure alert volume, false-positive rate, ack time, and resolution time.
4. Track cost per **actionable incident**, not just cost per rule.
5. Apply budgets and tags (`owner`, `env`, `costCenter`).
6. Audit unused rules and legacy queries regularly.
7. Never silence meaningful alerts just to save money; optimize signals, aggregations, and queries instead.
8. Verify current Azure Monitor pricing pages before budgeting.

## 34. Troubleshooting: Rule Does Not Fire

| Symptom | Cause | Check |
|---|---|---|
| Metric alert shows no data | Wrong metric, resource, namespace, or collection delay | Metrics Explorer and metric definitions |
| CPU > 80 yet rule stays quiet | 5m Average still below 80 or evaluation hasn't run | Window, aggregation, threshold |
| Rule Disabled | Created without enabling | Rule configuration |
| Multi-resource alert misbehaving | Incompatible type, region, or scope | Target metadata |
| Log alert stays silent | KQL returns 0 rows, wrong table/field | Run exact query against real schema |
| Log query returns 1 row with count=42 | Rule checks row count (=1) instead of column | Switch to numeric measure column |
| Errors exist, logs arrive late | Ingestion delay or sampling | `TimeGenerated`, ingestion health |
| KQL permission error | Identity/query authorization issue | Workspace permissions |
| Stateful alert won't re-fire | Still in `Fired` state, not yet `Resolved` | Alert instance state |
| Dynamic threshold lacks baseline | Insufficient history or wrong sensitivity | Metric history and sensitivity config |
| Rule fires, action group doesn't send | Disabled/bad receiver, routing, or suppression | Test action group, processing rules |
| Rule creation returns 403 | Missing ARM rights or Azure Policy block | Caller role, scope, Policy |
| Prod alert fires on wrong service | Shared workspace, query missing filter | `_ResourceId` and scope |

### Stage-by-Stage Debugging Flow

1. **Telemetry:** does the metric or log actually exist in the expected window?
2. **Rule:** are scope, Enabled, condition, aggregation, window, and frequency right?
3. **Evaluation:** are scheduled evaluations succeeding?
4. **State:** has it already Fired, is it stateful, and what is the recovery condition?
5. **Processing:** is a suppression or maintenance rule active?
6. **Action:** are the action group and receivers enabled and valid?
7. **Delivery:** did email, webhook, or Logic App receive and process the payload?
8. **Incident:** did the downstream incident platform deduplicate or filter it?

Never grant Owner or arbitrarily relax thresholds/severities before pinpointing which stage broke.

## 35. Troubleshooting: Action Group Fails to Notify

1. Verify `actionGroupId` in the metric/log rule matches the exact ARM ID.
2. Check that the action group is `enabled` and contains active receivers.
3. Click **Test action group** targeting a lab receiver and confirm email/webhook arrival.
4. Verify the Common Alert Schema flag matches what the consumer parser expects.
5. Check whether alert processing rules are suppressing notifications during maintenance.
6. Check email domains, spam filters, outbound policies, and on-call distribution lists.
7. For webhooks, inspect TLS, auth, routing, and HTTP 2xx/401/429/5xx responses.
8. For Logic Apps/Functions, check run history, managed identity permissions, and quotas.
9. Check whether receiver deduplication accidentally dropped a new alert.
10. Verify an actual alert instance Fired rather than only previewing KQL/Metrics Explorer.
11. Never paste raw access tokens or webhook shared secrets into chat while debugging.
12. Maintain a fallback channel if the primary notification provider goes down.

### Why Are Firing and Delivery Two Separate Tests?

- **Test action group** checks the receiver path without evaluating alert conditions.
- **Triggering an alert via telemetry** tests rule evaluation, after which you still verify delivery.
- An **end-to-end test** proves both connect cleanly via matching instance/correlation IDs.

## 36. Case Study: Payment System with Three Failure Modes

### Context

An Azure e-commerce product comprises:

- Spring Boot API on Azure Container Apps.
- PostgreSQL / Azure SQL for transactions.
- Azure Service Bus queue processing orders.
- Azure VM running a legacy connector.
- Workspace-based Application Insights / Log Analytics.
- Commerce, Platform, Data, and Security on-call teams.

### Alert Design

| Incident | Signal | Rule | Action Group |
|---|---|---|---|
| Legacy VM connector overloaded | VM `Percentage CPU` | Metric Average > 80%, 5m | Platform |
| Checkout 5xx spikes | `AppRequests` errors | Log error count/rate with min traffic | Commerce |
| Queue backlog stops draining | Service Bus metric | Metric threshold vs. baseline | Commerce/Data |
| `batch_completed` missing on schedule | `AppTraces` marker | Log no-data/freshness rule | Data |
| Role/permission edit causes Key Vault 403 | App error logs + Key Vault audit | Log count/error alert | Security/Platform |
| Certificate expiring soon | Cert metadata/event per support | Scheduled query / event alert | Security |

### Simulated Incident

At 10:00 UTC, a bad deployment causes checkout HTTP 500s for 15 minutes. Several VMs maintain normal CPU, so **CPU alerts stay silent**; log alerts and availability alerts must catch the outage. Notifications route to Commerce on-call via their action group. Shortly after, the incident platform receives DB dependency error alerts and deduplicates them under the same service/incident correlation.

At 10:20 UTC, on-call rolls back the deployment. Error rates drop; stateful alerts transition to `Resolved` per evaluation cadence, updating the incident workflow. The team still investigates root cause and reconciles impacted orders.

### Key Takeaways

- CPU is not a checkout SLO.
- 5xx rates require minimum sample guards and reliable sources.
- Action groups need owners, delivery tests, and escalation paths.
- Receivers need idempotency because one incident emits multiple alert signals.
- A `Resolved` alert does not prove lost business data was recovered.
- Log ingestion lag and sampling can affect log alert accuracy.
- Alert processing rules cut maintenance noise, yet must never hide `Sev0` outages.

~~~mermaid
flowchart TD
  API["Spring Boot + App Insights"] --> REQ["AppRequests error-rate KQL"]
  VM["Legacy VM"] --> CPU["CPU metric"]
  BUS["Service Bus"] --> QUEUE["Backlog metric"]
  REQ --> COM["Commerce on-call action group"]
  CPU --> PLAT["Platform action group"]
  QUEUE --> COM
  COM --> INCIDENT["Incident platform with dedup"]
  PLAT --> INCIDENT
  INCIDENT --> RUN["Owner + runbook + rollback"]
~~~

## 37. Comprehensive Lab: Metric Alert + Log Alert + Action Group

> **Safety:** deploy only inside an authorized **lab** resource group with a budget. KQL, metrics, action group notifications, Log Analytics, and integrations can incur charges. Never load-test production or send surprise pages to real on-call staff.

### Part A — Prepare Telemetry

1. Identify your lab subscription and resource group.
2. Pick a lab VM or resource emitting metrics.
3. Inspect Metrics Explorer, metric namespace, units, and dimensions.
4. Create or reuse a lab Log Analytics workspace.
5. Point a test app at workspace-based Application Insights.
6. Confirm `AppRequests` or the relevant log table contains data.
7. Note ingestion latency and sampling settings.
8. Pick a team-owned lab mailbox for the action group.
9. Document severity tiers and SLOs before setting thresholds.
10. Verify Azure Monitor RBAC rights to create rules and query logs.

### Part B — Action Group

1. Create `ag-platform-oncall-lab`.
2. Add a lab email receiver with Common Alert Schema enabled if needed.
3. Run **Test action group** and confirm arrival in the mailbox.
4. If using a lab webhook, verify HTTPS/auth and schema parsing.
5. Design deduplication by `alertId` and monitor condition.
6. Document runbook contacts, timezones, and on-call schedules.
7. Never use real SMS/voice numbers without consent.
8. Record the action group ARM ID for alert rules.

### Part C — Metric Alert

1. Target `vm-monitor-lab` and metric `Percentage CPU`.
2. Select `Average`, static threshold 80%, 5m window, 1m evaluation.
3. Set `Sev2` and attach the lab action group.
4. Deploy via Portal, CLI, or Bicep.
5. Verify the rule is Enabled with the exact scope.
6. On the **sandbox VM**, run a controlled CPU load or use an approved temporary test threshold.
7. Observe the alert instance transition to `Fired` with timestamp and metric value.
8. Verify the email/action group notification arrives.
9. Wait for recovery and record actual `Resolved` behavior.
10. Revert test thresholds/rules so noisy alerts aren't left behind.

### Part D — Log Alert

1. Write an `AppRequests` query for 5xx / `Success == false`.
2. Inspect sample records to verify resource ID and schema.
3. Select **number of rows** rather than a numeric measure for row-level results.
4. Configure a 15m window, 5m evaluation, and threshold e.g. > 20.
5. Attach the same or a dedicated action group per ownership.
6. Trigger controlled test request failures **in the lab**.
7. Wait for ingestion and evaluation; observe `Fired`.
8. Verify notification arrival and `signalType: Log` in Common Alert Schema.
9. Test a `summarize count()` query and explain why row-count != numeric count.
10. Add a missing-heartbeat alert alongside the failure-count alert.

### Part E — Noise, Security, and FinOps

1. Create a temporary rule with low-cardinality dimensions and inspect alert series.
2. Compare `Average` vs. `Maximum` thresholds for false positives.
3. Test a **lab** maintenance-window alert processing rule and verify scoped suppression.
4. Confirm alerts remain visible in the UI while notifications are suppressed.
5. Audit creator RBAC and webhook remediation identity rights.
6. Confirm logs and queries expose zero tokens or PII.
7. Review Cost Management estimates for metrics, logs, and alerts.
8. Write runbooks for 401/403, missing telemetry, rule not firing, and delivery failure.
9. Clean up lab rules, action groups, and temporary resources per authorization.
10. Write a short report noting which alerts were actionable vs. noisy and how to tune them.

## 38. Self-Check Questions

**Q1.** How do a metric alert and a scheduled query log alert differ in data source and latency?

**Q2.** Does an action group collect metrics or execute KQL on its own?

**Q3.** How does an alert rule differ from an alert instance and an alert processing rule?

**Q4.** Does `Average CPU > 80` over 5 minutes mean every single sample exceeded 80?

**Q5.** How does `Total` aggregation differ from `Average` on request counts?

**Q6.** How does evaluation frequency differ from window size?

**Q7.** Why can splitting by metric dimensions cause a cardinality explosion?

**Q8.** When are dynamic thresholds appropriate, and do they replace SLOs?

**Q9.** How do stateful and stateless alerts differ in repeat notifications?

**Q10.** How does monitor condition (`Fired`/`Resolved`) differ from user acknowledgement?

**Q11.** A log query returns 1 row with column `Failures=42`; why doesn't a row-count threshold `> 20` fire?

**Q12.** When do you configure a numeric measure column?

**Q13.** Why won't a log alert for `errors > 5` detect an app crash that stops emitting logs?

**Q14.** How can ingestion delay and sampling skew a log alert?

**Q15.** Why enforce minimum traffic when alerting on error rates?

**Q16.** Does `AppRequests` exist in every Log Analytics workspace?

**Q17.** What must a rule do when one workspace holds logs from many applications?

**Q18.** How do failing periods differ from `windowSize`?

**Q19.** What is the Common Alert Schema for, and is `alertContext` identical for metric and log alerts?

**Q20.** Why do webhook receivers need both authentication and idempotency?

**Q21.** Does testing an action group prove the alert condition works?

**Q22.** Does suppressing actions via an alert processing rule delete the alert?

**Q23.** Why shouldn't you suppress all `Sev0`/`Sev1` alerts during maintenance windows?

**Q24.** Why can a single database outage trigger multiple distinct alert instances?

**Q25.** What error fraction does a 99.9% SLO permit, and what does a 20x burn rate mean?

**Q26.** Which permissions are required to create alert rules and query a Log Analytics workspace?

**Q27.** A log alert doesn't fire even though the query finds rows: what should you check?

**Q28.** An alert shows `Fired`, yet on-call never received the email: where do you look first?

**Q29.** Why shouldn't an auto-restart Azure Function hold subscription Owner?

**Q30.** Which components can generate costs across a monitoring pipeline?

**Q31.** Why avoid using `userId` or `requestId` as default metric dimensions?

**Q32.** How can you test metric/log alerts end-to-end without impacting production?

**Completion criteria:** learners can choose and configure metric/log alerts based on real telemetry; write accurate row-count and numeric-measure KQL; create action groups with receivers and Common Alert Schema; verify rule firing, delivery, recovery, and no-data handling; and design severity, ownership, processing rules, noise reduction, security, and cost controls.

## Conclusion

**Metric alerts, log alerts, and action groups** form three complementary building blocks in **Azure Monitor**. Metric alerts detect threshold breaches quickly; scheduled query log alerts evaluate richer operational and business conditions; action groups connect fired alerts to responders and workflows. A reliable alert requires clear **scope, signal, aggregation, threshold, evaluation timing, severity, ownership, and action**—not merely a rule that saves without errors.

To operate Azure workloads safely and reliably, always verify **telemetry ingestion, row-count vs. numeric measure, stateful recovery, missing-data detection, dimension cardinality, Common Alert Schema, delivery reliability, SLOs/error budgets, Azure RBAC, incident idempotency, and FinOps**. Rehearse the full chain from data to alert to action in a lab, measure false positives, and refine runbooks before relying on it in production.

# Collecting Logs and Metrics with Container Insights

In the **CLOUD_PROVIDERS_AZURE** module, learners explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networking, compute, storage, and data services. The goal is deploying, monitoring, securing, and controlling costs for an application architecture on Azure. In the **AKS Operations** chapter, this lesson guides you through designing and using **Container Insights** and the **Azure Monitor** ecosystem to observe Kubernetes workloads: from application logs and pod status to CPU/memory metrics, alerts, and incident investigation.

Suppose an ordering system running on **Azure Kubernetes Service (AKS)** has three Deployments: `orders-web`, `orders-api`, and `payment-worker`. At 14:05, customers hit HTTP 500 errors. In Kubernetes, `orders-api` still shows three replicas in `Running` state. Looking only at pod status makes it easy to falsely conclude everything is fine. Finding the root cause requires combining multiple signal types: **application logs** recording errors, **Kubernetes inventory/events** describing pod changes, **metrics** showing CPU/memory pressure, and **tracing** if instrumented. Container Insights collects part of these signals with cluster context, while other Azure observability services complement it with deeper application telemetry.

After this lesson, you will be able to:

- Distinguish **logs, metrics, Kubernetes events, inventory, and distributed traces** in AKS operations.
- Explain Container Insights' collection path: **Azure Monitor Agent (AMA) → Data Collection Rule (DCR) → Log Analytics workspace**.
- Distinguish **Container Insights** from **Azure Monitor managed service for Prometheus**, Azure Monitor Metrics, Application Insights, and AKS control-plane diagnostic logs.
- Enable and verify Container Insights via the Portal or Azure CLI, accounting for workspace, permission, and network prerequisites.
- Write **KQL** queries to locate errors in `ContainerLogV2`, identify failing pods, and inspect metrics/inventory.
- Design dashboards, alerts, investigation workflows, and ways to reduce ingestion/retention costs.
- Enforce telemetry security, preventing secrets or personal data from leaking into logs.

## 1. Why Must AKS Monitoring Look Across Multiple Layers?

AKS is a managed Kubernetes platform, yet applications still run on nodes, pods, and containers with independent lifecycles. A 500 error may stem from application code, an expired secret, database timeouts, DNS, node memory exhaustion, or network failures. No **single** metric alone proves every root cause.

| Layer | Operational Question | Common Signal Sources |
|---|---|---|
| **Application** | Why did the API return 500? | Structured logs, exceptions, Application Insights/traces |
| **Container** | Did a container crash/restart or log errors to stderr? | Container logs, pod/container inventory, restart metrics |
| **Pod/Deployment** | Are replicas ready? Did image pull fail? | `kubectl`, Kubernetes events, inventory, workload metrics |
| **Node** | Is there CPU/RAM/disk/network pressure? | Node metrics, Container Insights performance, managed Prometheus |
| **Kubernetes control plane** | Are the API Server, scheduler, or autoscaler having issues? | AKS resource/diagnostic logs and service-supported signals |
| **Dependent Azure services** | Are Database/Storage/Key Vault slow or denying access? | Resource metrics, diagnostic logs, distributed tracing |
| **End-to-end system** | Are users experiencing SLO violations? | Request rate, error rate, latency, availability tests |

### 1.1. What Is a Log?

A **log** is a timestamped event record that can capture details of a specific request or error:

```json
{
  "timestamp": "2026-11-20T07:05:21Z",
  "level": "ERROR",
  "service": "orders-api",
  "message": "Payment provider timed out",
  "traceId": "d61c2e9f08f04bdc",
  "durationMs": 3000,
  "errorType": "UpstreamTimeout"
}
```

This is synthetic sample data, not logs captured from a live cluster. Logs help trace events back, but if every request writes dozens of lines, ingestion volume and storage costs rise rapidly.

### 1.2. What Is a Metric?

A **metric** is a numeric measurement over time, such as CPU utilization, container restart count, or requests per second. Metrics fit trend charts and alerts because they are much more compact than verbose logs:

```text
Time (UTC)           Pod                   CPU Usage
14:00                orders-api-abc        0.45 core
14:05                orders-api-abc        0.91 core
14:10                orders-api-abc        0.58 core
```

These numbers are illustrative. Distinguish **CPU cores**, **millicores**, **nanocores**, and **CPU percentage**; mixing units leads to wrong conclusions about consumption.

### 1.3. Kubernetes Events and Inventory

**Events** report state transitions such as `FailedScheduling`, `BackOff`, or `Unhealthy`. **Inventory** captures pods, nodes, containers, namespaces, and states observed by the agent. Together, they put logs into context: did errors start right after a pod was replaced or a node changed state?

### 1.4. Traces Are Not Container Logs

A **distributed trace** tracks a single request across multiple services and carries trace/span IDs. Traces require instrumentation (such as OpenTelemetry or Azure Monitor Application Insights) and do not automatically materialize merely from enabling Container Insights. Include `traceId` in logs to correlate with traces rather than expecting KQL over container stdout to reconstruct full span trees.

## 2. Where Does Container Insights Fit in Azure Monitor?

**Container Insights** is the container/Kubernetes monitoring experience within Azure Monitor, providing visibility into AKS workloads, performance, and logs per enabled settings. In modern deployments, logs/inventory/performance data are collected by **Azure Monitor Agent (AMA)** and routed via a **Data Collection Rule (DCR)** to the target **Log Analytics workspace**.

```text
AKS cluster
├── Nodes / kubelet / container runtime
│     └── container stdout/stderr
├── Kubernetes API
│     └── Pod, node, workload metadata, and events per configuration
└── Azure Monitor Agent (ama-logs)
       │
       │ Collects selected streams
       ▼
   Data Collection Rule (DCR)
       │
       │ Selects sources/streams, scope, destination; transformations if supported
       ▼
   Log Analytics workspace
       ├── ContainerLogV2
       ├── KubePodInventory / KubeNodeInventory / KubeEvents
       ├── Perf / InsightsMetrics (when collected)
       └── Other tables depending on config and version
             │
             ├── Azure Portal: Container Insights
             ├── KQL / Workbooks
             └── Log search alerts
```

This is a logical model. In practice, agent DaemonSet/Deployment names, DCRs, schemas, and populated tables vary by deployment type, collection settings, and service version. A missing table in the workspace **does not automatically mean data loss**: that stream might not be enabled, no events occurred, or data goes elsewhere.

### 2.1. Role of Each Component

| Component | Role | What to Verify |
|---|---|---|
| **Azure Monitor Agent** | Collects container/Kubernetes telemetry per config | Agent is running and can reach ingest endpoints |
| **Data Collection Rule** | Defines sources/streams and destination of collected data | Linked to the right AKS cluster, right streams/namespaces/settings |
| **Log Analytics workspace** | Stores and queries logs/inventory/metrics in tables | Right subscription/tenant, permissions, retention, and billing |
| **Container Insights** | Displays cluster/nodes/controllers/containers views and logs | Viewing the right cluster, time range, and workspace |
| **Azure Monitor alerts / Workbooks** | Alerts on and visualizes collected data | Thresholds, scopes, evaluation windows, and read permissions |

**Never confuse a Log Analytics workspace with where the application runs.** It stores telemetry, not container images or business databases. When multiple AKS clusters send data to one shared workspace, always filter by **`ClusterName`/cluster identity** and namespace in queries and dashboards to avoid mixing dev and prod.

### 2.2. What Does the DCR Do?

A DCR specifies which data goes to which destination and may support filtering/transformations depending on data source type. For Container Insights, settings typically govern:

- Collecting container stdout/stderr via **`ContainerLogV2`**.
- Collecting inventory, Kubernetes events, or agent-supported performance metrics.
- Choosing collection modes/presets supported by the service, such as namespace or log stream filtering.
- Ingestion-time transformations where supported by the stream/table and deployment type.

**Never manually edit a DCR managed by AKS/Container Insights without understanding the add-on's lifecycle.** Manual edits can be overwritten by platform reconciliation or break cluster-wide collection. Configure via supported APIs/Portal/IaC for Container Insights, then verify live ingestion.

## 3. Distinguishing Four Easily Confused Observability Systems

Azure Monitor offers multiple telemetry pipelines. They complement each other rather than sharing one master switch for every signal.

| Tool / Feature | Primary Data | Typical Query Surface |
|---|---|---|
| **Container Insights** | Container stdout/stderr, Kubernetes inventory/events, configured performance signals | Azure Portal / Log Analytics **KQL** and Container Insights UI |
| **Azure Monitor Metrics** | Platform/resource metrics or feature-collected metrics | Metrics Explorer, metric alerts, metrics API |
| **Azure Monitor managed service for Prometheus** | Prometheus-format metrics scraped per config from cluster/workloads | **Azure Monitor workspace**, **PromQL**, Azure Managed Grafana, or supported dashboards |
| **Application Insights / OpenTelemetry** | Request/dependency traces, exceptions, application telemetry | Application Insights, KQL on matching workspace, APM views |

For example: to read a `NullPointerException` printed to pod stderr, start in **`ContainerLogV2`**. To measure `container_cpu_usage_seconds_total` and calculate `rate(...)` in **PromQL**, you need the **managed Prometheus** pipeline or a compatible Prometheus stack—never expect raw Prometheus series to automatically appear in `ContainerLogV2`.

### 3.1. Log Analytics Workspaces and Azure Monitor Workspaces Are Different

- **Log Analytics workspace (LAW):** stores tabular log data queried with **Kusto Query Language (KQL)**.
- **Azure Monitor workspace (AMW):** stores Prometheus metrics for **Azure Monitor managed service for Prometheus** per supported model, queried with **PromQL**.

These two workspaces are **two distinct Azure resource types**. An application can use both if you want detailed Kubernetes logs and Prometheus metrics. Never point KQL queries at an Azure Monitor workspace expecting to find `ContainerLogV2`.

### 3.2. Control-Plane Logs Must Be Enabled Separately

Container Insights captures many pod/node and Kubernetes signals, yet **AKS control-plane resource/diagnostic logs** (such as API Server, audit, or scheduler categories where supported) must be configured separately via **Azure Monitor diagnostic settings** on the AKS resource. Enabling Container Insights does not automatically capture full Kubernetes audit logs.

When investigating who created/deleted Kubernetes resources, cluster admin actions, or control-plane events, verify enabled diagnostic categories, destination workspace, retention, and read RBAC. Audit logs can contain sensitive info; govern access and costs carefully.

## 4. Essential Log Analytics Tables to Know

When Container Insights is configured and data reaches the Log Analytics workspace, these tables are commonly useful:

| Table | Typical Contents | Use Case |
|---|---|---|
| **`ContainerLogV2`** | Container stdout/stderr log lines, pod/container metadata, timestamps | Debug app errors, filter by namespace/pod |
| **`KubePodInventory`** | Collected pod, container, status, and metadata records | Check which pods exist or are in error states |
| **`KubeNodeInventory`** | Node inventory and related statuses | Correlate pod errors with node state |
| **`KubeEvents`** | Kubernetes events captured by the agent | `FailedScheduling`, `BackOff`, `Unhealthy`, and other events |
| **`Perf`** | Collected performance counters | Inspect CPU, memory, or node/container counters |
| **`InsightsMetrics`** | Agent-emitted metric records per configuration | Analyze available performance trends |

Exact table and column names can vary by pipeline, DCR configuration, Container Insights version, and legacy vs resource-specific table modes. Where legacy **`ContainerLog`** data still exists, adjust KQL accordingly; this lesson prioritizes **`ContainerLogV2`** for modern container logging.

**Data not automatically captured in full:**

- Application logs written only to files inside the container filesystem instead of stdout/stderr without custom collector configs.
- Request tracing and dependency spans for uninstrumented apps.
- Custom Prometheus metrics without scrapers, target endpoints, and scrape rules enabled.
- AKS audit/control-plane categories without diagnostic settings enabled.
- Historical data from before monitoring was enabled or past retention expiry.

## 5. Designing Telemetry Before Enabling Collectors

Before turning on Container Insights on a production cluster, define clear observability goals:

| Scenario | Signals Needed | Query / View |
|---|---|---|
| API returns 500 | Application error logs and request telemetry | KQL `ContainerLogV2` + App Insights |
| Pod restarting repeatedly | Pod/container status, Kubernetes events | Inventory, events, restart metrics |
| Pod `OOMKilled` | Pod termination reason, memory usage and limit | `kubectl describe`, inventory/performance, metrics |
| Node out of CPU | Node CPU, scheduling latency, pending pods | Metrics/Prometheus + Kubernetes events |
| New deployment failing | Deployment timeline, pod logs/events | `kubectl`, Container Insights / KQL |
| No logs after deploy | Collector health, stdout/stderr, DCR, ingestion | Agent/stream/workspace and log producer |
| Rising costs | Per-table ingestion, lines/s, retention | Azure Monitor usage/cost and workspace billing |

Good design asks questions **that collected data can actually answer**, rather than turning on every category just to stare at crowded dashboards. Every log/metric stream should have an owner, purpose, retention window, and sensitivity classification.

### 5.1. Identifiers for Multi-Environment Filtering

At minimum, every dashboard and query should distinguish:

- AKS cluster and Azure subscription/resource group.
- Namespace, workload/Deployment, and container name.
- Pod/node and incident timestamp.
- Environment (`dev`, `test`, `prod`) via resource mappings/tags or equivalent metadata.
- Application version/revision or deployment timestamp when included in logs/telemetry.

Pod names include random suffixes that change on every rollout. To keep dashboards durable, filter by **namespace, Deployment/workload, or labels** where supported rather than pinning a single transient pod name.

## 6. Enabling Container Insights for AKS

The hands-on steps use **Azure CLI in Bash / Azure Cloud Shell**—do not run them against production without checking existing monitoring configs first. An AKS cluster may already send Container Insights data to a platform team's central workspace. **Never swap workspaces or DCRs just to run a lab**, as that can break live dashboards and alerts.

### 6.1. Prerequisites to Prepare

1. Active AKS cluster, with user holding read access plus appropriate permissions to enable the add-on.
2. Log Analytics workspace in the tenant/subscription (or Azure-supported model) with link/write permissions.
3. Cluster/nodes have **outbound DNS, HTTPS, and routing** to required Azure Monitor endpoints per network design; private endpoints or Azure Monitor Private Link Scopes have separate prerequisites.
4. Region, features, organizational policy, and AKS/agent version support the chosen collection flow.
5. Operations team agreed on logs/metrics scope, retention, data residency, budget, and query RBAC.
6. Required Kubernetes RBAC to inspect agent status, pods, and namespaces if checking via `kubectl`.

Never grant subscription-wide `Owner` to every operator merely to read logs. Separate rights to **enable add-ons/manage resources**, **query workspaces**, and **read the Kubernetes API**.

### 6.2. Inspect Cluster and Subscription

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

AKS_RG="rg-aks-operations-dev"
AKS_NAME="aks-orders-dev"
MON_RG="rg-monitoring-dev"
LOCATION="southeastasia"
LAW="law-aks-orders-dev"

az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{name:name,id:id,location:location,monitoring:addonProfiles.omsagent}" \
  --output json
```

`addonProfiles.omsagent` is a field name **retained for backward compatibility** in certain AKS APIs/CLIs; it does not mean current deployments run the legacy agent instead of **Azure Monitor Agent**. To confirm the real collection path, inspect the add-on, DCR, and running agent resources.

### 6.3. Create or Select a Log Analytics Workspace

In an isolated lab environment, you can create a workspace:

```bash
az monitor log-analytics workspace create \
  --resource-group "$MON_RG" \
  --workspace-name "$LAW" \
  --location "$LOCATION"

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$MON_RG" \
  --workspace-name "$LAW" \
  --query id --output tsv)

az monitor log-analytics workspace show \
  --resource-group "$MON_RG" \
  --workspace-name "$LAW" \
  --query "{name:name,id:id,location:location,retentionInDays:retentionInDays}" \
  --output json
```

This assumes `MON_RG` already exists. If your organization uses a centralized workspace with scoped RBAC, use the **governed workspace Resource ID** instead of creating a new one.

Retention and pricing plans vary across Log Analytics tiers and table plans. Before collecting production logs, review retention and data sensitivity policies rather than leaving defaults unexamined.

### 6.4. Enable the Monitoring Add-On

On supported AKS and Azure CLI versions, enabling Container Insights log collection uses a command such as:

```bash
az aks enable-addons \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --addons monitoring \
  --workspace-resource-id "$LAW_ID"
```

This command illustrates **enabling Container Insights** via the add-on path; it does not automatically enable **managed Prometheus**. In newer API/CLI versions, managed identity authentication or data collection preset flags may offer additional options—check Portal or syntax supported by your live cluster/CLI. Before running, verify whether the add-on is already enabled and pointing elsewhere to prevent unintended changes.

Verify:

```bash
az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "addonProfiles.omsagent" \
  --output json
```

Seeing the add-on `enabled` does not prove data is arriving in the workspace yet. Verify **agent health, DCR association, and live KQL data** in the next steps.

### 6.5. Enabling via Azure Portal

In the Azure Portal, navigate to **AKS → Insights** (or the equivalent **Monitoring/Insights** blade), select Container Insights settings, target Log Analytics workspace, and supported data collection/cost presets. After reviewing created/modified resources, apply and verify the DCR, collection streams, and workspace.

**Important:** the same "Monitoring" configuration pane may present switches for **Container Insights logs**, **Prometheus metrics**, and **Grafana**. Record clearly what was enabled; never report "all metrics and traces are enabled" just because Insights shows container data.

## 7. Verifying the Collection Pipeline from Node to Workspace

There is always ingestion latency between a container writing a log line and that line appearing in Log Analytics. Immediately after enabling, allow provisioning, agent startup, and ingestion to complete before concluding data is missing.

### 7.1. Check Nodes, Pods, and Agents with `kubectl`

```bash
az aks get-credentials \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME"

kubectl config current-context
kubectl get nodes -o wide
kubectl get pods --all-namespaces

# Agent names depend on version/configuration; do not assume fixed names.
kubectl get daemonsets -n kube-system
kubectl get deployments -n kube-system
```

In AMA Container Insights setups, you will typically see resources/pods named similarly to **`ama-logs`**. `omsagent` appears in older clusters/docs. Inspect the actual objects returned by `kubectl get` rather than guessing non-existent sample pod names.

If agent pods are in `CrashLoopBackOff`, Pending, or missing from target nodes, inspect `kubectl describe`, Kubernetes events, agent container logs, and node/taint/network constraints per runbooks. **Never delete the agent DaemonSet or DCR blindly.**

### 7.2. Generate Logs from a Test Application

In a lab environment with an active `orders-api` Deployment:

```bash
kubectl logs -n orders deployment/orders-api \
  --all-containers=true \
  --since=15m \
  --tail=100
```

`kubectl logs` verifies that **logs exist in Kubernetes / the container runtime**. It does not require Log Analytics and does not prove Container Insights ingested those lines.

If `kubectl logs` is empty, verify the app writes to **stdout/stderr**, emitted logs in that window, and pods started properly. If `kubectl logs` shows logs yet Log Analytics does not, investigate **agent → DCR → workspace**.

### 7.3. Verify the Workspace Using KQL

Open the target Log Analytics workspace → **Logs**, select roughly the last 1 hour, and run:

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| summarize LogLines=count() by PodNamespace
| order by LogLines desc
```

If data flows, this returns line counts per namespace. If empty, do not jump straight to blaming a broken agent: there may simply be no logs in that time window, the DCR might exclude that stream, the table may not be initialized yet, or data may be flowing to another workspace.

### 7.4. Inspect the Data Collection Rule and Destination

In the Azure Portal, inspect **Data Collection Rules** / associations linked to AKS and confirm:

- The DCR links to the exact AKS resource and is healthy.
- Enabled streams include the expected data types.
- The destination Log Analytics workspace matches the workspace you are querying.
- Namespace filters, log-level filters, collection presets, or transformations are not dropping the logs.
- Agents hold required permissions and network connectivity to ingest endpoints.

Some setups apply DCR transformations or log filtering at ingestion time. Data dropped prior to ingestion **cannot be recovered by changing KQL**; update the config and emit new test logs.

## 8. Writing Application Logs for Effective Container Insights Collection

Container Insights generally collects **container stdout/stderr** via the configured agent. Applications should use a logging framework emitting structured events with appropriate severity and context. Avoid writing separate log files inside pod filesystems by default.

### 8.1. Structured Logging

A better format than a hard-to-search plain line like `Payment failed`:

```json
{
  "timestamp": "2026-11-20T07:05:21Z",
  "level": "ERROR",
  "service": "orders-api",
  "operation": "charge",
  "traceId": "d61c2e9f08f04bdc",
  "durationMs": 3000,
  "status": "UPSTREAM_TIMEOUT",
  "message": "Payment provider did not respond within the deadline"
}
```

In the example above, **never log** payment cards, secrets, API tokens, or full customer payloads. To correlate transactions, use **internal IDs designed not to expose sensitive data**, paired with proper log access governance.

### 8.2. Log Levels and Sampling Strategy

| Level | Purpose | Risk If Misused |
|---|---|---|
| `DEBUG` | Detailed logic debugging, usually enabled temporarily | High ingestion cost, risk of leaking internal data |
| `INFO` | Lifecycle events and selective business milestones | Extremely noisy if logged per request unbounded |
| `WARN` | Abnormal conditions that have not necessarily failed | False alerts if warnings fire nonstop unclassified |
| `ERROR` | Failed operations needing investigation or action | Missed failures if exceptions are swallowed silently |

For high-traffic services, avoid logging `INFO` for every step inside every request. Use **sampling in appropriate instrumentation**, log significant events, and rely on metrics for aggregate counts. Before trimming logs, verify enough evidence remains to investigate severe incidents.

### 8.3. Java Logging Example

Spring Boot/Java apps can use SLF4J configured to log to console:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderProcessor {
    private static final Logger log =
            LoggerFactory.getLogger(OrderProcessor.class);

    public void process(String operationId) {
        log.info("Order processing started: operationId={}", operationId);
        try {
            // Execute business logic and call backend per application policy.
            log.info("Order processing completed: operationId={}", operationId);
        } catch (RuntimeException ex) {
            log.error("Order processing failed: operationId={}", operationId, ex);
            throw ex;
        }
    }
}
```

This illustrates SLF4J usage and requires a compatible runtime logging implementation. To emit structured JSON rather than plain text, configure the logging framework's appender/encoder accordingly. Never pass unapproved PII inside `operationId`, and ensure exception messages never embed secrets.

### 8.4. Timestamps and Trace Correlation

- Prefer **UTC** in logs and dashboards to correlate across regions.
- Include `traceId` or correlation IDs to link container logs with Application Insights/OpenTelemetry traces.
- Emit deployment/build version in app metadata where supported to distinguish pre- vs post-rollout failures.
- When pods are recreated, pivot on namespace/workload/trace ID rather than relying solely on pod name.
- Verify node clock synchronization and timestamp parsing; clock skew produces misleading timelines.

## 9. KQL Queries: Finding Namespace and Pod Logs

These examples run against a **Log Analytics workspace** holding `ContainerLogV2` data. Adjust namespace, pod prefix, and time windows for your live environment. When multiple clusters share one workspace, add a `ClusterName` or cluster-identity filter once exact column names and values are verified.

### 9.1. View the Latest 100 API Log Lines

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| project TimeGenerated, PodNamespace, PodName,
          ContainerName, LogLevel, Message=tostring(LogMessage)
| order by TimeGenerated desc
| take 100
```

This query matches pods starting with `orders-api`, common for Deployment-managed pods though not mandatory for all workloads. Interpret `LogLevel` carefully: agents may not accurately infer `LogLevel` from arbitrary plain-text lines.

### 9.2. Search Errors by Content

```kusto
ContainerLogV2
| where TimeGenerated > ago(30m)
| where PodNamespace == "orders"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| project TimeGenerated, PodName, ContainerName, Message
| order by TimeGenerated desc
```

Keyword search is a preliminary triage step. `ERROR` might appear inside an informational message, while JSON errors might store `level` in another field. For structured JSON logs, use `parse_json` once you verify the exact format preserved by the collector.

### 9.3. Count Error Lines in 5-Minute Buckets

```kusto
ContainerLogV2
| where TimeGenerated > ago(2h)
| where PodNamespace == "orders"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| summarize ErrorLines=count() by bin(TimeGenerated, 5m), PodNamespace
| order by TimeGenerated asc
```

**`ErrorLines` does not equal HTTP 500 count**: a single failed request might log five lines or zero lines, and background jobs may emit unrelated errors. To measure **API error rate**, use properly instrumented HTTP request telemetry/metrics, then use container logs for root-cause analysis.

### 9.4. Inspect Live Schema When a Query Fails

If the workspace reports missing columns or tables:

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| take 5
```

Inspect available columns, dataset/time range, and permissions. If `ContainerLogV2` does not exist, inspect DCR streams, ingestion health, and whether legacy log tables are configured. Never "fix" a query by guessing imaginary column names.

## 10. KQL: Inspecting Pods, Nodes, Events, and Performance Counters

A single log line saying "process terminated" does not tell you whether a pod was OOMKilled, replaced by a rollout, or exited cleanly. **Kubernetes inventory, events, and metrics** provide that context. The queries below assume those tables are being collected.

### 10.1. View Latest Pod Statuses

```kusto
KubePodInventory
| where TimeGenerated > ago(30m)
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| summarize Pods=count()
    by ClusterName, Namespace, PodStatus
| order by Pods desc
```

`arg_max` picks the **most recent record within the query window** for each cluster/namespace/pod tuple; it does not replace real-time checks with `kubectl get pods`. Inventory ingestion can lag or retain pods deleted since the last snapshot. When in doubt, check the Kubernetes API directly.

To inspect individual pods:

```kusto
KubePodInventory
| where TimeGenerated > ago(30m)
| where Namespace == "orders"
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| project ClusterName, Namespace, Name, PodStatus, TimeGenerated
| order by TimeGenerated desc
```

### 10.2. Inspect Kubernetes Events

```kusto
KubeEvents
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 50
```

This exploratory query keeps all columns so you can inspect the available schema. In workspaces containing columns like `Reason`, `Namespace`, or `Message`, filter for `FailedScheduling`, `BackOff`, or `Unhealthy`.

Compare directly against Kubernetes:

```bash
kubectl get events -n orders --sort-by=.metadata.creationTimestamp
kubectl describe pod <actual-pod-name> -n orders
```

Kubernetes events are not stored forever in-cluster; they have short TTLs. Log Analytics only holds events captured by the collector while that stream was active and within retention. Never expect last week's events to still appear in `kubectl get events`.

### 10.3. Explore Performance Counters

Before hardcoding counter names, discover which metrics exist in `Perf`:

```kusto
Perf
| where TimeGenerated > ago(1h)
| summarize Samples=count() by ObjectName, CounterName
| top 30 by Samples desc
```

Container Insights setups may emit CPU counters in nanocores. **Only run counter-specific queries after confirming `ObjectName`/`CounterName` exist and verifying their units.** Example counter exploration:

```kusto
Perf
| where TimeGenerated > ago(1h)
| where ObjectName == "K8SContainer"
| where CounterName == "cpuUsageNanoCores"
| extend Cores=CounterValue / 1000000000.0
| summarize AvgCores=avg(Cores)
    by bin(TimeGenerated, 5m), InstanceName
| order by TimeGenerated asc
```

`cpuUsageNanoCores` and `K8SContainer` are common names, **not guaranteed schemas in every workspace**. If empty, return to the discovery query, inspect collection configs, and check the performance experience. When averaging samples, verify whether sampling intervals are uniform.

### 10.4. Explore `InsightsMetrics`

```kusto
InsightsMetrics
| where TimeGenerated > ago(1h)
| summarize Samples=count() by Namespace, Name
| top 30 by Samples desc
```

`InsightsMetrics` holds performance records keyed by namespace/name; available metrics depend on collector configuration. Before building KPI dashboards, confirm **units**, dimensions, sampling cadence, and whether values are gauges or counters.

### 10.5. Correlating Log Timestamps with Restarts

Suppose `orders-api` errors spike at 14:05 and a pod restarts around 14:06. Investigation sequence:

1. Query `ContainerLogV2` for `orders-api` between 14:00–14:10 UTC.
2. Check `KubePodInventory` or events for pods/containers changing state.
3. Run `kubectl describe pod` for `Last State`, `Reason`, `Exit Code`, and liveness/readiness probes if the pod still exists.
4. Check performance metrics or managed Prometheus for CPU/memory trends prior to the restart.
5. Cross-check deployment/config change timestamps; never assume the restart was the root cause—it may be a **symptom** of an application bug.

A pod showing `Running` at 14:10 does not prove it never crashed between 14:00 and 14:10. Always check **restart counts/history** and timestamped events.

## 11. Metrics: Scope of Container Insights vs Managed Prometheus

### 11.1. Metrics from Container Insights

Container Insights surfaces cluster/node/controller/container performance from collected data. Keep in mind CPU/memory numbers may represent:

- **Absolute usage:** CPU cores, nanocores, memory bytes.
- **Relative usage:** CPU/memory usage vs capacity, allocatable, request, or limit.
- **Time semantics:** instantaneous sample, window average, or rate.

For instance, a container using `0.5 CPU core` against a `0.25 core` request simply means usage exceeds its request; you cannot conclude CPU throttling without checking its CPU limit and throttling metrics. Likewise, a container using `450 MiB` under a `512 MiB` limit is not automatically `OOMKilled` unless container state/events confirm it.

### 11.2. Azure Monitor Managed Service for Prometheus

For Prometheus-format metrics, Azure provides **managed service for Prometheus** depending on AKS/region availability, storing series in an **Azure Monitor workspace**. Visualization commonly pairs with **Azure Managed Grafana** or compatible dashboards.

Conceptual architecture:

```text
AKS nodes / pods / kube-state-metrics / Prometheus exporters
       |
       | Prometheus scrape targets + scrape configuration
       v
Azure Monitor metrics collection agent
       |
       v
Azure Monitor workspace (Prometheus)
       |
       +-- PromQL
       +-- Grafana dashboards
       +-- Prometheus rules / alerts when configured and supported
```

This pipeline is **distinct** from Log Analytics workspaces and `ContainerLogV2`. Enabling Prometheus scraping does not send stdout/stderr to Log Analytics, and enabling Container Insights does not scrape arbitrary custom exporters.

### 11.3. PromQL Examples

When runtime container CPU metrics are present in your Azure Monitor workspace:

```promql
sum by (namespace) (
  rate(container_cpu_usage_seconds_total{container!="", container!="POD"}[5m])
)
```

Because `container_cpu_usage_seconds_total` is a **counter**, `rate(...[5m])` computes CPU-seconds per second over a five-minute window, commonly interpreted as CPU cores when instrumentation matches. Labels like `namespace`, `pod`, and `container` depend on scrape configs and exporter versions.

Example query for `Pending` pods when `kube-state-metrics` is available:

```promql
sum by (namespace) (
  kube_pod_status_phase{phase="Pending"}
)
```

These are **PromQL** queries—they do not run in the Log Analytics KQL editor. If no data appears, check the workspace, scrape targets, default targets, custom scrape configs, and label names rather than assuming syntax errors.

### 11.4. Choosing the Right Metric Pipeline

| Question | Approach |
|---|---|
| Quick view of CPU/memory, container states, and logs inside AKS Insights | Container Insights with matching streams/config |
| Query Prometheus metrics with PromQL or power Grafana dashboards | Managed Prometheus + Azure Monitor workspace |
| HTTP request/error metrics for a Java API | OpenTelemetry/Prometheus instrumentation or Application Insights per team standards |
| Azure resource metrics outside Kubernetes | Azure Monitor Metrics / diagnostics on the target resource |
| Correlate Kubernetes logs and Prometheus metrics during one incident | Combine KQL and PromQL on a shared UTC timeline rather than expecting identical tables |

When building greenfield observability, teams often use **Container Insights for logs/inventory** and **managed Prometheus for metrics**. Avoid running two redundant collectors scraping the same data just to multiply charts; evaluate duplicate ingestion, cost, and semantic differences.

## 12. Actionable Dashboards, Workbooks, and Alerts

### 12.1. Minimum Viable AKS Dashboard

An effective on-call dashboard covers:

| Group | Signals Displayed | Why |
|---|---|---|
| **Availability** | Ready/Desired replicas, pending pods, NotReady nodes | Detect capacity shortfalls or scheduling errors |
| **Reliability** | Restart count, `OOMKilled`, probe failures | Detect unstable containers |
| **Performance** | CPU/memory usage, pressure, throttling if collected | Predict saturation |
| **Application** | Request rate, error rate, p95/p99 latency | Measure user experience |
| **Diagnostics** | `ERROR` logs by namespace/workload, Kubernetes events | Investigate root causes |
| **Change correlation** | Deployment timestamps, config changes, autoscale events | Pinpoint triggering changes |
| **Cost** | Ingestion volume, retention, metric cardinality | Govern observability budgets |

Do not lump every namespace into one unfilterable chart when separate teams own distinct boundaries. Provide filters for cluster, namespace, workload, environment, and time window.

### 12.2. Log Search Alert from `ContainerLogV2`

Sample KQL for a **scheduled query alert** counting error lines over 10 minutes:

```kusto
ContainerLogV2
| where TimeGenerated > ago(10m)
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| summarize ErrorLines=count()
```

In Azure Monitor, configure a **log search alert** scoped to the right Log Analytics workspace with evaluation cadence, threshold, action group, and severity per policy. Set thresholds from measured baseline traffic rather than picking one arbitrary number for every service.

**Do not label this an exact HTTP 5xx alert.** Since log lines may not map 1:1 to failed HTTP requests, SLO alerts should rely on instrumented **HTTP server request metrics or application telemetry**.

### 12.3. Metric Alerts and Prometheus Alerts

Metric alerts suit telemetry with crisp numeric semantics—CPU usage, node availability, pod restarts, or latency—depending on data source and Azure Monitor / managed Prometheus support. Every alert must define:

1. **Signal:** what is measured, in what unit, from which source?
2. **Scope:** which AKS cluster/namespace/app?
3. **Condition:** threshold breach duration or deviation from baseline?
4. **Evaluation:** evaluation frequency, window, and missing-data handling.
5. **Action:** which on-call rotation, incident tool, or automation receives it?
6. **Runbook:** verification and remediation steps to cut time-to-mitigate.

For multi-replica apps, avoid paging just because **one** container had a brief CPU spike with zero system impact. Conversely, do not wait until every replica dies before alerting. Tune thresholds to SLOs, traffic, and workload behavior.

### 12.4. Standard Alert Runbook

Example for alert `orders-api ERROR lines surge`:

1. Record UTC timestamp, cluster, namespace, and alert scope.
2. Check application p95 latency and HTTP 5xx rate.
3. Open KQL `ContainerLogV2` covering ±10 minutes.
4. Inspect restarts, pod events, and node pressure.
5. Check dependency traces or diagnostic logs for database/payment APIs.
6. Cross-check recent deployments and config changes.
7. Pick remediation: rollback, scale, fix backend, or repair secret/network.
8. Document the incident timeline and tune the alert if it caused noise.

An alert with no owner, runbook, or clear action becomes **alert fatigue**, even if its KQL syntax is flawless.

## 13. Diagnosing Missing Logs or Metrics

If logs do not appear in Container Insights, **do not blindly turn on every logging category or open all outbound traffic**. A telemetry pipeline has multiple links; pinpoint the first broken link.

### 13.1. Missing-Log Investigation Flow

```text
Is the application emitting logs?
       |
       +-- No -> fix app logging / stdout / stderr
       |
       v
Does kubectl logs show them?
       |
       +-- No -> inspect pod/container, time range, log producer
       |
       v
Is Azure Monitor Agent running?
       |
       +-- No -> inspect DaemonSet, nodes, agent logs/events
       |
       v
Does DCR collect ContainerLogV2 and target the right LAW?
       |
       +-- No -> check streams, filtering, association, destination
       |
       v
Can the agent reach ingest endpoints?
       |
       +-- No -> DNS, routing, firewall, Private Link, identity/permissions
       |
       v
Is KQL using the right workspace, table, time range, cluster/namespace?
       |
       +-- No -> fix query and read RBAC
       |
       v
Logs arrive -> check ingestion latency and standardize dashboards
```

### 13.2. Common Symptoms and Causes

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `kubectl logs` is empty | App logs to a file, nothing written to stdout, wrong container, or quiet window | Check app config, exact pod/container, `--previous` on restarts |
| `kubectl logs` works yet `ContainerLogV2` is empty | Add-on/agent/DCR/workspace issue or collector filtering | Check add-on, agent, DCR streams, LAW destination |
| Only one namespace missing logs | Namespace filter, collection preset, or silent namespace | Inspect DCR filters and query filters |
| Only old logs appear | Collector stopped, network blocked, querying wrong workspace | Check latest record timestamp, agent health, network |
| `ContainerLogV2` table missing | Stream not ingested yet, not enabled, wrong workspace, or legacy schema | Discover tables in workspace, inspect DCR and ingestion |
| Logs exist yet JSON fields not parsed | JSON stored as text/dynamic inside `LogMessage` | Use `tostring`/`parse_json` and verify schema |
| No Kubernetes events | Stream disabled, no events in window, or retention expired | `kubectl get events`, `KubeEvents` table, DCR |
| CPU metrics missing while logs exist | Performance stream disabled or managed Prometheus confused with LAW | DCR/AMA perf streams, AMW/scrape configs |
| PromQL returns no data | Managed Prometheus not enabled, targets unscraped, or wrong labels | AMW, collector, scrape targets, metric discovery |
| Some nodes lack telemetry | Agent not scheduled on node (taints/OS/arch/pressure) or network differs | DaemonSet scheduling, node events, agent logs |
| Logs appear delayed | Ingestion latency, pipeline backlog, overly narrow query window | `TimeGenerated`, ingestion time, workspace health |
| Cannot view Logs in Portal | User lacks workspace query RBAC or wrong scope | Azure RBAC, workspace access mode, subscription/tenant |

To compare **ingestion time** against event time, KQL provides `ingestion_time()` where supported by the table and data:

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| extend IngestedAt=ingestion_time()
| where isnotnull(IngestedAt)
| extend LagSeconds=datetime_diff("second", IngestedAt, TimeGenerated)
| summarize AvgLagSeconds=avg(LagSeconds),
            P95LagSeconds=percentile(LagSeconds, 95)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

This is a rough measurement of **event-vs-ingestion timestamp delta**; if `ingestion_time()` is unavailable or clocks drift, account for those caveats before treating it as an official service SLA metric.

### 13.3. Distinguishing `OOMKilled` from Liveness Probe Restarts

A container's restart count rises. Two common causes:

- The container exceeded its memory limit and was killed with reason `OOMKilled`.
- Liveness probes failed consecutively, causing kubelet to restart the container.

You cannot distinguish these from `restart count` alone. Inspect:

```bash
kubectl get pods -n orders -o wide
kubectl describe pod <actual-pod-name> -n orders

# If the container restarted and previous logs are still retained by the runtime:
kubectl logs <actual-pod-name> \
  -n orders \
  --previous \
  --tail=100
```

If previous logs rotated away or the pod was deleted, Container Insights can supply historical records **provided the agent collected them and retention has not expired**. Never treat missing historical logs as proof a container never restarted.

### 13.4. Investigating Errors After a Rollout

Suppose `orders-api` deployed version `2.1.0` at 14:00 and errors began at 14:05:

1. Check Pods/ReplicaSets/revisions and Kubernetes events.
2. Compare KQL logs before and after 14:00 using consistent UTC timestamps.
3. Inspect CPU/memory/restarts/Pending pods.
4. Compare request error rate and dependency duration.
5. Check whether secrets, images, resource limits, readiness probes, or network policies changed.
6. If errors correlate strictly with the new release, consider rolling back per runbooks rather than immediately blaming AKS infrastructure.

## 14. Securing Observability Data and Access Controls

Telemetry can contain sensitive data: internal hostnames, IP addresses, user IDs, request details, resource names, and even credentials if an app logs improperly. A shared multi-team Log Analytics workspace becomes a **high-value data store that must be protected**.

### 14.1. Protect at the Source

- Never log passwords, API keys, Entra access tokens, Kubernetes ServiceAccount JWTs, connection strings, or private certificates.
- Do not dump raw request/response bodies containing customer data to stdout/stderr by default.
- Redact sensitive headers such as `Authorization`, `Cookie`, and session IDs.
- Use correlation IDs designed to satisfy privacy and retention requirements.
- Keep log levels stricter in prod than dev; `DEBUG` must have an owner and expiration.
- Audit logging libraries, exception handlers, and HTTP middleware so they never accidentally dump secrets.

Ingestion-time transformations can strip certain fields where technically supported, yet **should never be your sole defense against secret leaks**. Once a token leaves the app to a collector/buffer, it may already touch multiple surfaces. Prevent leaks inside the application first.

### 14.2. Separating Telemetry Read and Write Permissions

Separate:

| Principal | Permissions Scope to Consider |
|---|---|
| **Platform team** | Manage add-ons, DCRs, agent configuration, and networking |
| **Application / SRE** | Query logs and dashboards for assigned workloads |
| **Security / Compliance** | Audit data and configuration changes per policy |
| **CI/CD identity** | Apply approved infra/collector changes without default read access to all logs |
| **Business stakeholders** | View high-level dashboards if needed, without arbitrary raw log queries |

Design Log Analytics Azure RBAC, workspace access control, and data isolation within actual service capabilities. **A single shared workspace does not automatically create namespace-level security boundaries** across all tables/logs. For strict access or residency boundaries, consider separate workspaces aligned with system/data boundaries.

### 14.3. Data Retention, Residency, and Incident Forensics

Before enabling production logging:

1. Confirm workspace region and data residency requirements.
2. Classify logs that may contain PII or security-sensitive data.
3. Choose retention aligned with operational/audit needs and table/tier capabilities.
4. Configure query and export permissions appropriately.
5. Document data-privacy workflows and incident response if a secret leaks into logs.

Never assume "longer retention is always better." Infinite retention inflates cost and breach exposure. Conversely, overly short retention leaves investigations blind a few days after an incident.

### 14.4. Securing the Telemetry Transport Path

Agents require network reachability to Azure Monitor ingestion endpoints for the chosen cloud/region. In private AKS clusters or restricted egress topologies:

- Verify DNS resolution and routing to required endpoints.
- Check Azure Firewall/NSG/UDRs, proxies, and supported allowlists.
- If using Azure Monitor Private Link Scope, plan private endpoints and private DNS cleanly.
- Verify agent/managed identity permissions and resource associations.
- Avoid opening unrestricted outbound Internet when only a specific DNS/route rule is missing.

A **private AKS cluster** does not automatically route all telemetry through private endpoints. Verify the live telemetry path and Azure Monitor prerequisites explicitly.

## 15. Managing Container Insights Costs

Good observability needs enough data to debug incidents, yet you cannot log every detail at high verbosity indefinitely without budget control.

### 15.1. Primary Cost Drivers

| Item | What Drives Cost Up? | How to Control |
|---|---|---|
| **Log ingestion** | Heavy `INFO`/`DEBUG` volume, per-request logging, noisy namespaces | Tune log levels, sampling, stream/namespace filtering |
| **Log retention** | Keeping verbose logs for months or years | Per-table retention matched to investigation needs |
| **Managed Prometheus** | Many scrape targets/series, high-cardinality labels | Tune scrape configs, allowlists, drop unused labels |
| **Dashboards / queries / alerts** | Heavy scheduled queries or overly frequent alert evaluations per pricing | Optimize KQL, evaluation frequency, and windows |
| **Log Analytics / Monitor services** | Workspace tier, add-on features, data exports | Choose fitting plans and review current pricing |
| **Networking** | Private endpoints, egress, or intermediate network appliances | Clean routing, review total TCO |

Most of these costs **scale with ingested/stored bytes and active features, not line counts in source code**. When 100 replicas emit per-request debug logs simultaneously, daily volume can jump 100× over a single instance.

### 15.2. Estimating Log Volume from `ContainerLogV2`

In Log Analytics tables containing `_BilledSize`, estimate ingested volume:

```kusto
ContainerLogV2
| where TimeGenerated > ago(7d)
| summarize ApproxIngestedGiB=sum(_BilledSize) / 1073741824.0
    by PodNamespace
| order by ApproxIngestedGiB desc
```

This is an **estimate from table record sizes**, not an official Azure invoice. Billable/non-billable policies, table plan pricing, retention, region, and ancillary charges can make actual billing differ; check **Azure Cost Management**, Usage data, and resource pricing. If the table or column is absent, verify schema and billing model before modifying the query.

### 15.3. Why Avoid "One Large Log Line per Request"?

Suppose an API handles 200 requests/second and logs an average of 2 KB/request:

```text
200 requests/s × 2 KB ≈ 400 KB/s
400 KB/s × 3600 s ≈ 1.44 GB/hour
1.44 GB/hour × 24 hours ≈ 34.6 GB/day
```

This is a **rough illustrative estimate** in decimal units, excluding metadata/encoding overhead, compression, other logs, and exact billing mechanics. Traffic spikes, retry storms, or `DEBUG` logs multiply volume dramatically. Therefore:

- Use **metrics** for repetitive aggregate counts (RPS, latency, error rate).
- Use **logs** for actionable diagnostic events with context.
- Use **sampled traces** to follow requests across services.
- Enable debug logging only temporarily during incidents, then dial it back.

### 15.4. Filter Data at Collection Config, Not Only in KQL

Running `where PodNamespace == "orders"` in KQL **does not reduce ingestion cost for logs from other namespaces** once all data has already landed in the workspace. To cut real ingestion, adjust **collection streams, namespace filters, transformations, or application log volume** per pipeline capabilities.

Change DCR/filters systematically:

1. Measure log volume and distribution by workload/namespace.
2. Identify high-volume, low-value streams.
3. Trim unnecessary `INFO`/`DEBUG` or non-critical dev namespaces.
4. Confirm `ERROR` logs, mandatory audit logs, and critical investigation signals remain intact.
5. Deploy changes via IaC/supported tooling.
6. Compare ingestion, query coverage, and cost post-change.

Features like **Basic logs, table plans, data collection transformations, or cost presets** carry limits on query syntax, alerting, retention, or eligibility. Never switch table tiers purely for a lower per-GB price without checking query and alert compatibility first.

### 15.5. Prometheus Cardinality

Prometheus time series are uniquely identified by **metric name + label set**. Labels like `pod`, `container`, and `namespace` are useful within reason. Putting **`userId`**, **`requestId`**, or **`orderId`** into metric labels creates a new series per request, exploding cardinality, cost, and query overhead.

Never put per-request identifiers in metric labels. Keep correlation IDs in logs/traces under privacy policies, and measure RPS/latency via histograms/counters with bounded-cardinality dimensions.

## 16. Real-World Scenario: API Returns 500 While Pods Stay Running

### 16.1. Incident Description

Order system layout:

```text
Internet
   |
   v
Ingress / Application Gateway (per architecture)
   |
   v
Service orders-api in namespace orders
   |
   +-- Pod A (node-1)
   +-- Pod B (node-2)
   +-- Pod C (node-2)
   |
   v
Payment API + database
```

At 14:05 UTC, an alert fires for elevated error rate. `kubectl get pods -n orders` shows all three pods `Running`. A new app release went out at 14:00. Operations must distinguish:

- Bug in the new release?
- Database or Payment API timing out?
- Pods restarted/OOMKilled and came back `Running`?
- `node-2` experiencing CPU/RAM saturation?
- Recent network or secret change?

### 16.2. Step 1 – Confirm User Experience

Check **request telemetry / Application Insights** or live HTTP metrics to confirm:

- What did the HTTP 5xx rate rise from and to?
- Did p95/p99 latency spike?
- Are all endpoints failing or only `POST /orders`?
- Is it isolated to production or affecting other environments too?

If only logs exist without HTTP metrics instrumented, investigate logs first—but **never report a fabricated error rate percentage without a true request denominator**.

### 16.3. Step 2 – Inspect Container Logs

```kusto
ContainerLogV2
| where TimeGenerated between (datetime(2026-11-20T14:00:00Z) ..
                               datetime(2026-11-20T14:15:00Z))
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| project TimeGenerated, PodName, ContainerName, Message
| order by TimeGenerated asc
```

Timestamps and strings are practice examples; during live incidents, use the **actual incident UTC window**. Suppose the query reveals all three pods logging `Payment provider timed out` right after the rollout. That is a **symptom** pointing toward a dependency—not yet sufficient proof that the external Payment API itself is broken.

### 16.4. Step 3 – Cross-Check Pods, Events, and Metrics

```bash
kubectl get pods -n orders -o wide
kubectl describe deployment orders-api -n orders
kubectl get events -n orders --sort-by=.metadata.creationTimestamp
```

In Container Insights, check node/container CPU/memory between 13:55–14:15 UTC and inspect restart counts. If `node-2` shows high CPU alongside `Unhealthy` events, suspect node pressure. If node metrics look normal while dependency traces show rising timeouts, investigate network paths and the downstream service.

### 16.5. Step 4 – Correlate Changes and Isolate Root Cause

Compare timeline:

| Time | Hypothetical Event |
|---|---|
| 14:00 | Deployed `orders-api:2.1.0` |
| 14:03 | Request latency climbs |
| 14:05 | `Payment provider timed out` logs appear |
| 14:06 | HTTP 5xx alert fires |
| 14:09 | Partial canary rollback to stable release |
| 14:12 | Error rate drops while backend and network remain unchanged |

If rolling back partially cuts errors proportionally to traffic on the new version, that is strong evidence implicating the release. Still inspect **code paths, retries/circuit breakers, deadlines, and dependency performance** to pinpoint the exact bug.

Never declare root cause from a single chart. **Temporal correlation is not causation.** Runbooks should require corroboration across at least two independent telemetry signals before authorizing production rollbacks.

### 16.6. Step 5 – Post-Incident Review

After recovery:

1. Document the timeline, responders, deployed versions, and recovery time.
2. Evaluate whether alerts fired promptly enough.
3. Identify missing log/trace fields that would speed up future triage.
4. Add regression tests or circuit-breaker/timeout guards if application-caused.
5. Keep temporary debug log increases time-boxed, then revert to control ingestion.
6. Confirm retention covers post-incident forensics without retaining disallowed sensitive data.

## 17. Hands-On Exercises

### Exercise A – Enable Log Collection and Verify

**Environment:** a dev AKS cluster with `orders-api` Deployment and a test Log Analytics workspace.

**Tasks:**

1. Check whether the cluster already has Container Insights enabled.
2. If not, plan enabling the add-on against an authorized workspace.
3. Verify the agent is running, DCR links to the cluster, and destination is correct.
4. View logs from Kubernetes via `kubectl logs`.
5. Query `ContainerLogV2` over the last 30 minutes filtered to namespace `orders`.
6. Explain the difference between "logs exist in Kubernetes" and "logs ingested into Log Analytics."

**Solution guide:** use `az aks show`, inspect `ama-logs` (or active agent resources), verify DCR/LAW, then run KQL. If `kubectl logs` shows output while `ContainerLogV2` is empty, inspect add-on/DCR, identity, and networking before blaming the application.

### Exercise B – Write KQL to Investigate Errors

Suppose 10 `orders-api-*` pods run in namespace `orders`, and an incident occurred in the past 10 minutes.

**Tasks:**

- Write KQL returning up to 100 log lines containing `timeout` or `exception`.
- Group matching error line counts by pod in 5-minute bins.
- Explain why counting error lines does not yield the HTTP 500 rate.
- Explain how to link logs to trace IDs when instrumented.

**Reference solution:**

```kusto
ContainerLogV2
| where TimeGenerated > ago(10m)
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| extend Message=tostring(LogMessage)
| where Message has_any ("timeout", "exception")
| summarize MatchingLines=count()
    by bin(TimeGenerated, 5m), PodName
| order by TimeGenerated desc
```

To return **individual log lines**, replace `summarize` with `project` and `take 100`. Computing the 5xx rate requires total requests and failed requests from HTTP metrics/telemetry; trace IDs must be propagated and logged by the application.

### Exercise C – Distinguishing Prometheus from Container Insights

An SRE team enabled Container Insights, sees `ContainerLogV2` in Log Analytics, yet cannot run `rate(container_cpu_usage_seconds_total[5m])` in the KQL editor.

**Questions:**

1. Why won't PromQL run in Log Analytics KQL?
2. Which workspace type is needed for managed Prometheus?
3. Which scraper/exporter emits `container_cpu_usage_seconds_total` in a live pipeline?
4. What can cause PromQL to return no data even when AKS is healthy?
5. Why shouldn't `orderId` be used as a metric label?

**Solution guide:** KQL and PromQL are different query languages over different stores. Managed Prometheus stores metrics in an Azure Monitor workspace via a scrape pipeline. No data can result from disabled metrics collection, missing targets, mismatched labels, or querying the wrong workspace. `orderId` explodes cardinality and risks exposing sensitive IDs.

### Exercise D – Cost Optimization

An AKS cluster runs 100 pods generating ~35 GB of container logs daily, 60% from `DEBUG` logs in the `test` namespace.

**Tasks:**

1. Propose application config changes to lower default `DEBUG` logging.
2. Explain how to use DCR/namespace filtering where supported without dropping production logs.
3. Explain why filtering by namespace inside a Log Analytics KQL query does not reduce ingestion spend.
4. Choose separate retention windows for troubleshooting logs, audit logs, and metrics.
5. Build a post-optimization verification checklist, including a negative test confirming real errors still appear.

**Solution guide:** cut noise at the source first; configure collection filters deliberately; measure ingestion before and after; preserve `ERROR` logs and vital security events; inspect Cost Management and workspace billing rather than treating `_BilledSize` as an invoice.

### Exercise E – Responding to Pod Restarts

A `payment-worker` Deployment shows rising restart counts, and logs indicate process termination.

**Task:** outline the sequence using `kubectl describe`/`kubectl logs --previous`, `KubeEvents`, `KubePodInventory`, memory metrics, and release version to distinguish `OOMKilled`, probe failures, and code crashes. Specify which checks still require querying the Kubernetes API directly rather than relying solely on lagged summary tables.

## 18. Self-Check Questions

**1. What roles do Container Insights and a Log Analytics workspace play?** Container Insights provides collection and monitoring experiences for AKS; the Log Analytics workspace stores configured logs/inventory/performance tables queried via KQL.

**2. What does `ContainerLogV2` contain?** Container stdout/stderr log records and related metadata when the stream is enabled and ingested.

**3. Does enabling Container Insights automatically generate request traces for every Java service?** No. Traces require instrumentation such as OpenTelemetry or Application Insights.

**4. What does a Data Collection Rule govern?** Sources/streams, destinations, and supported collection/transformation rules per deployment mode.

**5. `kubectl logs` has logs yet KQL shows nothing—what do you check?** Agent health, DCR, LAW destination, network, permissions, and query time range/cluster/namespace.

**6. Are a Log Analytics workspace and an Azure Monitor workspace the same resource?** No. LAW stores KQL log tables; AMW stores Prometheus metrics for managed Prometheus under supported models.

**7. To run `rate(container_cpu_usage_seconds_total[5m])`, should you use KQL or PromQL?** PromQL against the appropriate Prometheus metrics source.

**8. Does `ContainerLogV2` `ErrorLines` equal HTTP 5xx requests?** No. You need HTTP request metrics/telemetry with a valid total-request denominator.

**9. Does a `Running` pod prove it never restarted or hit OOM?** No. Inspect restart history, container `Last State`, events, and metrics.

**10. Does filtering by namespace in KQL reduce log ingestion cost?** No, because those logs were already ingested. Reduce ingestion at the source, collector, or DCR where supported.

**11. Why avoid `requestId` and `orderId` labels in Prometheus?** They cause high cardinality, hurting performance/cost and risking sensitive data exposure.

**12. Why shouldn't you log JWTs or secrets while debugging?** Logs persist long-term and are readable by multiple people/systems; leaked bearer credentials can be abused.

**13. To collect AKS API Server audit logs, is enabling Container Insights enough?** No. Configure AKS diagnostic settings and supported control-plane log categories separately.

**14. Why monitor both node/platform metrics and application telemetry?** Outages can originate in infrastructure or application logic/dependencies; one signal alone cannot diagnose everything.

## 19. Production Container Insights Deployment Checklist

- [ ] Classified **logs, metrics, Kubernetes events/inventory, and traces** against real operational needs.
- [ ] Selected the right AKS cluster, Azure subscription, region, and Log Analytics workspace.
- [ ] Audited existing monitoring configurations before enabling add-ons or modifying DCRs.
- [ ] Enabled Container Insights via AKS/CLI/Portal-supported mechanisms.
- [ ] Confirmed collection agents are running with permissions and network reachability to Azure Monitor endpoints.
- [ ] Confirmed DCR links to the right cluster with proper streams, namespace filters, and LAW destination.
- [ ] Verified `kubectl logs` shows output and `ContainerLogV2` receives records within the test window.
- [ ] Verified inventory, events, and performance tables actually populate as intended.
- [ ] Kept KQL/LAW distinct from PromQL/AMW; enabled managed Prometheus separately when needed.
- [ ] Instrumented application request metrics and traces independently where required.
- [ ] Enabled AKS diagnostic settings separately if control-plane/audit logs are required.
- [ ] Logs include cluster, namespace, workload, UTC timestamp, version, and correlation IDs.
- [ ] No secrets, tokens, or unneeded PII in logs; workspace query RBAC enforced.
- [ ] Dashboards cover availability, resource pressure, errors, latency, and release changes.
- [ ] Alerts specify scope, thresholds, evaluation windows, action groups, and runbooks.
- [ ] Tested pod restart/OOM, missing-log, missing-metric, and workspace-query failure drills.
- [ ] Reviewed data residency, retention, workspace access, privacy, and compliance.
- [ ] Measured ingestion, trimmed noisy logs, bounded metric cardinality, and forecasted costs.
- [ ] Managed monitoring configs/IaC, role assignments, and change reviews under operational governance.
- [ ] Tested rollback steps when modifying data collection or switching workspaces.

## 20. Conclusion

**Container Insights** is an essential observability layer for AKS, collecting **container logs, Kubernetes inventory/events, and configured performance metrics** via Azure Monitor Agent, Data Collection Rules, and a Log Analytics workspace. This data helps operations teams debug pod errors, restarts, and node pressure while correlating incidents with deployments. **KQL over `ContainerLogV2`** excels at searching and aggregating logs, while inventory, event, and performance tables supply vital context.

A complete AKS observability stack typically pairs Container Insights with **Azure Monitor managed Prometheus** for Prometheus metrics/PromQL, **Application Insights/OpenTelemetry** for request tracing, and **AKS diagnostic settings** for control-plane logs as needed. Turning on collectors is only step one: validate end-to-end live ingestion, pair alerts with runbooks, keep sensitive data out of logs, restrict query RBAC, and manage ingestion/retention so observability stays reliable within budget.

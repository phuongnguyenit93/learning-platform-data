# Managed Prometheus and Azure Managed Grafana for AKS

An **Azure Kubernetes Service (AKS)** cluster can run hundreds of Pods and dynamically create, delete, or reschedule them across nodes. When a Java API slows down or a Deployment drops below its ready replicas, operators immediately need answers: **Which Pod is consuming CPU? When did the HTTP error rate rise? Do nodes have enough memory? Is the app genuinely broken, or is a dashboard simply failing to receive data?** Manually SSHing into individual machines does not scale with Kubernetes.

**Azure Monitor managed service for Prometheus** (**Managed Prometheus**) provides Azure-managed storage and querying for Prometheus-compatible metrics. **Azure Managed Grafana** provides managed dashboards to query and visualize metrics, combine data sources, and support operations. Used together with AKS, both services let you build observability around **PromQL, dashboards, alerts, and cluster/namespace/Pod-scoped telemetry** without operating Prometheus and Grafana infrastructure yourself.

This lesson belongs to the **AKS Operations** chapter in the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Entra ID to virtual networking, compute, storage, and data, followed by deployment, monitoring, security, and cost management. Here the focus is building a **reliable AKS metrics pipeline**, measuring both Kubernetes and application health, enforcing least-privilege access, and controlling observability costs.

After this lesson, you will be able to:

- Distinguish **metrics, logs, and traces** and the roles of Prometheus, Azure Monitor workspaces, and Grafana.
- Explain the architecture **AKS → metrics collector → Azure Monitor workspace → PromQL → Azure Managed Grafana**.
- Enable Managed Prometheus for a cluster via the Portal or Azure CLI when authorized.
- Configure metrics read permissions and user roles in Azure Managed Grafana.
- Understand default scrape targets, custom scrapes, and how to export JVM/HTTP metrics from Spring Boot.
- Write **PromQL** queries for CPU, memory, replica availability, request rates, and error ratios.
- Design dashboards, alert rules, action groups, and incident runbooks.
- Diagnose **No data** errors, missing metrics, wrong namespaces/labels, permission errors, and network blocks.
- Estimate costs and prevent high cardinality, overly dense scraping, and unnecessary retention.

## 1. Observability in AKS: Metrics, Logs, and Traces

**Observability** is the ability to infer internal system state from operational signals. Three primary signal families:

| Signal Group | Best Questions Answered | Examples |
|---|---|---|
| **Metrics** | How much, how fast/slow, and how does it change over time? | CPU usage, Ready Pods, requests/second, p95 latency |
| **Logs** | What specific event occurred, and what was the error message? | Java exceptions, Kubernetes events, authentication failures |
| **Traces** | Which services did a single request traverse, and where did it stall? | HTTP gateway → orders API → database |

Prometheus focuses on **time-series metrics**. A metric consists of a name, a label set, and timestamped numeric samples:

~~~text
http_server_requests_seconds_count{
  application="orders-api",
  method="GET",
  status="200"
} 18452
~~~

This is an illustrative example; actual names and labels depend on the exporter/runtime and scrape config. As requests arrive, the counter increments; PromQL uses **`rate()`** or **`increase()`** to calculate rates or counts over a window.

### Do Not Conflate Observability Services

- **Managed Prometheus**: Prometheus-format metrics, scrape rules, and PromQL queries.
- **Azure Monitor workspace (AMW)**: Azure resource storing and querying Managed Prometheus metrics; not an Azure Log Analytics workspace.
- **Azure Managed Grafana**: dashboard and query UI; not the primary metric storage backend of Managed Prometheus.
- **Container Insights**: container/cluster observability covering logs, inventory, and selected signals; typically uses Log Analytics in its standard model.
- **Application Insights / OpenTelemetry**: measures requests, dependencies, traces, and application telemetry as configured.

A cluster running **Managed Prometheus** does not automatically collect **stdout/stderr logs** or distributed traces. Conversely, enabling Container Insights does not automatically capture custom Java Prometheus metrics.

## 2. Managed Prometheus + Managed Grafana Architecture

~~~text
                     AKS cluster
                +----------------------+
                | kubelet / cAdvisor   |
                | kube-state-metrics   |
                | node exporters       |
                | Java /metrics        |
                +----------+-----------+
                           |
                      Prometheus scrape
                           |
                           v
                 Azure Monitor metrics
                  collector (ama-metrics)
                           |
                           | Managed ingestion
                           v
                    Azure Monitor
                      workspace
                  (Prometheus metrics)
                           ^
                           | PromQL / data source
                           |
                   Azure Managed Grafana
                     dashboards / users
                           |
                     Operator / SRE

     Separate optional pipelines:
       AKS logs ----------> Log Analytics / Container Insights
       Java traces -------> Application Insights / trace backend
       Alerts ------------> Azure Monitor Action Groups
~~~

Metrics collectors typically appear inside the cluster as workloads related to **`ama-metrics`** when Managed Prometheus is enabled per AKS-supported modes.

**Data does not automatically flow into Grafana just by creating a Grafana workspace.** The cluster must run collectors/scrapes; metrics must ingest into AMW; Grafana needs the data source and read permissions; and operators need access to Grafana.

### Who Manages What?

| Component | Azure Manages | Operations Team Still Manages |
|---|---|---|
| AKS control plane | Per AKS model | Node pools, workloads, security, quotas, upgrades |
| Managed metrics backend | Service infra for storing/querying metrics | Choosing AMW, scrape targets, labels, retention/cost, RBAC |
| Metrics collectors | Supported add-on/extension lifecycle | Enabling feature, custom scrapes, checking Pods/ingestion |
| Azure Managed Grafana | Managed Grafana hosting | IAM, data sources, folders/dashboards, alerts, and user RBAC |
| Java instrumentation | Does not write application code | Micrometer/Actuator, useful metrics, cardinality, and privacy |

Managed does not mean **zero configuration**, **zero cost**, or **no permissions management**.

## 3. What Is an Azure Monitor Workspace?

An **Azure Monitor workspace (AMW)** is the Azure resource dedicated to Prometheus-format metrics used by Managed Prometheus. It serves as the ingestion target for collectors and the query source for PromQL.

### Distinguishing the "Workspaces"

| Name | Primary Purpose |
|---|---|
| **Azure Monitor workspace** | Stores and queries Azure-managed Prometheus metrics |
| **Log Analytics workspace** | Stores/queries logs with Kusto Query Language (KQL) when services send data there |
| **Azure Managed Grafana workspace** | Hosts the Grafana UI, data source configs, dashboards, and user permissions |

All three resources can serve the same AKS architecture, yet **they are not interchangeable**. Specifically, a Grafana dashboard running PromQL against AMW is not running KQL against Log Analytics.

### Region and Scope Considerations

When designing:

- Place AMW in an organization-approved region, subscription, and resource group.
- Check support for connecting multiple clusters to one AMW per service version and architecture.
- Consider separating **dev/test/prod**, tenants, or domains to isolate permissions, cost, and query complexity.
- Never assume AKS, AMW, and Grafana must always reside in the exact same region across every topology; verify support matrices, residency, latency, and policies.
- Document resource ownership, alerts, retention, and recovery plans if AMW or dashboards are disrupted.

**An AMW receiving metrics from multiple sources** requires consistent labels distinguishing cluster, namespace, and workload. Never treat a display cluster name as a security boundary if RBAC grants read access across the whole workspace.

## 4. Which Metrics Should You Monitor on AKS?

Organize signals in layers:

| Layer | Representative Metrics | What It Reflects |
|---|---|---|
| **Cluster/node** | CPU, memory, node readiness, filesystem, network | Do nodes have capacity and stay healthy? |
| **Kubernetes objects** | Deployment desired/available replicas, Pod phases, restart counts | Are controllers meeting desired state? |
| **Container** | CPU usage, memory working set, throttling, restarts | Which container is the bottleneck? |
| **Application** | HTTP request rate, error rate, duration, JVM memory/GC | What are users and callers experiencing? |
| **Dependencies** | DB pool usage, queue lag, dependency failures | Is a bottleneck outside the container? |
| **Business** | Successful checkouts, background jobs, processing time | Is the system completing real work? |

The default Managed Prometheus collector scrapes a curated set of Kubernetes targets/metrics—such as **kubelet/cAdvisor, kube-state-metrics, and node exporters**—depending on add-on version and enabled features. Azure may apply **keep-lists / minimal ingestion** on default metrics to control costs.

**Do not assume every metric from every exporter in the cluster is scraped automatically.** In particular, Spring Boot Java metrics require exposing a Prometheus endpoint and configuring **custom scraping** or matching collection rules.

## 5. Enabling Managed Prometheus on AKS via Azure Portal

Prerequisites before proceeding:

1. An active **AKS cluster** in a subscription you are permitted to manage.
2. An existing or permitted **Azure Monitor workspace** in the right scope.
3. Permissions to update AKS monitoring settings, link to AMW, and create related resources.
4. Reviewed budget/ingestion costs and data retention policies.
5. Network and Azure Policies do not block the add-on/collector or ingestion endpoints.

General Portal steps:

1. Sign in to the [Azure Portal](https://portal.azure.com) and open the target **AKS cluster**.
2. Open **Monitoring** or **Insights** and locate the option to enable **Managed Prometheus / Prometheus metrics**.
3. Select an existing **Azure Monitor workspace** or create a new one if permitted.
4. Optionally link Grafana if the Portal workflow offers it, or configure Azure Managed Grafana separately afterward.
5. Review resources, identities, IAM, scope, and cost implications.
6. Enable the feature and confirm the metrics collector add-on deploys.
7. Open AMW and confirm metrics arrive before building custom dashboards.

Exact blade and button names vary in the Portal. **Do not enable Container Insights / log collection unintentionally just to get Managed Prometheus**, since that is a separate pipeline and bill.

### Does Enabling Monitoring Disrupt Applications?

The goal is adding observability without changing application code. However, collectors consume CPU/memory and generate network traffic on nodes; when updating monitoring configs on a production cluster, schedule a proper window and verification steps. Never treat it as **zero-risk**.

## 6. Azure CLI: Inspecting AKS and Enabling the Metrics Add-On

Examples use **Bash / Azure Cloud Shell** with Azure CLI and required permissions. Lines with placeholders cannot run verbatim. Only run **`update`** commands on lab clusters or under an approved change request.

### Select Subscription, Cluster, and AMW

~~~bash
az login
az account list --output table
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG_AKS="<AKS_RESOURCE_GROUP>"
AKS="<AKS_CLUSTER_NAME>"
AMW_ID="<EXISTING_AZURE_MONITOR_WORKSPACE_RESOURCE_ID>"

az aks show \
  --resource-group "$RG_AKS" \
  --name "$AKS" \
  --query "{name:name,location:location,id:id,monitorProfile:azureMonitorProfile}" \
  --output json
~~~

**`AMW_ID`** must be the real Resource ID of an Azure Monitor workspace, not a Log Analytics workspace ID or Grafana workspace ID.

### Enable Managed Prometheus Collection

~~~bash
az aks update \
  --resource-group "$RG_AKS" \
  --name "$AKS" \
  --enable-azure-monitor-metrics \
  --azure-monitor-workspace-resource-id "$AMW_ID"
~~~

This mutates the AKS resource; check **`az aks update --help`**, your Azure CLI version, and subscription feature support before running. Some environments use different extensions/flags over time; never fix errors by randomly installing extensions without reading the error message first.

### Verify Configuration

~~~bash
az aks show \
  --resource-group "$RG_AKS" \
  --name "$AKS" \
  --query "azureMonitorProfile" \
  --output json
~~~

If you have Kubernetes access:

~~~bash
az aks get-credentials \
  --resource-group "$RG_AKS" \
  --name "$AKS"

kubectl config current-context
kubectl get pods -n kube-system | grep ama-metrics
~~~

**`az aks get-credentials`** can switch your default kubeconfig context, so confirm you are not pointing at a production cluster. Add-on Pod names/groups can evolve; seeing those Pods is a helpful signal, not proof that every scrape target is healthy.

**Important:** Running collector Pods do not guarantee AMW has received metrics, and AMW receiving metrics does not guarantee Grafana has permission to read them.

## 7. What Is Azure Managed Grafana For?

**Azure Managed Grafana** is Azure's managed Grafana service used to:

- Build dashboards organized by ops team, namespace, cluster, application, or environment.
- Write metric queries (PromQL for Managed Prometheus).
- Combine multiple data sources depending on supported plugins/versions/features.
- Manage folders, dashboard variables, permissions, and sharing.
- Configure/visualize alerting via Grafana mechanisms where appropriate.

Azure Managed Grafana **does not scrape Pods itself** and does not replace the metric storage backend. Grafana queries configured data sources.

~~~text
Azure Managed Grafana dashboard
  Panel: "Java API request rate"
      |
      | PromQL query
      v
Azure Monitor workspace (managed Prometheus)
      |
      v
Time-series samples collected from AKS
~~~

### What Goes in Grafana vs Azure Monitor?

| Need | Appropriate Tool |
|---|---|
| Multi-panel dashboards and PromQL exploration | Azure Managed Grafana |
| Managed storage, collection, and querying of Prometheus metrics | Azure Monitor workspace + Managed Prometheus |
| Alert rules operating independently of an open browser dashboard | Azure Monitor Prometheus rule groups / alert rules where appropriate |
| Notifications to email, webhooks, or on-call systems | Azure Monitor Action Groups or alerting contact points |
| Investigating specific Java exceptions | Application logs / Application Insights |
| Tracing calls across microservices | Distributed tracing / OpenTelemetry |

Never design alerting around someone **keeping a dashboard open in a browser**.

## 8. Connecting Azure Managed Grafana to an Azure Monitor Workspace

Typical setup workflow:

1. Create or open an approved **Azure Managed Grafana workspace**.
2. Enable/configure Grafana's **managed identity** per service capabilities.
3. Grant Grafana's identity **metrics read permissions** on the Azure Monitor workspace.
4. Connect the **Azure Monitor managed service for Prometheus** data source (or Prometheus data source via supported Azure integration).
5. Open a built-in dashboard to confirm Kubernetes series appear.
6. Assign **Grafana Viewer/Editor/Admin** roles to operators.
7. Test with a Viewer-only account to verify it cannot alter data sources or permissions.

### Data Read Permissions Differ from Grafana Login Permissions

Two separate permission layers exist:

| Principal | Scope | Typically Required Permission |
|---|---|---|
| **Grafana managed identity** | Azure Monitor workspace | **Monitoring Data Reader** or equivalent role specified by integration docs |
| **Dashboard user** | Azure Managed Grafana resource | **Grafana Viewer**, **Grafana Editor**, or **Grafana Admin** |
| **Integration administrator** | Azure resources and Grafana settings | Scoped IAM/datasource admin rights with audit trail |

A user may log in to Grafana cleanly yet see **No data** because Grafana's identity lacks permission to query AMW. Conversely, Grafana may have AMW query rights while a user without Grafana access cannot open the dashboard.

### Least-Privilege Permission Model

- On-call operators viewing dashboards: **Viewer** when edits are unnecessary.
- SREs / dashboard maintainers: **Editor** within approved folders/scopes.
- Data source / IAM administrators: **Admin** under change control and audit.
- Grafana identity: **read-only**, never needing permission to delete AMW or mutate AKS.

**Never share a single generic Grafana Admin account.** Use Entra ID, security groups, scoped roles, and audit logs.

## 9. Building a Foundational Kubernetes Dashboard

A useful AKS operations dashboard answers questions in order:

1. **Are enough cluster nodes Ready?**
2. **Are any Deployments short on available Pods?**
3. **Which Pods/containers are consuming CPU/memory?**
4. **Are application errors or latency rising?**
5. **Is the issue isolated to one namespace, one node, or cluster-wide?**

### Suggested Layout

~~~text
Dashboard: AKS Production Overview

Filters: cluster | namespace | workload

┌─────────────────────────────────────────────┐
│ Ready Nodes │ Ready Pods │ Alerts │ RPS     │
├─────────────────────────────────────────────┤
│ CPU usage by namespace                      │
├─────────────────────────────────────────────┤
│ Memory working set by Pod                   │
├─────────────────────────────────────────────┤
│ Deployment desired vs available replicas    │
├─────────────────────────────────────────────┤
│ Java API: request rate / 5xx / p95 latency  │
└─────────────────────────────────────────────┘
~~~

This is a **wireframe**, not an importable JSON dashboard. When building a live dashboard, verify data sources, intervals, units, labels, and time-series formatting per metric.

### Dashboard Variables

Grafana supports template variables to filter by cluster, namespace, or workload from live labels or lists. Conceptual variable query:

~~~promql
label_values(kube_pod_info, namespace)
~~~

**`label_values`** is a **Grafana variable query syntax**, **not a standard PromQL function** executable in raw Prometheus APIs/editors. Inside panel PromQL queries, use standard PromQL filtering by the selected variable:

~~~promql
sum by (namespace) (kube_pod_status_phase{phase="Running"})
~~~

In some setups, metrics or labels are trimmed or renamed by minimal ingestion or relabeling; verify live series rather than assuming copied queries always return data.

## 10. PromQL Fundamentals: Metrics, Labels, Range Vectors

**PromQL** is Prometheus's time-series query language. Four core constructs:

| Concept | Example | When Used |
|---|---|---|
| **Instant vector** | `kube_node_status_condition` | Inspect latest values of matching series |
| **Label filtering** | `{namespace="orders"}` | Narrow down to a specific workload/scope |
| **Range vector** | `[5m]` | Analyze samples over a time window |
| **Aggregation** | `sum by (pod) (...)` | Roll up multiple series along desired dimensions |

Common Prometheus metric types:

- **Counter:** monotonically increasing (aside from resets/restarts), e.g., HTTP request counts. Typically paired with **`rate()`** or **`increase()`**.
- **Gauge:** rises and falls, e.g., memory usage or Ready Pods.
- **Histogram:** tracks distribution of observations via buckets, total count, and sum to estimate quantiles like latency.
- **Summary:** tracks observations/durations; pre-computed quantiles cannot be aggregated across Pods the same way histograms can.

Never run **`rate()`** on arbitrary gauges, and never average per-Pod p95 values from summaries and claim it is service-wide p95.

### Verify a Metric Exists Before Building Panels

In the Query editor, start with a simple check:

~~~promql
up
~~~

**`up = 1`** generally means the latest scrape succeeded for that target; **`up = 0`** means the scrape failed per Prometheus semantics. Still, depending on ingestion filters, labels, or stored series, verify actual targets. **Missing `up` series** alone does not prove the cluster is down.

Next check:

~~~promql
count by (job) (up)
~~~

Use this to see which **`job`** labels exist. If completely empty, inspect the data source, time range, region, permissions, scrape config, and ingestion lag.

## 11. PromQL for Nodes and Pods

Examples use common `kube-state-metrics` / `cAdvisor` metrics; **exact series and labels depend on collector config, metric keep-lists, and Kubernetes version**.

### Count Ready Nodes

~~~promql
sum(kube_node_status_condition{condition="Ready",status="true"})
~~~

If multiple clusters share the same workspace, filter by cluster label when present. Never sum nodes across two separate clusters and misread them as one healthy cluster.

### CPU Usage by Pod

~~~promql
sum by (namespace, pod) (
  rate(container_cpu_usage_seconds_total{
    namespace="orders",
    container!="",
    container!="POD"
  }[5m])
)
~~~

Counter **`container_cpu_usage_seconds_total`** tracks consumed CPU-seconds; **`rate()`** expresses consumption roughly in CPU cores. A value of **`0.25`** represents roughly **0.25 cores** over the query window, not 25% of an arbitrary node.

### Memory Working Set by Pod

~~~promql
sum by (namespace, pod) (
  container_memory_working_set_bytes{
    namespace="orders",
    container!="",
    container!="POD"
  }
)
~~~

Units here are **bytes**. In Grafana, choose **bytes (IEC)** or matching units. Do not confuse working set with Java heap; container memory also includes native memory, thread stacks, buffers, and filesystem cache per metric definition.

### Deployments Missing Replicas

~~~promql
kube_deployment_spec_replicas{namespace="orders",deployment="orders-api"}
-
kube_deployment_status_replicas_available{namespace="orders",deployment="orders-api"}
~~~

A positive result means desired replicas exceed available replicas in the stored series. When multiple clusters or differing labels exist, align label sets when subtracting vectors; mismatched labels return empty results. Always **inspect raw labels and series before reusing sample panels**.

## 12. Instrumenting Java Applications with Micrometer

Infrastructure metrics only show whether nodes and Pods are up. When customers report slow APIs, you need **application metrics** covering requests, latency, errors, and JVM health.

With **Spring Boot Actuator + Micrometer Prometheus registry**, your app exposes an endpoint such as:

~~~text
GET /actuator/prometheus
Content-Type: text/plain; version=...

jvm_memory_used_bytes{area="heap",...} ...
process_cpu_usage{...} ...
http_server_requests_seconds_count{...} ...
~~~

Exact series and label names depend on Spring Boot, Micrometer, and instrumentation configuration.

### Maven Dependencies

In **`pom.xml`**, add required dependencies if missing:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Using a proper Spring Boot parent/BOM keeps dependency versions aligned. Avoid mixing multiple incompatible Prometheus client libraries just to get metrics working.

### `application.properties` Configuration

~~~properties
server.port=8080
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.probes.enabled=true
~~~

Verify locally or in sandbox:

~~~bash
curl -fsS http://localhost:8080/actuator/prometheus | head -n 25
~~~

The app must actually listen on port 8080 and allow access from your test environment. **Never expose `/actuator/prometheus` publicly to the Internet just so a collector can scrape it.** It can leak endpoint names, library versions, memory layouts, and topology; keep scraping inside controlled internal networking.

### Recording Business Metrics with Micrometer

Example using a **`Counter`** to track completed operations:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final Counter completedCounter;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completedCounter = Counter.builder("checkout_completed")
                .description("Completed checkout operations")
                .tag("result", "success")
                .register(registry);
    }

    public void completed() {
        completedCounter.increment();
    }
}
~~~

This is an instrumentation sample, **not a complete checkout system**. The Micrometer Prometheus registry exports this counter as **`checkout_completed_total`** by appending **`_total`** to **`checkout_completed`**. Call **`completed()`** only after business logic reliably confirms the outcome; if transactions retry or roll back, define clearly what "completed" means.

**Never attach `customerId`, `email`, `orderId`, or `requestId` as metric labels**: every unique value spawns a new time series, exploding cardinality, driving up costs, and risking sensitive data leaks.

## 13. Custom Scraping from Java Pods

Managed Prometheus generally does not automatically discover your Java **`/actuator/prometheus`** endpoint. To collect application metrics, configure **custom scraping** via AKS/Managed Prometheus-supported mechanisms.

Common approaches:

- **Pod annotations** when annotation-based scraping is enabled and configured in the add-on.
- **Custom Prometheus scrape config** via the supported Azure Monitor metrics collector ConfigMap/mechanism.
- Prometheus Operator integrations/CRDs where deployed; **never assume `ServiceMonitor`/`PodMonitor` works automatically** merely from enabling Managed Prometheus without a supporting controller.

### Pod Annotations: Advertising the Endpoint

Example Pod template metadata:

~~~yaml
template:
  metadata:
    labels:
      app: java-api
    annotations:
      prometheus.io/scrape: "true"
      prometheus.io/path: "/actuator/prometheus"
      prometheus.io/port: "8080"
  spec:
    containers:
      - name: java-api
        image: <ACR_LOGIN_SERVER>/java-api:1.0.0
        ports:
          - name: http
            containerPort: 8080
~~~

This is a **Pod template snippet**, not a complete Deployment. **Annotations alone do not guarantee scraping.** The collector must be configured to enable annotation discovery for the right namespace, path, port, and auth/network. How annotation scraping and namespace filters are configured varies by add-on version; follow official ConfigMap documentation rather than assuming Prometheus Operator is installed.

### Conceptual Prometheus Scrape Job Sample

For a collector accepting standard **Prometheus `scrape_config`** with Kubernetes service discovery enabled, a job looks like:

~~~yaml
scrape_configs:
  - job_name: java-api
    scrape_interval: 30s
    metrics_path: /actuator/prometheus
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - observability-demo
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: java-api
      - source_labels: [__meta_kubernetes_pod_container_port_name]
        action: keep
        regex: http
~~~

**This is a Prometheus scrape snippet**, **not a complete ready-to-apply Kubernetes ConfigMap**. In Managed Prometheus, place it in the exact **ConfigMap name/key/namespace** following the **current Azure Monitor metrics add-on custom-scrape schema** (for example, documentation commonly references **`ama-metrics-prometheus-config`**; verify exact schema, service discovery RBAC, limits, and rollout mechanics before applying).

### How to Verify Live Targets Are Being Scraped

1. Confirm the **Java app** returns metrics via `curl` inside cluster networking.
2. Confirm the collector config applied cleanly without parse or relabel errors.
3. Query Java metric names like **`jvm_memory_used_bytes`** in AMW/Grafana.
4. Filter by **`job`**, **`namespace`**, and **`pod`** after checking live labels.
5. Check fresh timestamps and sample counts rather than relying on an old screenshot.
6. In restricted networks, inspect NSGs/NetworkPolicies, DNS, and collector permissions.

If the collector cannot reach the Java endpoint, **never expose the app publicly**. Fix in-cluster connectivity and scrape configuration.

## 14. PromQL for Java Applications

Examples below assume standard Micrometer metric names. **Not every app exports histogram buckets**, and `job`/`namespace` labels may be added by the collector. Test raw queries before finalizing dashboards.

### Requests Per Second

~~~promql
sum(
  rate(http_server_requests_seconds_count{job="java-api"}[5m])
)
~~~

If label **`job="java-api"`** does not exist, replace it with the selector attached by your collector. This computes **requests/second** from Spring/Micrometer's request counter.

### HTTP 5xx Ratio

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="java-api",
    status=~"5.."
  }[5m])
)
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{job="java-api"}[5m])),
  0.001
)
~~~

The result is a **0–1** ratio, not a 0–100 percentage. In Grafana, pick unit **Percent (0.0–1.0)** or multiply by **100** with 0–100 units. At low traffic, ratios swing wildly on a couple of errors; pair alerts with minimum request volume or absolute error count thresholds.

### p95 Latency When Histogram Buckets Are Exported

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="java-api"}[5m])
  )
)
~~~

**Run this only if histogram bucket metrics are actually exported.** With Micrometer/Spring Boot, enable histogram buckets/SLOs for HTTP server requests. Without **`_bucket`** series, this returns empty. You cannot calculate p95 from a single `_count` series.

The standard unit for **`http_server_requests_seconds`** is **seconds**; set Grafana units to **seconds**. Multiply by 1000 if displaying milliseconds deliberately.

### JVM Heap Usage

~~~promql
sum(
  jvm_memory_used_bytes{job="java-api",area="heap"}
)
~~~

With multiple replicas, **`sum`** aggregates heap across matching processes. To compare individual Pods:

~~~promql
sum by (pod) (
  jvm_memory_used_bytes{job="java-api",area="heap"}
)
~~~

Monitor **JVM heap, non-heap, GC pauses, container working set, and `OOMKilled`** together. Heap well below the container memory limit does not prevent OOMs from native memory, thread stacks, or direct buffers.

### Custom Checkout Counter

~~~promql
sum by (result) (
  increase(checkout_completed_total{job="java-api"}[1h])
)
~~~

This measures **instrumented events**, which do not automatically guarantee committed database rows. Reconcile against business records if used for SLAs or billing.

## 15. Designing a Java API Dashboard Around the Four Golden Signals

An API dashboard should cover:

| Signal | Panel | How to Interpret |
|---|---|---|
| **Latency** | p50/p95/p99 request duration | Are users experiencing tail latency? |
| **Traffic** | Requests per second | Is load spiking or dropping abnormally? |
| **Errors** | 5xx ratio and absolute error count | Are errors breaching the SLO? |
| **Saturation** | CPU throttling, memory, thread/connection pools | Is the workload nearing capacity limits? |

For Java, add **GC pause duration**, heap usage, live threads, and database connection pool metrics. Avoid stuffing all 100 metrics onto one overview page; separate **overview** and **deep-dive** dashboards by use case.

### Illustrative Drill Thresholds

Suppose a team sets a **99.9% success SLO** for an API (hypothetical target). A healthy dashboard might show:

~~~text
Request success rate 5m    99.95%
HTTP 5xx rate 5m           0.05%
p95 latency                220 ms
Ready Pods / desired       3 / 3
JVM heap used              62%
~~~

These figures are **illustrative**, not real AKS telemetry or universal SLO prescriptions. Set thresholds from user expectations, baseline traffic, error budgets, and application behavior.

## 16. Azure Monitor Prometheus Alert Rules

Dashboards help humans inspect data; **alert rules** catch regressions even when nobody has Grafana open.

In Azure Monitor, create **Prometheus rule groups** linked to AMW containing **recording rules** or **alert rules** per service capabilities. Alerts route through Azure Monitor **Action Groups** to email, webhooks, or incident response tools.

### Sample PromQL Alert for Under-Provisioned Deployment Replicas

~~~promql
sum(
  kube_deployment_status_replicas_available{
    namespace="orders",
    deployment="orders-api"
  }
)
<
2
~~~

This example assumes a desired minimum of two Pods and should pair with **`for: 10m`** in the rule config to avoid paging on brief blips. If HPA adjusts desired replicas dynamically, **compare available against desired** instead of hardcoding **`2`**.

An expression comparing against desired replicas with matching labels:

~~~promql
kube_deployment_spec_replicas{namespace="orders",deployment="orders-api"}
-
kube_deployment_status_replicas_available{namespace="orders",deployment="orders-api"}
> 0
~~~

This is a **PromQL expression**, not a complete ARM/Bicep/YAML alert rule. On Azure, create a **Prometheus rule group** via Portal, Bicep/ARM, or API/CLI with evaluation interval, scope, condition, action group, and RBAC.

### Alerting on HTTP 5xx Ratio

A practical rule evaluates:

- SLO-aligned error threshold (e.g., 5xx ratio above budget over a sustained window).
- Minimum request volume to avoid paging on a single error during quiet hours.
- Observation window and **`for` duration** to prevent flapping.
- Ingestion latency, scrape intervals, and missing-series handling.
- On-call owner, escalation path, and linked runbook.

Never configure **`error_ratio > 0`** alone: a single transient error would page operators for an otherwise healthy service.

### Alerting on Missing Data

**No data does not mean the API is healthy.** If the collector crashes or scraping is blocked, charts go blank while the app may be down. Add **metrics absence/staleness** alerts, collector health checks, ingestion lag checks, or independent synthetic availability probes.

## 17. Recording Rules and Query Performance

**Recording rules** precompute expensive expressions and store results as new time series, speeding up heavy dashboards where appropriate.

Conceptual example:

~~~promql
sum by (namespace, deployment) (
  kube_deployment_status_replicas_available
)
~~~

This can be recorded as a reusable aggregated metric following rule-group naming syntax and organizational conventions.

However, recording rules **create additional series**, adding cost and lifecycle overhead. Never generate per-Pod or per-`customerId` recording rules for ephemeral objects. Prioritize aggregations shared by SLOs and frequently viewed dashboards.

### Query Range Considerations

A dashboard spanning 30 days on a 5-second refresh consumes far more query resources than a 1-hour view refreshing every minute. Practice:

- Match **time range** to the investigation goal.
- Set **query step / min interval** realistically relative to scrape intervals.
- Precompute heavy expressions via recording rules when justified.
- Avoid fanning out across millions of unneeded label values.
- Restrict dashboard variables to relevant clusters and namespaces.

## 18. Cardinality: Why Costs Escalate Rapidly

In Prometheus, every unique combination of **metric name + label values** creates a distinct time series.

Suppose metric:

~~~text
http_server_requests_seconds_count{
  method="GET",
  route="/orders/{id}",
  status="200",
  pod="orders-api-abc"
}
~~~

If a **`user_id`** label has 100,000 unique values multiplied across methods, statuses, and pods, total series explode dramatically.

### Estimation Example

Suppose:

- 10 stable API routes.
- 4 HTTP methods.
- 5 status groups.
- 10 Pods.

Theoretical upper bound:

~~~text
10 routes × 4 methods × 5 statuses × 10 pods
= 2,000 time series for one metric family
~~~

Adding one **`customer_id`** label with 20,000 values yields:

~~~text
2,000 × 20,000 = 40,000,000 potential series
~~~

This is a **theoretical combinatorial upper bound**, not a guarantee all combinations occur—yet it clearly illustrates the financial and operational risk of high-cardinality labels.

### Label Design Rules

- Use labels with **bounded, stable value sets**: `region`, `environment`, `namespace`, `service`, `method`, `status` class.
- For HTTP routes, use **route templates** such as **`/orders/{id}`**, never raw URLs containing entity IDs.
- Never use **`email`, `requestId`, `traceId`, `userId`, `sessionId`, or `orderId`** as metric labels.
- Record transaction identifiers in **logs/traces** under proper privacy controls.
- Drop unnecessary metrics at scrape time where supported by the collector.
- Monitor active series count and ingestion volume, and set cost budgets/alerts.

## 19. Scrape Intervals, Retention, and Cost Modeling

In Prometheus-style metrics, the **scrape interval** sets how often exporters are sampled. Example:

~~~text
1,000 time series
Scraped every 30 seconds
=> 2 samples/minute/series
=> ~120,000 samples/hour (rough estimate before filters/gaps)
~~~

Halving the interval to **15 seconds** roughly doubles sample volume for the same series before filtering or aggregation. When picking intervals:

- Time-sensitive alerting metrics may warrant higher resolution.
- Long-term capacity metrics often work fine at lower frequency.
- Factor in collector overhead, ingestion limits, latency, and service pricing.
- Managed Prometheus retention depends on plan/features/service limits—never assume infinite retention.

### Costs to Account For

| Component | Cost / Risk |
|---|---|
| Managed Prometheus | Metrics ingestion and usage charges under current pricing |
| Azure Monitor workspace | Storage and query usage within service limits |
| Azure Managed Grafana | Workspace/tier/instance pricing and enabled features |
| Azure Monitor alerts | Alert rule evaluations, notifications, and Action Groups per pricing |
| Container Insights / Log Analytics | **Separate** ingestion/retention costs if enabled |
| AKS collector | CPU/RAM on nodes, impacting cluster capacity |
| Networking | Egress or private networking charges per topology |
| Application Insights | Separate telemetry and retention charges if enabled |

Never assume fixed pricing across all regions or tiers. Use the **Azure Pricing Calculator, Azure Monitor usage/cost analysis, and Cost Management**. **Budget alerts do not stop ingestion automatically**; controlling spend requires tuning series counts, scrape configs, intervals, and retention.

## 20. Securing Managed Prometheus and Grafana

Metrics can expose internal details:

- Cluster, node, namespace, service, and endpoint names.
- Connection counts, traffic volume, and rollout state.
- Poorly chosen labels can leak customer names, usernames, or internal URLs.
- Overly broad Viewer access can expose internal system topology.

### Controls to Implement

1. **Microsoft Entra ID** and RBAC for Grafana users; separate Viewer/Editor/Admin roles.
2. **Managed identity** for Grafana querying AMW with scoped read-only permissions.
3. **Least privilege** over AMW administration, AKS, and collector configs.
4. **Private metrics endpoints** whenever possible; never expose port 8080/Actuator publicly just for scraping.
5. **Network access** controls to AMW/Grafana/ingestion endpoints per product support and network policy.
6. **TLS, secret management**, and auditing for any additional data-source integrations.
7. **Never log access tokens** or credential-bearing data-source configs.
8. **Data classification** for metric/label names, exported dashboards, and screenshots.

### Multi-Tenancy and Namespace Isolation

**A `namespace` label is not tenant security** inside AMW or Grafana. Any identity holding workspace-wide read rights can query metrics across namespaces/clusters depending on data and permissions. Strict multi-tenant isolation requires separate **workspaces, data sources, and IAM boundaries** rather than relying solely on a Grafana **`namespace`** variable.

Do not let Team A modify or delete Team B's critical alert dashboards when folder/permission boundaries can prevent it.

## 21. Azure Monitor Prometheus and Private Networking

A private AKS cluster, a private ACR, and an AMW present **three distinct networking paths**. For Managed Prometheus to work, collectors inside AKS must reach Azure Monitor ingestion endpoints via supported network paths.

When clusters run inside egress-restricted VNets:

- Verify DNS resolution and firewall/proxy rules for required Azure Monitor collector endpoints.
- Verify the add-on's managed identity / service authentication per supported configs.
- When using Azure Monitor Private Link Scope (AMPLS) or supported private networking, design private DNS and routing carefully.
- Ensure probes from metrics collectors to **`/actuator/prometheus`** are not blocked by NetworkPolicies or namespace policies.
- Separate **in-cluster scrape failures** from **AMW ingestion failures** and **Grafana-to-AMW query failures**.

~~~text
Java exporter (pod)
      |
      | Internal HTTP scrape
      v
ama-metrics collector
      |
      | Azure Monitor ingestion via supported path
      v
Azure Monitor workspace
      ^
      | Azure Monitor / Prometheus data source API
      |
Azure Managed Grafana
~~~

When a dashboard shows No data, identify the **last hop that saw data**: Java endpoint, collector, AMW query, or Grafana panel. Never disable firewalls cluster-wide just to "test."

## 22. Incident: Dashboard Shows "No Data"

A dashboard can be blank while the Java API serves traffic normally. Diagnose layer by layer:

| Layer | Signal / Check | Possible Cause |
|---|---|---|
| Dashboard | Time range, data source, panel PromQL | Wrong data source, metric name, namespace, or time range |
| Azure Managed Grafana | User login and data source health | Missing Viewer/Admin role or Grafana managed identity permissions |
| AMW | Query a basic metric directly | Data not ingested yet, bad query, or missing permissions |
| Collector | `ama-metrics` Pods/logs and custom scrape config | Agent not running, bad config, or unhealthy scrape targets |
| Exporter | `curl /actuator/prometheus` from an allowed pod/network | Actuator not exposed, wrong port/path, or auth/network block |
| AKS | Pod/service readiness, NetworkPolicies, node status | Workload down or endpoints missing |

### Six-Step Workflow

1. In Grafana, set time range to **Last 1 hour**, pick the right data source, and test a verified Kubernetes metric.
2. Confirm Grafana's managed identity holds **Monitoring Data Reader** on AMW.
3. In AMW, check whether any fresh Kubernetes metrics are being ingested.
4. On AKS, inspect **`ama-metrics`** Pod status and collector logs per available permissions.
5. For Java metrics, test the endpoint inside the cluster and verify custom scrape config pickup.
6. After fixing, wait one scrape/ingestion cycle and verify fresh **sample timestamps**; document findings.

Do not lower dashboard refresh to 1 second trying to fix No data; that only amplifies query load.

## 23. Incident: Node Metrics Exist, Yet JVM Metrics Are Missing

**Scenario:** AMW receives container CPU and node metrics and the built-in Kubernetes Grafana dashboard works, yet **`jvm_memory_used_bytes`** returns nothing.

### Analysis

Default collector metrics may be working fine while the Java app still needs instrumentation and custom scraping:

1. Does the Java app include **`micrometer-registry-prometheus`** and Actuator?
2. Does **`/actuator/prometheus`** return **`jvm_*`** series in the lab environment?
3. Is the endpoint bound to the expected port and reachable by collectors inside the cluster?
4. Is custom scraping or annotation scraping actually enabled and scoped to the app's namespace?
5. Are relabeling rules accidentally dropping the job or metrics?
6. Is the Grafana query filtering on the wrong **`job`**, **`pod`**, or **`cluster`** labels?

**Fix:** ensure the endpoint and scrape config are right, inspect collector logs, query the raw metric first, and only then add label filters. Do not alter cluster-wide default scrape configs for a single app when a narrow namespace-scoped custom job works cleanly.

## 24. Incident: Dashboard Shows High CPU Yet App Is Healthy

**Scenario:** Pod CPU panels rise, yet p95 latency and 5xx error rates stay well within SLOs.

Do not equate **high CPU = outage**. Inspect:

- CPU limits and **throttling** indicators, not raw CPU usage alone.
- Is HPA scaling properly? Does the node pool have capacity?
- Are JVM GC pauses, heap, and thread pools healthy?
- Did requests per second increase proportionally?
- How long has CPU stayed elevated, on which workload, and is a background batch running?

An efficient application can run at high CPU during peak hours without breaching SLOs. Alerts should reflect **user-impact risk** and meaningful saturation rather than paging every time a line crosses 70%.

## 25. Incident: Alerts Vanish When the Metrics Collector Fails

**Scenario:** the collector stops sending metrics. The **`CPU > 90%`** rule stops receiving fresh series; dashboards go blank, yet operators receive zero high-CPU alerts.

CPU did not magically return to normal—**telemetry stopped arriving**.

### Solution

- Add **absence/staleness** alerts for critical metrics where supported by rule evaluation.
- Use independent signals such as **synthetic HTTP availability** or Azure platform health checks.
- Monitor **`ama-metrics` pod health** and ingestion pipelines.
- Verify the **`NoData`** handling mode on every alert rule and data source.
- Maintain a runbook for scrape/ingestion outages so they are never mistaken for healthy apps.

This is the **monitor the monitoring** principle: an observability system must detect when it loses its own telemetry.

## 26. Lab Drill: Reading Metrics on an AKS Lab Environment

### Objective

Complete an observability walkthrough **without needing to create a new cluster, AMW, or Grafana**:

1. Identify an existing AKS cluster and AMW.
2. Verify collectors are sending Kubernetes metrics.
3. Open Grafana with appropriate Viewer/Editor permissions.
4. Write three PromQL queries and build one dashboard.
5. If a lab Java app exists, verify custom metrics and walk through a hypothetical incident.

### Part A: Read-Only Infrastructure Inspection

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<AKS_RESOURCE_GROUP>"
AKS="<EXISTING_AKS_CLUSTER>"

az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{name:name,location:location,azureMonitorProfile:azureMonitorProfile}" \
  --output json
~~~

If you have AKS access:

~~~bash
az aks get-credentials --resource-group "$RG" --name "$AKS"
kubectl config current-context
kubectl get pods -n kube-system | grep ama-metrics
~~~

**Use only your assigned lab cluster.** If the metrics add-on is not enabled yet, do not enable it on a shared cluster without approval since it can incur charges.

### Part B: Open Grafana / AMW

1. In the Portal, open the assigned Azure Managed Grafana workspace.
2. Sign in via Entra ID with your assigned role.
3. Verify the Managed Prometheus / Azure Monitor workspace data source.
4. Open a built-in Kubernetes dashboard; check time range, cluster, and namespace.
5. If no data appears, walk through the layers in Section 22.

### Part C: Create Three PromQL Panels

**Panel 1 — Ready node count**:

~~~promql
sum(kube_node_status_condition{condition="Ready",status="true"})
~~~

**Panel 2 — Memory working set per Pod in the lab namespace**:

~~~promql
sum by (pod) (
  container_memory_working_set_bytes{namespace="observability-demo",container!=""}
)
~~~

**Panel 3 — Desired vs available replica gap**:

~~~promql
sum(
  kube_deployment_spec_replicas{namespace="observability-demo"}
)
-
sum(
  kube_deployment_status_replicas_available{namespace="observability-demo"}
)
~~~

If the namespace does not exist or metrics are filtered, queries return empty. Pick a namespace running a real lab workload and inspect live labels first.

### Part D: Optional Java Application Drill

If your team has a lab Spring Boot Java app:

1. Verify **`micrometer-registry-prometheus`** and **`/actuator/prometheus`**.
2. Confirm custom scraping is configured per Managed Prometheus-supported methods.
3. Query **`jvm_memory_used_bytes`** and **`http_server_requests_seconds_count`** using live labels.
4. Add panels for **RPS**, **JVM heap**, and **readiness**.
5. Update **`APP_MESSAGE`** on the demo app without generating destructive load; watch rollout and metrics.
6. Never expose the metrics endpoint publicly or generate traffic that blows quotas.

### Part E: Record Evidence

| Evidence | Requirement |
|---|---|
| AKS | Cluster, region, metrics add-on status |
| AMW | Workspace ID, region, metric data source |
| Grafana | Workspace URL, data source, user role |
| Collector | Pod/collector status and check timestamp |
| Queries | Three PromQL queries and outputs (or No data root cause) |
| Java | Metric names, labels, and endpoint scrape verification if applicable |
| Alerts | Propose at least one rule tied to SLOs/runbooks |
| Security | Zero leaked secrets, zero public exporters |
| Cost | Estimated/observed metrics ingestion and Grafana costs |

If you only hold Viewer rights, complete the **read-only** steps and design the target dashboard on paper; never escalate privileges just to edit shared dashboards.

## 27. Case Study: Java Rollout Spikes 5xx Errors

A Java Deployment in the **`orders`** namespace just updated. Ten minutes later, dashboards show:

~~~text
HTTP RPS         : 150 -> 160 requests/second
5xx ratio        : 0.2% -> 8.0%
p95 latency      : 200 ms -> 1700 ms
Available Pods   : 3 / 3
CPU usage        : no significant increase
DB pool waiting  : surged sharply
~~~

**Observation:** Ready Pods do not guarantee healthy business behavior. Signals point to the API waiting on database connections or a downstream dependency—potentially due to a code change, connection pool config, DB overload, or external service slowdown.

### Troubleshooting Workflow

1. Confirm time range, data source, and 5xx/latency queries use exact labels/releases.
2. Inspect Deployment revision, rollout timestamp, and configuration diffs.
3. Correlate **Java logs/traces**, DB pool metrics, and database health.
4. Evaluate app rollback if the new release caused it and data schemas are compatible.
5. If rolling back, watch 5xx/p95 charts recover—never declare success just because `kubectl rollout status` completed.
6. Add an alert rule with sensible thresholds and `for` duration; document RCA and regression tests.

**Never assume** the Kubernetes node is faulty when Pods are Ready and CPU is uncrowded. Metrics narrow down where to look; logs and traces explain why.

## 28. Case Study: Grafana Shows "No Data" After an IAM Change

A team just tightened RBAC. Users can still sign in to Azure Managed Grafana and view dashboard folders, yet every Prometheus panel returns a permission error or No data.

### Diagnosis

1. Confirm the data source points to the exact AMW.
2. Check which system-assigned or user-assigned **managed identity** Grafana uses.
3. Check whether **Monitoring Data Reader** (or integration-required role) is still assigned to that identity at the target AMW scope.
4. Inspect the Azure Activity Log for recent IAM changes.
5. Query AMW directly from another authorized principal to separate data loss from a permission failure.
6. Check RBAC propagation delay and data source metadata.

**Never** grant subscription-wide Owner/Contributor to Grafana just to test. Restore **least-privilege read access at the required scope** and verify the data source works again.

## 29. Production Checklist for AKS Observability

- [ ] Defined clear operational targets: SLOs, latency, error budgets, capacity, and security.
- [ ] Separated metrics, logs, and traces without assuming Managed Prometheus replaces logging.
- [ ] Placed AMW and Azure Managed Grafana in approved regions and subscriptions.
- [ ] Enabled the managed metrics add-on on the target cluster with healthy collectors and fresh data.
- [ ] Verified Kubernetes default targets and metric keep-lists in AMW.
- [ ] Java exporters expose Actuator + Micrometer Prometheus privately.
- [ ] Custom scrapes are explicitly configured via add-on-supported mechanisms; annotations alone are not assumed sufficient.
- [ ] PromQL selectors use live labels; dashboards separate cluster, namespace, and workload.
- [ ] Panels cover node readiness, replicas, CPU/memory, HTTP RPS/5xx/p95, and JVM health.
- [ ] Alerts cover both SLO/availability breaches and **missing metrics data**.
- [ ] Azure Monitor Prometheus alert rules link to Action Groups, on-call rotations, and runbooks.
- [ ] Grafana managed identity holds read-only AMW access; users hold scoped Viewer/Editor/Admin roles.
- [ ] Zero PII, tokens, or order IDs placed in metric labels.
- [ ] Scrape intervals, retention, recording rules, and series cardinality are bounded.
- [ ] NetworkPolicies, DNS, and private networking tested for collectors, AMW, and Grafana where needed.
- [ ] Logs and traces are correlated to move cleanly from metric anomalies to root cause.
- [ ] Dashboard ownership, versioning/provisioning, and recovery plans exist for accidental deletions.
- [ ] Cost Management budgets and owners track ingestion growth.
- [ ] Rehearsed both an application failure drill and a monitoring-pipeline No-data drill.

## 30. Self-Check Questions

1. How does an Azure Monitor workspace differ from a Log Analytics workspace and an Azure Managed Grafana workspace?
2. Does Managed Prometheus automatically capture all Java application metrics as soon as the AKS metrics add-on is enabled?
3. What role does the **`ama-metrics`** collector play in the architecture?
4. Why is Azure Managed Grafana not the primary metrics storage engine?
5. A user has Grafana Viewer access yet sees No data on dashboards: which other permission layer must you check?
6. Which principal typically needs **Monitoring Data Reader** when connecting Grafana to AMW?
7. How do counters, gauges, and histograms differ? When should you use **`rate()`**?
8. Why can a PromQL query filtering **`job="java-api"`** return empty even when the metric exists?
9. Is **`label_values`** in a Grafana variable a standard PromQL function?
10. Why don't **`prometheus.io/scrape`** Pod annotations alone guarantee Managed Prometheus scrapes your Pod?
11. Which dependencies and configuration does Spring Boot need to expose **`/actuator/prometheus`**?
12. What is required to calculate p95 latency using **`histogram_quantile`**?
13. When Pods are Ready yet HTTP 5xx spikes, which metrics and logs should you inspect?
14. Why shouldn't `customerId` or `orderId` be placed in metric labels?
15. With 1,000 series, how does sample volume roughly change if you scrape every 15 seconds instead of 30 seconds?
16. Does Grafana showing No data prove the application has stopped running?
17. Which type of alert detects when a collector stops sending metrics?
18. Why should alert rules specify time windows, `for` durations, and noise controls?
19. Which type of cost can Prometheus recording rules increase?
20. Distinguish the **`Java exporter → collector`**, **`collector → AMW`**, and **`Grafana → AMW`** paths when troubleshooting networking.
21. Which labels and filters must a multi-cluster dashboard enforce to avoid mixing cluster data?
22. Why shouldn't Grafana's managed identity be granted subscription-wide Owner?

## 31. References

- [Azure Monitor managed service for Prometheus](https://learn.microsoft.com/azure/azure-monitor/metrics/prometheus-metrics-overview) — service architecture and capabilities.
- [Monitor AKS with Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-monitoring-enable) — enabling Kubernetes/AKS metrics collection.
- [Default Prometheus metrics for AKS](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-default) — default targets and metric keep-lists.
- [Configure custom scraping for Managed Prometheus](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-configuration) — collector configuration.
- [Azure Managed Grafana overview](https://learn.microsoft.com/azure/managed-grafana/overview) — Azure-managed dashboard service.
- [Connect Azure Managed Grafana to Azure Monitor workspace](https://learn.microsoft.com/azure/managed-grafana/how-to-connect-azure-monitor-workspace) — data source and permissions setup.
- [Prometheus rule groups in Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-prometheus) — recording/alert rules and Action Groups.
- [Prometheus query language (PromQL)](https://prometheus.io/docs/prometheus/latest/querying/basics/) — instant/range vectors, selectors, and functions.
- [Prometheus best practices for instrumentation](https://prometheus.io/docs/practices/instrumentation/) — labels, metric design, and cardinality.
- [Spring Boot Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer and Prometheus endpoints.
- [Kubernetes resource metrics pipeline](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/) — distinguishing Kubernetes metric pipelines.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating Azure monitoring and resource costs.

**Conclusion:** operating AKS effectively requires visibility into both **Kubernetes infrastructure** and **real application behavior**. Managed Prometheus scrapes and stores metrics in an Azure Monitor workspace; Azure Managed Grafana visualizes and analyzes them using PromQL. For reliable operations, verify the end-to-end pipeline from exporter to collector, collector to AMW, and AMW to Grafana, configuring proper permissions, custom scrapes, dashboards, and alerts. Finally, govern cardinality, ingestion, retention, and costs so your observability stack stays trustworthy, secure, and sustainable.

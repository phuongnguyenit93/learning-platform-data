# Scale Up, Scale Out, and Autoscale Web Applications

> **Chapter:** Web Applications with App Service  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control the cost of an application architecture on Azure.

## Lesson objectives

After this lesson, you will be able to:

1. Distinguish between **scale up**, **scale down**, **scale out**, and **scale in** in Azure App Service.
2. Explain the relationship between a **Web App**, **App Service Plan**, **worker instances**, deployment slots, and costs.
3. Choose between scaling up and scaling out based on CPU, memory, throughput, latency, workload characteristics, and resource limits.
4. Understand two ways to automatically adjust instance counts: **rule/metric-based Azure Monitor autoscale** and **App Service automatic scaling** where supported.
5. Design scale-out/scale-in thresholds, minimum/maximum instance counts, cooldowns, schedules, and alerts.
6. Use the Azure Portal, Azure CLI, and Azure Monitor to inspect configurations, observe performance, and verify changes.
7. Apply **stateless** design principles, health checks, shared session storage, and cost control when scaling instance counts.

## 1. Context: a web application with growing traffic

A ticketing system deployed on Azure App Service serves around 300 requests/second on normal days. When ticket sales open, requests jump suddenly to 1,200 requests/second. Charts show application CPU near 95%, rising HTTP p95 latency, and emerging 5xx errors.

There are at least three options:

- **Scale up:** move the App Service Plan to a higher resource tier, such as workers with more CPU/memory.
- **Scale out:** increase the number of worker instances so multiple copies of the app serve requests in parallel.
- **Autoscale:** let the platform adjust instance counts automatically via metric rules, schedules, or supported automatic mechanisms.

Never jump straight to "add lots more instances" before knowing the cause. If the app is slow due to **SQL Database**, a third-party API, or a lock in code, adding App Service instances may just pile more concurrent requests onto that bottleneck.

### Overview model

~~~mermaid
flowchart TD
    U["Users / clients"]
    IN["App Service entry point / routing"]
    PLAN["App Service Plan\nSKU, region, worker instance count"]
    W1["Worker 1\nWeb App"]
    W2["Worker 2\nWeb App"]
    W3["Worker 3\nWeb App"]
    DB["Database / Cache / Storage"]
    MON["Azure Monitor\nCPU, memory, HTTP, latency"]
    CTRL["Scaling configuration\nmanual / rule-based / automatic"]
    U --> IN
    IN --> W1
    IN --> W2
    IN --> W3
    PLAN -.-> W1
    PLAN -.-> W2
    PLAN -.-> W3
    W1 --> DB
    W2 --> DB
    W3 --> DB
    PLAN -.-> MON --> CTRL
    CTRL -.-> PLAN
~~~

This diagram outlines the conceptual layers; routing architecture and worker details are managed by Azure. A Web App can run across one or more instances of an App Service Plan depending on scaling mode and configuration.

## 2. Web App, App Service Plan, and instances

**Azure App Service** is a PaaS service for running web applications, APIs, and supported web workloads. You manage app code, configuration, connections, and deployments; Azure manages much of the underlying infrastructure.

Entities to distinguish:

| Entity | Function | Example |
| --- | --- | --- |
| **Web App** | Resource holding application configuration and deployment | `shop-api-prod` |
| **App Service Plan (ASP)** | Defines region, OS, tier, capabilities, and allocated compute capacity | `asp-shop-prod` |
| **Worker instance** | A compute unit running the application within the plan | Worker 1, Worker 2 |
| **Deployment slot** | Separate deployment/release environment inside a Web App on supported tiers | `staging`, `production` |
| **Azure Monitor** | Collects and displays metrics/logs, fires alerts, and runs rule-based autoscale where supported | CPU percentage, memory, HTTP responses |
| **Backend dependencies** | Services called by the app; can become independent bottlenecks | Azure SQL, Redis, Blob Storage |

### One plan can run multiple Web Apps

Example:

~~~text
App Service Plan: asp-team-prod
  SKU: Standard S1
  Instances: 2

  Web App: shop-api
  Web App: admin-portal
  Web App: reporting
~~~

In this shared-plan setup, **three applications compete for the same plan compute capacity**. When you scale out the plan from 2 to 4 instances under the typical plan-level model, the **plan's** resource pool and cost change, and all apps on the plan can be affected.

Therefore:

- High CPU in `reporting` can impact `shop-api`.
- Scaling a plan up/out increases cost for the entire plan even if only one app needs more capacity.
- To isolate capacity or cost for a critical app, consider a **dedicated App Service Plan**.
- Some per-app/per-site scaling or automatic scaling features have their own scope depending on tier and settings; do not assume every app can set an independent worker count on the same plan.

### Do not confuse instances with App Service Plans

One plan with 4 instances is **different** from 4 App Service Plans. It is also different from 4 deployment slots. Adding slots does not automatically add dedicated machines to scale production.

## 3. Scale up, scale down, scale out, and scale in

### 3.1. Scale up (vertical scaling)

**Scale up** means moving the plan to a tier/size with more resources or features. Example:

~~~text
Before: App Service Plan Standard S1
After:  App Service Plan Premium v3 P1v3
~~~

This illustrates **changing tier and size**, not an absolute performance comparison for every application. Exact CPU, memory, features, and pricing must be checked against the current SKU at deployment time.

Scale up is appropriate when:

- An instance runs short on **RAM**, hits out-of-memory errors, or spends excessive time in garbage collection.
- The workload needs stronger single-process/request resources that do not split easily across instances.
- You need higher-tier capabilities such as specific networking options, deployment slots, or dedicated features.
- The app is already scaled out, yet **each worker remains resource-starved**.

**Scale down** reduces tier/size to save cost when load drops, provided the target tier still supports the app and leaves enough headroom.

### 3.2. Scale out (horizontal scaling)

**Scale out** increases the number of instances running the app:

~~~text
Before: 2 worker instances
After:  5 worker instances
~~~

Scale out is typically effective when the app:

- Processes requests that can be distributed independently across multiple workers.
- Spends most work in app CPU/memory rather than waiting on a single bottlenecked dependency.
- Is designed to be **stateless** or uses shared session state.
- Has health checks and safe new-instance startup behavior.

**Scale in** decreases the instance count when load subsides. Scale in requires special care around in-flight requests, sessions, background jobs, and local data.

### 3.3. Comparison table

| Criterion | Scale up / down | Scale out / in |
| --- | --- | --- |
| What changes | Worker tier/capacity size | Number of instances |
| Goal | Increase/decrease per-worker capacity or change plan features | Increase/decrease total parallel serving capacity |
| Best for | Memory-bound workloads or hard-to-distribute work | Independent HTTP/API requests, parallelizable workloads |
| Impact on state | Changing SKU can trigger restarts/workload migration | New instances boot; old instances may be removed |
| App preparation | Verify tier, resource, and config compatibility | Stateless design, session store, shared storage, graceful shutdown |
| Cost | Depends on tier/size and instance count | Typically scales proportionally with billed instance count |
| Risk | Paying for an expensive tier while still bottlenecked on dependencies | Splitting compute does not fix DBs, locks, or rate limits |
| Automation | Do not assume autoscale automatically upgrades SKUs | Autoscale typically adjusts **instance count**, not tier |

### 3.4. Decision examples

Suppose there is one instance and:

- CPU 25%, memory near limit, frequent OOM: prioritize evaluating **scale up** or fixing memory leaks.
- CPU 85%, memory 45%, independent requests, database has headroom: evaluate **scale out**.
- CPU 20%, SQL connection count maxed out, SQL query latency rising: investigate the **database and connection pool** first.
- CPU spikes daily from 12:00–13:00 and drops at night: consider **metric- or schedule-based autoscale**.

In all four scenarios, cross-check error rates, latency, and application causes; CPU metrics alone are never enough to decide.

## 4. Limits to check before scaling

### 4.1. SKU/tier and scaling capabilities

App Service spans Free/Shared, Basic, Standard, Premium, and Isolated tiers across multiple generations/variants. **Manual scaling, Azure Monitor autoscale, and App Service automatic scaling are not equally available across all tiers.**

Practical verification steps:

1. Identify the **App Service Plan** SKU/tier, e.g., `S1` or `P1v3`.
2. Inspect scaling options in the Azure Portal for that exact plan/web app.
3. Check maximum instance limits, VM families, region availability, and subscription quotas.
4. Check whether **rule-based autoscale** or another **automatic scaling** mode is active.
5. Check total instance limits and any App Service Environment constraints if applicable.

Never use an instance limit copied from another tier to plan production scaling.

### 4.2. Adding instances does not expand resources infinitely

A scale-out operation can be blocked or fall short because:

- Tier or plan instance limits were reached.
- Subscription/region quota or capacity constraints exist.
- New instances are still booting or warming up.
- A database, external API, or storage service is the bottleneck.
- New instances fail startup/health checks and never enter rotation.
- Session affinity, local filesystems, or background jobs are not multi-instance safe.

**Desired instance count does not immediately equal healthy serving instances.** During traffic surges, account for both scaling lag and worker readiness.

### 4.3. Scaling does not automatically improve whole-system availability

Multiple instances distribute load and reduce single-worker reliance, but:

- All instances in a plan may still reside in one region and share regional outages.
- A single-point-of-failure database remains a single point of failure.
- A bug in a new app release can break **every worker**.
- Zone or multi-region availability must be designed explicitly according to SKU, region, and architecture support.
- Scaling out does not replace backups, disaster recovery, or monitoring.

## 5. Preparing applications before scaling out

An app that runs well on one instance is not guaranteed to work cleanly across multiple instances.

### 5.1. Avoid storing critical sessions in a single worker's memory

Suppose a user logs in and the session lives only in Worker A's RAM:

~~~mermaid
sequenceDiagram
    participant U as User
    participant R as App Service routing
    participant A as Worker A
    participant B as Worker B
    U->>R: Login
    R->>A: Request 1
    A-->>U: Session stored only on Worker A
    U->>R: Request 2
    R->>B: Request routed to Worker B
    B-->>U: Session missing
~~~

To avoid this failure:

- Use a shared session store, such as **Azure Managed Redis** or an appropriate cache/session service.
- Store business state in a database, storage, or shared service designed for concurrency.
- Prefer securely validated stateless tokens/sessions where appropriate.
- Do not rely on **ARR affinity / sticky sessions** as the sole durable fix: workers can recycle, scale in, or shift targets.

### 5.2. Do not rely on the local filesystem for persistent state

App Service provides application storage and temporary storage with different semantics across environments. With multiple instances, never assume files written to a **local temporary directory** appear on other workers or survive restarts.

Data types that generally belong outside workers:

| Data | Where to consider |
| --- | --- |
| Uploaded files | Azure Blob Storage or an appropriate storage service |
| Sessions | Shared cache or session service |
| Job queues | Azure Service Bus, Azure Queue Storage, or an appropriate queue |
| Persistent processing outputs | Database / Blob Storage |
| Critical logs | Application Insights / Log Analytics / centralized log sink |
| Keys / secrets | Azure Key Vault and managed identity per design |

Never use local caches or temp directories as the sole source of business data.

### 5.3. Handling background jobs and singleton tasks

Apps often run timers, scheduled tasks, or queue processors inside the web process. After scaling out, **every instance may start the task simultaneously** unless coordinated in code.

For example, a "send daily report at 00:00" job across 4 instances could send 4 emails or write duplicate records.

Solutions:

- Offload background jobs to Azure Functions, WebJobs, or a dedicated job service.
- Use queues with claim/lock/idempotency mechanisms when multiple workers consume jobs.
- Ensure operations can safely retry.
- Monitor retries and dead-letter queues instead of assuming scale-in stops jobs gracefully.

### 5.4. Warm-up, readiness, and graceful shutdown

New workers need time to:

1. Initialize the runtime and load the application.
2. Open required connections.
3. Load configs, caches, or dependencies.
4. Become ready to serve valid requests.

Design a **Health check** endpoint such as `/health/ready` reflecting real readiness, especially for slow-starting apps. On supported tiers/configs, **Always On** helps avoid idle unloading and cold restarts, but does not replace health checks or capacity planning.

When an instance is removed, the app must handle shutdown cleanly without dropping active requests or corrupting data. Never run multi-hour work inside a single HTTP request if workers can recycle or scale in.

### 5.5. Connection pools and downstream limits

Suppose each instance opens up to 80 database connections:

~~~text
2 instances × 80 connections = 160 possible connections
6 instances × 80 connections = 480 possible connections
~~~

If the database only allows or performs well up to ~250 connections, scaling out to 6 instances can make the system **less stable**. Tune pool limits, caching, pooling strategies, database capacity, and controlled retry/backoff policies.

## 6. Manual scaling in Azure Portal and Azure CLI

### 6.1. Check current state

First select the right tenant/subscription and inspect configuration:

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Only switch subscriptions after verifying the target subscription.
az account set --subscription "<SUBSCRIPTION_ID>"

# Inspect plan configuration.
az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{name:name, location:location, sku:sku.name, tier:sku.tier, capacity:sku.capacity}" \
  --output json

# Inspect the web app and its linked plan.
az webapp show \
  --resource-group rg-web-lab \
  --name shop-api-lab \
  --query "{name:name, state:state, serverFarmId:serverFarmId}" \
  --output json
~~~

Names in these examples are hypothetical; substitute authorized real resources. These read commands do not create or modify resources. If the App Service Plan does not exist, verify your subscription and resource group before continuing.

### 6.2. Scale up via Portal

For operators with App Service Plan management permissions:

1. Open **Azure portal → App Service Plans** and select the plan hosting the Web App.
2. Review the SKU/tier and all apps sharing the plan.
3. Open **Scale up (App Service plan)** or the corresponding pricing plan blade.
4. Compare CPU, memory, capabilities, pricing, and support for the target tier.
5. Apply changes during an approved maintenance window if restart/disruption risk exists.
6. Monitor provisioning, HTTP error rates, p95 latency, and sibling apps afterward.

### 6.3. Scale up via Azure CLI

~~~bash
# Example updating the App Service Plan SKU; CAN incur charges and restarts.
az appservice plan update \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --sku P1v3
~~~

**Do not run this on production without authorization.** It modifies the plan, affecting shared apps/slots, features, billing, and worker lifecycles. Verify target SKU availability in the region and compatibility with your environment.

### 6.4. Manual scale out

In the Portal, use **Scale out (App Service plan)** and choose an instance count permitted by the tier. With CLI:

~~~bash
# Example setting the worker instance count to 3.
# This modifies provisioned resources and billing.
az appservice plan update \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --number-of-workers 3
~~~

Then inspect the updated configuration:

~~~bash
az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{name:name, sku:sku.name, tier:sku.tier, instances:sku.capacity}" \
  --output json
~~~

`sku.capacity` shows the configured plan instance count, while startup time, health, and live traffic reaching new workers must be verified via metrics and logs.

### 6.5. Distinguish config changes from verified impact

Scaling is a **control-plane operation**. Success returned by the Azure API does not guarantee p95 latency has dropped or all instances are ready. After scaling, verify:

- Effective instance count reported by service telemetry.
- Behavior of all sibling apps sharing the plan.
- HTTP 2xx/4xx/5xx counts and response times.
- CPU/memory, DB connections, errors, and logs.
- Cost changes aligning with expectations.

## 7. Metric-based autoscale with Azure Monitor

**Azure Monitor autoscale** defines rules to automatically increase or decrease a supported resource's **instance count** based on metrics or schedules. For eligible App Service Plans, autoscale adjusts plan capacity as load shifts.

### 7.1. Components of an autoscale setting

| Component | Meaning | Example |
| --- | --- | --- |
| **Target resource** | Plan whose instance count will change | `asp-web-prod` |
| **Minimum instances** | Lowest count autoscale is allowed to reach | 2 |
| **Maximum instances** | Highest count autoscale is allowed to reach | 6 |
| **Default instances** | Fallback count for a profile when needed | 2 |
| **Metric rule** | Threshold and evaluation window | Average CPU > 70% over 10 minutes |
| **Scale action** | Add or remove instances | +1 / −1 |
| **Cooldown** | Wait period before re-evaluating scaling after an action | 10–20 minutes |
| **Autoscale profile** | Set of rules/instance bounds for a schedule | Peak hours / off-hours |
| **Notification** | Alerts operators on scale events and failures | Email, webhook, alert where supported |

### 7.2. Small-scale rule example

Suppose a web API is stateless and CPU-bound. The ops team selects:

~~~yaml
# ILLUSTRATIVE CONFIGURATION, not a directly deployable ARM/Bicep file.
target: asp-web-prod
instances:
  min: 2
  default: 2
  max: 6
rules:
  - direction: scale-out
    metric: CPU Percentage
    condition: average > 70% during 10 minutes
    action: add 1 instance
    cooldown: 10 minutes
  - direction: scale-in
    metric: CPU Percentage
    condition: average < 35% during 20 minutes
    action: remove 1 instance
    cooldown: 20 minutes
~~~

Between 35% and 70%, neither rule triggers scaling. This gap between scale-out and scale-in thresholds is called **hysteresis** in control design, reducing flapping when a metric hovers near one boundary.

Values like 70%, 35%, and 10/20 minutes are **examples to tune against real SLOs and data**, not universal Azure defaults for every app.

### 7.3. Why include a scale-in rule and cooldown?

If you only scale out without scaling in, costs stay high after traffic drops. Conversely, scaling in too aggressively causes oscillation (flapping):

~~~text
CPU 72% → add instance
CPU 32% → remove instance
CPU 75% → add instance
...
~~~

**Cooldowns, asymmetric thresholds, and evaluation windows** damp oscillation. The autoscale service also applies internal safeguards and rule evaluations; do not expect instant changes on every single metric sample.

### 7.4. Never rely solely on CPU

CPU works well for compute-bound workloads, but:

- Waiting on a database/API: low CPU while request latency climbs.
- Memory leak: normal CPU while memory climbs continuously.
- Long queue despite low CPU because the app processes on a single thread.
- A batch job burning CPU on a shared plan can trigger autoscale for unrelated Web Apps.

Depending on published metrics, consider **memory usage, HTTP queue length, request count, response time**, or suitable custom metrics. Verify which metrics are supported as autoscale signals for your resource at deployment time.

**Good rules target the real bottleneck**, not merely whichever metric is easiest to view in the Portal.

### 7.5. Schedule-based scaling

For predictable daily peaks, such as 18:00–22:00, use scheduled autoscale profiles:

| Window | Min | Default | Max | Purpose |
| --- | ---: | ---: | ---: | --- |
| Normal daytime | 2 | 2 | 5 | Lower baseline cost |
| Known sale hours | 4 | 4 | 10 | Pre-warmed capacity ahead of surge |
| Overnight | 2 | 2 | 4 | Appropriate scale-in bounds |

Numbers are illustrative. Configure timezones and daylight-saving transitions carefully, and ensure profiles do not overlap unpredictably.

**Combining rules and schedules** pre-stages capacity ahead of metric spikes; pure metric autoscale always lags behind collection, evaluation, provisioning, and warm-up delays.

## 8. Creating and verifying Azure Monitor autoscale

### 8.1. Configuring via Azure Portal

On an App Service Plan tier supporting rule-based autoscale:

1. Open the **App Service Plan** in the Azure Portal; verify region, SKU, hosted Web Apps, and current instance count.
2. Open **Scale out** or the relevant **Autoscale** blade (the UI may link to **Azure Monitor autoscale settings** depending on Portal version).
3. Choose **custom/rule-based autoscale** and create a profile with min, default, and max instances.
4. Add a **scale-out rule** matching your analyzed metric and window (e.g., average CPU > 70% over 10 minutes, add 1 instance).
5. Add a **scale-in rule** with a lower threshold and longer window (e.g., CPU < 35% over 20 minutes, remove 1 instance).
6. Configure cooldowns, notifications, and schedules as needed; ensure min/max stay within resource limits.
7. Save the autoscale setting, then inspect **Scale history / Run history / Activity Log** and instance count changes.
8. Monitor latency, 5xx errors, CPU/memory, and backend errors over at least one representative load cycle.

Verify whether the system uses rule-based autoscale **or another automatic scaling mode** before adding settings. Never run two conflicting autoscalers against the same target.

### 8.2. Reading resource ID and supported metrics via CLI

~~~bash
# Retrieve the App Service Plan Resource ID.
PLAN_ID=$(az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query id \
  --output tsv)

echo "$PLAN_ID"

# List autoscale settings in the resource group.
az monitor autoscale list \
  --resource-group rg-web-lab \
  --output table

# List actual metric definitions supported on the plan.
az monitor metrics list-definitions \
  --resource "$PLAN_ID" \
  --output table
~~~

These commands are read-only. Verify **exact metric names and units** rather than guessing from a sample dashboard—CPU and memory percentages can differ across resource types or APIs.

### 8.3. Creating an autoscale setting via CLI (modifies resources)

In an authorized lab on a supported tier, Azure CLI provides autoscale management commands:

~~~bash
# WRITE OPERATION: create an autoscale setting for the plan.
az monitor autoscale create \
  --resource-group rg-web-lab \
  --name autoscale-asp-web-lab \
  --resource "$PLAN_ID" \
  --min-count 2 \
  --max-count 6 \
  --count 2
~~~

This creates the setting with instance bounds. **You must still add metric rules/profiles** to achieve load-driven scaling as designed. Arguments, features, and required permissions can vary by CLI/extension version; check `az monitor autoscale create --help` before running.

Continue in the Azure Portal to add CPU rules and cooldowns, or inspect `az monitor autoscale rule create --help` and supply exact available metric names. Never copy a rule expression from another resource type without checking.

### 8.4. Confirming the autoscale setting is active

~~~bash
az monitor autoscale show \
  --resource-group rg-web-lab \
  --name autoscale-asp-web-lab \
  --output json

az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{sku:sku.name, configuredInstances:sku.capacity}" \
  --output json
~~~

Distinguish three verification checks:

- **Setting is valid:** min/max, rules, and cooldowns match approval.
- **Scale action fired:** run history/activity logs show count adjustments at expected times.
- **App improved:** SLOs are met, instances are healthy, and no 5xx spikes or DB overload occurred.

An autoscale setting working mechanically does not automatically mean users see better performance.

## 9. App Service automatic scaling vs. rule-based autoscale

Azure App Service offers **automatic scaling** driven by HTTP traffic for eligible App Service Plans/tiers. This differs from **Azure Monitor autoscale**, which relies on user-defined metric/schedule rules.

### 9.1. How automatic scaling thinks

Where supported, App Service automatically adjusts the instance count serving **individual web apps** based on HTTP traffic and mode parameters like always-ready/max limits.

Common concepts:

- **Always ready instances:** minimum warm instances kept available for the app in supported configurations.
- **Maximum scale limit:** ceiling on instances for the app within allowed limits.
- **Prewarmed instances:** buffer capacity prepared by the feature to absorb bursts.
- **Traffic-based scaling:** the managed service decides when to scale from incoming traffic rather than requiring users to tune a 70% CPU rule.

Availability, configuration, Portal UI placement, and limits vary by **tier, region, App Service Plan type, and service version**. Do not assume this feature exists on Basic or in every App Service environment.

### 9.2. Comparing the two automatic modes

| Criterion | Azure Monitor autoscale | App Service automatic scaling |
| --- | --- | --- |
| Trigger | Operator-defined metric rules or schedules | App Service traffic-driven automatic scaling where supported |
| Typical scope | Adjusts App Service Plan instance count | Can scale per Web App within feature configuration bounds |
| User sets explicit CPU thresholds? | Yes, if choosing CPU metrics | Not the primary model |
| Key settings | Min/default/max, metric rules, cooldowns, profiles | Always-ready, maximum scale limit, and related options |
| Best when | Need granular control over thresholds, schedules, custom metrics | HTTP workloads wanting managed scaling with minimal manual rules |
| Support conditions | Depends on tier, SKU, and target resource | Depends on specific App Service tiers/features |
| Limits | Subject to metric lag, min/max, quotas, warm-up | Still bounded by ceilings, warm-up, dependency bottlenecks, cost |

If the Portal offers mode selection, use **one appropriate mechanism** and review existing settings. Never assume two autoscalers can overwrite instance counts together without conflict.

### 9.3. Automatic scaling does not solve everything

Even with managed worker scaling, applications still need:

- Stateless sessions and shared dependencies.
- Readiness/health checks.
- Database capacity and connection pooling.
- Measurement of p95 latency, HTTP errors, and capacity.
- Budget-aligned min/max limits.
- Incident playbooks for when scaling hits the ceiling yet the app remains slow.

If one Web App on a shared plan has a wildly different traffic profile from siblings, automatic scaling is worth evaluating **when per-app scaling is supported**; alternatively, move it to its own plan for clean resource and cost isolation.

## 10. Measuring scaling effectiveness with Azure Monitor and Application Insights

### 10.1. Look beyond CPU

Before and after a scaling change, capture the same telemetry groups:

| Metric group | Purpose |
| --- | --- |
| **CPU Percentage** | Spot compute-bound workloads or background CPU contention |
| **Memory Percentage / Working Set** | Check memory pressure, garbage collection, and OOM |
| **Requests/Second** | Measure incoming load and achieved throughput |
| **HTTP 5xx** | Track server, backend, or application errors |
| **Response time, p95/p99** | Validate actual latency SLOs |
| **HTTP queue length** | Detect requests queuing when workers lack capacity |
| **Instance count** | Confirm autoscale changed capacity |
| **Restarts, availability, health check** | Verify workers are genuinely healthy |
| **Dependency latency** | Check if SQL, cache, storage, or external APIs are overloaded |
| **Cost and budget** | Weigh compute/monitoring spend against benefit |

Not every metric is available on every SKU and telemetry setup. Check the actual metric catalog for your **App Service Plan, Web App, Application Insights**, or logging backend.

### 10.2. Plan-level vs. app-level metrics

- **App Service Plan** metrics may aggregate load across all apps/slots sharing compute.
- **Web App** metrics reflect an individual app's traffic, status codes, or response times.
- **Application Insights** shows requests, dependencies, exceptions, and per-operation latency when instrumented.
- Azure SQL or cache metrics must be inspected separately, as those services do not automatically scale with the App Service Plan.

If a plan hosts both `shop-api` and `reporting`, high plan CPU may stem from a `reporting` job. Plan CPU autoscale still reacts to aggregate load, but does not prove `shop-api` is the culprit.

### 10.3. Example KQL queries with Application Insights

If the environment collects request telemetry into Application Insights' `requests` table:

~~~kusto
requests
| where timestamp >= ago(2h)
| summarize
    TotalRequests = count(),
    Failures = countif(success == false),
    P95Latency = percentile(duration, 95)
    by bin(timestamp, 5m)
| order by timestamp asc
~~~

This query correlates traffic surges with p95 latency and failed requests. **Table and field names can differ** in workspace-based resource-specific tables or alternative observability pipelines; inspect your real schema and adapt accordingly.

To locate slow operations:

~~~kusto
requests
| where timestamp >= ago(1h)
| summarize
    Requests = count(),
    P95Latency = percentile(duration, 95),
    FailureCount = countif(success == false)
    by name
| order by P95Latency desc
~~~

If results show only `POST /checkout` is slow while other endpoints remain fast, investigate dependencies, locks, or queries in checkout before concluding you need more instances.

### 10.4. Tracking autoscale events

Use:

- **Azure Monitor autoscale history / Activity Log**.
- Plan/web app metrics over time.
- Application Insights or Log Analytics.
- Azure Monitor alerts when instance counts approach max or SLOs degrade.
- **Cost Management** to track compute and supporting services.

If autoscale does not fire, check whether the setting is enabled, which profile is active, metric conditions, aggregation windows, quotas, and run history. Do not assume it is broken just because CPU spiked for a few seconds.

## 11. Sizing exercise: 2 or 10 instances?

### 11.1. Estimating from measured throughput

Suppose lab load tests show one instance handles roughly **150 requests/second** while keeping p95 latency below the SLO threshold. Peak hours expect **1,200 requests/second**.

Without headroom:

\[
\text{Minimum instances under a simple linear model}
=
\left\lceil\frac{1200}{150}\right\rceil
=8
\]

If proactively targeting ~80% of measured capacity for headroom:

\[
N
=
\left\lceil\frac{1200}{150\times0.8}\right\rceil
=
10
\]

**Preliminary conclusion:** consider around 10 instances to serve the assumed workload linearly.

This is only an **estimation model**, not a guarantee that 10 instances always achieve 1,200 RPS. Real throughput depends on concurrency, response sizes, databases, caching, warm-up, routing, instance variance, and cost.

### 11.2. Adding instances can overload the database

Suppose each app instance has a connection pool capped at 50 connections:

~~~text
2 instances × 50 connections = 100
8 instances × 50 connections = 400
10 instances × 50 connections = 500
~~~

If the database handles roughly 300 useful connections under real load, 10 instances can trigger SQL contention and request timeouts even while web app CPU stays low.

Optimize queries, add caching, tune connection pools, and size the backend before raising max instances to 10. Autoscale **max count must have an engineering basis**, not just a budget guess.

### 11.3. Estimating compute instance-hours

Suppose a day has 21 hours at 2 instances and 3 peak sale hours at 10 instances on the same tier/SKU:

~~~text
21 hours × 2 instances = 42 instance-hours
 3 hours × 10 instances = 30 instance-hours
Total                   = 72 instance-hours/day
~~~

If running 10 instances statically all day:

~~~text
24 hours × 10 instances = 240 instance-hours/day
~~~

Under this simplified calculation, autoscale reduces compute usage from 240 to 72 instance-hours/day. However, **actual billing** also depends on provisioning/scale-in timing, tier unit rates, billing granularity, features on the plan, other services, and current pricing rules. Do not treat this ratio as an exact percentage invoice reduction.

### 11.4. Traffic jumping within 20 seconds at sale open

If traffic leaps from 200 to 1,200 RPS in 20 seconds, a "CPU > 70% averaged over 10 minutes" rule **will react too slowly** due to metric aggregation and instance boot times.

Consider:

- **Scheduled pre-scaling** ahead of known sale openings.
- Maintaining enough minimum instances for unpredictable bursts.
- Caching/CDNs, queues, and rate limiting to smooth peaks.
- Load-testing warm-up behavior of new workers.
- Tuning rules on real telemetry without making thresholds so twitchy they flap.

## 12. When autoscale fails to help or causes errors

### 12.1. Low CPU, high response time

**Symptom:** App Service Plan CPU is only 25%, yet API p95 latency jumps from 250 ms to 4 seconds. Azure SQL shows slow queries.

**Analysis:** requests are blocked waiting on the database. Adding web instances may push even more concurrent load onto SQL.

**Remediation:** analyze queries/indexes, connection pools, retries, caching, and SQL capacity. Scale web instances only when evidence proves the web tier is the bottleneck.

### 12.2. Per-instance memory leak

**Symptom:** every few hours, a worker's memory climbs to the limit and the process restarts. Scaling out from 2 to 5 instances slows the buildup, yet crashes still recur.

**Analysis:** scaling out buys time before hitting the ceiling, but does not eliminate a memory leak.

**Remediation:** capture heap dumps/diagnostics securely, inspect object retention and connection/resource leaks, patch code, and load test. Temporary scale-up can soften impact while fixing the root cause.

### 12.3. In-memory sessions dropping users

**Symptom:** after scaling out, users navigate across pages and occasionally lose login sessions.

**Analysis:** sessions live on a single worker. ARR affinity reduces occurrences but worker recycles and scale-in remain risks.

**Remediation:** move session state to a shared store; check shared encryption/session keys, logout, and retry handling. Explicitly test with sticky sessions disabled if your app supports it.

### 12.4. Cron jobs firing multiple times after scale-out

**Symptom:** the system sends the same notification four times after scaling from 1 to 4 instances.

**Analysis:** the timer lives inside the duplicated web process.

**Remediation:** extract scheduled jobs; use queues, distributed locks, or idempotency, and monitor for duplicate executions.

### 12.5. Scale-in kills in-flight work

**Symptom:** a 15-minute report-export HTTP request aborts when an instance scales in or recycles.

**Remediation:** offload long tasks to stateful background processing with queues and retries; have the HTTP request enqueue the job and return a job ID.

### 12.6. Autoscale hits maximum

**Symptom:** high CPU, instance count stuck at 6/6, rising HTTP queue length.

**Remediation:** inspect tier/quotas, optimize app code, evaluate raising max alongside backend capacity, plan a scale-up, or split workloads. Never raise max arbitrarily without checking budget and downstream limits.

### 12.7. Two apps on a shared plan distort metrics

**Symptom:** `shop-api` has light traffic, yet plan CPU spikes nightly due to `reporting`.

**Remediation:** isolate critical workloads onto their own App Service Plan if needed; reschedule batch jobs; select appropriate autoscale signals and check per-app limits. Do not assume both apps need the same worker count.

## 13. Controlling costs when scaling

### 13.1. Compute is billed by App Service Plan and capacity

In typical dedicated plan models, compute billing tracks **tier/size and instance count over time**, not just actual request volume. A plan shared by multiple Web Apps remains a shared compute bill; services like Log Analytics, Application Insights, databases, networking, or storage bill separately.

| Decision | Cost impact |
| --- | --- |
| Scale up to a higher tier/size | Unit price per instance can increase |
| Scale out from 2 to 6 instances | Billed capacity scales with instance count |
| Raise minimum instances | Raises baseline 24/7 spend |
| Scale in when load drops | Reduces instance-hours where configured |
| Dedicated plan per app | Increases isolation, may increase total plans/instances |
| Add Application Insights or longer log retention | Can increase ingestion/retention charges |
| Scale web without scaling database | Web costs rise without guaranteed SLO gains |

### 13.2. Design deliberate boundaries

A sound autoscale profile includes:

- Minimum instances sized for normal traffic and availability needs.
- Maximum instances sufficient for projected peaks while protecting budgets and downstreams.
- Scale-in rules to avoid holding excess capacity too long.
- Alerts when pinned at max or when autoscale fails.
- Real cost reviews after at least one representative load cycle.

Verify costs using the **Azure Pricing Calculator** and **Cost Management** for your actual region, SKU, pricing policy, and subscription. Never copy prices or limits from another region or tier.

## 14. Guided practice: designing autoscale for an API

### 14.1. Simulated telemetry

An API on a Standard/Premium App Service Plan eligible for rule-based autoscale reports the following:

| UTC Time | Instances | Avg CPU | P95 latency | HTTP 5xx |
| --- | ---: | ---: | ---: | ---: |
| 08:00 | 2 | 35% | 180 ms | 0.1% |
| 09:00 | 2 | 78% | 520 ms | 1.2% |
| 09:15 | 3 | 61% | 340 ms | 0.5% |
| 09:30 | 4 | 48% | 220 ms | 0.2% |
| 12:00 | 4 | 21% | 190 ms | 0.1% |
| 12:40 | 2 | 39% | 200 ms | 0.1% |

These numbers are for drill purposes only; you cannot reverse-engineer Azure's exact rule evaluation solely from six samples.

### 14.2. Task A — Pick min/max and rules

Initial design:

~~~text
min instances: 2
default:       2
max:           6

Scale out: CPU average > 70% over 10 minutes, +1 instance
Scale in:  CPU average < 35% over 20 minutes, -1 instance
Cooldown: 10 minutes after scale out, 20 minutes after scale in
~~~

**Question:** why not use the same 60% threshold for both scale out and scale in?

**Answer:** CPU fluctuating around 60% could cause continuous scale-out/scale-in flapping. A threshold gap reduces oscillation, though real telemetry still needs tuning.

### 14.3. Task B — Evaluate results

- After adding instances, CPU and latency fell. That is a positive signal, though not sole proof of causality—check request rates alongside it.
- Once load drops, scale in gradually to save costs without hurting SLOs.
- If p95 remains high despite low CPU, investigate database or network dependencies.
- If 5xx errors jump whenever a worker is added, inspect startup/health probes, connection pools, and app config.

### 14.4. Task C — Inspect via CLI without modifying resources

Run read-only commands:

~~~bash
az appservice plan show \
  --resource-group rg-web-lab \
  --name asp-web-lab \
  --query "{plan:name, sku:sku.name, instances:sku.capacity}" \
  --output json

az monitor autoscale list \
  --resource-group rg-web-lab \
  --output table

# If an autoscale setting exists:
az monitor autoscale show \
  --resource-group rg-web-lab \
  --name autoscale-asp-web-lab \
  --output json
~~~

Record plan/tier, min/max/profiles, and any rules found. If no autoscale setting appears, state only that **no Azure Monitor autoscale setting exists at the queried scope**; verify whether the app uses another automatic scaling mode before concluding no autoscaling is configured.

### 14.5. Task D — Pre-sale spike scenario

A ticket sale starts at 19:00 and traffic jumps within 30 seconds; a 10-minute average CPU rule will be too slow.

**Proposed design:** schedule a pre-scale before 19:00 with higher minimum instances, warm-up, and load checks; afterward scale down gradually via metrics/schedule. Pair with caching, queues, and valid throttling to avoid flooding the database.

### 14.6. Task E — Database limit

Each instance allows up to 60 DB connections, and the database handles ~300 connections under measured load.

\[
\text{At 6 instances: }6\times60=360
\]

**Answer:** adjust connection pools, concurrency limits, backend capacity, or min/max bounds. Never set max=6 while ignoring downstream limits.

## 15. Operational checklist before and after scaling

### Before making changes

- Confirm exact subscription, plan, tier, and sibling Web Apps on the plan.
- Identify the bottleneck using CPU/memory/latency/error/dependency metrics.
- Verify quotas/tier limits and current instance count.
- Verify whether the app is stateless with shared session/upload storage and idempotent jobs.
- Choose min/max, rules, cooldowns, or schedules aligned with traffic and SLOs.
- Estimate instance-hours, database connections, and cost.
- Ensure proper permissions, testing plan, and rollback plan.

### After making changes

- Confirm config/instance counts took effect and workers are ready.
- Test health endpoints, login/sessions, and representative requests.
- Inspect p95/p99 latency, 5xx errors, CPU/memory, and request queue length.
- Check sibling Web Apps sharing the plan and database load.
- Monitor autoscale history, alerts, and cost impact.
- Document findings, applied changes, and any evidence-based rule adjustments.

## 16. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Scale up means adding more instances." | Scale up changes capacity/tier/size; scale out changes instance count. |
| "Autoscale upgrades S1 to Premium when CPU spikes." | Azure Monitor autoscale typically changes **instance count**, not the SKU. |
| "Scaling out one Web App never affects other apps on the plan." | Plans normally share compute; check specific per-app/automatic scaling modes. |
| "10 instances automatically handle 10x the traffic." | Scalability also depends on databases, caches, locks, networking, and app design. |
| "With ARR affinity, in-memory sessions are safe." | Instances can recycle or scale in; use shared external state. |
| "Scale-in preserves all running background tasks." | Background jobs and long requests require queues, retries, and graceful shutdown. |
| "Autoscale reacts the instant CPU spikes for one second." | Metric windows, rule evaluation, cooldowns, and boot times all add lag. |
| "Scale up is always zero-downtime." | Changing SKU/workers can trigger restarts or transient capacity shifts. |
| "Low CPU means plenty of headroom." | The app may be waiting on DBs, I/O, memory, or queues. |
| "Raising max instances has no downside." | It can blow budgets or overwhelm downstream dependencies. |
| "A deployment slot is a separate plan/VM." | Slots typically share plan compute and add to aggregate load. |
| "No errors in Application Insights means the system is error-free." | Instrumentation, sampling, or routing/logging may be missing. |

## 17. Self-check questions

**Q1.** When should you prefer scale up over scale out?

**Answer:** When per-instance RAM/CPU is exhausted, higher-tier features are needed, or the workload cannot parallelize easily—still verifying the true bottleneck first.

**Q2.** Web Apps A and B share an App Service Plan. If you scale out the plan from 2 to 4 instances, which costs and apps must be checked?

**Answer:** Plan compute cost scales with instances; check both A and B since they share the plan and experience the change together.

**Q3.** CPU drops from 80% to 45% after scaling out, yet p95 latency stays high. What do you investigate?

**Answer:** Databases, caches, networking, external dependencies, locks, and request queues. Lower plan CPU does not prove better SLOs.

**Q4.** Why avoid setting scale out > 70% and scale in < 69% over the same short window?

**Answer:** Too narrow a band triggers constant flapping on normal metric noise. Use tested hysteresis and cooldowns.

**Q5.** An app stores sessions in worker memory. Why does it break easily on scale-out?

**Answer:** Workers do not share in-memory session data. Requests can hit another worker, or instances can restart/scale in; use a shared session store.

**Q6.** Are Azure Monitor autoscale and App Service automatic scaling identical?

**Answer:** Not quite. Azure Monitor autoscale uses metric/schedule rules and typically adjusts plan capacity; App Service automatic scaling uses traffic-based per-app mechanisms on supported tiers.

**Q7.** Each worker sustains 100 RPS within SLO. To serve 450 RPS linearly without headroom, how many workers are needed at minimum?

**Answer:** `ceil(450/100) = 5`. Always reserve headroom and validate dependencies in real deployments.

**Q8.** Autoscale is capped at 6 instances, currently sits at 6/6, and the app is still slow. What should you do?

**Answer:** Inspect tier/quotas, CPU/memory, and app/dependency bottlenecks; consider scaling up, optimizing code, splitting workloads, or raising max deliberately.

**Q9.** What goes wrong if uploaded files are saved in a temporary local directory during scale-out?

**Answer:** Files will not exist across other workers and lack durability. Store them in Blob Storage or an appropriate shared storage service.

**Q10.** Why is scheduled autoscale sometimes more effective than metric-only autoscale?

**Answer:** For predictable peaks, you can add and warm up capacity before traffic hits, eliminating metric evaluation and worker startup lag.

## Key takeaways

- **Scale up/down** changes per-worker capacity or tier; **scale out/in** changes worker instance counts.
- **App Service Plan** is the core compute and billing boundary; multiple Web Apps can share one plan.
- **Azure Monitor autoscale** uses metrics, min/max bounds, cooldowns, and schedules; **App Service automatic scaling** is traffic-driven where supported by the tier.
- Effective autoscale rules rest on **SLOs, real bottlenecks, warm-up times, and downstream capacity**.
- Apps that scale out reliably need **stateless design, shared session stores, queues/idempotency, health checks, and graceful shutdown**.
- Always compare **CPU, memory, request rate, p95/p99 latency, errors, instance count, database metrics, and cost** before and after changes.
- Scaling only succeeds when users experience better service within target cost and reliability bounds.

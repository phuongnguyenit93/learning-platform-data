# Monitoring, Load Testing, and System Recovery Drill Lab

## 1. Objectives and Lab Context

A system is operationally ready only when engineering can answer with **evidence**: is the service healthy from the user's perspective, how much load can it sustain, where are the bottlenecks, do alerts reach the right person, and how quickly does it recover when a component fails? Seeing Azure resources provision cleanly or report `Running` answers none of these questions.

In the **Architecture and Capstone Labs** chapter of the `CLOUD_PROVIDERS_AZURE` module, this lesson brings together subscriptions, resource groups, Microsoft Entra ID, VNets, compute, storage, databases, deployment, monitoring, security, and cost to practice three continuous loops:

1. **Monitoring:** define business journeys, measure SLIs/SLOs, collect metrics–logs–traces, create alerts, and test notification paths.
2. **Load testing:** model request traffic, run baseline/ramp/peak/stress tests, pinpoint bottlenecks, and evaluate capacity under degraded components.
3. **Recovery drills:** inject **controlled** faults or test restores in an isolated environment, measure RTO/RPO and data integrity, update runbooks, and run post-incident reviews.

The lesson uses a **hypothetical `orders` application** consisting of an order API, event worker, database, and blob storage. All traffic numbers, thresholds, and durations are **learning assumptions**, not Azure SLAs or built-in guarantees.

### 1.1. Deliverables

By the end of the lab, learners should have:

- A workload diagram and an SLI/SLO and RTO/RPO target table confirmed by the business owner.
- Dashboards and KQL queries tracking request success, latency, dependency errors, and saturation.
- At least one alert with an independently tested notification path and an on-call runbook.
- A bounded load-test scenario with p95/p99, throughput, error rate, resource/cost data, and bottleneck root-cause analysis.
- Evidence from one application failover exercise and one clearly scoped data-restore test.
- A UTC timeline, measured recovery times, acknowledged-data reconciliation, and a post-incident report with action items.

**Safety boundaries:** Never use real user accounts, payment instruments, or customer data for load generation. Never break production, disable backups, or force failovers on live data to complete an exercise.

## 2. Reference Architecture and Evaluation Scope

The `orders` application serves `POST /orders` and `GET /orders/{id}`. Placing an order writes a database record, emits an event to a queue, and a worker writes a confirmation file to blob storage. Users authenticate via Microsoft Entra ID or an appropriate identity provider; the API uses Managed Identity to access supported Azure services.

~~~mermaid
flowchart TB
    U["Users / synthetic tests"] --> EDGE["Azure Front Door / ingress"]
    EDGE --> A["Orders API Region A"]
    EDGE --> B["Orders API Region B (standby)"]
    A --> DB["Azure SQL / primary database"]
    B --> DB
    A --> Q["Queue / message broker"]
    B --> Q
    Q --> WK["Background worker"]
    WK --> ST["Azure Blob Storage"]
    A --> ID["Entra ID / Managed Identity / Key Vault"]
    B --> ID
    MON["Azure Monitor + App Insights + Log Analytics"] -.-> EDGE
    MON -.-> A
    MON -.-> B
    MON -.-> DB
    MON -.-> Q
    MON -.-> WK
    OPS["On-call / runbook / alerts"] -.-> MON
~~~

This is a **logical diagram**. If the database lives in only one region, API Region B still depends on that region for data; having two API deployments **does not prove regional DR**. To practice data failover, the workload must use supported replicas/failover groups or restorable backups.

### 2.1. Inventory Table to Complete

| Component | Scope / owner | Health signals | What impact does failure cause? |
| --- | --- | --- | --- |
| Azure Front Door or ingress | Platform | Origin health, HTTP 5xx, latency | Users cannot reach healthy APIs |
| App Service / VM / AKS API | App / SRE | RPS, success, p95, CPU, memory if available | Cannot create or read orders |
| Database | DBA | Query latency, connections, CPU/IO, throttling, replication | Read/write failures, data risk |
| Queue and worker | App | Backlog, oldest-message-age, dead-letter, retries | Orders created but processing stalls |
| Blob Storage | Data / platform | Request success/latency, capacity, auth failures | Cannot write/read confirmation files |
| Identity / Key Vault | Security | Auth failures, access denied, availability | API cannot obtain tokens or secrets |
| VNet, DNS, Private Endpoint | Network | DNS, TCP/TLS, flows, connection tests | Resources run yet cannot connect |
| Monitoring / alerting | SRE | Ingest health, alert delivery, data latency | Blind to failures or unable to triage |

Add your live environment's **subscription ID, resource group, region, SKU/tier, dependency FQDNs, on-call owner, and dashboard links**. Access only scopes and data you are authorized to view.

### 2.2. Questions You Must Not Skip

- If API Region A fails, does Front Door route requests to Region B? What does the health probe actually check?
- If the database region fails, can API B read/write against recovered data?
- If a worker stops running, does the queue pile up while the API keeps returning HTTP 200?
- If a token or secret expires, do synthetic checks catch it?
- After failover, are all previously confirmed orders intact with zero duplicates?

Every answer requires **separate evidence**. Never declare a system healthy merely because CPU is low.

## 3. Defining SLIs, SLOs, RTO, and RPO Before Testing

### 3.1. SLIs and SLOs

A **Service Level Indicator (SLI)** measures service quality—such as order success rate or p95 latency. A **Service Level Objective (SLO)** is the target for that indicator over a defined window.

Hypothetical exercise targets:

| Metric | Definition | Assumed target |
| --- | --- | --- |
| Availability SLI | Ratio of valid order requests returning non-duplicate success | **≥ 99.9%** monthly |
| API latency | p95 of successful `POST /orders` at normal load | **< 500 ms** |
| Read latency | p95 of `GET /orders/{id}` | **< 300 ms** |
| Asynchronous processing | p95 time from committed order to worker completion | **< 30 s** |
| Peak error rate | Server/timeout error rate during test window | **< 1%** |
| Detection | Time from user impact until alert fires | **≤ 3 minutes** |
| Recovery | Time from `T_impact` until recovery criteria pass | **RTO ≤ 30 minutes** |
| Recovery point | Max business-tolerable data age in recovery | **RPO ≤ 5 minutes**, by data class |

**Warning:** business rules may demand **zero lost confirmed/paid orders**. In that case, a general 5-minute RPO for ordinary records does not excuse losing confirmed orders; use transactions/reconciliation or a stricter data-class RPO.

### 3.2. Choosing the Availability Denominator

Example:

~~~text
Valid business transactions:       100,000
Successful unique transactions:     99,920
Failed/timeout transactions:             80

Success rate = 99,920 / 100,000 × 100% = 99.92%
Error rate   =     80 / 100,000 × 100% = 0.08%
~~~

If the API returns HTTP 200 yet the order was never saved or was duplicated, it is not a business success. Measuring status codes alone is an **HTTP SLI**, not necessarily an **order-flow SLI**.

With a **99.9%** availability SLO over a 30-day month, the time-equivalent error budget is roughly:

~~~text
30 days × 24 hours × 60 minutes × (1 − 0.999)
= 43.2 minutes of equivalent unavailability
~~~

This conversion applies to time-based availability; it is not automatically the error budget if your organization measures **request-based** availability. Keep denominators and SLO windows consistent.

### 3.3. Distinguishing Recovery Time from Recovery Point

- **RTO (Recovery Time Objective):** maximum acceptable time from impact until service meets recovery criteria. Measured in practice as `T_recovered − T_impact` against pre-defined exit checks.
- **RPO (Recovery Point Objective):** maximum acceptable data loss measured by recovery point age. Reconcile **timestamps and IDs of confirmed transactions**—never substitute downtime for RPO.
- **MTTD/MTTR:** mean time to detect/recover across multiple incidents; a single drill yields one observed duration, not a statistically representative mean.

A system can hit a 10-minute RTO and still lose confirmed orders: **such a drill cannot be declared a full pass**.

## 4. Setting Up the Test Zone and Safety Limits

### 4.1. Authorized Blast Scope

A lab exercise should define:

~~~yaml
exercise_id: "orders-observe-load-dr-lab"
environment: "staging-isolated"
subscription: "<test-subscription>"
resource_group: "rg-orders-lab"
business_owner: "<business-role>"
technical_owner: "<sre-role>"
data_classification: "synthetic-only"
allowed_targets:
  - "staging-api"
  - "staging-database"
  - "test-ingress-origin"
prohibited_targets:
  - "production-database"
  - "production-payment-provider"
  - "shared-identity-control-plane"
approvals:
  load_test: "<owner>"
  failure_injection: "<exercise-controller>"
stop_conditions:
  - "Out-of-scope production impact"
  - "Real customer data appears in test path"
  - "Throttling spreads to shared services"
  - "Cost or limits exceed approved thresholds"
cleanup_owner: "<platform-role>"
~~~

This is a governance **exercise charter**, not YAML enforced automatically by Azure. Replace placeholders with authorized targets. Before injecting faults, assign an Exercise Controller empowered to halt the drill.

### 4.2. Isolating Data and Permissions

- Create dedicated synthetic tenants, users, and order IDs; tag with `exercise_id` for filtering afterward.
- Use Managed Identities or least-privilege test identities; never embed tokens, SAS tokens, or secret connection strings in load scripts or reports.
- Block outbound emails/SMS/webhooks to real customers; never call live payment gateways from tests.
- Bound load generator ingress, RPS, and total request counts to protect shared dependencies.
- Record baselines and backup/recovery points before any state-mutating test.
- Configure Azure Cost Management budgets/alerts. **Budgets do not stop billing automatically**, so pair them with quotas, time limits, and a cleanup owner.

### 4.3. Which Scenarios Need Isolation?

| Scenario | Where to run | What NOT to do |
| --- | --- | --- |
| Baseline/ramp load test | Architecture-representative staging with rate caps | Blast unbounded traffic at production |
| Origin failover drill | **Test** Front Door/origin or isolated test route | Disable a production origin just to learn |
| Database restore | Database/resource group **separate from production** | Restore over live data |
| Alert delivery check | Test Action Group + controlled staging alert | Break production to "be sure alerts work" |
| Regional DR test | Tabletop or DR-configured test environment | Arbitrarily force-failover production databases |

## 5. Designing Telemetry: Metrics, Logs, Traces, and Synthetic Checks

No single dashboard covers the whole system. Collect signals across the **control plane**, **data plane**, application, and user experience.

| Telemetry type | What it explains | Azure examples |
| --- | --- | --- |
| **Metrics** | Numeric time series for fast alerting | Azure Monitor resource metrics, CPU, RPS, latency |
| **Application logs** | Business/technical context and specific errors | Structured logs in Log Analytics or Application Insights |
| **Distributed traces** | Request path across API, DB, queue, and downstream | Application Insights / OpenTelemetry instrumentation |
| **Synthetic transactions** | External user-perspective journey checks | Availability tests or controlled synthetic scripts |
| **Management activity** | Who changed resources, when, and outcome | Azure Activity Log |
| **Platform health** | Azure platform events impacting supported resources/regions | Azure Resource Health, Azure Service Health |
| **Business events** | Orders committed, processed, paid, or deduplicated | Independent application/business telemetry |

**Do not confuse control plane with data plane.** Activity Log shows App Service config edits, not API exceptions. Healthy Resource Health does not prove `POST /orders` succeeds.

### 5.1. Fields to Correlate

Emit structured logs containing fields such as:

~~~json
{
  "timestampUtc": "2026-11-20T10:00:00Z",
  "service": "orders-api",
  "environment": "staging",
  "region": "region-a",
  "operation": "create-order",
  "correlationId": "trace-example-0001",
  "synthetic": true,
  "exerciseId": "orders-observe-load-dr-lab",
  "orderId": "lab-order-0001",
  "result": "success",
  "latencyMs": 187
}
~~~

Never log email addresses, phone numbers, tokens, or payment details. Propagate `correlationId` across ingress → API → database/queue/worker. When one request fans out asynchronously, include both **trace IDs and business event IDs** to stitch the full flow.

### 5.2. Meaningful Instrumentation

- Inbound HTTP: method, route template, status, duration, region, instance, test run ID.
- Outbound dependencies: DB/Storage/queue calls, timeouts, retry counts, and duration.
- Background worker: `message_age`, backlog, retries, dead-letters, and handling time.
- Business: `order_created`, `order_processed`, `order_failed`, `order_duplicate_blocked` keyed by unique ID.
- App capacity: CPU, memory, Java GC/heap, thread pools, connection pools (metric availability depends on App Service/VM/AKS and agent).
- Data health: replication lag/recovery state where supported, DB saturation, and backup status.

Align log **retention** with investigation needs, understand sampling behavior, and standardize on UTC clocks. Sampling can skew telemetry request counts and p95 if handled poorly; cross-check against load generator measurements.

## 6. Azure Monitor and Application Insights: First Steps

### 6.1. Set Up Workspace and App Telemetry

In the test environment, configure a **Log Analytics workspace** and **Application Insights** using a workload-supported integration. Select compatible instrumentation for your Java/App Service/AKS runtime and verify:

1. Requests appear with application role/service and timestamps.
2. Dependencies link under the same trace/operation ID.
3. Exceptions and app logs capture diagnostic context without leaking PII.
4. Synthetic tests or staging requests appear on dashboards.
5. On-call staff have read permissions for queries and alerts at the verified scope.

**Azure Monitor does not automatically collect all logs without enabling diagnostic settings/instrumentation.** Check ingestion/retention costs and avoid leaving verbose debug logging on indefinitely during load tests.

### 6.2. Read-Only Azure CLI Commands for Context and Resources

~~~bash
# Check subscription/tenant to avoid investigating the wrong environment.
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

# Inventory resources in the lab resource group.
az resource list \
  --resource-group rg-orders-lab \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

# List metrics actually supported by a specific resource.
az monitor metrics list-definitions \
  --resource "/subscriptions/<subscription-id>/resourceGroups/rg-orders-lab/providers/<provider>/<type>/<resource-name>" \
  -o table
~~~

Values in `<...>` are placeholders. Run `az monitor metrics list` only after confirming exact metric names, namespaces, and aggregations. Managed PaaS services do not always expose identical CPU/memory metrics as VMs.

### 6.3. Checking Control-Plane Changes Around Failures

~~~bash
az monitor activity-log list \
  --resource-group rg-orders-lab \
  --start-time "2026-11-20T09:30:00Z" \
  --end-time "2026-11-20T11:00:00Z" \
  --query "[].{utc:eventTimestamp,operation:operationName.value,status:status.value,correlation:correlationId}" \
  -o table
~~~

UTC timestamps are illustrative. Seeing a deployment coincide with rising 5xx errors is an **investigation lead**, not automatic proof of causation; inspect dependency errors, release diffs, and rollback behavior.

## 7. KQL Queries to Measure SLIs and Spot Bottlenecks

These examples assume the app emits telemetry to **workspace-based Application Insights** with `AppRequests` and `AppDependencies`. Table/column names vary with workspace type, agents, sampling, and collection methods; always check your live schema.

### 7.1. Request Failure Rate and p95 by Minute

~~~kusto
AppRequests
| where TimeGenerated between (
    datetime(2026-11-20T09:30:00Z) .. datetime(2026-11-20T11:00:00Z))
| summarize
    Requests = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false),
    P95LatencyMs = percentile(DurationMs, 95)
  by AppRoleName, bin(TimeGenerated, 1m)
| extend ErrorRatePct =
    iff(Requests == 0, real(null), 100.0 * Failures / Requests)
| order by TimeGenerated asc
~~~

`ItemCount` reflects weighting when telemetry sampling is active. Cross-check sampled p95 estimates against un-sampled measurements when needed; never mistake rounded dashboard numbers for exact latency across every single request.

### 7.2. Breaking Down Critical Endpoints

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false),
    P95Ms = percentile(DurationMs, 95)
  by Name, ResultCode, AppRoleName
| order by Failed desc, P95Ms desc
~~~

Depending on instrumentation, `Name` may be a route template or operation name. If customer IDs appear in logged paths, adjust instrumentation to log **route templates** instead of raw URLs.

### 7.3. Analyzing Dependency Failures

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize
    Calls = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false),
    P95DependencyMs = percentile(DurationMs, 95)
  by AppRoleName, Type, Target
| extend FailureRatePct =
    iff(Calls == 0, real(null), 100.0 * Failures / Calls)
| order by Failures desc
~~~

If API p95 rises alongside database dependency p95, check connection pools, query plans, throttling, and network RTT. Never rush to scale up API CPU before locating the bottleneck.

### 7.4. Query for an Error-Based Alert

~~~kusto
AppRequests
| where TimeGenerated >= ago(5m)
| summarize
    Requests = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false)
| extend FailureRatePct =
    iff(Requests == 0, real(null), 100.0 * Failed / Requests)
| where Requests >= 30 and FailureRatePct > 2.0
~~~

This illustrates a **minimum-volume business condition** requiring at least 30 requests in 5 minutes. If zero requests arrive, this query will not fire even though traffic vanished completely; therefore pair it with a separate **availability/synthetic alert**. When creating Azure Monitor log alerts, review query result handling, aggregation, evaluation frequency, and no-data behavior for the chosen alert rule type.

### 7.5. Measuring Alerts and Notification Paths

A well-formed alert specifies **signal**, **threshold**, **lookback window**, **evaluation frequency**, **severity**, **action group**, and **runbook link**. Group alerts by workload/incident to prevent duplicate notification storms from one root cause. Because Log Analytics has ingestion latency, log-based alerts are not always suited to sub-second detection targets.

## 8. Minimum Dashboard and Alert Suite

### 8.1. On-Call Dashboard

Organize into three tiers:

| Group | Charts / metrics | Question answered |
| --- | --- | --- |
| **Golden signals** | Traffic, errors, latency, saturation | What impact are users experiencing? |
| **Dependencies** | DB latency/errors, queue backlog, storage failures, identity/Key Vault errors | Which layer is bottlenecking? |
| **Recovery & operations** | Region/origin health, failover status, recent deploys, backup health, synthetic checks | Where can we recover and verify? |

Support filters by **subscription, resource group, region, application role, deployment version, and test run ID** where data permits. During load tests, isolate synthetic traffic from real traffic so production SLO reports stay uncorrupted.

### 8.2. Sample Alerts to Configure

| Alert | Illustrative condition | Action |
| --- | --- | --- |
| Synthetic create-order fails | Consecutive failures within approved window | Page on-call for journey outage |
| HTTP error rate | > 2% over 5 minutes with sufficient volume | Open API/ingress runbook |
| p95 API latency | > 500 ms across sufficient sample size | Inspect dependencies and saturation |
| Queue backlog age | Oldest message age > 60 s during active load | Check workers, dead-letters, and retries |
| Database saturation/timeout | Service metrics exceed baseline threshold | DBA + app owner investigate together |
| Region/origin unhealthy | Corresponding probe fails | Check routing and remaining regional capacity |
| Backup/replication unhealthy | Service-specific health event/metric | Data/SRE verify DR readiness |

Calibrate every threshold against your **actual baseline**—do not treat sample values as official Azure defaults.

### 8.3. Configuring an Alert in Azure Portal

1. Select the target resource or workspace under **Azure Monitor → Alerts → Create**.
2. Choose scope and signal (metric or log query), checking units, aggregation, and window.
3. Set thresholds from your SLI/SLO table, including minimum volume guards against noisy small samples.
4. Attach an approved **Action Group**: team email, on-call channel, or workflow.
5. Add description, runbook link, severity, and owner; follow least privilege for recipients.
6. Save; test **Action Group delivery** independently, then inject a controlled staging event if possible to verify **signal-to-alert end-to-end**.

**An Action Group test only checks the notification delivery channel**, not metric/log alert conditions or log ingestion. Conversely, an alert firing does not prove on-call staff received, read, and acted on it.

## 9. Planning Load Tests Before Generating Requests

Load testing aims to answer predefined architectural questions, not merely achieve the highest possible RPS.

### 9.1. Load Test Types

| Type | How it runs | What it reveals |
| --- | --- | --- |
| **Baseline** | Low, steady load confirming initial signals | Baseline latency and instrumentation health |
| **Load / ramp** | Step-wise increase toward target load | Scaling behavior along the load curve |
| **Peak** | Sustained design peak long enough to measure | SLO compliance at peak, backlog, and quotas |
| **Stress** | Push beyond design limits safely | Breaking point, load shedding, and recovery |
| **Spike** | Sudden surge then drop | Autoscale lag, retry storms, cold starts |
| **Soak / endurance** | Moderate load held over hours | Memory leaks, connection leaks, log/disk growth |
| **Resilience under load** | Lose an instance/origin under representative load | N−1 capacity, failover latency, data correctness |

Every test needs **stop conditions**, monitored resources, and an exercise coordinator. Never run extended stress/soak tests in shared environments without budget and capacity approval.

### 9.2. Open vs. Closed Workloads

- **Open model:** schedules arrivals at a target rate (e.g., 60 RPS) regardless of server slowness, exposing behavior under queuing pressure.
- **Closed model:** a fixed pool of virtual users sends requests, waits for replies/think time, then repeats; as the server slows, throughput naturally drops.

Both models have distinct value. When testing **arrival rate** resilience, watch **achieved RPS** alongside target RPS. An under-resourced load generator will cap results before the server bottlenecks.

### 9.3. Business Scenarios and Request Mix

Illustrative peak workload profile:

~~~text
60%: GET /api/catalog               (read-only)
30%: GET /api/orders/{syntheticId}  (read-only on test data)
10%: POST /api/orders               (writes test data, idempotent)

Target total arrival rate:            100 requests/second
Expected read rate:                    90 requests/second
Expected write rate:                   10 requests/second
~~~

Never treat 100 RPS as a standalone KPI. A single `POST` can trigger far more database writes and queue events than a `GET`. Tests must reflect realistic **request mix, payload sizes, tenant/customer distribution, and concurrency**.

**Start safely** with read-only endpoints in staging to verify telemetry. Add write tests only after creating dedicated test tenants/ledgers with record caps, idempotency, and cleanup.

## 10. Writing a Load Test Script with k6

The example below uses **k6** running from a controlled test/local/CI machine. **Do not** assume a k6 JavaScript file imports directly into Azure Load Testing; Azure Load Testing has its own URL-based and supported script flows (such as JMeter), so match tool and format.

### 10.1. k6 Sample Reading the Catalog

Save as `catalog-load.js` in your learner environment. The path and context are **illustrative examples**, not files generated by this lesson.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    catalog_read: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 40,
      maxVUs: 200,
      stages: [
        { duration: '3m', target: 20 },
        { duration: '5m', target: 20 },
        { duration: '3m', target: 60 },
        { duration: '5m', target: 60 },
        { duration: '3m', target: 20 }
      ],
      gracefulStop: '30s'
    }
  },
  thresholds: {
    'http_req_failed{journey:catalog-read}': ['rate<0.01'],
    'http_req_duration{journey:catalog-read}': ['p(95)<500']
  }
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('Missing BASE_URL for staging');
  }

  const headers = {
    'x-test-run-id': __ENV.TEST_RUN_ID || 'staging-load-lab'
  };

  if (__ENV.TEST_TOKEN) {
    headers.Authorization = 'Bearer ' + __ENV.TEST_TOKEN;
  }

  const response = http.get(
    baseUrl + '/api/catalog?limit=20',
    {
      headers,
      tags: { journey: 'catalog-read' },
      timeout: '10s'
    }
  );

  check(response, {
    'catalog status 200': (r) => r.status === 200,
    'response is nonempty': (r) => r.body !== null && r.body.length > 0
  });
}
~~~

**Understanding the script:**

- `ramping-arrival-rate` controls request arrival rate, not directly virtual user count.
- `preAllocatedVUs`/`maxVUs` govern whether the generator has enough VUs to hit the target rate—they do not alter Azure quotas.
- `thresholds` evaluate test pass/fail criteria; they do not protect production.
- `TEST_TOKEN` is a test credential managed safely by the learner; keep tokens out of shell history/logs per security policy.
- Checking status `200` is valid only if the endpoint defines 200 as success; order-creation flows also need idempotency and correctness assertions.

Illustrative run command on a machine with k6 installed:

~~~bash
# Target ONLY an authorized staging URL.
BASE_URL="https://staging-orders.example.com" \
TEST_RUN_ID="lab-2026-11" \
k6 run --summary-export catalog-summary.json catalog-load.js
~~~

The domain is an **example**, not a live endpoint to hit. Before running, verify source IP allowlists, authentication, quotas, rate caps, load generator capacity, and zero impact on production dependencies.

### 10.2. Load Testing with Azure Load Testing

When using **Azure Load Testing**, the general workflow is:

1. Create/verify the Azure Load Testing resource in a test subscription with proper permissions.
2. Select a supported test type—e.g., **URL-based test** for single endpoints or **Apache JMeter test** for multi-step journeys.
3. Target staging, configure step-wise engine counts/load, headers, and secrets via supported secret mechanisms.
4. Define **test failure criteria** on error rate/response time alongside supported Azure resource metrics.
5. Verify **network access** from test engines to private endpoints or staging VNets if used; never assume private resources are automatically reachable.
6. Run a small baseline, confirm test engines aren't self-bottlenecked, then ramp within approved bounds.
7. Export/save results and reconcile with Azure Monitor/Application Insights and Cost Management.

Do not upload `catalog-load.js` into a JMeter flow without proper tooling/conversion. Learners may choose **k6 or Azure Load Testing** per requirements while keeping a consistent metric set for comparisons.

### 10.3. Verifying the Load Generator

Before blaming the server for slowness, check:

- Achieved RPS vs. target RPS; dropped/skipped iterations from insufficient VUs or generator errors.
- Generator CPU/memory/network and realistic geographic placement.
- DNS, TLS handshakes, connection reuse, and client timeouts.
- Whether test data or auth endpoints bottlenecked an external service outside the workload under test.
- k6 p95 vs. App Insights p95: matching time windows, request types, and sampling rules.

An underpowered load generator can make a fragile system **look artificially healthy**.

## 11. Running a Staged Load Test

Reference schedule:

| Phase | Illustrative duration | Target | Checks to perform |
| --- | --- | --- | --- |
| Warm-up | 3 minutes | 5–10 RPS | Ensure instrumentation, dependencies, and caches are warm |
| Baseline | 5 minutes | 20 RPS | Record p50/p95/p99, error rate, CPU, DB/queue |
| Ramp | 3 minutes | 20 → 60 RPS | Watch saturation and scaling events |
| Sustained peak | 10 minutes | 60 RPS | Check SLO compliance, 429s, and queue age |
| Controlled stress (optional) | 3–5 minutes | Ramp within approved cap | Find breaking point and load shedding |
| Cool-down | 5 minutes | 20 RPS then stop | Observe recovery, backlog drain, and lingering resources |

This is a **suggested schedule** and need not match Section 10's script verbatim. When running the sample script, inspect its stages and log exact executed rates. If the system has never served 60 RPS before, start lower with approval.

### 11.1. Measurements to Retain

1. Target RPS vs. achieved RPS per minute; total requests, durations, and status codes.
2. Journey-specific SLIs and p95/p99 latency—never averages alone.
3. CPU/memory/GC, network, connection pools, DB utilization, and query latency.
4. Queue depth and oldest-message-age; verify worker consumption rate.
5. Throttling (HTTP 429 or service quota errors) and retry counts.
6. Autoscale events, quota/instance allocations, scale-out lag, and cold starts if applicable.
7. Synthetic business ledger reconciliation: acknowledged, processed, failed, and duplicated orders.
8. Incurred cost and log ingestion during the test; clean up temporary resources afterward.

### 11.2. Drawing Evidence-Based Conclusions

Hypothetical results table:

| Achieved load | API p95 | 5xx errors | DB p95 | Queue age | Preliminary interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| 20 RPS | 180 ms | 0.1% | 45 ms | 4 s | Within targets |
| 40 RPS | 280 ms | 0.2% | 85 ms | 6 s | Headroom remaining |
| 60 RPS | 490 ms | 0.8% | 180 ms | 23 s | Near SLO boundary |
| 70 RPS | 920 ms | 3.5% | 390 ms | 85 s | Breaches multiple thresholds |

These numbers are **learning examples**, not Azure benchmarks. An initial hypothesis may point to database/queue saturation, yet you must inspect queries, connection pools, service RU/DTU/vCore/IOPS, per-layer telemetry, and retries before concluding.

A chart showing latency rising with traffic does not automatically prove autoscale failed. Capacity might be pinned by the database or an N+1 query introduced in a release.

## 12. Diagnosing Bottlenecks Across CPU, Memory, Disk, Network, and Dependencies

| Symptom | Common causes | Distinguishing evidence | Mitigations to consider |
| --- | --- | --- | --- |
| High app CPU, rising p95 | CPU-bound code, serialization, GC, too few instances | Per-instance CPU, profiler, GC time, request mix | Optimize CPU, scale appropriately, consider caching |
| Memory climbs steadily during soak | Memory leak, unbounded cache, heap pressure | Heap/GC, RSS, OOM/restarts, time series | Leak investigation, memory limits, cache eviction |
| Rising disk latency, slow worker | Disk/IOPS cap, storage throttling | Disk latency/queue, service metrics, IO profile | Batch IO, SKU/throughput, indexing, caching |
| Rising network RTT and timeouts | Routing, DNS, TLS, egress, SNAT exhaustion | Connection errors, RTT, DNS lookup, network metrics | Check routing, pool reuse, scale outbound |
| HTTP 429 | Gateway or downstream quota/throttling | Error/substatus, headers, service metrics, retries | Backoff/jitter, smooth bursts, adjust quotas if justified |
| DB dependency p95 spikes | Query/index, locks, pool, CPU/IO, connections | Query diagnostics, DB metrics, app dependencies | Tune queries/indexes, transactions, pools, or capacity |
| Queue age rises while API returns 200 | Slow consumer, worker errors, unhealthy downstream | Backlog, dead-letters, worker errors | Scale workers safely, fix consumer, dedup |
| All instances fail right after deploy | Bad config, identity, secret, or schema | Deploy history, Activity Log, exceptions | Conditional rollback, verify data compatibility |
| Single region/zone fails | Routing/ingress/zone dependency | Origin probes, health, network, per-region telemetry | Failover per runbook and check n−1 capacity |

**Identify the real bottleneck before upgrading SKUs.** Buying larger VMs raises bills without fixing an unindexed SQL query. Conversely, over-optimizing cost until no headroom remains during a zone outage breaks Reliability.

### 12.1. Retries and Load Shedding

When a backend is overloaded, immediate client retries multiply incoming traffic and worsen outages. Design for:

- Bounded timeouts and retry budgets.
- Exponential backoff, jitter, and honoring `Retry-After` headers when provided.
- Idempotency keys for writes; never duplicate orders or payments.
- Circuit breakers or bulkheads to isolate failing dependencies.
- Returning clear degraded/503 responses instead of hanging connections indefinitely.

Test these mechanisms in staging; never mark a load test "passed" because requests were silently dropped without proper client feedback.

## 13. Recovery Drills: Distinguishing Failure Domains

A "DR drill" is more than clicking a failover button. Pick a **failure domain** and verify its specific claims.

| Failure type | Safe fault injection example | What it proves |
| --- | --- | --- |
| Process/instance | Mark one test backend instance unready | Health probe drops bad instance; survivors carry load |
| Region/API | Disable Region A test origin on test route | Ingress shifts to API Region B; SLIs recover |
| Database/service | Restore backup into test DB or run supported test failover | Data and API remain usable post-recovery |
| Network/identity | Simulate network deny or under-privileged test identity in staging | Detects dependency failure cleanly without widening rights |
| Queue/worker | Pause test consumer for a bounded interval | Backlog alert fires; safe replay without duplicates |
| Full region | Tabletop or DR exercise in backup environment | Runbook, dependencies, routing, data, and scoped RTO/RPO |

Never use an API-only shutdown drill to claim full DR readiness for a **regional or database outage**. Each drill proves only the specific failure domain tested.

### 13.1. Preparing a DR Runbook

A runbook should capture:

~~~yaml
runbook_id: "RB-ORDERS-DR-LAB"
scenario: "staging-region-a-api-unavailable"
environment: "staging-isolated"
incident_commander: "<role>"
exercise_controller: "<role>"
application_owner: "<role>"
database_owner: "<role>"
trigger:
  - "Synthetic create-order failures exceed threshold"
  - "Origin A unhealthy"
go_conditions:
  - "Origin B ready to serve traffic"
  - "Data plane and identity B verified"
  - "No out-of-scope production traffic"
stop_conditions:
  - "Risk of losing acknowledged data"
  - "Injection impacts shared dependencies"
  - "Load exceeds approved limits"
verification:
  - "API SLIs meet targets within recovery window"
  - "Orders created/read accurately with zero duplicates"
  - "Queue and worker recover cleanly"
  - "Metrics, traces, and alerts remain operational"
cleanup:
  - "Restore test origin"
  - "Confirm health of both APIs"
  - "Reconcile temporary resources and costs"
~~~

This is an **exercise artifact**, not an automated configuration for Azure Chaos Studio, Front Door, or failover services. Replace placeholders and confirm approval before executing.

### 13.2. Runbook for a Front Door Origin Failure

In a **staging environment with two independent origins**:

1. Confirm origins A and B are healthy, running identical API versions, and have identical data/secret access.
2. Record baselines under approved test load, including synthetic create/read-order probes.
3. Use config or fault injection **strictly on the test origin** to make API A unhealthy; record `T_impact`.
4. Confirm the Health Probe detects the failure; record `T_detected`.
5. Watch traffic shift to B per routing policy; observe transient errors and connection draining.
6. Run end-to-end synthetic checks verifying orders and queue drain; record `T_recovered` once SLOs hold in the target window.
7. Restore origin A only after verifying full health; inspect traffic and telemetry.
8. Archive changes, timestamps, logs, and outcomes in the report.

**Origin failover time does not depend solely on DNS TTL** when using Front Door/traffic managers; probe intervals, failure thresholds, routing rules, connection states, and client retries all contribute. Never promise fixed failover times without measuring them.

### 13.3. N−1 Capacity When Losing a Zone or Instance

Suppose peak workload demands **600 requests/second**, split across two regions each able to handle **400 RPS max**.

~~~text
Initial healthy capacity = 400 + 400 = 800 RPS
Peak demand              = 600 RPS

After losing one region:
Remaining capacity       = 400 RPS
Deficit                  = 600 − 400 = 200 RPS
~~~

The architecture spans two regions yet **lacks N−1 capacity** to maintain SLOs at peak. Ensure each surviving region can carry load (or scale out fast enough) and that databases, queues, and ingress have matching capacity. These numbers illustrate **measured capacity limits**, not default Azure limits.

## 14. Data Recovery Drills: Backup, Restore, and Correctness

**Having backups does not prove you can restore within RTO.** Separate data-recovery tests from API fault injection to measure data restoration cleanly.

### 14.1. Test Model on Azure SQL or Backup-Capable Services

Example with **Azure SQL Database** where restore is supported:

1. Confirm synthetic data and an available **recovery point** per live retention policy.
2. Create a set of orders with unique IDs; store an ACK ledger independent of the target database.
3. Execute a service-supported restore into a **new test database**, never overwriting production.
4. Verify schemas, tables, permissions, test API connectivity, row counts, and checksums/transaction IDs.
5. Record restore start time, time until DB accepts queries, and time until end-to-end order flow recovers.
6. Reconcile all orders acknowledged prior to the simulated incident against the restored database.
7. Verify private networking, firewalls, RBAC/Entra auth, keys, and monitoring on the restored database.
8. Clean up test resources per procedure after reporting; keep sanitized evidence only.

With Azure Backup/ASR or other database engines, recovery commands and mechanics differ. Never apply Azure SQL failover/restore steps blindly to other Azure services.

### 14.2. Measuring RPO Properly

Hypothetical timestamps:

~~~text
T_impact                  = 10:00:00 UTC
Last acknowledged write   = 09:59:50 UTC
Last recoverable write    = 09:57:30 UTC

Estimated recovery-point gap
  = 09:59:50 − 09:57:30
  = 2 minutes 20 seconds
~~~

This **2-minute 20-second** gap is a timestamp estimate, not full proof every transaction recovered. Check exact `orderId` lists, versions, commit states, checksums, and duplicates. Clocks can skew and replication/ingestion can be asynchronous.

Reconciliation template:

| Synthetic Order ID | ACKed before incident? | Present in restored DB? | Conclusion |
| --- | --- | --- | --- |
| `lab-001` | Yes | Yes, valid checksum | Pass |
| `lab-002` | Yes | No | **Lost acknowledged data – FAIL** |
| `lab-003` | No | No | Client retry/cancel per business flow |
| `lab-004` | Yes | Two logical copies | **Duplicate – FAIL** |

If any acknowledged order is missing, **flag a data integrity failure** even if the recovery-point age fell within a generic RPO. For payment transactions, reconcile against authoritative ledgers rather than blindly re-charging.

### 14.3. Data Failover and Failback

When using geo-replication/failover groups or writable DR replicas:

- Enforce a **single authoritative writer** to prevent split-brain.
- Understand asynchronous replication data-loss windows before forced failovers.
- Verify DNS, listeners, connection pools, and SDK reconnection after role swaps.
- During failback, **re-synchronize writes committed while DR served traffic**, establish source of truth, and shift traffic back deliberately.
- Measure RTO, data correctness, and failback time separately; never equate control-plane "failover succeeded" with full application recovery.

## 15. Measuring Recovery Timelines Consistently

Assign a dedicated timeline scribe using **UTC and multi-source evidence**.

| Milestone | Hypothetical example | Meaning |
| --- | --- | --- |
| `T_impact` | 10:00:00 | Users begin failing primary transactions |
| `T_detected` | 10:02:15 | Alert fires or on-call detects impact |
| `T_declared` | 10:04:00 | Incident Commander confirms and assigns roles |
| `T_mitigated` | 10:11:00 | Traffic shifted / majority of impact mitigated |
| `T_recovered` | 10:14:30 | Transactions meet SLIs/SLOs across defined window |
| `T_closed` | 11:05:00 | Verification, cleanup, and comms completed |

~~~text
Detection time = 10:02:15 − 10:00:00 = 2 minutes 15 seconds
Observed RTO   = 10:14:30 − 10:00:00 = 14 minutes 30 seconds
~~~

Against Section 3's hypothetical targets, detection time and RTO passed. **This says nothing about RPO or data integrity**: those require separate data reconciliation.

### 15.1. "Recovered" Exit Criteria

A system is recovered only when:

- Synthetic **create + read order** checks pass within the observation window.
- Error rates and p95 latency on critical journeys return within SLOs.
- Queue workers drain backlog without unbounded growth or duplicates.
- Database reads/writes and authorization succeed from the active serving region.
- Data risk is verified, or unknown status is explicitly noted without declaring full success.
- Monitoring/alerts run properly on the failover environment, not just primary.

Never set `T_recovered` to when the API/VM first reports `Running` or when an operator clicks the failover button.

## 16. Integrated Scenario: Running Load While Losing an Origin

This capstone combines all three disciplines, strictly **scoped to staging** to avoid unintended impact.

### 16.1. Phased Execution Plan

~~~mermaid
flowchart LR
    A["Baseline telemetry & synthetic ledger"] --> B["Bounded load test"]
    B --> C["Record healthy-region metrics"]
    C --> D["Inject origin A failure"]
    D --> E["Observe alerts & failover"]
    E --> F["Verify API, data, queue"]
    F --> G["Restore origin & observe"]
    G --> H["Review RTO/RPO, SLO, cost"]
    H --> I["Update runbooks & retest"]
~~~

Recommended sequence:

1. Generate a test run ID and **synthetic data**; log acknowledged order counts/IDs independently.
2. Run a baseline at traffic where the system easily meets SLOs.
3. Ramp to an **approved representative load**, never starting at full peak without knowing N−1 capacity.
4. While origin A is healthy, record p95, CPU, dependency errors, worker lag, and ingress split.
5. Have only the Exercise Controller trigger failure on test origin A.
6. Observe alerts, shift to B, and recovery time; if any stop condition hits, halt injection/load and restore safely.
7. Maintain a brief observation window confirming API B handles sustained traffic cleanly.
8. Restore origin A, check traffic/health, and clean up test data/resources.
9. Keep **API failover** results separate from **database restore** results; claim data DR only with direct restore evidence.

### 16.2. Sample Results Table

| Check | Target | Illustrative observation | Evaluation |
| --- | --- | --- | --- |
| Alert detection | ≤ 3 minutes | 2 minutes 15 seconds | Pass |
| API recovery | RTO ≤ 30 minutes | 14 minutes 30 seconds | Pass |
| Peak API error rate | < 1% | 0.7% | Pass |
| p95 create-order | < 500 ms | 620 ms during failure | **Fail** |
| Queue age | < 30 seconds | 75 seconds for 4 minutes | **Fail** |
| Data integrity | Zero lost/duplicate ACKed orders | 1 missing order after restore test | **Fail** |
| Cleanup | Zero stray out-of-scope test resources | Fully cleaned | Pass |

Even though recovery time passed, **the overall exercise cannot be marked PASS** when latency, queue age, and data integrity miss agreed criteria. Mark the overall status `PARTIAL/FAILED` until remediated or formally risk-accepted.

### 16.3. Separating Causation from Correlation

If p95 spikes after disabling origin A, causes might include insufficient B capacity, DB connection pool exhaustion, autoscale lag, or client retries multiplying real traffic. Compare:

- Before/after request counts on A and B.
- App instances, autoscale events, CPU/GC, and DB dependency latency.
- Retry counts, queue age, and origin health flip timestamps.
- Identical transaction mix and achieved RPS—not just target RPS.

State **hypotheses and verification tests**, never jumping to conclusions from a single chart.

## 17. Incident Response Runbook and Azure Support Coordination

A practical runbook defines triggers, scope, owners, and decision branches:

| Step | Action | Evidence | Transition condition |
| --- | --- | --- | --- |
| 1. Validate | Verify alert, SLI, scope, UTC time | Dashboard / synthetic check | Open incident if real impact confirmed |
| 2. Classify | API, DB, queue, network, identity, or Azure platform? | Traces, metrics, Health, Activity Log | Assign owner and investigation track |
| 3. Mitigate | Shed load, shift to healthy origin, approved rollback | Operation ID, change record | Must not risk out-of-scope data |
| 4. Verify | Synthetic create/read, data ledger, queue, p95 | Tests + logs/traces | Meets SLO over verification window |
| 5. Escalate | Escalate internally or to Microsoft if needed | Resource ID, UTC, error codes, correlation ID | Ticket owner assigned |
| 6. Recover | Restore test environment or fail back per runbook | Healthy state, replication/backups | No unverified dependencies remain |
| 7. Review | Timeline, root cause, action items, and retest | PIR report | Owners + acceptance tests assigned |

**Azure Support requests** do not replace an incident commander. If a platform issue or unexplained service behavior is suspected, gather:

- Exact subscription, resource group, region, and **ARM resource ID**.
- UTC time window, business impact, error codes, and real request/correlation IDs.
- Findings from Azure Service Health, Resource Health, Azure Monitor, Activity Log, repro steps, and attempted mitigations.
- Logs/screenshots with **tokens, passwords, SAS, connection strings, and PII redacted**.
- Specific questions for Microsoft support, response owner, and current recovery status.

Support severity/channels depend on your support plan and real business impact. Never open high-severity emergency tickets just for feedback on a non-production lab exercise.

## 18. Post-Incident Review and Turning Findings into Improvements

Run a **post-incident review (PIR)** even for game days: failed drills produce high-value improvements when backed by logs and concrete follow-ups.

### 18.1. Post-Exercise Report Template

~~~markdown
# Orders Monitoring / Load / DR Exercise — <exercise-id>

## Scope
- Subscription, resource group, regions, owner:
- Test targets and stop conditions:
- Architecture, app version, and synthetic dataset:

## Objectives and Results
| SLI/SLO/RTO/RPO | Target | Observed | Pass/Fail |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## UTC Timeline
| UTC | Event | Evidence | Owner |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Load Test
- Tool, RPS/VU config, duration:
- Achieved throughput, p95/p99, error rates:
- Saturation, dependencies, retries, queue:
- Bottleneck hypotheses and checks:

## Resilience / DR
- Failure domain and injection method:
- Traffic routing / recovery:
- Observed RTO:
- Recovery point / transaction ID reconciliation:
- Unverified criteria:

## Safety, Security, and Cost
- Secrets/PII protected:
- Cost and resource cleanup:
- Out-of-scope side effects if any:

## Findings and Actions
| ID | Finding | Owner | Deadline | Acceptance test |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |
~~~

### 18.2. Examples of Verifiable Action Items

| Finding | Action | Closure criteria |
| --- | --- | --- |
| p95 exceeds 500 ms after failover | Increase N−1 capacity and tune DB connection pools/workers | Re-run origin-loss test at representative load; p95 meets SLO |
| Queue backlog hits 75 s | Bound retries, improve worker scaling, add dead-letter alerts | Workers drain backlog within target window |
| Alerts email only, no on-call | Update Action Group / on-call routing, add escalation | Alert delivery and ack tested within SLA |
| DB restore missing an order | Investigate recovery point, reconciliation, and replay/idempotency | Next drill recovers 100% of acknowledged orders |
| Cannot separate synthetic traffic | Add test-run tag/trace field | Queries cleanly isolate test vs. business traffic |
| Log costs exceed forecast | Cut debug noise, set retention and controlled sampling | Ingest cost drops while security/incident telemetry stays intact |

Mark an action `Done` only when a retest or evidence proves behavior **actually improved**. Merging a PR or raising a quota without retesting does not close a finding.

## 19. Budgeting, Governance, and Lab Cleanup

Load testing, telemetry, and multi-region setups all incur costs. Forecast:

- API/worker compute, autoscale instances, and DR environment uptime.
- Database throughput/IO, backups/restores, replicas, and temporary storage.
- Azure Front Door / ingress, data transfer, and networking components.
- Azure Load Testing (if used), billed by virtual user hours / engine runs per pricing model.
- Log Analytics ingestion, retention, Application Insights, and dashboards.
- Synthetic data generation (orders, blobs, queue messages) and cleanup/retention.

**No fixed prices apply in this lesson**; use Azure Cost Management / Pricing Calculator for your region, SKU, subscription, and agreement. Treat budget alerts as notifications, not hard spending cutoffs.

### 19.1. Cleanup Checklist

1. Stop load generators and disable fault injection; verify no unintended test traffic remains.
2. Restore staging Front Door origins/routes and API state; confirm zero production impact.
3. Verify backups/replication on touched resources returned to healthy states.
4. Delete synthetic data by `exercise_id` where safe, keeping sanitized evidence.
5. Delete resources **strictly inside your owned lab scope**, avoiding shared resource groups.
6. Check workers, queues, disks, public IPs, restored DBs, and test assets for lingering charges.
7. Retain only needed alerts, logs, and dashboards for future drills; lower verbose logging levels afterward.
8. Record actual incurred spend once Cost Management updates and obtain owner sign-off.

## 20. Knowledge Checks and Common Misconceptions

**1. If API p95 stays under 500 ms yet order creation duplicates orders, did the test pass?** No. HTTP latency is only one signal; verify **business correctness**. Duplicate orders violate critical integrity criteria.

**2. If an Action Group test email arrives, is alerting tested end-to-end?** No. That tests only the delivery channel; verify the signal, threshold, evaluation window, and live staging firing path.

**3. Why doesn't adding CPU or RU/s fix every bottleneck?** The bottleneck may be missing indexes, connection pools, networking, locks, hot partitions, or downstream dependencies; use telemetry and tests to isolate it.

**4. With APIs in two regions, can you claim full DR readiness?** No. Databases, identity, networking, queues, and storage may still depend on a single region.

**5. Does an RTO under 30 minutes mean RPO was also met?** No. RTO measures service recovery time; RPO and data integrity require reconciling recovery points and transaction IDs.

**6. If a failover test causes 30 seconds of errors, should it go in the report?** Yes. Record the timeline, affected request types, impact, acceptance decision, and mitigations—never just write "failover succeeded."

**7. Should you run stress tests directly on production to find max capacity?** Never without explicit scope, approvals, guardrails, caps, and stop conditions; representative staging is much safer.

**8. Does daily "Backup Success" guarantee data can be restored?** No. Run restore drills, verify permissions/configs, and reconcile restored data.

**9. Why record achieved RPS and load generator metrics?** If the generator fails to send target load, "zero server errors" proves nothing about capacity. Separate generator limits from system limits.

**10. During a game day, can you check only HTTP 200 status codes?** No. Verify end-to-end transactions, queues, data integrity, identity, costs, and recovery of all key SLIs.

## 21. Capstone Exercise and Grading Criteria

### Task A — Establish Monitoring

Based on Section 2's diagram, define at least **four SLIs** across API, database/queue, and user experience. Build dashboards/queries for request rate, p95 latency, dependency errors, and queue backlog. Attach owners, scope, and runbook links to alerts. Note gaps explicitly if live telemetry is unavailable.

### Task B — Load Testing

Design a test covering **baseline, ramp, sustained peak, and cool-down**; specify tools, load, request mix, synthetic data, and stop conditions. Use k6 or supported Azure Load Testing flows. Capture target/achieved RPS, p95/p99, 429s, errors, dependency saturation, and cost.

### Task C — Degraded-Capacity Drill

In **staging**, take API origin A out of rotation via an approved procedure. Measure `T_impact`, `T_detected`, `T_recovered`, failed requests, and API B's capacity. Build an **N−1 capacity** table against design load.

### Task D — Data Recovery

Run a restore test into an isolated resource, or present a tabletop if lacking permissions. Reconcile ACKed IDs against readable data in the restored DB and note RPO measurement limits. Never use a "Backup Success" badge as proof of application recovery.

### Task E — Post-Incident Review and Improvements

Write a report using Section 18's template with at least **three findings**, owners, deadlines, and acceptance tests. Separate met, missed, and unverified criteria, and propose retests after remediation.

### Acceptance Rubric

| Area | Meets bar when |
| --- | --- |
| **SLO/SLI** | Defined around business transactions with consistent measurement windows |
| **Monitoring** | Includes metrics, logs, traces, synthetic checks, and alerts with owners |
| **Load model** | Captures target/achieved RPS, request mix, and safety boundaries |
| **Performance** | Shows p95/p99 and bottleneck evidence rather than guessing from CPU alone |
| **Resilience** | Distinguishes instance, region, API, and database failure domains |
| **RTO/RPO** | Backed by timestamps and a data ledger checking loss/duplicates separately |
| **Security** | Isolated tests, least privilege, zero leaked secrets/PII |
| **Cost** | Budget, temporary resources, and cleanup verified |
| **Decisions** | Includes runbooks, stop/rollback criteria, and approvers |
| **Learning** | Includes PIR, verifiable action items, and retest criteria |

## 22. Summary

Monitoring, load testing, and recovery drills form **one continuous verification loop**, not three disconnected chores:

~~~text
Business goals
  → SLIs/SLOs and RTO/RPO
  → Instrumentation + alerts
  → Baseline and load testing
  → Saturation and dependency analysis
  → Controlled fault injection / restore tests
  → Recovery time measurement and data integrity reconciliation
  → Post-incident review
  → Architecture, runbook improvements, and retesting
~~~

What matters most is **evidence of user experience and data integrity**: HTTP 200 responses, `Running` resources, or `Success` backups are never enough to declare a system healthy or recovered. A reliable Azure workload pairs sound measurement with known performance bounds, N−1 resilience, verified data recovery, disciplined human runbooks, and strict security and cost guardrails.

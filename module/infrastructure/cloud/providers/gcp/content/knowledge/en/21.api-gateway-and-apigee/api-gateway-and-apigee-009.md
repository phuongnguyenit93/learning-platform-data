# Apigee Analytics and API Observability

## Learning Objectives

After this lesson, learners can:

1. Distinguish **Apigee API Analytics**, **API Monitoring**, **Cloud Monitoring**, **Cloud Logging**, and **Debug** by purpose, latency, and data scope.
2. Read traffic, error, latency, and target performance metrics; use **metrics**, **dimensions**, **filters**, and **aggregations** without misinterpreting numbers.
3. Use dashboards, **custom reports**, and the **Apigee Metrics API** to investigate an API proxy; understand custom data collection with **DataCapture**.
4. Establish alerting principles based on **error rate, latency, traffic, and fault source**, correlating investigations with Java applications on Cloud Run/GKE.
5. Design data exports to Cloud Storage/BigQuery, protect personal data, and control IAM, cost, and retention windows.
6. Practice an API incident detection–isolation–remediation workflow with exercises and answers.

## 1. Context: A Running API Is Not Enough—It Must Be Observable

Suppose an e-commerce platform exposes a Java **orders-api** on Cloud Run to the Internet through an **Apigee API proxy**. The proxy verifies API keys/OAuth tokens, enforces **Quota** and **SpikeArrest**, forwards requests to the backend, and returns responses to clients.

One evening, the HTTP 5xx rate spikes while p95 latency breaches the SLO. The operations team needs to know:

- Which API, **environment**, and **proxy revision** are affected?
- Is the failure caused by a **gateway policy**, connectivity to the **target**, or processing errors inside the Java service?
- How many requests are impacted and when did it start?
- Does the issue correlate with a specific developer app/API product, region, or release?
- Should we alert, roll back the proxy or the backend, and which metrics prove recovery?

Within the **CLOUD_PROVIDERS_GCP** module, Apigee connects projects, IAM/VPCs, Cloud Run/GKE/Compute Engine, Cloud SQL, logging, and cost. This lesson focuses on **API lifecycle observability** and operations rather than creating proxies or OAuth security from scratch.

~~~mermaid
flowchart LR
    C["Client / mobile app"] --> G["Apigee API proxy<br/>VerifyAPIKey, Quota, routing"]
    G --> B["Java orders-api<br/>Cloud Run / GKE"]
    B --> DB["Cloud SQL"]
    G --> A["Apigee API Analytics<br/>reports and trends"]
    G --> M["API Monitoring<br/>near-real-time errors / latency"]
    G --> L["Access logs / Debug<br/>transaction evidence"]
    B --> O["Cloud Logging + Monitoring<br/>backend metrics, traces"]
    A --> R["Operations / product team"]
    M --> R
    L --> R
    O --> R
~~~

**Core point:** Apigee sees the **traffic path through the proxy**, but cannot fully explain JVM heap behavior, SQL queries, Pub/Sub queues, or latency inside Cloud Run/GKE. Root-cause diagnosis requires combining telemetry from both the **gateway and the backend**.

## 2. Five Distinct Observability Tools

| Tool | Best-Answered Question | Data Form | Notes |
|---|---|---|---|
| **Apigee API Analytics** | How do traffic, developers/API products, and proxy performance change over days/weeks? | Aggregated metrics, dimensions, dashboards, reports | Has processing delay; not per-request raw logs |
| **Apigee API Monitoring** | Which proxy is currently failing, which fault codes are rising, and in which region? | Near real-time, Timeline/Investigate/Recent, alert integration | Suited for operational triage; figures may differ from Analytics |
| **Cloud Monitoring** | When should we alert/page on-call? Are we breaching an SLO? | Time series, alerting policies, incidents, notification channels | Supported metrics/labels depend on Apigee version and type |
| **Cloud Logging / access logs** | Exactly when did a failed request occur, and what was its status/fault? | Log events | Must be enabled; manage permissions, retention, cost, and PII filtering |
| **Apigee Debug** | What did a policy or flow variable do on a test request? | Trace/session for selected requests | Use under strict access control; does not replace historical analytics |

**Analytics and API Monitoring do not share the same data pipeline.** Numbers can differ due to ingestion speed, aggregation, sampling/bucketing, scope, and retention. Do not expect request counts in both UIs to match down to the exact number within the same minute.

### 2.1. Data Delay and Retention

Per current documentation, after a request passes through a proxy, **API Analytics can take up to 10 minutes** before metrics appear in dashboards, custom reports, or the Metrics API. **API Monitoring** aims for near-real-time signals but does not guarantee every event appears instantaneously.

**Retention depends on telemetry type, Apigee plan, and add-ons.** Analytics docs describe viewing data up to **14 months** with eligible entitlements; some plans/observability paths have shorter windows. API Monitoring metrics use a different window; monitoring log data containing query parameters/user agents is managed by Google under its own retention policy (documentation cites **6 weeks** for this log type). When designing long-term storage, **verify actual entitlements/retention** and plan exports.

On **Apigee Pay-as-you-go**, API Analytics/custom reports may require enabling the **Apigee API Analytics add-on** for the relevant environment and incur charges; Subscription plans have different entitlements. Do not assume every organization has all dashboards/exports enabled by default.

## 3. Thinking in Metrics, Dimensions, Filters, and Time Windows

An analytics report answers: **what are we measuring**, **how are we grouping it**, **what are we filtering**, and **over what time window**?

| Component | Example | Meaning |
|---|---|---|
| **Metric** | `message_count`, `total_response_time`, `policy_error` | Quantitative measurement |
| **Aggregation** | `sum(message_count)`, `avg(total_response_time)` | How values are aggregated |
| **Dimension** | `apiproxy`, `response_status_code`, `developer_app` | How data is grouped |
| **Filter** | `apiproxy = orders-v1; response_status_code >= 500` | Narrows the request set |
| **Time range/unit** | Last 2 hours, grouped every 5 minutes | Window and granularity |

### 3.1. Commonly Used Metrics

| API Metric Name | Common Aggregation | Used For |
|---|---|---|
| **message_count** | sum | Counting API proxy calls |
| **tps** | System-provided TPS value | Transactions per second |
| **is_error** | sum | Failed proxy executions; **not identical to all HTTP 4xx** |
| **policy_error** | sum | Policy errors **causing the proxy to fail** |
| **target_error** | sum | Errors from the backend target |
| **total_response_time** | avg/min/max or percentile per supported API | Total time from proxy receiving request to sending response |
| **target_response_time** | avg/min/max or percentile | Time waiting for the target's response |
| **request_processing_latency** | avg/min/max | Time Apigee spends processing request before sending to target |
| **response_processing_latency** | avg/min/max | Time Apigee spends processing response before returning to client |
| **cache_hit** | sum | Number of ResponseCache hits when caching is configured |

Apigee documentation supports only a **specific set of aggregation functions per metric**—you cannot apply every function to every field. When you need p95/p99, use the **Latency Analysis dashboard** or supported percentile syntax in the Metrics API; **never infer p95 from avg**.

### 3.2. Important Dimensions

| Dimension / API Field | Question |
|---|---|
| **apiproxy** | Which proxy is slowest or failing most? |
| **environment** | How does prod differ from test? |
| **api_product** | Which API product is impacted? |
| **developer_app**, **developer_email** | Which app/developer is driving traffic growth? |
| **response_status_code** | What share of responses returned 200, 401, 429, 500, 503 to clients? |
| **target_response_code** | What did the backend return **before** Apigee potentially altered the status? |
| **request_verb** | How do GET/POST/PUT differ? |
| **target_url**, **target_host** | Which backend/upstream is producing errors? |
| **ax_execution_fault_policy_name** | Which policy caused the flow to fail? |
| **gateway_flow_id** | Helps distinguish transactions when correlating data |

**Do not confuse `response_status_code` with `target_response_code`:** Apigee can reject a request at VerifyAPIKey (before calling the target) or rewrite the status code via RaiseFault/AssignMessage. In those cases, `target_response_code` may be empty or differ from the status returned to the client.

### 3.3. SLI Formulas and Calculation Pitfalls

For a hypothetical SLO of **99.9% of valid requests free of server errors**, define the denominator and error classes clearly:

\[
\text{Server error rate} = \frac{\text{requests with HTTP 5xx}}{\text{total requests in measurement scope}} \times 100\%.
\]

\[
\text{Availability SLI} = 1-\frac{\text{failed requests counted against error budget}}{\text{total valid requests}}.
\]

Example with **100,000 requests** and **140 HTTP 5xx**: the 5xx rate is **0.14%** and availability under this simple definition is **99.86%**, exceeding a **0.10%** error budget. These are hypothetical numbers for practice, not real measurements.

**Note:** 401s from invalid API keys, 429s from Quota/SpikeArrest, and 404s from business logic may or may not count against your SLO depending on the **service contract**. The metric **`sum(is_error)` does not automatically equal "total 5xx."** To count 5xx responses, filter/group by **`response_status_code`** and distinguish client-induced responses from backend/proxy failures.

## 4. Analyzing Latency to Pinpoint Bottlenecks

The **Latency Analysis** dashboard displays **median (p50)**, **p95**, **p99**, and latency breakdowns across proxy and target.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Apigee
    participant T as Target Java API
    C->>P: HTTP request
    Note over P: Request processing latency
    P->>T: Forward request
    Note over P,T: Target response time
    T-->>P: Target response
    Note over P: Response processing latency
    P-->>C: Client response
~~~

| Metric | Start / End | Diagnostic Hint |
|---|---|---|
| **Total response time** | Apigee receives request → returns response | Gateway-observed SLI, including target and overhead |
| **Target response time** | Apigee sends to target → receives response | Java backend, SQL, network path to target |
| **Request processing latency** | Request received → sent to target | Policies, request transformations, auth, quota |
| **Response processing latency** | Target response received → sent to client | Response transformations, policies, serialization/cache |

For requests that actually reach the target, total response time comprises target time plus gateway overhead; **do not sum averages computed over different request populations to assert causation**. On a cache hit, the request **never hits the target**, so there is **no target response time** for that transaction.

### Example Reading p95 and p99

- p50 = **65 ms**, p95 = **350 ms**, p99 = **1,800 ms**.
- Target response time p99 also climbed from **200 ms** to **1,600 ms**.
- Request/response processing inside Apigee remained nearly unchanged.

**Reasonable hypothesis:** the backend or connectivity to the target is slow; inspect **Cloud Run/GKE latency, JVM GC, Cloud SQL query times, and connection pools**. **This alone is not enough to conclude** the DB caused errors without traces/logs.

Conversely, if target latency is steady while request processing latency spikes after adding a policy, investigate policies/flows at the gateway. The p99 metric is sensitive to the tail; **never use averages to hide problems affecting the slowest 1% of requests**.

## 5. Using Built-In Analytics Dashboards

In the Google Cloud console, open **Apigee → Analytics → API metrics**, then select the environment, time range, and proxy to analyze.

| Dashboard | When to Use | Question to Answer |
|---|---|---|
| **API Proxy Performance** | Traffic/TPS shifts | Which proxy spiked, and which version/revision is involved? |
| **Error Code Analysis** | 4xx/5xx increases | Which status codes and faults stand out? |
| **Latency Analysis** | SLA/p95 degrades | Is the proxy or the target spending the time? |
| **Cache Performance** | Cache hit rate drops | Are more requests hitting the backend? |
| **Target Performance** | Upstream slowdown | Which target URL/host has high latency/errors? |

### 5-Step Investigation Workflow

1. Select the **right Apigee organization/environment**, time zone, and time window; record them in the incident.
2. In API Proxy Performance, find **which proxy saw TPS/error changes**.
3. In Error Code Analysis, separate **`response_status_code`** and **`target_response_code`**; determine whether errors come from the gateway or backend.
4. In Latency Analysis and Target Performance, compare **total and target p95/p99** against baseline.
5. Pivot to **API Monitoring → Investigate**, Cloud Logging, or backend traces to confirm the hypothesis with request evidence.

**Do not treat a dashboard covering the last 5 minutes as the complete picture**, since Analytics can lag by up to 10 minutes. During active mitigation, prioritize API Monitoring/Cloud Monitoring and logs; use Analytics to validate broader trends once data settles.

## 6. Custom Reports: Metric × Dimension × Filter

When built-in dashboards do not answer the exact question, open **Apigee → Analytics → Custom reports**. A report defines metrics, aggregations, dimensions, filters, and a time range, rendered as a line or column chart.

### 6.1. Lab Exercise A — Errors by Proxy and Status

**Goal:** identify which proxy had the most errors in the **prod** environment yesterday.

In **Custom reports → Create**:

1. Name it **Orders proxy errors – daily**.
2. Select metrics **Proxy errors (sum)** and **Traffic (sum)** if allowed together in the report.
3. Select dimension **API Proxy**; optionally add **Response Status Code**.
4. Filter **API Proxy = orders-v1** (or related proxies) and environment **prod**.
5. Select **yesterday (UTC or UI-displayed timezone)**, line/column chart, then save/run.
6. Inspect the status breakdown and total requests over the same window; **never divide one proxy's error count by the entire environment's total traffic**.

If you need the **true 5xx rate**, filter **`response_status_code` from 500 to 599** and divide by total requests in that same scope. **Proxy errors** include certain failures that do not map strictly 1:1 to 5xx, so distinguish metrics from status codes.

### 6.2. Real-Time Reports vs. Asynchronous Report Jobs

| Type | Purpose | Limits / Notes |
|---|---|---|
| **Real-time custom report** | Viewed in UI; results typically appear within a few minutes | UI window up to **92 days** per documentation |
| **Asynchronous report job** | Submits a job and retrieves results once complete | Limits of **365 days** and **32 MB** max result size per documentation |
| **Metrics API** | Integrates reports into scripts/apps | Requires permissions, valid range, pagination/filtering |
| **Export Analytics** | Writes data to Cloud Storage/BigQuery | Separate **asynchronous** system, subject to add-on/entitlement |

Do not confuse a "real-time custom report" with API Monitoring. Here **real-time** refers to synchronous report generation/UI rendering—**it does not mean Analytics data has zero ingestion delay**.

### 6.3. Preventing Hidden Skew from Poor Grouping

For example, a report of *average target latency* by **API Proxy** can mask that only **one target host** is slow. Compare the same metric with dimension **`target_url`** and filter **`response_status_code >= 500`**. For a TPS spike, group by **`developer_app`** to see whether one client surged or all clients grew together.

**Avoid high-cardinality dimensions** such as request IDs, raw URLs containing user IDs, or session tokens. They hinder analysis, create PII risk, and increase storage/query load.

## 7. DataCapture: Collecting Custom Business Dimensions

Built-in metrics do not automatically know **client tier** (bronze/silver/gold) or sales channel codes. The **DataCapture policy** lets you persist a **curated value** from proxy flow variables into Analytics; it is an **Extensible policy** and may affect entitlements/cost.

### 7.1. Two Required Steps

1. Create a **Data Collector resource** at the Apigee organization level with a data type and a name starting with **`dc_`**.
2. Add a **DataCapture policy** to an API proxy flow to bind the collector to a validated/mapped **flow variable**.

For example, a backend/VerifyAPIKey flow sets **`client.tier.analytics`** to only one of **bronze, silver, gold, unknown**. **Never** capture raw Authorization headers, API keys, card numbers, emails, or full request bodies just for convenience.

### 7.2. Create a Data Collector

Assume **APIGEE_ORG=shop-apigee-dev** is a real organization and the operator holds permission to create Data Collectors. The command below is for authorized labs only; in a shared organization, adding a resource affects the analytics schema.

~~~bash
export APIGEE_ORG="shop-apigee-dev"
ACCESS_TOKEN="$(gcloud auth print-access-token)"

curl --fail-with-body -sS \
  -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/datacollectors" \
  -d '{
    "name": "dc_client_tier",
    "description": "Low-cardinality subscription tier",
    "type": "STRING"
  }'
~~~

**Do not run if the collector already exists**; check first via UI/API. Names must start with **`dc_`**; do not create two collectors differing only by letter case. Never print **`ACCESS_TOKEN`** or save it in source code. `--fail-with-body` requires a compatible curl version; on older curl, use `-f -sS` and inspect HTTP status.

### 7.3. DataCapture Policy XML

Inside the API proxy bundle, create policy XML **DC-ClientTier.xml** and attach it to the **right flow step** after the variable is populated:

~~~xml
<DataCapture name="DC-ClientTier" continueOnError="true" enabled="true">
  <Capture>
    <DataCollector>dc_client_tier</DataCollector>
    <Collect ref="client.tier.analytics" />
  </Capture>
</DataCapture>
~~~

**Important:**

- The variable **`client.tier.analytics`** **does not exist automatically**: populate it using a controlled ExtractVariables/AssignMessage/JavaScript policy before the DataCapture step.
- `continueOnError="true"` is an illustrative choice so an observability glitch does not fail business requests; where capture is mandatory, select error handling per design.
- One policy can contain multiple **`Capture`** blocks, but each **`DataCollector`** within the same policy must be distinct.
- Never collect sensitive/high-cardinality data; comply with privacy, retention, data residency, and access controls.
- After deploying a new proxy revision, **wait for Analytics data to arrive**, then inspect custom reports by `dc_client_tier`. Display names in UI/API may depend on the resource/data collector configuration.

**Pitfall:** DataCapture does not replace transaction logs or distributed tracing. It captures **selected fields** for aggregation and must not be used to dump full payloads for every request.

## 8. API Monitoring: Detecting and Isolating Incidents

In the Apigee console, open **Proxy Development → API monitoring**. Three useful views:

| View | When to Use | How to Read |
|---|---|---|
| **Timeline** | When did the incident start? | Correlate error/latency spikes against deployments or traffic surges |
| **Investigate** | Which proxy, fault code, region, or status is affected? | Drill down by dimension and fault source |
| **Recent** | Which APIs are currently standing out? | Treemap showing traffic volume and anomaly severity |

### 8.1. Isolating Where Errors Originate

| Signal | First Hypothesis | Verify Next |
|---|---|---|
| `VerifyAPIKey` / `InvalidApiKey`, 401/403 | Client sent missing/invalid/unauthorized key | API product, developer app, VerifyAPIKey policy logs |
| `SpikeArrest` or `QuotaViolation`, typically 429 | Traffic exceeded policy limits | Client identity, policy thresholds, spike baseline |
| `TargetEndpoint` timeout fault / 503 | Connectivity/backend/network issue | Target host, Cloud Run/GKE readiness, VPC, upstream errors |
| **target_error** rising, target `response_code` 500/503 | Java backend returning errors | Java logs, dependency traces, Cloud SQL |
| **policy_error** rising after proxy revision deploy | New or misconfigured policy | Diff proxy revision, run Debug in a safe environment |

Exact error/fault codes depend on actual policies and flows—not every 429 comes from SpikeArrest. For instance, a **backend rate limiter** can return 429 or an Apigee Quota policy can generate 429. Look at **`fault source` and `target_response_code`** rather than guessing from HTTP status alone.

### 8.2. Alerting via Cloud Monitoring

**API Monitoring integrates with Cloud Monitoring alerting**, including:

- **Metric-based alerts:** request/response counts, HTTP 500/503, latency percentiles, or fault counts exceeding thresholds over a window.
- **Log-based alerts:** when a specific event/fault pattern appears in Cloud Logging.

Create alerts under **Monitoring → Alerting → Policies → Create policy**, not via a separate button inside API Monitoring Timeline. Creators need roles such as **`roles/monitoring.alertPolicyEditor`**; managing notification channels requires **`roles/monitoring.notificationChannelEditor`**. Read-only viewers of API Monitoring typically need **`roles/apigee.readOnlyAdmin`** and **`roles/monitoring.viewer`**.

For Apigee and Apigee hybrid **v1.12+**, documentation recommends newer metrics such as:

~~~text
apigee.googleapis.com/proxy/request_count
apigee.googleapis.com/proxy/response_count
apigee.googleapis.com/proxyv2/latencies_percentile
~~~

Available metrics and filterable labels depend on version/environment. You can group by **`env`, `location`, `proxy_name`, `method`, `response_code`, `fault_code`, `fault_source`**, or percentile where supported; inspect **Metrics Explorer** before creating policies.

### 8.3. Alert Design Examples — Not Google Defaults

| SLI | Illustrative Condition | Action |
|---|---|---|
| **5xx rate** | Above **2%** for **5 minutes**, with at least 100 requests | Page on-call, check Error Code Analysis and target health |
| **Latency p95** | Above **800 ms** for **10 consecutive minutes** | Compare target vs. proxy latency, DB latency |
| **429 rate** | **3× baseline** spike, excluding load-test groups | Inspect SpikeArrest/Quota and traffic sources |
| **Throughput drop** | Drops **70%** vs. typical same hour | Check network, client errors, DNS, rollouts |

These are **hypothetical lesson numbers**, not universal SLOs. At 10 requests/5 minutes, 2% is noisy; add a **minimum traffic** condition or multi-window burn-rate alerts. Configure **tested notification channels**, owners/on-call rotations, severity, and runbook links to avoid alert fatigue.

**Alerts do not fix incidents automatically:** an incident brings the team to API Monitoring, followed by confirmation via logs/target telemetry and an authorized rollback or fix.

## 9. Lab Exercise B — Calling the Apigee Metrics API

**Goal:** retrieve **request count**, **proxy failures**, and **target latency** per API proxy without creating a new dashboard. This is the **Apigee management API**, not the client business API URL.

### 9.1. Preparation

You need an active Apigee organization, a **`test`** environment with traffic, appropriate Analytics read permissions, and a logged-in `gcloud` account. Names below are illustrative; replace with real values:

~~~bash
export APIGEE_ORG="shop-apigee-dev"
export APIGEE_ENV="test"
ACCESS_TOKEN="$(gcloud auth print-access-token)"
~~~

**Never commit or print the access token**; the account needs appropriate Apigee analytics permissions. If data comes back empty, check environment, UTC timestamps, analytics add-on/entitlement, and the ~10-minute delay before concluding the API is broken.

### 9.2. Fetch Request Counts per Proxy Over Two Days

~~~bash
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/apiproxy?select=sum(message_count)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&timeUnit=day"
~~~

**Syntax:**

- **`/stats/apiproxy`** groups by dimension **`apiproxy`**. Omit **`/apiproxy`** for environment-level totals.
- **`select=sum(message_count)`** retrieves total proxy calls.
- **`timeRange`** uses format **`MM/DD/YYYY HH:MM~MM/DD/YYYY HH:MM`** with spaces URL-encoded as **`%20`**; this is an example window only.
- **`timeUnit=day`** buckets by day; check chart time zones and date boundaries carefully.

The output JSON contains **`environments`**, **`dimensions`**, and **`metrics`**; numeric values may be returned as float strings. Never sum totals across incompatible dimensions or take unweighted averages of averages.

### 9.3. Fetch Proxy Errors and Target Latency

~~~bash
# Proxy failures (not synonymous with all 5xx response codes)
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/apiproxy?select=sum(is_error)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&timeUnit=day"

# Average target response time by target URL
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/target_url?select=avg(target_response_time)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&timeUnit=day"
~~~

**Reading results accurately:** if a request is rejected by Apigee before reaching the target, **`target_response_time`** may not be recorded. Never divide total proxy requests by target call counts from an unmatched group.

### 9.4. Analyze 5xx Codes by Proxy

~~~bash
curl -f -sS \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/stats/apiproxy?select=sum(message_count)&timeRange=11/17/2026%2000:00~11/18/2026%2023:59&filter=(response_status_code%20ge%20500%20and%20response_status_code%20le%20599)"
~~~

Filtering by **`response_status_code`** counts proxy calls returning 500–599 to clients, which differs from **`sum(is_error)`**. To compute the **5xx ratio**, issue an **unfiltered** query for the same environment/timeRange/dimension and divide per proxy.

### 9.5. The Metrics API Does Not Replace Incident Metrics

The Metrics API has a **maximum `timeRange` of roughly 6 months per query** per documentation; for longer history, use exports or split queries. It supports **`sortby`, `topk`, `limit`, `offset`**, though stable sorting is needed when paginating. On Pay-as-you-go organizations without the **API Analytics add-on**, queries may be rejected even while proxies continue serving traffic.

For minute-level production alerting, use **Cloud Monitoring metrics** rather than polling the Analytics API every few seconds—because ingestion delay, quotas, and data models differ.

## 10. Correlating Apigee with Java Backends, Cloud Logging, and Debug

### 10.1. Correlation ID Across Systems

An HTTP request may traverse **load balancer → Apigee → Cloud Run/GKE → Cloud SQL**. Propagate a safe **correlation ID** along with the request and emit it in telemetry.

~~~text
Client sends request
  ↓
Apigee: request_id = 5b0f... (generated or validated)
  ↓ header: X-Request-ID
Java orders-api: logs request_id + duration + operation
  ↓
Cloud Logging: filter request_id and service
  ↓
Trace backend/SQL to isolate high latency
~~~

If clients send **`X-Request-ID`**, the proxy/backend must **validate** its format and length rather than trusting it blindly. Avoid putting API keys, emails, tokens, or real order numbers into IDs written to logs. For standard distributed tracing, prefer **W3C `traceparent`** per your configured tracing stack.

### 10.2. Java/Spring Boot: Safe Structured Logging

Simple interceptor example illustrating reading/attaching an ID—**not a complete tracing implementation**:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public final class CorrelationInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest req,
                             HttpServletResponse res,
                             Object handler) {
        String id = req.getHeader("X-Request-ID");
        if (id == null || !id.matches("[A-Za-z0-9_-]{8,64}")) {
            id = UUID.randomUUID().toString();
        }
        req.setAttribute("correlationId", id);
        res.setHeader("X-Request-ID", id);
        return true;
    }
}
~~~

**Note:** you must **register the interceptor** in Spring MVC for it to run, e.g., via **`WebMvcConfigurer.addInterceptors`**. Test tracing/correlation on the live request path. Never log raw `Authorization`/`Cookie` headers or full payloads; log only **method, route template, status, duration, proxy/backend release version, and safe correlation ID**.

### 10.3. Debug and Access Logs

**Apigee Debug** fits once an error is isolated to a proxy policy: select the right environment/proxy, start a time-bounded session, and send a **non-PII test request** to inspect flow variables, policy execution, and target calls.

**Apigee access logs** record transaction details at ingress and help diagnose edge cases that aggregated metrics miss, such as ingress status **`0`**. Check Logging/IAM/retention before exporting logs to external systems.

Never enable full-payload logging for every production request merely because of one rare bug: it increases cost, latency/volume, and risks violating data-protection policies.

### 10.4. Choosing the Right Source

| If You See | Investigate Next |
|---|---|
| **Policy error** rising after a proxy revision | Diff policies, Apigee Debug, and proxy deployment history |
| **Target error** rising with target `response_code=503` | Cloud Run/GKE service logs, readiness, resource quotas |
| **Target latency** rising while proxy overhead stays flat | Backend traces, JVM GC, Cloud SQL query statistics |
| **No target response code**, 401/429 at proxy | VerifyAPIKey/OAuth, Quota/SpikeArrest, API product/app |
| **HTTP 200 from proxy** but UI reports wrong data | Business logs/traces, validation, response transformations |

**Do not assume Cloud Trace automatically produces end-to-end traces** just because Apigee Analytics is enabled. Configure trace context propagation, SDKs, and telemetry properly across proxy and backend per architecture.

## 11. Exporting Analytics to Cloud Storage or BigQuery

**Export** is appropriate for long-term history, joining API usage with cost/revenue, or SQL analysis. It is **not** real-time streaming logs. Per documentation, export supports **CSV** and **newline-delimited JSON** to **Cloud Storage** or **BigQuery** via an **asynchronous** export job.

### 11.1. General Workflow

1. Choose the destination dataset/bucket and a **data location** compatible with your Analytics region and residency requirements.
2. Enable required APIs and grant the **Apigee service agent** write access to the destination, scoped to the specific resource.
3. Create an **analytics datastore** in the Apigee organization.
4. Submit an **export request** for one environment and one day of data.
5. Monitor **`state`** until completed; verify record counts, schema, encryption, and retention.
6. Join with other datasets in BigQuery after removing/masking PII.

For certain US/EU Analytics setups, BigQuery export requires a **dataset in the matching US/EU multi-region**; if you need a single specific region dataset, you may need to export to Cloud Storage first and load into BigQuery. **Do not create a dataset in an arbitrary region** and assume export will succeed.

### 11.2. Export API Example — Requires a Configured Datastore

Example curl for an organization and environment with datastore **`Analytics-BQ-Dev`** already configured:

~~~bash
ACCESS_TOKEN="$(gcloud auth print-access-token)"
curl -f -sS -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://apigee.googleapis.com/v1/organizations/${APIGEE_ORG}/environments/${APIGEE_ENV}/analytics/exports" \
  -d '{
    "name": "Daily API analytics export for lab",
    "description": "Export one UTC day of data",
    "dateRange": {
      "start": "2026-11-17",
      "end": "2026-11-18"
    },
    "outputFormat": "json",
    "datastoreName": "Analytics-BQ-Dev"
  }'
~~~

**Notes:**

- **`dateRange` may span only one day** per the export API and uses UTC boundaries. `end` is the start of the following day.
- The initial response may show **`state=enqueued`**; this does **not** mean export is finished. Poll the **`self`** URL or list exports to check status.
- The Export API has quotas—documentation notes **500 calls/day/organization**; quota errors can return **429**.
- Free/trial plans do not support export; Pay-as-you-go requires an eligible add-on; IAM permissions to create datastores/exports differ from dashboard view permissions.
- Exported JSON contains metrics/dimensions per configuration and **is not automatically a table of raw request-level access logs**.

### 11.3. Post-Export Quality Checks

| Check | Why Does It Matter? |
|---|---|
| Right environment / time window | Avoid mixing test and production |
| Job completed, object/table exists | `enqueued` does not mean data has been written |
| Schema, record count, and metric totals | Detect missing, duplicate, or late-arriving data |
| Partitions / retention / permissions | Never keep PII indefinitely or expose buckets/datasets publicly |
| Encryption and location | Comply with security and data residency |
| BigQuery query costs | Avoid full historical scans on large tables |

Never export request headers, cookies, or full payloads without a legitimate purpose and security controls; **DataCapture** and access logs can increase the sensitivity of stored data.

## 12. Security, IAM, Reliability, and Cost of Observability

### 12.1. Role-Based Access Control

| Group | Need | Permissions and Limits to Review |
|---|---|---|
| **API product analyst** | View traffic and custom reports | Apigee Analytics Viewer/read role per entitlement; no proxy-edit rights |
| **SRE / on-call** | View API Monitoring, Cloud Monitoring, logs | **`roles/apigee.readOnlyAdmin`**, **`roles/monitoring.viewer`**, Logging Viewer scoped to data |
| **Alert operator** | Create/edit alerts and notification channels | **`roles/monitoring.alertPolicyEditor`**, **`roles/monitoring.notificationChannelEditor`** |
| **Proxy developer** | Edit flows, DataCapture, deploy revisions | Apigee developer/deployer roles scoped per environment |
| **Data platform** | Export and manage BigQuery/GCS datastores | Apigee Analytics Editor/Org Admin where required, destination permissions for service agent |
| **Security / auditor** | Audit permission changes and data access | Scoped audit/viewer roles without reading raw secrets/payloads |

Exact roles vary by Apigee organization/plan; **check official permissions** before granting. Never grant **Apigee Organization Admin** to everyone just so they can view dashboards. During exports, the Apigee service agent needs write permission on the destination; do not confuse it with the Java backend's runtime service account.

### 12.2. Personal Data Risks

- **`Authorization`**, **`Cookie`**, **`Set-Cookie`**, API keys, OAuth tokens, and passwords: **never capture** into custom dimensions/logs.
- **`User-Agent`, query strings, client IP, developer email** can be personal data; apply privacy reviews and proper retention.
- Never use **raw customer ID** as a custom dimension with millions of values. Capture only **low-cardinality identifiers** such as tier, API product, or controlled channel.
- Enable DataCapture on production proxies only after reviewing **sensitivity, masking, schema/cardinality, cost, and access permissions**.
- When sharing reports outside operations, prefer aggregated, anonymized data; never send raw log links over unapproved channels.

### 12.3. Costs and Limits

Commercially, Apigee may bill based on **API calls**, environments, extensible policies, Analytics add-ons, advanced features, or capacity. In addition:

| Component | Risk |
|---|---|
| **Analytics add-on / reports** | Limited without entitlement; report jobs have quotas |
| **DataCapture** | Extensible policy may carry separate cost/capacity impact |
| **Cloud Monitoring alerting** | Starting **5/1/2026**, Google begins billing for alerting per current pricing |
| **Cloud Logging** | Log volume, retention, queries/exports, and data access |
| **Cloud Storage / BigQuery export** | Object storage, ingestion, BigQuery queries, transfer/egress |
| **Java backend** | Cloud Run/GKE, Cloud SQL, networking as request volume grows |

Set **billing budgets** and review usage by environment/product. **Budget alerts do not automatically stop** proxies or shut down resources. Do not hard-code unit prices in docs since pricing, quotas, and entitlements evolve.

### 12.4. Product Scope: Apigee ≠ API Gateway

**Google Cloud API Gateway** and **Apigee** are two different API management products. API Gateway suits simpler gateway needs driven by API config/OpenAPI, whereas Apigee focuses on **API lifecycle, products/developers, policies, analytics, and deep operations**. The dashboards, DataCapture, and Metrics API covered in this lesson are **Apigee features**; do not copy their paths, IAM roles, or APIs to API Gateway expecting them to behave identically.

## 13. Incident Runbook: From Alert to Verified Recovery

Suppose at **10:15 UTC**, an alert fires: **`orders-v1` HTTP 5xx > 2% for 5 minutes**.

### Step 1 — Verify Scope

Confirm **Apigee org, environment, proxy, UTC time window, region, and traffic volume**. Rule out false alarms from the **`test`** environment or non-production synthetic load.

### Step 2 — Isolate Gateway vs. Target

In **API Monitoring → Timeline/Investigate**, filter proxy `orders-v1`, status 5xx, and fault source:

- **Policy errors/flow faults** rising: check proxy revision, VerifyAPIKey/Quota/JavaScript execution.
- **Target errors/target 503** rising: inspect Cloud Run/GKE backend.
- Empty `target_response_code`: requests may have been rejected early, served from cache, or failed before reaching the target.

### Step 3 — Compare Latency

In **Latency Analysis**, compare **total**, **target**, and **request/response processing** against pre-incident baselines. If target time jumps while proxy overhead stays steady, investigate Java/database. If gateway overhead jumps right after a policy deploy, inspect the proxy revision.

### Step 4 — Correlate Releases and Logs

Align timestamps:

~~~text
10:08  Cloud Run revision orders-00042 promoted
10:11  Java logs: connection timeouts begin rising
10:15  Apigee target_error + HTTP 503 rise
10:17  Cloud SQL connections hit limit
~~~

This is a **hypothetical timeline** for practice. Never treat temporal proximity as sole proof of causation; corroborate using logs/traces/metrics sharing the same correlation ID.

### Step 5 — Controlled Remediation

If caused by a new backend revision, **roll back Cloud Run traffic** after checking schema/data compatibility. If caused by a proxy revision, roll back the **proxy deployment** through the approved pipeline. If caused by Quota/SpikeArrest, never raise rate limits arbitrarily before distinguishing legitimate traffic from abuse.

### Step 6 — Confirm Recovery

Monitor continuously for at least one full alert window:

- 5xx and target errors return to baseline.
- p95/p99 latency returns within SLO.
- Request volume is normal—errors did not drop merely because traffic fell to 0.
- Java logs, Cloud SQL, and gateway metrics show consistent trends.
- No new alerts fire; update ticket, owner, and root cause.

**Analytics dashboards may lag behind**; use them to summarize impact once data converges rather than delaying production mitigation.

## 14. End-to-End Scenario: E-Commerce API on GCP

The **Hai Dang** system uses:

- Apigee **`orders-v1`** and **`payments-v1`** in **`prod`**.
- **Java `orders-api`** backend on Cloud Run connected to Cloud SQL PostgreSQL.
- **Cloud Logging + Monitoring** for the backend; **Apigee API Analytics + API Monitoring** for the API edge.
- API products for **`mobile-partners`** and **`merchant-portal`** with different auth/quotas.

### 14.1. Operational Dashboard Design

| Dashboard / Report | Metrics | Dimensions / Filter | Action on Anomaly |
|---|---|---|---|
| **API health** | `message_count`, 5xx status counts, p95 total latency | proxy, environment | Trigger SRE triage |
| **Target health** | `target_error`, target response time | `target_url`/`target_host` | Inspect Cloud Run, Cloud SQL |
| **Policy health** | `policy_error` | proxy, fault policy | Review API key/OAuth/quota config |
| **Client usage** | TPS, request counts | `developer_app`, API product | Capacity planning, abuse detection |
| **Business segment** | Orders API calls | `dc_client_tier` (3–4 values) | Compare consumption across tiers |

### 14.2. Java Canary Rollout Check

After shifting 10% of backend traffic to a new revision:

1. Watch **Apigee errors/latency** per proxy, checking both old and new backend revisions if revision telemetry exists.
2. Capture correlation IDs to cross-reference **Cloud Run logs** for failed gateway requests.
3. If target latency rises with no proxy policy deploy, prioritize backend and SQL connection pool investigation.
4. After rolling back the backend, confirm **SLOs and traffic volume** recover—do not rely solely on HTTP 200 from a `/health` endpoint.

### 14.3. Hypothetical Metrics Example

Over 10 minutes:

| Proxy | Requests | HTTP 5xx | 5xx Rate | p95 Total |
|---|---:|---:|---:|---:|
| `orders-v1` | 80,000 | 1,600 | **2.0%** | 980 ms |
| `payments-v1` | 20,000 | 20 | **0.1%** | 240 ms |

Sound conclusion: failures are concentrated in **`orders-v1`**, not the entire Apigee organization. Next hypothesis: the `orders-api`/Cloud SQL target or a policy attached only to `orders-v1`. **Do not rush to alter global Apigee configuration** while `payments-v1` continues meeting its SLO.

If `orders-v1`'s error budget is **0.1%**, across 80,000 requests the simple budget is **80 errors**. Seeing **1,600** HTTP 5xx means burning **20× the error budget** for that window—always verifying the exact SLO definition of 5xx and window length.

## 15. Exercises and Suggested Answers

### Exercise A — Pick the Right Tool

**Scenario:** (1) find 30-day request trends for an API product, (2) notice 503 errors started spiking 2 minutes ago, (3) inspect VerifyAPIKey flow variables on a test request, (4) correlate errors with SQL traces.

**Answer:** (1) **API Analytics/custom report**, (2) **API Monitoring/Cloud Monitoring**, (3) **Apigee Debug**, (4) **backend Cloud Logging/Tracing**. Do not force a single tool to serve all four purposes.

### Exercise B — Calculate Error Rate

A proxy receives **50,000 requests**, with **250 HTTP 5xx**, **1,000 HTTP 401**, and **500 HTTP 429**.

**Question:** What is the HTTP 5xx rate? Should every 401/429 count toward SLO errors?

**Answer:** **0.5%**. 401/429 can reflect policies working as designed; rely on the SLO contract to decide inclusion rather than adding them mechanically.

### Exercise C — Distinguish Proxy vs. Target Errors

Metrics for `orders-v1`: **`sum(policy_error)=600`**, **`sum(target_error)=0`**, most clients receive HTTP 401, and `target_response_code` is empty.

**Suggested Answer:** many requests are likely rejected before reaching the target by VerifyAPIKey/OAuth. Check **`ax_execution_fault_policy_name`**, developer app/key status, and proxy revision—do not rush to roll back Cloud SQL.

### Exercise D — Interpret Latency

Before deploy: p95 total **250 ms**, p95 target **200 ms**. After deploy: p95 total **900 ms**, p95 target **220 ms**, with request-processing p95 surging.

**Answer:** suspect a bottleneck in **Apigee request processing/policies**, not the Java target based on initial figures. Inspect the proxy revision and Debug; percentiles from separate series cannot be added as exact identities.

### Exercise E — Design a Custom Report

You need to find the **top 5 client apps with the most HTTP 429s** in prod yesterday.

**Answer:** metric **`sum(message_count)`**, dimension **`developer_app`**, filter **`response_status_code = 429`**, yesterday's time range, and environment **`prod`**; sort descending / `topk=5`. Compare against **each app's total requests** before judging which app violates limits most frequently by ratio.

### Exercise F — Protect DataCapture

The growth team wants to record the **`Authorization` header** and **customer email** as dimensions for every request.

**Answer:** reject this design due to credential/PII leakage and high cardinality. Choose low-sensitivity, low-cardinality values like a validated **client tier**; review DataCapture policies, retention, and access permissions.

### Exercise G — Call the Metrics API

**Task:** write a request fetching total requests per proxy in the **`test`** environment for one UTC day, then cross-check against a dashboard. Identify why the response might be empty.

**Suggested Answer:** use **`/organizations/ORG/environments/test/stats/apiproxy?select=sum(message_count)&timeRange=...&timeUnit=day`** with an authorized Bearer token. Verify organization/environment/time window, analytics add-on, actual traffic, IAM, and the **up-to-~10-minute data delay**.

### Exercise H — Alerting and Triage

Proxy `orders-v1` sees rising 503s with no increase in `policy_error`; both `target_error` and `target_response_time` are rising.

**Answer:** prioritize the target backend, Cloud Run/GKE readiness, Cloud SQL connections, and networking; inspect Apigee fault sources and logs. Configure 5xx and latency alerts with minimum traffic thresholds rather than alerting on individual failed requests.

### Exercise I — Export and Cost

An organization needs **24 months** of analytics for annual analysis, while the UI entitlement provides a shorter retention window.

**Answer:** design a controlled export to **Cloud Storage/BigQuery** with partitioning/lifecycle/IAM, privacy review, matching analytics location, and accuracy checks. Track export job states **`enqueued → completed`**, quotas, and storage/query costs; do not confuse exports with detailed request access logs.

## 16. Summary and References

**Six key takeaways:**

1. **API Analytics** reveals API trends and performance; **API Monitoring** prioritizes near-real-time incident detection and triage. Their two pipelines differ in delay and figures.
2. Choose the right **metric, dimension, filter, and time window**; **`proxy errors`, `policy errors`, `target errors`, and HTTP `5xx`** are not synonymous.
3. Break latency into **total, target, and request/response processing**, and read p95/p99—never averages alone.
4. **Custom reports, Metrics API, and DataCapture** extend analysis; DataCapture must collect **curated data only**, never raw secrets or PII by default.
5. **Cloud Monitoring alerts + access logs + backend telemetry** form the investigation chain from alert to root cause and recovery verification.
6. **Least-privilege IAM, entitlements/add-ons, retention, region, and logging/export costs** must be evaluated before enabling in production.

**Official sources for further reference:**

1. [Apigee API Analytics overview](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/analytics-services-overview) — Analytics structure, dashboards, data delay/retention.
2. [Analytics metrics, dimensions and filters](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/analytics-reference) — exact API metric and dimension names.
3. [Latency Analysis dashboard](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/latency-analysis-dashboard) — target/request/response latency and p95/p99.
4. [Create and manage custom reports](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/create-custom-reports) — reports, report jobs, and filters.
5. [Using the Metrics API](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/use-analytics-api-measure-api-program-performance) — REST queries, `select`, `timeRange`, `topk`.
6. [DataCapture policy](https://docs.cloud.google.com/apigee/docs/api-platform/reference/policies/data-capture-policy) — XML, DataCollector, and Extensible policy details.
7. [Collect custom analytics data](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/using-data-capture) — creating collectors and custom dimensions.
8. [API Monitoring overview](https://docs.cloud.google.com/apigee/docs/api-monitoring) — Timeline, Investigate, Recent, fault isolation.
9. [Set up alerts and notifications](https://docs.cloud.google.com/apigee/docs/api-monitoring/alerts-notifications) — metrics/labels, thresholds, Cloud Monitoring IAM.
10. [Understand Apigee observability](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/understand-apigee-observability) — how Analytics, Monitoring, and access logs differ.
11. [Export Analytics data](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/export-data) — Cloud Storage/BigQuery, datastores, and export jobs.

# Observing Load Distribution Without Inferring from a Few Requests

An `order-service` application calls `inventory-service` using RestClient, WebClient, or OpenFeign via Spring Cloud LoadBalancer. Requests are distributed across inventory `ServiceInstance`s; when inspecting a handful of consecutive responses, you may see one instance receive more requests than another. **That alone is not enough to conclude the load-balancing algorithm is broken.**

The exact same outcome—"7 hits on instance A, 3 on B"—can arise naturally from normal Random selection, from Round Robin across multiple independent callers, from retries, from an instance leaving the candidate list temporarily, or from sampling that drops failed requests.

This lesson belongs to the **System Observability** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module and walks through observing the right layers:

- **Service discovery and instance selection:** how many candidates exist on each pass, filtered by health, zone, hint, weight, sticky session, or other policies?
- **HTTP client:** how many HTTP attempts does one logical RestClient/WebClient/OpenFeign request generate, and how do they finish?
- **Backend:** which replica actually received and completed the request, how long did it take, and with what status?
- **Statistics:** given sample size N and the expected algorithm, does the observed deviation remain consistent with random variation?
- **Operations:** distributions of request count, active requests, latency, error rate, and CPU/concurrency can differ dramatically.

The goal is measuring **the right quantity, the right time window, the right population, and the right hypothesis** before switching algorithms, raising retries, or concluding a replica is being ignored.

## 1. First Question: What Does "Balanced" Mean?

A system can balance along many different objectives:

| Objective | Quantity to measure | Common misconception |
|---|---|---|
| Balancing **selections** | How often LoadBalancer selects each `ServiceInstance` | Assuming every selection yields a successful HTTP request |
| Balancing **attempts** | Actual HTTP requests sent to each instance | Forgetting retries or pre-network I/O failures |
| Balancing **successful requests** | Responses meeting the defined success condition | Ignoring failed or timed-out requests |
| Balancing **active requests** | Concurrent in-flight calls on each instance | Confusing concurrency with requests per minute |
| Balancing **processing time** | Total service time or latency distribution | Two instances with equal counts can have vastly different costs |
| Balancing **resources** | CPU, memory, threads, connection pools, queue depth | Assuming Round Robin monitors CPU automatically |
| Balancing **user experience** | End-to-end p95/p99, error rate, deadline misses | Looking only at A/B ratios |
| Balancing **by policy** | Distribution matching zone/weight/hint/tenant/affinity | Assuming every instance must receive equal traffic |

**Spring Cloud LoadBalancer selects instances; it does not guarantee equal CPU, latency, or successful responses.** Default Round Robin or Random operates over the **supplied candidate list**, not over every instance a dashboard thinks exists.

Questions that sound similar require different measurements:

- "Is A selected 50% of the time?" → count caller selections over a stable candidate population.
- "Does A receive 50% of HTTP attempts?" → count backend HTTP attempts, including retries and other callers.
- "Is A overloaded?" → check active/concurrency, CPU, queues, service time, and error rate.
- "Is LoadBalancer skipping B?" → check candidate lists and selection metrics, not just response bodies.
- "Are users seeing slowness?" → measure end-to-end latency, statuses, and retries.

## 2. One Logical Call Can Produce Multiple Distinct Events

~~~mermaid
flowchart LR
    U["Business operation"] --> C["HTTP client"]
    C --> L["LoadBalancer choose"]
    D["Discovery + suppliers"] --> L
    L --> I["Inventory instance"]
    I --> R["HTTP response / error"]
    R --> C
~~~

When retries are enabled, the real sequence can look like:

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant LB as LoadBalancer
    participant A as inventory A
    participant B as inventory B

    O->>LB: 1 logical GET /stock
    LB-->>O: select A
    O->>A: HTTP attempt #1
    A--xO: Connection reset
    Note over O: Retry only if configured
    O->>LB: select again
    LB-->>O: select B
    O->>B: HTTP attempt #2
    B-->>O: 200 OK
    O-->>O: 1 completed logical call
~~~

In this example:

| Count type | Value |
|---|---:|
| Business logical calls | 1 |
| LoadBalancer selections | 2 |
| HTTP attempts reaching backend | Could be 1 or 2 depending on whether the failure occurred before or after sending |
| Completed logical responses | 1 |
| Successful HTTP backend responses | 1 |
| Failed HTTP/network attempts | At least 1 error on caller; uncertain if backend received it |

A TCP connection failure can occur **before** the backend ever receives the request. A read timeout can occur **after** the backend succeeded while the response failed to reach the caller. Caller and backend counts therefore do not have to match.

### Denominators Must Not Be Swapped

Let:

- `N_selection`: total `ServiceInstance` selections.
- `N_sent`: total attempts actually sent by the transport.
- `N_received`: total attempts received by the backend.
- `N_success`: attempts succeeding per business definition.
- `N_logical`: total calls from business code.

If a dashboard plots `N_success(A) / sum(N_success)`, that shows **share of successful requests**, not necessarily the algorithm's selection rate for A. A failing instance can receive plenty of attempts yet few successes, nearly "disappearing" from a success chart.

## 3. Why a Few Initial Requests Are Not Enough to Conclude Anything

Suppose LoadBalancer picks uniformly at random between two instances A and B. On each selection, theoretically:

\[
P(A)=P(B)=0.5
\]

This does **not** mean every two requests must hit A once and B once. All of the following sequences are valid:

~~~text
A, B, B, A, A, B
A, A, A, B, A, A
B, B, B, B, B, A
~~~

Consecutive runs of the same instance are a normal property of Random selection. Sending just 10 requests and seeing 7 for A and 3 for B gives no reliable evidence of algorithmic bias.

With Round Robin in **one caller, a fixed candidate list, and no retries**, selections alternate cleanly; however, **response completion** order can still differ from selection order due to network latency and concurrency.

### Every Experiment Must Start with an Explicit Hypothesis

Example null hypothesis `H0`:

> During the measurement window, a single caller uses unweighted Random selection, choosing independently from the exact same three always-eligible instances; each instance's selection probability is 1/3.

If that hypothesis does not hold because of health filtering, zones, weights, or instance-count changes, comparing against 1/3 is invalid from the start.

Never adopt "every replica gets 33.3% of traffic" as a universal standard for a system with zone preferences, tenant affinity, weighted routing, or callers in different zones.

## 4. Statistical Variation Under Random Selection

With `N` independent selections and probability `p_i` for instance `i`, the selection count `X_i` follows a marginal binomial distribution:

\[
X_i \sim \operatorname{Binomial}(N,p_i)
\]

Expectation and standard deviation:

\[
E[X_i]=Np_i,\qquad
\sigma_i=\sqrt{Np_i(1-p_i)}.
\]

The observed proportion `\hat p_i = X_i/N` has standard error:

\[
SE(\hat p_i)=\sqrt{\frac{p_i(1-p_i)}{N}}.
\]

Two-instance example, `p_A=0.5`:

| Selection count `N` | Expected A count | Standard deviation of count | Approx. 95% range for A share |
|---:|---:|---:|---:|
| 10 | 5 | 1.58 | Normal approximation **unreliable** because sample is too small |
| 100 | 50 | 5.00 | Roughly 40.2%–59.8% |
| 1,000 | 500 | 15.81 | Roughly 46.9%–53.1% |
| 10,000 | 5,000 | 50.00 | Roughly 49.0%–51.0% |

The intervals for `N >= 100` are **approximations** via `p ± 1.96 × SE`, **not SLOs or guaranteed LoadBalancer bounds**. They assume independent draws, a fixed candidate set and fixed `p`, and no sticky routing, retry affinity, or other biases.

With three equal replicas and `N=900`, each replica expects 300 selections. Standard deviation:

\[
\sigma=\sqrt{900\times\frac13\times\frac23}
=\sqrt{200}\approx14.14.
\]

An illustrative sample could be:

~~~text
A: 287   (31.9%)
B: 305   (33.9%)
C: 308   (34.2%)
Total: 900
~~~

These are **illustrative numbers**, not real measurements. They are not 300/300/300, yet they fit a healthy Random algorithm well. "Not perfectly even" does not mean "broken Random".

## 5. Why Even Round Robin Does Not Guarantee Alternating Responses

Round Robin picks the next position in the **instance list it receives at selection time**. With a fixed list `[A, B, C]`, a single caller, no retries, and sequential calls, the selection sequence can be:

~~~text
choose #1 -> A
choose #2 -> B
choose #3 -> C
choose #4 -> A
choose #5 -> B
choose #6 -> C
~~~

Yet if A takes 500 ms, B takes 30 ms, and C takes 100 ms, responses can **arrive out of selection order**:

~~~text
choose:    A, B, C, A, B, C
complete:  B, C, B, C, A, A
~~~

Therefore:

- Never use **response arrival order** to prove selection order.
- When multiple caller replicas each hold their own LoadBalancer context, do not expect every instance cluster-wide to share **one global Round Robin counter**.
- When the candidate list changes length or order between selections, the resulting sequence shifts too.
- With retries, one logical request can contribute more than one selection.
- If some streamed requests stay open longer, call counts may stay balanced while active request counts skew sharply.
- With same-instance preference or sticky sessions, Round Robin may not be the final effective policy.

Inspect **selections** rather than only **completion order**, especially with WebClient and asynchronous execution.

## 6. The Changing Candidate Set Is the True Denominator

Spring Cloud LoadBalancer does not necessarily pick among **every instance in the registry**. `ServiceInstanceListSupplier` layers can produce a filtered candidate set:

~~~mermaid
flowchart LR
    R["DiscoveryClient"] --> C["Cache / supplier"]
    C --> H["Health check filter"]
    H --> Z["Zone / hint / request filtering"]
    Z --> S["Eligible ServiceInstances"]
    S --> A["RoundRobin / Random / other policy"]
    A --> I["Selected instance"]
~~~

This is a conceptual flow. **Actual supplier ordering depends on configuration**, not a single universal pipeline across all projects.

Example:

| Time | Eligible candidates | Unweighted Random probability |
|---|---|---|
| 10:00–10:05 | A, B, C | 1/3 each |
| 10:05–10:10 | A, C (B unhealthy) | A/C 1/2 each, B = 0 |
| 10:10–10:15 | A, B, C | 1/3 each |

Merging into one 15-minute chart without showing candidate-set changes makes B appear "abnormally under-utilized". Yet that is the **intended** result of health filtering.

With zone preference, a caller in `zone=az-1` prefers A/B in the same zone over C in another zone; selections must be evaluated against the **zone policy**. With weighted routing, the target is not 1/3, but perhaps a 1:2:3 ratio over each stable window.

**Never build a 33.3% alert threshold for every service ID** without knowing whether policy applies weights, zones, hints, or sticky sessions.

## 7. Sources of Distribution Skew to Recognize

| Source | Visible symptom | Evidence to gather |
|---|---|---|
| Stale discovery | New instances get few hits or dead instances remain | Registry events, live supplier list, refresh timestamps |
| Cache TTL | Candidate list updates lag | Cache settings, TTL, list snapshots over time |
| Health checks | Instance dropped on health failure | Health check results, healthy list, recovery time |
| Zone preference | Certain replicas preferred per caller zone | Caller zone, instance zone metadata |
| Hint routing | Requests with different hints hit different subsets | Normalized hint values, supplier candidates |
| Weighted selection | Higher-weight replicas get more turns | Weights and expected distribution per window |
| Sticky session / same-instance preference | One client repeats on the same instance | Cookie/session/affinity policy, client cohorts |
| Retry-aware supplier | Later attempts avoid prior instance | Retry count, prior instance, current selection |
| Multiple caller replicas | Each caller has independent selection state | Caller ID, request ID, release version |
| Horizontal autoscaling | Denominator changes over time | Instance lifecycle, start/stop timestamps |
| Canary release | Canary version intentionally gets less traffic | Routing policy, version labels |
| Circuit breaker | Some logical calls blocked before LoadBalancer | Not-permitted calls, breaker state |
| Other gateway/LB layers | Backend volume mismatches client-side selections | Trace paths and metrics at each layer |
| Pool/transport errors | Selection occurs but backend never receives request | Client transport errors, TCP, server access logs |

To analyze properly, **stratify** by time, caller, and policy before aggregating. A 24-hour rollup can hide 5-minute degradations—or conversely misattribute planned rollouts to algorithmic bias.

## 8. Choosing Window and Sample Size Deliberately

A reliable measurement plan should specify:

1. **Hypothesis:** unweighted Random, Round Robin, or intentional routing?
2. **Population:** all attempts from all callers, one specific caller, one route, or same-zone only?
3. **Denominator:** selections, sent attempts, received attempts, successes, or logical calls?
4. **Window:** 1 minute, 15 minutes, 1 hour; does it include scaling/deploys?
5. **Sample size:** how many valid selections occur in each window and cohort?
6. **Criteria:** acceptable deviation ±? evaluated statistically or operationally?
7. **Warm-up period:** do LoadBalancer context init, JVM JIT, connection pools, or discovery cache warm-up introduce bias?
8. **Concurrency:** sequential, 20 concurrent, 500 concurrent; are retries active?
9. **Service state:** are all instances healthy with no zone/hint differences?
10. **Collection completeness:** are failures, 503/no-instance, and cancelled requests instrumented?

For example, three replicas each expect ~300 selections after 900 turns. A 10-second chart with seven requests cannot establish long-term skew. Dashboards should display **both percentage and sample count**; when `N` is tiny, show "low sample / inconclusive" instead of turning red immediately.

### Sample Size Estimate for Random

To keep approximate margin of error within ±5 percentage points at roughly 95% confidence for `p=0.5` (maximum variance case):

\[
N \approx \frac{1.96^2\cdot 0.5(1-0.5)}{0.05^2}
\approx 384.
\]

This is a **theoretical sample size for estimating a proportion under independent Bernoulli trials**, not a rule saying "384 requests guarantees a valid test". If selections are correlated, policies shift, or samples are improperly stratified, statistical power drops.

In confidence intervals, expected margin of error shrinks roughly as `1/\sqrt{N}`. Halving the margin of error requires roughly **four times** as many selections, assuming conditions remain constant.

## 9. Do Not Infer Causation from One Percentage Chart

Suppose a dashboard shows:

~~~text
A: 65% completed requests
B: 25% completed requests
C: 10% completed requests
~~~

This data **does not yet answer**:

- Did LoadBalancer select A 65% of the time, or did A simply complete more requests?
- Did B/C time out frequently, under-reporting completions?
- Was C unhealthy or in another zone for half the window?
- Did traffic come from one caller or multiple callers with different policies?
- Is N = 20 or N = 2,000,000?
- Did C receive fewer requests **by design** due to canary weights?
- How long was each replica ready to serve traffic?
- Is a reverse proxy, Service Mesh, or Kubernetes Service behind the scenes re-routing requests?

Distinguish three kinds of statements:

- **Observation:** "Over 10 minutes, backend C recorded 8% of successful responses on route GET /stock."
- **Hypothesis:** "C may have been health-filtered or assigned a lower weight."
- **Conclusion:** "The eligible instance list during that window included C for only 8% of policy selections, corroborated by traces and supplier logs."

A standalone percentage chart is an **investigation signal**, never automatic proof of root cause.


## 10. MicrometerStatsLoadBalancerLifecycle: Caller-Side Data Source

Spring Cloud LoadBalancer provides `MicrometerStatsLoadBalancerLifecycle`, a `LoadBalancerLifecycle` collecting statistics on load-balanced calls. To enable it, you need a `MeterRegistry` and:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
~~~

Per Spring Cloud Commons documentation, provided meters include:

| Meter | Type | What does it measure? |
|---|---|---|
| `loadbalancer.requests.active` | Gauge | Currently active LoadBalancer calls, optionally carrying instance tags |
| `loadbalancer.requests.success` | Timer | Duration of load-balanced calls ending with returning a response to the underlying HTTP client |
| `loadbalancer.requests.failed` | Timer | Duration of load-balanced calls ending with an exception |
| `loadbalancer.requests.discard` | Counter | Calls discarded because LoadBalancer could not obtain a `ServiceInstance` |

**Crucial distinction:** `loadbalancer.requests.success` **does not automatically equal HTTP 2xx counts or successful business transactions**. Under lifecycle metric semantics, "success" describes the call finishing by handing a response to the client layer—it does not guarantee status 200. An HTTP 500 response can still land in the response-received branch depending on integration and handling. To know 5xx rates, measure HTTP statuses at the appropriate caller/server layer.

Similarly, `loadbalancer.requests.discard` does not represent all failed requests, but one specific case: **failing to obtain a target instance**.

Metrics attach tags for service instance, request, or response **when data is available**. Some blocking integrations omit full request/response metadata, so **never assume every tag always exists**. Timer `count` reflects timer recordings per tag set and does not automatically equal domain logical requests.

### Dependencies and Demo Configuration

In a Spring Boot application using a LoadBalancer-enabled HTTP client, add Actuator to expose the registry/endpoints per config:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

These dependencies **supplement** `spring-boot-starter-web` or `spring-boot-starter-webflux` and your chosen HTTP client. If exporting to Prometheus, add the Micrometer Prometheus registry managed by the Spring Boot BOM:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Example `application.yml` for an internal test environment:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
~~~

`include-path: false` prevents dynamic paths containing SKU/order IDs from entering the `uri` tag in LoadBalancer metrics. Spring Cloud Commons notes that `RestTemplate`-backed load balancing can lack URI templates and fall back to raw paths when tagging, causing **high cardinality** if paths contain unbounded IDs. With `RestClient` and `WebClient`, Spring Cloud can use the URI template when available, though you should still inspect the live registry.

**Never expose Actuator metrics/prometheus publicly on the Internet.** Enforce network access controls, authentication, scrape permissions, and instance-metadata disclosure policies. All endpoint examples below assume a local or trusted management network.

## 11. Inspecting Figures from /actuator/metrics

After starting the caller and sending a few requests through LoadBalancer, try:

~~~powershell
Invoke-RestMethod "http://localhost:8080/actuator/metrics"

Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.success"

Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.failed"

Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.discard"
~~~

Meters generally appear only **after at least one observation is recorded**. A 404 for a meter name does not automatically mean LoadBalancer is broken. Possible reasons:

- No matching request has occurred yet, so the meter is not registered.
- Missing Actuator/`MeterRegistry` or `stats.micrometer.enabled` is not turned on.
- Querying the **backend's management endpoint** instead of the **caller** running LoadBalancer.
- The client bypassed LoadBalancer because it used a static IP/URL.
- The metrics endpoint is restricted by exposure or security rules.
- Meter/label names differ across release trains and exporters.

`/actuator/metrics/{meter}` returns `measurements` and `availableTags`. Before building dashboards, **inspect the actual `availableTags`** to confirm whether they carry service ID/instance tags for comparison. Do not guess tag names like `instanceId`, `serviceId`, or `status` and create queries that silently return 0.

### Timers, Counters, and Gauges Must Be Read Differently

- **Timer:** exposes `COUNT` and `TOTAL_TIME` in Actuator; `COUNT` is the event count, and total time divided by count is the mean latency per meter semantics. Mean does not replace p95/p99.
- **Counter:** monotonically increasing; to compute per-minute traffic, use `increase()`/`rate()` in a time-series system, accounting for process restarts/resets.
- **Gauge:** instantaneous value at scrape time; `active=0` does not mean zero requests arrived over the past minute.
- **Histogram/timer distribution:** must be explicitly enabled/configured for reliable p95/p99; never infer p99 from averages.

Prometheus translates meter names/units into its own conventions—for instance, timers produce `*_seconds_count` and `*_seconds_sum` series. **Verify live series names at `/actuator/prometheus` or in the actual registry** before writing PromQL; never copy a metric name assuming it holds across every version.

## 12. Combining Client-Side LoadBalancer Metrics with Backend Metrics

To understand load distribution, never measure the caller alone.

~~~mermaid
flowchart LR
    O["Caller: LB lifecycle metrics"] --> LB["Select ServiceInstance"]
    LB --> A["Backend A: HTTP server metrics"]
    LB --> B["Backend B: HTTP server metrics"]
    LB --> C["Backend C: HTTP server metrics"]
    A --> M["Dashboard / tracing"]
    B --> M
    C --> M
    O --> M
~~~

An observation board should cover these groups:

| Layer | Metrics or logs to collect | What it distinguishes |
|---|---|---|
| Caller business | Total logical calls, route/operation, errors | User-facing demand |
| LoadBalancer lifecycle | Success/failed/discard, active, instance tags when present | Selection/execution in the LB integration |
| HTTP client | Attempts, response status, connect/read timeouts, retry count | Transport successes/failures |
| Inventory HTTP server | `http.server.requests`, response status, duration | What the backend actually received and processed |
| Inventory application | Endpoint business success/failure | Business outcome |
| Host/JVM | CPU, heap, GC, thread pools, queue depth | Processing/resource cost |
| Distributed trace | Caller span, downstream span, correlation ID, attempts | Stitching the exact request path |

Backend request counts may include **health probes** or traffic not originating from `order-service`. Filter by endpoint, client source, and environment instead of mixing `/actuator/health` into business load charts.

In Prometheus/Kubernetes environments, distinguish replicas via stable **scrape target** labels (pod/instance) or controlled instrumentation. Never turn request IDs, user IDs, sessions, or SKUs into metric labels; that causes high cardinality and degrades metrics performance and cost.

### Should Responses Return instanceId?

In a **lab or controlled diagnostic environment**, a backend might return:

~~~json
{
  "instanceId": "inventory-b",
  "sku": "SKU-001"
}
~~~

This helps confirm which backend handled the request. However, avoid embedding sensitive infrastructure metadata in every production response; prefer server-side metrics/logs and trace context.

Even when a response body shows B, you only know **B returned the response**. You still do not know whether A was selected on an earlier attempt and failed.

## 13. Even Request Counts Do Not Mean Even Resource Load

Consider 1,000 total attempts split evenly across A and B:

~~~text
A: 500 requests, average service time 10 ms
B: 500 requests, average service time 200 ms
~~~

Corresponding total service times:

\[
W_A=500\times10\mathrm{ms}=5000\mathrm{ms}
\]

\[
W_B=500\times200\mathrm{ms}=100000\mathrm{ms}.
\]

Request counts are balanced, yet B accumulates **20 times** the processing time. At constant throughput with longer service times, B's in-flight request count is typically higher.

By an approximate reading of **Little's Law** in steady state:

\[
L \approx \lambda W
\]

where `L` is the average number of items in the system, `\lambda` is throughput, and `W` is average time in the system. When two instances receive the same request rate while B has higher latency, active requests on B will be higher.

**Do not switch algorithms solely because B's active gauge is higher.** B may be slow due to GC, DB hotspots, CPU throttling, heavier payloads, connection pools, noisy neighbors, or version mismatches. Check those variables first.

### Counts, Rates, and Latency Belong Side by Side

A solid operational dashboard per service ID can include:

1. Requests/sec per replica (by status class).
2. Active requests and connection pool utilization.
3. Error rates: 4xx/5xx/exceptions/timeouts.
4. Response latency p50, p95, p99.
5. CPU, memory, GC pauses, thread/queue pressure.
6. Eligible replicas from discovery/health over time.
7. Retry rate and discard/no-instance counts.
8. Version/zone/weight of each replica.

An even ~33/33/34 request split where one replica shows much higher p99 still warrants investigation; conversely, a 50/30/20 split can be completely correct when weights are configured that way.

## 14. Daily Aggregate Distributions Can Hide Short Anomalies

Suppose over 15 minutes each instance receives vastly different traffic across phases:

| Time window | A | B | C | State |
|---|---:|---:|---:|---|
| 10:00–10:05 | 200 | 200 | 200 | All three healthy |
| 10:05–10:10 | 300 | 0 | 300 | B excluded by health |
| 10:10–10:15 | 200 | 200 | 200 | B recovered |
| **Total** | **700** | **400** | **700** | B has 22.2% of total |

Looking only at the 15-minute total, B appears severely under-served. Yet normalizing by **eligible time** reveals a different story: B getting zero traffic while filtered out is expected—it is a health/discovery event, not a Random bug.

To analyze an autoscaling event, record:

- When the instance registered and became healthy.
- When LoadBalancer's supplier actually saw the instance, not just when the Kubernetes pod turned Ready.
- Zone, hint, weight, and version labels at that moment.
- Selection count within each window where the eligible set was stable.
- Cache TTL cycles and deployment rollouts.

When plotting shares, display **N and eligible instance count** alongside percentages, not just three percentage lines.

## 15. Using Statistics to Ask Questions, Not as an Automatic "Pass/Fail Oracle"

For Random selection with theoretical probabilities `p_i` and `N` selections, deviation can be tested with a **goodness-of-fit test**, such as the chi-square statistic:

\[
\chi^2=\sum_{i=1}^{k}\frac{(O_i-E_i)^2}{E_i},
\qquad E_i=Np_i
\]

where `O_i` is the measured selection count for instance `i`, and `E_i` is the expected count under policy.

For example, with `N=900` and three equal instances at `1/3`, expected count is 300 each; illustrative data `O = (287, 305, 308)`:

\[
\chi^2
=\frac{(287-300)^2}{300}
+\frac{(305-300)^2}{300}
+\frac{(308-300)^2}{300}
\approx0.86.
\]

This deviation is small on the standard chi-square scale with 2 degrees of freedom; **there is no basis to treat it as clear evidence of bias** under the simple model. Still, the test neither proves the algorithm is flawless nor proves backends are always balanced.

### Caveats That Must Be Stated Clearly

- Expected counts must be large enough for the chi-square approximation; use exact/Monte Carlo methods for small samples rather than forcing the test.
- Selections are **not independent** under Round Robin or sticky/affinity policies: an IID Random chi-square test does not apply as-is.
- If `p_i` varies over time, split into windows with stable policy or compute time-weighted expected exposure.
- Checking many windows and many services guarantees some crossings by pure chance; account for multiple comparisons.
- Distinguish **operational significance** from **statistical significance**. A 1-percentage-point skew may be statistically significant at huge `N` yet irrelevant operationally.
- Even if bias is detected, statistics only says "data disagrees with the hypothesis"; it **does not automatically prove LoadBalancer code is the cause**.

For single-caller Round Robin, you can verify the **selection sequence and eligible list cardinality** under controlled conditions. For Random, evaluate distribution over large samples using probability rather than asserting "every three requests hit each replica once".

## 16. Traces and Logs to Explain Why a Replica Was Chosen

Aggregate metrics detect shifts, while tracing explains **why a single logical call generated multiple attempts or picked a particular instance**.

A trace might show:

~~~text
Trace: quote-request-123
  OrderService GET /quotes
    InventoryClient logical GET inventory-service/stock
      attempt #1 -> inventory-a -> connection reset
      retry backoff 100 ms
      attempt #2 -> inventory-b -> HTTP 200
    PricingClient GET pricing-service/price -> HTTP 200
~~~

Modern tracing systems like Micrometer Tracing/OpenTelemetry provide span propagation; never hand-roll `traceparent` UUIDs or stuff dynamic user data into span attributes.

Diagnostic patterns:

- Two backend access logs with the same correlation ID → likely a retry or duplicate caller attempts.
- One business span with multiple outbound spans → check retry policy and attempt count.
- Caller logs "selected inventory-a" while server A has no log → failure occurred before the HTTP request reached A.
- Server A logged 200 while caller timed out → response was likely lost or delayed; do not claim "A never received the request".
- Client-side dashboard metrics differ from server-side → check other traffic sources (gateways, probes, scheduled jobs) and scrape timing.

Never log raw `Authorization` headers, cookies, user IDs, or full URLs with sensitive query strings. Use route templates, service IDs, trusted instance IDs, and sanitized correlation IDs.

## 17. Do Not Replace Metrics with Per-Request Debug Logs

Temporary logging can help inspect an algorithm, but never let production emit millions of unbounded `selectedInstance=...` log lines. Problems include:

- Increased CPU, allocations, I/O, and log storage costs.
- Risk of leaking sensitive infrastructure hosts/ports.
- Once sampling or truncation kicks in, logs no longer represent full traffic.
- Server logs only see requests that arrived; pre-transport failures are absent.
- Logging selections after request completion can scramble order and misrepresent Round Robin.

Prefer **Micrometer counters/timers/gauges** for trends, **sampled tracing** for deep dives, and **structured logs** at key failure boundaries. Enable debug logging only temporarily in controlled environments.

If you need a custom `LoadBalancerLifecycle` to record selection details, check the lifecycle API and generic types for your Spring Cloud release train; never deploy an untested custom class as production telemetry.

## 18. Designing Dashboards So Percentages Do Not Mislead You

Group panels by service ID and operation first, then show:

| Panel | Contents | Reason |
|---|---|---|
| **Traffic attempts** | Requests/sec per instance, status breakdown | Shows what each replica actually receives |
| **LoadBalancer lifecycle** | Success/failed/discard/active by available tags | Isolates failure to select an instance |
| **Eligibility** | Healthy and filtered candidate counts over time | Fair ratios depend on the eligible set |
| **Latency** | p50, p95, p99 per instance and end-to-end | Balanced counts do not mean balanced tail latency |
| **Errors** | Timeouts, connect failures, HTTP 5xx, circuit open | Separates transport failures from selection |
| **Retry amplification** | Attempts / logical calls | Backend traffic exceeding user traffic |
| **Capacity** | CPU, memory, queues, active requests | Shows real resource pressure |
| **Deployment timeline** | Scale up/down, rollouts, config versions | Pinpoints when policy or topology shifted |

Pair percentages with **sample count**, time window, caller scope, and expected policy. "A 60% (N=5)" means something completely different from "A 60% (N=500,000, expected 50%, stable eligible set)".

### How Should Alerts Work?

Instead of alerting on "A deviated by more than 5%" over any window, an operational alert can require:

- Minimum `N` threshold in the window (enough observations).
- Confirmed stable eligible set and weights.
- Operationally meaningful skew persisting across consecutive windows.
- Real impact signal: backend p99, error rate, active requests, or user-facing SLO degraded.
- Not during an intentional deploy, canary, or health-filtering transition.

**Alerts should trigger concrete action**, not merely flag non-round percentages. "B receives zero traffic despite being healthy, in-zone, and eligible for all callers" deserves investigation far more than "B got 31% instead of 33.3% over 20 requests".


## 19. Lab: Measuring Distribution Across Three Inventory Replicas

The lab below teaches how to **count and explain data**, not how to prove "every instance must get exactly 1/3". Topology:

~~~text
order-service :8080
    |
    | @LoadBalanced RestClient
    | http://inventory-service/demo/whoami
    v
Spring Cloud LoadBalancer
    |
    +--- inventory-a :8081
    +--- inventory-b :8082
    +--- inventory-c :8083
~~~

Run all three backends from the same codebase, differing only in port and `demo.instance-id`. Use `SimpleDiscoveryClient` to focus on LoadBalancer without setting up an external registry.

### 19.1. Endpoint on Each Inventory Replica

Required dependencies on inventory: `spring-boot-starter-web` and `spring-boot-starter-actuator`. For the custom Micrometer Counter, use `io.micrometer.core.instrument.Counter` provided by the matching dependencies.

~~~java
package com.example.inventory;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final String instanceId;
    private final Counter completedHandlerCounter;

    public InstanceController(
            @Value("${demo.instance-id}") String instanceId,
            MeterRegistry registry) {

        this.instanceId = instanceId;

        this.completedHandlerCounter = Counter.builder(
                        "demo.inventory.handler.requests"
                )
                .description("Requests reaching the demo handler")
                .tag("instance", instanceId)
                .register(registry);
    }

    @GetMapping("/demo/whoami")
    public InstanceReply whoAmI() {
        completedHandlerCounter.increment();
        return new InstanceReply(instanceId);
    }

    public record InstanceReply(String instanceId) {
    }
}
~~~

This counter tracks **requests reaching the demo handler**, not *every LoadBalancer instance selection*, nor does it verify transport delivery of the response. If a client times out before reaching the backend, the counter does not increment; if the backend finishes processing and the response drops in transit, the counter **still increments**.

Launch three inventory processes with distinct properties:

~~~powershell
java -jar inventory-service.jar --server.port=8081 --demo.instance-id=inventory-a
java -jar inventory-service.jar --server.port=8082 --demo.instance-id=inventory-b
java -jar inventory-service.jar --server.port=8083 --demo.instance-id=inventory-c
~~~

Run each command in a **separate terminal**. These commands assume a built demo JAR; this is not a prebuilt Spring Cloud artifact. In a real Maven/Gradle project, launch accordingly.

Before testing LoadBalancer, call each instance directly:

~~~powershell
Invoke-RestMethod "http://localhost:8081/demo/whoami"
Invoke-RestMethod "http://localhost:8082/demo/whoami"
Invoke-RestMethod "http://localhost:8083/demo/whoami"
~~~

Confirm you receive `inventory-a`, `inventory-b`, and `inventory-c` in turn and all three are ready.

### 19.2. Caller Configuration with SimpleDiscoveryClient and Metrics

In `order-service/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
              - uri: http://localhost:8083

    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

This setup uses **three equally weighted replicas** and intentionally disables zone/hint/sticky sessions and retries. If your project already has custom retries or suppliers, verify/disable them in the **lab environment** so measurement samples stay easy to interpret. Never turn off production retries or circuit breakers just to make charts look cleaner.

### 19.3. RestClient by Service ID

Create the load-balanced builder:

~~~java
package com.example.order.http;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfig {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {

        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Expose a proxy endpoint:

~~~java
package com.example.order.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class InventoryProxyController {

    private final RestClient client;

    public InventoryProxyController(
            @Qualifier("inventoryRestClient") RestClient client) {

        this.client = client;
    }

    @GetMapping("/demo/inventory")
    public InstanceReply inventory() {
        return client.get()
                .uri("/demo/whoami")
                .retrieve()
                .body(InstanceReply.class);
    }

    public record InstanceReply(String instanceId) {
    }
}
~~~

`RestClient` calls `http://inventory-service/demo/whoami`, and Spring Cloud LoadBalancer selects a `ServiceInstance` from the configured list. This controller endpoint is for lab use only; responses exposing infrastructure IDs should not necessarily be open to the Internet.

### 19.4. Observe N = 10 First, Without Jumping to Conclusions

PowerShell:

~~~powershell
1..10 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/demo/inventory"
}
~~~

You may observe near-alternating Round Robin, or—if Random is configured—a few consecutive hits on the same replica. **Ten requests only confirm routing works; they cannot establish long-term statistical distribution.**

Verify the active algorithm and suppliers before predicting ratios. If a client uses weighted routing or a custom `ReactorLoadBalancer<ServiceInstance>`, do not expect default behavior.

### 19.5. Count 900 Responses and Preserve Errors

~~~powershell
$N = 900
$results = New-Object 'System.Collections.Generic.List[string]'

for ($i = 0; $i -lt $N; $i++) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8080/demo/inventory" -TimeoutSec 3
        $results.Add([string]$response.instanceId)
    }
    catch {
        $results.Add("ERROR")
    }
}

$results |
    Group-Object |
    Sort-Object Name |
    Select-Object Name, Count,
        @{ Name = "Percent"; Expression = { [math]::Round(100.0 * $_.Count / $N, 2) } }
~~~

This is a **sequential** script from a single PowerShell process. It counts **completed responses received by the client** and groups failures into `ERROR`; you cannot assume N=900 means exactly 900 LoadBalancer selections if the framework retries.

Example **illustrative output, not real measured results**:

~~~text
Name          Count  Percent
----          -----  -------
inventory-a     287    31.89
inventory-b     305    33.89
inventory-c     308    34.22
~~~

Under single-caller Round Robin with a fixed 3-instance list and no retries, selections may hit or approach 300/300/300 after 900 selections; completed counts can still differ when errors happen. Under Random, 287/305/308 is no proof of a bug. At large `N`, cross-check directly against metrics.

### 19.6. Cross-Check Caller and Backend Actuator Endpoints

On the caller:

~~~powershell
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.success"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.failed"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.discard"
~~~

On the backends, depending on exposure configuration:

~~~powershell
Invoke-RestMethod "http://localhost:8081/actuator/metrics/demo.inventory.handler.requests"
Invoke-RestMethod "http://localhost:8082/actuator/metrics/demo.inventory.handler.requests"
Invoke-RestMethod "http://localhost:8083/actuator/metrics/demo.inventory.handler.requests"
~~~

Before comparing, ensure backends also expose metrics via `management.endpoints.web.exposure.include` in the lab. With the custom counter `demo.inventory.handler.requests`, Actuator returns the count and `instance` tag registered by code. Across multiple processes, each counter starts at 0; subtract the **initial baseline** instead of comparing raw counts between a freshly restarted instance and one running for hours.

On the caller, inspect actual `availableTags` on LoadBalancer meters. Only use timer counts directly for per-instance distribution when an instance tag is actually present and reliable; if tags are missing or unstable, supplement with verified backend metrics and traces.

### 19.7. When Testing with WebClient or OpenFeign

The lab logic remains identical: business code calls by service ID, the backend returns `instanceId`, and the caller aggregates outcomes.

With WebClient:

~~~java
// webClient must be built from @LoadBalanced WebClient.Builder
Mono<InstanceReply> reply = webClient.get()
        .uri("http://inventory-service/demo/whoami")
        .retrieve()
        .bodyToMono(InstanceReply.class);
~~~

The request executes only upon subscription. If `Mono` is never subscribed to or is cancelled, **never count it as an HTTP attempt definitely sent**.

With OpenFeign:

~~~java
@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/demo/whoami")
    InstanceReply whoAmI();
}
~~~

Add `@EnableFeignClients` and the required dependencies; this snippet only shows the caller's interface. Define `InstanceReply` accordingly. OpenFeign may use a different HTTP client, retryer, and metrics setup than WebClient, so always compare **equivalent** observation layers rather than comparing a timer count directly against total method calls arbitrarily.

## 20. Experimenting with Topology Changes to Understand Ratios

After stabilizing the baseline lab, change **one factor at a time**.

### Scenario A — Stop inventory-c

Stop the process on port 8083 while static `SimpleDiscoveryClient` still returns that URI. Without a health-check supplier configured, LoadBalancer **may continue selecting C**, triggering connection errors.

Observed results:

- A/B still return 200.
- Attempts selecting C fail before reaching the backend.
- C's **completed responses** share drops to 0.
- C's selection share **does not necessarily drop**, because static discovery has not removed C.

This demonstrates why "C has zero successes" does not mean "LoadBalancer stopped picking C".

Once a suitable `HealthCheckServiceInstanceListSupplier` is enabled and removes C from the eligible set, new selections distribute across A/B per policy. In Spring Cloud, the health supplier can have its own refresh/caching interval; verify update timing rather than assuming changes take effect instantaneously.

### Scenario B — Slow Down B

Modify the **lab environment** so B delays 500 ms while A/C respond fast. While all still return 200, Round Robin may select B at a similar frequency while B's **active requests** and p95/p99 climb.

Investigate B's performance/backpressure/capacity rather than blindly swapping Round Robin for Random. If timeouts or health filtering eventually exclude B, expected distribution shifts over time.

### Scenario C — Enable Bounded Retries

Inject a transient connection error on A or one instance, then enable retries in the lab only. Observe:

- One logical request can generate two attempts.
- A retry-aware supplier may avoid the failed instance, or could re-select it depending on policy.
- Backend request counts can exceed user request counts.
- Caller success counts can differ from network attempt counts.
- Retries increase latency and load; avoid enabling them across multiple layers simultaneously without a deadline.

Test reports must specify the exact **layer being counted**.

### Scenario D — Caller Runs Two Replicas

Run two `order-service` instances calling the same inventory service ID. Each caller maintains its own Round Robin state. If user traffic hits caller A and caller B unevenly, combined selections/responses will differ from the single-caller lab.

Never assume Spring Cloud LoadBalancer maintains a **global atomic Round Robin counter across caller JVMs**.

## 21. Non-Flaky Testing: What Should You Assert?

### For Round Robin Under Controlled Conditions

If a unit/integration test controls **one LoadBalancer instance**, a fixed list `[A, B, C]`, no retries, no concurrency, and no supplier changes, you can assert each instance's selection count differs by at most one after `N` selections (and matches exactly when `N` is divisible by three). Assert at the **selection** layer or an equivalent mock/stub, not on response completion order.

If tests run concurrently with other clients, experience differing warm-up, or refresh instance lists, such assertions can flake because experiment assumptions no longer hold.

### For Random

Never write tests like:

~~~java
// Anti-pattern: random does not guarantee exact 3/3 split after 6 requests.
assertEquals(2, countA);
assertEquals(2, countB);
assertEquals(2, countC);
~~~

Instead:

1. Unit test that selection never picks an instance outside the eligible set.
2. Test empty/single-instance lists and valid fallback behavior.
3. If a test requires a specific choice, use a deterministic/stub strategy rather than real Random.
4. Statistical distribution tests belong on large samples with tolerances, recorded seeds/conditions where supported, and never arbitrary tight thresholds.
5. Distribution checks in load/performance tests should report **ratios, N, and expected intervals**, rather than becoming flaky unit tests on every PR.

### Testing Metric Semantics

Specifically test these distinctions:

- An HTTP 500 may be counted as a response rather than an exception by LB lifecycle depending on integration.
- A no-instance event increments discard rather than backend requests.
- A retried request can emit multiple events at certain metric layers.
- A request rejected by a circuit breaker may never touch LoadBalancer.
- Backend handler counters and HTTP server metrics have different scopes.
- An instance restart resets cumulative counters.

These tests protect **measurement quality**—just as vital as routing algorithm correctness.


## 22. Diagnostic Table for Abnormal Load Distribution

| Observation | Possible explanation | Evidence to gather |
|---|---|---|
| All 10 requests hit A | Coincidental Random run, sticky session, or only A eligible | Larger sample, strategy, and supplier check |
| A/B/C do not get exact 1/3 | Random variation, weights, zone/hint, health filtering | Expected policy and `N` per window |
| Round Robin does not return A-B-C responses in order | Completions reordered by latency/concurrency | Selection events and traces |
| C has zero successful responses | C excluded or attempts to C failed | Eligible list, selections, client errors, and backend logs |
| `loadbalancer.requests.success` high while HTTP 5xx rises | Lifecycle success means response received, not HTTP 2xx | Status metrics at HTTP client/server |
| Backend count exceeds user requests | Retries, gateway traffic, probes, or background jobs | Attempts per logical call, routes, and sources |
| Backend count lower than caller selections | Connect failures, no-instance, or pre-delivery errors | Client transport errors and server access logs |
| Ratios shift after autoscale | Discovery/cache updates asynchronous | Registry events, supplier snapshots, and TTL |
| B receives less despite being healthy | Zone/hint, weights, sticky/session preference | Caller metadata, eligible list, and routing policy |
| A has higher active gauge | A is slower or has deeper queues/pools | p95/p99, CPU, pools, threads, queues |
| Prometheus counter drops suddenly | Process restart/metric reset or scrape gap | Restart timestamps, `rate`/`increase` reset handling |
| No `loadbalancer.requests.*` | Property disabled, missing registry, no events yet, or wrong app | Config, Actuator meter list, and sample traffic |
| Instance tag missing | Integration does not supply that metadata | Actual `availableTags` and backend metrics |
| Time series explode | Dynamic URI/path/user ID in labels | `include-path=false`, `MeterFilter`, and route templates |
| One logical request picks two instances | Retry, resubscription, or proxy retry | Trace attempts and retry config |
| Discard increases | LoadBalancer failed to obtain a target instance | Service ID, discovery, and suppliers |
| Even request split but poor user SLO | Uneven work/capacity, timeouts, or latency | End-to-end latency, error rate, active requests |
| Two callers show different ratios | Differing caller zone/state/version | Caller ID, config, and instance list |
| 503 rises while instance list is non-empty | Backend or proxy returned 503 | Classify status origin and health logic |

## 23. Analysis Runbook When Dashboards Show Skew

Execute in order:

1. **Bound the scope:** service ID, operation, caller instance, zone, time window, and deployed version.
2. **Confirm the denominator:** does the chart count selections, HTTP attempts, backend arrivals, 2xx responses, or logical calls? Are failed/cancelled attempts included?
3. **Check sample size:** is `N` large enough to talk about percentages? With only a few requests, report raw counts without concluding.
4. **Verify expected policy:** Round Robin, Random, weights, zones, hints, sticky/affinity, canary, and retry-aware supplier.
5. **Inspect the eligible list:** which instances did discovery/health suppliers provide during each sub-window?
6. **Cross-check caller and server:** lifecycle metrics, transport metrics, backend HTTP statuses, and server request counters.
7. **Inspect retries:** attempts per logical operation, which layer owns retries, and any no-instance events?
8. **Read latency/resource metrics:** do p95/p99, active requests, CPU, queues, or connection pools diverge?
9. **Inspect traces:** did requests fail before reaching the instance, or did the backend process them while responses failed to return?
10. **Reproduce under control:** one caller, static list, clear policy, no retries, sufficient `N`, and no scaling during the window.
11. **Fix the verified root cause:** health filtering, discovery cache, zone/weight metadata, retry budget, or backend bottleneck—never swap algorithms on a hunch.
12. **Evaluate after change:** use the same traffic cohort and SLOs rather than comparing two few-minute percentages.

### Responsible Conclusion Examples

**Insufficient evidence:**

> "Round Robin is broken because the first three requests all went to A."

**Evidence-backed:**

> "Over a 15-minute window, a single caller sent 900 GET inventory calls; three instances remained continuously healthy under unweighted Random policy with retries disabled. Successful responses were A=287, B=305, C=308. This distribution shows no clear deviation from 1/3 under the simple model; continue monitoring latency/error rates and cross-checking selection metrics."

These numbers are **illustrative**, not real measured data. In production, include data sources, explicit count definitions, timezone/window, error counts, and metric completeness.

## 24. Checklist Before Concluding a Load-Balancing Issue

- [ ] Know the exact `ReactorLoadBalancer<ServiceInstance>` algorithm and configuration in use.
- [ ] Check `ServiceInstanceListSupplier` and eligible instances within each window.
- [ ] Separate selections, sent attempts, received requests, successful responses, and logical calls.
- [ ] Segment data by caller, route, version, zone, and time when policy/topology changes.
- [ ] Never judge Random from a handful of requests; always state `N` and expected probabilities `p_i`.
- [ ] Never assert Round Robin by response completion order under concurrency.
- [ ] Never compare against `1/N` instances when policies use weights, hints, zones, or affinity.
- [ ] Inspect caches, discovery, health checks, retries, and scaling events before concluding a replica is ignored.
- [ ] Know the source of instance IDs; do not rely solely on response bodies or sampled logs.
- [ ] Enable `spring.cloud.loadbalancer.stats.micrometer.enabled` with a `MeterRegistry` when LoadBalancer metrics are needed.
- [ ] Understand `active`, `success`, `failed`, and `discard` semantics, and inspect actual `availableTags`.
- [ ] Never assume lifecycle `success` equals HTTP 2xx.
- [ ] Cross-check backend statuses, durations, and counters with caller lifecycle/transport metrics.
- [ ] Use baselines/`rate`/`increase` for cumulative counters; account for restarts and scrape gaps.
- [ ] Secure Actuator/Prometheus and restrict high-cardinality tags/URI paths.
- [ ] Monitor p95/p99, error rate, active requests, and resources—not request counts alone.
- [ ] Separate logical calls from attempts across retry, timeout, and circuit-breaker policies.
- [ ] Account for warm-up, rollouts, health transitions, and autoscaling.
- [ ] Write deterministic unit tests for selection edge cases; evaluate Random statistically on large samples separately.
- [ ] Skew alerts must account for sample size, expected policy, and operational impact.
- [ ] Draw conclusions from multiple corroborating sources, never one screenshot or three responses.

## References

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstanceListSupplier`, Round Robin/Random, health, caching, retries, and **Spring Cloud LoadBalancer Statistics**.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): `spring.cloud.loadbalancer.stats.micrometer.enabled` and instance selection properties.
- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `MeterRegistry`, timers, counters, gauges, HTTP metrics.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): configuring and securing `/actuator/metrics`.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter types, tag cardinality, timers, and distribution statistics.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `rate()`, `increase()`, and counter resets.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient and blocking HTTP clients.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive WebClient and subscriptions.
- [Spring Cloud OpenFeign — Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign, LoadBalancer, and observability.

**Conclusion:** Accurate load-distribution observability starts with **the denominator, the eligible instance set, the expected policy, and the statistical window**—not how many times a replica appears in a handful of responses. Random exhibits natural statistical variance; Round Robin is shaped by concurrency, retries, changing lists, and multiple independent callers. Combining Micrometer LoadBalancer lifecycle metrics, backend HTTP counters, tracing, sufficiently large samples, and time-aligned discovery/health data lets you spot genuine distribution skew without mistaking randomness for an algorithmic bug.

# Integrating Prometheus and Building Dashboards for Spring Cloud Gateway

An API Gateway is typically the **shared entry point** of a microservices system. When users hit `502/503/504` errors, slow requests, or rate limiting, looking solely at a single backend's logs will not answer: which route did the request traverse, is the Gateway or downstream slow, how many retries happened, is the circuit breaker open, or does the issue occur on just one Gateway instance?

In **SPRING_CLOUD_GATEWAY**, **Observability** requires combining **metrics, traces, and logs**; this lesson focuses specifically on **integrating Prometheus and building dashboards** capable of answering real operational questions. Prometheus scrapes time series from **Micrometer/Actuator**, while Grafana (or an equivalent query UI) visualizes traffic, error rates, latency, saturation, scrape health, and signals from route predicates, filter chains, service discovery, authentication, rate limiting, retries, circuit breakers, and TLS.

Learning objectives:

1. Properly enable the Micrometer Prometheus Registry and `/actuator/prometheus` endpoint on the Gateway.
2. Distinguish metrics for **incoming application requests**, **Gateway-routed requests**, and **outbound backend attempts**.
3. Verify meter names, tags, and units from the **live runtime** instead of copying version-mismatched PromQL.
4. Write PromQL queries for RPS, HTTP 5xx, mean latency, P95/P99, and scrape status.
5. Design dashboards around operational questions with route/instance filter variables and actionable alerts.
6. Bound cardinality, protect metrics endpoints, and test scenarios involving retries, rate limiting, fallbacks, caching, and multiple Gateway instances.

> **Scope:** Primary implementation examples target **Spring Cloud Gateway Server WebFlux** with Spring Boot Actuator and Micrometer. **Gateway Server Web MVC** uses a different web stack and metrics integration; do not assume identical meter names, tags, or Gateway metrics enablement flags across all release trains. Verify starter names, configuration namespaces, meters, and labels against your **actual Spring Boot/Spring Cloud/Gateway version**. URIs and ports in this lesson are for a lab environment; real Prometheus endpoints must be secured.

## 1. Observability Architecture: From Gateway to Prometheus and Grafana

Prometheus typically uses a **pull** model: it periodically sends HTTP GET requests to a metrics endpoint and stores the resulting time series. In a Spring Boot app, Actuator paired with a Micrometer Registry exports data in Prometheus format.

~~~mermaid
flowchart LR
    C["Client / ingress"] --> G1["Gateway instance A"]
    C --> G2["Gateway instance B"]
    G1 --> S["Microservices / lb://"]
    G2 --> S
    G1 --> A1["Actuator /prometheus A"]
    G2 --> A2["Actuator /prometheus B"]
    P["Prometheus"] -->|"scrape 15s"| A1
    P -->|"scrape 15s"| A2
    P --> TS["Time-series storage"]
    GF["Grafana dashboards"] -->|"PromQL"| P
    AL["Alert rules / Alertmanager"] <-->|"evaluation/notifications"| P
    L["Logs + distributed traces"] -.->|"complementary analysis"| GF
~~~

**Prometheus does not receive individual HTTP requests directly.** On each scrape, it collects data aggregated by the application into counters, timers, gauges, or histograms. Thus, a transient error between two scrapes is still captured in an **incremented counter**, though you should never expect every individual event to appear as a log line in Prometheus.

### Role of Each Component

| Component | Role | Cannot Do on Its Own |
|---|---|---|
| **Spring Boot Actuator** | Exposes management endpoints and many JVM/HTTP metrics | Does not create Grafana dashboards automatically |
| **Micrometer** | Instrumentation API for counters, timers, gauges, and tags | Does not retain historical metrics long-term without a backend |
| **Prometheus Registry** | Exports meters in Prometheus scrape format | Does not enable network ACLs or endpoint security automatically |
| **Prometheus** | Scrapes, stores time series, runs PromQL and alert rules | Does not know route/business semantics unless the app instruments them |
| **Grafana** | Visualizes metrics and builds dashboards/variables | Cannot fix missing or flawed source metrics |
| **Logs/tracing** | Explains a specific request or call path | Does not replace aggregate latency/error-rate metrics |

**A good-looking dashboard is not proof of complete observability.** You must verify where in the request lifecycle data is collected, which conditions are missed, and the semantics of each indicator.

## 2. Start from Operational Questions, Not from Charts

In a microservices Gateway, on-call engineers typically need to answer:

| Question | Signal to Measure | Decision Supported |
|---|---|---|
| How many requests/sec enter the Gateway? | Inbound request rate | Capacity planning, traffic spikes |
| Which route is seeing increased traffic? | Gateway requests by route ID | Identify the involved service |
| How many requests return 5xx? | Error ratio by route/status | Detect system errors |
| Are users experiencing slowness? | P50/P95/P99 latency | Evaluate SLOs instead of averages |
| Is a route returning many 429s? | 429 rate, rate limiter outcomes | Quota tuning or Redis issue? |
| Are retries multiplying backend load? | Incoming requests vs. downstream attempts | Prevent retry storms |
| Is the circuit breaker opening or falling back often? | Breaker state, fallback counter if instrumented | Diagnose dependency outages |
| Is a route caching properly? | Actual cache hit/miss and origin request count | Measure offload and correctness |
| Is one node failing more than others? | Per-instance metrics and scrape `up` | Resolve deployment/network issues |
| Is the Gateway saturated? | CPU, heap/direct memory, connection pool, threads/event loop | Scale out or fix bottlenecks |
| Is the dashboard blank due to an app failure or scrape failure? | Prometheus `up`, target discovery, sample count | Separate missing data from zero traffic |

Organize dashboards around the **four golden signals**—*traffic, errors, latency, saturation*—followed by dedicated panels for **resilience** and **control-plane/routing changes**.

## 3. Distinguishing Three Layers of Request Metrics

This is the most important distinction to make before writing queries.

| Measurement Layer | Example Meter / Source | Requests Counted |
|---|---|---|
| **HTTP server inbound** | Spring Boot `http.server.requests` when instrumentation is enabled | HTTP requests received and instrumented by the app, potentially including 401/403/404 that never enter a Gateway route |
| **Gateway route-level** | `spring.cloud.gateway.requests` on supporting Gateway versions | Requests observed by the Gateway metrics filter on routes, per filter/version semantics |
| **Outbound/downstream attempts** | Reactor Netty/HTTP client metrics or verified custom counters | Calls sent from the Gateway to backends, potentially **more than one per client request** |

A single client request:

~~~text
GET /api/orders/42
  ├─ Spring Security authenticates
  ├─ Gateway matches route orders-read
  ├─ RequestRateLimiter checks quota
  ├─ Retry attempt #1 -> orders-service: 503
  ├─ Retry attempt #2 -> orders-service: 200
  └─ Client receives 200
~~~

Here, **one client request** generated **two outbound calls**. If you only look at `spring.cloud.gateway.requests`, you must not assume it reveals both backend attempts; if you look at HTTP client metrics, you must not treat every attempt as a separate user request.

### Requests That May Not Appear in Route-Level Meters

- Requests that match no Gateway route.
- Requests rejected by Spring Security **before route matching**.
- Requests served by a non-Gateway handler.
- Requests blocked by ingress/WAF before reaching the application.
- Filter short-circuits, retries, fallbacks, or caching depending on ordering and implementation.

**Do not infer application-wide 401/403/404 rates solely from gateway-route meters** when requests can be rejected before reaching the Gateway metrics filter. Supplement with inbound server metrics, access logs, security counters, or ingress telemetry.

## 4. Adding Dependencies for Actuator and Prometheus

In a **Gateway Server WebFlux** application using a **compatible Spring Boot/Spring Cloud BOM** to manage versions:

~~~groovy
dependencies {
    // Choose the Gateway Server WebFlux starter matching your release train.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    // Spring Boot management endpoints and Micrometer integration.
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Prometheus registry for Micrometer.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

In older Spring Cloud Gateway lines, the starter may be named `spring-cloud-starter-gateway` and the namespace may be `spring.cloud.gateway.*` rather than `spring.cloud.gateway.server.webflux.*`. **Never add starters from different lines side by side** just to experiment.

### Why Are All Three Needed?

- The Gateway starter provides the routing and filter engine.
- Actuator integrates Spring Boot management endpoints and application metrics.
- The Prometheus registry formats Micrometer data for Prometheus; **having Actuator alone does not guarantee `/actuator/prometheus` exists**.

Do not override the Micrometer version arbitrarily against the Spring Boot BOM. Changing registries or export conventions can alter metric names and leave existing dashboards blank.

## 5. Configuring Actuator for a Lab Environment

Example Gateway application running on **port 8080**, with management endpoints on **port 9091**:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: gateway-edge
      environment: lab
~~~

**This is a lab configuration**, not sufficient to consider management endpoints secure. In production:

1. Use **network ACLs / Kubernetes NetworkPolicy / service mesh policies** so only Prometheus and administrators can reach the management port.
2. Enable TLS/authentication suitable for your scraper and deployment model; store credentials in Secrets, never in Git.
3. Restrict exposed endpoints: `metrics` is handy for discovering meter names in a lab, but does not need to be exposed to Prometheus in production.
4. Check which management context/port Actuator runs on and how Spring Security protects that context.
5. Never expose `env`, `configprops`, `heapdump`, `gateway route mutation`, or `*` to the internet just for debugging.
6. Set explicit scrape timeouts, network routing, and health checks.

**Separating the management port does not automatically secure it.** Port 9091 can still be reached from the internet if firewalls or load balancers expose it improperly.

### Checking Endpoints with curl

~~~bash
# Example only when curl runs on the same host/network namespace as the Gateway.
curl -i "http://127.0.0.1:9091/actuator/health"

# Useful in a lab to discover meter names:
curl -sS "http://127.0.0.1:9091/actuator/metrics"

# Prometheus text exposition:
curl -sS "http://127.0.0.1:9091/actuator/prometheus" \
  | grep '^spring_cloud_gateway_requests'
~~~

If the Gateway runs in a separate container, `127.0.0.1` inside the Prometheus container refers to **Prometheus itself**, not the Gateway. In Docker or Kubernetes, use appropriate DNS/service targets. If the actuator endpoint uses authentication/TLS, lab commands must use authorized credentials instead of disabling auth.

## 6. Enabling Gateway Route Metrics and Verifying Actual Names

In many Spring Cloud Gateway Server WebFlux lines, the **Gateway Metrics Filter** records this meter when Actuator is present:

~~~text
spring.cloud.gateway.requests
~~~

This is the **Micrometer meter name**, not the Prometheus time-series name. Prometheus typically converts timer series into:

~~~text
spring_cloud_gateway_requests_seconds_count
spring_cloud_gateway_requests_seconds_sum
spring_cloud_gateway_requests_seconds_max
~~~

Exact names and exported series depend on the registry, version, and configuration. **Never assume every Gateway version emits all three series or uses the exact tags below**; inspect the actual text returned by `/actuator/prometheus`.

### Common Gateway Tags

| Micrometer Tag | Meaning | Warning |
|---|---|---|
| `routeId` | ID of the Gateway route | Too many dynamic route IDs cause high cardinality |
| `routeUri` | Target/route URI | May expose topology and increase series count |
| `outcome` | HTTP outcome group | Know the exact groupings of your version |
| `status` | HTTP status as described by the meter | Do not confuse with `httpStatusCode` |
| `httpStatusCode` | HTTP status code, e.g., `200`, `503` | Commonly used for filtering 5xx |
| `httpMethod` | GET/POST/PUT/... | Only permits a finite value set |
| `path` (optional) | Request path when the corresponding tag is enabled | **High cardinality and PII risk** |

Some Gateway versions allow enabling the path tag via configuration such as:

~~~properties
# Example in versions using the older namespace:
spring.cloud.gateway.metrics.tags.path.enabled=false
~~~

Newer namespaces place similar properties under `spring.cloud.gateway.server.webflux.metrics...`. **Do not copy an old property into a newer version and assume it takes effect.** Verify property binding using `/actuator/configprops` in a secured environment, startup logs, or release-train docs. **Keep path-tag disabled** if routes contain arbitrary IDs, tokens, or sensitive values.

### Reading the Meter in Actuator

~~~bash
curl -sS \
  "http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests"
~~~

If `metrics` is exposed and traffic has matched a Gateway route, the response lists the meter and available tags. If it does not exist:

- No matching traffic has initialized the meter yet.
- Actuator/registry is missing or the Gateway metrics filter is inactive.
- Property/namespace changed or metrics are disabled.
- The app is running Gateway **Server Web MVC** or Proxy Exchange with a different meter set.
- The management endpoint is protected (`401/403`) or scraped on the wrong port.

**Do not “fix” this by writing PromQL against a nonexistent metric.** Verify the meter at runtime first, then build the dashboard.

## 7. Histograms and Why P95/P99 Do Not Exist Automatically

A standard Timer typically emits **count** and **sum** (in seconds when exported to Prometheus), which lets you compute **average latency**. However, computing **cluster-wide P95/P99 across multiple Gateway instances** requires **histogram buckets** (`..._bucket`) instrumented and exported via configuration.

Example enabling a **percentile histogram specifically for** `spring.cloud.gateway.requests` in Spring Boot versions supporting this property binding:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "[spring.cloud.gateway.requests]": true
~~~

Square brackets around the map key preserve dots in the meter name when Spring Boot's binder parses map keys; verify the effective configuration on your version.

Then query:

~~~bash
curl -sS "http://127.0.0.1:9091/actuator/prometheus" \
  | grep '^spring_cloud_gateway_requests_seconds_bucket'
~~~

If `_bucket` does not appear:

1. No meter or traffic yet.
2. Histogram not enabled on the exact timer name.
3. Actual meter name differs from expected.
4. Exporter/registry does not emit histograms as configured.
5. Using a different metric type or stack.

**Histograms are not free.** Every tag-value combination multiplies by the bucket count, increasing time series, RAM, and storage cost. Enable histograms only on timers needed for percentile SLOs; keep route IDs/URIs and bucket counts bounded.

### Units and Interpretation

| Series | Meaning | Unit |
|---|---|---|
| `..._seconds_count` | Number of recorded measurements | Count |
| `..._seconds_sum` | Total time of all measurements | Seconds |
| `..._seconds_bucket{le="..."}` | Measurements with value ≤ bucket boundary | Count, cumulative counter |
| `..._seconds_max` (if present) | Max per Micrometer time-window semantics | Seconds, **not P99** |

**Do not multiply by 1,000 twice by mistake.** Prometheus `_seconds` series are normally in **seconds**; Grafana can either set Unit = seconds or handle conversion to milliseconds automatically.

## 8. Setting Up a Scrape Job in Prometheus

Example Prometheus config file **strictly for a lab where Prometheus and Gateway share a host/network namespace**:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: gateway-edge
    metrics_path: /actuator/prometheus
    scheme: http
    static_configs:
      - targets:
          - "127.0.0.1:9091"
        labels:
          environment: lab
~~~

In Docker Compose, replace `127.0.0.1` with the reachable DNS/service name on the shared network; in Kubernetes, use Service/Pod discovery or Prometheus Operator `ServiceMonitor`/`PodMonitor` when those CRDs are installed. **Do not assume Prometheus automatically discovers Gateway pods.**

### Parameters to Watch

| Field | Purpose |
|---|---|
| `job_name` | Groups scrape targets, attached as the `job` label |
| `metrics_path` | Actuator Prometheus endpoint path |
| `scrape_interval` | Sampling interval |
| `scrape_timeout` | Timeout per scrape attempt |
| `static_configs` or service discovery | Targets to scrape |
| `relabel_configs` | Normalizes/limits labels from discovery |
| TLS/Auth config | Secures access to management endpoints |
| `metric_relabel_configs` | Filters series at ingestion; review cost and data loss risks |

**Never embed plaintext usernames/passwords or bearer tokens in shared config files.** When scrapes require auth, use secret files/Secrets and proper TLS/auth settings, restricting read permissions on Prometheus credentials.

### Is Prometheus Scraping Successfully?

Query:

~~~promql
up{job="gateway-edge"}
~~~

Meaning:

- `1`: the latest scrape succeeded for that target.
- `0`: target exists in discovery/config, but scraping failed.
- **No series**: target not yet discovered, wrong job name, retention/lookback expired, or wrong label query.

`up=1` proves **scraping works**; it **does not prove Gateway routing and backends are healthy**. Combine it with route-level metrics, traffic probes, and health checks.

## 9. Basic PromQL: Request Rate (RPS)

The following examples **assume** the live runtime emits `spring_cloud_gateway_requests_seconds_count` with `job`, `routeId`, and `httpStatusCode` labels. Adjust if your scraped series use different label names.

### Total RPS of Gateway Routes

~~~promql
sum(
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

`rate(counter[5m])` estimates the average per-second growth rate over a 5-minute window and handles counter resets (such as pod restarts) far better than raw counter subtraction.

### RPS by Route ID

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

This shows how much traffic `catalog-read`, `orders-write`, etc. receive across all Gateway instances scraped under that job. Keep route IDs consistent across nodes; randomly generated route IDs per deploy make dashboards hard to compare.

### RPS by HTTP Method

~~~promql
sum by (httpMethod) (
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

To compare GET vs. POST on one route, add `routeId="catalog-read"` or use a Grafana variable as shown in the dashboard section.

### Total Requests Over 1 Hour

~~~promql
sum(
  increase(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[1h])
)
~~~

`increase` computes counter growth adjusted for resets and extrapolated over the window; results may be non-integers. It is great for trends and approximate totals over a period, **not an exact log of individual requests**.

## 10. PromQL Error Rates: 5xx, 4xx, and 429

A Gateway dashboard must separate **server errors** from **client errors**, because 401/403 responses from authentication policies do not mean the Gateway itself is failing.

### 5xx Rate by Route

~~~promql
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      httpStatusCode=~"5.."
    }[5m]
  )
)
~~~

### 5xx Percentage (%) by Route

~~~promql
100 *
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      httpStatusCode=~"5.."
    }[5m]
  )
)
/
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge"
    }[5m]
  )
)
~~~

Formula:

\[
\mathrm{5xx\ ratio} = \frac{\mathrm{5xx\ requests}}{\mathrm{all\ measured\ gateway\ requests}}\times100\%
\]

**Note on the denominator:** this counts only requests observed by the *gateway-route meter*. It does not automatically represent all inbound requests, especially when Spring Security rejects pre-route or requests match no route.

### 429 Rate

~~~promql
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      httpStatusCode="429"
    }[5m]
  )
)
~~~

`429 Too Many Requests` can come from `RequestRateLimiter`, ingress, or downstream. **Do not assume 429s from every layer are recorded by the Gateway route meter**; verify filter ordering and cross-check inbound/ingress logs.

### 401/403 and 404

- 401/403 may reflect Spring Security rejecting requests before Gateway route metrics are recorded.
- 404 may come from no matching route or the backend returning 404 after route matching.
- 5xx can also stem from fallbacks/circuit breakers or client connection errors, not only the backend.

Therefore, an **inbound HTTP dashboard** should also include `http.server.requests` if actually exported by the app, and a **downstream health dashboard** should track per-target counters separately.

### Handling a Zero Denominator

When a route receives no requests for 5 minutes, the denominator is 0 or the series disappears. Do not display “0% errors” as proof the route is healthy. Configure dashboards to show **No data / No traffic** when the denominator is meaningless, and set minimum traffic thresholds on alerts.

## 11. PromQL Latency: Mean, P95, and P99

### Average Latency (Seconds)

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_sum{job="gateway-edge"}[5m])
)
/
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{job="gateway-edge"}[5m])
)
~~~

Average latency helps show overall trends, but **is insufficient for evaluating tail latency**. A route with 95% of requests at 20 ms and 5% at 5 s still has a relatively low average compared to what slow users actually feel.

### P95 by Route, When Histogram Buckets Actually Exist

~~~promql
histogram_quantile(
  0.95,
  sum by (le, routeId) (
    rate(
      spring_cloud_gateway_requests_seconds_bucket{
        job="gateway-edge"
      }[5m]
    )
  )
)
~~~

### P99 by Route

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(
      spring_cloud_gateway_requests_seconds_bucket{
        job="gateway-edge"
      }[5m]
    )
  )
)
~~~

**`le` must be kept** in `sum by (le, routeId)` because `histogram_quantile` needs the bucket boundaries. To compute **Gateway-wide** P95, use `sum by (le)`. Never average per-instance P95 values to infer cluster-wide P95.

### Limitations of Histogram-Based Percentiles

- Histograms provide **percentile estimates derived from bucket boundaries**, not exact timestamps of individual requests.
- Overly sparse buckets near the SLO threshold reduce estimation accuracy.
- A 5-minute window with very few requests causes P99 to fluctuate wildly.
- Some latency metrics measure the **Gateway filtering/routing phase**, which does not necessarily equal end-user latency across CDN/ingress/network.
- Without `_bucket`, **never pass off `_max` or the mean as P99**.

### Example Reading Results

Suppose the dashboard for route `catalog-read` shows:

| Metric | Illustrative Value | Interpretation |
|---|---:|---|
| RPS | 240 requests/s | Traffic measured by gateway-route meter |
| Average | 75 ms | Mean across the measured phase |
| P95 | 180 ms | Roughly 95% of measurements fall below this estimate |
| P99 | 650 ms | Tail latency; investigate if SLO is stricter |
| 5xx ratio | 0.4% | Not necessarily caused by the Gateway itself |
| 429 rate | 15 req/s | Identify which layer emits 429 and check quota policy |

These numbers are **synthetic data for interpretation practice**, not measurements from a real system.

## 12. Designing Grafana Dashboards Around Investigation Flow

A useful dashboard lets operators move from **overview → route → instance → downstream**, rather than piling up unrelated charts.

### Suggested Layout

| Row | Panel | Chart Type | Purpose |
|---|---|---|---|
| 1. Health | Scrape `up` per instance | State/Stat | Is telemetry still being collected? |
| 1. Health | Total inbound RPS, Gateway routed RPS | Time series | Distinguish traffic drops, unmatched, and denied requests |
| 1. Health | Global 5xx ratio | Stat + sparkline | Quick check on availability risk |
| 1. Health | Global P95/P99 | Time series | Gateway-wide tail latency |
| 2. Routes | RPS by route ID | Stacked time series / table | Hot routes and traffic shifts |
| 2. Routes | 5xx rate by route | Time series / table | Isolate failing routes |
| 2. Routes | P95/P99 by route | Time series | Slow routes |
| 2. Routes | Status code breakdown | Time series | Separate 401/403/404/429/5xx |
| 3. Infrastructure | CPU, heap, GC, thread/event-loop or pool metrics | Time series | Saturation and resource leaks |
| 3. Infrastructure | JVM/process uptime/restarts | Stat | Correlate with cold starts/deploys |
| 4. Resilience | Retry attempts, breaker state, fallback count | Time series | Detect cascades and retry storms |
| 4. Resilience | Cache hits/misses, rate-limit decisions | Time series | Efficiency and quota accuracy |
| 5. Deployment | Route revision, app version, node health | Table | Configuration drift and canaries |

**Not every panel has a built-in metric.** The resilience row requires instrumentation at the right points or connecting Resilience4j/Redis/cache/LoadBalancer metrics where versions and binders support them. Hide or clearly mark **Not instrumented** on panels lacking data sources instead of showing 0 as if a feature never failed.

### Grafana Variables

Useful variables:

- `$job` or `$application`: select the Gateway service.
- `$environment`: staging/prod.
- `$instance`: inspect a specific node or select All.
- `$routeId`: filter to a route of interest.
- `$statusClass`: select 2xx/4xx/5xx on dedicated panels.

Example **Grafana Prometheus variable query** syntax (not PromQL run directly in Prometheus's expression browser):

~~~text
label_values(
  spring_cloud_gateway_requests_seconds_count{job="gateway-edge"},
  routeId
)
~~~

Inside a panel's PromQL, reference the Grafana-interpolated variable:

~~~promql
sum by (routeId) (
  rate(
    spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge",
      routeId=~"$routeId"
    }[5m]
  )
)
~~~

**The `$routeId` variable is Grafana template syntax, not standard PromQL.** When enabling All/multi-select, ensure regex formatting and escaping work properly. Never let dashboard viewers query PII labels (which shouldn't exist in metrics anyway).

### Units and Axes Organization

- RPS: `req/s`.
- Error ratio: percentage `0–100%`.
- Latency: seconds or milliseconds, **consistent** across panels.
- Memory: bytes/MiB/GiB, distinguishing heap from direct memory.
- CPU: percentage per process/container, avoiding confusion with CPU cores.
- `up`: display 0/1 per instance; never turn “no series” into 1.

Add panel notes specifying: **which meter, where it measures, how long the sample window is, and whether 401/404/429 are included**.

## 13. Optimizing Cardinality and Time-Series Budgets

Prometheus stores each **metric name + labels** combination as a separate time series. On a Gateway, series counts grow rapidly with routes, status codes, methods, instances, and histogram buckets.

Suppose a histogram has:

- 100 route IDs;
- 6 HTTP status codes;
- 4 methods;
- 8 instances;
- 15 buckets (illustrative).

Bucket series alone can reach:

\[
100\times6\times4\times8\times15 = 288,000
\]

This is a **worst-case estimate if every combination occurs**, excluding `_sum`/`_count`, additional labels, and other metrics. Not every Gateway automatically produces this exact count.

### What to Label and What Not to Label

| Tag | Recommendation | Why |
|---|---|---|
| `routeId` | Yes, if route set is controlled | Enables per-route analysis |
| `application`, `environment`, `region` | Yes, finite values | Compares environments |
| `httpMethod` | Yes | Finite cardinality |
| `httpStatusCode` | Yes | Error debugging |
| `routeUri` | Consider carefully | Can vary and expose topology |
| Full `path` | **Avoid** | `/users/1`, `/users/2`, ... create unbounded series |
| URL with query string | **No** | PII/tokens and cardinality |
| Free-form `userId`, `tenantId` | **No** | Unbounded cardinality and potentially sensitive data |
| JWT/token/API key/cookie | **Never** | Leaks credentials |
| `traceId`/`requestId` | Not as a metric tag | Unique per request; use traces/logs/exemplars instead |
| Raw exception message | No | PII, internal details, and high cardinality |

### Path Templates Instead of Raw Paths

If you genuinely need to distinguish API resource patterns, prefer **route IDs** or a **normalized route template** like `/api/orders/{id}` provided by the platform. Never build tags from `request.getURI().getRawPath()` or user-supplied queries.

With **dynamic routes**, limit new route IDs per minute/day, prune deleted routes, and watch cardinality on `routeUri` and optional `path`. A portal creating a new route ID per request can overload Prometheus and Grafana.

### Histograms Only Where Needed

Enable histograms on the 2–3 timers that truly need P95/P99 first; monitor series growth in Prometheus via `scrape_samples_scraped`, `prometheus_tsdb_head_series` (if available), or Prometheus internal dashboards. Never turn on histograms wholesale across every endpoint and tag just to “have more data.”

## 14. Monitoring Retry, CircuitBreaker, RateLimiter, Cache, and LoadBalancer

Resilience features change how Gateway metrics must be interpreted.

### Retry: Requests vs. Attempts Differ

A single client GET request may be retried 3 times before succeeding. If the dashboard only shows Gateway request counts and a 0% final error ratio, the backend might be absorbing **3x load** invisibly.

Track additionally (where instrumentation allows):

~~~text
gateway_downstream_attempts_total{
  route_id="catalog-read",
  outcome="success|failure"
}
~~~

This is a **suggested custom counter convention**, **not a default Gateway metric**. Each **outbound attempt** must be recorded **once** at the point where the request is actually sent; placing the counter at the wrong spot in the filter chain can count an entire retry loop once or double-count attempts.

A useful ratio:

\[
\mathrm{Attempt\ amplification}
=
\frac{\mathrm{Downstream\ attempts}}
     {\mathrm{Gateway\ routed\ requests}}
\]

A ratio near 1 is normal for routes issuing one outbound call per request; higher values can indicate retries, or intentional fan-out. **Do not apply it as a generic alert across BFF/aggregation endpoints.**

### CircuitBreaker and Fallback

If using Spring Cloud CircuitBreaker/Resilience4j, metrics for call outcomes, states, and slow calls may be available **when bindings/registries are properly enabled**. Exact series names depend on integration/version; never assume `resilience4j_circuitbreaker_state` or specific state values exist identically across every release.

A failure can fall back to a 200 response, meaning Gateway HTTP 5xx ratio **no longer reflects full quality degradation**. Add a dedicated **fallback counter** and design dashboards to separate normal successes from degraded successes.

### RequestRateLimiter and Redis

`RequestRateLimiter` can return `429` when quota is exceeded, which by itself doesn't prove Redis is healthy. When relying on Redis:

- Monitor Redis connectivity and latency via real client/Redis metrics.
- Count allowed/denied/error outcomes using a **low-cardinality policy ID** when instrumented.
- Never attach `principal` or raw API keys as metric tags.
- Distinguish 429s issued by the Gateway limiter, ingress, or downstream.

### LocalResponseCache

A response cache can cut outbound calls, yet **a fast HTTP 200 is not proof of a cache hit**. Measure actual lookup hits/misses in supporting implementations and compare against backend call counts. Cache metrics may come from a Caffeine binder or custom-instrumented filter rather than a default `gateway_cache_hits_total`.

Never chase hit ratios at the expense of caching responses across wrong users or tenants; **correctness and isolation** must be tested independently.

### Service Discovery / LoadBalancer

A `lb://orders-service` URI can route across multiple instances. Gateway route metrics capture `routeUri`, which **does not necessarily record the specific instance chosen**. To pinpoint an unhealthy backend instance, inspect metrics/traces from the HTTP client, load balancer, or instrumented backend, avoiding raw dynamic hosts as high-cardinality labels.

## 15. Monitoring Saturation: JVM, Netty, Pools, and TLS

While backend errors show up clearly in HTTP status codes, the Gateway can also slow down because it is saturated itself.

| Group | Common Metric / Source | What to Watch |
|---|---|---|
| JVM heap | `jvm.memory.used` / `jvm.memory.max` | Memory pressure, leaks |
| JVM GC | `jvm.gc.pause` | GC pauses inflating tail latency |
| Process CPU | `process.cpu.usage` or container metrics | CPU saturation |
| Threads | `jvm.threads.live` | Thread growth; stack-specific |
| Reactor Netty HTTP client | Connection pool/HTTP client metrics when enabled | Pending acquires, active connections, timeouts |
| Server connections | Netty/container/ingress metrics | Client concurrency, slow connections |
| TLS | Handshake failures from client/server/ingress metrics & logs | Certificate/SNI/trust issues |
| Redis/Discovery | Client/service metrics when instrumented | External dependency bottlenecks |
| Host/container | CPU throttling, memory limits, OOM kills | Infrastructure bottlenecks |

**Reactor Netty meter names can vary by version and metrics configuration**, and adding the Prometheus registry does not always export connection pool metrics automatically. Before building panels, check the live meter list and HTTP client support.

### Why Does Gateway P99 Rise Even When Backend P99 Does Not?

Possible causes:

1. Gateway event loop or Servlet threads are blocked.
2. Connection pool is exhausted or waiting on acquires.
3. DNS/TLS handshake or service discovery is slow.
4. Retry/backoff increases total elapsed time.
5. Request/response body filters buffer large payloads.
6. Redis rate limiter is slow or circuit breakers are transitioning states.
7. Scraper/dashboard is comparing two mismatched time-series scopes.

Use trace spans and correlation-ID logs to isolate the **slow hop** instead of guessing from a single latency panel.

## 16. Alerting: Conditional Alerts and Runbooks

An alert must answer: **what should the on-call engineer do upon receiving it?** Without clear actions, dashboards are just pretty charts.

### Example: High 5xx Ratio Alert with Sufficient Traffic

**Illustrative** Prometheus rule file:

~~~yaml
groups:
  - name: gateway-edge.rules
    rules:
      - alert: GatewayHigh5xxRatio
        expr: |
          (
            sum by (job) (
              rate(spring_cloud_gateway_requests_seconds_count{
                job="gateway-edge",
                httpStatusCode=~"5.."
              }[5m])
            )
            /
            sum by (job) (
              rate(spring_cloud_gateway_requests_seconds_count{
                job="gateway-edge"
              }[5m])
            )
          ) > 0.05
          and on (job)
          sum by (job) (
            rate(spring_cloud_gateway_requests_seconds_count{
              job="gateway-edge"
            }[5m])
          ) > 1
        for: 10m
        labels:
          severity: warning
          service: api-gateway
        annotations:
          summary: "High Gateway 5xx ratio"
          description: "5xx rate on sufficient traffic exceeded 5% for 10 minutes."
~~~

**5%, 1 req/s, and 10 minutes are illustrative thresholds**, not universal SLOs. In production, base thresholds on service risk, error budget, and time windows. The minimum traffic guard prevents false alarms when 1–2 requests produce a high error ratio.

### Scrape Failure Alert

~~~promql
up{job="gateway-edge"} == 0
~~~

Add rules/logic for **targets disappearing from discovery**: if the `up` series disappears completely, `up == 0` **will not catch it**. Never equate “no data” with “healthy.”

### High P99 Latency Alert

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
) > 1
~~~

This uses an illustrative **1 second** threshold. Pair it with a minimum traffic volume and a `for` duration; low-traffic routes make P99 noisy. For streaming/WebSocket APIs or large uploads, define dedicated latency SLOs rather than applying a 1-second limit to every route.

### Minimal Runbook for a 5xx Alert

1. Check `up` and sample freshness; avoid diagnosing a blank dashboard as an application outage.
2. Identify the top routes contributing to 5xx growth.
3. Compare P95/P99, traffic volume, and method/status code distribution.
4. Inspect retry amplification, circuit breaker opens/fallbacks, 429s, Redis, and backend metrics.
5. Compare Gateway instances/pods, deployment revisions, and route configuration changes.
6. Use traces/logs with correlation IDs (never raw tokens) to locate the failing hop.
7. If tied to a canary or config change, roll back safely; if caused by a dependency outage, reduce retry pressure/throttle or coordinate incident response.
8. After recovery, write a postmortem and fix alerts/dashboards if metrics were missing or miscounted.

## 17. Lab Exercise: Generating Traffic and Querying Prometheus

### Lab Setup

Assume:

- Gateway Server WebFlux: `http://localhost:8080`.
- Actuator management: `http://127.0.0.1:9091`.
- Catalog backend: `http://localhost:9090`, exposing `GET /catalog/items/42`.
- Prometheus has a `gateway-edge` target pointing at the management endpoint.
- Histograms are enabled on the route-level meter and `_bucket` has been verified.
- Lab access only; never send heavy test traffic to production.

Sample route in Gateway versions using the legacy configuration namespace:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
            - Method=GET
          filters:
            - StripPrefix=1
~~~

For `GET /api/catalog/items/42`, `StripPrefix=1` strips `/api` so the backend receives `/catalog/items/42`. If using Gateway Server WebFlux with the newer configuration namespace, place the route under the **matching release-train namespace** (such as `server.webflux`) and verify the route loads before measuring metrics.

### Step 1 — Send a Test Call and Verify the Path

~~~bash
curl -i "http://localhost:8080/api/catalog/items/42"
~~~

Confirm the backend is invoked properly. The status may be 200, 404, or another code depending on your test endpoint. If the request did not match the route, do not use it as evidence that the route-level meter is broken.

### Step 2 — Send Several Sequential Requests

~~~bash
for n in 1 2 3 4 5; do
  curl -sS -o /dev/null \
    -w "code=%{http_code} time=%{time_total}s\n" \
    "http://localhost:8080/api/catalog/items/42"
done
~~~

A small batch verifies **counter increments**, not reliable P99 values. Avoid drawing strict percentile conclusions from 5 samples.

### Step 3 — Verify the Meter in Actuator

~~~bash
curl -sS "http://127.0.0.1:9091/actuator/metrics" \
  | grep -o 'spring.cloud.gateway.requests'

curl -sS \
  "http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests"
~~~

If `/actuator/metrics` is exposed in the lab, the response lists available tags. If the meter is absent, revisit Section 6 to verify dependencies, property namespace, filter enablement, and route matching.

### Step 4 — Inspect Prometheus Text Exposition

~~~bash
curl -sS "http://127.0.0.1:9091/actuator/prometheus" \
  | grep '^spring_cloud_gateway_requests_seconds'
~~~

Check which series are emitted: `_count`, `_sum`, and `_bucket`. Note exact **live** label names. If they differ from the examples, update your PromQL accordingly.

### Step 5 — Query `up` and RPS

In the Prometheus expression browser:

~~~promql
up{job="gateway-edge"}
~~~

Then:

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

With only a few requests, `rate[5m]` may be small or lack enough samples immediately. Wait for Prometheus to collect several scrapes and inspect the target; **do not blindly spam traffic just to make a chart appear**.

### Step 6 — Generate a Controlled Error

On the **lab backend**, create an endpoint that intentionally returns `503`, route a path to it, and call it with cURL. Compare:

- Does the Gateway route meter record `httpStatusCode=503`?
- Does the inbound HTTP meter record the corresponding status?
- Did any Retry or CircuitBreaker turn the final response into 200, 502, or 504?
- How many attempts did the backend actually receive?
- Does the per-route 5xx ratio chart update once Prometheus scrapes the new counter values?

Never inject intentional 503 errors into production services, and never assume all 5xx errors originate from the backend.

### Step 7 — Controlled Shutdown of a Lab Target

Stop one test Gateway instance or close its management endpoint and observe `up=0`. Next, remove the target from scrape config/discovery and observe the **no-data** behavior. These are two distinct failure modes; dashboards and alerts must distinguish them.

## 18. Building a Grafana Dashboard Step by Step

### Step 1 — Configure the Datasource

In Grafana, add a **Prometheus datasource** pointing to the Prometheus server URL reachable from the **Grafana container/instance**—never mistakenly use the Gateway's `localhost`. Verify Explore can run:

~~~promql
up{job="gateway-edge"}
~~~

If no data returns, check Prometheus target/discovery, scrape errors, datasource URL, RBAC, and time range.

### Step 2 — Create Filter Variables

For example, create a `routeId` query variable using `label_values(...)` as in Section 12. Create an `instance` variable from the `instance` label of `up`, ensuring All/multi-select works with your regex filters. Keep route ID values controlled; avoid route IDs containing free-form user input.

### Step 3 — Build Panels in Order

1. **Scrape health** first so you know whether metrics are still arriving.
2. **Gateway routed RPS**, followed by **5xx ratio**.
3. **P95/P99** once bucket series exist.
4. **Top routes** by RPS and 5xx rate.
5. **By instance** when suspecting a single node.
6. **JVM/memory/CPU/connections** in the saturation row.
7. **Retry, circuit breaker, cache, rate limiter** where data sources and dedicated metrics exist.
8. **Deployment annotations** to correlate alerts with new versions or config changes.

### Step 4 — Create Investigation Links

From a route panel, add dashboard links or drill-downs filtered by `routeId`, `environment`, and `instance`, plus links to your trace/log viewer if integrated. **Never embed access tokens, user IDs, or raw queries in panel URLs.**

### Step 5 — Validate with Real Lab Events

- A successful request increments the counter.
- A lab backend 503 increments 5xx on the right meter.
- A route with no traffic shows **No data/No traffic**, not 100% success.
- A stopped scrape target returns `up=0`, or disappears if discovery changes.
- A Retry-enabled route shows backend attempts > incoming requests when instrumented.
- Grafana time range and timezone match the viewer's context.
- P95/P99 appear only when histograms emit buckets.

**A dashboard is only complete once you have triggered and verified at least one scenario for each critical panel.**

## 19. Troubleshooting: Wrong Metrics or Blank Dashboards

| Symptom | Common Cause | Resolution |
|---|---|---|
| `/actuator/prometheus` 404 | Missing Prometheus registry, endpoint not exposed, wrong path/port | Check dependencies, management context, exposure |
| `/actuator/prometheus` 401/403 | Management security requires credentials | Configure valid scrape credentials/network; don't disable auth carelessly |
| Prometheus `up=0` | Target unreachable, timeout, TLS/auth mismatch | Check Targets page and scrape error |
| No `up` series | Target not discovered, wrong job, or series expired | Check scrape config/service discovery |
| JVM metrics exist but no Gateway requests | No route traffic yet, Gateway metrics filter inactive, wrong stack | Check Actuator meters and route matching |
| Metric name differs from examples | Different namespace/release train/Micrometer naming | Use live runtime names and update PromQL |
| No `_bucket` series | Histogram not enabled for the right meter | Verify distribution config and restart if needed |
| P95/P99 blank while count exists | Wrong `le` query, missing buckets, wrong job/routeId regex | Inspect raw series |
| 5xx ratio is 0 while clients see errors | Errors happened before route metrics, final status changed, filter order | Compare ingress/inbound/backend/request traces |
| 429 missing from route meter | Limiter rejected before measurement point or 429 came from ingress | Add metrics at the blocking layer |
| Counter drops after deploy | Counter reset on app restart | Use `rate`/`increase`, never subtract raw values |
| Route RPS suddenly shifts after ID rename | Route IDs changed, duplicating series | Compare config revisions and series cardinality |
| P99 is very noisy | Low traffic or overly sparse buckets | Use a longer window and check sample count |
| P99 spikes after enabling body logging | Buffering/blocking in the Gateway | Remove body logging, profile, and inspect memory |
| Prometheus consumes excessive RAM | Path/user ID labels, overly wide histograms | Reduce cardinality and series count |
| Dashboard misdisplays seconds as milliseconds | Wrong unit conversion | Check `_seconds_*` and panel format |
| Many retries yet 5xx stays flat | Retries succeeded, final status is 200 | Instrument downstream attempts |
| Frequent circuit breaker fallbacks yet 200s | Degraded successes masked | Instrument fallback counter/state |
| One node loses traffic on dashboard | Scrape/down, service discovery, or routing imbalance | Check `up`, instance labels, deployment |
| Dashboard blank after datasource switch | Wrong Grafana datasource, time range, or permissions | Test `up` in Explore first |
| Metrics endpoint leaks topology | Public `routeUri`, job/instance labels | Restrict management network and viewing permissions |

### Six-Layer Diagnostic Workflow

1. **Is the application running and matching routes?** cURL a lab endpoint backed by a real service.
2. **Does Micrometer have the meter?** Query Actuator `/metrics` in a secured environment.
3. **Does Prometheus exposition contain the series?** Inspect `/actuator/prometheus` and label names.
4. **Is Prometheus scraping?** Check `up`, the Targets page, and job/instance labels.
5. **Is PromQL valid with enough samples?** Test count/rate first, then 5xx and histograms.
6. **Are Grafana units, time range, variables, and permissions right?** Test in Explore and verify each panel.

Never fix a blank dashboard by exposing all Actuator endpoints publicly or logging raw request bodies/tokens.

## 20. Production Acceptance Checklist

- [ ] Using the **correct Spring Cloud Gateway variant and release train**, without copying metrics configs from WebFlux to MVC unverified.
- [ ] Application includes `spring-boot-starter-actuator` and `micrometer-registry-prometheus`.
- [ ] `/actuator/prometheus` is exposed **only to Prometheus and authorized parties**.
- [ ] Management port enforces network ACLs, appropriate TLS/auth, and exposes no route mutations/heapdumps/secrets.
- [ ] Prometheus scrapes the right targets/services with `up=1` on every expected instance.
- [ ] Clear separation between `http.server.requests`, `spring.cloud.gateway.requests`, and outbound attempt metrics.
- [ ] Actual meters and tags verified via Actuator/Prometheus exposition.
- [ ] Not treating Gateway route metrics as complete counts for pre-routing 401/403/404s.
- [ ] Understanding how `rate`/`increase` handle counter resets and preserve time windows.
- [ ] Meaningful per-route RPS, 5xx ratio, status breakdown, and P95/P99 panels exist.
- [ ] Computing P95/P99 only from **actually exported** histogram buckets, never from `_max`.
- [ ] Seconds/ms units verified without improperly adding or averaging percentiles.
- [ ] No raw paths, userId, JWT, session, email, query string, or requestId used as metric labels.
- [ ] Cardinality controlled across `routeId`, `routeUri`, histogram buckets, and dynamic routes.
- [ ] Dedicated `up` panel and **No data** state so scrape failures are never mistaken for zero errors.
- [ ] Inbound requests and downstream attempts measured separately when Retry is enabled.
- [ ] 429/RateLimiter, breaker/fallback, and cache hit/miss tracked **only where genuinely instrumented**.
- [ ] Not assuming all Resilience4j/Redis/Netty metrics exist identically on every version.
- [ ] Monitoring heap/direct memory, GC, CPU, connections, and stack-specific saturation.
- [ ] Dashboards provide per-route, per-instance, and deployment-annotation views.
- [ ] Alerts include traffic guards, `for` durations, SLO-aligned thresholds, and owned runbooks.
- [ ] Tested backend 503, 429, unmatched route, down scrape target, and retry scenarios in a **lab**.
- [ ] Retention/series budgets, datasource permissions, and dashboard upgrade process alongside Gateway upgrades are in place.
- [ ] Logs/traces carry correlation IDs to debug slow hops without leaking PII/credentials into metrics.

## 21. Extended Exercises

**Exercise 1 — RPS and error budget.** Write PromQL showing requests/s and 5xx ratio by `routeId` over 5-minute and 1-hour windows. Explain why a route with zero traffic should show **No data** instead of 0% errors.

**Exercise 2 — Histograms.** Enable histograms on `spring.cloud.gateway.requests`, send enough lab requests, and compare P50/P95/P99. Use `sum by (le)` for cluster-wide and `sum by (le, routeId)` for per-route calculations; explain why you must never average P99 values from two pods.

**Exercise 3 — Retry amplification.** Send a GET to a backend returning 503 twice followed by 200. Create an outbound attempts counter at the right routing point (or use verified client metrics) and compare it to Gateway routed requests. Explain what happens if the counter is placed in the wrong position within the Retry filter chain.

**Exercise 4 — Scrape failures.** Shut down one lab management endpoint and observe `up=0`; then remove the target from discovery and observe **absence**. Propose two distinct alerts instead of conflating the two situations.

**Exercise 5 — Cardinality.** Generate a test dataset with 10,000 URL IDs behind a single normalized route ID. Compare series counts with and without the raw path label enabled. Never use real user IDs or tokens.

**Exercise 6 — Actionable alerting.** Write a rule for 5xx ratio > 2% over 10 minutes with an appropriate traffic guard for a hypothetical route. Outline the runbook: check `up`, route ID, p99, downstream traces, recent rollouts, and rollback decisions.

**Exercise 7 — Dashboard review.** Label any breaker/cache/Redis panels lacking live metrics as “Not instrumented.” Secure the Prometheus endpoint with a network policy and confirm Grafana can still query Prometheus without exposing Actuator to the internet.

## Official Reference Documentation

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — look up **Gateway Metrics Filter**, **Actuator API**, and **Server WebFlux/Server Web MVC** for your exact version.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — release trains and corresponding documentation.
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer, distribution histograms, tags, and registry configuration.
- [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — management endpoint exposure and security.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — counters, timers, histograms, meter names/tags, and cardinality.
- [Prometheus — Getting Started](https://prometheus.io/docs/prometheus/latest/getting_started/) — scrape configuration and basic queries.
- [Prometheus — Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase`, `histogram_quantile`.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) — `for`, labels, and annotations.
- [Grafana — Dashboards](https://grafana.com/docs/grafana/latest/dashboards/) — panels, variables, templates, and dashboard design.
- [Grafana — Prometheus Data Source](https://grafana.com/docs/grafana/latest/datasources/prometheus/) — configuring the datasource and PromQL in Grafana.

**Remember:** Integrating Prometheus for Spring Cloud Gateway goes beyond turning on `/actuator/prometheus`. You must **verify the actual exported metrics and labels**, separate **inbound requests, Gateway routed requests, and downstream attempts**, use `rate` and **histogram buckets** for RPS, error rates, and P95/P99, and build dashboards that support investigating **traffic, errors, latency, and saturation**. Bounding cardinality and securing management endpoints are mandatory security requirements; a dashboard is valuable only when its numbers are **accurately scoped, verifiable, and lead to concrete operational actions**.

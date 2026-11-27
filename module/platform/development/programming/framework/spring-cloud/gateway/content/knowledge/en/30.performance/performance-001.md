# Measuring Throughput and Latency Percentiles Across Hops in Spring Cloud Gateway

An API Gateway can handle **2,000 requests/second** and still frustrate users if 1% of requests take multiple seconds. Conversely, an average latency of 30 ms does not prove the system can absorb additional load: connection queues, blocked event loops, or an overloaded downstream can cause **P99 to spike sharply** right before throughput starts dropping.

This lesson belongs to the **Performance** chapter of **SPRING_CLOUD_GATEWAY** and focuses on one specific measurement capability: **measuring throughput and latency percentiles across each hop**. We will distinguish timing as seen from the client, ingress, Gateway, and backend; set up Micrometer/Prometheus along with distributed tracing; write PromQL queries for RPS/P50/P95/P99; run controlled benchmarks; and identify root causes when route predicates, filter chains, path/header transformations, service discovery, authentication, rate limiting, circuit breakers, retries, or TLS slow down the request path.

By the end of this lesson, you will be able to answer with data rather than guesswork:

1. At a specific load level, **how many requests actually complete per second** and how many fail or are rejected?
2. What are the **P50, P95, P99, and P99.9** latencies, and are they measuring **TTFB or the full response**?
3. Where does the extra time go—client/ingress, Security, Gateway filters, queue/connection acquire, DNS/TLS, downstream processing, or download back to the client?
4. How do retries, circuit breakers, fallbacks, and caches cause the **number of backend calls** to differ from the **number of user requests**?
5. Does an optimization improve **tail latency under the same traffic and error rate**, or does it merely raise throughput by dropping or rejecting requests?

> **Scope:** The main examples use **Spring Cloud Gateway Server WebFlux**, Reactor Netty, Spring Boot Actuator, Micrometer, and Prometheus. **Gateway Server Web MVC** has a different Servlet thread model, handler/filter APIs, and instrumentation: do not blindly apply Netty metrics or WebFlux `GlobalFilter`s to MVC. Starter names, configuration namespaces, meter names, labels, and specific measurement points vary across release trains. Inspect what your application **actually exports** before drawing conclusions. Numeric values and thresholds in this lesson are educational examples, not default production SLOs.

## 1. First-Principles Thinking: Measuring One Transaction Across Multiple Boundaries

An HTTP request passes through multiple hops, and each hop can involve **wait time**, **processing time**, and **data transfer time**. In Gateway Server WebFlux, the typical path is:

~~~mermaid
flowchart LR
    C["Client / load generator"] --> E["DNS / TCP / TLS / ingress"]
    E --> G["Gateway HTTP server"]
    G --> S["Spring Security / WebFilters"]
    S --> P["Route predicates / filter chain"]
    P --> Q["HTTP client pool / load balancer / TLS"]
    Q --> B["Backend HTTP server"]
    B --> D["Business logic / DB / cache"]
    D --> B
    B --> Q
    Q --> P
    P --> G
    G --> E
    E --> C
~~~

**These boxes do not automatically form independent timers that can simply be added together.** A Gateway timer may already include both route filters and backend wait time; a backend timer may include DB query time; an HTTP client span may include connecting, sending the request, and receiving the response. You must understand the **start/end points** and whether each measurement is **inclusive or exclusive**.

### Separating Three Observation Layers

| Location | What it measures | What it does not automatically know |
|---|---|---|
| **Client/load generator** | Time the caller waits, network errors, response body, TTFB/total | How much CPU the Gateway spent or how long the backend queued |
| **Gateway ingress + route metrics** | Requests received/routed, HTTP status, route ID, processing duration at measurement boundaries | Needs tracing/client metrics to break down downstream phases |
| **Downstream HTTP client + backend** | Connection/pool/HTTP attempts, backend server duration, DB/cache spans | Cannot infer client experience without ingress/network |

A request blocked by a WAF **never reaches the Gateway**. A request rejected by Spring Security before route selection may appear in inbound HTTP server metrics but not in Gateway route metrics. This is why you must define the **denominator** before comparing RPS and error ratios.

## 2. Precisely Defining Throughput and Types of RPS

**Throughput** is the amount of work **actually completed** per unit of time. For an HTTP Gateway, people commonly use **requests/second (RPS)**, though there are several ways to count it.

\[
\text{Completed RPS} = \frac{\text{completed requests in the measurement window}}{\text{window duration in seconds}}
\]

| Metric | What is counted? | Used to answer |
|---|---|---|
| **Offered RPS** | Rate at which the client/load generator attempts to send requests | How much load is being placed on the system? |
| **Accepted RPS** | Requests entering the ingress/Gateway at the measurement point | Are requests being blocked before the application? |
| **Gateway routed RPS** | Requests that matched a route and were recorded by the Gateway meter | Which route is receiving traffic? |
| **Completed RPS** | Requests that received a terminal HTTP response or finished as defined by the test | How much work was completed? |
| **Successful RPS** | Valid responses meeting success criteria (e.g., 2xx + valid body) | How much real business value is the system delivering? |
| **Rejected RPS** | 401/403/429/413... rejected by policy | Is throughput being pushed down by auth/quota? |
| **Downstream attempts/s** | Total outbound HTTP attempts | Are retries/fan-out amplifying backend load? |
| **Byte throughput** | Bytes/s uploaded or downloaded at a boundary | Is the network or streaming saturated? |

**A system that returns fast 429s for 80% of requests must not be considered fast or healthy just because completed RPS and average latency look great.** Always examine **successes, errors, rejections, and actual offered requests** side by side.

### Calculation Example

Over 60 seconds in a lab run:

- The client attempts to send 12,000 requests: offered = **200 RPS**.
- The Gateway completes 11,700: completed = **195 RPS**.
- Of those, 11,100 satisfy the contract, 400 are 429, and 200 are 5xx.
- Successful throughput = **185 RPS**; 429 = **6.67 RPS**; 5xx = **3.33 RPS**.

**Do not treat 195 RPS as "successful capacity"**, because 600 requests did not deliver the expected business outcome.

## 3. Concurrency, Arrival Rate, and Little's Law

Higher throughput does not mean latency will stay constant. When each request holds a connection longer, the number of concurrent in-flight requests grows.

A commonly used steady-state form of **Little's Law** is:

\[
L = \lambda W
\]

Where:

- `L` is the **average number of transactions currently in the system**;
- `\lambda` is the **average completion/arrival rate** in steady state (requests/s);
- `W` is the **average time a transaction spends in the system** (seconds).

For example, at **200 RPS** with an average processing time of **250 ms** (0.25 seconds), the corresponding average concurrency is roughly:

\[
L = 200 \times 0.25 = 50\ \text{in-flight requests}
\]

If `W` increases to 1 second under higher load while RPS stays at 200, the average number of in-flight requests can rise to **200**. This puts pressure on connection pools, heap/direct memory, queues, and backends.

**Do not use Little's Law as an absolute predictor over short intervals, during sharp traffic swings, or when requests are being dropped/timing out.** It applies best to a system in a relatively steady state, using consistent measurement boundaries and completion definitions.

### Open-Loop vs. Closed-Loop Load

- **Closed-loop:** Each virtual user waits for a response before issuing the next request. When the backend slows down, offered RPS automatically drops; looking only at p95 might trick you into thinking the system handles load well.
- **Open-loop / arrival-rate:** The load generator tries to maintain the configured arrival rate even when responses slow down, within the tool's resource limits. It makes queue growth and saturation easier to spot if enough load-generation resources are provisioned.
- **Testing needs both:** closed-loop approximates user think time; arrival-rate lets you examine behavior at a fixed offered load.

**Always report both offered rate and achieved rate**; never report just "200 users" because 200 users does not mean 200 requests/s.

## 4. Client-Side Latency: TTFB vs. Total Time

A client can measure several milestones:

| Metric | Time span | Useful for |
|---|---|---|
| DNS lookup | Domain resolution when not cached | Diagnosing DNS |
| TCP connect | Establishing a new TCP connection | Network/connect latency |
| TLS handshake | Establishing TLS when a new connection is needed | Certificate/SNI/crypto cost |
| **TTFB** (*time to first byte*) | From request start to the first response byte per client/tool | Initial response latency |
| **TTLB / total time** | From start until the entire response is received | Complete download experience |
| Download duration | From first byte to last byte, if measurable | Network, proxy buffering, client bandwidth |
| End-to-end transaction | May include redirects, multiple requests, or workflows | Business user experience, not just one HTTP call |

**TTFB and total time are close for a 1 KB JSON payload, but can differ by minutes for a 2 GiB file, SSE, or streaming.** Do not apply the same latency SLO to a short JSON response and an intentionally long-lived stream.

### Inspecting Client Milestones with curl

~~~bash
curl -sS -o /dev/null \
  -w 'dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s pretransfer=%{time_pretransfer}s ttfb=%{time_starttransfer}s total=%{time_total}s code=%{http_code}\n' \
  'http://localhost:8080/api/catalog/items/42'
~~~

cURL's `time_*` fields are generally **cumulative timestamps from the start of the transfer**, not independent segments. For example, to estimate the time from connection establishment to the first byte, you must subtract the appropriate two milestones—**do not add all of the DNS/connect/TLS/TTFB/total values together**.

For plain `http://` without TLS, `time_appconnect` is usually meaningless or 0. With connection reuse, HTTP/2 multiplexing, or DNS caching, connection fields can differ from the first request. **A single curl command is not a P99 benchmark.**

## 5. What Do P50, P95, and P99 Measure?

Given a set of `N` completed latency observations sorted in ascending order, a **percentile p** describes the latency level at or below which roughly **p% of observations** fall according to the chosen quantile algorithm.

| Percentile | Practical interpretation | When to use |
|---|---|---|
| **P50** (median) | Roughly half of requests are faster, half are slower | Typical experience |
| **P90** | Roughly 90% of observations are below this level | Slow yet common |
| **P95** | Roughly 5% of requests are slower | Key tail metric for APIs |
| **P99** | Roughly 1% of requests are slower | Small but significant tail issues |
| **P99.9** | Roughly 0.1% of requests are slower | Large scale, requires many samples |

In a hypothetical run of **10,000 requests** with P99 = **800 ms**, roughly 100 observations in the slowest group may exceed the 800 ms region, depending on the quantile method and distribution. **Never explain P99 as "a request spends 99% of its time at 800 ms."**

### Why Averages Can Mislead

A route has 99 requests taking 20 ms and 1 request taking 5,000 ms:

\[
\overline{T} = \frac{99\times20 + 1\times5000}{100}=69.8\ \text{ms}
\]

The average is around **69.8 ms**, yet 1% of users have to wait **5 seconds**. If you increase retries in the Gateway, the average may improve when failures are recovered, while **P99 worsens** because some requests wait through additional backoff.

### Percentiles Need Context

Always include:

- Number of samples in the window;
- Success/error request ratio;
- Endpoint/route, HTTP method, and payload size;
- Measurement window (`1m`, `5m`, `1h`);
- Measurement source (client, Gateway, backend) and boundary;
- Algorithm: exact quantile from raw samples, histogram bucket estimate, or summary percentile.

**P99 with 30 requests per 5 minutes is usually too unstable for production optimization decisions.** When sample counts are low, inspect the count and trends over a longer window.

## 6. Never Add or Average Percentiles Across Hops

A serious mistake is doing this:

~~~text
P99(client→Gateway) = 30 ms
P99(Gateway)        = 200 ms
P99(backend)        = 300 ms

DO NOT conclude:
P99(end-to-end) = 30 + 200 + 300 = 530 ms
~~~

Each P99 can come from **different requests**. Moreover, the Gateway timer may already **include** the backend, so adding double-counts it. Similarly, P99 values from two Gateway instances cannot be added or averaged to find the cluster-wide P99.

### The Right Way to Decompose

1. Pick **the same request/trace**.
2. Measure start/end timestamps on **one timeline** and identify inclusive vs. exclusive spans.
3. Determine which segments are sequential and which overlap.
4. If you need end-to-end P99, compute it from **all end-to-end observations** or an aggregated histogram of the same type and unit.
5. If you need "P99 pool wait time," measure a dedicated **pool acquire** timer across actual acquire attempts rather than subtracting two percentiles.

### Timeline Example for *One* Request

~~~mermaid
gantt
    title Illustrative timeline of a single HTTP request
    dateFormat x
    axisFormat %L
    section Client
    Full request :a, 0, 270
    section Gateway
    HTTP server span :b, 12, 240
    section Outbound
    Client HTTP attempt span :c, 38, 204
    section Backend
    HTTP server span :d, 60, 190
~~~

The spans above **intentionally overlap**. From a 228 ms Gateway span and a 166 ms outbound span, only when you know the boundaries, clock accuracy, and execution structure can you estimate the time spent outside outbound. That is **not P95/P99 data**.

> **Rule:** Compute percentiles from **raw observations or histogram buckets of the same family**. Use **traces** to see the slow hop on *one request*, and **metrics** to see the latency distribution across *many requests*.

## 7. Dividing Measurement Hops in Gateway Server WebFlux

A practical boundary layout:

| Hop / measurement point | Start → end | Suitable tools | Pitfalls |
|---|---|---|---|
| Client → ingress | Request start → ingress receives | Load generator + ingress metrics | Unsynchronized clocks skew subtraction |
| Ingress | Receives request → forwards to Gateway | Reverse proxy access timings/traces | Ingress may buffer the body |
| Gateway HTTP server | Request received → response completed per server instrumentation | `http.server.requests`/server observations | May include handlers other than Gateway routes |
| Security/WebFilters | Entry → security decision | Tracing/low-cardinality custom timing | May reject before route metrics |
| Route matching | Before route selection → route selected | Custom instrumentation/trace if needed | Gateway does not have a dedicated matcher timer by default |
| Gateway filter chain | From wrapper before `chain.filter` to terminal signal | Custom `GlobalFilter` timer | Inclusive: may include outbound |
| HTTP client acquire | Acquiring a connection from the pool | Reactor Netty/client pool metrics | Not the same as TCP connect when pool reuses |
| DNS / connect / TLS | Creating a new connection | Client/Netty metrics & spans | Does not occur on connection reuse |
| Backend request | Backend receives → response per timer | Backend `http.server.requests` | May include DB/cache |
| Response to client | Backend bytes → final client bytes | Client total, ingress, Netty traces | Streaming/backpressure have a large impact |

**Do not assume every hop has a built-in meter in the Gateway.** Spring Boot, Reactor Netty, the HTTP client, the load balancer, and Micrometer Observation may enable different telemetry depending on version; complex phases like predicate evaluation may need custom instrumentation if your optimization goal truly requires it.

## 8. Separating Request Latency from HTTP Attempt Latency

A client request can follow different branches:

~~~mermaid
flowchart TD
    C["1 incoming request"] --> G["Security + route/filter"]
    G --> L{"RateLimiter?"}
    L -->|429| RL["Ends with 429, 0 outbound attempts"]
    L -->|Allowed| A1["Outbound attempt #1"]
    A1 --> R{"Result?"}
    R -->|503 and retried| W["Backoff"]
    W --> A2["Outbound attempt #2"]
    A2 --> OK["200 → client"]
    R -->|200| OK
    R -->|Circuit open/fallback| FB["Fallback response"]
~~~

- **Incoming count:** one client request.
- **Routed count:** usually one measurement at the Gateway route if it passes the instrumentation point, though you should verify your version.
- **Outbound attempts:** 0, 1, 2, or more.
- **User-perceived latency:** may include retry/backoff and response transfer.
- **Backend server duration:** measured by the backend **per attempt**; two backend attempts may belong to a single user request.

### Retry Amplification

A useful ratio to track:

\[
A = \frac{\text{outbound attempts/s}}{\text{incoming routed requests/s}}
\]

For a normal **one request → one outbound call** route, `A` is close to 1. When retries spike, `A` increases. However, for intentional aggregation/fan-out routes, `A` can exceed 1 even when healthy. Therefore, **tie policies and interpretation to each route**, rather than alerting on one global threshold for all APIs.

**An HTTP 503 from the backend does not automatically mean Reactor emits `onError`.** An HTTP client may receive a response with status 503 as a normal result; the Gateway Retry filter or client policy decides whether to make another attempt.

## 9. Actuator, Micrometer, and Prometheus: Preparing Measurement Data

First, you need a metrics source for the Gateway.

Example Gradle dependencies for a Gateway Server WebFlux application with a **compatible Spring Boot/Cloud BOM**:

~~~groovy
dependencies {
    // Starter name may vary across release trains.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

A **lab** configuration with application port 8080 and management port 9091:

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

**Security:** Separating the port does not make it private. In production, `/actuator/prometheus` must be restricted with network ACLs/ServiceMonitor permissions and appropriate authentication/TLS, and sensitive Actuator endpoints must not be exposed to the Internet. The `metrics` endpoint is useful in a lab but does not necessarily need to be open to everyone in production.

### Discovering Which Meters Are Actually Present

~~~bash
curl -sS 'http://127.0.0.1:9091/actuator/metrics'
curl -sS 'http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests'
curl -sS 'http://127.0.0.1:9091/actuator/prometheus' \
  | grep -E '^(spring_cloud_gateway_requests|http_server_requests)'
~~~

In Gateway Server WebFlux lines that include the **Gateway Metrics Filter**, a common timer is `spring.cloud.gateway.requests`, exported to Prometheus as series like `spring_cloud_gateway_requests_seconds_count` and `..._sum`. Common labels include `routeId`, `routeUri`, `outcome`, `status`, `httpStatusCode`, and `httpMethod`; a path tag may be optional.

**Do not copy queries and assume metric/label names are always identical.** Registry naming conventions, release trains, and how filters are enabled change; verify `/actuator/metrics` and raw `/actuator/prometheus` in your actual runtime. Some metrics only appear after the first instrumented request.

### HTTP Server Meter vs. Gateway Route Meter

- `http.server.requests` generally measures requests at the web server/application HTTP layer.
- `spring.cloud.gateway.requests` generally measures outcomes at the **Gateway route instrumentation point**.
- A request returning 401 before route matching may **not** increment the Gateway route count.
- A request to `/actuator/health` may be measured by the separate management web server, **not** a Gateway route.
- Requests blocked by ingress/WAF cannot appear in in-process Gateway meters.

Do not swap these two meters interchangeably if you want to measure **successes or pre-routing rejections**.

## 10. Enabling Histograms for Aggregatable P95/P99

The `spring.cloud.gateway.requests` timer may export count/sum **without histogram buckets**. From count + sum you can only calculate the **average**, not accurately derive P95/P99.

Example Spring Boot Micrometer distribution configuration for **a specific timer**:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        "[spring.cloud.gateway.requests]": true
~~~

Square brackets on the map key preserve the dotted meter name when the Spring Boot binder processes map properties; verify that the configuration takes effect in your version.

Check the raw exposition:

~~~bash
curl -sS 'http://127.0.0.1:9091/actuator/prometheus' \
  | grep '^spring_cloud_gateway_requests_seconds_bucket'
~~~

If there is no `_bucket`, check:

1. Has the timer been recorded at least once?
2. Are the meter name and namespace right?
3. Was the distribution histogram enabled before the meter was registered?
4. Does the registry/Prometheus exporter emit buckets?
5. Is the app using Gateway Server WebFlux or another variant?

### Timer Metrics and Units

| Example Prometheus series | Meaning | Unit |
|---|---|---|
| `..._seconds_count` | Number of measurements | Count |
| `..._seconds_sum` | Total duration | Seconds |
| `..._seconds_bucket{le="0.25"}` | Number of measurements ≤ 250 ms in the cumulative bucket | Count |
| `..._seconds_max` if exported | Time-window max depending on meter | Seconds, **not P99** |

Buckets can have many different `le` values; the examples below **do not assume** a `0.25` bucket must exist unless explicitly stated.

**Histograms multiply the number of time series by label combinations × buckets.** Do not enable histograms indiscriminately across all routes/URIs/paths with unbounded cardinality.

## 11. Scraping All Gateway Instances with Prometheus

Example Prometheus config for a **lab environment on the same host/network namespace**:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: gateway-edge
    metrics_path: /actuator/prometheus
    scheme: http
    scrape_timeout: 5s
    static_configs:
      - targets:
          - '127.0.0.1:9091'
        labels:
          environment: lab
~~~

If the Gateway runs in Docker/Kubernetes, Prometheus's `127.0.0.1` is **the Prometheus container itself**. Use appropriate DNS/service discovery to scrape **each Gateway instance individually**, not just a load-balanced Service that can hit a different pod on each scrape and make counters hard to aggregate.

### Always Start by Checking Scrape Health

~~~promql
up{job="gateway-edge"}
~~~

- `up=1`: target was scraped successfully on the last attempt.
- `up=0`: target is present but the scrape failed.
- No `up` series: target may not be discovered yet or was dropped from scraping; **does not mean healthy**.

A performance dashboard without an `up` panel can easily mistake **missing data** for **0 RPS or zero errors**.

## 12. PromQL: Measuring RPS and Throughput by Route

The queries below assume the live runtime exports:

~~~text
spring_cloud_gateway_requests_seconds_count{
  job="gateway-edge",
  routeId="catalog-read",
  httpStatusCode="200"
}
~~~

Update metric and label names if your environment's exposition differs from the example.

### Total Gateway Routed RPS

~~~promql
sum(
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

`rate(counter[5m])` estimates the per-second rate of increase and handles counter resets (such as restarts) better than subtracting raw counters.

### RPS by Route ID

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

### RPS by Method and Route

~~~promql
sum by (routeId, httpMethod) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

### Estimated Requests Over One Hour

~~~promql
sum by (routeId) (
  increase(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[1h])
)
~~~

`increase` can return non-integer values due to window interpolation; it is not an exact per-request event log.

### Splitting 2xx, 4xx, and 5xx

~~~promql
sum by (routeId, httpStatusCode) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge",
    httpStatusCode=~"[245].."
  }[5m])
)
~~~

If you want **business-level successful RPS**, do not treat every 2xx as "success": a fallback might return HTTP 200 with stale data, or an API might return 202 before work finishes. Instrument a separate business outcome when needed, using bounded labels.

## 13. PromQL: Average, P50, P95, and P99 Latency

### Average Route Latency

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_sum{
    job="gateway-edge"
  }[5m])
)
/
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

The result is in **seconds**. Do not equate this with client TTFB or backend processing time.

### P50 per Route

~~~promql
histogram_quantile(
  0.50,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

### P95 per Route

~~~promql
histogram_quantile(
  0.95,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

### P99 per Route

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

**Keep `le` in `sum by (le, routeId)`.** With classic Prometheus histograms, `histogram_quantile` needs the upper bound of each bucket. If you want **cluster-wide** P99, use `sum by (le)`, *provided the histogram family, units, and bucket layout match*.

### Why Not Average Each Node's P99?

Two nodes can receive different request volumes and latency distributions. Averaging `P99_A` and `P99_B` **does not produce the cluster-wide P99**. The right approach is to **sum bucket counts first and then call `histogram_quantile`**, rather than aggregating quantile results.

**Histogram P99 is an estimate** based on bucket boundaries. With low traffic or coarse buckets, it can diverge noticeably from exact percentiles computed from raw observations. If your SLO is 250 ms, make sure you have sufficient bucket resolution around that mark.

## 14. Measuring Latency SLOs with Histograms: Sometimes More Useful Than P99

P99 reveals tail latency, but many systems want to answer: **What percentage of requests complete under 300 ms?**

If the histogram has a **`le="0.3"`** bucket, the fraction of requests ≤ 300 ms per route is:

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_bucket{
    job="gateway-edge", le="0.3"
  }[5m])
)
/
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

This is a **ratio from 0 to 1**, not a percentage until multiplied by 100. If there is no `0.3` bucket, the expression will not give the intended result; **do not invent `le="0.3"` in a query** and assume the Registry measured that bucket. Configure Micrometer histogram/SLO boundaries appropriately for your version.

### A Proper Latency SLI Must Choose Its Denominator

Should a request that returns 503 in 5 ms count as "fast"?

- For an **availability/error SLO**, it is an error.
- For a **latency SLO**, you may choose only successful requests or all attempts, but you must state the definition explicitly.
- For a **user journey**, both status and latency may jointly define success.

One example definition: **"99% of successful requests on route catalog-read complete under 300 ms, measured from Gateway server receipt to response completion."** Alongside this, maintain a **separate error-rate SLO** so the system cannot satisfy its latency SLO by failing fast.

## 15. Comparing Hops with Distributed Tracing

Aggregated metrics tell you which route has high P99; **a trace of one slow request** helps pinpoint the slow hop. With Spring Boot/Micrometer Tracing + OpenTelemetry or an equivalent tracing system, you can collect spans such as:

~~~text
traceId = 77... (illustrative)
└── edge-gateway.server           0 - 270 ms
    ├── authentication                2 - 18 ms (if instrumented)
    ├── route-and-filter             18 - 250 ms (may include outbound)
    │   └── http.client/orders       36 - 235 ms
    │       └── orders-service.http  55 - 210 ms
    │           └── database.query   80 - 190 ms
    └── response-write               250 - 270 ms (if instrumented)
~~~

**Spans are nested/overlapping**—do not add all durations together. A 199 ms client span may include a 155 ms backend server span; a 110 ms database query lies inside the backend span.

### Which Differences Are Meaningful?

For **a single trace**, when time boundaries align:

- The Gateway may spend time in security/route/filters before outbound.
- A long HTTP client span may include queue/pool acquire, DNS, connect, TLS, request upload, backend wait, and response download.
- A backend server span may include DB/cache calls.
- The gap between client wait and backend server processing may come from network/pool/serialization, **but cannot be broken down further without instrumentation**.

To find the **P99 of the pool acquire hop**, you need a **metric/histogram for acquire duration** or enough span data for proper statistics—**never subtract P99(backend) from P99(client)**.

### Trace Propagation Through the Gateway

- Use standard propagation, commonly `traceparent`/`tracestate`, across systems that support it.
- Both Gateway and backend must agree on propagators to share the same trace ID.
- Sampling typically does not store **every request**: a few slow traces are clues, not a full population distribution.
- Never put JWTs, session IDs, API keys, or sensitive raw queries into span attributes.
- Clock skew and instrumentation overhead should be checked when trying to analyze very short segments.

**Metrics give distributions, tracing gives the execution path, and logs give error details**—these three tools complement one another.

## 16. Measuring Filter Chain Timing Properly in WebFlux

When you need a custom measurement, you can place a **`GlobalFilter`** around part of the Gateway filter chain to capture elapsed time. Example using a Micrometer Timer with bounded tags:

~~~java
package example.gateway.performance;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class GatewayChainTimingFilter
        implements GlobalFilter, Ordered {

    private final MeterRegistry meterRegistry;

    public GatewayChainTimingFilter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Override
    public int getOrder() {
        return -1000; // Illustrative position; verify effective filter ordering.
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        return Mono.defer(() -> {
            long startNanos = System.nanoTime();

            return chain.filter(exchange)
                .doFinally(signal -> {
                    long elapsedNanos = System.nanoTime() - startNanos;
                    meterRegistry.timer(
                        "edge.gateway.wrapped.chain.duration",
                        "terminal", signal.name())
                        .record(elapsedNanos, TimeUnit.NANOSECONDS);
                });
        });
    }
}
~~~

### Interpreting This Custom Metric Correctly

- `Mono.defer(...)` starts timing at **subscription**, not prematurely when the filter graph is assembled.
- `doFinally` runs on **complete/error/cancel** and records elapsed time, so `terminal` only has a finite set of values.
- This timer measures the **entire downstream filter chain**, which can include routing, backend wait, and response composition. It **does not** measure "only the custom filter's CPU cost."
- `getOrder()=-1000` is an example. GlobalFilters and route-specific filters are sorted by `Ordered`; there is no guarantee this timer wraps all filters if another filter runs outside it.
- Requests rejected by Spring Security **before the Gateway filter chain** will not appear in this timer.
- A request short-circuited by an inner filter can complete **without going outbound**; do not treat this timer as backend latency.
- `doFinally` can run after the terminal signal flows downstream; when testing counters/timers, synchronize appropriately instead of asserting with an immediate read race.

**Never add raw URLs, principals, IPs, JWTs, or request IDs as Timer labels.** If you need per-route breakdown, prefer the Gateway route timer with normalized `routeId`; custom timers with dynamic route IDs need a cardinality policy.

### If You Only Want to Measure *One* Filter

A filter with:

~~~java
return chain.filter(exchange)
    .doOnSuccess(ignored -> observeSuccess());
~~~

measuring from before `chain.filter(...)` until after the chain completes will include **all processing inside the chain**, not just the duration of `observeSuccess()` or of that filter.

To measure **self-cost**, wrap the narrow logic itself with a separate timer, or instrument specific operations (parsing a token, looking up a Redis key, transforming headers) while accounting properly for async execution. Never compute "Gateway overhead = total timer − backend P95," because **subtracting P95s is statistically invalid**.

## 17. Connection Pool, DNS, TLS, and Load Balancing: Commonly Missed Hops

A `lb://orders-service` route may resolve quickly, yet the outbound call is still slow because:

1. Service Discovery/LoadBalancer is slow to refresh instances.
2. The HTTP connection pool has no idle connections left, forcing requests to wait on acquire.
3. Creating a new TCP connection takes time.
4. DNS is slow or failing.
5. TLS handshake/certificate validation/SNI runs into issues.
6. A newly scaled-up backend is not warmed up yet.
7. The backend accepts the request quickly but responds slowly due to DB/cache.

### Measuring with the Right Metrics

| Suspect area | Observation needed | Typical symptom |
|---|---|---|
| Pool acquire | Pending acquire count/duration | RPS may not drop yet, P99 rises due to queueing |
| Connect | New connection time/error | Slow connect, network packet loss |
| TLS | Handshake time/failures | P99 spikes on new connections, certificate issues |
| DNS | Resolution latency/errors | Error spikes when changing hostnames/instances |
| Backend | HTTP server timer + service spans | Backend P95 rises with load |
| LoadBalancer | Instance distribution, selected service ID | One hot or failing instance |
| Ingress | Proxy upstream timings | Gateway is not the bottleneck |

Reactor Netty metric names vary by version and how instrumentation is enabled; **do not guess meter names and build blank panels**. Inspect `/actuator/metrics` and raw exposition first. In a runtime with tracing, inspect one trace that **reuses a connection** and one trace that **opens a new connection** to see the difference in connect/TLS cost.

### HTTP Keep-Alive and HTTP/2

A benchmark that opens a new connection on every request measures heavy TCP/TLS overhead, unlike browser/mobile/backend workloads that use keep-alive. HTTP/2 multiplexing can alter connection counts and queueing behavior, so always report:

- HTTP protocol version;
- Connection reuse policy;
- Max connections / pending acquire settings;
- TLS on/off, endpoint/certificate;
- Load balancer and number of backend instances;
- Client concurrency.

**Never compare P99 across two environments with different TLS/keep-alive/protocol settings and blame Gateway filters.**

## 18. Measuring Payloads: TTFB and TTLB for Uploads, Downloads, SSE, and WebSockets

A small JSON GET endpoint can use generic `request duration`. However, certain traffic types need separate SLIs.

| Traffic type | Useful metrics | Misleading metrics |
|---|---|---|
| Small JSON GET | RPS, total latency P95/P99, error ratio | Average only |
| Small JSON POST | Total latency, successful RPS, write conflicts | Treating retry count as user requests |
| Large file upload | Bytes/s, time-to-acknowledge, total upload duration, failure/cancel rate | Shared P99 with JSON GET |
| Large file download | TTFB, TTLB, bytes/s, checksums, incomplete downloads | Treating TTFB as the entire download |
| SSE | Time to first event, inter-event gap, reconnects, active streams | Treating total connection lifetime as latency |
| WebSocket | Handshake duration, message RTT, active connections, frame errors | Treating socket open time as HTTP request P99 |
| gRPC streaming | Per-message/stream SLIs per protocol | Default HTTP/1.1 request rate |

**Body filters** such as `CacheRequestBody`, `ModifyRequestBody`, or `ModifyResponseBody` can force stream buffering. When that happens:

- TTFB may rise even if the backend emitted chunks early.
- Heap/direct memory can grow with body size × concurrency.
- A route-level timer may wait for the entire stream, making it non-comparable to JSON requests.
- Retrying a request body may require buffering or replay and increase backend load.

Do not blindly raise `max-in-memory-size` to get higher RPS; prefer streaming pass-through whenever the gateway does not need to read the entire body.

## 19. Designing Reproducible Load Tests: More Than Running a Few curl Commands

A rigorous performance test must define the **workload**, **environment**, **completion criteria**, and **result verification method**.

### Pre-Run Checklist

| Attribute | Must fix / record |
|---|---|
| Code & config | Git revision, Gateway/filter configuration, Spring Boot/Cloud BOM |
| Runtime | Java version, container CPU/memory limits, JVM flags |
| Infrastructure | Gateway/ingress/backend instances, resource requests/limits |
| Protocol | HTTP/1.1 or HTTP/2, TLS, keep-alive, connection pooling |
| Route mix | GET/POST ratio, path patterns, authenticated/anonymous |
| Payload | Body/response sizes, gzip, cacheability |
| Backend behavior | CPU/DB delay, error injection, cache hit ratio |
| Arrival pattern | Constant rate, ramp, burst, closed-loop |
| Measurement | Warm-up, steady-state window, scrape frequency |
| Success | Response status, schema/checksum, business side effects |
| Stop rules | Error ratio, memory pressure, downstream health, production isolation |

**Only generate load in authorized, bounded environments.** Do not run benchmarks that blast heavy traffic, retry storms, or TLS handshake stress into production without a capacity and rollback plan.

### Warm-Up and Steady State

In the JVM, warm-up affects JIT compilation, class loading, connection pools, TLS sessions, and caches. A basic workflow:

1. Deploy Gateway/backend and record versions.
2. Warm up with light load matching the request mix.
3. Run a **baseline** at a fixed offered rate.
4. Hold for several minutes—long enough for sufficient samples/scrapes to estimate P95/P99.
5. Step up offered rate in controlled increments.
6. Observe throughput, latency, error ratio, concurrency, pool queues, and CPU.
7. Stop when exceeding safety limits and record the saturation point.
8. Repeat runs multiple times; avoid treating a single run as ground truth.

## 20. k6 Example: constant-arrival-rate and Client Percentiles

A load generator like **k6** provides the `constant-arrival-rate` executor to attempt starting a fixed number of iterations per second instead of waiting for a previous user to finish before sending the next request.

Example **lab script** `gateway-performance.js`:

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const baseUrl = __ENV.GATEWAY_URL || 'http://localhost:8080';
const success = new Rate('catalog_success');

export const options = {
  scenarios: {
    catalog_read: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '3m',
      preAllocatedVUs: 100,
      maxVUs: 300,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    catalog_success: ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(
    baseUrl + '/api/catalog/items/42',
    { tags: { scenario_name: 'catalog_read' } }
  );

  const valid = check(response, {
    'HTTP 200': (r) => r.status === 200,
    'response has item': (r) => r.body.includes('42'),
  });

  success.add(valid);
}
~~~

Targets like `100 req/s`, `P95 < 500 ms`, `P99 < 1,000 ms`, and `<1%` error rate are **lab thresholds**, not universal standards. In this script, each iteration sends one HTTP request. If you edit a script to send multiple requests per iteration, **iteration rate no longer equals HTTP RPS**.

### Reading the k6 Report Correctly

| Common k6 metric | How to interpret |
|---|---|
| `http_reqs` | Total HTTP requests and rate |
| `http_req_duration` | Send + wait + receive duration per k6 semantics; does not equal full DNS/connect/TLS |
| `http_req_waiting` | Time waiting for the first response byte (close to TTFB within tool scope) |
| `http_req_connecting` | TCP connection setup time |
| `http_req_tls_handshaking` | TLS handshake |
| `http_req_blocked` | Time a request was blocked before sending began |
| `http_req_failed` | Ratio of requests k6 marks failed per expected response policy |
| `dropped_iterations` | Iterations that could not start on schedule |
| `vus` / `vus_max` | Active/available virtual users |

**You must check `dropped_iterations` and actual `http_reqs`.** If the script tries to send 100 req/s but the load generator runs out of CPU/VUs and drops many iterations, the Gateway **probably never received 100 req/s**. Also monitor the health of the load-generator machine, not only the Gateway's CPU.

### Do Not Misplace `sleep`

With `constant-arrival-rate`, you do not need `sleep(1)` at the end of an iteration just to achieve 1 RPS/user; that changes how long a VU is held and can starve VUs. Consult k6's load-model guide and verify actual throughput.

### Running in the Lab

~~~bash
k6 run -e GATEWAY_URL=http://localhost:8080 gateway-performance.js
~~~

This command is for learners to practice in a lab environment—**do not execute in STEP 4**. If using a test token, pass it via secrets/env vars per policy; never commit credentials into scripts or send real PII payloads to dashboards.

## 21. Detecting Coordinated Omission and Load-Generator Bottlenecks

**Coordinated omission** occurs when a measurement system only records latencies of requests that were actually sent, while **ignoring requests that were scheduled to arrive but were delayed**. In a closed-loop workload, when the backend stalls, the client stops sending the next request, so the histogram misses the wait times users would experience under an independent arrival model.

### Example

Suppose the system is expected to handle 100 requests/s, and the backend stalls once for 5 seconds:

- A closed-loop client just waits on the current request, **reducing offered load**;
- Because each VU sends the next request only after receiving a response, few samples are recorded during the stall;
- Measured P99 can look much lower than what would happen if arrivals continued on schedule.

**The solution is not a "magic" tool**, but rather:

1. Define an arrival model matching the real workload.
2. Use constant-arrival-rate when evaluating SLO compliance at a fixed arrival rate.
3. Track `dropped_iterations`, generator CPU, network throughput, and target achieved RPS.
4. Provision enough VUs/connections so requests start on time.
5. Record queueing and timeouts, including requests dropped or rejected by policy.
6. If using HDRHistogram or a tool with corrected latency, understand its exact assumptions and correction method.

**Never compare two P99s when one test dropped load and the other met the offered rate.**

## 22. Testing Multiple Load Levels to Find the Saturation Knee

A load test should answer: **at what offered RPS do P95/P99 start rising sharply while successful throughput fails to scale proportionally?**

Example *hypothetical* data for a JSON API:

| Offered RPS | Successful RPS | P50 (ms) | P95 (ms) | P99 (ms) | 5xx | Notes |
|---:|---:|---:|---:|---:|---:|---|
| 50 | 50 | 25 | 60 | 100 | 0% | Plenty of headroom |
| 100 | 100 | 30 | 75 | 140 | 0% | Stable |
| 200 | 198 | 45 | 150 | 350 | 0.5% | Tail begins rising |
| 300 | 275 | 100 | 500 | 1,800 | 5% | Queueing/throttling |
| 400 | 285 | 180 | 1,500 | 5,000 | 18% | Overloaded |

This data is **not a real Spring Cloud Gateway benchmark**. It illustrates the pattern where **throughput nears a ceiling while latency climbs steeply**. If you only looked at peak throughput, you might call 400 RPS "capacity" even though only 285 RPS succeed and P99 hits 5 seconds.

### Determining Operating Load

SLO-compliant capacity is not necessarily maximum throughput. A sound target must satisfy **all of these simultaneously**:

- Sufficient successful RPS.
- Error ratio within budget.
- P95/P99 below target.
- No sustained queueing or connection-pool saturation.
- Headroom in JVM CPU/memory, Netty direct memory, and backend DB pools.
- Ability to recover if one instance is lost or a burst arrives.

**Judge by useful work completed on time**, not by the total number of requests to which the server managed to return some status code.

## 23. Benchmarking Route Predicates, Filters, and Body Transformations

In a Gateway with many routes/filters, you may suspect a custom filter is adding latency. You need a **controlled A/B design**.

### Single-Change Experiments

1. **Baseline:** Route `Path=/api/catalog/**` → echo backend, minimal filters.
2. **Route config:** Add a simple `Header`/`Method` predicate, keeping the workload identical.
3. **Header filter:** Add `SetRequestHeader`, without touching the body.
4. **Security:** Enable JWT verification with a well-defined cache/JWK policy.
5. **Rate limiter:** Enable the Redis limiter with a quota that **does not block test traffic** so you measure the allowed-path overhead.
6. **Body transform:** Test only with small bounded JSON; compare heap/TTFB/P99.
7. **Retries:** Inject a controlled 503 rate at the backend, measure outbound attempts.
8. **Circuit breaker:** Introduce controlled slow backend behavior, measure fallback/error distribution.

**Change only one factor at a time**, or use an experimental design with clear controls. Changing CPU limits, JVM flags, backend latency, cache TTL, and filter order all at once makes it impossible to attribute a P99 shift to any single factor.

### Separating Overhead from Backend Time

- If Gateway P99 rises alongside backend server P99, check downstream/DB first.
- If backend P99 stays flat while Gateway HTTP client P99 rises, check the connection pool, TLS/DNS, or network.
- If the HTTP client timer stays steady while Gateway ingress P99 rises, check Security, routing, body filters, or response writing.
- If client P99 rises while Gateway ingress P99 stays steady, check ingress, CDN, network, and client download.

These are **localization heuristics**, not exact percentile subtraction; confirm using traces and instrumentation on the same request.

## 24. How Security, RateLimiter, Retry, Fallback, and Cache Skew Comparisons

A benchmark must separate each execution branch.

| Mechanism | Effect on throughput/latency | Must measure alongside |
|---|---|---|
| **Spring Security** | JWT/JWK verification, permission checks, 401/403 short-circuit | % authenticated, auth failures, security timer if present |
| **RequestRateLimiter** | Early 429s can lower average latency | Accepted vs. rejected RPS, limiter policy |
| **Retry** | Increases successful responses but stretches P99 and raises backend attempts | Retry count, backoff time, downstream attempts |
| **CircuitBreaker** | Open circuit returns errors/fallbacks quickly | State, fallback rate, business success |
| **LocalResponseCache** | Cache hits are fast and skip the backend | Hit/miss ratio, stale data correctness |
| **LoadBalancer** | Distributes across instances with varying latencies | Selected instance, per-backend metrics |
| **TLS/mTLS** | Handshake, encryption cost, certificate validation | New vs. reused connections, TLS errors |
| **Body filters** | Buffering/transforming increases memory and delays TTFB | Payload size, heap/direct memory, GC |
| **CORS preflight** | Browsers may send OPTIONS before the main request | Request types and end-user journey |
| **Fallback headers** | May forward error metadata to fallback | Sensitive data protection |

### Do Not "Optimize" by Failing Fast

Suppose instead of calling a slow backend, the Gateway trips a breaker and returns 503 immediately. P99 might drop from 1,000 ms to 20 ms, while **availability drops**. Dashboards must show **both latency and service outcomes**.

Similarly, a Redis rate limiter returning 429 very quickly can raise completed RPS while reducing successful RPS. An "optimization" is only acceptable when **speed, success, and security SLOs** are all met.

## 25. Dashboards: Reading Root Causes Instead of Just Looking at Charts

A performance dashboard should have these rows:

| Row | Panels | Answers the question |
|---|---|---|
| 1. Data health | `up` per Gateway instance, scrape freshness | Are metrics still being collected? |
| 2. Traffic | Incoming vs. routed RPS, successful vs. 4xx/429/5xx | Where is traffic going? |
| 3. Latency | P50/P95/P99 per route + histogram count | Which route has rising tail latency? |
| 4. Downstream | HTTP client attempts, latency, pool pending, connection errors | Is the Gateway waiting on the network/backend? |
| 5. Backend | Server P95/P99, DB spans, cache/DB pool | Is the backend slow at processing or queueing? |
| 6. Saturation | CPU, heap/direct memory, GC, threads/event-loop, FDs, connections | Is the system nearing overload? |
| 7. Resilience | Retry amplification, breaker state/fallback, 429 | Are errors being masked or load amplified? |
| 8. Deploy | Version/revision, route change markers | After which deploy did the issue start? |

### Suggested Grafana Variables

- `environment`, `application`, `instance`;
- `routeId`, `httpMethod`;
- A standard time range such as 5m/15m when comparing trends;
- Links to logs/traces matching **route ID, time range, and trace ID** (never make trace ID a metric label).

**Do not display "P99 = 0" when there are no histogram samples.** Use a **No data / No traffic** state while keeping the `up` panel visible to distinguish zero traffic from a broken exporter.

### Alerts Need a Traffic Guard

For example, **route-level P99 > 1 second** only makes sense when there are enough requests in the window:

~~~promql
(
  histogram_quantile(
    0.99,
    sum by (le, routeId) (
      rate(spring_cloud_gateway_requests_seconds_bucket{
        job="gateway-edge"
      }[5m])
    )
  ) > 1
)
and on (routeId)
(
  sum by (routeId) (
    rate(spring_cloud_gateway_requests_seconds_count{
      job="gateway-edge"
    }[5m])
  ) > 5
)
~~~

The **1 second** and **5 RPS** thresholds here are for learning only. Production needs a `for` duration, per-route SLOs, alert ownership, and runbooks; do not share the same threshold across large uploads, WebSockets, or SSE.

## 26. Hop-by-Hop Lab: From Client to Gateway and Backend

### Assumed Environment

- Gateway Server WebFlux: `http://localhost:8080`.
- Catalog backend: `http://localhost:9090`.
- Gateway Actuator: `http://127.0.0.1:9091` (lab only).
- Prometheus job `gateway-edge` scraping the Gateway (one or more instances).
- If available, the backend also exports `http.server.requests` and has tracing enabled.
- Separate load-generator host or sufficient local resources; no sensitive data.

Lab route (using the older namespace from corresponding Gateway releases):

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

A `GET /api/catalog/items/42` request is forwarded as `GET /catalog/items/42`. If your release train uses the `spring.cloud.gateway.server.webflux.routes` namespace, **adapt the configuration to your version**—do not copy both namespaces and create duplicate routes.

### Step 1 — Baseline Direct Backend vs. Through Gateway

~~~bash
# Call backend directly (control):
curl -sS -o /dev/null \
  -w 'backend code=%{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  'http://localhost:9090/catalog/items/42'

# Call through Gateway:
curl -sS -o /dev/null \
  -w 'gateway code=%{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  'http://localhost:8080/api/catalog/items/42'
~~~

**Do not subtract two single curl results and declare "Gateway overhead"**: connections, backend caches, network paths, and JVM state can differ. Use multiple samples, equivalent workloads, and tracing/server/client instrumentation to attribute latency.

### Step 2 — Verify Meter Count/Sum/Buckets

~~~bash
curl -sS 'http://127.0.0.1:9091/actuator/metrics/spring.cloud.gateway.requests'

curl -sS 'http://127.0.0.1:9091/actuator/prometheus' \
  | grep '^spring_cloud_gateway_requests_seconds'
~~~

If there is no `_bucket`, fix the histogram setup before building P95/P99 queries. If labels do not include `routeId`, check the actual tag names in your Gateway version.

### Step 3 — Run a Test at a Fixed Load Level

~~~bash
k6 run -e GATEWAY_URL=http://localhost:8080 gateway-performance.js
~~~

Observe **achieved RPS, failed/dropped iterations, and P95/P99 from k6**. Record the offered rate, concurrency, payload, backend state, and container limits so the test is reproducible.

### Step 4 — Compare Prometheus and k6 at Proper Boundaries

In Prometheus:

~~~promql
sum by (routeId) (
  rate(spring_cloud_gateway_requests_seconds_count{
    job="gateway-edge"
  }[5m])
)
~~~

~~~promql
histogram_quantile(
  0.99,
  sum by (le, routeId) (
    rate(spring_cloud_gateway_requests_seconds_bucket{
      job="gateway-edge"
    }[5m])
  )
)
~~~

**Do not expect the two P99s to match identically.** k6 measures client-side `http_req_duration` (not identical to a server-side timer); Prometheus uses histogram estimates with different scrape/window boundaries; latency may also include network/ingress overhead. First, compare **trends** and **definitions**.

### Step 5 — Inject Controlled Downstream Delay and Retries

Configure the **lab** backend to raise delay from 30 ms to 150 ms on a defined percentage of requests. If Retry is enabled, intentionally return 503 for some calls to observe:

- Backend HTTP server P95/P99;
- Gateway route P95/P99;
- Outbound attempts/s;
- Retry backoff and total request duration;
- Client success/error counts.

**Never induce mass 503s or timeouts in production to measure.**

### Step 6 — Compare With and Without a Body Filter

On a small size-bounded JSON endpoint, measure P99 and memory with a body-reading filter turned on vs. off. Check TTFB/total and verify whether the filter buffered the full body. Do not feed multi-GiB files into `ModifyRequestBody(String.class, ...)` just to prove it consumes RAM.

### Step 7 — Conclude from Evidence

Record a results table:

| Variant | Achieved successful RPS | Client P95 | Client P99 | Gateway P99 | Backend P99 | 5xx/429 | Notes |
|---|---:|---:|---:|---:|---:|---|---|
| Baseline | Measured | Measured | Measured | Measured | Measured | Measured | No body transform |
| Header filter | Measured | Measured | Measured | Measured | Measured | Measured | Same workload |
| JWT auth | Measured | Measured | Measured | Measured | Measured | Measured | Same token policy |
| Redis limiter | Measured | Measured | Measured | Measured | Measured | Measured | 429 counted separately |
| Retry enabled | Measured | Measured | Measured | Measured | Measured | Measured | Attempts/s counted separately |

**Do not fill predicted numbers into the table as real results.** If backend/outbound are not instrumented yet, record **Not instrumented** instead of 0 ms.

## 27. Troubleshooting: Performance Symptoms → Hops to Investigate

| Symptom | Hypothesis to check | Signals / verification steps |
|---|---|---|
| Client P99 rises while Gateway P99 is steady | Ingress, network, TLS, client download | Ingress upstream timings, curl, client tracer |
| Gateway P99 rises, backend P99 is steady | Security/filters, pool acquire, LB/network | Gateway tracing + HTTP client/pool metrics |
| Gateway and backend P99 both rise | Backend/DB or shared resources | Backend traces, DB pool, CPU/GC |
| P99 jumps sharply after an RPS threshold | Queueing/saturation | Inflight, pending acquire, CPU, latency vs. offered RPS |
| Completed RPS rises while successful RPS drops | Fast 429/5xx | Response status mix, error SLO |
| 503s drop, P99 rises after enabling Retry | Retries recover errors but add backoff/attempts | Downstream attempts, retry count, deadlines |
| P99 drops unexpectedly after breaker opens | Fast 503/fallback masking an outage | Breaker state/fallback rate/business outcome |
| Cache lowers backend RPS | High cache hit rate **or** blocked requests | Hit/miss metrics and status mix |
| Upload P99 much higher than JSON | TTLB depends on size/bandwidth | TTFB, bytes/s, stream duration |
| SSE P99 looks "infinite" | Meter measures stream lifetime | Measure time to first event/inter-event gap instead |
| One Gateway node is slower | CPU throttling, JDK/config/deploy drift | Per-instance CPU, P99, version |
| Pool pending acquire rises | Too few idle connections/slow backend | Netty pool metrics, attempts, retries |
| TLS latency only high on first request | Handshake/connection reuse | Compare new vs. reused connections |
| k6 P99 looks low despite backend stall | Closed-loop/coordinated omission, dropped load | Arrival model, dropped_iterations, offered/achieved |
| Prometheus P99 is empty | Histogram not enabled/wrong labels | Raw `_bucket`, `up`, `le` query |
| Route P99 computed by averaging pod P99s | Invalid percentile aggregation | Sum bucket counts then histogram_quantile |
| Prometheus RAM grows | Raw path/user ID tag, too many buckets | Cardinality audit and series budget |
| Custom timer is faster than reality | Placed after security/routing or before completion | Filter order, start/end boundaries |
| Metrics missing 401/403 requests | Security short-circuits before route meter | Compare `http.server.requests` and access logs |
| Status 200 despite backend failure | Fallback returned 200 | Breaker/fallback instrumentation |

### Six-Step Investigation Process

1. **Is the data trustworthy?** Check `up`, scrape latency, sample count, and histogram buckets.
2. **Is it the same workload?** Compare offered/achieved RPS, route mix, cache/TLS/keep-alive, and error rate.
3. **Is the client or Gateway slow?** Compare client TTFB/TTLB with the Gateway HTTP server timer.
4. **Is the Gateway or outbound/backend slow?** Compare the Gateway route timer with HTTP client and backend timers; inspect concrete traces.
5. **Which queue is growing?** Connection pool pending, CPU throttling, event loop, Redis, DB pool.
6. **Which change caused it?** Check deploys/revisions, predicates/filters, retry/breaker/limiter, and run a controlled A/B rollback.

Do not jump straight to "increase thread pool" or "increase timeout" before knowing **the actual load, which queue is filling, and which latency type is affected**.

## 28. Statistical and Engineering Mistakes to Avoid

| Mistake | Why it is wrong | Right practice |
|---|---|---|
| Reporting only average latency | Hides tail latency | P50/P95/P99 + sample count/error mix |
| Adding P99s across hops | Quantiles are not additive; spans overlap | Trace per request and separate histograms |
| Averaging P99s across pods | Does not preserve the combined distribution | Sum histogram buckets before computing quantile |
| Treating `_max` as P99 | Max differs from quantiles; has time-window semantics | `histogram_quantile` from buckets |
| Computing P99 from count/sum | Only yields the average | Enable histograms or collect proper raw samples |
| Benchmarking small GETs and extrapolating to uploads/video | Workloads differ in size/stream lifetime | Separate SLOs and benchmarks per endpoint class |
| Judging capacity by total RPS | 429/5xx can inflate apparent RPS | Successful RPS + error/latency SLO |
| Ignoring offered vs. achieved RPS | Load generator may drop requests | Monitor generator health/dropped iterations |
| Running only a single cURL | Insufficient for P95/P99 | Repeat samples over steady-state windows |
| Comparing non-TLS HTTP/1.1 against TLS HTTP/2 | Connection/handshake behavior differs | Hold protocol/keep-alive/TLS constant |
| Using raw `Path` as a label | Cardinality explosion/PII | Stable route ID/path template |
| Including backend in a filter timer and calling it filter CPU | Inclusive boundary | Instrument a narrow operation |
| Not measuring backend attempts | Retries hide true load | Counter per attempt/hop |
| Treating missed scrapes as 0 requests | Missing data differs from zero traffic | `up` + no-data states |
| Using p99 from too few samples | Noisy/low confidence | Display count and use an adequate window |
| Increasing timeouts to cut errors | Holds connections/queues longer, can worsen p99 | Deadline budgets, queue controls, retry policies |
| Exposing metrics endpoints to the Internet | Leaks topology/metrics | Proper network ACLs, auth/TLS |

## 29. Production Checklist Before Publishing Measurement Results

- [ ] I clearly defined the **HTTP endpoint/route** and **what constitutes a successful request**.
- [ ] I distinguished offered, accepted, routed, completed, and **successful RPS**.
- [ ] I accounted for rate limiting/429/503 when interpreting throughput.
- [ ] I understand `L=\lambda W` only holds in a relatively steady state with consistent boundaries.
- [ ] I distinguished **TTFB, TTLB, and HTTP request lifetime**, especially for uploads/SSE/WebSockets.
- [ ] I recorded **P50/P95/P99/P99.9**, sample counts, error rates, and appropriate time windows.
- [ ] I did not add P99s across hops or average P99s across pods.
- [ ] I verified which meters/tags/units are **actually exported** in the Gateway version in use.
- [ ] I have `spring-boot-starter-actuator` + the right registry if using Prometheus.
- [ ] I secured management endpoints; `/actuator/**` is not publicly exposed.
- [ ] I understand `http.server.requests` differs from `spring.cloud.gateway.requests` and outbound attempt metrics.
- [ ] I only compute P95/P99 from real histogram buckets, never from `_max`.
- [ ] I keep the `le` label in `histogram_quantile` and aggregate buckets properly.
- [ ] I control histogram cardinality, dynamic route IDs, and avoid raw path/userId/token labels.
- [ ] I monitor scrape health `up` and detect **No data**.
- [ ] I use traces to locate slow hops on **the same request**, never subtracting two percentiles.
- [ ] I have clear inbound/Gateway/outbound/backend latency boundaries.
- [ ] I do not call a filter timer wrapping `chain.filter` "the filter's own CPU time."
- [ ] I measure connection-pool acquire, DNS/TCP/TLS, and backend/DB when suspected and instrumented.
- [ ] I record protocol, TLS, connection reuse, load balancer, payload, and concurrency.
- [ ] I have a baseline and a workload mix representative of real traffic.
- [ ] I use open-loop arrival rates when evaluating capacity at a fixed arrival rate.
- [ ] I check `dropped_iterations`/load-generator saturation and actual achieved RPS.
- [ ] I measure **outbound attempts** and **fallbacks** when Retry/CircuitBreaker are enabled.
- [ ] I test auth, rate limiter, body filters, cache, and streams separately by workload class.
- [ ] I run controlled single-factor A/B tests and repeat them over steady-state windows.
- [ ] I record raw results sufficient for reproduction and never fabricate numbers when uninstrumented.
- [ ] I have performance budgets/SLOs, traffic-guarded alerts, runbooks, and safe stop thresholds.
- [ ] I do not declare an optimization successful merely because latency dropped while success rate fell.

## 30. Practice Exercises and Questions

**Exercise 1 — P95/P99 from histograms.** Given a Gateway exporting `spring_cloud_gateway_requests_seconds_bucket`, write two PromQL queries for a single route's P95 and the cluster-wide P99. Explain why `le` must be kept and why you must not average P99 across two pods.

**Exercise 2 — Useful throughput.** Over 60 seconds, the client sends 18,000 requests; 17,400 complete and 600 time out; of the 17,400, 1,200 return 429 and 300 return 503. Calculate offered RPS, completed RPS, and successful RPS when success is defined as the remainder meeting the contract.

**Exercise 3 — Timeline decomposition.** Given a trace with a 350 ms Gateway server span, a 280 ms HTTP client span, and a 200 ms backend server span, why must you **not** say "Gateway overhead = P99 350 − backend P99 200 = 150 ms"? Propose which queue/pool/TLS instrumentation would provide real evidence.

**Exercise 4 — Retry amplification.** A backend returns 503 on the first attempt, 503 on the second, and 200 on the third. With 1,000 client requests all retried under the same policy, compute the outbound attempts. How might tracking only p99 and final 5xx be misleading?

**Exercise 5 — Canary.** Run baseline and candidate at the same 200 offered RPS, with identical payload/cache/TLS, measuring P50/P95/P99 and error ratio. Write acceptance criteria covering **both successful throughput and P99**, not just averages.

**Exercise 6 — Coordinated omission.** Describe a closed-loop test with 50 VUs where the backend stalls for 5 seconds. Why can offered RPS drop? Compare this with `constant-arrival-rate` and explain the role of `dropped_iterations`.

**Exercise 7 — Streaming.** Measure TTFB and TTLB of a 100 MiB file through the Gateway with a response body transform enabled vs. disabled. How can you tell whether the transform buffered the response? Why should it not share the same P99 SLO as JSON GET?

**Exercise 8 — Metrics security.** Enable a dynamic route `/api/items/{id}` and consider attaching the raw path as a label. Estimate the number of series with 100,000 item IDs; propose replacement labels and ways to restrict access to `/actuator/prometheus`.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Gateway Metrics Filter, route/filter lifecycle, Reactor Netty HTTP client, and Server WebFlux/Server Web MVC variants by version.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer registries, histogram/percentile distributions, and tags.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — managing exposure and securing management endpoints.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — Timer, Observation, histograms, percentiles, and cardinality.
- [Prometheus — Histogram and Summaries](https://prometheus.io/docs/practices/histograms/) — aggregating histograms, bucket bounds, and pitfalls when combining quantiles.
- [Prometheus — PromQL Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase`, `histogram_quantile`.
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) — time series and labels.
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/) — HTTP client/server metrics, connection pool, TLS, and timeouts.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — scheduling, non-blocking pipelines, backpressure, and cancellation.
- [Grafana — Prometheus Data Source](https://grafana.com/docs/grafana/latest/datasources/prometheus/) — dashboards and PromQL.
- [Grafana k6 Documentation](https://grafana.com/docs/k6/latest/) — constant-arrival-rate, HTTP timings, thresholds, and load-testing caveats.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent` and correlating spans across services.

**Remember:** Measuring Gateway performance is never just a single requests/s number or average latency. Measure **offered and successful throughput**, **P50/P95/P99 at the proper boundaries**, and distinguish **client → ingress → Gateway/security/filter chain → HTTP client/pool/TLS → backend → response**. Use **Prometheus histograms** for aggregated percentiles and **distributed traces of the same request** to pinpoint slow hops; **never add or average P99s**. When retries, 429s, fallbacks, caching, or streaming are involved, also measure **outbound attempts, business outcomes, and TTFB/TTLB** so you never conclude the system is "faster" while it is actually rejecting requests or failing to do useful work.

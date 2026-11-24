# HTTP Server Metrics, Response Latency, and Active Request Counts

## 1. Problem Statement: The API Returns 200, Yet Users Experience Slowness

A Spring Boot API may serve thousands of HTTP requests per minute. When the application slows down, looking only at "200 OK" logs cannot answer:

- How many requests arrive per second, and how many succeed vs. fail?
- How long does `GET /api/products/{id}` take: mean, p95, p99?
- How many requests are **currently in flight at the moment of observation**, rather than already completed?
- Did latency rise because of a few very slow requests, or because all requests slowed down?
- Is the server out of servlet worker threads, backed up in a queue, experiencing slow downstream databases, or is the proxy returning 502?
- Are histograms and active-request counts measured **per instance** or across all replicas?
- Why does a dashboard show RPS and latency yet miss a single hung request?

In the Spring Boot ecosystem, three main pieces fit together:

1. **Spring Boot Actuator**: collects and exposes diagnostics/metrics when properly configured.
2. **Micrometer Metrics + Observation**: names meters, attaches tags, measures duration/count/active tasks, and integrates registries.
3. **Prometheus/Grafana or another telemetry backend**: scrapes, stores series, computes rates/quantiles, and fires alerts.

This lesson belongs to **HTTP Observability** and focuses on metrics **on the HTTP server receiving requests**:
- `http.server.requests` — **Timer** for completed requests.
- `http.server.requests.active` — **LongTaskTimer** tracking active request observations in Spring Boot 3.5 when observation long-task timers are enabled.
- Common Prometheus series such as `http_server_requests_seconds_count`, `http_server_requests_seconds_sum`, `http_server_requests_seconds_bucket`, and `http_server_requests_active_seconds_count`.

**Distinguish from the start:** the completed-requests Timer, the in-flight LongTaskTimer, and the count of TCP connections or busy threads **are not the same number**. One HTTP/2 connection can carry multiple active request streams; one HTTP/1.1 keep-alive TCP connection can sit idle with zero running requests.

> **Lab versions:** Spring Boot **3.5.x**, Java **17+**, Spring MVC with embedded Tomcat, Boot-managed Micrometer, and Prometheus registry. Spring Boot 4.x may change configuration, especially active long-task timer behavior; when upgrading, inspect actual runtime metrics rather than assuming legacy series always exist. The Spring MVC example code uses `Thread.sleep` **intentionally to simulate latency** on a Servlet thread; **never use this blocking pattern on a WebFlux event loop**.

## 2. End-to-End Request Observation Diagram

~~~text
Client / Browser
       |
       | HTTP request
       v
CDN / Load Balancer / Reverse Proxy
       |
       | upstream request
       v
Spring Boot (Tomcat / Jetty / Reactor Netty)
       |
       +--> HTTP server observation starts
       |          |
       |          +--> LongTaskTimer active: +1
       |          |
       +--> Filters / Security / Dispatcher
       |          |
       +--> Controller / business / DB / HTTP client
       |          |
       +--> response processing completes
                  |
                  +--> Timer records elapsed time
                  +--> LongTaskTimer active: -1
                  |
                  v
             HTTP response

Micrometer MeterRegistry
       |
       +--> /actuator/metrics (diagnostics by meter name)
       +--> /actuator/prometheus (Prometheus exposition)
                     |
                     v
             Prometheus scrape
                     |
                     v
           PromQL + Grafana + Alerts
~~~

This diagram is a **conceptual model**; the exact placement of observation filters and async handling varies across Spring MVC, WebFlux, security filters, containers, and versions. Before concluding whether metrics cover a failure, verify whether the request actually reached the observation instrumentation or was blocked at a proxy/gateway.

**Observations** in Spring Framework can serve both metrics and tracing simultaneously. Metrics provide aggregated numbers; distributed traces provide detailed execution paths for individual requests. They complement one another and cannot replace each other when investigating latency.

## 3. Understanding Where "Response Time" Is Measured

When someone says "the request took 500 ms", always ask where measurement started and ended.

### Server-Side Latency

Micrometer HTTP server observation measures from when server instrumentation begins handling the request until the observation stops, depending on the web stack and async lifecycle. It typically spans routing, filters, business logic, and part of serialization/response processing; it **does not necessarily equal** the end-to-end duration perceived by the user over the network.

### Client End-to-End Latency

A browser also experiences:
- DNS lookup and TCP/TLS handshake.
- Queueing at CDN/LB/proxy.
- Network RTT, packet loss, and retransmissions.
- Downloading large bodies or connection congestion.
- Client scheduling/rendering.

Hence:

~~~text
Client-observed latency
  ≈ Network/TLS + Edge/proxy + Queue + Origin processing
    + Response transfer + Client-side effects
~~~

This formula is intuitive rather than strict; stages can overlap and do not simply add independently. **Never treat the server timer as the sole proxy for user experience.** For end-to-end analysis, combine RUM, edge metrics, downstream `http.client.requests`, tracing, and origin HTTP server metrics.

### Streaming and Long-Lived Connections

An SSE request keeping a response open for 20 minutes can remain **active in LongTaskTimer for 20 minutes**, while the completed Timer only records a sample when the observation finishes. That does **not** mean the request burned CPU continuously for 20 minutes. Classify streaming/long-poll routes separately and do not mix them into fast JSON API latency SLOs.

## 4. Two Core HTTP Server Metrics: Timer and LongTaskTimer

### 4.1. `http.server.requests` — Timer for Completed Requests

In Spring Boot 3.5, default Spring MVC/WebFlux instrumentation records a timer named `http.server.requests` from web-stack observations. A Micrometer Timer typically exposes these measurements:

| Statistic | Meaning | When to use |
|---|---|---|
| `COUNT` | Number of completed measurements recorded in the timer | Total requests, throughput/RPS |
| `TOTAL_TIME` | Total duration across recorded requests | Computing mean latency |
| `MAX` | Maximum value within the implementation's **time window** | Spotting spikes; do not treat as all-time max since process start |
| Histogram buckets (if enabled) | Count of completed requests with duration ≤ each boundary | Aggregable p95/p99 and % under SLO |

When a request starts and has not finished yet, the **Timer's COUNT does not immediately increment**. Timers track **completed** observations. To see requests currently open, inspect `http.server.requests.active` or an appropriate in-flight gauge.

**Example:** 10 completed requests totaling 2.5s ⇒ mean 0.25s = 250ms. Yet you do not know how many took 2s vs. 5ms; averages hide tail latency.

### 4.2. `http.server.requests.active` — LongTaskTimer While Requests Are Still Running

In Boot 3.5, `management.observations.long-task-timer.enabled` defaults to **true** per Common Application Properties. A LongTaskTimer is created for observations, including eligible HTTP server observations; its name is typically `http.server.requests.active`.

LongTaskTimer reports:
- **ACTIVE_TASKS**: number of samples/requests being tracked *at the moment of reading*.
- **DURATION** (or total duration of active tasks): sum of current ages of unfinished requests.
- **MAX** of active tasks: age of the longest currently running task, depending on backend/registry.

Example with two requests in flight—one running for 8s, the other for 2s:

~~~text
ACTIVE_TASKS = 2
DURATION ≈ 10s
MAX ≈ 8s
~~~

Once both finish, the active count drops back to **0**, while the completed Timer count increments by **2**. LongTaskTimer's `DURATION` is not a monotonic cumulative sum of finished requests; it rises and falls with active tasks.

**Watch out for labels:** while a request is still in flight, tags like final `status`, `outcome`, or `uri` may be unresolved or appear as `UNKNOWN`. Do not require the active metric to carry `uri="/api/slow/{id}"` and `status="200"` like the completed Timer. First aggregate active counts across the **series actually emitted**.

### 4.3. Quick Comparison

| Question | Timer `http.server.requests` | LongTaskTimer `http.server.requests.active` |
|---|---|---|
| How many requests completed? | Yes, `COUNT` | No |
| Latency of finished requests? | Yes | No |
| How many request observations are active right now? | Not directly | Yes, active count |
| Longest-running stuck request? | Not directly | Can check current active max duration |
| Is it a cumulative counter? | `COUNT` grows with completed events (resets on restart) | **No**, active count is a snapshot |
| Is it TCP socket count? | No | No |
| Is it busy Tomcat worker threads? | No | No |
| Suitable for RPS with `rate()`? | Yes, via Prometheus `_count` | Never apply `rate()` to active gauge |

### 4.4. Version Upgrade Note

The name and presence of the active long-task timer **depend on version and observability configuration**. Some Spring Boot 4.x lines change how active timers are created. This lesson targets Boot 3.5.x where `management.observations.long-task-timer.enabled=true` applies. After any upgrade, check release notes, properties, and `/actuator/metrics` before relying on alerts; if the metric disappears, do not interpret it as "the app has zero running requests".

## 5. HTTP Metric Tags: method, uri, status, outcome, exception

A Timer named `http.server.requests` is not just one global number; it is broken down by **tags (dimensions)** such as:

| Tag | Example | Meaning |
|---|---|---|
| `method` | `GET`, `POST` | HTTP method |
| `uri` | `/api/items/{id}` | Handled route pattern/template when known |
| `status` | `200`, `404`, `503` | HTTP status when the request finished |
| `outcome` | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Semantic status group |
| `exception` / `error` | `none` or exception class name | Error marker depending on observation/registry version |
| `instance`, `job` | Added by Prometheus scrape/infra | Replica and logical scrape target |

Example:

~~~text
http.server.requests{
  method=GET,
  uri=/api/slow/{jobId},
  status=200,
  outcome=SUCCESS
}
~~~

This is a **conceptual representation of a meter with tags**, not raw Prometheus exposition text.

### Why Use URI Templates?

Suppose you serve 1 million requests to `/api/items/123`, `/api/items/124`, ... Using the raw URL as `uri` would create 1 million distinct label values, causing **metric cardinality explosion**. Spring web observations use route patterns like `/api/items/{id}` to group requests of the same kind.

**Never put** user IDs, order UUIDs, query strings, emails, access tokens, session IDs, or full URLs/paths containing personal data into tags. Prometheus series cost memory, CPU, and storage; cardinality ≈ product of tag cardinalities. Even 10 methods × 20 statuses × 200 routes × 5 instances yields 200,000 theoretical combinations before adding other tags, so always measure actual series counts.

### Handled Error Yet `exception=none`?

This happens when an exception is resolved into a response by controller advice or an exception handler. Spring Boot/Spring Framework documentation notes that **handled exceptions are not always recorded as exception tags** by default. Use `status`/`outcome` to track HTTP errors, and traces/logs for exception root causes. Never equate `exception=none` with "no business error occurred".

Errors blocked at a load balancer, WAF, or API gateway before reaching the JVM **never appear in origin HTTP server metrics**. Add edge metrics/logs for complete end-user error rates.

## 6. Initializing a Spring Boot 3.5 Project with Actuator and Prometheus

### 6.1. Dependencies

Generate a project using Spring Initializr:
- Java **17+**, Gradle, Spring Boot **3.5.x**.
- **Spring Web**, **Spring Boot Actuator**.
- Add the Prometheus registry if not already selected.

In an Initializr project with the Spring Boot Gradle plugin and dependency management, the `dependencies` block is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

This is a **Gradle dependency fragment**, not a complete `build.gradle`. Spring Boot dependency management resolves compatible Micrometer versions. In Spring Boot 4.x, the MVC starter is typically `spring-boot-starter-webmvc`; avoid accidentally mixing MVC and WebFlux when demonstrating a single stack.

**Do not manually create a `Counter` for every HTTP request already instrumented by Spring Framework.** Incrementing your own counter alongside `http.server.requests` on dashboards risks double counting or inconsistent tagging semantics.

### 6.2. Configuring application.yml

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  tomcat:
    mbeanregistry:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"
  observations:
    long-task-timer:
      enabled: true
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests:
          - 100ms
          - 300ms
          - 1s
          - 3s
~~~

Explanation:
- `server.port=8080`: demo HTTP port.
- `server.tomcat.mbeanregistry.enabled=true`: enables Tomcat MBean registry so Boot can publish **Tomcat metrics** under `tomcat.*`. This is supplemental telemetry and **not required** for HTTP request Timers.
- `management.endpoints.web.exposure.include`: exposes `/actuator/metrics` and `/actuator/prometheus` for curl testing. **Never expose these endpoints publicly in production**; security details are in Section 25.
- `management.observations.long-task-timer.enabled=true`: explicitly states the Boot 3.5 default so active observation LongTaskTimers appear.
- `management.metrics.distribution.percentiles-histogram.http.server.requests=true`: enables percentile histograms for meters matching this prefix, emitting Prometheus `_bucket` series for **aggregable** p95/p99 calculations. **Increases time series count and memory**; do not enable globally across every meter in production.
- `management.metrics.distribution.slo.http.server.requests`: adds service-level boundaries at 100ms, 300ms, 1s, and 3s when supported by the histogram/timer registry. These thresholds are illustrative, not mandatory SLOs for every API.

**Subtle detail:** distribution properties match by **meter ID prefix**, so `http.server.requests.active` also starts with `http.server.requests`. Depending on Micrometer/Boot version, certain histogram/distribution properties can affect the active LongTaskTimer as well and emit extra series. Inspect `/actuator/prometheus`, check actual cardinality, and consider a `MeterFilter` if you need to separate the two names cleanly. Never assume the property produces buckets exclusively for the completed Timer across all versions.

If you only want basic HTTP request counts and mean latency, **you can omit the entire `distribution` block**; `_count` and `_sum` of the completed Timer are still exported, while `_bucket` requires histogram/SLO config.

## 7. Runnable Java Code: fast, slow, error, and URI Templates

Create `src/main/java/demo/httpmetrics/HttpMetricsApplication.java`:

~~~java
package demo.httpmetrics;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@RestController
public class HttpMetricsApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpMetricsApplication.class, args);
    }

    public record SlowResult(String jobId, long sleptMs) { }

    @GetMapping("/api/fast")
    public Map<String, String> fast() {
        return Map.of("message", "ok");
    }

    @GetMapping("/api/slow/{jobId}")
    public SlowResult slow(
            @PathVariable String jobId,
            @RequestParam(defaultValue = "3000") long ms)
            throws InterruptedException {

        if (ms < 0 || ms > 10_000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "ms must be between 0 and 10000"
            );
        }

        // ONLY to create a slow request in this Spring MVC/Tomcat demo.
        // NEVER use Thread.sleep on a WebFlux event loop.
        Thread.sleep(ms);

        return new SlowResult(jobId, ms);
    }

    @GetMapping("/api/error")
    public void simulatedError() {
        throw new ResponseStatusException(
            HttpStatus.SERVICE_UNAVAILABLE,
            "simulated unavailable"
        );
    }
}
~~~

This is a **complete single Java source file** inside a Spring Boot project with the dependencies above. Once running, you have:
- `GET /api/fast`: JSON response `{"message":"ok"}`.
- `GET /api/slow/A?ms=3000`: holds the servlet request ~3s then returns JSON with `jobId="A"` and `sleptMs=3000`.
- `GET /api/error`: returns **503 Service Unavailable** via Spring MVC error handling.

**Intentional demo trade-off:** `Thread.sleep` blocks a servlet worker thread, making "in-flight" requests easy to observe in a classroom demo. In production, do not tie up Tomcat worker threads sleeping; measure real downstream latency with tracing. In **WebFlux**, use `Mono.delay(Duration.ofSeconds(...))` or non-blocking APIs instead of calling `Thread.sleep` on the Reactor event loop.

### 7.1. Startup

From the project root with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

By default the server listens on port 8080 as configured in YAML. If the port is occupied, stop the other app first. Never run formal latency benchmarks with debug builds, active debugger breakpoints, or a heavily loaded laptop.

### 7.2. Testing fast, slow, and error

~~~bash
curl -sS -i http://localhost:8080/api/fast
curl -sS -i "http://localhost:8080/api/slow/A?ms=3000"
curl -sS -i http://localhost:8080/api/error
~~~

Expectations:
- Fast: status **200**, body `{"message":"ok"}`.
- Slow: status **200**, body with `jobId="A"` and `sleptMs=3000`.
- Error: status **503**; Spring Boot's error body depends on configuration, so do not assert raw error JSON verbatim.

`Map.of` and Jackson determine field order; check JSON by key. `ms=3000` represents an intentional 3s delay **inside the controller**, so client-observed latency will be slightly above 3s due to routing, serialization, and network overhead.

### 7.3. Repeating Requests to Generate Statistics

~~~bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null http://localhost:8080/api/fast
done
~~~

This is Bash/Linux/macOS/Git Bash syntax, **not** native PowerShell. On Windows PowerShell:

~~~powershell
1..5 | ForEach-Object {
  curl.exe -sS -o NUL http://localhost:8080/api/fast
}
~~~

After a few requests, the Timer records measurements for `/api/fast`; if nothing shows up in Actuator, verify endpoint exposure, dependencies, web stack, and actual request URLs.

## 8. Inspecting Metrics via `/actuator/metrics`

### 8.1. Listing Meter Names

~~~bash
curl -sS http://localhost:8080/actuator/metrics
~~~

The endpoint returns JSON with a `names` array, partially illustrated as:

~~~json
{
  "names": [
    "http.server.requests",
    "http.server.requests.active",
    "jvm.memory.used"
  ]
}
~~~

This is an **illustrative excerpt**, not a complete list or guaranteed ordering. Real runtimes include many JVM, process, system, HTTP connection, and Tomcat meters (when registry is enabled).

### 8.2. Viewing the Completed Timer

~~~bash
curl -sS http://localhost:8080/actuator/metrics/http.server.requests
~~~

A response typically has a structure like:

~~~json
{
  "name": "http.server.requests",
  "measurements": [
    {"statistic": "COUNT", "value": 7.0},
    {"statistic": "TOTAL_TIME", "value": 3.2},
    {"statistic": "MAX", "value": 3.01}
  ],
  "availableTags": []
}
~~~

**Do not treat `7`, `3.2`, `3.01`, or `availableTags=[]` as fixed output**: they depend entirely on the requests executed, registry, and active tags. Responses may also include `description`, `baseUnit`, `method`/`uri`/`status` tags, and different ordering. Focus on the semantics of `COUNT`, `TOTAL_TIME`, and `MAX`.

To filter by a specific route/status:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/api/fast&tag=method:GET"
~~~

Templated route:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/api/slow/{jobId}&tag=method:GET"
~~~

Shell/curl URL syntax may require percent-encoding `{` and `}`; a cleaner approach with curl is `--globoff` or `--get --data-urlencode`:

~~~bash
curl -sS --get \
  --data-urlencode 'tag=uri:/api/slow/{jobId}' \
  --data-urlencode 'tag=method:GET' \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

**Note:** raw `{jobId}` in a curl URL can be interpreted as a curl URL glob expression; `--get --data-urlencode` is much safer to teach and run. Actuator drill-down uses the **original dot-separated meter name**, not the underscore Prometheus name.

### 8.3. Viewing the Active LongTaskTimer

~~~bash
curl -sS \
  http://localhost:8080/actuator/metrics/http.server.requests.active
~~~

Measurements can include `ACTIVE_TASKS` and `DURATION`; when no request is running at the snapshot moment, `ACTIVE_TASKS` may be 0 or the meter may not yet appear depending on lifecycle/version. **Never interpret a single `active=0` reading as zero traffic**: it merely means zero request observations were inside the scope at that instant.

Crucially, while a slow request remains open, the active count rises. We will make this clearly visible in Section 9.

## 9. Hands-On "In-Flight Request": Two Terminals

### 9.1. Terminal A — Start a Slow Request

Open one terminal and run:

~~~bash
curl -sS -i \
  "http://localhost:8080/api/slow/long-job?ms=10000"
~~~

The controller sleeps for 10 seconds. While it is still waiting, **let the command run**—do not press Ctrl+C.

### 9.2. Terminal B — Read Active Metrics While Terminal A Waits

Within a few seconds of starting A:

~~~bash
curl -sS \
  http://localhost:8080/actuator/metrics/http.server.requests.active
~~~

Look for `ACTIVE_TASKS`. With one slow request running, the active count **may be around 1**, though other concurrent requests (including metrics scrapes themselves) may show up depending on instrumentation/filtering. The key proof is that the active count **rises during the slow window**, not that it equals exactly 1 on every read.

If you sample every 2 seconds while the request is still running, the active duration of that request increases. Once Terminal A finishes, the active count returns to baseline while the `http.server.requests` completed Timer increments by one.

### 9.3. Reading the Live Gauge and Seeing Completed Count Change

Try:

~~~bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/api/slow/{jobId}"
~~~

Use the `--get --data-urlencode` variant from Section 8 to avoid URL globbing. While A is still processing, the completed count for the slow route **has not increased yet**; once A completes, it increments. This clearly illustrates the difference between `Timer` and `LongTaskTimer`.

### 9.4. Sending Two Concurrent Slow Requests

Run in two terminals or background processes:

~~~bash
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/A?ms=10000"
~~~

~~~bash
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/B?ms=10000"
~~~

While both wait, scrape the active metric from a third terminal. As long as Tomcat has enough worker threads, you should observe the active count rise by roughly **2** over baseline. If the two requests are staggered or the sampler runs late, the observed number may differ—that is the nature of **instantaneous sampling**, not a metric bug.

### 9.5. Why Is It Hard to "Catch" Fast Requests in an Active Gauge?

If a request takes 5ms and Prometheus scrapes every 15s, the probability of scraping during that 5ms window is tiny. Fast requests are still **counted by the Timer upon completion**, whereas an active snapshot will read 0 most of the time.

To understand regular traffic, look at **RPS and Timer latency**. To understand **concurrency/backlog**, inspect the active gauge alongside container queues/connections and steady load tests. Never use a single snapshot as proof that no work is happening.

## 10. Prometheus Metric Naming: Don't Confuse It with Actuator Meter Names

Actuator/Micrometer logical names:

~~~text
http.server.requests
http.server.requests.active
~~~

In Prometheus exposition, names are normalized with unit and statistic suffixes:

~~~text
http_server_requests_seconds_count
http_server_requests_seconds_sum
http_server_requests_seconds_max
http_server_requests_seconds_bucket

http_server_requests_active_seconds_count
http_server_requests_active_seconds_sum
http_server_requests_active_seconds_max
~~~

The presence of `_bucket` depends on histogram/SLO configuration and registry/version. The `active` series below belong to **LongTaskTimer**; its `_count` represents **active tasks at scrape time**, unlike the cumulative completed Timer count above.

**Illustrative sample lines**, not actual measured output from the project:

~~~prometheus
http_server_requests_seconds_count{method="GET",status="200",uri="/api/fast"} 5
http_server_requests_seconds_sum{method="GET",status="200",uri="/api/fast"} 0.045
http_server_requests_active_seconds_count{method="GET",uri="UNKNOWN"} 1
http_server_requests_active_seconds_sum{method="GET",uri="UNKNOWN"} 4.3
~~~

Real labels may also include `exception`, `error`, `outcome`, `job`, or `instance`; active `uri` may be `UNKNOWN`. The active timer's `_sum` **is not a cumulative duration** like `http_server_requests_seconds_sum`.

### Checking Real Exposition Output

~~~bash
curl -sS http://localhost:8080/actuator/prometheus
~~~

In Bash/Linux you can filter:

~~~bash
curl -sS http://localhost:8080/actuator/prometheus \
  | grep '^http_server_requests'
~~~

Windows PowerShell:

~~~powershell
(Invoke-WebRequest -UseBasicParsing \
  http://localhost:8080/actuator/prometheus).Content
~~~

PowerShell 5.1 does not use `\` for line continuation like Bash; single-line version:

~~~powershell
(Invoke-WebRequest -UseBasicParsing http://localhost:8080/actuator/prometheus).Content
~~~

In Docker/Kubernetes, Prometheus must reach the **real service/Pod address**, not `localhost` inside the Prometheus container. The command above inspects a locally running demo.

## 11. Minimal Prometheus Scrape Job Configuration

Example fragment in `prometheus.yml`:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "spring-web-runtime"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
~~~

This is **for Prometheus running on the same host as Spring Boot**. If Prometheus runs in its own container, `localhost:8080` points to the Prometheus container itself, so replace it with the appropriate container/network service address. Production typically uses Kubernetes service discovery, Operator `ServiceMonitor`/`PodMonitor`, TLS/mTLS/auth, and network policies instead of static targets.

### When Do Series Appear?

- HTTP metrics may only register once an observation has a sample or becomes active, so hit `/api/fast` or `/api/slow` before concluding "the metric is missing".
- Prometheus scrapes on its interval; wait for one scrape cycle or check the targets-status UI.
- When the app restarts, cumulative counters reset. PromQL `rate()`/`increase()` handle counter resets properly; never compute `count(now) - count(before)` manually across processes without accounting for restarts.

**Do not use `/actuator/metrics` as a production metrics scraper backend.** It is a diagnostic endpoint listing meter names and measurements; Prometheus should scrape `/actuator/prometheus` in its exposition format.

## 12. PromQL: Throughput / Requests Per Second

The Prometheus series for completed request counts is typically:

~~~text
http_server_requests_seconds_count
~~~

### Service-Wide RPS

~~~promql
sum(rate(http_server_requests_seconds_count{job="spring-web-runtime"}[5m]))
~~~

Explanation:
- `rate(counter[5m])` estimates the per-second rate of increase over a 5-minute window, accounting for counter resets.
- `sum(...)` sums series across tags, routes, and instances.
- The result is **average requests per second over 5 minutes**, not the exact count in any single isolated second.

With multiple replicas, `sum(rate(...))` aggregates throughput across the whole service when labels match all targets.

### RPS by HTTP Method/Route

~~~promql
sum by (method, uri) (
  rate(http_server_requests_seconds_count{
    job="spring-web-runtime",
    uri=~"/api/.*"
  }[5m])
)
~~~

Use route **templates** so the series count stays bounded; never use raw `jobId` or `ms` values in tags.

### Total Requests Over 5 Minutes

~~~promql
sum(increase(http_server_requests_seconds_count{
  job="spring-web-runtime"
}[5m]))
~~~

`increase` estimates the total increase over the window and can return fractional values due to extrapolation/sampling; this does not mean the server received "half a request".

**Never apply `rate()` to `http_server_requests_active_seconds_count`**: the active series is a snapshot gauge, not a monotonically increasing request counter.

## 13. PromQL: Mean Response Latency

If `_sum` is the total duration of completed requests and `_count` is the count of completed requests, then:

~~~text
Average latency = ΔTotalDuration / ΔCompletedRequests
~~~

PromQL:

~~~promql
sum(rate(http_server_requests_seconds_sum{
  job="spring-web-runtime"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="spring-web-runtime"
  }[5m])),
  1e-9
)
~~~

The output unit is **seconds/request**; multiply by 1000 for milliseconds.

### Why Not Average Per-Instance Averages?

Suppose:
- Instance A served 100 requests with a mean of 100ms.
- Instance B served 1 request with a mean of 2s.

The unweighted average of the two means is 1.05s, whereas the true mean across all 101 requests is much lower. The right method is **sum total durations, sum total counts, then divide**—never average per-instance averages.

### By Route

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_sum{
    job="spring-web-runtime",uri=~"/api/.*"
  }[5m])
)
/
clamp_min(
  sum by (uri) (
    rate(http_server_requests_seconds_count{
      job="spring-web-runtime",uri=~"/api/.*"
    }[5m])
  ),
  1e-9
)
~~~

This yields **average latency** per route, not p95/p99. When tail latency matters, use histograms as shown next.

## 14. PromQL: p95/p99 and Histogram Buckets

### Why Mean Latency Is Insufficient

Across 100 requests:
- 95 requests complete in 20ms.
- 5 requests complete in 3s.

The mean rises due to the 5 slow requests, yet it fails to show **how many users hit the tail** or the true shape of the distribution. For service latency SLOs, p95/p99 are usually far more informative than the mean.

### Histogram Bucket Metric

With histograms enabled as in Section 6:

~~~text
http_server_requests_seconds_bucket{le="0.1", ...}
http_server_requests_seconds_bucket{le="0.3", ...}
http_server_requests_seconds_bucket{le="1.0", ...}
http_server_requests_seconds_bucket{le="+Inf", ...}
~~~

`le` is the cumulative bucket upper bound in **seconds**; the bucket value is the count of samples with duration **≤ boundary**. Exact buckets in practice may vary depending on Micrometer/registry and configuration.

Service-wide p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="spring-web-runtime"
    }[5m])
  )
)
~~~

Per-route p99:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      job="spring-web-runtime",
      uri=~"/api/.*"
    }[5m])
  )
)
~~~

**Important:**
- `histogram_quantile` over classic Prometheus histograms gives an **estimate** via linear bucket interpolation, not an exact p95 from raw samples.
- You must preserve the `le` label when aggregating classic histograms.
- Histograms must be enabled and `_bucket` series present; otherwise queries return no data.
- Avoid computing p95 for a route with only 1–2 requests in 5 minutes and treating it as statistically reliable. Check sample volume.
- `management.metrics.distribution.percentiles.http.server.requests=0.95,0.99` produces **client-side percentiles** if enabled independently; they are **not accurately aggregable across instances**. With Prometheus and multiple replicas, prefer histograms if your cardinality budget allows.

### Fraction of Requests Under a 300ms SLO

Assuming the `0.3` bucket boundary actually exists:

~~~promql
sum(rate(http_server_requests_seconds_bucket{
  job="spring-web-runtime",le="0.3"
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="spring-web-runtime"
  }[5m])),
  1e-9
)
~~~

Values range from 0 to 1, estimating the **proportion** of 5-minute requests finishing in ≤300ms for matching filters/labels. For an SLO of 99% within 300ms, require ≥0.99 under sufficient traffic volume.

**Never use** `http_server_requests_active_seconds_sum` as the numerator for mean latency or completed-request SLO histograms: that tracks the cumulative age of **currently running requests**, which has completely different semantics.

## 15. PromQL: 5xx Rate and Distinguishing Outcomes

5xx ratio over 5 minutes:

~~~promql
sum(rate(http_server_requests_seconds_count{
  job="spring-web-runtime",status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    job="spring-web-runtime"
  }[5m])),
  1e-9
)
~~~

A result of 0.03 corresponds to roughly **3%** over the window when traffic is large enough to estimate reliably. When traffic is zero, clamping the denominator prevents NaN, though it **does not replace missing-data checks**. Set separate alerts for scrape failures (`up == 0`) and traffic drops if appropriate.

### 4xx Does Not Mean Server Failure

- 400 validation errors may indicate clients sending invalid data.
- 401/403 from Security may indicate authentication failures, bots, or permission rules.
- 404 may be nonexistent URLs.
- 429 indicates rate limiting, reflecting either overload or intentional throttling.
- 5xx generally warrants investigation for server or dependency failures.

Chart these groups separately and alert based on user impact instead of lumping all non-200 responses into one vague "error rate". For errors returned by a gateway/CDN before reaching the origin, **origin `http.server.requests` will not see them**; add edge metrics.

### Some Error Responses Have No Exception Tag

If a controller throws `ResponseStatusException` and an exception handler resolves it, the final status may be 503 while `exception`/`error` tag reads `none` depending on observation handling. Base 5xx queries on `status`/`outcome` per policy, not exclusively on `exception!="none"`.

## 16. PromQL: Requests Currently in Flight

### 16.1. Active Count Using LongTaskTimer

In Boot 3.5 with LongTaskTimer enabled, Prometheus typically exposes:

~~~text
http_server_requests_active_seconds_count
~~~

Service-wide query:

~~~promql
sum(http_server_requests_active_seconds_count{
  job="spring-web-runtime"
})
~~~

Per-instance query:

~~~promql
sum by (instance) (
  http_server_requests_active_seconds_count{
    job="spring-web-runtime"
  }
)
~~~

This represents a **snapshot of active observations at each Prometheus scrape**, neither historical request totals nor new request arrival rate.

### 16.2. Total Age of Currently Active Requests

~~~promql
sum(http_server_requests_active_seconds_sum{
  job="spring-web-runtime"
})
~~~

This is the **accumulated seconds of tasks currently running** at scrape time; e.g., 3 running tasks aged 2s, 5s, and 8s ⇒ sum ≈ 15s. It drops abruptly when a long task completes. **Never apply `rate()` to active sum to compute request latency.**

You may also see `http_server_requests_active_seconds_max` when exported, representing the max active age within that snapshot/time window, not max completed request latency.

### 16.3. Active ≠ Tomcat Busy Threads ≠ TCP Active Connections

| Measurement | Unit | Example difference |
|---|---|---|
| HTTP active requests | Unfinished observations | A 1-hour SSE stream stays active |
| Tomcat busy threads | Busy worker threads | Servlet async can keep a request active without pinning a thread |
| TCP current connections | Sockets/connections | An HTTP keep-alive connection can sit idle between requests |
| HTTP/2 concurrent streams | Active HTTP/2 request streams | One TCP connection carries multiple streams |
| Queue length | Tasks/connections waiting for handling | Not yet inside HTTP observation, so not counted as active |
| Downstream active calls | In-flight HTTP client/DB calls | One inbound request may fan out to multiple outbound calls |

Hence there is no universal formula `active HTTP requests = active TCP connections` or `active requests = Tomcat busy threads` valid across all runtimes.

### 16.4. Active Metric Labels Can Differ from Completed Metrics

An in-flight request does not yet have a final status and may not yet have a resolved URI mapping, so `uri=UNKNOWN` or `status=UNKNOWN` can appear. If querying:

~~~promql
http_server_requests_active_seconds_count{uri="/api/slow/{jobId}"}
~~~

returns empty, **do not conclude the entire active counter is broken**. Check real series at `/actuator/prometheus`, query without a URI filter first, and rely only on labels actually emitted.

## 17. Relationship Between RPS, Latency, and Concurrency: Little's Law

In a system near steady state, Little's Law states:

\[
L = \lambda W
\]

Where:
- `L` = average number of requests/work items inside the measured system.
- `λ` = arrival/completion rate (requests/second).
- `W` = average time a request spends inside that system/boundary (seconds).

Examples within a consistent boundary:
- 20 requests/second, mean latency 0.25s ⇒ roughly **5 in-flight requests** on average.
- 20 requests/second, mean latency 1s ⇒ roughly **20 in-flight requests** on average.

**Critical preconditions:** same request population, same boundary, stable system, and sufficiently long averaging window. If the active metric includes long-lived SSE streams while the completed timer measures only short JSON requests, applying Little's Law across mismatched populations is invalid. If upstream queues sit outside the server observation, `L` from the active metric will not reflect that queue either.

By Little's Law, if RPS stays roughly constant while active count climbs, latency or queueing is worsening. Always inspect CPU, Tomcat/Netty capacity, downstream pools, and timeouts to find the **cause** before mechanically "adding more threads".

### Operational Signatures

| RPS | Latency | Active count | Initial diagnosis |
|---|---|---|---|
| Increasing | Stable | Increasing proportionally | More workload; may still be healthy |
| Flat | Increasing | Increasing | Possible downstream bottleneck, lock contention, pool exhaustion, CPU |
| Decreasing | Increasing | High | Saturation, queueing/backpressure, or timeouts |
| Flat | Stable | Permanently high | Streaming/long polling or leaked in-flight work |
| Drops to 0 | N/A | 0 | Possibly zero traffic **or** metrics/target lost; check `up` |
| Error rate rising | May drop or rise | Any | Fail-fast or timeouts; inspect statuses and traces |

This table offers **heuristics** only. Production diagnosis requires latency distributions, traces, logs, and saturation metrics together.

## 18. Tomcat Runtime Metrics: Context for Understanding Active HTTP

The demo enabled:

~~~yaml
server:
  tomcat:
    mbeanregistry:
      enabled: true
~~~

Spring Boot can expose metrics prefixed with `tomcat.` through the Tomcat MBean Registry. Depending on version and connector, you may see:
- Current/busy worker threads.
- Connections associated with the Tomcat connector.
- Session metrics (if enabled by server and config).
- Request-processing metrics per connector.

Run:

~~~bash
curl -sS http://localhost:8080/actuator/metrics
~~~

Then inspect exact names starting with `tomcat.` and drill down per meter—**do not guess that every Tomcat sub-meter always exists**. When running WebFlux on Reactor Netty, you will not have those Tomcat MBeans; use Reactor Netty metrics and connection provider metrics instead.

### Reading Them Together

A snapshot showing:
- HTTP active requests = 200.
- Tomcat busy threads = 20.
- TCP connections = 900.

is **not contradictory**: many async HTTP requests may be active without holding worker threads, while many of the 900 keep-alive sockets sit idle. If Tomcat busy threads approach the limit while queues/latency climb, investigate blocking calls or downstream latency. If active requests rise mostly from SSE, monitor stream/client counts instead of blindly bumping Tomcat `max-threads`.

**Never treat the demo's `Thread.sleep` as a production capacity model**; it deliberately pins servlet threads so learners can easily observe metrics changing.

## 19. Spring WebFlux and Reactive HTTP Server Observations

WebFlux also receives default HTTP server instrumentation from Spring Boot Actuator, typically sharing the logical meter name `http.server.requests` and active timer when enabled, though runtime behavior differs:

- Handlers return `Mono`/`Flux`, and the Reactor Netty event loop must not be blocked.
- A request waiting non-blockingly on downstream I/O remains an active HTTP observation.
- A long-lived `Flux<ServerSentEvent<?>>` stream keeps its observation active, affecting active counts and final timer latency on completion.
- HTTP/2 multiplexing means active request streams do not equal TCP connections.

### Proper WebFlux Fragment

~~~java
// Fragment inside a @RestController of a WebFlux project:
@GetMapping("/api/reactive-slow")
public Mono<Map<String, String>> slow() {
    return Mono.delay(Duration.ofSeconds(3))
        .map(ignored -> Map.of("message", "done"));
}
~~~

Requires imports `reactor.core.publisher.Mono`, `java.time.Duration`, `java.util.Map`, and `org.springframework.web.bind.annotation.GetMapping`. This is a **fragment**, not a standalone source file. It produces a 3s async delay without blocking the event loop with `Thread.sleep`.

**Do not port the MVC demo to WebFlux simply by swapping the starter** while leaving `Thread.sleep` intact. In WebFlux, blocking code stalls all connections sharing that event loop. Use async APIs or isolate unavoidable blocking libraries via `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.

### Metrics Are Not Downstream Traces

If a WebFlux handler calls a partner service via `WebClient`, the server timer measures inbound request lifecycle per observation, while outbound `WebClient` produces `http.client.requests` when constructed from the auto-configured builder. To see whether a 3s delay came from the database, partner API, or serialization, use child spans/tracing or custom business timers; a single HTTP server timer does not break down internal stages.

## 20. Observing Timed-Out, Canceled, and Disconnected Requests

Not every request ends cleanly with `200` or `500`:
- Client aborts mid-request.
- Browser navigation cancels a stream.
- Reverse proxy times out and returns 504 to the client while the origin is still processing.
- Servlet asynchronous request times out.
- Reactor Netty network disconnect.
- Graceful shutdown cuts off a long-lived stream.

Consequences:
- Active LongTaskTimer decrements once the observation stops/cancels, though detection of disconnects can lag.
- Completed Timer records samples/statuses reflecting the **origin's** outcome, which can differ from what the proxy returned to the client.
- If the gateway rejects a request before it reaches the app, zero origin sample exists.
- A response that already committed 200 before streaming failed mid-way cannot retroactively change HTTP status to 500; record separate error signals and observe client telemetry.

When investigating timeouts:
1. Compare `http.server.requests` and `http.client.requests` alongside service traces.
2. Check vendor-specific proxy/ingress metrics for 499/502/503/504.
3. Check whether active count drops after cancellations or stays elevated.
4. Inspect client, LB/proxy, Servlet async, and Reactor operator deadlines.
5. Verify subscriptions/resources are cleaned up on client disconnects.

**Do not equate "gateway returned 504" with "Spring Boot has status=504"**; the gateway may emit 504 before the JVM knows anything failed.

## 21. HTTP Server Metric Names and Customizing ObservationConvention

Spring Boot 3.5 allows renaming the HTTP server observation via:

~~~yaml
management:
  observations:
    http:
      server:
        requests:
          name: http.server.requests
~~~

The default name is already `http.server.requests`. Rename it only with a migration plan for dashboards, recording rules, and alerts, since changing the name breaks existing Prometheus queries.

To add low-cardinality tags or change conventions, Spring Framework provides:
- **MVC:** `org.springframework.http.server.observation.DefaultServerRequestObservationConvention` / `ServerRequestObservationConvention`.
- **WebFlux:** equivalent types in `org.springframework.http.server.reactive.observation`.

Customizations should rely on **HTTP route templates**, service tiers, or bounded API group names; avoid raw URLs, queries, or user IDs. Never attach exception messages as tags. Changing the observation convention can affect both **metrics and trace attributes**, since both derive from observations per Framework design.

### When to Write a Custom Active Requests Gauge

Some systems need "business requests in progress" with a boundary distinct from HTTP observations—for instance, counting only authenticated APIs while excluding SSE. You can maintain a **custom Gauge/`AtomicInteger`** or dedicated LongTaskTimer with a well-defined scope, provided:
- Counters increment/decrement cleanly across all completion, error, timeout, and cancellation paths.
- Async MVC/WebFlux tracks the **publisher lifecycle**, not just method entry/exit.
- Tag cardinality and metric names avoid colliding with built-in meters.
- Never name a custom metric `http.server.requests.active` and cause double counting.

**Prefer built-in HTTP metrics first**, adding custom instrumentation only when boundaries are clearly defined and tested.

## 22. Minimal Dashboard for an API Service

A useful dashboard presents these together:

| Panel | Metric/query | Meaning |
|---|---|---|
| Traffic RPS | `sum(rate(http_server_requests_seconds_count[5m]))` | Completed request throughput |
| HTTP 5xx rate | `sum(rate(...{status=~"5.."}[5m]))` | Server errors/second |
| HTTP 5xx ratio | 5xx count rate / total count rate | Error percentage |
| Mean latency | rate(total duration) / rate(count) | Average completed request time |
| p95/p99 latency | `histogram_quantile` over `_bucket` | Tail latency |
| Requests under SLO | `le="0.3"` bucket / total | 300ms SLO compliance when bucket exists |
| Active requests | `sum(http_server_requests_active_seconds_count)` | In-flight observations |
| Active age | `http_server_requests_active_seconds_max` or active sum | Long-open requests; verify semantics |
| Tomcat busy/current threads | Actual `tomcat.*` meter names | Worker pool saturation |
| JVM heap/GC/process CPU | Built-in Micrometer JVM/system meters | Runtime pressure |
| Availability | Prometheus `up` / Actuator health | Whether target is scrapeable/serving |
| Dependency latency | `http.client.requests`, DB metrics/traces | Downstream bottlenecks |

**Never treat RPS = 0 as proof the system is "healthy".** If the Prometheus target is down, both RPS and active gauges lose series; configure dedicated alerts for `up == 0` and expected target counts.

### Add Useful Labels Without Multiplying Series Unboundedly

Reasonable labels include `application`, `environment`, `region`, `instance`, `method`, `uri` template, `outcome`, and `status`. Still, cap total combinations. For per-request drill-down, use trace IDs in logs/traces with proper retention and access controls—**never put trace IDs into metric labels**.

## 23. Alerting on Latency and Saturation: Require Traffic Floors

Never alert on "p99 > 1s" when a service had a single request in 10 minutes, nor blindly on `active_requests > 100` without knowing if those are SSE subscriptions. Combine:
- Minimum traffic / sample count.
- Error budget or SLO targets per route class.
- Violation duration (e.g., `for: 5m`).
- Metric boundaries: gateway vs. origin, completed vs. in-flight.
- Expected behavior of streaming routes.
- Per-replica capacity and autoscaling behavior.

An **illustrative** Prometheus alert rule, not a complete organizational SLO policy:

~~~yaml
groups:
  - name: spring-http
    rules:
      - alert: ElevatedHttp5xxRatio
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              job="spring-web-runtime",status=~"5.."
            }[5m]))
            /
            clamp_min(
              sum(rate(http_server_requests_seconds_count{
                job="spring-web-runtime"
              }[5m])),
              1e-9
            )
          ) > 0.05
          and
          sum(rate(http_server_requests_seconds_count{
            job="spring-web-runtime"
          }[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Spring HTTP 5xx ratio above 5 percent"
~~~

The `and` clause triggers only when the error ratio exceeds 5% **and** traffic exceeds 1 RPS in the same scope; thresholds are purely illustrative. Production also needs independent alerts for zero-traffic or down targets so a 100% outage isn't masked.

### Alerting on Active Requests

Sample query:

~~~promql
sum by (instance) (
  http_server_requests_active_seconds_count{
    job="spring-web-runtime"
  }
)
~~~

Compare against baseline and real instance limits: Tomcat max threads, connection pools, CPU, memory, and streaming subscriber counts. A value of 100 may be completely normal for reactive SSE yet alarming if each request holds a JDBC connection.

**Avoid rigid per-route active alerts** if the active metric lacks resolved `uri` tags before completion. If per-route in-flight alerts are required, instrument a dedicated meter at the appropriate boundary.

## 24. Troubleshooting: Missing or Incorrect Metrics

| Symptom | Common cause | How to check |
|---|---|---|
| `/actuator/metrics` returns 404 | Missing Actuator/exposure off, different path | Check starter, `include`, base-path, management port |
| `/actuator/prometheus` returns 404 | Missing `micrometer-registry-prometheus` or unexposed | Add registry, include `prometheus`, restart |
| Metrics endpoint returns 401/403 | Spring Security/management access rules | Authenticate properly; do not disable auth blindly |
| JVM metrics exist, no `http.server.requests` | No instrumented requests hit yet, observation disabled, path unmapped | Call `/api/fast` then check meter, verify config/stack |
| Completed Timer exists, no `http.server.requests.active` | LongTaskTimer disabled/version difference/filtered | Check Boot 3.5 property, real meter name, scrape during slow request |
| `active_count=0` despite high RPS | Scrapes miss very short requests | Test 10s slow request, increase frequency, or run steady load |
| Active filtered by `uri=/api/slow/{jobId}` is empty | In-flight tags have `uri=UNKNOWN` or unresolved | Query aggregated without URI filter and inspect real labels |
| `_bucket` missing | Histogram/SLO disabled or different config/registry | Check distribution config and `/actuator/prometheus` |
| p95 query empty/NaN | Missing bucket data, low traffic, wrong label selector | Verify `_bucket` and `le` labels |
| Mean latency huge/tiny | Confusing seconds with ms or omitting `/ count` | Use `rate(sum)/rate(count)`, multiply by 1000 for ms |
| RPS doubled | Scraping duplicate targets, duplicate custom counter, wrong aggregation | Check targets and `job`/`instance` labels |
| Counts reset after deploy | Process restart resets Timer counters | Use `rate()/increase()` properly |
| Max latency "drops to 0" after a while | Micrometer `MAX` decays/resets on time window | Do not treat `MAX` as all-time maximum |
| HTTP 502 at CDN, origin 5xx=0 | Edge generated errors before/outside Spring | Compare gateway/CDN and origin metrics |
| `exception=none` despite `status=500` | Exception handled by advice, tag omits root cause | Check status, logs, traces, handler behavior |
| Active metric grows endlessly | SSE/WS streams, uncompleted async, cancellation leaks | Classify routes, check open connections/subscriptions, thread dumps |
| Tomcat busy metrics missing | Tomcat MBean registry off or not using Tomcat | `server.tomcat.mbeanregistry.enabled=true`, check stack |
| Too many metric time series | Raw URL/user ID tags or broad histograms | URI templates, cardinality budget, scope histograms |
| Prometheus scrape fails in Docker | Using `localhost:8080` across container network namespaces | Use valid service hostname/network route |
| Actuator endpoint exposed to Internet | Exposure without network/security controls | Protect with auth/mTLS/ingress rules |

### Concise Diagnostic Workflow

1. Confirm the project uses the expected Spring Boot version, starters, and web stack.
2. Send fast, slow, and error requests.
3. Check `/actuator/metrics` for `http.server.requests`.
4. While a slow request is open, inspect `http.server.requests.active`.
5. Inspect `/actuator/prometheus`, distinguishing completed vs. active `_count`.
6. Check Prometheus target status/`up` and series labels.
7. Verify histogram buckets exist before using `histogram_quantile`.
8. Correlate total RPS, latency, 5xx, and active counts with logs/traces.
9. If suspecting a bottleneck, inspect Tomcat/Netty, JVM, DB pool, and HTTP client metrics.
10. Evaluate queries/alerts against traffic volume, deployments, and streaming workloads.

## 25. Observability Security and Cost

**Actuator metrics can reveal operational details**: route names, error statuses, counts, JVM/process metrics, and environment details in other endpoints. Never expose all of `/actuator/**` publicly just for Prometheus. Even `/actuator/prometheus` should be protected via an appropriate mechanism:
- Private network or service discovery + network policy.
- Dedicated management port bound to a private interface/ingress.
- Spring Security authentication/authorization or mTLS.
- Scraper credential/secret rotation and TLS encryption.
- Role-based access for dashboards, alert routing, and retention policies.

The demo project **omits Spring Security**, so `management.endpoints.web.exposure.include` makes metrics directly accessible on `localhost:8080`. Run it strictly for learning. Once `spring-boot-starter-security` is added, Boot applies different actuator security defaults, and a custom `SecurityFilterChain` overrides automatic config—verify actual behavior rather than assuming endpoints stay private.

**Metric cardinality cost:** Histogram buckets multiply series count across every tag combination, instance, and boundary. Enabling histograms across all HTTP traffic can significantly increase Prometheus ingestion and storage; restrict histograms to critical route classes/SLOs, control labels, and monitor series counts/costs.

## 26. Automated Testing: Verifying Timers Appear Without Tag Explosion

Standard tests do not need a running Prometheus server to verify Micrometer instrumentation. In a Spring Boot integration test with Actuator, you can invoke real endpoints via `MockMvc` or `TestRestTemplate` and inspect metrics, though **do not expect every test slice to enable all production registries automatically**. Individual test setups may swap `MeterRegistry` or disable metrics. For production QA, verify at least:
- `GET /api/fast` returns 200 and increments `http.server.requests` count.
- `GET /api/error` returns 503 and reflects the status tag.
- `GET /api/slow/{jobId}` with multiple job IDs uses **a single URI template tag**.
- An in-flight slow request is recorded by the active LongTaskTimer when sampled.
- Histogram buckets contain the expected SLO boundaries.
- Prometheus scraping succeeds without errors and series count stays under budget.
- Multi-replica aggregation computes mean/p95 accurately.
- Client disconnects and stream cancellations do not leak the active gauge indefinitely.

### Example Verification Using curl with a Path Variable

~~~bash
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/job-100?ms=1"
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/job-200?ms=1"
curl -sS -o /dev/null \
  "http://localhost:8080/api/slow/job-300?ms=1"
~~~

Check the meter by `uri`:

~~~bash
curl -sS --get \
  --data-urlencode 'tag=uri:/api/slow/{jobId}' \
  http://localhost:8080/actuator/metrics/http.server.requests
~~~

You should see `COUNT` for the shared template route increase across those requests, without three separate URI labels holding `job-100`, `job-200`, and `job-300`. Exact numbers depend on prior calls and exposure config; do not assert raw output verbatim.

## 27. Review Questions

**1.** Does `http.server.requests` count a request immediately when the request begins?

**Answer:** The Timer records when the observation finishes. To see in-flight requests, use LongTaskTimer `http.server.requests.active` (when supported by version/config).

**2.** Are `http_server_requests_seconds_count` and `http_server_requests_active_seconds_count` both cumulative counters?

**Answer:** No. The first is a monotonically increasing completed-request count; the second is a LongTaskTimer **active task count snapshot** that rises and falls.

**3.** Why not use `rate(http_server_requests_active_seconds_count[5m])` to calculate RPS?

**Answer:** Active count is a gauge of running work, not a counter of completed requests. Compute RPS from `rate(http_server_requests_seconds_count[5m])`.

**4.** How do you calculate mean latency from Prometheus?

**Answer:** Divide `sum(rate(http_server_requests_seconds_sum[5m])) / sum(rate(http_server_requests_seconds_count[5m]))` over matching labels/scopes; result is in seconds/request.

**5.** Why should service-wide p95 use histograms rather than averaging per-pod p95 values?

**Answer:** Percentiles are not aggregable by averaging. Histogram buckets can be summed across `le` and passed to `histogram_quantile` to estimate p95 across the full distribution.

**6.** If `/actuator/metrics/http.server.requests.active` returns `active=0` while Timer count is large, is the app broken?

**Answer:** Not necessarily. Very fast requests finish before the snapshot is taken; the two meters measure different states.

**7.** An HTTP/2 connection carries three active streams—does active HTTP requests equal 1?

**Answer:** No. One connection can carry multiple request streams; the request-level active metric reflects multiple active observations.

**8.** Why is a metric tag like `uri=/api/items/123` per ID dangerous?

**Answer:** Cardinality grows with the number of IDs, inflating memory and Prometheus storage. Use the route template `/api/items/{id}`.

**9.** If a client receives 502 from the gateway while origin metrics show zero 502s, is there a contradiction?

**Answer:** No. The gateway can generate 502 on upstream timeout/connection failure before the origin sends a response. Compare edge metrics and traces.

**10.** Is `http.server.requests.active` equal to Tomcat busy threads?

**Answer:** No. Async/reactive requests can stay active without occupying a worker thread, and keep-alive sockets can remain open with zero active requests.

**11.** Why evaluate cost before enabling histograms on `http.server.requests`?

**Answer:** Each bucket multiplies every combination of method/status/uri/instance, increasing time series, ingestion, and storage.

**12.** Why can `http.server.requests.active` lack the same `uri`/`status` tags as the completed Timer?

**Answer:** While a request is still running, routing and final status may not be determined yet at sample time, yielding `UNKNOWN` or different tags.

**13.** Should `management.endpoints.web.exposure.include="*"` be enabled on a public API just so Prometheus can scrape?

**Answer:** No. Expose the minimum needed (`metrics`/`prometheus`) and protect it via private networking and security controls.

**14.** Is `http_server_requests_seconds_max` the maximum latency since application startup?

**Answer:** No. Micrometer's max uses a decaying time window and can reset to 0 when no new samples arrive.

**15.** How do you tell whether rising RPS alongside rising active requests indicates overload?

**Answer:** Check latency, error rate, instance capacity, queues, CPU/thread usage, and downstream health; concurrency rising proportionally with RPS is not automatically an error.

### Extended Exercises

Using the project from Section 7:
1. Send 100 rapid requests to `/api/fast`, read the completed Timer count, and compare against Prometheus RPS over a sufficient window.
2. Send two concurrent requests `/api/slow/A?ms=10000` and `/api/slow/B?ms=10000`; scrape `http.server.requests.active` while both are running and record active snapshots and current durations.
3. After both requests complete, confirm Timer completed count and total duration increase while active count returns to baseline.
4. Send 10,000 distinct job IDs through the path template and measure label cardinality; **never use real user IDs**.
5. Toggle `percentiles-histogram`, compare `_bucket` series and total series count. Run PromQL for p95 and compare against mean latency.
6. Place the service behind a test NGINX/LB, trigger a gateway timeout, and explain why origin status/count differs from client-observed errors.
7. In a WebFlux project, replace the blocking delay with `Mono.delay` and observe active counts vs. event-loop threads, contrasting with MVC.
8. Write an error-rate alert with a traffic floor alongside a separate `up == 0` alert, then analyze low-traffic edge cases.

## 28. Official Reference Sources

- [Spring Boot 3.5 — Metrics and Observation/HTTP server instrumentation](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Actuator Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Metrics Endpoint REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/metrics.html)
- [Micrometer — Concepts: Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Concepts: Long Task Timers](https://docs.micrometer.io/micrometer/reference/concepts/long-task-timers.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Spring Framework — MVC HTTP Server Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Prometheus — Querying: Rate, Increase, Histogram Quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/)
- [Prometheus — Metric Types: Histogram](https://prometheus.io/docs/concepts/metric_types/)
- [Prometheus — Instrumentation Best Practices](https://prometheus.io/docs/practices/instrumentation/)

**Takeaway:** `http.server.requests` is a **completed Timer** for throughput, error ratios, average latency, and histogram quantiles; `http.server.requests.active` is an **in-flight LongTaskTimer** showing active observations. When monitoring HTTP, measure **consistent boundaries**, keep tag cardinality low, apply PromQL appropriate to each metric type, cross-check thread/connection/queue metrics, and secure Actuator before exposing Prometheus endpoints.
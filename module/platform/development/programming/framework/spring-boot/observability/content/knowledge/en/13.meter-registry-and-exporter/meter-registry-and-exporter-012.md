# Testing Metric Export

In the **Meter registry and exporter** chapter of the **SPRING_BOOT_OBSERVABILITY** module, **testing metric export** means verifying that a measurement recorded inside a Spring Boot application **actually reaches the intended collection destination, carries the right name/labels/units, and continues to be collected reliably**. Calling `Counter.increment()` does not prove Prometheus received the data; likewise, `/actuator/prometheus` returning HTTP 200 does not guarantee dashboards are querying the right series.

The module teaches how to set up observability using **Micrometer Observation, metrics, logs, and distributed tracing**, accounting for context propagation, cardinality, exporters, and sampling to investigate errors, latency, and real runtime behavior. This lesson focuses on the **metrics** branch and how to verify every boundary in the pipeline; logs and traces serve as corroborating signals rather than replacing metric tests.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **in-app meter testing**, **exporter testing**, **scrape/push testing**, and **backend query testing**.
2. Write unit tests for `Counter` and `Timer` using `SimpleMeterRegistry`.
3. Write Spring Boot integration tests confirming that service-created metrics appear in `/actuator/metrics` and `/actuator/prometheus`.
4. Verify backend-transformed metric names, labels, units, histograms, and counter resets.
5. Verify a Prometheus target is **UP**, scraping successfully, and delivering usable samples, rather than checking HTTP status alone.
6. Separate instrumentation errors, registry wiring, endpoint exposure/security, networking, scraper issues, and query errors.
7. Test realistic failure cases such as high-cardinality tags, missing histograms, bad authentication, and differences between metrics and trace sampling.
8. Build a verification checklist before rolling out exporters in production environments.

## 2. Defining "Export Success" at Each Layer

A measurement travels through multiple layers. Each layer can succeed or fail independently:

~~~mermaid
flowchart LR
    A["Business code calls Counter/Timer<br/>or Micrometer Observation"]
    B["MeterRegistry / metrics handler"]
    C["Backend registry<br/>e.g., Prometheus"]
    D["Actuator /prometheus<br/>endpoint"]
    E["Prometheus scrape target"]
    F["Prometheus TSDB"]
    G["PromQL / dashboard / alert"]
    A --> B --> C --> D --> E --> F --> G
~~~

With a **push** registry such as an OTLP metrics pipeline, the path from the registry runs publisher → collector → backend instead of going through `/actuator/prometheus`. The primary exercises here use Prometheus **pull/scrape** for straightforward testing.

| Verification Layer | Question | Appropriate Evidence |
| --- | --- | --- |
| **Instrumentation** | Did the measurement code actually run? | Unit tests asserting counter/timer changes when calling the service. |
| **MeterRegistry** | Was the meter registered with the exact name and tags? | `MeterRegistry.find(...)` or Actuator metrics endpoint. |
| **Exporter** | Does the registry emit backend-compatible names, units, and labels? | Raw content of `/actuator/prometheus`. |
| **Transport/scrape** | Can Prometheus connect, authenticate, and parse the payload? | Target status, `up`, scrape metrics, and scraper logs. |
| **Storage/query** | Are samples stored in the backend and queryable? | PromQL matching exact job/instance/labels. |
| **Operations** | Does the pipeline stay trustworthy across errors, restarts, and config changes? | Negative tests, scrape alerts, and post-deploy data checks. |

**Never treat a test at an upper layer as covering all lower layers.** For instance, passing unit tests does not prove an exporter is configured. Conversely, `up=1` only proves Prometheus scraped the target at that moment—it does not prove every business metric exists.

## 3. Preparing the Spring Boot Application

The examples below target **Spring Boot 3.x, Java 17+**, using Spring MVC and dependency management matching your Spring Boot version.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

A configuration **for local or protected test environments only**:

~~~yaml
spring:
  application:
    name: order-api

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: order-api
      environment: local
~~~

Explanation:

- **Actuator** provides metrics infrastructure and diagnostic endpoints.
- **Prometheus registry** exports data in a scrapeable format.
- **Exposure** controls which Actuator endpoints are published over HTTP, yet **does not replace authentication, authorization, or network policies**.
- **Common tags** identify application/environment, and must never contain request IDs or per-request variable data.

Verify whether your real environment uses a separate management port, base path, or security chain. If `spring-boot-starter-security` or a custom `SecurityFilterChain` is present, test requests must carry valid authentication. Never disable security just to make tests return HTTP 200.

### Which Endpoints to Inspect?

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` returns JSON listing recorded meters. `/actuator/prometheus` returns exporter payload for scrapers. If the app uses a dedicated management port, replace port 8080 with the management port and host.

## 4. Creating a Predictable Metric

To keep tests deterministic, use a **dedicated probe metric** with a fixed name, finite tags, and predictable measurements—independent of whether the JVM happens to run GC or how many HTTP calls the test framework fires.

Example Spring service:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class ExportProbeMetrics {

    private final MeterRegistry meters;

    public ExportProbeMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void recordSuccess() {
        meters.counter("demo.export.requests", "outcome", "success")
                .increment();

        // Controlled synthetic measurement for testing;
        // in real applications, measure actual duration.
        meters.timer("demo.export.duration", "operation", "probe")
                .record(25, TimeUnit.MILLISECONDS);
    }
}
~~~

Calling `recordSuccess()` once:

- Increments Counter `demo.export.requests` with `outcome=success` by 1.
- Records a 25 ms sample into Timer `demo.export.duration` with `operation=probe`.
- Places measurements into the `MeterRegistry` injected by Spring Boot, which distributes them to configured exporters.

In real business logic, never hardcode a 25 ms duration; wrap the call with `Timer.record(...)` or use Micrometer Observation to time the actual operation. This snippet only creates a **repeatable verification anchor** for export tests.

One mistake to avoid is replacing `outcome` with a request ID:

~~~java
// Do not do this: a new tag for nearly every request.
meters.counter("demo.export.requests", "request.id", requestId)
        .increment();
~~~

Use `outcome=success/error` because it has a small value set. High-cardinality identifiers must stay in logs or trace attributes governed by data policies, never in metric labels.

## 5. Unit Test: Is the Meter Recorded Properly?

The first test needs no web server or Prometheus. `SimpleMeterRegistry` keeps measurements in memory, ideal for unit testing instrumentation logic.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ExportProbeMetricsTest {

    @Test
    void recordsExpectedCounterAndTimer() {
        try (SimpleMeterRegistry meters = new SimpleMeterRegistry()) {
            ExportProbeMetrics probe = new ExportProbeMetrics(meters);

            probe.recordSuccess();
            probe.recordSuccess();

            assertThat(meters.get("demo.export.requests")
                    .tag("outcome", "success")
                    .counter()
                    .count()).isEqualTo(2.0);

            var timer = meters.get("demo.export.duration")
                    .tag("operation", "probe")
                    .timer();

            assertThat(timer.count()).isEqualTo(2L);
            assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
                    .isCloseTo(50.0,
                            org.assertj.core.data.Offset.offset(0.001));
        }
    }
}
~~~

From this unit test, you know:

1. Names and tags at the Micrometer layer are correct.
2. Two calls incremented the counter by two.
3. The Timer recorded two samples totaling 50 ms per test inputs.
4. No per-request dynamic labels appear in this measurement.

**Not yet proven:** Actuator endpoints are exposed, the Prometheus registry exists, the scraper has access, or the backend received samples. `SimpleMeterRegistry` does not simulate the full Prometheus pipeline.

If this test cannot find the meter, inspect your code path, meter name, tags, and passed registry. Never try to fix this by editing Prometheus scrape config: the bug sits upstream of the exporter.

## 6. Integration Test: From Spring Bean to Export Endpoint

The next step verifies **the real Spring Boot-configured registry** and Actuator HTTP endpoints. Example using Spring MVC, an existing Spring Boot application, and `spring-boot-starter-test`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "management.endpoints.web.exposure.include=health,metrics,prometheus"
    }
)
class MetricsExportIntegrationTest {

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private ExportProbeMetrics probe;

    @Test
    void exportsCustomMetricViaPrometheus() {
        // Generate data before reading the exporter.
        probe.recordSuccess();

        ResponseEntity<String> diagnostic = http.getForEntity(
                "/actuator/metrics/demo.export.requests", String.class);

        assertThat(diagnostic.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(diagnostic.getBody())
                .contains("demo.export.requests")
                .contains("COUNT");

        ResponseEntity<String> scrape = http.getForEntity(
                "/actuator/prometheus", String.class);

        assertThat(scrape.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(scrape.getBody())
                .contains("demo_export_requests")
                .contains("outcome=\"success\"");
    }
}
~~~

This test **illustrates Spring Boot 3.x**. It assumes the project has a discoverable `@SpringBootApplication`, does not move the management server to a separate port, has the Prometheus registry on the test classpath, and allows endpoint access in the test context. If Spring Security is enabled, use an authenticated test client with an authorized identity instead of disabling auth.

**Why don't assertions hardcode the entire metric line?** Actuator displays the Micrometer name (`demo.export.requests`), whereas the Prometheus exporter applies backend naming conventions (`demo_export_requests...`, potentially with suffixes like `_total`). Tests can assert essential names/labels, then tighten assertions to match your project's exact exporter version. Never rely solely on an overly broad `contains("demo")` check.

This test still needs no Prometheus server: it proves **Spring Boot generates exporter output at the HTTP endpoint**. Backend verification still happens separately.

### Notes on Test Isolation

- Use test-specific metric names and stable tags; never mutate global registries without restoring them.
- When multiple tests share a Spring `ApplicationContext`, counters can **accumulate** across tests. Avoid asserting "count equals exactly 1" in reused integration contexts, or use isolated test contexts and manage lifecycle carefully.
- Do not rely on line ordering of series, tags, or comments in Prometheus text: ordering is not a business API contract.
- If security or management ports are customized, HTTP tests must use matching URLs, credentials, TLS, and roles.
- An HTTP 200 check alone is insufficient; verify **the recorded metric appears with the right labels and units**.

## 7. Manual Inspection: Names, Tags, Units, and Values

After invoking a metered business endpoint, inspect:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/demo.export.requests
curl -s http://localhost:8080/actuator/prometheus
~~~

**Illustrative example** of Actuator output:

~~~json
{
  "name": "demo.export.requests",
  "measurements": [
    {"statistic": "COUNT", "value": 2.0}
  ],
  "availableTags": [
    {"tag": "outcome", "values": ["success"]}
  ]
}
~~~

With the Prometheus registry, a counter may export as:

~~~text
# TYPE demo_export_requests_total counter
demo_export_requests_total{outcome="success",application="order-api",environment="local"} 2.0
~~~

This only illustrates naming and formatting; verify the final format and names produced by your actual exporter version. In other cases, Actuator may list additional tags or the Prometheus exporter may place suffixes differently per naming conventions.

### Trying a Tag Filter in Actuator

~~~bash
curl -s --get \
  --data-urlencode "tag=outcome:success" \
  http://localhost:8080/actuator/metrics/demo.export.requests
~~~

The `tag=key:value` parameter filters measurements by tags. It is not PromQL and does not query Prometheus storage; Actuator reports meter state inside the queried process.

### Comparing Duration

If Timer `demo.export.duration` records two 25 ms samples:

~~~text
Expected: count=2, totalTime=50 ms=0.05 seconds
~~~

Prometheus may export `demo_export_duration_seconds_count` and `demo_export_duration_seconds_sum`. **Never** compare `0.05` seconds directly against `50` ms without converting units. Before asserting, check metric name, `baseUnit`, and actual exporter output.

## 8. End-to-End Prometheus Scrape Testing

Once the app serves the endpoint, configure Prometheus to scrape periodically. Lab example:

~~~yaml
scrape_configs:
  - job_name: "order-api"
    metrics_path: /actuator/prometheus
    scrape_interval: 15s
    static_configs:
      - targets: ["order-api.internal:8080"]
~~~

`order-api.internal` is an illustrative hostname; it must resolve from **Prometheus's network**, not just a developer's laptop. Protect the endpoint across network boundaries and, where appropriate, with TLS/authentication.

Verification steps:

1. Open Prometheus Target Status or query the targets API to find job `order-api`.
2. Confirm the target is **UP**, check the last scrape timestamp, and read any error message if DOWN.
3. Inspect scraped sample counts, scrape duration, and scrape interval to spot slow endpoints or oversized payloads.
4. Query the probe metric with exact `job`, `instance`, and labels.
5. Invoke `recordSuccess()` a controlled number of additional times, wait at least one scrape interval, and confirm the counter climbs.
6. Verify scraping after restarts or security config updates.

PromQL examples:

~~~promql
up{job="order-api"}
~~~

If `up=1`, Prometheus recently scraped the target successfully. **It does not prove `demo_export_requests_total` exists.** To verify a specific metric, query it directly:

~~~promql
demo_export_requests_total{job="order-api",outcome="success"}
~~~

Across multiple timestamps, inspect the increase:

~~~promql
increase(demo_export_requests_total{job="order-api",outcome="success"}[10m])
~~~

`increase(...)` may not equal an exact integer count because Prometheus extrapolates across samples in the window and handles counter resets. In unit tests, assert exact counts in the registry; in backend tests, check upward trends and continuity over an appropriate window rather than demanding `increase` equal an exact integer `N`.

Internal metrics generated by Prometheus, such as `up` and `scrape_duration_seconds`, **are not emitted by the application**. They signal collection health.

### Target Is UP, Yet Data Is Wrong

If the target is UP while dashboards lack the metric:

- Does the meter actually exist in the registry? Was it recorded after startup?
- Did the Prometheus exporter emit the expected name/suffix and labels?
- Is the query filtering the wrong `application`, `environment`, `instance`, or `job`?
- Is `metric_relabel_configs` in Prometheus dropping the series?
- Did a deploy change naming conventions, collectors, or registry versions?

Do not edit application business logic if the raw endpoint already outputs the right metric; inspect the scrape path and queries instead.

## 9. Testing Security and Network Boundaries

A metric exporter can expose routes, dependency names, environments, and runtime state. In production, `/actuator/prometheus` should only be reachable by authorized scrapers, never exposed casually on the public internet.

Your test suite should cover:

| Caller | Expected Access | Evidence |
| --- | --- | --- |
| Authorized Prometheus service account or scraper | Allowed to read `/actuator/prometheus`. | HTTP 200, target UP, samples present. |
| Unauthorized public user | Cannot view telemetry. | Network blocked or HTTP 401/403, per policy. |
| Operator with diagnostic permissions | Allowed to read `/actuator/metrics` when granted. | HTTP 200 with valid JSON. |
| Unauthorized identity | Cannot read endpoint or endpoint hidden. | 401/403/404 per infrastructure design. |

If the endpoint returns 401/403 to the scraper, fix **identity, roles, credentials, and TLS/networking**—never strip security just to turn the target UP. When using a separate management port, test from Prometheus's network, not only localhost on the app host.

Never put usernames/passwords directly in committed files or URLs that might be logged. For Basic auth, use it only over HTTPS or an equivalently protected transport, with least-privilege permissions for the scraper.

A critical negative test is verifying that from an unauthorized network, the endpoint **never returns 200** with metric details.

## 10. Histograms and Testing Metric Distributions

Counters and timer sum/count are usually insufficient for computing cluster-wide P95/P99 across multiple instances. If dashboards rely on histograms, verify the exporter actually emits bucket series.

Spring Boot 3.x config example:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

When histograms are active and exported by the Prometheus registry under common names, you may see:

~~~text
http_server_requests_seconds_bucket{le="0.1",...} ...
http_server_requests_seconds_bucket{le="0.5",...} ...
http_server_requests_seconds_bucket{le="+Inf",...} ...
~~~

Example P95 query:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="order-api",uri="/checkout",method="POST"
    }[5m])
  )
)
~~~

Tests must verify:

1. `_bucket` series actually exist in exporter output—not just `_sum` and `_count`.
2. Buckets use **seconds** matching the series name.
3. `uri` is a **route template**, not a URL containing a request ID.
4. Queries sum buckets by `le` and required grouping dimensions without mixing services or environments.
5. Enough samples exist in the window; at very low traffic, P95 fluctuates heavily.

Histograms multiply series counts, so test both sample volume and cardinality after enabling them. Trace sampling **does not create bucket series** and is never a fix for missing metric histograms.

## 11. Testing Cardinality and Metadata

An exporter can "succeed" by HTTP status while flooding the backend with excessive metric tags. Add data-quality assertions as well.

Example to avoid:

~~~java
registry.counter("checkout.requests", "requestId", requestId)
        .increment();
~~~

Every new request ID creates a new label combination. At 100 requests/second, 24 hours yields roughly:

~~~text
100 × 60 × 60 × 24 = 8,640,000 requests/day
~~~

If every ID differs, the `requestId` dimension alone generates millions of label values—risking memory, ingestion, index, and storage blowups.

Replace with:

~~~java
registry.counter("checkout.requests",
        "operation", "checkout",
        "outcome", "success").increment();
~~~

When inspecting payloads:

- Confirm labels have finite value sets such as `operation`, `outcome`, `method`, and normalized `uri`.
- Confirm no `requestId`, `userId`, email, token, or raw URL with identifiers appears in metric labels.
- Confirm common tags like `application` and `environment` are applied cleanly without unexpected series multiplication.
- Check series/sample counts in the backend after enabling a new metric.
- When IDs are needed to trace a specific request, put them in logs/MDC and trace attributes under privacy policies rather than metric labels.

A test validating **allowed meter names and tag keys** catches regressions before deploying an exporter.

## 12. Push Export, Composite Registries, and Differences to Test

Not every exporter works like Prometheus pull/scrape.

| Export Style | How Data Moves | Extra Testing Needed |
| --- | --- | --- |
| **Prometheus pull** | Prometheus server makes HTTP calls to the app endpoint. | Exposure, routing, auth, TLS, scrape targets, content format. |
| **Push registry** | App sends metrics periodically to a backend/collector. | Target endpoint, credentials, batch/step interval, retries, timeouts, queues. |
| **Composite registry** | One `MeterRegistry` fans out meters to multiple child registries. | Each destination receives data; names/units and tags map accurately. |
| **OTLP metrics** | Metrics export via an OTLP pipeline. | Collector receiver/exporter, resource attributes, temporality, backend mapping. |

An OTLP **metrics exporter** is separate from an OTLP **tracing exporter**. Having a working tracing exporter does not prove OTLP metrics export works. Likewise, working Prometheus scrapes do not prove traces or logs are stored.

When testing push, in addition to verifying meters in the registry, confirm the backend/collector actually receives the metric with no auth errors or dropped batches. Use a test collector or authorized staging backend; never commit real credentials into repositories.

**Composite registries and write counts:** business code increments a counter once. The registry handles fanning out measurements to child destinations; never increment twice to "send to two backends," or counts will be wrong.

## 13. Relationship to Micrometer Observation and Tracing

A custom `Observation` can produce metrics via a metrics handler and tracing spans via a tracing handler:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public void reserve(ObservationRegistry observations) {
    Observation.createNotStarted("inventory.reserve", observations)
            .lowCardinalityKeyValue("operation", "reserve")
            .observe(() -> {
                // Actual inventory reservation logic goes here.
            });
}
~~~

This snippet illustrates the API; in real code, replace the body with the actual business call. For the metric to appear:

1. The Observation must be created and completed through its proper lifecycle.
2. `ObservationRegistry` must have a matching metrics handler.
3. The handler must record into the configured `MeterRegistry`.
4. The registry/exporter must publish/expose the measurement.
5. The backend must scrape/ingest and store the data.

When tracing is also enabled, sampled operations produce spans and logs can carry `traceId`/`spanId` while context is active. Still, **a metric timer does not automatically carry per-request trace IDs**, because metrics aggregate across calls. Trace sampling may keep only a small fraction of requests; metric call counts normally do not shrink proportionally.

When traces break across an HTTP hop, check context propagation (`traceparent`), instrumentation, async context, and the tracing exporter. Fixing Prometheus metric export will not reconnect parent–child spans.

## 14. Runbook: Exporter Returns 200, Yet the Dashboard Is Blank

Suppose an operator calls `/actuator/prometheus` and sees data, yet the `order-api` dashboard does not display `demo.export.requests`.

Walk the verification chain:

1. **Application:** trigger `recordSuccess()`, check `/actuator/metrics/demo.export.requests` has the meter and expected tags.
2. **Exporter:** read raw `/actuator/prometheus` and find the Prometheus-converted name, e.g., `demo_export_requests_total`.
3. **Network:** from where Prometheus runs, check hostname, port, base path, TLS/identity, and network policies.
4. **Scraper:** check target UP/DOWN status, parse errors, timeouts, and scrape sample count; verify `metrics_path`.
5. **Backend:** query `up{job="order-api"}`, then query the bare metric name without excessive label filters.
6. **Cardinality/filters:** check metric relabeling, retention, common tags, dropped series, and filter clauses.
7. **Dashboard:** check time range, datasource, environment/job/instance variables, units, and query expression.
8. **Post-fix:** generate a few more samples, wait for scrape cycles, and confirm series and counters rise steadily.

Never change application instrumentation, exporter config, and dashboard queries all at once—you will not know which layer fixed it. Focus on finding **the first boundary in the pipeline lacking evidence**.

## 15. Quick Diagnostic Table

| Symptom | Likely Suspects to Check | How to Confirm |
| --- | --- | --- |
| Unit test misses meter | Code path not run, wrong name/tags, different registry. | `SimpleMeterRegistry.find(...)`, service invocation count. |
| Actuator `/metrics` lacks custom metric | No samples yet, meter never recorded, denied by filter. | Call probe, inspect meter names and tags. |
| `/actuator/prometheus` returns 404 | Missing Prometheus registry, endpoint unexposed/disabled, or wrong URL. | Dependencies, management port/path, exposure settings. |
| `/actuator/prometheus` returns 401/403 | Wrong caller permissions or authentication. | Spring Security/proxy rules, roles, and credentials. |
| Endpoint 200, metric absent | Meter never recorded, different registry, renamed, or filtered. | Compare Actuator JSON against raw exporter text. |
| Prometheus target DOWN | Network, TLS, auth, timeout, parse error, or wrong URL. | Targets UI/API, scraper logs, curl from Prometheus network. |
| `up=1`, query returns empty | Wrong name/suffix, job/instance, label selector, or relabeling. | Strip filters step by step; compare raw payload. |
| Timer has `_count`/`_sum`, no `_bucket` | Histogram disabled or registry/version not emitting buckets. | Inspect distribution config and raw exporter output. |
| Values drop after restart | Counter/timer reset on process restart. | Inspect instance/restart timing and use `rate()`/`increase()`. |
| Series count spikes sharply | Per-request ID, user ID, raw URL, or excessive tag dimensions. | Audit metadata and active series counts. |
| Metrics complete, traces missing | Tracing sampling/bridge/exporter/propagation differs from metrics. | Check tracing separately; cross-check with logs. |

## 16. Self-Check Exercises

### Exercise 1: What Does Each Test Prove?

`SimpleMeterRegistry` shows `demo.export.requests` incremented from 0 to 2, yet the Prometheus target is DOWN. Can you report that metric export works end-to-end?

**Answer:** No. The unit test only proves the meter records properly. You still must verify the exporter endpoint, reachability, target status, and backend queries.

### Exercise 2: Is `up=1` Enough?

Prometheus reports `up{job="order-api"}=1`, yet `demo_export_requests_total` is missing. Can you conclude the service received no requests?

**Answer:** Not enough evidence. The code may not have hit the probe, the metric may be filtered, naming may differ, the exporter may lack the meter, or backend relabeling/queries may be wrong. Check layer by layer.

### Exercise 3: Unit Mismatch

A Timer records two 25 ms samples, yet the dashboard displays a total time of 0.05 seconds. Is this an exporter bug?

**Answer:** No. `50 ms = 0.05 seconds`. Prometheus timer metrics commonly use seconds, while Java APIs may record milliseconds/nanoseconds. Check base units before filing a bug.

### Exercise 4: Authentication Failure

After enabling security, `/actuator/prometheus` returns 200 when Ops curls it manually, yet the Prometheus target reports 401. What should you do?

**Answer:** Verify the scraper's identity, credentials/roles, network/TLS path, and the exact URL it calls. Never disable auth just to turn the target UP. After fixing, verify samples land in the backend.

### Exercise 5: Testing Histograms

A dashboard uses `histogram_quantile`, yet `http_server_requests_seconds_bucket` does not exist. Can you compute cluster-wide P95 accurately by averaging per-instance P95s?

**Answer:** No. You need histograms or a compatible distribution model; never compute cluster-wide P95 by averaging P95s. Enable histograms selectively and monitor bucket series and cardinality costs.

### Exercise 6: Trace Sampling

An application processes 1,000 requests; metrics count nearly all of them, yet the trace backend stores only about 100 traces. Does this mean metrics export is broken?

**Answer:** No. Tracing may sample around 10%, while metrics aggregate all instrumented requests. The two branches have separate collection policies and exporters.

## 17. Pre-Production Metric Export Testing Checklist

- [ ] Unit tests verify counters/timers update properly when business code runs.
- [ ] Integration tests exercise the real Spring Boot registry, not only `SimpleMeterRegistry`.
- [ ] `/actuator/metrics` displays expected names, tags, and measurements.
- [ ] `/actuator/prometheus` exports exact names, labels, and units with the Prometheus registry on the classpath.
- [ ] Prometheus target is verified from the scraper's actual network with proper auth and TLS.
- [ ] Both `up=1` and direct queries for specific metrics return data—not just target health alone.
- [ ] Verified counters increase across multiple recordings and restarts/resets are handled properly.
- [ ] Histogram buckets genuinely exist if dashboards/alerts compute P95/P99.
- [ ] No request IDs, user IDs, emails, or sensitive data appear as metric tags.
- [ ] Common tags, exporter naming, and metric relabeling align with dashboards.
- [ ] Management endpoints deny telemetry to unauthorized callers.
- [ ] Alerts exist for missed scrapes, auth failures, and timeouts—not only business alerts.
- [ ] Metrics, logs, and traces are correlated in their proper roles; trace sampling is not confused with metric export.
- [ ] After deploy, verify data from every instance and in the backend over a sufficient time window.

**Key takeaway:** Testing metric export does not end at `Counter.increment()` or an HTTP 200 from `/actuator/prometheus`. A reliable verification flow runs from **accurate measurements in `MeterRegistry`**, through **accurate exporter payloads**, to **successful scrape/push delivery and queryable series**, while securing endpoints and controlling cardinality. When every layer has its own evidence, you can trust metrics to detect anomalies and pair them with logs and distributed tracing to investigate errors and latency in Spring Boot.

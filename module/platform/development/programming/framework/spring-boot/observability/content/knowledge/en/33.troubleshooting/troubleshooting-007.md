# Diagnosing Duplicate Metrics in Spring Boot

Duplicate metrics can cause dashboards to show double the actual request rate, counters to increment faster than expected, histograms to record more observations than reality, or Prometheus to store multiple series that appear to represent the same signal. In Spring Boot, the cause does not lie solely in Micrometer instrumentation. A metric can be recorded twice in code, the same application can export via multiple registries, or Prometheus can scrape the same endpoint across multiple targets.

This lesson, **Duplicate Metrics**, belongs to the **Troubleshooting** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

After this lesson, you will be able to distinguish duplicate instrumentation from duplicate scraping and duplicate export, read labels to determine whether series truly differ, locate Micrometer configurations causing double-recording, fix the proper owner of a meter, and add regression tests to prevent recurrence.

## 1. How Do Duplicate Metrics Manifest?

Common symptoms:

- Request rate or throughput nearly doubles after adding a starter or dashboard.
- A counter increases faster than the actual number of operations.
- The same metric appears on multiple rows with different labels.
- Prometheus has multiple targets pointing to the same application instance.
- A dashboard sums two series that reflect the same traffic source.
- The meter name is the same, but registries/exporters differ.
- Timer count differs from the request count recorded in access logs or tests.

Do not draw conclusions merely because two rows share the same metric name. In Prometheus, a time series is uniquely identified by its metric name plus its entire label set. Two series with the same name but different `instance`, `job`, `pod`, or `service` labels may represent two valid instances. A problem exists when the same event is recorded or scraped twice unintentionally, or when a query mistakenly sums copies together.

## 2. Classifying Three Root Cause Groups

| Group | What Is Duplicated? | Example |
| --- | --- | --- |
| Duplicate instrumentation | One operation updates meters multiple times | HTTP server instrumentation and a custom filter both increment a request counter |
| Duplicate scrape/target | The same endpoint is scraped multiple times | Two scrape jobs both pull the same Actuator endpoint |
| Duplicate export/registry | The same meter is published via multiple paths | One `MeterRegistry` is scraped by two jobs or two exporters push to the backend |

The three groups have different fixes. If instrumentation produces two increments, fix the code/handler. If Prometheus scrapes the same target twice, fix service discovery/scrape config. If the dashboard sums two export paths, choose one canonical data source or distinguish the pipelines clearly.

## 3. Start from Raw Prometheus Series

First, inspect the full label set of the suspected metric. For example:

```promql
http_server_requests_seconds_count
```

In the Prometheus UI, expand each series and compare labels such as `job`, `instance`, `service`, `pod`, `uri`, `method`, `status`, and `outcome`. Ask:

1. Do the two series share the same `job`/`instance`/`pod`?
2. Are two jobs scraping the same `host:port/path`?
3. Is the difference only a label added by relabeling?
4. Does one series come from the application registry and the other from an agent/sidecar?
5. Is the same operation instrumented twice inside one process?

Inspect the Prometheus Targets page to verify scrape URL, job, labels, last scrape, and scrape health. Do not start by dropping labels or summing series in the dashboard before identifying the source.

## 4. Detecting the Same Endpoint Being Scraped Multiple Times

If a single application endpoint appears under multiple `job`/target labels, Prometheus may be scraping it redundantly.

Count targets per instance:

```promql
count by (instance) (up{job=~".*orders.*"})
```

Find instances with more than one target:

```promql
count by (instance) (up) > 1
```

The query above is only a heuristic signal; one instance can legitimately be scraped by multiple jobs for different endpoints. Also check the metrics path, scheme, port, and target labels.

Cross-check scrape frequency and target identity on the Prometheus Targets page. Two jobs scraping the same endpoint can create two sets of series differing only by `job` label, and a dashboard doing `sum by (service)` drops the `job` label and doubles the traffic.

## 5. Duplicate Instrumentation in Spring Boot

Spring Boot Actuator/Micrometer can automatically instrument HTTP server requests, JVM, datasource, and many other integrations. If you add a custom filter/aspect measuring the same operation, two measurements can be produced for a single request.

Conceptual bug example:

```java
// Framework already records http.server.requests.
// A custom filter also increments another request counter
// for exactly the same server request.
class RequestCountingFilter {
    void afterRequest() {
        // requestCounter.increment();
    }
}
```

If the custom meter has a different name, a dashboard may sum both meters as though they were independent sources. If it shares the same meter name and tags, the count may increment twice. Establish the owner of each metric before adding instrumentation.

Principles:

- Use framework instrumentation for standard HTTP lifecycles.
- Use custom `Observation`s for business operations not already measured by the framework.
- Do not create a custom counter merely to duplicate the built-in server request count.
- Choose distinct names when two metrics measure different semantics.

## 6. @Timed and @Observed Measuring the Same Method

A common mistake is adding both `@Timed` and `@Observed` to the same method intending to enable both metrics and tracing. `@Observed` can create an `Observation` handled by both metrics and tracing handlers; `@Timed` can create a separate `Timer` via AOP. Depending on setup, one operation may record two `Timer`s or emit semantically overlapping measurements.

Example needing review:

```java
@Service
class OrderService {
    @Timed("orders.process")
    @Observed(name = "orders.process")
    public void process(Order order) {
        // business operation
    }
}
```

Not every configuration creates the exact same meter, yet this case must be reviewed carefully. Pick one instrumentation owner for the operation. If you need `Observation` to emit both metrics and spans, use `@Observed` with appropriate handlers; if you only need a simple duration `Timer`, use `@Timed`.

## 7. Checking Multiple Filters, Aspects, and Interceptors

An HTTP request can pass through servlet filters, Spring MVC interceptors, AOP aspects, and framework instrumentation. If multiple layers create request timers, inspect which lifecycle each layer measures.

Checkpoints:

- Is a filter registered both as a component and via `FilterRegistrationBean`?
- Is a filter added to both the security chain and the servlet container?
- Do two `WebMvcConfigurer` beans register the same interceptor?
- Do annotation AOP and a custom aspect both intercept the method?
- Is an operation instrumented at both controller and service layers with the same name/tags?
- Do test configuration and production configuration share the same bean registrations?

An operation may legitimately have parent/child observations across different layers. Only classify it as a duplicate when two instruments measure the same boundary/semantics and are summed as a single metric.

## 8. Multiple MeterRegistry Instances and CompositeMeterRegistry

Micrometer can use multiple registries: Prometheus, OTLP, StatsD, or in-memory registries. `CompositeMeterRegistry` lets a meter be registered into multiple child registries. This is a valid design when each registry serves a distinct backend.

However, avoid:

- Registering the same registry bean twice.
- Creating a custom registry outside the Spring context alongside an auto-configured registry.
- Attaching the same registry to a composite multiple times.
- Exporting the same registry to a backend via two scrape jobs.
- Running agent instrumentation alongside a Micrometer bridge for the same signal without clear ownership.

Multiple registries do not necessarily mean the meter is incremented multiple times inside the application. A single meter update can fan out to multiple registries; duplication occurs when those copies feed back into the same query/backend and get summed as multiple sources.

## 9. Distinguishing Duplicate Series from Label Cardinality

High cardinality creates many distinct series, which is not automatically duplication. Example:

```text
http_server_requests_seconds_count{uri="/orders/1",status="200"}
http_server_requests_seconds_count{uri="/orders/2",status="200"}
```

These two series differ by URI and may reflect two valid requests; however, raw URIs containing IDs create unbounded cardinality. Duplicate scraping typically produces identical measurement content with differing labels such as `job`/`replica`; duplicate instrumentation can produce the same series with abnormally high counts.

Distinguish:

- **Duplicate:** the same event or source is recorded/exported multiple times.
- **High cardinality:** one metric has too many label combinations.
- **Legitimate multiplicity:** multiple instances genuinely receive separate traffic.

Do not resolve duplication by arbitrarily stripping labels. Doing so can merge valid data or obscure instance-level behavior.

## 10. Cross-Checking Against Actual Request Volume

Pick a time window with easily identifiable traffic and compare:

- HTTP access log count (ensure logs are not sampled/dropped).
- Micrometer HTTP server request `Timer` count.
- Prometheus scrape target count.
- Gateway/load balancer request count.
- Application-level business operation count.

These figures do not have to be equal: gateways may count retries, access logs may record probes, application metrics only record requests after entering the server, and a business operation may run multiple times per request. Compare using matching scope and semantics.

One verification method is sending `N` requests from a test client to an isolated instance, then confirming the `Timer` count increases by roughly `N` at the expected instrumentation boundary. Exclude health probes, retries, and background calls from the fixture.

## 11. Queries to Isolate Doubled Metrics

Compare request counts by job:

```promql
sum by (job) (
  increase(http_server_requests_seconds_count[10m])
)
```

Compare by job and instance:

```promql
sum by (job, instance) (
  increase(http_server_requests_seconds_count[10m])
)
```

Find series sharing business labels across different scrape jobs:

```promql
count by (service, instance, uri, method, status) (
  http_server_requests_seconds_count
)
```

The final query only shows how many series remain after removing `job` and certain labels. If the result exceeds 1, check whether the dropped labels distinguish two legitimate scrape sources; this alone is not conclusive proof of duplication.

To verify whether a counter increments twice, run a test workload with a known request volume and compare `increase()` against requests sent in the same time window, keeping scrape intervals and counter resets in mind.

## 12. Fixing at the Exact Source of Duplication

| Root Cause | Fix Direction |
| --- | --- |
| Custom filter duplicates HTTP server metric | Remove custom counter or change to an operation metric with distinct semantics |
| `@Timed` and `@Observed` both instrument method | Pick one instrumentation owner |
| Filter registered twice | Keep a single registration path |
| Duplicate Prometheus scrape jobs | Consolidate scrape config or remove duplicate target |
| Service discovery creates two targets for same endpoint | Fix relabeling/selector/annotations |
| Same registry attached to composite multiple times | Fix bean wiring and registry lifecycle |
| Agent and Micrometer both instrument HTTP | Pick one source or clearly separate signals |
| Dashboard sums multiple export pipelines | Pick one canonical source or filter by pipeline |

After fixing, verify raw series and the target list before modifying dashboard queries. If you merely edit the query to divide the count in half, the root cause remains and other dashboards stay broken.

## 13. Regression Tests for Duplicate Metrics

Tests should prove that one operation creates exactly one measurement at the chosen boundary:

| Test | What to Prove |
| --- | --- |
| Single request test | `N` requests create exactly `N` HTTP server observations per scope |
| Filter registration test | Custom filter is registered only once |
| AOP test | One method is not double-measured by two aspects |
| Observation handler test | One operation creates the expected number of `Observation`s |
| Meter registry test | Timer/counter count increments exactly once |
| Composite registry test | Meter fans out properly to child registries without duplicate child registration |
| Prometheus scrape config test | One endpoint has one canonical target for the intended job |
| Dashboard query test | Query does not sum the same pipeline twice |

Example meter count test using `SimpleMeterRegistry`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class RequestMetricTest {
    @Test
    void incrementsCounterOncePerRecordedOperation() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Counter counter = registry.counter("orders.processed");

        counter.increment();

        assertThat(counter.count()).isEqualTo(1.0);
    }
}
```

This is a basic meter test, not a substitute for an integration test of real filters/aspects. A complete test should invoke the application boundary, capture meters from the Spring-managed registry, and verify counts after each invocation.

## 14. Common Mistakes

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| HTTP request count nearly doubled | Framework and custom filter both counting | Check filters/interceptors and server instrumentation |
| Series repeated under two `job` labels | Prometheus scrapes the same endpoint twice | Check Targets page and scrape configs |
| `@Observed` creates extra timer after adding `@Timed` | Two AOP instrumentations on the same method | Capture meter names/counts and pick one owner |
| Only one dashboard is doubled | Query sums two pipeline/export sources | Check `job`/agent/registry labels |
| Count doubles after adding an agent | Agent and Micrometer both instrument | Define ownership for HTTP/JDBC/tracing |
| Many series, each with normal count | High cardinality or multiple instances | Check labels and route templates |
| Metrics differ from access logs | Scope includes probes/retries or log sampling | Align scope and semantics |
| Composite registry exports twice | Child registry registered redundantly | Check bean graph and registry lifecycle |
| Timer count is high while business count is low | HTTP retries or method called multiple times | Compare server boundary and business operation |
| Dividing query by half still wrong | Only masks symptom on dashboard | Fix underlying instrumentation or scrape source |

## 15. Real-World Scenario: Request Rate Doubles After Adding a Monitoring Agent

**Hypothetical scenario:** After deploying a monitoring agent, the `orders-service` dashboard jumps from 500 to nearly 1,000 requests/second. The load balancer and access logs still show around 500 requests/second.

Investigation workflow:

1. **Inspect raw series:** compare `job`, `instance`, `pod`, `uri`, and `method`; determine whether two series exist from two pipelines or one series' count doubled.
2. **Inspect targets:** open the Prometheus Targets page and look for two scrape URLs pointing to the same pod's management endpoint.
3. **Inspect the agent:** check whether the agent automatically instruments the HTTP server and exports the same metric family.
4. **Inspect application beans:** review recently added custom filters, `MeterRegistry` beans, and `Observation` handlers.
5. **Isolate:** send `N` requests to a test instance and capture meter counts in each registry.
6. **Fix ownership:** keep one canonical HTTP instrumentation/export path or cleanly separate pipelines via explicit labels if two backends are truly required.
7. **Verify:** target count returns to expected, request rate matches traffic source, and dashboards no longer sum duplicate series.

Do not assume the agent is the root cause solely because timing coincided with deployment. Prove which data path created or scraped the duplicate.

## 16. Self-Check Exercises

**Exercise 1.** Are two series with the same metric name always duplicates?

*Hint:* No. A Prometheus series' identity consists of the metric name and the full label set; two different instances can be valid.

**Exercise 2.** How does duplicate instrumentation differ from duplicate scraping?

*Hint:* Instrumentation records measurements multiple times inside the process; duplicate scraping reads the same endpoint across multiple targets/jobs.

**Exercise 3.** Why does placing `@Timed` alongside `@Observed` require review?

*Hint:* Both can instrument the same method and produce overlapping duration measurements depending on handlers/aspects.

**Exercise 4.** Does `CompositeMeterRegistry` mean a meter is incremented multiple times?

*Hint:* Not necessarily. A single update fans out to child registries; problems arise if the same data is re-collected/exported and summed as multiple sources.

**Exercise 5.** How do you detect that the same endpoint is being scraped twice?

*Hint:* Compare Prometheus targets, scrape URL, `job`, `instance`, metrics path, and labels.

**Exercise 6.** Why shouldn't you divide a metric by two in the dashboard to fix duplication?

*Hint:* It masks the root cause and breaks whenever traffic or the number of pipelines changes.

**Exercise 7.** Are multiple URI labels a duplicate metric?

*Hint:* Not necessarily; it may be high cardinality from raw URIs. Use route templates and inspect each label set.

**Exercise 8.** Which test proves HTTP instrumentation records only once?

*Hint:* Send a known number of requests to a test instance, capture registry meter counts, and verify filter/aspect registrations.

## 17. Key Takeaways

- Duplicate metrics can come from duplicate instrumentation, duplicate Prometheus scraping, or duplicate export/query aggregation; identify the category before fixing.
- A Prometheus series is identified by its metric name plus full label set; sharing a metric name does not mean the same series.
- Spring Boot Actuator/Micrometer already provides extensive instrumentation; custom filters/aspects should measure operations with distinct semantics.
- Carefully review `@Timed`, `@Observed`, filters, interceptors, agents, registries, and `Observation` handlers to avoid measuring the same boundary twice.
- `CompositeMeterRegistry` fans out meter updates to multiple registries; inspect wiring/export paths before concluding a counter increment is duplicated.
- Use raw series, the Prometheus Targets page, and `job`/`instance`/`pod` labels to separate scrape duplication from legitimate instances.
- Do not patch dashboards by halving counts or stripping labels before fixing the source generating duplicate data.
- Write regression tests at the application boundary and registry, and review scrape configs/dashboard queries to keep duplicates from returning.

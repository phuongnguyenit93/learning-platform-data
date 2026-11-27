# Tracking Failure Rate, Slow Calls, and Execution Duration

A circuit breaker only helps protect a system when operations teams can observe what state it is in, how dependencies are responding, and how long calls take. With Spring Cloud CircuitBreaker using Resilience4j, metrics can be exported via Micrometer, Spring Boot Actuator, and collection systems such as Prometheus. Key metrics include failure rate, slow-call rate, successful/failed/not-permitted call counts, and execution duration of protected calls.

When monitoring, separate three perspectives: **dependency health**, **circuit breaker behavior**, and **business request experience**. The circuit breaker's failure rate does not necessarily equal the application's overall HTTP 5xx rate; likewise, the supplier timer does not necessarily include fallback execution time or controller processing. Measuring the right boundaries ensures dashboards reflect root causes rather than just a single aggregate number.

## 1. Questions Observability Must Answer

A circuit breaker dashboard should help answer:

- Is each per-dependency breaker in `CLOSED`, `OPEN`, `HALF_OPEN`, or a special state?
- How many calls actually ran, and how many were rejected before touching the dependency?
- What are the current failure rate and slow-call rate in the sliding window?
- Is execution duration for successful and failed calls increasing or decreasing?
- Is the fallback being invoked frequently, and is the fallback completing successfully?
- Are business requests still slow or returning errors to users even though the circuit breaker is blocking the dependency?

Do not display only the `OPEN` state. State tells you the breaker is blocking calls; error rates, latency, and rejection counts explain why it opened and how severely the business flow is affected.

## 2. Distinguishing the Core Metrics

| Metric | Meaning | How to Read It |
| --- | --- | --- |
| `failureRate` | Percentage of calls recorded as failed in the sliding window | Rises when the dependency throws exceptions configured to be recorded |
| `slowCallRate` | Percentage of calls exceeding `slowCallDurationThreshold` in the sliding window | Can rise even when calls still ultimately succeed |
| `numberOfSuccessfulCalls` | Number of calls recorded as successful | Shows the count of successful samples in the window |
| `numberOfFailedCalls` | Number of calls recorded as failed | Excludes exceptions configured to be ignored |
| `numberOfBufferedCalls` | Total results stored in the window | Shows whether enough samples exist relative to `minimumNumberOfCalls` |
| `numberOfNotPermittedCalls` | Number of calls rejected by the breaker | Shows traffic blocked when the breaker denies execution |
| `state` | Current state of the breaker | Cross-reference against rates and rejection counts |
| Call duration | Execution time of the protected call | Analyze average latency, plus p95/p99 if histograms are enabled |

Failure rate is generally understood by the formula:

\[
\text{failureRate} = \frac{\text{failed calls}}{\text{successful calls} + \text{failed calls}} \times 100\%
\]

Exceptions configured as ignored are not counted as either successful or failed. Calls rejected while the breaker is `OPEN` are also not failed dependency calls because the supplier never runs. Therefore, do not add `not permitted` to the failure rate denominator.

`slowCallRate` is calculated separately:

\[
\text{slowCallRate} = \frac{\text{slow calls}}{\text{successful calls} + \text{failed calls}} \times 100\%
\]

A single call can be both slow and failed. When that happens, it contributes to both statistics; do not sum the two rates together. Rates are used to trigger state decisions only after `minimumNumberOfCalls` is reached.

Before the minimum number of samples is reached, Resilience4j may return `-1` to indicate insufficient data for evaluation. Dashboards should display an "insufficient samples" state instead of interpreting `-1` as a negative error rate or replacing it with `0%`.

## 3. Enabling Micrometer and Spring Boot Actuator

With Spring Boot, add Actuator, Resilience4j's Micrometer module, and a registry for your monitoring system. Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-micrometer</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
```

Manage Spring Boot, Spring Cloud, and Resilience4j versions via a compatible BOM or dependency management. Do not mix versions from different release trains just to pull in a newer Micrometer version.

Resilience4j integrates with Micrometer to register meters for circuit breakers. With Spring Boot integration, configure the backend and registry by instance ID. Example:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when_authorized
  metrics:
    tags:
      application: ${spring.application.name}
    distribution:
      percentiles-histogram:
        resilience4j.circuitbreaker.calls: true
```

`resilience4j.circuitbreaker.instances.inventory` defines the breaker being monitored. `management.metrics.tags.application` adds an application label to distinguish instances in the monitoring system. A timer histogram enables collecting latency distributions instead of only sum and count; verify Micrometer and backend distribution settings to make sure histogram buckets are exported.

After the application starts, inspect available meters via Actuator `GET /actuator/metrics` and view a specific meter via `GET /actuator/metrics/{metric-name}`. Prometheus scrapes `/actuator/prometheus` once the corresponding registry is present. Exact meter names and tags depend on Micrometer/Resilience4j versions; use the application's actual meter list as your reference when building dashboards.

## 4. Resilience4j Meters to Observe

With Micrometer integration, circuit breaker meters typically take the form:

| Meter | Type | Purpose |
| --- | --- | --- |
| `resilience4j.circuitbreaker.calls` | Timer | Counts calls by outcome kind and records execution duration |
| `resilience4j.circuitbreaker.state` | Gauge | Represents current state via the state tag |
| `resilience4j.circuitbreaker.failure.rate` | Gauge | Current failure rate in the sliding window |
| `resilience4j.circuitbreaker.slow.call.rate` | Gauge | Current slow-call rate in the sliding window |
| `resilience4j.circuitbreaker.buffered.calls` | Gauge | Current number of samples in the window |
| `resilience4j.circuitbreaker.slow.calls` | Gauge | Number of slow calls by outcome group |

The `resilience4j.circuitbreaker.calls` timer usually includes a `name` tag identifying the breaker and a `kind` tag distinguishing `successful`, `failed`, or `not_permitted`. Gauge meters include the `name` tag; the state meter includes a tag representing the state. Metric names are converted according to registry conventions—for example, dots may become underscores in Prometheus.

Verify which tags are actually emitted in the version you use. Do not hardcode assumptions about converted metric names if the application uses a custom naming convention or a different registry.

## 5. Measuring Execution Duration and Latency Percentiles

The circuit breaker timer helps analyze execution duration at the protected call boundary. Total duration divided by sample count gives average latency, but averages can hide a group of very slow requests. When histograms are enabled, also track p50, p95, and p99.

Interpretation examples:

| Observation | Possible Meaning |
| --- | --- |
| p50 stable, p95 spikes sharply | A subset of requests experiences tail latency, possibly due to pools, network, or overloaded dependency |
| Both p50 and p95 rise together | Most calls are slow; the dependency may be experiencing widespread degradation |
| p95 rises while failure rate has not increased | The dependency still returns responses, but slowly; slow-call rate may open the breaker before errors appear |
| Supplier duration is low, but HTTP request time is high | Time is spent outside the supplier, such as queuing, fallback, serialization, or application processing |

The circuit breaker timer typically measures the wrapped execution. If a fallback runs after the supplier throws an exception or the breaker rejects a call, fallback time should not be mistaken for dependency response time. To measure end-to-end experience, also use web-layer request metrics such as `http.server.requests` or dedicated business metrics.

## 6. Prometheus Query Examples

A Micrometer Timer is commonly exported as series such as `resilience4j_circuitbreaker_calls_seconds_count`, `_sum`, and `_bucket`. Verify exact names at `/actuator/prometheus`.

The failure rate of executed calls over the last five minutes can be calculated as failed calls divided by total successful and failed calls:

```promql
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m])
)
/
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_count{kind=~"successful|failed"}[5m])
)
```

The query above computes a traffic-based ratio over a five-minute window. It does not necessarily match the `failureRate` used by the breaker for state decisions, because the breaker evaluates its own sliding window with its own size and type. When traffic is zero, division may yield no samples or undefined values; dashboards should handle zero-traffic cases gracefully.

Average latency of successful and failed calls:

```promql
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_sum{kind=~"successful|failed"}[5m])
)
/
sum by (name) (
  rate(resilience4j_circuitbreaker_calls_seconds_count{kind=~"successful|failed"}[5m])
)
```

If histograms are enabled and buckets are exported, p95 can be calculated as:

```promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(resilience4j_circuitbreaker_calls_seconds_bucket{kind=~"successful|failed"}[5m])
  )
)
```

Do not include `not_permitted` as samples for dependency latency because the supplier does not execute in that case. You can build a separate chart for rejections by counting or taking the rate of the meter with `kind="not_permitted"`, after verifying how the metric is exported in your version.

## 7. Separating Dependency, Fallback, and End-to-End Request Metrics

A business request can pass through many steps: controller, validation, circuit breaker, client, fallback, response mapping, and serialization. A single metric cannot explain all of them.

Include at least three metric groups:

| Group | Where to Measure | Questions Answered |
| --- | --- | --- |
| Circuit breaker/dependency | Supplier wrapped by the breaker | Is the dependency succeeding, failing, or slow? Is the breaker blocking requests? |
| Fallback | Fallback function or backup handler | How many requests use fallback? Does fallback complete successfully? |
| Business request | Web server or API layer | How long do users wait, and how many error responses do they receive? |

For example, an `OPEN` breaker may keep the dependency failure rate from climbing further because the supplier stops running, while `not_permitted` counts rise. If the fallback quickly returns cached data, end-to-end requests can still succeed. Dashboards should show all three events: the dependency previously degraded, the breaker is currently blocking, and the application is serving via fallback.

You can use a dedicated Micrometer `Counter` to record fallbacks. Example:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class FallbackMetrics {

    private final MeterRegistry meterRegistry;

    public FallbackMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void recordInventoryFallback(String reason) {
        meterRegistry.counter(
            "application.fallback.calls",
            "dependency", "inventory",
            "reason", reason
        ).increment();
    }
}
```

Use only bounded tag values such as `open`, `timeout`, or `dependency_error`. Never pass user IDs, order IDs, full URLs, or exception messages as tags because each new value creates a distinct time series and increases cardinality. Detailed context belongs in structured logs and traces, not metric labels.

## 8. Recording State Transitions and Events

Metrics reveal trends; events explain a specific state transition. Resilience4j provides an event publisher for each circuit breaker:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryCircuitBreakerEvents {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryCircuitBreakerEvents.class);

    public InventoryCircuitBreakerEvents(CircuitBreakerRegistry registry) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        breaker.getEventPublisher()
            .onStateTransition(event ->
                log.info("inventory circuit breaker state transition: {}", event))
            .onCallNotPermitted(event ->
                log.warn("inventory call not permitted: {}", event))
            .onError(event ->
                log.warn("inventory call failed: {}", event));
    }
}
```

Register listeners once during the application lifecycle, not on every request. If instances are created by a separate Spring Cloud factory, verify that the registry in the example manages the exact breaker being invoked; do not create a standalone registry assuming its events reflect the factory's state. You can use a customizer or the integration mechanism of your Spring Cloud CircuitBreaker version to attach listeners to the underlying instance.

State transition logs should include the breaker ID, previous and new states, and timestamp. Where possible, include trace ID or correlation ID in request logs instead of turning those IDs into metric tags. Event listeners must not log sensitive payloads or exception messages containing personal data.

## 9. Organizing Dashboards by Dependency

A practical dashboard can be structured into rows:

1. **State:** current state, count of `CLOSED` → `OPEN` transitions, time spent in `OPEN`, and `not_permitted` count.
2. **Reliability:** failure rate, slow-call rate, successful/failed call counts, and sample count in the window.
3. **Latency:** p50/p95/p99 of protected calls compared with `slowCallDurationThreshold` and client timeouts.
4. **Resilience:** fallback count, fallback completion rate, and probe counts in `HALF_OPEN`.
5. **User impact:** request rate, latency, and response codes of the API calling the dependency.

Keep one panel or dashboard per critical dependency while using consistent naming conventions and units. Overlay configured thresholds alongside metric lines so viewers understand why current rates trigger state transitions.

## 10. Alerting on Symptoms, Not State Alone

Useful alerts include:

- Breaker remains `OPEN` longer than operationally expected.
- `not_permitted` spikes suddenly, indicating many requests are being blocked.
- Failure rate exceeds threshold over a sustained interval with sufficient traffic.
- Slow-call rate or p95 continuously exceeds latency objectives.
- Fallback rate rises sharply or fallbacks themselves begin failing.
- End-to-end requests show rising latency or 5xx errors despite the breaker protecting the dependency.

Avoid alerting based on a single isolated error sample. At low traffic, a single error can produce a 100% rate in a small window without representing a widespread outage. Combine sample count, sustained duration, breaker state, and impact on business requests. Choose evaluation intervals aligned with `slidingWindowType`, `slidingWindowSize`, and SLO targets.

## 11. Securing Observability Endpoints

Actuator `metrics` and `prometheus` endpoints can reveal internal dependency names, application structure, and traffic patterns. Expose only required endpoints, restrict access within the monitoring network, and apply authentication/authorization if reachable from outside a trusted network. Do not expose `env` or `configprops` publicly merely for debugging convenience.

When using Prometheus, configure scraping over an internal network and avoid putting credentials into labels. In multi-instance environments, attach `application`, `environment`, and `instance` labels following operational conventions; avoid high-cardinality labels like request IDs.

## 12. Investigation Workflow for Metric Anomalies

When failure rate or slow-call rate increases, follow this sequence:

1. Identify the breaker ID and its current state.
2. Check sample counts in the sliding window and `minimumNumberOfCalls`.
3. Compare failure rate with slow-call rate to tell whether the dependency is failing or simply slow.
4. Inspect call duration p95/p99 along with logs and traces at the anomaly timestamp.
5. Check `not_permitted` counts to see how many requests the breaker is blocking.
6. Correlate fallback metrics with end-to-end request latency and response codes.
7. Inspect timeouts, exception classification, client pools, network, and dependency health.

If the breaker is `OPEN` while failure rate stops rising, that can be expected behavior: the supplier is blocked so no new dependency results update the rate. If the fallback rate is high while API requests still succeed, the system may be sustaining service via fallback data; evaluate data staleness and business acceptability.

## 13. Testing Metrics and Events

In integration tests, verify meters appear after executing successful, failed, slow, and rejected calls. With `SimpleMeterRegistry`, you can verify meters without running Prometheus:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CircuitBreakerMetricsTest {

    @Test
    void recordsCallsAndStateMetrics() {
        SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
        CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        TaggedCircuitBreakerMetrics.ofCircuitBreakerRegistry(registry)
            .bindTo(meterRegistry);

        breaker.executeRunnable(() -> { });

        assertThat(meterRegistry.find("resilience4j.circuitbreaker.calls")
            .tag("name", "inventory")
            .timer()).isNotNull();
        assertThat(meterRegistry.find("resilience4j.circuitbreaker.state")
            .tag("name", "inventory")
            .gauges()).isNotEmpty();
    }
}
```

This example illustrates the concept; metric binding APIs and emitted tags can differ across Resilience4j versions. In your project, use the API corresponding to your managed version and verify actual meter tags. Beyond meters, test state transition events when open conditions are met and call-not-permitted events when calling in the `OPEN` state.

## 14. Observability Rules

- Track failure rate and slow-call rate separately; never merge them into a single error rate.
- Monitor sample counts and breaker state alongside rates to avoid drawing conclusions from very low traffic.
- Measure breaker call duration and end-to-end API latency using separate metrics.
- Track `not_permitted` separately because blocked calls are not failed dependency calls.
- Measure fallback rate and fallback outcomes to know how the application sustains service.
- Enable histograms when p95/p99 is needed and verify actual buckets in Prometheus.
- Use low-cardinality tags; put request details into logs and traces.
- Secure Actuator endpoints and emit structured state transition events.

By combining metrics, events, logs, and traces, development teams can determine whether a dependency is failing, running slowly, or already blocked by the circuit breaker—while also knowing whether fallbacks and business requests maintain service quality. This provides the evidence needed to tune sliding windows, error thresholds, timeouts, and fallback policies based on the real behavior of a Spring Cloud system.

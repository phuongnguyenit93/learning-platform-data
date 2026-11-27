# Integrating Actuator, resilience4j-micrometer, and Metrics Collection Systems

A Circuit Breaker only protects a service effectively when development and operations teams understand what state it is in, how many calls succeed or fail, whether the slow-call rate is rising, and how frequently the fallback is being used. If you only configure thresholds in `application.yml` without collecting metrics, it is very difficult to know whether those thresholds fit actual traffic or whether the Circuit Breaker is opening too often.

Spring Boot Actuator provides administrative and application observability endpoints. Micrometer standardizes how metrics are recorded and forwarded to monitoring systems. Resilience4j provides the `resilience4j-micrometer` module to export metrics for Circuit Breaker, Retry, Bulkhead, and other resilience mechanisms. Prometheus can periodically scrape these metrics, while Grafana uses the data to build dashboards and alerts.

This lesson explains how to connect those components in a Spring Cloud CircuitBreaker application using Resilience4j, how to read metrics, how to monitor state, and how to secure Actuator endpoints when deploying the application to production.

## 1. Metrics Collection and Visualization Architecture

In an Order application calling Inventory through a Circuit Breaker, the observability flow can be organized as follows:

~~~text
Order Service
  |
  +--> CircuitBreaker "inventory"
  |       |
  |       +--> state, calls, failure rate, slow-call rate
  |
  +--> Spring Boot Actuator
          |
          +--> Micrometer MeterRegistry
                    |
                    +--> Prometheus registry
                              |
                              v
                         /actuator/prometheus
                              |
                              v
                         Prometheus server
                              |
                              v
                         Grafana dashboard
                         Alerts / notifications
~~~

Each component has its own responsibility:

- **Resilience4j** records the results and states of resilience mechanisms.
- **resilience4j-micrometer** converts that data into meters with standardized names and tags.
- **Micrometer** provides a common API so the application does not depend directly on the format of a specific monitoring system.
- **Spring Boot Actuator** manages the metrics, health, and Prometheus endpoints.
- **Prometheus** scrapes metrics from application instances at regular intervals.
- **Grafana** queries data from Prometheus to display trends, dashboards, and alerts.

Metrics differ from logs and traces. Metrics are suited for aggregating trends over time; logs help investigate a specific event; traces show the path and timing of a request across multiple services. All three should be combined when operating distributed systems.

## 2. Preparing Dependencies

In a Spring Boot application using Spring Cloud CircuitBreaker with Resilience4j, you need Actuator and Resilience4j's metrics module. If you want Prometheus to scrape the application's endpoint directly, add Micrometer's Prometheus registry.

Maven dependency example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
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
~~~

Versions should be managed using Spring Boot dependency management and a compatible Spring Cloud BOM. Do not manually choose separate Spring Cloud, Resilience4j, and Micrometer versions without checking the project's compatibility matrix.

Spring Boot Actuator already brings Micrometer core into the dependency graph, so you usually do not need to declare `micrometer-core` directly. The `resilience4j-micrometer` module provides the adapter from Resilience4j metrics to Micrometer. The Prometheus registry provides the scrape format that Prometheus understands.

If the application only needs to view metrics locally via Actuator, you do not necessarily need to add the Prometheus registry. If the monitoring system uses another backend such as OTLP, Datadog, or another registry supported by Micrometer, add the corresponding registry and configure the exporter for the environment.

## 3. Configuring Circuit Breaker and Actuator

Example `application.yml` for a Circuit Breaker named `inventory`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  endpoint:
    health:
      show-details: when_authorized

  health:
    circuitbreakers:
      enabled: true

  metrics:
    tags:
      application: order-service
~~~

The Circuit Breaker configuration creates a sliding window of the 20 most recent calls and requires at least 10 samples before evaluating rates. A failure rate or slow-call rate reaching 50% can transition the circuit to OPEN. These thresholds are illustrative values only and must be tuned based on the dependency's normal latency, traffic volume, and reliability objectives.

In the Actuator section:

- `health` provides the application's health status.
- `info` provides configured application information.
- `metrics` allows inspecting available meters and tags.
- `prometheus` exports data in Prometheus scrape format.

The Prometheus endpoint only appears when `micrometer-registry-prometheus` is on the classpath. The `metrics` and `prometheus` endpoints do not necessarily display the same names: Micrometer normalizes meter names according to the target registry's conventions.

Only expose the endpoints that are actually needed. By default, Spring Boot only exposes `health` over HTTP. Do not open all endpoints with `*` on a public network.

## 4. How Does Resilience4j Automatically Register Metrics with Micrometer?

When using Spring Cloud CircuitBreaker Resilience4j with the right dependencies, auto-configuration can set up metrics collection automatically. The key dependencies are:

- `spring-boot-starter-actuator`
- `resilience4j-micrometer`

Spring Cloud CircuitBreaker Resilience4j includes metrics auto-configuration when the required dependencies are present. You do not need to create a second `MeterRegistry` or manually bind to the same registry if auto-configuration already handles it.

For applications using Resilience4j directly without the corresponding auto-configuration, you can bind the registry using Resilience4j's API:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.micrometer.tagged.TaggedCircuitBreakerMetrics;
import io.micrometer.core.instrument.MeterRegistry;

public class CircuitBreakerMetricsConfiguration {

    public void bindMetrics(
            CircuitBreakerRegistry circuitBreakerRegistry,
            MeterRegistry meterRegistry) {

        TaggedCircuitBreakerMetrics
            .ofCircuitBreakerRegistry(circuitBreakerRegistry)
            .bindTo(meterRegistry);
    }
}
~~~

`TaggedCircuitBreakerMetrics` registers metrics for instances in the registry and can track instances created later through the registry's event mechanism. Only use manual binding when the application does not have an equivalent auto-configuration mechanism. Binding the same registry multiple times can cause duplicate meters or meter name registration errors.

When the application uses Spring Cloud's `CircuitBreakerFactory`, keep using the registry and provider managed by Spring configuration. Do not create an independent `CircuitBreakerRegistry` solely to read metrics, because that registry may not contain the instances protecting business calls.

## 5. Key Circuit Breaker Metrics

Resilience4j provides many meters. Exact names and tags may vary by module version, but common metric groups include:

| Metric | Data Type | Meaning |
| --- | --- | --- |
| resilience4j.circuitbreaker.calls | Timer | Count and duration of successful, failed, or ignored calls |
| resilience4j.circuitbreaker.state | Gauge | Current state of the Circuit Breaker |
| resilience4j.circuitbreaker.failure.rate | Gauge | Percentage of failed calls in the evaluation window |
| resilience4j.circuitbreaker.slow.call.rate | Gauge | Percentage of slow calls in the evaluation window |
| resilience4j.circuitbreaker.buffered.calls | Gauge | Number of successful and failed calls currently stored in the window |
| resilience4j.circuitbreaker.max.buffered.calls | Gauge | Maximum number of samples for the current window |
| resilience4j.circuitbreaker.not.permitted.calls | Counter | Number of calls rejected because the Circuit Breaker does not permit execution |

Meters typically include a `name` tag to identify the instance. The `calls` metric also includes a `kind` tag to distinguish `successful`, `failed`, and `ignored`. The `state` metric includes a `state` tag to distinguish `closed`, `open`, `half_open`, and special states supported by the version.

For example, `inventory` is the instance name declared in `application.yml`. When viewing metrics, filter by `name=inventory` so you do not accidentally combine metrics from Payment or Shipping.

Do not infer state from a single counter alone. For instance, an increase in failed calls may indicate that a dependency is experiencing errors, but you also need to examine the failure rate, total sample count, slow-call rate, and current state to understand the situation.

## 6. Reading Metrics via Actuator

Once Actuator is enabled and the `metrics` endpoint is exposed, you can list available meters:

~~~bash
curl http://localhost:8080/actuator/metrics
~~~

Look up a Circuit Breaker meter:

~~~bash
curl http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.calls
~~~

The endpoint returns measurements and filterable tags. For example, querying only the `inventory` instance and failed calls:

~~~bash
curl "http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.calls?tag=name:inventory&tag=kind:failed"
~~~

You can check the state:

~~~bash
curl "http://localhost:8080/actuator/metrics/resilience4j.circuitbreaker.state?tag=name:inventory&tag=state:open"
~~~

If a meter does not exist, check the following in order:

1. Whether Actuator is on the classpath.
2. Whether `resilience4j-micrometer` is on the classpath.
3. Whether Spring Cloud CircuitBreaker is using the Resilience4j provider.
4. Whether the `inventory` instance has been created and has received calls.
5. Whether the `metrics` endpoint is exposed.
6. Whether any configuration disables Spring Cloud CircuitBreaker Resilience4j metrics.
7. Whether you are inspecting the wrong registry or the wrong instance name.

Meter names in the Actuator endpoint use Micrometer naming format. Names displayed in Prometheus may be normalized to lowercase with underscores. When querying Actuator, use the meter name returned by the `/actuator/metrics` endpoint.

## 7. Exporting Metrics for Prometheus

Prometheus operates on a scrape model: the Prometheus server periodically calls an endpoint on each application instance to collect metrics. Add the `micrometer-registry-prometheus` dependency and expose the `prometheus` endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Verify the endpoint from a machine with access:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

If configured correctly, the response contains metric lines in Prometheus format. A Micrometer meter name like `resilience4j.circuitbreaker.calls` may be converted to `resilience4j_circuitbreaker_calls_seconds_count` and related series according to Prometheus naming rules.

Example scrape configuration in `prometheus.yml`:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service:8080
~~~

In Docker or Kubernetes environments, targets must use a hostname and port that Prometheus can actually reach. Do not use `localhost` in Prometheus configuration if the application runs in another container, because `localhost` then points to the Prometheus container itself.

If Actuator endpoints are on a separate management port, `metrics_path` and `targets` must use the management port. If the endpoint requires authentication, configure Prometheus to send credentials via a secret or appropriate security mechanism; never write credentials directly into configuration files committed to the repository.

## 8. Building Dashboards Around Operational Questions

A good dashboard answers specific questions rather than merely displaying lots of charts. For a Circuit Breaker, include the following areas:

| Dashboard Area | Metrics to Display | Operational Question |
| --- | --- | --- |
| State | State per instance | Which dependency is OPEN or HALF_OPEN? |
| Traffic | Calls by kind and instance | How many calls are succeeding or failing? |
| Error Rate | Failure rate and slow-call rate | How severely is dependency quality degrading? |
| Rejections | Not permitted calls | How many requests are being blocked by the Circuit Breaker? |
| Latency | Call duration and HTTP client latency | Are requests slow at the Circuit Breaker or at the HTTP layer? |
| Fallback | Fallback count per dependency | How often are users receiving degraded responses? |
| Resources | Threads, connection pools, bulkhead rejections | Is a dependency incident exhausting caller resources? |

Do not monitor only the OPEN state. A Circuit Breaker may transition to OPEN briefly and recover while the failure rate or slow-call rate remains elevated. Dashboards should show trends over time and allow drill-down by instance name.

Include a summary table for each dependency covering state, failure rate, slow-call rate, rejected calls, and fallback counts. When protecting multiple instances, instance names must remain stable so dashboards and alerts do not create a new series after each deployment.

## 9. Prometheus Query and Alert Examples

After successful scraping, Prometheus stores time series. The names below illustrate normalized forms produced from Micrometer; confirm the actual names and tags at the application's Prometheus endpoint.

OPEN state for Inventory:

~~~promql
resilience4j_circuitbreaker_state{
  name="inventory",
  state="open"
} == 1
~~~

Rate of failed calls over 5 minutes:

~~~promql
rate(
  resilience4j_circuitbreaker_calls_seconds_count{
    name="inventory",
    kind="failed"
  }[5m]
)
~~~

Current failure rate:

~~~promql
resilience4j_circuitbreaker_failure_rate{
  name="inventory"
}
~~~

You can create an alert when the Circuit Breaker stays OPEN continuously:

~~~yaml
groups:
  - name: circuit-breaker-alerts
    rules:
      - alert: InventoryCircuitBreakerOpen
        expr: resilience4j_circuitbreaker_state{name="inventory",state="open"} == 1
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: Inventory Circuit Breaker is OPEN
          description: Requests to Inventory are being rejected by the circuit breaker.
~~~

Alerts should be tied to clear operational actions. For example, when Inventory stays OPEN continuously, the on-call engineer can inspect Inventory health, HTTP error rates, latency, network connectivity, and rejected request counts. Do not alert solely on a very brief state transition if the system recovers quickly without user impact.

When alerting on failure rate, add a minimum sample condition or rely on the Circuit Breaker metric after `minimumNumberOfCalls` has been met. A 100% rate from a single sample can cause noisy alerts if request volume is not considered.

## 10. Health Indicators and Application Status

Actuator health and Circuit Breaker metrics serve different purposes:

- The `health` endpoint returns health status based on configured `HealthIndicator`s and health groups.
- Metrics provide continuous measurements of calls, error rates, and states.
- Readiness indicates whether an instance should receive new traffic.
- Liveness indicates whether the process is alive and can keep running.

Resilience4j can register a health indicator for a Circuit Breaker via `registerHealthIndicator`. When the health indicator is enabled, an OPEN state can cause the Circuit Breaker component to report DOWN and affect the overall status of `/actuator/health`.

Consider this carefully before enabling it in production. An OPEN `inventory` dependency does not necessarily mean the Order process itself is dead. If Order can still serve other features or return a controlled fallback, marking the entire application DOWN may cause the platform to remove the instance from traffic, creating a wider outage.

Do not include dependency state in the liveness probe. If you need it for readiness, decide based on the instance's business capability and design a dedicated health group. You can keep liveness independent of the Circuit Breaker while using metrics and alerts for operations teams to monitor dependencies.

Example showing health indicator configuration as an intentional choice:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        registerHealthIndicator: true

management:
  health:
    circuitbreakers:
      enabled: true
~~~

Verify the state mapping for your version of the Resilience4j Spring Boot integration and confirm the impact on the health endpoint before including this configuration in a readiness probe.

## 11. Monitoring Retry, Bulkhead, TimeLimiter, and HTTP Client

A Circuit Breaker does not operate alone. If an application combines multiple policies, dashboards should make the boundaries of each mechanism clear.

| Mechanism | Metrics to Monitor |
| --- | --- |
| Retry | Calls succeeding on first attempt, succeeding after retry, failing after exhausting attempts |
| Bulkhead | Calls currently holding permits, rejected calls, thread pool and queue usage |
| TimeLimiter | Timeouts, completion duration, and canceled tasks if applicable |
| HTTP client | Request count, response status, latency, connection timeout, and response timeout |
| Circuit Breaker | State, calls, failure rate, slow-call rate, and not-permitted calls |

As retries increase, the Circuit Breaker's failure rate can be interpreted differently depending on policy wrapping order. If the Circuit Breaker sits inside Retry, each attempt may record a sample. If the Circuit Breaker wraps outside Retry, it typically receives the final outcome of the retry chain. Dashboards should show both attempt count and request count to avoid confusion.

If Bulkhead frequently rejects calls while the Circuit Breaker remains CLOSED, the caller may have exhausted its concurrency budget before the dependency is judged as failing. If TimeLimiter timeouts rise alongside the slow-call rate, inspect response times and timeout budgets. Observing multiple metrics together helps pinpoint the bottleneck layer.

## 12. Combining Metrics, Logs, and Distributed Tracing

Metrics show how many errors occur and how trends change; logs and traces help find the root cause of a specific request.

A useful log entry may include:

- Circuit Breaker instance name.
- Previous and new state on transition.
- Event type: `success`, `error`, `call not permitted`, or `state transition`.
- Correlation ID or trace ID if available.
- Dependency name and business route.
- Exception class sanitized of sensitive information.

You can register event listeners on the Circuit Breaker to record state transitions:

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

inventory.getEventPublisher()
    .onStateTransition(event ->
        log.warn(
            "CircuitBreaker inventory state changed: {}",
            event.getStateTransition()
        )
    )
    .onCallNotPermitted(event ->
        log.warn("CircuitBreaker inventory rejected a call")
    )
    .onError(event ->
        log.debug(
            "CircuitBreaker inventory recorded an error",
            event.getThrowable()
        )
    );
~~~

Do not log every successful call at WARN or ERROR level. Under high traffic, logging every event can generate substantial load and storage cost. Use metrics to aggregate successes; log important events such as state transitions, mass rejections, or unexpected errors.

Traces should be created at request boundaries and propagated through an instrumented HTTP client. With a trace ID in logs, operators can locate the corresponding span to see whether latency occurred at the gateway, HTTP client, or target service. Never put access tokens, cookies, or secrets into tags, logs, or trace attributes.

## 13. Avoiding High Cardinality and Sensitive Data

Micrometer uses tags to group metrics. Tags with an unbounded number of values can create hundreds of thousands or millions of time series, increasing Prometheus memory usage and cost.

Appropriate tags typically include:

- `application` or service name.
- Dependency or Circuit Breaker instance name.
- Operation name with a finite set of values.
- `outcome` or `kind`.
- `environment` or `region` with a bounded list.

Avoid using the following values as metric tags:

- User ID or customer ID.
- Order ID or transaction ID.
- Correlation ID or trace ID.
- Full URLs containing path variables.
- Exception messages or arbitrary request data.

High-cardinality values belong in logs or traces with suitable retention and query policies. Likewise, never record access tokens, refresh tokens, passwords, session cookies, or secrets in logs or metrics.

The `application` tag in the `application.yml` example has a fixed value:

~~~yaml
management:
  metrics:
    tags:
      application: order-service
      environment: production
~~~

Do not name instances per request or per user. An instance name like `inventory` makes sense; `inventory-user-123` or `inventory-order-456` creates too many meters and defeats per-dependency management.

## 14. Securing Actuator Endpoints

Actuator endpoints can expose information about the application, resources, configuration, and traffic. While the `metrics` endpoint typically does not contain access tokens, it can still reveal dependency names, internal errors, states, and load patterns. Endpoints such as `env`, `configprops`, `heapdump`, or `threaddump` can expose even more sensitive data or deeper operational details.

Key security principles:

1. Expose only necessary endpoints such as `health`, `info`, `metrics`, and `prometheus`.
2. Place management endpoints on an internal network or a dedicated management port where appropriate.
3. Protect endpoints with Spring Security, an internal gateway, network policies, or platform authentication.
4. Restrict read access to metrics and detailed health views by role.
5. Never expose all endpoints with `*` on the public internet.
6. Use secret management for Prometheus or collector credentials.
7. Verify exposed endpoints after each deployment to ensure extra endpoints were not accidentally opened.

You can configure the management server on a separate port:

~~~yaml
management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Binding to loopback is only suitable when Prometheus or a collection agent runs on the same host. In Kubernetes or containerized environments, use separate network policies and services so only the monitoring system is allowed access.

If endpoints are accessed from another network, do not rely solely on changing the port for security. Use TLS, authentication, and network access controls suited to your infrastructure.

## 15. Verification Workflow from Application to Dashboard

After completing configuration, verify step by step to isolate issues at the right layer:

1. Confirm the application starts with Actuator, `resilience4j-micrometer`, and the Prometheus registry dependencies.
2. Send successful requests through the `inventory` Circuit Breaker.
3. Trigger some failed or slow requests so the Circuit Breaker records samples.
4. Call `/actuator/metrics` and confirm the `resilience4j.circuitbreaker.calls` meter is present.
5. Query the meter with `name=inventory` and appropriate `kind` tags.
6. Call `/actuator/prometheus` and confirm Circuit Breaker series are exported.
7. Verify the Prometheus target is UP and receiving fresh data.
8. Build a Grafana dashboard showing state, failure rate, slow-call rate, calls, and not-permitted calls.
9. Perform a controlled circuit opening test and verify the dashboard and alerts reflect the state.
10. Restore the dependency and observe `HALF_OPEN` followed by `CLOSED`.
11. Verify Actuator endpoints are accessible only to authorized components.
12. Verify tags do not contain request IDs, user IDs, or sensitive data.

If the Prometheus target is UP but lacks Circuit Breaker metrics, the scraper may be hitting the right endpoint while Resilience4j metrics are not bound. If Actuator `metrics` has data but Prometheus does not, check the `prometheus` endpoint exposure, registry dependency, scrape path, port, and access permissions. If the dashboard shows an unusually high number of series, check tag cardinality.

## 16. Common Issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Missing `/actuator/prometheus` endpoint | Missing `micrometer-registry-prometheus` or endpoint not exposed | Add the registry dependency and expose `prometheus` |
| `/actuator/metrics` lacks Resilience4j meters | Missing `resilience4j-micrometer` or auto-configuration inactive | Check dependencies and the Resilience4j provider |
| Missing `calls` metric for `inventory` | Instance not created yet or no calls passed through it | Verify instance name and request flow |
| Duplicate meters registered | Both auto-configuration and manual code bind the same registry | Keep only one metrics registration mechanism |
| Prometheus target DOWN | Wrong host, port, path, TLS, or authentication | Check scrape target and endpoint reachability from Prometheus |
| Dashboard shows different metric names | Registry normalizes names per Prometheus conventions | Inspect raw exposition output at `/actuator/prometheus` |
| Health turns DOWN when Circuit Breaker is OPEN | Circuit Breaker health indicator contributes to overall health | Revisit indicator setting and health group design |
| Alert spikes unexpectedly | Threshold too low or sample count too small | Combine failure rate with traffic volume and `for` duration |
| Prometheus has too many time series | Tags contain user IDs, request IDs, or continuously changing values | Use tags with a finite set of values |
| Metrics endpoint publicly accessible | Overly broad exposure or network policy | Restrict endpoints, add authentication, and segment networks |

## 17. Operational Principles

- Use Actuator to expose only the required observability endpoints.
- Use `resilience4j-micrometer` to export metrics from the exact Circuit Breaker registry protecting calls.
- Use a single metrics binding mechanism; avoid duplicate registration.
- Use Prometheus or an appropriate Micrometer backend to store time-series data.
- Use Grafana to monitor state, failure rate, slow-call rate, rejections, and fallbacks.
- Combine metrics with logs and traces to investigate specific requests.
- Configure alerts with sufficient hold duration and sample counts to avoid noisy alerts.
- Do not let an OPEN Circuit Breaker automatically fail liveness for the entire application if it can still serve other functions.
- Avoid high-cardinality tags and never put secrets into metrics.
- Protect Actuator endpoints with authentication and network controls.

Actuator, Micrometer, and `resilience4j-micrometer` form the telemetry pipeline from the Circuit Breaker to the monitoring system. When meters are bound to the right instances, Prometheus scrapes cleanly, and dashboards display both state and error rates, operations teams can recognize degrading dependencies, evaluate protection thresholds, and handle incidents based on data. Restricting endpoints, controlling tags, and combining metrics with logs and tracing keeps observability effective while remaining safe in production.

## References

- [Spring Cloud CircuitBreaker — Collecting Metrics](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/collecting-metrics.html)
- [Resilience4j Micrometer](https://resilience4j.readme.io/docs/micrometer)
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Actuator Endpoints and Exposure](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)

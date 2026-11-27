# Integrating Micrometer and Version-Compatible Observability Tools

A Spring Data Relational R2DBC application needs observability across multiple layers: HTTP requests, business logic, repositories/queries, the connection pool, the JVM, and the database. Micrometer provides a unified API for recording metrics and observations; Spring Boot Actuator auto-configures many observability components; registries and tracing bridges forward telemetry to Prometheus, OpenTelemetry, or other monitoring backends.

However, observability capabilities depend on your versions of Spring Boot, Spring Framework, Spring Data Relational, Micrometer, R2DBC SPI, and drivers. Having HTTP metrics does not mean SQL is instrumented; having a connection pool does not mean every query has a span; adding a new Micrometer dependency does not guarantee compatibility with your current BOM.

This lesson explains how to select and align versions, distinguish metrics from observations/traces/logs, enable Actuator, observe the R2DBC pool and repositories, create business metrics/observations, export telemetry to Prometheus or OpenTelemetry, protect sensitive data, and verify instrumentation against the real driver and database.

## 1. What Is Observability?

Observability is the ability to infer the internal state of a system from the telemetry it emits. For a reactive API using R2DBC, we need to answer questions such as:

- Which requests are slow?
- Is time spent in HTTP, service logic, queries, or waiting for connections?
- Is the connection pool exhausted, or are many requests waiting?
- Did queries fail due to constraints, timeouts, or lost connections?
- Which services did a request pass through?
- How did error rates and latency change after a deployment?
- Is the database or JVM overloaded?

Three foundational telemetry types:

| Data Type | Question Answered | Example |
|---|---|---|
| Metrics | How is overall health changing over time? | Request rate, p95 latency, pool pending |
| Traces | Which steps did a specific request go through? | HTTP span, service span, database span |
| Logs | What specific event or error occurred, and in what context? | Constraint violation, timeout, retry |

The three types complement one another. Metrics reveal rising error rates; traces locate the slow request and segment; logs provide exception details and error codes for root-cause analysis.

~~~text
Client request
     |
     v
HTTP server observation / metric
     |
     v
Business operation observation
     |
     v
Repository / SQL instrumentation (if supported)
     |
     v
R2DBC connection pool metrics
     |
     v
Database
     |
     +---- metrics ----> MeterRegistry ----> Prometheus
     |
     +---- traces -----> Micrometer Tracing -> OTLP backend
     |
     +---- logs -------> Logging system (trace/span correlation)
~~~

Not every layer is instrumented automatically. Determine what telemetry Spring Boot provides out of the box, what comes from Spring Data/drivers, and what the application must add itself.

## 2. What Components Make Up Micrometer?

Micrometer is an observability facade for Java. It provides an API allowing applications to record telemetry without coupling directly to a specific metrics backend.

Common components:

- **MeterRegistry:** manages and stores meters such as `Counter`, `Timer`, `Gauge`, and `DistributionSummary`.
- **ObservationRegistry:** creates and manages `Observation` instances; an observation can produce metrics and spans depending on registered handlers.
- **Micrometer Observation:** a unified model for an operation with start/end times, name, context, key-values, and errors.
- **Micrometer Tracing:** a unified tracing API connecting to bridges like Brave or OpenTelemetry.
- **Registry/exporter:** forwards meters to Prometheus, OTLP, Graphite, or other backends.
- **Context propagation:** supports carrying context across thread/reactive boundaries when the corresponding integration is enabled.

Metrics and Observations are related, not identical. One `Observation` can be handled by multiple handlers, such as one creating a `Timer` and another creating a span. A standalone `Timer` does not automatically create a distributed trace.

## 3. Aligning Spring Boot, Spring Data, and Micrometer Versions

When integrating observability, start with the Spring Boot BOM in use. The BOM manages a set of versions tested together, including Spring Framework, Spring Data, Micrometer, and many related dependencies.

Do not upgrade Micrometer or Spring Data independently just to get a new API without verifying compatibility. Mixing generations can lead to `NoSuchMethodError`, `ClassNotFoundException`, unconfigured beans, or silent instrumentation failures.

### 3.1. Generations to Distinguish

| General Generation | Observability Characteristics | Approach |
|---|---|---|
| Spring Boot 2.x / Spring Framework 5.x | Actuator and Micrometer metrics are the common foundation; Observation API is not uniformly integrated like Boot 3 | Use BOM-managed dependencies/versions; verify tracing capabilities for your stack |
| Spring Boot 3.x / Spring Framework 6.x | Micrometer Observation becomes the unified observability foundation; includes Micrometer Tracing integration | Use Actuator, registries, and bridges compatible with the BOM |
| Newer Spring Boot/Spring Framework generations | APIs, auto-configuration, registries, and exporters may evolve | Follow documentation for your exact release train; do not mechanically apply old examples |

This table describes generation boundaries, not a full compatibility matrix for every patch release. Spring Boot 3.x also spans multiple minor releases where capabilities were added incrementally. For instance, certain repository or client observation features may require newer Spring Data/Spring Framework versions than Boot 3.0's baseline.

Before writing code, record:

1. Spring Boot version.
2. Spring Framework version selected by the BOM.
3. Spring Data Relational version.
4. R2DBC SPI and driver versions.
5. Micrometer Core/Observation/Tracing versions.
6. Registry or exporter versions.
7. Java version.

Inspect the dependency tree to catch transitive libraries pulling in mismatched Micrometer versions. With Gradle, check dependency insight for `micrometer-core`, `micrometer-observation`, and registries. With Maven, inspect the dependency tree and effective POM.

### 3.2. Do Not Mix Legacy Metrics APIs with New Observations Arbitrarily

In older stacks, applications might use `MeterRegistry`, `Timer`, `Counter`, and a separate tracing integration. When migrating to Observation, you do not have to delete all custom metrics immediately. You can keep meaningful metrics and add Observations for key business boundaries.

However, avoid recording the same operation twice via different aspects or filters, which produces duplicate metrics and skewed counts. Verify actual meter and span names after enabling instrumentation.

### 3.3. Do Not Pin Micrometer Independently When Managed by Spring Boot

Minimal Gradle example for an application using Spring Boot dependency management:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Add registry only when required by the backend.
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Do not declare separate versions if the Spring Boot BOM already manages those artifacts. If you need a Micrometer feature only available in a newer release, check the compatibility matrix and consider upgrading Spring Boot together.

## 4. Enabling Spring Boot Actuator

Actuator provides endpoints and auto-configuration for health, metrics, info, and management/observability features.

Dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Example configuration:

~~~yaml
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
      application: order-service
~~~

`prometheus` is only available when a suitable Prometheus registry is on the classpath. Without adding the registry, this endpoint will not be created.

Never expose all Actuator endpoints to the public Internet. Endpoints like `env`, `configprops`, `beans`, `heapdump`, or `loggers` can reveal configuration and internal state. Only expose the endpoints actually needed and restrict access using network policies, authentication, authorization, or a dedicated management port.

### 4.1. Health vs. Metrics

Health answers whether a component is currently up/available. Metrics measure trends and load. A passing database health check does not mean query latency is good; an active metrics endpoint does not prove the database is ready.

Key states to distinguish:

- **Liveness:** is the process alive and able to keep running?
- **Readiness:** is the instance ready to accept traffic?
- **Dependency health:** is the database or dependent system reachable?

Do not tie every dependency error to liveness in a way that causes the orchestrator to continuously restart instances during a brief database disconnect. Readiness is usually more appropriate for pausing traffic while a dependency is unavailable, depending on architecture.

## 5. Built-in Spring Boot Metrics

When Actuator and Micrometer are configured, Spring Boot typically provides metrics for the HTTP server, JVM, process, system, and supported components.

| Category | Example Common Meter Names | Meaning |
|---|---|---|
| HTTP server | `http.server.requests` | Request counts, durations, and outcomes |
| JVM memory | `jvm.memory.used`, `jvm.memory.max` | Heap/non-heap memory |
| JVM threads | `jvm.threads.live` | Live thread count |
| Garbage collection | `jvm.gc.*` | GC activity |
| Process | `process.cpu.usage`, `process.uptime` | Process CPU and uptime |
| System | `system.cpu.usage`, `system.load.average.1m` | OS load |
| Logback | `logback.events` | Log counts by level if binder enabled |
| Repository | Meters/observations per Spring Data version capabilities | Repository call durations and outcomes if instrumented |

Meter names and tags can vary across Spring Boot/Micrometer generations, registries, and configurations. Query `actuator/metrics` or inspect the live registry instead of hardcoding dashboards to unverified names.

### 5.1. HTTP Server Metrics

`http.server.requests` typically shows:

- Request counts by route/method/status.
- Processing time.
- Latency distribution.
- Success/error outcomes.

Use route templates like `/api/orders/{id}` rather than actual URIs containing IDs. If the URI tag includes per-request IDs, metric cardinality grows with every request.

### 5.2. Histograms and Percentiles

A `Timer` can provide count, total time, and max; histograms/percentiles require configuration tailored to the registry and workload.

Example distribution configuration for HTTP requests:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
      slo:
        http.server.requests: 100ms,300ms,1s,3s
~~~

Property names and SLO syntax must be verified against your Micrometer/Spring Boot version. Histograms create additional time series; enable them only for meters you need to monitor and weigh storage costs.

Do not rely on average latency alone. A few very slow requests can be hidden by many fast requests. Track p50/p95/p99 or appropriate histogram buckets.

## 6. Observing the R2DBC Connection Pool

R2DBC typically uses a connection pool to reuse connections. While the pool runs, you need to know:

- How many connections are currently leased to callers?
- How many connections are open/allocated in total?
- How many connections are idle?
- How many requests are waiting to acquire?
- Is acquire wait time increasing?
- Are connections timing out or failing validation?

With `r2dbc-pool`, Spring Boot/Micrometer can expose pool metrics depending on version and how `ConnectionFactory` is configured.

Commonly encountered pool meters include:

| Meter Group | Meaning |
|---|---|
| `r2dbc.pool.acquired` | Connections currently acquired/in use |
| `r2dbc.pool.allocated` | Connections allocated by the pool |
| `r2dbc.pool.idle` | Idle connections |
| `r2dbc.pool.pending` | Requests waiting for a connection |

Exact names, units, tags, and auto-registration depend on `r2dbc-pool`, Spring Boot, and Micrometer versions. Confirm via `/actuator/metrics` or registry scrapes.

Example pool configuration:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 30m
~~~

These properties are examples; use them only when your driver and Spring Boot configuration support pooling. Do not copy connection limits without comparing against the database session limit and application replica count.

### 6.1. Interpreting Pool Metrics

Common signals:

- `pending` rising steadily: requests are waiting for connections; the pool may be too small, queries/transactions too long, or the database unresponsive.
- `acquired` near `max-size` for extended periods: the connection pool is frequently saturated.
- `idle` near 0 alongside rising `pending`: check connection hold times and workload.
- `allocated` fluctuating abnormally: connection creation or validation may be experiencing issues.
- Rising acquire timeouts: callers cannot obtain connections within the deadline.

Do not immediately increase `max-size`. If the database is already overloaded, adding connections can worsen lock contention, CPU, and memory pressure. Check query duration, transaction duration, database capacity, and replica count first.

### 6.2. Calculating Total Connections When Scaling Out

If each instance has a pool max of 20 connections and the system runs 8 replicas, the application can request up to 160 connections, excluding migrations, jobs, or other services.

Estimation formula:

\[
\text{Max total connections}
=
\text{pool max-size per instance}
\times
\text{instance count}
+
\text{non-application connections}
\]

Budget according to database limits. Pool size is a system-wide decision, not just a number in a YAML file.

## 7. Metrics and Observations at the Repository/R2DBC Layer

Distinguish at least three instrumentation boundaries:

1. **Repository invocation:** repository method call duration and outcome.
2. **Database client/query:** statement execution time, operation type, and permitted query metadata.
3. **Connection pool:** wait time and connection resource states.

A Spring Data version may provide repository observations without automatically generating detailed spans for every SQL statement. Spring Framework `DatabaseClient` may have its own instrumentation depending on release and `ObservationRegistry` setup. Raw R2DBC SPI or driver-specific calls may bypass those abstractions altogether.

Therefore, do not infer that having repository metrics means you have query traces, or that having HTTP traces means database spans are being created.

### 7.1. Repository Instrumentation Depends on Spring Data Version

Spring Data Commons/Relational added observability across different releases. Check documentation for your exact version to determine:

- Do repository methods create Observations?
- Are Observations enabled by default, or do they require registry/configuration?
- Can observation conventions be customized?
- Which tags are created: repository, method, outcome, exception?
- Are reactive repositories measured over subscription duration or only method return time?
- Are tracing spans supported, or only meters?

A key characteristic of reactive repositories is that methods return `Mono`/`Flux` before the query executes. Proper instrumentation measures the publisher lifecycle from subscription to complete/error/cancel. A timer that only measures publisher creation time will not reflect database latency.

### 7.2. DatabaseClient and SQL Observations

If your Spring Framework/Spring Data version supports `DatabaseClient` observations, confirm `ObservationRegistry` is wired into the builder/auto-configuration the application actually uses.

If constructing a custom `DatabaseClient`, do not assume it inherits registries from other beans automatically. Use the Spring Boot-managed builder or bean configuration per your version's documentation.

SQL statements and bind values can contain sensitive data. Avoid adding full dynamic SQL, emails, tokens, or user parameters as metric tags or span attributes. If query identity is needed, use a stable operation name or normalized query category.

### 7.3. Raw R2DBC Drivers and Instrumentation

If the application calls `ConnectionFactory`, `Connection`, or `Statement` directly or uses custom wrappers/proxies, repository/`DatabaseClient` instrumentation may be bypassed.

Driver-specific metrics, an R2DBC proxy listener, or custom Observations may be required. Verify wrapper ordering: pool, proxy, transaction-aware connection factory, and Spring Data must be layered properly so transaction context or metrics are not lost.

Do not wrap `ConnectionFactory` arbitrarily and expect the transaction manager, dialect resolver, and pool binder to recognize the wrapper as the underlying driver. Run integration tests after modifying wrappers.

## 8. Adding Business Metrics with MeterRegistry

Technical metrics show how HTTP and the database behave; business metrics show how many orders, payments, or reservations the application processes.

Example incrementing a `Counter` after successfully saving an order:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;
    private final Counter createdOrders;

    public OrderService(
            OrderRepository repository,
            MeterRegistry meterRegistry) {
        this.repository = repository;
        this.createdOrders = meterRegistry.counter("orders.created");
    }

    public Mono<Order> create(Order order) {
        return repository.save(order)
                .doOnSuccess(saved -> {
                    if (saved != null) {
                        createdOrders.increment();
                    }
                });
    }
}
~~~

`Mono`'s `doOnSuccess` can also receive `null` when the publisher completes empty, so the example checks `saved != null`. If the operation always emits an entity on success, `doOnNext` can be used.

This counter increments after the repository publisher succeeds. If an outer transaction has not committed yet, the metric could increment before final transaction commit. If you need to count only committed orders, place the metric at a post-commit boundary or emit it from a post-commit event/outbox.

### 8.1. Measuring Reactive Publisher Completion Time

Do not measure time by calling `Timer.record()` around `Mono` construction, because the query has not necessarily run at that point.

Measure the publisher lifecycle with `Timer.Sample` inside `Mono.defer`:

~~~java
public Mono<Order> create(Order order) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return repository.save(order)
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "success";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancelled";
                        default -> "other";
                    };

                    sample.stop(meterRegistry.timer(
                            "orders.create.duration",
                            "outcome",
                            outcome));
                });
    });
}
~~~

This example uses modern Java switch expressions; on older Java versions, use if/else or a helper method. Each subscription creates its own sample, and `doFinally` records completion, error, or cancellation.

If the publisher runs inside a caller-managed transaction, this duration only measures the repository step inside this method. It does not necessarily include the outer transaction commit. Choose the boundary you want to measure and place the timer there.

## 9. Creating Observations for Business Operations

Observation is well-suited when you want a single operation to produce both metrics and traces depending on configured handlers.

Example creating an observation around a publisher:

~~~java
public Mono<Order> submit(SubmitOrderCommand command) {
    return Mono.defer(() -> {
        Observation observation = Observation.start(
                "orders.submit",
                observationRegistry);

        return orderService.submit(command)
                .doOnError(observation::error)
                .doFinally(signal -> observation.stop());
    });
}
~~~

The observation is created inside `Mono.defer`, giving each subscription its own lifecycle. It stops when the publisher completes, errors, or is cancelled.

This example measures a business boundary. If you need to propagate the parent observation/span and baggage across the entire Reactor chain, use context propagation integrated with your Spring/Micrometer version; do not create an Observation and assume every downstream operator picks up the context automatically. Inspect your tracing backend to verify actual parent-child relationships.

### 9.1. Using @Observed or @Timed When Appropriate

Micrometer provides annotations such as `@Observed` and `@Timed` in corresponding generations. However, annotations do not work automatically in every application:

- `@Observed` typically requires `ObservedAspect` and proper AOP setup if using proxy-based annotations.
- `@Timed` may require `TimedAspect` or corresponding auto-configuration.
- Self-invocation bypasses proxies.
- For reactive methods, verify whether the aspect measures until the terminal signal or only until the method returns the publisher.
- Avoid applying aspects alongside filters/repository instrumentation that measure the same operation twice.

For reactive publishers, instrumentation must attach to the subscription lifecycle. Check Micrometer/Spring Boot documentation for your exact version and test complete/error/cancel cases.

## 10. Exporting Metrics to Prometheus

The Prometheus registry can expose metrics through an Actuator endpoint.

Dependency:

~~~kotlin
dependencies {
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

The Prometheus scrape endpoint is typically:

~~~text
/actuator/prometheus
~~~

Example Prometheus scrape configuration:

~~~yaml
scrape_configs:
  - job_name: order-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - order-service:8080
~~~

In production environments, targets and ports must follow your deployment platform's networking and service discovery. Protect endpoints with internal networking or authentication; never expose metrics endpoints publicly if they disclose topology and operational details.

### 10.1. Checking Metrics via Actuator

Useful endpoints:

- `/actuator/health`
- `/actuator/metrics`
- `/actuator/metrics/http.server.requests`
- `/actuator/metrics/jvm.memory.used`
- `/actuator/prometheus`

Specific meter names depend on enabled instrumentation. If `/actuator/metrics` does not list an expected meter, inspect registries, binders, auto-configuration, and profiles rather than assuming Prometheus will generate data on its own.

### 10.2. Application and Environment Tags

Fixed tags like `application`, `region`, and `environment` help filter dashboards. Never add tags with nearly unbounded values.

A reasonable tag set might include:

- `application=order-service`
- `environment=staging`
- `region=ap-southeast-1`
- `operation=create-order`
- `outcome=success|error|cancelled`

Ensure tag values come from a finite, controlled set.

## 11. Tracing with Micrometer Tracing and OpenTelemetry

Metrics tell you an endpoint is slow; traces show where time was spent across each step of a specific request.

In Spring Boot generations supporting Micrometer Tracing, applications typically combine:

- Micrometer Tracing API.
- A bridge to Brave or OpenTelemetry.
- An exporter sending spans to a backend.
- Context propagation across Reactor.
- HTTP and supported client instrumentation.

Example OpenTelemetry-oriented dependencies in a Boot stack that manages them:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Artifacts and versions must be verified against your Spring Boot BOM and tracing generation. Do not mix Brave and OpenTelemetry bridges in the same configuration without a specific design.

### 11.1. A Trace Can Contain Multiple Spans

~~~text
Trace: POST /api/orders
 |
 +-- HTTP server span
      |
      +-- order.submit
      |     |
      |     +-- validate order
      |     |
      |     +-- repository.save
      |            |
      |            +-- database query span (if instrumented)
      |
      +-- HTTP response
~~~

Not every node appears automatically. If the driver/`DatabaseClient`/repository lacks instrumentation, the trace may contain only the HTTP span or business spans. Use the tracing backend to verify actual spans rather than relying on an expected diagram.

### 11.2. Sampling

Tracing every request can incur significant CPU, network, and storage costs. Sampling selects a fraction of traces to export.

- Lower sampling ratios reduce costs but can miss rare errors.
- Tail-based sampling can retain error or slow traces after seeing the outcome, though it requires collector support.
- Error/high-latency sampling must align with backend and privacy policies.
- Do not use sampling as a replacement for metrics; metrics still need to record aggregate rates and latency.

Verify trace context propagates across WebFlux, Reactor, and downstream clients. A standalone `subscribe()` call can break context and lose trace links.

## 12. Context Propagation in Reactor

Reactive applications can switch threads between operators. Relying purely on `ThreadLocal` to carry trace IDs or request metadata can cause lost context.

Micrometer Context Propagation and Spring/Reactor integrations bridge Reactor Context and `ThreadLocal`-based instrumentation. Exact configuration depends on Spring Boot, Micrometer Context Propagation, and Reactor versions.

Principles:

- Use Spring/Micrometer integrations supported by the BOM.
- Do not manually copy trace IDs into `ThreadLocal` inside every service method.
- Do not call detached `subscribe()` inside services.
- Verify traces across `publishOn`, `subscribeOn`, `flatMap`, and HTTP clients.
- If using custom schedulers or callback libraries, confirm context propagates across those boundaries.
- Never put sensitive data into baggage.

Trace IDs link logs and traces, not business identities or credentials.

## 13. Correlating Logs with Traces

When Micrometer Tracing and logging integrations are configured, logs can carry trace IDs and span IDs to jump directly to the matching trace.

Example log:

~~~text
INFO  traceId=... spanId=... Order created
ERROR traceId=... spanId=... Database operation failed
~~~

Exact format depends on the logging framework and configuration. Never generate a new trace ID per log line; use context propagation and correlation integration.

Logs should include:

- Stable operation or route name.
- Trace/correlation ID when present.
- Exception class and appropriate cause.
- SQLState/vendor code if safe.
- Outcome and duration when helpful.

Never log passwords, access tokens, connection URLs with credentials, sensitive bind values, or full request payloads. Both trace attributes and log fields may be accessible to many users or systems.

## 14. Cardinality and Privacy

A common mistake is adding user IDs, order IDs, or full SQL to metric tags. Each distinct value can create a separate time series, consuming Prometheus memory and slowing backend queries.

Avoid:

~~~java
meterRegistry.counter(
        "orders.created",
        "orderId",
        order.getId().toString(),
        "email",
        customer.getEmail())
        .increment();
~~~

Prefer tags with finite value sets:

~~~java
meterRegistry.counter(
        "orders.created",
        "channel",
        normalizedChannel,
        "outcome",
        "success")
        .increment();
~~~

Rules:

- **Low-cardinality keys:** operation, status, method, outcome, fixed region.
- **High-cardinality data:** order ID, user ID, trace ID, request ID.
- High-cardinality data may be acceptable in traces/logs when controlled, though it is not automatically safe.
- Never put emails, phone numbers, tokens, SQL parameters, or PII in metric tags.
- Never put raw SQL or query parameters into spans without a protection policy.
- Bound exception/message tag values; never use dynamic error messages as tags.

The Observation API separates low-cardinality and high-cardinality key-values so backends can process each appropriately. Never declare unique IDs as low-cardinality tags.

## 15. Tracking R2DBC Errors and Retries

Metrics/observations should distinguish error categories:

- Constraint violations.
- SQL grammar or API usage errors.
- Connection acquisition failures.
- Query timeouts.
- Lock/optimistic locking conflicts.
- Serialization failures.
- Driver/network failures.
- Cancellations.

Do not use exception messages as metric tags because messages can contain dynamic data and cause high cardinality. Use the exception class or a normalized error category.

When retries exist, track separately:

- Retry count.
- Successful retries.
- Exhausted retries.
- Retry reason category.
- Total operation duration including backoff.

Use clear metric names such as `database.operation.retry` with `operation` and `reason` tags from finite sets. Avoid recording a counter per retry with arbitrary SQLState tags if those codes can take too many values.

Retrying an entire transaction can cause one request to execute SQL multiple times. Traces should identify individual attempts and the overall operation; avoid creating excessive spans or redundant log noise.

## 16. Health Indicators and Database Status

Actuator can provide an R2DBC health contributor when auto-configuration and the `ConnectionFactory` are supported.

Health checks typically test basic database reachability or connection validity. They do not replace:

- Query latency metrics.
- Pool saturation metrics.
- Replication lag monitoring.
- Lock wait metrics.
- Disk/storage capacity monitoring.
- Database-specific monitoring.

Inspect `/actuator/health` in secured environments. Component details should be shown only to authorized callers. Never expose hostnames, schemas, connection URLs, or internal exceptions publicly.

If the application uses multiple `ConnectionFactory` beans, verify each health contributor is named and categorized properly. An unavailable secondary database should not necessarily mark the entire application unready if core use cases continue working; this belongs to your application's health policy.

## 17. Configuring ObservedAspect and TimedAspect

If you want to use annotations, configure the appropriate aspects.

Example configuring `ObservedAspect` in a stack with Micrometer Observation:

~~~java
@Configuration
public class ObservationConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
~~~

Similarly, `TimedAspect` can be registered when using `@Timed`:

~~~java
@Bean
TimedAspect timedAspect(MeterRegistry registry) {
    return new TimedAspect(registry);
}
~~~

Classes and packages must exist in your dependency versions. Some Spring Boot generations or starters may auto-configure parts of this; avoid duplicate bean registrations. Check the condition evaluation report or application context before defining beans manually.

Annotation example:

~~~java
@Observed(name = "orders.submit")
public Mono<Order> submit(SubmitOrderCommand command) {
    return orderRepository.save(map(command));
}
~~~

With reactive return types, verify whether the aspect tracks the publisher through its terminal signal. If the aspect only measures the time for the method to construct and return the publisher, recorded durations will be artificially tiny and miss database latency. When unsure, use explicit reactive instrumentation such as `Mono.defer` with `doFinally`, or the reactive observation mechanism supported by your Spring release.

## 18. Creating a Custom ObservationConvention

When framework instrumentation provides an observation whose default tags are insufficient, you can supply a custom convention if that component's extension point supports it.

Conventions should add stable, operationally meaningful attributes:

- Repository/operation name.
- Command type such as `SELECT`/`INSERT`/`UPDATE`.
- `success`/`error` outcome.
- Non-sensitive entity type.
- Fixed database system.

Do not add:

- Entity IDs.
- Emails/usernames.
- Raw SQL containing values.
- Bind parameters.
- Tokens.
- Request bodies.

Before writing a convention, check the API for the exact component and version. `ObservationConvention` for HTTP, repositories, and database clients use different context types; you cannot reuse an arbitrary convention across all observations.

## 19. Dashboards and Alerts

An R2DBC dashboard can combine the following groups:

| Group | Metrics to Monitor |
|---|---|
| HTTP | Request rate, 4xx/5xx, p95/p99 latency |
| Service | Duration and outcome of core business operations |
| Repository/database | Query/operation duration, error rate if instrumented |
| Pool | Acquired, allocated, idle, pending, acquire timeout |
| JVM | Heap, GC pauses, thread count |
| Process | CPU, uptime |
| Database | Active sessions, lock waits, slow queries, connection limits |
| Tracing | Error traces, slow traces, downstream dependencies |

Meaningful alerts:

- HTTP 5xx exceeds threshold over a sustained window.
- p95/p99 latency rises continuously.
- Pool pending rises and acquire timeouts appear.
- Database connections approach server limit.
- Query timeouts or lock conflicts spike.
- JVM heap approaches limit or GC pauses stay elevated.
- Retry rate spikes sharply.

Use sustained windows and persistence conditions so alerts do not fire on brief spikes. Every alert should link to a runbook outlining the next investigation steps.

## 20. Controlling Metrics and Tracing Costs

Observability has resource costs:

- Meters and time series.
- Histogram buckets.
- Span volume.
- Export network traffic.
- Storage/retention.
- Instrumentation CPU and allocations.
- Log volume.

Controls to apply:

1. Enable histograms only on meters needed for percentiles/SLOs.
2. Cap tag cardinality.
3. Sample traces according to traffic and diagnostic needs.
4. Do not log SQL/bind values by default.
5. Reduce duplicate logging across layers.
6. Use stable meter/observation names.
7. Check time-series counts before rollout.
8. Monitor exporter errors so the observability backend never degrades the request path.

Never let a slow exporter or collector block the reactive event loop. Use official registries/exporters and appropriate configurations.

## 21. Verifying Instrumentation with Integration Tests

Tests should not only assert HTTP 200. Verify that metrics/observations are emitted when operations execute.

With Micrometer, `SimpleMeterRegistry` is well-suited for unit testing custom metrics:

~~~java
@Test
void incrementsCreatedOrderCounter() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    OrderMetrics metrics = new OrderMetrics(registry);

    metrics.orderCreated();

    assertThat(registry.get("orders.created").counter().count())
            .isEqualTo(1.0);
}
~~~

For `Observation`, use a test registry/handler matching your Micrometer version to verify observations start, stop, and record errors. Do not merely assert the method was called; verify the observation name and outcome.

### 21.1. Verifying Reactive Lifecycle

Tests should cover:

- Publisher completing successfully.
- Publisher emitting an error.
- Subscriber cancelling the subscription.
- Publisher subscribed to multiple times.
- Retries triggering multiple executions.
- Transaction commit/rollback at the proper boundary.

For example, `doFinally` must run for complete, error, and cancel. If `Timer.Sample` is created outside `Mono.defer`, multiple subscriptions can share a single sample and produce incorrect durations.

### 21.2. Checking Actuator Endpoints

In integration tests, call `/actuator/metrics` or `/actuator/prometheus` when exposed in the test profile.

Verify:

- The endpoint exists when the registry is present.
- Expected meters appear after the operation runs.
- Tags contain no sensitive data.
- Histograms/buckets are enabled as expected.
- Endpoints are secured if authentication is required.
- Metrics are recorded after the publisher actually finishes, not merely when the method returns.

Do not assert the full scrape text verbatim because formatting and ordering may change. Focus on meter names, counts, tags, and essential contracts.

## 22. Checking Version Compatibility in CI

An upgrade to Spring Boot, Spring Data, Micrometer, or an R2DBC driver can alter instrumentation behavior. Include CI checks to:

1. Resolve the dependency tree and check version convergence.
2. Start the application context with the test profile.
3. Verify `MeterRegistry` and `ObservationRegistry` beans exist.
4. Verify the R2DBC `ConnectionFactory` and pool beans are wired properly.
5. Run a real repository operation against a test database.
6. Verify pool metrics are registered when pooling is enabled.
7. Verify repository/`DatabaseClient` observations if supported by the release.
8. Verify trace context propagates through WebFlux/Reactor.
9. Call Actuator metrics/prometheus endpoints.
10. Verify metric tags contain no IDs or PII.
11. Compare meter/span names after version upgrades.
12. Run smoke/load tests to measure overhead if instrumentation changed.

Do not rely solely on compilation succeeding. Auto-configuration is conditional on classpath and properties and may skip creating beans even when code compiles.

## 23. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Pinning Micrometer version outside Spring Boot BOM | Incompatible dependencies | Use the BOM and inspect the dependency tree |
| Adding Actuator without a registry | No Prometheus exporter | Add the corresponding registry |
| Exposing all Actuator endpoints | Exposes configuration and internal state | Expose only needed endpoints and secure access |
| Assuming HTTP metrics include SQL | Cannot tell which query is slow | Verify repository/client/driver instrumentation |
| Assuming every R2DBC driver supports tracing | Traces lack database spans | Check specific driver and instrumentation support |
| Timing a `Mono` around the method call | Measures publisher creation instead of execution | Place `Timer` inside `defer` and stop on terminal signal |
| Sharing one `Timer.Sample` across subscriptions | Wrong durations or races | Create samples per subscription |
| Raising pool `max-size` when pending is high | Can overload the database further | Check queries, transactions, and total connections |
| Using IDs/emails as metric tags | Exploding cardinality and data leaks | Use tags with finite value sets |
| Logging raw SQL/bind values in traces | Exposes sensitive data | Use operation names and normalized metadata |
| Enabling histograms on every meter | Surge in time series | Enable only where needed for SLOs |
| Using `@Observed` without an aspect | Annotation creates no observations | Configure the aspect or use the API directly |
| Aspect measuring method return instead of publisher lifecycle | Artificially tiny reactive latencies | Check reactive support or instrument the publisher |
| Calling detached `subscribe()` | Lost trace/context and detached lifecycle | Chain publishers in a single reactive chain |
| Adding multiple instrumentations to the same step | Duplicate metric/span counts | Pick one clear measurement boundary |
| Assuming `SimpleMeterRegistry` proves exporter works | Tests pass yet Prometheus cannot scrape | Integration-test real registry and endpoint |
| Skipping version checks when upgrading Boot | Missing meters/spans or renamed metrics | Run compatibility tests in CI |

## 24. Step-by-Step Micrometer + R2DBC Integration Workflow

A practical implementation sequence:

1. Identify Spring Boot, Spring Framework, Spring Data, R2DBC SPI, and driver versions.
2. Use the Spring Boot BOM to select compatible Micrometer and registry versions.
3. Add Actuator.
4. Add required registries/exporters, e.g., Prometheus.
5. Expose needed endpoints and secure them.
6. Verify HTTP/JVM/system metrics.
7. Enable pooling and confirm R2DBC pool metrics.
8. Check whether repository/`DatabaseClient` observations are supported in your release.
9. Add business metrics/observations for critical operations.
10. Configure a tracing bridge and exporter if distributed tracing is needed.
11. Verify Reactor context propagation and log correlation.
12. Enforce tag cardinality, privacy, histogram, and sampling controls.
13. Verify metrics/spans with integration tests against a real database.
14. Operationalize SLO dashboards and alerts.
15. Re-run compatibility checks whenever upgrading Spring Boot, Spring Data, Micrometer, or drivers.

## 25. Takeaways

- Metrics, traces, and logs answer different questions and must be combined.
- Micrometer provides a unified API; `MeterRegistry` manages meters and `ObservationRegistry` manages observations.
- Use the Spring Boot BOM to align Spring Framework, Spring Data, Micrometer, registries, and tracing bridges.
- Spring Boot 2.x and 3.x belong to different observability generations; verify your exact minor/patch release instead of applying generic configs.
- Actuator provides health/metrics endpoints; Prometheus requires its corresponding registry.
- HTTP metrics do not imply SQL or R2DBC queries are instrumented.
- R2DBC pool metrics surface pending acquires, saturation, and connection pressure; meter names depend on version.
- Reactive timing must measure from subscription to complete/error/cancel, not just `Mono`/`Flux` construction.
- Repository observation, `DatabaseClient` observation, and driver tracing are distinct layers with varying support.
- An Observation can produce both metrics and traces via handlers; a standalone `Timer` does not create distributed spans.
- Micrometer Tracing requires a compatible bridge/exporter and proper Reactor context propagation.
- Use low-cardinality tags; never put user IDs, order IDs, emails, tokens, or SQL parameters into metrics.
- Control histograms, trace sampling, and log volume to bound costs.
- Protect Actuator endpoints and never expose infrastructure details publicly.
- Verify instrumentation in CI via dependency tree checks, application context startup, database tests, meter/observation assertions, and endpoint scrapes.

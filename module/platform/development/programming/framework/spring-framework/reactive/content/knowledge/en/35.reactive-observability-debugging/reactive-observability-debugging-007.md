# Micrometer for Reactor Chains and Avoiding High-Cardinality Labels

A Reactor chain can process thousands of requests and emit millions of elements. Measuring only HTTP endpoints is often not enough to know which pipeline stage is slow, how many subscriptions fail, whether streams complete normally or get cancelled, or whether a scheduler's queue is backing up. Micrometer provides a backend-independent measurement model; Reactor integrates with Micrometer to observe publishers and schedulers without writing listeners manually for every signal.

A common operational mistake when adding metrics is putting values that change on nearly every request into metric tags, such as orderId, userId, sessionId, requestId, or full URLs. Each tag combination creates a separate meter/time series. The number of series can grow rapidly, driving up RAM, ingest cost, storage volume, and query latency. Micrometer Observation distinguishes low-cardinality and high-cardinality key values to separate data suitable for metrics from data suitable for tracing.

This lesson belongs to the **Observability and Debugging** group of the Spring Framework - reactive module. It focuses on how to instrument Flux/Mono, read Reactor meters, measure Schedulers, use Observation, design tags with bounded value sets, and limit cardinality risks in Spring Boot 3.3.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the roles of Micrometer MeterRegistry and ObservationRegistry.
- Distinguish metrics, logs, and distributed traces.
- Know why Reactor metrics live in the separate reactor-core-micrometer module.
- Use Micrometer.metrics(MeterRegistry) with tap() to measure publishers.
- Name chains with name() and add tags with tag().
- Use Micrometer.observation(ObservationRegistry) to create observations for reactive chains.
- Distinguish metrics-level instrumentation from observation-level instrumentation.
- Measure Schedulers using Micrometer.timedScheduler().
- Understand Reactor meters such as flow duration, subscribed, requested, onNext delay, and scheduler tasks.
- Define cardinality, time series, and tag combination explosion.
- Distinguish low-cardinality and high-cardinality values.
- Understand why tags placed directly on Micrometer.metrics are always metric dimensions.
- Use Observation.lowCardinalityKeyValue() and highCardinalityKeyValue() appropriately.
- Design stable meter names, tags, route templates, and common tags.
- Use MeterFilter as an additional safeguard layer.
- Test meters using SimpleMeterRegistry.
- View metrics via Spring Boot Actuator and the Prometheus endpoint.
- Avoid writing personal data, secrets, or request identifiers into metric labels.

## 2. Metrics, Logs, and Traces Serve Different Roles

The three observability signals complement one another:

| Signal | Answers the Question | Example |
| --- | --- | --- |
| Metrics | Is the system healthy or trending abnormally? | Error rate, throughput, p95 latency, queue size |
| Logs | What specific event occurred? | Order O-1001 rejected due to invalid state |
| Traces | Which services/spans did a request traverse and where was time spent? | Gateway → Order API → Inventory → Database |

Metrics are typically aggregated over time and dimensions. They are suited for dashboards, alerts, and trend analysis. Logs contain details of individual events. Traces represent a request's path across multiple components, including spans, durations, and attributes.

Do not turn metrics into an event store. A metric like orders.pipeline.flow.duration can show the processing time distribution; it does not need a separate time series for every order. When you need to look up a specific order, use traces/logs with appropriate access control and retention.

### What Is Micrometer?

Micrometer is a metrics facade. Applications record Counter, Timer, Gauge, or DistributionSummary via MeterRegistry; the corresponding registry forwards data to Prometheus, OTLP, Datadog, Graphite, or another supported backend.

Micrometer Observation adds a shared abstraction for a unit of work. Depending on registered ObservationHandlers, an observation can generate metrics, traces, or other signals.

| Registry | Purpose | Common APIs |
| --- | --- | --- |
| MeterRegistry | Record and query meters | Counter, Timer, Gauge, DistributionSummary |
| ObservationRegistry | Start/stop observations and handle contextual key values | Observation.createNotStarted(), ObservationHandler |

In Spring Boot with Actuator, the appropriate registries and ObservationRegistry are usually auto-configured. Inject the Spring-managed beans; do not create a separate global static registry and expect it to receive Boot's configuration.

## 3. Reactor Integrates with Micrometer via a Separate Module

In Reactor 3.5 and later, the official instrumentation API lives in the artifact:

~~~xml
<dependency>
  <groupId>io.projectreactor</groupId>
  <artifactId>reactor-core-micrometer</artifactId>
</dependency>
~~~

This module provides the entry points:

- Micrometer.metrics(meterRegistry): collects detailed publisher metrics.
- Micrometer.observation(observationRegistry): observes the lifecycle of a reactive sequence.
- Micrometer.timedScheduler(...): wraps a Scheduler to measure work submitted through the wrapper.

These APIs accept a registry explicitly. That makes it clear which registry receives the metrics/observations, instead of relying on a hidden global registry.

Older Reactor instrumentation approaches based on reactor.util.Metrics and legacy operator metrics have been replaced by reactor-core-micrometer. For new code on Reactor 3.6, prefer Micrometer.metrics or Micrometer.observation combined with tap(). Adding micrometer-core to the classpath alone is not enough to call the new APIs; you need the dependency for the right module.

## 4. Measuring a Flux or Mono with Micrometer.metrics

To enable metrics for a publisher:

~~~java
Flux<OrderEvent> measured = Flux.just(
        new OrderEvent("created"),
        new OrderEvent("validated"))
    .name("orders.pipeline")
    .tag("operation", "process")
    .tap(Micrometer.metrics(meterRegistry));
~~~

Meaning:

1. Flux.just creates the source.
2. name() sets a stable meter prefix.
3. tag() adds a dimension with a small value set.
4. tap() installs the SignalListener provided by Reactor Core Micrometer.
5. When the publisher is subscribed to and completes, the corresponding meters are updated.

There must be a subscription for the pipeline to run and metrics to be recorded. Creating a Flux without subscribing does not produce an actual execution.

~~~java
measured.subscribe(
    event -> log.info("event={}", event),
    error -> log.error("pipeline failed", error));
~~~

In a WebFlux application, you normally do not manually subscribe inside a service/controller. Return the Flux/Mono so the framework manages the subscription. The subscribe() above only illustrates a standalone consumer.

### Why Does name() Matter?

~~~java
.name("orders.pipeline")
~~~

Meters created at the instrumentation point use the orders.pipeline prefix. If name() is omitted, Reactor uses the default prefix reactor.

Meter names should describe a stable business flow. Never put order IDs or user IDs into the name:

~~~java
// Avoid: each order creates a different meter name.
.name("orders." + orderId)
~~~

Use a stable name and analyze via bounded tags.

## 5. Placing Instrumentation at the Right Position in the Pipeline

tap(Micrometer.metrics(...)) measures the chain at the point where it is attached. Place it where it reflects the unit of work you want to observe.

~~~java
Flux<OrderEvent> result = source
    .filter(this::isValid)
    .map(this::normalize)
    .name("orders.validation")
    .tag("operation", "validate")
    .tap(Micrometer.metrics(meterRegistry))
    .flatMap(this::persist);
~~~

In this example, instrumentation is placed after validate/normalize and before persist. It observes the publisher from that point according to the tapped sequence's lifecycle. If you want to measure persist as well, place tap after persist or create an observation spanning the whole operation.

~~~java
Flux<OrderEvent> result = source
    .filter(this::isValid)
    .map(this::normalize)
    .flatMap(this::persist)
    .name("orders.process")
    .tag("operation", "create")
    .tap(Micrometer.metrics(meterRegistry));
~~~

This is instrumentation for the overall pipeline.

Do not mechanically attach metrics to every operator. Too many instrumentation points can create a huge number of meters, increase overhead, and make dashboards hard to read. Choose meaningful boundaries: ingest, validation, persistence, outbound calls, or an end-to-end business operation.

If a pipeline has retries, metrics attached before versus after retry can reflect different subscription counts or lifecycles. Decide whether you want to measure one overall business request or each attempt. Place tap according to that goal and test subscription counts and error statuses.

## 6. Common Reactor Meters

Reactor Core Micrometer provides several meters under the configured prefix.

| Meter Suffix | Type | Meaning |
| --- | --- | --- |
| .flow.duration | DistributionSummary | Time from subscription to terminal signal or cancellation |
| .malformed.source | Counter | Number of invalid signals from the source, such as onNext after onComplete |
| .onNext.delay | Timer | Interval between onNext signals, or from onSubscribe to the first onNext |
| .requested | DistributionSummary | Total demand requested by the subscriber |
| .subscribed | Counter | Number of subscriptions to the sequence |
| .scheduler.tasks.active | LongTaskTimer | Currently active scheduler tasks |
| .scheduler.tasks.completed | Timer | Task completion duration |
| .scheduler.tasks.pending | LongTaskTimer | Tasks waiting to be executed |
| .scheduler.tasks.submitted | Counter | Number of submitted tasks, distinguished by submission type |

Exact meters depend on the instrumentation type and Reactor version. For publisher metrics, the dynamic prefix comes from name(); if no name is set, it is usually reactor.

### Flow Duration and Terminal Status

Flow duration measures the lifecycle from subscribe until the chain finishes or is cancelled. Status can distinguish:

- completed: emitted onNext then onComplete.
- completedEmpty: completed without onNext.
- error: terminated with onError.
- cancelled: downstream cancelled the subscription.

Status is useful when a pipeline does not finish as expected. A high cancellation rate can indicate clients closing connections, timeouts, downstream no longer needing data, or application logic proactively cancelling.

### OnNext Delay

OnNext delay measures the gap between data signals. If a stream normally emits steadily but delay rises, there may be downstream backpressure bottlenecks, a slow source, a busy scheduler, or a slow external dependency.

It does not explain the cause by itself. Combine with traces, scheduler metrics, queue metrics, and logs to pinpoint the bottleneck.

### Requested Amount

Requested amount reflects subscriber demand. It is useful when analyzing backpressure. If a subscriber requests Long.MAX_VALUE, the stream has unbounded demand from that side; do not conclude the whole system lacks backpressure from a single meter alone.

## 7. Measuring Observations of a Reactive Sequence

Micrometer.metrics focuses on detailed publisher metrics. Micrometer.observation creates an observation for the sequence's lifecycle. Depending on ObservationRegistry handlers, an observation can produce timers, traces, or both.

~~~java
Flux<OrderEvent> observed = source
    .name("orders.pipeline")
    .tap(Micrometer.observation(observationRegistry));
~~~

This is the simplest way to create an observation for a sequence. ObservationRegistry must be supplied explicitly.

### Observation with Custom Name and Key Values

~~~java
Flux<OrderEvent> observed = source
    .tap(Micrometer.observation(
        observationRegistry,
        registry -> Observation.createNotStarted(
                "orders.process",
                registry)
            .lowCardinalityKeyValue("operation", "create")
            .lowCardinalityKeyValue("region", "ap-southeast-1")
            .highCardinalityKeyValue("order.id", orderId)
    ));
~~~

Here:

- orders.process is a stable observation name.
- operation has a small value set such as create, update, cancel.
- region comes from a finite list of regions.
- order.id is a unique identifier for an order, which has high cardinality.

Under Spring Boot's default Observation handler rules, low-cardinality key values are added to metrics and traces; high-cardinality key values are added only to traces. For high-cardinality values to appear in traces, the application needs an appropriate tracing handler/bridge configured. If only a metrics handler is present, high-cardinality values do not become metric labels.

Do not put emails, tokens, addresses, payment details, or personal data into traces just because the API accepts high-cardinality keys. Tracing still requires security policies, access control, and retention limits.

## 8. How Do Micrometer.metrics and Micrometer.observation Differ?

| Criterion | Micrometer.metrics | Micrometer.observation |
| --- | --- | --- |
| Entry point | MeterRegistry | ObservationRegistry |
| Reactor API | tap(Micrometer.metrics(registry)) | tap(Micrometer.observation(registry)) |
| Goal | Detailed publisher meters | Lifecycle of a unit of work |
| Tags | name() and tag() become meter dimensions | low/high cardinality key values |
| Traces | Does not create spans from the metrics API alone | Can create spans if registry has a tracing handler |
| Use when | You need demand, subscriptions, flow duration, onNext delay | You need unified metrics/tracing observation |

You do not need to attach both APIs to the same publisher. If both create timers for the same unit of work, you may get overlapping data. Pick one instrumentation type per goal or document each one's distinct purpose.

## 9. What Is Cardinality?

Cardinality is the number of distinct values a dimension can take. In metrics, a time series is identified by the metric name plus its set of tag/label values.

~~~text
orders.pipeline.flow.duration{
  operation="create",
  region="ap-southeast-1",
  status="completed"
}
~~~

A different tag combination is a different time series:

~~~text
orders.pipeline.flow.duration{
  operation="cancel",
  region="ap-northeast-1",
  status="error"
}
~~~

If operation has 4 values, region has 5 values, and status has 4 values, the maximum number of combinations is 4 × 5 × 4 = 80 series for one metric name, if every combination occurs.

If you add orderId with 1,000,000 distinct values, the theoretical number of combinations jumps to 80,000,000. That is the worst case by Cartesian product of value domains; in practice it also depends on which combinations occur.

### Why Is High Cardinality Dangerous?

Each series can consume memory, metadata, index entries, scrape/export work, and storage. Rising cardinality causes:

- Increased RAM usage in the application or metrics backend.
- Higher storage and ingestion costs.
- Slow Prometheus scrapes/queries.
- Slow-loading dashboards and unstable alerts.
- Continuous creation of short-lived series.
- Exceeding backend quotas.
- Difficulty keeping the metric schema stable across releases.

High sample count and high series count are two different problems. A metric with few series updated frequently can have many samples; a metric with millions of label combinations has high cardinality even if each series has few samples.

## 10. Low Cardinality and High Cardinality

Low-cardinality values have a finite, small, stable domain. High-cardinality values can produce huge numbers of variants, often growing with request or entity counts.

| Low-Cardinality Usually Fits Metrics | High-Cardinality Usually Unfit as Metric Tags |
| --- | --- |
| operation=create/update/delete | orderId |
| outcome=success/error | userId |
| status=completed/error/cancelled | sessionId |
| region from a small allowlist | requestId |
| paymentMethod=card/bank | traceId |
| route=/orders/{id} | raw URL /orders/12345 |
| environment=dev/staging/prod | email or IP |
| exceptionType from known classes | dynamic exception message |

Low cardinality has no single universal threshold for every backend. A tag with 20 values may be fine in one system yet too large on a very hot metric. Evaluate expected series count, update frequency, backend quotas, and query needs.

### Finite Values Must Truly Be Bounded

If the region tag is taken directly from a query string, users can send region=abc-1, region=abc-2, and countless other values. A tag name that sounds low-cardinality does not guarantee its values are actually bounded.

~~~java
private static final Set<String> REGIONS = Set.of(
    "ap-southeast-1",
    "ap-northeast-1");

private String normalizeRegion(String input) {
    return input != null && REGIONS.contains(input)
        ? input
        : "other";
}
~~~

The tag can only take one of three values: the two defined regions or other.

## 11. Dangerous Mistake: Putting IDs into Reactor tag()

Example to avoid:

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("orderId", orderId)
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

Every distinct orderId creates a new metric dimension. With millions of orders, series counts can grow rapidly.

A similar mistake is putting userId, requestId, or sessionId into tags:

~~~java
.tag("userId", userId)
.tag("requestId", requestId)
.tag("sessionId", sessionId)
~~~

Micrometer.metrics has no mechanism to guess that a tag is high-cardinality and divert it to traces. Every tag from Reactor tag() is used as a meter dimension.

### Fix

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("operation", "lookup")
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

If orderId is needed to locate a specific request, use logs with a structured field or a controlled trace attribute. Do not sacrifice the health of your metrics backend just to query a single order in Prometheus.

## 12. Using High-Cardinality Values Properly in Observation

Observation has an API that clearly separates the two groups:

~~~java
Observation.createNotStarted("orders.lookup", observationRegistry)
    .lowCardinalityKeyValue("operation", "lookup")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("order.id", orderId)
    .observe(() -> repositoryLookup(orderId));
~~~

When using Spring Boot with default Observation handlers:

- operation and outcome are sent to metrics and traces.
- order.id is sent only to traces.
- order.id does not spawn a metric series per order.

For reactive chains, you can use Micrometer.observation inside tap() as shown earlier to observe the publisher's lifecycle.

### High Cardinality Does Not Mean Everything Should Be Recorded

Traces are useful for investigating a specific request, yet can contain sensitive data. Avoid storing tokens, passwords, cookies, emails, or full payloads. Internal IDs also require evaluation of retention, access control, and data policies.

### What If There Is No Tracing Handler?

ObservationRegistry may only have a meter handler. In that case, high-cardinality key values are not turned into metrics under Spring Boot's semantics, but may not be exported anywhere either. If traces are needed, configure a Micrometer Tracing bridge and matching exporter; do not convert high-cardinality values into metric tags to compensate for missing tracing.

## 13. Metric Names and Route Templates Must Be Stable

Metric names are part of your operational schema. Name them after business capabilities and do not embed request parameters.

Do:

~~~java
.name("orders.pipeline")
.name("inventory.reservation")
.name("payments.authorize")
~~~

Do not:

~~~java
.name("orders." + orderId)
.name("users." + username)
.name("http." + request.getURI())
~~~

For HTTP routes, use route templates rather than raw paths. For instance, /orders/{id} has a small route domain; /orders/10001, /orders/10002, ... generate many distinct values.

Good conventions:

- Meter names are stable and namespaced.
- Tag keys are consistent and do not get renamed between releases.
- Tag values come from enums or allowlists.
- Never attach raw URLs, query strings, or exception messages.
- Keep the exact same set of tag keys for the same metric name.
- Use common tags for environment/region/instance when they have bounded domains.

Some backends, including Prometheus, expect series sharing a metric name to have a consistent label schema. Do not arbitrarily add a tag key on one pipeline branch while omitting it on another.

## 14. MeterFilter: An Additional Safeguard Layer

Micrometer MeterFilter allows denying, transforming, or bounding meter registration. It is useful for preventing an unexpected tag from creating unbounded series.

~~~java
@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterFilter tenantTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "orders.pipeline",
            "tenant",
            20,
            MeterFilter.deny());
    }
}
~~~

Meaning:

- Applies only to meters whose names start with orders.pipeline.
- Inspects values of the tenant tag.
- Allows at most 20 distinct values for matching meters.
- Once the threshold is exceeded, the fallback filter returns DENY for corresponding new meters.

Spring Boot automatically registers MeterFilter beans with the Spring-managed MeterRegistry.

### MeterFilter Does Not Replace Good Tag Design

If a filter allows the first 20 tenants and denies the rest, metrics for subsequent tenants are not recorded as expected. It does not group them into other, does not fix the tag, and does not automatically notify operators that the schema is wrong.

Therefore:

1. Design tags with finite domains from the start.
2. Use MeterFilter as a defensive limit.
3. Monitor meter counts and alert when filters begin denying meters.
4. Verify prefix and tag key so the filter affects only intended meters.
5. Do not set thresholds so low that valid data gets dropped.

You can use MeterFilter.ignoreTags("requestId", "userId") to strip certain tags from meter IDs, but this is a post-hoc mitigation. It is better not to attach those tags in the first place.

## 15. Common Tags in Spring Boot

Common tags apply across many meters. Examples:

~~~properties
management.metrics.tags.application=order-service
management.metrics.tags.environment=staging
~~~

These values should be stable per deployment. Do not put pod request IDs or constantly changing build timestamps into common tags.

For Observation, you can configure common low-cardinality key values:

~~~properties
management.observations.key-values.region=ap-southeast-1
management.observations.key-values.stack=production
~~~

These values are added to observations per Spring Boot configuration. If a property takes arbitrary values from an environment or tenant with a huge domain, it can still produce high cardinality. Being named common does not automatically make a value low-cardinality.

## 16. Measuring Schedulers with Micrometer.timedScheduler

Reactor executes asynchronous work via Schedulers. When you need to observe a dedicated scheduler, you can wrap it:

~~~java
Scheduler original = Schedulers.newParallel(
    "order-worker", 4);

Scheduler measured = Micrometer.timedScheduler(
    original,
    meterRegistry,
    "orders.scheduler");
~~~

Then use the wrapper for tasks:

~~~java
Mono<Void> work = Mono.fromRunnable(
        () -> performCpuWork())
    .subscribeOn(measured)
    .then();
~~~

Only Runnables submitted through the measured wrapper are measured. If code elsewhere submits directly to original, those tasks are not instrumented by the wrapper.

When creating a dedicated Scheduler, dispose of it on application shutdown:

~~~java
@Bean(destroyMethod = "dispose")
Scheduler orderWorkerScheduler(MeterRegistry registry) {
    Scheduler original = Schedulers.newParallel(
        "order-worker", 4);

    return Micrometer.timedScheduler(
        original, registry, "orders.scheduler");
}
~~~

For application-created schedulers, manage cleanup. Do not wrap the same scheduler multiple times without reason, as it can double-measure or only measure one submission path.

### Reading Scheduler Metrics

Scheduler meters can report submitted tasks, completed tasks, active tasks, pending tasks, and execution time. Continuously rising pending tasks can indicate scheduler overload, blocking operations, or improper concurrency. Combine with CPU, thread pool, queue, GC, and external dependency metrics to find the cause.

## 17. Metrics and Observation Do Not Automatically Mean Tracing Is Enabled

Spring Boot Actuator auto-configures Micrometer MeterRegistry and ObservationRegistry. However, to export traces, the application needs a corresponding tracing bridge and exporter.

A basic metrics setup may include:

- spring-boot-starter-actuator.
- micrometer-registry-prometheus.
- reactor-core-micrometer.

To export traces, you can add a Micrometer Tracing bridge for OpenTelemetry or Brave and a suitable exporter. Do not assume high-cardinality Observation key values are being exported simply because code calls highCardinalityKeyValue().

Spring Boot may auto-instrument HTTP servers, WebClient, or supported integrations. If you create another observation wrapping the exact same operation without distinct boundaries, metrics can be double-counted. Choose clear boundaries:

- HTTP server observation: overall request duration.
- Reactor pipeline observation: duration of an internal business flow.
- Scheduler metrics: task execution performance.
- Database observation: query duration.

## 18. Context Propagation for Observation in Reactor

Observation context may need to cross threads and reactive pipelines. Spring Boot 3.3 provides the property:

~~~properties
spring.reactor.context-propagation=auto
~~~

The default is limited. Auto mode enables automatic context propagation for new subscriptions, helping ThreadLocal values be restored from Reactor Context at appropriate execution points.

Keep in mind:

- Context propagation does not reduce cardinality.
- It does not automatically turn a dynamic tag into a high-cardinality trace attribute.
- It does not replace setting proper low/high key values.
- The hook applies to new subscriptions; configure it at startup.
- ThreadLocals must still be cleaned up to prevent leaking data to tasks reusing the thread.
- For custom executors or @Async, ContextPropagatingTaskDecorator may be needed.

If you only use Reactor metrics with MeterRegistry, you do not need to enable auto context propagation just to record meters. Enable it when the application needs to propagate observation/tracing context across thread boundaries by design.

## 19. Wrong and Right Examples: Tracking Orders

### Wrong: Every Order Creates a Time Series

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("orderId", orderId)
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

Each distinct orderId creates a new metric dimension. With millions of orders, series counts can escalate rapidly.

### Right: Metrics Use Bounded Dimensions

~~~java
public Mono<Order> find(String orderId) {
    return repository.findById(orderId)
        .name("orders.lookup")
        .tag("operation", "lookup")
        .tap(Micrometer.metrics(meterRegistry));
}
~~~

If you need to distinguish found, missing, or error, design a status tag based on terminal signals or an Observation convention with a small value set. Do not attach a static label that misrepresents outcomes.

### Right: Specific IDs Kept in Traces

~~~java
public Mono<Order> findOrderObserved(String orderId) {
    return repository.findById(orderId)
        .tap(Micrometer.observation(
            observationRegistry,
            registry -> Observation.createNotStarted(
                    "orders.lookup",
                    registry)
                .lowCardinalityKeyValue(
                    "operation", "lookup")
                .highCardinalityKeyValue(
                    "order.id", orderId)));
}
~~~

Order ID does not become a metric dimension in Spring Boot's default Observation handler; it can appear in traces if tracing is configured. If traces carry sensitive data, apply redaction and access control policies.

## 20. Hands-On Java 17+ Project with Spring Boot 3.3.5

The project below provides a WebFlux endpoint emitting OrderEvents, measures the publisher with Micrometer.metrics, and provides a lookup operation creating an Observation with order ID as a high-cardinality trace attribute.

### Directory Structure

~~~text
reactor-micrometer-demo/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example/observability
    │   │   ├── ObservabilityApplication.java
    │   │   ├── OrderEvent.java
    │   │   ├── OrderMetricsService.java
    │   │   ├── OrderController.java
    │   │   └── MetricsConfiguration.java
    │   └── resources/application.properties
    └── test
        └── java/com/example/observability
            └── ReactorMetricsTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>reactor-micrometer-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core-micrometer</artifactId>
    </dependency>
    <dependency>
      <groupId>io.micrometer</groupId>
      <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot dependency management provides compatible versions for Reactor, Micrometer, and the Prometheus registry. reactor-core-micrometer is a separate dependency required to use Reactor's Micrometer API.

### application.properties

~~~properties
server.port=8080

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.tags.application=reactor-micrometer-demo
management.metrics.tags.environment=dev

management.observations.key-values.region=ap-southeast-1
management.observations.key-values.stack=local

spring.reactor.context-propagation=auto
~~~

The common values application, environment, region, and stack have controlled value domains. Do not replace them with request IDs, timestamps, or usernames.

The Prometheus endpoint is exposed at /actuator/prometheus. Expose only necessary actuator endpoints in deployment environments, and configure appropriate authentication/network policies.

### ObservabilityApplication.java

~~~java
package com.example.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ObservabilityApplication.class, args);
    }
}
~~~

### OrderEvent.java

~~~java
package com.example.observability;

public record OrderEvent(
    String orderId,
    String status) {
}
~~~

The record is the response DTO. orderId appears in the JSON response because it is business data; returning an ID to an API client does not mean it should be used as a metric tag.

### OrderMetricsService.java

~~~java
package com.example.observability;

import java.util.Set;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class OrderMetricsService {

    private static final Set<String> ALLOWED_REGIONS =
        Set.of("ap-southeast-1", "ap-northeast-1");

    private final MeterRegistry meterRegistry;
    private final ObservationRegistry observationRegistry;

    public OrderMetricsService(
            MeterRegistry meterRegistry,
            ObservationRegistry observationRegistry) {
        this.meterRegistry = meterRegistry;
        this.observationRegistry = observationRegistry;
    }

    public Flux<OrderEvent> events(String region) {
        String safeRegion =
            region != null && ALLOWED_REGIONS.contains(region)
                ? region
                : "other";

        return Flux.just(
                new OrderEvent("ord-1001", "created"),
                new OrderEvent("ord-1002", "validated"),
                new OrderEvent("ord-1003", "completed"))
            .name("orders.pipeline")
            .tag("operation", "process")
            .tag("region", safeRegion)
            .tap(Micrometer.metrics(meterRegistry));
    }

    public Mono<OrderEvent> lookup(String orderId) {
        return Mono.fromSupplier(
                () -> new OrderEvent(orderId, "found"))
            .tap(Micrometer.observation(
                observationRegistry,
                registry -> Observation.createNotStarted(
                        "orders.lookup",
                        registry)
                    .lowCardinalityKeyValue(
                        "operation", "lookup")
                    .highCardinalityKeyValue(
                        "order.id", orderId)));
    }
}
~~~

Points to observe:

1. orders.pipeline is a stable meter name.
2. operation has only a finite set of actions.
3. region is mapped through an allowlist; any other value becomes other.
4. orderId resides in the response payload, not in metric tags.
5. lookup uses the Observation API; order.id is marked high-cardinality.
6. MeterRegistry and ObservationRegistry are injected from Spring Boot.

If there is no tracing handler, high-cardinality order.id may not be exported; add Micrometer Tracing and an exporter when specific traces are needed. Do not turn order.id into a tag just to force it into metrics.

### OrderController.java

~~~java
package com.example.observability;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class OrderController {

    private final OrderMetricsService service;

    public OrderController(OrderMetricsService service) {
        this.service = service;
    }

    @GetMapping("/orders/events")
    public Flux<OrderEvent> events(
            @RequestParam(defaultValue = "ap-southeast-1")
            String region) {
        return service.events(region);
    }

    @GetMapping("/orders/{id}")
    public Mono<OrderEvent> lookup(@PathVariable String id) {
        return service.lookup(id);
    }
}
~~~

The controller returns publishers to WebFlux. The framework subscribes and serializes responses. Do not call subscribe() in the controller just to record metrics; tap() is in the chain and metrics are recorded when the HTTP request subscribes to the publisher.

### MetricsConfiguration.java

~~~java
package com.example.observability;

import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterFilter tenantTagLimit() {
        return MeterFilter.maximumAllowableTags(
            "orders.pipeline",
            "tenant",
            20,
            MeterFilter.deny());
    }
}
~~~

The filter acts as a backup limit in case someone accidentally adds a tenant tag to orders.pipeline. This example does not attach a tenant ID; if per-tenant analysis is needed, consider a tier/segment with a small, controlled domain.

### ReactorMetricsTest.java

~~~java
package com.example.observability;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import reactor.core.observability.micrometer.Micrometer;
import reactor.core.publisher.Flux;

class ReactorMetricsTest {

    @Test
    void publisherRecordsMetersWithBoundedTags() {
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

        Flux.range(1, 3)
            .name("orders.pipeline")
            .tag("operation", "process")
            .tag("region", "ap-southeast-1")
            .tap(Micrometer.metrics(registry))
            .blockLast();

        Meter subscribed = registry.getMeters().stream()
            .filter(meter ->
                meter.getId().getName().equals(
                    "orders.pipeline.subscribed"))
            .findFirst()
            .orElseThrow();

        assertEquals(
            "process",
            subscribed.getId().getTag("operation"));

        assertEquals(
            "ap-southeast-1",
            subscribed.getId().getTag("region"));

        assertFalse(
            subscribed.getId().getTags().stream()
                .anyMatch(tag ->
                    tag.getKey().equals("orderId")));

        registry.close();
    }

    @Test
    void meterFilterCapsDistinctValuesForOneTag() {
        SimpleMeterRegistry registry =
            new SimpleMeterRegistry();

        registry.config().meterFilter(
            MeterFilter.maximumAllowableTags(
                "orders.pipeline",
                "customerId",
                2,
                MeterFilter.deny()));

        registry.counter(
            "orders.pipeline.calls",
            "customerId", "customer-a").increment();

        registry.counter(
            "orders.pipeline.calls",
            "customerId", "customer-b").increment();

        registry.counter(
            "orders.pipeline.calls",
            "customerId", "customer-c").increment();

        long matchingMeters = registry.getMeters().stream()
            .filter(meter ->
                meter.getId().getName().equals(
                    "orders.pipeline.calls"))
            .count();

        assertEquals(2, matchingMeters);
        registry.close();
    }
}
~~~

The first test subscribes to the publisher with blockLast() to trigger instrumentation and verifies the subscribed meter and stable tags. The second test demonstrates MeterFilter denying meters above the tag value cap. These are unit tests for an in-memory registry; they do not replace testing Prometheus scraping or trace exporters.

### Run Tests

~~~bash
mvn -q clean test
~~~

When both tests pass, Maven exits with code 0. The example does not require a database or external service.

### Run the Application

~~~bash
mvn spring-boot:run
~~~

Call the endpoint:

~~~bash
curl "http://localhost:8080/api/orders/events?region=ap-southeast-1"
~~~

Expected JSON response:

~~~json
[
  {"orderId":"ord-1001","status":"created"},
  {"orderId":"ord-1002","status":"validated"},
  {"orderId":"ord-1003","status":"completed"}
]
~~~

Call lookup:

~~~bash
curl "http://localhost:8080/api/orders/ord-1001"
~~~

Response:

~~~json
{"orderId":"ord-1001","status":"found"}
~~~

### Inspect Meters via Actuator

~~~bash
curl "http://localhost:8080/actuator/metrics/orders.pipeline.subscribed"
~~~

View exposed Prometheus metrics:

~~~bash
curl "http://localhost:8080/actuator/prometheus"
~~~

Metric names when exported to Prometheus may be normalized per the registry's naming convention. Use the metrics endpoint to inspect original meter IDs; use the prometheus endpoint to see the actual format scraped by backends.

## 21. Testing and Verifying Cardinality

A cardinality test should verify at least:

- Meter names do not contain dynamic IDs.
- Tag keys form a stable set.
- Tag values come from enums/allowlists.
- Two requests with two different orderIds do not create two different metric series when orderId is not a tag.
- MeterFilter denies values exceeding thresholds when a guard is configured.
- Observation high-cardinality fields are not accidentally converted into metric tags.
- Meter counts grow within expected bounds after a representative batch of requests.

You can use SimpleMeterRegistry to inspect meter IDs in unit tests. For integration tests, use PrometheusMeterRegistry or Actuator endpoints to verify exported names/labels.

### Measure Before and After

1. Send 100 requests with 100 different order IDs.
2. Count the meters for orders.pipeline.
3. Confirm the meter count did not increase 100x just because IDs differed.
4. Change operation from create to cancel.
5. Confirm only series matching the designed operation domain appear.

Do not measure registry.getMeters().size() only once at startup. Cardinality issues may only surface when real traffic exercises rare code paths.

### Observing Metric Counts in Production

Track total active series, new series over time, meters denied by MeterFilter, new tag values for key dimensions, series churn rate, backend query latency, and scrape duration.

A cardinality spike often appears after a release adds a tag or changes a route name. Include tag schemas in code reviews and tests, just like database schema changes.

## 22. Common Mistakes and Fixes

1. **Adding micrometer-core without reactor-core-micrometer.** Reactor's Micrometer APIs are missing; add the proper module.
2. **Using legacy reactor.util.Metrics in new code.** Prefer Micrometer.metrics() or Micrometer.observation().
3. **Creating a publisher without subscribing.** The pipeline has not run so no meter events occur; let WebFlux manage subscription or subscribe in a standalone consumer.
4. **Forgetting name().** Meters use the default reactor prefix; set a stable business-oriented name.
5. **Setting name based on orderId.** Every ID creates a new meter name; keep prefixes static.
6. **Putting userId/orderId/requestId into tag().** Every value creates a new metric dimension; move identifiers to traces/logs appropriately.
7. **Assuming Micrometer.metrics auto-detects high cardinality.** Every Reactor tag() is a metric tag; the API does not automatically divert dynamic tags to traces.
8. **Using Observation.highCardinalityKeyValue and expecting Prometheus to have that label.** Under Boot's default handlers, high-cardinality keys are for traces only.
9. **Having no tracing exporter yet expecting trace attributes to be stored.** Add a bridge/exporter or accept that high-cardinality keys are not exported.
10. **Using raw URLs as tags.** Path IDs and query strings can generate endless series; use route templates.
11. **Using exception messages as tags.** Messages often contain IDs, inputs, or dynamic text; use exception class or bounded outcomes.
12. **Putting IPs/emails/tokens into metrics.** Both cardinality and privacy suffer; never put secrets/PII in labels.
13. **Using region names without validating input.** Query parameters can take unbounded values; normalize with an allowlist.
14. **Using different tag keys for the same meter name.** Backends can run into inconsistent schemas; keep tag keys fixed.
15. **Relying on MeterFilter as the sole solution.** Filters can deny valid data past the cap; fix tag design at the source.
16. **Setting maximumAllowableTags too low.** New meters get dropped and dashboards miss data; choose thresholds matching valid domains.
17. **Not checking metric names after normalization.** Prometheus may convert dots to underscores; inspect via the actual endpoint.
18. **Attaching overlapping metrics and observations without boundaries.** The same work may be counted twice; pick clear instrumentation points.
19. **Measuring a scheduler wrapper while submitting tasks to the original scheduler.** Those tasks bypass the wrapper and are not measured; use the wrapper at submission sites.
20. **Creating new Schedulers without disposing them.** Threads/resources linger after tests or shutdown; manage lifecycles.
21. **Placing tap too early or too late relative to the business unit to measure.** Meters reflect the wrong boundary; define the pipeline segment to observe clearly.
22. **Thinking Micrometer.metrics and Micrometer.observation produce the same meters.** The two APIs have different goals and datasets; choose the right one.
23. **Enabling automatic context propagation to solve cardinality.** Context propagation does not limit tag counts; tag design still has to be right.
24. **Testing only with SimpleMeterRegistry and assuming Prometheus export is right.** An in-memory registry does not check scrape format; add integration tests if needed.
25. **Not monitoring series churn after releases.** A dynamic tag may only surface when real traffic rises; track series counts and denied meters.

## 23. Reactor Metrics Design Checklist

Before merging instrumentation:

- Is the publisher given a stable name?
- Do meter names accidentally contain dynamic IDs or URLs?
- Does each tag key have a clear value domain?
- Are region, environment, operation, and status bounded/normalized?
- Are userId, orderId, requestId, sessionId, or traceId absent from metric tags?
- Are raw paths, query strings, IPs, or emails absent from tags?
- If IDs are needed for investigation, are controlled traces/logs used instead?
- Are Micrometer.metrics and Micrometer.observation clearly distinguished?
- Do high-cardinality Observation keys go only to traces as intended?
- Are registries injected from Spring Boot?
- Is reactor-core-micrometer included in dependencies?
- Do MeterFilters have exact prefixes/tag keys and sensible caps?
- Are there tests checking meter IDs and tag sets?
- Is there a test sending requests with many IDs to confirm series do not scale with IDs?
- Does the scheduler wrapper measure tasks actually submitted through it?
- Do custom schedulers have cleanup?
- Is there no duplicate instrumentation at the same boundary?
- Does Actuator expose only necessary endpoints with proper protection?
- Does the Prometheus/metrics backend have alerts for cardinality or series growth?
- Do logs/traces have redaction, access control, and retention policies?

## 24. Self-Check Exercises

**Question 1.** Which module does Reactor use for modern Micrometer integration?  
**Answer:** reactor-core-micrometer.

**Question 2.** Which API records publisher metrics into MeterRegistry?  
**Answer:** tap(Micrometer.metrics(meterRegistry)).

**Question 3.** Why should you give a chain a name()?  
**Answer:** To establish a stable, easy-to-find meter prefix and avoid the generic default prefix.

**Question 4.** What does tag() on a publisher used with Micrometer.metrics create?  
**Answer:** A metric dimension/tag for the publisher's meters.

**Question 5.** Should orderId be a metric tag?  
**Answer:** Typically no; it has high cardinality and creates too many series.

**Question 6.** Which registry does Micrometer.observation accept?  
**Answer:** ObservationRegistry.

**Question 7.** Where are Observation's low-cardinality key values exported under Spring Boot's default handlers?  
**Answer:** Metrics and traces.

**Question 8.** Where are high-cardinality key values exported under Spring Boot's default handlers?  
**Answer:** Only traces, not metric labels.

**Question 9.** Which API measures a Scheduler?  
**Answer:** Micrometer.timedScheduler().

**Question 10.** What does the cardinality of a multi-tag metric depend on?  
**Answer:** The number of distinct tag value combinations; worst-case is the product of each tag's cardinality.

**Question 11.** What is MeterFilter.maximumAllowableTags used for?  
**Answer:** Limiting the number of distinct values for a tag key on meters whose names match a prefix.

**Question 12.** Does MeterFilter automatically group values exceeding the limit into other?  
**Answer:** No; the filter can deny meters above the threshold. To group values, normalize them before creating tags.

**Question 13.** Can raw URLs be used as tags?  
**Answer:** They should not be; use stable route templates such as /orders/{id}.

**Question 14.** Do you need to manually subscribe in a WebFlux controller for metrics to work?  
**Answer:** No; return the publisher so the framework subscribes. Metrics are recorded when the subscription actually runs.

**Question 15.** What can SimpleMeterRegistry verify?  
**Answer:** Meter IDs and tags in memory, though it does not replace testing exporters/backends.

## 25. Key Takeaways

Reactor integrates with Micrometer via reactor-core-micrometer. Use name() to set a stable meter prefix, tag() to add dimensions with small value domains, and tap(Micrometer.metrics(meterRegistry)) to record publisher metrics. Micrometer.observation(observationRegistry) measures the lifecycle of a reactive sequence; Micrometer.timedScheduler() measures tasks routed through a Scheduler wrapper.

Cardinality is the number of distinct tag values; each tag combination can create a time series. Never put orderId, userId, requestId, sessionId, email, IP, or raw URLs into metric tags. With Observation, lowCardinalityKeyValue goes to metrics and traces under Spring Boot's default handlers; highCardinalityKeyValue is for traces only. If tracing is not configured, high-cardinality values may not be exported anywhere.

MeterFilter.maximumAllowableTags is a defensive safeguard, not a substitute for designing tags with finite value domains. Test meter IDs, measure series growth, and monitor cardinality after every release. Use metrics to observe overall trends, traces/logs to investigate individual requests, and protect sensitive data across every signal.

### References

- Project Reactor 3.6, [Exposing Reactor Metrics](https://docs.spring.io/projectreactor/reactor-core/docs/3.6.3/reference/html/#metrics).
- Project Reactor, [Micrometer.metrics and Micrometer.observation](https://projectreactor.io/docs/core/release/reference/metrics.html).
- Spring Boot 3.3, [Metrics and MeterRegistry](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).
- Spring Boot 3.3, [Observability and Cardinality](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).
- Micrometer, [Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).
- Micrometer, [Observation Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html).
- Micrometer, [Concepts: Meters and Tags](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).
- Reactor Core Javadoc, [Micrometer entry point](https://docs.spring.io/projectreactor/reactor-core/docs/3.6.11/api/reactor/core/observability/micrometer/Micrometer.html).

# `loggers`, `metrics`, and Basic Operational Signals

When a Spring Boot application runs on your personal machine, you can tell what it is doing by watching the console. However, when the application runs in containers, across multiple servers, or handles thousands of requests, merely seeing the line “Started Application” is not enough. You need to answer practical questions:

- Is the application alive and able to receive traffic?
- Where is a request slow? Is the error rate rising?
- Is a work queue backing up?
- Which log level is active, and can DEBUG be raised temporarily during an incident?
- How are request volume, response times, and error counts changing over time?
- When a dependency like the database runs into trouble, does the system emit appropriate signals?

Spring Boot provides building blocks to observe application status: **logging**, **Micrometer metrics**, **Actuator endpoints**, **health indicators**, **application availability**, and integration with external monitoring systems. These components do not replace one another; they offer complementary views of the same application.

This lesson belongs to the **Application Observability** chapter of **Spring Boot Fundamentals**. Its focus is `loggers`, `metrics`, and basic operational signals: how to enable, read, interpret, extend, and protect them.

## 1. What Is Application Observability?

In software operations, **observability** is the ability to understand the internal state and behavior of a system from the signals it emits. With Spring Boot, common signals include:

| Signal | Question Answered | Example |
|---|---|---|
| **Logs** | What specific event happened? | “Payment failed: orderId=ORD-123” |
| **Metrics** | What are the frequency, rate, or trend? | 100 requests/sec, 2% errors, P95 latency 300 ms |
| **Traces** | Which components did an operation pass through? | API → Service → Database → Gateway |
| **Health/availability** | Is the instance alive and ready to accept traffic? | `UP`, `DOWN`, accepting/refusing traffic |
| **Application events** | Which lifecycle phase did the app just enter? | Started, Ready, shutdown |
| **Alerts** | When do operators need to act? | HTTP 5xx rate exceeds threshold over a time window |

This lesson focuses deeply on logs, metrics, and availability/health, while pointing out where traces and alerts connect with them.

### 1.1. Three Layers of Questions

Suppose users report: “Payments are very slow.”

**Layer 1 — Is there a widespread problem?**

Check metrics:

```text
request rate          : 250 requests/s
HTTP 5xx rate         : 7%
P95 request duration  : 1.8 s
```

These numbers are illustrative examples, not measurements from a specific system.

**Layer 2 — Is there a specific error event?**

Check logs:

```text
ERROR Payment gateway timeout: orderId=ORD-123 attempt=3
java.net.SocketTimeoutException: Read timed out
    at ...
```

**Layer 3 — Where did one request travel?**

If tracing exists, inspect spans of the same request to identify which dependency or operation consumed most of the time.

Metrics speak to *scale and trends*, logs speak to *specific events*, and traces speak to *an operation's path*. Health indicates current operational status according to rules you configure.

### 1.2. Monitoring Does Not Appear Automatically Just Because Logs Exist

An application can write thorough logs yet still lack dashboards, alerting, or metric storage. Spring Boot provides APIs and endpoints to emit signals; you still need to choose where to collect, store, visualize, and alert appropriately.

Conceptual diagram:

```text
                  Spring Boot Application
               ┌──────────────┬──────────────┐
               │              │              │
               ▼              ▼              ▼
          SLF4J Logger   Micrometer       Actuator
               │          Metrics       Health/Info
               ▼              │              │
         Console/JSON          ▼              ▼
               │        Registry/Export   Probes
               ▼              │              │
         Log Collector         ▼              ▼
               │         Metrics Backend  Orchestrator
               └──────────────┬──────────────┘
                              ▼
                      Dashboard / Alert
```

Not every application needs all of the tools above from day one. What matters is knowing which signal solves which problem.

## 2. What Role Does Spring Boot Actuator Play?

**Spring Boot Actuator** is the module providing endpoints and integrations for managing and monitoring an application. It enables observing information such as health, metrics, logger configuration, and application info.

In Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

In Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

After adding the starter and starting an application with a suitable web environment, you can use exposed web endpoints.

Example:

```text
GET http://localhost:8080/actuator/health
```

Basic result:

```json
{
  "status": "UP"
}
```

### 2.1. An Endpoint Existing Does Not Mean It Is Exposed over HTTP

Actuator includes many endpoints such as:

- `health`
- `info`
- `loggers`
- `metrics`
- `env`
- `beans`
- `conditions`
- `configprops`
- `threaddump`
- `heapdump`
- `prometheus` when a matching registry is present

However, **not all of them are exposed over the web by default**. In typical Boot configurations, `health` is the web endpoint exposed by default; to access `loggers` or `metrics` over HTTP, you need to configure exposure.

This is an important security choice: many endpoints reveal internal information or allow controlling the application.

### 2.2. Example: Exposing Required Endpoints

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,loggers
```

Then, depending on security and web configuration, the corresponding endpoints can be accessed under `/actuator/...`.

Do not set:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

in production without a clear reason, access policy, and protective measures.

### 2.3. Actuator Does Not Have to Use the Main Application Port

You can configure a separate management server port in supported environments:

```yaml
management:
  server:
    port: 9090
```

Then web management endpoints can be served on a port different from the main server.

Separating the port helps apply separate network policies, yet **does not automatically guarantee endpoint security**. You still need authentication, authorization, TLS, or appropriate network access restrictions.

## 3. What Are Loggers and Log Levels?

A logger is typically associated with a class or package name:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
```

SLF4J provides common levels:

- `TRACE`: very deep detail, typically used when tracing code execution paths.
- `DEBUG`: diagnostic information for developers.
- `INFO`: noteworthy operational events.
- `WARN`: abnormal situations where the application can still continue.
- `ERROR`: errors causing an operation to fail or requiring attention.

Example:

```java
log.info("Order accepted: orderId={}", orderId);

log.debug(
        "Order validation: orderId={} itemCount={}",
        orderId,
        itemCount
);

log.warn(
        "Payment retry: orderId={} attempt={}",
        orderId,
        attempt
);

log.error(
        "Payment failed: orderId={}",
        orderId,
        exception
);
```

The `{}` syntax parameterizes messages; passing a `Throwable` in the trailing cause position lets the backend record the stack trace.

### 3.1. Logger Names and Package Hierarchy

With:

```java
LoggerFactory.getLogger(
        "com.example.orders.service.OrderService"
);
```

the logger has the name `com.example.orders.service.OrderService`.

A logger can inherit its effective level from a parent logger if it has no explicit level of its own.

Example:

```text
ROOT = INFO
  └── com.example = DEBUG
        └── com.example.orders = (not explicitly declared)
             └── OrderService
```

`OrderService` can inherit effective level `DEBUG` from `com.example`.

### 3.2. Configured Level Differs From Effective Level

Two concepts:

- **Configured level:** the level directly configured for that logger, which can be `null` if inherited.
- **Effective level:** the log level actually applied after accounting for hierarchy and backend rules.

Example:

```text
ROOT: configuredLevel=INFO, effectiveLevel=INFO
com.example: configuredLevel=DEBUG, effectiveLevel=DEBUG
com.example.orders: configuredLevel=null, effectiveLevel=DEBUG
```

A logger having no configured level of its own does not mean it emits no logs.

## 4. Configuring Loggers via `application.yml`

The most common way to set log levels at startup is `logging.level`.

```yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
```

Meaning:

- By default the system logs from INFO upward.
- Package `com.example.orders` allows viewing DEBUG logs.
- Spring Web reduces verbosity to WARN for corresponding loggers.

Equivalent example in `application.properties`:

```properties
logging.level.root=INFO
logging.level.com.example.orders=DEBUG
logging.level.org.springframework.web=WARN
```

### 4.1. A Single Class Can Have Its Own Level

```properties
logging.level.com.example.orders.service.OrderService=TRACE
```

This configuration targets a specific logger name.

However, do not enable TRACE or DEBUG broadly in production long-term without considering:

- Log volume generated.
- Disk/network and storage costs.
- Data that might be exposed.
- Performance impact during high-frequency logging.

### 4.2. Configuration Does Not Guarantee a Log Line Will Always Be Emitted

If you set:

```properties
logging.level.com.example.orders=INFO
```

then:

```java
log.debug("Order id={}", orderId);
```

may not be emitted because DEBUG is lower than the effective level INFO.

Beyond log level, output also depends on backends, appenders, filters, sampling, and collector configuration.

### 4.3. Use Placeholders for Messages

Write:

```java
log.info(
        "Order created: orderId={} customerId={}",
        orderId,
        customerId
);
```

instead of:

```java
log.info("Order created: " + orderId);
```

Parameterized logging lets the backend defer string formatting when the level is disabled. However, Java still evaluates argument expressions before calling the logger, so do not put expensive computations inside DEBUG logs without care.

## 5. What Is `/actuator/loggers` Used For?

Actuator provides the `loggers` endpoint to **inspect logger configuration** and, if permitted, **change log levels at runtime**.

Example query:

```bash
curl http://localhost:8080/actuator/loggers
```

The endpoint can return the list of logger names and the levels supported by the logging system.

To inspect a specific logger:

```bash
curl http://localhost:8080/actuator/loggers/com.example.orders
```

Illustrative response:

```json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
```

Actual values depend on application configuration. `configuredLevel=null` can mean the logger is inheriting its level from a parent logger.

### 5.1. Why Change Levels While the Application Is Running?

Suppose production hits a rare bug. You want to temporarily increase log detail for package `com.example.orders.payment` briefly to gather evidence, without restarting a process serving live traffic.

If Actuator's `loggers` endpoint is exposed and appropriately protected, you can change that logger's configured level at runtime.

This is both a useful diagnostic tool and **a system control capability** that requires strict access restrictions.

## 6. Changing Logger Levels at Runtime

Example HTTP POST request to the `loggers` endpoint:

```bash
curl -X POST \
  http://localhost:8080/actuator/loggers/com.example.orders.payment \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}'
```

With the endpoint exposed, write operations allowed, and security satisfied, this request sets logger `com.example.orders.payment` to DEBUG.

Reading back:

```bash
curl http://localhost:8080/actuator/loggers/com.example.orders.payment
```

Illustrative response:

```json
{
  "configuredLevel": "DEBUG",
  "effectiveLevel": "DEBUG"
}
```

### 6.1. Clearing the Configured Level to Inherit

You can send `null` to clear a logger's explicit level:

```bash
curl -X POST \
  http://localhost:8080/actuator/loggers/com.example.orders.payment \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}'
```

Then the effective level falls back to the logger hierarchy and backend rules.

### 6.2. Is This Change Saved to `application.yml`?

**No.** Changing a logger via Actuator normally updates logging configuration **inside the running process**. It does not edit the project's `application.yml` file.

When the application restarts, the logging system re-initializes from configuration sources; previous runtime changes are typically lost.

Therefore:

- Use the endpoint for temporary diagnostics.
- Use configuration-as-code for stable log policies.
- Log/audit toggling DEBUG on and off if operational procedures require auditing.

### 6.3. Each Replica Has Its Own Logger State

If an application runs three replicas:

```text
orders-api replica A
orders-api replica B
orders-api replica C
```

changing a logger level via replica A's endpoint **does not automatically update** replicas B and C. It is per-process runtime state.

To change log levels consistently across an entire cluster, use operational tools/processes targeting the relevant instances or update deployment config and roll out.

### 6.4. Do Not Leave `POST` to `loggers` Public

The ability to alter log levels can cause an application to log sensitive data or increase I/O load. When exposing the endpoint, place it behind authentication/authorization and necessary network restrictions.

Do not allow arbitrary Internet users to send POST requests to `/actuator/loggers`.

## 7. What Are Metrics?

A **metric** is a measurement observable over time, typically used to compute rates, trends, or compare states.

Examples:

- Total requests processed.
- Duration of each HTTP request.
- Number of queued tasks.
- CPU utilization.
- JVM heap used.
- Retry counts.
- Connections in a pool.
- Exceptions or errors by category.

If logs are many “individual stories,” metrics are numerical series suited for aggregation and graphing.

### 7.1. Metric Names and Tags

A metric can have:

```text
name:  app.orders.created
tags:
  channel: web
  outcome: success
value: 128
```

`name` states what is measured; `tags` (labels/dimensions) group the data. For example, counting orders by channel.

Do not confuse metric tags with free-form log text. Tags create **distinct time series** in the monitoring backend, so the number of tag values directly impacts monitoring system cost and performance.

### 7.2. Three Common Meter Types

| Type | Description | Example |
|---|---|---|
| **Counter** | Value increasing with event occurrences | Number of created orders |
| **Gauge** | Measures current value that can go up or down | Queue depth |
| **Timer** | Records count and duration of operations | Order processing time |

In addition, Micrometer provides distribution summaries, long task timers, and other meter types suited to specific use cases.

## 8. Micrometer and `MeterRegistry`

Spring Boot uses **Micrometer** as its standard abstraction for metrics.

Important APIs:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
```

**`MeterRegistry`** is where meters are registered, looked up, and managed.

Diagram:

```text
Application code / Auto-configured instrumentation
                    │
                    ▼
               Micrometer API
                    │
                    ▼
               MeterRegistry
                    │
                    ▼
       Registry implementation/export
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    Prometheus              Other backend
         │                     │
         ▼                     ▼
      Scrape/query         Push/publish/query
```

Spring Boot Actuator and corresponding starters usually provide substantial automatic instrumentation. To export metrics to a specific backend, you may need to add a registry dependency and configure exposure/export.

### 8.1. Do Not Confuse `MeterRegistry` with the HTTP Endpoint

You can use `MeterRegistry` in code without exposing `/actuator/metrics` over HTTP.

Conversely, `/actuator/metrics` is a way to **inspect/diagnose** metrics inside the application, not necessarily the standard ingestion format of a monitoring backend.

For example, Prometheus normally scrapes `/actuator/prometheus`, rather than directly scraping JSON from `/actuator/metrics`.

## 9. The `/actuator/metrics` Endpoint

Expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Then:

```bash
curl http://localhost:8080/actuator/metrics
```

The response can list metric names recorded by the registry:

```json
{
  "names": [
    "jvm.memory.used",
    "process.cpu.usage",
    "http.server.requests"
  ]
}
```

This is an illustrative response. Actual metric names depend on dependencies, version, application type, and whether any activity has occurred.

### 9.1. Inspecting a Specific Metric

```bash
curl http://localhost:8080/actuator/metrics/jvm.memory.used
```

Illustrative response:

```json
{
  "name": "jvm.memory.used",
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 73400320.0
    }
  ],
  "availableTags": [
    {
      "tag": "area",
      "values": ["heap", "nonheap"]
    }
  ]
}
```

`VALUE` and the number in the example are purely illustrative. Specific tags and values may differ.

### 9.2. Filtering Metrics by Tags

Example:

```bash
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=area:heap"
```

The `tag=key:value` query selects meters matching supported tags.

When HTTP metrics have tags such as method, status, or URI template, you can also filter by the actual tags reported by the endpoint. Do not guess tag names/values if the application lacks the corresponding meter.

### 9.3. Why Might Metrics Not Appear Yet?

Some metrics are only created when instrumentation has matching dependencies or once the first operation occurs.

For example, `http.server.requests` might not appear yet if the app is not a web application, no requests have arrived, instrumentation is disabled, or the version/framework uses a different convention.

Do not conclude Actuator is broken simply because an anticipated metric name is missing from the list.

## 10. Counter: Counting Business Events

Suppose you want to know how many times the application created an order successfully.

A service can inject `MeterRegistry`:

```java
package com.example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MeterRegistry registry;

    public OrderService(MeterRegistry registry) {
        this.registry = registry;
    }

    public void createOrder(String orderId) {
        // Execute order creation business logic.
        saveOrder(orderId);

        registry.counter(
                "app.orders.created",
                "channel",
                "web"
        ).increment();
    }

    private void saveOrder(String orderId) {
        // Illustrative example: implement an actual repository.
    }
}
```

Each call to `increment()` increases the counter by one.

### 10.1. Counters Measure Events, Not Current State

Counters fit “how many times has it happened”:

```text
orders created total = 10
orders created total = 11
orders created total = 12
```

Do not use a counter to measure “how many orders are currently waiting.” Current state can rise or fall, so it normally fits a gauge.

### 10.2. Measure Rates Rather Than Looking at Raw Totals Alone

In a monitoring backend, a counter can be used to compute events per second or events per minute.

If an instance restarts, the in-process counter can reset to 0. Monitoring backends usually provide rate/increase functions that handle counter resets under suitable conditions.

Do not take two counter values far apart in time and assume their difference is always accurate without accounting for restarts, scrape gaps, and backend semantics.

### 10.3. Name Metrics Consistently

With Micrometer, dot-separated names such as:

```text
app.orders.created
```

are readable conventions. When exported to a backend, names may be converted to match backend naming conventions.

For example, Prometheus typically uses underscores and unit/type suffixes. Avoid hardcoding a backend-specific name in business logic when Micrometer's naming convention works.

## 11. Gauge: Observing Current Values

A gauge fits state that can increase or decrease:

- Queue depth.
- Busy worker count.
- Current connection count.
- In-flight task count.

Example object tracking queue depth:

```java
package com.example.orders;

import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import org.springframework.stereotype.Component;

@Component
public class QueueDepthMonitor {

    private final AtomicInteger depth = new AtomicInteger();

    public QueueDepthMonitor(MeterRegistry registry) {
        registry.gauge(
                "app.queue.depth",
                Tags.of("queue", "orders"),
                depth
        );
    }

    public void setDepth(int value) {
        depth.set(value);
    }
}
```

When code updates `depth`, Micrometer can observe the current value when the metric is read/published.

### 11.1. Do Not Increment a Gauge Like a Counter

If you need to count total processed tasks, use a counter. If you need to measure tasks currently waiting, use a gauge.

A queue depth might look like:

```text
09:00 -> 10
09:01 -> 25
09:02 -> 18
09:03 -> 2
```

Looking only at the final number cannot tell you how many tasks passed through the queue over the last hour; that is a separate question requiring a counter.

### 11.2. Avoid Creating Temporary Gauge Objects That Lose References

Micrometer often holds weak references to measured objects in several gauge mechanisms. If you create an object locally inside a constructor/method with no strong reference retained, the gauge can stop working reliably once the object is garbage collected.

In the `QueueDepthMonitor` example, the `depth` field is held by a long-lived bean, making it suitable for measurement.

### 11.3. When Fetching Queue Depth From an External System

If the queue lives in a message broker, use an appropriate API or exporter to retrieve queue depth. A local `AtomicInteger` inside the application does not automatically reflect the true queue depth of Kafka/RabbitMQ/SQS.

Only name a metric “queue depth” when the data source actually carries that meaning.

## 12. Timer: Measuring Duration and Execution Count

Timer is an essential meter type for latency.

Example:

```java
package com.example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final MeterRegistry registry;

    public PaymentService(MeterRegistry registry) {
        this.registry = registry;
    }

    public void pay(String orderId) {
        Timer.Sample sample = Timer.start(registry);

        try {
            performPayment(orderId);
        } finally {
            sample.stop(registry.timer(
                    "app.payment.duration",
                    "operation",
                    "pay"
            ));
        }
    }

    private void performPayment(String orderId) {
        // Call payment gateway and handle result.
    }
}
```

`Timer.Sample` captures the start time, then `stop(...)` records the duration into a Timer.

Using `finally` ensures duration is still recorded when the operation throws an exception. However, this simple timer does not classify the outcome yet.

### 12.1. What Measurements Does a Timer Typically Provide?

Depending on registry/backend, a Timer can support:

- Recording count (`count`).
- Total time (`total time`).
- Maximum duration in a recording window (`max`), depending on implementation/window.
- Histogram buckets and percentile estimates if enabled.
- Other statistics per registry.

Do not assume histograms or P95 are exported by default for every Timer. Configure distribution statistics appropriately.

### 12.2. Measuring Both Success and Error Outcomes

Example:

```java
public void pay(String orderId) {
    Timer.Sample sample = Timer.start(registry);
    String outcome = "success";

    try {
        performPayment(orderId);
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(registry.timer(
                "app.payment.duration",
                "operation", "pay",
                "outcome", outcome
        ));
    }
}
```

`outcome` has only two fixed values—`success` and `error`—keeping cardinality low.

If calling a gateway with retries, decide whether the Timer measures a single attempt, the entire workflow, or end-to-end response time. Metric names and documentation must reflect exactly what is measured.

## 13. Histograms and Percentiles: Reading Latency Properly

Suppose 100 requests have durations:

- 90 requests complete in 100 ms.
- 9 requests complete in 500 ms.
- 1 request takes 5 seconds.

The average may look quite good, yet the slowest requests still hurt user experience.

Key percentiles to watch:

- **P50:** roughly 50% of requests take no longer than this.
- **P95:** roughly 95% of requests take no longer than this.
- **P99:** roughly 99% of requests take no longer than this.

### 13.1. Percentiles Are Not Averages

Two systems can have the same average latency yet very different tail latency.

Example:

```text
System A: most requests 100 ms, almost no outliers
System B: most requests 20 ms, yet a few requests 5 s
```

Averages can mislead. For production APIs, operators typically track P95 or P99 alongside throughput and error rate.

### 13.2. Histograms Have a Cost

When histogram buckets are enabled, time-series count grows by:

```text
metric × label combinations × buckets
```

Therefore, do not enable histograms on every timer with uncontrolled tags. Pick critical latency metrics with bounded tag values and buckets tailored to SLO targets.

### 13.3. Do Not Average Per-Instance P95 Values

P95 computed independently per instance cannot be accurately aggregated using a simple arithmetic mean.

If system-wide P95 is needed, use histograms or appropriate aggregation mechanisms supported by the monitoring backend. This is why metric type and export format design matter—not just picking a number to display.

## 14. Metric Tags and the Cardinality Problem

Tags help slice metrics, yet carry huge risk if their values are nearly unbounded.

### 14.1. Low Tag Cardinality

Good example:

```text
app.orders.created
  channel=web
  result=success
```

A few controlled `channel`/`result` values:

```text
channel ∈ {web, mobile, partner}
result  ∈ {success, failure}
```

The number of tag combinations is finite and easy to track.

### 14.2. High Tag Cardinality

Do not do:

```java
registry.counter(
        "app.orders.created",
        "orderId",
        orderId
).increment();
```

If every order has a distinct ID, the system creates a new time series for almost every order.

Similarly, avoid using:

- `userId`.
- `sessionId`.
- Raw request URLs containing IDs.
- Email addresses.
- Trace IDs.
- Per-request generated UUIDs.
- Arbitrary error messages as tags.

Those values belong in **logs or traces**, not metric tags.

### 14.3. Why Does Cardinality Explode Quickly?

Suppose a metric has:

```text
10 routes
× 5 status categories
× 4 methods
× 3 instances
= 600 time series
```

Adding `userId` with 100,000 values makes potential combinations grow enormously.

This is an illustrative cardinality calculation, not a forecast of actual time series. Actual counts depend on combinations that really occur and how the backend handles them.

### 14.4. Use URI Templates Instead of Raw Paths

For HTTP request metrics, tag values like:

```text
/orders/{id}
```

are far more suitable than:

```text
/orders/123456
/orders/123457
/orders/123458
```

Spring Boot web instrumentation typically attempts to use route templates when routing info is available. Still, unmatched requests or custom tags can create unintended cardinality if raw paths are recorded.

## 15. Built-In Metrics That Are Commonly Useful

When Actuator/Micrometer and matching instrumentation are present, an application can expose many metrics.

| Group | Example Metric Names | Meaning |
|---|---|---|
| JVM | `jvm.memory.used` | JVM memory currently in use |
| JVM | `jvm.gc.pause` | GC pause duration |
| Threads | `jvm.threads.live` | Number of live Java threads |
| CPU | `process.cpu.usage` | Process CPU usage per registry |
| Process | `process.uptime` | How long the process has been running |
| HTTP | `http.server.requests` | Count/duration of HTTP server requests |
| Database pool | `hikaricp.connections.active` | Active connections when HikariCP instrumentation exists |
| Executor | `executor.active` or corresponding convention | Executor activity if instrumented |
| Disk | `disk.free` | Available disk space in matching meter source |

Exact names, presence, and tags depend on Spring Boot version, Micrometer, registry, platform, and runtime libraries. Do not treat this table as a guaranteed list in every application.

### 15.1. How Do JVM Metrics Help?

A `jvm.memory.used` chart might show memory usage rising steadily. Yet concluding a memory leak from heap used alone is premature.

You also need to check:

- Heap max/committed.
- GC frequency and pause time.
- Allocation rate if instrumented.
- Workload and traffic.
- Thread count.
- Container memory limits.

Metrics guide investigation; diagnosing a memory leak may require a profiler, heap dump, and deeper analysis.

### 15.2. What Do HTTP Metrics Tell You?

With `http.server.requests`, you can observe:

- Request count and rate.
- Duration.
- Status code/outcome groups.
- HTTP method.
- URI template.
- Exception tag when captured by instrumentation.

Some status labels may be transformed or lose granularity depending on the backend; check actual available tags before writing dashboard queries.

## 16. HTTP Traffic: Rate, Errors, Duration, Saturation

A useful observability framework for services is **traffic, errors, latency, and saturation**.

### 16.1. Traffic / Request Rate

Measures requests per second or requests per minute.

Example:

```text
09:00 - 100 req/s
09:05 - 250 req/s
09:10 - 270 req/s
```

Rising traffic does not automatically mean an error. It could be a marketing campaign, batch clients, or a client polling too frequently.

### 16.2. Error Rate

Example:

```text
total requests = 10,000
failed requests = 200
error rate = 2%
```

You need to define “failed” for your system:

- HTTP 5xx usually reflects server errors.
- HTTP 4xx may be normal input errors or incidents depending on the API.
- Upstream proxy timeouts may never produce an HTTP response from the application.
- Business failures might still return HTTP 200 if the contract is designed that way.

Thus HTTP error rate and business failure rate can differ.

### 16.3. Duration / Latency

Track P50/P95/P99 instead of averages alone.

An API that handles most requests very fast yet has a high P99 can still deliver poor user experience.

### 16.4. Saturation

Measures how close resources are to their limits:

- Connection pool active/idle/pending.
- Queue depth.
- Thread pool saturation.
- CPU.
- Memory/GC.
- Disk.
- Open connections.

Saturation rising alongside latency and error rate is a signal worth investigating. Still, do not jump to a cause without checking workload and dependencies.

## 17. Prometheus and `/actuator/prometheus`

Prometheus is a popular backend for storing and querying time series. With Spring Boot, you usually add the Micrometer Prometheus registry dependency.

Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Maven:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Expose the endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Then:

```bash
curl http://localhost:8080/actuator/prometheus
```

If registry and endpoint are properly configured, the response normally uses Prometheus/OpenMetrics exposition format instead of Actuator's metrics JSON.

### 17.1. Two Different Metrics Endpoints

| Endpoint | Primary Purpose | Typical Format |
|---|---|---|
| `/actuator/metrics` | Inspect metric list and details via Actuator | JSON |
| `/actuator/prometheus` | For Prometheus to scrape metrics | Text exposition |

Do not configure Prometheus to scrape `/actuator/metrics` merely because the endpoint name sounds right. Use the right endpoint and registry matching the backend.

### 17.2. Prometheus Needs Scrape Configuration

Merely enabling the endpoint does not mean Prometheus already knows where to collect.

Example minimal scrape config:

```yaml
scrape_configs:
  - job_name: "orders-api"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
```

This example assumes Prometheus can connect to `localhost:8080` from where it runs. In containers/Kubernetes, Prometheus's `localhost` is usually not the application container's localhost; use appropriate service/target addresses.

### 17.3. Backend Conventions Can Rename Metrics

Micrometer code:

```java
registry.counter("app.orders.created").increment();
```

In Prometheus output, names can be normalized and given suffixes per meter/backend type. Check the actual exposition output when writing queries rather than relying on Java method names in all cases.

## 18. What Question Does the `health` Endpoint Answer?

`/actuator/health` provides a health evaluation based on applied `HealthIndicator`s.

Simple example:

```bash
curl http://localhost:8080/actuator/health
```

Response:

```json
{
  "status": "UP"
}
```

If a critical indicator reports failure:

```json
{
  "status": "DOWN"
}
```

Actual output also depends on health aggregation, health groups, enabled indicators, and how the application manages state.

### 18.1. `UP` Is Not a Guarantee of Perfect Business Behavior

`UP` means configured health checks evaluated as healthy at the moment of inspection.

It **does not mean**:

- Every endpoint is responding within allowed latency.
- No requests are failing.
- The database never times out.
- All queues are empty.
- All external services are available.
- There is no memory leak.

Health checks are a useful signal with a limited scope.

### 18.2. Health and HTTP Status

In common Actuator configuration, certain health statuses map to HTTP statuses:

- `UP` typically corresponds to HTTP 200.
- `DOWN` or `OUT_OF_SERVICE` typically corresponds to HTTP 503.
- Custom statuses may require appropriate mapping.

When designing readiness probes, orchestrators typically care more about HTTP success/failure status than full JSON details.

### 18.3. Health Details Can Be Sensitive

For example, a datasource health indicator may report details about the dependency. Restrict showing details to unauthorized callers.

Common property:

```yaml
management:
  endpoint:
    health:
      show-details: never
```

Modes can include `never`, `when_authorized`, and `always` depending on version. In production, avoid exposing `always` publicly if details could reveal infrastructure.

## 19. Writing a Custom `HealthIndicator`

Spring Boot lets you register a `HealthIndicator` for a subsystem the application wants to check.

Example of a simple local check:

```java
package com.example.orders.health;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class OrderProcessingHealthIndicator
        implements HealthIndicator {

    private final OrderProcessingState state;

    public OrderProcessingHealthIndicator(
            OrderProcessingState state
    ) {
        this.state = state;
    }

    @Override
    public Health health() {
        if (state.isOperational()) {
            return Health.up()
                    .withDetail("component", "order-processing")
                    .build();
        }

        return Health.down()
                .withDetail("component", "order-processing")
                .build();
    }
}
```

Where `OrderProcessingState` is an application-defined abstraction, for example:

```java
package com.example.orders.health;

import org.springframework.stereotype.Component;

@Component
public class OrderProcessingState {

    public boolean isOperational() {
        // Example: fast local state check.
        return true;
    }
}
```

The indicator returns state at query time.

### 19.1. Naming and Aggregation

A bean `OrderProcessingHealthIndicator` is typically mapped to a health contributor with an inferred name like `orderProcessing`.

It can participate in aggregate health depending on `HealthContributorRegistry` and configured health groups.

Do not add an indicator reporting `DOWN` for a non-essential condition if that causes the orchestrator to pull the entire service out of traffic unnecessarily.

### 19.2. Health Checks Must Be Fast and Bounded

Do not run a heavy query or call an external service without a timeout whenever the health endpoint is called.

Health probes can run frequently. A hanging check can itself increase load and distort operational status.

If external dependencies must be checked, design:

- Short, explicit timeouts.
- Caching policies when appropriate.
- Suitable health group boundaries.
- Separation of mandatory vs. optional dependencies.
- Avoidance of side effects.

## 20. How Do Liveness and Readiness Differ?

Two signals are especially important in container orchestration.

**Liveness** answers:

> “Is this process in a state that needs a restart?”

**Readiness** answers:

> “Is this instance ready to receive traffic?”

The two questions are not the same.

| Scenario | Liveness | Readiness |
|---|---|---|
| Instance just started, warm-up incomplete | Usually alive | Not ready yet |
| Instance operating normally | Live | Ready |
| Instance wants to pause receiving traffic | Still live | Not ready |
| Process hit an unrecoverable failure | Possibly not live | Not ready |
| An external dependency has an outage | Does not necessarily affect liveness | Can affect readiness if mandatory dependency |

### 20.1. Why Not Put Every Dependency Into Liveness?

Suppose the database temporarily loses connectivity for 30 seconds. If every application instance's liveness depends directly on the database, the orchestrator could continuously restart all instances right while the database is struggling.

This can trigger a **restart storm** and worsen the situation.

Liveness should reflect local state indicating the process genuinely needs a restart. Dependency availability is usually better evaluated in readiness or a dedicated metric/alert, depending on design.

### 20.2. Readiness Is Not a Latency Metric

Readiness only permits/denies receiving traffic per policy. An instance can be “ready” yet still slow.

Therefore, combine readiness with request duration, error rate, queue depth, and resource metrics.

## 21. Spring Boot Availability States

Spring Boot provides the `ApplicationAvailability` abstraction with two state groups:

- `LivenessState`.
- `ReadinessState`.

Representative states:

```text
LivenessState.CORRECT
LivenessState.BROKEN

ReadinessState.ACCEPTING_TRAFFIC
ReadinessState.REFUSING_TRAFFIC
```

During a typical startup lifecycle:

```text
SpringApplication starts
        │
        ▼
Prepare and refresh context
        │
        ▼
ApplicationStartedEvent
        │
        ▼
LivenessState.CORRECT
        │
        ▼
ApplicationRunner / CommandLineRunner
        │
        ▼
ApplicationReadyEvent
        │
        ▼
ReadinessState.ACCEPTING_TRAFFIC
```

The diagram illustrates key milestones; availability states are also influenced by events and the shutdown lifecycle.

### 21.1. Reading State From `ApplicationAvailability`

```java
package com.example.orders;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityReporter {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(
            ApplicationAvailability availability
    ) {
        this.availability = availability;
    }

    public boolean isAcceptingTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }

    public boolean isLive() {
        return availability.getLivenessState()
                == LivenessState.CORRECT;
    }
}
```

You can read these two states in code if there is a suitable use case, yet do not check them on every request just to decide every business action when the orchestration layer already uses readiness.

### 21.2. Changing Readiness Intentionally

For example, an application needs to stop accepting traffic temporarily before performing maintenance:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
);
```

When maintenance finishes and the application can receive traffic again:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.ACCEPTING_TRAFFIC
);
```

This controls the application's own readiness, not a way to “fix” any dependency failure. State transitions must be carefully designed to avoid declaring ready before the application is actually ready.

## 22. Actuator Liveness/Readiness Probes

When health probes are enabled, Spring Boot provides the corresponding health groups.

Example endpoints:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

In a Kubernetes environment detected by Spring Boot, probes may be enabled automatically; in other environments, you can enable them explicitly:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Then test:

```bash
curl http://localhost:8080/actuator/health/liveness
curl http://localhost:8080/actuator/health/readiness
```

### 22.1. Purpose of Each Probe

Liveness normally uses the application's liveness state; readiness normally uses readiness state. Health groups can be configured with additional indicators when appropriate.

Do not add every external dependency to the liveness group just to “check thoroughly.” Consider the consequences if the dependency fails and the orchestrator restarts multiple instances.

### 22.2. Probes on a Separate Management Port

If the management server runs on a separate port, the health endpoint may respond fine while the main HTTP server has trouble. That is a known operational limitation.

In some Spring Boot lines, you can configure additional probe paths on the **main server port** so probes test closer to real traffic paths. Check capabilities and properties for your version.

### 22.3. Example Kubernetes Probe

A conceptual configuration:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

This is only a path example, not timing advice for all applications. Choose `startupProbe`, `failureThreshold`, `timeoutSeconds`, and `periodSeconds` based on actual startup time and failure behavior.

## 23. Startup, Readiness, and Shutdown

Observability is not only watching state while requests are processed; lifecycle signals matter too.

### 23.1. Startup

An application may have opened its TCP port before completing warm-up or startup tasks. Do not rely solely on port listening to conclude a service is ready.

`ApplicationRunner` and `CommandLineRunner` can execute mandatory tasks before the ready milestone is published.

If a runner blocks too long or throws an exception, the application may not reach `ApplicationReadyEvent`.

### 23.2. Shutdown

When the application begins stopping, readiness can transition to refusing traffic according to lifecycle. Combining this with graceful shutdown at the web server and orchestrator helps reduce interrupted requests.

Example web server graceful shutdown configuration in supported versions:

```yaml
server:
  shutdown: graceful
```

Time allowed for shutdown phases can be bounded via Spring Boot lifecycle configuration:

```yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

These properties apply in supported applications/embedded servers and do not automatically ensure every external resource closes cleanly on its own.

### 23.3. Tracking Restarts and Uptime

Metrics like `process.uptime` or orchestrator signals show how long an instance has run and whether unexpected restarts occur.

Example:

```text
Instance A uptime: 3 days
Instance B uptime: 2 minutes
Instance C uptime: 1 minute
```

If B/C repeatedly show very short uptimes, investigate startup failures, liveness restarts, memory limits, and deployment events.

Uptime alone does not explain why a restart happened; it is a guiding signal.

## 24. Application Events and Operational Signals

Spring Boot emits lifecycle events you can use to observe startup.

Example:

```java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ApplicationLifecycleLogger.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("Application startup completed and ready");
    }
}
```

This is a lifecycle event log, not a substitute for orchestrator readiness endpoints/metrics.

### 24.1. Do Not Arbitrarily Block the System in Event Listeners

A synchronous listener can prolong event processing depending on the event multicaster and configuration. Avoid putting heavy tasks inside a lifecycle listener just to emit a log line.

### 24.2. Events Differ From Alerts

A log “Application is ready” is an event. An alert “10 restarts in 5 minutes” normally requires a backend or monitoring system applying rules over time.

Do not mix the two concepts: a Spring event is not automatically an alert sent to the operations team.

## 25. Connecting Logs and Metrics With Context

Suppose the metric:

```text
app.payment.duration{outcome="error"}
```

spikes suddenly alongside error rate. You need related logs to know which operation and which dependency caused it.

Logs might contain:

```text
Payment failed: orderId=ORD-123 gateway=primary attempt=3
```

While metrics should keep stable labels:

```text
operation=pay
gateway=primary
outcome=error
```

**Order ID** belongs in logs, yet should not be a metric tag due to very high cardinality.

### 25.1. Correlation ID

A request ID or trace ID in logs helps track events belonging to the same operation.

Example:

```text
traceId=abc123 INFO Order accepted orderId=ORD-123
traceId=abc123 DEBUG Calling payment gateway
traceId=abc123 ERROR Gateway timed out
```

Using SLF4J MDC or integrated tracing lets you attach correlation fields to logging events.

### 25.2. MDC Does Not Automatically Propagate Across All Threads

MDC typically relies on thread-local state, so when using `@Async`, executors, or reactive programming, appropriate context propagation is needed.

Do not assume calling `MDC.put("traceId", ...)` in a controller automatically makes the value appear in every asynchronous callback.

### 25.3. Tracing Is a Complementary Piece

Spring Boot integrates with Micrometer Observation/Tracing with appropriate versions and dependencies. Yet merely adding `spring-boot-starter-actuator` does not mean the application exports end-to-end distributed traces to a backend.

You need appropriate bridges, exporters, sampling, and collectors. This lesson only notes where traces fit in observability; metrics and logs remain valuable on their own.

## 26. A Spring Boot Example With Logs, Counter, and Timer

Let us design a simple order-processing application. The goal is seeing all three signals appear together:

- Logs describing events.
- Counters counting successful/failed orders.
- Timers measuring processing duration.

### 26.1. Gradle Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

The example assumes the project manages versions and repositories matching the Spring Boot plugin in use.

### 26.2. `application.yml` Configuration

```yaml
spring:
  application:
    name: orders-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,loggers
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  metrics:
    tags:
      application: orders-api

logging:
  level:
    root: INFO
    com.example.orders: INFO
```

This is a learning configuration. In production, endpoints like `loggers` and `metrics` must be protected with appropriate network/security controls. Do not copy this exposure config verbatim into an Internet-facing service without designing access control.

### 26.3. Main Application

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 26.4. Service With Metrics and Logger

```java
package com.example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    private final MeterRegistry registry;

    public OrderService(MeterRegistry registry) {
        this.registry = registry;
    }

    public String create(String orderId, boolean fail) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            log.info("Creating order: orderId={}", orderId);

            if (fail) {
                throw new IllegalStateException(
                        "Simulated order processing failure"
                );
            }

            registry.counter(
                    "app.orders.processed",
                    "outcome",
                    "success"
            ).increment();

            log.info("Order created: orderId={}", orderId);
            return "created";

        } catch (RuntimeException ex) {
            outcome = "error";

            registry.counter(
                    "app.orders.processed",
                    "outcome",
                    "error"
            ).increment();

            log.error(
                    "Order processing failed: orderId={}",
                    orderId,
                    ex
            );
            throw ex;

        } finally {
            sample.stop(registry.timer(
                    "app.orders.processing.duration",
                    "outcome",
                    outcome
            ));
        }
    }
}
```

Here, only two fixed `outcome` values exist, without creating metric tags from `orderId`.

Note that the example deliberately logs the exception in the service for illustration. In a real application, if controller advice also logs the same exception at ERROR, define clear error boundaries to avoid duplicate stack traces.

### 26.5. Controller

```java
package com.example.orders;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping("/orders")
    public ResponseEntity<String> create(
            @RequestParam String orderId,
            @RequestParam(defaultValue = "false") boolean fail
    ) {
        return ResponseEntity.ok(service.create(orderId, fail));
    }
}
```

This example uses query parameters solely for quick illustration; production APIs should have proper validation, request bodies/contracts, and error handling.

### 26.6. Trying Two Test Requests

Success:

```bash
curl -X POST "http://localhost:8080/orders?orderId=ORD-001"
```

Simulated failure:

```bash
curl -X POST "http://localhost:8080/orders?orderId=ORD-002&fail=true"
```

Observations:

- Logs `Order created` or `Order processing failed`.
- Counter `app.orders.processed` with the corresponding outcome.
- Timer `app.orders.processing.duration` gains an observation.
- HTTP metrics can record the request and status.
- `/actuator/health` may still remain `UP` because one failed operation does not mean the process is unhealthy.

### 26.7. Viewing Metrics After Calling Requests

```bash
curl http://localhost:8080/actuator/metrics/app.orders.processed
```

Or filter:

```bash
curl "http://localhost:8080/actuator/metrics/app.orders.processed?tag=outcome:success"
```

Counter values and available tags will reflect operations that occurred in this instance.

### 26.8. Temporarily Raising DEBUG

```bash
curl -X POST \
  http://localhost:8080/actuator/loggers/com.example.orders \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"DEBUG"}'
```

In this example, only the logger level is raised. If code has no `log.debug(...)` calls, this change does not magically generate extra DEBUG messages from that class.

## 27. Minimal Operational Signals for an API

A Spring Boot REST API can start with a basic observability set:

| Signal | Operational Question | Suggested Action |
|---|---|---|
| Liveness | Does the process need a restart? | Suitable probe for orchestrator |
| Readiness | Can it accept requests? | Add/remove instance from traffic |
| Request rate | How much traffic is arriving? | Monitor load and capacity |
| Error rate | How many requests fail? | Alert when exceeding a significant threshold |
| P95/P99 latency | How slow is it for users? | Find bottlenecks |
| JVM memory + GC | Are memory/GC abnormal? | Investigate heap/GC |
| CPU usage | Is the process near limits? | Investigate saturation |
| Database pool | Is the pool starved for connections? | Inspect pool/queries |
| Application logs | What errors occurred and in what context? | Investigate incidents |
| Application-specific metrics | Is the business workflow healthy? | Track rates, queues, failures |

The signal set should adapt to the application type:

- Batch job: job success/failure/duration.
- Message consumer: processing rate, lag, DLQ count.
- Scheduler: last execution, duration, and failure count.
- API gateway: upstream error rate, latency.
- Background worker: queue depth, saturation, and retries.

No single metric set fits every service.

## 28. Alerting: Do Not Alert on Every `ERROR` Log

A system can have occasional ERROR lines from isolated bad requests while still serving well. Conversely, an application might silently emit no ERROR logs while request counts drop to 0 or latency spikes sharply.

Therefore, alerting typically relies on metrics and service objectives rather than counting the string “ERROR” in logs alone.

### 28.1. Example Alert Conditions

- HTTP 5xx rate rises above a significant percentage for 5–10 minutes.
- Readiness fails consecutively across multiple replicas.
- P95 latency stays elevated continuously.
- Queue depth rises without draining over an extended period.
- Process restarts occur too frequently.
- Critical scheduled jobs fail to complete within expected cycles.

These durations/thresholds are conceptual examples. Tune them to actual traffic, baselines, and system goals; a 5% error rate can be severe for a core API yet tell only part of the story on an experimental batch tool.

### 28.2. Avoiding Alert Fatigue

If alerts trigger too easily, operations teams receive too many unnecessary notifications and may miss real incidents.

Design:

- Thresholds meaningful to users.
- Reliable time windows and sample sizes.
- Routing/escalation policies.
- Short runbooks for each alert.
- Separation of informational signals from actionable alerts.

### 28.3. Health Does Not Replace SLOs

A service can always report `UP` while 20% of requests return errors or P99 latency is very high.

Thus, SLOs for availability/success and latency generally need to rely on traffic-level metrics/tracing, not health probes alone.

## 29. Securing Actuator and Observability Data

Observability endpoints are very helpful yet can also become an attack surface or information leak.

### 29.1. Minimal Exposure Principle

If only health is needed for the orchestrator:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

If monitoring needs Prometheus:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

If operations needs runtime loggers:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus,loggers
```

However, in the final case, suitable access controls must be added.

### 29.2. Authentication and Authorization

If Spring Security is on the classpath, how Spring Boot auto-configures Actuator protection depends on existing security configuration. When an application defines its own `SecurityFilterChain`, review the policy for Actuator endpoints: do not assume default auto-security still protects every endpoint as before.

You can use network separation, management ports, reverse proxies, or Spring Security filter chains so only operational subjects can access sensitive endpoints.

### 29.3. Higher-Risk Endpoints

For example:

- `env`, `configprops`: can reveal key names and internal configuration.
- `beans`: exposes application context structure.
- `heapdump`: can contain sensitive in-memory data.
- `threaddump`: exposes runtime internals.
- `loggers`: can alter log levels at runtime if write operations are enabled.

Do not expose these endpoints publicly just for debugging convenience.

### 29.4. Notes on Log Data

Even when Actuator is secured, log files or collectors can still contain secrets, tokens, or user data.

When logging:

- Choose non-sensitive business IDs.
- Never log raw passwords/tokens.
- Avoid dumping entire HTTP bodies.
- Check whether exception messages contain secrets.
- Use structured logging/escaping to prevent log injection.
- Set appropriate retention and access control.

## 30. Diagnosing When `loggers` or `metrics` Endpoints Are Unreachable

### 30.1. HTTP 404

Possibilities:

- Missing `spring-boot-starter-actuator`.
- Endpoint not exposed over web.
- Base path changed.
- Application uses a non-web environment.
- Prometheus registry missing, so `prometheus` endpoint is unavailable.
- Endpoint disabled or configuration/conditions do not match.

Check dependencies, effective configuration, and endpoint mappings of the actual application.

### 30.2. HTTP 401 or 403

The endpoint may exist yet be blocked by security policy.

- `401 Unauthorized` typically relates to missing/invalid authentication.
- `403 Forbidden` typically relates to authorization or another protective mechanism.

Do not disable Spring Security completely just to access metrics; configure permissions for the monitoring service or operator appropriately.

### 30.3. `GET loggers` Works, Yet `POST` Fails

Could be due to:

- HTTP write operations restricted.
- Security permissions.
- CSRF protection in certain configurations.
- Endpoint configured read-only in that environment.
- Invalid JSON payload or unsupported level.
- Proxy/firewall disallowing POST method.

Check HTTP status, server logs, and security configuration rather than concluding the endpoint “doesn't work” just because GET succeeds.

### 30.4. Metric Name Does Not Appear

Possible causes:

- No request/event has triggered meter creation yet.
- Micrometer registry not configured as expected.
- Instrumentation dependency missing.
- Metric filtered/disabled.
- Metric name differs by version.
- Application runs non-web, so HTTP server metrics do not exist.
- Custom service never called `increment()` or `record()`.

Some metrics may register lazily when the first event occurs.

### 30.5. Prometheus Scrape Empty or Target Not Found

Check:

1. Is the registry dependency present?
2. Is `/actuator/prometheus` exposed?
3. Are authentication/network policies suitable?
4. Can Prometheus reach the actual target?
5. Is the scrape path right?
6. Is TLS/proxy rewriting paths?
7. Is a target in another container being mistaken for `localhost`?

### 30.6. Health Always `UP` Even When Users Report Errors

Existing indicators may only check the process and basic dependencies, not reflecting business failures.

Check HTTP error rates, latency, logs, and custom metrics. Do not force the health endpoint to become a comprehensive business check for every request.

## 31. Avoiding Common Misconceptions

### 31.1. “Having Actuator means having a full monitoring system”

No. Actuator provides endpoints and integrations. You still need collection, metric storage, dashboards, alerts, and access control.

### 31.2. “Changing a logger via the endpoint edits `application.yml`”

No. Runtime logger levels normally live only in the running process and can be lost on restart.

### 31.3. “Metrics are just counted logs”

Not quite. Metrics use meter types and tags to record quantitative data; logs are detailed events. Metrics can be derived from logs in some platforms, yet the two models have distinct goals and costs.

### 31.4. “Every request should have a `requestId` metric tag”

No. Request IDs have very high cardinality. Use logs/traces for request-specific identifiers; metrics use finite dimensions.

### 31.5. “Health UP means the application has zero errors”

No. Health only represents the configured health checks at the moment of inspection.

### 31.6. “If a database is DOWN, liveness should also be DOWN”

Not necessarily. External dependency outages are not always a reason to restart every application instance.

### 31.7. “Prometheus reads JSON from `/actuator/metrics`”

Normally Prometheus scrapes `/actuator/prometheus` when the Micrometer Prometheus registry is present and the endpoint is exposed.

### 31.8. “Turning on DEBUG makes the app automatically print every needed detail”

No. DEBUG only allows existing log statements written at that level to be output. If code lacks log statements at the spot under investigation, changing the level generates no extra info.

### 31.9. “System P95 equals the average of each instance's P95”

No. Percentiles cannot be accurately aggregated simply by averaging separately computed percentiles. Histograms or suitable aggregation methods are required.

### 31.10. “Gauge and Counter are both just numbers”

Although both emit numbers, they represent different semantics. Counters count cumulative events; gauges measure current state that can go up or down.

## 32. Workflow for Observing a Spring Boot Incident

Suppose customers report the API is returning errors and running slowly.

**Step 1 — Check availability**

Inspect `/actuator/health` and configured readiness/liveness probes. Are instances being pulled from traffic? Are they restarting repeatedly?

**Step 2 — Check traffic and error rate**

Inspect request rate and status/outcome metrics. When did errors begin? Are they concentrated on one endpoint or system-wide?

**Step 3 — Check latency**

Inspect duration/P95/P99. Did speed degrade on all endpoints or just one operation?

**Step 4 — Check saturation**

CPU, memory/GC, thread pools, DB pools, queue depth. Is any resource hitting limits?

**Step 5 — Read logs with context**

Search by request ID, order ID, component, or error code. Inspect the `Throwable`/cause chain. Do not search only for the generic keyword `ERROR`.

**Step 6 — Temporarily change logger level if needed**

If authorized, raise DEBUG on a narrow package via the `loggers` endpoint briefly, then return it to the baseline level.

**Step 7 — If tracing exists, inspect request paths**

Identify which dependency call consumes time or times out.

**Step 8 — Check changes near the error timestamp**

Deployments, configuration, scaling, network policies, database maintenance, or traffic shifts.

**Step 9 — Assess impact and remediate**

Roll back, scale, shed load, fix the dependency, or adjust configuration per the true root cause. Do not restart en masse just because one indicator reports DOWN.

**Step 10 — Post-incident**

Add any missing metrics/logs/alerts so next time detection and diagnosis happen faster.

A good observability flow moves from **overall trends** to **specific cases**, and only then to technical root causes.

## 33. Hands-On Exercises

### Exercise 1 — Enabling Actuator

Add `spring-boot-starter-actuator` to a Spring Boot project. Start it and call `GET /actuator/health`. Observe the JSON status.

### Exercise 2 — Distinguishing `configuredLevel` and `effectiveLevel`

Configure `logging.level.root=INFO` and `logging.level.com.example=DEBUG`. Expose `loggers`, query a logger under `com.example`, and explain why `configuredLevel` can be `null` while `effectiveLevel` is DEBUG.

### Exercise 3 — Changing Log Level at Runtime

Use POST `/actuator/loggers/com.example` to set DEBUG, send some requests, then set `configuredLevel=null`. Check behavior and confirm config files were not modified.

### Exercise 4 — Counting Events With Counter

Inject `MeterRegistry` and create counter `app.orders.created`. Call the service three times and check the value via `/actuator/metrics/app.orders.created`.

### Exercise 5 — Classifying Success and Error

Create metric `app.orders.processed` with tag `outcome=success|error`. Test both scenarios and use query `tag=outcome:...` to filter.

### Exercise 6 — Creating a Gauge

Register gauge `app.queue.depth` backed by an `AtomicInteger` held by a bean with a strong reference. Change the value and inspect the metric.

### Exercise 7 — Measuring Time With Timer

Use `Timer.Sample` around a method with simulated latency. Inspect count, total time, and available statistics. Trigger an exception to confirm `finally` still records duration.

### Exercise 8 — Inspecting HTTP Metrics

Create a controller `GET /products/{id}`, send several successful and failing requests. Inspect `http.server.requests` and actual tags. Do not add product ID as a metric tag yourself.

### Exercise 9 — Exploring JVM Metrics

Inspect `jvm.memory.used`, `jvm.threads.live`, `jvm.gc.pause`, and `process.cpu.usage` if available. Explain each metric and limitations when inferring root causes.

### Exercise 10 — Enabling Prometheus

Add `micrometer-registry-prometheus`, expose `prometheus`, and access `/actuator/prometheus`. Compare its format with `/actuator/metrics`.

### Exercise 11 — Testing Liveness and Readiness

Enable probes, call `/actuator/health/liveness` and `/actuator/health/readiness`. Explain why statuses can differ during startup.

### Exercise 12 — Custom `HealthIndicator`

Create a `HealthIndicator` based on local state. Have it alternately report UP/DOWN, observing health aggregation and HTTP responses per configuration.

### Exercise 13 — Seeing How `ApplicationRunner` Affects Readiness

Create an `ApplicationRunner` performing a brief task before becoming ready for traffic. Observe the `ApplicationReadyEvent` milestone and readiness state during startup.

### Exercise 14 — Avoiding High-Cardinality Tags

Write a counter with `orderId` as a tag, then explain how time-series counts can grow with every order. Refactor it to bounded `channel`/`outcome` tags.

### Exercise 15 — Securing Actuator

Configure minimal endpoint exposure. If Spring Security is present, allow only operational roles/authorities to access `loggers` and sensitive metrics. Verify 401/403 responses and do not leave internal endpoints public.

### Exercise 16 — Building a Mini-Dashboard

From built-in metrics, design a dashboard showing request rate, HTTP error rate, P95 latency, JVM heap, and process uptime. Note which question each panel answers.

### Exercise 17 — Designing Meaningful Alerts

Pick a test API, define a simple SLO, and create an alert condition when errors or latency stay bad over a time window. Explain why you should not alert on an isolated ERROR log.

### Exercise 18 — Incident Workflow

Simulate a timeout in a downstream service. Use health, request metrics, logs, and (if available) traces to diagnose. Record which signal appeared first, which helped pinpoint the cause, and what was still missing.

## 34. Official References

- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint catalog, exposure, access, and security.
- [Spring Boot Reference — Monitoring and Management](https://docs.spring.io/spring-boot/reference/actuator/index.html): overview of production-ready features.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, `MeterRegistry`, metrics export, and custom instrumentation.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): configuring logger levels and logging system.
- [Spring Boot Reference — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability): liveness/readiness states and availability events.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): Counter, Gauge, Timer, registries, tags, and distribution statistics.
- [Prometheus Documentation — Exposition Formats](https://prometheus.io/docs/instrumenting/exposition_formats/): scrape mechanics and metric formats.
- [Spring Boot API — HealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/HealthIndicator.html): custom health contributions.

**The core point:** `loggers` adjusts the detail level of events you need to read; `metrics` measures frequencies, latency, errors, and resource usage over time; `health`, `liveness`, and `readiness` help operations systems decide an instance's state. A well-observed application does not simply turn on lots of endpoints—it chooses the right signals, keeps metric tags low-cardinality, protects data and access permissions, knows when to look at logs versus metrics, and connects them into an actionable incident response process.

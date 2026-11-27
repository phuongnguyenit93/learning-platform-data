# Avoiding Telemetry Blocking Requests in Spring Boot

> **Chapter:** Observability Performance  
> **Lesson:** Avoiding Telemetry Blocking Requests  
> **Module:** SPRING_BOOT_OBSERVABILITY — Setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing. Learn context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

## 1. Why Must Telemetry Never Block Requests?

Observability helps understand what an application is doing, yet instrumentation and sending telemetry also consume resources. If a request thread must wait for an exporter to transmit spans over the network, a log appender to write slowly to disk, or a metrics registry to perform expensive synchronous work, the observation system can increase latency of the very system being observed.

**Non-blocking telemetry** means the business processing path does not wait for external telemetry backend export work to complete. The application still creates metadata and records events at a small cost; batching, serialization, and data transmission should be handled through appropriate mechanisms, usually asynchronously.

Signals to consider:
- Metrics: updating meters in-process and scraping/exporting.
- Traces: creating spans, ending spans, sampling, batching, and exporting.
- Logs: creating log events, formatting, enqueueing, writing to file/stdout, and shipping to a collector.
- Events/audit: may have different durability requirements than diagnostic telemetry.

Not every telemetry operation is automatically asynchronous. An instrumentation API may perform synchronous work on the request thread; you need to understand the implementation, exporter, appender, and registry you are using.

~~~mermaid
flowchart LR
  A["Request thread"] --> B["Business operation"]
  B --> C["Record observation / span / log event"]
  C --> D["Bounded in-process buffer"]
  D --> E["Background worker / batch processor"]
  E --> F["OTLP collector / log backend"]
  C --> G["Metrics registry"]
  G --> H["Scrape / export"]
~~~

## 2. Distinguishing Instrumentation Cost from Export Cost

A request can incur two groups of costs:

| Category | Examples | How to control |
| --- | --- | --- |
| Instrumentation | Creating spans, reading clocks, adding attributes, tag lookups | Keep operations reasonable, low-allocation, low-cardinality |
| Export | Serialization, batching, network I/O, retries, compression | Batch processor, async exporter, timeouts, bounded queues |
| Logging | Message formatting, argument evaluation, appender I/O | Async appender, guard expensive formatting |
| Metrics | Updating counters/timers, meter lookups, histograms | Reuse meters; avoid dynamic tags and meter creation |

Asynchronous export does not make instrumentation free. If each request creates thousands of spans or serializes large payloads directly on the request thread, latency still increases even though network sending runs in the background.

The goal is to keep synchronous work short, predictable, and bounded; deferrable I/O and batching work should be isolated from the request path.

## 3. Telemetry Operations That Commonly Cause Blocking

Common design mistakes:
- Calling an exporter directly on the request thread and waiting for a response.
- Using a synchronous log appender writing to disk or sending logs over the network.
- Calling a remote logging/analytics API inside a business method.
- Performing DNS/network lookups to resolve metadata on every request.
- Serializing large objects or reading request/response bodies just to log.
- Flushing the exporter after every single span.
- Retrying telemetry indefinitely when the collector fails.
- Using an unbounded queue that causes memory to grow continuously.
- Creating meters/spans with very high-cardinality tags or attributes.

Example of what not to do:

~~~java
public Order createOrder(Command command) {
    Order order = orderRepository.save(command);

    // Anti-pattern: request thread waits for remote telemetry service.
    telemetryClient.sendBlocking("order.created", order.id());

    return order;
}
~~~

If the telemetry backend slows down, business requests slow down too. If the telemetry backend goes down, business requests may fail even after the database successfully committed the order. This is unnecessary coupling.

## 4. Batch and Asynchronous Span Export

With the OpenTelemetry SDK, `BatchSpanProcessor` is commonly used to collect ended spans and export them in the background. The application does not have to send each span synchronously to the collector.

~~~java
SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .addSpanProcessor(
                BatchSpanProcessor.builder(otlpExporter)
                        .setScheduleDelay( Duration.ofSeconds(5))
                        .setMaxQueueSize(2048)
                        .setMaxExportBatchSize(512)
                        .build())
        .build();
~~~

This is an OpenTelemetry SDK API example; in Spring Boot, prefer compatible auto-configuration or starters rather than creating an extra SDK/tracer provider manually if Boot already manages it. Never register two tracer providers for the same application.

The batch processor usually has a finite queue. When the queue fills up, new spans may be dropped per policy; the exporter may retry within its own limits. This protects memory and request latency, though dropped spans and queue saturation must be monitored.

Method/configuration names may change by OTel SDK version. Use a compatible BOM and check the documentation for the deployed version.

## 5. Queues Must Be Bounded

An async pipeline needs a buffer between producers (request threads) and the consumer (background exporter). With an unbounded buffer, when the backend runs slower than telemetry generation, data piles up until the JVM runs out of memory.

Example:
- Application generates 10,000 spans/s.
- Exporter can only send 4,000 spans/s.
- Backlog grows by 6,000 spans/s.
- After 60 seconds, roughly 360,000 extra spans are waiting.

A bounded buffer forces a clear full-queue policy:
- Drop newest or drop oldest.
- Block producer (usually inappropriate for request telemetry).
- Sampling/priority policy before enqueueing.
- Reduce payload or export rate.
- Scale consumer capacity in a controlled way.

For diagnostic telemetry, intentional dropping is usually better than slowing down or crashing business requests. For audit/business events requiring durability, use a dedicated durable storage pipeline with explicit delivery guarantees.

## 6. Backpressure and Overload Policies

Backpressure regulates producers when consumers cannot keep up. On the request path, a telemetry queue must never block indefinitely. Choose overload policies based on data type:

| Data | Potentially suitable policy |
| --- | --- |
| Debug logs | Drop/sample under overload |
| Trace spans | Bounded queue, sampling, drop counters |
| Metrics | In-process aggregation, periodic scrape/export |
| Mandatory audit records | Durable queue/outbox with retry and delivery policy |
| Security events | Dedicated pipeline with loss control; alert on pipeline failure |

Do not lump mandatory audit events together with trace/debug telemetry under one drop policy. Each data type has different durability and privacy requirements.

Monitor queue depth, enqueue failures, dropped event counts, exporter errors, export duration, and worker utilization. Never emit synchronous logs every time a telemetry queue drops an item; use counters/gauges and sampled logs to avoid secondary overload.

## 7. Micrometer Observation on the Request Path

Micrometer Observation provides a lifecycle for recording operations. An Observation can be handled by handlers that emit metrics and tracing. Creating the observation/low-cardinality key-values still incurs cost on the executing thread.

~~~java
Observation.createNotStarted("orders.create", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> orderService.create(command));
~~~

Illustrative example of the synchronous API. Handlers can create spans and update metrics. Span export may be batched/async depending on the tracing bridge and exporter configuration.

To minimize overhead:
- Instrument only meaningful boundaries.
- Use finite low-cardinality values.
- Do not create batches of child spans for every tiny data row.
- Avoid computing expensive attributes if the span is unsampled and the value is unneeded for metrics.
- Never call a remote service to enrich tags.
- Use conventions to standardize metadata instead of duplicating complex logic.

Never write an Observation handler that performs synchronous network operations. Handlers run during lifecycle start/stop and can directly impact requests if their implementation blocks.

## 8. How Does Sampling Reduce Cost?

Sampling decides which traces are retained/exported. Head sampling can decide early when the trace starts; tail sampling typically decides after the collector receives enough spans or waits out a window.

For example, a 10% head sampling probability can cut exported traces under normal load. However, if all errors or slow traces must be kept, a more suitable policy or collector tail sampling is required.

Sampling should not be mistaken for guaranteeing exactly 10% of every traffic group. Results depend on the sampler, parent-based behavior, trace flags, and distributions.

Notes:
- Keep trace context propagation active even when a trace is not exported if supported by the integration.
- Never use sampling to replace metrics counters.
- Do not create spans just to count requests; use a `Counter`.
- Avoid logging sensitive trace bodies/attributes prior to sampling.
- Monitor sampled/dropped trace rates.

Sampling reduces export load, but does not eliminate all instrumentation cost and does not replace queue capacity planning.

## 9. Metrics: Update Locally, Export Separately

Micrometer `Counter`/`Timer` typically update state in-process. With Prometheus, the scraper reads metrics via an endpoint; business requests do not call Prometheus on every counter increment.

~~~java
@Component
public class OrderMetrics {

    private final Counter created;

    public OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordCreated() {
        created.increment();
    }
}
~~~

Create meters once and reuse them. Never create dynamic tag values per order ID or user ID. Dynamic meter creation can bloat the registry and waste CPU/memory.

Histogram/percentile configurations carry CPU and memory costs. Enable appropriate buckets only for key latencies; avoid hundreds of buckets across thousands of tag combinations.

## 10. Asynchronous Logging

Logging can become a bottleneck if request threads wait on file I/O, network appenders, or heavy message formatting.

Options:
- Write to stdout/stderr for runtime/agent collection if supported by the platform logging pipeline.
- Use an async appender with a bounded queue.
- Avoid synchronous network appenders on the request path.
- Reduce log volume on hot paths.
- Use parameterized logging to skip formatting when the level is disabled.
- Do not log payloads or repeat stack traces at every layer.

Example of parameterized logging:

~~~java
log.debug("Order created id={} channel={}", orderId, channel);
~~~

If DEBUG is disabled, the logging framework can skip formatting the message. However, argument expressions are evaluated before calling the method; avoid expensive function calls inside arguments:

~~~java
// Avoid expensive work on every request:
log.debug("Request details={}", buildLargeDiagnosticPayload());
~~~

You can guard with a log-level check before building payloads, or better yet, remove large payloads from the hot path and log small standardized metadata.

Async appenders have trade-offs: a full queue can drop logs, and unflushed logs can be lost on process crash. Choose queue size, discard policy, shutdown flush, and durability per requirements.

## 11. Do Not Treat Remote Logging as a Business Dependency

Do not call a log analytics HTTP endpoint directly inside controllers/services to record each event. Doing so turns the telemetry backend into a synchronous dependency.

~~~java
// Avoid this pattern in request handling:
logAnalyticsClient.publishBlocking(event);
~~~

Use a proper logging framework/appender or agent/collector. If an event must never be lost (e.g., audit), persist it via transaction/outbox or durable messaging and process it separately.

Never trade business consistency for successful log delivery. An order creation request must not return HTTP 500 just because the log collector is unavailable after the order has already committed.

## 12. Timeouts, Retries, and Circuit Breakers for Exporters

Exporters calling a collector/backend need finite timeouts. Retries must be bounded with backoff and jitter; infinite retries drive up backlog and network pressure.

Define:
- Export timeout.
- Max retry attempts or retry duration.
- Exponential backoff/jitter.
- Queue capacity.
- Export batch size.
- Behavior when the collector is unavailable.
- Shutdown flush deadline.

A circuit breaker can prevent an exporter from hammering a failing endpoint, but check whether the exporter SDK already includes a retry policy. Avoid stacking multiple retry layers that multiply requests.

Telemetry export failures should generally never fail business requests. Increment an exporter error metric and alert through an independent channel.

## 13. Context Propagation When Offloading to Background Workers

When a span is created during a request and exported on a background thread, the exporter needs the span context already captured in the span data. Do not rely on `ThreadLocal`/MDC from the request thread remaining valid when the worker runs.

For custom async processing:
- Capture context at the appropriate boundary.
- Propagate context across executor/reactive contexts per integration.
- Restore/clear context after the task to prevent context leakage across requests.
- Never store `traceId` in a static mutable variable.
- Never construct bogus parent-child relationships when batching multiple spans.

A log written on a background thread may miss MDC `traceId` if context is not propagated. Do not fix that by leaving `ThreadLocal` intact on the request thread after the request finishes.

## 14. Shutdown and Telemetry Flushing

During JVM shutdown, the batch processor may still hold spans/logs in queues. Flush within a finite deadline to avoid losing final data.

Workflow:
1. Stop accepting new requests or start graceful shutdown.
2. Finish in-flight operations within the shutdown budget.
3. Flush/shut down exporters and async appenders.
4. Wait up to the configured deadline.
5. Close resources and stop the process.

Never call `forceFlush` after every request. Flush periodically or at shutdown via the SDK lifecycle. Shutdown timeout must be smaller than the platform termination grace period so the process has time to finish.

If the collector is down, flushing may time out. Business shutdown must still finish on time; never wait indefinitely just to ship every telemetry record.

## 15. Measuring Observability Overhead

Never evaluate instrumentation by gut feeling alone. Compare identical workloads across configurations:
- Telemetry disabled (baseline).
- Metrics only.
- Tracing with sampling.
- Logging at normal levels.
- Full observability/export enabled.
- Slow or unavailable collector.

Measure:
- Request p50/p95/p99.
- Throughput.
- CPU and allocation rate.
- GC pauses/heap.
- Request thread utilization.
- Telemetry queue depth/drop counts.
- Export duration/errors.
- Log queue saturation.
- Memory when the collector is unavailable.

Use load tests with warm-up, concurrency, and a steady traffic mix. Test both steady state and bursts; async queues can mask latency briefly, yet backlogs will climb if consumers fall behind.

## 16. Troubleshooting Telemetry Slowing Down Requests

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| p95 rises when tracing is enabled | Excessive span creation/attributes or sync exporter | Profile request threads, inspect processor |
| Requests slow down when collector is down | Blocking/retrying exporter on request path | Async batching, timeouts, bounded queues |
| Heap grows steadily | Unbounded queue or backlog not draining | Queue size, drop policy, export rate |
| CPU spikes sharply | Serialization, compression, cardinality, or log formatting | CPU profile, batch size, tags |
| Request logging lags | Sync file/network appender or queue backlog | Appender config and queue metrics |
| Traces lost under high load | Full batch queue or sampler drops | Dropped spans, queue saturation |
| Shutdown loses final spans | No flush or deadline too short | SDK lifecycle, shutdown timeout |
| Trace ID missing on worker | Context not propagated | Executor/Reactor context integration |
| Requests fail when telemetry backend errors | Telemetry placed on critical path | Separate async/durable pipelines |
| Metrics registry bloats | Dynamic tags/meter creation | Tag cardinality and meter filters |
| Duplicate exports/request retries | Stacked retries or multiple SDKs | Exporter config and ownership |
| Async logs lose events on crash | Unflushed queue/insufficient durability | Use a durable path for mandatory events |

### Investigation Workflow

1. Compare latency with telemetry off vs. each signal enabled one by one.
2. Profile request threads for network/file I/O or serialization.
3. Check whether exporters/appenders run synchronously.
4. Inspect queue capacity, backlog, drop counts, and export throughput.
5. Check retries/timeouts when the collector is unavailable.
6. Review span counts, attributes, log volume, and metric cardinality.
7. Check context propagation across background workers.
8. Test graceful shutdown and flush deadlines.
9. Re-run load tests with the same workload after fixes.

## 17. Practical Scenario: Slow Collector Raises API Latency

**Scenario:** `order-service` enables tracing and OTLP export. When the collector becomes overloaded, API p95 jumps from 120 ms to 900 ms. CPU climbs and thread dumps show many request threads waiting on network calls.

### Step 1 — Locate I/O on the Request Path

Thread dumps/profiles show the exporter is invoked synchronously when spans end. Every request waits for the collector response.

### Step 2 — Switch to a Batch/Async Processor

Use `BatchSpanProcessor` aligned with your SDK/Boot integration, with a bounded queue and sensible batch size. Do not create a second tracer provider if auto-configuration already manages the SDK.

### Step 3 — Establish an Overload Policy

Set bounded queue capacity, export timeout, and retry limits. Monitor dropped spans when the collector falls behind. Never block request threads waiting for queue space.

### Step 4 — Trim Instrumentation Cost

Remove overly granular spans, drop expensive attributes, and control sampling. Use metrics to retain full request/error counts.

### Step 5 — Verify

Simulate a slow/down collector. Compare request p95/p99, CPU, queue depth, dropped spans, and export errors. The API must continue serving requests within resource limits; telemetry may degrade according to the chosen overload policy.

**Desired outcome:** telemetry backend failures do not cascade into failures or latency spikes in the business API, while the system still measures how much telemetry was dropped.

## 18. Labs and Self-Check Questions

### Lab A — Measure Baseline

Run a load test with telemetry off, then enable metrics, tracing, and logging step by step. Compare p95/p99, CPU, allocations, and throughput.

### Lab B — Collector Unavailable

Stop the collector in a test environment. Observe request latency, exporter queue, retries, drop counts, and heap. Verify requests never wait on network export.

### Lab C — Bounded Queue

Generate spans faster than export throughput. Observe queue saturation and drop policy. Compute backlog growth and pick appropriate capacity/alerts.

### Lab D — Async Logging

Compare a synchronous appender with an async appender under load. Simulate queue saturation and process shutdown. Identify which logs may be dropped vs. which require durable storage.

### Lab E — Context Propagation

Create a request span, schedule a background task, and log inside the worker. Verify trace context correctness, no MDC leakage across tasks, and no broken parent spans.

### Lab F — Graceful Shutdown

Create spans sitting in the batch queue and send SIGTERM. Verify flushing finishes within the termination grace period and the process still shuts down if the collector is unresponsive.

### Self-Check Questions

1. Why doesn't async export make instrumentation free?
2. How does `BatchSpanProcessor` help request latency?
3. What risks does an unbounded queue introduce?
4. When a telemetry queue fills up, what overload policies can be used?
5. Why shouldn't audit events share the same drop policy as debug traces?
6. What synchronous costs can Micrometer Observation incur?
7. How does a metrics `Counter` differ from span export?
8. What durability trade-offs does async logging carry?
9. Why shouldn't a controller call a remote log API synchronously?
10. Which costs does sampling reduce, and which does it not reduce?
11. How should exporter timeouts/retries be bounded?
12. How should context be propagated to background workers?
13. Why shouldn't you flush the exporter after every request?
14. Within what budget must shutdown flush telemetry?
15. How do you prove telemetry does not slow requests down under load?

**Completion criteria:** distinguish instrumentation vs. export cost; configure batch/async exporters; use bounded queues and overload policies; never call telemetry backends synchronously during requests; control logging, sampling, retries, and cardinality; propagate context; flush at shutdown; and benchmark when the collector is slow or unavailable.

## 19. Key Takeaways

- Telemetry must never force business requests to wait for network/file exports to complete.
- Instrumentation still carries CPU/allocation overhead even when exporters run asynchronously.
- Batch exporters collect spans and ship them in the background; they require bounded queues and export timeouts.
- Unbounded queues can drive heap usage to OOM when the backend slows down.
- Under overload, apply drop/sampling policies for diagnostic telemetry; mandatory audit data requires a dedicated durable pipeline.
- Micrometer Observation handlers must never perform synchronous network I/O inside start/stop callbacks.
- Metrics generally update the registry locally; avoid dynamic meter/tag creation.
- Async logging reduces blocking but carries queue-loss and shutdown durability trade-offs.
- Sampling cuts export volume, yet does not replace metrics or eliminate all instrumentation cost.
- Exporter retries/timeouts must be bounded; telemetry backend errors must never fail business APIs.
- Context propagation must work properly when handing off to worker threads; never retain `ThreadLocal`/MDC after a request finishes.
- Flush telemetry with a finite deadline on shutdown; never wait indefinitely.
- Use load tests and profiling to measure p95/p99, CPU, heap, queue saturation, and dropped telemetry.

## References

- [OpenTelemetry Java — Exporters and SDK](https://opentelemetry.io/docs/languages/java/sdk/)
- [OpenTelemetry Java — BatchSpanProcessor](https://opentelemetry.io/docs/languages/java/sdk/#span-processors)
- [OpenTelemetry Collector — Scaling and Resiliency](https://opentelemetry.io/docs/collector/resiliency/)
- [Micrometer Observation Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Logback — Appenders](https://logback.qos.ch/manual/appenders.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/)

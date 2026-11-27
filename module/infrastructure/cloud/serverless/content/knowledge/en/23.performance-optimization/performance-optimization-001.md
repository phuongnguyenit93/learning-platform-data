# Measuring Latency Percentiles and End-to-End Time Breakdown

A serverless API may have a median processing time of only 80 ms yet still leave a portion of users waiting over 2 seconds. Averages often hide this slow group of requests. To understand the actual experience, development teams need to measure **latency percentiles** such as p50, p90, p95, and p99, and then break a request down into observable intervals: gateway wait, instance initialization, Java processing, database/API calls, response serialization, and transferring the result back to the client.

In event-driven systems, you also need to measure the time a message spends waiting in the queue and the time from when an event is created until the business operation completes. A consumer that processes a message in 40 ms can still create a slow experience if the message waited 15 seconds in the queue.

This lesson focuses on how to define measurement boundaries, read percentiles correctly, combine metrics/logs/traces, and instrument Java functions to locate the step causing tail latency. The goal is to measure the entire flow under a consistent definition, then use that data to improve SLOs and performance.

## Learning Objectives

After this lesson, you will be able to:

- Explain p50, p90, p95, and p99 using a latency distribution.
- Distinguish between latency, duration, throughput, and queue wait.
- Choose measurement boundaries for HTTP requests and asynchronous events.
- Break down end-to-end latency into meaningful spans or stages.
- Understand why you cannot add up the p95 of individual dependencies to derive the p95 of the entire request.
- Use histograms and sample counts to track percentiles across multiple instances.
- Measure duration in Java using `System.nanoTime()`, Micrometer, and OpenTelemetry.
- Distinguish between cold start, handler duration, dependency latency, and network overhead.
- Identify the critical path when a request calls multiple dependencies sequentially or in parallel.
- Design load tests, dashboards, SLIs/SLOs, and alerts for tail latency.

## 1. Latency and Percentiles

**Latency** is the time from a defined start point to a defined end point. For example, HTTP end-to-end latency can be measured from when the client sends a request until the client receives the complete response. Server processing duration might only measure from when the application receives the request until it generates a response.

These two measurements are not the same. When comparing figures, you must know where each metric starts and ends.

### p50, p90, p95, and p99

A percentile is the value at or below which a given percentage of observations fall.

| Metric | Interpretation | Used to Understand |
|---|---|---|
| **p50** | 50% of requests have latency at or below this value | Typical experience at the middle of the distribution |
| **p90** | 90% of requests are at or below | The group slower than the common baseline |
| **p95** | 95% of requests are at or below | Tail latency commonly used in SLOs |
| **p99** | 99% of requests are at or below | Very slow group of requests |

For example, a service has 10,000 requests in a measurement window:

- p50 = 90 ms: roughly half of the requests complete in 90 ms or less.
- p95 = 650 ms: roughly 95% of the requests complete in 650 ms or less.
- p99 = 1,800 ms: roughly 99% of the requests complete in 1.8 seconds or less.

The rest of the distribution can have much higher latency. Some requests may take 5 seconds due to cold starts, connection pool waits, database locks, or retries.

~~~mermaid
flowchart LR
    A["Fastest"] --> B["p50"]
    B --> C["p90"]
    C --> D["p95"]
    D --> E["p99"]
    E --> F["Slowest 1% of requests"]
~~~

Percentiles are not error rates. A p99 of 1.8 seconds does not mean 1% of requests failed; it means 1% of requests fall above that latency threshold. Error rates must be tracked separately.

### Why Can Averages Be Misleading?

Suppose there are 100 requests: 99 requests take 50 ms and one request takes 5,000 ms.

- Average is approximately 99.5 ms.
- p50 is approximately 50 ms.
- p99 depends on the statistics system's percentile calculation rule, but it will reflect the slow tail near 5 seconds.

The average can look quite good while one in 100 requests is very slow. For services with fan-out or high traffic, a small percentage of slow requests can still affect many users.

Averages remain useful for calculating total resource usage or overall trends. However, to evaluate user experience and tail latency, inspect percentiles alongside sample counts and error rates.

### Percentiles Depend on Sample Count

p99 over 100 requests has very few observations in the tail; the result can fluctuate widely. When traffic is low, display the sample count and choose a window long enough to yield reliable data. Do not interpret a percentile calculated from just a few requests as a stable SLO.

Systems may use different interpolation or nearest-rank rules. When comparing dashboards or environments, use the same metric definition and the same calculation method.

## 2. Define Measurement Boundaries Before Instrumenting

Before adding timers, answer two questions:

1. **Where does measurement start?**
2. **Where does measurement end?**

An API can have multiple valid measurements:

| Measurement | Start | End |
|---|---|---|
| Client-perceived latency | Client starts sending request | Client receives complete response |
| Gateway/request latency | Gateway receives request | Gateway returns response |
| Application duration | Handler starts processing | Handler produces result or response |
| Dependency duration | Start calling database/API | Receive result or timeout |
| Queue wait | Broker accepts message | Consumer starts processing |
| Consumer processing duration | Consumer starts processing | Consumer ack/commit per definition |
| Business end-to-end latency | Business event occurs | Business outcome completes |

Do not call all of these values `latency` without specifying the scope. Metric names should reflect the boundary, such as `http.server.request.duration`, `orders.queue.wait`, or `orders.business.completion.duration`.

### Consistent Units and Clocks

- Use milliseconds or seconds consistently across dashboards and SLOs.
- For durations within the same process, prefer a monotonic clock such as `System.nanoTime()`.
- For timestamps used to correlate across services, use UTC and synchronize server clocks.
- Do not take timestamps from two different machines and subtract them directly without accounting for clock skew.
- Do not use wall-clock time to measure short durations within the same JVM.

`System.currentTimeMillis()` and `Instant.now()` represent calendar time; they can be adjusted by time synchronization or clock changes. `System.nanoTime()` is only suitable for calculating elapsed intervals, not timestamps that can be sent to another service.

## 3. End-to-End HTTP Request Breakdown

An HTTP request to a Java function or Cloud Run service can pass through multiple stages:

~~~mermaid
flowchart TD
    A["Client: DNS / connect / TLS"] --> B["Edge / API Gateway / load balancer"]
    B --> C["Platform routing / instance selection"]
    C --> D["Cold start or warm instance"]
    D --> E["Java handler / HTTP server"]
    E --> F["Authentication / validation / business logic"]
    F --> G["Database / cache / external API"]
    G --> H["Serialize response"]
    H --> I["Network response to client"]
~~~

A simple breakdown:

```text
Client-perceived latency
  = client/network setup
  + gateway/edge time
  + platform dispatch and queueing
  + instance initialization (if any)
  + application processing
  + response transfer
```

This is a conceptual model. Some stages may overlap, be measured at different boundaries, or already be included in gateway/platform metrics. Do not add metrics with overlapping scopes because you will double-count.

### Stages Typically Observed

| Stage | What to Measure | Signs of Slowness |
|---|---|---|
| DNS/connect/TLS | Time for client to establish connection | Slow before the request reaches the server |
| Gateway/edge | Request latency and integration latency if available | Slow gateway policy, authorizer, or upstream |
| Platform dispatch | Time waiting for an available instance | Increased load, lack of capacity, scale-out |
| Cold start/init | Runtime and application initialization time | Large image/JAR, heavy Spring context, init remote calls |
| Handler | Total processing time in the application | CPU, locks, validation, or slow code |
| Database | Connection acquisition, query, and transaction | Pool exhaustion, locks, queries missing indexes |
| External API | Connect, TLS, server response, retry | Rate limits, network, upstream degradation |
| Serialization | Converting objects to JSON/protobuf | Large payloads, reflection, or data copying |
| Response transfer | Response size and transfer time | Large response, bandwidth, or slow client |

### Do Not Add Overlapping Metrics

For example, API Gateway integration latency may already include most of the Lambda execution time and round trip. If you add integration latency to Lambda duration, you may count the Lambda processing portion twice.

Before building a dashboard, document the definition of each metric from the provider: resource, start/end points, unit, aggregation, and what is already included. If you do not know the boundary, treat the metric as an independent perspective rather than adding it into a formula.

## 4. End-to-End Event-Driven Breakdown

With a queue or event bus, the time from producer to business outcome typically includes:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker / Queue
    participant C as Consumer function
    participant D as Database / API
    P->>B: Publish event
    Note over B: Message wait / backlog
    B->>C: Deliver message
    Note over C: Cold start / dispatch
    C->>D: Process business operation
    D-->>C: Result
    C-->>B: Ack / commit
~~~

At least three measurements should be separated:

1. **Publish duration:** how long the producer takes to send the event and receive acknowledgment from the broker.
2. **Queue wait/age:** how long the message waits from when the broker receives it until the consumer starts.
3. **Processing duration:** how long the consumer processes from start until completion/ack according to the trigger's semantics.

In addition, you can measure **business completion latency** from when the business event occurs until the entire workflow finishes. For example, if an order is created at 10:00:00 but payment and inventory complete at 10:00:12, the business completion latency is about 12 seconds.

Do not equate consumer processing duration with end-to-end latency. A consumer running in 30 ms can still be processing a message that waited 20 seconds.

### Timestamps and Clock Skew

If the producer records `occurredAt` and the consumer records `processedAt`, subtracting the two timestamps depends on clock synchronization across hosts. A drift of a few hundred milliseconds can skew queue wait numbers, especially when the true latency is very short.

Prefer:

- Using enqueue/delivery timestamps provided by the broker when available.
- Using trace/span timestamps with synchronized clocks and accounting for skew.
- Recording event occurred time separately from broker publish time.
- Using a monotonic clock to measure processing duration within an invocation.
- Keeping event ID/correlation ID to link logs and traces, rather than relying solely on timestamps.

If you need to measure business completion across multiple services, define a canonical timestamp source and acceptable error margin. Do not use client timestamps sent by the user as a trusted baseline for SLOs.

## 5. Waterfall Traces and the Critical Path

A distributed trace represents a request as spans with start times, end times, and parent-child relationships. The waterfall view shows whether stages run sequentially or in parallel.

For example, a handler calls the database and then calls the payment API sequentially:

~~~text
HTTP server span       |-----------------------------|  420 ms
  validate             |--|                              15 ms
  database query       |--------|                         95 ms
  payment API          |----------------|                210 ms
  map + serialize      |---|                              30 ms
  other/overhead       |-------|                          70 ms
~~~

In this example, the payment API is the dependency taking the largest share of time. Optimizing the 15 ms validation will not significantly improve total latency if the payment API still takes 210 ms.

### Sequential vs. Parallel

If two dependencies run sequentially, the total duration is roughly the sum of each step's duration plus overhead.

If two dependencies run in parallel, the duration of the parallel branch is roughly equal to the slowest branch, not the sum of both.

```text
Sequential:
  total ≈ A + B + C + overhead

Parallel:
  total ≈ max(A, B) + join/overhead
```

The critical path is the chain of operations that determines the final completion time. A good trace helps reveal the critical path instead of merely ranking dependencies by individual duration.

Do not parallelize calls if they have data dependencies, unsafe side effects, or increase load on backends. Latency optimization must preserve correctness and bound concurrency.

### Do Not Add the p95 of Individual Spans

Suppose the database query p95 is 100 ms and the payment API p95 is 300 ms. You cannot conclude that the whole request's p95 is 400 ms. The two percentiles may belong to different requests; the distribution and correlation between stages determine the percentile of the sum.

To know the end-to-end p95, measure the duration of the root request directly. Use child spans to explain requests that fall into the tail. You can sum durations within the same trace when spans are sequential and non-overlapping, but percentiles of individual spans cannot be summed to produce an aggregate percentile.

## 6. Histograms, Percentiles, and Aggregation

To compute percentiles across multiple instances, systems typically need histograms or mergeable distribution data.

### Histograms

A histogram divides durations into buckets. For example:

| Latency Range | Request Count |
|---|---:|
| ≤ 50 ms | 120 |
| > 50 to ≤ 100 ms | 460 |
| > 100 to ≤ 250 ms | 310 |
| > 250 to ≤ 500 ms | 80 |
| > 500 ms to ≤ 1 s | 25 |
| > 1 s | 5 |

A histogram shows the distribution and allows combining counts from multiple instances across the same bucket boundaries. The backend can estimate percentiles from the histogram.

### Percentile Summaries vs. Histograms

A percentile calculated locally on each instance generally cannot be accurately aggregated by averaging those percentiles.

For example:
- Instance A has p95 = 100 ms with 10 requests.
- Instance B has p95 = 1,000 ms with 10,000 requests.

The average of the two p95 values is 550 ms, but that is not the p95 of all 10,010 requests.

For distributed systems, prefer histograms with appropriate buckets or a backend that supports mergeable distributions. If you use client-side percentiles, understand that those percentiles may only reflect individual instances/processes and cannot be accurately aggregated at the service level.

### Choosing Appropriate Buckets

Buckets should be concentrated around the latency region that matters for your SLO. If the target is 300 ms, you need dense buckets around 100–500 ms. Buckets that are too sparse yield inaccurate percentile estimates; too many buckets can increase time-series count and cost.

Keep the same bucket boundaries across revisions and environments if you want to compare them. Units must be consistent; avoid recording milliseconds in one metric and seconds in another.

## 7. Measuring Duration in Java with a Monotonic Clock

For synchronous code within a single JVM, use `System.nanoTime()` to measure elapsed time.

~~~java
import java.util.concurrent.TimeUnit;

public final class TimedOrderService {
    private final OrderService delegate;
    private final LatencyMetrics metrics;

    public TimedOrderService(
            OrderService delegate,
            LatencyMetrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    public OrderResult place(PlaceOrderCommand command) {
        long started = System.nanoTime();
        try {
            return delegate.place(command);
        } finally {
            long elapsed = System.nanoTime() - started;
            metrics.recordHandlerDuration(
                    elapsed, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Use `finally` to record duration even when processing fails. If you only record on success, dashboards will miss the latency of failed or timed-out requests.

Do not use `System.nanoTime()` as an event timestamp or send this value to another process. It only has relative meaning within the same JVM/process.

### Measuring Individual Dependencies

You can wrap dependency calls with a shared helper or instrumentation:

~~~java
long started = System.nanoTime();
try {
    return paymentClient.authorize(request);
} finally {
    long elapsed = System.nanoTime() - started;
    paymentMetrics.recordAuthorizeDuration(
            elapsed, TimeUnit.NANOSECONDS);
}
~~~

Metric names should indicate the dependency and operation. Do not add orderId, userId, or full URLs as metric tags. Specific IDs belong in controlled traces/logs.

## 8. Using Micrometer Timer to Measure Percentiles

Spring Boot commonly integrates Micrometer. `Timer` records count, total time, and duration distribution. The registry/exporter configuration determines which backend receives the metrics.

Example:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class OrderMetrics {
    private final Timer handlerTimer;
    private final Timer databaseTimer;

    public OrderMetrics(MeterRegistry registry) {
        this.handlerTimer = Timer.builder("orders.handler.duration")
                .description("Order handler duration")
                .publishPercentileHistogram()
                .serviceLevelObjectives(
                        java.time.Duration.ofMillis(100),
                        java.time.Duration.ofMillis(250),
                        java.time.Duration.ofMillis(500),
                        java.time.Duration.ofSeconds(1))
                .register(registry);

        this.databaseTimer = Timer.builder("orders.database.duration")
                .description("Order database operation duration")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordHandlerDuration(long amount, TimeUnit unit) {
        handlerTimer.record(amount, unit);
    }

    public <T> T recordDatabase(java.util.concurrent.Callable<T> action)
            throws Exception {
        return databaseTimer.recordCallable(action);
    }
}
~~~

Histograms and SLO buckets must be configured appropriately for your registry/backend. Not every exporter handles histograms the same way; verify the actual metrics in Cloud Monitoring or the metrics system in use.

Some registries support client-side percentiles via `publishPercentiles(0.50, 0.90, 0.95, 0.99)`. Those values are useful for a process-local view, but should not be assumed to aggregate accurately across multiple instances. If you need service-level percentiles, prefer histogram/distribution aggregation supported by the backend.

### Limiting Cardinality

Metric tags must have a small, bounded set of stable values:

- `operation=place_order`
- `dependency=database`
- `outcome=success|failure`
- `revision=stable|canary` or a backend-managed revision label

Do not use `orderId`, `customerId`, email, request ID, or raw URL paths as tags. Every new value can create a separate time series, rapidly increasing costs and query overhead.

## 9. Distributed Tracing with OpenTelemetry

Metrics tell you that a service has tail latency; traces help explain where a specific request was slow.

A trace should have:
- A root server span for the request or consumer invocation.
- Child spans for important business steps.
- Client spans for databases, HTTP APIs, or message publishes where instrumentation supports it.
- Error status and exception events when an operation fails.
- Attributes with diagnostic value and controlled cardinality.

Example of manual span creation in Java:

~~~java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class InventoryService {
    private final Tracer tracer;

    public InventoryService(Tracer tracer) {
        this.tracer = tracer;
    }

    public Reservation reserve(String sku, int quantity) {
        Span span = tracer.spanBuilder("inventory.reserve").startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("inventory.operation", "reserve");
            span.setAttribute("inventory.quantity", quantity);

            return reserveInternal(sku, quantity);
        } catch (RuntimeException error) {
            span.recordException(error);
            span.setStatus(StatusCode.ERROR, "Inventory reservation failed");
            throw error;
        } finally {
            span.end();
        }
    }

    private Reservation reserveInternal(String sku, int quantity) {
        // Call repository and apply reservation rules.
        return new Reservation(sku, quantity, true);
    }
}

record Reservation(String sku, int quantity, boolean reserved) {
}
~~~

The application needs the OpenTelemetry SDK or Java agent along with a configured exporter. Simply calling the API to create spans without an active SDK/exporter may mean spans never appear in the backend.

Do not record sensitive SKUs, customer IDs, tokens, or full payloads in spans if unnecessary. If you need correlation with specific entities, consider data policies and use controlled logs.

### Propagating Trace Context Across Boundaries

For HTTP, OpenTelemetry typically propagates W3C Trace Context via `traceparent` and `tracestate` when instrumentation is configured for client/server libraries.

For queues/events, the producer must propagate trace context via message attributes following the broker/instrumentation convention. The consumer extracts the context and creates an appropriate consumer span or span link. If context is lost, producer and consumer traces can become disconnected even if the event ID matches.

Keep `eventId` and `correlationId` separate from the trace ID. Trace sampling may drop a trace; event IDs are still needed for deduplication, replay, and business investigations.

### Sampling and Tail Latency

If you only sample a small random percentage, very slow requests might not have their traces stored. You can:
- Increase sampling in test environments or during investigations.
- Use tail-based sampling in a collector if the architecture supports it, retaining traces with errors or those exceeding a latency threshold.
- Rely on histograms/metrics to detect the tail, then query corresponding logs/traces.
- Keep sampling policies stable when comparing before/after a release.

Sampling affects observability, not the latency of requests as defined by metrics. However, overly heavy instrumentation or synchronous export can impact performance; exporters should operate asynchronously according to SDK guidance.

## 10. Cold Start, Warm Start, and Initialization

In serverless, the first request on a new instance may pay the cost of initializing the runtime and application.

Common sources of cold starts:

- Creating a new execution environment/container.
- Starting the JVM and class loading.
- Initializing the Spring application context.
- Loading dependencies, configuration, and secrets.
- Creating connection pools or clients.
- Downloading image/container layers or runtime artifacts.
- Initializing network interfaces or private connections.

Distinguish between:
- **Initialization duration:** the time from when the runtime/instance begins initializing until it is ready.
- **Handler duration:** the time the code spends processing the invocation/request.
- **End-to-end latency:** the time the caller actually waits, which may include init and platform overhead.

Not every user's first request is a cold start; a warm instance can handle the request immediately. Conversely, scale-out can spin up several new instances even when the service already has traffic.

### Measuring Cold Starts Separately

Record startup duration using lifecycle hooks or platform metrics. Correlate request latency with logs/traces to determine whether a request ran on a new instance.

On AWS Lambda, the REPORT log can show `Init Duration` for invocations that initialize an environment; the `Duration` metric mainly reflects handler execution time. On Cloud Run, observe container startup/instance metrics and request logs; platform metric definitions should be verified per service type and configuration.

Do not add init duration to handler duration if the request/platform metric already includes that time. Clearly identify what each metric counts.

### Improving Cold Starts

- Reduce artifact/image size and unnecessary dependencies.
- Avoid heavy remote calls in static initializers or constructors.
- Reuse thread-safe SDK clients across warm invocations.
- Reduce framework and bean initialization time.
- Only use minimum/provisioned capacity when target latency justifies the cost.
- Re-measure p95/p99 and startup duration after every change.

Do not defer essential configuration or security checks just to reduce startup. A function must fail clearly if it cannot run safely.

## 11. Databases and Connection Pools as Common Sources of Tail Latency

Increased handler duration is not necessarily caused by CPU. A request may spend most of its time waiting for a connection or the database.

Separate the measurements:

1. **Connection acquisition:** time waiting to acquire a connection from the pool.
2. **Query execution:** time the database spends executing the query.
3. **Result transfer/mapping:** time to receive and map results into objects.
4. **Transaction commit:** commit time if measured separately.
5. **Pool wait/timeout:** number of requests that had to wait or failed to acquire a connection.

If the connection pool is small, high concurrency can increase queuing inside the pool. If the pool per instance is too large, total connections during autoscaling can exceed database limits.

Estimate the upper bound:
```text
Potential connections ≈ max instances × pool size per instance
```

This is a theoretical limit; actual connection count depends on the number of instances and how the pool opens connections. Set max instances, pool size, and the database connection budget together.

### Database Trace Example

A trace might show:
- HTTP server span: 900 ms.
- Connection acquire: 520 ms.
- SQL query: 180 ms.
- Serialize/other: 100 ms.

Optimizing indexes will not solve the 520 ms spent waiting for the pool. You need to investigate connection counts, concurrency, leaks, transactions holding connections too long, and max instance counts.

## 12. External APIs, Retries, and Timeout Budgets

An external dependency can have variable latency and rate limits. Measure separately:
- DNS/connect/TLS if exposed by the client.
- Time to first byte or response duration.
- Retry count.
- Backoff time.
- Timeout count.
- Status/error category.

A logical request that retries three times can have a much higher total latency than a single attempt. Dashboards should distinguish:
- Duration per attempt.
- Total dependency time including retries.
- Number of attempts per logical operation.

Set dependency timeouts lower than the overall request timeout so there is still time to handle fallbacks and return a response. Exponential backoff with jitter helps avoid synchronized retry storms, though retries should only apply to transient errors and operations that are safe to retry.

If a request has a 5-second timeout, do not let the database timeout at 5 seconds and only then start serializing the response. Allocate budgets for authentication, database, external APIs, and overhead.

Example budget:

| Stage | Illustrative Budget |
|---|---:|
| Gateway/authentication | 100 ms |
| Java validation/business | 150 ms |
| Database | 700 ms |
| Payment API | 1,500 ms |
| Serialize/response overhead | 150 ms |
| Safety margin | 400 ms |
| **Total** | **3,000 ms** |

This is a hypothetical budget for illustration. Real budgets must be based on SLAs, measured percentiles, and each dependency's timeouts. Parallel stages can use different budgets than sequential stages.

## 13. Queue Wait, Backlog, and Consumer Processing

For queue-based functions, queue wait is often one of the main drivers of increased business latency.

Monitor:
- Message age or oldest unprocessed message.
- Queue depth/backlog.
- Publish-to-consume delay.
- Consumer processing duration.
- Batch size and batch duration.
- Retry count, visibility/ack deadline, and DLQ depth.
- Consumer concurrency and instance count.

If queue depth grows while processing duration remains steady, consumer capacity may be lower than the arrival rate. If queue depth is steady while message age grows, a partition/shard may be stuck or messages may be retrying repeatedly.

A batch consumer can process multiple messages in one invocation. Do not divide total batch duration by the number of messages and call that per-message latency if messages arrived at different times or were processed in parallel. Record enqueue timestamps and per-message processing times if precise analysis is required.

### Arrival Rate and Service Rate

If the message arrival rate exceeds the processing rate over an extended period, the backlog will grow.

```text
Backlog growth ≈ arrival rate - processing rate
```

When arrival rate exceeds processing rate, increasing concurrency or consumer count can help, but you must verify downstream database/API capacity. If a dependency is already at its limit, scaling consumers only turns a backlog into a connection storm or throttling.

## 14. Analyzing Percentiles by Route, Revision, and Dependency

An overall service p95 can hide a very slow route. Group by operationally meaningful dimensions:

- Route/operation (use route templates, not raw paths with IDs).
- Revision/version.
- Region.
- Success/failure outcome.
- Dependency or operation type.
- Trigger type or event type.
- Cold/warm classification if the platform provides a reliable signal.

Dashboard example:

| Group | p50 | p95 | p99 | Count |
|---|---:|---:|---:|---:|
| GET /orders/{id} | 45 ms | 180 ms | 450 ms | 20,000 |
| POST /orders | 90 ms | 620 ms | 1,900 ms | 8,000 |
| POST /payments | 140 ms | 1,100 ms | 3,200 ms | 2,000 |

These numbers are illustrative. POST /payments has a higher p95, so you need to inspect traces to see whether the slowdown lies in the payment provider, retries, or the database.

Do not create metric labels by userId, orderId, or requestId. Those dimensions cause rapid cardinality explosion. Use traces/logs to investigate individual requests.

## 15. Cloud Metrics, Logs, and Traces

The three observability signals complement each other:

| Signal | Role in Latency Analysis |
|---|---|
| Metrics/histograms | Shows p50/p95/p99, count, throughput, and trends over time |
| Request/container logs | Provides request ID, revision, status, errors, and timestamps |
| Distributed traces | Breaks a request into spans and reveals the critical path |

On AWS Lambda, you can correlate invocation count, duration, errors, throttles, and concurrent executions with logs/traces. Init duration may appear separately in logs/telemetry depending on runtime and configuration.

On Cloud Run, combine request latency, instance count, CPU/memory, startup metrics, and structured container logs. For event-driven workloads, monitor queue age/backlog at the broker alongside consumer duration.

Metric names, units, resource labels, and aggregations vary by provider and integration type. Before creating an SLO, verify whether the metric measures server processing or caller-perceived latency. If you need real user experience metrics, you can add client-side measurement or synthetic monitoring.

### Log Queries to Aid Investigation

A useful log entry typically contains:
- Trace ID/span ID.
- Request/correlation ID.
- Service and revision.
- Route template or event type.
- Duration and status/outcome.
- Dependency name and error category.

Do not log tokens, secrets, sensitive payloads, or unnecessary personal information. Log durations should use a consistent unit and meaningful field names.

## 16. Designing Latency SLIs/SLOs

A latency SLI is typically the proportion of eligible requests completing below a threshold.

Examples:
- 99% of valid requests complete within 500 ms over a 30-day window.
- 95% of order-creation requests complete within 1 second.
- 99% of events are processed within 30 seconds from when the broker receives the message.

These targets are examples, not platform defaults. Clearly define:
- Which requests/events belong in the denominator.
- Whether timeouts and errors count as bad events.
- Whether routes/priority tiers are separated.
- Whether measurement is from the client, gateway, broker, or application.
- The time window and how percentiles/histograms are computed.
- How canceled requests or client disconnects are handled.

An SLO like "99% of requests under 500 ms" can use the histogram bucket at 500 ms to compute the proportion of good events. This approach is generally much easier to aggregate across multiple instances than trying to average per-instance p95s.

### Tail Latency and User Impact

If a web page calls 20 services in parallel, the probability that at least one dependency is slow can be high even if each service has a good p99. Fan-out amplifies tail latency. Measure the root request end-to-end and its critical path, not just individual dependency SLOs.

## 17. Load Testing for Reliable Percentile Measurement

Measuring latency with a few manual requests is not enough. You need load tests that reflect real traffic.

### Test Types

| Test Type | Goal |
|---|---|
| Baseline | Measure the service at low load and standard configuration |
| Load test | Determine latency/throughput at expected load |
| Stress test | Find the saturation point and behavior beyond capacity |
| Spike test | Observe burst traffic and scale-out |
| Soak test | Detect leaks, pool exhaustion, or degradation over time |
| Cold-start test | Measure requests on new instances and startup duration |
| Dependency degradation | See how the system reacts when a database/API slows down or times out |

### Keep Scenarios Realistic

- Payloads, response sizes, and route mix similar to production.
- Controlled request arrival rate; do not rely solely on closed-loop clients.
- Concurrency and ramp-up simulating real traffic growth.
- Databases, caches, and external APIs with production-like behavior.
- Record error rate, throughput, and percentiles simultaneously.
- Sufficient sample count for meaningful p95/p99.
- Separate warm runs and cold-start runs.
- Run in a region and network path appropriate for the target environment.

A closed-loop load generator that sends a new request only after the previous one completes can slow down its sending rate when the service slows down, under-loading the system right when it is congested (coordinated omission). Arrival-rate-based testing controls the request rate independently of response time.

Do not use production traffic or sensitive data without proper approval and safeguards. Do not generate heavy load against real dependencies without limits and coordination with their owners.

## 18. Tail Latency Investigation Examples

### Scenario A: Stable p50, Spiking p99

- p50 remains 80 ms.
- p99 jumps from 500 ms to 3 seconds.
- Error rate has not increased.

Possibilities:
- Cold starts during scale-out.
- Some requests waiting on the connection pool.
- GC pauses or thread contention.
- External API experiencing tail latency.
- Retries/backoff occurring on only a fraction of requests.

Investigation steps:
1. Slice latency by revision, route, and instance/cold-start indicator.
2. Find traces for requests over 1 second.
3. Compare child spans, pool waits, and dependency attempts.
4. Check startup logs, GC/heap, and concurrency.
5. Run a load test reproducing the same traffic pattern.

### Scenario B: Fast Handler, Slow Event Completion

- Consumer processing p95 = 70 ms.
- Oldest message age = 25 seconds.
- Queue depth increases continuously.

The cause may be consumer throughput lower than arrival rate or a concurrency limit. Optimizing the Java handler by 10 ms may not be enough; you need to adjust consumer capacity and dependency budgets.

### Scenario C: Slow Overall Request, Normal Database Span

- Root HTTP span = 1.2 seconds.
- Database span = 80 ms.
- Payment span = 200 ms.

The remaining time may lie in uninstrumented connection acquisition, application locks, auth calls, retries, serialization, or platform overhead. Check span coverage and stage timing logs before drawing conclusions.

## 19. Mistakes When Measuring Latency

| Mistake | Consequence | Fix |
|---|---|---|
| Looking only at average | Hides tail latency | Track p50/p95/p99 and count |
| Comparing percentiles from different windows/samples | Wrong conclusions | Same window, dimensions, and sample count |
| Averaging p95 across instances | Does not yield service-wide p95 | Use histogram/distribution aggregation |
| Adding p95s of dependencies | Does not yield end-to-end p95 | Measure root span and inspect individual traces |
| Using wall-clock to measure duration in JVM | Affected by clock adjustments | Use nanoTime |
| Subtracting timestamps from two unsynchronized hosts | Incorrect queue wait | Broker timestamps, clock sync, and traces |
| Merging cold start with handler duration | Obscures bottleneck | Measure init separately |
| Measuring only handler, ignoring queue wait | Misses backlog | Measure event age and queue delay |
| Metric tags containing request IDs | Cardinality explosion | Put IDs in logs/traces |
| Load test with too few requests | Unstable p99 | Increase sample count and repeat |
| Retries excluded from total duration | Underestimates latency | Measure attempts and logical operation |
| Viewing only service metrics, not client | Misses network/gateway | Synthetic or client-side latency |

## 20. Latency Measurement and Optimization Checklist

- [ ] Each metric defines start/end, unit, and resource scope.
- [ ] Client latency, server duration, queue wait, and business completion are distinguished.
- [ ] p50, p90/p95, p99 are tracked alongside request count.
- [ ] Percentiles are aggregated from appropriate histograms/distributions.
- [ ] Per-instance percentiles are not averaged.
- [ ] Root requests have traces and child spans for critical dependencies.
- [ ] HTTP and message propagation preserve trace context/correlation IDs.
- [ ] Durations in the JVM use a monotonic clock.
- [ ] Cold start/init is measured separately from handler duration.
- [ ] Database connection acquisition and query duration are separated.
- [ ] Dependency retries, timeouts, and attempt counts are recorded.
- [ ] Queue age/backlog is monitored alongside consumer processing duration.
- [ ] The critical path is identified before optimizing.
- [ ] Metric labels have low cardinality and contain no sensitive data.
- [ ] Latency SLOs clearly define denominator, threshold, and window.
- [ ] Load tests include baseline, load, spike, soak, and cold-start scenarios.
- [ ] After optimization, rerun the same workload and compare percentiles/errors/throughput.

## Self-Check

1. Which two parts of a latency distribution do p50 and p99 describe?
2. Why can an average look good even when a subset of requests is very slow?
3. How does client-perceived latency differ from application duration?
4. If a message has a 40 ms consumer processing duration but a 20-second queue wait, what is the business latency?
5. Why can you not add the database p95 to the payment API p95 to deduce the root request p95?
6. What advantage do histograms have when aggregating latency across multiple instances?
7. When measuring duration in the JVM, why should you use `System.nanoTime()`?
8. How does cold start/init duration differ from handler duration?
9. If queue age increases while consumer processing duration stays flat, what should you investigate?
10. Why can arrival-rate load testing detect tail latency better than closed-loop testing?
11. When a request calls multiple dependencies in parallel, how is the critical path determined?
12. What elements must be clearly defined for an SLO like "99% of requests under 500 ms"?

Effective latency measurement starts with defining the right boundaries. Percentiles reveal the tail of the distribution; histograms enable aggregation across instances; traces show where a specific request spent its time. By separately measuring cold start, handler, dependencies, queue wait, and business completion, development teams can locate the true critical path, establish realistic SLOs, and verify every optimization under the same workload.

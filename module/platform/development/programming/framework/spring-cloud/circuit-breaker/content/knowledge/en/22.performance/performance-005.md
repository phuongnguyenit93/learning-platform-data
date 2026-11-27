# Event Logging and Metrics Overhead on the Hot Path

A circuit breaker needs to record call outcomes, update its sliding window, and emit events when changes occur. In Spring Cloud applications using Resilience4j, Micrometer and the event publisher provide visibility into that behavior. However, every extra operation on the hot path carries a cost: reading clocks, updating meters, allocating tags, formatting logs, capturing stack traces, allocating objects, and shipping data to collection backends.

The goal is not to strip out observability to cut latency. Instead, match the detail level to event frequency, keep synchronous hot-path work very short, and offload I/O or heavy processing to a separate bounded path. A rare state transition can be logged in full; a success event occurring tens of thousands of times per second should be aggregated into a metric rather than writing a log line per request.

## 1. What Does the Hot Path Include?

The hot path is the code executed for every request or every dependency call. When a circuit breaker wraps a call, the processing path can include:

```text
Business request
      |
      v
Circuit breaker checks state
      |
      v
Supplier calls HTTP/RPC client
      |
      v
Record success / failure / duration
      |
      v
Update sliding window and metrics
      |
      v
Emit event if applicable
      |
      v
Return result or handle fallback
```

Checking state and updating statistics are essential parts of the circuit breaker itself. Additional observability overhead usually comes from application-registered event listeners, logging, custom metrics, dynamic tags, or external exports.

Distinguish between two kinds of work:

- **In-place updates:** incrementing a counter, recording a timer/gauge, or writing a value to an in-memory buffer. These operations are usually fast, yet they still consume CPU and memory and can cause contention when many threads update the same meter.
- **I/O or heavy processing:** writing to files, shipping logs over the network, calling telemetry backends, serializing large payloads, querying databases, or running analytical computations. Never perform such work directly inside a per-call callback.

Micrometer typically updates meters in memory while Prometheus scrapes the endpoint on a separate schedule. Scraping does not run synchronously inside each request, yet each meter update still has a cost, and a large number of time series increases memory, CPU, scrape payload size, and storage expense.

## 2. Overhead of Different Observability Operations

| Operation | Typical Overhead | When Appropriate |
| --- | --- | --- |
| Incrementing a counter | Meter lookup, counter update, internal synchronization | Counting high-frequency events with finite tags |
| Recording duration with a timer | Clock read, count/sum update, plus histogram buckets if enabled | Measuring call duration or key operations |
| Reading state via a gauge | Storing a callback and sampling the value on scrape | Observing current state or resource counts |
| Logging a state transition | Message formatting and log write; typically infrequent | Recording `CLOSED`/`OPEN`/`HALF_OPEN` transitions for investigation |
| Logging every success/failure | Formatting and emitting one line per call; can generate heavy I/O | Only under low traffic or deliberate sampling |
| Exception stack traces | Capturing and formatting stack frames, inflating log volume | Errors needing diagnosis, with rate control |
| Trace/span | Context creation, timestamps, propagation, and export | Tracing flows across services; requires suitable sampling |
| Sending events to a remote service | Serialization, network I/O, retries, and delivery error handling | Run asynchronously through a bounded queue/buffer |

There is no single overhead number that holds for every application. Actual cost depends on the JDK, Micrometer/Resilience4j versions, meter registry, logging backend, thread count, histogram setup, tag volume, and production load. Measure in a production-like environment rather than assuming a meter or log line is always cheap.

## 3. Event Listeners Can Run Directly on the Event-Emitting Thread

Resilience4j provides an event publisher for events such as state transitions, call successes, call errors, and calls not permitted. Directly registered consumers are generally invoked as the event is emitted. Therefore, treat callbacks as part of a path that may execute on the calling thread unless a specific integration or version guarantees asynchronous dispatch.

Example listener that only logs state transitions:

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
                log.warn("inventory circuit breaker state transition: {}", event));
    }
}
```

State transitions occur far less frequently than call successes, so logging each transition can be reasonable. Even so, a synchronous logging backend can still block the event-emitting thread while writing. Use an asynchronous log appender if needed, along with a bounded queue and an explicit queue-full policy.

Do not attach `onSuccess` and log at `INFO` for every successful call. At high traffic, that produces log volume proportional to request rate, inflating formatting, I/O, transport, and storage costs. Use aggregated timers and counters to answer trend questions; log detailed entries only when there is an investigative reason.

## 4. Choosing Which Events to Log

Each event type has a different frequency and diagnostic value:

| Event | Expected Frequency | Recommended Handling |
| --- | --- | --- |
| State transition | Much lower than call count | Structured log with breaker ID and previous/new state |
| Call success | Can approach nearly every request | Do not log per call; use timers/counters |
| Call error | Spikes during outages | Aggregated metrics, sampled logs, or rate-limited logs per error category |
| Call not permitted | Can be very high when breaker is `OPEN` | Count with metrics; avoid logging a warning for every blocked request |
| Slow call | Depends on latency and threshold | Use slow-call rate and histograms; sample logs if investigation is needed |
| Reset or admin action | Rare and operationally significant | Write an audit log with actor, reason, and timestamp |

When a breaker is `OPEN`, huge volumes of requests can be rejected very rapidly. If every `CallNotPermittedException` captures a stack trace and emits an `ERROR` log line, the system can pile extra load onto CPU, disk, log collectors, and the network right in the middle of an incident. Count rejections via metrics and log state transitions; only sample rejected calls if additional context is needed.

## 5. Metrics: Cheaper Than Per-Request Logging, Still Bounded

Micrometer and Resilience4j expose aggregated metrics for circuit breakers. A timer can record counts and execution durations grouped by outcome; gauges can expose state, failure rate, slow-call rate, or buffered sample counts. These meters reveal trends without writing a log line for every request.

However, every combination of meter name and tags produces one or more time series. For example, a metric tagged with `dependency`, `environment`, `region`, and `pod` multiplies series by the combinations of values. Adding `userId`, `orderId`, `sku`, or request ID can drive cardinality nearly as high as the request count itself.

Safe tagging rules:

- Use bounded value sets such as `dependency=inventory`, `result=success|failure`, `environment=prod`.
- Add `pod` or `instance` only when per-replica breakdown is required and the metrics backend can absorb the resulting series count.
- Never use user IDs, order IDs, request IDs, parameterized URLs, or exception messages as tags.
- Group exceptions into finite buckets such as `timeout`, `connection`, `rejected`, `other` when error breakdown is needed.
- Put specific IDs and detailed causes into controlled logs or traces, not into metric labels.

Example registering a counter once in the constructor rather than building dynamic names and tags on every request:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryFallbackMetrics {

    private final Counter fallbackCounter;

    public InventoryFallbackMetrics(MeterRegistry registry) {
        this.fallbackCounter = Counter.builder("application.fallback.calls")
            .description("Number of inventory fallback responses")
            .tag("dependency", "inventory")
            .register(registry);
    }

    public void recordFallback() {
        fallbackCounter.increment();
    }
}
```

The meter is created once and reused. If you need breakdowns by cause, pre-register a small set of counters with finite tags or use a meter provider keyed by a fixed enum; avoid passing arbitrary exception strings into tags.

## 6. Timers and Histograms Increase Monitoring Cost

A timer measures count and total duration. When histograms are enabled, the registry also maintains or exports buckets so percentiles can be computed in the backend. Histograms are valuable for p95/p99 tracking, yet extra buckets and tags multiply time-series counts.

Example enabling histograms for the circuit breaker call timer:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        resilience4j.circuitbreaker.calls: true
```

Do not turn on histograms for every meter simply because you can. Pick timers that serve SLOs or tail-latency investigations, size buckets around your target response times, and verify cardinality after deployment. If your backend supports aggregated percentiles in another way, weigh the cost and accuracy of each option.

A timer measuring supplier duration does not necessarily include fallbacks or the entire business request. When you need to separate dependency latency from end-to-end latency, define two timers at clear boundaries instead of merging them into one metric. Avoid adding a custom timer that duplicates Resilience4j's built-in timer unless it answers a distinct observability question.

## 7. Measuring Dependency Duration with a Reusable Timer

When you need a dedicated business metric for inventory calls, initialize the timer once and record duration around the client call:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
public class InventoryClientMetrics {

    private final InventoryClient client;
    private final Timer dependencyTimer;

    public InventoryClientMetrics(
            InventoryClient client,
            MeterRegistry registry) {
        this.client = client;
        this.dependencyTimer = Timer.builder("dependency.client.duration")
            .description("Time spent waiting for the inventory dependency")
            .tag("dependency", "inventory")
            .register(registry);
    }

    public InventoryResult fetch(String sku) {
        long started = System.nanoTime();
        try {
            return client.fetch(sku);
        } finally {
            dependencyTimer.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS
            );
        }
    }
}
```

The `finally` block ensures the timer still records duration when the client throws an exception. This example measures synchronous client call duration; for reactive APIs or `CompletionStage`, record duration when the publisher or stage terminates rather than stopping the timer as soon as the asynchronous handle is returned. If Resilience4j already exports a timer at the exact same boundary, reuse the existing meter instead of double-instrumenting.

Never attach `sku` as a timer tag. If you need to know which SKU failed, record that value in controlled logs or traces while respecting the application's data policies.

## 8. Asynchronous Logging Still Requires Bounded Queues

An async appender moves log writing or shipping off the request thread, yet it does not reduce cost to zero. The event-emitting thread must still construct the log event, format or prepare the message, and enqueue it. Once the queue fills up, the logging framework may block, drop logs, or apply another policy depending on configuration.

If you offload events to a dedicated worker, use a bounded queue and define explicit behavior under overload:

```text
Resilience4j event callback
          |
          v
Create small event summary
          |
          v
Bounded queue
    |              |
    | space left   | full
    v              v
Enqueue     Drop/sample low-priority event
    |
    v
Background worker
    |
    v
Log collector / telemetry backend
```

Do not spawn a new `CompletableFuture.runAsync(...)` for every event and push it onto the common pool without limits. That pattern accumulates unbounded tasks when the logging backend slows down, exhausting memory and the thread pool. A bounded queue forces an explicit decision: drop high-frequency events, sample them, or apply bounded backpressure.

State transitions carry high diagnostic value and occur infrequently; they can be handled on a higher-priority path than call successes. When a shared queue fills up, consider emitting a short log for state transitions or using a separate bounded queue. Never let telemetry hang business requests.

## 9. Targeted Log and Trace Sampling

Common techniques to curb log volume:

- Log state transitions in full since they are rare and operationally important.
- Skip per-call success logs; rely on aggregated timers and counters.
- Sample call errors or slow calls by ratio, interval, or the first few occurrences of each failure episode.
- Limit repeated stack traces; keep enough examples to identify the error class while tracking total occurrences via metrics.
- Apply trace sampling for normal traffic and retain error/tail-latency traces according to tracing backend capacity.
- Separate administrative audit logs from diagnostic logs that may be sampled.

Sampling must preserve investigative utility. Logging one random error per hour might miss the onset of an outage. Prefer capturing the first occurrence right after the breaker moves to `OPEN`, periodic samples while errors persist, and a sample when the breaker recovers. Total error counts remain reflected in metrics.

Never use sampling to discard mandatory audit trails or durable business events. A circuit breaker's event publisher is for observability and diagnostics; if transaction auditing is required, write to an audit or domain event store with appropriate durability and semantics.

## 10. Avoiding Heavy Operations Inside Callbacks

Event callbacks should not:

- Make HTTP, RPC, or database calls to send events immediately.
- Read configuration from a remote store or query service discovery.
- Serialize full request/response payloads or dump large objects.
- Write full stack traces for every call error during an outage.
- Create metrics with tags containing a fresh value per request.
- Wait indefinitely on locks, semaphores, or queues.
- Run synchronous statistical computations or analytics on the event-emitting thread.

Callbacks should extract small, stable fields such as breaker ID, state transition, error category, and timestamp, then update local metrics or enqueue a compact summary into a bounded buffer. If the worker falls behind, drop high-frequency diagnostic events and increment an internal dropped-event counter.

Example minimal listener logging only state transitions:

```java
breaker.getEventPublisher()
    .onStateTransition(event -> {
        log.warn("Circuit breaker transition: {}", event);
    });
```

There is no need to register listeners on every request. Register once during bean lifecycle initialization and verify that the breaker retrieved from the registry is the exact instance protecting the call. If multiple breakers exist, attach listeners per instance or use the appropriate integration customizer.

## 11. Avoiding Duplicate Metrics and Logs

Resilience4j and Micrometer already provide meters for call outcomes, state, and duration. If the application registers additional counters for every success, failure, and not-permitted call without a distinct purpose, data gets duplicated and dashboards become easy to misread.

Create custom metrics only when they answer a different question, such as:

- How many business requests used a fallback?
- How many commands were rejected because a dependency was unavailable?
- How often did the fallback itself fail?
- How many administrative actions force-opened or reset a breaker?

Custom metrics should have clear names and units. Do not add successful fallbacks to successful dependency calls: those are two events at two different boundaries. Likewise, do not count call-not-permitted rejections as new dependency errors, because the supplier was never executed.

## 12. Benchmarking Observability Overhead

To verify whether observability settings slow down the hot path, measure under production-like load. Compare runs with identical datasets and business configuration:

1. Baseline: circuit breaker active with minimal built-in metrics and no per-call logging.
2. Metrics: enable required timers, gauges, and counters.
3. Logging: enable state-transition logs and the sampled error-logging policy.
4. Histograms/tracing: enable histograms or trace sampling at the planned rates.
5. Telemetry stress: slow down the log collector or push queues near capacity to verify system behavior when the observability backend degrades.

Record throughput, CPU, allocation/GC, request p50/p95/p99, dependency latency, logs/second, time-series count, and queue utilization. Evaluate both normal operation and `OPEN` breaker periods, because call-not-permitted rejections and exceptions can arrive in large bursts.

When comparing runs, hold replica count, thread pools, request mix, and warm-up duration constant. Do not draw conclusions from a brief run or mean latency alone. The goal is to pinpoint which observability components add meaningful overhead and confirm that the cost is acceptable relative to diagnostic value.

## 13. Example Bounded Observability Configuration

A baseline configuration can expose required endpoints, attach low-cardinality application tags, and enable histograms on the circuit breaker call timer:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: order-service
      environment: production
    distribution:
      percentiles-histogram:
        resilience4j.circuitbreaker.calls: true
```

Do not add tags like user ID, request ID, or order ID. With many dependencies or pods, estimate expected time-series counts before enabling histograms across all combinations. Restrict access to Actuator/Prometheus endpoints via monitoring networks and appropriate authorization.

For logging, prefer state transitions at `WARN` or `INFO` per operational convention; repeated call errors should be aggregated or sampled. Set log levels per environment and avoid leaving `DEBUG` enabled for every request in production for extended periods.

## 14. Hot-Path Design Checklist

- Use built-in Resilience4j meters before creating duplicate metrics.
- Initialize `Counter`/`Timer` instances once and reuse them; never register new meters from request values.
- Keep tags low-cardinality and bounded.
- Use timers/histograms to aggregate latency instead of per-call logging.
- Log state transitions in full; sample call errors, slow calls, and call-not-permitted events under high traffic.
- Never perform network I/O, database access, or heavy processing inside event callbacks.
- When offloading events to a worker, use bounded queues, explicit drop/backpressure policies, and metrics for queue depth/drops.
- Never spawn unbounded async tasks per event.
- Keep dependency, fallback, and end-to-end request metrics separate; do not merge outcomes across boundaries.
- Benchmark p95/p99, CPU, allocations, log volume, and cardinality with instrumentation enabled.
- Secure telemetry endpoints and keep sensitive data out of tags and logs.

Good observability detects dependency degradation, explains why a circuit breaker opened, and quantifies user impact. By matching detail level to event type, aggregating high-frequency traffic into metrics, and keeping callbacks brief, applications preserve diagnostic power without turning logging or telemetry into a new bottleneck on the hot path.

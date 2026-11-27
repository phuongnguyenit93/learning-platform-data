# Micrometer Timer, Counter, and Distribution in Spring Integration Runtime

## Lesson objectives

In **SPRING_INTEGRATION_RUNTIME**, a message can pass through inbound adapters, channels, pollers, executors, handlers, gateways, and external systems. When a flow slows down or backlogs grow, looking only at CPU and heap is usually not enough to pinpoint the cause. **Micrometer** provides a unified measurement model to observe **frequency**, **processing duration**, and **size/value distributions** at key boundaries.

Three particularly useful meter types are:

- **Timer**: how long an operation takes; tracks **recorded count, total time, maximum time**, and can export histograms/percentiles depending on configuration.
- **Counter**: how many times an event type occurred, such as parse errors, timeouts, suppressed duplicates, or retry attempts.
- **DistributionSummary**: a set of non-time values, such as payload size (bytes), number of items in a batch, or message group size.

This lesson belongs to the **Observability** chapter and connects the three meters to Spring Integration specifics: **DirectChannel, ExecutorChannel, poller, consumer, transaction, retry, errorChannel, correlation, and MessageStore**.

After this lesson, you will be able to:

1. Choose the right meter type instead of using Counter/Timer/DistributionSummary arbitrarily.
2. Name metrics, units, and tags with safe cardinality.
3. Record a Timer using **Timer.Sample** around a service activator, even when exceptions occur.
4. Use Counter for retries/errors/duplicates and DistributionSummary for payload/batch sizes.
5. Distinguish **send latency**, **queue wait**, **handler execution latency**, and **business end-to-end latency** across asynchronous channels.
6. Export metrics from Spring Boot Actuator/Micrometer to Prometheus or compatible backends, understanding count/sum/buckets and percentiles.
7. Test meters with **SimpleMeterRegistry** and build meaningful dashboards/alerts across failures, restarts, and multi-instance scaling.

> **Principle:** First define **the unit being measured** (message, attempt, delivery, batch, or business operation), **time boundaries**, and **event emission point**. Only then choose the meter type. A metric with clean numbers that measures the wrong boundary easily leads to wrong operational conclusions.

## 1. Which questions does observability answer at runtime?

Consider an order ingestion flow:

~~~mermaid
flowchart LR
    S["Broker inbound adapter"] --> C["ordersInput<br/>DirectChannel"]
    C --> Q["QueueChannel<br/>persistent store"]
    Q --> P["Polling consumer"]
    P --> E["ExecutorChannel / worker"]
    E --> H["Order handler"]
    H --> D[("Database")]
    H --> X["Outbound HTTP"]
    H -. "Exception" .-> R["errorChannel / recovery"]
~~~

An operator might ask:

| Question | Recommended measurement | Do not confuse with |
| --- | --- | --- |
| How many requests arrive? | Ingress counter or receive count | Unique business transactions |
| How long does the handler take? | Timer around the handler | Time the message waited in queue before the handler |
| How many retries occurred? | Retry attempts counter | Source message count or unique business failures |
| How large are payloads? | DistributionSummary in bytes | Timer or current queue-size Gauge |
| How many messages are waiting? | Queue depth/backlog **Gauge** | Counter of total messages that ever entered the queue |
| How many flows are failing? | Counter by error type + rate | Cumulative counter since JVM start |
| Why did P95 latency increase? | Per-stage Timers + queue wait | A Timer measuring only the send into ExecutorChannel |
| Are duplicates occurring? | Duplicate delivery / duplicate effect Counter | Delivery count without an idempotency key |

**Logs** show specific events and business keys; **traces** link steps within an execution; **metrics** aggregate behavior over time to reveal trends and trigger alerts. The three pillars complement each other rather than replacing one another.

## 2. Micrometer's meter model

**MeterRegistry** is where meters are registered and recorded. A meter has a **name**, **tags**, and a specific type; the combination **name + tags** represents one time series.

| Type | Micrometer API | Primary data | Common uses |
| --- | --- | --- | --- |
| **Counter** | Counter.increment() | Total count or incremented amount | Errors, retries, discards, successful events |
| **Timer** | Timer.record(...), Timer.Sample | Count, total time, max, optional histogram | Handler/HTTP/DB/poller execution duration |
| **DistributionSummary** | DistributionSummary.record(value) | Count, sum, max, optional histogram | Byte size, records per batch, message group size |
| **Gauge** | Gauge over an observed object/value | Instantaneous value at sampling time | Queue depth, in-flight count, executor active threads |
| **LongTaskTimer** | LongTaskTimer.start()/sample.stop() | Number of long-running active tasks and their durations | Long batches, prolonged waiting jobs, active work |

**Counters only increase** and must not be used to represent the number of items currently sitting in a queue. A QueueChannel might receive 1,000 and process all 1,000 messages: the ingress Counter stays at 1,000, while the backlog Gauge must return to 0.

**Timers already include a count**. If you only need both the count and duration of the same operation, you do not need to register a separate Counter counting the exact same invocations. A separate Counter is useful when it represents **different semantics**, such as classified errors, suppressed duplicates, or initiated retries.

**DistributionSummary is not a Timer**. Recording the number 300 into a summary means a **numeric value of 300 in your chosen base unit**, and does not automatically turn it into 300 ms.

## 3. Timer: measuring operation duration

### What does a Timer record?

After three executions taking **80 ms**, **100 ms**, and **420 ms**:

| Quantity | Example value |
| --- | ---: |
| Timer count | 3 |
| Timer total time | 600 ms |
| Average duration of the three runs | 200 ms |
| Maximum observed duration | 420 ms |

In Micrometer, **Timers record durations via Duration or Runnable/Callable APIs**, while backends may export in **seconds** or another appropriate unit. Do not mix manual nanosecond/millisecond numbers with a unit different from what the API expects.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

class TimerExamples {
    private final MeterRegistry registry;

    TimerExamples(MeterRegistry registry) {
        this.registry = registry;
    }

    void recordOneDuration() {
        Timer timer = Timer.builder("orders.validation.duration")
                .description("Duration of order validation")
                .tag("flow", "order-import")
                .register(registry);

        timer.record(Duration.ofMillis(125));
    }

    void recordRunnable() {
        Timer timer = registry.timer(
                "orders.normalization.duration",
                "flow", "order-import");

        timer.record(() -> normalizeOrder());
    }

    private void normalizeOrder() {
        // Demo: work to measure.
    }
}
~~~

### Timer.Sample when outcome is known only after execution

This is the right pattern for attaching an **outcome=success/error** tag after the handler completes:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

record OrderCommand(String orderId, int itemCount) {}

interface OrderProcessor {
    void process(OrderCommand order);
}

@Component
class InstrumentedOrderHandler {
    private final MeterRegistry registry;
    private final OrderProcessor processor;

    InstrumentedOrderHandler(MeterRegistry registry,
                             OrderProcessor processor) {
        this.registry = registry;
        this.processor = processor;
    }

    @ServiceActivator(inputChannel = "orderRequests")
    public void handle(Message<OrderCommand> message) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            processor.process(message.getPayload());
        } catch (RuntimeException failure) {
            outcome = "error";
            throw failure; // Let the error flow/transaction receive the actual error.
        } finally {
            Timer timer = Timer.builder("orders.handler.duration")
                    .description("Execution duration of order handler attempt")
                    .tag("flow", "order-import")
                    .tag("handler", "order-handler")
                    .tag("outcome", outcome)
                    .register(registry);
            sample.stop(timer);
        }
    }
}
~~~

**Accurate interpretation:**

1. One **handle(...) invocation** corresponds to one sample, even when a RuntimeException is thrown.
2. When **RequestHandlerRetryAdvice** wraps the method externally, the method may be invoked multiple times. The Timer above measures **each handler attempt**, not by default a single business operation.
3. With an **ExecutorChannel**, the method runs on a worker thread; the Timer measures work inside the method, **not time waiting in the executor queue**.
4. Do not put **orderId, correlationId, messageId, or exception messages** into tags, as these values can be nearly unique per request.
5. This sample classifies RuntimeException; if business logic uses other error types or returns failure statuses without throwing, define **outcome** accordingly.
6. **Timer.Sample** is a single-execution timing object. If you need to measure multiple phases, create separate samples at clear boundaries rather than stopping the same sample multiple times for different metrics.

### Choosing the right boundaries for Timer APIs

| Timer | Starts | Ends | Meaning |
| --- | --- | --- | --- |
| **send duration** | Before MessageChannel.send | When send returns/throws | Channel send duration, which may be only a handoff |
| **poll duration** | When poller starts a poll cycle | When poll cycle finishes | Cost of poll/receive/dispatch per topology |
| **queue wait** | When message is enqueued | When consumer starts processing | Queueing delay |
| **handler duration** | When handler is invoked | When handler returns/throws | Execution time of a handler attempt |
| **business end-to-end** | When business work is accepted | When final outcome is committed/confirmed | Business SLA; may span multiple deliveries/retries |

The Timers above **do not automatically add up to a single number** when there is parallel processing, overlap, retry waiting, or multiple branches. You must examine the actual topology and measurement clocks/timestamps.

## 4. Counter: measuring events and error causes

Counters measure **incremental counts**. For example, each time a message is flagged as a duplicate:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

class DuplicateMeter {
    private final Counter duplicates;

    DuplicateMeter(MeterRegistry registry) {
        this.duplicates = Counter.builder("orders.duplicate.suppressed")
                .description("Business duplicate events safely suppressed")
                .tag("flow", "order-import")
                .register(registry);
    }

    void duplicateWasSuppressed() {
        duplicates.increment();
    }
}
~~~

A Counter can increment by a positive number other than 1 when counting an **actual processed quantity**, whereas negative values are incompatible with Counter semantics.

### Defining counters around observable events

| Example metric | When to increment? | When NOT to increment |
| --- | --- | --- |
| **orders.ingress.received** | A message is received by the consumer per delivery unit | Merely because a producer sent a request the adapter has not received |
| **orders.handler.failed** | A handler attempt genuinely failed | A message is sitting in a queue without having run |
| **orders.retry.attempted** | A retry attempt is started | The initial attempt if policy defines "retry" as subsequent attempts |
| **orders.duplicate.suppressed** | A duplicate is verified and safely suppressed | Merely seeing the same correlationId; that is not necessarily a duplicate |
| **orders.dlq.published** | DLQ/quarantine confirmed receipt per contract | Merely deciding to send to DLQ before sending succeeds |
| **orders.operation.completed** | A business operation is confirmed complete | On every handler call or every HTTP retry |

**Why separate attempts from operations?** If a broker redelivers a message three times and each delivery retries the handler twice, there can be many **handler failure events** for **one** business operation. Dashboards must not label handler attempts as "failed orders" without deduplication.

### Avoid incrementing a Counter in both catch and errorChannel for the same failure

~~~text
Handler catches exception:
    orders.handler.failed += 1

ErrorChannel consumer receives the same exception again:
    orders.handler.failed += 1  <-- Double-counted if this is the same event.
~~~

Instead:

- Place **handler.failed** at a single point, such as an interceptor or handler entry.
- Place **error.message.received** on the errorChannel if you want to measure ErrorMessages delivered to the error flow (that is a **different unit**).
- Place **recovery.completed** after business recovery actually completes.
- Place **operation.failed** when the business operation transitions to terminal failure, if a durable source of truth exists.

## 5. DistributionSummary: measuring sizes and distributions

**DistributionSummary** fits **non-duration values**, such as payload byte size or record count per batch.

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;

class PayloadSizeMetrics {
    private final DistributionSummary bytes;
    private final DistributionSummary batchRecords;

    PayloadSizeMetrics(MeterRegistry registry) {
        bytes = DistributionSummary.builder("orders.payload.size")
                .description("Serialized payload sizes")
                .baseUnit("bytes")
                .tag("flow", "order-import")
                .publishPercentileHistogram()
                .register(registry);

        batchRecords = DistributionSummary.builder("orders.batch.records")
                .description("Number of records in each submitted batch")
                .tag("flow", "order-import")
                .register(registry);
    }

    void onPayload(byte[] serializedPayload) {
        bytes.record(serializedPayload.length);
    }

    void onBatch(int recordCount) {
        if (recordCount < 0) {
            throw new IllegalArgumentException("Negative batch size");
        }
        batchRecords.record(recordCount);
    }
}
~~~

**What is measured must be clearly defined:**

- **serializedPayload.length** is the byte count of the **serialized representation**, not the exact RAM occupied by the Java object.
- If you read a JSON String and call **length()**, that is the number of UTF-16 code units, **not UTF-8 byte count**. For byte count, measure after encoding or from the actual byte[].
- If messages are compressed, **uncompressed** size and **compressed wire** size differ; name the meter/tags according to the measurement boundary.
- DistributionSummary records one observation **per batch** in the example; if the same batch is retried, you will record multiple samples. That is the distribution of **attempted batches**, not automatically the distribution of **unique business batches**.

### When to use Gauge instead of DistributionSummary?

~~~text
Group A just received 10 messages, then released and is now empty.
Group B has 200 messages waiting.
~~~

- To know **the size of a group at release time**: record a **DistributionSummary** sample of 10 and a sample of 200.
- To know **how many groups are waiting right now** or **total queued messages right now**: use a **Gauge**.
- To know the total number of messages **ever received** since process start: use a **Counter**.

Do not create a new Gauge per groupId; the number of groups can grow without bound. Instead, take a snapshot/aggregate from the store and emit metrics only along controlled flow/status dimensions.

## 6. Metric names, tags, and cardinality limits

A metric is registered like:

~~~text
name: orders.handler.duration
tags:
    application = order-service
    flow = order-import
    handler = order-handler
    outcome = success
~~~

Tags can create many independent meter series. If:

~~~text
4 flows × 8 handlers × 3 outcomes × 5 instances = 480 time series
~~~

then when exporting histograms, **each time series also has many buckets**. This multiplier grows rapidly. Avoid tags with **unbounded values**:

| Tag to consider | Cardinality | Reason |
| --- | --- | --- |
| flow, endpoint (bounded list) | Low to medium | Pinpoint failure location |
| outcome=success/error/timeout | Low | Classify result |
| errorType=validation/network/db/unknown | Low if fixed buckets | Diagnose errors |
| transport=kafka/http/file | Low | Distinguish adapters |
| application, environment, instance | Per infrastructure | Filter by service/replica; instance count must be factored in |
| **orderId/paymentId/eventId** | Very high | Do not use as meter tags |
| **messageId/correlationId/traceId** | Very high | Put in logs/traces |
| **exception message, full URI, SQL text** | Unbounded, potentially sensitive | Use error category and route template |

**Naming/units:** Micrometer can transform names when exporting to backends. For example, Timer **orders.handler.duration** may become Prometheus series with a **_seconds** suffix, while DistributionSummary with **baseUnit("bytes")** may carry a corresponding suffix. Do not hardcode a suffix convention and assume it is identical across every registry.

## 7. Which automatic meters does Spring Integration provide?

Spring Integration includes Micrometer/management integration for components such as channels and endpoints, depending on version, dependencies, and management configuration. Some paths also support **Micrometer Observation**, combining metrics and tracing.

**Do not assume every endpoint automatically emits the exact same set of metrics.** Meter names, tags, capture mechanisms, and instrumentation timing depend on:

1. Versions of **Spring Integration**, Spring Framework, Spring Boot, and Micrometer.
2. Whether a suitable **MeterRegistry**/metrics captor or observation infrastructure exists in the context.
3. Whether management/observation is enabled for the endpoint/channel by configuration.
4. Whether the endpoint is actually **message-driven**, **polling**, a **gateway**, or an async channel.
5. Which backend the registry exports to and how filters/renaming are configured.

### Practical metric verification workflow

- Enable minimal observability in a dev/test environment.
- Send one successful message and one controlled failing message.
- Inspect the meter list in **MeterRegistry** or the Actuator endpoint **/actuator/metrics** when enabled.
- Verify **names, tags, meter types, counts, and timing scope** against actual behavior.
- Test a send through DirectChannel, a send through ExecutorChannel, an empty poll receiving no message, and a failing handler; different paths can yield different observations.

**Avoid stacking automatic and manual meters:** If the framework already provides a Timer for the same **handler execution**, adding an application-recorded Timer can be useful for business breakdown, but it must use a distinct name/definition so dashboards do not add the two metrics and report double the request count.

## 8. Spring Boot Actuator and the Prometheus backend

A Spring Boot application using Micrometer can expose metrics endpoints via **spring-boot-starter-actuator**. For Prometheus, an appropriate registry dependency such as **micrometer-registry-prometheus** is typically required; verify exact artifact names and auto-configuration against your project version.

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
      environment: staging
~~~

**Security note:** This is an example for an environment with protected management endpoints. Do not expose **/actuator/metrics** or **/actuator/prometheus** openly on the public Internet. Configure authentication, network policies, authorization, and scrape access per operational standards.

### Differences between in-registry metrics and scraped data

A **Timer** registered in the JVM may provide:

~~~text
name = orders.handler.duration
count = 20
totalTime = 4.7 seconds
max = 0.63 seconds
~~~

When exported to Prometheus, a histogram-enabled timer typically becomes metrics close to:

~~~text
orders_handler_duration_seconds_count{flow="order-import",outcome="success"} ...
orders_handler_duration_seconds_sum{flow="order-import",outcome="success"} ...
orders_handler_duration_seconds_bucket{flow="order-import",outcome="success",le="0.5"} ...
~~~

The **_bucket** series appear only when histograms/SLO buckets are configured appropriately. Exact naming also depends on version/registry; inspect the actual scrape endpoint instead of assuming every meter exports count, sum, max, buckets, and percentiles identically.

### Difference between Counter and rate

Counters typically reset to 0 on process restart. Dashboards should look at **rate of increase over a time interval** when analyzing recent behavior.

Illustrative PromQL example if **orders.duplicate.suppressed** is exported as a matching Counter:

~~~promql
sum(rate(orders_duplicate_suppressed_total[5m]))
~~~

This is the **average number of duplicates suppressed per second** over 5 minutes, not the total duplicates since the beginning of the system's life. Use **increase(metric[...])** when you want to estimate the number of events added during a window:

~~~promql
sum(increase(orders_duplicate_suppressed_total[1h]))
~~~

**Do not divide a raw Counter directly by system uptime seconds** to infer current rate: multiple process restarts and replica count changes can skew the result.

## 9. Histograms, percentiles, and latency distributions

**Average duration** fails to describe tail latency. For instance, 99 requests run in 50 ms and one request takes 5 seconds. The average remains relatively low compared to **P99**, yet 1% of users experience severe slowness.

Micrometer supports configuring percentile histograms/SLO buckets per meter/backend:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

class OrderTimerConfiguration {
    private final Timer orderHandlerTimer;

    OrderTimerConfiguration(MeterRegistry registry) {
        this.orderHandlerTimer =
                Timer.builder("orders.handler.stage.duration")
                        .description("Order processing stage duration")
                        .tag("flow", "order-import")
                        .publishPercentileHistogram()
                        .serviceLevelObjectives(
                                Duration.ofMillis(100),
                                Duration.ofMillis(500),
                                Duration.ofSeconds(2))
                        .register(registry);
    }

    void record(Duration duration) {
        orderHandlerTimer.record(duration);
    }
}
~~~

The example above illustrates a **fixed Timer** for a stage. If you want an outcome tag once the result is known, build outcome-tagged Timers as in Section 3, while **keeping the same histogram and service level objectives policy** across every outcome so dashboards compare consistently.

### What do P50/P95/P99 mean?

| Quantile | How to read |
| --- | --- |
| **P50** | Roughly half of the observations are less than or equal to this level |
| **P95** | Roughly 95% of observations fall at or below this level |
| **P99** | Roughly 99% of observations fall at or below this level |

P99 is **not** the maximum duration; the slowest requests can still be significantly higher than P99. At low traffic, percentiles can be unstable due to low sample counts.

### Per-instance percentiles versus aggregated histograms

**Client-side percentiles** are precomputed by Micrometer from each registry/instance's local distribution and usually **cannot be summed or averaged** accurately to produce a cluster-wide percentile.

**Histogram buckets** suit backends like Prometheus for computing quantiles over data **aggregated across instances**. Example using the custom timer above:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_handler_stage_duration_seconds_bucket[5m])
  )
)
~~~

**Condition:** The meter must export buckets with matching names and labels. In applications with many flows/handlers, you usually need to filter by **flow** or **endpoint** before aggregating. Merging handlers with very different latency profiles into one histogram can cause the combined P95 to hide a bottleneck.

### Ratio of requests above a threshold

If a Timer has a bucket for **2 seconds**, the ratio of observations **exceeding 2 seconds** can be estimated via count and bucket with matching filters/aggregations:

~~~promql
(
  sum(rate(orders_handler_stage_duration_seconds_count[5m]))
  -
  sum(rate(orders_handler_stage_duration_seconds_bucket{le="2.0"}[5m]))
)
/
sum(rate(orders_handler_stage_duration_seconds_count[5m]))
~~~

Check the actual **le** label; backends may format the bucket value differently, such as **"2"**. When the denominator is 0 (no traffic), dashboards/alerts must handle empty/undefined results rather than reporting a guaranteed 0% error rate.

### DistributionSummary also supports histograms

If you need **P95 payload size** or the ratio of payloads exceeding a threshold, you can configure histograms or SLO buckets on DistributionSummary. However, memory/export cost scales with the number of meters/tags. Enable histograms only on metrics that directly support an SLO or capacity decision.

## 10. Measuring latency accurately when flows have DirectChannel and ExecutorChannel

Case **DirectChannel**:

~~~text
Producer thread
  send(message)
    → DirectChannel
       → Handler (150 ms)
  send returns (after ~150 ms + overhead)
~~~

Because the handler runs synchronously on the sender thread, a Timer around send can **include** handler duration. However, with **ExecutorChannel**:

~~~text
Producer thread                   Worker thread
  send(message)
    → ExecutorChannel
       → enqueue task -------------→ wait in queue (500 ms)
  send returns (5 ms)              → handler (150 ms)
                                   → DB / HTTP
~~~

A Timer around **send()** now sees only **5 ms**, while the user experiences **655 ms** before the business step finishes. If dashboards mistake send latency for **end-to-end latency**, you will think the system is fast even as executor backlogs mount.

### Three measurements to separate

1. **dispatch duration:** from before send() until send() returns.
2. **queue wait:** from when the message is actually enqueued until the worker starts processing.
3. **processing duration:** from when the worker enters the handler until the handler completes/throws.

When business requirements specify a source-to-sink SLA, also measure **business end-to-end duration** using a reliable start milestone and terminal completion state. Multiple messages may represent a single operation, so avoid recording completion Timers multiple times due to retries/replays.

### Measuring queue wait via enqueue timestamp

One illustrative approach is attaching enqueue-time metadata:

~~~java
import java.time.Duration;
import java.time.Instant;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.messaging.Message;

class QueueWaitObserver {
    private final MeterRegistry registry;

    QueueWaitObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    void observeWhenDequeued(Message<?> message) {
        Object header = message.getHeaders().get("enqueuedAtEpochMillis");
        if (!(header instanceof Long started)) {
            return; // Missing metadata: do not record a fake sample.
        }

        long elapsed = Instant.now().toEpochMilli() - started;
        if (elapsed < 0) {
            // Clock skew/shift: do not treat a negative value as valid latency.
            return;
        }

        Timer.builder("orders.queue.wait.duration")
                .tag("flow", "order-import")
                .register(registry)
                .record(Duration.ofMillis(elapsed));
    }
}
~~~

**Important limitations:**

- Attach the timestamp **at the exact moment of enqueueing**; attaching it at the producer before several transformers will include those other steps.
- Wall clocks **can jump**, and clocks between hosts can drift. If measuring a segment within the **same process**, prefer a monotonic clock such as **System.nanoTime()**; never compare nanoTime values across JVMs or across restarts.
- If messages cross a broker/persistent store and restarts, epoch timestamps can be preserved to measure cross-process wait time, provided you manage clock synchronization, formatting, and schema.
- Do not add per-message timestamps as **metric tags**. They are data for computing a duration, not a grouping dimension.

## 11. Poller, consumer, and MessageStore: which timers help?

A polling endpoint typically has these stages:

~~~text
Scheduled poll begins
  → MessageSource.receive()
  → message may be null or non-null
  → dispatch / handle
  → commit / rollback
Poll finishes
~~~

**Different questions require different metrics:**

| Measurement | Type | Signal |
| --- | --- | --- |
| Poll count | Counter | Is the poller running on schedule? |
| Empty poll count | Counter | Polling continuously with no data? |
| receive() duration | Timer | Is the DB/file/broker source slow? |
| Poll cycle duration | Timer | How long does one poll hold the thread? |
| Messages per poll | DistributionSummary | Large/small batches, load variations |
| Wait time in MessageStore | Appropriate Timer/Gauge | Is the backlog aging or growing? |
| Waiting message count | Gauge | Backpressure |
| Commit/rollback count | Counter by outcome | Transaction failure rate |

An empty poll **is not** a failed message. Counting every poll into **orders.ingress.received** causes dashboards to report phantom traffic.

### Timer around receive() differs from Timer around the whole poll

If receive() returns in 10 ms while the handler takes 900 ms, **poll total duration** can be close to 910 ms on a synchronous path; **receive duration** should record only 10 ms. Separating the two metrics distinguishes a slow data source from slow processing.

For a poller with **maxMessagesPerPoll > 1**, a single poll cycle can process multiple messages. Poll count is **not identical** to delivery count; define the denominator carefully when comparing throughput.

### MessageGroupStore and aggregators

Aggregator/resequencer groups can wait long durations due to missing parts, mismatched correlation, or store issues. Use:

- **Gauge** for the number of incomplete groups and backlog size (if the store supports efficient querying).
- **DistributionSummary** for group size **at release time**.
- **Timer** from group creation to release, provided timestamps are durable and clocks are reliable.
- **Counter** for normal releases, partial releases, timeouts, discarded late messages, and failures.

A completed group that retains metadata may have size 0; do not treat size=0 as meaning no state exists. Also, do not load **every payload of every MessageGroup** on every metrics scrape; use lighter metadata or stored aggregates.

## 12. Retry, errorChannel, and transactions: counts are easily inflated

Suppose:

~~~text
Broker: 2 deliveries
RequestHandlerRetryAdvice: 3 attempts per delivery
HTTP client: 2 attempts per handler call
~~~

In a total-failure scenario, theoretically **2 × 3 × 2 = 12 HTTP calls** can occur for **one business operation**.

Meters must be named strictly by unit:

| Metric | If recorded at the right point | Max count in example |
| --- | --- | ---: |
| Broker delivery Counter | Consumer receives one delivery | 2 |
| Handler attempt Timer count | Each handler execution | 6 |
| HTTP client attempt Timer count | Each HTTP call | 12 |
| Business operation Counter | One operation confirmed complete | 0 or 1 depending on business outcome |

This does not mean every flow automatically emits these exact numbers: outcomes depend on the adapter, retry configuration, and instrumentation points. The table simply illustrates how **a single operation can generate multiple technical events**.

### Recording outcome when errors propagate

Inside a handler:

- Measure Timers for both success and error using proper **try/catch/finally**.
- Let exceptions propagate outward when transactions/error handling need to handle them; do not catch and return success just to make metrics look clean.
- Use **outcome=error** and a Counter with **bounded error categories**; avoid tagging full exception stack traces.
- Separate **failed attempts** from **terminally failed business operations**.

On **errorChannel**:

- Count **ErrorMessage delivered**, without assuming it captures every exception across every layer.
- Inspect originalMessage or MessagingException.failedMessage when available to log with correlationId/eventId.
- Do not assume ErrorMessage carries business correlation in its outermost headers.
- When recovery routes to a DLQ, increment **dlq.published** only after the handoff is confirmed per contract.

### Metrics must not assume a transaction committed

If a handler increments **orders.operation.completed** before DB commit and the transaction rolls back, the Counter remains incremented. Micrometer Counters **do not participate in DB transactions** and do not roll back automatically with them.

To measure business completion more accurately:

- Define the source of truth as **DB state**, a committed outbox event, or the confirmed target system.
- Place the Counter at the **confirmed outcome** boundary, not when starting an update.
- With **afterCommit** callbacks, remember there is a crash window after commit before the callback runs: a metric event can be missed; operations dashboards should not use in-memory Counters as the sole audit ledger.
- Use **queries against durable data** or reconciliation if completion counts must be exact for financial/reconciliation purposes.

**Metrics are best-effort observations**, not a substitute for transaction ledgers or message delivery guarantees.

## 13. Testing Timer, Counter, and DistributionSummary with SimpleMeterRegistry

**SimpleMeterRegistry** lets you test meters right inside the JVM without a Prometheus server. Tests should verify:

- Meters **are registered with the expected names and tags**.
- One success/error call produces **exactly one sample** per unit of measurement.
- Timers record **non-negative** durations and accurate counts; do not write tests asserting exact nanosecond durations.
- Counters increment only at the right event and do not double-increment during retries/error flows.
- DistributionSummary records valid counts and uses the right byte/record unit.

### Unit testing a Timer around a handler

The JUnit 5 example below uses **InstrumentedOrderHandler** and **OrderProcessor** directly from Section 3:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

class HandlerMetricsTest {

    @Test
    void successCreatesOneSuccessSample() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            OrderProcessor processor = order -> {
                // Simulate a successful operation.
            };
            InstrumentedOrderHandler handler =
                    new InstrumentedOrderHandler(registry, processor);

            handler.handle(
                    MessageBuilder.withPayload(
                            new OrderCommand("O-42", 3)).build());

            Timer timer = registry.find("orders.handler.duration")
                    .tag("flow", "order-import")
                    .tag("handler", "order-handler")
                    .tag("outcome", "success")
                    .timer();

            assertNotNull(timer);
            assertEquals(1L, timer.count());
            assertTrue(timer.totalTime(
                    java.util.concurrent.TimeUnit.NANOSECONDS) >= 0);
        } finally {
            registry.close();
        }
    }

    @Test
    void failureIsTimedAndStillPropagates() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            OrderProcessor processor = order -> {
                throw new IllegalStateException("DB unavailable");
            };
            InstrumentedOrderHandler handler =
                    new InstrumentedOrderHandler(registry, processor);

            assertThrows(IllegalStateException.class, () ->
                    handler.handle(
                            MessageBuilder.withPayload(
                                    new OrderCommand("O-43", 2)).build()));

            Timer timer = registry.find("orders.handler.duration")
                    .tag("outcome", "error")
                    .timer();
            assertNotNull(timer);
            assertEquals(1L, timer.count());
        } finally {
            registry.close();
        }
    }
}
~~~

**Test limitation:** Calling handle(...) directly only tests **application-recorded metrics**. It **does not** verify framework-generated metrics when messages traverse DirectChannel, advice chains, or errorChannel. To test those, spin up a real Spring Integration context and send messages through channels.

### Testing Counter and DistributionSummary

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PayloadAndDuplicateMetricsTest {

    @Test
    void countsDuplicateAndRecordsPayloadBytes() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            DuplicateMeter duplicates = new DuplicateMeter(registry);
            PayloadSizeMetrics sizes = new PayloadSizeMetrics(registry);

            duplicates.duplicateWasSuppressed();
            duplicates.duplicateWasSuppressed();
            sizes.onPayload(new byte[128]);
            sizes.onPayload(new byte[512]);

            Counter counter = registry.find(
                    "orders.duplicate.suppressed").counter();
            DistributionSummary summary = registry.find(
                    "orders.payload.size").summary();

            assertNotNull(counter);
            assertEquals(2.0, counter.count());
            assertNotNull(summary);
            assertEquals(2L, summary.count());
            assertEquals(640.0, summary.totalAmount(), 0.0001);
        } finally {
            registry.close();
        }
    }
}
~~~

**Note:** If a backend exports units or renames metrics, looking up a meter in **SimpleMeterRegistry** by its registered API name is one thing; querying the series in a **Prometheus registry** may require the normalized name and unit suffix.

### Integration test: DirectChannel and ExecutorChannel

A realistic framework test should have two branches:

**Branch A — DirectChannel**

1. Create an IntegrationFlow with an inbound DirectChannel and a handler with a Timer.
2. Send a message and verify the handler completed before send returned.
3. Verify the handler Timer count incremented by exactly one for a non-retried delivery.
4. Have the handler throw an exception; verify error propagation and outcome=error.

**Branch B — ExecutorChannel**

1. Use a bounded executor and a **CountDownLatch** to keep the worker occupied.
2. Send a message; record dispatch duration separately around send().
3. Enqueue another message to create queue wait.
4. Release the latch and wait for the handler to finish using a bounded timeout condition.
5. Verify that a small **dispatch duration** can coexist with a **long queue wait**, while handler duration has its own sample.
6. Trigger an exception in the worker and verify the error flow is observable; do not assume the exception is thrown on the sending thread.

Do not use fixed Thread.sleep calls as the sole basis for timing assertions. Latency tests can vary under CI load; use **latches, fake clocks/clock abstractions, or Awaitility conditions** when verifying logic accurately.

## 14. @Timed, @Observed annotations and double-measurement risks

Beyond creating meters manually, Micrometer and the Spring ecosystem offer observability annotations/mechanisms such as **@Timed** and **@Observed**.

**Do not assume any annotation works immediately upon adding it to a method.** They require supporting infrastructure (such as Aspects/observation handlers or version-specific auto-configuration). In particular:

- An annotation on a **private method** or a method called via **self-invocation** may be missed by proxies/aspects if the solution relies on AOP.
- A Spring Integration endpoint may already be instrumented by management/observation; adding annotations and manual Timers can measure **the same execution multiple times**.
- When **@Observed** emits both observations/traces and metrics, avoid unintentionally configuring another Timer with the same meaning under different tags.
- Annotations usually measure **method execution**; with ExecutorChannel, they do not automatically measure full queue wait or end-to-end workflow duration.

### Choosing between automatic and manual instrumentation

| Requirement | Best fit |
| --- | --- |
| High-level view of channel/handler invocations | Built-in Spring Integration metrics/observation if configured |
| Measuring a specific business stage | Manual Timer or supported annotation |
| Attaching outcome once result is known | Timer.Sample with outcome tag |
| Counting duplicates blocked in DB | Counter at deduplication verification point |
| Measuring serialized payload bytes | DistributionSummary at serialization boundary |
| End-to-end SLA across messages/restarts | Durable timestamps/business state + completion instrumentation |
| Investigating a specific paymentId | Trace/logs with safe business IDs; not meter tags |

**How to check for duplicates:** Diagram every place meters are recorded, name the **unit of measurement** for each meter, and run a test sending N messages to reconcile counts. If N=10 yet a dashboard sums two different timer counts and reports 20 requests, fix the dashboard logic.

## 15. Sample dashboard for Spring Integration Runtime

A useful dashboard separates **traffic**, **latency**, **errors**, and **saturation**, while displaying endpoint health/lifecycle status.

| Panel area | Metric/chart | Question |
| --- | --- | --- |
| **Traffic** | Ingress deliveries per second | Is the source sending steadily or stalled? |
| **Handler latency** | Timer P50/P95/P99 and count | Which handler is slow? Are there enough samples? |
| **Queue wait** | Queue wait Timer P95 | Is backlog causing messages to wait too long? |
| **Errors** | Rate of handler errors, error messages, DLQ | Where do errors originate and is recovery completing? |
| **Retries** | Retry attempts per operation (estimated from business source) | Are retries amplifying load? |
| **Payload sizes** | DistributionSummary size P95 and max | Are unusually large payloads arriving? |
| **Saturation** | Queue depth, executor active/queued/rejections | Are workers or DB connections exhausted? |
| **Persistence** | MessageStore read/write latency, pending groups | Is the store becoming a bottleneck? |
| **Correlation** | Incomplete groups, expirations, discards | Are messages missing or groups releasing late? |
| **Lifecycle** | isRunning, desired vs actual, poll rate | Is a flow stopped, paused, or failing? |

### Sample PromQL: handler attempt throughput

If Timer **orders.handler.duration** is exported as a Prometheus histogram/timer count:

~~~promql
sum by (outcome) (
  rate(orders_handler_duration_seconds_count[5m])
)
~~~

This represents **handler attempts per second**, broken down by outcome. It is not directly the count of business operations.

### Sample PromQL: average handler duration

~~~promql
sum(
  rate(orders_handler_duration_seconds_sum[5m])
)
/
sum(
  rate(orders_handler_duration_seconds_count[5m])
)
~~~

Results are typically in **seconds** when Timers follow Prometheus export conventions; verify actual series names and units.

### Sample PromQL: handler attempt error ratio

~~~promql
sum(
  rate(orders_handler_duration_seconds_count{outcome="error"}[5m])
)
/
sum(
  rate(orders_handler_duration_seconds_count[5m])
)
~~~

**This is the error rate over handler attempts**, not the error rate per unique order. With retries, a failed first attempt followed by a successful retry still contributes to the numerator; that is useful for spotting downstream instability, but does not mean the order ultimately failed.

**Zero denominator:** When a flow is stopped or has no traffic, the expression may yield no value; do not replace it with "100% success" without indicating **no data** status.

### When to alert

Avoid alerting simply on "Total error Counter > 100", since cumulative totals keep rising with uptime. Instead use conditions like:

- Error **rate** or abnormal spike relative to baseline.
- P95 latency exceeding SLO **when traffic is sufficient for percentiles to be meaningful**.
- Queue depth or message age increasing steadily across multiple scrape intervals.
- Active executor threads near capacity, rising rejections, and falling handler throughput.
- DLQ or persistent retry pending age exceeding recovery windows.
- Incomplete MessageGroups older than SLA or duplicate business effects > 0.
- Desired state RUNNING while endpoint actual state is STOPPED or poll count is stagnant.

When the system restarts, Counters reset and gauges disappear or change values. Dashboards must account for **instance lifecycle** and **rates** rather than directly comparing cumulative totals across two JVM restarts.

## 16. Performance: meters have overhead too

Good instrumentation should not become a new bottleneck:

- **Cardinality:** Each tag combination is a separate meter. Dynamic orderIds create nearly as many meters as messages, consuming RAM and slowing backends.
- **Histograms:** Multiple buckets multiplied by tags increase memory/export overhead. Enable them only for a few critical latencies/sizes.
- **Hot path:** Do not serialize payloads solely to measure byte size if the main path does not need serialization; that can add significant CPU load.
- **Blocking metrics:** Recording a metric should never make synchronous network calls to a monitoring backend on the handler thread; use properly designed registries/exporters.
- **Sampling:** Metrics usually aggregate nearly every observation client-side; tracing can be sampled. Do not assume trace counts equal Counter totals.
- **Expensive Gauges:** A Gauge running heavy queries or scanning the entire MessageStore on every scrape can induce load or lock contention.
- **Exemplars:** If your backend supports attaching trace exemplars to histograms, use the properly configured capability rather than turning traceId into a fixed tag on every sample.

### Metadata and data privacy

Metric tags must contain only data appropriate for a monitoring system with proper access control. Never put account numbers, emails, customer names, raw exception messages, or payloads into metrics.

For traces/logs containing business keys:

- Use masking/hashing/tokenization where needed.
- Enforce retention and access controls.
- Avoid leaking payloads via error channels or exporters.
- Avoid creating high-cardinality metrics from unvalidated message header values.

## 17. Diagnostic scenario: flow is slow even though handler Timer looks good

Suppose the dashboard shows:

~~~text
Ingress = 1,500 messages/min
Handler P95 = 120 ms
Queue wait P95 = 15 s
Queue depth = 42,000 messages
Executor active = max workers
Error rate = 0.5%
~~~

**Appropriate conclusion:** The handler runs fast **once inside a worker**, but most latency comes from **queue wait/saturation**. Increasing the gateway timeout will not fix the root cause. Check ingress vs processing rate, consumer concurrency, DB capacity, contention, executor pools, and backpressure.

Another scenario:

~~~text
Ingress = 200 operations/min
Handler attempts = 850/min
HTTP calls = 1,700/min
Handler P95 = 2.5 s
HTTP timeout count rising
~~~

The rising attempts-to-operations ratio indicates **retry amplification**. Do not immediately multiply worker threads when downstream is already overloaded. Inspect retry ownership, max attempts, deadlines, backoff/jitter, circuit breakers, and idempotency.

Another scenario:

~~~text
Aggregator incomplete groups = 12,500
Incoming message rate is normal
Release rate drops near 0
MessageGroupStore read latency increases
~~~

Investigate correlation keys, release conditions, missing/out-of-order messages, persistent store/indexes, lock contention, and group expiry. Counting inbound messages does not prove a group has received **all required business parts**.

## 18. Hands-on exercise: instrumenting an order ingestion flow

**Problem statement:** The following flow runs two replicas and receives orders from a broker:

~~~text
Broker inbound adapter
   → ordersIngress
   → QueueChannel backed by persistent MessageStore
   → polling consumer
   → OrderHandler (DB + HTTP)
   → outbound event
   ↘ errorChannel / retry / DLQ
~~~

Observability requirements:

1. **Delivery** throughput and **business operations completed** must be separated.
2. Provide Timers for **handler attempt**, **queue wait**, and **outbound HTTP attempt**.
3. Provide Counters for **retry attempts**, **duplicate safely suppressed**, **DLQ published**, and **handler failed**.
4. Provide DistributionSummaries for **serialized payload bytes** and **batch records**.
5. Dashboard displays **P95 queue wait**, **P95 handler**, error rate, backlog, throughput, and endpoint state.
6. No metric tag contains orderId, eventId, correlationId, or traceId.
7. Test that retrying one operation three times is not counted as three completed orders.
8. After restarts, Counters may reset, yet DB/outbox remains the source of truth for business completion.

### Solution approach

**Step 1 — Draw the boundaries.** Identify exact moments of enqueue/dequeue, handler start/end, DB commit, HTTP request start/end, and business completion.

**Step 2 — Name the meters.** For example: orders.delivery.received, orders.queue.wait.duration, orders.handler.duration, orders.http.duration, orders.payload.size, orders.retry.attempted, orders.duplicate.suppressed.

**Step 3 — Choose tags.** flow, endpoint, outcome, and errorType from bounded sets; application/environment as common tags. Never add business IDs to meters.

**Step 4 — Instrument with Micrometer.** Use Timer.Sample around the handler in try/finally, Counters at meaningful event points, DistributionSummary at serialization/batch boundaries, and Gauges for backlogs.

**Step 5 — Verify built-in metrics.** If Spring Integration management already provides send/receive/handler meters, do not double-count them on dashboards or label them as business operation counts.

**Step 6 — Test.** Use SimpleMeterRegistry to verify counts/tags; use a real IntegrationFlow with DirectChannel/ExecutorChannel to verify scope; use persistent stores and broker tests for restarts/redeliveries.

**Step 7 — Build dashboards/alerts.** Use rate() for Counters, histogram_quantile() for histograms, and Gauges for backlogs. Distinguish **no traffic** from **healthy throughput**.

### Recommended test matrix

| Case | Input/scenario | Assertion |
| --- | --- | --- |
| 1 | Handler succeeds once | Timer outcome=success count=1 |
| 2 | Handler throws RuntimeException | Timer outcome=error count=1, exception still propagates |
| 3 | Same eventId redelivered twice | Duplicate Counter increments by 1 if second is suppressed |
| 4 | Handler retries 3 attempts | Handler Timer counts attempts; business completion does not increment by 3 |
| 5 | Payloads of 128 and 512 bytes | Summary count=2, sum=640 bytes |
| 6 | Executor queue blocked with latch | Queue wait increases; send duration is not mistaken for end-to-end |
| 7 | Empty poll with no message | Poll Counter increments; ingress delivery Counter does not |
| 8 | ErrorChannel handles same error from handler | Do not double-count the same handler.failed metric |
| 9 | Transaction rolls back after handler | Do not mark business operation completed if DB did not commit |
| 10 | Restart between delivery and ack | New meters may reset; idempotency/DB outcome remains accurate |
| 11 | 10,000 distinct orderIds | Series count does not grow with orderId |
| 12 | Group missing parts beyond SLA | Incomplete/timeout/discard metrics reflect true outcome |

## 19. Pre-production checklist

- Distinguished **Counter, Timer, DistributionSummary, and Gauge** based on actual data to measure?
- Does each meter have a clear **unit and event boundary** definition?
- Does the handler Timer record both **success and error**?
- Separated **dispatch/send**, **queue wait**, **handler processing**, and **end-to-end SLA**?
- Across ExecutorChannel, avoided treating send latency as business latency?
- When a poller returns null, avoided wrongly incrementing message delivery counts?
- Do retry metrics distinguish **delivery, handler attempt, external call, and business operation**?
- Do errorChannel metrics avoid double-counting errors already recorded at the handler?
- Is the business completion Counter recorded **after commit** (or reconciled) rather than before commit where rollbacks skew counts?
- Does DistributionSummary use **actual bytes/actual record counts** instead of confusing String length?
- Verified metric names, base units, and Prometheus export rules in the current version?
- Are histograms/P95/P99 actually enabled, backed by sufficient traffic, and free of excessive cardinality?
- Do tags use only bounded sets, excluding orderId/eventId/correlationId/traceId/exception messages?
- Do dashboards use appropriate **rate/increase** functions when Counters reset after restarts?
- Included **backlog Gauges** and executor saturation indicators rather than relying only on handler Timers?
- Avoided double-measuring between built-in Spring Integration metrics/Observation and custom meters?
- Are management endpoints authenticated/access-controlled and free of sensitive data leaks?
- Covered SimpleMeterRegistry unit tests, channel/poller/executor integration tests, and retry/restart tests?

## Conclusion

**Micrometer Timer, Counter, and DistributionSummary** are three distinct yet complementary observability tools: **Timer** measures duration, **Counter** counts events, and **DistributionSummary** tracks value distributions such as byte size or batch size. Choosing the wrong meter type or placing boundaries incorrectly produces a dashboard that looks precise while misleading investigations.

In Spring Integration Runtime, metrics must be interpreted alongside **channels, endpoints, pollers, consumers, executors, transactions, retries, message stores, error flows, and correlation**. A Timer around send on an ExecutorChannel does not measure queue wait; a handler Counter does not represent unique business operations; a DB rollback does not roll back a Micrometer Counter. Therefore, define units of measurement, bound cardinality, combine logs/traces, and reconcile measurements against durable business state.

When implemented and tested properly, these three meters surface **backpressure, retry storms, latency tails, abnormal payloads, and recovery failures**, enabling evidence-based operational decisions instead of relying on isolated logs or ambiguous totals.

## References

- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer Reference — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)

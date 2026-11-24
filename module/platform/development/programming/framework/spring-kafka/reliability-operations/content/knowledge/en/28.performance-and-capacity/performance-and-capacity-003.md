# Listener Processing Time

## 1. What Is Listener Processing Time?

In Spring Kafka, **listener processing time** is the time the application spends processing data after the Kafka consumer receives a record and invokes the listener method. It is a critical performance metric because it affects throughput, consumer lag, the ability to retain partition assignments, and service capacity.

For example, Order Fulfillment consumes the `orders.created` topic. Each record needs data validation, reading order state, calling Inventory, and writing the result to the database. If the listener processes in 40 ms on average while p99 reaches 3 seconds, some partitions may fall behind even though the average still looks healthy.

~~~text
Kafka broker
    |
    | ConsumerRecord
    v
KafkaConsumer.poll()
    |
    v
Spring Kafka listener container
    |
    v
@KafkaListener method
    |
    +--> validate event
    +--> load business state
    +--> call downstream services
    +--> update database
    |
    v
Listener returns / throws
    |
    v
Acknowledgment, error handling, next poll
~~~

You need to distinguish listener processing time from:

- **Poll duration:** the time a `KafkaConsumer.poll()` call takes to return.
- **End-to-end event latency:** the time from when the producer creates/publishes the event until the business outcome completes.
- **Consumer lag:** the gap between the offset the consumer has processed/committed and the log end offset.
- **Commit latency:** the time needed to commit offsets or complete a transaction.
- **Downstream latency:** the time for DB, HTTP, cache, or dependent services to respond.

A listener can process quickly while the consumer still lags due to too few partitions/concurrency, slow broker fetches, or downstream commits. Conversely, poll may return quickly while the listener takes a long time before the next poll.

## 2. Why Does Processing Time Matter?

Processing time determines how many records each consumer can complete in a unit of time. When the incoming message rate exceeds the processing rate, a backlog builds up.

Example:

~~~text
Producer rate       = 1,000 records/second
Consumer capacity   =   700 records/second

Backlog growth      =   300 records/second
~~~

Even when the listener has no errors, the system still cannot keep up with traffic. If this persists, consumer lag and event age grow, potentially violating business SLAs.

Processing time also impacts:

- Time between polls.
- max.poll.interval.ms and group membership.
- Number of consumer instances required.
- Batch size and memory pressure.
- Database connection pools and HTTP connection pools.
- Retry frequency and duplicate processing.
- CPU, memory, tracing, and metrics costs.
- Recovery capability after a traffic spike.

Do not optimize average processing time alone. Percentiles, throughput, lag, and downstream saturation must be evaluated together.

## 3. Milestones in Processing a Record

A record goes through multiple distinct intervals:

~~~text
t0: producer creates event
 |
 v
t1: record appended by broker
 |
 v
t2: consumer poll receives record
 |
 v
t3: listener starts
 |
 v
t4: listener completes or throws exception
 |
 v
t5: acknowledgment / offset commit completes
 |
 v
t6: business outcome confirmed downstream
~~~

Corresponding metrics:

| Interval | Meaning |
|---|---|
| t0 to t1 | Producer-side creation/publish delay, depending on timestamp |
| t1 to t2 | Broker retention/fetch/consumer scheduling delay |
| t2 to t3 | Container dispatch delay |
| t3 to t4 | Listener processing time |
| t4 to t5 | Ack/commit/transaction completion |
| t0 to t6 | End-to-end business latency |

Do not use Kafka record timestamps as an absolute clock if producer and consumer clocks are not synchronized. For end-to-end latency, you must define the timestamp source and clock synchronization.

### 3.1. Measuring the Right Boundary

If you start a timer at the beginning of the listener and stop right before returning, the timer measures the method body duration. If the timer covers validation, DB, and HTTP calls, that is the listener processing duration from the application's perspective.

If you want to measure time up to Kafka offset commit, you need instrumentation at the appropriate container/ack/transaction lifecycle point. Do not add commit time into the listener timer by guesswork.

## 4. Record Listeners and Batch Listeners

Spring Kafka supports two common listener types.

A **record listener** receives one ConsumerRecord at a time:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Each invocation processes one record. A processing timer can measure a single method invocation.

A **batch listener** receives a list of records:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "ordersBatchFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (var record : records) {
        orderService.process(record.value());
    }
}
~~~

One invocation processes multiple records. If a timer wraps the entire method, the result is **batch processing time**, not the latency of individual records.

For example, a batch has 100 records and the method takes 500 ms:

- Batch duration = 500 ms.
- Simple average service time by division = 5 ms/record.
- However, you cannot conclude that every record took 5 ms.
- One record might have taken 300 ms while the remaining records were faster.

### 4.1. Choosing the Right Unit

| Listener type | What does a method-level timer measure? | What else is needed for per-record latency? |
|---|---|---|
| Record | One record invocation | Usually already close to per-record duration |
| Batch | Entire batch | Separate timer/metric inside the loop or version-appropriate per-record observation |
| Async handoff | Task submission time | Timer inside the worker to measure business completion |
| Transactional listener | Listener method duration | Add transaction/commit outcome if needed |

With batches, monitor batch size, batch duration, and throughput in records/second simultaneously.

## 5. Factors That Make Up Processing Time

A listener typically performs several steps:

~~~text
Listener invocation
       |
       +--> Deserialize / conversion (usually before method)
       |
       +--> Validation
       |
       +--> Business rules
       |
       +--> Database reads/writes
       |
       +--> HTTP / RPC calls
       |
       +--> Cache / lock / filesystem
       |
       +--> Result mapping
       |
       v
Method returns
~~~

Note that deserialization, interceptors, and container dispatch may sit outside the method-level timer boundary depending on instrumentation. If you need to measure the full pipeline from fetch to business completion, measure at the corresponding points.

Factors that commonly consume the most time:

- Database queries, transaction locks, or connection pool waits.
- HTTP calls to other services.
- Synchronous retry/backoff.
- CPU-heavy JSON transformations or cryptography.
- Overly large batches.
- Lock contention on shared state.
- Garbage collection and memory allocation.
- Thread scheduling/CPU throttling.
- Overly heavy logging or tracing.
- Schema registry or external lookups on the hot path.

Do not assume a slow listener is caused by the Kafka broker. Most business processing time resides inside the application or its dependencies.

## 6. Manual Measurement with System.nanoTime()

A simple approach is using System.nanoTime() to measure duration inside the listener:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    long started = System.nanoTime();

    try {
        orderService.process(event);
    }
    finally {
        long elapsedNanos = System.nanoTime() - started;

        log.debug(
            "Order listener processing completed in {} ms",
            elapsedNanos / 1_000_000.0
        );
    }
}
~~~

**System.nanoTime()** is suitable for measuring time intervals within the same JVM because it is a monotonic clock. Do not use System.currentTimeMillis() to measure short durations because the wall clock can jump due to time synchronization.

The code above still logs duration in finally if the business service throws an exception. If you want to distinguish success and failure, record the outcome explicitly:

~~~java
long started = System.nanoTime();
String result = "success";

try {
    orderService.process(event);
}
catch (RuntimeException ex) {
    result = "failure";
    throw ex;
}
finally {
    long elapsed = System.nanoTime() - started;
    processingMetrics.record(elapsed, result);
}
~~~

In production, use Timer/Observation to obtain histograms and percentiles instead of only logging individual durations.

## 7. Using Micrometer Timer

Micrometer Timer measures execution count and completion time. A Timer can provide:

- Count.
- Total time.
- Max.
- Histograms/percentiles if configured.
- Distribution statistics depending on the registry.

Example custom Timer:

~~~java
@Component
public class OrderProcessingMetrics {

    private final Timer timer;

    public OrderProcessingMetrics(MeterRegistry registry) {
        this.timer = Timer.builder("app.kafka.order.processing")
            .description("Time spent processing an order event")
            .tag("listener", "orders-created")
            .register(registry);
    }

    public void record(Runnable action) {
        timer.record(action);
    }
}
~~~

Listener:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    processingMetrics.record(() -> orderService.process(event));
}
~~~

This is a custom metric. If Spring Kafka already creates a timer for the listener, check existing metrics before creating another timer with overlapping semantics.

### 7.1. Measuring Both Success and Failure

A Timer typically measures duration for both successful and failed invocations if the wrapper records in finally. If you need to classify outcomes, add a `result` tag with a bounded set of values:

~~~text
result=success
result=failure
~~~

Do not put exception messages, stack traces, or error IDs into metric tags. If exception types are needed, map them to a bounded set of categories such as timeout, validation, dependency, or other.

### 7.2. Do Not Create a Timer per Record

Do not create a new MeterRegistry.timer() using a record key or correlation ID. Creating meters per message ID causes unbounded time-series growth.

Register timers with a fixed or allowlisted low-cardinality tag set.

## 8. Spring Kafka Micrometer Listener Timers

Spring Kafka supports Micrometer metrics for listener containers. In legacy Micrometer timer configuration, listener processing is measured and exported under a metric named by Spring Kafka convention, typically **spring.kafka.listener** in modern versions.

The container can enable/disable instrumentation via property:

~~~java
factory.getContainerProperties()
    .setMicrometerEnabled(true);
~~~

Static tags can be added:

~~~java
factory.getContainerProperties()
    .setMicrometerTags(Map.of(
        "application", "fulfillment-service",
        "environment", "production"
    ));
~~~

Some versions support `micrometerTagsProvider` to add dynamic tags per ConsumerRecord for record listeners. This provider does not apply to batch listeners and is not used when `observationEnabled=true`.

Meter names, default tags, and behavior can differ across versions. Check the actual metrics in the registry or actuator endpoint rather than assuming tag names from another version.

### 8.1. Metric Tags Should Have Low Cardinality

Suitable examples if topic/family have a managed set of values:

~~~text
listener=orders-created
topic=orders.created
environment=prod
event.family=order
~~~

Do not use:

~~~text
order.id=order-913828
correlation.id=order-flow-9281
offset=9812371
~~~

Values that change per message belong in controlled logs/traces, not metric labels.

## 9. Micrometer Observation and Tracing

Since Spring Kafka 3.0, listener containers can use Micrometer Observation. When `observationEnabled` is turned on and an ObservationRegistry is configured, the framework can create observations for listeners; registered handlers can emit metrics and tracing spans.

~~~java
var properties = factory.getContainerProperties();

properties.setObservationEnabled(true);
properties.setObservationRegistry(observationRegistry);
~~~

Observation enables a single shared instrumentation source for metrics and traces:

~~~text
Kafka listener invocation
          |
          v
       Observation
          |
     +----+----------------+
     |                     |
     v                     v
Meter handler        Tracing handler
     |                     |
     v                     v
Timer metrics          Span
~~~

Enabling observation does not by itself guarantee backend spans. You still need a Micrometer Tracing bridge, exporter, sampler, and tracing backend.

### 9.1. Observation vs. Custom Timer

- Observation integrates metrics/tracing under a single shared lifecycle.
- Manual Timer is suitable for measuring an isolated piece of business logic.
- Both can be used if they measure different boundaries.
- Do not create two metrics with the same name/semantics for one invocation and sum them as if they were two different types of work.

If listener observation is already present, a custom Timer should measure a specific stage such as the database stage or a downstream call.

## 10. Percentiles Matter More Than Averages

Average processing time can hide tail latency.

Example with 100 records:

- 95 records process in 10 ms.
- 5 records process in 2 seconds.

Average:

~~~text
(95 x 10 ms + 5 x 2000 ms) / 100
= 109.5 ms
~~~

An average of 109.5 ms may not look too high, yet 5% of records take 2 seconds. For critical events, tail latency can violate SLAs.

What to observe:

| Statistic | Question |
|---|---|
| p50 | How long does a typical case take? |
| p90 | Where does the slowest 10% start? |
| p95 | Common tail latency |
| p99 | Very slow cases |
| max | Are there any spikes or outliers? |
| count | How many invocations were measured? |
| total time | Total processing time |
| throughput | How many records complete per second? |

Percentiles are computed according to what the backend supports. Client-side percentiles and histogram buckets have different semantics and costs. For Prometheus, histograms are generally suitable for aggregating across multiple instances.

## 11. Configuring Histograms and Percentiles

Example custom Timer with a histogram:

~~~java
Timer.builder("app.kafka.order.processing")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(50),
        Duration.ofMillis(100),
        Duration.ofMillis(250),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

SLO buckets should reflect business requirements. If an order event must be processed within 200 ms, 50/100/250 ms buckets can be useful. If a listener calls an external service with higher latency, buckets should match reality.

Do not enable percentile histograms on every metric unconditionally. Histogram buckets create extra time series and ingestion cost. Set a budget and enable them only on critical listeners.

## 12. How Does Batch Size Affect Processing Time?

With a batch listener, total duration usually increases with record count and per-record complexity.

Example:

~~~text
batch size = 100
average per-record work = 8 ms
sequential processing estimate = 800 ms
~~~

This is a simple estimate. A batch may have shared setup costs, database bulk operations, or parallelism, so actual duration does not necessarily equal plain multiplication.

What to measure:

- Batch size.
- Batch processing duration.
- Records processed per batch.
- Average/p95 time per record if instrumented.
- Failure count and retry count.
- Time spent in shared DB/bulk operations.

### 12.1. max.poll.records

The Kafka consumer property **max.poll.records** limits the number of records returned in a single poll. A high value can increase throughput if batch processing is efficient, but can also prolong batch processing time and increase memory pressure.

Lowering `max.poll.records` can help:

- Reduce processing time per batch.
- Reduce the number of in-flight records.
- Cap the interval between polls.
- Reduce the amount of work to retry when a batch fails.

However, lowering it too far can increase poll overhead and reduce throughput. Benchmark with real payloads and dependencies.

### 12.2. Batch Database Writes

If the listener can use bulk inserts/updates, batch processing is sometimes faster than processing each record individually. However, large batches can hold transactions/connections longer and worsen p99.

Choose batch size based on DB capacity, lock contention, memory, and SLAs.

## 13. max.poll.interval.ms and Processing Time

**max.poll.interval.ms** is the allowed time limit between polls within a consumer group. If a listener processes for too long before polling again, the consumer may be considered stalled and partition assignments may change.

Example:

~~~text
max.poll.interval.ms = 300000 ms (5 minutes)

poll() returns 200 records
listener takes 360 seconds to process the batch
next poll arrives too late
~~~

The consumer risks leaving the group/triggering a rebalance for exceeding `max.poll.interval.ms`.

Do not solve every problem by raising `max.poll.interval.ms`. If a listener hangs due to an HTTP call without a timeout, raising the interval only prolongs the incident and allows consumer lag to grow longer.

### 13.1. Accounting for Total Time Between Polls

Time between polls can include:

- Processing records in the batch.
- Error handling and blocking backoff.
- Rebalance callbacks.
- Transaction completion.
- GC pauses or CPU starvation.
- Other synchronous work on the consumer thread.

A listener method taking 30 seconds does not always mean the poll interval is 30 seconds if there are multiple polls/dispatches in the flow; check the actual container mode and threads.

## 14. pollTimeout vs. Processing Time

**pollTimeout** is the time the consumer poll waits for records. **Listener processing time** is the time spent processing records after poll returns data.

~~~text
pollTimeout = 5 seconds

poll():
  returned 20 records in 40 ms

listener:
  processes records in 2.5 seconds

next poll()
~~~

In the example, poll latency is 40 ms; batch/listener processing time is 2.5 seconds. Changing `pollTimeout` does not make business logic faster.

If poll returns empty, poll wait time can reach up to `pollTimeout`, yet listener processing time has no corresponding invocation.

## 15. Downstream Latency and Connection Pools

Listeners often call databases or HTTP services. When downstream slows down, listener processing time rises.

Example:

~~~text
Listener processing = 900 ms
  validation         =  10 ms
  database pool wait = 300 ms
  SQL execution      = 100 ms
  payment HTTP       = 450 ms
  mapping/logging    =  40 ms
~~~

Optimization requires measuring each stage:

- Connection pool wait time.
- Query execution time.
- HTTP connection acquisition.
- DNS/TLS handshake.
- Remote response time.
- Retry/backoff duration.
- Serialization/deserialization.

A DB query itself can be fast yet wait 300 ms for a connection because the pool is exhausted. Measuring query duration alone will miss this bottleneck.

### 15.1. Dependency Timeouts

Set connect timeouts, response/read timeouts, and overall deadlines for HTTP/RPC. For databases, set appropriate query timeouts and transaction timeouts.

Never let a downstream call block the consumer thread indefinitely. Retries must be bounded with backoff; otherwise, a dependency outage can tie up the entire listener capacity.

## 16. Retries Increase Processing Time

When a listener throws an exception, the Spring Kafka error handler can retry the record. A single business event may undergo multiple processing attempts.

~~~text
Attempt 1 -> DB timeout -> backoff 1s
Attempt 2 -> DB timeout -> backoff 2s
Attempt 3 -> success
~~~

Distinguish between:

- **Attempt duration:** duration of a single listener invocation.
- **Retry backoff:** wait time between attempts.
- **Total recovery time:** total time from the first attempt to the final outcome.
- **End-to-end latency:** may also include queue wait before the first attempt.

If the timer sits inside the listener method, it typically measures each invocation rather than automatically adding backoff time outside the method. To measure total recovery time, track state/timing at the retry workflow layer or use an enclosing tracing span.

### 16.1. Retries Are Not Capacity

Retries can reduce throughput because the same record consumes multiple attempts. If a dependency is failing, blindly increasing concurrency or shortening backoff can put even more load on an already weakened dependency.

Monitor attempt count, failure rate, backoff duration, and DLT rate alongside the processing timer.

## 17. Error Handlers and DLT Affect Latency

`DefaultErrorHandler` can retry and then recover a record. If backoff is long, the total time from initial receipt to recovery can be very large even when each individual listener invocation is short.

~~~text
Listener attempt
     |
     v
Exception
     |
     v
Error handler
     |
     +--> Backoff
     |
     +--> Retry listener
     |
     +--> Recoverer / DLT
~~~

Measure separately:

- Listener invocation duration.
- Error handler retry count.
- Backoff time.
- Recovery/DLT publish duration.
- Total time to final outcome.

Do not lump everything into a single timer so you can no longer tell whether business code is slow or the retry policy is long.

## 18. Transactions and Acknowledgment

With `AckMode` RECORD, BATCH, MANUAL, or MANUAL_IMMEDIATE, the commit/ack point differs. Listener processing time does not necessarily include offset commit time.

With transactional listeners, a transaction may encompass listener processing as well as Kafka send/offset operations. Transaction completion can add latency after the method body finishes.

If you need end-to-end commit latency, measure the transaction lifecycle or commit outcome at the right point. Do not infer that the commit is finished merely because the listener method returned.

### 18.1. Database Side Effects and Kafka Offsets

If a listener writes to a database and the consumer crashes before the Kafka offset is committed, the record may be redelivered. The listener processing timer will record another invocation, even though the business event only has one intended outcome.

Use idempotency or an inbox pattern to protect side effects and understand the semantics of success metrics properly.

## 19. Concurrency and Throughput

Spring Kafka concurrency creates multiple child consumers inside a listener container. Increasing concurrency can increase parallel processing capability, though it still depends on partition count.

~~~text
Topic: orders.created (6 partitions)

concurrency = 3
  child 0 -> P0, P1
  child 1 -> P2, P3
  child 2 -> P4, P5
~~~

If concurrency exceeds the number of partitions, some child consumers may not be assigned any partitions. Increasing concurrency beyond partition count does not automatically increase throughput.

Considerations:

- Partition count.
- CPU cores and CPU throttling.
- DB connection pool capacity.
- HTTP downstream rate limits.
- Listener thread blocking.
- Ordering requirements.
- Consumer group rebalance overhead.

### 19.1. Estimating Throughput

If one record takes 20 ms on average and is processed sequentially on a single consumer thread:

~~~text
1 / 0.020 seconds = 50 records/second
~~~

With 6 independent consumers, theoretical throughput could approach 300 records/second if partitions and downstream permit. Actual throughput will be lower due to polling, serialization, networking, commits, locks, and shared dependencies.

Do not treat this simple formula as a capacity commitment. Benchmark with a representative workload.

## 20. Blocking and Asynchronous Processing

A synchronous listener holds the consumer thread while processing:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    inventoryClient.reserve(event);
    paymentClient.authorize(event);
    orderRepository.save(event);
}
~~~

If an HTTP call takes 2 seconds, the consumer thread is held for that duration. This reduces poll frequency and can impact `max.poll.interval.ms`.

You can offload some work to async processing, but offset acknowledgment must be designed carefully. If the listener submits a task and returns, the container may treat the invocation as complete and commit the offset before the async task succeeds.

Options:

- Keep synchronous processing, but configure timeouts and optimize dependencies.
- Use batch/bulk operations.
- Build an application-level work queue with durable handoff.
- Use async listener return types/acknowledgment patterns supported by your Spring Kafka version.
- Only commit once business completion semantics are satisfied.

**Async does not automatically increase throughput** if downstream remains the bottleneck or the queue is unbounded.

## 21. Thread Pools and Backpressure

If a listener submits tasks to an executor, configure limits for:

- Core/max pool size.
- Queue capacity.
- Rejection policy.
- Task timeout/cancellation.
- Shutdown behavior.
- Context propagation.
- Acknowledgment semantics.

An unbounded queue can make the listener processing timer appear very low (measuring only submission time) while actual wait time and memory grow continuously.

~~~text
Kafka listener
     |
     v
Executor queue
     |
     v
Worker threads
     |
     v
Database / HTTP
~~~

Measure separately:

- Listener handoff duration.
- Queue wait time.
- Worker execution time.
- Queue depth.
- Rejected task count.
- Total time to business completion.

Backpressure must adapt the producer rate or consumer intake to real capacity, rather than merely shifting backlog from Kafka into RAM.

## 22. Batch Size, Concurrency, and Memory

Increasing batch size can reduce per-record overhead, but increases:

- Object allocations.
- Heap usage.
- GC pressure.
- Transaction duration.
- Retry cost when a batch fails.
- Interval between polls.

Increasing concurrency can increase parallelism, but also increases connection usage and DB contention.

Change one parameter at a time and measure the same workload:

| Parameter | Potential Positive Impact | Risk |
|---|---|---|
| max.poll.records | Larger batches, amortized overhead | Long processing, high memory |
| concurrency | More consumer threads | DB/HTTP saturation, rebalances |
| fetch.min.bytes | Fetch efficiency in suitable workloads | Higher latency waiting for data |
| fetch.max.wait.ms | Can improve batching | Longer fetch waits |
| max.poll.interval.ms | Tolerates longer processing | Slower detection of failed consumers |
| DB pool size | Reduces pool wait if DB has spare capacity | DB overload, connection contention |

Do not increase everything at once, as it becomes difficult to determine which change produced which effect.

## 23. Measuring Each Stage in Business Logic

A listener can use separate Timers for individual steps:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    validationTimer.record(() -> validator.validate(event));

    Order order = databaseTimer.recordCallable(
        () -> orderRepository.load(event.orderId())
    );

    paymentTimer.record(() -> paymentClient.authorize(order));

    persistenceTimer.record(() -> orderRepository.markPaid(order.id()));
}
~~~

This example only illustrates the concept; handle checked exceptions and return values appropriately with Micrometer's Timer API.

Stage timers reveal whether the bottleneck is in validation, DB, payment, or persistence. Use stable metric names, low-cardinality tags, and never create meters keyed by order ID.

If a listener has multiple business branches, keep semantics consistent so the sum of stage durations remains explainable. Not every set of stage timers sums cleanly to the listener timer due to overhead, parallel work, or nested calls.

## 24. Structured Logging and Slow Listener Diagnostics

You can log warnings when a listener exceeds a threshold:

~~~java
long started = System.nanoTime();

try {
    orderService.process(event);
}
finally {
    long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);

    if (elapsedMs > 500) {
        log.warn(
            "Slow Kafka listener: listener={}, durationMs={}, eventType={}",
            "orders-created",
            elapsedMs,
            event.getClass().getSimpleName()
        );
    }
}
~~~

The 500 ms threshold is just an example. Choose it based on SLAs and actual distributions.

Do not log payloads, tokens, customer data, or raw keys solely for diagnostics. Use approved correlation IDs/trace IDs to link logs and traces.

### 24.1. Logging Every Record Can Become Its Own Bottleneck

At high throughput, an INFO log for every record can turn logging I/O into a significant portion of listener processing time. Use metrics for aggregates and log selectively for slow/error cases.

Log sampling should preserve enough diagnostic information without losing all evidence on rare incidents.

## 25. Defining SLOs for Listener Processing

An SLO should clearly define:

- Does it measure record invocation or end-to-end event latency?
- Where does it start and end?
- Does it include retry/backoff?
- Does it include commit/transaction?
- Does it measure success only or failures as well?
- Which percentile is used?
- What time window?
- Which listeners are critical?

Example:

~~~text
SLO:
  99% successful orders.created listener invocations
  complete within 250 ms over a rolling 30-minute window
~~~

This SLO does not mean 99% of published events reach business completion within 250 ms if producer-to-consumer queue delay is not measured.

### 25.1. Multi-Signal Alerting

A useful alert can combine:

- Rising p95/p99 processing time.
- Rising consumer lag.
- Dropping throughput.
- Rising error/retry rate.
- Rising downstream latency.

Alerting solely on high average latency can miss tail latency. Alerting solely on high lag cannot distinguish a slow consumer from a producer spike.

## 26. Benchmarking and Capacity Planning

Benchmarking listener processing requires a representative workload:

1. Production-like payload sizes.
2. Realistic event type distribution.
3. Similar success/failure/retry ratios.
4. Production-like database and downstream latency.
5. Intended partition count and concurrency.
6. Production-like logging/tracing settings.
7. JVM and JIT warm-up.
8. Measure throughput, p50/p95/p99, lag, CPU, heap, and connection pools.
9. Run long enough to observe GC and sustained load.
10. Test burst traffic and recovery after a dependency outage.

Do not benchmark against a mock service responding in 1 ms and treat the result as production capacity.

### 26.1. Little's Law as an Estimate

Little's Law:

~~~text
L = lambda x W
~~~

Where:

- `L` is the average number of items in the system.
- `lambda` is the average throughput.
- `W` is the average time in the system.

If a consumer receives 500 records/second and a record spends an average of 0.2 seconds in the pipeline, the average number of records in-flight/queued under this simple model is:

~~~text
L = 500 x 0.2 = 100 records
~~~

This is a steady-state system estimate. It does not replace measuring lag or calculating partition capacity; define the boundary of `W` precisely.

## 27. Runbook When Listener Processing Time Increases

1. Identify listener ID, topic, group, and deployment version.
2. Compare p50, p95, p99, and max against the baseline.
3. Inspect throughput and consumer lag per partition.
4. Determine whether it is a record listener or batch listener.
5. Check batch size, max.poll.records, and concurrency.
6. Measure DB connection pool wait and query latency.
7. Measure HTTP/RPC latency, timeouts, and retry counts.
8. Check CPU, heap, GC pauses, and thread contention.
9. Check max.poll.interval.ms and rebalance events.
10. Separate listener invocation time from retry backoff and commit latency.
11. Inspect traces/logs of a few permitted slow samples.
12. Optimize the specific bottleneck rather than blindly increasing concurrency.
13. Change one parameter at a time and benchmark.
14. Confirm p95/p99, throughput, and lag improve together.
15. Verify duplicate/replay and offset commit semantics after changes.

When listener processing time is low yet lag keeps growing, examine producer rate, partition count, fetch/poll behavior, assignments, and broker capacity. Do not blame every backlog on the business method.

## 28. Common Misconceptions

**Listener processing time equals poll duration.** False; poll can return quickly while the listener takes a long time.

**Low average means the listener is healthy.** False; p95/p99 can still be very high.

**A batch timer is a per-record timer.** False; it usually measures the entire invocation/batch.

**Increasing concurrency always increases throughput.** False; partition count and downstream capacity bound it.

**Increasing `max.poll.interval.ms` fixes a slow listener.** It only changes the liveness threshold; it does not make code faster.

**Reducing `pollTimeout` makes business logic faster.** Incorrect; `pollTimeout` is the poll wait duration.

**A listener timer includes offset commits.** Not by default; commits/transactions have their own lifecycle.

**Retry backoff is inside the listener timer.** Not necessarily; it depends on where instrumentation is placed.

**Submitting an async task means business processing is complete.** False; it may only mean handoff to a queue.

**A metric label can be `order ID` for debugging.** False; use logs/traces according to policy.

**Increasing batch size is always good.** It can increase memory, tail latency, and retry costs.

**Logging every record makes investigation easier.** Logging volume itself can become a bottleneck.

## 29. Implementation Checklist

- [ ] Defined listener processing time boundaries.
- [ ] Distinguished poll, listener, commit, and end-to-end latency.
- [ ] Identified record vs. batch listener.
- [ ] Enabled Micrometer timers or Observation appropriate to the version.
- [ ] Tracked p50/p95/p99 and throughput.
- [ ] Added stage timers for DB/HTTP if needed.
- [ ] Used low-cardinality metric tags.
- [ ] Avoided attaching record keys, offsets, or correlation IDs as metric labels.
- [ ] Monitored batch size and max.poll.records.
- [ ] Compared max.poll.interval.ms against worst-case processing.
- [ ] Configured timeouts and bounded retries for dependencies.
- [ ] Implemented backpressure and bounded executor queues.
- [ ] Avoided committing offsets before async business completion.
- [ ] Protected side effects with idempotency.
- [ ] Benchmarked with realistic payloads/dependencies.
- [ ] Alerted on a combination of latency, lag, throughput, and failures.
- [ ] Maintained a runbook for investigating slow listeners.

## 30. References

- Spring Kafka Reference — Monitoring: https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html
- Spring Kafka Reference — Micrometer Observation: https://docs.spring.io/spring-kafka/reference/appendix/micrometer.html
- Spring Kafka Reference — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Micrometer Documentation — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Apache Kafka Consumer Configuration — max.poll.interval.ms and max.poll.records: https://kafka.apache.org/documentation/#consumerconfigs

Verify against your application's exact Spring Kafka, Micrometer, and Kafka client versions, as meter names, default tags, batch observation, and auto-configuration may change between versions.

## 31. Key Takeaways

**Listener processing time** measures how long the application takes to process a record or batch inside a listener. It differs from poll duration, consumer lag, commit latency, and end-to-end event latency. To locate bottlenecks, define measurement boundaries and observe p50/p95/p99 alongside throughput and lag.

Spring Kafka can provide Micrometer listener timers or Observation; custom Timers are useful for measuring business stages like databases and downstream calls. With a batch listener, a timer wrapping the method typically measures the whole batch rather than each individual record. Retry/backoff and transaction completion may also fall outside the listener method timer.

Optimization requires measuring downstream latency, batch size, concurrency, max.poll.records, max.poll.interval.ms, CPU/GC, and connection pools. Never increase concurrency or batch size blindly; use representative benchmarks, timeouts, backpressure, and idempotency. Only consider a listener healthy when latency, throughput, lag, and offset progress all meet operational targets.


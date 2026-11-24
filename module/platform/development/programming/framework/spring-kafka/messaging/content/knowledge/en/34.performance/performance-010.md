# Avoiding Blocking in Listeners

In Spring Kafka, listeners are typically invoked on a consumer thread managed by the listener container. While a listener is processing a record, that consumer has not yet returned to its `poll()` loop to fetch the next data. If the listener waits on I/O for too long, awaits a future, holds a lock, or runs prolonged computation, the time between polls grows, throughput drops, and the consumer may exceed `max.poll.interval.ms`.

Avoiding blocking does not mean every listener must be asynchronous. Synchronous processing in a listener remains appropriate when work has bounded duration, explicit timeouts, and sufficient throughput. What matters is controlling processing time, preventing slow dependencies from holding the consumer thread indefinitely, and committing offsets only after work completes or is durably handed off.

This lesson belongs to the **Performance** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, and mastering serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing to operate messaging pipelines reliably.

## 1. What does the consumer thread do?

The listener container owns the Kafka consumer and coordinates the lifecycle of polling, record dispatch, acknowledgment, and offset commits. For record listeners, the container invokes the listener for each record returned from poll. While the listener runs synchronously, the consumer thread generally does not return to poll for the next batch.

~~~mermaid
sequenceDiagram
    participant C as Consumer thread
    participant K as Kafka broker
    participant L as Listener
    C->>K: poll()
    K-->>C: records
    C->>L: invoke listener(record)
    Note over C,L: Consumer thread is busy processing
    L-->>C: return
    C->>K: next poll()
~~~

For batch listeners, a single invocation may process multiple records before the container returns to poll. Therefore, total batch processing time must also fit within the poll budget.

Never call `KafkaConsumer.poll()` directly from inside a listener. The consumer is managed by the container; manipulating the consumer directly from a listener can break Spring Kafka's lifecycle, thread ownership, and offset management.

## 2. What does blocking in a listener mean?

A blocking operation forces the consumer thread to wait before it can proceed. Common examples include:

- Synchronous HTTP calls to slow services or without a read timeout.
- Database queries waiting on a connection pool, locks, or slow queries.
- Calling `Future.get()`, `CompletableFuture.join()`, or `CountDownLatch.await()`.
- Using `Thread.sleep()` to wait for retries or dependencies.
- Waiting on semaphores, synchronized locks, or empty queues.
- Reading/writing large files or calling slow filesystem operations.
- Running prolonged CPU-bound work inside the listener.
- Manually retrying multiple times inside the listener.
- Synchronous logging to a congested appender or sink.

A call that looks fast in dev can block for seconds in production under network latency, connection pool contention, or downstream overload. Never judge performance solely by average times on a local machine.

## 3. Signs a listener is blocking

Several symptoms often appear together:

| Symptom | Possible cause |
| --- | --- |
| Consumer lag grows continuously | Listener processes slower than records arrive. |
| Poll interval climbs high | Consumer thread is held in listener or waiting on locks/I/O. |
| Unexpected rebalances | Consumer exceeded max.poll.interval or lost membership. |
| Low throughput despite idle CPU | Listener is waiting on I/O or external pools. |
| HTTP/DB connection pool exhausted | Listener holds connections too long or concurrency exceeds capacity. |
| p95/p99 latency spikes sharply | Tail latency in dependencies or lock contention. |
| Retries rise alongside timeouts | Listener is dealing with an unstable dependency. |
| Heap/queues grow | Work accumulates faster than it is processed. |

Consumer lag is only one signal; rising lag can stem from producer acceleration, too few partitions, or a slow consumer. Combine lag with listener duration, poll intervals, thread dumps, and downstream metrics to pinpoint the cause.

## 4. max.poll.interval.ms and liveness

`max.poll.interval.ms` limits the maximum gap between `poll()` calls while a consumer participates in a group. If slow listener processing keeps the consumer from polling in time, the consumer may be deemed stalled; partitions can be reassigned and the current processing attempt may lose the ability to commit offsets.

Distinguish clearly:

- `max.poll.interval.ms`: limits application progress between two poll calls.
- `session.timeout.ms`: limits how long the coordinator waits for consumer heartbeats before considering the member disconnected.
- Heartbeat: mechanism to maintain membership; in modern Kafka clients, heartbeats can run on a separate background thread.
- Listener duration: actual time the application takes to process a record or batch.

Heartbeats may continue while the listener is running, yet that does not bypass the max poll interval limit. If the listener holds the consumer thread too long, the consumer can still be evicted from the group for failing to call poll in time.

Do not raise `max.poll.interval.ms` to mask a listener that can block indefinitely. Measure processing time, set timeouts on dependencies, and adjust poll intervals only after understanding worst-case workloads.

## 5. Calculating a poll time budget

A consumer must finish work on received data before the next poll. For record listeners, if a poll returns multiple records and the container processes sequentially, total time can approach the sum of processing times across polled records plus overhead.

Illustrative example:

~~~text
max.poll.records = 100
p95 processing time per record = 80 ms

Approximate processing budget:
100 x 80 ms = 8 seconds
Plus overhead for serialization, dispatch, commit, and scheduling
~~~

Do not multiply p95 by record count and assume that is the worst case. Tail latencies across multiple records can compound; measure processing duration across entire polls/batches and check p99 under realistic load.

Related settings:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
~~~

These values are illustrative only. Choose `max.poll.records` according to record size, processing time, and memory; choose `max.poll.interval.ms` with a safety margin based on controlled maximum processing time. Reducing records per poll increases poll frequency while shortening per-batch processing time.

## 6. Set timeouts on all external I/O

A synchronous listener can remain safe if every external call has a deadline. Timeouts must cover both connection establishment and response waiting.

Example using Java HttpClient:

~~~java
@Bean
HttpClient downstreamHttpClient() {
    return HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
}

public String fetchOrderStatus(URI uri) throws Exception {
    HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(3))
        .GET()
        .build();

    HttpResponse<String> response =
        downstreamHttpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

    if (response.statusCode() >= 500) {
        throw new DownstreamUnavailableException(
            "Downstream returned " + response.statusCode()
        );
    }

    return response.body();
}
~~~

`send()` still blocks the consumer thread, yet wait time is bounded. A 2-second connect timeout and 3-second request timeout do not mean total duration is always exactly 3 seconds; account for DNS, TLS, connection reuse, client retries, and scheduling.

For databases, set query timeouts, transaction timeouts, and connection pool wait limits. For Redis or HTTP clients, configure connect, read/response, and acquisition timeouts. Avoid letting any single dependency have a timeout longer than the entire record processing budget.

## 7. Propagate deadlines end to end

If a listener calls multiple dependencies sequentially, each dependency should not be allowed its own full timeout independently. A record has an overall deadline; each step gets only the remaining time.

Example:

~~~java
Instant deadline = Instant.now().plusSeconds(5);

Duration remaining = Duration.between(
    Instant.now(),
    deadline
);

if (remaining.isNegative() || remaining.isZero()) {
    throw new ProcessingDeadlineExceededException();
}

downstreamClient.call(request, remaining);
~~~

In distributed systems, deadlines or request timeouts can be propagated via headers/correlation metadata per internal contract. Upon receiving a record, compute the remaining budget and pass it down to database/HTTP clients.

Deadlines prevent situations where a listener waits 3 seconds on service A and then another 3 seconds on service B despite a 4-second total SLA for the record. When the deadline expires, throw an appropriate exception so the error handler can retry or recover per policy.

## 8. Do not retry with sleep loops inside listeners

Avoid writing manual retries like this:

~~~java
@KafkaListener(topics = "orders")
public void listen(OrderEvent event) {
    for (int attempt = 0; attempt < 5; attempt++) {
        try {
            downstreamClient.process(event);
            return;
        }
        catch (TransientException exception) {
            Thread.sleep(1_000);
        }
    }

    throw new ProcessingFailedException();
}
~~~

Each sleep holds the consumer thread, reducing throughput and potentially pushing the consumer past the poll interval. When many records fail concurrently, all consumer threads can end up stuck in backoff sleeps.

Use Spring Kafka's retry mechanisms such as `DefaultErrorHandler` with bounded backoff for blocking retries, or retry topics for non-blocking retries when ordering and semantics allow. For transactional listeners, post-rollback retry paths typically use `AfterRollbackProcessor`.

Retries must classify exceptions. Permanent data errors should not be retried repeatedly; transient errors need backoff and attempt limits. Do not stack retries across the HTTP client, service layer, and Kafka handler without calculating total attempts and total deadline.

## 9. Cap connection pools and downstream concurrency

Increasing listener concurrency can proportionally increase concurrent requests to databases or HTTP services. If downstream only tolerates 20 concurrent requests while consumers emit 80 requests, connection pools and services can overload.

Enforce limits across layers:

- Kafka listener concurrency.
- HTTP connection pool and max connections.
- Database connection pool.
- Worker executor size.
- Per-dependency semaphore/bulkhead.
- Rate limits per service or tenant.

Example semaphore limiting concurrent calls:

~~~java
private final Semaphore downstreamSlots = new Semaphore(20);

public Result callDownstream(Request request) {
    boolean acquired = downstreamSlots.tryAcquire();

    if (!acquired) {
        throw new DownstreamSaturatedException();
    }

    try {
        return downstreamClient.call(request);
    }
    finally {
        downstreamSlots.release();
    }
}
~~~

`tryAcquire()` does not wait indefinitely. When no slot is free, the listener fails fast so the error handler or backpressure coordinator can act. If choosing a timed acquire, that timeout must fit inside the record's budget.

## 10. Tune concurrency within limits

Spring Kafka supports concurrency on the listener container factory. Each child container owns its own consumer; multiple consumers can process assigned partitions in parallel.

~~~java
factory.setConcurrency(4);
~~~

Concurrency can boost throughput when enough partitions exist and downstream has spare capacity. Yet excessive concurrency increases:

- Concurrent requests to databases/HTTP.
- Threads and memory footprint.
- Connection pool contention.
- Context switching and lock contention.
- In-flight records during rebalances or shutdown.

In a consumer group, useful active consumers are capped by assigned partitions. Raising concurrency above partition count does not parallelize a single partition in order; some child containers simply receive no partitions.

Raise concurrency only after measuring the bottleneck and verifying downstream capacity. If a listener blocks on a slow API, adding consumers may only overload the API further.

## 11. Separate CPU-bound and I/O-bound work

The two workloads require different treatments:

| Type | Examples | Optimization direction |
| --- | --- | --- |
| I/O-bound | HTTP, JDBC, Redis, file/network | Timeouts, connection pools, bounded async I/O, bulkheads |
| CPU-bound | Compression, encryption, computation, heavy parsing | CPU profiling, lower allocations, batching, cap workers to CPU |

If CPU is low while listener duration is high, look for I/O waits, locks, or queues. If CPU is high and thread dumps show listeners computing, adding async threads generally adds no CPU capacity; it may only increase context switching.

Do not run heavy CPU-bound tasks on the default common ForkJoinPool without load control. Use an appropriately sized executor with bounded queues and cap in-flight tasks.

## 12. Use a bounded executor when offloading

Offloading can help when a listener must trigger time-consuming work and the application has an appropriate acknowledgment strategy. The executor must be bounded; an unbounded queue can grow heap indefinitely when downstream slows down.

Configuration example:

~~~java
@Bean
ThreadPoolTaskExecutor orderExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("order-worker-");
    executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy()
    );
    return executor;
}
~~~

Queue capacity and pool size must match downstream throughput. When the queue is full, `AbortPolicy` rejects tasks; rejections must flow back to the listener/error handler or backpressure policy. Do not casually use `CallerRunsPolicy` because it can execute heavy tasks right on the consumer thread, blocking the listener again.

An executor does not make work durable. If the process stops, running tasks and in-memory queued tasks can be lost.

## 13. Offload asynchronously without acknowledging offsets too early

Dangerous pattern:

~~~java
@KafkaListener(topics = "orders", groupId = "orders")
public void listen(OrderEvent event) {
    orderExecutor.execute(() -> orderService.process(event));
}
~~~

The listener returns immediately after enqueueing. With typical automatic acknowledgment, the container can commit the offset before the worker finishes. If the process crashes after commit but before completion, Kafka will not redeliver the record and the in-RAM task is lost.

Only offload when one of these clear contracts is in place:

1. Use an asynchronous listener return type supported by your Spring Kafka version so the container knows when the task completes.
2. Use manual acknowledgment with appropriate async acknowledgment settings and acknowledge only after work finishes.
3. Persist work to durable storage inside a listener transaction before confirming offsets.
4. Forward the record to a work topic or durable queue and acknowledge after durable handoff succeeds.

Without such a contract, synchronous processing in the listener with bounded timeouts is usually simpler and safer.

## 14. Asynchronous listener return types

Recent Spring Kafka versions support certain asynchronous return types such as `CompletableFuture` and `Mono`. When using this feature, the container can await completion before acknowledging records per that version's async listener semantics.

Illustrative example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders",
    containerFactory = "asyncOrderListenerFactory"
)
public CompletableFuture<Void> listen(OrderEvent event) {
    return CompletableFuture.runAsync(
        () -> orderService.process(event),
        orderExecutor
    );
}
~~~

If work succeeds normally, the future completes normally. If the worker throws an exception, the future completes exceptionally so the container handles it through the supported error-handling path.

Before using, check your Spring Kafka version and its documentation: supported return types, whether AckMode is adjusted automatically or must be configured, async acknowledgment, retry behavior, and handling future completion after a rebalance. Do not assume all Spring Kafka versions support the same return types.

The executor must still be bounded with a rejection policy. Do not detach the future from the listener; if the method returns a future that completes before the work actually finishes, offsets can still be committed prematurely.

## 15. Manual acknowledgment and async acknowledgment

When using manual acknowledgment, the listener or worker must acknowledge only after work completes per contract. With async/out-of-order processing, check `asyncAcks` and the container's `AckMode`.

Conceptual example:

~~~java
@KafkaListener(
    topics = "orders",
    containerFactory = "manualAckOrderFactory"
)
public void listen(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderExecutor.execute(() -> {
        try {
            orderService.process(event);
            acknowledgment.acknowledge();
        }
        catch (Exception exception) {
            // Route error to the appropriate retry/recovery mechanism.
            failureHandler.handle(event, exception);
        }
    });
}
~~~

This is only a flow outline. Do not copy directly without configuring manual AckMode, async acknowledgment, and version-appropriate error handling. Acknowledgments can have ordering and consumer-thread constraints; calling from a worker thread must be supported by the container configuration.

When async acknowledgment is enabled, the container may hold out-of-order acknowledged offsets and pause the consumer until missing earlier offsets are acknowledged. If a task never completes, the partition can stay stalled. Every task requires timeouts, cancellation, and error handling.

## 16. Durable handoff for long-running work

If work takes several minutes or must survive restarts, do not hold the consumer thread or store tasks only in RAM. Transfer responsibility to a durable mechanism:

- Write a job to a database in a transaction, then have another worker read the job.
- Write an outbox row and relay it to a work topic.
- Publish a command to a separate topic and acknowledge input after broker handoff confirmation.
- Use a durable work queue if your architecture includes one.

Example model:

~~~mermaid
flowchart TD
    A[Input topic] --> B[Listener]
    B --> C[Persist job or outbox]
    C --> D[Commit input offset]
    C --> E[Worker reads durable job]
    E --> F[Execute long-running work]
    F --> G[Mark completed]
~~~

If persisting the database job and committing the Kafka offset are not in the same transaction, handle failure windows and idempotency. You can use database transaction synchronization or the inbox/outbox pattern depending on data direction and required guarantees.

Durable handoff keeps listeners short and stable, but adds storage components, worker lifecycles, retries, and job state. Job designs need a unique event ID to prevent duplicates when input is redelivered.

## 17. Pause/resume for backpressure

When a bounded queue or downstream worker pool nears capacity, you can ask the listener container to pause to throttle incoming records. When the queue drops below a low watermark and any other pause reasons clear, the container resumes.

Example logic:

~~~java
if (queueDepth >= HIGH_WATERMARK) {
    container.pause();
}
else if (queueDepth <= LOW_WATERMARK) {
    container.resume();
}
~~~

Use distinct high/low watermarks to avoid rapid pause/resume oscillation. Account for already-polled records and in-flight tasks because pausing does not revoke already-received records. The container continues polling to maintain consumer liveness; paused partitions deliver no new records to the listener.

Pause/resume does not replace proper acknowledgment. If a listener commits offsets immediately upon RAM enqueueing, pausing only slows new arrivals rather than protecting queued tasks from loss on process restart.

## 18. Ordering and idempotency with increased asynchrony

When listeners process asynchronously, completion order can differ from poll order. For instance, `OrderUpdated(version=2)` could finish before `OrderUpdated(version=1)` if two tasks execute concurrently.

If per-key or per-aggregate ordering is a business requirement:

- Keep processing sequential per partition or per key.
- Use keyed executors/partitioned worker queues.
- Include sequence/version numbers in events and reject stale updates.
- Do not ack offsets past an earlier record unless the container supports appropriate async ack semantics.
- Use idempotency keys to handle redeliveries.

Kafka only guarantees record ordering within a partition. Offloading to a worker pool does not automatically preserve business completion order. Test cases where an earlier task finishes slower than a later task explicitly.

## 19. Retries, circuit breakers, and timeouts

A slow downstream causes blocking, yet continuous retries can amplify load further. Combine timeouts, circuit breakers, bulkheads, and retry policies:

- Timeouts bound each call's duration.
- Circuit breakers stop calling persistently failing dependencies.
- Bulkheads cap concurrent requests.
- Retries use backoff and attempt caps.
- Backpressure pauses listeners when downstream capacity is exhausted.

Never retry inside a listener with sleep loops. Let exceptions reach the error handler or route to retry topics per policy. When a circuit breaker is open, fail fast to retry/recover; do not hold the consumer thread sleeping until half-open.

## 20. Transactions and side effects when offloading

Kafka transaction contexts and standard Spring database transactions are tied to specific threads or resource contexts. When offloading work to an executor, do not assume the listener's transaction propagates to worker threads.

Risks include:

- The container's Kafka transaction may finish when the listener returns while the worker is still running.
- A database transaction on the listener thread does not wrap SQL statements executed on the worker.
- Offsets may commit before the worker completes.
- Workers may keep running after a rebalance or shutdown.
- Retries may reprocess the same event while an earlier task is still active.

If transactions are required, keep operations inside an appropriate transaction boundary or use durable handoff. Workers should be idempotent by event ID and verify job state before producing side effects.

## 21. Shutdown, rebalance, and cancellation

During application shutdown or consumer rebalances, async tasks may still be running. If a task finishes after its partition has moved to another consumer, stale acknowledgments may be invalid or offset commits may fail.

Establish a policy:

- Stop accepting new tasks when the container stops.
- Wait for running workers up to a bounded grace period.
- Cancel unstarted tasks where possible.
- Never ack if work has not met its durability contract.
- Ensure redelivery can occur safely and workers are idempotent.
- Persist running task state for post-restart recovery if work is critical.

Do not stall shutdown indefinitely waiting on downstream. Graceful shutdown must have a deadline; past the deadline, let unacknowledged records be redelivered by Kafka.

## 22. Measuring and profiling listeners

Track metrics by listener ID, topic, and consumer group:

- Listener processing duration p50/p95/p99.
- Poll interval and max poll interval breach count.
- Consumer lag per partition.
- Records per poll and batch size.
- Timeout, retry, recovery, and DLT counts.
- HTTP latency, DB query latency, and connection pool wait time.
- Executor active threads, queue depth, and rejected tasks.
- Pause duration, in-flight task count, and async completion latency.

To find blocking threads, take thread dumps and inspect consumer thread stacks. Frames like socket reads, JDBC waits, `Future.get`, `LockSupport.park`, `Thread.sleep`, or monitor contention usually point directly to the wait point.

Use tracing/correlation IDs to link listener duration to downstream calls. Do not look only at CPU usage; low CPU paired with high consumer lag is a strong signal to check I/O waits or pool exhaustion.

## 23. Testing non-blocking listeners and async processing

Tests should cover success, timeouts, full queues, and lifecycle events:

1. Fast downstream: listener completes and offsets advance per policy.
2. Slow downstream: timeout triggers within the defined budget.
3. Unresponsive downstream: consumer is not held indefinitely.
4. Full worker executor: tasks are rejected and records follow the error-handling policy.
5. Async task fails: exception reaches the container/error handler rather than being swallowed.
6. Async task completes: offsets are confirmed only after completion or durable handoff.
7. Process restart after enqueueing: verify no task loss per durability contract.
8. Rebalance while tasks run: verify tasks/acks are handled safely.
9. Multiple records with same key: ordering and idempotency behave as required.
10. Queue hits high watermark: container pauses; resumes once below low watermark.
11. Increased concurrency: downstream connection pool stays within capacity.
12. Large batches: batch processing time fits within the poll budget.

Use Testcontainers or Embedded Kafka to verify offsets and redeliveries; use a latency-controllable mock server to simulate downstream. Use latches/Awaitility with timeouts rather than fixed sleeps. Tests should assert committed offsets and output topics, not merely method invocations.

## 24. Common mistakes

| Practice | Risk | How to fix |
| --- | --- | --- |
| Synchronous HTTP without timeout | Consumer thread can wait indefinitely | Set connect/response timeouts and overall deadline |
| Using `Thread.sleep` for retries | Holds consumer thread during backoff | Use error handlers/retry topics |
| Calling `Future.get` in listener | Turns async task into blocking wait | Use async listener return support or bounded synchronous call |
| Enqueueing to RAM then returning | Offsets may commit before worker processes | Proper async ack or durable handoff |
| Using unbounded queues | Heap grows when downstream slows | Bounded queues and backpressure |
| Raising concurrency without load measurement | Overloads downstream/pools | Cap concurrency to partitions and capacity |
| Raising max.poll.interval to hide bugs | Only delays rebalances | Reduce processing time and enforce timeouts |
| Running CPU-heavy work on consumer thread | Slow polls despite no I/O | Profile and use bounded workers if ack semantics permit |
| Swallowing exceptions in listener | Offsets may commit despite business failure | Rethrow exceptions or handle recovery explicitly |
| Offloading to executor while relying on old tx context | Side effects and offsets lose shared boundary | Durable handoff, idempotency, and proper transactions |

## 25. Non-blocking checklist

Before taking a listener to production, confirm:

1. Measured listener duration p95/p99 and batch processing times.
2. Every HTTP/DB/Redis call has timeouts.
3. Each record has an overall deadline.
4. No `Thread.sleep`, `Future.get`, or unbounded lock waits.
5. Retries live in appropriate error handlers/retry mechanisms.
6. `max.poll.records` and `max.poll.interval.ms` fit the processing budget.
7. Listener concurrency does not exceed downstream capacity.
8. Connection pools, worker pools, and semaphores are bounded.
9. Executors have bounded queues and rejection policies.
10. Offloading never commits offsets before completion or durable handoff.
11. Async listener return types match your Spring Kafka version.
12. Manual/async acknowledgments are tested under exact container config.
13. Per-partition/per-key ordering is preserved or guarded via sequence/version.
14. External side effects have idempotency and clear transaction boundaries.
15. Pause/resume uses high/low watermarks and accounts for in-flight records.
16. Shutdown/rebalance has grace periods, cancellation, and redelivery policies.
17. Metrics cover poll intervals, listener durations, queue depth, timeouts, and rejected tasks.
18. Integration tests cover timeouts, async failures, restarts, and offsets.

Avoid blocking in listeners by bounding every operation's duration, controlling concurrency, and protecting the poll budget. Offloading to workers is only safe when the container knows when work completes or records are durably handed off; enqueueing in RAM and returning can advance offsets before business work finishes. Combining timeouts, bounded executors, proper acknowledgments, idempotency, and backpressure keeps consumers progressing without building uncontrolled backlogs.


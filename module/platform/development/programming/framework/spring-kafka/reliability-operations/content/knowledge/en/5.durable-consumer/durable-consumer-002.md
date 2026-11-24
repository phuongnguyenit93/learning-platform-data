# Poll Loop and the max.poll.interval.ms Limit

A Kafka consumer must continuously call `poll()` to receive new records and participate in consumer group coordination. In a Spring Kafka application, the listener container manages this loop: the container calls `poll()`, dispatches records to the listener for processing, handles acknowledgments and offset commits as configured, and continues polling. If processing time prevents the consumer from calling `poll()` frequently enough, Kafka may consider the consumer no longer making progress, remove it from the group, and reassign its partitions.

The `max.poll.interval.ms` property sets the upper limit on the maximum time between two consecutive `poll()` calls. This is a critical limit when operating consumers with long-running work, large batches, retries with backoff, or dependencies on external systems. Understanding this limit properly helps avoid unintended rebalances, duplicate processing, and consumers repeatedly losing and regaining partitions.

## 1. How Does the Poll Loop Work?

A Kafka consumer does not receive records by waiting for the broker to push individual messages to the application. The application actively calls `poll()` to retrieve ready records. The basic loop looks like this:

```text
consumer thread
      |
      v
    poll()
      |
      v
Receive up to N records from assigned partitions
      |
      v
Dispatch records to the listener for processing
      |
      v
Acknowledgment / commit as configured
      |
      v
    Next poll()
```

In Spring Kafka, `KafkaMessageListenerContainer` runs the consumer on a container thread. That thread calls the Kafka consumer's `poll()` and invokes the corresponding `@KafkaListener` method. With `ConcurrentMessageListenerContainer`, each child container has its own consumer and loop; the `concurrency` property determines how many child consumer containers are created.

For example, a record listener receives one record at a time:

```java
@KafkaListener(topics = "payments", groupId = "payment-worker")
public void handle(PaymentRequested event) {
    paymentService.process(event);
}
```

The listener is invoked for each record. However, the Kafka consumer may have returned multiple records in a single `poll()`. The container may have to invoke the listener multiple times to process the entire batch of records received before returning to the next `poll()`. Therefore, even if each `handle()` call is fairly fast, the total processing time for all records from one poll can still be long.

With a batch listener, the container passes the entire batch to a single listener invocation:

```java
@KafkaListener(topics = "payments", groupId = "payment-worker")
public void handleBatch(List<PaymentRequested> events) {
    paymentService.processBatch(events);
}
```

A batch listener can reduce method invocation overhead and group I/O operations, but batch processing time must also fit within the time budget between two polls. Using `AckMode.RECORD` or `AckMode.BATCH` affects when offsets are committed; it does not remove the requirement that the consumer must keep calling `poll()` on time.

## 2. What Does max.poll.interval.ms Limit?

`max.poll.interval.ms` is the maximum duration a Kafka consumer is allowed to go without calling `poll()` between two consecutive polls. When this duration exceeds the threshold, the consumer is considered non-compliant with the group's progress requirement. Kafka can evict the consumer from the group and trigger a rebalance so partitions are assigned to another consumer.

This property measures the time between `poll()` invocations, not the maximum duration of a single record and not how long `poll()` is allowed to wait for the broker to return data. The time budget must include all work occurring after one poll returns and before the next poll, such as:

- Processing all records received from the previous poll.
- Calling databases, HTTP services, payment gateways, or external services.
- Running business logic, serialization/deserialization, and data processing.
- Synchronous retries or backoff executed on the consumer thread.
- Offset commits, callbacks, and other coordination work.
- Pauses caused by garbage collection, CPU contention, or blocked threads.

You can approximate the budget as follows:

```text
time between two polls
  = record/batch processing time
  + synchronous retry and wait time
  + commit time and auxiliary work
  + runtime/OS delay

Operational condition:
  time between two polls < max.poll.interval.ms
```

The Kafka Java consumer typically has a default `max.poll.interval.ms` of 300,000 ms (5 minutes). The actual runtime value depends on the client version and applied configuration; inspect the runtime configuration rather than assuming all environments keep the default.

### Example: A Batch Causing the Poll Loop to Miss Its Deadline

Suppose a consumer receives 80 records in one poll. The listener processes sequentially, taking about 450 ms per record:

```text
80 records × 450 ms = 36,000 ms = 36 seconds
```

If `max.poll.interval.ms` is set to 30,000 ms, the consumer can exceed the limit before finishing the batch and calling the next `poll()`. With commits, external service calls, or a GC pause, the actual elapsed time is even longer.

The key point is that the total duration of the entire poll processing cycle determines the risk. One record taking 2 seconds may be safe under a 5-minute limit, but 200 consecutive records taking 2 seconds each can take over 6 minutes and cause the poll loop to time out.

## 3. Distinguishing max.poll.interval.ms from Heartbeat and Session Timeout

Three properties are often confused because all relate to whether a consumer stays in the group:

| Property | Role | Question It Answers |
|---|---|---|
| `max.poll.interval.ms` | Limits the time between two `poll()` calls; monitors progress of the consuming application. | Is the consumer still fetching data and making processing progress on pace? |
| `session.timeout.ms` | Time the coordinator waits for a valid heartbeat before considering the consumer disconnected. | Is the consumer still maintaining contact with the group coordinator? |
| `heartbeat.interval.ms` | Interval between heartbeats sent by the consumer under the active group protocol. | How frequently does the consumer send membership keep-alive signals? |

In modern Kafka consumers, heartbeats can be sent by a background thread while the application thread is processing records. Therefore, healthy heartbeats do not mean the consumer is allowed to stop calling `poll()` indefinitely. `max.poll.interval.ms` protects application-level processing progress, whereas session timeout primarily detects loss of connectivity.

Increasing `session.timeout.ms` does not directly solve a listener taking too long between polls. Likewise, lowering `heartbeat.interval.ms` does not make a long batch finish faster. When diagnosing a rebalance, look for the exact root cause: missed heartbeats, poll interval exceeded, network errors, consumer shutdown, or another membership change.

## 4. max.poll.records Controls Work Per Poll

`max.poll.records` caps the maximum number of records returned to the application by a single `poll()` call. This is one of the most important tuning levers when batch processing time affects the poll interval.

Example:

```yaml
spring:
  kafka:
    consumer:
      max-poll-records: 50
      properties:
        "[max.poll.interval.ms]": 180000
```

In this example, each poll returns at most 50 records and the time between two polls must not exceed 180 seconds. Property names under `consumer.properties` are passed verbatim to the Kafka client; the bracket syntax preserves dotted keys during Spring Boot configuration binding.

Lowering `max.poll.records` reduces the amount of work that can accumulate in a single poll cycle. This typically helps the consumer return to polling sooner and bounds the worst-case processing time of a batch. In return, the application may execute more poll cycles, increasing coordination overhead or reducing the efficiency of operations that benefit from batching.

`max.poll.records` does not limit how many records the broker stores in a partition and does not limit the total bytes the consumer fetches internally. It caps the number of records returned in a single `poll()` invocation. Therefore, do not treat it as a topic capacity limit or a record retention mechanism.

### Estimating Configuration from Processing Time

For a sequentially processing listener, you can start with this estimate:

```text
T_batch ≈ N × T_record
T_cycle ≈ T_batch + T_commit + T_overhead
```

Where:

- `N` is the maximum actual number of records received in a poll, not exceeding `max.poll.records`.
- `T_record` is the processing time of one record.
- `T_commit` is the time spent on commits and acknowledgments.
- `T_overhead` includes retries, callbacks, GC pauses, and other waits.

Suppose one record usually takes 300 ms, a poll receives 100 records, and commits plus auxiliary work take about 5 seconds:

```text
T_batch ≈ 100 × 300 ms = 30 seconds
T_cycle ≈ 30 + 5 = 35 seconds
```

Do not set `max.poll.interval.ms` right at 35 seconds. Actual durations vary with load, database latency, payload size, and anomalies. Measure processing times under representative load, inspect high percentiles, and leave sufficient headroom. If processing times have a long tail, reduce records per poll or restructure the work rather than relying solely on averages.

## 5. Configuring the Consumer in Spring Kafka

Spring Boot lets you configure Kafka consumer properties via `spring.kafka.consumer`. The following example caps records per poll, disables Kafka client auto-commit, and sets the poll interval to three minutes:

```yaml
spring:
  kafka:
    consumer:
      group-id: payment-worker
      enable-auto-commit: false
      max-poll-records: 50
      properties:
        "[max.poll.interval.ms]": 180000
    listener:
      ack-mode: record
      concurrency: 3
```

`enable-auto-commit: false` lets the Spring Kafka listener container coordinate acknowledgments and offset commits according to `AckMode`. `concurrency: 3` creates up to three child consumer containers for this listener endpoint. Each consumer has its own poll loop and `max.poll.interval.ms` budget.

Concurrency does not split one partition across multiple consumers simultaneously in the same consumer group. If a topic has only two partitions, raising concurrency to six does not create six parallel processing threads for those two partitions; some consumers will receive no partitions. If only one partition carries heavy load, increasing concurrency will not automatically split that partition's load across multiple consumers either. When tuning, consider partition count, key distribution, and business-level parallelism.

With Java configuration creating `ConsumerFactory` directly, you can set properties using Kafka client constants:

```java
Map<String, Object> props = new HashMap<>();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "payment-worker");
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 50);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 180_000);

ConsumerFactory<String, PaymentRequested> factory =
        new DefaultKafkaConsumerFactory<>(props);
```

When using Java configuration, ensure properties are set on the exact `ConsumerFactory` that the listener container actually uses. Settings declared in YAML that are overridden by a custom factory will not produce the expected behavior.

## 6. What Happens When a Consumer Exceeds the Poll Interval?

Suppose consumer A owns partition `payments-2`. Consumer A calls `poll()`, receives a batch of records, and blocks while calling a payment service. Processing time exceeds `max.poll.interval.ms`.

A typical sequence of events occurs:

1. Consumer A fails to call `poll()` within the allowed interval.
2. Kafka considers consumer A no longer meeting the group's progress requirement.
3. Consumer A leaves the group or is deemed no longer eligible to retain membership under the group protocol.
4. The group performs a rebalance and partition `payments-2` may be assigned to consumer B.
5. Consumer B resumes reading from the group's current committed offset.

If A already executed the business side effect without committing the corresponding offset, B may read that record again. For instance, A sent a payment request to an external system but did not commit the offset; after the rebalance, B receives the record again and could submit the request a second time. This is a source of duplicate processing when a consumer exceeds the poll interval.

The exact outcome depends on commit timing, acknowledgment mode, transactions, and rebalance handling. Never assume all records in the poll were committed or that all will be re-read. Design listeners to be idempotent: reprocessing the same event ID must not produce duplicate business effects. You can use unique keys, an inbox table, database unique constraints, or target APIs supporting idempotency keys.

Rebalances also carry operational cost: another consumer takes over partitions and may have to reload state, caches, or connections; during handoff, processing latency increases. If the poll interval is exceeded repeatedly, the system can fall into a loop of partial processing, membership loss, rebalancing, and reprocessing.

## 7. Retries and Backoff Can Slow Down the Poll Loop

A listener may throw an exception when the database is temporarily unavailable or an external service returns an error. The Spring Kafka error handler can retry synchronously with backoff. If retries and wait periods happen on the consumer thread, they increase the elapsed time from one poll to the next.

For example, a record requiring three attempts, each taking 4 seconds with 10 seconds between attempts:

```text
3 processing attempts × 4 seconds = 12 seconds
2 backoff intervals × 10 seconds = 20 seconds
Total time per record ≈ 32 seconds
```

If a poll contains multiple failing records or extended retries, the total time can exceed the limit. Include retry time in the poll loop budget, not only successful processing time.

For long backoff intervals, Spring Kafka provides `ContainerPausingBackOffHandler` in supported versions. This mechanism pauses the container during the wait and continues polling while paused to keep the consumer active with the group. Actual pause duration may be rounded to `pollTimeout`, so understand your container configuration and running version.

Another option is offloading long retries to a retry topic or a separate processing flow. In that case, failed records are routed to the retry stream per the designed policy; the main consumer can move on to other records. Clearly define event ordering, retry counts, retry deadlines, dead-letter topics, and how to prevent duplicate processing between the main and retry flows.

## 8. Handling Long Work While Maintaining Polling

If a listener routinely takes longer per record than the poll budget allows, simply raising `max.poll.interval.ms` can mask the problem and delay detecting a hung consumer. Several design approaches should be considered:

**Reduce synchronous processing time.** Optimize database queries, set explicit timeouts on HTTP clients, batch I/O operations, or reduce payload size. The goal is to bring processing time within predictable bounds.

**Reduce records per poll.** Tune `max.poll.records` so the container processes fewer records before calling the next poll. This helps when total batch duration is the main culprit.

**Pause the container when load throttling is needed.** Spring Kafka supports pausing and resuming listener containers or partitions. When a consumer is paused, the container continues calling `poll()` according to its mechanics without fetching new records to deliver to the listener from paused partitions. This is useful for applying backpressure while maintaining the poll heartbeat. Always use the listener container API instead of calling `KafkaConsumer.pause()` directly from an arbitrary thread.

**Use asynchronous processing with managed acknowledgments.** Offloading work to an executor and returning immediately from the listener lets the container keep polling while background work finishes. However, acknowledgments must remain tied to actual processing outcomes. Committing offsets before work completes can lose business operations on failure. Out-of-order completions require configuring and understanding the async acknowledgment mechanism of your Spring Kafka version. Never use the same `KafkaConsumer` from background threads because Kafka consumers are not thread-safe.

**Split long-running work into a separate workflow.** If a record triggers work lasting tens of minutes or hours, consider durably recording the request and handing the long-running work to a dedicated worker or workflow. The Kafka consumer can acknowledge once intake is safely persisted, while completion state of the long work is tracked separately.

## 9. Configuration Mistakes and Diagnostics

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Consumer rebalances frequently under higher load | Batch processing time exceeds `max.poll.interval.ms`. | Measure time from poll start to next poll; inspect records per poll and listener duration. |
| Consumer loses partitions when an external service slows down | Listener blocks in synchronous calls or retries. | Check HTTP/database timeouts, backoff, and tail latency. |
| Lag grows even though consumer heartbeats are healthy | Consumer has not finished work and is not polling often enough, or throughput is below producer rate. | Measure poll cadence, processing time, records per second, and per-partition lag. |
| Duplicate business operations appear after a rebalance | Record produced external side effects without committing offset before partition reassignment. | Correlate event IDs, offsets, commit logs, and idempotency mechanisms. |
| Increasing concurrency does not increase throughput | Too few partitions, hot partition, or bottleneck in database/target service. | Inspect assignment, key distribution, CPU usage, and I/O time. |
| Poll interval set very high yet consumer stays slow | Raised slow-consumer detection limit without fixing processing time or bottlenecks. | Review throughput, lag, timeouts, and actual processing duration. |

When seeing commit errors or poll timeout logs, read all logs around the rebalance timestamp. A commit error may be a consequence of the group membership already having changed; it is not necessarily the root cause. Correlate listener start time, listener completion time, next poll time, commit time, and partition revocation time.

## 10. Monitoring the Poll Loop in Operations

Monitoring consumer lag alone is not enough. Lag shows how far committed progress trails the end of the log, but it does not pinpoint why the consumer is slow. Combine the following signals:

- Listener processing time per record and per batch, especially high percentiles.
- Time between two polls or age of the last poll if provided by your monitoring stack.
- Actual records received per poll and batch size distribution.
- Offset commit latency and commit failure count.
- Rebalance count, revoked/assigned partitions, and handoff duration.
- Retry count, total backoff duration, and records sent to dead-letter topics.
- Consumer lag per partition and lag growth/drain rate.
- Database/HTTP call latency, CPU utilization, and GC pause duration.

When investigating, log `topic`, `partition`, `offset`, event ID, and processing duration. These fields link a specific record to business logs and consumer group progress. Avoid logging full sensitive payloads just for diagnostics; metadata is usually sufficient for tracing.

## 11. Practical Tuning Procedure

When a consumer experiences rebalances due to poll timeouts, proceed in the following sequence:

1. Confirm logs show the consumer actually exceeded `max.poll.interval.ms`, rather than losing connectivity or rebalancing due to another member change.
2. Measure processing time from when `poll()` returns records to the next `poll()` under representative and peak load.
3. Identify whether time is dominated by the listener, batch size, retry/backoff, database, HTTP, or GC.
4. If the batch is too large, reduce `max.poll.records` and re-measure throughput and poll cadence.
5. If synchronous processing is too slow, optimize I/O, enforce timeouts, apply controlled pause/resume, or adopt an appropriate async/retry architecture.
6. Only increase `max.poll.interval.ms` when long processing time is intentional, bounded, and measured. Leave margin for peak load and transient incidents.
7. Verify idempotency and safe record reprocessing after rebalances; acknowledge offsets only after guaranteed work completes.
8. Monitor lag, rebalances, and listener duration after changes to confirm system stability.

`max.poll.interval.ms` is the time bound for a consumer to prove its processing loop continues making progress. Stable operations require coordinating batch size, processing duration, retries, acknowledgment strategy, and dependent service capacity. When each consumer returns to `poll()` on time and business operations tolerate redelivery, the consumer group experiences fewer unintended rebalances and recovers progress reliably after failures.

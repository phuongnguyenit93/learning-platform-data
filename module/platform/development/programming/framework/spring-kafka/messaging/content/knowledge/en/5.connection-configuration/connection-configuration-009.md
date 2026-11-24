# max.poll.interval.ms and processing time

A Kafka consumer can remain connected to the broker yet still be removed from the consumer group if the application takes too long to process a batch of records. This situation frequently occurs when a listener calls external services, writes data slowly, processes a large batch sequentially, or waits on retries with long backoffs. Kafka uses `max.poll.interval.ms` to bound the time between two consecutive consumer `poll()` calls; this setting helps detect consumers that are no longer making progress in the consumption loop.

In Spring Kafka, `KafkaMessageListenerContainer` manages the poll loop and invokes the `@KafkaListener` method. Therefore, listener execution time, the number of records returned in one poll, and how retries behave all affect the duration before the next poll. Understanding this relationship helps choose suitable configurations, avoid unintended rebalances, and reduce record reprocessing.

## 1. The poll lifecycle and meaning of max.poll.interval.ms

A consumer group needs to know which consumer is responsible for processing which partitions. For consumers using group management, the application must continue calling `poll()` to prove it is still making progress. A simplified processing cycle can be pictured as follows:

```text
poll()
  |
  +-- receive at most max.poll.records records
  |
  +-- Spring Kafka invokes listener for the records
  |
  +-- business processing / retries / offset acknowledgment
  |
next poll()
```

`max.poll.interval.ms` is the maximum allowed duration between two calls to `poll()`. If this interval exceeds the limit, the consumer may be deemed unable to keep up, leave the group, and trigger a rebalance. The Kafka consumer default is typically `300000` ms (5 minutes); verify the effective configuration of the running Kafka client version rather than assuming every environment keeps the default.

The key point is that this timer is tied to `poll()` progress, not just the processing time of a single record. When a single poll returns many records, the listener may have to process all of those records before the container calls the next poll. Thus, a listener that handles each individual record fairly quickly can still exceed the limit if the batch is too large.

## 2. Distinguishing commonly confused settings

| Setting | Role | Main impact |
|---|---|---|
| `max.poll.interval.ms` | Bounds the duration between two `poll()` calls | Consumer may leave the group if it fails to poll in time |
| `max.poll.records` | Maximum number of records returned by one `poll()` call | Determines the workload the listener must process in one cycle |
| `session.timeout.ms` | How long the broker waits for heartbeats before considering the consumer disconnected | Detects unreachable consumers |
| `heartbeat.interval.ms` | Interval at which the client sends heartbeats | Coordinates heartbeats within the consumer group |
| Spring Kafka `pollTimeout` | How long a single poll waits for data when no records are ready | Controls the container's data wait timeout |

`session.timeout.ms` and `heartbeat.interval.ms` relate to heartbeats and disconnect detection. `max.poll.interval.ms` tracks application-level processing progress. A consumer can keep sending heartbeats while the listener is running, but that does not substitute for calling `poll()` on time. When `max.poll.interval.ms` is exceeded, the client can leave the group even though the network connection has not dropped.

`max.poll.records` limits the number of records returned to the application in one poll. It is not a byte-size limit and does not replace fetch configurations such as `fetch.max.bytes` or `max.partition.fetch.bytes`. Reducing `max.poll.records` typically lowers processing time per cycle, at the cost of more frequent polls and reduced batching efficiency.

With static membership, meaning a consumer configured with `group.instance.id`, exceeding the poll limit may prevent partitions from being reassigned immediately; the broker may wait until `session.timeout.ms` expires. Static membership can reduce some rebalances during brief instance restarts, but it does not solve the root cause of a listener taking too long to process.

## 3. Calculating time for a processing cycle

When processing sequentially, you can estimate a cycle's duration as the sum of record processing times plus other work occurring between two polls:

\[
T_{cycle} \approx \sum_{i=1}^{N} T_{handler,i} + T_{commit} + T_{retry} + T_{overhead}
\]

Where:

- `N` is the actual number of records received in the poll, not exceeding `max.poll.records`.
- `T_handler,i` is the time the listener spends processing the `i`-th record, including synchronous DB or HTTP calls.
- `T_commit` is the offset acknowledgment time if commits happen within that cycle.
- `T_retry` is the total wait and retry time under the active retry approach.
- `T_overhead` includes scheduling, garbage collection, logging, and other delays.

This is an estimation model for time budgeting, not Kafka's exact internal measurement formula. When parallel processing is involved, measure actual wall-clock time from when poll returns until the consumer can poll again; do not extrapolate solely from the average duration of a single task.

For example, a consumer receives 120 records and each record takes about 700 ms to process sequentially. The listener portion alone requires about 84 seconds. If commits, retries, and other delays add 15 seconds, the cycle is around 99 seconds. With `max.poll.interval.ms=120000`, the safety margin is only 21 seconds. One slow external service call or a burst of retries can push the cycle over the threshold.

If `max.poll.records` is reduced to 40, the sequential processing under the assumptions above drops to about 28 seconds per cycle. In return, the consumer polls more often and may need more iterations to consume the same data volume. Actual numbers must be chosen from the processing time distribution, not just the mean.

The configuration rule of thumb is to keep cycle duration significantly below `max.poll.interval.ms`, leaving headroom for load spikes, dependency latency, retries, and garbage collection. Use p95/p99 measurements or high-load tests rather than relying only on the happy path.

## 4. Configuration in Spring Boot

You can set the time limit and record limit per poll in `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      group-id: billing-worker
      enable-auto-commit: false
      max-poll-records: 40
      properties:
        "[max.poll.interval.ms]": "180000"
```

In this example, each poll returns at most 40 records and the consumer must call the next poll within 180 seconds. `enable-auto-commit: false` lets the Spring Kafka container manage offset acknowledgment per the configured `AckMode`. This is a standard Spring Kafka setup; maintain consistency between commit timing and when business logic has succeeded.

When configuring directly in Java, pass the properties to `ConsumerFactory`:

```java
Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "billing-worker");
consumerProps.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
consumerProps.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG, 40);
consumerProps.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 180_000);

ConsumerFactory<String, OrderCreated> consumerFactory =
        new DefaultKafkaConsumerFactory<>(consumerProps, keyDeserializer, valueDeserializer);
```

Imports and deserializers in this example are omitted to focus on the two properties being tuned. Avoid declaring the same property in multiple places with conflicting values; verify the final effective configuration used to create the consumer.

## 5. Impact on @KafkaListener

Example of a record listener processing orders:

```java
@Component
public class BillingListener {

    private final BillingService billingService;

    public BillingListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(topics = "orders", groupId = "billing-worker")
    public void onMessage(OrderCreated event) {
        billingService.handle(event);
    }
}
```

Even though `onMessage` receives only one `OrderCreated` per invocation, the container may still be processing multiple records returned from a single poll. If the container invokes the listener sequentially for 40 records, the time of all 40 invocations accumulates before the next poll occurs. Therefore, evaluate the total time of the entire cycle, not just a single call to `billingService.handle()`.

With a batch listener, the entire batch is usually passed into a single method invocation:

```java
@KafkaListener(topics = "orders", groupId = "billing-worker")
public void onBatch(List<OrderCreated> events) {
    billingService.handleBatch(events);
}
```

A batch listener can leverage bulk DB writes, yet a large batch also lengthens the time before the next poll. Set `max.poll.records` according to the batch processing duration and the downstream system's load tolerance.

`AckMode` determines how the container acknowledges offsets. For instance, `BATCH` normally acknowledges offsets after finishing the records from a poll; `RECORD` acknowledges after each record for a record listener. Choose an `AckMode` matching delivery requirements, but do not treat per-record committing as a substitute for managing poll time: the listener still must finish the current work for the container to continue the loop.

## 6. What happens when processing exceeds the limit?

Suppose a consumer receives records from partition `orders-2`, and then the listener blocks for 4 minutes on an HTTP call. If `max.poll.interval.ms` is only 3 minutes, the consumer misses the next poll deadline. Kafka may remove the consumer from the group and initiate a rebalance to assign the partition to another consumer.

When the partition is handed to a new consumer, uncommitted records can be re-read starting from the last confirmed offset. Thus, a record may have already produced effects in a DB or external system yet still be redelivered by Kafka. This is why consumers should implement idempotent processing, such as using a unique `eventId` to prevent recording a business action twice.

Increasing `max.poll.interval.ms` can reduce rebalances during long processing, but setting it too high slows down detecting a stuck consumer. Moreover, raising the limit does not make the listener faster, does not reduce consumer lag, and cannot fix a downstream service call that hangs indefinitely. Configure timeouts for HTTP, DB, and other potentially slow operations.

## 7. How to handle listeners that take a long time

1. **Lower `max.poll.records` before blindly raising timeouts.** Start with a small batch, measure cycle duration, and gradually increase if the system has spare processing capacity. This is usually the right choice when each record carries high or highly variable business cost.
2. **Set `max.poll.interval.ms` from measurements.** Choose a value larger than cycle duration under heavy load with clear headroom. Never use a huge timeout to hide a hanging listener.
3. **Bound downstream operation durations.** Set connect/read timeouts for HTTP, query timeouts for DB, and cap retry counts. A retry with a long backoff also consumes budget between polls if it blocks the listener.
4. **Optimize with batch processing where possible.** If business logic allows, group DB operations or service calls in batches to cut overhead. Still measure total batch time and keep batch size bounded.
5. **Offload long-running work from the listener when appropriate.** The listener can validate the event and hand work off to a durable queue or persist it to a job table within an appropriate transaction before acknowledging the offset. Separate workers handle the slow task. Only commit after work is durably persisted; putting it into an in-memory-only queue and committing Kafka offsets risks losing work on process crash.
6. **Be careful with asynchronous processing.** Never call `KafkaConsumer` methods directly from business threads because the consumer is not thread-safe. If a listener returns results asynchronously or acknowledges outside the poll thread, use mechanisms supported by Spring Kafka and understand how the container tracks offsets, pause/resume, and acknowledgment order.
7. **Scale concurrency alongside partitions.** Spring Kafka can spawn multiple consumers via `concurrency`; each consumer has its own poll loop and time budget. Raising concurrency helps when sufficient partitions and resources exist, though it does not speed up a single sequentially slow listener.

## 8. Monitoring and diagnostics

When seeing repeated rebalances or abnormal consumer lag growth, cross-check the following signals:

- Listener processing duration per record and per batch, especially at p95/p99.
- Actual record count returned per poll and the `max.poll.records` setting.
- Time from starting batch processing until the container can poll again.
- Offset commit duration, retry counts, and total backoff duration.
- Kafka consumer logs for exceeding `max.poll.interval.ms`, leaving the group, and rebalances.
- Consumer lag, consumption rate, and rebalance count over the same time window.

A useful investigation workflow is reproducing with production-like batch sizes and dependency latencies, measuring cycle duration, and then lowering `max.poll.records` to see whether duration scales with record count. If time increases mainly due to an anomalous HTTP or DB call, fix timeouts and retries at that dependency. If cycles are steady yet always hover near the limit, tune batch size or timeout and re-verify under heavy load.

## 9. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| Increasing `session.timeout.ms` fixes slow listeners | Look at `max.poll.interval.ms`, since it bounds the time between two polls |
| A record listener handles one record at a time so there is no batch | One poll can still return many records; listener invocation times accumulate |
| Spring Kafka `pollTimeout` is the same as `max.poll.interval.ms` | One property is the wait time during a poll; the other is the limit between two polls |
| Increasing `max.poll.interval.ms` is always better | An overly large timeout delays detecting a consumer that has stopped making progress |
| Committing offsets early avoids rebalances | Early commits can drop records if business logic has not finished; acknowledge after processing or durable job persistence |
| Increasing `concurrency` fixes a record that takes too long to process | Concurrency distributes partitions across multiple consumers; it does not shorten processing time for a single running record |

## 10. Pre-production checklist

- Measured processing duration under heavy load and identified the maximum duration of a poll cycle.
- `max.poll.records` fits the processing cost per record or per batch.
- `max.poll.interval.ms` exceeds expected cycle time with intentional headroom.
- DB calls, HTTP calls, and retries all have timeouts or time bounds.
- Offset commit strategy aligns with when business processing succeeds.
- Listeners are idempotent to tolerate re-reads after rebalances or pre-commit failures.
- Monitoring tracks listener latency, consumer lag, and rebalance logs to catch negative trends.

`max.poll.interval.ms` is part of consumer lifecycle design. Good configuration balances batch size, processing duration, retries, commits, and consumer group resilience. When the entire poll cycle is measured and controlled, Spring Kafka applications suffer fewer slow-processing rebalances and operate more reliably.

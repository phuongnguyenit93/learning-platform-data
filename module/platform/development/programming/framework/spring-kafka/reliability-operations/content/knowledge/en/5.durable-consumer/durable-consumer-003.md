# max.poll.records and Processing Time

In a Kafka consumer, max.poll.records caps the maximum number of records returned to the application by a single poll() call. This parameter directly affects how much work a consumer receives in one poll cycle, the processing time before the next poll, batch size, the ability to keep pace with the consumer group, and the risk of triggering a rebalance.

The parameter must be evaluated alongside max.poll.interval.ms. max.poll.interval.ms defines the maximum time a consumer is allowed to go without calling poll() before being considered no longer making progress. If the application takes too long processing after a poll, the consumer can exceed this limit, leave the group, and trigger a rebalance. Another consumer may take over the partition, while in-flight work on the old consumer can finish late and create duplicates if the offset was not committed.

The configuration goal is to choose a records-per-poll count that the consumer can process within the allowed time window while still achieving good throughput and reasonable resource utilization. Increasing max.poll.records does not automatically make a consumer faster; if processing time scales with record count, a large batch can delay the next poll past the deadline.

## 1. Consumer Poll and Processing Loop

A Kafka consumer operates in a loop: fetch data, process data, record progress, and poll again. In a simple synchronous consumer, the cycle looks like this:

~~~
poll()
  |
  v
Receive up to max.poll.records records
  |
  v
Process records / batch
  |
  v
Commit offsets as configured
  |
  v
Next poll()
~~~

The consumer group relies on the poll cadence to know whether a consumer is still participating in processing. max.poll.interval.ms sets the bound on the time between two poll() calls. If a consumer fails to poll again within this deadline, the coordinator may consider the consumer hung or unable to process and begin revoking its partitions.

One important point: poll() may return fewer records than max.poll.records. This value is an upper bound on the records returned in a single poll, not a guarantee that every poll will always return that many records.

## 2. What Does max.poll.records Control?

max.poll.records is a Kafka consumer configuration. It caps the maximum number of records the consumer returns from a single poll to the application.

Example:

~~~properties
max.poll.records=100
~~~

With this configuration, a single poll returns at most 100 records. If less data is available, the consumer receives fewer. If more data is available, the remainder will be returned in subsequent polls.

This parameter impacts:

- **Work per cycle:** larger batches can amortize fixed per-record overhead.
- **Time between polls:** with sequential processing, more records typically extend processing time before the next poll.
- **Memory and batch size:** the application holds more records in memory at once, especially when payloads are large or the listener deserializes data into objects.
- **Retry and replay blast radius:** a large batch can force many records to be reprocessed when an error rolls back the batch.
- **Latency:** records at the start and end of a batch start processing at different times; large batches can make trailing records wait longer.

max.poll.records is not a limit on total bytes fetched from the broker. Kafka also has fetch configurations such as max.partition.fetch.bytes and fetch.max.bytes. The consumer can fetch data into its internal buffer before the application pulls records via poll(). Therefore, lowering max.poll.records does not necessarily reduce the bytes the client has already fetched or holds in memory immediately.

The actual record count per poll also depends on available data, assigned partitions, record sizes, fetch limits, and the consumer's read position.

## 3. What Does max.poll.interval.ms Control?

max.poll.interval.ms is the maximum time a consumer is permitted to go without calling poll() before the group considers it stalled. This value must exceed the processing duration of one poll cycle plus any associated delays before the next poll.

Example configuration:

~~~properties
max.poll.interval.ms=300000
~~~

A value of 300,000 ms equals 5 minutes. If the application receives a batch and takes over 5 minutes to call the next poll(), the consumer can exceed the limit.

Do not confuse max.poll.interval.ms with session.timeout.ms:

| Configuration | What It Monitors | Consequence When Exceeded |
|---|---|---|
| max.poll.interval.ms | Application progress via poll() invocations | Consumer may leave the group and partitions are reassigned |
| session.timeout.ms | Duration the coordinator receives no valid heartbeat | Coordinator considers consumer disconnected and triggers a rebalance |
| heartbeat.interval.ms | Heartbeat cadence in traditional consumer group setups | Controls heartbeat frequency, usually set lower than session timeout |

Heartbeats and polls serve two distinct purposes. A consumer may still be sending heartbeats while the application fails to call poll() for too long. max.poll.interval.ms remains the safeguard for processing progress. Specific heartbeat behavior depends on the consumer group protocol and Kafka version, but heartbeats should never be relied upon as a substitute for timely polling.

## 4. Relationship Between Record Count and Processing Time

For sequential processing, the duration of one cycle can be estimated by:

~~~
T_poll_cycle
  = T_poll_and_fetch
  + T_processing
  + T_commit
  + T_application_overhead
~~~

If each record has a roughly stable average processing time:

~~~
T_processing ≈ N × T_record
~~~

Where:

- N is the actual number of records processed in the cycle, not exceeding max.poll.records.
- T_record is the processing time of one record.
- T_poll_cycle is the time elapsed from one poll to the next poll.

The operational requirement is that T_poll_cycle must be smaller than max.poll.interval.ms with sufficient headroom. Never design right up to the limit because actual durations fluctuate due to GC, database load, network, broker, scheduler, retries, and commits.

For example, if a listener processes sequentially at about 250 ms per record and a poll returns 400 records, processing alone can take around 100 seconds. If max.poll.interval.ms is 60 seconds, that batch risks exceeding the limit even when both consumer and broker are healthy.

This is only an initial estimate. For production systems, measure the duration of the entire batch or poll cycle directly at high percentiles such as p95 and p99. Individual record times have uneven distributions; a few slow records can stretch the entire batch.

### 4.1. Calculating Batch Limit from a Time Budget

Suppose:

- max.poll.interval.ms is 300,000 ms.
- The application reserves 60,000 ms as headroom for commits, scheduling, GC, and variance.
- Sequential p95 processing time of one record is 500 ms.

The estimated processing budget is 240,000 ms. Maximum records under this estimate:

~~~
N <= 240,000 / 500
N <= 480 records
~~~

Do not treat 480 as a guaranteed safe setting. Per-record p95 does not mean the sum of 480 records always stays within budget. Measure p95/p99 of the full batch under realistic load, test with slow records, and pick a lower cap if variance is high.

If actual batch p99 is 190 seconds and max.poll.interval.ms is 300 seconds, there is roughly 110 seconds of headroom. If p99 is close to 295 seconds, the configuration is dangerously close to the limit and a GC pause or slow dependency can trigger a rebalance.

## 5. Configuration in Spring Boot and Spring Kafka

With Spring Boot, max.poll.records can be configured directly via consumer properties. max.poll.interval.ms is passed into Kafka consumer properties.

Example:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
        session.timeout.ms: 45000
        heartbeat.interval.ms: 15000
~~~

The values above are illustrative. Adjust them for your broker, consumer group protocol, processing duration, and actual SLOs. Spring Kafka listener containers usually manage offset commits via AckMode; when using a container, configure an appropriate ack mode and transactions rather than enabling auto commit arbitrarily.

You can configure concurrency on the listener container so multiple consumer instances process in parallel:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties()
           .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
~~~

Concurrency creates multiple consumers within the same listener container. Each consumer has its own poll loop and max.poll.interval.ms budget. Increasing concurrency can increase parallel processing capacity if the topic has enough partitions and dependent systems have headroom. If there are fewer partitions than consumers, some consumers will have no partitions to process.

Do not increase concurrency merely to compensate for an oversized batch or a slow record. Identify whether the bottleneck lies in CPU, database, HTTP dependencies, partition count, or per-record processing time.

## 6. Record Listeners and Batch Listeners

Spring Kafka supports listeners that process one record at a time and listeners that process an entire batch. The choice of listener affects timing calculations and the scope of work inside a poll.

### 6.1. Record Listener

Example:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderEvent event) {
    billingService.process(event);
}
~~~

With a record listener, the container invokes the listener for each record fetched from the poll. Even though the listener receives one record at a time, the consumer still has to continue polling on the container's cadence. If a poll returns 100 records and each listener invocation takes 2 seconds, processing the whole group can take around 200 seconds plus overhead before the container polls again.

Therefore, do not look only at the duration of a single listener invocation. Measure the total time from when the container receives poll results until it can issue the next poll.

### 6.2. Batch Listener

A batch listener receives a list of records in a single call:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    containerFactory = "batchOrdersListenerFactory"
)
public void handleBatch(List<OrderEvent> events) {
    billingService.processBatch(events);
}
~~~

Batch listeners are helpful when dependencies support bulk operations, such as writing multiple database rows in one transaction or calling a batch API. In those cases, processing time can be lower than sequential per-record processing.

However, large batches can:

- Increase memory used by lists and deserialized objects.
- Increase the completion time of a single callback.
- Increase the number of records that must be reprocessed if a batch fails.
- Introduce high latency for records near the end of the batch.
- Create load spikes on databases or downstream services.

Choose max.poll.records based on the batch size the listener can realistically process within the poll limit, not solely on broker fetch capability.

## 7. What Happens When max.poll.interval.ms Is Exceeded?

When a consumer fails to call the next poll() within the allowed time, the group coordinator may consider the consumer unable to make progress and trigger a rebalance. Partitions held by that consumer can be revoked and assigned to another consumer.

A typical sequence of events:

~~~
Consumer A calls poll() and receives records
          |
          v
Batch processing takes too long
          |
          v
Does not call poll() before max.poll.interval.ms
          |
          v
Consumer A leaves group / partition is revoked
          |
          v
Group rebalance
          |
          v
Consumer B receives partition
          |
          v
Consumer B reads from the latest committed offset
~~~

If consumer A has not committed the offsets of the records it was processing, consumer B may read them again. This is standard at-least-once behavior: records may be processed more than once, but should not be lost if offsets are committed only after successful processing and side effects are properly designed.

Another risk is that consumer A continues executing side effects after the partition has already been assigned to consumer B. Both may then act on the same business entity concurrently. Use idempotency keys, transactions on the target resource, or appropriate ownership checks.

With static membership, partition revocation timing can differ: partitions may be retained until session timeout rather than being transferred immediately when max.poll.interval.ms is exceeded. Static membership does not eliminate the poll progress limit; it only alters certain behaviors when a member temporarily stops polling.

## 8. Offset Commits and Processing Scope

max.poll.records determines how many records may be returned in a poll; AckMode and commit strategy determine which offsets are recorded as processed. These two concepts are related but do not replace each other.

In Spring Kafka:

- AckMode.RECORD commits offsets after the listener successfully processes each record per container semantics.
- AckMode.BATCH commits offsets of processed records in the batch when the batch finishes.
- AckMode.MANUAL and MANUAL_IMMEDIATE allow the listener to control acknowledgment according to configuration and execution context.
- Kafka transactions can include processed offsets in the same transaction as output records when the container is configured as transactional.

If a batch listener processes partially and then fails, retry and commit behavior depends on AckMode, the error handler, batch listener semantics, and transaction configuration. Clearly determine which records completed, which must be re-read, and whether side effects can repeat.

Never commit offsets before the protected work succeeds. Committing too early before an application failure can cause records to be skipped upon restart. Conversely, if side effects succeed but offsets are not committed, records may be reprocessed; idempotency handles this case.

## 9. Handling Slow Records and Unstable Dependencies

A single record can take much longer than the rest due to database locks, API timeouts, retries, large payloads, or heavy CPU work. If one slow record pushes the whole poll cycle past the limit, address the cause at both the record level and the batch level.

### 9.1. Setting Dependency Timeouts

Every database or HTTP call should have a finite timeout. If a listener can wait indefinitely, the consumer can stop polling indefinitely.

For example, if one record calls three dependencies sequentially, the worst-case time can be the sum of all three timeouts plus local processing time. Factor this total budget into single-poll processing time.

### 9.2. Shrinking Batches When Slow Records Occur

Lowering max.poll.records reduces the maximum number of records processed in one cycle. This can bring the poll cycle back under max.poll.interval.ms, at the cost of more polls and potentially higher overhead.

If only one category of records is very slow, consider separating streams/topics or handling that workload with a dedicated worker. A shared batch with vastly different processing times makes choosing an optimal batch limit difficult.

### 9.3. Using Pause/Resume When Waiting Is Needed

The Spring Kafka listener container supports pause and resume to temporarily stop receiving more records while keeping the container's poll loop active. This is useful when downstream is overloaded or the application needs to wait for a recovery condition.

Pausing does not mean the consumer stops all activity. The container still needs to keep polling to maintain group state and process control operations. Use the listener container's pause/resume API and verify behavior for your Spring Kafka version.

### 9.4. Avoiding Arbitrary Offloading from the Consumer Thread

Pushing work to an executor can help the consumer thread call poll() more steadily, but introduces problems around offsets and partition ownership. If the listener returns before work completes, the container may commit offsets while side effects are still unfinished.

If using asynchronous processing:

- Only acknowledge/commit after the corresponding work finishes.
- Preserve per-partition result handling and ordering if business logic requires ordering.
- Handle partition revocation while tasks are still running.
- Never call Kafka Consumer APIs directly from arbitrary threads; consumers are generally not thread-safe.
- Use version-appropriate async acknowledgment or listener/container support, and understand that the container may pause to wait for pending acknowledgments.

Offloading only improves poll cadence if commit, backpressure, and rebalance handling are fully solved.

## 10. How Retries and Backoff Slow Down Polling

If an error handler performs blocking retries directly on the listener/container thread, retry and backoff durations count toward the interval before the next poll. For example, 5 retries with backoffs of 1, 2, 4, 8, and 16 seconds already consume 31 seconds before counting processing and commits.

For extended retries:

- Include total processing plus backoff time in the max.poll.interval.ms budget.
- Use container pausing where appropriate to keep polling while waiting.
- Consider non-blocking retry topics if business requirements allow changes in ordering and processing flow.
- Avoid long synchronous retries on the consumer thread when multiple partitions share a consumer.

Non-blocking retries move records to retry topics and allow the consumer to continue, though they can alter processing order among records sharing a key or partition. Choose the retry approach based on ordering requirements, not throughput alone.

## 11. Impact of Concurrency and Partition Count

In Spring Kafka, concurrency on ConcurrentMessageListenerContainer creates multiple child listener containers, each with its own consumer. The number of active consumers is bounded by the number of assigned partitions.

Example for a topic with 6 partitions:

- Concurrency 1: one consumer handles all 6 partitions.
- Concurrency 3: up to 3 consumers can receive partitions, averaging 2 partitions per consumer under balanced assignment.
- Concurrency 6: up to 6 consumers can process in parallel, each potentially receiving one partition.
- Concurrency 10: some consumers may receive no partition assignments.

max.poll.records applies per consumer, not to the combined batch of the entire listener container. With concurrency 3 and max.poll.records 100, a poll on each consumer can return up to 100 records; the total records actively processed across consumers can exceed 100.

Increasing concurrency increases parallel poll loops and total processing capacity, but also increases connections, memory, database load, and concurrent tasks. If the database only sustains 10 concurrent queries, raising concurrency to 30 can increase processing time rather than reduce it.

Tune concurrency to partition count and downstream capacity. Monitor per-consumer processing duration to detect uneven load distribution or partitions with heavy records.

## 12. Reading Metrics to Know Whether Tuning Is Needed

Do not tune max.poll.records based solely on consumer lag. Rising lag can stem from producer rate exceeding processing rate, slow dependencies, too few partitions, skewed key distribution, or constant consumer rebalances.

Useful signals:

| Signal | Interpretation |
|---|---|
| Time between two polls | Is it approaching max.poll.interval.ms? |
| Processing time per record and per batch | Does the current batch fit within the time budget? |
| Actual records per poll | Is it consistently hitting max.poll.records? |
| Consumer lag per partition | Which partition is falling behind? |
| Rebalance count and duration | Are partitions being revoked from consumers frequently? |
| Commit latency and commit failures | Are commits stretching the poll cycle? |
| Retry count and backoff duration | Is the error handler holding the consumer thread too long? |
| CPU, GC pauses, and heap | Is the consumer constrained by JVM resources? |
| Database/API latency | Which dependency is elongating processing time? |

Consumer metrics can be exported via Kafka client JMX, Micrometer, or your application's observability stack. Metric names and tags depend on versions. Verify actual metrics and tag by group, client, and topic/partition with controlled cardinality.

### 12.1. Example Scenario Readings

**Lag rising, batch processing time low, no rebalances:** total throughput may simply be insufficient for the producer rate. Check concurrency, partition count, CPU, and bulk processing capability before raising max.poll.records.

**Lag rising, batch time near max.poll.interval.ms, rebalances increasing:** the batch may be too large or a dependency is processing too slowly. Lower max.poll.records, reduce per-record processing time, or adjust max.poll.interval.ms after assessing impact.

**Lag rising on only one partition:** keys may be skewed or a subset of records is slow to process. Raising concurrency cannot split one partition across multiple consumers in the same group simultaneously; review keys, partitioning, or how heavy work is handled.

**Small batch size yet poll cycle still long:** a few records may take a very long time, commits may be slow, the error handler may be blocking on retries, or the JVM may experience large GC pauses. Find where the time is spent instead of blindly shrinking the batch further.

## 13. Procedure for Tuning max.poll.records

A practical procedure:

1. Measure records per poll, record processing time, batch processing time, and interval between polls.
2. Identify whether the listener processes per record or in batches, sequentially or concurrently.
3. Measure p95/p99 processing time under production-like load, including retries and dependency timeouts.
4. Pick a time budget below max.poll.interval.ms to leave room for commits, GC, and variance.
5. Choose max.poll.records so the p99 batch fits within that budget.
6. Experiment with increasing/decreasing batch size under representative load while monitoring throughput, lag, memory, and rebalances.
7. Test behavior when a record is slow, a broker loses leadership, or downstream times out.
8. Roll out gradually with rollback thresholds if rebalances or lag spike unexpectedly.

No single max.poll.records value fits every application. Consumers handling lightweight data can use larger batches to reduce overhead. Consumers calling slow APIs or performing many side effects may need small batches and bounded concurrency.

## 14. Commonly Confused Configurations

| Configuration | Controls | Does Not Mean |
|---|---|---|
| max.poll.records | Maximum records returned in a single poll | Maximum bytes fetched from the broker |
| max.poll.interval.ms | Maximum time between polls | Timeout of a single record or HTTP call |
| max.partition.fetch.bytes | Per-partition fetch data limit in a request per Kafka rules | Number of records delivered to the listener |
| fetch.max.bytes | Overall fetch data limit in a request per Kafka rules | Fixed application batch size |
| session.timeout.ms | Heartbeat miss limit | Maximum time a listener is allowed to process |
| heartbeat.interval.ms | Heartbeat cadence | Offset commit timing |
| AckMode | How the container acknowledges/commits offsets | Maximum records in a poll |
| concurrency | Number of child consumers/containers running in parallel | Number of partitions processed beyond assigned partitions |

Distinguishing these configurations accurately prevents fixing the wrong layer. If records are too large, raising max.poll.records will not solve it. If the listener processes too slowly, raising fetch.max.bytes will not make the consumer poll sooner.

## 15. Common Design Mistakes

| Practice | Consequence | Adjustment |
|---|---|---|
| Setting max.poll.records very high without measuring batch duration | Poll cycle can exceed max.poll.interval.ms | Measure batch p95/p99 and pick a fitting limit |
| Only increasing max.poll.interval.ms to hide hung records | Rebalances arrive late, hung tasks stay stuck longer, and recovery slows | Set dependency timeouts, cap batches, and handle slow records |
| Confusing max.poll.records with a byte limit | Memory still grows due to fetch caches or large payloads | Check both fetch byte limits and payload sizes |
| Raising concurrency above partition count | Consumers sit unassigned and waste resources | Base on partition count and downstream capacity |
| Offloading tasks and committing offsets immediately | Processing can be lost if workers fail after commit | Acknowledge after task completion and handle revocations |
| Blocking retries too long inside the listener | Misses poll deadline, triggering rebalances | Budget backoff or use pause/non-blocking retries |
| Setting batch too low without measuring | Increases poll/commit overhead and reduces throughput | Test under load and monitor latency/throughput |
| Raising batch size to fix lag caused by a hot partition | Hot partition remains the bottleneck | Review key distribution and partitioning |

## 16. Operations Checklist

Before taking a consumer configuration into production, verify:

1. What is max.poll.records set to, and what is the actual record count per poll?
2. Is the listener a record listener or a batch listener?
3. Does processing run sequentially or concurrently, and what is the p95/p99 duration of one batch?
4. Is the sum of processing, commit, retry, and backoff times below max.poll.interval.ms with headroom?
5. Do dependencies have finite timeouts and backpressure mechanisms?
6. Do AckMode and offset commit timing align with side effects?
7. When the poll interval is exceeded, can records be reprocessed safely?
8. If using async processing, how are tasks still running after partition revocation handled?
9. Does concurrency match partition count and database/API capacity?
10. Can dashboards detect long poll cycles, rebalances, lag, commit failures, and dependency latency?

max.poll.records and processing time must be designed together. Sufficiently large batches reduce overhead, yet every batch must finish before the poll deadline with realistic headroom. When processing is long or variable, reducing work per poll, improving dependencies, bounding retries, and managing pause/resume will help consumers maintain steady progress.

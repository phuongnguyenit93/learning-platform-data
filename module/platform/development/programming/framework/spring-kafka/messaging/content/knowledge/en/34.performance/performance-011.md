# Durability vs. Performance Trade-offs

## Lesson Objectives

In the **Performance** chapter, this lesson analyzes how to balance data durability with throughput and latency when building Kafka applications with Spring Kafka. A configuration can reduce the risk of losing records while increasing acknowledgement time, replication overhead, or processing latency. Conversely, optimizing too aggressively for speed can widen the data-loss window or increase duplicate processing when failures occur.

**SPRING_KAFKA_MESSAGING** focuses on building event-producing and consuming applications using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing for reliable messaging pipelines. Durability vs. performance trade-offs must be evaluated across the entire event path: producer, broker replication, consumer processing, and offset commits.

After this lesson, learners will be able to:

- Distinguish between durability, availability, throughput, and latency.
- Understand the impact of producer `acks`, retries, and idempotence.
- Combine replication factor with `min.insync.replicas`.
- Tune batching, linger, compression, and producer buffers.
- Choose appropriate consumer acknowledgment/commit strategies.
- Understand Kafka transactions and the scope of exactly-once semantics.
- Recognize the limits of Kafka guarantees when updating external databases.
- Tune fetch, poll, and concurrency without causing continuous rebalances.
- Design configurations according to SLAs and event criticality.
- Validate via failure tests and controlled benchmarks.

## 1. Durability and performance are distinct goals

**Durability** is the ability to preserve acknowledged data across failures such as broker process crashes, host failures, or replica disconnects. **Performance** is typically evaluated by throughput and latency:

- Throughput: number of records or bytes processed per unit of time.
- Latency: time from sending until receiving acknowledgement or completing processing.
- Durability: probability that an acknowledged record survives a failure.
- Availability: ability to keep accepting and processing requests when part of the system fails.

It is impossible to maximize every metric with a single configuration. For example, waiting for full replication can increase latency while reducing record loss risk when a leader fails. Grouping many records into a batch reduces request count and boosts throughput, yet the first record must wait longer for the batch to fill or linger to expire.

Distinguish the milestones in an event flow:

1. Application creates an event.
2. Producer serializes and puts the record into the buffer.
3. Producer sends the request to the broker.
4. Broker leader appends the record.
5. Replicas catch up with the leader per the replication protocol.
6. Broker sends acknowledgement according to the `acks` setting.
7. Consumer polls the record.
8. Listener executes side effects.
9. Consumer commits the offset.

A record may already be acknowledged by the broker yet not processed by the consumer. Conversely, a listener may have updated a database while the offset is not yet committed, causing redelivery after a crash. Thus, producer durability and consumer reliability are two separate concerns.

~~~mermaid
flowchart LR
    A["Application event"] --> B["Serialize + producer buffer"]
    B --> C["Broker leader"]
    C --> D["Follower replicas"]
    D --> E["Producer acknowledgment"]
    E --> F["Consumer poll"]
    F --> G["Listener processing"]
    G --> H["Offset commit"]
    I["Producer settings"] -. "acks / retries / batching" .-> B
    J["Topic settings"] -. "replication / min ISR" .-> C
    K["Consumer settings"] -. "ack mode / commit" .-> G
~~~

## 2. Producer acks determines write confirmation level

The `acks` property specifies how many broker acknowledgements the producer requires before considering a send successful.

| acks | Confirmation condition | Trade-off |
|---|---|---|
| 0 | Producer does not wait for broker acknowledgement | Low latency, but no confirmation whether the broker received the record |
| 1 | Leader confirms after appending the record to its local log | Faster, but the leader can fail before followers replicate |
| all | Leader waits for current ISR replicas to confirm per the replication protocol | Stronger durability, potentially higher latency and dependent on ISR |

### 2.1. acks=0

The producer sends records without waiting for broker confirmation. The application has no proof the broker received the record. If the network drops or the broker misses the request, the application may still treat the send as complete.

This setting is only appropriate for data that can be lost and regenerated, such as non-critical telemetry. Never use it for payments, orders, inventory, or commands requiring guarantees.

### 2.2. acks=1

The leader acknowledges after writing the record to its own log. Followers can replicate afterward. If the leader crashes before followers receive the record, another replica elected as leader may lack the newly acknowledged record.

`acks=1` can lower wait time compared to `acks=all`, yet creates a data-loss window upon leader failure. Use it only when durability requirements tolerate this risk and replication topology has been evaluated.

### 2.3. acks=all

`acks=all` requires the leader to wait for all current ISR replicas to confirm the record per the replication protocol. This is typically chosen for critical events, though `min.insync.replicas` must be configured properly to prevent writes when the ISR is too small.

`acks=all` does not mean the broker fsynced each record to disk before replying. Kafka relies on logs, page cache, and replication; actual durability also depends on broker settings, OS, filesystem, and storage infrastructure.

## 3. Replication factor and min.insync.replicas

Producer `acks` is only part of durability. Topics need enough replicas to tolerate broker failures.

Example topic with replication factor 3:

~~~text
Topic: commerce.order.created
Partition 0:
  Broker 1: Leader
  Broker 2: Follower
  Broker 3: Follower

min.insync.replicas = 2
producer acks = all
~~~

In this setup, producers can only write with `acks=all` when at least two replicas are in the ISR. The leader waits for current ISR replicas to confirm. If the ISR shrinks to one, the broker rejects writes to uphold the `min ISR` condition rather than accepting a write with weaker protection.

| Replication factor | min.insync.replicas | Operational meaning |
|---:|---:|---|
| 1 | 1 | No redundant replica |
| 3 | 1 | Can still write when only the leader remains in ISR |
| 3 | 2 | Can write when at least two replicas are in ISR |
| 3 | 3 | Requires all three replicas in ISR to allow writes |

For critical data, a common baseline is replication factor 3, `min.insync.replicas` 2, and producer `acks=all`. This is a starting point for evaluation, not a mandatory rule for every workload.

New topics can be declared with Spring Kafka when managing topics via `KafkaAdmin`:

~~~java
@Bean
public NewTopic orderCreatedTopic() {
    return TopicBuilder.name("commerce.order.created")
        .partitions(6)
        .replicas(3)
        .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
        .build();
}
~~~

This example applies when creating a new topic. For existing topics, manage configs through dedicated provisioning/admin workflows and verify actual broker configs; do not assume declaring a bean automatically alters every property of an existing topic.

### 3.1. When ISR falls below min ISR

When the number of replicas in the ISR drops below `min.insync.replicas`, producers may receive `NotEnoughReplicas` or `NotEnoughReplicasAfterAppend` errors. This is intentional durability protection: the broker rejects writes because minimum replication cannot be satisfied.

Applications should:

- Retry according to an appropriate delivery timeout and retry policy.
- Monitor ISR shrinks and under-replicated partitions.
- Fix the broker/network/disk issue causing replicas to fall behind.
- Avoid lowering min ISR mid-incident without assessing data-loss risk.
- Alert when producer error rates rise due to insufficient replicas.

If min ISR equals the replication factor, any transient replica loss can block writes. Durability is higher, while write availability is lower. If min ISR is too low, the system keeps accepting writes with few healthy replicas at the cost of reduced fault tolerance.

### 3.2. Unclean leader election

Unclean leader election allows a non-ISR replica to become leader when no ISR replica can lead. This can restore availability, but risks losing records that replica had not yet received.

For durable data, unclean leader election is normally disabled. In exchange, partitions may remain unavailable until an ISR replica returns. This is an availability vs. durability choice when the entire ISR loses leadership eligibility.

## 4. Producer idempotence and retries

Retries help producers recover from transient errors like network timeouts or broker leader transitions. Yet if the broker wrote a record and the acknowledgement was lost, the producer can resend and create duplicates.

An idempotent producer uses a producer ID and sequence numbers so the broker detects retries of the same batch, preventing duplicate writes from retries within a producer session.

Recommended configuration:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
~~~

In modern Kafka clients, idempotence is enabled by default in many standard configs; declaring it explicitly makes operational intent clearer. When idempotence is enabled, Kafka requires compatible settings such as `acks=all`, `retries` greater than 0, and `max.in.flight.requests.per.connection` within the supported limit.

Idempotence protects internal producer retries. It does not automatically eliminate duplicates caused by:

- Application calling publish twice for the same business event.
- Service restarting and regenerating an event.
- Clients resending a command after a timeout.
- Two independent producers emitting the same event.
- Consumer executing side effects multiple times after uncommitted offsets.

Therefore, critical events should still carry a stable `eventId` and use consumer idempotency.

### 4.1. Retries and delivery timeout

Producer retries can raise latency. `delivery.timeout.ms` caps total time the producer tries sending a record before reporting failure; `request.timeout.ms` caps waiting for a single request; `linger.ms` adds batch accumulation wait time.

Set `delivery.timeout.ms` sufficiently larger than `request.timeout.ms` and `linger.ms`. If too short, the producer may fail while the broker is recovering. If too long, callers wait longer before learning a send failed.

Do not retry infinitely at the business layer without bounds. Once the producer hits delivery timeout, the application should record the failure state and decide application-level retries using event ID/idempotency policies.

## 5. Batching: increasing throughput by grouping records

Producers group multiple records for the same partition into a batch before sending. Batching reduces network request overhead, amortizes protocol cost, and typically raises throughput.

Two key configurations:

- `batch.size`: target batch size in bytes per partition.
- `linger.ms`: how long the producer waits for more records to fill the batch further before sending.

Example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536
        linger.ms: 5
        buffer.memory: 67108864
~~~

This example uses a 64 KiB target batch, 5 ms linger, and 64 MiB producer buffer. These are benchmark starting points; low-volume or latency-sensitive workloads may need lower linger.

### 5.1. Increasing batch size

Larger batches can improve network and compression efficiency when partition traffic is sufficient. However, overly large batches can:

- Increase producer memory usage.
- Make the first record wait longer.
- Create large traffic bursts to brokers.
- Increase per-batch serialization/compression time.
- Yield no benefit if per-partition traffic is too low.

Batches are formed per partition, so total memory can climb when a producer sends to many partitions concurrently.

### 5.2. Increasing linger.ms

`linger.ms` gives the producer extra time to gather records. Higher linger usually improves batch utilization and throughput under dense traffic, in exchange for higher send latency.

For APIs requiring responses in a few milliseconds, low or zero linger may make sense. For throughput-oriented event pipelines, a few milliseconds or more can improve performance noticeably. Measure p95/p99 latency rather than looking only at average throughput.

### 5.3. Do not flush after every record

Calling `flush` after every send forces the producer to push pending batches and destroys batching benefits. Normally, let the producer buffer and batch naturally, then track send futures.

Flush only at clear business boundaries, when ensuring buffered records are sent before shutdown, or in special workflows. Never use per-message flushing by default.

## 6. Compression: trading CPU for network and disk

Producers can compress batches before sending. Kafka supports common codecs like `gzip`, `snappy`, `lz4`, and `zstd` depending on client/broker versions.

| Codec | General characteristics | Trade-off |
|---|---|---|
| none | Uncompressed | Low CPU, more bytes transferred |
| lz4 | Fast compression/decompression | Typically moderate compression ratio |
| snappy | Fast, low CPU overhead | Typically moderate compression ratio |
| gzip | Good compression ratio in many workloads | Higher CPU and may increase latency |
| zstd | Good compression ratio with multiple compression levels | Can be CPU-intensive depending on level |

Example:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        compression.type: lz4
~~~

Compression is usually more effective when batches are large enough and payloads have repetitive structure. Already-compressed or encrypted payloads may shrink very little. Compression lowers network bandwidth and written data volume, while raising CPU on producer, broker, or consumer depending on where codecs run.

Measure CPU, network bytes, disk throughput, and latency together. Do not pick a codec solely by highest compression ratio.

## 7. Buffering and asynchronous sending

`KafkaTemplate.send` sends asynchronously and returns a future. Calling `get` immediately after every send serializes the send flow and caps throughput to broker round-trip latency.

Example:

~~~java
public CompletableFuture<SendResult<String, OrderCreated>> publish(
        OrderCreated event) {

    return kafkaTemplate.send(
        "commerce.order.created",
        event.orderId(),
        event
    );
}
~~~

You can attach a callback to record success/failure:

~~~java
kafkaTemplate.send(topic, key, event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            log.error("Kafka publish failed, eventId={}",
                event.eventId(), exception);
            return;
        }

        RecordMetadata metadata =
            result.getRecordMetadata();

        log.debug("Published topic={}, partition={}, offset={}",
            metadata.topic(),
            metadata.partition(),
            metadata.offset());
    });
~~~

This example uses `CompletableFuture` in Spring Kafka 3.x. With Spring Kafka 2.x, `send` typically returns `ListenableFuture` with its corresponding callback API.

Do not create unbounded numbers of in-flight futures. If the producer outpaces the broker, `buffer.memory` can fill up; `send` can block up to `max.block.ms` and throw an exception. Enforce bounded concurrency, rate limits, or application-level backpressure.

## 8. Choosing producer settings by goal

| Workload | Acks | Idempotence | Batching/compression | Direction |
|---|---|---|---|---|
| Payment/order command | all | true | Moderate batch, low linger per SLA | Prioritize durability and clear error handling |
| Audit event | all | true | Moderate/large batch, suitable compression | Prioritize durable storage and steady throughput |
| High-volume clickstream | all or per data-loss tolerance | true if preventing retry duplicates | Larger batch, compression | Prioritize throughput and cost |
| Reconstructible metrics | May consider 1 or 0 per risk | As needed | Large batch, compression | Prioritize speed/cost |
| Low-latency command | all if durability needed | true | Low linger, smaller batch | Meet SLA without dropping business guarantees |

Never use `acks=0` just because benchmarks show high throughput. Benchmarks must reflect broker/network failures and the data-loss tolerance the business accepts.

## 9. Consumer acknowledgment and offset commits

Consumers poll records from Kafka. Offset commits tell the broker how far the consumer group has processed. Commit timing determines the window of records that can be redelivered after a crash.

In Spring Kafka, the container manages commits via `AckMode`. Common modes include:

| AckMode | Commit timing | Trade-off |
|---|---|---|
| RECORD | After listener processes each record successfully | Smaller replay window, more frequent commits |
| BATCH | After processing the entire batch from a poll | Fewer commits, potentially more records replayed |
| TIME | When time interval and processing conditions are met | Tunes commit frequency |
| COUNT | When record count threshold is met | Reduces commit overhead |
| COUNT_TIME | By count or time | Balances commit count |
| MANUAL | Listener explicitly acknowledges; container commits per policy | Finer control, requires careful code |
| MANUAL_IMMEDIATE | Commits immediately on acknowledge per execution context | Can raise commit overhead |

Verify exact names and semantics against your Spring Kafka version. With `RECORD`/`BATCH`, the listener must complete successfully before the container commits per the chosen mode.

### 9.1. Why committing before processing can lose data

Suppose a consumer commits the offset before updating the database. If the process crashes after the commit but before the database write, Kafka will not redeliver the committed record. The side effect is lost.

If the consumer updates the database first and then commits the offset, a crash after the database commit but before the Kafka offset commit can cause redelivery. This is at-least-once behavior; idempotency is needed to avoid duplicate side effects.

For critical business logic, the standard order is processing successfully first and committing offsets afterward, paired with idempotent database operations or an inbox table.

### 9.2. Auto commit and Spring Kafka

Understand `enable.auto.commit` clearly. Spring Kafka listener containers usually manage offset commits and disable Kafka auto commit by default in modern configurations, yet declaring it explicitly and checking effective config is good practice.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Spring Kafka listener containers default to synchronous commits in common setups. You can configure this explicitly on the listener container factory:

~~~java
factory.getContainerProperties().setSyncCommits(true);
~~~

Synchronous commits use `commitSync` for container-managed commits. This can add latency, while commit errors are observed directly in the commit path. Async commits can reduce wait time, but require understanding callbacks, commit ordering, and error handling.

### 9.3. RECORD or BATCH?

`RECORD` makes sense when each event has independent side effects and you want to minimize the number of records replayed after an error. `BATCH` can improve commit efficiency when processing many records per poll, yet an error late in the batch may cause multiple uncommitted records to be redelivered depending on error-handling and acknowledgment policies.

Choose based on commit cost, processing semantics, and idempotency capabilities. Do not pick `BATCH` solely to reduce commit count if listener code cannot handle duplicates.

## 10. Consumer fetch and poll tuning

Consumers pull records via `poll`. Several properties govern data volume and poll timing:

- `fetch.min.bytes`: minimum bytes the broker tries to accumulate before returning a fetch response.
- `fetch.max.wait.ms`: how long the broker may wait to reach `fetch.min.bytes`.
- `max.partition.fetch.bytes`: limit on data pulled from a single partition per fetch.
- `fetch.max.bytes`: limit on total data in a fetch response.
- `max.poll.records`: maximum records returned in one poll.
- `max.poll.interval.ms`: time limit between polls before the consumer is considered stalled.

Raising `fetch.min.bytes` can cut request count and raise throughput under dense traffic, while adding latency under low traffic. Raising `max.poll.records` increases work per poll, yet the listener must finish that batch within `max.poll.interval.ms`.

If record processing is slow, raising `max.poll.records` can push the consumer past `max.poll.interval.ms` and trigger rebalances. Tune processing time, concurrency, and poll interval together.

Example settings:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 500
      properties:
        fetch.min.bytes: 65536
        fetch.max.wait.ms: 50
        max.partition.fetch.bytes: 1048576
        max.poll.interval.ms: 300000
~~~

These values are only benchmark examples. Never apply them verbatim when payloads are large, listeners are slow, or partition count is low.

## 11. Concurrency and partitions

Within a consumer group, a partition is assigned to at most one consumer member at a time. Increasing concurrency enables parallel processing when the topic has enough partitions.

For example, a topic with 6 partitions:

- Concurrency 1: one consumer reads all 6 partitions.
- Concurrency 3: up to three consumers share 6 partitions.
- Concurrency 6: up to six consumers can run, one partition each.
- Concurrency 10: at least four consumers get no partitions in the group if no other topics are subscribed.

Raising concurrency beyond partition count does not increase throughput for that topic. It also increases threads, connections, and consumer management overhead.

In Spring Kafka:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    concurrency = "3"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Concurrency must balance against:

- Partition count.
- Processing time per record.
- Database/downstream capacity.
- Consumer instances in the deployment.
- Per-key ordering requirements.
- Consumer lag and rebalance frequency.

Do not increase concurrency when the database is already overloaded; doing so can lower end-to-end throughput via contention and connection pool exhaustion.

## 12. Kafka transactions and exactly-once semantics

Idempotent producers prevent retry duplicates within one producer session. Kafka transactions extend guarantees across multiple records and offsets in Kafka-to-Kafka workflows.

A transaction can:

- Write multiple records to one or more topics.
- Include consumer group offsets in the same transaction.
- Commit all or abort all.

In consume-transform-produce, the consumer reads input, the producer writes output, and input offsets are committed within the transaction. Downstream consumers configured with `isolation.level=read_committed` read only records from committed transactions.

~~~mermaid
sequenceDiagram
    participant C as Input Consumer
    participant A as Application
    participant T as Kafka Transaction
    participant O as Output Topic
    participant G as Consumer Group Offset
    C->>A: Read input record
    A->>T: Begin transaction
    A->>T: Produce output record
    A->>T: Send input offset to transaction
    T->>O: Commit output
    T->>G: Commit offset atomically
    Note over O,G: Or abort both output and offset
~~~

Kafka exactly-once semantics protect a properly configured consume-process-produce chain within Kafka. It does not create an atomic distributed transaction between Kafka and an external database.

### 12.1. Configuring transactions in Spring Kafka

With Spring Boot, you can configure a transaction ID prefix:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-unique-
    consumer:
      properties:
        isolation.level: read_committed
~~~

The transaction ID prefix must be unique across active application instances to avoid producers fencing one another. In multi-replica deployments, attach a stable, unique instance identity to the prefix instead of the illustrative literal above.

Spring Boot can auto-configure a transaction-capable producer factory when `transaction-id-prefix` is set. Listener containers can participate in transactions per appropriate Spring Kafka configuration. Check transaction manager, listener factory, and error handling for your application version.

### 12.2. Cost of transactions

Transactions add complexity and can raise latency:

- Producers must begin/commit/abort transactions.
- Coordinators manage transaction state.
- `read_committed` consumers only read up to the last stable offset, potentially waiting on open transactions to finish.
- Long-running transactions can delay visibility of subsequent records for `read_committed` consumers.
- Transaction timeouts and fencing must be operated properly.

Keep transactions short, bound records per transaction, and never call slow external services while a transaction is open.

## 13. Kafka transactions do not cover databases

A listener may update a database and then publish a Kafka event. A Kafka transaction does not automatically commit/roll back the database transaction alongside it.

Example:

1. Database transaction commits successfully.
2. Process crashes before Kafka publish.
3. Database holds new state, yet no event was sent.

Or:

1. Kafka publish succeeds.
2. Database transaction rolls back.
3. Event was emitted while database state remained unchanged.

This is the dual-write problem. Common solutions include:

- Transactional Outbox: write business data and an outbox row in the same database transaction; a separate publisher relays outbox rows to Kafka.
- Inbox/idempotency: consumer stores processed event IDs alongside business updates.
- CDC: read outbox/change logs to publish events.
- Saga/compensation: coordinate multiple services using compensatable business steps.

Never advertise Kafka EOS as an exactly-once guarantee for every side effect in the system. State transaction boundaries explicitly.

## 14. Durability vs. speed trade-offs by layer

| Layer | Durability priority | Speed priority | Risk/cost |
|---|---|---|---|
| Producer acks | all | 1 or 0 | Lower write confirmation guarantee |
| Idempotence | enabled | May disable if duplicates tolerated | Retries can write duplicates |
| Broker replication | RF 3, min ISR 2 | Lower RF | Fewer redundant replicas |
| Leader election | Unclean election disabled | May enable if availability prioritized | May lose unreplicated records |
| Batching | Sufficient batch within SLA | Large batch, higher linger | Higher latency and memory |
| Compression | Balanced codec | May disable compression | Higher network/disk usage |
| Consumer commit | After successful processing | Commit by batch/count/time | Larger replay window |
| Transaction | Kafka EOS when needed | Simpler at-least-once | Coordinator/transaction overhead |
| Consumer isolation | `read_committed` for transactional flows | `read_uncommitted` if acceptable | May see aborted records |

Durable settings do not necessarily make everything drastically slower if batching and compression are tuned well. Measure each layer to find the real bottleneck.

## 15. Three reference configuration profiles

The following profiles are starting points for benchmarking, not universal presets.

### 15.1. Durability-first profile

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        delivery.timeout.ms: 120000
        request.timeout.ms: 30000
        linger.ms: 5
        batch.size: 32768
        compression.type: lz4
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

The topic should use replication factor 3 and `min.insync.replicas` 2. This profile suits critical events, transactional flows, or per-record commit requirements. Set `read_committed` only when consumers must filter uncommitted/aborted transactional records; if producers do not use transactions, `read_uncommitted` can be simpler.

### 15.2. Balanced profile

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 5
        batch.size: 65536
        compression.type: lz4
        delivery.timeout.ms: 120000
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
~~~

Uses batch commits to reduce commit overhead when listeners process batches safely and idempotently. Evaluate how many records can be replayed after an error.

### 15.3. Throughput-first profile

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        linger.ms: 20
        batch.size: 131072
        compression.type: zstd
        buffer.memory: 134217728
    consumer:
      enable-auto-commit: false
      max-poll-records: 1000
    listener:
      ack-mode: batch
~~~

This profile increases batch accumulation time, batch size, and buffering. Throughput can rise under dense traffic and compressible payloads, though latency and memory also increase. Check producer/consumer CPU, broker request queues, consumer lag, and p99 end-to-end latency.

## 16. Measure instead of guessing

Benchmarks must reflect production-like payloads and failure modes.

Measure at minimum:

- Producer records/sec and bytes/sec.
- Producer request latency p50, p95, p99.
- Send errors, retry counts, and timeouts.
- Average batch size and compression ratio.
- Broker network, disk throughput, and request queues.
- Under-replicated partitions and ISR shrinks.
- Consumer records/sec and per-partition lag.
- Listener processing time.
- Commit latency and commit failures.
- End-to-end event age from `createdAt` to `processedAt`.
- Duplicate rate and DLT rate.

Do not measure average throughput alone. A setting can increase throughput by 30% while multiplying p99 latency or causing consumer lag to climb continuously.

### 16.1. Benchmark workflow

1. Create topics with production-like replication factor and partition count.
2. Use payloads matching real sizes and distributions.
3. Warm up producers, brokers, and consumers.
4. Run a baseline configuration.
5. Change one parameter group at a time.
6. Measure throughput, p95/p99 latency, CPU, network, disk, and lag.
7. Repeat with broker restarts or slow replicas.
8. Compare lost data, duplicates, and recovery time.
9. Pick the configuration meeting SLAs rather than simply peak throughput.

Use the same producer count, consumer count, partition count, and workload when comparing. Changing multiple parameters simultaneously makes it hard to tell which change produced the outcome.

## 17. Failure testing for durability

Durability is only proven when the system encounters faults.

Scenarios to test in test/staging environments:

- Stop the leader broker right after a producer send.
- Disconnect a follower to shrink the ISR.
- Pause a broker or inject a network partition.
- Restart the producer while requests are in flight.
- Kill a consumer after executing side effects but before offset commit.
- Kill a consumer after offset commit.
- Slow down the database or reject connections.
- Leave a transaction open for a long time and then abort it.
- Replay old records through a new consumer version.

Verify outcomes by event ID:

| Scenario | What to verify |
|---|---|
| Leader fails after `acks=1` | Records may be lost if followers had not replicated |
| Leader fails after `acks=all` and proper min ISR | Acknowledged records remain on eligible replicas |
| Consumer crashes before processing | Record is redelivered |
| Consumer crashes after DB commit, before offset commit | Record may be redelivered, yet side effects do not duplicate |
| Consumer crashes after offset commit | No completed side effects before commit are lost |
| Transaction aborts | `read_committed` consumers do not see aborted output |
| ISR drops below min ISR | Producers receive errors instead of writing below the protection threshold |

Never run destructive failure tests in production. Use recoverable environments with clearly identifiable test data.

## 18. Common configuration mistakes

| Symptom | Possible cause | Suggested action |
|---|---|---|
| Low producer throughput | `acks`, linger, compression, or broker bottleneck | Measure request latency, batches, and CPU |
| Records lost on leader failure | `acks=1` or weak replication/min ISR | Use `acks=all`, appropriate RF, and min ISR |
| Producer reports `NotEnoughReplicas` | ISR below min ISR | Restore replicas and monitor ISR |
| Producer buffer full | Slow broker or app sending too fast | Backpressure, bounded concurrency, measured buffer increase |
| Latency rises after raising linger | Producer waits to accumulate batches | Lower linger or adjust SLA |
| High CPU after enabling compression | Codec/level too heavy | Try lz4/snappy or lower compression level |
| Consumer lag rising | Processing throughput lower than publish rate | Check partitions, downstream, poll, and concurrency |
| Frequent rebalances | Slow processing exceeding `max.poll.interval.ms` or unstable consumer | Adjust poll/processing and find bottlenecks |
| Duplicate side effects | At-least-once redelivery, app retries | Idempotency by event ID |
| `read_committed` shows high lag | Open transactions or slow commits | Shorten transaction duration and watch LSO |
| Transactional producer fenced | Duplicate transaction ID prefix across instances | Use unique prefixes |
| DLT cannot read old records | Schema Registry missing schema versions | Retain schema history and test replays |

## 19. Selection rules by event criticality

Not every event needs the same level of durability.

| Event type | Recommended protection | Rationale |
|---|---|---|
| PaymentCaptured | `acks=all`, RF 3, min ISR 2, idempotence | Financial transactions must never be silently lost |
| OrderCreated | `acks=all`, RF 3, min ISR 2, idempotent consumer | Initiates multiple downstream workflows |
| Audit/security event | High replication, clear retention, DLT monitoring | Required for traceability and investigation |
| InventoryChanged | `acks=all`, keyed by product/warehouse, idempotent consumer | Requires accurate state and per-key ordering |
| Clickstream | Batching/compression, replication per data value | High volume, often has reconstructible sources |
| Periodic metrics | May prioritize throughput/short retention | Data can usually be re-aggregated |

If one topic carries multiple event types with different criticality levels, consider splitting topics or producer policies to avoid a compromise setting that fits none well.

## 20. Design and operations checklist

- [ ] Defined RPO: maximum acceptable record loss?
- [ ] Defined p95/p99 latency SLAs?
- [ ] Producer uses `acks` matching event criticality?
- [ ] Idempotence enabled where retry duplicates must be prevented?
- [ ] Replication factor and `min.insync.replicas` sized appropriately?
- [ ] Explicit policy for unclean leader election?
- [ ] Retries and delivery timeouts sensibly bounded?
- [ ] Batching/linger benchmarked with real payloads?
- [ ] Compression codec fits CPU/network budget?
- [ ] Producer buffer has backpressure?
- [ ] Consumer commits only after successful processing?
- [ ] `AckMode` aligns with duplicate window and commit cost?
- [ ] Concurrency does not exceed partition/downstream capacity?
- [ ] `max.poll.interval.ms` accommodates processing duration?
- [ ] Kafka transactions used only when atomic Kafka workflows are needed?
- [ ] Database side effects use outbox/inbox or idempotency?
- [ ] Metrics cover ISR, under-replicated partitions, lag, and commits?
- [ ] Failure tests executed across broker, producer, consumer, and transactions?
- [ ] Measured end-to-end latency, not just producer throughput?

## Conclusion

Durability and performance must be balanced around business requirements. For critical events, a common baseline is producer `acks=all`, idempotence enabled, topic replication factor 3, and `min.insync.replicas` 2; consumers process successfully before committing offsets, combined with idempotency to tolerate redelivery. Batching, linger, and compression can improve throughput while preserving these guarantees, provided latency, CPU, network, and memory are measured.

Kafka transactions support exactly-once for consume-process-produce flows within Kafka; they do not automatically cover external databases or side effects. Define RPO and latency SLAs first, tune each layer via benchmarks, and validate through failure testing. A good configuration meets business requirements both under normal operation and when brokers, networks, or consumers fail.

# Trade-offs Between Latency and Durability

In a Spring Kafka system, latency and data durability often jointly influence how an event travels from producer to consumer. To confirm a record more safely, the producer may have to wait for multiple replicas to acknowledge. To increase throughput, the producer may batch many records before sending. To avoid reprocessing data, the consumer may commit offsets after every record or after a batch. Each choice impacts response time, fault tolerance, throughput, and the amount of work that may need replay when an incident occurs.

The goal of reliable design is not minimizing latency at all costs or maximizing replication for every topic without examining load. You need to define acceptable data loss, business processing deadlines, the fault scope to tolerate, and latency budgets. Then choose producer, topic, broker, consumer, and transaction configurations suited to each event stream.

## 1. Distinguishing Latency, Throughput, and Durability

These three concepts are related, yet none can substitute for another:

- **Latency** is the time an operation or event takes to travel from a start milestone to an end milestone. In Kafka, you can measure producer send-and-ack time, time a record waits in a topic, listener processing time, or time from emission to business completion.
- **Throughput** is the amount of work a system processes per unit of time, such as records/sec or MB/sec. A high-throughput configuration can still have high p99 latency if records wait for batching or downstream processing.
- **Durability** is the ability of accepted data to survive and remain recoverable after failures within the design scope, such as a broker or disk failure. Durability depends on replication, ISR, producer acknowledgements, storage, and recovery procedures.

For example, a producer sending 10,000 records/sec can achieve high throughput through batching, yet the first record in a batch must wait slightly longer before transmission. Conversely, sending every record immediately can reduce producer wait time while increasing request counts, network overhead, and broker processing cost.

End-to-end latency should be viewed as the sum of time across multiple stages:

~~~text
Producer creates record
      |
      v
Wait in buffer / batching
      |
      v
Send request and wait for broker ack
      |
      v
Record resides in topic
      |
      v
Consumer polls and runs business logic
      |
      v
Commit offset
      |
      v
Business work is considered complete
~~~

Measuring only the `KafkaTemplate.send()` call without observing future completion, consumer wait time, and offset commit timing shows only part of latency. A system with a fast-responding producer can still have high end-to-end latency due to consumer lag or slow downstream dependencies.

## 2. Defining Latency Budgets and Acceptable Data Loss

Before choosing settings, answer two questions:

1. How quickly must an event finish processing for business logic to remain valid?
2. During broker or application failures, how many acknowledged events is the system allowed to lose?

Do not rely solely on an average latency number. Set targets for percentiles such as p50, p95, and p99. p50 reflects typical experience; p95 and p99 reveal the slow tail that users or downstream systems still encounter. A payment flow may require stricter p99 targets than an asynchronous telemetry collection flow.

Acceptable data loss should be described via RPO (Recovery Point Objective): the maximum amount of data or time window of data that can be lost in an incident scenario. Time to restore service is described by RTO (Recovery Time Objective). Replication and acknowledgements can reduce RPO for single-broker failures; they do not by themselves guarantee RTO if cluster, network, application, or operational procedures cannot recover.

| Stream type | Example | Common priorities |
|---|---|---|
| Critical transactions | Payment commands, balance changes, order confirmations | High durability, idempotency, reconciliation; latency must stay within SLA |
| Near-real-time business updates | Shipment status, inventory sync | Balance latency and durability; monitor lag and ordering |
| Telemetry and logs | Application metrics, technical logs, observability events | Throughput and cost often matter most; partial data loss may be acceptable depending on purpose |
| Ephemeral signals | Typing indicators, presence status | Low latency; stale data loses value quickly |

These are guiding tendencies, not rigid rules. Some telemetry used for auditing also demands high durability; some transactional events can be processed asynchronously while still preserving data.

## 3. Producer Acknowledgement: Acknowledgement Speed vs. Durability

Kafka producers have three basic options for `acks`:

| `acks` | When does the producer receive an ack? | Consequence |
|---|---|---|
| `0` | Producer does not wait for broker acknowledgement | Low producer-side latency, yet no confirmation whether the broker received the record; highest risk of data loss |
| `1` | Leader acknowledges after writing the record to the leader's local log | Usually faster than waiting for the whole ISR; if the leader fails before other replicas receive the record, the record can be lost |
| `all` | Leader waits for replicas currently in the ISR to acknowledge | Better protection against replica failures; latency and write availability depend on ISR state |

`acks=all` does not mean waiting for every replica ever configured for the partition, including disconnected ones. It waits for replicas currently in the In-Sync Replica Set (ISR). Therefore, `acks=all` must be paired with an appropriate replication factor and `min.insync.replicas`.

Example topic with replication factor 3 and `min.insync.replicas=2`:

- When the ISR has 3 replicas, writes with `acks=all` require acknowledgements from the replicas in the ISR.
- When one replica fails and the ISR drops to 2, the producer can still write if both replicas acknowledge.
- When the ISR drops to 1, the broker rejects writes per the minimum requirement. The producer receives an error and can retry per configuration.

Rejecting writes when the ISR is insufficient is a deliberate choice protecting durability. If the system lowers acknowledgement requirements automatically to keep accepting writes, it can turn an availability incident into silent data loss at the business layer.

### 3.1. Example Durability-Focused Producer Configuration

For critical events, a Spring Boot configuration can start from:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Timeouts and retry counts in this example should be tuned to SLAs, Kafka client version, and cluster capacity. `delivery.timeout.ms` caps total time the producer tries to deliver a record; a huge retry count does not mean infinite retries.

`enable.idempotence=true` prevents the producer from creating duplicates due to retries within its producer session and helps preserve ordering under compatible settings. Idempotence is usually right for critical streams because it lowers duplicate risk from retries without forcing the application to disable other performance optimizations.

### 3.2. Do Not Equate send() with Successful Acknowledgement

In Spring Kafka 3.x, `KafkaTemplate.send()` returns a `CompletableFuture`. Receiving the future only indicates the asynchronous send was initiated; observe completion results:

~~~java
CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, error) -> {
    if (error != null) {
        log.error("Publish failed, orderId={}", orderId, error);
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.debug("Publish acknowledged: topic={}, partition={}, offset={}",
            metadata.topic(), metadata.partition(), metadata.offset());
});
~~~

If a business API only returns success after the broker acknowledges the record, coordinate the future result with the request flow and timeout budget. Avoid unbounded thread blocking. If business logic already committed the database while Kafka send failed, or the outcome is ambiguous due to a timeout, you need an outbox and stable event ID for safe replay.

## 4. Replication and min.insync.replicas

Replication creates multiple copies of partitions across different brokers. When a leader fails, an eligible replica can be elected as the new leader. A higher replication factor increases redundancy, while also increasing storage usage, replication traffic, and resource cost.

`min.insync.replicas` sets the minimum number of synchronized replicas required for the broker to accept writes when producers use `acks=all`. This draws a clear boundary between write availability and required data safety.

Common design example for critical topics:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
unclean.leader.election.enable = false
~~~

This design can typically continue accepting writes when one replica fails, as long as at least two replicas remain in the ISR. If the ISR drops below two, writes are rejected to protect required replication levels. Do not apply this blindly if a cluster has only two brokers, brokers share one failure domain, or replication cost exceeds system capacity.

Placing replicas across distinct brokers or racks/zones reduces the risk of one physical fault losing multiple copies at once. Rack awareness is effective only when broker rack metadata accurately reflects infrastructure topology.

### 4.1. Durability Has Operational Costs

Replication does not only add acknowledgement time. It also consumes network bandwidth, disk capacity, I/O, and CPU. When a broker returns after an outage, replica catch-up can compete for resources with normal traffic. Monitor:

- Under-replicated partitions and offline partitions.
- ISR shrinks/expands and replica catch-up duration.
- Broker network throughput, disk utilization, and request latency.
- Leader election counts and recovery time after broker restarts.

Kafka typically relies on the OS page cache and replication for high write performance; do not assume every acknowledgement equals a synchronous fsync to storage media for each individual record. Base RPO assessments on Kafka semantics, broker settings, replication, and actual storage characteristics.

## 5. Batching, Linger, and Compression

Producers can group multiple records for the same partition into a batch. Sending batches reduces request counts, uses network and brokers more efficiently, and can boost throughput. In return, records may wait slightly longer before the batch is dispatched.

Key settings:

| Setting | Impact on latency | Impact on throughput and resources |
|---|---|---|
| `linger.ms` | Adds intentional wait time when a batch is not yet full | Can form larger batches and reduce request overhead |
| `batch.size` | Larger batches may take longer to fill | Increases batching efficiency while consuming more memory |
| `compression.type` | Can add CPU cost for compression/decompression | Reduces bytes transferred and stored; effectiveness varies with data |
| `buffer.memory` | Insufficient buffer can cause sends to block or fail on timeout | Determines how much data the producer can queue when brokers slow down |

### 5.1. Choosing Linger by Traffic Characteristics

For low-rate streams needing fast response, a small `linger.ms` limits batching wait time. For high-volume streams, raising linger modestly can build fuller batches without breaching SLAs.

Balanced configuration example:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[linger.ms]": 5
        "[batch.size]": 32768
        "[compression.type]": lz4
~~~

This is only a baseline for benchmarking. `linger.ms=5` does not guarantee every record always waits exactly 5 ms; batches can ship earlier when full or under other send conditions. Actual efficiency depends on partition count, key distribution, record size, and send rate.

### 5.2. Choosing Compression

Compression reduces bytes crossing the network and written to logs, especially when records in a batch share repetitive structure. In return, producers and brokers/consumers may spend CPU compressing and decompressing.

- `lz4` is often considered when minimizing CPU overhead while keeping high speed.
- `zstd` can achieve strong compression ratios, though CPU and latency should be benchmarked.
- `snappy` is a balanced option across many workloads.
- `gzip` can compress tightly but usually costs more CPU.

No single codec is best for every payload. Already-compressed, encrypted, or high-entropy data may not shrink noticeably. Measure network bytes, CPU, batch size, and p99 before switching codecs.

## 6. Consumer Acknowledgement and Offset Commit Timing

Consumers also introduce a latency/durability trade-off. The sooner offsets are committed, the faster reported lag drops, yet committing before business work completes risks skipping records after a crash. Committing after successful processing means records can be redelivered if the consumer dies before commit; thus business logic must tolerate duplicates.

With Spring Kafka, `enable.auto.commit=false` is commonly used so the listener container manages commits. Common acknowledgement modes:

| Ack mode | When does commit happen? | Characteristics |
|---|---|---|
| `RECORD` | After the listener processes each record successfully | Easy to tie commit timing to each record's outcome; may increase commit count |
| `BATCH` | After all records in a poll batch succeed | Reduces commit overhead; on error, unconfirmed portions of the batch may reprocess |
| `TIME` / `COUNT` / `COUNT_TIME` | When time, record count, or either threshold is reached | Balances commit overhead against how many records could be replayed |
| `MANUAL` / `MANUAL_IMMEDIATE` | Driven by application-controlled acknowledgements | Flexible, but requires calling ack at the right time and understanding container semantics |

Example listener configuration managing offsets per batch:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        "[max.poll.records]": 100
    listener:
      ack-mode: batch
~~~

Larger batches can raise throughput and cut commit overhead, yet batch processing takes longer, more records may replay after failures, and the consumer must still call `poll()` on time. Smaller batches narrow the scope of in-flight work while potentially raising overhead.

### 6.1. Never Commit Before Business Effects Are Durable

Suppose a consumer receives `OrderPaid`, updates a database, and commits the offset:

1. If the database commit succeeds and the consumer dies before Kafka commits the offset, the record can be redelivered. The consumer must be idempotent.
2. If Kafka commits the offset first and the database transaction fails, the record may not be redelivered even though business logic never completed. This risks losing business effects.

Therefore, for normal database processing, finish the database transaction before the listener returns normally or calls ack. For stronger guarantees, use an inbox table with an event ID and unique constraint in the same database transaction as business updates.

### 6.2. Synchronous and Asynchronous Commits

Spring Kafka listener containers can usually commit offsets synchronously or asynchronously depending on `syncCommits`. Synchronous commits wait for broker responses, making commit errors easy to spot immediately while adding a network round trip on the processing path. Asynchronous commits can reduce wait time, yet delayed commit results or commit errors must be observed and handled carefully.

Do not switch to asynchronous commits merely to shave a few milliseconds off latency without measuring how much budget commits actually consume. Monitor commit latency, commit failures, and the number of records potentially replayed on consumer shutdown.

## 7. Batch Size, Poll Interval, and Consumer Lag

`max.poll.records` caps how many records are returned in one poll. High values can lower poll overhead and improve batch efficiency, yet the listener needs more time to finish the batch. If the interval between polls exceeds `max.poll.interval.ms`, the consumer may leave the group and trigger partition reassignment.

Choose batch size based on real processing time:

~~~text
Batch processing time
  = number of records in batch
    x average processing time per record
    + batch overhead
~~~

This is a simple estimate; processing-time distributions, concurrency, and downstream calls can push p99 far above the mean. When records have uneven processing times, a large batch can be dominated by a single slow record.

Consumer lag shows the gap between the offset confirmed by a consumer group and the latest offset in a partition. Continuously growing lag usually indicates production exceeds processing speed or consumers are blocked. Decreasing lag does not necessarily prove business work succeeded if the application committed offsets prematurely.

Also monitor the age of the oldest unprocessed record. Two groups with identical lag counts under different production rates can have vastly different actual time delays. A 10,000-record backlog might clear in seconds on a high-throughput stream, yet represent hours on a low-volume stream.

## 8. Transactions and the Cost of Exactly-Once in Kafka

Kafka transactions allow writing multiple records and input offsets within a single Kafka transaction. For consume-transform-produce, Spring Kafka can coordinate transactions so outputs and offsets commit atomically. Consumers using `isolation.level=read_committed` read only records from committed transactions.

Transactions add coordination and commit steps, so they typically carry higher latency cost than non-transactional produce/consume flows. Transaction timeouts, processing time, and record counts per transaction must be bounded. Long-running transactions can force `read_committed` consumers to wait at the tail of the log until the transaction finishes.

When configuring a transactional producer, ensure a unique transaction ID prefix across application instances. Duplicate prefix settings or improper transactional producer lifecycles can trigger fencing errors or transaction initialization failures.

Use Kafka transactions only when atomic semantics for Kafka data are needed, such as transforming one input record into multiple output records where the input offset must commit alongside outputs. If a flow only emits one event and a consumer updates a database, a Kafka transaction does not automatically create a distributed transaction with the database.

### 8.1. Outbox and Inbox for Database-Involved Flows

Transactional outbox writes business changes and the event to emit into the same database transaction. A publisher reads the outbox and sends events to Kafka. Sending can repeat if the publisher fails after the broker receives the record but before the database marks it sent; hence consumers need idempotency.

An inbox on the consumer records the event ID and applies business updates in the same database transaction. When a record is redelivered, a unique constraint detects the already-processed event and blocks duplicate side effects.

Outbox/inbox can add latency due to extra database writes/reads and publisher polling or CDC. In return, it establishes a clear recovery mechanism between the database and Kafka without assuming both systems share a single atomic transaction.

## 9. Retention and Durability Over Time

Replication protects against certain broker failures; retention governs how long records remain available for consumers to reread or recover after outages.

`retention.ms` and `retention.bytes` bound the time or log size kept on a topic. Overly short retention can cause a consumer stopped longer than the retention window to lose access to older data. Longer retention increases disk demand and can affect broker costs.

With `compact` topics, Kafka retains the latest value per key per compaction policy; compaction is not a complete backup of every event version. If business logic requires historical auditing, never treat a compacted topic as a store of every mutation.

DLTs and retry topics also need appropriate retention. Failed records must remain long enough for investigation and replay, yet should not be kept indefinitely without security, capacity, and cleanup policies.

## 10. Multi-Region and Limits of Durability

Replication inside a single Kafka cluster usually protects data against broker failures within that cluster and configured topology. It does not automatically protect against losing an entire region, wide-reaching administrative mistakes, or incidents cutting off access to the whole cluster.

Cross-region data replication usually incurs latency and is often asynchronous. This creates a window where data is acknowledged in the source region yet not yet replicated to the standby region. If the source region is lost completely during that window, RPO can exceed 0.

When designing disaster recovery, define:

- Which region is the primary writer and how write ownership fails over.
- Inter-region replication lag and acceptable RPO.
- How to prevent two regions from accepting conflicting writes unintentionally.
- How to migrate consumer groups, offsets, and schemas/configs to the standby environment.
- Reconciliation procedures for missing or doubly processed records after failover.

Increasing cross-region durability usually increases latency, network cost, and operational complexity. Choose synchronous cross-region acknowledgements only when SLAs truly demand them and infrastructure can sustain that latency.

## 11. Measuring to Find the Balance Point

Do not tune multiple parameters simultaneously and draw conclusions from a single benchmark run. Change one group at a time, hold load and test data steady, and compare latency, throughput, and failure behavior together.

| Component | Metrics to measure | Question |
|---|---|---|
| Producer | Send latency p50/p95/p99, error rate, retry rate, batch size, compression rate, buffer wait | Is waiting on brokers, batching, or buffers taking the time? |
| Broker | Produce request latency, ISR, under-replicated partitions, disk/network utilization | Are replication or broker resources creating a bottleneck? |
| Consumer | Poll interval, processing duration, commit latency, lag, and oldest record age | Is delay in polling, processing, committing, or backlog? |
| Transaction | Transaction duration, abort rate, timeouts, and fencing errors | Are transactions too long or failing frequently? |
| Business | Time from event creation to business completion, duplicates, and missing events | Did technical tuning actually improve business outcomes? |

Measure across multiple conditions:

1. Low baseline load to observe `linger.ms` and batching effects when records are sparse.
2. Normal load to measure latency and throughput under expected conditions.
3. Peak load to find CPU, network, disk, and consumer concurrency limits.
4. Broker losing one replica to verify `acks=all` and `min.insync.replicas` behavior.
5. Consumer downtime or slow downstream to observe lag, retries, and recovery duration.
6. Backlog replay to learn how quickly the system catches up to live traffic.

Benchmark results are meaningful only when failure tests are included. A configuration achieving low p99 under normal conditions yet losing records during a broker fault fails durability requirements for critical streams.

## 12. Reference Configurations by Goal

### 12.1. Latency-Prioritized Streams

For reconstructible data or data tolerating partial loss, consider:

- Low `linger.ms` to limit batching wait.
- Batch size and compression tuned to record size and load.
- `acks=1` only when business logic accepts record loss risk if the leader fails before replicas receive the data.
- Consumer processing smaller batches if fast per-event response is required.
- Retention and replay capability still sufficient for committed recovery targets.

Do not default to `acks=0` for every real-time stream. The producer receives no confirmation from brokers, making it hard to tell whether records ever arrived; low latency at the producer API does not prove events reached the system.

### 12.2. Durability-Prioritized Streams

For transactional events or non-reconstructible data:

- Topic has an appropriate replication factor with replicas spread across fault domains.
- `min.insync.replicas` set to the minimum acceptable replica count.
- Producer uses `acks=all` and idempotence.
- Consumer commits after business effects are durable.
- Consumer uses inbox/deduplication or idempotency keys.
- Retention is long enough for expected recovery windows.
- DLT, outbox, or appropriate replay and reconciliation mechanisms exist.

Modestly higher latency can be a reasonable price for lower RPO. Verify whether p99 still meets SLAs instead of assuming high durability always prevents meeting real-time goals.

### 12.3. Throughput-Prioritized Streams

For high-volume streams:

- Use batching and compression after benchmarking.
- Choose partition counts and keys to distribute load evenly.
- Use consumer batch processing if business logic allows.
- Avoid overly frequent offset commits when commit overhead is significant, while bounding how many records may replay.
- Set buffer, retry, and poll limits to avoid memory buildup or overwhelming downstream systems.

High throughput must go hand in hand with backlog control. If a system runs fast in short bursts yet cannot catch up after an outage, recovery goals are still unmet.

## 13. Decision Workflow When Latency Spikes

When p95 or p99 rises, do not immediately lower `acks` or `min.insync.replicas`. Identify which stage introduces the delay:

1. If producer send latency rises, inspect broker request latency, ISR, retries, buffer wait, and network.
2. If batch wait rises, review `linger.ms`, per-partition traffic, and batch size.
3. If broker latency rises, check disk, network, request queues, and replica catch-up.
4. If the producer is fast yet end-to-end is slow, check consumer lag, poll intervals, listener duration, and downstream dependencies.
5. If commit latency is high, evaluate commit frequency and consider ack modes or sync commits after measuring potential replay volume.
6. If transactions run long, shorten processing inside transactions or split work along proper business boundaries.
7. After changes, rerun benchmarks and failure tests to ensure latency gains do not degrade durability beyond acceptable limits.

## 14. Configuration Selection Checklist

### Before choosing producer settings

- [ ] Defined RPO and latency SLAs for the event stream.
- [ ] Decided `acks` level based on the impact of losing a record.
- [ ] Aligned replication factor and `min.insync.replicas` with topology.
- [ ] Enabled idempotence when producer retries can create duplicates.
- [ ] Aligned `delivery.timeout.ms` with business time budgets.
- [ ] Benchmarked `linger.ms`, `batch.size`, and compression.

### Before choosing consumer settings

- [ ] Disabled auto commit if the listener container manages offsets.
- [ ] Aligned ack mode with when business work actually completes.
- [ ] Ensured database commits occur before offsets are confirmed.
- [ ] Made consumers idempotent when records can be redelivered.
- [ ] Matched batch size and `max.poll.interval.ms` to processing time.
- [ ] Monitored commit latency and consumer lag.

### Before going to production

- [ ] Tested losing one broker replica and verified write behavior matches design.
- [ ] Tested stopping the consumer between processing and offset commit.
- [ ] Measured p50/p95/p99 at baseline, normal, and peak loads.
- [ ] Determined backlog recovery time after an outage.
- [ ] Verified retention suffices for recovery and replay windows.
- [ ] Configured alerts for ISR, under-replicated partitions, lag, and producer errors.
- [ ] Documented a runbook explaining how to handle write availability vs. durability trade-offs.

## Conclusion

Latency and durability must be balanced according to the value of each event type. `acks=all`, replication, and `min.insync.replicas` determine producer-side acknowledgement strength; batching and compression shape send efficiency; ack mode, polling, and commits decide when consumers confirm processing; transactions and outbox/inbox handle consistency boundaries between Kafka and other systems. Measuring end-to-end latency, throughput, lag, and failure behavior reveals the real balance point. A good configuration meets SLAs within committed RPO and recovers cleanly using verified procedures.

# Consumer lag and consumption rate

In a Spring Kafka system, seeing that a consumer is still running is not enough to conclude the pipeline is healthy. A listener may continuously process records yet fail to keep up with producer speed, causing **consumer lag** to climb steadily. Conversely, zero lag does not guarantee all business side effects are complete: records may be routed to a retry topic, processed asynchronously, or have offsets committed before work is truly durable.

Two quantities that must be observed together are **consumer lag**—how far behind a consumer group is relative to available data—and **consumption/processing rate**—how many records a consumer receives or completes per unit time. Combining them with record age, errors, retries, publish rate, and offset commit status is what lets you judge whether the system is catching up, accumulating backlog, or stuck.

This lesson covers how to understand offsets and lag per partition, the difference between records consumed and records processed, backlog calculations, Kafka client and Spring Kafka metrics, CLI tools for inspecting consumer groups, dashboard/alert design, effects of retries and transactions, capacity planning, and operational runbooks.

## 1. What is consumer lag?

Kafka divides each topic into partitions, where each partition is an append-only log with monotonically increasing offsets. A **consumer group** stores a committed offset for each topic-partition it consumes. The committed offset normally represents the **next position** the group will read when resuming from confirmed state, not the last processed offset minus one.

A common calculation when comparing group offsets and end offsets:

~~~text
lag(group, topic, partition)
    = logEndOffset(topic, partition)
      - committedOffset(group, topic, partition)
~~~

Example:

~~~text
Partition orders.events-0

Log positions:
... 4997 | 4998 | 4999 | 5000 | 5001 | 5002 | 5003 | ...

Group committed offset = 5000
Log end offset         = 5004  (next position after the last record)

Offset lag = 5004 - 5000 = 4
~~~

This result reflects the distance between two offset positions. In ordinary Kafka topics it is close to the number of records remaining to advance through, though **not always identical to unprocessed business events** because the log can contain transaction markers, aborted records, compaction gaps, and semantic differences across measurement tools.

### 1.1. Lag is per group and partition

Lag is not a single property of a topic. On the same topic, two consumer groups can be at completely different positions:

| Consumer group | Committed offset | End offset | Lag |
|---|---:|---:|---:|
| `billing-group` | 8,900 | 10,000 | 1,100 |
| `analytics-group` | 9,950 | 10,000 | 50 |
| `audit-group` | 10,000 | 10,000 | 0 |

To determine whether a service is lagging, filter by the **exact consumer group**, topic, and partition. Never use one group's lag to infer another group's health.

### 1.2. Topics with multiple partitions

Suppose `orders.events` has three partitions:

| Partition | Committed offset | Log end offset | Lag |
|---|---:|---:|---:|
| 0 | 13,000 | 13,100 | 100 |
| 1 | 6,200 | 7,200 | 1,000 |
| 2 | 4,500 | 4,520 | 20 |
| **Total** | | | **1,120** |

The **total group lag** across these partitions is the sum of lags, here 1,120 offset positions. Yet the **maximum partition lag** is 1,000 on partition 1; this may be a hot partition requiring investigation. A dashboard showing only the total easily hides imbalance across partitions.

## 2. Commonly confused offset positions

In operations, distinguish at least these terms:

| Concept | Meaning |
|---|---|
| Log start offset | Earliest position still retained by Kafka per retention/compaction |
| Log end offset (LEO) | Next position after the last data written to the log as defined by Kafka |
| Consumer position | Next position `KafkaConsumer` expects to fetch when continuing |
| Committed offset | Position durably confirmed by the consumer group |
| Last stable offset (LSO) | Safe read boundary for `read_committed` consumers when open transactions exist |

They are not necessarily equal.

### 2.1. Position can advance ahead of successful processing

Kafka `poll()` fetches a batch of records and advances the consumer's fetch position. If the listener receives the batch and processes slowly, **consumer position may already advance** while the committed offset remains behind.

~~~text
Log end offset:  1,100
Consumer poll() received up to offset 1,049
Consumer position: 1,050
Group committed offset: 1,000

Fetch-position lag   ≈ 1,100 - 1,050 = 50
Committed-offset lag = 1,100 - 1,000 = 100
~~~

Both quantities are valid yet answer different questions:

- **Fetch lag:** how far has the consumer fetched?
- **Committed lag:** how far has the group durably confirmed?

If the application processes asynchronously or commits in batches, the gap can be large. Do not assume Kafka client `records-lag-max` and lag computed by an exporter from group committed offsets are always equal.

### 2.2. Committed offset does not prove side effects finished

If a listener enqueues an async task and returns success, the container can commit the offset before the worker finishes. Dashboards may then show lag dropping cleanly while the database remains un-updated.

Therefore, track **business processing completed rate** or pending task counts when using async workflows. Some Kafka consumers read faster than actual processing capacity, keeping Kafka lag low while shifting the backlog into an internal queue.

### 2.3. Retention and vanished data

If a consumer group falls too far behind and Kafka retention deletes records before the group consumes them, the committed offset may sit behind the log start offset. A simple lag subtraction then fails to show **how many events are permanently unreadable**.

Inspect log start offset, committed offset, retention, and `auto.offset.reset` policy together. Never reset a group offset to `latest` just to zero out lag unless business stakeholders approve skipping data.

## 3. Lag when using Kafka transactions

Consumers with `isolation.level=read_committed` skip records from aborted transactions; reading is also bounded by the **last stable offset (LSO)** when an open transaction exists.

Depending on the exporter and how it queries end offsets, lag may be measured against:

- Log end offset / high watermark, reflecting data stored on the broker.
- Last stable offset for `read_committed` visibility.

These two methods yield different lag values while a long-running transaction is open.

~~~text
LEO = 5,500
LSO = 5,400  (open transaction)
Committed offset = 5,350

By LEO: 5,500 - 5,350 = 150
By LSO: 5,400 - 5,350 = 50
~~~

Neither measurement is inherently "wrong" if clearly defined. When comparing dashboards from two exporters, know which **end-offset reference** each uses.

### 3.1. Open transactions can make lag appear stuck

A long-lived open transaction prevents `read_committed` consumers from reading records past the LSO, even while network, threads, and the consumer group remain healthy.

When suspected, check:

1. Are transactional producers holding transactions open too long?
2. Are producers failing to commit/abort?
3. Is downstream using `read_committed` or `read_uncommitted`?
4. Does the lag metric use LEO or LSO?
5. Is the consumer processing available records up to the LSO?

Do not switch immediately to `read_uncommitted` just to "reduce lag," as consumers would read output from aborted transactions.

## 4. What rates make up consumption rate?

In a Kafka pipeline, there are at least four distinct rates:

| Rate | Typical unit | What it actually measures |
|---|---|---|
| Producer arrival rate | records/s, bytes/s | Records written to Kafka from upstream |
| Consumer fetched/consumed rate | records/s, bytes/s | Records read by Kafka consumer via poll/fetch |
| Listener invocation rate | calls/s | Number of times the listener method is called |
| Business success throughput | events/s | Events completing business processing as defined by the app |

A listener may receive 1,000 records/s yet complete business processing for only 700 records/s; the remainder may fail, move to a retry topic, or stay queued.

### 4.1. Kafka client records-consumed-rate

Kafka consumers expose metrics such as `records-consumed-rate`, `bytes-consumed-rate`, `records-lag-max`, and fetch metrics, depending on Kafka client version. They show consumer-layer activity, not necessarily **successful database commits** or **completed business events**.

Do not name a custom metric `business_success_rate` for Kafka client `records-consumed-rate`. The two semantics differ and belong in separate series.

### 4.2. Listener invocation rate differs from batch record count

For a record listener, one call typically corresponds to one record delivered to the adapter. For a batch listener, one call can contain hundreds of records:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing",
        containerFactory = "batchFactory")
public void consume(List<OrderEvent> events) {
    orderService.processBatch(events);
}
~~~

If the method is called 10 times/s with an average batch size of 200, the invocation rate is 10 calls/s while the record delivery rate is around 2,000 records/s. Do not compute record throughput from batch listener method call counts alone.

### 4.3. Errors and retries inflate attempt rate

An event may be processed multiple times by the listener during retries. Counting listener calls can rise even when unique completed business events do not increase.

To evaluate real progress, measure separately:

- Processing attempts count.
- Business successes count.
- Business permanent failures count.
- Retry/DLT rate.
- Unique completed event IDs if the system has an appropriate store.

Never use event ID as a metric tag due to excessive cardinality; for deduplication use a database/inbox or workflow state.

## 5. Relationship between input, throughput, and lag

A simple model:

~~~text
L(t + Δt) ≈ max(0, L(t) + A(Δt) - C(Δt))

L = backlog in corresponding record/offset units
A = newly arrived data
C = data completed/committed by the consumer
~~~

When expressed in records/s over a time window:

~~~text
Net backlog growth rate ≈ producer arrival rate
                          - effective consumer completion rate
~~~

Suppose:

- Producer sends 500 records/s.
- Consumer effectively completes and commits 400 records/s.

At steady rates, backlog grows by roughly 100 records/s. After 10 minutes, backlog rises by nearly 60,000 records. This is an estimate: actual numbers are affected by batch commits, transactions, compaction, filtering, retries, and traffic fluctuations.

### 5.1. High consumption rate is not automatically healthy

If a producer writes 2,000 records/s and the consumer processes 1,500 records/s, a throughput of 1,500 records/s sounds large yet lag **still increases**.

Conversely, if the producer writes only 100 records/s and the consumer processes 150 records/s, existing backlog is shrinking.

Never judge a consumer by a standalone records/s figure; place it beside **upstream rate** and **lag trend**.

### 5.2. Falling lag does not guarantee business completion

If errors are published to a retry topic, the main topic offset may commit and main topic lag drops. Yet the event has not completed business processing—it merely moved to another queue. Similarly, the DLT can hold events awaiting investigation.

For workflows with retry topics/outboxes/worker queues, aggregate status across the full processing path rather than watching main topic lag alone.

## 6. Estimating time to catch up on backlog

When effective consumer capacity exceeds producer rate, you can estimate how long it takes to drain the backlog:

~~~text
Time to catch up ≈ Current backlog
                   / (Consumer capacity - Producer arrival rate)

Condition: Consumer capacity > Producer arrival rate.
~~~

Example:

- Current backlog: 10,000 records.
- Producer continues sending 200 records/s.
- Consumer effectively processes 250 records/s.
- Net backlog drain capacity: 50 records/s.

Then estimated catch-up time:

~~~text
10,000 / (250 - 200) = 200 seconds
~~~

About 3 minutes 20 seconds is an estimate assuming stable input rates and throughput. In production, rates vary by time of day, record size, partition distribution, and dependency health.

### 6.1. When capacity is equal to or lower than input rate

If:

~~~text
Consumer capacity <= Producer arrival rate
~~~

backlog **cannot steadily shrink** under this simple model. Raising timeouts or restarting consumers does not fix a capacity deficit. You must optimize processing, reduce work per record, adjust partitions/concurrency, or scale resources appropriately.

### 6.2. Do not let total throughput hide a hot partition

Suppose each partition has an arrival and completion rate:

| Partition | Incoming | Completed | Backlog change |
|---|---:|---:|---:|
| 0 | 80/s | 100/s | Shrinks 20/s |
| 1 | 200/s | 140/s | **Grows 60/s** |
| 2 | 20/s | 50/s | Shrinks 30/s |

Total backlog might grow net by only 10/s, yet partition 1 grows by 60/s. If events require per-key ordering and partition 1 has a hot key, simply adding consumers to the same group will not allow a single partition to be processed concurrently by multiple consumers.

Inspect key distribution, partition count, per-key processing cost, and stateful ordering contracts.

## 7. Record-count lag vs. time-based lag

A backlog of 10,000 records could mean:

- About 10 seconds of data in a pipeline processing 1,000 records/s.
- About 3 hours of data in a pipeline processing under 1 record/s.

Record count alone does not express business delay. Also measure:

- **Oldest unprocessed record age:** age of the oldest waiting event.
- **End-to-end processing latency:** time from event creation until business side effects finish.
- **Event-time delay:** difference between source event time and processing time, if a reliable business timestamp exists.
- **Time to first success after incident:** recovery time during an outage.

### 7.1. Kafka timestamps are not always business event time

A Kafka record timestamp can be producer-supplied `CreateTime` or broker-assigned `LogAppendTime`, depending on topic configuration. The business event timestamp inside the payload can differ further because events may be created before being sent to Kafka.

When computing end-to-end latency, document which timestamp is used. Do not treat clocks on unsynchronized producer machines as ground truth without checking clock skew.

### 7.2. Consumer group lag is 0 yet events are stale

A record arriving in Kafka after sitting in an upstream outbox for 30 minutes can be processed immediately by the consumer, keeping Kafka lag near 0. However, business delay measured from event creation is still 30 minutes.

Combine Kafka lag with upstream outbox age and business event age if SLOs require fresh data.

## 8. Checking lag with Kafka CLI

Kafka provides `kafka-consumer-groups.sh` to inspect consumer group status. Example:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-group
~~~

On Windows, use the script matching your Kafka installation or run from a shell environment with the Kafka CLI. Folder names and paths vary by distribution.

Illustrative output:

~~~text
GROUP         TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
billing-group orders.events  0          13000           13100           100  consumer-a
billing-group orders.events  1          6200            7200           1000  consumer-b
billing-group orders.events  2          4500            4520             20  consumer-c
~~~

Numbers above are examples, not data from a live cluster.

### 8.1. Reading the columns accurately

- `GROUP`: consumer group ID.
- `TOPIC` and `PARTITION`: specific log.
- `CURRENT-OFFSET`: committed offset stored by the group.
- `LOG-END-OFFSET`: end offset retrieved by the tool at measurement time.
- `LAG`: gap calculated by the tool from end offset and group offset.
- `CONSUMER-ID`, `HOST`, `CLIENT-ID` (if present): assigned member/instance.

If `CURRENT-OFFSET` or consumer ID displays `-`, do not interpret it as zero. The group may have no committed offset yet, no active members, or unassigned partitions as presented by the tool. Check group state and offset reset policy.

### 8.2. Checking group state

In Kafka CLI versions that support it:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-group \
  --state
~~~

The group may be `Stable`, `PreparingRebalance`, `CompletingRebalance`, or have no members, depending on group protocol version. Do not conclude from lag alone that the group has live consumers; check membership/assignments and service logs.

### 8.3. Multiple samples over time are needed

A single CLI snapshot gives only **current lag**. To tell whether backlog is growing or shrinking, you need multiple timestamped samples across clear intervals. In production, use an exporter/metrics system rather than polling CLI commands at high frequency.

### 8.4. Never reset offsets just to clean up dashboards

Commands that alter group offsets can skip records or trigger massive replays. If lag is high, investigate root cause and capacity first. Resetting offsets requires a runbook, verification of affected data, and proper approval.

## 9. Related Kafka client metrics

The Java Kafka consumer client exposes numerous metrics via JMX and metrics APIs. Exact MBean or field names vary by Kafka client version, though the following groups are typically very useful.

| Common metric | Layer | Interpretation |
|---|---|---|
| `records-consumed-rate` | Kafka consumer fetch manager | Rate of records received by consumer |
| `bytes-consumed-rate` | Consumer fetch manager | Byte throughput |
| `records-lag-max` | Consumer fetch manager | Highest fetch lag observed by consumer across partitions |
| `records-lag` or per-partition metrics | Consumer fetch manager | Per-partition lag within client scope |
| `fetch-rate` | Consumer fetch manager | Frequency of fetch requests |
| `fetch-latency-avg` / `fetch-latency-max` | Consumer fetch manager | Fetch latency |
| `poll-idle-ratio-avg` | Consumer metrics in supported versions | Fraction of time the poll thread spends idle between polls |
| `commit-rate` and commit latency | Consumer coordinator | Offset commit activity and latency |
| Rebalance-related metrics | Consumer coordinator | Frequency/duration of group rebalances |

### 9.1. Client lag and group committed lag differ

The Kafka client metric `records-lag-max` relates to fetch/consumer position, whereas consumer group lag from an exporter is typically computed from committed group offsets. Especially with batching, manual acks, or transactions, they do not necessarily match.

Name panels distinctly, for example:

- "**Fetch lag max per consumer**".
- "**Committed offset lag by group/partition**".

Do not merge both metrics into one series labeled "lag" without stating the definition.

### 9.2. Interpreting metrics across multiple consumers

A group has multiple consumers, each with its own `client.id` assigned a subset of partitions. Summing every `records-lag-max` does not equal total group lag.

For total backlog, use committed offsets per partition. To detect which consumer is stalled on fetches, use client lag max along with client ID/assigned partitions.

## 10. Spring Kafka listener metrics

Kafka client metrics alone are not enough to verify that a listener processed business logic successfully. Spring Kafka supports Micrometer metrics/observation for listener containers in appropriate versions, and applications can add custom metrics.

Signals to capture:

1. Listener invocation duration.
2. Listener processing attempt count.
3. Business success count.
4. Business failure count classified by stable exception groups.
5. Retry count and recovery/DLT rate.
6. Records currently in-flight or waiting in internal queues.
7. Database commit or downstream dependency duration.

### 10.1. Do not equate listener invocation with success

Example:

~~~java
@KafkaListener(
        topics = "orders.events",
        groupId = "billing-group")
public void consume(OrderEvent event) {
    billingService.processIdempotently(event);
}
~~~

Method call count includes retries. A method returning normally could be processing a new event or deduplicating an already-processed record. Therefore, agree on what "success" means:

- Success = listener threw no exception.
- Success = database transaction committed.
- Success = unique business event completed for the first time.

Each metric answers a different question. In reliability dashboards, include **truly durable processing throughput** per business contract, not invocations alone.

## 11. Example: instrumenting business success/failure with Micrometer

Example using `MeterRegistry` to distinguish completed events from failed attempts:

~~~java
@Component
public class OrdersListener {

    private final OrdersService orderService;
    private final Counter successes;
    private final Counter failures;
    private final Timer processingTimer;

    public OrdersListener(
            OrderService orderService,
            MeterRegistry meterRegistry) {
        this.orderService = orderService;

        this.successes = Counter.builder(
                "app.kafka.orders.processing.success")
                .description("Successfully processed Kafka orders")
                .register(meterRegistry);

        this.failures = Counter.builder(
                "app.kafka.orders.processing.failure")
                .description("Failed Kafka order processing attempts")
                .register(meterRegistry);

        this.processingTimer = Timer.builder(
                "app.kafka.orders.processing.duration")
                .description("Order listener processing duration")
                .register(meterRegistry);
    }

    @KafkaListener(
            topics = "orders.events",
            groupId = "billing-group")
    public void consume(OrderEvent event) {
        long started = System.nanoTime();

        try {
            orderService.processIdempotently(event);
            successes.increment();
        }
        catch (RuntimeException ex) {
            failures.increment();
            throw ex; // Preserve exception for Spring Kafka error handler.
        }
        finally {
            processingTimer.record(
                    System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
        }
    }
}
~~~

This snippet assumes `OrderService`, Micrometer, and imports are configured. The `successes` counter here counts **listener invocations completing normally**; it does not deduplicate unique event IDs automatically. If `processIdempotently` returns normally because the record was previously processed, the counter still increments. To track unique completed events, have the business API return an appropriate outcome or track event state in the database.

### 11.1. Never swallow errors just to increment a failure metric

If the listener catches an exception and returns normally, Spring Kafka may commit/ack the record per policy even though business work failed. Measuring failures must not break error-handling semantics. Record the metric and **rethrow** the exception unless durable recovery occurred.

### 11.2. Instrument batch listeners accurately

If a listener receives a `List<ConsumerRecord<K,V>>`, counters should increment by **the number of records successfully processed**, not by 1 per batch unless the metric is explicitly named as a batch count. When a batch fails mid-way, determine the actual succeeded count and commit semantics before incrementing success counts.

## 12. Commit rate can be low even when the consumer is healthy

Offset commits depend on `AckMode`, batch boundaries, transactions, and manual ack mechanisms. In some configurations, a listener processes hundreds of records yet commits only once at the end of the batch.

Example:

~~~text
Poll returns 500 records.
Listener processes all 500 records.
Container commits offset after batch.

Business throughput: 500 records processed.
Commit count: 1 time.
~~~

Do not treat `commit-rate × 1 record` as throughput.

### 12.1. Committed lag has a sawtooth pattern

In applications committing by batch:

~~~text
Lag
 ^
 |         /|         /|
 |        / |        / |
 |       /  |       /  |
 |______/   |______/   |____
 +--------------------------> time
           commit     commit
~~~

Between commits, the producer keeps writing records so committed lag rises; when the batch commits, lag drops sharply. Do not page on a brief spike if it is simply the normal rhythm of the ack policy.

However, if the interval between commits grows unusually long or offsets stall while processing successes stop increasing, investigate the listener/downstream.

### 12.2. Manual ack and asyncAcks

With manual acknowledgment, the application is responsible for acking at the right time. With asynchronous ack modes supported by Spring Kafka, the container may hold records or pause delivery while ack gaps remain unresolved.

Common scenario:

- Kafka client `records consumed` rises from polling.
- Business tasks are in-flight.
- Committed offset stalls because one ack is still missing.
- Group lag climbs even though some tasks completed.

Include in-flight counts, oldest in-flight age, and ack gaps on dashboards if using this model.

## 13. Retries, DLT, and "hidden" lag

Spring Kafka supports blocking retries and non-blocking retry topics. Both mechanisms produce different backlog paths.

### 13.1. Blocking retry

When the error handler holds a record for retry with backoff, the consumer slows down on that partition. Committed lag climbs if upstream continues publishing. At the same time, listener processing attempts can spike while business success rate is zero.

Observe:

- Exception classes.
- Retry attempt count.
- Backoff duration.
- Consumer group lag per partition.
- Record age and DLT recovery.

### 13.2. Non-blocking retry

When a failing record is published to a retry topic:

~~~text
orders.events (main)
      |
      | processing error
      v
orders.events-retry-... (delayed)
      |
      | retries exhausted
      v
orders.events-dlt
~~~

The main topic offset can be confirmed once the record moves to the retry topic, so **main topic lag can drop to 0 while the event is still unfinished**.

To know how much work remains in the system:

1. Monitor lag on retry consumer groups.
2. Monitor record counts on retry topics and when they become eligible for processing.
3. Monitor DLT publish rate and unresolved case counts.
4. Monitor business event completion age if available.

Do not blindly sum all group lags across multiple topics and claim that is the exact number of unique waiting events: one event can appear across multiple stages, replays, or duplicates.

### 13.3. DLT lag does not mean lost data

DLT typically holds records that exhausted retries and need separate handling. If the DLT consumer is intentionally turned off for manual review, DLT lag can rise deliberately. What matters is having an owner, retention, investigation SLA, and replay plan—not necessarily forcing DLT lag to 0 at all costs.

## 14. Pause and backpressure affect lag

Spring Kafka provides `MessageListenerContainer.pause()` and `resume()` to control delivery when downstream is overloaded. While paused, the container can still poll to maintain group membership without delivering new records per container pause mechanics.

During a pause:

- Producers can still write new data.
- Committed lag usually rises.
- Consumer `records consumed rate` can be low or zero.
- Downstream queues have time to drain.

After resuming, backlog shrinks only if net processing capacity exceeds arrival rate.

### 14.1. Do not page during planned maintenance

Rising lag during an intentional pause is expected. Dashboards should display pause state and reason. Alerts can shift from "lag is rising" to "maintenance exceeded allowed duration" to avoid false alarms, without losing visibility into backlog approaching retention limits.

### 14.2. Simultaneous resume can cause bursts

If multiple pods resume together after a downstream incident, draining the backlog can trigger a new connection storm and retry storm.

Consider:

- Staggered resume.
- Bounded concurrency and queue capacity.
- Rate limiters or adaptive backpressure.
- Watching DB pools, HTTP 429/503, and processing latency.
- High/low watermark hysteresis.

Resume is a delivery switch, not an automatic rate limiter.

## 15. Rebalances change metric shapes

During scale-out, scale-in, deploys, or consumer group errors, Kafka can rebalance partition assignments.

Effects:

- Which client ID/instance reports lag for a partition can change.
- `records-consumed-rate` of the old consumer drops to 0 after losing assignment.
- New consumers need time to start and receive partitions.
- Committed lag can climb during the pause in processing.
- Uncommitted records may be redelivered.

### 15.1. Do not arbitrarily sum metrics from old and new consumers

During rolling deploys, exporters may retain stale time series briefly. Summing per-client lag across old and new consumers can double-count the same partition.

For **consumer group lag**, prefer a single measurement source based on group/partition committed offsets with stable identity. Use client-specific metrics to analyze local behavior and assignments.

### 15.2. Concurrency cannot exceed partition count

Within one consumer group, each partition is assigned to at most one consumer at a time. If a topic has 4 partitions, raising active consumers from 4 to 12 will not split a single partition across 3 consumers.

If lag concentrates on one partition, fix key skew or increase partitions according to an appropriate ordering design. Merely raising concurrency only creates idle consumers with no partition assignment.

## 16. Differences between records/s and bytes/s

Two workloads both at 1,000 records/s can consume vastly different resources:

- Average record 500 bytes: ~500 KB/s payload.
- Average record 100 KB: ~100 MB/s payload.

Therefore, records/s throughput must be paired with bytes/s, CPU, memory, network, and downstream cost.

### 16.1. One record can cost more CPU than another

For instance, an `OrderEvent` updates a single database row, while an `InvoiceEvent` reconciles hundreds of lines. Both count as 1 record yet differ substantially in processing time.

Track duration histograms by a **bounded event class** if the contract defines event types; avoid putting event IDs or order IDs in metric tags.

### 16.2. Batch size and efficiency

Batch processing can boost throughput by reducing transactions/round trips, yet it can also cause:

- Longer processing time per poll.
- Larger commit delays.
- Poison pills affecting the entire batch.
- Higher memory pressure.
- Difficulty separating completed vs. failed records.

Batch tuning must include correctness and latency checks, not just records/s.

## 17. Consumption capacity and capacity planning

To resolve sustained lag, identify the primary bottleneck:

| Bottleneck | Common symptoms | Remediation |
|---|---|---|
| CPU parse/decompress | High CPU, rising processing latency | Optimize codecs, scale partitions/consumers if helpful |
| Database pool | Connection waits, rising p95 latency | Tune SQL/transactions, scale pool safely |
| HTTP downstream | Rising timeouts/429/503 | Backoff, circuit breakers, reduce concurrency, cache |
| Single hot partition | One partition's lag surges | Balance keys, review partitioning/ordering |
| Consumer fetch/network | High fetch latency, low byte rate | Inspect broker/network/client config |
| Blocking retry | High error rate, committed offset stuck | Classify exceptions, DLT, backoff |
| Large batches | Sawtooth commits, high latency | Shrink batch size, tune processing |
| GC/memory | Long pauses, fluctuating throughput | Heap profiling, bounded queues, reduce allocations |

### 17.1. Scaling a consumer group properly

To increase throughput by adding consumers:

1. Verify the topic has enough partitions.
2. Verify the workload can be processed in parallel across partitions.
3. Verify the bottleneck is the consumer rather than a shared downstream.
4. Calculate total concurrency across all pods.
5. Test rebalances/rolling deploys.
6. Measure effective business completion rate after scaling.

If the database is already out of connections, adding more consumers can reduce throughput further.

### 17.2. Scaling partitions and ordering

Increasing partitions enables more consumers to process in parallel, with caveats:

- Key → partition mappings can change.
- Future events with the same key may land on a new partition.
- Preserving ordering across a partition count change is difficult without design.
- More partitions increase broker management overhead.

Do not add partitions just to lower average lag per partition; evaluate ordering contracts and actual load.

## 18. Minimum dashboard design

An incident-response dashboard should answer: **where is the backlog, how fast is it growing, why is it growing, and when will it catch up?**

### 18.1. Overview status group

- Total committed lag of the consumer group.
- Max partition lag.
- Number of partitions with growing lag.
- Producer arrival rate and consumer success rate.
- Oldest unprocessed event age.
- Count of active group members and assigned partitions.
- Consumer group state/rebalances.

### 18.2. Performance group

- Records consumed/s and bytes consumed/s.
- Listener successful records/s.
- Listener processing duration p50/p95/p99.
- Database query/transaction latency.
- HTTP downstream error rate.
- CPU, memory, and GC pauses.

### 18.3. Reliability group

- Error/retry/DLT rate.
- Last successful processing timestamp.
- Commit failure rate.
- Transaction aborts/producer fencing if using Kafka transactions.
- Pause/resume state and backpressure reason.
- Worker queue depth if using async processing.

### 18.4. Per-partition breakdown

Include a table or heatmap for highest-lag partitions instead of showing total lag alone. For large consumer groups, prioritize top N partitions by lag and lag growth rate.

## 19. Prometheus/Grafana: know the schema before writing queries

Metric names depend on the exporter (Kafka exporter, JMX exporter, Micrometer, OpenTelemetry collector, etc.), so the PromQL examples below **apply only if your exporter actually emits these names and labels**. Never copy them straight into production dashboards without checking the metrics endpoint.

### 19.1. Total lag by group and topic

Example if the exporter exposes `kafka_consumergroup_lag`:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag{consumergroup="billing-group"}
)
~~~

### 19.2. Maximum partition lag

~~~promql
max by (consumergroup, topic) (
  kafka_consumergroup_lag{consumergroup="billing-group"}
)
~~~

### 19.3. Business success rate

Suppose the application exports counter `app_kafka_orders_processing_success_total` from Micrometer/Prometheus:

~~~promql
sum(rate(app_kafka_orders_processing_success_total[5m]))
~~~

If metrics carry `service`/`listener` labels, filter appropriately so different pipelines are not added together by mistake.

### 19.4. Lag growth rate

For a gauge-type lag metric, you can compare the difference over a window. Example:

~~~promql
delta(
  kafka_consumergroup_lag{
    consumergroup="billing-group",
    topic="orders.events"
  }[5m]
)
~~~

`delta` on a gauge gives the difference over a 5-minute window, not a counter rate. Before interpreting, group properly by partition and account for rebalances, offset resets, or missing samples. If you want lag growth per second, divide the change by the elapsed time or use a method suited to your system's time series.

### 19.5. Common query mistakes

- Applying `rate()` to a lag gauge as if lag were a counter.
- Summing per-client lag metrics that have overlapping assignments after a rebalance.
- Forgetting to filter by consumer group.
- Mixing main topic and retry topic and calling it unique business events.
- Using a single instantaneous sample to conclude sustained lag growth.
- Applying an absolute 1,000-record lag alert across all topics regardless of traffic.

## 20. Alert design: trend, duration, and SLO

There is no single absolute consumer lag threshold suitable for every application. Useful alerts include:

| Alert | Reference condition | Meaning |
|---|---|---|
| Sustained growing lag | Lag rises continuously over a sufficiently long window | Capacity below input rate or consumer failing |
| Lag age exceeds SLO | Oldest event age exceeds budget | Data arriving late for business |
| No progress | Committed offset not advancing while input exists | Consumer stopped, retrying, blocked, or commit issue |
| Hot partition | Max partition lag exceeds baseline | Skew or slow per-key processing |
| Processing throughput drop | Success rate drops sharply vs. baseline | Dependency/CPU/error regression |
| Retry/DLT spike | Error/recovery rate spikes | Data issue or downstream failure |
| Consumer group unstable | High rebalance/active member churn | Disruptive partition reassignments |
| Backpressure duration | Container paused too long | Dependency has not recovered |

### 20.1. Do not page when a topic is legitimately quiet

A sparse transactional topic may go hours with no records. Zero lag and zero throughput are normal when the producer emits no events. An alert for "consumer throughput = 0" only makes sense when **expected input** or pending backlog exists.

### 20.2. Separate warning and critical

Example:

- Warning: lag grows for 15 minutes while business freshness still meets SLO.
- Critical: oldest unprocessed event age breaches SLA, or committed offset stalls while the producer continuously emits critical records.

Adjust numbers per service; use the example only to show the principle of combining volume, duration, and impact.

### 20.3. Avoid alert flapping

Batch commits and traffic bursts can cause brief lag spikes followed by drops. Use evaluation windows, persistence durations, and hysteresis. Do not page for a brief lag spike if the pipeline catches up normally.

## 21. Runbook: lag grows despite high records-consumed-rate

1. Identify the consumer group/topic/partition with rising lag.
2. Compare incoming records/s against consumed records/s.
3. Compare consumed records/s against **business success rate**.
4. Check record processing duration and error/retry rates.
5. Check commit frequency and ack mode.
6. Check whether backlog is shifting into worker queues or retry topics.
7. Check partition key skew and hot partitions.
8. Check database/HTTP dependency saturation.
9. If the bottleneck is the consumer and partitions are sufficient, consider raising concurrency/replicas.
10. Monitor max lag, total lag, and oldest age after changes.

**Do not conclude the consumer is fast enough just because `records consumed/s` is large.** It can still be slower than upstream.

## 22. Runbook: high lag while records-consumed-rate is near 0

1. Check whether the group has active members.
2. Confirm whether the listener container is running or stopped.
3. Check consumer group rebalances or partition assignments.
4. Check pause/backpressure state.
5. Check broker/authentication/authorization/network logs.
6. Check deserialization/conversion errors before the listener.
7. Check blocking retries or error handlers holding a record.
8. Take thread dumps to look for blocked listeners or deadlocks.
9. Check `max.poll.interval.ms` and `NonResponsiveConsumerEvent`.
10. Fix the root cause, then confirm committed offsets advance and lag drops.

Never reset offsets to `latest` just to turn lag to 0. Doing so can skip unprocessed data.

## 23. Runbook: low lag yet slow business completion

This is a dangerous situation because Kafka dashboards look healthy.

1. Check whether the listener enqueues async work and returns success.
2. Check task queue depth and oldest in-flight task age.
3. Check whether database transactions actually committed.
4. Check retry topic/DLT backlogs.
5. Check upstream outbox age and business event timestamps.
6. Verify whether offset commits occur before durable side effects.
7. Add business completion metrics and reconcile event IDs.
8. Fix acknowledgment policy if Kafka offsets are confirmed too early.

Low Kafka lag cannot compensate for data stuck in a non-durable internal queue.

## 24. Runbook: lag rising on a single partition

1. Identify the topic-partition with the fastest-growing lag.
2. Compare incoming rates across partitions.
3. Check key distribution and hot keys.
4. Identify which pod runs the consumer assigned that partition.
5. Measure processing duration and exception rate for that partition alone.
6. Verify whether one failing record is blocking progress.
7. Check downstream workload for the corresponding key/tenant.
8. Consider revising the partitioning strategy if ordering contracts allow.
9. Do not merely scale consumer replicas past partition count.

If the same aggregate requires sequential processing, breaking ordering for throughput can cause data corruption worse than lag.

## 25. Runbook: committed lag does not drop after resume

1. Confirm the container actually resumed, not merely accepted a request.
2. Check for remaining partition-level pause requests.
3. Check if the framework keeps pausing due to ack gaps/error handling.
4. Check consumer group assignments and state.
5. Determine whether listener processing is actively running or blocked.
6. Check if producer arrival rate exceeds processing capacity.
7. Compare committed lag against fetch lag and success rate.
8. If committing in batches, wait an appropriate commit cycle before concluding.

Resuming does not guarantee backlog shrinks if downstream remains slow or continuously fails.

## 26. Runbook: lag spike after deploy/rebalance

1. Check deploy timestamps and consumer group rebalance logs.
2. Verify active consumer counts before and after rollout.
3. Check whether all partitions are assigned.
4. Determine whether producer rate spiked at the same time.
5. Check startup time, consumer start failures, and executor threads.
6. Check schema/deserializer compatibility with new records.
7. Re-measure success throughput after rollout.
8. If the spike is brief and drops, it may be a normal rebalance effect.
9. If the spike persists, roll back or fix the regression per procedure.

Do not diagnose from an instantaneous lag chart alone; correlate with deployment annotations and group events.

## 27. Runbook: exporter reports negative, missing, or inconsistent lag

1. Check whether the metric computes from committed offset, consumer position, LSO, or LEO.
2. Check for stale partition/member series.
3. Check whether the group has never committed offsets or the consumer was newly initialized.
4. Check retention/compaction and log start offset.
5. Check recent manual offset resets or seeks.
6. Check open transactions if using `read_committed`.
7. Compare CLI, `AdminClient`, and exporter at the same point in time.
8. Check scrape intervals, missing data, and duplicate targets.

If a tool reports negative values due to asynchronous end/commit snapshots or normalization quirks, do not turn negative values into "negative backlog" in business reports. Identify the data source's definition and calculation, then align queries/dashboards consistently.

## 28. Testing lag and throughput in integration environments

A solid test suite verifies both metrics and actual outcomes.

### 28.1. Normal consumer catching up

1. Create a topic with multiple partitions.
2. Send a batch of records with stable event IDs.
3. Start the test group from an appropriate offset.
4. Verify the listener processes successfully.
5. Verify committed offsets advance.
6. Verify group lag drops to the expected level.

### 28.2. Processing slower than producer

1. Send records at an input rate higher than controlled processing capacity.
2. Measure `records-consumed-rate` and success rate separately.
3. Observe rising lag trend.
4. Stop the producer or increase capacity.
5. Confirm backlog gradually shrinks.

### 28.3. Manual acknowledgment and batch commit

1. Configure the appropriate ack mode.
2. Process multiple records before committing.
3. Observe committed lag rising and falling in commit cycles.
4. Confirm metrics do not treat commit count as record throughput.

### 28.4. Retry/DLT

1. Send an event triggering a retryable exception.
2. Confirm blocking retry or retry-topic routing follows policy.
3. Measure main-topic lag and retry-topic lag separately.
4. Confirm business success is not counted when the event has only moved to a retry topic.
5. When retries exhaust, verify DLT and recovery metrics.

### 28.5. Crash before commit

1. Process a record but simulate a crash before offset commit.
2. Restart a consumer in the same group.
3. Confirm the record can be redelivered.
4. Confirm the business handler is idempotent.
5. Reconcile consumed count, business success, and committed lag.

### 28.6. Partition skew

1. Send more events to one key/partition than others.
2. Confirm max partition lag rises even while total group throughput stays high.
3. Scale consumers past partition count and check actual effect.
4. Evaluate key distribution/ordering before altering partitions.

## 29. Common misconceptions

**Lag of 0 means all business work is done.** False if offsets committed while records moved to retry topics, worker queues, or async processing.

**`records-consumed-rate` is business success rate.** The client receiving a record does not equate to a database commit.

**A high `records-consumed-rate` means the consumer is fast enough.** Must be compared against arrival rate and lag trend.

**Summing client `records-lag-max` gives total group lag.** Per-client max is not the sum of committed lag across partitions.

**Monitoring total lag alone is enough.** One hot partition can hide inside an aggregate average.

**Setting lag > 1,000 alert for every topic.** What 1,000 records means depends on rate, size, SLO, and workload.

**Taking `rate()` on a lag gauge like a counter.** Lag goes up and down; use gauge operations and account for resets/stale data.

**Treating commit rate as record rate.** One commit can confirm an entire batch.

**Increasing concurrency indefinitely.** Throughput remains bounded by partitions or downstream bottlenecks.

**Treating every lag spike after rebalance as an outage.** Look at the recovery trend.

**Ignoring LSO on transactional topics.** LEO and LSO can diverge while transactions are open.

**Resetting offsets to clear lag.** Can skip unprocessed data.

**Ignoring retry/DLT backlog.** Low main-topic lag does not mean the workflow succeeded.

**Not measuring record age.** Count-based lag does not by itself reflect business latency.

## 30. Monitoring and operations checklist

### Metric definitions

- [ ] Distinguished fetch lag from committed consumer group lag.
- [ ] Agreed on end-offset reference when using `read_committed`.
- [ ] Dashboards explicitly identify group/topic/partition.
- [ ] Track both total lag and max partition lag.
- [ ] Distinguished records fetched, listener invocations, and business success.
- [ ] Track record age or end-to-end latency per SLO.

### Application configuration

- [ ] Ack/commit mode matches side-effect durability.
- [ ] Listeners do not return success before critical work finishes or is durably persisted.
- [ ] Idempotency handles redelivered records.
- [ ] Retries/backoff/DLT are observed separately.
- [ ] Queue/in-flight metrics exist if using async workers.
- [ ] Concurrency matches partition counts and downstream capacity.

### Dashboards and alerts

- [ ] Input rate placed beside completion rate.
- [ ] Lag trends shown, not just instantaneous snapshots.
- [ ] Top hot partitions highlighted.
- [ ] Alerts based on duration/SLO instead of one universal absolute threshold.
- [ ] Pause/rebalance/maintenance annotations included.
- [ ] Event IDs/offsets never used as metric tags.
- [ ] Metric schemas and label names verified against the live exporter.

### Recovery

- [ ] Runbook exists for continuously growing consumer lag.
- [ ] Runbook exists for stalled lag with idle consumer processing.
- [ ] Runbook exists for low lag with slow business completion.
- [ ] Runbook exists for retry-topic/DLT backlogs.
- [ ] Runbook exists for hot partitions and key skew.
- [ ] Group offsets never reset without assessing data-loss risk.
- [ ] Capacity plan exists for rising input throughput.

## Conclusion

**Consumer lag** reflects the gap between available data in Kafka and consumer group progress, yet you must specify whether you are measuring **committed offset**, **consumer position**, **LEO**, or **LSO**. **Consumption rate** likewise requires separating Kafka client fetches, listener invocations, and truly completed business events. A high-throughput consumer can still fall behind if producers write faster; a group with zero lag can still hold backlogs in retry topics or internal queues.

To operate Spring Kafka reliably, measure lag per partition, place input rate alongside processing success rate, and add record age, error/retry/DLT metrics, pause state, and rebalance signals. Use backlog/catch-up math for capacity planning without overlooking hot partitions, transaction visibility, and commit semantics. Most importantly, **lag is only a Kafka progress indicator**; reliability conclusions must rest on durable processing and meeting business SLOs.

# Consumer Lag, Checkpoints, and Resuming Stream Consumption

## 1. Why Monitor Consumer Progress?

In event-driven architectures, producers write messages to a queue or stream; consumers read and process them. In serverless, a Java function may be triggered with batches of events. The platform can scale out instances as traffic increases, yet successful function invocations alone do not prove every message was processed and its results safely persisted.

Two critical operational questions are: how far behind the producer is the consumer, and if the consumer stops abruptly, where does the next read resume? **Consumer lag** measures the distance between available data and the progress a consumer has completed. **Checkpoints** persist progress positions so consumers can resume after restarts, rebalances, or failures. These two concepts are tightly coupled: inaccurate checkpoints can distort lag metrics, skip records, or replay already-processed data.

In a serverless system, rising lag can delay business outcomes—for instance, a payment is authorized while the order remains `PENDING`. Without monitoring message age and checkpoints, the system may report healthy function executions while the backlog grows continuously.

## 2. Queues and Streams Track Progress Differently

Queues and streams both transmit messages asynchronously, yet they represent progress differently:

| Trait | Queue | Ordered / Offset-Based Stream |
|---|---|---|
| Read model | Consumer receives a message and acknowledges (acks) it or lets it be redelivered | Consumer reads by position in a log or shard |
| Progress | Usually represented via per-message ack/delete state | Usually represented via offset, sequence number, or per-partition/shard checkpoint |
| After processing | Acked messages may be deleted from the queue | Records stay in the stream until retention expires; consumer groups can re-read |
| Multiple consumers | Typically compete for messages or use separate subscriptions | Separate consumer groups can read independently |
| Replay | Usually requires keeping copies, DLQs, or redrive mechanisms | Can seek back to older offsets/sequences while data stays within retention |

Not all queues share identical semantics, and not all streams use contiguous numeric offsets. For instance, Kafka uses per-partition offsets; Kinesis uses per-shard sequence numbers; some managed stream services store checkpoints via event source mappings. Understand your specific platform's semantics rather than assuming every `ack`, `commit`, and `checkpoint` behaves identically.

## 3. What Is Consumer Lag?

For an offset-based stream, lag is typically expressed as the gap between the newest readable position and the consumer's committed position. In Kafka, a common per-partition calculation is:

\[
\text{lag records} = \text{log end offset} - \text{committed offset}
\]

The committed offset usually indicates **the next offset to read**, not the last processed offset. For example, if a consumer successfully processes offset `41` and commits `42`, the next startup begins at offset `42`.

Suppose a partition has a log end offset of `500000` and a committed offset of `487500`, giving a lag of roughly `12500` records. At a processing rate of 500 records/second with negligible temporary producer traffic, the backlog represents about 25 seconds of work. This is only an estimate; arrival rates, record sizes, and processing times fluctuate.

### Ways to Measure Lag

| Metric | Question Answered | Notes |
|---|---|---|
| Offset/record lag | How many records behind the stream head is the consumer? | Useful for comparisons within a partition; offsets may contain gaps |
| Time lag / age of oldest record | How long has the oldest unprocessed record been waiting? | Closer to business impact, though dependent on timestamps and clocks |
| Byte lag | How much unread data remains? | Useful when record sizes vary widely |
| Processing latency | How long does a record take from emission to completion? | Measures end-to-end delay; requires reliable timestamps |
| Backlog growth rate | Is lag growing or shrinking, and how fast? | Helps detect when consumers cannot keep up with producers |

Do not inspect only aggregate lag across the whole stream. One partition may be stalled while others have near-zero lag. Monitor per consumer group and per partition/shard, tracking both the highest-lag partition and the oldest record age.

### Offset Lag and Time Lag Are Not the Same

One partition may hold 10,000 queued records representing only a few seconds if producers emit rapidly; another partition may hold just 100 records where the oldest has waited 30 minutes because a consumer stalled. Offset lag measures relative volume; age lag measures business delay.

In Kafka, offsets represent positions in the log rather than strictly contiguous visible records. Compaction, transactions, and aborted/control offset gaps mean subtracting offsets does not always equal the exact count of records the application will receive. With `read_committed`, consumers also read only committed records under Kafka's transactional semantics. Treat offset lag as a log-progress indicator and pair it with record/age metrics provided by the platform or application.

Depending on how the broker exposes metrics, the end marker may be log end offset, high watermark, or last stable offset. For `read_committed` consumers, last stable offset may better approximate currently readable data, since it does not advance past open transactions. When comparing dashboards and admin tools, verify they use the same offset boundary type.

## 4. Estimating Backlog Catch-Up Capacity

A consumer reduces backlog only when its processing rate exceeds the incoming record rate. Let:

- \(B\): number of backlogged records.
- \(\lambda\): incoming record rate per second.
- \(\mu\): aggregate successful processing rate per second.

When \(\mu > \lambda\), the approximate catch-up time is:

\[
T_{catchup} \approx \frac{B}{\mu - \lambda}
\]

For example, with 120,000 backlogged records, a consumer handling 1,500 records/second, and producers continuing at 1,000 records/second, the backlog drains at 500 records/second—taking roughly 240 seconds to catch up if load and performance hold steady.

If \(\mu \leq \lambda\), the backlog will not shrink. Increasing invocations or concurrency may not help if the bottleneck is a database, an external API, partition limits, or a hot partition key. When calculating throughput, use **successful** processing rates rather than merely polled or invoked record counts.

## 5. Checkpoints, Offsets, and Commits

A checkpoint is the position a consumer uses to resume reading after stopping. Depending on the platform, a checkpoint may be:

- Committed offsets of a consumer group per Kafka partition.
- Processed sequence numbers for a Kinesis shard.
- Read positions persisted by an event source mapping for a function.
- Progress cursors or tokens managed by the streaming service.

Checkpoints must represent **durably completed** progress. Polling or receiving a record does not mean the record was processed. Calling an API successfully is not enough if the outcome is not persisted somewhere recoverable.

### Committing After Processing

Suppose a consumer reads record offset `41`:

1. Consumer reads the record.
2. Applies business changes and commits the database transaction.
3. After the database confirms success, the consumer commits offset `42`.
4. If the consumer stops before step 3, record `41` may be redelivered and must be processed idempotently.

Committing after durable business side effects prioritizes avoiding data loss. In exchange, if the process dies after writing data but before committing the offset, the record may be reprocessed. This is standard at-least-once behavior.

### Why Not Commit Before Processing?

If a consumer commits offset `42` before writing the business change for record `41`, and crashes between the two steps, the next run starts at `42`. Record `41` was marked complete even though business changes were never saved. From the application's viewpoint, this is data loss (message loss).

### Checkpointing Too Frequently or Too Infrequently

- Committing after every single record minimizes rework on failure, but increases commit operations and overhead.
- Committing per batch reduces overhead, though crashing mid-batch can redeliver multiple already-processed records.
- Timer-based commits must align with actual progress; never commit the latest polled position while earlier records are still in flight.

Choose commit boundaries based on latency, throughput, batch size, and idempotency capabilities. In FaaS environments, event source mappings typically manage checkpoints per batch or per failed record; functions must follow the platform's response contract.

## 6. Checkpoints Must Be Contiguous Under Parallel Processing

A subtle bug occurs when consumers process records in parallel. Suppose a partition contains records `100`, `101`, and `102`:

- Record `100` is processing slowly.
- Records `101` and `102` finish.
- The consumer commits the position after `102` (offset `103`).
- The instance crashes before `100` completes.

When resuming from `103`, record `100` may be skipped even though it never finished. Therefore, a checkpoint must indicate **the position immediately following the highest contiguous completed record**, not the highest-offset record that finished out of order.

<text weight="semibold">Per-partition progress example</text>

```text
Offset:        100       101       102       103
Status:       RUNNING   DONE      DONE      NOT READ
Checkpoint:   100       100       100       100
                         ^
           Cannot advance past 100 because this record is unfinished

After 100 completes:
Offset:        100       101       102       103
Status:       DONE      DONE      DONE      NOT READ
Checkpoint:                         103
```

In this example, the checkpoint is the next offset to read. Only after `100`, `101`, and `102` all finish does the consumer commit `103`. If a record fails, the consumer must retry it or route it to quarantine per policy before advancing past that position.

"Contiguous" here means every readable record prior to the checkpoint position has been safely processed in partition order. Not every arithmetic integer offset necessarily holds a record; compaction or transactions can leave gaps. Consumers should rely on the broker's position/offset semantics rather than assuming every sequential integer offset exists.

To parallelize safely, use one of these approaches:

- Process sequentially within each partition, and in parallel across partitions.
- Track completion state for every offset and commit only the highest contiguous completed offset.
- Pause a partition when a batch hits a failing record, completing or retrying that record before continuing.
- Use the platform's partial batch failure API to checkpoint only up to the safe position defined by platform semantics.

Do not assume thread or future completion order matches record order. If business rules require per-aggregate order, preserve that order in the consumer or use an appropriate partition key.

## 7. Java Kafka Consumer: Disabling Auto-Commit and Committing After Processing

The example below illustrates a consumer sequentially processing records returned by `poll`. Once every record in the batch is processed and durably saved, the consumer commits the current position. If the handler throws an exception, `commitSync()` is skipped; upon restart, uncommitted records can be re-read.

```java
import java.time.Duration;
import java.util.Properties;

import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;

public final class OrderEventsConsumer {
    public static void main(String[] args) {
        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "broker:9092");
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "order-projection-v1");
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
                StringDeserializer.class.getName());
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");

        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(properties)) {
            consumer.subscribe(java.util.List.of("order-events"));

            while (true) {
                ConsumerRecords<String, String> records =
                        consumer.poll(Duration.ofMillis(500));

                for (ConsumerRecord<String, String> record : records) {
                    // Must persist business effects durably and idempotently.
                    applyEventIdempotently(record.key(), record.value());
                }

                // Commit the next offset only after the entire batch succeeds.
                consumer.commitSync();
            }
        }
    }

    private static void applyEventIdempotently(String key, String value) {
        // Replace with a DB transaction + inbox/unique event ID in real applications.
    }
}
```

This is a continuously running consumer example, not a direct handler for every FaaS runtime. `KafkaConsumer` is not thread-safe; never share one instance across multiple threads. If processing in parallel, manage contiguous offsets per partition and never commit past unfinished records. Production deployments also need broker security, deserializers/schemas, graceful shutdown, poll intervals, max poll records, timeouts, and error handling.

`auto.offset.reset=earliest` applies only when the group has no valid offset or its offset no longer exists under Kafka semantics; it does not make the consumer re-read from the start on every restart. `latest` can skip existing backlog when a group has no prior offset. `none` throws an error if no offset is found, forcing operators to choose a policy explicitly.

When running in FaaS via an event source mapping, the platform typically manages consumer groups, polling, and checkpointing. The function receives event batches and returns results per the trigger contract. Do not spin up an internal Kafka consumer loop inside a function when the platform already manages polling; two independent poll/commit layers will conflict or corrupt checkpoints.

## 8. Resume: Continuing from a Checkpoint

Resuming means starting or continuing a consumer from a saved position. General flow:

1. Identify the consumer group or subscription to resume.
2. Read the committed checkpoint for each partition/shard.
3. Verify the checkpoint still falls within the retained data range.
4. Assign partitions/shards to consumers per the platform's mechanism.
5. Read from the position following the checkpoint, process idempotently, and continue committing.
6. Monitor lag, errors, and replays during the catch-up phase.

In Kafka, consumer groups store offsets per partition. When a consumer restarts, it joins the group, receives partition assignments, and begins from each partition's committed offset. If no valid offset exists, `auto.offset.reset` dictates behavior (`earliest`, `latest`, or `none`). Setting `earliest` can replay large amounts of old data; `latest` can skip backlog accumulated before the group started.

In sharded streams, checkpoints usually correspond to sequence numbers or shard positions. Event source mappings can automatically recover from saved checkpoints. When a function fails, the platform may retry the batch or shard per configuration. Check your specific trigger documentation to know which records are replayed and when checkpoints update.

### Resume vs. Replay

- **Resume:** continue from the current checkpoint after a normal interruption.
- **Replay:** deliberately re-read a historical range of data to recover, rebuild projections, or re-run logic.
- **Backfill:** read historical data to generate new datasets, usually using a separate consumer group or pipeline.

Replay can produce duplicate side effects in target systems. Before replaying, verify consumer idempotency, whether outputs can be overwritten safely, and whether a separate consumer group is needed to protect production progress. Never reset offsets on a production consumer group casually just to "retry"; doing so can make every partition replay unexpected historical data.

## 9. Retention and Expired Checkpoints

A checkpoint is only useful if data at that position still exists. Streams have finite retention: Kafka deletes segments by time or size, and managed stream services limit retention days. If a consumer stops longer than the retention window, its checkpoint may point to deleted data.

When an offset falls outside retained bounds, the platform may raise `OffsetOutOfRange`, require a reset policy, or start from the earliest available position. Choose `earliest` when older retained data can still be replayed; if expired past retention, `earliest` simply starts at the oldest surviving record. Choosing `latest` resumes with new records while skipping lost backlog. No automatic option can recover deleted records.

To reduce risk:

- Set retention longer than the maximum business-tolerable outage duration.
- Alert when age lag approaches the retention window.
- Keep copies or archives if long-term historical replay is required.
- Maintain processes to rebuild projections or reconcile from authoritative sources.
- Document unrecoverable data gaps explicitly and assess business impact.

Longer retention buys more recovery time while increasing storage costs and potentially hitting capacity quotas. Balance RPO, recovery time, audit needs, and cost.

## 10. Rebalances and Partition Ownership

In Kafka consumer groups, rebalances happen when members join or leave, sessions time out, or partitions are reassigned. During a rebalance, a consumer can lose ownership of partitions it is actively processing. If commits miss the deadline or processing is mid-flight, records may be redelivered to another consumer.

A consumer should:

- Handle graceful shutdown and stop accepting new work when about to lose assignments.
- Finish or cancel in-flight work according to a clear policy.
- Commit offsets safely before releasing partitions if time and ownership still hold.
- Never commit after losing partition ownership.
- Design idempotent handlers because rebalances can still produce duplicates.

In FaaS, event source mappings may manage leases and shard ownership on behalf of the application. Still, scale-outs, function timeouts, new deployments, or mapping errors can reassign shards. Monitor invocations, retries, and checkpoints to detect failure loops.

Useful consumers in a group are bounded by the number of partitions/shards that can run in parallel. If a topic has 8 partitions and you run 30 consumers in one group, at most ~8 consumers can own partitions at once; the rest sit idle. Increasing partitions boosts parallelism while affecting ordering, key mappings, and operations; design partitioning upfront for expected throughput.

## 11. Backpressure and Handling Rising Lag

Backpressure limits ingestion or processing rates so consumers do not overload dependencies. Rising lag can stem from producer bursts, degraded consumer capacity, hot partitions, or slow downstream services.

Mitigation steps:

1. **Locate the bottleneck:** compare per-partition lag, handler duration, database latency, API rate limits, error rates, and concurrency.
2. **Scale consumer capacity safely:** raise concurrency or batch throughput if dependencies can handle it.
3. **Reduce per-record work:** optimize queries, batch database writes, or remove unnecessary synchronous calls.
4. **Throttle inputs:** pause partitions, reduce poll rates, or cap event source mapping concurrency when downstream is overloaded.
5. **Address partition skew:** check whether partition keys concentrate traffic onto a single partition.
6. **Split slow consumers:** split unrelated work out of one overloaded consumer into separate queues/subscriptions.

Do not scale concurrency infinitely. Each Java instance opens connections, calls APIs, and generates concurrent load. When the database is the bottleneck, scaling out can accelerate failures. Set reserved/max concurrency, connection pool limits, batch sizes, and timeouts aligned with dependencies.

### Batch Size and Batching Window in FaaS

Large batches reduce invocations and startup overhead, while increasing wait time to fill batches, memory needs, and replay blast radius when a batch fails. Small batches reduce latency and blast radius while potentially raising invocation costs. Batching windows let the platform wait briefly to gather records; balance against latency SLAs.

With ordered streams, one failing record can stall shard/partition progress if the platform retries the whole batch or holds checkpoints at the failing record. Distinguish transient errors (retryable) from poison messages (consistently failing due to data or code). Record poison messages in a DLQ/quarantine with event ID and root cause, skipping only under an approved business policy. Silently dropping records creates hard-to-detect data holes.

## 12. Retries, Partial Batch Failure, and Checkpoints

When a function processes batches, three behaviors are common:

- **Whole-batch retry:** a single failing record causes the entire batch to be redelivered. Already-succeeded records may run again; consumers must be idempotent.
- **Partial batch response:** the function returns failed record identifiers or the first failed position per platform protocol; the mapping retries only what is needed or holds checkpoints before the failure point.
- **Bisect batch:** the platform splits failing batches into smaller chunks to isolate failing records; this increases invocations but isolates poison records.

Not all platforms support the same mechanism. Some only accept reporting the first failed sequence number in a shard; some accept a list of message IDs; others manage retries at the invocation level. Adapters must return the exact structure required by the trigger. If a function returns success while a record remains unsaved, the platform may checkpoint past that record.

A safe batch workflow:

1. Parse and validate each record.
2. Process records using idempotency keys.
3. Mark a record succeeded only after durable side effects.
4. Collect retryable failures and data errors needing quarantine.
5. Return partial failures per platform semantics.
6. Monitor retry counts, DLQs, and checkpoints to prevent poison messages from blocking shards indefinitely.

For ordered streams, never confirm records after a failing record if doing so advances the checkpoint past the failure. You can process independent records on other partitions, while progress within one partition must follow contiguity rules.

## 13. Idempotency and the Boundary Between Business Data and Checkpoints

Typically, business database updates and offset/checkpoint commits happen in two separate systems. No single atomic transaction spans both. Consequently, two failure cases can arise:

- Database commit succeeds, but consumer dies before committing the checkpoint: the record is redelivered.
- Checkpoint commit succeeds before the database commits: the record may be skipped even though business changes were not saved.

Prefer database first, checkpoint second to avoid losing records, and rely on idempotency to handle redeliveries. Store `eventId` in an inbox/processed-events table with a unique constraint inside the same transaction that updates business data. If follow-up events must be emitted after updating, use a transactional outbox inside that same transaction.

For Kafka-to-Kafka pipelines, Kafka transactions can coordinate writing outputs and committing offsets atomically when properly configured. However, those transactions do not automatically cover external databases or APIs. With Kinesis, Pub/Sub, or managed event source mappings, combine application-level idempotency with the checkpoint/ack semantics offered by the service.

Never promise "exactly once" solely because a broker supports transactions or a function uses checkpoints. Specify exactly which boundary is covered: reading, in-broker writes, database updates, or external side effects. For payments, emails, or partner API calls, idempotency keys and reconciliation remain essential.

## 14. Operating Java Consumers on Serverless

When Java functions are triggered by stream batches, design for invocation limits:

- Function timeout must accommodate the largest batch under reasonable downstream slowness.
- Batch size and concurrency must fit database and API dependency capacity.
- Never kick off async work and return success before the work finishes or is persisted to another durable queue.
- On timeout, assume a subset of records may have processed and will be redelivered.
- Never store checkpoints in static variables or temporary instance files.
- Use bounded connection pools and safely reuse clients when the runtime permits.
- With large batches, budget for memory, payload sizes, and deserialization time.
- When deploying new code, ensure older schemas remain readable while old records persist within retention.

Functions can experience cold starts or mid-processing termination. Platform-managed or consumer-group checkpoints must serve as the source of truth for progress. New instances resume from the checkpoint and may receive part of the previous batch again. Therefore, handlers must be safe to re-run.

If a function simply transforms quickly and writes to a database, measure latency by batch and record. If one record calls an external API with variable latency, consider an intermediate queue or workflow to decouple slow calls from the stream consumer, avoiding holding partitions open and inflating lag for subsequent records.

## 15. Controlled Replay and Backfill

Replay is useful when fixing projection bugs, building new reports, or recovering data after incidents. Yet replay can re-emit millions of records and spike downstream load.

A replay procedure should include:

1. Selecting the target offset/sequence range or time window.
2. Creating a separate consumer group or subscription if production progress must be protected.
3. Identifying historical schema versions and verifying the consumer can still parse them.
4. Using a separate sink or idempotency keys to avoid duplicating live business side effects.
5. Throttling replay rates to avoid overloading databases and APIs.
6. Monitoring lag, errors, processed records, and checkpoints throughout the run.
7. Reconciling outcomes before promoting replayed data to production flows.

If replaying on the production consumer group, understand that resetting offsets affects active partitions and running consumers. Never run two consumer groups writing concurrently to the same projection without overwrite protection or clear data partitioning.

## 16. Observing Lag and Checkpoints

An operational dashboard should combine broker, consumer runtime, and business metrics:

| Metric | Purpose | Alerting Hint |
|---|---|---|
| Per-partition/shard lag | Detect stalled partitions | Lag rises steadily or one partition diverges sharply from peers |
| Age of oldest record | Measure real delay | Exceeds business processing SLA |
| Consumer throughput | Compare processing rate vs. arrival rate | Throughput stays below arrival rate for an extended span |
| p95/p99 processing latency | Spot slow records or dependencies | Exceeds latency budget |
| Commit/checkpoint age | Detect consumers processing without saving progress | Time since last checkpoint exceeds threshold |
| Retry and failure counts | Spot transient issues or poison messages | Retries spike or repeat on the same event ID |
| DLQ/quarantine depth | Track unprocessable records | New records arrive or record age grows |
| Rebalance/lease changes | Detect unstable groups | Frequent rebalances or shards constantly switching owners |
| Function concurrency and timeouts | Assess serverless limits | Concurrency hits ceiling or timeouts climb |

Structured logs should contain `eventId`, topic/stream, partition/shard, offset/sequence, consumer group, correlation ID, duration, and outcome. Never log sensitive payloads. When a record is processed multiple times, correlate event IDs with checkpoints to determine whether the fault lies in the handler, commit logic, or trigger mapping.

Set alerts around business semantics. An email queue may tolerate minutes of delay; balance updates or fraud detection may need alerts within seconds. Never apply a single record-lag threshold blindly across streams with vastly different record sizes and SLAs.

## 17. Scenario Example: Consumer Down for 10 Minutes

Suppose a stream receives 800 records/second. The consumer stops for 10 minutes, accumulating roughly:

\[
800 \times 10 \times 60 = 480,000 \text{ records}
\]

After restarting, the consumer handles 1,200 records/second while producers keep sending 800 records/second. The net backlog drain rate is 400 records/second, yielding an estimated catch-up time of:

\[
480,000 / (1,200 - 800) = 1,200 \text{ seconds} = 20 \text{ minutes}
\]

During this window, the consumer continues processing new records while age lag remains elevated. If the SLA requires updates within 2 minutes, scale processing capacity or throttle producers while verifying dependencies can sustain higher load. If the stream has only 4 shards and each shard is already saturated, scaling function instances beyond 4 will not speed up the stream.

If the last checkpoint saved before the consumer stopped, resuming reads from that position. Some records right before the outage may have written to the database without committing the checkpoint, creating duplicates. Inbox/idempotency logic prevents those records from applying side effects twice. Once lag returns to normal, keep monitoring age lag, retries, and DLQs to confirm no records remain stuck.

## 18. Checkpoint and Recovery Design Process

When deploying a new consumer, lock down these decisions before running in production:

1. **Define the progress unit:** per-partition offset, per-shard sequence, or per-message ack.
2. **Choose checkpoint storage:** broker/consumer group, managed event source mapping, or dedicated checkpoint store.
3. **Determine commit timing:** after database commit, after output write, or per partial batch contract.
4. **Design idempotency:** event IDs, unique constraints, or idempotency keys for external effects.
5. **Decide parallelism level:** per partition/shard, ensuring checkpoints never advance past unfinished records.
6. **Define retries and poison messages:** max retries, backoff, DLQ/quarantine, and controlled skip rules.
7. **Set retention and recovery policies:** max tolerable outage, expired-offset handling, and recovery source.
8. **Calculate catch-up capacity:** measure arrival rate, successful throughput, and backlog drain time.
9. **Inject failures in tests:** kill functions between processing and commit, trigger database failures, rebalances, expired retention, and replays.
10. **Set up observability:** per-partition lag, age, checkpoint age, retries, DLQs, concurrency, and business state.

## 19. Pre-Production Consumer Checklist

- [ ] Understood ack/offset/checkpoint semantics of the queue or stream in use.
- [ ] Lag is measured per partition/shard alongside SLA-aligned age lag.
- [ ] Successful processing throughput exceeds arrival rate under expected load.
- [ ] Checkpoints advance only after durable business side effects.
- [ ] Offsets commit the next position to read and never skip incomplete records.
- [ ] Consumers are idempotent to survive duplicates after crashes, rebalances, or retries.
- [ ] Parallel processing maintains contiguous checkpoints per partition/shard.
- [ ] Auto-commit is disabled or configured properly for required semantics.
- [ ] Resume policy is explicit when checkpoints are missing or expired past retention.
- [ ] Replay/backfill uses isolated groups or pipelines with appropriate load throttling.
- [ ] Retries, partial batch failures, DLQs, and poison messages have clear workflows.
- [ ] Concurrency, batch size, timeouts, and connection pools match dependency capacity.
- [ ] Rebalances and graceful shutdowns do not commit after losing partition ownership.
- [ ] Alerts exist for lag, age, checkpoint age, retries, DLQs, and timeouts.
- [ ] Tested crashes between side effects and checkpoints and verified zero data loss.

## Conclusion

Consumer lag tells you how far behind the stream head a consumer sits; checkpoints define where reading resumes after an interruption. Solid design commits only after durable business results, handles duplicates via idempotency, and advances checkpoints solely across contiguous completed records. In serverless, align batching, concurrency, timeouts, partitions/shards, and platform leases/sessions so scaling never sacrifices progress. Retention, replay, backpressure, and age-lag monitoring enable controlled recovery whenever consumers slow down or stop.

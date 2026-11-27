# Backpressure, Replay, and Observing Streaming Processing Latency

## Learning Objectives

After this lesson, you will be able to:

- Explain backpressure, consumer lag, backlog, and end-to-end latency in a streaming pipeline.
- Distinguish overload across producers, brokers/streams, processors, and sinks.
- Design flow control using bounded buffers, rate limiting, batching, pause/resume, and retries with backoff.
- Monitor Kinesis Data Streams via iterator age, throughput throttling, and KCL metrics.
- Monitor Amazon MSK via offset lag, time lag, consumer group health, and partition metrics.
- Analyze Managed Service for Apache Flink via source lag, operator throughput, CPU/memory, and checkpoint metrics.
- Monitor delivery freshness, retries, and backups for Amazon Data Firehose.
- Design replay from Kinesis retention, Kafka offsets, Flink checkpoints/snapshots, and S3 archives.
- Ensure safe replay using idempotency, deduplication, event identity, and side-effect controls.
- Build actionable latency SLIs/SLOs, CloudWatch dashboards, alarms, and runbooks.

## 1. Why Does Streaming Need Backpressure and Replay?

A streaming pipeline ingests data continuously from applications, devices, logs, or transactional systems. Data flows through brokers and processors into databases, search indexes, data lakes, or downstream APIs.

~~~mermaid
flowchart LR
    P["Producers"] --> S["Kinesis / MSK"]
    S --> F["Flink / Lambda consumers"]
    F --> Q["Enrichment / rules"]
    Q --> D["Database / S3 / OpenSearch"]
    D --> U["Dashboard / downstream apps"]
~~~

Under normal conditions, processing speed closely matches ingestion speed. When traffic spikes or a dependency slows down, unprocessed data accumulates. Consumers read slower than producers, lag grows, latency stretches, and data may eventually approach retention limits.

Two critical operational capabilities:

- **Backpressure control:** regulating flow rate so the system neither ingests nor holds more data than it can safely process.
- **Replay:** re-reading stored data to recover from failures, fix processing logic, or regenerate outputs.

Backpressure keeps the system alive when load surges. Replay enables recovery after errors occur or when data needs reprocessing. Both require observability; without measuring backlog and data age, operations teams cannot tell when to shed load, scale capacity, or start a replay.

## 2. Distinguishing Backpressure, Lag, and Latency

| Concept | Meaning | Question to answer |
|---|---|---|
| Backpressure | Downstream cannot consume fast enough, forcing upstream to slow down | Which operator or sink is bottlenecking the pipeline? |
| Consumer lag | Distance between the latest data position and what the consumer has processed/committed | How many records or how much time is the consumer behind? |
| End-to-end latency | Time from when an event occurred until its result is persisted at the destination | How long must end users wait? |
| Backlog | Count or volume of data awaiting processing | How much queued work has piled up? |
| Throughput | Rate of data passing through a boundary | How many records/bytes per second does the system process? |
| Freshness | Age of data at a point in the pipeline | How long has the oldest undelivered record been waiting? |

Consumer lag does not always equal latency. Kafka may show large offset lag for tiny recent records, or a few records may have been waiting a long time. Kinesis iterator age measures the age of the last record a consumer read relative to now, yet does not capture the span from application event creation until sink commit.

A system can experience backpressure at one operator without high end-to-end latency yet if buffers still absorb it. Conversely, a sink may stall after the consumer already committed offsets, leaving lag low while data fails to appear where users query it. Measure both individual stages and the full end-to-end journey.

## 3. How Does Backpressure Form?

Backpressure arises when the input rate exceeds the processing capacity of one or more components.

Suppose a producer emits 80,000 records/second, a processor handles 70,000 records/second, and a sink writes 60,000 records/second. The sink is the bottleneck. The end-to-end pipeline completes only around 60,000 records/second. If the producer keeps sending 80,000 records/second, the backlog grows by roughly 20,000 records/second.

~~~mermaid
flowchart LR
    P["Producer<br/>80k records/s"] --> B["Broker / stream"]
    B --> W["Processor<br/>70k records/s"]
    W --> S["Sink<br/>60k records/s"]
    S -. "Slow ACK" .-> W
    W -. "Buffer full" .-> B
    B -. "Rising lag" .-> P
~~~

Backlog changes according to:

\[
\Delta B = \lambda_{in} - \lambda_{out}
\]

Where `B` is backlog, `λin` is the incoming record rate, and `λout` is the rate of records successfully processed and committed at the destination. When `λin` exceeds `λout`, backlog grows. When `λout` exceeds `λin`, the system can drain the backlog.

Estimated drain time:

\[
T_{drain} \approx \frac{B}{\lambda_{out} - \lambda_{in}}
\]

This formula only holds when processing throughput exceeds ingestion rate and remains relatively steady.

### 3.1 Little's Law

For a stable system:

\[
L = \lambda W
\]

`L` is the average number of items in the system, `λ` is average throughput, and `W` is the average time an item spends in the system.

For example, a pipeline processing 10,000 events/second with an average of 50,000 events waiting or in flight has an average residence time of roughly 5 seconds. Do not apply this formula to forecast when load grows unbounded or throughput swings wildly.

## 4. Pinpointing Where the Bottleneck Lies

| Location | Signs | Common causes |
|---|---|---|
| Producer | Rising retries/throttling, high send latency | Writing too fast, hot partitions, insufficient broker capacity |
| Broker/stream | Rising write throttling or request latency | Under-provisioned shards/partitions, saturated disk/network |
| Consumer fetch | Slow polls/fetches, read throttling | Shared throughput contention, too many consumers |
| Processor | Rising CPU/busy time, rising input lag | Heavy logic, serialization, oversized state, skew |
| External dependency | Timeouts, retries, exhausted connection pools | Slow database, API, or search cluster |
| Sink | Rising ACK latency, delivery freshness, and retries | Destination out of capacity, unsuitable batching |
| Checkpoint/state | Prolonged or failing checkpoints | Large state, barrier alignment delays, slow storage |

Do not start by blindly adding workers. If the bottleneck is a database, adding consumer parallelism can overload the database further. If the bottleneck is a single hot partition, adding consumers cannot split one partition into multiple independent streams.

## 5. Flow Control at Each Boundary

### 5.1 Bounded Buffers

Buffers must be bounded. Unbounded queues can drive heap usage to OOM when consumers slow down. Finite buffers propagate pressure back upstream or force producers to slow down.

Monitor record counts, byte volume, time spent buffered, and buffer-full events.

### 5.2 Rate Limiting and Admission Control

Rate limiters cap producer send rates. Admission control can reject or defer lower-priority workloads when the system nears overload.

Options:

- Token bucket or leaky bucket at the application gateway.
- Concurrency caps in consumers.
- Write-rate caps into databases.
- Prioritizing critical events while deferring non-critical telemetry/batches.
- Using queues to absorb bursts within a pre-calculated window.

Never drop transactional data merely to keep latency low. If dropping is ever necessary, enforce an explicit policy covering data classes, auditing, and recovery.

### 5.3 Batching

Batching cuts request counts and overhead. Batches that are too small raise request rates; batches that are too large inflate latency, memory usage, and retry scope. Size batches around payload size, processing time, API limits, latency SLOs, and sink transaction sizes.

### 5.4 Controlled Retries

Retries suit transient failures such as throttling, timeouts, or network resets. Use exponential backoff and jitter so producers do not retry in lockstep.

\[
delay_n = random(0,\min(cap,base \times 2^n))
\]

Bound retry attempts or retry duration. Invalid payloads, unsupported schemas, or permission denials rarely resolve through retries; route those records to quarantine/DLQ.

### 5.5 Pause and Resume

Kafka consumers can pause partitions when downstream saturates and resume once capacity recovers. Consumers must still poll on schedule to preserve group membership and avoid rebalances caused by exceeding `max.poll.interval.ms`.

In Flink, backpressure propagates through network buffers from downstream back upstream. When a sink slows down, upstream operators receive fewer buffers and slow down record emission. This protects the pipeline, though if prolonged, source lag rises.

## 6. Backpressure with Amazon Kinesis Data Streams

Kinesis Data Streams stores records in shards. Producers write with `PutRecord`/`PutRecords`; consumers read via `GetRecords` or Enhanced Fan-Out `SubscribeToShard`.

### 6.1 Producer-Side Throttling

Signs include rising `WriteProvisionedThroughputExceeded`, higher `PutRecord`/`PutRecords` latency, or `ProvisionedThroughputExceededException`.

Common causes:

- Insufficient shards for write throughput.
- Skewed partition key distribution creating hot shards.
- One tenant/entity generating most of the traffic.
- Short bursts exceeding capacity.
- Aggressive producer retries compounding load.

Remediation steps:

1. Inspect per-shard throughput if enhanced shard-level metrics are enabled.
2. Inspect partition key distribution.
3. Choose partition keys with adequate cardinality and spread.
4. Increase shard count or switch to On-demand mode when suitable for the workload.
5. Apply retries with backoff and jitter.
6. Check `FailedRecordCount` and per-record errors in `PutRecords`; HTTP success does not mean every record succeeded.

### 6.2 Consumer-Side Throttling

With shared-throughput consumers, multiple consumers share a shard's read capacity. Options:

- Tune `GetRecords` batch size and processing time.
- Increase shard count when architecture and key distribution allow.
- Use Enhanced Fan-Out (EFO) when multiple consumers need independent throughput.
- Remove unnecessary consumers.
- Split critical workloads into separate streams when isolation is required.

EFO allocates dedicated read throughput up to 2 MB/second per shard per registered consumer and pushes records over HTTP/2 `SubscribeToShard`. Shared throughput imposes an aggregate read limit per shard that consumers must split.

### 6.3 Kinesis and Lambda Event Source Mapping

When Lambda reads Kinesis, event source mapping polls the stream and delivers batches to the function. Key settings:

- `BatchSize` and `MaximumBatchingWindowInSeconds`.
- `ParallelizationFactor`.
- `MaximumRetryAttempts` and `MaximumRecordAgeInSeconds`.
- `BisectBatchOnFunctionError`.
- `FunctionResponseTypes` with `ReportBatchItemFailures`.
- `DestinationConfig` for records discarded after configured retries.

Raising parallelization increases concurrency, yet also increases pressure on downstream databases or APIs. Monitor `Duration`, `Errors`, `Throttles`, and `IteratorAgeMilliseconds` together. Evaluate ordering semantics before increasing parallel processing.

## 7. Backpressure with Amazon MSK and Apache Kafka

Kafka divides topics into partitions. A consumer group processes each partition with at most one consumer member at a time. Active consumers in a group cannot exceed the number of partitions holding data to process.

### 7.1 Consumer Lag

Offset lag is the difference between the partition's latest offset and the offset committed by the consumer group. Time lag estimates the time needed to drain that offset lag at the current rate.

| MSK metric | Meaning |
|---|---|
| `MaxOffsetLag` | Largest lag across a topic's partitions |
| `OffsetLag` | Per-partition lag |
| `SumOffsetLag` | Sum of lag across partitions |
| `EstimatedTimeLag` | Estimated time to drain lag |
| `EstimatedMaxTimeLag` | Estimated time to drain the slowest partition |
| `RollingEstimatedTimeLagMax` | Trend of maximum time lag over a rolling window |

MSK consumer-lag metrics have prerequisites to appear: the consumer group must be in `STABLE` or `EMPTY` state; the group must have committed offsets; the group name must not contain colons; ASCII characters must be used so CloudWatch dimensions register. If metrics vanish, check rebalance/group state and offset commits before assuming the consumer is healthy.

### 7.2 Consumer Poll Loop

Consumers must call `poll` regularly to receive records and stay in the group protocol. Processing a batch too slowly on the same thread can exceed `max.poll.interval.ms`, marking the consumer dead and triggering a rebalance.

A safe pattern:

1. Poll records.
2. Enqueue records into a bounded worker queue.
3. Workers process and write to the sink.
4. Commit offsets only after processing/sink writes succeed.
5. Pause partitions when the queue fills.
6. Resume when the queue drains.
7. Keep the poll loop running within configured intervals.

Committing offsets before sink writes succeed risks losing records on crashes. Committing after sink writes means a crash before commit can cause reprocessing. Thus, idempotency and transaction semantics matter far more than merely picking auto-commit vs. manual commit.

### 7.3 Adding Partitions and Consumer Parallelism

Adding partitions can raise parallelism, subject to trade-offs:

- A consumer group cannot process one partition concurrently across multiple consumers.
- Key ordering is guaranteed only within a partition.
- Adding partitions can alter key-to-partition mapping for new records.
- Hot keys can still cause skew.
- Rebalances can temporarily dip throughput.
- Higher partition counts increase metadata and operational overhead.

### 7.4 Kafka Pause/Resume

When a sink slows down, pause affected partitions, cap queued records in the worker queue, lower `max.poll.records` if batches are oversized, use bounded executors, and avoid infinite blocking retries on the poll thread.

## 8. Backpressure in Managed Service for Apache Flink

Flink processes streams via an operator graph. Each operator receives records, transforms them, and forwards results downstream. When downstream falls behind, network buffers fill and backpressure propagates upstream.

~~~mermaid
flowchart LR
    A["Source"] --> B["Parse"]
    B --> C["Enrich"]
    C --> D["Aggregate"]
    D --> E["Sink"]
    E -. "Slow sink" .-> D
    D -. "Buffer full" .-> C
    C -. "Backpressure" .-> B
~~~

### 8.1 Identifying the Bottlenecked Operator

An operator can bottleneck due to:

- Synchronous I/O calling external APIs.
- One key receiving disproportionate records.
- Heavy state lookups or RocksDB contention.
- CPU-intensive serialization/deserialization.
- Slow sink commits.
- Checkpoint barriers waiting on upstream.
- One subtask handling far more data than peers.

Monitor per-operator input/output throughput, parallelism, CPU, container memory/disk, source lag, and checkpoint duration.

### 8.2 Optimizing Operators

- Increase parallelism on operators that scale independently.
- Use async I/O for external calls with bounded concurrency.
- Batch sink writes.
- Avoid synchronous per-record calls to remote services.
- Trim unnecessary state and optimize state keys.
- Mitigate hot keys with key salting or workload splitting where semantics allow.
- Set timeouts on external calls.
- Cap in-flight requests to avoid overloading downstream systems.

### 8.3 Metrics and Flink Versions

Managed Service for Apache Flink documents `backPressuredTimeMsPerSecond` and `busyTimeMsPerSecond` for the Flink 1.13 runtime. Do not assume these two metrics exist across every current runtime.

On newer runtimes, use version-supported metrics such as:

- `records_lag_max` for Kafka sources.
- `millisbehindLatest` for Kinesis sources.
- `Operator.numRecordsInPerSecond` and `Operator.numRecordsOutPerSecond`.
- `cpuUtilization`, `containerCPUUtilization`, and `containerMemoryUtilization`.
- `lastCheckpointDuration`, `lastCheckpointSize`, and `numberOfFailedCheckpoints`.
- `numRestarts` and runtime-specific state metrics.

Flink 2.2 changed metrics: `fullRestarts` was removed in favor of `numRestarts`; `uptime`/`downtime` were deprecated; some connector metrics also changed. When upgrading runtimes, audit CloudWatch alarms and dashboards.

## 9. Checkpoints, Snapshots, and Replay in Flink

| Mechanism | Goal | Usage |
|---|---|---|
| Checkpoint | Periodic state backup for job failure recovery | Created automatically by Flink on interval |
| Snapshot/Savepoint | User- or service-triggered state backup | Intentional updates, migrations, rollbacks, or restores |
| Source offset state | Read position in Kinesis/Kafka | Stored with state inside checkpoints when supported by the connector |

Managed Service for Apache Flink uses checkpoints to recover from failures. Snapshots restart applications from saved state. With snapshot configuration enabled, the service can create system snapshots during updates, scaling, or stops to preserve semantics per AWS documentation.

A checkpoint is not a copy of the entire raw stream. It holds application state and source positions. To reprocess historical data from scratch, design replay at the source and decide how to initialize fresh or compatible state.

### 9.1 Slow Checkpoints Add More Lag

Checkpointing snapshots state, aligns barriers, and writes state to storage. When checkpoints drag on, operators spend more time checkpointing, sources keep accumulating records, and subsequent checkpoints may be delayed.

Monitor `lastCheckpointDuration`, `lastCheckpointSize`, and `numberOfFailedCheckpoints`. Checkpointing too frequently adds overhead; checkpointing too rarely increases recovery rework.

### 9.2 Exactly-Once Requires End-to-End Design

Flink checkpointing preserves state and source positions, yet end-to-end exactly-once also depends on sinks. Sinks must support transactional commits or idempotent writes. When calling external APIs without idempotency, retries after failures can create duplicate side effects.

## 10. Backpressure and Delivery in Amazon Data Firehose

Amazon Data Firehose is a managed delivery service. It buffers records and delivers them to S3, Redshift, OpenSearch, Splunk, HTTP endpoints, and supported destinations.

Larger buffers typically produce larger objects/batches and fewer requests, while increasing delivery latency. Smaller buffers deliver data faster while increasing requests/overhead.

When a destination slows down or fails:

- Firehose retries according to the destination's retry policy.
- Data freshness increases as the oldest undelivered record ages.
- Delivery errors may appear in CloudWatch Logs.
- For DirectPut sources, data is retained up to 24 hours.
- If the source is Kinesis Data Streams or MSK, retry longevity depends on source stream/topic retention.
- Configure S3 backup for failed records or all records as required.

Never assume S3 backup automatically holds every delivery-failed record. Backup behavior depends on destination, transformations, and backup mode configuration.

### 10.1 Metrics to Monitor

- `IncomingBytes` and `IncomingRecords`.
- `ThrottledRecords`.
- `DeliveryToS3.DataFreshness` or the corresponding destination `DataFreshness` metric.
- Delivery success/failure metrics for OpenSearch, Redshift, Splunk, or HTTP endpoints.
- `BackupToS3.DataFreshness` when all-record backup is enabled.
- `ActivePartitionsLimit` and `PartitionCountExceeded` when using dynamic partitioning.

`DataFreshness` is the age of the oldest record waiting in Firehose. If it rises continuously, delivery is falling behind. If no metric emits, either the stream has no incoming data or delivery is stalled; inspect incoming metrics and destination logs together.

## 11. What Is Replay and When Is It Needed?

Replay means re-reading stored records to regenerate outputs. Scenarios:

- A consumer was stopped long enough to build a backlog.
- A code bug produced incorrect results.
- Schemas or enrichment logic changed.
- Rebuilding an analytics table or search index.
- Recovering after a sink outage.
- Investigating an incident or reconciling data.
- Launching a new consumer for a new use case.

Replay can read from source streams, Kafka topics, S3 archives, or DLQs. Each source has its own retention limits, ordering, and semantics.

### 11.1 Replay Is Not Retry

| Retry | Replay |
|---|---|
| Re-attempts a failed operation or record | Re-reads a dataset from a specified position |
| Usually happens automatically | Usually an intentional operational action |
| Uses backoff and retry policies | Uses offsets, sequence numbers, timestamps, or archives |
| Goal is completing the current attempt | Goal is reprocessing or regenerating outputs |

Replay requires an explicit scope, start/end boundaries, rate cap, destination, and deduplication policy. Never replay an entire production stream without understanding its side effects.

## 12. Replay from Amazon Kinesis Data Streams

Kinesis retains records for a retention period:

- Default 24 hours.
- Extendable up to 365 days.
- Retention beyond 24 hours incurs extra fees.
- Increasing retention does not restore records that already expired under the old retention.

Starting positions:

| Position | Meaning |
|---|---|
| `LATEST` | Starts from new records arriving after the consumer begins |
| `TRIM_HORIZON` | Starts from the oldest record still within retention |
| `AT_TIMESTAMP` | Starts from a specified Unix timestamp |
| `AT_SEQUENCE_NUMBER` | Starts at a specific sequence number |
| `AFTER_SEQUENCE_NUMBER` | Starts after a specific sequence number |

### 12.1 Replaying with a New Consumer

A safe way to test replay is creating a new consumer application with its own checkpoint/lease namespace. The new consumer can read from `TRIM_HORIZON` or `AT_TIMESTAMP` within retained data.

When using KCL, checkpoints live in the lease table. Changing `InitialPositionInStream` does not automatically overwrite existing checkpoints. Use a new application name/lease table for replay or reset checkpoints following a tested runbook.

### 12.2 Controlled Replay

- Pick timestamp or sequence boundaries.
- Record shard IDs and source retention.
- Read with a dedicated consumer.
- Throttle replay rate so the sink is not overloaded.
- Write results to a replay destination or staging table.
- Compare counts/checksums before merging.
- Deduplicate using event IDs.
- Log an audit trail with timestamp, owner, and scope.

If replaying the same stream into a production sink, distinguish replay events from real-time events so older results do not overwrite newer data.

## 13. Replay from Amazon MSK/Kafka

Kafka retains records by topic partitions and retention policies. Consumer groups store committed offsets; replay typically works by resetting to an earlier offset.

Offset reset options:

- `--to-earliest`: start from the earliest retained offset.
- `--to-latest`: skip current backlog and read from the tail.
- `--to-offset`: start from a specific offset.
- `--to-datetime`: start from the corresponding timestamp.
- `--shift-by`: shift offsets by a record count.

Example dry-run resetting a group to earliest:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server b-1.example.kafka.ap-southeast-1.amazonaws.com:9098 \
  --group orders-processor-replay \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

After verifying the dry-run output, re-run with `--execute`. The consumer group must be stopped or have zero active consumers before resetting offsets.

### 13.1 Using a Separate Consumer Group

For large replays, creating a new consumer group is usually safer. The new group tracks its own offsets without altering production consumer progress. However, account for extra broker read load and sink capacity.

### 13.2 Retention and Log Compaction

- Delete retention purges segments by time or size.
- Log compaction retains the latest value per key and may discard older records.
- A compacted topic is not a complete archive of every historical event.

If you need to replay full business history, configure time-based topic retention appropriately or archive raw events to S3 before compaction drops older versions.

## 14. Replay with Lambda Event Source Mapping

Lambda can read Kinesis or MSK via event source mappings. Settings governing retries/replay include `StartingPosition`, `MaximumRecordAgeInSeconds`, `MaximumRetryAttempts`, `BisectBatchOnFunctionError`, `FunctionResponseTypes`, `DestinationConfig`, and `ParallelizationFactor`.

With unbounded retries, records can keep retrying until retention expires. With maximum record age or attempt limits, expired records are discarded per policy and routed to the failure destination if configured.

Do not merely re-enable a disabled mapping expecting it to read from the beginning. Starting position applies only at mapping creation; an existing mapping keeps its own progress checkpoint. Create a separate mapping/consumer or follow a tested reset procedure.

## 15. Replay and Recovery with Flink

Flink stores operator state and source offsets in checkpoints/snapshots. Restarting from a snapshot resumes from the saved state and source position.

Three distinct goals:

1. **Crash recovery:** use the latest checkpoint to resume near the point of failure.
2. **Code/config rollback:** restore a snapshot compatible with the prior version.
3. **Reprocess historical data:** re-read from an older source offset/timestamp and initialize state per replay logic.

The third goal requires dedicated design. Resetting source offsets while keeping old aggregation state causes double-counting. Restoring old state with newer source offsets can skip data. Coordinate state snapshots, source positions, and sink transactions.

Before replaying:

- Verify snapshot compatibility with operator UIDs and state schemas.
- Choose source offsets/timestamps.
- Decide whether state starts empty or from a restore.
- Use a staging sink or transactional sink.
- Check duplicate and late-event handling.
- Rate-limit replay and cap production load impact.
- Plan cutover from replay output to live output.

## 16. Dead-Letter Queues and Quarantine

A poison record is one that repeatedly fails due to payload, schema, business rules, or dependencies. If a failing record blocks an entire partition/batch, throughput for trailing records stalls.

Workflow:

1. Determine whether the error is retryable.
2. If it is a permanent data error, move the record to quarantine/DLQ.
3. Store the original payload, event ID, source position, error code, and timestamp.
4. Continue processing remaining records if semantics permit.
5. Fix the data or consumer logic.
6. Replay the DLQ through a controlled pipeline.
7. Monitor for duplicates and verify outcomes.

Never write full sensitive payloads to logs. Quarantine buckets/queues require encryption, retention, access controls, and auditing.

### 16.1 Partial Batch Failures

With Lambda Kinesis/SQS event source mappings, partial batch responses let the function report exactly which items failed. This avoids retrying the whole batch when only one record failed. With Kinesis, watch ordering: one failed record can affect how subsequent sequence numbers are handled depending on configuration.

## 17. Defining Latency for Streaming

An event can carry multiple timestamps:

- `eventCreatedAt`: when the business event occurred.
- `producedAt`: when the producer sent the event.
- `brokerIngestedAt`: when the stream/broker received the record.
- `consumerReceivedAt`: when the processor read the record.
- `processingStartedAt`: when processing began.
- `processingCompletedAt`: when logic finished.
- `sinkCommittedAt`: when the destination confirmed the write.

| Latency | Formula | Purpose |
|---|---|---|
| Producer latency | `producedAt - eventCreatedAt` | Time spent preparing/sending from the application |
| Ingestion latency | `brokerIngestedAt - producedAt` | Time to ingest data into the broker |
| Queue/consumer lag age | `consumerReceivedAt - brokerIngestedAt` | Wait time before the consumer reads the record |
| Processing latency | `processingCompletedAt - processingStartedAt` | Business logic execution time |
| Sink latency | `sinkCommittedAt - processingCompletedAt` | Time to write/commit results |
| End-to-end latency | `sinkCommittedAt - eventCreatedAt` | Time from business occurrence to persisted result |

Synchronize clocks across hosts with NTP/chrony. Clock skew can yield negative or misleading timestamp deltas. With event-time processing, business timestamps and watermarks matter more than processing time.

## 18. Event Time, Processing Time, and Watermarks

- **Event time:** when the event actually occurred in the source system.
- **Ingestion time:** when the event entered the stream processor.
- **Processing time:** when the processor executed the logic.
- **Watermark:** an estimate that the system has received most events with event times earlier than a threshold.

Watermarks enable handling out-of-order events and window aggregations. Stalled watermarks can result from idle sources, slow partitions, or late-arriving events. A window failing to emit does not always mean slow CPU; the watermark may not have crossed the window end yet.

Separate processing lag, event-time lag, late-event rate, and sink commit lag. Never rely on a single lag metric to represent every form of latency.

## 19. End-to-End Pipeline Observability

~~~mermaid
flowchart TD
    A["Producer metrics"] --> B["Broker metrics"]
    B --> C["Consumer lag"]
    C --> D["Processor metrics"]
    D --> E["Sink delivery metrics"]
    E --> F["Business freshness / E2E latency"]
    A -. "trace/event ID" .-> F
~~~

| Group | Metrics to monitor |
|---|---|
| Producer | Incoming records/bytes, send latency, errors, throttling, retry count |
| Broker/stream | Shard/partition utilization, request latency, write throttling, disk/network |
| Consumer | Iterator age, offset lag, time lag, records consumed, poll/fetch latency |
| Processor | Input/output records per second, processing duration, CPU, memory, busy/backpressured time if supported by runtime |
| State/checkpoint | Checkpoint duration/size, failed checkpoints, restart count |
| Sink | Write/ACK latency, retries, error rate, throttling, freshness |
| Business | Events created, events committed, duplicate count, missing event count, p95/p99 latency |

### 19.1 Event Identity and Correlation

Every event should include a unique `eventId`, `eventType`, `schemaVersion`, `entityId`/partition key, `eventCreatedAt`, producer name, and `correlationId`/`traceId`.

Do not use `eventId`, `orderId`, or `customerId` as CloudWatch metric dimensions due to extreme cardinality. Record them in logs/traces; keep metric dimensions bounded to low-cardinality fields like service, stream, topic, consumer group, or environment.

## 20. CloudWatch Metrics for Kinesis Data Streams

Kinesis emits metrics in the `AWS/Kinesis` namespace. Basic stream-level metrics emit every minute; enhanced shard-level metrics must be enabled separately and can incur extra charges. Standard metric data follows CloudWatch metrics retention.

| Metric | Meaning | Usage |
|---|---|---|
| `GetRecords.IteratorAgeMilliseconds` | Age of the last record read in `GetRecords` | Track whether consumers are falling behind |
| `IteratorAgeMilliseconds` | Shard-level iterator age | Pinpoint hot shards or slow consumers |
| `ReadProvisionedThroughputExceeded` | Read throttling | Identify insufficient read capacity |
| `WriteProvisionedThroughputExceeded` | Write throttling | Identify insufficient write capacity |
| `IncomingBytes` / `IncomingRecords` | Data sent by producers | Detect bursts and hot shards |
| `OutgoingBytes` / `OutgoingRecords` | Data read by consumers | Measure read throughput |
| `GetRecords.Latency` | Duration of `GetRecords` API calls | Spot slow read paths |
| `SubscribeToShardEvent.MillisBehindLatest` | Lag of an EFO consumer | Monitor push consumers |

AWS recommends alarming on the `Maximum` statistic of `IteratorAgeMilliseconds`. When iterator age exceeds roughly 50% of the retention period, treat it as a warning that records risk expiring before consumers catch up. Actual alarm thresholds should be much lower depending on RPO and recovery time.

## 21. CloudWatch Metrics for MSK

MSK provides broker metrics and consumer lag metrics. More granular monitoring levels can incur additional costs. Use `PER_TOPIC_PER_PARTITION` when investigating per-partition lag; use the default level for general operations.

| Metric | Meaning |
|---|---|
| `MaxOffsetLag` | Maximum lag on a topic |
| `OffsetLag` | Per-partition lag |
| `SumOffsetLag` | Total offset backlog |
| `EstimatedTimeLag` | Estimated drain time |
| `EstimatedMaxTimeLag` | Drain time for the slowest partition |
| `KafkaDataLogsDiskUsed` | Disk usage |
| `RequestTime` | Broker request processing time |
| `TrafficShaping` | Packets shaped/dropped/queued |

Consumer lag metrics are not always emitted. During group rebalances, before any committed offsets exist, or when group names are invalid for CloudWatch dimensions, metrics may be absent. Supplement with client-side metrics and logs to avoid a false healthy signal.

## 22. Metrics for Managed Service for Apache Flink

| Metric | Meaning |
|---|---|
| `records_lag_max` | Maximum record lag for Kafka sources |
| `millisbehindLatest` | Milliseconds consumer lags behind Kinesis head |
| `Operator.numRecordsInPerSecond` | Operator input throughput |
| `Operator.numRecordsOutPerSecond` | Operator output throughput |
| `cpuUtilization` | Task manager JVM CPU |
| `containerCPUUtilization` | Whole-container CPU |
| `containerMemoryUtilization` | Whole-container memory |
| `lastCheckpointDuration` | Latest checkpoint duration |
| `lastCheckpointSize` | Latest checkpoint size |
| `numberOfFailedCheckpoints` | Failed checkpoint count |
| `numRestarts` | Restart count on newer runtimes |

Verify metrics against your exact Flink version and connectors. For example, `backPressuredTimeMsPerSecond` was published by AWS for Managed Service for Apache Flink runtime 1.13; on Flink 2.2, use the corresponding runtime metrics and connector measurements rather than alarming on retired metrics.

## 23. Metrics for Amazon Data Firehose

Firehose emits metrics in the `AWS/Firehose` namespace every minute. Bursts lasting only a few seconds may not stand out clearly in one-minute metrics.

| Metric | Meaning |
|---|---|
| `IncomingBytes` / `IncomingRecords` | Ingestion volume |
| `ThrottledRecords` | Throttled records |
| `DeliveryToS3.DataFreshness` | Age of oldest buffered record before S3 delivery |
| `DeliveryToOpenSearchService.DataFreshness` | Age of oldest record before OpenSearch delivery |
| `DeliveryToRedshift.DataFreshness` | Age of oldest record before Redshift delivery |
| `DeliveryToHttpEndpoint.DataFreshness` | Age of oldest record before HTTP endpoint delivery |
| `DeliveryToS3.Success` | Successful put count |
| `BackupToS3.DataFreshness` | Freshness of backup data when configured |
| `PartitionCountExceeded` | Active partition limit exceeded under dynamic partitioning |

Continuously rising `DataFreshness` usually points to an overwhelmed destination, destination errors, overly low buffering hints, or prolonged delivery retries. Inspect error logs and destination metrics together to distinguish causes.

## 24. Building Latency SLIs/SLOs and Alarms

SLOs should express business outcomes rather than just CPU or queue depth.

Examples:

- 99% of events are written to the sink within 3 seconds.
- 99.9% of records do not exceed 60 seconds of consumer lag.
- Post-burst backlogs drain within 10 minutes.
- No critical records approach retention expiration.
- Failed checkpoint rate does not climb continuously.
- DLQ holds no records older than 15 minutes.

These thresholds are examples only. Define yours from workload profile, retention, business criticality, and recovery objectives.

### 24.1 Multi-Signal Alarms

A useful alarm might combine:

- Continuously rising `IteratorAgeMilliseconds`.
- `ReadProvisionedThroughputExceeded` greater than 0.
- `IncomingRecords` exceeding `OutgoingRecords` over multiple periods.
- High consumer CPU or memory.
- Rising sink ACK latency.
- Rising error/retry rates.

High lag can stem from a legitimate producer burst. High CPU may not cause latency if throughput remains sufficient. Combine signals to reduce false positives.

### 24.2 Example CloudWatch Alarm for Kinesis Iterator Age

~~~bash
aws cloudwatch put-metric-alarm \
  --alarm-name orders-stream-iterator-age-high \
  --namespace AWS/Kinesis \
  --metric-name GetRecords.IteratorAgeMilliseconds \
  --dimensions Name=StreamName,Value=orders-events \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 3 \
  --datapoints-to-alarm 2 \
  --threshold 30000 \
  --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching
~~~

The 30,000 ms threshold in this example is 30 seconds, not a universal default. Tune it to your SLO and retention. `notBreaching` is illustrative only; missing metrics could mean the consumer stopped entirely, so production requires separate heartbeat/consumer availability alarms.

### 24.3 p95 and p99

Average latency can hide tail latency. Use histograms or metric distributions to inspect p50, p95, and p99. If 95% of events take 100 ms while 5% take 20 seconds, the average misrepresents the tail experience.

## 25. Diagnostic Workflow When Lag Increases

~~~mermaid
flowchart TD
    A["Lag / freshness alarm"] --> B{"Did producer rate increase?"}
    B -->|Yes| C["Check bursts, partition keys, write throttling"]
    B -->|No| D{"Did consumer throughput drop?"}
    D -->|Yes| E["Check CPU, memory, processing time, rebalances"]
    D -->|No| F{"Is sink ACK slow?"}
    F -->|Yes| G["Check database/API, retries, connections"]
    F -->|No| H["Check checkpoints, network, metric gaps"]
    C --> I["Mitigate + monitor drain ETA"]
    E --> I
    G --> I
    H --> I
~~~

Follow this order:

1. Confirm the source is still receiving records.
2. Compare incoming and outgoing throughput.
3. Inspect lag per shard/partition, not only totals.
4. Check throttling and broker/stream capacity.
5. Check consumer group state/rebalances.
6. Check operator input/output rates and CPU/memory.
7. Check sink latency, retries, and connection pools.
8. Check checkpoint duration and failed checkpoints.
9. Estimate drain time and retention risk.
10. Choose a mitigation: throttle producers, scale consumers, add capacity, pause lower-priority workloads, or quarantine bad records.

Never change multiple variables at once. Record the timestamp and effect of each mitigation to isolate the true root cause.

## 26. Case Study: Order Pipeline Delayed After a Flash Sale

An e-commerce application emits `OrderCreated` events to Kinesis Data Streams. Managed Service for Apache Flink enriches events, sums revenue per store, and writes results to Aurora. During a flash sale, event volume quadruples.

### Symptoms

- `IncomingRecords` surges sharply.
- `IteratorAgeMilliseconds` climbs from 200 ms to 45 seconds.
- Flink `millisbehindLatest` rises.
- Flink CPU sits at 55%, yet sink ACK latency jumps from 40 ms to 2 seconds.
- `lastCheckpointDuration` increases.
- Aurora connection pool is nearly exhausted.

### Analysis

CPU is not the primary bottleneck. Flink is experiencing sink backpressure because Aurora is slow. As the sink stalls, aggregate operators emit fewer records, source lag climbs, and checkpoints take longer because pipeline progress slows down.

### Actions

1. Cap sink write concurrency.
2. Batch upserts to reduce round trips.
3. Increase connection capacity carefully and inspect query plans.
4. Temporarily shed non-critical analytics workloads.
5. Monitor checkpoint duration and source lag.
6. Once the sink stabilizes, raise Flink parallelism if operator throughput is still insufficient.
7. Calculate drain ETA before retention risk hits.
8. Reconcile order counts and totals once the backlog clears.

Raising Flink parallelism upfront would have overloaded Aurora even further. Identify the sink as the bottleneck and throttle concurrency first.

## 27. Lab: Creating a Kinesis Stream, Observing Lag, and Replaying

Run this lab in an AWS sandbox. Never run on a production stream.

### Step 1: Create an On-demand Stream

~~~bash
aws kinesis create-stream \
  --stream-name orders-events-lab \
  --stream-mode-details StreamMode=ON_DEMAND \
  --region ap-southeast-1
~~~

Wait for the stream to become `ACTIVE`:

~~~bash
aws kinesis describe-stream-summary \
  --stream-name orders-events-lab \
  --region ap-southeast-1
~~~

### Step 2: Increase Retention for the Lab

~~~bash
aws kinesis increase-stream-retention-period \
  --stream-name orders-events-lab \
  --retention-period-hours 72 \
  --region ap-southeast-1
~~~

72-hour retention is illustrative. Retention beyond 24 hours may incur charges.

### Step 3: Send Records

Create `event.json`:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "orderId": "order-1001",
  "amount": 125000,
  "eventCreatedAt": "2026-11-20T10:00:00Z"
}
~~~

Send the record using `fileb`:

~~~bash
aws kinesis put-record \
  --stream-name orders-events-lab \
  --partition-key order-1001 \
  --data fileb://event.json \
  --region ap-southeast-1
~~~

Send multiple records with different partition keys to generate load and observe distribution.

### Step 4: Read from TRIM_HORIZON

Get the shard ID:

~~~bash
aws kinesis list-shards \
  --stream-name orders-events-lab \
  --region ap-southeast-1
~~~

Get an iterator:

~~~bash
aws kinesis get-shard-iterator \
  --stream-name orders-events-lab \
  --shard-id shardId-000000000000 \
  --shard-iterator-type TRIM_HORIZON \
  --region ap-southeast-1
~~~

Pass the returned `ShardIterator` to `GetRecords`. Data in the response is base64-encoded; decode before parsing JSON.

### Step 5: Test Replaying from a Timestamp

~~~bash
aws kinesis get-shard-iterator \
  --stream-name orders-events-lab \
  --shard-id shardId-000000000000 \
  --shard-iterator-type AT_TIMESTAMP \
  --timestamp 1795168800 \
  --region ap-southeast-1
~~~

Timestamp is in Unix epoch seconds; pick a timestamp within retention. If the timestamp precedes the trim horizon, Kinesis returns from the oldest retained record.

### Step 6: Observe CloudWatch

Monitor the `AWS/Kinesis` namespace:

- `GetRecords.IteratorAgeMilliseconds`.
- `IncomingRecords` and `IncomingBytes`.
- `ReadProvisionedThroughputExceeded`.
- `WriteProvisionedThroughputExceeded`.

Run a deliberately slow test consumer to watch iterator age climb, then speed up processing and measure drain time.

### Step 7: Verify Safe Replay

- Record `eventId` in the sink.
- Send the same record twice.
- Confirm the sink produces only one business effect.
- Replay from an earlier timestamp.
- Reconcile event counts and business totals.
- Document replayed record counts and completion time.

### Step 8: Cleanup

~~~bash
aws kinesis delete-stream \
  --stream-name orders-events-lab \
  --enforce-consumer-deletion \
  --region ap-southeast-1
~~~

Delete the stream only after finishing the lab and confirming no consumers still need the data.

## 28. Common Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Kinesis IteratorAge rises steadily | Consumer processing slower than ingestion | Check processing time, sink latency, CPU/memory, and shard lag |
| Kinesis write throttling | Insufficient shard capacity or hot partition key | Analyze key distribution, add shards, or evaluate On-demand |
| Kinesis read throttling | Consumers sharing throughput | Use EFO, reduce consumers, or increase capacity |
| KCL MillisBehindLatest high | Slow record processor or downstream blocking | Inspect `processRecords.Time`, `Success`, and dependency calls |
| MSK MaxOffsetLag rising | Consumer group falling behind | Check partition skew, consumer throughput, and rebalances |
| MSK lag metrics missing | Group unstable, no committed offsets, or invalid dimension | Check group state, ASCII naming, and committed offsets |
| Continuous Kafka rebalances | Poll loop blocked or `max.poll.interval.ms` too low | Decouple processing from poll thread, check heartbeats and processing time |
| Flink millisbehindLatest rising | Source not consumed fast enough | Check operator throughput, CPU, memory, and sink |
| Low Flink output rate | Operator or sink bottleneck | Compare per-operator input/output rates and dependencies |
| Rising Flink checkpoint duration | Large state, barrier alignment, or slow storage | Inspect checkpoint stages, state size, and operator progress |
| Repeated Flink checkpoint failures | Timeouts, resource pressure, or snapshot incompatibility | Check failed checkpoints, logs, and state compatibility |
| Firehose DataFreshness rising | Slow destination or prolonged retries | Check destination capacity, retry policy, and error logs |
| Firehose ThrottledRecords rising | Ingestion exceeding quota | Check `IncomingBytes`/`Records` and request limits |
| Missing Firehose DataFreshness | No active deliveries or metric not emitted under config | Check incoming metrics, backup settings, and destination metrics |
| Replay creates duplicates | Non-idempotent sink or wrong commit timing | Use event IDs, deduplication, and commit after sink success |
| Replay finds no old records | Retention expired or compaction dropped records | Check retention, archives, and offset boundaries |
| Low lag yet stale dashboard | Consumer commits before sink or slow sink pipeline | Measure sink commit time and end-to-end freshness |
| Backpressure on a single key | Hot key/partition or skew | Analyze key distribution, salting, or workload separation |
| Backlog persists despite scaling consumers | Sink or broker is the bottleneck | Measure end-to-end throughput before scaling further |
| Latency rises while throughput stays flat | Tail latency or one slow partition | Track p95/p99 and per-partition/shard lag |

## 29. Best Practices

### Backpressure and Flow Control

- Use bounded queues and cap in-flight requests.
- Retry with exponential backoff and jitter.
- Set timeouts on every external dependency.
- Isolate critical and non-critical consumers.
- Do not scale consumers past sink capacity.
- Monitor lag per shard/partition and key distribution.
- Pause/resume or rate-limit when downstream saturates.
- Prioritize critical records per business policy.

### Replay and Recovery

- Size retention around RTO and maximum incident fix time.
- Archive raw events to S3 when history longer than stream retention is required.
- Use a separate consumer group for large replays.
- Never reset production offsets while consumers are running.
- Maintain checkpoints/snapshots and test restore compatibility.
- Use event IDs and idempotent sinks.
- Route replay outputs to staging before merging.
- Keep an audit trail for every replay execution.
- Never treat increasing retention as recovering already-expired data.

### Observability

- Measure end-to-end latency, not just processor duration.
- Track p50/p95/p99 and maximum lag.
- Set alarms well before backlogs approach retention expiration.
- Monitor ingestion, processing, checkpoints, and sinks.
- Include correlation IDs and event IDs in logs/traces.
- Avoid high-cardinality metric dimensions.
- Re-verify dashboards/alarms after runtime or connector upgrades.
- Check metric emission prerequisites before assuming missing data means healthy.

### Reliability and Data Correctness

- Commit offsets only after sink commits succeed.
- Use transactional sinks or idempotency whenever side effects occur.
- Quarantine poison records instead of retrying forever.
- Design schema evolution and compatibility.
- Test duplicates, late events, and out-of-order events.
- Rehearse replays, checkpoint restores, and sink outages.
- Keep source retention long enough for recovery to complete.

## 30. Practice Exercises

1. How does backpressure differ from consumer lag?
2. Why does low consumer lag not guarantee low end-to-end latency?
3. If a producer emits 80,000 records/s and a sink processes 60,000 records/s, how much does the backlog grow per second?
4. When can Little's Law be used to estimate latency?
5. Why is a bounded buffer safer than an unbounded queue?
6. When should you use rate limiting instead of scaling consumers?
7. What does Kinesis `IteratorAgeMilliseconds` reflect?
8. Why must Kinesis retention be sized around recovery time?
9. What are the current default and maximum Kinesis retention periods?
10. What kind of contention does Enhanced Fan-Out solve?
11. Why might adding shards fail to resolve a sink bottleneck?
12. How do Kinesis `TRIM_HORIZON`, `LATEST`, and `AT_TIMESTAMP` differ?
13. Why does increasing retention not restore expired records?
14. How do MSK `MaxOffsetLag` and `EstimatedTimeLag` differ?
15. Why can a consumer group rebalance increase lag?
16. Why must the poll loop not be blocked by long downstream processing?
17. Why can adding Kafka partitions change key-to-partition mapping?
18. How does Flink backpressure propagate from sink back to source?
19. How do checkpoints and snapshots differ?
20. Why can rising Flink checkpoint duration increase source lag?
21. Why does processor-level exactly-once not automatically guarantee exactly-once for external APIs?
22. What does Firehose `DataFreshness` measure?
23. How long does DirectPut Firehose retain data at most when the destination is unavailable?
24. Why does replay require an idempotent sink?
25. Why does replaying from a Kafka compacted topic not guarantee restoring full event history?
26. How does event time differ from processing time?
27. Can a stalled watermark delay window output even when CPU is low?
28. Which metrics should you monitor to detect whether a sink is causing backpressure?
29. Why use p95/p99 instead of average latency alone?
30. What must be verified before resetting production consumer offsets?

### Suggested Answers

1. Backpressure is a flow-control signal caused by a slow downstream; lag is the consumer's progress gap behind the latest data.
2. Consumers may commit offsets before the sink finishes, or the sink may have its own internal queue.
3. Grows by 20,000 records/s.
4. When the system is stable and throughput is relatively steady.
5. Bounded buffers cap memory and exert flow control; unbounded queues can cause OOM.
6. When producer bursts exceed short-term capacity or downstream dependencies need protection.
7. Age of the last record read by the consumer relative to the current time.
8. Because expired data can no longer be replayed from the stream.
9. 24 hours default, up to 365 days maximum.
10. It gives each registered consumer dedicated read throughput per shard.
11. Because the sink still writes only at its existing rate.
12. `TRIM_HORIZON` reads from the oldest retained record; `LATEST` reads new records; `AT_TIMESTAMP` reads from a specified timestamp.
13. Records already trimmed from the stream cannot be recovered simply by raising retention.
14. `MaxOffsetLag` is the largest offset count gap; `EstimatedTimeLag` is the estimated time to drain it.
15. Partition ownership shifts, some partitions pause processing briefly, and metrics may pause while the group is unstable.
16. Consumers can exceed `max.poll.interval.ms`, get evicted from the group, and trigger rebalances.
17. Key-to-partition hashing for new records can map to different partitions once partition count increases.
18. Downstream network buffers fill up, preventing upstream operators from emitting more records and forcing them to slow down.
19. Checkpoints recover state automatically; snapshots/savepoints are triggered/managed backups for intentional restores.
20. The job spends more time snapshotting and less time processing, causing source lag to rise.
21. An external API may execute a request and time out before returning a response; retries can trigger duplicate side effects.
22. Age of the oldest record waiting for delivery inside Firehose.
23. 24 hours.
24. Replay can deliver the same event multiple times.
25. Compaction can discard older versions per key.
26. Event time is when the business event occurred; processing time is when the processor executes logic.
27. Yes. Windows wait for the watermark to pass the window boundary.
28. Sink ACK latency, retry/error rates, write throughput, and processor output rates.
29. Averages mask tail latency affecting a subset of records.
30. Stopped consumers, offset boundaries, retention, sink idempotency, expected duplicates, and a rollback plan.

## 31. Interview Questions

### Is backpressure always a bug?

No. Backpressure is a protective mechanism preventing downstream overload. The problem is prolonged backpressure driving up lag and latency. Identify the root cause and determine whether the system drains backlogs within SLO.

### Why can increasing consumer count make a system slower?

New consumers can contend for broker throughput, trigger rebalances, increase concurrent sink writes, and open more connections. If the sink is the bottleneck, adding consumers only increases pressure.

### What problem does Kinesis EFO solve?

EFO allocates dedicated read throughput to registered consumers, avoiding multiple consumers sharing shard read throughput. It does not expand sink capacity and incurs separate charges.

### Why might MSK consumer lag metrics be missing?

The group may be unstable, have no committed offsets yet, or have a consumer group name incompatible with CloudWatch dimension rules. Check group health and client metrics.

### How do you identify which operator causes backpressure in Flink?

Compare input/output throughput, parallelism, busy/CPU metrics, container memory, source lag, sink ACKs, and checkpoint duration per operator/task. Also inspect per-subtask skew.

### Is checkpointing a historical replay mechanism?

No. Checkpoints restore state and source positions near the saved point. Historical replay requires re-reading records from source offsets/timestamps or an archive.

### How do you prevent duplicates during replay?

Use stable event IDs, idempotent writes, a deduplication store, or transactional sinks. Record an audit replay ID and verify source/sink commit semantics.

### Why does end-to-end latency require a sink timestamp?

Consumer lag only shows how far the consumer has read. Sinks can lag or commit long after the consumer read or committed offsets. The sink commit timestamp reveals when results actually become usable.

### When should you archive a stream to S3?

When you need replay beyond Kinesis/MSK retention, historical audits, or dataset regeneration without putting heavy load on production streams.

### How do you choose a retention period?

Base it on incident detection time, code/dependency fix time, backlog drain time, RTO, and cost. Retention must exceed the total time required to recover and reprocess.

## 32. Checklist Before Taking a Streaming Pipeline to Production

### Capacity and Backpressure

- [ ] Baseline and peak throughput measured.
- [ ] Partition key/shard distribution avoids severe hot spots.
- [ ] Consumer parallelism matches shards/partitions.
- [ ] Sink capacity and connection limits verified.
- [ ] Buffers are bounded with a flow-control policy.
- [ ] Retries use backoff, jitter, timeouts, and max attempts.
- [ ] Pause/resume or admission control mechanism in place.

### Replay and Data Correctness

- [ ] Retention covers recovery objectives.
- [ ] Archive exists if long-term history is required.
- [ ] Replay boundaries defined by timestamp/offset/sequence.
- [ ] Separate consumer group or lease namespace ready for replay.
- [ ] Sink idempotency and deduplication tested.
- [ ] Checkpoints/snapshots enabled and restores rehearsed.
- [ ] DLQ/quarantine has an owner, retention, and replay workflow.
- [ ] Schema evolution and late/out-of-order events tested.

### Observability and Latency

- [ ] Source ingest, consumer lag, processor throughput, and sink freshness tracked.
- [ ] End-to-end timestamps and correlation IDs implemented.
- [ ] p95/p99 latency SLIs defined.
- [ ] Alarms fire before records approach retention expiration.
- [ ] Dashboards exist per stream/topic/shard/partition/operator.
- [ ] Alarms exist for checkpoint duration/failures and sink retries.
- [ ] Metric support verified for exact runtime/connector versions.
- [ ] Missing metrics are never assumed healthy by default.

### Operations

- [ ] Runbooks exist for lag spikes, sink outages, replays, and offset resets.
- [ ] Change/approval workflow exists for production replays.
- [ ] Replay rate limiting configured.
- [ ] Post-replay reconciliation procedure defined.
- [ ] CloudWatch alarms have owners and escalation paths.
- [ ] Costs budgeted for enhanced metrics, EFO, retention, and archives.
- [ ] Failure and recovery rehearsed under near-production load.

## 33. Official References

- [Monitor Amazon Kinesis Data Streams with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Troubleshoot Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/troubleshooting-consumers.html)
- [Change the Kinesis Data Streams retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Kinesis Data Streams starting positions](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_StartingPosition.html)
- [Develop enhanced fan-out consumers](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Monitor the Kinesis Client Library with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-kcl.html)
- [Handle Kinesis consumer startup, shutdown, and throttling](https://docs.aws.amazon.com/streams/latest/dev/kinesis-record-processor-additional-considerations.html)
- [Lambda parameters for Kinesis event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-kinesis-parameters.html)
- [Monitor consumer lags in Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/consumer-lag.html)
- [Amazon MSK metrics for CloudWatch](https://docs.aws.amazon.com/msk/latest/developerguide/metrics-details.html)
- [Amazon MSK consumer groups](https://docs.aws.amazon.com/msk/latest/developerguide/msk-consumer-groups.html)
- [Amazon MSK topic configuration](https://docs.aws.amazon.com/msk/latest/developerguide/msk-configuration-properties.html)
- [Monitoring Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/monitoring.html)
- [Metrics and dimensions in Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/metrics-dimensions.html)
- [Use CloudWatch alarms with Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/monitoring-metrics-alarms.html)
- [Implement fault tolerance in Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/how-fault.html)
- [Manage application backups using Flink snapshots](https://docs.aws.amazon.com/managed-flink/latest/java/how-snapshots.html)
- [Troubleshoot Flink checkpoints](https://docs.aws.amazon.com/managed-flink/latest/java/troubleshooting-checkpoints.html)
- [Best practices for Managed Service for Apache Flink](https://docs.aws.amazon.com/managed-flink/latest/java/best-practices.html)
- [Monitor Amazon Data Firehose with CloudWatch metrics](https://docs.aws.amazon.com/firehose/latest/dev/monitoring-with-cloudwatch-metrics.html)
- [Troubleshoot errors in Amazon Data Firehose](https://docs.aws.amazon.com/firehose/latest/dev/troubleshooting.html)
- [Handle data delivery failures in Amazon Data Firehose](https://docs.aws.amazon.com/firehose/latest/dev/retry.html)
- [Amazon Data Firehose quotas and limits](https://docs.aws.amazon.com/firehose/latest/dev/limits.html)
- [Pause and resume Amazon Data Firehose delivery](https://docs.aws.amazon.com/firehose/latest/dev/pause-restart-stream.html)

# Managed Service for Apache Flink and Stateful Stream Processing

Amazon Managed Service for Apache Flink is a managed service for building and operating streaming data processing applications with Apache Flink. It fits when data arrives continuously and applications need time-based computations, event correlation, keyed grouping, windowing, pattern detection, or maintaining state across events. Typical examples include transaction fraud detection, per-minute product metrics, IoT device monitoring, clickstream analytics, and data enrichment before writing to downstream systems.

The key distinction of stateful stream processing is that the application does not merely process each record in isolation. It can remember an account's transaction count, total revenue over a time window, user session state, or results accumulated across partitions. When a task fails, state must be restored consistently with the source read position and sink write state. Apache Flink provides state, checkpoints, event time, and recovery mechanisms; Managed Service for Apache Flink manages the runtime infrastructure, AWS integrations, monitoring, and operational lifecycle actions.

This lesson covers the stateful stream processing model, DataStream API and Table API/SQL, key/window/time semantics, checkpoints and snapshots, exactly-once guarantees, scaling, connectors, deployment, and operations on AWS.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Explain the role of Apache Flink in streaming architectures and distinguish stateless from stateful processing.
- Distinguish sources, transformations/operators, keyed state, operator state, windows, sinks, and runtime tasks.
- Choose processing time, ingestion time, or event time; understand watermarks, late events, and idle partitions.
- Design keyed state, TTL, windows, and serialization aligned with business requirements.
- Distinguish checkpoints, savepoints, application snapshots, system snapshots, and enhanced snapshots.
- Design fault recovery and understand conditions for application-level and end-to-end exactly-once semantics.
- Choose DataStream API, Table API, or SQL for a workload.
- Connect Kinesis Data Streams, Amazon MSK, Amazon S3, Data Firehose, and supported sinks.
- Configure parallelism, `maxParallelism`, `ParallelismPerKPU`, and autoscaling.
- Deploy Java/Python/SQL applications and manage IAM, VPC, logging, metrics, and costs.
- Troubleshoot backpressure, checkpoint failures, lag, state growth, and snapshot compatibility errors.

## 2. What Is Managed Service for Apache Flink?

Amazon Managed Service for Apache Flink was previously named Amazon Kinesis Data Analytics for Apache Flink. The service lets you develop and run Apache Flink applications without managing compute clusters, task managers, job managers, or checkpoint storage infrastructure yourself. Applications can be written in Java, Scala, Python, or SQL depending on compatible APIs/runtimes and connectors.

Apache Flink is a distributed stream processing engine. A job is a graph of interconnected operators. Operators process records in parallel across tasks, exchange data via network shuffles, and can maintain state. The runtime coordinates tasks, checkpoints, and failure recovery.

Managed Service for Apache Flink manages application lifecycles and runtime resources. Developers remain responsible for designing business logic, schemas, keys, state, watermarks, connectors, sink semantics, capacity settings, IAM permissions, testing, and operations.

### 2.1 Components of an Application

| Component | Role |
|---|---|
| Source | Reads events from Kinesis Data Streams, Amazon MSK/Kafka, or connector-supported sources |
| Deserialization | Converts bytes/messages into typed, schema-structured records |
| Transformation | Filters, maps, flatMaps, joins, aggregates, enriches, or routes records |
| Keyed state | Stores state isolated per key, such as transaction totals per account |
| Operator state | Stores state bound to an operator/subtask, such as offsets or managed partition lists |
| Window | Groups records by time or count to compute results |
| Timer | Triggers processing at a specific event time or processing time |
| Sink | Writes results to Kinesis, Kafka/MSK, S3, Firehose, or supported systems |
| Checkpoint coordinator | Coordinates checkpoints to consistently persist state and processing positions |
| Runtime | Schedules tasks, distributes parallelism, recovers failures, and executes the job |

### 2.2 General Architecture

    Producers / Applications / IoT Devices
                    |
                    v
             Kinesis Data Streams
                    |
                    v
        Managed Service for Apache Flink
          +----------------------------+
          | Source and deserializer    |
          | Timestamp and watermark    |
          | KeyBy / Window / Join      |
          | Keyed state and timers     |
          | Checkpoint / recovery      |
          | Aggregation and enrichment |
          +----------------------------+
             |             |        |
             v             v        v
          Kinesis         MSK      S3 / Firehose
             |             |        |
             +-------------+--------+
                           |
                           v
                Lakehouse / Analytics
                Alerts / Applications

A real-world architecture also includes an IAM execution role, CloudWatch Logs, CloudWatch metrics, S3 for application packages, KMS keys, VPC/subnets/security groups, and a deployment pipeline. Sources and sinks are billed separately from Managed Service for Apache Flink.

### 2.3 When Should You Use Flink?

Flink fits when an application needs:

- Continuous computation over unbounded data streams.
- Maintaining state across events.
- Event-time window aggregations.
- Joining multiple streams or enriching with reference data.
- Handling out-of-order events and watermarks.
- Recovering from checkpoints without re-reading full history.
- Low latency with high throughput and complex processing logic.

If you only need simple record delivery from a stream to S3 without complex state or windows, consider Amazon Data Firehose or other integration services. If a workload is primarily streaming SQL queries, Table API/SQL or dedicated streaming SQL services can reduce boilerplate code. Choose the engine based on state needs, event time, latency, control, and operational capability.

## 3. Stateful and Stateless Stream Processing

### 3.1 Stateless Processing

Stateless operators process the current record without remembering results from prior records. Examples:

- Normalizing field names.
- Filtering out transactions below a threshold.
- Converting JSON to Avro/Protobuf.
- Adding a constant or reformatting timestamps.

Given the same input, the operator computes output independently. On task restart, it typically just resumes reading input from the proper position without restoring accumulated business state.

### 3.2 Stateful Processing

Stateful operators retain data across multiple records. Examples:

- Total transactions per account over 10 minutes.
- Failed login count within a sliding window.
- User session state until inactivity expires.
- Inventory levels per SKU.
- Joining a transaction stream with loaded reference data.

Suppose a stream receives transactions:

| Timestamp | Account | Amount |
|---|---|---:|
| 10:00:01 | A100 | 40 |
| 10:00:03 | B200 | 25 |
| 10:00:05 | A100 | 70 |
| 10:00:08 | A100 | 20 |
| 10:00:09 | B200 | 30 |

After grouping by account, state might look like:

| Account key | Running total |
|---|---:|
| A100 | 130 |
| B200 | 55 |

When the next record for A100 arrives, the operator updates A100's state without rescanning the entire stream. State can persist for hours, days, or longer depending on TTL and business rules.

### 3.3 Keyed State and Operator State

**Keyed state** is partitioned by key after splitting the stream via `keyBy`. Each key has isolated state. Example:

    transactions
      -> keyBy(accountId)
      -> ValueState(totalAmount)
      -> fraud rule

Keyed state fits counters, aggregates, session state, timers, and per-entity rules. During rescaling, Flink redistributes key groups across parallel subtasks.

**Operator state** is bound to an operator instance/subtask rather than a specific business key. It is useful for state redistributed across subtasks, such as partition metadata or connector-specific source state. Operator state can use union redistribution or list redistribution depending on implementation.

Never pick operator state as a substitute for keyed state when logic requires isolating state per customer/account. Using the right state type ensures accurate rescaling and recovery.

### 3.4 State Backend and State Size

Managed Service for Apache Flink uses RocksDB as the embedded key/value store for state in the runtime environment per service documentation. Active state can live on local storage; checkpoints/snapshots are durably persisted to recover if a host/task is lost.

State size affects:

- Checkpoint and restore duration.
- Running application storage usage.
- Rescaling duration.
- I/O and memory pressure.
- Ability to complete checkpoints within timeout.

Do not store entire payloads unnecessarily in state. Keep only fields needed for future decisions, set TTL when data expires, use efficient serializers, and avoid huge object graphs.

### 3.5 State TTL

State TTL lets state entries expire automatically over time. For instance, user session state can expire after 30 minutes of inactivity. TTL caps state growth, but must be configured according to semantics:

- Does TTL start on state creation or on state update?
- Does reading state refresh TTL?
- Is expired data cleaned up immediately or lazily/incrementally?
- On checkpoint restore, do TTL timestamps retain proper meaning?
- Could TTL discard data still needed for late events or auditing?

TTL does not replace stream or database retention. If replay or auditing is required, preserve raw data in a data lake or appropriate source retention.

## 4. Event Time, Processing Time, and Watermarks

### 4.1 Three Time Concepts

| Time characteristic | Meaning | Example |
|---|---|---|
| Processing time | Wall-clock time on the worker executing the operator | Record processed at 10:05:10 |
| Ingestion time | Time the record enters the Flink system | Record received by Flink at 10:05:08 |
| Event time | Time the event actually occurred at the producer | Transaction occurred at 10:04:55 |

Processing time is simple and reflects system execution time, yet results vary with processing speed, retries, and backlogs. Event time reflects business occurrence time, suiting analytics that require results aligned with when events actually happened.

Consider a phone losing connectivity for 5 minutes and then sending a batch of events. Processing time assigns all events to when the batch arrived; event time can still place them into the windows when they actually occurred.

### 4.2 What Is a Watermark?

A watermark is a signal indicating that the stream processor can assume events with timestamps earlier than a threshold have already been observed, within the configured out-of-order bound. Watermarks help Flink decide when to close windows and emit results.

Example using event time with up to 30 seconds of allowed delay:

    Watermark = max(event timestamp observed) - 30 seconds

If the newest observed event has timestamp 10:05:00, the watermark is roughly 10:04:30. A window ending at 10:04:00 can close once the watermark passes that end timestamp per window semantics.

A watermark is neither a record timestamp nor a guarantee that no late events remain. An event older than the watermark can still appear due to producer delays, retries, or uneven reading across source partitions.

### 4.3 Out-of-Order Events and Allowed Lateness

Suppose a 1-minute window ends at 10:05:00. A transaction with event time 10:04:58 arrives at 10:05:20. If the watermark has already passed 10:05:00, this event is a late event for that window.

Several strategies exist:

- Tolerate out-of-order arrival up to a bound via watermark delay.
- Configure allowed lateness to update already-emitted window results for an extra interval.
- Route late events to a side output for separate processing.
- Use downstream correction/retraction mechanisms when business logic requires adjusting prior results.
- Drop overly late events if they no longer hold value.

Pick a strategy aligned with SLAs. Real-time dashboards can accept preliminary figures plus updates; financial reconciliation may require a late-event path and period-close procedures.

### 4.4 Idle Shards/Partitions

Downstream watermarks are governed by the slowest input. If a source subtask reads multiple shards/partitions and one shard has no data, that idle shard's watermark may stall, preventing event-time windows from closing.

You can use a watermark strategy with an idleness timeout to exclude idle subtasks from watermark calculation. Conceptual example in the Java DataStream API:

    WatermarkStrategy.<Event>forBoundedOutOfOrderness(Duration.ofSeconds(30))
        .withIdleness(Duration.ofMinutes(1));

Idleness resolves partitions emitting zero records, though it does not advance event time on stale data. Understand your source connector's semantics and test late-event behavior once an idle shard resumes activity.

### 4.5 Choosing Time Semantics

| Requirement | Recommendation |
|---|---|
| Count records processed per machine minute | Processing time |
| Sum transactions per actual minute of occurrence | Event time |
| SLAs based on system ingestion time | Ingestion time or source-assigned timestamp |
| Multiple producers with clock skew | Normalize timestamps, bound out-of-orderness, monitor clock skew |
| Sources with idle shards | Watermark idleness and late-event policy |

## 5. Windows and Time-Based Computations

### 5.1 Tumbling Windows

Tumbling windows split a stream into non-overlapping intervals, such as every minute or every hour. Each event belongs to one window based on its timestamp.

Example summing amount per account each minute:

    event stream
      -> keyBy(accountId)
      -> tumbling event-time window(1 minute)
      -> sum(amount)

### 5.2 Sliding Windows

Sliding windows have a size and a slide step. For instance, a 10-minute window updated every minute. One event can belong to multiple windows. This suits rolling averages, moving counts, or detecting recent behavior.

### 5.3 Session Windows

Session windows group nearby events according to activity periods for a key. When inactivity exceeds a gap, the session closes. Used for user sessions, IoT devices, or customer interactions.

### 5.4 Count Windows and Global Windows

Count windows trigger by record count instead of time. Global windows assign all records to a single window and require custom triggers to emit results. Use them when business logic dictates batch-count triggers or custom triggers; otherwise, time-based windows are usually easier to reason about.

### 5.5 Window Lifecycle

A window has more than just a size. Specify:

- Timestamp used to assign events to windows.
- Watermark and allowed lateness.
- Trigger defining when results are emitted.
- Accumulation mode or how updates/retractions are handled.
- State cleanup after window expiration.
- Where late events go.

Overly long windows or wide allowed lateness can bloat state significantly. Very short windows reduce latency but increase emission frequency and sink overhead.

## 6. DataStream API and Stateful Operators

### 6.1 DataStream Pipeline

The DataStream API models pipelines using sources, transformations, and sinks. A typical flow:

    Source
      -> Deserialize
      -> Assign timestamps and watermarks
      -> Filter invalid records
      -> KeyBy business key
      -> Stateful process / window
      -> Enrich or route
      -> Sink

Common transformations:

| Operator | Purpose |
|---|---|
| `map` | One input produces one output |
| `flatMap` | One input produces 0..n outputs |
| `filter` | Retains records matching a predicate |
| `keyBy` | Partitions records by key to enable keyed state |
| `union` | Merges multiple streams of the same type |
| `connect/coProcess` | Connects two streams and processes both inputs |
| `window` | Groups records by time/count |
| `process` | Custom logic, state, and timers |
| `side output` | Emits secondary streams such as late events or invalid data |

### 6.2 Keyed State Example

The following example illustrates using keyed state to count transactions per account. Imports, the `Event` schema, and source/sink setup are omitted to focus on state:

    DataStream<Event> events = ...;

    DataStream<Event> keyed = events
        .keyBy(Event::accountId);

    DataStream<AccountCount> counts = keyed
        .process(new KeyedProcessFunction<String, Event, AccountCount>() {
            private transient ValueState<Long> countState;

            @Override
            public void open(Configuration parameters) {
                ValueStateDescriptor<Long> descriptor =
                    new ValueStateDescriptor<>("transaction-count", Long.class);
                countState = getRuntimeContext().getState(descriptor);
            }

            @Override
            public void processElement(
                Event event,
                Context context,
                Collector<AccountCount> out) throws Exception {
                Long current = countState.value();
                long next = (current == null ? 0L : current) + 1L;
                countState.update(next);
                out.collect(new AccountCount(event.accountId(), next));
            }
        });

`keyBy` must precede keyed state usage. Omitting `keyBy` or choosing an unstable key means state will not represent the entity accurately. Never use a null `accountId` or a shared default value for many records, as they will pile onto one hot key.

### 6.3 Timers and Stateful Rules

Timers let operators execute logic at a target event time or processing time. Examples:

- Trigger an alert if an account does not confirm a transaction within 30 seconds.
- Close a session when no new events arrive.
- Emit aggregated results when a window closes.
- Clean up temporary state after expiration.

Timers are bound to keys and are checkpointed alongside state. Registering excessive timers or failing to delete obsolete timers can cause state and checkpoints to grow rapidly.

### 6.4 Serialization and Schema Evolution

State must be serialized for checkpointing and restoration. Custom data types require stable serializers. Changing classes, fields, types, serializers, or keys can render old state incompatible.

Best practices:

- Use versioned schemas.
- Keep state types explicit and stable.
- Verify serialization in local integration tests.
- Avoid renaming operators when mapping state from savepoints.
- Set stable operator UIDs in DataStream jobs when managing state across code updates.
- Test restoring from real snapshots before deploying major changes.

## 7. Table API and SQL

Table API/SQL fits relational operations such as filtering, projection, joins, aggregations, and windowing. It reduces Java code for workloads with clear schemas/tables.

### 7.1 Streaming Tables

A table can represent an append-only stream or a changelog stream. A SQL query can continuously ingest new records and emit updated results. When joining, aggregating, or windowing, the runtime still maintains state underneath.

### 7.2 Event-Time Windows in SQL

Conceptual example:

    CREATE TABLE transactions (
      account_id STRING,
      amount DECIMAL(18, 2),
      event_time TIMESTAMP(3),
      WATERMARK FOR event_time AS event_time - INTERVAL '30' SECOND
    );

    SELECT
      window_start,
      window_end,
      account_id,
      SUM(amount) AS total_amount
    FROM TABLE(
      TUMBLE(
        TABLE transactions,
        DESCRIPTOR(event_time),
        INTERVAL '1' MINUTE
      )
    )
    GROUP BY window_start, window_end, account_id;

This illustrates a SQL event-time window; connector `WITH` options, catalogs, serialization, and sinks must be configured for your active connector/runtime version. Do not copy this schema verbatim to production if your source uses different timestamps or watermark bounds.

### 7.3 Choosing an API

| Need | Suitable API |
|---|---|
| Simple filters/maps/aggregates with clear schemas | SQL or Table API |
| Custom keyed state, timers, side outputs | DataStream API |
| Relational joins/aggregations | Table API/SQL |
| Combining custom logic and SQL | DataStream + Table API |
| Controlled windowing and event-time semantics | Both, depending on complexity |

SQL does not eliminate state design. A streaming query with `GROUP BY` or `JOIN` still requires state sizing, retention, watermarks, and checkpointing.

## 8. Checkpoints, Savepoints, and Snapshots

### 8.1 Why Checkpoints Are Needed

A checkpoint is a consistent snapshot of job state at a processing point. It lets Flink restore operator state and source read positions after a job/task failure. When checkpoints succeed, the application recovers and resumes without reprocessing full history.

With Managed Service for Apache Flink, enabling checkpointing is recommended. Default settings in the service guide enable checkpoints with a 60-second interval and a 5-second minimum pause under default configuration. Verify exact active values for your runtime and application settings.

### 8.2 Checkpoint Barriers

Flink injects checkpoint barriers into streams. Barriers flow through operators to produce a consistent snapshot across state and input positions. For operators with multiple inputs, checkpoint alignment ensures inputs are snapshotted at the same logical point.

If one input is slow, barriers wait and checkpoint duration can increase. Unaligned checkpoints can reduce alignment time in certain workloads, though they trade off state/checkpoint size and must be verified against service/runtime support.

### 8.3 How Checkpoints Differ from Savepoints

| Concept | Purpose | Lifecycle |
|---|---|---|
| Checkpoint | Automatic recovery on job failure | Created by runtime on interval; service-managed |
| Savepoint | Intentional state snapshot for updates, migrations, or admin tasks | Explicitly created and managed by operators/applications |
| Application snapshot (legacy) | Snapshot managed by Managed Service for Apache Flink bound to an application | Restorable only by the application that created it |
| Enhanced snapshot | Snapshot as an independent AWS resource with its own ARN | Restorable to enhanced-snapshot-mode applications in the same account/Region; supports S3 export/import |
| System snapshot | Snapshot created by the service during updates/stops/scaling per snapshot mode | Preserves state across administrative operations |

In AWS documentation, every snapshot is an Apache Flink savepoint. However, automatic checkpoints and snapshots/savepoints have different goals, management lifecycles, and retention; do not use the names interchangeably.

### 8.4 Legacy Snapshots vs. Enhanced Snapshots

Managed Service for Apache Flink supports two snapshot modes:

- Application snapshots (legacy): snapshots belong to the creating application and can only be restored by that application.
- Enhanced snapshots: each snapshot has an independent ARN and survives application deletion; can be restored into another application in enhanced snapshot mode within the same account and Region, or exported/imported via S3.

Enhanced snapshots require Apache Flink 1.20 or newer. New applications may still default to legacy mode; to use enhanced mode, select it during application creation or upgrade. An application uses only one mode at a time.

When deleting an application, its legacy snapshots are deleted with it, whereas enhanced snapshots persist and continue incurring storage charges until deleted individually. Factor this into cleanup workflows and budgets.

### 8.5 System Snapshots and Exactly-Once During Updates

When snapshots are enabled, Managed Service for Apache Flink can create system snapshots during operations like updates, stops, and certain configuration changes. Behavior during scaling/VPC/logging changes may vary by snapshot mode.

If snapshots are configured and the application restore configuration points to the proper snapshot, the service can preserve exactly-once semantics during updates or service-managed scaling/maintenance. Force stop skips creating a system snapshot; it can cause data loss or duplicate processing. Use force stop only with a runbook and acceptance of its consequences.

With enhanced snapshot mode, AWS recommends taking an enhanced snapshot before each code release and waiting for `READY` status prior to updating. Retain snapshots long enough for policy-defined rollbacks, then delete obsolete snapshots.

### 8.6 Snapshot Frequency

Taking snapshots multiple times a day recovers closer to the point of failure, yet increases:

- Storage costs.
- CPU/I/O usage during snapshotting.
- Checkpoint/snapshot duration.
- Risk of overlapping snapshots if state is large.

Choose frequency based on RPO, business criticality, state size, and restore duration. Do not set snapshot intervals too short if checkpoints struggle to finish or the application is under backpressure.

### 8.7 Snapshot Compatibility

A snapshot can become incompatible with new code if you change operator topology, operator UIDs, key types, serializers, state schemas, or `maxParallelism`. Before releasing:

1. Take a snapshot from the running version.
2. Deploy the new code in a test environment.
3. Restore the snapshot into the new code.
4. Verify operator state mapping and state contents.
5. Run with representative data and verify sink output.
6. Roll out to production only with a tested rollback plan.

If state is no longer compatible, plan for state migration, schema evolution, or intentionally discarding old state by business decision. Never use skip-restore options to mask compatibility bugs if that state holds critical data.

## 9. Exactly-Once and Practical Limits

### 9.1 Processing Guarantees

Three common terms:

- **At-most-once:** records may be lost, but never reprocessed.
- **At-least-once:** records are not lost under proper recovery, but may be processed multiple times.
- **Exactly-once:** every logical effect is reflected exactly once within the system's guarantee scope.

Flink checkpointing recovers state and source positions. However, end-to-end exactly-once also depends on source connectors, sink connectors, transaction protocols, and destination idempotency.

### 9.2 Source, State, and Sink Must Align

Suppose Flink reads transactions from Kinesis, updates state, and writes results to Kafka:

1. Source records its read position in the checkpoint.
2. Operator state is snapshotted alongside the checkpoint.
3. Sink coordinates commits so outputs are not duplicated on restore.
4. On failure, Flink restores source position and state from the checkpoint.
5. Sink completes or rolls back corresponding transactions.

If a sink writes records directly without transactions/idempotency, restarts can replay outputs already written prior to checkpoint completion. Therefore, never assume every sink is exactly-once by default.

### 9.3 Transactional Sinks

The Kafka connector supports exactly-once semantics in proper configurations, typically using transactions and requiring checkpointing. S3 FileSink coordinates file commits via checkpoints/committers. The Kinesis sink and other connectors have their own guarantees, limits, and setup requirements.

For API/database sinks that do not participate in checkpoint-coordinated transactions, use idempotent writes, unique event IDs, keyed upserts, or downstream deduplication.

### 9.4 Idempotency

An idempotent operation yields the same outcome when executed repeatedly. For example, updating order state via an upsert keyed on `order_id` and version prevents creating duplicate records on retries.

For payment/fraud workflows:

- Use unique `event_id` values.
- Write state with versions/sequences.
- Use conditional writes or downstream transactions.
- Separate non-rollbackable side effects from the core pipeline.
- Route malformed events to a DLQ/quarantine.

Flink's internal exactly-once does not automatically ensure emails, SMS, webhooks, or payment calls fire only once unless the receiving system enforces idempotency.

## 10. Connecting Sources and Sinks

### 10.1 Kinesis Data Streams Source

Kinesis Data Streams is a common source for Managed Service for Apache Flink. The Kinesis source connector reads records from shards into a DataStream. Configure stream name/ARN, Region, initial position, credentials/role, and a connector version compatible with your Flink runtime.

Initial positions are typically `LATEST` or `TRIM_HORIZON` depending on connector. `LATEST` reads new records per configuration; `TRIM_HORIZON` starts from the oldest retained record. Picking the wrong initial position can miss history or force re-reading a huge backlog.

Enhanced Fan-Out (EFO) gives registered consumers dedicated read throughput. Standard consumers share shard read throughput. EFO helps when multiple applications read the same stream or consistent low latency is required; it carries separate costs and consumer count limits.

### 10.2 Amazon MSK/Kafka Source

The Kafka connector reads topic/partitions and offsets. Specify:

- Bootstrap brokers and authentication.
- Topics, consumer groups, and starting offsets.
- Partition assignment and parallelism.
- TLS/SASL/IAM authentication matching the cluster.
- VPC networking, security groups, and DNS.
- Event timestamps and watermark strategy.

If source partitions sit idle or suffer skew, event-time watermarks can stall. Monitor per-partition lag and source subtasks.

### 10.3 Sinks

Common sinks:

| Sink | Use case | Key considerations |
|---|---|---|
| Kinesis Data Streams | Forward results to another stream or downstream consumer | Partition keys, shard capacity, throttling, and connector guarantees |
| Amazon MSK/Kafka | Event buses, microservices, data integration | Transactional sinks, topic partitions, authentication |
| Amazon S3 | Data lakes, archives, analytics | File rolling, checkpoint commits, partitioning, and small files |
| Amazon Data Firehose | Managed delivery to S3, Redshift, OpenSearch, or supported targets | Buffering, retries, transformations, and service cost |
| JDBC/databases | Upserts or serving tables | Connection pools, batching, transactions, and idempotency |

### 10.4 Connector Compatibility

Connector versions must match the Flink runtime version and Java dependencies. Never copy a connector JAR from another Flink version merely because package names match. Consult AWS's connector matrix for your chosen runtime, especially when upgrading from Flink 1.x to 2.x.

Note when upgrading the Kinesis connector: `FlinkKinesisConsumer` and `KinesisStreamsSource` are not state-compatible. Migrations require a separate offset/state plan; do not assume an old snapshot restores directly onto the new source connector.

### 10.5 Source Retention and Replay

Checkpoints do not replace source retention. If application downtime outlasts Kinesis/MSK retention, the source may no longer hold older data for replay. Size retention for RTO, backfills, and incident recovery. For Kinesis, retention is bounded by stream settings; for MSK, it depends on log retention and disk capacity.

## 11. Scaling, Parallelism, and KPUs

### 11.1 Parallelism

Parallelism is the number of subtasks running concurrently for an operator/job. Higher partition or key counts enable load distribution; too little parallelism creates bottlenecks, while excessive parallelism increases overhead, network shuffles, and checkpoint costs.

In Managed Service for Apache Flink:

- `Parallelism` is the application's parallel task count.
- `ParallelismPerKPU` is the number of task slots scheduled per KPU.
- Required KPUs relate to `Parallelism` divided by `ParallelismPerKPU`.

`ParallelismPerKPU` defaults to 1 and can be raised up to 8 per scaling docs. Raising it can utilize KPUs better for blocking-I/O workloads, though it will not increase throughput if the bottleneck is CPU, source partitions, or sinks.

### 11.2 Operator Parallelism

Individual operators can override parallelism. Raising application parallelism while leaving a critical operator at low parallelism still creates a bottleneck. For instance, if the source has 16 subtasks but an enrichment operator has 1 subtask, all records funnel through a single sequential point.

Check:

- Source parallelism relative to shard/partition count.
- Key distribution and hot keys.
- Operator busy/backpressure ratios.
- Sink throughput and transaction commits.
- Serialization, network shuffles, and state size.

### 11.3 maxParallelism

`maxParallelism` is the upper bound on parallelism a job can scale to while preserving state. Keyed state is organized into key groups; during rescaling, key groups are reassigned across subtasks.

If left unspecified, default `maxParallelism` can be 128 when an application starts with parallelism not exceeding 128. To scale higher later, configure an appropriate `maxParallelism` upfront.

Changing `maxParallelism` on an existing application makes prior snapshots incompatible for restore under AWS rules. This is a critical architectural decision; pick your target ceiling before production.

### 11.4 Autoscaling

Managed Service for Apache Flink autoscaling relies on CPU utilization. Per current documentation, if CPU exceeds 75% for 15 minutes with autoscaling enabled, the service can scale up parallelism/capacity. Autoscaling does not automatically react to every metric such as heap memory utilization, source lag, or backpressure.

If the bottleneck is memory, skew, I/O, or sinks, automatically adding KPUs may not resolve it. Inspect operator parallelism, key distribution, memory, checkpoint duration, and downstream capacity.

### 11.5 Kinesis Processing Units

One KPU provides 1 vCPU of compute and 4 GB of memory. The service uses KPUs to measure processing capacity. Each Apache Flink application is also billed one additional KPU for orchestration under the current pricing model.

KPUs cannot be derived directly from records/second without benchmarking. Throughput depends on:

- Record size and schema complexity.
- Number of operators and transformations.
- State size, key cardinality, and windows.
- Serialization/compression.
- Source/sink latency and I/O.
- Machine learning or cryptographic computation.
- Parallelism and data skew.

Load test with data matching production sizes and distributions. Watch CPU, heap, backpressure, checkpoints, and source lag to size capacity.

## 12. Deploying Applications

### 12.1 Java DataStream Workflow

A typical deployment flow:

1. Create Kinesis Data Streams/MSK sources and destinations.
2. Create an S3 bucket to hold application packages.
3. Develop the Java application with compatible Flink APIs and connectors.
4. Test locally with representative data.
5. Build a fat JAR containing the application and required dependencies.
6. Upload the JAR to S3.
7. Create the Managed Service for Apache Flink application and select the runtime version.
8. Assign the service execution role.
9. Configure checkpoints/snapshots, parallelism, environment properties, logging, and VPC.
10. Start the application and monitor status and CloudWatch metrics.
11. Send test records and verify sink output.

AWS getting-started tutorials use JDK 11 and Maven for Java DataStream examples; current runtime/SDK versions may support or require newer versions. Always verify your chosen runtime version against the Developer Guide and connector compatibility matrix.

### 12.2 Fat JARs and Dependencies

Applications must bundle required dependencies inside a fat JAR/uber JAR. Avoid:

- Accidentally bundling Flink runtime dependencies already provided by the service.
- Version conflicts in Jackson/Netty/connectors.
- Improperly shading service loader metadata.
- Missing connectors or serializers at runtime.
- Exceeding supported JAR size limits.

Build and run locally with the exact dependency/runtime profile before uploading.

### 12.3 Application Configuration

An application needs:

- Application name and runtime environment.
- Code package S3 location/version.
- Service execution role ARN.
- Environment properties.
- Parallelism settings.
- Checkpointing and snapshot settings.
- VPC settings if accessing private resources.
- CloudWatch logging options.

When creating via the console, some dependent resources like IAM roles and CloudWatch log streams may be provisioned automatically. When using CLI/API, operators must create and grant permissions on associated resources explicitly.

### 12.4 Deploying Java Code

Illustrative build and upload commands:

    mvn clean package
    aws s3 cp target/stream-job.jar s3://my-flink-artifacts/releases/stream-job-1.0.0.jar

After uploading, create the application via console, CloudFormation, or AWS CLI/API. Use object versioning or immutable artifact names so you know the exact binary running.

Never place access keys in source code or environment properties. Use IAM execution roles and least-privilege policies.

## 13. Security and Networking

### 13.1 Service Execution Role

Managed Service for Apache Flink assumes the service execution role to access AWS resources. The role requires:

- A trust policy for the corresponding service principal per AWS documentation.
- Read permissions on source streams/topics.
- Write permissions on sinks.
- Read permissions on the S3 application package.
- Write permissions to CloudWatch Logs.
- KMS permissions if streams, buckets, or secrets use customer managed keys.
- Network/VPC integration permissions as configured.

Separate roles by application and environment. Never grant administrator access just to silence `AccessDenied` quickly.

### 13.2 VPC Access

If sources/sinks reside in private subnets, configure VPC, subnets, and security groups on the application. Verify routes, DNS, NAT or VPC endpoints, security group ingress/egress, and NACLs.

Managed Service for Apache Flink runs in AWS-managed infrastructure; attaching a VPC configuration does not automatically grant access to every private resource. Verify real network reachability and IAM permissions separately.

### 13.3 Encryption and Secrets

Use TLS for Kafka/MSK, databases, and supported endpoints. Use KMS for encryption at rest per resource policies. Store external credentials in AWS Secrets Manager or supported providers; never put passwords in JARs, source code, or logs.

If you change a KMS key policy, verify the application role and service principal retain required decrypt/encrypt permissions. A disabled key or altered policy can prevent the application from reading sources/sinks or restoring state.

### 13.4 Data Privacy

Stateful streams may hold PII, payment metadata, or user behavior in state and snapshots. Ensure you:

- Minimize sensitive data stored in state.
- Set appropriate TTLs and retention.
- Restrict access to snapshots and logs.
- Encrypt data and lock down buckets.
- Never log full payloads in debug logs.
- Establish compliant data deletion processes if state retains identifiable information.

## 14. Monitoring and Operations

### 14.1 Key Metrics

Monitor application and Flink CloudWatch metrics:

| Metric | Meaning | Signs to investigate |
|---|---|---|
| CPU utilization | Compute utilization | Sustained high usage near saturation |
| `heapMemoryUtilization` | JVM heap usage | Continuously rising toward limits |
| `backPressuredTimeMsPerSecond` | Time tasks spend backpressured | Rising at operators or downstream |
| `busyTimeMsPerSecond` | Time tasks spend busy | High while output remains low |
| `idleTimeMsPerSecond` | Time tasks spend idle | Possible input starvation or upstream bottleneck |
| `lastCheckpointDuration` | Duration of latest checkpoint | Steadily rising toward timeout |
| `lastCheckpointSize` | Size of latest checkpoint | Abnormal growth from state bloat |
| `numRecordsIn/Out` | Record throughput | Rising input paired with dropping output |
| `currentInputWatermark` | Current watermark | Stalled due to idle partitions or event-time bugs |
| `downtime` | Application outage duration | Spiking on restarts or failures |

Metric names and dimensions depend on runtime/monitoring level. Choose an appropriate monitoring level; overly granular Debug or Parallelism levels can add log/metric overhead and trigger backpressure.

### 14.2 Backpressure

Backpressure happens when downstream operators cannot consume upstream output fast enough. Sources may slow down as buffers fill.

Common causes:

- Slow sink writes or sink throttling.
- CPU-intensive operators.
- Key skew overloading one subtask.
- Heavy serialization/deserialization.
- Slow network shuffles or external I/O.
- Excessive logging, especially per-record logging.

Investigation steps:

1. Identify operators/subtasks showing high backpressure.
2. Compare busy, idle, input, and output rates.
3. Inspect sink latency and throttling.
4. Inspect key distributions and hot keys.
5. Inspect CPU, heap, GC, and checkpoint durations.
6. Optimize logic or sinks before blindly increasing parallelism.

### 14.3 Checkpoint Failures

Checkpoints can fail due to:

- Oversized state or checkpoint duration exceeding timeout.
- Backpressure delaying barriers.
- Sink/source permissions or network errors.
- Incompatible serializers/schemas.
- Snapshot quotas or storage failures.
- Under-provisioned operators.

Inspect `lastCheckpointDuration`, `lastCheckpointSize`, checkpoint alignment/start delays, and logs. When checkpoints fail, recovery falls back to the last successful checkpoint, increasing replay volume and data lag.

### 14.4 Logging

Application logs should focus on lifecycle events, warnings, errors, state migrations, connector exceptions, and key business events. Never emit a log line per record at high throughput. Excessive logging can bottleneck execution, inflate CloudWatch ingestion bills, and induce backpressure.

If logs fail to appear, verify the execution role has `PutLogEvents`, `DescribeLogGroups`, and `DescribeLogStreams`; verify the application is running and the CloudWatch log stream is properly configured.

### 14.5 Alarms and Runbooks

Set CloudWatch alarms for:

- Application downtime or status other than `RUNNING`.
- Sustained high CPU utilization.
- High backpressure.
- Checkpoint duration nearing timeout or checkpoint failures.
- Rising source lag.
- Stalled watermarks.
- Sink errors/throttling.
- Rapidly growing state/checkpoint size.

Every alarm needs an owner, severity, dashboard, and runbook. Never rely on CPU alone to judge health; an application with low CPU and rising source lag may be stalled on a connector or sink.

## 15. Troubleshooting Common Scenarios

| Symptom | Possible cause | Resolution |
|---|---|---|
| Application fails to start | Broken JAR, dependency conflict, missing IAM permissions, incompatible runtime | Read application errors, check artifact and execution role |
| Cannot read Kinesis | Wrong stream ARN/Region, IAM deny, bad initial position or connector config | Check source config, role, and stream status |
| Cannot connect to MSK | Security group, subnet, DNS, TLS/SASL, or bootstrap brokers | Check VPC routing and authentication |
| Watermark not advancing | Idle shard, bad event timestamps, slow source subtask | Enable idleness, inspect timestamps and source lag |
| Windows fail to emit results | Watermark hasn't passed end time, late events, or wrong trigger | Inspect watermarks and allowed lateness |
| State growing continuously | High key cardinality, missing TTL, overly long windows, uncleaned timers | Bound state, add TTLs and timer cleanup |
| Checkpoints failing | Backpressure, large state, timeouts, sink/source issues | Check checkpoint metrics and operator bottlenecks |
| Low CPU but high lag | Sink I/O, hot keys, source partitions, or memory bottlenecks | Check backpressure, heap, parallelism, and partitions |
| Application update stuck | Snapshot failure, state incompatibility, bad code/package | Inspect status, snapshots, and rollback options |
| Snapshot restore fails | Incompatible Flink version, operator UID, serializer, or `maxParallelism` | Test restores pre-release, plan state migrations |
| Duplicate outputs | Non-transactional/non-idempotent sink or force stop | Use transactions, event IDs, and deduplication |
| Missing outputs | Wrong checkpoint/snapshot, expired source retention, failed sink commit | Check source position, restore point, and sink transactions |

If an application stays in a transient state like `STARTING`, `UPDATING`, `STOPPING`, or `AUTOSCALING` too long, read the troubleshooting guide before force stopping. Force stopping can lose or duplicate data. With snapshots enabled, rolling back to a prior version can restore from the latest successful snapshot.

## 16. Managed Service for Apache Flink Cost

### 16.1 KPU-Hours

Compute costs depend on KPU count and application uptime. One KPU provides 1 vCPU and 4 GB RAM. The service bills one extra KPU per application for orchestration on Apache Flink applications.

Managed Service for Apache Flink bills per second in supported Regions, with a 10-minute minimum charge per application start. Thus, a 2-minute job run can still incur the 10-minute minimum for that start. Check the pricing page per Region before budgeting.

### 16.2 Running Application Storage

The service bills for running application storage used by stateful processing. AWS pricing guidance specifies per-KPU storage allocation and a GB-month rate; running applications have a minimum storage charge per the FAQ. When estimating, do not ignore storage simply because state is small or streams are idle.

### 16.3 Durable Backup Storage

Optional durable application backups/snapshots are billed per GB-month. Enhanced snapshots persist after application deletion, so maintain a retention/cleanup policy. Snapshot import/export follows separate pricing rules per current pricing docs.

### 16.4 Dependent Service Costs

Managed Service for Apache Flink pricing excludes sources and sinks:

- Kinesis Data Streams shard/on-demand throughput and data retrieval.
- MSK brokers, storage, networking, and data transfer.
- S3 storage, requests, and lifecycle transitions.
- Data Firehose ingestion/delivery.
- CloudWatch Logs and metrics.
- VPC NAT Gateways, endpoints, and data transfer.
- KMS, Secrets Manager, and downstream services.

### 16.5 Cost Optimization

- Size parallelism/KPUs from benchmarks rather than over-provisioning.
- Use autoscaling when workloads fluctuate and logic suits it.
- Do not leave Studio notebooks running in interactive mode when idle.
- Stop batch applications once finished, keeping the 10-minute minimum per start in mind.
- Minimize state size and align TTLs with business rules.
- Retain snapshots per RPO/rollback policies and delete obsolete enhanced snapshots.
- Avoid debug logging in production.
- Optimize source/sink batching and network paths.
- Track costs by application, Region, and workload.

## 17. Reference Design: Transaction Fraud Detection

### 17.1 Requirements

A payment platform ingests transactions from multiple channels. Each record has `transaction_id`, `account_id`, `amount`, `merchant_id`, `event_time`, and `device_id`. The system must alert when an account executes too many transactions or exceeds an amount threshold within a 5-minute window.

### 17.2 Pipeline

    Payment producers
          |
    Kinesis Data Streams
          |
    Managed Service for Apache Flink
          |
    Parse + validate schema
          |
    Assign event time + watermark
          |
    keyBy(account_id)
          |
    5-minute event-time window
          |
    Count + sum + velocity rules
          |
      +---+----------------+
      |                    |
      v                    v
    Fraud alerts        Aggregated metrics
      |                    |
    EventBridge/SNS      S3 / MSK

### 17.3 State Design

Per-`account_id` state can track:

- Transaction count in the window.
- Total amount.
- Distinct merchant count.
- Distinct device count.
- Timestamp of the latest transaction.

Do not store full raw transactions if only aggregates are needed. For auditing, archive raw events separately to S3/Kinesis.

### 17.4 Fault Tolerance

Checkpoints save keyed state and source progress. Pre-deployment snapshots enable code rollbacks. Alert sinks should use transactions or idempotency keys based on `transaction_id`/`rule_id` to prevent duplicate alerts after restarts.

### 17.5 Scaling and Hot Keys

High-volume accounts can become hot keys. Raising overall application parallelism cannot split a single key if logic serializes state for that key. Use two-stage aggregation, salting, or partitioning strategies if business logic permits, then merge results.

### 17.6 Late Events

A 30-second watermark delay and 2-minute allowed lateness serve as an initial baseline. Benchmark and measure false positives/false negatives. Overly late transactions can route to a side output for reconciliation rather than being silently dropped.

## 18. Lab: Stateful Stream Processing with Kinesis

### Objective

Build a Flink application that reads transactions from Kinesis, counts per account, writes results to a target stream, and observes checkpointing and recovery.

### Prerequisites

- Lab AWS account and Region.
- Input/output Kinesis Data Streams.
- S3 bucket for JAR artifacts.
- Java JDK and Maven compatible with the chosen runtime.
- IAM execution role with permissions for source, sink, S3 artifact, and CloudWatch Logs.
- AWS CLI or console access.

### Step 1: Create Streams

Create two streams, such as `input-transactions` and `output-account-count`. Choose capacity appropriate for your lab and Region. Never use real payment data.

### Step 2: Write the Application

1. Create a Maven project with compatible Flink runtime and Kinesis connector dependencies.
2. Define an `Event` schema with `account_id`, `transaction_id`, and `event_time`.
3. Add a Kinesis source.
4. Parse records and filter invalid inputs.
5. Assign timestamps and watermarks.
6. Call `keyBy(account_id)`.
7. Use `ValueState` or a window aggregate to count events.
8. Write results to a Kinesis sink.
9. Enable checkpointing and log lifecycle/error events.

### Step 3: Test Locally

1. Run the application in an IDE or local runner.
2. Send multiple records with repeated `account_id` values.
3. Verify counters increment per account.
4. Send out-of-order records and observe watermark/window behavior.
5. Verify sink output.

### Step 4: Deploy

1. Build the fat JAR.
2. Upload the JAR to S3.
3. Create the Managed Service for Apache Flink application.
4. Select the runtime and service execution role.
5. Configure source/sink properties.
6. Enable checkpointing and snapshots as required.
7. Start the application and inspect CloudWatch metrics.

### Step 5: Test Recovery

In the lab environment:

1. Send data and record outputs.
2. Wait for a successful checkpoint.
3. Perform a graceful restart/stop with a snapshot.
4. Restart and verify state/counters.
5. Compare outputs to detect any lost or duplicate records.
6. Create a snapshot before testing code changes.

Do not force stop stateful applications unless data loss or duplicate risks are accepted.

### Step 6: Operational Checks

- Observe CPU, heap, input/output records, and backpressure.
- Check `lastCheckpointDuration` and `lastCheckpointSize`.
- Check source lag and sink throughput.
- Try scaling parallelism in the lab.
- Verify the application still restores from snapshots after changes.

### Step 7: Lab Cleanup

Stop/delete the application per procedure. Delete unneeded enhanced snapshots. Delete streams, S3 artifacts, and log groups per lab policy. Verify Kinesis, S3, and CloudWatch have no unexpected billable resources remaining.

## 19. Self-Check Questions

**Question 1.** How does stateful stream processing differ from stateless processing?

**Answer:** Stateful operators retain state across multiple records, such as per-account counters; stateless operators process each record independently.

**Question 2.** When should you use keyed state?

**Answer:** When isolated state is needed per business key such as `account_id`, `customer_id`, or `device_id` after `keyBy`.

**Question 3.** How does operator state differ from keyed state?

**Answer:** Operator state is bound to an operator/subtask; keyed state is partitioned by key and automatically redistributed across key groups during rescaling.

**Question 4.** What is a watermark used for?

**Answer:** Signaling event-time progress so windows/operators know when time-based data can be evaluated or closed.

**Question 5.** Why can an idle shard prevent windows from closing?

**Answer:** Downstream watermarks can be held back by an input subtask that emits no new watermarks; idleness excludes idle subtasks from the calculation.

**Question 6.** How does a checkpoint differ from a savepoint?

**Answer:** Checkpoints serve automatic fault recovery; savepoints/snapshots are intentionally created for updates, migrations, or administration.

**Question 7.** How do enhanced snapshots differ from legacy snapshots?

**Answer:** Enhanced snapshots have independent ARNs and outlive the application; legacy snapshots are tied to the creating application.

**Question 8.** What minimum Flink runtime is required for enhanced snapshots?

**Answer:** Apache Flink 1.20 or newer per current AWS documentation.

**Question 9.** Does checkpointing alone guarantee end-to-end exactly-once?

**Answer:** No. Sources, sinks, transactions, and idempotency must work together to prevent lost or duplicate outputs.

**Question 10.** Why is force stop risky?

**Answer:** Force stop skips creating a system snapshot; restarting can lose or duplicate data.

**Question 11.** What does `maxParallelism` affect?

**Answer:** The maximum parallelism achievable while preserving state; changing `maxParallelism` can break restore compatibility with prior snapshots.

**Question 12.** Which metric drives Managed Service for Apache Flink autoscaling?

**Answer:** CPU utilization; per current documentation, CPU above 75% for 15 minutes can trigger scaling when autoscaling is enabled.

**Question 13.** Why doesn't adding KPUs always fix backpressure?

**Answer:** Bottlenecks may lie in sinks, hot keys, memory, networking, or per-operator parallelism; autoscaling does not respond to every metric.

**Question 14.** What resources make up one KPU?

**Answer:** 1 vCPU of compute and 4 GB of memory.

**Question 15.** Why must connector versions match the Flink runtime?

**Answer:** APIs, serializers, and runtime dependencies can differ; incompatible connectors can break builds or startup.

**Question 16.** How do event-time windows handle late events?

**Answer:** Via watermarks, allowed lateness, side outputs, or application-configured correction policies.

**Question 17.** Why should you avoid logging every record in production?

**Answer:** Log volume can bottleneck execution, inflate CloudWatch costs, and induce backpressure.

**Question 18.** When an application lags despite low CPU, what should you inspect?

**Answer:** Source partitions, sink throughput, backpressure, memory, hot keys, and network/I/O.

**Question 19.** Are enhanced snapshots deleted automatically when an application is deleted?

**Answer:** No. Enhanced snapshots persist independently and must be deleted separately when no longer needed.

**Question 20.** Which costs beyond KPUs should be included in estimates?

**Answer:** Orchestration KPUs, running application storage, durable backup storage, sources/sinks, Kinesis/MSK, S3, CloudWatch, VPC, and data transfer.

## 20. Production Readiness Checklist

- [ ] DataStream API or Table API/SQL chosen to match business logic.
- [ ] Source/sink connectors verified compatible with the runtime.
- [ ] Event schemas versioned with malformed-data handling.
- [ ] Keys distribute evenly without unmanaged hot keys.
- [ ] State size, TTL, and timer lifecycles designed.
- [ ] Event time, watermarks, idleness, and late-event policies defined.
- [ ] Checkpointing enabled with suitable intervals/timeouts.
- [ ] Snapshot mode, retention, and rollback procedures approved.
- [ ] Enhanced snapshot compatibility tested if used.
- [ ] End-to-end exactly-once verified with real sources/sinks.
- [ ] Idempotency keys or deduplication applied to external side effects.
- [ ] `Parallelism`, `maxParallelism`, and `ParallelismPerKPU` chosen ahead of production.
- [ ] Autoscaling tested against CPU and non-CPU bottlenecks.
- [ ] IAM execution role follows least privilege.
- [ ] VPC, security groups, routes, DNS, and KMS policies verified.
- [ ] CloudWatch logs/metrics/alarms have owners and runbooks.
- [ ] Remediation runbooks exist for backpressure, checkpoint failures, source lag, and sink throttling.
- [ ] RPO/RTO and source retention cover replay/recovery needs.
- [ ] Costs budgeted for KPUs, orchestration, running storage, snapshots, and sources/sinks.
- [ ] Obsolete enhanced snapshots purged per retention policy.

## 21. Official References

1. [Amazon Managed Service for Apache Flink Documentation](https://docs.aws.amazon.com/managed-flink/) — service overview, APIs, and Developer Guide.
2. [Get started with the DataStream API](https://docs.aws.amazon.com/managed-flink/latest/java/getting-started.html) — Java applications, Maven, and development environment.
3. [Get started with Table API and SQL](https://docs.aws.amazon.com/managed-flink/latest/java/gs-table.html) — SQL/Table API.
4. [Add streaming data sources](https://docs.aws.amazon.com/managed-flink/latest/java/how-sources.html) — Kinesis and MSK sources.
5. [Write data using sinks](https://docs.aws.amazon.com/managed-flink/latest/java/how-sinks.html) — Kinesis, Kafka/MSK, S3, and Firehose sinks.
6. [Implement fault tolerance](https://docs.aws.amazon.com/managed-flink/latest/java/how-fault.html) — checkpoints and fault recovery.
7. [Manage application backups using snapshots](https://docs.aws.amazon.com/managed-flink/latest/java/how-snapshots.html) — legacy/enhanced snapshots and system snapshots.
8. [How enhanced snapshots work](https://docs.aws.amazon.com/managed-flink/latest/java/snapshots-how-it-works.html) — snapshot modes and lifecycles.
9. [Implement application scaling](https://docs.aws.amazon.com/managed-flink/latest/java/how-scaling.html) — parallelism, `maxParallelism`, and autoscaling.
10. [Review application resources](https://docs.aws.amazon.com/managed-flink/latest/java/how-resources.html) — KPUs and task slots.
11. [Track events using the DataStream API](https://docs.aws.amazon.com/managed-flink/latest/java/how-time.html) — processing/ingestion/event time.
12. [Maintain best practices](https://docs.aws.amazon.com/managed-flink/latest/java/best-practices.html) — checkpoints, watermarks, and performance.
13. [Troubleshoot performance issues](https://docs.aws.amazon.com/managed-flink/latest/java/performance-troubleshooting.html) — CPU, parallelism, logging, and backpressure.
14. [Troubleshoot checkpoint issues](https://docs.aws.amazon.com/managed-flink/latest/java/troubleshooting-checkpoints.html) — checkpoint stages and failures.
15. [Set up application logging](https://docs.aws.amazon.com/managed-flink/latest/java/cloudwatch-logs.html) — CloudWatch Logs and IAM permissions.
16. [Managed Service for Apache Flink pricing](https://aws.amazon.com/managed-service-apache-flink/pricing/) — KPUs, running storage, and durable backups.
17. [Managed Service for Apache Flink FAQs](https://aws.amazon.com/managed-service-apache-flink/faqs/) — minimum usage, KPUs, and billing.
18. [Use Flink connectors](https://docs.aws.amazon.com/managed-flink/latest/java/how-flink-connectors.html) — connector/runtime compatibility.

---

**Conclusion:** Stateful stream processing requires proper coordination across keys, state, event time, watermarks, checkpoints, and sink semantics. Managed Service for Apache Flink removes runtime infrastructure overhead, yet reliability still depends on state design, snapshot compatibility, parallelism, connectors, IAM, and operational practices. Test recovery and exactly-once behavior with realistic workloads before taking critical streaming applications to production.

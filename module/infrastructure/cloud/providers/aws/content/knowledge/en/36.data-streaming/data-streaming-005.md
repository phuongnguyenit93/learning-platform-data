# Enhanced Fan-Out, Ordering, and Late-Arriving Data

A Kinesis data stream can serve multiple consumers concurrently: transaction processors, fraud detection, operations dashboards, data lakes, and analytics models. These consumers may need the same records while having different throughput and latency requirements. If all consumers use shared reading, they contend for each shard's read quota. At the same time, when a stream has multiple shards, record ordering is only guaranteed within a defined scope; a consumer may observe events in an order different from when they actually occurred in the business domain.

Amazon Kinesis Data Streams provides **Enhanced Fan-Out (EFO)** to allocate dedicated read throughput to each consumer per shard. The service also uses partition keys and sequence numbers to organize record ordering. At the processing layer, frameworks such as Managed Service for Apache Flink use event time, watermarks, and allowed lateness to handle late or out-of-order events.

Three distinct problems must be separated:

- **Fan-out:** multiple consumers reading the same stream without contending for read throughput.
- **Ordering:** the order in which related records are routed to shards and processed.
- **Late data:** events arriving at the system after their business timestamp has passed, or after the window's watermark has advanced past them.

EFO does not sort records by event timestamp. Partition keys do not create global ordering across multiple shards. Watermarks do not make late data disappear; they help the system decide when to emit window results and how long to retain state.

## Learning Objectives

After this lesson, learners will be able to:

- Explain Enhanced Fan-Out and distinguish it from shared-throughput consumers.
- Register an EFO consumer, read with SubscribeToShard, and understand subscription lifecycles.
- Select partition keys to maintain ordering for events of the same entity while distributing load evenly.
- Distinguish between in-shard ordering, per-partition-key ordering, and event-time order.
- Explain the impact of retries, PutRecords, resharding, KCL checkpoints, and KPL aggregation on ordering.
- Distinguish between processing time, ingestion/arrival time, and event time.
- Use watermarks, bounded out-of-orderness, idleness, and allowed lateness to handle late-arriving events.
- Design side outputs or reconciliation flows for events exceeding the accepted lateness window.
- Monitor consumer lag, watermark progress, shard throughput, and retention to avoid data loss.

## 1. Context: One Stream, Multiple Consumers

Kinesis Data Streams stores records in shards. Producers write records into the stream; consumers read records to process, enrich, or forward results to other services.

An architecture can have multiple independent consumers:

~~~mermaid
flowchart LR
    P["Producers"] --> K["Kinesis Data Stream"]
    K --> C1["Consumer A: fraud"]
    K --> C2["Consumer B: analytics"]
    K --> C3["Consumer C: data lake"]
    K --> C4["Consumer D: notifications"]
    C1 --> O1["Risk decisions"]
    C2 --> O2["Metrics / aggregates"]
    C3 --> O3["Amazon S3"]
    C4 --> O4["Notification service"]
~~~

Consumers may need the same data without necessarily sharing the same processing speed. A fraud consumer needs low latency; an analytics consumer may need high throughput; a data lake consumer may run in batches. If one consumer is slow, it should not degrade the read capability of other consumers.

Kinesis has two common stream-reading models:

- **Shared throughput:** consumers call GetRecords and share the shard's read limit.
- **Enhanced Fan-Out:** each registered consumer receives a dedicated pushed data stream via SubscribeToShard.

For independent per-record processing, Kinesis also offers queue consumers for On-demand streams. Queues track record acknowledgement state and suit stateless processing; stream consumers are better suited when logic must maintain state and process records in shard order.

## 2. What Is Enhanced Fan-Out?

Enhanced Fan-Out is a feature that lets a registered consumer receive dedicated read throughput of up to roughly 2 MB of data per second per shard. This throughput is not shared with other EFO consumers or shared-throughput consumers.

EFO uses a push model:

1. Register the consumer with the stream.
2. Kinesis issues an ARN for the consumer.
3. The consumer calls SubscribeToShard for the target shard.
4. Kinesis pushes SubscribeToShardEvent messages over an HTTP/2 connection.
5. The consumer processes records, saves checkpoints, and renews the subscription to continue reading.

An EFO consumer can read all shards in a stream using KCL or subscribe to individual shards via the API. EFO only changes data delivery and read throughput; stream ordering semantics still depend on partition keys, shards, and how consumers process data.

### 2.1. Shared Throughput vs. EFO

| Criterion | Shared-throughput consumer | Enhanced Fan-Out consumer |
|---|---|---|
| Read API | GetRecords | SubscribeToShard |
| Model | Consumer pulls data over HTTP | Kinesis pushes data over HTTP/2 |
| Read throughput | Up to ~2 MB/s total per shard shared among all consumers reading that shard | Each consumer gets dedicated throughput up to ~2 MB/s per shard |
| Record propagation latency | AWS docs cite ~200 ms average reference for one consumer; can rise when shared by multiple consumers | ~70 ms average reference in AWS examples, largely independent of consumer count |
| Quota contention | Yes, when multiple consumers read the same shard | Eliminates read contention across EFO consumers |
| Cost | No separate consumer-shard hour fee for shared reads | May incur consumer-shard hour and data retrieval fees depending on capacity mode |
| Best for | One or few consumers, moderate read load | Multiple independent consumers, high throughput, or low-latency needs |

Latency figures are AWS reference measurements under test conditions, not an SLA or latency guarantee for all workloads.

### 2.2. Consumer Registration Limits

Under current quotas:

| Capacity mode | Maximum registered consumers per stream |
|---|---:|
| Provisioned | 20 |
| On-demand Standard | 20 |
| On-demand Advantage | 50 |

The 50-consumer limit on On-demand Advantage applies only in AWS Regions supporting that quota; check the current Region list before designing. The registered consumer limit is shared between enhanced fan-out consumers and queue registrations. When designing many consumers, count total consumers/queues registered on the stream, not just active EFO consumers.

A registered consumer that is no longer used still consumes quota until deregistered. Establish a consumer lifecycle process and clean up test consumers once finished.

### 2.3. When Should You Use EFO?

EFO is a good fit when:

- Multiple applications need to read the entire stream independently.
- Consumers have high throughput and frequently hit throttling from sharing read capacity.
- You need lower record propagation latency to consumers.
- Consumers run at different speeds and a slow consumer must not affect others.
- You need to isolate fraud, observability, analytics, and archival pipelines.

Shared throughput can fit when there are only one or a few consumers, low read rates, and cost is a primary priority. EFO adds cost in many capacity modes, so measure actual throughput, consumer count, and latency before enabling it.

## 3. Registering and Using EFO

### 3.1. Registering a Consumer with the AWS CLI

Example registering a consumer named fraud-detector:

~~~bash
aws kinesis register-stream-consumer \
  --stream-arn arn:aws:kinesis:ap-southeast-1:111122223333:stream/orders \
  --consumer-name fraud-detector \
  --region ap-southeast-1
~~~

Kinesis returns a ConsumerARN. The consumer must be in the ACTIVE state before calling SubscribeToShard. You can use the following commands to inspect and manage it:

~~~bash
aws kinesis describe-stream-consumer \
  --consumer-arn <CONSUMER_ARN> \
  --region ap-southeast-1

aws kinesis list-stream-consumers \
  --stream-arn <STREAM_ARN> \
  --region ap-southeast-1

aws kinesis deregister-stream-consumer \
  --consumer-arn <CONSUMER_ARN> \
  --region ap-southeast-1
~~~

The Consumer ARN is tied to the registration instance. If you deregister and recreate a consumer with the same name, the new ARN will differ. IAM policies referencing the consumer ARN must be updated accordingly.

### 3.2. SubscribeToShard and HTTP/2

SubscribeToShard establishes an HTTP/2 connection between a consumer ARN and a specific shard. Kinesis sends SubscribeToShardEvent frames containing records, a continuation sequence number, and childShards metadata once a shard closes.

A subscription stays open for up to about 5 minutes. The consumer must call SubscribeToShard again to keep receiving data. The API rate-limits subscribe calls per consumer and shard; do not create a tight retry loop that triggers ResourceInUseException.

When a shard closes due to a split/merge, the continuation sequence number may no longer be valid for further reading; the event can return childShards so the consumer discovers child shards. Handle this as a shard transition step rather than retrying the subscription infinitely on the old shard.

Java example using AWS SDK for Java 2.x illustrating subscribing to one shard:

~~~java
KinesisAsyncClient client = KinesisAsyncClient.create();

SubscribeToShardRequest request = SubscribeToShardRequest.builder()
    .consumerARN(consumerArn)
    .shardId(shardId)
    .startingPosition(p -> p.type(ShardIteratorType.LATEST))
    .build();

SubscribeToShardResponseHandler handler =
    SubscribeToShardResponseHandler.builder()
        .subscriber(new SubscribeToShardResponseHandler.Visitor() {
            @Override
            public void visit(SubscribeToShardEvent event) {
                for (Record record : event.records()) {
                    processRecord(record);
                }

                // Persist progress only after the records are safely processed.
                saveCheckpoint(event.continuationSequenceNumber());
            }
        })
        .onError(error -> log.error("EFO subscription failed", error))
        .build();

client.subscribeToShard(request, handler).join();
~~~

This is a processing skeleton; a production application must implement retries/backoff, client lifecycle management, error handling, durable checkpointing, and subscription renewal. When opening the next subscription, pass the saved continuation sequence number with a starting position matching the application's checkpoint semantics. Never save a checkpoint before processing results are durably persisted.

### 3.3. IAM Permissions

Consumers need permissions for both the stream and registered consumers. Common actions include:

- kinesis:DescribeStreamSummary
- kinesis:ListShards
- kinesis:DescribeStreamConsumer
- kinesis:SubscribeToShard
- kinesis:RegisterStreamConsumer if the consumer registers itself
- kinesis:DeregisterStreamConsumer if the application manages consumer lifecycle itself

If the stream is encrypted with a customer managed KMS key, producers and consumers also need key usage permissions per policy. Use IAM roles and least privilege; never embed long-lived access keys in applications.

## 4. Choosing a Consumer Model: Stream Consumer or Queue Consumer?

Given current Kinesis Data Streams capabilities, select the consumer model based on workload semantics:

| Requirement | Suitable model |
|---|---|
| Stateful computation requiring in-shard ordered record processing | Stream consumer, shared or EFO |
| Multiple independent consumers needing dedicated throughput | EFO stream consumer |
| Independent per-record processing, worker scaling, and per-record acknowledgement | Queue consumer |
| Windowing, aggregation, sessions, or anomaly detection | Stream consumer paired with Flink/KCL |
| Stateless tasks such as enrichment, API calls, or isolated order handling | Queue consumer may fit |

Queue consumers track acknowledgements and can redeliver unacknowledged records. Delivery is at-least-once; applications must be idempotent. Queue ordering is best effort. If business logic requires sequential processing per partition key, read the stream directly using a stream consumer.

Do not move an ordering-sensitive pipeline to a queue solely to add more workers without verifying the impact on ordering and state.

## 5. Ordering in Kinesis Data Streams

Ordering is a consumer's ability to observe records in the exact sequence required by business logic. In Kinesis, ordering is organized per shard and partition key, not globally across the entire stream.

Each data record has:

- A partition key supplied by the producer in user-managed partition-key mode.
- A shard ID chosen by Kinesis from the partition key's hash range.
- A sequence number assigned by Kinesis when the record is written.
- A payload containing application data; Kinesis does not interpret its contents.

### 5.1. Partition Keys Determine the Shard

Kinesis computes an MD5 hash of the partition key to map the record to a shard's hash key range. Records with the same partition key are routed to the same shard in user-managed partition-key mode.

Example for an order system:

- Partition key = orderId: events for the same order go to the same shard.
- Partition key = customerId: events for the same customer go to the same shard.
- Partition key = region: can yield too few keys and cause hot shards.
- Partition key = constant: all records funnel into one shard, capping throughput.

Choose the partition key around the entity requiring order preservation, while analyzing cardinality and load distribution. An overly hot partition key can drive its shard to throughput limits even while other shards sit idle.

### 5.2. Ordering Guarantee Scope

| Scope | Ordering |
|---|---|
| Records within the same shard | Consumers read the shard in sequence order |
| Same partition key in user-managed mode | Mapped to the same shard; suitable for preserving order of related records |
| Two different partition keys in the same shard | Have shard sequence order, but no natural business relationship between the keys |
| Two different shards | No global ordering across records |
| Event time inside payload | Not automatically sorted by business timestamp by Kinesis |

Sequence numbers are not a global offset comparable across shards. Do not use sequence numbers from two different shards to conclude which business event happened first.

### 5.3. Service-Managed Record Distribution

Kinesis currently supports two record distribution strategies:

- **User-managed partition keys:** producers provide a partition key; Kinesis hashes it to pick a shard. Used for workloads needing ordering across related records.
- **Service-managed record distribution:** Kinesis distributes records evenly across shards automatically; suits stateless workloads without ordering requirements.

Service-managed distribution provides no ordering guarantees. Partition keys may be ignored during shard assignment; consumers may also receive records without a partition key. Do not mix the two strategies in the same stream. If you have both ordering-sensitive and ordering-agnostic workloads, consider separate streams.

## 6. Preserving Order from the Producer Side

### 6.1. PutRecord and SequenceNumberForOrdering

PutRecord sends one record at a time. When strictly increasing sequence numbers are needed for the same partition key, the producer can send sequentially and pass the previous record's sequence number in SequenceNumberForOrdering on the next request.

~~~java
String previousSequenceNumber = null;

for (OrderEvent event : eventsForSameOrder) {
    PutRecordRequest.Builder builder = PutRecordRequest.builder()
        .streamName("orders")
        .partitionKey(event.orderId())
        .data(SdkBytes.fromUtf8String(event.toJson()));

    if (previousSequenceNumber != null) {
        builder.sequenceNumberForOrdering(previousSequenceNumber);
    }

    PutRecordResponse response = kinesisClient.putRecord(builder.build());
    previousSequenceNumber = response.sequenceNumber();
}
~~~

This is a sequential pattern for a single partition key. In concurrent applications, serialize writes for the same key or use a dedicated sequencing mechanism. Never share one global sequence number variable across multiple keys.

SequenceNumberForOrdering does not establish ordering across different partition keys.

### 6.2. PutRecords and Partial Failures

PutRecords sends multiple records in one request to boost throughput. The API returns per-record results; some records may succeed while others encounter throttling or transient errors.

Producers must:

1. Check FailedRecordCount.
2. Identify exact entries with an ErrorCode.
3. Retry only failed records with exponential backoff and jitter.
4. Track business ordering of retried records.
5. Include an application-level idempotency key to handle uncertainty over whether a timed-out request was persisted.

PutRecords does not have a SequenceNumberForOrdering parameter. If strict per-key ordering is mandatory, design the producer to serialize writes per key and prevent later records from overtaking earlier ones on retry. Do not assume retrying failed records in a batch preserves business order if subsequent records already succeeded.

### 6.3. Hot Partition Keys and Throughput

Each shard has a capacity limit. If too many records with the same partition key hit one shard, that shard can become hot while other shards remain lightly loaded.

Ways to mitigate hot shards:

- Pick a high-cardinality key that still reflects the required business ordering.
- Avoid using a single constant key for the entire stream.
- Monitor IncomingBytes, IncomingRecords, and throttling per shard.
- Separate data types with different ordering requirements into distinct streams.
- Use shard splits/resharding or an appropriate capacity mode as total load grows.

Do not arbitrarily append random suffixes to a partition key if doing so breaks required ordering. If you must split a hot entity across multiple partitions, the application needs sequence numbers or a downstream reorder buffer to restore order.

## 7. Ordering During Resharding

Resharding changes shard counts via splits or merges. After a split/merge, the old shard becomes a parent shard in the CLOSED state; records already written to the parent remain readable during retention. New records route to child shards by hash range.

This introduces a risk: if a consumer reads a child shard before draining all remaining records from the parent shard, the order for the same partition key can invert in processing results.

### 7.1. How KCL Handles Parent and Child Shards

The Kinesis Client Library (KCL) manages per-shard leases, distributes shards to workers, checkpoints progress, and adapts to splits/merges. KCL ensures child shards are processed only after parent shards have finished and been checkpointed.

KCL provides at-least-once processing. After a crash/restart, some records may be reprocessed from the latest checkpoint. Sinks or business logic must be idempotent.

### 7.2. What Custom Consumers Must Do

If building a custom consumer directly on the API:

1. Track shard states and parent/child relationships.
2. Read all remaining records from parent shards.
3. Confirm the iterator/continuation indicates the parent has no more data.
4. Only then begin reading child shards in proper sequence.
5. Persist checkpoints and shard lineage.
6. Test splits/merges in a test environment.

Never assume shard IDs or shard counts stay fixed over a stream's lifetime.

## 8. KPL Aggregation and Checkpointing

The Kinesis Producer Library (KPL) can pack multiple user records into one Kinesis data record to reduce overhead and improve ingest efficiency. Consumers must de-aggregate to recover the original user records.

When aggregation is enabled:

- Multiple user records can share the sequence number of the underlying Kinesis record.
- KPL user records also carry a subsequence number.
- Checkpointing only by sequence number may be insufficient to pinpoint the last processed subrecord.
- KCL supports de-aggregation and per-record/subsequence checkpointing.

With KCL, prefer checkpointing with the record object when distinguishing KPL user records is necessary. If persisting checkpoints yourself, store both sequence number and subsequence number. If you only checkpoint a batch's sequence number and the consumer crashes mid-batch, user records may be replayed or skipped depending on checkpoint placement.

Service-managed record distribution does not support KPL aggregation; verify compatibility before changing distribution strategies.

## 9. Why Do Events Arrive Late?

A record can arrive at Kinesis in ingest order and still be a late event in business time. For example:

- An IoT device goes offline for 10 minutes and then flushes buffered data.
- A mobile app sends events after reconnecting.
- A producer retries a request after a timeout.
- One shard is processed more slowly by consumers than other shards.
- Backfills or replays inject historical data into the stream.
- Device clocks drift or timestamps are generated across unsynchronized systems.

Distinguish three notions of time:

| Time type | Meaning | Example |
|---|---|---|
| Event time | When the event actually occurred in the business domain. | order_created_at or sensor_timestamp. |
| Ingestion/arrival time | When Kinesis received the record. | ApproximateArrivalTimestamp. |
| Processing time | When the consumer processes the record. | When Flink/KCL runs business logic. |

Example:

- Event occurs at 10:00:00.
- Device loses connectivity and sends at 10:07:00.
- Kinesis receives the record at 10:07:01.
- Consumer processes it at 10:07:02.

By event time, the record belongs to the 10:00 window. By ingestion time and processing time, it appears around 10:07. If a dashboard relies on processing time, the 10:00 metrics may never be updated even though the older record just arrived.

Kinesis does not sort records by payload event timestamps. Applications must decide which timestamp serves as the source of truth.

## 10. Event Time and Watermarks in Apache Flink

Apache Flink supports three common time concepts:

- **Processing time:** wall-clock time on the processing machine when the operator receives the record.
- **Event time:** timestamp attached to when the business event occurred.
- **Ingestion time:** when the record enters the pipeline or ingestion source, depending on configuration.

Event-time windows need to know when data for a time interval can be considered reasonably complete. Flink uses watermarks to represent event-time progress.

### 10.1. What Is a Watermark?

A watermark T signifies that the system assumes no more events with timestamps less than or equal to T will arrive in the normal stream, under the chosen watermark strategy. A watermark is an operational heuristic, not an absolute guarantee that older events cannot appear.

With 30-second bounded out-of-orderness, a simple watermark is roughly calculated as:

\[
Watermark = MaxEventTimeObserved - 30s
\]

If an event with a timestamp earlier than the current watermark arrives later, it is treated as a late event for the corresponding window.

### 10.2. Watermark Strategies

Common strategies:

| Strategy | When to use |
|---|---|
| Monotonous timestamps | Event time increases monotonically per source/subtask. |
| Bounded out-of-orderness | Tolerates events arriving out of order up to a measured bound, e.g., 30 seconds or 2 minutes. |
| Custom watermark generator | When data follows custom rules or needs per-source adjustments. |
| Idleness detection | When an idle shard/partition has no events and stalls the shared watermark. |

With Kinesis, Managed Service for Apache Flink can use approximate arrival time as the default timestamp from the source connector. If the payload holds a reliable eventTime, extract the business timestamp and apply a TimestampAssigner.

DataStream API example:

~~~java
WatermarkStrategy<OrderEvent> watermarkStrategy =
    WatermarkStrategy
        .<OrderEvent>forBoundedOutOfOrderness(Duration.ofSeconds(30))
        .withTimestampAssigner(
            (event, previousTimestamp) -> event.eventTimeMillis())
        .withIdleness(Duration.ofMinutes(1));

DataStream<OrderEvent> timestamped =
    source.assignTimestampsAndWatermarks(watermarkStrategy);
~~~

The 30-second bound is illustrative. Measure actual event delay distributions to choose the bound. If set too small, many valid events are treated as late; if set too large, window output is delayed and state must be held longer.

## 11. Allowed Lateness and Side Outputs

Watermarks determine when a window can emit its main result. However, events may still arrive after the watermark has passed the end of the window.

Flink provides allowed lateness to retain window state for an extra duration. For instance, a 10:00–10:05 window with 5 minutes of allowed lateness can keep accepting events for that window until the watermark passes window end plus 5 minutes.

Example:

~~~java
OutputTag<OrderEvent> lateOutputTag =
    new OutputTag<OrderEvent>("late-orders") {};

SingleOutputStreamOperator<OrderSummary> summaries =
    timestamped
        .keyBy(OrderEvent::customerId)
        .window(TumblingEventTimeWindows.of(Time.minutes(5)))
        .allowedLateness(Time.minutes(5))
        .sideOutputLateData(lateOutputTag)
        .aggregate(new OrderAggregate());

DataStream<OrderEvent> tooLate =
    summaries.getSideOutput(lateOutputTag);
~~~

This example demonstrates configuring the DataStream API; add the aggregate function, output types, and imports suited to your application.

### 11.1. Late Firing and Updated Results

If an event arrives after the watermark but within allowed lateness:

- Flink can merge the event into the window state.
- The window can emit a result again.
- The subsequent emission is an updated version of the earlier result.

Therefore, downstream systems must not assume each window emits only once. Use window keys, versions, or upsert semantics to overwrite older results cleanly.

### 11.2. Events Exceeding Allowed Lateness

When an event arrives after allowed lateness expires:

- Window state may already have been purged.
- The event is no longer included in the main window output.
- If sideOutputLateData is configured, excluded events can be routed to a side output.
- The side output can be written to S3, a DLQ, or a repair stream for investigation and backfill.

Do not silently drop late events if they affect financial figures, inventory, or compliance. Maintain a late-record counter metric, threshold alerts, and a reconciliation process.

## 12. Shard Idleness and Stalled Watermarks

Flink computes the watermark across parallel inputs as the minimum watermark. If one source subtask reads a shard with no events, that subtask's watermark may stop advancing. Other shards still receive data, yet downstream windows may fail to close because the shared watermark is held back.

You can use withIdleness so Flink excludes idle inputs from watermark calculation after a timeout.

However, understand two limitations:

- withIdleness does not synthesize new watermarks when a shard is idle; it merely drops the idle subtask's stale watermark from the global watermark calculation.
- If the entire stream has no events, built-in watermarks may stop advancing and the final window will not close.

In tests over a finite set of events, explicitly emit a final watermark or use an appropriate test harness. In production, inspect watermark progress, shard assignment, and source idleness; do not inflate allowed lateness to mask a stalled watermark bug.

Managed Service for Apache Flink also notes that when reading multiple shards in parallel, one shard may be processed faster than another. If subtasks emit divergent watermarks, events may be flagged as late or operators may buffer data. Check the watermark strategy, shard assigner, and watermark alignment support in your source connector.

## 13. How Do Late Events Differ from Consumer Lag?

These two issues are frequently confused:

| Phenomenon | Cause | Signs |
|---|---|---|
| Event-time late event | Producer sends an old event after business occurrence; payload timestamp is behind watermark | Low event time despite recent arrival/processing time |
| Consumer lag | Consumer processes slower than stream write rate | Rising iterator age or MillisBehindLatest |
| Watermark stall | An input/shard is idle or a subtask stops emitting watermarks | Windows fail to close even while other shards have data |
| Out-of-order arrival | Producer concurrency, retries, shard interleaving, or replay | Sequence order differs from event-time order |

If consumer lag rises, first address throughput, throttling, backpressure, and dependencies. If older event times arrive late while consumers are caught up, handle them via watermarks/allowed lateness and reconciliation.

## 14. Retention and Replay for Data Recovery

Kinesis Data Streams retains records temporarily per the retention period:

- Default: 24 hours.
- Extendable up to 365 days.
- Extended/long-term retention may incur additional fees.
- When reducing retention, records older than the new threshold can become inaccessible almost immediately.

Retention is a window for consumers to recover from failures. It is not a long-term backup. If a consumer is stopped longer than retention, older records expire and cannot be replayed from the stream.

Common starting positions:

| Starting position | Purpose |
|---|---|
| LATEST | Read only new records arriving after the consumer starts. |
| TRIM_HORIZON | Read from the oldest record still within retention. |
| AT_TIMESTAMP | Start reading from a specified timestamp. |
| AT_SEQUENCE_NUMBER / AFTER_SEQUENCE_NUMBER | Resume from a checkpointed sequence number. |

For late-event repair, you can replay a time range from Kinesis if records remain within retention, or fetch raw events from S3/a data lake if the organization archives them long-term.

Do not reduce retention while consumers are lagging without assessing data loss risk. Monitor iterator age and temporarily raise retention if extra recovery time is needed, while still fixing the root cause of slow consumption.

## 15. Monitoring EFO, Ordering, and Late Data

An operational dashboard should combine metrics from Kinesis, KCL, and Managed Service for Apache Flink.

| Metric / signal | Meaning | Action on abnormal increase |
|---|---|---|
| SubscribeToShardEvent.MillisBehindLatest | How far behind stream head an EFO consumer is | Check throughput, record processing, downstream dependencies, and backpressure |
| SubscribeToShard.Success | Whether EFO subscriptions are established successfully | Check consumer ARN, IAM, and renewal cycle |
| SubscribeToShard.RateExceeded | Subscribe called over quota or overlapping subscription | Tune retry/renew loop and concurrency |
| GetRecords.IteratorAgeMilliseconds | Age of the last record read by consumer | Alert before records expire from retention |
| ReadProvisionedThroughputExceeded | Shared consumer experiencing read throttling | Reduce shared consumers, optimize polling, or consider EFO |
| WriteProvisionedThroughputExceeded | Producer experiencing write throttling | Inspect hot shards, partition keys, and capacity |
| IncomingBytes / IncomingRecords | Ingest rate into the stream | Compare against capacity and baseline |
| OutgoingBytes / OutgoingRecords | Outbound read volume | Identify shards/consumers with unusual load |
| KCL lease/checkpoint metrics | Workers, shard ownership, and checkpoints | Check worker failures, lease contention, and checkpoint delays |
| Flink currentInputWatermark | Current watermark at operators | Detect idle shards, skew, or misconfigured watermark strategies |
| Custom late-event counter / side-output count | Events dropped or routed to late handling | Adjust lateness, timestamp source, or repair process |
| Flink backPressure / busyTime | Operator bottleneck | Tune CPU, parallelism, serialization, and sink throughput |

### 15.1. Retention Alerts

Use GetRecords.IteratorAgeMilliseconds for shared consumers and SubscribeToShardEvent.MillisBehindLatest for EFO. Set alerts well ahead of the retention period. If iterator age exceeds roughly 50% of retention, the risk of record expiration rises and requires immediate attention.

Do not rely solely on Average. One hot shard or one specific consumer can lag while the stream-wide average remains low. Use maximum or per-shard/consumer metrics during investigation.

Enhanced shard-level monitoring may incur additional CloudWatch costs. Enable only the metrics needed for troubleshooting and capacity planning.

## 16. Design Example: Order Events and Fraud Analytics

An e-commerce system emits events:

- OrderCreated
- PaymentAuthorized
- InventoryReserved
- OrderShipped
- OrderCancelled

Each event contains orderId, customerId, eventType, eventTime, producerId, and eventVersion.

### 16.1. Partition Key

Choose orderId as the partition key so events for the same order route to the same shard. Consumers can inspect eventVersion or business sequence numbers to detect duplicate or out-of-order events.

Do not use customerId if a single large customer generates excessive events causing a hot key. If business logic requires ordering per customer instead of per order, explicitly evaluate throughput levels and trade-offs.

### 16.2. EFO Consumers

Register independent consumers:

- Fraud detector: needs fast reads to evaluate transactions.
- Real-time analytics: computes revenue and funnels.
- Data lake writer: archives raw events for replay.
- Customer notification: sends email/SMS once order state qualifies.

EFO gives each consumer dedicated read throughput. Each consumer still handles errors and checkpoints independently.

### 16.3. Event-Time Analytics

Suppose the application counts orders in 5-minute windows based on eventTime. Producers may submit events 2 minutes late due to device or network delays.

A 30-second watermark bound would be insufficient if real-world data commonly arrives 2 minutes late. The team should measure latency distributions and pick an appropriate bounded out-of-orderness, such as 3 minutes, paired with 5 minutes of allowed lateness.

Events arriving within allowed lateness update window results. Events exceeding the deadline route to a late-event stream and run reconciliation to fix aggregates if needed.

### 16.4. Correctness

- Use an idempotency key on eventId.
- Use orderId + eventVersion to detect duplicate or stale events.
- Do not emit duplicate notifications when a Flink window late-fires.
- Use an upsert sink or store window versions.
- Store raw events in S3 for backfills.
- Monitor late-event rate and consumer lag separately.

## 17. Cost and Architecture Trade-offs

EFO cost depends on capacity mode and Regional pricing. With Provisioned and On-demand Standard, EFO may incur consumer-shard hour and data retrieval charges. Consumer-shard hours depend on shard count multiplied by registered EFO consumers and active registration duration.

On-demand Advantage has a different pricing model; current pricing documentation states there is no separate EFO surcharge beyond data read charges under that model. In exchange, the mode applies a minimum commitment of 25 MB/s ingest and 25 MB/s retrieval aggregated across On-demand streams in the Region; if usage is lower, shortfall charges may apply per pricing. Calculate total ingest, retrieval, retention, and other streams before enabling.

Factors to include in your cost model:

- Average and peak shard counts.
- Number of registered EFO consumers.
- GB of data read by each consumer.
- Consumer-shard hours.
- Retention beyond 24 hours.
- Enhanced CloudWatch metrics.
- KCL workers and DynamoDB lease/checkpoint tables.
- Managed Service for Apache Flink compute, snapshots, storage, and log ingestion.

EFO does not reduce the volume of data each consumer must process. If 5 consumers read the whole stream, total data retrieval can approach 5 times ingest volume (depending on record/filtering behavior). Enable EFO only for consumers with clear throughput/latency needs.

## 18. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| EFO consumer receives ResourceNotFound or ResourceInUse | Consumer not ACTIVE yet, wrong ARN, or subscription already open | Describe consumer, check status, and renew on the proper cycle |
| SubscribeToShard hits RateExceeded | Calling API too frequently or overlapping subscriptions | Limit to one active subscription per consumer/shard and back off |
| EFO consumer lag increases | Slow record processing, downstream bottleneck, or hot shard | Check MillisBehindLatest, processing time, and sink |
| Shared consumer throttled | Multiple consumers sharing read throughput | Reduce shared consumers or move performance-sensitive consumers to EFO |
| Records for same entity out of order | Partition key does not reflect entity or parallel producer retries | Use a stable key, serialize writes per key, and control retries |
| Hot shard | Low partition key cardinality or one overly hot key | Change key strategy, split workloads, or reshard |
| Ordering breaks after reshard | Custom consumer reads child before draining parent | Handle parent-child lineage or use KCL |
| Duplicate records after restart | KCL at-least-once / checkpoint after sink commit not exact | Idempotent sink and checkpoint after durable write |
| KPL records duplicated or skipped on restart | Checkpoint stored only sequence number, omitting subsequence | Use KCL checkpoint(record) or store sequence + subsequence |
| Flink window fails to close | Watermark held back by idle shard or no new events | Inspect currentInputWatermark, withIdleness, and bounded test completion |
| Late records dropped | Watermark bound or allowed lateness too short | Measure event-time lag, increase bound/lateness, or use side output |
| Window output appears multiple times | Late firing updates window | Use upsert/versioning and deduplicate output |
| Replay cannot find records | Records aged out of retention | Fetch raw data from S3/archive or long-term storage |

## 19. Lab Exercise: EFO and Late Events

Goal: design an order-events stream with two independent consumers, preserve ordering by orderId, and handle late-arriving events using event-time windows.

### Step 1: Design the Data

Create an event schema containing:

- eventId: unique identifier.
- orderId: partition key.
- eventVersion: business sequence number of the order.
- eventTime: timestamp when the event occurred.
- eventType: event type.
- payload: business data.

### Step 2: Create the Stream and Register Consumers

Create a Kinesis Data Stream in the target Region. Register fraud and analytics consumers via RegisterStreamConsumer. Wait for both consumers to reach ACTIVE.

### Step 3: Write Records

Producers write events with partition key orderId. For streams requiring strict order, serialize PutRecord calls for the same orderId and pass SequenceNumberForOrdering. For PutRecords, inspect each record result and design retries so business order is not inverted.

### Step 4: Subscribe and Process

Use SubscribeToShard or KCL. Verify each consumer reads data independently. Persist checkpoints only after outputs are durably written; ensure idempotent processing.

### Step 5: Test Late Events

Send an event with eventTime 10:00 and arrival time 10:02. Send another with eventTime 10:01 and arrival time 10:04. Verify the 5-minute window, watermark bound, and allowed lateness.

### Step 6: Test Events Exceeding Lateness

Send an event belonging to the 10:00 window after the watermark passes window end + allowed lateness. Verify the event routes to the side output and writes to S3/the repair stream.

### Step 7: Test Failures

- Stop a consumer and restart it from its checkpoint.
- Inject duplicate eventId values.
- Increase load on a single partition key to observe a hot shard.
- Split a shard in a test environment and verify parent/child ordering.
- Slow down a sink to observe consumer lag.
- Leave one shard idle to check watermark progress.

### Step 8: Evaluate Results

Compare latency, consumer lag, late-event rate, dropped late records, duplicate rate, EFO cost, and aggregate correctness. Document the partition key strategy, watermark bound, and allowed lateness in an ADR.

## 20. Misconceptions to Avoid

1. **EFO sorts records by event time.** EFO only changes the delivery model and throughput; event-time logic is handled by the application.
2. **EFO creates global ordering.** Ordering is not guaranteed across shards.
3. **One stream means all consumers share throughput.** EFO allocates dedicated throughput per registered consumer.
4. **Adding consumers always requires EFO.** Shared throughput still works well with few consumers and low load.
5. **Fewer partition keys are better.** Low cardinality can cause hot shards.
6. **Sequence numbers are a global offset.** Sequence numbers are scoped to a shard and partition key and cannot be compared across the stream.
7. **PutRecords always preserves order after retries.** Partial failures and retries must be handled per record and business logic.
8. **Resharding does not affect ordering.** Custom consumers must handle parent-child shard lineage.
9. **KCL guarantees exactly-once.** KCL provides at-least-once; sinks require idempotency.
10. **Kinesis arrival timestamp is event time.** Event time must be extracted from the payload to reflect business occurrence time.
11. **A watermark guarantees no older events remain.** A watermark is a progress heuristic; late events can still arrive.
12. **Allowed lateness keeps events forever.** Window state is retained only until the lateness deadline.
13. **Late firing emits only one result.** Windows can emit updated results multiple times.
14. **withIdleness synthesizes watermarks when the stream has no data.** It only excludes idle inputs from the watermark calculation.
15. **Increasing retention solves all consumer lag.** Retention only extends replay time; bottlenecks must still be fixed.
16. **Queue consumers preserve ordering like stream consumers.** Queues suit stateless processing; ordering is best effort.

## 21. Self-Check Questions

**1. What problem does Enhanced Fan-Out solve?**

It provides dedicated read throughput for each EFO consumer per shard and uses HTTP/2 push to reduce read contention.

**2. How much throughput does EFO provide per shard?**

Up to roughly 2 MB/s per consumer per shard.

**3. How does shared throughput differ from EFO?**

Shared consumers split the shard's total read capacity; EFO consumers receive dedicated throughput.

**4. What is a partition key used for?**

Routing records to shards via hashing and grouping related records onto the same shard.

**5. Does Kinesis guarantee ordering across two shards?**

No. There is no global ordering across shards.

**6. What is the scope of SequenceNumberForOrdering?**

It enforces strictly increasing sequence numbers for the same partition key when producers write sequentially with PutRecord; it does not order across different partition keys.

**7. Why must PutRecords inspect every record?**

A batch can have both succeeded and failed records; producers must retry only failed records while preserving business semantics.

**8. How does KCL handle resharding?**

KCL tracks leases and shard lineage, drains parent shards before child shards, and checkpoints progress.

**9. Why can KCL reprocess records?**

KCL provides at-least-once delivery; crashes occurring after sink commit but before checkpointing can cause records to replay.

**10. How does event time differ from arrival time?**

Event time is when the business event occurred; arrival time is when Kinesis received the record.

**11. What does a watermark mean?**

A watermark indicates the event-time progress beyond which the system assumes older data will no longer arrive in normal flow.

**12. What does 30-second bounded out-of-orderness do?**

It generates a watermark lagging roughly 30 seconds behind the maximum observed event time to tolerate a bounded amount of disorder.

**13. What is the purpose of allowed lateness?**

It keeps window state alive for an extra interval after the watermark passes the window end to accept late-arriving events.

**14. Why does late firing require upserts or deduplication?**

A window can emit updated results again after receiving late events.

**15. What problem does withIdleness solve?**

It removes watermarks of idle shards/subtasks from the global watermark calculation so those inputs do not block downstream windows.

**16. Why is consumer lag different from late events?**

Consumer lag is processing delay behind the stream head; a late event is an event carrying an older business timestamp arriving late relative to event time or the watermark.

**17. What is the default retention of Kinesis Data Streams?**

24 hours; extendable up to 365 days depending on configuration and cost.

**18. When should you use a queue consumer?**

When each record can be processed independently and you want per-record acknowledgement and worker scaling without managing shard leases or ordering semantics.

## 22. Production Checklist

- [ ] Every consumer has clear throughput, latency, and business objectives.
- [ ] EFO is enabled only for consumers needing dedicated throughput or low latency.
- [ ] Total registered consumers and queue registrations stay within quota.
- [ ] Consumers are ACTIVE before calling SubscribeToShard.
- [ ] Subscriptions renew on schedule, with retries/backoff and child shard handling.
- [ ] IAM roles grant only the required stream/consumer permissions.
- [ ] Partition keys accurately reflect entities requiring ordering.
- [ ] Partition keys have appropriate cardinality and load distribution.
- [ ] Producers serialize writes per key when strict ordering is required.
- [ ] PutRecords handles partial failures per record.
- [ ] KCL checkpoints after durable sink writes; sinks are idempotent.
- [ ] Custom consumers handle parent/child lineage after resharding.
- [ ] KPL aggregation has proper de-aggregation and subsequence checkpointing.
- [ ] Event schemas include eventId, eventTime, and eventVersion.
- [ ] Watermark bounds are based on measured event-time delay distributions.
- [ ] Allowed lateness fits freshness SLAs and state budgets.
- [ ] Late events exceeding the deadline have a side output, alerts, and repair process.
- [ ] Watermark idleness is configured and monitored.
- [ ] IteratorAge/MillisBehindLatest alerts fire well before approaching retention.
- [ ] Retention is long enough for recovery/replay with long-term archival if needed.
- [ ] Tests cover duplicates, out-of-order events, late events, resharding, and sink outages.
- [ ] Dashboards cover streams, shards, consumers, and Flink operators.
- [ ] Costs are modeled for EFO, retrieval, retention, CloudWatch, and Flink state/snapshots.
- [ ] Runbooks specify rollback, replay, reconciliation, and owners.

## References

- [Enhanced Fan-Out consumers](https://docs.aws.amazon.com/streams/latest/dev/enhanced-consumers.html)
- [Develop enhanced fan-out consumers with the AWS SDK for Java](https://docs.aws.amazon.com/streams/latest/dev/building-enhanced-consumers-api.html)
- [RegisterStreamConsumer API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_RegisterStreamConsumer.html)
- [SubscribeToShard API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_SubscribeToShard.html)
- [SubscribeToShardEvent API](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_SubscribeToShardEvent.html)
- [Kinesis Data Streams terminology and concepts](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Develop producers using the AWS SDK for Java](https://docs.aws.amazon.com/streams/latest/dev/developing-producers-with-sdk.html)
- [Service-managed record distribution](https://docs.aws.amazon.com/streams/latest/dev/service-managed-record-distribution.html)
- [Important considerations for service-managed distribution](https://docs.aws.amazon.com/streams/latest/dev/service-managed-pk-considerations.html)
- [Use Kinesis Client Library](https://docs.aws.amazon.com/streams/latest/dev/kcl.html)
- [Resharding, scaling and parallel processing with KCL](https://docs.aws.amazon.com/streams/latest/dev/kinesis-record-processor-scaling.html)
- [Develop producers using Kinesis Producer Library](https://docs.aws.amazon.com/streams/latest/dev/developing-producers-with-kpl.html)
- [KPL consumer de-aggregation and checkpointing](https://docs.aws.amazon.com/streams/latest/dev/kinesis-kpl-consumer-deaggregation.html)
- [Change the Kinesis Data Streams retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Kinesis Data Streams quotas and limits](https://docs.aws.amazon.com/streams/latest/dev/service-sizes-and-limits.html)
- [Monitor Kinesis Data Streams with CloudWatch](https://docs.aws.amazon.com/streams/latest/dev/monitoring-with-cloudwatch.html)
- [Troubleshoot Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/troubleshooting-consumers.html)
- [Managed Service for Apache Flink best practices: watermarks and idle shards](https://docs.aws.amazon.com/managed-flink/latest/java/best-practices.html)
- [Apache Flink: Generating Watermarks](https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/event-time/generating_watermarks/)
- [Apache Flink: Windows and allowed lateness](https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/windows/)
- [Amazon Kinesis Data Streams pricing](https://aws.amazon.com/kinesis/data-streams/pricing/)

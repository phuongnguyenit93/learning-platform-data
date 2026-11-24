# Group Lag and Its Operational Significance

Consumer group lag is the distance between a consumer group's recorded reading progress and the latest data position available in the partitions the group is reading. Lag tells operations teams whether consumers are keeping up with producer speed, which partitions hold the backlog, and whether processing capacity is sufficient to handle the load.

Rising lag does not automatically mean data is lost. It usually indicates that records are waiting to be read or processed. Conversely, zero lag at a moment in time does not prove the entire messaging pipeline is healthy: consumers might be stopped, the group might have no assignment, or the topic might not be receiving data. Therefore, lag must be interpreted alongside consumer group state, data production rate, processing duration, listener errors, and record age.

This lesson belongs to the **Consumer group** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-producing and event-consuming applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while also learning serialization, retries, dead-lettering, transactions, exactly-once semantics, concurrency, and testing to operate reliable messaging pipelines.

## 1. What Is Consumer Group Lag?

Kafka stores records in topic partitions. A consumer group reads those partitions and persists committed progress separately for each topic-partition. Lag represents the distance between the latest data position and the position the group has committed.

For example, a partition has a log end position of 1,000 and the group has committed offset 900. The offset distance is 100. This indicates the group is 100 offsets behind the end of the log by standard calculation.

~~~text
Topic: order-events, Partition: 0

Offset:      900                         999
               |--------------------------|
Committed:    900
Log end:                                 1000 (next offset)
Lag:                                      100
~~~

In the example, committed offset 900 is the next position the group will read when recovering from its committed offset. Log end offset 1,000 is the next position at which the broker can append a record. The difference between the two values is 100.

Lag is usually tracked per partition, then aggregated by consumer group, topic, or across the whole system. A group reading multiple topics will have separate lag per topic-partition.

## 2. Which Offsets Are Used to Calculate Lag?

To understand lag, you need to distinguish three concepts: log end offset, consumer position, and committed offset.

### 2.1. Log End Offset

The log end offset (LEO) is the next offset the broker will assign when appending a record to a partition. If the last record has offset 99, the log end offset is normally 100.

LEO describes the end of the log on the queried replica. In practice, monitoring tools may use the high watermark or another readable milestone depending on the lag type and API. Therefore, when comparing numbers across multiple tools, verify the exact end reference each metric uses.

### 2.2. Consumer Position

The consumer position is the next position the Kafka consumer will read in the current active session. When a consumer polls and receives records, its position advances even if the application has not committed the offset yet.

Position is part of the consumer's runtime state. If the process stops before committing, the in-memory position is lost and the consumer may restart from the old committed offset.

### 2.3. Committed Offset

The committed offset is the next position a consumer group has persisted in Kafka so it can resume reading after a consumer restart or when partitions are handed to another consumer.

Committed offset is the durable milestone of group progress. It does not prove business operations outside Kafka completed if the application committed at the wrong time or side effects were not synchronized.

### 2.4. Basic Lag Formula

For a topic-partition, the common calculation is:

\[
\text{Committed Lag} = \text{Log End Offset} - \text{Committed Offset}
\]

Example:

| Value | Offset |
| --- | ---: |
| Log end offset | 1,500 |
| Committed offset | 1,420 |
| Committed lag | 80 |

If the group has read and committed through offset 1,499, the committed offset becomes 1,500 and lag under this formula is 0.

Some tools display lag based on consumer position instead of committed offset. In that case, lag can appear lower than committed lag if the consumer has polled data without committing yet. Read the metric definition rather than assuming every metric named lag uses the same reference point.

### 2.5. Lag Does Not Always Equal the Exact Count of Readable Events

An offset is a position in the log, not a contiguous counter of payloads the application is guaranteed to receive. Offsets can have gaps due to log compaction, transaction control records, or records hidden under the active isolation level.

Therefore, offset difference is often called record lag, but it should be understood as a positional distance in the log. It may be close to the number of waiting records in a normal log, yet it does not always match the exact number of events the application will receive.

## 3. Lag Is Calculated Separately per Partition

A consumer group stores offsets separately for each partition. Consequently, a single offset cannot describe the entire group.

For example, the `billing-service` group reads the `payment-events` topic with three partitions:

| Partition | Log end offset | Committed offset | Lag |
| --- | ---: | ---: | ---: |
| 0 | 12,000 | 11,990 | 10 |
| 1 | 8,500 | 8,100 | 400 |
| 2 | 9,200 | 9,190 | 10 |
| **Total** |  |  | **420** |

Total lag is 420 offsets. However, partition 1 accounts for most of the backlog. Looking only at the total could cause operations to miss uneven load distribution.

Important perspectives:

- **Per-partition lag:** identifies which partition is accumulating a backlog.
- **Total group lag:** estimates the group's total offset distance across partitions.
- **Max lag:** detects the slowest partition.
- **Lag rate of change:** reveals whether the backlog is growing, shrinking, or steady.
- **Per-topic lag:** identifies which topic is affecting the group.

If one partition has high lag while other partitions are near zero, investigate key skew, hot data, consumer assignment, or an unusually slow processing task on that partition.

## 4. Illustrating Lag Growing and Shrinking Over Time

Lag changes over time. Producers continuously append records; consumers continuously read and commit. When the incoming data rate exceeds the processing rate, the backlog grows. When consumers process faster than the incoming data rate, the backlog shrinks.

~~~mermaid
flowchart TD
    A[Producer appends record] --> B[Partition log grows]
    B --> C{Consumer keeping up?}
    C -->|No| D[Lag increases]
    C -->|Yes| E[Consumer position advances]
    E --> F[Commit offset]
    F --> G[Lag decreases or stays stable]
    D --> H[Investigate throughput, errors, rebalances]
~~~

Suppose:

- Producers generate 800 records per second.
- The consumer group processes and commits at an equivalent of 650 records per second.
- The backlog grows by roughly 150 records per second under simplified conditions.

If this continues for 10 minutes, lag can grow by roughly 90,000 records. Exact numbers depend on partitions, batching, retries, transactions, and how metrics count offsets.

When consumers scale capacity to 1,000 records per second while producers still generate 800 records per second, the backlog can shrink by roughly 200 records per second net. If lag is currently 90,000, the theoretical time to drain the backlog is approximately 450 seconds, assuming steady rates and no additional disruptions.

Simple estimation formula:

\[
\text{Drain Time} \approx
\frac{\text{Current Backlog}}
{\text{Consumer Throughput} - \text{Producer Throughput}}
\]

This formula is only meaningful when consumer throughput exceeds producer throughput and both rates are measured over the same scope of data. If consumers are not faster than producers, the backlog cannot drain on its own.

## 5. Distinguishing Record Lag and Time Lag

Record lag shows offset distance. Time lag attempts to express how old the waiting data is. These two metrics answer different questions.

| Metric | Question Answered | Limitation |
| --- | --- | --- |
| Record/offset lag | How many offsets is the group behind the end of the log? | Does not directly reflect wait time or event criticality. |
| Time lag | How old are the unprocessed events? | Calculation depends on metrics, timestamps, and tooling. |
| Processing latency | How long does it take the listener to process one record or batch? | Does not show how large the accumulated backlog is. |
| End-to-end latency | How long does it take from event emission until business completion? | Requires correlation/timestamps across services. |

A topic receiving thousands of events per second can have a lag of 10,000 that represents only a few seconds of data. A topic with few events per minute can have a lag of 20 where the oldest event has been waiting for hours.

Time lag has no single universal formula across all tools. Some systems use the timestamp of the latest processed record or the oldest unprocessed record; others measure the difference between the current time and the event timestamp. Review the metric definition, clock skew, and timestamp semantics before configuring alerts.

For business workflows with time-based SLAs, time lag or end-to-end latency is often more directly meaningful than a fixed record-lag threshold.

## 6. What Does High Lag Mean Operationally?

High lag indicates that the consumer group is falling behind the currently available data position. Specific impact depends on the data type and service SLA.

Examples:

- **Payments:** transaction statuses or reconciliation may update slowly.
- **Orders:** projections and customer notifications may be delayed.
- **Inventory:** stock counts may not reflect the latest events.
- **Telemetry:** dashboards and alerts may rely on stale data.
- **Audit:** audit entries may appear late in storage systems.

Prolonged high lag can lead to:

- Events being processed later than the business expects.
- Backlogs occupying log storage for extended periods.
- Consumers having to process large data volumes after recovery.
- Increased risk of exceeding retention if consumers fall behind for too long.
- Increased latency across downstream event-dependent services.
- Difficulty meeting SLAs or workflow completion deadlines.

Lag does not mean data has been lost. As long as records remain within retention and consumers can read, the group can catch up. However, if retention deletes data before the group reaches it, the consumer may lose the ability to read the entire original backlog.

## 7. Common Causes of Increasing Lag

### 7.1. Producers Generating Data Faster Than Consumers Can Process

This is a common cause. Producer throughput increases due to traffic spikes, batch imports, campaigns, or an upstream service emitting more events than normal.

How to recognize it:

- Record send rate increases.
- Consumer processing rate does not increase proportionally.
- Lag grows across multiple partitions.
- Listeners do not necessarily throw errors; they simply cannot keep up.

The response is to characterize incoming load, inspect consumer capacity, and decide whether to scale or throttle producers if the system supports backpressure.

### 7.2. Slow Consumer Processing

Listeners may execute database queries, HTTP calls, heavy computations, or writes to multiple external systems. If processing time per record rises, consumer throughput drops and lag grows.

What to measure:

- Listener processing duration.
- Database/HTTP wait times.
- Retry counts.
- Batch size and records per poll.
- CPU, heap, GC, and thread utilization.

Increasing consumer count does not fix an overloaded downstream dependency. You may need to optimize queries, batch writes, tune connection pools, cache, or reduce synchronous work inside the listener.

### 7.3. Consumers Stopped or Unassigned

Consumers may not be running due to crashes, deployments, configuration errors, or inability to reach brokers. A consumer group may have no active members or lack consumers receiving assignments.

A group with no consumers can still have old committed offsets while lag continues growing as producers write data. Distinguish an inactive group from an active group that is processing slowly.

Check group state, members, assignments, and listener container startup logs before increasing concurrency.

### 7.4. Frequent Rebalances

Rebalances occur when members join/leave the group, subscriptions change, or consumers fail poll/heartbeat requirements. During a rebalance, affected partitions may temporarily go unprocessed.

Possible causes include:

- Continuous container restarts.
- Consumers exceeding `max.poll.interval.ms` due to slow processing.
- Unstable networking or brokers missing heartbeats.
- Frequent deployment scale-ups/scale-downs.
- Changes to topic subscriptions or partition counts.

If rebalances occur continuously, adding more consumers can make matters worse. Find the root cause destabilizing group membership.

### 7.5. Retries or Poison Records Slowing Down a Partition

A failing record can be retried repeatedly or wait through backoff delays. If error handling blocks the partition, subsequent records on the same partition must wait. Lag on that partition climbs while other partitions may remain normal.

What to check:

- Listener exceptions and retry counts.
- Whether the error handler is seeking, retrying, or routing records to a DLT.
- Backoff durations and retry attempt counts.
- Error rate per topic/partition.
- Whether the DLT is growing unusually.

Do not retry indefinitely on data errors that cannot resolve themselves. Distinguish transient dependency errors from invalid payloads and establish an appropriate DLT policy.

### 7.6. Skewed Key Distribution

If many records share the same key or certain keys are hot, one partition can receive far more data than others. A consumer group cannot split a single partition across multiple consumers in the same group.

The symptom is high lag on one partition while other partitions remain near zero. Inspect key distribution, per-partition throughput, and processing duration for records in the hot partition.

Changing keys or adding partitions can help future distribution, but it can affect key ordering and does not automatically redistribute old records. This is a design change that must be evaluated beforehand.

### 7.7. Broker or Network Issues

Brokers can slow down due to disk I/O, CPU, replication, request queues, or networking. Slow consumer fetches reduce processing rate even when the listener does little work.

Monitor broker request latency, bytes in/out, under-replicated partitions, network errors, and consumer fetch metrics. If multiple groups simultaneously lag on topics served by one cluster, investigate shared infrastructure.

## 8. Reading Lag with the Kafka CLI

Kafka provides the `kafka-consumer-groups.sh` tool to inspect consumer group state and offsets.

List groups:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Describe a specific group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service
~~~

The output typically includes columns similar to:

| Column | Meaning |
| --- | --- |
| GROUP | Consumer group name. |
| TOPIC | Topic the group is reading. |
| PARTITION | Specific partition. |
| CURRENT-OFFSET | Group's committed offset. |
| LOG-END-OFFSET | Log end marker reported by the tool. |
| LAG | Offset distance between log end and current offset. |
| CONSUMER-ID | Consumer member identifier if present. |
| HOST | Host of the consumer member. |
| CLIENT-ID | Consumer's client ID. |

Column names or formatting can differ across Kafka CLI versions. If `CURRENT-OFFSET` does not exist yet, the tool may display a dash and report lag as unknown instead of a valid number.

Illustrative output example:

~~~text
GROUP            TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
billing-service  payment-events 0          1200            1210            10
billing-service  payment-events 1          900             1500            600
billing-service  payment-events 2          750             755             5
~~~

In the example, partition 1 has a lag of 600, significantly larger than the other two partitions. Start investigating that partition: which consumer is assigned, which keys concentrate there, whether records are failing/retrying, or which downstream task is slow.

You can also view group state depending on the Kafka version:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service \
  --state
~~~

Or view assignments/members:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group billing-service \
  --members \
  --verbose
~~~

Specific options depend on the Kafka version. Check the help output of the script bundled with your cluster/client.

## 9. Lag, Consumer Position, and Commit Cadence

A consumer may have polled records without committing yet. Thus, committed lag and position-based lag can differ.

Example:

- Log end offset is 1,000.
- Consumer position has advanced to 980.
- Latest committed offset is 950.

Then:

- Position-based distance: 20.
- Committed lag: 50.

The consumer has already read part of the backlog, but has not persisted durable progress to the group coordinator yet. If the consumer stops, it may re-read from committed offset 950.

This is not necessarily an error. If the container uses batch acknowledgement, offsets may be committed after the poll batch finishes processing. However, committing too infrequently makes committed lag appear higher than the actual amount of pending work.

Read lag alongside consumer position, records consumed, commit rate, and listener processing metrics. Do not increase commit frequency merely to make dashboards look better; committing too often adds extra requests and coordinator overhead.

## 10. Lag with Transactions and Isolation Levels

For consumers reading transactional data, the isolation level affects which records are visible.

- `read_uncommitted` allows consumers to read records belonging to uncommitted transactions as well.
- `read_committed` only returns records from committed transactions and stops at the last stable offset (LSO), the safe boundary for committed data.

If a transaction stays open for a long time, the LSO can fall below the log end offset. Consumers using `read_committed` cannot read past the unfinished transaction region, even as the log end offset continues to climb.

Therefore, lag measured against the log end offset may include distance that a `read_committed` consumer cannot yet read because a transaction is still open. This is not necessarily slow consumer processing; inspect transactional producers, open transaction durations, and LSO/high-watermark metrics in your tooling.

When investigating lag on transactional topics, verify the consumer's isolation level and the lag definition displayed by your monitoring tool.

## 11. Lag with Log Compaction and Retention

### 11.1. Log Compaction

On a compacted topic, Kafka can remove older versions of the same key during compaction. Offsets in the log can have gaps relative to the records seen by the application.

Therefore, the offset difference on a compacted topic does not necessarily equal the number of payloads waiting for the consumer. Lag remains useful for tracking read position, but you must understand log compaction semantics.

### 11.2. Retention and the Risk of Data No Longer Available to Read

Kafka retains records according to retention policies. If a consumer group falls behind longer than the retention window, its committed offset can fall behind the partition's log start offset.

When the consumer resumes, Kafka may report an offset-out-of-range condition. Subsequent behavior depends on `auto.offset.reset` and the application's recovery policy.

Example:

- The group committed offset 100.
- Retention deletes old segments, raising the log start offset to 500.
- The consumer returns at offset 100, but data from that offset no longer exists.
- The consumer must handle the offset-out-of-range situation; resetting to `earliest` starts from remaining data, while `latest` can skip the still-retained backlog.

This is why you should set alerts on lag/time lag and ensure capacity to drain backlogs before data expires past retention. Prolonged high lag can turn from a latency problem into a risk of being unable to replay all data.

## 12. Adding Consumers to Reduce Lag

Scaling consumers is one way to increase throughput, but it only helps when assignable partitions remain and the bottleneck is consumer capacity.

For example, a topic with six partitions:

~~~text
6 partitions

Concurrency 2:
  Consumer A -> P0, P1, P2
  Consumer B -> P3, P4, P5

Concurrency 6:
  Consumer A -> P0
  Consumer B -> P1
  Consumer C -> P2
  Consumer D -> P3
  Consumer E -> P4
  Consumer F -> P5
~~~

The diagram is only one illustrative assignment; the assignor may distribute differently. Within the same group, useful consumers are bounded by the number of assigned partitions. Increasing concurrency from six to ten does not create extra parallel reading threads for a six-partition topic.

Before scaling, check:

- Is lag growing across all partitions or only a few partitions?
- Do consumers have enough CPU, memory, and threads?
- Do database or HTTP dependencies still have capacity?
- Is listener duration dominated by I/O?
- Are rebalances or poll timeouts occurring?
- Are there enough partitions for the target concurrency?

If consumers have already saturated the database, adding consumers can overload the database and cause lag to grow even faster. Scale the entire processing pipeline, not just the consumer count.

### 12.1. Is Adding Partitions the Solution?

Increasing partitions can expand future parallelism for the group. However, it does not automatically split the existing backlog into the new partitions; existing records remain in the old partitions.

Additionally, changing the partition count can alter key-to-partition mapping under the default partitioner. If key-based ordering matters, evaluate the impact before increasing partitions.

Adding partitions also increases metadata, replication traffic, and broker resource usage. It is a topology decision, not a default firefighting action whenever lag climbs.

## 13. Monitoring Lag with Metrics in Spring Kafka Systems

In a Spring Kafka application, combine Kafka client metrics, listener metrics, and infrastructure metrics to diagnose lag causes.

Metric groups to observe:

| Group | Suggested Metrics | Meaning |
| --- | --- | --- |
| Consumer fetch | Fetch rate, fetch latency, bytes consumed | Whether consumers are fetching data efficiently from brokers. |
| Consumer records | Records consumed rate, records lag/max lag if exported by client | How much consumers are reading and fetch distance to log end. |
| Listener | Processing count, processing duration, error count | Whether listeners process quickly or slowly and whether errors occur. |
| Commit | Commit rate, commit latency, commit failures | Whether reading progress is being recorded reliably. |
| Group | Member count, assignment, rebalance count | Whether the group is stable and partitions are distributed reasonably. |
| Producer | Record send rate, request latency | Whether incoming data rate has spiked unusually. |
| Broker | Request queue, disk, network, ISR | Whether Kafka infrastructure is the bottleneck. |

Spring Kafka can integrate with Micrometer to record listener observations/timers depending on configuration and version. The Kafka client also exposes consumer metrics; metric names, granularity, and export mechanisms depend on the Kafka client version and monitoring stack.

Do not assume a single metric always represents committed lag for the whole group. Some consumer metrics reflect fetch lag or consumer-runtime lag; committed group lag is typically collected via the Kafka Admin API, exporters, or group administration tools.

Tag metrics with appropriate labels such as consumer group, topic, and partition, while controlling cardinality. If the system has thousands of partitions or dynamic topics, exporting every label to every metric system can significantly raise monitoring costs.

## 14. Designing Lag Alerts

A good alert should detect trends and impact rather than relying solely on a single static threshold.

You can combine:

- Absolute lag by group/topic.
- Maximum lag on a single partition.
- Lag growth rate over a time window.
- Time lag or age of unprocessed records.
- Consumer groups with no members or missing assignments.
- Listener error rate and processing latency.
- Duration for which lag remains continuously above threshold.

Illustrative alert rules example:

| Severity | Reference Condition | Action |
| --- | --- | --- |
| Warning | Lag grows continuously for several minutes while time lag stays within SLA | Check throughput, partition distribution, and consumer utilization. |
| Critical | Time lag breaches SLA or lag keeps rising even though consumers are active | Immediately investigate listeners, downstream dependencies, and brokers. |
| Critical | Group has no consumers while topic continues receiving data | Restore listeners/containers or deployments. |
| Critical | Committed offset is older than log start offset | Assess data expired past retention and execute recovery plan. |

Specific thresholds must be based on normal throughput, SLAs, and retention. A telemetry topic may tolerate tens of thousands of records of lag if that equals only a few seconds; a transactional topic may require alerting when records are delayed by a few seconds.

Avoid alerting on a single sample. Use time windows, sustained conditions, and per-service thresholds to reduce false alerts.

## 15. Investigation Runbook When Lag Increases

When receiving a lag alert, proceed from broad scope down to specific partitions.

1. **Identify group and topic:** which consumer group, topic, and environment have lag.
2. **Inspect per-partition lag:** determine whether all partitions are climbing or only one partition.
3. **Check group state/members:** verify whether the group has active consumers and complete partition assignments.
4. **Compare producer and consumer throughput:** see whether incoming data surged or consumer rate dropped.
5. **Check listener latency/errors:** verify whether listeners are slow, retrying, or stuck on a failing record.
6. **Check rebalances/polls:** verify whether the group is rebalancing continuously or consumers are exceeding `max.poll.interval.ms`.
7. **Check dependencies:** database, HTTP, connection pools, CPU, memory, GC, and network.
8. **Check brokers:** fetch latency, request queues, disk, replication, and network.
9. **Check retention:** determine whether the backlog risks exceeding data retention time.
10. **Evaluate remediation:** scale consumers, optimize listeners, adjust partitions, or throttle producers based on the identified root cause.

Do not reset offsets to zero out lag as a default fix. Resetting offsets can skip unprocessed data or cause data to be re-read; it directly alters business progress and requires an intentional decision.

## 16. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| Lag is the exact number of messages waiting in consumer memory. | Lag is usually an offset distance in the log, not messages buffered in RAM. |
| Zero lag means the service is healthy. | The group might be inactive or the topic might have no new data; check state and throughput. |
| High lag means data is lost. | It is usually a backlog; inability to read only happens if data expires past retention or offsets are skipped/reset. |
| All lag metrics are identical. | Metrics may be based on committed offset, consumer position, fetch position, or different log milestones. |
| Offsets are a contiguous event count. | Offsets are log positions; compaction/transactions can create gaps between records visible to the application. |
| Adding consumers always reduces lag. | Parallelism is capped by partitions, and the bottleneck may lie downstream or in brokers. |
| Simply add partitions whenever lag is high. | Identify the bottleneck first; adding partitions affects key ordering and topology. |
| Committing an offset proves business work is complete. | Commits only record group progress; consistency with databases/APIs must be designed separately. |
| Resetting offsets makes the system healthier. | Resetting can skip or replay data; business impact must be evaluated. |
| Retention is unrelated to lag. | Consumers falling behind too long may lose access to old data once retention deletes segments. |

## 17. Consumer Group Lag Operations Checklist

When monitoring a consumer group, verify:

1. Per-topic-partition lag metrics and group totals exist.
2. Committed lag is distinguished from consumer/fetch position lag.
3. Producer rate and consumer processing rate are tracked.
4. Listener processing duration, error, and retry metrics exist.
5. Member count, assignments, and rebalances are monitored.
6. Alerts exist for lag growth trends and time lag/SLA.
7. Retention is checked whenever a backlog persists.
8. Partition skew and key distribution are evaluated.
9. Procedures exist to scale consumers without overloading downstreams.
10. Runbooks exist for offset reset/replay with proper business approval.

Consumer group lag is a vital indicator of how well a system keeps up with incoming data. Its value comes from combining per-partition offsets with throughput, processing latency, group state, and retention to pinpoint root causes. When lag semantics and trends are read accurately, operations teams can spot bottlenecks early, estimate backlog drain times, and choose recovery actions without accidentally skipping business data.


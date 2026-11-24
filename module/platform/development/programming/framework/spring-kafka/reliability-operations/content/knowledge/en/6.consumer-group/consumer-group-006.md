# Consumer Group Lag

Consumer group lag is the amount of progress by which a consumer group trails the data available in Kafka. For each partition, lag is typically expressed as the difference between the end offset of the log and the group's committed offset. Sustained lag growth can indicate that consumers are not keeping up with producer rate, processing is slow, partition load is unevenly distributed, or consumers are repeatedly failing.

Lag is an important signal in Kafka operations, yet it does not explain its own root cause. A group with high lag might be processing steadily and catching up after a traffic spike. Conversely, low lag does not guarantee a healthy system if records are committed before side effects finish or the application is skipping data under a special policy.

To interpret lag accurately, you must understand which offsets are being compared, how lag is computed per partition, how quickly the backlog is changing, and what state the consumer group is in. Investigation requires combining lag with throughput, processing duration, commits, rebalances, errors, and record age.

## 1. What Is Consumer Group Lag?

Kafka stores records in each partition and numbers offsets sequentially by position in the log. A consumer group maintains its own committed offset for each partition the group has processed. Consumer group lag describes the gap between the latest data position and the position the group has committed.

For example, a partition has:

- A log end offset of 1,250.
- A group committed offset of 1,200.

Under the standard offset calculation, the group has roughly 50 offsets to advance:

~~~text
Lag = Log end offset - Committed offset
    = 1,250 - 1,200
    = 50
~~~

The committed offset typically represents the next offset the consumer group will read, not the offset of the last processed record. If a consumer has processed record offset 1,199 and committed offset 1,200, the next read starts at 1,200.

Lag is calculated separately per partition. Total group lag is usually the sum of lag across monitored partitions. However, total lag can hide a hot partition with a massive backlog while other partitions have near-zero lag. When investigating, always check the sum, the maximum value, and the per-partition lag distribution.

## 2. Offsets to Distinguish

To understand a lag figure, you need to know which end-of-log reference the system is using.

### 2.1. Consumer position

Consumer position is the next position the consumer will read in client memory. After `poll` returns records, the position may already advance even if the application has not finished processing those records and has not committed offsets yet.

Therefore, position is not synonymous with committed offset. If the consumer stops before committing, the next startup may re-read from the old committed offset.

### 2.2. Committed offset

The committed offset is durably stored progress for the consumer group. It can be written via auto-commit, synchronous/asynchronous consumer commits, or the mechanism managed by the Spring Kafka listener container.

If the application commits offsets after successful processing, committed offset is a useful signal for measuring recorded progress. If the application commits before completing side effects, lag may drop while business work has not actually finished. Consequently, commit timing directly affects the operational meaning of lag.

### 2.3. Log end offset (LEO)

Log end offset is the next offset at the end of the partition leader's log. It reflects the latest position written on the leader, including data that may not yet be fully replicated to all replicas.

Some lag tools use the log end offset as the baseline. This is a common measurement, though not every record at the tail of the log is necessarily ready for consumers to read in every configuration.

### 2.4. High watermark (HW)

High watermark is the boundary up to which prior records have been replicated under Kafka's criteria to allow consumers to read. For consumers reading in normal mode, data past the high watermark is not returned as replication-committed data.

If lag is computed from LEO, part of the gap may lie in the region written by the leader that has not yet reached the high watermark. Therefore, lag calculated against LEO can appear higher than the amount of data a consumer can currently read.

### 2.5. Last stable offset (LSO)

For consumers using isolation level `read_committed`, Kafka only returns committed transactional records and stable data up to the Last Stable Offset (LSO). An open transaction can hold the LSO behind LEO or HW.

As a result, a `read_committed` consumer may show lag relative to LEO even though data past the LSO cannot be read until the transaction finishes. When investigating a transactional group, examine long-running open transactions and producer state alongside lag.

### 2.6. Summary of positions

| Position | Meaning | What it helps you understand |
|---|---|---|
| Consumer position | Next read position in the client | How far the consumer has polled |
| Committed offset | Stored progress of the group | Where a restart will resume |
| LEO | End of log on the leader | How far the leader has appended data |
| HW | Boundary of data replicated sufficiently for reading | How far standard consumers can read |
| LSO | Stable boundary for `read_committed` | How far transactional consumers can read |

Different tools may choose LEO, HW, or LSO as the lag baseline. When comparing dashboards with CLI commands or exporter metrics, check the metric definition and offset source being used.

## 3. Calculating Lag per Partition

Using the log end offset calculation:

~~~text
partition_lag = log_end_offset - committed_offset
~~~

If a group has no committed offset yet, tools may show an unknown state, a special value, or compute from the offset reset policy depending on implementation. Do not assume committed offset equals 0 in all cases.

Example:

| Partition | LEO | Committed offset | Lag |
|---|---:|---:|---:|
| 0 | 10,500 | 10,480 | 20 |
| 1 | 8,900 | 8,700 | 200 |
| 2 | 9,300 | 9,250 | 50 |
| 3 | 11,100 | 10,600 | 500 |
| **Total** | | | **770** |

The group has a total lag of 770, yet partition 3 accounts for most of the backlog. Looking only at the total, an operations team might add consumers when the true cause is skewed key distribution or a group of records in partition 3 processing very slowly.

Offset lag is also not always equal to the exact count of physically readable records. Due to log compaction, retention, transaction markers, and non-contiguous offsets in visible data, subtracting offsets represents a positional distance in the log. Tools may label it record lag, but understand that it is an offset-based measurement.

## 4. Record Lag and Time Lag

Two complementary perspectives:

- **Offset lag:** the offset distance between the end of the log and the committed offset.
- **Time lag:** the age of unprocessed records or the time difference between the latest data and the data the group is currently processing.

For instance, a lag of 10,000 records may be tiny if the topic receives 100,000 records per second, yet critical if the topic only receives 10 records per minute and the head of the backlog has been waiting for hours.

Time lag must also be clearly defined. It can measure the age of the oldest unprocessed record, the time delta from the newest record's timestamp to the record the group is reading, or the timestamp difference between the head of the log and the committed position. Different definitions carry different meanings and depend on producer or broker timestamps.

If producers send incorrect timestamps, clocks skew, or records are replayed from an older source, time lag can be misleading. Combine offset lag with record age, throughput, and business objectives.

## 5. Why Does Consumer Group Lag Grow?

Lag grows when the incoming data rate exceeds the group's processing rate over a period of time, or when the group stops making progress. Common causes fall into several categories.

### 5.1. Producers send faster than consumers process

If producers generate 20,000 records/sec while the whole group only processes 15,000 records/sec, the backlog grows by roughly 5,000 records every second under steady rates.

Causes may include increased traffic, changes in producer batching, a backfill job replaying historical data, or multiple producers writing to the topic. Before adding consumers, measure ingress rate and processing rate to know the exact deficit.

### 5.2. Slow per-record processing

Listeners may call databases, HTTP APIs, payment services, or perform heavy CPU work. If a dependency slows down, each record takes longer and consumer throughput drops.

Signals to inspect:

- Processing time per record and per batch.
- Database connection pools, lock waits, and query latency.
- HTTP timeouts, retries, and downstream errors.
- CPU saturation, heap pressure, and GC pauses.
- Payload sizes and deserialization times.

### 5.3. Skewed key distribution

Kafka assigns a partition to only one consumer at a time within the same group. If key partitioning sends most traffic to one partition, the consumer holding that partition can become overloaded while other consumers sit idle.

Increasing concurrency cannot split one partition across multiple consumers in the same group. Inspect key distribution, partition counts, throughput, and per-partition lag. If business rules allow, you can change the key or partitioning strategy, though such changes can affect ordering and how old/new data is distributed.

### 5.4. Inactive or insufficient consumers

Consumers may crash, restart continuously, lose broker connectivity, have configuration errors, or receive no partition assignments. If fewer active consumers are running than expected, total throughput drops and lag rises.

Check group state, member count, partition assignments, startup logs, and connection errors. Having members present in a group does not guarantee every member is actively processing partitions.

### 5.5. Frequent rebalances

Rebalances occur when members join or leave the group, partition counts change, or the group must redistribute partitions. During a rebalance, consumers may pause processing. If rebalances repeat continuously, useful processing time drops dramatically.

Common causes:

- Consumers exceed `max.poll.interval.ms` due to slow batch processing.
- Consumers miss heartbeats or have unstable connections.
- Continuous deployments/restarts.
- Changes in partition count or group membership.
- Timeout settings mismatched with processing duration.

Monitor rebalance counts, rebalance durations, member churn, and intervals between poll calls to pinpoint the cause.

### 5.6. Retries and poison record failures

A failing record can be retried repeatedly or halt listener processing on a partition. If blocking retries have long backoffs, the consumer slows down its poll cadence. If a record cannot be processed and has no recovery policy, the group can get stuck at the same position.

Inspect retry counts, exceptions, backoffs, DLT, and offset state. A solid retry policy must distinguish transient errors from unrecoverable data errors.

### 5.7. Slow commits or missing commits

A consumer may poll and process data while committed offsets fail to advance due to commit errors, delayed commits, or misconfigured acknowledgment settings. Lag based on committed offsets then grows even though consumer position has moved further ahead.

Check commit latency, commit failures, `AckMode`, auto-commit, and transactions. If the application processes asynchronously and commits at the wrong time, committed offsets may reflect progress out of sync with actual side effects.

### 5.8. Long-running open transactions

With `read_committed` consumers, a long-running open producer transaction can hold back the LSO and prevent consumers from reading records after that transaction in the partition. Lag measured against LEO can rise even though consumers have read all stable data available.

Inspect transaction timeouts, the producer owning the transaction, commit/abort errors, and the transaction coordinator. Do not simply try to speed up consumers when the read boundary is blocked by an incomplete transaction.

## 6. How to View Consumer Group Lag

Kafka provides the `kafka-consumer-groups` CLI tool to inspect groups, members, partition assignments, committed offsets, and lag.

Example:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service
~~~

The output typically includes columns like:

~~~text
GROUP            TOPIC   PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
billing-service  orders  0          1200            1250            50   consumer-a
billing-service  orders  1          900             1100            200  consumer-b
~~~

Column names and formatting may vary by Kafka version. Key values to read:

- **CURRENT-OFFSET:** the committed offset saved by the group.
- **LOG-END-OFFSET:** the end-of-log reference used by the tool to calculate lag.
- **LAG:** the offset gap as computed by the tool.
- **CONSUMER-ID / HOST / CLIENT-ID:** the member holding the partition if assigned.

If the group has no members, the group may be inactive or consumers may have stopped. Lag can still exist because committed offsets are stored independently of consumer processes.

You can inspect group state:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service \
  --state
~~~

And inspect members/assignments:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server broker1:9092 \
  --describe \
  --group billing-service \
  --members \
  --verbose
~~~

Options may vary across Kafka distributions. Run `kafka-consumer-groups.sh --help` in the target environment to confirm syntax.

Do not use offset reset flags such as `--reset-offsets` during routine diagnostics. Resetting offsets alters the group's position and can skip data or replay large volumes of records. Only execute a reset when the business goal, partition scope, target offsets, and recovery plan are clearly defined.

## 7. Measuring Lag with AdminClient

Internal monitoring applications can use `AdminClient` to read a group's committed offsets and partition end offsets. The example below illustrates fetching both offset sets:

~~~java
Properties properties = new Properties();
properties.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "broker1:9092");

try (Admin admin = Admin.create(properties)) {
    String groupId = "billing-service";

    Map<TopicPartition, OffsetAndMetadata> committed =
        admin.listConsumerGroupOffsets(groupId)
             .partitionsToOffsetAndMetadata()
             .get(10, TimeUnit.SECONDS);

    Set<TopicPartition> partitions = committed.keySet();
    Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> ends =
        admin.listOffsets(
            partitions.stream().collect(Collectors.toMap(
                tp -> tp,
                tp -> OffsetSpec.latest()
            ))
        ).all().get(10, TimeUnit.SECONDS);

    committed.forEach((partition, metadata) -> {
        long current = metadata.offset();
        long end = ends.get(partition).offset();
        long lag = Math.max(0L, end - current);

        System.out.printf(
            "%s-%d committed=%d end=%d lag=%d%n",
            partition.topic(),
            partition.partition(),
            current,
            end,
            lag
        );
    });
}
~~~

This is a baseline example for partitions that already have committed offsets. Production systems must handle partitions with no commits yet, rebalancing groups, authorization errors, timeouts, and topic/partition changes while fetching the two offset sets. The two queries also do not form an atomic snapshot: producers and consumers can continue advancing between reading committed offsets and end offsets.

When measuring lag for `read_committed`, understand which end-offset reference the tool uses. `ListOffsets` with `OffsetSpec.latest` normally retrieves end offsets according to the API and Kafka version semantics; it does not automatically expose every LSO/HW view in all configurations. Do not directly compare self-computed figures against an exporter using a different baseline without checking definitions.

## 8. Measuring Backlog Growth and Drain Rates

A single lag number at one point in time only shows the size of the gap. To know whether a group is catching up, observe the rate of lag change over time.

Let:

- `L` be the current backlog measured in offset/record lag.
- `λ` be the incoming record rate, in records/sec.
- `μ` be the consumer processing and commit rate, in records/sec.

If rates are steady and `μ` exceeds `λ`, the backlog drain rate is approximately:

~~~text
net_drain_rate = μ - λ
~~~

Estimated time to catch up:

~~~text
catch_up_time = L / (μ - λ)
~~~

Example:

- Current lag is 600,000 records.
- Producers generate 8,000 records/sec.
- Consumers process and commit 10,000 records/sec.

The backlog drain rate is 2,000 records/sec:

~~~text
catch_up_time = 600,000 / 2,000
              = 300 seconds
              = 5 minutes
~~~

If `μ` is equal to or less than `λ`, the group cannot durably drain the backlog. Adding consumers only helps if it actually increases `μ`; if the bottleneck is a hot partition, database, or downstream API, adding consumers may not help.

This calculation is an estimate. Throughput fluctuates with time, record size, partitions, batching, retries, and dependencies. Compute separately per partition or over a sufficiently long measurement window to avoid drawing conclusions from a brief burst.

## 9. Consumer Lag and Catch-Up Time

When backlog grows after a high-traffic spike, the operational question is usually whether the group can catch up before a deadline.

Estimation workflow:

1. Measure current lag per partition and for the whole group.
2. Measure producer ingress rate over the same time window.
3. Measure consumer processing/commit rate under steady state.
4. Compute net drain rate.
5. Compare catch-up time against the SLO or when the business requires fresh data.
6. Verify the consumer rate does not overload databases, APIs, or brokers.

For example, a group has a lag of 1.2 million records, ingress of 4,000 records/sec, and processing of 7,000 records/sec:

~~~text
net_drain_rate = 7,000 - 4,000 = 3,000 records/sec
catch_up_time  = 1,200,000 / 3,000 = 400 seconds
~~~

If the catch-up target is 2 minutes, current throughput is insufficient. The system needs higher processing capacity or reduced ingress during recovery. If you merely raise concurrency when the database is already saturated, per-record latency can rise and `μ` may even drop.

## 10. How to Reduce Lag Safely

There is no single lag-reduction fix for every cause. Choose the measure based on the bottleneck.

### 10.1. Increase parallel processing capacity

If there are enough partitions and downstream still has headroom, increasing concurrency or consumer count in the group can raise total throughput.

Before scaling up:

- Confirm the topic has enough partitions to distribute to new consumers.
- Check database connection pools and downstream concurrency limits.
- Inspect key distribution to detect hot partitions.
- Measure processing duration and commits after scaling.
- Monitor rebalances during scaling.

If partition count is smaller than consumer count, surplus consumers will process no data. Adding partitions is a change that impacts partitioning and ordering; evaluate key mapping, existing data, and consumer assignments.

### 10.2. Optimize per-record processing

If per-record processing time is high, focus on dependencies:

- Optimize database queries and indexes.
- Use bulk inserts/updates where appropriate.
- Reduce HTTP round trips or batch requests.
- Set bounded timeouts and retries.
- Avoid redundant computations or repeated deserialization.
- Bound payload sizes and remove unnecessary work from the consumer thread.

Measure p95/p99 to identify slow records. A low average can hide a few records stalling an entire partition.

### 10.3. Tune max.poll.records

`max.poll.records` controls how many records are returned in a single poll. Larger batches can improve bulk processing efficiency but lengthen the time before the next poll. Smaller batches reduce per-cycle processing duration and limit retry blast radius, at the cost of higher polling overhead.

Tune based on `max.poll.interval.ms` and p95/p99 batch processing times. Do not raise `max.poll.records` simply because lag is high; if consumers are already missing poll cadences, larger batches can trigger additional rebalances.

### 10.4. Tune retries and DLT

If lag is caused by failing records retrying for too long:

- Separate retryable errors from non-retryable data errors.
- Cap retry attempts and total retry duration.
- Use appropriate backoff intervals.
- Route records to a DLT once recovery policies are exhausted.
- Ensure DLT publication and original offset commits follow chosen semantics.

A DLT lets the main partition keep progressing once failing records are handled per policy. However, monitor the DLT separately; otherwise, backlog simply moves from the main topic to the error topic.

### 10.5. Pause when downstream is overloaded

Spring Kafka containers can pause/resume to throttle incoming work while downstream recovers. Pausing must go through the appropriate container API, preserve the framework's poll loop, and have clear resume conditions.

Pausing does not make the backlog disappear; it stops consumers from taking on more work while the target system is overloaded. While paused, producers may keep writing and lag can grow. Alerts and a post-resume recovery plan are required.

## 11. Rebalances and Lag

Rebalances can increase lag because consumers pause processing, partitions are revoked and reassigned, and consumers may have to re-read from committed offsets. A single brief rebalance is not necessarily an incident; continuous rebalances are a warning sign.

Factors to check:

- Is batch processing duration approaching or exceeding `max.poll.interval.ms`?
- Are consumers restarting, crashing, or losing heartbeats?
- Are deployments causing multiple members to leave the group simultaneously?
- Were partitions or subscriptions modified?
- Is the assignment strategy causing skewed load distribution?
- Are consumers completing side effects after a partition has already been revoked?

In Spring Kafka, the listener container and rebalance listener provide integration points to handle partition assignment/revocation. When partitions are revoked, the application should safely finish or cancel running work and commit valid progress before losing ownership, if configuration allows.

Do not try to reduce lag by repeatedly restarting consumers. Mass restarts typically trigger more rebalances and lower throughput during recovery.

## 12. Lag and Delivery Semantics

Lag reflects the commit progress of a consumer group, so it must be read alongside delivery semantics.

### 12.1. At-least-once

If consumers only commit offsets after successful processing, a failure occurring after side effects but before commit can cause records to be re-read. Lag may grow or stall during retries. Consumers must be idempotent so duplicates do not repeatedly alter business state.

### 12.2. At-most-once

If consumers commit offsets before processing, lag may drop even when side effects have not succeeded. When the application fails after committing, records can be skipped. A low-lag dashboard cannot directly detect business data lost due to premature commits.

### 12.3. Exactly-once in Kafka

With Kafka transactions, an application can commit output records and input offsets within the same transaction. Downstream consumers using `read_committed` only observe committed outputs. When a transaction aborts, offsets and outputs are neither committed together.

Lag in a transactional model still must be interpreted against committed offsets and the appropriate log reference. Long-running open transactions can hold back the LSO and keep records unreadable. EOS within Kafka does not automatically encompass external databases or HTTP APIs outside Kafka.

## 13. Meaningful Lag Alerting

Do not set a single static lag threshold for every topic. Appropriate thresholds depend on ingress rate, SLOs, retention, record size, and business processing time.

A useful alert set can include:

| Alert | Purpose |
|---|---|
| Total lag exceeds threshold across consecutive windows | Detects sustained backlogs |
| Max partition lag rises rapidly | Detects hot partitions or stalled consumer members |
| Sustained positive lag growth rate | Consumers are not keeping up with ingress |
| Oldest unprocessed record age breaches SLO | Detects real business latency |
| Group has zero members while lag remains | Detects stopped consumer groups |
| Abnormal spike in rebalances | Detects consumers failing to maintain cadence |
| Commit failures or stagnant committed offsets | Detects progress not being recorded |
| Rising DLT lag | Detects errors accumulating in the recovery stream |

Use time windows and sustained-duration conditions to avoid paging on brief traffic spikes that self-recover. Also set alerts per critical group/topic rather than only cluster-wide.

## 14. Runbook When Lag Spikes Suddenly

When paged, investigate systematically to locate where the backlog sits.

### Step 1: Confirm the scope

- Which group is affected?
- Which topics and partitions have lag?
- Is lag growing across all partitions or only a few?
- Does the group have active members and assignments?
- When did lag begin rising?

### Step 2: Determine if the backlog is still growing

Compare lag across multiple timestamps, producer ingress rate, and consumer processing/commit rate. If lag is shrinking, the group may be self-recovering. If lag keeps climbing, identify the throughput deficit.

### Step 3: Check consumer health

Inspect restarts, crashes, rebalances, `max.poll.interval.ms`, batch processing duration, commit failures, thread pools, and GC. If consumers hold no assignments, check group state and partition counts.

### Step 4: Check dependencies

Measure database latency, connection pools, HTTP timeouts, downstream error rates, CPU, and network. If a dependency is the bottleneck, scaling consumers may make things worse.

### Step 5: Choose mitigation

- Increase concurrency if partitions and downstream capacity remain available.
- Optimize processing when per-record latency is high.
- Tune batch size when poll cycles run too long.
- Fix key/partitioning if a hot partition exists.
- Tune retries/DLT if poison records are blocking progress.
- Restore brokers/ISR or resolve long-running open transactions if the root cause is on the Kafka side.

### Step 6: Verify recovery

Observe lag dropping, oldest record age returning to target, processing rate exceeding ingress rate for the required duration, stable rebalances, and healthy downstream load. Record the root cause and configuration changes to prevent recurrence.

## 15. Common Operational Mistakes

| Practice | Risk | Remediation |
|---|---|---|
| Looking only at total lag | Misses hot partitions | Track max lag and per-partition distribution |
| Treating offset lag as exact record count in all cases | Misinterprets log compaction, transactions, or offset gaps | Verify how the tool computes lag and whether it uses LEO/HW/LSO |
| Adding consumers when downstream is saturated | Database/API slows further and lag rises | Measure bottlenecks before scaling |
| Resetting offsets to zero out lag | Skips data or replays massive volumes | Reset only with a business decision and controlled plan |
| Repeatedly restarting consumers when lag rises | More rebalances and lower throughput | Investigate polling, dependencies, and consumer errors |
| Committing offsets before side effects | Artificially low lag while risking lost business work | Commit after processing or use appropriate transactions |
| Ignoring the DLT | Backlog merely shifts to the error stream | Monitor DLT and replay procedures |
| Using one lag threshold for all topics | Noisy alerts or missed incidents | Set thresholds based on ingress, SLOs, and retention |

## 16. Consumer Group Lag Design and Operations Checklist

Before taking dashboards and alerts to production, answer:

1. Is lag calculated from committed offset to LEO, HW, or another baseline?
2. Are metrics broken down by group total, per partition, and per member?
3. Does the group have committed offsets for all partitions?
4. Are offset lag and unprocessed record age tracked separately?
5. Do producer ingress rate and consumer processing/commit rate use the same units and measurement window?
6. Can you calculate net drain rate and catch-up time after a backlog spike?
7. Are hot partitions, key skew, and assignment imbalances detected?
8. Does the dashboard include rebalances, poll intervals, commit failures, retries, and dependency latency?
9. Is there an idempotency policy when records are re-read after failures or rebalances?
10. Is there a clear runbook before raising concurrency, adding partitions, or resetting offsets?

Consumer group lag is a progress indicator, not a root-cause diagnosis. Reading committed offsets, end-of-log baselines, and per-partition lag distributions accurately shows where a group is falling behind. Combining lag with ingress/processing rates, processing durations, rebalances, and record age lets operations teams forecast catch-up times and select safe recovery actions without overloading systems or risking unintended data loss.

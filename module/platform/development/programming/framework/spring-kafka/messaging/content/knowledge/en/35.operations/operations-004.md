# Reading Current Offset and Log End Offset

When operating Kafka, two values to inspect regularly are a consumer group's **current offset** and each partition's **log end offset**. Current offset shows the position the consumer group has committed to resume reading from; log end offset shows the end position of the log. The difference between the two is the common basis for calculating **consumer lag**.

You can read these values using `kafka-consumer-groups.sh` or Kafka `AdminClient`. Describing a consumer group only reads metadata and offsets; it does not move offsets. This makes it a safe inspection step before deciding whether to scale consumers, investigate processing errors, or run a recovery procedure.

## 1. Offsets are numbered per partition

Kafka does not assign a single global offset sequence across an entire topic. Each partition has its own log and offset sequence. The first record in a partition typically starts at offset `0`; subsequent records receive increasing offsets within that partition.

For example, topic `orders.events` has three partitions:

```text
orders.events-0: 0, 1, 2, 3, 4, ...
orders.events-1: 0, 1, 2, 3, ...
orders.events-2: 0, 1, 2, 3, 4, 5, ...
```

A consumer group stores progress separately for each topic-partition pair. Therefore, when checking offsets, inspect each partition individually; an aggregated topic-level number can hide a single lagging partition.

An offset is a position in the log, not a business ID. It carries no global meaning across partitions or across topics.

## 2. Distinguishing current offset, log end offset, and lag

### 2.1. Current offset is the committed offset

In `kafka-consumer-groups --describe` output, the `CURRENT-OFFSET` column shows the committed offset stored by Kafka for that consumer group and partition. This value is usually **the next position the consumer group will read after recovering from the committed offset**.

If a consumer processed record offset `99` and committed progress after that record, the committed offset is typically `100`. When the consumer restarts, it resumes from offset `100`.

Thus, the committed offset is not the offset of the last processed record. It is the next position.

### 2.2. Log end offset is the end of the log

Log end offset is the boundary offset at the end of the log range queried by the tool. The leader log end offset (LEO) is the next position to be assigned to a new record; if a partition holds offsets `0` through `999`, LEO is `1000`. In CLI output, `LOG-END-OFFSET` is the end marker returned by the Kafka API for lag calculation; when replication or transactions are present, do not assume this marker always equals the leader's raw LEO.

LEO is the trailing boundary value, not the offset of the last record. If a partition has no records yet, LEO is typically `0`.

### 2.3. Consumer lag

For a partition with a valid committed offset:

\[
lag = logEndOffset - committedOffset
\]

Example:

```text
CURRENT-OFFSET = 100
LOG-END-OFFSET = 125
LAG            = 25
```

The consumer group committed position `100`, while the log can be read up through position `124`. The offset difference is `25`.

Visual example: records span offsets 0 to 124, while the committed offset sits at position 100.

```text
Record offsets:  ... 96  97  98  99 | 100 101 102 ... 124
                                      ^                 ^
                              committed offset       log end = 125

Lag = 125 - 100 = 25 offsets
```

Lag is the difference in offset units, which does not always equal the exact count of remaining records to process. Compaction, transactions, and offset gaps can make those two concepts diverge.

## 3. Do not confuse committed offset with the consumer's current read position

A running consumer may have polled and processed records well ahead of its committed offset. When commits happen per batch, periodically by time, or after acknowledgment, `CURRENT-OFFSET` can trail the consumer's in-memory position.

Example:

```text
Consumer in-memory position:     150
Committed offset on broker:      120
Log end offset:                  200
```

The consumer has advanced to position `150` but has only committed `120`. If the process terminates unexpectedly before the next commit, the consumer can re-read part of the records starting from `120`. This is one source of redelivery/duplicates under at-least-once processing.

Factors affecting when commits happen include:

- `enable.auto.commit` and the auto-commit interval if using Kafka consumer auto-commit.
- Spring Kafka `AckMode` such as `RECORD`, `BATCH`, `TIME`, `COUNT`, `MANUAL`, or `MANUAL_IMMEDIATE`.
- Whether the listener succeeds or throws an exception.
- Error handlers, retries, and recovery policies.
- Consumer rebalances or process restarts.

When investigating lag, inspect committed offsets, consumer position/records-lag metrics, listener processing time, and the time of the most recent commit. Do not conclude a consumer is stuck from a single `CURRENT-OFFSET` snapshot.

## 4. Reading offsets with kafka-consumer-groups

The most common command:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

On Windows, the script may be named `kafka-consumer-groups.bat`; on Linux/macOS it is typically `kafka-consumer-groups.sh`. Run the command from Kafka's `bin` directory or provide the full path to the script.

Example output:

```text
GROUP         TOPIC         PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
orders-service orders.events 0          100             125             25   consumer-1
orders-service orders.events 1          210             220             10   consumer-2
orders-service orders.events 2          80              80              0    consumer-3
```

Meaning of the main columns:

| Column | Meaning |
| --- | --- |
| `GROUP` | Consumer group name |
| `TOPIC` | Topic for which the group has offsets |
| `PARTITION` | Specific partition |
| `CURRENT-OFFSET` | Committed offset, i.e. the next position after the latest commit |
| `LOG-END-OFFSET` | End of the log queried by the tool for the partition |
| `LAG` | Difference between log end offset and committed offset |
| `CONSUMER-ID` | Consumer member currently assigned the partition, if the group is active |

Output may also include `HOST` and `CLIENT-ID`. Exact column names and formatting vary across Kafka versions, though reading the three offset columns remains similar.

## 5. Inspecting a specific topic

You can restrict output to a single topic:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --topic orders.events
```

This is helpful when a consumer group subscribes to multiple topics and you need to investigate `orders.events` specifically.

If you do not know the group ID, list the groups:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

If you need to inspect group state:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --state
```

To inspect members and partition assignments:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Options such as `--state`, `--members`, and `--verbose` depend on the Kafka CLI version. If your version does not support an option, run `kafka-consumer-groups.sh --help` for that distribution.

## 6. Connecting to a secured cluster

For clusters with TLS or SASL enabled, supply a client properties file via `--command-config`:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.internal:9093 \
  --command-config client.properties \
  --describe \
  --group orders-service
```

Example `client.properties` for SASL_SSL/SCRAM:

```properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="ops-reader" password="<injected-secret>";
ssl.truststore.location=/etc/kafka/secrets/ops.truststore.p12
ssl.truststore.password=<injected-secret>
ssl.truststore.type=PKCS12
```

`<injected-secret>` is a placeholder that should be replaced with the secret via a secret manager or a temporary restricted-permission file before running the CLI. Kafka CLI does not interpolate environment variables with `${KAFKA_OPS_PASSWORD}` syntax inside properties files. Never commit real passwords to a repository or share client properties files containing credentials over unsecured channels.

The principal running the command needs permissions to describe consumer groups and read topic metadata/offsets. If you encounter `GroupAuthorizationException` or ACL errors, ask the Kafka administrator to grant the required read/describe permissions on the group; do not alter offsets to work around authorization errors.

## 7. Understanding output when there is no committed offset yet

A new group might not have committed offsets for a partition yet. In that case, `CURRENT-OFFSET` and `LAG` may display `-` instead of a number.

This is not necessarily an error. It can happen when:

- The group has never consumed that partition.
- The consumer has not read or committed any records yet.
- Auto-commit is disabled and the listener has not committed yet.
- The group was just created or is currently undergoing assignment.

When there is no committed offset, the actual starting position depends on `auto.offset.reset` (`earliest`, `latest`, or `none`) and current offset state. `earliest`/`latest` applies only when no valid offset exists under consumer semantics; setting it does not immediately write a committed offset on configuration alone.

Check group state, consumer logs, `auto.offset.reset`, and when the listener started before concluding the group lost its offsets.

## 8. LEO, high watermark, and last stable offset

In advanced operations, distinguish three partition markers:

| Marker | Meaning |
| --- | --- |
| Log End Offset (LEO) | Next position in the leader's log; the next offset to be assigned |
| High Watermark (HW) | Boundary of data replicated sufficiently to be readable by normal consumers |
| Last Stable Offset (LSO) | Stable read boundary for `read_committed` consumers, not advancing past open transactions |

In clusters with transactions, LEO, HW, and LSO can differ. A `read_uncommitted` consumer can read up to the high watermark and observe uncommitted transactional records; a `read_committed` consumer reads only up to LSO so it never sees records from unfinished transactions. Kafka CLI/Admin APIs and exporters may use different isolation boundaries when querying end offsets.

Therefore, lag reported by a CLI or exporter depends on how the tool queries end offsets and isolation levels. When comparing against a consumer with `isolation.level=read_committed`, check whether your metrics/exporters use the corresponding boundary. Do not assume every value labeled `end offset` represents the same marker across all tools.

## 9. Offset gaps and compacted topics

Offsets increase in write order, but not every offset number necessarily corresponds to a readable record.

Offset gaps can appear when:

- The topic uses log compaction and older records are removed.
- A transaction is aborted; its records are withheld from `read_committed` consumers.
- Retention deletes old segments.
- Internal log operations leave offsets non-contiguous relative to the records visible to a consumer.

For example, a partition has readable offsets `10`, `12`, `15`; committed offset is `10`, and end offset is `16`. The offset difference is `6`, but that does not guarantee exactly six records are waiting to be processed.

Thus, lag is an offset-based progress indicator. To know actual throughput and processed record counts, combine it with `records-consumed-rate`, application counters, and per-partition metrics.

## 10. Reading committed offsets and log end offsets with AdminClient

In operational applications or internal tooling, you can use Kafka `AdminClient` instead of shelling out to the CLI. AdminClient can query committed offsets for a group and log end offsets for the corresponding partitions.

The following example retrieves partitions with committed offsets for group `orders-service`, then queries their log end offsets:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.ListOffsetsResult;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;

public class ConsumerOffsetInspector {

    public static void main(String[] args) throws Exception {
        Map<String, Object> properties = new HashMap<>();
        properties.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );

        try (AdminClient admin = AdminClient.create(properties)) {
            String groupId = "orders-service";

            Map<TopicPartition, OffsetAndMetadata> committed = admin
                    .listConsumerGroupOffsets(groupId)
                    .partitionsToOffsetAndMetadata()
                    .get(10, TimeUnit.SECONDS);

            Map<TopicPartition, OffsetSpec> requests = new HashMap<>();
            committed.keySet().forEach(partition ->
                    requests.put(partition, OffsetSpec.latest())
            );

            Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> ends =
                    admin.listOffsets(requests)
                            .all()
                            .get(10, TimeUnit.SECONDS);

            committed.forEach((partition, metadata) -> {
                long currentOffset = metadata.offset();
                var endInfo = ends.get(partition);

                if (endInfo == null) {
                    System.out.printf(
                            "%s: unable to read log end offset%n",
                            partition
                    );
                    return;
                }

                long logEndOffset = endInfo.offset();
                long lag = logEndOffset - currentOffset;

                System.out.printf(
                        "%s current=%d end=%d lag=%d%n",
                        partition,
                        currentOffset,
                        logEndOffset,
                        lag
                );
            });
        }
    }
}
```

This snippet is a minimal example; in real applications, externalize bootstrap servers and security properties in configuration and never hardcode credentials. `AdminClient` must have permissions to describe the group and query topic offsets.

Key APIs:

- `listConsumerGroupOffsets(groupId)` retrieves committed offsets per topic-partition.
- `partitionsToOffsetAndMetadata()` returns a map of partition → committed offset metadata.
- `listOffsets(requests)` queries offset markers per partition.
- `OffsetSpec.latest()` requests the end-of-log marker under the client/API version's semantics.

The example prints only partitions that already have committed offsets. Uncommitted partitions are absent from the map; if you need to check every partition of a topic, fetch topic/partition metadata first and query `OffsetSpec.latest()` for all partitions.

If `lag` is negative, do not silently clamp it to `0`. Investigate topic deletion/recreation, stale offset metadata, log truncation, or mismatches between the compared offset markers.

## 11. Fetching beginning offsets to check retention

Log start/beginning offset is the lowest offset still readable in a partition. It helps verify whether the committed offset still lies within retained data.

Example using `OffsetSpec.earliest()`:

Assuming `partitions` is the set of `TopicPartition` values obtained from the metadata of the topic under inspection:

```java
Map<TopicPartition, OffsetSpec> beginningRequests = new HashMap<>();
partitions.forEach(partition ->
        beginningRequests.put(partition, OffsetSpec.earliest())
);

Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> beginnings =
        admin.listOffsets(beginningRequests)
                .all()
                .get(10, TimeUnit.SECONDS);
```

If the committed offset is smaller than the beginning offset, data from the position where the consumer wants to resume may already have been deleted by retention. The consumer can hit `OffsetOutOfRangeException` and fall back to `auto.offset.reset` or a designed recovery policy.

If the committed offset is larger than the log end offset, investigate why offset metadata no longer matches the current log. Do not reset offsets blindly based on a single snapshot; verify topic identity, partitions, and cluster state first.

## 12. Aggregating lag across a group

Lag is typically calculated per partition. Total group lag can be summed as:

\[
groupLag = \sum_{p \in partitions} lag_p
\]

Example:

| Partition | Current offset | Log end offset | Lag |
| ---: | ---: | ---: | ---: |
| 0 | 100 | 125 | 25 |
| 1 | 210 | 220 | 10 |
| 2 | 80 | 80 | 0 |
| **Total** |  |  | **35** |

A total lag of `35` shows the group is 35 offsets behind the end of the log under this calculation. However, partition `0` has greater lag than the other partitions; inspect the specific consumer member assigned to that partition.

Total lag is useful for overview dashboards, though it does not replace per-partition lag. A single hot partition can fall behind while total lag still looks small.

## 13. Reading lag alongside consumer group state and assignments

While a group is rebalancing, partition assignments can shift while the tool is querying. Offset snapshots may not represent a steady state.

Check group state and members:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service \
  --members \
  --verbose
```

Observe:

- Whether the group is `Stable` or `PreparingRebalance`/`CompletingRebalance`.
- How many members are active.
- Which partitions are assigned to each member.
- Whether any partitions have no assigned member.
- Whether members churn constantly due to restarts, timeouts, or heartbeat failures.

If lag increases alongside constant rebalancing, check `max.poll.interval.ms`, listener processing time, `session.timeout.ms`, `heartbeat.interval.ms`, and network errors. Do not simply raise concurrency before identifying the cause of rebalances.

## 14. Interpreting common scenarios

| Symptom | Likely possibilities | Investigation path |
| --- | --- | --- |
| Lag steadily at 0 | Group has committed right up to the end of the log | Also monitor throughput and error rate |
| Lag growing steadily | Producers outpace consumers or listener/downstream is slow | Measure processing time, consumer rate, partition skew, and dependency latency |
| Lag spikes then drops | Traffic burst or consumer catching back up | Check recovery time and peak lag |
| One partition has high lag | Key skew, hot data, or an unhealthy consumer member | Check partition assignment, key distribution, and member logs |
| Current offset stuck, end offset rising | Consumer not committing, hung listener, rebalances, or commit failures | Check consumer state, logs, AckMode, and error handler |
| Current offset stuck, end offset also stuck | Topic has no traffic or consumer stopped advancing | Check producer rate and listener health |
| Current offset shows `-` | Group has not committed offsets for the partition | Check new group status, auto.offset.reset, and initial processing |
| Negative lag | Offset metadata and current log are out of sync or markers differ | Check topic recreation, truncation, and isolation semantics |
| High lag after downtime | Consumer is draining an accumulated backlog | Estimate drain rate and downstream capacity |
| Low lag but slow business processing | Consumer polled/committed, but side effects or internal queues lag | Measure business latency, pending work, and commit boundaries |

## 15. Estimating backlog drain time

If you know current lag and net processing speed, you can estimate how long consumers need to catch up to producers.

Suppose:

- Current lag is `120,000` offsets.
- Consumers process an average of `1,500` records/second.
- Producers continue writing `1,000` records/second.

The net lag drain rate is `1,500 - 1,000 = 500` records/second. Estimated drain time:

\[
120000 / 500 = 240\ seconds
\]

That is roughly four minutes if rates remain steady and the offset gap approximates the number of records to process. For compacted topics, offset gaps, or transactions, this is only a rough estimate. Measure actual per-partition throughput and watch the lag trend after scaling.

If consumer throughput is less than or equal to producer throughput, the backlog will not shrink. In that case, scale processing capacity, throttle producers, optimize listeners/downstream services, or adjust partitioning if the workload allows.

## 16. Causes of growing lag

Rising lag can originate across multiple layers:

**Producers and partitioning:** sudden spike in producer throughput; skewed key distribution sending most records to one partition; too few partitions for the required parallelism.

**Consumers:** low concurrency, too few replicas, frequent rebalances, unsuitable `max.poll.records`, or consumers not receiving partitions.

**Listeners:** overly slow synchronous work, slow HTTP/database calls, lock contention, exhausted thread pools, or oversized batches.

**Retries and errors:** failing records retried repeatedly, blocking backoff holding up a partition, failing DLT publishes, or downstream persistently returning errors.

**Brokers/network:** high fetch latency, overloaded brokers, flaky network, slow disk I/O, or partition leader changes.

Correlate lag with producer send rate, consumer records rate, listener duration, error/retry rate, rebalance count, and broker health to isolate the bottleneck.

## 17. Interpreting lag carefully with transactions

If producers use Kafka transactions and consumers set `isolation.level=read_committed`, consumers do not read records belonging to uncommitted transactions. A long-running open transaction can hold LSO back, forcing `read_committed` consumers to wait even as LEO keeps advancing.

In this situation, `LEO - committedOffset` can appear larger than the records currently visible to a `read_committed` consumer. Check transaction duration, LSO/HW if your tools expose them, and the consumer's isolation level.

Never change `isolation.level` in production merely to make a lag dashboard drop. Doing so can expose uncommitted transactional data to consumers and break business semantics.

## 18. Observing lag via metrics and monitoring

Beyond the CLI, collect lag periodically through a Kafka exporter, JMX exporter, or your Kafka platform's monitoring tools. Application metrics can complement this with:

- Records consumed rate.
- Listener processing duration p95/p99.
- Commit latency and commit failures.
- Rebalance total/rate.
- Assigned partition count.
- Retry rate and DLT publish rate.
- Downstream database/HTTP latency.

Dashboards should include both total lag and per-partition lag. Alerts should evaluate sustained lag duration, growth rate, and processing SLAs, rather than firing whenever lag is non-zero.

An alert rule worth considering:

```text
consumer group lag > threshold for N minutes
AND consumer throughput < producer throughput
```

Thresholds and duration windows depend on throughput, SLAs, and backlog drain capacity for each stream. An audit topic can tolerate higher lag than a payment-processing topic.

## 19. Offset operations that can impact data

`kafka-consumer-groups --describe` is a read-only operation. Options like `--reset-offsets` modify group progress and can cause records to be re-read or skipped depending on the new target position.

Before resetting offsets, prepare a specific plan:

1. Confirm the exact cluster, group, topic, and partitions.
2. Record current committed offsets and log start/end offsets.
3. Clarify the business objective: replay, skip backlog, or recover after retention.
4. Stop the consumer group or ensure it is inactive as required by your CLI/version.
5. Run preview/dry-run mode if supported and review the output.
6. Obtain operational approval, save backup/offset records, and prepare a rollback plan.
7. Execute only when potential duplicates or data loss are fully understood.

Never run `--reset-offsets --execute` solely because lag looks high. Lag is a signal to investigate; resetting offsets changes data processing semantics.

## 20. Checklist for investigating current offset and log end offset

When lag is reported for a consumer group, work through this order:

1. Confirm the exact bootstrap servers, security config, and group ID.
2. Run `kafka-consumer-groups --describe --group ...` to inspect per-partition offsets.
3. Check `CURRENT-OFFSET`, `LOG-END-OFFSET`, and `LAG`.
4. Verify group state, member count, and partition assignments.
5. Check whether committed offsets exist or show `-`.
6. Compare snapshots across multiple timestamps to tell whether lag is growing, shrinking, or flat.
7. Check producer throughput, consumer rate, and listener processing duration.
8. Check retries, DLT, commit failures, and rebalances.
9. If offsets look anomalous, inspect beginning offsets, retention, topic recreation, and transaction isolation.
10. Consider resetting offsets only after having a recovery plan and assessing data impact.

A consumer group's current offset is its committed progress, whereas log end offset marks the end of a partition's log. Their difference is a useful lag indicator, but must be read alongside consumer position, commit policy, group state, partition assignments, and transaction semantics. Use the CLI for quick checks, AdminClient to integrate into operational tooling, and metrics to track trends continuously.

## 21. Self-check

1. Why are Kafka offsets tracked separately per partition?
2. What position does `CURRENT-OFFSET` in `kafka-consumer-groups --describe` represent?
3. Why is the committed offset normally the next position rather than the last processed record?
4. What is the formula for per-partition lag?
5. Why can current offset be lower than the consumer's in-memory processing position?
6. When can `CURRENT-OFFSET` display `-`?
7. How do LEO, high watermark, and last stable offset differ?
8. Why does lag not always equal the exact number of pending records in a compacted topic?
9. Which AdminClient APIs are used to read committed offsets and log end offsets?
10. Why should you never reset offsets based solely on a single high-lag snapshot?

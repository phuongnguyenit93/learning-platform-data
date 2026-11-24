# Dead-Letter Topic Retention Policy

A dead-letter topic (DLT) stores Kafka records that failed after retries or were classified as non-retryable. The DLT is typically where operations teams find the root cause, fix data or configuration, and replay records. If retention is too short, records can be deleted before being detected and handled; if retention is too long without a size limit, the DLT can fill up broker disks.

A retention policy must balance three goals: **enough time to recover**, **bounded disk usage**, and **preserving data needed for investigation/audit**. Kafka enforces retention via topic configurations such as `retention.ms`, `retention.bytes`, and `cleanup.policy`. These settings must be designed alongside DLT workflows, consumer capacity, replication factor, and application replay capabilities.

## 1. How Long Should a DLT Be Retained?

There is no single duration right for every system. DLT retention must exceed the total time required to detect an incident, investigate, fix the root cause, and replay records.

You can plan using the formula:

\[
T_{retention} \geq T_{detect} + T_{investigate} + T_{fix} + T_{replay} + T_{buffer}
\]

Where:

- `T_detect`: time from when a record enters the DLT until an alert fires and someone picks it up.
- `T_investigate`: time spent analyzing exceptions, payloads, dependencies, and business impact.
- `T_fix`: time to deploy a fix or repair data/configuration.
- `T_replay`: time needed to replay the entire backlog at a safe throughput.
- `T_buffer`: reserve margin for weekends, off-hours, prolonged outages, or approval workflows.

For example, if a system needs up to 2 days to detect, 2 days to investigate, 3 days to fix, and 2 days to replay, a 7-day retention is too tight. Add buffer so weekend incidents or sudden DLT spikes do not cause data loss.

| DLT objective | Policy to consider |
|---|---|
| Operations and replay within a few days | Finite retention, larger than target recovery time. |
| Extended incident investigation or internal audit | Longer retention, strict access control, and optional export to archival storage. |
| Multi-month/multi-year compliance storage | Do not rely solely on a Kafka topic; consider archiving to object storage or a dedicated archive system. |
| DLT prone to sudden spikes | Combine time-based retention and byte limits to protect brokers. |

A DLT is not an indefinite archive. If audit requirements exceed Kafka storage capabilities, build an archive pipeline with write confirmation, integrity checks, and an independent retrieval policy.

## 2. Key Retention Configurations

Kafka manages log cleanup through `cleanup.policy`. With the `delete` policy, the two primary settings are `retention.ms` and `retention.bytes`.

| Configuration | Meaning | Unit/scope |
|---|---|---|
| `cleanup.policy` | Selects log cleanup mode: delete old segments, compact by key, or combine both. | Topic |
| `retention.ms` | Maximum time logs are kept before old segments become eligible for deletion under `delete` policy. | Milliseconds, topic |
| `retention.bytes` | Log size limit per partition; when exceeded, old segments can be deleted to free space. | Bytes, per partition |
| `segment.bytes` | Maximum size of a single log segment before rolling a new segment. | Bytes, per partition |
| `segment.ms` | Maximum time before Kafka rolls a new segment even if the current segment is not full. | Milliseconds, per partition |
| `delete.retention.ms` | How long tombstone markers are kept in a compacted topic. | Milliseconds, compaction-only |

With `cleanup.policy=delete`, Kafka can delete old segments when **either the time limit or the size limit is reached**, whichever makes a segment eligible first. These two limits complement each other; do not treat `retention.bytes` as extra space that only triggers after `retention.ms` expires.

In common Kafka configurations, the default `retention.ms` is 604,800,000 ms (7 days), and the default `retention.bytes` is `-1` (unlimited by size). Actual values can be overridden at the broker or topic level, so inspect effective cluster settings rather than relying on defaults.

## 3. Choosing `cleanup.policy` for a DLT

For a DLT storing failed events for investigation and replay, the typical choice is:

```properties
cleanup.policy=delete
```

The `delete` policy retains record history for the retention window and then removes old segments. This suits DLTs because each individual failure may need separate inspection, even when multiple records share the same business key.

Kafka also supports `compact` and `compact,delete`:

| Policy | Behavior | Suitable for a historical DLT? |
|---|---|---|
| `delete` | Deletes old segments by time/size retention. | Usually best for keeping every failure within a time window. |
| `compact` | Keeps the latest value per key; older records with the same key can be removed once compaction runs. | Only suitable if the DLT is designed as latest error state per key without needing all failure history. |
| `compact,delete` | Compacts retained segments and deletes old segments per retention. | Not suitable if complete DLT history must be preserved. |

For instance, three failed events for the same `orderId=O100` might need independent investigation. With `cleanup.policy=compact`, records sharing a key can be compacted down to the newest one, losing history of the first two failures. If the goal is preserving every dead-letter event, use a unique key per event or prefer `delete`.

`delete.retention.ms` is not the normal DLT retention period. That setting controls how long tombstone markers are kept in compacted topics; do not use it in place of `retention.ms` on a DLT with `cleanup.policy=delete`.

## 4. Configuring `retention.ms` and `retention.bytes`

The example below configures the DLT to retain up to 14 days and cap size at 10 GiB per partition:

```properties
cleanup.policy=delete
retention.ms=1209600000
retention.bytes=10737418240
```

Explanation:

- `1209600000` ms = 14 days.
- `10737418240` bytes = 10 GiB per partition.
- If the topic has 6 partitions, the logical size limit is roughly 60 GiB across the topic before accounting for replication and overhead.
- Old segments become eligible for deletion when retention time expires or when a partition exceeds the byte limit.

Setting `retention.ms=-1` disables the time limit; setting `retention.bytes=-1` disables the size limit. If both are `-1` and cleanup policy is `delete`, the DLT has no finite retention limit under these two settings. This risks filling up disks if there is no archive pipeline or other cap.

## 5. Creating a DLT with Spring Kafka `TopicBuilder`

When Spring Kafka manages topic creation via `KafkaAdmin`, you can declare a `NewTopic` bean with topic-level configurations:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class DeadLetterTopicConfiguration {

    @Bean
    NewTopic ordersDltTopic() {
        return TopicBuilder.name("orders.events-dlt")
                .partitions(6)
                .replicas(3)
                .config("cleanup.policy", "delete")
                .config("retention.ms", "1209600000")
                .config("retention.bytes", "10737418240")
                .build();
    }
}
```

In this example:

- The DLT has 6 partitions to match a 6-partition source topic when the recoverer sends records to the corresponding partition.
- A replication factor of 3 requires enough eligible brokers in the cluster.
- `cleanup.policy=delete` retains every failed record during the retention window.
- `retention.ms` and `retention.bytes` establish both limits per partition.

`NewTopic` specifies the configuration when `KafkaAdmin` creates the topic. If the DLT already exists, inspect its actual config and use the Kafka Admin API or CLI to alter topic settings when needed; do not assume declaring the bean will automatically alter every setting on an existing topic.

Replication factor does not change the per-partition `retention.bytes` value, but it affects the total physical storage the cluster must hold. If using producer `acks=all`, configure an appropriate `min.insync.replicas` to enforce minimum write durability for the DLT.

## 6. Altering Existing DLT Configurations with Kafka CLI

You can change topic configuration using `kafka-configs.sh`:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events-dlt \
  --alter \
  --add-config cleanup.policy=delete,retention.ms=1209600000,retention.bytes=10737418240
```

Inspect configuration:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events-dlt \
  --describe
```

The `--describe` output shows topic-level config overrides. If a property does not appear in overrides, the topic may be inheriting the broker default. Check broker configs as well when determining effective values.

Shortening retention can make old segments eligible for immediate deletion. Before applying in production, confirm the DLT backlog has been processed or archived, and verify the change does not violate the replay window promised to operations.

## 7. Estimating DLT Storage Capacity

DLT capacity depends on failed record volume, compressed record size, retention window, and replication factor.

Logical capacity estimate:

\[
S_{logical} \approx R_{day} \times B_{record} \times D
\]

Where:

- `R_day`: average number of dead-letter records per day.
- `B_record`: average compressed record size, including payload and headers.
- `D`: retention days.

Total cluster capacity estimate:

\[
S_{cluster} \approx S_{logical} \times RF + S_{overhead}
\]

`RF` is the replication factor. `S_overhead` includes indexes, segments, filesystem overhead, and operational headroom; measure it on an actual cluster since compression and partition distribution matter significantly.

Example:

- 1,000 failed records/day.
- Average compressed size of 20 KiB/record.
- 14-day retention.
- Replication factor of 3.

Approximate logical size:

\[
1000 \times 20\ KiB \times 14 \approx 273.4\ MiB
\]

Approximate total across replicas on the cluster:

\[
273.4\ MiB \times 3 \approx 820.2\ MiB
\]

This is a baseline estimate excluding indexes, segment overhead, large headers, traffic bursts, and safety margins. A DLT can spike dramatically during a dependency outage; size for incident scenarios rather than only normal daily averages.

### Dividing the limit per partition

`retention.bytes` applies at the partition level. If a topic has `P` partitions and you want to cap total logical size around `S`, you can start with:

\[
retention.bytes \approx \frac{S}{P}
\]

For example, 60 GiB across 6 partitions corresponds to about 10 GiB per partition. Add headroom if key distribution is skewed or one partition receives more failed records than others. A hot partition can hit its byte limit and delete older data earlier than sibling partitions.

## 8. Retention Is Not Exact Per-Record TTL

Kafka cleans data by log segments, not by deleting individual records at the exact instant they expire. A segment must roll and become eligible under retention/cleanup rules before the broker deletes the file. Therefore:

- `retention.ms` is a log retention limit under `delete` policy, not a precise per-record expiration timer.
- `segment.bytes` and `segment.ms` affect when segments roll and the granularity of cleanup.
- Large segments make time-based deletion coarser because Kafka deletes whole segment files.
- Active segments cannot be deleted like closed segments; thus partition size can temporarily exceed `retention.bytes` before rolling and cleanup complete.
- Actual deletion timing also depends on cleanup cycles and broker load.

Never promise business stakeholders that a record will vanish at exact second N. Treat retention as an operational storage window and build replay/alerting with buffer prior to expiration.

## 9. DLT Partition Count and Replication Factor

A DLT needs enough partitions for how the recoverer routes records. With default `DeadLetterPublishingRecoverer`, records are usually sent to the partition with the same index as the source partition. Consequently, a DLT normally needs at least as many partitions as the source topic.

If the DLT has fewer partitions than the source topic, publishing to a non-existent partition can fail. You can customize the destination resolver to pick valid partitions or let the partitioner decide, while preserving required traceability and throughput.

Replication factor determines how many partition replicas are maintained across the cluster. It is not a retention window and does not replace backups/archives. When a record is deleted due to retention, replicas reflect the truncated log via replication; replication cannot recover expired records.

When designing a production DLT, evaluate:

- Broker count and sustainable replication factor.
- `min.insync.replicas` alongside producer `acks` if stronger write durability is required.
- Disk capacity per broker after replica placement.
- Partition count and key skew of failed records.
- DLT consumer capacity to read and replay before retention expires.

## 10. Replay Procedure Before Records Expire

Retention only helps if operations knows how to process records within the storage window. A safe replay procedure should include:

1. **Detection:** alert when the DLT receives new records or oldest record age climbs.
2. **Classification:** group errors by exception class, error code, source topic, and service.
3. **Remediation:** fix the dependency, configuration, or source data before replaying.
4. **Scoping:** replay by approved source topic, partition, offset range, event ID, or error category.
5. **Traceability:** attach metadata such as `replay-id`, `replayed-at`, `replay-operator`, and DLT source when republishing.
6. **Deduplication:** keep `eventId` and use an idempotent consumer/inbox so side effects are not applied twice.
7. **Verification:** check replayed count, succeeded count, continuing failures, and business offsets/sequences.

If aggregate ordering must be preserved, do not replay records sharing the same key in random order. You may need to sort by original partition and original offset or business sequence, depending on how the DLT was populated. Offsets across different partitions cannot be compared into a single global order.

Never blindly replay the entire DLT back to the source topic before fixing the root cause. Doing so creates error loops, grows the DLT faster, and overloads consumers/databases. Rate-limit replays so you do not overwhelm a freshly recovered system.

## 11. Consumer Offsets and Retention

A consumer group's committed offset does not lock records and does not prevent Kafka from deleting expired segments. If a DLT consumer stays stopped longer than the retention window, old records can be purged even though the group still holds a committed offset pointing there.

When a consumer requests an offset outside the remaining log range, behavior depends on `auto.offset.reset`:

| Value | Behavior when offset is out of range or no committed offset exists |
|---|---|
| `earliest` | Starts from the earliest remaining offset; records deleted by retention cannot be re-read. |
| `latest` | Starts from the current end of the log; may skip remaining backlog depending on reset position. |
| `none` | Throws an error when no valid offset is available. |

For a DLT consumer used for investigation/replay, set `earliest` if you want to read all remaining retained data when a new group starts; however, this cannot bring back expired records. Monitor consumer lag and oldest record age to ensure consumers keep pace inside the retention window.

## 12. Monitoring and Alerting on Retention

A DLT deserves its own dashboard or at least metrics separate from business topics. Metrics to track:

| Metric | Purpose |
|---|---|
| DLT incoming records/rate | Detect abnormal spikes in failed records. |
| DLT bytes per partition | Track `retention.bytes` usage and detect hot partitions. |
| Oldest DLT record age | Identify backlogs nearing the retention window. |
| DLT consumer lag | Show whether DLT handling keeps up with incoming failures. |
| Broker disk usage | Spot disk-exhaustion risks from DLTs or other topics. |
| DLT publish failure | Detect when the recoverer cannot write records to the DLT. |
| Replay success/failure count | Measure recovery effectiveness and recurring failures. |
| Exception class/error category | Highlight widespread system, data, or business errors. |

Alert when:

- DLT ingress exceeds normal thresholds.
- Oldest DLT record age reaches a significant fraction of the retention window, e.g., 70–80%.
- Consumer lag rises continuously or fails to drain after a dependency recovers.
- A partition approaches `retention.bytes` or broker disk crosses operational thresholds.
- Recoverer publishing fails or the DLT topic lacks sufficient partitions/ISR.

Do not monitor only topic-wide totals. A single partition can hit its byte cap while overall topic size remains low, causing old data in that partition to be deleted early.

## 13. Security and Long-Term Storage

DLTs frequently hold failing payloads and exception metadata. Contents can include personal data, tokens, SQL, internal URLs, or deployment details. The longer retention is, the longer sensitive data persists.

Controls to apply:

- Restrict DLT read/write access via ACLs or equivalent authorization.
- Scrub credentials and sensitive headers before publishing to the DLT.
- Encrypt data in transit and at rest per cluster policy.
- Set retention to match recovery needs and data policies, avoiding infinite retention by default.
- If long-term archiving is needed, export records to object storage or an audit store with proper lifecycle/immutability.
- Log who replayed records, when, and with what outcome.
- Verify data deletion workflows against privacy/compliance requirements.

Archiving must confirm successful writes and verify counts/checksums before shortening Kafka retention. Copying unverified data and letting Kafka delete the originals can cause data loss if the archive pipeline breaks.

## 14. Complete DLT Policy Example

An illustrative configuration for an order-processing service:

| Property | Example value | Rationale |
|---|---|---|
| Topic | `orders.events-dlt` | Dedicated DLT for the order stream. |
| Partitions | `6` | Matches a 6-partition source topic when preserving partition indices. |
| Replication factor | `3` | Maintains multiple replicas across the cluster. |
| `cleanup.policy` | `delete` | Retains every failed record during the retention window. |
| `retention.ms` | `1209600000` | 14 days for investigation and replay. |
| `retention.bytes` | `10737418240` | 10 GiB per partition as a storage cap. |
| DLT consumer | `orders-dlt-ops` | Dedicated consumer for investigation/replay. |
| Oldest age alert | `10 days` | Alerts before the 14-day window expires. |

These numbers are only examples. Before applying them, size based on failure rate, record size, partition skew, replication factor, replay capacity, and your system's audit requirements.

## 15. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Records vanish before replay | `retention.ms` is shorter than detection and remediation time. | Increase retention window, alert on oldest record age, and archive if needed. |
| DLT consumes excessive disk | No byte limit set or sustained high failure rate. | Set `retention.bytes`, fix root cause, and monitor broker disk. |
| One partition loses records earlier than others | `retention.bytes` applies per partition and record distribution is skewed. | Monitor bytes/partition, adjust partitioning, or size limits with headroom. |
| DLT only keeps the latest event per key | Topic uses `cleanup.policy=compact` or `compact,delete`. | Use `delete` if every dead-letter event must be kept. |
| `delete.retention.ms` does not change DLT expiration | Confused tombstone retention with log retention. | Use `retention.ms` and `retention.bytes` for `delete` cleanup. |
| Records still exist past retention mark | Kafka deletes by segment, not per-record to the exact second. | Include buffer in replay plans and understand `segment.ms`/`segment.bytes`. |
| Consumer offset out of range | Consumer stopped longer than retention and old offsets were purged. | Reset to earliest surviving offset per reset policy; rely on archives/backups for purged data. |
| Updated `TopicBuilder` but topic config did not change | Topic already existed and live config was not altered. | Use Kafka CLI/Admin API to alter and `--describe` to verify. |
| Replication did not save expired records | Retention deletes logs on the partition and replicas sync the deletion. | Use archives/backups if recovery past retention is required. |

## 16. Key Takeaways

- Choose a retention window larger than the sum of detection, investigation, fix, replay, and buffer times.
- `retention.ms` caps time; `retention.bytes` caps size per partition under `delete` cleanup.
- Once either `delete` limit is met, old segments become eligible for deletion.
- `cleanup.policy=delete` is usually right for DLTs needing every failure preserved; `compact` can discard older records sharing a key.
- `delete.retention.ms` governs tombstones in compacted topics and does not replace `retention.ms` on a standard DLT.
- Retention operates at the segment level, not as an exact per-record TTL.
- Multiply `retention.bytes` by partition count for the topic's logical limit; replication factor multiplies physical cluster storage.
- Committed offsets do not protect records from retention; consumer lag must stay inside the retention window.
- Have an idempotent replay workflow that preserves source metadata and rate-limits replay throughput.
- If retention longer than Kafka's window is required, archive to dedicated storage and verify integrity before reducing retention.

A solid DLT policy starts from realistic recovery times, sizes for failure traffic and partition counts, and then sets `retention.ms`, `retention.bytes`, and `cleanup.policy`. Combining monitoring for oldest record age, consumer lag, and disk usage with a controlled replay workflow ensures failed records have enough time to be handled without letting DLTs consume disk uncontrollably.

## References

- [Apache Kafka — Topic Configurations](https://kafka.apache.org/44/configuration/topic-configs/)
- [Apache Kafka — Consumer Configurations](https://kafka.apache.org/documentation/#consumerconfigs)
- [Spring for Apache Kafka — Dead-letter Publishing](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#publishing-dead-letter-records)
- [Spring for Apache Kafka — KafkaAdmin and Topic Configuration](https://docs.spring.io/spring-kafka/reference/kafka/configuring-topics.html)

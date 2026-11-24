# Managing Dead-Letter Topics

A dead-letter topic (DLT) stores records that failed after retry policies were exhausted or were classified as non-retryable. In Spring Kafka, a DLT is typically published by `DeadLetterPublishingRecoverer` when using `DefaultErrorHandler`, or created in a non-blocking retry flow with `@RetryableTopic`. A DLT isolates failing records so the main stream keeps flowing, while preserving payload data and metadata for investigation, remediation, and replay.

Managing a DLT is a long-term operational responsibility. The topic must have clear naming and partition topology, appropriate replication and retention, least-privilege access control, alerts when backlogs grow, and a controlled replay workflow. Creating a topic with a DLT suffix without assigning ownership lets failed records sit there until retention expires or disks fill up.

## 1. Defining the role of a DLT in the architecture

A DLT is a regular Kafka topic used by convention. The Kafka broker does not inherently know which records are dead-letter; the application and Spring Kafka decide when to route a record to this topic.

Typical flow with blocking retries:

```text
orders.events
      |
      v
@KafkaListener
      |
      +---- processed successfully ----------------> commit per AckMode
      |
      +---- exception
               |
               v
       DefaultErrorHandler
               |
        +------+------+
        |             |
      retry       retries exhausted / fatal error
        |             |
        +-------------+
               |
               v
   DeadLetterPublishingRecoverer
               |
               v
       orders.events.DLT
               |
       +-------+--------+
       |                |
  investigate     controlled replay
```

With non-blocking retries, a record may pass through one or more retry topics before reaching the DLT. Retry topics hold records for scheduled redelivery; the DLT holds records that exhausted attempts or are non-retryable. Clearly distinguish which topics are retry topics and which is the DLT so operators never replay from the wrong one.

## 2. Standardizing DLT and retry topic names

Pick a consistent naming convention for easy discovery, ACL grants, retention policies, and dashboards. Example:

| Source topic | Example retry topic | Example DLT |
|---|---|---|
| `orders.events` | `orders.events-retry-1000` | `orders.events.DLT` |
| `payments.events` | `payments.events-retry-1000` | `payments.events.DLT` |
| `inventory.events` | `inventory.events-retry-1000` | `inventory.events.DLT` |

Spring Kafka uses different suffix conventions depending on the mechanism:

- `DeadLetterPublishingRecoverer` defaults to routing to the source topic plus the `.DLT` suffix.
- `@RetryableTopic` has its own default DLT suffix, typically `-dlt`; configurable via `dltTopicSuffix`.

Do not assume both mechanisms automatically generate the same name. Document the exact topic names in deployment configs, ACLs, dashboards, and runbooks. If changing a suffix, update producer/recoverer settings, topic provisioning, DLT consumers, and alerts together.

Keep the DLT name tied to the source topic. This naming pattern makes data origin and operational policy obvious from the topic name alone, especially when one cluster hosts multiple domains.

## 3. Designing partitions for the DLT

With the default `DeadLetterPublishingRecoverer`, records are normally sent to the same partition number as the source partition. Therefore, the DLT needs at least as many partitions as the source topic when using default partition mapping.

Example:

```text
orders.events
  partition 0 --------------> orders.events.DLT partition 0
  partition 1 --------------> orders.events.DLT partition 1
  partition 2 --------------> orders.events.DLT partition 2
  ...
  partition 11 -------------> orders.events.DLT partition 11
```

If the source topic has 12 partitions, create the DLT with at least 12 partitions when the recoverer preserves partitions. If using a custom destination resolver to map partitions differently, verify that the target partition exists and source metadata is preserved for replay.

Partition count also determines the maximum parallelism of a consumer group reading the DLT. If you want multiple workers processing the DLT concurrently, provide enough partitions and verify that partitioning preserves required ordering.

Do not arbitrarily increase DLT partitions after going live. Partition count affects consumer assignments and key mapping; when replaying back to the source topic, decide explicitly whether to preserve the original partition or use the current key partitioner.

## 4. Creating DLTs before enabling production consumers

In production, provision DLTs ahead of time using IaC, a Kafka operator, or cluster governance workflows. Do not rely on broker auto topic creation to create DLTs with the right partition count, replication, and retention.

Example creating a DLT for a 12-partition source topic on a three-broker cluster:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders.events.DLT \
  --partitions 12 \
  --replication-factor 3
```

If the cluster enforces authorization, the command requires an admin principal with topic creation rights. Listener applications should not be granted broad topic creation rights just so DLTs appear automatically.

When using `@RetryableTopic`, provision both retry topics and the DLT matching the exact naming strategy and partition counts. You can let Spring Kafka auto-create topics locally, but production should explicitly declare replication factors and topic configs; check `autoCreateTopics`, `numPartitions`, and `replicationFactor` attributes on your Spring Kafka version.

## 5. Configuring DLT durability

Because DLTs hold records needed for investigation or recovery, their durability should match the criticality of the events. A common production setup has three replicas and requires at least two replicas in the ISR:

| Topic config | Example | Meaning |
|---|---:|---|
| `replication.factor` | `3` | Number of replicas per partition |
| `min.insync.replicas` | `2` | Minimum in-sync replicas required to accept writes from `acks=all` producers |
| `cleanup.policy` | `delete` | Retains records until retention expires |
| `compression.type` | `producer` | Keeps the codec sent by the DLT producer |

You can apply topic configs after creation:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --alter \
  --add-config min.insync.replicas=2,cleanup.policy=delete,compression.type=producer
```

`min.insync.replicas` only enforces acknowledgement protection when producers use `acks=all`. Verify that the producer used by the recoverer has appropriate acknowledgement settings. If ISR drops below threshold, DLT publishing can fail; this is an error that must be detected and addressed, never a reason to silently drop records.

Replication factor must match actual broker count. For example, RF=3 cannot be satisfied on a single-broker cluster. Never copy local RF=1 settings to production if the DLT must survive broker failures.

## 6. Configuring retention and cleanup policy

DLTs must retain records long enough for operations to detect, analyze, fix, and replay them. Base retention on incident response times, on-call schedules, fix turnaround, replay windows, and organizational compliance rules.

Example retaining the DLT for seven days:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --alter \
  --add-config retention.ms=604800000,cleanup.policy=delete
```

Important properties:

| Config | Operational meaning |
|---|---|
| `retention.ms` | Duration to retain records before becoming eligible for deletion |
| `retention.bytes` | Log size limit per partition |
| `cleanup.policy=delete` | Deletes old segments based on retention |
| `segment.bytes` | Target log segment size |
| `segment.ms` | Maximum time before a segment rolls per config |

Kafka retention is not an exact per-record TTL. Deletion happens per log segment on cleanup cycles; records can persist slightly past the exact retention deadline. Include buffer for cleanup delay when sizing retention.

For DLTs, `cleanup.policy=delete` is usually appropriate because every individual failure needs to be preserved. Do not enable `compact` merely to save disk space: if multiple failing records share a key, compaction can remove older records and erase error history needed for investigation. Use compaction only if the DLT is deliberately designed as a latest-state changelog rather than an archive of every failed event.

If setting `retention.bytes`, note that the limit applies per partition. When one partition hits the threshold, older records on that partition may be deleted before other partitions. Never set `retention.bytes` too low and lose failed records before operations can handle them.

## 7. Estimating DLT storage capacity

Required storage depends on failed record volume, average serialized/compressed record size, retention days, and replication factor.

Rough estimate:

```text
logical bytes = failed records per day
             x average stored bytes per record
             x retention days

physical bytes ≈ logical bytes x replication factor
```

Example with 20,000 failed records per day, 4 KiB average stored size, and 7-day retention:

```text
logical bytes = 20,000 x 4 KiB x 7
              ≈ 547 MiB

with replication factor 3:
physical bytes ≈ 1.6 GiB
```

This is a baseline estimate, excluding indexes, segment overhead, headers, actual compression ratios, replica placement, and incident error spikes. Provision headroom for peak incidents rather than daily averages alone.

Monitor disk usage by topic and partition, and configure broker disk quotas/alerts. A schema regression or widespread dependency outage can spike DLT traffic from a handful of records to millions in a short period.

## 8. Granting separate ACLs for DLT publishers and consumers

Separate permissions across applications publishing to the DLT, investigation tools, and replay tools:

| Principal | Typical required permissions | Scope |
|---|---|---|
| Listener application | `WRITE`, `DESCRIBE` | DLT topic |
| DLT inspector | `READ`, `DESCRIBE` | DLT topic and inspector consumer group |
| Replay service | `READ` on DLT, `WRITE` on target topic, matching group rights | Source/DLT topics and replay group |
| Provisioning principal | `CREATE`, `ALTER`, `ALTER_CONFIGS`, `DESCRIBE_CONFIGS` as needed | Managed topics only |

Example granting DLT publish rights to an application:

```bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --add \
  --allow-principal User:orders-service \
  --operation WRITE \
  --operation DESCRIBE \
  --topic orders.events.DLT
```

Example granting DLT read and group permissions to an inspector:

```bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --add \
  --allow-principal User:dlt-inspector \
  --operation READ \
  --operation DESCRIBE \
  --topic orders.events.DLT

kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --add \
  --allow-principal User:dlt-inspector \
  --operation READ \
  --group orders-dlt-inspector
```

These commands illustrate the Kafka ACL authorizer; principals, operations, and extra permissions depend on your security setup. When the cluster uses SASL/TLS, add `--command-config client.properties` containing appropriate auth settings. Never commit passwords or API secrets directly in scripts or source control.

If DLT publishing participates in a Kafka transaction, the principal also needs permissions on the corresponding transactional ID. Scope permissions to specific resources rather than cluster-wide wildcards.

## 9. Ensuring DLT publishes are acknowledged

The recoverer sends to the DLT using a producer. Calling send does not guarantee the broker persisted the record. If the topic does not exist, partition is invalid, ACL denies access, or brokers lack ISR, the send can fail.

With `DeadLetterPublishingRecoverer`, you can require send failures to be surfaced:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;

DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(kafkaTemplate);

recoverer.setFailIfSendResultIsError(true);
```

Pair the recoverer with `DefaultErrorHandler` as configured on your listener container. When DLT publishing fails, recovery must be treated as failed so the error handler/container applies its fallback policy. Never acknowledge the source record as recovered without confirmed DLT publication.

With transactional listeners, confirm whether the DLT send joins the transaction and whether the transaction manager/recoverer are configured properly. A Kafka transaction covers only Kafka resources participating in that transaction.

## 10. Verifying the DLT topic and effective configuration

After provisioning, verify the topic exists with sufficient partitions:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.events.DLT
```

Read topic configs:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events.DLT \
  --describe
```

Check the consumer group reading the DLT:

```bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --describe \
  --group orders-dlt-inspector
```

Items to confirm:

- The topic exists on the right cluster/namespace.
- Partition count matches the recoverer's partition mapping.
- Leaders and replicas are distributed and ISR meets policy.
- `cleanup.policy`, `retention.ms`, `retention.bytes`, and `min.insync.replicas` are accurate.
- Publisher principal has write access and inspector has read access.
- DLT consumer group shows expected lag and progress.
- Dashboards and alerts watch the exact live topic name.

## 11. Reading and investigating DLT records

A DLT may contain deserialized payloads or raw bytes depending on where the error occurred and serializer settings. Never assume every record is a JSON string or the same Java object type.

For records produced by Spring Kafka recoverers, check source metadata such as:

| Metadata | Purpose |
|---|---|
| Original topic | Identify which topic produced the error |
| Original partition | Identify source partition |
| Original offset | Trace back to the source record |
| Original timestamp | Timestamp of the source record per timestamp type |
| Exception class/message | Classify the error and locate root cause |
| Original consumer group | Identify which consumer group processed the record |

Spring Kafka provides header constants such as `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, `KafkaHeaders.DLT_ORIGINAL_OFFSET`, and `KafkaHeaders.DLT_EXCEPTION_FQCN`. Use the constants from your running Spring Kafka version to read headers rather than guessing header names.

Example inspection listener:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.stereotype.Component;

@Component
class OrdersDltInspector {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersDltInspector.class);

    @KafkaListener(
            id = "orders-dlt-inspector",
            topics = "orders.events.DLT",
            groupId = "orders-dlt-inspector"
    )
    public void inspect(ConsumerRecord<String, Object> record) {
        var originalTopic = record.headers()
                .lastHeader(KafkaHeaders.DLT_ORIGINAL_TOPIC);
        var originalOffset = record.headers()
                .lastHeader(KafkaHeaders.DLT_ORIGINAL_OFFSET);

        log.error(
                "DLT record: topic={}, partition={}, offset={}, key={}, originalTopicHeader={}, originalOffsetHeader={}",
                record.topic(),
                record.partition(),
                record.offset(),
                record.key(),
                originalTopic != null,
                originalOffset != null
        );
    }
}
```

This example only illustrates receiving the record and checking header presence; in real systems, decode headers per Spring Kafka's written types, store investigation records in an incident/audit system, and avoid logging sensitive payloads. If a listener is purely observational, ensure its consumer group and offset policy will not accidentally trigger extra side effects.

## 12. Monitoring DLTs with metrics and alerts

Do not alert only when the first record lands in a DLT. A single failed record may be an isolated glitch; thousands of rapidly arriving records or aged uninvestigated records signal serious operational trouble.

Track at minimum:

| Metric | Meaning | Alert when |
|---|---|---|
| DLT records in | New records entering the DLT | Sudden spike or above baseline |
| DLT bytes in | New failed data volume | Rapid disk/network growth |
| DLT consumer lag | Backlog waiting for inspector/replay consumer | Lag grows steadily or fails to drain |
| Oldest DLT age | Age of oldest uninvestigated record | Breaches response SLA |
| Publish failure | Recoverer fails to send to DLT | Any sustained errors or sudden spike |
| DLT partition skew | Errors concentrated on one partition | One partition grows much faster than others |
| Replay success/failure | Outcome of reprocessing | Repeated replay failures |

A consumer group's `records-lag-max` is a lag indicator, not record age, and does not replace DLT ingest rate. To measure record age accurately, add a DLT-entry timestamp header such as `x-dlt-recorded-at` via an appropriate recoverer header function, or capture receipt timestamp in the inspector. The original event timestamp may already be old before the record ever reaches the DLT.

Tier alerts by severity:

- **Warning:** DLT receives new records at low rate while the inspector keeps up.
- **Critical:** DLT spikes rapidly, inspector lag stalls, record age breaches SLA, or DLT publishing fails.
- **Capacity:** DLT/broker storage approaches disk limits or retention begins deleting records before handling.

Include topic, partition, consumer group, exception class, and dashboard links in alerts so on-call engineers can start investigating immediately.

## 13. Designing an operational dashboard

A practical DLT dashboard should show:

1. Records in per minute by source topic.
2. Bytes in and DLT log storage size over time.
3. Consumer lag for each inspector/replay group.
4. Maximum age of unprocessed records.
5. Breakdown by exception class and source topic.
6. Publish failures and retry/recoverer failures.
7. Replay counts, replay success/failures, and records under manual review.
8. Partitions with the highest backlog.

Provide filters by environment, service, source topic, exception class, and time range. Never display raw payloads or sensitive personal data on dashboards; use event IDs and tracing metadata.

## 14. Controlled DLT replay workflow

Replay means resending records stored in the DLT after fixing the underlying cause. Never automatically replay the entire DLT the moment a service turns healthy; if schemas, data, or side effects were not addressed, records will keep failing or create duplicate effects.

Safe workflow:

1. Pause automatic replay if enabled; keep the DLT intact for investigation.
2. Identify root cause using exception, schema ID, event ID, and source metadata.
3. Fix code, schema, dependency, or business data.
4. Test sample records in staging.
5. Select target records to replay by topic/partition/offset, event ID, or time window.
6. Replay at a throttled rate while monitoring downstream capacity.
7. Verify business outcomes and idempotency.
8. Record an audit entry detailing who replayed, when, record count, and result.
9. Close the incident only once DLT backlog and replay failures return to acceptable levels.

Replaying produces new records with new offsets on the target topic. Preserve original topic/partition/offset and DLT source coordinates in custom headers or an audit store for traceability. If partition ordering must be preserved, use intentional partition mapping instead of relying on key hashing alone and assuming partitions stayed identical.

## 15. Replay example with Spring Kafka

A replay service can read DLT records, resend payloads to the source topic, and attach audit headers. The following Spring Kafka 3.x example assumes the DLT deserializer produces `Object` and the producer serializer supports that value type:

```java
import java.nio.charset.StandardCharsets;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class DltReplayService {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    DltReplayService(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void replay(
            ConsumerRecord<String, Object> dltRecord,
            String targetTopic,
            int targetPartition,
            String replayId
    ) {
        ProducerRecord<String, Object> replayRecord = new ProducerRecord<>(
                targetTopic,
                targetPartition,
                dltRecord.key(),
                dltRecord.value()
        );

        replayRecord.headers().add(
                "x-replay-id",
                replayId.getBytes(StandardCharsets.UTF_8)
        );
        replayRecord.headers().add(
                "x-replay-source-topic",
                dltRecord.topic().getBytes(StandardCharsets.UTF_8)
        );
        replayRecord.headers().add(
                "x-replay-source-partition",
                Integer.toString(dltRecord.partition()).getBytes(StandardCharsets.UTF_8)
        );
        replayRecord.headers().add(
                "x-replay-source-offset",
                Long.toString(dltRecord.offset()).getBytes(StandardCharsets.UTF_8)
        );

        // Wait for broker send acknowledgement before caller acknowledges the DLT record as replayed.
        kafkaTemplate.send(replayRecord).join();
    }
}
```

In real applications, `targetTopic` and `targetPartition` must be validated against source metadata or approved replay rules; never accept them arbitrarily from untrusted requests. If the DLT holds raw `byte[]` due to deserialization failures, the replay producer must preserve raw bytes or deserialize with a fixed schema before sending. If using Avro/Protobuf/JSON Schema, the replay tool needs the matching serializer.

When calling the service from a DLT listener, return normally only after the send succeeds. If sending fails, let the exception propagate so the container does not commit the DLT offset as if replay succeeded. Ensure the listener's error handler does not trap the DLT record in an infinite replay loop.

## 16. Idempotency and ordering during replay

Kafka assigns a new offset to republished records; it has no idea whether a record already caused side effects earlier. Initial processing might have updated a database successfully without committing the offset before later entering replay. Without idempotency, the system can create duplicate orders, charges, or emails.

Protective measures:

- Use stable event IDs and persist completed-processing state.
- Use unique constraints or an inbox table in the database.
- Use upserts/idempotent commands for repeatable side effects.
- Preserve key and partition mapping if per-partition ordering is a business requirement.
- Replay in small batches with rate limits and a kill switch if error rates spike.

Never replay multiple records with the same key concurrently if business logic depends on order. If the source topic's partition count changed, revisit old partition mappings carefully.

## 17. Cleaning up a DLT after resolution

Do not delete a DLT topic just because a dashboard temporarily shows zero lag. Before cleanup, confirm:

- No uninvestigated or pending-replay records remain.
- All related incidents have formal resolution decisions.
- Audit/replay logs are archived in the proper store.
- Retention satisfies storage and compliance policies.
- No consumer groups or replay tools still need to read older records.

Normally, let retention automatically clean old segments per approved policy. Manual topic deletion is high-impact, wiping all topic data and offsets; execute it only through an approved governance workflow after verifying the exact cluster and topic.

## 18. Runbook when DLT volume spikes

| Step | Action | Expected outcome |
|---|---|---|
| 1. Confirm | Check DLT records in, bytes in, lag, and oldest age | Establish severity and start time |
| 2. Isolate | Group by source topic, partition, and exception class | Identify affected services/record types |
| 3. Preserve | Check retention/disk and pause unsafe auto-replay | Prevent data loss during investigation |
| 4. Diagnose | Inspect headers, schema IDs, event IDs, and matching logs | Identify root cause |
| 5. Remediate | Fix schema, code, dependency, ACL, or downstream | Sample records process cleanly |
| 6. Test replay | Replay a small bounded batch | Verify outcomes and idempotency |
| 7. Ramp up | Gradually raise batch/rate within capacity | Backlog drains steadily |
| 8. Close | Record audit, monitor alerts, and close incident | No unplanned backlog remains |

If failures stem from an overloaded downstream system, do not replay even if the DLT consumer can read. Restore capacity first, or replay will simply push load right back onto the failing system.

## 19. Common misconceptions

1. **Creating a single-partition DLT for a multi-partition source topic.** A recoverer preserving source partitions will fail sending to non-existent target partitions.
2. **Setting retention too short.** Records can be purged before operations finishes investigating.
3. **Enabling compaction on a DLT without understanding the consequences.** Multiple failed records with the same key can be compacted away, losing failure history.
4. **Assuming DLT publishes always succeed.** ACLs, missing topics, low ISR, and broker outages can break sends.
5. **Watching only consumer lag.** Lag does not reveal DLT ingest rate or oldest record age.
6. **Replaying everything as soon as the service turns healthy.** Underlying data/schema issues or duplicate side effects may remain unaddressed.
7. **Replaying without preserving source metadata.** Makes tracing new records back to original topic/partition/offset difficult.
8. **Granting wildcard permissions to DLT inspectors.** Exposes failed data across unrelated domains; scope ACLs per topic/group.
9. **Assuming the same suffix across all mechanisms without checking.** `DeadLetterPublishingRecoverer` and `@RetryableTopic` have distinct naming conventions.
10. **Deleting the topic when lag hits 0.** Data needed for audits or other replay groups may still reside in the topic.

Effective DLT management treats the DLT as a core part of messaging operations: provision proper partitions and replication, set sufficient retention, grant role-based ACLs, confirm publish acknowledgements, monitor ingest rate/lag/record age, and maintain an idempotent replay runbook. When these responsibilities are tied to specific service owners and dashboards, the DLT becomes a controlled recovery zone instead of a graveyard of unhandled errors.

# Retention and storage duration

Kafka is designed to retain records for a configured time window or until a configured storage size limit is reached. The mechanism governing whether old data is kept or removed is called **retention**. This is a core part of Kafka's model: it affects how much data consumers can replay, how far behind a consumer is allowed to lag, how much disk capacity to provision, and how topics are designed.

In a Spring Kafka application, producers send records via `KafkaTemplate` and consumers receive records via `@KafkaListener`. These two components do not control a topic's storage lifecycle. Retention is managed on the Kafka broker side via broker settings and per-topic configurations. Spring Kafka can declare topic configs when creating a topic, yet retaining and deleting segments remains Kafka's responsibility.

## 1. What is retention?

Kafka writes records into each partition's log. Logs are divided into **segments**; when the active segment reaches a size or time threshold, the broker closes it and starts a new segment. Older segments can be cleaned up according to the topic's cleanup policy.

Retention determines how long data in the log is kept or up to what maximum size. For topics using the `delete` policy, Kafka can delete old segments once they exceed time or size limits. For topics using `compact`, Kafka cleans up older versions of the same key to retain the latest state per key.

Retention does not mean Kafka deletes a record as soon as a consumer reads it. Multiple consumer groups can read the same record at different times; data remains according to the topic policy until eligible for cleanup. Even when a consumer group commits an offset, the record does not immediately disappear.

For example, topic `orders.events` is configured to retain data for seven days. An analytics service can pause for two days and resume if the needed records still remain within retention. If the service stays down longer than the retention window and old data has been deleted, the consumer cannot recover those records merely by resetting offsets.

## 2. Two primary limits: time and size

### Time-based retention with `retention.ms`

`retention.ms` sets the maximum retention duration for topics using `cleanup.policy=delete`, in milliseconds. When omitted at the topic level, Kafka uses the broker default, typically configured via `log.retention.ms` or equivalent minute/hour properties.

For example, seven days is expressed as:

```text
7 days = 7 x 24 x 60 x 60 x 1000
       = 604800000 ms
```

Common values:

| Value | Meaning |
| --- | --- |
| `retention.ms=86400000` | One-day time limit |
| `retention.ms=604800000` | Seven-day time limit |
| `retention.ms=2592000000` | Approximately 30-day time limit |
| `retention.ms=-1` | No time limit enforced by this property |

`retention.ms=-1` does not mean data is protected forever against all causes of loss. It only disables time-based retention limits; size limits, compaction policies, administrative actions, infrastructure failures, and other mechanisms can still affect the data.

### Size-based retention with `retention.bytes`

`retention.bytes` sets the maximum log size retained **per partition**, not the total size of the entire topic. When a partition exceeds the threshold, Kafka can delete older segments to bring usage back below the limit.

For example, if a topic has six partitions and sets `retention.bytes=10737418240` (10 GiB), the approximate logical limit is 60 GiB for the entire topic. With a replication factor of three, physical storage across brokers may be roughly three times the logical size, excluding overhead, indexes, distribution skew, and temporary space from segment-based cleanup.

A value of `retention.bytes=-1` disables size limits via this property. When size is unbounded here, still control retention duration or disk usage through other operational safeguards.

If both `retention.ms` and `retention.bytes` are configured for a `delete` topic, both limits apply. Old data can be cleaned up either when reaching the time limit or when the partition needs to free space. Therefore, actual retention may be shorter than expected if the size limit is too low relative to the data ingestion rate.

## 3. Kafka deletes data by segment

Kafka does not routinely open individual records to delete them one by one upon expiration. Data is managed by segments. Configurations affecting segment rolling and checking include:

| Configuration | Meaning |
| --- | --- |
| `segment.bytes` | Maximum size of a segment before the log rolls to a new segment |
| `segment.ms` | Maximum duration before the current segment rolls, even if the size limit is not reached |
| `log.retention.check.interval.ms` | Interval at which the broker checks for segments eligible for deletion |

Because cleanup runs by segment and on a check interval, a record does not necessarily vanish at the exact millisecond `retention.ms` expires. A segment may remain until it rolls and the next cleanup check occurs. On low-traffic topics, `segment.ms` can noticeably affect when a segment closes.

This also explains why retention should not be used as a precise per-record expiration timer. If business requirements demand deleting a record at an exact timestamp, design additional storage or deletion mechanisms at the application layer.

## 4. `cleanup.policy`: delete and compact

Time/size retention is usually understood alongside `cleanup.policy`. A topic can use `delete`, `compact`, or a combination of both.

### The `delete` policy

With `cleanup.policy=delete`, Kafka deletes old segments based on retention limits. This is the common choice for event logs, application logs, telemetry data, or events needed for a bounded period.

For example, topic `orders.events` can keep all order events for seven days so analytics services or support systems have time to replay data after an incident.

### The `compact` policy

With `cleanup.policy=compact`, Kafka performs key-based log compaction. Within a partition, multiple records sharing the same key can be written over time; compaction retains the latest value per key and cleans up older versions once eligible. This suits maintaining changelogs or topics representing latest state, such as `customer-state` keyed by `customerId`.

Compaction does not instantaneously turn a topic into a table with strictly one record per key. Older records may remain in the log before the cleaner runs; a consumer reading from the beginning can still observe multiple versions of a key. Consumers must understand that compacted data is a stream of state changes and apply records in partition order.

To delete a key from compacted state, the producer sends a **tombstone**: a record with the target key and a `null` value. Tombstones are retained for `delete.retention.ms` so consumers have an opportunity to observe the deletion marker before the tombstone is cleaned up. The default is typically 24 hours. If a consumer replays too slowly and the tombstone has already been purged, it may not realize that key was ever deleted.

### Combining `compact,delete`

`cleanup.policy=compact,delete` lets Kafka both compact data by key and delete old segments under retention limits. This combination is useful when a topic needs latest state per key while still bounding data age.

Do not default to `compact` for every topic. When the requirement is preserving full event history for a period, `delete` is usually more appropriate. When the requirement is restoring latest state per key, `compact` can fit better. Choose the policy based on how consumers use the data.

## 5. Configuring retention on brokers and topics

Kafka has broker-level defaults. For example, `log.retention.hours` typically defaults to seven days and applies whenever a topic does not override the corresponding policy. A topic can set its own `retention.ms` or `retention.bytes` to use a different retention window from the global default.

Use topic-level settings when different data streams have different retention requirements. For instance, technical events might only need three days, whereas business events need 30 days for reconciliation. Avoid raising broker-wide retention just to satisfy one topic if doing so unexpectedly inflates storage for all other topics.

Example topic configuration via Spring Kafka:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic orderEventsTopic() {
        return TopicBuilder.name("orders.events")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_DELETE)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .config(TopicConfig.RETENTION_BYTES_CONFIG, "10737418240")
                .build();
    }
}
```

When the Spring Boot application starts, `KafkaAdmin` can use the `NewTopic` bean to create the topic if it does not already exist. The example above configures six partitions, a replication factor of three, seven-day retention, and a 10 GiB limit per partition. The cluster must have enough brokers to satisfy the declared replication factor.

A `NewTopic` bean primarily describes a topic to be created. If the topic already exists, changing values in code should not be taken as proof that the live configuration on the broker was updated. For existing topics, use the Kafka Admin API or Kafka administration tools to alter configurations and verify actual state.

Connection properties like `spring.kafka.bootstrap-servers` can live in `application.yml`, yet retention is a topic/broker setting—not a property controlling how long a single `KafkaTemplate.send` call or `@KafkaListener` method keeps data.

## 6. How does retention affect consumers?

A consumer group stores offsets to record reading positions per partition. Offsets record how far the consumer has progressed; they do not keep records alive past the topic's retention.

Suppose consumer group `billing-service` stops running for ten days while the topic retains data for only seven days. When the consumer resumes, part of the unread data may have already been deleted. The consumer can encounter an out-of-range offset (`OffsetOutOfRange`). Subsequent behavior depends on configuration and error handling, but data purged by retention cannot be recovered by Kafka simply by resetting offsets to the beginning.

`auto.offset.reset` is frequently misunderstood in this scenario:

- `earliest`: when no valid offset exists, start from the earliest record still present in the partition.
- `latest`: when no valid offset exists, start at the end of the log and receive only new data.
- `none`: raise an error if no valid offset is found.

`earliest` does not restore deleted data. It only positions the consumer at the start of the data that remains stored. Therefore, choose retention based on the maximum outage a consumer might endure, plus the time needed to catch up on the backlog after recovery.

Topic retention also differs from how long Kafka retains consumer group offsets. Offsets are stored in the internal `__consumer_offsets` topic and follow a separate broker expiration policy. Expiring a group's offsets does not delete events from the topic; conversely, events expired by retention do not immediately delete the group's offsets.

## 7. Estimating storage and choosing retention duration

An initial estimate multiplies average data rate by desired retention duration:

```text
Approximate logical storage  = write rate per second x retention seconds
Approximate physical storage = logical storage x replication factor
```

For example, a topic receiving an average of 2 MiB/s with seven-day retention:

```text
2 MiB/s x 604800 s = 1,209,600 MiB
                   ≈ 1,181 GiB
                   ≈ 1.15 TiB logical storage
```

With a replication factor of three, cluster-wide storage could be around 3.45 TiB before overhead and headroom. This is a rough estimate; real capacity planning must account for peak throughput, record size, compression, partition skew, growth rate, segments/indexes, and free disk headroom required for safe broker operation.

When choosing retention, answer these questions:

1. What is the longest downtime a consumer might experience?
2. After coming back online, how long will it take to drain the backlog?
3. Are there business, audit, or reconciliation rules governing data retention time?
4. What are the topic's average and peak write rates?
5. How many partitions and what replication factor does the topic have?
6. Is full history needed, or only the latest state per key?

If retention is too short, slow consumers may miss their chance to read data. If retention is too long, disk cost and recovery time can grow. Size limits must also be large enough not to evict data earlier than the desired business window.

## 8. Monitoring and testing retention

In production operations, monitor broker log disk usage, per-partition size, disk utilization, write rates, and consumer lag. Continuously rising consumer lag can indicate processing cannot keep up with ingestion; if lag approaches the retention boundary, intervene before unread data gets purged.

When investigating a topic, inspect actual broker configurations rather than reading only application config files. Check `cleanup.policy`, `retention.ms`, `retention.bytes`, `segment.ms`, `segment.bytes`, and broker retention defaults. A live topic's configuration can differ from what a newer application deployment declares.

Integration tests can use Kafka Testcontainers or a test broker to verify topics are created with expected configs. You can use `AdminClient` to describe topic configs and assert expected values. Testing segment deletion due to retention must account for segment rolling time and cleanup intervals; never assume a record disappears at the exact instant `retention.ms` elapses.

For compacted topics, explicitly test same-key updates and tombstones. Consumers rebuilding state must read the needed records and understand that compaction can eliminate intermediate versions.

## 9. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| Kafka deletes records once a consumer reads them | Records are kept according to the topic's cleanup policy and retention |
| `retention.bytes` is a topic-wide limit | It is a per-partition limit |
| `retention.ms` deletes each record at exact expiration | Kafka cleans up by segment and cleanup check intervals |
| `auto.offset.reset=earliest` recovers all old data | It only reads from the earliest data still retained |
| Compacted topics keep full history | Compaction keeps the latest state per key after the cleaner runs |
| Increasing topic retention extends consumer group offset retention | Events and group offsets have separate retention policies |

## 10. Conclusion

Retention determines how long or up to what size limit Kafka preserves data. With `cleanup.policy=delete`, the two key settings are `retention.ms` and `retention.bytes`; with `compact`, Kafka removes older versions per key and uses tombstones to represent key deletions.

Kafka performs cleanup by segment, so actual deletion timing may lag behind configured thresholds. Retention also defines the time limit within which a lagging consumer must catch up before unread data is evicted. When building Spring Kafka applications, configure retention at the broker or topic level, declare topics appropriately with `NewTopic` when needed, verify live broker configurations, and monitor consumer lag alongside disk capacity.

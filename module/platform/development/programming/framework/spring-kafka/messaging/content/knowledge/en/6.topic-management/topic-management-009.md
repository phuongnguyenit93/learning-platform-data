# Inspecting Topic Metadata

Kafka stores metadata to describe topic structure and partition distribution state across brokers. When operating a Spring Kafka flow, metadata tells you whether a topic exists, how many partitions it has, which broker is leader for each partition, which replicas are in sync, and which configurations the topic uses. Inspecting metadata helps detect misconfigurations, missing replicas, leaderless partitions, or environment discrepancies before those issues impact producers and consumers.

Metadata does not contain record payloads. It describes how Kafka organizes and serves the log. To inspect actual data, use a consumer or a record-reading tool; to inspect topic structure and state, use the Kafka Admin API or administrative commands.

## 1. What Does Topic Metadata Include?

When describing a topic, the key details to observe include:

| Attribute | Meaning |
|---|---|
| Topic name | Topic name used by producers and consumers |
| Topic ID | Internal identifier of the topic within the cluster; does not replace the topic name in application config |
| Internal topic | Indicates whether the topic is an internal topic used by Kafka |
| Partition count | Current number of partitions in the topic |
| Replication factor | Number of replicas assigned per partition under the current configuration |
| Partition leader | Broker currently handling read/write requests for the partition |
| Replicas | List of brokers assigned a copy of the partition |
| ISR | In-Sync Replicas, the replicas currently keeping up with the leader per Kafka's criteria |
| Offline replicas | Replicas currently unavailable |
| Topic configs | Settings applied at the topic level, such as retention, cleanup policy, and record size limits |

A topic can have multiple partitions, each with its own leader. Example of an `orders` topic with 3 partitions and a replication factor of 3:

```text
Topic: orders
Partition 0: Leader 1, Replicas 1,2,3, ISR 1,2,3
Partition 1: Leader 2, Replicas 2,3,1, ISR 2,3,1
Partition 2: Leader 3, Replicas 3,1,2, ISR 3,1,2
```

In this example, each partition has one leader and two follower replicas. Partition 0's leader is broker 1, while partitions 1 and 2 have leaders on brokers 2 and 3, respectively. All brokers are in the ISR, so at the time of inspection the replicas are in sync.

## 2. Distinguishing Replicas, Leader, and ISR

When reading metadata, understand the relationship among these three lists:

- **Replicas:** all brokers assigned to store a copy of the partition, including both leader and followers.
- **Leader:** one broker from the replicas list responsible for handling read/write requests for the partition.
- **ISR:** the subset of replicas meeting synchronization conditions with the leader. Normally the leader also belongs to the ISR.

Example:

| Partition | Replicas | Leader | ISR | Observation |
|---|---|---:|---|---|
| 0 | 1, 2, 3 | 1 | 1, 2, 3 | All replicas are in sync |
| 1 | 2, 3, 1 | 2 | 2, 3 | Broker 1 is lagging or no longer in the ISR |
| 2 | 3, 1, 2 | - | - | No leader available at the time of inspection |

When ISR has fewer entries than replicas, the partition is under-replicated. If the leader fails, Kafka must elect a new leader from eligible replicas. When no eligible replica remains to serve as leader, the partition may enter an unavailable state until an eligible replica recovers or an operator intervenes.

The replication factor is the number of assigned copies, not the number of currently healthy copies. Compare `Replicas`, `Isr`, and `OfflineReplicas` rather than looking solely at the replication factor.

`min.insync.replicas` is a different configuration from the replication factor. It sets the minimum ISR threshold for certain write operations using `acks=all` to be accepted. For instance, a replication factor of 3 and `min.insync.replicas=2` allow writes while at least two replicas remain in the ISR; if ISR drops to 1, producers may receive `NotEnoughReplicas` or related errors. This setting does not create extra replicas and does not guarantee all replicas stay healthy.

## 3. Viewing Metadata with Kafka CLI

### Listing Topics

Use `kafka-topics.sh` to list topics that the current principal has permission to view:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
```

The output confirms topic names, though it does not show partition and replica states. The list may include internal topics such as `__consumer_offsets` depending on permissions and tool behavior.

### Describing a Topic

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Typical output looks like:

```text
Topic: orders  TopicId: ...  PartitionCount: 3  ReplicationFactor: 3
  Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
  Topic: orders  Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3
  Topic: orders  Partition: 2  Leader: 3  Replicas: 3,1,2  Isr: 3,1,2
```

Column names and formatting may vary by Kafka version. How to interpret key fields:

| Field | Interpretation |
|---|---|
| PartitionCount | Total number of partitions in the topic |
| ReplicationFactor | Number of replicas assigned per partition in the summary line |
| Partition | Partition index |
| Leader | Broker ID currently acting as leader; `-1` indicates no leader |
| Replicas | Broker IDs assigned replicas |
| Isr | Broker IDs currently in the ISR |

To describe all topics, omit the `--topic` option:

```bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe
```

### Filtering Problematic Partitions

Some Kafka CLI versions support filtering under-replicated or unavailable partitions:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --under-replicated-partitions

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --unavailable-partitions
```

The first command finds partitions whose ISR count is less than their assigned replicas. The second finds partitions without an available leader. Depending on Kafka version, option names or filtering behavior may differ; check `kafka-topics.sh --help` on the exact toolset deployed.

## 4. Inspecting Topic-Level Configurations

Partition and replica metadata does not replace checking topic configs. Common configs to review:

| Config | Meaning |
|---|---|
| `cleanup.policy` | Data cleanup mode: `delete`, `compact`, or combined depending on version |
| `retention.ms` | Data retention duration under the retention policy |
| `retention.bytes` | Log size limit per partition |
| `segment.bytes` | Target log segment size |
| `max.message.bytes` | Topic-level limit on record batch size |
| `min.insync.replicas` | Minimum replicas in ISR for `acks=all` writes |
| `message.timestamp.type` | Selects producer-supplied or broker-assigned timestamp |

Use `kafka-configs.sh` to describe topic configs:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

This command normally displays configs explicitly overridden at the topic level. To also inspect defaults and config sources, use `--all` if your Kafka CLI version supports it:

```bash
kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe \
  --all
```

When inspecting, distinguish topic-level overrides from values inherited from the broker or Kafka defaults. Not seeing a key in the overrides list does not mean Kafka has no effective value for that key.

Some configs are read-only, some can be changed dynamically, and some depend on the broker version. Before altering a config, verify its source, dynamic update support, and impact on retention, storage, or write availability.

## 5. Inspecting Metadata with AdminClient

Kafka provides `AdminClient` for querying metadata and administering resources. You can use `describeTopics()` to read topic descriptions from Java:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.common.TopicPartitionInfo;

public class TopicMetadataReader {

    public void describe(AdminClient adminClient) throws Exception {
        Map<String, TopicDescription> topics = adminClient
                .describeTopics(List.of("orders"))
                .allTopicNames()
                .get(10, TimeUnit.SECONDS);

        TopicDescription description = topics.get("orders");
        if (description == null) {
            throw new IllegalStateException("Topic orders was not returned");
        }

        System.out.printf(
                "name=%s, topicId=%s, internal=%s%n",
                description.name(),
                description.topicId(),
                description.isInternal()
        );

        for (TopicPartitionInfo partition : description.partitions()) {
            String leader = partition.leader() == null
                    ? "none"
                    : Integer.toString(partition.leader().id());

            System.out.printf(
                    "partition=%d, leader=%s, replicas=%s, isr=%s, offline=%s%n",
                    partition.partition(),
                    leader,
                    partition.replicas(),
                    partition.isr(),
                    partition.offlineReplicas()
            );
        }
    }
}
```

`describeTopics()` returns topic metadata, including topic ID, internal flag, and partition list. Each `TopicPartitionInfo` provides the partition number, leader, replicas, ISR, and offline replicas. Leader can be `null` when a partition has no available leader, so code should check before accessing the broker ID.

`AdminClient` is an asynchronous client. Its methods return result objects containing `KafkaFuture`; the example above waits up to 10 seconds via `get(timeout, unit)`. In real applications, handle timeouts, authorization errors, non-existent topics, and broker connection failures. Do not block indefinitely on a business API request thread.

### Creating an AdminClient in Spring Kafka

If Spring Boot has already configured `KafkaAdmin`, you can reuse its connection properties to create an `AdminClient`:

```java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
class KafkaAdminClientConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient topicAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}
```

The bean is closed by Spring when the context stops via `destroyMethod = "close"`. If the application connects to multiple clusters, create the `AdminClient` from the corresponding cluster's configuration and assign explicit qualifiers to avoid querying the wrong environment.

In a simple application, `KafkaAdmin` and `NewTopic` beans suffice for declaring topics at startup. Only create a dedicated `AdminClient` when you need to read metadata, inspect configs, or perform administrative operations in business or operational flows.

## 6. Reading Topic Configs with AdminClient

Partition metadata and topic config are two separate queries. You can use `describeConfigs()` to read topic configurations:

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.Config;
import org.apache.kafka.common.config.ConfigResource;

public class TopicConfigReader {

    public void describe(AdminClient adminClient) throws Exception {
        ConfigResource topic = new ConfigResource(
                ConfigResource.Type.TOPIC,
                "orders"
        );

        Map<ConfigResource, Config> configs = adminClient
                .describeConfigs(List.of(topic))
                .all()
                .get(10, TimeUnit.SECONDS);

        Config config = configs.get(topic);
        for (Config.Entry entry : config.entries()) {
            System.out.printf(
                    "name=%s, source=%s, sensitive=%s, value=%s%n",
                    entry.name(),
                    entry.source(),
                    entry.isSensitive(),
                    entry.isSensitive() ? "<hidden>" : entry.value()
            );
        }
    }
}
```

`Config.Entry` reports the name, config source, sensitive/read-only flags, and value if display is permitted. Some sensitive values may be masked; do not log them. The config source distinguishes topic-level overrides from broker-inherited or default configs.

When comparing two environments, retrieve both topic descriptions and topic configs. Two topics with the same name and partition count can still behave differently operationally if their retention or replication assignment differs.

## 7. Declaring Topics with Spring Kafka

Spring Kafka provides `KafkaAdmin` and `NewTopic` to declare topics as beans. When `KafkaAdmin` is active in the application context, it uses the broker admin API to create topics at startup:

```java
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.KafkaAdmin;

@Configuration
class TopicConfiguration {

    @Bean
    KafkaAdmin.NewTopics applicationTopics() {
        return new KafkaAdmin.NewTopics(
                TopicBuilder.name("orders")
                        .partitions(6)
                        .replicas(3)
                        .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                        .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
                        .build(),
                TopicBuilder.name("orders-dlt")
                        .partitions(6)
                        .replicas(3)
                        .build()
        );
    }
}
```

`NewTopics` groups multiple topic declarations into a single bean. `TopicBuilder` helps express partition count, replication factor, and topic configs directly in source code. The example values assume the cluster has enough brokers to satisfy a replication factor of 3.

Declaring `NewTopic` expresses desired configuration when creating topics. For existing topics, keep the actual behavior clear:

- Spring Kafka may increase partition counts when an existing topic has fewer partitions than declared, depending on broker capability and framework version.
- Kafka does not support reducing partitions through standard alter-partition operations.
- Do not assume that editing configs in a `NewTopic` bean automatically updates all topic configs of an existing topic. Use `AdminClient.incrementalAlterConfigs()` or `kafka-configs.sh --alter` for intentional config changes.
- If the cluster provisions topics via dedicated tooling, avoid having multiple systems modify the same topic without clear ownership rules.

## 8. Verifying Topics Before Application Use

A basic verification workflow for the `orders` topic can proceed in order:

1. Confirm the topic appears in the list with `kafka-topics.sh --list`.
2. Describe the topic to check partition count, replication factor, leader, replicas, and ISR.
3. Check topic configs such as retention, cleanup policy, and `min.insync.replicas`.
4. Check for unavailable and under-replicated partitions.
5. Compare metadata against requirements of producers, consumers, and the deployment environment.

Example checklist:

| Item | Illustrative Expectation | Signs to Investigate |
|---|---|---|
| Topic exists | `orders` appears | Topic missing or misspelled name |
| Partition count | 6 | Insufficient expected parallelism or mismatch across environments |
| Replication factor | 3 | Lower than the system's durability standard |
| Leader | Every partition has a broker leader | Leader is `-1` or missing |
| ISR | ISR equals replicas under healthy conditions | Prolonged ISR shrinkage |
| Offline replicas | None | Replica broker offline |
| Retention | Matches business retention period | Retention too short or too long |
| Cleanup policy | Matches data type | Misuse of `compact`/`delete` |
| `min.insync.replicas` | Matches replication factor and `acks` | Value causes producer write failures or weaker durability than intended |

The values in the table are examples, not universal defaults for every topic. Determine goals for throughput, durability, retention, and storage cost before picking parameters.

## 9. Common Misinterpretations When Reading Metadata

| Symptom | Correct Interpretation | Troubleshooting Direction |
|---|---|---|
| Topic exists yet producer cannot write | Existing metadata does not prove the producer has write permissions or an available leader | Check ACLs, leader, broker logs, and producer errors |
| Replication factor is 3 but ISR has only 2 | One replica is lagging, disconnected, or ineligible for the ISR | Check brokers, network, log replication, and under-replicated duration |
| Partition shows leader `-1` | No leader available at query time | Check brokers and replicas; identify why leadership was lost |
| Topic config does not list every key | CLI may only list overrides; other values are inherited | Use `--all` if supported and inspect config source |
| Client view differs from CLI just run | Client may be using cached metadata or connecting to another cluster | Verify bootstrap servers, cluster identity, and refresh timing |
| Partition count is right yet consumer throughput stays low | Consumer count, partition assignment, and processing speed still limit parallelism | Check consumer group and per-partition lag |
| Topic already exists yet `NewTopic` bean remains | Bean declares desired state; behavior on existing topics is limited | Check partition count and use dedicated alter-config APIs when needed |

Metadata is managed by brokers, and clients typically cache it to reduce requests. After modifying a topic or broker, observations from a client may not reflect the new state immediately. When comparing, record the cluster, query timestamp, and use the same bootstrap endpoint to avoid false conclusions.

## 10. Permissions and Safety During Inspection

Metadata commands and Admin API calls require appropriate permissions. Depending on security configuration, a principal may need permissions to describe topics, describe configs, or administer the cluster. If you encounter `TopicAuthorizationException`, `ClusterAuthorizationException`, or similar errors, inspect the principal's ACLs rather than assuming the topic does not exist.

Do not grant full admin accounts to applications that only need to read metadata. Separate permissions by purpose:

- Runtime applications typically only need describe permissions plus read/write access on specific topics and groups.
- Monitoring tools need read access to metadata and configs within an authorized scope.
- Provisioning pipelines need permissions to create topics, add partitions, or alter configs per policy.

`--alter` operations, changing replica assignments, or changing retention can have major impacts on data and cluster load. When you only need to inspect, use read-only commands like `--list`, `--describe`, and `--describe` configs. Before making changes, confirm the right cluster, topic, and rollback plan.

## 11. Topic Metadata Operations Checklist

1. Confirm the correct bootstrap server and cluster before querying.
2. Check topic name, topic ID, and internal flag when distinguishing application topics from internal topics.
3. Verify partition count and replication factor against design requirements.
4. Compare leader, replicas, ISR, and offline replicas for every partition.
5. Read topic configs and distinguish overrides from inherited values.
6. Cross-check `min.insync.replicas` with replication factor and producer `acks`.
7. Use `AdminClient` or `KafkaAdmin` in Spring Kafka for automated checks with explicit timeouts and error handling.
8. Grant least-privilege metadata permissions to applications and monitoring tools.
9. Record the cluster and timestamp when saving inspection outputs to compare across deployments.

Metadata is a snapshot of a topic's structure and distribution state at a point in time. By accurately reading partitions, leaders, replicas, ISRs, and config sources, development teams can catch misconfigurations or broker issues early and make informed decisions before event flows are disrupted.

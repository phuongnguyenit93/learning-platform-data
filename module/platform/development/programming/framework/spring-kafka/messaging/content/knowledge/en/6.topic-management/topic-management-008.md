# Creating Topics with Kafka Tools

A topic is where Kafka stores event records. Before producers send data and consumers read data, the topic needs to exist with an appropriate partition count, replication factor, and storage policy. Kafka provides command-line tools to create, list, inspect, alter configurations, and delete topics. Spring Kafka can also declare topics using `KafkaAdmin` and `NewTopic` when the application starts.

This lesson uses the Kafka CLI with `--bootstrap-server` connectivity, an approach suitable for both KRaft clusters and modern Kafka clusters. Examples use `localhost:9092`; replace it with the bootstrap address of your target environment. Commands ending in `.sh` are for Linux/macOS. On Windows, use the corresponding scripts in `bin\windows` ending in `.bat`.

## 1. Preparing Tools and Connecting to the Cluster

Kafka ships administrative scripts in the `bin` directory of the installation. Common scripts include:

| Tool | Purpose |
|---|---|
| `kafka-topics.sh` | Create, list, describe, increase partitions, and delete topics |
| `kafka-configs.sh` | View and alter configurations of topics or brokers |
| `kafka-reassign-partitions.sh` | Plan and execute replica reassignment across brokers |
| `kafka-consumer-groups.sh` | Inspect consumer groups and offsets, useful when verifying read flows |

Before running commands, know a reachable bootstrap server address. Example for a local cluster:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

On Windows PowerShell or Command Prompt, the corresponding command is:

```powershell
bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --list
```

If Kafka runs inside Docker, you can run scripts from the Kafka container or use the port published to the host machine. `localhost:9092` is only valid when the broker is actually listening at that address from where you execute the command. In secured environments, pass a client config file using `--command-config`, for example:

```bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config config/admin-client.properties \
  --list
```

The `admin-client.properties` file holds connection and authentication properties needed by the Kafka client, such as TLS or SASL settings. Keep this file in a protected location and avoid placing passwords, tokens, or private keys directly in commands saved in terminal history or shared documentation.

Prefer `--bootstrap-server` for administrative operations. Older guides may use `--zookeeper`; that connection method belongs to the legacy ZooKeeper architecture and is not an option for KRaft clusters.

## 2. Creating a Topic

A basic topic creation command requires the topic name, partition count, and replication factor:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
```

Meaning of the flags:

- `--create`: instructs Kafka to create a topic.
- `--topic orders`: name of the topic to create.
- `--partitions 6`: creates six partitions, numbered from 0 to 5.
- `--replication-factor 3`: each partition has three replicas across different brokers if the cluster has enough eligible brokers.

The replication factor is the number of copies of each partition, not the number of copies of the topic as a whole. With a replication factor of 3, a partition has one leader replica and up to two follower replicas. Producers and consumers typically communicate with the leader; followers replicate data to improve fault tolerance.

A cluster needs at least three brokers eligible to host replicas to create a topic with a replication factor of 3. If you only have a single local broker, use `--replication-factor 1`. Do not use a replication factor of 1 for important production topics just because the command succeeded on a local machine.

To make deployment scripts idempotent across repeated runs, use `--if-not-exists`:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --if-not-exists \
  --topic orders \
  --partitions 6 \
  --replication-factor 3
```

This option avoids failing solely because the topic already exists. It does not automatically verify that an existing topic matches the desired partition count, replication factor, or configuration; run a verification step after creation.

## 3. Listing and Describing Topics

List topics that the current account is authorized to view:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

View details of a specific topic:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

The output typically displays total partitions, replication factor, topic configurations, and per-partition details. A partition line contains important fields:

```text
Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
```

- `Partition`: partition number.
- `Leader`: broker currently serving as leader for the partition; `-1` indicates no leader is currently elected.
- `Replicas`: brokers assigned to hold replicas.
- `Isr`: set of replicas currently in sync (in-sync replicas) with the leader.

If a broker is down, the number of replicas in the ISR may be lower than the assigned replicas. Check ISR and broker health before concluding a topic is ready to tolerate faults. You can describe partitions missing synchronized replicas using:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --under-replicated-partitions
```

This command identifies partitions whose ISR count is below their assigned replica count. In operations, combine the output with broker logs and network/disk health checks to find the root cause.

## 4. Choosing Partitions and Replication Factor

Partitions determine the parallelism and ordering scope of a topic. Records within the same partition are read in offset order. Kafka does not guarantee global ordering across multiple partitions. When a producer sends keyed records, the partitioner typically uses the key to select a partition, routing records with the same key to the same partition as long as the partition count remains unchanged.

Several guidelines when choosing the partition count:

1. Estimate target throughput and the parallel processing capacity of consumer groups.
2. Consider expected consumer instances. Within a consumer group, a partition is assigned to at most one consumer at a time; consumers exceeding the partition count will sit idle.
3. Account for storage capacity, log segment file counts, recovery overhead, and rebalance duration. Too many partitions also increase broker management overhead.
4. Consider per-key ordering. If business logic requires events for the same entity to be processed in order, producers must send the same key and partition design must stay stable.

Replication factor determines data redundancy. With a replication factor of 3 and `min.insync.replicas=2`, a producer using `acks=all` is only acknowledged when at least two replicas are in the ISR. This configuration balances fault tolerance and write availability; if the ISR falls below the threshold, producers may receive errors rather than writing to too few replicas. Choose values based on broker count, data durability requirements, and tolerance for write interruptions.

Example creating a production topic with three replicas and six partitions:

```bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.net:9092 \
  --create \
  --topic payments.events.v1 \
  --partitions 6 \
  --replication-factor 3
```

This is merely a syntax example. The right partition count still depends on throughput, broker count, record size, consumer count, and system SLAs.

## 5. Viewing and Modifying Topic Configurations

Topics have configurations affecting storage and resilience. Some common configurations:

| Configuration | Meaning |
|---|---|
| `retention.ms` | Duration data is retained before segments become eligible for deletion by retention |
| `retention.bytes` | Storage limit per partition before older data becomes eligible for removal |
| `cleanup.policy` | Data cleanup policy, typically `delete` or `compact` |
| `min.insync.replicas` | Minimum replicas in the ISR required for certain write modes like `acks=all` to succeed |
| `segment.bytes` | Target size of a single log segment |

View topic configuration:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

Set retention to seven days and require at least two synchronized replicas:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=604800000,min.insync.replicas=2
```

`604800000` milliseconds equals seven days. `min.insync.replicas=2` must be coordinated with the replication factor and producer `acks`; setting a threshold higher than the replicas sustainable in the ISR will cause writes to be rejected.

To switch a topic to compaction:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name customer-state \
  --alter \
  --add-config cleanup.policy=compact
```

`delete` keeps logs for the retention window and then removes old segments. `compact` retains the latest value per key via background compaction; tombstones can mark deleted keys. Compaction does not mean only one record per key exists immediately, as uncompacted segments can still contain older records.

Delete an override so the topic reverts to the inherited default value:

```bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --delete-config retention.ms
```

After making changes, re-run `--describe` to verify the effective configuration. Default values may come from broker configuration and the Kafka version; do not assume a specific value without inspecting the cluster.

## 6. Increasing Partition Count

Kafka lets you increase a topic's partition count:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders \
  --partitions 9
```

The command above increases the topic from six to nine partitions. Partition count can only be increased this way; it cannot be decreased via `kafka-topics --alter`. Decreasing partitions normally requires creating a new topic with the desired structure and migrating data under a separate plan.

Increasing partitions has a major consequence for keyed records: the partitioner may map the same key to a new partition after the partition count changes. Old records remain in old partitions while new records may go to different partitions. As a result, processing order for a key across the transition point may no longer hold as before. Evaluate ordering requirements, consumer groups, and migration procedures before increasing partitions on an active topic.

The increase-partitions command does not alter the replication factor. Changing replica placement or replication factor requires a reassignment workflow using `kafka-reassign-partitions.sh`, accompanied by a plan for network load, disk capacity, and ISR health. Do not edit broker metadata directly to move replicas.

## 7. Deleting a Topic

When a topic is no longer used and its data can be discarded, the delete command is:

```bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --delete \
  --topic orders-test
```

Deleting a topic is a destructive operation. Deletion may proceed asynchronously depending on cluster state and broker configuration; the command returning does not mean all data files have disappeared immediately. Deletion permissions also depend on ACLs and cluster topic-deletion settings. Afterward, you can use `--list` or `--describe` to check status.

Before deleting a production topic, confirm producers have stopped writing, dependent consumers and applications have migrated off, data has no remaining retention obligations, and necessary operational approvals are in place. Do not use the delete command to fix a topic suffering from replica errors or consumer lag; investigate the root cause first.

## 8. Creating Topics from a Spring Kafka Application

When you want to manage topics alongside application configuration, Spring Kafka supports declaring `NewTopic` beans. `KafkaAdmin` uses `AdminClient` to create topics at application startup if they do not exist yet. Example:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
public class KafkaTopicConfiguration {

    @Bean
    public NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .build();
    }
}
```

The application needs bootstrap servers configured, for example:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
```

Spring Boot typically auto-configures `KafkaAdmin` when Spring Kafka is on the classpath and valid bootstrap servers are provided. When using a single local broker, set `.replicas(1)`; `.replicas(3)` in the example requires a cluster with enough brokers to hold replicas.

Declaring `NewTopic` makes startup topic creation repeatable and keeps desired configuration next to source code. However, do not treat this bean as a general-purpose migration tool for existing topics. Once a topic exists, verify its actual state via Kafka CLI or `AdminClient` and apply changes intentionally. In particular, decreasing partitions is unsupported and increasing partitions can affect per-key ordering.

In production, operations teams may manage topics through deployment pipelines or centralized governance tools; applications should only create topics themselves if that is an agreed convention. Enabling broker auto-create topics can lead to topics being created with unintended default partition counts or replication factors. Explicitly declaring topics provides much better control over these parameters.

## 9. Complete Topic Creation and Verification Workflow

A practical workflow can include the following steps:

1. Define the topic name by domain and event type, e.g. `orders.created.v1`.
2. Choose the partition count based on throughput, expected consumer count, and per-key ordering requirements.
3. Choose the replication factor based on broker count and fault-tolerance needs.
4. Create the topic using `kafka-topics` or declare `NewTopic` per your team's deployment workflow.
5. Set retention, cleanup policy, and `min.insync.replicas` via `kafka-configs` if needed.
6. Run `--describe` to verify partitions, leaders, replicas, and ISR.
7. Send a test record, read it with a test consumer group, and monitor logs/metrics before routing live traffic.

Example verification command suite after creating a topic:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders

bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
```

If a partition has no leader or the ISR is lower than expected, resolve the broker issue before enabling producers. If partition counts or configs do not match, adjust them using a change procedure whose impact has been evaluated. Successful topic creation only confirms metadata was accepted; it does not prove producers, consumers, access permissions, and storage policies are all working properly.

## 10. Common Errors

| Symptom | Common Cause and Troubleshooting Direction |
|---|---|
| `TopicExistsException` | Topic already exists; use `--if-not-exists` for repeatable creation commands, then `--describe` to verify actual configuration |
| `InvalidReplicationFactorException` | Replication factor exceeds brokers eligible to host replicas; inspect cluster and choose an appropriate value |
| `InvalidPartitionsException` | Invalid partition count or alter command does not increase partition count; check current and requested values |
| `TopicAuthorizationException` | Account lacks ACLs for the topic operation; ask an administrator to grant required permissions |
| `TimeoutException` or connection failure | Wrong bootstrap server, unreachable listener/port, DNS, or TLS/SASL misconfiguration; test from the exact host/container running the CLI |
| No leader or ISR missing replicas | Broker down, replica lagging, or network/disk issues; check broker logs and replica status |
| Topic created with unexpected config | Topic may have been auto-created or pre-created by another pipeline; inspect `--describe` and broker settings |

## Checklist

- Connected to the intended cluster using `--bootstrap-server` with an account holding required permissions.
- Topic name, partition count, and replication factor determined according to application needs.
- Replication factor does not exceed brokers eligible to host replicas.
- Retention, cleanup policy, and `min.insync.replicas` fit data requirements.
- `--describe` shows leaders, replicas, and ISR in the expected state.
- Impact of increasing partitions on per-key ordering has been reviewed.
- Topic alter or delete commands verified for the target environment and exact topic name.

The Kafka CLI offers a direct way to manage the topic lifecycle; Spring Kafka complements this by letting applications declare topics alongside code through `KafkaAdmin` and `NewTopic`. Whichever method you use, verify metadata and replica state after operations to ensure topics are ready for messaging flows.

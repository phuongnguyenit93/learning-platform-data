# Configuring Topics and Partitions in Spring Kafka

A Spring Kafka system may run smoothly when it has a single consumer and a few thousand events per day, yet fail as traffic grows: one partition overloads, consumers sit idle, data is lost during broker outages, or newly created topics receive default settings that violate SLAs. These problems usually originate in **topic and partition design and configuration**, not in `@KafkaListener` business logic.

This lesson belongs to **Spring Kafka Reliability Operations → Deployment and Configuration**, guiding how to choose partition counts, replication factors, minimum in-sync replicas, retention, key-based message routing, Spring Boot/Spring Kafka configuration, safe change rollouts, testing, and topic observability in operations. Examples use **Java 17, Spring Boot 3.x, Spring Kafka 3.x, and Apache Kafka**, with CLI commands on a Linux-style environment. Selected numbers are **illustrative examples**, not standard parameters for every cluster.

## 1. Understanding Topics, Partitions, Replicas, and Consumer Groups

A **topic** is a named event stream, such as `orders.events.v1`. Each topic consists of one or more **partitions**; each partition is an append-only log with its own offset sequence. A partition has one **leader replica** and may have **follower replicas** on other brokers for fault tolerance.

```text
Topic: orders.events.v1

                    Kafka cluster
    +--------------------+--------------------+--------------------+
    | Broker 1           | Broker 2           | Broker 3           |
    |                    |                    |                    |
    | P0 leader          | P0 follower        | P0 follower        |
    | P1 follower        | P1 leader          | P1 follower        |
    | P2 follower        | P2 follower        | P2 leader          |
    +--------------------+--------------------+--------------------+

    P0: offset 0 -> offset 1 -> offset 2 -> ...
    P1: offset 0 -> offset 1 -> offset 2 -> ...
    P2: offset 0 -> offset 1 -> offset 2 -> ...
```

In the diagram, the topic has 3 partitions and replication factor 3. Each partition has three copies across three brokers; at any time, only **one leader** serves normal reads and writes for that partition. Followers replicate data from the leader and can be elected leader via Kafka mechanisms if the leader becomes unavailable.

| Component | Role | Misconception to Avoid |
| --- | --- | --- |
| Topic | Data stream name | A topic is not a single globally ordered queue when it has multiple partitions |
| Partition | Unit of log storage, offset ordering, and load splitting | Multiple partitions do not automatically parallelize a single key |
| Offset | Record position **within one partition** | Offset 10 on P0 is not offset 10 on P1 |
| Leader replica | Primary replica serving a partition | Not every replica is an independent partition |
| Follower replica | Copy of a partition | Followers do not increase partition count to split consumer work |
| Replication factor (RF) | Total desired replicas per partition | RF=3 does not mean three business messages |
| ISR | Replicas keeping up with the leader per Kafka criteria | ISR can shrink during broker or network issues |
| Consumer group | Consumers coordinating partition sharing | Within a group, one partition is normally assigned to at most one consumer at a time |

### 1.1. At What Scope Is Ordering Guaranteed?

Kafka preserves write order **within each partition**. If events for the same order must be processed sequentially:

```text
ORDER_CREATED -> PAYMENT_AUTHORIZED -> ORDER_SHIPPED
```

use the **same stable business key**, such as `orderId`, so those events route to the same partition under the active partitioning strategy. There is no ordering guarantee across different partitions of a topic.

Note that final processing order also depends on concurrency and application logic. A listener that dispatches work onto an asynchronous thread pool can finish a later event before an earlier one, even when Kafka delivers records in offset order. **Partition order does not automatically guarantee the order of all downstream side effects.**

## 2. Questions to Answer Before Creating a Topic

Before choosing `partitions=6` and `replication-factor=3`, document the data and load contract:

1. **Event type:** entity events, business commands, audit logs, CDC, or latest state snapshots?
2. **Throughput:** average and peak messages/sec, message sizes, and consumer processing speed.
3. **Ordering key:** must order hold by `orderId`, `customerId`, `accountId`, tenant, or the entire topic?
4. **Concurrency:** how many messages/sec can one consumer handle, and how many consumer instances are planned?
5. **Retention:** retain history for 1 day, 7 days, 30 days, or only the latest value per key?
6. **Reliability:** how many broker failures must be tolerated, and can writes pause rather than risk data loss?
7. **Security:** who can create topics, produce, consume, read payloads, and view metadata?
8. **Scale/change:** are partition increases, key/schema changes, cluster migrations, or historical replays anticipated?

Example decision record:

```yaml
topic: orders.events.v1
purpose: Domain events for order lifecycle
key: orderId
partitions: 6
replicationFactor: 3
minInSyncReplicas: 2
cleanupPolicy: delete
retention: 7 days
producerAcks: all
consumerGroup: orders-worker
orderingScope: one orderId within one partition
```

This is a **decision specification**, not a config file Kafka parses directly. Translate the actual settings into provisioning tools, Spring Kafka `NewTopic`, CLI commands, or operator manifests.

## 3. Choosing Partition Count by Load and Concurrency

Partitions are a primary parallelism boundary for consumer groups. Suppose a topic has 3 partitions:

```text
Topic: orders.events.v1
    P0 ----> Consumer A
    P1 ----> Consumer B
    P2 ----> Consumer C

Consumer D: unassigned to any partition in the same group
```

If 4 consumers run in the same group against only 3 partitions, at most 3 consumers receive partitions at a time; the fourth sits idle for that topic. Conversely, a single consumer can handle **multiple partitions**.

### 3.1. Initial Estimation

Example:

| Parameter | Assumed Value |
| --- | ---: |
| Peak input | 9,000 messages/sec |
| Single consumer worker capacity | 2,000 messages/sec |
| Minimum workers by throughput | `ceil(9000/2000) = 5` |
| Planned partitions | 6 |
| Consumer application replicas | 3 |
| Concurrency per replica | 2 |

Six partitions allow up to six consumer threads to hold partition assignments, e.g., 3 replicas × 2 listener threads = 6 consumers in the group. However, this calculation is **only a starting point**, because throughput varies with message size, DB latency, batch size, GC, network, rebalances, and key distribution.

No simple formula guarantees `partitions = peak throughput / worker throughput` is optimal. Benchmark in a production-like environment with headroom for bursts and watch per-partition lag.

### 3.2. Do Not Pick Partition Counts Solely by Pod Count

Partition count lives at the topic level, whereas pod/consumer counts can autoscale up and down. For example:

```text
6 partitions, 2 pods × concurrency 2 = 4 consumers
-> each consumer can receive 1-2 partitions

6 partitions, 3 pods × concurrency 2 = 6 consumers
-> up to 6 consumers working

6 partitions, 5 pods × concurrency 2 = 10 consumers
-> some consumers receive no partition assignment
```

Adding pods improves throughput only if unassigned partitions remain, the database/API has spare capacity, and the bottleneck is not a single hot key.

### 3.3. Hot Partitions and Key Skew

If the key is `tenantId`, one tenant generating 80% of traffic can overload the partition holding that tenant while other partitions remain underutilized:

```text
Partition P0: 80% records  [HOT]
Partition P1:  8% records
Partition P2:  6% records
Partition P3:  6% records
```

Adding partitions does not split a **single key** across multiple partitions, because all events sharing that key are intentionally routed together for ordering. Trade-offs include:

- Using a higher-cardinality key if business logic does not need tenant-wide ordering.
- Splitting a tenant into sub-keys like `tenantId + accountId` if per-account ordering suffices.
- Dedicated topics or pipelines for hot sources when load isolation is needed.
- Optimizing consumer/DB processing rather than only adding partitions.

Never add a random salt to a business key if event ordering by the original key is required.

## 4. Replication Factor, ISR, and Fault Tolerance

Partition count governs load parallelism; **replication factor** governs how many replicas store each partition. They serve distinct goals.

Example with 3 brokers:

```text
Topic orders.events.v1
  partitions = 6
  replication.factor = 3
  min.insync.replicas = 2

Producer:
  acks = all
```

With this setup, the producer requests leader acknowledgment per `acks=all`, and Kafka accepts writes only when ISR meets `min.insync.replicas=2`. This increases the likelihood that acknowledged messages survive a broker failure, assuming replication, leader election, and infrastructure operate properly.

| Condition | Remaining ISR | `acks=all`, min ISR=2 | Meaning |
| --- | ---: | --- | --- |
| Three replicas synced | 3 | Writes can succeed | Meets threshold |
| One broker failed/slow | 2 | Writes can still succeed | Two copies remain in ISR |
| Two brokers failed/slow | 1 | Writes rejected or wait/fail on timeout | Prioritizes avoiding writes without enough replicas |
| Leader lost, ISR follower exists | Depends on live replicas | New leader can be elected | Availability depends on leader election |
| Broker failed with RF=1 | Potentially zero replicas | Partition may become unavailable | No backup replica exists |

### 4.1. `acks=all` and `min.insync.replicas` Must Work Together

- `acks=0`: producer does not wait for broker acknowledgment.
- `acks=1`: leader acknowledges after writing locally; acknowledged data can still be lost if the leader fails before followers replicate.
- `acks=all`: producer waits for acknowledgments per Kafka ISR requirements.
- `min.insync.replicas`: minimum in-sync replicas required to accept writes under `acks=all`.

RF=3 with `min.insync.replicas=1` does not provide the same write protection as RF=3/min ISR=2. Conversely, min ISR=3 requires all three replicas in ISR to write, so a single broker issue lowers write availability. This is a **durability vs. availability trade-off**, not "higher is always better."

Never set `replication.factor` higher than the number of available brokers eligible to host replicas under Kafka constraints. On a single-broker dev/test cluster, RF=3 cannot be provisioned as in a three-broker production cluster.

### 4.2. Never Enable Unclean Leader Election Casually

Allowing an **out-of-sync** replica to become leader when no eligible ISR exists risks losing data written to the old leader but not yet replicated to the new leader. In durability-sensitive systems, keep `unclean.leader.election.enable=false` unless you have explicitly analyzed the trade-offs and recovery policy.

Replication only protects against certain broker faults; it **does not replace backups, deletion controls, access control, or disaster recovery plans**. If an operator deletes a topic or sets retention too low, all three replicas lose the history together.

## 5. Creating Topics via Kafka CLI

In production, decide **who owns topic provisioning**: platform team, IaC/operator, deployment pipeline, or the application itself. For topics with reliability guarantees, centralized management and change review are generally safer than letting every service auto-create topics.

Assuming a cluster with at least three brokers, create a topic:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --create \
  --topic orders.events.v1 \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete
```

`604800000` milliseconds equals seven days. `bootstrap-server` can be a broker list matching cluster networking. On secured clusters, Admin CLI commands also need TLS/SASL settings, typically supplied via a restricted-permission client config file.

Inspect the topic after creation:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --describe \
  --topic orders.events.v1
```

Output shows partition count, replication factor, leader, replicas, and ISR:

```text
Topic: orders.events.v1
PartitionCount: 6
ReplicationFactor: 3
Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
...
```

This is **illustrative output**, not a fixed broker response. Actual leaders/replicas/ISRs depend on the cluster. In operations, check **every partition**, not just the first one.

View topic-level overrides:

```bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1:9092 \
  --entity-type topics \
  --entity-name orders.events.v1 \
  --describe
```

Some Kafka values inherit from broker defaults and do not appear as overrides in every view. To audit effective settings, use the Kafka Admin API or platform tooling and document inherited defaults.

### 5.1. `auto.create.topics.enable` Is Not Production Provisioning

Kafka brokers offer `auto.create.topics.enable`. When enabled, touching a non-existent topic can trigger topic creation with broker defaults under supported conditions. A single-character typo in a topic name can accidentally create an unwanted topic with wrong partition counts or RF.

In tightly managed clusters, it is usually best to:

- Provision topics explicitly via controlled tooling.
- Disable broker auto-topic creation where cluster policy allows.
- Restrict `CREATE`/`ALTER`/`DELETE` permissions via ACLs or RBAC.
- Verify topic existence and configuration before deploying producers/consumers.

Do not confuse **broker auto creation** with **Spring `KafkaAdmin` plus `NewTopic` beans**: they are separate resource creation paths that can be enabled or disabled independently.

## 6. Defining `NewTopic` in Spring Kafka

Spring Kafka offers `KafkaAdmin` and `NewTopic` to declare topics via Java configuration. A Spring Boot app usually auto-configures `KafkaAdmin` when using the Kafka starter with valid bootstrap servers.

Example for a **single-broker local/test environment**:

```java
package com.example.kafka.config;

import org.apache.kafka.common.config.TopicConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.kafka.config.TopicBuilder;
import org.apache.kafka.clients.admin.NewTopic;

@Configuration
public class LocalTopicConfiguration {

    @Bean
    @Profile({"local", "test"})
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events.v1")
                .partitions(3)
                .replicas(1)
                .config(TopicConfig.CLEANUP_POLICY_CONFIG,
                        TopicConfig.CLEANUP_POLICY_DELETE)
                .config(TopicConfig.RETENTION_MS_CONFIG, "86400000")
                .build();
    }
}
```

Locally, RF=1 because a single broker cannot hold three replicas. Never use this local setup to conclude that production RF=3 broker fault tolerance behaves as designed.

When `KafkaAdmin` runs at startup, it can use `NewTopic` beans to create topics as needed. **Do not treat the code above as a GitOps reconciler for all existing topic changes**: resource update behavior depends on Spring Kafka version and config type; certain changes cannot be applied simply by editing `NewTopic`.

### 6.1. Where Should Topics Be Managed?

| Management Approach | Suitable When | Controls Needed |
| --- | --- | --- |
| `NewTopic` + `KafkaAdmin` | Local, test, small services granted provisioning rights | Prevent unintended prod topic creation; startup permissions |
| Kafka CLI / `AdminClient` | Investigations or controlled changes | Command review, auditing, operator permissions |
| Terraform / platform IaC | Multi-environment, peer review, drift management | State management, ordering, rollback capability |
| Kubernetes operators like Strimzi | Kafka clusters managed via CRDs | CRD permissions, reconciliation, immutable/hard-to-change fields |
| Managed Kafka console/API | Provider-managed clusters | Provider limits, quotas, auditing, and IAM |

For instance, if production topics are created by the platform team, the consumer service **does not need topic CREATE permissions**. It only needs read/write and consumer group permissions per the operational contract.

## 7. Configuring Spring Boot Producers/Consumers for Provisioned Topics

Illustrative `application.yml`:

```yaml
app:
  kafka:
    topics:
      orders: orders.events.v1

spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        enable.idempotence: true

    consumer:
      group-id: orders-worker
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        allow.auto.create.topics: false

    listener:
      concurrency: 3
      ack-mode: record
```

These values illustrate **a non-transactional consumer** with Spring container-managed offset commits. When using Kafka transactions, manual acknowledgment, batch listeners, or custom retry/seek policies, configure the listener container according to **those specific semantics**; never copy `ack-mode` while ignoring the transaction manager.

`auto-offset-reset: earliest` applies only when the group **has no valid committed offset** for a partition, or in out-of-range offset cases. It does not make the consumer replay the entire topic on every restart. In production, align `earliest`, `latest`, or `none` with your bootstrap/replay policy rather than letting defaults cause data loss or duplication.

### 7.1. Keep Topic Names Separate from Business Logic

Producer:

```java
package com.example.kafka.orders;

import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> template;
    private final String topic;

    public OrderEventPublisher(
            KafkaTemplate<String, String> template,
            @Value("${app.kafka.topics.orders}") String topic) {
        this.template = template;
        this.topic = topic;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId, String eventPayload) {

        // Stable key to keep events for the same orderId
        // on one partition while partition count/partitioner stays unchanged.
        return template.send(topic, orderId, eventPayload);
    }
}
```

Consumer:

```java
package com.example.kafka.orders;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "${app.kafka.topics.orders}",
        groupId = "${spring.kafka.consumer.group-id}")
    public void consume(ConsumerRecord<String, String> record) {
        String orderId = record.key();
        String payload = record.value();

        // Validate, process, and persist results safely/idempotently.
        // Exception handling must follow the approved retry/DLT policy.
        processBusinessEvent(orderId, payload);
    }

    private void processBusinessEvent(String orderId, String payload) {
        // Placeholder: replace with actual business logic.
    }
}
```

This is a **structural example**, not a complete event schema. With JSON/Avro/Protobuf, configure matching serializers/deserializers, schema validation, and version compatibility policies separately. Avoid logging raw `eventPayload` if it holds sensitive data.

### 7.2. `concurrency` Does Not Create More Partitions

If a topic has 6 partitions and the listener container configures `concurrency: 3`, one Spring instance typically starts 3 consumers in the same group. Running 2 application replicas gives up to 6 consumers in the group. If other consumers already exist in that group, assignments depend on group membership and the assignor.

```text
Topic: 6 partitions

Pod A / listener:
  Consumer A1 -> P0
  Consumer A2 -> P1
  Consumer A3 -> P2

Pod B / listener:
  Consumer B1 -> P3
  Consumer B2 -> P4
  Consumer B3 -> P5
```

This diagram illustrates one possible assignment. Kafka does not promise to always assign partitions in that exact order. If a deployment runs 4 pods × concurrency 3 = 12 consumers for 6 partitions, some consumers receive no partitions for this topic.

## 8. Partition Keys and Message Routing

A producer can send with a key:

```java
kafkaTemplate.send("orders.events.v1", "order-101", "CREATED");
kafkaTemplate.send("orders.events.v1", "order-101", "PAID");
kafkaTemplate.send("orders.events.v1", "order-101", "SHIPPED");
```

With the same key and unchanged partitioner/partition count, records normally route to the same partition so consumers read them in offset order. If a producer sends **without a key**, the client picks partitions via batching/sticky strategies or client-version partitioning rules; never assume fixed round-robin distribution.

### 8.1. Explicitly Choosing a Partition

Kafka producer APIs and `KafkaTemplate` allow specifying a partition at send time:

```java
int partition = 2;

kafkaTemplate.send(
        "orders.events.v1",
        partition,
        "order-101",
        "ORDER_CREATED");
```

This helps in specialized integration protocols, yet couples application code to physical topology. When partition counts or routing policies change, **hardcoding `partition=2` can become a design flaw**. Normally, a stable business key and default partitioning are preferable.

If a custom partitioner is required, verify determinism, distribution balance, and stability across producer versions. Never look solely at partition count while ignoring hashing strategies and key serialization.

### 8.2. Increasing Partitions Can Change Key Mapping

With an initial partition count of 3:

```text
hash(order-101) % 3  -> P1
```

After scaling to 6:

```text
hash(order-101) % 6  -> could be P4
```

This expression illustrates the principle behind hash partitioning, **not the exact formula for every Kafka producer version**. The key takeaway is: **the same key can map to a different partition after partition count increases**.

If old messages remain in P1 while new messages enter P4, two consumers can process them concurrently and violate business ordering for `orderId`. That is one reason never to treat "increasing partitions" as a harmless change.

When strict per-key ordering is mandatory, design a migration plan such as:

1. Pausing or gating producers.
2. Draining/reconciling backlogs before changing routing.
3. Increasing partitions or creating a versioned topic with new routing.
4. Switching consumers/producers at a clear data boundary.
5. Monitoring event ordering and idempotency during cutover.

If using a custom partitioner, changing the hashing algorithm carries the same risk even if partition count stays constant.

## 9. Increasing Partitions and Hard-to-Reverse Changes

Kafka permits **increasing the partition count** of an existing topic under suitable conditions:

```bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1:9092 \
  --alter \
  --topic orders.events.v1 \
  --partitions 12
```

This command changes the topic from 6 to **12 total partitions**, not "adding 12 more partitions." Afterward:

- Consumer groups gain more parallelism opportunities, but must rebalance and receive new assignments.
- Producers may route keys to different partitions than before.
- Each new partition starts at its own initial offset without historical data from old partitions.
- Adding partitions does not migrate existing records from P0–P5 to P6–P11 to rebalance past data.
- Log segments, file handles, metadata, and cluster management overhead increase.

**Kafka does not support reducing a topic's partition count via standard alter operations.** If too many partitions were created, shrinking typically requires a new topic, data/routing migration, and consumer cutover.

### 9.1. Changing Replication Factor Is Not Like Adding Partitions

Replication factor should not be treated as a parameter altered like partition count via `kafka-topics.sh --alter`. Moving replicas or changing replication for an existing topic requires a **replica reassignment workflow** supported by the cluster/operators, checking broker capacity, replication progress, and leader elections.

Reassignment can generate heavy I/O and network traffic. Execute carefully, watch ISRs, and avoid major topology changes while the cluster is missing replicas or under emergency load.

### 9.2. Preparing a Rollback Plan

Before increasing partitions, record:

```text
Topic name / environment
Current partition count / replicas / min ISR
Producer key/partitioner strategy
Consumer groups and current lag
Peak message rate / partition skew
Plan to pause/drain or version topics
Validation after change
Recovery plan if ordering/business output is affected
```

You cannot "roll back" by lowering partition count directly once applied. Therefore, reversal usually means **migrating producers/consumers to the old or a new versioned topic** with reconciled data, rather than reverting the partition count.

## 10. Configuring Retention and Cleanup Policies

Topic configuration goes beyond partitions and RF. **Retention** governs how long or up to what size data stays in the log; **cleanup policy** governs how Kafka reclaims log segments.

| Property | Purpose | Operational Notes |
| --- | --- | --- |
| `retention.ms` | Data retention duration per retention policy | Not an exact per-record millisecond-precision TTL |
| `retention.bytes` | Log size limit **per partition** | Total storage also depends on partition count and replicas |
| `cleanup.policy=delete` | Deletes old log segments by retention | Common for event streams keeping bounded history |
| `cleanup.policy=compact` | Retains latest record per key via compaction | Does not immediately leave strictly one record per key |
| `cleanup.policy=compact,delete` | Combines compaction and retention-based deletion | Understand how retention and segment cleanup interact |
| `min.insync.replicas` | ISR threshold for `acks=all` writes | Unrelated to consumer counts |
| `unclean.leader.election.enable` | Allows electing an out-of-ISR leader in emergencies | Carries data-loss risk when enabled |
| `max.message.bytes` | Max record/batch size at the topic level | Must coordinate with producer/consumer fetch limits |

### 10.1. Event Streams vs. State/Changelog Topics Need Different Policies

For time-ordered event streams:

```text
orders.events.v1
cleanup.policy = delete
retention.ms  = 604800000  (7 days)
```

For latest entity state:

```text
orders.current-state.v1
cleanup.policy = compact
key             = orderId
value           = latest state
```

A compacted topic can still retain **multiple versions of the same key for a period**, because compaction runs via the log cleaner and segment rules. Messages with a `null` value (tombstones) delete keys in compacted logs and must be designed carefully with consumers and replays.

### 10.2. Disk Capacity and Replication

For example, one partition storing 100 GiB of logical data at RF=3 requires roughly **300 GiB of replica storage**, excluding indexes, segments, overhead, and broker distribution. Across many partitions, calculate total capacity by topic, retention window, peak ingestion rate, and observed compression ratios.

Never estimate storage simply as message count × raw payload size while ignoring compression, protocol overhead, indexes, and replication. Check quotas and disk/network limits of managed Kafka providers as well.

## 11. Security Configuration and Environment Isolation

A reliable deployment must never accidentally produce production data to a dev topic or create a new topic from a typo:

```text
dev.orders.events.v1
stg.orders.events.v1
prod.orders.events.v1
```

This naming scheme works **when an organization shares a cluster**. When each environment has a dedicated cluster, topics can keep the same name `orders.events.v1` while separated by bootstrap servers and access controls. What matters is an explicit policy, not adding environment prefixes everywhere.

Essential controls:

- Supply bootstrap servers and cluster identity via deployment config; never hardcode production endpoints in source.
- Grant producers only necessary WRITE/DESCRIBE rights; grant consumers READ/DESCRIBE on topics and matching group rights.
- Reserve `CREATE`/`ALTER`/`DELETE` topic permissions for provisioning principals, not application services.
- Configure TLS/SASL or cluster-appropriate auth/authorization; store secrets in a secret manager.
- Separate service accounts per environment with rotation and auditing.
- Enforce Schema Registry/compatibility when using Avro, Protobuf, or JSON Schema.
- Apply quotas so a runaway workload cannot starve the entire cluster.

Never log raw credentials, SASL JAAS configs, access tokens, or sensitive message payloads during troubleshooting. Topic compaction and retention do not replace personal data protection policies.

## 12. Safe Deployment Sequence: Topics First, Services Second

Suggested rollout order:

```text
1. Review topic contract
         |
         v
2. Provision/verify topic
         |
         +--> partitions / replication / ISR
         +--> retention / cleanup / ACL
         |
         v
3. Verify schema + serializer/consumer contract
         |
         v
4. Deploy producer/consumer with the new topic configuration
         |
         v
5. Controlled smoke test
         |
         v
6. Monitor lag, partition skew, ISR, and errors
```

For a new topic:

1. Verify the cluster has sufficient broker/rack capacity for target replication.
2. Create the topic via audited provisioning tooling.
3. Verify leaders/replicas/ISRs across every partition.
4. Confirm credentials/ACLs for application principals are granted.
5. Configure producer `acks=all` and idempotence as required.
6. Deploy consumers with explicit group IDs and offset policies.
7. Send a test message through a safe channel; confirm key, partition, schema, and processing output.
8. Enable monitoring and alerts before ramping traffic.

When modifying topics carrying live data, prepare a canary/cutover plan and message reconciliation; never run alter commands during peak traffic assuming consumers adapt seamlessly with zero impact.

### 12.1. Version Topic Contracts

Names like `orders.events.v1` reflect an event contract. When making incompatible changes to keys, ordering, or schemas, consider `orders.events.v2` with controlled dual-publish or dual-read phases instead of silently altering routing on the existing topic.

If dual-publishing, design **idempotency** downstream and establish which data boundary is the source of truth. Two topics can receive events at different times; never assume cross-topic consistency merely because the producer called `send()` twice.

## 13. Testing Topics and Partitions with Embedded Kafka

For local/test runs, `spring-kafka-test` provides `@EmbeddedKafka` to spin up an embedded broker and topics with exact partition counts. Tests can verify:

1. The topic exists with the expected partition count.
2. Messages with the same key route to the same partition when topology stays stable.
3. Producers send to specified valid partitions.
4. Consumer groups receive records per listener configuration.

**A single-broker Embedded Kafka is insufficient to prove RF=3/min ISR=2 fault tolerance.** Testing replication, ISR behavior when brokers die, leader elections, and rolling upgrades requires a multi-broker Kafka test cluster or dedicated integration environment.

### 13.1. Test Dependencies

```groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
}
```

### 13.2. Testing Metadata and Key Routing

The test below uses Spring Boot auto-configuration to build `KafkaTemplate<String,String>`, then checks broker metadata:

```java
package com.example.kafka;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.TopicDescription;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest(
    classes = TopicPartitionTest.TestApp.class,
    properties = {
        "spring.kafka.producer.key-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer",
        "spring.kafka.producer.value-serializer="
            + "org.apache.kafka.common.serialization.StringSerializer"
    }
)
@EmbeddedKafka(
    partitions = 3,
    topics = "orders.test.v1",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class TopicPartitionTest {

    static final String TOPIC = "orders.test.v1";

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {}

    @Autowired
    EmbeddedKafkaBroker broker;

    @Autowired
    KafkaTemplate<String, String> template;

    @Test
    void topicHasThreePartitions() throws Exception {
        Map<String, Object> props = Map.of(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                broker.getBrokersAsString());

        try (AdminClient admin = AdminClient.create(props)) {
            Map<String, TopicDescription> topics =
                    admin.describeTopics(List.of(TOPIC))
                            .allTopicNames()
                            .get(10, TimeUnit.SECONDS);

            assertThat(topics.get(TOPIC).partitions()).hasSize(3);
        }
    }

    @Test
    void sameKeyUsesSamePartitionWhenTopologyIsStable()
            throws Exception {

        RecordMetadata first = template
                .send(TOPIC, "order-101", "CREATED")
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata();

        RecordMetadata second = template
                .send(TOPIC, "order-101", "PAID")
                .get(10, TimeUnit.SECONDS)
                .getRecordMetadata();

        assertThat(first.partition()).isEqualTo(second.partition());
        assertThat(first.topic()).isEqualTo(TOPIC);
        assertThat(second.offset()).isGreaterThan(first.offset());
    }
}
```

This test uses a fixed test-broker topic and makes no guarantee that the same key stays on the same partition **after increasing partitions or changing partitioner algorithms**. Testing RF/min ISR requires a multi-broker cluster; topics created by `@EmbeddedKafka` here normally have RF=1.

### 13.3. Testing Listener Concurrency and Assignments

With a three-partition topic, you can declare:

```java
@KafkaListener(
    topics = "orders.test.v1",
    groupId = "orders-test-group",
    concurrency = "3")
public void consume(ConsumerRecord<String, String> record) {
    // Record topic/partition/offset for testing.
}
```

This snippet is a listener fragment requiring a Spring bean class and imports. In integration tests, send records **explicitly targeting partitions 0, 1, and 2** to guarantee data on every partition, await full partition assignment before sending, and assert each record is processed once in an isolated test run.

Never send 30 messages with 30 random keys assuming Kafka will distribute exactly 10 messages per partition: hash distribution does not promise uniform balance on a small sample.

### 13.4. Testing Replication and ISR on a Three-Broker Cluster

This is an **infrastructure-level test**, not a unit test:

1. Spin up a three-broker Kafka cluster in an isolated test environment.
2. Provision a topic with 3 partitions, RF=3, min ISR=2.
3. Run an `acks=all` producer and verify writes and reads succeed.
4. Stop one broker, wait for leader/ISR stabilization, and confirm writes still satisfy policy while sufficient ISRs remain.
5. Stop another broker or reduce ISR below two, and verify the producer receives errors or timeouts per contract.
6. Restore brokers and verify ISRs recover fully with no loss of committed records under test conditions.

Never attempt to simulate RF=3 on a single embedded broker. In failover tests, use bounded timeouts, track which broker is leader/follower, and never draw conclusions from an arbitrary sleep. On managed Kafka where stopping brokers is restricted, use a dedicated Kafka chaos environment.

## 14. Observing Topics and Partitions Post-Deployment

A "successfully created" topic can still underperform or fail durability expectations. Dashboards should observe **producers, brokers, partitions, and consumer groups**:

| Group | Metrics / Events to Watch | Meaning |
| --- | --- | --- |
| Broker/topic | Under-replicated partitions | Replicas falling behind leader |
| Broker/topic | Offline partitions / unavailable leaders | Partitions may be unavailable |
| Replication | ISR shrink/expand | Write safety fluctuating |
| Producer | Record send rate, error rate, retries | Write failures or load spikes |
| Producer | Record latency and timeouts | Broker/network/ISR bottlenecks |
| Partition | Bytes in/out, messages in per partition | Hot partitions, key skew |
| Consumer group | Lag per partition | One partition falling behind |
| Consumer | Rebalance frequency, poll/processing latency | Assignment churn or slow processing |
| Storage | Disk usage, log size, retention/cleanup activity | Disk exhaustion or unexpected data purge |
| Security | Authorization failures / unknown topic | Misconfigured ACLs or provisioning |

Example interpretation:

```text
Topic: orders.events.v1 (6 partitions)

P0 lag: 100
P1 lag: 80
P2 lag: 110
P3 lag: 95
P4 lag: 65,000   <-- needs investigation
P5 lag: 90
```

Severe lag isolated to P4 can point to **hot keys, a failing consumer assigned to P4, poison-record retries, or slow downstream DB/APIs**. Simply adding pods rarely helps immediately because within one consumer group, a single partition is not shared concurrently across multiple consumers under standard assignment.

### 14.1. Avoid High-Cardinality Metric Labels

Bounded-cardinality labels like `topic`, `partition`, `consumer_group`, `client_id`, and `error_code` can be useful depending on cluster size. Never use `orderId`, `customerId`, message keys, or offsets as time-series metric labels: series counts explode and risk leaking sensitive info.

In diagnostic logs, record `topic`, `partition`, `offset`, and approved execution/correlation references; avoid dumping full payloads or credentials.

## 15. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Creating RF=3 topic on single-broker local fails | Insufficient brokers for replication | Use RF=1 locally or run a three-broker cluster |
| Producer reports `UNKNOWN_TOPIC_OR_PARTITION` | Topic not created, typo, or stale metadata | Verify provisioning, bootstrap servers, and ACLs |
| Broker auto-creates misconfigured topic | `auto.create.topics.enable` is on, topic typo | Provision explicitly; restrict permissions and auto-creation |
| New consumer skips historical data | Group has no offset and `auto-offset-reset=latest` | Choose bootstrap offset policy intentionally |
| Some consumers sit idle | More consumers in group than partitions | Reduce concurrency/pods or adjust topology |
| Single partition has extreme lag | Hot key or slow processor | Inspect key skew, capacity, and ordering contracts |
| `acks=all` times out during broker fault | ISR fell below `min.insync.replicas` | Restore replicas/cluster; do not recklessly lower durability |
| Same order's events processed out of order after partition increase | Same key hashed to a new partition | Migration plan with drain/order boundary or topic versioning |
| Retention deletes data earlier than replay needs | Insufficient `retention.ms/bytes` | Recalculate retention, storage budget, and replay SLA |
| Compacted topic still holds old records | Compaction is not instantaneous | Understand log cleaner/segment semantics |
| Adding partitions does not rebalance past data | Kafka does not move old records to new partitions | Tune future load; do not expect historical rebalancing |
| Consumer group rebalances continuously | Deployments/poll timeouts/instance churn | Monitor membership, processing times, and group config |
| App fails to provision topic on startup | Missing CREATE rights or broker not ready | Provision pre-deploy or configure `KafkaAdmin` properly |
| Editing Java topic config fails to alter existing topic fully | Mistaking `NewTopic` for full reconciliation | Use operator/IaC workflows and post-change verification |
| Message key is a random UUID on every order event | Fails to preserve per-order ordering | Key by the defined business entity |

## 16. Pre-Production Topic Checklist

**Data Contract**

- Topic name/version is clear; schema and key are agreed between producers and consumers.
- Ordering scope is documented per entity/partition.
- Replay, retention, and data retention window plans exist.

**Reliability**

- Partition count is sized for peak load and consumer capacity.
- Replication factor and min ISR align with broker count, SLAs, and durability requirements.
- Producer `acks`, idempotence, and retries are configured consistently.
- Alerts exist for under-replicated/offline partitions and disk pressure.

**Deployment**

- Topics are provisioned/verified before dependent apps start.
- ACLs/RBAC, TLS/SASL, and secret management work properly.
- Consumer group IDs and `auto-offset-reset` are chosen intentionally.
- Concurrency/pod counts do not overload downstream databases or APIs.

**Change and Recovery**

- Never increase partitions without analyzing key mapping and ordering impacts.
- Replica reassignment, retention changes, and schema evolution have rollback/cutover plans.
- Per-partition lag dashboards and broker-failure/rebalance tests exist for high-reliability flows.
- Idempotency and deduplication handle redeliveries after crashes/rebalances.

## 17. Practice Exercise

Suppose you must build the `orders.events.v1` pipeline at 9,000 messages/sec peak with three consumer replicas:

1. **Topic design:** choose 6 partitions, RF=3, min ISR=2 on a three-broker cluster; explain why partition count differs from RF.
2. **Provision:** create the topic via Kafka CLI or IaC with 7-day retention and `delete` cleanup.
3. **Verify:** use `kafka-topics.sh --describe` and `kafka-configs.sh --describe` to inspect partition count, replicas, ISR, and topic overrides.
4. **Spring Boot:** configure `spring.kafka.bootstrap-servers`, producer `acks=all`, idempotence, consumer group, and `concurrency=2` per pod.
5. **Ordering:** send `CREATED`, `PAID`, `SHIPPED` for the same `orderId`. Confirm metadata shows all events landed on the same partition under a stable topology.
6. **Distribution:** send many distinct orderIds, count messages per partition, and check for key skew. Do not expect exact uniformity on a small sample.
7. **Partition scaling:** simulate scaling from 6 to 12 partitions in test. Check whether sample keys change partitions, then write a cutover plan preserving ordering.
8. **Concurrency:** run two pods × `concurrency=3` on a six-partition topic; then run four pods × `concurrency=3` and explain why extra threads stay idle.
9. **Broker failure:** on a three-broker test cluster, stop one broker and observe leaders/ISR and `acks=all` producer behavior; drop ISR below two to observe durability enforcement.
10. **Retention:** compare `cleanup.policy=delete` vs. `compact` on another test topic and explain why compaction does not immediately purge all older versions.
11. **Monitoring:** build a dashboard with throughput, per-partition lag, ISR, producer errors, and disk usage; set alerts for hot partitions.
12. **Deployment:** decouple topic provisioning from service runtime, verify ACLs, and write a config-change checklist with rollback/cutover plans.

## 18. Summary

**Topics and partitions are architectural decisions with long-lived operational consequences.** Partitions define parallelism and ordering scope; replication factor, ISR, and producer acknowledgments establish the durability policy; retention and cleanup policy govern data preservation and replay; and keys/partitioners determine record distribution.

In Spring Kafka, `KafkaTemplate` and `@KafkaListener` must align with real topic configurations, yet **they never replace proper cluster-level provisioning, verification, monitoring, and safe change management**. When designed upfront around load, ordering, durability, and access controls—and verified via Embedded Kafka and multi-broker environments when needed—systems scale and recover cleanly without compromising data stream correctness.

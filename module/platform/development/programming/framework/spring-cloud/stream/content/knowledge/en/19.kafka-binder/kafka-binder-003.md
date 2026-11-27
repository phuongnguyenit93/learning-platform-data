# Topic Provisioning and Controlling `autoCreateTopics` and `autoAddPartitions`

The Kafka Binder needs a topic to connect an output or input binding to Kafka. When a binding is initialized, the binder checks the target topic and required partition count. Depending on configuration, the binder can create a topic that does not yet exist or increase the partition count of an existing topic. Two key properties control this behavior: `autoCreateTopics` and `autoAddPartitions`.

In development environments, automatically creating and expanding topics helps launch applications quickly. In production, topic provisioning usually needs centralized management to control replication factor, retention, capacity, access permissions, and scaling plans. Understanding both properties prevents applications from unintentionally creating resources or failing to start because a topic has too few partitions.

## 1. Topics Are Resources Used by Bindings

In Spring Cloud Stream, a Kafka binding's `destination` property typically maps to a Kafka topic name. Producers send records to the topic; consumers read records from the topic using a consumer group and offsets.

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          content-type: application/json
        processOrder-in-0:
          destination: orders.created
          group: inventory-service
          content-type: application/json
```

In this example, both bindings use the same destination `orders.created`. The producer and consumer group operate on the same topic. A group does not create a separate topic; it maintains independent offset state so instances in the same group share partitions.

A topic must be pre-created or provisioned by the binder when the binding initializes. Creating a topic involves the topic name, partition count, and replication factor. Settings like retention, cleanup policy, compression, quotas, and ACLs are separate operational decisions; do not treat the two auto-provisioning properties below as a full topic governance mechanism.

## 2. `autoCreateTopics`: Creating a Topic When It Does Not Exist

`spring.cloud.stream.kafka.binder.autoCreateTopics` controls whether the Kafka Binder automatically creates a topic when the destination does not exist. By default, this property is `true` in standard Kafka Binder configuration.

- When `true`, the binder can use the Kafka `AdminClient` to create missing topics during binding provisioning, if the connected account has sufficient administrative permissions.
- When `false`, the binder does not proactively create topics. Topics must be created beforehand via admin tools or Infrastructure as Code; if the topic does not exist, binding provisioning may fail.
- This property applies to the binder's topic provisioning. It is not the same setting as `auto.create.topics.enable` on the broker side.

Example configuration for a development environment:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-create-topics: true
```

With the configuration above, when the application creates a binding to `orders.created`, the binder can create the topic if it is missing. If the broker does not allow the user to create topics, the application can still encounter an authorization error even when `auto-create-topics` is enabled.

### 2.1. Distinguishing from Kafka Broker's `auto.create.topics.enable`

A Kafka broker has its own `auto.create.topics.enable` setting, which controls whether the broker automatically creates a topic when a client accesses a non-existent topic via paths that trigger implicit creation. This is a broker-level setting.

The two settings have different scopes:

| Setting | Where Configured | Role |
|---|---|---|
| `spring.cloud.stream.kafka.binder.autoCreateTopics` | Spring Cloud Stream application | Allows the binder to explicitly provision topics via `AdminClient` |
| `auto.create.topics.enable` | Kafka broker | Allows or blocks the broker from implicitly creating topics when a client requests metadata/read/write for a missing topic |

Disabling implicit topic creation on the broker does not automatically forbid `AdminClient` from creating topics explicitly. Conversely, disabling `autoCreateTopics` in the binder does not change broker settings. In tightly governed environments, implicit broker creation and automatic application provisioning are usually both disabled; deployment pipelines create topics before deploying producers and consumers.

## 3. `autoAddPartitions`: Increasing Partitions on an Existing Topic

`spring.cloud.stream.kafka.binder.autoAddPartitions` controls whether the binder automatically increases the partition count when an existing topic has fewer partitions than required by binding/binder configuration. By default, this property is typically `true`.

For example, suppose the `orders.created` topic currently has 2 partitions, but the producer configuration requests 6 partitions. If `autoAddPartitions` is enabled and the user has permission to alter topics, the binder can ask Kafka to increase the partition count to 6 during binding provisioning.

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-add-partitions: true
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-count: 6
```

`partition-count` on the producer is the desired/requested partition count for the destination during provisioning. The actual partition count of the topic is managed by Kafka. If the topic already has more partitions, the binder does not shrink the partition count down to a smaller configured value.

When `autoAddPartitions` is `false`, the binder does not automatically expand topics. If an existing topic does not meet the required partition count, the binding may fail to provision. In that case, an administrator must expand the topic beforehand through an approved admin process, or adjust application configuration to match the existing topic.

### 3.1. Where Does the Required Partition Count Come From?

The partition count requested by the binder can be influenced by configuration at both the binder and binding levels. Properties that commonly need to be reviewed together include:

| Property | Scope | Meaning |
|---|---|---|
| `spring.cloud.stream.kafka.binder.min-partition-count` | Kafka Binder | Minimum number of partitions the binder requires for a provisioned topic |
| `spring.cloud.stream.bindings.<binding>.producer.partition-count` | Producer binding | Desired partition count for the producer's destination |
| `spring.cloud.stream.bindings.<binding>.consumer.concurrency` | Consumer binding | Number of consumer threads in one instance; affects parallel consumption capacity per instance |
| `spring.cloud.stream.instance-count` | Application | Declared instance count when the binder needs to calculate capacity for partitioned consumers |

The final requested value depends on binding type, partitioning configuration, and binder version. For consumers partitioned by instance, both `instance-count` and `concurrency` must be accounted for when planning partition count. Do not look only at the producer's `partition-count` or only at the number of running pods and assume the topic has enough partitions.

For example, a consumer service running 3 instances with concurrency 2 each can use up to 6 consumer slots in parallel within the same group. A topic with fewer than 6 partitions will leave some slots without any partitions assigned. Increasing partitions only helps when downstream capacity and data partitioning strategy can support it.

## 4. Combining the Two Properties

The two properties control two distinct situations:

| `autoCreateTopics` | `autoAddPartitions` | Expected Behavior |
|---|---|---|
| `true` | `true` | Binder can create missing topics and add partitions to existing topics when needed |
| `true` | `false` | Binder can create new topics with the requested partition count, but will not expand an existing topic that has too few partitions |
| `false` | `true` | Topic must exist; binder can add partitions if the existing topic has too few and the user has alter permission |
| `false` | `false` | Topics and required partition counts must be prepared in advance; binder does not auto-create or expand |

When `autoCreateTopics` is disabled and the topic does not exist, `autoAddPartitions` cannot replace topic creation. Conversely, if the topic already exists, disabling topic creation does not necessarily prevent the binder from expanding partitions while `autoAddPartitions` remains enabled.

## 5. Configuration Examples by Environment

### 5.1. Local Development Environment

In local environments, allowing the binder to auto-create topics and add partitions lets developers focus on producer/consumer code:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
          auto-create-topics: true
          auto-add-partitions: true
          min-partition-count: 1
          replication-factor: 1
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-count: 3
        processOrder-in-0:
          destination: orders.created
          group: inventory-local
          consumer:
            concurrency: 3
```

A replication factor of 1 suits a single-node Kafka setup for learning; it provides no fault tolerance. Local topics can be created when bindings initialize, and the binder can add partitions if the topic already exists with fewer partitions than requested.

### 5.2. Production Environment with Centralized Provisioning

In production, it is usually best to have pipelines or a platform team pre-create topics. The application simply connects to already provisioned resources:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-create-topics: false
          auto-add-partitions: false
      bindings:
        publishOrder-out-0:
          destination: orders.created
          producer:
            partition-count: 12
        processOrder-in-0:
          destination: orders.created
          group: inventory-service
          consumer:
            concurrency: 4
```

Before deploying this configuration, the `orders.created` topic must exist with an appropriate partition count (at least 12 per the producer requirement in the example) along with platform-standard replication factor, retention, cleanup policy, and ACLs. If the topic is missing or lacks enough partitions, the binding may fail to initialize. The application does not modify topic configuration on its own in this environment.

Values can be separated by Spring profile, such as `application-local.yml` and `application-prod.yml`. Check the active profile in startup logs to avoid accidentally running production with a local configuration that allows resource creation.

## 6. Pre-Provisioning Topics with Kafka Tools

When auto-creation and expansion are disabled, administrative pipelines must provision topics beforehand. Example using `kafka-topics.sh`:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders.created \
  --partitions 12 \
  --replication-factor 3
```

A replication factor of 3 requires a cluster with enough suitable brokers. Adjust broker count, rack awareness, and replication policy to match your actual platform; do not copy this value into a smaller cluster.

Inspect the topic after creation:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.created
```

The topic description reports partition count, leader, replicas, and ISR. Confirm the right cluster, topic, and partition count before deploying the application.

If you need to add partitions to an existing topic, use the alter command:

```bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --alter \
  --topic orders.created \
  --partitions 18
```

The new partition count must be greater than the current count. Kafka does not support reducing the partition count of an existing topic via standard alter operations. To reduce partitions, plan to create a new topic and migrate data, producers, and consumers through a migration procedure.

## 7. Impact of Increasing Partitions

Increasing partitions is not just a capacity change. It changes parallelism, data distribution, and can affect processing order.

### 7.1. Consumer Group Parallelism

In a Kafka consumer group, each partition at any given time is assigned to at most one consumer member in the group. If the group has more consumers than partitions, some consumers will receive no partitions. Adding partitions can increase parallelism, but only if the application, database, and downstream services can handle the extra load.

For example, with a 4-partition topic and 8 consumer instances in a group, at most 4 consumers have partitions assigned at once. Expanding the topic to 8 partitions allows the group to assign work to all 8 consumers, depending on configuration and group state.

### 7.2. Ordering by Key Can Change After Expansion

Kafka guarantees ordering within a single partition, not across the entire topic. With the default partitioner, keys are typically hashed to choose a partition based on the current partition count. When the partition count increases, the same key may map to a different partition for new records. Older records for that key remain in the old partition.

This can cause old and new records for the same key to be processed by different consumers, leading to out-of-order observations compared to before. If business logic requires strict ordering by `orderId`, treat partition expansion as an architectural change; you may need a stable partitioning strategy, versioned routing, or migration to a new topic.

### 7.3. Resource and Operational Overhead

More partitions increase log segments, metadata, file handles, leader election overhead, rebalances, and operational effort. Consumer groups also have to reassign partitions when partition counts change. Do not set partition counts excessively high just "for headroom" without estimating throughput, record size, retention, and consumer count.

## 8. Provisioning Permissions and Common Errors

The binder may connect to brokers successfully yet still lack permission to create or alter topics. The runtime account needs permissions matching the provisioning operations. ACL models vary by Kafka version and platform authorization setup; grant least-privilege permissions for specific topics/prefixes and environments.

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Binding fails because topic does not exist | `autoCreateTopics=false` and topic not provisioned; or user lacks create permission | Check topic on cluster and `AdminClient` permissions |
| Topic does not automatically add partitions | `autoAddPartitions=false`, requested count does not exceed current count, or missing alter permission | Compare actual partitions with requested count; check permissions and provisioner logs |
| Local app creates topic with 1 partition unexpectedly | `partition-count`/`min-partition-count` not loaded or wrong profile | Check effective configuration and `kafka-topics --describe` |
| Topic created with low replication factor | Replication factor setting unsuitable or cluster has too few brokers | Check replication factor and broker count; adjust provisioning process |
| Startup fails with authorization exception | Runtime principal lacks required describe/create/alter permissions | Check ACLs and the application's actual principal |
| Increasing partitions alters ordering by key | Hash partitioning depends on partition count | Evaluate ordering requirements and migration plan |
| Broker creates topics unexpectedly | `auto.create.topics.enable` is enabled | Check broker configuration and cluster governance process |

Specific exceptions may include authorization errors, topic metadata errors, or partition creation errors; exact exception names and root causes depend on Kafka client, broker, and binder versions. Read full startup logs, especially the root cause from `AdminClient`/provisioner.

## 9. Dynamic Destinations and StreamBridge

`StreamBridge` can send to destinations determined at runtime, and the binder can create dynamic bindings on the first send. If dynamic destinations are uncontrolled, an application can accidentally create many topics based on input data, such as customer names or request IDs.

For dynamic destinations:

- Use an allowlist or naming rule that bounds the set of valid destinations.
- Clearly define who is permitted to create topics and which topics must be pre-provisioned.
- Consider disabling `autoCreateTopics` in production so dynamic bindings cannot create unplanned topics.
- Monitor the count of dynamic bindings/topics and establish a cleanup process after confirming no data needs to be retained.
- Never use raw user input directly as a topic name without validating characters, length, and permissions.

Dynamic binding does not bypass topic provisioning rules. It only changes when the binder discovers the destination and provisions the binding.

## 10. Testing Provisioning Behavior

Testing should cover different topic states:

1. Topic does not exist and `autoCreateTopics=true`: verify the binder creates the topic with the expected partition count and replication factor.
2. Topic does not exist and `autoCreateTopics=false`: verify startup/binding reports a clear error without creating unintended topics.
3. Existing topic has fewer partitions than required and `autoAddPartitions=true`: verify the topic is expanded.
4. Existing topic has fewer partitions than required and `autoAddPartitions=false`: verify the binding does not silently run with an under-partitioned topic.
5. User lacks create/alter permissions: verify authorization errors are caught and logs contain actionable information.
6. Topic already has more partitions than configured: verify the binder does not attempt to reduce partitions.
7. Partition expansion when keyed records exist: re-check ordering and record distribution.
8. Dynamic destination outside allowlist: verify the application rejects it before creating a binding or topic.

The Test Binder is suitable for testing function logic and certain binding behaviors in the JVM, but it does not replace real Kafka for topic creation, ACLs, partition counts, replication factors, and `AdminClient`. Provisioning behavior must be tested against an embedded/containerized broker or a Kafka test environment with production-equivalent permissions.

## 11. Configuration Selection Process

| Environment | `autoCreateTopics` | `autoAddPartitions` | Appropriate Management Approach |
|---|---:|---:|---|
| Local workstation | `true` | `true` | Let the binder create resources for learning and experimentation |
| Isolated integration test | Per fixture | Per fixture | Create topics explicitly in test setup if verifying provisioning |
| Staging | Usually `false` | Usually `false` or per platform policy | Provision via pipeline to mirror production |
| Production | Usually `false` | Usually `false` | Centralized topic management; review partitions/replication/retention/ACLs before deployment |

There is no single mandatory value for every system. If the platform allows binders to provision topics, restrict permissions and strictly control configuration. If topics are centrally governed, disable both automatic features so applications only use pre-allocated resources.

## 12. Pre-Deployment Checklist

- [ ] Every binding has an explicit `destination` and the topic exists or is permitted to be created.
- [ ] `autoCreateTopics` is chosen according to environment policy.
- [ ] `autoAddPartitions` is chosen according to the partition governance process.
- [ ] `minPartitionCount`, producer `partitionCount`, consumer `concurrency`, and `instance-count` are checked as needed.
- [ ] Topic has enough partitions for the desired level of parallelism.
- [ ] Replication factor, retention, cleanup policy, compression, and ACLs are managed separately.
- [ ] Runtime principal has only the necessary create/alter/describe permissions.
- [ ] Broker-level `auto.create.topics.enable` has been checked and distinguished from the binder property.
- [ ] Key-based ordering impact has been evaluated before increasing partitions.
- [ ] Dynamic destinations have allowlists and count limits.
- [ ] Integration tests against real Kafka cover topic provisioning and access permissions.
- [ ] Startup logs and metrics indicate whether topic/partition provisioning succeeded.

`autoCreateTopics` determines whether the binder proactively creates missing topics; `autoAddPartitions` determines whether the binder automatically expands partitions of existing topics when needed. These two properties make development convenient, but in production you must weigh administrative permissions, replication, retention, parallelism, and key-based ordering. Intentional topic management ensures applications start consistently and prevents unplanned Kafka resource changes.

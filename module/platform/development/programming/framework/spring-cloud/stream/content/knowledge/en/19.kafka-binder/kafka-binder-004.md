# Configuring Partition Count, Replication Factor, and Topic Properties

The Kafka Binder connects Spring Cloud Stream bindings to Kafka topics. When a binding needs a topic that does not yet exist, the binder can create the topic and configure its partition count, replication factor, and selected topic properties. When the topic already exists, the binder checks whether the current configuration meets the binding's requirements; some options can add partitions, while changing existing replica assignments or topic configs usually requires separate administrative operations.

Three configuration groups should be distinguished:

- **Partition count** determines how a topic is divided into independent ordered log streams and affects parallel processing capacity.
- **Replication factor** defines how many copies of each partition exist across brokers, affecting fault tolerance and storage cost.
- **Topic properties** control retention period, compaction policy, message size limits, minimum in-sync replicas, and other storage behaviors.

Spring Cloud Stream provides configuration at both the Kafka binder level and the individual binding level. Choosing the right scope lets many topics share common defaults while special topics receive custom settings tailored to business needs.

## 1. Kafka Topic Structure

A topic contains one or more partitions. Each partition is an append-only log with its own record order and is identified by an ordinal number. Records within the same partition have monotonically increasing offsets; Kafka does not maintain a global order across partitions.

~~~text
Topic: orders.events

Partition 0:  offset 0 -> offset 1 -> offset 2
Partition 1:  offset 0 -> offset 1 -> offset 2
Partition 2:  offset 0 -> offset 1 -> offset 2
~~~

The producer selects the partition for each record, typically based on the record key or partitioning strategy. A consumer group distributes partitions among its consumer members for parallel processing. Partition count is therefore a key factor when designing throughput and concurrency.

Each partition has one leader replica and may have multiple follower replicas on other brokers. Producers write to the leader; followers replicate data from the leader. Kafka tracks the set of replicas that are in sync, called the ISR (In-Sync Replicas). If the leader fails, an eligible replica can be elected as the new leader according to cluster policy.

## 2. Partition Count and Replication Factor

These two parameters have different meanings:

| Parameter | Meaning | Example |
|---|---|---|
| Partition count | Number of independent logs in the topic | 6 partitions |
| Replication factor | Number of copies of each partition, including the leader | 3 replicas |

If a topic has 6 partitions and a replication factor of 3, there are 18 partition replicas distributed across brokers in total. This does not mean the topic has 18 logical partitions; a consumer group still only distributes the 6 logical partitions.

A replication factor of 3 generally requires at least 3 brokers so replicas can be placed on separate brokers. If a cluster has fewer brokers, creating a topic with a replication factor greater than the broker count may fail or fail to achieve the desired distribution depending on configuration and version.

Partition count affects:

- Maximum parallelism of a consumer group for that topic.
- Number of leaders and metadata the cluster must manage.
- Log segment sizes, file handles, and operational overhead.
- Key distribution and per-partition ordering.

Replication factor affects:

- Ability to continue reading and writing when a broker fails.
- Storage footprint and inter-broker replication traffic.
- How many replicas must catch up for a partition to return to a fully healthy state.
- Write availability when the ISR count drops below the required threshold.

Do not increase partitions solely to add more consumers. If a topic has 6 partitions, a consumer group can assign up to 6 partitions to 6 consumers at once; additional consumers will not receive partitions. Choose the partition count based on measured throughput, processing latency, expected concurrency, and broker resources.

## 3. Kafka Binder-Level Configuration

The Kafka Binder provides global properties under the `binder` section:

| Property | Role |
|---|---|
| `auto-create-topics` | Allows the binder to create topics when needed |
| `auto-add-partitions` | Allows the binder to add partitions when an existing topic has too few |
| `min-partition-count` | Minimum number of partitions the binder requires when provisioning |
| `replication-factor` | Default replication factor for topics created by the binder |
| `required-acks` | Write acknowledgement level required by the Kafka producer |

Configuration example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
          auto-create-topics: true
          auto-add-partitions: true
          min-partition-count: 3
          replication-factor: 3
          required-acks: all
~~~

Meaning:

- **auto-create-topics: true** allows the binder to create a topic when it does not exist and the binder needs to provision it.
- **auto-add-partitions: true** allows the binder to increase the partition count of an existing topic when its current count is below the required level.
- **min-partition-count: 3** sets the minimum partition count at the binder level.
- **replication-factor: 3** sets the default replication factor for auto-created topics.
- **required-acks: all** requires the producer to wait for acknowledgement from replicas in the ISR according to Kafka semantics.

In current Kafka Binder documentation, `min-partition-count` only takes effect when `auto-create-topics` or `auto-add-partitions` is enabled. This value can be overridden by the producer's `partition-count` or by the product of `instance-count` and `concurrency` if either is larger. Thus, the actual provisioned partition count may be greater than `min-partition-count`.

Binder-level `replication-factor` applies to auto-created topics and can be overridden per binding. Starting with Kafka Binder 3.0.8, the default value is `-1`, which uses the broker's `default.replication.factor` configuration. In older versions, defaults and handling differ; some versions require a value of at least 1. Verify your binder version before relying on defaults.

## 4. Distinguishing Binder vs. Broker `auto-create-topics`

The Kafka Binder's `auto-create-topics` property is independent of the Kafka broker's `auto.create.topics.enable` setting:

- If the binder enables `auto-create-topics`, the binder can proactively provision topics based on application configuration.
- If the binder disables `auto-create-topics`, the binder expects the topic to already exist and be configured; if the topic does not exist, the binding may fail to start.
- If the broker still enables `auto.create.topics.enable`, the broker may automatically create a topic upon receiving a metadata request for a non-existent topic, using broker-side default settings.

In production, if an organization wants to govern topics through an infrastructure process, topics should be pre-created via admin tools or an operator, unintended auto-creation should be disabled, and the binder should be configured to use existing topics. The infrastructure pipeline is then responsible for partition counts, replica assignments, and topic properties.

## 5. Configuring Partition Count Per Binding

In addition to the binder-wide `min-partition-count`, a producer binding has a `partition-count` property. This property hints at the number of partitions when the binder provisions a topic:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-count: 6
            partition-key-expression: payload.orderId
~~~

In this example, the `publishOrder-out-0` binding publishes to the `orders.events` topic and requests at least 6 partitions during provisioning. `partition-key-expression` selects `orderId` as the partition key via Spring Cloud Stream's generic partitioning mechanism. Messages with the same `orderId` are routed to the same partition when using the same algorithm and partition count.

`partition-count` is not a command to reduce a topic's partition count. Kafka does not support decreasing partition counts with standard alter operations. If a topic already has 8 partitions while the binding requests 6, the binder uses the existing partition count; it does not shrink it to 6.

If the topic already has fewer partitions than the requested value:

- When `auto-add-partitions` is `false`, the binder may reject provisioning and fail to start the binding.
- When `auto-add-partitions` is `true`, the binder may add partitions to reach the required level.

Increasing the partition count can change the key-to-partition mapping. With a hash partitioner, the same `orderId` may be written to an old partition before expansion and a new partition after expansion. Consequently, increasing partitions can place older and newer messages with the same key on different partitions, affecting business ordering. Plan a migration and evaluate consumers before making changes.

## 6. Replication Factor Per Binding

A specific topic may need a different replication factor than the binder-wide default. The Kafka Binder allows setting the replication factor under the producer binding's `topic` configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
~~~

The full configuration path is `spring.cloud.stream.kafka.bindings.<binding-name>.producer.topic.replication-factor`. This value overrides the binder-wide `replication-factor` when provisioning the topic for that binding.

Per-binding replication factor is only used during topic provisioning. If the topic already exists, changing this value in `application.yml` does not automatically redistribute the topic's replicas. Changing the replication factor of an existing topic requires a replica reassignment operation using Kafka admin tools or a cluster management platform.

An explicit replica assignment can be declared using `topic.replicas-assignment`. This is a map from partition ID to the list of broker IDs assigned replicas for that partition. When replica assignment is provided, `replication-factor` is ignored because the broker list already determines the replica count and exact placement. Ensure broker IDs exist, are distributed sensibly, and never place all replicas of a partition on the same broker.

## 7. Configuring Topic Properties Per Binding

Kafka topics have many properties that control storage and operational behavior. The Kafka Binder lets you set them via the `topic.properties` map under producer or consumer binding configuration. Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
                properties:
                  min.insync.replicas: 2
                  retention.ms: 604800000
                  cleanup.policy: delete
                  max.message.bytes: 1048576
                  segment.bytes: 1073741824
~~~

This example sets:

- **min.insync.replicas: 2** requires at least two replicas in the ISR when a producer writes with `acks=all`.
- **retention.ms: 604800000** sets the maximum log retention under the delete policy to seven days.
- **cleanup.policy: delete** uses retention-based log deletion.
- **max.message.bytes: 1048576** sets the record batch size limit at the topic configuration level.
- **segment.bytes: 1073741824** sets the target log segment size to roughly 1 GiB.

`topic.properties` is a map of Kafka topic configuration properties, not a map of Kafka producer client properties. Properties like `linger.ms`, `batch.size`, or `compression.type` belong to the producer client and must be placed under `producer.configuration` or the corresponding producer properties, not mistakenly placed in `topic.properties`.

`topic.properties` is used when the binder provisions the topic. For an existing topic, do not assume that modifying this map updates the configuration currently stored on the broker. Use the Kafka Admin API, `kafka-configs.sh`, or a topic management operator to update existing configs.

## 8. Commonly Used Topic Properties

| Property | Meaning | Use Case |
|---|---|---|
| `cleanup.policy` | Delete, compact, or combined policy | Event logs or keyed changelogs |
| `retention.ms` | Log retention duration under delete policy | Retaining data for a business window |
| `retention.bytes` | Log size limit per partition | Controlling disk storage usage |
| `min.insync.replicas` | Minimum ISR required for writes with `acks=all` to succeed | Balancing data durability and write availability |
| `max.message.bytes` | Record batch size limit | Preventing oversized messages from stressing brokers |
| `segment.bytes` | Log segment size | Tuning log management and retention tasks |
| `message.timestamp.type` | Choose `CreateTime` or `LogAppendTime` | Standardizing timestamp interpretation |

### cleanup.policy

With **delete**, Kafka removes old segments once they exceed the configured retention time or retention size. This is the common choice for event logs with a retention window.

With **compact**, Kafka retains the latest value per key during compaction while optionally preserving tombstones for a period to represent key deletions. This policy fits changelogs or topics storing current state by key.

You can combine `delete` and `compact` when you need both compaction and a retention time cap. Do not use `compact` for every event topic: if the business requires a complete history of events, compaction can discard older values sharing the same key.

### retention.ms and retention.bytes

`retention.ms` sets the maximum time logs are retained under the delete policy. `retention.bytes` sets a size limit per partition. When both are configured, Kafka can delete old segments as soon as either retention limit is met. Estimate total storage based on partition count, write rate, and retention period.

Retention is a storage policy, not a guarantee that a message is preserved to the exact millisecond and then immediately purged. Kafka performs deletion at segment granularity and on the broker's cleanup check interval.

## 9. Combining Replication Factor, min.insync.replicas, and acks

Replication factor alone is not enough to describe write durability. Understand the relationship between:

- **replication.factor:** total number of replicas assigned to each partition.
- **min.insync.replicas:** minimum number of replicas that must remain in the ISR for writes with `acks=all` to be accepted.
- **acks:** acknowledgement level requested by the producer.

A common configuration for critical topics:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          required-acks: all
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
                properties:
                  min.insync.replicas: 2
~~~

With a replication factor of 3 and `min.insync.replicas` of 2:

- When all three replicas are in the ISR, `acks=all` requires acknowledgement from all replicas in the ISR.
- When one replica is lost and two remain in the ISR, writes can still succeed after those two in-sync replicas acknowledge.
- When the ISR drops below two, a producer writing with `acks=all` receives an error rather than accepting writes below the minimum threshold.

This configuration prioritizes data durability; when the cluster loses too many replicas, the system may temporarily reject writes. This is the trade-off between availability and durability. Do not lower `min.insync.replicas` merely to eliminate write errors if doing so undermines the data guarantees required by the business.

The default value of `required-acks` can vary between binder versions. In current documentation, the default is `all`; set it explicitly when durability is critical and verify the actual effective configuration of your application version.

## 10. Complete Configuration for Topic orders.events

Example combining partition count, replication factor, topic properties, and partition key:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
          producer:
            partition-count: 6
            partition-key-expression: payload.orderId
      kafka:
        binder:
          brokers: localhost:9092
          auto-create-topics: true
          auto-add-partitions: true
          min-partition-count: 3
          replication-factor: 3
          required-acks: all
        bindings:
          publishOrder-out-0:
            producer:
              topic:
                replication-factor: 3
                properties:
                  min.insync.replicas: 2
                  retention.ms: 604800000
                  cleanup.policy: delete
                  max.message.bytes: 1048576
~~~

In this configuration, the binder can create `orders.events` with at least 6 partitions because the producer's `partition-count` is greater than `min-partition-count`. The topic is created with replication factor 3, `min.insync.replicas` set to 2, and a seven-day maximum log retention under the delete policy. Messages with the same `orderId` are routed by key to preserve ordering within the same partition when producers share the same partitioning strategy.

This example uses `auto-create-topics` and `auto-add-partitions` to illustrate automatic provisioning. In production, organizations may disable both options, create topics via an infrastructure pipeline, and keep binder configuration strictly for connecting. Either way, verify the actual topic after the application starts.

## 11. Managing Existing Topics with Kafka Tools

When topics are managed outside Spring Cloud Stream, you can create a topic using `kafka-topics.sh`:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.events \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete
~~~

Inspect partition and replica assignments:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.events
~~~

Inspect topic config overrides:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe
~~~

Increase partition count:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter \
  --topic orders.events \
  --partitions 9
~~~

The alter partition count command only increases partitions; it cannot reduce already created partitions. After increasing, verify leader/replica distribution and re-evaluate partition keys since key mappings may change.

To modify existing topic configs, you can use `kafka-configs.sh` with the alter operation. Changing the replication factor requires a replica reassignment process; merely changing `replication-factor` in `application.yml` does not move replicas of an existing topic.

## 12. Rules When a Topic Already Exists

Before starting a binding, the binder checks the existing topic and provisioning requirements. Common scenarios:

| Topic State | Binder Configuration | Expected Outcome |
|---|---|---|
| Topic does not exist | `auto-create-topics` enabled | Binder can create the topic per provisioning configuration |
| Topic does not exist | `auto-create-topics` disabled | Binding may fail because the topic has not been created |
| Topic has fewer partitions than required | `auto-add-partitions` disabled | Binder may refuse to start the binding |
| Topic has fewer partitions than required | `auto-add-partitions` enabled | Binder may add partitions |
| Topic has more partitions than required | Any | Binder keeps the existing partition count |
| Topic has a different replication factor than configured | Topic already exists | Requires separate replica management; do not assume the binder changes it |
| Topic has different topic properties than configured | Topic already exists | Inspect and update via admin tools if changes are needed |

Do not rely on provisioning settings as a substitute for drift checks. A topic may exist and the binding may start, yet its retention, cleanup policy, or replica assignment may be wrong. Include a topic configuration check step in your pipeline or operational procedures.

## 13. Planning Partition Count

Partition count should be chosen based on load and processing capacity requirements:

1. Estimate average and peak message rates.
2. Measure processing throughput of a single consumer instance with realistic payloads.
3. Determine the maximum number of consumers that need to run concurrently in one group.
4. Reserve headroom for growth and rebalances.
5. Check broker count, total cluster partitions, and storage resources.
6. Evaluate key-based ordering requirements before increasing partitions.

For example, if one consumer steadily processes 500 messages/second and the system needs around 2,000 messages/second, four partitions can be a starting point to run four consumers in parallel. This is only an initial estimate; actual throughput also depends on key distribution, I/O latency, batching, producer throughput, brokers, and consumer concurrency.

Avoid creating too many partitions before they are needed. Each partition carries metadata, log segments, replicas, and processing overhead. Increasing partitions can also alter key-based ordering and increase rebalance work.

## 14. Planning Replication Factor

Replication factor should reflect desired fault tolerance and broker topology:

- RF=1 has no follower replicas; losing the broker holding the leader can make the partition unavailable until the broker recovers.
- RF=2 provides one additional copy, though tolerance to simultaneous failures and ISR policy must be carefully weighed.
- RF=3 typically allows placing the leader and two followers on separate brokers, a common balance between durability and cost.

A replication factor of 3 roughly triples storage usage compared to a single copy, excluding segment and metadata overhead. For many topics or high-volume streams, calculate total storage based on partition count, retention, and replication factor.

Replicas should be spread across appropriate brokers and failure domains. If all brokers reside in the same rack or failure zone, a high replication factor still cannot protect against a rack- or zone-level outage. Use rack awareness and reassignment procedures aligned with your infrastructure.

## 15. Changing Partitions and Replicas in Production

Before modifying an existing topic:

- Check consumer group lag and identify a safe window for the change.
- Identify producers using partition keys or custom partitioners.
- Assess whether increasing partitions will shift a key to another partition and break ordering.
- Check broker capacity, replica placement, and network load during reassignment.
- Identify impacts on Kafka Streams state stores or applications relying on partition count.
- Perform the change in a staging/test environment first, verifying leaders/ISR and throughput.
- Record before/after configurations and prepare a rollback or compensation plan.

Kafka allows increasing partition counts but not decreasing them via normal operations. Changing the replication factor requires redistributing replicas; this process can consume significant bandwidth and I/O. Do not run bulk reassignments when the cluster is resource-constrained or has under-replicated partitions.

## 16. Verifying Configuration After Provisioning

After the application creates or connects to a topic, verify:

- The topic exists with the exact name and expected partition count.
- Each partition's replication factor matches requirements.
- Leaders and followers are sensibly distributed across brokers.
- ISR count meets `min.insync.replicas`.
- Topic configs such as `cleanup.policy`, `retention.ms`, and `max.message.bytes` have the expected values.
- Producers actually use the intended `acks` and partition key.
- Consumer groups can receive partitions and lag stays within thresholds.

Record desired configurations as IaC or topic manifests so they can be compared against actual state. Do not rely solely on successful application startup logs; a binder starting cleanly does not guarantee every topic property matches the design.

## 17. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Binding fails to start because topic does not exist | `auto-create-topics` disabled and topic not provisioned | Create topic via infrastructure or enable controlled provisioning |
| Binder reports insufficient partitions | Existing topic has fewer partitions than required and `auto-add-partitions` is off | Increase partitions with a plan or enable `auto-add-partitions` |
| Topic created with low replication factor | Binder used broker default replication factor or different version behavior | Set `replication-factor` explicitly and check binder version |
| Producer fails with `NotEnoughReplicas` | ISR fell below `min.insync.replicas` while using `acks=all` | Restore replicas, inspect brokers and ISR; do not arbitrarily lower thresholds |
| Topic properties do not change after deploy | Topic already exists; map only applies during provisioning | Update via Kafka Admin API, `kafka-configs`, or operator |
| Messages with same key switch partitions after topic expansion | Partition count changed the key mapping algorithm | Plan migration and handle per-aggregate ordering |
| Adding consumers does not increase throughput | Low partition count or skewed key distribution | Measure partition lag and key distribution; adjust design |

## 18. Pre-Release Checklist

- Partition count is determined by throughput, concurrency, and ordering requirements.
- Replication factor matches broker count and failure domains.
- `min.insync.replicas` and producer `acks` are configured for desired durability.
- Binder-wide `min-partition-count` is distinguished from per-producer-binding `partition-count`.
- Whether `auto-create-topics` and `auto-add-partitions` are allowed in the environment is confirmed.
- Topic properties are configured in the right scope and expected to apply only during provisioning.
- Existing topics have been inspected; `application.yml` is not assumed to alter existing replica assignments or configs.
- Plans are in place for partition expansion, replica reassignment, and key-ordering impact.
- Post-deployment steps exist to describe topics, check ISR, and verify topic configs.
- Desired configurations are stored in pipelines or infrastructure management tools.

The Kafka Binder allows configuring topics at both the binder and individual binding levels, enabling applications to request partition counts, replication factors, and topic properties tailored to each event stream. Clearly distinguish provisioning configuration from existing topic state, combine replication factor with `min.insync.replicas` and producer `acks`, and assess how increasing partitions affects key ordering. Inspecting actual topics after deployment ensures that application configuration, brokers, and business requirements remain consistent.

## References

- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Apache Kafka — Topic Configs](https://kafka.apache.org/44/configuration/topic-configs/)

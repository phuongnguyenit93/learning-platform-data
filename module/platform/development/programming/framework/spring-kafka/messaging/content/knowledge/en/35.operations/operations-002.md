# Checking Topics and Partitions

In Kafka operations, a topic may still exist while the messaging flow is failing: a partition has no leader, a replica falls behind the leader, ISR shrinks, leader distribution is skewed, or a consumer group cannot read data. Therefore, checking a topic does not stop at confirming the topic name exists in the cluster. You must inspect partition structure, replica state, topic configuration, access permissions, and consumer group progress.

With Spring Kafka, an application can use Kafka `AdminClient` to query topic metadata and configuration. In daily operations, Kafka CLI commands and broker dashboards are also useful to cross-check results. This lesson walks through checking from topic existence down to partition health, offsets, and consumer groups, while explaining the warning signs that require action.

This lesson belongs to the **Operations** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on inspecting topics and partitions to keep event send/receive flows running reliably.

## Learning Outcomes

After this lesson, you can:

- Check whether a topic exists in a Kafka cluster.
- Read partition count, leader, replicas, ISR, and offline replicas.
- Distinguish replication factor from partition count.
- Identify leaderless partitions and under-replicated partitions.
- Read topic configurations such as retention, cleanup policy, and min ISR.
- Use Kafka AdminClient in Java to describe topics and partitions.
- Use Kafka CLI to inspect topics, configs, and consumer groups.
- Check consumer groups, committed offsets, and lag.
- Understand how increasing partitions impacts key distribution and ordering.
- Build a checklist and runbook for inspecting topics/partitions in production.

## 1. Topics and partitions in operations

A topic is the logical name of a record stream. Kafka divides a topic into partitions to store logs and distribute load. Each partition is an independently ordered log with monotonically increasing offsets as records are written.

For example, topic `orders.created` has three partitions:

~~~text
orders.created
├── partition 0: offset 0, 1, 2, 3, ...
├── partition 1: offset 0, 1, 2, 3, ...
└── partition 2: offset 0, 1, 2, 3, ...
~~~

When inspecting a topic, determine at minimum:

- Whether the topic exists with the exact expected name.
- How many partitions it has.
- Which broker is the leader for each partition.
- Which brokers hold replicas.
- Which replicas are currently in the ISR (in-sync replicas).
- Whether any replicas are offline.
- Whether retention, cleanup, and min ISR configurations meet requirements.
- Whether consumer groups are assigned partitions and keeping up with data.

A topic can exist yet be unavailable to serve traffic if a partition has no leader. A partition can also still have a leader while replication is degraded because ISR is smaller than the replication factor.

## 2. Distinguishing partition count and replication factor

Two settings that are often confused:

| Setting | Meaning | Primary impact |
|---|---|---|
| Partition count | Number of log partitions in the topic | Parallelism, record distribution, and consumer group concurrency ceiling. |
| Replication factor | Number of replicas per partition | Broker fault tolerance and data durability. |

For example, a topic with 6 partitions and replication factor 3 means each partition has one leader and two follower replicas, provided the cluster has enough brokers and assignments are properly placed.

Increasing partition count can increase parallelism, but it does not automatically increase the replication factor. Increasing the replication factor requires a replica reassignment procedure or an appropriate admin tool; simply running a command to add partitions does not create additional copies of data.

Partition count also cannot be reduced directly via a standard alter operation. If fewer partitions are needed, you typically must create a new topic and migrate data according to a plan.

## 3. Leader, replicas, and ISR

Each partition has one leader that handles produce requests and serves fetches under Kafka's replication model. Follower replicas replicate data from the leader. The ISR is the set of replicas currently caught up with the leader according to broker criteria.

Example:

~~~text
Partition 0
  Leader: broker 1
  Replicas: broker 1, broker 2, broker 3
  ISR:      broker 1, broker 2, broker 3

Partition 1
  Leader: broker 2
  Replicas: broker 1, broker 2, broker 3
  ISR:      broker 2, broker 3
~~~

Partition 0 has all three replicas in the ISR. Partition 1 has one replica missing from the ISR; data can still be read/written through the leader, but fault tolerance is reduced.

If a leader is lost, Kafka can elect a new leader from the ISR. If no eligible replica remains in the ISR, the partition can become unavailable, unless the cluster is configured to allow unclean leader election with the trade-off of potential data loss.

Do not equate the replicas list with the ISR. Replicas describe where the partition is configured to be stored; ISR describes which replicas are currently in sync according to broker state.

## 4. How to inspect topics with Kafka CLI

Basic command:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --list
~~~

Describe a topic:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --describe --topic orders.created
~~~

The output typically shows:

- Topic name.
- Partition count.
- Replication factor.
- Partition ID.
- Leader broker ID.
- Replica broker IDs.
- ISR broker IDs.

Illustrative example output:

~~~text
Topic: orders.created  PartitionCount: 3  ReplicationFactor: 3
Topic: orders.created  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders.created  Partition: 1  Leader: 2  Replicas: 1,2,3  Isr: 2,3
Topic: orders.created  Partition: 2  Leader: 3  Replicas: 1,2,3  Isr: 1,2,3
~~~

In this example, partition 1 has an ISR containing only brokers 2 and 3, even though the replication factor is 3. You should inspect broker 1, replication logs, and networking to find the cause.

On Windows, the script may be named `kafka-topics.bat`. Depending on the installation, use the file in `bin/windows` and keep the same arguments.

## 5. Checking topic existence and handling missing topics

A topic may be missing from the list because:

- The topic has not been created yet.
- The name or cluster/bootstrap server is wrong.
- The principal lacks list/describe permissions.
- The topic was just deleted or is undergoing metadata changes.
- The tool is connected to the wrong environment.

Do not immediately create the topic when it cannot be found. First verify the cluster, topic name, ACLs, and provisioning workflow. If auto topic creation is enabled, a producer or consumer using a misspelled name can accidentally trigger creating an unintended topic with default settings.

In production, topics should be provisioned via IaC, Kafka AdminClient, or a controlled governance process covering partition count, replication factor, retention, and ACLs. Automatic topic creation from runtime requests needs strict limits and validation.

## 6. Inspecting topic configuration

Use `kafka-configs` to view topic configuration:

~~~bash
kafka-configs.sh --bootstrap-server kafka-1:9092 --entity-type topics --entity-name orders.created --describe
~~~

Key configurations include:

| Config | Operational meaning |
|---|---|
| `retention.ms` | Log retention duration by record age, under the delete cleanup policy. |
| `retention.bytes` | Log size limit per topic/partition configuration. |
| `cleanup.policy` | `delete`, `compact`, or a combination depending on version/configuration. |
| `min.insync.replicas` | Minimum number of synchronized replicas required for producers using `acks=all` to succeed. |
| `segment.bytes` | Log segment size before rolling under configured conditions. |
| `max.message.bytes` | Maximum record batch size accepted by the topic, to be cross-checked with broker/producer limits. |

Effective configuration can come from topic overrides or broker defaults. When checking, inspect both the config source and the effective value. Not every config is displayed identically across all Kafka versions.

For compacted topics, retention and cleanup semantics differ from standard delete topics. Do not mechanically assume old records will be deleted strictly by retention.ms when cleanup policy is compact.

## 7. Understanding under-replicated and offline partitions

Two warning signs to watch closely:

- **Under-replicated partition**: the number of replicas in the ISR is smaller than the configured replica count.
- **Offline partition**: a partition currently has no available leader to serve requests.

For example, if the replication factor is 3 but the ISR only has 2 replicas, the partition is under-replicated. This reduces fault tolerance; if another replica fails, the partition can lose availability.

If a partition has no leader, producers/consumers may see errors such as leader unavailable or request timeout. Check broker logs, broker status, disk, network, controller/quorum, and replica synchronization.

Do not manually alter ISR or force replicas into the ISR by editing metadata. Brokers manage ISR automatically based on sync status; fix the underlying cause making the follower lag behind.

## 8. Checking leader distribution across brokers

If many partition leaders are concentrated on a single broker, that broker may carry noticeably heavier produce/fetch load than the others.

Look at leader distribution:

| Broker | Leader partition count | Observation |
|---|---:|---|
| broker 1 | 18 | May be carrying high leader load. |
| broker 2 | 17 | Relatively balanced. |
| broker 3 | 5 | May indicate leader imbalance. |

This table only illustrates how to read the counts, not fixed thresholds. Cross-check bytes in/out, request rate, disk throughput, CPU, and network. Equal leader counts do not guarantee equal load if partitions have uneven traffic.

Preferred replica election or reassignment can help balance leaders/replicas, but must follow operational procedures and impact assessment. Do not trigger production reassignments based solely on leader counts.

## 9. Checking partitions with Kafka AdminClient

Java applications can use AdminClient to fetch topic metadata. Example creating an AdminClient with bootstrap server configuration:

~~~java
Properties properties = new Properties();
properties.put(
        AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
        "kafka-1:9092,kafka-2:9092"
);

try (AdminClient admin = AdminClient.create(properties)) {
    // Perform metadata queries here.
}
~~~

In a Spring Boot application, reuse managed security settings and bootstrap servers. Do not create a new AdminClient per HTTP request; manage its lifecycle as a shared bean or service and close the client on application shutdown.

If the cluster uses SASL/TLS, AdminClient must also receive the matching security properties, and its principal needs describe/list permissions. Do not grant broad admin credentials to endpoints that only read metadata.

## 10. Listing topics and describing partitions with AdminClient

Example checking topic existence and fetching partition descriptions:

~~~java
public TopicDescription describeTopic(
        AdminClient admin,
        String topicName) throws Exception {

    Set<String> topicNames = admin.listTopics()
            .names()
            .get(10, TimeUnit.SECONDS);

    if (!topicNames.contains(topicName)) {
        throw new IllegalArgumentException(
                "Topic does not exist: " + topicName
        );
    }

    return admin.describeTopics(List.of(topicName))
            .values()
            .get(topicName)
            .get(10, TimeUnit.SECONDS);
}
~~~

Reading partition details:

~~~java
TopicDescription description =
        describeTopic(admin, "orders.created");

for (TopicPartitionInfo partition : description.partitions()) {
    Node leader = partition.leader();

    String leaderId = leader == null
            ? "NO_LEADER"
            : Integer.toString(leader.id());

    List<Integer> replicaIds = partition.replicas().stream()
            .map(Node::id)
            .toList();

    List<Integer> isrIds = partition.isr().stream()
            .map(Node::id)
            .toList();

    List<Integer> offlineIds = partition.offlineReplicas().stream()
            .map(Node::id)
            .toList();

    log.info(
            "topic={}, partition={}, leader={}, replicas={}, isr={}, offline={}",
            description.name(),
            partition.partition(),
            leaderId,
            replicaIds,
            isrIds,
            offlineIds
    );
}
~~~

This example uses `List.toList()`, which requires Java 16 or newer. For older Java versions, replace it with `collect(Collectors.toList())`.

In production checks, do more than log details. Compute indicators such as:

- Partitions without a leader.
- Partitions where ISR is smaller than replica count.
- Partitions with offline replicas.
- Leader count per broker.
- Topics whose partition count differs from expected configuration.

If an AdminClient request times out or hits an authorization error, distinguish a query failure from the topic genuinely not existing.

## 11. Reading topic configs with AdminClient

You can use `describeConfigs` to read topic configuration:

~~~java
ConfigResource resource = new ConfigResource(
        ConfigResource.Type.TOPIC,
        "orders.created"
);

Map<ConfigResource, Config> configs = admin
        .describeConfigs(List.of(resource))
        .all()
        .get(10, TimeUnit.SECONDS);

Config config = configs.get(resource);

for (ConfigEntry entry : config.entries()) {
    if (!entry.isSensitive()) {
        log.info(
                "config={}, value={}, source={}, default={}",
                entry.name(),
                entry.value(),
                entry.source(),
                entry.isDefault()
        );
    }
}
~~~

Do not log sensitive config values. Some configs may be masked or return null depending on the broker and permissions.

Config read permissions can differ from metadata describe permissions. If metadata succeeds but describeConfigs is denied, check the corresponding ACL operation instead of concluding the topic is broken.

## 12. Checking consumer groups and partition assignment

A healthy topic does not guarantee consumers are reading cleanly. Check the consumer group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 --describe --group orders-fulfillment
~~~

The output typically includes:

- Topic and partition.
- Current committed offset.
- Log end offset.
- Lag.
- Consumer ID, host, and client ID if a member is active.

Example:

~~~text
GROUP                TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orders-fulfillment   orders.created  0          1200            1200            0
orders-fulfillment   orders.created  1          980             1100            120
orders-fulfillment   orders.created  2          1500            1500            0
~~~

Partition 1 has a lag of 120 records. Inspect the consumer assigned to that partition, processing speed, listener errors, retries, and downstream dependencies.

If the group does not appear or has no committed offset, check the group ID, consumer status, and `auto.offset.reset` policy. The reset policy only applies when the group has no valid offset yet; changing it will not rewind a group that has already committed offsets.

## 13. How partition count limits consumer parallelism

In a standard consumer group, each partition is assigned to at most one consumer member at a time. If a topic has 4 partitions and the group has 8 consumers, at most 4 consumers receive partitions for that topic; the remaining consumers sit idle.

This means:

- Increasing concurrency beyond the partition count does not increase processing parallelism for the topic.
- Increasing partitions can expand the number of consumers that can be assigned partitions.
- More partitions also increase metadata, segment files, replication overhead, and operational cost.
- A hot partition can still be a bottleneck even while other partitions are idle.

Choose partition count based on throughput, expected consumers, ordering, log size, replication, and broker capacity. Do not increase partitions merely to raise a concurrency number.

## 14. Increasing partitions can affect key-based ordering

With the default partitioner, keyed records are typically mapped to a partition based on a hash of the key and the current partition count. When the partition count increases, a key may map to a different partition for newly produced records.

Example before increasing partitions:

~~~text
order-1001 -> partition 1
~~~

After increasing partitions:

~~~text
order-1001 -> partition 4
~~~

Old records remain on partition 1; new records can land on partition 4. Kafka does not move old records and provides no global ordering across two partitions. Therefore, increasing partitions can break the assumption that all events for the same key always go to the same partition over the topic's lifetime.

Before increasing partitions, assess ordering requirements. If per-aggregate ordering must be preserved, consider a stable custom partitioner, a controlled topic migration, or event version/sequence numbers so consumers can detect ordering.

## 15. Increasing partitions with Kafka CLI

You can increase the partition count using:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 --alter --topic orders.created --partitions 6
~~~

This increases the partition count to 6 if the topic currently has fewer than 6. Standard alter commands cannot reduce partition count.

Before running:

1. Confirm the topic is on the right cluster and environment.
2. Check the current partition count.
3. Evaluate key-based ordering and consumer groups.
4. Check broker capacity, replica placement, and quotas.
5. Document the target partition count and reason for change.
6. Plan to monitor consumer rebalances and lag after the change.

After altering, run describe again to verify the partition count and check replica/leader assignments. Adding partitions does not guarantee replication is balanced or that the new partitions have optimal placement.

## 16. Checking replication factor and ISR after an incident

When replication degrades, check:

- Which brokers are offline or recently restarted.
- Whether disks are full, slow, or experiencing I/O errors.
- Whether inter-broker networking has packet loss or high latency.
- Whether follower fetches are lagging behind.
- Whether log directories have errors.
- Whether brokers are handling reassignment or recovery.
- Whether ISR recovers once followers catch up.

If producers use `acks=all`, acknowledgement requirements relate to ISR and `min.insync.replicas`. For instance, with replication factor 3 and min ISR 2: producers can continue writing with ISR 2 when configuration and state permit; if ISR drops below 2, produces may be rejected. Always inspect the exact topic/broker configs and producer settings.

Do not lower min.insync.replicas or enable unclean leader election just to clear temporary errors. Such changes directly alter the availability-versus-durability trade-off and can increase the risk of data loss.

## 17. Checking ACLs and topic describe permissions

An operational tool may fail to see a topic due to missing permissions rather than the topic not existing.

Commonly required permissions include:

- List topics or cluster metadata.
- Describe topic.
- Describe topic configs.
- Read consumer group offsets.
- Describe consumer group.
- Alter topic or configs if performing administrative tasks.

Use a read-only principal for dashboards/health checks that only need visibility. Separate principals with alter/create/delete rights from normal producer/consumer services.

For Kafka CLI with SASL/TLS, pass a client config file via `--command-config`:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9093 --command-config client.properties --describe --topic orders.created
~~~

Protect config files like secrets; never pass passwords inline in shell commands saved in history or CI logs.

## 18. Metrics and alerts to monitor

Topics and partitions must be monitored continuously, not only inspected manually during incidents.

| Metric or signal | Meaning | Action when abnormal |
|---|---|---|
| Offline partitions | Partition has no leader | Check brokers, controller/quorum, disks, and network. |
| Under-replicated partitions | ISR is smaller than replica count | Check follower lag and broker health. |
| ISR shrink/expand rate | Replicas repeatedly leaving/rejoining ISR | Investigate network/disk/CPU instability. |
| Leader count per broker | Leader distribution | Evaluate load imbalance. |
| Request error/timeout | Clients failing API requests | Cross-check brokers, network, ACLs, and client logs. |
| Consumer lag per partition | Consumer falling behind | Check processing rate, key skew, and assignment. |
| Disk usage/log dir health | Broker storage capacity | Trim by retention and plan storage expansion. |
| Produce/fetch bytes rate | Actual traffic on topic/broker | Compare against capacity and traffic patterns. |

Alerts should be based on thresholds and sustained duration. A brief ISR shrink during maintenance differs from prolonged under-replication. Tie alerts to specific runbooks and owners.

## 19. Topic and partition inspection runbook

When producer timeouts or rising consumer lag are reported, follow this sequence:

1. Confirm the bootstrap servers and cluster match the right environment.
2. Verify that the topic exists and its name is exact.
3. Run describe topic to inspect partition count, leaders, replicas, and ISR.
4. Identify any leaderless or under-replicated partitions.
5. Inspect affected brokers, disks, networking, and logs.
6. Read topic configs: retention, cleanup policy, min ISR, and message size limits.
7. Check consumer group assignment, current offset, log end offset, and lag.
8. Cross-check listener errors, retries, DLT, and downstream dependencies.
9. Check ACLs if metadata or operations are denied.
10. Change partitions/configs only after evaluating ordering, durability, and capacity.
11. Re-verify metadata and consumer behavior after changes.
12. Record root cause, timestamps, actions taken, and recovery outcomes.

Do not delete and recreate a topic to "reset" an incident without a data plan. Deleting a topic can cause data loss, change topic identity/offsets, and impact every consumer.

## 20. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only that the topic exists | Misses leaderless partitions or shrinking ISR | Inspect every partition and replica state. |
| Confusing partition count with replication factor | Scales the wrong parameter for a bottleneck | Clarify whether parallelism or durability is needed. |
| Looking at replicas and assuming all are healthy | Overlooks followers outside the ISR | Compare replicas with ISR and offline replicas. |
| Recreating a topic that fails to list | Can create the wrong topic or mask ACL/cluster errors | Verify bootstrap, permissions, and name first. |
| Increasing partitions without checking key ordering | Events with the same key can switch partitions | Assess ordering and migration strategy. |
| Lowering min ISR so producers keep writing | Reduces durability guarantees | Change only after risk review and approval. |
| Granting admin rights to health checks | Over-exposes privileges unnecessarily | Use a read-only principal. |
| Watching only total consumer lag | Misses a single hot partition | Monitor lag per partition. |
| Auto-creating topics with default configs | Wrong partition count/retention/replication | Provision topics in a controlled manner. |

## 21. Capstone exercise: inspecting topic orders.created

Suppose a cluster has three brokers and a topic `orders.created`. Build a topic inspection tool for the operations team.

Requirements:

1. Connect AdminClient to the cluster using a principal with describe-only permissions.
2. Verify that the topic exists.
3. Read partition count and replication factor.
4. Print leader, replicas, ISR, and offline replicas for each partition.
5. Count partitions with no leader.
6. Count under-replicated partitions.
7. Count offline replicas and leader distribution per broker.
8. Read retention.ms, cleanup.policy, and min.insync.replicas.
9. Inspect consumer group `orders-fulfillment` and per-partition lag.
10. Cross-check producer acks against min ISR.
11. Test missing describe permissions and distinguish an authorization failure from a non-existent topic.
12. Create a test topic, increase its partition count, and verify metadata after the change.
13. Document the impact of partition expansion on key distribution.
14. Export health check results into a report with status HEALTHY, DEGRADED, or UNAVAILABLE.
15. Write a runbook for offline partitions and under-replicated partitions.

The exercise is complete when the tool can identify missing topics, leaderless partitions, out-of-sync replicas, lagging consumer groups, and configs deviating from baseline.

## 22. Learning sequence and completion criteria

| Stage | Core focus | Self-check criteria |
|---|---|---|
| 1. Topic model | Topics and partitions | Explain log/offset per partition. |
| 2. Replica model | Leader, replicas, ISR | Distinguish configured replicas from in-sync replicas. |
| 3. CLI | kafka-topics and kafka-configs | Describe topics and read configs. |
| 4. AdminClient | listTopics, describeTopics, describeConfigs | Query metadata from Java. |
| 5. Health | Offline and under-replicated partitions | Detect degraded partitions. |
| 6. Consumer group | Assignment, committed offset, and lag | Locate partitions where consumers fall behind. |
| 7. Partition planning | Count, concurrency, and key distribution | Assess impact when increasing partitions. |
| 8. Durability | Replication factor, acks, and min ISR | Understand trade-offs when ISR shrinks. |
| 9. Security | ACLs and command config | Use least privilege for inspection. |
| 10. Operations | Metrics and runbooks | Diagnose issues and verify after changes. |

This lesson is complete when you can inspect topics via CLI and AdminClient, explain each partition's state, identify under-replication/offline leaders, inspect consumer lag, and evaluate safety before changing partition count.

Inspecting topics and partitions is foundational to operating Kafka. Examine leaders, replicas, ISR, configs, and consumer groups together; a topic with a valid name is not necessarily healthy. Every partition or durability change must be evaluated against ordering, load, and fault tolerance before being applied.


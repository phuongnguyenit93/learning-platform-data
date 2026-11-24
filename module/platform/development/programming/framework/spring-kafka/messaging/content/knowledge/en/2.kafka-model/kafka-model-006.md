# Replication and availability

## 1. Why does Kafka need replication?

Kafka stores data in partitions. If a partition only has a single copy and the broker holding that partition fails, the partition cannot serve reads or writes until the broker recovers. This creates a single point of failure and can disrupt the entire event stream.

**Replication** is the mechanism of maintaining multiple copies of a partition across different brokers. When a broker fails, Kafka can elect an eligible remaining replica as the new leader so the partition keeps operating. Replication thus contributes to higher availability and data durability.

In the Spring Kafka Messaging module, producers send events through `KafkaTemplate` and consumers receive events through `@KafkaListener`. Spring Kafka APIs help the application communicate with the Kafka cluster; broker-side data fault tolerance depends on the replication factor, ISR, producer settings, and cluster deployment.

## 2. Leader and follower replicas

Each partition has one or more replicas. At any given time, one replica acts as the **leader**; the remaining replicas are **followers**.

- Producers send records to the target partition's leader.
- Consumers normally read records from the leader.
- Followers actively fetch data from the leader to keep their log copies up to date.
- When the leader fails, Kafka coordinates electing an eligible replica as the new leader.

For example, topic `orders` has partition `orders-0` with a replication factor of 3:

```text
                    write record
Producer ------------------------------> Broker A
                                         Leader orders-0
                                              |
                             follower fetch   |   follower fetch
                                  +-----------+-----------+
                                  |                       |
                                  v                       v
                              Broker B                Broker C
                              Follower                Follower
```

Three replicas are three copies of the **same partition**, not three different partitions. Brokers A, B, and C can simultaneously host replicas of other partitions; Kafka distributes leaders and replicas to balance load.

### Replication factor

The replication factor (RF) is the configured number of replicas for each partition, including the leader. For example:

| Replication factor | Copies per partition | Operational meaning |
|---:|---:|---|
| 1 | 1 | No backup copy; failure of the broker holding the replica can make the partition unavailable |
| 2 | 2 | One backup copy; lower fault tolerance and redundancy than RF=3 |
| 3 | 3 | Can retain another copy when one broker holding a replica fails, given appropriate ISR conditions and write settings |

RF must be less than or equal to the number of brokers eligible to host replicas. RF=3 does not mean every record is written three times by the producer; the producer sends only to the leader, and Kafka replicates the record to followers.

## 3. ISR and eligibility for leader election

**ISR (In-Sync Replicas)** is the set of replicas keeping up with the leader according to Kafka's synchronization criteria. The ISR always includes the current leader. Followers must fetch data frequently enough to remain in this set; a replica that falls too far behind can be removed from the ISR and re-added once it catches up.

Suppose a partition has RF=3:

| Replica | Broker | Status | In ISR? |
|---|---|---|---|
| Replica 0 | A | Leader | Yes |
| Replica 1 | B | Follower, caught up with leader | Yes |
| Replica 2 | C | Follower, lagging behind | May have been removed |

If the current ISR is `{A, B}`, Kafka considers A and B sufficiently caught-up copies to serve writes and leader election. Replica C outside the ISR is not treated as an equivalently safe copy at that moment.

The ISR changes depending on broker status and synchronization speed. Therefore, do not look at RF alone to conclude how many safe copies a partition currently has. Monitor actual replica counts, ISR, and leader status as well.

### High watermark

Kafka uses the **high watermark** to mark the boundary of data synchronized across replicas in the ISR. Normal consumers can only read records that have crossed the high watermark visibility threshold; this prevents a standard consumer from reading a record that existed only on the leader and then disappeared if the leader failed.

The high watermark is not the consumer's committed offset. The high watermark reflects a partition's replication progress; the committed offset reflects the reading progress saved by a consumer group. The two concepts serve different purposes.

## 4. Leader election and broker failure handling

When the broker holding the leader disconnects or stops, Kafka's controller detects the failure and coordinates electing a new leader. An active replica in the ISR can be elected as the new leader. After the role transition, producers and consumers continue interacting with the new leader using updated cluster metadata.

Example with RF=3 and initial ISR `{A, B, C}`:

1. Broker A holds the partition leader.
2. Broker A fails.
3. Kafka elects B or C, which remains in the ISR, as the new leader.
4. Clients refresh metadata and send requests to the new leader.
5. When A recovers, A's replica resynchronizes and can rejoin the ISR.

Election can cause a brief interruption. Applications must configure appropriate timeouts, retries, and error handling; never assume every send succeeds instantaneously during broker changes.

### Unclean leader election

Under normal conditions, Kafka prefers electing a new leader from the ISR. The `unclean.leader.election.enable` setting controls whether an out-of-ISR replica may be elected when no ISR replica is available.

- If unclean election is disabled, the partition may become temporarily unavailable when no ISR replica can serve as leader. This prioritizes preserving already-synchronized data.
- If unclean election is enabled, a lagging replica may be elected to restore availability. Records that had not yet replicated to that replica can be lost.

This is a trade-off between availability and risk of data loss. For critical business flows, understand the consequences before enabling unclean election; do not enable it merely to shorten partition offline time.

## 5. Combining replication with acks and min.insync.replicas

Replication factor determines how many replicas are maintained. The producer's `acks` configuration determines the acknowledgment level required on writes; `min.insync.replicas` sets the minimum ISR threshold for a broker to accept a write request with `acks=all`.

### Acks modes

| Value | When does the producer receive acknowledgment? | Trade-off |
|---|---|---|
| `0` | Does not wait for broker acknowledgment | Low latency, but the producer does not know whether the broker received the record |
| `1` | Leader acknowledges after writing the record to its local log | Faster; records can be lost if the leader fails before followers replicate |
| `all` (`-1`) | Leader waits for replicas currently in the ISR to acknowledge per replication protocol | Higher guarantee; writes can be rejected if ISR drops below the minimum threshold |

`acks=all` does not automatically wait for the entire RF. It waits for replicas currently in the ISR. If RF=3 yet only one replica remains in the ISR, `acks=all` alone can still allow writes through that single replica. That is why combining it with `min.insync.replicas` is essential.

### Example with RF=3 and min.insync.replicas=2

Suppose a topic has RF=3 and `min.insync.replicas=2`, and the producer uses `acks=all`:

- When the ISR has 3 replicas, the broker can accept writes and await acknowledgment from the replicas in the ISR.
- When one replica fails and 2 remain in the ISR, the broker can still accept writes. The cluster retains tolerance depending on leader and replica state, though a further drop would breach the threshold.
- When only 1 replica remains in the ISR, the broker rejects `acks=all` writes because the threshold of 2 is not met. The application receives an error instead of silently writing with lower redundancy than configured.

Thus, RF=3 combined with `min.insync.replicas=2` is commonly used to keep writing when one replica is lost while still requiring at least two copies in the ISR to participate in acknowledgment. Actual behavior also depends on which brokers/racks hold replicas, the ISR at write time, and leader election status.

## 6. Configuring replication for a topic

The replication factor is set when creating a topic or during replica reassignment procedures. Example creating topic `orders` with 6 partitions and RF=3:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 6 \
  --replication-factor 3 \
  --config min.insync.replicas=2
```

This command requires a cluster with at least three brokers able to host replicas. Each partition will have three replicas; partition leaders are distributed to avoid concentrating all load on a single broker.

You can inspect leaders, replicas, and ISR with:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Partition descriptions typically show `Leader`, `Replicas`, and `Isr` fields. `Replicas` lists brokers assigned to hold copies; `Isr` lists replicas currently in sync; `Leader` identifies the broker currently serving that partition.

Common broker/topic settings:

```properties
# Broker configuration
unclean.leader.election.enable=false

# Broker default for auto-created topics (if auto-create is enabled)
default.replication.factor=3

# Can be set at the topic level to require at least two replicas in the ISR when writing with acks=all
min.insync.replicas=2
```

`default.replication.factor` is the default for auto-created topics; it does not retroactively change the replication factor of existing topics. For important topics, proactively create topics and verify assignments rather than relying on auto-creation.

## 7. Producer configuration in Spring Kafka

A Spring Boot application can instruct the producer to use `acks=all` and enable idempotence as follows:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
```

`acks=all` asks the broker to acknowledge via the ISR mechanism. `enable.idempotence` helps the producer avoid creating duplicate records due to retries within Kafka's producer guarantees. Idempotence configuration must align with producer constraints such as `acks`, `retries`, and maximum in-flight requests per connection; modern Kafka clients validate these constraints automatically.

`min.insync.replicas` is a broker/topic-side setting, not something configured only inside the Spring producer. Both sides must align: the producer requests `acks=all`, and the topic/broker sets an appropriate ISR threshold. Setting `acks=all` without a minimum threshold can leave write redundancy lower than expected when the ISR shrinks.

Example sending an event:

```java
@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

The application must observe the completion result of the `CompletableFuture`. When the ISR falls below `min.insync.replicas`, the broker can return errors like `NotEnoughReplicas` or `NotEnoughReplicasAfterAppend`; the business layer must classify errors, retry within bounds, and record status for follow-up handling. Never catch and swallow errors, as doing so turns infrastructure failures into silent event loss at the application layer.

## 8. Replica placement and fault tolerance by rack/availability zone

Replication only helps when copies reside in independent failure domains. If all three replicas of a partition sit on the same physical host, rack, or availability zone that fails together, RF=3 still cannot protect the partition.

Kafka supports rack awareness via the `broker.rack` setting. During assignment, Kafka can spread replicas across different racks if the cluster is configured properly and has enough brokers across racks. In cloud environments, you can map racks to availability zones.

Design considerations:

- Every broker must have an accurate, consistent rack/zone identifier.
- Replicas of the same partition should be spread across multiple independent failure domains.
- The number of racks/zones and brokers per rack must suffice for the desired RF.
- Cross-rack network capacity and bandwidth must support replication traffic.
- Verify actual assignments; setting `broker.rack` alone does not automatically rebalance existing topics.

If a system spans only a single availability zone, replication still protects against individual broker or disk failures, but not a zone-wide outage. When regional disaster recovery is required, establish dedicated backup and cross-cluster replication strategies.

## 9. Replication is not backup or exactly-once

Replication maintains live operational copies of the same partition inside a single cluster. It is not an independent backup. If an application writes bad data, deletes a topic, emits erroneous events, or an administrative operation alters data, that mistake affects all replicas. Retention can also expire data across replicas according to configured policies.

Therefore, critical systems still need backup/restore procedures, long-term archival, or cross-cluster replication depending on recovery objectives. Test restores periodically, because having backups you cannot restore within required recovery times fails operational goals.

Replication also does not automatically yield end-to-end exactly-once semantics for business logic. `acks=all` and an idempotent producer improve write reliability; Kafka transactions can provide exactly-once processing guarantees in properly configured Kafka flows. When consumers call external systems such as databases or payment APIs, you still need idempotency, transaction boundaries, or outbox/inbox patterns.

## 10. Monitoring replication health

Operations teams need to monitor signals indicating whether replicas are keeping up and whether partitions remain able to serve traffic.

| Metric/Signal | Meaning | Investigation direction |
|---|---|---|
| Offline partitions | Partition has no available leader | Check brokers, controller, ISR, and network health |
| Under-replicated partitions | Current replica count is below replication factor or not caught up | Check disconnected brokers, disks, network, and replication load |
| Under-min-ISR partitions | Partition has ISR below `min.insync.replicas` | Assess write availability and replica recovery |
| ISR shrink/expand | Replica removed from or re-added to ISR | Find why followers repeatedly lag behind |
| Leader election rate | Frequency of leader elections | Check flaky brokers, restarts, or network issues |
| Produce errors/latency | Producer rejected or writing slowly | Check `acks`, min ISR, timeouts, and broker health |

Beyond metrics, monitor broker logs, disk capacity, read/write throughput, network traffic, and controller status. A persistently lagging follower can signal insufficient broker resources or replication traffic unable to keep pace with write throughput.

## 11. Safe operational practices

When maintaining or upgrading a Kafka cluster, proceed one broker at a time and check partition health after each step. Stopping multiple brokers simultaneously can drop the ISR below the minimum threshold or leave partitions without a leader.

Helpful practices:

1. Choose RF based on broker count, failure domains, and recovery objectives; RF=3 is typically a starting point for production environments with enough brokers.
2. Pair `acks=all` with `min.insync.replicas` to enforce a minimum number of copies during write acknowledgment.
3. Verify zero offline, under-replicated, and under-min-ISR partitions before continuing a rollout.
4. Perform maintenance sequentially, waiting for replicas to catch up and ISR to stabilize before moving to the next broker.
5. Use rack awareness and verify assignments to reduce the risk of a single physical failure taking out multiple replicas at once.
6. Test broker/leader shutdown scenarios in staging; verify producer retries, consumer resumption, and proper application error handling.
7. Maintain separate backup, restore, and disaster recovery plans for long-term retained data.

## 12. Summary

- Each partition has one leader and can have multiple follower replicas; producers write to the leader and followers fetch data to replicate.
- Replication factor is a partition's total replica count, including the leader.
- ISR is the set of replicas keeping up with the leader and underpins safe write acknowledgments and leader elections.
- `acks=all` paired with `min.insync.replicas` enforces a minimum acknowledgment threshold on writes.
- Leader election recovers partitions after broker failures; unclean election can restore availability at the risk of data loss.
- Rack awareness spreads replicas across failure domains; monitoring and sequential maintenance keep the cluster healthy.
- Replication does not replace backups and does not automatically guarantee exactly-once semantics for business work outside Kafka.

When implementing Spring Kafka, treat reliability as a property of the entire pipeline: producers must inspect send outcomes, the Kafka cluster must maintain enough replicas in the ISR, and consumers must handle errors and safe redelivery. Configuring each layer properly keeps the messaging system operating when a broker or infrastructure domain fails.

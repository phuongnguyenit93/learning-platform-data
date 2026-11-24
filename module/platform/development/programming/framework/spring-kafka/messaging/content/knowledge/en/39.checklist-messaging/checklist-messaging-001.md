# Topic Design Checklist

A topic is the storage and event-distribution contract between producers and consumer groups. A well-designed topic clearly answers what data is written to it, who owns the data, which key partitions the records, how long records are retained, what durability guarantees apply, and how to handle consumers that fall behind.

Use this checklist when creating a new topic or reviewing a topic before taking a Spring Kafka flow into production. Configuration numbers must be validated against actual load, broker capacity, and business requirements; there is no single partition count or retention period that fits every system.

## 1. Define the topic's purpose and boundaries

Before choosing partitions or retention, describe the topic's role:

- Does the topic hold events that have occurred, commands requesting an action, or state snapshots?
- Does one topic represent a clear event family/domain stream?
- Which producers are allowed to write, and which consumer groups need to read?
- Do the consumers need the same schema and the same retention policy?
- Does the data need to be separated by sensitivity level, tenant, or retention lifecycle?

Avoid creating topics per message, per request, or per consumer. Multiple consumer groups can read the same topic independently with their own offsets; there is no need to duplicate a topic just because multiple applications are interested in an event.

Split topics when streams have substantive differences in schema, access permissions, retention, load, ordering, or lifecycle. If only the processing logic differs, a single topic with multiple consumer groups is usually easier to manage.

## 2. Name topics consistently

A topic name should indicate the domain, data type, and contract version. For example:

| Name | Purpose |
| --- | --- |
| `orders.events.v1` | Business events about orders |
| `payments.commands.v1` | Commands requesting payment processing |
| `inventory.snapshot.v1` | Inventory state snapshots |
| `orders.events.retry-1000` | Retry topic with delay per the chosen policy |
| `orders.events.dlt` | Dead-letter topic for the orders stream |

Conventions to standardize:

- Use lowercase letters and one consistent separator style, such as dots or hyphens.
- Avoid vague names like `data`, `events`, `topic1`, or names tied to a temporary implementation.
- Do not embed volatile information such as hostname, pod ID, or deployment date in the topic name.
- Name retry/DLT topics after the source topic so they can be traced back to the original stream.
- Check the limits and naming conventions of the Kafka platform in operation.

Some metrics systems normalize dots and underscores in ways that can cause metric name collisions. Therefore, choose an observable convention and check how the exporter displays topic names.

## 3. Finalize the event contract before creating the topic

A topic is only a byte store; producers and consumers still need to agree on the meaning of the key, headers, and value. An event envelope typically has these fields:

| Field | Role |
| --- | --- |
| `eventId` | Stable identifier for deduplication and tracing |
| `eventType` | Event type, for example `OrderPaid` |
| `schemaVersion` | Payload structure version |
| `aggregateId` | Entity identifier that requires ordering |
| `occurredAt` | Business occurrence timestamp |
| `correlationId` | Links steps within a business flow |
| `payload` | Business data of the event |

Choose JSON, Avro, Protobuf, or another format according to your ecosystem. If using Schema Registry, define the compatibility mode and schema registration workflow before producers emit new payloads. Schema changes must be tested against consumers running older versions.

Do not use Kafka headers to replace business fields that consumers need to store long-term. Headers are suited for transport metadata such as trace context, replay source, or DLT information.

## 4. Choose the message key and partition strategy

The key determines which partition a record is routed to by the partitioner. If events of the same aggregate must be read in order, a stable aggregate ID is typically used as the key:

```java
kafkaTemplate.send(
    "orders.events.v1",
    event.orderId(),
    event);
```

With key `orderId`, events for the same order are placed into the same partition when the partition count and partitioner do not change. Kafka maintains record ordering within a single partition; Kafka does not provide global ordering across multiple partitions.

Key checklist:

- Does the key represent the unit that needs ordering, such as `orderId`, `accountId`, or `deviceId`?
- Is the key distribution even, or could a hot key overload a single partition?
- Do keyless events genuinely tolerate distribution not tied to an aggregate?
- Do consumers need sequential processing per key, or can they process in parallel?
- Has partition distribution been tested with realistic data?

Increasing the partition count can change the hash-to-partition result for keys in subsequent publishes. Old events for a key may reside in the old partition while new events go to a different partition. If per-aggregate ordering is a strict requirement, treat the partition count as a long-term decision and plan a separate migration/repartition strategy.

## 5. Estimate the number of partitions

The partition count directly affects parallelism, the number of useful consumers in a group, load distribution, and operational cost. Start from the target throughput and the safe measured throughput on a single partition:

\[P_{base} = \left\lceil \frac{R_{target}}{R_{partition}} \right\rceil\]

Where `R_target` is the target records/second to process and `R_partition` is the throughput/partition verified via load testing with production-like record size, replication, consumer logic, and brokers. Then add headroom for bursts, growth, and rebalances.

For example, if the target load is 1,200 records/second and testing shows a single partition stably handles 300 records/second, the baseline is 4 partitions. If roughly 50% headroom is needed, you might evaluate 6 partitions and re-verify with tests. This is a starting point, not a default number.

Additional checks:

- Maximum consumer/concurrency a group can utilize: does not exceed the number of assigned partitions.
- Total partitions on the cluster and broker operational limits.
- Rebalance time, segment file overhead, open files, and metadata cost.
- Ability to scale consumers independently of producers.
- Degree of skew across keys and partitions.

Do not create hundreds of partitions just for headroom without supporting numbers. Too many partitions increase metadata, file, recovery, and operational overhead, even when throughput does not increase proportionally.

## 6. Choose replication and durability

Replication factor (RF) determines the number of partition copies. For production requiring broker fault tolerance, RF=3 is commonly evaluated with replicas placed across different brokers/racks/availability zones. Local or single-broker test environments typically use RF=1.

A common durability configuration:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
```

And the corresponding topic/broker configuration:

```bash
kafka-topics.sh --bootstrap-server kafka.example.com:9092 \
  --create --topic orders.events.v1 \
  --partitions 6 --replication-factor 3

kafka-configs.sh --bootstrap-server kafka.example.com:9092 \
  --entity-type topics --entity-name orders.events.v1 \
  --alter --add-config min.insync.replicas=2,unclean.leader.election.enable=false
```

Replication factor is chosen when creating the topic via `--replication-factor` (or equivalent provisioning config); `min.insync.replicas` is a topic configuration. `unclean.leader.election.enable` may be managed at the broker or topic level depending on cluster version and policy.

`acks=all` requires the leader to wait for acknowledgements from replicas currently in the ISR; it does not mean every configured replica must respond. `min.insync.replicas=2` sets the minimum ISR threshold for the broker to accept writes with `acks=all`. If ISR drops below the threshold, the producer receives an error instead of accepting a write with lower durability than the policy.

An idempotent producer reduces duplicates caused by producer-level retries under the conditions Kafka supports. It does not replace business idempotency when consumers call databases or HTTP services.

Durability checklist:

- Is RF appropriate for the number of brokers and fault-tolerance requirements?
- Are replicas distributed across racks/AZs according to failure domains?
- Is `min.insync.replicas` compatible with the producer's `acks`?
- Are under-replicated partitions and ISR shrinks being monitored?
- Is there a procedure for broker loss and when ISR drops below the threshold?

## 7. Choose retention and cleanup policy

Retention must derive from replay, investigation, compliance, and storage capacity needs. Two common cleanup policies are:

| Policy | Use when |
| --- | --- |
| `delete` | You need to keep event history for a period and then delete old segments |
| `compact` | You need to keep the latest value per key, suitable for changelogs or state topics |
| `compact,delete` | You need key-based compaction while still bounding data age |

Example event history topic configuration:

```properties
cleanup.policy=delete
retention.ms=604800000
segment.bytes=1073741824
```

The example above retains data under a seven-day policy. With a compacted topic, older records with the same key may be removed after compaction; tombstones represent key deletion and have their own retention window. Do not use compaction if consumers need to replay the entire event history.

Rough storage estimation:

\[Storage \approx IngressBytesPerSecond \times RetentionSeconds \times ReplicationFactor\]

For example, 100 records/second, 1 KiB average size, and seven-day retention produce about 57.7 GiB of data per replica before accounting for compression and overhead; RF=3 requires roughly 173 GiB of total replica storage. Actual usage also depends on segments, indexes, compaction, compression, bursts, and disk headroom.

`retention.bytes` is applied per partition, not as a single total limit for the entire topic. When configuring by bytes, multiply by the partition count to estimate total storage.

## 8. Record size limits and compression

Large records can increase latency, memory usage, and fetch times. Before raising limits, check whether the payload can be split or stored as an external object outside Kafka with only a reference sent.

Related limits to align:

- `max.message.bytes` on the topic/broker.
- `max.request.size` on the producer.
- `max.partition.fetch.bytes` and `fetch.max.bytes` on the consumer.
- Serializer, Schema Registry, or intermediate gateway limits, if any.

Choose compression suited to the data and CPU: `lz4` or `zstd` are commonly evaluated to balance throughput/ratio; `gzip` can compress more tightly at higher CPU cost. Load test with real payloads because already-compressed or encrypted data may not shrink much.

## 9. Design retry topics and DLT alongside the source topic

If consumers have retry or dead-letter recovery, include auxiliary topics in the initial design:

- Retry topics have clear names, delay levels, partitions, and retention.
- The DLT has long enough retention for investigation and controlled replay.
- ACLs for consumers, retry publishers, and DLT operators are separated by role.
- Partition counts of retry/DLT topics are compatible with the destination resolver if source partitioning must be preserved.
- Dashboards exist for retry rate, DLT rate, and oldest record age.
- Replay has idempotency and a process to prevent infinite error loops.

Non-blocking retry can allow newer events to be processed before an event waiting for retry. If business logic requires strict per-aggregate ordering, consider blocking retry or a version/sequence mechanism to detect out-of-order events.

## 10. Security and access permissions

Design ACLs together with the topic; do not wait until the application hits `TopicAuthorizationException` to grant permissions:

| Principal | Typical minimum permissions required |
| --- | --- |
| Topic producer | `WRITE` on the topic; describe permission if required by client/flow |
| Consumer principal | `READ` on the topic and `READ` on the group ID the consumer joins |
| Retry publisher/recoverer | Write permission on the corresponding retry/DLT topics |
| DLT operator | Read permission on the DLT; grant replay permission only when needed |
| Topic provisioning | Topic creation/configuration permission via a dedicated admin principal |

Use SASL/TLS suited to the broker, store credentials in a secret manager, and avoid using admin principals for runtime services. Prefix ACLs should only be used when all topics sharing that prefix belong to a single trust boundary.

## 11. Manage topics as versioned infrastructure

Production topics should be provisioned in a controlled manner via IaC, a Kafka Admin workflow, or a dedicated deployment pipeline. Do not rely on broker auto topic creation in production because a typo in a topic name can create an unintended topic with default settings.

Each topic needs an owner responsible for schema, partitions, retention, ACLs, quotas, and incident handling. Store the desired configuration in the infrastructure source of truth; check for drift between desired configuration and actual broker configuration.

Changes such as increasing partitions, changing cleanup policy, shortening retention, or changing the key contract require review like an API change. Reducing partitions is not a simple operation; it usually requires creating a new topic and migrating data/consumers.

## 12. Monitoring and alerting before production

At a minimum, monitor:

- Ingress record/byte rate and request latency.
- Total consumer group lag and per-partition lag.
- Under-replicated/offline partitions, ISR size, and broker disk usage.
- Produce/fetch errors, request timeouts, and quota throttling.
- Retry, recovery, DLT rate, and DLT record age.
- Partition skew, hot keys, and load distribution across consumers.
- Retention headroom and disk growth rate.

Set alerts based on trends and thresholds tied to SLOs. For example, continuously rising lag while consumer processing rate is below ingress rate signals accumulating backlog; prolonged under-replicated partitions pose a durability risk.

## 13. Example topic design review: orders.events.v1

Suppose a system emits order events, needs per-order ordering, requires seven-day replay, and must tolerate one broker failure:

| Attribute | Illustrative decision | Reason to verify |
| --- | --- | --- |
| Topic | `orders.events.v1` | Event contract by domain and version |
| Key | `orderId` | Keeps events of the same order on one partition |
| Partitions | 6 | From target load, benchmarks, and headroom; check for skew |
| Replication factor | 3 | Distributes replicas across failure domains |
| `min.insync.replicas` | 2 | Allows writes when at least two ISRs remain with `acks=all` |
| Producer | `acks=all`, idempotence enabled | Increases durability and avoids duplicates on producer retry |
| Cleanup | `delete` | Retains event history for replay |
| Retention | 7 days | Per replay needs and actual storage capacity |
| Compression | `lz4` or `zstd` after benchmarking | Balances CPU, network, and disk |
| Security | Producer WRITE; consumer READ topic/group | Least privilege per principal |
| Operations | Lag, ISR, disk, throughput, DLT | Detects backlog and broker risks |

The values above are a review example. Before applying them, replace them with actual throughput benchmarks, event sizes, broker counts, available storage, failure domains, and SLOs.

## 14. Pre-creation topic checklist

Use the following checklist during design review and store decisions alongside infrastructure configuration:

- [ ] Topic purpose, producers, consumer groups, and owner have been identified.
- [ ] Topic name follows the domain/event/version convention.
- [ ] Event schema, key, headers, and compatibility policy have been agreed upon.
- [ ] Key preserves required business ordering; hot partition risks have been evaluated.
- [ ] Partition count is based on throughput benchmarks, concurrency, and headroom.
- [ ] Impact of increasing partitions on key ordering has been accepted.
- [ ] Replication factor, rack/AZ placement, `acks`, and `min.insync.replicas` are compatible.
- [ ] Retention/compaction meets replay, compliance, and storage needs.
- [ ] Storage is estimated from ingress, retention, replication, and compression.
- [ ] Message size and producer/broker/consumer limits have been checked.
- [ ] Retry topics, DLT, retention, and replay procedure have been designed.
- [ ] ACLs for producers, consumers, retry, DLT, and provisioning have been defined.
- [ ] Topic is created via IaC/controlled process; auto-create has been reviewed.
- [ ] Dashboards, alerts, owner, and incident runbooks are ready.
- [ ] Load tests, schema compatibility tests, and failure tests have results.

Only create the topic after decisions on contract, key, partitions, durability, retention, security, and operations have been reviewed. A topic is part of a long-term messaging API; changing partitions, keys, or cleanup policy after production data exists can affect consumers, ordering, and replayability.

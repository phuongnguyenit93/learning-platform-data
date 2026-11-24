# Availability, Durability, and Recoverability Goals

In Spring Kafka operations, reliability must be defined by the outcomes the system delivers to the business. A Kafka cluster may still be running while the application cannot publish records, a consumer may remain connected while processing latency rises continuously, or data may have been acknowledged by the broker without being safely processed by the target system. Therefore, goals must be set for the entire data flow from the producer, through Kafka, to the consumer and downstream services.

The three foundational goals are **availability**, **data durability**, and **recoverability**. They are closely related but measure different properties:

- Availability indicates whether the system can accept and process work within the committed time bounds.
- Durability indicates whether acknowledged records remain intact after failures covered by the chosen protection model.
- Recoverability indicates whether the operations team can restore the service and data to a state serving the business within the allowed timeframe.

No single Spring Kafka configuration guarantees all three goals. The outcome depends on Kafka topology, producer and consumer configurations, application error handling, infrastructure capacity, deployment procedures, and incident runbooks.

## 1. Defining Goals at the Business Flow Level

### 1.1. Availability

A Kafka flow is considered available when the producer can publish valid records, the broker can accept and store records according to the defined policy, and the consumer can continue processing data. Checking only process status or TCP connectivity is not enough. For example, an application health check may return `UP` while the producer continuously times out or consumer lag has exceeded the business threshold.

At least three perspectives should be distinguished:

1. **Platform availability:** brokers can elect leaders, required partitions have leaders, replicas are synchronized, and listeners accept connection requests.
2. **Application availability:** producers can publish records, consumers join groups, process messages, and record results.
3. **Business availability:** events are accepted and produce outcomes before the business deadline. A consumer that is still running but processing slower than the transaction deadline may be considered unavailable under the business SLO.

Availability must also be tied to latency. An event-publishing API returning success after several minutes does not meet the same goal as an API returning in a few hundred milliseconds. Therefore, in addition to success rate, monitor latency at the p50, p95, and p99 percentiles, along with the age of unprocessed records.

### 1.2. Data Durability

Data durability describes the ability to retain records after the producer receives an acknowledgement. You must define clearly what that acknowledgement means. With Kafka, the result depends on:

- Number of partition replicas (`replication.factor`).
- Number of replicas that must be in sync before the broker accepts writes (`min.insync.replicas`).
- Acknowledgement level requested by the producer (`acks`).
- How Kafka elects leaders when replicas fall out of sync.
- Replica placement, retention policies, and broker disk health.

For example, the producer uses `acks=all`, the topic has a replication factor of 3, and the broker requires at least 2 replicas in the ISR. In that case, a write is acknowledged only if all replicas currently in the ISR have received the record and the ISR count is not below the minimum. This configuration helps withstand certain single-broker failures, but it does not mean the data has been written synchronously to every broker in the cluster or backed up to another geographic region.

### 1.3. Recoverability

Recoverability is the capability to return the system to a serving state after a failure while controlling the amount of data that may be lost or must be reprocessed. Two commonly used metrics are:

- **RTO (Recovery Time Objective):** the maximum allowed time to restore the service after an incident.
- **RPO (Recovery Point Objective):** the maximum amount of data that may be lost, measured by time or by event count.

RTO and RPO must be tied to a specific failure scenario. The RTO for replacing a single broker may differ from the RTO for losing an entire availability zone or losing the whole cluster. The RPO of losing one replica in a cluster is not the same as the RPO of losing an entire deployment region.

In-cluster replication helps preserve copies when a broker fails, but it does not replace backups. If a topic deletion, application bug, or corrupt data is written to all replicas, replication will replicate that very change. To recover deleted or corrupted data, you need an independent recovery source such as a standby cluster copy, data exports, the source system of record, or the ability to replay events from upstream.

## 2. Turning Goals into SLIs, SLOs, and Alerts

An **SLI (Service Level Indicator)** is the actual measured metric; an **SLO (Service Level Objective)** is the internal target for that metric; an **SLA (Service Level Agreement)** is the commitment agreed upon with service consumers. Do not publish an SLA before you have measured stable SLIs and clearly defined the calculation method.

| Goal | SLIs to Track | Operational Question |
|---|---|---|
| Producer availability | Send success rate, error count, timeouts, p95/p99 acknowledgement latency | Can the application publish events within the committed time? |
| Kafka availability | Leaderless partitions, offline partitions, under-replicated partitions, request response time | Can the cluster accept and serve reads/writes according to policy? |
| Consumer availability | Processing success rate, processing time, commit failures, rebalance count | Is the consumer processing steadily and maintaining progress? |
| Timely data flow | Consumer lag, age of the oldest unprocessed record, time from publish to processing | Do events reach the target system before the business deadline? |
| Durability | ISR size, ISR shrink, under-replicated partitions, write errors, disk capacity and retention | Are acknowledged records protected according to the failure model? |
| Recovery | Actual RTO, actual RPO, backlog drain time, number of records needing replay or reconciliation | After an incident, how soon do the service and data return to normal? |

Success rates need a clear denominator. For instance, do not count malformed requests sent by a client as Kafka infrastructure failures if the SLO only measures the ability to accept valid requests. Conversely, if the goal is the end-to-end experience, measure failures from downstream services that prevent events from completing business processing as well.

A starting set of goals might include monthly publish success rate, p95 acknowledgement latency, maximum age limit for unprocessed events, RTO for a broker failure, and RTO for a full-zone failure. Specific values must be determined from business requirements, actual load, infrastructure capacity, and game-day exercise results. For instance, a `99.9%` availability target is meaningless without agreeing on the measurement, time window, exclusions, and how downtime is calculated.

Alert thresholds should be based on trends and impact. Consumer lag rising continuously even while below an absolute threshold can signal that the consumer is losing the ability to keep up with data generation rate. A partition briefly under-replicated during a rolling restart may be a transient state; if it persists or spreads across many partitions, it is a signal requiring action. Alerts should specify the service, cluster, topic, consumer group, impact severity, and corresponding runbook.

## 3. Designing Around a Failure Model

Before choosing configurations, list the failures the system must continue to withstand:

| Failure Scenario | Questions to Answer |
|---|---|
| Producer process stops or loses network | Can the producer reconnect and resend without causing unintended duplicate side effects? |
| One broker stops abruptly | Do partitions have another leader? Do remaining replicas have enough ISR to keep accepting writes? |
| A disk or host fails | Do other replicas have enough data and resources to serve traffic? |
| An availability zone loses connectivity | Are replicas distributed across independent zones? Does the cluster still have enough ISR? |
| Consumer stops mid-processing | At what point was the offset committed? Can the event be redelivered safely? |
| Downstream is slow or down | Is the backlog retained? Does the consumer have appropriate backpressure and retry mechanisms? |
| Accidental writes or topic deletion | Is there an independent recovery copy or source to replay from? |
| Entire cluster or region outage | Has the failover procedure to the standby cluster been rehearsed? |

You cannot optimize every property simultaneously in every situation. For example, `min.insync.replicas=2` with `acks=all` may reject writes when the ISR drops to one replica. This is a choice prioritizing data protection over continuing writes with insufficient copies. If you lower the threshold so the system keeps accepting writes, you must accept and explicitly document the increased risk of data loss.

Define independent failure boundaries. Three replicas placed on the same host or in the same zone do not protect well against a failure of that host or zone. In multi-zone environments, use rack awareness so Kafka distributes replicas across racks/zones and verify actual placement for every partition.

## 4. Protecting Data on the Producer Side

### 4.1. Acknowledgement and Retry Configuration

For critical events, a common configuration is `acks=all` with producer idempotence enabled. An idempotent producer helps Kafka deduplicate records caused by retries within the same producer session per the supported protocol. It does not automatically eliminate all duplicate business events, such as a client submitting the same command twice or an application restarting and generating a new event.

Example configuration in Spring Boot's `application.properties`:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
```

The timeout values in the example are a design starting point and must be tuned according to latency, business request timeouts, and broker configuration. `delivery.timeout.ms` caps the total time the producer attempts to complete delivery, including queuing and retries. When the timeout expires, the application must handle the failure result rather than assuming the record was stored.

In Spring Kafka, `KafkaTemplate.send()` is an asynchronous operation. Calling the send method without exception only indicates the application initiated the send; broker acknowledgement or failure appears in the future/callback. The application must observe that outcome, log actionable errors, and decide on retries at the appropriate layer. Avoid calling `flush()` after every single record without a clear reason, as doing so can degrade batching and throughput.

### 4.2. Idempotence and Event Keys

The producer should attach a stable identifier to events, such as `eventId`, `orderId`, or a business key. The Kafka `record key` determines which partition a record is routed to by the partitioner, so choose keys aligned with business ordering requirements. Events with the same key normally land in the same partition and preserve ordering within that partition.

A partition key is not a deduplication mechanism. If the same business command is sent twice, the consuming application may still see two records. The consumer or target service must use the event ID to recognize already-processed events, such as storing the event ID with a unique constraint in the database.

### 4.3. Kafka Transactions

Kafka transactions support atomically writing multiple Kafka records and combining offset consumption with output production in a consume-transform-produce flow. Consumers reading transactional data need `isolation.level=read_committed` to receive only committed transactions. In Spring Kafka, the configured transaction ID prefix must be unique across concurrently running application instances to avoid transactional ID conflicts.

Kafka transactions do not automatically make database writes, HTTP calls, or email sends part of the Kafka transaction. If a listener updates a database and then commits a Kafka offset, a failure between the two operations can still leave inconsistent state. For flows integrating Kafka and a database, consider a transactional outbox on the publishing side and an inbox/idempotency pattern on the receiving side. This pattern bridges the gap between the two systems by storing business state and the event in one database transaction, then publishing the event in a retryable way.

## 5. Protecting Data on the Broker Side

### 5.1. Replication and ISR

A commonly used configuration for critical topics in a cluster with at least three independent brokers is:

```properties
default.replication.factor=3
min.insync.replicas=2
unclean.leader.election.enable=false
```

These are broker-side or topic-side settings, not `application.properties` properties in a Spring Boot application. Verify the actual replication factor and min ISR on each topic; cluster defaults do not guarantee every existing topic uses the right policy.

- `replication.factor=3` creates three copies of each partition. Replicas should reside on different brokers and failure domains.
- `min.insync.replicas=2` requires at least two synchronized replicas when the producer uses `acks=all`.
- `unclean.leader.election.enable=false` avoids electing an out-of-sync replica as leader when no synchronized replicas remain. This protects data consistency better, though the partition may become temporarily unavailable if no eligible ISR remains.

ISR (in-sync replicas) is the set of replicas keeping up with the leader according to Kafka's criteria. Monitor both ISR count and ISR shrink/expand events. A partition with replication factor 3 that has only one replica left in the ISR operates below the intended protection level, even if applications can still read data.

### 5.2. Retention and Capacity

Retention determines how long or up to what size limit Kafka keeps data. Choose retention long enough for downstream outages, investigation time, recovery time, and any required replay window. For topics using log compaction, understand that Kafka retains the latest state per key according to compaction policies; compaction is not a full historical backup of every version.

Capacity estimation must account for data generation rate, retention, replication factor, index/segment overhead, traffic growth, and operational headroom. An initial estimate for physical storage capacity is:

```text
approximate storage capacity
  = data throughput per second
  × retention seconds
  × replication factor
  × headroom factor
```

This is only a rough estimate. Use actual data size after compression, version/configuration overhead, growth rate, partition distribution, and usable capacity per broker. Monitor disk usage and disk growth rate; alert before brokers approach operational limits.

Replication protects against certain hardware failures, while retention supports re-reading data within a time window. Neither replaces an independent backup for accidental deletion, bad writes, or total cluster loss.

## 6. Ensuring Safe Consumer Processing

### 6.1. Offsets and Delivery Semantics

Offsets represent a consumer group's read progress on each partition. The committed position determines where Kafka resumes delivering data after a consumer restarts or a partition is reassigned to another member.

For business processing that must avoid losing events, the common principle is to finish processing before committing the offset. This yields **at-least-once** semantics: a record may be reprocessed if the application completes its side effect but stops before committing the offset. Therefore, handlers must be idempotent or have a deduplication mechanism.

| Offset Handling | Behavior When Consumer Stops | Consequence |
|---|---|---|
| Commit before processing | Kafka may not redeliver unfinished records | Risk of losing business side effects; close to at-most-once |
| Process then commit | Kafka may redeliver if stopped before commit | Potential duplicate processing; at-least-once |
| Kafka transaction combining offsets and Kafka output | Offsets and output records are committed atomically within Kafka | Can achieve exactly-once for Kafka-to-Kafka flows within the transactional configuration scope |

Example consumer configuration:

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.listener.ack-mode=record
```

`enable-auto-commit=false` lets Spring Kafka manage commit timing according to the container acknowledgement mode. `ack-mode=record` commits after each successfully processed record; this mode is easy to reason about but may incur higher commit overhead compared to `BATCH`. Choose the mode based on batch size, throughput requirements, and business processing boundaries. With manual acknowledgement, acknowledge only after the required work has completed.

`auto-offset-reset=earliest` applies only when the group has no valid offset yet or the current offset no longer exists. It does not mean every restart reads from the beginning. Using `latest` can skip older data when a group has no offset yet; the choice must align with consumer group initialization and replay policies.

Example listener illustrating idempotent processing:

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(OrderCreated event) {
    // applyOnce checks eventId and applies the business side effect only once.
    billingService.applyOnce(event.eventId(), event);
}
```

Here `applyOnce` represents the application's deduplication mechanism, such as writing the event ID into an inbox table with a unique constraint inside the same database transaction as the business update. Only persist the event ID after the update succeeds or execute both operations in the same transaction; otherwise, the consumer could mark the event as processed when the business effect was never persisted.

### 6.2. Poll, Heartbeats, and Processing Time

The consumer must call `poll()` frequently enough to maintain group membership. If processing a batch takes too long, the consumer may exceed `max.poll.interval.ms`, be treated as dead, and trigger a rebalance. Continuous rebalances reduce throughput and cause lag to grow.

Settings to review together:

- `max.poll.records`: maximum records returned in a single poll. Smaller batches can reduce per-batch processing time while increasing poll/commit overhead.
- `max.poll.interval.ms`: maximum interval between polls. The value must exceed high-load batch processing time with a safety margin.
- `session.timeout.ms` and heartbeats: affect how the group detects disconnected consumers.
- Listener container `concurrency`: number of consumer threads in the application. Increasing concurrency helps only when enough partitions and downstream capacity exist.

A consumer group cannot parallelize across more consumers than the number of partitions assigned to the group at the same time. If throughput needs to increase, evaluate partition count, downstream processing capacity, key ordering, and connection limits before increasing concurrency. Increasing partitions can affect key distribution and cross-partition ordering, so assess it before changing a live topic.

If downstream is slow, avoid blindly increasing consumer count. Apply backpressure, bound concurrency, tune batch sizes, and protect downstream from overload. A faster consumer does not help if the database or downstream API has already hit its limit.

## 7. Retries and Dead Letter Topics

Not all processing errors share the same remediation:

- **Transient errors:** database timeouts, network glitches, or overloaded dependencies. Can be retried with a bounded count and increasing backoff.
- **Unprocessable data errors:** schema-invalid payloads, missing required fields, or invalid values. Continuous retries usually cannot fix these; route the message to a Dead Letter Topic (DLT) after an appropriate retry policy.
- **Configuration or deployment errors:** can affect an entire partition or all consumers. Detect quickly, roll back the bad release/config, and throttle retry rates to avoid amplifying load.

In Spring Kafka versions with `DefaultErrorHandler`, you can configure bounded retries and route failed records to a DLT using `DeadLetterPublishingRecoverer`. Example:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    // 2 retries after the initial processing attempt, 1 second apart.
    return new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<Object, Object> kafkaListenerContainerFactory(
        ConsumerFactory<Object, Object> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {
    ConcurrentKafkaListenerContainerFactory<Object, Object> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

In this example, the handler is invoked at most three times in total: the first attempt plus two retries. This is an illustrative configuration; classify exceptions to choose which errors are retried, tune backoff to dependency recovery time, and ensure the producer used for DLT publishing has matching serializer configuration.

When using `DeadLetterPublishingRecoverer`'s default resolver, verify the DLT naming convention and destination partition behavior for your Spring Kafka version. If preserving the source partition, the DLT must have enough corresponding partitions. The DLT must also have appropriate replication, retention, ACLs, and alerts; moving a record to the DLT does not mean the incident is resolved.

A responsible DLT process must retain source metadata such as topic, partition, offset, key, timestamp, exception, and event ID. Operations must know who monitors the DLT, how to classify errors, how to repair data or code, how to replay, and how to prevent failing records from forming infinite loops. When replaying, reuse the original event identifier and ensure target consumers are idempotent.

Spring Kafka also supports non-blocking retry topics, such as via `@RetryableTopic`. This allows a partition to continue processing other records while one record awaits retry, though it can alter relative processing ordering across events. If the business requires strict per-key ordering, assess the impact of retry topics and design the processing flow accordingly.

## 8. Incident-Specific Recovery Plans

Runbooks must describe detection signals, blast radius, safe actions, owners, and criteria for confirming service recovery. The table below provides a reference framework for building runbooks tailored to your actual environment.

| Incident | Primary Recovery Actions | Post-Recovery Verification |
|---|---|---|
| Producer disconnected or timing out | Check DNS, network, TLS/SASL, broker availability, and quotas; let producer retry within delivery timeout; handle send failures in the application | Publish success rate returns to normal; no abnormal backlog at the producer call site; errors are not silently swallowed |
| One broker stopped | Check leader election, ISR, and replicas; recover the broker or replace the node per runbook | No offline partitions remain; under-replicated partitions return to normal thresholds; replicas have caught up |
| ISR drops below min ISR | Identify the broker/disk/network causing replica lag; restore replicas and monitor catch-up | ISR count meets policy; producer writes succeed again without arbitrarily lowering min ISR |
| Consumer stopped or continuously rebalancing | Check exceptions, processing time, poll interval, heartbeats, and downstream health; restart or roll back the faulty release | Group stabilizes; commits advance; lag begins dropping; no unhandled duplicate business side effects |
| Downstream overloaded | Cap concurrency, pause or throttle consumers via supported mechanisms; restore downstream capacity; ramp processing back up gradually | Downstream stabilizes; backlog shrinks; no additional timeouts or retry storms |
| Poison message | Fix the data or code root cause; preserve the record with metadata; execute controlled replay from DLT | Records are processed; DLT count drops; replay creates no duplicate side effects |
| Accidental topic or data deletion | Halt the impacting operation; check retention and independent backup/replica sources; restore topic, config, and data per procedure | Restored record count and scope reconciled; producers/consumers point to the right topic and offsets |
| Cluster or region outage | Activate DR plan; cut over producers/consumers to standby cluster per rehearsed procedure; check data sync and offsets | Actual RTO/RPO recorded; read/write flows and access permissions work; data is reconciled |

### 8.1. Recovering Consumer Backlog

After a consumer outage, the backlog may be large even when Kafka is healthy. The key is determining whether the consumer can process faster than new events arrive.

```text
approximate backlog drain time
  = number of backlogged records
  / (recovery processing throughput - incoming data throughput)
```

For example, if the backlog has 1,800,000 records, the consumer processes 8,000 records/sec, and the producer continues generating 2,000 records/sec, the net drain capacity is 6,000 records/sec, yielding an ideal drain time of about 300 seconds. Actual time also depends on record size, key distribution, partition count, downstream latency, retries, and rebalances.

If recovery throughput does not exceed incoming throughput, the backlog will not shrink. In that case, safely increase processing capacity, shed or throttle input load, or apply a business plan to drain the backlog. Increase consumer count only when assignable partitions remain and downstream has capacity.

### 8.2. Cluster or Region Recovery

A DR plan must specify the standby cluster, how topics and data are replicated, required schemas/ACLs/configs, bootstrap servers per application, traffic cutover steps, consumer offset handling, and failback procedures to the primary cluster. Technologies like MirrorMaker 2 or cluster-linking solutions can help replicate data, but do not assume offsets, ACLs, schemas, and application configs are automatically fully compatible.

Failing over to a standby cluster can introduce gaps or duplicates depending on how data and offsets are synchronized. Measure replication lag, determine the cutover point, control which cluster producers write to, and include a post-failover data reconciliation step. Failing back to the primary cluster also requires its own procedure; do not merely point bootstrap servers back without establishing data direction and offset state.

## 9. Observability and Alerting in Spring Kafka

Reliability must be observed from both the application and the platform. Spring Boot Actuator with Micrometer can export application metrics and certain Kafka metrics into your monitoring system; Kafka brokers/clients also expose metrics via JMX or corresponding exporters. Exact metric names depend on Spring Boot, Spring Kafka, Kafka client versions, and registry configuration.

### 9.1. Producer Metrics

Track send success rate, error and timeout counts, retry rate, request latency, record send rate, batch size, and buffer exhaustion. If latency rises alongside retry rate, inspect broker load, network, quotas, ISR, and batch size. A producer may still succeed in sending while latency rises enough to time out business requests.

### 9.2. Broker Metrics

Important signals include:

- Offline partitions and leaderless partition count.
- Under-replicated partitions, ISR shrink/expand events, and replica fetch lag.
- Request latency, request queue, network processor, and request handler utilization.
- Disk usage, data growth rate, log directory failures, and broker health.
- Connection count, quota throttling, and authentication/authorization errors.

Offline partitions generally require critical-severity alerts because those partitions cannot serve normally. Prolonged under-replicated partitions indicate data protection is below policy. Capacity alerts must leave enough lead time to expand disks or adjust load before brokers run out of space.

### 9.3. Consumer and Business Metrics

Track lag per partition and group, age of the oldest unprocessed record, record processing rate, processing latency, commit failures, rebalance rate, exception counts, and DLT publish rate. Lag is just a record count; on low-volume topics, the age of the oldest record can reflect business impact better.

Add business metrics such as processed order counts, pending transactions, event rejection rates, and end-to-end time from emission to completion. Use event IDs or correlation IDs in logs to trace the same event across producer, Kafka, and consumer. Avoid logging sensitive payloads or full record contents without proper justification and controls.

### 9.4. Designing Actionable Alerts

Every alert should answer three questions: what is broken, which service is impacted, and what the on-call engineer should do next. Examples:

- `offline partitions > 0`: identify affected topic/partition, involved brokers, and the leader recovery runbook.
- Sustained `under-replicated partitions > 0`: inspect brokers, disks, network, and replica catch-up rate.
- Continuously rising consumer lag or record age exceeding SLO: identify group/partition, processing rate, and downstream health.
- DLT spike: inspect application version, schema, dependencies, and exception groups.
- Rising producer timeouts: inspect broker latency, ISR, quotas, and network; also check caller retries to avoid retry storms.

Do not alert purely on a static threshold if transient states are normal. Use sustained duration, rate of change, affected partition count, and business SLOs to reduce noisy alerts while catching incidents early.

## 10. Operational Procedures to Keep Goals Stable

### 10.1. Safe Application Deployment and Shutdown

Rolling deployments must avoid losing too many consumers in the same group simultaneously or causing brokers to lose required quorum/ISR. Set a termination grace period sufficient for listener containers to stop accepting new work, complete in-flight processing within allowed limits, and commit offsets. For long-running work, define shutdown timeout behavior to prevent committing offsets while background side effects continue.

Changes to concurrency, partition count, serializers, schemas, or retry configuration can impact ordering, throughput, and compatibility with older data. Roll out incrementally, observe metrics after each step, and prepare a rollback plan. When upgrading Kafka client or Spring Kafka versions, check compatibility and default changes affecting producers, consumers, transactions, and error handlers.

### 10.2. Capacity Management

Capacity planning must account for average throughput, peak traffic, record size, compression ratio, partition count, replication factor, retention, consumer processing rate, and downstream capacity. Maintain headroom so the system can absorb traffic spikes and drain backlogs after incidents. If designed only for average load, a single backlog event may prevent the system from ever catching up with producers.

Periodically review limits such as file descriptors, network bandwidth, disk IOPS, connection counts, quotas, request handler capacity, and heap size. For Spring applications, monitor thread pools, database connection pools, GC pauses, and synchronous dependencies inside listeners. These bottlenecks can slow consumers even when brokers are healthy.

### 10.3. Recovery Drills

Runbooks are trustworthy only once practiced. Drill across failure tiers: stop a consumer, stop a broker in a controlled environment, slow down a downstream service, handle a poison message, restore data from backup, and fail over to a standby cluster. Record time to detect, time to begin recovery, time to reach SLO, backlog size, replayed record counts, and any discrepancies after reconciliation.

After every drill or real incident, update measured RTO/RPO, dashboards, alerts, access permissions, contact lists, and runbook steps. If actual results miss targets, adjust the architecture or committed goals rather than merely closing the incident.

## 11. Verifiable Operational Readiness Criteria

A Spring Kafka system should only be considered operationally ready when the owning team can answer and demonstrate the following:

1. Critical business flows, failure models, SLIs/SLOs, RTO, and RPO are defined for each scenario.
2. Producers have explicit `acks`, idempotence, timeout, and send-result handling policies; send errors are never ignored.
3. Critical topics have appropriate replication factor, min ISR, placement, and retention; alerts exist for lost replicas or low disk capacity.
4. Consumers have clear offset commit strategies, idempotent processing, controlled poll durations, and backpressure when downstream is slow.
5. Retries are bounded; DLTs have designated owners, retention, alerts, and controlled replay procedures.
6. Dashboards display producer, broker, consumer health, and business latency; alerts map to concrete actions.
7. Independent recovery sources exist for situations where replication is insufficient, data is accidentally deleted, or a cluster is lost; DR procedures have been rehearsed.
8. Deployment, shutdown, capacity planning, rollback, and post-recovery reconciliation procedures are in place.

These criteria turn reliability goals into concrete operational responsibilities. With real metrics from production traffic and drills, teams can tune SLOs, topology, timeouts, retention, and processing capacity to balance availability, data protection, cost, and recovery time.

# Scaling Multiple Application Instances

A Spring Kafka application can run multiple instances concurrently to increase processing capacity and maintain service availability when one instance fails. For consumers, the common scaling approach is running multiple application replicas that join the same Kafka consumer group. Kafka distributes the topic's partitions across consumer members in the group; each partition is assigned to at most one active consumer in that group at a time.

To scale effectively, coordinate three levels: the number of application instances, listener concurrency per instance, and topic partition count. Adding instances does not automatically increase throughput if the topic has too few partitions or if the bottleneck is a database, HTTP service, or processing logic. Conversely, using a different group ID per instance causes each group to read the entire data stream independently, creating fan-out instead of load sharing.

This lesson belongs to the **Concurrency and Scaling** chapter of the **SPRING_KAFKA_MESSAGING** module. The module focuses on building event-driven applications with Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, understanding topics, partitions, offsets, and consumer groups, while learning serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing for reliable messaging pipelines.

## 1. What Does Scaling Multiple Instances Mean?

An instance is a running application process. In production, multiple instances of the same service can be deployed across containers, pods, VMs, or servers. These instances typically share topic and consumer group configurations to divide the work.

For example, the `order-projection` service runs three instances:

~~~text
order-projection-1 ─┐
order-projection-2 ─┼──> Kafka consumer group: order-projection
order-projection-3 ─┘
                         |
                         v
                  Topic: order-events
                  Partition 0..5
~~~

Instances do not arbitrarily pick partitions themselves. The consumer group coordinator and partition assignor distribute partitions to consumer members. When an instance joins or leaves the group, assignments can change and the group performs a rebalance.

Horizontal scaling means increasing or decreasing the number of application instances. Vertical scaling means increasing CPU, memory, or resources of a single instance. Both can be combined, though horizontal consumer scaling is limited by the number of assignable partitions.

~~~mermaid
flowchart TD
    A[Application with multiple instances] --> B[Same group ID]
    B --> C[Kafka consumer group]
    C --> D[Partition assignment]
    D --> E[Consumer member on instance A]
    D --> F[Consumer member on instance B]
    D --> G[Consumer member on instance C]
    E --> H[Listener processes records]
    F --> H
    G --> H
~~~

## 2. Using the Same Group ID for Load Sharing

If multiple instances need to jointly process an event stream under a work-sharing model, all consumers must use the same group ID.

Configuration example:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
~~~

Each instance runs the same artifact and configures group ID `order-projection`. Kafka treats those consumers as members of the same group and distributes partitions among them.

Within a group:

- Each partition is assigned to at most one consumer member at a time.
- A consumer can be assigned multiple partitions.
- Consumers share offset progress per topic-partition.
- When a consumer leaves the group, its partitions can be reassigned to other members.
- Each member does not receive every record of the topic if the group has multiple consumers; members divide the partitions.

Sharing the same group ID is essential for load sharing. If each instance has its own group ID, Kafka creates independent groups and each group reads all topic data with its own offsets.

## 3. Distinguishing Work-Sharing from Fan-Out

Two commonly confused patterns:

| Pattern | Group ID | Result |
| --- | --- | --- |
| Multiple instances of the same service sharing load | Identical | Consumers share partitions and records. |
| Multiple independent services each needing every event | Different per service | Each group reads the entire data stream independently. |
| Each instance accidentally uses a unique group ID | Different per instance | Each instance receives a full copy of all data, without load sharing. |

Example:

~~~text
Work-sharing:
  order-projection-1 ─┐
  order-projection-2 ─┼── group: order-projection
  order-projection-3 ─┘       each event is processed by one member in the group

Fan-out:
  billing-service ───── group: billing
  audit-service ─────── group: audit
  analytics-service ─── group: analytics
       each group reads all events from the topic
~~~

Fan-out fits when billing, audit, and analytics each need the data. Work-sharing fits when multiple replicas of the billing service only need to split processing of the same stream. Do not include pod IDs or hostnames in the group ID if the goal is load sharing within the same service.

## 4. Partitions Limit Active Consumers

A partition is the maximum unit of parallelism within a consumer group. If a topic has six partitions, at most six consumer members can receive partitions from that topic simultaneously. Excess consumers can still join the group, but have no partitions to read.

Examples:

| Partition count | Consumer members | Max consumers with useful assignments |
| ---: | ---: | ---: |
| 6 | 1 | 1 |
| 6 | 3 | 3 |
| 6 | 6 | 6 |
| 6 | 9 | 6 |
| 6 | 12 | 6 |

This limit applies to the total number of partitions provided by the group's subscription. If the group subscribes to multiple topics, available partitions can be counted across the entire set of topics the group reads.

For example, a topic has six partitions and the application runs ten instances, each with one consumer. At most six consumers receive partitions; the remaining four consumers are idle for that topic. Adding instances does not enable multiple consumers in the same group to process one partition in parallel.

If one partition is hot or slow to process, idle consumers cannot automatically take over part of that partition. You must investigate key distribution, partition count, and processing time.

## 5. Concurrency Within Each Instance

A Spring Kafka instance can create multiple consumers for the same listener via listener container concurrency. When running multiple instances, total consumer members equal the product of instance count and concurrency per instance, assuming every instance creates the same listener.

Example:

- 3 application instances.
- Each instance configures concurrency = 2.
- Up to 6 consumer members total in the same group.
- With a 6-partition topic, the group can distribute partitions across all 6 consumers.

Diagram:

~~~text
Instance A: consumer A-1, consumer A-2 ─┐
Instance B: consumer B-1, consumer B-2 ─┼── group order-projection
Instance C: consumer C-1, consumer C-2 ─┘

Topic order-events:
  P0  P1  P2  P3  P4  P5
  Each partition is assigned to one consumer member
~~~

Concurrency can be configured via the container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(2);
    return factory;
}
~~~

Or configure concurrency on the listener endpoint if supported by your Spring Kafka version and declaration style:

~~~java
@KafkaListener(
    id = "orderProjectionListener",
    topics = "order-events",
    groupId = "order-projection",
    concurrency = "2"
)
public void onOrderEvent(OrderEvent event) {
    orderProjection.apply(event);
}
~~~

Do not configure concurrency in multiple places without understanding precedence across annotations, factories, and Spring Boot properties. Pick one primary place to manage it so operators can easily determine how many consumers are created per instance.

## 6. Calculating Total Consumers When Scaling

You can estimate the number of created consumer members as follows:

\[
C_{\text{total}} = R \times C_{\text{instance}}
\]

Where:

- R is the number of application replicas/instances.
- C_instance is the listener concurrency per instance.

The number of consumers with useful assignments cannot exceed the partitions subscribed by the group:

\[
C_{\text{active}} \leq \min(C_{\text{total}}, P)
\]

Where P is the total number of partitions in the group's subscription. This formula is an upper bound; actual assignments also depend on subscriptions and the partition assignor.

Examples:

| Replicas | Concurrency/instance | Consumer members | Partitions | Assigned consumers |
| ---: | ---: | ---: | ---: | ---: |
| 2 | 2 | 4 | 8 | Up to 4 |
| 3 | 2 | 6 | 6 | Up to 6 |
| 4 | 2 | 8 | 6 | Up to 6 |
| 4 | 1 | 4 | 12 | Up to 4 |
| 6 | 2 | 12 | 12 | Up to 12 |

This is an initial capacity-planning calculation. It does not assert that every consumer has the same data volume or throughput; partitions may have skewed load and listeners may process at different speeds.

## 7. How Kafka Distributes Partitions

The partition assignor determines how partitions are distributed to consumer members in a group. Common assignors include:

- **RangeAssignor:** distributes partition ranges per topic.
- **RoundRobinAssignor:** distributes cyclically across the set of topic-partitions.
- **StickyAssignor:** tries to keep assignments stable and balanced when possible.
- **CooperativeStickyAssignor:** supports cooperative rebalancing to reduce the number of partitions revoked at once.

Actual behavior depends on the configured assignor, Kafka client version, and compatibility across members. Do not assume every cluster uses the same default assignor.

With multiple topics, RangeAssignor can produce uneven distributions in certain topologies, while round-robin or sticky can yield different results. If specific assignment behavior is needed, test with actual topics, partitions, and consumer members.

Cooperative rebalancing can reduce disruption during membership changes, but does not eliminate rebalances completely. All members must use compatible assignor configurations for transitions to work properly.

## 8. Rebalance When Scaling Up or Scaling Down

When adding instances, new consumers join the group. The coordinator updates membership and the group performs a rebalance to redistribute partitions. When removing instances or when a consumer loses connection, the group also rebalances to hand remaining partitions to active members.

During a rebalance:

- Some partitions may pause processing temporarily.
- Old assignments are revoked or transferred.
- New consumers receive partitions and resume from committed offsets.
- Uncommitted records may be read again.
- Throughput may dip temporarily, especially when rebalances happen frequently.

Continuously scaling up and down on short-term fluctuations can cause excessive rebalances. Autoscalers should have cooldowns, stabilization windows, or sufficiently stable thresholds before changing replica counts.

Do not evaluate scaling solely by checking that pod counts increased. Inspect group state, member count, partition assignments, lag, and rebalance duration after scaling.

## 9. Shared Offsets Within a Group

Offsets are stored by group ID and per topic-partition. When a partition moves from consumer A to consumer B in the same group, consumer B resumes from the group's committed offset if that offset is still valid.

Scaling instances does not create a new set of offsets per pod. This enables replacement consumers to continue the previous member's work.

Example:

~~~text
Group: order-projection

order-events-0 -> committed offset 1200
order-events-1 -> committed offset 950
order-events-2 -> committed offset 1800

Before rebalance:
  Instance A owns P0, P1
  Instance B owns P2

After rebalance:
  Instance B may receive P0
  Instance C may receive P1, P2

Offsets still belong to group order-projection
~~~

If each instance uses a different group ID, offsets are tracked separately per group. This creates fan-out and increases read load on brokers.

Do not reset offsets when scaling up. Adding consumers does not require resetting progress; Kafka uses the existing committed offsets for each partition.

## 10. Ordering When Running Multiple Instances

Kafka preserves record order within each partition. Within the same group, a partition is assigned to at most one consumer member at a time, preserving partition read order when the consumer processes sequentially.

If the producer uses orderId as the key, events with the same orderId are normally routed to the same partition according to the partitioner and topology. When scaling multiple instances, that partition can move from one instance to another after a rebalance, but is never split simultaneously across two members of the same group.

However, business ordering can still be broken if:

- The listener submits work to a thread pool without waiting for completion.
- The consumer commits offsets before business tasks finish.
- Non-blocking retries allow later events to be processed before failed events.
- Multiple producers emit events with the same key without sequence/coordination rules.
- Changing partition counts alters key-to-partition mappings.

Horizontal scaling does not solve ordering by itself. Keep keys stable, process sequentially per partition or key, and design retries appropriately.

## 11. When to Increase Partitions?

If the group already has useful consumers equal to the partition count and lag keeps growing, adding instances will not increase parallelism for that topic. You may need to add partitions, which is a topology decision that requires evaluation.

Increasing partitions can:

- Increase maximum parallelism for future consumer groups.
- Spread load across more consumers.
- Increase metadata, replication traffic, and broker resources.
- Change key-to-partition mappings with hash/modulo-based partitioners.
- Affect per-key ordering when old and new records may reside in different partitions.

Before increasing partitions, check:

1. Whether the bottleneck is truly consumer capacity or a downstream database/API.
2. Whether partitions suffer from hot keys or skew.
3. Whether changing key-to-partition mappings is acceptable.
4. Whether draining the backlog or topic versioning is needed.
5. Whether brokers have enough disk, network, and replication capacity.

If one partition is hot because a single key accounts for most traffic, adding partitions may not spread that key because the same key still hashes to one partition under the partitioner. Revisit the key unit or aggregate sharding if business rules permit.

## 12. Scaling by Throughput and Lag

A consumer group must process data at least as fast as incoming data if lag is to remain stable. When producer throughput exceeds consumer throughput over an extended period, backlog grows.

A simple capacity estimate:

\[
R_{\text{needed}} =
\left\lceil
\frac{\lambda_{\text{incoming}}}
{\mu_{\text{per-consumer}}}
\right\rceil
\]

Where:

- λ_incoming is the incoming record rate to the group.
- μ_per-consumer is the actual throughput of one consumer member.
- R_needed is the required consumer count under a simple load model.

Next, cap by partition count and check downstream bottlenecks. Consumer throughput does not necessarily scale linearly when adding members, because database connection pools, brokers, CPU, network, and partition skew can constrain the system.

For example, producers generate 4,000 records/second and one consumer sustainably processes 800 records/second. The initial estimate requires five active consumers. If the topic only has three partitions, the group cannot utilize all five consumers for that topic; evaluate partition topology or optimize per-partition throughput.

To measure accurately, use production-like workloads and monitor per-partition lag, records-consumed rate, listener duration, CPU, memory, database latency, and rebalances.

## 13. Autoscaling Based on Consumer Lag

Replicas can be scaled automatically based on consumer lag or related metrics. However, relying on CPU alone may be unsuitable: consumers can be I/O-bound with low CPU while lag continues to climb.

Useful signals include:

- Total lag or max per-partition lag.
- Rate of lag growth/drain.
- Record/batch processing duration.
- Records consumed rate and producer rate.
- CPU/memory.
- Partition count and consumers currently holding assignments.
- Group state and rebalance rate.

An autoscaling workflow should:

1. Define lag thresholds based on SLA and retention.
2. Scale out when lag grows continuously and unused partitions remain.
3. Wait for rebalance completion before re-measuring throughput.
4. Scale in when backlog stabilizes and consumers have spare capacity.
5. Use cooldowns/stabilization to avoid replica flapping.
6. Avoid scaling beyond useful partition limits without another reason.
7. Maintain minimum replicas matching availability requirements.

For example, a topic has 12 partitions and concurrency 1; the autoscaler can scale up to roughly 12 useful consumer members for that group. With concurrency 2 per instance, only about six instances are needed to create 12 consumer members. Actual deployment numbers still depend on resources and assignments.

When scaling to zero, the group has no consumer members. Producers can still write data; lag accumulates and consumption only resumes when new instances start. Scale-to-zero only fits when SLAs tolerate startup latency and backlog.

## 14. Configuration in Spring Boot and Multi-Replica Deployment

Example configuration of a listener with concurrency two:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      concurrency: 2
~~~

Spring Boot applies concurrency to the auto-configured listener container. If the application defines custom container factories, configure concurrency on those factories or on the corresponding endpoints to ensure the effective value matches expectations.

In Kubernetes, you can run multiple replicas of the same Deployment. Each pod uses the same group ID and subscription; Kafka automatically distributes partitions as pods join the group.

Conceptual example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-projection
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-projection
  template:
    metadata:
      labels:
        app: order-projection
    spec:
      containers:
        - name: app
          image: example/order-projection:1.0.0
~~~

The manifest only illustrates replica count. Configure resource requests/limits, readiness/liveness probes, termination grace periods, secrets, and Kafka connectivity according to your environment's deployment standards.

Do not include the pod name in the group ID if you want load sharing. If group ID varies by pod, each pod becomes an independent group and receives every event.

## 15. Graceful Shutdown and Scaling Down

When the orchestrator reduces replicas, pods are terminated. The Spring application needs time to stop listener containers, finish or cancel in-flight processing per its lifecycle, and close consumers cleanly.

Coordinate:

- Platform termination grace period.
- Spring lifecycle shutdown timeout.
- Maximum listener processing duration.
- `max.poll.interval.ms` and heartbeat settings.
- AckMode/offset commits.
- In-flight retries/backoff.
- Databases or dependencies the listener needs during shutdown.

If a pod is killed before processing/committing finishes, records may be re-read by another member. This is why handlers should be idempotent and business operations must be retry-safe.

Scaling down too rapidly can trigger consecutive rebalances. Drain step by step, use cooldowns, and monitor group membership during rollouts.

## 16. Static Membership and `group.instance.id`

Kafka supports static membership via `group.instance.id`. Consumers with a stable static identity can reduce unnecessary rebalances when processes restart within the configured timeout window.

However:

- Every concurrent member in the same group must have a unique group.instance.id.
- The ID should remain stable for the same instance across restarts to benefit from static membership.
- Do not reuse the same literal ID across all replicas.
- Duplicate IDs can fence the older consumer or cause group membership errors.
- Static membership does not replace health checks, graceful shutdown, or error handling.

In container environments, derive the ID from a stable replica/pod identity and configure it via consumer properties. Do not hardcode the same group.instance.id in an application.yml shared by all replicas.

Static membership fits when instances have stable identities and brief restarts frequently cause expensive rebalances. In autoscaling environments where replicas change continuously, evaluate lifecycle and identity strategies carefully.

## 17. Bottlenecks Not Solved by Adding Instances

Scaling consumers only helps when consumer capacity is the bottleneck. Other limits can prevent adding instances from improving throughput:

| Bottleneck | Symptom | Remediation |
| --- | --- | --- |
| Database connection pool | Many consumers waiting for connections, rising DB latency | Optimize queries/bulk writes, connection pools, and transactions. |
| HTTP downstream | Request timeouts, rate limits, high latency | Use bulk APIs, cap concurrency, backoff, or dedicated queues. |
| Hot partition | One partition has high lag, others have low lag | Review key distribution and partitioning strategy. |
| CPU/GC | High CPU, GC pauses, slow processing | Profile, optimize object allocation and payloads. |
| Network/broker | High fetch latency, request queues, or network saturation | Inspect brokers, network, replication, and client fetch settings. |
| Lock contention | Threads waiting on locks, flat throughput | Shrink critical sections or partition the work. |
| Retry storm | Rising retries, downstream stays overloaded | Classify errors, apply backoff, limit retries, and use DLT. |

If adding replicas overloads the database, lag can grow even faster. Scale the entire processing pipeline cohesively and cap concurrency to protect downstream systems.

## 18. Idempotency and Duplicates with Multiple Instances

Multiple instances do not mean every event is processed only once in all scenarios. A consumer may process a record and crash before committing offsets; after a rebalance, another member reads that record again.

Principles:

- Use a unique event ID to identify events.
- Design idempotent database updates or persist processed event IDs.
- Set appropriate transaction boundaries between business processing and offset commits.
- Do not commit before durable work completes.
- For Kafka-to-Kafka pipelines, consider Kafka transactions/EOS within their supported scope.
- For database and Kafka, evaluate transactional outbox/inbox or matching consistency patterns.

Producer idempotence protects certain retry cases when sending records within the same producer session; it does not replace consumer-side idempotency when records are redelivered or applications actively emit duplicate events.

## 19. Testing Multi-Instance Scaling

Test against a real broker via Testcontainers or an integrated Kafka environment, running multiple consumer members in the same group.

Scenarios:

1. Run two instances with the same group ID and confirm partitions are split between them.
2. Increase instance count and observe rebalances and assignments.
3. Remove one instance and confirm partitions are reassigned.
4. Create more consumers than partitions and confirm excess members have no assignments.
5. Run the same service with different group IDs to demonstrate fan-out.
6. Verify offsets resume from committed offsets after member replacement.
7. Send multiple keys and confirm per-partition ordering.
8. Simulate slow processing, retries, and rebalances.
9. Verify graceful shutdown when scaling down.
10. Measure throughput, lag, listener latency, CPU, memory, and database load.

In tests, do not merely assert the number of running processes. Verify actual assignments and processed record counts. Use event IDs to detect duplicates and per-aggregate sequences to verify ordering.

## 20. Scaling Workflow When Consumer Lag Grows

When lag rises, proceed in order:

1. Identify the lagging group, topic, and partitions.
2. Check whether the group has enough members and assignments.
3. Compare consumer member count with partition count.
4. Check listener concurrency on each instance.
5. Measure per-consumer throughput and processing time.
6. Determine whether the bottleneck is in consumers, partition skew, brokers, or downstream.
7. If partitions and resources allow, scale out in steps.
8. Wait for rebalance and re-measure lag/throughput.
9. If the partition limit is reached, optimize processing or evaluate adding partitions.
10. When scaling down, drain in a controlled manner and verify offsets/lag stabilize.

Do not reset offsets just to bring lag down to zero. Resetting can skip unprocessed data or cause events to be re-read; it is an operation requiring business impact assessment.

## 21. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| Adding pods always increases throughput. | Useful consumers are limited by partitions and downstream capacity. |
| Each pod should have its own group ID. | To share load, replicas must use the same group ID. |
| Same group ID means every pod receives every record. | Members split partitions; each group tracks its own progress. |
| Concurrency equals partition count. | Concurrency is the number of consumer containers created per instance; partitions are the distributed work source. |
| Excess consumers still process the same partition in parallel. | A partition is assigned to at most one member in a group at a time. |
| Scaling up causes zero disruption. | Membership changes can trigger rebalances and temporarily lower throughput. |
| Adding partitions always fixes hot keys. | The same key can still hash to a single partition. |
| Low CPU means consumers have spare capacity. | Consumers may be blocked on I/O or downstream while CPU is low. |
| Static membership allows sharing the same ID across all pods. | Every concurrent member requires a unique group.instance.id. |
| Scaling down does not affect in-flight processing. | Stopping a pod can cause redelivery if records were not committed. |

## 22. Multi-Instance Scaling Design Checklist

Before deploying to production, confirm:

1. Replicas that need to share load use the same group ID.
2. Services needing independent copies use separate group IDs.
3. Total consumer members are calculated as replicas times concurrency.
4. Partition count is sufficient for useful parallelism.
5. Assignment strategy fits topic/partition count and client version.
6. Each consumer has an observable client identity.
7. group.instance.id, if used, is unique and stable per member.
8. Per-key ordering is preserved across producer, consumer, and retries.
9. Downstream has enough connections/capacity for total concurrency.
10. Autoscaler is based on lag/throughput and includes cooldowns.
11. Rebalances and graceful shutdown are monitored.
12. Idempotency handles duplicates after crashes/rebalances.
13. Integration tests verify partition assignment and failover.
14. Runbooks exist for scaling up/down and investigating lag.

Scaling multiple instances enables Spring Kafka to increase processing capacity and resilience by distributing partitions among consumer members in the same group. Effectiveness depends on group ID, concurrency per instance, partition count, assignment strategy, and downstream capacity. By planning these factors alongside ordering, rebalancing, offsets, and idempotency, applications can scale cleanly without adding wasted load or breaking event processing semantics.


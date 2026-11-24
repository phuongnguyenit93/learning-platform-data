# Application and Kafka Failure Domains

In Spring Kafka operations, a failure is rarely just "Kafka failed" or "the application failed." Failures typically start within a specific scope and then propagate across dependencies: a slow listener causes a consumer to miss a poll interval, the consumer leaves the group, partitions are reassigned, and lag rises; or a broker disconnects, forcing partition leaders to re-elect, producers to ramp up retries, and the application to exhaust send-waiting threads.

A **failure domain** is the scope of components that can be affected together by a single fault or common cause, along with the boundary within which we can isolate, recover, and observe. Correctly identifying failure domains helps answer four questions during design and incident response:

1. What is the smallest component that is failing?
2. Which components or data flows are impacted together?
3. Where else can the fault propagate through shared resources or dependencies?
4. To what extent can that component be recovered independently without losing or duplicating data?

The goal is not to eliminate every fault. The goal is to limit the blast radius, keep healthy parts operating, and recover data in a controlled manner.

## 1. Distinguishing Failure Domain, Failure Mode, and Blast Radius

These three related concepts are not synonymous:

- **Failure domain**: a zone sharing a common risk or failure mechanism, such as a JVM, a node, an availability zone (AZ), a broker, or a Kafka cluster.
- **Failure mode**: how a fault manifests, such as a process stopping, network loss, disk exhaustion, an unavailable leader, a listener throwing exceptions, or a database refusing connections.
- **Blast radius**: the actual scope of impact when a failure mode occurs, such as one partition being disrupted, an entire consumer group building lag, or every service sharing one database halting processing.

A single failure domain can encompass multiple failure modes. A single failure mode can also span multiple domains if components share infrastructure. For example, losing an AZ can simultaneously take out several application pods, several brokers, and part of the network infrastructure. In that case, running multiple pods still does not achieve high availability if all pods reside in the same AZ.

Do not treat logical boundaries as independent fault boundaries. Two differently named deployments may still depend on the same DNS, secret, database connection pool, NAT gateway, or Kafka cluster.

## 2. Application-Side Failure Domains

A Spring Boot application using Spring Kafka has multiple layers of failure domains. Distinguish between them because each layer recovers differently.

### 2.1 Process, JVM, and Container

This is the smallest common scope:

- A JVM can stop due to startup failures, `OutOfMemoryError`, configuration errors, library bugs, or OS termination.
- A container can be restarted due to failed health checks, exceeding memory limits, or main process exit.
- A pod can be rescheduled when a node fails or when a new version is deployed.
- Losing a consumer instance triggers a Kafka group rebalance and reassigns the partitions that instance owned.

If the application has multiple independent replicas, losing one pod usually reduces processing capacity only temporarily. However, this holds only when replicas do not share a failing dependency and remaining replicas have sufficient capacity.

When a process stops abruptly, records already read whose offsets have not been committed may be re-read after partitions are assigned to another consumer. Therefore, process fault tolerance must go hand in hand with idempotent business processing.

### 2.2 Node, Rack, Availability Zone, and Region

Pods may be independent at the process layer yet still share physical hardware or infrastructure zones:

- **Node failure** affects every pod running on that node.
- **Rack failure** can affect shared power, switches, or network links.
- **AZ failure** can take out compute, network, and storage simultaneously across a zone.
- **Region failure** can take down the entire service cluster in that region.

If all replicas of a consumer service are placed on the same node or AZ, having many replicas does not help when that failure domain is completely lost. Use topology spread constraints, pod anti-affinity, or equivalent placement mechanisms to distribute replicas across nodes/AZs. Placement must be verified against actual runtime state; declaring constraints that the scheduler cannot satisfy provides no redundancy.

### 2.3 Deployment, Configuration, and Versioning

A deployment error can turn into a failure domain for the entire service:

- A new version contains a bug causing every listener to throw exceptions.
- Misconfigured bootstrap servers, group ID, topic, or serializers prevent all instances from connecting or deserializing.
- Expired secrets or certificates cause many instances to lose authentication simultaneously.
- An incompatible feature flag or schema breaks the entire data flow.

Rolling updates reduce risk only when the older version remains healthy and can keep processing while the new version rolls out. If the same broken configuration is pushed to all replicas, rolling updates will not stop the failure from spreading.

Maintain rollback capability, versioned configuration management, schema compatibility checks, and phased small-batch rollouts. When changing Kafka configuration, distinguish errors affecting only one consumer group from errors affecting every producer or consumer sharing that configuration.

### 2.4 Listener Container, Consumer Thread, and Consumer Group

In Spring Kafka, a method annotated with **@KafkaListener** normally runs inside a listener container. The container manages the consumer, poll loop, listener invocation, error handling, and offset commits per configuration.

Key scopes:

- **Consumer thread**: a consumer executes polls and processes partitions assigned to it. A slow or blocked listener can prevent the consumer from polling on time.
- **Listener container**: manages one or more consumers depending on concurrency configuration and container type.
- **Application instance**: can run multiple containers or multiple distinct listeners.
- **Consumer group**: consumers in the same group share a topic's partitions. A group has its own offsets and assignment state.
- **Partition**: Kafka's unit of parallelism and ordering. Within a consumer group, at any given time, a partition is assigned to at most one consumer.

**@KafkaListener** `concurrency` increases the number of consumers managed by the container per application instance. With 4 pods each running concurrency 3, the group can have up to 12 active consumers. The number of consumers actually receiving partitions remains capped by the subscribed partition count. If the topic has only 6 partitions, the remaining 6 consumers will have no partitions to process in that group.

A dead consumer usually does not harm the topic or Kafka cluster. It changes the group's assignment. If multiple consumers repeatedly join and leave the group, repeated rebalances can reduce throughput and drive up lag.

### 2.5 Shared Resources Inside the Application

Pools and executors are also failure domains:

- Thread pools exhausted by hung downstream calls.
- Database connection pools depleted, preventing listeners from completing processing.
- HTTP connection pool or DNS resolver failures slowing down every record that depends on an external service.
- Heap memory, direct memory, or producer buffers growing to their limits.
- A lock or unbounded queue blocking multiple listeners.

A listener processing a record slowly does not affect only that record. If it occupies the consumer thread, other partitions assigned to the same consumer stall as well. If all listeners share one pool, a single slow downstream service can bottleneck multiple unrelated business flows.

Bound pools and queues, enforce timeouts on dependency calls, isolate pools for workloads of differing criticality, and monitor saturation. Unbounded retries can worsen resource exhaustion.

## 3. Kafka-Side Failure Domains

Kafka has multiple data and control layers. One broker is not the whole cluster, and one partition is not a broker.

### 3.1 Partition, Leader, and Replica

Topics are divided into partitions. Each partition has one leader and may have replicas on other brokers.

- Producers send records to the partition leader.
- Consumers read records from the leader per assignment and read configuration.
- Replicas keeping up with the leader can belong to the ISR (in-sync replicas) set.
- When a leader loses serving capability, Kafka can elect an eligible replica as the new leader.

One broker may serve as leader for many partitions and follower replica for many others. Hence, losing one broker can disrupt multiple partitions simultaneously without necessarily taking down the entire topic or cluster.

Replication factor dictates the configured number of copies for a partition. It does not mean all copies are always in sync. ISR reflects the replicas keeping up per cluster criteria. Replication configuration and broker placement must account for physical failure domains; placing replicas of the same partition in the same AZ provides no protection when that AZ fails.

### 3.2 Broker

A broker is a Kafka node storing partition replicas and serving requests. A broker can experience:

- Process crashes or continuous restarts.
- Full disks, filesystem errors, or high I/O latency.
- Network partitions, packet loss, or unstable connectivity.
- Overloaded CPU, memory, or request handler threads.
- Configuration, certificate, or authentication errors.

When a broker fails, partitions with replicas on that broker lose a replica; partitions led by that broker must elect a new leader if an eligible replica exists. If the cluster still has enough replicas and required quorum, data can still be served. However, reduced ISR counts may cause producers to be rejected when durability policies require sufficient replicas.

### 3.3 Controller and Metadata Quorum

Kafka requires a controller to manage cluster metadata and state transitions. On Kafka running KRaft, the controller quorum maintains the metadata log and elects the active controller.

The controller/quorum is the control-plane failure domain. Losing quorum can block operations requiring metadata updates or new leader elections. Impact on existing read/write flows depends on cluster state, though topology changes and partition recovery may stall. Therefore, monitor controller quorum separately from broker data-plane request health.

Do not conclude the cluster is completely healthy merely because some existing producers and consumers can still send/read records. The control plane may be degraded and make incident recovery much harder.

### 3.4 Topic, Quotas, and Security Configuration

Some faults are scoped to a topic or client rather than the whole cluster:

- A topic is deleted, created with too few partitions, or given inappropriate retention settings.
- ACL changes strip a principal of read, write, or describe permissions on a topic.
- Throughput quotas cause clients to be throttled.
- Incompatible schema or serializer changes.
- Consumer groups using the wrong group ID or subscribing to the wrong topic.

An ACL error on one service account can halt one application while another continues normally. Conversely, modifying a shared ACL or credential can affect multiple services. Manage identities and permissions per service, topic, and environment; avoid sharing one principal across all applications.

### 3.5 Cluster, AZ, and Region

A Kafka cluster is a large failure domain because many topics and consumer groups depend on it. If the cluster fails completely, producers cannot write and consumers cannot continue reading from that cluster.

In-cluster replication protects against certain broker failures, but does not automatically protect against losing an entire cluster or region. Recovering in another region requires a dedicated disaster recovery strategy, such as cross-cluster replication via MirrorMaker 2 or an equivalent solution, producer/consumer cutover procedures, offset management, and failover testing.

Cross-cluster replication does not automatically yield a safe active-active system. Clearly define the primary write site, conflict resolution, ordering consistency, group offset translation, RPO, and RTO.

## 4. Viewing Failure Domains Across the Entire Data Flow

A record typically crosses multiple boundaries. The diagram below helps pinpoint where a record can be blocked, lost, or processed repeatedly.

~~~mermaid
flowchart LR
    P["Producer process"] --> C["Client: serialize, buffer, metadata"]
    C --> N["Network, DNS, TLS, ACL"]
    N --> K["Kafka broker: partition leader"]
    K --> R["Partition replicas / ISR"]
    R --> G["Consumer group assignment"]
    G --> L["Spring listener container"]
    L --> A["Application business logic"]
    A --> D["Database or downstream service"]
    L --> O["Offset commit"]
~~~

Every arrow is a boundary where faults can arise. Examples:

- Producer serialization fails: the record is never sent to Kafka.
- Producer sends but receives no ACK before timeout: the outcome may be ambiguous to the application; retries may be needed and must be guarded by idempotence.
- Broker receives the record but replicas do not meet minimum ISR: writes may be rejected when an appropriate durability policy is active.
- Consumer reads the record but the listener fails: the record may be retried, moved to a retry topic/DLT, or continue blocking the partition depending on the error handler.
- Business logic writes to the database successfully, but the process crashes before committing the offset: the record may be re-read and write to the database again.
- Offset commit succeeds before the business effect completes: a subsequent error may prevent the record from being reprocessed.

Therefore, monitor both Kafka state and business processing state. Zero consumer lag does not prove data was written accurately to the database; a producer receiving an ACK does not prove downstream finished its work.

## 5. Failure Domains on the Producer Path

Producers have multiple independent points of failure:

1. The application fails to construct the event or serialize the payload.
2. The client fails to fetch metadata, authenticate, or connect to brokers.
3. Producer buffers fill up because brokers are slow or the network is disrupted.
4. The partition leader is unavailable or replicas fail to satisfy ACK requirements.
5. The application times out and decides to retry or report an error.

### 5.1 ACK and Durability

ACK options carry distinct meanings:

- **acks=0**: producer does not wait for broker acknowledgement. Throughput may be high, but the application does not know whether the broker received the record.
- **acks=1**: leader acknowledges after writing locally. If the leader fails before other replicas obtain the data, the record may be lost.
- **acks=all**: leader waits for replicas currently in the ISR to acknowledge per the replication protocol. This is the common choice for critical data.

**acks=all** must be combined with **min.insync.replicas**. For example, a topic with replication factor 3 and **min.insync.replicas=2**: when at least 2 ISRs remain, producers can write per policy; when ISR drops below 2, the broker rejects writes instead of silently degrading durability. The application must handle that write error and have a bounded retry mechanism.

**acks=all** does not mean every configured replica must ACK. It applies to the ISR at the time of the write. Replication factor, min ISR, and replica placement must be designed together.

### 5.2 Idempotent Producer and Retries

Enabling an idempotent producer helps Kafka eliminate duplicate records arising from producer retries within the same producer session via sequence numbers. This is an important safeguard when networks are flaky or ACKs are delayed.

However, idempotence does not replace business-layer idempotency. If the application restarts and actively resends the same business command as a new send, Kafka cannot automatically tell it is the same business operation. Use a stable event ID or business key so downstream can detect and deduplicate repeated processing.

Retries must have an overall time bound. If the producer keeps retrying during an extended broker or network outage, queued requests can exhaust buffers and starve application resources. Balance **delivery.timeout.ms**, request timeouts, retries, and external caller timeouts.

### 5.3 Transactional Outbox

If a business operation both updates a database and publishes a Kafka event, the two independent operations can diverge:

- The database commit succeeds, but the Kafka send fails.
- Kafka receives the event, but the database rolls back.

Kafka transactions do not automatically create an atomic transaction between Kafka and a relational database. Transactional outbox solves this by writing business data and an outbox row within the same database transaction; a separate publisher reads the outbox and sends events to Kafka. Because the publisher can send duplicates, consumers still need idempotency or deduplication.

## 6. Failure Domains on the Consumer Path

A consumer can read a record successfully yet fail to complete the business effect. Clearly separate three actions: polling records, processing business logic, and committing offsets.

### 6.1 Offsets and Commit Timing

With at-least-once processing, the application typically completes the business effect first and commits the offset afterward. If the process crashes between the two steps, the record is re-read. This prioritizes avoiding record loss while requiring safe duplicate handling.

If offsets are committed before the business effect completes, a process crash after commit can cause the record to be skipped on the next read. Hence, commit timing must align with business requirements.

In Spring Kafka, choose an appropriate ack mode, disable auto commit so the container manages commits, and use manual acknowledgement only when the application truly needs explicit control over confirmation timing. Manual acks in the wrong place can cause data loss or unpredictable duplicate processing.

### 6.2 Consumer Rebalances

Rebalances occur when group membership, subscriptions, or assignments change. Common causes include:

- Pods being deployed or restarted.
- Consumers losing connectivity or heartbeats.
- Listeners taking too long, exceeding poll limits.
- Consumer counts changing due to autoscaling.
- Topic partitions increasing or subscriptions changing.

During a rebalance, partitions may temporarily go unprocessed. If a consumer has not committed offsets for already-processed records, those records may be redelivered. Continuous rebalances cut useful processing time and increase lag.

Set **max.poll.interval.ms** based on realistic batch processing duration, records per poll, and downstream latency. Increasing this value does not cure an indefinitely hung listener; enforce timeouts and duration limits on every dependency.

### 6.3 Poison Messages and Business Errors

A poison message is a record that consistently fails processing, such as malformed payloads, missing required fields, or unconvertible data. If retried indefinitely on the same partition, one record can block every subsequent record on that partition.

Classify errors:

- Transient errors: timeouts, database unavailable, rate limits, or network glitches. Can be retried with backoff.
- Unrecoverable data or business errors: invalid payloads, incompatible schemas, or invariant violations. Usually should go to a DLT after an appropriate retry count.
- Widespread configuration or authentication errors: do not hammer retries per record; alert and restore the configuration or credentials.

A DLT isolates failing records so the main partition keeps moving, but a DLT is also an operational component: it requires retention, ACLs, replication, monitoring, investigation procedures, and controlled replay capabilities. Never treat sending to a DLT as business completion.

### 6.4 Blocking Retry and Retry Topics

There are two common approaches:

- **Blocking retry**: the listener container retries the record on the current processing thread. This preserves per-partition ordering better, though a failing record can block the partition during retries.
- **Non-blocking retry / retry topic**: moves the record to a retry topic with a wait delay and reprocesses it later. This avoids holding the consumer thread, though later records may be processed before a record awaiting retry. If business logic strictly requires per-key ordering, design carefully.

Choose a strategy based on ordering requirements, expected recovery time, retry counts, and lag tolerance. Avoid stacking unbounded retries across multiple layers—such as HTTP client retries, listener retries, and retry topics multiplying downstream calls.

## 7. Spring Kafka: Mapping Failure Domains to Configuration

Spring Kafka provides consumer management and error-handling abstractions, yet framework configuration alone does not create high availability. Understand which boundary each setting affects.

### 7.1 Listener Concurrency and Partitions

Example listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service",
    concurrency = "3"
)
public void handle(OrderCreated event) {
    billingService.process(event);
}
~~~

Concurrency creates multiple consumers for the listener container. Increasing concurrency increases parallelism only when enough partitions and processing resources exist. With 4 pods each having concurrency 3, the group can have up to 12 consumers; how many receive partitions remains capped by the partition count. Scaling pods and concurrency far past the partition count yields idle consumers that add no throughput. If all consumers call an already overloaded database, increasing concurrency spreads the database failure domain faster.

Clarify:

- Topic partition count.
- Number of pods and concurrency per pod.
- Actual consumer count in the group.
- Database and downstream load capacity.
- Partition/key ordering requirements.

### 7.2 Baseline Producer and Consumer Configuration

Illustrative Spring Boot configuration for a flow requiring data durability and container-managed commits:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
        delivery.timeout.ms: 120000
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.interval.ms: 300000
        max.poll.records: 100
    listener:
      ack-mode: record
~~~

This is a starting point, not a one-size-fits-all configuration. Tune timeouts, records per poll, ack mode, and producer delivery timeout based on latency, record size, processing time, and SLAs. Consumer configuration must match how the listener processes records and commits offsets.

### 7.3 Exception Handling and Dead Letter Topic

**DefaultErrorHandler** can be configured with **DeadLetterPublishingRecoverer** for bounded retries before routing unrecoverable records to a DLT. Illustrative example:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                new TopicPartition(
                    record.topic() + ".DLT",
                    record.partition()
                )
        );

    DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
        );

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

The example assumes the DLT has already been created with enough partitions matching the source partitions. If the DLT lacks the target partition, DLT publishing can fail. In real systems, configure the error handler on the appropriate listener container factory, classify exceptions per business rules, and verify DLT publish outcomes.

Key notes:

- Do not place every exception in the non-retryable group; transient database errors can recover.
- Do not infinitely retry unfixable data errors.
- Ensure the DLT has replication, retention, ACLs, and alerts.
- Preserve error metadata, original topic/partition/offset, and correlation/event IDs for investigation.
- Replay DLTs in a controlled manner, avoiding bulk bursts that overload downstream.

### 7.4 Retry Topics

Spring Kafka supports non-blocking retry topics via **@RetryableTopic**. This model fits when you want to decouple retry wait times from the main consumer thread. Create and manage retry topics/DLT, and define attempt counts, backoff, partitioning, and retention. Check ordering impacts: retried records may be processed after newer records on the source partition.

### 7.5 Kafka Transactions and Exactly-Once Limits

Kafka transactions can combine consuming records, producing other records, and committing offsets within the same Kafka transaction. This is useful for consume-transform-produce flows and supports exactly-once semantics within Kafka's scope when properly configured.

However, if the listener updates a database or calls an external API, Kafka transactions do not make those side effects part of an atomic transaction. Use idempotency keys, inbox/outbox, or appropriate coordination mechanisms for side effects outside Kafka.

## 8. Incident and Impact Scope Matrix

| Incident | Direct Failure Domain | Typical Symptoms | Remediation Direction |
|---|---|---|---|
| A consumer pod stops | Pod / consumer member | One member leaves group, rebalance, temporary lag bump | Recover pod; check restart reason; confirm partitions reassigned |
| Listener processes too slowly | Consumer thread / group | Poll gaps, rebalances, rising lag, downstream timeouts | Find slow calls; enforce timeouts; reduce batch/concurrency if needed |
| One record consistently fails | Record / partition | Repeated retries, stalled partition, or rising DLT | Classify error; route failing record to DLT; fix data/logic then replay |
| Database runs out of connections | Shared pool or database | Widespread listener timeouts, rising pool pending count | Recover database/pool; cap concurrency; apply backpressure |
| One broker stops | Broker and its partition replicas | Leader elections, shrunk ISR, request errors or higher latency | Check broker, disk, network; recover broker; monitor ISR and partitions |
| ISR below min ISR | Partition durability boundary | Producers receive insufficient-replica errors | Recover replicas/broker; do not lower durability hastily without risk review |
| Controller quorum lost | Kafka control plane | Metadata/leader changes stalled | Check quorum and controller nodes; restore quorum per runbook |
| Bad credentials/ACLs | Principal or client group | Authentication/authorization errors | Restore scoped secret/ACL; avoid aggressive retries |
| Incompatible topic or schema | Topic / inter-service contract | Serialization/deserialization errors, consumers unable to process | Restore compatible contract; control rollout and replay |
| Entire AZ outage | AZ | Multiple pods/brokers/network dependencies lost together | Shift capacity to remaining AZs; verify replicas and load tolerance |
| Kafka cluster outage | Cluster | Producers cannot write, consumers cannot read | Activate DR/failover; check RPO/RTO and cutover procedures |

The table above describes typical symptoms. A single symptom is insufficient to conclude root cause. For instance, rising consumer lag can result from a stopped consumer, slow downstream, partition load spike, continuous rebalancing, or sudden producer throughput surge.

## 9. Designing to Limit Blast Radius

### 9.1 Distribution and Redundancy

- Run multiple application replicas across different nodes/AZs.
- Spread Kafka brokers and partition replicas across racks/AZs matching physical topology.
- Maintain replication factor and min ISR aligned with acceptable data loss tolerance.
- Avoid tying all service accounts, secrets, or gateways to a single administrative point of failure.
- Verify remaining capacity when losing a node or AZ; redundancy matters only if the remainder can handle the load.

### 9.2 Bulkheads and Resource Limits

Isolate resources by workload or dependency so one slow group of requests does not consume all threads, connections, and queues. Use bounded queues, bounded thread pools, explicit timeouts, and backpressure. Monitor both pool utilization and wait times.

For listeners, balance concurrency against partition count and downstream capacity. If a database can sustain only a certain concurrency level, total concurrent consumers must stay within that bound or be throttled.

### 9.3 Controlled Retries

Retries help only when faults are recoverable. Retry designs should include:

- Finite attempt counts.
- Backoff, usually with jitter when multiple clients may retry concurrently.
- Overall timeout across the entire processing chain.
- Classification of transient vs. unrecoverable errors.
- Mechanisms to halt or back off retries when dependencies are overloaded.
- Monitoring retry counts and DLT ingress rates.

Unbounded retries can trigger a retry storm: right as the database recovers, masses of consumers retry simultaneously and overload the database again.

### 9.4 Schema Compatibility and Safe Deployments

Schema evolution must enforce compatibility rules between concurrently running producers and consumers. Whether to deploy producer or consumer first depends on change type; ensure old and new versions can co-read/write across the rollout window. Incompatible changes should roll out in multiple phases with tests and a rollback plan.

Do not change topics, partitioning keys, or serialization formats without assessing impact on ordering, load distribution, consumer assignment, and replayability.

### 9.5 Cross-Cluster Disaster Recovery

For recovery requirements after losing a cluster or region, define upfront:

- **RPO**: maximum acceptable data loss measured in time.
- **RTO**: target duration to restore service.
- Which cluster serves as the primary write source.
- How required topics and metadata are replicated.
- How producer bootstrap servers and consumer groups cut over.
- How offsets, duplicate records, and late-arriving records are handled.
- Who holds authority to trigger failover and criteria for failback.

Cross-cluster replication does not automatically produce a safe active-active system. Clearly define the primary write site, conflict resolution, ordering consistency, group offset translation, RPO, and RTO. Conduct periodic failover drills. An untested cross-cluster replication setup does not prove the application can fail over during an incident.

## 10. Observing Failure Domains with Metrics and Logs

Group signals by boundary for rapid isolation.

| Layer | Signals to Track |
|---|---|
| Application process | Restart count, exit reason, heap, GC pauses, CPU, memory, thread count |
| Listener/container | Listener error rate, processing duration, poll interval, active consumer count, rebalance count |
| Consumer group | Lag by group/topic/partition, commit failures, partition assignment, time without progress |
| Producer | Send errors, retry count, request latency, record error rate, buffer availability, timeouts |
| Kafka broker | Broker availability, request handler saturation, network processor idle, request latency, disk usage and I/O |
| Partition/replication | Under-replicated partitions, under-min-ISR partitions, offline partitions, ISR shrink/expand, leader elections |
| Controller | Controller/quorum health, metadata operation latency, controller election status |
| Downstream | Database connection pool, query latency, timeouts, error rate, queue depth, and saturation |
| Retry/DLT | Retry topic lag, DLT publish failures, DLT record rate, age of oldest record |

Observability principles:

- Measure lag per partition, not just group totals; one stuck partition can be masked by other healthy partitions.
- Correlate consumer lag with produce rate and processing rate. Lag growing due to producer load spikes differs from lag growing due to degraded consumer capacity.
- Propagate correlation IDs or event IDs end-to-end across producer, Kafka headers, listener, and downstream logs.
- Log topic, partition, offset, group ID, exception class, and retry attempt when handling errors.
- Alert on lack of progress duration and record age alongside absolute lag counts.
- Avoid alerting only when processes die; a live process whose listener stops processing records is also an incident.

## 11. Isolation Procedure During an Incident

When an alert fires, trace from symptom to fault boundary in order:

1. **Identify the affected flow**: which producer, topic, consumer group, business workflow, and start time.
2. **Determine scope**: one record, one partition, one consumer member, one pod, one service, one broker, one AZ, or the entire cluster.
3. **Locate the last point of progress**: producer send/ACK, last committed offset, last successfully processed record, and last database side effect.
4. **Cross-check both sides**: producer rate, broker health, ISR/leaders, consumer assignment/lag, listener errors, and downstream latency.
5. **Check shared causes**: recent deployments, config, credentials, DNS, network, quotas, databases, or schemas.
6. **Mitigate impact**: halt faulty rollouts, lower concurrency if downstream is overloaded, isolate dependencies, or route failing records to DLT per runbook.
7. **Recover and verify**: confirm partitions have leaders, ISR recovered, consumers make progress, lag shrinks, and business effects persist accurately.
8. **Close incident with evidence**: document root cause, actual failure domain, scope of affected data, and preventive actions.

Do not immediately scale up consumers when seeing lag. If the database is the bottleneck, increasing concurrency hits the database harder. Likewise, never lower **min.insync.replicas** or change ACK policy merely to clear producer errors without evaluating data loss risk.

## 12. Testing Fault Isolation Capabilities

A system proves its failure domain boundaries only when each boundary is deliberately tested under controlled fault injection. Drills can include:

- Stopping one consumer pod and confirming partitions reassign, uncommitted records are re-read, and business effects are not duplicated.
- Slowing down the database or downstream service to verify timeouts, bulkheads, backpressure, and concurrency caps.
- Sending an invalid record to confirm bounded retries, DLT capture, and continued progress on the partition.
- Stopping one broker in a test environment to observe leader election, ISR, and producer errors.
- Inducing ISR shrinkage to verify **min.insync.replicas** protects durability as expected.
- Testing expired credentials or misconfigured ACLs in a staging environment to validate alerts and recovery steps.
- Drilling single-AZ loss or DR cluster cutover if required by SLA.

Each drill needs a hypothesis, scope, abort conditions, test data, and success criteria. For example: "When losing one consumer pod, its partitions reassign within target time; no ACKed records are lost; uncommitted records may be reprocessed without duplicate side effects."

Never run fault injection in production without approval, bounded scope, and clear kill switches. Update runbooks, dashboards, and alert thresholds from drill findings.

## 13. Design and Operations Checklist

**Application**

- [ ] Replicas are distributed across nodes/AZs per infrastructure capability.
- [ ] Appropriate readiness/liveness probes exist and restart reasons are understood.
- [ ] Listener concurrency aligns with partition count and downstream capacity.
- [ ] Pools, threads, and queues are bounded; dependencies have timeouts.
- [ ] Offset commits align with business effect completion timing.
- [ ] Business operations carry idempotency keys or deduplication mechanisms.
- [ ] Retries are bounded, exceptions are classified, and a DLT/replay runbook exists.

**Kafka**

- [ ] Replication factor, min ISR, and ACK policies match durability requirements.
- [ ] Replicas of the same partition are spread across physical failure domains.
- [ ] Brokers, disks, network, partitions, and controller/quorum have dedicated dashboards.
- [ ] ACLs, credentials, and quotas are managed per service/topic.
- [ ] Topics have governed partition counts, retention, and schema compatibility.
- [ ] DLTs and retry topics have replication, retention, access controls, and alerts.

**End-to-End System**

- [ ] A map exists for producer → topic/partition → consumer group → downstream.
- [ ] The last created, read, processed, and committed record can be determined.
- [ ] Alerts exist for lag, record age, rebalances, retries, and DLT.
- [ ] Runbooks exist for broker loss, pod loss, downstream outage, and credential failure.
- [ ] RPO/RTO and DR procedures are defined, and drilled if SLA requires.
- [ ] Drills prove isolation and recovery against concrete criteria.

Failure domains are a tool for designing and operating reliability. When each boundary has a clearly defined blast radius, observability signals, isolation controls, and recovery procedures, a local fault is far less likely to escalate into a system-wide Spring Kafka outage.


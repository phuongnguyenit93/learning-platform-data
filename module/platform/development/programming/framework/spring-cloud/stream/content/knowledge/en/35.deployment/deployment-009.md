# Recovering from Broker Loss, Instance Loss, or Full Disks

## 1. Recovery Is Part of Deployment Design

A Spring Cloud Stream application processes events through `Supplier`, `Function`, and `Consumer` functions connected to Kafka, RabbitMQ, or Pulsar via bindings and binders. In production deployments, losing broker connectivity, losing an instance mid-processing, or running out of disk space are normal failure modes that require upfront planning, not improvisation after the fact.

Resilience is more than restarting containers. A system is considered recovered only when:

- Connectivity to the broker and critical dependencies is restored.
- Producers send and receive confirmations per the designed durability guarantees.
- Consumers resume reading messages from the right offset, queue, or subscription.
- Incomplete messages are reprocessed or moved to a managed error state.
- No data is lost beyond the accepted RPO; duplicates are identified and handled safely.
- Backlogs drain within target timelines and operational metrics return to normal.

The three failure classes covered in this lesson have very different boundaries: a **broker outage** affects message storage and distribution infrastructure; an **instance outage** affects application consumers/producers; **disk full** can happen on the broker, storage nodes, or the application itself.

~~~mermaid
flowchart LR
    P[Producer / Supplier] --> B[(Kafka / RabbitMQ / Pulsar)]
    B --> C1[Consumer instance A]
    B --> C2[Consumer instance B]
    C1 --> D[(Database / downstream)]
    C2 --> D
    B -. Broker unavailable .-> F1[Broker recovery]
    C1 -. Pod crash .-> F2[Instance recovery]
    B -. Storage full .-> F3[Disk capacity recovery]
    F1 --> R[Verify offsets, backlog and outcomes]
    F2 --> R
    F3 --> R
~~~

In production, always weigh data durability, business consistency, and availability together. Never casually delete logs, lower durability, or disable authentication merely to silence alerts.

## 2. Distinguishing Availability, RTO, and RPO

A recovery runbook needs measurable outcome definitions:

| Concept | Interpretation | Illustrative Target Example |
|---|---|---|
| Availability | The system can receive/process requests or messages per commitment | At least one valid processing path exists |
| RTO (Recovery Time Objective) | Target time to restore service after an incident | Under 15 minutes |
| RPO (Recovery Point Objective) | Maximum acceptable data loss, measured in time | 0 for broker-acknowledged events, if durability configs meet requirements |
| Recovery backlog | Messages accumulated during the outage | Does not exceed storage and processing limits |
| Backlog drain time | Time to reduce backlog below threshold after the system is healthy | Under 20 minutes |
| Delivery guarantee | At-most-once, at-least-once, or specific pipeline semantics | At-least-once with idempotent side effects |

Numbers in the table are **design examples**, not default guarantees of any broker or binder. An RPO of 0 can only be claimed after verifying replication, acknowledgment, durability configurations, and failure scopes. For side effects in databases or external services, a durable broker does not automatically provide an end-to-end pipeline transaction.

Separate the moment **the broker becomes reachable again** from the moment **the backlog finishes draining**. An alert may clear as soon as networking recovers while business SLAs are still breached due to excessive message age.

## 3. Failure Model: Where Can Things Break?

A message typically passes through these steps:

1. Producer builds the event and sends it to the broker.
2. Broker persists and confirms according to durability settings.
3. Consumer receives the event and starts processing.
4. Handler writes to a database or calls a downstream service.
5. Handler finishes; producer emits output if any.
6. Offset is committed or message is acknowledged.

Failures can occur between any two steps. Therefore, ask **what state is the message currently in?** before re-running anything:

| Failure Point | Possible Consequence | Evidence to Collect |
|---|---|---|
| Before broker ack | Producer does not know whether the message was persisted | Producer exceptions, sequence/event IDs, broker logs |
| After broker ack, before consumer handling | Message remains in backlog | Offsets/queue/subscription cursors |
| After side effect, before consumer ack | Message may be redelivered; duplicate side effect | Business transactions, event IDs, acks/commits |
| While publishing output | Output may be unsent or sent with lost ack | Output topic/queue, producer acks, correlation IDs |
| During retry or DLQ | Message may be stuck in retry/DLQ | Retry attempts, DLT records, consumer health |

Recovery procedures must preserve the ability to reconcile those states. Never delete consumer groups, queues, state directories, or log segments before confirming whether they hold data needed for recovery.

## 4. Three Incident Classes and First-Response Priorities

| Incident | Common Symptoms | First Action |
|---|---|---|
| Loss of one Kafka broker | Partition leaders shift, producer timeouts, lag rises | Check replication/ISR, leader status, cluster scope |
| Loss of a RabbitMQ node | AMQP reconnects, quorum leaders move, queues may become unavailable | Check cluster health, quorum majority, and queue state |
| Loss of a Pulsar broker | Client reconnects, brief lookup/producer/consumer errors | Check broker ownership, BookKeeper, and metadata |
| Loss of an application instance | Pod restarts, rebalancing, unacked redeliveries | Check surviving instances, assignments, and handler idempotency |
| Broker disk full | Write errors, message publishing blocked, ledgers fail to create | Identify node/filesystem, stop load growth, restore capacity safely |
| Application disk full | Log errors, Kafka Streams state restoration fails | Check state/log volumes and active write operations |

Initial triage must distinguish a **single-component failure** from **loss of majority/quorum**. "One broker down" in a fully replicated cluster does not equal total cluster unavailability.

## 5. Monitoring Signals Needed Before an Incident Happens

Reliable recovery is impossible if you do not know where processing stopped. Collect and alert on:

- **Broker:** Node availability, partition/queue/ledger health, leaders/quorum, write latency, throttling, disk utilization, free bytes, and disk I/O latency.
- **Kafka:** Offline partitions, under-replicated partitions, ISR shrinks, controller/leader changes, producer errors, and consumer lag by partition/group.
- **RabbitMQ:** Disk/memory alarms, blocked connections, ready/unacked messages, quorum queue member/leader state, publisher confirms, and consumer counts.
- **Pulsar:** Broker connectivity, BookKeeper bookie health, ledger write errors, backlogs, subscription dispatch/redelivery, and storage free space.
- **Application:** Binding state, producer send failures, handler latency, error rates, JVM GC/heap, restart counts, and readiness.
- **Business:** Successfully processed `eventId`s, duplicate side effects, DLQs, message age, and end-to-end duration.

Distinguish **transient errors auto-retried by clients** from **prolonged incidents requiring intervention** using duration thresholds and trends. Error spikes lasting a few seconds may accompany leader elections; backlog climbing steadily over minutes signals insufficient capacity.

## 6. General Runbook: Detect, Isolate, Recover, Verify

Following this sequence reduces the risk of making things worse:

~~~mermaid
flowchart TD
    A[Alert: broker / pod / disk] --> B[Identify scope and last-known-good]
    B --> C[Preserve evidence, check data durability]
    C --> D{Risk of further data loss?}
    D -->|Yes| E[Throttle ingress / pause unsafe writes]
    D -->|No| F[Prepare supported recovery action]
    E --> F
    F --> G[Recover quorum / process / capacity]
    G --> H[Verify producer and consumer continuity]
    H --> I[Reconcile event IDs and drain backlog]
    I --> J[Observe SLO and close incident]
~~~

Execute sequentially:

1. Record timestamp, alerts, affected brokers/instances/volumes, and topic/queue scope.
2. Assess replication, quorum, unacked data, and retention/backlog status.
3. If further data loss or cascading disk exhaustion threatens, throttle ingress or isolate failing flows; do not delete data manually.
4. Choose a recovery action **supported** by the broker, orchestrator, and storage platform.
5. Verify connectivity, producer confirmations, consumer assignments, and message processing.
6. Measure backlog drain, inspect DLQs/retries, and reconcile `eventId`s.
7. Close the incident only when data integrity, performance, and availability all meet criteria.

Do not restart an entire cluster to fix one unhealthy Pod without evidence that the remaining components are impaired as well.

## 7. Kafka: Losing One Broker When Data Is Replicated

Kafka topics can have multiple replicas across brokers. With a replication factor greater than one, losing a broker lets leadership elect from surviving replicas and producers/consumers reconnect to the new leader automatically.

Typical durability configuration example:

~~~text
replication.factor = 3
min.insync.replicas = 2
producer acks = all
unclean.leader.election.enable = false
~~~

These values express clear intent: confirm writes only when minimum ISR is met; do not elect out-of-sync replicas as leaders just to boost availability. This is not a magic guarantee against all failures, especially if replicas share nodes/zones or suffer correlated faults.

When a broker stops:

- Check partition leaders and remaining ISR counts.
- Check whether producers are retrying around leader changes or timing out persistently.
- Check consumer group rebalancing and per-partition lag.
- Ensure surviving brokers are not saturated on disk/network from extra load.
- Bring the failed broker back via operational procedures and watch replica catch-up before declaring the cluster healthy.

Never lower `min.insync.replicas` or enable unclean leader election solely to clear producer errors without explicitly accepting the data loss risk.

## 8. Kafka: When Too Many Replicas or Leaders Are Lost

If ISR falls below `min.insync.replicas`, producers with `acks=all` may receive errors like `NotEnoughReplicas` or `NotEnoughReplicasAfterAppend`. That usually indicates the broker refusing to acknowledge writes that fail the durability threshold.

Remediation approach:

1. Identify affected partitions, current ISR, and brokers holding replicas.
2. Check whether brokers went down due to networking, disks, JVM crashes, TLS, or storage failures.
3. Restore healthy replicas/brokers before increasing load.
4. If replicas remain insufficient, keep writes degraded or temporarily throttle ingress per runbook.
5. Once ISR recovers, verify producers can write and receive acknowledgments again.

In rare catastrophic events, an organization may have to weigh recovery actions carrying data-loss risk. Such decisions require formal approval, explicit RPO sign-off, and reconciliation plans—never treat them as routine troubleshooting steps.

## 9. Kafka: Producer Retries Do Not Equal Exactly-Once Processing

Kafka producers can retry on network glitches or leader changes. Producer idempotence, sequence numbers, and delivery settings reduce duplicates during retries within the producer's protocol scope.

However:

- A producer that never receives an ack may not know for sure whether the previous message was persisted.
- When an application re-emits a **business event** after restarting, it looks like a brand-new message to producer idempotence even with the same payload.
- After a crash, a consumer may reprocess messages whose offsets were not committed.
- Side effects outside Kafka such as database writes, REST API calls, or emails are not automatically protected by Kafka transactions.

Therefore, attach a stable `eventId`; consumers handle duplicates safely via unique constraints, inbox/deduplication tables, or appropriate business keys. For transactional Kafka-to-Kafka pipelines, configure and test transactions/offset commits against your exact binder version and topology.

## 10. Kafka Consumers: Instance Loss and Rebalancing

Consider a 6-partition topic with a 3-instance consumer group; each instance handles two partitions. When one instance crashes, the Kafka group coordinator reassigns its partitions to surviving instances.

~~~mermaid
flowchart LR
    T[(orders.events: six partitions)] --> G[Consumer group]
    G --> A[Instance A]
    G --> B[Instance B]
    G --> C[Instance C]
    B -. Crash .-> R[Rebalance]
    R --> A
    R --> C
~~~

During assignment handoff, processing may pause briefly. Processed messages whose offsets were not committed will be re-read after rebalancing. Unprocessed messages remain in the Kafka log as long as retention has not expired them.

To recover safely:

- Run multiple instances for availability; avoid placing all instances on the same node.
- Design idempotent handlers.
- Commit offsets only after completing protected processing, per binder semantics.
- Bound handler durations and tune poll/session timeouts properly.
- Monitor rebalance duration, lag, and duplicate side effects.

Adding consumer replicas can help clear backlogs if spare partitions and downstream headroom remain; adding replicas beyond the group's partition count does not scale parallelism linearly.

## 11. RabbitMQ: Node Loss and the Role of Quorum Queues

RabbitMQ uses exchanges, queues, publisher confirms, and consumer acknowledgments. With a single-copy classic queue on one node, losing that node can make the queue unavailable; durability also depends on queue type, storage, and operational setup.

Quorum queues use a replica set and consensus to maintain state. When one member is lost while a majority stays healthy, the queue can continue serving after electing/transferring leadership appropriately. When majority is lost, do not assume the queue can accept writes normally.

When a node fails:

1. Check RabbitMQ cluster health and node membership.
2. Check queue types, replica membership, quorum majority, and leader status.
3. Verify connections/channels are reconnecting.
4. Check publisher confirms, ready/unacked messages, and redeliveries.
5. Recover the node or replace members per supported quorum queue procedures.

Never delete queues or force cluster resets before verifying majority status and which replicas still hold data.

## 12. RabbitMQ: Publisher Confirms and Consumer Acks Across Restarts

Persistent messages in durable queues improve durability, yet do not replace publisher confirms—especially when you need certainty about how far the broker accepted storage responsibility.

Critical scenarios:

| Scenario | Possible Outcome |
|---|---|
| Producer publishes then disconnects before confirm | Unclear whether publish succeeded; verify and retry safely |
| Consumer receives message then crashes before ack | Broker may redeliver to another consumer |
| Consumer writes to DB successfully yet ack never reaches broker | Message may be redelivered and cause duplicate side effects |
| Quorum queue loses majority | Queue may become unavailable for writes/processing under quorum rules |

Consumers must handle repeats; producers/bridges must reconcile by message ID. When using the Spring Cloud Stream Rabbit binder, verify that configured publisher confirms and retry/error handling truly match business delivery guarantees.

## 13. Pulsar: Broker Loss Differs from BookKeeper Loss

Pulsar separates stateless serving brokers from persistent BookKeeper storage (bookies). Losing one Pulsar broker shifts topic ownership; clients look up/reconnect to another broker and continue reading/writing if metadata and storage remain healthy.

Conversely, losing too many bookies or encountering ledger/write quorum failures can prevent safe data writes. Never assume "brokers are up so topics can write."

When handling a Pulsar outage:

- Separate broker service faults from metadata/coordination and BookKeeper issues.
- Inspect broker ownership, client lookup/reconnects, topic backlogs, and subscription cursors.
- Confirm enough writable bookies remain to satisfy configured write/ack quorums.
- Verify broker-acknowledged messages remain readable after restoration.
- Monitor redeliveries and timeouts; never skip duplicate-message protection.

Recovery must follow the operational docs of your Pulsar/BookKeeper cluster, especially when replacing bookies, recovering ledgers, or handling failed disks.

## 14. Application Instance Loss: Three Failure Windows to Know

When a Spring Cloud Stream Consumer is killed, restarted, or rescheduled by an orchestrator, three failure windows commonly arise:

1. **Before starting side effects:** The message was not processed; a new consumer must pick it up.
2. **After side effects succeed but before offset commit/ack:** The message may be redelivered, causing duplicates if idempotency is missing.
3. **After commit/ack but before sending a downstream output:** Without a shared transaction across both steps, downstream may miss expected results.

For example, a consumer receives `OrderPaid`, records `Paid` in the database, and crashes before committing the Kafka offset. After rebalancing, the same event runs again. If the payments table enforces a unique constraint on `paymentEventId`, the second attempt is recognized instead of charging twice.

Key takeaway: restarts only restore the worker process; **event state and business consistency** must be protected by pipeline design.

## 15. Kubernetes Liveness, Readiness, and Startup Probes

Kubernetes uses three probes for distinct purposes:

- **Liveness:** Is the process alive locally, or severely wedged and needing a restart?
- **Readiness:** Is the Pod ready to receive traffic or participate in coordinated routing?
- **Startup:** Grants slow-starting or slow-restoring apps time to finish before liveness kicks in.

Never let brief broker outages trigger mass liveness failures: if every Pod restarts over the same failing broker, a restart loop can worsen recovery. Understand how readiness applies to message listeners; Kubernetes readiness mainly governs Service endpoints and does not automatically pause consumers across all binders.

Actuator HTTP probe configuration example:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Illustrative Kubernetes manifest snippet placed inside the Deployment's container spec:

~~~yaml
terminationGracePeriodSeconds: 75
containers:
  - name: order-processor
    image: registry.example/order-processor:1.0.0
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
~~~

Enable and expose the endpoints per your environment's security policy. Startup, shutdown, and probe timings are examples; measure real restore/teardown times to size values and avoid killing processes mid-message.

## 16. Graceful Shutdown to Reduce Redeliveries

Upon receiving `SIGTERM` during a rolling update or scale-down, the application should:

1. Stop accepting or generating new work per binder/consumer capabilities.
2. Let in-flight messages finish within a bounded window.
3. Ack/commit completed messages according to the active mechanism.
4. Close managed producers/consumers, connections, and resources.
5. Hand off partitions or let the broker redeliver unfinished messages.

Shutdown timeouts must fit handler execution times, backoffs, and broker client closure; do not expect every callback to stop cleanly instantaneously. If a process gets `SIGKILL` after the grace period expires, unacked/uncommitted messages may be reprocessed.

`PodDisruptionBudget` and rolling update strategies limit simultaneous Pod losses, yet do not replace replication, idempotency, or broker recovery capabilities.

## 17. Kafka Streams: Losing an Instance with State Stores

Kafka Streams applications using `KTable`, aggregations, or windows maintain local state stores backed by changelog/repartition topics in Kafka. When a Pod is lost, tasks shift to another instance; state stores must restore before tasks can process accurately.

Distinguish:

- **Local state directory:** Instance-local processing state/copy, potentially lost when a Pod is replaced.
- **Changelog topic:** Authoritative state recovery source in Kafka Streams when configured with proper retention.
- **Standby tasks:** Can cut recovery time under suitable conditions, at the cost of extra resources and requiring configuration and testing.

When using ephemeral volumes for state, tasks may need to restore large data volumes on every restart. When using persistent volumes, manage state ownership carefully and avoid mounting the same state directory into multiple tasks/instances simultaneously. Never delete a state store simply because startup feels slow; verify whether the store can rebuild from the changelog first.

Key metrics include restore bytes/records, restore duration, rebalance duration, changelog lag, disk I/O, and time from restart to steady processing.

## 18. Full Disks: Pinpoint the Exact Storage Layer

"Disk full" can mean different layers:

| Full Location | Example Causes | Impact |
|---|---|---|
| Kafka broker data volume | Topic retention, replication catch-up, growing log segments | Producer writes fail, partitions lose stability |
| RabbitMQ broker volume | Queue backlog, quorum queue logs, message store | Disk alarm triggers, publishers blocked or queues cannot write |
| Pulsar BookKeeper volume | Growing ledger/data journals, exhausted bookie capacity | Ledger writes or ensemble placement fail |
| Kafka Streams state directory | Changelog restoration, RocksDB, large state | Task restore/execution fails, Pods restart |
| Application root/log filesystem | Verbose logs, temp files, heap dumps | JVM/file operations fail, container destabilizes |
| Monitoring/logging sidecar | Unrotated log buffers | Node disk pressure, Pod evictions |

Never run a generic file-deletion command across all scenarios. Brokers manage interconnected logs, ledgers, and indexes; manual deletion risks data loss or metadata corruption.

## 19. Assessing the Severity of Disk Pressure

Gather at least:

- Which filesystem is full, remaining free bytes, and free inodes.
- Hourly growth rate and estimated time to critical threshold.
- Which component is writing and what data type is growing.
- Whether existing replication/quorum/retention still protects data.
- Whether ingress can be throttled or low-priority workloads paused without losing messages.
- Whether volumes can be expanded through supported procedures.

A volume with 5% free space growing at 50 GiB/minute can be more urgent than one at 1% free that is flat with sufficient operational buffer, depending on system constraints.

Prioritize restoring capacity and curbing new data generation. Do not ignore warnings simply because the JVM is still running or the broker port remains open.

## 20. Kafka: Full Disk on a Broker

When Kafka data directories run out of space, brokers may fail to append logs, impacting partition leaders/followers and producers. If replicas fall behind, ISR can shrink, preventing `acks=all` producers from meeting write requirements.

Safe runbook:

1. Confirm affected brokers, log directories, free bytes, and partitions.
2. Inspect broker error logs, failed log dirs, and under-replicated/offline partitions.
3. Throttle producer ingress via approved application mechanisms or rate limits.
4. Expand storage or rebalance/relocate partitions using supported admin tools.
5. Verify retention/cleanup policies match design, without slashing retention arbitrarily and erasing unconsumed data.
6. Once headroom returns, let brokers catch up replicas and verify ISR and producer acknowledgments.
7. Monitor consumer lag and confirm no data gaps or skipped ranges occurred.

**Never delete files directly inside Kafka `log.dirs`** to free space. Never slash retention to tiny values during an incident without confirming replay needs and consumer progress.

## 21. RabbitMQ: Disk Alarms and Blocked Publishers

RabbitMQ enforces a disk-free alarm. When free disk drops below the configured threshold, the broker/cluster may block publishers to stop storage growth while allowing consumers to keep receiving and draining backlogs if other conditions permit.

Traffic flow illustration:

~~~mermaid
flowchart LR
    P[Publishers] -. Blocked by disk alarm .-> R[(RabbitMQ)]
    R --> Q[(Durable / quorum queues)]
    Q --> C[Consumers drain backlog]
    C --> DB[(Business side effects)]
~~~

Identify which nodes triggered the alarm, actual free disk, and which queues hold the backlog. Priority actions are expanding disk capacity, throttling ingress, keeping healthy consumers draining backlogs, and resolving whatever blocked backlog consumption.

Never lower `disk_free_limit` to unsafe values or directly delete message-store/quorum-queue files just to unblock publishers. Never alter policies mid-quorum-loss without understanding the consequences.

## 22. Pulsar/BookKeeper: Bookie Out of Disk Space

BookKeeper stores data ledgers for Pulsar. A full bookie may stop accepting writes or fail journal/entry-log operations; if too few writable bookies remain to satisfy ensemble/write quorum, producers fail even while brokers stay alive.

Remediation must follow Pulsar/BookKeeper operational procedures:

- Inspect bookie writable/read-only state, journal, and ledger directories.
- Inspect free disk, entry-log compaction/garbage collection, and ledger replication health.
- Throttle ingress or shift workloads per supported policies if writable bookies run short.
- Add storage capacity or extra bookies, letting the system rebalance/recover ledgers via official tools.
- Verify namespaces/topics can produce/consume again and subscription backlogs drain.

Never delete ledger/index files manually. Never rely on restarting Pulsar brokers as the primary fix when the root cause lies in BookKeeper storage.

## 23. Application or Kafka Streams State Disk Full

Application disks can fill from logs, temp files, heap dumps, or Kafka Streams RocksDB state. Impacts differ:

- Root/log filesystem full: Application may keep running partially while failing to write logs, dumps, or temp files.
- Kafka Streams state volume full: State stores/restores fail, putting tasks into error states.
- Node ephemeral storage pressure: Kubernetes may evict Pods, triggering repeated consumer rebalances.

Runbook:

1. Pinpoint the exact failing filesystem and fast-growing data type.
2. Check whether workloads can temporarily pause/throttle to stop additional writes.
3. Fix log rotation and expand quotas/capacity per infrastructure standards.
4. If state stores must be rebuilt, verify changelogs and replication remain intact before recreating local state.
5. After restart, wait for state restoration/readiness; watch I/O and returning load.

Never delete the state directory of a running Pod or wipe volumes holding non-recreatable data. When restoring state from changelogs, estimate restore duration and verify required retention beforehand.

## 24. Backpressure and Ingress Throttling During Recovery

If ingress keeps rising while consumer capacity drops, backlogs can outgrow storage and trigger disk incidents. Maintain approved throttling mechanisms:

- Slow down non-critical publishers or pause batch imports temporarily.
- Rate-limit upstream APIs/producers by tenant, priority, or event type.
- Cap concurrent processing if downstream saturates; avoid hot retry loops.
- Use retries with exponential backoff and jitter so instances do not retry in lockstep.
- Retain messages in brokers/storage with adequate retention instead of silently dropping data.

Shedding load does not mean silently discarding accepted events. If upstream cannot buffer, the system needs explicit rejection signals or durable buffers/outboxes within the business contract.

## 25. Retries, DLQs, and Poison Messages During System Recovery

When a broker comes back online, huge bursts of messages may arrive simultaneously. If certain messages always fail, unbounded retries trap partitions/consumers in loops, rebuild disk pressure, and delay healthy messages.

Safe design:

1. Classify transient vs. non-retryable errors.
2. Configure bounded max attempts, backoff, and retryable exception rules.
3. Route poison messages to a DLQ per policy; alert if DLQ publishing fails.
4. Attach `eventId`, original topic/queue, failure reason, attempt count, and timestamp to error records.
5. Reprocess DLQs through an approved, idempotent workflow rather than endlessly dumping them back in bulk.

A DLQ is not a "trash bin" replacing schema/logic fixes. During disk-full incidents, account for retry and DLQ traffic too because they also consume storage.

## 26. Illustrative Configuration for the Spring Cloud Stream Kafka Binder

Example of a consumer processing order events, using a fixed group, disabling topic auto-creation, and bounding shutdown duration. The configuration uses a single `spring` root:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            maxAttempts: 3
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlt
server:
  shutdown: graceful
~~~

This is an illustrative configuration, not proof that retries, DLQs, or transactions have been tested. Pre-create the DLQ, publish permissions, and consumer/producer policies beforehand. Exact properties depend on your Spring Cloud Stream/Kafka binder version; with batch mode, transactional binders, or native decoding, error handling mechanics may differ.

## 27. Rabbit Binder and DLQ Configuration by Workload

With RabbitMQ, destinations typically map to exchanges and consumer groups map to queues. Example configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              prefetch: 20
~~~

When production pre-provisions queues/exchanges and restricts runtime principals, align `autoBindDlq`/provisioning accordingly. Overly large prefetch increases unacked messages and redelivery windows if an instance dies; overly small prefetch can limit throughput.

Do not assume enabling DLQ handles every error automatically. Verify dead-letter exchanges/queues, publisher/consumer permissions, retry policies, and that failed messages actually land in the DLQ.

## 28. Pulsar Binder Recovery: Subscriptions and Acknowledgments

The Spring Cloud Stream Pulsar binder uses topics/subscriptions, differing from Kafka group offsets and Rabbit queue acknowledgments:

- **Exclusive/Failover:** Fits when only one consumer should be active per scope; failover can switch consumers.
- **Shared:** Multiple consumers share load; redeliveries may reach different consumers without subscription-wide ordering.
- **Key_Shared:** Routes by key to maintain per-key affinity under normal conditions; requires compatible producer keys/batching.

When a Pulsar broker or consumer instance drops, check subscription cursors, unacked messages, redeliveries, and backlogs. Verify ack timeouts, negative acks, retry-letter/DLQ settings, and binder properties supported by your exact version.

If ordering by `orderId` or `accountId` is required, never flip the subscription type to `Shared` mid-incident just to boost concurrency without assessing business semantics.

## 29. Data Model for Safe Reprocessing

Example of a business handler with a stable `eventId`:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPaid(String eventId, String orderId, long amountCents) {}

interface PaymentService {
    void applyOnce(String eventId, String orderId, long amountCents);
}

@Configuration
class PaymentFunctions {

    @Bean
    Consumer<OrderPaid> processPayment(PaymentService paymentService) {
        return event -> paymentService.applyOnce(
            event.eventId(), event.orderId(), event.amountCents()
        );
    }
}
~~~

`applyOnce` must be backed by a real transaction/unique constraint or inbox pattern, not an in-memory map. A viable implementation can:

1. Open a database transaction.
2. Insert `eventId` into a `processed_events` table with a unique constraint.
3. If `eventId` already exists, skip duplicate side effects.
4. If inserted newly, update state/payment in the same transaction.
5. Commit the transaction; only then let the consumer ack/commit per configured semantics.

If messages redeliver on instance or broker loss, `eventId` prevents running side effects twice. This does not automatically cover external HTTP APIs outside the database; use idempotency keys or an outbox when calling external services.

## 30. Measuring Backlog Drain Time After Recovery

Once the broker returns, ingestion may resume immediately while backlog keeps growing unless processing throughput exceeds incoming rate.

Suppose:

~~~text
backlog after outage = 90,000 events
new incoming rate     = 600 events/s
processing capacity   = 1,100 events/s
net drain rate        = 500 events/s
estimated drain time  = 90,000 / 500 = 180 s
~~~

This is a simple linear model. Retries, hot keys, large payloads, and database bottlenecks can degrade throughput over time. If capacity equals or trails ingress, backlog will never clear on its own.

Monitor backlog age alongside backlog count, p95/p99 end-to-end latency, retry attempts, and CPU/disk I/O during recovery. Never scale consumer replicas blindly when the bottleneck is one hot partition or a connection-pool-limited downstream.

## 31. Staging Fault-Injection Test Matrix

Before production, rehearse in an environment whose broker topology, replication, volumes, retention, and retry settings mirror production:

| ID | Staging Fault Action | Primary Expectation | Evidence to Collect |
|---|---|---|---|
| F01 | Stop one Kafka broker under load | Leader failover, zero loss of protected messages | ISR, producer errors, `eventId` reconciliation |
| F02 | Stop one consumer Pod | Partitions reassign, backlog drains after recovery | Rebalance, lag, duplicates prevented |
| F03 | Kill Pod after DB commit, before ack (fault hook) | Redelivery causes zero duplicate side effects | Unique `eventId` and database state |
| F04 | Lose one RabbitMQ node in a quorum queue | Queue keeps serving if majority holds | Quorum status, publisher confirms |
| F05 | Lose a Pulsar broker | Clients reconnect and keep reading/writing while storage is healthy | Topic ownership, backlog, redeliveries |
| F06 | Fill test broker disk to warning threshold | Alerts fire, broker blocks/throttles writes, zero data loss | Disk alarms, logs, free bytes |
| F07 | Fill local state volume of a test Pod in isolation | Task fails cleanly then restores | Restore time, state correctness |
| F08 | Simulate downstream 503 and poison messages | Bounded retries, accurate DLQ routing | Retry counts, DLQ IDs, no infinite loops |
| F09 | Restore broker after 5-minute outage | Backlog drains within target RTO | Drain graph, oldest event age |

Controlled destructive tests must use approved test resources only. For disk-full tests, use isolated quotas/volumes; never flood shared cluster filesystems or personal workstations indefinitely.

## 32. Reconciling Events After an Incident

Generate `eventId`/`correlationId` right at the producer. After recovery, account across the **unique event ID set**:

~~~text
broker-acknowledged input IDs
    = unique successfully completed IDs
    + unique business-rejected IDs
    + unique DLQ IDs
    + unique still-pending/unknown IDs
~~~

Condition: outcome sets must be **mutually exclusive**, or the verifier must flag any ID appearing in multiple sets. Counting raw message totals hides duplicates and missing IDs.

Verify further:

- How many messages were reprocessed without causing duplicate side effects?
- Are any broker-acknowledged messages missing from every outcome set past the recovery deadline?
- Did any events land in the DLQ due to transient errors that should have succeeded?
- What is the maximum age of the oldest remaining backlog event?
- Did Kafka Streams stores restore results consistent with their changelogs?

A run fails if unknown outcomes remain past the deadline, even if the service health endpoint reports UP.

## 33. Dangerous Actions to Avoid

- Never delete Kafka log segments, RabbitMQ message stores, or BookKeeper ledgers directly from the filesystem.
- Never delete queues/DLQs or bulk-reset consumer offsets without a reconciliation plan and approval.
- Never enable unclean Kafka leader election or lower `min.insync.replicas` mid-incident without evaluating data loss.
- Never disable publisher confirms or weaken durability solely for higher benchmark throughput.
- Never tie liveness probes to broker health so all Pods restart continuously during broker failures.
- Never delete Kafka Streams local state stores without confirming changelogs can rebuild them.
- Never handle poison messages with infinite retries or unbounded DLQ reprocessing.
- Never scale consumers past downstream capacity, fueling retry storms and heavier disk pressure.
- Never close an incident merely because application Pods show RUNNING while lag keeps rising.

Any action that weakens durability or risks data loss must be treated as a high-risk operational change with owner sign-off and documented RPO limits.

## 34. Pre-Go-Live Checklist

- [ ] Appropriate replication/quorum configured for Kafka, RabbitMQ, or Pulsar/BookKeeper.
- [ ] Broker data volumes alert on capacity and growth rate well before filling up.
- [ ] At least one standby instance or explicit recovery strategy exists for critical workloads.
- [ ] Readiness/liveness/startup probes do not trigger restart storms when brokers fail.
- [ ] Graceful shutdown and termination grace periods have been tested.
- [ ] Offsets/acks advance only after required work completes per delivery semantics.
- [ ] Consumer handlers implement idempotency for duplicates/redeliveries.
- [ ] Bounded retries, backoff, and DLQs verified end-to-end.
- [ ] Dashboards track producer errors, consumer lag, queue backlog age, DLQ, and free disk.
- [ ] Kafka Streams changelog/state restoration rehearsed if stateful processing is used.
- [ ] Ingress throttling strategy exists without silently dropping events.
- [ ] Dedicated runbooks cover broker outages, Pod loss, and disk pressure.
- [ ] Staging fault drills run with reconcilable `eventId`s.
- [ ] RTO/RPO and backlog drain measured against business SLOs.

## 35. Response Workflow Summary

On broker loss: **check replication/quorum first, restore nodes, and verify producers/consumers resume under proper durability guarantees**. On instance loss: **let orchestration/brokers redistribute work, protect side effects with idempotency, and allow state restoration when needed**. On full disks: **identify the exact storage layer, curb load generation, and expand or reclaim capacity via supported tools; never delete broker files arbitrarily**.

Every incident must close on evidence: topics/queues serving normally again, broker-acknowledged data accounted for with valid outcomes, failing messages isolated cleanly, backlogs shrinking, and RTO/RPO/SLO targets met. That way, Spring Cloud Stream does not merely reconnect—it genuinely restores event processing and business state integrity.

## References

- [Spring Cloud Stream — Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Stream Kafka Binder — Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream Rabbit Binder — Reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Apache Kafka — Operations and Replication](https://kafka.apache.org/documentation/)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Disk Alarms](https://www.rabbitmq.com/docs/disk-alarms)
- [Apache Pulsar — Architecture](https://pulsar.apache.org/docs/concepts-architecture-overview/)
- [Apache BookKeeper — Overview](https://bookkeeper.apache.org/docs/overview/)

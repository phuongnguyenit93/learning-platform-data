# Transaction Rolled Back, Timed Out, or Producer Fencing

In a **SPRING_CLOUD_STREAM** application processing events with Supplier/Function/Consumer, Kafka transactions link writing multiple records—and, in a properly configured consume-transform-produce flow, committing input offsets alongside output records—inside a single Kafka transaction. However, transactions can roll back due to business exceptions, processing timeouts, broker disconnects, rebalances, or another producer claiming the same **transactional.id**.

Three commonly confused symptoms are:

- **Rollback:** the current transaction does not commit; output records within the transaction are aborted and offsets may be reprocessed.
- **Timeout:** a time limit was exceeded. This could be a broker transaction deadline, a client wait for metadata/acknowledgment, or the consumer poll interval; each requires a different fix.
- **Producer fencing:** the broker invalidates a producer using an older epoch of the same `transactional.id`, preventing it from continuing to write or commit transactions. Never keep using a fenced producer instance.

This lesson belongs to the **Troubleshooting** chapter. The focus is the Spring Cloud Stream Kafka message binder and Kafka Streams binder; RabbitMQ and Pulsar have different transaction or acknowledgment semantics, so Kafka causes and parameters cannot be applied verbatim.

## 1. Kafka Transaction Model to Understand Before Diagnosing

Kafka producer transactions group writes across multiple partitions/topics together with a set of consumer offsets into one atomic commit/abort unit in Kafka. When a producer uses a **transactional.id**, the broker assigns a producer ID and epoch to identify the valid owner of the transactional session.

A typical transaction lifecycle:

~~~mermaid
flowchart TD
    A[Create transactional producer] --> B[initTransactions]
    B --> C[beginTransaction]
    C --> D[Send output records]
    D --> E{Error during processing/send?}
    E -->|No| F[sendOffsetsToTransaction if consume-process-produce]
    F --> G[commitTransaction]
    G --> H[Records and offsets committed in Kafka]
    E -->|Abortable error| I[abortTransaction]
    I --> J[Aborted records invisible to read_committed]
    J --> K[Input may be reprocessed]
    E -->|Fatal/fenced| L[Close producer; replace instance]
~~~

This model describes transactions inside Kafka. Frameworks like Spring Kafka or Spring Cloud Stream invoke these steps automatically, so application code does not normally call begin/commit manually.

Critically: **Kafka transactions do not automatically span databases, HTTP APIs, or other broker systems**. A Kafka transaction rollback cannot undo a completed payment or an already-committed database transaction.

## 2. Execution Path of the Spring Cloud Stream Kafka Binder

Example processor:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder(
        OrderValidator validator) {
    return validator::validate;
}
~~~

Bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation-service
        validateOrder-out-0:
          destination: orders.validated
~~~

When **Kafka binder transactions are enabled**, a standard imperative invocation runs as follows:

1. The listener receives a record from the input topic.
2. The container starts a Kafka transaction.
3. The function processes the record on the consumer thread.
4. Messages sent through the output binding join the active transaction on that thread.
5. The container sends the input record's offset to the transaction.
6. If the handler succeeds, the container commits the transaction; if an error occurs, the transaction rolls back.
7. After rollback, the container applies seek/re-fetch/retry and recovery accordingly.

Conditions to keep in mind:

- The outbound path must genuinely use the **transactional producer factory** of the same binder/transaction context.
- Async processing or sending on another thread does not automatically participate in the consumer thread's transaction.
- Consumers reading transactional outputs should set **isolation.level=read_committed** if they must not see aborted records.
- A successful Kafka transaction does not verify external side effects outside Kafka.

## 3. What Does Rollback Mean for Records and Offsets?

Suppose the input topic contains event E42, the function emits output V42, and then throws an exception.

| Component | When Transaction Commits | When Transaction Aborts |
| --- | --- | --- |
| Transactional output record V42 | Visible to `read_committed` consumers | Invisible to `read_committed` consumers |
| Input offset sent to same transaction | Valid commit; group can advance | Not committed as part of that transaction |
| Next processing cycle | Normally moves to next record | E42 may be re-read per container recovery |
| HTTP/database side effect | Outside Kafka transaction | Does not roll back automatically |
| `read_uncommitted` consumer | Can see committed records | Can also see aborted records |

A rollback does not mean the broker physically deleted the record. Kafka still writes transaction markers and offsets to the log. Consumers in `read_committed` mode filter out records belonging to aborted transactions.

**Never conclude data was lost just because logs show a rollback.** First verify the output topic with `read_committed`, input committed offsets, and processing/replay counts.

## 4. Classifying Rollback Causes

A rollback can be expected behavior or an infrastructure symptom.

| Category | Example Exceptions | Action |
| --- | --- | --- |
| Permanent business error | `InvalidOrderException`, validation failed | Do not retry forever; after rollback route to DLT/quarantine |
| Transient error | HTTP 503, database timeout, leader election | Bounded retries with backoff after rollback |
| Producer error | `SerializationException`, timeout, authorization | Determine fatal vs abortable before retrying |
| Consumer/group error | `CommitFailedException`, rebalance, `max.poll.interval.ms` exceeded | Investigate session/assignment and processing duration |
| Transaction coordinator | Broker unreachable, coordinator unavailable, transaction timeout | Measure latency, transaction state, and broker health |
| Producer fencing | `ProducerFencedException`, `InvalidProducerEpochException` | Close fenced producer; fix `transactional.id` or lifecycle |

Before acting, determine whether the exception occurred **inside the business function**, **while sending a record**, **while sending offsets**, or **during `commitTransaction`**. Stack traces at the `KafkaProducer` layer often wrap multiple causes; read the **root cause** and transaction timeline.

## 5. Three Timeouts Never to Confuse

Kafka systems have at least three independent timeouts often lumped together as "transaction timeout."

| Timeout | Scope | Meaning |
| --- | --- | --- |
| **transaction.timeout.ms** | Kafka producer transaction | If a transaction stays open too long, the transaction coordinator may abort it |
| **max.block.ms** | Blocking `KafkaProducer` calls | Caps waiting for metadata, buffer space, or certain transaction calls |
| **delivery.timeout.ms** | Sending one producer record | Caps total time for a record send to report success/failure after send |
| **request.timeout.ms** | Producer request to broker | Caps waiting for a broker response |
| **max.poll.interval.ms** | Consumer group member | Too long between polls can drop group membership / trigger rebalance |
| **transaction.max.timeout.ms** | Kafka broker | Maximum `transaction.timeout.ms` a broker lets clients request |

For example, a transaction has **transaction.timeout.ms=60000** ms while the handler calls an external API taking 90 seconds. The coordinator can abort the transaction before the handler finishes, even if `max.poll.interval.ms` still has plenty of headroom.

Conversely, a **TimeoutException** on a commit/abort call can stem from **max.block.ms** or network drops; it does not prove the broker aborted the transaction. When an acknowledgment is lost, the commit outcome is **uncertain from the caller's viewpoint**. Never immediately publish a duplicate without an idempotency/reconciliation plan.

## 6. transaction.timeout.ms and transaction.max.timeout.ms

Apache Kafka producer defines:

- **transaction.timeout.ms:** the transaction coordinator actively aborts transactions running past this limit; in Kafka 4.2, the timer starts when the first partition is added to the transaction.
- **transaction.max.timeout.ms:** the maximum timeout the broker permits a client to request. If a producer asks for more, Kafka returns a configuration error such as **InvalidTxnTimeoutException** when initializing transactions.

Published defaults in Kafka 4.2 documentation:

| Property | Reference Default | Where Set |
| --- | --- | --- |
| transaction.timeout.ms | 60000 ms (1 minute) | Producer |
| transaction.max.timeout.ms | 900000 ms (15 minutes) | Broker |

These are Kafka 4.2 defaults, not limits suited to every workload. Never raise the broker maximum just to mask a hung handler.

**Rule for choosing timeouts:** `transaction.timeout.ms` must comfortably exceed P99/P99.9 processing duration, retries/backoff, commit time, and broker latency—yet remain small enough because an open transaction holds back the **Last Stable Offset (LSO)** for `read_committed` consumers on involved partitions.

## 7. Example Timeout from Slow Processing

A function:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder(
        OrderValidator validator) {
    return order -> {
        validator.validateWithExternalApi(order); // may block for 75 seconds
        return new OrderValidated(order.orderId(), true);
    };
}
~~~

If transaction timeout is 60 seconds and the HTTP call waits 75 seconds, the transaction can abort before the function even returns output. When the framework attempts to send or commit, errors surface at the producer/transaction-manager layer.

Remediation must start with profiling:

1. Measure function duration, HTTP call duration, and transaction commit duration by percentile.
2. Enforce tight HTTP timeouts, bounded retries, and circuit breakers.
3. Move long-running work to an async step with its own event/outbox where appropriate.
4. Raise `transaction.timeout.ms` only if business semantics and the Kafka coordinator genuinely need longer transactions.
5. Verify `transaction.timeout.ms` does not exceed broker `transaction.max.timeout.ms`.
6. Test under slow brokers, producer retries, and concurrent consumer rebalances.

Never hold a Kafka transaction open while awaiting human approval, multi-minute workflows, or large external batches; split into smaller steps with identifiers and idempotency.

## 8. TimeoutException Does Not Always Mean the Transaction Rolled Back

Common examples:

~~~text
org.apache.kafka.common.errors.TimeoutException:
  Timeout of ... expired before successful completion

org.apache.kafka.common.errors.TimeoutException:
  Expiring ... record(s) for ...

org.apache.kafka.common.errors.InvalidTxnTimeoutException:
  Transaction timeout ... exceeds broker maximum ...
~~~

These log lines are illustrative; exact wording varies across Kafka client versions.

How to investigate properly:

- **Metadata/buffer errors:** check bootstrap servers, advertised listeners, ACLs, `buffer.memory`, broker latency, and `max.block.ms`.
- **Delivery errors:** check `delivery.timeout.ms`, `request.timeout.ms`, retries, ISR/acks, and network.
- **Transaction deadline errors:** check `transaction.timeout.ms` and how long the transaction actually stayed open.
- **Exceeds broker maximum:** align producer and broker configuration.
- **Commit response timeout:** do not assume the transaction aborted; inspect `read_committed`, idempotency keys, and consumer offset state before replaying.

Once a producer transaction hits a fatal or fenced state, do not try to "rescue" it by bumping timeouts and reusing the same object.

## 9. What Is Producer Fencing?

Kafka uses **transactional.id** to link producer sessions to the same transactional identity and **producer epoch** to fence out older (zombie) producers.

Example:

1. Pod A starts a producer with `transactional.id` **orders-tx-0**, epoch e1.
2. A freezes or loses network connectivity without dying.
3. Pod B uses the same `transactional.id` **orders-tx-0** and calls `initTransactions`, receiving new epoch e2.
4. The broker rejects any further transactional requests from producer A.
5. A receives **ProducerFencedException** or a related epoch error; A must close that producer.

~~~mermaid
sequenceDiagram
    participant A as Producer A (epoch e1)
    participant K as Kafka transaction coordinator
    participant B as Producer B (epoch e2)
    A->>K: initTransactions(orders-tx-0)
    K-->>A: epoch e1
    A->>K: begin/send (transaction open)
    B->>K: initTransactions(orders-tx-0)
    K-->>B: epoch e2; fence old session
    A->>K: send/commit (epoch e1)
    K-->>A: ProducerFencedException
    Note over A: Close old producer; never retry with same instance
    B->>K: begin/send/commit (epoch e2)
~~~

Fencing is a **correctness safeguard**: only the current valid producer session may issue transactional requests for a transactional ID. Ignoring fencing and keeping the old producer alive does not make the system safer; it only repeats fatal errors.

## 10. When Is Fencing Normal, and When Is It a Deployment Bug?

Old producer A being fenced after a failover can be expected Kafka behavior, as new producer B takes over the identity to block zombies.

However, continuous fencing while two pods run normally usually indicates a misconfiguration:

| Symptom | Suspected Cause |
| --- | --- |
| Two replicas share `transactional.id`/prefix | Prefix is not unique per live instance |
| Fencing after rolling deployment | New pod reuses identity of old pod during overlap |
| Fencing on long-lived idle producer cache | Transactional ID expired on broker; producer reuses stale epoch |
| Fencing after restart/network blip | New session got a higher epoch while zombie process kept running |
| Kafka Streams reports task migrated/fenced | Task ownership moved on rebalance/failover; distinguish from binder producer prefix collisions |
| Consumer group instance fencing exception | Likely static membership **FencedInstanceIdException**, distinct from `ProducerFencedException` |

Having two **concurrently active** instances use the same **transactional.id** is wrong. In some failover designs, reusing an identity to fence zombies is intentional, but requires a clear fencing lifecycle and deployment contract. With Spring Kafka **EOSMode.V2**, the docs require a **distinct `transactionIdPrefix` per active application instance**.

## 11. ProducerFencedException Is Fatal for That Producer

Per the Kafka Producer API, **ProducerFencedException** indicates another producer with the same `transactional.id` has superseded this session. On receiving it, **close the producer instance**; never call send/commit/abort again on the fenced object as a business retry.

Practical remediation steps:

1. Record `transactional.id` (redacted if needed), pod ID, instance ID, timestamp, and root stack trace.
2. Stop using the fenced producer and let the framework/container close it and create a new session when appropriate.
3. Compare prefixes and actual `transactional.id` values across all active replicas.
4. Inspect pod rollout overlap, orphan processes, duplicate deployments, and producer caches.
5. Once collisions are eliminated, initialize new producers only via the standard lifecycle.
6. Verify input offsets, `read_committed` outputs, and duplicate side effects before replaying.

Never catch `ProducerFencedException` inside a business function and return success; doing so can trick callers into believing the record committed. Never generate a random `transactional.id` per record to "avoid" fencing: that defeats per-session transactional identity and bloats coordinator state unnecessarily.

## 12. Fencing Without a New Replica: Producer Expiration

Spring Kafka documents the case of a long-idle transactional producer: the broker can expire a `transactional.id` after **transactional.id.expiration.ms**; when the old cached producer resumes activity, it can be fenced even without a visible rebalance or new pod.

**DefaultKafkaProducerFactory** supports **maxAge** to evict aged cached producers and build fresh ones before `transactional.id` expires. Use this feature only when:

- Symptoms are confirmed to stem from idle producers and ID expiration.
- `maxAge` is set safely below the broker expiration window with margin.
- You verify the exact factory used by the binder rather than configuring an unrelated producer factory.
- You do not substitute `maxAge` tweaks for diagnosing prefix collisions.

Do not set `transactional.id.expiration.ms` excessively high when the real cause is two active replicas sharing an ID.

## 13. Enabling the Kafka Transactional Binder in Spring Cloud Stream

Minimal illustrative configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          destination: orders.validated
      kafka:
        binder:
          brokers: kafka:9092
          transaction:
            transaction-id-prefix: order-validation-instance-a-
~~~

A non-empty **spring.cloud.stream.kafka.binder.transaction.transactionIdPrefix** enables the transactional binder. In this example, **instance-a** is valid only for a single instance; in Kubernetes/scale-out deployments, provide a distinct prefix per pod/instance.

When transactions are enabled, the binder shares a transactional producer factory across output bindings. Per-binding producer properties may be ignored; shared producer properties go under:

~~~text
spring.cloud.stream.kafka.binder.transaction.producer.*
~~~

Consequently, editing **spring.cloud.stream.kafka.bindings.validateOrder-out-0.producer.configuration** may not affect the actual transactional producer as operators expect.

Do not confuse the Kafka transactional binder with database transactions or with the transaction manager auto-configured by Spring Boot for a standalone `KafkaTemplate`.

## 14. Unique Prefix per Instance in Multi-Pod Deployments

Wrong:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: orders-tx-
~~~

If all three pods share `orders-tx-` and each factory generates the same suffix, actual transactional IDs collide and continuously fence one another.

Right in principle:

~~~text
pod order-service-a -> order-tx-order-service-a-
pod order-service-b -> order-tx-order-service-b-
pod order-service-c -> order-tx-order-service-c-
~~~

The prefix can be supplied via an orchestrator-injected environment variable using the pod name or an instance identity guaranteed unique across active pods.

Kubernetes example passing pod name as an environment variable:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0
          env:
            - name: INSTANCE_ID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
~~~

The application must incorporate `INSTANCE_ID` into the Spring configuration before building the producer factory; the pod name above is merely the **identity source**, and does not automatically become the transaction prefix until wired into the Spring Cloud Stream property.

Watch lifecycle transitions: if two processes reuse the same logical instance identity during failover, enforce zombie fencing and overlap control. If the goal is running multiple active replicas concurrently, prefixes must never collide.

## 15. Configuring Timeouts for a Transactional Producer

Spring Cloud Stream provides a shared producer namespace when the transactional binder is enabled. Common declarative example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: order-validation-instance-a-
            producer:
              configuration:
                transaction.timeout.ms: 120000
                delivery.timeout.ms: 120000
                request.timeout.ms: 30000
~~~

This is an illustrative configuration, not fixed production values. **transaction.timeout.ms** belongs in Kafka producer configuration; **transaction.max.timeout.ms** belongs on the broker, not under binder producer properties.

When tuning timeouts:

- Transaction deadline must cover real processing and commit time with headroom.
- Delivery timeout applies per send, not in place of the transaction deadline.
- Request timeout applies per request/ack, not to total function duration.
- Max block time can affect transaction calls when the coordinator or metadata is slow.
- Never set transaction timeout higher than the broker maximum.
- Measure P99/P99.9 under load and run broker disruption tests before changing defaults.

Verify in your binder version that properties under **transaction.producer.configuration** actually propagate to the live Kafka producer factory; never assume the broker honors them just from reading `application.yml`.

## 16. Spring Cloud Stream Transactions Differ from Spring Boot KafkaTemplate Transactions

Two common paths exist:

**Path A — Spring Cloud Stream Kafka binder:** transactions are enabled via **spring.cloud.stream.kafka.binder.transaction.transactionIdPrefix**, and the binder's container manages transactions during consume-process-produce.

**Path B — Spring Kafka/Spring Boot:** configuring **spring.kafka.producer.transaction-id-prefix** makes Spring Boot auto-create a `KafkaTransactionManager` for Boot's producer factory; used with `KafkaTemplate`, `@Transactional`, or `TransactionTemplate`.

These two paths do not automatically share the same producer factory or transaction context. Know whether records are sent through **StreamBridge/output bindings** or a specific **KafkaTemplate**, and which transaction manager governs them. Mixing them can send outputs outside the transaction committing input offsets.

**Do not set both prefixes assuming they merge into one transaction.** Verify beans/producer factories, thread context, and binder selection explicitly.

## 17. Retries and DLT When the Kafka Binder Is Transactional

In transactional mode, the Spring Cloud Stream Kafka binder **does not run ordinary retry and dead-lettering inside the original transaction** the same way a non-transactional binder does.

Reason: if the handler fails and the transaction rolls back, any output records sent within that transaction roll back too. Therefore, retry/recovery must happen **after rollback**.

Binder documentation notes:

- Consumer retry properties configure **DefaultAfterRollbackProcessor** when transactions are enabled.
- The processor seeks/re-fetches failed records on the next poll and applies configured backoff/recovery.
- When sending failing records to a DLT, recovery runs through the container's recovery mechanism rather than expecting a DLT write inside an aborted transaction to stick.
- The recovered record's offset can be committed in a **new transaction** alongside recovery depending on binder options.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      kafka:
        bindings:
          validateOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.validation-service.dlt
~~~

This configures retry/DLT for the **regular Kafka message binder**. Actual recovery behavior, transaction managers, and offset commits must be verified for your Spring Cloud Stream/Spring Kafka versions. A custom error handler can alter the recovery flow completely.

## 18. txCommitRecovered and Offsets of DLT-Routed Records

The Kafka binder exposes the consumer property **txCommitRecovered** for transactional recovery. Docs note the default is **true**: once a record is handled by the recoverer (e.g., published to the DLT), its offset is committed in a new transaction.

This prevents the loop:

1. Handler fails and the main transaction rolls back.
2. Recoverer publishes the failing record to the DLT.
3. Yet the original offset is not marked recovered.
4. Consumer re-reads the original record and keeps publishing duplicate DLT copies.

Never set **txCommitRecovered=false** "just to be safe" without understanding the replay consequences. Disabling recovered commits can cause the record to be reprocessed per container policy and create duplicates.

Questions to test:

- Was the DLT publish acknowledged by the broker?
- When DLT publish fails, does the original offset remain uncommitted for retry?
- If DLT succeeds while offset commit fails, does event ID idempotency handle duplicates?
- Does the DLT consumer read at the right isolation level?
- Does a custom error handler replace `DefaultAfterRollbackProcessor` or the default recoverer?

## 19. DefaultAfterRollbackProcessor and Poison Messages

Spring Kafka uses **DefaultAfterRollbackProcessor** to handle records after rollback. For record listeners, the processor seeks to the failing record and subsequent unprocessed records. For batch listeners, the replay scope is usually broader because the container cannot pinpoint the exact failing record without extra metadata; newer releases add dedicated batch recovery mechanisms.

Define clear policies:

| Policy | When to Use |
| --- | --- |
| Bounded retry + backoff | Short timeouts, transient broker or external API errors |
| Non-retryable + DLT | Schema errors, corrupt data, business invariant violations |
| Quarantine | Records needing manual intervention or sensitive handling |
| Parking lot after N replays | Prevents DLT → main topic → DLT loops |
| Pause consumer and alert | Configuration bugs or widespread downstream outage |

Avoid infinite retries on a poison message that stall the partition. At the same time, never silently discard failing records and commit offsets if the business requires auditing and replayability.

## 20. KafkaTemplate.executeInTransaction for Local Producer Transactions

When using Spring Kafka directly rather than the transactional binder, `KafkaTemplate` offers a local transaction API:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class AuditPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public AuditPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishBoth(String eventId, String payload) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.events", eventId, payload);
            operations.send("orders.audit", eventId, "published");
            return null;
        });
    }
}
~~~

This snippet assumes `KafkaTemplate` uses a transactional producer factory. If the callback finishes, the template commits; if it throws an exception, the transaction rolls back.

Important notes:

- `executeInTransaction` starts a new **local transaction** and does not automatically join an active `KafkaTransactionManager` transaction.
- For consumer-triggered exactly-once read-process-write, do not replace the binder transaction with a standalone local transaction assuming input offsets commit together.
- If the producer is fenced, close it; let the framework manage cache/factory recreation per lifecycle.
- Commit timeouts or errors require reconciliation because the broker-side outcome may be unknown to the caller.

## 21. Consumer isolation.level=read_committed

To keep consumers from seeing records from aborted transactions, configure:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consumeValidated-in-0:
          destination: orders.validated
          group: downstream-service
      kafka:
        bindings:
          consumeValidated-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

This applies to consumers on the **regular Kafka message binder**. If a consumer uses `read_uncommitted` (the Kafka default), it can observe transactional records that were later aborted.

### Last Stable Offset (LSO)

Under `read_committed`, a consumer reads only up to the **LSO**—the boundary just before the oldest open transaction on that partition. One long-running open transaction can stall `read_committed` consumers at an offset even while the high watermark climbs higher.

Once committed or aborted, the LSO advances. Consumers may also notice **offset gaps** caused by filtered transaction markers or aborted records. That is not automatically data loss.

~~~text
Partition:
  offset 101: committed record
  offset 102: record in an open transaction
  offset 103: record from another producer
  offset 104: record from another producer

read_committed: cannot read past the open transaction at 102
read_uncommitted: can read uncommitted transactional records
~~~

If `read_committed` lag spikes unexpectedly, check for long-open transactions before adding consumer concurrency or partitions.

## 22. Do Not Confuse Transaction Timeout with max.poll.interval.ms

**max.poll.interval.ms** caps the time between consumer group `poll()` calls. Slow handlers or retry/backoff blocking poll can cost the consumer its partition ownership, leading to rebalances, offset commit failures, or membership-related fencing.

**transaction.timeout.ms** caps how long a transaction stays open on the broker. Both limits are independent yet both impact consume-process-produce pipelines:

- Transaction deadline shorter than processing time → coordinator aborts.
- Poll interval exceeded → group may rebalance and the consumer is no longer owner when sending offsets.
- Both happen close together → logs show nested exceptions, obscuring the primary cause.

Remediation: profile handlers, bound HTTP/database calls, shrink batch sizes, offload long work asynchronously, and size timeouts from real measurements. Never merely raise `max.poll.interval.ms` while transactions still time out at 60 seconds.

## 23. Producer Epoch, Commit Failures, and Consumer Rebalances

In an exactly-once pipeline, producer transactions and consumer groups coordinate to commit input offsets. If the consumer loses assignment or group membership shifts, sending offsets or committing can fail.

Symptoms to cross-check:

| Log / Exception | Question |
| --- | --- |
| `ProducerFencedException` | Is another active producer using the same `transactional.id`? |
| `InvalidProducerEpochException` | Is the producer using a stale epoch or invalidated session? |
| `CommitFailedException` | Did the consumer lose membership / rebalance before committing? |
| `FencedInstanceIdException` | Is a static `group.instance.id` duplicated? |
| `TimeoutException` in `sendOffsetsToTransaction` | Did the coordinator/group metadata respond within `max.block.ms`? |
| `InvalidTxnTimeoutException` | Did the producer request a transaction timeout above the broker maximum? |

Do not lump distinct fencing errors into one cause. Duplicate **`group.instance.id`** affects static consumer membership, distinct from duplicate **`transactional.id`** causing producer fencing. Both can appear together during a rolling update, yet each requires a different fix.

## 24. Kafka Streams Binder Has Its Own Transaction Path

The Kafka Streams binder builds on the Kafka Streams API and does not handle transactions identically to the imperative Kafka message binder.

To enable exactly-once in Kafka Streams, configure the processing guarantee per the Kafka Streams API and your Kafka version, e.g.:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              processing.guarantee: exactly_once_v2
~~~

This uses the **spring.cloud.stream.kafka.streams.binder.configuration** namespace, not `transactionIdPrefix` from the regular Kafka message binder.

In Kafka Streams:

- The Streams runtime manages producers, tasks, offsets, and transactions across the topology.
- Transaction timeouts can accompany task migrations, rebalances, state restoration, commit intervals, or coordinator delays.
- Producer/task fencing can occur normally during failover; if continuous, check instance identity, assignments, group membership, resource starvation, and producer settings.
- Never apply regular Kafka message listener `DefaultAfterRollbackProcessor` options to Kafka Streams errors; they are two different runtimes.

Monitor stream thread state, rebalance/restore duration, transaction abort/error metrics, changelog lag, and broker transaction coordinator health.

## 25. Why Doesn't a Kafka Rollback Roll Back the Database?

Suppose a function runs:

1. Read `OrderCreated` from Kafka.
2. Write `VALIDATED` status to the database.
3. Send `OrderValidated` via Kafka output binding.
4. Kafka `commitTransaction` fails and rolls back.

The database may have already committed even though Kafka outputs and offsets rolled back. When the input is reprocessed, database side effects can execute a second time.

~~~mermaid
flowchart LR
  I[(Kafka input)] --> F[Function]
  F --> DB[(Database transaction)]
  F --> KT[(Kafka transaction)]
  KT -->|Abort| R[Kafka output and offset roll back]
  DB -->|Committed| S[Database does not roll back automatically]
~~~

Never treat database `@Transactional` combined with Kafka binder transactions as an automatic distributed ACID transaction. Choose patterns such as **transactional outbox**, **idempotent consumer/inbox**, reconciliation, or sagas/compensation depending on your domain. Even transaction synchronization between Kafka and a DB has crash windows and requires verifying commit order; do not advertise it as full two-phase commit.

## 26. Classify Exceptions Before Retrying

An operational classification guide:

| Category | Examples | Retry with Same Producer? | Action |
| --- | --- | --- | --- |
| Invalid business data | Validation failed | No | Abort and route to DLT/quarantine |
| Transient Kafka/network | Coordinator load, retriable transport | Per client/runtime policy | Backoff; rollback/reprocess if needed |
| Abortable transaction state | Transaction must abort, producer still valid | Do not continue that transaction | Abort per framework and start a fresh transaction |
| Producer fenced/fatal | `ProducerFencedException`, certain epoch/auth errors | **No** | Close producer; replace instance after investigating |
| Uncertain commit outcome | Timeout awaiting commit response | Never blindly replay | Reconcile output/offsets/idempotency before acting |

Kafka producer errors can be classified as fatal, abortable, or retriable depending on API and client version. Avoid blanket `catch (Exception) -> abort -> retry` with the same producer object for every failure. That can corrupt the transactional state machine and mask data loss.

## 27. Quick Diagnostic Decision Tree

~~~mermaid
flowchart TD
  A[Transaction error received] --> B{ProducerFencedException / InvalidProducerEpoch?}
  B -->|Yes| C[Close old producer, investigate ID collision / zombie / expiry]
  B -->|No| D{InvalidTxnTimeoutException?}
  D -->|Yes| E[Compare producer transaction.timeout vs broker max]
  D -->|No| F{TimeoutException?}
  F -->|Yes| G[Identify call site: metadata, send, offset, commit, abort]
  F -->|No| H{Business function threw exception?}
  H -->|Yes| I[Rollback -> after-rollback retry/DLT]
  H -->|No| J[Check group rebalance, coordinator, and ACLs]
  G --> K[Check deadlines, network, metrics, transaction outcome]
  C --> L[Do not reuse fenced producer]
  E --> M[Fix configuration and test]
  I --> N[Do not treat DLT in rolled-back tx as committed]
~~~

Once the cause is isolated, fix it at the right layer: transaction ID collision, timeout budget, consumer processing time, recovery policy, or broker availability. Never respond to all transaction failures by simply raising retries.

## 28. 10-Step Production Runbook for Rollback/Fencing Alerts

1. **Scope:** identify app, pod, deployment, consumer group, input/output topics, partition, event ID, and transactional ID if present.
2. **Read the root exception:** distinguish transaction deadline, `max.block` timeout, send failure, rebalance, and fencing.
3. **Record timestamps:** begin, sends, external calls, `sendOffsetsToTransaction`, commit/abort, and container restarts.
4. **Check rollout:** look for active pods sharing the same transaction prefix; check for orphan processes and zombies.
5. **Inspect effective config:** Spring Cloud Stream binder transaction prefix, `transaction.producer.*`, Kafka client timeouts, broker `transaction.max.timeout.ms`, and `isolation.level`.
6. **Check broker:** coordinator availability, auth/ACLs, ISRs, and network latency.
7. **Verify `read_committed`:** did output records commit or abort, and is LSO stalled?
8. **Check input offsets:** is the consumer group advancing commits, or are records being re-fetched?
9. **Verify DLT/recovery:** do DLT records exist and did recovered offsets commit per policy?
10. **Recover safely:** fix prefix/timeout/code, spin up fresh producers as needed, replay using event IDs/idempotency, and document runbook results.

When commit outcomes are uncertain, never manually replay messages before checking Kafka state and business records. Restarting pods en masse can also trigger fresh ID collisions and rebalances.

## 29. Logs and Metrics to Collect

Log in structured form without printing secrets or sensitive payloads:

- App instance/pod ID, transaction prefix (redacted/shortened as needed), group ID.
- Input and output topic/partition/offsets.
- Event ID, correlation ID, and trace ID if available.
- Exception class, root cause, and stack trace.
- Function duration, downstream wait time, and transaction duration.
- Rollback, abort, producer fencing, retry, and DLT publish counts.
- Kafka producer error/commit/abort metrics per client/producer factory.
- Consumer lag, rebalance count, poll interval, and assignments.
- Broker transaction coordinator error rate, transaction timeouts, and replication health.
- `read_committed` progress/LSO where tooling supports it.

Never put raw `transactional.id` as a high-cardinality metric tag across all producer instances when a stable tag suffices; keep per-instance IDs in controlled logs and traces. Avoid logging full transaction headers or personal data.

## 30. CLI Commands to Check Consumer Offsets and Visibility

Check group progress:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group validation-service \
  --describe
~~~

Read the output topic with a **`read_committed`** consumer:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic orders.validated \
  --from-beginning \
  --consumer-property isolation.level=read_committed
~~~

Compare against a **`read_uncommitted`** consumer in a test environment:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic orders.validated \
  --from-beginning \
  --consumer-property isolation.level=read_uncommitted
~~~

If a record shows up under `read_uncommitted` but not under `read_committed`, it may belong to an aborted or still-open transaction. Do not jump to conclusions before checking transaction lifecycle, offsets, and markers. In production, bound duration, record counts, and ACLs; avoid running unbounded console commands on sensitive topics.

## 31. Essential Fault-Injection Test Matrix

| Test Scenario | What to Observe | Expected Outcome |
| --- | --- | --- |
| Function throws before send | Retry/DLT, input offset | Transaction aborts; input retried or recovered per policy |
| Function throws after send before commit | `read_committed` output | Output inside aborted transaction never appears |
| Handler slower than `transaction.timeout.ms` | Broker abort, commit exception | Expired transaction does not commit; recovery path works |
| Producer timeout exceeds broker max | Startup/`initTransactions` | Clear config error, no blind retry loop |
| Two active pods share prefix | Producer epoch/fenced logs | Older producer fenced; fix identity |
| Producer idle beyond expiration | Producer cache reuse | Verify `maxAge`/expiry or fresh producer creation |
| Broker lost after send before commit response | Uncertain commit outcome | No blind replay; reconciliation/idempotency handles it |
| Consumer rebalances mid-long handler | Offset commit, group state | Failure/retry follows listener semantics |
| DLT publish failure | Original offset, DLT records | Message is not silently dropped |
| DB commits before Kafka aborts | DB + Kafka output | Duplicate on replay handled by idempotency |
| Kafka Streams task migration | Stream state/assignment | EOS processing continues cleanly after failover |
| Output consumer `read_uncommitted` | Aborted output visibility | Exposes risk of reading uncommitted data |

Use Testcontainers or a real test broker to exercise the transaction coordinator, producer epochs, and `read_committed`. Spring Cloud Stream's Test Binder validates only function/binding behavior and cannot prove real Kafka transaction commits or aborts.

### Suggested Integration Test

1. Start a Kafka test broker and create transactional input/output topics.
2. Enable the transactional binder with a unique per-instance prefix.
3. Send event E1 successfully; verify `read_committed` sees V1 and input offset advances.
4. For E2, make the function throw after emitting output; verify V2 does not appear under `read_committed`.
5. Briefly disrupt the broker or block the commit response; inspect exceptions and verify transaction outcome with an independent consumer.
6. In a separate low-level test, run two producers with the same `transactional.id`; verify the older producer gets fenced and must close.
7. Restore the broker; verify retries/DLT, offsets, and idempotency prevent duplicate side effects.

Never rely on fixed sleeps as proof. Use Awaitility, bounded polling, timeouts, and assertions on outputs and offsets.

## 32. Common Anti-Patterns

| Wrong Reaction | Why It Is Dangerous | Better Alternative |
| --- | --- | --- |
| Set all timeouts to 30 minutes | Keeps transactions open long, stalling LSO/`read_committed` | Profile bottlenecks and size deadlines with a budget |
| Retry with a fenced producer | Session was already invalidated by the broker | Close producer and establish a new session properly |
| Share the same transaction prefix across all replicas | Collisions and continuous fencing | Unique prefix per live instance |
| Retry/DLT inside the rolling-back transaction | DLT records can be aborted too | Recover after rollback in a new transaction when needed |
| Mark input handled when DLT publish fails | Loses ability to recover the record | Verify recoverer + offset commit semantics |
| Read outputs with `read_uncommitted` | Exposes aborted records | Use `read_committed` when required |
| Treat DB `@Transactional` as Kafka+DB atomic | The two systems commit independently | Outbox/inbox, reconciliation, idempotency |
| Mix Boot `KafkaTemplate` transactions with binder transactions | Producer factories use different contexts | Verify bean/manager/transaction boundaries |
| Raise `max.poll.interval.ms` to fix every timeout | Does not extend the broker transaction deadline | Measure and fix the right timeout |
| Treat commit `TimeoutException` as guaranteed abort | Commit outcome may be uncertain | Reconcile and enforce idempotency before replaying |
| Generate a new transaction ID per event | Wastes coordinator resources without fixing root cause | Prefix per producer instance; let factory manage suffixes |
| Apply Kafka Streams settings to the message binder | Different binders and runtimes | Configure according to the active binder |

## 33. Production Checklist for Transactional Kafka Workloads

- Clearly distinguish transactional binder vs Kafka Streams EOS.
- Enable transactions on the exact right binder and producer factory.
- Assign a unique `transaction-id-prefix` per active instance.
- Monitor rolling deployment overlaps, zombies, and producer cache expiry.
- Size timeouts from real processing times; verify against broker maximums.
- Separate transaction timeout, `max.block`, delivery, and `max.poll` limits.
- Use `read_committed` on consumers that must ignore aborted outputs.
- Configure `DefaultAfterRollbackProcessor`/retry and DLT for transactional mode.
- Check `txCommitRecovered` before choosing replay policies.
- Never swallow fatal fencing/epoch exceptions.
- Ensure fenced producers are closed and never reused.
- Verify DLT publishing, input offsets, and output visibility via broker integration tests.
- Build idempotency for database/HTTP side effects.
- Monitor transaction duration, abort/fence counts, lag, and LSO.
- Maintain a runbook for uncertain commit outcomes prior to replay.

## References

- [Spring Cloud Stream 5.0 — Kafka Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/transactional.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — After Rollback Processor](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#after-rollback-processor)
- [Apache Kafka 4.2 — Producer Configs](https://kafka.apache.org/42/configuration/producer-configs/)
- [Apache Kafka 4.2 — Broker Configs](https://kafka.apache.org/42/configuration/broker-configs/)
- [Apache Kafka 4.2 — KafkaConsumer read_committed](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Apache Kafka 4.2 — ProducerFencedException API](https://kafka.apache.org/42/javadoc/org/apache/kafka/common/errors/ProducerFencedException.html)
- [Apache Kafka 4.2 — KafkaProducer transaction API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)

APIs, defaults, and transactional error classifications can change across Kafka client, Spring Kafka, Spring Cloud Stream, and Kafka Streams versions. Consult the exact release train/BOM and running broker configuration before applying recovery procedures in production.

## Conclusion

**Rollback** can be the right mechanism to protect consistency between input offsets and output Kafka records when processing fails. **Timeouts** must be classified precisely: transaction deadline, producer blocking/delivery, or consumer poll. **Producer fencing** is a broker safeguard against stale producer sessions, never an error to retry with the fenced producer itself.

In the Spring Cloud Stream Kafka transactional binder, input offsets and output records can commit together in one transaction when executed on the right consumer thread and producer context; retries/DLT belong after rollback. In Kafka Streams, EOS is configured in its own runtime. Safe diagnosis requires comparing logs, transaction IDs/prefixes, producer epochs, timeout budgets, `read_committed` visibility, DLT records, and input offsets, while designing idempotency because side effects outside Kafka do not roll back with the transaction.

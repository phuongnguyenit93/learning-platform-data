# Zombie fencing

In transactional Kafka architectures, a **zombie** is a producer or consumer instance that has lost ownership of a piece of work yet remains active, or unexpectedly resumes running after hanging, losing network connectivity, or pausing too long. If a zombie is still allowed to write results and commit old offsets, two processes could complete the same record together, corrupt consumer group progress, and produce duplicates.

**Zombie fencing** is the mechanism that prevents a stale instance from completing operations that are no longer valid. Kafka has two distinct layers worth separating: **producer fencing** using `transactional.id` plus producer epoch, and **consumer zombie fencing** using consumer group membership metadata when offsets are sent into a Kafka transaction. Together they establish *exactly-once processing semantics* (EOS) for flows reading from Kafka and writing results back to Kafka.

In Spring Kafka, these mechanisms work effectively when the producer factory, Kafka transaction manager, transactional listener container, and downstream consumers are configured properly. They do not make non-Kafka side effects such as database writes, HTTP calls, or emails exactly-once. This lesson explains boundaries, configurations, and how to investigate zombie incidents in production.

## 1. How do zombies appear?

Suppose topic `payments.commands` has partition 0 assigned to consumer A in group `payment-worker`. A receives offset 100 and starts processing. Due to a stop-the-world GC pause or a hanging HTTP call, A fails to poll again before the deadline.

The coordinator detects A is no longer making progress; after membership changes, partition 0 is assigned to consumer B. B reads the uncommitted record and starts processing. When A recovers, the old code may continue executing even though the coordinator no longer recognizes A as the partition owner.

~~~text
T1: Partition 0 -> consumer A, generation G1
    A polls offset 100, starts processing

T2: A hangs or fails to poll on time
    Group rebalance -> partition 0 moves to B, generation G2
    B processes offset 100 from valid committed offset

T3: A recovers
    A tries to publish output and commit source offset with old context
    A is a zombie: lost ownership yet still executing code
~~~

Situations that commonly create zombies:

- Consumer exceeds `max.poll.interval.ms` due to slow processing, blocking backoff, or deadlocks.
- Long JVM pause followed by recovery after the group has already rebalanced.
- Network partition preventing the old process from learning partition ownership changed.
- Rolling deployment starting a new process before the old process stops completely.
- An old producer losing connectivity and resuming with a transactional identity already claimed by a new producer.
- Asynchronous processing keeping old work in a thread pool after the container revoked the partition.

The Kafka group coordinator can manage a single valid owner at a time, yet cannot immediately halt every CPU thread in an old application process. Fencing provides a safety barrier at the **commit protocol step**, where a process must prove its transaction/membership is still valid.

## 2. Three types of fencing that are easy to confuse

| Mechanism | Verification basis | Problem solved |
|---|---|---|
| Producer epoch fencing | `transactional.id` with producer ID/epoch | Old producer tries to write/commit after a new producer took over the same identity. |
| Consumer zombie fencing in EOS | Consumer group metadata when offsets join a Kafka transaction | Consumer that lost membership/generation tries to commit results of an old assignment. |
| Static member fencing | `group.instance.id` in consumer group | Two consumers claim the same static instance ID. |

These properties have different scopes:

- `transactional.id` identifies a **transactional producer** to the Kafka transaction coordinator.
- `transactionIdPrefix` is the namespace for Spring Kafka's producer factory to generate concrete `transactional.id` values.
- `group.id` identifies the consumer group.
- `group.instance.id` identifies a *static consumer member* within the group.
- Consumer group generation/member metadata represents valid group participation at the protocol step of committing offsets.

You cannot merely set `group.instance.id` and assume you have exactly-once Kafka transactions. Nor can you use `transactionIdPrefix` in place of group metadata to detect every zombie after a rebalance.

## 3. Producer fencing: transactional.id and producer epoch

A transactional Kafka producer initializes via `initTransactions()` with a `transactional.id`. The transaction coordinator manages the producer ID and epoch for that identity. When a new producer validly initializes with the same transactional ID, the broker can bump the epoch and strip the older producer of transaction rights.

~~~mermaid
sequenceDiagram
    participant P1 as Old Producer P1
    participant K as Kafka Transaction Coordinator
    participant P2 as New Producer P2
    P1->>K: initTransactions (transactional.id=X)
    K-->>P1: Producer epoch E1
    P1->>K: beginTransaction
    Note over P1: P1 hangs
    P2->>K: initTransactions (transactional.id=X)
    K-->>P2: Producer epoch E2
    Note over K: Epoch E1 is no longer valid
    P1->>K: commitTransaction with E1
    K-->>P1: Producer fenced / epoch invalid
    P2->>K: Commit transaction under E2
~~~

This diagram illustrates the principle; exact producer ID, epoch, and transaction state details are coordinated by the Kafka client/broker. P1 may receive `ProducerFencedException` or an epoch-related error depending on the operation and version.

Fencing is beneficial when a new producer **replaces an old logical producer**. However, if two valid independent replicas are configured with the same transactional ID, they will continuously fence each other. That is an identity bug, not a scaling strategy.

### Do not share prefixes across instances

Spring Kafka normally combines `transactionIdPrefix` with a suffix managed by `DefaultKafkaProducerFactory`. If two instances share a prefix and generate matching suffixes, their actual transactional IDs can collide.

~~~text
Wrong when running concurrently:
  Pod A: transactionIdPrefix = orders-tx-
  Pod B: transactionIdPrefix = orders-tx-

Better:
  Pod A: transactionIdPrefix = prod-orders-pod-a-tx-
  Pod B: transactionIdPrefix = prod-orders-pod-b-tx-
~~~

In multi-replica environments, the prefix should include service, environment, and a sufficiently unique instance identity. Do not create a new prefix per message; let the producer factory manage suffixes/caches over its lifecycle.

**Important:** in EOS V2, when A and B use different transactional IDs, producer epoch fencing between those two IDs does **not by itself** prevent A from committing a stale offset. That requires the group metadata mechanism covered next.

## 4. Zombie consumers after a rebalance

In a *consume–transform–produce* flow, a consumer receives an input record, publishes a Kafka result, and commits the input offset. If the offset commits independently of the output, a failure can cause duplicates or dropped results.

With a transactional listener container, Spring Kafka can put Kafka outputs and input offsets into the same transaction. When sending offsets into a transaction, Kafka needs **consumer group metadata** to verify whether the member is still valid.

For example, A owns partition 0 in generation G1. While A hangs, B receives the partition after a rebalance in G2. If A tries to finish its transaction with stale group metadata, Kafka can reject the transactional offset commit; outputs from the failed transaction are not treated as committed.

~~~mermaid
sequenceDiagram
    participant A as Consumer A, generation G1
    participant G as Group Coordinator
    participant B as Consumer B, generation G2
    participant T as Transaction Coordinator
    A->>G: JoinGroup, assigned partition 0
    A->>A: Poll offset 100, start processing
    Note over A: Stops polling too long
    G-->>B: Rebalance, assign partition 0
    B->>B: Process offset 100 in new transaction
    A->>T: sendOffsetsToTransaction with metadata G1
    T->>G: Verify group member's commit authority
    G-->>T: A/G1 is no longer valid
    T-->>A: Reject transactional commit
    B->>T: Commit with valid metadata G2
~~~

This is a logical diagram; internal messages between coordinators depend on the Kafka version. The key point is that **offsets are validated against membership**, not merely by group name or an offset value.

### Fencing does not necessarily stop old code from executing

A may still finish a calculation or an API call before receiving a fencing error. Kafka protects only operations within the Kafka transaction/membership protocol. Therefore, never rely on fencing as a mechanism to prevent all external side effects.

## 5. EOS V2 and KIP-447

KIP-447 extended the Kafka protocol so transactional offset commits use consumer group metadata and support fencing zombie consumers after rebalances. Spring Kafka supports EOS V2 in corresponding versions; starting from Spring Kafka 3.0, only EOS V2 remains, replacing the EOS V1 of older releases. EOS V2 requires a sufficiently recent Kafka broker supporting this mechanism (Kafka 2.5 or newer).

Key design points:

1. Producer transactions still carry `transactional.id` and epoch.
2. Consumer groups provide member/generation metadata.
3. Transactional producers send offsets into the transaction alongside group metadata.
4. The coordinator validates membership before letting the transaction commit offsets.
5. A zombie carrying stale metadata cannot simply be accepted as a member with commit authority.

EOS V2 enables a per-instance transactional ID model instead of needing a separate producer identity per group/topic/partition as some older implementations required. In Spring Kafka, each application instance still needs an independent `transactionIdPrefix` namespace when producers can operate concurrently.

Do not interpret EOS V2 as "Kafka will never redeliver a record." Kafka can redeliver on transaction aborts, rebalances, or process crashes. EOS here concerns **committed Kafka results** and **coordinated offsets**, not how many times the listener method was called.

## 6. Proper commit flow in Spring Kafka

A transactional listener for reading commands and emitting result events follows this sequence:

~~~mermaid
flowchart TD
    A[Container polls input record] --> B[Begin Kafka transaction]
    B --> C[Listener processes]
    C --> D[KafkaTemplate publishes output in transaction]
    D --> E{Listener finishes successfully?}
    E -->|Yes| F[Container sends input offsets and group metadata to transaction]
    F --> G{Offset commit valid?}
    G -->|Yes| H[Commit Kafka transaction]
    G -->|No| I[Abort / transaction failure]
    E -->|No| I
    I --> J[AfterRollbackProcessor retry or recovery]
~~~

A transaction can include output records across multiple partitions/topics. When the transaction commits, downstream consumers with `isolation.level=read_committed` see the committed outputs. When the transaction aborts, downstream in `read_committed` mode will not process output records as a successful transaction.

`read_uncommitted` consumers lack this guarantee: they can see uncommitted or aborted transactional records per Kafka semantics. Therefore, a pipeline with producer transactions whose downstream reads with `read_uncommitted` will not achieve the expected committed-result guarantee.

### The committed offset is the next position

If the record at offset 100 was processed successfully, the container puts offset 101 into the transaction for that partition. Do not confuse the record offset with the next committed offset.

If the transaction aborts, offset 101 is not committed as a successful transaction. When a valid member resumes, the source record can be redelivered from the previous committed offset.

## 7. Transaction configuration in Spring Boot

Example Spring Kafka service using a transactional producer and listener:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.internal:9092
    producer:
      transaction-id-prefix: prod-orders-INSTANCE_ID-tx-
      properties:
        "[acks]": all
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
    listener:
      ack-mode: record
      concurrency: 3
~~~

`INSTANCE_ID` is a placeholder to be replaced by a real identity, unique across concurrently active application instances/producer factories. Never use one fixed prefix for all replicas.

When matching auto-configuration conditions hold, Spring Boot can configure `KafkaTransactionManager` from the transactional producer factory. However, verify that the **effective listener container factory** actually uses that manager. If custom factories exist, never infer that a prefix makes every listener transactional.

Listener example:

~~~java
@KafkaListener(
        topics = "orders.commands",
        groupId = "orders-transformer",
        containerFactory = "transactionalListenerFactory")
public void transform(ConsumerRecord<String, OrderCommand> record) {
    OrderResultEvent result =
            orderTransformer.transform(record.value());

    resultKafkaTemplate.send(
            "orders.results",
            record.key(),
            result);
}
~~~

This snippet assumes:

- Bean `transactionalListenerFactory` is configured with the appropriate Kafka transaction manager.
- `resultKafkaTemplate` uses a producer factory capable of joining the container's transaction.
- Key/value serializers, topics, and ACLs are configured properly.
- The listener throws an exception to the container when a mandatory step fails.

The container manages placing offsets into the transaction; do not call `commitSync()` from the listener or another worker thread to bypass errors.

### Configuring the producer factory in Java

If the application does not rely completely on auto-configuration:

~~~java
@Bean
ProducerFactory<String, OrderResultEvent> resultProducerFactory() {
    Map<String, Object> config = new HashMap<>();
    config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1.example.internal:9092");
    config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
    config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderResultEvent> factory =
            new DefaultKafkaProducerFactory<>(config);
    factory.setTransactionIdPrefix("prod-orders-INSTANCE_ID-tx-");
    return factory;
}
~~~

In production, prefix and bootstrap servers must come from deployment configuration. The producer factory is just one piece; create a Kafka transaction manager and attach it to the container factory using the API matching your Spring Kafka version.

## 8. Configurations that do not replace zombie fencing

| Configuration | Role | What must not be inferred |
|---|---|---|
| `enable.auto.commit=false` | Disables Kafka consumer auto-commit so the container controls offsets | Does not create an output + offset transaction yet. |
| `ack-mode: record` | Listener container acknowledgment rule when applicable | Does not guarantee offsets are in the same transaction as outputs. |
| `group.instance.id` | Identifies a static consumer member across restarts | Not a Kafka producer `transactional.id`. |
| `max.poll.interval.ms` | Deadline between poll calls | Raising the timeout does not solve every zombie or deadlock. |
| `transactionIdPrefix` | Producer transactional ID namespace | Does not prove the consumer still owns the partition in the current group generation. |
| `isolation.level=read_committed` | Reads only committed Kafka transactional records | Does not prevent the listener method from re-running or duplicate HTTP requests. |

No single parameter can substitute for defining proper transaction boundaries.

## 9. Distinguishing ProducerFencedException and FencedInstanceIdException

`ProducerFencedException` relates to a transactional producer's right to use a `transactional.id`/epoch. `FencedInstanceIdException` relates to a static consumer member using an invalid `group.instance.id` or being replaced by another member with the same ID.

If two pods have:

~~~text
Pod A:
  group.instance.id = orders-consumer-0
  transactionIdPrefix = orders-tx-a-

Pod B:
  group.instance.id = orders-consumer-0
  transactionIdPrefix = orders-tx-b-
~~~

Then duplicate static member identity errors can appear even though producer prefixes differ. Conversely, two pods with different static member IDs yet the same producer prefix still risk producer fencing.

Distinguishing them prevents wrong fixes: changing `group.instance.id` does not fix transactional ID collisions; changing producer prefixes does not fix two static members sharing an ID.

## 10. Retry, rollback, and after-rollback recovery

In a Kafka transactional listener container, when a listener throws an exception, the Kafka transaction is rolled back/aborted. Spring Kafka has post-rollback handlers like `DefaultAfterRollbackProcessor` to seek/retry records or recover once attempts are exhausted.

Do not blindly apply offset-handling practices from non-transactional listeners onto transactional listeners. Some error-handler details and APIs vary by Spring Kafka version.

When a zombie is fenced:

1. Never try to continue committing the old transaction.
2. Never keep and reuse a fenced producer.
3. Let the container/framework handle rollback or stop depending on error type.
4. Let a valid consumer re-read from the committed offset as needed.
5. Keep listeners idempotent for all non-Kafka side effects.

If unprocessable records must be routed to a DLT, recovery must confirm DLT publishing and commit the recovered offset per the corresponding transaction policy. Never treat a failed DLT publish as successful recovery.

In Spring Kafka, standard non-blocking retries via `@RetryableTopic` **are not supported in direct combination with Kafka container transactions**. When long delays are required, adjust retries within the rollback model or design a separate workflow/retry topology; never mix both mechanisms and call it exactly-once.

## 11. max.poll.interval.ms and transaction.timeout.ms

Zombies can appear when a listener blocks too long. Two deadlines to watch:

| Property | Controls | Risk if exceeded |
|---|---|---|
| `max.poll.interval.ms` | Maximum interval between consumer `poll()` calls | Consumer can lose membership, trigger partition rebalance, and become a zombie on recovery. |
| `transaction.timeout.ms` | Maximum age of a Kafka transaction per broker limit | Coordinator can abort the expired transaction. |
| `session.timeout.ms` | Heartbeat timeout | Affects detecting disconnected members and reassigning partitions. |

Example:

~~~text
max.poll.interval.ms = 300000 (5 minutes)
transaction.timeout.ms = 60000 (1 minute)

T=00:00 A polls record and begins transaction
T=00:05 A calls external service, hangs
T=01:xx Transaction may time out and abort
T=05:xx Consumer may lose group membership
T=06:00 B receives partition and processes record
T=07:00 A recovers, tries to commit old transaction
         -> fails due to invalid transaction/identity/membership
~~~

Exact timing depends on broker/client, heartbeats, static membership, group protocol, and software versions. The example illustrates that transaction timeout and poll timeout are independent.

Do not raise both timeouts indefinitely just to mask slow listeners. Bound HTTP/DB timeouts, reduce `max.poll.records` if batches are too large, use appropriate retry backoff, and avoid holding transactions open across multi-minute jobs.

## 12. Static membership and zombie fencing

`group.instance.id` allows a consumer group to recognize a static member across restarts. This can reduce rebalances when an instance returns before `session.timeout.ms` expires. Yet static membership does not replace Kafka transactions.

When a static member exceeds `max.poll.interval.ms`, the client may stop heartbeating and the coordinator waits until session timeout before reassigning partitions. This can leave partitions held longer. Once ownership transfers, transactional consumer group metadata remains critical to prevent the old process from committing offsets as the current owner.

Therefore, manage two namespaces:

- `group.instance.id`: unique per static member in the consumer group.
- `transactionIdPrefix` / `transactional.id`: unique per appropriate transactional producer in the Kafka cluster.

Never set both fields identically across all replicas simply because both represent "instance."

## 13. Kafka EOS does not cover databases and HTTP

Suppose listener A processes `PaymentRequested`:

~~~text
Consumer A:
  - Receives event evt-17
  - Writes to database successfully
  - Hangs before Kafka transaction commit

Consumer B:
  - Re-receives evt-17 after rebalance
  - Writes to database a second time if lacking deduplication

Consumer A:
  - Recovers and hits Kafka zombie fencing
~~~

Kafka can prevent A's output transaction from committing erroneously, yet the database may already have been written during A's or B's execution. Producer fencing does not roll back database transactions.

Essential safeguards:

- Use a stable `eventId` and unique constraint/inbox in the same database transaction as business updates.
- When needing a DB update followed by a Kafka event, use a transactional outbox where appropriate.
- Call external APIs with partner-supported idempotency keys.
- Distinguish committed Kafka outcomes from actual business outcomes.
- Never ack/commit early while asynchronous work is still incomplete.

| Impact | Protected by Kafka transaction/fencing? | Required addition |
|---|---|---|
| Kafka output in same transaction | Yes, via commit/abort and `read_committed` | Proper template/container and producer transaction wiring. |
| Source offset in same transaction | Yes, with valid group metadata | Never commit offsets outside the transaction. |
| Separate database update | No | DB transactions, deduplication/inbox. |
| HTTP request or payment call | No | Idempotency keys and result state tracking. |
| Email/SMS | No | Outbox, dedupe, or resend policies. |

Only state **exactly-once within Kafka transaction scope** when describing the pipeline; avoid claiming "the whole system never repeats."

## 14. Testing zombie fencing with fault injection

Test failure windows in staging/integration environments with an appropriate Kafka broker; never induce intentional producer collisions in production.

### Test A: producer epoch fencing

1. Initialize transactional producer P1 with ID `test-zombie-X`.
2. Begin a transaction and send a record without committing.
3. Initialize producer P2 with the **same transactional ID**.
4. Let P2 finish initializing valid transactional identity.
5. Let P1 attempt to commit the old transaction.
6. Verify P1 loses commit rights or receives a fencing/epoch error.
7. Read outputs with `read_committed` to confirm records from the uncommitted transaction are not visible as valid results.

### Test B: consumer group fencing after rebalance

1. Run transactional listener A processing partition 0.
2. Pause A at a controlled step and trigger a group assignment change.
3. Run listener B so B gets partition 0 and processes from the committed offset.
4. Let A continue sending output/committing the transaction using old group context.
5. Verify A's transaction cannot commit offsets as a valid member.
6. Read outputs with a `read_committed` consumer and compare with committed offsets.
7. Verify B can complete transactions cleanly and no unauthorized output from A is committed.

### Test C: side effects can still duplicate

1. Have A write to the database successfully, then stop before Kafka commit.
2. Have B re-read the event after rebalance.
3. Observe the database can be updated twice without idempotency.
4. Add an inbox / unique event ID and re-run.
5. Verify only one database effect is applied even though the listener may be called multiple times.

In each test, log poll timing, group generation/assignment, transaction begin/abort/commit, event IDs, and output outcomes. Never rely on a single exception to declare all of EOS verified.

## 15. Monitoring and diagnostics

| Signal | Observation purpose |
|---|---|
| `ProducerFencedException` / producer epoch errors | Detects stale producers or `transactional.id` collisions. |
| Transaction begin/commit/abort | Tracks successful transactions and rollbacks. |
| Transaction duration p95/p99 | Detects transactions nearing timeout. |
| Consumer rebalance, partition revoked/assigned | Pinpoints when partition ownership moves. |
| Listener processing duration and poll interval | Detects risk of exceeding `max.poll.interval.ms`. |
| Consumer group generation/member metadata when emitted | Correlates old processes with membership loss. |
| Committed offsets and `read_committed` output | Verifies valid committed Kafka outcomes. |
| External idempotency collisions | Detects side effects facing duplicate attempts. |
| DLT/recovery status | Confirms failing records are handled after abort/retry. |

Structured logs should include application instance, group ID, listener ID, topic, partition, offset, event ID, exception class, transaction status, and rebalance timestamps. Do not put event IDs or changing transactional IDs into metric labels with high cardinality. Never log tokens, secrets, or sensitive payloads.

A single fencing event when an old producer is replaced may match design expectations. **Repeated continuous fencing across valid live instances** is an incident signal requiring investigation, usually tied to duplicate prefixes or broken producer lifecycles.

## 16. Runbook when ProducerFencedException occurs repeatedly

1. Record cluster, service, environment, pod/VM, producer factory, and transactional ID if available.
2. Find all instances capable of generating that transactional ID, including old processes during rolling deployments.
3. Inspect the effective `transactionIdPrefix`, suffix strategy, and instance ID source.
4. Determine whether fencing is an old producer being replaced cleanly or two valid instances fencing each other.
5. On collision, assign unique prefixes to each instance/factory that can run concurrently.
6. Never reuse a fenced producer; let the framework close/discard it and handle the failed transaction.
7. Inspect input offsets, Kafka outputs, and non-Kafka side effects of aborted transactions.
8. Monitor abort/fencing rates and consumer lag after fixing the deployment.

Never disable Kafka transactions or generate a random transactional ID per record just to silence the exception. Those workarounds destroy the protection boundaries you need.

## 17. Runbook when a consumer recovers after a rebalance

1. Identify topic/partition/offset and when consumer A began processing.
2. Read rebalance logs: when A was revoked and when B was assigned.
3. Cross-check `max.poll.interval.ms`, `session.timeout.ms`, transaction timeout, and listener duration.
4. Verify the container actually sends offsets with group metadata into the Kafka transaction.
5. Determine whether A's commit error was group membership fencing, producer epoch fencing, or transaction timeout.
6. Check `read_committed` downstream; verify output from A's failed transaction is not processed as committed.
7. Confirm B processed/committed the record validly.
8. For databases/HTTP, check idempotency and run compensation if duplicate side effects occurred.
9. Reduce processing time / blocking retries and reproduce the rebalance scenario in staging.

Never arbitrarily reset offsets to "sync" with a zombie. Wrong resets can skip unprocessed records or cause unwanted replays.

## 18. Runbook when a static member is fenced

1. Verify whether the exception is actually `FencedInstanceIdException`.
2. Identify `group.id` and `group.instance.id` of running members.
3. Find pods/VMs with duplicate static IDs; inspect ordinals, rollout overlap, and instance identities.
4. Stop the mis-mapped process and restore static membership per procedure.
5. Inspect `transactionIdPrefix` **separately** to rule out Kafka producer collisions.
6. Verify group assignments, committed offsets, and Kafka transaction outcomes.

Static membership fencing and producer fencing can occur simultaneously in a broken deployment, yet never conflate the root causes of the two exceptions.

## 19. Zombie fencing control matrix

| Checkpoint | Question to answer | Evidence |
|---|---|---|
| Producer identity | Do independent transactional producers have distinct full IDs? | Prefix/suffix and replica inventory. |
| EOS protocol | Do broker/client/Spring Kafka support EOS V2 group metadata? | Versions, transaction mode, and integration tests. |
| Container transaction | Are input offsets and Kafka outputs in the same transaction? | `KafkaTemplate`, producer factory, and transaction manager wiring. |
| Group membership | Are zombie consumers rejected when committing offsets after rebalance? | Group generation, logs, and transactional offset commit errors. |
| Output visibility | Do downstream consumers needing EOS use `read_committed`? | Consumer effective config. |
| Poll budget | Is the listener polling within budget? | `max.poll.interval.ms` and listener duration p99. |
| Transaction timeout | Do transactions finish before the deadline? | `transaction.timeout.ms` and transaction duration. |
| Static membership | Is `group.instance.id` unique within the group? | Instance mapping and fencing logs. |
| External idempotency | Are databases/APIs safe if both A and B run the logic? | Unique event IDs, inbox/outbox, and fault-injection tests. |
| Recovery | Do transaction aborts lead to proper retry/recovery? | `AfterRollbackProcessor`, DLT, and committed offsets. |

**Conclusion:** Zombie fencing prevents a producer or consumer that lost ownership from completing a Kafka transaction under a stale context. Kafka uses `transactional.id` and producer epochs to fence old producers; in EOS V2, consumer group metadata enables rejecting offset commits from zombies after rebalances, even when instances have different producer IDs. Spring Kafka leverages this when the transactional listener container, `KafkaTemplate`, and transaction manager are wired properly. Reliable operation also requires unique prefixes, sensible poll/transaction deadlines, `read_committed` downstream, and idempotency for all non-Kafka effects.

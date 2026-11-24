# EOS and retry topics

**Exactly-Once Semantics (EOS)** and **retry topics** solve two different problems in Spring Kafka systems. Kafka EOS aims to **atomically commit output records and input offsets** in a Kafka-to-Kafka pipeline. Retry topics, particularly Spring Kafka's **non-blocking retries**, route a failing record to an intermediate topic to be reprocessed after a delay, keeping the original consumer from being blocked by that record.

Combining both concepts without defining transaction boundaries can lead to false conclusions: **"transactions enabled" does not mean "every hop to a retry topic is exactly-once."** A record may be written to a retry topic and then forwarded a second time if the process dies before confirming the offset. A retried record may complete after a record that arrived later, inverting business order. When databases, HTTP APIs, or emails are involved, Kafka transactions do not automatically roll back external side effects either.

This lesson explains the guarantees of each mechanism, limitations when combining them, alternative designs, and how to observe failure windows in Spring Kafka.

## 1. Defining exactly what "exactly once" means

An event can pass through multiple steps:

~~~text
Producer -> input topic -> consumer/listener -> output topic -> downstream consumer
                               |
                               +-> database, HTTP API, email...
~~~

Common guarantee levels:

| Guarantee level | Meaning | Example risk |
|---|---|---|
| At-most-once | May lose records while avoiding reprocessing | Offset commits before side effect finishes |
| At-least-once | Does not intentionally drop records, yet may redeliver | Side effect ran, process dies before offset commit |
| Kafka EOS for consume–process–produce | Kafka outputs and input offsets commit atomically in a Kafka transaction | Does not cover databases/HTTP outside the Kafka transaction |
| Exactly-once business effect | A business effect applies once per event ID/invariant | Requires idempotency, inbox/outbox, or suitable transaction design |

**EOS does not mean the Java listener runs only once.** If a Kafka transaction rolls back or the process dies before commit, the same input can be executed by the listener again. What is protected is the transactional output alongside input progress of successful transactions, when downstream reads with `isolation.level=read_committed`.

Kafka EOS also does not eliminate *duplicate business events* published by a producer as distinct records. If upstream sends two records with the same `eventId`, a container transaction can process and commit both unless business logic deduplicates them.

## 2. Standard Spring Kafka EOS: outputs and offsets in the same transaction

In a listener container configured with a Kafka transaction manager, the typical processing path is:

~~~mermaid
sequenceDiagram
    participant K as Input topic
    participant C as Listener container
    participant L as Business listener
    participant P as Transactional Kafka producer
    participant O as Output topic
    K-->>C: Poll record offset N
    C->>P: Begin Kafka transaction
    C->>L: Invoke listener
    L->>P: Send output record
    P-->>O: Write as uncommitted
    L-->>C: Return success
    C->>P: Add input offset to transaction
    C->>P: Commit Kafka transaction
    Note over O: Visible to read_committed consumers
~~~

If the listener throws an exception or the transaction aborts, uncommitted outputs are hidden from `read_committed` consumers and input offsets are not committed by the failed transaction.

| Scenario | Transactional output | Input offset |
|---|---|---|
| Commit succeeds | Takes effect | Committed in the same transaction |
| Aborts due to listener error | Invisible to `read_committed` | Not committed by that transaction |
| Process dies before commit | May be broker-aborted / handled per broker state | Input can be redelivered |
| DB committed yet Kafka aborted | DB remains mutated | Input can be redelivered |

The last case proves the EOS boundary covers only resources genuinely participating in the Kafka transaction.

## 3. How do non-blocking retry topics work?

Spring Kafka supports routing failing records to retry topics instead of holding the original consumer across a long backoff. Retry listeners read records from intermediate topics and delay processing until the wait interval elapses.

~~~text
orders
  |
  +-- listener fails
       |
       v
orders-retry-1000    (wait ~1 second)
       |
       +-- still fails
            |
            v
orders-retry-2000    (wait ~2 seconds)
            |
            +-- still fails
                 |
                 v
orders-dlt          (retry budget exhausted)
~~~

Topic names are illustrative; the framework uses configurable suffix strategies and topic reuse. The Kafka broker itself does not know that a topic ending in `1000` must hold records for exactly 1,000 ms. Retry listener infrastructure uses metadata and pause/resume mechanics to enforce delays.

Forwarding a record to a retry topic creates a **new publish** with its own topic, partition, and offset. Retry consumers use different consumer groups/offsets and lifecycles than the original consumer. Without a transaction explicitly designed to combine forwarding with the source offset, a gap exists that can produce duplicates.

## 4. Why are EOS and retry topics easily mistaken as compatible by default?

Suppose record A at `orders-1@42` fails. A retry mechanism performs:

~~~text
(1) Read orders-1@42
(2) Publish A to orders-retry-1000
(3) Acknowledge/commit offset of orders-1
(4) After delay, retry consumer processes A
~~~

If steps (2) and (3) are **not** committed atomically:

- Retry publish succeeds, yet process dies before offset commit: A can be re-read on the original topic and published a second time to the retry topic.
- Offset commits even though the retry publish actually failed: risks losing the record's processing path if error handling is flawed.
- Retry consumer finishes a side effect then dies before committing the retry topic offset: A is redelivered and the side effect can repeat.
- Forwarding to DLT succeeds while retry offset is uncommitted: an extra DLT copy can appear after restart.

In other words, **retry topics can preserve processing continuity via at-least-once delivery, yet do not automatically guarantee exactly-once business effects**.

A Kafka transactional producer can help build an atomic *consume-from-topic-X → produce-to-topic-Y + commit X's offset* hop if both genuinely sit in the same Kafka transaction. However, that requires deliberate per-hop design, not an automatic guarantee arising from adding a retry-topic annotation.

## 5. Key limitation: @RetryableTopic with container transactions

In common Spring Kafka releases supporting retry topics, **non-blocking retries via `@RetryableTopic` do not combine directly with container transactions** under the default configuration flow. Additionally, non-blocking retry topics carry specific constraints with batch listeners.

Therefore, avoid deploying:

~~~java
// ILLUSTRATION OF PATTERN TO AVOID / NOT SUPPORTED BY DEFAULT
@RetryableTopic(attempts = "4")
@KafkaListener(
    topics = "orders",
    containerFactory = "transactionalListenerFactory")
public void onMessage(OrderEvent event) {
    // Do not assume retry annotations and Kafka container
    // transactions combine into one EOS pipeline.
}
~~~

This example illustrates a **problematic configuration to avoid**, not a recommended code pattern. When running a Spring Kafka transactional listener, use rollback and retry mechanisms compatible with container transactions or build a separate topology with verified transaction boundaries.

When upgrading Spring Kafka versions, consult your project version's documentation/APIs for exact support levels. Never infer from a simple test snippet running without error that retry-topic forwarding and offsets are atomic.

## 6. Configuring Kafka transactions for listeners

For reading from Kafka and writing to Kafka, an illustrative Spring Boot configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example:9092,kafka-2.example:9092
    producer:
      transaction-id-prefix: order-transform-instance-01-
      acks: all
    consumer:
      group-id: order-transformer
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Key points:

- `transaction-id-prefix` must be managed so transactional IDs do not collide across concurrently active producers/instances.
- `enable-auto-commit: false` explicitly leaves offsets coordinated by the container instead of Kafka client auto-commits.
- `read_committed` is especially crucial for **downstream consumers** reading transactional outputs, since `read_uncommitted` consumers can see later-aborted records.
- `acks: all` aligns with durability goals of transactional publishing.
- If using a custom listener factory, attach the transaction manager properly; never assume every factory is transactional just because a property is set.

A transaction manager created from a transactional `ProducerFactory`:

~~~java
@Bean
KafkaTransactionManager<String, OutputEvent> kafkaTransactionManager(
        ProducerFactory<String, OutputEvent> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Attaching it to the container factory in versions supporting the corresponding API:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, InputEvent>
transactionalListenerFactory(
        ConsumerFactory<String, InputEvent> consumerFactory,
        KafkaTransactionManager<String, OutputEvent> txManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, InputEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setKafkaAwareTransactionManager(txManager);
    factory.getContainerProperties()
           .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
~~~

This snippet illustrates Spring Kafka using `setKafkaAwareTransactionManager`; older versions may use a different API. Ensure the `KafkaTemplate` sending outputs uses the **exact same transactional producer factory** coordinated by the transaction manager.

## 7. Preferred approach for EOS: blocking retries and after-rollback

When Kafka EOS and transient-error handling are needed, a simpler path is letting the container transaction roll back and using **`DefaultAfterRollbackProcessor`** for seek/retry/recovery instead of switching to non-blocking retry topics.

~~~mermaid
flowchart TD
    A["Consume from source topic"] --> B["Begin Kafka transaction"]
    B --> C["Listener processes, sends Kafka output"]
    C --> D{"Listener succeeded?"}
    D -->|Yes| E["Offset + output commit in tx"]
    D -->|No| F["Abort transaction"]
    F --> G["AfterRollbackProcessor"]
    G --> H{"Retries remaining?"}
    H -->|Yes| I["Backoff + seek/re-read"]
    I --> A
    H -->|No| J["Recovery/DLT per policy"]
~~~

Conceptual configuration example:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, InputEvent>
afterRollbackProcessor(DeadLetterPublishingRecoverer recoverer) {
    return new DefaultAfterRollbackProcessor<>(
        (record, exception) -> recoverer.accept(record, exception),
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Attaching the processor to the factory:

~~~java
factory.setAfterRollbackProcessor(afterRollbackProcessor);
~~~

`FixedBackOff(1_000L, 3L)` means a 1-second pause and up to three retries per `FixedBackOff` semantics. Classify permanent data errors so they do not retry pointlessly; fatal exceptions may need immediate recovery.

**Very important:** Having only an after-rollback processor and recoverer **does not prove** DLT publishing and committing the recovered offset happen in the same Kafka transaction. To commit recovery in a new transaction, configure `commitRecovered` and the corresponding Kafka operations/template per your Spring Kafka version's API.

## 8. Choosing a model based on business requirements

| Most important requirement | Design direction |
|---|---|
| Kafka input offsets and Kafka outputs must commit together | Container Kafka transactions + compatible retry/rollback flow |
| Transient errors, must preserve partition order | Blocking retry/backoff after rollback |
| Prolonged errors, must preserve source topic throughput | Separate retry topic/workflow, accept at-least-once and handle duplicates |
| Per-aggregate/key ordering mandatory | Keep per-partition processing or workflows with state/sequence |
| Must combine retry topics with atomic forwarding | Design each transactional consume→produce→offset hop explicitly, do not rely on default annotations |
| Database updates and Kafka outputs | Transactional outbox + inbox/idempotency per invariant |
| Permanent payload errors | DLT/quarantine, do not retry continuously |
| Retries after hours/days | Durable workflow scheduler or delayed queue by dedicated design |

No single option is optimal for every pipeline. Transactional blocking retries can stall a partition for a while; retry topics boost throughput at the cost of ordering and extra hops where duplicates must be handled.

## 9. Processing order when records travel through retry topics

Kafka preserves ordering **within a single partition of a single topic**. Once record A moves to a retry topic, record B on the original topic can be processed before A.

~~~mermaid
sequenceDiagram
    participant K as orders-1
    participant L as Original listener
    participant R as orders-retry-1000
    participant S as Business state
    K-->>L: A = OrderCreated, offset 10
    L-->>R: Forward A due to error
    K-->>L: B = OrderCancelled, offset 11
    L->>S: Apply B
    Note over R: Wait delay
    R-->>S: Apply A later than B
~~~

If processing B before A breaks the state machine, non-blocking retry topics may be unsuitable. **Kafka transactions do not automatically preserve ordering across different topics.**

Safeguards:

- Use event versions/sequences and optimistic locking per aggregate.
- Ignore stale events superseded by newer versions if business rules allow.
- Park early-arriving events in a pending table and apply only when dependencies/sequences are valid.
- Choose blocking retries when ordering matters more than throughput.
- Implement idempotency by event ID rather than relying purely on current offsets.

## 10. Kafka EOS does not cover database and HTTP side effects

Suppose a transactional listener both writes to a DB and publishes to Kafka:

~~~java
@KafkaListener(
    topics = "payments.received",
    containerFactory = "transactionalListenerFactory")
public void onPayment(PaymentReceived event) {
    paymentService.updateDatabase(event); // separate DB transaction
    kafkaTemplate.send(
        "payments.applied",
        event.paymentId(),
        new PaymentApplied(event.paymentId())
    );
}
~~~

A possible failure window:

~~~text
1. Kafka container transaction begins.
2. DB writes and commits successfully.
3. Kafka output/offset commit fails.
4. Input is redelivered after rollback/restart.
5. Listener updates DB a second time if not idempotent.
~~~

Kafka transactions cannot roll back an already-committed database transaction. Retry topics introduce additional deliveries from intermediate topics, making idempotency even more critical.

Typical solutions:

- **Inbox:** write the processed event ID and business state in the same DB transaction.
- **Outbox:** write business state and outgoing event in the same DB transaction; a publisher sends to Kafka afterward.
- **Idempotency key:** pass a stable business ID to HTTP/payment APIs if supported by the provider.
- **Saga/workflow:** manage progress and compensation across multi-step external systems.

Simply adding Spring's `@Transactional` to a method without checking transaction managers and resources does not merge two systems into a distributed atomic transaction.

## 11. Example idempotent consumer for retry topics

An event must keep a stable ID across the original topic, retries, and DLT:

~~~json
{
  "eventId": "evt-91fe",
  "orderId": "order-101",
  "eventType": "OrderApproved",
  "schemaVersion": 2
}
~~~

The application can enforce a unique constraint on `event_id`:

~~~java
@Service
public class OrderProjectionService {

    @Transactional // database transaction
    public void apply(OrderApproved event) {
        boolean firstProcessing =
            processedEventRepository.insertIfAbsent(event.eventId());

        if (!firstProcessing) {
            return;
        }

        orderRepository.markApproved(event.orderId());
    }
}
~~~

`insertIfAbsent` is conceptual: implement via a unique-key insert inside a real DB transaction. The processed marker and business update must commit in **the same DB transaction**.

However, there is a subtle trap: if the DB commits, the first attempt's Kafka output rolls back, and then the replay returns early because the inbox says "already processed," the required Kafka output may never be sent. For pipelines combining DB+Kafka, use an outbox or a mechanism that deterministically re-emits outputs from committed state—do not stop at adding an inbox.

For Kafka-only transformations, container transactions solve output/offset atomicity better than manual offset commits. Idempotency by business event ID is still needed if producers or retry stages can emit multiple records carrying the same event ID.

## 12. Transaction identity and read_committed across multiple stages

A Kafka transaction uses `transactional.id` to identify the producer. When scaling consumer instances or listener concurrency, transactional IDs must be managed to prevent producer fencing.

~~~text
pod-A: transaction-id-prefix = orders-tx-A-
pod-B: transaction-id-prefix = orders-tx-B-
pod-C: transaction-id-prefix = orders-tx-C-
~~~

If two producers concurrently use the same transactional ID, the broker can fence one producer. Errors such as `ProducerFencedException` are not per-record data errors and must be handled at the lifecycle/transaction layer, not forwarded fruitlessly through every retry topic.

For custom retry topics built with Kafka transactions, **every hop** must verify:

1. Which transactional producer publishes to the next stage?
2. Is the current stage's consumer offset sent into that same transaction?
3. Does the consumer reading the next stage use `read_committed`?
4. Are any publish/commit steps occurring outside the transaction?
5. How does recovery behave when a process dies mid-transaction?

One stage protected by Kafka EOS does not make the entire business workflow exactly-once if another stage uses at-least-once publishing or non-Kafka side effects.

## 13. Is adding manual transactions to a retry pipeline enough?

In principle, you can build a custom retry topic system where each forward runs inside a transaction:

~~~text
Retry stage X:
  begin Kafka transaction
  read record from X
  publish same business event to Y
  send consumed offset of X to transaction
  commit

Retry stage Y:
  read_committed consumer receives record
~~~

If every hop executes properly, per-hop forwarding atomicity can be preserved. However, implementation must also handle:

- Transaction lifecycle and producer fencing.
- Delay rules, timestamps, partition pause/resume.
- DLT publishing and recovered offsets.
- Serialization errors in the forwarding producer.
- Rebalances and partition assignments.
- Idempotency of business handlers.
- Cross-topic ordering.
- Observability of event state across stages.

That constitutes a **dedicated architecture**, not advice to swap `@RetryableTopic` for a few `KafkaTemplate` calls and assume EOS. Verify real failure windows and compatibility with your deployed Spring Kafka version.

## 14. DLT does not mean business success

Once a record exhausts retries, moving it to a Dead Letter Topic (DLT) may be a **terminal state for the consumer**, yet does not mean the business operation succeeded.

A typical recovery workflow:

~~~text
Input record failed repeatedly
       |
       v
Classify permanent/transient
       |
       +-- Recover to DLT
       |
       +-- Store original topic/partition/offset
       +-- Store exception and event ID
       +-- Alert owner
       |
       v
Manual/controlled replay after fixing cause
~~~

If DLT publishing succeeds while the source stage offset fails to commit, the record can be sent to the DLT a second time. If the offset commits while DLT publishing fails, the system risks losing the recovery path. You must choose atomic recovery when required, or accept duplicate DLT entries and deduplicate by event ID/source provenance.

DLT entries should preserve metadata such as original topic, partition, offset, consumer group, exception class, and event ID. Never alter event IDs during replay. If copying full stack traces/headers across stages, watch record sizes and sensitive data.

## 15. Actual execution counts can exceed configured attempts

A non-blocking retry annotation:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(topics = "orders", groupId = "order-processor")
public void process(OrderEvent event) {
    orderService.apply(event);
}
~~~

This example applies to a listener **not using Kafka container transactions** in an environment supporting `@RetryableTopic`. `attempts = "4"` means one initial attempt plus up to three retries orchestrated by this topology; not four additional retries.

However, **actual business executions** can be higher if:

- The HTTP client has internal retries.
- The service layer has `@Retryable` or its own retry library.
- Records are redelivered after a consumer crash/rebalance.
- Forwarding to a retry topic executes twice across a failure window.
- The DLT is replayed after resolving an incident.
- Upstream emits duplicate business events.

Never use the annotation's `attempts` count as proof that side effects run at most four times in all circumstances. That number describes the topology's retry policy, not a mathematical end-to-end bound across crashes/duplicates/replays.

## 16. Handling transient vs. permanent errors

| Error | Typically suitable policy | EOS/retry impact |
|---|---|---|
| Transient HTTP 503/timeout | Retry with bounded backoff | Requires API idempotency |
| Transient database connection error | Retry + monitor outage | Separate DB transactions still need idempotency |
| Unparseable JSON/schema | Non-retryable, DLT/quarantine | Retrying the same bytes will not make the payload valid |
| Terminal business rule violation | Do not retry fruitlessly | Store rejection result or route to DLT per policy |
| Kafka producer fencing | Investigate transactional IDs, lifecycle | Do not treat as a per-record business error |
| Kafka transaction timeout | Optimize processing time/timeout | Rolls back, may redeliver |
| DLT publisher failure | Recovery incomplete | Never silently drop the record |

With transactional listener containers, use retries compatible with rollback flows. With non-transactional retry topics, error classification decides whether to forward to a retry stage or DLT. Both cases require a clear termination point.

## 17. Compatibility with batch listeners and long-running retries

Spring Kafka's non-blocking retry topics primarily target **record listeners**; do not assume they work identically with batch listeners across all versions. With batch + transactions, an error can roll back the whole batch, even if some records already caused non-Kafka side effects.

If a record must wait minutes or hours before retrying, keeping an open Kafka transaction during the wait is an unsuitable design:

- `transaction.timeout.ms` limits how long a transaction may stay open.
- `max.poll.interval.ms` and consumer group lifecycles must be maintained.
- Long-open transactions block `read_committed` reading via Last Stable Offset.
- Kafka transactions are not a long-term task scheduler.

Using a durable workflow or retry topics with clear boundaries and idempotency usually makes more sense for long delays. Still, that is a **consistency trade-off**, not "an easier way to turn on EOS."

## 18. Failure matrix: which questions determine guarantee level?

| Failure point | Risk without atomic forward/offset | Mechanism to consider |
|---|---|---|
| Crash before retry publish | Original record may be redelivered | At-least-once, valid retry |
| Crash after retry publish, before source offset commit | Two copies of same event on retry topic | Atomic forward+offset or dedup |
| Retry publish fails yet offset commits | Retry path lost | Never commit progress until recovery succeeds |
| Retry listener produces side effect then crashes | Side effect may repeat | Idempotency/inbox |
| DLT publish OK yet source offset uncommitted | Duplicate DLT | Dedup by event ID/source |
| DB commit succeeds yet Kafka aborts | DB update may re-execute | Inbox/outbox |
| Listener swallows exception and returns success | Container may commit despite unfinished business work | Propagate failures with proper semantics |
| Output consumer reads `read_uncommitted` | May see aborted records | Configure `read_committed` |
| Retried record processed after newer event | Inverted business order | Version/sequence/state machine |

This matrix does not replace concrete transaction design; it helps locate the exact failure windows requiring protection.

## 19. Observability: do not watch only source-topic consumer lag

When retry topics operate, source-topic lag may look low while the real backlog sits in retry topics or the DLT. One business event can traverse multiple topics at different offsets.

Monitor:

- Volume forwarded from source topic to each retry topic.
- Lag and oldest record age per retry stage.
- Execution counts per event ID in logs/tracing (never use event IDs as metric labels).
- Kafka transaction commit/abort errors and transaction duration.
- Producer fencing, transaction timeouts, consumer group rebalances.
- Duplicates caught by inbox/idempotency.
- DLT volume, DLT publish failures, and replay success rate.
- Time from initial event to business completion, including retry delays.
- Event ordering per aggregate/version when business logic depends on order.

Metric labels should use low-cardinality fields like topic, stage, event type, exception class, and outcome. Event IDs, original offsets, and trace IDs belong in logs/tracing, not as metric labels across millions of events.

## 20. Runbook when duplicates occur after enabling retry topics

1. **Isolate the duplicate:** Are there two Kafka records with the same event ID, or was one Kafka record run multiple times by a listener?
2. **Locate where it duplicated:** Retry topic, DLT, output topic, database, or HTTP side effect?
3. **Read metadata:** Original topic/partition/offset, event ID, attempt, consumer group, and retry stage.
4. **Check transactional boundaries:** Were the forwarding producer and source offset committed in the same Kafka transaction?
5. **Check application crashes/rebalances:** Did an outage happen between publish and offset commit?
6. **Check idempotency:** Are inbox unique constraints / idempotency keys working?
7. **Check downstream isolation:** Do output consumers use `read_committed`?
8. **Check stacked retries:** Are HTTP clients, service retries, and `@RetryableTopic` multiplying calls?
9. **Check ordering:** Did an old event retried after a newer event corrupt state?
10. **Fix and replay carefully:** Keep event IDs intact; never re-send the entire DLT before knowing the root cause.

If duplicates live in DB/HTTP, merely turning on Kafka producer transactions will not fix them. If duplicates are two committed copies of the same business event created by separate transactions, `read_committed` will not deduplicate them either.

## 21. Runbook when a transactional listener stalls offsets

For listeners using Kafka container transactions, check:

- Is the listener throwing exceptions continuously? Read the cause and classify transient vs. permanent.
- Does `DefaultAfterRollbackProcessor` have a bounded retry budget?
- Is a dependency timeout holding transactions open too long?
- Is producer fencing occurring due to shared prefixes across pods?
- Is `KafkaTemplate` using the container's transactional producer factory?
- Are the broker transaction coordinator and ACLs healthy?
- Is downstream blocked by an open transaction and `read_committed`/LSO?
- Is recovery/DLT failing and forcing the record to reprocess?

Never simply reset offsets to clear lag. Wrong resets can skip business records and mask the real transaction/rollback root cause.

## 22. Illustrative scenarios for clarifying semantics

### Case A — Kafka-only transform, single transaction

Input A is read from `orders`, the listener publishes output A' to `shipments`, and commits the offset in the same Kafka transaction. If the transaction aborts, `read_committed` consumers do not see A'. After restart, A can be invoked again and the new transaction commits A' along with the offset.

**Expected outcome:** Kafka output and input offset share one fate; the listener may re-execute, yet no aborted output is visible to downstream with proper isolation.

### Case B — Default non-blocking retry, process crashes during forward

Input A is published to `orders-retry-1000`. Before the source topic offset commits, the process dies. On recovery, the original consumer re-reads A and publishes it again to the retry topic.

**Possible outcome:** Two retry records share the same event ID. Deduplication/idempotency or deliberate atomic forward/offset design is required.

### Case C — Retry succeeds, yet DB was already written on the first attempt

The consumer writes to the DB on the first run and fails before acknowledging the record. The retry listener receives A and writes to the DB again. Even if Kafka transactions and offsets are handled cleanly at some stages, the DB does not roll back with Kafka.

**Required outcome:** Inbox unique constraint in the same DB transaction to block duplicate side effects; if Kafka output is also needed, consider an outbox so output is not lost when the retry skips the second DB write.

### Case D — Retries invert ordering

A (`OrderCreated`) is routed to retry; B (`OrderCancelled`) processes immediately on the original topic. After the delay, A runs again and tries to create an already-canceled order.

**Required outcome:** Version/sequence ordering checks or designs that prevent B from overtaking A when invariants require it.

## 23. Checklist for designing EOS and retry topics

- [ ] Defined whether EOS must protect a Kafka-only pipeline or also business side effects?
- [ ] Are Kafka outputs and input offsets in the same transaction when claiming Kafka EOS?
- [ ] Do critical downstream consumers use `read_committed`?
- [ ] Are transactional ID prefixes unique across active instances?
- [ ] Do transactional listeners use compatible after-rollback/recovery instead of misusing `@RetryableTopic`?
- [ ] If using retry topics, have publish/commit failure windows and duplicates been documented?
- [ ] Are durable event IDs, idempotency keys, and deduplication in place?
- [ ] Has ordering across original topics and retry topics been evaluated?
- [ ] Have total attempts across all retry layers and processing durations been calculated?
- [ ] Are failed DLT publishes prevented from being treated as successful processing?
- [ ] Do runbooks and metrics cover every retry stage, not just the source topic?
- [ ] If DB/HTTP exist, have inbox/outbox/workflow patterns been chosen for each invariant?

**Conclusion:** Spring Kafka EOS and non-blocking retry topics are two tools with complementary goals that do not combine by default into an end-to-end exactly-once guarantee. When atomic Kafka output + source offset is needed, use container transactions and compatible rollback/retry handling. When long delays and sustained throughput are needed, retry topics can be a strong choice provided duplicate risks, ordering shifts, and full idempotency/recovery are designed in. For databases or non-Kafka systems, business guarantees must be built inside those systems themselves and cannot rely solely on Kafka transactions.

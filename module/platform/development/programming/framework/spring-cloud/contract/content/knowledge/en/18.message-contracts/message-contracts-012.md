# Limits of verifying ordering, redelivery, and exactly-once processing

## 1. Why can a valid message contract still yield wrong outcomes?

In asynchronous systems, a **producer** emits messages through a broker/topic/queue and a **consumer** receives them to execute business logic. Spring Cloud Contract specifies these interactions with **Groovy/YAML DSL**, generating producer tests and stubs for consumers to test via Stub Runner. However, **valid schemas do not guarantee valid delivery or business effects**.

For example, Payment Service emits:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "PaymentCaptured",
  "paymentId": "PAY-77",
  "orderId": "ORD-123",
  "aggregateVersion": 2,
  "amount": 120000,
  "currency": "VND"
}
~~~

A contract can verify the destination, headers, and JSON above. Yet such a test **does not prove**:

- That `OrderCreated`, `OrderPaid`, and `OrderShipped` are processed in order.
- That the broker will not redeliver `evt-1001` after a consumer crash.
- That the consumer will not deduct inventory or charge money twice upon receiving duplicates.
- That a Kafka transaction spans the database, email, or external HTTP services.
- That retries, dead-lettering, and recovery always behave properly under network faults or concurrent execution.

This lesson belongs to the **Message contracts** chapter of the `SPRING_CLOUD_CONTRACT` module. We examine the **limits of verifying ordering, redelivery, and exactly-once processing**, separate contract testing boundaries from integration testing, and design supplementary checks in CI.

### Objectives

After this lesson, you will:

1. Read a message contract and pinpoint what it actually verifies.
2. Distinguish business occurrence order, publish order, broker delivery order, and consumer completion order.
3. Recognize redelivery caused by lost acks/offset commits or retries.
4. Distinguish at-most-once, at-least-once, and exactly-once **effect**.
5. Design idempotent consumers using event IDs, unique constraints, and transactions.
6. Explain outbox/inbox patterns, Kafka transactions, DLTs, and their limits.
7. Build a test matrix covering schemas, ordering, duplicates, crashes, and release pipelines.

> **Principle:** A contract checks one observable interaction. **A sequence of interactions across time, retries, and crashes** is a different problem requiring dedicated tests.

## 2. What does Spring Cloud Contract Messaging verify?

Example Groovy message contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_captured')
    description('Producer emits event after capturing payment')
    label 'paymentCaptured'

    input {
        triggeredBy('publishCapturedPayment()')
    }

    outputMessage {
        sentTo('payments.captured')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'PaymentCaptured')
        }
        body(
            eventId: 'evt-1001',
            eventType: 'PaymentCaptured',
            paymentId: 'PAY-77',
            orderId: 'ORD-123',
            aggregateVersion: 2,
            amount: 120000,
            currency: 'VND'
        )
    }
}
~~~

Same intent in YAML DSL:

~~~yaml
name: payment_captured
description: Producer emits event after capturing payment
label: paymentCaptured
input:
  triggeredBy: publishCapturedPayment()
outputMessage:
  sentTo: payments.captured
  headers:
    contentType: application/json
    eventType: PaymentCaptured
  body:
    eventId: evt-1001
    eventType: PaymentCaptured
    paymentId: PAY-77
    orderId: ORD-123
    aggregateVersion: 2
    amount: 120000
    currency: VND
~~~

**DSL explanation:**

- `label` identifies/triggers the consumer-side message stub where supported.
- `input.triggeredBy` specifies the method the producer test calls to trigger the message; the base class/test context must provide that method.
- `outputMessage.sentTo` is the destination verified via the messaging integration.
- `outputMessage.headers` protects declared headers.
- `outputMessage.body` protects key payload fields and data types.
- `eventId` and `aggregateVersion` are **business fields**, not flags enabling exactly-once semantics in Spring Cloud Contract.

With a proper message verifier, the generated producer test calls the method, observes the message at the destination, and compares headers/body. You may need `@AutoConfigureMessageVerifier` and Spring Cloud Stream/Spring Integration/JMS or custom adapter configuration matching your application version.

A passing generated test **does not induce crashes**, **does not force broker redeliveries**, **does not verify offset commits**, and **does not prove database side effects are deduplicated**.

### 2.1. Do not infer guarantees from a schema field

Having `eventId` only allows consumers to **identify a logical event**; you still need code/DB constraints to deduplicate. Having `aggregateVersion: 2` lets consumers inspect a version; you still need routing, sequencing, and handling for missing/stale versions. Having `occurredAt` aids time tracing; it is not a global clock guaranteeing order.

### 2.2. Verification scope table

| Passing producer contract test | Can be concluded | Cannot yet be concluded |
| --- | --- | --- |
| Message sent to right destination | One matching output observed in test context | Every publish succeeds through a real broker |
| Payload matches JSON | Consumer has a compliant schema example | Every runtime event is valid |
| Header `eventType` matches | Sample event carries agreed metadata | Broker retry policy works |
| `eventId` matches format | Producer supplies an identifier | Duplicate delivery never occurs |
| `aggregateVersion` is a number | Data matches schema | Consumer enforces monotonic versions |
| Test observes expected message | Producer satisfies one interaction | No second unwanted message was emitted |
| CI build is green | Configured assertions ran and passed | Exactly-once business effect under faults |

## 3. Three separate areas of responsibility

| Area | Typical question | Primary testing |
| --- | --- | --- |
| **Message interface** | Do event type, body, headers, and destination match? | Spring Cloud Contract and Stub Runner |
| **Delivery** | How do ordering, acks, retries, redelivery, and dead-lettering work? | Broker integration tests, failure injection |
| **Business logic** | Does the consumer double-deduct inventory, miscalculate totals, or apply stale versions? | Unit/domain/transaction tests |

Tests can share sample data to reduce drift, yet **conclusions must stay within the proper layer**. For instance, a consumer handling two copies of an event without duplicating effects does not mean the broker's redelivery was tested. Conversely, a broker redelivering properly while a handler charges money twice is still a business bug.

## 4. Ordering has multiple meanings

“Messages in the right order” can refer to:

1. Order in which **business events** arise in the domain.
2. Order in which the producer submits publish calls.
3. Order in which the broker appends or enqueues them.
4. Order in which the consumer receives messages.
5. Order in which the consumer **commits side effects**.

These orders do not necessarily match:

~~~text
Producer:   E1(OrderCreated) → E2(OrderPaid) → E3(OrderShipped)
Broker:     E1 → E2 → E3
Consumers:  E1 started; E2 started; E2 finished; E1 finished; E3 finished
Effects:    E2 → E1 → E3
~~~

A standalone contract for `E2` cannot prove that `E1`'s effects must finish before `E2`.

### 4.1. Kafka only guarantees per-partition order

Kafka stores records by **topic-partition** with monotonically increasing offsets. Consumers read in offset order **within a partition**; there is no global order across partitions.

~~~text
orders.events
  partition-0: ORD-123/v1 → ORD-123/v2 → ORD-123/v3
  partition-1: ORD-456/v1 → ORD-456/v2
~~~

A common way to preserve per-order ordering is setting the Kafka record key = `orderId` and controlling partitioning. However:

- `orderId` in the JSON body **does not automatically become the Kafka key**.
- Concurrent producers, retries, and async publishing must be designed to preserve intended write order.
- Changing partition counts/partitioners can alter where new records for a key land.
- Retry topics, concurrent task execution, or async handlers can make **business completion order** diverge from offset order.
- Different orders on two partitions have no shared total order.

### 4.2. RabbitMQ: FIFO does not mean in-order completion

A queue can dispatch in enqueue order under specific conditions, yet multiple consumers, prefetch, requeues, nacks, and connection drops affect redelivery and processing.

~~~text
Queue: E1 → E2 → E3
Consumer A receives E1, processes slowly
Consumer B receives E2, commits before E1
Consumer A disconnects, E1 is redelivered
~~~

Therefore, “the queue is FIFO so consumers will process all effects in order” is **not unconditionally true**.

### 4.3. Sequence/version requires an explicit policy

~~~json
{
  "eventId": "evt-102",
  "aggregateId": "ORD-123",
  "aggregateVersion": 2,
  "eventType": "OrderPaid"
}
~~~

`aggregateVersion` can be checked by a contract, yet the consumer needs dedicated logic:

| Prior state | Received event | Example policy |
| --- | --- | --- |
| Applied v1 | v2 | Process and store lastAppliedVersion=2 |
| Applied v2 | v2 | Ignore duplicate |
| Applied v2 | v1 | Handle stale event per policy |
| Applied v1 | v3 | Detect v2 gap; buffer/retry/resync |

Do not assume every application must process all versions sequentially: some systems use latest-state snapshots, others require every transition. State the business commitment clearly before writing tests.

## 5. Redelivery: crash after commit, before ACK

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database
    B->>C: Deliver evt-102
    C->>D: Write business effect
    D-->>C: COMMIT succeeds
    Note over C: Crash before ACK / offset commit
    B->>C: Redeliver evt-102
    C->>D: Risk of duplicate effect
~~~

Situations that commonly cause redeliveries or duplicates:

- Consumer crashes or loses connection before acknowledging.
- Kafka offset uncommitted or transaction rolled back.
- Error handler retries after an exception.
- Producer republishes because a prior publish confirmation was lost.
- Outbox relay publishes successfully then crashes before recording published state.

**Publisher confirm**, **consumer ack**, and **database commit** are three distinct signals. RabbitMQ publisher confirms do not prove consumers processed the message; consumer acks do not make external transactions safe by themselves.

RabbitMQ provides a `redelivered` flag as a hint that a message was previously dispatched, yet a duplicate republished by the producer arrives as a fresh delivery. Hence **never replace event identity and deduplication with the `redelivered` flag**.

## 6. At-most-once, at-least-once, and exactly-once effects

| Model | Meaning | Risk or requirement |
| --- | --- | --- |
| **At-most-once** | Does not actively redeliver once considered received | Messages can be lost |
| **At-least-once** | Retries/redelivers unless processing is confirmed | Can deliver the same event multiple times |
| **Exactly-once effect** | One logical event causes at most one side effect within the stated boundary | Requires idempotency, transactions, deduplication |
| **Kafka EOS read-process-write** | Kafka outputs and consumed offsets can commit atomically | Does not cover databases/email/gateways outside Kafka |

“Received once”, “listener invoked once”, “event has one offset”, and “money charged only once” are **different guarantees**. Explicitly state the target entity, transaction boundary, retry/crash scenarios, and test evidence.

An at-least-once system can achieve **exactly one business effect** when consumers are properly idempotent. That does not turn it into a system with exactly-once delivery.

## 7. Idempotent consumers and atomic markers

Suppose Fulfillment Service must unlock shipping only once for `evt-1001`:

~~~text
evt-1001 1st time → unlock
evt-1001 2nd time → do not unlock again
evt-1001 3rd time → do not unlock again
~~~

Use a stable event identity across redeliveries of the same **logical event**. An illustrative PostgreSQL table:

~~~sql
CREATE TABLE processed_messages (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Concept of processing inside the **same database transaction**:

~~~sql
BEGIN;
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('fulfillment-service', 'evt-1001');

UPDATE orders
SET fulfillment_unlocked = TRUE
WHERE order_id = 'ORD-123';
COMMIT;
~~~

Upon a duplicate-key conflict, the application must **not run the UPDATE again**. This illustrates the mechanism, not a complete SQL handler. DB uniqueness and transactions stop two concurrent instances from processing duplicates simultaneously.

### 7.1. The check-then-act pitfall

~~~java
if (!processedMessages.existsById(event.eventId())) {
    fulfillment.apply(event);
    processedMessages.save(event.eventId());
}
~~~

Two threads can both see `exists = false` before either saves, then both apply the effect. Checking existence in application code alone is **not atomic**.

Intentional pseudocode:

~~~java
// PSEUDOCODE: tryInsert is a custom project API
@Transactional
public void handle(PaymentCaptured event) {
    boolean firstTime =
        processedMessages.tryInsert("fulfillment-service", event.eventId());
    if (!firstTime) {
        return;
    }
    fulfillmentRepository.unlock(event.orderId());
}
~~~

`tryInsert` is not a built-in Spring Cloud Contract or Spring Data API. Real implementations must rely on proper unique constraints and transactions.

### 7.2. Transaction boundaries must be stated explicitly

If the effect only updates the same database, it can be made atomic with the processed marker. If the effect **sends an email, calls a payment gateway, or invokes an HTTP service**, a database transaction cannot roll back external side effects. You need idempotency keys at the receiving service, a transactional outbox, or compensation/reconciliation.

**Deduplication keys may be** `eventId`, `(eventType, aggregateId, aggregateVersion)`, or `paymentId + effectType` depending on business rules. Using `orderId` alone could mistakenly block other valid events in an order's lifecycle.


## 8. Transactional outbox does not eliminate duplicates on its own

A producer often needs to update a database and emit an event. Both naive sequences have failure windows:

~~~text
COMMIT payment = CAPTURED
→ Crash before publish
→ Consumer does not know payment changed

Publish PaymentCaptured
→ Database rollback
→ Consumer receives event for uncommitted state
~~~

**Transactional outbox** writes the business change and an outbox record inside the **same database transaction**; post-commit, a relay reads the record and publishes to the broker.

~~~mermaid
flowchart LR
    A["Business action"] --> B["DB transaction"]
    B --> C["Update payment"]
    B --> D["Insert outbox"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Outbox relay"]
    F --> G["Broker"]
    G --> H["Idempotent consumer"]
~~~

An outbox **does not inherently guarantee zero duplicate publishes**: the relay can publish successfully and crash before marking the event as sent, publishing again after restart. Therefore, the consumer side still needs duplicate handling.

### 8.1. Inbox / processed-message ledger

A complementary pattern records `(consumerName, eventId)` in a processed-messages or inbox table inside the **same transaction** as the business effect. If the event was already processed, do not apply the effect again.

Define retention windows for processed IDs. If brokers or operations allow replaying events from months ago, purging the deduplication table after a few days can cause duplicate processing.

### 8.2. Identifiers with distinct roles

| Field | Meaning |
| --- | --- |
| `eventId` | Stable identity of a logical event, used for deduplication |
| `aggregateId` | Affected domain entity/aggregate |
| `aggregateVersion` | Version or sequence within the aggregate |
| `correlationId` | Links logs/traces across multiple interactions |
| `causationId` | Event/command that caused the current event, if published in schema |

These are **schema conventions**, not fields Spring Cloud Contract injects automatically. Contracts check presence/format; the application must enforce operational semantics.

## 9. Kafka exactly-once has boundary limits

Spring Kafka supports transactions for **read → process → write Kafka** flows. When listener containers, transaction managers, Kafka outputs, and consumed offsets are properly configured, output records and offsets commit atomically within a Kafka transaction.

Spring Kafka documentation also notes that **read/process may execute more than once**, while the Kafka read-process-write output is transactionally protected. Distinguish how many times a listener is invoked from how Kafka outputs appear to consumers configured with the right isolation level.

| Flow | Is Kafka EOS enough by itself? | Why |
| --- | --- | --- |
| Kafka input → Kafka output + consumed offsets | Possible when configured properly | Same Kafka transaction |
| Kafka input → PostgreSQL update | Not by default | Database has its own transaction |
| Kafka input → send email | No | SMTP does not roll back with Kafka |
| Kafka input → call payment gateway | No | Gateway has external side effects |
| Kafka input → call HTTP service | Not by default | Timeouts/retries require target-side idempotency |

For side effects outside Kafka, use idempotency keys, outbox/inbox patterns, or reconciliation. **A generated message contract test never proves a distributed transaction.**

EOS mode APIs, broker versions, and transaction behavior vary across Spring Kafka/client versions; verify against your exact dependencies when configuring production systems.

## 10. Retries, backoff, DLQ/DLT, and poison messages

Consumers can face **transient** errors like DB blips, **permanent** errors like unparseable schemas, or unclassified errors. Error-handling policies must specify:

- Which errors are retried and which are rejected immediately?
- Maximum retry attempts and backoff intervals?
- Is `eventId` preserved across retries and replays?
- Which DLT/DLQ receives unprocessable events?
- Who monitors, fixes, and replays those events?
- Can retry topics let newer events overtake older events for the same aggregate?
- Are metrics and traces tagged with event ID, attempt count, and consumer instance?

Spring Kafka provides `DefaultErrorHandler`, `BackOff`, and `DeadLetterPublishingRecoverer`; RabbitMQ provides ack/nack, requeue, and dead-lettering. These mechanisms belong to **runtime/integration tests**, and cannot be inferred from an `outputMessage`.

### 10.1. Non-blocking retries can invert business order

~~~text
Main topic: E1(v1) then E2(v2)
E1 fails → moved to retry topic
E2 on main topic succeeds
After delay, E1 is retried
Business completion: E2 before E1
~~~

When strict version processing is required, use gap detection, buffering, or per-key blocking instead of relying on original publish order.

### 10.2. Dead-lettering does not mean business success

Routing a message to a DLT means the pipeline **failed to complete business processing along the normal path**. Set up alerts, replay runbooks, retry-count monitoring, and deduplication on replay.

If a consumer reads error events from a DLT, you can write a message contract for the **error event schema**; however, retry counts and DLT transition timing must be verified with real broker tests.

## 11. Testing ordering with a message sequence, not one event

Example order events:

~~~json
{"eventId":"evt-1","aggregateId":"ORD-123","aggregateVersion":1,"eventType":"OrderCreated"}
~~~

~~~json
{"eventId":"evt-2","aggregateId":"ORD-123","aggregateVersion":2,"eventType":"OrderPaid"}
~~~

~~~json
{"eventId":"evt-3","aggregateId":"ORD-123","aggregateVersion":3,"eventType":"OrderShipped"}
~~~

A **broker integration test** should:

1. Start a broker/testcontainer and consumer in an isolated environment.
2. Publish events with the same key `ORD-123` in order.
3. Wait for final state `SHIPPED` and `lastAppliedVersion = 3` within a bounded timeout.
4. If business rules require all three steps, inspect audit/domain records rather than only the final status.
5. Intentionally send `v1 → v3 → v2` to test gap/out-of-order policies.
6. Exercise consumer concurrency, redelivery, and retry policies close to production.

Pseudocode:

~~~java
// PSEUDOCODE: publish and awaitCondition are custom test helpers
publish(orderCreated("ORD-123", 1));
publish(orderPaid("ORD-123", 2));
publish(orderShipped("ORD-123", 3));

awaitCondition(Duration.ofSeconds(10), () ->
    orderProjection.find("ORD-123").status().equals("SHIPPED")
);

assertThat(orderProjection.find("ORD-123").lastAppliedVersion())
    .isEqualTo(3);
~~~

`publish`, `awaitCondition`, and `orderProjection.find` in this example **are not Spring Cloud Contract APIs**.

### 11.1. Never wait with guessed sleeps

~~~java
publish(orderShipped("ORD-123", 3));
Thread.sleep(2000);
assertThat(orderProjection.find("ORD-123").status())
    .isEqualTo("SHIPPED");
~~~

This test flakes easily when CI has a backlog. Wait on an **observable condition** with a bounded timeout and diagnostic logging on timeout, e.g., using Awaitility or an equivalent helper.

### 11.2. What to collect when an ordering test fails

- Topic/partition/offset or queue/delivery tag.
- `eventId`, `aggregateId`, `aggregateVersion`, message key.
- Timestamps of publish, broker accept, consumer receive, and DB commit.
- Consumer concurrency, prefetch, error handler, and transaction mode.
- Any duplicate or missing version?

This evidence separates producer out-of-order publishing from broker redelivery and concurrent consumer execution.

## 12. Testing redelivery and duplicates at two levels

### 12.1. Unit/domain test: same event twice

~~~java
// PSEUDOCODE: the methods below are application helpers
PaymentCaptured event =
    samplePaymentCaptured("evt-1001", "ORD-123");

handler.handle(event);
handler.handle(event);

assertThat(fulfillmentRepository.countUnlockActions("ORD-123"))
    .isEqualTo(1);
~~~

This test guards idempotent business effects in a test harness. It **does not prove** the broker will redeliver properly after a lost ack.

### 12.2. Concurrent duplicate test

Two consumers receive the same `eventId` simultaneously. Tests should verify:

- Unique constraints stop two transactions from both recording the marker and applying the effect.
- The losing transaction handles the duplicate safely.
- No external side effects run outside the DB before processing is authorized.
- No infinite retries or deadlocks occur.

Calling a handler twice sequentially is **insufficient** when production runs multiple consumer instances.

### 12.3. Broker test with failure injection

~~~text
Given:
  Consumer receives evt-1001
  Business transaction commits successfully

When:
  Consumer stops before ack/offset commit
  Broker detects client failure
  Consumer restarts

Then:
  Event is redelivered per policy
  No second business effect occurs
  Duplicate is safely acked/committed
~~~

Inject the fault **right after commit and before ack**. Simply publishing the same message twice tests duplicate handling, not broker redelivery after a crash.

### 12.4. Ack/offset commits should align with published processing milestones

- Acking too early risks losing work on crashes.
- Acking too late or failing to ack causes redeliveries.
- Consumers must be safe when events are reprocessed.
- Kafka transactional read-process-write has its own offset/output transaction mechanics.
- RabbitMQ manual acks should follow a defined completion-milestone policy.

There is no single universal ack order across all messaging integrations.

## 13. At what level does Stub Runner test consumers?

Spring Cloud Contract can create messaging stubs with label `paymentCaptured`. With an appropriate integration, consumer tests trigger the sample event and verify the application handles the message per schema.

**Consumer stub tests can verify:**

- The listener decodes JSON, headers, and metadata.
- The consumer does not depend on fields not declared in the contract.
- The business handler processes a sample event.
- Consumer idempotency within the test context, if explicitly triggered twice with the same event ID and side effects are asserted.

**They do not prove by themselves:**

- That Kafka/RabbitMQ preserves ordering per production configuration.
- That ack/nack, rebalances, or retries work properly under network faults.
- That an outbox relay never drops events during crashes.
- That external payment/email side effects never duplicate.
- That the system is end-to-end exactly-once.

**Conclusion:** Generated producer messaging tests, Stub Runner consumer tests, broker integration tests, and failure injection are **complementary layers**, not substitutes for one another.


## 14. End-to-end design: tracking every communication boundary

Consider Payment Service and Fulfillment Service. Illustrative architecture:

~~~mermaid
flowchart TD
    P["Payment Service"] --> O["Payment DB + Outbox"]
    O --> R["Outbox relay"]
    R --> K["Kafka / RabbitMQ"]
    K --> C["Fulfillment Consumer"]
    C --> I["Inbox / unique eventId"]
    I --> D["Update fulfillment in DB transaction"]
    D --> A["Ack / offset commit per policy"]
    C --> X["DLT if unprocessable"]
~~~

This diagram is a **reference design model**, not infrastructure provided automatically by Spring Cloud Contract.

### 14.1. Invariants to protect

| Invariant | Owner | Verification |
| --- | --- | --- |
| `PaymentCaptured` has right body/headers and types | Producer | Spring Cloud Contract messaging producer test |
| Message published to declared destination | Producer adapter | Generated contract test with message verifier |
| Payment status and outbox event commit together | Producer persistence | Outbox transaction integration test |
| Relay retries when publish fails | Relay/broker integration | Relay integration/failure test |
| Events for same aggregate use right message key | Producer broker adapter | Kafka/RabbitMQ integration test |
| Consumer understands event schema | Consumer | Stub Runner consumer contract test |
| Duplicate event does not unlock shipping twice | Consumer domain/DB | Idempotency transaction + concurrency test |
| Stale-version event does not regress state | Consumer domain | Out-of-order sequence test |
| Crash before ack does not repeat business effect | Consumer + broker | Failure injection + restart test |
| Poison event goes to DLT per policy | Consumer infrastructure | Retry/DLT integration test |
| CI blocks producer failing contract | Release pipeline | Producer verification and publish gate |

### 14.2. Writing specific enough exactly-once requirements

Vague statement:

> Every message in the system is always processed exactly once.

A more testable requirement:

> For the same `eventId` of `PaymentCaptured`, unlocking fulfillment for `orderId` commits at most once in PostgreSQL; the processed-event record and fulfillment update share a single transaction. If the message is redelivered, the consumer does not execute the side effect again.

The second statement specifies **logical event identity**, **business effect**, **database boundary**, and **redelivery condition**. It still does not cover sending emails or calling payment gateways unless those side effects are explicitly included in the design.

## 15. A responsible test matrix

A practical suite should split by layer:

| Layer | Scenario | Assertions |
| --- | --- | --- |
| Contract producer | Emit sample `PaymentCaptured` | Destination, eventType, schema, headers |
| Contract consumer | Stub triggers sample event | Deserialization, data-handling branches |
| Domain unit | Same `eventId` handled twice | Effect applied only once |
| DB integration | Two concurrent handlers receive duplicate | Unique constraint and safe transaction |
| Kafka ordering | Events v1–v3 sharing key | Partition/offset and consumer projection match |
| Rabbit delivery | Lost ack/connection | Redelivery follows policy |
| Crash injection | Crash after DB commit, before ack | No second side effect |
| Outbox integration | Relay crashes after publish | May republish; downstream stays idempotent |
| Retry policy | Transient/permanent errors | Correct attempts, backoff, DLT |
| Replay | Replay older events | No duplicate side effects |
| Release gate | Producer contract fails | Failing stubs/artifacts are not published |

### 15.1. Reliability of asynchronous tests

Broker tests must observe real conditions rather than sleeping arbitrarily:

- Use bounded timeouts and clear error messages.
- Use distinct `eventId`/`correlationId` values per scenario.
- Isolate topics, queues, consumer groups, schemas, or DBs where possible.
- Never let data from prior tests cause false passes.
- When ordering matters, test with production-like concurrency/prefetch.
- Never count listener invocations to infer how many times a business effect occurred.
- Inspect both database state and message offsets/positions when fault tests fail.

Pseudocode checking post-processing state:

~~~java
// PSEUDOCODE: not a Spring Cloud Contract API
publish(paymentCaptured("evt-1001", "ORD-123"));
publish(paymentCaptured("evt-1001", "ORD-123"));

awaitCondition(Duration.ofSeconds(10), () ->
    fulfillmentRepository.find("ORD-123").isUnlocked()
);

assertThat(fulfillmentRepository.countUnlockActions("ORD-123"))
    .isEqualTo(1);
~~~

For **concurrent duplicates**, have two consumers process concurrently with proper synchronization barriers and DB constraints, rather than publishing twice sequentially and assuming all races are covered.

## 16. How does CI protect contracts and reliability?

A producer with the Spring Cloud Contract plugin configured can run:

~~~bash
./mvnw -B clean verify
~~~

or Gradle:

~~~bash
./gradlew clean build
~~~

Commands are meaningful only if generated tests are genuinely **generated, compiled, and executed** with the matching message verifier/binder. A `BUILD SUCCESS` with zero messaging contract tests executed **is not proof that contracts were verified**.

### 16.1. Suggested tiered pipeline

~~~text
Pull request:
  - Compile, unit/domain tests
  - Generated producer contract tests
  - Consumer tests with compatible stubs
  - Database idempotency/transaction tests

Integration pipeline:
  - Kafka/RabbitMQ ordering, retries, DLT
  - Concurrent duplicates, redelivery, crash injection
  - Outbox relay recovery

Pre-release:
  - Verify stubs artifact/version
  - Check consumer backward compatibility
  - Check metrics, alerts, replay runbooks
  - Release only producer/stubs that passed required gates
~~~

Not every heavy test must run on every commit when resources are constrained. However, **reliability claims must rest on tests that actually ran on a managed cadence**. Never cite contract test results to claim a failure-injection scenario was tested when it has never been executed.

### 16.2. Code review checklist for message changes

1. Did destination, headers, fields, or data types read by consumers change?
2. Does `eventId` stay stable across retries of the same logical event?
3. Were consumer groups added or concurrency settings changed?
4. Did message keys/partitioners, partition counts, or routing change?
5. Can retries/DLTs alter per-key ordering?
6. Are business effects protected by idempotency/transactions?
7. Are there side effects outside the DB needing idempotency keys?
8. If the outbox relay crashes before/after publishing, how can data be lost or duplicated?
9. Were tests added proving the new properties at the right boundaries?

## 17. Common misconceptions

| Claim | Why it is insufficient | How to fix the mental model or test |
| --- | --- | --- |
| “Contract has `eventId`, so duplicates can't happen” | Field has no automatic deduplication effect | Design unique constraints/idempotent handlers |
| “Kafka guarantees order across the whole topic” | Ordering is per-partition, not global across partitions | Choose keys and test per-aggregate order |
| “Queue is FIFO, so effects commit FIFO” | Concurrency, prefetch, requeues change completion order | Broker/consumer integration tests |
| “Publisher confirm proves the consumer processed it” | Publisher confirm and consumer ack are independent | Observe separate signals |
| “Acked means the business effect definitely committed” | Ack may not be tied to external transactions | Design ack boundaries + idempotency |
| “Kafka EOS covers PostgreSQL and email” | Kafka transactions do not span external systems | DB idempotency/outbox or coordination |
| “Sending an event twice tests broker redelivery” | That mainly tests duplicate handling | Test crash/lost ack with a real broker |
| “Moved to DLT means processing succeeded” | DLT signals normal processing failed | Monitoring, alerts, replays |
| “Timestamps determine version order” | Clock skew, retries, and delays make order unstable | Use domain-issued versions/sequences |
| “Check-exists then update is enough” | Two instances can both read false | Unique constraints and transactions |
| “Outbox eliminates duplicates” | Relay can republish on crash | Idempotent consumers |
| “Stub Runner green means the broker is reliable” | Stubs do not simulate delivery faults | Broker integration/fault tests |

### 17.1. Investigating a double-applied effect

When an order's inventory is deducted twice:

1. Did both executions have the **same `eventId`**?
2. Did the producer emit two logical events, or did a relay/broker redeliver one?
3. Was there a crash, rebalance, timeout, or nack/requeue?
4. Did the handler record processed-event before or after the effect? Inside the same transaction?
5. Did two consumer instances run concurrently and both pass an `exists` check?
6. Did an external API create duplicate effects due to a missing idempotency key?
7. Do logs include `eventId`, `aggregateId`, attempt, partition/offset, and transaction outcome?

Never loosen a contract to permissive matchers just to let runtime duplicates slip by. Contract schemas and business idempotency are **two separate problems**.

## 18. Practice exercise: PaymentCaptured and Fulfillment Service

Suppose Payment Service emits an event when transaction `PAY-900` for order `ORD-900` is captured:

~~~json
{
  "eventId": "evt-pay-900",
  "eventType": "PaymentCaptured",
  "paymentId": "PAY-900",
  "orderId": "ORD-900",
  "aggregateVersion": 2,
  "amount": 450000,
  "currency": "VND"
}
~~~

Consumer Fulfillment Service must unlock shipping **once** and never let older events regress state.

### 18.1. Task A — Write the producer contract

Write a Groovy messaging contract containing:

- `label: paymentCaptured`.
- `input.triggeredBy` as the trigger provided by the test context.
- `outputMessage.sentTo` as `payments.captured`.
- Header `eventType: PaymentCaptured`.
- Body with properly typed `eventId`, `paymentId`, `orderId`, `aggregateVersion`, `amount`, and `currency`.

Hint:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_captured_for_fulfillment')
    label 'paymentCaptured'

    input {
        triggeredBy('publishCapturedPayment()')
    }

    outputMessage {
        sentTo('payments.captured')
        headers {
            header('eventType', 'PaymentCaptured')
        }
        body(
            eventId: 'evt-pay-900',
            eventType: 'PaymentCaptured',
            paymentId: 'PAY-900',
            orderId: 'ORD-900',
            aggregateVersion: 2,
            amount: 450000,
            currency: 'VND'
        )
    }
}
~~~

**Explanation:** The contract protects destination, payload, and headers for one concrete event. It does not yet test redelivery, outbox, ordering, or external effects.

### 18.2. Task B — Idempotency

Send event `evt-pay-900` to the consumer **twice**. Verify:

- Fulfillment applies only one business change.
- The processed-messages table records the event exactly once.
- The duplicate does not throw exceptions triggering infinite retries.
- Run two instances handling the same event concurrently to test uniqueness.

Question: If the broker delivers twice yet the effect occurs once, is that exactly-once **delivery**?

**Hint:** No. It is at-least-once delivery combined with an exactly-once **effect within the tested boundary**.

### 18.3. Task C — Ordering

Send events with versions `1`, `2`, `3` for `ORD-900`, then intentionally send `1`, `3`, `2`. Clearly define whether the application will:

- Buffer v3 and wait for v2?
- Retry v3?
- Apply only the latest snapshot and skip v2?
- Error and route to DLT when a gap cannot be resolved?

There is no single right answer for every domain. What matters is that **the rule is written down explicitly and proven by tests**, not left to scheduler luck.

### 18.4. Task D — Crash after commit, before ack

Use a broker testcontainer or isolated integration environment. Let the consumer commit the business effect, then stop it before ack/offset commit. Restart and verify:

1. The broker redelivers the message per configuration.
2. The processed event ID prevents duplicate effects.
3. The consumer safely acks/commits the duplicate.
4. Logs/metrics provide full event traceability.

Do not substitute calling a handler twice in memory and claim you tested a real crash.

### 18.5. Task E — Write bounded conclusions

Write three sentences yourself:

- “Our contract tests protect ___”.
- “Our broker integration tests protect ___”.
- “Our idempotency + transaction tests protect ___”.

If something has not been tested, write “unverified” rather than claiming it is guaranteed.

## 19. Checklist before claiming a messaging system is safe

- [ ] Contracts specify the destination, headers, body, and schema version consumers need.
- [ ] Generated producer messaging tests are genuinely generated and executed.
- [ ] Message verifier, triggers, and test context are properly configured.
- [ ] Ordering, redelivery, and exactly-once guarantees are never inferred from a message contract.
- [ ] Ordering is defined per aggregate key, partition/queue, or concrete scope.
- [ ] Message keys, partitioning, and consumer concurrency match requirements.
- [ ] `eventId` stays stable across all redeliveries of the same logical event.
- [ ] Consumers enforce unique constraints and transactions covering processed-event + business effects.
- [ ] Concurrent duplicates are tested, not only sequential duplicates.
- [ ] Side effects outside the database have idempotency or compensation.
- [ ] Producer outbox/relay is tested for crashes before and after publishing.
- [ ] Broker redelivery, ack/offset commits, retries/backoff, and DLTs have been verified.
- [ ] Ordering tests include out-of-order and missing-version scenarios.
- [ ] Tests use bounded timeouts and isolated resources; avoid `Thread.sleep`.
- [ ] Consumer Stub Runner tests verify schema handling without assuming broker guarantees.
- [ ] CI blocks publishing artifacts when producer verification fails.
- [ ] Metrics, alerts, and replay runbooks are ready for operations.

## 20. References

- [Spring Cloud Contract — Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): `triggeredBy`, `outputMessage`, `sentTo`, labels, and message verifiers.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): boundaries of read-process-write Kafka transactions and consumed offsets.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): partition ordering, partition keys, consumer groups, and reliability.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): publisher confirms, ack/nack, requeue, and redelivery.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): guidance on building systems resilient to redelivery.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): error handlers, backoff, and dead-lettering.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox): consistency between DB commits and publishing, plus relay duplicate risks.

**Key takeaway:** Spring Cloud Contract helps verify that **messages are described accurately**, without guaranteeing on its own that **every message arrives in order, is delivered only once, or causes a single business effect**. Define explicit boundaries by aggregate, event ID, and transaction scope; combine idempotent consumers, outbox/inbox patterns, broker integration tests, and fault injection. Reliable CI must verify both **data interfaces** and **behavior under retries, duplicates, and crashes**.

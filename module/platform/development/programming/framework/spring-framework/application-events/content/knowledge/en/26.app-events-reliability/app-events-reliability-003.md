# At-Least-Once and Internal Events in Spring Framework Application Events

## 1. Key Question: Does publishEvent Guarantee At-Least-Once?

**No.** `ApplicationEventPublisher.publishEvent(...)` is a mechanism for publishing events **within a Spring ApplicationContext**, not a durable queue. Spring Application Events itself **does not guarantee at-least-once delivery**, does not persist events across restarts, and does not automatically retry until every listener succeeds.

Within the **Reliability** group, the lesson **At-Least-Once and Internal Events** focuses on distinguishing three things that are easily confused:

1. **In-memory notification dispatch:** Spring selects listeners and dispatches events in-process.
2. **Re-running a call after failure:** retries can cause the **same logical event** to be processed multiple times.
3. **Providing an at-least-once delivery guarantee:** requires durable storage, state tracking, retries, and outcome confirmation; not merely adding an annotation or calling `publishEvent`.

For example, `OrderPlaced(eventId=EVT-42)` is created after placing an order. If a listener writes an audit record and the process dies before recording it as "processed", a retrying worker can re-run that event. **At-least-once permits duplicates**: the same event ID can reach a consumer two or more times, and the consumer must handle that.

A desirable model:

```text
Place order in transaction
      |
      +--> COMMIT Orders + Outbox record (durable)
                              |
                              v
                       Dispatcher/Worker
                              |
                       send / retry event
                              |
                      Consumer/Handler
                              |
                  idempotent processing by eventId
                              |
                    record outcome / confirm
```

The crucial step is defining **what is being guaranteed**: event arrival at the broker, event arrival at a specific consumer, or business side-effect success? These milestones are not synonymous.

### What You Will Learn

- The meaning of at-most-once, at-least-once, and exactly-once per boundary.
- Where synchronous Spring listeners, asynchronous multicasters, and `@TransactionalEventListener` can lose events.
- Why retries create duplicates, especially in the gap between **side effect** and **acknowledgment**.
- Designing event IDs, idempotency, inboxes, outboxes, and processing states.
- A Java 17+ illustration with Spring Context: replaying an event while applying the business effect only once.
- Distinguishing an in-memory simulation from an implementation with durable guarantees.
- Testing crash windows, retries, transactions, and monitoring stuck events.

## 2. Three Delivery Semantics

| Semantics | What the system tries to guarantee | Main risk | When is it appropriate? |
| --- | --- | --- | --- |
| **At-most-once** | A message is delivered at most once across the chosen boundary | Can be lost | Telemetry/best-effort if loss is acceptable |
| **At-least-once** | Message delivery is retried until acknowledged per policy | Can be delivered **multiple times** | Workflows needing retries that can be made idempotent |
| **Exactly-once** | An outcome is applied strictly once within a defined scope | Hard to guarantee end-to-end across multiple resources | Mechanisms with tight transactions/deduplication and narrow scope |

**At-least-once does not mean "running the listener once is enough".** It describes the **retry/ack policy** of a delivery mechanism, not a single callback count across the entire event lifecycle.

A system may guarantee the broker receives an event at least once, yet **not guarantee an external consumer executed the side effect**. Or a consumer may read an event multiple times while using a unique constraint so the business effect applies only once. Always state the boundary name and operating conditions explicitly.

### Conditions to Claim At-Least-Once

An architecture typically requires:
- **Durable message source:** outbox DB, durable queue/topic, or equivalent mechanism.
- **Stable event identity:** the same logical event preserves its `eventId` across retries.
- **Acknowledgment (ack) rules:** treat an attempt as successful only at a defined milestone.
- **Policy-based retries:** transient errors are retried with backoff and long-term failure handling.
- **Duplicate-tolerant consumers:** idempotent or transactional deduplication.
- **Real operations:** backlog visibility, alerts, retention, DLQ/quarantine, and outage recovery.

If you cap retry attempts and move events to a dead-letter queue, state the commitment accurately: events are **not silently lost**, yet **not every event is automatically processed to success**. Prolonged infrastructure outages, expired retention, or unfinished manual remediation still affect outcomes.

## 3. What Does Spring Application Events Do by Default?

### 3.1. Synchronous Multicast

With the default `SimpleApplicationEventMulticaster`, listeners normally run on the **publisher's thread**:

```text
OrderService.placeOrder()
   |
   +--> publishEvent(OrderPlaced)
              |
              +--> Listener A
              +--> Listener B
              +--> Listener C
   |
   +--> publishEvent returns (if no error propagates)
```

If listener B throws an exception and there is no custom `ErrorHandler` to suppress it, the exception can propagate to the publisher and remaining dispatches may stop. Spring **does not automatically create a durable retry record** to ensure B/C will be retried after a restart.

If an application service catches the exception and calls `publishEvent(event)` again, listener A **may have already succeeded the first time** and will be invoked again. This is a source of duplicates caused by retrying the whole multicast, not necessarily by Spring retrying on its own.

**Critical trap:** `publishEvent` completing without error only proves callbacks were dispatched under current semantics; it does **not** prove an email reached the recipient or a listener's transaction committed. A listener might simply enqueue another task and return.

### 3.2. Async Multicaster

When `SimpleApplicationEventMulticaster.setTaskExecutor(...)` is configured, async-capable listeners can be submitted to an executor:

```text
Publisher thread: publishEvent -> submit task -> return
                                        |
                                        v
                                Worker processes later
                                        |
                              success / exception / crash
```

`publishEvent` can return **before the worker starts**. If the process dies while the event is sitting in a **RAM** queue, unexecuted work can be lost. Without a durable broker/outbox, this is strictly **best-effort dispatch**.

If a handler throws an exception on a worker, the error normally does not return to the publishing thread. You need dedicated error handling for the executor, metrics, retries, and durable storage if event loss is unacceptable.

### 3.3. `@Async @EventListener`

`@Async` runs through a Spring async proxy and an executor configured via `@EnableAsync` or `@Async("executorName")`. It changes **thread execution**, without creating a new delivery guarantee. For async `void` methods, exceptions must be observed via `AsyncUncaughtExceptionHandler` or an equivalent mechanism. An `assertThrows` around `publishEvent` does not properly test failures inside the worker.

**In summary:** sync/async is an **execution mode** choice; at-least-once is a **message persistence, retry, and ack** choice. Do not conflate the two decisions.

## 4. Four Distinct Moments to Track

An event typically passes through multiple steps:

```text
Domain fact accepted
   |
   v
Database COMMIT
   |
   v
Event dispatched / queued
   |
   v
Listener/consumer receives event
   |
   v
Side effect committed / external API confirmed
   |
   v
Delivery record ACKed / marked SENT
```

Different milestones create different risk points:

1. **Before DB commit:** if an event is published and a consumer performs an off-DB side effect, and the source transaction later rolls back, the side effect may be impossible to roll back.
2. **After DB commit, before dispatch:** a process crash leaves the business fact persisted while the in-memory event never reaches the consumer.
3. **After dispatch, before side effect:** worker crash or downstream timeout; you need to know whether to retry.
4. **After side effect, before ACK:** the side effect succeeded, yet the sender does not know; retrying causes the event to be reprocessed. This is the **classic point where duplicates arise**.
5. **After ACK, before completion in another system:** a local ACK may only confirm enqueuing, not that the external consumer finished processing.

Therefore, reliability cannot be solved just by "moving the listener to `AFTER_COMMIT`". Solutions must align with the **failure windows** and the required type of side effect.

## 5. Transaction-Bound Events: What AFTER_COMMIT Helps With and What It Does Not

Example listener:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    notificationService.send(event.orderId());
}
```

This is an **integration snippet**, requiring a Spring bean, transaction manager, event type, and corresponding imports.

`@TransactionalEventListener` defaults to `AFTER_COMMIT`. When a publisher emits an event inside an active transaction, the listener binds to transaction synchronization and runs in the configured phase. If there is no active transaction, by default the listener **is not invoked** (`fallbackExecution=false`), unless the application explicitly enables fallback.

Advantage: reduces the risk of executing side effects for a transaction that rolls back before commit.

However, remember these limitations:

- If the JVM/process stops **right after commit** before the callback runs, the event can be **lost**; Spring has no default durable callback registry.
- If an `AFTER_COMMIT` callback throws an exception, the source transaction has already committed; you cannot "roll back" the business fact retroactively.
- If the callback interacts with the DB, old transaction resources may still be bound during a cleanup phase; new writes need their own proper transaction, such as a bean method with `Propagation.REQUIRES_NEW`.
- `AFTER_COMMIT` does not mean asynchronous; the body can run on the thread completing the transaction.
- With Spring 6.1 and reactive transactions, the transaction context lives in the Reactor Context; events must carry `TransactionContext` as their source (typically via `TransactionalEventPublisher`) for transactional event listeners to receive the right context. This **does not** create a durable delivery guarantee.

**Conclusion:** `AFTER_COMMIT` helps choose **execution timing**, not an at-least-once mechanism.

## 6. Designing Internal Events with Clear Identity

A proper event should carry a stable ID:

```java
public record OrderPlaced(
    String eventId,
    String orderId,
    String correlationId,
    long totalCents
) {}
```

In this example:
- `eventId` identifies **one occurrence** of a logical event and does not change when retrying that same event.
- `orderId` identifies the aggregate; one order can emit many distinct events.
- `correlationId` links multiple steps in the same workflow for log tracing; it does **not** replace the event ID used for deduplication.
- `totalCents` is a snapshot of business value at the moment the event occurred.

Do not put JPA managed entities or mutable collections directly into a payload that needs retry/replay. Once the transaction closes or the process restarts, the old entity is no longer a reliable snapshot. Records with primitives/immutable value objects are more suitable.

**Do not generate `UUID.randomUUID()` every time a worker retries.** The ID should be assigned when the logical event is created and persisted in the outbox, then passed intact across every attempt. With multiple independent consumers, the deduplication key is usually the pair **`consumerName + eventId`**, not just a global event ID; each consumer is entitled to process the same event once for its own responsibility.

## 7. Why Do Retries Produce Duplicates?

Suppose a worker has outbox event `EVT-42` and sends it to a consumer:

```text
Attempt #1:
   Worker sends EVT-42
   Consumer processes and writes projection successfully
   Worker is interrupted before writing ACK/SENT
   => outbox still believes sending is incomplete

Attempt #2:
   Worker reads EVT-42 again
   Consumer receives the same EVT-42 again
   => duplicate delivery
```

From the sender's perspective, attempt #1 was never confirmed. From the consumer's perspective, the business effect may already be committed. Without a single shared transaction spanning databases on both ends and the broker, the sender **cannot deduce** whether the event was processed solely from a timeout or lost ACK.

Distinguish between:
- **Duplicate delivery:** the same event is sent/received multiple times.
- **Duplicate attempt:** the same handler may be invoked multiple times.
- **Duplicate business effect:** the same business action is unintentionally applied multiple times.

At-least-once **permits the first two**, but must be designed to **prevent the third**.

### Repeating an Event Is Not Always an Error

If `OrderPlaced(EVT-42)` is redelivered, an idempotent listener can skip the second time. However, if the order later emits `OrderAddressChanged(EVT-43)`, that is a different event and must be processed even though `orderId` is identical. Deduplicating by `orderId` alone would wrongly drop a valid event.

## 8. Runnable Java 17+ Example: Simulating Duplicates and an Idempotent Listener

This example uses **Spring Context 6.1.21**, without Spring Boot, a message broker, or a database. It simulates:

1. Storing an event in an **in-memory outbox** (not durable).
2. A worker publishing the event to a synchronous `@EventListener`.
3. Simulating a worker failure **after the listener processed it but before marking SENT**.
4. The worker retrying the **exact same event ID**.
5. The listener checking `eventId` in a `processedIds` set and incrementing the business effect only once.

**Mandatory limitation to understand:** the program does not intentionally crash the JVM, instead throwing an exception to simulate a failure window. Both the outbox and processed IDs live in RAM, so **the demo does not actually provide at-least-once across restarts**. For production guarantees, replace them with a DB/broker and transactional deduplication as in sections 9–11.

### 8.1. Structure

```text
internal-event-retry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/InternalEventRetryDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'internal-event-retry-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.InternalEventRetryDemo'
}
```

### 8.2. Complete Java File

`src/main/java/demo/InternalEventRetryDemo.java`:

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class InternalEventRetryDemo {

    public record OrderPlaced(String eventId, String orderId) {}

    // Simulates a durable outbox, though in practice it only stores in RAM.
    public static final class InMemoryOutbox {
        private OrderPlaced pending;
        private boolean sent;
        private int attempts;

        public void add(OrderPlaced event) {
            if (pending != null) {
                throw new IllegalStateException("One event only in demo");
            }
            pending = event;
        }

        public OrderPlaced nextPending() {
            return sent ? null : pending;
        }

        public void incrementAttempts() {
            attempts++;
        }

        public void markSent() {
            sent = true;
        }

        public int attempts() {
            return attempts;
        }

        public boolean sent() {
            return sent;
        }
    }

    // In-memory idempotency: illustration only, not safe across restarts.
    public static final class OrderProjectionListener {
        private final Set<String> processedIds = new HashSet<>();
        private int effects;

        @EventListener
        public void on(OrderPlaced event) {
            if (!processedIds.add(event.eventId())) {
                System.out.println(
                    "DUPLICATE eventId=" + event.eventId()
                );
                return;
            }

            effects++;
            System.out.println(
                "HANDLED eventId=" + event.eventId()
                    + " orderId=" + event.orderId()
            );
        }

        public int effects() {
            return effects;
        }
    }

    public static final class OutboxWorker {
        private final InMemoryOutbox outbox;
        private final ApplicationEventPublisher publisher;

        public OutboxWorker(
                InMemoryOutbox outbox,
                ApplicationEventPublisher publisher) {
            this.outbox = outbox;
            this.publisher = publisher;
        }

        public void deliverOnce(boolean failBeforeAck) {
            OrderPlaced event = outbox.nextPending();
            if (event == null) {
                return;
            }

            outbox.incrementAttempts();
            publisher.publishEvent(event);

            // Simulate a sender failure after the listener has already run.
            if (failBeforeAck) {
                throw new IllegalStateException(
                    "simulated failure after publish"
                );
            }

            outbox.markSent();
            System.out.println(
                "ACKED eventId=" + event.eventId()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public InMemoryOutbox outbox() {
            return new InMemoryOutbox();
        }

        @Bean
        public OrderProjectionListener projectionListener() {
            return new OrderProjectionListener();
        }

        @Bean
        public OutboxWorker worker(
                InMemoryOutbox outbox,
                ApplicationEventPublisher publisher) {
            return new OutboxWorker(outbox, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            InMemoryOutbox outbox =
                context.getBean(InMemoryOutbox.class);
            OutboxWorker worker =
                context.getBean(OutboxWorker.class);
            OrderProjectionListener projection =
                context.getBean(OrderProjectionListener.class);

            outbox.add(new OrderPlaced("EVT-42", "ORD-42"));

            try {
                worker.deliverOnce(true);
            } catch (IllegalStateException expected) {
                System.out.println(
                    "WORKER_ERROR " + expected.getMessage()
                );
            }

            // Retry the same event without generating a new eventId.
            worker.deliverOnce(false);

            System.out.println(
                "attempts=" + outbox.attempts()
            );
            System.out.println(
                "business_effects=" + projection.effects()
            );
            System.out.println(
                "outbox_sent=" + outbox.sent()
            );
        }
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

**Expected business stdout:**

```text
HANDLED eventId=EVT-42 orderId=ORD-42
WORKER_ERROR simulated failure after publish
DUPLICATE eventId=EVT-42
ACKED eventId=EVT-42
attempts=2
business_effects=1
outbox_sent=true
```

Step-by-step explanation:

1. `Config` registers `OrderProjectionListener` as a Spring bean with an `@EventListener` method. No async multicaster is configured, so Spring dispatches synchronously when `publisher.publishEvent(event)` is called.
2. On the first run, the worker picks up `EVT-42`, increments `attempts`, and publishes the event. The handler has never seen this ID, so it increments `effects=1` and prints `HANDLED`.
3. The worker throws an exception **after** `publishEvent` completes but **before** calling `outbox.markSent()`; `main` catches the error and prints `WORKER_ERROR`.
4. Because `sent=false`, on the second run the worker reads the **exact same event object** with `eventId=EVT-42`. The handler already stored that ID in `processedIds`, so it prints `DUPLICATE` and does not increment `effects`.
5. The worker sets `sent=true` and prints `ACKED`. Result: two attempts, one business effect, sent state.
6. `HashSet` and `int` in the demo are **not thread-safe** when listeners run concurrently; checking `contains/add` is also insufficient to guarantee exactly-once across processes. Production needs unique constraints/transactions and controlled work distribution.
7. `outbox.sent()` only illustrates a **local** ACK. In a real model, a broker ACK or SENT marker has specific semantics; never treat "publish returned" in an async multicaster as listener completion.

**Key takeaway:** the example shows *why* duplicates appear and *why* idempotency is needed, rather than proving Spring Application Events inherently provides an at-least-once guarantee. This is a lesson in failure-handling design, not a promise of durable delivery.

## 9. Production Pattern: Transactional Outbox to Avoid Losing Publish Intent

A more reliable approach for applications using a relational DB:

```text
Inside the place-order transaction:
    UPDATE orders SET status = 'PLACED', ...
    INSERT INTO outbox(
        event_id, aggregate_id, type, payload, status
    ) VALUES (..., 'PENDING')
    COMMIT  -- single transaction

Outbox dispatcher after commit:
    read PENDING records
    send to broker / managed handler
    wait for target ack
    mark SENT or schedule retry

Consumer:
    receive event with stable eventId
    dedupe/idempotent
    commit business effect
    acknowledge consumption when appropriate
```

If the business transaction rolls back, both the `orders` change and the outbox record roll back. If it commits, the intent to emit the event is durably saved. A worker can restart and re-read unsent records.

### 9.1. Two Steps Must Be Atomic on the Publishing Side

Pseudo-SQL example:

```sql
BEGIN;

UPDATE orders
SET status = 'PLACED'
WHERE order_id = :order_id
  AND status = 'DRAFT';

-- After confirming exactly one valid order transitioned state:
INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload_json, status
) VALUES (
    :event_id, :order_id, 'OrderPlaced', :payload_json, 'PENDING'
);

COMMIT;
```

This is a **conceptual pattern**, requiring real DB schemas, business invariants, locking/optimistic locking, and row-count checks. Never publish to a broker before transaction commit hoping a rollback can recall the message.

**Do not turn an outbox into an event payload holding mutable JPA entities.** Store IDs and versioned immutable snapshots, or an integration DTO/JSON with a clear contract.

### 9.2. The Sender Can Resend the Same Record

A typical outbox dispatcher performs:

```text
select pending event
claim/lease
publish message
receive broker acknowledgment
mark record sent
```

If the worker crashes **after publishing succeeds but before marking sent**, the next run can send a duplicate. That is why a transactional outbox normally yields **at-least-once publishing**, not end-to-end exactly-once by default.

To support multiple dispatchers:
- Claim a batch of records with appropriate locking/leasing (e.g., `FOR UPDATE SKIP LOCKED` if the DB supports it).
- Design lease expiry so another worker can reclaim work if an instance dies.
- Avoid holding a DB transaction open across slow remote API calls without a specific reason; claim state/leases can manage this.
- Track durations for outbox pending, inflight, sent, failed, and quarantined states.
- Have retry/backoff policies, monitoring, and recovery when the broker fails.

`SENT` must be defined clearly: for instance, the broker acknowledged receiving the message, **not necessarily** that every consumer finished processing it.

### 9.3. Do Internal Events Always Need a Broker?

**Not necessarily.** If the requirement is simply "run a job after commit without losing it", you can implement a **durable local job/outbox table** in the same application:
- The business transaction writes the job/outbox row to the DB.
- A worker in the same application reads pending jobs after commit.
- The worker invokes the service handler and records the result/ack.
- If the worker errors/restarts, un-acked jobs can be retried.
- The handler uses idempotency by job/event ID.

This mechanism inherits the durability of the source data without needing Kafka/RabbitMQ. However, it requires designing multi-instance concurrency, leases, retries, failure policies, and operability. Never use plain `ApplicationEventPublisher` to simulate a durable job queue.

## 10. Inbox/Idempotency: Avoiding Duplicate Business Effects

The outbox only handles the **publishing/sending** side. Consumers wanting to avoid repeating effects should record processed event markers under an appropriate transaction.

### 10.1. Inbox Pattern in a Relational DB

Pseudo-SQL example for a consumer updating a projection:

```sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_id)
VALUES (:consumer_name, :event_id)
ON CONFLICT DO NOTHING;

-- If INSERT created 1 row: process the effect in the SAME transaction.
-- If INSERT created 0 rows: duplicate; do not apply the effect again.

UPDATE order_projection
SET placed_orders = placed_orders + 1
WHERE projection_id = :projection_id;

COMMIT;
```

**Warning:** the snippet above is an **operational outline**, not a verbatim runnable script. It assumes PostgreSQL-style `ON CONFLICT` and application code **checking the row count**; the `UPDATE` must only run when the INSERT succeeds. If the INSERT is a duplicate, skip the UPDATE and commit/ack. A unique constraint is required:

```sql
ALTER TABLE processed_events
ADD CONSTRAINT uq_processed_consumer_event
UNIQUE (consumer_name, event_id);
```

Safety conditions here:
1. Inserting the "processed" marker and updating the projection **reside in the same DB transaction**.
2. The DB unique constraint ensures two workers racing on the same `(consumerName,eventId)` cannot both apply the effect, even if both read "not seen yet" before inserting.
3. If the transaction fails before commit, **both the inbox marker and projection update roll back**; retries can still process it.
4. ACK the message **after** the DB transaction commits successfully, per the specific broker/consumer semantics.

Do not commit a "processed" marker first and then apply the business update in a separate transaction: crashing between the two steps leaves a marker without the effect, causing retries to skip and effectively losing the event.

### 10.2. Handling External Side Effects

If a consumer needs to send an email, call a payment gateway, or hit an external API outside the DB, a local unique constraint cannot guarantee the external side effect ran once.

Approaches:
- Call an API supporting an **idempotency key** and pass `eventId` or an appropriate business key.
- Turn the external task into a **secondary job/outbox** written in the same deduplication transaction, then let a dedicated worker execute it with retries.
- For third parties without idempotency support, design reconciliation/compensation, query state via external references, and bound duplicate impact.
- Never mark "processed" merely because an HTTP request was sent; distinguish success, transient failure, and unknown outcome.

An email sent twice may be an unavoidable duplicate if the provider lacks strong idempotency guarantees. Describe the real guarantee rather than advertising exactly-once when boundaries do not share a transaction.

### 10.3. Dedupe Key per Consumer

Suppose `EVT-42` is consumed by `BillingProjection`, `AuditProjection`, and `NotificationHandler`. If a shared table has a single unique `eventId` and the first consumer writes the marker, the remaining consumers could be wrongly blocked.

Use a unique key `(consumer_name, event_id)` or a separate inbox table per consumer. Each consumer is allowed to process the same event for its own purpose **once**, while blocking duplicate retries for itself.

## 11. At-Least-Once with Multiple Listeners in the Same Process

A single Spring event can trigger multiple independent listeners:

```text
OrderPlaced EVT-42
   |
   +--> AuditListener           success
   +--> NotificationListener    failed
   +--> LoyaltyListener         success
```

If you retry the **entire** `publishEvent(EVT-42)`, `AuditListener` and `LoyaltyListener` may re-run even though they already succeeded. The Spring multicaster has no built-in per-listener acknowledgment.

There are three options depending on requirements:

1. **Best-effort internal event:** accept lost tasks/manual recovery; simple, suitable for rebuildable metrics/cache invalidation if the business permits.
2. **Local per-handler retry/idempotency:** handler retry logic with stable keys, timeouts, and error reporting; keeping state only in RAM still leaves a crash gap.
3. **Durable handler jobs:** persist one job per critical consumer, e.g. unique `(eventId,handlerName)`, with independent retries and acks. This can be built with a DB queue/outbox or a broker with appropriate consumer groups/subscriptions.

Using a single shared `SENT` status for the whole event **does not prove** all listeners finished. When reliable fan-out is required, track outcomes per consumer/subscription/handler. One slow handler should not cost another handler its processing ability, unless business transactions explicitly require all of them in a single designed atomic boundary.

### Ordering and Versions

At-least-once **does not guarantee ordering**. `OrderPlaced(v5)` can be retried and arrive after `OrderCancelled(v6)`. Consumers need a policy:
- process by `aggregateVersion`/sequence if the contract requires it;
- detect duplicates via `eventId`;
- ignore older versions, buffer, or reconcile depending on semantics;
- use an appropriate partition/key if the broker guarantees order within that scope.

Deduplication and ordering are **two separate problems**.

## 12. Backoff, Poison Messages, and Retry Limits

Retrying every error immediately can cause a retry storm:
- DB is down → thousands of tasks retry instantly, adding even more load.
- Broker is slow → publishers exhaust threads and connections.
- Invalid event payload → retrying a permanent error forever with no hope of success.
- One failing listener blocks the whole pipeline without isolation.

A practical policy can classify errors:

| Error type | Example | Handling approach |
| --- | --- | --- |
| Transient | network timeout, 503, retriable deadlock | Backoff with jitter, concurrency limits |
| Invalid | bad schema, missing ID, violated domain invariant | Do not retry infinitely; quarantine/DLQ, fix or intervene |
| Unknown outcome | HTTP timeout after downstream may have committed | Retry with **the same idempotency key**, reconcile when needed |
| Duplicate conflict | Inbox unique conflict/already processed | Ack per contract; create no new side effect |
| Overloaded infrastructure | queue full, broker unavailable | Keep durable records and slow retries/apply backpressure |

**Exponential backoff with jitter** reduces thundering herds where many workers retry at the exact same instant. You can cap max attempts and move records to a DLQ, but then state the guarantee accurately: the event was retained for failed-item handling, **not business-completed**. You need dashboards and safe replay/resubmit procedures.

Never change the event ID when moving to a DLQ or replaying the same logical event; store attempt count and last error as separate metadata rather than embedding them into the event's identity.

## 13. Transactions, Error Handling, and Event Loss Risk

### 13.1. @EventListener Inside the Source Transaction

A synchronous `@EventListener` invoked while a service is `@Transactional` can execute before commit. If the listener writes to the same DB transaction, its changes can roll back with the service when the transaction fails. However, if the listener calls an external API, the API does not participate in DB rollback by default.

Adding `@TransactionalEventListener(AFTER_COMMIT)` to defer side effects can get timing right, yet still leaves a post-commit crash window. For work that must complete, an outbox persisted atomically with the business state narrows the **lost publish intent** gap.

### 13.2. Multicaster ErrorHandler

`SimpleApplicationEventMulticaster.setErrorHandler(...)` can change how listener errors are handled. If the handler suppresses exceptions and only logs, the caller may see publish succeed even when a listener failed. If it propagates, the caller may receive an error (on the sync path) and think it should retry the entire event; consider earlier listeners that already executed effects.

Never rely on the return of `publishEvent()` as a durable ACK when async listeners exist. If using a custom `ErrorHandler`, metrics and retries must know accurately where exceptions count as failures, avoiding both swallowing errors and falsely marking tasks "DONE".

### 13.3. Retries Must Not Repeat Domain Commands

Suppose a `PlaceOrder` command committed and emitted `OrderPlaced`. When resending a notification is needed, do **not** re-run the entire `PlaceOrder` command to generate a new event; doing so can duplicate invoices/payments or create extra audit facts.

Persist and retry the **event that already occurred** with a stable ID; do not replay the source business command unless the command was designed to be idempotent and that is truly the intended action.

### 13.4. Reactive Flows

In Spring WebFlux, an unsubscribed `Mono` may not have run its logic yet. Creating an event and calling `publishEvent` outside the reactive chain does not automatically make transactions or eventual completion correct. With reactive transactions, use proper context propagation and `TransactionalEventPublisher`; `@TransactionalEventListener` does not turn messages into a durable queue.

Do not call `subscribe()` inside a listener to "fire-and-forget" when guarantees are required: exceptions, cancellation, lifecycle, and awaiting completion become hard to control. Compose the reactive chain properly or persist durable work per contract.

## 14. Testing At-Least-Once and Idempotency

Reliability tests **cannot just assert a callback was called**. You must test failure windows and duplicate attempts.

### 14.1. Unit Test of an Idempotent Handler

For a handler receiving `EVT-42`:
1. Call the first time; assert the business effect is applied.
2. Call a second time with the **same `eventId`**; assert the effect does not increase.
3. Call `EVT-43` with the same `orderId` as a different event; assert the new event is processed properly.
4. If multiple consumers exist, verify each consumer deduplicates independently.
5. Verify the record contains an immutable snapshot, not a managed entity.

In the Java demo in section 8, publishing the same event twice yields `business_effects=1`, though that alone is not enough to prove persistent idempotency.

### 14.2. Integration Test for Transaction Rollback

Use a real DB or test container:
- In one transaction, update the aggregate and insert the outbox row.
- Force a rollback; assert **neither** is committed.
- Commit normally; assert **both** exist.
- Do not merely mock the repository and conclude atomicity was tested.

If using `@Transactional` on a test method where the framework auto-rolls back at the end of the test, explicitly control commits with `TransactionTemplate` or test transaction utilities when you need to prove the commit branch.

### 14.3. Crash Before and After ACK

Scenarios to test:

| Simulated failure point | Remaining data | Expectation after restart/retry |
| --- | --- | --- |
| Before DB transaction commit | No aggregate change/outbox | No spurious event emitted |
| After DB commit, before dispatcher | Outbox PENDING exists | Worker resumes sending |
| After broker receives, before sender marks SENT | Outbox still PENDING | May send duplicate; consumer deduplicates |
| After consumer DB effect commits, before broker ACK | Effect + inbox marker committed | Broker redelivers; consumer skips duplicate and ACKs |
| Before consumer DB commit | Effect + marker rolled back | Retry applies effect once |
| External API timeout with unknown outcome | Downstream state may have succeeded | Retry with same idempotency key/reconcile |
| Event causing permanent failure | Record retried/moved to DLQ | Alerts and recovery actions occur, never vanishes silently |

Testing sender crashes can use fault injection at the exact step (after publish and before marking sent). Testing consumer crashes can kill the process/test container or inject controlled faults; always read state back from durable storage rather than keeping everything in RAM.

### 14.4. Concurrency Test

Two workers receiving `EVT-42` simultaneously must not create two business effects:
- Use a DB unique constraint as the final contention mechanism.
- Test two transactions running concurrently and verify one becomes a duplicate.
- Do not use only `ConcurrentHashMap.putIfAbsent(...)` in a single process and claim multi-instance safety.
- If outbox records are claimed by multiple dispatchers, test leases, locks, and expiry.

### 14.5. Testing Async with Signals, Not Sleep

If a listener runs asynchronously, use `CountDownLatch`, `CompletableFuture`, or Awaitility with a finite timeout to wait for the **exact processing milestone**; `Thread.sleep(500)` does not prove at-least-once. A test waiting for `publishEvent()` to return has not proven the listener ran.

### 14.6. Post-Commit Integration Test

With `@TransactionalEventListener(AFTER_COMMIT)`, actually commit and assert the listener ran; roll back and assert the after-commit listener did not run. However, that result only tests **phase behavior**, not that the callback still runs after a process crash. To verify reliability, test the outbox/queue and restart recovery.

## 15. Observing and Operating an At-Least-Once Pipeline

Useful metrics:

| Metric | Meaning |
| --- | --- |
| `outbox.pending.count` | Number of unsent events |
| `outbox.oldest.pending.age` | Age of the oldest pending event |
| `outbox.dispatch.attempts` | Number of send attempts |
| `outbox.dispatch.failures` | Number of failed sends |
| `outbox.sent.count` | Number of times sender marked delivery successful |
| `consumer.duplicate.count` | Number of deduplicated duplicates |
| `consumer.processing.duration` | Processing time per attempt |
| `consumer.final.failures` | Number of events routed to quarantine/DLQ |

The names above are **illustrative conventions**; Micrometer/Prometheus do not emit all these metrics automatically without instrumentation. Use bounded tags like `eventType`, `consumer`, `outcome`, and `exceptionCategory`.

**Do not attach `eventId` or `orderId` to metric tags** due to high cardinality. Put IDs in structured logs/tracing; keep `correlationId` to trace workflows. When a record stays PENDING too long or the DLQ grows, you need alerts and recovery runbooks, not just dashboards.

Distinguish metrics:
- `dispatch attempts`: number of tries.
- `logical events`: number of distinct event IDs.
- `consumer effects committed`: number of committed business effects.
- `duplicates skipped`: number of deduplicated attempts.

If three attempts of the same `EVT-42` yield one effect, displaying "3 events processed" is semantically wrong. Name and document metrics accurately by boundary so SLOs are not distorted.

## 16. When Is a Best-Effort Internal Event Enough?

Not every event needs an outbox and a broker.

| Event / task | Typical reliability to consider |
| --- | --- |
| Recording a minor metric that can tolerate missing samples | Best-effort is usually acceptable |
| Evicting a cache that has a TTL and can rebuild | Eventual repair may be acceptable |
| Sending non-essential notifications | Depends on product commitment; retries or a queue may suffice |
| Updating user-facing critical projections | Should have durable retries or rebuild/reconciliation mechanisms |
| Sending invoices, ledger posting, charging fees | Requires atomic intent, idempotency, audit, and strict recovery |
| Cross-service integration requiring zero lost changes | Outbox + broker/worker + consumer deduplication and monitoring |

Examples are discussion guides only; actual business requirements dictate the guarantee level. Some systems can rebuild projections from source data instead of saving every event; in that case, verify recovery time and consistency requirements.

**Do not promote every Spring event to a Kafka message just out of fear of duplicates.** Conversely, never use an in-memory `@Async @EventListener` for work where losing even one item is unacceptable. Choose the reliability level matching the goal.

## 17. Common Misconceptions

1. **"Spring publishEvent guarantees at-least-once."** False: it dispatches in-process; there is no default durable store/retry.
2. **"@TransactionalEventListener(AFTER_COMMIT) never loses events."** False: crashing right after commit still leaves a gap.
3. **"Enabling @Async gives you a safe queue."** False: an in-RAM executor queue does not survive process restarts on its own.
4. **"At-least-once means the listener runs only once."** False: duplicates are expected behavior.
5. **"Event ID is the order ID."** False: one aggregate can emit many events.
6. **"Retrying the whole PlaceOrder command is the same as retrying the OrderPlaced event."** False: can duplicate source business operations.
7. **"An in-JVM HashSet is enough to deduplicate."** Not durable across restarts and unsafe across multiple instances.
8. **"INSERT inbox marker then call API in another transaction is atomic."** False: crashing between the two steps can lose the effect.
9. **"Sender marking SENT means every consumer finished."** Not necessarily; depends on the ACK contract.
10. **"Outbox gives end-to-end exactly-once."** Normally false: can duplicate on crash between publish and marking sent.
11. **"Deduplicating by correlationId is enough."** False: one correlation ID can span many events.
12. **"At-least-once guarantees ordering."** False: ordering/versions must be handled separately.
13. **"Retry permanent errors as fast as possible."** False: causes retry storms; needs backoff/quarantine.
14. **"ErrorHandler suppresses the error and publish returns means success."** False: a listener may have failed.
15. **"Running a test once proves crash recovery."** False: must test durable state and fail/restart windows.

## 18. Design Review Checklist

- [ ] Is the guaranteed **boundary** stated clearly: sender→broker, broker→consumer, or business effect?
- [ ] Does critical work have durable intent/outbox or an equivalent queue?
- [ ] Is Event ID generated **once** per logical event and preserved across retries?
- [ ] Are correlation IDs or aggregate IDs avoided as substitutes for event IDs?
- [ ] Are payloads immutable/serializable, free of JPA managed entities or transient context?
- [ ] Are aggregate + outbox written in the same transaction when post-commit event loss must be avoided?
- [ ] Is there a clear ACK contract: what does SENT mean, what does DONE mean?
- [ ] Does the consumer have deduplication/unique constraints on `(consumerName,eventId)` and atomic effects where possible?
- [ ] Do external side effects have idempotency keys or reconciliation/compensation?
- [ ] Are there retry/backoff/jitter, timeouts, dead-letter/quarantine, and runbooks?
- [ ] Are multi-worker contention, leases/claims, and post-crash resets handled?
- [ ] Is there an ordering/version policy and handling for late-arriving events?
- [ ] Do metrics separate attempts, duplicates, committed effects, and backlog?
- [ ] Do tests cover rollbacks, crashes before/after ACK, duplicates, concurrency, and restarts?
- [ ] If best-effort only, has the business accepted the risk of event loss?

**Remember:** Spring Application Events solves **in-process notification**, not **durable delivery** by default. If at-least-once is required, you must have a durable event/job source, retries, and explicit ACKs. Duplicates are then normal: design idempotent consumers and proper transactions/inboxes so the same logical event can be **delivered multiple times while creating the valid business side effect only once** within the committed scope.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1 API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.1 API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring 6.1 API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Martin Fowler — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)

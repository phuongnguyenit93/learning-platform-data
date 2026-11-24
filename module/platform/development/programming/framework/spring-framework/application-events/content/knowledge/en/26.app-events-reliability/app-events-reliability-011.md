# Ensuring Ordering for Dependent Events in Spring Framework

## 1. The Problem: Event A Must Finish Before Processing Event B

An application often splits work into events:

```text
OrderSubmitted
    |
    +-- ReserveInventory
    |
    +-- AuthorizePayment
    |
    +-- CreateInvoice
```

Suppose the business requirement is **create the invoice only after inventory has been reserved and payment has been authorized**. If three independent listeners all listen to `OrderSubmitted`, calling them in order A, B, C **does not guarantee** the operations complete in that order. Especially with `@Async`, thread pools, transaction callbacks, retries, or brokers, two handlers can overlap and finish in a different order.

In the **Reliability** group of Spring Framework Application Events, "ordering guarantee" must be stated precisely:

- **Publish order:** the producer calls `publishEvent(E1)` before `publishEvent(E2)`.
- **Dispatch/invocation order:** the multicaster starts calling listener X before listener Y.
- **Completion order:** X's work and side effects actually succeed before Y executes its dependent part.
- **Commit order:** data changes for E1 commit before changes related to E2.
- **Delivery/consume order:** E1 arrives at and is applied by the consumer before E2, even across retries, multiple workers, and restarts.
- **Per-aggregate order:** E1 of order O-1 must precede E2 of **the same order O-1**; global locking across unrelated orders is not necessarily required.

These are **different** contracts. Neither an `@Order` annotation nor increasing executor threads can substitute for all of them.

**Core principle:** When B genuinely depends on the **successful outcome** of A, represent that boundary with a result event such as `InventoryReserved` or a durable state. Only start B once the precondition is verified.

## 2. What Does `@Order` Solve, and What Does It Not Solve?

Spring Framework supports `@Order` on `@EventListener` methods to arrange **listener invocation order**:

```java
@Order(10)
@EventListener
public void validate(OrderSubmitted event) {
    // Validate data.
}

@Order(20)
@EventListener
public void reserve(OrderSubmitted event) {
    // Reserve inventory.
}
```

This is **illustrative code**, not a standalone application; it requires Spring beans, imports for `org.springframework.core.annotation.Order` and `org.springframework.context.event.EventListener`.

With the **default synchronous multicaster**, `validate` is called before `reserve` according to ordering. If `validate` runs and returns normally, `reserve` is then called along the regular dispatch path. This can be useful for small, synchronous operations within the same context and event.

However:

1. `@Order` **creates no transaction boundary** and does not enforce committed data.
2. It cannot guarantee external callbacks (HTTP, email, broker) succeeded if the listener merely **submits** a task and returns.
3. With `@Async`, calling through the proxy may only **enqueue the task on an executor**; the next handler is dispatched while the previous task is still running or has not even started.
4. If events A and B are published from **two different threads/producers**, `@Order` across listeners of one event does not define a total order between A and B.
5. With a custom multicaster using an executor, listener invocation and completion may not match order.
6. `@Order` only sorts Spring-known listeners within a matching dispatch/phase mechanism; it does not define processing order across services, brokers, JVM restarts, or multiple nodes.

Decision table:

| Tool | Useful guarantee | Should not be inferred |
| --- | --- | --- |
| `@Order` + synchronous listener | Invocation order within one dispatch; earlier method finishes normally before next runs | DB commit, durable delivery, global order |
| `@Order` + `@Async` | Order Spring **invokes/submits** listeners at the dispatcher when applicable | Async tasks finish in that order |
| Single-worker executor | Sequential execution of **tasks already accepted on that executor**, per queue/policy semantics | Multiple producers publish in business order; no task fails/crashes |
| Result event `ACompleted` emitted after A succeeds | B is only **triggered** when milestone A is announced in code | Events/side effects are durably persisted across crashes |
| `@TransactionalEventListener(AFTER_COMMIT)` | Handler waits for successful commit of the transaction that published the event | All post-commit handlers finish or get retried |
| Transactional outbox + sequence + ordered worker | Foundation for reliable delivery and per-aggregate ordering when implemented properly | Automatic exactly-once side effects, ordering across all aggregates |

**Conclusion:** `@Order` is a callback-sorting tool, not a mechanism for orchestrating dependent workflows.

## 3. Counterexample: Two Listeners Subscribing to One Event

Suppose both inventory and payment handle `OrderSubmitted`:

```java
@Component
class InventoryListener {
    @Async("eventExecutor")
    @Order(0)
    @EventListener
    public void reserve(OrderSubmitted event) {
        inventoryApi.reserve(event.orderId());
    }
}

@Component
class PaymentListener {
    @Order(10)
    @EventListener
    public void charge(OrderSubmitted event) {
        paymentApi.charge(event.orderId());
    }
}
```

This is an **illustrative snippet, not standalone**; it requires `@EnableAsync`, an executor, service APIs, and Spring-managed beans.

Valid execution trace:

```text
Publisher thread                 Worker thread
      |
      +-- dispatch InventoryListener (@Order 0)
      |       |
      |       +-- submit reserve task --------->
      |
      +-- dispatch PaymentListener (@Order 10)
      |       |
      |       +-- paymentApi.charge(...)
      |                                      reserve() has not finished yet
      |
      +-- publisher continues
```

Even though `@Order(0)` was processed earlier by the dispatcher, it **does not wait** for `reserve()` on the executor to finish. If payment requires reserved inventory, the system has a race condition.

Insufficient "fixes":

- Changing `@Order(0)` to `@Order(-100)`: only changes invocation priority.
- Putting `Thread.sleep(100)` in the payment listener: I/O latency and schedulers are unpredictable.
- Growing the thread pool: can make the race happen even more often.
- Using `AtomicBoolean reserved` and `while (!reserved) {}`: busy-waiting, not durable, breaks across multiple events/orders.
- Treating `publishEvent()` returning as a signal that all async handlers succeeded: violates the API contract.

You need a **business-meaningful happens-before relationship**: when reservation succeeds, the producer/handler emits **`InventoryReserved`**; the consumer for the dependent step listens only to `InventoryReserved`, not `OrderSubmitted`.

## 4. Designing Event Chains Around Completion Milestones

A sounder model:

```text
OrderSubmitted
    |
    +-- InventoryService.reserve(orderId)
            |
            +-- SUCCEEDS and required state is recorded
                    |
                    +-- publish InventoryReserved(orderId, reservationId)
                            |
                            +-- PaymentService.authorize(...)
                                    |
                                    +-- SUCCEEDS
                                            |
                                            +-- publish PaymentAuthorized
                                                    |
                                                    +-- InvoiceService.create(...)
```

Each result event expresses **a business fact already achieved**, rather than "starting to do work".

With in-memory synchronous services, once a step succeeds and `publishEvent` is called in the handler, the next event dispatches via Spring. With async, the handler must **explicitly call the publisher** after work finishes:

```java
@Async("eventExecutor")
@EventListener
public void onSubmitted(OrderSubmitted event) {
    Reservation reservation = inventory.reserve(event.orderId());

    // Only publish when reserve() actually succeeds.
    publisher.publishEvent(new InventoryReserved(
            event.orderId(), reservation.id()));
}
```

This is **illustrative code**; `inventory`, `Reservation`, and event classes belong to the application.

Two critical conditions:

1. `inventory.reserve(...)` must have a clear contract: when it returns normally, is the resource actually reserved? If it only returns a future or "accepted", await **true completion** rather than publishing "reserved" prematurely.
2. `publishEvent(new InventoryReserved(...))` happens **after the previous step succeeds**, yet if durability across crashes is required, you need an event store/outbox. Calling the publisher in RAM does not ensure the next event recovers after a restart.

Failure events should have their own contract such as `InventoryReservationFailed`, or a durable workflow state; never emit `InventoryReserved` in a `finally` block regardless of outcome.

## 5. Runnable Example: `@Order` Does Not Wait for Async; Result Events Solve Dependencies

The example uses **Java 17+**, **Spring Framework 6.2.12**, and Gradle 8+. No Spring Boot, web server, database, or message broker is needed.

We intentionally create two listeners for **the same event** `OrderSubmitted`:

- `AsyncInventoryListener` has `@Order(0)` and `@Async("eventExecutor")`; the reservation work is gated by a `CountDownLatch`.
- `DirectInvoiceListener` has `@Order(10)` and handles `OrderSubmitted` **directly**; it reads the reservation status even though it was ordered later in dispatch.
- `ChainedInvoiceListener` does **not** listen to `OrderSubmitted`, listening instead to `InventoryReserved` published only after reservation finishes.

The output will prove that a listener with `@Order(10)` can still run while `@Order(0)` async work has not finished; meanwhile, the listener relying on the result event runs only after the precondition is met.

### 5.1. Project Structure

```text
spring-dependent-events-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DependentEventsDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-dependent-events-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.DependentEventsDemo'
}
```

### 5.2. `src/main/java/demo/DependentEventsDemo.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class DependentEventsDemo {

    public record OrderSubmitted(String orderId) {}
    public record InventoryReserved(String orderId) {}

    // Demo-only state, not a production state store.
    public static class Probe {
        final CountDownLatch inventoryStarted = new CountDownLatch(1);
        final CountDownLatch allowInventory = new CountDownLatch(1);
        final CountDownLatch invoiceObserved = new CountDownLatch(1);

        final AtomicBoolean inventoryDone = new AtomicBoolean(false);
        final AtomicBoolean directSawDone = new AtomicBoolean(true);
        final AtomicBoolean chainedSawDone = new AtomicBoolean(false);
        final AtomicReference<String> invoicedOrder =
                new AtomicReference<>();
        final AtomicReference<Throwable> workerError =
                new AtomicReference<>();
    }

    public static class AsyncInventoryListener {
        private final Probe probe;
        private final ApplicationEventPublisher publisher;

        public AsyncInventoryListener(
                Probe probe, ApplicationEventPublisher publisher) {
            this.probe = probe;
            this.publisher = publisher;
        }

        @Order(0)
        @Async("eventExecutor")
        @EventListener
        public void reserve(OrderSubmitted event) {
            probe.inventoryStarted.countDown();
            try {
                // Block work to prove @Order does NOT wait for async.
                if (!probe.allowInventory.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "inventory release timeout");
                }

                // Simulate reservation succeeded.
                probe.inventoryDone.set(true);

                // Next event is published ONLY AFTER step A finishes.
                publisher.publishEvent(
                        new InventoryReserved(event.orderId()));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.workerError.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.workerError.compareAndSet(null, ex);
            }
        }
    }

    // Later in dispatch does NOT mean after A completes.
    public static class DirectInvoiceListener {
        private final Probe probe;

        public DirectInvoiceListener(Probe probe) {
            this.probe = probe;
        }

        @Order(10)
        @EventListener
        public void onSubmitted(OrderSubmitted event) {
            probe.directSawDone.set(probe.inventoryDone.get());
        }
    }

    // Triggered only by the event representing prior step success.
    public static class ChainedInvoiceListener {
        private final Probe probe;

        public ChainedInvoiceListener(Probe probe) {
            this.probe = probe;
        }

        @EventListener
        public void onInventoryReserved(InventoryReserved event) {
            probe.chainedSawDone.set(probe.inventoryDone.get());
            probe.invoicedOrder.set(event.orderId());
            probe.invoiceObserved.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        AsyncInventoryListener asyncInventoryListener(
                Probe probe, ApplicationEventPublisher publisher) {
            return new AsyncInventoryListener(probe, publisher);
        }

        @Bean
        DirectInvoiceListener directInvoiceListener(Probe probe) {
            return new DirectInvoiceListener(probe);
        }

        @Bean
        ChainedInvoiceListener chainedInvoiceListener(Probe probe) {
            return new ChainedInvoiceListener(probe);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Probe probe = context.getBean(Probe.class);

            try {
                context.publishEvent(new OrderSubmitted("O-42"));

                if (!probe.inventoryStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async inventory did not start");
                }

                // Async thread is blocked; @Order(10) listener
                // already dispatched on the publisher thread.
                System.out.println("direct saw inventory done="
                        + probe.directSawDone.get());
                System.out.println("inventory done before release="
                        + probe.inventoryDone.get());
            } finally {
                // Even if an error occurs, release worker for shutdown.
                probe.allowInventory.countDown();
            }

            if (!probe.invoiceObserved.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "dependent event was not observed");
            }
            if (probe.workerError.get() != null) {
                throw new IllegalStateException(
                        "inventory worker failed",
                        probe.workerError.get());
            }

            System.out.println("chained saw inventory done="
                    + probe.chainedSawDone.get());
            System.out.println("invoiced order="
                    + probe.invoicedOrder.get());
        }
    }
}
```

### 5.3. Running the Example

With JDK 17+ and Gradle installed:

```bash
gradle -q run
```

Expected `System.out.println` lines:

```text
direct saw inventory done=false
inventory done before release=false
chained saw inventory done=true
invoiced order=O-42
```

Gradle and libraries may print other logs depending on configuration; the four lines above are the output intentionally printed by the program.

### 5.4. Why Is This Output Deterministic?

1. `@EnableAsync` creates an async interceptor for the `AsyncInventoryListener` bean. Spring's event infrastructure invokes the listener through the Spring bean proxy, so `reserve(...)` is submitted to `eventExecutor`.
2. The `@Order(0)` listener is dispatched before the `@Order(10)` listener for `OrderSubmitted`, yet **the reserve work runs on another thread**.
3. `inventoryStarted.countDown()` signals the worker started, then the worker blocks on `allowInventory.await(...)`; hence `inventoryDone` **cannot be true yet** when `main` prints the first two lines.
4. `DirectInvoiceListener` still runs on `OrderSubmitted`'s dispatch path and reads `false` because nothing waited for reservation to succeed.
5. `finally` releases the latch; the worker sets `inventoryDone=true` and explicitly calls `publisher.publishEvent(new InventoryReserved(...))`.
6. `ChainedInvoiceListener` listens for `InventoryReserved` and is called by the default synchronous multicaster on the thread that just published the new event; it reads `inventoryDone=true`, records the order ID, and triggers `invoiceObserved`.
7. `main` prints the last two lines **only after** the latch confirms the dependent handler observed the result event. No `Thread.sleep()` is used to guess scheduler order.

**Demo limitation:** `AtomicBoolean` here only simulates a completed business step in memory, **not a DB reservation or crash-safe delivery guarantee**. Production systems must tie publishing `InventoryReserved` to **successful state persistence** and use proper retry/idempotency designs.

## 6. Choosing How to Guarantee Ordering by Dependency Level

Not every event needs the same model. Distinguish the cases:

| Case | Mechanism to consider |
| --- | --- |
| Two small, synchronous operations, same event, same thread | `@Order` + simple handler design, or explicit service call if A must precede B |
| B may start only when async A succeeds | Emit `ACompleted` after A, have B listen to `ACompleted` |
| A and B must be in **one DB transaction** | Service/orchestrator calls A then B inside one `@Transactional`; events do not replace transaction atomicity |
| B needs data committed by A | Publish in A's transaction, consume at `@TransactionalEventListener(AFTER_COMMIT)` or outbox |
| Multiple events of the **same aggregate** must apply in order | Monotonic `aggregateSequence`, keyed ordered dispatch, consumer version/gap checking |
| Independent aggregates can run in parallel | Partition/serialize by `aggregateId`, letting different keys run concurrently |
| B needs both A and C to finish | Durable state machine/join barrier tracking each precondition, not merely relying on invocation order |
| Multi-service system with crashes/retries and durability needs | Transactional outbox + ordered relay + idempotent consumer, or workflow engine |

Very important example: if **inventory check** and **payment authorization** are both preconditions for **creating an invoice**, they can run in parallel yet need a **join condition**:

```text
                   +-- InventoryReserved(orderId)
OrderSubmitted ----|
                   +-- PaymentAuthorized(orderId)
                              |
                    [does order state have both?]
                              |
                              +-- InvoiceRequested(orderId)
```

The safe way is persisting per-order state in the DB and emitting `InvoiceRequested` only when both flags succeed, using **atomic updates/optimistic locking or a unique constraint** so two concurrent listeners do not emit two invoices. Never use a static `HashMap` and unsynchronized `if (inventory && payment)` to decide in multi-threaded/multi-node systems.

## 7. Synchronizing One Service vs. Guaranteeing Event Ordering Are Two Separate Problems

If the real business requirement is:

1. Validate;
2. Reserve inventory;
3. Record payment;
4. Confirm order;

and all operations live in **the same DB and require atomicity**, explicit service calls are often easier to reason about and control than event choreography:

```java
@Transactional
public void checkout(CheckoutCommand command) {
    validation.validate(command);
    Reservation reservation = inventory.reserve(command);
    Payment payment = paymentRepository.record(
            command, reservation);

    orderRepository.confirm(command.orderId(),
            reservation.id(), payment.id());

    publisher.publishEvent(new OrderConfirmed(
            command.orderId()));
}
```

This is an **illustrative snippet**; types and services are application-defined. DB operations in the same transaction can roll back together. However, calling an **external HTTP payment system** does not automatically join the DB transaction; when external services are involved, you need sagas/compensation or stateful workflows.

**Rule:** Events fit **announcing milestones that happened and reducing coupling**, not necessarily replacing sequential control flow when steps are tightly dependent, need immediate error returns, or must share a single transaction.

Even inside an explicit service flow, you can publish an `OrderConfirmed` event once DB state is established, then use an outbox/after-commit for post-processing tasks.

## 8. `@TransactionalEventListener(AFTER_COMMIT)` Solves One Kind of Ordering

Example:

```java
@Transactional
public void placeOrder(CreateOrder command) {
    repository.insert(command);
    publisher.publishEvent(new OrderStored(command.orderId()));
}
```

Listener:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void sendToWarehouse(OrderStored event) {
    warehouseClient.enqueue(event.orderId());
}
```

These are **illustrative snippets**, requiring Spring transaction annotation imports, service beans, and application-defined event types.

`@TransactionalEventListener(AFTER_COMMIT)` binds the handler to the **successful transaction commit milestone**. If the transaction rolls back, the `AFTER_COMMIT` handler is not invoked. This is the right barrier when downstream needs committed data.

Yet limitations remain:

- `AFTER_COMMIT` does **not** make all post-commit listeners finish sequentially.
- If multiple `AFTER_COMMIT` listeners carry `@Order`, Spring can order callbacks within that phase, yet that does not replace `@Async` task completion or an external service confirming success.
- With imperative transactions, the event must be published **while the transaction is active on the right thread**. Publishing on a worker thread outside the transaction expecting it to attach to the HTTP thread's transaction will not work.
- Without a transaction, transactional listeners **do not run** by default (`fallbackExecution=false`).
- After commit, JDBC/JPA transaction resources may still be thread-bound during callback execution. If the listener must write new DB data, use `@Transactional(propagation = REQUIRES_NEW)` on a proxied service bean or an equivalent transaction boundary.
- If the executor rejects or the JVM dies after DB commit before the callback finishes, the source transaction **cannot roll back** to rescue post-processing.

### 8.1. `AFTER_COMMIT` and Event B

If post-commit listener A runs and publishes event B on a thread **with no new transaction**, a `@TransactionalEventListener` for B may **not be called** because there is no transaction to bind to. If B needs to bind to the commit of another DB change, you need:

```text
T1 commits OrderStored
    |
    +-- after-commit A
          |
          +-- service opens a new transaction T2
                 |
                 +-- write result of step A
                 +-- publish B while T2 is active
                 |
                 +-- T2 COMMITS
                      |
                      +-- AFTER_COMMIT listener for B
```

Never casually call `publishEvent(B)` inside a post-commit callback expecting every transactional listener of B to pick it up automatically.

## 9. Multiple Events of the Same Aggregate: Ordering by `aggregateId` and Sequence

In queue/broker or multi-instance architectures, business ordering may need to survive restarts and retries.

Example of order O-42 changing sequentially:

```text
Order O-42
  E1: created         aggregateSequence=1
  E2: payment-approved aggregateSequence=2
  E3: shipped         aggregateSequence=3
```

Consumers must avoid applying E3 before processing the required preconditions from E1/E2.

A useful envelope:

```java
public record OrderedEvent<T>(
        String eventId,
        String aggregateId,
        long aggregateSequence,
        String eventType,
        String correlationId,
        Instant occurredAt,
        T payload) {}
```

This is an **illustrative definition**, requiring `import java.time.Instant`. Each field has a role:

- `eventId`: unique identifier of **each created business event instance**, for deduplication.
- `aggregateId`: key to partition/serialize events belonging to the same entity/aggregate.
- `aggregateSequence`: **monotonically increasing sequence number per aggregate event**, generated in the same transaction as the state/outbox change.
- `eventType`: announces the business milestone, e.g., `PaymentAuthorized`.
- `correlationId`: links events of the same workflow/request.
- `occurredAt`: reference/logging timestamp, **not a locking or total-order mechanism**.
- `payload`: immutable snapshot or delta with an explicit schema.

**Important:** If an aggregate version can increment on a change that **does not emit an event**, do not assume the event sequence matches the entity `@Version` contiguously. Manage a dedicated `aggregateSequence` for the event stream or define a contract for gaps. Distinguish `schemaVersion` (payload structure version) from `aggregateSequence` (event order).

### 9.1. Detecting Duplicates, Stale Events, and Missing Events

A keyed consumer can persist:

```text
lastAppliedSequence[aggregateId] = n
```

For an incoming event with sequence `s`:

```text
s == n + 1 -> eligible to apply if business state matches;
              commit change and lastAppliedSequence atomically
s <= n     -> stale or duplicate event; handle per idempotency/contract
s > n + 1  -> gap detected: hold/retry/defer and investigate missing event
```

This is **pseudocode**; combine it with `eventId`, migration/replay policies, and business cases where certain states may be skipped. Do not apply that formula rigidly if the event stream does not guarantee contiguous sequences or the consumer intentionally needs only the latest state.

If a consumer needs every historical step, never simply "take the highest-version event and overwrite" when E1 has not been processed. If a consumer only builds a **current-state projection** from full snapshots, it may choose **last-write-wins by version** and ignore older events. Those are two distinct contracts and must be documented explicitly.

### 9.2. Atomic Updates to Prevent Races Between Two Consumers

Illustrative SQL logic:

```sql
-- All inside the transaction processing an aggregate's event.
SELECT last_sequence
FROM consumer_progress
WHERE consumer_name = :consumer AND aggregate_id = :aggregate_id
FOR UPDATE;

-- Only when incoming_sequence = last_sequence + 1 and event not yet processed:
-- 1) apply DB side effect
-- 2) update last_sequence
-- 3) insert processed_event(event_id) under unique key
-- COMMIT
```

This is **database-dependent SQL/pseudocode**, not a runnable script. Row locking/contention/unique indexes must be tailored to the concrete database; if no `consumer_progress` row exists yet, handle row creation and creation races with proper unique constraints/upserts. Off-DB tasks (email/HTTP) do not roll back automatically in this transaction; use an outbox/downstream idempotency.

The goal is preventing **two consumers processing the same `aggregateId` concurrently** from both thinking they are applying the next sequence.

## 10. Transactional Outbox: Commits, Ordering, and Retries

To avoid losing events when a service crashes between DB commit and publish, use a **transactional outbox**:

```text
Transaction T1
  |
  +-- update aggregate O-42
  +-- increment aggregateSequence to k
  +-- INSERT outbox(eventId, O-42, seq=k, payload, status=NEW)
  +-- COMMIT
        |
        +-- outbox relay fetches committed NEW rows
        +-- publishes to broker preserving ordering for O-42
        +-- updates send status / retries on failure
               |
               +-- consumer deduplicates, checks sequence, applies effect
```

With multiple producer instances, sequences must be issued under a consistent rule, such as optimistic locking/row locks on the aggregate when updating in the same transaction. If T1 writes event E1 and rolls back, E1 must not be sent; the relay sees only committed outbox rows.

**An outbox does not automatically guarantee ordering if the relay is implemented carelessly.** Typical mistakes:

- Two relays reading the same aggregate and processing outbox rows in parallel: E2 can be sent/acked before E1.
- Using `SELECT ... FOR UPDATE SKIP LOCKED` without enforcing per-aggregate ordering: a second worker can skip a locked E1 and send E2.
- Retrying E1 with a long backoff while letting E2 overtake it when the business requires strict order.
- Sorting by application timestamps from multiple hosts: clocks do not yield reliable business ordering.
- Sorting `ORDER BY id` across the whole table when IDs do not reflect commit order or per-aggregate sequence assignment.
- Publishing to different partitions/queues and expecting the broker to preserve global order.

If strict per-aggregate ordering is required, the relay needs **at most one active send stream per key** or controlled version/gap buffering and ACK policies. In exchange, per-aggregate throughput has a ceiling; independent aggregates can still run in parallel.

### Example Outbox Structure

```sql
CREATE TABLE outbox_events (
    event_id VARCHAR(80) PRIMARY KEY,
    aggregate_id VARCHAR(80) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json CLOB NOT NULL,
    status VARCHAR(20) NOT NULL,
    UNIQUE (aggregate_id, aggregate_sequence)
);
```

This is **illustrative DDL**; adjust types/indexes, retention, and transaction isolation for the real database. `UNIQUE (aggregate_id, aggregate_sequence)` prevents two events of the same aggregate from receiving the same sequence number, yet **does not assign sequences properly on its own** and **does not stop E2 from overtaking E1 in the relay**. Matching write and dispatch algorithms are required.

Track `eventId`, retry counts, next attempt times, failure reasons, processing states, and the case where a message was sent to the broker yet the worker crashed before marking completion. Consumers must be idempotent because outbox relays can resend duplicates.

## 11. Ordering Through Brokers: Keys, Partitions, and Limits

With a message broker supporting ordering within **a specific partition/queue**, you can route all events for **the same aggregate** using the same key:

```text
key = orderId
event = { eventId, orderId, aggregateSequence, eventType, payload }
```

However, separate the conditions:

1. The producer/relay must **send in the aggregate's exact sequence**; a broker cannot fix out-of-order sends from the producer.
2. Events sharing the same key must route to **the same ordering lane/partition** in the chosen configuration.
3. Consumers must process sequentially, or ensure they do not commit offsets/acks past an event whose dependency has not finished.
4. With async callbacks or multiple worker threads inside the same partition, **side-effect completion order** can still diverge from broker delivery order.
5. Retries, rebalances, redeliveries, DLQs, and restarts can introduce duplicates or gaps that must be handled.
6. Brokers do not provide a usable total order across **different partitions/aggregates**.

Thus "same Kafka partition" (or an equivalent sequential queue in another system) is only **one piece** of the contract. In many cases, sequence checks and idempotent consumers are still necessary.

If B depends on event A from **two different aggregates**, grouping by `orderId` alone does not resolve cross-aggregate dependencies; use a workflow coordinator/saga or durable join state tracking both conditions.

## 12. Handling Errors, Timeouts, and Retries Without Breaking Ordering

A dependent step can fail:

```text
OrderSubmitted
  |
  +-- ReserveInventory
        |
        +-- SUCCESS -> InventoryReserved -> proceed to Payment
        |
        +-- TRANSIENT FAILURE -> retry with backoff
        |
        +-- PERMANENT FAILURE -> ReservationFailed / compensation
```

Never emit `InventoryReserved` in `finally`, because `finally` runs **even when reservation fails**. Never automatically retry the **entire** already-committed order creation command just because one post-processing step failed.

Required decisions:

- **Transient error:** retry that step with backoff/jitter and attempt limits; under strict ordering, later events of the same aggregate may need to be held back.
- **Permanent error:** update failure status, dead-letter, or compensate; do not leave queues waiting forever with no signal.
- **Duplicate message:** `eventId`/idempotency key; duplicate side effects must be prevented or harmless.
- **Ambiguous timeout:** an external call may have succeeded even though the client timed out; retries must use an idempotency key or verify remote state.
- **Process crash:** state and pending work must be persisted durably if recovery is required; in-RAM latches/`CompletableFuture`s are insufficient.
- **Executor rejection:** `TaskRejectedException` or another rejection policy occurs when pools/queues fill up; the event may have been published yet the handler was never admitted to the pool.
- **Async exception:** errors in `@Async void` do not normally propagate to the publisher; configure `AsyncUncaughtExceptionHandler`, metrics, and recovery.
- **Ordering policy:** explicitly decide between "block all subsequent events after E1 fails" vs. "allow independent events to pass E1"; base it on the dependency graph rather than imposing a global total order blindly.

**Trade-off:** strict ordering can cause **head-of-line blocking** — E1 failing stalls E2/E3 on the same aggregate. That may be right when E2 truly requires E1, yet independent events should not be forced into the same queue unnecessarily.

## 13. Context, Threads, and Event Payloads

Events used by async listeners or brokers should carry **immutable payloads**:

```java
public record InventoryReserved(
        String eventId,
        String orderId,
        String reservationId,
        long aggregateSequence) {}
```

This is a **separate illustrative definition**, not replacing the minimal record in section 5's runnable example.

Avoid putting directly into events:

- Mutable JPA entities, Hibernate lazy proxies, or `EntityManager`;
- `HttpServletRequest`, `HttpSession`, `MultipartFile`/request streams;
- `SecurityContext`, live `ThreadLocal`s, MDC, or thread-bound connections;
- `List<MutableLine>` where the record merely holds references to mutable elements.

`@Async` does not automatically propagate imperative transactions, request contexts, or logging contexts; if correlation/tenant/user IDs are needed for business logic, capture **validated values** into an immutable DTO at publish time. Consider `TaskDecorator`/context propagation for observability, without using it to extend Servlet request lifecycles.

An immutable payload ensures B receives **consistent data matching the captured contract**, without guaranteeing commit or delivery order on its own. Keep responsibilities separated.

## 14. How to Test Ordering Reliably

### 14.1. Tests Without Arbitrary Timers

Never do:

```java
publishEvent(A);
Thread.sleep(100);
assertTrue(bFinished);
```

This is a **counterexample**. CI machines can be slower, executors busier, or schedulers pick different threads. A better pattern uses `CountDownLatch`, `Phaser`, futures with timeouts, or a test executor whose ordering you control.

The example in section 5 proves the exact problem with latches:

- Hold worker A in an incomplete state;
- Prove a handler listening to the same event with a higher `@Order` can still run;
- Release worker A;
- Await `InventoryReserved` and verify B sees only `inventoryDone=true`.

### 14.2. Testing Failure of Step A

Create an inventory service that intentionally fails:

```text
OrderSubmitted -> InventoryReservationFailed
```

Assert **no** `InventoryReserved` and **no** `InvoiceRequested`. If the application has retries, verify retry attempts and final state rather than just asserting a single exception.

### 14.3. Testing Transactions and Rollbacks

When publishing event B depends on DB commit:

- Publish event inside transaction T1, commit T1: B is emitted along the designed path.
- Publish event inside T1 then roll back: no "committed" event may reach downstream.
- With `@TransactionalEventListener(AFTER_COMMIT)`, if the test is wrapped in Spring Test's default-rollback `@Transactional`, the callback won't run automatically; use `TestTransaction.flagForCommit()` and `TestTransaction.end()` to test the real commit milestone.
- Post-commit tests should check real DB state or a durable outbox, not infer from log order.

### 14.4. Testing Per-Aggregate Contention

Create two workers receiving E1/E2 of the same `aggregateId`, intentionally delaying E1 so E2 arrives first. Assert the consumer **does not apply E2 ahead of E1** when the contract requires contiguous sequences. Check:

1. An already-processed `eventId` does not recreate side effects on redelivery.
2. E2 with `sequence=2` waits/is deferred if `lastAppliedSequence=0`.
3. Only after E1 applies and commits can E2 apply.
4. Two workers trying to process one event cannot both commit side effects when proper unique constraints/locking are used.
5. When E1 cannot be processed, there is DLQ/gap alerting/compensation instead of waiting forever.
6. Events of **different** `aggregateId`s can still run in parallel up to capacity.

### 14.5. Fault-Injection Tests for Outbox/Brokers

Scenarios:

| Fault | What to verify |
| --- | --- |
| T1 rolls back | No committed outbox row sent to broker |
| Crash after T1 commit before relay | Outbox row remains and is recovered |
| Crash after publish before marking SENT | May resend duplicate; consumer is idempotent |
| E1 retries while E2 waits | Per-aggregate ordering policy holds |
| Consumer receives E2 before E1 | Detects gap, defers, or reconciles per contract |
| Two relays run in parallel | Does not break send order for the same aggregate |
| Worker thread pool full | Does not treat rejected events as processing success |
| Rebalance/restart | Dedupe/progress state persists and recovers |

An integration test using only `@RecordApplicationEvents` can prove an event was published by Spring; it **does not prove** all async listeners finished, the DB committed, or the broker preserved order. Tests must observe the exact boundary you want to guarantee.

## 15. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@Order(10)` listener runs before `@Order(0)` finishes | Earlier listener uses `@Async` or only submits a task | Have B listen to A's result event, or call services sequentially |
| Event E2 published after E1 finishes before E1 | Multi-worker executor, varying service times | Serialize by key or wait for completion under the right condition |
| Switching executor to one thread still breaks business ordering | Multiple producers submit out of sequence or nested async side effects | Transaction-issued versions/sequences, state machine |
| B reads DB yet doesn't see A | A hasn't committed or worker runs in a different transaction | `AFTER_COMMIT` or outbox, do not rely on dispatch |
| `AFTER_COMMIT` listener B doesn't run | Event B published outside a transaction with `fallbackExecution=false` | Publish inside an active transaction or adjust listener design |
| E2 overwrites newer/correct state | E2 arrives out of order or update lacks version check | Atomic sequence/version check |
| Multi-relay outbox reorders events | Concurrent workers/`SKIP LOCKED` bypasses E1 | Per-key ordered relay, gap/sequence validation |
| Same Kafka partition yet side effects reorder | Consumer pushes messages into a pool and processes concurrently | Serialize processing per key; ack/commit after the right boundary |
| Duplicate events after retries | Relay crashes after publish; broker redelivery | `eventId`, idempotent consumer, and unique constraints |
| Needs both Inventory and Payment yet invoice fires too early | Listening to only one event or non-atomic flag checks | Durable join state and atomic transitions |
| Chain stalls while publisher sees no error | `@Async void` exception on worker | Async error handler, metrics, failure event/state, retries |
| Events lost after JVM crash | Using only in-RAM Spring Application Events | Transactional outbox or durable queue |
| Ordering test occasionally fails | `sleep` or asserting immediately after async publish | Latches/futures/controlled executor with timeouts |

## 16. Ordering Design Checklist for Dependent Events

Before shipping a dependent event chain to production:

- [ ] Is "order" defined as **publish, invocation, completion, commit, or consume**?
- [ ] **Which milestone of A** does B depend on: started, operation finished, or committed?
- [ ] Is `@Order` mistakenly assumed to guarantee completion of `@Async`?
- [ ] Is there an `ACompleted`/`ACommitted` event emitted **only after A succeeds**?
- [ ] If A and B share one DB transaction, would sequential service calls be better than building a complex event chain?
- [ ] If A is external, are timeouts, idempotency, retries, and compensation defined?
- [ ] If the workflow has multiple preconditions, are there a durable join state and atomic transitions?
- [ ] With multiple instances, is `aggregateId` chosen as the ordering key and are sequences issued properly?
- [ ] Does the outbox relay prevent E2 from overtaking E1 for the same aggregate?
- [ ] Does the consumer persist deduplication, gap detection, and `lastAppliedSequence` durably?
- [ ] Are broker/queue/worker ordering boundaries understood correctly (per partition/key, not global)?
- [ ] Are races tested with latches and fault injection for retries/crashes?
- [ ] When ordering causes head-of-line blocking, are SLOs, alerts, and stuck-event remediation defined?

**Summary:** In Spring Framework Application Events, `@Order` only sorts **listener invocation** within a dispatch context; with `@Async`, it cannot guarantee the prior task finished. When events have dependencies, emit an event **marking successful completion of the prior step**, make the next step listen specifically to that event, or use an orchestrator/state machine for multiple conditions. When work must survive commits, crashes, multiple instances, and retries, add a **transactional outbox, per-aggregate sequences, ordered processing, and idempotent consumers**. Never confuse invocation order with business outcome correctness.

## References

- [Spring Framework 6.2 — ApplicationContext Events, `@Order`, and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — `TransactionPhase.AFTER_COMMIT` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Transactional Outbox Pattern — microservices.io](https://microservices.io/patterns/data/transactional-outbox)

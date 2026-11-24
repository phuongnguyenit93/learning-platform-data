# Snapshotting Data at Event Publication Time in Spring Framework

## 1. The Problem: Should an Event Hold Data from *Publication Time* or Mutable Live Data?

When publishing an application event via `ApplicationEventPublisher.publishEvent(...)`, an important design question arises: **what point in time should the listener observe the business state at?** If a listener directly receives an entity or domain object that is still mutating, it may observe a different state from the one present when the publisher emitted the event—especially when the event is processed asynchronously, queued, or stored for later processing.

A **snapshot payload** is a representation of data captured at a specific point in time, sufficient to describe the event and **unaffected when the source object continues to change**. Typically, a snapshot is an immutable DTO/record containing the required values rather than a direct reference to a JPA entity, collection, or service.

For example: an order currently has status `CREATED` and one order line with quantity `1`. The service creates an `OrderSnapshotEvent` containing the ID, status, version, timestamp, and copied lines, then calls `publishEvent(...)`. Afterward, the order is updated to `PAID` with quantity `9`. A listener processing the earlier snapshot must still see `CREATED` and quantity `1`, because that is the published event data.

Principles:

- **Capture time** is when the application **creates the snapshot**, typically right before `publishEvent()`; not when the listener executes.
- **Immutability** is a property of **the entire data graph inside the payload**, not merely the outermost wrapper object.
- **A snapshot is distinct from the latest state**: listeners should not assume a snapshot always reflects the most recent DB state.
- **Publishing an event is distinct from committing a transaction**: `publishEvent()` does not by itself guarantee that the current transaction commits successfully.
- **Event timestamp is distinct from data version**: timestamps aid diagnostics, whereas versions/sequences control updates and business ordering.

This lesson belongs to the payload design group for **Spring Framework Application Events**. The main example uses plain Spring Framework without depending on Spring Boot, JPA, or a message broker.

## 2. Risks of Passing Mutable Objects

Consider the following way of publishing an event:

```java
public record OrderUpdatedEvent(OrderEntity order) {}

publisher.publishEvent(new OrderUpdatedEvent(order));
// Other code can still modify order after the event is published.
```

This is an **illustrative snippet**; `OrderEntity`, `order`, and `publisher` are supplied by the application.

The `OrderUpdatedEvent` record only makes the **`order` field reference** immutable. It does **not** make `OrderEntity` itself immutable. If the entity is mutated:

```java
order.setStatus("PAID");
```

then a listener holding the event can observe the new status when reading `event.order().getStatus()`.

This publishing pattern easily produces subtle bugs:

1. **Async race:** the event is submitted to an executor when status is `CREATED`, but the worker thread reads the object after the publisher has set status to `PAID`.
2. **Post-publish mutation:** even a synchronous listener might retain the event for later use; when read again, the reference points to the new state.
3. **JPA lazy loading:** an entity/proxy tied to an `EntityManager` or persistence context may no longer be usable on another thread, causing lazy attribute access failures or transaction-dependency errors.
4. **Inconsistent data:** a listener reads individual fields at different moments while multiple threads modify the object, forming a combination of values that never existed as a valid business state.
5. **Excessive data exposure:** passing the entire entity graph can leak sensitive data or create tight coupling between publisher and consumer.
6. **Hard to reproduce events:** an event holding a mutable reference is not a historical record; later logs/debugging may not reflect the exact moment the event was emitted.

Even with the default synchronous `@EventListener`, passing an entity directly still makes payloads hard to reuse, hard to test, and fragile if configuration later switches to async.

## 3. Designing an Immutable Snapshot Payload

An example suited for Java 17:

```java
public record OrderLineSnapshot(String sku, int quantity) {}

public record OrderSnapshot(
        String orderId,
        String status,
        long version,
        Instant capturedAt,
        List<OrderLineSnapshot> lines) {

    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}

public record OrderStatusChangedEvent(OrderSnapshot snapshot) {}
```

This is an **illustrative definition snippet** (requiring imports for `java.time.Instant` and `java.util.List`); a complete runnable program is in section 5.

Each field serves a specific purpose:

| Field | Role |
| --- | --- |
| `orderId` | Aggregate identifier so consumers know which business object changed |
| `status` | Concrete business value at capture time |
| `version` | Aggregate change version/sequence; useful for detecting stale, duplicate, or out-of-order events |
| `capturedAt` | Timestamp when the application created the snapshot, aiding logging and analysis |
| `lines` | Copy of data needed by listeners, composed of immutable `OrderLineSnapshot`s |
| `OrderStatusChangedEvent` | Event name expressing a business fact recorded at publication time |

**Why isn't `record` alone enough?** A record only prevents reassigning fields on the record instance. With a field of type `List<MutableLine>`, the list may change and the `MutableLine` instances inside can still be modified. `List.copyOf(lines)` protects **the list structure from direct additions/removals** but only performs a **shallow copy**. If elements remain mutable, changes to elements will still surface through the snapshot.

Therefore, the payload above combines:

- `OrderLineSnapshot` contains only `String` and `int`, both having immutable semantics.
- `OrderSnapshot` stores a `List.copyOf(...)` list.
- `Instant` is an immutable type, safe to hold inside a record.
- No `EntityManager`, `OrderEntity`, `MutableLine`, `InputStream`, `Connection`, or live stateful objects are stored in the payload.

Immutability checks can be strengthened with `Objects.requireNonNull` and input validation. If an element in `lines` contains deeply nested objects such as `Map<String, List<MutableLine>>`, consider **recursive defensive copying** for that data. Never call an object "immutable" merely because its outermost class has `final` fields.

## 4. Event Flow: Create the Snapshot Before or After `publishEvent()`?

Recommended pattern:

```text
Business thread (publisher)
  |
  +-- has aggregate needing to publish event
  |
  +-- reads necessary values
  +-- creates immutable DTOs / snapshot (time T0)
  +-- creates event pointing to immutable snapshot
  |
  +-- publishEvent(event)
        |
        +-- synchronous @EventListener may run immediately on publisher thread
        |
        +-- @Async @EventListener may be submitted to an executor
        |
        +-- @TransactionalEventListener may register a transaction callback
  |
  +-- aggregate continues changing or transaction continues processing
        |
        +-- snapshot in the event still describes T0
```

Spring Framework dispatches Application Events synchronously by default via the default multicaster. However, **the `publishEvent()` API itself does not promise that all listeners execute synchronously or immediately**: the multicaster may be configured with an executor, a method may use `@Async`, or a listener may be bound to a transaction phase.

The snapshot must be formed **before the event handoff point**. Passing a `Supplier<OrderEntity>` or `() -> entity.getStatus()` merely **defers reading**, rather than capturing a snapshot; by the time the supplier executes, the data may have changed. Similarly, putting an entity onto a queue and converting it to a DTO only on the worker thread is too late to guarantee preserving the state at publication time.

On the other hand, capturing a snapshot from an aggregate being concurrently modified **does not automatically guarantee an atomic state**. To avoid a "torn snapshot", read consistently along the aggregate boundary: use the same lock for in-memory data, transaction/locking and versioning for DB data, or construct the event from **the change values already determined within a single business operation**. `List.copyOf(...)` does not replace synchronization when the source collection is being modified concurrently.

## 5. Runnable Java 17+ Example: Immutable Snapshot vs. Mutable Reference

The following example uses **Spring Framework 6.2.12** and Gradle 8+, without Spring Boot. We publish **two events**:

- `OrderSnapshotEvent` holds an **immutable copy** of the order before mutation.
- `OrderReferenceEvent` holds a **reference to the mutable aggregate** to demonstrate what not to do.

A default synchronous Spring listener stores both events. After the publisher mutates the aggregate, the program prints the stored data to prove the snapshot preserves the old state while the reference sees only the new state.

### 5.1. Project Structure

```text
spring-event-snapshot-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SnapshotEventDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-event-snapshot-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.SnapshotEventDemo'
}
```

### 5.2. File `src/main/java/demo/SnapshotEventDemo.java`

```java
package demo;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SnapshotEventDemo {

    // Value objects containing only immutable values.
    public record LineSnapshot(String sku, int quantity) {}

    public record OrderSnapshot(
            String orderId,
            String status,
            long version,
            Instant capturedAt,
            List<LineSnapshot> lines) {

        public OrderSnapshot {
            Objects.requireNonNull(orderId);
            Objects.requireNonNull(status);
            Objects.requireNonNull(capturedAt);
            lines = List.copyOf(lines);
        }

        public int firstQuantity() {
            return lines.get(0).quantity();
        }
    }

    public record OrderSnapshotEvent(OrderSnapshot order) {}

    // Control event: a record wrapper that holds a mutable reference.
    public record OrderReferenceEvent(MutableOrder order) {}

    public static final class MutableLine {
        private final String sku;
        private int quantity;

        public MutableLine(String sku, int quantity) {
            this.sku = sku;
            this.quantity = quantity;
        }

        public String sku() {
            return sku;
        }

        public int quantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }
    }

    public static final class MutableOrder {
        private final String id;
        private String status = "CREATED";
        private long version = 1;
        private final List<MutableLine> lines = new ArrayList<>();

        public MutableOrder(String id) {
            this.id = id;
            lines.add(new MutableLine("BOOK", 1));
        }

        public String status() {
            return status;
        }

        public long version() {
            return version;
        }

        public int firstQuantity() {
            return lines.get(0).quantity();
        }

        public int lineCount() {
            return lines.size();
        }

        // Capture operation: create independent value objects without putting
        // MutableLine or List<MutableLine> directly into the event.
        public OrderSnapshot snapshot(Instant at) {
            List<LineSnapshot> copied = lines.stream()
                    .map(line -> new LineSnapshot(line.sku(),
                                                   line.quantity()))
                    .toList();

            return new OrderSnapshot(id, status, version, at, copied);
        }

        public void markPaid() {
            status = "PAID";
            version++;
            lines.get(0).setQuantity(9);
            lines.add(new MutableLine("PEN", 2));
        }
    }

    public static final class SnapshotObserver {
        private OrderSnapshotEvent snapshotEvent;
        private OrderReferenceEvent referenceEvent;

        @EventListener
        public void onSnapshot(OrderSnapshotEvent event) {
            snapshotEvent = event;
        }

        @EventListener
        public void onReference(OrderReferenceEvent event) {
            referenceEvent = event;
        }

        public OrderSnapshot savedSnapshot() {
            return snapshotEvent.order();
        }

        public MutableOrder savedReference() {
            return referenceEvent.order();
        }
    }

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;
        private final MutableOrder order = new MutableOrder("O-100");

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void publishThenChange() {
            Instant fixedTime = Instant.parse("2026-01-01T00:00:00Z");
            OrderSnapshot snapshot = order.snapshot(fixedTime);

            publisher.publishEvent(new OrderSnapshotEvent(snapshot));
            publisher.publishEvent(new OrderReferenceEvent(order));

            System.out.println("at publish: " + format(snapshot.status(),
                    snapshot.version(), snapshot.firstQuantity()));

            // The source data changes after both events have been published.
            order.markPaid();
        }

        public MutableOrder currentOrder() {
            return order;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        SnapshotObserver snapshotObserver() {
            return new SnapshotObserver();
        }

        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    private static String format(String status, long version, int qty) {
        return status + "/" + version + "/" + qty;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService service = context.getBean(OrderService.class);
            SnapshotObserver observer =
                    context.getBean(SnapshotObserver.class);

            service.publishThenChange();

            OrderSnapshot saved = observer.savedSnapshot();
            MutableOrder reference = observer.savedReference();
            MutableOrder current = service.currentOrder();

            System.out.println("current: " + format(current.status(),
                    current.version(), current.firstQuantity()));
            System.out.println("snapshot: " + format(saved.status(),
                    saved.version(), saved.firstQuantity()));
            System.out.println("reference: " + format(reference.status(),
                    reference.version(), reference.firstQuantity()));
            System.out.println("line counts: snapshot="
                    + saved.lines().size() + ", current="
                    + current.lineCount());

            boolean listIsUnmodifiable = false;
            try {
                saved.lines().add(new LineSnapshot("NEW", 1));
            } catch (UnsupportedOperationException ex) {
                listIsUnmodifiable = true;
            }
            System.out.println(
                    "snapshot list unmodifiable=" + listIsUnmodifiable);
        }
    }
}
```

Run on JDK 17+ with Gradle installed:

```bash
gradle -q run
```

Lines printed by the program (ignoring build tool messages, if any):

```text
at publish: CREATED/1/1
current: PAID/2/9
snapshot: CREATED/1/1
reference: PAID/2/9
line counts: snapshot=1, current=2
snapshot list unmodifiable=true
```

### 5.3. Explaining the Output

1. `AnnotationConfigApplicationContext` creates the Spring beans and registers `@EventListener` methods. `ApplicationEventPublisher.publishEvent(Object)` supports events that are ordinary Java records; Spring can wrap the payload in `PayloadApplicationEvent` for type-based dispatching.
2. `OrderService` captures `OrderSnapshot` at `Instant.parse(...)`. The fixed timestamp in the example keeps output reproducible; real applications typically use `Clock.instant()` or `Instant.now()` from an injected clock.
3. Both events are published while the source state is `CREATED`, version `1`, first quantity `1`. The synchronous listener saves them, but **saving a reference** is not **copying data**.
4. `order.markPaid()` changes the status to `PAID`, increments version to `2`, updates quantity to `9`, and adds a new order line.
5. `savedSnapshot()` remains `CREATED/1/1` with only one line because the payload holds immutable DTOs.
6. `savedReference()` reads an old `MutableOrder` variable that still points to the same instance as `currentOrder()`, thus seeing `PAID/2/9` and two lines.
7. `List.copyOf(...)` protects the list inside `OrderSnapshot`. Attempting `add(...)` on the snapshot list throws `UnsupportedOperationException`, so the program prints `snapshot list unmodifiable=true`.

Although the example uses **synchronous** listeners to keep output deterministic, the same reference hazard is even more significant with `@Async`, an executor on the event multicaster, or a queue mechanism. With async listeners, execution order and read timing may differ; **do not** use `Thread.sleep(...)` to prove snapshotting. Use `CountDownLatch`, `CompletableFuture`, or synchronization test utilities with timeouts.

**Example limitation:** `MutableOrder.snapshot(...)` reads an object manipulated by a single thread in the demo. In systems with concurrent updates, code must ensure consistent capture via synchronization/transactions/versioning rather than merely adding `List.copyOf(...)`.

## 6. Deep Copying and Defending Against Mutable Data

A very common trap:

```java
record WrongPayload(List<MutableLine> lines) {
    WrongPayload {
        lines = List.copyOf(lines);
    }
}
```

This is illustrative code, requiring the `MutableLine` type as in the example above. The `WrongPayload.lines()` list disallows `add/remove`, but if an inner `MutableLine` has `setQuantity(9)` called on it, the content seen through the event still changes.

Three levels of protection must be distinguished:

| Technique | What Does It Protect? | What Does It Not Protect? |
| --- | --- | --- |
| `final` field or Java record | Prevents reassigning the field | The object pointed to by the field can still be mutable |
| `List.copyOf(...)` / `Map.copyOf(...)` | Prevents directly modifying the collection structure in the payload; creates an unmodifiable resulting collection | Does not make elements/values inside immutable |
| Converting each element to an immutable DTO/record | The content state of each element is captured by value | Does not by itself guarantee an atomic snapshot if the source mutates concurrently |

Proper example with a collection:

```java
List<LineSnapshot> lines = entity.getLines().stream()
        .map(line -> new LineSnapshot(
                line.getSku(), line.getQuantity()))
        .toList();

OrderSnapshot snapshot = new OrderSnapshot(
        entity.getId(),
        entity.getStatus(),
        entity.getVersion(),
        clock.instant(),
        lines);
```

This is **illustrative code**; `entity`, `clock`, and the getters belong to the application, not a standalone program. `List.copyOf(...)` in the record constructor guards against callers passing a list that might still be mutated. Still, avoid accessing lazy JPA relations outside a transaction or persistence context; normally map DTOs inside an active transaction/persistence context or use a query projection to fetch the exact data.

If the payload contains `Date`, `byte[]` arrays, `ArrayList`, `HashMap`, mutable POJOs, or deeply nested structures, perform defensive copying in the **constructor** and when **returning data** if mutable components are re-exposed. For example, a byte array must be cloned on receipt and return; switch to `String`/`Instant`/immutable value objects where appropriate. `Collections.unmodifiableList(original)` is only a **view** disallowing modification through that view, while the `original` list can still be modified elsewhere; it is not equivalent to an independent snapshot.

## 7. A Snapshot Must Be Taken in a Consistent State

A payload whose fields are immutable after creation can still be **wrong at creation time** if read from an inconsistent source.

Dangerous example:

```text
Thread A: reads status = PAID
Thread B: updates version = 8, status = CANCELLED
Thread A: reads version = 8
Thread A: creates event (PAID, version 8)
```

In the real system, no valid state `(PAID, 8)` may ever exist. The immutable event merely freezes an **inconsistent** set of values.

Options depend on architecture:

- **In-memory aggregate:** synchronize concurrent mutation and capture; for instance, use the same lock/`synchronized` block or a single-thread ownership strategy.
- **JDBC/JPA transaction:** capture business values within a single transaction and appropriate isolation level. When using optimistic locking with `@Version`, the event version should match the meaningful aggregate version after the update.
- **Reading from multiple tables or sources:** consider consistent query projections, snapshot isolation, or transaction-scoped coordination; do not assume separate queries reflect a single global point in time.
- **Creating events from determined commands/results:** after applying business changes, construct value objects from the already-decided data before leaving the business boundary, rather than re-reading a live object from another thread.

A practical way to reduce races with JPA: inside a `@Transactional` service scope, update the entity, determine the values to publish, map them to immutable DTOs, and then publish the event. However, the transaction may still roll back or fail to commit later, so post-commit listeners or an outbox remain necessary if consumers must only act once data is committed.

**`capturedAt` is not a locking mechanism.** Even when timestamps use `Instant.now()`, you cannot rely solely on two clocks across two different services for exact global ordering. When stale, duplicate, or out-of-order detection is needed, design `aggregateVersion`, `eventId`, or a stable sequence.

## 8. Events Published Before Commit: A Snapshot Does Not Guarantee Successful Persistence

Suppose there is a method:

```java
@Transactional
public void confirmOrder(Order order) {
    order.markConfirmed();
    publisher.publishEvent(new OrderConfirmedEvent(
            toSnapshot(order)));
    // An error may occur here, causing the transaction to roll back.
}
```

This is illustrative code (assuming types and helpers are defined in the application).

The snapshot describes data at event publication time, yet the transaction can roll back. In that case:

- A synchronous `@EventListener` may already have read the snapshot even though the DB never commits later.
- An `@Async @EventListener` may process the snapshot while the transaction is still open and while the DB on another thread does not yet see the data.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` is invoked only after the event's transaction **commits successfully**, provided the event was published inside an appropriate transaction.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)` reacts on the rollback branch, not a "committed" event.
- An `AFTER_COMMIT` snapshot is still **the value captured before commit**, not automatically refreshed by Spring to the final DB read.
- By default, `@TransactionalEventListener` does not execute if an event is published **without a transaction** (unless `fallbackExecution = true`).

For operations like sending emails or calling external systems only once data is committed, choosing `AFTER_COMMIT` is the right step regarding **timing**. Yet it is not a **durable delivery** guarantee: if the process dies after the DB commit and before event handling completes, in-memory work can be lost. Guaranteed delivery requires a **transactional outbox** or equivalent design.

### Snapshots and the Transactional Outbox

When a snapshot must be reliably delivered to a broker or another consumer:

```text
@Transactional service
    +-- update aggregate
    +-- create snapshot / event payload with eventId
    +-- write outbox row containing snapshot payload (same transaction)
    +-- commit
           |
           +-- outbox worker reads committed row
           +-- send to broker / external system
           +-- mark completed, retry on failure
```

Here the payload is persisted in the same transaction as the business data; if the transaction rolls back, the outbox record rolls back too. The worker processes after commit and requires **idempotency**, retries, and status tracking. Never infer that `@TransactionalEventListener(AFTER_COMMIT)` alone provides retry/durability equivalent to an outbox.

If consumers need **the state at the moment the business action occurred**, the outbox should store the **snapshot payload** in the same transaction, rather than storing only an ID and re-reading the current `order` seconds later (since the record may have changed further). If consumers only need to process **the latest state**, sending an ID and re-querying may be the better choice. These two semantics must be decided explicitly.

## 9. Choosing the Payload: ID, Delta, or Full Snapshot?

Not every event needs to carry all data.

| Payload Style | Example | Pros | Trade-offs |
| --- | --- | --- | --- |
| **ID-only** | `OrderChanged(orderId)` | Lightweight, minimal data leakage, low schema coupling | Listener must look up data and may see a state *newer* than publication time |
| **Delta / fact** | `OrderStatusChanged(orderId, oldStatus, newStatus, version)` | Expresses exact change, small payload | Listener may need prior state or must apply events in exact order |
| **Snapshot** | `OrderSnapshot(id, status, lines, version, capturedAt)` | Self-contained for history, async, messaging | Larger payload, requires versioning and data security |
| **Full entity reference** | `OrderChanged(entity)` | Easy to write initially | Mutable coupling, lazy loading, thread safety, unsuitable for storing/network transfer |

Selection rules:

- If consumers need **the exact product names and quantities at purchase time**, a snapshot covering those values is appropriate.
- If consumers only need to **refresh a screen with the latest state**, ID + re-query is usually simpler.
- If consumers must **apply state transitions**, a delta with `aggregateVersion` can avoid copying every field.
- Do not "snapshot the entire entity graph" by default: a snapshot should only include fields required by the event contract.

A good event usually expresses **what happened** (`OrderPaid`, `OrderCancelled`), not merely that a generic object changed (`ObjectUpdated`). With snapshots, the event name should make clear whether it represents pre-change state, post-business-operation state, or committed state. An event name alone does not replace documenting transaction boundaries.

## 10. Metadata: Timestamp, Version, Idempotency, and Schema

For events that need to be persisted or sent via a broker, consider an envelope:

```java
public record EventEnvelope<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        String correlationId,
        T payload) {}
```

This is an **illustrative definition**; it requires importing `java.time.Instant` and a suitable payload `T`.

These fields solve different problems:

- `eventId`: unique identifier for **each business event emission**; helps consumers prevent duplicate processing on retries.
- `eventType`: business-meaningful name, e.g., `OrderPaid`.
- `schemaVersion`: version of the **message/payload structure**, independent of the order's version.
- `aggregateId`: key identifying the order or related aggregate.
- `aggregateVersion`: version of the entity/aggregate after the business operation or per an agreed convention; aids stale-event detection and ordering.
- `occurredAt`: time the producer recorded the event; aids logs/metrics, does not replace a sequence.
- `correlationId`: links to the business request/workflow, useful for tracing.
- `payload`: immutable value snapshot or a delta with a clear contract.

**Important version distinction:** `schemaVersion=2` might indicate that a `currency` field was added, whereas `aggregateVersion=15` indicates the order has undergone a series of updates. Do not conflate these two concepts.

For messaging, events must be serialized into portable data such as JSON/Avro/Protobuf. Java records help represent data inside the JVM but **do not automatically guarantee schema compatibility across services or versions**. Test serialization/deserialization and plan backward compatibility when adding/renaming/removing fields.

When a consumer receives an event again due to a retry:

```text
eventId already processed -> skip duplicate side effect
stale aggregateVersion   -> may skip or handle per policy
new aggregateVersion     -> apply if conditions and ordering are met
```

This is an **illustrative strategy**, not a one-size-fits-all rule. Some systems must process every historical event completely rather than skipping older events; ordering contracts and idempotency must be clearly defined.

## 11. Sensitive Data and Snapshot Size

Snapshots are often stored in logs, outboxes, brokers, queues, or audit databases. Accidentally including too many fields in an event can cause data to outlive the original business record and reach multiple consumers.

Principles:

1. **Data minimization:** include only information consumers need; avoid passwords, access tokens, detailed addresses, card numbers, or unnecessary personal data.
2. **Do not rely on lazy entity graphs:** define explicit DTO projections with allowed publishable fields.
3. **Limit size:** thousands of order lines, embedded images, or large byte arrays can slow queues and inflate memory/serialization costs; for large payloads, consider ID + version + a separately stored snapshot, while preserving point-in-time semantics.
4. **Retention and deletion:** snapshots in outboxes/logs must follow retention limits and appropriate data-handling mechanisms.
5. **Schema control:** changing fields can affect multiple consumers; publish contracts, version them, and test compatibility.
6. **Do not put secrets in `toString()`:** Java records auto-generate `toString()` containing all record fields, so logging the whole event may inadvertently leak data.

Immutable snapshots reduce data-race risks, **not security risks by themselves**. Whatever is copied into an event must be treated as an API contract with its own lifecycle.

## 12. Testing Snapshots and Listeners

A valuable test suite should verify:

1. **Capture at publication time:** create an order in `CREATED` state, capture snapshot, publish event, mutate order to `PAID`; assert the snapshot remains `CREATED`.
2. **Deep immutability:** mutate the source collection, mutate source elements, attempt to mutate the snapshot's collection; verify the payload is unchanged.
3. **Self-contained business data:** consumers can operate solely from the snapshot without needing a lazy JPA entity or `EntityManager`.
4. **Concurrency:** producer updates the aggregate while capturing across multiple threads; verify consistent snapshot creation or lock/version conflict detection.
5. **Async:** `@Async` listener uses latches/futures for controlled waiting, verifying the payload stays unchanged even as the publisher continues mutating the source object.
6. **Transaction commit/rollback:** if a listener must run after commit, test both successful commit and rollback; creating an event snapshot does not mean an after-commit listener always runs.
7. **Serialization:** payloads sent via broker or outbox deserialize against the expected schema; `Instant`, enums, optional fields, and versions are handled properly.
8. **Duplicates/out-of-order arrival:** consumers use `eventId` and `aggregateVersion` per business policy without blindly overwriting newer state with an old snapshot.
9. **Sensitive data:** ensure payloads, logs, and persisted data do not contain fields beyond the allowed scope.

Example JUnit test logic without Spring (illustrative snippet):

```java
OrderSnapshot before = order.snapshot(clock.instant());
order.markPaid();

assertEquals("CREATED", before.status());
assertEquals(1, before.lines().get(0).quantity());
assertThrows(UnsupportedOperationException.class,
        () -> before.lines().add(new LineSnapshot("X", 1)));
```

This is **not a standalone program**: `order`, `clock`, JUnit imports, and records belong to the application's test context. The complete runnable Spring example is in section 5. Do not assert results of an async listener before the test awaits task completion.

### Common Pitfalls

| Symptom | Root Cause | Fix |
| --- | --- | --- |
| Listener sees new state instead of state at publication time | Event holds a mutable entity/object | Create an independent snapshot DTO/record before `publishEvent()` |
| Record still gets "mutated" indirectly | Record field holds a mutable list/map/object | Defensive copy and immutable elements, not just `final` |
| List inside event changes when source list changes | Using a `Collections.unmodifiableList(source)` view | Use an independent collection snapshot, e.g., `List.copyOf` plus deep copy |
| Snapshot contains self-contradictory fields | Producer reads source while another thread mutates it | Capture under the same lock/transaction or use consistent versioning |
| `LazyInitializationException` in async listener | Passing JPA entity/proxy across persistence context boundaries | Map necessary data to DTOs before publishing |
| Event sent externally even though transaction rolled back | Using a regular listener before commit | Use `AFTER_COMMIT` or an outbox depending on delivery requirements |
| Post-commit event has only ID, yet consumer sees newer data | Consumer re-queries DB after aggregate updated again | Send snapshot/version if business logic requires historical data |
| Snapshot sent once, but consumer processes twice | Retry / at-least-once delivery | Event ID, idempotency key, and safe duplicate handling |
| Old event overwrites new state | Missing sequence or version validation | Use `aggregateVersion` and ordering rules |
| Payload too large or leaks data | Copying entire entity graph, including secrets | Design minimal DTOs, retention, schema, and security |

## 13. Pre-Publication Checklist

Before calling `publishEvent(...)`, ask yourself:

- **What moment should the data reflect?** When the command was accepted, after in-memory changes, after flush, or after commit?
- **Does the consumer need a past fact or the latest state?** If past, snapshot; if latest, ID + re-query may fit better.
- **Is the payload isolated from mutable objects?** Have collection elements and nested objects also been properly copied?
- **Is capture consistent?** Does a transaction/lock/version cover all fields?
- **Does the event have sufficient identity/version/timestamp?** For tracing, idempotency, ordering, and schema evolution.
- **Are there commit constraints?** If the listener may only trigger external effects after commit, design a transaction-phase listener or outbox.
- **Is there sensitive data or unnecessary payload bloat?** Publish only required fields.
- **Have post-publish mutations been tested?** Prove the snapshot stays unchanged even as the source aggregate continues living and mutating.

**In summary:** A snapshot payload is **an immutable value capture independent of the source object at the time the publisher creates the event**. Use Java records/value objects combined with defensive copying to preserve data at publication time, and avoid putting mutable JPA entities directly into events. Capture consistency, transaction outcome, delivery ordering, and failure recovery are **separate** responsibilities requiring explicit design.

## References

- [Spring Framework — ApplicationContext Events, `@EventListener` and asynchronous listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html)
- [Java SE 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))

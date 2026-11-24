# Passing Identifiers or Immutable Data Instead of Session-Bound Entities

## 1. The Problem: A JPA Entity Is Not a Thread-Safe Message

In a Spring application, a transaction typically opens a persistence context to fetch JPA entities via an `EntityManager` or Hibernate `Session`. On the request thread, code loads `OrderEntity` from a repository, mutates its state, and then wants to publish an event or pass the entity to an `@Async` method. The seemingly convenient approach:

```java
// Anti-pattern, not a standalone Java program.
@Transactional
public void approve(long orderId) {
    OrderEntity order = repository.findById(orderId).orElseThrow();
    order.approve();
    backgroundWorker.notifyCustomer(order); // Passing a managed entity.
}
```

Yet `backgroundWorker` may run on another thread while the caller's transaction has not committed, has rolled back, or after the persistence context has closed. An entity can hold lazy proxies, uninitialized collections, mutable state, and references to a large object graph. **A managed entity is not a data contract designed to cross transactions, threads, processes, or message brokers.**

The goal of this lesson in the **Transactions and Events** group of **Spring Framework - concurrency**: **pass identifiers (IDs) or immutable data (immutable snapshots/DTOs) instead of entities bound to a persistence context** across asynchronous boundaries.

After finishing this lesson, you should be able to:

1. Explain managed, detached, lazy associations, dirty checking, and why `Session`/persistence contexts are not thread-safe.
2. Understand why `@Async` does not automatically transfer the caller's transaction, `EntityManager`, or Hibernate session to the worker.
3. Choose between **passing an ID and reloading**, **passing an immutable snapshot**, and **passing an ID plus version** according to consistency needs.
4. Know how to build a snapshot **while the context is still valid**, without accidentally touching lazy associations on the worker.
5. Apply Spring `@TransactionalEventListener(phase = AFTER_COMMIT)` within its proper scope; distinguish post-commit events from durable queues.
6. Use `@Version`/optimistic locking or conditional updates when stale jobs must not overwrite newer state.
7. Recognize the limits of `List.copyOf` and `record`: an immutable outer reference does not automatically make a deep object graph immutable.
8. Work with runnable Java 17+ examples, illustrative Spring/JPA structures, and a concurrency testing plan.

**Main message:** passing an entity reference to another thread passes only **a reference**; it does not pass a live transaction, clone state, or grant permission to use the persistence context from another thread.

## 2. What Does a Persistence Context Actually Manage?

A JPA persistence context tracks entities and their relationships within a unit of work. A Hibernate `Session` provides a persistence context and typically handles:

- **Identity map / first-level cache:** within a context, one entity row by identifier has one corresponding managed representation.
- **Dirty checking:** Hibernate detects changes on managed entities and synchronizes them to the database at the appropriate flush/commit.
- **Lazy loading:** an association may be represented by an uninitialized proxy or collection; accessing it may require a live context/session.
- **Unit of work:** operations are coordinated within a configured transaction/flush scope.
- **Lifecycle:** a context can be transaction-scoped, extended, or application-managed; it does not live for the entire JVM lifetime by default.

In a typical Spring Data JPA setup, the transaction-bound `EntityManager` is managed per transaction scope and thread context. An entity fetched inside a transaction is **managed** at that moment. Once the context closes, the entity becomes **detached**; accessing already-loaded fields may still work, whereas accessing unloaded lazy associations can throw `LazyInitializationException` under Hibernate.

### 2.1. Four Basic JPA Entity States

| State | Description | Risk when handed to a background worker |
| --- | --- | --- |
| `new/transient` | New object, not yet attached to a persistence context | No dirty checking; ID may not be assigned yet |
| `managed` | Object attached to a persistence context | Non-thread-safe graph/session sharing; data may be uncommitted |
| `detached` | Entity that was managed but is no longer attached to that context | Unloaded lazy fields can fail, data may be stale, mutations do not auto-flush |
| `removed` | Entity marked for deletion in the context | Worker may observe state no longer valid after commit/rollback |

**Distinction needed:** an entity reference **passed** to a worker does not instantly become detached merely by changing threads. The entity may still be managed in **the caller's context**. The problem is that the context/Session is not designed for concurrent use from multiple threads; once the context ends, the reference becomes detached.

### 2.2. Session Is Not Thread-Safe

The Hibernate User Guide explicitly states that `Session`/`EntityManager` and persistence contexts are **not thread-safe**. Never hand the same real `EntityManager`/`Session` to multiple workers, and never let workers concurrently mutate the same managed entity graph inside one context.

An important nuance: the `EntityManager` bean injected by Spring via `@PersistenceContext` in many real setups is a **shared transactional proxy** that is safe to *inject* into multiple Spring services, because the proxy routes calls to the target `EntityManager` matching the active thread/transaction. That **does not** make the **target EntityManager**, persistence context, or entities loaded from that context safe to share across threads.

### 2.3. OSIV Can Mask Design Bugs

Open Session in View (OSIV) can keep a persistence context alive across an HTTP request in some Spring web configurations, allowing lazy properties to load unintentionally during response serialization. It does not guarantee the session stays alive in any `@Async` worker, does not make JPA entities thread-safe, and easily causes N+1 queries and hard-to-observe query counts.

Do not enable OSIV or keep transactions open long merely to "patch" passing entities to workers. **Specify the needed data** and build clean boundaries.

## 3. Why Is Passing an Entity Directly to @Async Error-Prone?

```text
Request thread                          Worker thread
-------------------------               ------------------------
@Transactional
   |
   | findById(42)
   v
managed OrderEntity ----- reference ---> @Async process(OrderEntity)
   |                                        |
   | mutate/flush/commit                    | getCustomer().getEmail()
   |                                        | getLines().size()
   | close persistence context              | mutate order.setStatus(...)
   v                                        v
transaction ended                    lazy failure / stale data /
                                     concurrent modification /
                                     no predictable flush
```

Real-world failure modes:

- **Lazy associations:** `order.getLines()` is uninitialized. If the worker touches it after the context closes, it can hit `LazyInitializationException`.
- **Race while the caller is still running:** the worker reads `order.status` right as the caller mutates it; there is no isolated snapshot.
- **Broken dirty-checking expectations:** mutating a detached entity in the worker does not update the database automatically; mutating a managed entity from another thread misuses a non-thread-safe context.
- **Pre-commit reads:** the worker may run before the creating/updating transaction commits. A query in a new transaction may not even see the new row, or may read an older version.
- **Rollbacks:** the caller emits an event / submits a task before commit and then rolls back; the worker may still send an email about an order that never committed.
- **Message serialization:** JPA proxies and bidirectional relations cause huge payloads, recursion, unintended data exposure, or serializer errors.
- **Long-lived transactions:** holding an entity manager/connection open across slow tasks increases contention and bloats the first-level cache.

Passing an entity does not fail immediately every single time. An entity with all fields eagerly loaded and only read might look "fine" in tests. That is **no guarantee** of consistency, thread-safety, or lifecycle correctness.

## 4. Principle: Turn Data Access Into an Explicit Contract

Instead of carrying a **managed entity reference**, carry a **message/command** holding minimal, stable, business-meaningful data:

1. **ID:** the worker receives the identifier and opens an appropriate transaction/persistence context of its own to load data.
2. **Immutable snapshot:** the caller builds an immutable DTO from the required fields while the context is valid, then passes it to the worker.
3. **ID + version/revision:** the worker uses the ID to reload or verify the version to detect stale jobs.
4. **Hybrid:** ID + version + a few snapshot fields for optimization, while still defining which data is authoritative.

| Criterion | ID then re-fetch | Immutable snapshot | ID + expected version |
| --- | --- | --- | --- |
| Payload size | Small | Depends on selected fields | Small |
| When data is read | When the worker loads it | When the caller builds the snapshot | When the worker loads/checks version |
| Sees updates after the event? | Possibly, depending on transaction/isolation | No, snapshot preserves old values | Can detect changes |
| Lazy loading | Worker loads inside new context | Caller must materialize needed fields before sending | Worker loads inside new context |
| Easy over queue/broker | Yes | Yes if DTO is serializable per protocol | Yes |
| Query cost in worker | Yes | Possibly none | Usually yes |
| Stale risk | Reads new state that may diverge from event | Deliberately point-in-time snapshot | Has rule to reject stale state |
| Typical use | "Process current state of order X" | "Send message reflecting event at time T" | "Apply only if revision X is still valid" |

No choice is "always best". Ask about **time semantics**: should the worker act on **the latest current state** or **an event that happened at a specific point in time**?

## 5. Pattern 1 — Pass Only the ID; Worker Reloads Inside Its Own Transaction

This is usually the simplest starting point:

```java
// Anti-pattern: managed OrderEntity passed across the async boundary.
@Async("orderExecutor")
public CompletableFuture<Void> sendNotice(OrderEntity order) {
    String email = order.getCustomer().getEmail();
    gateway.send(email, order.getId());
    return CompletableFuture.completedFuture(null);
}
```

Change to:

```java
// Spring fragment: pass only the identifier value.
@Async("orderExecutor")
public CompletableFuture<Void> sendNotice(long orderId) {
    NoticeSnapshot notice = snapshotLoader.loadById(orderId);
    gateway.send(notice);
    return CompletableFuture.completedFuture(null);
}
```

`snapshotLoader` is **another Spring bean** with a `@Transactional(readOnly = true)` method. It loads the entity inside the worker's new transaction, extracts the needed data, and returns a snapshot. The worker sends the email **after** the read transaction closes, avoiding holding a transaction open across slow network I/O.

Benefits:

- No entity/Session sharing between caller and worker.
- Each transaction gets an independent persistence context.
- Payloads can cross message brokers: just ID, version, and tenant ID if needed.
- Easy to change persistence implementations and optimize queries without breaking complex event schemas.
- Can handle deleted records or records invisible due to uncommitted transactions.

### 5.1. Re-Fetching Means Reading State When the Worker Runs

Suppose at event time an order has status `CREATED`, yet before the worker runs someone updates it to `CANCELLED`. A worker loading by ID sees `CANCELLED`. That is **correct** if the goal is "only send if the order is currently still eligible"; it may be **wrong** if the recipient needs an accurate audit record of the `CREATED` event that occurred.

To avoid confusion, be explicit:

- **Fresh-state command:** "Read the current state of order X and decide whether to send."
- **Historical event:** "Order X was confirmed at T with data Y." Events need snapshots or versioned/historical storage to represent the event itself.
- **Guarded command:** "Apply command only if order X is still at version V."

### 5.2. Wait for Commit Before the Worker Looks Up a Newly Created Record

If the caller creates an order and submits the worker **before commit**, the worker may run before the row commits, so `findById` returns empty or sees old state depending on isolation. Do not solve this with `Thread.sleep(500)` because scheduling order is not guaranteed.

Proper solutions depending on requirements:

- Attach listeners to `AFTER_COMMIT` via `@TransactionalEventListener` when a real transaction exists.
- Persist a durable outbox/job record **in the same transaction** if the event must never be lost.
- If the workflow depends on the transaction succeeding, do not call `@Async` directly to trigger side effects **before commit**.

## 6. Pattern 2 — Immutable Snapshot Preserving Data at Event Emission Time

When the worker needs **the values at the moment the caller decided**, an immutable DTO expresses the contract accurately.

Example using a Java 17 `record`:

```java
public record OrderNoticeSnapshot(
        long orderId,
        String customerEmail,
        String status,
        java.util.List<String> productCodes) {

    public OrderNoticeSnapshot {
        java.util.Objects.requireNonNull(customerEmail);
        java.util.Objects.requireNonNull(status);
        productCodes = java.util.List.copyOf(productCodes);
    }
}
```

This is a **DTO definition fragment**. `record` gives final components; `String` is immutable; `List.copyOf` snapshots the list structure and returns an unmodifiable list rejecting nulls. Because every element is an immutable `String`, the graph in this example has solid snapshot semantics.

**Deep warning:** `List.copyOf` only **shallow-copies** the list structure; it does not deep-copy each element. If `productCodes` were `List<MutableLine>`, each `MutableLine` could still be mutated after sending. Likewise, a record containing a `Date`, array, entity, `List<MutableEntity>`, or object with setters **does not become deeply immutable** just because the outer type is a record.

### 6.1. Choosing the Right Data

A good snapshot:

- Contains only fields the worker genuinely needs.
- Has clear semantics: ID, operation ID, timestamp, status at event emission, version if needed.
- Contains no `EntityManager`, `Session`, `PersistenceContext`, lazy proxy, or live `PersistentCollection`.
- Contains no request-lifecycle objects or unnecessary sensitive data.
- Has a stable schema if serialized over a message broker.
- Uses immutable scalars, equally immutable nested records/DTOs, and immutable collections.

If an association is lazy-loaded, explicitly fetch/initialize it **inside the open transaction** and map each field into the DTO; never pass a lazy collection for the worker to "read later".

### 6.2. Transaction Boundary of a Snapshot

When building a snapshot inside a `@Transactional` method, you are capturing **the state visible to code** inside that transaction. If the transaction later rolls back, a snapshot emitted immediately from the method may describe changes that never committed.

Therefore:

- If the event is only valid upon successful commit, publish it under an appropriate contract and process via `@TransactionalEventListener(AFTER_COMMIT)`, or write an outbox in the same transaction.
- You can **build the snapshot before commit** while the entity is validly accessible, and have the listener dispatch/process it only **after commit**.
- A snapshot does not guarantee DB data won't change after capture; it guarantees **the captured payload does not change** if designed to be genuinely immutable.

## 7. Java 17+ Example — Mutable Reference vs. Immutable Snapshot

The following plain Java example models one thread holding a mutable reference while a `record` holds captured values. No JPA is needed to see that **passing a reference does not copy values**. A latch creates deterministic ordering instead of relying on `Thread.sleep`.

File `MutableVsSnapshotDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MutableVsSnapshotDemo {
    static final class MutableOrder {
        private volatile String status;

        MutableOrder(String status) {
            this.status = status;
        }

        String status() {
            return status;
        }

        void changeStatus(String newStatus) {
            status = newStatus;
        }
    }

    record OrderSnapshot(String status) {}

    public static void main(String[] args) throws Exception {
        MutableOrder entity = new MutableOrder("CREATED");
        OrderSnapshot snapshot = new OrderSnapshot(entity.status());
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> byReference = executor.submit(() -> {
                release.await();
                return entity.status();
            });

            Future<String> bySnapshot = executor.submit(() -> {
                release.await();
                return snapshot.status();
            });

            entity.changeStatus("CANCELLED");
            release.countDown();

            System.out.println("reference=" +
                    byReference.get(5, TimeUnit.SECONDS));
            System.out.println("snapshot=" +
                    bySnapshot.get(5, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac MutableVsSnapshotDemo.java
java MutableVsSnapshotDemo
```

Output:

```text
reference=CANCELLED
snapshot=CREATED
```

**Explanation:**

- `byReference` holds the same `entity` reference, so after `main` changes status, the worker sees the new value.
- `bySnapshot` holds the record containing the String captured at `CREATED`.
- `volatile` here only makes status reads/writes clear regarding memory visibility; it does not make a JPA entity or Hibernate Session thread-safe.
- The latch establishes the *happens-before* relationship needed for observed ordering. This models **Java reference mutability**, not a claim about JPA internals.
- If business logic wants the worker to handle **the latest state**, re-fetching by ID is one strategy; if it wants to process the exact `CREATED` event, a snapshot is another.

## 8. Java 17+ Example — Freezing Nested Data With Proper Copying

A snapshot containing a `List` must avoid being "immutable on the outside, mutable on the inside".

File `DeepEnoughSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepEnoughSnapshotDemo {
    record Line(String productCode, int quantity) {}

    record OrderSnapshot(long id, List<Line> lines) {
        OrderSnapshot {
            lines = List.copyOf(lines);
        }
    }

    public static void main(String[] args) {
        List<Line> liveLines = new ArrayList<>();
        liveLines.add(new Line("SKU-A", 2));

        OrderSnapshot snapshot =
                new OrderSnapshot(101L, liveLines);

        liveLines.add(new Line("SKU-B", 1));

        System.out.println("live-size=" + liveLines.size());
        System.out.println("snapshot-size=" + snapshot.lines().size());
        System.out.println("first=" +
                snapshot.lines().get(0).productCode());

        try {
            snapshot.lines().add(new Line("SKU-C", 3));
        } catch (UnsupportedOperationException ex) {
            System.out.println("list-is-unmodifiable=true");
        }
    }
}
```

```bash
javac DeepEnoughSnapshotDemo.java
java DeepEnoughSnapshotDemo
```

Output:

```text
live-size=2
snapshot-size=1
first=SKU-A
list-is-unmodifiable=true
```

Here `Line` is a record holding `String` and `int`; the list is copied into an unmodifiable list, so the snapshot is sufficiently immutable under this simple contract.

**Do not overgeneralize:** if list elements were `MutableLine` objects with setters, `List.copyOf` would still hold references to those elements. In that case, map each element to an immutable `Line` **element by element** before creating the list snapshot.

An example mapping inside a JPA transaction:

```java
List<OrderLineSnapshot> lines =
        order.getLines().stream()
                .map(line -> new OrderLineSnapshot(
                        line.getSku(),
                        line.getQuantity()))
                .toList();
```

This is a Spring/JPA fragment assuming `getLines()` is fetched/read while the persistence context is valid and `OrderLineSnapshot` is an immutable DTO. `Stream.toList()` returns an unmodifiable list, though deep immutability still depends on the elements.

## 9. Java 17+ Example — Choosing Fresh State or Snapshot by Contract

File `IdVsSnapshotDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class IdVsSnapshotDemo {
    record Order(long id, String status) {}
    record OrderEvent(long id, String statusAtEvent) {}

    public static void main(String[] args) {
        Map<Long, Order> store = new ConcurrentHashMap<>();
        store.put(7L, new Order(7L, "CREATED"));

        Order atEvent = store.get(7L);
        long idOnly = atEvent.id();
        OrderEvent snapshot =
                new OrderEvent(atEvent.id(), atEvent.status());

        store.put(7L, new Order(7L, "CANCELLED"));

        Order current = store.get(idOnly);

        System.out.println("loaded-now=" + current.status());
        System.out.println("event-snapshot="
                + snapshot.statusAtEvent());
    }
}
```

```bash
javac IdVsSnapshotDemo.java
java IdVsSnapshotDemo
```

Output:

```text
loaded-now=CANCELLED
event-snapshot=CREATED
```

This is a `ConcurrentHashMap` simulation, not a database/JPA setup. It deliberately highlights two different questions:

- **"What is order 7's status at processing time?"** -> re-fetch by ID.
- **"What was order 7's status when the event was created?"** -> use a snapshot.

In a real database, isolation levels, replication lag, and transaction timing also affect what the worker sees. So "re-fetch" does not mean "always see the real-time latest state on every replica".

## 10. Recommended Spring/JPA Structure: Events Carry Only IDs, Workers Load Snapshots in Their Own Transactions

The following snippets are **architectural patterns in a Spring Boot + Spring Data JPA project**, not individual files runnable with `javac` alone. They require proper Spring/JPA imports, database beans, and real entity/repository/service/notification-gateway types.

### 10.1. Entity and Repository

Example domain with `OrderEntity` and `OrderLineEntity`. In this snippet, the entity has an ID and fields; the `lines` collection can be lazy-loaded.

```java
// File: OrderEntity.java (fragment)
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String status;
    private String customerEmail;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public Long getId() { return id; }
    public long getVersion() { return version; }
    public String getStatus() { return status; }
    public String getCustomerEmail() { return customerEmail; }
    public List<OrderLineEntity> getLines() { return lines; }

    public void markApproved() {
        status = "APPROVED";
    }
}
```

`OrderLineEntity` is a separate entity with an `order` relationship and `sku`/`quantity` fields; declare it in your project. `@Version` lets optimistic locking detect competing writes per provider semantics, without turning the entity into an object safe to share across threads.

Repository fetching the order together with its lines via an intentional query:

```java
// File: OrderRepository.java (fragment)
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Query("""
           select distinct o from OrderEntity o
           left join fetch o.lines
           where o.id = :id
           """)
    Optional<OrderEntity> findWithLines(@Param("id") Long id);
}
```

This query requires valid relationships/mappings in the project. It can be replaced by `@EntityGraph`, a DTO projection, or a dedicated query. **Do not** return this entity to another worker after the repository call completes merely because the query fetched eagerly; doing so still couples code to a managed entity and mutable graph.

### 10.2. Command and Snapshot Decoupled From JPA

```java
// File: OrderCommitted.java
public record OrderCommitted(long orderId) {}

// File: OrderNoticeSnapshot.java
public record OrderNoticeSnapshot(
        long orderId,
        long version,
        String customerEmail,
        java.util.List<String> productCodes) {

    public OrderNoticeSnapshot {
        productCodes = java.util.List.copyOf(productCodes);
    }
}
```

Both records are **value carriers**; neither holds an entity, Hibernate proxy, or `EntityManager`. If `customerEmail` contains personal data, apply payload minimization and your system's data-handling policies, especially when sending over brokers or logging.

### 10.3. Loader Owning the Read Transaction on the Worker Thread

```java
// File: OrderSnapshotLoader.java (fragment)
@Service
public class OrderSnapshotLoader {
    private final OrderRepository repository;

    public OrderSnapshotLoader(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderNoticeSnapshot load(long id) {
        OrderEntity order =
                repository.findWithLines(id).orElseThrow();

        List<String> codes =
                order.getLines().stream()
                        .map(OrderLineEntity::getSku)
                        .toList();

        return new OrderNoticeSnapshot(
                order.getId(),
                order.getVersion(),
                order.getCustomerEmail(),
                codes);
    }
}
```

This is a **separate Spring bean**. The worker calls `loader.load(id)` through a Spring-managed reference so `@Transactional(readOnly = true)` is intercepted when transaction management is active. The loader builds the snapshot **inside the context**, then returns the DTO. Once the method finishes, the worker never needs to touch lazy entity fields.

**Do not treat `readOnly = true` as an absolute write-prevention lock on every database:** it is a transaction/provider hint to optimize or restrict flushing depending on configuration; business correctness still needs explicit design.

### 10.4. @Async Worker Receives an ID, Not an Entity

```java
// File: OrderNotificationWorker.java (fragment)
@Service
public class OrderNotificationWorker {
    private final OrderSnapshotLoader loader;
    private final NotificationGateway gateway;

    public OrderNotificationWorker(
            OrderSnapshotLoader loader,
            NotificationGateway gateway) {
        this.loader = loader;
        this.gateway = gateway;
    }

    @Async("notificationExecutor")
    public CompletableFuture<Void> deliver(long orderId) {
        OrderNoticeSnapshot payload = loader.load(orderId);
        gateway.send(payload);
        return CompletableFuture.completedFuture(null);
    }
}
```

The worker opens a read transaction **through a separate loader bean**, then calls the gateway with a DTO. This separation avoids holding a DB transaction open while waiting on HTTP/email I/O. Gateway errors fail the `@Async` call's future per Spring's mechanism; the caller or event listener must observe and handle failures.

If notifications must be delivered even across a JVM restart, an in-memory worker alone is insufficient; see the **outbox** section below.

### 10.5. Bounded Executor Configuration

```java
@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {
    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("notice-");
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(40);
        return executor;
    }
}
```

This fragment requires matching imports. Thread/queue numbers are illustrative only. `@EnableAsync` activates async annotation processing; the executor bean governs resources. If `notificationExecutor` rejects tasks under overload, the application must have a handling policy rather than dropping exceptions silently or assuming "publishing the event means we're done".

## 11. Transaction-Bound Events: Process Only After Commit

A typical flow has a transactional service update the order and publish a **lightweight event**:

```java
// File: OrderApplicationService.java (fragment)
@Service
public class OrderApplicationService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderApplicationService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void approve(long orderId) {
        OrderEntity order =
                repository.findById(orderId).orElseThrow();
        order.markApproved();

        // Event carries the ID, not OrderEntity.
        publisher.publishEvent(new OrderCommitted(orderId));
    }
}
```

If a regular listener were invoked immediately inside the transaction, calling the worker directly could run **before commit**. We need a transaction-phase listener:

```java
// File: OrderCommittedListener.java (fragment)
@Component
public class OrderCommittedListener {
    private final OrderNotificationWorker worker;

    public OrderCommittedListener(
            OrderNotificationWorker worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderCommitted event) {
        worker.deliver(event.orderId())
              .whenComplete((ignored, error) -> {
                  if (error != null) {
                      // Record the error according to real logging/monitoring.
                  }
              });
    }
}
```

These snippets need imports, a real transaction manager, and events published **inside a transaction**. `@TransactionalEventListener` defaults to the `AFTER_COMMIT` phase. When no transaction exists, the listener is **not invoked** by default unless `fallbackExecution=true` is explicitly enabled.

**Expected timeline:**

```text
Request thread:
  @Transactional approve()
     -> find managed OrderEntity
     -> mutate entity
     -> publish OrderCommitted(orderId)
     -> commit transaction
     -> AFTER_COMMIT listener calls worker.deliver(orderId)

Worker executor thread:
  @Async deliver(orderId)
     -> @Transactional(readOnly=true) loader.load(orderId)
     -> opens a new context in the worker
     -> maps entity to immutable snapshot
     -> closes read transaction
     -> gateway.send(snapshot)
```

A post-commit listener is **not automatically asynchronous**. `@TransactionalEventListener` binds to the transaction lifecycle; calling `worker.deliver(...)` is what passes through the `@Async` proxy to submit the task to the executor.

### 11.1. Two Important Warnings About AFTER_COMMIT

**Warning 1 — In-memory events are not durable.** The DB transaction can commit successfully and the JVM can die **before** the listener submits the task, or while the task sits in an in-memory queue before the process is killed. `AFTER_COMMIT` prevents running before commit as configured; it does **not** promise at-least-once delivery across restarts. If tasks must not be lost, use a transactional outbox or durable job queue.

**Warning 2 — Post-commit resources may still be bound.** Per Spring Javadoc, during `AFTER_COMMIT`/`AFTER_COMPLETION` callbacks, transactional resources can sometimes still be accessible even though the transaction already committed; a DB write performed on that same transaction resource may **not commit**. If a listener must perform synchronous transactional writes, use an appropriate new transaction (such as `REQUIRES_NEW` via a Spring proxy); in the pattern above, we only dispatch to the worker, and the loader opens a transaction on the worker thread.

Do not assume "after commit" means every resource has already been unbound the instant the callback starts.

### 11.2. When You Need a Snapshot of a Specific Before/After State

A listener receiving only an ID loads **the current state when the worker runs**, which might already reflect updates *after* the event. If an email must state exactly "approved at T for total Y", the event should carry an immutable snapshot of those fields — constructed **inside the transaction** once state is ready and processed only after commit — or store the data in an outbox inside the transaction.

Do not capture `OrderEntity` and defer mapping the DTO until the post-commit listener; that brings lazy/context hazards right back. **Materialize snapshots while the context is still valid.**

## 12. Avoiding Stale Data: ID Plus Version and Optimistic Locking

Passing an ID guarantees you can re-fetch inside a dedicated context, yet does not by itself prevent processing stale information. Use `@Version` or a revision/generation if you need to confirm which state a task corresponds to.

Example event:

```java
public record OrderNotificationRequested(
        long orderId,
        long expectedVersion) {}
```

The worker reads the current version and decides:

```java
OrderNoticeSnapshot current = loader.load(event.orderId());

if (current.version() != event.expectedVersion()) {
    // Event is stale; skip, reconcile, or follow policy.
}
```

This is only a **pre-processing check fragment**. If data can change **between the check and committing the side effect**, a Java comparison has a check-then-act race. Enforce the condition **atomically at the update boundary**: JPA optimistic locking on flush/commit, a versioned conditional SQL UPDATE, or downstream fencing.

Also note that `@Version` is typically incremented on flush. If you publish an event inside a transactional method and read `getVersion()` **before flush**, the value may still be the old version. If the event needs the **committed version**, obtain the version after flushing and process the event only after commit; verify your JPA provider and actual transaction behavior.

### 12.1. Conditional Update in the Database

Illustrative SQL example:

```sql
UPDATE orders
SET notification_state = 'SENT'
WHERE id = :order_id
  AND version = :expected_version
  AND notification_state = 'PENDING';
```

The updated row count is the critical signal: 1 means the condition held when the database executed the statement; 0 means the record, version, or state changed or does not exist. Transactions, isolation, and version increments must match the schema properly. **This is not yet a fencing guarantee for an external email send**, since email delivery happens in another system.

For multi-table updates, design the transaction so checking and updating occur in **the same atomic scope**, rather than doing a `findById` followed much later by an unguarded write.

### 12.2. Java 17+ Example: Guarding Updates With Version

File `VersionedUpdateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class VersionedUpdateDemo {
    record State(long version, String status) {}

    static boolean updateIfVersion(
            AtomicReference<State> store,
            long expectedVersion,
            String newStatus) {

        while (true) {
            State current = store.get();

            if (current.version() != expectedVersion) {
                return false;
            }

            State next = new State(
                    current.version() + 1,
                    newStatus);

            if (store.compareAndSet(current, next)) {
                return true;
            }
        }
    }

    public static void main(String[] args) {
        AtomicReference<State> state =
                new AtomicReference<>(new State(1, "CREATED"));

        long oldVersion = state.get().version();

        state.set(new State(2, "APPROVED"));

        System.out.println("stale-applied=" +
                updateIfVersion(state, oldVersion, "SENT"));
        System.out.println("current-applied=" +
                updateIfVersion(state, 2, "SENT"));
        System.out.println("final=" +
                state.get().version() + ":" +
                state.get().status());
    }
}
```

```bash
javac VersionedUpdateDemo.java
java VersionedUpdateDemo
```

Stdout:

```text
stale-applied=false
current-applied=true
final=3:SENT
```

This is a single-JVM model using `AtomicReference.compareAndSet`. Version comparison plus state update happen atomically via CAS on the **current reference**. In multi-replica production systems, use **database conditional updates / optimistic locking**, never a local `AtomicReference`.

If the side effect is an email or HTTP call, you cannot place network I/O inside a CAS to build a distributed transaction. Use an outbox, idempotency, and reconciliation per the receiving system's contract.

## 13. Immutable Snapshots Must Also Be Safe for Ownership and Serialization

A good DTO should never embed a **JPA entity** inside:

**Unsafe:**

```java
record OrderEvent(long id, OrderEntity entity) {}
record CustomerEvent(long id, List<CustomerEntity> customers) {}
```

The outer record has an immutable reference, yet `entity` and list elements remain mutable and may hold lazy proxies.

**Better:**

```java
record CustomerSnapshot(long id, String email) {}

record OrderEvent(
        long id,
        long revision,
        List<CustomerSnapshot> customers) {

    OrderEvent {
        customers = List.copyOf(customers);
    }
}
```

This example may require importing `List`; it is a DTO definition fragment. Construct `CustomerSnapshot` from scalar fields loaded inside the transaction rather than creating a record that still wraps an entity reference.

### 13.1. Do Not Abuse Entity Serialization

Avoid publishing full entities over JSON/Kafka/RabbitMQ because:

- Lazy fields may be accessed outside a session.
- Bidirectional relationships cause recursion or bloated payloads.
- Persistence schemas differ from event schemas; changing JPA mappings can break consumers.
- Personal data or internal fields may leak unintentionally.
- Entities can carry behavior and invariants unsuitable for a serialized contract.
- A "deserialized entity" does not automatically become a **managed entity** in a new transaction.

Messages should use dedicated event DTOs with their own schemas, versioning when needed, minimal fields, and valid IDs. Consumers must handle older messages during schema evolution.

### 13.2. An ID Is Not Enough in Multi-Tenant Systems

In multi-tenant applications, passing only `orderId` may be insufficient to establish the proper access scope. Events should include `tenantId` or required scope metadata (not a whole mutable `SecurityContext`), and workers must enforce authorization and tenant isolation at the authoritative data store. Do not assume that because a controller authenticated the request, an asynchronous worker automatically carries full security context.

### 13.3. Version and Event Time Are Not the Same

- `id` identifies the resource.
- `version` identifies the revision and helps detect stale updates.
- `eventId` identifies a single event emission/operation for deduplication.
- `occurredAt` describes when the event occurred; it is not a strong concurrency key.
- `tenantId` identifies the scope.
- `correlationId` supports tracing and auditing.

Choose metadata purposefully instead of stuffing every field into one record.

## 14. @Async and Transaction Context Are Two Distinct Boundaries

When a method is invoked through a Spring `@Async` proxy, execution is typically submitted to an executor and runs on another thread. Spring transactions in the standard imperative model rely on a thread-bound context; the caller's transaction **does not automatically move to the worker**.

Distinguish these points:

1. `@Async` enables execution handoff through a proxy when `@EnableAsync` is present; it does not open a transaction.
2. `@Transactional` enables transaction advice when intercepted properly; it does not create an executor.
3. Putting both annotations on a single method can work depending on advice ordering and configuration; the more controllable pattern is **separating the async worker bean and the transactional loader bean** so boundaries stay clear.
4. `@Transactional(readOnly = true)` on the loader opens a context suited to the worker thread when invoked through a proxy.
5. `this.loadById(id)` within the same bean bypasses transaction advice in proxy mode; extract the loader to another bean or use an explicit transaction mechanism.
6. The caller's context may contain unflushed/uncommitted objects, so an ID re-fetch in the worker **before commit** may miss changes.

### 14.1. OpenEntityManagerInView Is Not a Context-Propagation Tool

OSIV can keep a context open on the request thread, yet it **does not** carry that context into `@Async` or `CompletableFuture` callbacks. Avoid relying on OSIV to keep object graphs alive. Proper design relies on queries, projections, DTOs, and short, explicit transaction scopes.

### 14.2. Reactive Context Is a Different Model

With Spring WebFlux/R2DBC, transaction context can flow through Reactor context rather than `ThreadLocal`. Even so, the message-boundary principle remains useful: never carry resources/sessions tied to an execution context across incompatible threads or callbacks. `@TransactionalEventListener` in Spring 6.1+ also supports reactive transactions under its own rules; use the right event source and context. Do not extrapolate reactive handling directly from imperative JPA examples.

## 15. When Is Passing an ID Better Than a Snapshot?

**Passing an ID** is usually appropriate when:

- The worker must evaluate the entity's **current state**.
- Permission to send/write depends on the latest status, consent, subscription, or data.
- The object graph is large, only a few fields are needed, and an optimized repository query exists.
- Jobs live long across retries, replicas, or restarts.
- Event schemas should stay simple while worker logic decides using fresh domain state.

Example: "once an order is confirmed, if a notice has not been sent yet and the order has not been cancelled, send it once" -> ID + checking state/version/idempotency inside the worker.

**Downsides:** the worker incurs an extra DB query and may observe a changed or deleted record; you must handle `not found` and consistency lag.

## 16. When Is an Immutable Snapshot Better Than an ID?

An **immutable snapshot** is usually appropriate when:

- Content must reflect **the values at event time**.
- Consumers live in other systems without access to the source database.
- You do not want a slow worker reading newer state and distorting historical semantics.
- The event is a business fact ("order was confirmed with total X"), not a command ("read the latest state").
- You want to reduce coupling to JPA mappings and database schemas.

Example: an audit/billing event requiring amount, currency, approvedAt, and revision **right at commit time**. The snapshot must be built from valid data and published only after commit; if crash durability is required, store an outbox record in the same transaction.

**Downsides:** larger payloads, schema versioning, deep immutability requirements, and sensitive-data policies. Snapshots are **intentionally point-in-time** relative to current state; consumers must not overwrite a newer aggregate without versioning/fencing.

## 17. Hybrid Pattern: ID + Version + Minimal Snapshot

A domain event can use:

```java
public record OrderApprovedEvent(
        long orderId,
        long aggregateVersion,
        String approvedCurrency,
        long approvedAmountMinor,
        String eventId) {}
```

This is a Java 17 value-type fragment. The consumer can:

- Use the amount/currency snapshot to record event audits.
- Use `orderId` to query additional fresh data when needed.
- Use `aggregateVersion` to detect stale events when maintaining a latest-wins state projection.
- Use `eventId` to deduplicate retries and redeliveries.

No single field guarantees exactly-once execution across all services. You still need unique constraints, conditional updates, or appropriate downstream idempotency mechanisms.

### 17.1. SQL Example Checking Version When Applying a Projection

```sql
UPDATE order_views
SET status = :status,
    source_version = :incoming_version
WHERE order_id = :order_id
  AND source_version < :incoming_version;
```

This is **sample SQL** requiring a suitable schema, transaction, and handling for missing rows (a valid UPSERT). It prevents a lower-version event from overwriting a newer projection, though it does not by itself solve insert races, duplicate events, or cross-table atomicity.

## 18. Transactional Outbox for Events That Must Not Be Lost

`@TransactionalEventListener(AFTER_COMMIT)` works well for tying logic to commit **within a living process**, yet it **does not** guarantee jobs survive if the process dies between DB commit and the listener/async queue.

For at-least-once delivery requirements:

```text
Inside order create/update transaction:
    UPDATE/INSERT order...
    INSERT outbox(event_id, order_id, version, immutable_payload)
COMMIT

Outbox worker:
    read undelivered events
    publish/dispatch with bounded retries
    consumer deduplicates by event_id
    record delivery status
```

This is architectural pseudocode, not standalone SQL. When writing **order + outbox in the same DB transaction**, either both commit or both roll back. Consumers may receive redelivered messages, so **idempotency** must be designed in. Events carry IDs or immutable DTOs/projections — **never managed JPA entities**.

If stale commands arriving after newer ones must be blocked, add `version`/fencing on the consumer; an outbox does not automatically keep event data equal to the latest state.

### 18.1. Competition Between Events Can Still Occur After Commit

Two order events may be published close together and processed out of publish order by workers. An event ID only helps deduplicate, not order. For latest-wins projections, use aggregate versions and conditional updates. For workflows needing strict global ordering, design dedicated partitioning/ordering guarantees.

## 19. Testing: Proving Managed Entities Never Cross the Boundary

A good test captures transactions, threads, entity states, and real data — not just checking that a future completed.

### 19.1. Unit Tests for DTOs

- Construct `OrderNoticeSnapshot` with a mutable `List`, mutate the original list afterward, and verify the snapshot is unchanged.
- Attempt to mutate `snapshot.productCodes()` and verify the list rejects `add`.
- Verify nested elements are immutable, not just the outer record.
- Verify null checks, missing fields, schema versions, and stripped sensitive fields.

The Java 17+ examples in this lesson provide deterministic test cases.

### 19.2. Integration Tests With JPA/Hibernate

1. Create an order and lazy association inside a transaction.
2. Load the entity, build the DTO **inside the transaction**, and close the transaction.
3. Access the DTO on a worker thread and confirm zero dependency on the Hibernate session.
4. Test deliberately leaking an unloaded lazy proxy outside the context and verify provider behavior — typically `LazyInitializationException` in Hibernate when accessing something needing a session. Do not assume every entity field always throws.
5. Measure query counts to catch projection N+1 issues; use fetch joins, entity graphs, or DTO projections as appropriate.
6. Force the transaction to roll back after publishing the event and confirm the `AFTER_COMMIT` listener applies no side effects.
7. Publish an event inside a successful transaction and verify the worker reads **committed** data.
8. Mutate the entity before the worker loads it; check that the ID path sees state per isolation while the snapshot retains captured state.
9. Trigger an optimistic locking conflict and verify stale versions are rejected.
10. Kill the process after DB commit before dispatch, comparing `@TransactionalEventListener` behavior with a durable outbox.

### 19.3. Do Not Use Sleep to Guess Ordering

Use `CountDownLatch`/`CyclicBarrier`/`CompletableFuture` with timeouts to coordinate *event published*, *transaction committed*, *worker started*, and *worker allowed to query*. `Thread.sleep(100)` does not guarantee the transaction committed in time or the worker ran when expected.

For instance, an integration test can hold the worker at a barrier, let the caller commit and mutate state, and then release the worker. Verify the ID path and snapshot path diverge as intended. With multiple replicas, test isolation/concurrency on a real DB rather than only an in-memory map.

### 19.4. Proxies and Transactions on the Right Thread

- Is `@EnableAsync` genuinely loaded into the context?
- Is the `@Async` method called via a Spring-managed bean rather than `this.method()`?
- Is the `@Transactional` loader intercepted via another bean?
- Does the chosen executor thread have the expected name prefix and bounds?
- Does the `AFTER_COMMIT` listener run on commit and get skipped on rollback?
- Are errors from `CompletableFuture<Void>` observed rather than ignored?
- Does the loader close its transaction before long external I/O?

## 20. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Passing a managed entity directly into `@Async` | Sharing object graph/session across threads; races/lazy failures | Pass an ID or immutable DTO |
| Thinking switching threads auto-detaches entities | Entity may still belong to caller's context | Never share contexts/entities across threads |
| Reading lazy associations in worker after caller tx closes | `LazyInitializationException` when unloaded | Fetch/materialize DTO inside a valid transaction |
| Enabling OSIV to "fix" async lazy loading | Masks boundaries, gives no thread-safety | Worker's own transaction + DTO |
| Passing `List.copyOf(entities)` | Copies the list, yet elements remain mutable entities | Map each element to an immutable snapshot |
| Reading entity into event before commit and running immediately | Worker sees uncommitted/rolled-back data | `AFTER_COMMIT` or outbox |
| Assuming `@TransactionalEventListener` always runs async | Phase-bound listener by default, not a separate executor | Call `@Async` worker via proxy or configure explicitly |
| Assuming `AFTER_COMMIT` guarantees durable delivery | JVM crash can lose in-memory events | Transactional outbox/queue |
| Passing ID assuming worker sees the state at event time | Re-fetch may observe newer state | Pass snapshot if historical fact is needed |
| Passing snapshot and using it to overwrite latest state | Snapshot may be stale | Version/conditional update and domain invariants |
| Reading `@Version` before flush thinking it is the committed revision | Version may not have incremented yet | Verify flush/commit and payload version |
| Putting `@Transactional` on a self-invoked helper | Advice can be bypassed | Extract transactional loader into another bean |
| Keeping a DB transaction open during slow email/HTTP calls | Holds resources and raises contention | Copy DTO, close transaction, then call gateway |
| Carrying `SecurityContext`/`HttpServletRequest` to workers | Request/thread context becomes invalid | Pass safe ID/scope and re-authorize at boundary |
| Serializing whole JPA entities to a broker | Lazy recursion, schema coupling, data leaks | Dedicated message schema |
| Using IDs without tenant scope | Cross-tenant data exposure | Tenant isolation and authoritative authorization |
| Ignoring worker future failures | Jobs fail silently | Monitor completions, metrics, retries/durable jobs |

## 21. Practice Exercises

### Exercise 1 — Refactor an Async Service

Given:

```java
@Transactional
public void createOrder(OrderEntity entity) {
    repository.save(entity);
    worker.sendEmail(entity);
}
```

Redesign so that: the transactional service persists the order and publishes `OrderCommitted(orderId)`; an `AFTER_COMMIT` listener dispatches `worker.sendEmail(orderId)`; the worker invokes a separate `@Transactional(readOnly=true)` loader to obtain an immutable payload. Explain why `entity` must not be an async parameter.

### Exercise 2 — Snapshot Lazy Associations

Given an `OrderEntity` with lazy `List<OrderLineEntity> lines`. Write an appropriate fetch query, build an `OrderNoticeSnapshot` with a `List<LineSnapshot>` where every element is immutable, close the persistence context, and use the snapshot on a worker thread.

### Exercise 3 — Latest State or History?

An order is at version 8 when the event fires, but moves to version 9 before the worker runs. Define desired behavior for (a) a historical invoice email, (b) sending a notice only if the order is not cancelled, and (c) updating a search projection. Choose ID, snapshot, or ID+version and explain.

### Exercise 4 — Optimistic Locking

Write a test with two workers using the same `expectedVersion`. The first worker succeeds; the second must receive `OptimisticLockException` or 0 rows from a conditional UPDATE depending on implementation. Never allow stale data to overwrite newer data.

### Exercise 5 — Event Boundaries and Retries

Roll back a transaction after publishing an event; verify the `AFTER_COMMIT` listener does not run. Then simulate process termination after commit before the listener runs; explain why an outbox recovers the work. Add `eventId` so the consumer deduplicates retries.

### Exercise 6 — Multi-Tenancy and Data Protection

Design an event containing only `tenantId`, `orderId`, `eventId`, and strictly required snapshot fields. The worker queries by both tenant and ID without relying on request `SecurityContext`, avoiding logging emails or full payloads. Test that a tenant A event cannot read a tenant B order.

### Exercise 7 — Deep Immutability

Replace `List<String>` with `List<MutableLine>` inside a record and observe that `List.copyOf` does not block mutating element fields. Fix it by mapping each line to an immutable `record LineSnapshot`. Write assertions after mutating the source.

## 22. Pre-Production Checklist

- [ ] I know managed entities and persistence contexts belong to a unit of work, not a message payload.
- [ ] I never share target `EntityManager`/Hibernate Sessions or managed entity graphs concurrently across threads.
- [ ] I choose ID when the worker needs fresh state; snapshot when it needs point-in-time state; ID+version when a stale guard is needed.
- [ ] I never access lazy entity associations in a background thread outside an appropriate context.
- [ ] Snapshots are created inside a valid transaction and are immutable **including all required nested elements**.
- [ ] I do not assume `@Async` transfers transactions or request contexts to workers.
- [ ] I use a separate transactional loader bean invoked through a Spring proxy.
- [ ] I understand `@TransactionalEventListener(AFTER_COMMIT)` does not imply async or durability.
- [ ] I never hold DB transactions open across external network/email calls.
- [ ] I use optimistic locking/fencing when stale updates must not overwrite newer ones.
- [ ] I use an outbox/idempotency when events must be delivered and retried.
- [ ] I enforce tenant scope, access control, and sensitive-data minimization in payloads.
- [ ] I test lazy loading, rollbacks, commits, re-fetching, snapshots, stale versions, and restarts.

**Conclusion:** in Spring concurrency, the safe approach is **crossing async/event boundaries using values with clear contracts** — IDs, immutable snapshots, or ID+version — instead of passing entities still bound to a persistence context. Workers open their own needed transactions, materialize DTOs inside those boundaries, and control post-commit side effects. The result is code with transparent lifecycles, minimal Hibernate session coupling, straightforward concurrency testing, and clean scalability across queues and replicas.

## 23. Official References

- Hibernate ORM — [User Guide, Persistence Context](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): managed/detached states, session lifecycle, dirty checking, lazy loading, and thread-safety.
- Hibernate ORM — [An Introduction to Hibernate 6](https://docs.hibernate.org/orm/6.6/introduction/html_single/): why Session/EntityManager must not be shared across threads.
- Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` phases and `fallbackExecution`.
- Spring Framework Javadoc — [TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): note on resources after `AFTER_COMMIT`.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executors, and lifecycle.
- Spring Framework — [Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): Spring transaction proxies and `@Transactional` boundaries.
- Jakarta Persistence — [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): entity lifecycle, persistence contexts, and `@Version`.

Always verify Spring/JPA/Hibernate versions in your project. The Spring/JPA and SQL snippets above are **integration templates requiring real domain types, imports, and dependencies**; the examples explicitly marked `javac`/`java` are standalone Java 17+ programs.

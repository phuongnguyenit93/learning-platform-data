# Avoiding Oversized Payloads in Spring Framework Application Events

## 1. Lesson Objectives

A well-designed application event expresses **what just happened** using a small, clear, and stable data contract, rather than carrying the entire object graph currently being processed. In Spring Framework, calling `ApplicationEventPublisher.publishEvent(...)` decouples the emitter from receivers, yet does not by itself solve **payload size, heap retention duration, data consistency, and listener cost**.

This lesson focuses on **avoiding oversized payloads** when designing internal Spring application events, while noting what must change if events move to a message broker or distributed system.

After this lesson, you will be able to:

- Define precisely what "oversized payload" means in **in-process Spring events** and distinguish it from serialized messages.
- Identify events carrying whole JPA entity graphs, long lists, files/`byte[]`, HTTP objects, or mutable objects.
- Choose among **ID/reference events**, **minimal immutable snapshots**, and **size-bounded batch events**.
- Know when listeners should load data by ID and when a small snapshot is needed to avoid reading stale/wrong state.
- Explain the impact of synchronous execution, async, queues, transactions, and data lifecycles on memory and correctness.
- Build a runnable Java 17+ example with Gradle and practice verifying with real metrics.

**Key message:** "Avoiding oversized payloads" is not only about reducing bytes in one class. It is about designing the **event contract**, bounding the **object graph kept alive**, and clarifying **who is responsible for reading data when the listener runs**.

## 2. What Actually Is an Event Payload in Spring Framework?

Spring Framework allows publishing any object:

~~~java
publisher.publishEvent(new OrderPlaced(orderId, "CREATED"));
~~~

If the object does not extend `ApplicationEvent`, Spring wraps it in `PayloadApplicationEvent<?>` to dispatch it to matching listeners. A listener can use:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Receive the exact published payload.
}
~~~

Both snippets above are illustrative: `publisher`, `OrderPlaced`, and the listener bean must exist.

With Spring's default multicaster, regular listeners are invoked **synchronously on the publishing thread**. An executor can be configured to dispatch across other threads. However, **internal publishing does not by default serialize objects to JSON or deep-copy entire objects**. It passes events through Spring's listener infrastructure within the same process.

This leads to two important conclusions:

1. An event holding a reference to a large `OrderEntity` **does not duplicate the entire entity graph for each listener** merely because there are multiple listeners. Yet the event still holds a reference to that object graph; the garbage collector cannot reclaim objects that remain reachable.
2. If a listener, executor queue, buffer, retry structure, or lambda retains the event, all objects reachable from the payload **can stay alive longer than expected**. When each event retains its own graph, a backlog of many events creates significant heap and GC pressure.

When data is sent to Kafka, RabbitMQ, HTTP, a JSON outbox, or another process, payloads usually **must be serialized**, adding costs for bytes transferred, encoding/decoding, message limits, storage, and schema compatibility. Never apply the "just pass an in-RAM reference" model directly to cross-process paths.

## 3. When Is a Payload Considered Too Large?

There is no fixed byte threshold that every Spring system must obey. Evaluate based on **necessity, ratio of needed data to carried data, backlog potential, latency, and load conditions**.

Examples of payloads at risk of being oversized:

- An event carrying an entire `OrderEntity` plus JPA relations like `orderLines`, `customer`, `addresses`, and `payments` when the listener only needs `orderId`.
- An event carrying a very long `List<OrderDetail>` when the listener only needs to know a batch finished.
- An event embedding full images, PDFs, `byte[]`, Base64 strings, or uploaded files just to announce "uploaded".
- An event stuffing in `HttpServletRequest`, HTTP sessions, security principals, response objects, connections, streams, `EntityManager`, or complex lifecycle resources.
- An event containing an entire mutable object graph that the emitter might mutate after `publishEvent`.
- High-frequency repeating events where every instance repeats bulky metadata even though only a few fields are useful.

Distinguish three kinds of size:

| Concept | Meaning | How to Observe |
| --- | --- | --- |
| **Shallow size** of the event instance | Memory of the event object itself and its reference/primitive fields | Profiler / heap inspection |
| **Retained/reachable graph** | Objects reachable from the event and its referenced objects | Heap dump, profiler; do not double-count shared graphs |
| **Serialized size** | Size after converting to JSON/Avro/Protobuf/... | Measure directly after serialization with the real codec |

A `record OrderPlaced(long orderId)` is tiny, whereas a `record OrderPlaced(OrderEntity order)` can hold references to thousands of objects behind it. Conversely, two events referencing the same large immutable catalog do not mean the heap duplicated the catalog. Therefore, never try to measure size via `event.toString().length()` or `Object.toString()`; those do not measure object graph memory.

## 4. Design Principle: Keep Minimal Data to Satisfy the Contract

Before adding a field to an event, ask:

1. **What does the listener truly need?** Just an ID? New status? Timestamp? Tenant ID? Version number? A few values that must remain immutable?
2. **Is that value available/stable at publication time?** If the listener needs state at the exact occurrence time, consider a snapshot.
3. **When does the listener run?** Immediately on the publisher thread, asynchronously, after commit, or after retries?
4. **Can it look up by ID?** Is the repository accessible after commit? Could the record be deleted or modified before the listener reads it?
5. **Does the payload contain sensitive data?** Does holding/logging/serializing it widen the exposure surface?
6. **Does the data have long-term value?** If the event goes to a broker, the schema must be stable and sufficient for reprocessing.

The goal is not "fewest fields at all costs". The goal is **minimum data that is still sufficient for receivers to process correctly**.

Example:

~~~java
// Avoid: every listener receives the entire entity graph.
public record OrderPlacedBad(OrderEntity wholeOrder) {}

// Minimal when listeners can re-query:
public record OrderPlaced(long orderId) {}

// Small snapshot when semantics at publication time must be preserved:
public record OrderPlacedSnapshot(
        long orderId,
        String orderStatus,
        java.time.Instant occurredAt,
        long version) {}
~~~

These are illustrative definitions; `OrderEntity` is not defined in this snippet. Do not put all three payload styles into the same production event "just in case".

## 5. Strategy 1: Event Carries Only an ID or Reference Key

Basic example:

~~~java
public record InvoiceGenerated(long invoiceId) {}
~~~

Upon receiving the event, the listener fetches only the fields it needs from the repository:

~~~java
@EventListener
public void onInvoiceGenerated(InvoiceGenerated event) {
    Invoice invoice = invoiceRepository.findById(event.invoiceId())
            .orElseThrow();
    reportService.process(invoice);
}
~~~

These snippets require `Invoice`, the repository, the service, and the listener bean to be configured; they are not a standalone program.

### 5.1. Pros

- Small payload with low coupling to entity structure; changing internal properties does not force updating every event.
- Minimal heavy object graphs held in memory at publish time.
- Listeners can read the exact **projection** they need rather than working with an entire entity.
- Lower risk of accidentally leaking PII, attachments, or lazy-loaded graphs into inappropriate places.
- If later moving from internal events to a broker, serializing a simple ID and version is easier to manage.

### 5.2. Trade-offs: Lookups and Data Accuracy

ID-only is not free. The listener must hit the repository, so it can encounter:

- **N+1 queries:** thousands of listeners/IDs processed individually increase round-trips.
- **Uncommitted data unseen:** a listener running in another transaction or thread before commit might not read the row.
- **Data already mutated:** a delayed listener might read a newer state rather than the state at event occurrence.
- **Record deleted:** the ID was valid at publish time but no longer exists at handling time.
- **Authorization/tenant bounds:** the listener needs to know the valid scope to query without relying on a `ThreadLocal` security context from an old request.

Thus, use ID-only only when the listener is **allowed to read the current state** and has clear handling for not-found/retries/stale data. If processing depends strictly on a past fact, use a small snapshot or a proper event log/outbox.

## 6. Strategy 2: Minimal Immutable Snapshot

Not every listener should re-query data. Some decisions depend on **the state at the exact moment of the business event**. For example, a listener calculating commission on an agreed price; afterward, the product price may change.

In that case, carrying only an ID is insufficient. The event should hold **business values that cannot be safely re-derived later**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record PaymentAccepted(
        String paymentId,
        String currency,
        BigDecimal capturedAmount,
        Instant acceptedAt) {}
~~~

This content stays small, carries clear semantics, and does not force receivers to drag along the `Payment` entity, transaction history, card details, billing address, or log data.

You may also include:

- `entityVersion` to detect that the record has since changed.
- `occurredAt` to distinguish event time from listener execution time.
- `tenantId` for multi-tenant data; treat it as an **authorization input**, not proof of access rights.
- Small `correlationId`/`traceId`, without embedding an entire request/trace object.

### 6.1. Records Have Only Shallow Immutability

Java records create final fields, yet do not automatically make inner objects immutable. For example:

~~~java
public record BatchReady(java.util.List<Long> ids) {
    public BatchReady {
        ids = java.util.List.copyOf(ids);
    }
}
~~~

`List.copyOf(...)` produces an unmodifiable snapshot of the list structure, preventing the publisher from adding/removing IDs via the old list and mutating the list in the event. However, if elements are mutable objects, `List.copyOf` **does not deep-copy element contents**. With `Long` IDs, stability is much easier to guarantee.

For `byte[]`, copy defensively if binary data must truly be included; however, a better approach is usually **not sending binary data in events**, instead sending an object-storage ID/name and minimal metadata.

### 6.2. Do Not Bind Events to Live Entities

JPA/Hibernate entities typically have:

- Uninitialized lazy associations and proxies.
- Persistence contexts, bidirectional relationships, and many linked objects.
- Mutable state and transaction/session lifecycles.
- Risk of failure when an async listener accesses a lazy field after the session closes.

Therefore, **do not treat an entity graph as a "free snapshot"**. An unserialized entity may look small at publish time, yet calling getters inside a listener triggers unexpected queries, lazy initialization errors, or graph bloat. Convert to DTOs/records with explicitly defined fields.

## 7. Strategy 3: Use References for Large Resources Instead of Embedding Directly

For images, PDFs, videos, contracts, import files, or large analytical payloads, events should announce **resource location and status** rather than carrying the data:

~~~java
public record DocumentUploaded(
        String documentId,
        String storageKey,
        long contentLength,
        String checksum) {}
~~~

Meaning of the fields:

- `documentId` identifies the document in the domain.
- `storageKey` locates the object in a storage system the listener is authorized to access.
- `contentLength` supports limit checks/observability.
- `checksum` supports integrity verification when genuinely needed.

Do not place **long-lived signed URLs**, secret access keys, session tokens, Base64-encoded file contents, or open streams into payloads. For private storage, listeners generate short-lived URLs or use authorized SDKs/identities.

An object storage reference only solves "not keeping binaries inside the event"; it still requires rules:

- The object must exist and be accessible when the listener runs.
- Object retention/TTL must outlive valid processing lifetimes.
- Listeners must enforce file size/type limits, tenant permissions, and checksums per policy.
- Object deletion jobs must coordinate with retries or delayed messages.

When events move to a broker, the serialized payload is typically the reference + small metadata; binaries are fetched on demand with size limits and safe streaming.

## 8. Runnable Java 17+ Example: Publishing an ID Instead of the Whole Order

This example runs on **plain Spring Framework**. An in-memory repository keeps the focus on event contract size; this is **not** an example demonstrating real transactions, JPA, or databases. A listener receives only `orderId` and `status`, then queries just the data it needs from the repository.

### 8.1. Project Structure

~~~text
small-payload-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── PayloadSizeDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'small-payload-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'demo.PayloadSizeDemo'
}
~~~

Spring Framework 6.2.x requires Java 17 or higher. When running inside Spring Boot, use the Boot BOM to manage compatible framework versions.

### 8.2. Complete Source Code

Save as `src/main/java/demo/PayloadSizeDemo.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class PayloadSizeDemo {

    // Internal DTO simulating a record stored in the repository.
    public record OrderDetails(
            long id,
            String customerName,
            List<String> itemCodes) {

        public OrderDetails {
            itemCodes = List.copyOf(itemCodes);
        }
    }

    // Event does not hold OrderDetails, only the information actually needed.
    public record OrderPlaced(
            long orderId,
            String status,
            Instant occurredAt) {}

    public static class OrderRepository {
        private final Map<Long, OrderDetails> orders =
                new ConcurrentHashMap<>();

        public void save(OrderDetails order) {
            orders.put(order.id(), order);
        }

        public Optional<OrderDetails> findById(long id) {
            return Optional.ofNullable(orders.get(id));
        }
    }

    public static class NotificationListener {
        private final OrderRepository repository;

        public NotificationListener(OrderRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            OrderDetails order = repository.findById(event.orderId())
                    .orElseThrow(() ->
                            new IllegalStateException(
                                    "Missing order " + event.orderId()));

            System.out.println(
                    "listener: order=" + order.id()
                    + ", status=" + event.status()
                    + ", items=" + order.itemCodes().size());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public OrderRepository orderRepository() {
            return new OrderRepository();
        }

        @Bean
        public NotificationListener notificationListener(
                OrderRepository repository) {
            return new NotificationListener(repository);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderRepository repository =
                    context.getBean(OrderRepository.class);

            repository.save(new OrderDetails(
                    101L, "Mai", List.of("SKU-A", "SKU-B")));

            System.out.println("publisher: saved order 101");

            context.publishEvent(
                    new OrderPlaced(
                            101L,
                            "CREATED",
                            Instant.parse("2026-11-11T03:00:00Z")));

            System.out.println("publisher: publishEvent returned");
        }
    }
}
~~~

### 8.3. Running and Expected Stdout

From the `small-payload-demo` directory, with JDK 17+ and Gradle installed, run:

~~~bash
gradle -q run
~~~

If the project has a Gradle Wrapper, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

The lines **printed by the application itself** will appear in order:

~~~text
publisher: saved order 101
listener: order=101, status=CREATED, items=2
publisher: publishEvent returned
~~~

Gradle and logging may emit additional lines depending on the environment.

**Explanation:**

1. The repository stores `OrderDetails` containing detailed data. In a real application this could be a database; the example uses `ConcurrentHashMap`.
2. `OrderPlaced` has only `orderId`, `status`, and `occurredAt`, holding no reference to `OrderDetails` or `List<String>`.
3. Spring uses `ApplicationEventPublisher.publishEvent(Object)` to emit the POJO record, and `@EventListener` automatically matches the exact type.
4. The default multicaster invokes listeners synchronously, so `listener: ...` appears **before** `publisher: publishEvent returned`.
5. The listener fetches data by ID and prints the item count. All detailed data lives in the repository, not the event payload.

**Demo limitation:** `OrderRepository` is in-memory with no network, transactions, or concurrent updates during execution; therefore, the example only illustrates **a small contract and synchronous flow**. Never assume the ID-only pattern is safe in all async/transaction scenarios without designing read boundaries.

## 9. Refactoring from Large Payload to Small Payload: Before–After Example

Suppose a service currently publishes:

~~~java
// Illustrating a design that needs reconsideration:
publisher.publishEvent(new OrderChanged(
        orderEntity,
        customerEntity,
        orderEntity.getLines(),
        invoicePdfBytes));
~~~

These four objects can retain a massive graph; several are mutable JPA entities or `byte[]`. Simply because a listener wants to send an "order changed" notification does not mean it needs the full data.

Alternative design:

~~~java
publisher.publishEvent(new OrderStatusChanged(
        orderId,
        previousStatus,
        currentStatus,
        Instant.now(),
        entityVersion));
~~~

In practice, both `OrderChanged` and `OrderStatusChanged` must be defined; this is an **illustrative snippet**, not standalone code. A small record like `OrderStatusChanged` informs receivers of the business fact without exposing entity structure. To display product lists, the listener can query a specific projection from the repository; if it needs the exact "list at occurrence time", consider an appropriate small snapshot.

### 9.1. Do Not Blindly Shift Costs to Listeners

Avoiding big payloads while creating 1,000 duplicate queries is equally undesirable. You can:

- Use projection queries selecting only needed fields rather than loading whole graphs.
- Batch lookups by ID if a listener processes multiple events of the same type.
- Use bounded caches when data fits, with explicit invalidation rules.
- Offload non-critical notifications to workers that do not block requests.
- Cap batch sizes, queues, worker counts, and publish rates rather than only tweaking event fields.

Good design optimizes **end-to-end cost**: heap, CPU, database, transactions, and latency.

## 10. Impact of Synchronous vs. Asynchronous Event Processing

### 10.1. Synchronous Default

With the default `SimpleApplicationEventMulticaster`, listeners execute on the publisher's thread. A large event increases memory pressure yet typically stays alive only for the duration of listener execution, unless other code retains a reference. Another major cost is listeners traversing graphs or accessing lazy associations, triggering unexpected database queries.

~~~text
publisher -> publishEvent(large event)
          -> listener A processes immediately
          -> listener B processes immediately
          -> publishEvent returns
~~~

### 10.2. When a Task Executor Is Enabled

If the multicaster is configured with `ThreadPoolTaskExecutor` or listeners use `@Async`, tasks can be **enqueued** and run later. At that point, the event/payload remains referenced by worker tasks while waiting.

~~~text
publisher -> submit event A ---\
publisher -> submit event B ----> executor queue -> worker processes
publisher -> submit event C ---/
~~~

On this path, several risks rise sharply:

- **Retained heap** grows with the number of queued events and each event's graph.
- Long queues cause listeners to process data late; IDs can go stale and records may have changed.
- Listeners do not necessarily finish in publication order, even with `@Order`.
- `ThreadLocal`, security context, MDC, and imperative transactions **do not automatically** follow onto worker threads.
- Exceptions in workers may not propagate back to the publisher.
- Overloaded executors may reject tasks or apply rejection policies; never assume `publishEvent` always equals successful processing.

Setting an executor on the multicaster also **does not mean every listener runs async**: since Spring 6.1, `ApplicationListener` implementations that do not support async at the multicaster level—including some transaction-synchronized listeners—must run on the publisher thread for the required registration phase.

### 10.3. A Queue Capacity Estimate

If each event holds its own ~200 KiB byte array, **10,000 backlogged tasks** can retain roughly **1.95 GiB of array data** (excluding overhead), even if the listener logic only needs an ID. This is merely an illustrative multiplication assuming **each event holds distinct data**, not an actual heap measurement.

In reality, retained size depends on reference sharing, object layout, queues, and garbage collectors; verify using profilers/JFR/heap dumps and real queue metrics. Never measure only the shallow size of a record and declare it safe.

## 11. Transactions and When Data Is Read by ID

A critical question: with ID-only events, **at what point does the listener read the data?**

### 11.1. Synchronous Event in the Current Transaction

If a service publishes after saving an entity yet **before commit**, a synchronous listener running inside the active transaction can see uncommitted changes. Still, the listener finishing does not mean the transaction committed; the final commit may still roll back.

If the listener sends an email at this stage, the database can roll back while the email has already gone out. That is a **timing** design bug, not a bug caused by small payloads.

### 11.2. Post-Commit Events

For operations that should only happen after a transaction succeeds, one option is:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    // Handle post-commit reaction, reading data in the appropriate scope.
}
~~~

This is an **illustrative method** requiring a Spring bean, transaction manager, and a defined `OrderPlaced` class. `@TransactionalEventListener` also defaults to `AFTER_COMMIT`; declaring it explicitly improves readability.

Things to remember:

- Under default settings, if an event is published **outside a transaction**, the transactional listener does not run unless `fallbackExecution = true` is set.
- If the listener reads the **latest** state after commit, the record may already have been updated again; if disallowed, the event needs a version/snapshot or version checks.
- If the listener writes new data after commit, do not assume a fresh transaction is active. Open an explicit new transaction when further commits are needed.
- If events must survive restarts, **Spring in-process events are not durable queues**; consider a transactional outbox, broker, and idempotent consumers.

### 11.3. Do Not Use ID-Only When an Absolute Snapshot Is Required

For example, the price at payment time approved by the customer is a business fact that must be preserved. A listener querying the current price one minute later could get a different result. In such cases, the event may need:

~~~java
public record PaymentCaptured(
        String paymentId,
        java.math.BigDecimal amount,
        String currency,
        long agreementVersion) {}
~~~

This still avoids gigantic graphs while keeping the exact minimal content that must stay immutable. For highly sensitive data, consider protective tokens/references instead of putting raw values directly into events when unnecessary.

## 12. Batch Events and Cardinality Limits

An event carrying a list of IDs can make sense when one business operation creates multiple objects, yet an unbounded list becomes an oversized payload in another way:

~~~java
// Avoid when ids may contain hundreds of thousands of entries:
public record BatchImported(java.util.List<Long> ids) {}

// Carry batch summary information only:
public record BatchImportCompleted(
        String batchId,
        long importedCount) {}
~~~

In the second approach, the listener queries rows having `batchId`, paginating in bounded chunks. If each item needs independent processing, a controlled queue/batch worker mechanism is usually better than publishing one event holding every entity.

When you genuinely send a list of IDs:

- Enforce a maximum element limit based on benchmarks.
- Copy the list at event creation time so the producer cannot mutate it after publishing.
- Consider ordered batches/windows, retries, and deduplication.
- Use pagination/keyset fetching so listeners do not reload the entire batch into memory at once.
- Avoid query explosions: batch-fetch instead of querying one ID at a time when the contract allows.

A batch reference like `batchId` must also have a long enough retention policy; if batch rows are deleted before the listener runs, shrinking the payload via reference can create hard-to-fix failures.

## 13. Boundary Rules and Data Protection

### 13.1. Keep Only Shareable Data

Shrinking payloads often reduces data-leak surface area, yet an ID alone is not automatically safe. An ID, tenant ID, or customer ID can still be sensitive. For events:

- Never put passwords, access tokens, JWTs, secrets, cookies, or card details into payloads.
- Never put an entire `SecurityContext` or `HttpServletRequest` into events; pass required facts and authenticate/authorize in the listener.
- Do not log full payloads by default if events contain PII.
- Enforce tenant boundaries when listeners query by ID; an ID taken from an event is not proof of access rights.
- If events leave the process, define schemas, data classifications, and access controls independently.

### 13.2. Behavioral Limits, Not a "Magic Threshold"

Depending on the system, you can establish policies:

- No binary files or entity graphs inside events.
- Events carry only primitives, IDs, enums, timestamps, and necessary small DTOs.
- No unbounded lists; require batch ID + pagination beyond a measured threshold.
- Every event has a clear contract between producer and consumer.
- No references to mutable objects with request/transaction lifecycles.
- With outboxes/brokers: bound **serialized bytes** based on real infrastructure limits rather than counting fields alone.

In code reviews, a useful question is: **"If 10,000 events of this type are queued waiting to be processed, which objects remain reachable?"**

## 14. Measuring and Testing to Decide Whether a Payload Is Too Large

Measure in an environment close to real workloads rather than relying on a test printing `Runtime.getRuntime().freeMemory()` before/after a single event. GC, class loading, caches, and JIT distort such numbers.

Useful metrics:

| Metric | Why |
| --- | --- |
| Serialized payload size (if using a broker) | Network/storage cost and real message size limits |
| Heap usage, allocation rate, retained objects | Evaluates RAM pressure and reference retention |
| GC pause/CPU | Detects allocation churn or heap pressure |
| Executor active threads and queue depth | Detects backlogs retaining many events |
| Publisher p95/p99 latency | Shows whether synchronous listeners slow down requests |
| Listener processing latency and errors/retries | Shows whether shifting work to repositories increases duration |
| Query count / rows fetched / N+1 | Evaluates the cost of ID-only events |
| DB transaction timeout/lock time | Detects listeners holding transactions open too long |

Tools to use: Java Flight Recorder (JFR), heap dumps/histograms, Micrometer/Actuator where available, `ThreadPoolTaskExecutor` metrics, database slow-query logs, load integration tests, and JMH for isolated microbenchmarks. If using queue consumers, also measure message lag, retries, and DLQ counts.

### 14.1. Tests to Write

1. **Schema test:** event contains only approved fields, with no entities/`byte[]` or disallowed resources.
2. **Immutability test:** if the event holds a list, mutating the original list after event creation does not alter the event's list.
3. **Synchronous test:** default listener is invoked along the expected path with sufficient projection data.
4. **Async/backlog test:** bound queues and observe heap/latency when listeners are slow and many events are published.
5. **Transaction test:** listener runs only after commit when required; no side effects occur on rollback.
6. **Stale/not-found test:** listener reacts appropriately if the entity was deleted or version changed prior to processing.
7. **Batch/load test:** with thousands of IDs, verify no `N+1` overload and no gigantic lists are constructed.
8. **Security test:** IDs never cross tenant boundaries, and payloads contain no secrets or unnecessary PII.

Do not cram everything into one unit test. Test event contracts with unit tests, and use integration tests with real configurations for transactions/async/DB.

## 15. Common Mistakes and Fixes

| Mistake / Misconception | Problem | Fix |
| --- | --- | --- |
| "Spring events auto-serialize, so large classes only affect JSON" | In-process events pass object references, impacting retained heap | Measure object graphs and reference lifetimes |
| "With multiple listeners, Spring always deep-copies entity graphs" | No default deep-copy guarantee exists | Avoid heavy payloads due to retention/mutable state; do not assume unconditional cloning |
| Publishing a full JPA entity "in case listeners need it" | ORM/lazy-loading coupling and large graph retention | Use IDs or small projections/snapshots |
| Publishing `MultipartFile`/`InputStream` directly | Lifecycle-bound resources that may close or hold huge data | Persist durably first, send only a storage reference |
| ID-only, yet listener reads on another thread before commit | Cannot see data or transaction context | Emit/register in the right phase, post-commit if needed |
| ID-only when listener needs original price | Current data has already changed | Use a small immutable snapshot with amount/version |
| Mutable list inside a record | Records are only shallowly immutable | Use `List.copyOf` for ID lists; make elements immutable |
| Unbounded queue with large events | Backlogs retain heap, causing GC pressure and OOM | Bound queues, apply backpressure, size pools, cap payload size |
| Single event holding hundreds of thousands of items | Payloads/buffers grow without bound | Batch IDs and paginate/chunk |
| Shrinking payload but causing N+1 repository fetches | Shifts cost from RAM to DB | Projections, batch queries, caching when appropriate |
| "Once `publishEvent` returns, async listeners succeeded" | Only handed off to dispatch; tasks might not have run yet | Track completion/errors, retries, observability |
| Using only `Thread.sleep` to test async | Flaky tests that do not measure real lifecycle | Latches/futures with timeouts and data assertions |
| Putting sensitive data in events/logs | Widens data exposure surface | Least-privilege payloads, do not log secrets |
| Sending internal events to a broker with the whole object graph | Serialized bytes and schemas differ from in-memory references | Design DTOs/contracts and measure actual byte sizes |

## 16. Pre-Merge Design Checklist

- [ ] Event is named after a specific business fact, and its payload expresses **exactly the required information**.
- [ ] No full JPA entity graphs, requests/sessions, streams, connections, or binary files inside events.
- [ ] If ID-only, listeners accept reading **current state**; otherwise, use a small snapshot/version.
- [ ] List fields are bounded and defensively snapshotted if mutable.
- [ ] Events contain no unnecessary secrets/PII, and listeners verify tenant/access context appropriately.
- [ ] Sync/async behavior, queue retention, rollback, and DB commit timing have been analyzed.
- [ ] Behavior is defined when records are missing, versions mismatch, tasks retry, or events replay.
- [ ] In-memory object graph size is not confused with serialized message size.
- [ ] Heap/queue/latency/query metrics exist to evaluate performance under real load.
- [ ] Spring in-process events are not used in place of an outbox/broker when durable delivery is required.

## 17. Self-Check Questions

**1.** Why can `record Event(OrderEntity order)` cause memory pressure even though the `record` has only one field?

**Answer:** That field is a reference; the event can retain the entire object graph reachable from the entity, especially when tasks pile up in a queue. A record does not shrink the underlying graph.

**2.** If a listener only needs an ID to query the current state, which payload should be chosen?

**Answer:** A small event containing the ID and genuinely needed metadata. No need to carry the full entity graph or attachments.

**3.** If a listener must use the amount at payment time, is ID-only sufficient?

**Answer:** Not always. Use a small immutable snapshot such as `paymentId`, `amount`, `currency`, and `agreementVersion`; if re-reading, ensure point-in-time accuracy.

**4.** Can you publish events containing large PDF `byte[]` arrays because "Spring does not serialize"?

**Answer:** You should not. Not serializing by default does not eliminate heap storage costs and reference retention; a storage reference is normally the right solution.

**5.** Is `@TransactionalEventListener(AFTER_COMMIT)` guaranteed to always run?

**Answer:** No. Without a transaction and with `fallbackExecution` defaulting to `false`, the listener does not run. If commit fails/rolls back, `AFTER_COMMIT` callbacks do not fire as a successful commit.

**6.** Is switching to ID-only always faster?

**Answer:** No. If every listener triggers too many queries, overall cost can worsen; use projections, batch fetching, and real measurements.

**7.** Why is `List.copyOf(ids)` helpful for batch events?

**Answer:** It keeps the event's list structure from being mutated by additions/removals from the producer after creation and blocks mutations through the event. It does not deep-copy mutable elements.

## 18. References

- Spring Framework `ApplicationEventPublisher` — event publication and payload objects: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework `PayloadApplicationEvent`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Spring Framework `SimpleApplicationEventMulticaster` — default synchronous dispatch, executor, and error handling: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference — Standard and Custom Events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Reference — Observability Support and context propagation: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Java Flight Recorder / JDK Flight Recorder: https://docs.oracle.com/en/java/javase/17/jfapi/

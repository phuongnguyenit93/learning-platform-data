# Avoiding Shared Mutable State

## Lesson Objectives

In the **Concurrency and Scaling** chapter, this lesson explains why concurrent Kafka listeners must avoid sharing mutable state across multiple processing threads. With Spring Kafka, a listener endpoint can create multiple child consumer containers; these consumers can invoke the same listener bean almost simultaneously. If the listener or a service holds mutable data in shared fields, the application can suffer race conditions, lost updates, corrupted data, and hard-to-reproduce bugs.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`, while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing. When increasing concurrency or running multiple instances, safe state design is essential for scaling consumers without corrupting business results.

After this lesson, learners can:

- Understand why listener beans are by default shared across multiple consumer threads.
- Identify shared mutable state and common race conditions.
- Design stateless listeners and prefer immutable objects.
- Distinguish local variables, bean fields, static fields, and external state.
- Choose `AtomicLong`, `LongAdder`, `ConcurrentHashMap`, or locks for the right purpose.
- Protect business invariants with transactions and appropriate storage mechanisms.
- Avoid bugs when handling batches, asynchronous callbacks, and retries.
- Test thread safety and monitor concurrency bugs in production.

## 1. Why Can Kafka Consumers Process Concurrently?

In Spring Kafka, `ConcurrentKafkaListenerContainerFactory` can create a `ConcurrentMessageListenerContainer` managing multiple child containers. Each child container owns its own Kafka consumer and runs its own poll/listener loop.

Example:

~~~java
factory.setConcurrency(3);
~~~

An endpoint with concurrency 3 can have three consumer threads invoking the same listener method. In Spring, listeners are normally singleton beans, so these threads invoke methods on the same listener object.

~~~mermaid
flowchart TD
    A["@KafkaListener singleton bean"] --> B["Listener method"]
    C["Consumer thread 1"] --> B
    D["Consumer thread 2"] --> B
    E["Consumer thread 3"] --> B
    B --> F["Shared service dependencies"]
~~~

If the application has two replicas, each replica can create three more consumers. There are then six consumers in the same group, concurrently invoking singleton beans inside each process.

Concurrency comes from several places:

- Listener container `concurrency`.
- Multiple application instances/replicas.
- Multiple listener endpoints sharing a single service bean.
- Executors or asynchronous callbacks created by the application.
- Scheduled jobs, HTTP requests, or other processing flows accessing the same bean.

Never assume a listener method is invoked by only one thread. Your design must verify whether every shared dependency is safe under concurrent calls.

## 2. What Is Shared Mutable State?

State is data an object retains across multiple processing invocations. Mutable state is data that can change after the object is created.

Example of a listener with a field:

~~~java
@Service
public class OrderListener {

    private int processedCount;

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void listen(OrderCreated event) {
        processedCount++;
        // Process the event.
    }
}
~~~

`processedCount` is mutable state in a singleton bean. When multiple consumer threads call `listen()` at the same time, they read and write this field concurrently.

Common sources of shared mutable state:

- Fields on singleton `@Component`, `@Service`, and `@Repository` beans.
- `static` fields.
- `ArrayList`, `HashMap`, and `HashSet` accessed by multiple threads.
- Cached DTOs or domain objects mutated directly.
- Non-thread-safe buffers, formatters, or builders.
- Variables in service objects injected into multiple listeners.
- Custom caches or registries holding mutable values inside.
- Data held in singletons to track processing progress.

Not every field is dangerous. A `final` field pointing to an immutable object is generally safe to share. However, `final` only prevents reassigning the reference; it does not make the referenced object immutable.

~~~java
private final List<String> topics = new ArrayList<>();
~~~

The `topics` reference cannot be reassigned to another list, but the list's contents can still be modified, and `ArrayList` is unsafe when multiple threads read and write concurrently.

## 3. Race Conditions and Lost Updates

A race condition occurs when the outcome depends on the order or timing of threads accessing shared state.

For example, `processedCount++` is not an atomic operation. Logically, it consists of:

1. Reading the current value.
2. Adding one.
3. Writing the new value.

Suppose the initial value is 10:

~~~text
Thread A reads 10
Thread B reads 10
Thread A writes 11
Thread B writes 11

Result: 11
Expected: 12
~~~

One increment is lost. This is a lost update.

Similar bugs can occur when:

- Two threads simultaneously check that an order does not exist and both create an invoice.
- Two threads simultaneously update a balance based on a stale value.
- One thread adds an element while another thread iterates an `ArrayList`.
- One thread mutates a cached object while another thread reads it.
- Two threads simultaneously update state through a non-atomic sequence of steps.

Concurrency bugs are often hard to reproduce because they depend on thread scheduling, system load, and I/O timing. A single test may pass repeatedly even when the code still has a race condition.

## 4. Visibility and Memory Consistency Issues

Even without an obvious lost update, one thread may not immediately observe another thread's changes if the program does not establish proper synchronization relationships.

Example:

~~~java
public class ListenerState {

    private boolean stopped;

    public void stop() {
        stopped = true;
    }

    public void work() {
        while (!stopped) {
            // Continue working.
        }
    }
}
~~~

If `stop()` and `work()` run on two different threads, the `stopped` field lacks a visibility mechanism. The thread running the loop is not guaranteed to observe the change as intended by the application.

Using `volatile` can guarantee visibility for an independent flag:

~~~java
private volatile boolean stopped;
~~~

However, `volatile` does not make compound operations like `count++` atomic. Nor does it protect invariants spanning multiple fields.

Choose the right tool:

- `volatile`: visibility for a single independently read/written value.
- `AtomicInteger`/`AtomicLong`: atomic operations on a single variable.
- `synchronized`/`Lock`: protecting regions of operations requiring atomicity and invariants.
- Concurrent collections: protecting collection structure according to their contracts.
- Database transactions/constraints: protecting business data shared across multiple processes.

## 5. Prefer Stateless Listeners

A stateless listener does not hold mutable business state across invocations. It receives an event, calls a service to process it, and returns.

Example:

~~~java
@Service
public class OrderCreatedListener {

    private final BillingService billingService;

    public OrderCreatedListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void listen(OrderCreated event) {
        billingService.createInvoice(event);
    }
}
~~~

The method does not modify any listener fields. Data for a single execution resides in parameters and local variables.

Normal local variables belong to the method invocation's stack frame. Each thread has its own invocation, so local variables cannot be directly modified by other threads.

~~~java
public void listen(OrderCreated event) {
    String orderId = event.orderId();
    BigDecimal total = calculateTotal(event);

    billingService.createInvoice(orderId, total);
}
~~~

Stateless does not mean the whole application has no state. It means the listener does not rely on in-memory mutable state of the bean to coordinate across invocations. Business state should live in a place with proper concurrency controls such as a database, thread-safe cache, or dedicated state store.

## 6. Prefer Immutable Objects

Immutable objects do not allow state modifications after creation. They are easy to share across threads because there are no writes after initialization.

Java records are a strong choice for event DTOs:

~~~java
public record OrderCreated(
    String orderId,
    String customerId,
    BigDecimal total
) {
}
~~~

Record fields are `final` and records provide no setters. Multiple listener threads can read the same instance without locks if inner components are also immutable or unmutated.

Note that immutability is only truly safe when the entire object graph contains no shared mutable objects. For example:

~~~java
public record OrderSnapshot(List<String> itemIds) {
}
~~~

This record does not automatically make the list immutable. If the caller keeps the original list and mutates it, the snapshot still observes that change.

You can make a defensive copy:

~~~java
public record OrderSnapshot(List<String> itemIds) {

    public OrderSnapshot {
        itemIds = List.copyOf(itemIds);
    }
}
~~~

`List.copyOf` creates an unmodifiable list through a new reference and prevents structural changes to the original list from affecting the snapshot. Inner elements must also be immutable if shared.

## 7. Use Local Variables Instead of Temporary Fields

Do not store data from the current invocation in a singleton field.

Unsafe:

~~~java
@Service
public class OrderListener {

    private OrderCreated currentEvent;

    @KafkaListener(topics = "commerce.order.created")
    public void listen(OrderCreated event) {
        currentEvent = event;
        billingService.process(currentEvent);
    }
}
~~~

Two threads can overwrite each other's `currentEvent`. Thread A can call the service with Thread B's event.

Safer:

~~~java
@Service
public class OrderListener {

    @KafkaListener(topics = "commerce.order.created")
    public void listen(OrderCreated event) {
        billingService.process(event);
    }
}
~~~

If a temporary variable is needed, declare it inside the method. Do not use a field merely to pass data between lines within a single invocation.

When state must be held across multiple records, explicitly define its scope and synchronization mechanism. Never use a singleton field to hold the "current record" or "current batch".

## 8. Thread-Safe Collections and Their Limits

If you genuinely need a collection shared across multiple threads, choose a structure whose contract supports concurrency.

Example:

~~~java
private final Map<String, OrderSnapshot> cache =
    new ConcurrentHashMap<>();
~~~

`ConcurrentHashMap` allows multiple threads to access and update map structure safely per its supported operations.

However, that does not automatically make value objects inside thread-safe:

~~~java
private final Map<String, MutableOrderState> states =
    new ConcurrentHashMap<>();
~~~

If two threads retrieve the same `MutableOrderState` and modify its fields, race conditions still occur. `ConcurrentHashMap` only protects operations on the map, not all operations on values.

For append-mostly, read-heavy lists, consider `CopyOnWriteArrayList` when writes are infrequent and reads are frequent. This collection copies its underlying array on writes, making it unsuitable for write-heavy workloads or large lists.

Do not use `Collections.synchronizedList` as an automatic cure-all. When iterating over the collection, external synchronization per the wrapper's contract is still required to avoid concurrent modification.

Example of synchronized list iteration:

~~~java
List<String> synchronizedTopics =
    Collections.synchronizedList(new ArrayList<>());

synchronized (synchronizedTopics) {
    for (String topic : synchronizedTopics) {
        log.info("Topic: {}", topic);
    }
}
~~~

All other code adding, removing, or iterating the list must follow the same synchronization rule. When possible, prefer not sharing mutable lists or use immutable snapshots.

## 9. `AtomicLong`, `LongAdder`, and Atomic Operations

For an independent counter, `AtomicLong` can be used:

~~~java
@Service
public class ListenerMetrics {

    private final AtomicLong processedCount = new AtomicLong();

    public void markProcessed() {
        processedCount.incrementAndGet();
    }

    public long processedCount() {
        return processedCount.get();
    }
}
~~~

`incrementAndGet()` is an atomic operation. Multiple threads incrementing the counter will not suffer lost updates.

If only metric counting under high write load is needed, `LongAdder` can reduce contention:

~~~java
private final LongAdder processedCount = new LongAdder();

public void markProcessed() {
    processedCount.increment();
}

public long processedCount() {
    return processedCount.sum();
}
~~~

`LongAdder` fits aggregate statistics. The value of `sum()` during concurrent updates is not an absolute atomic snapshot. Do not use it to issue unique sequence numbers or guard business decisions.

### 9.1. Atomics Do Not Protect Multi-Step Business Logic

Example using `AtomicInteger` for inventory quantity:

~~~java
if (stock.get() > 0) {
    stock.decrementAndGet();
}
~~~

This snippet still has a logical race condition. Two threads can both read `stock` as 1 and both decrement it, resulting in -1.

You can use a compare-and-set loop:

~~~java
boolean reserveOne(AtomicInteger stock) {
    while (true) {
        int current = stock.get();

        if (current <= 0) {
            return false;
        }

        if (stock.compareAndSet(current, current - 1)) {
            return true;
        }
    }
}
~~~

This protects the check-and-decrement on a single atomic variable inside one process. However, if inventory resides in a database updated by multiple application instances, an `AtomicInteger` in each process is insufficient. Atomic updates or locking in the database are required.

## 10. `ConcurrentHashMap` and Compound Operations

Do not split a "check then insert" operation into two steps when multiple threads execute concurrently:

~~~java
if (!states.containsKey(orderId)) {
    states.put(orderId, new OrderState());
}
~~~

Two threads can both see the key missing and both create state. Use an atomic operation like `computeIfAbsent`:

~~~java
OrderState state = states.computeIfAbsent(
    orderId,
    ignored -> new OrderState()
);
~~~

The mapping function should be short, perform no long I/O, and avoid updating back into the same map in a re-entrant manner.

If the `OrderState` object is mutable and modified by multiple threads, synchronize the state separately or switch to immutable state updates:

~~~java
private final ConcurrentHashMap<String, OrderSnapshot> states =
    new ConcurrentHashMap<>();

public void update(String orderId, OrderEvent event) {
    states.compute(orderId, (key, current) ->
        apply(current, event)
    );
}
~~~

In this example, `apply` should return a new snapshot without mutating the `current` object. `compute` ensures replacing the key's value happens atomically per the map's contract. Do not use this approach to replace transactions for data requiring coordination across multiple keys or systems.

## 11. When to Use `synchronized` or `Lock`?

When an invariant requires multiple operations to execute together as a unit, `synchronized` or `Lock` can be used.

Example:

~~~java
public class InMemoryInventory {

    private int available;

    public synchronized boolean reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            return false;
        }

        available -= quantity;
        return true;
    }
}
~~~

The `synchronized` block protects checking and decrementing the quantity inside one object on a single JVM.

Drawbacks:

- Threads must wait for each other when entering the critical section.
- Broad locks reduce concurrency and throughput.
- Locks apply only within that process/JVM.
- Does not protect state if another process accesses the same data elsewhere.

If using `ReentrantLock`, always unlock in `finally`:

~~~java
private final Lock lock = new ReentrantLock();

public void update() {
    lock.lock();
    try {
        // Critical section.
    } finally {
        lock.unlock();
    }
}
~~~

Avoid holding locks while calling HTTP, databases, or slow operations whenever possible. Keep critical sections short and clearly scoped.

## 12. Business State Should Be Protected in Authoritative Storage

Spring Kafka consumers often run across multiple threads and multiple instances. A `synchronized` block or `AtomicLong` inside a JVM cannot synchronize state across replicas.

For example, two instances simultaneously process order events and update inventory. Both have their own `AtomicInteger`. Each instance may believe stock remains even though the total quantity was already reserved by the other instance.

For critical business state, use storage mechanisms capable of concurrent coordination:

- Database transactions.
- Unique constraints or optimistic locking.
- Atomic update statements.
- Redis atomic operations or distributed locks when appropriate.
- Inbox/idempotency tables to prevent duplicate processing.
- Kafka Streams state stores when the problem requires stateful stream processing by key.

Example of optimistic locking with JPA:

~~~java
@Entity
public class Inventory {

    @Id
    private String productId;

    private int available;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }

        available -= quantity;
    }
}
~~~

`@Version` allows the persistence provider to detect competing updates. When two transactions modify the same version concurrently, one transaction can fail with an optimistic lock conflict and must retry per business policy.

A conditional update statement can also guard stock deduction:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

Check the updated row count. If it equals 0, stock is insufficient or the record does not exist. The database executes the check and update as an atomic statement under the DBMS's semantics.

## 13. Idempotency and Duplicate Delivery

A Kafka consumer can receive a record again if processing completes before offsets are committed, or if retries/rebalances cause redelivery. Therefore, never use an in-memory `Set` in a singleton listener as a long-term deduplication mechanism.

Example of an insufficiently safe approach:

~~~java
private final Set<String> processedEventIds =
    ConcurrentHashMap.newKeySet();

public void process(OrderCreated event) {
    if (processedEventIds.add(event.eventId())) {
        billingService.createInvoice(event);
    }
}
~~~

This set exists only inside a single JVM. Data is lost on restart; with multiple replicas, each replica has its own set. Two instances can process the same event simultaneously.

A more reliable approach is storing the event ID in the database with a unique constraint inside the same transaction as the business change:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Inside the transaction:

1. Attempt to insert the event ID.
2. If the insert succeeds, apply the business change.
3. If a unique constraint violation occurs, the event was already processed; ignore according to policy.
4. Commit the database transaction.
5. Let the listener complete so the container commits the Kafka offset.

Design unique violation handling appropriately for your transaction manager and database driver. The goal is for marking the event processed and applying the business change to commit or roll back together.

## 14. Do Not Share Mutable State Through Async Callbacks

A listener may call `KafkaTemplate.send()` or an executor. Callbacks typically run on a different thread. Do not assume callbacks run on the consumer thread.

Dangerous example:

~~~java
private OrderCreated currentEvent;

public void listen(OrderCreated event) {
    currentEvent = event;

    kafkaTemplate.send("billing.audit", event)
        .whenComplete((result, error) -> {
            auditService.record(currentEvent, error);
        });
}
~~~

Another listener invocation can overwrite `currentEvent` before the first callback executes. The callback would record the audit for the wrong event.

Capture an immutable local variable in the callback:

~~~java
public void listen(OrderCreated event) {
    OrderCreated current = event;

    kafkaTemplate.send("billing.audit", current)
        .whenComplete((result, error) -> {
            auditService.record(current, error);
        });
}
~~~

`current` belongs to the current invocation and is captured by the callback via closure. This is safe if `OrderCreated` is immutable and dependencies called from the callback are also thread-safe.

If the listener must wait for the send to finish before committing the offset, await the future or use an async listener mechanism supported by your Spring Kafka version. Returning from the listener before critical work finishes can cause the container to commit offsets too early.

## 15. `ThreadLocal` Is Not Event State Storage

`ThreadLocal` holds per-thread values, which can be useful for short-lived context such as a correlation ID in a synchronous flow. However, it should not be used to store consumer business state.

Problems:

- Async callbacks may run on different threads and miss the value.
- Container threads are reused across many records.
- Old values can leak into the next invocation if not cleaned up.
- `ThreadLocal` does not share state across replicas.
- Context propagation across executors is not guaranteed.

If `ThreadLocal` must be used, always clean up in `finally`:

~~~java
try {
    RequestContext.set(traceId);
    billingService.process(event);
} finally {
    RequestContext.clear();
}
~~~

Prefer passing context explicitly via parameters or using intentional context propagation mechanisms rather than relying on implicit `ThreadLocal`.

## 16. Batch Listeners and Mutable State

A batch listener receives `List<ConsumerRecord<K,V>>`. The list belongs to that listener invocation, but should not be shared with another thread and mutated after the listener returns.

Do not do this:

~~~java
private List<ConsumerRecord<String, OrderCreated>> currentBatch;

public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    currentBatch = records;
    executor.submit(() -> process(currentBatch));
}
~~~

The next batch invocation can overwrite `currentBatch`. The older task may mistakenly process the new batch.

Create a local snapshot and pass it directly:

~~~java
public void listen(List<ConsumerRecord<String, OrderCreated>> records) {
    List<OrderCreated> events = records.stream()
        .map(ConsumerRecord::value)
        .filter(Objects::nonNull)
        .toList();

    processBatchAndWait(events);
}
~~~

If offloading to an executor, wait for tasks to finish before the listener returns or manage acknowledgement/offsets through a supported async mechanism. `List.copyOf(records)` only copies the list structure; it does not make `ConsumerRecord` or mutable payloads inside immutable.

## 17. Do Not Use Static Mutable State to Share Across Consumers

A `static` field exists at the classloader/JVM level, not as a distributed state store.

Example:

~~~java
public class ConsumerState {
    public static final Map<String, Integer> COUNTS =
        new HashMap<>();
}
~~~

If multiple listener threads update `COUNTS`, `HashMap` can suffer race conditions. Switching to `ConcurrentHashMap` only protects the map structure, while value update logic must still be safe.

Moreover, each application replica has its own static map. Static fields do not synchronize across pods or servers.

Only use static immutable constants for immutable configuration data. Avoid static mutable caches unless concurrency, eviction, memory bounds, and cross-instance synchronization are properly designed.

## 18. Per-Partition State and Processing Order

Some problems want in-memory state keyed by partition or record key. This is possible if you control assignment, thread ownership, rebalances, restarts, and state recovery. This is far more complex than storing a map in a listener.

Points to consider:

- Partitions can move to another consumer during a rebalance.
- Consumers can restart and lose RAM state.
- A key can route to a different partition after adding partitions or changing partitioners.
- Multiple application instances do not share local maps.
- State must be restored or rebuilt from a changelog/database.

If logic requires stateful processing by key, windowing, joins, or recoverable state stores, consider Kafka Streams. Kafka Streams provides task/partition ownership and changelog-backed state stores under a stream-processing model instead of manually managing mutable maps inside listeners.

In a standard Spring Kafka listener, relying solely on "the same partition is handled by one consumer" is insufficient to guarantee local state always exists or always stays on the same thread across rebalances.

## 19. Transaction Annotations and Thread Boundaries

Spring's `@Transactional` normally binds the transaction context to the executing thread. If a listener hands off work to an executor, the listener thread's transaction does not automatically follow the new task.

Example:

~~~java
@Transactional
public void listen(OrderCreated event) {
    executor.submit(() -> billingService.createInvoice(event));
}
~~~

The transaction wrapping `listen()` may complete before the task finishes running. The task may run outside the intended transaction.

If a transaction is needed for async work, call a service method that opens its own transaction inside the task, or use an explicitly supported transaction management mechanism. Never share non-thread-safe `EntityManager`/sessions across threads.

Similarly, do not assume security context, MDC, or tracing context propagates automatically to executors. Use intentional context propagation and clear context after the task completes.

## 20. Be Careful with Injected Dependencies

A stateless listener can still be unsafe if a dependency it calls holds non-thread-safe mutable state.

Example:

~~~java
@Service
public class BillingService {

    private final SimpleDateFormat formatter =
        new SimpleDateFormat("yyyy-MM-dd");

    public String format(Date date) {
        return formatter.format(date);
    }
}
~~~

`SimpleDateFormat` is not thread-safe. Multiple listener threads calling the same service can produce corrupted output or errors.

Use immutable/thread-safe `DateTimeFormatter`:

~~~java
private static final DateTimeFormatter FORMATTER =
    DateTimeFormatter.ISO_LOCAL_DATE;

public String format(LocalDate date) {
    return FORMATTER.format(date);
}
~~~

When reviewing listeners, inspect the entire dependency graph:

- Are formatters, parsers, and builders mutable?
- Are there collection fields that get mutated?
- Are there clients or sessions designed for single-thread use?
- Are there shared buffers?
- Are there hand-rolled caches?
- Do methods return mutable objects that callers subsequently mutate?

Many libraries such as `KafkaTemplate` are designed to be shared across a Spring application, but do not generalize that every injected object is thread-safe. Verify each class's contract.

## 21. Testing Thread Safety

Standard unit tests with single sequential calls miss many race conditions. Controlled concurrent load must be generated.

Example testing a counter:

~~~java
@Test
void shouldCountConcurrentUpdates() throws Exception {
    int workers = 8;
    int incrementsPerWorker = 10_000;

    AtomicLong count = new AtomicLong();
    ExecutorService executor =
        Executors.newFixedThreadPool(workers);

    CountDownLatch ready = new CountDownLatch(workers);
    CountDownLatch start = new CountDownLatch(1);

    List<Future<?>> tasks = new ArrayList<>();

    for (int worker = 0; worker < workers; worker++) {
        tasks.add(executor.submit(() -> {
            ready.countDown();
            start.await();

            for (int i = 0; i < incrementsPerWorker; i++) {
                count.incrementAndGet();
            }

            return null;
        }));
    }

    try {
        assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
        start.countDown();

        for (Future<?> task : tasks) {
            task.get(10, TimeUnit.SECONDS);
        }

        assertThat(count.get())
            .isEqualTo((long) workers * incrementsPerWorker);
    } finally {
        executor.shutdownNow();
    }
}
~~~

This test illustrates synchronizing start timing to induce contention. The `finally` block shuts down the executor even if assertions or futures fail, preventing thread leaks in tests.

### 21.1. Testing Concurrent Listeners

For Kafka integration tests:

1. Create a multi-partition topic.
2. Configure listener concurrency greater than 1.
3. Send multiple events with varied key distributions.
4. Generate enough concurrent load for multiple consumers to receive partitions.
5. Verify the exact count of processed events and zero lost updates.
6. Verify database constraints and idempotency when sending duplicates.
7. Restart or rebalance consumers under load if recovery testing is needed.

Use `CountDownLatch`, `CyclicBarrier`, Awaitility, or a test probe for synchronization. Avoid fixed `Thread.sleep()` calls because they do not guarantee threads reach contended sections together.

### 21.2. Race Condition Testing Cannot Rely on a Single Pass

Race conditions depend on thread scheduling. Running stress tests for many iterations increases detection probability, but does not mathematically prove code is thread-safe.

Combine:

- Reviewing state ownership.
- Verifying dependency thread-safety contracts.
- Unit testing concurrent operations.
- Integration testing with listener concurrency.
- Testing duplicates, rebalances, and restarts.
- Monitoring metrics and logs in staging environments.

## 22. Monitoring Concurrency in Production

Signals that help detect bugs or contention caused by shared state:

| Signal | What to Observe |
|---|---|
| Consumer concurrency | Actual child consumer count and replica count |
| Listener processing time | Processing duration and variance across invocations |
| Consumer lag | Lag by group and partition |
| Error/retry rate | Errors rising as concurrency increases |
| Database conflicts | Optimistic lock conflicts, deadlocks, or unique violations |
| Lock wait time | Threads waiting on locks and overly long critical sections |
| Thread pool queue | Async tasks backing up in queues |
| Heap/cache size | Unbounded growth of mutable caches |
| Duplicate event count | Events redelivered or processed repeatedly |
| Rebalance frequency | Unstable consumer membership |

When increasing concurrency, monitor throughput and error rate together. Rising throughput alongside surging duplicates, database conflicts, or latency may indicate shared state is causing contention or data corruption.

## 23. Common Design Mistakes

| Design | Risk | Remediation |
|---|---|---|
| `count++` in a singleton field | Lost updates | `AtomicLong`/`LongAdder` if solely for metrics |
| Shared `ArrayList` across listener threads | Race conditions and structural corruption | Local lists or appropriate collections |
| Shared `HashMap` | Concurrent modification/corruption | `ConcurrentHashMap` or a state store |
| `ConcurrentHashMap` holding mutable values | Race conditions inside values | Immutable values, atomic `compute`, or locks |
| `currentEvent` field | Threads overwrite each other's events | Use parameters/local variables |
| Static mutable cache | Not thread-safe and not shared across replicas | Cache with concurrency/eviction or external store |
| `ThreadLocal` without cleanup | Context leaks to subsequent invocations | `try/finally` and clear |
| Callback reading mutable field | Callback reads the wrong data | Capture immutable local variables |
| Submitting task then returning from listener | Offsets committed before task finishes | Await task or use controlled async acknowledgement |
| `synchronized` on entire listener | Throughput drops, lock contention | Shrink critical section or design statelessly |
| Using Atomics to guard multiple fields | Invariants can still break | Locks, transactions, or atomic updates |
| Using RAM for deduplication | State lost on restart and diverges per replica | Inbox/unique constraint in database |

## 24. Checklist Before Increasing Concurrency

- [ ] Listener bean does not hold the current event or batch in a mutable field?
- [ ] Temporary variables are kept local per invocation?
- [ ] Shared DTOs/events are immutable or defensively copied?
- [ ] Service dependencies have been checked for thread safety?
- [ ] Shared collections have appropriate concurrency contracts?
- [ ] Atomics are used only for operations on independent variables?
- [ ] Multi-step invariants are protected by appropriate locks/transactions?
- [ ] Critical business state resides in authoritative storage?
- [ ] Idempotency does not rely on an in-memory Set/Map?
- [ ] Callbacks do not read mutable fields that can be overwritten?
- [ ] Async tasks finish before offset commits or use explicit acknowledgement mechanisms?
- [ ] `ThreadLocal` is properly cleaned up?
- [ ] Transactions and context propagation are handled properly across thread boundaries?
- [ ] Tests cover concurrent load, duplicates, rebalances, and restarts?
- [ ] Consumer lag, lock waits, database conflicts, and retry rates are monitored?

## Conclusion

When Spring Kafka increases concurrency, multiple consumer threads can invoke the same singleton listener bean and the same service dependencies. Mutable state in fields, static collections, or shared object caches can cause race conditions, lost updates, and inconsistent data. Prefer stateless listeners, local variables, and immutable objects; use atomics, concurrent collections, or locks only when state sharing is genuinely needed and within each mechanism's limits.

Business state requiring consistency across threads or application instances should be protected by transactions, constraints, optimistic locking, or appropriate state stores. In particular, never use in-memory state to replace durable idempotency, never return from a listener before asynchronous work completes, and always test under realistic concurrency. Explicit state ownership lets you raise consumer concurrency while keeping processing results reliable.

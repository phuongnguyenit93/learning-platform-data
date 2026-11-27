# Keeping Functions Stateless and Avoiding Unsafe Shared State

In Spring Cloud Stream, `Supplier`, `Function`, and `Consumer` beans are typically registered as Spring beans and connected to a broker through bindings. A standard Spring bean has singleton scope: the same instance can serve many invocations throughout the application's lifetime. Depending on the binder, consumer concurrency, and deployment topology, multiple messages may be processed concurrently. Therefore, event-processing functions should keep per-invocation data in local variables and avoid storing mutable business data in shared fields.

A stateless design ensures each message can be processed independently, tested easily, and scaled by adding consumers or instances. When business logic genuinely requires state across multiple messages, that state needs a clear owner and update mechanism—such as a transactional database or a Kafka Streams state store. An in-memory shared Java field does not automatically become a safe state store for distributed systems.

## 1. Understanding Stateless Functions

An event-processing function can be considered stateless when the result and side effects of an invocation do not depend on temporary data retained from prior invocations inside the function object itself. The function reads the incoming message, executes business rules, and returns a result or performs side effects through a component dedicated to persistence.

For example, an order validation function can receive `OrderCreated`, validate the total amount and line items, and produce `OrderValidated`. All data needed for that invocation is contained in the message or read from dependent services:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total,
        List<OrderItem> items) {}

public record OrderValidated(
        String eventId,
        String orderId,
        BigDecimal total) {}

@Bean
Function<OrderCreated, OrderValidated> validateOrder(OrderPolicy policy) {
    return event -> {
        policy.validate(event);
        return new OrderValidated(
                event.eventId(),
                event.orderId(),
                event.total());
    };
}
```

The function does not retain `event` in a field for the next invocation. Each invocation has its own `event` variable. The injected `OrderPolicy` object must also have a thread-safe contract when used concurrently: prefer a service that holds no per-request mutable state, or a service managing state through a concurrency-controlled data store.

In Spring Cloud Stream's functional model, the core roles are:

| Function Type | Stateless Usage |
|---|---|
| `Supplier<T>` | Produces a new message from a data source or current time; does not rely on a mutable counter field to generate content |
| `Function<T, R>` | Transforms a message into a result; intermediate data belongs to the current invocation |
| `Consumer<T>` | Performs an action for a message; durable state is persisted through a repository or dedicated service |

A heartbeat `Supplier` can generate a fresh timestamp and identifier on each emission:

```java
public record Heartbeat(Instant emittedAt, UUID eventId) {}

@Bean
Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat(Instant.now(), UUID.randomUUID());
}
```

Using a clock and UUID generator does not require retaining a shared business variable. If you need a monotonically increasing sequence number across restarts or across multiple instances, use a properly synchronized unique sequence generator rather than an `int counter` in the bean.

## 2. Why Shared State Easily Causes Bugs

Spring manages beans with singleton scope by default. When a function is registered as a bean, the binder may invoke that same instance from different processing threads. Concurrency depends on binder configuration, partition count, consumer count, instance count, and deployment layout. Do not assume each message gets its own bean copy or that all invocations run sequentially.

The following example has a data race bug:

```java
@Bean
Consumer<OrderCreated> unsafeOrderHandler() {
    List<String> processedOrders = new ArrayList<>();

    return event -> {
        processedOrders.add(event.orderId());
        System.out.println("Processed: " + processedOrders.size());
    };
}
```

`ArrayList` is not designed for concurrent writes from multiple threads. Two invocations can mutate its internal structure simultaneously, causing missing entries, inconsistent state, or access exceptions. Even if replaced with `Collections.synchronizedList`, that list still lives only in one process, lacks durability, and cannot coordinate across instances.

**Note:** A variable declared inside the bean factory method and captured by the lambda still represents state living alongside the lambda object. Declaring the variable inside the bean creation method does not make it a local variable per invocation.

Common types of shared state that cause problems include:

- `ArrayList`, `HashMap`, `HashSet`, or mutable objects updated across multiple invocations.
- Counters, running totals, or inventory quantities stored in fields or `static` variables.
- A non-thread-safe `DateFormat`, builder, or library object reused across calls.
- Caches lacking size bounds, expiration policies, synchronization, and clear invalidation rules.
- A mutable payload stored and later mutated while another thread is still using it.

These bugs can be hard to reproduce on a developer's machine because they only emerge under higher load, parallel partition processing, or multi-instance deployments.

## 3. Organizing Data by Ownership Scope

Identify which scope data belongs to before choosing where to store it:

| Data Scope | Examples | Appropriate Location |
|---|---|---|
| Single invocation | Payload, validation results, temporary variables | Local variables inside the lambda or called method |
| Single message passed across steps | `eventId`, `orderId`, `occurredAt`, business data | Immutable payload and headers with an explicit contract |
| Durable business state | Inventory, order status, processed markers | Database or storage service with transactions and concurrency control |
| Stream-aggregated state | Order count per customer, windowed metrics | Kafka Streams state store or appropriate stateful stream processor |
| Reconstructible auxiliary data | Reference metadata, infrequently changing config | Bounded cache with expiration policy and clear synchronization rules |

### 3.1. Keep Per-Invocation Data in Local Variables

Local variables are created inside the function body on every execution. As long as mutable references do not escape or get shared with other threads, each invocation has its own isolated data area:

```java
@Bean
Function<OrderCreated, OrderValidated> validateOrder(OrderPolicy policy) {
    return event -> {
        BigDecimal normalizedTotal = event.total().setScale(2, RoundingMode.HALF_UP);
        List<OrderItem> validItems = event.items().stream()
                .filter(item -> item.quantity() > 0)
                .toList();

        policy.validate(normalizedTotal, validItems);

        return new OrderValidated(
                event.eventId(),
                event.orderId(),
                normalizedTotal);
    };
}
```

The list produced by the stream is scoped to the current invocation. Do not assign that list to a bean field or return a mutable reference shared across multiple consumers. Remember that local variables are only scope-safe if the objects they point to are not concurrently mutated elsewhere.

### 3.2. Prefer Immutable Payloads

Immutable payloads reduce the risk of one processing step mutating data that another step is reading. Java `record` types suit many message DTOs because components are assigned at construction time and have no setters:

```java
public record OrderItem(String productId, int quantity) {}

public record OrderCreated(
        String eventId,
        String orderId,
        List<OrderItem> items) {

    public OrderCreated {
        items = List.copyOf(items);
    }
}
```

A `record` only guarantees shallow immutability. If an inner component is a mutable object, that component can still be mutated through another reference. In the example, `List.copyOf` creates a list that cannot be modified via the `List` API, and `OrderItem` is a record holding only immutable values. For deeply nested payloads, copy or use immutable types at every appropriate level.

Do not mutate an incoming message directly to attach processing results. Create a new output message or use a dedicated result type so input and output contracts remain clear.

### 3.3. Use Dependencies with Thread-Safe Contracts

Beans injected into a function may be singletons just like the function itself. That does not mean every dependency is unsafe; it means the team must understand their usage contracts.

- Stateless services typically coordinate calls to repositories or connection-managed clients.
- Spring Data repositories and transaction managers are designed to work through Spring's management layer, though transaction boundaries and data updates still require proper design.
- Custom objects with mutable fields must be synchronized or replaced with a non-shared-state design.
- Do not hold an `EntityManager`, JDBC connection, or transaction context in a field for reuse across invocations; let Spring manage resource scoping.

For example, a consumer can call a transactional service rather than keeping an inventory map inside the bean:

```java
@Bean
Consumer<OrderCreated> reserveInventory(InventoryService inventoryService) {
    return event -> inventoryService.reserve(event);
}
```

The service must control inventory updates in the data store—such as via conditional updates, appropriate locking, or optimistic locking. Moving logic into another service does not make it safe automatically; what matters is clearly defining state ownership and contention handling.

## 4. Do Not Use In-Memory Counters as Business State

A common example is counting processed messages:

```java
@Bean
Consumer<OrderCreated> unsafeCounter() {
    AtomicInteger count = new AtomicInteger();

    return event -> {
        int current = count.incrementAndGet();
        System.out.println("Processed orders: " + current);
    };
}
```

`AtomicInteger` makes increments atomic within a single process, but it does not solve the following problems:

- When the application restarts, the value resets to zero.
- Multiple instances have separate counters and no consistent global total.
- Retries or message redeliveries increment the counter again.
- The value is not tied to a business transaction and cannot serve as proof of processing.

If used solely for local diagnostics, use a proper metrics system and accept the scope of a local metric. If business statistics are required, record them using durable storage with identifiers, deduplication, and explicit aggregation policies. Never treat a counter variable in a bean as an authoritative data source.

## 5. Updating Durable State Safely

Many business workflows must remember the outcome of previous messages. For example, upon receiving `OrderCreated`, an inventory service must deduct or reserve stock. Inventory state must survive restarts and update accurately when two orders request the same product concurrently.

One approach is to place the operation in a transactional service and record the processed `eventId` within the same transaction boundary:

```java
@Service
public class InventoryService {
    private final ProcessedEventRepository processedEvents;
    private final InventoryRepository inventory;

    public InventoryService(
            ProcessedEventRepository processedEvents,
            InventoryRepository inventory) {
        this.processedEvents = processedEvents;
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(OrderCreated event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        for (OrderItem item : event.items()) {
            int updated = inventory.reserveIfAvailable(
                    item.productId(), item.quantity());
            if (updated != 1) {
                throw new InsufficientInventoryException(item.productId());
            }
        }

        processedEvents.save(new ProcessedEvent(event.eventId()));
    }
}
```

In this example, `reserveIfAvailable` should perform a conditional database update—for instance, decrementing stock only when `available_quantity >= requested_quantity`—and return the number of updated rows. The `ProcessedEvent` table needs a unique constraint on `eventId`. Both the check and marker write must be protected within the same transaction; calling `existsById` first and saving later without a unique constraint can still suffer a race condition when two consumers process the same event simultaneously.

When two distinct messages update the same product concurrently, the database must resolve contention using locks, atomic updates, optimistic locking, or another mechanism suited to the data model. If the transaction fails, inventory changes and the processed marker must roll back together so the message can be retried safely.

Business-level idempotency is especially important because message brokers can redeliver messages after timeouts, restarts, or acknowledgment failures. Keeping state in a database does not automatically guarantee exactly-once processing; the application still needs event identifiers, data constraints, and an appropriate retry policy.

## 6. When Stream State Is Needed, Use a Stateful Tool

Not every computation can be handled independently per message. For example, a system may need to count orders per customer, sum revenue over time windows, or maintain running balances by key. If state is stored in a `HashMap` field on a function bean, that state exists only in one instance and is lost when the process stops.

For Kafka streams requiring keyed state, Kafka Streams provides stateful transformations with state stores and state recovery mechanisms. Spring Cloud Stream's Kafka Streams binder allows declaring functions using `KStream` or `KTable` types, distinct from pure per-message functions:

```java
@Bean
Function<KStream<String, OrderEvent>, KStream<String, Long>> orderCountByCustomer() {
    return events -> events
            .groupByKey()
            .count(Materialized.as("orders-count-by-customer"))
            .toStream();
}
```

In this example, the record key must be the customer ID to count per customer. `count` maintains results in a state store named `orders-count-by-customer`; Kafka Streams manages a changelog topic to restore state when a task restarts or migrates to another instance. Keys, partitions, serdes, and topology must be configured properly. If the key is wrong or records for the same customer land in different partitions, aggregated results may not reflect the intended scope.

A state store is not a global Java map. It belongs to a topology/task, is bound to partitions, and has a recovery lifecycle. Teams must monitor storage usage, changelogs, recovery times, and topology changes during deployment. With RabbitMQ or Pulsar, choose a stateful processing model appropriate for that platform; Kafka Streams state store mechanics cannot be ported directly to another binder.

## 7. "Thread-Safe Fixes" That Do Not Solve the Real Problem

Certain fixes eliminate a concurrency exception yet still fail to solve state ownership:

| Approach | Remaining Limitation |
|---|---|
| Replacing `HashMap` with `ConcurrentHashMap` | Safer for map operations within one JVM, but data is neither durable nor synchronized across multiple instances |
| Wrapping collections with `synchronized` | May reduce race conditions in one process but creates contention bottlenecks and does not protect database/broker transactions |
| Using `AtomicInteger` for stock counts | Atomic only in one process's memory; does not guarantee concurrent updates across instances or restarts |
| Using `ThreadLocal` | Ties data to a thread while threads are pooled and reused; unsuitable for business state or async context propagation |
| Using `static` fields | Shared within the current classloader, unsafe across multiple processes, and hard to test in isolation |
| Reducing concurrency to one | May mask symptoms in small environments, lowers throughput, and offers no protection across multiple instances |

Synchronized structures and thread-safe caches remain useful for well-scoped auxiliary data, such as caches of immutable configuration. However, if data carries business meaning, must survive restarts, or can be updated by multiple instances, move it to an appropriate persistent store.

## 8. Testing Independence and Concurrency Safety

Unit tests for each function should verify that the same input always yields the expected output and does not depend on prior invocation order. A simple check is calling the function repeatedly with different inputs and then calling it again with the first input to detect retained stale data:

```java
@Test
void validationDoesNotLeakDataBetweenInvocations() {
    Function<OrderCreated, OrderValidated> function =
            validateOrder(new DefaultOrderPolicy());

    OrderValidated first = function.apply(order("evt-1", "ord-1"));
    OrderValidated second = function.apply(order("evt-2", "ord-2"));
    OrderValidated firstAgain = function.apply(order("evt-1", "ord-1"));

    assertThat(first.orderId()).isEqualTo("ord-1");
    assertThat(second.orderId()).isEqualTo("ord-2");
    assertThat(firstAgain).isEqualTo(first);
}
```

For services updating a database, integration tests should cover two concurrent consumers handling orders competing for the same inventory, redelivery of the same `eventId`, transaction rollbacks, and application restarts. Outcomes must guarantee no negative inventory, no duplicate recording of the same event, and no lost processing markers when transactions fail.

For Kafka Streams, also test state store restoration, partition reassignments, late-arriving data, and partition count changes. For standard binders, test at the concurrency level actually used in production; single-threaded tests are insufficient to expose all race conditions.

## 9. Pre-Deployment Design Checklist

- [ ] `Supplier`, `Function`, and `Consumer` beans do not hold per-message payloads or business data in mutable fields.
- [ ] Singleton dependencies are reviewed for safety under concurrent multi-threaded invocation.
- [ ] Payloads favor immutable types; nested collections and objects are not shared for mutation.
- [ ] Temporary variables for a single invocation stay within call scope and do not escape into uncontrolled async tasks.
- [ ] Business state is stored in a database or service with an explicit concurrent update contract.
- [ ] Consumers implement idempotency via `eventId` and a unique constraint on the processed-event store.
- [ ] Stream-aggregated state uses a state store or platform with proper recovery guarantees.
- [ ] `static` fields, `ThreadLocal`, in-memory counters, or in-memory collections are not used as durable business state sources.
- [ ] Tests cover duplicate delivery, concurrency, rollbacks, and restarts according to stream requirements.

Stateless functions are the right default for most event transformation and routing steps in Spring Cloud Stream because each message can be processed independently and scaled with consumer capacity. When business logic must remember data, place state in components responsible for storage, synchronization, and recovery. This separation prevents bugs caused by singleton beans being mutated across threads while clarifying consistency and recovery semantics for the entire event flow.

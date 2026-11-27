# Stateful Handlers and Thread Safety in Spring Integration

## Learning Objectives

When building a **Spring Integration Runtime**, messages pass through channels, endpoints, consumers, pollers, and executors before reaching a handler. A handler that works for individual messages sequentially is not necessarily correct when multiple messages arrive concurrently. This lesson helps you:

- Distinguish **per-invocation state**, **handler-bean state**, **correlation-keyed state**, and **external durable state**.
- Identify where a handler can be invoked concurrently, even when using `DirectChannel`.
- Recognize lost updates, cross-message data leakage, out-of-order execution, duplicates, and races between retries and side effects.
- Choose the right protection mechanism: immutable data, local variables, atomic operations, synchronization, message group stores, or database transactions.
- Observe and test thread safety at runtime rather than inferring it from channel names.

> **Key idea:** Thread safety is a property of *how a handler accesses shared state*, not an automatic guarantee from annotations, singleton beans, or synchronous flow execution.

## 1. Where Does Handler State Live?

In Spring Integration, a **`MessageHandler`** receives a message and processes it; a service activator usually delegates processing to a POJO method. A shared handler or service bean typically outlives any individual message by a huge margin.

| State Scope | Examples | Concerns to Control |
| --- | --- | --- |
| **Per-invocation** | Local variable computing a total, immutable DTO per message | Safer when each invocation keeps its own data; still watch out for shared input objects |
| **Inside the handler instance** | Counters, caches, `Map` holding in-flight orders | Concurrent reads/writes across threads; lost on restart if held only in RAM |
| **By correlation key** | Group of messages for an order waiting for all parts | Multiple messages with the same key can arrive concurrently or out of order |
| **Out-of-process** | Balances in DB, Redis, JDBC `MessageStore` | Multiple instances, restarts, transactions, duplicates, and distributed locking |

Distinguish **intentional state** from **accidentally leaked state**. For example, a `lastCustomerId` field on a singleton meant to "remember the most recent customer" can cause two messages to overwrite each other's data. A local `customerId` variable extracted directly from the message has no such issue.

**`MessageHeaders`** is designed as a header collection that cannot be mutated directly after creation; however, this **does not make the payload immutable**. If the payload is an `ArrayList`, `Map`, or entity with setters, two handlers/threads holding references to it can still mutate it. Prefer passing immutable DTOs or creating copies when transferring data ownership.

## 2. Channels Determine Where Code Executes, Not State Protection

The diagram below illustrates a frequently misunderstood scenario:

~~~mermaid
flowchart LR
    P1["Producer A · thread A"] --> DC["DirectChannel"]
    P2["Producer B · thread B"] --> DC
    DC --> H["Single singleton handler"]
    H --> S[("Shared state")]
~~~

`DirectChannel` invokes the handler on **the thread of the `send` call itself**. If two producers call `send` concurrently, two invocations into the same handler can still overlap. "One thread per send" does not mean "only one thread for the entire handler."

| Runtime Component | Typical Execution Behavior | Impact on Stateful Handlers |
| --- | --- | --- |
| **`DirectChannel`** | Handler runs synchronously on the sender's thread; sender waits for completion | Different senders can still invoke the same handler concurrently |
| **`ExecutorChannel`** | Hands off dispatch to a `TaskExecutor`, usually running on another thread | Can run in parallel, does not preserve order by default; sender's thread-bound transaction does not cross the channel |
| **`QueueChannel` + polling consumer** | Messages sit in a queue; poller fetches and invokes the handler | A single sequential consumer can reduce contention, but multiple pollers/tasks/executors increase parallelism |
| **`PublishSubscribeChannel`** | Sends messages to subscribers; typically synchronous by default, executor configurable | Subscribers may observe the same referenced payload; concurrent sends or an executor introduce contention |
| **Aggregator/correlating endpoint** | Groups messages by correlation key via `MessageGroupStore` | Needs per-group synchronization and management of group lifecycle, timeouts, and late arrivals |

A helpful way to read a flow is to trace the **thread path** from producer through each channel, gateway, poller, executor, and endpoint before reaching the handler. Thread handoff points are also usually where transaction boundaries, `ThreadLocal`/MDC context, and error propagation back to the caller change.

**Do not assume "messages arrive in exact order."** In concurrent systems, messages sharing a key can finish out of order, retries can replay older operations, and broker messages can be redelivered. If ordering matters to business correctness, explicitly define per-key ordering, serialization, or version checks in the datastore.

## 3. Race Conditions: Code That Passes for One Message but Fails Under Concurrency

Example of a handler receiving inventory reservation requests:

~~~java
import java.util.HashMap;
import java.util.Map;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

record ReserveCommand(String sku, String requestId) {}
record ReserveResult(String requestId, boolean accepted) {}

@Component
class UnsafeReservationHandler {
    private final Map<String, Integer> remaining = new HashMap<>();

    @ServiceActivator(inputChannel = "reservationRequests")
    public ReserveResult reserve(ReserveCommand command) {
        int before = remaining.getOrDefault(command.sku(), 0);
        if (before <= 0) {
            return new ReserveResult(command.requestId(), false);
        }

        remaining.put(command.sku(), before - 1);
        return new ReserveResult(command.requestId(), true);
    }
}
~~~

Suppose stock for SKU A is 1 and two threads process concurrently:

1. Thread T1 reads `before = 1`.
2. Thread T2 also reads `before = 1`.
3. T1 writes `0` and returns `accepted = true`.
4. T2 also writes `0` and returns `accepted = true`.

The system confirmed **two** requests when only **one** item existed. This is a *check-then-act* and *lost update* bug. `HashMap` is also unsafe under concurrent writes; replacing it with `ConcurrentHashMap` **still does not** fix the multi-step read → check → write sequence.

Common variants:

- A `currentOrder` or `currentUser` field overwritten by another message before the handler builds its response.
- A counter using `count++` losing updates.
- A shared `ArrayList` modified while another thread is iterating over it.
- A handler calling an external service inside a `synchronized` block, extending lock hold time and bottlenecking throughput.
- Two application replicas both "locked" with `synchronized`, yet each replica only locks within **its own JVM**.

## 4. Making Single-JVM State Safe with Atomic Operations

If state is only for demonstration or single-process counting, you can use **`ConcurrentHashMap`** combined with **`AtomicInteger`**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class LocalReservationHandler {
    private final ConcurrentMap<String, AtomicInteger> remaining =
            new ConcurrentHashMap<>();

    // Initialize each SKU during bootstrap; do not call again to reset during processing.
    public void registerSku(String sku, int initialQuantity) {
        if (initialQuantity < 0) {
            throw new IllegalArgumentException("Quantity must be non-negative");
        }
        if (remaining.putIfAbsent(sku, new AtomicInteger(initialQuantity)) != null) {
            throw new IllegalStateException("SKU already registered: " + sku);
        }
    }

    @ServiceActivator(inputChannel = "reservationRequests")
    public ReserveResult reserve(ReserveCommand command) {
        AtomicInteger stock = remaining.get(command.sku());
        if (stock == null) {
            throw new IllegalArgumentException("Unknown SKU: " + command.sku());
        }

        int before = stock.getAndUpdate(qty -> qty > 0 ? qty - 1 : 0);
        return new ReserveResult(command.requestId(), before > 0);
    }
}
~~~

`getAndUpdate` performs an atomic update on **a single value** and returns the pre-update value. Two threads both seeing quantity 1 cannot both succeed in decrementing it. The transformation function should be short, pure, and side-effect-free because it may be re-evaluated under contention.

**Limitations:** The example above holds state solely in one JVM's RAM. It stores no `requestId` history, cannot block duplicate deliveries of the same request, does not support multiple replicas sharing inventory, loses data on restart, and guarantees no synchronization with database transactions. Do not use this pattern as the source of truth for inventory or money.

### When One Key Holds Multiple Fields

For small, immutable per-key state, you can update multiple fields together using `compute`:

~~~java
record BatchProgress(int received, int failed) {}

private final ConcurrentMap<String, BatchProgress> progress =
        new ConcurrentHashMap<>();

void recordResult(String batchId, boolean successful) {
    progress.compute(batchId, (key, old) -> {
        BatchProgress current =
                old == null ? new BatchProgress(0, 0) : old;
        return new BatchProgress(
                current.received() + 1,
                current.failed() + (successful ? 0 : 1));
    });
}
~~~

For a single key, `compute` prevents fragmented updates to `received` and `failed`. However, it **does not** make operations across multiple keys or against a DB transactional. Avoid HTTP calls, sending messages, DB writes, or long waits inside `compute`; if the callback is retried, side effects could even be duplicated.

If a handler enforces invariants spanning multiple dependent entities (such as transferring money between two accounts), keep the entire invariant inside a datastore transaction with proper concurrency control rather than combining multiple `AtomicInteger`s.

## 5. When State Belongs to a Group of Messages: Use Correlation

A workflow might receive multiple parts of one order: payment, shipment, and inventory check. They may arrive at different times. Using mutable fields on a handler to "hold messages until complete" easily mixes up orders.

Spring Integration provides an **aggregator**, which is a **stateful message handler**. It:

1. Determines a **correlation key** for grouping (by default typically taken from the `correlationId` header).
2. Stores messages belonging to the group via a **`MessageGroupStore`**.
3. Uses a **`ReleaseStrategy`** to decide when the group is ready to emit a result.
4. Applies a per-group lock when operating on a group; by default, an in-process lock is used.

~~~mermaid
flowchart TD
    M1["Message: order-42 / payment"] --> C["Correlation key = order-42"]
    M2["Message: order-42 / shipment"] --> C
    M3["Message: order-42 / inventory"] --> C
    C --> G[("MessageGroupStore")]
    G --> R{"ReleaseStrategy: ready?"}
    R -- "Not yet" --> G
    R -- "Yes" --> O["Aggregated result"]
~~~

**What must not be inferred:** An aggregator protects group updates managed by its endpoint; it does not automatically protect arbitrary mutable fields on POJOs or side effects invoked from `ReleaseStrategy`/processors. Business callbacks should still minimize shared state and avoid non-idempotent side effects.

When **multiple instances** share a `MessageGroupStore`, consider a **shared `LockRegistry` across instances**. `DefaultLockRegistry` is only effective within a single process. Distinguish:

- **`MessageGroupStore`** persists messages and group metadata; choosing in-memory vs. persistent determines survival across restarts.
- **`LockRegistry`** coordinates concurrent workers operating on a group; a shared store does not automatically turn an in-JVM lock into a distributed lock.
- **Idempotency/deduplication** prevents re-applying business side effects; group locks do not replace unique constraints, idempotent receivers, or processed-request tracking.

You also need to decide on **group timeouts**, late-arriving messages, expiring/discarding groups or emitting partial results, and cleanup policies for stale groups. Keeping groups indefinitely in RAM can cause unbounded memory growth. Never share one `MessageGroupStore` across multiple aggregators with independent expiry policies without proper partitioning and callbacks.

## 6. Transactions, Retries, and Thread Boundaries

Suppose a handler must deduct inventory in the DB, log processing history, and emit a confirmation message. Under concurrency, **thread-safe in RAM** and **transaction-safe in the datastore** are two distinct requirements.

### Same-Thread Transaction Case

With `DirectChannel`, synchronous sending and processing can participate in the transaction currently bound to the thread, **if** the transaction manager and involved resources support it. When the handler throws an error, the sender typically sees the error in the synchronous `send` call. However, a DB rollback **does not automatically roll back** an `AtomicInteger` or Java field value.

### Crossing to an Executor

With `ExecutorChannel`, processing typically happens on another thread. The sender's transaction/`ThreadLocal` does not carry over to the handler's thread by default, and `send` can complete before the handler throws an error. Design transactions **on the consumer/handler side** and route errors for the asynchronous step. Do not rely on `CallerRunsPolicy` or accidental thread reuse to guarantee transaction boundaries.

### A Safer Pattern for Business State

For inventory in a DB, you can use a conditional update inside a transaction:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = :sku AND available > 0;
~~~

Only confirm the reservation if the updated row count is 1. If messages can be redelivered, `requestId` must be recorded **idempotently** via a unique constraint or a processing record in the same transaction; the check-and-record order must withstand two concurrent consumers. Across multiple distributed resources, consider transactional outbox/inbox or compensating workflows rather than assuming a single transaction spans broker, DB, and HTTP.

Principles for retries:

- Retries **re-execute** a segment of processing; retrying does not mean the message is new or prior side effects were undone.
- If a handler successfully called a payment API and then timed out reading the response, a retry can invoke payment again. Use an idempotency key on the target system or design reconciliation.
- If messages can arrive as duplicates, **counting `handleMessage` invocations** is not the same as **counting unique business operations**.
- Asynchronous errors must be observed on an appropriate error flow/`errorChannel`; do not merely catch exceptions around the producer's `send` call and assume all downstream errors are covered.

## 7. Choosing State Protection by Scope

| Requirement | Appropriate Approach | Key Limitations |
| --- | --- | --- |
| Independent per-message processing | Stateless handler, local variables, immutable DTOs | Payloads or injected services could still share state |
| Single-instance metrics/counters | `AtomicLong`, `LongAdder`, or concurrent structures | Not cluster-wide accurate; resets on restart |
| Short-lived per-key cache | `ConcurrentMap` or cache with TTL/size bounds | Needs eviction, invalidation, and memory policies |
| Multi-field updates for one key in RAM | `compute` with immutable objects, per-key locking when appropriate | Does not span multiple keys, DBs, or remote calls |
| Correlated message aggregation | Aggregator + `MessageGroupStore` + release/expiry | Needs group design, deduplication, persistent store, and distributed locks |
| Inventory, quotas, money, multi-replica dedup | DB transactions, unique constraints, conditional updates, optimistic locking | Must handle conflicts/retries and external side effects |
| Per-entity/key ordering required | Per-key consumer/partitioning, version-checked updates, or intentional serialization | Global ordering usually hurts throughput; scale-out requires consistent partitioning |

**Locking the whole handler** with `synchronized` can serialize certain operations inside one JVM, yet forces unrelated keys to wait on each other; it does not solve multi-instance concurrency and easily bottlenecks if locks are held across I/O. When per-key state is required, prefer per-key protection or push invariants down into the datastore.

## 8. Practice: Reading a Running Flow

Consider a model (conceptual diagram, not a complete configuration):

~~~text
HTTP/gateway
  └─ DirectChannel
       └─ transformer (stateless)
            └─ ExecutorChannel (thread pool 8)
                 └─ @ServiceActivator reservationHandler
                      ├─ DB update
                      └─ outbound event
~~~

Answer step by step:

1. **Where does concurrency originate?** Multiple HTTP requests can arrive simultaneously; the executor allows up to multiple tasks running concurrently; differing subscriber, poller, and replica counts can increase actual concurrency.
2. **Where does state actually live?** Fields on `reservationHandler`, shared caches/DAOs, DB, mutable payloads, and external systems.
3. **Is per-key ordering required?** Two requests for the same SKU or `orderId` can arrive out of order; use version/condition checks if order determines the outcome.
4. **Where do transactions start?** Do not assume the HTTP thread's transaction continues past `ExecutorChannel`.
5. **On error or retry, what can re-run?** Distinguish messages taken from a queue, committed SQL, external APIs already called, and emitted events.
6. **When stopping/restarting `IntegrationFlow`, does state survive?** State in handler fields and in-memory stores depends on bean/process lifecycle; persistent state depends on store configuration. Stopping an endpoint does not automatically clear all business state.

### Verifying with Concurrent Tests

Create test data for 1 SKU with inventory 50, dispatch 200 concurrent reserve commands with **200 distinct `requestId`s**, wait for all to complete, then verify:

- Assuming each command is dispatched **once**, accepted count must be exactly 50, rejected count exactly 150, and remaining stock 0.
- Repeat the test across multiple threads and runs; if a broker/retry is involved, measure message count and unique `requestId` count separately.
- Send **the same `requestId`** twice to verify whether idempotency logic actually works.
- If running multiple application instances, test against a shared DB or store; single-JVM tests do not prove correctness when scaling out.
- Inject simulated failures between the DB write and event emission to test duplicates, rollbacks, timeouts, and recovery mechanisms.

### What to Observe in Production Diagnostics

In logs/traces, include `messageId`, `correlationId`, business keys (`orderId`/SKU), endpoint, thread name, and attempt or `requestId`. Avoid logging sensitive data unnecessarily. Track active thread counts, executor queues, rejected tasks, poller delays, queue backlogs, stuck/timed-out groups, retry rates, duplicates, and lock hold times. Symptoms like throughput dropping as pool size grows, accepted requests exceeding limits, or groups waiting forever usually indicate issues with state synchronization, business invariants, or correlation.

## 9. Checklist Before Deploying a Stateful Handler

- **Ownership:** Which state lives per message, per bean, per key, per JVM, or per cluster?
- **Concurrency:** What can invoke the handler concurrently? Are there thread boundaries, multiple pollers, multiple endpoints referencing the same bean, or multiple replicas?
- **Atomicity:** Does the "read → check → write" operation execute within a single atomic operation/transaction?
- **Immutability:** Do payloads/callbacks mutate objects shared with other handlers?
- **Ordering:** Is strict per-key ordering required? If so, what enforces it?
- **Duplication:** Under retries/redeliveries, could an already-processed `requestId` be re-applied?
- **Persistence:** How do restarts, redeploys, flow stop/start, and group expiration affect state?
- **Error path:** Where do exceptions thrown past `ExecutorChannel` go; is there sufficient observability and recovery?
- **Operations:** Are there memory limits, TTLs, backpressure, timeouts, lock monitoring, and concurrency tests?

## Conclusion

The safest handler is usually one that **holds no business state in mutable fields**: each invocation works on its own message and delegates consistency to an appropriate datastore or message group mechanism. When holding state is unavoidable, identify its sharing scope first, protect the exact invariants, and test under real concurrency. Channels and executors determine *the execution path*; message stores, locks, and transactions determine *how state stays consistent*.

## References

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Framework Overview](https://docs.spring.io/spring-integration/reference/overview.html)

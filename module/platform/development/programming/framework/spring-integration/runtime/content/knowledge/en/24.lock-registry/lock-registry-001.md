# LockRegistry and Keyed Locking

When a Spring Integration system processes multiple messages concurrently, two messages may modify the state of **the same business entity** at the same time. For example, an order receives two updates almost simultaneously: the first message confirms payment, and the second requests a refund. If both handlers read the old state and then write their results, the update order can become incorrect even though each handler works properly on its own.

**Keyed locking** lets you serialize the processing region for messages **sharing the same key**, while still allowing different keys to be processed in parallel. Spring Integration provides the **<code>LockRegistry</code>** interface to obtain a <code>java.util.concurrent.locks.Lock</code> by key. There are single-JVM implementations as well as distributed implementations backed by shared resources.

This lesson belongs to the **Lock registry** chapter of the **SPRING_INTEGRATION_RUNTIME** module. We will practice keyed locking as messages flow through channels, endpoints, consumers, pollers, and executors; and analyze how locks interact with transactions, retries, message stores, correlation, error flows, and runtime metrics.

> **Important limitation:** A lock controls access to a critical section. A lock **does not by itself guarantee** transaction commits, exactly-once message delivery, or that side effects happen only once. To handle retries and redeliveries safely, you still need appropriate transactions, idempotency, and storage contracts.

## 1. The problem: multiple messages, same business key

A typical example:

~~~text
Message 1: tenant=T1, order=O42, action=PAY
Message 2: tenant=T1, order=O42, action=REFUND
Message 3: tenant=T1, order=O93, action=PAY
~~~

With an <code>ExecutorChannel</code> or a consumer invoked from multiple threads, messages 1 and 2 can enter the same handler concurrently. We want messages 1 and 2 **not to overlap** when updating O42, while message 3 can still be processed in parallel.

~~~mermaid
flowchart LR
    C["ExecutorChannel"] --> M1["PAY O42"]
    C --> M2["REFUND O42"]
    C --> M3["PAY O93"]
    M1 --> K1["Lock key: T1:O42"]
    M2 --> K1
    M3 --> K2["Lock key: T1:O93"]
    K1 --> S1["O42 processing region<br/>one message at a time"]
    K2 --> S2["O93 processing region<br/>can run in parallel"]
~~~

Without a lock boundary, the **read → check → write** pattern is prone to race conditions:

~~~text
Thread A: reads O42 = NEW
Thread B: reads O42 = NEW
Thread A: writes O42 = PAID
Thread B: writes O42 = REFUNDED (without checking PAID state)
~~~

Locking on the same key prevents two threads from entering the mutually exclusive processing section within the **registry scope**. However, if another node uses a separate registry, or a service updates the database without following the same rule, a local lock is not enough to protect the entire system.

## 2. What LockRegistry is and its core API

The <code>org.springframework.integration.support.locks.LockRegistry</code> interface declares:

~~~java
Lock obtain(Object lockKey);
~~~

<code>obtain(...)</code> **retrieves the lock object associated with the key**; it does not mean you have acquired execution rights yet. You must call one of the <code>Lock</code> operations:

| <code>Lock</code> API | Meaning | Notes |
|---|---|---|
| <code>lock()</code> | Waits until the lock is acquired | Can wait indefinitely; does not respond to interrupts while waiting per the <code>Lock</code> contract |
| <code>lockInterruptibly()</code> | Waits for the lock while allowing interruption | Throws <code>InterruptedException</code>; restore the interrupt flag if converting to an unchecked exception at the application layer |
| <code>tryLock()</code> | Attempts immediate acquisition | Returns <code>false</code> if currently held |
| <code>tryLock(timeout, unit)</code> | Waits up to a specified duration | Returns <code>false</code> on expiration; may throw <code>InterruptedException</code> |
| <code>unlock()</code> | Releases the lock after the critical section | Only call after successful acquisition, typically inside <code>finally</code> |

Minimal example:

~~~java
LockRegistry registry = new DefaultLockRegistry();
Lock lock = registry.obtain("tenant:T1:order:O42");

lock.lock();
try {
    // Read state, validate, and update O42.
} finally {
    lock.unlock();
}
~~~

**Always release the lock in <code>finally</code>** if it was successfully acquired, even when business code throws an exception. When using <code>tryLock</code>, check the <code>acquired</code> flag before calling <code>unlock()</code>; calling <code>unlock()</code> without owning the lock can throw an error and mask the original exception.

### executeLocked() since Spring Integration 6.2

Starting in version 6.2, <code>LockRegistry</code> provides default <code>executeLocked(...)</code> methods to wrap a critical section:

~~~java
public void applyWithLock(
        LockRegistry registry,
        String businessKey,
        Runnable action) throws InterruptedException {

    registry.executeLocked(businessKey, () -> action.run());
}
~~~

An overload accepting a <code>Duration</code> limits the wait time:

~~~java
public void applyWithTimeout(
        LockRegistry registry,
        String businessKey,
        Runnable action) throws InterruptedException, TimeoutException {

    registry.executeLocked(
        businessKey,
        Duration.ofSeconds(2),
        () -> action.run()
    );
}
~~~

<code>executeLocked</code> handles acquiring and releasing the lock and propagates exceptions from the inner action to the caller; the <code>Duration</code> overload throws <code>TimeoutException</code> if the lock cannot be acquired before the deadline. <code>InterruptedException</code> still must be handled by the caller; the snippets assume <code>java.time.Duration</code> and <code>java.util.concurrent.TimeoutException</code> are imported.

<code>executeLocked</code> reduces the risk of forgetting <code>unlock</code>, but it does not eliminate the need to design the **right key** and the **right critical section**.

## 3. Choosing the key: the most important decision

The key must represent **the exact resource that requires mutual exclusion**. For example, <code>orderId</code> is insufficient if different tenants can share the same ID.

| Key | Assessment |
|---|---|
| <code>orderId</code> | Can collide across tenants |
| <code>tenantId + ":" + orderId</code> | Better, but needs escaping rules if values contain <code>:</code> |
| <code>tenant:T1:order:O42</code> | Namespaced key by entity type |
| <code>message.getHeaders().getId()</code> | Usually unsuitable: each message has its own ID, so two messages for the same order will not share a lock |
| <code>correlationId</code> | Suitable when the correlation key actually represents the unit to lock; may not match the business key |
| <code>UUID.randomUUID()</code> | Wrong for shared locking: every call produces a new key |

You can design a uniform key builder function:

~~~java
public final class BusinessLockKeys {
    private BusinessLockKeys() {}

    public static String forOrder(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing tenantId/orderId");
        }

        // Length-prefix each component so delimiters are unambiguous.
        return "orders/" + tenantId.length() + ":" + tenantId
             + "/" + orderId.length() + ":" + orderId;
    }
}
~~~

Keys must be generated **consistently everywhere** the registry is used. When multiple deployments run simultaneously during a rolling deployment, changing key normalization can cause two versions to lock differently for the same order.

Practical rules:

1. Base the lock on the entity **that needs protection**, not on a single message delivery.
2. Namespace by business domain (<code>orders</code>, <code>accounts</code>) and tenant when needed.
3. Use immutable data; if using a custom key object, implement stable <code>equals()</code>/<code>hashCode()</code>. For distributed locks, normalized string keys are generally easier to keep consistent.
4. Do not include full payloads, sensitive information, or unbounded-size values in backend keys.
5. Use **the same key** across all code paths that can modify the same resource, including replay/retry flows.

**A lock key is different from an idempotency key.** Two messages with the same <code>orderId</code> can be two valid operations that must run sequentially; an idempotency key distinguishes a redelivery of a specific operation.

## 4. DefaultLockRegistry: single-JVM locking and striped locking

<code>DefaultLockRegistry</code> is an in-memory implementation backed by <code>ReentrantLock</code> instances. Upon initialization, it creates an array of locks; keys are mapped to array slots by masking <code>hashCode()</code>.

~~~java
LockRegistry registry = new DefaultLockRegistry();       // 256 stripes
LockRegistry wider = new DefaultLockRegistry(0x3ff);      // 1024 stripes
~~~

The <code>mask</code> parameter must have the form <code>2^n - 1</code>. <code>0xff</code> (255) gives 256 slots, and <code>0x3ff</code> (1023) gives 1024 slots.

~~~mermaid
flowchart TD
    K1["key: order:O42"] --> H1["hashCode & mask"]
    K2["key: order:O93"] --> H2["hashCode & mask"]
    K3["key: order:O12"] --> H3["hashCode & mask"]
    H1 --> L1["ReentrantLock stripe 17"]
    H2 --> L2["ReentrantLock stripe 83"]
    H3 -. "May collide" .-> L1
~~~

**Distinct keys do not always get distinct locks.** Two keys whose hashes land in the same stripe will wait on each other; this is *false contention*, not a data correctness bug. Increase the stripe count when there is evidence of collision causing bottlenecks, rather than maxing it out by default without considering resource trade-offs and load testing.

<code>DefaultLockRegistry</code> has these characteristics:

- Locking works across threads **using the same registry instance** within the same JVM.
- Local locks use <code>ReentrantLock</code> semantics, so the same thread can re-enter its held lock; it must call <code>unlock</code> the same number of times it locked.
- Different JVMs/pods have independent lock arrays. Two pods each creating <code>new DefaultLockRegistry()</code> **do not synchronize with each other**.
- The lock does not automatically protect a database transaction committing on another node.

If a system has only one JVM handling that resource and no external update paths, a local registry is usually a reasonable starting point.

## 5. Example: locking by order key in a Service Activator

Suppose an inbound adapter produces messages containing <code>OrderCommand</code> and sends them to <code>orders.input</code>. Multiple workers may invoke the handler concurrently.

**Step 1 — command and business service:**

~~~java
public record OrderCommand(String tenantId, String orderId, String operation) {}

@Service
public class OrderService {
    @Transactional
    public void apply(OrderCommand command) {
        // Read state, validate business rules, and write to the database.
        // Add corresponding DB constraints/idempotency in a real application.
    }
}
~~~

**Step 2 — lock in the runtime adapter before calling the service:**

~~~java
@Component
public class KeyedOrderHandler {
    private final LockRegistry registry;
    private final OrderService service;

    public KeyedOrderHandler(LockRegistry registry, OrderService service) {
        this.registry = registry;
        this.service = service;
    }

    @ServiceActivator(inputChannel = "orders.input")
    public void handle(OrderCommand command) {
        String key = BusinessLockKeys.forOrder(
            command.tenantId(), command.orderId());
        Lock lock = registry.obtain(key);
        boolean acquired = false;

        try {
            acquired = lock.tryLock(2, TimeUnit.SECONDS);
            if (!acquired) {
                throw new IllegalStateException("Timed out waiting for lock: " + key);
            }
            service.apply(command);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting for lock: " + key, ex);
        } finally {
            if (acquired) {
                lock.unlock();
            }
        }
    }
}
~~~

**Step 3 — Spring Integration wiring:**

~~~java
@Configuration
@EnableIntegration
public class OrderLockConfig {
    @Bean
    LockRegistry orderLockRegistry() {
        return new DefaultLockRegistry();
    }

    @Bean(name = "orders.input")
    MessageChannel ordersInput() {
        return new ExecutorChannel(orderExecutor());
    }

    @Bean
    TaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-");
        return executor;
    }
}
~~~

Key imports: <code>org.springframework.integration.support.locks.LockRegistry</code>/<code>DefaultLockRegistry</code>, <code>org.springframework.integration.annotation.ServiceActivator</code>, <code>org.springframework.integration.channel.ExecutorChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.messaging.MessageChannel</code>, <code>org.springframework.core.task.TaskExecutor</code>, <code>org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor</code>, and <code>java.util.concurrent.TimeUnit</code>.

The configuration snippet is an abbreviated example; Spring manages the initialization and destruction of the executor bean. In a real application, inject the lifecycle-managed executor bean into the channel configuration instead of calling the factory method directly. The endpoint is discovered when Spring Integration processes annotations in the application context; do not register an additional Java DSL endpoint pointing to the same method unless you intend to create a second consumer.

**Execution order:** A worker thread acquires the lock <code>tenant:T1:order:O42</code>; inside the locked section, it invokes the service through the Spring proxy; if <code>@Transactional</code> starts the transaction at the service level, the service's commit/rollback typically completes **before the method returns** and the handler releases the lock. If a transaction was started by **a caller outside the handler**, releasing the lock at the end of the handler may occur **before the outer commit**. In that case, you must adjust the lock placement or transaction boundary so no other worker reads uncommitted state.

## 6. Locking directly with LockRequestHandlerAdvice (Spring Integration 6.5+)

Since Spring Integration **6.5**, <code>LockRequestHandlerAdvice</code> supports keyed locking around a request handler invocation. The advice can compute the key from the message using a static value, a SpEL expression, or a callback; this is useful when you want service logic to remain unaware of the messaging runtime.

~~~java
@Configuration
public class OrderAdviceConfig {
    @Bean
    LockRegistry orderLocks() {
        return new DefaultLockRegistry();
    }

    @Bean
    LockRequestHandlerAdvice orderLockAdvice(LockRegistry orderLocks) {
        LockRequestHandlerAdvice advice = new LockRequestHandlerAdvice(
            orderLocks,
            message -> {
                OrderCommand cmd = (OrderCommand) message.getPayload();
                return BusinessLockKeys.forOrder(
                    cmd.tenantId(), cmd.orderId());
            }
        );
        advice.setWaitLockDurationExpressionString("'PT2S'");
        return advice;
    }
}

@Component
public class AdvisedOrderConsumer {
    private final OrderService service;

    public AdvisedOrderConsumer(OrderService service) {
        this.service = service;
    }

    @ServiceActivator(
        inputChannel = "orders.input",
        adviceChain = "orderLockAdvice"
    )
    public void apply(OrderCommand cmd) {
        service.apply(cmd);
    }
}
~~~

<code>LockRequestHandlerAdvice</code> belongs to <code>org.springframework.integration.handler.advice</code>. The snippet above is **an alternative** to <code>KeyedOrderHandler</code> in the previous section: register **only one** consumer on <code>orders.input</code> for this use case when applying the example, so the same command is not processed twice.

Notes about the advice:

- The advice applies at the configured handler; it does **not** automatically lock upstream transformers/adapters or the entire preceding flow.
- If the key-computation callback returns <code>null</code>, the advice by default **does not acquire a lock**; you can configure a <code>discardChannel</code> to route keyless messages according to policy.
- <code>waitLockDuration</code> sets the wait time to acquire the lock, not the TTL of a distributed lock and not a business completion deadline.
- Check your Spring Integration version: do not use <code>LockRequestHandlerAdvice</code> in applications running on 6.4 or earlier.

## 7. When do you need to switch to a distributed LockRegistry?

If Spring Boot instances A and B both process messages that can modify a shared resource, two local registries **cannot** exclude each other.

~~~mermaid
flowchart TD
    A["Pod A<br/>DefaultLockRegistry"] --> DB["Shared database"]
    B["Pod B<br/>DefaultLockRegistry"] --> DB
    C["No shared lock<br/>overwrites can still occur"] -.-> DB
~~~

Spring Integration supports several distributed lock backends, such as <code>JdbcLockRegistry</code>, <code>RedisLockRegistry</code>, <code>HazelcastLockRegistry</code>, and <code>ZookeeperLockRegistry</code>. With a distributed backend, all nodes must share the same **registry namespace and key** representing the same resource.

| Implementation | Synchronization scope | Key considerations |
|---|---|---|
| <code>DefaultLockRegistry</code> | Threads in the same JVM, same instance | Striped collisions; do not use as a cluster lock |
| <code>JdbcLockRegistry</code> | Nodes sharing a JDBC lock repository | Lock table, transactions, DB latency, lease and renewal |
| <code>RedisLockRegistry</code> | Nodes sharing Redis/registry key | Lock expiration, network/Redis availability, cache/renewal |
| <code>HazelcastLockRegistry</code> | Configured Hazelcast cluster/backend | Cluster topology and semantics |
| <code>ZookeeperLockRegistry</code> | Nodes sharing ZooKeeper | Sessions and connection failures |

Example JDBC infrastructure on one node; other nodes must use the same database and region:

~~~java
@Configuration
public class DistributedLockConfig {
    @Bean
    DefaultLockRepository orderLockRepository(DataSource dataSource) {
        DefaultLockRepository repository =
            new DefaultLockRepository(dataSource);
        repository.setRegion("order-processing");
        return repository;
    }

    @Bean
    LockRegistry orderLockRegistry(DefaultLockRepository orderLockRepository) {
        return new JdbcLockRegistry(orderLockRepository);
    }
}
~~~

You need the corresponding JDBC lock tables from the Spring Integration schema script for your database and an appropriate transaction manager. <code>DefaultLockRepository</code>/<code>JdbcLockRegistry</code> belong to <code>org.springframework.integration.jdbc.lock</code>. This configuration is the core infrastructure; the channel/handler beans in earlier examples can use the injected <code>LockRegistry</code> without changing the business key.

**Do not treat a lease as an absolute guarantee.** A node can experience a long pause, lose connectivity, or hold a lock past its lease duration; another node can then acquire the same lock after expiry while the old node has not stopped processing. Depending on consistency requirements, combine locks with versioning/fencing or conditional updates in the database to prevent stale workers from writing. A lock does not replace update guards on the protected resource.

## 8. Lock wait timeout vs. lock TTL

Two concepts must be kept separate:

| Parameter | Controls | Example |
|---|---|---|
| <code>tryLock(2, SECONDS)</code> | Thread waits at most two seconds to acquire the lock | On expiration, reject/retry per policy |
| Distributed lock Lease/TTL | How long the backend retains ownership tracking | If a node dies, the key can expire so another node can take over |
| Aggregator <code>groupTimeout</code> | Deadline to evaluate/complete a group missing messages | Neither a lock wait nor a lock lease |
| Channel <code>sendTimeout</code> / <code>receiveTimeout</code> | Wait limit when sending/receiving messages | Does not lock business resources |
| Transaction timeout | Execution time limit for a transactional operation | Does not transfer an already acquired lock to another node |

Lock acquisition failures must be categorized clearly:

~~~text
Acquired → run use case → commit/rollback → unlock
Timed out → do not run use case → retriable/backoff error
Interrupted → do not run use case → preserve interrupt semantics
Lease lost → ownership state uncertain → alert/assess consistency
~~~

When catching <code>InterruptedException</code>, if the code converts it into an unchecked exception, call <code>Thread.currentThread().interrupt()</code> first. Never catch the error and proceed to run the business operation **without the lock**; doing so breaks the mutual exclusion contract.

With <code>RedisLockRegistry</code>, unlocking an expired lock can throw a serious exception because the protected resource may already have been accessed by another node. Automatic lease renewal on Redis was added in Spring Integration 6.4 via <code>setRenewalTaskScheduler()</code>; specific versions and renewal settings should be verified before use.

## 9. Locks, transactions, retries, and idempotency

A correct outcome depends on how boundaries are ordered:

~~~text
Message
  → lock by business key
     → service transaction begin
        → check state + write DB
     → commit/rollback
  → unlock
  → reply / publish event
~~~

This pattern ensures the service's database operations complete before the lock is released **provided** there is no pre-existing outer transaction. There are three important exceptions:

1. **Transaction wrapping the lock:** calling the handler from a facade that already opened a transaction; the handler releases the lock before the facade commits. Another worker can acquire the lock and access the DB while the previous transaction has not yet finished.
2. **Asynchronous downstream:** the handler may release the lock after sending to an <code>ExecutorChannel</code> or <code>QueueChannel</code> while the downstream consumer has not processed it yet. Protecting the entire chain requires redesigning the unit of work or inter-step coordination.
3. **Non-DB side effects:** HTTP calls, emails, or publishing messages to a broker are usually not automatically rolled back with a JDBC transaction. You need idempotency and potentially a transactional outbox.

### Retry under the lock or lock per retry attempt?

| Arrangement | Behavior | Consequence |
|---|---|---|
| Lock outside retry | One worker holds the lock across all attempts and backoff | Preserves exclusion but holds the lock longer, risking contention |
| Retry outside lock | Each attempt acquires and releases the lock | Allows other workers between attempts; must re-check state each time |
| Broker retry after redelivery | A message arrives again at a later time | A lock does not prevent duplicate side effects; requires a separate idempotency key |

Database deadlocks, lock acquisition timeouts, or transient backend disconnections can be retried within bounds; deterministic business errors such as <code>quantity &lt;= 0</code> are usually not worth retrying. When it is unclear whether a transaction committed, check idempotency before re-executing.

**Do not lock by message ID** if your goal is to serialize operations on the same entity: redelivery can produce a different message ID while the business key remains the same.

## 10. Does endpoint locking change threads and lifecycle?

Locks **do not create threads**, nor do they make a flow end-to-end synchronous:

| Topology | Where does the lock run? | Risk |
|---|---|---|
| <code>DirectChannel</code> → handler | Sender thread | Waiting on the lock prolongs <code>send()</code> or request–reply gateway calls |
| <code>ExecutorChannel</code> → handler | Worker thread after handoff | Many waiting workers can saturate the pool/queue |
| <code>QueueChannel</code> → poller → handler | Poller/scheduler thread | Lock wait stretches a poll cycle, reducing throughput |
| Two replicas on the same broker | Consumer threads on each replica | Distributed lock needed if the same resource can be processed across replicas |

When stopping an <code>IntegrationFlow</code> or endpoint, work that is running or waiting on a lock may not finish immediately. If the executor is shut down or interrupted, handlers must release locks properly; with distributed locks, lease expiration after a crash may introduce a wait window for other nodes.

Bound lock acquisition wait time according to the request/poller SLA. For messages that cannot be processed due to timeout, decide explicitly: retry/backoff, return an error to the caller, emit an <code>ErrorMessage</code> to the appropriate error flow, or route to a deferred queue. Setting a timeout without a failure path leads to lost messages or logs without recovery.

## 11. Performance: lock contention and hot keys

Keyed locking preserves concurrency across different resources, but it does not increase throughput for **a single** hot resource:

~~~text
100 messages with the same order=O42
  → one lock key
  → at most one thread in the critical section at a time

100 messages across 100 different orders
  → many lock keys
  → can process in parallel, depending on registry and stripe/worker count
~~~

With local striped locks, different keys can contend on the same stripe. With distributed locks, network latency, Redis/JDBC contention, and lease renewal overhead can exceed the business processing itself.

Metrics to observe:

- **Lock wait time:** time from starting to wait until acquired; inspect p50/p95/p99 by endpoint and key type.
- **Lock hold time:** duration the lock is held, especially when it includes database queries or external APIs.
- **Timeout/interrupt/lease lost count:** track failure reasons during lock acquisition and release.
- **Executor saturation and queue depth:** many workers waiting on locks can cause backlogs.
- **Throughput per business key:** detect when one key dominates traffic.
- **DB optimistic conflict / retry count:** evaluate whether additional version checks or idempotency are needed.

Do not attach raw keys containing sensitive data or extreme cardinality as labels on system metrics. You can use correlation IDs in controlled traces/logs and aggregate metrics by endpoint, operation type, or normalized tenant.

## 12. Diagnosing stuck messages or duplicate processing

| Symptom | Causes to check | Evidence |
|---|---|---|
| Two messages for the same order still run concurrently | Different keys, different registry instances, or two pods using local locks | Logs of normalized keys, node ID, registry type |
| Messages wait too long | Hot key, holding lock across slow HTTP, DB locks, or executor congestion | Lock wait/hold metrics, thread dumps, DB/Redis metrics |
| <code>tryLock</code> always times out | Lock held too long, lease not expired, or contention | Owner, timestamp, TTL, retry policy |
| After restart, another node still cannot process | Distributed lease still active | TTL/renewal, backend state, connection logs |
| <code>unlock</code> throws an exception | Releasing lock by wrong owner, not acquired, or lease expired | Stack trace and ownership logs |
| Lock is right but DB still has duplicate records | Redelivery after unlock, another code path, missing transaction/idempotency | Unique constraints, business event ID, retry logs |
| Adding threads does not increase throughput | One hot key, striped collisions, or slow lock backend | Key distribution, active thread pool, p95 lock wait |
| Error channel receives no errors | Errors swallowed or synchronous processing throws back to sender | Thread boundary, handler advice, and exception path |

When diagnosing, trace a request using its correlation ID and **masked business lock key**. Confirm every "lock acquired" log has a matching "lock released" or explicit failure exit; never simply increase timeouts before finding which code is holding the lock.

## 13. Testing keyed mutual exclusion

Tests must prove two different things: **the same key cannot execute concurrently**, and **different keys can execute concurrently**. A sequential unit test calling a handler twice does not prove locking behavior.

Example direct test using a local registry, JUnit 5, and an executor:

~~~java
@Test
void sameKeyNeverEntersCriticalSectionConcurrently() throws Exception {
    LockRegistry registry = new DefaultLockRegistry();
    ExecutorService workers = Executors.newFixedThreadPool(8);
    CountDownLatch start = new CountDownLatch(1);
    AtomicInteger inside = new AtomicInteger();
    AtomicInteger peak = new AtomicInteger();
    List<Future<?>> tasks = new ArrayList<>();

    try {
        for (int i = 0; i < 20; i++) {
            tasks.add(workers.submit(() -> {
                start.await();
                Lock lock = registry.obtain("tenant:T1:order:O42");
                lock.lock();
                try {
                    int active = inside.incrementAndGet();
                    peak.accumulateAndGet(active, Math::max);
                    try {
                        Thread.sleep(5);
                    } finally {
                        inside.decrementAndGet();
                    }
                } finally {
                    lock.unlock();
                }
                return null;
            }));
        }

        start.countDown();
        for (Future<?> task : tasks) {
            task.get(10, TimeUnit.SECONDS);
        }
        assertEquals(1, peak.get());
    } finally {
        workers.shutdownNow();
    }
}
~~~

Types used: <code>Lock</code>, <code>ExecutorService</code>, <code>Executors</code>, <code>CountDownLatch</code>, <code>AtomicInteger</code>, <code>Future</code>, <code>ArrayList</code>, <code>List</code>, and <code>TimeUnit</code>. This test proves mutual exclusion for the same key within **one JVM**. To prove different keys are not blocked, write a test using two keys verified to map to different stripes and synchronize their entry into the critical section.

For a cluster, you need **at least two processes/application contexts**, sharing the same real backend and registry namespace; measure whether two nodes ever process the same key concurrently. Include test cases for crashes, TTL expiration, renewal, restarts, retries, and a concurrent request arriving right before or during database commit.

### Scenarios to include in integration test suites

| Test case | Expected result |
|---|---|
| 20 messages for the same order on one instance | At most one handler holds the same lock at a time |
| Multiple keys and multiple threads | Appropriate concurrency across keys with no state mixing |
| One thread holds lock past timeout | Waiting threads receive timeout; service is not executed |
| Worker interrupted while waiting | Exits cleanly without losing interrupt semantics |
| Service throws an exception | Lock is released in <code>finally</code>; other workers can proceed |
| Two pods sharing JDBC/Redis registry | No two valid owners enter the critical section simultaneously under supported backend guarantees |
| Lock lease expires while handler is running | Ownership loss detected; prevents invalid data overwrites |
| Retry/redelivery of the same business event | Unique constraints/idempotency ensure no duplicate side effects |
| Endpoint stopped while waiting for lock | No leaked workers/locks; clear error path |

## 14. Production readiness checklist

- [ ] Lock represents the exact resource to protect; keys are namespaced, stable, and generated identically across all code paths.
- [ ] Confirmed whether the registry operates within one JVM or across multiple instances; clustered deployments use a shared backend and matching region/namespace.
- [ ] Every <code>lock()</code>/<code>tryLock()</code> has a guaranteed <code>unlock()</code> path in <code>finally</code>, executed only after successful acquisition.
- [ ] Defined lock wait budget, timeout/interrupt handling, and retry policy aligned with SLA, poller, and executor settings.
- [ ] Protected processing region has an appropriate transaction boundary; lock is not released before commit if that breaks consistency.
- [ ] Locks are not held across slow HTTP/IO when a safer transaction, queue, or workflow design exists.
- [ ] Idempotency keys or unique constraints protect against duplicate side effects; locks are not confused with exactly-once delivery.
- [ ] Distributed lease/renewal and lock-loss scenarios are tested, with stale-writer protection where needed.
- [ ] Lock wait, hold, timeouts, hot keys, thread pools, and error flows are monitored while avoiding exposure of sensitive keys.
- [ ] Single-JVM concurrency tests and multi-node tests exist when production runs multiple replicas.

**Conclusion:** <code>LockRegistry</code> allows Spring Integration and applications to maintain **exclusive processing rights for a specific key**. Choosing the right key, deciding between a local or distributed registry, locking the right scope, reliably releasing locks, and combining with transactions/idempotency are the prerequisites for consistent message flows under higher concurrency. Keyed locking is part of runtime design, not an automatic guarantee for an entire distributed flow.

## References

- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/6.5/distributed-locks.html)
- [Spring Integration Reference — Lock Advice (6.5)](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/lock.html)
- [Spring Integration Javadoc — LockRegistry 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/locks/LockRegistry.html)
- [Spring Integration Javadoc — DefaultLockRegistry 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/locks/DefaultLockRegistry.html)
- [Spring Integration Reference — Redis Lock Registry](https://docs.spring.io/spring-integration/reference/redis.html)
- [Spring Integration Reference — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html)

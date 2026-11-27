# Lock Timeout and tryLock in Spring Integration Runtime

## Lesson Objectives

In **SPRING_INTEGRATION_RUNTIME**, multiple channels, consumers, pollers, and executors may concurrently process messages belonging to an order or a correlation group. When two threads or two application instances update the same state at the same time, read–check–write operations are prone to race conditions. **LockRegistry** helps obtain locks by key to coordinate processing sections that require exclusive execution.

This lesson belongs to the **Lock registry** chapter and focuses on **Lock timeout and tryLock**: how to attempt acquiring a lock without waiting, wait with a bounded timeout, decide what to do on timeout, and handle distributed lock backends properly.

After this lesson, you will be able to:

- Explain **LockRegistry.obtain(lockKey)** and how to use **Lock.lock()**, **Lock.tryLock()**, and **Lock.tryLock(timeout, unit)**.
- Distinguish **lock wait time**, **lock hold time**, **transaction timeout**, **message deadline**, and **distributed lock lease/TTL**.
- Write handlers that always **unlock in finally**, preserve ownership properly, and handle **InterruptedException**.
- Choose among **fail-fast**, **bounded wait**, **delayed retry**, or **routing the message to recovery** when a lock is busy.
- Understand the limits of **DefaultLockRegistry** within a single JVM and the additional requirements when using Redis, JDBC, or ZooKeeper.
- Test contention, timeouts, interrupts, crashes, lease expiration, transaction rollbacks, and message redelivery.

> **Principle:** Acquiring a lock only protects the guarded work within the **scope and duration permitted by the implementation**. A lock does not automatically turn HTTP, DB, broker, and MessageStore operations into a single transaction.

## 1. Why does a message flow need a lock?

Suppose two consumers receive requests to update the same order O-42:

~~~text
Consumer A: reads order status = NEW
Consumer B: reads order status = NEW
Consumer A: transitions to RESERVED, records event
Consumer B: transitions to RESERVED, records a duplicate event
~~~

Within one JVM, **synchronized** or a local lock can protect part of the state. When Spring Integration scales across multiple instances, each JVM has its own memory and monitors; thus A's synchronized block does not stop B.

~~~mermaid
flowchart LR
    A["Instance A<br/>worker-1"] --> K["Lock key:<br/>order:O-42"]
    B["Instance B<br/>worker-3"] --> K
    K --> L[("Shared LockRegistry")]
    L --> S[("Shared state<br/>MessageStore / DB")]
~~~

Conditions for the diagram to actually protect data:

1. Every participant modifying the same resource uses **the same lockKey generation rule**.
2. They share **the same synchronization domain**: the same JVM for local locks, or the same backend/namespace for distributed locks.
3. Each participant touches the protected state **only after acquiring the lock** and obeys release rules.
4. Long-lived or multi-instance data also needs appropriate **transactions, optimistic locking, unique constraints, or idempotency**.

**A lock key is not MessageHeaders.ID.** A redelivered message may receive a new technical ID. When the goal is serializing processing per order, use **orderId** or a **stable correlation key**.

## 2. Core API: LockRegistry and java.util.concurrent.locks.Lock

Spring Integration defines **org.springframework.integration.support.locks.LockRegistry**. The primary usage contract is:

~~~java
import java.util.concurrent.locks.Lock;
import org.springframework.integration.support.locks.LockRegistry;

Lock lock = lockRegistry.obtain("order:O-42");
~~~

**obtain(key)** returns a **java.util.concurrent.locks.Lock** object representing the lock. Obtaining the Lock object **does not mean** you hold exclusive rights; you must call **lock()**, **tryLock()**, or **tryLock(timeout, unit)**.

| Lock API | Meaning | When to use |
| --- | --- | --- |
| **lock()** | Attempts to acquire the lock and waits until acquired, per the implementation's contract | Only when unbounded waiting is acceptable and interruption/shutdown behavior is understood |
| **tryLock()** | Attempts immediate acquisition; returns **true/false** without waiting for release | Handler must respond quickly when the resource is busy |
| **tryLock(timeout, unit)** | Waits up to the specified duration to try acquiring; returns true/false, may throw **InterruptedException** | Need to bound lock wait to protect latency and thread pools |
| **lockInterruptibly()** | Waits for the lock while remaining responsive to thread interruption | Need shutdown/cancellation support while waiting |
| **unlock()** | Releases an acquired lock | Always inside **finally** after successful acquisition |

With distributed implementations, a **tryLock()** call does not wait for **the lock to be released**, though talking to Redis/DB/ZooKeeper still incurs latency and can throw infrastructure exceptions. **The timeout of a timed tryLock** is a lock-wait limit per implementation; it is not a **guaranteed deadline** for the entire network and business call.

### Trying to acquire a lock immediately

~~~java
Lock lock = lockRegistry.obtain("order:O-42");
if (!lock.tryLock()) {
    // Another worker is currently processing the same key.
    // Decision: retry later, signal BUSY, or route to recovery.
    throw new LockBusyException("order O-42 is busy");
}

try {
    processOrder("O-42");
} finally {
    lock.unlock();
}
~~~

Here, **false** is an expected lock-contention outcome, not business success. If the handler **returns normally** when false, a poller/broker may treat the message as successfully processed, depending on acknowledgement and transaction settings.

### Trying to acquire a lock with a timeout

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;

Lock lock = lockRegistry.obtain("order:O-42");
boolean acquired = false;

try {
    acquired = lock.tryLock(300, TimeUnit.MILLISECONDS);
    if (!acquired) {
        throw new LockBusyException("Timeout waiting for order O-42");
    }
    processOrder("O-42");
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Thread interrupted while waiting for lock",
            interrupted);
} finally {
    if (acquired) {
        lock.unlock();
    }
}
~~~

Mandatory rules:

- **Only unlock when acquired == true**; calling unlock without owning the lock can cause errors.
- Never **swallow InterruptedException**: restore the interrupt flag or propagate per contract so shutdown/cancellation works.
- **LockBusyException** in the example is an application exception, not a built-in Spring Integration class.
- Never return success or ack a message simply because the wait timed out.
- Lock acquisition can fail due to **contention**, while the backend can also throw exceptions on connection loss; classify these two cases separately.

## 3. Example handler with locking and idempotency

The snippet below illustrates guarding each **orderId** inside a service activator. It uses the common **LockRegistry** API, so the locking code stays the same whether the application configures DefaultLockRegistry or a distributed implementation.

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.support.locks.LockRegistry;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

record OrderCommand(String orderId, String eventId, String targetStatus) {}

interface OrderRepository {
    // Must be atomic/idempotent (e.g., unique eventId and DB transaction).
    void applyIfNew(OrderCommand command);
}

class LockBusyException extends RuntimeException {
    LockBusyException(String message) {
        super(message);
    }
}

@Component
class OrderUpdateHandler {
    private final LockRegistry lockRegistry;
    private final OrderRepository repository;

    OrderUpdateHandler(LockRegistry lockRegistry, OrderRepository repository) {
        this.lockRegistry = lockRegistry;
        this.repository = repository;
    }

    @ServiceActivator(inputChannel = "orderUpdates")
    public void handle(Message<OrderCommand> input) {
        OrderCommand command = input.getPayload();
        if (command.orderId() == null || command.orderId().isBlank()
                || command.eventId() == null || command.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing orderId or eventId");
        }

        String lockKey = "order-update:" + command.orderId();
        Lock lock = lockRegistry.obtain(lockKey);
        boolean acquired = false;

        try {
            acquired = lock.tryLock(250, TimeUnit.MILLISECONDS);
            if (!acquired) {
                throw new LockBusyException("Busy lockKey=" + lockKey);
            }

            // Business update must tolerate duplicates/redelivery.
            repository.applyIfNew(command);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while acquiring " + lockKey, interrupted);
        } finally {
            if (acquired) {
                lock.unlock();
            }
        }
    }
}
~~~

This is a **contract example**, not a full deployable flow. You must declare the **LockRegistry** bean, repository, channels, and source/consumer. An implementation of **OrderRepository.applyIfNew** must protect DB atomicity, handle duplicate **eventId** values, and scope transactions properly; a Java lock does not replace those requirements.

**Why keep lock hold times short?** When locking per orderId, other orders can still run in parallel. Holding a lock across a 10-second HTTP request makes messages for the same orderId wait a long time; if the distributed lock backend has a short lease, ownership can even expire before the HTTP call finishes.

## 4. Distinguishing four easily confused timeouts

In Spring Integration Runtime, "timeout" can refer to different clocks:

| Clock | What does it measure? | What happens on expiration? |
| --- | --- | --- |
| **Lock wait timeout** | Waiting to **acquire** the lock, e.g., 250 ms | Timed tryLock returns false or is interrupted; critical section has not been entered |
| **Lock lease / TTL** | How long a distributed lock is considered valid by the backend | Backend may grant the same key to another worker even if the old worker has not finished |
| **Transaction timeout** | Duration a transaction may stay active per transaction manager | Transaction may roll back / be marked rollback-only; does not automatically revert external side effects |
| **Message deadline / gateway timeout** | Total time caller waits for business completion | Caller may time out and retry while the old worker is still running |

There are also **poller receive timeout**, **executor queue wait**, **aggregator group timeout**, and **HTTP connect/read timeout**. They do not automatically share an overall budget.

### Example: 300 ms lock wait, 5-second lease

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant L as Distributed lock
    participant B as Worker B
    A->>L: obtain K + acquire (lease 5 s)
    L-->>A: acquired
    B->>L: tryLock(K, 300 ms)
    L-->>B: false (lock is busy)
    Note over A: Work stalls or GC pauses > 5 s
    Note over L: Lease expires
    B->>L: tryLock(K) on new attempt
    L-->>B: acquired
    Note over A,B: Risk of two workers mutating data concurrently!
~~~

**Lock wait timeout = 300 ms** does not extend **lease = 5 seconds**. Once the lease expires, the implementation may revoke ownership; this depends on the backend and heartbeat/renewal configuration. If worker A is unaware it lost its lease and still writes to the DB, the distributed lock **no longer guarantees exclusivity** for that operation.

For resources requiring strong consistency, combine:

- **Fencing tokens** or **monotonically increasing version/epoch** so the data store rejects stale writers.
- **Optimistic locking/version conditions** in the DB (e.g., updating only when the current version still matches).
- **Idempotency keys / unique constraints** for business operations that may repeat.
- **Deadlines** for critical sections and explicit handling for ownership loss.

Never assume every LockRegistry issues fencing tokens or renews leases indefinitely. Read the contract of the **specific implementation** chosen.

## 5. Choosing the right LockRegistry scope

Spring Integration offers multiple **LockRegistry** implementations. Choice depends on instance count, infrastructure, latency, and required guarantees:

| Implementation | Coordination scope | Good fit when | What to verify |
| --- | --- | --- | --- |
| **DefaultLockRegistry** | **Single JVM** | Tests, single-instance apps, purely local state | Cannot lock across JVMs; restarts discard lock state |
| **JdbcLockRegistry** | Multiple JVMs sharing a **DB** | Already using an RDBMS and needing distributed locks | Lock table, transactions, lock lifetime, polling contention, cleanup |
| **RedisLockRegistry** | Multiple JVMs sharing **Redis** | Low latency, Redis infrastructure already available | TTL, renewal, failover, network partitions, ownership, and unlock |
| **ZookeeperLockRegistry** | Multiple JVMs sharing **ZooKeeper** | System already relies on ZooKeeper coordination | Session expiry, connection loss, watches/ownership, and recovery |

Minimal configuration for **a single JVM**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.integration.support.locks.LockRegistry;

@Configuration
class LocalLockConfiguration {
    @Bean
    LockRegistry lockRegistry() {
        return new DefaultLockRegistry();
    }
}
~~~

**Do not copy the configuration above into a multi-replica service** expecting it to protect shared groups: each replica creates its own DefaultLockRegistry. If multiple beans or flows must coordinate within **the same JVM**, they must likewise share the same registry instance or a consistent locking mechanism.

For distributed implementations, bean setup may require dedicated module dependencies, lock tables/schema policies, a RedisConnectionFactory, or a ZooKeeper client. TTL, renewal, and cleanup parameters vary across Spring Integration versions; configure per the documentation for your exact registry type and version, and test failure modes on real infrastructure.

## 6. Rules for building lock keys

A good lock key is **stable, narrow enough, and semantically unambiguous**:

~~~text
order-update:v1:tenant-A:O-42
order-update:v1:tenant-A:O-43
order-update:v1:tenant-B:O-42
~~~

Common mistakes:

- **Global locking** with a fixed string `"orders"` forces every order into a single queue, hurting throughput.
- **Overly narrow locking** using a fresh MessageHeaders.ID on every send puts two messages for the same order under two different locks.
- Missing **tenantId**, environment, or namespace causes independent applications to contend unnecessarily.
- Including **retry attemptId** in lockKey makes each retry bypass the previous attempt's lock, defeating mutual exclusion.
- Unnormalized keys: `"O-42"`, `"o-42"`, or strings with whitespace accidentally represent the same order under different locks.
- Using one lockKey for unrelated resources, or two different lockKey formats for the same invariant.

For multi-step business logic, identify the invariant before picking the key. For instance, **orderId** fits if all order state changes must serialize; **skuId** fits if all stock deductions for the same SKU must contend on one lock. However, if a single operation modifies **two SKUs**, locking on orderId alone does not protect the inventory invariant.

**Avoiding deadlocks when acquiring multiple locks:** Establish a consistent lock order, such as sorting SKUs and acquiring sequentially; set timeouts and release already-acquired locks if the next lock fails. Across multiple DB resources, database transactions and optimistic locking are often easier to manage than composing manual application locks.

## 7. When tryLock returns false: what to decide?

**tryLock returning false is not a random technical glitch**: it signals that the lock could not be acquired within the allowed time. The right action depends on message type and source contract.

~~~mermaid
flowchart TD
    A["Message arrives at handler"] --> L{"tryLock succeeded?"}
    L -- "Yes" --> W["Process in critical section"]
    W --> U["unlock in finally"]
    U --> OK["Result / ack per contract"]
    L -- "No" --> D{"Can wait or retry?"}
    D -- "Yes, budget left" --> R["Backoff / reschedule"]
    D -- "No" --> E["Business BUSY / quarantine / alert"]
    R --> A
~~~

### Three common approaches

**A. Fail-fast (tryLock())**: preferred when threads must be freed quickly, callers understand BUSY status, or messages can move to delayed retry. Fits high-throughput systems with durable queues; avoid hot retry loops.

**B. Timed wait (tryLock(250, MILLISECONDS))**: tolerates brief contention without tying up executors indefinitely. The contract still requires an **end-to-end deadline** and a fallback plan when acquisition fails.

**C. Unbounded wait (lock())**: consider only when waiting is genuinely acceptable and shutdown, thread capacity, and lease/network failures are handled. In polling flows or bounded executors, a long-held `lock()` can exhaust worker threads.

| Scenario when lock cannot be acquired | Appropriate response options | Risk to avoid |
| --- | --- | --- |
| Synchronous API needing fast response | Return BUSY/CONFLICT per explicit contract | Returning HTTP 200 and treating as complete |
| Broker consumer with redelivery | Throw exception or nack for adapter-backed backoff redelivery | Infinite tight-loop nacks |
| Polling endpoint reading from DB | Roll back / keep message in source per transaction | Removing from source and returning normally, losing the message |
| Durable retry queue | Bounded delay/requeue preserving the same idempotency key | Resetting attempt budget on every redelivery |
| Work is no longer valid after deadline | Record expired or business failure state | Keeping threads waiting for locks after the request expired |

**Important:** Across QueueChannel, pollers, and JMS/AMQP/Kafka adapters, **ack/commit/offset/redelivery** behavior varies by source and configuration. Never assume "throwing LockBusyException guarantees redelivery" without verifying the adapter's transaction and acknowledgement settings.

## 8. How does lock timeout relate to retries and error handling?

A message hitting lock contention may pass through multiple retry layers:

~~~text
Broker redelivery: max 4 deliveries
  → Handler RetryAdvice: max 3 attempts
      → tryLock(250 ms) inside each attempt
~~~

If every attempt waits until expiration, **up to 12 lock waits** can occur for a single business operation (not counting scheduled replays and caller retries). Waiting alone can reach **12 × 250 ms = 3 seconds** sequentially, before even accounting for backoff, dispatch, I/O, and overlapping deliveries.

To prevent retry storms:

1. Designate a **single retry owner** for lock contention: handler, broker, or scheduled replay; agree on a total budget.
2. Apply **backoff + jitter** when multiple consumers contend on the same lock.
3. Preserve the same **business idempotency key** across all attempts and redeliveries.
4. Bound **timeouts to remaining budget**, instead of waiting a fresh 250 ms endlessly after the caller's deadline passed.
5. Once budget is exhausted, write to a **FailureJournal/DLQ/quarantine** or explicit business failure state.
6. Do not retry every exception alike: invalid input or permission denied will not improve by waiting on a lock.

An **ErrorMessage** on errorChannel only means the failure was published via the configured error mechanism; it does not automatically return the message to the input channel. When an error occurs past an **ExecutorChannel**, the caller may already have finished `send`. Error flows should inspect **failedMessage/originalMessage** when present to recover business key, correlationId, attempt count, and cause.

### Lock wait timeout is not automatic transaction rollback

If a handler catches a timeout and returns normally, an outer transaction may commit depending on configuration. Conversely, throwing an exception **can** roll back the transaction, depending on rollback rules and transaction boundaries. You must test the concrete chain **poller → channel → handler → store → adapter**.

## 9. Locks and transactions: what do they preserve?

A lock protects a **critical section** according to key and implementation; a transaction protects **atomicity** of operations on compatible resources. They solve related problems without replacing each other.

Example:

~~~text
T1: acquire lock(order:O-42)
T2: open/enter DB transaction
T3: check state → update DB
T4: DB commit
T5: unlock
~~~

This ordering is usually straightforward: exclusivity is held **past the commit point**. However, if **@Transactional** wraps the method while the lock is released inside the method body **before the transaction proxy commits**, a gap opens: another worker can acquire the lock while DB changes are still uncommitted. Audit whether the **transaction interceptor sits outside or inside the lock** and use DB concurrency controls whenever correctness depends on commit visibility.

**Risk example:**

~~~text
@Transactional proxy starts transaction
  → handle(): acquire lock → update DB → unlock → return
@Transactional proxy only now commits transaction

Worker B acquires lock after unlock but before worker A commits.
~~~

For critical DB updates, prefer **unique constraints**, **optimistic locking**, or conditional updates so correctness does not rely solely on application-tier locks. Never place long transactions containing unbounded HTTP calls inside a lock.

### Locks do not automatically cross thread boundaries

~~~mermaid
flowchart LR
    P["Poller / transaction A"] --> D["DirectChannel"]
    D --> H["Handler holds lock"]
    P --> E["ExecutorChannel"]
    E --> W["Worker thread B<br/>transaction B if configured"]
~~~

- **DirectChannel** invokes synchronously on the sender's thread. It can share the same transaction when resources/advice align; multiple senders can still invoke the handler concurrently.
- **ExecutorChannel** hands off to a thread pool. The sender's transaction and ThreadLocal do not propagate automatically; a lock is held only if explicit code acquires it on the worker.
- **QueueChannel** and polling endpoints typically create a new consumption/transaction; a consumer lock timeout does not necessarily propagate back to the producer.

Never acquire a lock on thread A, hand off the critical section to thread B, and have B call unlock. With many **Lock** implementations, ownership is bound to the acquiring thread; unlocking from another thread can fail or violate the contract. Place the lock right where the business work executes.

## 10. LockRegistry in aggregators and MessageGroupStore

**Aggregators**, **resequencers**, and correlating endpoints typically maintain state by **groupId** in a **MessageGroupStore**. Two messages with the same groupId arriving concurrently can collide when adding messages, evaluating the release strategy, or marking the group complete.

~~~mermaid
flowchart TD
    M1["Message A<br/>groupId=O-42"] --> L["Lock by groupId"]
    M2["Message B<br/>groupId=O-42"] --> L
    L --> S[("MessageGroupStore")]
    S --> R{"ReleaseStrategy<br/>satisfied?"}
    R -- "No" --> S
    R -- "Yes" --> G["MessageGroupProcessor + output"]
~~~

For correlating handlers, Spring Integration uses a **LockRegistry** to synchronize group operations. **The default LockRegistry typically has single-JVM scope**; when multiple instances access a persistent store concurrently, evaluate **distributed locking** or an alternative concurrency mechanism.

Do not add an ad-hoc lock in a service activator under a **different key than groupId** and assume the aggregator is safe: the aggregator itself must be protected by the locking mechanism the endpoint actually uses. Nor should you wrap a manual outer lock around an aggregator using another lock without analyzing **acquisition order**, as that easily causes deadlocks.

**Remember to distinguish states:**

- **Release**: release strategy allows the group to emit output.
- **Complete**: the group is marked complete.
- **Expire**: group/metadata is purged according to policy.
- **Late arrival**: a message arriving after completion may be discarded or start a new group if metadata was removed.

The lock guards the state-update section; it does **not** decide release conditions, expiry, deduplication, or crash survival. A persistent MessageStore and idempotency remain necessary for correct runtime behavior.

## 11. Lease expiration and stale writers: the hardest problem

A distributed lock may need a **lease TTL** to avoid locking a key forever when an instance crashes. Yet TTL introduces the case where an old worker keeps running after its lease expires:

~~~text
00:00  Instance A acquires lock K, 5-second lease
00:02  A starts calling DB, stalls due to GC/network
00:05  A's lease expires; backend allows lock re-issuance
00:06  Instance B acquires lock K and writes version 8
00:07  A resumes and attempts to write version 7 data
~~~

If the DB cannot tell which writer is stale, A can overwrite newer data. **A past successful tryLock does not prove ownership is still valid right now.**

### Reducing risk with versioning/fencing

Example record with a **version** column:

~~~sql
UPDATE orders
SET status = :newStatus, version = version + 1
WHERE id = :orderId AND version = :expectedVersion;
~~~

If A passes `expectedVersion=7` while B already updated to `version=8`, the updated row count is **0** and A must handle the conflict instead of overwriting. When stale-writer protection spans multiple resource types, **monotonic fencing tokens** checked by each target resource may be more suitable if supported by the backend.

**Distinction:** A DB version check does not fully undo an external HTTP call A already made earlier. For external side effects, you need destination-side idempotency keys, reconciliation, or compensation. Distributed systems have their own failure modes such as split-brain, network partitions, and clock skew.

### When unlock fails

A distributed lock implementation may reject unlock if ownership expired or the backend is unavailable. Do not ignore this error:

- Record the cause, lockKey, thread/instance, and lock hold duration.
- Separate **business operation errors** from **lock release errors**; avoid letting an exception in `finally` mask the original root cause in logs/traces.
- Do not arbitrarily attempt to unlock from a different thread.
- Rely on health checks, alerts, and backend-appropriate cleanup/lease expiry—never forcefully delete a lock owned by another active process.

Ideal lock hold duration should be as short as possible, yet long enough to protect **the entire critical invariant**. Shortening hold time by unlocking early before DB commit can corrupt data.

## 12. Testing tryLock and timeouts in a single JVM

Here is a JUnit 5 test using **DefaultLockRegistry** to verify **timeout when another thread holds the same key**. Use latches/futures instead of fixed sleeps:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import java.util.concurrent.locks.Lock;
import org.junit.jupiter.api.Test;
import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.integration.support.locks.LockRegistry;

class LockTimeoutTest {

    @Test
    void timedTryLockFailsWhenAnotherThreadHoldsSameKey() throws Exception {
        LockRegistry registry = new DefaultLockRegistry();
        String key = "order:O-42";
        Lock primary = registry.obtain(key);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        primary.lock();
        try {
            Future<Boolean> attempted = pool.submit(() -> {
                Lock contender = registry.obtain(key);
                boolean acquired =
                        contender.tryLock(100, TimeUnit.MILLISECONDS);
                if (acquired) {
                    contender.unlock();
                }
                return acquired;
            });

            assertFalse(attempted.get(2, TimeUnit.SECONDS));
        } finally {
            primary.unlock();
            pool.shutdownNow();
        }

        // After release, a new attempt can acquire the lock.
        Lock next = registry.obtain(key);
        assertTrue(next.tryLock());
        next.unlock();
    }
}
~~~

This test is meaningful because two threads **genuinely contend on the same key**; trying to acquire twice sequentially on the same thread with a **reentrant** lock would succeed on the second call and mislead the test.

**Additional variants to include:**

1. **tryLock() fail-fast:** thread B receives false while A holds the lock.
2. **Timed wait succeeds:** A releases before B's timeout; B acquires and unlocks cleanly.
3. **Interrupt:** B is interrupted while waiting in timed tryLock; verify InterruptedException handling and that business work is not reported as succeeded.
4. **Different keys:** A holding `order:O-42` does not block processing `order:O-43`.
5. **Exception in critical section:** repository throws; lock is still released by finally.
6. **Multiple producers:** send messages with the same orderId to handlers across multiple workers; verify no two critical sections overlap.
7. **No leaks:** after thousands of failures, messages for the same key can still acquire the lock and the pool never stalls.

### A test verifying non-overlapping critical sections

Use **AtomicInteger active** and **AtomicInteger maxActive** inside a fake repository. Upon entering, increment active, update maxActive, and decrement active in finally. When all messages for the **same key** complete successfully, **maxActive must equal 1**. With different keys, allow maxActive > 1 to prove the lock does not inadvertently serialize the entire system.

Never treat single-JVM tests with DefaultLockRegistry as proof for Redis/JDBC in a cluster. Distributed locks need more realistic test environments to verify failover and network failures.

## 13. Testing distributed locks, crashes, and transactions

Important scenarios for integration tests:

| Case | How to reproduce | Result to verify |
| --- | --- | --- |
| Two instances, same key | A holds lock K, B calls timed tryLock K | B does not enter critical section before lock is granted |
| Two instances, different keys | A holds K1, B acquires K2 | Both run concurrently; no overly broad locking |
| Lock wait timeout | A holds longer than B's wait timeout | B reports BUSY/timeout and enters proper retry/recovery |
| Instance crash while holding lock | Kill A after acquire | Backend releases/allows recovery per lease contract; no permanent deadlock |
| DB/Redis disconnect | Cut connection right during acquire/unlock | Infrastructure error is observable; never treated as acquired |
| Lease expires while A still runs | A stalls past lease, B acquires same key | Stale writer blocked via version/fencing/idempotency |
| Slow transaction commit | A unlocks before commit | Test detects and eliminates concurrency gap |
| Retry/redelivery | Same eventId delivered multiple times | No duplicate side effects produced |
| Executor saturation | Many messages waiting on same key | Pool/queue does not block indefinitely; backpressure applies |
| Flow restart with MessageStore | Pending messages recovered | Old locks expire/recover; state stays consistent |

**Do not verify only the acquire boolean.** Check DB record counts, emitted events, data versions, message store state, retry counts, lock ownership, and external system effects. A test checking only that B returned false does not prove B could not write to the DB via another code path.

## 14. Runtime observability and performance diagnostics

When diagnosing "slow flow" or "stuck messages", check lock contention alongside poller backlogs, executor saturation, and DB latency.

| Signal | Questions to ask |
| --- | --- |
| **lock wait latency p50/p95/p99** | Which keys are contended? Is the deadline sufficient? |
| **tryLock success/failure rate** | Are timeouts caused by real contention or backend errors? |
| **lock hold duration** | How long is the handler holding the lock across HTTP/DB transactions? |
| **active/blocked workers** | Are thread pools tied up by `lock()` or long timed `tryLock` calls? |
| **backend lock errors** | Is Redis/DB/ZooKeeper experiencing timeouts, failover, or session expiry? |
| **stale lease / unlock failures** | Is the lease too short, did a process pause, or was ownership lost? |
| **broker redelivery / RetryAdvice attempts** | Are contention retries causing a retry storm? |
| **group release latency** | Is the aggregator waiting on locks, missing messages, or slow ReleaseStrategy? |
| **duplicate/conflict count** | Are lock keys inconsistent or are store/idempotency protections insufficient? |

Example structured log emitted intentionally by the application:

~~~text
flow=orderUpdate endpoint=orderUpdateHandler
orderId=O-42 eventId=E-19 correlationId=checkout-42
lockKey=order-update:O-42
lockWaitMs=250 acquired=false
backend=redis thread=order-worker-8
decision=DELAYED_RETRY attempt=2
~~~

Log a **sanitized/safe lockKey**, avoiding PII or tokens. Measure **hold duration** and **wait duration** separately: raising timeouts may lower BUSY rates while increasing latency, tying up threads, and hurting throughput.

### Quick diagnostic checklist

1. **Is it the right registry?** Is each instance using its own local DefaultLockRegistry while mutating a shared DB?
2. **Is it the same key?** Did the key accidentally include attemptId, differ in casing, or lack a namespace?
3. **What is waiting?** Timed tryLock, unbounded `lock()`, DB transaction, HTTP call, or broker ack?
4. **Waiting how long?** Is the lock wait timeout larger than the caller deadline, poller interval, or executor budget?
5. **Who still holds the lock?** Hung thread, slow DB commit, failed lease renewal, or expired TTL?
6. **What happens on false?** Does the handler throw/retry, or silently return and mark the message complete?
7. **What happens after unlock?** Has the DB committed yet; can an old worker write after lease expiry?
8. **Where are error details?** Do you have ErrorMessage, failedMessage, correlationId, and idempotency key for investigation?

## 15. Practice exercise: safe order update processing

**Problem statement:** A Spring Integration flow receives order updates from a broker. There are three workers per instance, and two instances access the same DB. Some messages share duplicate eventIds; occasionally a worker takes 8 seconds. Each message has a 2-second deadline for synchronous requests, though broker events can retry durably later.

Requirements:

- Messages with the same **orderId** must not concurrently corrupt business state.
- Messages with different orderIds must not be blocked by a global lock.
- When the lock is busy, do not tie up a worker for more than **200 ms** per attempt.
- Never apply the same **eventId** twice.
- If the lock backend disconnects or a lease expires, the system must not overwrite newer updates.
- When retry budget is exhausted, errors must land in a clear terminal state.

**Design direction:**

1. Use a **distributed LockRegistry** because there are two instances; build lock key **order-update:{tenant}:{orderId}**.
2. Call **tryLock(200, MILLISECONDS)** in the consumer before running the critical section.
3. On false, return a classifiable error so scheduled retry / broker redelivery runs **with backoff**, under one retry owner and a bounded budget.
4. On true, run a DB transaction/conditional update with **unique eventId** and **version**; use proper exception/rollback semantics.
5. Keep lock hold time controlled. Avoid slow HTTP calls inside the lock unless strictly required and lease/ownership safety is ensured.
6. When unlock or the backend fails, record **lock outcome** and business state separately; configure alerts and reconciliation.
7. Downstream consumers process events idempotently; critical event-publishing flows use an outbox to survive crashes.
8. Test with at least two JVMs across contention, timeout, retry, stale lease, and restart cases.

### Self-check questions

**Question 1:** A worker calls **tryLock(300, MILLISECONDS)**, receives false, and returns normally. Will the broker message definitely be redelivered?

**Answer:** **No.** Depending on adapter/ack/transaction settings, normal handler completion may be treated as processed. To trigger retry, define an explicit policy, throw an exception, or enqueue durable retry/recovery per the source contract.

**Question 2:** A worker acquires a distributed lock and runs for 10 seconds while the lease is only 5 seconds. Is it guaranteed to still be the owner?

**Answer:** **No.** The backend may expire the lease and grant the lock to another worker; verify the implementation's renewal/ownership contract and guard the DB with versioning/fencing/idempotency.

**Question 3:** If the lock is released in finally while the DB transaction only commits after the method returns, are two workers guaranteed never to read uncommitted state?

**Answer:** **No.** There is a gap between unlock and commit. Adjust the lock/transaction boundary or let the DB enforce invariants via concurrency control.

**Question 4:** Why is testing in a single JVM with DefaultLockRegistry insufficient to conclude correctness when scaling to two replicas?

**Answer:** Because the two replicas maintain **separate registries and locks**; only a distributed backend or shared concurrency mechanism coordinates across JVMs. Test with at least two instances and a shared data store.

## 16. Pre-deployment checklist

- Is the lock key a **stable business/correlation key**, not a message ID or attempt ID?
- Did you distinguish **LockRegistry.obtain()** from actually acquiring the lock?
- When using tryLock(timeout), did you check **true/false** and handle **InterruptedException**?
- Do you unlock only in **finally** after successful acquisition, on the exact owning thread?
- Are lock wait timeout, transaction timeout, HTTP timeout, message deadline, and lease TTL defined separately?
- For multi-JVM deployments, do you use a distributed registry with failover testing instead of DefaultLockRegistry?
- Did you handle lease expiration while a worker is still running using versioning/fencing and idempotency?
- Does the lock guard only the necessary invariant without a global key creating unnecessary contention?
- When the lock cannot be acquired, does the message have an explicit **retry/recovery** path rather than a false success ack?
- Did you avoid hot/multi-layer retry loops and preserve budget across broker redeliveries?
- Are locks and transactions placed on the right thread and **commit** boundary?
- Do aggregators, MessageGroupStore, and consumers sharing keys use a consistent locking mechanism?
- Do you have logs/metrics for contention, hold time, timeouts, backend errors, unlock failures, and correlation?
- Do you have tests for fail-fast, timed wait, interrupts, concurrency, lease expiry, multi-instance, and restarts?

## Conclusion

**tryLock** is the primary tool for managing contention in Spring Integration Runtime: you can probe immediately or wait for a bounded duration, then route messages to retry/recovery if the lock cannot be acquired. **LockRegistry** supplies locks by key, while the chosen implementation determines whether scope is single-JVM or distributed.

Sound design considers **channels, endpoints, consumers, pollers, executors, transactions, retries, message stores, and correlation** together. Never confuse **lock wait time** with **lease TTL**, never unlock before the invariant is protected, and never mistake a lock for an exactly-once guarantee. Combine **deadlines, idempotency, DB concurrency control, observability, and multi-instance testing** so flows recover safely under contention or backend failures.

## References

- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration API — LockRegistry](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/locks/LockRegistry.html)
- [Java SE API — Lock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html)

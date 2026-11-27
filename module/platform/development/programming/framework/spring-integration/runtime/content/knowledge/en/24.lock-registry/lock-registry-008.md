# Lock Latency and Throughput Impact in Spring Integration

## 1. Why is a message flow slow even with many workers?

In **SPRING_INTEGRATION_RUNTIME**, messages flow through `MessageChannel`, endpoints, consumers, pollers, and executors. Adding more workers normally lets independent messages run in parallel. However, when multiple messages must update **the same state** — such as the same aggregator `MessageGroup` — they must pass through a mutually exclusive region controlled by `LockRegistry`. Multiple threads end up **waiting on the same lock**, preventing throughput from scaling proportionally.

The topic **Lock registry → Lock latency and throughput impact** helps you understand:

1. Why a hot `correlationId` can become a bottleneck even when the executor still has spare CPU.
2. How to break down registry lookup time, lock wait time, lock hold time, unlock time, and downstream processing.
3. How to estimate throughput from critical-section duration, independent key count, and worker count.
4. Differences between single-JVM `DefaultLockRegistry` and JDBC/Redis/ZooKeeper distributed locks.
5. How to measure and optimize while preserving consistency, transactions, retries, correlation, and recovery.

Example: 20 messages all carrying `correlationId = "ORDER-42"` arrive at an aggregator simultaneously. Only one thread may update group state at a time; the other 19 threads must wait.

~~~mermaid
flowchart LR
    M["20 messages ORDER-42"] --> E["Executor: 20 workers"]
    E --> L{"obtain(ORDER-42) then lock()"}
    L -->|One thread holds lock| G["Read / update MessageGroup"]
    L -->|Other threads| W["Wait for ownership"]
    G --> U["unlock()"]
    U --> W
    W --> L
~~~

A lock is a **state-access synchronization tool**; it does not by itself guarantee idempotency, atomic commits, or exactly-once message processing.

## 2. LockRegistry and the intervals to measure

Spring Integration defines `org.springframework.integration.support.locks.LockRegistry`. Its core API is `obtain(Object lockKey)`, returning a `java.util.concurrent.locks.Lock`:

~~~java
Lock lock = lockRegistry.obtain("tenant-1:order-42");
lock.lock();
try {
    updateSharedGroup();
}
finally {
    lock.unlock();
}
~~~

**`obtain()` does not mean you have acquired exclusive access.** Only calling `lock()`, `lockInterruptibly()`, or `tryLock()` performs acquisition.

Since Spring Integration **6.2**, `executeLocked()` manages acquisition and release:

~~~java
LockRegistry registry = new DefaultLockRegistry();

registry.executeLocked("order:42", () -> {
    updateSharedGroup();
});

// Throws TimeoutException if lock cannot be acquired within wait time.
registry.executeLocked(
        "order:42",
        Duration.ofMillis(250),
        () -> updateSharedGroup());
~~~

This snippet illustrates API usage and assumes required imports and `updateSharedGroup()` are provided; callers handle `InterruptedException`, `TimeoutException`, or task exceptions according to the signature used. `Duration.ofMillis(250)` bounds **lock wait time**, not execution time inside the critical section.

| Measurement | Start and end | Meaning |
| --- | --- | --- |
| `T_obtain` | Before/after `registry.obtain(key)` | Lookup, lock wrapper allocation, cache/hash stripe |
| `T_wait` | Before `lock()/tryLock()` until successful acquire | Contention wait, thread scheduling, polling/backend network |
| `T_hold` | Right after acquire until before unlock | Exclusive hold duration |
| `T_unlock` | Inside `unlock()` | Releasing local lock or updating distributed backend |
| `T_queue` | Waiting for executor/poller/consumer availability | Not lock latency, though it adds to total message latency |
| `T_flow` | End-to-end across a flow | Includes queue, lock, I/O, and downstream |

~~~text
Message enters
  -> executor queue wait (T_queue)
  -> registry.obtain(key) (T_obtain)
  -> lock acquisition wait (T_wait)
  -> critical update / store I/O (T_hold)
  -> unlock (T_unlock)
  -> reply / downstream / ack
~~~

Separating these intervals accurately tells you whether to optimize SQL, lock hold scope, retry schedules, thread pools, or the distributed lock backend.

## 3. Critical-section duration limits per-key throughput

Suppose each message holds a lock for an average of `S` seconds, and every message has **the same key** and must pass through that section. The ideal ceiling for the guarded section is:

\[
\lambda_{\text{1 key}} \le \frac{1}{S}
\]

If `S = 0.010 s` (10 ms), a single key tops out at roughly **100 operations/s** in the simple model, before overhead. Scaling workers from 4 to 64 will not let two threads mutate the same group under the same lock simultaneously.

If there are `K` truly independent keys, `P` workers, and uniform key distribution:

\[
\lambda_{\text{total}} \lesssim \frac{\min(K,P)}{S}
\]

This is only a **reference upper bound**; actual throughput depends on key skew, database/network latency, hash stripe collisions, scheduling, and downstream throughput.

| `S` per message | Independent keys | Workers | Ideal upper bound |
| --- | ---: | ---: | ---: |
| 10 ms | 1 | 16 | ~100 messages/s |
| 10 ms | 4 | 16 | ~400 messages/s |
| 10 ms | 16 | 16 | ~1,600 messages/s |
| 20 ms | 1 | 16 | ~50 messages/s |
| 20 ms | 16 | 16 | ~800 messages/s |

What matters most is the **key frequency distribution**, not just total distinct keys. If you have 1,000 order IDs yet 80% of messages share `"BATCH-ALL"`, one hot group will dominate p99 latency. By contrast, when each order uses a proper business correlation key, distinct groups can be updated concurrently.

When the arrival rate on a single key exceeds sequential processing capacity, `T_wait` and executor queues grow. Threads waiting on locks still occupy worker slots in the pool, affecting even unrelated keys that are not contending.

~~~text
Key A: worker-1 [work A] -> worker-2 [work A] -> worker-3 [work A]
       ---------- Only one critical section at a time ----------

Key B: worker-4 [work B] can run concurrently with key A
Key C: worker-5 [work C] can run concurrently with A/B
~~~

## 4. DefaultLockRegistry: lock striping and false contention

`DefaultLockRegistry` is backed by `ReentrantLock` **within one JVM**. Spring Integration 6.x Javadoc states that the implementation uses an array of **striped locks**:

- Default mask `0xFF` creates **256** lock stripes.
- `obtain(key)` selects a stripe via `key.hashCode() & mask`.
- Two **different** keys can share a lock if their masked hashes collide.
- Constructor `DefaultLockRegistry(int mask)` accepts masks of form `2^n - 1`; for instance, `0x3FF` creates 1,024 stripes.

~~~java
LockRegistry registry = new DefaultLockRegistry(0x3FF);

Lock lockA = registry.obtain("order-A");
Lock lockB = registry.obtain("order-B");
~~~

Never assume `lockA != lockB` merely because two keys are unequal. Stripe collisions produce **false contention**: unrelated keys wait on each other even though their business state is independent.

| Symptom | Cause | Change to try |
| --- | --- | --- |
| One hot key; adding workers stays slow | Messages genuinely require the same lock | Reduce `T_hold`; partition work by contract-valid keys |
| Many independent keys still block each other | Hash mask collisions in `DefaultLockRegistry` | Inspect hash distribution; consider increasing stripes |
| Two JVMs mutating the same group race | `DefaultLockRegistry` applies only per JVM | Use a shared distributed registry for shared state |
| Increasing stripes gives no improvement | Bottleneck is a single key or the database | Re-measure `T_wait` and `T_hold` instead of raising stripes blindly |

Adding stripes can reduce collisions, but **does not help** if all messages share one key. `DefaultLockRegistry` itself provides neither distributed mutual exclusion nor transactions.

## 5. How do JDBC and Redis locks add latency?

When multiple Spring Integration instances share a `MessageGroupStore` or a lockable resource, a distributed registry is usually needed to coordinate ownership. Added costs include network RTT, database/Redis operations, polling or notifications, lease renewals, and backend load.

| Registry | Synchronization scope | Typical costs | Notes |
| --- | --- | --- | --- |
| `DefaultLockRegistry` | Within process/JVM | Scheduling, contention, hash stripes | Do not use alone for cross-pod shared state |
| `JdbcLockRegistry` | Instances connected to matching lock repository/DB | SQL, connection pool, polling between tries | DDL, `region`, TTL/ownership must match |
| `RedisLockRegistry` | Instances sharing the same Redis lock namespace | Redis RTT, spin/pub-sub, expiry | Verify topology and release semantics |
| `ZookeeperLockRegistry` | Instances sharing a ZooKeeper ensemble | Session/watcher coordination, network | Requires session/failover operations |
| Custom registry | Per implementation | Depends on backend | Verify atomicity and failure handling |

### 5.1. JDBC: `idleBetweenTries` and polling

Since Spring Integration **5.1.8**, `JdbcLockRegistry` exposes `idleBetweenTries`. Documentation notes a default of **100 ms** in those versions. When an owner on another instance releases a lock, a contender may wait until its next retry attempt to observe the lock is free.

**100 ms is not a fixed cost for every acquire.** An uncontended lock can be acquired quickly, while database lock contention, connection pool waits, or network latency make real wait times longer. Lowering `idleBetweenTries` can trim tail latency at the cost of higher DB query frequency.

Also verify:

- DDL/primary key of the lock table, region/key namespace, and queries issued by `DefaultLockRepository`.
- Connection pool: if many workers wait for DB connections just to poll locks, adding workers can overload the DB further.
- TTL: lease duration must cover critical-section time or use renewal. If an owner dies, lease expiration enables recovery; if an owner runs past TTL, two nodes can mutate state together.
- Since 6.4, `JdbcLock.unlock()` can throw `ConcurrentModificationException` when ownership expired; treat that as a data-safety issue to investigate.
- TTL-related APIs and DDL changed in 7.x; use the exact schema matching your version when upgrading.

### 5.2. Redis: SPIN_LOCK, PUB_SUB_LOCK, and TTL

For `RedisLockRegistry`, documentation since Spring Integration **5.5.13** describes two modes via `RedisLockType`:

| Mode | How it waits for locks | Trade-off |
| --- | --- | --- |
| `SPIN_LOCK` | Polls periodically, typically ~100 ms interval | Broad compatibility, involves network polling |
| `PUB_SUB_LOCK` | Receives notification when owner unlocks | Can reduce network chatter and tail wait where supported |

Documentation notes `SPIN_LOCK` is the default in those versions because some Redis Master/Replica setups do not support the required pub/sub pattern. Do not enable `PUB_SUB_LOCK` without verifying your Redis infrastructure.

Redis locks have a documented default expiration of **60 seconds** in those versions; this is configurable. Short TTLs speed up recovery after an instance crash while increasing the risk of **losing ownership** during slow handlers, GC pauses, or network partitions.

Spring Integration 6.4 adds a configurable renewal task scheduler for Redis; Spring Integration 7.0 adds `DistributedLock` and per-acquire TTL for JDBC/Redis. When unlocking an expired lock, 6.4+ can throw `ConcurrentModificationException`. Treat this as a signal that the resource was exposed to concurrent access—never catch and ignore it.

### 5.3. Comparing under identical correctness requirements

You cannot compare single-instance `DefaultLockRegistry` speed against shared JDBC/Redis locks to argue distributed locks are "not worth it". A fast local lock that **fails to protect a shared group across multiple JVMs** is simply incorrect when nodes write to a shared store.

Distributed locks also **do not create exactly-once processing**: DB transactions, message acks, broker redeliveries, retries, and external APIs still require dedicated idempotency or coordination. If a node loses its lease yet keeps writing, you may need version checks or **fencing tokens validated by the target resource**, rather than relying on an expired mutex.

## 6. Aggregators, resequencers, and hot correlation keys

An aggregator uses a `MessageGroupStore` to hold messages sharing a correlation key until release. Group mutations must be synchronized; `LockRegistry` acquires the lock for the group ID. Messages with the same `correlationId` therefore run **sequentially for group updates**, while distinct groups can be processed concurrently.

~~~mermaid
flowchart TD
    A["Message #1 / correlationId=G1"] --> L1["Lock G1"]
    B["Message #2 / correlationId=G1"] --> L1
    C["Message #3 / correlationId=G2"] --> L2["Lock G2"]
    L1 --> S1[("Group G1")]
    L2 --> S2[("Group G2")]
    S1 --> R1{"Release strategy"}
    S2 --> R2{"Release strategy"}
~~~

Throughput drivers:

- **Correlation strategy** must separate independent workloads. Using one constant key for every batch forces almost the entire flow to serialize.
- **Group store I/O** under the lock: slow queries, heavy serialization, and DB transaction waits directly inflate `T_hold`.
- **Release strategy**: optimize around needed state/metadata; avoid scanning/rebuilding the entire group on every message when alternatives exist.
- **Synchronous output dispatch**: if an aggregator holds the lock while sending output over a `DirectChannel` to a slow downstream, locks stay held longer.
- **Shared store in a cluster**: requires a shared distributed registry using the same key; default `DefaultLockRegistry` is insufficient across instances.

Spring Integration provides **`releaseLockBeforeSend`** (since 5.1.1) to release the lock before dispatching output, lowering deadlock risk and hold times in suitable flows. Verify release behavior, ordering, and post-unlock error handling before enabling it. Since 6.5, `AbstractMessageGroupStore` also supports locking group metadata via `setLockRegistry(...)`; verify exact versions and providers.

### Deadlock between two aggregators

~~~text
Thread T1: aggregator A holds lock A
  -> synchronously calls aggregator B, needs lock B

Thread T2: aggregator B holds lock B
  -> synchronously calls aggregator A, needs lock A

T1 waits for B, T2 waits for A -> deadlock
~~~

Spring Integration documentation suggests flow-level options: separate registries per aggregator when appropriate, `ExecutorChannel`/`QueueChannel` between stages, or `releaseLockBeforeSend`. These changes alter boundaries and can affect transactions/error handling, so re-verify correctness afterward.

## 7. Instrumentation: measure wait and hold instead of guessing

~~~java
Lock lock = registry.obtain(key);
long waitStart = System.nanoTime();

lock.lockInterruptibly();
long acquiredAt = System.nanoTime();

try {
    performGroupUpdate();
}
finally {
    long beforeUnlock = System.nanoTime();
    lock.unlock();
    long afterUnlock = System.nanoTime();

    long waitNs = acquiredAt - waitStart;
    long heldNs = beforeUnlock - acquiredAt;
    long unlockNs = afterUnlock - beforeUnlock;

    metrics.record("lock.wait", waitNs);
    metrics.record("lock.held", heldNs);
    metrics.record("lock.unlock", unlockNs);
}
~~~

This is an **instrumentation snippet**; `registry`, `key`, `metrics`, and `performGroupUpdate()` are application-defined. With distributed locks, `unlock()` can throw an exception; record that error separately rather than assuming release succeeded.

Use `System.nanoTime()` for elapsed intervals and convert to milliseconds/seconds when reporting. Never measure lock wait times using wall-clock timestamps that can jump. Track p50, p95, p99, and failure counts, not just averages.

| Suggested metric | Detects |
| --- | --- |
| `lock.obtain.duration` | Abnormal wrapper/cache lookup latency |
| `lock.acquire.wait` (p50/p95/p99) | Hot keys, polling delays, contention, starvation |
| `lock.held.duration` | Long critical sections / I/O |
| `lock.release.duration` | Slow backend unlock |
| `lock.timeout.count` and `lock.interrupted.count` | Waits exceeding budget / cancelled workers |
| `lock.owner_lost.count` | Expired leases or lost ownership |
| `executor.active` and `executor.queue.depth` | Workers blocked waiting, backlog |
| `flow.input.rate` and `flow.output.rate` | Arrival exceeding completion rate |
| `message.group.age` and `message.group.size` | Aggregator backlog growth |
| `db.pool.wait`, `redis.command.latency` | Lock/store backend saturation |

These metric names are **instrumentation examples**, not metrics emitted automatically by Spring Integration. Never tag metrics with full `correlationId`, `orderId`, or raw lock keys due to high cardinality; use endpoint, registry type, result, and traffic tier. Put specific keys only in privacy-controlled traces/logs.

## 8. Runnable example: local hot-key vs. 16-key benchmark

This example uses **Java 17+** and a compatible `spring-integration-core` dependency (6.2+/7.x). Place the entire snippet in `LockLatencyDemo.java` under package `demo.integration`. It runs 1,600 tasks across 16 workers, each holding a lock for roughly 2 ms. The two runs differ only in key selection.

~~~java
package demo.integration;

import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.LockSupport;
import java.util.function.IntFunction;

import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.integration.support.locks.LockRegistry;

public final class LockLatencyDemo {

    private static final int WORKERS = 16;
    private static final int OPERATIONS = 1600;
    private static final long HOLD_NANOS =
            TimeUnit.MILLISECONDS.toNanos(2);

    public static void main(String[] args) throws InterruptedException {
        run("ONE HOT KEY", i -> "group-HOT");
        run("SIXTEEN KEYS", i -> "group-" + (i % 16));
    }

    private static void run(String label, IntFunction<String> keyFor)
            throws InterruptedException {

        LockRegistry registry = new DefaultLockRegistry(0x3FF);
        ExecutorService executor = Executors.newFixedThreadPool(WORKERS);

        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(OPERATIONS);
        ConcurrentLinkedQueue<Long> waitNs = new ConcurrentLinkedQueue<>();
        ConcurrentLinkedQueue<Long> heldNs = new ConcurrentLinkedQueue<>();
        AtomicInteger failed = new AtomicInteger();

        try {
            for (int i = 0; i < OPERATIONS; i++) {
                final int index = i;

                executor.execute(() -> {
                    try {
                        start.await();
                        Lock lock = registry.obtain(keyFor.apply(index));

                        long waitStart = System.nanoTime();
                        lock.lockInterruptibly();
                        long acquiredAt = System.nanoTime();

                        try {
                            // Simulate state update requiring synchronization.
                            LockSupport.parkNanos(HOLD_NANOS);
                        }
                        finally {
                            long beforeUnlock = System.nanoTime();
                            lock.unlock();

                            waitNs.add(acquiredAt - waitStart);
                            heldNs.add(beforeUnlock - acquiredAt);
                        }
                    }
                    catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        failed.incrementAndGet();
                    }
                    finally {
                        finished.countDown();
                    }
                });
            }

            long startedAt = System.nanoTime();
            start.countDown();
            finished.await();

            double seconds =
                    (System.nanoTime() - startedAt) / 1_000_000_000.0;
            int completed = waitNs.size();

            System.out.printf(
                    "%s completed=%d failed=%d duration=%.3fs "
                    + "throughput=%.1f msg/s waitP95=%.3fms "
                    + "heldP95=%.3fms%n",
                    label, completed, failed.get(), seconds,
                    completed / seconds,
                    percentileMs(waitNs, 95),
                    percentileMs(heldNs, 95));
        }
        finally {
            executor.shutdownNow();
        }
    }

    private static double percentileMs(
            ConcurrentLinkedQueue<Long> samples, int percentile) {

        long[] values = samples.stream()
                .mapToLong(Long::longValue)
                .sorted()
                .toArray();

        if (values.length == 0) {
            return Double.NaN;
        }

        int pos = Math.max(0, Math.min(values.length - 1,
                (int) Math.ceil(
                        percentile / 100.0 * values.length) - 1));
        return values[pos] / 1_000_000.0;
    }
}
~~~

### Interpreting the results properly

| Workload | Relative expectation | Why |
| --- | --- | --- |
| `ONE HOT KEY` | High `waitP95`, capped throughput | 16 workers contend on a single lock |
| `SIXTEEN KEYS` | Lower `waitP95`, higher throughput | Multiple independent lock keys exist |
| Increasing workers with 1 key | Throughput barely changes, wait grows | Exclusive operations per second cannot increase |
| Increasing lock hold time | Throughput drops | `1/S` decreases in the simple model |

**This is an illustrative experiment, not a production benchmark.** `LockSupport.parkNanos` is affected by OS scheduling, CPU throttling, and GC; thread pools/queues also add overhead. Never treat laptop numbers as JDBC/Redis SLAs. For serious benchmarks, include warm-up, multiple iterations, p95/p99 alongside backlog, the real backend, and realistic traffic.

Extension exercise: vary `WORKERS` from 4 to 32, increase `HOLD_NANOS`, change 16 keys to 2/4/64 keys, and test the default `0xFF` mask vs. larger masks. Observe when throughput stops scaling.

## 9. Shortening lock hold times while preserving correctness

An effective technique is moving operations that **do not require mutual exclusion** outside the critical section.

**Poor choice when I/O can be separated:**

~~~java
registry.executeLocked(accountKey, () -> {
    Account state = repository.load(accountKey);
    RemoteProfile profile = remoteClient.fetchProfile(accountKey);
    repository.update(state, profile);
});
~~~

If the HTTP call takes 300 ms, the lock stays held throughout the network wait.

**Separating I/O when the contract allows:**

~~~java
RemoteProfile profile = remoteClient.fetchProfile(accountKey);

registry.executeLocked(accountKey, () -> {
    Account state = repository.load(accountKey);
    repository.updateIfVersionMatches(state, profile);
});
~~~

The second version is safe only if profile data can be fetched beforehand and the update enforces an appropriate **version/conditional check**. If the remote call depends on state just read inside the lock, design explicit read/version/retry handling. Never shrink a critical section by breaking consistency.

Optimization techniques:

- Keep the locked scope to minimal read-check-update; move heavy logging, serialization, and HTTP calls outside when semantics allow.
- Optimize DB indexes and group store queries; avoid loading an entire group merely to inspect small metadata.
- Fix correlation strategies so **genuinely independent** work uses distinct keys.
- Use `releaseLockBeforeSend` when appropriate for aggregator flows, verifying downstream behavior and post-unlock errors.
- Avoid nested locks; when multiple locks are needed, enforce a consistent acquisition order.
- For high-conflict DB workloads, compare optimistic locking/CAS against mutexes; test duplicates and rollbacks before switching.

Do not try to drive `T_hold` to zero by removing locks when the store requires atomic group updates. The goal is **eliminating unnecessary exclusive hold time**.

## 10. LockRequestHandlerAdvice for endpoints (Spring Integration 6.5+)

Spring Integration 6.5 introduces `LockRequestHandlerAdvice`. It evaluates a key from the message and calls `LockRegistry.executeLocked()` around the handler scope; distinct keys can execute concurrently per registry semantics.

~~~java
// Java config example; requires application handler/channel beans.
@Configuration
class LockAdviceConfiguration {

    @Bean
    LockRegistry lockRegistry() {
        return new DefaultLockRegistry(0x3FF);
    }

    @Bean("accountLockAdvice")
    LockRequestHandlerAdvice accountLockAdvice(LockRegistry lockRegistry) {
        LockRequestHandlerAdvice advice =
                new LockRequestHandlerAdvice(lockRegistry,
                    message -> {
                        AccountCommand command =
                                (AccountCommand) message.getPayload();
                        return command.tenantId() + ":" + command.accountId();
                    });

        advice.setWaitLockDurationExpressionString("'PT1S'");
        return advice;
    }
}

record AccountCommand(String tenantId, String accountId, long delta) { }

@MessageEndpoint
class AccountEndpoint {

    @ServiceActivator(
        inputChannel = "accountCommands",
        adviceChain = "accountLockAdvice")
    public void handle(AccountCommand command) {
        // Example: call account update service with its own transaction.
        accountService.apply(command);
    }
}
~~~

This snippet is **not standalone**: it requires imports for `@Configuration`, `@Bean`, `@MessageEndpoint`, `@ServiceActivator`, `LockRequestHandlerAdvice`, `LockRegistry`, `DefaultLockRegistry`, an injected `accountService` bean, and the `accountCommands` channel. It illustrates lock scope and wait limits.

Limitations to understand:

- `waitLockDuration` limits **waiting to acquire**, not handler execution time.
- Returning a `null` key causes the advice to skip locking and proceed; configure a discard channel if keyless messages should be rejected.
- The advice wraps the target handler, not automatically every downstream endpoint; for reply-producing handlers, request-handler advice scope can end before reply dispatch.
- When running multiple instances against a shared store, replace the local registry with the proper distributed registry backend.
- If a handler fails after causing side effects, retries/redeliveries can still re-invoke it. Locks do not replace idempotency.

## 11. Timeouts, TTL, renewal, retries, and transactions

### Lock wait timeout

~~~java
Lock lock = registry.obtain(key);

if (!lock.tryLock(250, TimeUnit.MILLISECONDS)) {
    throw new TimeoutException("Unable to obtain lock within 250ms");
}

try {
    process();
}
finally {
    lock.unlock();
}
~~~

`tryLock()` can throw `InterruptedException`. Callers must classify timeouts vs. interruptions and never retry infinitely. An overly short timeout on a hot key raises failure rates and fuels retry storms.

### Lease TTL vs. wait timeout

| Scenario | Behavior to consider |
| --- | --- |
| `tryLock` waits past deadline | Acquisition fails; handler is not invoked |
| Lock acquired but TTL expires | Owner can lose exclusivity while still running |
| Owner dies while holding lock | TTL enables another instance to recover after expiration |
| `unlock()` after losing ownership | Can throw severe error; verify state correctness |
| Lock renewal falls behind | Lease can still expire due to GC pauses or network issues |
| Lock released but broker redelivers | Message can run again; idempotency is required |

When an external system accepts an update after an owner lost its lease, a simple TTL lock cannot stop the stale owner. Design **fencing tokens / conditional versions / idempotency** at the target resource per requirements.

### Retry advice before vs. after lock advice

~~~text
[retryAdvice, lockAdvice] -> handler
  attempt 1: acquire -> handler throws -> unlock
  backoff outside lock
  attempt 2: acquire -> handler returns -> unlock

[lockAdvice, retryAdvice] -> handler
  acquire -> attempt 1 throws -> backoff -> attempt 2 -> unlock
  lock held across retry/backoff duration
~~~

The first arrangement avoids holding locks during backoff, though business invariants may require holding the lock across the entire sequence. With retries, account for acquisition attempts, timeouts, and effects committed prior to failure.

### Transactions and async boundaries

- `DefaultLockRegistry` is not a database transaction manager.
- `JdbcLockRegistry` uses a DB, yet lock ownership does not automatically merge atomically with business transactions.
- `DirectChannel` normally preserves the call stack and transaction thread, whereas `ExecutorChannel`/pollers establish separate execution boundaries.
- If a thread waits on a lock inside an open transaction, it holds DB connections/locks longer, spreading contention to other components.
- Recovery callbacks may swallow exceptions and make upstream think a message succeeded. Verify ack/rollback/error channels for your exact flow.

Never use distributed locks in place of outboxes/inboxes, `MessageStore`, broker acks, or bounded retry rules.

## 12. Diagnosing production issues from symptoms

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Adding executor threads leaves throughput flat | Hot key or long critical section | `T_wait`, `T_hold`, key distribution |
| Low CPU yet growing queue | Workers waiting on locks or I/O | Thread dumps, active executors, DB/Redis |
| p99 wait rises after scaling pods | Higher distributed lock contention | Wait per instance, group, polling |
| Distinct keys still wait on each other in one JVM | `DefaultLockRegistry` striped hash collision | Mask/hash distribution |
| Redis/JDBC wait high despite small `T_hold` | Poll interval / network / backend latency | Acquire vs. held vs. unlock; spin/pub-sub |
| Aggregator holds groups too long | Overly broad correlation key, slow release/store | Group size/age, store queries |
| Workers hang with zero progress | Nested lock/aggregator deadlock | Thread dumps, lock order cycles |
| Unlock throws after GC pause | Lease/TTL expired before completion | TTL, renewal, GC logs |
| One pod mutates state while another holds lock | Local registry on shared store or lost ownership | Shared registry, TTL, fencing |
| Timeouts worsen backlog | Immediate retries on same hot key | Cap retries, backoff, DLQ |

Debugging steps:

1. Locate the **actual acquire/release points** and keys used by aggregators, advice, or manual code.
2. Measure `T_obtain`, `T_wait`, `T_hold`, and `T_unlock` separately.
3. Analyze key distribution over 1–5 minute windows to spot hot keys and skew.
4. Correlate arrival/completion rates, queue depth, consumer lag, and oldest message age.
5. Check thread pools, DB connections, network RTT, Redis/JDBC lock queries, and GC pauses.
6. Run fault injection: long lock holds, TTL expiration, process kills, slow Redis/DB, multi-node contention.
7. Change one factor at a time—workers, key cardinality, stripe mask, critical section, poll interval—while keeping business invariants intact.
8. Verify after tuning: no lost group updates, no duplicate side effects, no broken correlation or transactions.

## 13. Distinctions to keep straight when optimizing

- **True contention**: multiple messages legitimately need the same logical key; cannot be fixed by adding stripes.
- **False contention**: distinct keys share a hash stripe in a local registry; inspect mask configuration.
- **Backend latency**: Redis/JDBC round trips, polling, and connection pools; measure with real distributed setups.
- **Lock wait timeout**: bounds how long a contender waits, not lease TTL.
- **Lock TTL**: bounds ownership lifetime; expiring while a handler runs puts correctness at risk.
- **Message latency**: also includes queues, pollers, executors, transactions, stores, and downstream steps.
- **Retries**: can multiply acquisitions or hold locks across backoffs depending on advice ordering.
- **Correlation**: grouping rules directly govern how many keys can proceed concurrently.
- **Transactions/idempotency**: commit/ack/recovery semantics must still be designed independently of mutexes.

## 14. Practice exercises

1. Run `LockLatencyDemo` with 1 hot key vs. 16 keys. Compare throughput, `waitP95`, and `heldP95`.
2. Increase `WORKERS` from 4 to 16 to 32 with a single key; explain why throughput barely changes.
3. Keep worker count fixed and increase `HOLD_NANOS` from 2 ms to 10 ms; compare against the `1/S` ceiling.
4. Construct keys sharing the same hash mask to demonstrate false contention; switch to `DefaultLockRegistry(0x3FF)` and re-test.
5. Build an aggregator with 1,000 messages sharing one `correlationId` vs. spread across many groups; measure group age and `T_wait`.
6. Test `releaseLockBeforeSend` or decoupling with `ExecutorChannel` in a test environment; compare latency and downstream semantics.
7. With a shared persistent `MessageGroupStore` across two application instances, test local locks then distributed locks to verify races and consistency.
8. If using JDBC, vary `idleBetweenTries` and measure both p99 wait **and** query rate; avoid tuning wait by overloading the DB indefinitely.
9. If using a compatible Redis setup, compare `SPIN_LOCK` vs. `PUB_SUB_LOCK` on your real topology while monitoring network traffic.
10. Intentionally let a handler run past TTL in a test environment; verify lost-ownership errors are not swallowed.
11. Swap `retryAdvice`/`lockAdvice` order, measure hold time across backoff, and check side effects/idempotency.
12. Capture a thread dump when two aggregators acquire locks in opposite order, then fix the flow to eliminate deadlock.

## 15. Official references

- [Spring Integration — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html): `LockRegistry`, `executeLocked()`, distributed providers, and TTLs.
- [Spring Integration — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation groups, lock scope, release, and deadlocks.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): synchronized message group metadata and backends.
- [Spring Integration — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html): `idleBetweenTries`, TTL, renewal, and ownership.
- [Spring Integration — Redis Lock Registry](https://docs.spring.io/spring-integration/reference/redis.html#redis-lock-registry): `SPIN_LOCK`/`PUB_SUB_LOCK`, expiry, and renewal.
- [Spring Integration — Lock Request Handler Advice](https://docs.spring.io/spring-integration/reference/handler-advice/lock.html): `LockRequestHandlerAdvice`, wait duration, and message keys.
- [Javadoc — LockRegistry (6.4)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/support/locks/LockRegistry.html): `executeLocked` signatures.
- [Javadoc — DefaultLockRegistry (6.5)](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/locks/DefaultLockRegistry.html): hash mask, striped locks, and constructors.

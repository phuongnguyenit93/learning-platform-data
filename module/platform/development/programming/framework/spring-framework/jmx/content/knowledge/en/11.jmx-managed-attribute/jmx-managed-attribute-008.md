# Checking Whether a Getter Causes Queries or Side Effects

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a getter exposed with `@ManagedAttribute` can be invoked repeatedly by JMX clients, not just when a user clicks to view an attribute.
- Distinguish getters that only read in-memory state from getters that trigger database queries, HTTP calls, file reads, lock waits, or data mutations.
- Identify **side effects** and risks regarding latency, thread contention, transactions, security, resources, and downstream dependencies.
- Design JMX attributes based on snapshots or counters updated in business flows, keeping getters cheap and semantically clear.
- Perform behavioral verification using tests, profilers/metrics, and live observation during JConsole or exporter polling.
- Know when to use an explicit JMX operation instead of a getter that looks like a read-only check.

## 2. Why Must a Managed Getter Be Inspected?

In Spring JMX, `@ManagedAttribute` marks a method to be exposed as a managed attribute. Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderMonitor {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

A JMX client may request:

```java
server.getAttribute(objectName, "PendingCount");
```

This call triggers execution of the getter logic (according to MBean metadata and dispatch mechanism). **JMX does not automatically turn a getter into a pre-cached value.** If the getter runs a SQL query or calls an external system, every client attribute read can generate additional work.

This is the danger when a seemingly harmless `getXxx()` method actually performs an expensive operation:

```java
@ManagedAttribute
public long getPendingCount() {
    return orderRepository.countPendingOrders(); // May query DB.
}
```

A JConsole view refreshing every few seconds, an exporter polling every 15 seconds, and multiple operators opening dashboards concurrently can trigger many query executions. If the table is large or the database is congested, the act of observing itself can increase load right when the system needs diagnosis.

**Principle:** A managed getter should have explicit cost and effect; never assume `get` implies "safe, fast, and free of side effects."

## 3. How Does JMX Read Attributes?

General path:

```text
JConsole / JMX exporter / custom client
                  |
          getAttribute("PendingCount")
                  |
                  v
             MBeanServer
                  |
             JMX metadata
                  |
                  v
          @ManagedAttribute getter
                  |
         +--------+---------+
         |                  |
         v                  v
    read RAM value     query DB/HTTP
    fast, stable      has latency, errors, load
```

When an exporter polls multiple attributes via `getAttributes`, the implementation can still call each corresponding getter. Execution frequency depends on the exporter, filters, and polling cadence—never assume each attribute is read only once during the application's lifecycle.

For an MBean managing a long-lived process, clients may connect concurrently:

- JConsole/JMC or operational tools.
- Metric-collecting exporters.
- Administrative health-checking systems.
- Automation scripts.
- Developers querying manually through a JMX client.

Thus the getter becomes **an execution entry point from outside the application**. Attributes that are "read-only" from JMX's perspective can still produce side effects if the method body has side effects.

## 4. Distinguishing Read-Only Attributes, Pure Functions, and Side Effects

A getter can be a *read-only attribute* when JMX metadata lacks a setter, yet that only states that **clients cannot invoke a setter for that attribute**. It does not guarantee the implementation avoids writing to a database or mutating state.

Three levels to distinguish:

| Getter Kind | Example | Assessment |
|---|---|---|
| **RAM snapshot read** | `return cachedPendingCount.get();` | Usually suitable for JMX polling |
| **Lightweight calculation, no state change** | `return success.sum() + failure.sum();` | Usually acceptable if cost is small |
| **External/expensive source read** | `repository.countByStatus(...)` | Must evaluate latency and load |
| **Performs side effect** | `refreshCache(); return size;` | Unsuitable for read-only getter expectations |
| **Waits on synchronization/long locks** | `synchronized` on a contended lock | Risks causing stalls |
| **Makes network calls** | `httpClient.getStatus()` | Prone to timeouts, introduces external dependency failures |

A getter might not modify data yet still be **operationally unsafe** if it forces a full table scan, spawns threads, opens new connections, or holds locks for long periods. Conversely, reading an in-memory counter takes only a few CPU operations with minimal dependencies.

A **pure getter** in the strict sense alters no observable state and performs no I/O; in practical Java, however, there may be minor allocations, clock reads, internal caching, or synchronized access. The operational goal is **stable semantics, bounded cost, and avoiding unintended side effects**.

## 5. Signs That a Getter Is "Hiding" Expensive Work

Inspect the implementation and methods that the getter calls indirectly. Notable warning signs include:

- Repository methods such as `countByStatus`, `findAll`, `fetch`, `save`, `flush`.
- `EntityManager.createQuery`, `JdbcTemplate.queryForObject`, aggregation queries.
- HTTP/gRPC/Redis/Kafka client calls to another process.
- File reads, directory scans, or external storage checks.
- Loops iterating over large collections or summing on every getter call.
- `Thread.sleep`, locks, latches, blocking futures, `join()`.
- Lazy object initialization, cache loading, or config refreshing.
- Heavy logging on every read, inflating log volume.
- Incrementing counters, resetting statistics, clearing state, or updating timestamps.

Not every sign is an absolute ban. For instance, `countByStatus` on a small, well-indexed table might meet requirements, but **latency and repetition under polling** must be well understood. Even a read-only query still puts load on the DB.

## 6. Bad Example: JMX Getter Querying the Database on Every Read

Suppose a Spring bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderMonitor {

    private final OrderRepository repository;

    public OrderMonitor(OrderRepository repository) {
        this.repository = repository;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return repository.countPendingOrders();
    }
}
```

Path:

```text
Exporter poll 15s
       |
       v
getPendingOrders()
       |
       v
SELECT COUNT(*) ... WHERE status='PENDING'
       |
       v
Database CPU / index scan / network
```

If the query takes 300 ms, a single collector might not cause serious trouble. However, load can escalate when multiple instances or multiple collectors poll concurrently, and the query slows down further when the database is saturated.

Approximate frequency calculation example:

```text
4 collectors x 1 request/15s = 16 reads/minute
10 apps x 16 = 160 reads/minute
```

This is merely an illustration assuming **each collector actually reads the attribute independently**; it is not a universal formula for all exporter setups. Actual frequency must be measured in deployment.

Getters can also throw exceptions such as timeouts or exhausted connection pools. When that happens, dashboards lose metrics precisely when the system is in trouble.

## 7. Solution 1: Update a Counter When Business State Changes

If the pending count can be derived from application state transitions, maintain an in-memory metric and let the getter read it quickly.

Example:

```java
import java.util.concurrent.atomic.AtomicLong;

public class OrderStatistics {
    private final AtomicLong pending = new AtomicLong();

    public void onOrderQueued() {
        pending.incrementAndGet();
    }

    public void onOrderCompleted() {
        pending.decrementAndGet();
    }

    public long getPending() {
        return pending.get();
    }
}
```

Management bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderManagement {

    private final OrderStatistics statistics;

    public OrderManagement(OrderStatistics statistics) {
        this.statistics = statistics;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return statistics.getPending();
    }
}
```

Thus every JMX attribute read only invokes `AtomicLong.get()`, with no DB query.

### Considerations

- The counter must be updated at **the exact state transition point**; if a transaction rolls back, it must not be counted as completed.
- If the app has multiple replicas, an in-JVM counter only represents **that instance**, not automatically the cluster-wide total.
- Counters can drift after restarts, crashes, or external data modifications.
- `onOrderCompleted` should not allow the count to go negative under unexpected states.
- When authoritative numbers are needed, use a periodic background reconciliation/snapshot process instead of querying inside every getter call.

In-memory counters optimize for fast reads, yet accuracy depends on update logic. Do not convert a database measurement into a RAM counter without clarifying semantics.

## 8. Solution 2: Snapshot Updated on a Separate Schedule

If a metric must be aggregated from a database or external system, update a snapshot via a separately managed task:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PendingOrderSnapshot {

    private final OrderRepository repository;
    private final AtomicLong latestValue = new AtomicLong();
    private volatile long refreshedAtEpochMillis;

    public PendingOrderSnapshot(OrderRepository repository) {
        this.repository = repository;
    }

    @Scheduled(fixedDelayString =
            "\${monitoring.pending-refresh-ms:30000}")
    public void refresh() {
        long count = repository.countPendingOrders();
        latestValue.set(count);
        refreshedAtEpochMillis = System.currentTimeMillis();
    }

    public long currentValue() {
        return latestValue.get();
    }

    public long refreshedAtEpochMillis() {
        return refreshedAtEpochMillis;
    }
}
```

And the JMX management bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderSnapshot,name=primary")
public class PendingOrderManagement {

    private final PendingOrderSnapshot snapshot;

    public PendingOrderManagement(PendingOrderSnapshot snapshot) {
        this.snapshot = snapshot;
    }

    @ManagedAttribute
    public long getPendingOrders() {
        return snapshot.currentValue();
    }

    @ManagedAttribute
    public long getLastRefreshEpochMillis() {
        return snapshot.refreshedAtEpochMillis();
    }
}
```

In Spring, `@Scheduled` requires scheduling to be enabled, such as via `@EnableScheduling` in an appropriate configuration. Before the scheduler runs, the initial value (0 in the example) **is not necessarily real data**. Production systems should explicitly represent "uninitialized," "refresh failed," or "stale snapshot" states using additional attributes.

### Advantages

- Decouples JMX read frequency from DB query frequency.
- Bounds the number of queries according to schedule.
- When the DB is slow, JMX getters still return the previous snapshot instead of blocking directly on the query.
- Refresh timestamps allow observing whether data is fresh or stale.

### Trade-offs

- Values have latency; not an instantaneous database snapshot.
- Multiple replicas may still refresh simultaneously, creating background load.
- Refresh failures must be recorded to avoid silently serving stale numbers.
- Appropriate transaction/isolation levels and data-fetching methods must be considered.

If using a shared scheduler across many jobs, a slow query can delay other jobs. Separating cadence from JMX getters does not automatically solve all background load issues.

## 9. Designing Attributes to Represent Data Freshness

When using snapshots, expose at least the value and update status:

```text
PendingOrders = 125
LastRefreshEpochMillis = 1794391200000
SnapshotHealthy = true
```

You can also add:

- `LastRefreshDurationMillis`: duration of the last query.
- `RefreshFailures`: count of failed refreshes.
- `SnapshotAgeMillis`: age at read time (lightweight calculation using the clock).
- `LastErrorCode`: short code containing no sensitive data.
- `RefreshInProgress`: status flag if needed.

A getter computing `SnapshotAgeMillis` from `System.currentTimeMillis()` and the stored timestamp is typically quite cheap:

```java
@ManagedAttribute
public long getSnapshotAgeMillis() {
    long updatedAt = snapshot.refreshedAtEpochMillis();
    return updatedAt == 0L
            ? -1L
            : Math.max(0L, System.currentTimeMillis() - updatedAt);
}
```

This is a short calculation creating no queries. `-1` is an example convention for "no snapshot yet"; clearly document its meaning for operators and exporters, since not all metric systems handle negative sentinel values well.

## 10. Dangerous Side Effects: Getters Mutating State

Example to avoid:

```java
@ManagedAttribute
public long getPendingOrders() {
    long count = repository.countPendingOrders();
    repository.markMetricsRead(); // Writes state while merely viewing.
    return count;
}
```

Or:

```java
@ManagedAttribute
public int getRetryQueueSize() {
    retryQueue.purgeExpired(); // May delete items.
    return retryQueue.size();
}
```

A JMX client merely intending to view metrics inadvertently triggers system changes. If monitoring runs frequently, side effects occur frequently and become hard to trace.

Separate clearly:

- **Getter/attribute:** reads a snapshot or performs a cheap calculation, executing no management actions.
- **Operation:** deliberate actions like `refreshSnapshot()`, `clearCache()`, `resetStatistics()`.

Example:

```java
@ManagedAttribute
public long getPendingOrders() {
    return snapshot.currentValue();
}

@ManagedOperation
public void refreshSnapshot() {
    snapshot.refresh();
}
```

Operations must also have proper permissions and load limits; exposing an operation is not automatically safe. For potentially long-running operations, consider returning a job status and executing asynchronously under control instead of blocking the JMX thread for long periods.

## 11. Can a Getter Block Threads or Cause Deadlocks?

A getter might do no I/O yet still pose risks if it waits on a lock held by business logic:

```java
@ManagedAttribute
public int getPendingOrders() {
    synchronized (sharedLock) {
        return expensiveAggregateOverLargeMap();
    }
}
```

If aggregation takes several seconds while holding the lock, JMX polling can contend with business threads. Conversely, business code holding the lock for a long time stalls JMX readers, and clients may time out.

Risks to check:

- Lock contention and lock hold duration.
- Calling other methods inside a lock leading to lock inversion.
- Blocking on `Future.get()`, `CountDownLatch.await()`, or external locks.
- Iterating over large collections inside a critical section.
- Mutable values where readers may observe unsynchronized state.

Solutions depend on workload: `AtomicLong`, `LongAdder`, immutable snapshots, short-held read/write locks, or metric registry mechanisms. Do not force atomics onto every complex structure when multi-field consistency is needed.

### LongAdder vs. AtomicLong?

`LongAdder` suits counters updated frequently under contention, though `sum()` is not a strictly atomic snapshot while multiple threads keep updating. `AtomicLong` supports atomic reads/writes of a single long value. Choose based on the semantics you wish to expose, not solely on throughput.

## 12. Concurrency and Consistency Across Multiple JMX Attributes

Suppose an MBean has:

```text
Queued = 100
Processed = 500
Failed = 20
```

Clients may read each attribute at slightly different times. Meanwhile workers continue updating, so combining individual values may not reflect a single consistent snapshot.

Do not assume `MBeanServer.getAttributes()` guarantees all attributes are computed at the same atomic instant. If consumers need multi-field consistency, you can:

1. Create an immutable snapshot object swapped atomically.
2. Expose one compound attribute containing the related fields.
3. Include a generation/timestamp to identify matching snapshots.
4. If computation is complex, update the snapshot outside the getter thread.

Example:

```java
public record QueueSnapshot(
        long queued,
        long processed,
        long failed,
        long updatedAtMillis) {}
```

Getters can return simple numeric fields from a `volatile QueueSnapshot`. To expose a record as a JMX attribute across Standard MBean mechanisms requires considering type mapping; MXBeans have dedicated open-type mapping rules. Never assume every Java record is supported by JMX serialization/mapping without configuration.

## 13. Does the Getter Invoke @Transactional or @Cacheable?

A `@ManagedAttribute` getter may invoke a service wrapped by a Spring AOP proxy. If the service runs a database query inside a transaction, actual behavior depends on proxies, transaction propagation, and runtime configuration.

Example:

```java
@ManagedAttribute
public long getPendingOrders() {
    return orderService.countPendingOrders();
}
```

Even if `countPendingOrders()` is annotated `@Transactional(readOnly = true)`, every JMX poll can still open a transaction and run SQL. `readOnly=true` is a hint or transaction mode depending on the stack; it does not guarantee low getter cost or zero side effects.

`@Cacheable` can reduce query counts, yet:

- Cache misses still hit the DB.
- Cache expiry triggers refreshes at polling time.
- Concurrent client requests can cause a stampede if the cache is not coordinated properly.
- Cached values may be stale.
- Proxy/self-invocation affects whether advice actually runs.

Therefore `@Transactional(readOnly = true)` or `@Cacheable` is not a certification that a getter is "safe for monitoring."

## 14. Quantifying Getter Read Cost

To decide whether a getter suits exporter polling, know at least:

- **Normal latency:** average, p95, p99.
- **Latency when dependencies slow down:** whether explicit timeouts exist.
- **Invocation frequency:** number of collectors × interval × number of instances.
- **Resource consumption:** SQL queries, CPU, allocations, network, lock waits.
- **Business impact:** connection pool usage, thread contention, throughput.
- **Failure behavior:** throws exceptions, blocks, returns stale value or sentinel.
- **Data freshness:** whether freshness satisfies operational needs.

Suppose a getter takes 200 ms and is called 12 times/minute in one JVM. Cumulative execution time totals nearly 2.4 seconds/minute if calls are sequential, yet from that number alone you cannot infer CPU utilization or congestion; the getter might mostly be waiting on I/O. If calls overlap and share a DB pool with business traffic, the impact can be much larger.

Reducing the polling interval from 30 seconds to 5 seconds increases request frequency roughly sixfold **assuming constant client count and collection schedules**. That is why frequency must be factored in right from getter design.

## 15. Testing for Side Effects with Unit Tests

A test can verify that a getter does not access the repository when merely reading a snapshot.

JUnit 5 and Mockito example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class OrderManagementTest {

    @Test
    void getterReadsSnapshotWithoutDatabaseQuery() {
        OrderRepository repository = mock(OrderRepository.class);
        OrderStatistics statistics = new OrderStatistics();
        statistics.onOrderQueued();

        OrderManagement management =
                new OrderManagement(statistics);

        assertEquals(1L, management.getPendingOrders());
        assertEquals(1L, management.getPendingOrders());

        verifyNoInteractions(repository);
    }
}
```

This example illustrates the principle: the getter reads `OrderStatistics` without calling the repository. In production code, if the repository is not even in the dependency graph of the tested object, asserting `verifyNoInteractions` on a mock never passed into the system is purely illustrative. A more meaningful test **injects a spy/mock for a real dependency the getter could call**, then verifies zero I/O calls; or uses integration tests with an SQL statement counter.

### Testing Real Side Effects

With an implementation prone to side effects:

```java
class BadMonitor {
    private final OrderRepository repository;

    BadMonitor(OrderRepository repository) {
        this.repository = repository;
    }

    long getPendingOrders() {
        return repository.countPendingOrders();
    }
}
```

Test:

```java
@Test
void getterDoesNotQueryDatabase() {
    OrderRepository repository = mock(OrderRepository.class);
    when(repository.countPendingOrders()).thenReturn(10L);

    BadMonitor monitor = new BadMonitor(repository);
    monitor.getPendingOrders();

    verify(repository, never()).countPendingOrders();
}
```

This test **will fail intentionally**, proving the getter executes a query and fails the "no I/O in getter" requirement. Do not treat a failing test as a final standard; refactor to a snapshot-reading getter and re-run the test against a real dependency graph.

If requirements allow bounded queries, use integration/performance tests measuring query count and latency instead of asserting "zero I/O."

## 16. Testing Through MBeanServer, Not Just Direct Java Calls

A getter can work when called directly yet differ due to exporter/proxy/metadata behavior. With Spring JMX, test via `MBeanServer`:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.shop.orders:type=OrderMonitor,name=primary");

Object value = server.getAttribute(name, "PendingOrders");
System.out.println(value);
```

This snippet assumes the MBean was registered in the platform MBeanServer under the corresponding ObjectName; Spring may use a different MBeanServer depending on configuration. Do not treat that code as a self-contained example without the registration/export step.

During verification, collect:

1. Number of times the getter is called for one read request.
2. Number of SQL queries, HTTP calls, or Redis calls.
3. Latency and exceptions.
4. Thread/lock contention under concurrent client reads.
5. Impact on business workloads as frequency increases.
6. `MBeanInfo` confirming the attribute has the right name and read-only/writable semantics.

Also test while JConsole or an exporter actually runs, as tools may poll multiple attributes or more clients may connect than anticipated.

## 17. Observing Getters in Operational Environments

A practical strategy:

- Instrument metrics measuring **snapshot refresh** or background query duration.
- Track refresh failure counts, snapshot age, and latest refresh timestamp.
- Observe SQL query counts emitted from monitoring code paths.
- Use a profiler, Java Flight Recorder, or thread dumps when suspecting locks/blocking.
- Measure load when exporters/JConsole connect.
- Configure appropriate timeouts for any mandatory I/O.
- Avoid adding INFO/ERROR logging on every normal getter call, which causes log spam.

If adding instrumentation to a getter, the instrumentation itself must be lightweight. An in-RAM timer/counter is usually suitable; logging or sending network requests every time a getter is read creates an expensive observation loop.

## 18. When to Use an Operation Instead of an Attribute?

JMX attributes are usually treated as data that can be read repeatedly. The following actions should be modeled as **operations** if they genuinely need to be exposed:

- `refreshCache()`
- `recalculateStatistics()`
- `reconcileDatabaseCounts()`
- `resetCounters()`
- `purgeExpiredEntries()`
- `reloadConfiguration()`

Example:

```java
@ManagedOperation(description = "Refresh pending count snapshot")
public void refreshPendingOrders() {
    snapshot.refresh();
}
```

An operation can consume resources or mutate state, so it must be access-controlled, bounded by timeouts, and logged/audited appropriately if operationally significant. **Do not turn a getter into an operation just to dodge quality checks**; choose the API according to behavioral semantics.

If a value requires expensive computation whenever operators explicitly request it, expose a `calculateCurrentCount()` operation with documented cost, while keeping a `CachedCount` attribute returning a cheap snapshot.

## 19. Management Design Example for a Cache

A cache has:

```text
EntryCount
HitCount
MissCount
LastRefreshEpochMillis
RefreshHealthy
```

**Suitable getters:**

```java
@ManagedAttribute
public long getHitCount() {
    return hitCounter.sum();
}

@ManagedAttribute
public long getMissCount() {
    return missCounter.sum();
}

@ManagedAttribute
public int getEntryCount() {
    return cacheStatsSnapshot.entryCount();
}
```

**Risky getter:**

```java
@ManagedAttribute
public int getEntryCount() {
    return remoteCache.scanAllKeys().size();
}
```

If every read has to scan an entire remote cache, re-evaluate metric semantics and use built-in cache statistics, counters/registries, or background snapshots. Even a `size()` call on a distributed cache can be an expensive distributed operation depending on implementation.

## 20. Notes on Sensitive Data and External Side Effects

JMX getters can be invoked by clients granted read access. Never let getters return secrets like passwords, access tokens, raw customer data, or unnecessary personal details.

Even an attribute that does not mutate local state can cause side effects **in external systems**:

- Increasing request counts against rate-limited APIs.
- Incurring per-API-call billing.
- Touching remote caches and refreshing access timestamps.
- Reading databases with locks/isolation causing contention.
- Initializing connections or refreshing credentials.
- Writing audit events per system policy.

Therefore inspect the getter's **entire call graph**, not just three lines of code inside the annotated method.

For remote JMX, configure authentication, encryption, and access control separately on the connector/server. The `@ManagedAttribute` annotation does not automatically enforce business-role authorization for clients.

## 21. Common Issues and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Database slows down when JConsole opens | Getter runs SQL on every read | Switch to snapshot, lower cadence, or optimize query |
| Exporter causes timeouts | Getter performs high-latency HTTP/DB reads | Bound I/O, add timeouts, background refresh |
| JMX read alters cache | Getter performs `refresh`, `purge`, or lazy initialization | Separate operation from getter |
| Attribute shows stale value | Snapshot not refreshing or refresh failing | Expose timestamp/health and freshness alerts |
| Counter differs from DB total | Increment/decrement on wrong transition or restart | Reconcile periodically, document per-JVM semantics |
| Dashboard loses metrics on dependency outage | Getter throws exception from external source | Return prior snapshot with stale flag, monitor refresh errors |
| Threads blocked by monitoring | Getter holds lock or awaits future | Shrink critical section, use atomics/snapshots |
| Unexpected surge in queries | Multiple exporters/collectors polling concurrently | Check request frequency and collector configuration |
| Transaction advice has no effect | Self-invocation or target call bypassing proxy | Keep boundary via Spring proxy, check AOP |
| Attribute exists but reading fails | Export metadata works, runtime getter throws exception | Inspect logs/stack trace and MBeanServer call |

## 22. Practice Exercises

### Exercise 1 — Classify Getters

Consider:

```java
@ManagedAttribute
public long getProcessedCount() {
    return processedCounter.sum();
}

@ManagedAttribute
public long getFailedCount() {
    return repository.countFailedOrders();
}

@ManagedAttribute
public long getCacheSize() {
    cache.removeExpiredEntries();
    return cache.size();
}
```

Classify:

1. Reads a RAM counter at minimal cost.
2. Triggers a database query on every JMX poll.
3. Has a side effect deleting cache entries.

Propose how to replace methods (2) and (3) with a snapshot or operation.

### Exercise 2 — Estimate Polling Load

Suppose a getter executes SQL and each JVM is polled by 3 collectors, each every 10 seconds. Across 12 JVMs, what is the total number of getter invocations per minute, assuming no caching and independent collectors?

```text
3 collectors × 6 times/minute × 12 JVMs = 216 calls/minute
```

This result is only the assumed call count; CPU time, query execution, and overlap must be measured separately.

### Exercise 3 — Design a Snapshot with Freshness

Design `PendingOrderSnapshot` with fields:

```text
pendingOrders
lastRefreshEpochMillis
lastRefreshDurationMillis
refreshFailures
snapshotHealthy
```

Create a scheduled refresh job, then have JMX getters read only the stored fields. Simulate a database timeout and determine what indicators the dashboard must show so stale numbers are not mistaken for fresh ones.

### Exercise 4 — Verify Repeated Calls

Use Mockito spy or mock a service used by the management bean. Call `server.getAttribute(name, "PendingOrders")` twice and verify zero repository calls. If the current implementation hits the DB directly, the test must catch that query.

### Exercise 5 — Side Effects from Lazy Loading

A getter calls `entity.getItems().size()` on a JPA entity. Explain when this triggers lazy loading and SQL, when it can throw `LazyInitializationException`, and why JMX polling should not depend on a persistence context that may no longer be open.

## 23. Self-Check Questions

**1. Does a "read-only" JMX attribute guarantee the getter does not write data?**

No. Read-only only describes the attribute's setter metadata; it does not prove the implementation has no side effects.

**2. Does `@Transactional(readOnly=true)` guarantee the getter puts no load on the DB?**

No. It can still open a transaction and run SQL on every client read.

**3. Why can a getter that feels fast manually still cause production load?**

Due to multiple clients, polling frequency, replica counts, contention, and changing dependency conditions.

**4. What should be done when a value must come from the DB but the query is expensive?**

Usually refresh a snapshot on a controlled schedule, or use an appropriate metrics/counter mechanism, while the getter reads only the stored value and exposes freshness.

**5. Can a `getPendingCount()` getter reset the counter upon reading?**

It should not if clients expect the attribute to be an idempotent read. Resetting behavior should be an explicit, protected operation.

**6. Can you determine there is no I/O based solely on the `getXxx()` method name?**

No. You must inspect the implementation and dependencies/call graph.

**7. If two JMX attributes are read together via `getAttributes()`, are they guaranteed to represent the same atomic snapshot?**

There is no general guarantee of that; you must design consistency yourself if consumers require it.

## 24. Key Takeaways

- A JMX getter is **code that can be executed repeatedly by external clients** calling `getAttribute`; it is not an automatically cached field.
- `@ManagedAttribute` does not guarantee a method is free of side effects, I/O, or blocking.
- Good getters typically return an **in-memory snapshot/counter** or perform a short calculation with bounded cost.
- If heavy querying is required, move it into a background refresh with cadence, timeouts, error status, and freshness timestamps.
- Intentional write/delete/reset/refresh tasks should be represented as controlled **JMX operations**.
- Measure latency, query counts, lock contention, and multi-client polling impact; do not merely infer from code.
- Test the real JMX path via `MBeanServer` and exporter, not just method unit tests.
- Distinguish metric accuracy from read cost: snapshots can be stale, and per-JVM counters can drift if update logic is flawed.
- Never let getters accidentally expose sensitive data or call external APIs with billing/rate-limit impact.

## 25. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `ManagedAttribute`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE 21 — `MBeanServer.getAttribute`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Micrometer Reference: https://docs.micrometer.io/micrometer/reference/
- Spring Framework Reference — Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html

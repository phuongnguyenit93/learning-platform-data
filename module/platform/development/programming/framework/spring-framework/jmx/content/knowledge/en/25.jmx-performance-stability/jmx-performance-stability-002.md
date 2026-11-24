# Compute-Heavy or I/O-Accessing Attributes in Spring Framework JMX

## Objectives

In Spring Framework JMX, getters annotated with \`@ManagedAttribute\`, or included in a Standard MBean/MXBean interface, can become **JMX attributes**. A JMX client reads an attribute via \`MBeanServerConnection.getAttribute()\` or \`getAttributes()\`. From an operator's perspective, this is "reading state"; however, from the JVM's perspective, the read can execute real Java code: querying a database, making HTTP calls, reading files, acquiring locks, scanning millions of elements, or computing complex statistics.

If a getter takes several seconds and is called repeatedly by JConsole, monitoring agents, and dashboards, it can generate unexpected load and make a troubled system even less stable. Even an attribute with no business side effects still has **resource side effects** such as CPU, I/O, lock contention, heap allocation, or thread starvation.

This lesson focuses on the principle: **a JMX attribute should be a fast, bounded, predictable, low-impact read**. For heavy computation or I/O, offload to a background update mechanism, a precomputed snapshot, or an explicit conditional diagnostic operation.

After this lesson, you will be able to:

- Distinguish lightweight getters from CPU-, I/O-, lock-, and allocation-intensive getters.
- Understand how JMX polling can amplify the load from a single getter.
- Design cached snapshots, scheduled refreshes, and bounded return payloads.
- Separate heavy computation/diagnostic commands from frequently read attributes.
- Configure timeouts, backpressure, concurrency limits, and circuit breakers at the right layer.
- Evaluate consistency, staleness, and failure modes of cached attributes.
- Measure JMX read cost via latency, throughput, allocations, and dependency load.
- Write tests ensuring attributes remain stable when dependencies are slow or unavailable.

## 1. A JMX Attribute Is an Executed Method

Spring annotation example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Queue,name=Orders")
public class QueueMonitor {

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return queueRepository.countPending();
    }
}
\`\`\`

The getter looks simple, but if \`countPending()\` runs a time-consuming SQL query, every time a client queries \`QueueDepth\` it may execute a new query. The same happens with a Standard MBean:

\`\`\`java
public interface QueueMonitorMBean {
    long getQueueDepth();
}
\`\`\`

Switching from annotations to an interface does **not** make the getter automatically cached or cost-limited. JMX metadata only defines the exposed attribute; execution behavior resides in the getter code.

Call flow:

\`\`\`text
JConsole / monitoring agent / custom client
                |
                | getAttribute(ObjectName, "QueueDepth")
                v
        MBeanServer / Spring exporter
                |
                v
          getQueueDepth()
                |
                +--> database query
                +--> network request
                +--> lock contention
                +--> object allocation
                +--> computation
                |
                v
          response / error
\`\`\`

Remember: from the client's perspective, being "read-only" does not mean cheap, non-blocking, or impact-free.

## 2. Four Frequently Overlooked Cost Categories

### 2.1 CPU-Bound

A getter might iterate over hundreds of thousands of objects to compute percentiles, checksums, or statistics:

\`\`\`java
@ManagedAttribute
public double getAverageLatencyMs() {
    return allRequests.stream()
        .mapToLong(Request::latencyMillis)
        .average()
        .orElse(0.0);
}
\`\`\`

If \`allRequests\` is very large and constantly changing, every read loops over the entire set again. Even a single dashboard with a few-second interval can become a significant CPU consumer. If the collection is not thread-safe, the getter can also suffer concurrent modification errors.

### 2.2 I/O-Bound

The getter executes a SQL query, HTTP call, file system read, JNDI lookup, Redis call, or RPC. For example:

\`\`\`java
@ManagedAttribute
public String getRemoteDependencyHealth() {
    return httpClient.callHealthEndpoint();
}
\`\`\`

When the downstream service is slow, the JMX call slows down too. Multiple monitoring agents probing simultaneously can amplify a downstream incident.

### 2.3 Lock-Bound

The getter acquires a lock used by business threads:

\`\`\`java
@ManagedAttribute
public int getPendingTasks() {
    synchronized (schedulerLock) {
        return tasks.size();
    }
}
\`\`\`

If the same lock is held while scheduling or processing large jobs, monitoring hangs. Conversely, high monitoring frequency can force business threads to contend for the lock.

### 2.4 Allocation-Bound

The getter builds large lists or serializes large object graphs:

\`\`\`java
@ManagedAttribute
public String getAllSessionsAsJson() {
    return serializeAllSessions();
}
\`\`\`

This can lead to heap pressure, GC pauses, exposure of sensitive data, and remote JMX transmission overhead. Even if computation is fast, a large payload still keeps the connector busy and slows down clients.

## 3. Polling Frequency Amplifies Cost

A dashboard may have multiple agents collecting metrics concurrently. Approximate call rate:

\[
N_{\text{calls per second}} =
\sum_{i=1}^{m} \frac{1}{T_i}
\]

Where \`T_i\` is the polling interval (in seconds) of each client. If 10 clients read an attribute every 5 seconds, the total is roughly 2 reads per second. If a getter triggers a query taking 500 ms of CPU or I/O, the aggregate cost can far exceed expectations.

Example:

| Client | Instance Count | Interval | Approximate Read Rate |
|---|---:|---:|---:|
| Monitoring agent A | 4 | 10 seconds | 0.4 reads/sec |
| Dashboard B | 3 | 5 seconds | 0.6 reads/sec |
| Manual JConsole | 2 | 2 seconds | 1 read/sec |
| Total | 9 | — | 2 reads/sec |

This is only the logical call count. Clients can read multiple attributes and retry after timeouts. If each read triggers a separate query, downstream systems can receive substantial load. Some JMX clients also use \`getAttributes\` to fetch multiple attributes in one request, yet the implementation may still invoke each getter individually.

Do not benchmark a getter in isolation and conclude it is safe. You must evaluate **reader count, frequency, concurrency, and failure modes**.

## 4. Principles for Designing Lightweight Attributes

A good attribute typically has these characteristics:

1. **Bounded work:** time, quantity, and memory usage are bounded.
2. **Non-blocking or short blocking:** does not wait on prolonged I/O or network calls.
3. **No surprising side effects:** does not create jobs, modify data, or trigger heavy tasks.
4. **Predictable latency:** latency varies little even when the system is overloaded.
5. **Small payload:** returns a scalar or small summary.
6. **Stable schema:** data type and meaning do not change depending on the situation.
7. **Clear freshness:** if cached, exposes the data age.
8. **Safe on failure:** dependency failures do not cause the getter to hang indefinitely.

Suitable example:

\`\`\`java
@ManagedAttribute
public long getCompletedCount() {
    return completedCount.sum();
}
\`\`\`

\`LongAdder.sum()\` has low cost in most cases, though it is not a strictly linearizable snapshot while threads are updating. For telemetry, eventual accuracy is acceptable; for control operations requiring exact preconditions, another synchronization mechanism must be used.

## 5. Anti-Pattern: Calling the Database Directly in a Getter

Example to avoid:

\`\`\`java
@ManagedAttribute(description = "Number of pending orders")
public long getPendingOrders() {
    return jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE state = 'PENDING'",
        Long.class
    );
}
\`\`\`

If the table is large and the query is unoptimized, JMX polling can continuously scan the database. When the database is already overloaded, dashboards make the situation worse.

Improvements:

- Update a counter in the business processing flow when events occur, if accuracy and lifecycle fit.
- Run statistical queries periodically with timeouts and dedicated resources.
- Store a snapshot of the result together with its update timestamp.
- Expose an explicit refresh operation if immediate fresh numbers are needed.
- Use a dedicated metrics backend if time-series statistics are required, rather than trying to turn a JMX getter into a BI query.

No single caching strategy fits every metric. An in-memory counter can drift on startup/restart or failed processing. Units, scope, and freshness must be clearly documented.

## 6. Cached Snapshot: Fast Reads, Separate Updates

A key pattern is separating \`refresh\` from \`read\`.

\`\`\`text
Scheduled/background worker
       |
       | query dependency / compute aggregate
       v
  Immutable Snapshot
       |
       | atomic/volatile publication
       v
  JMX getter
       |
       +--> returns simple value quickly
\`\`\`

Example:

\`\`\`java
import java.time.Instant;

public record QueueSnapshot(
    long depth,
    Instant refreshedAt,
    String status
) { }
\`\`\`

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "com.example.ops:type=Queue,name=Orders")
public class QueueSnapshotMonitor {

    private final QueueRepository repository;

    private final AtomicReference<QueueSnapshot> latest =
        new AtomicReference<>(
            new QueueSnapshot(-1, Instant.EPOCH, "NOT_READY")
        );

    public QueueSnapshotMonitor(QueueRepository repository) {
        this.repository = repository;
    }

    @Scheduled(fixedDelayString = "\${monitor.queue.refresh-delay-ms:10000}")
    public void refreshSnapshot() {
        try {
            long depth = repository.countPendingWithTimeout();
            latest.set(new QueueSnapshot(
                depth, Instant.now(), "OK"));
        } catch (Exception ex) {
            QueueSnapshot previous = latest.get();
            latest.set(new QueueSnapshot(
                previous.depth(),
                previous.refreshedAt(),
                "STALE"
            ));
        }
    }

    @ManagedAttribute
    public long getQueueDepth() {
        return latest.get().depth();
    }

    @ManagedAttribute
    public String getQueueSnapshotStatus() {
        return latest.get().status();
    }

    @ManagedAttribute
    public long getQueueSnapshotEpochMillis() {
        return latest.get().refreshedAt().toEpochMilli();
    }
}
\`\`\`

Here \`QueueRepository\` and \`countPendingWithTimeout()\` are illustrative application components that must be implemented with an actual repository and appropriate timeouts. Scheduling must be enabled (for example \`@EnableScheduling\`) for \`@Scheduled\` to work in Spring. The default configuration in the example is illustrative only; the appropriate interval depends on monitoring needs.

Advantage: the JMX getter only reads an \`AtomicReference\` and does not wait on the DB. Ensure the snapshot is immutable or never modified after publication so readers never observe a partial state.

## 7. Freshness and Staleness Must Be Described

A snapshot that stops updating can return old numbers forever. If you only expose \`QueueDepth=120\`, an operator might think that is current data even though the DB lost connectivity 30 minutes ago.

Therefore, for cached JMX attributes, also expose:
- \`SnapshotTimestamp\` or \`LastSuccessfulRefreshEpochMillis\`.
- \`SnapshotAgeSeconds\` (computed quickly from the timestamp).
- \`SnapshotStatus\`: \`OK\`, \`STALE\`, \`NOT_READY\`, or \`ERROR\`.
- \`LastRefreshDurationMillis\` if helpful.
- \`LastRefreshFailureCount\` or a redacted error.
- Documented TTL or maximum tolerated age.

Example:

\`\`\`java
@ManagedAttribute
public long getSnapshotAgeSeconds() {
    Instant timestamp = latest.get().refreshedAt();

    if (timestamp.equals(Instant.EPOCH)) {
        return -1L;
    }

    return Math.max(0L,
        Duration.between(timestamp, Instant.now()).getSeconds());
}
\`\`\`

Calling \`Instant.now()\` and computing the difference inside this getter is lightweight, unlike querying a DB. However, if strict consistency across multiple attributes is required, use an intentionally published snapshot object/OpenType instead of reading individual getters at different instants.

### 7.1 Policy When Refresh Fails

There are several options:
- **Last known good:** return old data accompanied by \`STALE\` status and timestamp.
- **Sentinel:** return \`-1\` or \`UNKNOWN\` with clearly documented meaning.
- **Exception:** report an attribute read error if freshness is mandatory.
- **No update:** keep holding the snapshot while incrementing an error counter.

The choice depends on the consumer. A dashboard needing continuous numbers may prefer last known good; a control system requiring exact data may not tolerate stale snapshots. Never use \`0\` as a fallback if \`0\` also carries the real meaning of "no jobs".

## 8. Separating Heavy Operations from Attributes

A deep scan should not live inside a getter polled periodically:

\`\`\`java
@ManagedAttribute
public String getFullDiagnosticReport() {
    return performSlowFullScan();
}
\`\`\`

Replace it with an explicit contract:

\`\`\`java
@ManagedOperation(
    description = "Request bounded diagnostic snapshot")
public String requestDiagnosticSnapshot(int maxItems) {
    // Validate maxItems and create a diagnostic task.
    return diagnosticService.enqueue(maxItems);
}

@ManagedAttribute
public String getLastDiagnosticStatus() {
    return diagnosticService.cachedStatus();
}
\`\`\`

The example depends on an application-defined \`diagnosticService\`. If the operation is asynchronous, return an operation ID and provide a way to read statuses \`ACCEPTED/RUNNING/SUCCEEDED/FAILED\`. Avoid returning multi-MB reports in an attribute; you can use a link or reference ID to secure administrative storage, without putting URLs containing secrets into JMX.

Heavy operations still need permissions, rate limits, timeouts, concurrency limits, and auditing. Turning a getter into an operation does not make the computation cheaper; it only separates intentional invocation from frequent polling.

## 9. Timeouts Must Be Set at the I/O Execution Layer

A JMX client may time out or close its connection while a getter is waiting on the database. That does not necessarily stop the server-side query. Therefore **do not treat client-side timeouts as the sole layer of protection**.

Timeouts are needed in dependency calls:

\`\`\`java
public long countPendingWithTimeout() {
    // Database query with configured statement/query timeout.
    // Appropriate connection acquisition timeout and network socket timeout.
    return repository.countPending();
}
\`\`\`

Timeouts to consider:
- Connection acquisition timeout.
- Network connect timeout.
- Read/response timeout.
- Database statement/query timeout.
- Application-level deadline.
- Cancellation behavior when the deadline expires.
- Resource cleanup if an exception occurs.

Settings depend on the driver, HTTP client, JDBC pool, and provider. Do not assume a JMX Remote property automatically bounds the duration of all getters. The client may have given up waiting while the server is still holding a thread or connection.

## 10. Concurrency Limits and Stampede Prevention

When multiple JMX clients simultaneously read an expensive getter, requests can overlap. A cache with uncontrolled refreshes can turn into a **thundering herd**: multiple readers see the cache expire at once and all call the DB.

Design approach:
- A single background refresh worker is responsible for updating the snapshot.
- Getters only return the last known value and never perform blocking refreshes themselves.
- If on-demand refresh is needed, use single-flight or a mutex/semaphore.
- Set a limit on concurrent refresh tasks.
- Provide timeouts and circuit breakers when dependencies are failing.
- Add jitter across instances so all nodes do not refresh at the exact same instant.
- Apply backoff after repeated refresh failures.

Conceptual example of concurrency limiting:

\`\`\`java
private final Semaphore refreshSlots = new Semaphore(1);

public boolean tryRefresh() {
    if (!refreshSlots.tryAcquire()) {
        return false; // A refresh is already running.
    }

    try {
        refreshSnapshot();
        return true;
    } finally {
        refreshSlots.release();
    }
}
\`\`\`

This example needs to be integrated properly with the actual scheduler and error handling; if a single non-overlapping scheduled task is used, the semaphore may not be needed. Never lock the entire JMX getter while performing I/O.

## 11. Caching Can Distort Metric Meaning If Poorly Designed

A cached attribute needs to clarify:
- Is the metric scoped to JVM, instance, tenant, or cluster?
- Is it updated by time or by event?
- Can events be lost or reset on restart?
- Is the snapshot consistent across fields?
- What is the maximum acceptable staleness?
- When refresh fails, does the client know the data is stale?
- Before an event finishes processing, has the counter already incremented?

For example, \`getQueueDepth()\` based on SQL \`COUNT(*)\` and \`getCompletedCount()\` based on an in-memory counter can belong to different points in time. Do not interpret the two values as a transactionally consistent snapshot without a synchronization mechanism.

### 11.1 Volatile Publication and Immutable Data

If you use:

\`\`\`java
private volatile QueueSnapshot latestSnapshot;
\`\`\`

and \`QueueSnapshot\` is immutable, readers can obtain a published snapshot without heavy locking. If the snapshot contains a mutable map/list and the producer modifies it after publication, \`volatile\` does not make those collections thread-safe.

For complex data, create an immutable copy before publishing or use verified thread-safe structures as appropriate.

## 12. Do Not Hold Business Locks While Computing Metrics

An anti-pattern:

\`\`\`java
@ManagedAttribute
public int getBacklogSize() {
    synchronized (globalSchedulerLock) {
        return performComplexScan();
    }
}
\`\`\`

If the scan is slow, work-processing threads can be blocked. Worse, the getter could call another dependency and deadlock due to unclear lock ordering.

Better options:
- Counters updated along the processing path.
- Snapshots built outside critical sections.
- Copy only a small structure under the lock, then compute outside the lock.
- Use \`LongAdder\`, \`AtomicLong\`, \`StampedLock\`, or equivalent structures depending on required consistency.
- Do not make remote I/O calls while holding a domain service lock.

\`LongAdder\` cannot always replace \`AtomicLong\`: if compare-and-set or a strictly linearizable value is needed for control decisions, choose the appropriate primitive.

## 13. Limiting Payload Size

A JMX client can read attributes as \`String\`, arrays, composite data, or appropriate collection mappings. A getter returning full stack traces, sessions, or job lists can cause:

- Large heap allocations.
- Expensive serialization/deserialization.
- RMI network overhead.
- Out-of-memory risks on server or client.
- Exposure of sensitive information.
- Increased JConsole rendering time.

Expose small summaries instead:

\`\`\`java
@ManagedAttribute
public int getPendingJobCount() {
    return cachedPendingCount;
}

@ManagedAttribute
public String getTopFailureCategory() {
    return lastSnapshot.topFailureCategory();
}
\`\`\`

If a list is required, apply pagination/bounded diagnostics via an appropriate operation. JMX is not the default choice for streaming large data or exporting an entire database.

## 14. Sourcing Data from Metrics Instead of Re-Querying

If the application already uses Micrometer, Dropwizard Metrics, or a metrics backend, many indicators are already updated in business flows or optimized collectors. You can read pre-updated counters/gauges instead of running new queries for JMX.

Example:

\`\`\`java
private final AtomicLong activeJobs = new AtomicLong();

public void onJobStarted() {
    activeJobs.incrementAndGet();
}

public void onJobCompleted() {
    activeJobs.decrementAndGet();
}

@ManagedAttribute
public long getActiveJobs() {
    return activeJobs.get();
}
\`\`\`

Simple example; in production ensure every completion/error/cancellation path updates the counter accurately. A negative active jobs count or one that never returns to 0 may indicate an instrumentation bug.

For metrics requiring time-series, alerting, or multi-dimensional labels, a dedicated observability backend is usually more suitable than a JMX getter returning heavy aggregates.

## 15. Isolating Management Resources from Business Resources

If snapshot refresh must use I/O, avoid letting it consume unbounded threads/connections shared with main requests.

Consider:
- A dedicated executor or bounded scheduler.
- A small thread pool with a bounded queue.
- Timeouts lower than the business SLA.
- Rate limits and backoff.
- Preventing monitoring failures from crashing the application context.
- Stopping the scheduler when the context closes.
- Preventing tasks from accumulating indefinitely after each polling period.

A background metrics refresh should not be a survival dependency of the entire system, unless that data serves an explicitly designed safety requirement.

## 16. Spring AOP and @Transactional Issues in Getters

A JMX getter may call a Spring service using \`@Transactional\` or wrapped by an AOP proxy. This does not exempt it from I/O cost. A JMX invocation can open a transaction, acquire a database connection, and hold resources for the duration of the query.

If the raw target is exported instead of the proxy, advice may not apply. If the proxy is exported, JMX metadata must be recognized properly by the assembler. A separate management adapter calling the service through the Spring proxy typically preserves transaction semantics while avoiding exposing the entire service.

Do not attach \`@Transactional\` to a getter just because it queries the DB without evaluating transaction isolation, timeouts, and pool pressure. For monitoring, a dedicated service fetching bounded snapshots is usually easier to control.

## 17. Exception Handling in Getters

A JMX getter may throw exceptions due to dependency failures. Clients may receive \`MBeanException\`, \`ReflectionException\`, \`IOException\`, or exceptions specific to the execution layer.

Distinguish between:
- Dependency unavailable.
- Cached snapshot stale.
- Attribute not yet initialized.
- Permission denied.
- Server-side computation failure.
- Remote transport failure.

If all of these turn into \`0\`, dashboards can confuse "no jobs" with "unable to read metric". If every exception propagates unchecked, monitoring can spam errors and increase retry load.

A good model is retaining last known good with status and timestamp, while logging redacted errors with rate limiting and without including queries/credentials in attribute strings.

## 18. Measuring JMX Attribute Performance

Evaluate:
- P50/P95/P99 latency of the getter.
- Reads per second.
- Concurrent clients.
- CPU time and allocation per read.
- Database queries/remote calls triggered.
- Thread pool or connection pool utilization.
- Lock contention and wait times.
- Degradation in business latency as polling increases.
- Staleness and refresh failure rate.
- Serialized response size.

Example test plan:

\`\`\`text
Scenario A: No JMX polling → baseline CPU, DB QPS, business latency.
Scenario B: 1 client polling every 10 seconds.
Scenario C: 10 clients polling every 5 seconds.
Scenario D: DB slow by 2 seconds with timeout configured.
Scenario E: DB unavailable, client retrying.
Scenario F: JVM heap pressure, multiple attributes read.
\`\`\`

Compare whether polling increases DB QPS linearly. If it does, the attribute still depends directly on I/O. After switching to snapshots, expect refresh queries to be controlled by the schedule, nearly independent of the number of JMX clients.

## 19. Integration Testing for Lightweight Getters and Snapshots

A test can verify that reading the attribute does not call the repository directly:

\`\`\`java
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import java.time.Instant;

class QueueSnapshotMonitorTest {

    @Test
    void readingCachedAttributeDoesNotQueryDatabase() {
        QueueRepository repository = mock(QueueRepository.class);
        QueueSnapshotMonitor monitor =
            new QueueSnapshotMonitor(repository);

        long depth = monitor.getQueueDepth();

        assertEquals(-1L, depth);
        verifyNoInteractions(repository);
    }
}
\`\`\`

If the test wants to verify refresh:

\`\`\`java
when(repository.countPendingWithTimeout()).thenReturn(42L);

monitor.refreshSnapshot();

assertEquals(42L, monitor.getQueueDepth());
assertEquals("OK", monitor.getQueueSnapshotStatus());
verify(repository, times(1)).countPendingWithTimeout();
\`\`\`

The example needs to reside in the same test fixture with the corresponding repository interface declared. Accurate verification against a real application should include a test via \`MBeanServer.getAttribute\` to prove the export path uses the optimized getter rather than a getter on another bean/proxy.

## 20. Verifying the JMX Contract and Actual Latency

Example reading from MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Queue,name=Orders");

long start = System.nanoTime();
Object value = server.getAttribute(name, "QueueDepth");
long elapsedNanos = System.nanoTime() - start;

System.out.println("QueueDepth=" + value);
System.out.println("Elapsed ms=" + elapsedNanos / 1_000_000.0);
\`\`\`

This is the latency of a call within the same JVM through the server interface, not remote latency. Remote clients also incur network, serialization, connector scheduling, and error handling. Do not use a single measurement to set an SLO; use multiple iterations, warm-up, and appropriate load scenarios.

For Spring \`@ManagedAttribute\`, attribute names should be verified via \`MBeanInfo\` if naming/assembler customization is used.

## 21. When to Use an Operation Instead of an Attribute?

| Need | Recommended Form |
|---|---|
| Current queue depth updated in advance | Lightweight attribute |
| Frequently tracked counter | Attribute |
| Snapshot refreshed every 10 seconds | Attribute holding cached value and timestamp |
| Scanning all pending jobs | Bounded operation with permissions |
| Exporting large diagnostic report | Operation creating a job, returning ID/status |
| Testing connectivity to downstream | Explicit operation with timeout/rate limit |
| Changing log level or clearing cache | Control operation with authorization/audit |
| Computing aggregate taking several minutes | Background task and progress status |

An operation can also be called by multiple clients, so load limits are still required. The key difference is that operators/scripts clearly see an explicit action rather than an unconsciously polled getter.

## 22. Common Misconceptions

**"Getters are read-only so they don't affect the system."** False: they can consume CPU/I/O/locks and slow down business logic.

**"When the JMX client times out, the server has stopped the query."** Not necessarily. The getter may still be running and holding resources.

**"Putting @ManagedAttribute on a bean automatically creates caching."** No. The Spring exporter only exposes metadata; it does not optimize the implementation.

**"Fetching multiple attributes in one getAttributes call runs computation only once."** Not guaranteed; each attribute may invoke its own getter.

**"Every metric must be strictly up-to-the-millisecond fresh."** Depends on the contract. For monitoring, staleness of a few seconds can be acceptable if freshness is clearly represented.

**"Returning 0 from a cached metric when the DB fails is fine."** Dangerous if 0 is a valid business value; use documented statuses/sentinels.

**"Changing a getter to an operation is enough."** Heavy operations still require concurrency/rate limits, timeouts, and authorization.

**"A metric on JMX must cover the entire cluster."** Not by default; an MBean typically represents a specific JVM/instance.

## 23. Runbook for Handling an Attribute Causing System Slowdown

1. Identify the ObjectName and attribute being polled.
2. Measure polling frequency from each monitoring agent and dashboard.
3. Trace the getter to DB, HTTP, file, lock, or computation.
4. Measure p95/p99, CPU/heap allocation, and downstream load.
5. Check server-side timeouts, not just client timeouts.
6. Temporarily reduce polling frequency if the load is dangerous.
7. Convert the getter to a cached snapshot or pre-updated counter.
8. Configure TTL/freshness status and timeouts for the refresh worker.
9. Test multiple concurrent polling clients and dependency unavailability.
10. Verify impact after the change on service latency and MBeanInfo.
11. Update the runbook so operators do not treat heavy operations as polling metrics.

## 24. Practice Exercises

**Exercise 1 — SQL COUNT in a getter.** \`getPendingOrders()\` runs \`SELECT COUNT(*)\` on a multi-million-row table with 20 clients polling every 5 seconds. Estimate queries/second and design a cache refreshing every 15 seconds with a stale status.

**Exercise 2 — Lock contention.** A getter acquires a global scheduler lock and iterates over the entire queue. Analyze the impact and propose a counter/snapshot that does not hold the lock for long.

**Exercise 3 — Timeouts.** The DB loses connectivity and the getter hangs. List the timeouts needed at JDBC, pool, and application layers, and explain why a JMX client timeout is insufficient.

**Exercise 4 — Monitoring stampede.** 15 clients simultaneously read a cached attribute when the TTL expires; every thread refreshes on its own. Design single-flight background refresh and last known good.

**Exercise 5 — Large payload.** A getter returns a list of 100,000 jobs with metadata. Convert it to a count/summary and a bounded diagnostic operation with a request ID.

**Exercise 6 — Testing.** Use a mock repository to prove \`getQueueDepth()\` does not call the DB, \`refreshSnapshot()\` calls it once, and status switches to \`STALE\` when refresh fails.

## Summary

In Spring Framework JMX, attributes are often read automatically and repeatedly by multiple clients. Consequently, a getter with heavy computation or I/O access can amplify CPU, DB QPS, network, lock contention, and memory pressure at the exact moment the system needs stable observability. Design getters as **fast, bounded read paths with minimal external dependencies**, moving heavy computation to scheduled/background refreshes or controlled diagnostic operations. When using snapshots, expose update timestamps, stale status, and failure behavior. Test under realistic polling load, configure timeouts at the dependency layer, and manage concurrency so that monitoring itself does not become the cause of an outage.

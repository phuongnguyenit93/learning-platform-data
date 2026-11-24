# Designing State-Reading APIs with Acceptable Cost Using @ManagedAttribute

## 1. The Problem: A Managed Getter Is Also a Real Execution Path

In Spring JMX, \`@ManagedAttribute\` allows exposing bean state as an MBean attribute. Operators can read the attribute via JConsole, VisualVM, automation, or monitoring systems. The syntax is very simple:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.size();
}
\`\`\`

However, a call to \`getQueueDepth()\` is not merely a display line. It executes inside the application JVM and can contend for locks, access a database, make network calls, allocate memory, or affect business processing threads. A monitoring tool may invoke the getter multiple times per second, from multiple clients, and sometimes concurrently.

Therefore, the management API must ensure **predictable read cost**, **load resilience**, **appropriate consistency**, and **zero side effects**. The goal is not necessarily absolute instantaneous accuracy for every metric; the goal is metrics useful enough for operations, safely exposed at an acceptable cost.

## 2. Distinguishing Three Attribute Categories

| Category | Example | Preferred Retrieval Strategy | Characteristics |
| --- | --- | --- | --- |
| Cheap current state | \`Paused\`, \`Running\`, \`Healthy\` | \`AtomicBoolean\`, immutable snapshot | Usually O(1) |
| Aggregated metrics | \`ProcessedTotal\`, \`FailureTotal\` | Counters/metrics updated on events | Fast read, may lag slightly |
| Computed metrics | \`PendingTasks\`, \`OldestMessageAge\`, \`ActiveSessions\` | Cache or snapshot computed by background task | Avoids querying/scanning on client reads |

An attribute with a seemingly simple return type (such as \`int\`) can still be very expensive if the getter executes \`SELECT COUNT(*)\`, scans millions of elements, locks a large dataset, or calls another system.

Design should start by asking: **when is this value updated, how much does reading cost, how much latency/staleness is acceptable, and who can call it?**

## 3. Principles for Managed Getters

A getter exported via JMX should:

1. **Read fast** in most situations, ideally O(1) or a known small cost.
2. **Not mutate data or business state**.
3. **Not depend on network/database calls on the synchronous read path**, unless specifically justified.
4. **Not hold locks for long** or block business processing threads.
5. **Not return internal mutable objects**, large collections, or sensitive data.
6. **Represent errors and data staleness** if the snapshot source fails.
7. **Have clear units and meaning**, e.g., millis, bytes, pending message count.
8. **Remain stable under continuous polling** from multiple clients.

A \`@ManagedAttribute\` getter may run on the thread handling JMX requests. If it hangs, clients slow down and can tie up the application's management resources; multiple slow getters at once can cause cascading impacts.

## 4. What Not to Do: Querying the DB Directly Inside the Getter

\`\`\`java
@Component
@ManagedResource(objectName = "com.example:type=Orders,name=Primary")
public class OrderManagementBad {
    private final OrderRepository repository;

    public OrderManagementBad(OrderRepository repository) {
        this.repository = repository;
    }

    @ManagedAttribute(description = "Pending order count")
    public long getPendingOrders() {
        return repository.countPendingOrders();
    }
}
\`\`\`

When a dashboard reads the attribute every 2 seconds from 10 clients, the query can run repeatedly without throttling. If the DB is slow, connections are exhausted, or transactions are locked, simply viewing status adds load to a system already in trouble.

A better approach is updating counts in the business flow or in a bounded background refresh, then letting the getter read the snapshot.

## 5. Using Event-Updated Counters

For cumulative metrics, there is no need to scan data on every read:

\`\`\`java
import java.util.concurrent.atomic.LongAdder;

public final class JobMetrics {
    private final LongAdder completed = new LongAdder();
    private final LongAdder failed = new LongAdder();

    public void completed() {
        completed.increment();
    }

    public void failed() {
        failed.increment();
    }

    public long completedTotal() {
        return completed.sum();
    }

    public long failedTotal() {
        return failed.sum();
    }
}
\`\`\`

JMX adapter:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Metrics,name=Primary",
    description = "Job counters"
)
public class JobMetricsJmx {
    private final JobMetrics metrics;

    public JobMetricsJmx(JobMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Completed jobs since process start")
    public long getCompletedTotal() {
        return metrics.completedTotal();
    }

    @ManagedAttribute(description = "Failed jobs since process start")
    public long getFailedTotal() {
        return metrics.failedTotal();
    }
}
\`\`\`

\`LongAdder\` is typically suitable when multiple threads update a counter; \`sum()\` is not a strictly linearizable snapshot during concurrent updates. If an exact point-in-time count is required, appropriate synchronization is needed. For telemetry, accepting an approximate snapshot is usually preferable to lock contention.

Cumulative counters should clearly describe their scope: since JVM startup, since module creation, or since the last reset. Avoid calling a value \`Total\` if it is silently reset.

## 6. Immutable Snapshots for Fast Multi-Field Reads

When multiple related states are needed, publish an immutable snapshot:

\`\`\`java
import java.time.Instant;

public record WorkerSnapshot(
    boolean running,
    int queued,
    int active,
    long completed,
    Instant capturedAt
) {}
\`\`\`

A component holding the latest snapshot:

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class WorkerStateView {
    private final AtomicReference<WorkerSnapshot> current =
        new AtomicReference<>(
            new WorkerSnapshot(false, 0, 0, 0, Instant.EPOCH)
        );

    public WorkerSnapshot snapshot() {
        return current.get();
    }

    public void publish(WorkerSnapshot next) {
        current.set(next);
    }
}
\`\`\`

JMX getters simply fetch the snapshot and extract fields:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Primary"
)
public class WorkerStateJmx {
    private final WorkerStateView view;

    public WorkerStateJmx(WorkerStateView view) {
        this.view = view;
    }

    @ManagedAttribute(description = "Current active worker count")
    public int getActiveWorkers() {
        return view.snapshot().active();
    }

    @ManagedAttribute(description = "Queued tasks")
    public int getQueuedTasks() {
        return view.snapshot().queued();
    }

    @ManagedAttribute(description = "Snapshot update time")
    public String getSnapshotAt() {
        return view.snapshot().capturedAt().toString();
    }
}
\`\`\`

Each getter reads an \`AtomicReference\`, so the cost is minimal. However, when a client reads three attributes across three separate calls, it can observe values from different snapshots if an update occurs between reads. If a strictly consistent set of values is required, expose a combined snapshot via an appropriate JMX type, such as \`CompositeData\`, or place the fields in an operation returning a clearly mapped shared snapshot.

\`AtomicReference\` only guarantees atomic publication of the **snapshot reference**. It does not automatically make input data consistent if the snapshot is built from multiple independently changing counters.

## 7. Background Refresh for Expensive Metrics

For statistics that must query a database or external system, move computation to a background task with controlled cadence and timeouts.

\`\`\`java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class PendingOrdersSnapshot {
    public record Value(long count, Instant capturedAt, boolean available) {}

    private final OrderRepository repository;
    private final AtomicReference<Value> latest =
        new AtomicReference<>(new Value(0, Instant.EPOCH, false));

    public PendingOrdersSnapshot(OrderRepository repository) {
        this.repository = repository;
    }

    @Scheduled(fixedDelayString = "\${management.pending.refresh-ms:10000}")
    public void refresh() {
        try {
            long count = repository.countPendingOrders();
            latest.set(new Value(count, Instant.now(), true));
        } catch (RuntimeException ex) {
            Value previous = latest.get();
            latest.set(new Value(
                previous.count(), previous.capturedAt(), false
            ));
            // Log/rate-limit errors at an appropriate place, without printing sensitive data.
        }
    }

    public Value current() {
        return latest.get();
    }
}
\`\`\`

Scheduling must be enabled via appropriate Spring configuration (\`@EnableScheduling\` when needed). \`fixedDelay\` waits for the previous run to finish before counting the delay, but **does not set a timeout** on the DB query itself; configure timeouts at the data source/driver/repository level so it cannot hang indefinitely.

An adapter reading the snapshot:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.orders:type=Pending,name=Primary"
)
public class PendingOrdersJmx {
    private final PendingOrdersSnapshot snapshots;

    public PendingOrdersJmx(PendingOrdersSnapshot snapshots) {
        this.snapshots = snapshots;
    }

    @ManagedAttribute(description = "Cached pending order count")
    public long getPendingCount() {
        return snapshots.current().count();
    }

    @ManagedAttribute(description = "Last successful refresh in ISO-8601")
    public String getCapturedAt() {
        return snapshots.current().capturedAt().toString();
    }

    @ManagedAttribute(description = "Whether last refresh succeeded")
    public boolean isAvailable() {
        return snapshots.current().available();
    }
}
\`\`\`

Do not hide data staleness: if a refresh fails, retain the last count while exposing \`Available=false\` and the old \`CapturedAt\`. Operational tools will avoid interpreting a stale value as current state.

## 8. Designing Cost and Freshness Thresholds

There is no single latency threshold for every system. Define budgets based on requirements and measure in practice:

| Read Kind | Reference Target | Mechanism |
| --- | --- | --- |
| Status flag | Under a few ms | Atomic/volatile read |
| Counter | Under a few ms | Event-updated counter |
| Queue size | Stable cost per implementation | Native metric or snapshot |
| DB statistics | Never run synchronously in getter | Scheduled cache |
| Multi-subsystem aggregate | Timestamped snapshot | Background aggregation |
| Infrequently changing data | Cache with invalidation | Event-driven refresh or TTL |

These numbers are reference design targets, not Spring/JMX guarantees. With multiple clients, you must also calculate total read frequency:

\`\`\`text
effective reads/second
  = number of clients
    × poll frequency per client
    × attributes polled
\`\`\`

For example, 5 clients each polling 4 times/second and reading 8 attributes generate about 160 attribute calls per second. If every getter queries the DB, the system generates 160 queries/second solely for observation.

Establish a **freshness contract**: \`CapturedAt\`, \`LastSuccessfulRefreshAt\`, \`Stale\`, \`Available\`, or TTL. Attribute names should reflect whether data is cached or live.

## 9. Do Not Lock Business Logic to Serve a Getter

A getter like the following is dangerous when the lock is shared with heavy business tasks:

\`\`\`java
@ManagedAttribute
public int getActiveCount() {
    synchronized (businessLock) {
        return expensiveCollection.size();
    }
}
\`\`\`

If \`businessLock\` is held during long processing, JMX clients must wait, and contention may increase. Never use managed getters to trigger scanning operations or hold locks across network boundaries.

Replace with:

- Atomic counters maintained when tasks start/finish.
- \`LongAdder\` if update throughput is prioritized.
- A snapshot computed on a separate path.
- Bounded \`tryLock\` if stricter state guarantees are truly needed and there is a way to report unavailable.
- Built-in metrics provided by the queue/executor, after verifying implementation complexity.

Bounded lock read example:

\`\`\`java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public Integer tryReadSize(
        ReentrantLock lock, java.util.List<?> records)
        throws InterruptedException {
    if (!lock.tryLock(5, TimeUnit.MILLISECONDS)) {
        return null; // Adapter will represent unavailable appropriately.
    }
    try {
        return records.size();
    } finally {
        lock.unlock();
    }
}
\`\`\`

Even though \`tryLock\` has a timeout, this approach may still be unnecessary if a snapshot suffices. Avoid magic values like \`-1\` where clients cannot tell an error from a real metric.

## 10. Getters Must Have No Side Effects

Do not use \`@ManagedAttribute\` getters to trigger business actions:

\`\`\`java
@ManagedAttribute
public String getStatus() {
    refreshFromRemoteSystem(); // Do not do this
    return status;
}
\`\`\`

JMX tools may read attributes automatically to render UI views. If every read triggers a refresh, simply opening a monitoring tab inadvertently mutates the system.

Separate clearly:

\`\`\`java
@ManagedAttribute
public String getStatus() {
    return snapshot.status();
}

@ManagedOperation(description = "Request refresh")
public void requestRefresh() {
    commands.requestRefresh();
}
\`\`\`

State-changing operations require authentication, authorization, auditing, rate limiting, and idempotency/repeat-call semantics. Getters retain the role of observation.

## 11. Choosing JMX-Appropriate Data Types

An attribute should return types JMX clients easily understand:

- \`boolean\`, \`int\`, \`long\`, \`double\` for metrics and status flags.
- \`String\` for short statuses or standard ISO-8601 timestamps.
- Open MBean types like \`CompositeData\` when a consistent group of fields is needed.
- Avoid returning lists of thousands of entities or internal object graphs via getters.

If displaying top-N errors, cap the element count and string length. Never expose personal data, tokens, or secret configuration via JMX, especially when remote connectors are enabled.

Do not return \`Map\` or complex custom DTOs directly if assembler/MXBean mapping is unclear; metadata may be incompatible with clients or incur high serialization costs.

## 12. Testing Cost, Safety, and Semantics

A unit test can confirm the getter reads the snapshot without calling the repository:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.time.Instant;

class WorkerStateJmxTest {
    @Test
    void getterReadsPublishedSnapshot() {
        WorkerStateView view = new WorkerStateView();
        view.publish(new WorkerSnapshot(
            true, 12, 3, 99, Instant.parse("2026-01-01T00:00:00Z")
        ));

        WorkerStateJmx adapter = new WorkerStateJmx(view);

        assertEquals(3, adapter.getActiveWorkers());
        assertEquals(12, adapter.getQueuedTasks());
        assertEquals("2026-01-01T00:00:00Z", adapter.getSnapshotAt());
    }
}
\`\`\`

An integration test can register the MBean on \`MBeanServer\` and read via \`getAttribute\`, checking attribute names, data types, and access permissions. For performance requirements, measure percentile latency and throughput in a representative environment; a single-run \`assert elapsed < 5ms\` test can be flaky on CI due to JIT/GC/scheduling.

Cases worth testing:

1. Multiple clients reading concurrently while state changes.
2. Slow or failing background refresh.
3. Initial snapshot before data is populated.
4. Large values, overflow, and JMX type conversions.
5. High-frequency getter invocation.
6. Application shutdown while clients are reading.
7. Unauthorized callers when the JMX channel enforces access control.

## 13. Observing the Observation System Itself

A management API can cause its own impact if read cost is unmeasured. When building production dashboards, measure:

- Attribute read counts, if needed and instrumentable.
- Latency of the snapshot-fetching/metric-generation path.
- Time elapsed since the last successful refresh.
- Refresh failure rate and timeout count.
- Returned payload size or serialization cost.
- Lock contention or threads blocked during JMX polling.

Avoid creating an observation loop: if \`getMetricsReadLatency()\` recomputes latency using a heavy operation, measuring itself adds load. Return only pre-recorded values from instrumentation.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Getter calls \`repository.count()\` | Generates DB load scaling with client count and poll frequency | Background cache/snapshot |
| Getter locks entire subsystem | Increases contention, can block | Atomic metric/snapshot |
| Getter reads full collection then filters | O(N), heavy memory allocations | Maintain separate aggregate and top-N |
| Getter calls remote API | Latency and network dependency failures | Background refresh with timeout |
| Getter triggers synchronization automatically | Observation causes side effects | Use explicit \`@ManagedOperation\` |
| Snapshot timestamp not exposed | Clients mistake stale data for current | \`CapturedAt\`, \`Available\`, \`Stale\` |
| Returning large custom objects | Slow mapping/serialization or errors | Scalars or bounded Open MBeans |
| Measuring performance with a single call | Easily misses concurrent load and tail latency | Load test with representative workload |

## 15. Workflow for Designing a New @ManagedAttribute

Before adding an attribute:

1. **Name and unit:** \`ActiveJobs\` (count), \`OldestJobAgeMillis\` (ms), \`LastSuccessAt\` (ISO-8601).
2. **Identify data source:** atomic state, counter, queue, repository, or remote service.
3. **Define cost budget:** complexity, expected max latency, polling frequency.
4. **Define freshness:** instantaneous value, eventual consistency, or cached snapshot.
5. **Choose update mechanism:** write-time metric, event-driven update, scheduled refresh.
6. **Design error states:** unavailable, stale, timestamp; avoid faking 0 when data is absent.
7. **Bound returned data:** field count, element count, length, and sensitive info.
8. **Test:** correctness, concurrency, failures, and cost under polling.
9. **Monitor in production:** observe latency and snapshot quality under heavy system load.

If an attribute is too expensive yet operators still need on-demand updates, separate it into a controlled \`requestSnapshotRefresh()\` operation, while the getter reads only the latest result. Never force clients to wait tens of seconds on a getter.

## 16. Key Takeaways

\`@ManagedAttribute\` turns a getter into a management API that can be invoked frequently and concurrently. **A good getter is a fast, predictable read with no side effects that never worsens system health during an incident.** Use event-updated counters for cumulative metrics, immutable snapshots for related state, and background refreshes for expensive statistics. Expose snapshot freshness and error states so operators understand the boundaries of the values they receive.

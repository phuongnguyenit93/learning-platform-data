# State Snapshots Instead of Reading Multiple Separate Attributes

## Objectives

In Spring Framework JMX, an MBean may expose multiple attributes such as `Queued`, `Processing`, `Completed`, `Failed`, and `Paused`. This lesson explains why reading individual attributes separately easily produces a point-in-time-inconsistent picture, how to design a coherent snapshot, performance trade-offs, and verification methods.

After this lesson, you will be able to:
- Distinguish per-getter data from a logical snapshot.
- Explain why `getAttributes()` does not inherently guarantee values are read atomically.
- Design immutable snapshots, timestamps, and generations.
- Distinguish atomic publication from atomic capture.
- Expose snapshots via `CompositeData`, MXBean, or a management adapter.
- Verify consistency, freshness, and read cost over JMX.

## 1. Why Can Reading Multiple Attributes Produce Wrong Results?

Suppose at T0 a queue has `Queued=10` and `Processing=2`, meaning total active jobs is 12. A JMX client reads `Queued=10`. Then a worker picks up a job: the queue shifts to `Queued=9`, `Processing=3`. The client next reads `Processing=3`. The combined result `10+3=13` is not a state that ever existed simultaneously.

Each value read individually was valid at its own instant; the error lies in combining different points in time into a single picture. This happens when:
- Workloads update counters continuously.
- Monitoring calls multiple getters sequentially.
- AOP interceptors, locks, or I/O give getters different latencies.
- Remote clients require multiple network round trips.
- Background refreshes update individual fields independently.

Even if a client calls `MBeanServerConnection.getAttributes(name, attributes)` to fetch multiple values in one command, the JMX API provides no general guarantee that all getters execute within a single transaction or under the same lock. `getAttributes` batches the call, rather than automatically turning an unsynchronized implementation into an atomic snapshot.

## 2. Types of Consistency to Distinguish

| Concept | Meaning | Limitation |
|---|---|---|
| Separate reads | Each getter returns a value at invocation time | Can skew in time |
| Batch attributes | One API fetches multiple attribute names | Not inherently atomic |
| Immutable snapshot | One object holding multiple fixed fields | Capture logic may still be wrong |
| Atomic publication | Reader sees a complete published snapshot | Does not guarantee inputs were captured together |
| Atomic capture | Fields satisfy invariants at a logical point | Requires writer/capture synchronization |
| Fresh snapshot | Data captured close to read time | Freshness does not guarantee consistency |
| Consistent snapshot | State tied to an explicit generation/invariant | May be stale |

Key point: using `AtomicReference<Snapshot>` guarantees publication of the reference, yet if the snapshot is constructed by reading five separate counters while writers update them, the snapshot's contents can still mix multiple points in time. To preserve invariants, you must control how updates or captures occur.

## 3. Designing an Immutable Data Snapshot

A Java record can represent a snapshot:

```java
public record QueueSnapshot(
        long queued,
        long processing,
        long completed,
        long failed,
        boolean paused,
        long capturedAtEpochMillis,
        long generation) {}
```

Primitive fields cannot change after constructing the record. The `capturedAtEpochMillis` field represents capture time; `generation` is an incrementing number for each new snapshot version. If any field holds a mutable collection or object, a record does not make those nested objects immutable; defensive copies are required.

Use `AtomicReference` for publication:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class SnapshotStore {
    private final AtomicReference<QueueSnapshot> latest =
            new AtomicReference<>();

    public QueueSnapshot current() {
        return latest.get();
    }

    public void publish(QueueSnapshot next) {
        latest.set(next);
    }
}
```

This mechanism lets readers obtain one object without locking just to read the reference. However, `current()` can return null before the first publish. Management code must represent `NOT_INITIALIZED` explicitly instead of returning 0 as if it were real data.

## 4. Consistent Capture via Shared State

If the critical invariant is `queued+processing=activeJobs`, update the fields together. For example, CAS on an immutable state:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class QueueStateMachine {
    public record State(long queued, long processing, long generation) {}

    private final AtomicReference<State> state =
            new AtomicReference<>(new State(10, 2, 0));

    public void startOneJob() {
        state.updateAndGet(old -> {
            if (old.queued() == 0) return old;
            return new State(
                    old.queued() - 1,
                    old.processing() + 1,
                    old.generation() + 1);
        });
    }

    public State capture() {
        return state.get();
    }
}
```

Because `queued` and `processing` transition in a single CAS, readers observe a `State` from the same generation. The function passed to `updateAndGet` must be side-effect free because it may be retried under CAS contention. If all writers do not follow this state machine, the invariant can still be broken.

Another option is `synchronized` with the same lock for both writers and capture:

```java
public final class LockedQueueState {
    private long queued = 10;
    private long processing = 2;
    private long generation;

    public synchronized void startOneJob() {
        if (queued == 0) return;
        queued--;
        processing++;
        generation++;
    }

    public synchronized QueueSnapshot capture() {
        return new QueueSnapshot(
                queued, processing, 0, 0, false,
                System.currentTimeMillis(), generation);
    }
}
```

Keep critical sections short. Never call SQL, HTTP, or wait on I/O while holding the lock, because monitoring can slow down workers. Both CAS and synchronized have trade-offs: CAS incurs contention and allocations; locks incur wait time and synchronization cost. Measure under your workload.

## 5. Why Can Multiple Getters Reading the Same Store Still Skew Generations?

Suppose a management bean:

```java
@ManagedAttribute
public long getQueued() {
    return snapshotStore.current().queued();
}

@ManagedAttribute
public long getProcessing() {
    return snapshotStore.current().processing();
}
```

The first call may read generation 20; background refresh publishes generation 21; the second call reads generation 21. Both getters read validly published snapshots, yet the client still mixes two generations.

To fix this, expose **a single `Snapshot` attribute** containing all fields and have clients read it once. This ensures every field in the response belongs to the same object/generation. If business logic requires strong consistency, you still must capture the snapshot properly as shown earlier.

## 6. Exposing Snapshots via CompositeData

`CompositeData` and `CompositeType` belong to the JMX Open MBean API, allowing a structure with an explicit schema to be exposed. A Standard MBean can define:

```java
import javax.management.openmbean.CompositeData;

public interface QueueMonitorMBean {
    CompositeData getSnapshot();
}
```

Helper creating `CompositeData`:

```java
import javax.management.openmbean.*;

public final class QueueSnapshotOpenData {
    private static final String[] NAMES = {
            "queued", "processing", "completed", "failed",
            "paused", "capturedAtEpochMillis", "generation"
    };
    private static final OpenType<?>[] TYPES = {
            SimpleType.LONG, SimpleType.LONG,
            SimpleType.LONG, SimpleType.LONG,
            SimpleType.BOOLEAN, SimpleType.LONG, SimpleType.LONG
    };
    private static final CompositeType TYPE;

    static {
        try {
            TYPE = new CompositeType(
                    "QueueSnapshot",
                    "Queue diagnostic state",
                    NAMES,
                    new String[]{
                        "Queued jobs", "Processing jobs",
                        "Completed jobs", "Failed jobs",
                        "Paused", "Capture timestamp", "Generation"
                    },
                    TYPES);
        } catch (OpenDataException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private QueueSnapshotOpenData() {}

    public static CompositeData convert(QueueSnapshot snapshot) {
        try {
            return new CompositeDataSupport(
                    TYPE, NAMES, new Object[]{
                        snapshot.queued(),
                        snapshot.processing(),
                        snapshot.completed(),
                        snapshot.failed(),
                        snapshot.paused(),
                        snapshot.capturedAtEpochMillis(),
                        snapshot.generation()
                    });
        } catch (OpenDataException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
```

MBean implementation:

```java
public final class QueueMonitor implements QueueMonitorMBean {
    private final SnapshotStore store;

    public QueueMonitor(SnapshotStore store) {
        this.store = store;
    }

    @Override
    public javax.management.openmbean.CompositeData getSnapshot() {
        QueueSnapshot value = store.current();
        if (value == null) {
            throw new IllegalStateException("No snapshot available");
        }
        return QueueSnapshotOpenData.convert(value);
    }
}
```

Benefit: `value` is read exactly once and all fields come from that object. JConsole or a JMX client can query `CompositeData` instead of performing multiple scalar attribute reads. Schema field names/types must remain stable because changing the schema can break older clients.

## 7. Reading Snapshots from MBeanServer

Once the MBean is registered under a valid ObjectName:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.shop.orders:type=QueueMonitor,name=outbox");

CompositeData snapshot =
        (CompositeData) server.getAttribute(name, "Snapshot");

long queued = (Long) snapshot.get("queued");
long processing = (Long) snapshot.get("processing");
long generation = (Long) snapshot.get("generation");

System.out.printf(
        "g=%d queued=%d processing=%d%n",
        generation, queued, processing);
```

The example assumes the MBean is registered in the platform MBeanServer itself. If the Spring exporter uses another MBeanServer, retrieve that server. `CompositeData.get` uses the exact field names defined in the schema.

## 8. Spring @ManagedResource and Management Adapters

In Spring Framework, you can create a management adapter instead of exporting the business service directly:

```java
import javax.management.openmbean.CompositeData;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Snapshot,name=outbox",
    description = "Coherent queue state")
public class QueueSnapshotManagement {
    private final SnapshotStore store;

    public QueueSnapshotManagement(SnapshotStore store) {
        this.store = store;
    }

    @ManagedAttribute
    public CompositeData getSnapshot() {
        QueueSnapshot value = store.current();
        if (value == null) {
            throw new IllegalStateException("Not initialized");
        }
        return QueueSnapshotOpenData.convert(value);
    }
}
```

An `MBeanExporter` or `AnnotationMBeanExporter` with an assembler that understands `@ManagedResource`/`@ManagedAttribute` must actually export the bean. Adding annotations alone does not create an MBean. Avoid having multiple exporters register the same ObjectName. If the adapter is wrapped by a Spring AOP proxy, inspect metadata/invocation via MBeanInfo.

This adapter only reads the snapshot. Business threads or a snapshot job maintain the data on their own lifecycle, avoiding turning JMX reads into expensive queries.

## 9. MXBean and Data Mapping Capabilities

MXBean has a mechanism for converting supported Java data types into OpenTypes. An interface can declare snapshot types valid under MXBean mapping. However, you cannot assume every Java class, record, collection, or generic DTO automatically maps to CompositeData across all JDKs.

If interoperability across JMX clients is needed, return explicit `CompositeData` or use verified MXBean type mappings. If only scalar metrics are needed, avoid overcomplicating the contract with large objects.

## 10. Scheduled Snapshot Refresh

A snapshot can be updated by a background task:

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class QueueSnapshotRefresh {
    private final QueueStateProvider provider;
    private final AtomicReference<QueueSnapshot> current =
            new AtomicReference<>();

    public QueueSnapshotRefresh(QueueStateProvider provider) {
        this.provider = provider;
    }

    @Scheduled(fixedDelayString =
            "\${monitoring.snapshot-refresh-ms:15000}")
    public void refresh() {
        QueueSnapshot fresh = provider.captureSnapshot();
        current.set(fresh);
    }

    public QueueSnapshot current() {
        return current.get();
    }
}
```

`QueueStateProvider` here is an application-defined abstraction. In Spring, scheduling must be enabled via appropriate configuration, such as `@EnableScheduling`. If `captureSnapshot()` must read multiple counters with an invariant, the provider must implement an appropriate atomic capture mechanism rather than reading them separately and assembling them.

With `fixedDelay`, the next run is scheduled after the previous run finishes, per scheduler configuration. Do not let the JMX getter call `refresh()` itself, because frequent polling can trigger repeated queries/locks.

## 11. Freshness and Failure Handling

A consistent snapshot can still be stale. Consider recording:
- `capturedAtEpochMillis`: capture timestamp.
- `generation`: published generation.
- `lastRefreshDurationMillis`: refresh duration.
- `refreshFailures`: number of failed refreshes.
- `healthy` or `stale`: data quality status.
- `initialized`: whether a valid snapshot exists yet.

Example operational policy:
- Refresh interval 15 seconds.
- Data older than 45 seconds is marked stale.
- Data older than 120 seconds is not used for automated decisions.

Thresholds are examples, not Spring defaults. When refresh fails, you can retain the last valid snapshot and expose errors/freshness clearly. Do not silently display old numbers as fresh data. When no snapshot exists yet, do not use `0` if it could be mistaken for a real measurement.

## 12. Multi-Source Snapshots Are Not Always Atomic

An aggregated dashboard:
- In-RAM queue depth.
- Database pool usage.
- JVM heap used.
- External HTTP service health.
- Error counter.

Each source has its own clock and update semantics. Even if you place everything in one `record` and publish via `AtomicReference`, you only guarantee **atomic publication**, not a **distributed consistent snapshot**. If cross-system consistency is mandatory, use a transaction or domain-specific protocol. If only a diagnostic view is needed, name it `best-effort snapshot` and include per-source timestamps.

## 13. Generation and Client Correlation

`generation` helps clients distinguish two captures:
- If two reads have the same generation, the store has not published a new version yet.
- If the generation stays unchanged longer than the freshness target, alert on staleness.
- If the application restarts, generation may reset; it does not sync across replicas automatically.
- When comparing multiple JVMs, separate instance identity/boot ID is required.

Do not place an ever-increasing generation as a Prometheus label; doing so creates unnecessary time series. A generation can be exposed as a value or metadata inside a JMX compound attribute.

## 14. When Is a Snapshot Better Than Scalar Attributes?

A snapshot fits when:
1. Multiple fields share related invariants.
2. An operator needs a picture from the same generation.
3. Clients need to read state in a single JMX round trip.
4. Data is small and the schema is stable.
5. Timestamp/version is needed to interpret state.
6. Individual getters would duplicate expensive aggregate computation.

Scalar attributes or metrics fit better when:
1. Each measurement is independent.
2. Time series/rates/alerts are needed.
3. The monitoring stack collects data by labels.
4. Cross-field atomic consistency is not required.
5. A compound snapshot is too large or costly to serialize.

You can maintain both: JMX snapshots for diagnostics and metrics from the same data source for dashboards. Document semantics clearly so clients reading at different times are not misled.

## 15. Performance Cost

Snapshots can reduce round trips and repeated computation, but do not automatically guarantee faster execution. Costs may include:
- Allocations creating DTOs or CompositeData.
- CAS contention when writers update continuously.
- Lock contention during capture.
- Serialization/transport of compound payloads.
- Data scan duration if the snapshot summarizes large collections.
- Background refreshes requiring SQL/HTTP.

Avoid exporting full JPA entities, order lists, or unbounded object graphs over JMX. Beyond latency, this risks exposing customer data, lazy loading errors, and classloader issues.

Measure p95/p99 latency, allocations, lock wait, payload size, and throughput impact before optimizing.

## 16. Combining Notifications with Snapshots

An MBean can emit a JMX notification when a queue crosses a threshold, and the listener then reads the snapshot to inspect state. Notifications are not by default a durable queue with replay. Therefore, polling/freshness checks are still needed when clients reconnect or miss events.

Example flow:
```text
queue.threshold.exceeded notification
    -> listener receives event
    -> connection.getAttribute(name, "Snapshot")
    -> process coherent state, generation and timestamp
```

Do not assume the notification and snapshot capture happen atomically; a new generation may already exist between emitting the event and the client reading. If exact correlation is needed, attach the generation to notification userData or appropriate message metadata.

## 17. Verifying Correctness with Concurrency Tests

Set up a test with a state machine enforcing `queued + processing = 12`. One thread updates state using CAS while another continuously reads snapshots.

Pseudocode:
```java
for (int i = 0; i < 100_000; i++) {
    QueueStateMachine.State snapshot = stateMachine.capture();
    if (snapshot.queued() + snapshot.processing() != 12) {
        throw new AssertionError("Torn snapshot");
    }
}
```

Test the real JMX path too: register the MBean in an isolated `MBeanServer` using `MBeanServerFactory.createMBeanServer()`, read `Snapshot` via `getAttribute`, verify schema/type/invariants, and unregister in `finally`. One passing concurrency test does not prove absolute absence of races; combine unit tests for state transitions with Java Memory Model reasoning.

## 18. Design Checklist

- [ ] Which fields must belong to the same generation?
- [ ] Which invariants must be preserved?
- [ ] Do writers update state through a unified mechanism?
- [ ] Is capture atomic or coherent per the contract?
- [ ] Is the snapshot immutable with defensive copies for mutable fields?
- [ ] Does publication have clear memory visibility?
- [ ] Does the JMX getter return the whole object instead of separate reads?
- [ ] Are timestamp, generation, initialized, and stale semantics clear?
- [ ] Are refresh failures reported?
- [ ] Does the getter avoid SQL/HTTP and long locks?
- [ ] Is payload size bounded?
- [ ] Are ObjectName and CompositeData schema stable?
- [ ] Are there integration tests for MBeanInfo and concurrent updates?
- [ ] Are secrets and personal data excluded?
- [ ] Do multiple JVMs have distinct identities and avoid claiming to be a cluster snapshot?

## 19. Common Mistakes

| Symptom | Cause | Solution |
|---|---|---|
| Sum queued + processing is skewed | Reading two attributes at different times | Single compound snapshot |
| `getAttributes()` still inconsistent | JMX batching is not atomic | Coherent capture in implementation |
| Immutable snapshot still breaks invariant | Fields read from independent counters | Appropriate CAS/lock/transaction |
| Slow JMX getter | Building snapshot inside getter with I/O | Background refresh |
| Snapshot too stale | Refresh failing or cadence too low | Timestamp, health, and stale indicator |
| `CompositeData` cast error | Contract mismatch | Inspect MBeanInfo and return type |
| Clients break after renaming fields | Breaking schema change | Versioning and migration |
| Dashboard loses historical detail | Snapshot is not a time-series store | Collect metrics separately |
| Multiple replicas share generation numbers | Generation is local per JVM | Instance identity/boot metadata |
| Large snapshot triggers GC | Returning entity graphs/collections | Aggregate, limit fields |

## 20. Exercises

**Exercise 1.** For an event moving one job from Queued to Processing, describe an interleaving where a client reads a total of 13 instead of 12.

**Exercise 2.** Write an immutable state and `AtomicReference.updateAndGet` to transition two counters simultaneously. Ensure the update function has no side effects.

**Exercise 3.** Create a `CompositeData` containing `queued`, `processing`, `generation`, and `capturedAtEpochMillis`; read it with a JMX client and verify the fields.

**Exercise 4.** Simulate 3 refresh failures. Explain how to retain the last-known-good snapshot and expose age/failure metadata without misleading operators.

**Exercise 5.** Compare a dashboard requirement to chart 24-hour queue depth with an operator requirement to view all counters from the same generation; choose scalar metrics or compound snapshots for each case.

**Exercise 6.** Create an integration test using `MBeanServerFactory.createMBeanServer()`, register the MBean, read the snapshot, assert invariants, and clean up the registration.

## 21. Self-Check

**Does MBeanServer.getAttributes() guarantee all getters execute at the same instant?** No. It is a batch access API without a general atomic snapshot guarantee.

**What does AtomicReference guarantee?** A reference is published/read with proper visibility; it does not automatically ensure atomic capture across multiple sources.

**Can a snapshot be stale yet consistent?** Yes. Consistency and freshness are two separate properties.

**Why can multiple getters reading the same SnapshotStore still skew?** Because the store can publish a new generation between two reads.

**Why use CompositeData?** To expose a compound attribute with an explicit JMX schema that clients can retrieve in a single read.

**Does a snapshot replace time-series metrics?** No. A snapshot is a state view; time series are for trends, rates, and alerts.

**Is AtomicReference alone enough for a consistent snapshot across multiple services?** No. A protocol or domain-specific semantics is needed if distributed consistency is required.

## 22. Key Takeaways

- Separate JMX attributes may be individually valid yet wrong when combined from different points in time.
- `getAttributes()` does not by default provide an atomic snapshot.
- Design a **compound snapshot** when cross-field invariants are required.
- Distinguish **atomic capture** from **atomic publication**.
- Use immutable state, appropriate CAS/locks, timestamps, and generations.
- Separate background refresh from JMX getters to avoid repeated cost.
- Handle stale, not initialized, and failures explicitly.
- Do not send large object graphs or sensitive data over JMX.
- Verify with MBeanInfo, getAttribute, unit/integration/concurrency tests.
- Scalar metrics and snapshots serve complementary purposes.

## 23. References

- Java SE 21 — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — CompositeData: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — CompositeDataSupport: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeDataSupport.html
- Java SE 21 — AtomicReference: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html

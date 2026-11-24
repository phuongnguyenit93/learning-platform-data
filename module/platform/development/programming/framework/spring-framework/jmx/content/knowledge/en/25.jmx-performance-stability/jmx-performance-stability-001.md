# Cost of Reading Attributes and Invoking Operations via JMX

## Learning Objectives

After this lesson, you will be able to:

- Explain the execution flow when a JMX client **reads an attribute** or **invokes an operation** on an MBean.
- Distinguish the costs of **JMX dispatch, reflection/metadata, serialization, network round trip**, and **business logic inside a getter/operation**.
- Understand why a seemingly simple getter can cause blocking, allocation, lock contention, or expensive data queries.
- Compare local JMX within the same JVM with remote JMX over a connector, especially RMI.
- Design MBeans with fast, side-effect-free getters and operations with bounded time, load, and concurrency.
- Avoid excessive polling, uncontrolled reads of many attributes, and cascading load effects on the application.
- Write Java/Spring examples and measure them in practice using benchmarks or by observing latency, throughput, and impact on the main workload.
- Recognize scenarios where Micrometer/metrics should be used instead of repeatedly invoking high-cost JMX operations.

## 1. JMX Is a Management Channel, Not a Free Data Path

Java Management Extensions (JMX) provides a mechanism to access managed resources through an MBeanServer. Spring Framework can export Spring beans as MBeans using MBeanExporter and metadata annotations such as @ManagedResource, @ManagedAttribute, and @ManagedOperation.

Model:

\`\`\`text
Monitoring / Admin client
       |
       | getAttribute(...) / invoke(...)
       v
MBeanServer or MBeanServerConnection
       |
       | look up ObjectName, MBean metadata, dispatch
       v
MBean adapter / target
       |
       | run actual getter or operation
       v
Application state / database / queue / cache
\`\`\`

Calling JMX **is not like reading a pre-built snapshot** in every case. Many MBeans compute data on demand when queried. A getter can execute Java code, hold a lock, iterate over a collection, query a database, or make a network call.

Key takeaway:

> The cost of a JMX call is usually the sum of the JMX infrastructure cost plus the cost of the exposed method itself. In many situations, the cost of the getter/operation is much larger than the JMX dispatch overhead.

## 2. How Do Attributes and Operations Differ?

An **Attribute** is a management property. With Spring:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.depth();
}
\`\`\`

Client call:

\`\`\`java
Object value = server.getAttribute(
    objectName,
    "QueueDepth"
);
\`\`\`

An **Operation** is a management action:

\`\`\`java
@ManagedOperation
public void refreshIndexes() {
    indexService.refresh();
}
\`\`\`

Client call:

\`\`\`java
server.invoke(
    objectName,
    "refreshIndexes",
    new Object[0],
    new String[0]
);
\`\`\`

The fundamental difference lies in the contract and usage expectations, **not that JMX automatically guarantees getters are always cheap and operations are always expensive**. A getter can be very costly if the implementation is poorly designed; an operation can be very fast if it only updates a flag.

An attribute getter should be observational, return quickly, and avoid side effects. An operation should clearly state its cost and impact so callers do not inadvertently perform heavy actions.

## 3. Sources of Cost in a JMX Call

It can be roughly broken down as:

\`\`\`text
Total time of a call
  = client request preparation time
  + connector/transport overhead
  + MBean lookup and dispatch
  + processing inside getter/operation
  + result conversion/serialization
  + return transport
  + client-side result processing
\`\`\`

This is a conceptual model, not an exact measurement formula for every implementation.

### 3.1. MBean Lookup and Dispatch Cost

MBeanServer identifies the registration via ObjectName, inspects metadata, and forwards the call to the managed resource or adapter. This may involve lookup, name and signature checks, reflection/proxy invocation, or interceptors.

Normally this cost is small for a simple getter, but it is not zero. Management calls repeated thousands of times per second should not be treated like a Java field access.

### 3.2. Method Execution Cost

A getter may:

- Read an AtomicLong or a precomputed snapshot.
- Hold a synchronized lock to read a collection.
- Iterate over millions of elements.
- Run a SQL COUNT on a large table.
- Call another service over HTTP.
- Aggregate multiple metrics at the moment it is queried.

These cases differ completely in CPU, I/O, latency, and the risk of slowing down the main workload.

### 3.3. Returned Data Cost

Returning an integer is different from returning a list of hundreds of thousands of elements. With remote JMX, the result also has to be marshaled/serialized over the connector and can create memory, GC, and network pressure.

### 3.4. Client-Side Cost

The JMX client also needs to process metadata, decode data, update dashboards, or store results. When polling very many MBeans and many JVMs, the aggregate load can be large even if each individual request is inexpensive.

## 4. Local JMX and Remote JMX

It is important to distinguish the access patterns:

| Mode | Call Path | Typical Costs |
|---|---|---|
| Direct method call | Java object → method | Mainly Java logic |
| MBeanServer in the same JVM | Java → MBeanServer → MBean | Adds registry/dispatch/adapter |
| Local monitoring tool via attach/connector | Tool → local transport → JVM | Adds transport and management mechanism |
| Remote JMX | Client → network connector → JVM → MBean | Adds network, authentication, TLS, serialization, round-trip time |

Within the same JVM:

\`\`\`java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

long count = (Long) server.getAttribute(
    name,
    "ProcessedJobs"
);
\`\`\`

This is still a call through the JMX API, but there is no remote network round trip like when using MBeanServerConnection over RMI.

Remote JMX:

\`\`\`java
MBeanServerConnection connection =
        connector.getMBeanServerConnection();

Object value = connection.getAttribute(name, "ProcessedJobs");
\`\`\`

Depending on the connector, JDK version, security, network, and data types, the latency difference can be significant. Do not state a ratio like "remote is X times slower" without measuring in the specific environment.

## 5. Examples of Cheap and Expensive Getters

### Cheap Getter: Reading an Already-Maintained Value

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;

public class QueueMetrics {
    private final AtomicLong processedJobs = new AtomicLong();

    public void recordProcessedJob() {
        processedJobs.incrementAndGet();
    }

    public long processedJobs() {
        return processedJobs.get();
    }
}
\`\`\`

MBean facade:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueMetricsMBeanView {

    private final QueueMetrics metrics;

    public QueueMetricsMBeanView(QueueMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Processed jobs since startup")
    public long getProcessedJobs() {
        return metrics.processedJobs();
    }
}
\`\`\`

The getter mainly reads an AtomicLong, which is relatively inexpensive.

### Expensive Getter: Scanning All Data on Every Poll

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return jobs.stream()
        .filter(job -> job.isPending())
        .count();
}
\`\`\`

If jobs is very large, every attribute read has to iterate over the data. When multiple monitoring agents poll concurrently, the cost can grow with the number of calls and the collection size.

An approach that may be more suitable:

- Maintain a counter when a job changes state.
- Compute a snapshot periodically outside the JMX call path.
- Use caching with a freshness bound if the data allows.
- Avoid holding locks for a long time while computing.

## 6. Computation Inside a Getter Needs Bounds

An ideal management getter should be:

1. **Fast:** do not run heavy data queries on the request path.
2. **Side-effect free:** do not clear caches, change configuration, or trigger jobs.
3. **Clear in semantics:** type, unit, freshness, and meaning of the value.
4. **Concurrency-safe:** use Atomic*, volatile, immutable snapshots, or appropriate synchronization.
5. **Predictable in error behavior:** do not hang indefinitely.
6. **Bounded in data volume:** limit cardinality and result size.

Example of reading a snapshot:

\`\`\`java
public record QueueSnapshot(
        long pendingJobs,
        long processedJobs,
        long generatedAtMillis) {
}
\`\`\`

Service storing the updated snapshot:

\`\`\`java
private volatile QueueSnapshot latestSnapshot =
        new QueueSnapshot(0, 0, 0);

public QueueSnapshot latestSnapshot() {
    return latestSnapshot;
}
\`\`\`

Pay attention to JMX serialization and type compatibility with remote clients. You do not necessarily want to export a custom record directly if clients in another JVM do not have that class. You can expose separate primitive attributes or appropriate Open Types.

## 7. Preventing Getters from Holding Locks Too Long

Less-than-ideal example:

\`\`\`java
@ManagedAttribute
public synchronized String getFullReport() {
    // Iterate over large data and build a long string
    return calculateLargeReport();
}
\`\`\`

If the same monitor lock is used by production threads, a monitoring client's getter can block business processing.

Separate computation from the critical section:

\`\`\`java
private volatile String cachedReport = "not available";

@ManagedAttribute
public String getReportSummary() {
    return cachedReport;
}
\`\`\`

A separate task updates cachedReport on a schedule or event. Make sure the snapshot is fresh enough for operational needs and does not expose sensitive data.

Not every synchronized getter is wrong; a very short critical section can be appropriate. The issue is lock duration, contention level, and impact on business threads.

## 8. MBean Operations Can Cause Heavy Load

Operations often have side effects:

\`\`\`java
@ManagedOperation
public void rebuildIndex() {
    indexService.rebuildAll();
}
\`\`\`

If rebuildAll takes several minutes, invoking it directly via JMX can tie up the processing thread and force the client to wait a long time, causing timeouts or dropped connections.

Better design for long-running tasks:

1. The operation only **submits a request** to start the work.
2. Return a job ID or initialization status.
3. The executor has an explicit concurrency limit.
4. Attributes/metrics report progress, results, and errors.
5. Provide timeouts, cancellation policies, or backpressure where appropriate.
6. Prevent submitting a flood of concurrent rebuilds.

Simple example:

\`\`\`java
@ManagedOperation(description = "Start one index rebuild if idle")
public String requestRebuild() {
    if (!running.compareAndSet(false, true)) {
        return "ALREADY_RUNNING";
    }

    try {
        executor.execute(() -> {
            try {
                indexService.rebuildAll();
            } finally {
                running.set(false);
            }
        });
        return "ACCEPTED";
    } catch (RuntimeException ex) {
        running.set(false);
        throw ex;
    }
}
\`\`\`

Assume running is an AtomicBoolean and executor/indexService are already injected. In production, you need to store outcome status, guard against executor shutdown, handle exceptions, configure queue capacity, and enforce authorization.

The core point: a long-running operation should not turn a JMX connector thread into an unbounded business worker.

## 9. Polling and the Load Multiplication Effect

A monitoring tool typically calls JMX periodically.

Suppose:

- 200 MBeans.
- Each MBean has 5 attributes to collect.
- 1 agent polls every 10 seconds.

Theoretical number of attribute reads:

\`\`\`text
200 × 5 / 10 = 100 attribute reads/second
\`\`\`

If 4 agents independently poll the same JVM, that can become 400 reads/second, not counting retries and metadata queries.

This number alone does not tell us CPU usage; actual cost depends on the implementation. However, it shows that **frequency and fan-out multiply total workload**.

Principles:

- Poll only the attributes you need.
- Choose intervals based on data change rate and operational value.
- Avoid synchronizing all clients to poll at the exact same instant if it causes spikes.
- Use reasonable jitter and backoff.
- Avoid aggressive retries when the JVM is already slow.
- Measure duration and impact before increasing frequency.
- Consider using a single collector and distributing metrics instead of having many clients query the same MBeans directly.

## 10. getAttribute Versus getAttributes

JMX provides:

\`\`\`java
Object value = connection.getAttribute(name, "QueueDepth");
\`\`\`

and:

\`\`\`java
AttributeList values = connection.getAttributes(
    name,
    new String[] { "QueueDepth", "ProcessedJobs", "Paused" }
);
\`\`\`

Calling getAttributes can reduce round trips when a client needs multiple attributes from **the same MBean**. With remote JMX, this is often an important factor.

However, understand that:

- The underlying getters may still be called to produce each value.
- An expensive getter does not become cheap just by batching the request.
- The result may not contain every attribute if some properties are unreadable or fail.
- You must inspect returned names/values in AttributeList rather than assuming all elements are present in order when errors occur.
- A batch request does not by default provide an atomic snapshot of the entire MBean; state can change between getters.

## 11. Avoid Calling getMBeanInfo Too Frequently

\`getMBeanInfo\` is very useful for discovering attributes, operations, and signatures:

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);
\`\`\`

However, if a client calls getMBeanInfo before every metric read, the metadata and remote round-trip cost can be unnecessary.

A monitoring client can usually:

1. Discover MBeans/attributes on connect or periodically.
2. Cache metadata for the duration of the session.
3. Read known attributes on a schedule.
4. Refresh metadata when an MBean re-registers, topology changes, or errors indicate the contract changed.

Do not cache metadata permanently if MBeans can be unregistered/re-registered or the application version changes.

## 12. High Cost When Returning Large Payloads

An attribute that is a long String or a large custom object can cause:

- Heavy allocation and garbage collection.
- Serialization/deserialization overhead.
- High network bandwidth consumption.
- Increased latency when multiple clients poll.
- Bloat in logs or monitoring systems.
- Compatibility issues with remote clients lacking the corresponding class.

Do not export entire queue contents or a list of all request IDs as a JMX attribute if the goal is just a few summary numbers.

Instead, use:

- Counts, utilization, and min/max/average as needed.
- Bounded summaries or a maximum number of elements.
- Well-structured Open Types with reasonable limits.
- Another API with pagination if large data retrieval is required, with appropriate authentication/authorization.

An MBean can be convenient for administration, but it should not become an unbounded data-export endpoint.

## 13. Measuring JMX Call Latency

Do not optimize based on gut feeling. Measure multiple times, across percentiles, and under multiple load conditions.

Rough code example for measuring a local call:

\`\`\`java
long start = System.nanoTime();

Object value = server.getAttribute(
    objectName,
    "QueueDepth"
);

long elapsed = System.nanoTime() - start;

System.out.println("Elapsed ns: " + elapsed);
System.out.println("Value: " + value);
\`\`\`

This is **not a proper benchmark** if run only once. The first call can incur class loading, JIT warmup, initialization, or cache effects.

A measurement process should:

1. Warm up the system appropriately.
2. Measure enough samples and percentiles such as p50, p95, and p99.
3. Compare when the JVM is idle versus under high business load.
4. Measure local and remote separately.
5. Track CPU, allocations, GC, lock contention, and thread count.
6. Measure both client-side round-trip time and server-side method duration when possible.
7. Avoid letting logging inside the loop skew results.
8. Use a dedicated benchmarking tool such as JMH when accurate microbenchmarks are needed.

Do not attribute the entire duration to "JMX overhead" if the getter runs a database query that takes hundreds of milliseconds.

## 14. Measuring the Getter or Operation Cost

You can instrument the business method to determine processing time independently of transport.

Example:

\`\`\`java
public long queueDepthMeasured() {
    long start = System.nanoTime();
    try {
        return queueService.depth();
    } finally {
        long elapsed = System.nanoTime() - start;
        methodDurationRecorder.record(elapsed);
    }
}
\`\`\`

This measurement has its own overhead. Do not instrument every call with expensive synchronous logging, as it alters the workload being observed.

When you have both client-side and server-side measurements:

\`\`\`text
Remote round-trip latency
    ≈ connector/network overhead
    + JMX dispatch
    + method execution
    + serialization/deserialization
\`\`\`

This is only an analytical breakdown; you must measure in practice to identify the bottleneck.

## 15. Concurrency Control and Backpressure

An MBean operation invoked simultaneously by multiple callers can cause issues:

- Two rebuild tasks contend over the same data.
- Multiple operations hold a shared lock.
- Monitoring clients continuously retry when they see timeouts.
- The management or business thread pool gets exhausted.
- A malicious or misconfigured client generates many requests.

Countermeasures:

- Use an AtomicBoolean, semaphore, or concurrency gate when an operation should only run once at a time.
- Set timeouts on I/O and downstream calls.
- Bound the executor's queue size.
- Reject requests with a clear status when the system is busy.
- Make operations idempotent when possible.
- Maintain auditing for sensitive management commands.
- Do not hold important locks during long-running I/O.

Example limiting to one job at a time:

\`\`\`java
private final Semaphore gate = new Semaphore(1);

@ManagedOperation
public String requestRefresh() {
    if (!gate.tryAcquire()) {
        return "BUSY";
    }

    try {
        executor.execute(() -> {
            try {
                refreshService.refresh();
            } finally {
                gate.release();
            }
        });
        return "ACCEPTED";
    } catch (RuntimeException e) {
        gate.release();
        throw e;
    }
}
\`\`\`

The example assumes the executor accepts the task successfully or throws on rejection; a real application must handle shutdown, failure states, fairness, and retryability.

## 16. Notes on Spring @ManagedAttribute and @ManagedOperation

Example of a management facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueManagement {

    private final QueueService service;

    public QueueManagement(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return service.cachedDepth();
    }

    @ManagedOperation(description = "Request metrics refresh")
    public String requestMetricsRefresh() {
        return service.requestRefresh();
    }
}
\`\`\`

Spring configuration can enable annotation-driven export:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    QueueManagement queueManagement(QueueService service) {
        return new QueueManagement(service);
    }
}
\`\`\`

Notes:

- @ManagedAttribute does not bound getter execution time.
- @ManagedOperation does not automatically turn a heavy task into an asynchronous job.
- MBeanExporter handles exporting metadata and registration, not optimizing business logic for you.
- Annotated methods become the management surface according to the exporter configuration.
- If a service uses an AOP proxy, verify that advice does not add unexpected latency or get bypassed along the invocation path.

## 17. Remote Connections: Adding Network, Serialization, and Security

Remote JMX typically adds the following costs:

- TCP/RMI or the corresponding transport connector.
- Encryption/decryption when TLS is enabled.
- Connection authentication and context.
- Marshaling and serialization of params/results.
- Network RTT, packet loss, and retransmission.
- Connector thread scheduling and server-side queueing.

Do not disable TLS or authentication just to gain better performance. Securing remote JMX is a separate operational requirement; optimization should come from polling design, batching, network placement, and method cost.

A custom MBean with write/invoke operations can cause severe impact if the remote endpoint is exposed, so concurrency limiting is also tied to security.

## 18. Latency and Timeout Do Not Mean the Operation Failed

In some situations, a remote JMX client may time out while an operation is running. That **does not prove** the operation on the server was canceled or rolled back.

For example, while the rebuildIndex operation is running:

\`\`\`text
Client sends invoke
   |
   v
Server starts rebuild
   |
   +-- network timeout occurs
   |
   v
Rebuild may continue
\`\`\`

Therefore:

- Avoid blindly retrying non-idempotent operations.
- Attach a request/job ID and status when needed.
- Allow querying results/progress via a lightweight attribute or operation.
- Design cancellation/timeouts at the actual execution layer rather than relying on client disconnect.
- Log audits to know whether an operation started and finished.

A client-side timeout can coincide with a task that continues consuming CPU/I/O on the server.

## 19. Comparing JMX and Metrics Pipelines

JMX is well suited for:

- Observing Java runtime state.
- Accessing management operations.
- Reading management attributes at low or medium frequency.
- Integrating existing JMX tools and MBeanServer.

A metrics pipeline such as Micrometer/Prometheus is usually suitable when:

- Continuously collecting counters, gauges, and histograms.
- Needing time-series aggregation and multiple instances.
- Having an explicit scrape schedule and a dedicated metrics backend.
- Wanting to avoid remote JMX clients arbitrarily polling a large number of attributes.

However, a metrics exporter also has costs; a gauge callback can execute heavy logic. Do not move an expensive getter to metrics while keeping the exact same implementation and expect the overhead to vanish.

If the application already uses Actuator/Micrometer, consider reusing counters/snapshots for both metrics and the JMX facade to avoid duplicate computation.

## 20. Real-World Scenarios

### Scenario A — Dashboard Polling Every Second

A dashboard calls \`getActiveSessions\` every second. The getter runs a database COUNT(*) query over a large dataset.

Consequence: query volume scales with the number of dashboards, adding load and latency to the database. Solution: maintain a counter or cached snapshot, choose a reasonable interval, and measure freshness.

### Scenario B — JConsole Slowing Down the Application

An MBean has a \`FullReport\` attribute that builds a long report under a synchronized lock. When an operator opens the MBeans tab, JConsole reads the attribute and holds the lock, disrupting business threads.

Solution: replace with a precomputed summary, decouple computation, bound output, and avoid long locks.

### Scenario C — RMI Polling Many JVMs

A collector scrapes hundreds of JVMs, each with hundreds of attributes. Latency and CPU increase due to the number of round trips, serialization, and response sizes.

Solution: reduce polling frequency, select only needed attributes, batch with getAttributes, and measure load.

### Scenario D — Rebuild Operation Causing Timeouts

A JMX client invokes a long-running rebuild operation. The client times out, retries, and spawns two concurrent jobs.

Solution: have the operation return accepted/job ID quickly, limit concurrency, expose outcome status, and define retry rules.

### Scenario E — Querying MBeanInfo Every Time

A monitoring agent calls \`getMBeanInfo\` before every \`getAttribute\`. This is unnecessary when the contract is stable.

Solution: cache metadata per connection/instance and refresh when lifecycle or schema changes.

## 21. Common Issues Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| CPU spikes when JMX monitoring is enabled | Getter performs heavy computation or polls too aggressively | Profile getter, reduce frequency, cache snapshot |
| JVM experiences lock contention | Getter holds a long synchronized lock | Shrink critical section, use snapshot/atomic |
| High remote JMX latency | Network/serialization or method cost | Measure client/server, batch, reduce payload |
| MBean operation times out | Operation executes for too long | Async job/status/concurrency gate |
| Client times out but task still runs | Network timeout does not cancel server-side execution | Control lifecycle and idempotency |
| GC increases after polling | Getter allocates large collections/strings | Return small summaries, reduce allocations |
| Inconsistent monitoring data | Attributes read at different points in time | Use a timestamped snapshot |
| Collector causes high load | Multiple agents polling simultaneously | Coordinate polling, avoid duplicate reads |
| getAttributes is still slow | Underlying getters are expensive | Optimize implementation |
| Metrics and JMX differ | Different sampling methods, freshness, or units | Standardize semantics and snapshots |
| Operation invoked multiple times | Retries or multiple clients | Idempotency, semaphore, audit |
| Remote JMX exposed insecurely | Disabling security to improve performance | Keep authentication/TLS and optimize access patterns |

## 22. Checklist for Designing a Reasonably Costed MBean

Before exposing an attribute:

1. Does the getter perform I/O or network calls?
2. Does it iterate over collections or allocate large objects?
3. Does it hold locks that affect business processing?
4. Can the value be read from Atomic*, volatile, or an immutable snapshot?
5. How much freshness is required? Can it be safely cached?
6. Is the output size bounded?
7. Does the getter have side effects?
8. How often are clients expected to poll, and how many clients are there?
9. Is an equivalent metric already available?
10. Have p95/p99 been measured under realistic load?

Before exposing an operation:

1. How long can it take?
2. Can it block/hold locks or call downstream services?
3. Does it modify data or availability?
4. Does it need an async job and status?
5. Are there concurrency limits and backpressure?
6. Are retries safe and idempotent?
7. Are timeouts/cancellation appropriate?
8. Are authorization and auditing in place?
9. If the client disconnects, how does server-side work proceed?
10. Is there an integration test via MBeanServer?

## 23. Hands-On Exercises

### Exercise 1 — Cheap and Expensive Getters

Create two managed attributes:

- \`ProcessedJobs\`: reads an AtomicLong.
- \`PendingJobs\`: iterates over a collection to count.

Call MBeanServer.getAttribute multiple times to observe processing time and CPU. Record sample counts, and distinguish warmup from steady state. Do not draw conclusions from a single run.

### Exercise 2 — getAttributes

Create an MBean with \`QueueDepth\`, \`ProcessedJobs\`, and \`Paused\`. Compare reading each attribute via getAttribute versus reading them together with getAttributes, especially when testing over a secured remote connector.

### Exercise 3 — Polling Rate

Suppose there are 300 MBeans, 4 attributes each, polled every 15 seconds. Compute total reads/second; then multiply by 3 independent collectors and discuss the impact when a getter consumes 2 ms of CPU.

### Exercise 4 — Long-Running Operation

Create an operation simulating long work using a test fixture, measure the latency of JMX invoke, and try the approach of returning \`ACCEPTED\` immediately and updating status in another attribute. Do not run risky tasks in production.

### Exercise 5 — Concurrency Control

An operation \`rebuild\` is invoked concurrently twice. Design a Semaphore/AtomicBoolean gate so only one request runs. Test the \`BUSY\` status of the second request and flag cleanup when the task finishes.

## 24. Key Takeaways

- **Reading attributes and invoking operations via JMX both run real code**; there is no guarantee of free CPU, I/O, memory, or time.
- Local MBeanServer has management overhead; remote JMX adds transport, serialization, network, and security.
- Good getters are lightweight, read pre-existing data, have no side effects, and avoid long locks.
- Time-consuming operations should have async/status mechanisms, concurrency limits, and clear retry semantics.
- Polling frequency × number of attributes × number of clients determines total call volume.
- getAttributes can reduce remote round trips but does not eliminate the cost inside getters.
- Measure p50/p95/p99 and profile the application under realistic load before optimizing.
- Do not disable JMX authentication/TLS to address performance.
- When the goal is high-volume metrics, consider Micrometer/metrics pipelines while still keeping callbacks/gauges lightweight.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — AttributeList: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/AttributeList.html

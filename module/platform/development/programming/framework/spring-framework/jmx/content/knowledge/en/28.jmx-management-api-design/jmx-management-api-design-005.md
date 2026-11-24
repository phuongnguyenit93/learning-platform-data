# Returning Small, Clear, and Observable Data Types in Spring Framework JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a JMX management API should favor data that is **small, semantically clear, cheap to read, and stable**.
- Distinguish between an **attribute used for monitoring** and an **operation performing a query or control action**.
- Choose simple JMX data types such as `boolean`, `int`, `long`, `double`, `String`, and appropriate Open MBean types when structured data is needed.
- Know when to use `CompositeData`, `TabularData`, or MXBean mapping instead of returning arbitrary business objects directly.
- Avoid returning huge collections, JPA entities, deep object graphs, sensitive data, or types that are hard for JMX clients to serialize or understand.
- Design APIs that separate `summary`, `count`, `status`, and `jobId` from large detailed payloads.
- Test `MBeanInfo`, `OpenType`, return types, read-only behavior, and edge cases when data is empty or changing.
- Account for polling, latency, memory allocation, cardinality, versioning, and authorization in Spring Boot or Spring Framework applications.

## 2. Why Return Types Determine Management API Quality

JMX (Java Management Extensions) is an interface for observing and controlling a JVM and application. Operators may use JConsole, VisualVM, Jolokia, a JMX exporter, or a Java client to inspect attributes and invoke operations. These tools do not always share the application's classpath or business object rendering logic.

An API returning complex, deeply nested objects or thousands of records causes several problems:

1. **Hard to display:** JConsole may not know how to render domain objects.
2. **Hard to use remotely:** objects may not be serializable or the client may lack the corresponding classes.
3. **Resource-intensive:** getters have to query large datasets, copy collections, or serialize objects.
4. **Hard to poll:** continuous reads by monitoring collectors drive up load.
5. **Hard to alert on:** numbers lack consistent names, units, or states.
6. **Easy to leak data:** object graphs may contain tokens, customer details, or internal addresses.
7. **Easy to break compatibility:** business model changes drag along changes to the JMX contract.

Design principle:

> **A good management API does not merely return data; it returns the right amount of data needed for operational decisions.**

For example, instead of returning a `List<Order>` of 50,000 entities, return `PendingOrderCount=154`, `OldestPendingAgeSeconds=27`, and `ProcessingState="RUNNING"`.

## 3. JMX Data Model to Keep in Mind

JMX supports multiple types of MBeans:

| Kind | Meaning | Return Type Design Guidance |
| --- | --- | --- |
| Standard MBean | Based on a conventional management interface. | Prefer primitives, wrappers, `String`, and simple types; check client compatibility. |
| MXBean | Maps Java types to standard Open Types. | Useful for structured data needing stronger JMX interoperability. |
| DynamicMBean | Defines metadata and handles get/set/invoke dynamically. | Return types must stay consistent with `MBeanInfo`. |
| Model MBean | Flexible metadata/descriptors; Spring typically uses an adapter for it. | Limit exposed surface and verify runtime metadata. |

The standard JMX management API can return certain Java objects where appropriate, yet **client readability and remote serializability** depend on the MBean type, connector, and data types. MXBeans/Open MBeans use Open Types, reducing reliance on custom classes.

### 3.1. Simple Types

Usually easy to consume:

```text
boolean    - running / healthy / enabled
int        - worker count / max concurrency
long       - processed count / queue depth
double     - utilization / latency ratio
String     - status / version / job ID
String[]   - small bounded list
Date       - point in time where supported
```

Depending on the implementation, large numbers and timestamps also need clearer semantics: use milliseconds/seconds, UTC/ISO-8601, and documented units. Do not pick a type simply because it transmits easily if operators might misinterpret its meaning.

## 4. Designing Attributes for Monitoring

Example MBean describing a worker:

```text
com.example.jobs:type=Worker,name=Importer

Running                     boolean
QueueDepth                  long
ProcessedItemsTotal         long
LastSuccessfulRunTime       String
AverageProcessingMillis     double
```

Each attribute should answer one clear question:

- `Running`: is the worker still running?
- `QueueDepth`: how many jobs are waiting at read time?
- `ProcessedItemsTotal`: total items processed since what starting point?
- `LastSuccessfulRunTime`: timestamp of the last success in which timezone/format?
- `AverageProcessingMillis`: average over a rolling window or entire lifetime?

A bare number `42` is not enough without a name and unit. For counters, clarify whether they reset on restart. For gauges, clarify how they are calculated and any update lag.

### 4.1. Spring @ManagedResource Example

```java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Importer",
    description = "Importer status and counters"
)
public class ImporterStatusManagement {

    private final ImporterMetrics metrics;

    public ImporterStatusManagement(ImporterMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Whether importer is running")
    public boolean isRunning() {
        return metrics.isRunning();
    }

    @ManagedAttribute(description = "Queued items (count)")
    public long getQueueDepth() {
        return metrics.getQueueDepth();
    }

    @ManagedAttribute(description = "Items processed since JVM start")
    public long getProcessedItemsTotal() {
        return metrics.getProcessedItemsTotal();
    }

    @ManagedAttribute(description = "Last success timestamp in ISO-8601 UTC")
    public String getLastSuccessfulRunTime() {
        return metrics.getLastSuccessfulRunTime();
    }
}
```

`ImporterMetrics` is an application-defined internal interface/service for reading metric snapshots. The adapter does not need to expose the metrics object or business entities as JMX values.

## 5. JMX Getters Must Be Lightweight with Minimal Side Effects

A JMX attribute getter is not just metadata. Every time a client calls `getAttribute`, the getter code actually executes.

Good design:

```java
@ManagedAttribute
public long getQueueDepth() {
    return queueDepthGauge.get();
}
```

Anti-pattern:

```java
@ManagedAttribute
public long getQueueDepth() {
    return repository.findAllPendingOrders().stream().count();
}
```

The second example may load all entities from the database and count them in the JVM; if monitoring polls every second, this becomes a major source of load. When a database query is needed, use a properly indexed count query, a scheduled snapshot, or a managed metric gauge.

Also avoid getters that:

- Call downstream HTTP APIs on every read.
- Create files or reset counters.
- Execute write transactions.
- Hold locks for a long time.
- Parse megabytes of JSON.
- Wait indefinitely on `Future.get()`.
- Return mutable collections that can be modified concurrently during serialization.

**A read-only getter in JMX does not automatically guarantee execution is harmless.** The implementation may still have side effects or consume heavy resources; test latency and load.

## 6. Data Volume Matters More Than Element Size

A `String[]` looks simple, but if it contains hundreds of thousands of elements it is no longer small data.

Example to avoid:

```java
@ManagedAttribute
public String[] getAllActiveSessionIds() {
    return sessionRepository.findAllSessionIds();
}
```

Problems:

- Large payloads and high bandwidth cost over remote JMX.
- High object allocation and GC pressure.
- Potential exposure of sensitive identifiers.
- Inconsistent snapshots while the dataset mutates.
- Hard for monitoring tools to turn into useful metrics.

Better design:

```java
@ManagedAttribute
public long getActiveSessionCount() {
    return sessionMetrics.activeCount();
}

@ManagedAttribute
public long getOldestSessionAgeSeconds() {
    return sessionMetrics.oldestAgeSeconds();
}
```

If a detailed list is truly needed, use a dedicated management API with pagination/limits and proper authorization rather than turning a JMX attribute into an unbounded data export endpoint.

## 7. What Should Operations Return?

JMX operations should return results with easy-to-understand semantics. Examples:

```text
requestRefresh() -> String requestId
getRefreshStatus(String requestId) -> String
getLastValidationError() -> String
resetDiagnosticCounters() -> boolean
```

- `requestId` confirms a request has been accepted.
- `status` indicates progress or terminal state.
- `boolean` is appropriate only when `true`/`false` are clearly defined.
- Exceptions represent rejection or errors and should not be mixed with valid data.

For long-running tasks, do not return a domain object or `Future` directly expecting the JMX client to wait. Using a request ID plus a small status value is much easier to consume.

### 7.1. Asynchronous Operation Example

```java
@ManagedOperation(
    description = "Submit refresh and return request ID"
)
public String requestRefresh() {
    return refreshCoordinator.submit();
}

@ManagedOperation(
    description = "Return QUEUED, RUNNING, SUCCEEDED or FAILED"
)
public String getRefreshStatus(String requestId) {
    return refreshCoordinator.status(requestId);
}
```

`refreshCoordinator` is an application-built service. It must handle job lifecycle, idempotency, retention, concurrency, exceptions, and authentication/authorization if the operation has side effects.

**Do not treat a request ID as proof that the job succeeded.** It only enables tracking.

## 8. Structured Data: When Is CompositeData Needed?

If you need to return a tightly related group of fields, a set of separate attributes can lack snapshot consistency. Example:

```text
ImportStatus:
  state             RUNNING
  queueDepth        23
  processedTotal    100532
  lastSuccessEpoch  1730000000000
```

JMX Open MBeans provide `CompositeData` to represent structured data with fields and types described by `CompositeType`/`OpenType`.

Simple example:

```java
import javax.management.openmbean.CompositeData;
import javax.management.openmbean.CompositeDataSupport;
import javax.management.openmbean.CompositeType;
import javax.management.openmbean.OpenType;
import javax.management.openmbean.SimpleType;

public CompositeData getStatusSnapshot() throws Exception {
    String[] keys = { "state", "queueDepth" };
    String[] descriptions = {
        "Current state", "Queued item count"
    };
    OpenType<?>[] types = {
        SimpleType.STRING, SimpleType.LONG
    };

    CompositeType type = new CompositeType(
        "ImportStatus",
        "Importer status snapshot",
        keys, descriptions, types
    );

    return new CompositeDataSupport(
        type,
        keys,
        new Object[] { "RUNNING", 23L }
    );
}
```

This is a plain Java JMX OpenData example. When exporting via Spring, choose an MBean/assembler type that keeps return type metadata compatible; do not assume Spring automatically converts any arbitrary POJO method into an Open MBean.

### 8.1. Benefits

- Fields are clearly named with `OpenType` definitions.
- Clients do not necessarily need the application's custom domain classes.
- Enables transmitting small snapshots with multiple related indicators.
- Easier to render than arbitrary `Map<String,Object>` in tools supporting OpenData.

### 8.2. Limitations

- The schema must remain stable.
- Oversized data is still unsuitable even as `CompositeData`.
- Deeply nested structures can be awkward to inspect in JConsole.
- Field/type changes can break clients.
- Should not be used to expose sensitive data without authorization.

## 9. TabularData: Use Only for Small Bounded Tables

`TabularData` represents a schema-defined table using `TabularType` where each row is a `CompositeData`. It works well for a small table such as:

```text
Top 5 queues:
  QueueName       Depth
  payments        4
  emails          8
  invoices       11
  retries        17
  notifications  23
```

Returning millions of records as `TabularData`, however, is not a good management API. When large tables are needed, use a dedicated query system/endpoint with pagination, filtering, and auth rather than turning JMX into a data query engine.

A JMX API might expose only:

```text
getTopQueues(int maxRows) -> TabularData
```

and validate `maxRows` within a small defined range. Enforce a safe upper bound; never let a client pass `Integer.MAX_VALUE` and force the server to dump every record.

## 10. MXBean and Open Type Mapping

MXBeans automatically map certain Java types to JMX Open Types, improving interoperability across JVMs and JMX clients.

Example:

```java
public interface ImportMonitorMXBean {
    long getQueueDepth();
    String getState();
}

public final class ImportMonitor
        implements ImportMonitorMXBean {
    public long getQueueDepth() { return 7L; }
    public String getState() { return "RUNNING"; }
}
```

For complex types, MXBean mapping follows specific rules. Never assume every Java class automatically maps to a valid `OpenType`. When designing structured data, verify JDK-supported types or use compatible DTOs and inspect `MBeanInfo`/`OpenType` at runtime.

### 10.1. Standard MBean, MXBean, and Spring Model MBean

These three mechanisms can give clients different experiences for the same Java type:

- Standard MBean exposes Java types directly per its interface contract.
- MXBean applies specific Open Type mapping.
- Spring's metadata-based exporter builds metadata from annotations/assemblers and adapters.

Choose the mechanism based on client requirements, not merely because an annotation is convenient.

## 11. Enums, Status, and Versioning

Returning an `enum` directly from a Standard MBean can couple remote clients to the application's class; in many cases a stable `String` is easier to consume.

Example:

```java
@ManagedAttribute
public String getProcessingState() {
    return state.name();
}
```

Defined value set:

```text
IDLE
RUNNING
PAUSED
FAILED
```

If `DRAINING` is added later, clients must handle unknown values gracefully instead of crashing. Avoid returning free-form message strings as the primary status if monitoring tools will parse it.

**Status code** and **human-readable message** should be two separate fields when needed:

```text
StatusCode = FAILED
StatusMessage = Unable to reach downstream service
```

Messages can change in wording or language, so do not use them as logic keys or metric labels.

## 12. Measurement Units Must Be Transparent

For example, an attribute `AverageLatency=250` does not say whether it is milliseconds, seconds, or microseconds.

Name clearly:

```text
AverageLatencyMillis = 250.0
UptimeSeconds        = 3600
HeapUsedBytes        = 128000000
CpuUtilizationRatio  = 0.75
```

Also provide a description:

```java
@ManagedAttribute(
    description = "Average processing latency in milliseconds"
)
public double getAverageLatencyMillis() {
    return metrics.getAverageLatencyMillis();
}
```

For absolute timestamps, use an explicit format such as ISO-8601 UTC or epoch milliseconds with a unit-bearing name. Avoid `LocalDateTime.toString()` without timezone context when data is observed across multiple hosts.

## 13. Snapshot Metrics and Consistency

Suppose a client reads sequentially:

```text
ProcessedTotal = 120
FailedTotal    = 5
SuccessTotal   = 116
```

The three values may be read at three different instants, so the sum no longer adds up. That does not necessarily indicate a synchronization bug or data corruption.

When a consistent snapshot is needed, you can:

- Capture an immutable snapshot in code and expose multiple fields from it.
- Use `CompositeData` for a small group of fields.
- Include a snapshot timestamp or version.
- Use locking/copying appropriate for the load level.
- Bound the snapshot cost so getters are never blocked.

Example:

```java
public record QueueSnapshot(
    long processed,
    long failed,
    long success,
    long capturedEpochMillis
) {}
```

This record is an application domain DTO. To expose it via JMX, apply appropriate mapping (e.g., MXBean/Open Data or flatten into simple fields); do not assume every JMX client automatically interprets Java records.

## 14. Avoid Secrets and PII

Management APIs can be read by monitoring tools, operators, or remote connectors. Never expose:

- Passwords, OAuth tokens, API keys, private keys.
- Full connection strings containing credentials.
- Personal or customer data when not strictly needed.
- Session identifiers or request bodies.
- Unsanitized stack traces that may contain sensitive data.
- Unnecessary internal file paths or topology details.

Instead of:

```java
@ManagedAttribute
public String getDatabaseConnectionString() {
    return datasource.getUrl(); // May expose internal topology.
}
```

provide a summary indicator:

```java
@ManagedAttribute
public boolean isDatabaseHealthy() {
    return databaseHealthSnapshot.isHealthy();
}
```

The getter must still remain lightweight: avoid running expensive synchronous connection checks on every JMX poll; use a periodically updated health state.

## 15. Compatibility of MBeanInfo

A JMX client can dynamically discover attributes and operations via:

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
```

For a stable API, tests should guard:

1. Correct `ObjectName`.
2. Attribute names and types.
3. Correct read/write flags.
4. Operation names, signatures, and return types.
5. Necessary descriptions and units.
6. No sensitive methods exported.

Changing `long` → `String` can stop clients from reading values as before. Renaming attributes can also break monitoring rules.

## 16. Example Test for a Small, Clear Attribute

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;

MBeanAttributeInfo depth = Arrays.stream(info.getAttributes())
    .filter(a -> "QueueDepth".equals(a.getName()))
    .findFirst()
    .orElseThrow(() ->
        new AssertionError("Missing QueueDepth"));

if (!"long".equals(depth.getType())
        || !depth.isReadable()
        || depth.isWritable()) {
    throw new AssertionError("QueueDepth contract mismatch");
}
```

For the return value, read the value in a test lab to confirm its runtime type:

```java
Object value = server.getAttribute(name, "QueueDepth");
if (!(value instanceof Long)) {
    throw new AssertionError("Expected long attribute value");
}
```

Keep in mind that Java reflection/JMX boxes primitive `long` into `Long` in the returned `Object`, whereas `MBeanInfo` reports the type name as `long`.

## 17. Testing Payload Size and Latency

For getters meant for polling, add performance tests at an appropriate level:

- Each read performs no full table scan.
- Read duration is short enough for the polling frequency.
- Collections/arrays have an upper bound.
- Memory allocations do not scale steeply with business record count.
- Null/unknown values are handled predictably.
- Downstream errors do not block `MBeanServer` threads indefinitely.

Example if a list must be returned:

```java
@ManagedOperation(
    description = "Return at most 10 recent error codes"
)
public String[] getRecentErrorCodes() {
    return errorRegistry.latestCodes(10)
        .toArray(String[]::new);
}
```

The contract should cap the array at 10 items, and each item should also have bounded size. `latestCodes(10)` must be a service method designed without copying a massive dataset.

### 17.1. Why Can a Fast Getter in Dev Still Be Slow in Prod?

Dev has only a handful of entities, whereas production has millions. Always test with representative load and data volumes, monitor real latency, and avoid linear scans over datasets in frequently polled getters.

## 18. When to Choose Metrics Instead of JMX Details

JMX suits direct administration and observation, but it is not a time-series database. For long-term dashboards and alerting:

| Need | Typically Suitable Approach |
| --- | --- |
| Read instantaneous JVM state | JMX attributes / JConsole |
| Read a concise business status | Spring JMX MBean |
| Time-series charts | Micrometer + monitoring backend |
| Alert thresholds across instances | Metrics collector / time-series system |
| Detailed record listings | Dedicated admin API with pagination/filter/auth |
| Bulk data download/export | Asynchronous job and dedicated storage |

Do not expose the same large dataset over both JMX and HTTP just because multiple tools consume it. Maintain a single internal metric source and provide small, transport-appropriate views.

## 19. Contrasting Design Patterns

### Anti-pattern A — Returning All Entities

```java
@ManagedOperation
public List<Order> getAllPendingOrders() {
    return orderRepository.findAllPending();
}
```

Problems: unbounded size, JMX clients may lack classes, sensitive data, heavy database cost.

### Better Approach

```java
@ManagedAttribute
public long getPendingOrderCount() {
    return orderMetrics.pendingCount();
}

@ManagedAttribute
public long getOldestPendingAgeSeconds() {
    return orderMetrics.oldestPendingAgeSeconds();
}
```

### Anti-pattern B — Returning a Future for a Long Job

```java
@ManagedOperation
public Future<String> rebuildIndex() {
    return rebuildService.submit();
}
```

Problems: `Future` is not an easily observable result type, and the client has no visibility into job lifecycle.

### Better Approach

```java
@ManagedOperation
public String requestIndexRebuild() {
    return rebuildService.submitAndReturnId();
}

@ManagedOperation
public String getIndexRebuildStatus(String id) {
    return rebuildService.status(id);
}
```

### Anti-pattern C — Using Messages as Status

```text
"Everything looks good at 10:01"
"Maybe busy; try later"
```

These strings are helpful for humans but difficult to automate rules against. Separate `StatusCode=HEALTHY/BUSY/FAILED` from `StatusMessage`.

## 20. Handling Null, Unknown, and Errors

A management API needs clear semantics when data is absent:

- Never run yet: is `LastRunTime` empty or `"NEVER"`?
- Undetermined status: what does `"UNKNOWN"` mean?
- Uninitialized counter: is `0` truly zero or missing?
- Non-existent Job ID: return `"NOT_FOUND"` or throw an exception?
- Unauthorized client: security errors must never be masked as valid values like `0`.

Good example:

```java
@ManagedAttribute
public String getLastSuccessTimeUtc() {
    return lastSuccess == null
        ? "NEVER"
        : lastSuccess.toString();
}
```

For a public management contract, document that `"NEVER"` is a valid sentinel. When using MXBean/OpenData, choose a structured or nullable representation suited to mapping rules and client needs.

Do not return `null` indiscriminately for all exceptions: clients will be unable to tell missing data apart from system failures.

## 21. Consistency and Minimizing Side Effects

Getters can be invoked automatically by monitoring tools. Therefore:

1. Do not write to the database inside a getter.
2. Do not reset counters when a getter is read.
3. Do not hold long locks or wait on long jobs.
4. Do not open unnecessary new sessions/connections.
5. Do not log at `INFO` level on every poll, causing a log storm.
6. Do not return mutable collections that may mutate while being read.
7. Do not build large object graphs just to display a few numbers.
8. Do not let formatters make external network calls.

If complex metric updates are required, use asynchronous sampling/caching/snapshotting with clearly defined freshness.

## 22. Designing in Spring Boot

Spring Boot provides JMX auto-configuration and Actuator JMX exposure depending on dependencies and version. Common properties:

```properties
spring.jmx.enabled=true
management.endpoints.jmx.exposure.include=health,info
```

This neither exports all Spring beans automatically nor enables a remote JMX connector. `management.endpoints.web.exposure.include` and JMX exposure can differ.

When a project uses `@EnableMBeanExport` or a custom `MBeanExporter`, avoid multiple exporters registering the same `ObjectName`. Inspect actual `MBeanInfo` once the Spring context is ready.

For remote JMX, connector authentication, TLS, and authorization are separate responsibilities. Spring Security HTTP does not protect JMX/RMI by default.

## 23. Hands-on Exercises

### Exercise 1 — Design a Status MBean

Create `ImporterStatusManagement` with `Running`, `QueueDepth`, `ProcessedItemsTotal`, and `LastSuccessfulRunTime`. Add complete descriptions and verify read-only flags.

**Goal:** small, clear data with explicit units.

### Exercise 2 — Convert an API Returning a Large List

Given a method `getAllPendingOrders()`, propose two or three replacement attributes that help operators diagnose issues without fetching all entities.

**Goal:** reduce payload size and data exposure.

### Exercise 3 — CompositeData

Create a `CompositeData` snapshot containing `state`, `queueDepth`, and `processedTotal` with proper `OpenType` definitions. Read the metadata and values using a Java client.

**Goal:** understand Open MBean data structures.

### Exercise 4 — Small Table

Create an operation returning the top 5 queues as `TabularData`. Try requesting 5000 rows and verify validation rejects or caps the request.

**Goal:** bounded data, avoiding unbounded payloads.

### Exercise 5 — Async Job Status

Design `requestRefresh()` returning an ID and `getRefreshStatus(id)` returning one of a fixed set of statuses.

**Goal:** distinguish accepted from completed.

### Exercise 6 — Contract Test

Check `MBeanInfo` for type, writability, signature, and description, plus negative assertions ensuring no internal methods are exported.

**Goal:** safeguard compatibility and security.

### Exercise 7 — Polling Load

Create one getter reading a snapshot and another performing a full data scan. Compare latency and allocations under repeated polling in a test environment.

**Goal:** understand the cost of a management getter.

## 24. Review Questions

**1. Why avoid returning full domain entities via JMX?** Because of large payloads, classpath/serialization coupling, poor displayability, and potential information leakage.

**2. Which types are usually easiest to observe?** Primitives, `String`, and small, clearly structured Open Types.

**3. When should `CompositeData` be used?** When a small snapshot with multiple named fields and stable types is needed.

**4. Is `TabularData` suitable for exporting millions of records?** No. It still incurs payload/serialization costs and is operationally unwieldy.

**5. Does `isWritable` indicate user permissions?** No. It indicates writability in MBean metadata.

**6. Why put units in attribute names?** To avoid confusion between milliseconds, seconds, bytes, and ratios.

**7. Does receiving a `requestId` mean the job has finished?** No; the client must check status.

**8. Why must JMX getters be lightweight?** Because monitoring tools may poll them continuously.

**9. Should alerts parse free-form status messages?** No. Use stable status codes.

**10. What can break when changing `long` to `String` in an MBean?** Clients and monitoring rules may break.

## 25. Summary

**Returning small, clear, and observable data types** is a foundational principle when designing a Spring Framework JMX management API. A good attribute returns just enough information for operational decisions, with stable names, units, types, freshness, and semantics. A good operation returns concise results that cleanly distinguish request acceptance from actual completion.

Prefer primitives/`String` or suitable Open Types; avoid large domain objects, entity collections, sensitive data, and heavy getters. Use `CompositeData`/MXBeans for small multi-field snapshots when helpful; use dedicated APIs or async jobs for large data. Always verify `MBeanInfo` at runtime, test latency/payload size, enforce JMX permissions, and maintain contract compatibility.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `ManagedAttribute`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — `ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `CompositeData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/CompositeData.html
- Java SE 21 — `TabularData`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/openmbean/TabularData.html
- Java SE 21 — MXBean documentation: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
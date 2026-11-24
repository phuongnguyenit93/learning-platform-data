# Selecting Operationally Useful Management Information in Spring JMX

## 1. Context

A Spring application can have hundreds of Spring beans and thousands of methods. However, **a good management API is not an API that exposes as much information as possible**. The goal of JMX is to help operators understand the current state of the system, identify signs of anomalies, find root causes, and safely perform permitted administrative operations.

In Spring Framework JMX, common annotations include:

- \`@ManagedResource\` describes a managed resource and its JMX name.
- \`@ManagedAttribute\` exposes a readable/writable attribute to management tools.
- \`@ManagedOperation\` exposes an operation that can be invoked via JMX.
- \`@ManagedNotification\` describes the types of notifications an MBean can emit.
- \`@ManagedOperationParameter\` provides descriptions for operation parameters.

Choosing what to expose is a **management contract design** decision, not merely adding annotations.

This lesson helps you:
1. Start from operational questions before choosing attributes.
2. Distinguish between state, metrics, configuration information, and management operations.
3. Design managed attributes that are easy to understand, low-impact, and cheap to read.
4. Choose useful operations while limiting risk.
5. Use notifications for significant state transitions.
6. Design consistent ObjectNames, descriptions, units, and error semantics.
7. Avoid exposing sensitive data and unnecessary business methods.
8. Test the management API using \`MBeanServer\` and realistic operational scenarios.

## 2. Start from Operator Questions

Before writing code, list the questions on-call engineers need to answer:

- Is the application still alive?
- Which resource is overloaded?
- Which queue is building a backlog?
- How many jobs are running, succeeded, or failed?
- Are connections to critical dependencies failing?
- What runtime configuration is currently in effect?
- What kind of error occurred most recently and when did it happen?
- Can a worker be safely paused?
- When an incident occurs, which operation can recover without corrupting data?
- When support is needed, can operators identify the exact instance experiencing the issue?

An example design table:

| Operational Question | Proposed Management Element | Reason |
|---|---|---|
| How large is the queue backlog? | Read-only \`PendingCount\` | Shows backlog |
| Is the worker running or paused? | Read-only \`State\` | Determines state |
| When was the last completion? | \`LastSuccessTime\` | Detects stalled progress |
| Is the error rate increasing? | Counters and metrics | Trend analysis |
| Can new work intake be paused? | Operation \`pauseIntake()\` | Clearly scoped action |
| Can processing be resumed? | Operation \`resumeIntake()\` | Procedural recovery |
| Is there a new critical error? | Notification \`worker.failed\` | Immediate signaling |
| Do we need to see runtime configuration? | Read-only non-secret settings | Diagnoses drift |

Not every question has to be answered through JMX. Solutions such as logs, distributed tracing, metrics backends, health endpoints, and dashboards have their own strengths. JMX should complement them with information **suited to in-JVM state and the component's management interface**.

## 3. Principles for Selecting Management Information

### 3.1. Useful for a Decision

A good attribute must lead to a clear action or assessment:

\`\`\`text
PendingCount = 1250
\`\`\`

is usually more useful than:

\`\`\`text
InternalQueueObject = com.example.queue.QueueImpl@3d01c6
\`\`\`

The first piece of information can be used to set alert thresholds or monitor backlog. The second is an opaque and unstable Java object representation.

### 3.2. Precise Semantics

The name \`Count\` is not enough. Count of what? At what point in time? Cumulative or instantaneous value?

Prefer naming:
- \`PendingCount\` — number of unprocessed jobs at read time.
- \`ProcessedTotal\` — total number of jobs processed since reset.
- \`FailuresTotal\` — total failures within a clearly defined scope.
- \`LastCompletedAt\` — timestamp of the most recent completion.

Each attribute needs a description clarifying **unit, scope, and reset conditions**.

### 3.3. Fast to Read and Low Impact

JConsole or a monitoring collector may poll attributes continuously. A getter that reads an \`AtomicLong\` is usually acceptable; a getter that queries an entire database or calls an external API can introduce load.

A managed getter should strive for:
- Short and predictable execution time.
- No side effects.
- Not blocking the hot path.
- Not holding a global lock for too long.
- Clear default/unavailable representation.
- Caching/snapshotting if computation is expensive.

### 3.4. Do Not Expose Sensitive Data

Avoid exposing:
- Passwords, API keys, bearer tokens.
- Connection strings containing credentials.
- Customer PII, emails, addresses.
- Internal raw stack traces containing secrets.
- Unclassified business payloads.
- Sensitive paths or configuration values unnecessary for operations.

An attribute readable via JMX can be collected by tools outside the application. Do not assume it is only visible on the local machine.

### 3.5. Stable Contract

JMX clients and monitoring scripts may depend on ObjectNames, attribute names, and operation signatures. Renaming them just because a Java class was refactored makes the management interface unstable.

## 4. Categorizing the Management API

Information can be divided into five groups.

| Group | Examples | Appropriate Design |
|---|---|---|
| Identity | App, instance, version | Read-only attributes |
| Health/state | Running, paused, degraded | Read-only attributes + notifications |
| Metrics | Queue depth, completed count, error rate | Attributes or metrics system |
| Configuration | Current concurrency limit, current mode | Read-only first; writable only when truly needed |
| Control | Pause, resume, clear cache | Explicit operations, validation, and authorization |

Each group carries different risks. Identity and state are generally safer to expose, though sensitive data still needs to be reviewed. Control operations can affect production data and therefore require stricter controls.

## 5. Use-Case Example of Designing an MBean

Suppose a Spring application has an order-processing worker. Operators need to know:
- Is the worker accepting new work?
- How large is the backlog?
- How many jobs are currently running?
- When was the most recent successful processing?
- Can new work intake be paused during a maintenance window?

A managed bean might look like this:

\`\`\`java
package com.example.operations;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=OrderProcessor",
    description = "Order processing worker management"
)
public class OrderWorkerManagement {

    private final AtomicInteger pendingCount = new AtomicInteger();
    private final AtomicInteger activeCount = new AtomicInteger();
    private final AtomicLong processedTotal = new AtomicLong();

    private volatile boolean intakePaused;
    private volatile Instant lastCompletedAt;

    @ManagedAttribute(description = "Pending orders at read time")
    public int getPendingCount() {
        return pendingCount.get();
    }

    @ManagedAttribute(description = "Orders currently being processed")
    public int getActiveCount() {
        return activeCount.get();
    }

    @ManagedAttribute(description = "Processed orders since counter reset")
    public long getProcessedTotal() {
        return processedTotal.get();
    }

    @ManagedAttribute(description = "Whether new work intake is paused")
    public boolean isIntakePaused() {
        return intakePaused;
    }

    @ManagedAttribute(description = "Last successful completion, ISO-8601 UTC")
    public String getLastCompletedAt() {
        Instant value = lastCompletedAt;
        return value == null ? "" : value.toString();
    }

    @ManagedOperation(description = "Pause intake of new orders")
    public void pauseIntake() {
        intakePaused = true;
    }

    @ManagedOperation(description = "Resume intake of new orders")
    public void resumeIntake() {
        intakePaused = false;
    }
}
\`\`\`

This is a model illustrating a management interface. In a real application, state/counters should be retrieved from the service responsible for processing rather than maintaining a separate copy of state that can drift from the actual worker. The two operations should delegate to a service with proper validation and concurrency handling.

### Why Not Expose Every Method?

If \`OrderWorkerManagement\` has methods like \`processInternalOrder()\`, \`loadCustomerData()\`, or \`deleteAllPendingRecords()\`, they should not be exported merely because they are public methods. Exposing a method publishes a management capability that can be invoked via JMX, including remotely if the connector grants access.

## 6. Read-Only Attributes First

A JMX attribute can be read-only or writable. When operators only need to observe, choose read-only.

\`\`\`java
@ManagedAttribute(description = "Number of active jobs")
public int getActiveJobs() {
    return activeJobs.get();
}
\`\`\`

For a writable attribute:

\`\`\`java
@ManagedAttribute(description = "Maximum allowed parallel jobs")
public int getMaxParallelJobs() {
    return maxParallelJobs;
}

@ManagedAttribute(description = "Maximum allowed parallel jobs")
public void setMaxParallelJobs(int value) {
    if (value < 1 || value > 64) {
        throw new IllegalArgumentException("Must be within 1..64");
    }
    maxParallelJobs = value;
}
\`\`\`

A writable attribute requires:
- Min/max bounds and valid state constraints.
- Determining whether the change takes effect immediately.
- Persistence rules across restarts.
- Concurrency safety.
- JMX authorization.
- Logging/auditing when values are sensitive.
- Rollback or recovery mechanisms if a change is invalid.

If a configuration change involves multiple conditions or significant impact, a clearly named managed operation is sometimes better than a simple setter.

## 7. Choose Manageable Data Types

Attributes should use types that can be displayed and transmitted over JMX:

- Primitives and wrappers.
- \`String\`, \`boolean\`, \`long\`, \`double\`.
- Enums with a well-defined contract representation.
- Simple arrays when necessary.
- \`CompositeData\`, \`TabularData\`, or MXBean-compatible types for structured data.

Avoid exposing complex object graphs directly:
- Spring \`ApplicationContext\`.
- \`DataSource\` implementations.
- \`EntityManager\`/\`Session\`.
- Raw \`ThreadPoolExecutor\` objects.
- Hibernate/JPA entities or large collections.
- Internal DTOs requiring the remote client to have the full classpath.

Complex types increase serialization overhead and the risk of incompatibility. For monitoring, several small, well-defined attributes are usually more convenient than returning an arbitrary internal object.

### Representing Time

Provide timestamps in a consistent standard format, for example:
- ISO-8601 UTC string: \`2026-11-11T08:30:00Z\`.
- Epoch milliseconds with a clear unit description.

Avoid returning timestamps formatted in the machine's default locale because operators across multiple time zones may misinterpret them.

## 8. Which Metrics Are Worth Exposing?

Not every computable number is useful.

### Commonly Valuable Groups

**Throughput**
- ProcessedTotal.
- CompletedPerMinute, if the calculation method is clearly defined.
- TasksAcceptedTotal.

**Backlog and saturation**
- PendingCount.
- ActiveCount.
- QueueCapacity.
- RejectedTasksTotal.

**Failures**
- FailedTotal.
- LastFailureAt.
- LastFailureCategory with sensitive information filtered out.

**Timing**
- LastSuccessAt.
- ProcessingDurationMs with clear definition and aggregation.
- QueueWaitDurationMs if proper instrumentation is available.

**Resource utilization**
- ActiveConnections.
- PoolSize.
- FreePoolSlots.
- CacheEntryCount.

### Avoid Metrics Without Semantics

For example, \`Load=0.8\` does not clarify:
- Is 0.8 equal to 80% or an absolute number?
- Over what time window is it measured?
- Does it belong to CPU, pool, queue, or a custom metric?
- What is the data source and freshness?

A better name could be \`WorkerUtilizationRatio\`, description: "Active worker slots divided by configured maximum, range 0.0..1.0".

### Do Not Turn JMX into a Metrics Backend

JMX provides a runtime management interface; dedicated metrics systems are usually better suited for:
- Long-term time-series storage.
- Centralized querying across multiple instances.
- Histograms and percentiles.
- Cardinality controls and alerting.
- Cross-service dashboards.

If Micrometer/Prometheus is already in place, there is no need to expose every metric a second time via custom JMX attributes. JMX can be used for diagnostic states and operations that metrics do not express well.

## 9. Design Operations by Risk Level

Choose an operation when operators genuinely need to **take action**.

Examples:
- \`pauseIntake()\`: stop accepting new work without losing in-flight work.
- \`resumeIntake()\`: resume intake.
- \`reloadReadOnlyConfiguration()\`: reload validated configuration.
- \`resetStatistics()\`: reset counters without affecting business state.
- \`triggerHealthCheck()\`: run a check with bounded cost.

Dangerous operations:
- \`deleteAllOrders()\`.
- \`resetProductionDatabase()\`.
- \`drainQueueWithoutAck()\`.

High-impact operations should not be exposed via JMX by default. If required, you must design authorization, auditing, preconditions, concurrency controls, and clear operational procedures.

### Operation Checklist

| Question | Requirement |
|---|---|
| Is the action idempotent? | Define retry semantics |
| Does it modify business data? | Review risk and permissions |
| Is it long-running? | Avoid blocking the JMX connector |
| Can it run concurrently? | Concurrency guard |
| What if it fails partway through? | Error/state model |
| Are parameters validated? | Reject invalid input |
| Is it audited? | Based on impact level |
| Is rollback/compensation needed? | Design explicitly |
| Is rate limiting needed? | Rate limiting/operational policy |

### Long-Running Operations Should Submit Async Jobs

Instead of:

\`\`\`java
@ManagedOperation
public void rebuildAllIndexes() {
    // 30 minutes of processing inside a JMX call.
}
\`\`\`

you can use:

\`\`\`java
@ManagedOperation(description = "Request index rebuild and return job ID")
public String requestIndexRebuild() {
    return rebuildService.submit();
}
\`\`\`

and expose \`getRebuildStatus()\` or status notifications. JMX remains the channel to trigger the action, not a transport pipe for multi-minute execution.

You need to decide the semantics of the request ID, idempotency, and retries, especially when a remote client times out after the server has already received the request.

## 10. Use Notifications for Important Changes

A JMX notification may be appropriate when:
- A worker transitions to DEGRADED.
- A queue is paused/resumed.
- An administrative task completes.
- A resource pool crosses a threshold.
- A configuration reload succeeds/fails.

\`\`\`java
@ManagedNotification(
    name = "com.example.orders.worker.degraded",
    notificationTypes = {"com.example.orders.worker.degraded"},
    description = "Worker entered degraded state"
)
\`\`\`

The annotation describes the type of notification an MBean can emit; it **does not generate events on its own**. The producer must actually emit it via \`NotificationPublisher\` or an appropriate JMX broadcaster.

Do not emit a notification for every single processed item in a high-throughput system; doing so can cause overload, noise, and make it difficult to distinguish critical events.

### Notifications Are Not a Durable Event Queue

JMX notifications do not guarantee durable replay if a listener has not registered, loses connection, or the JVM restarts. If events must not be lost, use durable messaging or an event store. JMX notifications should serve as signals for dashboard refreshes or administrative alerts.

## 11. ObjectName: Meaningful and Stable Names

ObjectName:

\`\`\`text
com.example.orders:type=Worker,name=OrderProcessor
com.example.orders:type=Queue,name=Payments
com.example.orders:type=Cache,name=Products
\`\`\`

A useful convention:
- Domain by application.
- \`type\` by MBean category.
- \`name\` by logical resource.
- \`instance\` when multiple MBeans of the same type exist on one server.
- \`env\` if you want to distinguish prod/staging/local in metadata.

Do not embed secrets, request IDs, session IDs, or user data in an ObjectName.

Avoid using runtime class names as the JMX contract; Spring AOP proxies and refactoring can cause class names to change.

### Environment-Qualified Names

\`\`\`text
com.example.orders:env=prod,type=Queue,name=Payments
com.example.orders:env=staging,type=Queue,name=Payments
\`\`\`

The same name can exist across different JVMs without conflict. Naming is only part of identity; monitoring must bind to the target/connector identity. The \`env\` key does not enforce access control on its own.

## 12. Metadata and Describing the Management Contract

\`@ManagedAttribute(description="...")\` or \`@ManagedOperation(description="...")\` should be written like concise documentation for operators.

Good example:

\`\`\`java
@ManagedAttribute(
    description = "Number of pending jobs, sampled at read time"
)
public int getPendingCount() { ... }
\`\`\`

Poor example:

\`\`\`java
@ManagedAttribute(description = "Value")
public int getCount() { ... }
\`\`\`

If a value has a unit, state it clearly:
- milliseconds.
- seconds.
- bytes.
- count.
- percentage.
- ratio 0..1.
- epoch milliseconds.

For counters, state the reset scope clearly:
- Since application start.
- Since last statistics reset.
- Within last minute.

Names and descriptions do not enforce validation or authorization. They only help clients understand the contract.

## 13. Expose Only Necessary Components

In a large Spring service with methods:

\`\`\`java
public class PaymentService {
    public void chargeCustomer(...);
    public void refund(...);
    public void reconcile(...);
    public long countPending(...);
}
\`\`\`

Do not attach \`@ManagedOperation\` to all of them just because the operations team wants "more tools."

A dedicated management facade is usually clearer:

\`\`\`java
@Component
@ManagedResource(
    objectName = "com.example.payments:type=Operations,name=Reconciliation"
)
public class PaymentManagement {

    private final PaymentService service;

    public PaymentManagement(PaymentService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending reconciliations")
    public long getPendingCount() {
        return service.countPending();
    }

    @ManagedOperation(description = "Request bounded reconciliation job")
    public String requestReconciliation() {
        return service.submitReconciliation();
    }
}
\`\`\`

Benefits:
- Small management API with a clear owner.
- Easier security review.
- Separates state and actions from service implementation details.
- Easier to inspect JMX metadata.
- Reduces dependence on which methods an AOP proxy exposes.

However, the facade still must validate inputs, rate-limit, and handle exceptions. Calling it a facade does not automatically make an operation safe.

## 14. Read Paths Require Performance Attention

A JMX client may poll \`PendingCount\` every second. If the getter executes a very expensive database query:

\`\`\`java
@ManagedAttribute
public int getPendingCount() {
    return repository.findAll().size(); // Bad example.
}
\`\`\`

it can increase CPU usage, allocations, database load, and application latency.

Better approaches:
- Maintain a counter/snapshot updated by the hot path.
- Use an optimized \`COUNT\` query if exactness is needed.
- Cache the result with a TTL.
- Provide a timestamp/age for the snapshot.
- Limit the polling interval.
- Separate expensive diagnostic operations from frequently polled getters.

Example:

\`\`\`java
private final AtomicInteger pendingSnapshot = new AtomicInteger();

@ManagedAttribute(description = "Latest pending count snapshot")
public int getPendingCount() {
    return pendingSnapshot.get();
}
\`\`\`

Counters/snapshots must have a reliable update source, especially with multiple producers/consumers and across restarts.

## 15. Consistency Across Attributes

Suppose an MBean exposes:
- PendingCount.
- ActiveCount.
- CompletedTotal.
- FailedTotal.

A JMX client may read each attribute at slightly different times. Therefore, do not assume they all form a transactionally consistent snapshot.

If reading multiple values at the same version is required:
- Expose a \`CompositeData\` or a snapshot operation.
- Add \`SnapshotVersion\`/\`SnapshotTime\`.
- Maintain an immutable snapshot object and swap an atomic reference on update.
- Use only the consistency level appropriate for the operational purpose.

Example:

\`\`\`java
public record WorkerSnapshot(
    int pending,
    int active,
    long completed,
    long capturedAtEpochMillis
) {}
\`\`\`

In JavaMXBean/ModelMBean, ensure the representation can be transmitted to JMX clients; do not assume an arbitrary record will always serialize/interoperate as expected. With standalone clients, OpenTypes or scalar attributes are usually easier.

## 16. Security Risks of JMX Management

An MBean can be accessed locally or through a JMX remote connector. Aspects that must be controlled:
- Which network interface the remote connector binds to.
- Authentication, authorization, TLS, or channel protection.
- Who has read, write, and invoke permissions.
- Which operations have production impact.
- Whether returned data contains secrets.
- Whether sensitive actions are audited.
- Whether concurrency limits, timeouts, and retries are in place.

\`@ManagedOperation(description="Admin only")\` does not enforce authorization on its own.

In Spring Boot applications, Actuator JMX exposure properties control **Actuator endpoints**, which does not mean every Spring Framework \`@ManagedResource\` is protected in the same way. You must verify each export and security layer.

## 17. Verifying the Exposed Interface

After enabling Spring JMX export:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Worker,name=OrderProcessor"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

var info = server.getMBeanInfo(name);

System.out.println(info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s type=%s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println("Operation=" + op.getName());
}
\`\`\`

Use the platform server only if the exporter actually registers there. If the application uses a custom \`MBeanServer\`, you must obtain the right reference.

Through \`MBeanInfo\`, verify:
- Are only the intended attributes exposed?
- Is any getter accidentally writable?
- Are there any dangerous operations?
- Do descriptions help operators understand the contract?
- Does notification metadata match the declared types?

## 18. Testing by Operational Use Case

A good test does not only assert that the MBean is registered. It sets up realistic scenarios:

### Backlog Growth Scenario

1. Create 100 simulated jobs.
2. Verify \`PendingCount\` increases as expected.
3. Start processing jobs.
4. Check \`ActiveCount\` and \`ProcessedTotal\`.
5. Verify counter reset semantics.

### Worker Paused Scenario

1. Put the worker into PAUSED state.
2. Check \`State\` and \`IntakePaused\`.
3. Invoke \`resumeIntake()\` via JMX in the test.
4. Verify the worker actually resumes accepting work.
5. Verify the operation cannot run when the caller lacks permissions in the corresponding security test configuration.

### Sensitive Data Scenario

1. Create configuration containing a fake secret.
2. Query \`MBeanInfo\`.
3. Read exposed attributes.
4. Assert the secret does not appear in the output.
5. Verify exceptions do not leak sensitive content.

### High-Frequency Polling Scenario

1. Poll getters at near-production rates.
2. Measure latency and resource usage.
3. Verify getters do not trigger unexpected heavy queries or locks.
4. Adjust sampling/caching if necessary.

These are management API design tests; they are distinct from unit testing the worker's core business logic.

## 19. How Accurate Does Information Need to Be?

Not all management information must be accurate to the nanosecond. A queue count can come from a snapshot a few seconds old if operators know the lag.

Categories include:
- **Exact at read time:** needed for strict control actions.
- **Eventually consistent:** suitable for trends and alerting.
- **Sampled:** suitable for metrics.
- **Snapshot with timestamp:** helps assess freshness.

If an application exposes a stale counter, it should include freshness metadata or a clear description to prevent wrong conclusions.

Examples:
- \`PendingCount\`.
- \`PendingCountCapturedAt\`.
- \`PendingCountAgeSeconds\`.

Never let a stale value be mistaken for a real-time measurement if it could affect operational decisions.

## 20. When to Use Notifications Instead of Polling?

Polling is suitable for:
- Frequently changing counters.
- States requiring periodic updates.
- Dashboards that must resynchronize after reconnecting.

Notifications are suitable for:
- Rare but important state transitions.
- Critical errors needing early warning.
- Administrative task completion.
- Configuration reload failures.

A common combination:
1. Client subscribes to notifications.
2. Notification signals state changed.
3. Client re-reads managed attributes.
4. Client refreshes its snapshot.
5. Upon reconnect, client reads the snapshot even if notifications were missed while offline.

Do not use notifications as a durable audit log. If every event must be retained, use an event store or durable messaging.

## 21. Workflow for Designing a Management API

A pragmatic workflow:

1. **List 5–10 operational questions:** prioritize those currently causing pain.
2. **Select necessary information:** do not blindly expose an entire object graph.
3. **Classify read/write/operation/notification.**
4. **Define semantics:** type, unit, update cadence, reset, freshness.
5. **Assess cost:** avoid slow getters.
6. **Assess risk:** secrets and dangerous operations.
7. **Choose ObjectName:** domain, type, name, instance.
8. **Implement facade:** decouple from business internals where appropriate.
9. **Verify at runtime:** \`MBeanServer\`, \`MBeanInfo\`, actual operations.
10. **Test by scenario:** overload, failure, recovery, unauthorized access.
11. **Document the contract:** so monitoring scripts and operators use it properly.
12. **Review on changes:** avoid breaking compatibility during refactoring.

Anything that neither helps answer an operational question nor supports a worthwhile management action probably does not need to be exposed.

## 22. Anti-Patterns

### 22.1. Exposing Every Public Method

This creates a large management surface, complicates security reviews, and couples clients to implementation details.

### 22.2. Getters with Side Effects

A \`getStatus()\` should not reset counters, trigger external mutations, or initiate task execution. Polling getters can be called repeatedly.

### 22.3. Overly Expensive Getters

Reading \`getPendingCount()\` while actually scanning millions of records degrades performance.

### 22.4. Missing Units and Reset Conditions

\`getLatency()\` returning 500 leaves it unclear whether it is milliseconds or microseconds.

### 22.5. Overly Long Synchronous Operations

Remote clients time out without knowing whether the job started; blind retries may launch duplicate jobs.

### 22.6. Using Notifications as a Durable Event Log

Losing the connection means events can be missed.

### 22.7. Exposing Secrets in Attributes

JMX clients may read and log unintended sensitive data.

### 22.8. ObjectName Changing with Proxy Classes

Spring AOP proxy types and class refactoring make the naming contract unstable.

### 22.9. Not Testing MBeanInfo

Annotations in source code do not prove the exporter actually published the expected interface.

### 22.10. Unmanaged Ownership

Multiple Spring contexts or exporters may register the same ObjectName and cause collisions.

## 23. Hands-on Exercises

### Exercise A — Select Management Information

For a job processing service, list:
- Three questions about state.
- Three useful metrics.
- Two genuinely necessary operations.
- One valuable notification.

Explain why other business methods should not be exposed.

### Exercise B — Design an MBean

Create \`QueueManagement\`:
- \`@ManagedResource\` with a clear ObjectName.
- Read-only \`PendingCount\`, \`ActiveCount\`, \`FailedTotal\`.
- Operations \`pauseIntake\`/\`resumeIntake\`.
- Descriptions clearly stating units and semantics.
- No database entities or secrets exposed.

### Exercise C — Runtime Testing

1. Start the Spring JMX exporter.
2. Obtain the right \`MBeanServer\`.
3. Call \`isRegistered()\` with the ObjectName.
4. Read \`MBeanInfo\`.
5. Assert the expected list of attributes and operations.
6. Assert no unexpected writable attributes exist.

### Exercise D — Performance

1. Create a getter performing a heavy query.
2. Poll the getter repeatedly in a load test.
3. Measure latency.
4. Replace it with a snapshot/cached attribute.
5. Compare latency and freshness.

### Exercise E — Security

1. Create an operation that modifies simulated state.
2. Expose it only via a management facade.
3. Validate inputs and preconditions.
4. Configure corresponding JMX permissions in a test environment.
5. Verify unauthorized callers cannot invoke it.
6. Record an audit entry for the action.

## 24. Self-Check Questions

**Question 1.** Should a good management API expose all Spring beans?  
**Answer:** No. Only expose information and operations that serve clear operational needs.

**Question 2.** Why are read-only attributes usually the first choice?  
**Answer:** They reduce the risk of unintended state modification and suit frequent observation needs.

**Question 3.** What must a counter describe?  
**Answer:** Unit, scope, reset cycle, and update timestamp if applicable.

**Question 4.** What is the problem with a getter that runs a very heavy query?  
**Answer:** Clients may poll continuously, generating load and slowing down the application.

**Question 5.** How should a long-running operation be designed?  
**Answer:** Usually return a job ID and expose status, avoiding holding a remote JMX call open for too long.

**Question 6.** Do JMX notifications guarantee replay after reconnect?  
**Answer:** There is no durable replay by default; clients should re-read snapshots.

**Question 7.** Does \`@ManagedOperation\` automatically grant admin privileges?  
**Answer:** No. Authorization must be enforced at the connector/server or an appropriate layer.

**Question 8.** Why is it necessary to inspect \`MBeanInfo\`?  
**Answer:** To confirm the interface actually exposed at runtime, not just annotations in source code.

## 25. Key Takeaways

- Designing a management API starts from **operational questions**, not from the number of public methods.
- Choose attributes that help diagnose state, metrics, configuration, and progress.
- Prefer read-only, fast-to-read attributes with clear semantics and no secrets.
- Operations must have clear purpose, validation, concurrency controls, and appropriate security.
- Long-running actions should be structured as stateful jobs.
- Notifications signal important events but do not replace durable messaging.
- ObjectNames and management interfaces should remain stable for scripts and dashboards.
- Use a management facade to separate administration from business internals.
- Verify through \`MBeanServer\`, \`MBeanInfo\`, and integration tests.
- Information that neither aids operational decisions nor mitigates risk should not be exposed.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 API — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

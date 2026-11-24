# Naming Attributes and Operations for Stable Semantics in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Understand why JMX attribute and operation names form a **public management contract** between the application and JMX clients.
- Distinguish between Java method names, JMX attribute names, JMX operation names, and MBean ObjectNames.
- Choose meaningful names that are consistent in quantity, unit, scope, state, and effect.
- Maintain compatibility when refactoring classes, methods, or changing application structure.
- Avoid ambiguous names such as \`Status\`, \`Count\`, \`Run\`, and \`Reset\` without context.
- Design a naming strategy, management facade, aliases, and migration policy for contract changes.
- Write \`MBeanInfo\` tests to catch unintended changes to attribute names, operation names, or signatures.
- Distinguish management API naming principles from internal variable names and metric names in other observability systems.

## 1. Why Do JMX Names Matter?

A JMX client may call:

\`\`\`java
Object count = connection.getAttribute(
    objectName,
    "PendingJobs"
);
\`\`\`

or:

\`\`\`java
Object result = connection.invoke(
    objectName,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

The strings \`PendingJobs\` and \`pauseProcessing\` are used by clients as an **API contract**. They may appear in:

- JConsole or VisualVM.
- Monitoring collectors.
- Operational scripts.
- SRE automation.
- Alerts and dashboards.
- Incident response runbooks.
- Integration tests.
- Management tools located outside the application's repository.

Renaming an exported Java method can break these consumers, even if the IDE automatically updates every call site in the source code.

**Principle:** JMX names must reflect stable management semantics rather than coupling tightly to changing implementation terminology.

## 2. Three Different Kinds of Names

Example:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueManagement {

    @ManagedAttribute
    public int getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void pauseProcessing() {
        service.pause();
    }
}
\`\`\`

We have:

| Element | Example | Role |
|---|---|---|
| Java class | \`QueueManagement\` | Type in source code |
| Java accessor | \`getPendingJobs()\` | Implementation method |
| JMX attribute name | \`PendingJobs\` | String passed to \`getAttribute\` |
| Java management method | \`pauseProcessing()\` | Annotated method |
| JMX operation name | \`pauseProcessing\` | String passed to \`invoke\` |
| MBean ObjectName | \`learning.jmx:type=QueueManagement,name=Primary\` | Resource identifier in \`MBeanServer\` |

The Java class name does not have to match the ObjectName. Attributes and operations are separate members inside the MBean.

### Why Not Just Use Class Names?

Refactoring \`QueueManagement\` to \`QueueAdministration\` does not necessarily change what JMX clients need to observe. If the ObjectName and management contract remain stable, clients do not need to know about the new code organization.

## 3. Designing Attribute Names Around Stable Quantities

An attribute typically describes an **observable state or quantity**.

Examples:

\`\`\`text
PendingJobs
ActiveConnections
CompletedRequests
ErrorCount
QueueCapacity
RetryDelayMillis
Paused
LastSuccessfulRefreshEpochMillis
\`\`\`

A good attribute name usually answers these questions:

1. **What quantity?** Job, request, connection, or task?
2. **What state?** Pending, active, completed, failed?
3. **What scope?** This queue, this pool, or the entire application?
4. **What unit?** Count, bytes, milliseconds, percentage?
5. **Freshness/source of value?** Snapshot or real-time figure?
6. **Are semantics stable?** Once published, can the name be preserved across many releases?

The name \`Count\` in an MBean with multiple quantities is easily misunderstood. \`PendingJobs\` expresses the meaning much more clearly.

### Do Not Overuse Abbreviations

Compare:

\`\`\`text
QSz
ReqCnt
ConnAct
\`\`\`

with:

\`\`\`text
QueueDepth
RequestCount
ActiveConnections
\`\`\`

Clear names help scripts, operators, and newcomers understand the meaning without decoding abbreviations.

Widely accepted abbreviations such as CPU, JVM, and GC may be kept if the team has a consistent naming convention. What to avoid are internal, volatile abbreviations.

## 4. Attribute Names and Accessor Rules

In Spring Framework, \`@ManagedAttribute\` is typically placed on a JavaBeans getter or setter.

Example:

\`\`\`java
@ManagedAttribute
public long getCompletedRequests() {
    return completed.get();
}
\`\`\`

The exposed attribute is normally \`CompletedRequests\`.

For a boolean:

\`\`\`java
@ManagedAttribute
public boolean isPaused() {
    return paused;
}
\`\`\`

The attribute is normally \`Paused\`.

A getter/setter pair:

\`\`\`java
@ManagedAttribute
public int getMaxConnections() {
    return maxConnections;
}

@ManagedAttribute
public void setMaxConnections(int value) {
    validateLimit(value);
    maxConnections = value;
}
\`\`\`

can produce a readable/writable \`MaxConnections\` attribute when configured with the appropriate exporter/assembler.

**Note:** In Spring, \`@ManagedAttribute\` has no \`name\` element to assign an arbitrary JMX name directly. If you want to keep the \`CompletedRequests\` attribute, the clearest approach is to preserve the corresponding accessor on a management facade or configure an appropriate metadata strategy.

## 5. Naming by Unit and Data Type

A management API can be misinterpreted when the same attribute name uses a different unit.

Examples of unclear names:

\`\`\`text
Timeout
Latency
Size
Usage
\`\`\`

Clearer alternatives:

\`\`\`text
ConnectionTimeoutMillis
RequestLatencyMillis
CacheSizeBytes
CpuUsagePercent
\`\`\`

Depending on JMX conventions, names may use suffixes such as \`Millis\`, \`Seconds\`, \`Bytes\`, \`Percent\`, or describe the unit in metadata. When compatibility across diverse clients is needed, putting the unit directly in the name is beneficial.

### Changing Units Is a Semantic Breaking Change

Suppose:

\`\`\`java
@ManagedAttribute
public long getConnectionTimeoutMillis() {
    return 5000L;
}
\`\`\`

If you change the implementation to return 5 seconds while keeping the name \`ConnectionTimeoutMillis\`, clients receive semantically wrong data.

If switching from milliseconds to seconds, you should:

- Keep the old attribute returning milliseconds.
- Expose a new attribute \`ConnectionTimeoutSeconds\` if genuinely needed.
- Announce and test the migration.
- Never silently change units under the old name.

For ratios, distinguish between 0–1 and 0–100. \`CpuUsagePercent\` should have different semantics from \`CpuUsageRatio\`, and metadata must reflect that accurately.

## 6. Naming Based on Actual State

A boolean attribute should express a verifiable condition.

Good examples:

\`\`\`text
Paused
Healthy
AcceptingRequests
CircuitBreakerOpen
ShutdownRequested
\`\`\`

Potentially ambiguous examples:

\`\`\`text
Status
Enabled
Active
Ready
\`\`\`

\`Ready\` could mean the service has initialized, is accepting requests, has loaded its cache, or has full connectivity to dependencies. If a short name is used, define its semantics in the description and keep it stable.

Example:

\`\`\`java
@ManagedAttribute(
    description = "Whether this queue accepts new jobs"
)
public boolean isAcceptingJobs() {
    return state.acceptingJobs();
}
\`\`\`

The name \`AcceptingJobs\` usually carries more concrete meaning than a generic boolean \`Active\`.

## 7. Operation Names Must Express Action

Unlike attributes, which represent observable data, operations represent actions.

Examples:

\`\`\`text
pauseProcessing
resumeProcessing
clearCache
refreshConfiguration
requestIndexRebuild
resetStatistics
rotateCredentials
\`\`\`

Prefer **verb + object**:

- \`pauseProcessing\` instead of \`pause\` if the MBean manages multiple components.
- \`resetStatistics\` instead of \`reset\` if resetting could also apply to connections or caches.
- \`refreshConfiguration\` instead of \`update\`, which leaves unclear what is updated.
- \`requestIndexRebuild\` if the operation only submits an asynchronous request and does not wait for the rebuild to finish.

Operation names must accurately reflect execution semantics.

### Names Must Distinguish Request from Completion

Suppose an operation:

\`\`\`java
@ManagedOperation
public String startRebuild() {
    executor.execute(indexService::rebuild);
    return "ACCEPTED";
}
\`\`\`

If the method only enqueues the task, \`requestRebuild\` or \`startRebuild\` is clearer than \`rebuildNow\`, which would lead users to expect the rebuild is finished when the call returns.

The contract should state clearly:

- Does the return value mean accepted/rejected or business completion?
- Is there a job ID?
- Is progress status exposed via another attribute?
- Can it be invoked again while already running?
- Does a client timeout cancel the work?

## 8. Do Not Name After Temporary Implementations

Suppose a service previously used Redis:

\`\`\`java
@ManagedAttribute
public int getRedisQueueSize() {
    return redisQueue.size();
}
\`\`\`

Later the team migrates to another queue backend. JMX clients still need to know the backlog, not necessarily the underlying storage technology.

If the contract is meant to reflect logical backlog, \`PendingJobs\` or \`QueueDepth\` is more stable than \`RedisQueueSize\`.

However, if the attribute specifically measures **a Redis-specific characteristic** (such as key count or Redis connection state), including the technology name is more accurate. Do not rename to something "generic" if it strips away the real meaning.

**Principle:** Name according to the nature of the data or operation clients need, not implementation details outside the contract.

## 9. Management Facades Help Keep Naming Stable

A sound design pattern is separating the management API from the business service.

Service:

\`\`\`java
public interface JobService {
    long pendingCount();
    boolean acceptingJobs();
    void suspendNewJobs();
}
\`\`\`

Facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=JobManagement,name=Primary",
    description = "Stable job management API"
)
public class JobManagement {

    private final JobService service;

    public JobManagement(JobService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Number of waiting jobs")
    public long getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedAttribute(description = "Whether new jobs are accepted")
    public boolean isAcceptingJobs() {
        return service.acceptingJobs();
    }

    @ManagedOperation(description = "Stop accepting new jobs")
    public void pauseProcessing() {
        service.suspendNewJobs();
    }
}
\`\`\`

Benefits:

- \`JobService.pendingCount()\` can be renamed without changing \`PendingJobs\`.
- The backend can be replaced while clients keep using the logical management contract.
- The \`pauseProcessing\` operation is named after the management behavior.
- The fixed ObjectName does not depend on the Spring bean name or Java class name.
- Other internal methods are not accidentally exported as operations.

Spring configuration:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    JobManagement jobManagement(JobService jobService) {
        return new JobManagement(jobService);
    }
}
\`\`\`

This configuration assumes \`JobService\` is already provided as a Spring bean and the exporter has an appropriate \`MBeanServer\`. In applications where Spring Boot JMX auto-configuration is active, avoid creating duplicate exporters for the same resource.

## 10. Avoid Names Generated from Runtime Proxies

When Spring AOP is active, a Spring bean may be a JDK dynamic proxy or a class-based proxy.

Do not derive an ObjectName from:

\`\`\`java
bean.getClass().getSimpleName()
\`\`\`

because the runtime class may be a dynamically generated proxy class that varies with framework configuration.

Define the ObjectName after the logical resource:

\`\`\`text
learning.jmx:type=JobManagement,name=Primary
\`\`\`

Attributes and operations should also rely on an intentional management facade or management interface rather than whatever methods happen to appear on a proxy.

If an operation needs transactional or security advice, the facade should call the Spring-managed service proxy; do not bypass the proxy just to simplify JMX metadata.

## 11. When Does Renaming a Java Method Cause a Breaking Change?

Initial code:

\`\`\`java
@ManagedAttribute
public long getQueuedTasks() {
    return service.pendingCount();
}
\`\`\`

JMX attribute: \`QueuedTasks\`.

After refactoring:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return service.pendingCount();
}
\`\`\`

The JMX attribute may become \`PendingJobs\`, even though the value has not changed.

An existing client:

\`\`\`java
connection.getAttribute(name, "QueuedTasks");
\`\`\`

may encounter \`AttributeNotFoundException\` after deployment.

A method rename inside the repository can be handled by an IDE, but external JMX scripts and monitoring systems do not update automatically.

### Transition Options

**Keep the old management name:**

\`\`\`java
@ManagedAttribute
public long getQueuedTasks() {
    return service.pendingCount();
}
\`\`\`

This is usually the best choice when semantics have not changed and existing clients still depend on it.

**Expose a controlled alias:**

\`\`\`java
@ManagedAttribute
public long getQueuedTasks() {
    return service.pendingCount();
}

@ManagedAttribute
public long getPendingJobs() {
    return service.pendingCount();
}
\`\`\`

When the exporter publishes both, old and new clients can operate side by side. Document the canonical name and any planned removal schedule for the old alias.

**Planned breaking change:** If semantics have genuinely changed, introduce a new attribute, announce versioning/migration, and do not pretend the old name retains the same meaning.

## 12. Renaming Operations Is Also a Breaking Change

Initially:

\`\`\`java
@ManagedOperation
public void clearStatistics() {
    service.resetCounters();
}
\`\`\`

Client calls:

\`\`\`java
connection.invoke(
    name,
    "clearStatistics",
    new Object[0],
    new String[0]
);
\`\`\`

If renamed to \`resetCounters()\` and only the new name is published, existing clients can no longer find the operation.

You can keep a compatibility wrapper:

\`\`\`java
@ManagedOperation
public void clearStatistics() {
    service.resetCounters();
}
\`\`\`

and publish a new operation under a migration plan if needed.

Avoid keeping two aliases indefinitely without documenting semantics, security, and auditing; having two different names trigger the same side effect complicates monitoring and auditing.

## 13. Signatures Are Part of the Operation Contract

The operation name is only part of it. JMX \`invoke\` also uses the signature.

Example:

\`\`\`java
@ManagedOperation
public void setQueueLimit(int limit) {
    service.setLimit(limit);
}
\`\`\`

Client:

\`\`\`java
connection.invoke(
    name,
    "setQueueLimit",
    new Object[] { 200 },
    new String[] { "int" }
);
\`\`\`

If the Java parameter type changes from \`int\` to \`long\`, the operation name stays the same, but the signature changes to \`long\`.

Some clients passing \`"int"\` per the old contract will fail. Treat parameter types and signatures as an inseparable part of the management API.

For operations requiring a parameter type change, consider introducing a new name or overload with a clear migration path, and test using \`MBeanInfo\`.

## 14. Setter Names and Write Access

An attribute is readable and also becomes writable via JMX if the exporter publishes a setter.

Example:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int newValue) {
    validate(newValue);
    maxWorkers = newValue;
}
\`\`\`

The attribute name remains \`MaxWorkers\`, but the contract now includes a writable property.

Adding a setter is not merely a convenience improvement. It expands the management surface and requires authorization. If the requirement is observation only, keep it read-only.

Avoid turning operations with side effects into getters. For example, a \`getRebuiltIndex()\` method that rebuilds an index is an anti-pattern because monitoring tools may call getters repeatedly.

## 15. Naming Conventions for Attribute Groups

A large system needs consistency.

Example queue group:

\`\`\`text
QueueDepth
QueueCapacity
PendingJobs
ProcessedJobs
FailedJobs
AcceptingJobs
LastProcessedAtEpochMillis
\`\`\`

Connection pool group:

\`\`\`text
ActiveConnections
IdleConnections
MaxConnections
ConnectionAcquireTimeoutMillis
ConnectionFailures
\`\`\`

Cache group:

\`\`\`text
EntryCount
HitCount
MissCount
EvictionCount
EstimatedSizeBytes
\`\`\`

For the same concept, the team should standardize on one term. Do not use \`PendingJobs\` in MBean A and \`WaitingTasks\` in MBean B if both share identical semantics without a good reason.

### Do Not Lump Everything Under Count

\`Count\`, \`Total\`, and \`Size\` are not strictly synonymous:

- \`Count\` typically indicates a quantity.
- \`Total\` may represent a cumulative figure since a starting point.
- \`Size\` may mean number of elements or number of bytes, depending on context.
- \`Rate\` typically represents an amount per unit of time.

Names must express the exact quantity. For example, \`RequestCount\` is a counter, whereas \`RequestsPerSecond\` is a rate.

## 16. Naming Time-Related State

An attribute named \`LastRefresh\` can be ambiguous as to whether it holds a timestamp, elapsed time since refresh, or duration of the refresh.

Clearer names:

\`\`\`text
LastRefreshEpochMillis
SecondsSinceLastRefresh
LastRefreshDurationMillis
\`\`\`

Also document the timezone and reference clock in the documentation.

If using timestamps in epoch milliseconds, ensure the type is wide enough (typically \`long\`). If measuring duration, do not give it a name that looks like an absolute timestamp.

When a name cannot convey every nuance, use \`description\` for specific semantics; however, a description should not be used to excuse an overly vague name.

## 17. What Not to Do

| Anti-pattern | Problem | Better Alternative |
|---|---|---|
| Attribute \`Data\` | Unclear quantity | \`QueueDepth\`, \`ProcessedJobs\` |
| Operation \`doIt\` | Unclear action/effect | \`refreshConfiguration\` |
| \`getStatus()\` returning huge JSON | Both vague and expensive | Specific attributes or bounded snapshot |
| \`reset()\` on multi-part MBean | Unclear what gets reset | \`resetStatistics\` |
| Changing unit while keeping name | Clients misread data | Unit-suffixed name or migration |
| Changing getter during refactor | Attribute unintentionally renamed | Keep facade/compatibility getter |
| Using proxy class name as ObjectName | Unstable name | Fixed logical ObjectName |
| Operation named \`rebuildNow\` that only enqueues | Behavior contradicts expectations | \`requestRebuild\` |
| Getter causing side effects | Polling triggers dangerous action | Convert to operation |
| Unannounced rename of old name | Breaks scripts | Deprecation/migration policy |

## 18. Testing the Contract with MBeanInfo

JMX clients see what \`MBeanServer\` exposes, not every source-code detail.

Example:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Arrays;

import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=JobManagement,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

boolean pendingJobsExists = Arrays.stream(
    info.getAttributes()
).anyMatch(a ->
    "PendingJobs".equals(a.getName())
    && "long".equals(a.getType())
    && a.isReadable()
);

boolean pauseExists = Arrays.stream(
    info.getOperations()
).anyMatch(o ->
    "pauseProcessing".equals(o.getName())
    && o.getSignature().length == 0
);

if (!pendingJobsExists || !pauseExists) {
    throw new IllegalStateException(
        "Unexpected JMX management contract"
    );
}
\`\`\`

If \`MBeanExporter\` uses a custom \`MBeanServer\`, obtain that server rather than assuming the platform server. In another JVM, clients need an \`MBeanServerConnection\` via a connector.

### Why Is MBeanInfo the Source of Truth?

An annotated getter when the exporter is not enabled produces no JMX attribute.

A properly named method that the assembler does not expose cannot be invoked by clients.

An AOP proxy may cause exposed metadata or invocable methods to differ from expectations.

\`MBeanInfo\` verifies the actual ObjectName, names, types, readable/writable semantics, and operation signatures that were exported.

## 19. Versioning and Deprecation Policy

JMX does not natively version via HTTP REST paths. A management API still needs a compatibility strategy.

For example, an old name:

\`\`\`text
CompletedJobs
\`\`\`

is replaced by:

\`\`\`text
ProcessedJobs
\`\`\`

A process can be:

1. Identify consumers using the old name.
2. Add the new attribute if semantics genuinely require it.
3. During the transition period, retain the old attribute when possible.
4. Mark the canonical name in documentation.
5. Update monitoring rules, alerts, and scripts.
6. Test both old and new names during the compatibility window.
7. Remove the old name only according to an announced change plan.

Do not create a \`version=2\` ObjectName for every minor refactor when preserving compatibility solves the problem. However, if the contract changes incompatibly, versioned MBeans or an explicit migration can be justified.

## 20. Distinguishing JMX Naming from Metric Naming

Micrometer/Prometheus and JMX both serve observability, but they have different naming models.

JMX example:

\`\`\`text
ObjectName: learning.jmx:type=QueueMetrics,name=Primary
Attribute: PendingJobs
\`\`\`

Metrics may use different naming and tag/label conventions.

You do not need to force a JMX attribute name to match a metric name verbatim. What matters is **consistent semantics and units** so the two sources do not cause confusion.

If a JMX getter and a metrics gauge read the same state, use a single business data source or shared snapshot rather than two calculations with differing definitions.

## 21. Real-World Scenarios

### Scenario A — Team Renames "jobs" to "tasks"

In internal code, \`pendingJobCount()\` is renamed to \`waitingTaskCount()\`.

If the \`PendingJobs\` JMX attribute is already used in dashboards, you can keep \`getPendingJobs()\` on the management facade and delegate to the new implementation.

If the concept of a task truly differs from a job, design a new attribute with clear semantics rather than assuming the two names are equivalent.

### Scenario B — Pool Changes Timeout Unit

Previously \`ConnectionTimeout\` returned milliseconds. After a library upgrade, the internal API returns seconds.

Do not return seconds under the old name without converting. Prefer \`ConnectionTimeoutMillis\` while keeping values in the expected unit, or perform a formal migration.

### Scenario C — Operation Only Enqueues Work

An operation named \`rebuildIndex()\` used to be synchronous; a new version becomes asynchronous.

Review the contract regarding completion and response. If the call now only returns accepted, documentation must clarify this; consider exposing \`requestIndexRebuild\` and job status instead of keeping misleading semantics.

### Scenario D — Automated JMX Client

A script calls \`pauseProcessing\`. A developer renames it to \`stopProcessing\` during a refactor.

If both behaviors are equivalent, a compatibility wrapper can protect the script. If \`stop\` permanently halts rather than pausing reversibly, that is a semantic change and should not be aliased unconditionally.

### Scenario E — ObjectName Generated from a Spring Proxy

Spring enables transactional AOP and the runtime class name changes. A naming strategy based on runtime class creates a new ObjectName, causing the JMX collector to lose sight of the old name.

Keeping a fixed logical ObjectName and a management facade avoids coupling to the proxy implementation.

## 22. Pre-Release Checklist for a Management API

1. Does the attribute name express a concrete quantity and state?
2. Are unit suffixes like \`Millis\`, \`Bytes\`, or \`Percent\` needed?
3. Does the data type match the unit and value range?
4. Do semantics remain stable across internal refactoring?
5. Is the getter read-only or writable as required?
6. Does the getter avoid side effects and heavy work?
7. Does the operation name have a clear verb and object?
8. Does the sync/async nature match the name and documentation?
9. Are signatures and result semantics documented clearly?
10. Is the ObjectName stable and independent of proxy classes?
11. Are there external consumers outside the repository requiring compatibility?
12. Is there an \`MBeanInfo\` integration test for the contract?
13. Is there a migration plan if renaming or changing units?
14. Is authorization enforced for operations and writable attributes?
15. Are secrets and sensitive data kept out of the management API?

## 23. Hands-on Exercises

### Exercise 1 — Evaluate Names

Given an MBean with these attributes:

\`\`\`text
Count
Status
Timeout
Data
Active
\`\`\`

Propose more specific names in the context of a connection pool. Explain what each name expresses and its unit.

### Exercise 2 — Safe Refactoring

You have \`getWaitingTasks()\` exposing \`WaitingTasks\`. The service renames its internal method from \`waitingCount()\` to \`pendingCount()\`. Write a management facade that preserves the old JMX attribute.

### Exercise 3 — Naming Operations

Rename:

\`\`\`text
run
reset
update
doAction
\`\`\`

to purposeful names for a cache and a scheduler. Explain when an operation that only enqueues work needs a \`request\`/\`start\` prefix.

### Exercise 4 — Detecting a Breaking Change

Initially, clients invoke \`setQueueLimit\` with signature \`int\`. After refactoring, the operation accepts \`long\`. Write an \`MBeanInfo\` test that detects the signature change and outline a migration approach.

### Exercise 5 — Read/Write Contract

Initially \`MaxWorkers\` is read-only. A patch adds a setter, making it writable. Inspect \`MBeanAttributeInfo.isWritable\` and describe the management risks.

## 24. Key Takeaways

- **Attribute and operation names are a public management API contract.**
- Attributes should express quantities/states; operations should express actions/effects.
- Units, data types, signatures, and semantics matter just as much as names.
- Do not name after volatile implementation details when clients need stable logical semantics.
- Refactoring exported Java methods can break JMX clients referencing names as strings.
- A management facade and compatibility aliases decouple the JMX contract from internal services.
- Verify \`MBeanInfo\` after export, not just annotations in source code.
- When the contract must change, use explicit migration/versioning instead of silent renames.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 API — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 API — MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html

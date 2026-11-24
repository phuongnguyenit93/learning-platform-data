# Defining Management Goals Before Creating an MBean in Spring Framework JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **genuine management needs** from simply exposing additional Java methods via JMX.
- Identify who uses the MBean, what they need to observe or control, in which environment, and to resolve which incidents.
- Categorize requirements into **monitoring**, **diagnostics**, **configuration**, and **operational control** before designing attributes/operations.
- Write verifiable goals, such as reducing queue backlog diagnosis time or allowing a consumer to be paused safely.
- Decide when to use JMX instead of Micrometer, Spring Boot Actuator, an HTTP management API, logs, or a dedicated job system.
- Evaluate data scope, read frequency, latency, side effects, security, concurrency, lifecycle, and compatibility.
- Translate operational goals into concrete **ObjectName**, attributes, operations, signatures, descriptions, and acceptance tests.
- Avoid creating oversized MBeans, exposing unnecessary service methods, or turning the management interface into a gateway for dangerous task execution.

## 2. Why Define Goals Before Creating an MBean?

In Spring Framework, a Java bean can be exposed as a JMX MBean using `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`. However, technical capability does not mean every bean should be exposed.

For example, a service with these methods:

```java
public class OrderService {
    public Order findById(String id);
    public List<Order> findAll();
    public void retryFailedOrders();
    public void clearAllOrders();
    public void updatePaymentToken(String token);
}
```

If the entire service is exported just to monitor the number of pending orders, the system inadvertently creates a large management surface, difficult access control, and data exposure risks. Meanwhile, the actual goal might simply be:

> When the queue backs up, operators need to know the pending item count, the age of the oldest item, the worker status, and the last error timestamp to decide whether intervention is needed.

That goal fits a few small, read-only attributes; there is no need to export `findAll()` or `clearAllOrders()`.

**Principle:** start from the decision the operator needs to make, then identify the minimal required data/actions. Do not start from the list of public methods on a class.

## 3. Positioning JMX in the Operations Landscape

A Spring system typically has multiple observability and management mechanisms:

| Need | Typically Suitable Mechanism | Remarks |
| --- | --- | --- |
| Long-term counter/gauge tracking | Micrometer + metrics backend | Provides charts, alerts, retention, and aggregation. |
| Health/readiness | Spring Boot Actuator or health system | Suitable for liveness, readiness, and orchestration. |
| Immediate JVM/runtime inspection | JMX platform MBeans, JConsole | Threads, memory, GC, class loading. |
| Compact internal state inspection | Custom JMX MBean | Useful when operational values inside the JVM are needed. |
| Intentional local control | Protected JMX operation | Requires authorization, validation, and audit. |
| Multi-record data querying | API with pagination and access control | Should not use JMX getters returning large object graphs. |
| Long-running, multi-stage tasks | Job queue/Spring Batch/scheduler | JMX can only submit commands, return a job ID, and read status. |
| Incident history investigation | Structured logs/tracing | JMX usually provides a snapshot, not a replacement for event history. |

A single need does not necessarily require picking only one tool. A queue depth can be both a metric and a JMX attribute for direct diagnostics. However, there should be **one logical data source** and appropriate views rather than recomputing an expensive query across every channel.

## 4. Four Categories of Management Goals

### 4.1. Monitoring — periodic observation

Examples:

- `QueueDepth`: number of items waiting.
- `Running`: whether the worker is active.
- `ProcessedTotal`: number of items processed since startup.
- `LastSuccessfulRunEpochMillis`: timestamp of the last successful run.

Characteristics: read frequently, low cost, prefer read-only, stable semantics.

### 4.2. Diagnostics — root-cause analysis

Examples:

- Most recent error by sanitized code.
- Most recent retry timestamp.
- Number of busy threads and queue saturation.
- Connector or dependency status checked in the background.

Characteristics: requires more detail than metrics, while still limiting payloads and sensitive information. If detailed traces or stack traces are needed, direct operators to logs/tracing instead of exposing raw large data via an MBean.

### 4.3. Configuration — tuning parameters

Examples:

- Worker count limit.
- Toggle diagnostics sampling on/off.
- Adjust an internal alert threshold.

Characteristics: writable attributes with validation, clear permission boundaries, concurrency control, and a mechanism to reflect the applied value.

### 4.4. Operational control — executing actions

Examples:

- `requestPause()`.
- `requestResume()`.
- `requestCacheRefresh()`.
- `requestReindex()`.

Characteristics: has side effects, must identify the actor, approval workflow if needed, idempotency, result status, audit, and recovery steps.

Do not lump all four goals into one giant MBean just because they belong to the same service class.

## 5. Starting from a Concrete Operational Scenario

Consider a scenario where a file import system has a backlog:

```text
Symptom:
  File processing time increases from 1 minute to 12 minutes.

Operator questions:
  Is the worker still running?
  How many items remain in the queue?
  How long has the oldest item been waiting?
  What category does the most recent error belong to?
  Can it be paused to inspect downstream?

Decision:
  Continue monitoring / scale capacity / pause / escalate.
```

From there, form a goal:

> Allow operators to determine within a short time whether the delay is due to queue saturation, a stopped worker, or downstream failure, while providing only controlled pause/resume actions.

The goal must link to concrete information/actions rather than vaguely stating "improve observability".

## 6. Pre-Code Design Questionnaire

| Question | Example Answer | Design Implication |
| --- | --- | --- |
| Who uses it? | On-call/SRE | Identifies roles and tools. |
| What decision do they need to make? | Whether to pause the importer? | Focuses on actionable information. |
| When is it accessed? | During backlog spikes or alerts | Defines polling frequency and SLA. |
| How fresh must the data be? | Snapshot updated every 5 seconds | Determines caching/sampling. |
| Sensitive data? | Error codes may contain request IDs | Sanitize, do not export payloads. |
| What does the action change? | Stops accepting new work, does not cancel running jobs | Requires documented semantics. |
| Who has permission to invoke the operation? | Only authorized operators | Security policy and tests. |
| Can it be called repeatedly? | `requestPause` is idempotent | Design safe retries. |
| What if the operation fails? | Returns defined status/exception | Logging and audit. |
| Are multiple instances needed? | Each Pod has its own worker | Distinguish local instance vs. cluster. |
| Do version upgrades have impact? | Dashboards depend on attribute names | Keep the contract stable. |

Answer these questions before choosing annotations or an assembler.

## 7. Turning Goals into Verifiable Requirements

A vague requirement:

```text
Expose worker information through JMX.
```

A better requirement:

```text
REQ-01: Operator reads QueueDepth of type long in the importer MBean.
REQ-02: Running of type boolean, read-only.
REQ-03: OldestQueuedAgeSeconds of type long, non-negative.
REQ-04: Getters do not query the entire database and meet the latency budget.
REQ-05: Only the control group can invoke requestPause().
REQ-06: requestPause() does not cancel running tasks; returns quickly.
REQ-07: No API to read full payloads or delete data via JMX.
REQ-08: MBean is unregistered when the Spring context closes.
```

These criteria align design, testing, and review. Specific latency thresholds should be based on environment load and project requirements, rather than picking an arbitrary nice number on paper.

## 8. Designing ObjectName from Usage Goals

JMX identifies MBeans via `ObjectName`, for example:

```text
com.example.import:type=Worker,name=Primary
com.example.import:type=Queue,name=Retry
com.example.import:type=Maintenance,name=Index
```

Use these conventions:

- Domain by application or module.
- `type` describes the resource kind.
- `name` describes the logical instance/resource.
- Stable key properties, containing no secrets or PII.
- Avoid values dependent on runtime proxy class names.
- Limit unbounded growth of dynamic ObjectNames.

Within the same `MBeanServer`, an ObjectName can only register one MBean at a time. Across different JVMs, the same ObjectName can appear without conflict.

**Design per instance or cluster-wide?** A custom MBean inside a JVM reflects only that instance's state unless the implementation actively aggregates cluster data. Naming it `GlobalStatus` does not automatically make the metrics cluster-wide.

## 9. Choosing Attribute or Operation?

### Prefer an attribute when

- The value is readable state/metrics.
- No input parameters are needed.
- It can be read repeatedly without changing state.
- Read cost is small and predictable.
- Monitoring tools need to poll it.

Example:

```java
@ManagedAttribute(description = "Queued items (count)")
public long getQueueDepth() {
    return metrics.queueDepth();
}
```

### Prefer an operation when

- The action has side effects.
- Parameters are required to trigger work.
- There is request/result status to observe.
- Explicit validation and error handling are needed.

Example:

```java
@ManagedOperation(
    description = "Request graceful pause; does not cancel running jobs"
)
public void requestPause() {
    controlService.requestPause();
}
```

Do not turn a simple metric retrieval into an operation requiring `invoke`, especially when monitoring accounts only have readonly access on the remote connector. Conversely, do not turn an important configuration-changing action into a getter with side effects.

## 10. Deciding Data Types and Payload Size

JMX is generally easiest to use when returning small, clear types:

```text
boolean  Running
long     QueueDepth
long     ProcessedTotal
double   AverageLatencyMillis
String   StatusCode
String   LastErrorType
```

If a structured snapshot is needed, consider Open Types or MXBean mapping when clients are compatible. Do not assume domain DTOs, JPA entities, `Future`, `Stream`, or arbitrary object graphs make good JMX contracts.

Avoid:

```java
@ManagedAttribute
public List<Order> getAllPendingOrders() {
    return repository.findAllPending();
}
```

Replace with:

```java
@ManagedAttribute
public long getPendingOrderCount() {
    return metrics.pendingCount();
}
```

If a detailed list is needed, use a dedicated API with pagination/authorization rather than fetching everything through a JMX getter. `CompositeData` and `TabularData` only help describe structure; they do not make very large payloads safe.

## 11. Defining Semantics and Units Upfront

Under-specified names cause misunderstandings:

```text
Latency = 250
Age = 30
Size = 1024
```

Name them instead:

```text
AverageLatencyMillis = 250.0
OldestQueuedAgeSeconds = 30
HeapUsedBytes = 1024
```

For counters, clearly document whether they count from JVM start or from the last reset. For ratios, specify range `[0,1]` or percentage `[0,100]`. For timestamps, use UTC ISO-8601 or epoch milliseconds with a unit-descriptive name.

Example description:

```java
@ManagedAttribute(
    description = "Age of the oldest queued item in seconds"
)
public long getOldestQueuedAgeSeconds() {
    return metrics.oldestQueuedAgeSeconds();
}
```

Descriptions must serve human operators and automated clients, not merely act as decorative text.

## 12. Real-Time Freshness and Read Cost

Every time a client calls `getAttribute`, the MBean's getter actually executes. If the getter queries the database, calls downstream services, or holds a lock for a long time, monitoring reads can degrade application performance.

A well-defined management goal specifies:

- Expected polling frequency.
- Getter latency budget.
- Whether a few seconds of data lag is acceptable.
- Whether metrics are updated by events or a sampler.
- CPU/I/O/GC cost.
- Behavior when downstream is unresponsive.

A safe design often reads from a **background-updated snapshot**:

```java
@ManagedAttribute(description = "Cached pending count")
public long getPendingCount() {
    return snapshot.get().pendingCount();
}
```

For example, `snapshot` can be an `AtomicReference<MetricsSnapshot>` updated by a sampler. Data freshness must be defined, without masking a stale snapshot by returning 0.

## 13. Defining the Security Surface Before Exporting

Spring JMX annotations such as `@ManagedAttribute` or `@ManagedOperation` do not grant roles on their own. You must distinguish:

```text
Export surface:
    What is present in MBeanInfo?

Authorization:
    Which callers can getAttribute/setAttribute/invoke?

Transport security:
    Who can connect, and how is the connection protected?
```

For remote JMX, appropriate authentication, TLS/network restrictions, and authorization are required. The JDK's readonly/readwrite access file mechanism is typically coarse-grained; when per-ObjectName/per-operation permissions are needed, dedicated enforcement such as `MBeanServerForwarder` or gateway/service authorization is required.

**Spring Security HTTP does not automatically protect the JMX/RMI connector.** Nor should `INFO` impact metadata be treated as proof that an operation is safe or as an authorization rule.

## 14. Separating Read-Only Monitoring from Control

For goals involving both observation and control, one organizational approach:

```text
com.example.import:type=Worker,name=PrimaryStatus
  Attributes:
    Running
    QueueDepth
    OldestQueuedAgeSeconds

com.example.import:type=Worker,name=PrimaryControl
  Operations:
    requestPause()
    requestResume()
```

Splitting into two MBeans makes reviewing the management surface easier, enables clear allowlists, and allows exporting the control MBean only in permitted environments.

However, **separating ObjectNames does not create authorization** if the connector still grants a readwrite account broad access across the entire server. Policy must be enforced at the appropriate layer.

## 15. Designing State-Mutating Operations

Before creating the `requestPause()` operation, you must answer:

1. Does pause mean stop accepting new jobs or also stop in-flight jobs?
2. Are repeated calls safe (idempotent)?
3. Does it return when the request is accepted or when all workers have stopped?
4. If a worker fails to stop, what state does the operator read?
5. Are there timeouts and recovery steps?
6. Who is authorized to invoke it?
7. Is it audited?
8. If the caller disconnects right after sending the command, can the result still be checked?

Example contract:

```text
requestPause() -> boolean
    true: pause request accepted
    false: request rejected due to business state

getControlState() -> String
    RUNNING | PAUSE_REQUESTED | PAUSED | FAILED
```

The key is to define the boolean clearly, without using `true` to imply both "request accepted" and "pause completed".

## 16. Do Not Run Long Tasks on JMX Threads

Operations that trigger index rebuilds, large cache clears, backlog reprocessing, or report exports can run for minutes. If the code executes synchronously:

```java
@ManagedOperation
public void rebuildIndex() {
    indexService.rebuildAll();
}
```

the `MBeanServer.invoke(...)` call may block until the work completes. With remote JMX, a client timeout does not guarantee the server stopped running.

A better contract:

```text
requestRebuild(String requestKey) -> String requestId
getRebuildStatus(String requestId) -> String
cancelRebuild(String requestId) -> boolean
```

The service dispatches via a bounded executor/queue, returns an ID quickly, and records states `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`.

Idempotency or deduplication is needed so retries do not create duplicate jobs; a bounded queue is required, and avoid `CallerRunsPolicy` if it could run heavy tasks on the JMX caller thread.

## 17. Designing a Small Management Adapter

In real applications, business services often have many methods unsuitable for export. Create a management adapter that exposes only the selected API.

Example:

```java
package example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.import:type=Worker,name=Primary",
    description = "Primary import worker management"
)
public class ImportWorkerManagement {

    private final ImportMetricsSnapshot metrics;
    private final ImportControlService control;

    public ImportWorkerManagement(
            ImportMetricsSnapshot metrics,
            ImportControlService control) {
        this.metrics = metrics;
        this.control = control;
    }

    @ManagedAttribute(
        description = "Queued import jobs (count)"
    )
    public long getQueueDepth() {
        return metrics.queueDepth();
    }

    @ManagedAttribute(
        description = "Oldest queued job age in seconds"
    )
    public long getOldestQueuedAgeSeconds() {
        return metrics.oldestQueuedAgeSeconds();
    }

    @ManagedAttribute(
        description = "Current worker state"
    )
    public String getState() {
        return metrics.state();
    }

    @ManagedOperation(
        description = "Request graceful pause; returns accepted flag"
    )
    public boolean requestPause() {
        return control.requestPause();
    }
}
```

`ImportMetricsSnapshot` and `ImportControlService` are abstractions defined by the application. The adapter keeps the JMX surface clear and delegates to Spring-managed services; it does not directly contain persistence or complex async logic.

In production, trusted authentication/authorization is required at the connector/server/service; the example above focuses on illustrating API shape.

## 18. Configuring MBeanExporter According to Goals

In Spring Framework, `MBeanExporter` and a metadata assembler can be used to export only selected beans:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ManagementConfiguration {

    @Bean
    public MBeanExporter managementExporter(
            ImportWorkerManagement management) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(Map.of("importWorkerManagement", management));
        return exporter;
    }
}
```

This is an explicit export style that reduces the risk of accidentally exposing multiple beans. Identify the `MBeanServer` appropriate for the context and avoid creating duplicate exporters when Spring Boot auto-configuration or `@EnableMBeanExport` is already in use.

**Do not choose `IGNORE_EXISTING`/`REPLACE_EXISTING` just to hide ObjectName collision errors.** Control ownership and the naming strategy instead.

## 19. Metadata Is a Public Contract

After export, clients can inspect:

```java
ObjectName name = new ObjectName(
    "com.example.import:type=Worker,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() + " : " + attribute.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(
        operation.getName() + " : " + operation.getReturnType()
    );
}
```

A well-articulated management goal should produce a matching **runtime contract**:

| Requirement | `MBeanInfo` Check |
| --- | --- |
| Has QueueDepth | `QueueDepth` attribute of type `long`. |
| Queue depth is read-only | `isReadable=true`, `isWritable=false`. |
| Has OldestQueuedAgeSeconds | Attribute of type `long`, description includes unit. |
| Has State | `State` attribute of type `String`. |
| Has requestPause | Zero-argument operation returning `boolean`. |
| Does not expose internal methods | Negative assertion of absence in operations. |

Do not rely on array order of attributes/operations; match by name and signature. `MBeanInfo` reflects MBean capabilities, not the current user's permissions.

## 20. Pre-Implementation Design Review Checklist

| Criterion | Question to Satisfy | Evidence |
| --- | --- | --- |
| Goal | Which decision does the MBean support? | Use case and runbook. |
| Audience | Who will read/invoke it? | Operator persona, role. |
| Surface | Only minimal attributes/operations? | MBeanInfo allowlist. |
| Semantics | Are names, units, and values clear? | API contract. |
| Performance | Lightweight getters, bounded latency? | Measurement/test. |
| Side effects | Do operations have validation and idempotency? | Behavior tests. |
| Security | Are identity/permissions/transport protected? | Security integration tests. |
| Observability | Are status, errors, and audit present? | Logs/metrics/status. |
| Lifecycle | Does start/close register/unregister? | Integration test. |
| Compatibility | Are existing clients unaffected? | Contract regression test. |
| Cluster | Per-instance or cluster-wide metrics? | Scope description. |
| Maintenance | Who owns the names and documentation? | Owner/runbook. |

This table is a design tool, not an automated scoring mechanism. Its purpose is to force risks to be discussed before the API is published.

## 21. Common Anti-Patterns

### 21.1. Exporting every public method

```java
public class AccountService {
    public Account findById(String id);
    public void resetPassword(String id);
    public void deleteAllAccounts();
}
```

**Problem:** Overly broad management surface, dangerous operations, easy data leaks. **Solution:** A very small allowlist management adapter.

### 21.2. Getter running a database scan

```java
@ManagedAttribute
public long getQueueDepth() {
    return repository.findAll().stream().count();
}
```

**Problem:** Monitoring increases system load. **Solution:** Updated counter/snapshot or an optimized count query with a clear refresh rate.

### 21.3. Operation running for minutes

```java
@ManagedOperation
public void rebuildAll() {
    indexingService.rebuildAll();
}
```

**Problem:** Blocks JMX caller, hard to retry. **Solution:** Request ID + async job status, bounded queue.

### 21.4. Metrics without units

```text
Latency=240
Uptime=9000
```

**Problem:** Clients do not know whether units are milliseconds or seconds. **Solution:** `LatencyMillis`, `UptimeSeconds`, with a clear measurement description.

### 21.5. Using a profile as the sole security boundary

```java
@Profile("!prod")
@ManagedResource
```

**Problem:** Profile may be misconfigured or another exporter may still publish the bean; remote connectors may remain unprotected. **Solution:** Explicit configuration conditions, protect the connector/service, test runtime exposure.

## 22. When Should You Not Create an MBean?

Not every management requirement should be solved with JMX. Avoid creating a new MBean if:

- You only need multi-instance aggregated charts/alerts and already have a metrics backend.
- You only need an HTTP health endpoint for an orchestrator.
- The data is too large and requires pagination, search, or filtering.
- The feature is for end users, not operators.
- The action requires an approval workflow, durable queue, or complex business audit.
- The team lacks a way to secure JMX permissions while the operation is highly sensitive.
- The MBean merely mirrors an internal method with no concrete operational use case.

JMX can still act as a **thin control surface** submitting requests to a dedicated system, rather than housing all management logic.

## 23. Testing Against Goals Rather Than Only Annotations

Tests should derive from the requirements in section 7:

### 23.1. Registration

```java
assertTrue(server.isRegistered(name));
```

However, this test only proves the ObjectName exists, not that the metadata or bean owner is correct.

### 23.2. Attribute contract

```java
var depth = Arrays.stream(server.getMBeanInfo(name).getAttributes())
    .filter(a -> "QueueDepth".equals(a.getName()))
    .findFirst()
    .orElseThrow();

assertEquals("long", depth.getType());
assertTrue(depth.isReadable());
assertFalse(depth.isWritable());
```

### 23.3. Operation contract

```java
var pause = Arrays.stream(server.getMBeanInfo(name).getOperations())
    .filter(op -> "requestPause".equals(op.getName()))
    .findFirst()
    .orElseThrow();

assertEquals(0, pause.getSignature().length);
assertEquals("boolean", pause.getReturnType());
```

### 23.4. Negative surface test

```java
boolean dangerous = Arrays.stream(
    server.getMBeanInfo(name).getOperations()
).anyMatch(op -> "deleteAllAccounts".equals(op.getName()));

assertFalse(dangerous);
```

### 23.5. Security integration

If remote JMX is enabled, test with the connector using readonly credentials and the control role, verify actual denial, and assert no side effects occur. A local `MBeanServer.invoke` does not go through remote connector authentication and does not prove authorization policy.

### 23.6. Lifecycle

Close the `ApplicationContext` in an isolated test and verify the exporter-managed MBean is no longer in the registry. Avoid ObjectName collisions when tests run in parallel.

## 24. Runbook Documentation for Operators

An MBean must be used properly after deployment. A brief runbook should record:

```text
ObjectName:
  com.example.import:type=Worker,name=Primary

Purpose:
  Diagnose queue backlog and request graceful pause.

Read attributes:
  QueueDepth, OldestQueuedAgeSeconds, State

Control operation:
  requestPause()

Authorization:
  Read-only operator vs control operator (enforced externally).

Side effects:
  Stops taking new jobs; current jobs may finish.

Verification:
  State -> PAUSE_REQUESTED -> PAUSED

Recovery:
  requestResume() only if permitted and implemented.

Escalation:
  On-call service owner.
```

Do not promise that `requestResume()` exists if it has not been implemented; the runbook must accurately reflect the `MBeanInfo` and behavior of the running version.

## 25. Hands-on Exercises

### Exercise 1 — From symptom to goal

A message-processing API is running slowly. Write three questions an operator needs answered and translate them into at most five small, read-only attributes.

**Goal:** design from needs, not from a source method list.

### Exercise 2 — Choosing the right tool

Categorize these requests: 14-day CPU alert, inspecting live worker status, downloading 100,000 orders, pausing a consumer, readiness probe. Choose the appropriate JMX, metrics, HTTP API, or job system and explain why.

**Goal:** avoid overusing JMX.

### Exercise 3 — Designing ObjectNames

Define ObjectNames for three different workers in the same JVM. Prove the names do not collide and contain no PII.

**Goal:** stable namespace and clear ownership.

### Exercise 4 — Reducing the surface

Given a service with 20 public methods, including data deletion and credential changes, design a management adapter with only three attributes and one safe operation.

**Goal:** use an allowlist.

### Exercise 5 — Writing acceptance tests

Write `MBeanInfo` checks for names, types, read/write flags, signatures, and forbidden operations.

**Goal:** protect the contract with tests.

### Exercise 6 — Long-running operations

Convert a synchronous `rebuildIndex()` into `requestRebuild(requestKey)`, `getRebuildStatus(id)`, and define retry/idempotency behavior.

**Goal:** separate accepted from completed.

### Exercise 7 — Security review

List viewer/operator permissions, identify which layer enforces permissions, and describe how to test that a remote readonly account cannot invoke control operations.

**Goal:** do not confuse metadata with authorization.

## 26. Review Questions

**1. What is the first step before creating an MBean?** Identify the need, actor, operational decision, and success criteria.

**2. Why avoid exporting an entire business service?** Risk of exposing data, dangerous operations, and an unstable contract.

**3. When is an attribute appropriate?** Lightweight readable state/metrics requiring no parameters and minimal/no side effects.

**4. When is an operation needed?** When there is a controlled action or parameterized query.

**5. What does `MBeanInfo` help evaluate?** The runtime contract: attributes, operations, types, signatures, and descriptions.

**6. Does `isWritable=true` prove the caller can write?** No, it is capability metadata, not user authorization.

**7. Why must getters be lightweight?** Because monitoring clients may poll frequently.

**8. Why should a long-running operation return a job ID?** So the JMX caller does not block for long, while enabling status tracking and safe retries.

**9. Do identical ObjectNames across two JVMs conflict?** No, if their registries/MBeanServers are separate.

**10. When should you not use JMX?** When the real need is large data queries, metrics retention, long workflows, or a public user API.

## 27. Summary

**Defining management goals before creating an MBean** is the most important step to making a JMX API useful and safe. Start from the operational scenario, the questions to answer, and the operator's decision; then determine the minimal data/actions, names, types, units, frequency, permissions, and side effects.

In Spring Framework, `MBeanExporter` and annotations help publish beans, but they do not replace contract design, authorization, or testing. A good MBean has a small, clear, stable API, lightweight getters, controlled operations, and an `MBeanInfo` matching the goal. When the need involves long-term metrics, large datasets, or complex workflows, choose the right tool instead of forcing everything into JMX.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `ManagedResource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — `ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Boot Reference — JMX: https://docs.spring.io/spring-boot/reference/actuator/jmx.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
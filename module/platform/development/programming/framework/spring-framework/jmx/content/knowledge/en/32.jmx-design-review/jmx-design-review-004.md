# Evaluating Attributes, Operations, and Notifications by Impact in Spring JMX

## 1. Context

Spring Framework JMX allows exposing the state and management capabilities of a Spring bean as an MBean via annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, and \`@ManagedNotification\`. However, a management API is only considered good when **what it exposes delivers operational value commensurate with its risk**.

The three components have different roles and impact levels:

- **Attribute:** allows reading a state value, and when writable, also allows modifying that value.
- **Operation:** allows invoking a management action that may mutate state or trigger work.
- **Notification:** emits signals about events or state transitions to registered listeners.

This lesson presents an impact-based evaluation method to decide what to expose, how to protect it, and what to test before taking a management interface to production.

### Expected Outcomes

After this lesson, you will be able to:

1. Distinguish the impact of read-only attributes, writable attributes, operations, and notifications.
2. Evaluate operational value, blast radius, security risks, and execution cost.
3. Build an inventory and risk matrix for a real-world MBean.
4. Choose which elements to keep, change, remove, or move to another management API.
5. Design appropriate validation, authorization, idempotency, auditing, and execution limits.
6. Inspect the metadata that JMX clients actually see via \`MBeanInfo\`.
7. Analyze remote JMX, Spring AOP proxies, and transaction boundaries when they affect behavior.
8. Test failure scenarios, high load, duplicate calls, and lost notifications.

## 2. Evaluating from Operational Questions

Do not start with the question "What public methods does this class have?". Start with:

- What does the operator need to know or do?
- Without this information/action, which incident becomes harder to resolve?
- Who is authorized to use it?
- What is the usage frequency and urgency?
- Is there another safer telemetry source or runbook?
- If the data is wrong, read too often, or the action is invoked by mistake, what happens?
- If the remote connection drops mid-call, can the outcome be recovered?

Example for a payment-processing worker:

| Question | Possible Interface | Needs Evaluation |
|---|---|---|
| Is the worker still making progress? | \`LastSuccessAt\`, \`ProcessedTotal\` | Freshness and semantics |
| Is there a backlog? | \`PendingCount\` | Read cost and data source |
| Are errors spiking? | \`FailedTotal\` + metrics rate | Counter resets and sampling |
| Can intake be paused? | \`pauseIntake()\` | SLA impact and recovery |
| Can jobs be retried? | \`retryJob(id)\` | Idempotency and authorization |
| Need to know failed transitions? | Notification \`worker.failed\` | Noise filtering, loss/reconnect |
| Need to view connection tokens? | Do not expose | Secret disclosure risk |

Key takeaway: **Observability is not the same as permission to mutate state**. Even a read-only attribute can have impact if calling it is resource-intensive or exposes sensitive data.

## 3. A Simple Evaluation Matrix

Each item can be evaluated against the following criteria:

| Criterion | Question | Attention Level |
|---|---|---|
| Operational value | Does it help diagnose or resolve incidents? | High when directly supporting decisions |
| Sensitivity | Does it expose secrets, PII, topology, or internal data? | Security risk |
| Side effect | Does it change state, create jobs, or delete data? | Correctness risk |
| Cost | Does a single call consume CPU, I/O, locks, or network? | Performance risk |
| Concurrency | Is it safe when multiple callers invoke concurrently? | Race condition risk |
| Reliability | Does a remote call timeout leave an indeterminate outcome? | Retry risk |
| Availability | Can it block thread pools or slow down the service? | Operational risk |
| Compatibility | Do clients depend on names, types, or semantics? | API change risk |
| Auditability | Is it necessary to record who did what and when? | Governance |
| Discoverability | Do operators understand names/units/descriptions? | Usability |

You do not need to collapse everything into a single "score". An attribute containing a password must be rejected regardless of high operational value; an operation deleting data requires strong permissions and workflows and cannot be approved based on a total score alone.

## 4. Classifying Impact Levels

A qualitative model for review:

**Level A — Lightweight observation:** Reading a small snapshot or counter with low overhead and no sensitive information.

**Level B — Costly or sensitive observation:** Reading large aggregates, stack/thread details, internal configuration, or triggering I/O.

**Level C — Controlled state change:** Setter changing a validated limit, or a recoverable pause/resume operation.

**Level D — High-impact action:** Resetting data, restarting components, clearing system-wide caches, or altering active work streams.

**Level E — Business action unsuitable for typical JMX:** Payments, refunds, deleting records, or tasks requiring strict audit/approval and transactional guarantees.

This classification is a discussion tool, not a formal JMX standard. Actual severity depends on context: \`clearCache()\` may be trivial locally yet cause severe load spikes in production.

## 5. Read-Only Attributes: Reading Is Not Always Harmless

Simple example:

\`\`\`java
@ManagedAttribute(description = "Current pending job count")
public int getPendingCount() {
    return pendingCount.get();
}
\`\`\`

This is generally a low-risk management surface if:
- The counter is maintained accurately.
- The getter does not block worker threads.
- The value reads quickly.
- No sensitive data is exposed.
- Units and sampling timing are clear.

Conversely:

\`\`\`java
@ManagedAttribute(description = "All active customer records")
public List<Customer> getCustomers() {
    return repository.findAll();
}
\`\`\`

has multiple problems:
- Returning customer records can violate security/privacy.
- Querying the entire database is heavy when JMX clients poll frequently.
- Large lists can slow down serialization or the connector.
- The object graph may be incompatible with remote JMX.
- Internal Java names/types become external client dependencies.

A better solution is exposing necessary aggregates, such as \`ActiveCustomerCount\`, or using a separately protected management API when detailed records are truly required.

## 6. Analyzing the Cost of a Managed Getter

A monitoring collector might read every attribute every 10 seconds across hundreds of JVMs. If each getter executes a 500 ms database query, total load can be significant.

Classify data sources:
- **In-memory counter:** usually minimal cost.
- **Cached snapshot:** low cost, with update lag.
- **Database aggregation:** incurs I/O cost, requires indexes/query plans.
- **External API:** incurs latency, timeouts, and failure modes.
- **Full thread dump/heap dump:** high cost, unsuitable for continuous polling.

For costly attributes, consider:
1. Switching to a periodically updated snapshot.
2. Exposing \`SnapshotTimestamp\` or \`SnapshotAgeSeconds\`.
3. Rate-limiting execution frequency.
4. If intentional diagnostic work is needed, use a dedicated operation instead of a getter.
5. Measuring latency in tests under representative workloads.

A read-only getter that locks the entire processing pipeline for 2 seconds can have major impact even without mutating state.

## 7. Consistency and Freshness of Attributes

JMX clients may read \`PendingCount\`, \`ActiveCount\`, and \`ProcessedTotal\` at different instants. Do not assume they form a transactionally consistent snapshot.

If consistent data is needed:
- Maintain an immutable snapshot.
- Return data carrying a \`version\` or \`capturedAt\`.
- Use OpenTypes/MXBean representation when structure is needed.
- Document freshness and accuracy clearly in the description.

A \`LastSuccessAt\` attribute may be null when no run has succeeded yet; descriptions must distinguish "never ran" from "data source unavailable".

Do not use undocumented sentinel values such as \`0\`. For example, \`LastSuccessEpochMs=0\` can be mistaken for the Unix epoch rather than "no data yet".

## 8. Writable Attributes: Acceptance Criteria

Example:

\`\`\`java
private volatile int maxConcurrentJobs = 8;

@ManagedAttribute(description = "Maximum concurrent jobs")
public int getMaxConcurrentJobs() {
    return maxConcurrentJobs;
}

@ManagedAttribute(description = "Maximum concurrent jobs")
public void setMaxConcurrentJobs(int value) {
    if (value < 1 || value > 64) {
        throw new IllegalArgumentException("Allowed range: 1..64");
    }
    maxConcurrentJobs = value;
}
\`\`\`

A writable property must be treated as a **configuration mutation API**. Reviews must answer:
- Does the new value take effect immediately or after restart?
- Does it interrupt in-flight tasks?
- Does it depend on the capacity of other resources?
- If multiple callers set it concurrently, which wins?
- Is the change persisted durably?
- Can it be rolled back?
- Who is permitted to set it?
- Is there an audit log?
- Could automated tools accidentally overwrite it due to legacy mappings?

For complex changes, an explicitly named operation like \`requestConcurrencyChange(int)\` can communicate preconditions better than a writable attribute. However, an operation does not add authentication, validation, or transactions on its own either.

## 9. Operations: Clear Impact and Recovery

\`@ManagedOperation\` creates an invocable capability over JMX. It can be as light as \`resetStatistics()\` or as dangerous as \`deletePendingJobs()\`.

Example of a clearly scoped management operation:

\`\`\`java
@ManagedOperation(description = "Pause acceptance of new jobs")
public void pauseIntake() {
    workerControl.pauseIntake();
}
\`\`\`

Design must clarify:
- Does pausing only stop accepting new work or also halt running jobs?
- How long does it take for the pause to take effect?
- Is calling pause multiple times safe?
- If the JVM restarts, is the paused state preserved?
- Which attribute can callers read to verify the outcome?
- If the operation fails mid-way, what state is the system left in?

### Comparing Some Operations

| Operation | Primary Risk | Recommended Control |
|---|---|---|
| \`resetStatistics()\` | Loss of counter continuity | Audit; clear reset scope |
| \`pauseIntake()\` | Reduced throughput | Authorization; state verification |
| \`resumeIntake()\` | Sudden load spike | Preconditions; rate limiting |
| \`clearCache()\` | Cache stampede | Concurrency guard; capacity checks |
| \`reloadConfiguration()\` | Inconsistent runtime config | Validation; rollback |
| \`triggerJob()\` | Duplicate execution | Idempotency key; job status |
| \`terminateWorker()\` | Loss of availability | Strong authorization/approval |
| \`deleteAllRecords()\` | Data loss | Usually should not be exposed via JMX |

## 10. Long-Running and Asynchronous Actions

A synchronous JMX operation running for several minutes can cause:
- Remote client timeouts.
- Connector resources held for a long time.
- Indeterminate outcomes on disconnect.
- Retries creating duplicate work.
- Load spikes when multiple operators invoke concurrently.

Instead of:

\`\`\`java
@ManagedOperation
public void rebuildIndex() {
    indexService.rebuildEverything();
}
\`\`\`

you can design:

\`\`\`java
@ManagedOperation(description = "Submit index rebuild and return job ID")
public String requestIndexRebuild() {
    return indexService.submitRebuild();
}

@ManagedAttribute(description = "Current rebuild state")
public String getRebuildState() {
    return indexService.currentState().name();
}
\`\`\`

Job identity, concurrency, and idempotency must be managed; simply returning a job ID does not create a durable job system by itself.

## 11. Remote Invoke Timeouts and Idempotency

Suppose a client invokes \`clearCache()\` over remote JMX, the server executes it successfully, but the response never reaches the client due to network loss.

From the client side:
\`\`\`text
invoke(clearCache) -> timeout
\`\`\`

A timeout **does not prove** the operation did not run. Retrying immediately can cause two cache clears or two rebuild tasks.

Operation reviews must determine:
- Is it idempotent?
- Is there a \`requestId\`?
- Is there an endpoint/attribute to look up status?
- Can state be checked before retrying?
- What is the consequence if executed twice?

For instance, \`pauseIntake()\` can usually be designed to be idempotent. An operation like \`chargeCustomer()\` is unsuitable for JMX exposure because it requires an exactly-once business effect, auditing, and complex authorization.

## 12. Authorization and the Principle of Least Privilege

Exposing an operation does not protect it. If the JMX remote connector permits the caller to invoke, the operation can be called.

A sound design includes:
- A read-only monitoring identity.
- A separate administrative identity with tighter permissions.
- Network segmentation.
- Connector authentication and authorization.
- TLS or appropriate transport protection.
- Server-side validation and auditing.
- No secrets in attributes or exception messages.

\`@ManagedOperation(description = "Admin only")\` is only a description. It does not enforce permissions.

Even local JMX must be evaluated according to the privileges of processes/users that can attach to and manage the JVM.

## 13. Notifications: Value and Limitations

JMX notifications are well suited for signaling:
- Worker transitioning to FAILED.
- Configuration reload succeeding or failing.
- System reaching a critical state.
- Administrative job starting/finishing.
- A resource becoming degraded.

Metadata example:

\`\`\`java
@ManagedNotification(
    name = "com.example.jobs.worker.failed",
    notificationTypes = {"com.example.jobs.worker.failed"},
    description = "Worker entered failed state"
)
\`\`\`

The annotation describes the notification type, while actually emitting it requires a broadcaster or \`NotificationPublisher\` sending a \`Notification\`.

### Notification impact goes beyond emitting events

A notification emitted too frequently can:
- Load serialization/remote connectors.
- Overflow memory in listeners or external queues lacking backpressure.
- Cause duplicate alerts or alert storms.
- Cause alert fatigue for critical incidents.
- Leak payloads or runtime state.

In particular, notifying per request/job in high-throughput systems is often unsuitable; metrics and sampled logs are usually better.

## 14. Notifications Are Not a Durable Message Broker

JMX does not provide event storage, durable replay, offsets, or exactly-once processing by default. A listener may:
- Not be registered yet when the notification fires.
- Lose connection.
- Be registered twice.
- Restart.
- Fail while processing the payload.
- Receive multiple events for the same logical cause.

If zero-loss event history is required, you must have another durable source such as an outbox/event store/broker. JMX notifications can act as a signal prompting clients to re-read a snapshot.

An appropriate pattern:

\`\`\`text
worker.changed notification
          |
          v
Client reads WorkerState attribute
          |
          v
Updates monitoring dashboard
\`\`\`

Upon reconnecting, the client re-reads \`WorkerState\` even if it missed notifications while offline.

## 15. Notification Payloads and Security

Data in \`Notification.userData\` can reach clients over the JMX connector. Consider:
- No passwords/tokens.
- No unnecessary PII.
- Size limits.
- Will clients understand the data type?
- Is remote serialization feasible?
- Can \`String\`, scalars, or OpenTypes replace internal DTOs?
- Is there a stable event ID/correlation ID?

Simple payload example:
\`\`\`java
notification.setUserData("job-123");
\`\`\`

If an arbitrary Java object is used, clients from another JVM may lack the class to deserialize it or be blocked by serialization filters. Do not treat a passing local test as proof of remote interoperability.

## 16. Combining Attributes, Operations, and Notifications

A commonly useful design:

\`\`\`text
Managed resource: JobWorker
  |
  +-- Attributes
  |      PendingCount (read-only)
  |      WorkerState (read-only)
  |      LastSuccessTime (read-only)
  |
  +-- Operations
  |      pauseIntake()
  |      resumeIntake()
  |
  +-- Notifications
         worker.paused
         worker.resumed
         worker.failed
\`\`\`

The three parts complement one another:
- Attributes allow reading current state.
- Operations trigger actions.
- Notifications announce state transitions.

Do not rely solely on notifications to confirm an operation completed. After calling pause, read \`WorkerState\` or a status attribute to verify. For asynchronous operations, use a job ID/status and timeout handling.

## 17. Spring Management Facade Example

Separate the management interface from a large business service:

\`\`\`java
package com.example.operations;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Import",
    description = "Import worker management"
)
public class ImportWorkerManagement {

    private final ImportWorkerService service;

    public ImportWorkerManagement(ImportWorkerService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending jobs at read time")
    public int getPendingCount() {
        return service.pendingCount();
    }

    @ManagedAttribute(description = "Current worker state")
    public String getWorkerState() {
        return service.state().name();
    }

    @ManagedOperation(description = "Pause acceptance of new jobs")
    public void pauseIntake() {
        service.pauseIntake();
    }

    @ManagedOperation(description = "Resume acceptance of new jobs")
    public void resumeIntake() {
        service.resumeIntake();
    }
}
\`\`\`

\`ImportWorkerService\` is the assumed business dependency in the example. Operations must have environment-appropriate validation and authorization. The facade does not enforce permissions by itself, but makes managing the JMX surface much cleaner.

## 18. Evaluation Matrix for the Facade

| Item | Type | Benefit | Impact | Decision |
|---|---|---|---|---|
| \`PendingCount\` | Read-only attribute | Diagnose backlog | Polling cost if query is heavy | Expose via snapshot |
| \`WorkerState\` | Read-only attribute | Know state | Low if enum is small | Expose |
| \`LastFailureMessage\` | Read-only attribute | Diagnostics | May leak details | Sanitize/truncate |
| \`setMaxConcurrentJobs\` | Writable attribute | Runtime tuning | Changes capacity | Validate, audit, authorize |
| \`pauseIntake()\` | Operation | Maintenance | Reduces throughput | Admin allowlist |
| \`clearAllJobs()\` | Operation | Rarely needed | Data loss | Do not expose |
| \`worker.failed\` | Notification | Immediate error alert | Noise, loss/retry | Expose with filter |
| \`job.completed\` per request | Notification | Excessive detail | High volume | Use metrics/event log |

This is an example; real requirements depend on SLOs, data classification, and actual permissions.

## 19. Evaluating API Evolution

ObjectNames, attribute names, and operation names are considered a contract with monitoring clients.

Changing:
\`\`\`text
com.example.jobs:type=Worker,name=Import
\`\`\`
to:
\`\`\`text
com.example.import:type=Worker,name=Primary
\`\`\`
can break existing scripts with \`InstanceNotFoundException\`.

Similarly:
- Renaming \`PendingCount\` to \`QueueLength\` breaks existing queries.
- Changing type \`long\` to a complex object can break client parsing.
- Removing an old operation can break runbooks.
- Changing a notification type requires updating listener filters.

When reviewing an API, assess external tool dependencies; do not treat refactoring JMX names as a harmless internal change.

## 20. Spring AOP and Actual Call Paths

A bean having both \`@ManagedResource\` and \`@Transactional\` may be wrapped by Spring in a JDK/CGLIB proxy. When reviewing operations:
- Is metadata discovered on the target class?
- Is the operation available through the proxy interface?
- Does the JMX invocation go through the Spring proxy so the transaction interceptor takes effect?
- Is there self-invocation causing \`@Transactional\` to be bypassed?
- Which bean is actually registered by the exporter?

A management facade calling an injected transactional service usually creates a cleaner boundary than directly exposing a service with multiple advices. Still, verify with integration tests; do not assume all proxy configurations behave identically.

## 21. Inspecting Actual MBeanInfo

Example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Import"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

var info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "%s %s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}

for (var notification : info.getNotifications()) {
    System.out.println("Notification: " + notification.getName());
}
\`\`\`

In systems using a custom MBeanServer, obtain the exact server used by the Spring exporter. \`MBeanInfo\` shows the runtime-exposed interface; annotations in source code alone do not prove everything was exported properly.

## 22. Testing Each Impact Category

### 22.1. Attribute tests

- Is the MBean registered?
- Do attributes have the right names/types/descriptions?
- Are any accidentally writable?
- Does the getter have side effects?
- Does repeated reading cause abnormal load?
- When data is missing/unavailable, is the result unambiguous?
- Is any sensitive data exposed?

### 22.2. Operation tests

- Does the operation have the expected signature?
- Are inputs validated?
- Are unauthorized users blocked?
- Is concurrent invocation controlled?
- Are repeated calls safe?
- If it fails mid-way, can state recover?
- If the client times out, is there a status to reconcile against?
- Are critical actions audited?

### 22.3. Notification tests

- Are type and payload correct?
- Is it emitted when the event occurs?
- Do filters receive only the intended types?
- Are listener lifecycle and cleanup correct?
- Are there duplicate callbacks?
- Is state lost across reconnects?
- Does emission rate cause overload?
- Can payloads be deserialized by remote clients?

### 22.4. Security tests

- Is the remote connector protected?
- Are read permissions separated from invoke/write permissions?
- Are secrets exposed via attributes, \`userData\`, or exceptions?
- Do local/remote callers stay within their intended permission scope?

## 23. Cost and Load Testing

One assumption to avoid: "JMX is rarely used, so it doesn't matter how expensive an operation is".

Collectors may poll every few seconds across many services. A database-querying getter can add substantial load. A long synchronous diagnostic operation can tie up connector threads or create contention.

Test:
- Getter p95/p99 latency under load.
- Memory allocations during serialization.
- Impact on business throughput.
- Lock contention.
- Behavior when 10 or 100 clients call simultaneously.
- Behavior when the connector network is slow.
- Cleanup when clients disconnect.

If monitoring slows down the service, adjust the design: cache/snapshot, limit payloads, rate-limit, or move to an on-demand diagnostic tool.

## 24. Documentation and Ownership

Each MBean should have:
- Owner/team.
- ObjectName convention.
- Attribute list with units, freshness, and reset semantics.
- Operations with inputs, side effects, preconditions, results, and recovery.
- Notifications with types, payload schema, and delivery limitations.
- Access policy.
- Runbook.
- Compatibility/deprecation policy.

A brief description in \`@ManagedAttribute\` is helpful, but does not replace documentation for high-impact operations.

## 25. When Should You Avoid JMX?

Some scenarios warrant preferring other tools:
- Business workflows needing authentication/approval, auditing, and idempotent requests: a secured administrative REST/gRPC API.
- Historical metrics and alerting: Micrometer/Prometheus or an equivalent observability stack.
- Distributed tracing: tracing infrastructure.
- Zero-loss events: durable broker/event store.
- Bulk data export: batch/report API.
- Versioned configuration with approvals: configuration management system.

JMX remains well suited for JVM-local state, diagnostic attributes, and small-scale operational actions. Choosing tools based on impact helps prevent using JMX as a backdoor to bypass business controls.

## 26. Practical Review Checklist

Before approving a management surface, answer:

1. Which operational question does this item serve?
2. Does it need to be exposed over JMX?
3. Is it read-only, writable, an operation, or a notification?
4. Does it involve sensitive data?
5. Are there side effects or correctness risks?
6. Could it be called frequently?
7. What are the latency, CPU, memory, and I/O costs?
8. Could it face concurrent calls and retries?
9. On remote disconnect, how does the caller determine the outcome?
10. Are validation and authorization sufficient?
11. Are auditing and a runbook in place?
12. Are names/types/semantics stable?
13. Has actual \`MBeanInfo\` been inspected?
14. Have failure, overload, and restart/reconnect been tested?
15. Is there a lower-risk alternative?

A review need not answer "yes" to every question. What matters is that every significant impact is identified and addressed intentionally.

## 27. Hands-On Exercises

### Exercise A — Management surface inventory

Given a service with 12 public methods, identify:
- Three useful read-only attributes.
- One acceptable writable attribute.
- Two genuinely needed operations.
- One notification worth emitting.
- Methods that should stay internal.

Justify based on value and risk, not code-style preferences.

### Exercise B — Reviewing a costly attribute

1. Create a getter reading all database records.
2. Measure latency under repeated polling.
3. Switch to a snapshot counter.
4. Add timestamp/freshness.
5. Propose safeguards so collectors do not poll too frequently.

### Exercise C — Impactful operation

1. Create \`pauseIntake()\` and \`resumeIntake()\`.
2. Define valid states and idempotency.
3. Write validation.
4. Test repeated and concurrent invocations.
5. Generate an audit record in a test environment.

### Exercise D — Remote timeout

1. Simulate a job-creating operation.
2. Drop the client response after the server receives the request.
3. Examine the risk of retries creating duplicate jobs.
4. Add a request ID or status lookup.
5. Verify duplicate requests do not duplicate side effects.

### Exercise E — Notifications

1. Create a \`worker.failed\` notification.
2. Register a listener with a filter.
3. Verify type/payload/sequence.
4. Test disconnect/reconnect.
5. Re-read the \`WorkerState\` snapshot.
6. Explain why notifications do not replace durable event history.

### Exercise F — Security

1. Place a dummy secret in configuration.
2. Verify all attributes do not expose the secret.
3. Use read-only and admin users in a connector test.
4. Verify reads are allowed while invoke is blocked for an unauthorized identity.
5. Verify auditing when an admin executes an operation.

## 28. Self-Check Questions

**Question 1.** Are read-only attributes always safe?  
**Answer:** No. They can leak sensitive data or generate heavy load.

**Question 2.** How does a writable attribute differ most significantly from a read-only one?  
**Answer:** It can mutate runtime state, requiring validation, authorization, and consistency.

**Question 3.** When should an operation return a job ID instead of running synchronously?  
**Answer:** When the task is long-running, risks timeouts, and requires status tracking and controlled retries.

**Question 4.** Do JMX notifications guarantee full replay after reconnect?  
**Answer:** Not by default; a snapshot or durable event store is needed if events cannot be lost.

**Question 5.** Does \`@ManagedOperation\` grant admin privileges by itself?  
**Answer:** No. Authentication/authorization must be configured separately.

**Question 6.** Why inspect \`MBeanInfo\`?  
**Answer:** To verify the actual exposed interface, including writable flags and operation signatures.

**Question 7.** Does a timed-out operation guarantee it did not execute?  
**Answer:** No. Idempotency/status lookup is required to resolve ambiguous outcomes.

**Question 8.** Why is a management facade helpful?  
**Answer:** It keeps the JMX surface small, establishes ownership, and separates it from business implementation details.

**Question 9.** What is the impact of emitting notifications too frequently?  
**Answer:** It can cause overload, alert storms, and higher serialization overhead.

**Question 10.** When should you choose an API other than JMX?  
**Answer:** When a workflow requires security, auditing, reliability, or scale beyond what JMX handles well.

## 29. Key Takeaways

- Attributes, operations, and notifications have different impact levels and require separate review.
- Operational benefit must be weighed against security, cost, and side-effect risks.
- Read-only is not inherently safe; writable attributes and operations require stronger controls.
- Avoid heavy getters or returning uncontrolled object graphs.
- Operations need validation, idempotency, concurrency control, auditing, and recovery semantics.
- A remote timeout does not prove an operation did not execute.
- Notifications lack durable replay by default; use snapshot/resync and an event store when needed.
- Extract a management facade from business services when it helps shrink the management surface.
- Inspect \`MBeanInfo\` on the actual MBeanServer to verify the exposed interface.
- Changing names/types changes the management API contract.
- JMX is useful for JVM-local state, but does not replace all observability and management workflow systems.
- Review a management API by impact rather than by count of annotations or methods.

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Exporting MBeans: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — \`ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — \`ManagedOperation\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Framework Javadoc — \`ManagedNotification\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedNotification.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html

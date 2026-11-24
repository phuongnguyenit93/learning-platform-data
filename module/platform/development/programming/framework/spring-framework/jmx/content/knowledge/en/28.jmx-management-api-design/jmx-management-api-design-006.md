# Separating Diagnostic Commands from State-Mutating Commands in Spring Framework JMX

## 1. Objective

JMX is the runtime management interface of a Java application. In Spring Framework, beans can be exported as MBeans using `MBeanExporter`, `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`. Through JConsole, VisualVM, or `MBeanServerConnection`, operators can read application state or invoke management methods.

A critical design issue is **not mixing commands intended solely for diagnostics with commands that mutate state**. An operation named `inspect`, `getStatus`, or `diagnose` that internally resets counters, reloads configuration, clears caches, opens connections, or runs jobs can cause incidents when monitoring tools invoke it repeatedly.

A management API should clearly separate two groups:

- **Observation/diagnostics (read/query):** reads current state snapshots, aggregate metrics, health, counters, version, or safe metadata; does not mutate business state.
- **Control/mutation (command):** reloads configuration, pauses/resumes processing, clears caches, resets counters, rotates pools, triggers retries, or changes a runtime parameter.

**Core principle:** anything intended strictly for observation must have **no significant side effects**; mutating control operations must have clear names and contracts, separate permissions, validation, resource bounds, auditing, and error-handling strategies.

## 2. Why Separate? JMX Clients May Invoke Automatically and Repeatedly

JMX monitoring typically polls attributes periodically, for example every 10–30 seconds. If `getQueueDepth()` inadvertently deletes failed jobs or `getCacheStats()` resets counters, a dashboard can alter application behavior simply by reading.

```text
Monitoring collector (periodic polling)
          |
          v
JMX getAttribute("QueueDepth")
          |
          v
Safe getter -> reads snapshot only

Operator (explicit action)
          |
          v
JMX invoke("pauseProcessing")
          |
          v
Command -> validation -> state change -> audit
```

Beyond polling risk, management tools may retry on timeouts, or a user may invoke an operation mistakenly because its name suggests read-only behavior. Separating queries from commands reduces operational risk and makes the API easier to authorize.

## 3. Distinguishing JMX Attributes and Operations

| Concept | Target Semantics | Examples |
| --- | --- | --- |
| Read-only attribute | Observable state, fast getter | `QueueDepth`, `ActiveWorkers`, `LastErrorCategory` |
| Writable attribute | Controlled runtime configuration change | `Enabled`, `MaxWorkers` |
| Diagnostic operation | Potentially resource-intensive diagnostics, still leaves business state unchanged | `collectThreadSummary()`, `sampleCacheKeys(int limit)` |
| Control operation | State-mutating action | `pause()`, `resume()`, `clearCache()` |

Not every operation mutates state; an operation may be read-only yet require parameters or computation. Still, separating **diagnostic operations** from **commands** helps operators know which operations are safe to repeat and which require approval.

A JMX attribute with a setter becomes writable, so exposing `setEnabled(boolean)` is effectively a **command** even if the UI presents it as editing a property. Never assume all attributes are read-only.

## 4. Anti-Pattern: Getters with Side Effects

```java
@ManagedAttribute
public int getFailedTaskCount() {
    int failed = failedTaskCounter.get();
    failedTaskCounter.set(0);  // Wrong: polling wipes the metric.
    return failed;
}
```

If a collector reads the attribute every minute, the counter resets every minute. Operators viewing dashboards struggle to see total errors, and two collectors can even observe conflicting figures.

Better design:

```java
@ManagedAttribute(description = "Total number of failed tasks")
public long getFailedTaskCount() {
    return failedTaskCounter.get();
}

@ManagedOperation(description = "Reset failure counter on demand")
public void resetFailedTaskCounter() {
    authorization.requireOperator();
    failedTaskCounter.set(0);
    audit.record("reset-failed-task-counter");
}
```

`authorization` and `audit` are application-provided abstractions. In production, reset logic may need synchronization with counter increments; if resetting can lose important data, prefer monotonic counters and compute windowed metrics instead of manual resets.

## 5. Anti-Pattern: Operations Named Diagnose That Mutate State

```java
@ManagedOperation
public String diagnoseConnectivity() {
    reconnectAllClients();       // Heavy impact.
    clearConnectionCache();      // Side effect.
    return runConnectivityTest();
}
```

The name `diagnoseConnectivity` sets an expectation of reading/checking, yet the method modifies live connections. When an operator runs it to inspect health, application behavior changes immediately and may erase evidence of the fault.

Split it instead:

```java
@ManagedOperation(description = "Read latest connectivity status")
public String getConnectivitySummary() {
    return diagnostics.safeConnectivitySummary();
}

@ManagedOperation(description = "Run a bounded connectivity probe")
public String runConnectivityProbe() {
    return diagnostics.runBoundedProbe();
}

@ManagedOperation(description = "Request client reconnection")
public void reconnectClients() {
    commands.reconnectClients();
}
```

Even `runConnectivityProbe()` can consume network/CPU and cause minor side effects (an extra request or short-lived connection). Therefore, document **diagnostic cost**, timeouts, and allowed frequency. "Read-only" in a management API means not mutating business state, not zero resource consumption.

## 6. Separating the Management Interface Using CQRS

The Command Query Responsibility Segregation (CQRS) principle can be applied at a small management API level:

```java
public interface QueueDiagnostics {
    int getQueueDepth();
    long getCompletedCount();
    String getHealthSummary();
}

public interface QueueCommands {
    void pauseProcessing();
    void resumeProcessing();
    void requestRefresh();
}
```

Two interfaces separate responsibilities in code, even though JMX does not enforce authorization merely because they are separate Java interfaces. They can be exported as two MBeans with distinct ObjectNames:

```text
com.example.jobs:type=QueueDiagnostics,name=Main
com.example.jobs:type=QueueControl,name=Main
```

Separating ObjectNames makes allowlists, operations, and monitoring clearer. However, if both MBeans live in the same `MBeanServer`/connector with full admin access, the separation **does not automatically create a security boundary**. Read and invoke permissions must be enforced at the connector or runtime layer.

## 7. Complete Spring JMX Example: Read-Only MBean

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueDiagnostics,name=Main",
    description = "Observe queue without mutating state"
)
public class QueueDiagnosticsMBean {
    private final QueueMetrics metrics;

    public QueueDiagnosticsMBean(QueueMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Number of waiting jobs")
    public int getQueueDepth() {
        return metrics.pendingCount();
    }

    @ManagedAttribute(description = "Number of completed jobs")
    public long getCompletedCount() {
        return metrics.completedCount();
    }

    @ManagedAttribute(description = "Aggregate health status")
    public String getHealthSummary() {
        return metrics.safeHealthSummary();
    }
}
```

`QueueMetrics` is an application-defined interface/service. Getters should return bounded snapshots, avoid executing heavy database queries directly when collectors poll frequently, and contain no secrets or personal data.

With annotation-based export, `@ManagedAttribute` is applied only to getters so the attributes above are expected to be read-only. If an annotated setter is added later, the contract changes to writable and must be reviewed as an administrative privilege change.

## 8. Dedicated Control MBean

```java
package com.example.management;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=QueueControl,name=Main",
    description = "Queue control operations"
)
public class QueueControlMBean {
    private final QueueControlService commands;
    private final ManagementAudit audit;

    public QueueControlMBean(
            QueueControlService commands,
            ManagementAudit audit) {
        this.commands = commands;
        this.audit = audit;
    }

    @ManagedOperation(description = "Pause intake of new jobs")
    public void pauseProcessing() {
        commands.pauseProcessing();
        audit.record("pause-processing");
    }

    @ManagedOperation(description = "Resume job intake")
    public void resumeProcessing() {
        commands.resumeProcessing();
        audit.record("resume-processing");
    }

    @ManagedOperation(description = "Request worker configuration refresh")
    public void requestRefresh() {
        commands.requestRefresh();
        audit.record("request-refresh");
    }
}
```

`QueueControlService` and `ManagementAudit` are illustrative abstractions. For critical operations, auditing should record the request attempt, success/failure outcome, and a safe correlation ID rather than logging only after command execution succeeds. Never store secrets, tokens, or personal data in audit events.

## 9. Enabling Annotation-Based MBean Export

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Ensure both management beans are discovered or declared in the `ApplicationContext`. `@EnableMBeanExport` lets Spring configure infrastructure to read annotation metadata and export eligible management beans. If the application has a manual `MBeanExporter` using a reflection assembler, avoid exporting the same `ObjectName` or accidentally exposing extra public methods.

With the two-MBean design, operators can distinguish them quickly:

```text
JConsole
  com.example.jobs
    QueueDiagnostics, Main
      Attributes: QueueDepth, CompletedCount, HealthSummary
    QueueControl, Main
      Operations: pauseProcessing, resumeProcessing, requestRefresh
```

The actual UI depends on JConsole and the `MBeanInfo` produced by the assembler. What matters is not placing state-mutating operations on the diagnostic MBean just because both use the same underlying service.

## 10. Read-Only Management Adapters Must Not Expose Business Services

Anti-pattern:

```java
@ManagedResource
public class JobService {
    public int getQueueDepth() { /* ... */ return 0; }
    public void deleteAllJobs() { /* ... */ }
    public void retryFailedJob(String id) { /* ... */ }
}
```

When using a reflection assembler, public methods such as `deleteAllJobs` can become unintended JMX operations. Having `@ManagedResource` on a class also does not guarantee safety if the exporter uses a different assembler that ignores annotation allowlisting.

Export a dedicated management adapter and annotate only methods intended for management. When source code cannot be modified, use `InterfaceBasedMBeanInfoAssembler` or `MethodNameBasedMBeanInfoAssembler` to create a controlled allowlist.

Never confuse a `public` Java method with "permitted to invoke via JMX." A management contract must be an intentional choice.

## 11. Naming Conventions for Queries and Commands

### Diagnostic Group

Clear prefixes: `get...`, `is...`, `list...`, `describe...`, `sample...`, `getStatus...`, `getSummary...`. If parameters or non-trivial computation are involved, use operations like `collect...` or `run...Probe` with documented cost instead of turning them into endlessly polled getters.

Examples:

```text
getActiveWorkerCount
getQueueDepth
getLastSafeErrorCategory
getConnectionState
collectThreadSummary(maxThreads)
```

### State-Mutating Group

Names should convey active intent: `request...`, `pause...`, `resume...`, `clear...`, `reset...`, `reload...`, `rotate...`, `shutdown...`. Avoid vague names like `update()`, `fix()`, or `checkAndRepair()` where operators cannot tell the scope of impact.

Examples:

```text
requestRefresh
pauseProcessing
resumeProcessing
clearCache
resetFailureCounters
requestShutdown
```

In Java, names do not enforce semantics. Names only aid understanding of the contract; enforcement still lives in implementation, security, and tests.

## 12. Commands Need Validation and Resource Bounds

Example operation modifying a worker limit:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Change worker limit")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "limit", description = "Value from 1 to 64"
    )
})
public void setWorkerLimit(int limit) {
    if (limit < 1 || limit > 64) {
        throw new IllegalArgumentException(
            "limit must be within [1, 64]"
        );
    }
    commands.updateWorkerLimit(limit);
}
```

Never allow operators to set unbounded values that exhaust CPU, threads, or memory. For every command, define:

- Preconditions.
- Valid value ranges.
- Post-success state and behavior on repeated calls.
- Timeouts, concurrency, and conflict handling when two operators invoke simultaneously.
- Rollback or recovery strategy if the operation fails midway.
- Auditing and required permissions.

A command returning `void` does not mean it completes instantaneously. For long-running work, return a non-sensitive `requestId` or expose progress via a diagnostic attribute rather than leaving a JMX invocation hanging indefinitely.

## 13. Idempotency for State-Mutating Operations

Commands such as `pauseProcessing()` can usually be made idempotent: calling them twice leaves the system in the paused state. Commands like `retryJob()` or `clearCache()` may not share that property.

Example:

```java
@ManagedOperation
public void pauseProcessing() {
    if (!state.isPaused()) {
        state.pause();
    }
}
```

In concurrent environments, a simple check-then-act snippet has a race condition if multiple threads mutate state simultaneously; the implementation needs appropriate synchronization or atomic mechanisms. This example only illustrates the desired idempotent semantics.

Never automatically retry JMX commands with side effects after a timeout: the request may already have succeeded on the server while the client lost the response. When safe retries are needed, use a request ID / idempotency key and tracked command status.

## 14. Authorization: Splitting MBeans Does Not Automatically Split Permissions

Even though two ObjectNames `QueueDiagnostics` and `QueueControl` separate the management contract, a JMX client with server-wide invoke permissions can still invoke commands. You must design:

1. **Read-only operator/monitoring roles** authorized to read required attributes.
2. **Privileged operator roles** authorized to invoke permitted commands.
3. Authentication and authorization at the JMX connector or an appropriate MBean management layer.
4. Network segmentation, TLS, and credential management.
5. Auditing of control commands at the application layer.

Do not assume Spring Security protecting HTTP APIs automatically protects every JMX connector. For local JMX, effective permissions depend on the JVM, `MBeanServer`, and access environment.

Separating `QueueControl` into its own MBean makes reviews and policy writing easier, but provides real security only when properly enforced.

## 15. Diagnostics Should Return Snapshots, Not Raw Internal Data

Instead of:

```java
@ManagedAttribute
public List<Job> getPendingJobs() {
    return queue.getAllPendingJobs();
}
```

return aggregate metrics:

```java
@ManagedAttribute
public int getPendingJobCount() {
    return queue.pendingCount();
}
```

If sampling a small set of jobs is genuinely needed for debugging, use a parameterized, bounded operation:

```java
@ManagedOperation(description = "Sample at most N pending jobs")
public String getPendingJobSummary(int maxItems) {
    int limit = Math.max(1, Math.min(maxItems, 20));
    return diagnostics.safePendingJobSummary(limit);
}
```

Outputs must strip PII/secrets and enforce size limits, even for highly privileged operators. Diagnostic operations that return huge payloads or scan databases can slow the system down; apply timeouts/limits and keep them off critical-path threads.

## 16. Combine with One-Way Notifications

JMX notifications are useful to signal that an event has occurred:

```text
Control operation: requestRefresh
     |
     v
Command accepted
     |
     v
Background refresh
     |
     +--> Diagnostic attribute: RefreshState
     +--> Notification: refresh.completed / refresh.failed
```

Do not require operators to call `getRefreshState()` if reading it triggers a refresh on every poll. Diagnostics observe progress; commands initiate action; notifications announce state transitions.

When a client receives a notification, it should re-read attributes to confirm current state. JMX notifications can be lost when clients have not subscribed yet or when the connector drops; they are not a durable message broker.

## 17. Designing Long Operations with Request/Observe

A clean pattern for long-running operations:

```java
@ManagedOperation(description = "Request asynchronous index rebuild")
public String requestIndexRebuild() {
    return jobs.submitIndexRebuild();
}

@ManagedAttribute(description = "Latest rebuild status")
public String getIndexRebuildStatus() {
    return jobs.getSafeCurrentStatus();
}
```

`submitIndexRebuild` returns a safe request ID or an accepted status. A background worker performs the execution. Upon receiving completion events, the application may emit a notification.

With this approach, a JMX invocation does not hold a thread waiting until work finishes. Enforce concurrency limits on background jobs, reject when backlog is full, and define idempotency so operators do not accidentally launch multiple jobs.

## 18. Inspecting MBeanInfo to Verify the Contract

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName diagnostics = new ObjectName(
    "com.example.jobs:type=QueueDiagnostics,name=Main"
);
ObjectName control = new ObjectName(
    "com.example.jobs:type=QueueControl,name=Main"
);

for (ObjectName name : new ObjectName[]{diagnostics, control}) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println(name.getCanonicalName());
    for (var attr : info.getAttributes()) {
        System.out.printf(
            "  Attribute %s writable=%s%n",
            attr.getName(), attr.isWritable()
        );
    }
    for (var op : info.getOperations()) {
        System.out.println("  Operation " + op.getName());
    }
}
```

This snippet assumes both MBeans are registered in the platform `MBeanServer`. If the exporter uses a different server, inspect that exact server. Reading metadata verifies the final JMX contract; you do not need to invoke a state-mutating operation just to confirm it is in the API.

## 19. Common Design Mistakes

| Symptom | Root Cause | Improvement |
| --- | --- | --- |
| Dashboard reading a getter resets metrics | Getter has side effects | Move reset into an explicit command |
| Operator runs `diagnose()` and service restarts | Diagnostic operation bundles remediation | Split `getStatus` and `requestRestart` |
| Monitoring user can invoke `clearCache()` | Connector allows overly broad invoke access | Separate command permissions and enforce on server |
| Attribute unexpectedly writable | Public setter exported | Expose getter only or use metadata allowlist |
| Command executed multiple times after timeout | Client retries without idempotency | Use request ID, status, and retry policy |
| `getConfig()` returns secrets | Diagnostics dump raw config | Return safe summary, redact, and restrict fields |
| MBean has too many methods | Exporting business service via reflection | Selective management adapter/interface |
| Diagnostic operation slows down application | Unbounded scan of large resources | Bounded sampling, timeouts, and offloading |
| Command fails without audit trail | Missing attempt/result logging | Audit invocations and outcomes without secrets |

## 20. Management API Checklist

- [ ] JMX getters do not mutate business state.
- [ ] Writable attributes are explicitly identified and exposed only when needed.
- [ ] Diagnostic operations document cost, bounds, and return shape.
- [ ] Commands use active verbs and document side effects.
- [ ] Read and control management adapters/interfaces are separated where appropriate.
- [ ] Commands have validation, concurrency guards, timeouts, or idempotency.
- [ ] Side-effecting commands are not blindly retried after timeouts without idempotency.
- [ ] Diagnostics never return secrets, tokens, PII, or large object graphs.
- [ ] Invoke permissions are enforced independently, not assumed from MBean names.
- [ ] Critical commands have safe audit logging.
- [ ] `MBeanInfo` matches the expected attributes and operations.
- [ ] ObjectNames and the management contract remain stable for dashboards and proxies.

## 21. Closing Mental Model

```text
Spring application
   |
   +-- Query/Diagnostics API
   |      +-- getQueueDepth
   |      +-- getHealthSummary
   |      +-- getCompletedCount
   |      +-- collectBoundedSnapshot
   |      -> Read-only MBean
   |
   +-- Command/Control API
          +-- pauseProcessing
          +-- resumeProcessing
          +-- requestRefresh
          +-- requestIndexRebuild
          -> Privileged MBean
                  |
                  v
             Validation + Audit + Execution
                  |
                  v
             Status attribute / Notification
```

**Conclusion:** separating diagnostic commands from state-mutating commands makes Spring JMX a clearer, safer, and more stable management API. Getters and diagnostic operations should be lightweight, bounded, and non-mutating; commands must be explicit, permission-controlled, validated, concurrency-safe, and audited. Splitting into separate interfaces or MBeans is a clear design tool, while security still has to be enforced at the connector/`MBeanServer` and application logic layers.

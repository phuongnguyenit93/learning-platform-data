# Boundaries between observation, diagnosis, and state-changing control in Spring Framework JMX

## Goal

When looking at a Spring application through Java Management Extensions (JMX), what matters is not only knowing how to export an MBean or invoke an operation. Operators must distinguish three types of actions with different levels of impact: **observing** what state the system is in, **diagnosing** why it exhibits that behavior, and **controlling** it so the system transitions to another state.

After this lesson, you can:
- Classify an MBean's attributes, operations, and notifications by actual effect rather than merely by name or API type.
- Identify the safe boundary between reading metrics, running checks, and altering the state of a Spring application.
- Design a JMX management surface with least privilege, stability, and traceability.
- Evaluate the risks of actions such as refreshing a cache, changing logging levels, pausing a worker, resetting statistics, or triggering a reconnect.
- Build a troubleshooting mindset: evidence, hypotheses, controlled action, and outcome verification.

## 1. Three action layers and each layer's question

Think of JMX like a control panel in an engine room. The same interface can display temperature, let you run a self-test, and include a switch that changes how the machine operates. These three actions do not share the same safety level.

| Layer | Question | Example in a Spring application | Expected impact |
|---|---|---|---|
| Observation | What is happening? | Reading queue depth, active connection count, worker state | Does not alter business state |
| Diagnosis | Why is it happening? | Fetching a pool summary, computing backlog status, running a health probe | May consume resources or trigger secondary activity |
| Control | What needs to change? | Pause/resume, updating runtime config, resetting cache, triggering reconnect | Deliberately changes state or behavior |

This is a **classification by actual effect**, not by method name. A method named `getReport()` might scan millions of records; an operation named `checkConnection()` might open a real connection; an attribute with a setter is a control surface. Conversely, an operation that merely returns an existing snapshot can still belong to observation.

A quick way to distinguish them:

1. **Reading**: The result is primarily data; under the same conditions, calling it again should not significantly alter the system.
2. **Diagnosis**: The result is evidence to confirm or refute a hypothesis; the task may consume CPU, I/O, locks, or call downstream services.
3. **Control**: The goal is to change state, configuration, or processing flow; you must evaluate permissions, preconditions, side effects, and recovery plans.

The boundary is not always absolute. Reading a metric that increments an access counter or allocates temporary objects has a minor technical side effect; calling a health check that executes a real DB query is diagnosis with impact; resetting a counter is an action that changes management state, even if it does not modify business data.

## 2. What does the JMX surface tell you and what does it not tell you?

JMX presents management resources as MBeans, usually named with an `ObjectName`. Tools such as JConsole or Java Mission Control can inspect **attributes**, **operations**, **notifications**, and metadata. With Spring Framework, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, `MBeanExporter`, and `@EnableMBeanExport` help expose Spring objects to JMX.

However, the technical form of a member does not by itself confirm its impact:

- **Read-only attribute**: usually intended for observation, yet a getter can perform heavy computation or external queries.
- **Writable attribute**: a setter is a control command. Writing a value may trigger a reload, reschedule work, or affect incoming requests.
- **Operation**: may simply compute a result, run a probe, reset state, or drive business actions. Metadata and operation names are no substitute for reading the behavioral contract.
- **Notification**: announces an event that occurred; subscription and emission still carry cost, and notifications can be lost, delayed, or duplicated depending on design.

Therefore, do not adopt "operations are dangerous, getters are safe" as a policy. Policies must state the **effect**, **cost**, **data sensitivity**, and **usage permissions** for each item.

### 2.1 A sample management contract table

| JMX member | Classification | Contract to publish |
|---|---|---|
| `QueueDepth` (read-only) | Observation | Snapshot at read time; no guarantee the count stays the same immediately afterward |
| `LastFailureSummary` (read-only) | Observation, sensitive data | Mask personal info/tokens; bound output length and generation cost |
| `diagnoseBacklog()` | Diagnosis | May scan metadata; bound execution time, result size, and call rate |
| `probeDatabase()` | Diagnosis | Calls the real DB with a timeout; a passing probe does not mean the whole system is healthy |
| `setPauseRequested(true)` | Control | Affects only new work; in-flight work may complete |
| `resetCounters()` | Control | Loses in-memory metric baseline; record evidence before resetting |
| `clearCache()` | Control | Increases load on backing data systems after cache eviction; may cause cascading effects |

This table should appear in operational documentation. Someone looking at a method in a console cannot infer all of its consequences on their own.

## 3. Thinking about state: what are you reading or changing?

Application state is not a single variable. It can be divided into:

- **Observable state**: request counts, queue depth, latency, connection count, and latest timestamps.
- **Adjustable runtime state**: pause flag, log level, bounded worker count, maintenance mode.
- **Business state**: orders, transactions, payments, emitted events; these have their own source of truth.
- **External state**: databases, brokers, other services, other nodes, or infrastructure.

A JMX action may change local runtime state without automatically changing the state of the remaining nodes. For example, calling `pause()` on only one Spring Boot instance running in a three-node cluster is not a "stop the entire system" button. Likewise, calling `clearCache()` on JVM A does not necessarily clear caches on JVM B or a distributed cache.

Distinguish further between **control intent** and **effective outcome**. Setting `pauseRequested=true` only expresses a request. A `paused=true` state should reflect that the processor has actually stopped accepting new work. If this is an asynchronous process, the system should publish `requestedState`, `effectiveState`, `lastTransitionTime`, and `lastTransitionError` instead of returning premature success.

### 3.1 Mental diagram for an action

```text
Need to understand the problem
      |
      v
Read current state and recent history
      |
      v
Enough evidence? -- No --> Run bounded diagnostics
      |                           |
     Yes <------------------------+
      |
      v
Truly need to change state?
      |                |
     No               Yes
      |                |
Keep monitoring  Verify permissions, scope,
                 preconditions, risks
                       |
                       v
                 Execute one change
                       |
                       v
                 Read back effective state,
                 metrics, and side effects
```

Not every detected error requires control intervention. There are situations where observing further or fixing a root cause outside the JVM is the better decision.

## 4. Spring JMX example: separating state reading from pause/resume requests

The following example illustrates exporting an MBean for a background processor. Observation methods return simple snapshots; control commands have explicit action names. Authentication, authorization, auditing, and scope-control policies must be configured additionally at the management and infrastructure layers, because Spring annotations **do not automatically create an authorization system**.

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.operations:type=WorkerControl,name=ImportWorker",
    description = "Observation and controlled lifecycle actions")
public class ImportWorkerControl {

    private final AtomicBoolean pauseRequested = new AtomicBoolean();
    private final AtomicBoolean acceptingNewWork = new AtomicBoolean(true);
    private final AtomicLong completedJobs = new AtomicLong();
    private volatile String lastTransitionTime = Instant.now().toString();

    @ManagedAttribute(description = "Requested pause intent")
    public boolean isPauseRequested() {
        return pauseRequested.get();
    }

    @ManagedAttribute(description = "Whether new work is actually accepted")
    public boolean isAcceptingNewWork() {
        return acceptingNewWork.get();
    }

    @ManagedAttribute(description = "Completed job count since process start")
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @ManagedAttribute(description = "Timestamp of last effective transition")
    public String getLastTransitionTime() {
        return lastTransitionTime;
    }

    @ManagedOperation(description = "Request a pause of new work")
    public void requestPause() {
        pauseRequested.set(true);
        // The actual worker loop must observe this intent.
    }

    @ManagedOperation(description = "Request resuming new work")
    public void requestResume() {
        pauseRequested.set(false);
        // The actual worker loop must observe this intent.
    }

    // Called only by the worker lifecycle when state really changes.
    public void recordAcceptingNewWork(boolean accepting) {
        acceptingNewWork.set(accepting);
        lastTransitionTime = Instant.now().toString();
    }

    // Called after a job actually completes.
    public void recordCompletedJob() {
        completedJobs.incrementAndGet();
    }
}
```

You can enable the exporter with configuration appropriate to the application:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

In a Spring Boot application, check the active JMX configuration, how MBeans are registered, and potential `ObjectName` collisions before combining multiple export mechanisms. The example object is only a **control adapter**, not a complete worker. The real background processor must read `pauseRequested` at a safe point and call `recordAcceptingNewWork` when the state transition actually takes effect. If pausing can fail or take time, extend the contract with a `PAUSING` state, the latest error, and transition timestamps.

From the operator's perspective:

1. Reading `PauseRequested` and `AcceptingNewWork` is **observation**.
2. Comparing both values, transition history, queue state, and errors is **diagnosis**.
3. Calling `requestPause()` or `requestResume()` is **control**.
4. Reading both values again after the operation is **verifying effectiveness**, avoiding confusing "the operation call succeeded" with "the system reached the desired state".

## 5. Why can a diagnostic check be dangerous?

Diagnosis sits between reading and controlling, but it is not "harmless reading". An operation called `dumpAllSessions()` can allocate huge copies on the heap; `checkAllDependencies()` can call many services concurrently and contribute to overloading them; `threadDump()` or broad snapshot captures carry cost at a moment when the JVM is already under pressure.

Safe diagnostic design typically has these properties:

- **Bounded scope**: only one pool, one queue, one partition, one time window, or top-N.
- **Bounded resources**: timeouts, concurrency limits, record counts, result byte limits, and call rate limits.
- **No data leaks**: return only filtered summaries; avoid passwords, tokens, raw payloads, and user-identifying details.
- **Clear semantics**: report snapshot timestamps, lag, and that data across multiple indicators may not be mutually consistent.
- **Controlled failure**: if an external dependency times out, return a failed diagnostic status; do not automatically trigger self-healing modes or infinite retries.
- **Traceability**: record who ran it, when, the target, and a correlation ID if available.

For example, `diagnoseBacklog()` should return a bounded summary such as `queued=420, oldestAgeSeconds=95, sampledAt=...` instead of trying to serialize every job in the queue. If the summary requires scanning, documentation should state estimated cost and limits.

## 6. Control means change: a stronger contract is required

A state-changing operation should answer six questions before being exposed over JMX:

1. **Who** is allowed to invoke it? Are read-only privileges separated from control privileges?
2. **What changes**? One bean, one JVM, one tenant, one shard, or the whole cluster?
3. **What are the preconditions**? Is it forbidden during shutdown, migrations, or sensitive transaction processing?
4. **When does it take effect**? Synchronously or asynchronously, immediately or after the current job finishes?
5. **What happens on repeated calls**? Is it idempotent, does it report already in the desired state, or does it cause repeated side effects?
6. **How is it reversed**? Is there an inverse operation, an effective TTL, auto-expiry, or is a restart required?

A good control operation bounds blast radius, validates inputs, returns meaningful results, and writes audit logs. For instance, changing `logLevel=DEBUG` can increase I/O and log sensitive data; allow it only within approved loggers, for a bounded duration, and revert to the initial level automatically. Resetting a cache can cause a cache stampede; support a verified key/prefix rather than clearing everything by default.

Do not use JMX as an arbitrary business API. Creating orders, issuing refunds, or modifying customer data must go through application paths with proper authentication, business-invariant checks, auditing, and transaction controls. Attaching `@ManagedOperation` to a service does not provide those guarantees on its own.

### 6.1 Idempotency does not mean risk-free

`pause()` may be idempotent with respect to state: calling it twice still leaves the state as "paused". Yet calling it at the wrong time still disrupts the system. `clearCache()` sometimes achieves the same empty-cache state after two calls, yet two calls can trigger two waves of data reloading. Thus, idempotency is a useful property, **not a substitute** for controlling permissions, timing, and impact.

### 6.2 Handling races and outcomes

In a multithreaded system, reading and then deciding is not an atomic operation:

```text
T0: Operator A reads state RUNNING
T1: Operator B requests STOPPING
T2: Operator A invokes refresh/restart based on stale snapshot
```

If two commands conflict, there should be a state machine and a mechanism to reject operations that violate preconditions. For critical actions, a state version or conditional request helps avoid applying a command based on a stale snapshot. The JMX API does not provide this business atomicity automatically; application logic must enforce it.

## 7. Security: reading can also be a sensitive privilege

JMX can expose configuration, topology, operational metrics, exceptions, thread names, and details related to user data. Hence even a "read-only" JMX connection can carry sensitive information.

When enabling remote JMX, you must evaluate authentication, authorization, channel encryption, network restrictions, and endpoint configuration; do not leave management ports publicly open. In many deployments, accessing an MBeanServer/JMX connector with broad privileges can invoke unintended operations. Permissions enforced at the connector, MBeanServer, or appropriate guard layer must be verified in practice; a "read-only" label in documentation is not enough to block calls.

Operational principles:

- Prefer internal management channels, strong authentication, and encryption.
- Separate those who read metrics from those allowed to invoke state-changing operations.
- Minimize the number of exported operations; do not export public methods merely for convenience.
- Mask secrets and personal data from attributes, notifications, and exception messages.
- Audit control commands with caller identity, target, safe parameters, outcome, and timestamp.
- Verify boundaries per **instance**, especially in Kubernetes or multi-node clusters.

Spring JMX annotations primarily describe and export resources; they are **not** an automatic per-operation security layer.

## 8. Real-world scenario: rising backlog in a worker

Suppose the import-processing queue of a Spring service grows from 20 to 2,000 jobs and the completion rate drops. The difference between the three layers becomes clear.

**Step 1 — Observation:** Read `QueueDepth`, `CompletedJobs`, `ActiveWorkers`, `OldestJobAge`, and the last error timestamp. Observe trends across multiple points in time because a single snapshot can mislead. Check metrics dashboards and logs at the same time rather than relying solely on JMX.

**Step 2 — Diagnosis:** Hypotheses include a slow downstream service, retry failures, a paused worker, lock contention, or too few consumers. Run a bounded summary operation, and cross-check the connection pool and dependency latency. Do not run heavy probes across every node simultaneously while the system is overloaded.

**Step 3 — Decision:** If downstream is failing, adding more workers could make things worse. If the queue grew due to a configuration change, a controlled configuration rollback may make sense. If DB pressure needs to be reduced, requesting a pause on new work may help, but backlog and SLAs must be weighed.

**Step 4 — Control:** An authorized person invokes an operation with a clear scope, e.g., `requestPause()` on the specific instance. Record the reason, prior values, and operator.

**Step 5 — Verification:** Read `PauseRequested`, `AcceptingNewWork`, active job count, and queue depth; verify that no new jobs are picked up after pause takes effect. If the target state is not reached within the allowed window, do not automatically retry in an infinite loop.

A short runbook helps avoid the "see an error, hit reset" reflex:

```text
Symptom -> Time-stamped snapshot -> Hypothesis -> Bounded probe
-> Impact assessment -> Authorized command & preconditions
-> Verify effective state -> Monitor aftermath -> Record
```

## 9. Common misconceptions

**"Getters are always harmless."** A getter can run expensive computations, block on locks, make network calls, or leak secrets. Inspect the getter's implementation and contract.

**"If an operation can be called, it should be called during an incident."** Technical capability to execute does not imply justification or authorization to execute. Evidence and a decision process are required.

**"JMX command succeeded means the application changed state."** If the command only sets a flag or enqueues a request, you must read the effective state or observe behavior.

**"Pausing one instance means pausing the whole cluster."** An MBean typically belongs to one JVM. Controlling a cluster requires coordination mechanisms and clear scope documentation.

**"Resetting metrics is a read-only operation."** Resetting mutates observable data, breaks time-series continuity, and can erase diagnostic evidence.

**"Naming it `safeCheck()` makes a diagnostic safe."** You must bound resources, call frequency, returned data, and impact on dependencies.

**"An exported MBean automatically enforces per-operation authorization."** Spring's export annotations do not replace connector configuration, roles, and real access checks.

## 10. Design checklist before exporting an MBean

For each attribute or operation, explicitly document:

| Criterion | Check question |
|---|---|
| Purpose | Observation, diagnosis, or control? |
| Data | What snapshot does it return; can it be sensitive or stale? |
| Resources | How much CPU/heap/I/O/locks/downstream does it use, and how is it bounded? |
| Side effects | Does it mutate state, lose metrics, or trigger work? |
| Scope | Does it affect a thread, bean, instance, tenant, or cluster? |
| Permissions | Who can read, who can execute, and where are audit logs stored? |
| Concurrency | What happens if two operators invoke concurrently or state changes mid-flight? |
| Failure | What do timeouts, partial success, and error messages mean? |
| Recovery | Is there an inverse command, auto-expiration, or rollback runbook? |
| Verification | Which metric or effective state proves the outcome? |

If you cannot answer the questions on effects, scope, and permissions, a control operation is not clear enough to place on the operational surface.

## 11. Mental exercise

Given the following JMX members:

1. `getCacheHitRatio()`: reads numbers from existing counters.
2. `scanSlowQueries(1000)`: scans recent query logs, consuming CPU and memory.
3. `setConsumerCount(16)`: adjusts the number of active consumers.
4. `getRecentErrors()`: returns unfiltered stack traces and request parameters.
5. `resetRetryStatistics()`: resets retry counters.
6. `pingDownstream()`: sends a real request to another service.

Classify each item and state one safety condition for each. Suggested answers: (1) observation, define the calculation window for the ratio; (2) diagnosis, bound scope and resources; (3) control, validate allowed range, load capacity, and permissions; (4) observation with sensitive-data risk, must filter/redact; (5) control over metric state, save baseline before resetting; (6) diagnosis with network impact, set timeout/rate limit.

Extended exercise: design `WorkerControlMBean` with four read-only attributes (`RequestedState`, `EffectiveState`, `LastTransitionTime`, `LastTransitionError`) and two operations (`requestPause`, `requestResume`). Write a state machine handling `RUNNING → PAUSING → PAUSED → RESUMING → RUNNING`, describe safe points to stop accepting jobs, behavior on repeated calls, and how operators verify the outcome.

## Conclusion

In Spring Framework JMX, **observation** builds awareness of state, **diagnosis** investigates causes with bounded cost, and **control** deliberately transitions state under permissions and preconditions. The boundary lies in the true effect of each MBean member, its blast radius, and operational conditions. A well-designed JMX surface helps operators know clearly what is happening, why it might be happening, and when a state-changing action is valid, while providing evidence to verify whether that action achieved its intended effect.

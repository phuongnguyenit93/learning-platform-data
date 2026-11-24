# Designing Operations Safe for Repeated Invocations in Spring JMX

## 1. Why Can an Operation Be Invoked Multiple Times?

In Spring Framework JMX, a method annotated with `@ManagedOperation` can be exposed as a **JMX operation** for management tools to invoke through `MBeanServer` or `MBeanServerConnection`. An operation can be used to reset metrics, refresh caches, reload configuration, pause a processor, or start a maintenance task.

Example:

```java
@ManagedOperation(description = "Reload runtime configuration")
public void reloadConfiguration() {
    // Read and apply current configuration.
}
```

Never assume an operation will be invoked only once. In practice, the same operation can be invoked repeatedly because:

- An operator clicks the **Invoke** button multiple times in JConsole or another JMX tool.
- An administrative script retries after a timeout because it does not know whether the previous call executed.
- Two monitoring tools or two staff members act at the same time.
- An automated system invokes the operation on a schedule or when an alert fires.
- A remote JMX connection drops after the server executed the action but before the client received the response.
- The runtime executes multiple administrative calls concurrently on separate threads.

An operation lacking safety design can reset the wrong state, launch two tasks simultaneously, send duplicate notifications, delete data multiple times, or change configuration unexpectedly.

**Goal:** define clear behavior for repeated calls, concurrent calls, and uncertain execution outcomes.

## 2. Distinguishing Idempotency, Thread Safety, and Retry Safety

These three properties are related but not identical.

### 2.1. Idempotency

An operation is **idempotent** when executing it multiple times with the same request context has the same final state effect as executing it once.

Conceptual representation:

```text
f(f(state)) = f(state)
```

Example:

```java
public void pause() {
    paused = true;
}
```

Calling `pause()` once or multiple times drives the state toward `paused=true`. This is idempotency in final state, assuming no other side effects exist.

Conversely:

```java
public void incrementCounter() {
    counter++;
}
```

is not idempotent: calling it twice increments the counter twice.

### 2.2. Thread Safety

A method can be conceptually idempotent yet still unsafe when multiple threads run concurrently.

Example:

```java
if (!started) {
    startWorker();
    started = true;
}
```

Two threads can both observe `started=false` and both call `startWorker()`. As a result, the worker is started twice even though `start()` sounds idempotent.

Synchronization, atomic state transitions, or a proper lifecycle management mechanism are required.

### 2.3. Retry Safety

An operation retried after a timeout must handle the case where **the server may have already executed it**. Even a thread-safe operation is not necessarily retry-safe if it has external side effects.

For example, `sendReport()` has a synchronization lock, yet each call sends a new email. When the client retries, recipients can still receive duplicates.

If a task has side effects that do not cancel out on their own, you need a **request ID/idempotency key**, persisted task results, or deduplication at the exact impact boundary.

## 3. Grouping Operations by Risk Level

| Operation Type | Example | Problem When Repeated | Design Approach |
| --- | --- | --- | --- |
| Read state | `getHealthSnapshot()` | Increased load, snapshot shifts | Keep read-only, cap cost |
| Set state | `pause()`, `setEnabled(true)` | Final state usually unchanged | Idempotent state transition |
| Reset counters | `resetStatistics()` | Can lose data measured between resets | Define reset boundary and timing |
| Refresh cache | `refreshCache()` | Duplicate work, higher downstream load | Single-flight or coalesce |
| Launch job | `startReindex()` | Multiple jobs contending for resources | State machine, operation ID |
| Emit external effect | `sendNotifications()` | Duplicate sends, duplicate records | Idempotency key, durable deduplication |
| Delete data | `purgeExpiredData()` | May affect newer data or be hard to roll back | Clear selection criteria, permission guard, async execution |

Not every operation needs an idempotency key or a database storing history. Choose a mechanism matching the **actual impact** of the method.

## 4. Basic Example: Idempotent Pause and Resume

Suppose a processor needs to transition between two states: running and paused.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public class WorkerControl {
    private final AtomicBoolean paused = new AtomicBoolean(false);

    public boolean isPaused() {
        return paused.get();
    }

    public void pause() {
        paused.set(true);
    }

    public void resume() {
        paused.set(false);
    }
}
```

These methods are state-idempotent:

```text
pause(); pause();    -> paused = true
resume(); resume();  -> paused = false
```

However, if pausing must actually stop accepting work, close connections, or emit events, changing a flag alone is not enough. Tie the state to real resources and decide whether side effects may be re-emitted.

### Operations Can Return Transition Results

```java
public boolean pause() {
    return paused.compareAndSet(false, true);
}
```

Return value:

- `true`: this call transitioned the state from running to paused.
- `false`: the state was already paused beforehand.

This helps when callers need to know whether the operation actually changed state. Do not treat `false` as an error if the operator's goal is simply “ensure the system is paused.”

### Wrapping with Spring @ManagedOperation

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.workers:type=WorkerControl,name=primary",
    description = "Worker lifecycle management"
)
public class WorkerManagement {
    private final AtomicBoolean paused = new AtomicBoolean();

    @ManagedAttribute
    public boolean isPaused() {
        return paused.get();
    }

    @ManagedOperation(description = "Pause processing if not paused")
    public boolean pause() {
        return paused.compareAndSet(false, true);
    }

    @ManagedOperation(description = "Resume processing if paused")
    public boolean resume() {
        return paused.compareAndSet(true, false);
    }
}
```

The snippet above illustrates atomic transitions; a production application must ensure schedulers/consumers actually honor the `paused` flag.

## 5. Preconditions and Postconditions When Invoking Operations

A safe operation needs sufficiently clear **preconditions** and **postconditions**.

Example `reloadConfiguration()`:

- Precondition: the new configuration is valid and the config source is reachable.
- While running: do not expose half-updated configuration to other threads.
- Postcondition on success: all relevant components use the same applied configuration version.
- On failure: retain the previous configuration or move to an observable error state; never leave the system in an indeterminate state.
- When repeated for the same version: do not re-apply unnecessary side effects.

An operational contract should answer:

1. Does calling again after completion do anything extra?
2. Will calling while already running be rejected, wait, or coalesce into the active task?
3. On timeout, how does the client check the outcome?
4. Can an error leave partial work behind?
5. Is a request identifier needed to distinguish two intentional executions?

## 6. Single-Flight: Allowing Only One Task to Run at a Time

For a cache refresh operation, two concurrent calls can load data simultaneously, spike database load, or race when writing snapshots. One solution is **single-flight**: only one refresh runs at a time.

```java
import java.util.concurrent.atomic.AtomicBoolean;

public class CacheRefreshService {
    private final AtomicBoolean refreshing = new AtomicBoolean();

    public boolean refresh() {
        if (!refreshing.compareAndSet(false, true)) {
            return false; // Another refresh is already running.
        }

        try {
            loadAndPublishNewSnapshot();
            return true;
        } finally {
            refreshing.set(false);
        }
    }

    private void loadAndPublishNewSnapshot() {
        // Build a complete new snapshot, then publish it atomically.
    }
}
```

Spring management adapter:

```java
@ManagedOperation(
    description = "Refresh cache; returns false if refresh is running"
)
public boolean refreshCache() {
    return refreshService.refresh();
}
```

This prevents overlapping runs **within the same object/JVM** at the same time. It does not guarantee running only once across multiple JVMs, multiple replicas, or over time after the previous run finished.

If multiple clients call again after the refresh finishes, the task may run again. To coalesce calls for the same request/version, design an operation key or check the currently applied version.

### Choosing Behavior for Calls While Running

Possible contracts include:

- Return `ALREADY_RUNNING` along with the active operation ID.
- Return `false` and document the “already running” meaning.
- Wait for the current task with a bounded timeout.
- Enqueue a new task if operational requirements genuinely demand it.

Do not silently run two expensive tasks if the system only permits one at a time.

## 7. Asynchronous Operations and Tracking Status

Long operations such as index rebuilding, full cache warm-up, snapshot backup, or system synchronization usually do not suit long synchronous JMX calls.

Better design:

```text
startReindex()
    -> return operation ID
    -> worker runs asynchronously
    -> JMX attributes report status
    -> client tracks progress/outcome
```

Example management contract:

```java
public interface ReindexManagementMBean {
    String startReindex();
    String getCurrentOperationId();
    String getCurrentStatus();
    int getProgressPercent();
}
```

Statuses can include:

```text
IDLE
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

Important design points:

- An operation ID must correspond to **a single execution**.
- While running, subsequent `startReindex()` calls need a consistent policy: return the current ID or explicitly reject.
- Clients can inspect status after a timeout without restarting the job.
- When the process restarts, whether an in-flight operation is recovered is a separate decision; never promise durability if state lives only in memory.
- If a job has durable side effects, manage checkpoints/recovery appropriately.

### A Simple State Machine

```text
IDLE --start--> RUNNING
RUNNING --success--> SUCCEEDED
RUNNING --error--> FAILED
RUNNING --cancel--> CANCELLED
SUCCEEDED/FAILED/CANCELLED --new start--> RUNNING
```

A system may require additional states like `STOPPING` or `CANCELLING`. Valid transitions must be defined up front to prevent race conditions.

## 8. Idempotency Keys When Operations Have External Side Effects

Suppose an operation:

```java
@ManagedOperation
public void publishReport() {
    reportPublisher.publish();
}
```

If the client retries after a timeout, the report could be sent twice. For work with side effects that must avoid duplication, add a caller-supplied **operation key**:

```java
@ManagedOperation(
    description = "Publish a report once per request key"
)
public String publishReport(String requestKey) {
    return reportService.publishOnce(requestKey);
}
```

Contract:

1. The caller generates a unique `requestKey` for one business intent.
2. Every retry of the same intent reuses **that exact key**.
3. The server checks whether the key has already been accepted/completed.
4. If already completed, return the stored status/result; create no new side effects.
5. If currently running, return `IN_PROGRESS` or the current operation ID.
6. If the key is new, execute according to the controlled workflow.

### Is an In-Memory Map Enough?

A `ConcurrentHashMap` can prevent duplicates within one JVM while the process stays alive, yet it is **insufficient** if guarantees must survive restarts or multiple replicas.

For critical side effects, use storage capable of synchronization and durable persistence, such as a database with a unique constraint on `requestKey` and operation status. You still must handle the gap between “recording status” and “executing the side effect”; when communicating with external systems, you may need a transactional outbox, downstream idempotency support, or a reconciliation process.

**An idempotency key reduces duplicate processing risk; it does not automatically make an external side effect exactly-once in all scenarios.**

## 9. Race Condition: Check-Then-Act

Code like:

```java
if (!jobRunning) {
    jobRunning = true;
    startJob();
}
```

is unsafe when two threads call concurrently. Both can read `false`.

Solution using atomic CAS:

```java
import java.util.concurrent.atomic.AtomicBoolean;

private final AtomicBoolean running = new AtomicBoolean();

public boolean startJob() {
    if (!running.compareAndSet(false, true)) {
        return false;
    }

    try {
        runJob();
        return true;
    } finally {
        running.set(false);
    }
}
```

This is the basic safe pattern for a synchronous task in a single JVM. When offloading to a background worker, do not reset `running` right after submitting the task, because the task is still running. State must be reset **when the task actually finishes**, whether on success or failure.

### With a Background Task

```java
public boolean startAsyncJob() {
    if (!running.compareAndSet(false, true)) {
        return false;
    }

    try {
        executor.execute(() -> {
            try {
                runJob();
            } finally {
                running.set(false);
            }
        });
        return true;
    } catch (RuntimeException ex) {
        running.set(false); // Submission failed.
        throw ex;
    }
}
```

This pattern handles executor submission rejection, though it does not yet include operation IDs, progress, durable results, or distinct failure states. For production, use an explicit state machine.

## 10. Avoid “Toggle” Actions When Idempotency Is Desired

An operation such as:

```java
public void toggleEnabled() {
    enabled = !enabled;
}
```

is not idempotent:

```text
enabled=false
toggle() -> true
toggle() -> false
```

If the client retries, the state can flip back to the original value, contrary to intent.

Clearer design:

```java
public void enable() {
    enabled = true;
}

public void disable() {
    enabled = false;
}
```

Or a read–write attribute:

```java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
```

This communicates the **target state** instead of inverting state. Even so, if the setter triggers side effects on every call, design it to act only when the value actually transitions.

## 11. Resetting Statistics: Define What Calling Twice Means

`resetStatistics()` looks like an idempotent operation, yet you must consider continuously updated data.

Suppose a counter is 100:

```text
T0: count = 100
T1: reset() -> count = 0
T2: 5 new requests arrive -> count = 5
T3: retry reset() -> count = 0
```

If called again at T3, the 5 new requests are also erased from statistics. Thus, two resets **are not equivalent to one reset** when intervening state changes occur.

How to handle depends on intent:

- If “reset right now” is a new intentional action, two resets may be acceptable.
- If a retry of the same intent must not erase metrics produced after the first reset, a request ID or sequence/version is needed.
- If metrics are important, you can use an **epoch** or snapshot to mark the reset point instead of irreversibly wiping measurement data.

Example using an epoch:

```text
statisticsEpoch = 42
resetStatistics(expectedEpoch=42)
    -> bump epoch to 43, return 43

retry resetStatistics(expectedEpoch=42)
    -> sees current epoch is 43, does not reset again
```

Concurrent interaction with counter updates must be designed carefully; an epoch does not automatically solve all race conditions.

## 12. Reloading Configuration: Version-Based Application

With `reloadConfiguration()`, if the configuration source changed between two calls, the same operation can apply two different versions. Therefore, define what “repeated call” is relative to.

A stable approach:

```java
@ManagedOperation(
    description = "Apply a specific validated config version"
)
public String applyConfiguration(String version) {
    return configurationService.applyVersion(version);
}
```

The server can:

1. Check the currently applied version.
2. If the current version matches, return `ALREADY_APPLIED`.
3. If different, load and validate the specific configuration version.
4. Build the complete new state/configuration.
5. Apply it via a controlled transition.
6. Record the version and outcome for clients to observe.

Do not rely merely on the method name `reload` to assume it is idempotent. A reload might emit events, reconnect downstream clients, or alter system configuration on every call.

## 13. What Should an Operation Return So Clients Know the Outcome?

An operation returning only `void` makes it hard for clients to distinguish cases:

- Executed and succeeded.
- Already ran previously so nothing more was done.
- Another task is currently running.
- Request accepted but not yet finished.
- Call failed because preconditions were not met.

For simple operations, `boolean` can suffice when clearly documented:

```text
true  = state was changed by this call
false = already in the desired state
```

For complex operations, you can return:

```text
STARTED
ALREADY_RUNNING
ALREADY_APPLIED
REJECTED
```

If returning a `String` status, standardize the supported values. With MXBeans, consider Open Types or simple types so generic JMX clients can read them.

For long tasks, return an operation ID and provide separate status attributes. A synchronous response returning `STARTED` **does not mean the work is complete**.

## 14. Errors, Timeouts, and Uncertain Outcomes

When a JMX client invokes an operation remotely, consider:

```text
Client -> invoke() -> Server
                 Server processes successfully
Client <- disconnects before receiving response
```

The client sees a timeout or connection error and cannot be certain whether the server executed the action. Therefore:

- Do not retry non-idempotent side-effecting operations by default.
- For state/version-idempotent operations, retrying may be safe when the contract permits.
- For operations with a request key, retry using the same key.
- For async operations, query status via the operation ID.
- For operations that do not support retries, inspect state first before deciding to re-invoke.

**A connection error only proves the client did not receive a reliable response; it does not prove the server did not execute.**

### Distinguishing Business Errors

An operation can throw an exception due to invalid data, disallowed current state, or failing downstream resources. JMX wraps/surfaces errors via appropriate exception types such as `MBeanException`, `ReflectionException`, or connection errors.

Clients should examine the root cause and signature metadata rather than assuming every error is worth retrying.

## 15. Avoid Side Effects in Getters and Watch Out for “Read” Operations

Some systems expose operations like:

```java
@ManagedOperation
public String inspectQueue() {
    return queueService.describe();
}
```

If read-only, the operation should not mutate business state. However, `inspectQueue()` can still cause high load, lock contention, or network calls. Not mutating state does not mean calling repeatedly has zero impact on the system.

Getters/operations used for periodic monitoring should:

- Have time and resource bounds.
- Avoid huge queries, unbounded blocking, or excessive data dumps.
- Use cached snapshots when appropriate.
- Be clearly documented as read-only along with any performance impact.
- Never produce side effects such as “read means delete” or “viewed means acknowledged.”

## 16. @ManagedOperation and Annotation Metadata

Spring Framework provides:

```java
@ManagedOperation(
    description = "Start a cache refresh when no refresh is running"
)
public boolean startRefresh() {
    return refreshService.tryStart();
}
```

The annotation helps the exporter publish the operation and its description. Parameter metadata can be added:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(
    description = "Apply a configuration version idempotently"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "version",
        description = "Immutable configuration version identifier"
    )
})
public String applyConfig(String version) {
    return configurationService.applyVersion(version);
}
```

The services `refreshService` and `configurationService` are illustrative components that must be defined/injected in a real application. Annotations **do not automatically add idempotency, synchronization locks, or retry logic**. They only supply metadata so JMX clients can invoke the method.

A compatible exporter, such as `AnnotationMBeanExporter`, is also required for Spring to read the annotations and register MBeans.

## 17. Securing Administrative Operations

Because JMX operations can alter runtime state, appropriate protective boundaries are required:

1. Do not expose sensitive operations without a clear operational need.
2. Protect remote JMX with authentication, TLS, and network access restrictions.
3. Enforce authorization for dangerous actions; `@ManagedOperation` is not an authorization mechanism on its own.
4. Log/audit state-changing actions as needed, including operation name, ObjectName, request key, timestamp, and outcome; avoid logging secrets.
5. For dangerous tasks, design an approval workflow or dedicated API if the system requires it.
6. Never treat a method name like `safeReset` as proof of safety; inspect the actual implementation and side effects.

Note: JMX auditing does not always carry full user identity across all environments; caller identification capability depends on connector/security configuration.

## 18. Testing Repeated Invocation Scenarios

A useful test suite for critical operations should cover the following cases:

| Case | Goal |
| --- | --- |
| Single invocation | Succeeds according to contract |
| Two consecutive invocations | Produces no unintended side effects |
| Two threads calling concurrently | Does not start two jobs if only one is allowed |
| Re-invoked while job is RUNNING | Returns clear status/ID |
| Re-invoked after SUCCEEDED | Behavior matches policy |
| Invoked after simulated timeout | State can be determined before retrying |
| Operation throws exception | State is cleaned up/recorded properly |
| Executor rejects task | Does not leave RUNNING flag stuck |
| Restart mid-job | Accurately reflects recovery capabilities |
| Multiple replicas receiving requests | Coordinates if system-wide behavior is required |

### Testing Concurrency with ExecutorService

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ConcurrentStartTest {
    public static void main(String[] args) throws Exception {
        CacheRefreshService service = new CacheRefreshService();
        CountDownLatch gate = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Boolean>> calls = new ArrayList<>();
            for (int i = 0; i < 8; i++) {
                calls.add(() -> {
                    gate.await();
                    return service.refresh();
                });
            }

            List<Future<Boolean>> results = new ArrayList<>();
            for (Callable<Boolean> call : calls) {
                results.add(pool.submit(call));
            }

            gate.countDown();
            for (Future<Boolean> result : results) {
                System.out.println(result.get());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

This is a **simulation pattern**. If `refresh()` finishes very quickly, multiple calls may run sequentially and all return true; that does not prove single-flight is broken. To properly verify the “no overlap” condition, keep the task in the RUNNING state long enough using a latch in the test or measure maximum concurrent tasks with a counter. Tests should assert real invariants rather than merely counting `true` results without controlling timing.

## 19. Observing Operation Outcomes via MBean Attributes

A well-designed management MBean should expose status for clients to inspect:

```text
Attributes:
  Status            RUNNING
  CurrentOperationId 42f...
  LastSuccessTime   2026-11-11T...
  LastError         <short summary>
  ProgressPercent   75

Operations:
  startRefresh()
  cancelRefresh()
```

These attributes help:

- Identify an operation currently in progress.
- Avoid blind retries after timeouts.
- Distinguish an accepted request from completed work.
- Let operators see errors without re-running the task.
- Monitor progress of long-running actions.

If providing `LastError`, avoid placing large stack traces, tokens, or sensitive data into JMX attributes. For long historical state, use proper logging/metrics systems instead of exposing entire histories as an attribute.

## 20. Clear Operation Naming and Contracts

Operation names should convey the **target state or concrete action**:

| Prefer | Reconsider | Reason |
| --- | --- | --- |
| `pauseProcessing()` | `toggleProcessing()` | Clear target state, easy to retry |
| `applyConfigVersion(String)` | `reloadEverything()` | Version identifies the request |
| `startReindex()` returning ID | Long `reindex()` with unclear status | Task can be observed |
| `refreshCacheIfIdle()` | Overlapping `refreshCache()` | Clear concurrency contract |
| `resetStatistics(expectedEpoch)` | Unconditional retry of `resetStatistics()` | Avoids wiping newer metrics |
| `getRefreshStatus()` | Re-invoking `refresh()` to check outcome | Separates query from command |

Long names are not always necessary. What matters is that descriptions explain behavior on repeated calls, while running, and on failure.

## 21. Design Patterns by Practical Scenario

### Case A: Toggling Features On/Off

Use state setters or operations setting a target state:

```java
public void enable()  { enabled.set(true); }
public void disable() { enabled.set(false); }
```

Idempotent in state, and thread-safe when using appropriate atomic state and triggering side effects only on state transitions.

### Case B: Cache Refresh

Use single-flight to prevent overlapping runs. If callers need to retry after timeouts, expose `RUNNING/SUCCEEDED/FAILED` status and an operation ID.

### Case C: Sending Data to an External System

Use an idempotency key and deduplication storage matching durability requirements. If the downstream system supports idempotent requests, pass the key according to the downstream contract.

### Case D: Resetting Metrics

Decide whether a reset is an action at invocation time or an identified request. If retries must not wipe newer data, use an epoch/version or request key.

### Case E: Running Long Maintenance Tasks

Use async jobs, status attributes, operation IDs, and lifecycle controls; avoid blocking JMX callers synchronously for unbounded durations.

## 22. Safe @ManagedOperation Design Checklist

Before exposing an operation via JMX, answer:

1. **Effect:** what state does the operation mutate and which resources does it affect?
2. **Idempotency:** do two calls with the same intent yield the same state and side effects?
3. **Concurrency:** can two concurrent clients cause a race condition?
4. **Retry:** on timeout, can the client determine whether the server already executed?
5. **Identity:** is a request ID, operation ID, or configuration version needed?
6. **State:** while running and upon completion, how do clients observe status?
7. **Error:** if it fails mid-way, does state remain valid and recoverable?
8. **Lifecycle:** if the JVM shuts down/restarts mid-task, how is the outcome handled?
9. **Security:** who is permitted to call the operation, and is auditing needed?
10. **Performance:** can the operation block, hold locks, or create heavy load?
11. **Scope:** is single-flight within one JVM sufficient, or is multi-replica coordination needed?
12. **Contract:** are description, parameters, return type, and ObjectName clear enough for operators?

## 23. Self-Check Questions

**1. Is a method annotated with `@ManagedOperation` automatically idempotent?**

No. The annotation only publishes JMX metadata; idempotency must come from method logic and managed side effects.

**2. Why is `toggleEnabled()` not retry-safe?**

Because calling it twice can flip state back to its original value. Target-state operations like `enable()` or `disable()` are easier to guarantee.

**3. Is `AtomicBoolean` enough to prevent duplicate runs across multiple replicas?**

No. It only synchronizes the state of one object inside one JVM. Multiple replicas need shared coordination or deduplication if system-wide guarantees are required.

**4. Is resetting counters always idempotent?**

No. If new data arrives between two resets, a retry can erase newer data. Define the reset contract by timestamp, epoch, or request ID.

**5. Does a timeout error from a JMX client prove the server has not executed?**

No. The server may have finished processing while the response never reached the client. Query state before retrying.

**6. When is an operation ID needed?**

When tasks run long, asynchronously, or clients need to know status/results after a connection interruption.

**7. Why does single-flight not guarantee exactly-once by itself?**

Because single-flight only prevents concurrent overlap within its protection scope; calling again after the task finishes can still trigger a new run, and multiple JVMs do not share state unless coordinated.

**8. Why does `synchronized` alone not solve retries?**

Because `synchronized` only controls concurrency within a single object/JVM; it does not recognize a previously executed request or external side effects.

## 24. Summary

When designing a Spring JMX `@ManagedOperation`, assume the operation can be invoked **multiple times, concurrently, and under uncertain outcome conditions**. A safe operation needs clear contracts for those scenarios.

- **Set target state** instead of toggling when idempotency is desired.
- **Atomic transitions or state machines** handle in-JVM concurrency.
- **Single-flight** prevents overlapping task runs.
- **Operation IDs and observable state** let clients handle timeouts without blind retries.
- **Idempotency keys/versions and suitable storage** are necessary when durable side effects must avoid duplication across restarts or replicas.
- **Authorization, validation, and auditing** protect high-impact administrative operations.

Key takeaway: **`@ManagedOperation` only makes a method visible to JMX; safety under repeated invocations must be engineered into the method's behavior and the components it controls.**

### References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE API — `MBeanServerConnection.invoke`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE API — `AtomicBoolean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html

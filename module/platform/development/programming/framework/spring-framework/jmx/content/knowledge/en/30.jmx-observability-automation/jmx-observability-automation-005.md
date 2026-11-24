# Scheduled Jobs Invoking Operations and Checking Conditions in Spring Framework JMX

## 1. Learning Objectives

In a long-running Java system, a JMX operation is not always invoked manually by an administrator via JConsole. A **scheduled job** can connect to an `MBeanServer`, read attributes, evaluate operational conditions, and decide whether to invoke a management operation. This pattern appears in automated recovery, controlled cache eviction, maintenance triggers, processing-mode switches, or scheduler health verification.

This lesson belongs to the **Observability and Automation** group of Spring Framework JMX. The focus is on designing a **scheduled job that invokes operations and checks conditions** intentionally, with measurable outcomes, bounded impact, and without turning the JMX channel into an uncontrolled source of dangerous command execution.

After this lesson, you will be able to:

- Distinguish between a **state-polling** job and a **control-executing** job.
- Read attributes via `MBeanServerConnection.getAttribute(...)`.
- Invoke operations via `MBeanServerConnection.invoke(...)` with the right `ObjectName`, arguments, and signature.
- Use Spring `@Scheduled` or an appropriate scheduler for periodic execution.
- Structure the flow: observe → evaluate condition → prevent duplicate calls → execute → verify → record.
- Recognize race conditions, timeouts, mid-flight disconnects, and multi-job concurrency effects.
- Design idempotency, cooldowns, bounded retries, auditing, access permissions, and automation kill switches.
- Distinguish MBean metadata from current state and final operation outcome.

## 2. The Real-World Problem

Suppose an application has a background processor `WorkerControl` exported via Spring JMX. The MBean exposes:

```text
ObjectName:
com.example.ops:type=WorkerControl,name=Primary

Attributes:
- PendingJobs: int (read-only)
- AcceptingJobs: boolean (read-only)
- LastMaintenanceResult: String (read-only)

Operations:
- pauseProcessing()
- resumeProcessing()
- requestMaintenance()
```

Requirement: at a regular interval, an administrative job checks the number of waiting jobs. If `PendingJobs` exceeds a threshold continuously over a window, rather than automatically “wiping the whole queue,” the system can raise an alert or request controlled maintenance. After invoking, the job verifies whether the operation was accepted and whether the state transitioned properly.

Core principle: **trigger conditions must be tied to a concrete operational goal and risk controls**—do not invoke a state-changing operation merely because a metric looks high.

Example condition:

```text
pendingJobs > 500
AND processing state is still RUNNING
AND threshold breached >= 3 consecutive polls
AND no maintenance is currently running
AND cooldown has elapsed
THEN requestMaintenance()
```

This is an illustrative condition. Real thresholds must be based on system capacity, business requirements, operation cost, and recoverability.

## 3. Architectural Flow

```text
Scheduler / @Scheduled
         |
         v
   Read MBean attributes
         |
         v
    Evaluate condition
         |
    +----+----------------------+
    | condition false          | condition true
    v                          v
   Record                       Check safety guards
   observation                    |
                                  +-- maintenance running? -> SKIP
                                  +-- cooldown active?     -> SKIP
                                  +-- not authorized?      -> STOP
                                  |
                                  v
                             Invoke operation
                                  |
                                  v
                             Verify outcome
                                  |
                                  v
                        Metrics / logs / audit / alerts
```

Three groups of responsibilities should be separated:

1. **Observer**: reads state and produces evidence for conditions.
2. **Decision policy**: determines when execution is allowed, including thresholds, hysteresis, cooldowns, permissions, and scope.
3. **Executor**: invokes the operation per contract, records, and verifies the result.

This separation allows testing the policy without invoking real operations, especially for operations with major side effects.

## 4. JMX Is an Access Mechanism, Not a Scheduler

JMX provides `MBeanServer`, `MBeanServerConnection`, ObjectNames, attributes, and operations. It **does not run on a schedule automatically** just because a method has `@ManagedOperation`.

Spring JMX example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.ops:type=WorkerControl,name=Primary",
    description = "Operational controls for background workers"
)
public class WorkerControl {

    @ManagedAttribute(description = "Number of pending jobs")
    public int getPendingJobs() {
        return 0; // Example; a real application reads from the queue monitor.
    }

    @ManagedOperation(
        description = "Request a maintenance operation"
    )
    public String requestMaintenance() {
        return "ACCEPTED";
    }
}
```

A scheduled job is a separate component: it can use `@Scheduled`, Quartz, a scheduler in an orchestration platform, or a standalone operations service. The job reads/calls the MBean using a JMX client just like any other consumer.

**Do not conflate `@ManagedOperation` with `@Scheduled`:**

- `@ManagedOperation` exposes a management action over JMX.
- `@Scheduled` instructs Spring scheduling to invoke a method on a schedule.
- Both can be used in the same application, but they do not automatically connect or bind to each other.

## 5. Designing an MBean with Observable State

If an automation job can invoke an operation, the MBean must expose enough information for the job to know when to invoke it and to verify the call.

Service example:

```java
package com.example.ops;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceService {

    private final AtomicInteger pendingJobs =
        new AtomicInteger();

    private final AtomicBoolean maintenanceRunning =
        new AtomicBoolean();

    private volatile String lastOutcome = "NEVER_RUN";

    public int getPendingJobs() {
        return pendingJobs.get();
    }

    public boolean isMaintenanceRunning() {
        return maintenanceRunning.get();
    }

    public String getLastOutcome() {
        return lastOutcome;
    }

    public String requestMaintenance() {
        if (!maintenanceRunning.compareAndSet(false, true)) {
            return "ALREADY_RUNNING";
        }

        try {
            // In practice: delegate work to a lifecycle-managed
            // job executor.
            runMaintenance();
            lastOutcome = "SUCCESS";
            return "COMPLETED";
        } catch (RuntimeException ex) {
            lastOutcome = "FAILED";
            throw ex;
        } finally {
            maintenanceRunning.set(false);
        }
    }

    private void runMaintenance() {
        // Bounded and controlled operational logic.
    }
}
```

MBean adapter:

```java
package com.example.ops;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=MaintenanceControl,name=Primary",
    description = "Read maintenance state and request controlled maintenance"
)
public class MaintenanceControl {

    private final MaintenanceService service;

    public MaintenanceControl(MaintenanceService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending job count")
    public int getPendingJobs() {
        return service.getPendingJobs();
    }

    @ManagedAttribute(description = "Whether maintenance is running")
    public boolean isMaintenanceRunning() {
        return service.isMaintenanceRunning();
    }

    @ManagedAttribute(description = "Last maintenance result")
    public String getLastOutcome() {
        return service.getLastOutcome();
    }

    @ManagedOperation(
        description = "Request bounded maintenance on this instance"
    )
    public String requestMaintenance() {
        return service.requestMaintenance();
    }
}
```

This illustrative pattern executes maintenance synchronously. If the task is long-running, offload it to an executor/job queue, return a request ID, and expose progress state along with the final outcome. Never block a JMX invoke call waiting on unbounded heavy work.

### 5.1. Why Is State Needed?

If a job only calls `requestMaintenance()` and ignores the state/result, it cannot distinguish:

- Request rejected because another job is already running.
- Operation completed successfully.
- Operation started and is still in progress.
- JMX transport disconnected and it is unclear whether the server received the request.
- Another worker processed it concurrently.

State attributes allow the job to cross-check reality after calling and reduce blind retries.

## 6. Reading Attributes via MBeanServerConnection

For a local server:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.ops:type=MaintenanceControl,name=Primary"
);

int pending = (Integer) server.getAttribute(
    name,
    "PendingJobs"
);

boolean running = (Boolean) server.getAttribute(
    name,
    "MaintenanceRunning"
);

System.out.printf(
    "pending=%d running=%s%n",
    pending, running
);
```

If the Spring exporter uses a dedicated `MBeanServer`, fetch that exact server instead of the platform server. An MBean registered on a separate server may not appear in the platform registry.

For a remote client, obtain `MBeanServerConnection` from `JMXConnector`:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;

MBeanServerConnection connection =
    connector.getMBeanServerConnection();

Object value =
    connection.getAttribute(name, "PendingJobs");
```

In both cases, the code reads current values; `MBeanInfo` is a tool for discovering metadata such as attribute names, types, and readable/writable flags, not a replacement for `getAttribute`.

## 7. Invoking Operations with `invoke`

Once the condition is accepted, the job calls:

```java
Object result = connection.invoke(
    name,
    "requestMaintenance",
    new Object[0],
    new String[0]
);
```

`ObjectName` must be an MBean registered on the connection in use. `operationName` must appear in `MBeanInfo.getOperations()` with the matching parameter signature.

Operation with parameters:

```java
Object result = connection.invoke(
    name,
    "setThreshold",
    new Object[] { Integer.valueOf(750) },
    new String[] { "int" }
);
```

In this example, `"int"` is the Java parameter type declared in the method signature, not the wrapper `java.lang.Integer`. If the operation declares `Integer`, the signature differs.

Do not treat every call returning `null` as an error: a `void` operation normally returns `null`. For state-changing operations, define an explicit way to verify the effect.

## 8. Writing a Scheduled Job with Spring `@Scheduled`

Enable scheduling:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfig {
}
```

Example job using an `MBeanServer` injected within the same application:

```java
package com.example.ops;

import java.time.Duration;
import java.time.Instant;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MaintenancePollingJob {

    private final MBeanServer server;
    private final ObjectName objectName;

    private int consecutiveBreaches = 0;
    private Instant lastInvocation = Instant.EPOCH;

    public MaintenancePollingJob(MBeanServer server) throws Exception {
        this.server = server;
        this.objectName = new ObjectName(
            "com.example.ops:type=MaintenanceControl,name=Primary"
        );
    }

    @Scheduled(fixedDelayString = "${ops.maintenance.poll-delay-ms:30000}")
    public void pollAndMaybeInvoke() throws Exception {

        int pending = (Integer) server.getAttribute(
            objectName, "PendingJobs"
        );

        boolean running = (Boolean) server.getAttribute(
            objectName, "MaintenanceRunning"
        );

        consecutiveBreaches =
            pending > 500 ? consecutiveBreaches + 1 : 0;

        if (consecutiveBreaches < 3 || running) {
            return;
        }

        Instant now = Instant.now();
        if (Duration.between(
                lastInvocation, now).compareTo(Duration.ofMinutes(10)) < 0) {
            return;
        }

        Object result = server.invoke(
            objectName,
            "requestMaintenance",
            new Object[0],
            new String[0]
        );

        lastInvocation = now;
        consecutiveBreaches = 0;

        System.out.println("Maintenance invoke result: " + result);
    }
}
```

This is a **simple policy illustration**, not a full production implementation. It assumes a single scheduler does not overlap runs of the same job instance. If multiple nodes/pods or multiple schedulers run simultaneously, each job has its own `lastInvocation` and could invoke the operation concurrently. You must add leader election, a distributed lock, a lease, or server-side conditional execution.

### 8.1. Fixed Delay vs. Fixed Rate

- `fixedDelay`: waits for the specified interval after the previous execution finishes.
- `fixedRate`: schedules on a cadence from the start of the previous execution, which can behave differently if an execution runs long.
- `cron`: executes on a calendar schedule; depends on timezone and missed-execution policies.

For jobs invoking JMX operations with side effects, `fixedDelay` is usually easier to reason about in simple examples, though it does not automatically prevent overlapping execution across multiple instances or complex scheduler executor setups.

## 9. Evaluating Conditions: Do Not Check Only a Single Threshold

If `PendingJobs` fluctuates around 500, a condition like:

```java
if (pending > 500) {
    invokeMaintenance();
}
```

can fire repeatedly as the count oscillates around the threshold. Typically needed:

- **Consecutive breaches**: breached across multiple consecutive polls.
- **Hysteresis**: distinct trigger threshold and recovery threshold.
- **Cooldown**: minimum interval between two invocations.
- **MaintenanceRunning guard**: do not invoke while a job is already running.
- **Health guard**: do not actuate if downstream is in an unsafe state.
- **Rate limit/budget**: maximum number of invocations per hour/day.
- **Human approval**: require approval for operations with a large blast radius.

Hysteresis example:

```text
Enter alert state: PendingJobs >= 800
Exit alert state:  PendingJobs <= 400
```

With this policy, a metric oscillating between 650–750 will not flap state continuously. When applied to state-changing operations, define clearly when re-actuation is permitted and when only alerting should happen.

## 10. Checking Conditions Before and After `invoke`

A job might read state and invoke an operation milliseconds later. In that window, state can change.

```text
T1: Poller reads MaintenanceRunning=false
T2: Manual operator calls requestMaintenance()
T3: Poller also calls requestMaintenance()
```

If the server implementation relies solely on client-side checks, two operations can run in parallel.

Therefore, **critical preconditions must be re-checked and enforced atomically on the MBean/service side**, for example:

```java
if (!maintenanceRunning.compareAndSet(false, true)) {
    return "ALREADY_RUNNING";
}
```

Client-side polling helps avoid unnecessary calls, but it is not the final locking mechanism.

After `invoke`, the job should also re-read state:

```java
String lastOutcome = (String) connection.getAttribute(
    name, "LastOutcome"
);

boolean running = (Boolean) connection.getAttribute(
    name, "MaintenanceRunning"
);
```

Note that asynchronous operations may return `ACCEPTED` while the job is still running. A state read immediately afterward is not guaranteed to be the final outcome.

## 11. Timeouts, Network Errors, and Retries

Remote JMX can fail at several stages:

1. Client fails to establish a connection.
2. Client fails while reading attributes.
3. Client sends `invoke` but never receives a response.
4. Server executes the operation and responds, but the transport drops.
5. Client fails while re-reading state after `invoke`.

The dangerous part is case 3/4: **a timeout does not prove the operation did not run**. If the job automatically retries immediately, it can execute a non-idempotent operation twice.

Recommended rules:

- For operations with side effects, prefer idempotency or a request ID.
- Never retry indefinitely.
- Record `UNKNOWN_OUTCOME` when the outcome cannot be determined.
- After an error, read state through a reliable path before deciding to retry.
- Use exponential backoff and frequency limits if retries are permitted.
- Have a circuit breaker/kill switch for automation on repeated failures.
- Distinguish authentication errors, authorization errors, missing ObjectName, and business-logic failures.

Handling example:

```java
try {
    Object result = connection.invoke(
        name, "requestMaintenance",
        new Object[0], new String[0]
    );
    recordAcceptedResult(result);
} catch (Exception ex) {
    recordUnknownOutcome(ex);
    // Do not automatically retry immediately without verifying state.
}
```

`recordAcceptedResult` and `recordUnknownOutcome` are placeholder telemetry/audit integration hooks.

## 12. Preventing Concurrent Execution Across Multiple Instances

If the application runs three replicas and each replica has the same `@Scheduled` job:

```text
Pod A -- poll --> JMX Target X
Pod B -- poll --> JMX Target X
Pod C -- poll --> JMX Target X
```

all three pollers may see the condition evaluate to true. `@Scheduled` does not provide a distributed lock on its own. Options:

- Run the scheduler on only a single control-plane instance.
- Use leader election.
- Use a distributed lock/lease with clear TTL and ownership.
- Enforce atomic guards on the MBean/service side.
- Have the operation accept a request ID for deduplication.
- Limit concurrency and quotas on the executing worker.

If the JMX targets are individual pods, decide whether the policy operates per-instance or cluster-wide. Identical ObjectNames across three JVMs do not refer to the same resource; automation must attach the connection/server identity to avoid acting on the wrong target.

## 13. Secure Remote JMX Connections for Automation

When the poller runs in another JVM, a `JMXConnector` and appropriate endpoint are needed:

```java
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
);

try (JMXConnector connector =
        JMXConnectorFactory.connect(url, secureEnvironment)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    Object value = connection.getAttribute(
        name, "PendingJobs"
    );
}
```

`secureEnvironment` is a placeholder variable holding authentication/connector configuration from a secret management source. Never hard-code passwords or tokens in source code.

Security requirements:

- JMX Remote inside a restricted management network.
- Authentication/TLS per organizational policy.
- Least privilege for the poller: read attributes and invoke only required operations.
- Audit actor, target, operation, and outcome.
- Never allow automation to arbitrarily invoke operations outside an allowlist.
- Never expose credentials in URLs, logs, or error messages.
- Provide a fast revocation/kill-switch mechanism if a job misbehaves.

JMX is a privileged management channel; automating scheduled calls amplifies the impact of a misconfiguration because errors can repeat consistently.

## 14. Lifecycle Management of Connections and Schedulers

A continuous polling job must manage resources:

- Close `JMXConnector` when no longer in use.
- If reusing connectors, detect disconnects and reinitialize with backoff.
- Do not create thousands of short-lived connections in tight succession when polling frequently.
- Stop the scheduler before closing `ApplicationContext` and `MBeanServer`.
- Do not let threads or listeners retain old classloaders after redeploys.
- Handle MBean unregistration or ObjectName changes.
- Record the MBean contract version if clients depend on signatures/types.

An application may use a local `MBeanServer` without needing a network connector. In that case, calling an internal service directly can be simpler than JMX; only use JMX as an integration path when it genuinely fits the architectural goal.

## 15. Checking `MBeanInfo` Before Automation Runs

Do not assume `PendingJobs` will always remain an `int` or that an operation will always exist after a refactor.

You can validate the contract:

```java
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = connection.getMBeanInfo(name);

boolean pendingFound = Arrays.stream(info.getAttributes())
    .anyMatch(a ->
        "PendingJobs".equals(a.getName())
        && "int".equals(a.getType())
        && a.isReadable()
    );

boolean operationFound = Arrays.stream(info.getOperations())
    .anyMatch(o ->
        "requestMaintenance".equals(o.getName())
        && o.getSignature().length == 0
    );

if (!pendingFound || !operationFound) {
    throw new IllegalStateException(
        "Incompatible JMX management contract"
    );
}
```

Metadata checks show the currently published interface; they do not replace runtime error handling. An MBean can still be unregistered after the check, and an operation can fail due to state, security, or logic.

If automation depends on contracts across multiple versions, version the management API or coordinate client/server rollouts rather than hoping old names remain.

## 16. Metrics, Logs, and Audits for Automated Jobs

A JMX-driven control job should publish its own telemetry.

| Metric | Meaning |
| --- | --- |
| `poll_count` | Total number of checks |
| `condition_true_count` | Number of times the trigger condition held |
| `invoke_attempt_count` | Number of operation invocations sent |
| `invoke_success_count` | Number of verified successes |
| `invoke_error_count` | Errors during invocation or verification |
| `unknown_outcome_count` | Indeterminate outcomes after timeouts/disconnects |
| `last_poll_timestamp` | Most recent observation time |
| `last_invoke_timestamp` | Most recent operation request time |
| `cooldown_skip_count` | Number of skips due to cooldown |

Logs should include fields such as:

```text
scheduler=maintenance-poller
target=com.example.ops:type=MaintenanceControl,name=Primary
connection=worker-primary-jmx
condition=pendingJobs>500 for 3 polls
operation=requestMaintenance
decision=INVOKE
outcome=ACCEPTED
correlationId=...
```

Never log credentials, tokens, or sensitive data. If the job runs across multiple replicas, telemetry must include the scheduler instance and JMX target identity to identify which instance made the decision.

Audits must distinguish **request sent**, **operation accepted**, **outcome completed**, and **outcome undetermined**. Those are four distinct states.

## 17. Avoiding Alert Loops and Automation Loops

A common risk:

1. A metric crosses a threshold.
2. The job invokes an operation.
3. The operation causes a transient shift that keeps the metric above the threshold.
4. The job invokes it repeatedly.
5. System load increases, worsening the incident.

For example, clearing a cache to reduce memory can spike cache misses and database load; if the job sees memory still high 30 seconds later and clears it again, it creates a harmful feedback loop.

Prevention:

- Maximum invocations per time window.
- Cooldowns long enough for the system to stabilize.
- Check trends rather than just point-in-time snapshots.
- Identify expected side effects of the operation.
- Define recovery thresholds and a `RECOVERING` state.
- Halt automation when repeated attempts fail to achieve the desired effect.
- Escalate to an operator instead of retrying forever.
- Run in dry-run mode to observe decisions before enabling real execution.

For risky operations, alerting and requiring approval may be better than full automation.

## 18. A Small Rule Engine for Control Decisions

Separating policy into a plain Java class lets you test without an `MBeanServer`:

```java
public final class MaintenancePolicy {

    private final int threshold;
    private final int requiredBreaches;
    private int consecutiveBreaches;

    public MaintenancePolicy(int threshold, int requiredBreaches) {
        this.threshold = threshold;
        this.requiredBreaches = requiredBreaches;
    }

    public boolean shouldRequest(
            int pendingJobs,
            boolean maintenanceRunning,
            boolean cooldownFinished) {

        if (pendingJobs > threshold) {
            consecutiveBreaches++;
        } else {
            consecutiveBreaches = 0;
        }

        return consecutiveBreaches >= requiredBreaches
            && !maintenanceRunning
            && cooldownFinished;
    }

    public void onRequestAccepted() {
        consecutiveBreaches = 0;
    }
}
```

This example assumes a serialized caller. If the policy is accessed concurrently from multiple threads, `consecutiveBreaches` must be synchronized or moved to sequential event processing.

It can be tested with JUnit without JMX:

```java
@Test
void requestsOnlyAfterThreeBreaches() {
    MaintenancePolicy policy = new MaintenancePolicy(500, 3);

    assertFalse(policy.shouldRequest(600, false, true));
    assertFalse(policy.shouldRequest(700, false, true));
    assertTrue(policy.shouldRequest(800, false, true));

    policy.onRequestAccepted();
    assertFalse(policy.shouldRequest(100, false, true));
}
```

This is clean separation: **policy tests** verify decisions; **JMX integration tests** verify attributes/operations; **end-to-end tests** verify execution outcomes.

## 19. Failure Modes and Resolutions

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| MBean not found | Wrong ObjectName, wrong MBeanServer, or exporter not running | `isRegistered`, `getMBeanInfo`, verify connection |
| `AttributeNotFoundException` | Attribute name/type changed or not exported | Inspect `MBeanInfo.getAttributes()` |
| `ReflectionException` | Wrong operation name or signature | Inspect `MBeanInfo.getOperations()` |
| `MBeanException` | Management method threw an exception wrapped by JMX | Check root cause and server state |
| Remote `IOException` | Connector/transport failure | Reconnect with backoff; do not blindly retry operations |
| Poller runs multiple times | Multiple replicas/schedulers or overlapping execution | Leader election/lease and server-side guard |
| Operation loops endlessly | Condition stays true, missing cooldown/budget | Hysteresis, invocation limits, kill switch |
| Operation reports ACCEPTED with no effect | Async job has not finished or failed | Track request ID/final state |
| JMX target changes during rollout | Unstable ObjectName/connection identity | Version contract and controlled discovery |
| Automation causes overload | Operation too heavy or triggered on bad threshold | Reduce scope, halt job, and review policy |

Errors must be classified before retrying. Never catch `Exception`, wait a few seconds, and blindly re-invoke a state-mutating operation.

## 20. Hands-On Exercises

Build a small Spring application with `MaintenanceControl` and a polling job:

1. Create `MaintenanceService` holding `PendingJobs`, `MaintenanceRunning`, and `LastOutcome`.
2. Export via `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`.
3. Enable `@EnableMBeanExport` and `@EnableScheduling` or equivalent configuration.
4. Use an isolated `MBeanServer` in tests to avoid conflicting with the platform server.
5. Create a poller reading `PendingJobs` and `MaintenanceRunning`.
6. Implement a policy requiring three consecutive breaches and a ten-minute cooldown.
7. When eligible, call `requestMaintenance` via `invoke`.
8. Inspect the return value and read `LastOutcome`.
9. Add a test where the operation is already running and verify it is not invoked again.
10. Add a test after a simulated `IOException` and verify no blind retry occurs.
11. Simulate two pollers reading the condition concurrently and verify the service-side guard prevents duplicate execution.
12. Record metrics: poll count, condition-true count, invoke count, and outcomes.

Only use fixtures/labs to invoke operations. If real operations can clear caches, pause workers, or alter production configuration, never run unapproved tests against production.

## 21. Self-Check Questions

**1. Does JMX run operations on a schedule automatically?** No, an external scheduler or automation component is needed.

**2. Why must a poller read attributes before invoking?** To make decisions based on current state rather than invoking operations unconditionally.

**3. Why are client-side conditions insufficient to prevent duplicate execution?** Because state can change between reading and invoking, or multiple pollers can read concurrently.

**4. What does `MBeanServerConnection.invoke` require?** ObjectName, operation name, argument array, and matching signature array.

**5. Should you retry immediately after a remote timeout?** No, if it is unknown whether the operation already ran; verify state or ensure idempotency first.

**6. Why is a cooldown needed?** To prevent operations from being called repeatedly before metrics stabilize.

**7. Does `@Scheduled` provide a distributed lock automatically?** No.

**8. Does an identical ObjectName on two JVMs refer to the same resource?** No, connection/JVM identity is also required.

**9. Why should an MBean expose operation status?** It helps automation distinguish `ACCEPTED`, `RUNNING`, `SUCCESS`, and `FAILED`.

**10. When should alerting be preferred over automated control?** When the impact is high, rollback is hard, or operator judgment is required.

## 22. Key Takeaways

- **A scheduled job is a scheduling concern**, while JMX provides the channel for reading attributes and invoking operations.
- A safe flow is **observe → evaluate condition → guard → invoke → verify → audit**.
- **MBeanInfo** describes the contract; **getAttribute** provides current state; **invoke** executes operations.
- Use **consecutive breaches, hysteresis, cooldowns, and invoke budgets** to prevent repeated commands.
- **Server-side guards** must handle concurrency; poller pre-checks do not guarantee atomicity.
- **Timeouts do not prove an operation did not run**; use idempotency/request IDs and verify final state.
- **`@Scheduled` provides no distributed coordination** across replicas.
- **JMX Remote must be secured** and pollers granted least privilege.
- Telemetry must track both **decision-making** and **actual execution**.
- Maintain a **kill switch** and runbook to pause automation if unexpected side effects occur.

A good JMX job is not one that invokes operations as frequently as possible. It is a **conditional operational controller** that knows when to act, when to skip, how to verify outcomes, and how to bound risk for the Spring Framework system.
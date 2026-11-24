# Side-Effect Operations and Confirmation Requirements in Spring Framework JMX

## Objectives

In JMX, an operation can be a read, diagnostic, or control command. With Spring Framework, the \`@ManagedOperation\` annotation helps expose a Java method onto the MBean management surface. However, the fact that a method appears in JConsole or a JMX client says nothing about **how safe its impact is**. A call such as \`resetCounters()\`, \`clearCache()\`, \`pauseConsumers()\`, \`reloadConfiguration()\`, or \`forceReconnect()\` can affect runtime state, continuity of observability data, dependency load, and business processing itself.

For side-effecting operations, you need to determine precisely **what changes, who is allowed to request the change, where confirmation is performed, and how the result is verified**. An “Are you sure?” dialog should not be treated as the entire solution: confirmation is only one layer in the management workflow, while the executing system still needs authorization, precondition checks, protection against repeated invocations, and an audit trail.

After this lesson, you will be able to:

- Distinguish observation/diagnostic operations from side-effecting operations, including methods with misleading names.
- Characterize side effects by scope, reversibility, repeatability, and consequences of accidental execution.
- Understand that \`@ManagedOperation\` only exposes the operation and does not add authentication, authorization, or confirmation dialogs on its own.
- Design appropriate confirmation mechanisms for manual operator clients and automated scripts.
- Apply the request → prepare/confirm → execute → verify model, including timeouts, race conditions, and auditing.
- Write management MBeans with input validation, state/version preconditions, and request IDs to limit unintended execution.
- Establish runbooks for reset, reload, pause, resume, reconnect, or runtime parameter-change commands.

## 1. A JMX Operation Can Produce Side Effects at Multiple Layers

A JMX client invokes an operation via \`MBeanServerConnection.invoke(ObjectName, String, Object[], String[])\`. When an MBean is exported by Spring, the call is routed to the corresponding management method based on metadata.

\`\`\`text
JMX Client
   |
   | invoke(ObjectName, operationName, params, signature)
   v
MBeanServer / JMX Connector
   |
   v
Spring-managed MBean / @ManagedOperation
   |
   +--> modify bean state
   +--> invoke internal service
   +--> modify runtime configuration
   +--> clear cache
   +--> make network request
   +--> trigger asynchronous task
\`\`\`

A single method can have multiple simultaneous side effects:

| Example Operation | Direct Effect | Possible Secondary Consequences |
|---|---|---|
| \`resetStatistics()\` | Resets in-memory counters | Loss of diagnostic baseline; dashboard discontinuity |
| \`clearCache()\` | Evicts cached data | Increased DB/downstream load from cache misses |
| \`requestPause()\` | Sets pause intent | Backlog grows; timeouts or SLAs may be impacted |
| \`setLogLevel("DEBUG")\` | Changes runtime log level | Log I/O and volume increase; risk of exposing data |
| \`forceReconnect()\` | Closes and reopens connections | In-flight requests fail; retries increase load |
| \`reloadConfiguration()\` | Reloads configuration | Changes behavior of new requests, potentially affecting all tenants |
| \`drainQueue()\` | Resumes processing backlog | Increases pressure on downstream dependencies |
| \`runDiagnostics()\` | Scans system state | CPU, heap, locks, or network are consumed |

Thus, “side effect” is not limited to writing to a database. A command that **only alters metrics**, **sets a control flag**, **sends a notification**, **initiates a resource-heavy probe**, or **changes how a service handles requests** is worthy of analysis.

## 2. Classifying Impact Levels Before Requiring Confirmation

Not every operation requires the same level of confirmation. Describe impact across at least four dimensions:

1. **Scope**: one bean, one thread pool, one JVM, one tenant, one shard, or the entire cluster?
2. **Reversibility**: can it be restored immediately, does it require waiting for convergence, or is data permanently lost?
3. **Repeatability**: does invoking multiple times produce new side effects?
4. **Severity**: minor cost only, degraded service quality, processing disruption, or modification of critical data?

Policy guideline table:

| Operation Category | Example | Reasonable Policy |
|---|---|---|
| Lightweight read-only | \`getQueueDepth()\` | Read permission and data limits |
| Costly diagnostics | \`captureThreadSummary()\` | Resource limits, timeout, and rate limiting |
| Easily reversible control | \`requestPause()\` | Control permission, preconditions, verify effective state |
| Broad-impact control | \`clearAllCaches()\` | Scoped confirmation, audit, and rollback plan |
| Hard-to-reverse action | \`purgeDeadLetterQueue()\` | Independent business approval workflow; perhaps should not be exported via JMX |

This is a mental framework, not a rule saying “confirmed means safe.” For dangerous operations, the right choice may be **not putting that operation on an MBean**, or only exposing a validated request executed through a controlled operational channel.

## 3. What Does @ManagedOperation Provide?

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=CacheAdmin,name=Catalog",
    description = "Catalog cache management")
public class CacheAdmin {

    @ManagedOperation(
        description = "Clear all catalog cache entries")
    public void clearAll() {
        // call cacheService.clearAll() in a real application
    }
}
\`\`\`

When the Spring exporter is enabled, the \`clearAll\` method can appear as an MBean operation. However, the annotation **does not automatically add**:

- Authentication for the JMX connection.
- Authorization by role, tenant, or action.
- A confirmation dialog.
- Idempotency or double-click protection.
- Transactions or rollback.
- Rate limits, timeouts, and an audit trail.
- Blocking execution if another operator just changed state.

A description like \`description = "Dangerous operation"\` helps humans understand the impact, yet it is only metadata; a script can still invoke it directly without reading the description.

\`@ManagedOperation\` is the **contract publication layer**, while execution policies must be designed in the application/service and at the access boundary.

## 4. Client Confirmation and Server Verification Are Two Different Things

A management UI can display a dialog:

> You are requesting to clear the Catalog cache on instance A. This action may increase database load. Confirm?

This helps when humans operate manually, but the JMX API does not force every client to go through the same UI. JConsole, custom clients, CI scripts, or another JMX connector can invoke the operation in their own way. Therefore:

\`\`\`text
UI confirmation
   |
   | helps operator recognize consequences
   v
JMX request
   |
   v
Server-side authorization + validation + precondition
   |
   v
Execution
   |
   v
Audit + re-read state
\`\`\`

**Client-side confirmation** addresses accidental clicks. **Server-side verification** addresses permissions, input data, current state, and actual impact. Never base system safety on the assumption that all callers use a UI with confirmation.

### 4.1 Metadata Is Not Enforcement

An operation with a thorough description, clearly named parameters, and warnings in a runbook can still be invoked by an unchecked script. Mandatory safeguards for critical control commands should be enforced on the server: input validation, invalid-state guards, request ID recording, and access control aligned with the JMX access boundary.

### 4.2 Avoid Using a Boolean \`confirmed\` Parameter as the Sole Protection

A misleading pattern:

\`\`\`java
@ManagedOperation
public void clearAll(boolean confirmed) {
    if (!confirmed) throw new IllegalArgumentException("confirm first");
    cache.clear();
}
\`\`\`

Any client permitted to invoke can simply pass \`true\`. That parameter is merely a flag chosen by the caller; it **does not prove** an authorized human reviewed the impact or confirmed the action. Nor does it prevent duplicate retries after a timeout.

If an operation needs high protection, use an approval/authorization workflow with server-controlled identity, scope, TTL, and audit, or an operational platform workflow.

## 5. Distinguishing Preview, Confirmation, and Execution

A safer design separates **impact assessment** from **execution**.

\`\`\`text
1. Operator selects action and scope
2. System prepares a current-state assessment
3. Operator reviews:
   - target
   - scope
   - affected objects
   - preconditions
   - estimated duration/cost
4. Operator confirms via a system-supported mechanism
5. Server re-verifies permissions and state
6. Execute or reject because state changed
7. Re-read effective state and audit record
\`\`\`

Example impact to preview for \`evictCacheRegion(String region)\`:

\`\`\`text
Target instance: inventory-02
Operation: evictCacheRegion
Region: product-details
Current entries: 128,420
Expected effect: cache misses increase until warm-up
Precondition: region exists and no cache rebuild in progress
Recovery: automatic refill, no instant rollback
\`\`\`

This is information at **preview time**, which may already have changed by the time the user clicks confirm. For sensitive operations, confirmation should be bound to state/version or an expiry, and the server re-checks before execution.

### 5.1 A Preview Is Not Necessarily a Lightweight “Read-Only” Operation

A preview might need to scan millions of keys or query external data. Bound item counts, timeouts, and result sizes. Estimated information should include a timestamp and be clearly labeled approximate if applicable.

## 6. Designing State/Version Preconditions to Avoid Confirming on Stale Data

Suppose an operator reads:

\`\`\`text
workerState = RUNNING
version = 41
\`\`\`

Then another operator pauses the worker and increments the version to 42. If the stale command proceeds without checking preconditions, an action could be based on a snapshot that is no longer true.

Design an operation with an expected version:

\`\`\`java
public interface WorkerControlMBean {
    String getState();
    long getStateVersion();
    boolean requestPause(long expectedVersion);
}
\`\`\`

Illustrative implementation:

\`\`\`java
import java.util.concurrent.locks.ReentrantLock;

public final class WorkerControl implements WorkerControlMBean {

    private final ReentrantLock lock = new ReentrantLock();
    private String state = "RUNNING";
    private long version;

    @Override
    public String getState() {
        lock.lock();
        try {
            return state;
        } finally {
            lock.unlock();
        }
    }

    @Override
    public long getStateVersion() {
        lock.lock();
        try {
            return version;
        } finally {
            lock.unlock();
        }
    }

    @Override
    public boolean requestPause(long expectedVersion) {
        lock.lock();
        try {
            if (version != expectedVersion) {
                return false;
            }
            if (!"RUNNING".equals(state)) {
                return false;
            }
            state = "PAUSE_REQUESTED";
            version++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
\`\`\`

Point to understand: \`true\` here only indicates **the pause request was accepted under the current state**; it does not prove the worker has stopped accepting jobs. A real worker loop must apply the pause at a safe point and then update \`effectiveState\`. If you need an atomic preview of state and version, provide a single snapshot rather than reading two separate attributes that could race.

Preconditions can include expected state, version, generation ID, preview expiration time, or target instance. The choice depends on the operation type; do not add versioning just to overcomplicate a harmless observation command.

## 7. Distinguishing Accepted Request from Completed Side Effect

For an asynchronous operation:

\`\`\`java
@ManagedOperation(description = "Request cache rebuild")
public String requestCacheRebuild(String region) {
    // enqueue job and return ID
    return "operation-123";
}
\`\`\`

Returning an ID only means the system accepted/recorded the request according to contract. You need a way to check:

\`\`\`text
getOperationStatus("operation-123")
  -> ACCEPTED
  -> RUNNING
  -> SUCCEEDED / FAILED / CANCELLED
\`\`\`

Synchronous actions can return affected record counts or final state; asynchronous actions should return an operation ID and expose a suitable status polling mechanism or notification.

When side effects are irreversible, clients must not interpret “JMX invoke timeout” as “the command did not run.” The server may have already completed execution while the response was lost. Check the operation ID or actual state before resending.

## 8. Idempotency and Duplicate Execution

A user can click twice, a script can retry after a timeout, or two operators can invoke the operation concurrently.

### 8.1 Different Types of Actions

| Operation | Is Re-invocation Safe? | Practical Issue |
|---|---|---|
| \`requestPause()\` | Usually state-idempotent | Can still disrupt service if called at the wrong time |
| \`setLogLevel("INFO")\` | Converges to same config | Overwrites another ongoing log level change |
| \`clearCache()\` | Does not guarantee identical side effects | Cache refill is triggered repeatedly |
| \`rotateCredential()\` | Must not blindly retry | Can rotate keys twice and break clients |
| \`resetStatistics()\` | Same resulting value | Loses history at different points in time |

**Idempotent in final value** does not mean **free of side effects when invoked repeatedly**.

### 8.2 Request ID for Critical Operations

An operation that needs duplicate protection can accept a request ID:

\`\`\`java
String requestRefresh(String region, String requestId);
String getRequestStatus(String requestId);
\`\`\`

The server retains a record by request ID and appropriate scope, returning the result of the existing request instead of re-executing on duplicates. You must define retention, concurrency, restart behavior, and handling when the same ID is sent with different parameters. If guarantees must survive JVM restarts, idempotency state must be persisted durably, not kept only in memory.

JMX only provides an invocation mechanism; it does not grant exactly-once execution to your operations automatically.

## 9. Authorization, Action Permissions, and Auditing

Even when an MBean has a dangerous operation, not everyone allowed to read metrics should be allowed to execute it.

A management design requires:

- Authenticating the JMX connector or access channel.
- Separating observation permissions from control operation invocation permissions.
- Restricting JMX endpoints to management networks with appropriate encryption.
- Minimizing the scope of operations exposed via MBeans.
- Checking authorization on the request by identity and scope if the command type requires it.
- Auditing who, when, on which target, which operation, which parameters after redaction, and what outcome.
- Separating application MBean management from full-JVM administration permissions if the system supports it.

Spring \`@ManagedOperation\` does not automatically apply HTTP endpoint Spring Security rules to the JMX connector. In some setups, JMX access control only distinguishes coarse read/write permissions; verify operation-specific protection capabilities of the connector or use a separate control channel if fine-grained permissions are needed.

### 9.1 What Is an Audit Record?

A useful management audit record can include:

\`\`\`text
timestamp: 2026-01-01T10:15:20Z
actor: operator-id-from-trusted-authentication
target: inventory-02 / CatalogCache
operation: requestRefresh
scope: region=product-details
requestId: 9a7f...
previousState: IDLE
decision: ACCEPTED
finalState: SUCCEEDED
durationMs: 8200
\`\`\`

This is an example structure; never log raw credentials, tokens, or payloads containing personal data. For asynchronous operations, two records may be needed: request accepted and final execution outcome.

If a JMX access path does not pass a trusted identity into the application method, never let the caller supply an \`actor\` string and treat it as an authenticated identity. Identity/auditing should come from a trusted boundary, not a self-declared parameter.

## 10. Spring Example: Operation with Precondition Verification and Clear Result

Design a management class for enabling local maintenance mode. It exposes read-only state and a state-changing operation with an expected version. The example cannot demonstrate full authentication/authorization; those layers must be configured at the JMX connection and appropriate control layer.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Maintenance,name=Primary",
    description = "Controlled runtime maintenance switch")
public class MaintenanceControl {

    private boolean maintenance;
    private long version;

    @ManagedAttribute(description = "Current local maintenance state")
    public synchronized boolean isMaintenance() {
        return maintenance;
    }

    @ManagedAttribute(description = "State generation number")
    public synchronized long getVersion() {
        return version;
    }

    @ManagedOperation(
        description = "Set maintenance only if expectedVersion matches")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "enabled",
            description = "Desired maintenance state"),
        @ManagedOperationParameter(
            name = "expectedVersion",
            description = "Version observed by operator")
    })
    public synchronized String setMaintenance(
            boolean enabled, long expectedVersion) {
        if (expectedVersion != version) {
            return "REJECTED_STALE_STATE";
        }
        if (maintenance == enabled) {
            return "UNCHANGED";
        }
        maintenance = enabled;
        version++;
        return "APPLIED";
    }
}
\`\`\`

In a real application, this is only the bean's internal control state. To achieve **effective maintenance**, request routing/service layers must actually honor the flag; if transitioning asynchronously, separate \`requestedMaintenance\` from \`effectiveMaintenance\`. With multiple instances, each MBean typically controls only one JVM; cluster-wide maintenance requires another coordination mechanism.

Additional note: reading \`maintenance\` and \`version\` separately can race between two calls. In workflows requiring strict confirmation, provide a cohesive snapshot or a prepare operation returning a precondition token.

## 11. Two-Phase Confirmation Model with Short-Lived Tokens

For operations with significant impact, you can design:

\`\`\`text
previewEviction(region)
  -> planId, target, impactSummary, expectedVersion, expiresAt

executeEviction(planId)
  -> operationId / accepted-or-rejected
\`\`\`

A real system needs to store the server-side plan and verify:

1. The plan is bound to a specific action/target/scope.
2. The plan has a short expiration.
3. The current caller has permission to execute the action.
4. The version/precondition is still valid.
5. The plan has not been consumed, or duplicates have defined behavior.
6. Marking consumed and starting the task are handled atomically for the target.
7. All outcomes are audited.

**A plan token by itself is not proof of approval.** If any JMX client can call \`preview\` and then \`execute\` without authorization, the two-phase flow only guards against accidental actions or stale state, not unauthorized callers.

For example, do not store full secrets or sensitive information in the plan summary returned by JMX. A preview should give operators enough information while limiting data exposure.

### 11.1 When Should Confirmation Tokens Not Be Put into JMX?

If the system already has a standard production control plane/approval workflow, use it to coordinate high-risk actions. JMX can then expose read-only state and results, or receive an already-authorized request from the control plane. Do not build a weaker separate approval mechanism merely to click a command from JConsole.

## 12. Side Effects Caused by Diagnostic Operations

An often-underestimated group of operations is \`diagnose\`:

\`\`\`java
@ManagedOperation
public String dumpRecentErrors(int limit) { ... }
\`\`\`

If the implementation:
- Queries a database.
- Scans large datasets.
- Serializes object graphs.
- Reads raw request payloads.
- Triggers remote probes.
- Causes stop-the-world pauses due to heavy snapshots.

then it is still an operation with resource side effects or information-exposure risks. It may not need the confirmation dialog of a destructive operation, but it requires **timeouts, size limits, rate limits, redaction, and appropriate permissions**.

A name starting with \`get\` is not enough to conclude a method is lightweight and read-only. Any high-cost operation should document its impact and safeguards.

## 13. Specific Scenarios

### 13.1 Resetting Metrics Before Collecting Evidence

**Scenario:** CPU spikes suddenly; an operator wants to call \`resetCounters()\` to “clean up the dashboard.”

**Risk:** resetting erases evidence needed for diagnosis and creates a break in time series.

**Better design:** snapshot or export metrics before resetting; restrict reset permissions; clearly state counter type, scope, and reset timestamp. If you only need rates over a time window, use proper time-series metrics rather than resetting to compute them.

### 13.2 Clearing Cache Across Multiple Nodes

**Scenario:** a cache holds stale data; an operator calls \`clearAllCaches()\` on three nodes.

**Risk:** multiple nodes suffer cache misses simultaneously, causing a load spike on the database.

**Better design:** identify the specific cache region/keys to evict, execute node by node or in waves, monitor hit ratio/DB latency, and define rollout stop conditions. If the cache is distributed, clarify the operation's scope; do not assume every node has an independent cache.

### 13.3 Changing Log Level at Runtime

**Scenario:** enabling DEBUG to troubleshoot an issue.

**Risk:** log volume surges, potentially logging sensitive information and impacting I/O.

**Better design:** allow only approved loggers, enforce an auto-expiring duration that restores the previous level, audit who performed it, and verify the effective log level.

### 13.4 Reconnecting to Downstream

**Scenario:** connections to an external service fail; an operator calls \`forceReconnect()\`.

**Risk:** aborts in-flight requests, triggers retry storms, and loses session state.

**Better design:** inspect circuit breaker/health, identify the target, limit concurrent reconnects, return an operation ID, and monitor connection state after the change.

### 13.5 Pausing/Resuming Workers

**Scenario:** queue backlog rises and a dependency is overloaded.

**Risk:** pausing the wrong component misses SLAs; resuming all at once spikes load.

**Better design:** separate requested/effective state, preconditions, limits on concurrency changes, auditing, and recovery procedures. If a command affects the whole cluster, use orchestration instead of calling individual MBeans unchecked.

## 14. Why Is “Confirm Once” Not Enough?

Consider this sequence of events:

\`\`\`text
T0: Operator views preview: 1,000 cache entries
T1: Another job adds 50,000 entries
T2: Operator confirms
T3: Server deletes all 51,000 entries
\`\`\`

The operator confirmed a scope different from reality at execution time. One safeguard is requiring a version, bounded scope, or impact threshold:

\`\`\`text
executeEviction(planId, maxAffectedEntries)
\`\`\`

The server rejects if the scope changed beyond the approved limit. For actions whose exact count cannot be known in advance, use impact caps, batching, stop capability, and clearly labeled “estimated” counts.

The design point is not how many times confirmation is clicked, but that **confirmation must bind to what is permitted to execute**.

## 15. Verification and Observation After Execution

Every administrative command should have a way to prove the outcome independent of the initial response.

| Operation | Post-Invocation Verification |
|---|---|
| \`requestPause()\` | \`RequestedState\`, \`EffectiveState\`, count of newly accepted jobs |
| \`clearCache(region)\` | Size/hit ratio of that specific region, downstream load |
| \`setLogLevel(...)\` | Effective log level, logging rate, restoration deadline |
| \`requestRefresh(...)\` | Operation status, successful refresh timestamp |
| \`forceReconnect()\` | Connection state, request errors, retry count |
| \`resetStatistics()\` | Counter reset marker/time and new baseline |

An operation returning \`"SUCCESS"\` is insufficient if the system has not transitioned to the expected state. For asynchronous commands, an effective state or completion event is needed. Without telemetry, operators cannot distinguish “command accepted” from “command took effect.”

## 16. Runbook for Side-Effecting Operations

Before invoking:

1. Specify target and scope: JVM, component, resource, tenant, cluster.
2. Read current state and collect baseline evidence.
3. Check side effects, limits, permissions, and recoverability.
4. Have a stop/rollback plan if the action can cause impact.
5. If approval is required, complete it via a workflow with identity and audit.
6. Record expected state/version and unique request ID if applicable.

During invocation:

1. Use the exact operation name/signature and bounded parameters.
2. Do not blindly retry on timeout or unclear results.
3. Note the operation ID, accepted/rejected status, and errors.
4. If state versioning is used, handle stale-state rejections by re-reading rather than forcing execution.

After invocation:

1. Re-read effective state/metrics, not just the return message.
2. Check downstream services and secondary effects.
3. Record final outcome along with timestamp, target, and request ID.
4. If the goal was not achieved, execute recovery per the runbook and defined permissions.

## 17. Common Misconceptions

**“@ManagedOperation asks for confirmation automatically.”** No. The annotation exposes the operation and metadata; confirmation is designed separately by the client or workflow.

**“Adding a confirmed=true parameter is security.”** No. Callers set this value themselves; authorization must rely on real identity and permissions.

**“A void operation gives no way to know it ran.”** You can add effective state, operation status, metrics, and audit records. Do not rely solely on the return type.

**“Only data-deletion commands need controls.”** Changing log levels, restarting connectors, pausing workers, or resetting metrics can all have major consequences.

**“A timeout means the command did not execute.”** No. Side effects may have occurred while the response was lost.

**“It is idempotent, so it can be retried freely.”** An operation idempotent in final value can still cause repeated I/O, load, or disruption.

**“UI confirmation replaces server-side authorization.”** No. Other clients can invoke directly over a JMX connection.

**“One operation on an MBean applies cluster-wide.”** Typically an MBean belongs to a single JVM; scope must be explicitly designed and documented.

## 18. Practice Exercises

### Exercise 1: Classify Side Effects

Given the operations:

\`\`\`java
String diagnoseBacklog(int maxSamples);
void clearAllCache();
boolean requestPause();
void resetCounters();
String requestReindex(String indexName);
\`\`\`

Classify them as observation/diagnostic/control, and identify scope, secondary effects, and conditions to check. For example, \`diagnoseBacklog\` is bounded diagnostics; \`clearAllCache\` is a control action that can cause a cache stampede; \`resetCounters\` erases observability baselines.

### Exercise 2: Design Scoped Confirmation

An operator wants to clear the \`product-details\` cache only on instance \`node-02\`. Design the preview details, expected version, expiry, and result. If the cache region grew 20x in size after the preview, the server should reject or require re-confirmation.

### Exercise 3: Handle Timeouts

A script calls \`requestReconnect(requestId)\`, and then the JMX connection times out. Should the script retry with a new request ID? No. Read operation/connection status and check the previous request ID first. If the outcome cannot be determined, record an indeterminate state and follow the runbook rather than causing additional side effects.

### Exercise 4: Authorization

An MBean has attribute \`QueueDepth\` and operation \`clearDeadLetters()\`. Read-only and control operator groups have different permissions. Describe how to protect the JMX boundary, operation scope, and audit. Note: a method cannot know a trusted identity merely from a caller-supplied string.

### Exercise 5: State Versioning

Design \`requestPause(long expectedVersion)\` and \`getStatusSnapshot()\`. Explain why two separate getters may not provide an atomic snapshot and why \`PAUSE_REQUESTED\` does not mean \`PAUSED\`.

## Summary

\`@ManagedOperation\` is how Spring exposes an administrative action over JMX; it does not provide confirmation or side-effect controls on its own. For impactful operations, determine **what the action changes, what scope it affects, what permissions the caller has, whether preconditions still hold, and whether the system actually reached the desired state**. UI confirmation reduces human mistakes, but real safety lies in authorization, validation, preconditions, idempotency, auditing, and post-execution observation. High-risk actions should go through a control workflow appropriate to the system rather than being exposed arbitrarily on an MBean.

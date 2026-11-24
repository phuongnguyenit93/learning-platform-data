# Managing Permissions by Impact Level of Each Operation in Spring Framework JMX

## 1. Why Authorize by Impact Level?

A management API is often used by diverse consumers: monitoring systems, on-call operators, SREs, administrators, or automated tooling. Not everyone allowed to read JVM state should be allowed to clear caches, change configuration, stop workers, or trigger data-mutating actions.

In Spring Framework, a bean can be exposed to JMX via `MBeanExporter`, `@ManagedResource`, and `@ManagedOperation`. Seeing an operation listed in `MBeanInfo` only means it has been published on the management interface — **it does not mean Spring automatically checks caller permissions against the operation's risk level**.

Example:

```java
@ManagedResource(
    objectName = "com.example:type=Worker,name=Orders")
public class WorkerManagement {

    @ManagedAttribute
    public int getPendingJobs() {
        return pendingJobs;
    }

    @ManagedOperation
    public void pause() {
        worker.pause();
    }

    @ManagedOperation
    public void clearAllPendingJobs() {
        worker.clearPendingJobs();
    }
}
```

A client may only need to observe `PendingJobs`; an operator may be permitted to call `pause()`; whereas `clearAllPendingJobs()` has destructive impact and needs separate approval and restrictions.

**Lesson goal:** design policies by impact tier, enforce authorization at the right layers, reduce the risk of operation misuse, and test the distinction between read-only observation and state-mutating control.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Classify management operations by impact level.
2. Distinguish JMX metadata `ACTION`, `INFO`, `ACTION_INFO`, and `UNKNOWN` from actual authorization mechanisms.
3. Design a role model for reader, operator, privileged operator, and administrator.
4. Understand the limitations of JMX remote access files with `readonly` and `readwrite` levels.
5. Explain why `@ManagedOperation`, `@ManagedResource`, and `ObjectName` do not create security boundaries on their own.
6. Reason about enforcement at the remote connector, `MBeanServer`, proxy/facade, and business service layers.
7. Design high-risk operations using least privilege, explicit intent, idempotency, auditing, and state preconditions.
8. Write tests ensuring read-only callers cannot execute state-mutating operations.
9. Separate authorization tests from business-logic and JMX metadata tests.
10. Follow a pre-production checklist before allowing operators to use a management API.

## 3. Defense-in-Depth Layer Model

```text
JMX client / operator
        |
        v
Network boundary
  firewall / VPN / tunnel / TLS
        |
        v
JMX connector
  authentication + access policy
        |
        v
MBeanServer / authorization layer
  object name + action + parameters
        |
        v
Spring exported MBean / management facade
  validation, explicit state checks
        |
        v
Business service
  domain authorization / invariants
        |
        v
State change + audit trail
```

Each layer answers a specific question:

| Layer | Question |
|---|---|
| Network | Who can connect to the management port? |
| Authentication | Which principal is calling? |
| Connector authorization | Is the principal permitted to issue this type of JMX request? |
| `MBeanServer` authorization | Are the specific `ObjectName`, operation, and action allowed? |
| Management facade | Is the operation intentionally exposed and guarded for this use case? |
| Business service | Is the action valid in the current state and context? |
| Audit | Can we trace who requested what and what the outcome was? |

Do not rely on a single layer and skip the rest. For instance, IP filtering alone cannot distinguish two staff members on the same network; method annotations alone cannot protect an unauthenticated connector.

## 4. Classifying Operations by Impact Level

Instead of a single generic "admin" bucket, assign an **impact tier** to each action.

| Tier | Examples | Impact | Recommended Policy |
|---|---|---|---|
| L0 — Observe | `getPendingJobs()`, `getHealth()` | Reads minimized non-sensitive data | Monitoring reader |
| L1 — Diagnostics | `dumpStateSummary()`, `getFailedJobCount()` | May reveal topology/metadata | Diagnostics reader, audit access as needed |
| L2 — Reversible action | `pause()`, `resume()`, `setLogLevel()` | Reversible state change | Operator, precondition checks |
| L3 — Disruptive action | `restartWorker()`, `reloadConnections()` | Service interruption | Privileged operator, confirmation and audit |
| L4 — Destructive/security action | `deleteQueue()`, `purgeData()`, `rotateKeys()` | Potential data loss or security impact | Avoid direct exposure if possible; dedicated approval workflow |

Actual classification depends on semantics:

- `clearCache()` may be safe for a rebuildable cache, yet cause heavy load or session loss if poorly designed.
- `setEnabled(false)` looks simple but can halt business processing.
- `refreshConfiguration()` can alter endpoints, credentials, or business rules.
- `getConfiguration()` is read-only regarding mutation yet can still leak secrets.

**"Read-only" does not mean "non-sensitive."** Data confidentiality and operational blast radius must be evaluated side by side.

## 5. JMX Impact Metadata Is Not a Security Policy

`MBeanOperationInfo` defines impact values:

- `INFO`: informational operation.
- `ACTION`: state-mutating operation.
- `ACTION_INFO`: combines action and information.
- `UNKNOWN`: unspecified.

You can inspect them:

```java
MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.printf(
        "%s impact=%d%n",
        op.getName(),
        op.getImpact());
}
```

This metadata helps management tools describe operations, **but does not restrict permissions on its own**. A client permitted to call `MBeanServerConnection.invoke` can attempt to invoke an operation regardless of whether metadata says `ACTION` or `INFO`. Actual permission depends on authorization enforced by the connector, server, or business layer.

### 5.1. Do Not Rely on Method Names

Names such as `refresh()`, `reconcile()`, or `sync()` do not reveal their blast radius. A `refresh` operation might update millions of records. Policies must reflect actual behavior, affected data, and blast radius—not getter/setter prefixes or naming choices.

### 5.2. Metadata Should Assist Humans

Even though it is not a security boundary, thorough descriptions help operators avoid mistakes:

```java
@ManagedOperation(
    description = "Pause new job intake; running jobs continue")
public void pauseIntake() { ... }
```

Management documentation should state preconditions, side effects, completion time, rollback capability, and audit IDs.

## 6. Authentication and Authorization Are Different

**Authentication:** proves who the caller is, such as principal `monitor-agent` or `operator-alice`.

**Authorization:** defines what that principal may do, such as `monitor-agent` reading metrics only while `ops-maintenance` may invoke `pauseIntake`.

**Audit:** logs the request, outcome, and correlation trace for later investigation.

A password-protected JMX endpoint does not automatically provide sound authorization. If every account shares `readwrite` access, monitoring accounts receive far more privilege than necessary.

## 7. JMX Access File: readonly and readwrite

The traditional JDK management agent supports an access file with roles such as `readonly` and `readwrite`. Illustrative configuration:

```text
# jmxremote.access - illustrative only
monitorRole readonly
operatorRole readwrite
```

Password/access files, authentication mechanisms, and file paths are configured per JDK and deployment setup. Never copy this example into production while omitting TLS, file permissions, network controls, and account policies.

Limitations:

- `readonly` enforces coarse-grained JMX operation categories.
- `readwrite` is usually too broad for an operator who should be allowed to call `pause()` but not `purge()`.
- Do not assume a JMX access file enforces per-`ObjectName + operationName + params` rules.
- Some JDK/management agents provide extra configuration restricting `create`/`unregister`; check documentation for the target JDK version.
- Custom connectors may have different semantics from the built-in management agent.

When granular authorization is required, add an authorization layer or split exposure across dedicated endpoints/servers per privilege group.

### 7.1. Readonly Does Not Replace Data Minimization

A `readonly` principal can still read sensitive attributes if the server exposes them. Therefore, never put passwords, API tokens, raw connection strings, or personal data in JMX attributes. For diagnostics, favor safe summaries and separate privileges.

## 8. Splitting Management Operations by Role

One structural approach is avoiding putting every method into one broad management interface.

For example, instead of:

```java
public interface EverythingManagementMBean {
    int getPendingJobs();
    void pause();
    void restart();
    void purgeAll();
}
```

design separately:

```java
public interface WorkerStatusMBean {
    int getPendingJobs();
    String getState();
}
```

```java
public interface WorkerOperationsMBean {
    void pauseIntake();
    void resumeIntake();
}
```

And move destructive actions into a separate management workflow with approvals rather than exposing them as ordinary JMX methods.

Splitting interfaces makes the surface easier to review, yet if both MBeans are registered in one `MBeanServer` behind a shared `readwrite` connector, anyone with broad write access **can still invoke any operation they can see**. Splitting interfaces without an authorization policy does not create a security boundary.

## 9. Designing a Management Facade Instead of Exporting Services Directly

A business service with many methods should not be exported in full:

```java
@Service
public class OrderService {
    public void createOrder(...) { ... }
    public void refund(...) { ... }
    public void purgeFailedOrders(...) { ... }
    public OrderStatus findStatus(...) { ... }
}
```

Instead, create a management facade containing only reviewed actions:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Operations,name=Primary",
    description = "Restricted management API for order processing")
public class OrderManagementFacade {

    private final OrderCoordinator coordinator;

    public OrderManagementFacade(OrderCoordinator coordinator) {
        this.coordinator = coordinator;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return coordinator.pendingCount();
    }

    @ManagedOperation(
        description = "Pause intake without deleting queued orders")
    public void pauseIntake() {
        coordinator.pauseIntake();
    }
}
```

This contract keeps `purgeFailedOrders` off JMX. For operations capable of mutating state, enforcement is still needed at the connector/server or business service layer.

### 9.1. Restrict Overly Broad Autodetection

If a custom `MBeanExporter` uses an assembler that exposes every public method or an overly broad naming convention, dangerous operations can slip out unintentionally. Production should favor an explicitly defined list of managed methods or reviewed metadata.

## 10. Per-Operation Authorization: Enforcement Strategies

Several architectural options exist depending on requirements and JMX implementation:

| Strategy | Strengths | Limitations |
|---|---|---|
| JMX connector authentication/role | Blocks unauthenticated callers or coarse role groups | Often lacks per-operation granularity |
| `MBeanServer` authorization wrapper | Inspects MBean name, operation, and access type | Requires careful implementation and testing across all entry points |
| Custom JMX connector/forwarder | Can enforce per principal and request | Adds complexity and implementation coupling |
| Management facade + business authorization | Keeps allowlists and invariants close to logic | Must propagate caller identity reliably |
| Separate management API (HTTP/gRPC) with RBAC | Easier integration of identity, authz, and approvals | No longer a direct JMX operation |
| Omit dangerous operations | Strongest reduction in attack surface | Requires an alternative workflow when needed |

If the system needs to know the **principal of each remote JMX caller**, do not read an arbitrary `ThreadLocal` inside a bean and assume it holds an authenticated user. Identity propagation depends on the connector and security context. Prefer APIs/security frameworks with explicit identity contracts or a JMX authorization layer tested against the actual implementation.

### 10.1. MBeanServerForwarder

The JMX Remote API provides `MBeanServerForwarder` to intercept `MBeanServer` operations. A custom forwarder can be used in an authorization architecture, but a complete implementation must cover **every impactful access path**, not only `invoke`.

Operations to review include:

- `invoke`: calling management methods.
- `setAttribute`/`setAttributes`: mutating state via attributes.
- `createMBean` or `registerMBean` when exposed.
- `unregisterMBean`: removing registrations.
- `getAttribute`/`getAttributes`: reading sensitive data.
- Notification subscriptions and metadata reads when information disclosure matters.

If you block `invoke("purge")` but forget `setAttribute("PurgeRequested", true)`, callers still have a path to mutate state. Authorization policies must cover **capabilities**, not just method names.

## 11. Example Policy Engine for a Management Facade

One JMX-independent way to express policy is capability-based authorization:

```java
public enum ManagementAction {
    VIEW_STATUS,
    VIEW_DIAGNOSTICS,
    PAUSE_INTAKE,
    RESTART_WORKER,
    PURGE_DATA
}
```

```java
public interface ManagementAuthorizer {
    void require(String principal, ManagementAction action);
}
```

Illustrative implementation:

```java
import java.util.Map;
import java.util.Set;

public final class RoleBasedAuthorizer
        implements ManagementAuthorizer {

    private final Map<String, Set<ManagementAction>> grants;

    public RoleBasedAuthorizer(
            Map<String, Set<ManagementAction>> grants) {
        this.grants = Map.copyOf(grants);
    }

    @Override
    public void require(
            String principal,
            ManagementAction action) {

        if (!grants.getOrDefault(principal, Set.of())
                .contains(action)) {
            throw new SecurityException(
                "Not authorized for management action");
        }
    }
}
```

This is an example of a **policy function**. In a real system, `principal` must originate from a trusted identity channel, never from an arbitrary parameter supplied by the JMX caller.

### 11.1. Anti-Pattern: Client Self-Declaring Principal

Unsafe:

```java
@ManagedOperation
public void purge(String callerName) {
    authorizer.require(callerName, PURGE_DATA);
    purgeService.run();
}
```

A client can simply pass `"admin"` as `callerName`. Never treat caller-supplied strings as proof of authentication.

Instead, enforce policy at the connector/server boundary where the principal is already authenticated, or use a dedicated management API with a trusted security context.

### 11.2. Defense in Depth in the Business Service

Even when the JMX layer permits an operator to invoke `pauseIntake`, the business service should still verify:

- Does the service currently allow pausing?
- Is a critical batch currently in progress?
- Is the caller's unit authorized to act on this resource?
- Are safety preconditions such as expected version met?
- Does the system need to audit and notify sibling components?

Authorization and business validity are two distinct checks.

## 12. High-Impact Operations Should Have Explicit Preconditions

Instead of a vague method:

```java
@ManagedOperation
public void restart() {
    restartInternal();
}
```

embed explicit control preconditions in the contract:

```java
@ManagedOperation
public String requestRestart(
        String requestId,
        String expectedState,
        String reason) {

    validateRequest(requestId, expectedState, reason);
    return maintenanceService.requestRestart(
        requestId, expectedState, reason);
}
```

Illustrative code only; `validateRequest` and `maintenanceService` must be implemented and secured.

Design requirements:

1. `requestId` enables correlation and deduplication.
2. `expectedState` guards against acting after state has changed.
3. `reason` supports auditing, though it does not replace caller identity.
4. Returned ID/status lets clients track progress instead of retrying blindly.
5. Authorization must occur before any side effect.
6. Never accept `"admin=true"` from the client as proof of privilege.
7. When modifying multiple resources, define the blast radius clearly.

Good validation does not replace authorization, but it reduces operational mistakes.

## 13. Two-Step Approval: Preview and Execute

For dangerous operations, you can split them:

```text
previewPurge(scope) -> impact summary
          |
          v
Review/approval outside JMX
          |
          v
executeApprovedPurge(approvalToken, requestId)
```

However, `approvalToken` is itself a sensitive credential. Passing it in JMX operation arguments requires protecting transport, logs, and debug traces, plus checking expiry, scope, and single-use semantics. A more practical approach is often routing destructive actions through an orchestration service with a dedicated approval workflow rather than exposing `executeApprovedPurge` on every JVM.

The goal is preventing a single click in JConsole from triggering an irreversible action.

## 14. Audit: Who Did What, and What Was the Impact?

A minimal audit event should record:

| Field | Meaning |
|---|---|
| `timestamp` | Time the server received the request |
| `principal` | Authenticated identity |
| `action` | Requested capability/operation |
| `objectName` | Managed resource |
| `requestId` | ID for correlation and deduplication |
| `scope` | Normalized impact scope |
| `decision` | Allowed/denied |
| `outcome` | Succeeded/failed/unknown |
| `duration` | Processing time |
| `correlationId` | Links logs and workflows |

Never log raw passwords, tokens, private keys, or unfiltered JMX parameters. Parameters may contain sensitive or personal data.

### 14.1. Denied Attempts Before Business Methods Must Also Be Audited

If the authorization layer rejects `invoke`, the business method never runs. Auditing placed solely inside the method will miss denied attempts. Record the decision where policy is enforced and audit execution outcomes in the execution layer when accepted.

### 14.2. Unknown Outcomes with Remote JMX

If a client disconnects after the server executes an operation, the client may see `IOException` even though the server already mutated state. Server-side audit logs, request IDs, and status queries help determine the outcome. Never automatically retry destructive operations merely because the client timed out.

## 15. Spring AOP and Management Methods

A development team might place authorization advice around a Spring bean method. However, whether the JMX exporter invokes the method through the proxy or directly on the target depends on exporter, assembler, and AOP configuration.

```text
JMX request
    |
    v
MBean adapter
    |
    +--> Spring AOP proxy?
    |        |
    |        +--> security advice
    |
    +--> target directly?
             |
             +--> advice may be bypassed
```

Therefore:

- Do not assume `@PreAuthorize` on an exported method is automatically enforced on every JMX invocation path.
- Verify the exported object is the proper proxy and that JMX calls actually pass through the security interceptor.
- Check whether JDK dynamic proxies expose the full management interface.
- Avoid self-invocation when logic depends on AOP advice.
- Never unwrap a proxy to "fix" a non-working MBean and inadvertently bypass authorization.
- Test denials with **real `MBeanServerConnection.invoke` calls**, not only direct service calls in unit tests.

Where strict security is required, do not rely solely on an AOP annotation that has not been verified end-to-end at the JMX boundary.

## 16. Read vs. Write Is Not Always Clear-Cut

An operation marked `INFO` may still perform heavy computation, read secrets, or strain the database. A getter can also make network requests.

Conversely, a setter like `setLogLevel` is a mutation yet may be permitted for operators under policy.

Evaluate along multiple axes:

| Axis | Question |
|---|---|
| Confidentiality | Does it disclose sensitive data? |
| Integrity | Does it modify data, configuration, or security state? |
| Availability | Can it stop or degrade the service? |
| Reversibility | Can it be rolled back? |
| Scope | One worker, one node, or the whole cluster? |
| Cost | How much CPU, I/O, DB, or network load? |
| Auditability | Can actor and outcome be determined? |

A sound permission matrix answers these axes before deciding which role may invoke an operation.

## 17. ObjectName Design and Resource-Level Authorization

Example MBeans:

```text
com.example.orders:type=Worker,region=vn,name=Primary
com.example.orders:type=Worker,region=sg,name=Primary
```

A VN operator may be allowed to call `pauseIntake` on `region=vn`, but not on `region=sg`. Authorization must evaluate **both `ObjectName` and operation**, not only the method name.

`ObjectName` is an input identifying a resource. It does not grant permissions. A caller might construct another `ObjectName` if the connector allows it; server policy must validate the permitted scope.

### 17.1. Avoid Overly Broad Wildcard Permissions

A policy granting:

```text
com.example.orders:*
```

can inadvertently include future MBeans, including dangerous operations. Prefer allowlists by domain/type/name/region and specific capabilities. Review permission drift whenever a new MBean or method is added.

## 18. Testing Impact-Based Authorization

Tests must verify **both denied paths and permitted paths**.

Suggested matrix:

| Principal | Status read | Diagnostics | Pause | Restart | Purge |
|---|---:|---:|---:|---:|---:|
| monitoring-reader | Allow | Deny | Deny | Deny | Deny |
| diagnostics-reader | Allow | Allow | Deny | Deny | Deny |
| operator | Allow | Allow | Allow | Deny | Deny |
| privileged-operator | Allow | Allow | Allow | Allow | Deny |
| emergency-admin | Allow | Allow | Allow | Allow | Conditional |

"Conditional" means additional approvals, time-bound access, and scope checks may be required. This table is illustrative; actual roles must be defined by the organization.

### 18.1. Testing the Policy Function

```java
import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class AuthorizerTest {

    @Test
    void monitoringCannotPause() {
        var grants = Map.of(
            "monitoring-reader",
            Set.of(ManagementAction.VIEW_STATUS));

        var auth = new RoleBasedAuthorizer(grants);

        assertThrows(SecurityException.class,
            () -> auth.require(
                "monitoring-reader",
                ManagementAction.PAUSE_INTAKE));

        assertDoesNotThrow(
            () -> auth.require(
                "monitoring-reader",
                ManagementAction.VIEW_STATUS));
    }
}
```

This test verifies only the role/capability mapping logic; **it does not prove the JMX connector actually attaches the right principal and enforces the policy**.

### 18.2. Testing the JMX Boundary

In an integration test with the appropriate security layer:

1. Create a `monitoring-reader` principal.
2. Connect to the secured connector.
3. Assert reading safe attributes succeeds.
4. Call `invoke("pauseIntake")` and assert denial.
5. Assert worker state remains unchanged.
6. Switch to an authorized `operator` principal.
7. Invoke the same operation and assert success.
8. Verify audit logs contain both denied and allowed decisions.
9. Ensure any equivalent setter is similarly restricted.
10. Close the connector/context and clean up MBean registrations.

Do not inject a fake principal inside a business method and call it an authentication integration test. Use real authentication or the connector's actual test fixture.

## 19. Testing Capabilities on MBeanServer

When verifying metadata/contract only, an isolated local server works well:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("test");

ObjectName name = new ObjectName(
    "com.example.orders:type=Worker,name=Primary");
```

After exporting the test MBean via Spring, inspect:

```java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
```

This verifies the exposed surface, not remote authorization. A local `MBeanServer` can be called directly by code in the same JVM without passing through an authenticated connector. Security tests must exercise the actual enforcement boundary.

## 20. Preventing Authorization Bypasses

A policy that blocks only `invoke` can be bypassed if the resource exposes a state-mutating path via a writable attribute.

Example:

```java
@ManagedAttribute
public void setPaused(boolean paused) {
    service.setPaused(paused);
}
```

Even if `pauseIntake()` is protected, a client can try:

```java
connection.setAttribute(
    name, new Attribute("Paused", true));
```

Therefore, exposure and authorization reviews must cover:

- Readable attributes.
- Writable attributes.
- Operations.
- Create/unregister capabilities if exposed.
- Notification subscriptions.
- Metadata discovery and permission to read sensitive descriptions/info.

One risk-reducing design is avoiding writable attributes for critical actions; use operations protected by authorization and clear preconditions instead. Still, no single pattern suffices for every system; always evaluate against your actual security policy.

## 21. Incidents and Break-Glass Access

During severe incidents, temporary elevated privileges may be needed. That does not mean granting permanent admin privileges to every operator.

A break-glass workflow typically requires:

1. Identifying the requester.
2. Recording the incident/ticket ID and justification.
3. Policy-defined approval or emergency mechanism.
4. Temporary privileges with a short TTL.
5. Restricted resource scope.
6. Auditing even when operations fail.
7. Revoking access upon expiry or incident closure.
8. Post-incident review.

If the JMX connector does not support that granularity, place privileged actions in a dedicated management service instead of forcing a coarse-grained connector to act as a full IAM system.

## 22. Production Adoption Guide

### Step 1: Build an Inventory

Enumerate all actually registered MBeans, attributes, and operations via `MBeanInfo`. Do not merely search for `@ManagedOperation` in source code, as libraries may also register MBeans.

### Step 2: Classify Impact

Apply the L0–L4 matrix and confidentiality/integrity/availability axes.

### Step 3: Choose Enforcement Boundaries

Ensure caller identity is authenticated and propagated reliably to where permissions are checked.

### Step 4: Minimize Exposure

Remove unneeded operations; separate read-only views from privileged actions.

### Step 5: Enforce Preconditions

Add expected state, request IDs, dry-runs, or previews for complex actions.

### Step 6: Audit

Record both denied and allowed attempts and outcomes without logging secrets.

### Step 7: Test

Cover wrong roles, wrong `ObjectName`s, writable attribute bypasses, remote connectors, context restarts, and confirming denials leave state unchanged.

### Step 8: Monitor

Alert on failed authorization attempts, bursts of privileged operations, and unexpected configuration changes.

### Step 9: Check for Drift

Whenever Spring, the JDK, or connectors change, re-verify `MBeanInfo`, policies, and the effective management surface.

### Step 10: Operational Documentation

Document who holds privileges, how to request access, operation consequences, and recovery procedures.

## 23. Common Design Mistakes

| Anti-pattern | Risk | Remediation |
|---|---|---|
| Every operator uses `readwrite` | Overly broad privileges | Granular auth or split management surface |
| Adding `@ManagedOperation` and assuming it is secured | Annotation only exposes | Enforce at trusted boundaries |
| Client passes `role=admin` as a parameter | Privilege spoofing | Obtain principal from authentication |
| Blocking only `invoke` | Writable attribute bypass | Cover `setAttribute(s)` in policy |
| JMX calls service directly, bypassing proxy | Security advice may be bypassed | Test the JMX path; use proper facade |
| Treating `INFO` impact as safe | Metadata enforces no permissions | Review actual behavior and impact |
| Exposing `purgeAll()` for convenience | Massive destructive impact | Separate workflow with approval |
| Not auditing denials | Permission probing goes unnoticed | Audit at the enforcement layer |
| Retrying on JMX timeout | Action may execute twice | Request IDs and status reconciliation |
| Domain-wide wildcard permissions | New MBeans unintentionally exposed | Allowlist by resource and capability |

## 24. Hands-on Exercises

### Exercise A — Inventory and Tiering

Create an MBean with `getPendingJobs`, `pauseIntake`, `restartWorker`, and `purgeQueue`. Inspect `MBeanInfo`, assign an impact tier to each method, and explain your criteria.

### Exercise B — Readonly vs. Readwrite

In an isolated and secured remote JMX lab, create two principals corresponding to `readonly` and `readwrite`. Try reading attributes and invoking state-mutating operations. Document the differences and highlight the limitations of coarse-grained authorization.

### Exercise C — Capability Policy

Implement `ManagementAction` and `ManagementAuthorizer`, and write unit tests for `monitoring-reader`, `operator`, and `privileged-operator`. Prove lower-privilege roles are denied on higher-impact capabilities.

### Exercise D — Writable Attribute Bypass

Create an MBean with both `pause()` and `setPaused(boolean)`. Design authorization covering both `invoke` and `setAttribute`. Write tests proving an unauthorized principal cannot change state through either path.

### Exercise E — Spring AOP

Attach security advice to a facade method, export it via Spring JMX, and invoke it through `MBeanServerConnection`. Verify the advice actually triggers. Switch proxy strategies in tests and inspect whether metadata or authorization is affected.

### Exercise F — Approval-Gated Operation

Design a `preview`/approval/`execute` workflow for a simulated data-deletion action. Require a request ID, expected state, auditing, and authorization checked from a trusted identity. Do not use real or production data for testing.

## 25. Self-Check Questions

1. Why does `@ManagedOperation` not grant or restrict access on its own?
2. What is the difference between impact metadata and an authorization policy?
3. In what case can a `readonly` principal still cause an information leak?
4. Why can a `readwrite` role be overly broad for an operator?
5. If `invoke` is blocked but `setAttribute` is allowed, what risk arises?
6. Why is a `callerName` parameter from a client not a trustworthy identity?
7. When should an operation be moved to a separate management workflow?
8. At which layer must auditing be recorded to capture denied attempts as well?
9. Why is testing through a real JMX connection necessary rather than unit-testing policies alone?
10. When might AOP security advice fail to execute?
11. Why must `ObjectName` be considered in authorization policies?
12. Why is a timeout insufficient to determine whether an operation succeeded?

## 26. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `@ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — `MBeanOperationInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — `MBeanServerForwarder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/MBeanServerForwarder.html
- Oracle JDK Monitoring and Management: https://docs.oracle.com/en/java/javase/21/management/
- Spring Security Reference: https://docs.spring.io/spring-security/reference/

**Key Takeaway:** JMX authorization must be based on **the impact level of the action and a verified authenticated identity**, not on annotations, method names, or impact metadata. Minimize the exposed surface first, enforce policies at trusted boundaries, protect both operations and writable attributes, apply preconditions, and audit and test per role.

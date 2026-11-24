# Removing an Operation Being Invoked by Administration Tools in Spring Framework JMX

## Objectives

JMX is a runtime management API. When Spring Framework exports beans via `MBeanExporter`, `@ManagedResource`, `@ManagedOperation`, or Standard MBean/MXBean interfaces, JMX clients can invoke operations through `MBeanServerConnection.invoke()`. Clients may be JConsole, VisualVM, an operations script, automation, a monitoring agent, a control plane, or an internal partner tool. Therefore, **removing an operation** is not merely refactoring a Java method: it can be a **breaking change to the management contract**.

It is especially dangerous when an operation is already invoked automatically by administration tools. A seemingly small change can cause emergency runbooks to fail, batch automation to report errors, or operators to repeatedly retry a command that no longer exists. For operations with side effects, improper retries or fallbacks can also leave system state inconsistent.

After this lesson, you will be able to:

- Explain why removing a JMX operation can break compatibility even when the application still starts up.
- Distinguish removing a Java method, dropping `@ManagedOperation`, changing a management interface, and changing an `ObjectName`.
- Identify client dependencies based on operation name, parameter signature, return type, and ObjectName.
- Plan inventory, deprecation, migration, and removal across versions.
- Design wrappers or compatibility operations for transition without keeping legacy code forever.
- Assess impacts on scripts, JConsole, remote clients, and automation.
- Use `MBeanInfo` and integration tests to lock down the management contract.
- Establish rollback, auditing, and change notifications for operations teams.

## 1. A JMX Operation Is a Public Contract

Example Spring bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Cache,name=Catalog",
    description = "Catalog cache administration")
public class CatalogCacheAdministration {

    @ManagedOperation(description = "Evict the entire catalog cache")
    public void clearAll() {
        // Call the application's cache management service.
    }
}
\`\`\`

A JMX client can invoke:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName objectName = new ObjectName(
    "com.example.ops:type=Cache,name=Catalog");

connection.invoke(
    objectName,
    "clearAll",
    new Object[0],
    new String[0]);
\`\`\`

The invocation depends on several elements:

| Contract element | Illustrative value | What can break clients |
|---|---|---|
| MBeanServer/endpoint | JMX connector of JVM A | Moving connector/server without updating clients |
| ObjectName | `com.example.ops:type=Cache,name=Catalog` | Changing domain/key properties |
| Operation name | `clearAll` | Removing or renaming |
| Parameter signature | `[]` | Adding, removing, or changing parameter types |
| Return value | `void` | Clients depending on result type/meaning |
| Authorization | Caller has invoke permission | Changing policy without notice |
| Behavior | Clears entire regional cache | Changing scope/effect without updating runbook |

Thus, deleting `clearAll()` from the Java class is only one kind of change. Removing `@ManagedOperation`, dropping the method from the management interface, or switching assemblers can also make the operation disappear from `MBeanInfo` even while the Java method still exists.

## 2. Distinguishing “Removing a Method” from “Stopping Export”

There are at least four cases:

1. **Removing the Java method completely.** Application code or direct Java callers can also break at compile time or runtime.
2. **Keeping the Java method but removing it from JMX metadata.** Internal application code still works, but JMX clients cannot invoke it via that contract.
3. **Keeping the method but changing operation name/signature.** Old clients cannot find the expected operation.
4. **Keeping the operation but changing ObjectName or target server.** Old JMX clients see the operation as removed, even though the implementation still exists elsewhere.

Example:

\`\`\`java
public class CacheAdministration {

    // No longer has @ManagedOperation.
    public void clearAll() {
        // Can still be called by Java code.
    }
}
\`\`\`

If the Spring exporter uses annotation-driven metadata, `clearAll` is not exported under this annotation. However, if the same bean is exported through another assembler, the method may still appear. Therefore, do not rely on “annotation removed” as final proof; inspect `MBeanInfo` on the actual running server.

For a Standard MBean:

\`\`\`java
public interface CatalogCacheMBean {
    long getHitCount();
    void clearAll();
}
\`\`\`

If `clearAll()` is removed from the interface, the implementation method may remain public yet no longer belong to the Standard MBean contract. This is also a breaking change for JMX clients that invoked the operation.

## 3. Why Do Administration Tools Often Depend Silently?

JMX clients do not necessarily reside inside the application source repository. They may be:
- Bash/PowerShell scripts invoking a JMX client.
- SRE automation jobs.
- JConsole or VisualVM plugins.
- A Java program using `JMXConnectorFactory`.
- A dashboard page with control buttons.
- An orchestration system invoking operations during deployment.
- Runbooks instructing operators to click a specific operation.
- Scheduled maintenance tasks.
- A monitoring library or control plane running in another JVM.

This makes grepping the application codebase insufficient. An operation may have zero calls in internal Java source yet still be used weekly by external operators.

### 3.1 Do Not Infer “Rarely Used” from Business Metrics

Without invocation auditing, it is hard to know which operations have been called. An MBean might only be used during severe incidents, so months with no invocations do not mean it is safe to delete.

Inventory administration systems, consult runbook owners, and establish actual tracking before removal.

## 4. What Do Clients See When an Operation Is Removed?

After the change, JMX metadata no longer contains the operation. An old call:

\`\`\`java
connection.invoke(
    name,
    "clearAll",
    new Object[0],
    new String[0]);
\`\`\`

may fail with `ReflectionException` or an exception dispatched according to the implementation/connector. If the MBean itself no longer exists, `InstanceNotFoundException` may occur. Over remote connections, these errors may be wrapped or accompanied by `IOException` if transport fails.

Do not claim every JMX client displays the same message. JConsole may remove the operation from its UI after refreshing metadata; scripts may keep trying to invoke it and fail; a client caching `MBeanInfo` may display the old button until refreshed.

Distinguish:

| Symptom | Possible cause |
|---|---|
| `isRegistered(name)=false` | MBean unregistered, ObjectName changed, or wrong server |
| MBean exists but operation missing from `MBeanInfo` | Contract removed the operation |
| Operation present but invoke fails | Wrong signature, permissions, implementation exception |
| Client reports timeout | Connection or operation may be slow; does not prove removal |
| Script compiles but fails at runtime | JMX invocations often use string names, unchecked by compiler |
| JConsole missing button after deploy | Runtime metadata changed or client viewing different server |

Verify the target server, ObjectName, and `MBeanInfo` before concluding the failure is due to operation removal.

## 5. Step 1: Inventory the Operation Before Removal

Create a table with at least:

| Field | Example |
|---|---|
| ObjectName | `com.example.ops:type=Cache,name=Catalog` |
| Operation name | `clearAll` |
| Signature | No parameters |
| Return type | `void` |
| Current behavior | Evicts the entire cache in one JVM |
| Side-effect risk | Cache misses spike, downstream overload |
| Owner | Cache operations team |
| Active clients | Runbook R-12, deployment script, dashboard |
| Last invoked | Based on audit if available |
| Replacement | `requestEviction(String region, String requestId)` |
| Planned removal version | Per release plan |
| Rollback plan | Keep compatibility adapter during transition |

Documenting on paper without runtime verification is not enough. An exporter may auto-discover extra operations, or a proxy/assembler may alter metadata.

### 5.1 Extracting the Contract from MBeanInfo

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("operation=" + operation.getName());
    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.println("  parameterType=" + parameter.getType());
    }
    System.out.println("returnType=" + operation.getReturnType());
}
\`\`\`

For overloaded operations, checking the name alone is insufficient. `reset(String)` and `reset(long)` share the same operation name but have different contracts.

If `int` changes to `Integer`, clients passing the old `"int"` signature may no longer match. That is a JMX compatibility change even if the operation name remains the same.

## 6. Step 2: Find Dependencies from Administration Tools

Sources to inspect:
1. Source of CLIs, operational scripts, control planes, and JMX plugins.
2. Job schedulers, pipelines, runbooks, dashboards with operation buttons.
3. List of users with JMX permissions and owning teams.
4. JMX invocation logs/audits if available.
5. Hard-coded endpoint and ObjectName configurations.
6. Staging, production, and parallel running application versions.
7. Disaster recovery systems where operations are rarely used.

Avoid recording raw secrets, JMX credentials, or sensitive payloads during inventory. Client discovery must include tools outside the application repository.

### 6.1 If Invocation Auditing Does Not Exist Yet

Do not declare “nobody uses it” merely because no string matches in code. Add logging/auditing in the management adapter or protected control plane. When the JMX MBeanServer or connector does not provide reliable method-level identity, never trust a client-supplied `actor` parameter as an authenticated identity.

Enabling metrics for operation invocation count and success/failure status helps assess usage, while avoiding exposing parameters containing secrets. For rare but critical operations, confirm directly with operations teams even when metrics show zero hits.

## 7. Step 3: Announce Deprecation Before Removal

A safer approach is keeping the old operation during a transition period while clearly documenting the replacement and migration path.

Example:

\`\`\`java
@ManagedOperation(
    description = "DEPRECATED: use requestEviction(region, requestId)")
public void clearAll() {
    // Delegate to the new service or adapter if equivalent.
    cacheEvictionService.requestLegacyClearAll();
}
\`\`\`

In Java you can also use:

\`\`\`java
@Deprecated(since = "2.4", forRemoval = true)
\`\`\`

However, `@Deprecated` does not automatically cause a remote JMX client to show a warning or block invocation. JMX clients may only see metadata published by the exporter. Deprecation notices must appear in the description, runbook docs, release notes, and communications to owners.

If the old operation has overly broad impact, do not maintain dangerous behavior without controls solely for compatibility. You may need to restrict permissions, validate preconditions, and design an approved emergency migration path.

## 8. Step 4: Design a Replacement with a Clear Contract

Suppose the old operation:

\`\`\`java
void clearAll();
\`\`\`

Replacement:

\`\`\`java
String requestEviction(String region, String requestId);
String getOperationStatus(String requestId);
\`\`\`

Benefits:
- Scoped by `region` instead of clearing everything.
- Includes a request ID to detect duplicate requests.
- Provides task status if executed asynchronously.
- Supports validation and auditing.

However, this is not a strictly equivalent drop-in replacement. `clearAll()` might be synchronous, whereas `requestEviction()` returns `ACCEPTED` before completion. Runbooks and clients must understand the difference. Do not keep the same operation name while silently changing semantics just because “it still appears to run”.

### 8.1 If the Replacement Is Only a Rename

A low-risk approach:

\`\`\`java
@ManagedOperation
public void refreshMetrics() {
    metricsService.refresh();
}

@Deprecated
@ManagedOperation(description = "DEPRECATED: use refreshMetrics")
public void reloadMetrics() {
    refreshMetrics();
}
\`\`\`

This works when both operations share identical semantics and repeatability. However, when using AOP proxies, self-invocation of `refreshMetrics()` within the same bean may bypass advice; if transaction/security advice is needed, call an injected service via the proper proxy.

## 9. Compatibility Adapter Instead of Keeping Old Logic

An adapter can decouple the JMX contract from the implementation:

\`\`\`java
public final class CacheAdministration {

    private final CacheMaintenanceService service;

    public CacheAdministration(CacheMaintenanceService service) {
        this.service = service;
    }

    @ManagedOperation(description = "DEPRECATED: use requestEviction")
    public void clearAll() {
        service.evictAllWithGuardrails();
    }

    @ManagedOperation(description = "Request bounded eviction")
    public String requestEviction(String region, String requestId) {
        return service.requestEviction(region, requestId);
    }
}
\`\`\`

In a real project, the class must be exported via annotation metadata or an appropriate interface; the service must implement validation, authorization, and auditing as designed. A compatibility adapter avoids duplicating business logic. When the support window ends, remove only the old entry point from the management contract rather than deleting the shared service.

However, `evictAllWithGuardrails()` must have a clear contract. If safety of the old operation cannot be guaranteed, consider revoking permissions or disabling it with notice; compatibility is not a reason to keep an uncontrollable operation active.

## 10. Distinguishing Deprecation, Disablement, and Removal

| Stage | Operation in MBeanInfo? | Invoke succeeds? | Purpose |
|---|---|---|---|
| Active | Yes | Old behavior | Normal usage |
| Deprecated | Yes | Usually still supported | Warn and migrate clients |
| Restricted | Yes | Only authorized callers/conditions | Reduce risk during transition |
| Disabled | May remain | Deliberately returns error | Block usage while keeping contract marker |
| Removed | No | Old clients cannot invoke | End old contract |

An operation that still appears but returns a “DISABLED” error is not equivalent to being removed. It helps scripts receive a clearer error, yet is still breaking behavior. Agree on the policy with operations teams.

Do not simply add a `confirmed=true` parameter and treat it as security. Callers can pass `true` themselves; permissions and confirmation must be bound to reliable identity, scope, and preconditions.

## 11. Versioning the Management API

There are several strategies:

### 11.1 Keep ObjectName and Add New Operations

\`\`\`text
com.example.ops:type=Cache,name=Catalog
  ├── clearAll()               [deprecated]
  └── requestEviction(region) [new]
\`\`\`

Suitable when keeping a single MBean. New clients can use the new method while old clients continue working during the transition.

### 11.2 New MBean per Version

\`\`\`text
com.example.ops:type=Cache,name=Catalog,api=v1
com.example.ops:type=Cache,name=Catalog,api=v2
\`\`\`

Suitable when two contracts differ significantly and must run in parallel. This increases registrations and requires clear ownership/lifecycle. Clients must select the right ObjectName; they do not automatically switch when the v1 MBean is removed.

### 11.3 Read-Only Observation on JMX, Control via Another Platform

If the old operation has major side effects, one path is:
- Keep JMX attributes read-only for health/status.
- Move control commands to a control plane with authentication, approval, and auditing.
- Publish a migration runbook and sunset date for the old operation.

This is often preferable when operations require tenant-scoped identity, two-person approval, or workflows more complex than JMX connector permissions provide.

## 12. When Clients Hard-Code ObjectName and Signature

A Java client:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.ops:type=Cache,name=Catalog");

connection.invoke(
    name,
    "clearAll",
    new Object[0],
    new String[0]);
\`\`\`

Can break when:
- ObjectName changes.
- Operation is removed.
- Signature changes to take parameters.
- Invoke permissions are narrowed.
- MBean moves to another server not served by the connector.
- MBean is registered only after a different startup point.
- Client uses stale cached metadata.

To ease migration, clients should include a discovery/validation step:

\`\`\`java
if (!connection.isRegistered(name)) {
    throw new IllegalStateException("Expected MBean not registered");
}

MBeanInfo info = connection.getMBeanInfo(name);
// Check operation + signature, not just name.
\`\`\`

Do not automatically fall back to an operation with similar semantics if it has side effects. For instance, `clearRegion("all")` is not necessarily equivalent to the old `clearAll()`. Only invoke a replacement when its contract is documented and approved by owners.

## 13. Compatibility Testing Before Deployment

An integration test can pin down the supported contract:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import javax.management.*;

class CacheJmxCompatibilityAssertions {

    static boolean hasOperation(
            MBeanInfo info, String operationName,
            String... parameterTypes) {

        return Arrays.stream(info.getOperations())
            .filter(op -> op.getName().equals(operationName))
            .anyMatch(op -> {
                MBeanParameterInfo[] signature = op.getSignature();
                if (signature.length != parameterTypes.length) {
                    return false;
                }
                for (int i = 0; i < signature.length; i++) {
                    if (!signature[i].getType()
                            .equals(parameterTypes[i])) {
                        return false;
                    }
                }
                return true;
            });
    }
}
\`\`\`

Test during the migration phase:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

assertTrue(hasOperation(info, "clearAll"));
assertTrue(hasOperation(
    info,
    "requestEviction",
    "java.lang.String",
    "java.lang.String"));
\`\`\`

After the approved removal date, update the test to:

\`\`\`java
assertFalse(hasOperation(info, "clearAll"));
assertTrue(hasOperation(
    info,
    "requestEviction",
    "java.lang.String",
    "java.lang.String"));
\`\`\`

This is a **contract test**, not just an implementation method test. It verifies that the exporter/assembler actually exposes the right operation. If overloads exist, compare the full signature rather than just the name.

### 13.1 Testing with a Real Client

An integration test should also create a JMX client via `MBeanServerConnection` and invoke the replacement on a safe fixture:

\`\`\`java
Object result = connection.invoke(
    name,
    "requestEviction",
    new Object[]{"test-region", "request-001"},
    new String[]{
        "java.lang.String",
        "java.lang.String"
    });
\`\`\`

Use a test service that does not delete production data. If the operation is asynchronous, check completion status rather than treating the initial response as final success.

## 14. Negative Test: Old Operation Must Disappear at the Right Time

After removal:

1. The MBean remains registered under the expected ObjectName.
2. The old operation is gone from `MBeanInfo`.
3. The replacement is present with the right signature.
4. Observation attributes are not lost.
5. A script using the new contract works.
6. A script attempting the old contract fails in the expected way.
7. Context shutdown unregisters cleanly without redeploy errors.

Do not test dangerous old operations in production just to prove they are gone. Inspecting `MBeanInfo` is a safer way to verify absence. In isolated test environments, negative invocation tests can be added if needed.

## 15. Controlling Rolling Deployments and Version Skew

A cluster with multiple JVMs may run different versions concurrently:

\`\`\`text
node-01: v2.4 — clearAll + requestEviction
node-02: v2.5 — clearAll + requestEviction
node-03: v2.6 — requestEviction only
\`\`\`

If a script controls multiple nodes simultaneously, it needs to know each node's contract. Switching all clients to `requestEviction` before all nodes have the new method causes errors on older nodes. Removing the old method before all clients migrate also causes errors.

Compatible rollout path:

\`\`\`text
Release A: add replacement, keep legacy operation
      |
      v
Upgrade all server nodes to support both
      |
      v
Migrate clients to replacement
      |
      v
Verify no legacy dependencies remain
      |
      v
Release B: deprecate/restrict legacy, monitor
      |
      v
Release C: remove legacy as planned
\`\`\`

Ordering must account for the system's rollout pattern. If a new client only supports the new contract, it cannot be deployed while older nodes lack support. A dual-path client may be needed, though any fallback must have safe semantics, especially for operations with side effects.

## 16. Side Effects and Idempotency During Migration

Removing an operation with side effects can push operators to look for workarounds or retry. Clearly document the replacement and how to verify results.

Suppose `clearAll()` is invoked over JMX and the connection times out. You cannot conclude the command did not run. If the client immediately switches to `requestEviction` and retries, the system may clear twice or trigger a cache stampede.

Mitigations:
- Operation ID or request ID.
- Status query to check whether a request was accepted/executed.
- Preconditions on state and scope.
- Bounded impact, rate limiting, and auditing.
- No blind retries after `IOException` or timeout.
- Recovery runbook when execution status is unknown.

Idempotency of final state does not mean repeated invocations have no side effects. `clearCache()` may leave the cache empty both times yet still trigger two waves of downstream load.

## 17. Auditing the Migration Process

You can track:
- Number of times the legacy operation is invoked.
- Caller identity if reliably provided by the connector/control plane.
- Target instance/ObjectName.
- Operation signature.
- Redacted parameters.
- Outcome: accepted/rejected/completed.
- Call source: script, UI, automation, or manual operation if identifiable.
- Last invocation time per environment.
- Time remaining until removal.

Do not log raw credentials, secrets, or personal data. `@ManagedOperation(description=...)` alone does not provide invocation auditing. If per-command identity is required and the JMX connector does not reliably pass caller identity, use a management gateway or control plane with dedicated authentication.

## 18. When Should a Legacy Operation Be Kept Longer?

Some operations are used only in rare situations:

- Recovering connections after a major outage.
- Cleaning up checkpoints after data corruption.
- Switching debug modes to investigate incidents.
- Managing disaster recovery systems.
- Repairing stuck queues.
- Running maintenance after several months.

Without usage telemetry, do not assume an operation is “unused” simply because it had zero hits for a week. A longer notice cycle or disaster recovery rehearsal in staging may be needed before removal.

However, if the old operation is unsafe, extending support must include permission restrictions, monitoring, and a clear sunset plan. Do not keep legacy operations indefinitely out of reluctance to coordinate.

## 19. Complete Deprecation Adapter Example

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Cache,name=Catalog",
    description = "Catalog cache management API")
public class CatalogCacheMBeanAdapter {

    private final CacheMaintenanceService service;

    public CatalogCacheMBeanAdapter(CacheMaintenanceService service) {
        this.service = service;
    }

    @Deprecated(since = "2.4", forRemoval = true)
    @ManagedOperation(
        description = "DEPRECATED: use requestEviction(region, requestId)")
    public void clearAll() {
        service.legacyClearAllWithGuardrails();
    }

    @ManagedOperation(
        description = "Request a bounded cache eviction")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "region",
            description = "Validated cache region"),
        @ManagedOperationParameter(
            name = "requestId",
            description = "Unique idempotency key")
    })
    public String requestEviction(String region, String requestId) {
        return service.requestEviction(region, requestId);
    }

    @ManagedOperation(
        description = "Read the current status of a request")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "requestId",
            description = "Existing request identifier")
    })
    public String getOperationStatus(String requestId) {
        return service.getOperationStatus(requestId);
    }
}
\`\`\`

`CacheMaintenanceService` here is an illustrative application service. In production, it must implement real validation, authorization, idempotency, auditing, and bounds. Naming `getOperationStatus` with one parameter causes it to be exported as an operation rather than a zero-argument attribute getter under the appropriate metadata model.

With Spring AOP, the adapter calls the injected service through its proxy so required advice still applies. Avoid calling the raw target directly and accidentally bypassing transactions/security.

## 20. Runbook for Removing an Actively Invoked Operation

### Before announcing the change

1. Identify ObjectName, operation, full signature, and behavior.
2. Capture `MBeanInfo` to record the current contract.
3. Inventory scripts, dashboards, runbooks, automation, and external clients.
4. Assign owners for the operation and consumers.
5. Classify side effects and rollback feasibility.
6. Design the replacement along with a rolling-upgrade support plan.
7. Agree on release/deprecation/removal dates.

### During the deprecation period

1. Add the replacement and keep legacy if safe.
2. Publish descriptions, release notes, and updated runbooks.
3. Add usage metrics/audits according to system reliability capabilities.
4. Update clients and deployment automation progressively.
5. Measure remaining legacy calls, including rare environments.
6. Test compatibility across multiple concurrently running versions.

### Before the removal date

1. Confirm operations teams have updated runbooks.
2. Confirm no known callers still depend on the old operation.
3. Verify edge cases such as disaster recovery.
4. Ensure all nodes support the new operation.
5. Have a rollback plan and suitable release window.
6. Finalize contract tests for the new version.

### After removal

1. Verify `MBeanInfo` no longer contains the old operation.
2. Verify the replacement works against a test fixture.
3. Monitor `ReflectionException`, failed invokes, and error logs.
4. Update dashboards, CLI help, docs, and troubleshooting notes.
5. Do not automatically restore the legacy operation if the reason for removal was a severe security risk.

## 21. Common Misconceptions

**“Removing a Java method only affects compiled code.”** False: JMX clients may invoke by string name and only fail at runtime.

**“No references in source means nobody uses it.”** False: automation and runbooks may live in other repositories/systems.

**“Renaming an operation keeps the same behavior so it isn't breaking.”** False: clients invoke by name and signature.

**“`@Deprecated` will automatically warn JConsole.”** Do not assume so. Publish deprecation via JMX metadata, documentation, and communication.

**“Add the replacement and delete the old operation immediately.”** Dangerous when clients or nodes upgrade via rolling rollouts.

**“Client can't see the operation means the bean was deleted.”** Not necessarily; the MBean may still exist without the operation in MBeanInfo.

**“Keeping ObjectName keeps all clients compatible.”** Insufficient: operation signatures and behavior can still change.

**“Timeout after invoke means the operation didn't execute.”** Not certain; do not blindly retry operations with side effects.

**“Separating versions by domain automatically creates separate access permissions.”** No. ObjectName namespaces do not replace connector authorization.

## 22. Practice Exercises

**Exercise 1 — Impact of removal.** A script invokes `clearAll()` using `MBeanServerConnection.invoke()`. After deployment, the MBean still exists but the operation is gone. Describe how to verify via `MBeanInfo` and the expected runtime error type.

**Exercise 2 — Signature migration.** Operation `reset(int)` changes to `reset(long)`. Why is this a breaking change even though the name stays `reset`? Write a test comparing signatures.

**Exercise 3 — Rolling cluster.** Three JVMs run different versions. Order the deployment of the replacement, server node upgrades, client upgrades, and removal of the legacy operation.

**Exercise 4 — Legacy runbook.** An operation has no usage logs for 6 months, but appears in a disaster recovery runbook. Can it be deleted immediately? Propose an approval and rehearsal process.

**Exercise 5 — Compatibility adapter.** Write a legacy method calling a new service and returning a compatible result, ensuring it does not bypass AOP advice.

**Exercise 6 — Side effects.** A client hits a timeout calling the old operation, then tries the new operation “just to be sure”. Analyze the double-execution risk and propose request IDs/status checks.

## Summary

Removing an operation actively invoked by administration tools changes a **runtime JMX contract**, not just Java source code. Clients depend on ObjectName, operation name, signature, return type, permissions, and semantics. The safe path is to inventory dependencies, observe usage, announce deprecation, add a replacement with a clear contract, migrate clients in phases, support rolling version skew, and remove only after verification. `MBeanInfo` and integration tests lock down the contract, while auditing/runbooks/rollbacks protect operations. For operations with side effects, managing idempotency and avoiding blind retries are especially critical. When each step has a clear owner and verification criteria, systems can evolve management APIs without breaking administration tools serving production.

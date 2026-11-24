# Reviewing Compatibility When Changing a Management Interface in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Identify a **management interface** as a contract between a JMX MBean and its consuming clients.
- Classify changes that can break compatibility: changing \`ObjectName\`, renaming attributes, changing data types, read/write semantics, operations, parameters, return types, notifications, and execution behavior.
- Distinguish **Java source/binary compatibility** from **JMX runtime compatibility**.
- Evaluate the impact of Standard MBean, MXBean, Spring \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, and AOP proxies.
- Build **\`MBeanInfo\`-based contract tests** alongside real read, write, and operation invocation checks.
- Verify compatibility for JMX remote clients, Open Types, and serialization.
- Plan migrations, aliases, deprecation, and rollbacks when a management API change is unavoidable.
- Design a pre-release review checklist to prevent breakage for monitoring collectors, scripts, and operational tools.

## 1. The Management Interface Is a Public Contract

A Java service may change its implementation frequently. However, once a method or attribute is exported via JMX, it becomes part of an interface consumed outside the codebase.

JMX client example:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueManagement,name=Primary"
);

long depth = (Long) connection.getAttribute(
    name,
    "PendingJobs"
);

connection.invoke(
    name,
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

The contract includes:

- **MBean identity:** \`ObjectName\` and target \`MBeanServer\`/connector.
- **Attribute schema:** name, type, readable/writable flags, boolean \`is\`-getter.
- **Operation schema:** name, parameter types/order, return type, impact.
- **Notification schema:** types and payload semantics.
- **Behavior:** units, timing, side effects, idempotency, exceptions.
- **Security:** who can read, write, or invoke.
- **Lifecycle:** when the MBean is present, unregistered, or replaced.

These consumers are typically not updated automatically by an IDE when a team refactors source code:

\`\`\`text
MBean exporter
    |
    v
MBeanServer
    |
    +-- JConsole / VisualVM
    +-- Monitoring collector
    +-- SRE scripts
    +-- Alert rules
    +-- Remote JMX applications
\`\`\`

Therefore, reviewing a management interface must evaluate the **client-visible contract**, not just method signatures in the repository.

## 2. Three Compatibility Layers to Distinguish

### Layer 1 — Java source compatibility

Will a Java client still compile against the new interface? For example, changing a return type from \`int\` to \`long\` can break code assigning the result to an \`int\`.

### Layer 2 — Java binary compatibility

Can a previously compiled client still link and call the Java method with a matching binary descriptor? Changing a method descriptor can trigger errors such as \`NoSuchMethodError\` when the client is not rebuilt.

### Layer 3 — JMX management compatibility

Do clients using the string-based JMX API still find the expected \`ObjectName\`, attributes, and operations? Is actual \`MBeanInfo\` after deployment still compatible?

Refactoring example:

\`\`\`java
public long getPendingJobs()
\`\`\`

to:

\`\`\`java
public long getWaitingTasks()
\`\`\`

Java call sites in the repository may be fully updated. Yet a JMX client calling:

\`\`\`java
connection.getAttribute(name, "PendingJobs");
\`\`\`

can hit an \`AttributeNotFoundException\`.

**Conclusion:** Java compilation tests cannot substitute for JMX contract tests.

## 3. Example Initial Management Interface

Let's design a Standard MBean for a clear baseline.

File \`QueueManagementMBean.java\`:

\`\`\`java
package example.jmx;

public interface QueueManagementMBean {

    long getPendingJobs();

    boolean isPaused();

    void pauseProcessing();

    void resumeProcessing();
}
\`\`\`

File \`QueueManagement.java\`:

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public class QueueManagement implements QueueManagementMBean {

    private final AtomicLong pending = new AtomicLong(5);
    private final AtomicBoolean paused = new AtomicBoolean();

    @Override
    public long getPendingJobs() {
        return pending.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void pauseProcessing() {
        paused.set(true);
    }

    @Override
    public void resumeProcessing() {
        paused.set(false);
    }
}
\`\`\`

Baseline JMX contract:

| Element | Name | Type/Semantics |
|---|---|---|
| ObjectName | \`learning.jmx:type=QueueManagement,name=Primary\` | MBean identity |
| Attribute | \`PendingJobs\` | \`long\`, read-only, pending jobs count |
| Attribute | \`Paused\` | \`boolean\`, read-only |
| Operation | \`pauseProcessing\` | 0 parameters, \`void\` |
| Operation | \`resumeProcessing\` | 0 parameters, \`void\` |

These values should be locked into a test fixture or intentional contract snapshot.

## 4. Types of Changes and Risk Levels

| Change | Common Impact | How to Evaluate |
|---|---|---|
| Change \`ObjectName\` | Client cannot find MBean | \`isRegistered\`, discovery test |
| Rename attribute | \`AttributeNotFoundException\` | \`MBeanInfo\` attribute names |
| Change \`int\` -> \`long\` | Cast/type mismatch | Type metadata and runtime value |
| Change read-only getter to writable | Expanded mutation privilege | \`isWritable\`, authorization |
| Remove writable setter | Existing admin scripts fail | \`setAttribute\` negative/compatibility tests |
| Rename operation | \`ReflectionException\`/operation not found | \`MBeanInfo\`, \`invoke\` |
| Change parameter types | Signature mismatch | Parameter type list |
| Change return type | Client conversion or binary break | Metadata and invocation result |
| Change units | Alerts trigger at wrong thresholds despite unchanged type | Semantic tests |
| Change sync to async | Client misinterprets completion | Behavioral contract |
| Change notification type | Listeners/filters miss events | Notification metadata and delivery tests |
| Switch Standard MBean to MXBean | Mapping/representation changes | Open Type metadata, remote clients |
| Change Spring AOP proxy strategy | Metadata/invocation may differ | Proxy and exporter integration tests |
| Add sensitive operation | Expands attack surface | Security review |
| Move MBean to another server | Clients connect to wrong registry | Server/connector identity |

Not every change necessarily breaks every client. However, each category above requires evaluating real consumers and contracts.

## 5. Changing ObjectName

Original example:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary
\`\`\`

Refactored to:

\`\`\`text
learning.jmx:type=QueueAdministration,name=Primary
\`\`\`

Even if the MBean keeps the exact same attributes, scripts using the old \`ObjectName\` will not find the resource.

**Safe approach when semantics are unchanged:** keep the old logical \`ObjectName\` even when the Java class is renamed.

With Spring:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueAdministration {
    // ...
}
\`\`\`

Do not generate \`ObjectName\` from \`bean.getClass().getSimpleName()\` because Spring AOP can produce unstable runtime proxy class names.

If changing \`ObjectName\` is unavoidable, provide a migration window or an adapter publishing both identities simultaneously without creating ownership conflicts.

## 6. Renaming an Attribute

Originally:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return queue.pendingJobs();
}
\`\`\`

After refactoring:

\`\`\`java
@ManagedAttribute
public long getWaitingTasks() {
    return queue.pendingJobs();
}
\`\`\`

From JMX's perspective, \`PendingJobs\` disappears and \`WaitingTasks\` appears.

Preserving compatibility in a management facade:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return queue.pendingJobs();
}

@ManagedAttribute
public long getWaitingTasks() {
    return queue.pendingJobs();
}
\`\`\`

During the migration window, both names can be exported. If the semantics of "job" and "task" genuinely differ, do not create a misleading alias; publish a new contract and document the difference instead.

## 7. Changing Attribute Type

Example:

\`\`\`java
@ManagedAttribute
public int getProcessedJobs() { ... }
\`\`\`

to:

\`\`\`java
@ManagedAttribute
public long getProcessedJobs() { ... }
\`\`\`

Type metadata changes:

\`\`\`text
ProcessedJobs: int
ProcessedJobs: long
\`\`\`

An existing client:

\`\`\`java
Integer count = (Integer) connection.getAttribute(
    name, "ProcessedJobs"
);
\`\`\`

can hit a \`ClassCastException\` when the runtime value changes to \`Long\`.

Do not rely on autoboxing to assume contract compatibility. Management APIs should migrate cleanly:

\`\`\`java
@ManagedAttribute
public int getProcessedJobs() {
    return legacyIntCount();
}

@ManagedAttribute
public long getProcessedJobsLong() {
    return service.processedCount();
}
\`\`\`

\`legacyIntCount()\` must have an explicit overflow policy—clamping, throwing an error, or documenting lifetime bounds—rather than silently truncating numbers.

Check the type via \`MBeanAttributeInfo.getType()\`, and check the actual runtime value via \`getAttribute\`.

## 8. Changing Primitive/Wrapper and Null Semantics

Changing:

\`\`\`java
public int getQueueDepth()
\`\`\`

to:

\`\`\`java
public Integer getQueueDepth()
\`\`\`

can change the JMX metadata type from \`int\` to \`java.lang.Integer\`. Additionally, the new getter can return \`null\`.

Even when non-null values box identically, the metadata contract has changed. Monitoring tools may inspect the type string to pick a converter.

If \`null\` represents "no data", do not replace it with \`0\` unless \`0\` carries the same semantics. You can add:

\`\`\`java
@ManagedAttribute
public boolean isQueueDepthAvailable() { ... }

@ManagedAttribute
public long getQueueDepth() { ... }
\`\`\`

to keep the type stable while representing availability separately, depending on the business contract.

## 9. Changing Operation Signatures

A JMX operation is identified not only by name, but also by parameter types.

Old example:

\`\`\`java
@ManagedOperation
public void setQueueLimit(int limit) { ... }
\`\`\`

Client:

\`\`\`java
connection.invoke(
    name,
    "setQueueLimit",
    new Object[] { 100 },
    new String[] { "int" }
);
\`\`\`

After changing the method to:

\`\`\`java
@ManagedOperation
public void setQueueLimit(long limit) { ... }
\`\`\`

clients passing signature \`"int"\` can no longer invoke the operation.

Changing an interface from \`int\` -> \`long\` can break Java compilation or require rebuilds; JMX clients passing the \`"int"\` type string also need migration.

One intentional approach is keeping the legacy overload if the framework/exporter supports it and semantics are clear:

\`\`\`java
@ManagedOperation
public void setQueueLimit(int limit) {
    service.setLimit(limit);
}

@ManagedOperation
public void setQueueLimit(long limit) {
    service.setLimit(limit);
}
\`\`\`

However, test JMX overload resolution, parameter type arrays, and tooling compatibility. Not all clients display overloads conveniently.

## 10. Operation Semantics Matter More Than Names Alone

Suppose \`rebuildIndex()\` originally ran synchronously, returning only upon completion.

After an upgrade, the operation only enqueues a job and returns immediately.

Name and signature remain identical, yet the behavioral contract has changed:

- May the client still treat method return as completion?
- If the client retries, does it create multiple jobs?
- Is there a job ID to track?
- Does a timeout mean the task stopped?
- Is there rate limiting/a concurrency gate?

A new name like \`requestIndexRebuild\` paired with a status attribute may reflect the semantics far better. For incompatible behavioral changes, migration must update runbooks and automation clients.

Do not evaluate compatibility solely through \`MBeanInfo\` when operations have side effects or timing contracts.

## 11. Read/Write Semantics Are Part of Both Contract and Security

Example v1:

\`\`\`java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}
\`\`\`

v2 adds a setter:

\`\`\`java
@ManagedAttribute
public void setMaxWorkers(int value) {
    validate(value);
    maxWorkers = value;
}
\`\`\`

The attribute shifts from read-only to writable. This is an **expansion of administrative privilege**, not merely API convenience.

Conversely, removing a setter breaks clients calling \`setAttribute\`.

Check:

\`\`\`java
MBeanAttributeInfo info = ...;

assertTrue(info.isReadable());
assertFalse(info.isWritable());
\`\`\`

If JMX connector read/write permissions are overly broad, adding a setter can open a new attack surface. Review authorization and auditing alongside contract tests.

## 12. Notification Contracts Can Also Break

An MBean emits notifications:

\`\`\`text
learning.queue.overloaded
learning.queue.recovered
\`\`\`

Listeners may filter on the exact type string:

\`\`\`java
filter.enableType("learning.queue.overloaded");
\`\`\`

If a new version renames the type to:

\`\`\`text
learning.queue.thresholdExceeded
\`\`\`

existing listeners stop receiving the events.

More than just the type string matters. Check:

- Source semantics.
- Sequence number behavior.
- Timestamp units.
- Message and \`userData\`.
- Notification delivery timing.
- Whether replay exists on client reconnect.
- Whether new notification volumes affect polling/automation.

\`MBeanInfo.getNotifications()\` verifies metadata type lists; integration tests emitting real events verify delivery.

## 13. Standard MBean, MXBean, and Spring Annotations

### Standard MBean

Management interface by convention:

\`\`\`java
public interface QueueManagementMBean {
    long getPendingJobs();
    void pauseProcessing();
}
\`\`\`

Changing this interface directly affects \`MBeanInfo\` and Java clients.

### MXBean

MXBeans map Java types to Open Types. For example, when returning a structured object, remote clients may see \`CompositeData\` instead of a custom Java class. Changing fields, keys, or Open Type schemas requires compatibility tests.

### Spring annotation-based MBean

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueManagement {

    @ManagedAttribute
    public long getPendingJobs() { ... }

    @ManagedOperation
    public void pauseProcessing() { ... }
}
\`\`\`

The exporter and metadata assembler determine the actual JMX schema.

In all cases, **Java declarations are only the input**. The contract must be verified against the \`MBeanServer\` after the application context initializes.

## 14. Impact of Spring AOP Proxies

Spring AOP may use JDK dynamic proxies or class-based proxies.

\`\`\`text
Caller
  -> Spring AOP proxy
  -> target service
\`\`\`

Scenarios affecting the management interface:

- Getter annotated on the implementation is missing from the JDK proxy interface.
- Target class metadata discovered by the exporter changes when switching proxy strategies.
- Operation appears in metadata yet is not invocable through the proxy under the current config.
- Unwrapping the proxy to export the raw target drops transaction/security advice.
- \`ObjectName\` derived from runtime proxy class name changes unexpectedly.

Use \`AopUtils\`:

\`\`\`java
Object bean = context.getBean("queueService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

Still, inspecting proxy classes does not replace \`getMBeanInfo\` and invocation tests.

### Management facade

Decouple the JMX contract from the business interface:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueManagement,name=Primary"
)
public class QueueManagementFacade {

    private final QueueService service;

    public QueueManagementFacade(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingJobs() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void pauseProcessing() {
        service.pause();
    }
}
\`\`\`

The facade keeps JMX names/types/semantics stable while the service can refactor methods or proxy strategies. If the service needs AOP advice, the facade should call the Spring-managed proxy of the service rather than instantiating a target with \`new\` outside the container.

## 15. Designing a Contract Baseline

A baseline may include:

\`\`\`text
MBean:
  learning.jmx:type=QueueManagement,name=Primary

Attributes:
  PendingJobs:
    type: long
    readable: true
    writable: false
    semantics: current pending job count
  Paused:
    type: boolean
    readable: true
    writable: false

Operations:
  pauseProcessing:
    parameters: []
    returnType: void
    semantics: stop accepting new jobs
  resumeProcessing:
    parameters: []
    returnType: void

Notifications:
  learning.queue.overloaded
\`\`\`

The example above is a documentation representation, not a mandate for a specific YAML schema. Baselines can be stored in Java test assertions or a project-managed versioned contract artifact.

Do not diff raw textual snapshots and treat any metadata array reordering as a breaking change. Normalize/sort names before comparing to avoid noise.

## 16. MBeanInfo Contract Tests

Testing JMX metadata is a key way to catch interface drift.

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class QueueManagementContractTest {

    private final MBeanServer server = /* test MBeanServer */ null;

    @Test
    void keepsAttributeContract() throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueManagement,name=Primary"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        MBeanAttributeInfo pending = Arrays.stream(
            info.getAttributes()
        ).filter(a -> "PendingJobs".equals(a.getName()))
         .findFirst()
         .orElseThrow();

        assertEquals("long", pending.getType());
        assertTrue(pending.isReadable());
        assertFalse(pending.isWritable());
    }

    @Test
    void keepsOperationContract() throws Exception {
        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueManagement,name=Primary"
        );

        MBeanOperationInfo pause = Arrays.stream(
            server.getMBeanInfo(name).getOperations()
        ).filter(o -> "pauseProcessing".equals(o.getName()))
         .findFirst()
         .orElseThrow();

        assertEquals("void", pause.getReturnType());
        assertEquals(0, pause.getSignature().length);
    }
}
\`\`\`

\`server\` is a placeholder for the test fixture: the project must create an \`MBeanServer\`, register the MBean, and clean up per lifecycle. Never use \`null\` in real tests.

Checking attributes/operations by name and type catches changes that Java compilation misses.

## 17. Runnable Integration Test Example with an Isolated MBeanServer

You can build a self-contained test fixture:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class StandardMBeanCompatibilityTest {

    @Test
    void exportsExpectedContract() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer(
                "compat.test"
            );

        ObjectName name = new ObjectName(
            "learning.jmx:type=QueueManagement,name=Primary"
        );

        try {
            server.registerMBean(new QueueManagement(), name);

            assertTrue(server.isRegistered(name));
            assertEquals(
                "long",
                java.util.Arrays.stream(
                    server.getMBeanInfo(name).getAttributes()
                ).filter(a -> "PendingJobs".equals(a.getName()))
                 .findFirst().orElseThrow().getType()
            );

            Object value =
                server.getAttribute(name, "PendingJobs");

            assertInstanceOf(Long.class, value);

            server.invoke(
                name,
                "pauseProcessing",
                new Object[0],
                new String[0]
            );

            assertEquals(
                true,
                server.getAttribute(name, "Paused")
            );
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
\`\`\`

This example verifies schema and behavior through the JMX API. In a Spring system, add a context test with \`MBeanExporter\` and AOP proxies to verify the corresponding integration.

## 18. Testing Compatibility from an Old Client's Perspective

A test using \`MBeanServer\` with the old names/types is good, yet a **legacy client fixture** adds even stronger coverage.

Example:

\`\`\`java
public final class LegacyQueueClient {

    private final MBeanServerConnection connection;
    private final ObjectName name;

    public LegacyQueueClient(
            MBeanServerConnection connection,
            ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public long pendingJobs() throws Exception {
        return (Long) connection.getAttribute(
            name, "PendingJobs"
        );
    }

    public void pause() throws Exception {
        connection.invoke(
            name,
            "pauseProcessing",
            new Object[0],
            new String[0]
        );
    }
}
\`\`\`

When upgrading the MBean implementation, run the legacy client fixture **without modifying client code**.

This catches bugs that inspecting \`MBeanInfo\` alone might miss:

- Operation keeps the same signature yet changes behavior.
- Getter returns values in a different unit.
- MBean resides on a different server.
- Authorization blocks a previously permitted action.
- Remote serialization changes.

If production runs multiple client versions, tests should cover all supported versions.

## 19. Before/After Version Comparison

A systematic evaluation collects contract snapshots from the prior and new versions:

\`\`\`text
Version A JMX metadata
         |
         v
Normalized contract baseline
         |
         | compare
         v
Version B JMX metadata
         |
         +-- Removed attributes?
         +-- Changed types?
         +-- New writable attributes?
         +-- Changed operation signatures?
         +-- Removed notification types?
\`\`\`

Process:

1. Start both versions in independent test environments.
2. Query the same logical \`ObjectName\`.
3. Fetch \`MBeanInfo\` and normalize the lists.
4. Compare names, types, readable/writable flags, and operation signatures.
5. Run required behavioral tests.
6. Classify changes as compatible, additive, breaking, or security-sensitive.
7. Approve breaking changes only when a migration plan exists.

A newly added attribute is usually additive, yet can also expand exposure of sensitive information. Thus "additive" does not mean "no security review needed".

## 20. Remote JMX Compatibility

Remote clients face issues that do not occur within the same JVM:

- Custom return-type classes may be absent from the client classpath.
- Serialization or \`serialVersionUID\` may change.
- MXBean/Open Type mappings change \`CompositeData\` shapes.
- Connector or transport policies change.
- TLS certificate/trust configuration affects connectivity.
- Client credentials/authorization change.
- \`ObjectName\` is registered on a different \`MBeanServer\` than the connector serves.

For APIs consumed by diverse clients, primitives, \`String\`, and Open Types with clear contracts usually reduce coupling compared to custom Java objects.

Do not treat a local JUnit test using \`MBeanServer\` as proof that all remote clients remain compatible. When remote usage exists, run at least one integration test through a secured connector.

## 21. Compatibility and Authorization

A management interface can change permissions without changing method names.

For example, a new version adds:

\`\`\`java
@ManagedOperation
public void clearAllQueues() { ... }
\`\`\`

This introduces a new surface with side effects. If the connector uses overly broad readwrite permissions, an old automation account may gain the ability to invoke the new operation.

Conversely, protecting an existing operation with new method-level security can cause previously valid clients to be denied.

During release review:

- Verify the interface contract.
- Verify readonly/readwrite permissions and connector granularity.
- Verify the Spring AOP method security call path.
- Test both authorized and unauthorized identities.
- Audit sensitive operations.
- Do not rely on HTTP Spring Security to protect JMX connectors.

Security changes are behavioral changes affecting compatibility and must be evaluated alongside the contract schema.

## 22. Migration Strategies

When a management interface change is unavoidable:

### Option A — Preserve the old contract

Keep old names/types on the facade and change only internal logic.

Suitable when semantics remain unchanged.

### Option B — Coexist old/new attributes

Example:

\`\`\`java
@ManagedAttribute
public long getPendingJobs() { ... }

@ManagedAttribute
public long getQueuedTasks() { ... }
\`\`\`

Publish both during the migration window and document the canonical name.

### Option C — Versioned ObjectName

Example:

\`\`\`text
learning.jmx:type=QueueManagement,name=Primary,version=1
learning.jmx:type=QueueManagement,name=Primary,version=2
\`\`\`

Use only when the APIs truly differ and must run in parallel. Two ObjectNames are two separate registrations; ownership, lifecycle, and consistent data must be managed.

### Option D — Adapter/facade for legacy clients

An adapter can continue returning old types, units, and operation names while delegating to the new service implementation.

### Option E — Planned breaking release

If keeping compatibility is infeasible, announce the breaking change, update operator docs, test critical consumers, and prepare a rollback strategy.

Do not silently rename or change types in a maintenance patch while out-of-repo clients still depend on them.

## 23. Pre-Release Review Checklist

1. Are existing ObjectNames still registered in the same \`MBeanServer\`/connector?
2. Did any attribute names change?
3. Did any attribute types change?
4. Did read/write semantics change?
5. Did units, nullability, or value ranges change?
6. Did any operation names change?
7. Did parameters or return types change?
8. Did sync/async behavior or side effects change?
9. Did notification types/payloads change?
10. Did Standard MBean/MXBean representations change?
11. Did Spring exporter/assembler settings change?
12. Did JDK dynamic proxy/class-based proxy strategy change?
13. Did security/authorization change?
14. Are remote client classpaths/serialization affected?
15. Do legacy client integration tests exist?
16. Are a consumer inventory and migration plan in place?
17. Is a rollback plan in place?
18. Were \`MBeanInfo\` and actual invocations verified?
19. Were \`ObjectName\` collisions/registration lifecycle verified?
20. Were documentation and runbooks updated?

## 24. Common Errors

| Symptom | Possible Cause | Mitigation |
|---|---|---|
| Client hits \`AttributeNotFoundException\` | JMX getter renamed or not exported | Check \`MBeanInfo\` and compatibility alias |
| Client fails casting \`Integer\`/\`Long\` | Attribute type changed | Test metadata, preserve legacy type |
| Operation \`invoke\` fails | Name or parameter signature changed | Compare \`MBeanOperationInfo\` |
| JConsole sees MBean yet scripts break | Contract changed even though \`ObjectName\` remains | Compare attributes/operations |
| Proxy change drops getter from MBean | JDK proxy interface lacks method | Test facade/assembler/proxy strategy |
| Remote client fails deserialization | Custom return type changed | Use Open Types or stable types |
| Alerts fire at wrong thresholds | Units/semantics changed | Document units explicitly, migrate |
| Bot invokes new operation unexpectedly | Overly broad readwrite permissions | Security review and separate surface |
| MBean moves to another server | \`Exporter.server\` changed | Verify \`MBeanServer\`/connector |
| Closing one context deletes another's MBean | Shared \`ObjectName\` ownership | Test lifecycle and policies |
| Notification listener misses events | Notification type changed | Contract tests and migration |
| Client times out then retries causing side effects | Operation async/timeout semantics changed | Job ID, idempotency, and runbook |

## 25. Hands-On Exercises

### Exercise 1 — Renaming an attribute

Create a v1 MBean with \`PendingJobs\`. Rename the getter to \`WaitingTasks\`. Run the legacy client fixture and observe the failure. Add a compatibility getter and re-run.

### Exercise 2 — Changing type

Create v1 \`ProcessedJobs\` of type \`int\`, and v2 of type \`long\`. Use \`MBeanInfo\` and \`getAttribute\` to catch the type break. Propose a migration alias.

### Exercise 3 — Operation signature

Replace \`setQueueLimit(int)\` with \`setQueueLimit(long)\`. Inspect operation signatures and client \`invoke\` with \`"int"\`. Design a compatibility strategy.

### Exercise 4 — AOP proxy

Export a Spring service with a JDK proxy, then switch to a class-based proxy. Verify whether \`ObjectName\`, metadata, and invocation remain intact. If not, try a management facade.

### Exercise 5 — Remote MXBean

Create an MXBean returning \`CompositeData\` or a type supported by Open Type mapping. Change the schema and test a legacy remote client. Record field/key compatibility findings.

### Exercise 6 — Security-sensitive release

A new MBean adds a \`clearCache\` operation. Evaluate permissions for an automation bot using readonly vs. readwrite accounts, and propose negative permission tests before release.

## 26. Core Takeaways

- **A management interface is a public API contract**, even when published over JMX rather than HTTP.
- Java source/binary compatibility does not replace JMX runtime compatibility.
- \`ObjectName\`, attribute names/types, writable flags, operation signatures, notifications, and semantics all require evaluation.
- \`MBeanInfo\` is the source of truth for actual post-export metadata.
- Proxy strategies, Spring JMX exporters, and remote serialization can alter the client-visible contract.
- A management facade isolates the management contract from business refactoring.
- Compatibility tests should run alongside legacy client fixtures and behavioral tests.
- Breaking changes require migration, documentation, consumer coordination, and a rollback plan.

## References

- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework AOP Proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

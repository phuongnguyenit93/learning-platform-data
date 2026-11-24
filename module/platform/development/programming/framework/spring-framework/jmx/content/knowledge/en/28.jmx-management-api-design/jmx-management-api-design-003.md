# Keeping the Management Interface Compatible Across Spring Framework JMX Upgrades

## 1. Lesson Objectives

A JMX management API does not serve only someone opening JConsole or Java Mission Control. It can be consumed by monitoring agents, shell scripts, dashboards, alerts, automated tests, and other operational tools. Therefore, when upgrading an application or Spring Framework, even a small change to an `ObjectName`, attribute, operation, or data type can break existing clients.

This lesson belongs to **Spring Framework JMX → Management API Design**. After this lesson, you will be able to:

- Treat the management interface as a versioned contract.
- Distinguish between **compatible**, **conditionally compatible**, and **breaking** changes.
- Protect `ObjectName`, attribute names, data types, readability/writability, operation names, and parameter signatures.
- Keep the API stable when refactoring Java classes, changing annotations, swapping assemblers, or enabling Spring AOP.
- Establish deprecation processes, aliases, versioned ObjectNames, and multi-version rollouts.
- Write contract tests comparing the current version's `MBeanInfo` against a published baseline.
- Recognize the limits of remote JMX, serialization, Open Types, and management automation.

## 2. A Management API Is a Public Contract

Suppose the system exports an MBean:

```text
com.example.orders:type=Queue,name=Payment
```

with the contract:

```text
Attributes:
  PendingCount : int      readable=true, writable=false
  Paused       : boolean  readable=true, writable=true

Operations:
  retryFailed(int maxCount) : void
  resetStatistics()         : void

Notifications:
  com.example.orders.queue.overloaded
```

An operational script might invoke:

```java
Object pending = connection.getAttribute(
    name, "PendingCount"
);

connection.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);
```

If an upgrade renames `PendingCount` to `QueueDepth`, the old script fails even though business logic still works. If a parameter changes from `int` to `long`, a client passing signature `"int"` may receive an invocation error. If `ObjectName` changes, the client may fail to find the MBean.

That is why management must be treated as an API consumed from outside the process, not merely a set of internal method names.

## 3. Elements That Make Up a JMX Contract

A JMX contract consists of at least the following layers:

| Element | Example | Risk When Changed |
| --- | --- | --- |
| `ObjectName` | `com.example.orders:type=Queue,name=Payment` | Client cannot locate the MBean |
| Domain/key properties | `type=Queue,name=Payment` | Query patterns and dashboards stop matching |
| Attribute name | `PendingCount` | `getAttribute` fails |
| Attribute type | `int` | Wrong cast/deserialization |
| Readability/writability | `readable=true,writable=false` | Client read/write is no longer valid |
| Operation name | `retryFailed` | `invoke` cannot find operation |
| Operation signature | `int` | Wrong overload invoked |
| Operation return type | `void` | Client handles response incorrectly |
| Notification type | `queue.overloaded` | Listeners/filters stop receiving events |
| Open MBean data schema | `CompositeType`, `TabularType` | Client cannot parse results |
| Behavior | Bounds, side effects, errors | Automation may misbehave even if signature stays unchanged |

Do not compare only Java interface source code. JMX clients see the **metadata registered in `MBeanServer`**, which can be affected by the exporter, assembler, proxies, annotations, or JVM.

## 4. Compatibility Differs from Compilability

In Java, changing:

```java
int getPendingCount();
```

to:

```java
long getPendingCount();
```

may be a reasonable change in business code. In JMX, however, the `PendingCount` attribute changes from `int` to `long`, causing an existing client:

```java
Integer count = (Integer)
    connection.getAttribute(name, "PendingCount");
```

to fail at runtime.

Similarly, a new Java method overload may compile fine, yet JMX clients invoke by operation name and an **array of parameter type names**, for example:

```java
new String[] { "int" }
```

If the signature changes, clients have no automatic way to adapt.

Consequently, compatibility tests must run at the JMX layer, not only at the compilation or class-level unit test layer.

## 5. Types of Changes and Compatibility Levels

Practical classification table:

| Change | Typical Assessment | Explanation |
| --- | --- | --- |
| Add a new read-only attribute | Usually compatible | Old clients continue reading old attributes |
| Add a newly named operation | Usually compatible | Does not remove old operations; consider security |
| Add a new notification type | Usually compatible, but check listeners | Broadly filtering listeners may receive extra events |
| Change description | Usually technically compatible | May affect tools relying on descriptions |
| Change key property order in ObjectName text | Does not change identity | `ObjectName.equals()` remains true |
| Change domain or key properties | Breaking | Different MBean name |
| Rename an attribute | Breaking | Old clients cannot find it |
| Change an attribute type | Breaking | Client casts/schemas may fail |
| Make a readable attribute unreadable | Breaking | Old clients can no longer read it |
| Remove attribute writability | Breaking for writers | `setAttribute` scripts will fail |
| Rename an operation | Breaking | `invoke` cannot find it |
| Change operation parameter types/order | Breaking | Signature mismatch |
| Change operation return type | Potentially breaking | Client parsing/casting differs |
| Remove an existing overload | Breaking | Clients using that overload fail |
| Change operation semantics while keeping name | Semantic breaking | May cause operational incidents |
| Rename notification type | Breaking for listeners/filters | Old filters no longer match |

"Usually compatible" does not mean unconditionally safe. An automated collector enumerating all operations can be affected when the API expands, and a new notification type can trigger overly broad listeners. Compatibility always depends on **actual clients**.

## 6. ObjectName Must Be Stable

Example ObjectName:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

Choose domain/key properties representing logical resources rather than runtime details like PID, object identity, random UUID, or proxy class name.

Unstable example:

```text
com.example.orders:type=Queue,name=Payment,pid=48122
com.example.orders:type=Queue,name=Payment,pid=53280
```

If a dashboard relies on an exact ObjectName, every restart changes the name.

More stable name:

```text
com.example.orders:type=Queue,name=Payment
```

In a multi-JVM system, the same ObjectName can exist on different servers. Collectors should track endpoint/instance identity separately rather than forcing dynamic details into the internal ObjectName when unnecessary.

### Key Order Is Not a Breaking Change

```java
ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Payment,type=Queue"
);

System.out.println(first.equals(second)); // true
```

When comparing, use `ObjectName.equals()` or canonical name, not just `String.equals()`.

## 7. Explicit Standard MBean Interface

One way to define a management contract is a dedicated Java interface:

```java
package com.example.orders.jmx;

public interface QueueAdminMBean {

    int getPendingCount();

    boolean isPaused();

    void setPaused(boolean paused);

    void retryFailed(int maxCount);
}
```

Implementation:

```java
package com.example.orders.jmx;

public class QueueAdmin implements QueueAdminMBean {

    private final QueueService service;

    public QueueAdmin(QueueService service) {
        this.service = service;
    }

    @Override
    public int getPendingCount() {
        return service.pendingCount();
    }

    @Override
    public boolean isPaused() {
        return service.isPaused();
    }

    @Override
    public void setPaused(boolean paused) {
        service.setPaused(paused);
    }

    @Override
    public void retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException(
                "maxCount must be between 1 and 100"
            );
        }
        service.retryFailed(maxCount);
    }
}
```

`QueueService` is an application-defined business interface. The `QueueAdmin` adapter separates the management path from the business implementation, allowing the service to be refactored while keeping method names in the management API intact.

To preserve compatibility, legacy methods on `QueueAdminMBean` should be retained until a clear deprecation/migration plan is executed.

## 8. With @ManagedResource, Verify Runtime Metadata

Spring JMX can export MBeans from annotations:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue management"
)
public class AnnotatedQueueAdmin {

    @ManagedAttribute
    public int getPendingCount() {
        return 10;
    }

    @ManagedOperation
    public void retryFailed(int maxCount) {
        // ...
    }
}
```

Enable the annotation-driven exporter:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {}
```

However, annotations in source code alone do not prove the actual JMX contract remains intact:

- The exporter might not be enabled in a given profile.
- The bean might not be scanned into the context.
- A Spring AOP proxy might alter the method surface.
- A different metadata assembler or naming strategy might be configured.
- Another exporter might register the same ObjectName.

Therefore, contract tests must read `MBeanInfo` from `MBeanServer` after the Spring context initializes.

## 9. Contract Testing with MBeanInfo

`MBeanServer.getMBeanInfo(ObjectName)` returns the registered metadata.

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "Expected MBean missing: " + name.getCanonicalName()
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "attribute %s %s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(
        "operation " + operation.getName()
    );
    for (var param : operation.getSignature()) {
        System.out.println(
            "  param type=" + param.getType()
        );
    }
}
```

Key pieces of information:

- `MBeanAttributeInfo`: name, type, readable/writable, `isIs`.
- `MBeanOperationInfo`: name, return type, signature, impact.
- `MBeanParameterInfo`: type and parameter metadata.
- `MBeanNotificationInfo`: notification types.
- For OpenMBeans, `OpenType` and the corresponding schema can also be checked.

Do not rely solely on `MBeanInfo.getClassName()` to verify the contract: a Spring `ModelMBean` or proxy may expose class metadata different from the business class.

## 10. Writing an Intentional Contract Baseline

A baseline for version v1 might look like:

```yaml
objectName: "com.example.orders:type=Queue,name=Payment"
attributes:
  PendingCount:
    type: int
    readable: true
    writable: false
  Paused:
    type: boolean
    readable: true
    writable: true
operations:
  - name: retryFailed
    returnType: void
    parameters:
      - int
notifications:
  - "com.example.orders.queue.overloaded"
```

The baseline must reflect **the published API and what clients rely on**, not just metadata from the newest build. Simply exporting current metadata and comparing it to itself always passes and catches no regressions.

You can store the baseline as a versioned fixture in test resources and compare it against runtime metadata. A good practice is building a normalized snapshot specifying which fields constitute the contract, avoiding sensitivity to array ordering or non-critical descriptions.

## 11. JUnit Backward-Compatibility Test Example

A test checking only the essential contract elements:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class QueueJmxContractTest {

    private final MBeanServer server = /* test server */;
    
    @Test
    void keepsV1ManagementContract() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        MBeanAttributeInfo count = Arrays.stream(
                info.getAttributes())
            .filter(a -> a.getName().equals("PendingCount"))
            .findFirst()
            .orElseThrow();

        assertEquals("int", count.getType());
        assertTrue(count.isReadable());
        assertFalse(count.isWritable());

        boolean retryAvailable = Arrays.stream(
                info.getOperations())
            .filter(op -> op.getName().equals("retryFailed"))
            .anyMatch(op ->
                op.getReturnType().equals("void")
                && op.getSignature().length == 1
                && op.getSignature()[0].getType().equals("int")
            );

        assertTrue(retryAvailable);
    }
}
```

In a real project, `server` must be initialized via Spring test configuration or a JMX test fixture where the MBean is registered. The placeholder in the example indicates a dependency to supply, not directly compilable Java source.

A backward-compatibility test typically verifies that **legacy elements remain present** rather than demanding exact equality over the entire `MBeanInfo`, because newer versions may legitimately add new attributes or operations.

## 12. Distinguishing Structural Compatibility from Semantic Compatibility

An operation may keep the exact same signature:

```java
void retryFailed(int maxCount);
```

yet if `maxCount` previously capped the number of retried items and after an upgrade is interpreted as the number of batches, existing clients could trigger heavy load even though metadata did not change.

Similarly:

- `getPendingCount()` previously counted every job in the queue, while the new version counts only ready jobs.
- `setPaused(true)` previously paused only local intake, while the new version pauses the entire cluster.
- `resetStatistics()` previously reset only counters, while the new version deletes historical data.
- `getTimeoutMillis()` previously returned milliseconds, while the new version returns seconds while still having type `long`.

Therefore, critical operations also need **behavioral tests** and documentation of semantics, units, scope of impact, side effects, and error handling.

Contract tests checking only names and types are necessary but not sufficient.

## 13. Do Not Break Old APIs Just for Prettier Names

Suppose v1 has:

```java
@ManagedAttribute
public int getPendingCount() { ... }
```

In v2 you want a clearer name:

```java
@ManagedAttribute
public int getQueuedOrderCount() { ... }
```

If replaced directly, `PendingCount` disappears. Existing clients may fail.

You can keep an alias during the transition period:

```java
@ManagedAttribute(
    description = "Deprecated: use QueuedOrderCount"
)
public int getPendingCount() {
    return getQueuedOrderCount();
}

@ManagedAttribute(
    description = "Queued orders waiting for processing"
)
public int getQueuedOrderCount() {
    return service.queuedOrderCount();
}
```

This lets old clients keep calling `PendingCount` while new clients move to `QueuedOrderCount`.

**Note:** Both getters call the same service method to avoid returning two differing calculations. Clearly state the deprecation timeline and remove the alias only in an announced breaking release.

## 14. Preserving Old Operation Signatures

Suppose v1:

```java
void retryFailed(int maxCount);
```

v2 wants to add `boolean dryRun`:

```java
void retryFailed(int maxCount, boolean dryRun);
```

If only the new version is kept, old clients calling:

```java
connection.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);
```

will not find the old signature.

One transition approach is keeping the old overload:

```java
@ManagedOperation(
    description = "Deprecated: retries without dry-run"
)
public void retryFailed(int maxCount) {
    retryFailed(maxCount, false);
}

@ManagedOperation(
    description = "Retries with optional dry-run"
)
public void retryFailed(int maxCount, boolean dryRun) {
    service.retryFailed(maxCount, dryRun);
}
```

This can support both old and new clients if the assembler/exporter exposes both overloads properly. With JMX, clients must send the exact operation signature; test both `"int"` and `"int","boolean"`.

If a framework/assembler does not handle overloads as desired, consider a differently named method such as `retryFailedPreview` or a clearer management adapter. Do not assume method name alone suffices to distinguish overloads.

## 15. When Should ObjectName Be Versioned?

Some changes cannot preserve both contracts on a single MBean:

- A mandatory attribute type changes incompatibly.
- An Open Data schema undergoes deep structural changes.
- Operation semantics change fundamentally.
- Two generations of clients/agents cannot share the same API.

Two management endpoints can be published on the same server:

```text
com.example.orders:type=Queue,name=Payment,api=v1
com.example.orders:type=Queue,name=Payment,api=v2
```

Or use a versioned domain:

```text
com.example.orders.management.v1:type=Queue,name=Payment
com.example.orders.management.v2:type=Queue,name=Payment
```

Use this only when strong compatibility requirements justify it. JMX inherently requires every ObjectName in the same `MBeanServer` to be unique.

An appropriate design may use two adapters:

```text
Business Service
     |
     +-- QueueAdminV1 (old contract)
     |        -> ObjectName api=v1
     |
     +-- QueueAdminV2 (new contract)
              -> ObjectName api=v2
```

Both adapters can delegate to the same service while preserving two client contracts. Clearly manage the lifecycle and eventual removal of v1.

## 16. Rolling Upgrades Across Multiple Instances

In a cluster or multi-JVM deployment, different versions may run simultaneously:

```text
Instance A: application version 1.9
Instance B: application version 2.0
Instance C: application version 2.0
```

Having the same ObjectName in each JVM does not mean all MBeans share the same contract. Collectors/agents may have to talk to both old and new versions during a rolling upgrade.

Guidelines:

1. Keep the old API working in the new release until most clients have upgraded.
2. Do not require all monitoring agents to upgrade simultaneously with the server.
3. Provide a capability or management API version attribute if the system needs to differentiate them.
4. Clients can inspect `MBeanInfo` and then select available operations.
5. Do not invoke new operations on older instances if metadata does not advertise them.
6. Read state/units consistently before aggregating metrics across versions.

A reference attribute:

```java
@ManagedAttribute(
    description = "Version of the public JMX management contract"
)
public String getManagementApiVersion() {
    return "2.0";
}
```

This version describes the **management contract**, which does not necessarily match the application version or Spring Framework version.

## 17. Spring AOP and Compatibility

When `@Transactional`, method security, or other advisors are enabled, Spring may create a JDK dynamic proxy or a class-based proxy.

If the exporter receives the proxy instead of the target, the method list and JMX annotation discovery may change:

- JDK proxies expose only methods on the interfaces they implement.
- Class-based proxies include more methods from the target but have limitations with `final`/`private` methods.
- Naming strategies based on runtime class names can become unstable.
- Exporting the raw target directly to avoid proxies can cause JMX invocations to bypass transactional or security advice.

To protect the contract, use a dedicated management adapter:

```text
Stable JMX / ObjectName
     |
     v
ManagementAdapter
     |
     v
BusinessService interface / Spring proxy
     |
     v
Business implementation
```

The adapter allows the Java business service class or proxy to change without altering public attribute/operation names. Still, integration-test invocations through the proxy to ensure advice executes properly.

## 18. Upgrading Spring Framework and Metadata Assemblers

The same Java class can be exported through several mechanisms:

- Standard MBean/MXBean.
- `MBeanExporter` with explicit `beans` mapping.
- `MetadataMBeanInfoAssembler` with an annotation source.
- `InterfaceBasedMBeanInfoAssembler`.
- `MethodNameBasedMBeanInfoAssembler`.
- Auto-detection via `@EnableMBeanExport`.

When changing export mechanisms or upgrading Spring, metadata discovery, naming strategies, or proxy handling may behave differently. Before changing dependencies, identify which mechanism is used and maintain contract tests against the **runtime artifact**.

Do not conclude "the new Spring version is incompatible" just because a source-annotation unit test passes while JConsole lacks the MBean. Check exporter configuration, target server, ObjectName, proxy type, and `MBeanInfo`.

## 19. Remote Clients and Serialization Compatibility

Remote JMX adds the requirement that data types match the client's JVM/classpath and connector serialization rules.

An operation:

```java
InternalJobDetails getJobDetails(String id);
```

may work locally yet fail remotely if the client lacks the `InternalJobDetails` class, its schema changed, or its `serialVersionUID` differs.

For smoother compatibility:

- Prefer primitives, wrappers, `String`, `ObjectName`, and appropriate Open MBean types.
- For structured data, consider MXBean/Open Data (`CompositeData`, `TabularData`).
- Avoid returning domain entities or internal object graphs directly over management APIs.
- Manage schema, field names, and units as part of the contract.
- When changing a data schema, consider optional fields with sensible defaults or a new API version.
- Test client compatibility from supported JVM/agent versions, not only in-process server calls.

An `MBeanInfo` showing `java.lang.Object` or a DTO type does not guarantee a remote client can deserialize the actual object.

## 20. Notification Changes Are Also Contract Changes

Suppose an MBean emits:

```text
com.example.orders.queue.overloaded
```

A listener uses `NotificationFilterSupport`:

```java
filter.enableType(
    "com.example.orders.queue.overloaded"
);
```

If a new version changes the type to:

```text
com.example.orders.queue.backlog.high
```

the old listener no longer matches.

During a transition period, you can emit both types or provide a suitable migration path, but account for **duplicate notifications** causing clients to process an event twice.

Beyond type names, preserve the semantics of `source`, `sequenceNumber`, `message`, `userData`, and `getNotificationInfo()` metadata. If clients rely on a `userData` schema, changing fields can also be breaking.

JMX notifications are not durable message delivery; do not rely on them as a migration mechanism that guarantees full event delivery.

## 21. Deprecation Lifecycle

A low-disruption upgrade workflow:

```text
Version N:
  Publish contract v1

Version N+1:
  Add v2 API / alias
  Keep v1
  Mark deprecated in descriptions and docs

Migration window:
  Update dashboards, automation, runbooks
  Measure clients still calling v1 (if telemetry is available)

Version N+K:
  Remove v1 only in an announced breaking release
```

JMX has no universal mechanism ensuring every client reads or honors deprecation descriptions. Therefore:

- Provide API documentation and a migration guide.
- Maintain an adequate support window.
- Inventory affected clients and agents.
- Keep tests verifying v1 continues working during the migration window.
- Remove the legacy API only after a formal decision.

Do not alter the semantics of an old operation without changing its version merely because the source signature looks identical.

## 22. Three-Layer Compatibility Testing

### Layer A: Metadata Contract Test

Initialize the Spring context and read `MBeanInfo` from the server. Verify that required attributes, operations, and notifications still exist with expected names, types, and flags.

### Layer B: Invocation Contract Test

Invoke legacy operations using **exact JMX signatures** and verify results and side effects:

```java
connection.invoke(
    name,
    "retryFailed",
    new Object[] { 5 },
    new String[] { "int" }
);
```

Test `getAttribute`, `setAttribute` (if supported), invalid input errors, and return types as well.

### Layer C: Remote Client Compatibility Test

From an older supported JMX client version, connect to the newer server and execute key operations. This catches classloading, serialization, and connector issues missed by local tests.

A balanced suite covering all three layers protects far better than merely checking for annotations on a class.

## 23. Comparing Metadata as Sets Rather Than by Order

When writing contract tests, do not rely on the array ordering of `getAttributes()` or `getOperations()`, because ordering is not what JMX clients depend on when invoking by name.

Helper example:

```java
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

static boolean hasOperation(
        MBeanInfo info,
        String name,
        String returnType,
        String... paramTypes) {

    return Arrays.stream(info.getOperations()).anyMatch(op ->
        op.getName().equals(name)
        && op.getReturnType().equals(returnType)
        && Arrays.equals(
            Arrays.stream(op.getSignature())
                .map(p -> p.getType())
                .toArray(String[]::new),
            paramTypes
        )
    );
}
```

With that helper:

```java
assertTrue(
    hasOperation(info, "retryFailed", "void", "int")
);
```

What matters is keeping the **operation signature** intact, not its position in the list.

## 24. Pre-Release Checklist for an Upgrade

| Question | Must Verify |
| --- | --- |
| Did `ObjectName` change? | Compare canonical names |
| Do old attributes still exist? | Names, types, readable/writable |
| Do old operations still exist? | Names, signatures, return types |
| Did semantics change? | Units, side effects, scope of impact |
| Did notifications change? | Types, `userData` schema, filters |
| Did proxy/AOP setup change? | Metadata and invocation remain correct |
| Did exporter/assembler change? | Runtime integration tests |
| Can older clients connect? | Remote compatibility test |
| Is there an alias/deprecation window? | Migration plan |
| Does rolling upgrade support both versions? | Client capability checks |
| Did security change? | Permissions and endpoint access |
| Could startup fail due to duplicate ObjectName? | Registration policy/ownership |

## 25. Hands-on Exercises

1. Create `QueueAdminMBean` v1 with `PendingCount` and `retryFailed(int)`. Export it via Spring `MBeanExporter` and save a baseline `MBeanInfo`.
2. Add `ActiveWorkers` in v2, run the v1 contract test, and explain why this change is usually compatible.
3. Rename `PendingCount` to `QueueDepth` without an alias; observe the v1 test failing.
4. Restore the old getter as an alias, add a deprecation description, and test both attributes.
5. Change `retryFailed(int)` to `retryFailed(long)`, invoke it with signature `"int"`, and analyze the failure.
6. Retain the `retryFailed(int)` overload, add a new operation, and verify `MBeanInfo` contains both signatures.
7. Create two adapters v1/v2 with two ObjectNames having keys `api=v1` and `api=v2`.
8. Enable Spring AOP proxies in the new version, and verify ObjectName and metadata remain unchanged.
9. Create a remote client test and verify the return type can be deserialized.
10. Write a migration checklist for a dashboard currently using `PendingCount` before deprecating the old attribute.

## 26. Self-Check Questions

- Why does a management API still need backward compatibility even though it is not a REST endpoint?
- When renaming an attribute while keeping a different Java method, can JMX clients break?
- Why is key property order in an `ObjectName` not a breaking change?
- How does changing a parameter type from `int` to `long` affect `MBeanServer.invoke`?
- Is adding a new operation always guaranteed not to affect old clients?
- Why must contract tests obtain `MBeanInfo` at runtime?
- When should an alias be used instead of renaming directly?
- When should a versioned `ObjectName` be created?
- Why can changing Spring AOP proxy mode affect the JMX contract?
- Do local tests fully verify remote serialization compatibility?

**Key Takeaway:** A management interface is an **operational API with real clients**. When upgrading Spring or your application, keep `ObjectName`, attributes, operations, signatures, notifications, and semantics stable. For incompatible changes, use aliases, deprecation windows, or versioned MBeans, and protect them with metadata contract tests, invocation tests, and remote client compatibility tests.
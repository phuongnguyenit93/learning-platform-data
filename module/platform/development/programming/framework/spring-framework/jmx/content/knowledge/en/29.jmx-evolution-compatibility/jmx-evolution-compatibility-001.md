# Adding New Attributes Without Breaking Existing Clients in Spring Framework JMX

## 1. Context and Goal

In Java Management Extensions (**JMX**), an MBean provides a **management contract** consisting of attributes, operations, and notifications. Clients may be JConsole, VisualVM, a Java script, a monitoring system, or a Spring application using `MBeanProxyFactoryBean`.

As an application evolves, we often want to add a new attribute: failed job count, last refresh timestamp, backlog status, or runtime configuration. This seemingly small change can still cause existing clients to fail if it also changes the `ObjectName`, data type, access permissions, or how existing attributes are exposed.

**Goal:** add new observability while preserving valid behavior for existing clients. The preferred approach is **compatible contract extension (additive evolution)**, followed by verification from a real client perspective.

This lesson belongs to the **Evolution and Compatibility** group in Spring Framework JMX, focusing on:

- The concept of compatibility for MBean metadata.
- Rules for safely adding attributes.
- Standard MBean and Spring annotation exporter examples.
- How typed clients, dynamic clients, and monitoring scripts react.
- Versioning, rollout, and rollback mechanisms.
- Testing `MBeanInfo` to detect contract-breaking changes.

## 2. What Does a JMX Contract Include?

Suppose an application exports an MBean:

~~~text
ObjectName:
  com.example.orders:type=Queue,name=payments

Attributes:
  PendingCount : long [read-only]
  Enabled      : boolean [read/write]

Operations:
  pause()      : void
  resume()     : void
~~~

A client can invoke:

~~~java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

Long pendingCount = (Long) connection.getAttribute(
    name, "PendingCount"
);
~~~

Or use a typed interface:

~~~java
public interface QueueAdminClient {
    long getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void pause();
    void resume();
}
~~~

Elements that can be part of the contract:

| Component | Meaning to the client |
| --- | --- |
| `ObjectName` | Locating the right MBean |
| Attribute name | Calling `getAttribute`, `setAttribute` |
| Java/JMX type | Casting, deserializing, and displaying |
| `isReadable()` | Whether read access exists per metadata |
| `isWritable()` | Whether write access exists per metadata |
| Operation name/signature | Calling `invoke` |
| Notification types | Filtering and handling events |
| Semantics | What the value and unit mean |
| Lifecycle | Whether the MBean still exists, whether it is replaced |

Not all changes are equally breaking. Adding a read-only attribute is usually less risky than changing the type of an existing attribute. However, **compatibility is not just whether Java code still compiles**: dashboards, collectors, and scripts may rely on names, units, or how metadata is read.

## 3. Golden Rule: Add New, Do Not Change the Old

Example before the new version:

~~~text
PendingCount : long [read-only]
Enabled      : boolean [read/write]
~~~

After adding:

~~~text
PendingCount    : long [read-only]
Enabled         : boolean [read/write]
LastRefreshTime : String [read-only]  <-- new
~~~

This is a compatible extension if:

1. `ObjectName` remains unchanged.
2. `PendingCount` remains `long`, readable, and preserves its semantics.
3. `Enabled` remains `boolean`, and both read and write work.
4. Existing operations remain exposed.
5. Existing clients are not forced to know about `LastRefreshTime`.
6. The new attribute causes no side effects that unintentionally alter existing state.

Most clients that read an attribute by name will not be affected if the MBean adds another attribute. However, clients that iterate over `MBeanInfo` themselves might wrongly assume that the attribute list is fixed, and therefore need to be tested.

### Change and Risk Matrix

| Change | Typical assessment | Notes |
| --- | --- | --- |
| Add a read-only attribute of simple type | Usually compatible | Dynamic clients might iterate assuming a fixed list |
| Add a read/write attribute | Potentially compatible | Increases control surface and requires authorization |
| Change `int` to `long` | Risk of breaking | Client casts or old proxy types |
| Rename `PendingCount` to `QueueDepth` | Breaking for old clients | Need to keep an alias or migration |
| Remove an old getter | Breaking | `AttributeNotFoundException` |
| Change read/write to read-only | Breaking for writing clients | `setAttribute` is rejected |
| Change meaning from “pending” to “total” | Semantically breaking | May not raise technical errors |
| Change ObjectName/domain | Breaking | Client cannot find the MBean |
| Add an operation | Usually additive | Control permissions and side effects |
| Change an existing operation signature | Risk of breaking | Typed clients and `invoke` mismatch |

## 4. Standard MBean Example: Adding a New Getter

### Initial Version

Management interface:

~~~java
package com.example.orders.management;

public interface PaymentQueueAdminMBean {
    long getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
~~~

Implementation:

~~~java
package com.example.orders.management;

public class PaymentQueueAdmin implements PaymentQueueAdminMBean {
    private volatile long pendingCount;
    private volatile boolean enabled = true;

    @Override
    public long getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

JMX Standard MBean introspection typically maps:

~~~text
getPendingCount()     -> PendingCount
isEnabled()           -> Enabled (readable)
setEnabled(boolean)   -> Enabled (writable)
~~~

### Extended Version

Add the getter to the **MBean interface** and implementation:

~~~java
public interface PaymentQueueAdminMBean {
    long getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);

    // New additive attribute.
    String getLastRefreshTime();
}
~~~

~~~java
import java.time.Instant;

public class PaymentQueueAdmin implements PaymentQueueAdminMBean {
    private volatile long pendingCount;
    private volatile boolean enabled = true;
    private volatile Instant lastRefreshTime = Instant.EPOCH;

    @Override
    public long getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public String getLastRefreshTime() {
        return lastRefreshTime.toString();
    }
}
~~~

In this example, `LastRefreshTime` is exposed as `java.lang.String`. Choosing an ISO-8601 String makes it easier for basic JMX clients to read compared to passing an `Instant` object directly, depending on the client's serialization/mapping capabilities.

**Key takeaway:** With a Standard MBean, adding a method only to the implementation without adding it to the `PaymentQueueAdminMBean` interface does not guarantee the method is exposed as an attribute. The MBean interface is the contract source of a Standard MBean.

## 5. Spring @ManagedAttribute Example: Extending a POJO

With Spring `AnnotationMBeanExporter`, you can annotate a getter:

~~~java
package com.example.orders.management;

import java.time.Instant;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=payments",
    description = "Payment queue management"
)
public class PaymentQueueManagement {

    private volatile long pendingCount;
    private volatile boolean enabled = true;
    private volatile Instant lastRefreshTime = Instant.EPOCH;

    @ManagedAttribute(description = "Queued payment jobs")
    public long getPendingCount() {
        return pendingCount;
    }

    @ManagedAttribute(description = "Whether queue processing is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    // New attribute: read-only.
    @ManagedAttribute(
        description = "Last successful cache/configuration refresh in ISO-8601 UTC"
    )
    public String getLastRefreshTime() {
        return lastRefreshTime.toString();
    }
}
~~~

When the Spring exporter reads metadata, the selected getters/setters can become JMX attributes. Verify the actual `MBeanInfo` instead of inferring solely from annotations.

### Why Not Add a Setter If Not Needed Yet?

~~~java
@ManagedAttribute
public void setLastRefreshTime(String value) {
    ...
}
~~~

If you allow clients to modify `LastRefreshTime`, you are opening up additional state-control capability. For an actual system timestamp, this is normally **observability data**, not configuration that should be changed via JMX. Therefore, exposing only the getter reduces operational risk.

### Check the Existing Exporter

In Spring Boot or a Spring application that already has JMX configuration, avoid creating a second `AnnotationMBeanExporter` just to add a getter. A duplicate exporter can cause `InstanceAlreadyExistsException` or unintentionally replace MBeans depending on the registration policy.

## 6. Do Not Change ObjectName When Only Adding an Attribute

If an MBean was previously named:

~~~text
com.example.orders:type=Queue,name=payments
~~~

then adding `LastRefreshTime` does not necessarily require changing it to:

~~~text
com.example.orders:type=Queue,name=paymentsV2
~~~

Changing the ObjectName will force old clients to update, even though the old API part remains intact.

When making only additive changes, it is usually best to keep the name stable. You can use metadata versioning to let clients know about new capabilities, but avoid changing the registry name unless truly necessary.

### When Is a Versioned ObjectName Useful?

If an **incompatible** contract change is needed, for example:

~~~text
com.example.orders:type=QueueAdmin,version=v1,name=payments
com.example.orders:type=QueueAdmin,version=v2,name=payments
~~~

Old clients can continue using v1 during the transition period, while new clients use v2. However, exposing two interfaces that control the same resource simultaneously requires clear concurrency and ownership to avoid duplicate or inconsistent operations.

## 7. Names, Types, and Semantics Must Remain Stable

An attribute consists of more elements than just a getter.

### 7.1. Name

If it was previously `PendingCount`, do not rename it to `PendingJobs` without a migration plan.

### 7.2. Type

If it was previously `long`, keep `long` when possible. A typed client might write:

~~~java
long pending = queueAdmin.getPendingCount();
~~~

and a dynamic client might cast:

~~~java
Long pending = (Long) connection.getAttribute(name, "PendingCount");
~~~

If the MBean changes to `int`, dynamic clients may hit `ClassCastException` and typed proxies may become incompatible.

### 7.3. Read/Write Flags

If an existing attribute is writable, switching it to read-only is breaking for clients calling the setter. Conversely, adding a setter to a previously read-only attribute can be an expansion of capability, though it also increases security risk.

### 7.4. Semantics and Units

If `AverageLatency` was previously in milliseconds, do not silently change it to seconds while keeping the same name/type. Clients will still run, but alert thresholds will be wrong.

A new attribute should clearly document:

- Units.
- Measurement scope.
- Update timing.
- Value when no data is available yet.
- Reset rules.
- Meaning in a multi-replica environment.

For example, `LastRefreshTime` is the timestamp of the **most recent successful refresh**, not when the refresh started.

## 8. New Data Types and Client Compatibility

A new attribute can use simple Java types:

~~~text
boolean, int, long, double, String
~~~

These types are generally easy for generic JMX clients to consume. For complex types, consider:

- Serializability over remote connections.
- Classpath on both sides.
- MXBean Open Types.
- `CompositeData` or `TabularData`.
- How JConsole/VisualVM renders them.
- Conversion capabilities of the framework exporter.

For example, avoid forcing every client to have a custom `CacheSnapshot` class on its classpath just to read a metric.

Instead of:

~~~java
public CacheSnapshot getSnapshot() { ... }
~~~

you can prefer simple attributes:

~~~java
public long getHitCount() { ... }
public long getMissCount() { ... }
public String getLastRefreshTime() { ... }
~~~

If structured data is needed, design an MXBean or Open Types with a clear contract. That is a separate API decision, not just a matter of adding a getter.

## 9. Do Typed Clients Need Updating?

Suppose a Spring client has an interface:

~~~java
public interface QueueAdminClient {
    long getPendingCount();
    boolean isEnabled();
}
~~~

After the server adds `LastRefreshTime`, old clients can continue calling the two old methods as long as the corresponding contract remains intact. It is not mandatory to modify old client interfaces just because the server added an attribute.

New clients can extend it:

~~~java
public interface QueueAdminClientV2 {
    long getPendingCount();
    boolean isEnabled();
    String getLastRefreshTime();
}
~~~

With `MBeanProxyFactoryBean`, the interface is configured as the proxy contract. The new server must expose the corresponding attribute, while the Java compiler only knows about the client-side interface.

### Mixed Versions

In a rolling update deployment, there may be:

~~~text
node-a: server v2 -> has LastRefreshTime
node-b: server v1 -> no LastRefreshTime
node-c: server v2 -> has LastRefreshTime
~~~

If a new client accesses node-b and calls the new getter, it will encounter an error. Therefore, you need a rollout plan or capability detection rather than assuming all replicas upgrade simultaneously.

## 10. Dynamic Clients Should Detect Capabilities

A client using `MBeanServerConnection` can check for an attribute before reading it:

~~~java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public static boolean hasReadableAttribute(
        MBeanServerConnection connection,
        ObjectName name,
        String attributeName
) throws Exception {
    MBeanInfo info = connection.getMBeanInfo(name);

    for (MBeanAttributeInfo attribute : info.getAttributes()) {
        if (attributeName.equals(attribute.getName())
                && attribute.isReadable()) {
            return true;
        }
    }
    return false;
}
~~~

Usage:

~~~java
if (hasReadableAttribute(connection, name, "LastRefreshTime")) {
    String value = (String) connection.getAttribute(
        name, "LastRefreshTime"
    );
    System.out.println(value);
} else {
    System.out.println("LastRefreshTime not supported");
}
~~~

This mechanism is useful when a new client must remain compatible with an old server during a rolling deployment.

**Timing note:** a race condition can occur: the client reads metadata at T1, the MBean is replaced at T2, and then `getAttribute` at T3 fails. Capability detection should be paired with proper runtime exception handling rather than treating metadata as permanent proof.

## 11. Testing Compatibility via MBeanInfo

`MBeanInfo` provides a description of the actual MBean interface.

Example helper to retrieve metadata:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

public static Map<String, MBeanAttributeInfo> attributes(
        MBeanInfo info
) {
    return Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            value -> value
        ));
}
~~~

When comparing two versions, what matters is not that the attribute lists are identical, but that **every old attribute remains compatible**.

A conceptual assertion:

~~~java
Map<String, MBeanAttributeInfo> oldAttributes =
    attributes(oldInfo);

Map<String, MBeanAttributeInfo> newAttributes =
    attributes(newInfo);

for (var entry : oldAttributes.entrySet()) {
    String name = entry.getKey();
    MBeanAttributeInfo oldAttr = entry.getValue();
    MBeanAttributeInfo newAttr = newAttributes.get(name);

    if (newAttr == null) {
        throw new AssertionError("Removed attribute: " + name);
    }
    if (!oldAttr.getType().equals(newAttr.getType())) {
        throw new AssertionError("Changed type: " + name);
    }
    if (oldAttr.isReadable() && !newAttr.isReadable()) {
        throw new AssertionError("Lost read access: " + name);
    }
    if (oldAttr.isWritable() && !newAttr.isWritable()) {
        throw new AssertionError("Lost write access: " + name);
    }
}
~~~

This snippet uses `var`, so it requires Java 10+. If the project uses Java 8, replace `var` with `Map.Entry<String, MBeanAttributeInfo>`.

The test above allows adding new attributes and detects several changes that break the old contract. It does not yet check semantics, security, or operations; critical contracts require additional checks.

## 12. Integration Testing with a Dedicated MBeanServer

To avoid affecting platform MBeans or other tests, you can use:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server = MBeanServerFactory.newMBeanServer();
~~~

Example test flow:

1. Create a test Spring context.
2. Register the custom bean and exporter into the test MBeanServer.
3. Verify the ObjectName exists.
4. Read `MBeanInfo`.
5. Assert old attributes still have the expected names/types/read-write flags.
6. Assert the new `LastRefreshTime` exists and is readable.
7. Call `getAttribute` on both old and new attributes.
8. Close the Spring context.
9. Verify MBeans managed by the exporter have been unregistered.

### Example Assertion for the New Attribute

~~~java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=payments"
);

MBeanInfo info = server.getMBeanInfo(name);

boolean found = false;

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    if ("LastRefreshTime".equals(attribute.getName())) {
        found = "java.lang.String".equals(attribute.getType())
            && attribute.isReadable()
            && !attribute.isWritable();
    }
}

assertTrue(found, "Expected read-only LastRefreshTime");
~~~

`server` and `assertTrue` are components already initialized/imported in the test fixture; the snippet only illustrates the assertion.

## 13. Compatibility Is Not Only in Metadata

A new attribute can allow the server to keep exposing all old attributes while still changing runtime behavior.

Example new getter:

~~~java
@ManagedAttribute
public String getRecentErrors() {
    return database.loadAllErrorsAsText();
}
~~~

It can cause problems:

- Frequent polling by JConsole or collectors increases database load.
- The getter may block for a long time or throw exceptions from downstream.
- Large text payloads create network overhead.
- Queries may hold locks or affect business latency.
- The getter may accidentally expose sensitive data.

Therefore, an “additive” change still needs attention to **performance, security, and observability cost**.

### New Getters Should Be Lightweight and Side-Effect Free

Prefer:

~~~java
@ManagedAttribute
public long getRecentErrorCount() {
    return errorCounter.get();
}
~~~

If a complex snapshot is needed, use caching, bound the returned data, or design a dedicated operation/endpoint.

**Do not treat metadata compatibility as a guarantee of performance compatibility.**

## 14. Do Not Create an Attribute by Renaming an Old Method

For example, if you want to add `QueueDepth`, do not replace:

~~~java
public long getPendingCount()
~~~

with:

~~~java
public long getQueueDepth()
~~~

and delete the old getter. In JMX introspection, that removes `PendingCount` and adds `QueueDepth`. Old clients using `PendingCount` will fail.

If both names need to coexist temporarily, you can do:

~~~java
@ManagedAttribute
public long getPendingCount() {
    return queueService.pendingCount();
}

@ManagedAttribute
public long getQueueDepth() {
    return queueService.pendingCount();
}
~~~

`queueService` is an illustrative dependency. Having both getters read from the same data source keeps them consistent, but you must document that the two attributes are aliases; avoid creating two independent counters that could drift apart.

When planning to remove the old alias, you need a concrete migration plan for consumers and an appropriate deprecation period.

## 15. Adding a Writable Attribute: Evaluating Access Control

A new attribute with a setter:

~~~java
@ManagedAttribute
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute
public void setMaxWorkers(int maxWorkers) {
    if (maxWorkers < 1 || maxWorkers > 64) {
        throw new IllegalArgumentException("Invalid maxWorkers");
    }
    this.maxWorkers = maxWorkers;
}
~~~

is more than just expanding observability data: it creates **runtime configuration modification capability**.

You need to review:

- Which clients have JMX write permissions?
- Does the remote JMX connector have authentication, TLS, and authorization?
- Are values thoroughly validated?
- Does the setter apply the change to the actual resource?
- Is the change thread-safe and consistent?
- Is auditing needed?
- Should it be restricted in production environments?
- Should exposure be avoided if there is no real administrative need yet?

**Do not automatically grant broad write permissions just because a new attribute needs testing.** Maintain a test environment and admin accounts with appropriate permissions.

## 16. Compatibility with Dashboards and Monitoring Collectors

A dashboard might read by:

~~~text
ObjectName: com.example.orders:type=Queue,name=payments
Attribute:  PendingCount
Type:       long
~~~

After adding `LastRefreshTime`:

- Collectors reading `PendingCount` by name will usually continue working.
- Collectors that discover all attributes may emit additional metrics or new logs.
- If a collector encounters a new unsupported type, it may report errors while enumerating.
- If a dashboard expects a fixed number of attributes, it must be tested.
- With multiple replicas, collectors may encounter different v1 and v2 servers during a rolling update.

### Preserving Contracts with a Golden Snapshot

You can store a normalized MBeanInfo contract as a baseline in the test repository, including:

~~~text
ObjectName
Attribute name
Attribute type
Readable/writable flags
Operation name/signature
Notification types (if relevant)
~~~

When upgrading, tests only require existing elements to remain compatible, without forcing new metadata to be identical. Avoid comparing descriptions or attribute order if they are not truly part of the client contract; they can change across versions or assemblers.

## 17. Safe Rollout Plan

A deployment strategy:

### Phase A — add the attribute on the server

Deploy the new MBean version while keeping the entire old API intact. Do not require new clients to use the new attribute yet.

### Phase B — verify the registry

Use JConsole, `MBeanInfo`, or integration tests to confirm across several JVMs:

~~~text
PendingCount    present
Enabled         present
LastRefreshTime present
~~~

### Phase C — update monitoring/clients

New clients can read the new attribute if capability is detected or after the server fleet has been upgraded.

### Phase D — monitor mixed versions

During a rolling update, some nodes do not yet have the new attribute. Avoid treating the missing attribute as an incident while still within the announced migration window.

### Phase E — stabilize the contract

Once the entire fleet supports it, you can begin requiring the new attribute in contract tests for the corresponding version.

If there is a plan to remove the old attribute, that is a separate breaking change requiring its own migration rather than bundling it into the “add new” release.

## 18. Rollback Must Be Planned in Advance

If a v2 client strictly requires calling `LastRefreshTime`, but the server rolls back to v1 without this attribute, the v2 client may fail.

Therefore, a rollback strategy needs:

- New clients supporting feature detection and fallback.
- Or keeping server v2 running until clients no longer need the new attribute.
- Or deploying in order: server first, client second; rolling back client first, server second.
- Monitoring to detect `AttributeNotFoundException` and typed proxy errors.
- Never changing ObjectName as a “quick fix” for compatibility issues.

Rollback readiness is part of designing an additive change, not just a deployment pipeline concern.

## 19. Replacing an MBean Can Lose Listeners

If an upgrade uses `RegistrationPolicy.REPLACE_EXISTING` in the same MBeanServer, a new MBean can replace the old MBean under the same ObjectName.

Consequences:

- Clients may experience a window where the ObjectName is unregistered.
- Typed proxies can call the new MBean if the contract remains compatible.
- Notification subscriptions on the old emitter do not automatically transfer to the new emitter.
- State inside the old adapter may be lost.
- In-flight operations on the old object do not stop automatically.

Therefore, when only adding an attribute, **avoid unnecessary runtime replacement** if normal deployment/lifecycle processes can be used. If replacement is unavoidable, plan for re-subscription, state, and ownership.

## 20. Adding an Attribute Related to Versioning

Sometimes clients need to know the management API version:

~~~java
@ManagedAttribute(
    description = "Management interface schema version"
)
public String getManagementSchemaVersion() {
    return "2";
}
~~~

An attribute like this helps with diagnostics. However, if old clients do not know about the version attribute, do not require them to read the version to continue using existing attributes.

You can use version as a supplementary signal, but **capability detection via MBeanInfo** is usually more reliable when a client needs to decide whether to read a specific attribute.

Moreover, simply incrementing a version string does not automatically make an API compatible: you still must preserve the names, types, and permissions of existing attributes.

## 21. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Old client gets `AttributeNotFoundException` | Old attribute renamed/removed | Keep old getter or alias |
| Old client gets `ClassCastException` | Attribute type changed | Maintain the old type |
| Typed proxy fails at runtime | Server missing method/getter required by interface | Compare `MBeanInfo` and interface |
| JConsole sees new attribute but script cannot read it | JMX name differs from what client calls | Use exact ObjectName/attribute name |
| New client fails on some nodes | Rolling update still has v1 servers | Capability detection/rollout order |
| Dashboard shows wrong metric | Semantics or unit changed | Document clearly and use a distinct new name |
| Slowdown after release | New getter is resource-intensive | Snapshot/cache and reasonable polling |
| Sensitive data leaked | New attribute contains data that should not be exposed | Scoping/security/redaction |
| ObjectName conflict | Duplicate exporter created during upgrade | Ownership and auto-config |
| Notifications stop after deploy | MBean replaced/unregistered | Re-subscribe and lifecycle handling |
| New setter called unintentionally | Overly broad readwrite permissions | Least privilege and validation |
| New attribute wrong type remotely | Complex type hard to deserialize | String/Open Types/MXBean |

## 22. Pre-Release Checklist

1. Is the **ObjectName** preserved?
2. Do all old attributes still exist?
3. Are the types of old attributes preserved?
4. Are readable/writable flags still compatible?
5. Do old operations/notifications still serve required clients?
6. Does the new attribute have a clear name, type, and semantics?
7. How are default values or missing data represented?
8. Is the new getter lightweight, bounded, and side-effect free?
9. If writable, have validation and permission restrictions been applied?
10. Do new clients handle servers that do not support the attribute yet?
11. Does the deployment involve rolling updates/mixed versions?
12. Will a rollback cause new clients to fail?
13. Is there an integration test comparing against the baseline MBeanInfo?
14. Has it been verified on the target MBeanServer/target JVM?
15. Is there a JConsole check or verification script for staging?
16. Do listeners need to re-subscribe if the MBean is replaced?
17. Have docs/dashboards been updated for the new attribute?
18. Is there a deprecation mechanism if the old attribute will be removed later?

## 23. Hands-on Exercise

**Goal:** extend a queue MBean from v1 to v2 while keeping a v1 Java client working.

### Part A — create v1

1. Create a Standard MBean or Spring annotation MBean with `PendingCount` and `Enabled`.
2. Register ObjectName `com.example.orders:type=Queue,name=payments`.
3. Write a v1 client that reads `PendingCount` and `Enabled`.
4. Capture the baseline `MBeanInfo` in an integration test.

### Part B — extend to v2

1. Add getter `getLastRefreshTime()` returning an ISO-8601 String.
2. Keep the ObjectName, the two old attributes, and existing operations unchanged.
3. Start the v2 version in a dedicated test MBeanServer.
4. Re-run the v1 client.
5. Compare old and new metadata.
6. Verify `LastRefreshTime` is readable and not writable.

### Part C — test mixed versions

1. Run one v1 target and one v2 target.
2. Write a v2 client that inspects `MBeanInfo` before reading `LastRefreshTime`.
3. For v1, the client uses a fallback instead of treating it as an error.
4. For v2, the client reads the actual value.
5. Simulate a server rollback and observe the client continuing to work.

### Part D — detect a breaking change

1. Intentionally rename `PendingCount` to `PendingJobs`.
2. Re-run the v1 client to observe the failure.
3. Restore the `PendingCount` alias.
4. Update the contract test to catch name changes in future releases.

## 24. Self-Check Questions

**1. Why is adding an attribute usually less breaking than renaming an old attribute?**

Because old clients can keep calling the old name; renaming causes lookups to stop matching.

**2. Is adding a getter to a Standard MBean implementation enough?**

Not necessarily. A Standard MBean publishes its contract via the MBean interface; the method must be added to the corresponding interface.

**3. Does `@ManagedAttribute` automatically register an MBean?**

No. A Spring exporter must be configured/enabled and the bean must reside in the appropriate context.

**4. Should `Instant` be used as the return type for all JMX clients?**

Mapping/serialization must be considered. An ISO-8601 String or Open Types may be more compatible with generic clients.

**5. Why does a new writable attribute require a security review?**

Because it opens up the ability to change runtime state, not just observe it.

**6. Can a new client read a new attribute on an old server?**

No, unless the old server already has that attribute. Clients should check capabilities or perform rollouts in a safe order.

**7. Is `MBeanInfo` sufficient to prove full compatibility?**

No. Metadata only checks structure; semantics, performance, security, and runtime behavior must also be tested.

**8. When should a new ObjectName with a version be used?**

When an incompatible change is required or two management APIs must be maintained in parallel.

## 25. Summary

**Adding a new attribute without breaking existing clients** requires preserving the old JMX contract and extending only the capabilities needed.

Safe approach:

- Keep the ObjectName and existing attributes/operations.
- Keep types, read/write permissions, and semantics of existing data.
- Add a new lightweight getter with a clear description, preferring read-only if used solely for observation.
- For Standard MBeans, update the management interface; for Spring JMX, update the metadata read by the exporter.
- Test with `MBeanInfo` and real clients.
- During rolling updates, new clients must tolerate servers that do not have the attribute yet.
- Prepare for rollback and avoid unnecessary runtime replacement.

A truly additive change means **old clients continue working without modification**, while new clients can use the extended functionality in a controlled manner.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Java SE API — MBeanAttributeInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

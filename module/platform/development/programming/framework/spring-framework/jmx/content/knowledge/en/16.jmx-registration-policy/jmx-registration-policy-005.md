# Trade-offs When Replacing an Active MBean in Spring JMX

## 1. Background: What Does Replacing an MBean Mean?

In Java Management Extensions (**JMX**), an MBean is registered with an **MBeanServer** under a unique **ObjectName**. Tools such as JConsole, VisualVM, administration scripts, and monitoring systems access the MBean through that ObjectName.

For example, an application exports:

```text
com.example.orders:type=Queue,name=payments
```

When another Spring bean or exporter tries to register a new MBean with the exact same ObjectName, a **name collision** occurs. Spring Framework supports choosing a registration policy via `RegistrationPolicy`, including **`REPLACE_EXISTING`**: replacing the already-registered MBean with the new MBean.

Replacement can solve redeployment needs or transfer ownership of a management name. However, if the old MBean is **actively being used by clients**, replacing it introduces trade-offs regarding:

- Continuity when reading attributes or invoking operations.
- Compatibility of metadata and the JMX contract.
- Active notification listeners and subscriptions.
- Internal MBean state.
- Ownership and lifecycle of multiple Spring ApplicationContexts.
- Behavior during the window between unregistration and re-registration.
- Risk of clients controlling the wrong resource after the ObjectName is reused.

Key point: **An ObjectName is not an immutable Java object identity over time.** It is a registry name. After replacement, the same ObjectName can point to a different MBean with new state and behavior.

## 2. Three Name-Collision Handling Policies

Spring provides `org.springframework.jmx.support.RegistrationPolicy` to define how the exporter handles a situation where an ObjectName is already in use.

| Policy | Behavior | Operational Meaning |
| --- | --- | --- |
| `FAIL_ON_EXISTING` | Fails with an error when the name is already registered | Detects conflicts and forces owner identification |
| `IGNORE_EXISTING` | Skips registering the new MBean if the name already exists | Keeps the existing MBean, though the new bean may remain unmanaged |
| `REPLACE_EXISTING` | Unregisters the old MBean and registers the new MBean | Swaps what is bound to the ObjectName, with risks of disruption and contract changes |

Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import java.util.Map;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanExporter queueExporter(PaymentQueueAdmin queueAdmin) {
        MBeanExporter exporter = new MBeanExporter();

        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=payments",
            queueAdmin
        ));

        exporter.setRegistrationPolicy(
            RegistrationPolicy.REPLACE_EXISTING
        );

        return exporter;
    }
}
```

`PaymentQueueAdmin` is an illustrative bean; in a real application it needs to be a valid MBean or be exported using an appropriate metadata assembler. The `REPLACE_EXISTING` policy does not make bean methods inherently safe; it only governs **registration behavior on ObjectName collisions**.

### Understanding “Replace” Properly

Replace is not an in-place update on the old MBean's Java object. Typically the exporter must **unregister** the existing name and then **register** the new MBean. This can trigger registration/unregistration events and create a time window where the ObjectName has no corresponding MBean.

Do not assume the entire replacement process is an atomic transaction or that client calls will always route smoothly to the new MBean.

## 3. When an MBean Is in Use, Who Can Be Affected?

An ObjectName may be a dependency point for many consumers:

```text
                      +-- JConsole: viewing attributes
                      |
                      +-- Monitoring collector: polling every 10 seconds
                      |
MBeanServer/ObjectName+-- Automation script: calling resetStatistics()
                      |
                      +-- Alerting service: monitoring queue depth
                      |
                      +-- Notification listener: receiving alerts
```

These consumers do not necessarily know that the MBean was replaced. They only know the ObjectName, attributes, or operations.

After replacement:

1. Clients may continue querying the ObjectName and receive the **new object**.
2. An in-flight call may succeed on the old MBean, fail, or execute on the new MBean depending on timing and dispatch mechanisms.
3. The new MBean's metadata may differ: old attributes/operations may be gone.
4. Notification subscriptions attached to the old MBean may no longer remain valid as before.
5. The new MBean's state may restart from default values or a different snapshot.
6. The old Spring context may still own a resource's lifecycle, causing issues when it closes.

Therefore, replacement should be treated as **modifying an active management contract**, even if the name stays the same.

## 4. First Trade-off: Access Availability

Suppose a monitoring tool reads:

```java
connection.getAttribute(
    new ObjectName("com.example.orders:type=Queue,name=payments"),
    "PendingCount"
);
```

While the exporter replaces the MBean, the following can happen:

```text
T0: Old MBean is registered
T1: unregister Old MBean
T2: ObjectName temporarily does not exist
T3: register New MBean
T4: Client successfully reads from New MBean
```

If the client calls precisely at T2, `getAttribute` can fail with `InstanceNotFoundException`.

If registering the new MBean fails at T3, the name may remain without an MBean, depending on the implementation and error handling. This is why replacement cannot by default be considered a zero-disruption update.

### Impact on Monitoring

A collector may record:

- One or more failed scrapes.
- Gaps in metric data.
- A false alert caused by the metric temporarily disappearing.
- Sudden metric jumps because the new MBean has different state.

For non-critical metrics, a brief gap may be acceptable. For operational control operations, the temporary disappearance of the ObjectName or switch to a new resource must be accounted for in deployment procedures.

### Design Conclusion

If the requirement is **no management gap**, replacing under the same ObjectName may not meet that requirement. Consider clearer lifecycle boundaries, swapping the underlying resource behind a stable MBean, or a controlled transition mechanism.

## 5. Second Trade-off: Metadata Contract Changes

JMX clients use `MBeanInfo` to discover what an MBean exposes:

- Attributes: name, type, readable/writable.
- Operations: name, parameters, return type.
- Notifications: supported event types.
- Descriptions and descriptors.

Example old MBean:

```text
ObjectName: com.example.orders:type=Queue,name=payments

Attributes:
  PendingCount : long [read-only]
  Enabled      : boolean [read/write]

Operations:
  resetStatistics() : void
```

New MBean:

```text
Attributes:
  QueueDepth : int [read-only]
  Enabled    : boolean [read-only]

Operations:
  clearQueue() : void
```

Even though the ObjectName did not change, old clients can break because:

- `PendingCount` no longer exists.
- `Enabled` is no longer writable.
- `resetStatistics()` was removed.
- Numeric type `long` changed to `int`.
- `clearQueue()` has a very different effect than resetting metrics.

**Keeping the same ObjectName does not mean keeping the same management API.**

### How Should Compatibility Be Verified?

Before replacing:

1. Retrieve `MBeanInfo` of the running MBean.
2. Identify which attributes/operations/notifications clients use.
3. Compare against the new MBean's metadata in an isolated environment.
4. Evaluate breaking changes, especially names and types.
5. Update collectors/scripts/dashboards beforehand or as part of the transition workflow.
6. Verify clients work after replacement.

A client using a typed proxy can suffer a larger impact if Java proxy methods are no longer compatible with the new contract.

## 6. Third Trade-off: Loss of Management State

Many MBeans hold internal state:

- Counters since startup.
- Management task status.
- Timestamp of the last operation invocation.
- Most recent error.
- Cached values or metric snapshots.
- Subsystem enabled/disabled state.

When replacing the old MBean with a new object, those states may be reinitialized.

Example:

```text
Old MBean:
  ProcessedCount = 150000
  LastResetTime = 10:00

New MBean:
  ProcessedCount = 0
  LastResetTime = null
```

Monitoring may misinterpret a counter dropping to 0 if it does not know this was a reset/replace event.

### Decoupling the MBean from the Resource to Reduce Impact

One design keeps the **business resource** independent and uses the MBean as an adapter:

```text
PaymentQueueService (holds real state)
              |
      PaymentQueueAdmin (JMX adapter)
              |
          MBeanServer
```

If the adapter is replaced while still referencing the same `PaymentQueueService`, business state may not be lost. However, adapter-specific state can still be lost and switching still requires concurrency handling.

Example:

```java
public interface PaymentQueueAdminMBean {
    long getPendingCount();
}
```

```java
public final class PaymentQueueAdmin
        implements PaymentQueueAdminMBean {

    private final PaymentQueueService service;

    public PaymentQueueAdmin(PaymentQueueService service) {
        this.service = service;
    }

    @Override
    public long getPendingCount() {
        return service.pendingCount();
    }
}
```

`PaymentQueueService` is an illustrative dependency; it must be defined and its lifecycle managed in a real application.

## 7. Fourth Trade-off: Notification Listeners and Subscriptions

JMX supports notifications via `NotificationBroadcaster` and `NotificationListener`. A client can register a listener to receive alerts when a queue exceeds a threshold or an MBean changes state.

When unregistering the old MBean:

- Subscriptions may be bound to the old MBean's broadcaster.
- The new MBean is a different object and does not automatically inherit old listeners/subscriptions.
- Notifications emitted during the transition window may not reach clients.
- Clients need a mechanism to detect registration changes and re-subscribe listeners.

One way to track registry changes is listening to notifications from **`JMImplementation:type=MBeanServerDelegate`**, the delegate MBean that emits registration/unregistration events of the MBeanServer.

Diagram:

```text
Client
  |
  +-- Subscribe to MBean notifications
  |
  +-- Subscribe to MBeanServerDelegate
          |
          +-- UNREGISTRATION_NOTIFICATION
          +-- REGISTRATION_NOTIFICATION
                  |
                  v
       Refresh metadata / re-subscribe
```

This is an architectural suggestion for clients that need to adapt to MBean replacement. Not all JMX clients automatically re-subscribe after replacement; verify with the tools you use.

### Do Not Confuse Notifications with Persistent Queues

JMX notifications are a runtime signaling mechanism. There is no guarantee equivalent to a persistent message queue or event replay after a connection drop. If alerts must not be lost, a more reliable event mechanism is needed at the application layer.

## 8. Fifth Trade-off: Ownership Across Multiple Spring Contexts

Suppose a single JVM contains two Spring `ApplicationContext`s:

```text
Context A
  └── MBeanExporter A
       └── ObjectName = com.example:type=Cache,name=primary

Context B
  └── MBeanExporter B
       └── ObjectName = com.example:type=Cache,name=primary
```

If Context B uses `REPLACE_EXISTING`, Context A's MBean may be unregistered and replaced by Context B's MBean.

Problems:

1. Context A may still believe it is responsible for managing that MBean.
2. When Context A closes, its unregistration logic may affect the current MBean if ownership/lifecycle is not handled properly.
3. Context B may close first, leaving no MBean registered even though Context A is still running.
4. The new MBean may control a different resource while keeping the same name.
5. Operations teams struggle to determine which context is the valid owner.

**Registration policy is a conflict-handling policy, not a mechanism for defining business ownership.**

### How to Design Clear Ownership

- Each ObjectName has one defined owner.
- Only that owner registers/unregisters it.
- Other contexts use proxies/clients to access it rather than registering the same name.
- If each context needs its own MBean, add a stable context/resource-identifying key.
- When a handover occurs, execute a controlled ownership transfer procedure.

## 9. Sixth Trade-off: In-Flight Management Operations

An MBean may have an operation such as:

```java
@ManagedOperation
public void rebuildIndex() {
    // Long-running maintenance task.
}
```

If replacement happens while `rebuildIndex()` is running, unregistering the MBean does not necessarily stop the thread that already entered the old method. The old Java object may still be referenced by threads, tasks, or other resources.

As a result, the following can happen:

```text
T0: Client invokes rebuildIndex() on Old MBean
T1: Old MBean starts a long task
T2: Exporter unregisters Old MBean
T3: Exporter registers New MBean
T4: Another client invokes rebuildIndex() on New MBean
T5: Both tasks may run concurrently
```

Replacing the MBean does not automatically guarantee **single-flight** execution or a shared mutex between the old and new versions.

### Decouple Resource Lifecycle from MBean Lifecycle

If an operation mutates a shared resource, enforce concurrency control at the resource/service level, not only with a `running` flag inside the MBean adapter.

For example, both old and new adapters reference a single service with one state machine:

```text
Old MBean ─┐
           ├── SharedReindexService
New MBean ─┘        |
                    +-- single-flight
                    +-- operation ID
                    +-- status
```

That way, both adapters share the same control mechanism. If the old and new resources are two independent objects, an additional handover protocol is needed to avoid competing tasks on the same data or external system.

## 10. Is Replacement Always Necessary?

In many cases, the actual requirement does not call for unregistering/re-registering the MBean.

### 10.1. Only Changing Data or State

If you need to update an attribute, use a setter or operation on the same MBean.

```text
MBean keeps the same ObjectName and instance
    |
    +-- setConfiguration(...)
    +-- refreshSnapshot()
    +-- resetStatistics()
```

This avoids name disruption in the registry, though operations still must be designed safely.

### 10.2. Wanting to Swap the Underlying Implementation

You can keep a stable MBean adapter and swap the delegate through a thread-safe mechanism:

```text
Stable MBean
    |
    +-- AtomicReference<ManagedService>
              |
              +-- Service V1
              +-- Service V2
```

Illustrative example:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class StableServiceAdmin implements StableServiceAdminMBean {
    private final AtomicReference<ManagedService> delegate;

    public StableServiceAdmin(ManagedService initial) {
        this.delegate = new AtomicReference<>(
            Objects.requireNonNull(initial)
        );
    }

    @Override
    public String getStatus() {
        return delegate.get().status();
    }

    public void replaceDelegate(ManagedService next) {
        delegate.set(Objects.requireNonNull(next));
    }
}
```

`ManagedService` and `StableServiceAdminMBean` are interfaces to define in a real application. The snippet shows how to swap the reference atomically; it **does not automatically manage in-flight calls** on the old delegate, uncleaned resources, or compatibility between the two implementations. If the requirement is that no calls run on the old service after cutover, a separate drain/quiesce mechanism is needed.

### 10.3. Needing an Incompatible New API

If the management contract changes significantly, consider registering a new name:

```text
com.example.orders:type=QueueAdmin,version=v1,name=payments
com.example.orders:type=QueueAdmin,version=v2,name=payments
```

During the transition period, both MBeans can coexist under different names. This allows clients to upgrade incrementally, while ensuring two MBeans do not concurrently perform dangerous commands without coordination.

## 11. When Is REPLACE_EXISTING a Reasonable Choice?

Replace may be appropriate if:

- One component clearly owns the ObjectName.
- The current MBean is definitely an old instance that needs replacing.
- There are no uncontrolled long-running operations.
- The attributes/operations contract has no breaking changes for clients.
- State that must persist lives in a shared resource or has a handover mechanism.
- A brief disruption during unregister/register is acceptable.
- Clients can handle transient errors and refresh metadata/subscriptions.
- Exporter and context lifecycles are cleanly structured.
- Monitoring is in place to confirm the new MBean actually appears and functions.

For example, in a development environment, context reload may re-register a low-criticality management MBean. Replace can be more convenient than fail when it is well known that the old MBean was left behind by reload and a single owner controls both versions.

Conversely, in production environments where multiple contexts share the platform MBeanServer, do not set `REPLACE_EXISTING` across all exporters as a blanket policy.

## 12. Controlled MBean Handover Workflow

If you still need to replace an MBean under the same name, you can follow this workflow:

### Step 1: Identify the Owner

Record which context/exporter currently owns the name and which resource is being managed.

### Step 2: Inventory Clients

List dashboards, scripts, JConsole sessions, listeners, and active operations in use.

### Step 3: Compare Metadata

Read both old and new `MBeanInfo`, confirming required attributes/operations remain compatible.

### Step 4: Check State and Running Tasks

If long operations exist, move to drain/quiesce state or wait for completion per contract. Do not assume unregistering cancels tasks.

### Step 5: Prepare the New MBean

Initialize resources, validate configuration, and ensure the new MBean is compliant and registrable. You can test the new MBean under a temporary ObjectName in an isolated MBeanServer, or in a staging environment.

### Step 6: Switch Over

Execute unregister/register through a controlled owner mechanism. If using Spring `REPLACE_EXISTING`, understand the exporter's limits and actual error handling.

### Step 7: Verify

Check that the ObjectName is registered, `MBeanInfo` is correct, attributes are readable, and notification listeners are restored if needed.

### Step 8: Monitor

Watch for scrape errors, invoke errors, sudden metric shifts, and task statuses after cutover.

### Step 9: Define Rollback

If rollback is required, know whether state can be reverted. For business side effects already executed by the new MBean, re-registering the old MBean does not automatically undo those effects.

## 13. Verifying the MBean Before and After Replace via API

### Check Registered Name

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=payments"
);

System.out.println("Registered: " + server.isRegistered(name));
```

`isRegistered` tells you an MBean exists under that name, **not whether it is the old or new version**.

### Read Metadata

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "ATTRIBUTE %s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "OPERATION %s return=%s%n",
        operation.getName(),
        operation.getReturnType()
    );
}
```

Metadata helps validate the contract, but if two implementations expose identical MBeanInfo, it is insufficient to verify the runtime version conclusively. You can expose a safe management attribute such as `ImplementationVersion` or `Generation` so clients can identify the replacement milestone.

### Check Operational State

Read important attributes such as:

```text
Status
PendingCount
LastSuccessfulOperation
ImplementationVersion
```

For operations with side effects, do not run a risky test command merely to confirm the MBean is alive. Prefer getters and read-only diagnostics.

## 14. Tracking Registry Changes via MBeanServerDelegate

JMX provides the system MBean `JMImplementation:type=MBeanServerDelegate`, which can emit `MBeanServerNotification` when an MBean is registered or unregistered.

An illustrative listener:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerNotification;
import javax.management.Notification;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public class RegistryObserver {

    public static void subscribe(MBeanServer server)
            throws Exception {

        ObjectName delegate = new ObjectName(
                "JMImplementation:type=MBeanServerDelegate"
        );

        NotificationListener listener = (notification, handback) -> {
            if (notification instanceof MBeanServerNotification event) {
                System.out.println(
                    notification.getType()
                    + " : " + event.getMBeanName()
                );
            }
        };

        server.addNotificationListener(
                delegate,
                listener,
                null,
                null
        );
    }
}
```

The example above uses modern Java `instanceof ... event` syntax; for older Java versions, cast using traditional syntax.

If building a custom client that supports replacement, you can observe registry events, refresh metadata, and re-subscribe listeners on the target MBean when the name reappears. Manage listener lifecycles to avoid leaks.

**Limitation:** notifications may be missed while a client is disconnected. Clients still need a mechanism to re-query registry state after reconnecting.

## 15. Do Not Use REPLACE_EXISTING to Fix Every Configuration Bug

When encountering `InstanceAlreadyExistsException`, the cause may be:

1. Two different beans using the same ObjectName.
2. Two `ApplicationContext`s exporting the same bean.
3. An MBean already registered manually and an exporter trying to register again.
4. An overly generic hard-coded ObjectName.
5. A bean/proxy initialized multiple times.
6. An old context that failed to unregister the MBean.
7. A library/framework already registered the name the application wants to use.

Choosing replace immediately can obscure the real cause. Better solutions are usually:

- Add distinguishing keys like `application`, `context`, `name`.
- Ensure only one exporter acts as owner.
- Check registration/unregistration lifecycle.
- Use explicit naming or a consistent `ObjectNamingStrategy`.
- Use `FAIL_ON_EXISTING` in environments where early error detection is required.

**Replace is only appropriate when removing the existing MBean is truly the intended behavior.**

## 16. Is IGNORE_EXISTING Safer?

`IGNORE_EXISTING` avoids unregistering the current MBean, reducing the risk of disrupting clients using the old MBean. However, it carries other trade-offs:

- The new bean is not exported as expected.
- Operators may see metrics from the old version even though the new application is running.
- An ObjectName may silently point to the wrong owner.
- If the old MBean is later unregistered, the new MBean will not automatically register in its place.

Therefore, `IGNORE_EXISTING` fits when the existing MBean is a shared resource and skipping the new bean registration is an explicit decision, not a way to brush aside an uninvestigated conflict.

### Comparison by Goal

| Goal | More Suitable Policy |
| --- | --- |
| Detect naming and ownership misconfigurations | `FAIL_ON_EXISTING` |
| Keep an existing MBean verified as the valid owner | `IGNORE_EXISTING` |
| Transfer ownership and replace an MBean under control | `REPLACE_EXISTING` |
| Need zero disruption or gradual client migration | Consider a stable adapter or a versioned new ObjectName |

## 17. Special Case: Remote Clients Holding a Proxy

A JMX client may create a typed proxy:

```java
import javax.management.JMX;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

PaymentQueueAdminMBean proxy = JMX.newMBeanProxy(
        connection,
        new ObjectName(
            "com.example.orders:type=Queue,name=payments"
        ),
        PaymentQueueAdminMBean.class
);
```

The proxy usually dispatches calls via the ObjectName and connection. If the MBean is replaced under the same name, subsequent calls may reach the new MBean.

However, that only works if:

- The new MBean exposes the exact required attributes/operations.
- Parameter and return types are compatible.
- Access permissions still allow it.
- The MBean is already registered when the call happens.

A typed proxy does not lock the ObjectName to the old Java object. If the new contract differs, the proxy can fail at runtime. If the client also holds a metadata cache or notification subscription, replacing the MBean may require refresh/re-subscription.

## 18. Special Case: Model MBeans and Metadata Caches

Spring can export POJOs via Model MBeans based on metadata. A Model MBean may have descriptors controlling attribute caching, such as `currencyTimeLimit`.

When replacing a Model MBean:

- Old cached attribute values on the Model MBean may be lost.
- Metadata descriptors may change.
- Getters on the new resource may reflect different data.
- Clients reading before/after may observe swings not caused by business activity.

If dashboards rely on counters, clarify whether the counter lives in the business service or only in the adapter/metadata cache. Reset/replace can create a new statistical boundary.

## 19. Special Case: Multi-Replica and Multiple JVMs

Each JVM has its own MBeanServer, so the same ObjectName on two JVMs is **not a registration conflict**.

```text
JVM A:
  com.example.orders:type=Queue,name=payments

JVM B:
  com.example.orders:type=Queue,name=payments
```

`REPLACE_EXISTING` in JVM B does not replace JVM A's MBean. However, centralized monitoring systems must attach target/instance labels to distinguish metrics.

If multiple Spring contexts in the **same JVM** share an MBeanServer, collisions can still happen. Do not confuse “multiple applications” with “multiple MBeanServers”: the uniqueness scope is always the specific server.

## 20. Observability and Alerting After Replacement

A replacement process should have telemetry signals:

| Signal | What to Detect |
| --- | --- |
| MBean registration count | Whether the name disappears/re-registers as expected |
| Scrape errors | Whether collectors hit read errors during replacement |
| Attribute schema | Whether names, types, and readable/writable flags remain intact |
| Operation failures | Whether scripts hit missing operations or mismatched signatures |
| Notification subscription health | Whether listeners resume receiving events after replacement |
| Resource status | Whether the new resource is ready |
| Active job count | Whether old and new tasks are running concurrently in overlap |
| State continuity | Whether counters, configs, or job statuses shift unexpectedly |

You can expose a read-only `Generation` or `ImplementationVersion` attribute to simplify diagnostics:

```java
@ManagedAttribute(
    description = "Generation of this management adapter"
)
public String getGeneration() {
    return generation;
}
```

Do not put secrets or sensitive build details into attributes. The generation value should also be designed for its purpose: deployment identifier, adapter lifecycle, or management interface version.

## 21. Example Incident Progression

An application has an MBean:

```text
ObjectName: com.example.cache:type=Cache,name=products
HitCount: 120000
Operations: clear(), resetStatistics()
```

A new Spring context starts up and uses `REPLACE_EXISTING` for the same name. The new MBean only exposes:

```text
HitCount: 0
Operations: clear()
```

Result:

1. Dashboards see `HitCount` suddenly drop from 120000 to 0.
2. Scripts invoking `resetStatistics()` fail because the operation no longer exists.
3. JConsole still shows the same ObjectName, potentially leading operators to assume the MBean did not change.
4. Listeners registered for the old MBean do not necessarily receive notifications from the new MBean.
5. When the old context stops, export lifecycle must be checked to avoid accidentally removing the current name.

The right fix must start from **contract and ownership**. If only metric computation code needs updating, a stable adapter or a controlled version transition can greatly reduce disruption.

## 22. Checklist Before Enabling REPLACE_EXISTING

Answer the following questions before choosing the replacement policy:

1. Which exporter/context owns the current ObjectName?
2. Which clients/scripts/dashboards does the MBean serve?
3. Are there registered notification listeners?
4. Does the old MBean have in-flight operations?
5. Does the new MBean preserve the attribute/operation contract?
6. Is there state inside the adapter that must be handed over?
7. Can the old resource stop safely before the new resource becomes active?
8. Is a brief window where the ObjectName does not exist acceptable?
9. Is there a way to verify the new MBean is the expected implementation?
10. If the new registration fails, what does the system do?
11. If rollback is needed, can operations already executed by the new MBean be reversed?
12. After replacement, do clients refresh metadata and re-subscribe notifications?
13. Could the old context/exporter accidentally unregister the new MBean?
14. Could a new name or stable adapter be used to avoid replacement?

These questions turn registration policy selection into a verifiable design decision rather than a single configuration flag.

## 23. Self-Check Questions

**1. Does `REPLACE_EXISTING` guarantee zero disruption?**

No. Unregistering and registering the new MBean can create a gap, transient errors, and lost subscriptions.

**2. Does the same ObjectName mean the same Java object?**

No. ObjectName is a registry name; it can point to a different MBean after replacement.

**3. Why can typed proxy clients fail after replacement?**

Because the new MBean may lack an operation/attribute or have a signature incompatible with the old proxy interface.

**4. Does replacement stop operations currently running on the old MBean?**

Not necessarily. Executing threads may continue on the old resource; dedicated concurrency and handover mechanisms are needed.

**5. Is `IGNORE_EXISTING` always the safest option?**

No. It can preserve an old MBean with the wrong owner and leave the new bean unmanaged.

**6. Why are multiple ApplicationContexts in the same JVM prone to collisions?**

Because they may share the platform MBeanServer; ObjectName must be unique within that server.

**7. How can a client tell an MBean was just replaced?**

It can monitor registration/unregistration notifications from MBeanServerDelegate and re-check metadata/attributes after reconnecting.

**8. When should a new ObjectName be used?**

When migrating an incompatible API or maintaining two versions in parallel for controlled client upgrades.

## 24. Summary

`RegistrationPolicy.REPLACE_EXISTING` can be useful when an MBean must be replaced under the same ObjectName, but replacing an MBean **actively in use** can directly impact availability, API contracts, state, listeners, running tasks, and the lifecycle of multiple Spring contexts.

A safe replacement decision requires:

- Identifying the **owner** of the ObjectName.
- Checking **MBeanInfo** and client compatibility.
- Proactively handling **notification subscriptions**.
- Managing state and in-flight tasks at the **resource/service layer**.
- Accepting or minimizing the unregister/register disruption window.
- Verifying the new MBean and having a failure-handling plan for cutover.

If the goal is simply to swap the implementation or data inside a resource, keeping a **stable MBean adapter** usually reduces risk. When APIs change incompatibly, assigning a new ObjectName for phased migration can be much clearer.

**Registration policy resolves name conflicts; continuity and safety of the management system must be designed separately.**

### References

- Spring Framework API — `RegistrationPolicy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Spring Framework API — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Java SE API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE API — `MBeanServerNotification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerNotification.html

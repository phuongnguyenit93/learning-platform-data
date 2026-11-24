# Versioning Management Interfaces in Spring Framework JMX

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain that a **management interface** in JMX is a contract for operational tools, not merely an internal Java interface.
- Distinguish compatibility levels: Java source/binary compatibility, JMX metadata compatibility, client compatibility, semantic compatibility, and operational compatibility.
- Identify breaking changes when modifying `ObjectName`, attribute name/type/access, operation name/signature, notification type, return type, description, and semantics.
- Design a **management interface versioning** strategy per MBean by preserving old contracts, adding new contracts, or including versions in ObjectName when needed.
- Plan migration between v1 and v2 in Spring Framework JMX without unintentionally breaking dashboards, alert rules, JConsole scripts, or JMX exporters.
- Use Standard MBeans, MXBeans, or annotation-driven management adapters with clear version boundaries.
- Verify compatibility using `MBeanServer.getMBeanInfo()`, `getAttribute()`, `invoke()`, and automated integration tests.
- Understand when not to create a new version and when to announce deprecation, run parallel support, and retire old APIs.

## 2. Management Interfaces Are Public APIs for Operations

JMX (Java Management Extensions) allows an application or JVM to expose a set of **attributes, operations, and notifications** in an `MBeanServer`. Those elements are identified by an `ObjectName` and `MBeanInfo` metadata.

Example:

~~~text
ObjectName:
com.example.shop.orders:type=QueueMonitor,name=outbox

Attributes:
PendingCount : int (read-only)
Paused       : boolean (read-only)

Operations:
pause()
resume()
resetStatistics()

Notifications:
com.example.shop.queue.threshold.exceeded
~~~

If a JMX exporter, dashboard, monitoring rule, or script already uses that contract, renaming `PendingCount` to `QueueDepth` can cause scripts to fail even though the new Java service compiles and runs.

**Principle:** A management interface already used by clients must be managed as a **versioned API with a compatibility lifecycle**.

Do not assume management methods are “internal only” and can be changed arbitrarily. In production, consumers may include:
- JConsole/JMC and incident troubleshooting tools.
- JMX exporters or metric collectors.
- Alert rules and dashboards based on attribute names.
- Automation scripts calling `getAttribute()`/`invoke()`.
- Java clients using `JMX.newMBeanProxy()` or Spring `MBeanProxyFactoryBean`.
- Application server or library management tools.

A change that does not affect the Java compiler can still break JMX clients.

## 3. What Layers Does “Versioning” Cover?

| Layer | Subject of change | Risk |
|---|---|---|
| Java source API | Interface, method, parameter names | Client code fails to compile |
| Java binary API | Method descriptors and class signatures | `NoSuchMethodError` or linkage errors |
| JMX ObjectName | Domain/key properties | Client cannot find MBean |
| JMX attribute metadata | Name/type/readable/writable | `AttributeNotFoundException` or cast failure |
| JMX operation metadata | Name/parameter signature/return | `ReflectionException` or wrong invocation |
| JMX value representation | Scalar, CompositeData, MXBean mapping | Client cannot parse/cast |
| Semantics | Meaning, units, consistency guarantees | Dashboard keeps running but misinterprets data |
| Security/authorization | Who can read or invoke | Automation denied or unintended privilege expansion |
| Lifecycle | Register/unregister timing | Clients lose endpoint during deployment |
| Observability mapping | Exporter rules, labels, dashboards | Time series interrupted or renamed |

Proper versioning must consider both **syntax** and **semantics**. For example, keeping attribute `Timeout` with the same name and type `long` while changing its unit from milliseconds to seconds is a breaking semantic change even though Java/JMX metadata did not change.

## 4. Example v1 Contract

Suppose the application initially has a Standard MBean:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

~~~java
public class QueueMonitor implements QueueMonitorMBean {
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return 42;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
~~~

Registration:

~~~java
ObjectName name = new ObjectName(
    "com.example.shop.orders:type=QueueMonitor,name=outbox");

server.registerMBean(new QueueMonitor(), name);
~~~

A JMX client reads:

~~~java
int count = (Integer) server.getAttribute(
        name, "PendingCount");
~~~

and invokes an operation:

~~~java
server.invoke(
        name, "pause", new Object[0], new String[0]);
~~~

Everything works as long as the MBean is registered and the contract matches. Problems arise when the server is upgraded without upgrading all clients simultaneously.

## 5. Which Changes Can Remain Compatible?

### 5.1. Adding a New Attribute

From v1:

~~~text
PendingCount : int
Paused       : boolean
~~~

to v2:

~~~text
PendingCount : int
Paused       : boolean
OldestPendingAgeMillis : long
~~~

If existing attributes keep their names, types, readability, and semantics, many existing clients continue working. This is typically an **additive change**.

However, there is no absolute guarantee: a client written against a rigid schema or relying on an exact attribute count might reject the new field. Contract tests are still needed.

### 5.2. Adding a New Operation

Adding `refreshSnapshot()` generally does not break old clients that only invoke previous operations. However, it expands the management surface and may introduce security or audit risks. “Backward compatible” does not mean “safe to expose”.

### 5.3. Updating Descriptions/Documentation

Updating the description of `PendingCount` for clarity usually does not break method signatures. However, exporters or automation might parse metadata descriptions by custom rules; avoid embedding mandatory machine-readable data in descriptions without documentation.

### 5.4. Optimizing Implementation

Switching a getter from a DB query to a cached snapshot while keeping the same contract may not break syntax, but you must announce the change in **freshness** if clients previously assumed each read returned a real-time query value.

### 5.5. Adding Auxiliary Metadata

Adding `CapturedAtEpochMillis`, `SnapshotHealthy`, or `Generation` can aid compatibility and transparency, provided old clients still receive old attributes with appropriate semantics.

## 6. Common Breaking Changes

| Change | Example | Impact |
|---|---|---|
| Changing ObjectName | `type=QueueMonitor` → `type=QueueStats` | Client `isRegistered` false; exporter misses MBean |
| Renaming attribute | `PendingCount` → `QueueDepth` | `AttributeNotFoundException` |
| Changing attribute type | `int` → `long` | Proxies/casts expecting `Integer` may fail |
| Changing access | readable → not readable | Clients can no longer read |
| Renaming operation | `pause` → `suspend` | `invoke` cannot find operation |
| Changing parameters | `resize(int)` → `resize(long)` | JMX signature mismatch |
| Changing return structure | scalar → CompositeData | Old deserializers/casts/schemas fail |
| Changing units | milliseconds → seconds | Metrics/alerts misinterpreted |
| Changing behavior | `resetStatistics` also resets business state | Unexpected side effects |
| Changing notification type | event name modified | Listeners filtering by type miss events |
| Changing version naming | v1 MBean removed before migration | Old clients lose endpoint |
| Changing remote access | connector/port/auth modified | Clients fail to connect |

A single change can break multiple layers. For example, switching from a Standard MBean to an MXBean can alter `MBeanInfo` and value mappings even when the Java interface looks nearly identical.

## 7. Changing int to long: Why Be Careful?

Example v1:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
}
~~~

v2:

~~~java
public interface QueueMonitorMBean {
    long getPendingCount();
}
~~~

A Java developer might view this as widening the integer range. Yet a v1 JMX client may cast:

~~~java
Integer value = (Integer) connection.getAttribute(
        name, "PendingCount");
~~~

In v2, the runtime JMX value may be `Long`, causing `ClassCastException`. A JMX dynamic proxy using the v1 interface may also fail to match the actual return type.

Smooth transition approaches:

- Keep the old `getPendingCount()` temporarily if values can still be represented accurately; never silently truncate.
- Add `getPendingCountLong()` or a newly named attribute that clearly indicates the type.
- If the `int` range is exceeded, define a policy for v1 (e.g., deprecate and signal overflow) instead of returning wrong numbers.
- Expose a v2 MBean with the new contract under a separate ObjectName if clients need synchronized upgrades.
- Measure actual client versions before removing v1.

Do not change types directly in production without compatibility tests.

## 8. Changing Units Can Also Be a Breaking Change

Suppose v1 has:

~~~text
AverageProcessingTime = 2500
Unit = milliseconds
~~~

If v2 returns `2.5` seconds under the same name, old clients will chart the metric 1000x lower or trigger false alerts.

Two clearer approaches:

1. Keep `AverageProcessingTimeMillis` and add `AverageProcessingTimeSeconds`.
2. Create an explicit v2 contract with a new name/description and migrate consumers systematically.

If using `@ManagedMetric` or descriptors with units, metadata must also be updated consistently. Do not expect clients to infer a unit change from a description string.

## 9. Strategy A — Keep One ObjectName and Evolve Additively

If changes are primarily non-breaking additions of attributes/operations, you can keep:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox
~~~

and extend the management interface:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();

    long getProcessedCount();
    long getLastRefreshEpochMillis();
}
~~~

Pros:
- Old clients keep using the old ObjectName.
- Monitoring rules do not need domain/key changes.
- Usually easy to operate when only adding data.

Cons:
- Contract can bloat if many legacy attributes accumulate.
- Hard to handle incompatible type/semantics changes.
- New operations require security review.

**Rule:** Only add new elements when old semantics can be preserved. Otherwise, use a parallel or versioned ObjectName strategy.

## 10. Strategy B — Create a Versioned ObjectName

When v2 breaks the v1 contract, two independent MBeans can be registered:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox,version=v1
com.example.shop.orders:type=QueueMonitor,name=outbox,version=v2
~~~

Each ObjectName has its own management contract.

Pros:
- Clients can explicitly choose their version.
- Enables step-by-step migration.
- Easy to test v1 and v2 side by side.
- Avoids silently changing behavior under the same ObjectName.

Cons:
- Requires operating two adapters/MBeans during the transition period.
- May duplicate metrics/numbers if collectors scrape both.
- Can increase load if v1 and v2 compute independently.
- Clients/dashboards must know the version key.

Note: if v1 previously used a name **without** the `version` key, adding only `version=v1` will still break old clients looking up the unversioned name. During migration, **keep the historical ObjectName** for v1 and use the version key only for v2, or provide a compatible alias MBean:

~~~text
Legacy v1: com.example.shop.orders:type=QueueMonitor,name=outbox
New v2:    com.example.shop.orders:type=QueueMonitor,name=outbox,version=v2
~~~

Do not alter the v1 name just to make both version names look neat and uniform.

## 11. Strategy C — Management Facade with Internal Versioning

Another option is keeping the ObjectName stable while placing a facade/adapter as the contract source:

~~~text
JMX client
    |
    v
QueueManagementFacade (stable ObjectName)
    |
    +-- adapter v1 semantics
    +-- adapter v2 implementation
    |
    v
Queue service + snapshot data
~~~

A facade hides implementation details and avoids directly exporting business beans. However, if a v1 method must return `int` while v2 needs `long`, the facade cannot swap the type under the same attribute while preserving binary/JMX compatibility. Adding a new attribute or versioned MBean is still required in that case.

A facade is not magic that converts every contract automatically. It merely centralizes version logic in one place.

## 12. Example of Standard MBean v1 and v2 in Parallel

Two interfaces:

~~~java
public interface QueueMonitorV1MBean {
    int getPendingCount();
}

public interface QueueMonitorV2MBean {
    long getPendingCount();
    long getProcessedCount();
    long getSnapshotEpochMillis();
}
~~~

Both implementations can read from a single `QueueStatistics` service:

~~~java
public final class QueueMonitorV1 implements QueueMonitorV1MBean {
    private final QueueStatistics stats;

    public QueueMonitorV1(QueueStatistics stats) {
        this.stats = stats;
    }

    @Override
    public int getPendingCount() {
        long value = stats.pendingCount();
        if (value > Integer.MAX_VALUE || value < Integer.MIN_VALUE) {
            throw new IllegalStateException(
                    "Legacy PendingCount is out of int range");
        }
        return (int) value;
    }
}
~~~

~~~java
public final class QueueMonitorV2 implements QueueMonitorV2MBean {
    private final QueueStatistics stats;

    public QueueMonitorV2(QueueStatistics stats) {
        this.stats = stats;
    }

    @Override
    public long getPendingCount() {
        return stats.pendingCount();
    }

    @Override
    public long getProcessedCount() {
        return stats.processedCount();
    }

    @Override
    public long getSnapshotEpochMillis() {
        return stats.snapshotEpochMillis();
    }
}
~~~

Because Standard MBean naming conventions depend on matching class/interface names, the two classes and interfaces here use matching name pairs. If different class/interface names are needed, use the `StandardMBean` wrapper from the Java JMX API.

Example explicit registration:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName legacyName = new ObjectName(
    "com.example.shop.orders:type=QueueMonitor,name=outbox");
ObjectName v2Name = new ObjectName(
    "com.example.shop.orders:type=QueueMonitor,name=outbox,version=v2");

server.registerMBean(new QueueMonitorV1(stats), legacyName);
server.registerMBean(new QueueMonitorV2(stats), v2Name);
~~~

This example assumes `stats` already exists, implements its own service interface, and has no name collisions. In a Spring application, use the proper bean/exporter owner rather than registering manually if lifecycle is managed by Spring.

**Be careful:** Do not “solve” v1 overflow by direct casting that silently yields negative/wrong numbers. When the legacy type can no longer represent values accurately, define an error-reporting policy or planned migration.

## 13. Spring Annotation-Driven Versioning

Another architecture uses two Spring management adapters with separate metadata.

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox",
    description = "Legacy queue management v1")
public class QueueManagementV1 {
    private final QueueStatistics stats;

    public QueueManagementV1(QueueStatistics stats) {
        this.stats = stats;
    }

    @ManagedAttribute
    public int getPendingCount() {
        long count = stats.pendingCount();
        if (count > Integer.MAX_VALUE) {
            throw new IllegalStateException("Count exceeds v1 range");
        }
        return (int) count;
    }
}
~~~

~~~java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox,version=v2",
    description = "Queue management v2")
public class QueueManagementV2 {
    private final QueueStatistics stats;

    public QueueManagementV2(QueueStatistics stats) {
        this.stats = stats;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return stats.pendingCount();
    }

    @ManagedAttribute
    public long getProcessedCount() {
        return stats.processedCount();
    }
}
~~~

Requirements:
- `QueueStatistics` is a Spring bean or properly injected contract.
- One annotation-aware exporter selects and registers both adapters.
- The naming strategy honors each resource's `objectName`.
- No other exporter creates duplicate registrations.
- Both adapters rely on shared data to avoid skewed measurements.
- Each ObjectName has a clear registration owner and lifecycle.

If using Spring AOP proxies, verify method exposure and annotation discovery. A dedicated management adapter is usually easier to maintain than annotating a business service directly when it carries multiple transaction/security advices.

## 14. Why Must REPLACE_EXISTING Never Be Used as Versioning?

Spring JMX supports `RegistrationPolicy`:

| Policy | When ObjectName already exists |
|---|---|
| `FAIL_ON_EXISTING` | Report conflict |
| `IGNORE_EXISTING` | Keep old MBean |
| `REPLACE_EXISTING` | Replace old MBean |

This is a **duplicate-registration handling policy**, not an API versioning mechanism. Using `REPLACE_EXISTING` to put v2 under v1's name can cause v1 clients to receive unexpected metadata and fail.

A versioning strategy must account for:
- Which names clients are using.
- Which contract is published.
- When clients migrate to v2.
- When v1 is deprecated and removed.
- How to roll back.
- Who owns each ObjectName.

If you want to swap implementations under the same ObjectName, ensure the contract stays compatible. Otherwise, a versioned ObjectName or compatibility adapter is the clear solution.

## 15. MBeanInfo Is the Runtime Source of Truth

Source code is the intended contract; `MBeanInfo` is what JMX clients actually observe.

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class ContractInspector {
    public static void inspect(String objectName) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        MBeanInfo info = server.getMBeanInfo(
                new ObjectName(objectName));

        System.out.println("MBean: " + objectName);
        System.out.println("Implementation: " + info.getClassName());

        for (MBeanAttributeInfo a : info.getAttributes()) {
            System.out.printf(
                "ATTR %s type=%s readable=%s writable=%s%n",
                a.getName(),
                a.getType(),
                a.isReadable(),
                a.isWritable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.printf(
                "OP %s returns %s%n",
                op.getName(),
                op.getReturnType());
        }
    }
}
~~~

If the Spring exporter uses a custom MBeanServer, inspect that exact server instead of the platform server. Metadata values prove API surface; to verify semantics, add tests that actually invoke and check results.

For overloaded operations, compare not just names but also parameter types and signatures. JMX `invoke(name, "resize", args, signature)` distinguishes `int` from `long` and other types.

## 16. Designing Contract Tests for v1 and v2

In a Spring integration test:
1. Start the ApplicationContext with the actual exporter/assembler.
2. Use a dedicated test MBeanServer if possible.
3. Verify the v1 ObjectName remains registered.
4. Verify the v2 ObjectName is registered.
5. Check v1 `PendingCount` has type `int` and is readable.
6. Check v2 `PendingCount` has type `long`.
7. Call `getAttribute()` and verify runtime values.
8. Verify old and new operations (including signatures).
9. Verify internal operations are not exposed.
10. Close the context and verify cleanup by the proper registration owner.

Assertion pseudocode:

~~~java
ObjectName v1 = new ObjectName(
    "com.example.shop.orders:type=Queue,name=outbox");

ObjectName v2 = new ObjectName(
    "com.example.shop.orders:type=Queue,name=outbox,version=v2");

assertTrue(server.isRegistered(v1));
assertTrue(server.isRegistered(v2));

MBeanInfo oldInfo = server.getMBeanInfo(v1);
MBeanInfo newInfo = server.getMBeanInfo(v2);

assertTrue(
    java.util.Arrays.stream(oldInfo.getAttributes())
        .anyMatch(a -> a.getName().equals("PendingCount")
                    && a.getType().equals("int")));

assertTrue(
    java.util.Arrays.stream(newInfo.getAttributes())
        .anyMatch(a -> a.getName().equals("PendingCount")
                    && a.getType().equals("long")));
~~~

This snippet assumes JUnit assertions are imported and the server has started and registered both MBeans. It is illustrative logic, not a complete standalone test.

Do not check only `isRegistered`; another MBean might occupy the same name if `IGNORE_EXISTING` registration policy is configured.

## 17. Snapshot Testing Metadata, with Caveats

One way to manage contracts is saving a structured description of MBeanInfo:

~~~json
{
  "objectName": "com.example.shop.orders:type=Queue,name=outbox",
  "attributes": [
    {"name": "PendingCount", "type": "int", "readable": true},
    {"name": "Paused", "type": "boolean", "readable": true}
  ],
  "operations": [
    {"name": "pause", "signature": []},
    {"name": "resume", "signature": []}
  ]
}
~~~

After each build, integration tests compare runtime metadata against the expected contract. Any diff flags a management API change requiring review.

Limitations:
- Some metadata descriptions or ordering may vary across assemblers/versions.
- Do not depend on attribute ordering if it has no contractual meaning.
- Overly rigid snapshots can cause valid additive changes to fail tests.
- Comparing metadata alone misses semantic changes like unit conversions or timeout behavior.

Separate tests into **required legacy contract** and **new v2 contract**, while testing key semantics with integration assertions.

## 18. Versioning with CompositeData and MXBean

An MBean may return `CompositeData` or an MXBean mapped type instead of scalar attributes.

Example v1 schema:

~~~text
QueueSnapshot {
  pendingCount: int
  paused: boolean
}
~~~

v2 schema:

~~~text
QueueSnapshot {
  pendingCount: long
  processedCount: long
  paused: boolean
  capturedAtEpochMillis: long
}
~~~

Changing `pendingCount` from int to long or renaming fields is a breaking change for clients reading the old schema.

Some field additions may be compatible with consumers that look up fields by name, whereas clients comparing the full CompositeType or deserializing into a fixed class can still fail.

Strategy:
- Keep the v1 `CompositeData` schema on the old ObjectName.
- Publish v2 under a versioned ObjectName or a new attribute with an explicit schema.
- Include explicit generation/timestamp and type metadata.
- Avoid returning DTOs/JPA entities directly if remote clients lack the same Java classes.
- Verify MXBean types genuinely support open-type mapping under the JDK.
- Keep schemas small; do not return unbounded collections over JMX.

Do not assume every Java record/generic type automatically works with MXBean mapping across all versions.

## 19. Versioning JMX Notifications

Some MBeans emit notifications and clients may filter by notification type.

Example:
~~~text
com.example.shop.queue.threshold.exceeded
~~~

If v2 renames it to:
~~~text
com.example.shop.queue.backlog.high
~~~

old listeners filtering on the v1 type will miss events even though the MBean still exists. Changes to review include:
- Notification type.
- Message format and userData schema.
- Threshold meaning.
- Sequence semantics.
- Frequency and reconnection guarantees.
- Attribute-change notification metadata if used.

During the transition, you can keep the old notification type or intentionally emit both. However, emitting double events can trigger automation twice if clients subscribe broadly. Document and test carefully.

JMX notifications are not durable queues with replay by default, so migration cannot rely solely on listeners receiving every event.

## 20. Versioning Operations with Side Effects

Operations carry higher risk than getters when behavior changes.

Example v1:
~~~java
void resetStatistics();
~~~

v2 keeps the name but expands behavior to also reset worker state or clear pending jobs. That is a dangerous breaking semantic change even though the signature did not change.

Clear approach:
- Keep `resetStatistics()` resetting only monitoring counters as in v1.
- Add a new operation `resetQueueState()` if truly needed.
- Set clear descriptions and authorization policies.
- Audit impactful operations.
- Avoid exposing destructive operations over JMX without a legitimate use case.

Do not introduce a new operation in v2 and grant broad readwrite access to all monitoring clients without enforcing least privilege.

## 21. Upgrading Spring Framework and Java JDK

Management contracts can change unintentionally when upgrading frameworks/runtimes:

- Assemblers or metadata discovery change.
- Proxy mode or target class resolution differs.
- MXBean/CompositeData type mappings differ.
- Naming strategies or auto-configuration pick different ObjectNames.
- Spring Boot Actuator JMX exposure defaults/properties change.
- JVM platform MBeans add attributes or metadata.

Therefore, versioning tests should run not only when management code changes, but also in CI when upgrading Spring, Spring Boot, JDK, or libraries providing MBeans.

Before upgrading:
1. Record MBeanInfo of contracts depended upon by consumers.
2. Run tests on the new runtime.
3. Compare ObjectNames and critical signatures.
4. Check collector/exporter rules.
5. Test Java client proxies and remote serialization.
6. Verify authentication/access if connectors are upgraded.

Do not automatically treat every metadata diff as a bug, but know which changes impact consumers.

## 22. Two-Phase Migration Plan

An actionable process:

### Phase A — Prepare v2

- Define the business/operational goal of the change.
- Classify as additive or breaking.
- Choose v2 ObjectName and new schema if breaking.
- Write a v1 compatibility adapter reading the same state source.
- Check getter costs and side effects.
- Create contract tests for both v1 and v2.
- Update deprecation documentation.

### Phase B — Deploy in parallel

- Deploy v1 and v2 in the same JVM/MBeanServer under distinct names.
- Ensure a single registration owner per name.
- Run JMX exporters or shadow dashboards reading v2.
- Compare values from the same source data, watching for freshness differences.
- Migrate consumers to v2 in waves.
- Monitor AttributeNotFound/ReflectionException errors or missing MBeans.

### Phase C — Retire v1

- Inventory remaining v1 consumers, including infrequently run scripts.
- Announce end-of-support schedule and rollback plan.
- Remove the v1 MBean in a major release or suitable maintenance window.
- Update alerts/metrics to avoid false positives.
- Keep monitoring client errors after deployment.

If there is no way to identify every client (especially JConsole/manual scripts), be cautious when removing v1. Keeping the alias longer may be worthwhile if cost is low and data is non-sensitive.

## 23. Maintaining Compatibility with Metrics Exporters and Dashboards

A JMX exporter may have rules based on ObjectName and attributes:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox
  attribute: PendingCount
  metric: shop_orders_pending
~~~

If ObjectName changes or type switches from a number to CompositeData, the exporter rule may fail to find data or require remapping.

Choose a strategy:
- Keep metric name `shop_orders_pending` if semantics remain unchanged.
- If units/semantics change, consider a new metric name and alert migration.
- Do not add continuously increasing version labels that cause cardinality explosion.
- When exposing both v1 and v2, avoid double-scraping and summing data twice.
- Watch for gaps in time series and alert on missing metrics.

JMX API version and metric name version are two separate layers. You can keep a metric stable across MBean implementation changes if mapping and semantics remain constant.

## 24. Sample Compatibility Matrix

| Consumer | v1 | v2 | Migration |
|---|---|---|---|
| Manual JConsole | Old ObjectName | v2 ObjectName | Notify and provide guide |
| JMX exporter | PendingCount int | PendingCount long | Update rules/types |
| Java proxy client | QueueMonitorV1MBean | QueueMonitorV2MBean | Deploy new client |
| Alert rules | shop_orders_pending | Corresponding metric map | Shadow test before switch |
| Automation pause | pause() | pause() or new operation | Verify signature/security |
| Support scripts | Hardcoded ObjectName | Versioned ObjectName | Release v2 scripts |

Build the matrix from the real system rather than assuming all consumers upgrade simultaneously.

## 25. Rollback and Registration Lifecycle

If v2 fails after deployment, rollback must answer:
- Does the v1 ObjectName still exist?
- Does v1 use the same state source or a separate cache?
- Did any v2 operations mutate state in a backward-incompatible way?
- Do collectors still scrape v1?
- Does Spring context shutdown cleanly unregister managed MBeans?
- Are two exporters competing and using `IGNORE_EXISTING`/`REPLACE_EXISTING`?

A sound migration avoids using registration policies as versioning. `REPLACE_EXISTING` is not a transactional rollback mechanism for MBeans.

If v1 is kept in parallel, consumer rollback is usually simpler: point clients back to the old ObjectName. However, that does not guarantee business data mutated by v2 operations can roll back; examine each operation's behavior.

## 26. Pragmatic Versioning Rules

A project team can adopt:

1. **Never break v1 accidentally.** Every management contract change must be documented.
2. **Add when additive works.** Prefer additive changes while old semantics remain valid.
3. **Change semantics → change name/version.** Especially units and operation behavior.
4. **Keep historical v1 ObjectName.** Do not “beautify” old names during migration.
5. **Do not mix metadata sources.** Each MBean has a clear management contract: interface, MXBean, or annotations.
6. **One owner per registration.** Avoid duplicate exporters.
7. **Test runtime contracts.** Compare MBeanInfo, values, and operation signatures.
8. **Track consumers.** Exporters, scripts, dashboards, alerts, local/remote clients.
9. **Use a deprecation window.** Do not delete legacy endpoints before consumer migration.
10. **Operational safety first.** Operations with side effects and remote JMX access require dedicated review.

## 27. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Client reports AttributeNotFoundException | Attribute renamed | Keep alias or migrate client |
| Client cast Integer to Long fails | Return type changed | Explicit v2 contract and conversion |
| JConsole cannot see MBean | v1 ObjectName changed | Keep legacy name, add v2 name |
| Exporter loses metric | Rule based on old type/name | Update mapping and shadow test |
| Dashboard charts off by 1000x | Changed milliseconds to seconds | New name/units and migration |
| Operation invoke fails | Different parameter signature | Version operation/client |
| Notification listener stops firing | Type/schema changed | Maintain compatibility or migrate subscription |
| MXBean client fails to decode | OpenType schema changed | Test mapping and version schema |
| Two MBeans cause double counting | Both v1/v2 scraped | Exclude one source or define clear rules |
| Rollback fails | v1 removed too early, v2 mutated state | Maintain compatibility window |
| Spring upgrade alters metadata | Different assembler/naming/proxy | Contract tests on new runtime |
| Old operation performs new side effect | Unversioned semantic change | Preserve old behavior, add new operation |

## 28. Hands-on Exercises

### Exercise 1 — Classify Changes

Evaluate these cases: adding `ProcessedCount`; changing `PendingCount` from int to long; renaming `getTimeoutMillis()` to `getTimeoutSeconds()`; adding `clearCache()`; editing a description. Classify as additive, breaking, or needing security review.

### Exercise 2 — Design v1/v2 ObjectNames

V1 currently uses `com.example.shop.orders:type=QueueMonitor,name=outbox`. Create a v2 ObjectName without changing the v1 name. Write a JMX client capable of reading both during the migration window.

### Exercise 3 — Metadata Contract Tests

Create a JUnit integration test verifying v1 attribute `PendingCount` is `int` and v2 is `long`; ensure old operations remain present on v1 and no internal operations are exposed.

### Exercise 4 — Metrics Exporter Migration

An exporter rule uses the old ObjectName and PendingCount. Propose a rule for v2, a way to prevent duplicate scraping, and a plan for migrating alerts.

### Exercise 5 — Notification Compatibility

A listener filters on type `queue.threshold.exceeded`. Propose a migration when v2 wants type `queue.backlog.high`. Highlight the risk of emitting two notifications and triggering duplicate actions.

### Exercise 6 — Rollback

Simulate a v2 getter mapping failure. Describe how clients fall back to v1, which ObjectNames must remain, and which tests run before and after rollback.

## 29. Self-Check

**1. Is renaming an attribute while the Java service still compiles a JMX breaking change?** Yes, clients reading the old name may hit AttributeNotFoundException.

**2. Is adding a new attribute always completely compatible?** Usually additive, though rigid-schema clients might reject it; verification is still needed.

**3. Why does changing int to long require versioning?** JMX runtime types change, and Java proxies/casts and exporter mappings may mismatch.

**4. Can `version=v1` be added to the old ObjectName immediately?** Not if clients hard-code the unversioned name; keep the alias/legacy name.

**5. Is REPLACE_EXISTING a safe versioning mechanism?** No. It only handles registration conflicts and can overwrite the old contract.

**6. Is MBeanInfo enough to guarantee semantic compatibility?** No. Tests are needed for values, units, side effects, and data freshness.

**7. Does MXBean make every custom DTO automatically portable?** No. Types must satisfy open-type mapping and schema rules.

**8. Should notification types be versioned?** It may be necessary if event/schema changes; old listeners could otherwise miss them.

## 30. Key Takeaways

- **A management interface is an operational API with real consumers.**
- Backward compatibility covers names, types, signatures, ObjectName, units, semantics, security, and lifecycle.
- Additive changes are usually easier to keep compatible than breaking changes.
- For breaking changes, keeping v1 and publishing v2 under a different ObjectName is a controllable strategy.
- Do not change historical ObjectNames merely to add a version key.
- Do not use registration policies as a substitute for a migration plan.
- Verify MBeanInfo and invoke real attributes/operations in tests.
- Monitor JMX exporters, dashboards, alert rules, and scripts when changing contracts.
- Plan deprecation, migration, rollback, and only then retire v1.
- For operations with side effects, semantic changes can be more dangerous than signature changes.

## 31. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — StandardMBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Java SE 21 — MXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html

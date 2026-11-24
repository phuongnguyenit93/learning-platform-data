# Changing ObjectName and Its Impact on Dashboards or Scripts in Spring Framework JMX

## 1. Why Can Renaming an MBean Cause Operational Failures?

In Java Management Extensions (JMX), each MBean is registered in an `MBeanServer` under an `ObjectName`. This is the identifier that JMX clients use to locate the MBean, read attributes, invoke operations, and register notification listeners.

An ObjectName has the form:

```text
domain:key=value,key2=value2
```

For example:

```text
company.orders:type=QueueMonitor,name=primary
```

If a new version renames it to:

```text
company.orders:type=QueueMonitor,name=orders
```

the Java MBean may still work, the Spring context may start successfully, and JConsole will still display the monitor, but tools configured with the old ObjectName may no longer find the target. Dashboards become empty, alerts stop updating, JMX exporters stop collecting metrics, or scripts throw `InstanceNotFoundException`.

**Changing an ObjectName is a JMX management contract change**, not just an internal rename in source code. This lesson shows how to determine the impact scope, design a compatibility policy, execute migration, and verify using the JMX API.

## 2. Distinguishing ObjectName, Spring Bean Name, and Java Class

A resource has at least three names:

| Concept | Example | Scope |
|---|---|---|
| Java class | `com.example.monitor.QueueMonitor` | Type inside the JVM |
| Spring bean name | `ordersQueueMonitor` | `ApplicationContext` / `BeanFactory` |
| JMX ObjectName | `company.orders:type=QueueMonitor,name=primary` | An `MBeanServer` |

These three names are not automatically identical. A Spring bean name can change while the ObjectName stays the same via explicit mapping; conversely, an ObjectName can change without changing the Java class or Spring bean name.

For example:

```java
exporter.setBeans(Map.of(
    "company.orders:type=QueueMonitor,name=primary",
    ordersQueueMonitor
));
```

In this configuration, the key is the JMX ObjectName. Changing the key to `name=orders` changes the MBean's address from the client's perspective.

If using `@ManagedResource(objectName = "...")`, the ObjectName can be declared directly on the bean. If using `ObjectNamingStrategy`, the effective name can be generated from configuration, bean type, bean name, or other values. With Spring Boot Actuator JMX, endpoints also have their own domain/naming convention.

**What needs to be verified is the actual registered ObjectName**, not just the annotation or bean name in the IDE.

## 3. ObjectName Is Part of the Management API

A JMX client typically calls:

```java
ObjectName name = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);

Object depth = connection.getAttribute(name, "QueueDepth");
```

If the server renames it to `name=orders` while the client still uses `name=primary`, the call can fail because the old name is no longer registered.

The constraints are like an API contract:

- **Domain name**: `company.orders`.
- **Key properties**: `type`, `name`, `instance`, `service`, etc.
- **Key values**: `primary`, `orders`, `worker-1`.
- **Attributes/operations** under that ObjectName.
- **Notification subscriptions** registered against the source.
- **Access permissions** may depend on domain/ObjectName in environments with fine-grained policies.

A small change in any component can cause selectors or queries to stop matching.

### 3.1. Difference Between Key Order and Key Values

Two ObjectNames:

```text
company.orders:type=QueueMonitor,name=primary
company.orders:name=primary,type=QueueMonitor
```

have the same domain and key/value set, so they represent the same ObjectName under JMX rules. The order of key properties does not change identity. You can use `ObjectName.getCanonicalName()` to produce a stable form for comparison.

Conversely:

```text
company.orders:type=QueueMonitor,name=primary
company.orders:type=QueueMonitor,name=orders
```

are two different names because the value of `name` differs.

Do not use raw string comparison to conclude that two ObjectNames differ simply because the key order changed; parse them into `ObjectName` and compare or canonicalize them.

## 4. Places Most Likely Affected by an ObjectName Change

The impact often goes far beyond JConsole:

| Component | How it depends on ObjectName | Symptom on rename |
|---|---|---|
| JConsole script or Java JMX client | `new ObjectName("...")` | `InstanceNotFoundException` |
| JMX monitoring exporter | Include rules by domain/properties | Metrics disappear from collector |
| Dashboard | Metric/label generated from ObjectName | "No data" panels, new series |
| Alert rule | Queries old metric | Silent alerts or false positives |
| Automation script | `invoke` on a fixed ObjectName | Admin jobs fail to run |
| Notification listener | Registered with a specific ObjectName | Stops receiving notifications from new MBean |
| Access policy | Permissions by name/domain | Client denied after migration |
| Inventory or audit | ObjectName allowlist | "Unknown" resource appears, old name missing |
| Integration test | Expected ObjectName | Registration test fails |

**Sometimes the biggest risk is silent failure:** the monitoring exporter may collect zero metrics without crashing the Spring application. An empty dashboard may be mistaken for "no errors", when in reality no data is arriving.

## 5. Dependency of Dashboards and Metric Pipelines

A common metrics flow:

```text
MBeanServer
    |
    | ObjectName + attribute
    v
JMX collector / exporter
    |
    | metric name + labels
    v
Monitoring backend
    |
    +--> Dashboard panel
    +--> Recording rule
    +--> Alert rule
```

There are at least two kinds of dependencies:

1. **The collector selects ObjectNames using a selector.** If the selector no longer matches, metrics are not emitted.
2. **The collector generates metric labels or metric names from the ObjectName.** After renaming, the metric may still exist but under a new label/name; the old dashboard still loses data.

For example, a JMX exporter rule designed for:

```text
company.orders<type=QueueMonitor,name=primary><>QueueDepth
```

After the name changes to `name=orders`, a rule matching `primary` exactly will stop matching. Actual rule syntax depends on the exporter; the line above illustrates a pattern style, not a universal configuration.

Therefore, do not just check that `queryNames` sees the new MBean. Check the metrics emitted by the collector, the actual labels, and the dashboard/alert queries as well.

## 6. Impact on Alerts: Missing Data Is Not Zero

Suppose a dashboard monitors queue depth:

```text
old ObjectName -> queue_depth{queue="primary"} = 120
```

After renaming, the collector may fail to scrape the old series:

```text
queue_depth{queue="primary"} -> absent / stale
```

This is **not equivalent to `queue_depth=0`**. If alerts treat missing data as normal state, an overloaded queue may go unalerted.

Alert rules should distinguish between:

- Actual measured values.
- Missing/stale metrics.
- Exporter unavailable.
- JMX target not yet READY.
- Collector scrape failures.
- Rename in progress during migration.

When changing an ObjectName, include "metrics presence" or collector health checks, not just threshold alerts like `QueueDepth > 100`.

## 7. Impact on Scripts and Spring Proxies

A script might hard-code:

```java
ObjectName monitor = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);

connection.invoke(
    monitor,
    "resetCounters",
    new Object[0],
    new String[0]
);
```

After renaming, the operation may throw `InstanceNotFoundException` or an equivalent error. If the script retries indefinitely, it only generates logs and unnecessary load.

A Spring client proxy can also bind a fixed ObjectName:

```java
MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
proxy.setServer(connection);
proxy.setObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);
proxy.setProxyInterface(QueueManagementMBean.class);
```

The proxy may be created, but the first call to the old name fails. **Successfully creating a proxy does not prove the target ObjectName still exists.**

Client/proxy configuration and accompanying integration tests should be updated in the migration plan, rather than only changing server annotations.

## 8. Impact on NotificationListener

JMX listeners register using an ObjectName:

```java
connection.addNotificationListener(
    oldName,
    listener,
    filter,
    handback
);
```

When the MBean is unregistered and re-registered under a new name, the old registration does not automatically follow the new resource.

In Spring, a `NotificationListenerBean` can also use:

```java
listenerBean.setMappedObjectNames(
    "company.orders:type=QueueMonitor,name=primary"
);
```

After renaming, the mapping must be updated or a strategy must support both names during the transition period.

JMX Notifications are not inherently durable queues. If a listener has not registered with the new name yet, emitted notifications may not be replayed. When migration affects critical alerts, it may be necessary to read current state via attributes after re-registering to avoid losing detection.

## 9. Impact on Policies, Permissions, and Allowlists

Some systems use domain/ObjectName in access policies or monitoring allowlists. When renaming:

```text
Allowed:
  company.orders:type=QueueMonitor,name=primary

New:
  company.orders:type=QueueMonitor,name=orders
```

The old policy may no longer apply. There are two directions of risk:

- Clients lose read/invoke permissions even though they should be authorized.
- Overly broad policies or fallback permissions grant unintended access.

You must test the actual authorization of the JMX connector/server, not just verify that username/password login still works. A successful connection does not prove permission to invoke attributes or operations after renaming.

Do not resolve this by granting full permissions across the entire domain just to make scripts work. Update targeted rules deliberately and test with identities that have the proper permissions.

## 10. Strategy 1: Keep ObjectName Stable

The lowest-migration-cost approach is to **not change the ObjectName** even when the application internals are refactored.

For example, the class and bean are renamed:

```java
@ManagedResource(
    objectName = "company.orders:type=QueueMonitor,name=primary"
)
public class OrdersRuntimeStatus {
    // ...
}
```

The JMX ObjectName remains as before. Clients can continue working if attributes/operations also stay compatible.

This is a good approach when:

- The old ObjectName is already used by many dashboards/scripts.
- The old name does not cause collisions or security issues.
- The change is purely internal refactoring.
- There is no need to distinguish additional new instances.

Treat ObjectName as a stable external identifier. Java classes can be renamed; ObjectName does not have to reflect the current class name.

### When Keeping the Same Name Is No Longer Suitable

If the old ObjectName causes collisions across modules, contains sensitive information, or cannot distinguish instances, it may need to change. In that case, use a clear migration strategy instead of changing it abruptly in a single commit.

## 11. Strategy 2: Support Old and New Names in Parallel

When changing the ObjectName is necessary, a transition period can register **two ObjectNames** so old and new clients have time to update.

```text
OLD:
company.orders:type=QueueMonitor,name=primary

NEW:
company.orders:type=QueueMonitor,name=orders
```

Both names should point to the same management state or facades with consistent behavior, so dashboards do not report conflicting numbers.

Avoid assuming you can register **the exact same MBean instance** under two ObjectNames in every case. Some implementations, lifecycles, or notification sources may have their own registration constraints. A controllable approach is to create two thin MBean facades that both read from a shared state holder/service.

```text
        QueueRuntimeState
           /        \
          /          \
 LegacyMonitor    CurrentMonitor
       |               |
  ObjectName OLD    ObjectName NEW
       |               |
   old clients      new clients
```

If both facades have state-mutating operations, determine whether callers could execute the operation twice across the two names. During transition, prefer making the legacy name read-only if possible and keeping control operations on a single name.

### 11.1. Do Not Double-Count Metrics

If the collector scrapes both OLD and NEW, it can produce two series for the same metric. Careless aggregation will double-count.

For example, both ObjectNames report `CompletedTotal=500`:

```text
old monitor -> 500
new monitor -> 500
```

A dashboard `sum(...)` across both would show 1000 even though the business only completed 500 tasks.

During the parallel period, configure the collector/recording rules to pick only one source as primary for each logical metric; legacy series can exist for compatibility without being added into the same total.

## 12. Strategy 3: Client Discovery Instead of Hard-Coding

If the system has multiple instances, an ObjectName pattern can be used:

```java
Set<ObjectName> matches = connection.queryNames(
    new ObjectName("company.orders:type=QueueMonitor,*"),
    null
);
```

The client then selects a target based on key properties such as `service`, `instance`, or `role`.

Discovery reduces coupling to a hard-coded name, but comes with conditions:

1. The pattern must be narrow enough not to match unintended MBeans.
2. If there are multiple matches, the client must select one intentionally.
3. Do not automatically invoke operations on all matches if they have side effects.
4. Handle targets appearing/disappearing at runtime.
5. Perform version/contract checks via `MBeanInfo`.
6. Do not use discovery as a substitute for authorization.

If an `MBeanProxyFactoryBean` requires a specific target ObjectName, you still must select one ObjectName after discovery and configure the proxy accordingly. A query pattern is not itself a single MBean for a proxy to call.

## 13. Strategy 4: Version the JMX Contract

For changes involving not only ObjectName but also attributes/operations, a versioning policy can be helpful:

```text
company.orders:type=QueueMonitor,version=v1,name=primary
company.orders:type=QueueMonitor,version=v2,name=primary
```

Or:

```text
company.orders.v1:type=QueueMonitor,name=primary
company.orders.v2:type=QueueMonitor,name=primary
```

There is no single standard for placing versions in an ObjectName. What matters is choosing a consistent, documented convention.

A new version should have a clear contract:

- Which attributes exist and what are their types?
- Which writable attributes are allowed to change?
- Which operations change signatures?
- Do notification types/payloads change?
- How will the ObjectName be kept stable throughout the version's lifecycle?

If only refactoring implementation without changing the contract, creating a new version may be unnecessary. Versioning should not make ObjectNames needlessly long or hard to manage.

## 14. Phased Migration Process

A safe process includes:

### Phase A — inventory dependencies

Find all references to the old ObjectName:

- Java JMX clients, shell scripts, and maintenance tools.
- JMX collector/exporter configurations.
- Dashboard panels, alerts, recording rules.
- Spring `MBeanProxyFactoryBean` configurations.
- `NotificationListenerBean.mappedObjectNames`.
- Access policies, inventories, and test fixtures.
- Operational runbooks.

Record each consumer's owner, usage frequency, permissions, and criticality.

### Phase B — define the new contract

Decide the new name, reason for change, MBeanServer scope, and compatible attributes/operations. Determine the transition approach: keep the old name, parallel alias, or cutover with downtime.

### Phase C — implement dual registration or compatibility adapter

If needed, register legacy and current facades. Verify they reflect the same accurate state. Do not let two exporters contend for the same ObjectName or create duplicate side effects.

### Phase D — update consumers

Update selectors in collectors, dashboards, alerts, scripts, and proxies. Run end-to-end checks in staging. Specifically verify alerts when metrics go missing.

### Phase E — observe and deprecate

During the transition period, check which consumers still read the old name. Not every JMX server provides detailed per-getter auditing; you may need client logs, monitoring configuration inspection, or access gateway logs to infer usage.

### Phase F — intentionally remove the old name

Remove the legacy MBean only once consumers have migrated, permissions are updated, and a rollback plan is in place. After removal, verify no dashboards/scripts still depend on the old name.

## 15. Java Example: Inspecting MBeanInfo Before and After Renaming

Define the two ObjectNames:

```java
ObjectName oldName = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);
ObjectName newName = new ObjectName(
    "company.orders:type=QueueMonitor,name=orders"
);
```

Check existence:

```java
boolean oldPresent = server.isRegistered(oldName);
boolean newPresent = server.isRegistered(newName);

System.out.printf(
    "old=%s new=%s%n",
    oldPresent, newPresent
);
```

Check the contract:

```java
if (newPresent) {
    MBeanInfo info = server.getMBeanInfo(newName);

    for (MBeanAttributeInfo attr : info.getAttributes()) {
        System.out.printf(
            "%s type=%s read=%s write=%s%n",
            attr.getName(),
            attr.getType(),
            attr.isReadable(),
            attr.isWritable()
        );
    }

    for (MBeanOperationInfo op : info.getOperations()) {
        System.out.println(
            "operation=" + op.getName()
        );
    }
}
```

Required types are imported from `javax.management`. This code must run against the **correct MBeanServer**; using the client JVM's local platform server will not inspect a remote server if the target is in another JVM.

Do not automatically invoke every operation during migration: an operation might restart a service, clear a cache, or mutate data. Metadata inventory is the appropriate verification step first.

## 16. Spring Example: Explicit ObjectName for Stability

Instead of relying on bean/class names:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class StableJmxConfiguration {

    @Bean
    public QueueStatusMonitor queueStatusMonitor() {
        return new QueueStatusMonitor();
    }

    @Bean
    public MBeanExporter exporter(
            MBeanServer server,
            QueueStatusMonitor monitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "company.orders:type=QueueMonitor,name=primary",
            monitor
        ));
        return exporter;
    }
}
```

`QueueStatusMonitor` must be a JMX-compliant MBean or configured with an appropriate assembler. When the class is refactored, the mapping preserves the old ObjectName.

If you later want to change to `name=orders`, follow a migration plan rather than just changing the value in `Map.of` and deploying.

## 17. Example Supporting Legacy and Current via Facades

A state holder:

```java
import java.util.concurrent.atomic.AtomicLong;

public class QueueRuntimeState {
    private final AtomicLong processed = new AtomicLong();

    public long getProcessed() {
        return processed.get();
    }

    public void recordProcessed() {
        processed.incrementAndGet();
    }
}
```

Management interface:

```java
public interface QueueMonitorMBean {
    long getProcessedTotal();
}
```

Two distinct facades can use a `StandardMBean` wrapper or appropriate management interface:

```java
public class QueueMonitorView implements QueueMonitorMBean {
    private final QueueRuntimeState state;

    public QueueMonitorView(QueueRuntimeState state) {
        this.state = state;
    }

    @Override
    public long getProcessedTotal() {
        return state.getProcessed();
    }
}
```

Because the class name `QueueMonitorView` does not automatically match the `QueueMonitorViewMBean` convention, it can be registered with a `StandardMBean` wrapper when using plain JMX:

```java
QueueRuntimeState state = new QueueRuntimeState();

StandardMBean legacy = new StandardMBean(
    new QueueMonitorView(state),
    QueueMonitorMBean.class
);

StandardMBean current = new StandardMBean(
    new QueueMonitorView(state),
    QueueMonitorMBean.class
);

server.registerMBean(legacy, oldName);
server.registerMBean(current, newName);
```

Required imports:

```java
import javax.management.StandardMBean;
import javax.management.ObjectName;
```

Two separate wrappers reading from the same state holder avoid unexpectedly registering a single MBean instance twice. In Spring, you can use two facade beans and separate `MBeanExporter` mappings with an appropriate assembler.

This is one specific compatibility strategy, not a requirement that every application use dual registration. If the old name has only a few consumers and a coordinated cutover is possible, keeping one name and updating clients simultaneously can be simpler.

## 18. Changing ObjectName via Annotation in Spring

An annotation-based bean:

```java
@ManagedResource(
    objectName = "company.orders:type=QueueMonitor,name=primary"
)
public class QueueMetrics {
    @ManagedAttribute
    public long getProcessedTotal() { /* ... */ }
}
```

If you change the annotation to:

```java
@ManagedResource(
    objectName = "company.orders:type=QueueMonitor,name=orders"
)
```

the exporter may register the MBean under the new name when the context re-initializes. That does not automatically create an alias for the old name.

If the application uses `@EnableMBeanExport` or Spring Boot JMX auto-configuration, identify which exporter owns the resource and avoid configuring a duplicate exporter during migration.

ObjectName can be overridden by a naming strategy or explicit mappings depending on how exporting is configured. Therefore, inspect `queryNames` after startup rather than merely assuming the new annotation took effect.

## 19. Common Misconceptions

### 19.1. “Changing ObjectName doesn't change Java methods, so clients aren't affected”

False. Clients use ObjectName to locate the MBean before accessing methods. Changing the name can cause clients not to find the resource.

### 19.2. “Changing key property order creates a new ObjectName”

Not necessarily. With the same domain and the same key/value set, ObjectName canonicalization expresses equivalent identity.

### 19.3. “An empty dashboard means QueueDepth is 0”

No. The metric may be missing/stale because the collector no longer matches the ObjectName. You must distinguish missing data.

### 19.4. “Updating the Spring server configuration is enough”

No. Client proxies, listeners, collectors, dashboards, alerts, scripts, and access policies may still hold the old name.

### 19.5. “Just registering the same object twice supports backward compatibility”

Do not assume this by default. Lifecycle and notification behavior can be tricky. Separate facades/wrappers sharing a state holder are usually easier to control.

### 19.6. “Two MBeans with the same metric will still keep dashboards accurate”

There is a risk of double counting. Collectors and aggregations must designate a primary source during dual registration.

### 19.7. “Querying an ObjectName pattern is enough to avoid all breaking changes”

A pattern can match multiple different resources or miss contract drift. You must select the target and verify `MBeanInfo`.

### 19.8. “The legacy alias can be removed as soon as the new code deploys”

Not all clients, cron jobs, and monitoring configurations may have updated yet. Verify dependencies and use an appropriate deprecation window.

## 20. Compatibility Testing in CI/CD

A test can create a Spring context and query expected ObjectNames:

```java
ObjectName oldName = new ObjectName(
    "company.orders:type=QueueMonitor,name=primary"
);

assertTrue(server.isRegistered(oldName));
```

When transitioning to a new name, expand the test to check both during migration:

```java
assertTrue(server.isRegistered(oldName));
assertTrue(server.isRegistered(newName));
```

After deprecation, update the test to expect the new name and verify the old name is gone. Tests should run with an isolated MBeanServer or dedicated ObjectName planning so they do not depend on resources from other JVMs/tests.

Beyond registration, also test:

- Attribute and operation signatures remain valid under the new name.
- No secrets or unintended operations are exported.
- Listeners can register against the new name.
- The metrics collector actually emits the expected series.
- Dashboard queries and alert rules can find the corresponding series.
- Admin accounts have the proper permissions.
- Context shutdown cleanup leaves no orphaned MBeans.

**Testing the Spring context alone is not enough for the metrics pipeline:** at least one end-to-end check in staging is needed to confirm the exporter, labels, and dashboards/alerts under actual configuration.

## 21. Troubleshooting Incidents After a Rename

If JConsole sees the new MBean but the dashboard has no data, check in order:

1. **Right JVM/MBeanServer?** Are JConsole and the collector connected to the same target?
2. **MBean registered?** Does `queryNames` include the new ObjectName?
3. **Metadata correct?** Does `MBeanInfo` contain the attributes read by the collector?
4. **Collector rule matching?** Does the rule still use the old domain/name?
5. **Scrape succeeding?** Does the collector have query/permission errors?
6. **Metric name/labels changed?** Does the backend have a new series while the panel still queries the old series?
7. **Alert behavior?** Is missing data being treated as OK?
8. **Dual registration?** Is there double counting or ambiguous labels?
9. **Access control?** Have permissions for the new ObjectName been granted?
10. **Caching/restart?** Does the collector or JMX client need to reload configuration/reconnect?

If an automation script fails:

```text
InstanceNotFoundException
  -> check the actual ObjectName
  -> check environment/instance
  -> update script per migration plan

AttributeNotFoundException
  -> ObjectName may be right but contract changed
  -> inspect MBeanInfo attributes

ReflectionException / MBeanException
  -> check operation signature and runtime target
```

Do not automatically replace ObjectName with a broad wildcard just to "get data" if the script executes operations with side effects.

## 22. Rollback Runbook When Renaming Breaks Monitoring

If severe telemetry loss occurs after deployment:

1. Confirm the issue lies in ObjectName/collector rules rather than MBeanServer or network.
2. If dual registration exists, temporarily keep the legacy name and switch collectors to the appropriate primary source.
3. If legacy was already removed, consider rolling back configuration/version or adding a controlled compatibility facade.
4. Synchronize dashboards, recording rules, and alerts so missing data is not mistaken for healthy.
5. Verify metrics/alerts recover with real data, not just that the application starts.
6. Record missed consumers to update the inventory and migration checklist.

Do not use `REPLACE_EXISTING` as a blind rollback mechanism when ownership of the MBean is unclear. That can accidentally replace another module's resource.

## 23. Hands-on Exercises

**Exercise 1 — Rename and script failure.** Register `QueueMonitor` at the old ObjectName. Write a JMX client reading `ProcessedTotal`. Change the registration to the new name while keeping the old client, observe `InstanceNotFoundException`, then update the client.

**Exercise 2 — Canonical ObjectName.** Create two `ObjectName` instances with the same keys/values in different orders; compare `equals` and `getCanonicalName()`. Then change the `name` value and explain the difference.

**Exercise 3 — Dashboard selector.** Write a hypothetical collector configuration matching only `name=primary`. Rename to `name=orders` and explain why the metric disappears. Design a rule fix or dual-collection phase.

**Exercise 4 — Dual facade.** Create two MBean wrappers sharing the same state holder. Register under old/new ObjectNames, read the same counter, and explain why the two series must not be summed together.

**Exercise 5 — Notification migration.** Register a listener on the old ObjectName, move the source to the new name. Verify the listener does not follow automatically, then update the mapping.

**Exercise 6 — Access policy.** In a test environment with JMX authorization, verify an account can read the old name but cannot read the new name. Update the policy deliberately without opening the entire domain.

**Exercise 7 — Integration test.** Create a Spring context with an exporter and an MBean. Assert ObjectName, MBeanInfo, and attributes. Change the name and adjust tests for each migration phase.

**Exercise 8 — Missing-data alert.** Design an alert for when the `queue_depth` metric disappears from the backend, distinguishing it from `queue_depth=0`. Describe how to verify the alert works in staging.

## 24. Self-Check Questions

1. What is the scope of an ObjectName and what is it used for?
2. Does changing a Spring bean name necessarily change its ObjectName?
3. Are two ObjectNames differing only in key order two different MBeans?
4. Why might JConsole show the new MBean while dashboards still lose data?
5. How does a missing metric differ from a zero value?
6. Which consumers besides Java JMX clients depend on ObjectName?
7. Why does dual registration carry a risk of double counting?
8. When should the old ObjectName be kept even though the implementation was refactored?
9. Why should `queryNames` with broad patterns not be used to invoke bulk operations?
10. What steps are needed before removing a legacy ObjectName?
11. How can access policies be affected after renaming?
12. How do you verify end-to-end that a migration succeeded?

## 25. Key Takeaways

**ObjectName is part of the JMX management API.** Changing the domain or key/values can break Java clients, Spring proxies, notification listeners, monitoring exporters, dashboards, alerts, and automation scripts even when the MBean registers normally under the new name.

Prefer keeping ObjectName stable when only refactoring internals. If a change is unavoidable, inventory consumers, choose a compatibility strategy, update selectors/permissions, verify MBeanInfo and end-to-end telemetry, manage a deprecation window, and remove the legacy name only after confirming no dependencies remain.

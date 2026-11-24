# Stable Identity Across Restarts in JMX ObjectName

## Objectives

After this lesson, you will be able to design a stable `ObjectName` for a managed resource across multiple JVM restarts; distinguish logical identity from per-run session state; avoid using random values, memory addresses, and initialization order in MBean names; and apply consistent naming conventions when exporting MBeans with Spring Framework.

## 1. ObjectName Is the Identity of an MBean

In JMX, each MBean is registered in an `MBeanServer` under a `javax.management.ObjectName`. The name has the structure:

```text
domain:key1=value1,key2=value2,...
```

Examples:

```text
com.example.orders:type=Queue,name=PaymentQueue
com.example.orders:type=ConnectionPool,name=Primary
com.example.orders:type=Worker,group=Billing,name=Retry
```

An `ObjectName` has two parts: a **domain** and a set of **key properties**. The domain partitions the namespace; the key properties specify the type and concrete identity of the MBean.

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=PaymentQueue"
);
System.out.println(name.getDomain());
System.out.println(name.getKeyProperty("type"));
System.out.println(name.getKeyProperty("name"));
System.out.println(name.getCanonicalName());
```

An `ObjectName` distinguishes MBeans **within the scope of one MBeanServer**. Two JVMs can register the exact same `ObjectName` string independently. When accessing remotely, full identity usually must include both the connection endpoint/instance and the JMX name inside it.

## 2. What Does "Stable Across Restarts" Mean?

Suppose an application operates a queue with logical identity `PaymentQueue`. The JVM starts first at 09:00, and then restarts at 10:00. If the queue is still the same managed resource, clients should find:

```text
com.example.orders:type=Queue,name=PaymentQueue
```

in both runs.

**Stability** means the naming rule relies on intentional logical attributes that exist independently of the lifetime of a single Java object:

- A fixed service name or management domain.
- The resource type: `Cache`, `Queue`, `ConnectionPool`, `Scheduler`.
- The logical resource name from managed configuration.
- A persistent tenant or partition identifier when that is genuinely part of the contract.

The name does not require the same Java object to survive across a restart: the old instance ended and a new instance was created. What must remain stable is **the path by which management systems recognize the same role or resource**.

Unstable examples:

```text
com.example.orders:type=Queue,id=6d77b62c-5e...
com.example.orders:type=Queue,createdAt=20261111T090000
com.example.orders:type=Queue,identityHash=18273645
com.example.orders:type=Queue,thread=worker-17
```

Newly generated UUIDs, startup timestamps, `System.identityHashCode`, thread names, PIDs, random ports, registration order, or collection indices all easily change after a restart. Clients have to continuously rediscover names, dashboards lose historical series, or alerts fail to locate the target object.

## 3. Logical Identity and Run-Session Data Must Be Separated

An MBean has many values that vary over time, yet these variations **do not belong in the ObjectName**.

| Property | Should It Be in ObjectName? | Example |
| --- | --- | --- |
| Resource type | Yes | `type=Queue` |
| Stable configured queue name | Yes | `name=PaymentQueue` |
| Stable cluster/tenant name when distinction is needed | Depends on requirements | `tenant=Retail` |
| JVM start time | Usually no | Attribute `StartTimeMillis` |
| Current PID | Usually no | Attribute `ProcessId` |
| Number of in-flight requests | No | Attribute `ActiveRequests` |
| `RUNNING/STOPPED` status | No | Attribute `State` |
| New UUID run-session ID per restart | No | Attribute `RunId` |

Example:

```java
public interface QueueMonitorMBean {
    String getState();
    int getPendingCount();
    long getStartTimeMillis();
    String getRunId();
}
```

The `ObjectName` stays `com.example.orders:type=Queue,name=PaymentQueue`, while the `RunId` and `StartTimeMillis` attributes tell operators that this is a new run session.

If tools need to detect a restart, inspect `RunId` or `StartTimeMillis`, uptime, JMX connection lifecycle, or counter resets. Keeping the same `ObjectName` does **not** mean counters or notification sequence numbers remain continuous across restarts.

## 4. Building ObjectName from Stable Configuration Values

A good rule is to centralize name-building logic in one place and pass identity components from trusted configuration or business metadata.

```java
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String logicalName)
            throws MalformedObjectNameException {
        return new ObjectName(
            "com.example.orders",
            java.util.Hashtable.of() // illustrative notation only, see implementation below
        );
    }
}
```

In actual Java, `Hashtable` does not have an `of()` factory; implement it explicitly as follows:

```java
import java.util.Hashtable;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName queue(String logicalName)
            throws MalformedObjectNameException {
        if (logicalName == null || logicalName.isBlank()) {
            throw new IllegalArgumentException("logicalName is required");
        }

        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("type", "Queue");
        properties.put("name", logicalName);
        return new ObjectName("com.example.orders", properties);
    }
}
```

Example:

```java
ObjectName objectName = JmxNames.queue("PaymentQueue");
```

Use the constructor with `Hashtable<String,String>` so JMX handles property value structure via the API; when building strings manually, use `ObjectName.quote(value)` for values needing escaping:

```java
String logicalName = "Billing,HighPriority";
ObjectName objectName = new ObjectName(
    "com.example.orders:type=Queue,name=" + ObjectName.quote(logicalName)
);
```

Do not concatenate untrusted input directly into a JMX name template: commas, equals signs, colons, asterisks, or question marks have special meaning in `ObjectName` syntax. Also constrain the length and character set of logical names to avoid creating an unbounded number of MBeans.

## 5. An MBean Registration with a Clear Lifecycle

Here is a simple Standard MBean example:

```java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void setPaused(boolean paused);
}
```

```java
public final class QueueMonitor implements QueueMonitorMBean {
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return 12;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void setPaused(boolean paused) {
        this.paused = paused;
    }
}
```

Registration and unregistration:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class QueueJmxRegistration implements AutoCloseable {
    private final MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();
    private final ObjectName name;

    public QueueJmxRegistration(String logicalName) throws Exception {
        this.name = JmxNames.queue(logicalName);
        server.registerMBean(new QueueMonitor(), name);
    }

    public ObjectName getObjectName() {
        return name;
    }

    @Override
    public void close() throws Exception {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
    }
}
```

Usage within the application lifecycle:

```java
try (QueueJmxRegistration registration =
         new QueueJmxRegistration("PaymentQueue")) {
    System.out.println(registration.getObjectName());
    // Run the application/queue resource...
}
```

After a restart, the `PaymentQueue` configuration produces the exact same `ObjectName`. Within a single JVM, registering two MBeans concurrently with the same name throws `InstanceAlreadyExistsException`: that signals an identity collision or lifecycle management bug that must be fixed, not solved by automatically appending a UUID.

Before re-registering in the same JVM, determine who owns the existing MBean. Never blindly call `unregisterMBean` on another component's MBean just to reclaim the name.

## 6. Multiple Instances of the Same Application

An important scenario: three replicas of a service all run the `PaymentQueue` queue.

```text
Replica A -> com.example.orders:type=Queue,name=PaymentQueue
Replica B -> com.example.orders:type=Queue,name=PaymentQueue
Replica C -> com.example.orders:type=Queue,name=PaymentQueue
```

This **does not collide** if each replica has its own `MBeanServer`. However, a centralized dashboard must distinguish replicas using endpoint identifiers or deployment metadata, for example:

```text
(cluster=production, service=orders, instance=orders-0,
 ObjectName=com.example.orders:type=Queue,name=PaymentQueue)
```

There are two strategies:

### A. ObjectName Represents Only the Resource Within Each JVM

Keep the name simple and let the monitoring/collector attach endpoint or service-instance labels during scraping. This works well when each JVM has its own namespace and the observability platform already manages target identity.

### B. ObjectName Carries a Persistent Instance Identifier

```text
com.example.orders:type=Queue,name=PaymentQueue,instance=orders-0
```

Only appropriate if `orders-0` is genuinely a stable ID under the deployment contract (such as a preserved StatefulSet ordinal name). If running a Deployment with random pod names on every rollout, the pod name is not a persistent identifier. When instances lack persistent identities, keep local names stable and let the collector distinguish targets with appropriate labels.

Do not mix "name of the same logical role" with "process identity" when operational goals require aggregating metrics across replicas.

## 7. Canonical Name and Key Property Order

The following two strings represent the same set of key properties:

```text
com.example.orders:type=Queue,name=PaymentQueue
com.example.orders:name=PaymentQueue,type=Queue
```

By `ObjectName` semantics, key property order does not alter identity. If you need a canonical string for storing, comparing, or logging, use `getCanonicalName()`, because the canonical form sorts key properties in a deterministic order.

```java
ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=PaymentQueue"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=PaymentQueue,type=Queue"
);

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
```

Do not build a naming system that relies on `HashMap` property iteration order or string serialization order; treat `ObjectName` as a value type.

**Key distinction:** canonicalization stabilizes the representation of **the same identity**. It cannot turn a name containing a random UUID, port, or PID into a persistent identity.

## 8. Spring Framework JMX and Stable Naming Strategies

In Spring, `MBeanExporter` manages registering beans into JMX. You can specify an `ObjectName` via annotations or explicit registration mappings:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=PaymentQueue",
    description = "Payment queue monitor"
)
public class PaymentQueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

When one service has multiple queues, avoid hardcoding the same `ObjectName` on every bean. Use configuration or a consistent naming mechanism and map each resource to a deterministic identity.

Example of registering via `MBeanExporter` with a `beans` map:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public MBeanExporter queueMBeanExporter(PaymentQueueMonitor monitor) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=PaymentQueue", monitor
        ));
        return exporter;
    }
}
```

This is an illustrative configuration for an explicit exporter; real applications should choose one consistent registration mechanism and avoid registering the same bean twice through both an automatic exporter and a manual exporter. If using Spring Boot, how JMX auto-configuration and exporters are enabled also depends on the Spring Boot version and application configuration.

For dynamic identities, build the `ObjectName` using an `ObjectNamingStrategy` or a central factory that receives stable IDs from configuration. Spring's lifecycle allows the exporter to register MBeans on context startup and unregister them on normal context shutdown; a crash or `kill -9` may bypass cleanup, though that JVM's MBeanServer terminates along with the process.

## 9. How Do Stable Names Help Monitoring and Automation?

An administrative script can query using the exact `ObjectName`:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=PaymentQueue"
);
Integer pending = (Integer) connection.getAttribute(
    name, "PendingCount"
);
```

If on every restart the name changed to `name=PaymentQueue-20261111T0900`, the script could fail with `InstanceNotFoundException`. Searching by wildcard would be required, increasing the risk of selecting the wrong MBean or reading values from an unintended run session.

Stable names improve:

- Dashboards, panels, and alerts tracking the same logical resource.
- Operational scripts and collectors not needing name updates on every deploy.
- Detecting MBeans disappearing and reappearing across restarts while preserving logical mapping.
- Comparing attributes and operations across releases.
- Access control rules and MBean name allowlists being easier to govern.

However, **an ObjectName is not a globally unique key across all points in time**. An MBean with the same name in a new run session does not carry the same state, counters, or event history as the old instance. For time-series data, collectors must clearly define service, cluster, instance, and environment labels as well as counter-reset handling.

## 10. Changing Identity Is a Migration

Suppose the old convention was:

```text
com.example:type=Pool,name=Primary
```

And the new convention is:

```text
com.example.db:type=ConnectionPool,name=Primary
```

This is a JMX identity change. For clients querying the exact name, it can cause breakage even when the Java class and attributes remain unchanged.

A migration should:

1. Document why the domain or key property is changing.
2. Inventory dashboards, alerts, scripts, and access policies depending on the old name.
3. If needed and supported, export an alias MBean during a transition window (the same logic managed under two separate names), taking care not to register duplicate `ObjectName`s.
4. Update clients and metric routing to the new name.
5. Remove the alias once downstream consumers have migrated.

Do not change `name` merely because internal Java classes or framework implementations changed. The JMX contract is an operational interface, so logical names have a lifecycle independent of code refactoring.

## 11. How to Verify Names Across Restarts

You can test with a small program using `ManagementFactory.getPlatformMBeanServer()`, registering `QueueMonitor` via `JmxNames.queue("PaymentQueue")`, and printing the canonical name. Run the program twice independently:

```text
Run 1: com.example.orders:name=PaymentQueue,type=Queue
Run 2: com.example.orders:name=PaymentQueue,type=Queue
```

If configuration has not changed, the two canonical names must be identical. Also test two distinct queues:

```text
com.example.orders:name=PaymentQueue,type=Queue
com.example.orders:name=RefundQueue,type=Queue
```

Two resources require two distinct names. Try registering a duplicate name in the same `MBeanServer`: you should observe `InstanceAlreadyExistsException`, and fix ownership/registration mechanisms rather than appending random suffixes.

In a Spring environment, an integration test can start an `ApplicationContext` for the JMX configuration, read `MBeanServer.queryNames`, close the context, and start a new context to compare canonical names. When sharing a single `MBeanServer`, the test must ensure the first context finishes unregistering before opening the second context so lifecycle conflicts are not mistaken for name instability.

## 12. Common Design Mistakes

**Using `Object.hashCode()` or `identityHashCode()` as a key.** These values are not designed to be persistent identities across restarts.

**Generating a UUID at registration time.** A fresh UUID each run is useful as a run ID, but it breaks contracts for exact-name lookups. If a UUID is genuinely a persistently stored business ID, it can be used as a name, provided it has operational meaning and contains no sensitive data.

**Using a list index.** `worker=0` is unstable if the list is reordered or instances are created/destroyed dynamically. Use an ordinal only when it is part of a guaranteed managed identity.

**Putting dynamic state into a key property.** `status=ACTIVE` causes the name to change whenever the resource transitions state. Use a `State` attribute instead.

**Assigning the same name to two MBeans in the same JVM.** They cannot be registered concurrently; add a distinguishing logical key or redesign the resource model.

**Assuming the same name always implies the same endpoint.** `ObjectName` only identifies within an `MBeanServer`; remote clients must also pick the right endpoint and handle reconnection.

**Relying on canonical strings to legitimize random names.** Canonicalization only standardizes key property order; it does not stabilize values.

## 13. Hands-On Exercises

1. Design an `ObjectName` for a `Cache` named `ProductCatalog` with properties `HitCount`, `Size`, and `StartTimeMillis`. Decide which belong in the name and which belong as attributes.
2. An application creates an MBean named `service:type=Worker,pid=12345`. Describe the negative impact after a restart and propose a logical replacement name.
3. Compare two name strings with different key orders using `ObjectName.equals()` and `getCanonicalName()`.
4. Given a system with 4 replicas, each having a `PaymentQueue`, design how the collector distinguishes targets without relying on ever-changing pod names.
5. Write an integration test that starts two Spring contexts sequentially and confirms that the `ObjectName` of the same configured MBean remains identical.

## 14. Self-Check Questions

- Why should PIDs, timestamps, or freshly generated UUIDs not be placed in the `ObjectName` of a stable resource?
- Is `ObjectName` guaranteed unique across multiple JVMs or only within a single `MBeanServer`?
- Are two `ObjectName`s with the same key properties in different orders equal?
- What is the difference between resource identity, run-session identity, and endpoint identity?
- When changing the domain from `com.example` to `com.example.db`, why must it be treated as a migration?
- How does Spring's `MBeanExporter` help with MBean lifecycle, and what must the application still specify?

**Key takeaway:** Construct `ObjectName` using controlled, stable logical identities from configuration. Keep per-run varying data as attributes, use the canonical name when a standard representation is needed, and separate MBean identity from connection/replica identity in distributed systems.
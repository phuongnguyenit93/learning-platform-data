# Configuring the beans Map Between ObjectName and Beans in Spring JMX

## Objectives

After this lesson, you will be able to use the Spring Framework to configure mappings between **JMX `ObjectName`** and **Spring beans** via `MBeanExporter`; understand how map entries become MBeans registered with an `MBeanServer`; choose an explicit registration mechanism; distinguish between map keys, Spring bean names, and JMX names; handle name conflicts, lifecycles, proxies, and MBean replacement policies; and verify results using the JMX API.

## 1. Why Map ObjectName and Beans?

In the Spring Framework, services or components are typically created and managed by an `ApplicationContext`. JMX, on the other hand, identifies management objects by `javax.management.ObjectName` inside an `MBeanServer`.

These two names serve two different responsibilities:

| Concept | Example | Role |
| --- | --- | --- |
| Spring bean name | `paymentQueueMonitor` | Locate and manage the object in the IoC container |
| JMX ObjectName | `com.example.payment:type=Queue,name=Primary` | Identify the MBean in the `MBeanServer` |
| Java type | `PaymentQueueMonitor` | Define the implementation and management capabilities |
| MBean interface/metadata | `PaymentQueueMonitorMBean` or `@ManagedResource` | Specify exposed attributes and operations |

Explicit mapping lets you tell Spring:

> Register **this bean** under **that ObjectName** in the MBeanServer.

This is the primary role of the `beans` property on `org.springframework.jmx.export.MBeanExporter`.

Target example:

```text
Spring ApplicationContext
  paymentQueueMonitor  ------> com.example.payment:type=Queue,name=Primary
  refundQueueMonitor   ------> com.example.payment:type=Queue,name=Refund
  workerMonitor        ------> com.example.payment:type=Worker,name=Retry
                               |
                               v
                         JMX MBeanServer
```

You control the management names, avoiding reliance on automatic inference from class names or bean names.

## 2. What Is the MBeanExporter beans Map?

`MBeanExporter` has a `beans` property used to specify the objects to export to JMX. Map keys can be `ObjectName` strings; values are typically bean objects or bean name references according to the mechanisms supported by the exporter.

Conceptual form:

```java
Map<String, Object> beans = Map.of(
    "com.example.payment:type=Queue,name=Primary", paymentQueueMonitor,
    "com.example.payment:type=Queue,name=Refund", refundQueueMonitor
);
exporter.setBeans(beans);
```

During the registration step, the exporter turns each entry into an MBean managed by the `MBeanServer`.

**Do not confuse the map key with the bean name.** The key `com.example.payment:type=Queue,name=Primary` is the name presented to JMX clients, whereas `paymentQueueMonitor` is the object/bean created by Spring.

The `setBeans` mechanism is **explicit registration**. It differs from:

- `setAutodetect(true)`: Spring discovers eligible beans according to autodetection and exporter/assembler rules.
- `@ManagedResource` with scanning/metadata mechanisms: provides JMX metadata for the exporter to use, but does not by itself guarantee every bean is registered if no suitable exporter is present.
- Direct registration via `MBeanServer.registerMBean(...)`: you manually manage all registration and unregistration.

In an application, choose an intentional strategy to prevent the same bean from being exported twice.

## 3. Complete Example: Explicitly Mapped Standard MBean

Create the Standard MBean interface:

```java
package com.example.payment.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void setPaused(boolean paused);
    void resetPending();
}
```

Implementation:

```java
package com.example.payment.jmx;

public class PaymentQueueMonitor implements PaymentQueueMonitorMBean {
    private volatile int pendingCount = 20;
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void setPaused(boolean paused) {
        this.paused = paused;
    }

    @Override
    public void resetPending() {
        pendingCount = 0;
    }
}
```

Java-based Spring configuration:

```java
package com.example.payment.config;

import com.example.payment.jmx.PaymentQueueMonitor;
import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class PaymentJmxConfiguration {
    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor();
    }

    @Bean
    public MBeanExporter paymentMBeanExporter(
            PaymentQueueMonitor paymentQueueMonitor) {
        MBeanExporter exporter = new MBeanExporter();

        Map<String, Object> registrations = new HashMap<>();
        registrations.put(
            "com.example.payment:type=Queue,name=Primary",
            paymentQueueMonitor
        );

        exporter.setBeans(registrations);
        return exporter;
    }
}
```

Spring creates `PaymentQueueMonitor` as a singleton bean, then passes the object into the exporter configuration. When the exporter initializes, it registers the bean into the `MBeanServer` under the configured ObjectName. In the case of a valid Standard MBean, the `PaymentQueueMonitorMBean` interface determines the attributes and operations visible to JMX clients.

A JMX client may see:

```text
com.example.payment:type=Queue,name=Primary

Attributes
  PendingCount : int      read-only
  Paused       : boolean  read-write

Operations
  resetPending() : void
```

**Key point:** The name `Primary` is not inferred by Spring from `PaymentQueueMonitor`; it comes from the map key. Renaming the Spring bean while keeping the ObjectName and MBean contract stable allows JMX clients to continue finding the exact same resource.

## 4. Mapping Multiple Beans to Different ObjectNames

Suppose there are two queues with distinct roles:

```java
@Bean
public PaymentQueueMonitor primaryMonitor() {
    return new PaymentQueueMonitor();
}

@Bean
public PaymentQueueMonitor refundMonitor() {
    return new PaymentQueueMonitor();
}

@Bean
public MBeanExporter queueExporter(
        @Qualifier("primaryMonitor") PaymentQueueMonitor primary,
        @Qualifier("refundMonitor") PaymentQueueMonitor refund) {
    MBeanExporter exporter = new MBeanExporter();

    Map<String, Object> registrations = new LinkedHashMap<>();
    registrations.put(
        "com.example.payment:type=Queue,name=Primary", primary
    );
    registrations.put(
        "com.example.payment:type=Queue,name=Refund", refund
    );

    exporter.setBeans(registrations);
    return exporter;
}
```

Additional imports:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
```

The map allows registering multiple distinct objects, but **each `ObjectName` within the same `MBeanServer` must be unique**. Two objects may have the same Java class, yet must use different keys if they represent two separate resources.

Recommended example:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:type=Queue,name=Refund
```

Avoid generating names with random IDs on each restart if the resource identity remains `Primary` or `Refund`. Stable logical names keep dashboards, management scripts, and alerts from having to change per run.

## 5. Key Format: Valid ObjectName Strings

Keys in the map must follow `ObjectName` syntax:

```text
domain:key=value[,key=value...]
```

For example:

```text
com.example.billing:type=ConnectionPool,name=Main
com.example.billing:type=Cache,name=Product
com.example.billing:type=JobScheduler,name=Nightly
```

Do not use special characters arbitrarily in values. When logical names are read from configuration, use the `ObjectName` constructor or `ObjectName.quote` to prevent commas, equal signs, or wildcards from altering the name structure.

```java
import javax.management.ObjectName;

String queueName = "High,Priority";
ObjectName objectName = new ObjectName(
    "com.example.payment:type=Queue,name="
        + ObjectName.quote(queueName)
);
```

If using `ObjectName` as an internal key, various Spring APIs may accept different forms of names/metadata depending on the configuration approach. With `MBeanExporter.setBeans`, the clearest approach is a complete, syntactically valid JMX name string, while keeping naming rules centralized.

**Important characteristic:** Key property order does not change identity according to `ObjectName.equals()`. `com.example:type=Queue,name=Main` and `com.example:name=Main,type=Queue` are the same ObjectName. Therefore, do not rely on differences in string ordering to avoid name collisions.

## 6. What Object Is the Map Value?

In Java configuration, the most common practice is passing the Spring bean object itself:

```java
Map<String, Object> registrations = Map.of(
    "com.example:type=Cache,name=Product", productCacheMonitor
);
exporter.setBeans(registrations);
```

Be aware that the object may be a **Spring AOP proxy**, not the target class. A JDK dynamic proxy may implement only business interfaces; a CGLIB proxy is a dynamic subclass. This affects how JMX recognizes Standard MBeans/MXBeans and which operations are exposed.

If a bean implements `CacheMonitorMBean` yet the exporter encounters `NotCompliantMBeanException`, you can use an **MBean adapter** or explicitly wrap the interface:

```java
import javax.management.StandardMBean;

CacheMonitorMBean exposed = cacheMonitorProxy;
StandardMBean adapter = new StandardMBean(
    exposed,
    CacheMonitorMBean.class
);

Map<String, Object> registrations = Map.of(
    "com.example:type=Cache,name=Product", adapter
);
exporter.setBeans(registrations);
```

The prerequisite is that `cacheMonitorProxy` actually implements `CacheMonitorMBean`. Otherwise, a management adapter is needed to call the service proxy through a compatible interface. Avoid passing the raw target object directly into JMX if doing so bypasses important security/transaction advice.

Also remember that `MBeanExporter` may process beans through metadata/assembler mechanisms depending on configuration. Therefore, choose the registration method and interface intentionally, then verify `MBeanInfo` after Spring starts.

## 7. Registering Beans via Annotations and MBeanExporter

Spring also supports `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.payment:type=Queue,name=Primary",
    description = "Primary payment queue monitor"
)
public class AnnotatedQueueMonitor {
    @ManagedAttribute
    public int getPendingCount() {
        return 20;
    }

    @ManagedOperation
    public void resetPending() {
        // Reset queue statistics
    }
}
```

If you want the exporter to use annotation metadata, you must configure an appropriate assembler, such as `MetadataMBeanInfoAssembler` and `AnnotationJmxAttributeSource`, or use `@EnableMBeanExport` in the corresponding Spring configuration.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxAnnotationConfig {
}
```

This is an alternative way to organize exporting. You should not simultaneously auto-export a bean with `@ManagedResource` and declare another `beans` map for the same ObjectName without clearly controlling registration. The result may be an MBean name collision, an error, or handling according to the registration policy.

### When to use an explicit map?

- You want to select **precisely** which beans are exported.
- You need a unified ObjectName convention that differs from Spring bean names.
- You want a configuration layer responsible for naming independently of implementations.
- You need to export multiple instances of the same class under different names.
- You want all registrations easy to find in one place.

### When to use annotations/auto-detection?

- The project dictates placing JMX metadata alongside the class.
- There are many management components and a consistently managed scanning mechanism is used.
- You want to declare `@ManagedAttribute`/`@ManagedOperation` directly on methods.

Both approaches can be combined in a controlled strategy, while avoiding duplicate registration and ensuring the exporter uses the right naming/metadata source.

## 8. Using ObjectNamingStrategy When Naming Follows a Common Rule

When there are many MBeans and names must be generated by convention, Spring allows using `ObjectNamingStrategy`. Common strategies live in `org.springframework.jmx.export.naming`, such as `MetadataNamingStrategy`, `KeyNamingStrategy`, and `IdentityNamingStrategy`.

In explicit mapping, if the map key is already a complete ObjectName, a complex strategy is not needed. When names should be generated from classes, annotations, or internal keys, you need to understand precedence and the exporter's naming mechanism.

Good conventions usually include an organization-managed domain and meaningful key properties:

```text
com.example.payment:type=Queue,name=Primary
com.example.payment:type=Queue,name=Refund
com.example.payment:type=Cache,name=ExchangeRates
```

Avoid relying on `System.identityHashCode` or proxy class names when stable identity across restarts is required.

## 9. Choosing an MBeanServer: Local or Shared

`MBeanExporter` must register into an `MBeanServer`. If not explicitly set, the exporter can use Spring's configuration and environment mechanism to locate/select an MBeanServer.

In an application using the platform MBeanServer, you can create an explicit reference bean:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;

@Bean
public MBeanServer platformMBeanServer() {
    return ManagementFactory.getPlatformMBeanServer();
}
```

Then configure the exporter:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer platformMBeanServer,
        PaymentQueueMonitor paymentQueueMonitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(platformMBeanServer);
    exporter.setBeans(Map.of(
        "com.example.payment:type=Queue,name=Primary",
        paymentQueueMonitor
    ));
    return exporter;
}
```

Ensure the parameter injects the exact `MBeanServer` intended, especially in environments with multiple servers. JConsole/JMC failing to see an MBean can happen when the exporter registers on a different server than the one the tool connects to.

When a separate `MBeanServer` bean is unnecessary, you can configure/register directly with the platform server in one place. Do not create multiple MBeanServers arbitrarily just to avoid name conflicts.

## 10. Registration Policy When an ObjectName Already Exists

If an MBean is already registered with the same `ObjectName` in the same `MBeanServer`, JMX by default does not allow registering a second object under the same name.

Common causes:

- Two exporters register the same bean.
- A bean is placed in the map and also discovered via auto-detection.
- Two Spring contexts share the same platform MBeanServer.
- An old MBean was not unregistered during a refresh/redeploy in the same JVM.
- Two map entries have name strings with different key ordering but the same canonical ObjectName.

Spring `MBeanExporter` provides registration policies, such as `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING` (enum values in `org.springframework.jmx.support.RegistrationPolicy`).

For example:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

- `FAIL_ON_EXISTING`: reports a conflict so developers fix ownership.
- `IGNORE_EXISTING`: ignores the new registration if an MBean with the same name already exists.
- `REPLACE_EXISTING`: can replace the existing MBean; requires understanding who owns it and its lifecycle.

For multi-context systems, `REPLACE_EXISTING` must be used cautiously because it can overwrite an MBean managed by another component. When prioritizing clear configuration, letting duplicate-name errors surface usually helps identify the real cause.

## 11. MBeanExporter Lifecycle

`MBeanExporter` integrates with the Spring lifecycle:

1. The context creates the managed beans.
2. The exporter receives the map configuration.
3. The exporter registers MBeans into the MBeanServer at the appropriate initialization phase.
4. JMX clients access attributes/operations.
5. When the context closes normally, the exporter unregisters the MBeans it manages according to the lifecycle mechanism.

While the application is running, do not treat the `beans` map as a mechanism that automatically syncs every runtime change after initialization. If MBeans need to be added/removed dynamically, use the exporter's or MBeanServer's dedicated registration API with proper ownership and synchronization management.

If an MBean with the same name needs to be re-registered, ensure the old lifecycle has ended or handle the registration policy explicitly; do not append random suffixes to the ObjectName just to bypass the error.

## 12. Verifying Mappings with MBeanServer and MBeanInfo

After ApplicationContext initialization, verify directly:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.payment:type=Queue,name=Primary"
);

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);
    System.out.println("Class: " + info.getClassName());

    Object pending = server.getAttribute(name, "PendingCount");
    System.out.println("Pending: " + pending);

    for (var operation : info.getOperations()) {
        System.out.println("Operation: " + operation.getName());
    }
}
```

The condition is that the exporter registers on the **platform MBeanServer**. If the application configures another server, you must reference that exact server.

You can also query by pattern:

```java
for (ObjectName registered : server.queryNames(
        new ObjectName("com.example.payment:type=Queue,*"), null)) {
    System.out.println(registered.getCanonicalName());
}
```

Wildcard queries help discover MBeans but do not replace using exact names in scripts targeting specific objects.

If `isRegistered(name)` returns `true` but attributes are missing, check the Standard MBean/MXBean contract, Spring metadata assembler, and the actual proxy received by the exporter.

## 13. An Integration Test in Spring

You can write a test that creates the context, configures the exporter, and verifies the actual MBean:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class PaymentJmxConfigurationTest {
    @Test
    void exportsMonitorWithExpectedObjectName() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.payment:type=Queue,name=Primary"
        );

        try (var context = new AnnotationConfigApplicationContext(
                PaymentJmxConfiguration.class)) {
            assertTrue(server.isRegistered(name));
            assertEquals(20, server.getAttribute(name, "PendingCount"));
        }

        assertFalse(server.isRegistered(name));
    }
}
```

The test assumes no MBean with the same name existed beforehand, the exporter uses the platform server, and the context closes cleanly. For tests running in parallel, use stable, per-test ObjectName namespaces to avoid contention within the same JVM; clean up via proper lifecycle rather than calling `unregisterMBean` indiscriminately.

## 14. Troubleshooting Common Configuration Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `MalformedObjectNameException` or naming parse error | Malformed ObjectName string, unquoted special characters | Use `ObjectName`, `ObjectName.quote`, normalize keys |
| `NotCompliantMBeanException` | Bean is not a valid MBean by convention or proxy hides interface | Check MBean interface, MXBean, adapter/`StandardMBean` |
| `InstanceAlreadyExistsException` | ObjectName already registered | Check duplicate exporters, lifecycle, and registration policy |
| JMC/JConsole does not see MBean | Exporter not active, wrong server, or wrong name | Check `MBeanServer`, domain, `isRegistered` |
| MBean visible but missing attributes/operations | Metadata assembler or management interface does not expose methods | Check `MBeanInfo` and Spring configuration |
| JMX method runs but aspect has no effect | Exporter received target instead of proxy | Ensure adapter calls the right Spring proxy or configure exposure properly |
| Attribute value errors when reading | Getter throws exception, incompatible data type | Check logs, Java/Open Data types, avoid heavy getters |
| Updates not visible after changing map in code | Context/exporter not reinitialized | Restart context or register/unregister according to lifecycle |

## 15. XML Configuration Option

For a Spring Framework project using XML, the map can be declared inside `MBeanExporter`:

```xml
<bean id="queueMonitor" class="com.example.payment.jmx.PaymentQueueMonitor"/>

<bean id="jmxExporter" class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.payment:type=Queue,name=Primary"
                   value-ref="queueMonitor"/>
        </map>
    </property>
</bean>
```

Here, `key` is the `ObjectName` string, and `value-ref` references the Spring bean by ID. XML makes the relationship between management names and objects explicit, suitable when the project still maintains XML configuration.

If multiple MBeans are needed, add `entry` elements with unique keys. Avoid having two contexts register duplicate keys in the same MBeanServer while both are active.

## 16. Practical Design Principles

- Set domains following organization or module namespaces, e.g., `com.example.payment`, `com.example.inventory`.
- Use operationally meaningful key properties: `type`, `name`, `component`, `tenant` when needed.
- Keep logical identity stable across restarts; PIDs, newly generated UUIDs, thread counts, or startup times should be attributes.
- Export small management interfaces; do not expose the entire internal API of a Spring bean.
- Clearly define which component is responsible for registering and unregistering MBeans.
- Ensure sensitive JMX operations have appropriate access controls; Spring AOP does not replace remote JMX security.
- Unify the export mechanism so a bean is not both explicitly mapped and auto-detected.
- Verify with real clients like JConsole or JMC, in addition to `MBeanServer` APIs in tests.

## 17. Exercises

1. Create two `PaymentQueueMonitor` beans and map them to `name=Primary` and `name=Refund`. Read both `PendingCount` values using `MBeanServer`.
2. Rename the Spring bean `primaryMonitor` to `paymentPrimaryMonitor` while keeping the ObjectName unchanged. Explain the impact on JMX clients.
3. Intentionally register the same ObjectName from two different exporters to observe the conflict error. Fix it by designating one exporter as the MBean owner.
4. Replace the mapped object with a `StandardMBean` adapter when the business bean is a JDK proxy, then compare `MBeanInfo`.
5. Inspect the metadata of an annotation-driven bean and an explicitly mapped bean to understand how interfaces/assemblers determine attributes and operations.
6. Write an integration test checking both `isRegistered` and `getAttribute`, then close the context and verify the MBean is no longer registered.

## 18. Self-Check Questions

- In `MBeanExporter.setBeans`, what does the map key represent and what does the value represent?
- Why can the same Java class be exported as two different MBeans?
- What happens if two exporters register the same canonical `ObjectName`?
- When can `@ManagedResource` and `@EnableMBeanExport` conflict with explicit mapping?
- When an MBean does not appear in JMC, should you check the name, the exporter, or the MBeanServer first?
- Why can registering the target instead of the proxy affect security or transaction advice?
- Why is it important to keep ObjectNames stable even when bean names and implementation classes change?

**Takeaway:** `MBeanExporter.setBeans` is the explicit bridge from a **JMX ObjectName** to a **Spring bean/object**. The map key defines the management identity, and the value is the exported object. Keep names unique and stable, choose the right server and exporter mechanism, verify the actual contract with `MBeanInfo`, and manage the registration lifecycle clearly.
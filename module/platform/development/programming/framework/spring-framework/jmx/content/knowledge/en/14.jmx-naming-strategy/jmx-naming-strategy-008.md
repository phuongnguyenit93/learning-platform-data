# Handling Multiple Instances of the Same Bean Type in Spring JMX

## Learning Objectives

When a Spring Framework application creates multiple instances of the same Java class, you must distinguish them in JMX using unique `ObjectName`s. After this lesson, you will be able to explain MBean identity scope, design naming strategies for multiple instances, configure `MBeanExporter` to register multiple beans of the same type, avoid name collisions, and verify the registry using `MBeanServer` or JConsole.

This lesson belongs to the **Naming strategy** group of Spring Framework JMX, focusing on the question: how can objects of the same type such as `CacheMonitor`, `DataSourceMonitor`, or `WorkerPoolMonitor` coexist in one JMX registry while remaining easy to identify and manage separately?

## 1. One Java Class Can Have Multiple MBean Instances

Suppose an application serves two tenants and has two separate caches:

```text
cacheMonitorPrimary   -> CacheMonitor(instance A)
cacheMonitorSecondary -> CacheMonitor(instance B)
```

Both objects belong to class `CacheMonitor` and share the same management attributes and operations. However, they hold **independent state**. If cache A's hit counter is 120 and cache B's is 450, JMX needs to publish two distinct objects so management tools do not confuse metrics.

An `MBeanServer` registers MBeans by `javax.management.ObjectName`. Within **the same server**, each `ObjectName` can identify only one registration at a time. Therefore, two instances of the same class cannot simultaneously use the exact same name:

```text
com.example.cache:type=CacheMonitor
com.example.cache:type=CacheMonitor
```

Conversely, two names with differing properties are valid:

```text
com.example.cache:type=CacheMonitor,name=primary
com.example.cache:type=CacheMonitor,name=secondary
```

This does not require renaming classes or creating two `*MBean` interfaces. Both instances can implement the same management contract. The difference lies in the identity of each registered object in the registry.

## 2. Distinguishing Java Class, Spring Bean Name, and JMX ObjectName

| Component | Example | Role |
| --- | --- | --- |
| Java class | `CacheMonitor` | Defines behavior and methods |
| Management interface | `CacheMonitorMBean` | Defines standard management API |
| Spring bean name | `primaryCacheMonitor` | Distinguishes bean in `ApplicationContext` |
| Another Spring bean name | `secondaryCacheMonitor` | Another bean with the same Java type |
| JMX `ObjectName` | `com.example.cache:type=CacheMonitor,name=primary` | Identifies instance A in the MBean server |
| Another JMX `ObjectName` | `com.example.cache:type=CacheMonitor,name=secondary` | Identifies instance B in the same server |

A bean name in Spring does not automatically become its JMX `ObjectName`. A Java class name is also insufficient to distinguish multiple instances.

Spring can use a naming strategy to derive management names, but you must understand **the specific strategy configured**. If generated names rely only on the class without instance identity, two beans of the same type risk colliding.

An operationally friendly naming convention typically consists of a stable domain and meaningful keys:

```text
com.example.cache:type=CacheMonitor,name=primary
com.example.cache:type=CacheMonitor,name=secondary
com.example.cache:type=CacheMonitor,tenant=tenant-a,name=local
com.example.cache:type=CacheMonitor,tenant=tenant-b,name=local
```

The keys are design choices, not a mandatory JMX list. An `ObjectName` has the form `domain:key=value,key=value`; the domain and key properties must produce a unique combination per registration.

## 3. Standard MBean Example Sharing a Contract

Create the management interface for all `CacheMonitor` instances:

**CacheMonitorMBean.java**

```java
package com.example.jmx;

public interface CacheMonitorMBean {
    String getLogicalName();
    long getHitCount();
    void resetStatistics();
}
```

**CacheMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class CacheMonitor implements CacheMonitorMBean {
    private final String logicalName;
    private final AtomicLong hits = new AtomicLong();

    public CacheMonitor(String logicalName) {
        this.logicalName = logicalName;
    }

    public void recordHit() {
        hits.incrementAndGet();
    }

    @Override
    public String getLogicalName() {
        return logicalName;
    }

    @Override
    public long getHitCount() {
        return hits.get();
    }

    @Override
    public void resetStatistics() {
        hits.set(0);
    }
}
```

Both instances use `CacheMonitorMBean` and share the same list of attributes/operations. The `LogicalName` attribute helps operators identify which object is being observed, but **does not replace assigning a unique `ObjectName`**: JMX looks up registrations by `ObjectName`, not by attribute values to disambiguate duplicate names.

`AtomicLong` is used so incrementing and resetting the counter have thread-safe semantics at the counter level. However, if concurrency requirements are more complex, design appropriate synchronization or snapshots.

## 4. Configuring MBeanExporter to Export Two Instances of the Same Type

An explicit approach is creating two Spring beans and passing them to `MBeanExporter.setBeans(...)` with two different JMX names.

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class MultiInstanceJmxConfiguration {

    @Bean("primaryCacheMonitor")
    public CacheMonitor primaryCacheMonitor() {
        return new CacheMonitor("primary");
    }

    @Bean("secondaryCacheMonitor")
    public CacheMonitor secondaryCacheMonitor() {
        return new CacheMonitor("secondary");
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter cacheExporter(
            @Qualifier("primaryCacheMonitor") CacheMonitor primary,
            @Qualifier("secondaryCacheMonitor") CacheMonitor secondary,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.cache:type=CacheMonitor,name=primary",
                primary,
                "com.example.cache:type=CacheMonitor,name=secondary",
                secondary
        ));
        return exporter;
    }
}
```

Key points:

1. `@Bean("primaryCacheMonitor")` and `@Bean("secondaryCacheMonitor")` create two independent singleton Spring beans.
2. `@Qualifier` specifies exactly which bean is injected when multiple beans share the same Java type.
3. `Map.of` associates each instance with a distinct `ObjectName`.
4. `MBeanExporter` registers both into **the same platform `MBeanServer`**.
5. The management interface does not need to be duplicated. Both use the `CacheMonitorMBean` contract.
6. JConsole can inspect, read, and invoke each instance independently by its registered name.

In a Spring Boot application with JMX auto-configuration, check which exporter has already been created and choose an appropriate configuration mechanism to avoid duplicate registration.

## 5. Proving Two MBeans Have Independent State

Run the `ApplicationContext` and mutate the two beans differently:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class MultiInstanceDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                MultiInstanceJmxConfiguration.class)) {

            CacheMonitor primary = context.getBean(
                    "primaryCacheMonitor", CacheMonitor.class);
            CacheMonitor secondary = context.getBean(
                    "secondaryCacheMonitor", CacheMonitor.class);

            primary.recordHit();
            primary.recordHit();
            secondary.recordHit();

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName primaryName = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=primary");
            ObjectName secondaryName = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=secondary");

            System.out.println(
                    "Primary registered: " + server.isRegistered(primaryName));
            System.out.println(
                    "Secondary registered: " + server.isRegistered(secondaryName));

            System.out.println(
                    "Primary hits: " + server.getAttribute(primaryName, "HitCount"));
            System.out.println(
                    "Secondary hits: " + server.getAttribute(secondaryName, "HitCount"));

            server.invoke(
                    primaryName,
                    "resetStatistics",
                    new Object[0],
                    new String[0]);

            System.out.println(
                    "Primary after reset: "
                    + server.getAttribute(primaryName, "HitCount"));
            System.out.println(
                    "Secondary after primary reset: "
                    + server.getAttribute(secondaryName, "HitCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.in.read(); // Keep context alive to inspect in JConsole.
        }
    }
}
```

If everything registers properly, before reset you will see `primary=2` and `secondary=1`. Invoking `resetStatistics` on `primaryName` resets only primary's counter; secondary still has `HitCount=1`.

The example shows that **ObjectName determines which object receives the JMX call**. The two instances share method signatures yet are controlled independently.

## 6. Naming Strategy in MBeanExporter

In the previous example, the exporter received concrete `ObjectName`s directly via `setBeans`. When many beans must be exported automatically, a naming strategy establishes naming rules instead of manually writing every `ObjectName`.

Spring Framework provides naming mechanisms such as `ObjectNamingStrategy` and related implementations including `KeyNamingStrategy`, `MetadataNamingStrategy`, and `IdentityNamingStrategy`, suited to different situations.

| Strategy | Usage Idea | Considerations |
| --- | --- | --- |
| `KeyNamingStrategy` | Uses configured keys or mappings to produce `ObjectName` | Must ensure keys distinguish instances |
| `MetadataNamingStrategy` | Reads names from metadata, e.g., `@ManagedResource(objectName=...)` | Two beans with the same fixed metadata can collide |
| `IdentityNamingStrategy` | Uses identity information to distinguish instances | Names can vary by instance/run, less stable for dashboards |

When you need monitoring automation based on stable names, naming with business keys (`tenant`, `pool`, `name`) is generally easier to operate than names depending on runtime identity.

Do not assume every naming strategy automatically generates stable and unique names. Check the strategy chosen in the exporter, the key values passed in, and the resulting `ObjectName` in the registry.

## 7. Using KeyNamingStrategy to Distinguish Instances

When controlled name configuration is needed, `KeyNamingStrategy` with mappings can be used. A Java configuration example:

```java
import java.util.Properties;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

@Bean
public KeyNamingStrategy cacheNamingStrategy() {
    KeyNamingStrategy naming = new KeyNamingStrategy();

    Properties mappings = new Properties();
    mappings.setProperty(
            "primaryCacheMonitor",
            "com.example.cache:type=CacheMonitor,name=primary");
    mappings.setProperty(
            "secondaryCacheMonitor",
            "com.example.cache:type=CacheMonitor,name=secondary");

    naming.setMappings(mappings);
    return naming;
}
```

If the exporter uses the corresponding logical bean keys, attach the naming strategy:

```java
exporter.setNamingStrategy(cacheNamingStrategy);
```

This is useful when configuration has many keys needing mapping to different JMX names. **The key name received by the strategy depends on how the exporter selects and identifies beans** (explicit mapping or autodetection); ensure the configuration uses the corresponding keys rather than assuming every bean always uses its Spring bean name in every mode.

For an example with only two instances, providing complete `ObjectName`s in `setBeans` remains an intuitive way to learn and verify results.

## 8. Annotation-Based Export with Multiple Instances

A class can be annotated with `@ManagedResource` so Spring builds management metadata:

```java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(description = "Cache monitor")
public class AnnotatedCacheMonitor {
    private final String name;

    public AnnotatedCacheMonitor(String name) {
        this.name = name;
    }

    @ManagedAttribute
    public String getName() {
        return name;
    }
}
```

Suppose two Spring beans are created:

```java
@Bean("firstAnnotatedMonitor")
public AnnotatedCacheMonitor firstAnnotatedMonitor() {
    return new AnnotatedCacheMonitor("first");
}

@Bean("secondAnnotatedMonitor")
public AnnotatedCacheMonitor secondAnnotatedMonitor() {
    return new AnnotatedCacheMonitor("second");
}
```

If both are detected by an annotation exporter, the exporter must produce **two different `ObjectName`s**. Since both instances share the same class and identical metadata, if the naming strategy relies solely on class name or a fixed `objectName` annotation, a conflict can occur.

One clear way to control this is explicitly exporting each object with distinct names via an appropriately configured exporter. Another is using a naming strategy that includes bean/instance identity in the keys. When combining annotation metadata with custom naming, ensure the assembler and naming strategy are configured consistently.

**You cannot resolve an `ObjectName` collision just by renaming `@Bean` if the naming strategy completely ignores Spring bean names.** Check the final JMX names.

## 9. Real-World Application Naming Patterns

### By Tenant

```text
com.example.platform:type=CacheMonitor,tenant=alpha
com.example.platform:type=CacheMonitor,tenant=beta
```

Suitable when each tenant has an independent object. If tenant identifiers contain special characters, construct valid `ObjectName`s and apply standard quoting/escaping.

### By Pool

```text
com.example.worker:type=ThreadPoolMonitor,pool=io
com.example.worker:type=ThreadPoolMonitor,pool=cpu
com.example.worker:type=ThreadPoolMonitor,pool=scheduler
```

Suitable for thread pools sharing the same management API but differing in active thread count and queue depth.

### By DataSource

```text
com.example.db:type=DataSourceMonitor,name=primary
com.example.db:type=DataSourceMonitor,name=analytics
```

Suitable when an application uses multiple data sources and needs to distinguish connection pools.

### By Role and Instance

```text
com.example.messaging:type=ConsumerMonitor,role=orders,instance=0
com.example.messaging:type=ConsumerMonitor,role=orders,instance=1
```

Used when multiple consumers of the same role exist in one JVM. These names are not automatically unique across a multi-JVM system: `ObjectName` uniqueness is scoped per `MBeanServer`, while connecting to the right JVM is the responsibility of clients or the monitoring system.

For systems with multiple JVM replicas, dashboards need to add JVM/host/service identity at the metrics collection layer, since two JVMs can register the exact same `ObjectName` without conflict.

## 10. Handling ObjectName Collisions

If two objects are registered under the name:

```text
com.example.cache:type=CacheMonitor,name=primary
```

the MBean server cannot hold both registrations simultaneously. By default, the exporter usually fails when a name already exists. Registration policies provided by Spring include:

- `REGISTRATION_FAIL_ON_EXISTING`: fails if the name is already registered.
- `REGISTRATION_IGNORE_EXISTING`: skips the new registration when the name exists.
- `REGISTRATION_REPLACE_EXISTING`: replaces the existing registration.

Configuration example:

```java
import org.springframework.jmx.support.MBeanRegistrationSupport;

exporter.setRegistrationBehavior(
        MBeanRegistrationSupport.REGISTRATION_FAIL_ON_EXISTING);
```

When an application needs two concurrent instances, **IGNORE** and **REPLACE** do not solve the need to keep two entries; they only change the conflict outcome. The right fix is generating distinguishing names per instance.

Using `REPLACE_EXISTING` can overwrite another component's MBean that operators are monitoring. In Spring applications with multiple `ApplicationContext`s sharing a server, define the owner and unregistration lifecycle of each `ObjectName`.

## 11. Configuring Multiple Instances with XML

Spring Framework supports XML bean definitions. The following example declares two instances of the same class and an exporter:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="primaryCacheMonitor"
          class="com.example.jmx.CacheMonitor">
        <constructor-arg value="primary"/>
    </bean>

    <bean id="secondaryCacheMonitor"
          class="com.example.jmx.CacheMonitor">
        <constructor-arg value="secondary"/>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="beans">
            <map>
                <entry
                    key="com.example.cache:type=CacheMonitor,name=primary"
                    value-ref="primaryCacheMonitor"/>
                <entry
                    key="com.example.cache:type=CacheMonitor,name=secondary"
                    value-ref="secondaryCacheMonitor"/>
            </map>
        </property>
    </bean>
</beans>
```

This configuration uses explicit mapping. If `server` is not declared, the exporter applies Spring's `MBeanServer` lookup mechanism based on configuration and the current runtime. When needing the platform server for JConsole inspection, configure/inject the server explicitly.

Both Java configuration and XML allow exporting multiple Spring beans of the same Java type, as long as each registration has a unique `ObjectName`.

## 12. Inspecting Multiple MBeans with MBeanServer

A reliable way to verify is querying the registry with a pattern:

```java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.cache:type=CacheMonitor,*"),
        null
);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
    System.out.println("LogicalName: "
            + server.getAttribute(name, "LogicalName"));
    System.out.println("HitCount: "
            + server.getAttribute(name, "HitCount"));
}
```

The pattern `type=CacheMonitor,*` matches names that have additional key properties beyond `type`, suitable when the application distinguishes by `name` or `tenant`.

The returned data is a set of `ObjectName`s; do not rely on iteration order to tell primary from secondary. Use the property:

```java
String instanceName = name.getKeyProperty("name");
```

to distinguish them or build a concrete mapping. When printing for logs/audits, `getCanonicalName()` is useful for displaying keys consistently in canonical order.

**Note:** `getPlatformMBeanServer()` returns the registry of the JVM running that code. If called from a separate client JVM, you will see the client's registry rather than the application server's. For remote clients, connect via `JMXConnector` to obtain an `MBeanServerConnection` to the target JVM.

## 13. Inspecting with JConsole

After starting the Spring application:

1. Open JConsole and connect to the right JVM by PID.
2. Select the **MBeans** tab.
3. Find the domain `com.example.cache`.
4. Expand the tree containing `type=CacheMonitor,name=primary` and `type=CacheMonitor,name=secondary`.
5. Read `LogicalName` and `HitCount` of each MBean; verify the two instances have separate data.
6. In a test environment, invoke `resetStatistics` on primary.
7. Read `HitCount` again on both primary and secondary; only primary is reset.

If both entries do not appear together, check whether both beans were selected by the exporter, whether JMX names collided, whether the exporter encountered errors at context startup, and whether JConsole is connected to the right server/JVM.

A JMX client may organize keys into a tree in a different order; do not infer an entry is missing just because you do not see the exact node order shown in an example.

## 14. Integration Testing Two Instances in ApplicationContext

JUnit Jupiter can be used to verify independent registrations:

```java
package com.example.jmx;

import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class MultiInstanceJmxTest {

    @Test
    void registersTwoCacheMonitorsWithSeparateState() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                MultiInstanceJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName primary = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=primary");
            ObjectName secondary = new ObjectName(
                    "com.example.cache:type=CacheMonitor,name=secondary");

            assertTrue(server.isRegistered(primary));
            assertTrue(server.isRegistered(secondary));
            assertNotEquals(primary, secondary);

            CacheMonitor first = context.getBean(
                    "primaryCacheMonitor", CacheMonitor.class);
            CacheMonitor second = context.getBean(
                    "secondaryCacheMonitor", CacheMonitor.class);

            first.recordHit();
            first.recordHit();
            second.recordHit();

            assertEquals(2L, server.getAttribute(primary, "HitCount"));
            assertEquals(1L, server.getAttribute(secondary, "HitCount"));

            server.invoke(
                    primary, "resetStatistics",
                    new Object[0], new String[0]);

            assertEquals(0L, server.getAttribute(primary, "HitCount"));
            assertEquals(1L, server.getAttribute(secondary, "HitCount"));

            Set<ObjectName> names = server.queryNames(
                    new ObjectName("com.example.cache:type=CacheMonitor,*"),
                    null);
            assertEquals(Set.of(primary, secondary), names);
        }
    }
}
```

This test verifies that the exporter registers both instances, and confirms JMX calls affect the right object. When running a suite with many parallel tests, do not share the platform MBean server with the same `ObjectName`. Use a separate server per fixture or per-test domains/instance names to reduce conflicts.

## 15. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Only one MBean visible | Both beans share `ObjectName`, one bean not exported, or exporter ignores/replaces | Check mappings, logs, and `queryNames` |
| `InstanceAlreadyExistsException` | Same JMX name on the same server | Add distinguishing key `name`, `tenant`, or `pool` |
| Two MBeans unexpectedly have identical metrics | Mappings point to the same Spring instance | Check `@Qualifier` and objects passed to `setBeans` |
| `NoUniqueBeanDefinitionException` | Injecting by type when multiple beans share the class | Use `@Qualifier` or inject by bean name |
| ObjectName displays differently than expected | Naming strategy changes name or normalizes key order | Read `queryNames`, `getCanonicalName` |
| Adding Spring bean name still collides | Strategy relies on fixed class/annotation | Fix naming strategy or JMX mappings |
| MBean disappears after context restart | Exporter unregisters on context close | Understand lifecycle, verify active context |
| JConsole does not find both | Wrong JVM, MBean server, or domain | Cross-check PID, `isRegistered`, server list |

## 16. Principles for Designing Durable Naming Strategies

1. **Choose a clear domain:** by application or subsystem, e.g., `com.example.cache`.
2. **Choose a role-descriptive type:** `type=CacheMonitor`, `type=ThreadPoolMonitor`.
3. **Add keys distinguishing instances:** `name`, `tenant`, `pool`, `role`, depending on the domain.
4. **Use stable identity when long-term dashboards are needed:** avoid relying on hashcodes or instance IDs that change on every run unless explicitly required.
5. **Do not put secrets or PII in ObjectNames:** names are often visible in management tools and monitoring systems.
6. **Escape property values per JMX standards:** when values contain commas, equals signs, colons, or special characters, use appropriate `ObjectName` construction APIs.
7. **Determine uniqueness scope:** JMX names are unique per `MBeanServer`, not automatically unique across multiple JVMs.
8. **Verify results after registration:** use `isRegistered`, `queryNames`, and metadata to confirm each instance was exported accurately.

## 17. Practice Exercises

**Exercise 1 — Two thread pools.** Create `WorkerPoolMonitor` with two Spring beans `ioPoolMonitor` and `cpuPoolMonitor`. Register them under `com.example.worker:type=WorkerPoolMonitor,pool=io` and `pool=cpu`. Verify independent `ActiveCount` attributes.

**Exercise 2 — Name collision.** Intentionally register two monitors under the same `com.example.worker:type=WorkerPoolMonitor` in a test environment. Record the error and fix it with the `pool` key.

**Exercise 3 — Naming strategy.** Replace explicit mapping with `KeyNamingStrategy` using mappings by bean keys. Observe final names via `queryNames` and compare benefits and complexity.

**Exercise 4 — Same-class annotations.** Create two instances of a class annotated with `@ManagedResource`. Check how the exporter selects them, try a fixed annotation name, and explain why `ObjectName` collisions must be resolved.

**Exercise 5 — Multiple JVMs.** Run two separate Java processes with the same `ObjectName` and connect sequentially using JConsole. Explain why there is no conflict when both processes have separate `MBeanServer`s.

## Conclusion

When Spring Framework exports multiple instances of the same bean type to JMX, each object needs a **unique `ObjectName` within the same `MBeanServer`**. Java classes and management interfaces can be shared, while Spring bean names and JMX names must be clearly distinguished. Using a naming strategy or `MBeanExporter.setBeans` with stable domains/key properties helps management tools identify and invoke each instance accurately. Verify with `MBeanServer` and JConsole to confirm both identity and independent state of the MBeans.

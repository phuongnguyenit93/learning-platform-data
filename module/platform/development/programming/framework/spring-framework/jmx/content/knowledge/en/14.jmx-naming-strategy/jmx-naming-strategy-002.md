# KeyNamingStrategy: Using Bean Map Keys as ObjectNames in Spring JMX

## 1. Objective

When exporting Spring beans via JMX, each MBean needs a unique `javax.management.ObjectName` within `MBeanServer`. Spring Framework provides `MBeanExporter` and naming strategies (`ObjectNamingStrategy`) to turn a bean together with its configuration key into a JMX name.

`KeyNamingStrategy` is suitable when an application declares a map of beans to export and **wants the map key itself to represent the MBean name**. Instead of forcing every class to have `@ManagedResource(objectName=...)`, configuration outside the class defines the management identity.

Key points to remember:

- The key of the `MBeanExporter.setBeans(...)` map is not just an arbitrary label when using `KeyNamingStrategy`: it is the input used to build the `ObjectName`.
- The bean instance is the **value** of the entry; the key is the basis for determining the **registration name**.
- JMX names have their own syntax: `domain:key=value[,key=value...]`.
- `KeyNamingStrategy` handles naming, not which attributes/operations are exported. Building `MBeanInfo` belongs to the assembler or the standard MBean contract.
- A valid object name must not collide with another MBean on the same server, unless a registration policy is explicitly configured.

## 2. From Bean Map to MBeanServer

Configuration flow:

```text
MBeanExporter
  setBeans(Map<String, Object>)
    |
    +-- key: "com.example.jobs:type=Worker,name=Primary"
    +-- value: workerManagementBean
            |
            v
    KeyNamingStrategy.getObjectName(bean, key)
            |
            v
    ObjectName("com.example.jobs:type=Worker,name=Primary")
            |
            v
    MBeanServer.registerMBean(...)
```

`MBeanExporter` passes two pieces of data to the naming strategy: the bean to export and the key associated with the export configuration. With `KeyNamingStrategy`, the key is the primary naming source. The Java class name or Spring bean ID does not automatically replace the key when you have specified an explicit JMX key in the map.

This separation is useful when one implementation is used across multiple deployments where each deployment has a different `ObjectName`. For the same reason, managing map keys must be treated as managing an operational API.

## 3. Example of a Standard MBean

Create an interface following the Standard MBean convention:

```java
package com.example.jobs;

public interface WorkerMonitorMBean {
    int getQueueDepth();
    boolean isPaused();
    void requestPause();
}
```

Implementation:

```java
package com.example.jobs;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class WorkerMonitor implements WorkerMonitorMBean {
    private final AtomicInteger queued = new AtomicInteger();
    private final AtomicBoolean paused = new AtomicBoolean();

    @Override
    public int getQueueDepth() {
        return queued.get();
    }

    @Override
    public boolean isPaused() {
        return paused.get();
    }

    @Override
    public void requestPause() {
        paused.set(true);
    }
}
```

`WorkerMonitor` has its own JMX contract and does not need to import Spring annotations. In a real application, the queued count is updated from the actual worker/queue and the pause command must follow management rules, rather than just mutating a variable the worker never uses.

## 4. Java Configuration with KeyNamingStrategy

Declare `MBeanExporter` and the map of beans:

```java
package com.example.jobs.config;

import com.example.jobs.WorkerMonitor;
import java.lang.management.ManagementFactory;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

@Configuration
public class JmxExportConfig {

    @Bean
    public WorkerMonitor workerMonitor() {
        return new WorkerMonitor();
    }

    @Bean
    public MBeanExporter mbeanExporter(WorkerMonitor workerMonitor) {
        Map<String, Object> exported = new LinkedHashMap<>();

        exported.put(
            "com.example.jobs:type=Worker,name=Primary",
            workerMonitor
        );

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setNamingStrategy(new KeyNamingStrategy());
        exporter.setBeans(exported);
        return exporter;
    }
}
```

When the context starts, the exporter registers `workerMonitor` under the name:

```text
com.example.jobs:type=Worker,name=Primary
```

In this example, `WorkerMonitor` is a Standard MBean. If the map value is a plain POJO, an appropriate `MBeanInfoAssembler` may be required so Spring creates a ModelMBean; `KeyNamingStrategy` does not turn an arbitrary POJO into a standard Java MBean by itself.

Also pay attention to Spring Boot configuration: if Boot already auto-creates an exporter, adding a manual exporter may cause duplicate registration of the same ObjectName or two different naming namespaces. A single consistent export strategy must be managed.

## 5. A Map Key Is Not an ObjectName Key Property

There are two uses of the word *key* that often cause confusion:

1. **Map key:** the string on the left side of `exported.put(key, bean)`; `KeyNamingStrategy` receives this string.
2. **ObjectName key property:** parts such as `type`, `name`, `instance` that sit *inside* the ObjectName syntax.

For example:

```java
String mapKey = "com.example:type=Cache,name=Catalog";
exported.put(mapKey, catalogMonitor);
```

The entire `mapKey` is a JMX ObjectName, while `type` and `name` are two property keys of the ObjectName. `KeyNamingStrategy` does not automatically infer a domain and properties from the word "catalogMonitor" in an arbitrary `Map` key unless you have designed or configured an appropriate conversion.

When no custom mapping is present, use keys with full ObjectName syntax, which are easy to cross-reference and stable.

## 6. KeyNamingStrategy and Properties Mappings

`KeyNamingStrategy` also supports a lookup table mapping keys to ObjectNames via `Properties`. Thanks to that, keys in the map can be short aliases while the actual JMX names are configured centrally.

Example defining mappings:

```java
import java.util.Properties;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

Properties mappings = new Properties();
mappings.setProperty(
    "primaryWorker",
    "com.example.jobs:type=Worker,name=Primary"
);
mappings.setProperty(
    "secondaryWorker",
    "com.example.jobs:type=Worker,name=Secondary"
);

KeyNamingStrategy naming = new KeyNamingStrategy();
naming.setMappings(mappings);
```

When declaring the map:

```java
Map<String, Object> exported = Map.of(
    "primaryWorker", primaryWorker,
    "secondaryWorker", secondaryWorker
);

MBeanExporter exporter = new MBeanExporter();
exporter.setNamingStrategy(naming);
exporter.setBeans(exported);
```

Meaning: the map key acts as an internal alias, and `Properties` provides the registration name. If there is no mapping for a key, the strategy can use that key as the input ObjectName; therefore, a key missing a mapping must be a valid name or registration will fail. Mappings should be tested and managed as part of application configuration.

Note: mappings are not MBean registration records; they only specify the names that will be used when the exporter performs registration.

## 7. MBeanInfoAssembler Determines the Management Surface

Alongside `ObjectNamingStrategy`, the exporter can use `MBeanInfoAssembler` to determine the attributes and operations of a bean.

For example:

```java
MBeanExporter exporter = new MBeanExporter();
exporter.setNamingStrategy(new KeyNamingStrategy());
exporter.setBeans(exported);
// exporter.setAssembler(assembler); // If exporting a POJO using ModelMBean
```

Clear division of responsibilities:

| Component | Responsibility |
| --- | --- |
| `MBeanExporter.setBeans` | Selects which beans are exported and the key attached to each bean |
| `KeyNamingStrategy` | Turns a key into an ObjectName |
| `MBeanInfoAssembler` | Determines metadata, attributes, and operations when exporting POJOs as ModelMBeans |
| `MBeanServer` | Registers and serves MBean queries |
| JMX client | Connects, finds ObjectNames, and interacts according to MBeanInfo |

If an MBean appears with the right name but is missing an operation, modifying `KeyNamingStrategy` usually has no effect. You must check the MBean interface or the assembler. If the operations are right but the name appears under the wrong domain, check the map key and mappings.

## 8. Safe ObjectName Rules

A valid JMX name has the form:

```text
domain:key=value[,key=value...]
```

Examples:

```text
com.example.jobs:type=Worker,name=Primary
com.example.jobs:type=Worker,name=Secondary,region=apac
```

Common problems:

- Improper domain or one containing unintended pattern characters.
- Missing `:` or `key=value` pairs.
- Duplicate property keys within the same name.
- Two map entries resolving to the same ObjectName.
- Dynamic values containing commas, equals signs, double quotes, or wildcards that are not handled properly.

Example from a dynamic value:

```java
import javax.management.ObjectName;

String rawInstanceName = "worker,apac*";

String objectNameText =
    "com.example.jobs:type=Worker,name=" +
    ObjectName.quote(rawInstanceName);

ObjectName objectName = new ObjectName(objectNameText);
System.out.println(objectName.isPattern()); // false

exported.put(objectName.getCanonicalName(), workerMonitor);
```

`ObjectName.quote` should be applied to the **property value**, not to the entire ObjectName. This prevents the map key from being parsed as a pattern or multiple unintended property pairs.

For names built from untrusted configuration, validate both the domain and property keys. Using `ObjectName` to verify structure before starting the exporter is good practice.

## 9. Difference Between Map Keys and Spring Bean Names

A Spring bean may be named `workerMonitor`:

```java
@Bean("workerMonitor")
WorkerMonitor monitor() {
    return new WorkerMonitor();
}
```

Yet an explicit map configuration still has the key:

```java
exported.put(
    "com.example.jobs:type=Worker,name=Primary",
    workerMonitor
);
```

When `KeyNamingStrategy` receives this key, the MBean name is `com.example.jobs:type=Worker,name=Primary` rather than `workerMonitor`. Changing the Spring bean name does not necessarily change the ObjectName if the map key remains the same.

Conversely, if the configuration exports beans by reference name and uses a simple bean name as the key, ensure the naming strategy or mapping can convert that key into a valid ObjectName. The safest and clearest approach in this course is to specify full explicit keys.

## 10. KeyNamingStrategy vs. MetadataNamingStrategy and IdentityNamingStrategy

Three strategies commonly mentioned in Spring JMX:

| Strategy | Naming Source | Use Case |
| --- | --- | --- |
| `KeyNamingStrategy` | Export map key, optionally via Properties mappings | Centralized identity configuration without needing `objectName` annotations on classes |
| `MetadataNamingStrategy` | Metadata such as `@ManagedResource(objectName=...)` | Annotation-driven export |
| `IdentityNamingStrategy` | Runtime identity characteristics of the object | Objects needing per-instance names, not aimed at producing stable operational names |

For MBeans used by automation and dashboards, names need to be stable across restarts so clients do not have to rediscover them using a random identifier. `KeyNamingStrategy` is suitable when you actively manage `ObjectName`s in configuration.

If the goal is for each deployment to have its own name, set an explicit `instance`/environment key property rather than relying on unstable runtime identity.

## 11. When Do Map Keys Collide?

Suppose there are two beans:

```java
exported.put(
    "com.example:type=Cache,name=Primary",
    cacheA
);
exported.put(
    "com.example:type=Cache,name=Primary",
    cacheB
);
```

In a Java `Map`, the second `put` with the same key **replaces the previous value**, so the exporter sees only one entry; it will not automatically report a duplicate MBean error in this specific case. This is a hard-to-detect cause because one bean simply "disappears" from the export configuration.

Another case:

```java
exported.put(
    "com.example:type=Cache,name=Primary",
    cacheA
);
exported.put(
    "com.example:name=Primary,type=Cache",
    cacheB
);
```

The two key strings differ so both remain in the `Map`, yet the two `ObjectName`s are equivalent in canonical identity. When both register into the same server, the second registration may throw `InstanceAlreadyExistsException`, depending on the registration policy.

Validate every key as an `ObjectName`, convert to `getCanonicalName()`, and check uniqueness before passing it to the exporter.

## 12. Building a Mapping with Canonical Name Duplicate Checking

Example of a small builder to detect duplicate JMX identities:

```java
import java.util.LinkedHashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class ExportedMBeans {
    private final Map<String, Object> values = new LinkedHashMap<>();
    private final Set<String> canonicalNames = new HashSet<>();

    public void add(String name, Object bean)
            throws MalformedObjectNameException {
        ObjectName objectName = new ObjectName(name);
        if (objectName.isPattern()) {
            throw new IllegalArgumentException(
                "A registration name cannot be a JMX pattern: " + name
            );
        }
        String canonical = objectName.getCanonicalName();
        if (!canonicalNames.add(canonical)) {
            throw new IllegalArgumentException(
                "Duplicate MBean ObjectName: " + canonical
            );
        }
        values.put(canonical, bean);
    }

    public Map<String, Object> asMap() {
        return Map.copyOf(values);
    }
}
```

This utility helps detect duplicate canonical `ObjectName`s **within your configuration**; it does not replace checking MBeans already registered by other components in `MBeanServer`. `Map.copyOf` creates an immutable map without guaranteeing iteration order; if stable display or initialization order is needed, return an unmodifiable `LinkedHashMap` copy appropriately.

## 13. Reading and Diagnosing Startup Errors

When the exporter fails to register an MBean, inspect the nested cause:

| Error / Symptom | Common Meaning | What to Check |
| --- | --- | --- |
| `MalformedObjectNameException` | Key/mapping produces a syntactically invalid name | Print the key and canonical parsing in tests |
| `InstanceAlreadyExistsException` | Name already exists on the same server | Compare canonical names, check other exporters |
| `NotCompliantMBeanException` | Bean is not yet a valid MBean and assembler does not handle it | Check Standard MBean/MXBean/assembler |
| Registration succeeds with wrong name | Map key or Properties mappings are not as expected | Check the resolved ObjectName |
| MBean does not appear | Map lacks entry, bean not created, or exporter did not run | Check bean context and configuration |
| MBean exists but lacks methods | MBean contract/assembler does not expose methods | Check `MBeanInfo` |

You can probe inside the same JVM:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName expected = new ObjectName(
    "com.example.jobs:type=Worker,name=Primary"
);

System.out.println(server.isRegistered(expected));

for (ObjectName name : server.queryNames(
        new ObjectName("com.example.jobs:*"), null)) {
    System.out.println(name.getCanonicalName());
}
```

If the exporter points to a custom `MBeanServer`, you must probe that exact server. When JConsole/VisualVM clients do not see the MBean even though the probe sees it, continue checking the JMX connector and the right JVM instead of changing map keys arbitrarily.

## 14. Testing KeyNamingStrategy

A unit test should verify that a key is converted into the expected name:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.jmx.export.naming.KeyNamingStrategy;

class KeyNamingStrategyTest {
    @Test
    void usesMapKeyAsObjectName() throws Exception {
        KeyNamingStrategy naming = new KeyNamingStrategy();

        ObjectName actual = naming.getObjectName(
            new WorkerMonitor(),
            "com.example.jobs:name=Primary,type=Worker"
        );

        ObjectName expected = new ObjectName(
            "com.example.jobs:type=Worker,name=Primary"
        );

        assertEquals(expected, actual);
        assertFalse(actual.isPattern());
    }
}
```

An integration test should start a Spring context with an exporter pointing to a dedicated test server or a uniquely namespaced ObjectName, then verify:

```java
assertTrue(mBeanServer.isRegistered(
    new ObjectName("com.example.jobs:type=Worker,name=Primary")
));
```

At the end of the test, close the context or unregister the test's MBeans. If using the platform server in parallel tests, avoid using the same static ObjectName. With `Properties mappings`, have tests verifying each alias resolves to the exact name without missing mappings.

## 15. Lifecycle and Access Control

`MBeanExporter` normally manages registering and unregistering the MBeans it owns along with the context lifecycle. However, do not assume the exporter may delete MBeans registered by another application. When enabling a registration policy that replaces existing MBeans, understand ownership and client impact.

`KeyNamingStrategy` does not provide authentication, authorization, or TLS. It only identifies MBeans. JMX connection permissions and operation invocation permissions remain governed by the connector, security policy, and application layer.

In production:

- Keep `ObjectName`s stable and avoid embedding secrets or personal data in keys.
- Avoid exporting dangerous operations just because they are public methods.
- Restrict remote JMX access.
- Manage aliases/mappings via versioned configuration.
- Check for name collisions at startup and log enough diagnostic information without exposing sensitive data.

## 16. When to Use KeyNamingStrategy?

Choose `KeyNamingStrategy` when:

1. You want to manage JMX names centrally in configuration, separated from classes.
2. One bean implementation is deployed in multiple instances with different ObjectNames.
3. You need to map internal aliases to stable JMX names.
4. You want to export standard MBeans without adding `@ManagedResource(objectName=...)` onto every class.
5. You want to control naming per module/deployment and protect the contract with tests.

If a team wants classes to declare their own names and management metadata, `MetadataNamingStrategy` together with annotations may be more suitable. Choose one approach consistently, without combining them arbitrarily so a single bean ends up with competing identity sources.

## 17. Key Takeaways

**KeyNamingStrategy treats the export map key as the source for determining the ObjectName.** When a key contains a full JMX name, the exporter can register the bean under that exact name; when mappings are configured, the key acts as an alias translated into an ObjectName. A naming strategy is only responsible for **naming**: the attribute/operation surface is still decided by the MBean contract or assembler, while access security must be managed separately. To avoid hard-to-find bugs, validate ObjectNames, check for duplicate canonical names, keep names stable, and verify results using `MBeanServer.isRegistered` or `queryNames`.

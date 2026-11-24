# Registering an assembler in MBeanExporter

## Learning objectives

In Spring Framework JMX, `MBeanExporter` registers managed objects into `MBeanServer`, while **MBeanInfoAssembler** determines the management interface for objects that do not provide a standard JMX contract themselves. After this lesson, you will:

- Understand the distinct roles of `MBeanExporter`, `MBeanInfoAssembler`, `MBeanServer`, and `ObjectName`.
- Register an assembler with an exporter via `setAssembler(...)`.
- Use `MethodNameBasedMBeanInfoAssembler` to explicitly choose which methods are published.
- Know when to use `InterfaceBasedMBeanInfoAssembler` or `MetadataMBeanInfoAssembler`.
- Verify attributes, operations, and registration status using `MBeanInfo`, rather than relying only on the application starting successfully.
- Recognize the scope of autodetection and the risks of accidentally publishing management methods.

## 1. Why does MBeanExporter need an assembler?

Any given Spring bean may have many public methods, of which only a small subset should be published over JMX. For example, `CacheService` has `getEntryCount()`, `resetStatistics()`, `deleteAllCustomerData()`, and many business methods. Management tools should only be allowed to observe entry counts and reset counters, without accidentally seeing sensitive business APIs.

JMX defines MBean types such as Standard MBeans with interfaces named `ClassNameMBean`, MXBeans, and Dynamic MBeans. If a bean already satisfies a standard JMX contract, `MBeanServer` can introspect that contract. For a POJO that does not implement a standard JMX interface, Spring can **adapt** the object into a ModelMBean, and in that case the assembler supplies management metadata.

Separation of responsibilities:

| Component | Responsibility |
| --- | --- |
| `MBeanExporter` | Selects beans to export, maps names, registers, and manages lifecycle |
| `MBeanInfoAssembler` | Builds `ModelMBeanInfo` describing attributes, operations, constructors, and notifications |
| `MBeanServer` | JMX registry, executes get/set/invoke according to the registered MBean contract |
| `ObjectName` | Unique identifier of an MBean within a server |
| JConsole/client | Reads metadata, views attributes, and invokes published operations |

The assembler does not scan the classpath or register MBeans into the server on its own. It must be used by the exporter for eligible objects. Conversely, attaching an assembler to an exporter does not automatically export every bean in `ApplicationContext`: there must still be a bean map, an autodetection mode, or a specific bean-selection mechanism.

## 2. Two decisions: selecting beans and selecting the management interface

Clearly separate two questions:

1. **Which beans are exported?** Decided by `MBeanExporter` configuration, such as `setBeans(Map.of(...))` or autodetection.
2. **Which methods of that bean are exposed?** Decided by the standard JMX interface or the assembler, depending on the object type and export path.

Model:

```text
ApplicationContext
    |
    +-- cacheService -----------------------+
    |                                      |
    +-- orderService                       |
    |                                      |
    +-- mBeanExporter                      |
            |                              |
            | setBeans: ObjectName -> bean |
            +------------------------------+
            |
            | setAssembler(...)
            v
       MBeanInfoAssembler
            |
            | Select getters / setters / operations
            | Build ModelMBeanInfo
            v
       ModelMBean adapter
            |
            | registerMBean(...)
            v
         MBeanServer
            |
            v
       JConsole / JMX client
```

In this example, the exporter registers `cacheService`; the assembler only publishes the configured methods. `orderService` can still be a valid Spring bean, yet is not an exported object.

## 3. Preparing a managed object as a POJO

Create a class that does not implement a `*MBean` interface, so the management interface is determined by the assembler.

**CacheService.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class CacheService {
    private final AtomicInteger entryCount = new AtomicInteger(3);
    private final AtomicInteger resetCount = new AtomicInteger();

    public int getEntryCount() {
        return entryCount.get();
    }

    public int getResetCount() {
        return resetCount.get();
    }

    public void resetStatistics() {
        resetCount.incrementAndGet();
    }

    public void deleteAllCustomerData() {
        throw new UnsupportedOperationException(
                "Sensitive business operation must not be exposed via JMX");
    }
}
```

The class contains multiple public methods, only some of which are selected as the management interface. `deleteAllCustomerData()` is an illustrative method showing the consequences of using an overly broad assembler. In real applications, sensitive business logic must be protected by dedicated architecture and access controls; never rely on method naming for protection.

## 4. Registering MethodNameBasedMBeanInfoAssembler in MBeanExporter

`MethodNameBasedMBeanInfoAssembler` belongs to package `org.springframework.jmx.export.assembler`. It lets you specify which methods should be included in management metadata.

Java configuration example:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler;

@Configuration
public class CacheJmxConfiguration {

    @Bean
    public CacheService cacheService() {
        return new CacheService();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MethodNameBasedMBeanInfoAssembler cacheAssembler() {
        MethodNameBasedMBeanInfoAssembler assembler =
                new MethodNameBasedMBeanInfoAssembler();
        assembler.setManagedMethods(
                "getEntryCount",
                "getResetCount",
                "resetStatistics"
        );
        return assembler;
    }

    @Bean
    public MBeanExporter cacheExporter(
            CacheService cacheService,
            MBeanServer platformMBeanServer,
            MethodNameBasedMBeanInfoAssembler cacheAssembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setAssembler(cacheAssembler);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=CacheService,name=primary",
                cacheService
        ));
        return exporter;
    }
}
```

Key points to understand:

- `cacheService()` creates the managed object, sharing the same instance with other Spring components if they inject this bean.
- `platformMBeanServer()` selects the current JVM's JMX server.
- `cacheAssembler()` specifies the three methods to include in `ModelMBeanInfo`.
- `cacheExporter()` attaches the assembler via `setAssembler(cacheAssembler)` and registers `cacheService` under an `ObjectName`.
- `deleteAllCustomerData()` is not in the list and is therefore not published by this assembler.
- Getter methods can be modeled as JMX attributes, while `resetStatistics()` can appear in operations.

Note on `setManagedMethods`: the Spring API takes a list of method names and does not distinguish individual overloads by parameter types. If a class has multiple methods with the same name but different signatures, verify the actual metadata or prefer non-overloaded management names to avoid confusion.

### What happens when setAssembler is not called?

`MBeanExporter` can use a default assembler for eligible POJOs. Depending on configuration/version, default assembly can publish more methods than you want. Therefore, for beans with many public business methods, choose an explicit assembler or management interface, then verify the attribute/operation list via `MBeanInfo`.

Do not assume a sensitive public method is protected simply because you have not added `@ManagedOperation`: with a method-naming assembler, exposure depends on the assembler configuration, not annotations.

## 5. Running in ApplicationContext

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            CacheService cache = context.getBean(CacheService.class);
            MBeanServer server = context.getBean(MBeanServer.class);

            ObjectName objectName = new ObjectName(
                    "com.example.jmx:type=CacheService,name=primary");

            System.out.println("Registered: "
                    + server.isRegistered(objectName));
            System.out.println("Entries: "
                    + server.getAttribute(objectName, "EntryCount"));

            cache.resetStatistics();
            System.out.println("Resets: "
                    + server.getAttribute(objectName, "ResetCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.in.read();
        }
    }
}
```

Spring initializes the exporter along with the context. After successful registration, JMX clients connecting to the right JVM see the `ObjectName` and metadata provided by the assembler. Closing the context normally triggers exporter lifecycle cleanup for the registrations it manages.

In an example using the platform server, there is no need to start remote JMX to call APIs within the same JVM. Connecting from another machine requires separate remote JMX configuration and security.

## 6. Inspecting the exact management interface via MBeanInfo

To know whether a method is exposed over JMX, read metadata from the server rather than guessing from the Java class:

```java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class InspectJmx {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jmx:type=CacheService,name=primary");

            MBeanInfo info = server.getMBeanInfo(name);

            System.out.println("Attributes:");
            for (var attribute : info.getAttributes()) {
                System.out.printf(
                        "  %s: %s, readable=%s writable=%s%n",
                        attribute.getName(),
                        attribute.getType(),
                        attribute.isReadable(),
                        attribute.isWritable());
            }

            System.out.println("Operations:");
            for (var operation : info.getOperations()) {
                System.out.println(
                        "  " + operation.getName());
            }
        }
    }
}
```

With an assembler configuration selecting only three methods, we expect to see attributes `EntryCount` and `ResetCount` and operation `resetStatistics` according to the assembled ModelMBean metadata. The exact representation of getters as attributes/operations can depend on the assembler strategy and JMX ModelMBean; therefore, actual assertions must be based on the returned `MBeanInfo`.

Most importantly: `deleteAllCustomerData` is not published as a JMX-callable operation. This is a check to perform when designing a management interface with an assembler mechanism.

## 7. Integration testing controlled exposure

JUnit Jupiter example:

```java
package com.example.jmx;

import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class CacheAssemblerTest {

    @Test
    void onlySelectedMethodsAreExposed() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                CacheJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jmx:type=CacheService,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            assertTrue(Arrays.stream(info.getAttributes())
                    .anyMatch(a -> "EntryCount".equals(a.getName())));

            assertTrue(Arrays.stream(info.getAttributes())
                    .anyMatch(a -> "ResetCount".equals(a.getName())));

            assertTrue(Arrays.stream(info.getOperations())
                    .anyMatch(o -> "resetStatistics".equals(o.getName())));

            assertFalse(Arrays.stream(info.getOperations())
                    .anyMatch(o ->
                            "deleteAllCustomerData".equals(o.getName())));
        }
    }
}
```

This test illustrates how to verify registry/metadata. If a project has multiple JMX tests running in parallel against the same platform server and `ObjectName`, they can collide. In large suites, use separate test servers, distinct domains, or isolated context configurations to ensure independence.

There is no need to invoke a sensitive operation to prove it is hidden; reading `MBeanInfo` is a safer way to verify it does not appear in the management contract.

## 8. InterfaceBasedMBeanInfoAssembler: selecting methods via a dedicated interface

Instead of listing method names, you can define an interface containing only the management API:

```java
package com.example.jmx;

public interface CacheManagement {
    int getEntryCount();
    int getResetCount();
    void resetStatistics();
}
```

The business class implements this interface:

```java
public class CacheService implements CacheManagement {
    // Implement CacheManagement methods.
    // Other business methods are not in the management interface.
}
```

Then use `InterfaceBasedMBeanInfoAssembler`:

```java
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
public InterfaceBasedMBeanInfoAssembler interfaceAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();

    assembler.setManagedInterfaces(CacheManagement.class);
    return assembler;
}
```

On the exporter:

```java
exporter.setAssembler(interfaceAssembler);
```

The advantage is that the management contract is described by a clear Java interface, with compiler support for checking signatures. This is a **management interface used by the Spring assembler**, not necessarily a Standard MBean interface following the `ClassNameMBean` convention.

Comparison:

| Assembler | Method selection | Suitable when |
| --- | --- | --- |
| `MethodNameBasedMBeanInfoAssembler` | Selects specific method names | Few managed methods, easy to specify |
| `InterfaceBasedMBeanInfoAssembler` | Selects methods declared on management interfaces | Want an explicit management API with compile-time checks |
| `MetadataMBeanInfoAssembler` | Reads metadata from an appropriate source, typically Spring JMX annotations | Want to describe attributes/operations via annotations |

The name `CacheManagement` without the `MBean` suffix is still valid for the interface-based assembler: the assembler uses the interface as configuration to build `ModelMBeanInfo`. Do not confuse this with directly registering a Standard MBean in JMX, where interface naming conventions have a specific role.

## 9. MetadataMBeanInfoAssembler and JMX annotations

If you want to control the management interface with Spring annotations, you can use `MetadataMBeanInfoAssembler` together with `AnnotationJmxAttributeSource`:

```java
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
public AnnotationJmxAttributeSource jmxAttributeSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
public MetadataMBeanInfoAssembler metadataAssembler(
        AnnotationJmxAttributeSource jmxAttributeSource) {
    MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(jmxAttributeSource);
    return assembler;
}
```

An annotated managed object:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.jmx:type=CacheAdmin,name=primary")
public class CacheAdmin {

    @ManagedAttribute(description = "Current entry count")
    public int getEntryCount() {
        return 3;
    }

    @ManagedOperation(description = "Reset cache statistics")
    public void resetStatistics() {
        // ...
    }
}
```

In a complete setup, the exporter must be configured with the proper naming strategy and assembler/attribute source as needed; calling `setAssembler(metadataAssembler)` alone does not guarantee `ObjectName` will be inferred from `@ManagedResource` if the naming strategy does not read annotations. If you want built-in convenience, `AnnotationMBeanExporter` or `@EnableMBeanExport` usually aligns the annotation reader, assembler, and naming together.

When using `MetadataMBeanInfoAssembler`, which beans are selected for export remains a separate decision. Do not interpret “having an annotation-reading assembler” as “Spring automatically scans and registers every annotated class” unless an appropriate autodetection strategy is enabled.

## 10. Explicit bean selection and autodetection

An exporter can use `setBeans(...)` to choose targets:

```java
exporter.setBeans(Map.of(
        "com.example.jmx:type=CacheService,name=primary",
        cacheService
));
```

Or configure an autodetect mode to locate beans through mechanisms supported by Spring. Mode constants you may encounter include `AUTODETECT_NONE`, `AUTODETECT_MBEAN`, `AUTODETECT_ASSEMBLER`, and `AUTODETECT_ALL`.

For example, their meanings:

- `AUTODETECT_NONE`: exports only explicitly configured beans.
- `AUTODETECT_MBEAN`: considers beans conforming to MBean conventions.
- `AUTODETECT_ASSEMBLER`: considers beans identifiable by the assembler via metadata.
- `AUTODETECT_ALL`: combines detection sources per configuration.

For learning how to **register an assembler**, `setBeans` helps separate bean selection from method selection. When bringing multiple beans into a system, carefully consider the autodetection strategy to avoid unintentionally expanding the management surface.

An assembler can only select methods for objects that the exporter actually passes into the assembly process. If an object is not in the list of beans to export, it will not appear in the registry even if the assembler is configured accurately.

## 11. XML configuration example

Spring Framework also supports XML bean definitions:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="cacheService" class="com.example.jmx.CacheService"/>

    <bean id="cacheAssembler"
          class="org.springframework.jmx.export.assembler.MethodNameBasedMBeanInfoAssembler">
        <property name="managedMethods">
            <list>
                <value>getEntryCount</value>
                <value>getResetCount</value>
                <value>resetStatistics</value>
            </list>
        </property>
    </bean>

    <bean id="mBeanExporter"
          class="org.springframework.jmx.export.MBeanExporter">
        <property name="assembler" ref="cacheAssembler"/>
        <property name="beans">
            <map>
                <entry
                    key="com.example.jmx:type=CacheService,name=primary"
                    value-ref="cacheService"/>
            </map>
        </property>
    </bean>
</beans>
```

In this XML example, the exporter does not specify `server`, so it uses the server-lookup mechanism according to the actual Spring configuration. If you want to ensure it registers into the platform `MBeanServer`, add an appropriate `MBeanServer` or `MBeanServerFactoryBean` bean and inject it via the `server` property.

XML and Java config differ in syntax but share the same model: the exporter bean references the assembler, managed beans, and server.

## 12. Lifecycle and configuration errors

When `ApplicationContext` initializes:

1. Spring creates dependent beans, including the object to export and the assembler.
2. `MBeanExporter` receives the server, assembler, and bean → `ObjectName` mapping.
3. The exporter builds metadata or uses an existing MBean contract depending on the bean type.
4. The exporter registers the MBean with `MBeanServer`.
5. JMX clients can query metadata and invoke operations according to permissions.

When the context closes normally, the exporter can unregister the MBeans it manages. In applications with multiple exporters or contexts sharing the platform server, avoid colliding `ObjectName`s and clarify ownership.

Some errors to watch for:

| Symptom | Cause to check | How to resolve |
| --- | --- | --- |
| MBean does not appear | Exporter not declared as a bean, bean missing from mapping, wrong server | Check context, `setBeans`, server, and `isRegistered` |
| Too many attributes/operations | Assembler too broad or not attached properly | Check `setAssembler` and `MBeanInfo` |
| Expected method missing | Misspelled method name, invalid getter/setter, not selected by assembler | Compare declared methods and metadata |
| `InstanceAlreadyExistsException` | Duplicate `ObjectName` in the same server | Choose unique names, check lifecycle |
| `NotCompliantMBeanException` / metadata error | Invalid MBean/metadata type | Check class, assembler, method signatures |
| JConsole does not see MBean | Wrong JVM/PID or context already closed | Confirm `ObjectName`, server, and process |
| Sensitive method appears | Wrong assembler mechanism or method selection config | Narrow the management interface and re-verify |
| Changed assembler but client still sees old metadata | Old MBean still registered, context not restarted | Check registration policy and target instance |

## 13. Security and exposure scope

`MBeanInfoAssembler` is a management interface design tool; it is not an authentication system. Even if an assembler publishes only a few methods, a JMX client with access can still invoke those operations. Therefore:

- Include only methods needed for operations in the assembler.
- Do not expose secret keys, tokens, or customer data through attributes.
- Keep side-effecting operations such as `clearCache`, `reloadRules`, and `shutdown` within an approved and controlled scope.
- Design validation and preconditions directly inside the implementation when appropriate.
- For remote JMX, configure proper authentication, authorization, and network restrictions.
- Inspect `MBeanInfo` after export rather than inferring from Java names.

If a business service has many methods unsafe for management, creating a separate **management facade/adapter** usually helps bound the JMX surface more clearly. Then the assembler can select methods on the facade with a small count and stable semantics.

## 14. Practice exercises

**Exercise 1 — Select methods by name.** Create a `QueueService` class with `getQueueDepth()`, `getProcessedCount()`, `resetCounters()`, and `deleteAllPendingJobs()`. Use `MethodNameBasedMBeanInfoAssembler` to export only the first three methods; verify `MBeanInfo` does not contain `deleteAllPendingJobs`.

**Exercise 2 — Swap the management interface.** Create a `QueueManagement` interface with only `getQueueDepth()` and `resetCounters()`, then switch to `InterfaceBasedMBeanInfoAssembler`. Compare metadata between the two configurations.

**Exercise 3 — Annotation metadata.** Place `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` on a test class and configure `MetadataMBeanInfoAssembler` along with `AnnotationJmxAttributeSource`. Inspect `ObjectName` and metadata; explain why the naming strategy must match the annotations.

**Exercise 4 — Test the same instance.** Inject the same `QueueService` bean into both a business service and the exporter. Increment counts from the business service and read via JMX to verify there is no separate management instance.

**Exercise 5 — Autodetection.** Compare `setBeans` against an appropriate autodetection mode. Check how many MBeans appear and which operations are published, then explain why those two decisions are independent.

## Conclusion

Registering an assembler in `MBeanExporter` means providing an `MBeanInfoAssembler` so Spring can build the management interface for exported beans. **The exporter selects objects and registers them; the assembler decides the management metadata of eligible objects.** You can use `MethodNameBasedMBeanInfoAssembler` for a method list, `InterfaceBasedMBeanInfoAssembler` for a Java interface contract, and `MetadataMBeanInfoAssembler` for annotation-style metadata. To confirm the configuration is right, inspect `ObjectName`, attributes, and operations from `MBeanServer`, especially ensuring business methods not intended for management are not exposed.

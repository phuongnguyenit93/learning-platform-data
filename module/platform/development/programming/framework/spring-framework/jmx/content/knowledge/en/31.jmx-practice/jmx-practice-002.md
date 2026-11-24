# Spring Framework JMX — Practice: Exposing a Resource with @ManagedResource

## 1. Lab Objectives

`@ManagedResource` is a Spring Framework annotation in the `org.springframework.jmx.export.annotation` package. This annotation declares a Spring bean as a resource manageable via Java Management Extensions (JMX). When the Spring JMX infrastructure is properly configured, the bean can be exported as an MBean and registered with an `ObjectName` in an `MBeanServer`.

This lab takes you from a regular Java POJO to a resource visible in JConsole or a JMX client. It covers Spring configuration, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, inspecting `MBeanInfo`, naming, and troubleshooting common issues.

**Expected result:** After running the application, an MBean with the ObjectName `com.example.training:type=WorkerPool,name=primary` appears, allowing you to read pool status, update a valid limit, and invoke a safe operation.

```text
Spring ApplicationContext
   |
   +-- WorkerPoolControl (@ManagedResource)
   |      +-- getActiveWorkers() (@ManagedAttribute)
   |      +-- getMaxWorkers()    (@ManagedAttribute)
   |      +-- setMaxWorkers()    (@ManagedAttribute)
   |      +-- resetStatistics()  (@ManagedOperation)
   |
   +-- JMX export infrastructure
            |
            v
       MBeanServer
            |
            v
com.example.training:type=WorkerPool,name=primary
            |
            v
       JConsole / JMX client
```

## 2. Distinguishing Annotations and the Registration Process

| Component | Role |
|---|---|
| `@ManagedResource` | Marks a class/resource for the exporter to extract management metadata |
| `@ManagedAttribute` | Exposes a getter/setter as a JMX attribute |
| `@ManagedOperation` | Exposes a method as a JMX operation |
| `@EnableMBeanExport` | Enables annotation-based JMX export in the Spring context |
| `MBeanExporter` | Registers beans into the MBeanServer; can be configured explicitly |
| `MBeanServer` | Registry of MBeans running within a JVM |
| `ObjectName` | Unique identifier of an MBean within an MBeanServer |
| `MBeanInfo` | Describes the exposed attributes, operations, and notifications |

Simply adding `@ManagedResource` to a class does not mean an MBean is registered successfully. The class must be managed by Spring as a bean, the JMX infrastructure must be active, the object name must be valid, and it must not collide with an existing registration.

Example:

```java
@ManagedResource(objectName = "com.example.training:type=WorkerPool,name=primary")
public class WorkerPoolControl {
    // ...
}
```

If the application does not create a `WorkerPoolControl` instance in the Spring context, the exporter has no suitable bean to scan or register.

## 3. Environment Setup

The examples use Java 17 or later, Spring Framework 6.x, and Maven. You can use a compatible Spring Boot application, but to avoid confusion between Boot auto-configuration and Spring Framework JMX, the main section uses a plain Spring context.

Minimal Maven dependencies:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>${spring.version}</version>
  </dependency>
</dependencies>
```

In `pom.xml`, set `spring.version` to a Spring Framework version appropriate for your JDK, or use dependency management already governed by your project. Avoid hardcoding different Spring module versions in the same application.

The JMX API resides in the Java platform (`java.management` module). When using a modular application, declare `requires java.management;` and the necessary Spring modules according to your project's module design.

You can create the package:

```text
src/main/java/com/example/training/
  WorkerPoolControl.java
  TrainingJmxConfig.java
  TrainingApplication.java
  JmxInspector.java
```

## 4. Create a Resource with @ManagedResource

First, build a POJO that manages a simulated worker pool. In a real application, you should use a management facade wrapping an actual executor or worker service; this example is simplified to make testing operations easy.

```java
package com.example.training;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.training:type=WorkerPool,name=primary",
    description = "Training worker pool controls"
)
public class WorkerPoolControl {
    private final AtomicInteger activeWorkers = new AtomicInteger(3);
    private volatile int maxWorkers = 8;
    private final AtomicInteger processedJobs = new AtomicInteger(42);

    @ManagedAttribute(description = "Currently active workers")
    public int getActiveWorkers() {
        return activeWorkers.get();
    }

    @ManagedAttribute(description = "Maximum allowed workers")
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(description = "Set the maximum worker count")
    public void setMaxWorkers(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("maxWorkers must be 1..64");
        }
        maxWorkers = value;
    }

    @ManagedAttribute(description = "Processed job counter")
    public int getProcessedJobs() {
        return processedJobs.get();
    }

    @ManagedOperation(description = "Reset the processed job counter")
    public void resetStatistics() {
        processedJobs.set(0);
    }

    // Internal method not marked for JMX.
    public void internalMaintenance() {
        activeWorkers.set(0);
    }
}
```

### Explanation

- `@ManagedResource` declares metadata for the resource and specifies an explicit ObjectName.
- Getters with `@ManagedAttribute` create readable attributes; `getMaxWorkers` paired with `setMaxWorkers` creates a read/write attribute.
- `resetStatistics()` is a JMX operation because it has `@ManagedOperation`.
- `internalMaintenance()` is not annotated; with an annotation-based metadata assembler, this method is intentionally not exposed.
- The setter validates input values. A JMX operation can come from an operations tool, so validation must happen on the server.

**Do not expose all public methods** merely because they are in the class. Treat the MBean surface as a management API and restrict it to what is genuinely needed.

## 5. Enable JMX Annotation Export

Spring Framework provides `@EnableMBeanExport` to register beans with the appropriate management annotations:

```java
package com.example.training;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class TrainingJmxConfig {

    @Bean
    public WorkerPoolControl workerPoolControl() {
        return new WorkerPoolControl();
    }
}
```

With this configuration, Spring creates a `WorkerPoolControl` instance in the application context, and the JMX infrastructure can then export it as an MBean with the declared ObjectName.

Choose only one primary export mechanism. If your project already enables `spring.jmx.enabled=true` in Spring Boot and has JMX auto-configuration active, check to avoid creating a duplicate exporter via `@EnableMBeanExport` or a manually declared `MBeanExporter`.

## 6. Run the Spring Context and Keep the Application Alive

To give JConsole time to connect to the JVM, the demo application needs to keep the process alive after the Spring context has initialized.

```java
package com.example.training;

import java.util.concurrent.CountDownLatch;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class TrainingApplication {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext ctx =
                 new AnnotationConfigApplicationContext(TrainingJmxConfig.class)) {

            System.out.println("JMX demo started; PID = " + ProcessHandle.current().pid());
            System.out.println("Use JConsole to inspect WorkerPool MBean.");

            new CountDownLatch(1).await();
        }
    }
}
```

This is a local demo example. `CountDownLatch.await()` keeps the program waiting until interrupted; when an appropriate stop signal is issued, the context closes and the exporter gets the chance to unregister the MBeans it owns. Do not use this infinite wait pattern to design lifecycles for production applications.

## 7. Verify ObjectName Using MBeanServer

Do not rely solely on startup logs. Use the JMX API to verify that the MBean is registered:

```java
package com.example.training;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxInspector {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.training:type=WorkerPool,name=primary"
        );

        System.out.println("registered = " + server.isRegistered(name));

        if (server.isRegistered(name)) {
            MBeanInfo info = server.getMBeanInfo(name);

            for (var attr : info.getAttributes()) {
                System.out.printf(
                    "%s type=%s read=%s write=%s%n",
                    attr.getName(), attr.getType(),
                    attr.isReadable(), attr.isWritable()
                );
            }

            for (var operation : info.getOperations()) {
                System.out.println("operation=" + operation.getName());
            }
        }
    }
}
```

**Important:** another Java process calling `ManagementFactory.getPlatformMBeanServer()` only obtains its own server, not the MBeanServer of the demo JVM. To inspect from Java, run the inspector in the same process or connect remotely via `JMXConnector` to the target JVM. If you run `JmxInspector` as a standalone program, `registered=false` does not prove that the demo export failed.

To test in the same JVM, you can invoke the inspection logic right after the context is initialized, or inject the `MBeanServer` used by the exporter.

## 8. Inspect the Resource with JConsole

Lab steps:

1. Run `TrainingApplication` and note its PID.
2. Open `jconsole` from a suitable JDK.
3. Select the demo JVM from the local processes list and connect.
4. Open the **MBeans** tab.
5. Locate the `com.example.training` domain and select `type=WorkerPool,name=primary`.
6. Open **Attributes** to view `ActiveWorkers`, `MaxWorkers`, and `ProcessedJobs`.
7. Read the current value of `MaxWorkers` and try writing a valid value, such as 12.
8. Open **Operations** to invoke `resetStatistics()`.
9. Read `ProcessedJobs` again to verify the counter reset to 0.

JConsole may display key properties in different tree layouts depending on the JDK version. If you do not see the MBean, verify the JVM/PID, the MBeanServer used by the exporter, and the actual ObjectName.

You do not need to open a remote JMX port just to use JConsole with a local JVM in a development environment; opening a remote connector has its own security implications.

## 9. Call the MBean Using the Java JMX API

In the same JVM and against the right MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.training:type=WorkerPool,name=primary"
);

int previous = (Integer) server.getAttribute(name, "MaxWorkers");
System.out.println("maxWorkers before=" + previous);

server.setAttribute(name, new Attribute("MaxWorkers", 12));

int updated = (Integer) server.getAttribute(name, "MaxWorkers");
System.out.println("maxWorkers after=" + updated);

server.invoke(
    name,
    "resetStatistics",
    new Object[0],
    new String[0]
);
```

For operations with parameters, you must pass the exact Java type signature. For example, `resize(int)` requires the signature `new String[]{"int"}`, not `java.lang.Integer` just because values in `Object[]` are boxed.

## 10. Alternative Explicit MBeanExporter Configuration

Besides the annotation-driven exporter, Spring also lets you declare an explicit `MBeanExporter`. If you use this approach for a POJO with Spring JMX annotations, configure an assembler that reads metadata:

```java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;

@Bean
AnnotationJmxAttributeSource jmxSource() {
    return new AnnotationJmxAttributeSource();
}

@Bean
MetadataMBeanInfoAssembler jmxAssembler(AnnotationJmxAttributeSource source) {
    MetadataMBeanInfoAssembler assembler = new MetadataMBeanInfoAssembler();
    assembler.setAttributeSource(source);
    return assembler;
}

@Bean
MBeanExporter customExporter(
        WorkerPoolControl control,
        MetadataMBeanInfoAssembler assembler) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of(
        "com.example.training:type=WorkerPool,name=primary",
        control
    ));
    return exporter;
}
```

This is an **alternative configuration** to `@EnableMBeanExport`, not an additional exporter to run concurrently for the same bean. Exporter/naming/assembler components in specific applications may require extra configuration depending on how POJOs are exported; verify metadata in the MBeanServer rather than just seeing that the bean was created.

## 11. Distinguishing @ManagedResource from @ManagedAttribute and @ManagedOperation

```java
@ManagedResource(objectName = "com.example.training:type=Cache,name=products")
public class CacheControl {

    @ManagedAttribute
    public int getSize() {
        return 100;
    }

    @ManagedOperation
    public void clearCache() {
        // ...
    }
}
```

`@ManagedResource` identifies and describes the class/resource. It does not mean every field or public method is exposed. `@ManagedAttribute` describes a property with a getter/setter, and `@ManagedOperation` describes an action.

Some bean getters may be processed by the assembler according to the configured metadata. Do not assume an unannotated public method is a JMX operation when using an annotation metadata assembler.

## 12. ObjectName Considerations

ObjectName pattern:

```text
com.example.training:type=WorkerPool,name=primary
```

This consists of:

- Domain `com.example.training`: the application's JMX namespace.
- Key `type=WorkerPool`: the resource type.
- Key `name=primary`: the instance identifier.

Within the same MBeanServer, an ObjectName is unique. If two Spring beans share the same ObjectName, `InstanceAlreadyExistsException` can occur. When you have multiple worker pools, use distinct names:

```text
com.example.training:type=WorkerPool,name=primary
com.example.training:type=WorkerPool,name=background
```

Do not put passwords, tokens, personal emails, or sensitive data into an ObjectName. Names are commonly displayed in JMX clients, monitoring tools, and logs.

Across different JVM replicas, identical ObjectNames in two JVMs do not directly collide because each JVM has its own MBeanServer. Monitoring must distinguish the endpoint/target of each replica.

## 13. Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| MBean not visible even though class has `@ManagedResource` | Bean is not in the Spring context or exporter is not enabled | Check `@Bean`, `@ComponentScan`, `@EnableMBeanExport` |
| `InstanceAlreadyExistsException` | Duplicate ObjectName or two exporters | Check the exporter list and `queryNames` |
| `MalformedObjectNameException` | Domain/key property name has invalid syntax | Instantiate `new ObjectName(...)` and validate |
| MBean exists but attribute is missing | Getter/setter missing `@ManagedAttribute` or wrong assembler | Inspect `MBeanInfo.getAttributes()` |
| Operation missing | Method missing `@ManagedOperation` | Inspect `MBeanInfo.getOperations()` |
| `AttributeNotFoundException` | Wrong JMX attribute name, e.g., `maxWorkers` instead of `MaxWorkers` | Read attribute metadata |
| `InvalidAttributeValueException` or business exception | Written value is invalid | Compare validation range and data type |
| JConsole connects but does not see the resource | Connected to the wrong JVM/server | Compare PID, JMX endpoint, and MBeanServer reference |
| JMX operation runs with wrong AOP behavior | Bean is proxied; invocation path bypasses interceptors | Inspect facade/proxy and test at runtime |
| Bean is unregistered when context closes | Exporter manages registration lifecycle | Check owner/context shutdown |

## 14. Scaling to Multiple Environments

In a Spring Boot application, you can enable JMX export depending on the version:

```properties
spring.jmx.enabled=true
```

However, check the auto-configuration of the Boot version you are using. Do not also enable `@EnableMBeanExport` if it creates a second exporter for the same bean and ObjectName. Actuator JMX endpoints are also distinct from custom application MBeans annotated with `@ManagedResource`; Actuator exposure configuration does not replace application resources/annotations.

In Docker/Kubernetes, remote JMX requires special attention to authentication, TLS, and RMI networking. For a local demo, do not expose remote JMX ports broadly.

## 15. Automated Testing of Exported Resources

A good integration test should verify:

1. The Spring context starts and the bean is exported.
2. The MBeanServer contains the expected ObjectName.
3. `MaxWorkers` is readable/writable as intended.
4. `ActiveWorkers` and `ProcessedJobs` are readable, and not writable when only getters exist.
5. `resetStatistics` is present in the operations list.
6. Writing a valid `MaxWorkers` value succeeds.
7. Writing an out-of-range value is rejected and state remains unchanged.
8. After the context closes, registrations owned by the exporter are cleaned up.

Example assertion skeleton:

```java
ObjectName name = new ObjectName(
    "com.example.training:type=WorkerPool,name=primary"
);

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
assertTrue(
    java.util.Arrays.stream(info.getOperations())
        .anyMatch(op -> op.getName().equals("resetStatistics"))
);
```

For tests, use an MBeanServer controlled by the test context or a dedicated name to avoid collisions with other applications. Never let tests invoke sensitive operations on production.

## 16. Practice Exercises

### Exercise 1 — Minimal resource

Add `@ManagedResource(objectName="com.example.training:type=Cache,name=users")` to a `UserCacheControl` class, add a `getEntryCount()` getter annotated with `@ManagedAttribute`, and verify that the `EntryCount` attribute appears.

### Exercise 2 — Read/write attribute

Add `getCapacity()` and `setCapacity(int)` with `@ManagedAttribute`, validated for 1..10000. Use JConsole to test writing a valid value and an invalid value.

### Exercise 3 — Operation

Add `@ManagedOperation` to `refreshCache()`. Use the JMX API or JConsole to invoke the operation and read a counter proving it ran.

### Exercise 4 — Two instances

Create two resources `primary` and `secondary`. Explain why they must not share one ObjectName and verify they reside in the same domain with different `name` keys.

### Exercise 5 — Duplicate exporter

Enable both `@EnableMBeanExport` and an explicit `MBeanExporter` exporting that same bean. Observe the collision error in a test environment, then choose a single configuration to own registration.

### Exercise 6 — Limit the surface

Add an unannotated public helper method and verify that the method does not appear in the operations list when using an annotation metadata assembler.

## 17. Completion Checklist

- The bean is created and managed by Spring.
- The class is annotated with `@ManagedResource` and a valid ObjectName.
- Necessary getters/setters have `@ManagedAttribute`.
- Permitted actions have `@ManagedOperation`.
- The Spring JMX exporter is enabled exactly once.
- The bean registers in the MBeanServer that JConsole/the client connects to.
- The ObjectName is unique and contains no sensitive data.
- Values written through JMX are validated.
- `MBeanInfo` metadata matches the expected attributes/operations.
- Lifecycle/unregistration and access permissions are tested before real deployment.

## 18. Summary

`@ManagedResource` is the starting point for turning a Spring-managed POJO into a resource manageable via JMX. However, the class annotation must be paired with the JMX export infrastructure, a valid ObjectName, and `@ManagedAttribute`/`@ManagedOperation` metadata for clients to see the right management interface. The lab should conclude by verifying the ObjectName, inspecting `MBeanInfo`, reading/writing a valid attribute, and invoking a safe operation in JConsole. Runtime verification prevents the misconception that annotations automatically expose all methods or automatically open remote JMX connections.
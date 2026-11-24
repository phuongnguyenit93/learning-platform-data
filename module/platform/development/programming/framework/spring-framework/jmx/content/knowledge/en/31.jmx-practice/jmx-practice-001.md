# Practice: Exporting a Spring Bean with MBeanExporter

## 1. Lab Objectives

In this lab, you will build a small Spring Framework application, create a Java bean representing a job processor, use **`MBeanExporter`** to expose that bean as a **JMX MBean**, and inspect it using `MBeanServer`, JConsole, or a Java JMX client.

After completing this lab, you will be able to:

- Explain the roles of `MBeanExporter`, `MBeanServer`, `ObjectName`, `MBeanInfo`, and Spring's JMX annotations.
- Create a Spring bean with a readable attribute, a writable attribute, and a safe management operation.
- Explicitly configure `MBeanExporter` in Java `@Configuration` to export a single specific bean, without enabling remote JMX.
- Use `AnnotationJmxAttributeSource`, `MetadataMBeanInfoAssembler`, and `MetadataNamingStrategy` for annotation-based export.
- Start the `ApplicationContext`, look up the MBean using `isRegistered`, read attributes, and invoke an operation.
- Inspect the runtime `MBeanInfo` to see what the bean has exposed and verify that internal APIs are not exposed.
- Identify common errors such as duplicate `ObjectName`, wrong server, missing metadata, or mismatched method signatures.
- Write a lifecycle test to verify that the MBean is unregistered after closing the context.

**Scope:** Local lab in a single JVM, using the platform `MBeanServer`; no remote RMI connector, JMX credentials, or firewall changes are required. The operations will not delete data or access production services.

## 2. Architecture You Will Build

```text
Java application (single JVM)
   |
   +-- Spring ApplicationContext
   |       |
   |       +-- JobController bean
   |       |      +-- getQueueDepth()
   |       |      +-- getMaxWorkers()
   |       |      +-- setMaxWorkers(int)
   |       |      +-- requestPause()
   |       |
   |       +-- MBeanExporter bean
   |              |
   |              +-- AnnotationJmxAttributeSource
   |              +-- MetadataMBeanInfoAssembler
   |              +-- MetadataNamingStrategy
   |              |
   |              v
   +-- Platform MBeanServer
             |
             +-- com.example.lab:type=Worker,name=Importer
             |
             +-- JConsole or Java client
```

`MBeanExporter` is the bridge between a Spring-managed bean and the JMX registration mechanism. `ObjectName` identifies the MBean within an `MBeanServer`; `MBeanInfo` describes the attributes/operations that a client actually sees. There is no requirement for the bean to open its own socket or run its own HTTP server.

## 3. Prerequisites

You need:

- A JDK with the `java.management` module and an inspection tool such as `jconsole` (typically included with the JDK).
- Maven or an equivalent Java build tool.
- Spring Framework, specifically `spring-context` and JMX-related dependencies.
- An IDE or terminal to run the Java application.
- A lab environment containing no sensitive data.

The examples use **Java 17+** and a Spring Framework 6.x version compatible with the project JDK. If you are using Spring Framework 7 or Spring Boot 4, check the corresponding Java/dependency versions; the sample code is based on the Spring JMX APIs named in this article.

### 3.1. Minimal Maven Configuration

Reference `pom.xml` file:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>spring-jmx-export-lab</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>6.2.0</spring.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>${spring.version}</version>
    </dependency>
  </dependencies>
</project>
```

The version above is only a configuration example for learning; in production deployments, use an organization-supported Spring release managed consistently via BOM/dependency management. In a Spring Boot application, you typically do not need to declare these libraries manually if the appropriate starter already brings them in.

## 4. Define the Management Contract Before Coding

In this lab, a worker managing an import queue has the following elements:

| Element | Type | Access | Meaning |
| --- | --- | --- | --- |
| `QueueDepth` | `long` | Read | Number of pending jobs. |
| `MaxWorkers` | `int` | Read/Write | Concurrency limit from 1 to 16. |
| `Running` | `boolean` | Read | Whether the worker is in the running state. |
| `requestPause()` | `void` operation | Control | Requests a graceful pause. |

`MaxWorkers` is bounded in the setter because allowing a client to assign an arbitrary number is dangerous. `requestPause()` only updates state in this lab; in a real application, it must delegate to a service with proper lifecycle, authorization, and auditing.

Fixed ObjectName:

```text
com.example.lab:type=Worker,name=Importer
```

Do not put passwords, tokens, customer emails, or dynamic payloads into an ObjectName.

## 5. Step 1 — Create the Spring-Managed Bean

Create the file `src/main/java/com/example/lab/JobController.java`:

```java
package com.example.lab;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.lab:type=Worker,name=Importer",
    description = "Importer worker management"
)
public final class JobController {

    private final AtomicLong queueDepth = new AtomicLong(12);
    private final AtomicInteger maxWorkers = new AtomicInteger(4);
    private final AtomicBoolean running = new AtomicBoolean(true);

    @ManagedAttribute(description = "Queued jobs (count)")
    public long getQueueDepth() {
        return queueDepth.get();
    }

    @ManagedAttribute(description = "Maximum parallel workers")
    public int getMaxWorkers() {
        return maxWorkers.get();
    }

    @ManagedAttribute(description = "Set maximum parallel workers")
    public void setMaxWorkers(int value) {
        if (value < 1 || value > 16) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 16"
            );
        }
        maxWorkers.set(value);
    }

    @ManagedAttribute(description = "Whether worker is running")
    public boolean isRunning() {
        return running.get();
    }

    @ManagedOperation(
        description = "Request a graceful pause of importer"
    )
    public void requestPause() {
        running.set(false);
    }

    public void eraseInternalState() {
        // Not a JMX operation defined in the lab.
    }
}
```

**Key points to note:** `@ManagedResource` defines resource-level metadata; `@ManagedAttribute` describes getters/setters; `@ManagedOperation` exposes an operation. The annotations take effect only when the exporter uses the corresponding metadata source.

### 5.1. Why use AtomicLong/AtomicInteger/AtomicBoolean?

A JMX client may read or write state concurrently with other threads. Atomic types help illustrate thread-safe reads/writes for simple fields. They do **not** replace the synchronization design of a real job processing system, but are suitable for a small JMX lab.

### 5.2. Why not annotate every public method?

A management API must be designed as an intentional contract. The `eraseInternalState()` method exists so you can verify that the appropriate metadata assembler does **not** automatically expose every public method when annotation-based exposure is specified.

## 6. Step 2 — Configure MBeanExporter

Create the file `src/main/java/com/example/lab/JmxLabConfig.java`:

```java
package com.example.lab;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxLabConfig {

    @Bean
    public JobController jobController() {
        return new JobController();
    }

    @Bean
    public MBeanServer jmxMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy strategy =
            new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    public MBeanExporter jmxExporter(
            MBeanServer jmxMBeanServer,
            JobController jobController,
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setBeans(Map.of(
            "jobController", jobController
        ));
        return exporter;
    }
}
```

This is an **explicit** configuration: a single `JobController` bean is exported based on metadata and named by the naming strategy, using the platform MBeanServer. There is no need to enable `@EnableMBeanExport` at the same time, since the lab creates the exporter manually.

### 6.1. What does each component do?

| Component | Responsibility |
| --- | --- |
| `MBeanServer` | The actual registry and dispatcher for JMX. |
| `AnnotationJmxAttributeSource` | Reads metadata from Spring's JMX annotations. |
| `MetadataMBeanInfoAssembler` | Builds `MBeanInfo` based on the metadata that was read. |
| `MetadataNamingStrategy` | Generates an ObjectName from the resource's metadata. |
| `MBeanExporter` | Registers the resource into the MBeanServer when the Spring context initializes. |
| `setBeans(Map.of(...))` | Specifies the exact bean to export, without relying on autodetection. |

In another application, you might configure `MBeanExporter` by bean name or via annotation-based configuration. In this lab, however, it is best to keep one clear path for easy diagnosis.

## 7. Step 3 — Start the ApplicationContext

Create the file `src/main/java/com/example/lab/App.java`:

```java
package com.example.lab;

import java.lang.management.ManagementFactory;
import java.util.concurrent.TimeUnit;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class App {
    public static void main(String[] args) throws Exception {
        ObjectName objectName = new ObjectName(
            "com.example.lab:type=Worker,name=Importer"
        );

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxLabConfig.class)) {

            System.out.println(
                "MBean registered: "
                    + server.isRegistered(objectName)
            );

            MBeanInfo info = server.getMBeanInfo(objectName);
            System.out.println(
                "MBean description: " + info.getDescription()
            );

            System.out.println(
                "Initial queue depth: "
                    + server.getAttribute(objectName, "QueueDepth")
            );

            System.out.println(
                "Initial running: "
                    + server.getAttribute(objectName, "Running")
            );

            System.out.println("Open JConsole to inspect this JVM.");
            TimeUnit.SECONDS.sleep(60);
        }

        System.out.println(
            "MBean registered after close: "
                + server.isRegistered(objectName)
        );
    }
}
```

During the 60 seconds that the context stays open, you can use JConsole to inspect and interact with the bean. This wait period is only for the lab, not how production systems operate. When the context closes, the exporter performs cleanup for the MBean it registered according to the lifecycle.

### 7.1. Sample Output

```text
MBean registered: true
MBean description: Importer worker management
Initial queue depth: 12
Initial running: true
Open JConsole to inspect this JVM.
...
MBean registered after close: false
```

The specific values may change if you interact with the MBean while it is running. If `MBean registered: false`, do not just change the ObjectName arbitrarily; check the exporter, metadata source, and target server.

## 8. Step 4 — Find the MBean in JConsole

1. Run the application from your IDE or terminal.
2. Open `jconsole` from the JDK on the same machine.
3. Select the exact JVM/PID running `com.example.lab.App` in the Local Process list.
4. Open the **MBeans** tab.
5. Find the `com.example.lab` domain.
6. Expand the key properties `type=Worker` and `name=Importer` according to how JConsole displays them.
7. Check the **Attributes** and **Operations** sections.

Expected result:

```text
com.example.lab
  type=Worker
    name=Importer
      Attributes
        QueueDepth = 12
        MaxWorkers = 4
        Running = true
      Operations
        requestPause()
```

Do not worry if the tree structure in JConsole looks slightly different due to how JConsole orders key properties. The exact `ObjectName` value is the JMX identifier.

### 8.1. Try reading an attribute

Select `QueueDepth`; JConsole should display the value `12`. This is a read-only attribute.

### 8.2. Try writing an attribute

Select `MaxWorkers` and change its value from `4` to `8` through JConsole's interface if supported. Then read it back; the expected value is `8`.

If you try `MaxWorkers=100`, the setter will reject it with an `IllegalArgumentException` because it is out of range. Depending on the MBean type and connector, the exception may be wrapped in a JMX wrapper and displayed as an error message.

### 8.3. Try invoking an operation

Invoke `requestPause()` on the Operations tab. Then read `Running` again; it should be `false`. This lab has no real worker; the operation simply flips a flag for demonstration.

**Do not perform similar actions on production MBeans that have operations such as `shutdown()`, `clearAll()`, or `dropCache()` without authorization.**

## 9. Step 5 — Inspect Directly Using MBeanServer

If you cannot use JConsole, you can still write a Java JMX client in the same JVM:

```java
import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.lab:type=Worker,name=Importer"
);

boolean exists = server.isRegistered(name);
System.out.println("Registered: " + exists);

Object depth = server.getAttribute(name, "QueueDepth");
System.out.println("Depth: " + depth);

server.setAttribute(
    name,
    new Attribute("MaxWorkers", 8)
);

server.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);

System.out.println(
    "Running after pause: "
        + server.getAttribute(name, "Running")
);
```

The `ObjectName` must match what the exporter registered. If the exporter uses a custom `MBeanServer` instead of the platform server, the snippet must be updated to query that server.

## 10. Step 6 — Read MBeanInfo and Verify Metadata

Merely seeing the MBean in JConsole is not enough. You need to verify the actual contract:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getDescription());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s, type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation=%s, return=%s, parameters=%d%n",
        operation.getName(),
        operation.getReturnType(),
        operation.getSignature().length
    );
}
```

Expected metadata:

| Element | Type | Read | Write |
| --- | --- | --- | --- |
| `QueueDepth` | `long` | Yes | No |
| `MaxWorkers` | `int` | Yes | Yes |
| `Running` | `boolean` | Yes | No |
| `requestPause` | `void` operation | N/A | N/A |

Important: `eraseInternalState()` is **not** exposed when annotation metadata is configured properly. If it appears, check the assembler and exposure policy in use.

### 10.1. Metadata is not authorization

`MBeanAttributeInfo.isWritable()` indicates that the attribute has an exposed setter; it does **not** mean that a specific JMX account is permitted to write to it. A read-only connector can still disallow `setAttribute` even when the metadata says writable.

With remote JMX, security is a separate layer and must be tested with an actual authenticated client.

## 11. Step 7 — Write an Integration Test

A test can initialize the context, inspect `MBeanInfo`, interact via `MBeanServer`, and ensure cleanup:

```java
package com.example.lab;

import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class MBeanExportIntegrationTest {

    @Test
    void exportsBeanAndUnregistersOnClose() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.lab:type=Worker,name=Importer"
        );

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    JmxLabConfig.class)) {

            assertTrue(server.isRegistered(name));
            assertEquals(
                12L,
                server.getAttribute(name, "QueueDepth")
            );

            server.setAttribute(
                name, new Attribute("MaxWorkers", 8)
            );
            assertEquals(
                8,
                server.getAttribute(name, "MaxWorkers")
            );

            server.invoke(
                name, "requestPause",
                new Object[0], new String[0]
            );
            assertEquals(
                false,
                server.getAttribute(name, "Running")
            );

            boolean hidden = java.util.Arrays.stream(
                server.getMBeanInfo(name).getOperations()
            ).anyMatch(op ->
                "eraseInternalState".equals(op.getName()));
            assertFalse(hidden);
        }

        assertFalse(server.isRegistered(name));
    }
}
```

This test requires the appropriate JUnit Jupiter dependency. If other tests run in the same JVM, be careful when using a fixed `ObjectName`: running multiple contexts in parallel can cause `InstanceAlreadyExistsException`. Use a per-test ObjectName or configure test isolation.

### 11.1. Do not test only by calling the bean directly

```java
JobController controller = context.getBean(JobController.class);
controller.requestPause();
```

The snippet above proves that the Java logic works, but it does **not** prove that the exporter registered the bean or that JMX dispatch works properly. A JMX integration test must invoke through `MBeanServer` and read the actual metadata.

## 12. Understand Registration and Unregistration Lifecycle

Spring's `MBeanExporter` registers MBeans during container/exporter initialization according to the framework lifecycle. When the context closes properly, the exporter cleans up the MBeans it manages.

```text
ApplicationContext.refresh()
        |
        v
MBeanExporter initialized
        |
        v
MBeanServer.registerMBean(...)
        |
        v
JConsole / client can inspect
        |
        v
ApplicationContext.close()
        |
        v
MBeanExporter cleanup
        |
        v
MBean no longer registered
```

If the JVM is killed forcefully, Java cleanup callbacks are not guaranteed to run. However, the registry inside that JVM also terminates with the process. For tests running in the same JVM, an unclosed context can leave old MBeans behind, causing conflicts for subsequent tests.

## 13. Why Choose an Explicit Exporter Over Autodetect?

`MBeanExporter` has several ways to determine which beans to export:

- Explicitly map beans via `setBeans(...)`.
- Autodetect by management interface or assembler/autodetection.
- Annotation-driven configuration via the Spring context.

In a first practice lab, explicit mapping has several advantages:

1. Easy to identify the exact bean being exported.
2. Easy to see which beans the exporter is managing.
3. Reduces the risk of unintentionally exposing beans.
4. Easy to diagnose duplicate `ObjectName` errors.
5. Does not depend on autodetection scanning the entire context.

When scaling up an application, you can consider annotation-based autodetect to reduce configuration, but you must write tests for the `MBeanInfo` contract and exposure security.

## 14. Comparison with @EnableMBeanExport

Spring also supports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class AnnotationDrivenJmxConfig {
}
```

The annotation-driven approach can create/configure an exporter through Spring's infrastructure. **Do not add it to a lab that already uses an explicit `MBeanExporter`** if both could register the same `ObjectName`.

In Spring Boot, auto-configuration with `spring.jmx.enabled` may also create an exporter depending on the version/configuration. If you create a manual exporter, establish clear ownership and avoid duplicate registration.

## 15. RegistrationPolicy and Duplicate ObjectNames

If an ObjectName already exists in the same `MBeanServer`, attempting to register it again can cause:

```text
javax.management.InstanceAlreadyExistsException:
com.example.lab:type=Worker,name=Importer
```

Spring provides `RegistrationPolicy` values such as `FAIL_ON_EXISTING`, `IGNORE_EXISTING`, and `REPLACE_EXISTING` to govern behavior when a name already exists.

Example:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
    RegistrationPolicy.FAIL_ON_EXISTING
);
```

In this lab, the fail-on-existing policy helps surface misconfigurations. Do not switch to `REPLACE_EXISTING` to mask a conflict without first identifying which component owns the existing MBean. `IGNORE_EXISTING` can also cause tests to think registration succeeded when they are actually observing an old MBean.

### 15.1. Common sources of duplicates

- Two Spring contexts sharing the platform MBeanServer.
- Two exporters exporting the same bean.
- Code registering directly via the JMX API before Spring.
- A previous test that did not close its context.
- Multiple modules sharing the same domain/type/name.
- A Spring Boot auto-exporter coexisting with a manual exporter.

The proper fix is to clarify ownership and naming conventions, not merely changing the registration policy.

## 16. Common Export Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `isRegistered=false` | Exporter not initialized or wrong ObjectName. | Check context, naming strategy, and target server. |
| `InstanceAlreadyExistsException` | Duplicate MBean name. | Close old contexts; ensure a single owner per name. |
| `MalformedObjectNameException` | Name contains unquoted special characters. | Use a valid `ObjectName`. |
| `NotCompliantMBeanException` | Bean does not follow JMX conventions or incompatible adapter. | Check assembler/metadata and MBean type. |
| `ReflectionException` on invoke | Wrong operation name/signature. | Inspect `MBeanInfo.getOperations()`. |
| `AttributeNotFoundException` | Attribute not exposed or wrong name. | Inspect `MBeanInfo.getAttributes()`. |
| Attribute not writable | Setter not exported or blocked by security policy. | Check metadata and connector permissions. |
| JConsole does not see the app | Connected to the wrong JVM or app already exited. | Check PID; keep the context alive during the lab. |
| Operation exposes internal method | Assembler/exposure is not an allowlist as intended. | Check `MetadataMBeanInfoAssembler`. |
| MBean still exists after test | Context not closed or unclear owner. | Clean up via lifecycle; inspect registry. |

## 17. Reading Logs When Export Fails

For diagnosis, you can raise the log level of the Spring JMX package in a lab environment:

```properties
logging.level.org.springframework.jmx=DEBUG
logging.level.org.springframework.jmx.export=DEBUG
```

The properties above use Spring Boot logging syntax; in plain Spring Framework, configure the corresponding logging backend. Not every Spring version is guaranteed to emit the exact same log messages. Reading the exception cause chain and inspecting the registry are more reliable sources of truth than a specific log line.

For example, if `BeanCreationException` wraps `MBeanExportException` and inside it is `InstanceAlreadyExistsException`, the root cause is likely an ObjectName conflict rather than a missing bean.

## 18. Local JMX Does Not Need a Remote Port

In this lab, everything runs in a single JVM and you use:

```java
ManagementFactory.getPlatformMBeanServer()
```

Therefore, you do not need:

```text
-Dcom.sun.management.jmxremote.port=9010
```

`MBeanExporter` does not automatically open a remote JMX port. If you want to connect from another machine, you must separately configure a connector/JVM management agent along with authentication, TLS, firewall rules, and the appropriate RMI hostname/port. Never expose unauthenticated remote JMX to a public environment.

## 19. Extending the Lab: Isolated MBeanServer

In a complex integration test, you can create an isolated `MBeanServer` to reduce collisions with the platform registry:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer isolated =
    MBeanServerFactory.createMBeanServer("com.example.lab");
```

Then inject this server into both `MBeanExporter` and the test client. When using a custom server, a local JConsole platform connection may not display MBeans in the custom server the same way it does for the platform server. You need to connect through the appropriate server/connector.

Make sure to release/clean up resources created by the test and avoid accidentally holding references that cause test leaks.

## 20. Extending the Lab: MBeanExporterListener

Spring provides `MBeanExporterListener` to track which MBeans are registered/unregistered by the exporter:

```java
import javax.management.ObjectName;
import org.springframework.jmx.export.MBeanExporterListener;

public final class LoggingRegistrationListener
        implements MBeanExporterListener {

    @Override
    public void mbeanRegistered(ObjectName name) {
        System.out.println("Registered: " + name);
    }

    @Override
    public void mbeanUnregistered(ObjectName name) {
        System.out.println("Unregistered: " + name);
    }
}
```

Attach the listener:

```java
exporter.setListeners(
    new LoggingRegistrationListener()
);
```

A listener helps observe successful lifecycle events, but there is no standard callback that receives every failed registration exception. For failures, you still have to inspect the exporter's exceptions/logs.

## 21. Extension: Impact of AOP Proxies

In real applications, a bean may be wrapped in a Spring AOP proxy due to `@Transactional`, `@Async`, or another aspect. When `MBeanExporter`/the assembler introspects a proxy, metadata can depend on how it resolves the target class and management interface.

To avoid complex dependencies for the management API:

- Create a dedicated management adapter annotated with `@ManagedResource` and selected operations.
- Have the adapter inject the Spring-managed service interface/proxy.
- Keep management methods short and control side effects.
- Test runtime `MBeanInfo` after AOP is enabled.
- Do not use a runtime proxy class name as an ObjectName.

In the basic lab, `JobController` has no AOP, so the export path is easy to trace. An advanced exercise can test a service proxy and compare the metadata.

## 22. Security When Writing a Management API

An MBean can expose operations that have major impacts on the JVM. Therefore:

1. **Expose only the necessary API**; do not arbitrarily export every public method.
2. **Prefer read-only attributes** for monitoring.
3. **Validate setter/operation arguments**; do not trust client data.
4. **Do not return sensitive secrets** through attributes or ObjectNames.
5. **Do not let long operations block JMX threads**; use a request ID + async job when needed.
6. **Protect remote connectors** with authentication, authorization, TLS, and a management network.
7. **Audit operations with side effects** using a trusted identity.
8. **Inspect `MBeanInfo`** to ensure internal methods are not exposed.

Do not treat the `@ManagedOperation` annotation as an authorization rule. It only defines metadata to expose an operation.

## 23. Lab Self-Assessment

You should be able to answer these questions yourself:

**1. What does `MBeanExporter` do?** Selects beans and registers them as MBeans in an MBeanServer.

**2. Why is `@ManagedResource` not enough without an exporter?** Because metadata annotations alone do not perform registration into the registry.

**3. What is `ObjectName` used for?** Uniquely identifying an MBean within the same MBeanServer.

**4. Why use `MetadataMBeanInfoAssembler`?** To build `MBeanInfo` based on annotation metadata read by the attribute source.

**5. Why inspect `MBeanInfo`?** To see the actual attributes, operations, signatures, and read/write capabilities.

**6. Why does `MaxWorkers` need validation?** Because a JMX client can pass unreasonable values and affect resources.

**7. Why should `eraseInternalState` not appear in Operations?** Because it is an internal method not meant to be exposed.

**8. If an exporter registers an MBean in a custom server, will querying the platform server find it?** Not necessarily; you must check the right server.

**9. When the context closes, what happens to MBeans managed by the exporter?** The exporter performs unregistration according to its lifecycle.

**10. Why shouldn't you use `REPLACE_EXISTING` to silence duplicate-name errors?** Because you could accidentally replace an MBean belonging to another component.

## 24. Extension Exercises

### Exercise A — Add an operation with parameters

Add:

```java
@ManagedOperation(description = "Adjust queue depth for lab")
public void setQueueDepthForLab(long value) {
    if (value < 0 || value > 1000) {
        throw new IllegalArgumentException(
            "Queue depth out of lab range"
        );
    }
    queueDepth.set(value);
}
```

Verify that the `MBeanInfo` signature is `long`; when calling `MBeanServer.invoke`, pass the signature array `new String[] {"long"}` instead of `java.lang.Long`.

### Exercise B — Add parameter metadata

Apply `@ManagedOperationParameters` and `@ManagedOperationParameter` to describe `value`. Inspect the information in `MBeanOperationInfo.getSignature()` after export.

### Exercise C — Add a listener

Attach an `MBeanExporterListener`, log on registration/unregistration, and verify that callbacks fire during the lifecycle.

### Exercise D — Conflict test

Pre-register an MBean with the same ObjectName in an isolated MBeanServer. Test the exporter with `FAIL_ON_EXISTING` and observe the exception, then clean up reliably.

### Exercise E — Switch MBean type

Create a Standard MBean via a `JobControllerMBean` interface. Compare the differences between Standard MBean conventions and Spring metadata-based Model MBeans using `MBeanInfo`.

## 25. Summary

You have learned how to **export a Spring bean as a JMX MBean using `MBeanExporter`**: defining the resource, attributes, and operation with annotations; configuring the metadata source, assembler, and naming strategy; selecting the platform MBeanServer; registering a specific bean; inspecting it via JConsole; and verifying via the JMX API.

The key takeaway is **do not stop once the ApplicationContext starts successfully**. Check the registered `ObjectName`, read `MBeanInfo`, test safe operations in the lab, confirm internal APIs are not exposed, and verify unregistration when the context closes. In real applications, manage exporter ownership, secure remote JMX, limit operation side effects, and maintain integration tests.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — `MBeanExporter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — `ManagedResource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — `MetadataMBeanInfoAssembler`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — `MetadataNamingStrategy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Java SE 21 — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — `MBeanInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
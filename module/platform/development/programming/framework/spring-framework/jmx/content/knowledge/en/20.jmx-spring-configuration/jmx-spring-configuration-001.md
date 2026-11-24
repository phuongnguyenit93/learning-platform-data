# Configuring JMX with Java Config in Spring Framework

## Learning Objectives

This lesson belongs to the **Spring configuration** group of Spring Framework JMX. After completing it, you will be able to:

- Understand the key components when configuring Java Management Extensions (JMX) with Spring Java configuration: `@Configuration`, `@Bean`, `MBeanServer`, `MBeanExporter`, and `ObjectName`.
- Create a Standard MBean and export a Spring object using Java Config, without XML.
- Know the difference between explicit export using `MBeanExporter` and annotation-driven export via `@EnableMBeanExport`.
- Attach a specific `MBeanServer` to an exporter, and control registration names and registration policy.
- Run, inspect, and invoke an MBean using `MBeanServer` or JConsole.
- Identify issues related to lifecycle, multiple instances, multiple exporters, Spring AOP proxies, and Spring Boot auto-configuration.

## 1. Overview: Spring JMX and Java Config

JMX is a standard Java mechanism that allows a JVM to expose management objects called MBeans. An MBean can provide **attributes** to monitor or adjust state, **operations** to perform actions, and **metadata** so management tools understand the contract.

Spring Framework supports JMX integration so applications can register Spring-managed objects into an `MBeanServer` without manually writing all the `registerMBean`/unregister code inside business logic.

With Java Config, we declare components using a `@Configuration` class and `@Bean` factory methods:

```text
@Configuration
   |
   +-- @Bean -> Managed Spring object
   |
   +-- @Bean -> MBeanServer
   |
   +-- @Bean -> MBeanExporter
                    |
                    +-- setServer(MBeanServer)
                    +-- setBeans(ObjectName -> bean)
                    |
                    v
               JMX Registry
                    |
                    v
            JConsole / JMX client
```

In this model, the **Spring bean name** (for example `jobMonitor`) and the **JMX `ObjectName`** (for example `com.example.jobs:type=JobMonitor,name=primary`) are two separate namespaces. The exporter decides which object appears in JMX and under what name.

## 2. Required Libraries

Spring JMX is part of Spring Framework. For a standalone Maven project, `spring-context` provides the IoC components and related JMX support. Example dependency structure:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>${spring.version}</version>
    </dependency>
</dependencies>
```

`spring.version` must be defined according to the dependency management set in the project. With Spring Boot, you should use Boot's dependency management/BOM instead of manually picking individual Spring Framework versions.

Core JMX APIs such as `MBeanServer` and `ObjectName` belong to the JDK (`javax.management`). In Java 9+, they reside in the `java.management` module. Spring JMX annotations reside in the `org.springframework.jmx.export.annotation` package, not `javax.management`.

There is no need to enable JMX remote to practice within the same JVM. JMX remote is only needed when a client in another process/machine must connect to the server via a connector; in that case, security and networking must also be configured.

## 3. Step 1 — Declare a Standard MBean

Create a standard JMX interface. The Standard MBean convention requires the management interface to be named `<ImplementationClassName>MBean`.

**JobMonitorMBean.java**

```java
package com.example.jmx;

public interface JobMonitorMBean {
    int getProcessedCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void resetStatistics();
}
```

**JobMonitor.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class JobMonitor implements JobMonitorMBean {
    private final AtomicInteger processed = new AtomicInteger();
    private volatile boolean enabled = true;

    public void recordProcessedJob() {
        if (enabled) {
            processed.incrementAndGet();
        }
    }

    @Override
    public int getProcessedCount() {
        return processed.get();
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void resetStatistics() {
        processed.set(0);
    }
}
```

`JobMonitor` is a POJO that can be managed by Spring while also implementing the JMX contract through `JobMonitorMBean`.

| Method | JMX Element | Access |
| --- | --- | --- |
| `getProcessedCount()` | Attribute `ProcessedCount` | Read-only |
| `isEnabled()` and `setEnabled(boolean)` | Attribute `Enabled` | Read/write |
| `resetStatistics()` | Operation `resetStatistics` | Invoke |
| `recordProcessedJob()` | Not in the Standard MBean interface | Internal method only |

You should not expose every business method to JMX. The management contract should be small, intentional, and limit operations with side effects.

## 4. Step 2 — Declare @Configuration, @Bean, and MBeanExporter

The explicit configuration below uses the JVM's platform `MBeanServer` and exports a single Spring bean via JMX.

**JmxConfiguration.java**

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter jobMonitorExporter(
            JobMonitor jobMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jobs:type=JobMonitor,name=primary",
                jobMonitor));
        return exporter;
    }
}
```

Each component has its own role:

1. `jobMonitor()`: creates the instance that business logic and JMX will manage together.
2. `platformMBeanServer()`: returns the existing JVM server; Spring only **uses** this server and does not own its lifecycle.
3. `jobMonitorExporter(...)`: creates the exporter, injects the exact object and server, and maps the JMX name to the instance.
4. `setServer(...)`: avoids ambiguity when multiple MBean servers exist.
5. `setBeans(...)`: specifies exactly which object is exported and the desired `ObjectName`.

When `ApplicationContext` initializes, `MBeanExporter` is managed by the Spring lifecycle and registers the MBean. There is no need to manually call `ManagementFactory.getPlatformMBeanServer().registerMBean(...)` again with the same `ObjectName`; doing so will cause a conflict.

## 5. Step 3 — Launch ApplicationContext

You can run the hands-on example in a plain Spring Framework application:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxDemoApplication {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            JobMonitor monitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            System.out.println("Registered: " + server.isRegistered(name));

            monitor.recordProcessedJob();
            monitor.recordProcessedJob();

            System.out.println(
                    "ProcessedCount: "
                    + server.getAttribute(name, "ProcessedCount"));

            System.out.println("PID: " + ProcessHandle.current().pid());
            System.out.println("Press Enter to close context.");
            System.in.read();
        }
    }
}
```

With the correct configuration, it prints `Registered: true` and `ProcessedCount: 2`. The `getAttribute` call goes through the JMX registry, so the result proves the exporter has placed the MBean into the server under the expected name.

`System.in.read()` only keeps the test program running so you can open JConsole. In a real web application/server, the lifecycle is managed by the runtime. When the context closes, the exporter can unregister the MBeans it registered; this is different from releasing the JVM's platform server.

## 6. Step 4 — Inspect in JConsole

JConsole usually comes with the JDK and supports observing local JVM MBeans. Steps:

1. Run `JmxDemoApplication`.
2. Open `jconsole` from the matching JDK.
3. Select the right Java process by the printed PID.
4. Open the **MBeans** tab.
5. Find the domain `com.example.jobs`.
6. Select the MBean `type=JobMonitor,name=primary`.
7. Read `ProcessedCount` and `Enabled`, and test the `resetStatistics` operation.
8. In the test environment, change `Enabled=false` or invoke `resetStatistics`, then compare the new values.

Each JMX client may display key properties in a different order, but `ObjectName` still identifies the registration. If you do not see the MBean, check the PID/JVM, the server used by the exporter, whether the context is still running, and `isRegistered(name)` before assuming Java Config is broken.

## 7. Configuring Multiple MBeans in Java Config

An exporter can register multiple beans under distinct names:

```java
@Bean("primaryJobMonitor")
public JobMonitor primaryJobMonitor() {
    return new JobMonitor();
}

@Bean("secondaryJobMonitor")
public JobMonitor secondaryJobMonitor() {
    return new JobMonitor();
}
```

When injecting two beans of the same type, use a qualifier:

```java
@Bean
public MBeanExporter multiMonitorExporter(
        @org.springframework.beans.factory.annotation.Qualifier(
                "primaryJobMonitor") JobMonitor primary,
        @org.springframework.beans.factory.annotation.Qualifier(
                "secondaryJobMonitor") JobMonitor secondary,
        MBeanServer platformMBeanServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(platformMBeanServer);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary", primary,
            "com.example.jobs:type=JobMonitor,name=secondary", secondary));
    return exporter;
}
```

This is **an alternative** to the `jobMonitorExporter` configuration in section 4; do not enable both exporters for the same `ObjectName`. Two Spring instances of the same Java class are valid; each instance only needs a unique `ObjectName` within the same server.

Both can share `JobMonitorMBean`, and JMX will control the exact instance by the name `primary` or `secondary`. The Spring bean name and JMX name remain two separate namespaces.

## 8. RegistrationPolicy on Duplicate ObjectName

If an `ObjectName` already exists in the server, the exporter needs a handling policy. Spring Framework provides `RegistrationPolicy` with the following options:

- `FAIL_ON_EXISTING`: throws an error when the name is already registered.
- `IGNORE_EXISTING`: keeps the existing MBean and skips the new registration at that name.
- `REPLACE_EXISTING`: replaces the old registration with the new MBean.

In Java Config:

```java
import org.springframework.jmx.support.RegistrationPolicy;

exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING);
```

Duplicate name errors are usually a sign of a naming strategy or lifecycle issue. You should not choose `IGNORE_EXISTING` just to "make startup succeed" if you actually need to expose the new MBean: JMX clients may still read data from the old instance. With `REPLACE_EXISTING`, you must understand the registration owner and the impact on active management tools.

Older Spring versions may use integer constants like `REGISTRATION_FAIL_ON_EXISTING` and different configuration methods. When implementing, choose the API appropriate for the dependency version in use.

## 9. Using @ManagedResource and @EnableMBeanExport Instead of *MBean Interfaces

Spring also has **annotation-driven JMX exporting**. Instead of implementing the `JobMonitorMBean` interface, a POJO can declare Spring JMX metadata:

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.jobs:type=AnnotatedJobMonitor,name=primary",
        description = "Managed job metrics")
public class AnnotatedJobMonitor {

    private final AtomicInteger processed = new AtomicInteger();

    @ManagedAttribute(description = "Processed job count")
    public int getProcessedCount() {
        return processed.get();
    }

    @ManagedOperation(description = "Reset processed counter")
    public void resetStatistics() {
        processed.set(0);
    }
}
```

Enable annotation exporting in Java Config:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class AnnotationJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public AnnotatedJobMonitor annotatedJobMonitor() {
        return new AnnotatedJobMonitor();
    }
}
```

`@EnableMBeanExport` enables export support based on Spring JMX annotations. `@ManagedResource` marks a bean as a managed object; `@ManagedAttribute` and `@ManagedOperation` define the exposed elements. `@ManagedResource` by itself does not create a Spring bean if the class is not registered via `@Bean` or appropriate component scanning.

**Choose only one model for the same JMX name**: explicit export with `MBeanExporter` or annotation-based exporter. If you accidentally enable both mechanisms registering the same `ObjectName`, you may encounter `InstanceAlreadyExistsException`.

## 10. Configuring JMX with Java Config and a Custom MBeanServer

Using the platform server is not mandatory. Spring provides `MBeanServerFactoryBean` to create or locate a custom server:

```java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class CustomMBeanServerConfiguration {

    @Bean(name = "applicationMBeanServer")
    public MBeanServerFactoryBean applicationMBeanServer() {
        MBeanServerFactoryBean factory = new MBeanServerFactoryBean();
        factory.setDefaultDomain("com.example.management");
        factory.setLocateExistingServerIfPossible(false);
        return factory;
    }
}
```

If an exporter needs a custom server, inject that `MBeanServer` product bean into `setServer`. `MBeanServerFactoryBean` is managed by the container, so the lifecycle of the server created by the factory can be handled via initialization and destroy callbacks.

Exporter example:

```java
@Bean
public MBeanExporter customExporter(
        JobMonitor monitor,
        @org.springframework.beans.factory.annotation.Qualifier(
                "applicationMBeanServer") MBeanServer server) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.management:type=JobMonitor,name=custom", monitor));
    return exporter;
}
```

This configuration is **a variant of the previous exporter**; do not register the same object/name a second time without intent. A custom `MBeanServer` has its own registry; local JConsole may be observing the platform server instead of the custom server. When clients need to access the custom server, an appropriate connection/connector must be designed.

## 11. Naming Strategy and ObjectName

An `ObjectName` has the form:

```text
domain:key1=value1,key2=value2
```

Examples:

```text
com.example.jobs:type=JobMonitor,name=primary
com.example.jobs:type=JobMonitor,name=secondary
com.example.db:type=PoolMonitor,pool=read
```

Spring has naming strategy mechanisms such as `KeyNamingStrategy`, `MetadataNamingStrategy`, and `IdentityNamingStrategy`, depending on how the exporter is configured. When using `setBeans(Map.of("fullObjectName", bean))`, we explicitly control the name, which is convenient for learning and debugging.

In large systems, the naming convention should contain domain, type, and a distinguishing key per instance to avoid collisions. `ObjectName` values containing special characters must be quoted/escaped according to JMX standards. Do not put secrets or sensitive information into displayed names.

If you want stable monitoring dashboards, avoid relying on random object identity that changes on every restart, unless that is a genuine requirement.

## 12. Ensuring the Same Spring Bean Is Exported via JMX

A common mistake is when the Spring service uses one instance while the exporter registers a different instance:

```java
@Bean
public MBeanExporter wrongExporter(MBeanServer server) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary",
            new JobMonitor())); // New instance, not the business bean.
    return exporter;
}
```

The configuration may register a valid MBean, but the counter in JConsole will not reflect actual processing flow. The right way is to inject the exact bean used by the business service:

```java
@Bean
public MBeanExporter correctExporter(
        JobMonitor monitor,
        MBeanServer server) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(
            "com.example.jobs:type=JobMonitor,name=primary", monitor));
    return exporter;
}
```

When multiple beans have the same Java type, use `@Qualifier` to specify the right instance. A correct `ObjectName` pointing to the wrong object is still a functional bug, because clients receive an unexpected data source.

## 13. ApplicationContext Lifecycle and Cleanup

`MBeanExporter` is a Spring bean with lifecycle callbacks. When the context initializes, the exporter registers MBeans. When the context closes normally, it unregisters the registrations it manages.

```text
ApplicationContext refresh
    |
    +-- JobMonitor Spring bean
    +-- MBeanServer
    +-- MBeanExporter.register
    |
Application running
    |
ApplicationContext close
    |
    +-- MBeanExporter.unregister
    +-- Destroy remaining beans
```

You should not use an independent static MBean registration without cleanup if the application can reload the context multiple times in the same JVM. Leftover registrations can cause the new initialization to hit duplicate names or clients to keep reading the old instance.

The platform `MBeanServer` belongs to the JVM, so it is not released just because one context closes. If Spring uses a custom server created by a factory bean, the server owner needs to manage release according to lifecycle; the exporter must have the opportunity to unregister before the server is released.

## 14. Spring AOP Proxies and the JMX Exporter

Spring beans can be wrapped by AOP proxies due to `@Transactional`, security, or logging aspects. When exporting such a bean, you must determine which object is actually registered by the MBean exporter and which metadata is used to build the management interface.

You should not assume JMX calls always go through all advice or always bypass advice. Behavior depends on whether the exporter registers the Spring proxy or the target object and how introspection is configured. For systems with dynamic proxies, inspect the MBean metadata and runtime behavior.

If a stable management interface is needed, you can create a separate management facade:

```java
public class JobAdminFacade {
    private final JobService jobService;

    public JobAdminFacade(JobService jobService) {
        this.jobService = jobService;
    }

    public long getProcessedCount() {
        return jobService.getProcessedCount();
    }
}
```

Then use the appropriate approach among Standard MBean, assembler, or Spring JMX annotations to expose only the desired management methods. A management facade helps reduce the risk of exposing sensitive business methods.

## 15. Inspecting via MBeanInfo and Operations

Read metadata from the server to confirm the exporter exposed the right interface:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.jobs:type=JobMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean is not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

for (var attribute : info.getAttributes()) {
    System.out.println(
            "Attribute: " + attribute.getName()
            + " / " + attribute.getType());
}

for (var operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
```

The snippet assumes an existing `context` variable of an appropriate `ApplicationContext` type. `isRegistered` proves the name is in the registry; `getMBeanInfo` proves the metadata that the JMX server is exposing. When verifying the exact instance, read an identifying attribute or compare behavior after changing the state of the injected bean.

If another MBean was already registered under the same `ObjectName` beforehand and the exporter uses an ignore/replace policy, checking `isRegistered` alone is not enough to conclude the new bean is the target.

## 16. JUnit Integration Test for Java Config

An integration test should create a real `ApplicationContext` and read from the JMX registry:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class JmxConfigurationTest {

    @Test
    void exportsJobMonitorWithExpectedAttributes() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            JobMonitor monitor = context.getBean(JobMonitor.class);
            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jobs:type=JobMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            monitor.recordProcessedJob();
            assertEquals(
                    1, server.getAttribute(name, "ProcessedCount"));

            server.invoke(
                    name,
                    "resetStatistics",
                    new Object[0],
                    new String[0]);

            assertEquals(
                    0, server.getAttribute(name, "ProcessedCount"));
        }
    }
}
```

In a test suite running in parallel, sharing the platform `MBeanServer` and the same `ObjectName` can cause conflicts. You must isolate the test server or use a distinct domain/name per fixture. The test must also close the context so the exporter cleans up.

This test proves registration, reading an attribute, and invoking an operation; it is an integration test of the path Java Config → exporter → JMX registry, rather than merely checking that the class has `@Configuration`.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Spring context has the bean, but JConsole does not see it | Missing exporter, wrong `ObjectName`, wrong JVM/server | Check `isRegistered` on the right server |
| `InstanceAlreadyExistsException` | Duplicate JMX name across exporters/contexts | Use unique names and a single clear owner |
| `NotCompliantMBeanException` | Standard MBean interface or types do not comply with JMX | Verify `JobMonitor implements JobMonitorMBean` |
| Counter differs between service and JMX | Exporter registered a different instance than the business bean | Inject the same bean into the exporter |
| Missing attribute | Interface/annotation/assembler does not expose the method | Read `MBeanInfo` and inspect metadata |
| Configured `@EnableMBeanExport` but bean not visible | Bean is not in the context or lacks appropriate management metadata | Check `@ManagedResource` and exporter |
| MBean disappears when context closes | Exporter unregisters according to lifecycle | Verify the context is still alive |
| Two beans of the same type cause injection ambiguity | Missing qualifier | Use `@Qualifier` or a specific bean name |
| Custom server does not appear in local JConsole | JConsole looks at the platform server | Connect to the custom server or use the API directly |
| Only fails when running the full test suite | Tests share server/names | Isolate fixtures and clean up contexts |

## 18. JMX Security and Operation Management

JMX can expose state-changing operations: `resetStatistics`, `clearCache`, `reloadRules`, `pauseQueue`, or `shutdown`. Java Config only determines registration and metadata; it **does not automatically provide** a fine-grained authorization layer for every operation.

When used in production:

1. Expose only the minimum necessary attributes/operations.
2. Do not put secrets or customer data into JMX attributes.
3. Validate preconditions before executing operations with side effects.
4. Protect remote JMX with authentication, encryption, and network restrictions.
5. Record appropriate logs/metrics to identify which operation ran and the resulting state.
6. Do not blindly retry non-idempotent operations when a connection drops.
7. Design stable `ObjectName` values that do not contain sensitive information.

For applications that only need metrics/health, consider other suitable observability approaches. JMX remains useful when direct management of JVM MBeans within the same process or via a compatible JMX client is required.

## 19. Practice Exercises

**Exercise 1 — Standard MBean with Java Config.** Create `CacheMonitorMBean` and `CacheMonitor`, and export them under `com.example.cache:type=CacheMonitor,name=primary`. Verify `CacheSize` using JConsole and `MBeanServer.getAttribute`.

**Exercise 2 — Multiple instances.** Create two beans `primaryCacheMonitor` and `secondaryCacheMonitor` of the same class. Use one `MBeanExporter` to register two distinct `ObjectName` values; verify that changing one instance does not affect the other.

**Exercise 3 — Annotation exporting.** Create a class with `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation`, then enable `@EnableMBeanExport`. Compare the metadata of the annotation-based MBean with the Standard MBean from exercise 1.

**Exercise 4 — Conflict handling.** Intentionally use two exporters with the same `ObjectName` in a test environment. Observe the error and fix it using a clear naming strategy, instead of choosing ignore when two MBeans are needed.

**Exercise 5 — Lifecycle.** Read `isRegistered(name)` before and after `ApplicationContext.close()`. Explain the difference between registration cleanup and the platform MBean server lifecycle.

**Exercise 6 — Local proxy.** Add an `MBeanProxyFactoryBean` to access an exported MBean. Compare calling through the local proxy with calling the Spring bean directly in terms of execution path and metadata.

## Conclusion

Configuring JMX with Java Config in Spring Framework brings Spring objects to the JMX registry via `@Configuration`, `@Bean`, `MBeanServer`, and `MBeanExporter`, or via annotation support such as `@EnableMBeanExport`. The explicit model uses **bean → ObjectName → exporter → MBeanServer** to control which instance is exposed. The annotation model uses `@ManagedResource` metadata and management annotations to select the exposed interface. Regardless of the approach chosen, verify registration via `MBeanServer`, manage lifecycles clearly, avoid duplicate names, and protect operations with side effects.

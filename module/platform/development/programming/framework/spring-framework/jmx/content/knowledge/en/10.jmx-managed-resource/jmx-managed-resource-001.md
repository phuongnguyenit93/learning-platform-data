# @ManagedResource Marks a Bean Managed via JMX in Spring Framework

## 1. Learning Objectives

In Spring Framework JMX, the `@ManagedResource` annotation marks a Java class as a **managed resource** that Spring can export to Java Management Extensions (JMX). This annotation is the starting point for metadata-driven JMX configuration: it describes the identity and meaning of a resource, while specific attributes and operations are exposed through their corresponding annotations.

After this lesson, you will be able to:

- Explain which Spring component `@ManagedResource` belongs to and how it differs from `@Component` or Spring Boot Actuator annotations.
- Know how to declare `objectName`, `description`, and select managed resource metadata.
- Understand the roles of `MBeanExporter`, `AnnotationJmxAttributeSource`, and `MetadataMBeanInfoAssembler`.
- Write a bean with `@ManagedResource` along with the required attributes/operations, register it into an `MBeanServer`, and read it from a JMX client.
- Distinguish **marking a resource** from **actual MBean registration**, and recognize scenarios where no MBean appears after adding the annotation.
- Manage ObjectNames, exposure scope, lifecycle, and security when an application has multiple beans.

## 2. What Is @ManagedResource?

`@ManagedResource` resides in the package:

```java
org.springframework.jmx.export.annotation.ManagedResource
```

This annotation can be placed on a class that Spring exports as an MBean. It provides resource-level metadata so that Spring can build the `MBeanInfo` model and identify the MBean according to the exporter configuration.

Minimal example:

```java
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main",
    description = "Runtime cache monitoring resource"
)
public class CacheMonitor {
}
```

Here:

- `objectName` is the JMX name identifying the MBean in an `MBeanServer`.
- `description` is a technical description for the resource, which management tools can display when reading `MBeanInfo`.
- The annotation itself **does not create a network endpoint**, does not open JMX Remote, does not guarantee the bean is registered, and does not automatically expose every public method.

For a resource to be useful, you typically need to mark internal members with `@ManagedAttribute` and `@ManagedOperation`, and configure Spring JMX to read metadata and export the bean.

## 3. ManagedResource and Related Concepts

```text
Spring ApplicationContext
       |
       +-- Managed bean (class)
       |       @ManagedResource
       |       @ManagedAttribute
       |       @ManagedOperation
       |
       +-- AnnotationJmxAttributeSource
       |       reads annotation metadata
       |
       +-- MetadataMBeanInfoAssembler
       |       builds the JMX management interface
       |
       +-- MBeanExporter
               |
               | registers with ObjectName
               v
           MBeanServer
               |
               +--> MBeanInfo / attributes / operations
               +--> JMX client: JConsole, management code
```

Different roles:

| Component | Responsibility |
| --- | --- |
| `@ManagedResource` | Marks the resource and describes class-level metadata |
| `@ManagedAttribute` | Describes a readable/writable management attribute |
| `@ManagedOperation` | Describes an invocable management operation |
| `AnnotationJmxAttributeSource` | Reads Spring's JMX annotations |
| `MetadataMBeanInfoAssembler` | Converts metadata into `MBeanInfo` components |
| `MBeanExporter` | Registers beans into an `MBeanServer` |
| `ObjectName` | Identifies the MBean in the JMX registry |
| `MBeanServer` | Server that manages MBeans and handles management requests |

Three steps must be kept distinct: **marking with annotations → Spring reading metadata → exporter registering into the server**. One step succeeding does not replace the remaining steps.

## 4. Complete Bean Example with @ManagedResource

Suppose an application wants to observe a runtime cache and support clearing counters for operational needs. The following bean represents simple management state:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main",
    description = "Management view of application cache counters"
)
public class CacheMonitor {

    private final AtomicInteger entryCount = new AtomicInteger();
    private volatile boolean enabled = true;

    @ManagedAttribute(
        description = "Current number of recorded cache entries"
    )
    public int getEntryCount() {
        return entryCount.get();
    }

    @ManagedAttribute(description = "Whether tracking is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Enable or disable tracking")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Reset the entry counter")
    public void resetCounter() {
        entryCount.set(0);
    }

    public void recordEntry() {
        if (enabled) {
            entryCount.incrementAndGet();
        }
    }
}
```

Meaning of each annotation:

- `@ManagedResource` applies to the `CacheMonitor` class: this is a resource that JMX metadata can describe.
- The `getEntryCount()` getter has `@ManagedAttribute`: exposes a read-only `EntryCount` attribute.
- The `isEnabled()` / `setEnabled(...)` getter and setter are marked: exposes a readable and writable `Enabled` attribute.
- `resetCounter()` has `@ManagedOperation`: exposes an operation that has a state-mutating effect.
- `recordEntry()` is unmarked: this is an internal business method and is not exposed by an annotation-based assembler merely because it is public.

The JMX management surface should be designed intentionally and should not correspond to every public API on the bean. Especially for state-mutating operations, control who can invoke them and what the execution result is.

## 5. Adding the Bean to Spring ApplicationContext

A JMX annotation is not synonymous with Spring component registration. If you want Spring to manage the bean, you can declare `@Bean`:

```java
package com.example.monitoring;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MonitorBeanConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }
}
```

Or place `@Component` on the class and enable appropriate component scanning.

```java
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main"
)
public class CacheMonitor {
    // ...
}
```

The two annotations serve two different systems:

- `@Component` helps Spring discover and create the bean in `ApplicationContext`.
- `@ManagedResource` provides JMX metadata so the bean can be exported as a managed resource.

A class with only `@ManagedResource` that is not instantiated as a bean or passed to `MBeanExporter` will not necessarily have any object in the JMX registry. Conversely, an ordinary `@Component` is not necessarily exposed as an MBean.

## 6. Configuring Annotation-Based Export

### 6.1. Annotation-Driven Declaration

Spring supports enabling annotation-based MBean export; in Java configuration you can use `@EnableMBeanExport`:

```java
package com.example.monitoring;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxExportConfig {
}
```

When this mechanism is enabled in a context containing the `CacheMonitor` bean, Spring sets up the exporter infrastructure to find and process marked managed resources. Details such as server selection, naming, and registration policy can be adjusted according to Spring configuration and the version in use.

Example of starting a standalone Spring application:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(
            MonitorBeanConfig.class,
            JmxExportConfig.class
        )) {

    // The JMX exporter is initialized alongside the ApplicationContext.
    // You can inspect the MBean on the selected MBeanServer.
}
```

This is a concise choice for hands-on exercises. It only takes effect within the `ApplicationContext` that receives the configuration; it does not automatically apply to all other contexts in the same JVM.

### 6.2. Manual Configuration to Clearly See Component Roles

You can configure `MBeanExporter` and the metadata assembler explicitly:

```java
package com.example.monitoring;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class ExplicitJmxConfig {

    @Bean
    public CacheMonitor cacheMonitor() {
        return new CacheMonitor();
    }

    @Bean
    public MBeanServer jmxServer() {
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
    public MBeanExporter mbeanExporter(
            CacheMonitor cacheMonitor,
            MBeanServer jmxServer,
            MetadataMBeanInfoAssembler assembler) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(jmxServer);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=CacheMonitor,name=Main",
            cacheMonitor
        ));
        exporter.setAssembler(assembler);
        return exporter;
    }
}
```

In this configuration:

1. `CacheMonitor` is created by Spring.
2. `jmxServer` selects the JVM's platform MBeanServer.
3. `AnnotationJmxAttributeSource` reads metadata from annotations on classes/methods.
4. `MetadataMBeanInfoAssembler` builds the JMX model from that metadata.
5. `MBeanExporter` registers the bean under a specific ObjectName.

The example above uses **only one** exporter mechanism. You should not both declare `@EnableMBeanExport` and create a manual exporter for the same bean without a clear design, as this can register duplicate names.

### 6.3. Where Should ObjectName Be Declared?

The `@ManagedResource(objectName = "...")` example shows the intended identity in metadata. When calling `MBeanExporter.setBeans(Map.of("...", bean))`, the exporter also receives an explicit registration name.

Both pieces of information must be consistent. If you want the ObjectName to be taken directly from the annotation, use a naming strategy or an annotation-driven mechanism that supports the corresponding metadata. If you want easy control during manual configuration, you can keep the explicit name in `setBeans(...)` and use the same string in the annotation to avoid conflicts.

## 7. Important Attributes of @ManagedResource

`@ManagedResource` has metadata fields for describing and identifying an MBean, among which `objectName` and `description` are the two most common.

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main",
    description = "Cache counters for operational monitoring"
)
```

### 7.1. objectName

`objectName` describes the JMX name, following the structure:

```text
domain:key=value,key2=value2
```

Example:

```text
com.example.monitoring:type=CacheMonitor,name=Main
```

ObjectName is a JMX key, not a class name, Spring bean name, or user-friendly dashboard title. It must be valid according to `javax.management.ObjectName` syntax and unique within an MBeanServer.

If there are multiple instances of the same type, distinguish them using key properties:

```text
com.example.monitoring:type=CacheMonitor,name=Main,instance=1
com.example.monitoring:type=CacheMonitor,name=Main,instance=2
```

Stable names are very important because JConsole, monitoring tools, alert rules, and scripts may store the ObjectName for access. Renaming it can break older clients trying to locate the MBean.

### 7.2. description

Description helps operators understand the MBean or management component:

```java
@ManagedResource(
    description = "Runtime management of application cache counters"
)
```

The description can be placed into `MBeanInfo` by the metadata assembler. It differs from ObjectName: description is for human readers, while ObjectName serves routing. A dashboard may display the description as help text, but should not use it as a unique key.

### 7.3. Additional Management Metadata

Spring Framework versions also support several other metadata attributes for resources such as `currencyTimeLimit`, `log`, `logFile`, `persistPolicy`, `persistPeriod`, `persistName`, and `persistLocation`. Their meaning relates to management descriptions and the JMX metadata model, but **does not imply that Spring automatically provides a persistence system, logging, or remote protocol** for every resource simply because the annotation has those fields.

When these attributes are needed, check their exact meaning in the Spring version and MBean/assembler type being used. For typical use cases, starting with `objectName`, `description`, and the necessary `@ManagedAttribute` / `@ManagedOperation` annotations is an easy-to-understand choice.

## 8. Reading the MBean After Export

After the context initializes, you can use the Java JMX API to verify that the resource is registered and that its metadata is correct.

```java
import java.lang.management.ManagementFactory;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=CacheMonitor,name=Main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean was not exported: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);
System.out.println("MBean: " + name.getCanonicalName());
System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
```

If the exporter is configured for a different server—for example, a container-managed server or one created separately by `MBeanServerFactoryBean`—you must inspect **that exact server**. An MBean may register successfully yet not appear in the platform server because the exporter used a different server.

When metadata is configured as in section 4, expected results include:

| Attribute | Read | Write |
| --- | --- | --- |
| `EntryCount` | Yes | No |
| `Enabled` | Yes | Yes |

You can read and write:

```java
import javax.management.Attribute;

int entries = (Integer) server.getAttribute(
    name, "EntryCount"
);

server.setAttribute(
    name, new Attribute("Enabled", Boolean.FALSE)
);

boolean enabled = (Boolean) server.getAttribute(
    name, "Enabled"
);
```

Do not attempt to write `EntryCount` because the metadata only exposes a getter, with no management setter. If `getAttribute` or `setAttribute` fails, distinguish between name errors, read/write permission errors, data type errors, and errors from bean logic.

## 9. How Do @ManagedResource and @ManagedAttribute Differ?

The two annotations have different scopes:

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main"
)
public class CacheMonitor {

    @ManagedAttribute
    public int getEntryCount() {
        return 42;
    }
}
```

- `@ManagedResource` states **this is a resource described for management via JMX**.
- `@ManagedAttribute` states **the corresponding method is described as a management attribute**.
- `@ManagedOperation` states **the corresponding method is described as a management operation**.

A class having `@ManagedResource` does not mean all public methods become operations or every getter becomes an attribute. When using `MetadataMBeanInfoAssembler`, per-member metadata determines the exposed surface.

The annotations also do not mean every action is safe. If annotations are placed on setters or operations that change runtime configuration, security and authorization must be considered.

## 10. Relationship with @Component, @Bean, and Spring Boot

### 10.1. @ManagedResource Is Not a Spring Container Stereotype

`@ManagedResource` marks a role in JMX. The Spring container still needs to know how to create the instance:

```java
@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=CacheMonitor,name=Main"
)
public class CacheMonitor {
}
```

or:

```java
@Bean
CacheMonitor cacheMonitor() {
    return new CacheMonitor();
}
```

Do not confuse the **bean discovery** mechanism with the **bean export** mechanism.

### 10.2. Spring Boot Actuator Is Not Synonymous with Core JMX

Spring Boot Actuator has its own management and metrics mechanisms and can provide JMX endpoints in certain configurations. Those endpoints are features of Spring Boot Actuator and depend on dependencies, exposure configuration, version, and security. Meanwhile, `@ManagedResource` and `MBeanExporter` belong to Spring Framework JMX.

You can use Spring Framework JMX in a Spring Boot application, but you should not infer that adding `@ManagedResource` will automatically enable all Actuator endpoints or open an HTTP management path.

### 10.3. Spring Bean Lifecycle and MBean Lifecycle

Spring beans are created, configured, and destroyed according to the `ApplicationContext`. The exporter participates in the lifecycle to register/unregister MBeans. When the context closes, MBeans owned by the exporter are typically cleaned up accordingly.

If a bean is registered directly outside Spring, unregistration must be managed by the owner of that registration. Avoid unregistering MBeans belonging to a container or other components yourself.

## 11. Common Pitfalls

### 11.1. Annotation Is Present but No MBean Appears

Common causes:

- The class has `@ManagedResource` but no bean was created in the Spring context.
- JMX export infrastructure has not been enabled or the exporter was not initialized.
- Manual configuration has an exporter but lacks a suitable metadata assembler/attribute source.
- The exporter registers into a different MBeanServer than the one the tool is connecting to.
- Invalid or duplicate ObjectName, or naming configuration does not behave as expected.
- Spring JMX configuration resides in a different context from the bean to be exported.
- Bean initialization or lifecycle errors prevented the exporter from registering successfully.

Diagnosis steps: check that the bean exists in `ApplicationContext`; verify the exporter ran; confirm the server and ObjectName; call `isRegistered(name)`; then read `MBeanInfo`.

### 11.2. MBean Appears but Attributes/Operations Are Missing

First check:

1. Do the getter/setter or operation have the appropriate annotation?
2. Does the assembler in use read Spring annotations?
3. Does the method have a valid signature for the JMX model being built?
4. Is there another export configuration overriding how the assembler exposes the interface?
5. Are you mistakenly looking at another MBean with the same name on a different server?

If `MBeanInfo` lacks the expected attribute, calling `getAttribute` will not make it appear. You must fix the export/metadata contract and reinitialize according to the appropriate lifecycle.

### 11.3. Duplicate ObjectName

An ObjectName must be unique within an MBeanServer. If two exporters or two resources both register:

```text
com.example.monitoring:type=CacheMonitor,name=Main
```

`InstanceAlreadyExistsException` or another registration policy outcome may occur. Assign names that distinguish instances and check who owns the registration. Do not automatically replace an existing MBean without understanding its origin.

### 11.4. Mistakenly Using the Spring Bean Name as the ObjectName

For example, the bean name is `cacheMonitor`, but the ObjectName is:

```text
com.example.monitoring:type=CacheMonitor,name=Main
```

JMX clients must use the registered ObjectName. The Spring bean name is an identifier in the container, not the default JMX name in all cases.

## 12. Real-World Scenarios and Design Decisions

### 12.1. Read-Only Status Resource

A current connection count meter only needs a getter:

```java
@ManagedResource(
    objectName = "com.example.monitoring:type=ConnectionStats,name=Primary"
)
public class ConnectionStats {

    @ManagedAttribute(description = "Active connection count")
    public int getActiveConnections() {
        return 0; // Illustrative; a real app reads from a runtime counter
    }
}
```

This is a good fit for JMX: a read-only management interface that does not expose dangerous intervention operations.

### 12.2. Resource Allowing Configuration Changes

A bean with `@ManagedAttribute` on a `setEnabled(boolean)` setter allows administrators to change state. However, the system must design for:

- Does the change take effect immediately or after a refresh cycle?
- Are there state conditions under which the setter rejects the change?
- Is auditing needed for who made the change, from which tool, and when?
- Should remote clients be allowed to write or only read?
- Is rate limiting or a confirmation operation needed?

An annotation only describes management capability; it does not automatically guarantee authorization or business rule correctness.

### 12.3. Multiple Instances of the Same Type

If the application runs multiple modules or the same bean type exports multiple instances in one JVM, use ObjectNames with distinct keys:

```text
com.example.monitoring:type=ConnectionStats,name=Primary
com.example.monitoring:type=ConnectionStats,name=Replica
```

Across multiple JVMs, the same ObjectName can exist in different MBeanServers. A multi-server monitoring dashboard must retain connection or host identity as well, not only the ObjectName.

## 13. Hands-On Exercise

Create a Spring application containing the `CacheMonitor` bean from section 4 and perform the following:

1. Initialize the bean in `ApplicationContext`.
2. Enable `@EnableMBeanExport` **or** configure `MBeanExporter` + `MetadataMBeanInfoAssembler` manually.
3. Use the platform MBeanServer in the same JVM to check the ObjectName:
   `com.example.monitoring:type=CacheMonitor,name=Main`.
4. Read `MBeanInfo.getDescription()` and the list of attributes/operations.
5. Call `getAttribute(name, "EntryCount")` and `getAttribute(name, "Enabled")`.
6. Write `Enabled=false`, read it back, and observe the result.
7. Invoke the `resetCounter()` operation via `MBeanServer.invoke(...)` if it was exposed.
8. Try invoking an internal method without `@ManagedOperation` via JMX and observe the result.
9. Close the Spring context and confirm the exporter executed the unregistration lifecycle properly for the resource it owns.

Example operation invocation:

```java
server.invoke(
    name,
    "resetCounter",
    new Object[0],
    new String[0]
);
```

Then:

```java
int current = (Integer) server.getAttribute(name, "EntryCount");
System.out.println("Entry count = " + current);
```

If the result differs from expectations, check whether an application process is concurrently incrementing the counter or whether a different MBean is being accessed.

## 14. Self-Check Questions

**1. Does `@ManagedResource` belong to the JDK or Spring Framework?** It belongs to Spring Framework's `org.springframework.jmx.export.annotation` package.

**2. Does adding `@ManagedResource` to a class automatically register it into an MBeanServer?** No. A bean instance and exporter infrastructure are required to process metadata and registration.

**3. Which annotation exposes a getter as a JMX attribute under the metadata mechanism?** `@ManagedAttribute`.

**4. Which annotation is used to describe a management operation?** `@ManagedOperation`.

**5. What does `objectName` in `@ManagedResource` mean?** The intended JMX identifier for the resource in an MBeanServer.

**6. How does `description` differ from ObjectName?** Description is a display description; ObjectName is the JMX routing key.

**7. When an MBean does not appear in JConsole, should you immediately conclude the annotation is wrong?** No. You should check the bean, exporter, server, ObjectName, and JConsole's connection path.

**8. Do `@ManagedResource` and `@Component` replace each other?** No; one annotation describes JMX metadata, while the other supports Spring bean registration.

**9. Can JMX annotations be used in Spring Boot?** Yes, because Spring Boot is built on Spring Framework; appropriate export and exposure configuration is still needed.

**10. Why shouldn't you export every public method?** Because the JMX interface is a management surface accessible from operational tools; only necessary and safe members should be exposed.

## 15. Key Takeaways

- **`@ManagedResource` marks a class** as a resource with JMX management metadata.
- **`@ManagedAttribute` and `@ManagedOperation`** describe the specific members exposed.
- **`MBeanExporter`** is responsible for registering the object into an `MBeanServer`.
- **`AnnotationJmxAttributeSource` and `MetadataMBeanInfoAssembler`** help Spring read annotations and generate JMX metadata.
- **Annotations do not replace Spring bean creation** and do not automatically enable remote connectors or Actuator.
- **ObjectName must be valid, unique within a server, and stable** for management clients.
- **Expose only the necessary management interface**, control operations with side effects, and ensure security when allowing remote access.

When using `@ManagedResource`, think along the flow: **Spring bean → JMX metadata → exporter → MBeanServer → JMX client**. This separation makes Spring Framework JMX configuration intentional and easy to diagnose when a resource does not appear or lacks the expected management interface.
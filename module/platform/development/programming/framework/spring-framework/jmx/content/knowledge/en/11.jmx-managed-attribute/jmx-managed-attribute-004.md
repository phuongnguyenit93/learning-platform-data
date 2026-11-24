# Description, Default, Descriptor, and Metadata of @ManagedAttribute in Spring Framework JMX

## 1. Context and Objectives

When a Spring bean is exported to JMX, management tools such as JConsole or Java clients can view the MBean's attributes. Beyond the attribute's value, JMX also provides **metadata**: what the attribute is named, what data type it has, whether it is readable/writable, and what description is provided for operators.

In Spring Framework, the `@ManagedAttribute` annotation allows describing a bean's getter or setter as a managed attribute. This lesson focuses on **description, default value, and descriptor/metadata**, rather than stopping at how to add the annotation. These concepts are related but distinct:

- **Description** is explanatory text describing the meaning of the attribute.
- **Default value** is metadata describing a default value; it does not automatically assign an actual value to the bean.
- **Descriptor** is an extended metadata structure in JMX containing named fields and their values.
- **MBeanAttributeInfo** provides standard attribute information such as name, type, description, readable, and writable.
- **MetadataMBeanInfoAssembler** is the Spring component that converts annotation information into the management metadata model.

After this lesson, you will be able to use `@ManagedAttribute(description = "...")`, understand `defaultValue`, inspect metadata via `MBeanServer.getMBeanInfo(...)`, read descriptors, and distinguish metadata from actual runtime state.

## 2. Model: From Annotation to JMX Metadata

```text
Spring bean
  @ManagedResource
  @ManagedAttribute
       |
       v
AnnotationJmxAttributeSource
       |
       v
MetadataMBeanInfoAssembler
       |
       v
MBeanExporter
       |
       v
MBeanServer
       |
       +---- getAttribute(ObjectName, "Enabled")
       |         -> Current state
       |
       +---- getMBeanInfo(ObjectName)
                 -> MBeanAttributeInfo
                    name/type/description/readable/writable
                    descriptor fields (if present)
```

Key point: `getAttribute` returns the value at read time; `getMBeanInfo` returns metadata about the management interface. If metadata specifies a particular default value, clients must not conclude that the current value necessarily equals that default.

In standard JMX, information about an attribute is represented by `javax.management.MBeanAttributeInfo`. MBeans can use `ModelMBeanAttributeInfo`, or another specialized metadata type, to carry additional descriptor fields. Spring supports generating metadata from annotations during export.

## 3. What Does @ManagedAttribute Describe?

The annotation:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
```

is placed on getter/setter methods to declare a managed attribute for metadata-based export.

Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=WorkerConfig,name=Main",
    description = "Runtime configuration of the worker"
)
public class WorkerConfig {

    private volatile boolean enabled = true;

    @ManagedAttribute(
        description = "Whether the worker is accepting new jobs"
    )
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(
        description = "Enable or disable processing new jobs"
    )
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

If the exporter and assembler are configured to read annotation metadata, JMX exposes `Enabled` as a readable and writable attribute. Clients can view its name, type, permissions, and description in `MBeanAttributeInfo`.

In the management model, descriptions on the getter and setter should convey the same meaning. If they conflict, management tools may display unexpected metadata depending on how the assembler merges metadata. Write consistent, clear descriptions telling operators how to interpret the value.

### 3.1. An Attribute Is a Management Contract

Not every field of a class becomes a JMX attribute. In the example, `enabled` is an internal field. The `isEnabled()` and `setEnabled(...)` methods are interpreted by the assembler as the `Enabled` attribute, if the metadata source and exporter permit.

A bean may have an unannotated getter, such as `getInternalToken()`; with an annotation-based assembler, that getter should not be exposed merely because it is public. This is why a management interface must be intentionally designed.

### 3.2. Description Is Not the Attribute Name

```java
@ManagedAttribute(
    description = "Maximum number of tasks allowed in flight"
)
public int getMaxConcurrentTasks() {
    return maxConcurrentTasks;
}
```

The attribute name is derived from the getter, typically `MaxConcurrentTasks`. The description is an English sentence explaining the meaning to humans. Clients must invoke:

```java
server.getAttribute(name, "MaxConcurrentTasks");
```

and not use the description string for routing. Descriptions can change during localization or documentation updates without changing the exposed attribute name.

## 4. MBeanAttributeInfo: Standard JMX Metadata

The `MBeanServer.getMBeanInfo(ObjectName)` API returns `MBeanInfo`. From it, read the attribute list:

```java
import java.lang.management.ManagementFactory;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=WorkerConfig,name=Main"
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "name=%s type=%s readable=%s writable=%s description=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getDescription()
    );
}
```

This snippet assumes the MBean has been registered on the platform MBeanServer. If the exporter uses another server, call `getMBeanInfo` on **that exact MBeanServer**.

| Method | Role |
| --- | --- |
| `getName()` | Exposed attribute name |
| `getType()` | Java type name of the attribute |
| `getDescription()` | Description text |
| `isReadable()` | Allows clients to read |
| `isWritable()` | Allows clients to write |
| `isIs()` | Reflects `isX()`-style getter for booleans |
| `getDescriptor()` | Descriptor containing extended metadata if provided |

For example, if JMX metadata for `Enabled` indicates `readable=true` and `writable=true`, clients can call `getAttribute` and `setAttribute` with the right name/type. However, actual invocation still depends on security, policies, and getter/setter logic.

## 5. Description: Writing Metadata for Accurate Operator Understanding

A description should answer "what does this attribute represent?" and, where necessary, "what are the units, range, and consequences of changing it?".

### 5.1. Good vs. Vague Descriptions

| Vague | Clearer |
| --- | --- |
| `"Count"` | `"Number of active jobs currently processing"` |
| `"Timeout"` | `"Maximum wait time for a job in milliseconds"` |
| `"Enabled"` | `"Whether new tasks can be accepted"` |
| `"Pool size"` | `"Maximum number of worker threads"` |

For writable attributes, the description should avoid falsely implying changes take effect immediately if the application only applies them on reload. For example:

```java
@ManagedAttribute(
    description = "Requested worker count; applied on next scheduler cycle"
)
public void setRequestedWorkers(int workers) {
    this.requestedWorkers = workers;
}
```

Here the description helps clients understand the setter changes the **requested configuration**, and the system may not immediately be running with the new worker count.

### 5.2. Metadata for Multilingual Systems

Description is a server-side metadata string. If a JMX client needs to display multiple languages, the UI application can use its own translation mechanism based on the attribute name and MBean type. Do not change `ObjectName` or attribute names just to translate labels.

Description plays no role in routing. It can be expanded or improved without changing how clients call `getAttribute`.

### 5.3. Keep Descriptions Stable

Descriptions suit stable semantics, not rapidly changing values. Do not put current state, runtime timestamps, or current task counts into a description if you expect clients to observe updates continuously; those values belong in attributes read from the MBean.

## 6. Default Value: Metadata vs. Actual State

Spring's `@ManagedAttribute` has a `defaultValue` element to describe the property's default value in management metadata. Example:

```java
@ManagedAttribute(
    description = "Maximum concurrent jobs",
    defaultValue = "8"
)
public int getMaxConcurrentJobs() {
    return maxConcurrentJobs;
}
```

**Crucial point:** `defaultValue = "8"` does not replace initializing the `maxConcurrentJobs` variable, does not automatically assign 8 when Spring creates the bean, and does not automatically validate the setter.

Runtime initialization example:

```java
public class JobConfig {
    private volatile int maxConcurrentJobs = 12;

    @ManagedAttribute(
        description = "Maximum concurrent jobs",
        defaultValue = "8"
    )
    public int getMaxConcurrentJobs() {
        return maxConcurrentJobs;
    }
}
```

If the MBean is exported properly, reading the `MaxConcurrentJobs` attribute can return `12` because that is the bean's state, even though metadata describes a default of `8`. Metadata and runtime data serve two different purposes.

### 6.1. What Is Default Metadata Good For?

Defaults can be useful for management tools that want to display a default configuration, or for management layers that support related descriptors. Usage depends on the MBean type, assembler, and client. Not all JMX clients display or interpret defaults in the same way.

Some tools only use name/type/readable/writable/description. Therefore, do not design business flows assuming clients will automatically apply `defaultValue`.

### 6.2. Using defaultValue for Numeric and Boolean Types

The annotation declares defaults as strings. When writing metadata, it must be interpreted according to the Spring/JMX metadata contract and the exposed attribute data type. If a default value is complex or incompatible, users may misunderstand it or management tools may fail to use it.

Choose a default that accurately reflects real configuration and aligns with documentation. However, if the runtime default comes from properties, environment variables, or a database, update documentation rules accordingly rather than leaving inaccurate hardcoded metadata.

### 6.3. Do Not Confuse with @Value or Spring Boot Configuration

```java
@Value("${worker.max-concurrent:8}")
private int maxConcurrentJobs;
```

`@Value` in Spring injects configuration values via property resolution. `@ManagedAttribute(defaultValue = "8")` describes JMX metadata. The two annotations solve independent problems. To know the current value, read the bean or the JMX attribute—do not rely on default metadata.

## 7. What Is a Descriptor?

JMX provides the `javax.management.Descriptor` interface. A descriptor can be understood as **a collection of named fields**, used to attach extended metadata to managed objects.

Example logical shape:

```text
Descriptor:
  name = MaxConcurrentJobs
  descriptorType = attribute
  default = 8
  currencyTimeLimit = 10
```

Specific fields and their interpretation depend on the MBean/ModelMBean type and metadata creator. Not every `MBeanAttributeInfo` contains these exact example fields, and not every JMX tool uses them.

JMX distinguishes these concepts:

- `MBeanInfo`: overall metadata about an MBean.
- `MBeanAttributeInfo`: standard metadata about an attribute.
- `Descriptor`: extended metadata attached to an MBean or individual members.
- `ModelMBeanAttributeInfo`: metadata type for Model MBeans, which can use descriptors with fields defined by the ModelMBean specification.

A key characteristic of descriptors is being **structured**: instead of stuffing many meanings into one description sentence, metadata can be represented as named fields for clients or ModelMBeans to process per contract.

## 8. Reading Descriptors in Java

Once `MBeanInfo` is obtained, you can retrieve the descriptor from each attribute:

```java
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    Descriptor descriptor = attr.getDescriptor();

    System.out.println("Attribute: " + attr.getName());
    System.out.println("Description: " + attr.getDescription());

    for (String fieldName : descriptor.getFieldNames()) {
        System.out.printf(
            "  %s = %s%n",
            fieldName,
            descriptor.getFieldValue(fieldName)
        );
    }
}
```

This is how to observe the fields an MBean actually exposes. The list may vary depending on the Spring metadata assembler, MBean type, server, or library version. Do not assume every MBean's descriptor has a `default` field.

To retrieve a single field:

```java
Object defaultMetadata =
    descriptor.getFieldValue("default");
```

The return value has type `Object`. A missing field may return `null`; client code should handle missing metadata. Do not cast directly to `String` without knowing how the emitter/assembler represented it.

### 8.1. Comparing Metadata and Actual Values

```java
for (MBeanAttributeInfo attr : info.getAttributes()) {
    if (!attr.isReadable()) {
        continue;
    }

    Object current = server.getAttribute(name, attr.getName());
    Object declaredDefault =
        attr.getDescriptor().getFieldValue("default");

    System.out.printf(
        "%s: current=%s metadataDefault=%s%n",
        attr.getName(),
        current,
        declaredDefault
    );
}
```

This comparison highlights the difference between the **current value** and the **declared default value**. It does not prove the application started with that default, nor does it guarantee the default is present in every MBean's metadata.

## 9. Metadata Assembly in Spring

For annotations to become JMX metadata, Spring needs a metadata source and an assembler. A basic configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class JmxMetadataConfig {

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
}
```

In a real application, the exporter configuration must also use this assembler; if you only declare an assembler bean without the exporter referencing it, JMX metadata may be exported via another mechanism.

Example:

```java
import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
public MBeanServer jmxServer() {
    return ManagementFactory.getPlatformMBeanServer();
}

@Bean
public MBeanExporter workerExporter(
        WorkerConfig workerConfig,
        MetadataMBeanInfoAssembler assembler,
        MBeanServer jmxServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(jmxServer);
    exporter.setAssembler(assembler);
    exporter.setBeans(Map.of(
        "com.example.monitoring:type=WorkerConfig,name=Main",
        workerConfig
    ));
    return exporter;
}
```

The second configuration snippet needs to be inside an appropriate `@Configuration` class with a `WorkerConfig` bean created in the context. After the exporter runs, clients can inspect `MBeanInfo` to see the exposed metadata.

Spring also provides annotation-driven configuration, such as `@EnableMBeanExport`, to set up the corresponding infrastructure. When using that configuration, avoid accidentally creating a second manual exporter for the same bean/ObjectName.

## 10. Complete Example: ManagedAttribute with Description and Default

A resource with a task-processing threshold:

```java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=JobSettings,name=Main",
    description = "Manage worker runtime limits"
)
public class JobSettings {

    private volatile int maxConcurrentJobs = 8;

    @ManagedAttribute(
        description = "Maximum number of concurrent jobs",
        defaultValue = "8"
    )
    public int getMaxConcurrentJobs() {
        return maxConcurrentJobs;
    }

    @ManagedAttribute(
        description = "Set the maximum concurrent jobs"
    )
    public void setMaxConcurrentJobs(int next) {
        if (next < 1 || next > 128) {
            throw new IllegalArgumentException(
                "maxConcurrentJobs must be between 1 and 128"
            );
        }
        maxConcurrentJobs = next;
    }
}
```

In this example:

- The runtime default is 8 thanks to the field initializer `= 8`.
- The annotation also describes default 8 in metadata.
- The setter validates the range 1 to 128, **not relying on description or defaultValue for automatic validation**.
- `MBeanExporter` must register the object and use an appropriate metadata assembler for the attribute to appear.
- When a client writes 16, `getAttribute(name, "MaxConcurrentJobs")` returns 16, while the default description can still remain 8.

Reading and writing:

```java
import javax.management.Attribute;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.monitoring:type=JobSettings,name=Main"
);

int before = (Integer) server.getAttribute(
    name, "MaxConcurrentJobs"
);

server.setAttribute(
    name,
    new Attribute("MaxConcurrentJobs", Integer.valueOf(16))
);

int after = (Integer) server.getAttribute(
    name, "MaxConcurrentJobs"
);

System.out.printf("Before=%d After=%d%n", before, after);
```

If you receive `AttributeNotFoundException`, check the actually exported metadata. If you receive an error from the setter, check the passed value and validation logic. You can check `isWritable()` on `MBeanAttributeInfo` before allowing modifications from a management tool.

## 11. Metadata Is a Contract, Not a Runtime Mechanism

Common misconceptions:

| Misconception | Reality |
| --- | --- |
| Having `description` gives the UI automatic translations | Description is just a metadata string; localization is up to the client |
| `defaultValue = "8"` automatically assigns 8 to the field | Configuration/field initialization must be done separately |
| A descriptor containing default means current value equals default | Current value must be read via `getAttribute` |
| Adding `@ManagedAttribute` auto-registers the bean | Requires an exporter and MBeanServer |
| Public Java getters always become JMX attributes | Depends on MBean interface/assembler |
| Every descriptor has all fields | Fields depend on MBean type and generated metadata |
| Description serves as attribute name in API calls | Clients use `MBeanAttributeInfo.getName()` |
| Metadata `writable=true` means clients always have permission to edit | Still requires authorization and setter acceptance |

Metadata should be understood as machine-readable documentation of the management surface. It tells a JMX client how to discover and interact with the resource, but it does not replace enforcing business rules and access control.

## 12. Scenarios for Using Description/Default/Descriptor

### 12.1. Helping Dashboards Understand Attributes

A dashboard monitoring dozens of MBeans can display `MBeanAttributeInfo.getDescription()` next to attribute names. For example, accompanying `MaxConcurrentJobs` with "Maximum number of concurrent jobs" helps operators understand it clearly.

If units need to be shown, descriptions can explicitly state "milliseconds" or "bytes". This is helpful information, though when applications/clients need structured metadata for units and constraints, maintain an explicit contract rather than forcing readers to parse description strings with regex.

### 12.2. Documenting Default Configuration

Default values in metadata help management tools know the suggested or default value. However, if the application has environment overrides, the declared default may still differ from the actual startup value.

To avoid misunderstanding, clients can present:

```text
Maximum concurrent jobs
Current value: 16
Declared default: 8
```

Instead of showing only "Default: 8" which misleads users into thinking runtime is running with 8.

### 12.3. Self-Discovering Management Tools

A tool that does not know attribute names ahead of time can:

1. Call `getMBeanInfo`.
2. Read `getAttributes()`.
3. Extract name/type/readable/writable/description.
4. Inspect descriptor fields if present.
5. Create edit controls only for writable attributes with supported data types.
6. Read the current value with `getAttribute`.
7. Send `setAttribute` if the user is permitted, then read back to confirm.

This is why consistent metadata is valuable: it enables tools to display and handle MBeans that were not hardcoded in advance.

## 13. Discovering Metadata Without Relying on Specific Configuration

A Java utility demonstrating defensive metadata printing:

```java
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class AttributeMetadataPrinter {

    private AttributeMetadataPrinter() {}

    public static void print(
            MBeanServerConnection connection,
            ObjectName objectName) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(objectName);

        System.out.println("MBean: " + objectName);
        System.out.println("MBean description: "
            + info.getDescription());

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "%s: type=%s, readable=%s, writable=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable()
            );
            System.out.println("  " + attr.getDescription());

            Descriptor descriptor = attr.getDescriptor();
            for (String field : descriptor.getFieldNames()) {
                Object value = descriptor.getFieldValue(field);
                System.out.printf("  descriptor[%s]=%s%n",
                    field, value);
            }

            if (attr.isReadable()) {
                try {
                    Object current = connection.getAttribute(
                        objectName, attr.getName());
                    System.out.println("  current=" + current);
                } catch (Exception ex) {
                    System.out.println("  read failed: "
                        + ex.getClass().getSimpleName());
                }
            }
        }
    }
}
```

Using `MBeanServerConnection` allows the utility to work across local or remote servers. Because metadata and current state have different lifecycles, attributes may change or the MBean may be unregistered right after `getMBeanInfo`; client code must tolerate real read errors.

Do not log secrets or sensitive attributes in production environments. A general discovery utility needs an exclusion list and an appropriate access control policy.

## 14. Practice Exercise

Using `JobSettings` from section 10 and an `MBeanExporter` using a metadata assembler:

1. Initialize the bean with `maxConcurrentJobs = 8`.
2. Export as an MBean with ObjectName `com.example.monitoring:type=JobSettings,name=Main`.
3. Call `MBeanServer.getMBeanInfo(name)`.
4. Find the `MBeanAttributeInfo` named `MaxConcurrentJobs`.
5. Print `getType()`, `isReadable()`, `isWritable()`, `getDescription()`.
6. Print all fields from `getDescriptor()` and observe whether a default field is present.
7. Read the current value via `getAttribute` (expect 8).
8. Write the value 16 and read back (expect 16).
9. Observe that metadata default still describes 8 if included in the descriptor by the exporter.
10. Try writing 0; the setter in the example will reject the out-of-range value.
11. Write 8 again to restore runtime to the initial configuration.

The hard part of the exercise is not writing the attribute, but interpreting it accurately: **description/default/descriptor belong to metadata; current value and validation belong to runtime**.

## 15. Self-Check Questions

**1. Does `@ManagedAttribute(description = "...")` change the attribute name?** No; the attribute name is derived from the method or corresponding metadata configuration.

**2. What is `MBeanAttributeInfo.getDescription()` used for?** Providing the attribute's description to clients/management tools.

**3. Does `defaultValue` in `@ManagedAttribute` automatically assign bean state?** No; it is metadata.

**4. Which JMX API returns the current value of an attribute?** `getAttribute(ObjectName, String)`.

**5. Which API returns the description and read/write permissions of an attribute?** `getMBeanInfo(ObjectName)`, then read `MBeanAttributeInfo`.

**6. How does a descriptor differ from a description?** A description is a descriptive string; a descriptor is a set of named fields for extended metadata.

**7. Can you assume a descriptor always contains `default`?** No; that depends on the MBean type, assembler, and exposed metadata.

**8. Why not use metadata to replace validation in the setter?** Metadata does not enforce business rules or constrain every JMX call automatically.

**9. When metadata says writable but `setAttribute` fails, what should you check?** Access permissions, value type, setter logic, and MBean errors.

**10. Can you change a description while keeping clients working?** Usually yes, if the attribute name and management contract stay unchanged; clients should not route by description.

## 16. Key Takeaways

- **`@ManagedAttribute`** describes a getter/setter as a JMX attribute when supported by the exporter/assembler.
- **Description** helps tools and operators understand an attribute's meaning.
- **Default value** is descriptive information; it does not auto-assign field values.
- **Descriptor** is field/value metadata, not runtime state.
- **`MBeanAttributeInfo`** provides name, type, description, readable/writable flags, and descriptor.
- **`getMBeanInfo`** reads metadata; **`getAttribute`** reads the current value.
- **`AnnotationJmxAttributeSource` + `MetadataMBeanInfoAssembler` + `MBeanExporter`** is a common Spring JMX integration path.
- Do not equate metadata with validation, authorization, or live state.

When designing managed attributes, write clear descriptions, ensure defaults reflect the configuration contract, and rely on descriptors only after inspecting the MBean's actual metadata. This distinction helps JMX clients interpret state accurately and reduces confusion between "default value" and "running value."
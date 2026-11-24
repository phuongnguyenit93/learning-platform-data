# Reading MBeanInfo and Verifying Expected Attributes in Spring Framework JMX Testing

## 1. Context and Goal

In Spring Framework JMX, a Java bean can be exported as an MBean to expose **attributes**, **operations**, and **notifications**. However, a Spring `ApplicationContext` starting up cleanly is not enough to prove the JMX interface matches requirements. An export configuration might register the wrong ObjectName, use a different assembler than expected, or miss a getter annotated with `@ManagedAttribute`. Therefore, tests need to **read the actual `MBeanInfo` from `MBeanServer` and verify the expected attributes**.

This is **JMX management contract** testing: instead of only checking that annotations exist in source code, we check what interface the Spring-exported object actually exposes to management clients.

After this lesson, you will be able to:

- Explain what `MBeanInfo` and `MBeanAttributeInfo` describe.
- Register/export a managed bean in a Spring test with an explicitly chosen server.
- Retrieve `MBeanInfo` from `MBeanServer.getMBeanInfo(ObjectName)`.
- Verify an attribute's name, Java type, read/write permissions, and description.
- Distinguish metadata tests from calling `getAttribute()` to check runtime values.
- Write regression tests against changes to annotations, naming strategies, or metadata assemblers.
- Avoid errors when multiple tests/JVM contexts share the platform MBeanServer.
- Design stable assertions that do not depend on element ordering or unguaranteed details.

## 2. Why Not Check Annotations Alone?

Consider the bean:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=QueueMonitor,name=Primary",
    description = "Queue runtime monitoring"
)
public class QueueMonitor {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether queue polling is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Change queue polling state")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute(description = "Current number of queued tasks")
    public int getQueuedTasks() {
        return 4;
    }
}
```

Reading the source code shows the intent to expose two attributes:

- `Enabled`: `boolean`, readable and writable.
- `QueuedTasks`: `int`, read-only.

However, a JMX client does not call source code. It connects to `MBeanServer`, looks up `ObjectName`, and uses whatever attributes the MBean **actually exposes**. If `MBeanExporter` is missing, the metadata assembler does not read annotations, the ObjectName differs, or a registration policy keeps an older MBean, runtime behavior can diverge from that intent.

Therefore, tests should observe:

```text
Spring bean
  |
  v
MBeanExporter + metadata
  |
  v
MBeanServer registry
  |
  +-- getMBeanInfo(ObjectName)
        |
        +-- getAttributes()
              |
              +-- MBeanAttributeInfo
                    name/type/readable/writable/description
```

The key point is checking the **published contract at the client access point**, not merely evaluating Java structure on the producer side.

## 3. MBeanInfo and MBeanAttributeInfo

JMX provides standard classes in the `javax.management` package:

| Class/API | Role |
| --- | --- |
| `MBeanServer` | Manages registered MBeans and executes management calls |
| `ObjectName` | Identifies an MBean within a server |
| `MBeanInfo` | Describes the management interface of an MBean |
| `MBeanAttributeInfo` | Describes an exposed attribute |
| `MBeanOperationInfo` | Describes an operation |
| `MBeanNotificationInfo` | Describes a notification type |
| `MBeanConstructorInfo` | Describes a constructor in metadata |
| `Descriptor` | Extended metadata in field/value form |

To obtain the attribute list:

```java
MBeanInfo info = server.getMBeanInfo(name);
MBeanAttributeInfo[] attributes = info.getAttributes();
```

For each attribute, the most useful fields for tests are:

```java
attribute.getName();
attribute.getType();
attribute.isReadable();
attribute.isWritable();
attribute.isIs();
attribute.getDescription();
attribute.getDescriptor();
```

Where:

- `getName()`: the name clients use when calling `getAttribute` or `setAttribute`.
- `getType()`: the attribute's type name, e.g. `int`, `boolean`, `java.lang.String`.
- `isReadable()`: whether a getter is exposed.
- `isWritable()`: whether a setter is exposed.
- `isIs()`: whether a boolean attribute uses an `isX()` getter.
- `getDescription()`: description for tools and operators.
- `getDescriptor()`: extended information if published by the MBean/assembler.

Do not treat the description as an identifier. `description` is human-readable text; `name` is the attribute key in the JMX interface.

## 4. Reading MBeanInfo via the Java JMX API

Example reading metadata of a registered MBean:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=QueueMonitor,name=Primary"
);

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "name=%s, type=%s, readable=%s, writable=%s, description=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable(),
        attribute.getDescription()
    );
}
```

Sample output might look like:

```text
name=Enabled, type=boolean, readable=true, writable=true, description=Whether queue polling is enabled
name=QueuedTasks, type=int, readable=true, writable=false, description=Current number of queued tasks
```

Exact descriptions depend on the metadata assembler and how annotations are interpreted. Tests should verify parts that belong to the **application contract**, rather than comparing full text output containing unnecessary framework details.

If the exporter uses a dedicated `MBeanServer`, the code must retrieve that exact server. Checking the platform server when the exporter registers into another server can cause `InstanceNotFoundException` even though the resource was exported properly.

## 5. Creating a Sample Bean for Testing

Example bean:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=QueueMonitor,name=Primary",
    description = "Queue monitoring MBean"
)
public class QueueMonitor {

    private final AtomicInteger queuedTasks = new AtomicInteger(4);
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether queue polling is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute(description = "Whether queue polling is enabled")
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedAttribute(description = "Number of waiting tasks")
    public int getQueuedTasks() {
        return queuedTasks.get();
    }

    // Internal method not intended to be exposed via JMX:
    public void internalRebuild() {
        queuedTasks.set(0);
    }
}
```

The bean exposes two attributes through metadata. `internalRebuild()` has no `@ManagedOperation`, so with an annotation-based assembler, that internal operation is not part of the expected JMX contract.

Keep the getter and setter of the same attribute consistent in meaning and description. If a getter says "seconds" while the setter says "milliseconds", the metadata can confuse operators.

## 6. Configuring Spring JMX in the Test Environment

To test independently, you can create a dedicated `MBeanServer` for the test. This reduces the risk of ObjectName collisions with other tests using the platform server.

```java
package com.example.monitoring;

import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration
public class JmxTestConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "com.example.test"
        );
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
    public MBeanExporter mBeanExporter(
            QueueMonitor monitor,
            MBeanServer testMBeanServer,
            MetadataMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.monitoring:type=QueueMonitor,name=Primary",
            monitor
        ));
        return exporter;
    }
}
```

This configuration clarifies three points:

1. The `QueueMonitor` bean is present in the Spring context.
2. `MBeanExporter` points to the **test's dedicated server**.
3. `MetadataMBeanInfoAssembler` uses `AnnotationJmxAttributeSource` to build metadata from Spring annotations.

You do not need to enable JMX Remote for this test. JUnit can interact directly with the local `MBeanServer`.

In real environments, `@EnableMBeanExport` or the corresponding auto-configuration can be used. For contract tests, however, making the server and assembler explicit reduces ambiguity when diagnosing failures.

## 7. JUnit 5 Test: Verifying Expected Attributes

A straightforward approach is using `AnnotationConfigApplicationContext` to spin up the Spring context and inspect the JMX registry.

```java
package com.example.monitoring;

import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class QueueMonitorJmxTest {

    @Test
    void exposesExpectedAttributes() throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     JmxTestConfiguration.class
                 )) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.monitoring:type=QueueMonitor,name=Primary"
            );

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            Map<String, MBeanAttributeInfo> attributes =
                Arrays.stream(info.getAttributes())
                    .collect(Collectors.toMap(
                        MBeanAttributeInfo::getName,
                        Function.identity()
                    ));

            assertTrue(
                attributes.containsKey("Enabled"),
                "Enabled should be exposed"
            );
            assertTrue(
                attributes.containsKey("QueuedTasks"),
                "QueuedTasks should be exposed"
            );

            MBeanAttributeInfo enabled = attributes.get("Enabled");
            assertEquals("boolean", enabled.getType());
            assertTrue(enabled.isReadable());
            assertTrue(enabled.isWritable());

            MBeanAttributeInfo queued =
                attributes.get("QueuedTasks");
            assertEquals("int", queued.getType());
            assertTrue(queued.isReadable());
            assertFalse(queued.isWritable());
        }
    }
}
```

This test verifies **registration + metadata contract**. It does not rely on the ordering of `info.getAttributes()` because it converts the array into a `Map` keyed by name. If the test fails, the assertion message pinpoints which attribute is missing or has the wrong permissions/type.

Some projects expose additional framework attributes on MBeans. When the requirement is simply "must include `Enabled` and `QueuedTasks`", prefer `containsKey` over forcing the attribute list to have exact size two. If the contract strictly forbids all other attributes, add an assertion on the set of names.

## 8. Writing Reusable Assertion Helpers

When many MBeans need verification, repeating `Arrays.stream(...)` in every test becomes hard to maintain. You can write a helper:

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

import static org.junit.jupiter.api.Assertions.*;

final class JmxAssertions {

    private JmxAssertions() {}

    static MBeanAttributeInfo requireAttribute(
            MBeanInfo info, String expectedName) {

        return Arrays.stream(info.getAttributes())
            .filter(attr -> expectedName.equals(attr.getName()))
            .findFirst()
            .orElseThrow(() ->
                new AssertionError(
                    "Missing JMX attribute: " + expectedName
                ));
    }

    static void assertReadOnly(
            MBeanInfo info, String name, String type) {

        MBeanAttributeInfo attr = requireAttribute(info, name);

        assertEquals(type, attr.getType());
        assertTrue(attr.isReadable());
        assertFalse(attr.isWritable());
    }

    static void assertReadWrite(
            MBeanInfo info, String name, String type) {

        MBeanAttributeInfo attr = requireAttribute(info, name);

        assertEquals(type, attr.getType());
        assertTrue(attr.isReadable());
        assertTrue(attr.isWritable());
    }
}
```

Usage:

```java
MBeanInfo info = server.getMBeanInfo(name);

JmxAssertions.assertReadWrite(info, "Enabled", "boolean");
JmxAssertions.assertReadOnly(info, "QueuedTasks", "int");
```

These helpers express the exact contract being verified. If you have many getter styles or write-only attributes, you can extend the helpers with boolean flags or an expected metadata structure.

## 9. Verifying Description When It Is Part of the Contract

If the metadata description matters to the management console, you can assert it:

```java
MBeanAttributeInfo queued =
    JmxAssertions.requireAttribute(info, "QueuedTasks");

assertEquals(
    "Number of waiting tasks",
    queued.getDescription()
);
```

However, do not turn harmless wording tweaks into test failures if descriptions are only supplementary documentation. Choose assertions based on the contract:

- If operations tools display the description and documentation mandates fixed wording: assert exact text.
- If the description is only for human readers: check `notBlank` or skip exact text assertions.
- If metadata is localized: design tests around locale or specific environment expectations.

Description is not the attribute name; to access the attribute, clients still pass `QueuedTasks` to `getAttribute`.

## 10. Checking `getAttribute()` After Confirming Metadata

`MBeanInfo` tells you an attribute is **exposed**. To know whether the actual getter executes cleanly, call `getAttribute`.

```java
Object enabled = server.getAttribute(name, "Enabled");
Object queuedTasks = server.getAttribute(name, "QueuedTasks");

assertEquals(Boolean.TRUE, enabled);
assertEquals(Integer.valueOf(4), queuedTasks);
```

This complements metadata testing rather than replacing it. Sometimes metadata marks `readable=true` while the actual getter fails due to an unavailable dependency, uninitialized state, or an exception inside bean logic.

For a writable attribute, you can test `setAttribute` and read it back:

```java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE)
);

assertEquals(
    Boolean.FALSE,
    server.getAttribute(name, "Enabled")
);
```

Tests should clean up or reset state so they do not affect other tests when sharing a bean or server.

### 10.1. Metadata Tests and Behavior Tests Have Different Scopes

| Check | Question Answered |
| --- | --- |
| `server.isRegistered(name)` | Is the MBean registered under the expected ObjectName? |
| `getMBeanInfo(name)` | What management interface is exposed? |
| `MBeanAttributeInfo.isReadable()` | Does metadata allow reading? |
| `MBeanAttributeInfo.isWritable()` | Does metadata allow writing? |
| `getAttribute(...)` | Does the getter return the expected data? |
| `setAttribute(...)` | Does the setter handle the value properly? |
| `getOperations()` | Which operations are exported? |
| `getNotifications()` | Which notification types does the MBean declare? |

Match each test type to a clear contract. For example, a metadata test does not need to invoke an operation that flushes a production cache just to prove `MBeanInfo` lists that operation.

## 11. Testing Exact Data Types and Read/Write Permissions

JMX type names reflect the Java type of the attribute:

```text
boolean
int
long
double
java.lang.String
```

For example:

```java
@ManagedAttribute
public long getProcessedJobs() {
    return 100L;
}
```

Expected metadata is typically:

```text
name = ProcessedJobs
type = long
readable = true
writable = false
```

A regression can occur when refactoring a getter from `int` to `long`. If a client or monitoring rule expects the old type, metadata tests catch the contract break.

For booleans, JMX metadata may set `isIs()` when the getter uses `isEnabled()`. Only assert this flag if it is a genuine contract requirement and the assembler in use has stable semantics across versions.

### 11.1. Do Not Assume Setters Are Ordinary Business Methods

If `Enabled` is writable, clients can mutate runtime behavior via JMX. Tests should validate authorization and setter logic at an appropriate level rather than treating `writable=true` as a safety guarantee. For operations or attributes with side effects, always use a test environment and isolated data.

## 12. Verifying the Absence of Unwanted Attributes

A useful security check is confirming that internal getters are **not exported**.

For example, if the bean has:

```java
public String getInternalSecret() {
    return "not-for-jmx";
}
```

Without `@ManagedAttribute` and using an annotation-based assembler, the expected contract should not expose `InternalSecret`. Test:

```java
Map<String, MBeanAttributeInfo> attributes = ...;

assertFalse(
    attributes.containsKey("InternalSecret"),
    "Sensitive internal attribute must not be exposed"
);
```

However, the export mechanism affects the outcome. A Standard MBean whose interface declares the getter or an assembler exporting public methods can produce a different surface. Therefore, tests must run with the **exact exporter/assembler configuration** the application uses, rather than checking annotations in isolation.

Do not put real secret values into test fixtures or logs. The goal is to confirm the interface does not expose unauthorized attributes.

## 13. Testing with a Dedicated MBeanServer to Avoid Interference

When running multiple tests in a single JVM, using the platform MBeanServer can lead to:

- ObjectName collisions between tests.
- Leftover MBeans from earlier tests.
- Different Spring contexts writing into the same registry.
- Order-dependent test results.
- Failures during parallel execution or when other plugins export MBeans under the same domain.

One solution is:

```java
MBeanServer isolated =
    MBeanServerFactory.newMBeanServer("com.example.test");
```

Each test or test group can own a dedicated server. `newMBeanServer` does not register the server in `MBeanServerFactory`'s lookup list, reducing unintended interference. Still, isolation does not replace cleanup if tests retain references to contexts, connectors, or long-lived resources.

When using Spring `MBeanExporter`, calling `setServer(isolated)` ensures the exporter registers into the test server. Avoid letting an exporter auto-detect the platform server while the test checks the isolated server.

### 13.1. Cleaning Up Resources with the Spring Context

In the sample test:

```java
try (AnnotationConfigApplicationContext context =
         new AnnotationConfigApplicationContext(
             JmxTestConfiguration.class
         )) {
    // Assertions
}
```

`close()` is called when exiting the `try` block. The exporter gets a chance to unregister the MBeans it manages. If a test manually registers via `server.registerMBean`, it must unregister the resources it owns.

A good test should never wipe an entire domain on the platform server just to clean up its environment.

## 14. Common Errors and How to Analyze Them

| Symptom | Possible Cause | Next Check |
| --- | --- | --- |
| `isRegistered` is false | Wrong server, wrong ObjectName, or exporter has not run | Check `setServer`, naming strategy, and context |
| `InstanceNotFoundException` | No MBean registered under that name at read time | Check registry and lifecycle |
| `InstanceAlreadyExistsException` | Duplicate ObjectName during registration | Use a dedicated test server or unique name |
| Metadata missing attribute | Missing annotation, assembler ignoring metadata, or wrong exporter | Inspect `getMBeanInfo` and configuration |
| Attribute name differs from expected | Different JavaBeans/naming getter or changed contract | Inspect actual `getName()` |
| `readable=false` | Missing exported getter | Check annotation and method |
| `writable=false` | Missing exported setter | Check annotation and method |
| Type `int` instead of `long` | Getter return type changed | Align contract, client, and test |
| `getAttribute` fails despite readable metadata | Runtime error in getter, security, or bean state | Check cause and state |
| Test passes alone but fails in suite | Shared server/context or order dependency | Isolate server, clean up, avoid arbitrary static state |

Do not fix a failing test by dropping an assertion without understanding the cause. In building the test suite, determine whether the contract requirement changed intentionally or the exporter is misconfigured.

## 15. Reading Attribute Metadata via `MBeanServerConnection`

Local tests use `MBeanServer`, while `MBeanServerConnection` is the common interface for remote operations. You can write a helper reusable for both local and remote checks:

```java
import javax.management.MBeanServerConnection;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

public final class JmxMetadataReader {

    private JmxMetadataReader() {}

    public static MBeanAttributeInfo findAttribute(
            MBeanServerConnection connection,
            ObjectName name,
            String attributeName) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(name);
        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            if (attributeName.equals(attribute.getName())) {
                return attribute;
            }
        }
        throw new IllegalArgumentException(
            "Missing attribute " + attributeName
        );
    }
}
```

This lets you verify the contract over an actual JMX connector if needed. However, remote integration tests are usually slower and depend on transport, credentials, ports, and network policies. For most metadata tests, in-JVM local tests are sufficient to verify the assembler/exporter. Use remote tests only when validating **connectors, security, transport, and cross-environment reachability**.

In particular, a remote JMX client may lack the server's custom classes. Choose appropriate management data types when designing MBeans to avoid classloader coupling.

## 16. Reading and Checking Descriptor Metadata When Needed

Beyond standard fields, JMX has `Descriptor` for extended metadata. Some assemblers or ModelMBeans may supply `default`, `currencyTimeLimit`, `persistPolicy`, or other fields.

```java
import javax.management.Descriptor;
import javax.management.MBeanAttributeInfo;

MBeanAttributeInfo attribute =
    JmxAssertions.requireAttribute(info, "QueuedTasks");

Descriptor descriptor = attribute.getDescriptor();

for (String field : descriptor.getFieldNames()) {
    System.out.printf(
        "descriptor[%s]=%s%n",
        field,
        descriptor.getFieldValue(field)
    );
}
```

Do not assume every `MBeanAttributeInfo` has a `default` field or any other optional field. If the application contract relies on descriptors, tests must prove the exporter actually publishes them in the Spring/JMX version in use.

With `@ManagedAttribute(defaultValue = "8")`, the default metadata is only descriptive; it does not initialize the runtime value to 8. To check current runtime state, always use `getAttribute`.

## 17. Defining a Clear Expected Contract

One maintainable way to organize tests is defining the contract as data:

```java
record ExpectedAttribute(
    String name,
    String type,
    boolean readable,
    boolean writable
) {}

List<ExpectedAttribute> expected = List.of(
    new ExpectedAttribute("Enabled", "boolean", true, true),
    new ExpectedAttribute("QueuedTasks", "int", true, false)
);
```

Then compare against `MBeanInfo`:

```java
Map<String, MBeanAttributeInfo> actual =
    Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            Function.identity()
        ));

for (ExpectedAttribute item : expected) {
    MBeanAttributeInfo attribute = actual.get(item.name());

    assertNotNull(attribute, "Missing " + item.name());
    assertEquals(item.type(), attribute.getType());
    assertEquals(item.readable(), attribute.isReadable());
    assertEquals(item.writable(), attribute.isWritable());
}
```

This pattern scales easily across multiple MBeans and produces clear failure messages. When you need to check descriptors, descriptions, or the `isIs` flag, extend the expected structure for the real contract rather than asserting arbitrary framework metadata.

### 17.1. Should You Assert Exact Attribute Counts?

It depends on the goal:

- **Positive contract:** verify the minimum required attributes exist. Use `containsKey` or `assertNotNull`.
- **Strict contract:** verify the exact set of allowed attributes, with no unexpected additions.
- **Security contract:** verify that specific internal/sensitive attributes are definitely not exported.

If you only need to ensure `Enabled` and `QueuedTasks` exist, avoid failing tests simply because the framework exposes additional harmless metadata.

## 18. Example Test Scenario When Refactoring a Spring Bean

Suppose an application originally has:

```java
@ManagedAttribute
public int getQueuedTasks() { ... }
```

After refactoring it becomes:

```java
@ManagedAttribute
public long getQueuedTasks() { ... }
```

Now the metadata type shifts from `int` to `long`. A dashboard or script casting to `Integer` may fail. Metadata tests catch the change even though both versions compile cleanly.

Another case is renaming:

```java
public boolean isEnabled()
```

to:

```java
public boolean isQueueEnabled()
```

Under JavaBeans naming conventions, the attribute name may change from `Enabled` to `QueueEnabled`. Name-based tests catch the contract break.

Yet another case is accidentally dropping a getter annotation when splitting a service class. The Spring context and bean still exist, but the attribute disappears from JMX. `getMBeanInfo` tests prevent this regression from passing the test pipeline.

## 19. Practice Exercises

Use `QueueMonitor` and `JmxTestConfiguration` above to complete the following:

1. Create a JUnit 5 test that opens `AnnotationConfigApplicationContext`.
2. Inject the test-created `MBeanServer`.
3. Verify the MBean has ObjectName `com.example.monitoring:type=QueueMonitor,name=Primary`.
4. Read `MBeanInfo` and print the list of `MBeanAttributeInfo`.
5. Assert `Enabled` is `boolean`, readable, and writable.
6. Assert `QueuedTasks` is `int`, readable, and not writable.
7. Assert `InternalSecret` is absent if the bean has an unexported internal getter.
8. Read `Enabled` via `getAttribute`, write `false`, and read it back.
9. Try writing `QueuedTasks` via `setAttribute` and observe the error because it is read-only.
10. Rename `getQueuedTasks` and re-run the test to observe the contract break.
11. Close the context and verify test resources are not leaked across other tests.

Expected metadata test output:

```text
MBean registered: true
Enabled: boolean readable=true writable=true
QueuedTasks: int readable=true writable=false
```

Use standalone tests and a dedicated server so you do not affect real MBeans in other processes. Never run side-effecting operations on production to perform exercises.

## 20. Self-Check Questions

**1. What information does `MBeanInfo` provide?** Metadata about an MBean's JMX management interface, including attributes, operations, and notifications.

**2. Which API returns the list of attributes?** `MBeanInfo.getAttributes()`.

**3. Which APIs return an attribute's name and type?** `MBeanAttributeInfo.getName()` and `getType()`.

**4. How do you know whether an attribute is readable/writable from metadata?** `isReadable()` and `isWritable()`.

**5. Why should tests map metadata by attribute name?** To avoid depending on the ordering of the metadata array.

**6. If metadata lists an attribute but the getter fails, which test catches it?** Actually invoking `MBeanServer.getAttribute(...)`.

**7. Why create a dedicated MBeanServer for tests?** To reduce ObjectName collisions, cross-test interference, and registration leaks on the platform server.

**8. Is `description` the name used to call `getAttribute`?** No, clients must use `getName()`.

**9. When should you assert the exact list of attributes?** When the management interface must be a closed contract that exposes no attributes outside the list.

**10. If the exporter registers on a dedicated server, why does checking the platform server fail?** Because they are two separate registries.

**11. Do annotation tests replace MBeanInfo tests?** No, annotations express intent; `MBeanInfo` reflects the interface published by the server.

**12. If a getter is refactored from int to long, how do metadata tests help?** They detect the data type change that JMX clients may depend on.

## 21. Key Takeaways

- **JMX tests should read actual `MBeanInfo`**, not merely check source annotations.
- **`MBeanAttributeInfo`** describes each attribute's name, type, readability/writability, and description.
- **`isRegistered`** checks MBean existence; **`getMBeanInfo`** checks the interface; **`getAttribute`** checks runtime values.
- **Use a dedicated MBeanServer in tests** to avoid ObjectName collisions and interference across Spring contexts.
- **Assert by name rather than order** of `getAttributes()`.
- **Distinguish positive contracts, strict contracts, and security contracts** when deciding how many attributes to assert.
- **Metadata assemblers, naming strategies, and exporters** can all alter the final JMX interface; tests must use the matching configuration.
- **Descriptions and descriptors are metadata**, not actual bean values.
- **JMX contract tests catch regressions** after refactorings, getter type changes, annotation edits, or export mechanism changes.

By reading `MBeanInfo` and verifying expected attributes on the right `MBeanServer`, you verify what JMX clients actually see. This is the foundation for keeping a Spring Framework JMX management interface consistent, safe, and stable over time.
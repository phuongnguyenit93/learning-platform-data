# Verifying Registered ObjectNames in Spring Framework JMX

## Lesson Objectives

In Spring Framework JMX, declaring `@ManagedResource`, configuring an `MBeanExporter`, or constructing a valid `ObjectName` **does not by itself prove** that the MBean was successfully registered. To accurately confirm that a managed resource appears in the JMX system, you must check the **right MBeanServer** and the **right ObjectName** at runtime.

This lesson belongs to **Spring Framework JMX → Testing**. After completing it, you will be able to:

- Distinguish a valid ObjectName from a registered ObjectName.
- Use `MBeanServer.isRegistered(ObjectName)` and `MBeanServerConnection.isRegistered(ObjectName)`.
- Use `queryNames`, `getMBeanInfo`, and key properties to identify the exact resource.
- Write unit tests for naming rules and integration tests for `MBeanExporter`.
- Test the lifecycle: registration when the Spring context starts, unregistration when the context closes.
- Detect name collisions, wrong domains, wrong MBeanServers, wrong JMX endpoints, or unintended name changes.
- Avoid flaky tests caused by sharing the platform MBeanServer or running tests in parallel.

## 1. ObjectName Is a Name, Not Proof of Registration

An MBean in JMX is identified by `javax.management.ObjectName`:

```text
domain:key1=value1,key2=value2
```

For example:

```text
com.example.orders:type=Queue,name=Payment
```

You can construct an ObjectName:

```java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

If the constructor succeeds, the name is syntactically valid. However, it may not yet be registered in any `MBeanServer`.

```text
Valid ObjectName
      |
      |  not enough!
      v
Specific MBeanServer
      |
      +-- isRegistered(name) == true
      |       -> MBean exists at check time
      |
      +-- isRegistered(name) == false
              -> no MBean with that name in this server
```

To avoid confusion, separate three questions:

1. **Syntax:** Is the ObjectName valid?
2. **Registration:** Does an MBean exist under this name in the target server?
3. **Contract:** Does the registered MBean expose the expected attributes/operations?

`isRegistered` answers the second question. If you need the third, also inspect `MBeanInfo`.

## 2. Checking with MBeanServer.isRegistered

`MBeanServer` provides the method:

```java
boolean isRegistered(ObjectName name);
```

Example checking the platform MBeanServer:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxRegistrationCheck {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        boolean registered = server.isRegistered(name);
        System.out.println("Registered: " + registered);
    }
}
```

This call verifies whether **the server instance currently being inspected** contains that ObjectName.

**Note:** If Spring `MBeanExporter` registers into a custom MBeanServer, calling `ManagementFactory.getPlatformMBeanServer()` may return `false` even though the MBean was successfully registered on another server. Do not conclude the exporter is broken before checking `setServer` or the server bean injected into the exporter.

## 3. ObjectName.equals and Canonical Name

Two strings with different key ordering still represent the same ObjectName:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:name=Payment,type=Queue
```

JMX treats them as the same identity:

```java
ObjectName first = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName second = new ObjectName(
    "com.example.orders:name=Payment,type=Queue"
);

assert first.equals(second);
assert first.getCanonicalName()
            .equals(second.getCanonicalName());
```

Therefore, tests should use:

```java
assertEquals(expectedObjectName, actualObjectName);
```

instead of comparing raw strings that may differ in key order.

`getCanonicalName()` is useful for logging, building test failure messages, and comparing output across different management tools.

**Key point:** A canonical name only normalizes the representation of a JMX identity; it does not prove that the name exists or belongs to the right server.

## 4. Checking a Concrete Name or a Pattern?

An ObjectName used for registration is normally a **concrete** name:

```java
ObjectName exact = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
```

When you need to find a group of MBeans, you can use a pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.orders:type=Queue,*"
);
```

Check:

```java
assertFalse(exact.isPattern());
assertTrue(pattern.isPattern());
```

For a specific name, use `isRegistered(exact)`. For a pattern, use `queryNames(pattern, null)` to retrieve matching ObjectNames.

Do not query with a pattern and assume the first result is the resource you want to operate on. If a test needs an exact MBean, check the **exact ObjectName**.

## 5. Creating a Standard MBean for Testing

Example MBean monitoring a queue:

```java
package com.example.orders.jmx;

public interface PaymentQueueMonitorMBean {
    int getPendingCount();
}
```

Implementation:

```java
package com.example.orders.jmx;

public final class PaymentQueueMonitor
        implements PaymentQueueMonitorMBean {

    private final int pendingCount;

    public PaymentQueueMonitor(int pendingCount) {
        this.pendingCount = pendingCount;
    }

    @Override
    public int getPendingCount() {
        return pendingCount;
    }
}
```

The class has an interface named `PaymentQueueMonitorMBean`, following the Standard MBean convention.

An MBean registered under:

```text
com.example.orders:type=Queue,name=Payment
```

will expose the `PendingCount` attribute. Before reading the attribute, however, the test should confirm that the name is registered in the target server.

## 6. Pure JMX Unit/Integration Test

To avoid touching the platform MBeanServer used by the JVM and other tests, create a dedicated server:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.management");
```

JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class ObjectNameRegistrationTest {

    @Test
    void registersExpectedObjectName() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("test.management");

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        try {
            assertFalse(server.isRegistered(name));

            server.registerMBean(
                new PaymentQueueMonitor(12),
                name
            );

            assertTrue(server.isRegistered(name));

            assertEquals(
                12,
                server.getAttribute(name, "PendingCount")
            );
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

The test verifies all three states:

1. Before registration: the MBean is absent from the server.
2. After registration: the MBean is present under the exact ObjectName.
3. After unregistration: the server no longer holds that registration.

When using `createMBeanServer`, you can call `releaseMBeanServer` to remove the server from the list managed by the factory. With `newMBeanServer`, the server is not registered in that factory list and does not use `releaseMBeanServer` in the same way.

## 7. Inspecting MBeanInfo After Confirming Registration

`isRegistered` only tells you the name exists; it does not prove the MBean has the expected contract.

After confirming:

```java
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);
System.out.println(info.getClassName());

for (var attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() + " : " + attribute.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

A good test can verify:

- The `PendingCount` attribute exists.
- The attribute type is `int`.
- The attribute is readable.
- Sensitive operations do not appear if the management interface forbids them.
- The MBean class or metadata matches expectations.

For a ModelMBean exported by Spring from an arbitrary bean, `info.getClassName()` may reflect the ModelMBean/metadata class rather than the exact business class. Therefore, checking attributes and operations is usually more useful than comparing class names alone.

## 8. Configuring Spring MBeanExporter

`MBeanExporter` can register beans into an MBeanServer when the Spring context starts:

```java
package com.example.orders.config;

import com.example.orders.jmx.PaymentQueueMonitor;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportTestConfiguration {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("test.management");
    }

    @Bean
    public PaymentQueueMonitor paymentQueueMonitor() {
        return new PaymentQueueMonitor(12);
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer testMBeanServer,
            PaymentQueueMonitor paymentQueueMonitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            paymentQueueMonitor
        ));
        return exporter;
    }
}
```

Here:

- `testMBeanServer` is a dedicated server.
- `paymentQueueMonitor` is a Standard MBean implementation.
- `mbeanExporter` registers the bean under a fixed ObjectName.
- The exporter manages the registration lifecycle alongside the Spring context.

**Attention:** Do not manually register the same bean into the server before the exporter initializes if you want to test the exporter performing registration itself. Doing so causes an ObjectName collision and obscures the test goal.

## 9. Spring Integration Test Checking ObjectName

JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringJmxRegistrationTest {

    @Test
    void exportsBeanWithExpectedObjectName() throws Exception {
        ObjectName expected = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        MBeanServer server;

        try (var context =
                 new AnnotationConfigApplicationContext(
                     JmxExportTestConfiguration.class)) {

            server = context.getBean(
                "testMBeanServer", MBeanServer.class
            );

            assertTrue(
                server.isRegistered(expected),
                "Missing JMX MBean: " + expected.getCanonicalName()
            );

            assertEquals(
                12,
                server.getAttribute(expected, "PendingCount")
            );
        }

        assertFalse(
            server.isRegistered(expected),
            "MBean should be unregistered after context close"
        );
    }
}
```

This tests **Spring wiring + JMX registration** in a single test.

If the test uses `@EnableMBeanExport` and annotations instead of a manual `MBeanExporter`, ensure that the annotation-created exporter actually uses the test server; do not assume all exporters pick the same MBeanServer just because a bean of that type exists in the context.

## 10. Checking ObjectName When Using @ManagedResource

Annotation-based export:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment",
    description = "Payment queue management interface"
)
public class AnnotatedQueueAdmin {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

When enabled:

```java
@Configuration
@EnableMBeanExport
public class AnnotationJmxConfig {
}
```

Spring can detect the resource and register it into the configured MBeanServer.

The test must verify:

```java
assertTrue(server.isRegistered(new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
)));
```

Do not stop at:

```java
assertNotNull(AnnotatedQueueAdmin.class
    .getAnnotation(ManagedResource.class));
```

The annotation existing on the class is only source metadata; it does not prove that the exporter initialized, scanned the bean, registered the right name, or used the right server.

## 11. queryNames for Testing Groups of MBeans

`MBeanServer.queryNames(ObjectName, QueryExp)` lets you look up existing MBeans by pattern:

```java
ObjectName pattern = new ObjectName(
    "com.example.orders:type=Queue,*"
);

var names = server.queryNames(pattern, null);

for (ObjectName item : names) {
    System.out.println(item.getCanonicalName());
}
```

A test can verify both resources are present:

```java
ObjectName payment = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);
ObjectName refunds = new ObjectName(
    "com.example.orders:type=Queue,name=Refund"
);

var names = server.queryNames(
    new ObjectName("com.example.orders:type=Queue,*"),
    null
);

assertTrue(names.contains(payment));
assertTrue(names.contains(refunds));
```

When you want to assert **no extra resources exist**, check the exact set of names in an **isolated test MBeanServer**. On the platform server, libraries or other tests may register valid MBeans in the same domain, making exact count assertions brittle.

## 12. Wrong MBeanServer Is a Common Root Cause

A single JVM can host multiple MBeanServers:

```text
JVM
  |
  +-- Platform MBeanServer
  |     +-- java.lang:type=Memory
  |
  +-- Custom MBeanServer
        +-- com.example.orders:type=Queue,name=Payment
```

If the exporter uses a custom server:

```java
exporter.setServer(customServer);
```

but the test calls:

```java
ManagementFactory.getPlatformMBeanServer()
    .isRegistered(name);
```

it can return `false` even when the exporter works completely properly.

To avoid this mistake:

1. Inject or retrieve the exact `MBeanServer` bean used by the exporter.
2. Check `setServer` in the configuration.
3. Log the ObjectName and server identity in diagnostic tests.
4. When using a remote connector, verify that the connector serves the right server.

Do not change the ObjectName arbitrarily just because `isRegistered` returned false on the wrong server.

## 13. Checking ObjectNames on a Remote Server

`MBeanServerConnection` also provides `isRegistered`, so checks can be performed from a client:

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name = new ObjectName(
        "com.example.orders:type=Queue,name=Payment"
    );

    boolean registered = connection.isRegistered(name);
    System.out.println("Remote registered: " + registered);
}
```

The same ObjectName can be registered across multiple JVMs. Therefore, remote checks must identify both the **endpoint/instance** and the ObjectName.

If remote `isRegistered(name)` returns `false`, the endpoint may be wrong, the MBean may not be exported yet, or the exporter may be using a different server than the one the connector serves.

## 14. Testing Duplicate ObjectName Errors

Within the same MBeanServer, two MBeans cannot be simultaneously registered under the same ObjectName.

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.InstanceAlreadyExistsException;

server.registerMBean(
    new PaymentQueueMonitor(12), name
);

assertThrows(
    InstanceAlreadyExistsException.class,
    () -> server.registerMBean(
        new PaymentQueueMonitor(99), name
    )
);
```

When using `MBeanExporter`, `RegistrationPolicy` determines how Spring reacts when a name already exists:

- `FAIL_ON_EXISTING`: throws an error.
- `IGNORE_EXISTING`: skips the new registration.
- `REPLACE_EXISTING`: replaces according to Spring's policy.

Tests must set expectations matching the configured policy. With fail-on-existing, do not assume Spring automatically renames the MBean to avoid collisions.

A registered ObjectName does not prove it is the **right bean** if an ignore policy keeps an older MBean. Inspect attributes/metadata or use instance-identifying properties when needed.

## 15. Checking ObjectName Across the Context Lifecycle

An important integration test should confirm that the MBean is no longer registered after the Spring context closes.

```text
Before refresh:
  registered = false

After refresh:
  registered = true

After close:
  registered = false
```

This catches bugs such as:

- Exporter failing to clean up MBeans.
- Another exporter co-owning the name.
- An old context still remaining alive.
- Tests reusing the platform server without cleanup.
- MBeans registered manually without lifecycle management.

Testing only `isRegistered == true` after startup may miss leaks during redeploys or multi-test runs.

Note that an ApplicationContext can close cleanly while the MBean remains on the server if it **was registered by another component**. Never automatically unregister resources that the test does not own.

## 16. Testing Naming Strategies

Spring supports `ObjectNamingStrategy` to generate names for beans.

Example naming convention:

```text
com.example.orders:type=Queue,name=Payment
com.example.orders:type=Queue,name=Refund
```

A unit test for a naming strategy should verify:

- Correct domain.
- `type`/`name` key properties.
- Different beans produce different names.
- Names remain stable across recreations of an object with the same logical identity.
- Names are not patterns if used for registration.
- Special characters are properly handled/quoted.

```java
ObjectName first = namingStrategy.getObjectName(
    paymentQueue, "paymentQueue"
);

assertEquals(
    new ObjectName("com.example.orders:type=Queue,name=Payment"),
    first
);
assertFalse(first.isPattern());
```

After unit testing, write a Spring integration test to ensure the exporter **actually uses** that naming strategy rather than a different naming path.

## 17. Diagnostic Support via JMX Properties

When debugging, you can print diagnostic details:

```java
System.out.println("Domain: " + name.getDomain());
System.out.println("Canonical: " + name.getCanonicalName());
System.out.println("Properties: " + name.getKeyPropertyList());
System.out.println("Registered: " + server.isRegistered(name));
```

And if registered:

```java
var info = server.getMBeanInfo(name);

System.out.println("MBean class: " + info.getClassName());
System.out.println("Attributes: " + info.getAttributes().length);
System.out.println("Operations: " + info.getOperations().length);
```

In production, avoid logging sensitive data from attribute values. ObjectNames can also contain internal identifiers; include only the keys truly needed for diagnostics.

## 18. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `isRegistered` returns false | Exporter has not run, wrong MBean name, or different server | Check context, `setServer`, `ObjectName` |
| `MalformedObjectNameException` | Invalid name string | Use `ObjectName` API, quote key properties when needed |
| `InstanceAlreadyExistsException` | Name already belongs to another MBean in the same server | Check owner, naming strategy, registration policy |
| `InstanceNotFoundException` | Name does not exist during read/invoke or was just unregistered | Check lifecycle and timing |
| MBean exists but lacks operations | Wrong metadata assembler/interface | Inspect `getMBeanInfo` |
| Test passes alone but fails in parallel | Sharing platform MBeanServer with fixed ObjectName | Create a dedicated MBeanServer |
| MBean not unregistered on context close | Another registration exists or lifecycle cleanup missing | Check owner and context teardown |
| Same ObjectName on two JVMs | Completely valid since each server has its own namespace | Combine endpoint + ObjectName to identify target |

## 19. Practice Exercises

1. Create `PaymentQueueMonitorMBean` and register it with `MBeanServer.registerMBean` into a test server. Verify before/after registration with `isRegistered`.
2. Use an `ObjectName` with reversed key properties to prove `equals` still returns `true`.
3. Create a Spring `MBeanExporter` configuration exporting a bean under a fixed ObjectName; write an integration test verifying `isRegistered` after `context.refresh()`.
4. Read `MBeanInfo` and assert the `PendingCount` attribute has type `int`.
5. Close the context and assert the MBean is no longer on the server.
6. Register two MBeans with the same ObjectName in a test server to observe `InstanceAlreadyExistsException`.
7. Intentionally configure the exporter with a custom server while testing against the platform server; explain the false negative.
8. Query with `com.example.orders:type=Queue,*` and verify the ObjectName set of two queues.
9. Write a test for an annotation-driven MBean using `@ManagedResource` instead of a manual exporter.

## 20. Self-Check Questions

- Why does a successful `new ObjectName(...)` still not prove an MBean is registered?
- What does `isRegistered` verify, and what does it leave unverified?
- When should you use `queryNames` instead of `isRegistered`?
- Why is the canonical name important when key property ordering differs?
- Why must you inspect the exact MBeanServer used by the exporter?
- After `isRegistered == true`, how do you verify the MBean exposes the expected attributes?
- Can the same ObjectName coexist on two different JVMs?
- Why does post-test cleanup prevent `InstanceAlreadyExistsException` in subsequent runs?

**Key takeaway:** A valid ObjectName is only a **name**. To verify that an MBean was actually exported by Spring, call `isRegistered` on the **right MBeanServer**, use `queryNames` for groups, use `MBeanInfo` to verify the contract, and test cleanup when the ApplicationContext closes.
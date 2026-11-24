# Invoking Read-Only, Read-Write Attributes, and Operations in Spring Framework JMX Testing

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** Testing  
> **Lesson:** Invoking read-only, read-write attributes, and operations

## 1. Lesson Objectives

JMX testing does not stop at seeing an MBean name in JConsole. An MBean can register successfully while an attribute fails to read, a setter does nothing, an operation signature mismatches, or an error occurs when routing through the Spring JMX exporter. After this lesson, you will be able to:

- Distinguish **read-only** attributes, **read-write** attributes, and JMX **operations**.
- Read \`MBeanInfo\` to identify actual names, types, read/write permissions, and operation signatures.
- Call \`MBeanServerConnection.getAttribute\`, \`setAttribute\`, and \`invoke\`.
- Write integration tests for Spring \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`.
- Verify both return values and side effects on bean state.
- Test error cases: writing to read-only attributes, type mismatches, wrong operation signatures, and invalid values.
- Separate export errors, JMX routing errors, and business method errors.

## 2. The Big Picture

Spring Framework can publish a Spring bean as an MBean via \`MBeanExporter\` or \`AnnotationMBeanExporter\`.

\`\`\`text
Spring ApplicationContext
         |
         v
@ManagedResource bean
         |
         +-- @ManagedAttribute getter
         |       -> Read-only attribute
         |
         +-- @ManagedAttribute getter + setter
         |       -> Read-write attribute
         |
         +-- @ManagedOperation method
                 -> JMX operation
         |
         v
MBeanExporter / ModelMBean
         |
         v
MBeanServer
         |
         +-- getAttribute(ObjectName, attributeName)
         +-- setAttribute(ObjectName, Attribute)
         +-- invoke(ObjectName, operationName, params, signature)
         |
         v
Integration test / JConsole / JMX client
\`\`\`

A JMX client should only use what the MBean **actually exposes**, rather than inferring from all public methods on the Java class.

## 3. Distinguishing the Three Operation Types

| Type | JMX API | Test Contract |
|---|---|---|
| Read-only attribute | \`getAttribute\` | Reads successfully; metadata readable=true, writable=false |
| Read-write attribute | \`getAttribute\`, \`setAttribute\` | Read old value, write valid value, read back and check state |
| Operation | \`invoke\` | Correct name, parameter count/types, return value, and side effects |

Example properties:

\`\`\`text
QueueDepth : int
  readable=true
  writable=false

MaxWorkers : int
  readable=true
  writable=true

resetCounters() : void
  operation
\`\`\`

Attributes typically follow JavaBeans conventions: \`getQueueDepth()\` maps to \`QueueDepth\`; \`getMaxWorkers()\` and \`setMaxWorkers(int)\` can form a read-write attribute. However, actual permissions depend on the assembler and applied annotations, so metadata must be verified.

## 4. Sample MBean for Testing

Build a simple MBean with both read-only metrics and modifiable configuration.

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=QueueControl,name=main",
    description = "Queue management test MBean"
)
public class QueueControl {

    private final AtomicInteger queueDepth = new AtomicInteger(3);
    private volatile int maxWorkers = 4;

    @ManagedAttribute(
        description = "Current queue depth"
    )
    public int getQueueDepth() {
        return queueDepth.get();
    }

    @ManagedAttribute(
        description = "Configured worker limit"
    )
    public int getMaxWorkers() {
        return maxWorkers;
    }

    @ManagedAttribute(
        description = "Configured worker limit"
    )
    public void setMaxWorkers(int maxWorkers) {
        if (maxWorkers < 1 || maxWorkers > 64) {
            throw new IllegalArgumentException(
                "maxWorkers must be between 1 and 64"
            );
        }
        this.maxWorkers = maxWorkers;
    }

    @ManagedOperation(
        description = "Clear queue depth counter"
    )
    public void resetCounters() {
        queueDepth.set(0);
    }

    @ManagedOperation(
        description = "Add synthetic queue entries"
    )
    public int addEntries(int count) {
        if (count <= 0 || count > 100) {
            throw new IllegalArgumentException(
                "count must be 1..100"
            );
        }
        return queueDepth.addAndGet(count);
    }
}
\`\`\`

Meaning:

- \`QueueDepth\`: only the getter is exposed, making it read-only in this annotation model.
- \`MaxWorkers\`: both getter and setter are annotated, making it read-write.
- \`resetCounters()\`: zero-argument operation returning void.
- \`addEntries(int)\`: operation taking primitive \`int\` and returning \`int\`.
- Validation in the setter and operation demonstrates errors on invalid input.

This code is a test fixture. In real applications, do not expose operations that mutate business state without proper authorization and auditing.

## 5. Java Configuration for Spring JMX

For deterministic testing, configure the exporter to use a specific \`MBeanServer\`.

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = QueueControl.class)
@EnableMBeanExport(server = "jmxServer")
public class JmxTestConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

\`@EnableMBeanExport\` enables annotation-based export; \`server = "jmxServer"\` references the **Spring bean name**, not a hostname or JMX endpoint URL.

If you choose the platform MBeanServer, tests sharing the same JVM may collide on ObjectNames. To isolate tests, create a dedicated server:

\`\`\`java
@Bean
public MBeanServer jmxServer() {
    return javax.management.MBeanServerFactory
        .newMBeanServer("learning.test");
}
\`\`\`

Using a custom server avoids collisions with the platform MBeanServer, though local JConsole attach usually will not automatically display MBeans in a private server. For integration tests, inject and query the exact server configured for the exporter.

## 6. Preparation Step: Verify the MBean Is Registered

Before calling any attribute or operation:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=QueueControl,name=main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}
\`\`\`

\`isRegistered\` returns \`true\` for a specific ObjectName in the **current MBeanServer**. It does not prove the bean published the right metadata; read \`MBeanInfo\` as well.

If \`isRegistered=false\`, check component scanning, \`@ManagedResource\`, the exporter, ObjectName, and the server being used before attempting invocations.

## 7. Reading MBeanInfo

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.printf(
        "Attribute %s type=%s readable=%s writable=%s%n",
        a.getName(),
        a.getType(),
        a.isReadable(),
        a.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    for (MBeanParameterInfo p : op.getSignature()) {
        System.out.print(p.getType() + " ");
    }

    System.out.println(") -> " + op.getReturnType());
}
\`\`\`

Expected metadata example:

\`\`\`text
Attribute QueueDepth type=int readable=true writable=false
Attribute MaxWorkers type=int readable=true writable=true
resetCounters() -> void
addEntries(int) -> int
\`\`\`

Attribute names, types, and read/write permissions from \`MBeanInfo\` represent the JMX contract clients see. In environments with multiple exporters or custom assemblers, do not rely solely on annotations in source code.

## 8. Testing a Read-Only Attribute

How to read:

\`\`\`java
Object rawDepth = server.getAttribute(
    name,
    "QueueDepth"
);

int depth = (Integer) rawDepth;
System.out.println(depth);
\`\`\`

\`getQueueDepth()\` returns primitive \`int\`, while JMX \`getAttribute\` returns \`Object\`, so the value is normally boxed as \`Integer\`.

An assertion:

\`\`\`java
assertEquals(
    3,
    server.getAttribute(name, "QueueDepth")
);
\`\`\`

### Verifying Non-Writability

\`\`\`java
MBeanAttributeInfo depthInfo =
    Arrays.stream(server.getMBeanInfo(name).getAttributes())
        .filter(a -> a.getName().equals("QueueDepth"))
        .findFirst()
        .orElseThrow();

assertTrue(depthInfo.isReadable());
assertFalse(depthInfo.isWritable());
\`\`\`

This checks metadata. To verify runtime behavior, attempt a write once in a separate test and expect failure.

\`\`\`java
assertThrows(
    javax.management.AttributeNotFoundException.class,
    () -> server.setAttribute(
        name,
        new javax.management.Attribute("QueueDepth", 99)
    )
);
\`\`\`

Depending on the implementation/adapter, the exception type may be wrapped or differ if validation occurs elsewhere. Do not rely solely on a single exception class to conclude the MBean is properly protected; combine metadata checks with verifying state remains unchanged.

**Never try writing a read-only attribute in production just to prove an error.** Use a test fixture or test environment.

## 9. Testing a Read-Write Attribute

Read the initial value:

\`\`\`java
int before = (Integer) server.getAttribute(
    name,
    "MaxWorkers"
);
\`\`\`

Write a new value:

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxWorkers", 8)
);
\`\`\`

Read back:

\`\`\`java
int after = (Integer) server.getAttribute(
    name,
    "MaxWorkers"
);

assertEquals(8, after);
\`\`\`

**Important:** \`Attribute\` takes the JMX attribute name and value, not the Java method name. Use \`"MaxWorkers"\`, not \`"setMaxWorkers"\`.

For a primitive \`int\` setter, the value \`8\` inside \`Attribute\` is boxed as \`Integer\`. Passing \`Long.valueOf(8)\` for an \`int\` attribute may cause a type mismatch error.

### Checking Bean State

If you have access to the Spring bean:

\`\`\`java
QueueControl bean = context.getBean(QueueControl.class);

assertEquals(
    8,
    bean.getMaxWorkers()
);
\`\`\`

Combining a JMX read-back with inspecting bean state confirms the attribute routes to the right object rather than another MBean with the same name on a different server.

## 10. Testing Invalid Setter Values

Setter with validation:

\`\`\`java
if (maxWorkers < 1 || maxWorkers > 64) {
    throw new IllegalArgumentException(...);
}
\`\`\`

Test:

\`\`\`java
int oldValue = (Integer) server.getAttribute(
    name,
    "MaxWorkers"
);

assertThrows(
    RuntimeException.class,
    () -> server.setAttribute(
        name,
        new Attribute("MaxWorkers", -5)
    )
);

assertEquals(
    oldValue,
    server.getAttribute(name, "MaxWorkers")
);
\`\`\`

\`RuntimeException.class\` here is a broad example illustrating the failure path; in real tests, observe the exact exception wrapped by the JMX ModelMBean/adapter, then assert the matching type and cause for your runtime.

Ensure the setter **validates before mutating**. If the setter updates state before throwing, the "state unchanged" check will fail and reveal an unsafe control path.

## 11. Invoking a Zero-Argument Operation

Method:

\`\`\`java
@ManagedOperation
public void resetCounters() {
    queueDepth.set(0);
}
\`\`\`

JMX invocation:

\`\`\`java
Object result = server.invoke(
    name,
    "resetCounters",
    new Object[0],
    new String[0]
);
\`\`\`

Verification:

\`\`\`java
assertNull(result);

assertEquals(
    0,
    server.getAttribute(name, "QueueDepth")
);
\`\`\`

A pair of empty arrays accurately represents "no arguments". \`new Object[] { null }\` is one \`null\` argument, not equivalent to an empty array.

For a \`void\` method, \`invoke\` normally returns \`null\`. However, \`invoke\` succeeding does not by itself prove that an **asynchronous** task launched by the operation has finished. If the operation enqueues a job, wait for or query job status.

## 12. Invoking an Operation with Parameters

Method:

\`\`\`java
@ManagedOperation
public int addEntries(int count) {
    return queueDepth.addAndGet(count);
}
\`\`\`

Invoke:

\`\`\`java
Object result = server.invoke(
    name,
    "addEntries",
    new Object[] { 5 },
    new String[] { "int" }
);
\`\`\`

If the counter was previously reset, the expected return value is \`5\`.

\`\`\`java
assertEquals(5, result);
assertEquals(5, server.getAttribute(name, "QueueDepth"));
\`\`\`

**The signature must use the declared Java type name**, not the runtime class of the object in \`Object[]\`. For \`addEntries(int)\`, the signature is \`"int"\`, even though \`5\` is boxed into \`Integer\`.

An incorrect invocation:

\`\`\`java
server.invoke(
    name,
    "addEntries",
    new Object[] { Integer.valueOf(5) },
    new String[] { "java.lang.Integer" }
);
\`\`\`

may fail to locate \`addEntries(int)\`. JMX does not automatically resolve overloads using all Java compiler boxing/widening rules.

## 13. Verifying Signature Metadata Before Invoke

\`\`\`java
MBeanOperationInfo op = Arrays.stream(
    server.getMBeanInfo(name).getOperations()
)
    .filter(o -> o.getName().equals("addEntries"))
    .filter(o -> o.getSignature().length == 1)
    .filter(o -> "int".equals(o.getSignature()[0].getType()))
    .findFirst()
    .orElseThrow();

assertEquals("int", op.getReturnType());
\`\`\`

If overloaded methods share a name, match the entire parameter type list. Matching by operation name or argument count alone can pick the wrong overload.

Inspecting \`MBeanInfo\` is especially helpful when the exporter uses a custom assembler or when the client is compiled separately from the server.

## 14. Integration Test Scenario with JUnit 5 and Spring Test

Example JUnit 5 skeleton:

\`\`\`java
package example.jmx;

import java.util.Arrays;
import javax.management.Attribute;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(JmxTestConfiguration.class)
class QueueControlJmxTest {

    @Autowired
    MBeanServer server;

    @Autowired
    QueueControl queueControl;

    private ObjectName name() throws Exception {
        return new ObjectName(
            "learning.jmx:type=QueueControl,name=main"
        );
    }

    @Test
    void readOnlyAttributeIsReadable() throws Exception {
        ObjectName name = name();

        assertTrue(server.isRegistered(name));

        MBeanAttributeInfo metadata = Arrays.stream(
            server.getMBeanInfo(name).getAttributes()
        )
            .filter(a -> a.getName().equals("QueueDepth"))
            .findFirst()
            .orElseThrow();

        assertTrue(metadata.isReadable());
        assertFalse(metadata.isWritable());
        assertEquals(
            queueControl.getQueueDepth(),
            server.getAttribute(name, "QueueDepth")
        );
    }

    @Test
    void readWriteAttributeChangesState() throws Exception {
        ObjectName name = name();

        server.setAttribute(
            name,
            new Attribute("MaxWorkers", 8)
        );

        assertEquals(8, server.getAttribute(name, "MaxWorkers"));
        assertEquals(8, queueControl.getMaxWorkers());
    }

    @Test
    void operationCanBeInvoked() throws Exception {
        ObjectName name = name();

        server.invoke(
            name,
            "resetCounters",
            new Object[0],
            new String[0]
        );

        Object result = server.invoke(
            name,
            "addEntries",
            new Object[] { 5 },
            new String[] { "int" }
        );

        assertEquals(5, result);
        assertEquals(5, server.getAttribute(name, "QueueDepth"));
    }
}
\`\`\`

The test suite uses a Spring context created via \`@SpringJUnitConfig\`. With an \`MBeanServer\` bean declared in \`JmxTestConfiguration\`, the server can be injected with \`@Autowired\`.

### Notes on Test Independence

Tests that mutate state such as \`setMaxWorkers\` or \`resetCounters\` can affect one another if they share a context and run in parallel. Therefore:

- Reset state in \`@BeforeEach\` or use a fresh fixture.
- Use a dedicated test server where appropriate.
- Do not rely on test execution order.
- Avoid running tests that write to the same MBean in parallel without isolation.
- Close contexts and clean up MBeans according to Spring Test's lifecycle.

## 15. Isolating MBeanServer for Tests

If using the platform MBeanServer:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

other tests in the same JVM may also register:

\`\`\`text
learning.jmx:type=QueueControl,name=main
\`\`\`

When that happens, \`InstanceAlreadyExistsException\` may occur.

One option is creating a dedicated MBeanServer for the test context:

\`\`\`java
@Bean
public MBeanServer jmxServer() {
    return MBeanServerFactory.newMBeanServer("learning.test");
}
\`\`\`

Use the same server for both the exporter and tests via \`@EnableMBeanExport(server="jmxServer")\`.

\`MBeanServerFactory.newMBeanServer\` creates a new server that is not added to registry discovery like \`createMBeanServer\`. Tests can still access it via the Spring bean. This keeps experiments from cluttering the platform JMX registry.

## 16. Testing Errors When Writing to a Read-Only Attribute

A negative test case:

\`\`\`java
assertThrows(
    Exception.class,
    () -> server.setAttribute(
        name,
        new Attribute("QueueDepth", 50)
    )
);
\`\`\`

The assertion above only ensures an exception occurs, so combine it with:

\`\`\`java
assertFalse(
    Arrays.stream(server.getMBeanInfo(name).getAttributes())
        .filter(a -> a.getName().equals("QueueDepth"))
        .findFirst()
        .orElseThrow()
        .isWritable()
);
\`\`\`

Then verify that the value of \`QueueDepth\` remains unchanged.

If no setter is exported, the JMX server rejects the write according to metadata. Never modify the implementation to "allow a setter" just to make a test convenient, as that alters the management contract.

## 17. Testing Wrong Attribute Types

The \`MaxWorkers\` attribute is declared as \`int\`. Try passing an incompatible type:

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxWorkers", "eight")
);
\`\`\`

Normally, the setter will reject a \`String\` instead of \`int\`. Check the appropriate exception and verify the state remains unchanged.

However, do not assume every framework adapter always throws the exact same exception class. Some errors may be wrapped in \`InvalidAttributeValueException\`, \`MBeanException\`, or a runtime wrapper depending on the call path.

## 18. Testing Non-Existent Operations

\`\`\`java
server.invoke(
    name,
    "missingOperation",
    new Object[0],
    new String[0]
);
\`\`\`

Expect the call to fail, typically as a \`ReflectionException\` or corresponding JMX error.

This is a useful check to confirm the MBean does not expose operations outside the allowlist. However, to verify the entire exposed surface, iterate through \`MBeanInfo.getOperations()\` and compare against the expected contract rather than probing random names.

## 19. Distinguishing Attributes from Operations

A Java getter such as:

\`\`\`java
public int getQueueDepth()
\`\`\`

can be exposed as attribute \`QueueDepth\`, not as operation \`getQueueDepth\`.

Clients typically read via:

\`\`\`java
server.getAttribute(name, "QueueDepth");
\`\`\`

rather than:

\`\`\`java
server.invoke(
    name,
    "getQueueDepth",
    new Object[0],
    new String[0]
);
\`\`\`

Do not treat the two as equivalent unless the MBean metadata explicitly exposes a separate \`getQueueDepth\` operation. The same Java method may be modeled differently by the adapter depending on the assembler, so clients must adhere to the registered management contract.

## 20. How Remote Testing Differs from Local Testing

\`MBeanServer\` implements \`MBeanServerConnection\`, so most test APIs can be shared:

\`\`\`java
MBeanServerConnection connection = server;
\`\`\`

Remote JMX:

\`\`\`java
try (JMXConnector connector =
         JMXConnectorFactory.connect(serviceUrl, environment)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    // getAttribute / setAttribute / invoke
}
\`\`\`

For remote testing, also consider:

- TCP/RMI connectivity, timeouts, and firewalls.
- Authentication, authorization, and TLS.
- Data types serialized across the connector.
- Distinguishing timeouts from actual operation failures.
- The possibility that the operation executed even though the response was lost.
- Whether the MBeanServer exposed by the connector matches the one used by the exporter.

Do not blindly retry side-effecting operations after a timeout; they may already have executed.

## 21. Testing via JConsole

A manual scenario:

1. Start the Spring context with the MBean exported to the platform server.
2. Open JConsole and select the target JVM.
3. Navigate to the **MBeans** tab.
4. Locate \`learning.jmx:type=QueueControl,name=main\`.
5. Open **Attributes** and confirm \`QueueDepth\` is read-only.
6. Read \`MaxWorkers\`, change it to a valid value, and read it back.
7. Open **Operations** and invoke \`resetCounters\`.
8. Invoke \`addEntries\` with an integer value.
9. Read \`QueueDepth\` again and confirm the change.
10. Stop the app and observe the unregistration lifecycle if needed.

JConsole may render attribute editors differently in the GUI depending on data types and implementation. If the GUI does not allow an action, inspect metadata and use a Java client to verify the JMX API rather than relying solely on the UI.

## 22. Security and Operational Notes

Operations and writable attributes can alter live application state. Therefore:

- Test only in fixtures or test environments; never run state-changing commands in production without approval.
- Deliberately restrict exported MBeans and ObjectNames.
- Enable authentication, authorization, and TLS whenever a remote connector is active.
- Do not assume Spring Security HTTP filters automatically protect JMX.
- Never expose getters returning secrets or user data.
- Audit critical operations and writable attributes.
- Avoid logging full parameter values if they may contain sensitive data.

JMX testing verifies that the management API works, but it must also verify that **only the intended API** is published.

## 23. Testing Checklist

- [ ] Managed Spring bean is created in the context.
- [ ] Exporter uses the right MBeanServer.
- [ ] ObjectName is registered without collisions.
- [ ] \`MBeanInfo\` accurately reflects expected attributes and operations.
- [ ] Read-only attributes have \`readable=true\`, \`writable=false\`.
- [ ] Read-only attributes can be read via \`getAttribute\`.
- [ ] Writing to read-only attributes is rejected.
- [ ] Read-write attributes succeed on read/write/read-back.
- [ ] Setters reject invalid input and protect state.
- [ ] Zero-argument operations are invoked with empty arrays.
- [ ] Parameterized operations use exact signatures.
- [ ] Return values and side effects are verified.
- [ ] Type mismatches, signature mismatches, and non-existent operations are handled.
- [ ] Tests do not depend on ordering or share unintended state.
- [ ] Remote connectors are tested separately when that access path is supported.

## 24. Practice Exercises

### Exercise 1: Read-Only Attribute

Add attribute:

\`\`\`java
@ManagedAttribute
public boolean isHealthy() {
    return true;
}
\`\`\`

Read \`Healthy\` via JMX, inspect metadata, and confirm no JMX setter is published.

### Exercise 2: Read-Write Attribute

Add:

\`\`\`java
private volatile long timeoutMillis = 1000;

@ManagedAttribute
public long getTimeoutMillis() {
    return timeoutMillis;
}

@ManagedAttribute
public void setTimeoutMillis(long value) {
    if (value < 100 || value > 60_000) {
        throw new IllegalArgumentException(
            "timeoutMillis out of range"
        );
    }
    timeoutMillis = value;
}
\`\`\`

Test \`setAttribute\` with \`Long.valueOf(3000)\`, read back \`TimeoutMillis\`, and test \`-1\` to verify validation.

### Exercise 3: Two-Parameter Operation

\`\`\`java
@ManagedOperation
public String schedule(String queueName, int batchSize) {
    return queueName + ":" + batchSize;
}
\`\`\`

How to invoke:

\`\`\`java
Object result = server.invoke(
    name,
    "schedule",
    new Object[] { "orders", 20 },
    new String[] { "java.lang.String", "int" }
);
\`\`\`

Verify the result \`"orders:20"\`. Then swap the signature order to observe the error and explain why clients must pass the exact declared types.

## 25. Self-Check Questions

1. Are read-only attributes determined by Java getters or JMX metadata?
2. Can \`getAttribute\` and \`invoke\` substitute for each other for every method?
3. Why does \`setAttribute\` use \`Attribute("MaxWorkers", 8)\`?
4. Do \`int\` and \`java.lang.Integer\` produce the same operation signature?
5. Why must you check state after an operation returns?
6. How do you verify that a getter is exported while a setter is not?
7. Why can multiple test methods mutating the same bean depend on each other?
8. When a remote invocation times out, can you assume the operation never ran?
9. How does a dedicated MBeanServer help tests?
10. Why should JMX tests verify both metadata and actual runtime behavior?

## 26. Key Takeaways

\`\`\`text
MBeanInfo -> published contract
    |
    +-- Read-only attribute
    |       getAttribute()
    |       setAttribute() must be rejected
    |
    +-- Read-write attribute
    |       getAttribute()
    |       setAttribute()
    |       getAttribute() to verify
    |
    +-- Operation
            invoke(name, op, params, signature)
            check return value + side effects
\`\`\`

**Core principle:** Spring JMX testing must go through a **real MBeanServer** to confirm exactly what management clients see. For read-only attributes, verify permissions and readability. For read-write attributes, verify writing, reading back, and validation. For operations, pass exact JMX signatures and verify both return values and state; reading annotations in source code or seeing an MBean exist is not enough.
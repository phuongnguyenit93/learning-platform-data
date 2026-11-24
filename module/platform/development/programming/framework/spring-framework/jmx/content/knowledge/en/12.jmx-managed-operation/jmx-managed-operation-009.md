# Testing Operation Invocation via MBeanServer in Spring Framework JMX

## Lesson Objectives

After this lesson, you will be able to:

- Explain why testing a Java method directly is not enough to prove the operation is actually published via JMX.
- Create a Spring bean using **@ManagedResource** and **@ManagedOperation**, then register it as an MBean.
- Use **MBeanServer.invoke(ObjectName, operationName, params, signature)** to invoke an operation like a JMX client.
- Write integration tests verifying ObjectName, operation metadata, return values, parameters, errors, and side effects.
- Distinguish invoking via MBeanServer inside the same JVM from invoking via MBeanServerConnection from an external client.
- Handle common errors: InstanceNotFoundException, ReflectionException, MBeanException, wrong signatures, operation names, or exporter configuration.

## 1. Why Test at the JMX Boundary?

Suppose a Spring bean has a method:

\`\`\`java
public void clearCache() {
    cache.clear();
}
\`\`\`

A unit test can call it directly:

\`\`\`java
cacheManager.clearCache();
\`\`\`

If the test passes, you only know the Java method works within the object scope. You **have not proven** that the method is exported by Spring as a JMX operation, has the right ObjectName and operation name, has a signature understood by JMX clients, or is invocable through MBeanServer.

In Spring Framework JMX, the administrative path is typically:

\`\`\`text
Spring ApplicationContext
    |
    +-- bean with @ManagedResource, @ManagedOperation
    |
    v
MBeanExporter + MBeanInfoAssembler
    |
    v
MBeanServer.registerMBean(...)
    |
    v
MBeanServer.invoke(ObjectName, operationName, params, signature)
    |
    v
Managed operation in Spring bean
\`\`\`

An integration test at the \`MBeanServer.invoke\` boundary verifies **registration**, **metadata mapping**, and **method invocation**. This is critical testing when JConsole, operational scripts, or other management systems depend on the JMX contract.

## 2. The MBeanServer invoke API

Central method:

\`\`\`java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
)
\`\`\`

Parameters:

| Parameter | Meaning | Example |
|---|---|---|
| \`name\` | ObjectName identifying the target MBean | \`learning.jmx:type=Queue,name=Primary\` |
| \`operationName\` | Published operation name | \`pause\` |
| \`params\` | Array of arguments passed in order | \`new Object[] { 25 }\` |
| \`signature\` | Array of Java type names for each parameter | \`new String[] { "int" }\` |
| Return value | Operation result or null if void | \`Boolean.TRUE\`, \`null\` |

An operation taking no parameters:

\`\`\`java
Object result = server.invoke(
    objectName,
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

An operation taking \`int\`:

\`\`\`java
Object result = server.invoke(
    objectName,
    "setThreshold",
    new Object[] { 25 },
    new String[] { "int" }
);
\`\`\`

The \`signature\` array holds **Java type names per the JMX contract**, not values. For example, \`"int"\` differs from \`"java.lang.Integer"\` if the actual method accepts primitive \`int\`. For zero-parameter operations, passing empty arrays is the clearest representation.

**Note:** Parameters and signatures must match the count, order, and types of the exported operation. The compiler does not verify the operation name in the string \`"setThreshold"\`; contract mismatches usually appear only at runtime.

## 3. @ManagedOperation Defines the Management Surface

Spring Framework provides the annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
\`\`\`

Example:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
public class QueueAdministration {

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pause() {
        // ...
    }
}
\`\`\`

\`@ManagedResource\` identifies a managed resource. \`@ManagedOperation\` marks a method to be published as an operation when the exporter uses annotation-based metadata assembly.

A public method **without the annotation** is not automatically exported just because it is public, when the metadata assembler configuration uses annotation-based selection.

\`@ManagedOperationParameter\` helps describe parameters so tooling displays them more clearly:

\`\`\`java
@ManagedOperation(description = "Change queue threshold")
@ManagedOperationParameter(
    index = 0,
    name = "threshold",
    description = "Non-negative queue threshold"
)
public void setThreshold(int threshold) {
    // ...
}
\`\`\`

Parameter description annotations do not change the operation's Java type. \`signature\` on invoke must still be \`"int"\`.

## 4. Example Spring Bean with Operations

Let's create a queue management component with simple state:

- \`pause()\`: stops accepting new jobs.
- \`resume()\`: allows accepting jobs.
- \`updateThreshold(int)\`: changes the threshold.
- \`describeState()\`: returns state as a String.

### 4.1. Managed Resource Class

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary",
    description = "Operational queue management"
)
public class QueueAdministration {

    private boolean paused;
    private int threshold = 100;

    @ManagedAttribute(description = "Whether queue is paused")
    public synchronized boolean isPaused() {
        return paused;
    }

    @ManagedAttribute(description = "Current queue threshold")
    public synchronized int getThreshold() {
        return threshold;
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public synchronized void pause() {
        paused = true;
    }

    @ManagedOperation(description = "Resume accepting jobs")
    public synchronized void resume() {
        paused = false;
    }

    @ManagedOperation(description = "Update the queue threshold")
    @ManagedOperationParameter(
        index = 0,
        name = "newThreshold",
        description = "A positive threshold"
    )
    public synchronized void updateThreshold(int newThreshold) {
        if (newThreshold <= 0) {
            throw new IllegalArgumentException(
                "newThreshold must be greater than zero"
            );
        }
        threshold = newThreshold;
    }

    @ManagedOperation(description = "Describe current queue state")
    public synchronized String describeState() {
        return "paused=" + paused + ",threshold=" + threshold;
    }

    // Not part of the annotation-based management contract.
    public void applicationInternalMethod() {
        // ...
    }
}
\`\`\`

The code above illustrates the administrative API; in a real application, pause/resume logic must connect to the actual queue processing mechanism, ensuring thread safety and proper authorization.

### 4.2. Configuring the Spring JMX Exporter

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    QueueAdministration queueAdministration() {
        return new QueueAdministration();
    }
}
\`\`\`

\`@EnableMBeanExport\` enables annotation-based JMX export infrastructure. When the Spring context initializes, the exporter discovers \`QueueAdministration\` via \`@ManagedResource\` and registers the MBean under the ObjectName on the annotation.

**Environment condition:** Tests must use the MBeanServer matching the exporter. In an application with multiple MBeanServers or a custom-configured exporter, do not assume \`ManagementFactory.getPlatformMBeanServer()\` is always the server actually holding the MBean. The test examples below use a dedicated MBeanServer to avoid conflicts with the platform server and make the export target explicit.

## 5. Configuring Tests with a Dedicated MBeanServer

To isolate tests and prevent ObjectName collisions when other tests run in the same JVM, you can provide a dedicated MBeanServer for \`@EnableMBeanExport\`.

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "testMBeanServer")
public class TestJmxConfiguration {

    @Bean(name = "testMBeanServer")
    MBeanServer testMBeanServer() {
        return MBeanServerFactory.createMBeanServer("test.jmx");
    }

    @Bean
    QueueAdministration queueAdministration() {
        return new QueueAdministration();
    }
}
\`\`\`

In this context, the exporter must use the \`testMBeanServer\` bean. The test retrieves the server from the same Spring context to ensure it invokes against where registration happened.

Note: if a project already has multiple JMX exporter configurations, do not import all of them into a test simultaneously because that can lead to duplicate registration or an unexpected export mechanism.

## 6. Integration Test: Invoking a Zero-Parameter Operation

Example using JUnit Jupiter (JUnit 5). Assumes Spring Framework and JUnit 5 dependencies are configured in the build.

\`\`\`java
package example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class QueueAdministrationJmxTest {

    private static final String MBEAN_NAME =
        "learning.jmx:type=Queue,name=Primary";

    @Test
    void pauseAndResumeAreCallableThroughMBeanServer()
            throws Exception {

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        TestJmxConfiguration.class)) {

            MBeanServer server =
                    context.getBean("testMBeanServer", MBeanServer.class);

            ObjectName name = new ObjectName(MBEAN_NAME);

            assertTrue(server.isRegistered(name));

            Object pauseResult = server.invoke(
                    name,
                    "pause",
                    new Object[0],
                    new String[0]
            );

            assertNull(pauseResult);
            assertEquals(Boolean.TRUE,
                    server.getAttribute(name, "Paused"));

            Object resumeResult = server.invoke(
                    name,
                    "resume",
                    new Object[0],
                    new String[0]
            );

            assertNull(resumeResult);
            assertEquals(Boolean.FALSE,
                    server.getAttribute(name, "Paused"));
        }
    }
}
\`\`\`

This test verifies multiple layers:

1. The Spring context creates the managed resource and exporter.
2. The MBean is registered under the exact ObjectName.
3. Operation \`pause\` exists with an empty signature.
4. Operation \`resume\` exists with an empty signature.
5. State observed via the JMX attribute changes as expected.

This is the difference compared to a test that only calls \`QueueAdministration.pause()\` directly.

## 7. Integration Test: Parameterized Operation

\`\`\`java
@Test
void updateThresholdAcceptsIntParameter() throws Exception {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    TestJmxConfiguration.class)) {

        MBeanServer server =
                context.getBean("testMBeanServer", MBeanServer.class);

        ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
        );

        assertEquals(100, server.getAttribute(name, "Threshold"));

        Object result = server.invoke(
                name,
                "updateThreshold",
                new Object[] { 250 },
                new String[] { "int" }
        );

        assertNull(result);
        assertEquals(250, server.getAttribute(name, "Threshold"));
    }
}
\`\`\`

Verification points:

- The operation name is \`updateThreshold\`, not a name guessed from the description.
- The signature uses \`"int"\` because the Java method accepts primitive \`int\`.
- \`new Object[] { 250 }\` passes a boxed Integer into the JMX invocation; JMX uses the signature to locate the matching method.
- The return value of a \`void\` operation is \`null\`.
- Re-read the \`Threshold\` attribute to prove the operation mutated state.

### Where Is Signature Easy to Get Wrong?

Suppose a client passes:

\`\`\`java
server.invoke(
    name,
    "updateThreshold",
    new Object[] { 250 },
    new String[] { "java.lang.Integer" }
);
\`\`\`

If the exporter only publishes the operation with signature \`int\`, the client may fail to find a matching operation. Reflection/invocation errors depend on metadata and implementation. Contract tests should always read \`MBeanOperationInfo\` accurately and avoid guessing signatures from runtime values.

## 8. Verifying Metadata with MBeanInfo

An MBean can be registered yet the desired operation is not published due to a missing \`@ManagedOperation\`, wrong assembler, or configuration differences. Therefore, inspect metadata before drawing conclusions.

\`\`\`java
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());

    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.println(
            "  " + parameter.getName() + ": "
            + parameter.getType()
        );
    }
}
\`\`\`

Contract test example:

\`\`\`java
import java.util.Arrays;

boolean hasUpdateThreshold = Arrays.stream(
        server.getMBeanInfo(name).getOperations()
).anyMatch(operation ->
        "updateThreshold".equals(operation.getName())
        && operation.getSignature().length == 1
        && "int".equals(
                operation.getSignature()[0].getType()
        )
);

assertTrue(hasUpdateThreshold);
\`\`\`

Metadata is the actual contract that JMX clients see after the Spring exporter processes annotations. Reading \`MBeanInfo\` is especially helpful when code uses Spring AOP proxies or custom metadata assemblers.

## 9. Testing Return Values

An operation returning \`String\`:

\`\`\`java
@ManagedOperation
public synchronized String describeState() {
    return "paused=" + paused + ",threshold=" + threshold;
}
\`\`\`

Test:

\`\`\`java
Object result = server.invoke(
        name,
        "describeState",
        new Object[0],
        new String[0]
);

assertEquals(
        "paused=false,threshold=100",
        result
);
\`\`\`

No cast is needed when using \`assertEquals\`, though when API consumers want explicit type handling, you can assert:

\`\`\`java
assertInstanceOf(String.class, result);
\`\`\`

If an operation returns a custom object, remote JMX clients can encounter serialization/classpath issues. For management APIs used across JVMs, consider simple types or appropriate MXBean/Open Types.

## 10. Testing Errors from a Managed Operation

The \`updateThreshold(int)\` operation throws \`IllegalArgumentException\` when the parameter is invalid.

\`\`\`java
@Test
void invalidThresholdIsRejectedThroughJmx() throws Exception {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    TestJmxConfiguration.class)) {

        MBeanServer server =
                context.getBean("testMBeanServer", MBeanServer.class);

        ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
        );

        Exception error = assertThrows(
                Exception.class,
                () -> server.invoke(
                    name,
                    "updateThreshold",
                    new Object[] { -1 },
                    new String[] { "int" }
                )
        );

        assertNotNull(error);
        assertEquals(100, server.getAttribute(name, "Threshold"));
    }
}
\`\`\`

The test above keeps the exception type relatively broad to illustrate the idea. When verifying a specific implementation, assert the exact wrapper exception and root cause.

### How JMX Represents Exceptions

Several errors to distinguish:

- \`InstanceNotFoundException\`: MBean not found by ObjectName.
- \`ReflectionException\`: error related to identifying/invoking the operation via reflection or signature.
- \`MBeanException\`: wrapper for checked exceptions thrown from an operation in certain cases.
- \`RuntimeMBeanException\`: wrapper for runtime exceptions thrown by an operation/managed resource.
- \`RuntimeErrorException\`: can wrap an \`Error\` in the MBean invocation path.

For example, for \`IllegalArgumentException\` in a standard JMX implementation, you can encounter \`RuntimeMBeanException\` with the corresponding cause. Verify the actual exception wrapper rather than assuming clients always receive the exact same Java exception directly as in an internal method call.

Example assertion focused on runtime exceptions:

\`\`\`java
import javax.management.RuntimeMBeanException;

RuntimeMBeanException thrown = assertThrows(
    RuntimeMBeanException.class,
    () -> server.invoke(
        name,
        "updateThreshold",
        new Object[] { -1 },
        new String[] { "int" }
    )
);

assertInstanceOf(
    IllegalArgumentException.class,
    thrown.getCause()
);
\`\`\`

When applying this to Spring-exported MBeans, verify how the exporter/adapter wraps exceptions in your actual version. If the exporter changes wrapping semantics, tests should match the contract observable at the JMX boundary.

## 11. Testing Unexported Operations

A common configuration mistake is leaving a public method in a bean without \`@ManagedOperation\`:

\`\`\`java
public void applicationInternalMethod() {
    // ...
}
\`\`\`

With an annotation-based metadata assembler that only publishes selected methods, this method should not appear as a JMX operation.

How to verify:

\`\`\`java
boolean accidentallyExposed = Arrays.stream(
        server.getMBeanInfo(name).getOperations()
).anyMatch(operation ->
        "applicationInternalMethod".equals(operation.getName())
);

assertFalse(accidentallyExposed);
\`\`\`

This is a meaningful **management surface test**: it proves unintended business actions are not exposed over JMX.

Do not call the method directly and infer whether it was exported. Inspecting metadata reflects the JMX contract.

## 12. Lifecycle Testing: Registration and Unregistration

When MBeanExporter is managed by Spring, registration is typically tied to the context lifecycle.

Example:

\`\`\`java
@Test
void mbeanRegistrationFollowsSpringContextLifecycle()
        throws Exception {

    MBeanServer server = MBeanServerFactory.createMBeanServer(
            "isolated.lifecycle"
    );

    ObjectName name = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
    );

    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

    context.registerBean(
            "testMBeanServer",
            MBeanServer.class,
            () -> server
    );
    context.register(TestJmxConfiguration.class);

    try {
        context.refresh();
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(server.isRegistered(name));
}
\`\`\`

**Technical note:** In simple test configurations, avoid registering two MBeanServer beans with the same name if \`TestJmxConfiguration\` also declares \`testMBeanServer\`. Choose **one** place to create/supply the MBeanServer into the context. The example above illustrates server injection; if using TestJmxConfiguration intact from Section 5, simply obtain the server from that context before closing it.

A more consistent and concise variant:

\`\`\`java
@Test
void unexportsOnContextClose() throws Exception {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    TestJmxConfiguration.class
            );

    MBeanServer server =
            context.getBean("testMBeanServer", MBeanServer.class);

    ObjectName name = new ObjectName(
            "learning.jmx:type=Queue,name=Primary"
    );

    try {
        assertTrue(server.isRegistered(name));
    } finally {
        context.close();
    }

    assertFalse(server.isRegistered(name));
}
\`\`\`

Use only the variant that matches your actual configuration. Lifecycle is especially important if tests create multiple Spring contexts in the same JVM: failing to close a context can leave registrations behind and cause ObjectName collisions on subsequent runs.

## 13. Reading Operation Information from MBeanServerConnection

A custom client in another JVM typically uses \`MBeanServerConnection\`, without having the same in-memory \`MBeanServer\` object.

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteOperationClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
        );

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "learning.jmx:type=Queue,name=Primary"
            );

            Object result = connection.invoke(
                name,
                "describeState",
                new Object[0],
                new String[0]
            );

            System.out.println(result);
        }
    }
}
\`\`\`

This is a skeleton example for a pre-configured management environment. The hostname is only a placeholder, and connecting requires a running remote JMX server, network reachability, credentials, and proper TLS/access permissions. Never enable unauthenticated remote JMX in shared environments.

**Important difference:** \`MBeanServerConnection\` lets clients invoke the same contract remotely. Integration tests within the same JVM verify mapping and functionality, yet **do not prove** that the remote connector, network, authentication, TLS, or permission policies are configured correctly. If deployment requirements need remote JMX, add connectivity and authorization tests in an appropriate environment.

## 14. Diagnostic Checklist When an Operation Cannot Be Invoked

When encountering the error:

\`\`\`text
Operation updateThreshold not found
\`\`\`

check in order:

1. **Is the ObjectName right?** Use \`server.isRegistered(name)\`.
2. **Is the MBeanServer right?** Is the test using the same server where the exporter registered?
3. **Is the operation in metadata?** Use \`getMBeanInfo(name).getOperations()\`.
4. **Is the operation name exact?** JMX uses the exported method name, case-sensitive.
5. **Is the signature right?** Primitive \`int\` differs from \`java.lang.Integer\`.
6. **Do parameters match in count and types?** \`params.length\` must match \`signature.length\`.
7. **Is the method annotated?** Check \`@ManagedOperation\` and the assembler/exporter.
8. **Does the bean have an AOP proxy?** Inspect metadata/proxy class if the method does not appear.
9. **Did the operation throw during execution?** If metadata and signature are right yet invoke still fails, inspect wrapper exception and cause.
10. **Does the JMX client have permission to invoke?** For remote connections, permissions/authorization can block the operation.

### Common Misconceptions

**“A public method is a JMX operation.”** Not necessarily. In annotation-based Spring JMX, the metadata assembler decides which methods are published.

**“A unit test calling the method directly is enough.”** Not enough to verify ObjectName, exporter, metadata, and signature.

**“Zero-parameter operations must pass null.”** The API allows certain null forms depending on implementation, but empty arrays keep tests clear and consistent.

**“The Java operation accepts int, so the signature must use Integer.”** Wrong when declaring primitive \`int\`: the type name in signature is \`"int"\`.

**“If MBean registration succeeds, every method is invocable.”** Successful registration only proves the MBean is valid; each operation must be verified to be exposed properly.

## 15. Parallel Testing and Isolation

The JMX platform MBeanServer is a JVM-wide resource. If multiple tests register the same ObjectName into the platform server, they can conflict.

Ways to reduce collisions:

- Use a dedicated MBeanServer for integration tests as in the examples.
- Use distinct per-test ObjectNames if sharing a server is truly required.
- Close the ApplicationContext at the end of the test.
- Do not use RegistrationPolicy.REPLACE_EXISTING to mask tests overwriting MBeans belonging to other tests.
- Avoid creating too many MBeanServers without cleanup, especially when running many tests in the same JVM.
- When creating an MBeanServer via factory, you can call \`MBeanServerFactory.releaseMBeanServer(server)\` after the context closes and no consumers remain, if the server was registered in the factory and owned by the test.

If tests run under a Spring Boot configuration with Actuator JMX, note that Boot's auto-configured exporter may differ from manual configuration. Isolate test configuration so only one exporter owns the ObjectName under test.

## 16. Safely Testing Values and Side Effects

For an administrative operation, tests should verify both the **invocation result** and **state changes**.

Example pausing a queue:

\`\`\`java
server.invoke(name, "pause", new Object[0], new String[0]);

assertEquals(
    Boolean.TRUE,
    server.getAttribute(name, "Paused")
);
\`\`\`

For operations with real side effects such as clearing caches, restarting threads, or altering configuration, never invoke them against production instances just for testing. Use a test fixture with controlled side effects.

Check:

- Is the operation idempotent?
- Does calling repeatedly risk causing errors?
- When parameters are invalid, is the existing state preserved?
- Does the operation require authorization and auditing?
- Is the return value easy to serialize for JMX clients?
- What happens when the bean is shutting down?

These questions belong to the management contract, beyond simple unit tests.

## 17. Integration Test Checklist Template

A test invoking an operation via MBeanServer should answer:

| Check | Expectation |
|---|---|
| Context initializes successfully | Exporter runs without error |
| ObjectName is registered | \`isRegistered(name) == true\` |
| Operation appears | \`MBeanInfo\` contains expected name |
| Signature is right | Parameter names/types and order match |
| Invoke succeeds | No unexpected exception thrown |
| Return value | Matches contract type/value |
| Side effect | Attribute or state reflects the change |
| Invalid arguments | Errors wrapped/represented consistently |
| Internal methods | Not unintentionally exported |
| After context.close | Exporter-managed MBean is unregistered |
| Test isolation | Does not overwrite MBeans of other tests/apps |

You do not need to turn every operation into a huge test suite. For critical management APIs, test contracts likely to break compatibility when renaming, changing parameter types, or altering metadata.

## 18. Practice Exercises

### Exercise A — Write an Incrementing Counter Operation

Create \`CounterAdministration\` with:

\`\`\`java
@ManagedAttribute
public int getCount() { ... }

@ManagedOperation
public void increment() { ... }
\`\`\`

Write a test:

1. Create Spring context and exporter.
2. Check that ObjectName is registered.
3. Read initial \`Count\`.
4. Invoke \`increment\` via \`MBeanServer.invoke\`.
5. Re-read \`Count\` and confirm it incremented by one.

### Exercise B — Operation with Two Parameters

Create:

\`\`\`java
@ManagedOperation
public int multiply(int left, int right) {
    return left * right;
}
\`\`\`

Expected invoke call:

\`\`\`java
Object value = server.invoke(
    name,
    "multiply",
    new Object[] { 6, 7 },
    new String[] { "int", "int" }
);
\`\`\`

Verify the result with \`assertEquals(42, value)\`.

Try changing the second signature element to \`java.lang.Integer\` and observe the error; compare with MBeanInfo to explain.

### Exercise C — Unannotated Method

Add a public method \`deleteAllData()\` to the managed bean without annotating it. Use \`getMBeanInfo\` to verify this method is not published.

### Exercise D — Reject Invalid Parameters

Create an operation \`updateThreshold(int)\` throwing \`IllegalArgumentException\` if the value is negative. Invoke via JMX with \`-1\`, observe the exception wrapper, and verify the old threshold remains unchanged.

### Exercise E — Lifecycle

Create the context and confirm the MBean exists; close the context and confirm the MBean disappears. Then create a new context and verify export does not suffer a duplicate ObjectName collision.

## 19. Summary

Testing **operation invocation via MBeanServer** tests a management contract, not just a Java method.

Key points to remember:

1. \`@ManagedOperation\` exposes a method per Spring JMX metadata.
2. \`MBeanServer.invoke\` requires the exact ObjectName, operation name, params, and signature.
3. \`MBeanInfo\` is the source of truth for verifying exported operation names and types.
4. Test return values, post-action state, and how errors are represented.
5. Use a dedicated MBeanServer and close contexts to isolate tests and avoid ObjectName collisions.
6. Local invoke tests do not replace testing remote JMX connectors, security, and networking.
7. Never publish or invoke dangerous actions merely because a method is public.
8. When refactoring method names, parameter types, or exporter configuration, protect the contract JMX clients rely on.

## References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Framework API — EnableMBeanExport: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanOperationInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

# Writing Tests to Verify the Management Interface in Spring Framework JMX

## Practice Objectives

A management interface is the contract between an MBean and administrative tools using JMX. When a Spring Framework application exports a bean, you should not merely confirm that the application starts or that JConsole displays an ObjectName. You must verify precisely **which attributes are readable/writable, which operations are callable, which parameter types are supported, which internal methods are not exposed, and whether registrations are cleaned up when the context closes**.

This lab builds a small Standard MBean, writes unit/integration tests with JUnit 5 and `MBeanServer`, and then extends to Spring's `MBeanExporter`. The tests focus on the runtime contract exposed by the `MBeanServer`, not just Java reflection. The ultimate goal is a CI-stable test suite that catches breaking changes or accidental exposure of sensitive operations.

After this lesson, you will be able to:

- Create a Standard MBean interface following naming conventions.
- Write a management implementation with extra public methods outside the interface.
- Register the MBean on an isolated server for testing.
- Verify ObjectName, `MBeanInfo`, attributes, operations, and parameter signatures.
- Read an attribute and invoke an operation via `MBeanServerConnection`.
- Confirm that public methods outside the management interface are not exported.
- Verify that read-only attributes cannot be written via JMX.
- Write a Spring integration test for `MBeanExporter` lifecycle.
- Control cleanup and prevent ObjectName collisions when tests run in parallel.
- Design negative contract tests for version changes.

## 1. The Problem

Suppose a system has a job-processing worker. The operations team only needs to:

1. Read the worker state.
2. Read the total completed job count.
3. Read the failed job count.
4. Request a pause.
5. Request a resume.

The implementation still contains internal methods such as \`deleteCheckpoint\` or \`rebuildInternalIndex\`, yet these methods **must not be exposed to JMX**.

Contract:

\`\`\`text
WorkerRuntimeMBean
├── State                 [read-only attribute]
├── CompletedCount        [read-only attribute]
├── FailedCount           [read-only attribute]
├── requestPause()        [operation]
└── requestResume()       [operation]

WorkerRuntime implementation:
├── Methods in management interface
├── deleteCheckpoint(id)  [public Java method, not exported]
└── rebuildInternalIndex()[public Java method, not exported]
\`\`\`

Testing requirements:

| Category | Required Condition |
|---|---|
| Registration | ObjectName is registered |
| Metadata | Attributes State, CompletedCount, FailedCount are present |
| Read-only | None of the attributes above are writable |
| Operations | requestPause and requestResume are present, with no parameters |
| No internal method leaks | No deleteCheckpoint/rebuildInternalIndex |
| Behavior | Invoking requestPause changes effective state appropriately |
| Cleanup | ObjectName is gone after unregister |
| Spring lifecycle | Closing ApplicationContext removes MBeans owned by the exporter |

## 2. Tools and Sample Layout

The project can use Java 17+, Spring Framework, and JUnit Jupiter.

Example Maven dependencies for testing:

\`\`\`xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>\${spring.version}</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>\${junit.jupiter.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
\`\`\`

This is a dependency fragment, not a complete POM. In a real project, use your organization's dependency management and compatible versions, and configure Surefire/JUnit Platform appropriately. Java Management APIs such as \`javax.management.MBeanServer\` belong to the JDK \`java.management\` module, not an arbitrary JMX library downloaded from Maven.

Structure:

\`\`\`text
src/main/java/com/example/jmx/
  WorkerRuntimeMBean.java
  WorkerRuntime.java
  ManagementConfiguration.java

src/test/java/com/example/jmx/
  WorkerRuntimeMBeanContractTest.java
  SpringJmxExportTest.java
\`\`\`

In simple tests you do not need to start a remote connector, because a local \`MBeanServer\` is sufficient to verify the management contract. Remote JMX authentication/TLS testing belongs in a separate test suite.

## 3. Write the Standard MBean Interface

\`\`\`java
package com.example.jmx;

public interface WorkerRuntimeMBean {

    String getState();

    long getCompletedCount();

    long getFailedCount();

    void requestPause();

    void requestResume();
}
\`\`\`

Under Standard MBean conventions, the \`WorkerRuntime\` implementation matches the \`WorkerRuntimeMBean\` interface. Parameterless \`getXxx()\` methods are normally exposed by JMX introspection as attributes; control methods are exposed as operations.

Key point: the interface **defines the permitted management members**. Do not add service methods like \`deleteCheckpoint\` to the interface merely because they are public in Java.

## 4. Implementation: Separate Management API and Public Internal API

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public final class WorkerRuntime implements WorkerRuntimeMBean {

    private volatile String state = "RUNNING";
    private final AtomicLong completedCount = new AtomicLong();
    private final AtomicLong failedCount = new AtomicLong();

    @Override
    public String getState() {
        return state;
    }

    @Override
    public long getCompletedCount() {
        return completedCount.get();
    }

    @Override
    public long getFailedCount() {
        return failedCount.get();
    }

    @Override
    public void requestPause() {
        state = "PAUSED";
    }

    @Override
    public void requestResume() {
        state = "RUNNING";
    }

    // Internal Java API. NOT part of WorkerRuntimeMBean.
    public void deleteCheckpoint(String checkpointId) {
        // In a real application: sensitive operation requiring restriction.
    }

    // Public method for internal logic, NOT exported via JMX contract.
    public void rebuildInternalIndex() {
        // Not a JMX operation.
    }

    public void onCompleted() {
        completedCount.incrementAndGet();
    }

    public void onFailed() {
        failedCount.incrementAndGet();
    }
}
\`\`\`

In this example, pause/resume update state immediately for test simplicity. With a real worker, \`requestPause()\` often records only the requested state, while the effective state changes after the worker stops accepting new jobs. In that case, tests must verify the operation's true semantics: \`ACCEPTED\` does not mean \`PAUSED\` immediately.

Do not use \`public final class\` above and expect a Spring class-based AOP proxy to subclass it. Direct Standard MBean tests do not need proxies. If you later want AOP on the implementation, evaluate an adapter design and proxy strategy.

## 5. Create an Isolated MBeanServer for Testing

JMX provides:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server = MBeanServerFactory.newMBeanServer();
\`\`\`

\`newMBeanServer()\` creates an isolated test server without registering it in the factory-tracked server list the way \`createMBeanServer()\` does. This is the right way to avoid colliding with the platform MBeanServer used by other tests.

Registration:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.test:type=WorkerRuntime,name=Contract");

WorkerRuntime worker = new WorkerRuntime();
server.registerMBean(worker, name);
\`\`\`

Tests must clean up so registrations are not retained beyond the fixture scope. With a separate server per test, the risk of affecting other tests drops, yet you should still unregister explicitly to test lifecycle and keep good ownership habits.

## 6. Test 1 — Verify the ObjectName Is Registered

\`\`\`java
package com.example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;

class WorkerRuntimeMBeanContractTest {

    @Test
    void registersAsStandardMBean() throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerRuntime,name=Contract");

        server.registerMBean(new WorkerRuntime(), name);

        try {
            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        } finally {
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

\`isRegistered\` confirms the registry entry exists, while \`getMBeanInfo\` confirms the server has introspection metadata for the MBean. However, these two assertions do not yet prove which members are exposed, so the following tests are needed.

## 7. Test 2 — Verify Attributes via MBeanInfo

You can inspect metadata:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

MBeanInfo info = server.getMBeanInfo(name);

Map<String, MBeanAttributeInfo> attributes =
    java.util.Arrays.stream(info.getAttributes())
        .collect(Collectors.toMap(
            MBeanAttributeInfo::getName,
            Function.identity()
        ));

assertTrue(attributes.containsKey("State"));
assertTrue(attributes.containsKey("CompletedCount"));
assertTrue(attributes.containsKey("FailedCount"));

assertTrue(attributes.get("State").isReadable());
assertFalse(attributes.get("State").isWritable());

assertEquals(
    "long",
    attributes.get("CompletedCount").getType());
assertFalse(attributes.get("CompletedCount").isWritable());
\`\`\`

Checking read-only flags is crucial. A Java class might have a public setter for internal use; if the setter is not part of the management interface, it must not automatically make the JMX attribute writable under the corresponding Standard MBean contract.

### 7.1 Testing the exact set of attributes

If the contract does not allow extra attributes, use set equality:

\`\`\`java
Set<String> names = java.util.Arrays.stream(
    info.getAttributes())
    .map(MBeanAttributeInfo::getName)
    .collect(Collectors.toSet());

assertEquals(
    Set.of("State", "CompletedCount", "FailedCount"),
    names);
\`\`\`

Exact-set checking has the advantage of catching newly exposed unplanned attributes. In systems with metadata from custom assemblers or inherited interfaces, define the intended contract and update tests only when changes are intentional.

## 8. Test 3 — Verify Operations and Signatures

A JMX operation has a name, return type, and parameter signature. To verify:

\`\`\`java
import javax.management.MBeanOperationInfo;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

MBeanOperationInfo[] operations = info.getOperations();

Set<String> operationNames = Arrays.stream(operations)
    .map(MBeanOperationInfo::getName)
    .collect(Collectors.toSet());

assertEquals(
    Set.of("requestPause", "requestResume"),
    operationNames);

for (MBeanOperationInfo operation : operations) {
    assertEquals(0, operation.getSignature().length);
    assertEquals("void", operation.getReturnType());
}
\`\`\`

This is a strict test for a parameterless management contract. When an operation is overloaded, comparing names alone is not enough; two overloads can share a name with different signatures. A general test should key by \`(operationName, listOfParameterTypes, returnType)\`.

### 8.1 Helper to check a specific operation

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import java.util.Arrays;

static boolean hasOperation(
        MBeanInfo info,
        String operationName,
        String... signature) {

    return Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals(operationName))
        .anyMatch(op -> {
            MBeanParameterInfo[] parameters = op.getSignature();

            if (parameters.length != signature.length) {
                return false;
            }

            for (int i = 0; i < parameters.length; i++) {
                if (!parameters[i].getType().equals(signature[i])) {
                    return false;
                }
            }
            return true;
        });
}
\`\`\`

Example:

\`\`\`java
assertTrue(hasOperation(info, "requestPause"));
assertFalse(hasOperation(info, "deleteCheckpoint", "java.lang.String"));
\`\`\`

For primitives, the signature must use the primitive name such as \`"int"\` instead of \`"java.lang.Integer"\` if that is the declared type. Do not infer signatures from client-side wrapper objects.

## 9. Test 4 — Internal Public Methods Must Be Hidden

This is an important negative contract test:

\`\`\`java
Set<String> exposed = Arrays.stream(info.getOperations())
    .map(MBeanOperationInfo::getName)
    .collect(Collectors.toSet());

assertFalse(exposed.contains("deleteCheckpoint"));
assertFalse(exposed.contains("rebuildInternalIndex"));
assertFalse(exposed.contains("onCompleted"));
assertFalse(exposed.contains("onFailed"));
\`\`\`

These methods are public Java methods, yet do not belong to \`WorkerRuntimeMBean\`. The Standard MBean contract must hide them from JMX.

This test has security value: a refactor or exporter/assembler change could accidentally expose a side-effecting operation. A test that only checks \`requestPause\` still exists can miss an unintentionally expanded management surface.

**Do not confuse "hidden from JMX" with access control across all channels.** The \`deleteCheckpoint\` method can still be called by Java code holding a reference to the object; separate security boundaries are needed if there are REST endpoints, message handlers, or other control planes.

## 10. Test 5 — Read Actual Attributes

Valid metadata does not guarantee the implementation works properly. Query via \`MBeanServer\`:

\`\`\`java
import javax.management.MBeanServerConnection;

MBeanServerConnection connection = server;

Object state = connection.getAttribute(name, "State");
Object completed = connection.getAttribute(name, "CompletedCount");

assertEquals("RUNNING", state);
assertEquals(0L, completed);
\`\`\`

In Java, \`MBeanServer\` extends \`MBeanServerConnection\`, so a local server can be used as a connection. This brings the test suite closer to remote JMX client behavior without needing a network connector.

If \`getAttribute\` throws \`AttributeNotFoundException\`, inspect \`MBeanInfo\` rather than only checking for a \`getState()\` getter in the Java class. The JMX attribute name is typically \`"State"\`, not \`"getState"\`.

## 11. Test 6 — Invoke Operations via JMX at Runtime

\`\`\`java
connection.invoke(
    name,
    "requestPause",
    new Object[0],
    new String[0]
);

assertEquals(
    "PAUSED",
    connection.getAttribute(name, "State"));

connection.invoke(
    name,
    "requestResume",
    new Object[0],
    new String[0]
);

assertEquals(
    "RUNNING",
    connection.getAttribute(name, "State"));
\`\`\`

Calling \`worker.requestPause()\` directly only tests the Java implementation. Calling via \`connection.invoke()\` also tests JMX operation dispatch, ObjectName, and signature.

In real applications, operations may be asynchronous. In that case, test \`RequestedState\` and \`EffectiveState\` separately, using a latch or deadline-bounded polling instead of an immediate assertion. An accepted response does not mean the worker has completely stopped.

## 12. Test 7 — Read-Only Attributes Cannot Be Set

\`\`\`java
import javax.management.Attribute;
import javax.management.AttributeNotFoundException;

assertThrows(
    AttributeNotFoundException.class,
    () -> connection.setAttribute(
        name,
        new Attribute("CompletedCount", 100L)
    )
);
\`\`\`

For Standard MBean read-only attributes, set attempts are typically rejected with \`AttributeNotFoundException\` per the JMX API. With custom MBeans or other invocation paths, the exception may be wrapped depending on the implementation. First assert \`MBeanAttributeInfo.isWritable()==false\`, then test the behavior supported by the actual server.

Never create tests that mutate critical production state just to prove permissions. Use harmless test MBeans.

## 13. A Test Fixture with Centralized Setup and Cleanup

To avoid code duplication, use JUnit lifecycle hooks:

\`\`\`java
package com.example.jmx;

import static org.junit.jupiter.api.Assertions.*;

import javax.management.*;
import org.junit.jupiter.api.*;

class WorkerRuntimeContractTest {

    private MBeanServer server;
    private ObjectName objectName;

    @BeforeEach
    void setUp() throws Exception {
        server = MBeanServerFactory.newMBeanServer();
        objectName = new ObjectName(
            "com.example.test:type=WorkerRuntime,name=Contract");

        server.registerMBean(new WorkerRuntime(), objectName);
    }

    @AfterEach
    void tearDown() throws Exception {
        if (server != null &&
                server.isRegistered(objectName)) {
            server.unregisterMBean(objectName);
        }
    }

    @Test
    void exposesOnlyExpectedAttributes() throws Exception {
        MBeanInfo info = server.getMBeanInfo(objectName);

        Set<String> attributes =
            Arrays.stream(info.getAttributes())
                .map(MBeanAttributeInfo::getName)
                .collect(Collectors.toSet());

        assertEquals(
            Set.of("State", "CompletedCount", "FailedCount"),
            attributes);
    }

    @Test
    void hidesInternalOperations() throws Exception {
        MBeanInfo info = server.getMBeanInfo(objectName);

        Set<String> names =
            Arrays.stream(info.getOperations())
                .map(MBeanOperationInfo::getName)
                .collect(Collectors.toSet());

        assertFalse(names.contains("deleteCheckpoint"));
        assertFalse(names.contains("rebuildInternalIndex"));
        assertTrue(names.contains("requestPause"));
    }
}
\`\`\`

The example requires imports for \`Arrays\`, \`Set\`, and \`Collectors\` when added to a project. Creating a new server in each test allows reusing the same ObjectName without collisions across fixtures. Cleanup maintains good lifecycle habits even when the test server is not shared.

### 13.1 If registration fails in @BeforeEach

When \`server.registerMBean\` throws an exception before setup completes, \`@AfterEach\` must still tolerate the unregistered state. Check \`server != null\`, \`objectName != null\`, and \`isRegistered\` if needed; or use \`try/finally\` inside each tightly scoped test.

Never write wildcard-domain unregister cleanup such as \`com.example.test:*\` on a shared platform server, as it can delete another test's MBeans.

## 14. Write an Integration Test with Spring MBeanExporter

Direct Standard MBean tests do not prove Spring configuration is correct. You must also test the exporter.

Example Java configuration:

\`\`\`java
package com.example.jmx;

import java.util.Map;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class ManagementConfiguration {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer();
    }

    @Bean
    public WorkerRuntime workerRuntime() {
        return new WorkerRuntime();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MBeanServer testMBeanServer,
            WorkerRuntime workerRuntime) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setAutodetect(false);
        exporter.setBeans(Map.of(
            "com.example.test:type=WorkerRuntime,name=Spring",
            workerRuntime
        ));
        return exporter;
    }
}
\`\`\`

The Spring exporter owns registering this map when the context starts and unregistering the registrations it owns when the context closes. Do not simultaneously enable \`@EnableMBeanExport\` if another annotation exporter would scan and duplicate the same bean under the same ObjectName.

## 15. Test the Spring Context Lifecycle

\`\`\`java
package com.example.jmx;

import static org.junit.jupiter.api.Assertions.*;
import javax.management.*;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class SpringJmxExportTest {

    @Test
    void exporterRegistersAndUnregistersMBean() throws Exception {
        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                ManagementConfiguration.class);

        MBeanServer server = context.getBean(MBeanServer.class);
        ObjectName name = new ObjectName(
            "com.example.test:type=WorkerRuntime,name=Spring");

        try {
            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);
            assertNotNull(info);

            assertEquals(
                "RUNNING",
                server.getAttribute(name, "State"));
        } finally {
            context.close();
        }

        assertFalse(server.isRegistered(name));
    }
}
\`\`\`

What to verify:
1. The Spring context initializes successfully.
2. The exporter uses the right server and ObjectName.
3. \`MBeanInfo\` reflects the contract.
4. Attributes are readable.
5. When the context closes, the registration is removed.

To test independent lifecycles of multiple contexts sharing an MBeanServer, create a dedicated fixture proving that closing context A does not remove context B's MBeans. No remote JMX connector is needed in this test.

## 16. Testing Annotation-Driven Management Interfaces

If the project uses Spring annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.test:type=Worker,name=Annotated")
public class AnnotatedWorkerMonitor {

    @ManagedAttribute
    public String getState() {
        return "RUNNING";
    }

    @ManagedOperation
    public void requestPause() {
        // Demo.
    }

    public void deleteInternalCheckpoint() {
        // Not annotated; should not be exported via metadata assembler.
    }
}
\`\`\`

Use properly configured \`@EnableMBeanExport\` or \`AnnotationMBeanExporter\`, then test \`MBeanInfo\` for the defined ObjectName. With annotation-driven export, hiding a method lacking \`@ManagedOperation\` is the result of metadata selection, not a Standard MBean interface.

Have dedicated tests ensuring:
- \`State\` is readable.
- \`requestPause\` is present.
- \`deleteInternalCheckpoint\` is absent.
- No unexpected writable attributes exist.
- Context shutdown cleans up properly.

If the same bean is exported by another assembler, simply omitting the annotation does not guarantee the method stays hidden. Testing runtime metadata remains the final proof.

## 17. Negative Contract Test When Changing the Management Interface

Suppose a developer accidentally adds:

\`\`\`java
public interface WorkerRuntimeMBean {
    String getState();
    long getCompletedCount();
    long getFailedCount();
    void requestPause();
    void requestResume();
    void deleteCheckpoint(String id); // Dangerous change.
}
\`\`\`

A test that only asserts \`requestPause\` exists will still PASS. However, a set-equality test:

\`\`\`java
Set<String> operationNames =
    Arrays.stream(info.getOperations())
        .map(MBeanOperationInfo::getName)
        .collect(Collectors.toSet());

assertEquals(
    Set.of("requestPause", "requestResume"),
    operationNames);
\`\`\`

will FAIL and force a review of the management contract change. This is the main benefit of negative contract tests: **detecting unplanned expansion of the JMX surface**.

For projects with many MBeans, you can store versioned contract snapshots as test data, while avoiding auto-updating snapshots on test failure without reviewing whether a new operation has side effects.

## 18. Testing Operations with Parameters and Overloads

A more complex MBean may expose:

\`\`\`java
void setConcurrency(int size);
String describeWorker(String workerId);
\`\`\`

Test signatures:

\`\`\`java
assertTrue(
    hasOperation(info, "setConcurrency", "int"));

assertTrue(
    hasOperation(
        info, "describeWorker", "java.lang.String"));
\`\`\`

Invoke:

\`\`\`java
server.invoke(
    name,
    "setConcurrency",
    new Object[]{Integer.valueOf(4)},
    new String[]{"int"}
);
\`\`\`

The \`Object[]\` argument holds an \`Integer\` wrapper because Java cannot put primitives directly into an \`Object\` array. Yet the JMX signature must specify the declared parameter type \`"int"\`. If a method is overloaded, tests must verify each signature rather than just the operation name.

For MXBeans, data types may be mapped to Open Types; tests should read \`MBeanInfo\` rather than assuming every type matches Standard MBeans.

## 19. MBeanServerConnection and Remote Tests

Local tests use \`MBeanServer\`, which is itself an \`MBeanServerConnection\`. To test a remote client, start a \`JMXConnectorServer\` in the fixture, connect via \`JMXConnectorFactory\`, and assert the same contract over \`MBeanServerConnection\`.

A remote test additionally exercises:
- Valid service URLs.
- Registry/connector startup.
- Authentication/TLS when required by the environment.
- Port management and firewall/network tests.
- Connector cleanup.
- Serialization and error behavior.

Do not run a remote connector for every contract test; that slows down CI and adds flakiness. Keep local contract tests fast, and reserve remote integration tests for connectivity and security paths.

## 20. Testing AOP Proxies

If the MBean implementation is proxied by Spring AOP, introspection can change. A test should verify:

\`\`\`java
Object bean = context.getBean("workerRuntime");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

With JDK dynamic proxies, verify whether the management interface is exposed. With class-based proxies, check method/final-class constraints. Do not test only that the target class implements the interface and assume the proxied object exports properly.

A dedicated management adapter often keeps the JMX contract more stable when domain services have \`@Transactional\`, \`@Async\`, or tracing advice. If a control operation calls a service, verify the call goes through the Spring proxy so advice is not bypassed.

## 21. Distinguishing Contract Tests from Behavior Tests

| Test Type | Question Answered |
|---|---|
| Java unit test | Does the method implementation work properly? |
| JMX metadata contract test | Which attributes/operations are actually exported? |
| JMX invocation test | Can a client read/invoke using the right ObjectName and signature? |
| Spring integration test | Does the context/exporter register and unregister properly? |
| Proxy test | Does proxying alter the management contract? |
| Remote connector test | Do URL, auth, TLS, and transport work properly? |
| Security test | Are unauthorized clients blocked? |
| Load test | Are getters lightweight and stable under polling? |

No single test can replace all of these. A test using \`server.getAttribute()\` does not prove remote TLS works; a remote test that connects successfully does not prove internal methods are hidden.

## 22. Common Mistakes When Writing Tests

### 22.1 Testing only direct Java method calls

\`\`\`java
worker.requestPause();
assertEquals("PAUSED", worker.getState());
\`\`\`

This test never checks \`MBeanServer\`/\`ObjectName\`, so it misses an exporter omitting the operation or having a wrong signature.

### 22.2 Checking only that ObjectName exists

\`\`\`java
assertTrue(server.isRegistered(name));
\`\`\`

Not enough; you must also check \`MBeanInfo\`, attributes, and operations.

### 22.3 Using the platform MBeanServer with fixed ObjectNames

Tests can collide with other tests or running applications. Prefer isolated test servers or unique namespaces, and never unregister whole domains.

### 22.4 Asserting operation count without checking names

Two different sets of operations can have the same count. Use exact sets along with signatures.

### 22.5 Checking only required members

Dangerous newly exported operations can slip through. Add negative contract assertions.

### 22.6 Using Thread.sleep to wait for asynchronous behavior

If an operation only requests a state and the worker transitions afterward, arbitrary sleeps create flaky tests. Use \`CountDownLatch\`, \`Awaitility\`, or deadline-bounded polling.

### 22.7 Skipping cleanup when an assertion fails

Registering an MBean in a test without \`finally\` or \`@AfterEach\` can leave the registration behind and cause collisions in subsequent tests.

### 22.8 Updating expected values to match runtime without review

If a new operation appears, a failing test may be signaling a security contract review. Never blindly update expected sets just to make CI green.

## 23. Step-by-Step Testing Workflow

1. **Create a small management interface.** Select only the attributes/operations genuinely needed.
2. **Create the implementation.** Include extra public methods outside the interface to test hiding.
3. **Initialize an isolated MBeanServer.** Do not depend on the platform registry.
4. **Register the MBean under an ObjectName.**
5. **Inspect \`MBeanInfo\`.** Assert the member list and flags.
6. **Invoke attributes/operations via \`MBeanServerConnection\`.**
7. **Test negative contracts.** Ensure no unplanned internal methods or writable attributes appear.
8. **Unregister in \`finally\`.**
9. **Create a Spring context fixture** with an explicit \`MBeanExporter\`.
10. **Verify lifecycle** when the context closes.
11. **Extend tests** for annotations/proxies/remote connectors as needed.
12. **Run in CI** and review every contract change.

## 24. Extension Practice Exercises

### Exercise 1 — Read-only vs. writable

Add a Java \`setState(String)\` method to the implementation without adding it to the management interface. Write a test proving \`State\` remains read-only. Then intentionally add the setter to the interface and observe how the test fails.

### Exercise 2 — Confirm sensitive methods stay hidden

Add a public \`deleteAllData()\` method to the implementation. Omit it from the interface. Write an exact operation-set test and negative assertion to catch an assembler accidentally exposing it.

### Exercise 3 — Signature compatibility

Add \`setMaxWorkers(int)\` to the management interface and write a test asserting signature \`"int"\`. Then change the method to take \`long\` and observe the contract test catching the breaking change.

### Exercise 4 — Spring lifecycle

Create two ApplicationContexts sharing the same test MBeanServer, each exporting a different ObjectName. Close the first context and assert the second context's MBean remains registered.

### Exercise 5 — AOP and management adapter

A \`@Transactional\` service is Spring-proxied. Write a small management adapter, export the adapter as an MBean, and assert the operation calls through the service proxy. Avoid exporting the raw target and bypassing advice.

### Exercise 6 — Notification contract

Extend the MBean with a \`worker.paused\` notification. Write a listener test with \`CountDownLatch\`, asserting type, userData, sequence, and cleanup. Use a filter to block other notifications.

### Exercise 7 — Performance

Create one getter reading a cached counter and one getter calling a repository. Use mocks and latency/interaction tests to prove management getters do not directly trigger heavy I/O on every read.

## 25. Pre-CI Test Checklist

| Checklist Item | Ready? |
|---|---|
| Management interface clearly defines the contract | Required |
| \`MBeanInfo\` attribute names/types/flags asserted | Required |
| Operation names/signatures asserted | Required |
| Negative assertions for non-exported methods | Required |
| Invocation tested via \`MBeanServerConnection\` | Required |
| Isolated test server or unique ObjectNames | Required |
| Cleanup always runs when assertions fail | Required |
| Spring exporter lifecycle has integration tests | Recommended |
| Annotation/proxy behavior tested when used | Recommended |
| Remote connector/security has dedicated tests | System-dependent |
| No destructive operations called on real data | Mandatory |
| Tests do not rely on arbitrary timing | Required |
| No secrets written to logs/test output | Required |

## Summary

Writing tests to verify a management interface in Spring Framework JMX means testing the **actual management contract** on the \`MBeanServer\`, not merely checking Java methods or Spring bean existence. Start with a small Standard MBean interface, read \`MBeanInfo\` to verify attributes and operations, call \`getAttribute\`/\`invoke\` through a connection, and prove internal methods do not appear. Use isolated test servers and \`finally\` cleanup to avoid collisions; add Spring integration tests for exporter lifecycle. These negative contract tests serve as a vital guardrail against refactors, auto-proxying, assembler changes, and accidental expansion of the management surface.

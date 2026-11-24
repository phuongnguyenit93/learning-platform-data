# Testing Beans with JMX Metadata in ApplicationContext

## 1. Goal: Testing That JMX Configuration Actually Takes Effect

In Spring Framework, a bean can be annotated with `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` to build a JMX management interface. However, checking annotations in the source code alone does not prove that:

- The bean is registered in the `ApplicationContext`.
- The `MBeanExporter` or `AnnotationMBeanExporter` infrastructure is active.
- The MBean is registered under the right `ObjectName`.
- `MBeanInfo` reflects the expected attributes and operations.
- Getters/setters/operations actually execute through the JMX interface.
- Internal methods are not accidentally exported.
- Closing the context does not leave behind registrations that affect subsequent tests.

This lesson guides you through writing automated tests for **beans with JMX metadata in a Spring context**, focusing on the published management contract and actual runtime behavior. We will use a small `ApplicationContext`, an isolated MBeanServer, JUnit 5, and standard JMX APIs.

**Core mindset:** Testing that a bean exists in Spring and testing that an MBean exists in JMX are two different checks. Both must be verified if the goal is to confirm effective JMX configuration.

## 2. Layered Testing Model

```text
            JUnit test
                |
    create Spring ApplicationContext
                |
        +-------+-------+
        |               |
     Managed bean   MBeanExporter
        |               |
        +-------+-------+
                |
           MBeanServer
                |
          ObjectName lookup
                |
              MBeanInfo
                |
       +--------+--------+
       |                 |
  Attribute access   Operation invoke
       |                 |
       +--------+--------+
                |
          Assertions
```

A complete test suite can include these layers:

| Layer | What to verify | Suggested API |
|---|---|---|
| Spring context | Managed bean is present | `containsBean`, `getBean` |
| Export infrastructure | Exporter is initialized | `getBeansOfType(MBeanExporter.class)` |
| Registration | ObjectName exists | `MBeanServer.isRegistered` |
| Metadata | Attributes/operations match contract | `getMBeanInfo` |
| Attribute behavior | Getters/setters run through JMX | `getAttribute`, `setAttribute` |
| Operation behavior | Management methods work | `invoke` |
| Negative test | Internal methods are not exported | Inspect `MBeanInfo` lists |
| Lifecycle | No leftover MBeans after test | `context.close()`, `isRegistered` |

You do not need to test everything in a single large test method. You can split assertion groups while sharing a setup with a clear lifecycle.

## 3. Distinguishing Source Metadata from MBeanServer Metadata

Annotations represent **configuration intent**:

```java
@ManagedResource(objectName = "lab.test:type=JobMonitor")
public class JobMonitor {

    @ManagedAttribute
    public int getActiveJobs() {
        return 3;
    }

    @ManagedOperation
    public void reset() {
        // ...
    }
}
```

However, a JMX client does not access annotations directly. It sees metadata from `MBeanInfo` provided by the exporter and MBeanServer.

```text
Java annotation
      |
Spring metadata source / assembler
      |
MBeanExporter / ModelMBean
      |
MBeanServer
      |
MBeanInfo
      |
JMX client
```

You can read annotations via reflection in a unit test, but that does not replace an integration test through MBeanServer. Factors such as component scanning, bean profiles, ObjectName, assembler, proxies, and registration policy can all make the effective metadata differ from what you expect from the source code.

Conversely, testing MBeanServer does not mean testing all business logic. You only need to confirm that the management path actually works and that the exposed scope is accurate.

## 4. Preparing Dependencies

The example uses Maven with Spring Context and JUnit Jupiter. Versions are managed by the project's BOM or dependency management.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

If the project does not use a parent/BOM to manage versions, declare compatible versions explicitly. Spring Framework 6+ uses Jakarta annotations when `@PostConstruct` is needed, though this lesson does not depend on `@PostConstruct`.

For Spring Boot projects, `spring-boot-starter-test` can provide JUnit Jupiter and Spring testing utilities. You do not need to start an entire web server just to verify JMX metadata; a small `AnnotationConfigApplicationContext` is usually simpler and faster.

There is no need to enable remote JMX or launch JConsole in automated tests. Checking against a local MBeanServer is sufficient to verify registration, metadata, and JMX behavior.

## 5. Building the Managed Bean for Testing

Create `JobMonitor.java`:

```java
package example.jmx;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "lab.test:type=JobMonitor,name=primary",
    description = "Job management test fixture"
)
public class JobMonitor {

    private final AtomicLong completed = new AtomicLong();
    private final AtomicInteger active = new AtomicInteger();
    private volatile int warningThreshold = 10;

    @ManagedAttribute(description = "Completed jobs")
    public long getCompletedJobs() {
        return completed.get();
    }

    @ManagedAttribute(description = "Active jobs")
    public int getActiveJobs() {
        return active.get();
    }

    @ManagedAttribute(description = "Warning threshold")
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @ManagedAttribute(description = "Change warning threshold")
    public void setWarningThreshold(int value) {
        if (value < 1 || value > 100) {
            throw new IllegalArgumentException(
                "warningThreshold must be between 1 and 100"
            );
        }
        warningThreshold = value;
    }

    @ManagedOperation(description = "Reset counters")
    public void resetCounters() {
        completed.set(0);
        active.set(0);
    }

    // Internal, not a JMX operation.
    public void recordCompletedJob() {
        completed.incrementAndGet();
    }

    public void startJob() {
        active.incrementAndGet();
    }
}
```

Management methods are selected using annotations. `recordCompletedJob()` and `startJob()` are not annotated; when using an appropriate annotation metadata assembler, they should not appear among JMX operations.

A class does not need `@Component` if the test creates it with `@Bean`. This keeps the fixture configuration explicit and avoids scanning extra beans outside the test scope.

## 6. Creating a Dedicated MBeanServer for Tests

The platform MBeanServer is a shared JVM resource:

```java
ManagementFactory.getPlatformMBeanServer();
```

If multiple tests use the same ObjectName on the platform server, they can collide even though each test creates a new ApplicationContext. For metadata tests, use an **isolated MBeanServer**:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("jmx-test");
```

After the test, close the Spring context so the exporter unregisters the MBeans it owns, and release the test server when it is no longer needed:

```java
MBeanServerFactory.releaseMBeanServer(server);
```

Imports:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
```

If some other tests require platform MXBeans, use a separate test JVM or unique ObjectNames with reliable cleanup. Never automatically delete pre-existing MBeans on the platform server belonging to libraries or the JDK.

**A dedicated MBeanServer is not a fake mock:** it still conforms to the JMX API, with real registration, metadata, and invocations. It simply isolates the registry from other MBeans in the same JVM.

## 7. Configuring the Test ApplicationContext

Create `JmxTestConfiguration.java`:

```java
package example.jmx;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.annotation.AnnotationMBeanExporter;

@Configuration
public class JmxTestConfiguration {

    @Bean
    public JobMonitor jobMonitor() {
        return new JobMonitor();
    }

    @Bean
    public AnnotationMBeanExporter annotationMBeanExporter(
            MBeanServer mbeanServer) {

        AnnotationMBeanExporter exporter =
            new AnnotationMBeanExporter();

        exporter.setServer(mbeanServer);
        return exporter;
    }
}
```

The test supplies the privately created `MBeanServer` to the context before `refresh()`, for example via `registerBean`. When the context refreshes, the exporter detects the `@ManagedResource` metadata and registers the corresponding MBean.

Because `AnnotationMBeanExporter` is explicitly declared here, do not also enable `@EnableMBeanExport` in the test fixture if it would create a second exporter that collides on the ObjectName. Similarly, do not mix in full Spring Boot auto-configuration in a narrow test without a specific reason.

Another way to organize this is to create an `MBeanExporter` with an explicitly configured `MetadataMBeanInfoAssembler`. The goal remains to exercise the exact metadata mechanism used by the application, not just instantiate plain beans.

## 8. Setting Up the Lifecycle in JUnit 5

Example test class:

```java
package example.jmx;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JobMonitorJmxTest {

    private static final String JMX_NAME =
        "lab.test:type=JobMonitor,name=primary";

    private MBeanServer server;
    private AnnotationConfigApplicationContext context;
    private ObjectName objectName;

    @BeforeEach
    void startContext() throws Exception {
        server = MBeanServerFactory.createMBeanServer("jmx-test");
        objectName = new ObjectName(JMX_NAME);

        context = new AnnotationConfigApplicationContext();

        // Register singleton server so @Bean exporter injects correctly.
        context.getBeanFactory().registerSingleton(
            "testMBeanServer", server
        );
        context.register(JmxTestConfiguration.class);
        context.refresh();
    }

    @AfterEach
    void stopContext() {
        try {
            if (context != null) {
                context.close();
            }
        } finally {
            if (server != null) {
                MBeanServerFactory.releaseMBeanServer(server);
            }
        }
    }
}
```

Each test method receives a fresh context and MBeanServer. Closing the context happens before releasing the server so the exporter has a chance to unregister the MBeans it manages.

If startup throws an exception inside `@BeforeEach`, JUnit still invokes `@AfterEach` per its normal lifecycle, so design cleanup to tolerate an incompletely initialized context. For complex test setups, you can wrap initialization in `try/finally` inside a helper to handle mid-setup failures more reliably.

## 9. Test 1: Bean Exists in ApplicationContext

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

@Test
void springContextContainsManagedBean() {
    assertTrue(context.containsBean("jobMonitor"));

    JobMonitor bean = context.getBean(JobMonitor.class);
    assertNotNull(bean);
}
```

This test verifies that the Spring configuration created the bean. It **does not prove** the MBean is registered. An application can have `JobMonitor` in the context while the exporter is missing or misconfigured.

If the test cannot find the bean, check `@Bean`, component scanning, profile/conditional configuration, and imports. Do not rush to change the JMX ObjectName because the issue may lie entirely in Spring bean registration.

## 10. Test 2: Exporter Is Present in Context

```java
import org.springframework.jmx.export.MBeanExporter;

@Test
void contextContainsMBeanExporter() {
    var exporters =
        context.getBeansOfType(MBeanExporter.class);

    assertFalse(exporters.isEmpty());
}
```

Because `AnnotationMBeanExporter` extends `MBeanExporter`, this type lookup finds the active annotation exporter.

If a test requires **exactly one exporter**, you can assert that the count equals one. However, understand the test scope: in a real application there may be multiple valid exporters for different MBean groups. Do not turn a simple fixture assumption into an absolute rule for every application.

Integration tests on production-like configurations may also need to inventory exporters in parent/child ApplicationContexts or auto-configuration. Calling `getBeansOfType` on one context does not automatically discover exporters in other independent contexts within the JVM.

## 11. Test 3: MBean Registered with Expected ObjectName

```java
@Test
void mbeanIsRegistered() {
    assertTrue(server.isRegistered(objectName));
}
```

This is the bridge between Spring and JMX. It verifies that the ObjectName exists in the **MBeanServer used by the test**.

However, an existing registration alone does not prove all attributes and operations are right. When multiple exporters share an MBeanServer, another MBean could occupy the name; isolating tests with a dedicated server reduces this risk.

You can check further:

```java
Set<ObjectName> names = server.queryNames(
    new ObjectName("lab.test:*"), null
);
assertTrue(names.contains(objectName));
```

The collection returned by `queryNames` has no guaranteed order. If you need to compare counts or sets of names, use a `Set`.

## 12. Test 4: Attribute Metadata Has Correct Read/Write Permissions

Inspect `MBeanInfo`:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

@Test
void expectedAttributesAreExposed() throws Exception {
    MBeanInfo info = server.getMBeanInfo(objectName);

    Map<String, MBeanAttributeInfo> attributes =
        java.util.Arrays.stream(info.getAttributes())
            .collect(java.util.stream.Collectors.toMap(
                MBeanAttributeInfo::getName,
                attribute -> attribute
            ));

    MBeanAttributeInfo completed = attributes.get("CompletedJobs");
    assertNotNull(completed);
    assertTrue(completed.isReadable());
    assertFalse(completed.isWritable());

    MBeanAttributeInfo warning = attributes.get("WarningThreshold");
    assertNotNull(warning);
    assertTrue(warning.isReadable());
    assertTrue(warning.isWritable());

    assertEquals("int", warning.getType());
}
```

This test checks the contract visible to a JMX client:

- `CompletedJobs`: read-only because no setter is exported.
- `WarningThreshold`: read-write because both matching getter and setter exist.
- The type of `WarningThreshold` is the primitive `int` in this contract's metadata.

If `getWarningThreshold()` is annotated but `setWarningThreshold(...)` is not exported under the configuration, the attribute may not be writable as expected. That is why actual metadata must be verified.

Do not infer writability from a single `server.getAttribute(...)` call; inspect `MBeanAttributeInfo.isWritable()`.

## 13. Test 5: Management Operation Is Exposed

```java
import javax.management.MBeanOperationInfo;

@Test
void resetOperationIsExposed() throws Exception {
    MBeanInfo info = server.getMBeanInfo(objectName);

    boolean found =
        java.util.Arrays.stream(info.getOperations())
            .map(MBeanOperationInfo::getName)
            .anyMatch("resetCounters"::equals);

    assertTrue(found);
}
```

An exported operation does not mean it should be invoked in production. In an isolated test fixture, `resetCounters()` is a side-effecting action that is safely controlled.

When a method takes parameters, `MBeanOperationInfo.getSignature()` provides the parameter types. Verify the signature as well, not just the name, if overloaded methods exist. If the target uses ModelMBean or MXBean mapping, the contract may differ; write assertions against the expected metadata of the export mechanism in use.

## 14. Test 6: Internal Methods Are Not Exported

An important security goal is proving that methods outside the management contract cannot be called via JMX:

```java
@Test
void internalMethodsAreNotJmxOperations() throws Exception {
    MBeanInfo info = server.getMBeanInfo(objectName);

    Set<String> operations =
        java.util.Arrays.stream(info.getOperations())
            .map(MBeanOperationInfo::getName)
            .collect(java.util.stream.Collectors.toSet());

    assertFalse(operations.contains("recordCompletedJob"));
    assertFalse(operations.contains("startJob"));
}
```

This is a **negative contract** check. When a developer adds a public method to the implementation, it should not automatically become a JMX operation just because an exporter uses an overly broad reflective assembler.

In environments requiring strict control, you can assert the entire set of allowed operations, not just a few forbidden methods. For example, only `resetCounters` is exposed in this fixture. However, keep in mind that `MBeanInfo` may present accessors according to the assembler's conventions; assertions should reflect the actual contract of the Spring version in use.

## 15. Test 7: Reading an Attribute Through JMX

After confirming metadata, perform an actual invocation:

```java
@Test
void canReadAttributeThroughJmx() throws Exception {
    JobMonitor target = context.getBean(JobMonitor.class);

    target.recordCompletedJob();
    target.recordCompletedJob();

    Object count = server.getAttribute(
        objectName, "CompletedJobs"
    );

    assertEquals(2L, count);
}
```

This test differs from `target.getCompletedJobs()`: it goes through `MBeanServer` and the ObjectName, proving the JMX access path works.

Avoid reading every attribute automatically from a list in production environments. Getters can have side effects, perform network calls, or return sensitive data. In the test fixture, we pick a simple, safe counter attribute.

## 16. Test 8: Writing Valid and Invalid Attribute Values

```java
import javax.management.Attribute;

@Test
void writableAttributeDelegatesToBean() throws Exception {
    server.setAttribute(
        objectName,
        new Attribute("WarningThreshold", 20)
    );

    JobMonitor target = context.getBean(JobMonitor.class);

    assertEquals(20, target.getWarningThreshold());
    assertEquals(
        20,
        server.getAttribute(objectName, "WarningThreshold")
    );
}
```

The setter must be exported and the metadata must be writable.

Testing validation:

```java
@Test
void invalidThresholdIsRejected() {
    assertThrows(Exception.class, () ->
        server.setAttribute(
            objectName,
            new Attribute("WarningThreshold", -1)
        )
    );
}
```

The example uses `Exception.class` to illustrate that JMX may wrap exceptions thrown by a setter inside another exception. When precise testing is needed, inspect the actual exception type produced by the Spring/JMX version used in the project, its `cause`, and relevant message; avoid asserting an unverified wrapper type.

Importantly, rejecting invalid input in a setter should not alter the existing configuration value. You can assert that `WarningThreshold` remains unchanged after the invalid input test.

## 17. Test 9: Invoking an Operation via MBeanServer

```java
@Test
void operationIsInvokable() throws Exception {
    JobMonitor target = context.getBean(JobMonitor.class);
    target.recordCompletedJob();

    Object result = server.invoke(
        objectName,
        "resetCounters",
        new Object[0],
        new String[0]
    );

    assertEquals(0L, target.getCompletedJobs());
}
```

Since `resetCounters()` returns `void`, the `invoke` result can be `null`; what matters is that the side effect occurred.

If an operation takes parameters:

```java
server.invoke(
    objectName,
    "setMode",
    new Object[]{"PAUSED"},
    new String[]{String.class.getName()}
);
```

then `setMode` must be exported as an operation with a matching signature. Do not treat every Java setter as an arbitrarily invokable operation; property setters are normally accessed via `setAttribute`.

In production, never invoke dangerous operations just to test JMX configuration. Use a test environment with dummy data.

## 18. Lifecycle Test: Context Close and Unregistration

After the `ApplicationContext` closes, the exporter is responsible for removing the MBeans it manages. A lifecycle test can create the context inside `try/finally`:

```java
MBeanServer server =
    MBeanServerFactory.createMBeanServer("lifecycle-test");

AnnotationConfigApplicationContext context =
    createJmxContext(server);

ObjectName name = new ObjectName(
    "lab.test:type=JobMonitor,name=primary"
);

try {
    assertTrue(server.isRegistered(name));
} finally {
    context.close();
}

assertFalse(server.isRegistered(name));

MBeanServerFactory.releaseMBeanServer(server);
```

`createJmxContext(server)` here is a helper that creates the context and configures the exporter just like the setup at the beginning of the lesson; define it in your test project. One implementation can use `registerSingleton`, then `context.register(JmxTestConfiguration.class)`, and `context.refresh()`.

Remember to only inspect MBeans created by the exporter under test. Never unregister all platform MBeans or other MBeans that the test does not own.

With `IGNORE_EXISTING` or `REPLACE_EXISTING` registration policies, ownership and cleanup may have edge cases requiring dedicated tests. It is best to use an isolated server and non-colliding ObjectNames to verify the basic lifecycle first.

## 19. Unit Testing Source Metadata vs. Runtime Integration Testing

There are two complementary testing levels:

### 19.1. Unit Testing Annotations via Reflection

```java
ManagedResource annotation =
    JobMonitor.class.getAnnotation(ManagedResource.class);

assertNotNull(annotation);
assertEquals(
    "lab.test:type=JobMonitor,name=primary",
    annotation.objectName()
);
```

For a getter:

```java
Method getter = JobMonitor.class.getMethod("getCompletedJobs");
assertNotNull(getter.getAnnotation(ManagedAttribute.class));
```

These tests are fast and inspect only source metadata without needing a Spring context. They are suitable when you want to guard against accidental removal of a specific annotation.

### 19.2. Integration Testing with MBeanServer

Check `MBeanInfo`, registration, and JMX calls as shown earlier. This layer catches issues such as:

- Exporter missing from the context.
- Bean not scanned or imported.
- Wrong or colliding ObjectName.
- Assembler selecting incorrect metadata.
- A proxy altering the exported bean.
- Registration policy skipping the new MBean.
- MBeanServer configured differently from expectations.

When the goal is **testing beans with JMX metadata in a context**, integration tests are decisive because they verify the contract actually published at runtime.

## 20. Separating Test Config from Production Config

Avoid loading the full production configuration for a simple metadata test if it:

- Connects to a database, broker, or remote service.
- Starts background schedulers or workers.
- Launches an HTTP server or remote JMX connector.
- Exports dozens of MBeans outside the test scope.
- Shares the platform MBeanServer across parallel tests.

Instead, build a small context with the fixture and exporter needed to reproduce the export mechanism. If you need to verify Spring Boot auto-configuration, write a separate **application-level integration test**, for example using a Spring Boot test context and verifying the exporter in a test environment with appropriate properties.

The two test types serve different purposes:

| Test type | Goal |
|---|---|
| Small, self-configured context | Verify MBean/metadata contract |
| Boot integration test | Verify JMX auto-configuration and application exposure |
| Remote JMX integration test | Verify connector, authentication, TLS, network topology |
| Manual JConsole test | Visual inspection and diagnostic support |

Do not turn every metadata test into a remote JMX test. Most `MBeanInfo` checks can run completely locally and deterministically when the server is properly isolated.

## 21. Common Issues When Running Tests in Parallel

Two tests creating separate contexts that both use:

```text
lab.test:type=JobMonitor,name=primary
```

on the platform server can cause `InstanceAlreadyExistsException`. Test outcomes will depend on execution order.

Mitigations:

1. Create a dedicated MBeanServer for each test or test suite.
2. Use distinct ObjectNames if a server must be shared.
3. Close the context in `@AfterEach`.
4. Unregister only MBeans owned by the test.
5. Do not use `REPLACE_EXISTING` to mask collisions caused by broken test isolation.
6. Isolate tests that require the platform server into a separate JVM fork if needed.

Tests using `@SpringBootTest` may also cache contexts across test classes. If a test mutates MBean state, reset the fixture and understand context caching lifecycles; do not assume every test method gets a brand-new context when using the Spring TestContext Framework.

## 22. Pitfalls to Avoid

### 22.1. Asserting Only That the Annotation Exists

`@ManagedResource` may be present without an active exporter. Always assert against the actual registry.

### 22.2. Asserting Only That the Bean Exists in Context

A Spring bean is not equivalent to a JMX MBean. Use `MBeanServer.isRegistered`.

### 22.3. Testing on the Shared Platform Server Without Cleanup

This easily causes flaky tests or reading MBeans left by an earlier test. Use an isolated server.

### 22.4. Matching ObjectName Without Inspecting MBeanInfo

Another exporter might occupy the same name. Verify the attributes and operations actually exposed.

### 22.5. Testing Only the Positive Contract

If a sensitive getter is accidentally exported, positive tests still pass. Also verify methods that **must not be exposed**.

### 22.6. Invoking Every Operation to Verify It

Operations may mutate data, clear caches, or restart workers. Only invoke safe operations in a test fixture.

### 22.7. Calling setAttribute on a Read-Only Property

This will be rejected per the JMX contract. Test read/write permissions using `MBeanAttributeInfo`, not by guessing from implementation method names.

### 22.8. Ignoring Exception Wrappers

JMX and Spring ModelMBean may translate or wrap exceptions. Test rejection behavior and unchanged state rather than guessing a specific wrapper exception class.

### 22.9. Confusing Spring JMX Metadata with Actuator

`@ManagedResource` belongs to annotation-based Spring JMX; `@Endpoint` and `@ReadOperation` belong to the Spring Boot Actuator endpoint model. The two export mechanisms are distinct, so test setup must match the endpoint model in use.

## 23. Technical Checklist Template for Tests

A concise checklist:

- [ ] Test uses an appropriately scoped context and MBeanServer.
- [ ] Managed bean exists in the context.
- [ ] Exporter is properly configured.
- [ ] MBean is registered under the expected ObjectName.
- [ ] MBeanInfo contains attributes with matching types/permissions.
- [ ] MBeanInfo contains operations with matching signatures.
- [ ] Internal methods outside the contract are not exported.
- [ ] Getters and setters work through JMX.
- [ ] Safe operations produce the expected side effects.
- [ ] Invalid input is rejected without corrupting state.
- [ ] Test cleans up both context and MBeanServer.
- [ ] No remote connector is invoked and no sensitive data is leaked.

This checklist applies to designing your project's test suite, not as an automated acceptance status of this article.

## 24. Practice Exercises

**Exercise 1 — Testing registration.** Create a `@ManagedResource` bean with two managed getters, use `AnnotationMBeanExporter` and a dedicated test MBeanServer. Assert that the ObjectName exists.

**Exercise 2 — Testing read/write metadata.** Create `getLimit()`, `setLimit(int)`, and `getCount()`. Verify that `Limit` is read-write and `Count` is read-only.

**Exercise 3 — Testing negative contract.** Add an unannotated `getInternalToken()` and assert it is not a JMX attribute. Add an unannotated `deleteAllData()` and assert it is not an operation.

**Exercise 4 — Testing operations.** Add an annotated `resetCounters()` method; invoke it via `MBeanServer.invoke` in a test environment and verify the counters.

**Exercise 5 — Testing collisions.** Create two exporters using the same ObjectName on a test server. Observe `FAIL_ON_EXISTING` in a dedicated test; do not use `REPLACE_EXISTING` to hide errors.

**Exercise 6 — Testing shutdown.** Close the context after registering the MBean and confirm the ObjectName is unregistered before releasing the MBeanServer.

**Exercise 7 — Spring Boot integration.** In a Boot test, enable `spring.jmx.enabled` for your Boot version, inspect a custom MBean, and distinguish it from Actuator endpoint JMX exports.

**Exercise 8 — Testing interface-based export.** Replace the annotation assembler with `InterfaceBasedMBeanInfoAssembler`, create an allowlist management interface, and assert that `MBeanInfo` does not expand when the implementation adds a new method.

## 25. Self-Check Questions

1. Why is reading annotations via reflection not enough to prove an MBean is exported?
2. What two different concerns do `ApplicationContext` and `MBeanServer` address?
3. How can `MBeanInfo` confirm read-only versus read-write attributes?
4. Why should you also check which methods are not exported?
5. Why are tests using the shared platform MBeanServer prone to collisions?
6. What responsibility does `AnnotationMBeanExporter` have in this test setup?
7. When `setAttribute` fails, why might the exception be wrapped?
8. How does `getAttribute` differ from calling the getter directly on the Spring bean?
9. What problems do context cleanup and releasing the MBeanServer prevent?
10. When do you need a Spring Boot integration test instead of a small context test?
11. If the ObjectName matches but the metadata differs from expectations, which layers do you inspect?
12. Why should you avoid enabling remote JMX in every metadata test?

## 26. Key Takeaway

**Testing JMX metadata in Spring must verify the contract at the MBeanServer, not merely annotations in source code or bean presence in the context.** Create a small context, an isolated MBeanServer, and the appropriate exporter, then assert the ObjectName, MBeanInfo, attributes, operations, and absence of non-contract methods. Finally, verify real JMX calls and lifecycle cleanup.

This test design catches missing exporter configuration, wrong naming, over-exported methods, incorrect read/write permissions, and registration bugs across multiple contexts. It also enforces a practical security boundary: only approved management capabilities appear on the application's JMX surface.

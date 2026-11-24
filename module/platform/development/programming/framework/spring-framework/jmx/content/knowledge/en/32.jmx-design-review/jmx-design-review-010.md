# Self-Assessment Using Evidence from MBeanInfo, Tools, and Tests in Spring Framework JMX

## 1. Lesson Objectives

In the **Design Review** group of Spring Framework JMX, an application starting up cleanly is not enough to prove JMX was designed properly. Likewise, seeing an MBean name in JConsole does not prove every attribute and operation is accurate, points to the right Spring bean, or is safe to operate.

This lesson guides a self-assessment method using three complementary forms of evidence:

- **MBeanInfo:** the JMX contract actually published in the `MBeanServer`.
- **Tool:** the ability to inspect and interact with the MBean in a running JVM.
- **Test:** automated verifications for registration, metadata, behavior, errors, and lifecycle.

Upon completion, learners can identify verification requirements, gather appropriate evidence, read JMX metadata structures, write integration tests, and present traceable conclusions. Assessments must clearly distinguish what has been verified, what remains unverified, and any remaining risks.

## 2. Requirements-and-Evidence Evaluation Framework

Every conclusion should follow a transparent chain:

~~~text
Design requirement
       |
       v
Expected evidence
       |
       v
Actual observation or assertion
       |
       v
Comparison against requirement
       |
       v
Conclusion and next actions
~~~

For example, the requirement "the MBean exposes only `QueueDepth` for reading" needs evidence from `MBeanAttributeInfo` for name, type, readable/writable flags, plus a `getAttribute` read in a test. Simply looking at `getQueueDepth()` in source code does not prove the exporter configuration registered the right MBean.

Similarly, the requirement "the `resetStatistics` operation is invocable" needs metadata checks on its signature and an `invoke` on a safe fixture. `MBeanInfo` listing the operation does not prove execution will not throw errors, hang, or corrupt business state.

Useful assessment statuses:

| Status | Interpretation |
| --- | --- |
| `VERIFIED` | Sufficient evidence shows the requirement is satisfied |
| `PARTIALLY_VERIFIED` | Only part of the path or scenarios has been proven |
| `NOT_VERIFIED` | Not enough checks yet to draw a conclusion |
| `FAILED` | Concrete evidence shows the requirement is not met |
| `NOT_APPLICABLE` | The requirement does not apply to this target |

Never turn "no evidence yet" into "passed" or "failed" without running a check.

## 3. Layers in the Spring JMX Pipeline

~~~text
Spring ApplicationContext
        |
        +-- Spring bean / AOP proxy
        |
        +-- MBeanExporter
                |
                +-- naming strategy
                +-- MBeanInfoAssembler
                +-- registration policy
                |
                v
            MBeanServer
                |
                +-- ObjectName -> registered MBean
                |
                +-- local JMX API
                |
                +-- JMXConnectorServer
                           |
                           v
                    JMX remote client
~~~

Layer-by-layer checks:

| Layer | Question | Evidence |
| --- | --- | --- |
| Spring bean | Which bean is being managed? | `ApplicationContext` and bean state |
| Exporter | Which beans are exported and which names chosen? | Configuration and registration logs |
| `MBeanServer` | Does the registry contain the right `ObjectName`? | `isRegistered`, `queryNames` |
| Metadata | What management API is actually published? | `MBeanInfo` |
| Local behavior | Do attributes and operations work? | `getAttribute`, `setAttribute`, `invoke` |
| Runtime tool | Can operators find the right JVM/MBean? | JConsole or equivalent tool |
| Remote connector | Can clients reach the right MBean remotely? | `JMXConnector` integration test |
| Lifecycle | Is the MBean unregistered cleanly when context closes? | Context close test and registry re-check |
| Security | Are the API surface and access permissions sound? | Metadata, authorization tests, and connection policy |

A failure at an upper layer does not automatically mean a lower layer is broken. For instance, succeeding via local `MBeanServer` while the remote connector fails usually points to network, credentials, or the advertised RMI endpoint rather than needing assembler changes.

## 4. Sample Standard MBean for Practice

Create a small MBean with clear properties.

**QueueMonitorMBean.java**

~~~java
package com.example.jmx;

public interface QueueMonitorMBean {
    int getQueueDepth();
    boolean isPollingEnabled();
    void setPollingEnabled(boolean enabled);
    void resetStatistics();
}
~~~

**QueueMonitor.java**

~~~java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger queueDepth = new AtomicInteger();
    private final AtomicInteger resetCount = new AtomicInteger();
    private volatile boolean pollingEnabled = true;

    public void enqueue() {
        queueDepth.incrementAndGet();
    }

    public int getResetCountForTest() {
        return resetCount.get();
    }

    @Override
    public int getQueueDepth() {
        return queueDepth.get();
    }

    @Override
    public boolean isPollingEnabled() {
        return pollingEnabled;
    }

    @Override
    public void setPollingEnabled(boolean enabled) {
        pollingEnabled = enabled;
    }

    @Override
    public void resetStatistics() {
        resetCount.incrementAndGet();
    }
}
~~~

Because `QueueMonitor` implements `QueueMonitorMBean`, it is a valid Standard MBean per JMX conventions. Methods present only on the implementation such as `enqueue()` and `getResetCountForTest()` are not automatically exposed via the management interface; they serve application logic and testing.

Expected contract:

| Name | Kind | Type | Access |
| --- | --- | --- | --- |
| `QueueDepth` | Attribute | `int` | Read |
| `PollingEnabled` | Attribute | `boolean` | Read/Write |
| `resetStatistics` | Operation | `void`, zero parameters | Invoke |

`getResetCountForTest` exists only to verify the operation actually produces an observable side effect; it should not be exposed if the management contract does not require it.

## 5. Spring JMX Configuration

~~~java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class QueueJmxConfiguration {

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter queueExporter(
            QueueMonitor queueMonitor,
            MBeanServer platformMBeanServer) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(Map.of(
                "com.example.orders:type=QueueMonitor,name=primary",
                queueMonitor));
        return exporter;
    }
}
~~~

From the configuration snippet, we can conclude the exporter **is intended** to register the bean under a specific name, which is not yet enough to prove registration succeeded. We must inspect the runtime registry.

If the project uses Spring Boot auto-configuration or a second exporter, `ObjectName` collisions can occur. If the exporter uses a custom `MBeanServer`, checking the platform server will not reflect that registry.

## 6. Reading MBeanInfo from the Right Server

The JMX API provides `MBeanInfo` containing the final metadata of the registered MBean.

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
            "Expected MBean is missing: " + name);
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("className=" + info.getClassName());
System.out.println("description=" + info.getDescription());

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "attribute=%s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable());
}

for (var operation : info.getOperations()) {
    System.out.printf(
        "operation=%s returnType=%s impact=%s%n",
        operation.getName(),
        operation.getReturnType(),
        operation.getImpact());

    for (var parameter : operation.getSignature()) {
        System.out.printf(
            "parameter=%s type=%s%n",
            parameter.getName(),
            parameter.getType());
    }
}

for (var notification : info.getNotifications()) {
    System.out.println(
        java.util.Arrays.toString(notification.getNotifTypes()));
}
~~~

`MBeanInfo` is evidence of the JMX API published **on the current server**. It does not guarantee every invocation will succeed, nor does it prove remote access is secured.

If `className` shows an adapter or `ModelMBean` instead of the implementation class, this may come from a Spring `MBeanInfoAssembler`. Evaluations should rely on the expected contract and MBean type in use, rather than drawing conclusions from `className` alone.

## 7. Evaluating Attributes via MBeanAttributeInfo

For each attribute, inspect name, type, read flag, write flag, and getter/setter semantics.

Expected example:

~~~text
QueueDepth: int, readable=true, writable=false
PollingEnabled: boolean, readable=true, writable=true
~~~

Some risks:
- `QueueDepth` accidentally becomes `String`, breaking older clients.
- `PollingEnabled` becomes read-only, preventing operators from tuning it.
- A setter that should stay internal gets exposed via JMX.
- The bean pointed to by the exporter is not the live business instance being updated.
- An attribute keeps the same name while its type or meaning changes.

A getter existing on a Java class does not guarantee JMX exports it. Standard MBeans depend on interfaces; Spring `ModelMBean`s can depend on assemblers and annotation metadata.

If an attribute's value updates asynchronously, read state at appropriate times and account for changes between reads. `MBeanInfo` provides no atomic snapshot guarantee.

## 8. Evaluating Operations via MBeanOperationInfo

An operation consists of:
- Method name.
- Return type.
- Parameter signature and order.
- Impact metadata.
- Description/descriptor depending on MBean type.

Client example:

~~~java
server.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);
~~~

For parameterized operations, the signature in JMX `invoke` must match the actual method types. A method accepting primitive `int` usually has signature `"int"`, whereas `Integer` has `"java.lang.Integer"`. Always check `MBeanOperationInfo` instead of guessing.

Impact `INFO`, `ACTION`, or `ACTION_INFO` is descriptive metadata, not an access-control system. An operation marked `INFO` that deletes data is still dangerous. Inspect the implementation and write safe functional tests.

## 9. Evaluating Notifications

When an MBean emits notifications, inspect `MBeanNotificationInfo`:

~~~java
for (var notification : info.getNotifications()) {
    for (String type : notification.getNotifTypes()) {
        System.out.println("notificationType=" + type);
    }
}
~~~

What metadata proves:
- Which notification types the MBean declares it supports.
- Published notification descriptions.

What metadata does NOT prove:
- Whether events are actually emitted when conditions occur.
- Whether listeners receive callbacks.
- Whether payload, sequence number, and source are accurate.
- Whether listeners are removed when context/clients close.
- Whether remote reconnects re-register listeners properly.

When testing notifications, use a fixture with an explicit broadcaster and listener, a `CountDownLatch` with a bounded timeout, and teardown in `finally`. Never use `Thread.sleep` as sole evidence.

## 10. Runtime Observation Using JConsole

Procedure:

1. Start the application and identify the PID/JVM instance.
2. Launch JConsole from a supported JDK.
3. Connect to the intended local JVM or test environment remote endpoint.
4. Open the MBeans tab and locate domain `com.example.orders`.
5. Select `ObjectName` `type=QueueMonitor,name=primary`.
6. Inspect `QueueDepth` and `PollingEnabled`.
7. Inspect metadata for the `resetStatistics` operation.
8. If needed, toggle `PollingEnabled` in a safe fixture and check bean state.
9. Never invoke dangerous operations in production merely to prove the tool works.
10. Record the JVM identity, endpoint, timestamp, and tool status.

A JConsole screenshot is useful runtime evidence, yet cannot replace integration tests or security tests. With custom `MBeanServer`s, JConsole might connect to a different server and fail to show the expected object.

## 11. Proving JMX Points to the Right Spring Bean

An exporter can register a valid MBean pointing to the wrong instance:

~~~java
exporter.setBeans(Map.of(
        "com.example.orders:type=QueueMonitor,name=primary",
        new QueueMonitor()));
~~~

If the business service uses a different `QueueMonitor` bean, JMX numbers stay frozen. To prove the right instance:

1. Retrieve the bean from `ApplicationContext`.
2. Perform a safe state change on that bean.
3. Read the corresponding attribute via `MBeanServer`.
4. Compare results, and repeat when two instances of the same type exist.
5. Add an `InstanceId` if the environment runs multiple JVMs/contexts.

Do not compare object reference identity between a client proxy and the bean to prove the same target; a JMX proxy and bean are distinct references. Verify through state and registration configuration.

## 12. Integration Testing Registration and State

~~~java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class QueueJmxTest {

    @Test
    void registersMBeanAndReadsBeanState() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                QueueJmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.orders:type=QueueMonitor,name=primary");

            assertTrue(server.isRegistered(name));

            QueueMonitor monitor = context.getBean(QueueMonitor.class);
            monitor.enqueue();

            assertEquals(1,
                    server.getAttribute(name, "QueueDepth"));
        }
    }
}
~~~

This is a straightforward integration test for Spring bean -> `MBeanExporter` -> `MBeanServer`. The test must close the context so the exporter cleans up.

In parallel test suites, use isolated servers or unique JMX names to avoid collisions when tests share the platform `MBeanServer`.

## 13. Assertions for MBeanInfo

~~~java
import java.util.Arrays;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

assertTrue(Arrays.stream(info.getAttributes()).anyMatch(a ->
        "QueueDepth".equals(a.getName())
        && "int".equals(a.getType())
        && a.isReadable()
        && !a.isWritable()));

assertTrue(Arrays.stream(info.getAttributes()).anyMatch(a ->
        "PollingEnabled".equals(a.getName())
        && "boolean".equals(a.getType())
        && a.isReadable()
        && a.isWritable()));

assertTrue(Arrays.stream(info.getOperations()).anyMatch(op ->
        "resetStatistics".equals(op.getName())
        && op.getSignature().length == 0));
~~~

These assertions guard the contract across code refactoring, assembler swaps, Spring upgrades, or migrating Standard MBeans to annotation-based exporting.

In some `ModelMBean` configurations, getter/setter metadata may be represented differently from a Standard MBean. When testing migrations, clearly define mandatory contract rules vs. intentionally accepted metadata differences.

## 14. Verifying Operations Actually Execute

Asserting that an operation appears in metadata is not enough. For a demo, an internal counter can measure side effects:

~~~java
QueueMonitor monitor = context.getBean(QueueMonitor.class);

int before = monitor.getResetCountForTest();

server.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);

assertEquals(before + 1, monitor.getResetCountForTest());
~~~

Operations may receive invalid input, throw business exceptions, or be blocked by external dependencies. In real systems, include tests for:
- Valid inputs.
- Invalid inputs clearly rejected.
- Operations not leaking secrets.
- Execution time bounded by an appropriate budget/deadline.
- Post-timeout outcomes not assumed to be guaranteed failures.
- Retries not creating duplicate side effects if the operation is non-idempotent.

Never execute production-impacting operations during a basic verification check.

## 15. Evaluating MBeanExporter Lifecycle

A critical point is whether registrations are cleaned up properly when the Spring `ApplicationContext` closes.

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

var context = new AnnotationConfigApplicationContext(
        QueueJmxConfiguration.class);

try {
    assertTrue(server.isRegistered(name));
} finally {
    context.close();
}

assertFalse(server.isRegistered(name));
~~~

This test assumes the fixture actually owns that registration. In environments with multiple exporters or `IGNORE_EXISTING`/`REPLACE_EXISTING` registration policies, shutdown outcomes can differ. Ownership must be managed accurately.

Closing a Spring context does not destroy the JVM's platform `MBeanServer`. With a custom `MBeanServer`, the server's owner is responsible for releasing it after the exporter has cleaned up registrations.

## 16. Testing Naming Strategies and Multiple Instances

When two beans of the same type must be managed, use two clear names:

~~~text
com.example.orders:type=QueueMonitor,name=primary
com.example.orders:type=QueueMonitor,name=secondary
~~~

Assertions should cover:
- Both names register simultaneously.
- The two ObjectNames point to distinct instances.
- Primary data is not overwritten by secondary outside explicitly defined shared state.
- Closing one context does not arbitrarily unregister MBeans owned by another context.
- The naming strategy does not unexpectedly alter names during refactoring.

`RegistrationPolicy.FAIL_ON_EXISTING` helps catch duplicate names. `IGNORE_EXISTING` can retain an old MBean so the new bean's metrics go unpublished; `REPLACE_EXISTING` requires clear ownership and lifecycle control. Policies do not replace a naming strategy.

## 17. Verifying via Remote Connector

A local JMX API test does not exercise the remote connector. For clients in another JVM, a proper `JMXConnectorServer` is needed and connected via `JMXConnector`.

Client example (assuming the test endpoint fixture is ready):

~~~java
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi");

try (JMXConnector connector =
        JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    assertTrue(connection.isRegistered(name));

    assertEquals(1,
            connection.getAttribute(name, "QueueDepth"));
}
~~~

Remote tests should run in an isolated environment with managed network/ports, bounded timeouts, and complete teardown.

If production requires TLS/authentication, dedicated security tests are mandatory. An unauthenticated loopback JMX connection only proves the fixture's transport, not production security policy.

## 18. Reviewing Security and Exposure Surface

The MBean inventory should classify attributes/operations by risk:

| Component | Risk | Assessment |
| --- | --- | --- |
| `QueueDepth` read-only | Metric observation | Usually appropriate |
| `PollingEnabled` writable | Alters processing | Restrict to authorized operators |
| `resetStatistics` | Mutates counters | Needs audit/side-effect tests |
| `getSecret()` | Information disclosure | Do not expose |
| `deleteAllData()` | Data destruction | Do not expose by default |
| `restartService()` | System disruption | Requires dedicated policy |

`MBeanInfo` provides evidence that a method is published, not that connector authorization is enforced. Verify actual security policies and user roles at runtime whenever remote JMX is used.

A negative metadata assertion ensuring dangerous methods are absent is just as valuable as checking that valid methods exist.

## 19. Evaluating Notifications

If an MBean implements `NotificationBroadcaster`, tests include:
1. `MBeanInfo` lists the expected notification type.
2. Listener registers successfully via `MBeanServer`.
3. A test event is emitted.
4. Listener receives the expected type, sequence, and payload.
5. Listener is removed.
6. After context close, no wrongly owned listeners remain registered.

Conceptual code:

~~~java
CountDownLatch latch = new CountDownLatch(1);
NotificationListener listener = (notification, handback) -> {
    if ("com.example.queue.threshold".equals(notification.getType())) {
        latch.countDown();
    }
};

server.addNotificationListener(name, listener, null, null);

try {
    triggerSafeTestNotification();
    assertTrue(latch.await(2, TimeUnit.SECONDS));
} finally {
    server.removeNotificationListener(name, listener);
}
~~~

This example assumes the fixture actually supports the chosen notification type and has a safe trigger method. Tests need a deadline so they do not hang if no callback arrives.

## 20. Evaluating Freshness and Identity

An MBean can still be registered with the right contract yet point to a stale bean. To evaluate observability, add:
- `InstanceId` and build version.
- `LastUpdatedEpochMillis`.
- `HeartbeatEpochMillis`.
- `SnapshotVersion` or sequence.
- `LastSuccessfulPoll` on the client.
- `FRESH`/`STALE`/`UNAVAILABLE` status.

An unchanging business metric alone does not prove data is stale: a queue can legitimately sit empty for hours. Heartbeat and poll timestamps provide better evidence when evaluating freshness.

If multiple JVMs share an `ObjectName`, clients must also identify the endpoint or JVM instance to avoid mixing data incorrectly.

## 21. Sample Design Evidence Table

| Requirement | Evidence | Conclusion Drawn |
| --- | --- | --- |
| Accurate `ObjectName` | `isRegistered` and `queryNames` | Registry currently holds expected name |
| Right bean | Mutate bean state then read JMX | JMX reflects live business instance |
| Read-only attribute | `MBeanAttributeInfo` | No setter exposed to clients via contract |
| Valid operation signature | `MBeanOperationInfo` | Callable API has matching name/parameters |
| Correct operation side effect | `invoke` + state assertion | Produces expected effect in fixture |
| Sensitive method omitted | Negative `MBeanInfo` assertion | JMX surface lacks that method |
| Clean lifecycle | `close` + registry check | Exporter unregisters according to ownership |
| Remote access | `JMXConnector` test | Connector fixture works |
| Authorization | Test user/role against secured connector | Actual permissions match policy |
| Notifications | Metadata + listener test | Event declared and emitted |
| Freshness | Timestamp/heartbeat/poll logs | Values distinguish stale vs. fresh |

Do not mark every requirement mandatory for every MBean. A read-only MBean needs no operations or notifications if the use case does not call for them.

## 22. Contract Snapshots to Prevent Regression

Metadata can be normalized:

~~~text
ObjectName=com.example.orders:type=QueueMonitor,name=primary

ATTR:
  PollingEnabled|boolean|READ|WRITE
  QueueDepth|int|READ|-

OP:
  resetStatistics|void|()
~~~

From `MBeanInfo`, sort attributes and operations by name/signature, then diff against the approved contract. If an operation is overloaded, method name alone is insufficient to identify a signature.

When migrating from Standard MBean to annotation-based `ModelMBean`, metadata may differ in descriptors, descriptions, or getter/setter representation. Compatibility evaluation must identify which fields clients actually depend on.

Do not diff raw console output verbatim if ordering or secondary metadata varies across framework versions.

## 23. Common Self-Assessment Pitfalls

**Looking only at JConsole:** can miss lifecycle, security, stale data, or remote connector issues.

**Checking only `isRegistered`:** the registry might contain another exporter's MBean, especially when `IGNORE_EXISTING` is used.

**Reading only source code:** having the right annotations/interfaces in code does not prove the exporter picked the expected bean and assembler.

**Checking only operation presence:** fails to catch exceptions or incorrect side effects.

**Running only happy-path tests:** misses duplicate ObjectNames, wrong types, missing permissions, timeouts, or missing cleanup.

**Using a remote client against the wrong server:** the connector may attach to a custom `MBeanServer` while tests inspect the platform server.

**Confusing AOP proxies with management interfaces:** you may inspect the proxy's metadata rather than the target class; understand which object the exporter actually receives.

**Failing to record concrete evidence:** concluding "looks good" omits the JVM, `ObjectName`, Spring version, test case, or timestamp observed.

## 24. Seven-Step Evaluation Workflow

1. **Define the purpose.** Does the MBean support observability, administrative operations, or notifications?
2. **Document the contract.** `ObjectName`, attribute types/permissions, operation signatures, expected behavior, and lifecycle.
3. **Inspect `MBeanInfo`.** Check metadata on the exact server used by the exporter.
4. **Observe runtime.** Use JConsole or an equivalent tool on the right JVM.
5. **Run tests.** Cover registration, behavior, negative cases, lifecycle, and remote/security where applicable.
6. **Verify each requirement.** Mark `VERIFIED`, `PARTIALLY_VERIFIED`, or `NOT_VERIFIED` based on evidence.
7. **Prioritize fixes.** Focus on security bugs, side effects, wrong instances, data freshness, and compatibility before cosmetic adjustments.

When refactoring is needed, re-run the same contract test suite before and after to catch unintended changes to the management API.

## 25. Hands-On Exercises

**Exercise 1.** Create a `CacheMonitorMBean` with `CacheSize` and `resetStatistics`, and capture an `MBeanInfo` snapshot including types/access/signatures.

**Exercise 2.** Add a `deleteAllData` method on the implementation without adding it to the management interface. Write a negative assertion verifying the method is absent from metadata.

**Exercise 3.** Accidentally export a `QueueMonitor` instance different from the bean updated by the service. Write a test exposing the discrepancy, then fix it via dependency injection.

**Exercise 4.** Create `primary` and `secondary` MBeans of the same class under two ObjectNames, using tests to prove the two instances remain isolated.

**Exercise 5.** Check registration before and after `ApplicationContext.close()`, distinguishing MBean unregistration from the platform server's lifecycle.

**Exercise 6.** Set up a remote connector in an isolated loopback fixture, connect via `JMXConnector`, and read an attribute over `MBeanServerConnection`.

**Exercise 7.** Add a notification type and verify `MBeanInfo`, listener callbacks, sequence numbers, and cleanup.

**Exercise 8.** Convert a Standard MBean to Spring annotation metadata, comparing before/after snapshots to detect differences.

**Exercise 9.** Produce an evaluation report containing requirements, evidence, results, and improvements for a real MBean in a sample project.

## Conclusion

Self-assessment of a Spring Framework JMX design must rely on **evidence from `MBeanInfo`, tools, and tests**, not gut feelings about configuration. `MBeanInfo` reveals the management contract actually published; tools like JConsole verify the operational experience; integration tests reproducibly verify registration, behavior, lifecycle, security, and compatibility. Every claim must be tied to an `ObjectName`, the right `MBeanServer`, the right managed instance, and observable results. Untested requirements must be explicitly marked unverified, and gaps between expectations and reality must be addressed according to risk severity.

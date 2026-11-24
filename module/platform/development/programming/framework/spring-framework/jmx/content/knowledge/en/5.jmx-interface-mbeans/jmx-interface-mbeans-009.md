# Testing the Management Interface as a Public Contract

## 1. Purpose and Significance

In Java Management Extensions (JMX), an MBean is not just a Java object whose methods can be called. When registered with an \`MBeanServer\`, an MBean exposes a **management interface** consisting of its identifier (\`ObjectName\`), attributes, operations, data types, read/write permissions, exceptions, and sometimes notifications. This interface can be used by JConsole, monitoring tools, operational automation, or clients developed by other teams.

Therefore, you should **test the JMX interface as a public contract**: test what clients actually observe and can do via JMX, rather than testing only internal Java methods.

After this lesson, you will be able to:

- Identify the components that make up an MBean's public contract.
- Distinguish direct Java method testing from testing through \`MBeanServerConnection\`.
- Verify \`ObjectName\`, \`MBeanInfo\`, attributes, operations, and parameter/return types.
- Build automated tests verifying behavior and errors when clients send invalid requests.
- Determine compatibility boundaries when changing names, types, writable/readable flags, or operations.
- Distinguish functional contract testing from security, authorization, concurrency, and remote connector testing.
- Apply the same testing mindset to MBeans exported from Spring Framework.

## 2. An MBean Is a Public API at the Management Layer

When a client knows only the \`ObjectName\`, it can invoke:

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);
Object value = connection.getAttribute(name, "QueueSize");
connection.setAttribute(name, new Attribute("Enabled", false));
Object result = connection.invoke(
    name, "resetStatistics", new Object[0], new String[0]);
\`\`\`

This resembles an application-level API: clients depend on the exposed names and structures. Renaming an internal method from \`resetCount()\` to \`clearCount()\` may be harmless if the MBean contract stays intact; renaming the JMX operation from \`resetStatistics\` to \`reset\` can break operational clients.

\`\`\`text
Application code
  |
  |  Standard MBean / MXBean / DynamicMBean / Spring exporter
  v
MBeanServer
  |
  |  getMBeanInfo / getAttribute / setAttribute / invoke
  v
JConsole, monitoring agents, automation, remote clients
\`\`\`

**Important testing boundary:** what clients observe through JMX is what must be verified. A unit test calling the Java object directly is still useful, but it does not prove the bean was registered under the right name, exposes the right metadata, or is accessible via JMX.

## 3. Which Components Belong to the Contract?

| Component | Aspects to Test | Example Risk |
|---|---|---|
| \`ObjectName\` | Domain, key properties, stable name, unique name | Dashboards cannot find the MBean after a rename |
| Attributes | Name, type, readable/writable, values, bounds | Client reads successfully, yet type changed from \`Integer\` to \`String\` |
| Operations | Name, parameters, signature, return type, effect | Scripts invoking old operation fail with \`ReflectionException\` |
| Metadata | \`MBeanInfo\`, descriptions, impact, notifications | Tools render UI incorrectly or omit actions |
| Exceptions | Error scenarios and how JMX reflects failures | Client receives exceptions that blur invalid input vs. system errors |
| Lifecycle | Registration, unregistration, restart, reload | Duplicate MBean names or failure to unregister |
| Behavior | Business meaning of attributes/operations | \`resetStatistics\` fails to reset the right data |
| Security | Who may observe or control | Unauthorized users invoke management operations |
| Compatibility | Contract across versions | Older clients break on a new release |

In contract testing, metadata should not be treated as decorative. \`isReadable()\`, \`isWritable()\`, \`getType()\`, \`getSignature()\`, and \`getReturnType()\` can all affect client behavior.

## 4. Designing a Testable JMX Contract

Suppose an application has a queue manager with the contract:

\`\`\`text
ObjectName:
  training.contract:type=Queue,name=Orders

Attributes:
  PendingCount : int      read-only
  Enabled      : boolean  read/write

Operations:
  resetStatistics() : void

Behavior:
  PendingCount >= 0
  Enabled = false causes new task submissions to be rejected
  resetStatistics() resets the counter to 0
\`\`\`

The contract is expressed as a Standard MBean:

\`\`\`java
// QueueControlMBean.java
public interface QueueControlMBean {
    int getPendingCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void resetStatistics();
}
\`\`\`

Illustrative implementation:

\`\`\`java
// QueueControl.java
import java.util.concurrent.atomic.AtomicInteger;

public final class QueueControl implements QueueControlMBean {
    private final AtomicInteger pending = new AtomicInteger();
    private volatile boolean enabled = true;

    @Override
    public int getPendingCount() {
        return pending.get();
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
        pending.set(0);
    }

    public boolean submitTask() {
        if (!enabled) {
            return false;
        }
        pending.incrementAndGet();
        return true;
    }
}
\`\`\`

In a real system, clearly define whether \`PendingCount\` counts queued, in-progress, or completed tasks; reset behavior may also differ. This example is intentionally minimal to focus on JMX. Because checking \`enabled\` and calling \`incrementAndGet\` are not atomic together, the example does not guarantee strict linearizability under concurrent updates; if the contract requires it, add state synchronization and concurrency tests.

### 4.1. Writing the Contract as Verifiable Criteria

A good contract specification states precisely:

1. Which \`ObjectName\` must exist after startup.
2. Which set of attributes must be exposed, with what types and read/write permissions.
3. Which operations are exposed, with what parameter signatures and return types.
4. Expected values or postconditions after each action.
5. Behavior on invalid actions.
6. What remains stable across releases.
7. Which permissions are required for remote access and audit requirements, if supported by the system.

If the contract does not define outcomes, a test asserting only "no exception thrown" is usually too weak to protect clients.

## 5. Creating a Test Environment via MBeanServer

Running the entire production application or opening a remote JMX port is unnecessary. For JMX-level contract testing, you can create an isolated \`MBeanServer\` to avoid colliding with the test process's platform MBeanServer:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server = MBeanServerFactory.newMBeanServer();
ObjectName name = new ObjectName(
    "training.contract:type=Queue,name=Orders");

QueueControl bean = new QueueControl();
server.registerMBean(bean, name);
\`\`\`

\`MBeanServerFactory.newMBeanServer()\` creates a new MBeanServer without registering it in the list discoverable via \`findMBeanServer\`. This keeps tests isolated. An \`MBeanServer\` also implements \`MBeanServerConnection\`, so tests exercise the same client contract as cross-JVM JMX connections.

Do not use \`ManagementFactory.getPlatformMBeanServer()\` for multiple parallel tests using fixed names if tests could collide. For Spring integration tests, you can select a dedicated server and configure the exporter to use it; this is important so tests do not pollute the shared environment.

## 6. Automated Testing with JUnit 5

The snippet below illustrates a test class for JDK 21 and JUnit Jupiter 5. It assumes \`QueueControl.java\` and \`QueueControlMBean.java\` are already in the test project.

\`\`\`java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import javax.management.*;
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class QueueControlContractTest {
    private MBeanServer server;
    private ObjectName name;
    private QueueControl queue;

    @BeforeEach
    void setup() throws Exception {
        server = MBeanServerFactory.newMBeanServer();
        name = new ObjectName(
            "training.contract:type=Queue,name=Orders");
        queue = new QueueControl();
        server.registerMBean(queue, name);
    }

    @Test
    void registrationAndPublicAttributesMatchContract()
            throws Exception {
        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);
        Map<String, MBeanAttributeInfo> attrs =
            Arrays.stream(info.getAttributes())
                  .collect(Collectors.toMap(
                      MBeanAttributeInfo::getName,
                      Function.identity()));

        assertEquals(2, attrs.size());

        MBeanAttributeInfo pending = attrs.get("PendingCount");
        assertNotNull(pending);
        assertEquals("int", pending.getType());
        assertTrue(pending.isReadable());
        assertFalse(pending.isWritable());

        MBeanAttributeInfo enabled = attrs.get("Enabled");
        assertNotNull(enabled);
        assertEquals("boolean", enabled.getType());
        assertTrue(enabled.isReadable());
        assertTrue(enabled.isWritable());

        assertEquals(0, server.getAttribute(name, "PendingCount"));
        assertEquals(true, server.getAttribute(name, "Enabled"));
    }

    @Test
    void writableAttributeChangesManagedBehavior()
            throws Exception {
        server.setAttribute(name, new Attribute("Enabled", false));
        assertEquals(false, server.getAttribute(name, "Enabled"));

        assertFalse(queue.submitTask());
        assertEquals(0, server.getAttribute(name, "PendingCount"));

        server.setAttribute(name, new Attribute("Enabled", true));
        assertTrue(queue.submitTask());
        assertEquals(1, server.getAttribute(name, "PendingCount"));
    }

    @Test
    void operationSignatureAndBehaviorMatchContract()
            throws Exception {
        MBeanInfo info = server.getMBeanInfo(name);
        MBeanOperationInfo reset =
            Arrays.stream(info.getOperations())
                  .filter(op -> op.getName().equals("resetStatistics"))
                  .findFirst()
                  .orElseThrow();

        assertEquals(0, reset.getSignature().length);
        assertEquals("void", reset.getReturnType());

        queue.submitTask();
        queue.submitTask();
        assertEquals(2, server.getAttribute(name, "PendingCount"));

        server.invoke(
            name, "resetStatistics",
            new Object[0], new String[0]);

        assertEquals(0, server.getAttribute(name, "PendingCount"));
    }

    @Test
    void invalidRequestsFailThroughJmxBoundary() {
        assertThrows(
            AttributeNotFoundException.class,
            () -> server.getAttribute(name, "UnknownAttribute"));

        assertThrows(
            AttributeNotFoundException.class,
            () -> server.setAttribute(
                name, new Attribute("PendingCount", 9)));

        assertThrows(
            InvalidAttributeValueException.class,
            () -> server.setAttribute(
                name, new Attribute("Enabled", "false")));

        assertThrows(
            ReflectionException.class,
            () -> server.invoke(
                name, "unknownOperation",
                new Object[0], new String[0]));
    }
}
\`\`\`

The example focuses on the **public JMX boundary**: tests query metadata and call \`server.getAttribute\`, \`server.setAttribute\`, and \`server.invoke\`. Calling \`queue.submitTask()\` directly is used only to stimulate state changes on the resource, while state observation and management control still go through JMX.

### 6.1. Why Verify Both Metadata and Actual Results?

Tests reading \`MBeanInfo\` catch unintended changes in the interface; invocation tests prove the interface is not merely declared but actually works. Both are needed:

\`\`\`text
Metadata test:
  Does the client see the right contract?

Behavior test:
  Do valid calls fulfill the right contract?
\`\`\`

An MBean might expose the right method while its implementation is broken; conversely, the implementation might be right while the exporter/assembler fails to expose the method, leaving clients unable to use it.

### 6.2. Issues with Comparing All Metadata Strictly

Not every descriptive field needs to stay frozen forever. If \`description\` is solely for UI display, wording edits may be valid. Contract tests should pin the parts clients actually rely on: names, types, permissions, signatures, behavioral semantics, and \`ObjectName\`s. If clients use descriptions to generate documentation, then descriptions can also become part of the contract.

## 7. Testing Error Cases and Boundary Behavior

### 7.1. Non-Existent Attribute

Client requests a name not registered on the MBean:

\`\`\`java
connection.getAttribute(name, "NotExists");
\`\`\`

Expected: an appropriate JMX error, such as \`AttributeNotFoundException\`. Tests should not assert only generic \`Exception\`, since a connection error could then make the test "pass."

### 7.2. Writing to a Read-Only Attribute

If \`PendingCount\` is exposed read-only, clients must not be able to modify it directly:

\`\`\`java
connection.setAttribute(
    name, new Attribute("PendingCount", 123));
\`\`\`

Expected: failure per the JMX contract; with Standard MBeans, typically \`AttributeNotFoundException\` for non-writable attributes. With DynamicMBeans, depending on the implementation, the specific error must be verified against the defined contract.

### 7.3. Wrong Data Type

\`\`\`java
connection.setAttribute(
    name, new Attribute("Enabled", "false"));
\`\`\`

\`Enabled\` is boolean. The string \`"false"\` is not \`Boolean.FALSE\`. Clients should not rely on implicit coercion unless the MBean contract or adapter explicitly documents conversion rules.

### 7.4. Non-Existent Operation or Signature Mismatch

\`\`\`java
connection.invoke(
    name, "resetStatistics",
    new Object[]{"extra"},
    new String[]{String.class.getName()});
\`\`\`

Even though the operation name matches, the signature differs from the zero-argument contract. The invocation is expected to be rejected. This is especially important when an MBean has overloads.

### 7.5. Operations with Side Effects

Never test data-destructive operations on a live user-serving system by calling them outside controlled boundaries. Use mock beans or isolated data fixtures. If management operations involve cache clearing, restarts, queue draining, log-level changes, or shutdown, design tests with clear postconditions and isolated scope.

## 8. Contract Testing for MXBeans and DynamicMBeans

### 8.1. MXBean: Testing Open Data Types

MXBeans support mapping Java types to JMX Open Data types so clients can interact through a standard set of data types. A Java method returning a DTO may be exposed as \`CompositeData\` instead of returning the DTO directly to JMX clients.

When testing MXBeans:

- Inspect exposed metadata, not just return types in the Java interface.
- Verify fields and types of \`CompositeData\` or \`TabularData\` if clients depend on them.
- Test null values, empty datasets, and compatibility when adding/removing fields.
- Verify operations can be invoked via \`MBeanServerConnection\`, not just via an internal Java proxy.

Example reading a composite type:

\`\`\`java
Object raw = connection.getAttribute(name, "WorkerStatus");
if (raw instanceof javax.management.openmbean.CompositeData data) {
    Object state = data.get("state");
    System.out.println(state);
}
\`\`\`

The name \`WorkerStatus\` and key \`state\` are illustrative examples; actual formats depend on the defined MXBean.

### 8.2. DynamicMBean: Metadata and Dispatch Must Match

\`DynamicMBean\` returns its own \`MBeanInfo\` and dispatches actions itself:

\`\`\`java
Object getAttribute(String attribute);
void setAttribute(Attribute attribute);
AttributeList getAttributes(String[] attributes);
AttributeList setAttributes(AttributeList attributes);
Object invoke(String actionName, Object[] params, String[] signature);
MBeanInfo getMBeanInfo();
\`\`\`

Tests must cross-check:

1. Every exposed attribute behaves properly according to its readable/writable flags.
2. Every operation in metadata is invocable with the exact \`signature\`.
3. Any name or signature absent from metadata is explicitly rejected.
4. Return types and accepted input values match metadata.
5. Batch methods return appropriate results, even when only some entries succeed.
6. If metadata can change at runtime, older clients or metadata caches are handled per published compatibility rules.

A \`DynamicMBean\` with valid metadata whose handler checks the wrong name still violates the contract. Use \`MBeanServerConnection\` itself as the common test path so \`MBeanServer\` logic is not bypassed.

## 9. Spring Framework JMX: Testing from ApplicationContext to MBeanServer

In Spring Framework, \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, and an appropriate assembler can expose Spring beans as MBeans. The client's contract then consists of the **export configuration** plus the bean's behavior.

Example managed bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.spring:type=Worker,name=Primary",
    description = "Worker management interface")
public class WorkerManagement {
    private volatile boolean enabled = true;

    @ManagedAttribute
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation
    public void disable() {
        this.enabled = false;
    }
}
\`\`\`

The application must enable/configure appropriate annotation export support, such as \`@EnableMBeanExport\`, or define an \`MBeanExporter\` and metadata assembler. Simply adding \`@ManagedResource\` to a class without a suitable exporter does not guarantee the MBean will be registered.

### 9.1. Testing Levels with Spring

**Level 1 — Bean unit test:** verify \`WorkerManagement\`'s business logic when called directly in Java.

**Level 2 — Spring integration test:** create an \`ApplicationContext\` containing the bean and JMX exporter; verify the MBean is registered under the expected \`ObjectName\`.

**Level 3 — JMX contract test:** call \`MBeanServerConnection\` to verify metadata, attributes, and operations like an independent client.

**Level 4 — Remote integration test:** run the connector with authentication, encryption, and network rules in a controlled test environment; verify clients access according to authorization policies.

If the system uses Spring Boot, check the JMX settings of the specific Boot version. Defaults and Actuator integration are additional concerns; do not infer Boot behavior from plain Spring Framework examples.

### 9.2. Testing ObjectName Collisions and Lifecycle

A common integration bug is exporting two beans under the same \`ObjectName\`. Tests should prove the naming convention generates unique names. If the application opens/closes contexts multiple times, also verify unregistration so stale MBeans do not remain or cause \`InstanceAlreadyExistsException\` on re-initialization.

Within the same JVM, using the platform \`MBeanServer\` can cause Spring integration tests to interfere with each other. Prefer isolated servers, unique \`ObjectName\`s, or a consistent cleanup strategy.

## 10. Compatibility Testing When the Interface Changes

A code change can break JMX clients even when the application compiles and runs.

| Change | Compatibility Risk | Strategy |
|---|---|---|
| Rename \`ObjectName\` | Clients cannot find the resource | Maintain transition aliases/mappings if needed |
| Rename attribute | Dashboards/scripts reading old name fail | Add new name alongside during transition when feasible |
| Change type \`int\` to \`String\` | Parsing and comparisons break | Introduce a new attribute or versioned schema |
| Change read-only to writable | Opens new state-mutation capability | Review permissions and test writes |
| Change writable to read-only | Existing automation fails | Announce migration and test impact |
| Remove operation | Client calls fail | Plan deprecation/transition |
| Add operation | Can be a compatible addition | Control permissions and side effects |
| Change overload/signature | Old client invocations mismatch | Keep old signature or bump version |
| Change metric meaning | Dashboards report wrong info despite unchanged type | Document semantic contract and test postconditions |
| Change \`CompositeData\` schema | Clients relying on keys/types may fail | Test against actual consumers |

One regression-testing technique: store an approved contract specification (e.g., list of \`ObjectName\`s, attributes, operations, and behavioral expectations) in a test fixture; on every release, verify required items remain present. For intentional changes, update the contract fixture together with migration docs and affected clients.

You do not necessarily have to snapshot the entire \`MBeanInfo.toString()\` output because display order or non-critical descriptions may vary across JDKs or implementations. Compare semantically meaningful components.

## 11. Security and Remote Access Testing

Functional contract tests on a local server do not prove a remote endpoint is safe. For remote JMX, run separate tests in a controlled environment:

- Valid clients can authenticate and access only permitted MBeans/operations.
- Unauthorized clients are rejected.
- Connections protect data in transit according to the system's TLS policy.
- JMX RMI ports/hostnames are configured and network-restricted properly.
- Sensitive information is not exposed via attributes/notifications.
- State-changing operations are permission-restricted and audited if policy requires.
- Access failures do not leak secrets in error messages or logs.

**Do not treat accessibility from public networks as a success criterion.** A secure operational model normally restricts JMX to a management network, VPN, or appropriate tunnel; all remote testing must remain within authorized boundaries.

These checks differ from \`MBeanInfo\`: metadata can expose an operation, while authorization is the responsibility of connector/access controller configuration or application policy. \`MBeanOperationInfo.ACTION\` does not itself grant or block permissions.

## 12. Testing Notifications and State Monitoring

If an MBean emits notifications, the contract also covers notification types, emission timing, and payloads. Tests should:

1. Register a listener via JMX.
2. Trigger a deterministic event in the fixture.
3. Wait for the notification using bounded-timeout synchronization.
4. Check type, source, sequence number (if required), timestamp, and userData.
5. Remove the listener after the test.
6. Verify spurious notifications are not emitted when no event occurs.

Do not rely on a fixed \`Thread.sleep\` hoping the notification arrived. Use \`CountDownLatch\` in tests with an explicit timeout. With asynchronous execution, design tests that separate operation invocation time from processing completion time.

JMX notifications do not replace a durable message queue. The contract should clearly document delivery, ordering, and replay guarantees (if any) rather than implicitly assuming notifications cannot be lost.

## 13. A Practical Testing Matrix

| Test Layer | Checks | Defects Caught |
|---|---|---|
| API metadata | \`ObjectName\`, attributes, operations, types | Breaking contract changes |
| API behavior | Read/write/invoke and postconditions | Incorrect implementation |
| Negative cases | Invalid names, types, and signatures | Bad validation/exceptions |
| Registration lifecycle | Register, duplicate names, unregister | Missing MBeans, resource leaks |
| Spring integration | Bean/exporter/assembler/naming strategy | Works when called directly, not exported via JMX |
| Concurrency | Reads/writes across multiple threads | Race conditions, inconsistent state |
| Notification | Event type, payload, timing | Subscribers receive wrong data |
| Security integration | Authentication, authorization, TLS, network | Exposed administrative privileges |
| Compatibility | Comparing old/new contracts | Broken legacy scripts, dashboards, and agents |

Not every lesson or every MBean needs all of these tests. The required rigor depends on how dangerous the management actions are, the number of consumers, and whether producer and clients release independently.

## 14. Practice Exercises

### Exercise A — Write a Contract Fixture

Create a test data file containing:

\`\`\`yaml
objectName: training.contract:type=Queue,name=Orders
attributes:
  - name: PendingCount
    type: int
    readable: true
    writable: false
  - name: Enabled
    type: boolean
    readable: true
    writable: true
operations:
  - name: resetStatistics
    signature: []
    returnType: void
\`\`\`

From the fixture, write assertions against \`getMBeanInfo\`. You do not need a complex YAML parser if the goal is simply practicing contracts; you can start with an equivalent Java structure.

### Exercise B — Intentionally Introduce a Breaking Change

Rename \`getPendingCount()\` to \`getQueueLength()\` in the interface. Run the contract test and record which metadata changed. Then restore the old interface while changing the internal implementation freely. Observe the difference between Java method names and public attribute names.

### Exercise C — Change Write Access

Remove the \`setEnabled\` setter. Use metadata tests to verify \`Enabled\` becomes read-only, and verify JMX writes fail. Discuss when this change is a breaking change for existing automation.

### Exercise D — Spring Integration

Create a Spring context containing \`WorkerManagement\` and a corresponding exporter. Use \`MBeanServerConnection\` to verify the exact \`ObjectName\` and \`disable\` operation. Then intentionally remove the export configuration to see the test fail even while bean unit tests still pass.

### Exercise E — Simulate a Legacy Consumer Client

Create a client that knows only the \`ObjectName\` and published names/signatures, with zero source references to \`QueueControl\`. Use it as a consumer contract test against both the old and new implementations. This is a good way to verify that the contract is protected independently of code details.

## 15. Self-Check Questions

1. Why is calling a Java method directly not a JMX contract test?
2. Which parts of \`MBeanInfo\` can break clients if changed?
3. Why is testing \`isRegistered\` insufficient to conclude an MBean works properly?
4. When is renaming an attribute a breaking change?
5. Why must operation \`signature\` be tested?
6. How do you test read-only attributes and mismatched input types?
7. What is the benefit of \`MBeanServerFactory.newMBeanServer()\` in tests?
8. What else does Spring JMX need tested beyond bean unit tests?
9. Why does metadata testing not replace remote JMX security testing?
10. When a system emits notifications, which elements belong to the subscriber's contract?

## 16. References

- Java SE 21 — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 — \`MBeanOperationInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — \`MBeanServerFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/

**Key takeaway:** testing an MBean as a public contract means observing and invoking it from the JMX client's perspective. Verify both metadata and behavior, test errors and lifecycle, protect compatibility, and keep functional testing separate from remote access authorization.

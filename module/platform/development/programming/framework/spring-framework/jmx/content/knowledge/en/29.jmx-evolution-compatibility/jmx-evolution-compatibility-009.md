# Checking JDK or Framework Changes Affecting JMX

## 1. Learning Objectives

When upgrading JDK or Spring Framework versions, business code may still compile and run, yet the JMX management surface can change in subtle ways: MBeans stop registering, ObjectNames differ, attribute/operation metadata changes, a Spring proxy no longer exposes methods as before, remote connectors fail to connect, or monitoring tools encounter data type errors.

This lesson belongs to **Spring Framework JMX → Evolution and Compatibility**. After this lesson, you will be able to:

- Identify which JMX behavioral layers can be affected when upgrading the JDK, Spring, or related libraries.
- Establish a clear baseline for ObjectNames, `MBeanInfo`, attributes, operations, and notifications.
- Test `MBeanExporter`, annotation-driven export, naming strategies, and Spring AOP after an upgrade.
- Verify platform MBeans, MXBeans, remote connectors, serialization, authentication, and network settings.
- Build a JDK/framework/client test matrix alongside canary and rollback procedures.
- Distinguish genuine API changes from issues caused by configuration, runtime classpath, module access, and deployment environment.

## 2. Why Can JMX Be Affected Even When Code Does Not Change?

JMX spans multiple layers:

```text
Management client: JConsole / JMC / agent / script
            |
            v
Remote connector (optional: RMI, TLS, auth)
            |
            v
MBeanServer / MBeanServerConnection
            |
            v
Spring MBeanExporter / annotation metadata
            |
            v
Managed bean / Spring AOP proxy / MXBean
            |
            v
Application services / JDK management internals
```

An upgrade can alter behavior at **any layer**:

1. JDK: MXBeans, module encapsulation, security configuration, TLS/ciphers, RMI behavior, or GC implementations.
2. Spring: exporter lifecycle, metadata assemblers, annotation scanning, naming strategies, AOP proxies, and classpath.
3. Libraries: MBeans from caches, message brokers, connection pools, or agents may change names/metadata.
4. Deployment: hostnames, container images, Java flags, Kubernetes port forwarding, firewalls, and certificates.
5. Clients: Java version, JConsole/JMC, JMX connector provider, or differing client/server classpaths.

Therefore, do not rely solely on unit tests of Java services; **test the JMX contract at runtime** and exercise management flows from where clients actually run.

## 3. Distinguishing Three Types of Compatibility

| Type | Question | Verification tool |
| --- | --- | --- |
| **Registration compatibility** | Is the MBean still present under the old ObjectName? | `isRegistered`, `queryNames` |
| **Management contract compatibility** | Are attributes, operations, signatures, and notifications intact? | `getMBeanInfo`, invoke/read tests |
| **Transport/operational compatibility** | Can clients still connect, authenticate, receive data, and operate reliably? | Remote connector integration test |

For example, after an upgrade, `isRegistered(name)` still returns `true`, yet `getAttribute(name, "PendingCount")` throws because the attribute was renamed. The registration test passes, but the contract test fails.

Or a local JMX call passes while remote JMX fails because `java.rmi.server.hostname` is misconfigured inside a container. The contract may be intact, yet transport is broken.

## 4. Cataloging the JMX Contract Before Upgrading

Before changing JDK/Spring, record:

- JVM/JDK vendor, major version, runtime options, and active GC.
- Spring Framework version, Spring Boot version if used, and related management dependencies.
- Which `MBeanServer` is used: platform or custom.
- Which `ObjectName`s the application exposes.
- Required attributes: name, type, read/write flags, and semantics.
- Critical operations: name, parameter types, return type, and side effects.
- Notification types, userData schema, and event semantics.
- JMX remote endpoints, authentication, TLS, and RMI ports.
- Which names or data types clients/agents use.
- Context startup/shutdown lifecycle and registration policy.

A baseline can be stored in YAML format:

```yaml
objectName: "com.example.orders:type=Queue,name=Payment"
attributes:
  PendingCount:
    type: "int"
    readable: true
    writable: false
  Paused:
    type: "boolean"
    readable: true
    writable: true
operations:
  - name: "retryFailed"
    signature: ["int"]
    returnType: "void"
notifications:
  - "com.example.orders.queue.overloaded"
```

The baseline must come from **the contract currently used by clients**, not freshly generated from the upgraded build and compared against itself.

## 5. Differences Between JDK Management MBeans and Application MBeans

The JDK provides platform management MXBeans, such as:

```text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=Runtime
java.lang:type=ClassLoading
java.lang:type=OperatingSystem
```

These standard MXBeans serve JVM observability. However, MBeans tied to specific collectors, implementations, or vendors can vary across JDKs:

```text
java.lang:type=GarbageCollector,name=...
java.lang:type=MemoryPool,name=...
java.nio:type=BufferPool,name=...
```

Do not assume GC or memory pool names remain identical across JDK generations. For example, switching garbage collectors can change the count and names of `GarbageCollectorMXBean`/memory pools even though clients still need the same kind of metrics.

It is better to query by pattern and inspect metadata:

```java
ObjectName gcPattern = new ObjectName(
    "java.lang:type=GarbageCollector,*"
);

for (ObjectName name :
        server.queryNames(gcPattern, null)) {
    System.out.println(name.getCanonicalName());
}
```

Clients must understand that individual collectors do not necessarily have immutable names. The absence of an implementation-specific MBean on a newer JDK **does not mean** standard JMX APIs were removed.

## 6. Reading JDK Information from the Target JVM

For a local JVM:

```java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
System.out.println(System.getProperty("java.vm.name"));
```

From `MBeanServerConnection`, you can query `java.lang:type=Runtime`:

```java
ObjectName runtimeName = new ObjectName(
    "java.lang:type=Runtime"
);

Object vmVersion = connection.getAttribute(
    runtimeName, "VmVersion"
);
Object specVersion = connection.getAttribute(
    runtimeName, "SpecVersion"
);

System.out.println(vmVersion);
System.out.println(specVersion);
```

Do not use the **client** Java version to infer the **server** Java version. With a remote connector, `System.getProperty("java.version")` on the client describes only the client itself.

When investigating compatibility, record client and server JDKs separately.

## 7. Checking Spring MBeanExporter After Upgrading

Spring can export MBeans via `MBeanExporter`:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class OrderJmxConfiguration {

    @Bean
    public MBeanExporter queueExporter(
            MBeanServer server,
            QueueAdminMBean queueAdmin) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "com.example.orders:type=Queue,name=Payment",
            queueAdmin
        ));
        return exporter;
    }
}
```

In this example, `QueueAdminMBean` is the application management interface; to register as a Standard MBean, the implementation object must follow the corresponding convention or be wrapped with an appropriate JMX mechanism.

After upgrading, check:

- Is the Spring configuration class loaded?
- Is the exporter created and initialized with the proper lifecycle?
- Is the injected `MBeanServer` the intended server?
- Does the ObjectName mapping match before?
- Has `RegistrationPolicy` changed in config?
- Is there a second exporter registering the MBean or another annotation-driven exporter?
- Does shutdown cleanly unregister MBeans owned by the exporter?

Successful registration by `MBeanExporter` does not automatically guarantee the remote JMX connector is configured correctly.

## 8. Checking @ManagedResource and Annotation-Driven Export

With annotations:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment"
)
public class OrderQueueAdmin {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation
    public void resetStatistics() {
        // ...
    }
}
```

And configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxAnnotationConfiguration {
}
```

After upgrading Spring, test **runtime MBeanInfo**, not just source annotations.

For example:

```java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Payment"
);

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);
```

Verify the attributes/operations actually published on the server. Seeing `@ManagedOperation` still present on the class does not prove the metadata assembler found that method on a Spring proxy.

## 9. MBeanInfo Is Proof of the Actual Contract

`MBeanServer.getMBeanInfo` lets you inspect:

```java
MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "%s %s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println(op.getName());
    for (var param : op.getSignature()) {
        System.out.println("  " + param.getType());
    }
}

for (var notification : info.getNotifications()) {
    System.out.println(
        java.util.Arrays.toString(
            notification.getNotifTypes()
        )
    );
}
```

When comparing against baseline:

1. Use `ObjectName.equals()` or canonical names; key order does not alter identity.
2. Compare attribute name/type/read-write flags.
3. Compare operation name, ordered parameter types, and return type.
4. Compare notification types and event payload contracts.
5. Check `OpenType` if using MXBean/OpenMBean.
6. Avoid treating array ordering, descriptions, or implementation class names as contractual unless clients actually depend on them.

A change in `MBeanInfo.getClassName()` may result from a ModelMBean/proxy implementation change; evaluate whether it actually breaks any client.

## 10. Writing Contract Tests for the New Version

Suppose the v1 management interface:

```java
public interface QueueAdminMBean {
    int getPendingCount();
    void resetStatistics();
}
```

After upgrading, ensure those elements still exist.

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Arrays;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;

class QueueJmxCompatibilityTest {

    private final MBeanServer server; // initialized in test fixture

    QueueJmxCompatibilityTest(MBeanServer server) {
        this.server = server;
    }

    @Test
    void keepsPublishedContract() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Payment"
        );

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(
            Arrays.stream(info.getAttributes()).anyMatch(
                a -> a.getName().equals("PendingCount")
                  && a.getType().equals("int")
                  && a.isReadable()
            )
        );

        assertTrue(
            Arrays.stream(info.getOperations()).anyMatch(
                o -> o.getName().equals("resetStatistics")
                  && o.getSignature().length == 0
                  && o.getReturnType().equals("void")
            )
        );
    }
}
```

This illustrates the assertion logic; in real JUnit 5 usage, the test fixture must supply `MBeanServer` via `@BeforeEach`, Spring Test, or a suitable factory. Do not rely on constructor injection unless the project configures a `ParameterResolver`.

For automated testing, create an isolated `MBeanServer` and enable the actual Spring exporter under test.

## 11. Testing Metadata Across Versions

A pipeline can produce two artifacts:

```text
baseline-jmx-contract.json
current-jmx-contract.json
```

Process:

```text
Build with old version
      |
      v
Start test context / MBeanServer
      |
      v
Export normalized MBeanInfo baseline
      |
      v
Build with new version
      |
      v
Start test context / MBeanServer
      |
      v
Export normalized current contract
      |
      v
Compare backward compatibility
```

A normalized record might look like:

```json
{
  "objectName": "com.example.orders:name=Payment,type=Queue",
  "attributes": [
    {
      "name": "PendingCount",
      "type": "int",
      "readable": true,
      "writable": false
    }
  ],
  "operations": [
    {
      "name": "resetStatistics",
      "returnType": "void",
      "signature": []
    }
  ]
}
```

Byte-for-byte equality across all metadata is unnecessary. A new version can add attributes while remaining compatible. Compare the legacy contract parts that **must continue to exist**, and add separate semantic tests.

## 12. Checking the Java Module System and Reflective Access

Since Java 9, the module system (JPMS) can affect libraries using reflection or accessing internal classes. When upgrading the JDK, older dependencies/agents may encounter:

```text
java.lang.reflect.InaccessibleObjectException
IllegalAccessException
ClassNotFoundException
NoClassDefFoundError
```

Common causes:

- An old library accesses an internal JDK package that is no longer open.
- An application module has not `exports` the package containing the management interface.
- The runtime lacks a module required by a tool/connector.
- Different classloaders prevent proxies/serializers from seeing the MBean type.
- A JMX agent or bytecode instrumentation is incompatible with the new JDK.

Distinguish `exports` and `opens`:

- `exports`: allows other modules to access a package's public API.
- `opens`: allows deep reflection under specified conditions.

Do not add sweeping `--add-opens` flags to mask all errors. Identify which library/stack trace requires access to which package, upgrade dependencies when possible, and open only the minimal required scope.

## 13. JDK Management Agent and Remote JMX Settings

Remote JMX can be enabled with JVM flags such as:

```bash
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=127.0.0.1
```

Specific options and behavior may vary by JDK distribution/version. Do not copy flags from an older runtime without re-testing after upgrading.

In production environments:

- Enable authentication and authorization.
- Use TLS and proper certificate policies.
- Restrict network access; never expose JMX ports publicly on the Internet.
- Verify the registry port, RMI server port, and advertised hostname.
- Never hard-code credentials in source or shell history when proper secrets management is available.
- Verify Docker/Kubernetes networking, NAT, DNS, and port forwarding.

An open TCP port does not prove a remote JMX client can successfully call `getAttribute`. Test end-to-end against the exact ObjectName.

## 14. JMX Clients and Servers on Different JDKs

For example:

```text
Client JDK 17 -> Server JDK 21
Client JDK 21 -> Server JDK 17
```

In principle, JMX Remote is designed for interoperability, though practical results depend on:

- Connector protocol and provider.
- TLS cipher/certificate policies.
- Authentication setup.
- Client classpath.
- Serialization of return types.
- MXBean/OpenMBean types.
- Features/attributes available only on newer JDKs.

An older JDK client should not assume it understands every new MXBean attribute on a newer JDK server. Nor should clients be forced onto the exact server JDK when current APIs/connectors support cross-version communication.

Verify the client/server pairs **actually present in operations**.

## 15. Serialization and MXBean/Open Data

A management operation returning an internal object:

```java
public InternalJobSnapshot getJobSnapshot();
```

may work locally yet fail remotely because the client JVM lacks the class or has a different serialization schema.

To reduce risk when upgrading JDK/Spring:

- Prefer primitives, wrappers, `String`, `ObjectName`, and JMX Open Types.
- For complex data, consider MXBeans to represent values via `CompositeData`/`TabularData`.
- Avoid exposing internal domain entities directly over remote JMX.
- Keep field names, types, and units compatible.
- Test actual deserialization from an external client JVM.
- Avoid Java-serialized classes tied to implementation details when clients span multiple languages or versions.

An `MBeanInfo` with valid metadata does not guarantee every remote client can process the payload successfully.

## 16. Spring AOP Proxies Can Change the JMX Surface

When changing Spring versions or enabling new advisors, a bean may be exposed via a JDK dynamic proxy or a class-based proxy.

```text
Business target
    |
    v
Spring AOP proxy
    |
    v
MBeanExporter / JMX metadata assembler
```

With JDK proxies, methods must exist on an exposed interface for callers to invoke them normally through the proxy. With class-based proxies, more class methods can be exposed, though `final`/`private` methods still have limits.

If the metadata source reads annotations on the target while the exported object is a proxy, an annotated method may still fail to invoke if the proxy interface lacks that method.

A controllable architectural solution:

```text
JMX Management Adapter (stable contract)
        |
        v
Business Service Interface / Spring AOP proxy
        |
        v
Target implementation
```

The adapter keeps `ObjectName` and attribute/operation contracts independent of the service's proxy mode. Still, run integration tests to confirm the call path preserves transaction/security advice.

## 17. Notification Compatibility

If an MBean emits notifications:

```text
com.example.orders.queue.overloaded
```

clients may use `NotificationFilterSupport` to receive only that type.

If an upgrade changes the notification type, source, or userData schema, old listeners may stop working.

Verify:

- Does `MBeanInfo.getNotifications()` still include old types?
- Does `NotificationListener` still receive callbacks when events trigger?
- Have `sequenceNumber` or source semantics changed?
- Does the remote connector deliver notifications over the connection?
- When a client reconnects after downtime, does it check state directly instead of assuming all notifications are reliably delivered?

JMX notifications are not a durable/exactly-once queue; do not rely on them as the sole audit source after an upgrade.

## 18. Testing Lifecycle and Duplicate Registrations

Spring exporters typically register MBeans on context startup and clean them up on context close. After upgrading, verify:

```text
Before context refresh: isRegistered = false
After context refresh:  isRegistered = true
After context close:    isRegistered = false
```

If multiple Spring contexts or exporters run in the same JVM:

- Uncleaned old MBeans can cause `InstanceAlreadyExistsException`.
- `RegistrationPolicy.IGNORE_EXISTING` can prevent the new context from exporting its MBean while clients still see the old object.
- `REPLACE_EXISTING` can overwrite another component's MBean if ownership is unclear.
- An annotation exporter and a manual exporter can double-register the same ObjectName.

Establish clear naming conventions and ownership; avoid random UUIDs just to dodge name collisions.

## 19. Upgrade Matrix to Verify

| Axis | Examples | Purpose |
| --- | --- | --- |
| JDK runtime | Current JDK, target JDK | Detect platform MBean and module access changes |
| Spring Framework | Current version, target version | Exporter/annotation/proxy lifecycle |
| Spring Boot (if used) | Current version, target version | Auto-configuration and JMX enablement |
| Management client | Current JConsole/JMC/agent | Check UX and client classes |
| Network environment | Local, staging, container, remote | RMI hostname/ports/TLS |
| MBean type | Standard MBean, MXBean, ModelMBean | Metadata and serialization |
| Access mode | Local, remote read, remote invoke | Contract and transport |
| Lifecycle | Startup, redeploy, shutdown | Registration/unregistration |
| Load | Normal polling, multiple collectors | Latency and stability |

You do not need to test combinations that do not exist in practice; prioritize the JDK/Spring/client pairs and deployment configurations currently or soon to be operated.

## 20. Implementing Tests Across Levels

### Level A: Unit Tests Without Remote JMX

Verify:

- ObjectNames produced by naming strategies are accurate.
- Java management interfaces are stable.
- Business logic is properly called by management adapters.
- Name parsing/canonicalization works properly.
- Simple data types did not change unintentionally.

### Level B: Integration Tests with Spring + Real MBeanServer

Use a dedicated server:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("test.management");
```

Start the Spring context containing the exporter, then verify:

```java
assertTrue(server.isRegistered(expectedObjectName));
MBeanInfo info = server.getMBeanInfo(expectedObjectName);
```

Then check attributes, operations, notifications, and lifecycle.

### Level C: Remote Connector Integration Tests

Start a secured test JMX connector in an isolated environment and connect from an external client JVM:

```java
try (JMXConnector connector =
         JMXConnectorFactory.connect(serviceUrl, env)) {

    MBeanServerConnection conn =
        connector.getMBeanServerConnection();

    assertTrue(conn.isRegistered(expectedObjectName));
    Object value = conn.getAttribute(
        expectedObjectName, "PendingCount"
    );
}
```

Verify connection success, metadata, invocation, and cleanup. Never use an unsecured production connector as a test lab.

### Level D: Canary/Staging Smoke Tests

Use the real target JDK/framework in a production-like deployment environment. Verify dashboards, monitoring agents, JConsole/JMC, and runbooks before broad rollout.

## 21. Recommended Upgrade Process

```text
1. Inventory current JMX contracts / endpoints / clients
                  |
                  v
2. Save baseline ObjectName + MBeanInfo
                  |
                  v
3. Upgrade JDK / Spring in test environment
                  |
                  v
4. Run unit + Spring integration + remote tests
                  |
                  v
5. Compare metadata, behavior, notifications
                  |
                  v
6. Validate TLS, auth, ports, DNS, container networking
                  |
                  v
7. Deploy canary and observe metrics/logs
                  |
                  v
8. Rollout gradually with rollback plan
```

During an upgrade, if a breaking change is detected, determine:

- Was the change intentionally designed?
- Which clients depend on the old contract?
- Can an alias or old signature be kept?
- Is a versioned ObjectName or dedicated management adapter needed?
- Can the application/JDK image be rolled back?
- Which operational docs and runbooks need updating?

Do not turn a contract bug into a client burden by “editing dashboards to match” without assessing the impact on other scripts and agents.

## 22. Distinguishing API Behavior from Deployment Environment

An issue appearing after a JDK upgrade is not necessarily a JMX API problem:

| Symptom | Where to investigate |
| --- | --- |
| `InstanceNotFoundException` | ObjectName, MBeanServer, exporter lifecycle |
| `InstanceAlreadyExistsException` | Duplicate exporter, registration policy, stale context |
| `NotCompliantMBeanException` | Standard MBean convention, assembler/proxy |
| `ReflectionException` on invoke | Operation signature and method exposure |
| `InaccessibleObjectException` | Java module encapsulation, reflection libraries |
| `NoClassDefFoundError` | Dependency/classpath/module changes |
| Remote connection refused | Port/firewall/connector not started |
| RMI lookup succeeds but call fails | RMI stub hostname/port, NAT/container |
| TLS handshake fails | Cipher/certificate/protocol policies |
| Deserialization fails | Type schema/classpath/client-server mismatch |
| GC metrics change | Different collector or MBean implementations |
| MBean still visible but values look "wrong" | Changed semantics/units or metric source |

Use startup logs, classpath inspection, JVM flags, `MBeanInfo`, controlled network traces, and isolated tests to narrow down the cause.

## 23. Hands-on Exercises

1. Create a Spring MBean `com.example.orders:type=Queue,name=Payment` and save the baseline ObjectName + `MBeanInfo`.
2. Run the same test across two JDK versions supported by your project; compare `java.lang` MXBeans and application MBeans.
3. Switch Spring proxy mode from JDK to class-based; check whether metadata and operation invocations differ.
4. Change `int getPendingCount()` to `long` and observe the contract test catching the breaking change.
5. Run an external remote client on a different JVM version than the server and test `getAttribute`/`invoke`.
6. Deliberately use a custom `MBeanServer` while connecting to the platform connector; explain why the MBean does not appear.
7. Inspect `java.lang:type=GarbageCollector,*` before and after switching GC; explain why collector names may differ.
8. Create a test starting/closing contexts repeatedly to detect MBean leaks or duplicate registrations.
9. Design a canary checklist for a JDK/Spring upgrade in an application with multiple monitoring agents.
10. Write a migration plan for an existing operation whose signature changed in a new Spring or application version.

## 24. Self-Check Questions

- Why does passing service unit tests not guarantee the JMX contract remains compatible?
- What critical information does `MBeanInfo` provide when comparing two versions?
- Why can platform GC MBean names differ after a JDK upgrade?
- Is a local JMX test sufficient to verify remote connectors/TLS?
- When `@ManagedResource` is still present yet the MBean disappears, what should you check?
- Why is the client JDK version not necessarily the server JDK version?
- Should `--add-opens` flags be added wholesale on reflection errors?
- When must older clients be supported during a rolling upgrade?
- Why is a contract baseline needed independent of the build under test?
- How must a rollback plan account for MBean management and monitoring?

**Key takeaway:** Upgrading the JDK or Spring Framework can affect JMX across registration, metadata, proxies, module access, serialization, and remote connectors. To upgrade safely, capture a baseline from the running version, verify the contract via `MBeanInfo`, test locally and remotely across real client/server JDK pairs, and deploy via canary with a rollback plan.
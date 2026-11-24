# Distinguishing Spring Context Errors from JMX Runtime Errors

## 1. Objectives

When a Spring Framework application uses JMX, the exact same symptom—"MBean not visible", "cannot read attribute", or "application fails to start"—can originate from completely different layers. An error can occur when Spring builds the ApplicationContext, when MBeanExporter registers a bean, when MBeanServer processes an invocation, or when a remote client connects through a JMX connector.

Effective diagnostics begin with the question: **When did the error occur, at which layer, and which component actually threw the exception?** Without isolating the right layer, operators easily apply the wrong fix: increasing client timeouts while the Spring bean was never created, enabling registration replacement to hide an ObjectName conflict, or disabling TLS just because JConsole cannot connect.

This lesson focuses on:
- Distinguishing Spring context errors, JMX export/registration errors, JMX runtime errors, and remote connector errors.
- Recognizing exceptions and when they arise.
- Tracing the cause chain of \`BeanCreationException\` to find the root cause.
- Inspecting MBeanExporter, MBeanServer, and ObjectName instead of looking only at JConsole.
- Using \`MBeanInfo\`, \`isRegistered\`, \`queryNames\`, and logs to isolate the incident.
- Separating errors caused by beans, AOP proxies, annotations, operations, serialization, permissions, and connectivity.
- Designing a runbook usable across development, CI, and production.

## 2. The Four-Layer Model

\`\`\`text
LAYER A — SPRING CONTEXT
  @Configuration / component scan / bean conditions
    |
    +-- BeanDefinition / Dependency Injection
    +-- BeanFactory / BeanPostProcessor
    +-- AOP proxies
    +-- Context refresh / destroy
    |
    v
LAYER B — JMX EXPORT
  MBeanExporter / AnnotationMBeanExporter
    |
    +-- select beans
    +-- read metadata / MBeanInfoAssembler
    +-- generate ObjectName
    +-- registerMBean
    |
    v
LAYER C — JMX RUNTIME
  MBeanServer
    |
    +-- registry ObjectName -> MBean
    +-- getAttribute / setAttribute
    +-- invoke / queryNames
    +-- notification listener
    |
    v
LAYER D — REMOTE CONNECTOR / CLIENT
  JMXConnectorServer <-> JMXConnector
    |
    +-- Service URL / DNS / firewall / RMI stub
    +-- authentication / TLS
    +-- connection loss / timeout
    +-- remote serialization / callback
\`\`\`

Some exceptions traverse multiple layers as wrappers. For instance, when \`MBeanExporter\` registers an MBean during Spring refresh and \`MBeanServer\` reports \`InstanceAlreadyExistsException\`, Spring may wrap that error in \`MBeanExportException\` and ultimately \`BeanCreationException\`. Looking only at the first exception line is not enough to conclude the root cause belongs to Spring dependency injection.

Key point: **the layer where an error surfaces is not always the layer that caused it**.

## 3. Quick Differentiation Table

| Symptom | Suspected Layer | First Check |
|---|---|---|
| Context refresh fails, bean lacks dependency | Spring context | Root cause of \`BeanCreationException\` |
| Context runs, yet monitor bean is absent | Spring context | \`containsBean\`, profiles, conditions |
| Bean exists, yet is not exported | JMX export | Exporter, autodetection, annotations/assembler |
| \`InstanceAlreadyExistsException\` | JMX registration | Duplicate ObjectName in same server |
| \`NotCompliantMBeanException\` | JMX contract/export | MBean interface, MXBean, proxy, assembler |
| \`MalformedObjectNameException\` | JMX naming | Domain/key property syntax |
| MBean registered, yet attribute missing | JMX metadata | \`MBeanInfo.getAttributes()\` |
| \`AttributeNotFoundException\` | JMX runtime contract | Attribute name and read/write flags |
| \`ReflectionException\` on invoke | JMX operation dispatch | Name, signature, overload |
| \`MBeanException\` on invoke | Implementation | Cause inside managed operation |
| JConsole cannot connect | Remote connector | Service URL, network, auth/TLS |
| Registry port open, yet calls time out | RMI transport | Actual host/port inside stub |
| Client connected, yet app MBean missing | Wrong server/endpoint/naming | Which MBeanServer does the connector point to? |
| Notifications do not arrive | Listener/filter/runtime/remote | Registration, filter, lifecycle |
| MBean disappears after redeploy | Lifecycle | Exporter owner, unregister, context close |

These are hints to prioritize checks rather than absolute mappings. For example, an \`InstanceNotFoundException\` may stem from a wrong ObjectName, an MBean not yet registered, or an MBean just unregistered on context close.

## 4. Layer A: Spring ApplicationContext Errors

The Spring context is responsible for reading configuration, creating beans, injecting dependencies, and applying BeanPostProcessors. Common errors:

### 4.1 Bean is not created

Example:

\`\`\`java
@Configuration
public class MonitoringConfig {
    @Bean
    public QueueMonitor queueMonitor(QueueRepository repository) {
        return new QueueMonitor(repository);
    }
}
\`\`\`

If no matching bean exists for \`QueueRepository\`, the context may report \`UnsatisfiedDependencyException\` or \`NoSuchBeanDefinitionException\`. JMX has not yet had any chance to register the monitor.

Checklist:
1. Is the bean definition loaded?
2. Are profiles and conditions active?
3. Does component scanning cover the package?
4. Do dependencies exist and qualify for autowiring?
5. Did the factory method/constructor throw an exception?
6. Did AOP or a BeanPostProcessor fail while creating a proxy?

Resolve the Spring layer before investigating JConsole.

### 4.2 Bean exists, yet JMX is absent

\`\`\`java
boolean hasBean = context.containsBean("queueMonitor");
Object bean = context.getBean("queueMonitor");
System.out.println(bean.getClass().getName());
\`\`\`

If \`hasBean=true\`, you cannot yet assume the exporter ran. Check \`@EnableMBeanExport\` or \`MBeanExporter\`, bean mappings, annotation metadata, and MBeanServer.

If the bean is marked \`@Lazy\`, initialization lifecycle and timing may differ from expectations. Do not force-initialize every bean just to diagnose one MBean in production.

### 4.3 Exception surfaces during context refresh, yet originates from JMX

A Spring exporter may register MBeans during initialization. When registration fails, context refresh can fail too. The stack trace often spans multiple layers:

\`\`\`text
BeanCreationException: Error creating bean 'mbeanExporter'
  caused by MBeanExportException
    caused by InstanceAlreadyExistsException:
      com.example.ops:type=Worker,name=Import
\`\`\`

The failure is reported in the Spring lifecycle, while the root cause is an ObjectName already present in MBeanServer. Read the deepest \`Caused by\` entry and inspect the actual registrations.

## 5. Layer B: Bean Selection and Export Errors

\`MBeanExporter\` can export beans via explicit mappings, Standard MBean autodetection, or assembler-based autodetection. \`AnnotationMBeanExporter\` selects beans based on annotation metadata in the corresponding configuration.

There are three steps to separate:

\`\`\`text
Does bean exist in context?
         |
         v
Does exporter select bean as a candidate?
         |
         v
Are MBeanInfo / ObjectName valid?
         |
         v
Does registerMBean succeed?
\`\`\`

If the bean is skipped at the selection step, the registry has no MBean and no obvious exception may appear. If the bean is selected yet metadata is invalid, you may see \`NotCompliantMBeanException\`, a naming error, or \`MBeanExportException\`.

### 5.1 Missing or misplaced annotations

\`\`\`java
@Component
public class CacheMonitor {
    @ManagedAttribute
    public long getHitCount() {
        return 0L;
    }
}
\`\`\`

If the annotation-driven configuration requires \`@ManagedResource\` metadata on the class and the class lacks it, it may not be auto-detected. Do not solve this by enabling broad context-wide autodetection, as doing so can accidentally export other beans.

Intentional configuration:

\`\`\`java
@Component
@ManagedResource(objectName = "com.example.ops:type=Cache,name=Catalog")
public class CacheMonitor {
    @ManagedAttribute
    public long getHitCount() {
        return 0L;
    }
}
\`\`\`

An appropriate annotation exporter must be active, and actual metadata must be verified in \`MBeanInfo\`.

### 5.2 AOP proxies alter detection

When \`@Transactional\` or AOP auto-proxying is enabled, the actual bean may be a JDK dynamic proxy or a class-based proxy. The MBean interface or annotations on the target class may be seen differently by the assembler depending on the export mechanism.

\`\`\`java
Object bean = context.getBean("cacheMonitor");
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
\`\`\`

If a JDK proxy does not expose the management interface, Standard MBean detection may no longer recognize it as before. A dedicated management adapter often helps decouple the JMX surface from an AOP-proxied domain service.

Do not blindly fix this by unwrapping the target: direct calls to the target can bypass transaction, security, or audit advice provided by the proxy.

### 5.3 Duplicate exporters or duplicate ObjectNames

A context might simultaneously enable \`@EnableMBeanExport\`, XML export, and \`@Bean MBeanExporter\`. If two exporters register the same ObjectName, one registration will collide. Establish a single owner per registration and avoid arbitrarily using a replace policy.

How to scan for exporters:

\`\`\`java
String[] exporters = context.getBeanNamesForType(
    MBeanExporter.class, true, false);
System.out.println(Arrays.toString(exporters));
\`\`\`

Two exporters are not automatically an error if their MBean sets are disjoint. Conversely, even a single exporter can fail if two beans share an ObjectName.

## 6. Layer C: JMX Runtime Errors

Once an MBean is registered, the JMX runtime determines which attributes and operations are available. A Java method may exist yet not belong to the management interface or not be published by the metadata assembler.

### 6.1 Checking the right MBeanServer

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.ops:type=Worker,name=Import");

System.out.println(server.isRegistered(name));
\`\`\`

This checks the platform MBeanServer. If the Spring exporter uses a custom server, pass that exact server; do not check the platform server and conclude the MBean is missing.

### 6.2 Right ObjectName, yet wrong members

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName() + " read=" + a.isReadable()
        + " write=" + a.isWritable());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
\`\`\`

\`MBeanInfo\` is the real verification source for the contract published by MBeanServer. If \`getAttribute(name, "QueueDepth")\` hits \`AttributeNotFoundException\`, verify the exact spelling/case of the attribute name and whether it appears in \`MBeanInfo\`.

### 6.3 Method exists in Java, yet is not published

A Standard MBean only publishes members belonging to its management interface. Annotation-driven export depends on metadata. Thus, calling:

\`\`\`java
connection.invoke(name, "deleteInternalState",
    new Object[0], new String[0]);
\`\`\`

can fail if \`deleteInternalState\` is a public Java method outside the JMX contract. This may be proper security design rather than a Spring context error.

### 6.4 Wrong operation signature

\`\`\`java
connection.invoke(
    name,
    "setThreshold",
    new Object[]{Integer.valueOf(10)},
    new String[]{"int"}
);
\`\`\`

In \`invoke\`, the signature describes **the declared parameter types of the operation**, not the runtime types of wrapper objects inside \`Object[]\`. If the operation accepts primitive \`int\`, the signature is typically \`"int"\`, not \`"java.lang.Integer"\`. With overloads, fetch the signature from \`MBeanOperationInfo\`.

A mismatched call can result in \`ReflectionException\` or a dispatch-related exception. Do not modify the Java method if the mistake lies solely in the client signature.

## 7. When the Managed Method Itself Throws an Exception

Suppose:

\`\`\`java
@ManagedOperation
public void requestRefresh() {
    if (refreshRunning) {
        throw new IllegalStateException("Refresh already running");
    }
    startRefresh();
}
\`\`\`

If the JMX invocation reaches the right MBean and operation yet the implementation throws an exception, the client may receive \`MBeanException\` or \`RuntimeMBeanException\` depending on the exception type and handling path. Inspect the cause instead of blaming the connector.

Distinguish:
- **JMX dispatch cannot find the method:** fix the operation name/signature or export contract.
- **Method is invoked, yet logic rejects it:** check preconditions/state and application exceptions.
- **Method runs and client times out:** it is uncertain whether the side effect completed.
- **Async operation returns an ID:** poll task status rather than relying solely on the initial response.

For production control actions, never blindly retry after a timeout: the request may have executed while the response was lost.

## 8. Attribute Errors Caused by Heavy-I/O Getters

A getter in JMX is not a static property; it can run arbitrary Java code:

\`\`\`java
@ManagedAttribute
public long getPendingOrders() {
    return repository.countPending();
}
\`\`\`

If the database is slow, \`getAttribute\` becomes slow or fails. This differs from an unregistered MBean. When \`server.isRegistered(name)=true\` yet reading the attribute hangs, investigate getter logic, DB timeouts, lock contention, and polling rates.

A common remedy is a cached snapshot or pre-updated counter, moving heavy computation to a background refresh with timeouts. Avoid increasing JMX client timeouts while letting getters continue holding DB connections or server threads.

## 9. Layer D: Connector, Client, and Transport

An MBean can work completely fine when called locally via MBeanServer yet remain unreachable remotely.

\`\`\`text
Local JMX call: OK
       |
       v
JMXConnectorServer
       |
       +-- RMI registry / stub
       +-- DNS / firewall
       +-- authentication / TLS
       +-- connector lifecycle
       |
       v
Remote JMX client: FAILED
\`\`\`

Common causes:

| Remote Symptom | Possible Cause |
|---|---|
| Connection refused | Wrong host/port, connector not started |
| Registry lookup OK, yet invoke fails | RMI stub advertises an unreachable endpoint |
| Authentication failed | Wrong credentials or server policy |
| SSLHandshakeException | Truststore, certificate, TLS mismatch |
| MalformedURLException | Invalid JMXServiceURL syntax |
| IOException after running for a while | Network/server restart or closed connector |
| Client sees JVM metrics, misses app MBean | Exporter uses another server or wrong ObjectName |

In JMX RMI, registry lookup and connector endpoint can use different hosts/ports. Opening the registry port alone is not enough to prove the remote JMX path works end-to-end.

### 9.1 Never fix errors by disabling security

When encountering authentication/TLS failures, do not turn off:

\`\`\`text
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
\`\`\`

on endpoints reachable from untrusted networks. Fix credentials, certificate trust, hostnames, and network policies instead. Spring \`@ManagedResource\` does not secure the connector on its own.

## 10. Diagnostic Decision Tree

\`\`\`text
Did the application start up successfully?
 ├── NO
 │    |
 │    +-- Root cause is dependency/bean/profile?
 │    |      └── SPRING CONTEXT ERROR
 │    |
 │    +-- Root cause is MBeanExportException/JMException?
 │           └── JMX EXPORT / REGISTRATION ERROR
 │
 └── YES
      |
      +-- Is the managed bean in ApplicationContext?
      |      ├── NO -> Bean scan/condition/definition
      |      └── YES
      |           |
      |           +-- Does the right MBeanServer register the ObjectName?
      |                  ├── NO -> Exporter/naming/registration
      |                  └── YES
      |                       |
      |                       +-- Does local getAttribute/invoke succeed?
      |                              ├── NO -> Runtime contract/logic
      |                              └── YES
      |                                   |
      |                                   +-- Does remote connector work?
      |                                          ├── NO -> URL/network/TLS/auth
      |                                          └── YES -> Client ObjectName,
      |                                                   signature, rights,
      |                                                   timing/lifecycle
\`\`\`

This tree prevents jumping straight to network debugging when the context does not even contain the MBean.

## 11. Real-World Example: Context Refresh Fails Due to Duplicate ObjectName

Configuration:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfig {
    @Bean
    public AnnotationMBeanExporter anotherExporter() {
        return new AnnotationMBeanExporter();
    }
}
\`\`\`

Depending on infrastructure bean registration and Spring version, this configuration can create overlapping export paths. If two exporters register the same MBean under the same ObjectName, a collision occurs.

A stack trace might look like:

\`\`\`text
BeanCreationException
  └── MBeanExportException
       └── InstanceAlreadyExistsException
\`\`\`

Classification: the failure surfaces during **Spring context refresh**, yet the root cause belongs to **JMX registration**. The fix is to choose one primary annotation export path, or separate exporter scopes clearly; do not default to registration replacement.

## 12. Real-World Example: MBean Disappears After Enabling @Transactional

Before the change, the target class implemented \`WorkerStatusMBean\` and the exporter recognized the Standard MBean. After adding transaction advice, the bean may become a JDK dynamic proxy and no longer expose the management interface as configured.

Symptoms:
- Spring \`containsBean("workerStatus")=true\`.
- \`AopUtils.isAopProxy(bean)=true\`.
- \`server.isRegistered(name)=false\`.
- Exporter logs may indicate the bean is ineligible or failed registration.

Diagnosis:
1. Identify the proxy interfaces.
2. Inspect the exporter/assembler in use.
3. Confirm whether the management interface is exposed by the proxy.
4. If needed, use a dedicated management adapter calling the Spring service through its proxy.
5. Verify MBeanInfo after the change.

Do not bypass the proxy by arbitrarily registering the raw target: transaction/security advice can be skipped when JMX invokes the target directly.

## 13. Real-World Example: Local OK, Remote Misses the MBean

Suppose:

\`\`\`java
MBeanServer customServer = MBeanServerFactory.createMBeanServer(
    "com.example.private");
exporter.setServer(customServer);
\`\`\`

Meanwhile, the JMX connector serves the platform MBeanServer. Local code calling \`customServer.isRegistered(name)\` returns true, yet JConsole on the platform connector does not see the bean.

This is neither a Spring bean bug nor a metadata bug. The issue is that the exporter and the connector point to **two different MBeanServers**.

Fixes:
- Use the same server reference if you intend to publish the bean through that connector.
- Or create a dedicated connector for the custom server with proper networking/security.
- Do not indiscriminately duplicate MBeans into another registry just to "make them show up in JConsole".

## 14. Real-World Example: Attribute Exists Yet Always Times Out

\`MBeanInfo\` shows attribute \`PendingJobs\` is published. The client can query the MBean, yet \`getAttribute\` times out.

This situation usually belongs to the runtime getter:
- Getter waits on a SQL query.
- Getter acquires a lock held by a worker thread.
- Getter calls a failing HTTP health endpoint.
- Getter serializes excessively large data.
- Monitoring agents poll concurrently, causing a stampede.

Check local call latency, dependency metrics, thread dumps, and server-side timeouts. If a remote client times out, do not assume the server stopped executing the getter.

## 15. Using MBeanInfo to Verify the Contract

After confirming the right MBeanServer and ObjectName:

\`\`\`java
import javax.management.*;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("attribute=" + attribute.getName()
        + ", readable=" + attribute.isReadable()
        + ", writable=" + attribute.isWritable());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("operation=" + operation.getName());
}
\`\`\`

Do not assume a Java getter named \`getQueueDepth()\` will inevitably show up verbatim as an operation: in JMX it is typically the attribute \`QueueDepth\`. If management interfaces/assemblers differ, the exposed member set differs too. MBeanInfo reflects the exact runtime contract published at that moment.

Also inspect members that should **not** be exported. An inadvertently exposed sensitive operation is a security issue, not merely a diagnostic bug.

## 16. Notifications: Distinguishing Filter Errors from Emitter Errors

A notification listener may miss events because:
- The MBean did not emit a notification.
- The listener registered on the wrong ObjectName.
- A filter rejected the event.
- \`handback\` was confused with \`userData\`.
- The listener was removed when the context closed.
- The remote connection dropped.
- An asynchronous callback had not finished executing.

How to diagnose:
1. Check \`MBeanInfo.getNotifications()\` for metadata.
2. Test the emitter locally with an unfiltered listener.
3. Add the filter back and test positive/negative events.
4. Use \`CountDownLatch\` or a controlled executor instead of arbitrary sleeps.
5. If local works while remote fails, shift focus to connector/transport.
6. Upon reconnect, re-read current state because notifications are not stored and replayed by default.

Do not treat notification metadata as proof that callbacks ran; test both separately.

## 17. Layered Logging

When investigating in development/test, enable appropriate logging:

\`\`\`properties
logging.level.org.springframework.beans=DEBUG
logging.level.org.springframework.jmx=DEBUG
logging.level.org.springframework.aop=DEBUG
\`\`\`

This is Spring Boot property syntax; for plain Spring Framework, configure the project's logging framework accordingly. Do not leave full DEBUG enabled long-term in production if log volume is high or sensitive data might appear.

Useful details:
- Which Spring context is refreshing?
- Which bean failed to instantiate?
- Which exporter registered the ObjectName?
- Which MBeanServer was chosen?
- What is the exception cause chain?
- Which registry is the connector server serving?
- Which Service URL did the client connect with?
- Timing of shutdown or redeploy?

Never log passwords, access tokens, keystore secrets, or sensitive raw payloads.

## 18. Exception-to-Resolution Mapping

| Exception or State | Typical Origin Layer | Resolution |
|---|---|---|
| \`NoSuchBeanDefinitionException\` | Spring bean lookup | Check scan/condition/definition |
| \`UnsatisfiedDependencyException\` | Spring injection | Check dependencies, qualifiers |
| \`BeanCreationException\` | Initialization wrapper | Inspect deepest cause |
| \`MBeanExportException\` | Spring JMX exporter | Inspect nested JMException |
| \`NotCompliantMBeanException\` | JMX contract | Fix MBean interface/metadata/proxy |
| \`InstanceAlreadyExistsException\` | Registry | Resolve ObjectName/owner |
| \`MalformedObjectNameException\` | Naming | Fix domain/key property syntax |
| \`InstanceNotFoundException\` | Registry/runtime | Verify right ObjectName/server/lifecycle |
| \`AttributeNotFoundException\` | MBean contract | Read MBeanInfo |
| \`ReflectionException\` | Operation dispatch | Check name/signature |
| \`MBeanException\` | Implementation checked exception | Read target exception |
| \`RuntimeMBeanException\` | Implementation runtime exception | Read target exception |
| \`IOException\` | Remote transport or other I/O | Identify layer and call state |
| \`SecurityException\` | Auth/authorization | Check permissions and connector |
| \`SSLHandshakeException\` | TLS handshake | Check cert/trust/protocol/hostname |

An exception class alone is insufficient to prove the full cause. Timing, call path, cause chain, and target server determine the right fix.

## 19. Troubleshooting Runbook

### Step 1 — Scope the incident

- Confirm JVM, node/instance, ApplicationContext, and environment.
- Confirm whether the symptom occurs at startup, during local operations, or remotely.
- Capture the exception cause chain and timestamp.
- Do not change security settings or retry destructive operations while the cause is unclear.

### Step 2 — Verify the Spring context

- Did the context refresh successfully?
- Does the managed bean exist?
- Is the bean proxied, and which interfaces does the proxy expose?
- Was the exporter created, and what is its export mode?

### Step 3 — Verify JMX registration

- Which MBeanServer does the exporter use?
- What ObjectName was generated?
- Is \`isRegistered(name)\` true?
- Are there duplicate registrations or stale entries?
- Does MBeanInfo have the expected attributes, operations, and notifications?

### Step 4 — Verify runtime behavior

- Do local \`getAttribute\` or \`invoke\` calls succeed?
- Does the getter involve heavy I/O/locking?
- Does the operation throw an exception or return a rejection state?
- Are listener/filter accurate and did the callback complete?

### Step 5 — Verify the connector

- Are Remote Service URL, registry host, and RMI endpoint right?
- Are auth/TLS/truststore/hostname valid?
- Do firewalls/DNS/NAT allow all required ports?
- Does the connector point to the right MBeanServer?
- Is the remote client calling the right ObjectName and signature?

### Step 6 — Verify after fixing

- Spring context starts up cleanly.
- MBean exists on the right server.
- MBeanInfo reflects the expected contract.
- Read-only attributes respond with reasonable latency.
- Control operations are tested in a safe environment.
- Context shutdown leaves no stale MBeans and does not remove unrelated registrations.

## 20. Layered Integration Testing

A useful fixture starts a Spring context with a dedicated test MBeanServer and verifies:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxLayeringTest {

    @Test
    void beanAndMBeanAreBothPresent() throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     MonitoringTestConfiguration.class)) {

            assertTrue(context.containsBean("workerMonitor"));

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                "com.example.test:type=Worker,name=Import");

            assertTrue(server.isRegistered(name));
            assertNotNull(server.getMBeanInfo(name));
        }
    }
}
\`\`\`

\`MonitoringTestConfiguration\` in the example is a project-defined fixture providing the right beans, exporter, and MBeanServer. The test above has no remote connector; it verifies the Spring and local registration layers. To test remote access, write a separate integration test starting a test connector with appropriate authentication/TLS.

### 20.1 Negative contract test

Besides asserting required MBeans are present, confirm unintended MBeans are absent:

\`\`\`java
ObjectName forbidden = new ObjectName(
    "com.example.test:type=InternalService,name=Payment");

assertFalse(server.isRegistered(forbidden));
\`\`\`

This catches overly broad exporter autodetection, especially after adding a new starter or configuration module.

### 20.2 Lifecycle test

Create the context, assert registration; close the context; assert registrations owned by the exporter are removed. If sharing the platform server with other tests, do not use domain wildcards to bulk-unregister. A context must not delete MBeans it did not register.

## 21. Common Misconceptions

**"BeanCreationException is always a Spring DI error."** No. It can wrap a JMX registration error occurring during context refresh.

**"If the bean exists, JMX must see it."** No. You need an exporter, selection, metadata, naming, and registration.

**"If the MBean shows up in JConsole, the Spring context is definitely healthy."** No. The MBean could be a stale registration or reflect only part of the application.

**"If local JMX is OK, remote JMX is definitely OK."** No. Remote also involves the connector, TLS, auth, network, and serialization.

**"JConsole not seeing the bean means an annotation error."** No. It could be the wrong MBeanServer or ObjectName.

**"AttributeNotFoundException means the Java getter is missing."** No. The getter may exist yet fall outside the JMX management contract.

**"A timeout means the operation never ran."** No. Side effects may already have taken place.

**"Changing registration policy to replace fixes the error."** It can hide an ownership conflict and cause lifecycle bugs.

**"MBeanInfo having a notification type means an event was emitted."** No. Metadata does not prove delivery.

## 22. Applied Exercises

**Exercise 1 — Wrapped exception.** Context startup fails with \`BeanCreationException -> MBeanExportException -> InstanceAlreadyExistsException\`. Identify the origin layer and how to fix ownership/ObjectName.

**Exercise 2 — Bean present, MBean absent.** \`containsBean=true\`, \`isRegistered=false\`. List the steps to check the exporter, autodetection, proxy, metadata, and naming.

**Exercise 3 — Remote missing MBean.** Local \`customServer.isRegistered(name)=true\`, JConsole does not see it. Prove the connector points to another server and propose a fix.

**Exercise 4 — Failing attribute.** \`MBeanInfo\` has attribute \`PendingJobs\`, yet \`getAttribute\` times out. Explain why this is not simply a Spring context error and how to measure the getter/dependency.

**Exercise 5 — Operation signature.** The method takes primitive \`int\`, yet the client passes signature \`java.lang.Integer\`. Fix it and verify metadata.

**Exercise 6 — Notifications.** A listener receives no events; distinguish emitter not sending, filter rejecting, listener not registered, and remote disconnect.

**Exercise 7 — AOP.** After enabling \`@Transactional\`, the MBean disappears while the Spring bean remains. Propose checks for proxy interfaces and a management adapter.

## Summary

Distinguishing Spring context errors from JMX runtime errors means distinguishing **when and at which layer the incident arises**. The Spring context creates beans and applies proxies; the exporter selects beans, builds metadata, and registers them; MBeanServer enforces the management contract; the connector serves remote clients. A surface-level Spring exception can wrap a deep JMX error, so always read the root cause. An effective diagnostic flow inspects sequentially: **context → exporter → MBeanServer → local runtime → remote connector**, using \`MBeanInfo\` and ObjectName checks to avoid guesswork. Once the right layer is identified, the fix is small, safe, and avoids risky measures like disabling security or replacing another component's MBeans.

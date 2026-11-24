# Reading Exporter, MBeanServer, and Connector Logs to Isolate Spring Framework JMX Incidents

## Learning Objectives

In a Spring Framework JMX application, JConsole failing to see an MBean or a remote client failing to invoke an operation can originate from multiple layers: the Spring bean was not created, \`MBeanExporter\` did not register it, the \`ObjectName\` is wrong, the \`MBeanServer\` is wrong, the MBean lacks metadata, or the remote \`JMXConnectorServer\` is not running. Looking only at one final exception and changing configurations randomly prolongs troubleshooting and can introduce new bugs.

This lesson belongs to the **Troubleshooting** section of Spring Framework JMX. After this lesson, you will be able to:

- Separate failures across the layers **Spring context → exporter → MBeanServer → connector → JMX client**.
- Enable and read appropriate logging for the Spring JMX exporter, Spring container, JDK JMX/RMI, and application components.
- Use indicators such as \`ObjectName\`, server identity, PID, endpoint, timestamp, and correlation IDs to correlate logs.
- Understand common exceptions: \`InstanceAlreadyExistsException\`, \`NotCompliantMBeanException\`, \`InstanceNotFoundException\`, \`AttributeNotFoundException\`, \`ReflectionException\`, RMI connection errors, and authentication errors.
- Verify conclusions drawn from logs using the \`MBeanServer\` API instead of relying entirely on JConsole.
- Write a safe, reproducible investigation procedure with clear isolation steps and root-cause conclusions.

## 1. Map of Layers to Observe

\`\`\`text
Spring ApplicationContext
    |
    | Bean creation / dependency injection
    v
Managed Spring bean
    |
    | MBeanExporter, assembler, naming strategy
    v
MBean registration
    |
    | ObjectName -> MBean
    v
MBeanServer
    |
    +-- Local client: MBeanServerConnection
    |
    +-- JMXConnectorServer
            |
            | RMI / transport / authentication
            v
       Remote JMX client (JConsole, custom client)
\`\`\`

Each layer exhibits distinct signals:

| Layer | Question | Source of Evidence |
| --- | --- | --- |
| Context | Was the Spring bean created and is the context still running? | Startup logs, bean definitions, dependency failures |
| Exporter | Is an exporter active and is the bean in the export mapping? | Spring JMX exporter logs, configuration |
| Naming | What is the final \`ObjectName\`? | Naming strategy logs, \`queryNames\` |
| Registry | Does the MBean exist in the right server? | \`isRegistered\`, \`getMBeanInfo\` |
| JMX contract | Are attributes/operations published? | \`MBeanInfo\`, exceptions |
| Connector | Did the remote endpoint start and bind to the right host/port? | Connector startup logs, socket diagnostics |
| Client | Is the client connecting to the right JVM, credentials, and URL? | Client logs, PID, JMX service URL |
| Runtime | Does the operation execute and respond properly? | App logs, result/exception, metrics |

**Diagnostic principle:** always start by proving the state at the layer closest to the suspected failure. If \`server.isRegistered(name)\` is \`false\` on the server used by the exporter, fixing the RMI connector will not make the MBean appear in the registry. If the local API reads the MBean successfully while the remote client fails, focus on the connector/transport/security instead of editing exporter metadata.

## 2. Three Key Failure Types to Distinguish

### 2.1. Registration errors

For example, the Spring context starts up, yet the MBean is not registered due to a duplicate name or an invalid implementation.

\`\`\`text
ApplicationContext -> MBeanExporter -> MBeanServer
                                    X registerMBean
\`\`\`

Indicators: startup exceptions or exporter logs, \`isRegistered\` not matching expectations.

### 2.2. Management contract errors

The MBean exists in the registry, yet lacks an attribute or operation. For example, \`getPendingCount()\` is not on the management interface, the assembler filters out the method, or the client passes the wrong operation signature.

\`\`\`text
MBeanServer: ObjectName exists
    |
    +-- getMBeanInfo succeeds
    +-- getAttribute/invoke fails
\`\`\`

Indicators: \`AttributeNotFoundException\`, \`ReflectionException\`, or unexpected metadata.

### 2.3. Remote connection errors

The MBean is registered and the local API works, yet remote clients cannot connect.

\`\`\`text
Local MBeanServer: OK
Remote JMX connector: X
Remote client: timeout / connection refused
\`\`\`

Indicators: \`IOException\`, \`ConnectException\`, RMI lookup failures, SSL handshake errors, or authentication errors. This is a different investigation area from the exporter.

## 3. Enabling Logs for the Spring JMX Exporter

When investigating, enable specific loggers rather than turning on application-wide DEBUG/TRACE. Relevant packages/classes typically include:

- \`org.springframework.jmx.export\`: \`MBeanExporter\` and export components.
- \`org.springframework.jmx.export.annotation\`: annotation metadata and annotation-based exporting.
- \`org.springframework.jmx.export.assembler\`: assemblers building management interfaces.
- \`org.springframework.jmx.export.naming\`: naming strategies.
- \`org.springframework.jmx.support\`: MBeanServer/registration support.
- \`org.springframework.beans.factory\`: bean creation and dependency wiring.
- \`org.springframework.context\`: ApplicationContext refresh, close, and lifecycle.

Example Spring Boot \`application.properties\` configuration:

\`\`\`properties
logging.level.org.springframework.jmx.export=DEBUG
logging.level.org.springframework.jmx.export.annotation=DEBUG
logging.level.org.springframework.jmx.export.assembler=DEBUG
logging.level.org.springframework.jmx.export.naming=DEBUG
logging.level.org.springframework.jmx.support=DEBUG
logging.level.org.springframework.beans.factory=INFO
\`\`\`

With Logback:

\`\`\`xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} [%thread] %-5level %logger{48} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.springframework.jmx.export" level="DEBUG"/>
    <logger name="org.springframework.jmx.support" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
\`\`\`

Exact log lines vary by Spring Framework version, logger implementation, and executed code path. Do not rely on matching a single literal log line. The goal is to obtain evidence: that the exporter initialized, which beans were evaluated, which JMX name was used, and whether any registration error occurred.

**Note:** DEBUG/TRACE can increase log volume and expose configuration details. Enable only for as long as needed, and never print credentials, secrets, or customer data.

## 4. What Information Should Logs Contain?

A diagnostic log line is generally useful when it includes:

\`\`\`text
timestamp | level | logger | thread | JVM/PID | context |
ObjectName | server identity | phase | outcome | error cause
\`\`\`

Illustrative log example:

\`\`\`text
2026-11-11T09:10:15.230Z INFO  app.jmx
pid=2145 context=orders-main phase=register
objectName=com.example.orders:type=QueueMonitor,name=primary
server=platform outcome=SUCCESS
\`\`\`

Illustrative error example:

\`\`\`text
2026-11-11T09:10:16.099Z ERROR app.jmx
pid=2145 context=orders-child phase=register
objectName=com.example.orders:type=QueueMonitor,name=primary
error=InstanceAlreadyExistsException
\`\`\`

The lines above are **illustrative application logging patterns**, not a promise that Spring emits this exact format. In real logging, use a consistent formatter/logger and avoid printing full exception messages if they could contain sensitive data.

Especially valuable fields:

- **Timestamp**: correlates startup, connector, and client events.
- **PID/JVM identity**: avoids analyzing logs from the wrong process.
- **Context ID**: distinguishes root/child contexts or restarted contexts.
- **\`ObjectName\`**: identifies the exact registration.
- **Server identity**: platform MBeanServer vs. custom server.
- **Thread name**: distinguishes startup, background worker, or JMX request threads.
- **Root cause**: exception type and relevant stack trace.
- **Correlation/request ID**: traces side-effecting operations, if provided by the application.

## 5. Reading Stack Traces: Finding the Root Cause Instead of Looking Only at Wrappers

Spring may wrap errors in exceptions such as \`BeanCreationException\`, \`MBeanExportException\`, or another lifecycle exception. For example:

\`\`\`text
BeanCreationException: Error creating bean 'mBeanExporter'
  caused by MBeanExportException: Could not register MBean
    caused by InstanceAlreadyExistsException:
      com.example.orders:type=QueueMonitor,name=primary
\`\`\`

In this case, \`BeanCreationException\` describes the impact on the context. **The root cause** is that the registry already holds that JMX name.

Another stack trace:

\`\`\`text
MBeanExportException: Unable to register bean
  caused by NotCompliantMBeanException:
    MBean class does not implement a valid management interface
\`\`\`

Here the issue is the MBean/type/metadata contract, not networking. Turning on TRACE for the RMI connector will not resolve a compliance error.

How to read it:

1. Identify the phase: startup, registration, connection, invocation, or shutdown.
2. Locate the first exception type with domain meaning.
3. Follow \`Caused by\` down to the root cause.
4. Correlate the exception with \`ObjectName\`, server, and bean.
5. Verify using the registry API or a small test.
6. Only then modify configuration/code.

Not every stack trace has complete \`Caused by\` details if logging is truncated. When logs are incomplete, configure logging/error reporting to log the full exception object and stack trace rather than only \`ex.getMessage()\`.

## 6. InstanceAlreadyExistsException Errors

\`InstanceAlreadyExistsException\` occurs when \`MBeanServer\` already holds a registration under the \`ObjectName\` that the exporter wants to use.

Common causes:

- Two \`MBeanExporter\` instances registering the same name.
- Spring XML exporter and Java Config exporter both active.
- Root context and child context sharing the platform server.
- Previous test did not close its context/unregister.
- Naming strategy producing the same name for multiple instances.
- Auto-configuration overlapping with a manual exporter.

How to verify:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

System.out.println(server.isRegistered(name));
System.out.println(server.getMBeanInfo(name).getClassName());
\`\`\`

This snippet is only valid when the exporter uses the **platform server**. If the exporter uses a custom server, inspect that exact server instead.

When a name already exists, find the registration owner before using \`REPLACE_EXISTING\`. If two instances are genuinely needed, assign distinct \`ObjectName\` values. \`IGNORE_EXISTING\` may let startup pass while clients keep reading the old MBean; it is not a general solution.

## 7. NotCompliantMBeanException and Invalid Metadata

\`NotCompliantMBeanException\` usually relates to an object failing to satisfy the MBean rules required by the JMX server, or invalidly constructed metadata.

Standard MBean example:

\`\`\`java
public interface QueueMonitorMBean {
    int getQueueDepth();
}

public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getQueueDepth() {
        return 5;
    }
}
\`\`\`

If the class does not implement the Standard MBean interface following conventions or uses incompatible methods/types, registration can fail.

Spring can also adapt a POJO into a ModelMBean via an assembler. In that case, check:

- Which \`MBeanInfoAssembler\` is attached?
- Are \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` targeting the intended members?
- Is a Spring AOP JDK proxy hiding implementation methods?
- Is there a method signature/type incompatible with JMX?
- Is the exporter receiving the exact object you think it is?

Do not try to solve this by randomly changing \`ObjectName\` if the fault stems from the management interface.

## 8. InstanceNotFoundException Errors

When a client calls:

\`\`\`java
connection.getAttribute(name, "QueueDepth");
\`\`\`

and the name does not exist in the target server, JMX may throw \`InstanceNotFoundException\`.

Causes to rule out:

1. The MBean has not been registered by the exporter.
2. \`ObjectName\` has the wrong domain or keys.
3. The client is connected to a different \`MBeanServer\`.
4. The client is connected to a different JVM.
5. The MBean was unregistered when \`ApplicationContext\` closed.
6. The naming strategy generated a different name than expected.
7. The exporter used \`IGNORE_EXISTING\`, kept another MBean, and the old owner closed, causing the name to vanish.

Use a query:

\`\`\`java
Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.orders:*"), null);

for (ObjectName n : names) {
    System.out.println(n.getCanonicalName());
}
\`\`\`

Do not guess JMX names from the Spring bean name alone. Read the final registry.

## 9. AttributeNotFoundException and ReflectionException Errors

If \`ObjectName\` exists yet an attribute is missing:

\`\`\`text
AttributeNotFoundException: QueueDepth
\`\`\`

it may be because:

- The getter is not part of the management interface.
- The assembler did not select that method.
- The \`@ManagedAttribute\` annotation was not detected.
- Attribute names are case-sensitive.
- The client targeted the wrong MBean or metadata changed.

Similarly, \`ReflectionException\` or invocation errors can arise when the method name/signature does not match.

Inspect metadata:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.println(
            attr.getName() + " " + attr.getType());
}

for (var operation : info.getOperations()) {
    System.out.println(
            operation.getName() + " "
            + java.util.Arrays.toString(operation.getSignature()));
}
\`\`\`

Example of invoking an operation with parameters:

\`\`\`java
server.invoke(
        name,
        "resizePool",
        new Object[]{8},
        new String[]{"int"});
\`\`\`

For method \`resizePool(int)\`, the JMX signature is \`"int"\`; do not change it to \`"java.lang.Integer"\` if metadata describes a primitive. Read \`MBeanOperationInfo.getSignature()\` to be certain.

## 10. Permission and Security Errors

A remote JMX connector may reject connections or invocations due to authentication, authorization, or TLS.

Indicators:

\`\`\`text
SecurityException
Authentication failed
SSLHandshakeException
Access denied
\`\`\`

Distinguish:

- **Authentication failure**: invalid or missing credentials.
- **Authorization failure**: client authenticated, yet lacks permission for the operation.
- **TLS handshake failure**: truststore/keystore/protocol mismatch.
- **Network failure**: client cannot reach the endpoint.
- **MBean operation failure**: connection and permissions succeeded, yet operation logic failed.

Do not print usernames/passwords, tokens, private keys, or the entire \`JMXConnectorFactory.connect\` environment map into logs. For security errors, logging the error category, correlation ID, and non-sensitive endpoint is sufficient for initial investigation.

## 11. Connector Errors: Connection Refused, Timeout, and RMI

A common JMX over RMI setup uses the URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://host.example:9010/jmxrmi
\`\`\`

Here the RMI registry may listen on one port while the exported RMI remote object uses another port. The client must pass both lookup and invocation. Hence there are cases where **registry lookup succeeds, yet remote invoke fails**.

Common errors:

| Indicator | Possible Cause | Inspection Action |
| --- | --- | --- |
| \`ConnectException: Connection refused\` | Wrong port, server not started, wrong bind interface | Check connector lifecycle and listening sockets |
| \`ConnectException: Connection timed out\` | Firewall, routing, unreachable host | Check network path and advertised host |
| \`NameNotFoundException: jmxrmi\` | Registry lacks \`jmxrmi\` binding | Check RMI naming and URL |
| Lookup succeeds, yet invoke fails | RMI stub advertises unreachable host/port | Check \`java.rmi.server.hostname\` and connector endpoint |
| \`SSLHandshakeException\` | Trust/keystore/protocol mismatch | Check TLS fixture and certificates |
| \`IOException\` during remote call | Connection closed, server restart, or transport error | Correlate client/server logs by timestamp |
| Client hits the wrong server | Same domain/name on another JVM | Verify JVM identity, PID, and endpoint |

**Important:** \`java.rmi.server.hostname\` is a JVM property affecting the host information advertised by RMI objects. It does not open ports, alter firewall rules, or guarantee the right address when running inside containers.

In Kubernetes/Docker, \`127.0.0.1\` inside the client container differs from \`127.0.0.1\` inside the server container. Design proper networking and advertised endpoints when testing cross-container.

## 12. Enabling JDK JMX/RMI Logging

Not all JMX/RMI logs flow through Spring's SLF4J/Logback loggers. For the JDK, diagnostic information may use \`java.util.logging\` (JUL), Java Flight Recorder, JVM management logs, or provider-specific mechanisms.

An illustrative JUL test configuration:

\`\`\`properties
handlers=java.util.logging.ConsoleHandler
.level=INFO

java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

javax.management.level=FINE
javax.management.remote.level=FINE
sun.rmi.level=FINE
\`\`\`

Launch the JVM with:

\`\`\`bash
java -Djava.util.logging.config.file=jmx-logging.properties \
     -cp target/classes com.example.Main
\`\`\`

Exact JDK/provider logger names and logged event volume **can vary across JDK versions**. Some internal JMX configurations may use other loggers, and RMI log verbosity depends on the implementation. Treat JUL as a supplemental source rather than a guarantee that every connection event will appear under one specific logger.

When debugging production, prefer enabling it in a reproduction environment or for a short window, since detailed transport logging adds overhead and contains infrastructure details.

## 13. Logging Connector Startup and Shutdown in the Application

For custom-created connectors, log clear lifecycle events:

\`\`\`java
JMXConnectorServer connector =
        JMXConnectorServerFactory.newJMXConnectorServer(
                serviceUrl, environment, mBeanServer);

try {
    connector.start();
    logger.info("JMX connector started: {}", connector.getAddress());
} catch (IOException e) {
    logger.error("JMX connector start failed", e);
    throw e;
}
\`\`\`

During shutdown:

\`\`\`java
try {
    connector.stop();
    logger.info("JMX connector stopped");
} catch (IOException e) {
    logger.error("Failed to stop JMX connector", e);
}
\`\`\`

Only log the service URL when it contains no credentials or sensitive data. Some environments use query parameters or service discovery containing data that must be masked; apply an appropriate logging policy.

In Spring, a \`JMXConnectorServer\` can be declared as a bean with \`destroyMethod="stop"\` or wrapped with \`SmartLifecycle\` to control start/stop timing. If the connector starts before the exporter, a client may connect successfully while the MBean is not yet registered. That is a timing/lifecycle error, not a transport error.

## 14. Proving the Right MBeanServer

A common mistake is checking the platform server while the exporter registers to a different custom server:

\`\`\`java
MBeanServer platform =
        ManagementFactory.getPlatformMBeanServer();

System.out.println(platform.isRegistered(name));
\`\`\`

If the exporter uses a custom \`MBeanServerFactoryBean\`, a \`false\` result on the platform server does not mean the exporter failed.

The right way is to fetch **the exact server injected into the exporter**:

\`\`\`java
MBeanServer server = context.getBean(
        "applicationMBeanServer", MBeanServer.class);

ObjectName name = new ObjectName(
        "com.example.orders:type=QueueMonitor,name=primary");

System.out.println(server.isRegistered(name));
\`\`\`

If multiple \`MBeanServer\` beans exist, use explicit qualifiers/bean names. An \`ObjectName\` is unique only within **one server**, not across all JVMs/servers. Two servers can hold the same name pointing to two different MBeans.

When a remote client views a connector, confirm which server that connector is attached to. Knowing only the PID is insufficient if a single JVM creates multiple servers.

## 15. A Structured Diagnostic Probe

You can write a small command running inside the JVM to emit required data without interacting through JConsole:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public final class JmxDiagnosticProbe {

    public static void inspect(
            MBeanServer server,
            ObjectName expected,
            String domainPattern) throws Exception {

        System.out.println("defaultDomain="
                + server.getDefaultDomain());

        System.out.println("registered="
                + server.isRegistered(expected));

        Set<ObjectName> matches =
                server.queryNames(
                        new ObjectName(domainPattern), null);

        for (ObjectName name : matches) {
            System.out.println(
                    "objectName=" + name.getCanonicalName());
        }

        if (!server.isRegistered(expected)) {
            return;
        }

        MBeanInfo info = server.getMBeanInfo(expected);

        System.out.println("class=" + info.getClassName());

        for (var attribute : info.getAttributes()) {
            System.out.println(
                    "attribute=" + attribute.getName()
                    + ",type=" + attribute.getType()
                    + ",readable=" + attribute.isReadable());
        }

        for (var operation : info.getOperations()) {
            System.out.println(
                    "operation=" + operation.getName());
        }
    }
}
\`\`\`

How to invoke:

\`\`\`java
JmxDiagnosticProbe.inspect(
        server,
        new ObjectName(
                "com.example.orders:type=QueueMonitor,name=primary"),
        "com.example.orders:*");
\`\`\`

The probe reveals: which entries exist on the inspected server, the exact names, and what the final management interface contains.

**Do not invoke side-effecting operations just to test connectivity** before understanding their behavior. Read \`isRegistered\`, \`getMBeanInfo\`, and read-only attributes first.

## 16. Distinguishing Exporter, MBeanServer, and Connector Logs

| Log Source | Focuses On | Cannot Conclude Alone |
| --- | --- | --- |
| Spring exporter | Bean selection, assembler, naming, registration | Whether remote connector is reachable |
| MBeanServer/registry probe | Registered names, metadata, attributes | Whether remote clients can traverse firewall/TLS |
| Connector startup logs | Endpoint, port, lifecycle, transport errors | Whether a specific MBean exposes the right contract |
| Client logs | URL, connect, auth, query, invoke outcome | Whether server-side operation finished after client timeout |
| Application service logs | Operation logic, database/network dependencies | Whether JMX transport connected properly |

An effective workflow correlates these sources by timestamp, rather than using a single log line to conclude the system works end-to-end.

## 17. Step-by-Step Isolation Workflow

### Step 1 — Confirm JVM and ApplicationContext

Gather PID, application name, context ID, environment/profile, and startup time. Read startup logs to check whether the context finished refreshing or hit \`BeanCreationException\`.

If the context failed to initialize, continue tracing the root cause before diving into the remote connector.

### Step 2 — Inspect the exporter

Verify whether \`MBeanExporter\` is declared or an annotation-driven exporter is enabled. Check \`beans\` mappings, autodetection, assembler, naming strategy, and registration policy.

For Spring Boot, inspect JMX auto-configuration to avoid two exporters registering simultaneously.

### Step 3 — Confirm server and ObjectName

Use \`server.isRegistered(name)\`, \`queryNames\`, and \`getMBeanInfo\` on the exact server used by the exporter. If the object is absent, focus on registration. If present yet missing methods, focus on management metadata.

### Step 4 — Inspect the connector

Verify that \`JMXConnectorServer\` started, bound to the right interface, has a usable URL, RMI registry/remote object host-ports are accurate, and credentials/TLS are configured.

### Step 5 — Test the client

Use a JMX client with the right address/credentials to read a read-only attribute or \`getMBeanInfo\`. If the client connects yet the operation fails to run, inspect signature/authorization/target exceptions.

### Step 6 — Correlate server-side and client-side logs

Match timestamps, operation names, request IDs, or job IDs. If the client times out, do not assume the server never ran. Check business state or terminal outcomes.

### Step 7 — Document the root cause

Every conclusion needs evidence like:

\`\`\`text
Symptom:
  JConsole connects, QueueDepth is missing.

Evidence:
  isRegistered(ObjectName) = true.
  MBeanInfo contains PendingCount, not QueueDepth.
  Exporter uses InterfaceBasedMBeanInfoAssembler.

Root cause:
  Management interface does not expose getQueueDepth().

Fix:
  Update the management contract deliberately; test metadata.

Verification:
  MBeanInfo now exposes QueueDepth; read-only query succeeds.
\`\`\`

Do not merely write "JMX broken" or "restarted and it went away," as that does nothing to prevent recurrence.

## 18. When Multiple ApplicationContexts or Exporters Run Together

A single JVM may host a root context, child contexts, or multiple plugin modules, all sharing the platform \`MBeanServer\`.

Common issues:

- Two exporters sharing one \`ObjectName\`.
- Old context unclosed, registration not unregistered.
- \`IGNORE_EXISTING\` preventing the new MBean from registering.
- \`REPLACE_EXISTING\` replacing the target and causing disruption when the old owner closes.
- Custom server released while another context still uses it.

To diagnose, log context ID/owner with every application-created registration. When conflicts happen, identify which exporter registered first, which policy applies, and which target instance currently sits in the registry.

Do not call \`unregisterMBean(name)\` arbitrarily in production just to "clean up" without confirming the owner. You could delete another component's MBean.

## 19. Spring Java Config Example with Clear Logging

\`\`\`java
@Configuration
public class DiagnosticJmxConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(DiagnosticJmxConfiguration.class);

    @Bean
    public MBeanServer platformMBeanServer() {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();
        log.info("Using JMX server defaultDomain={}",
                server.getDefaultDomain());
        return server;
    }

    @Bean
    public QueueMonitor queueMonitor() {
        return new QueueMonitor();
    }

    @Bean
    public MBeanExporter exporter(
            QueueMonitor queueMonitor,
            MBeanServer platformMBeanServer) {

        String objectName =
                "com.example.orders:type=QueueMonitor,name=primary";

        log.info("Preparing MBean export objectName={}", objectName);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(platformMBeanServer);
        exporter.setBeans(
                java.util.Map.of(objectName, queueMonitor));
        return exporter;
    }
}
\`\`\`

In this example, the log inside \`@Bean\` only indicates the exporter was **configured**, not that registration succeeded. Registration typically happens later in the exporter's lifecycle. To log \`REGISTERED\` accurately, observe lifecycle callbacks or check \`server.isRegistered(name)\` after the exporter finishes initialization.

In a real project, corresponding imports come from Spring context, JMX, SLF4J, and \`ManagementFactory\`; \`QueueMonitor\` is an MBean fixture conforming to the JMX contract you define.

## 20. Automated Testing for Per-Layer Failures

A good test suite should be structured by layer:

**Test 1 — Registration:** start a Spring context with the exporter and a test server, assert \`isRegistered\`.

**Test 2 — Metadata:** assert expected attributes/operations in \`MBeanInfo\`.

**Test 3 — Conflict:** attempt to create two same-named registrations on an isolated test server, verify the desired policy.

**Test 4 — Local invocation:** read a read-only attribute and invoke a safe operation via \`MBeanServer\`.

**Test 5 — Remote connector:** create a loopback \`JMXConnectorServer\` in a fixture, connect with \`JMXConnectorFactory.connect\`, and read attributes via \`MBeanServerConnection\`.

**Test 6 — Security:** with a fixture enforcing real authentication/TLS, test invalid/valid credentials and operation permissions.

**Test 7 — Shutdown:** close the context, verify the exporter unregisters its MBeans and the connector stops per owner.

These tests distinguish "broken registration" from "broken connector" without opening production endpoints for testing.

## 21. Logging in Containers and Distributed Deployments

When a Spring application runs in Docker or Kubernetes, log:

- Pod/container identity and process PID.
- Application context/profile/instance ID.
- JMX domain/\`ObjectName\`.
- Connector bind address and non-sensitive advertised host.
- Registry port and remote object port when using RMI.
- Connector start/stop timestamps.
- Error category and root cause.
- Correlation/job ID for side-effecting operations.

Do not assume \`127.0.0.1\` inside the client container is the server container's loopback. If the client connects to another container/pod hostname, the RMI stub must also advertise a host and port reachable by the client.

If the endpoint uses \`kubectl port-forward\`, recognize that RMI may use a second port, so forwarding only the registry port is sometimes insufficient. Configure connector/server ports compatible with the access path and verify in practice.

## 22. Logs and Security: Do Not Create Vulnerabilities While Debugging

During investigations, it is tempting to enable system-wide TRACE or print the entire connector environment. This can expose:

- JMX credentials.
- Keystore/truststore passwords.
- Authentication tokens.
- Sensitive internal addresses.
- Stack traces containing request data.
- Contents of attributes or operation parameters.

Rules:

1. Increase logging only on necessary packages.
2. Time-bound DEBUG/TRACE enablement.
3. Redact secrets and personal data.
4. Do not invoke dangerous operations to test connectivity.
5. Use an isolated/test environment when reproducing issues.
6. Retain sufficient evidence for analysis without posting raw logs publicly.

If an authentication error is suspected, do not fix it by disabling all authentication on a production endpoint. Use a dedicated test fixture to distinguish password, TLS, and network errors.

## 23. Quick Diagnostic Questions

| Question | If Answer Is "No" | Investigate Next |
| --- | --- | --- |
| Did Spring context initialize successfully? | Bean/exporter may be missing | Startup and bean logs |
| Was the exporter created? | No registration pipeline | IoC config, annotation enablement |
| Was the managed bean selected? | Not exported | \`setBeans\`/autodetection |
| Is \`ObjectName\` in the right server? | Registration/naming bug | Exporter and MBeanServer |
| Is \`MBeanInfo\` correct? | Interface/assembler bug | Metadata, annotations |
| Did local getAttribute succeed? | Contract or target error | Attribute name, exception |
| Has the connector started? | Remote endpoint inactive | Connector lifecycle logs |
| Did client connect succeed? | Network, RMI, auth, TLS | Client/transport logs |
| Did remote read succeed? | ObjectName/server mismatch | Client target, metadata |
| Does operation have clear outcome? | Logic blocked/failed | App logs, timeout, job status |

## 24. Hands-on Exercises

**Exercise 1 — Duplicate ObjectName:** create two exporters sharing the platform server with the same name \`com.example:type=Monitor,name=primary\`. Record the root cause and fix naming.

**Exercise 2 — Wrong server:** the exporter registers to a custom \`MBeanServer\`, yet diagnostic code reads the platform server. Compare \`isRegistered\` results and explain why JConsole may not see the custom server.

**Exercise 3 — Missing attribute:** create an MBean exposing only \`QueueDepth\`, then call \`getAttribute(name, "PendingCount")\`. Read \`MBeanInfo\` and show the fault lies in metadata/client, not transport.

**Exercise 4 — RMI connector:** create a local loopback fixture, start \`JMXConnectorServer\`, and connect with a remote client. Intentionally misconfigure the advertised hostname in the test environment to observe lookup/invoke failures.

**Exercise 5 — Context shutdown:** register an MBean, close \`ApplicationContext\`, then read the registry. Correlate with exporter unregister logs and distinguish a live server from a removed MBean.

**Exercise 6 — Timeline:** collect logs from Spring context, exporter, connector, and client; order them by timestamp and write a \`symptom → evidence → root cause → fix → verification\` report.

## Conclusion

**Reading exporter, MBeanServer, and connector logs to isolate faults** is a core skill when troubleshooting Spring Framework JMX. Split the path into concrete layers: Spring context creates beans, exporter selects/registers MBeans, server stores \`ObjectName\` and metadata, connector opens the remote endpoint, and client connects and executes calls. Combine logs with \`isRegistered\`, \`queryNames\`, \`getMBeanInfo\`, and safe reads to pinpoint which layer owns the error. A valuable conclusion always rests on evidence covering **JVM, server, ObjectName, phase, exception, and outcome**, rather than relying solely on one final error message.

# Diagnosing Missing MBeans in JMX Tools

## 1. Problem and Objectives

You have created an MBean in a Spring application and the logs report a successful startup, yet when opening **JConsole**, **VisualVM**, or another JMX tool, the expected object does not appear in the MBeans tree. The fault can lie in several independent layers: the application has not registered the MBean, registered it on a different \`MBeanServer\`, used a different \`ObjectName\`, the JMX connector is connected to the wrong JVM, access permissions are blocking it, or the UI has not refreshed.

An effective diagnostic approach works outward from **in-JVM evidence** to the **connection channel** and only then to the **UI**. Do not change ports, disable authentication, or edit annotations en masse before confirming whether the MBean is actually registered.

Lesson objectives:

1. Verify whether Spring actually exported the MBean.
2. Identify which server holds the registration.
3. Find the exact \`ObjectName\`, including domain, property keys, and quoted values.
4. Verify the connection targets the right JVM/\`MBeanServer\`.
5. Distinguish registration errors, connection errors, permission errors, and display errors.
6. Have automated verification methods using Java, Spring tests, and JMX tools.

## 2. MBean Delivery Path Model

\`\`\`text
Application bean / Management adapter
                  |
              MBeanExporter
                  |
       registerMBean(ObjectName)
                  |
              MBeanServer
                  |
       JMX local attach / connector
                  |
          JMX client connection
                  |
        JConsole / VisualVM / UI
\`\`\`

Every arrow is a boundary that requires its own evidence. If \`MBeanServer.isRegistered(name)\` returns \`false\`, refreshing the UI will not help. If it returns \`true\` yet the client still cannot see it, check **which server instance** the client is connected to.

**MBeanServer is not a JMX connector**: \`MBeanServer\` is the management registry inside the JVM; the connector routes client calls to a specific server. Opening a remote connection will not make an MBean appear if the exporter registered it on a different server.

## 3. Symptom Identification Table

| Symptom | Cause to Check First | Evidence to Gather |
| --- | --- | --- |
| MBeans tab is completely empty | Connected to wrong JVM or client lacks management access | PID, JMX URL, connection state |
| \`java.lang\` present but app MBeans missing | Exporter did not register or domain name differs | \`queryNames\`, exporter configuration |
| MBean appears in Java test but not in tool | Test uses a different server, connector, or process | \`MBeanServer\` identity, PID |
| Only one MBean is missing | Duplicate/wrong ObjectName, bean not scanned, or registration failed | Startup exceptions, \`isRegistered\` |
| MBean present but attributes/operations missing | Incorrect Standard MBean interface, MXBean mapping, or annotation metadata | \`getMBeanInfo\` |
| MBean disappears after startup | Spring context closed, exporter unregistered, bean lifecycle changed | Shutdown logs and registration over time |
| Remote connection fails | Host/port, RMI, firewall, authentication/TLS | Connection error and network configuration |
| Name lookup does not match | Wrong quoting/canonical name or pattern | \`ObjectName.getCanonicalName()\` |

## 4. First Step: Identify the Right Application and JVM

On machines with multiple JVMs, JConsole may show several processes with the same class name or JAR name. Cross-check PID, command line, and start time.

Common diagnostic commands when permitted by the JDK:

\`\`\`bash
jps -lv
jcmd <PID> VM.command_line
jcmd <PID> VM.system_properties
\`\`\`

\`jps\` or \`jcmd\` may be restricted by OS permissions, containers, PID namespaces, or attach settings. Do not assume that failing to find a PID means the application is not running.

In container/Kubernetes environments:

- A pod may contain multiple processes or a separate sidecar; host tools must target the right process namespace.
- \`localhost\` from a laptop refers to the user's machine, not automatically to the container.
- If using port-forwarding, configure the exact communication ports that JMX/RMI actually uses.
- Do not assume a DNS service name or HTTP port doubles as a JMX endpoint.

Record upfront: **PID/JVM**, **instance/deployment**, **JMX connection URL**, and **expected ObjectName**.

## 5. Inspecting the Platform MBeanServer Directly

Before touching any UI, use code inside the application JVM itself to inspect the registry:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistrationProbe {
    public static void printStatus() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName expected = new ObjectName(
            "com.example.orders:type=Worker,name=Primary"
        );

        System.out.println("MBean count = " + server.getMBeanCount());
        System.out.println("Registered = " + server.isRegistered(expected));
        System.out.println("Canonical name = " +
                expected.getCanonicalName());

        ObjectName pattern = new ObjectName("com.example.orders:*");
        for (ObjectName name : server.queryNames(pattern, null)) {
            System.out.println("Found: " + name.getCanonicalName());
        }
    }
}
\`\`\`

Run the probe **inside the process under inspection** (for example via startup diagnostics or an integration test); running a separate Java process reads that other process's platform server, since each JVM has its own registry.

Outcomes:

- \`isRegistered(expected) == true\`: the exact name exists in the platform server; move on to checking the connector/client.
- \`false\` yet \`queryNames(pattern)\` finds a similar name: most likely a name mismatch in keys, values, quoting, or domain.
- \`false\` with no MBeans in the domain: check the exporter and bean discovery; also verify whether a custom server is used instead of the platform server.

You can temporarily list \`queryNames(null, null)\` to inspect the registry, but avoid unbounded printing and never log names containing sensitive data in production logs.

## 6. Which MBeanServer Is Being Used?

Java allows **multiple \`MBeanServer\` instances inside the same JVM**. The common platform server is:

\`\`\`java
MBeanServer platform =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
\`\`\`

An application or framework can create another server:

\`\`\`java
MBeanServer custom =
        javax.management.MBeanServerFactory.createMBeanServer(
            "com.example.custom"
        );
\`\`\`

Registering on \`custom\` does not make the MBean appear on \`platform\`. A typical local attach client sees the platform management interface per JVM configuration; a custom server requires an appropriate connector if external clients are meant to see it.

In Spring, \`MBeanExporter\` can be assigned a specific server:

\`\`\`java
import org.springframework.jmx.export.MBeanExporter;

MBeanExporter exporter = new MBeanExporter();
exporter.setServer(platform);
\`\`\`

When more than one server exists, the most reliable approach is injecting the right \`MBeanServer\` into the exporter. If there are multiple \`MBeanExporter\` beans, determine which exporter is responsible for each bean and avoid duplicate registrations under the same name.

A probe can list servers tracked by \`MBeanServerFactory\`:

\`\`\`java
for (MBeanServer server :
        javax.management.MBeanServerFactory.findMBeanServer(null)) {
    System.out.printf("DefaultDomain=%s, count=%d%n",
            server.getDefaultDomain(), server.getMBeanCount());
}
\`\`\`

This list does not necessarily include every server created via \`newMBeanServer()\`; do not rely on it alone to prove no other server exists.

## 7. Checking Spring and Spring Boot Configuration

In plain Spring Framework, MBeans are typically exported via \`MBeanExporter\`. Spring JMX annotations require the exporter to read them using an appropriate metadata assembler and naming strategy. Adapter example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Worker,name=Primary"
)
public class WorkerJmxAdapter {
    @ManagedAttribute
    public int getQueueDepth() {
        return 5;
    }
}
\`\`\`

Having \`@Component\` and \`@ManagedResource\` does not guarantee registration if the package is not component-scanned, JMX export is disabled, or the exporter does not process the metadata. Check:

1. Is the \`WorkerJmxAdapter\` bean present in the Spring \`ApplicationContext\`?
2. Is an appropriate \`MBeanExporter\` present? Which server does it use?
3. Are the annotations read by the assembler?
4. What is the actual \`objectName\`?
5. Are there any MBean registration exceptions in the startup logs?

In Spring Boot, \`spring.jmx.enabled=true\` typically enables MBean export under version-appropriate auto-configuration. Example:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Verify the final effective configuration of the deployed environment, because profiles, environment variables, or command-line arguments can override properties files. If you declare a custom exporter yourself, check how it interacts with auto-configuration rather than assuming Boot handles everything uniformly.

Some beans managed by Actuator/metrics have their own export pipeline; a missing application MBean does not necessarily mean all Spring monitoring mechanisms are broken.

## 8. ObjectName: You Only Find the Right MBean with the Right Name

For example, these two names are equivalent because they differ only in key-property order:

\`\`\`text
com.example:type=Worker,name=Primary
com.example:name=Primary,type=Worker
\`\`\`

However, the following names can differ significantly:

\`\`\`text
com.example:type=Worker,name=Primary
com.example:type=Worker,name="Primary"
com.example:type=Worker,name=primary
com.example:type=Workers,name=Primary
\`\`\`

\`ObjectName\` preserves differences between quoted/unquoted values and letter case. When a value is created via \`ObjectName.quote\`, construct probes using the same rule.

\`\`\`java
String rawName = "Order,Priority";
ObjectName expected = new ObjectName(
    "com.example:type=Queue,name=" + ObjectName.quote(rawName)
);
\`\`\`

To search more broadly:

\`\`\`java
ObjectName pattern = new ObjectName("com.example:*");
java.util.Set<ObjectName> found =
        platform.queryNames(pattern, null);
\`\`\`

Do not accidentally put \`*\` in a registration name, as that creates a pattern rather than a concrete name. When multiple MBeans share a domain, use \`getCanonicalName()\` for consistent comparisons.

## 9. Distinguishing Standard MBeans, MXBeans, and Spring-Managed MBeans

A Java class named \`CacheMonitor\` is not automatically accepted by JMX simply because it has a \`getSize()\` method. For a **Standard MBean**, a public \`CacheMonitorMBean\` interface implemented by the class is normally required:

\`\`\`java
public interface CacheMonitorMBean {
    int getSize();
    void clear();
}

public class CacheMonitor implements CacheMonitorMBean {
    public int getSize() { return 7; }
    public void clear() { }
}
\`\`\`

If you want to register an implementation whose name/interface does not follow the naming convention, you can use \`javax.management.StandardMBean\` to pass the management interface explicitly:

\`\`\`java
CacheMonitor monitor = new CacheMonitor();

javax.management.StandardMBean wrapped =
    new javax.management.StandardMBean(
        monitor, CacheMonitorMBean.class
    );

platform.registerMBean(
    wrapped,
    new ObjectName("com.example:type=Cache,name=Primary")
);
\`\`\`

MXBeans have their own data-type mapping rules. Spring annotation-driven export can use an assembler to expose a bean as an MBean without always requiring an interface named per the Standard MBean convention. Choose the right registration model, check startup exceptions such as \`NotCompliantMBeanException\`, and then verify \`MBeanInfo\`.

## 10. MBean Exists, Yet Attributes or Operations Are Missing

This is a different issue from "MBean not found." Query the metadata:

\`\`\`java
javax.management.MBeanInfo info =
        platform.getMBeanInfo(expected);

System.out.println(info.getClassName());

for (javax.management.MBeanAttributeInfo attr :
        info.getAttributes()) {
    System.out.println("Attribute: " + attr.getName());
}

for (javax.management.MBeanOperationInfo op :
        info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}
\`\`\`

If metadata lacks the attribute/operation, the cause may be that the method is not in the MBean interface, the annotation was ignored, the data type cannot be mapped, or the bean was exported under a different model than expected.

If metadata is present yet reading fails, check access permissions, exceptions in getters, and return types. A slow or throwing getter often causes incomplete UI rendering without removing the registration itself.

## 11. Checking JConsole and VisualVM

With **JConsole**, the basic workflow is:

1. Open the right Java process in the local list, or enter the exact remote JMX service URL.
2. Open the MBeans tab (if supported by the tool/connection).
3. Expand the application's domain.
4. Inspect \`type\`, \`name\`, and other keys instead of looking only at class names.
5. Reconnect or refresh if the application registered MBeans after the client connected.

With **VisualVM**, MBean browsing capability may depend on the version and MBeans plugins. A tool not displaying an MBeans tab does not prove the server lacks registrations; cross-check with JConsole or another JMX client.

To separate UI bugs from server bugs, use a JMX client calling \`queryNames\` and \`getMBeanInfo\` directly. If the API returns data while the UI does not show it, the issue lies in the client/plugin, filters, or refresh timing.

## 12. Remote JMX: Checking the Connector and RMI

For remote JMX over RMI, a common setup uses JVM properties:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Djava.rmi.server.hostname=<reachable-host>
\`\`\`

This example only illustrates endpoint-related variables; **it is not a complete secure deployment configuration**. Proper authentication, SSL/TLS, and network access restrictions must be configured. Never use \`authenticate=false\` or \`ssl=false\` as a quick fix in production.

RMI can involve multiple endpoints if the RMI port is not fixed. Connecting to the registry port successfully and then hanging/failing can happen when the server returns an unreachable hostname or a firewall blocks the second port.

When a remote client reports errors:

- **Connection refused:** check host, port listener, and process.
- **Timeout:** check routing, NAT, container port mappings, and firewalls.
- **Authentication failed:** check credentials and connector policy.
- **TLS handshake failure:** check truststore/certificates and allowed protocols.
- **Connected, yet domain missing:** check which server the connector points to and query permissions.

**Separate network errors from MBean errors**: if a JMX connection cannot be established, you cannot conclude from the UI whether registrations exist.

## 13. Verifying with a JMXConnector Client

To determine what a client actually sees, run Java code reading via \`MBeanServerConnection\`:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class RemoteJmxProbe {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url)) {
            MBeanServerConnection connection =
                    connector.getMBeanServerConnection();

            ObjectName pattern = new ObjectName("com.example:*");

            for (ObjectName name :
                    connection.queryNames(pattern, null)) {
                System.out.println(name.getCanonicalName());
            }
        }
    }
}
\`\`\`

Run the probe from **the same location where the JMX UI runs** to reproduce the network path and access permissions. In environments requiring credentials/TLS, pass an environment map to \`JMXConnectorFactory.connect\` per actual configuration—avoid hard-coding passwords in source code.

If the remote probe sees the MBean while the UI does not, focus on the client UI. If the in-process probe sees it while the remote probe does not, check the connector, the MBeanServer exported by the connector, and access permissions.

## 14. Spring Proxies and Lifecycle Cases

A bean may be wrapped by an AOP proxy, a scoped proxy, or excluded by configuration conditions. This affects how the exporter detects annotations, interfaces, or bean names. If the issue appears only when transactions, security, or caching are enabled, inspect the actual proxy type and the interfaces visible to the exporter.

Regarding lifecycle:

- The Spring context initializes the exporter after managed beans are ready.
- When the context closes, the exporter may unregister registered MBeans.
- DevTools restarts, test contexts, hot reloads, and container redeploys can cause MBeans to appear and then vanish.
- Creating two contexts sharing the platform server and the same ObjectName can cause collisions.
- An MBean registered manually outside Spring may not be cleaned up automatically by the exporter.

Do not resolve collisions by blindly enabling unconditional MBean overwrite mode; determine who owns the registration and when it should unregister.

## 15. Integration Testing for "Missing MBean" Scenarios

An integration test should bring up the Spring context, obtain the right \`MBeanServer\`, and assert registration:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.ObjectName;

class JmxRegistrationAssertions {
    static void assertWorkerExposed(MBeanServer server)
            throws Exception {
        ObjectName name = new ObjectName(
            "com.example.orders:type=Worker,name=Primary"
        );

        assertTrue(server.isRegistered(name));
        var info = server.getMBeanInfo(name);

        assertTrue(
            java.util.Arrays.stream(info.getAttributes())
                .anyMatch(a -> "QueueDepth".equals(a.getName()))
        );
    }
}
\`\`\`

This test does not require opening JConsole and catches Spring configuration errors early. If system requirements include remote JMX, add a test with a trial connector in an isolated environment verifying \`queryNames\` via \`MBeanServerConnection\`; never enable remote management in production solely to run tests.

## 16. Diagnostic Decision Tree

\`\`\`text
MBean not visible in UI
  |
  +-- Connected to the right JVM/PID?
  |       +-- No --> select the right process/endpoint
  |
  +-- In-process isRegistered(ObjectName) == true?
  |       |
  |       +-- No --> does the bean exist in Spring context?
  |                       |
  |                       +-- No --> component scan/profile/condition
  |                       +-- Yes --> exporter/annotation/MBean compliance
  |
  +-- Right MBeanServer?
  |       +-- No --> specify the right server/connector
  |
  +-- Visible via client queryNames()?
  |       +-- No --> connector, permissions, connection, namespace
  |
  +-- Visible in client API but missing from UI?
          +-- refresh, tree filter, version/plugin, metadata
\`\`\`

Following this diagram keeps every hypothesis testable. A single "not visible" symptom can stem from completely different causes; record evidence at each boundary before changing configuration.

## 17. Thinking Pitfalls to Avoid

- **"Not visible in UI means the bean doesn't exist."** The UI is the last layer; query \`MBeanServer\` directly to confirm.
- **"Enabling \`spring.jmx.enabled=true\` lets remote clients connect."** Internal export and remote connectors are two separate concerns.
- **"The class name is the ObjectName."** Domain and key-properties define the JMX ObjectName, not necessarily the class name.
- **"Having platform MBeanServer makes every custom server show up together."** Each server maintains its own registry.
- **"Adding \`@ManagedResource\` is enough for registration."** An exporter and metadata mapping must actually be active.
- **"Disable security to test."** Diagnose with probes, logs, and controlled configs; do not disable access controls.
- **"Reconnecting always fixes it."** If \`isRegistered\` is false, reconnecting does not substitute for fixing registration.

## 18. Key Takeaways

When an MBean fails to appear in JConsole or VisualVM, verify in order: **right JVM → bean created by Spring → exporter registers right ObjectName → right MBeanServer → connector points to right server → visible to client API → rendered in UI**. \`isRegistered\`, \`queryNames\`, and \`getMBeanInfo\` are the core diagnostic primitives. They distinguish registration errors, naming errors, connection errors, and UI glitches without guessing from the screen.

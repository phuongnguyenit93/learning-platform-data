# Connecting JConsole to Local and Remote MBeanServers

## 1. Learning Objectives

After this lesson, you can:

- Explain that JConsole is a JMX tool in the JDK that accesses MBeans through an MBeanServer for observation and management operations.
- Connect JConsole to a Java application on the **same machine** (local process) or a **different machine** (remote JMX connection).
- Distinguish the platform MBeanServer from a JMX connector endpoint, and recognize the JMX/RMI transport path.
- Enable the required remote JMX configuration, understanding port, hostname, authentication, and TLS parameters.
- Self-diagnose common connection issues: missing process, wrong PID, missing attach permissions, firewall, NAT, RMI hostname, dynamic ports, TLS, and credentials.
- Use JConsole's MBeans tab to read attributes, inspect operations, observe notifications, and check safety limits when performing operations.
- Apply secure connection workflows in Spring Framework applications, JVM services, containers, and servers.

## 2. What Is JConsole?

**JConsole** is a graphical tool bundled with some JDK distributions, built on Java Management Extensions (JMX). It helps operators observe the JVM and registered MBeans, typically through these tabs:

- **Overview:** summary of CPU, memory, thread count, and classes.
- **Memory:** heap/non-heap, memory pools, GC, and memory usage graphs.
- **Threads:** total thread count, states, and thread information exposed by the JVM.
- **Classes:** number of loaded and unloaded classes.
- **VM Summary:** runtime, JVM, classpath/path, OS details, and management properties.
- **MBeans:** tree of ObjectNames, attributes, operations, and notifications exposed via JMX.

JConsole is **not** a long-term metrics store or a distributed analytics system. It is primarily suited for live, point-in-time observation and diagnosis. Long-term monitoring tools such as Prometheus/Grafana can collect metrics via dedicated exporter mechanisms if the application requires history and alerting.

An MBean can be registered in the JVM's platform MBeanServer:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example:type=Cache,name=Products"
);
server.registerMBean(cacheMonitor, name);
\`\`\`

JConsole will see this MBean through a JMX connection if the connector points to the right MBeanServer and access permissions allow it.

## 3. Connection Architecture

\`\`\`text
                      Application JVM
+--------------------------------------------------------+
| Business services / Spring beans                       |
|           |                                            |
|       MBeans / MXBeans                                 |
|           | register                                   |
|           v                                            |
| Platform MBeanServer                                   |
|   java.lang:type=Memory                                |
|   java.lang:type=Threading                             |
|   com.example:type=Cache,name=Products                 |
|           ^                                            |
|           | MBeanServerConnection API                  |
|           |                                            |
|    JMX agent / JMXConnectorServer (when remote enabled)|
+-----------|--------------------------------------------+
            ^
            | JMX/RMI, over network when using remote
            |
        JConsole
        - Local Process
        - Remote Process
\`\`\`

**Platform MBeanServer** manages MBeans inside the Java process. **JMXConnectorServer** provides a way for clients to connect from outside the process when configured. With the common RMI-based remote JMX, the connection also depends on the hostname advertised by the RMI stub and the associated ports.

For **local** connections, JConsole on the same host can typically discover eligible JVMs and use the local management/attach mechanism. For **remote** connections, the client needs a configured endpoint reachable over the network, potentially with authentication and TLS.

Key point to remember: calling \`ManagementFactory.getPlatformMBeanServer()\` in code **does not automatically open a remote JMX port**. A local process can have JMX MBeans without having remote connectivity enabled.

## 4. Prerequisites

Before starting, check:

1. **JDK/JConsole:** a JDK installation containing the \`jconsole\` tool. Some minimal runtime images do not include graphical tools.
2. **Java process:** the application is running in a JVM with the JMX management API; with a standard JDK platform MBeanServer, system MBeans are typically available.
3. **Local permissions:** the account running JConsole can see/attach to the process, depending on the OS, user permissions, and JVM configuration.
4. **Remote connector:** the target JVM has JMX remote enabled; the endpoint and required ports are open within the proper network scope.
5. **Security:** credentials, truststore/certificates, or a connection tunnel if required by policy.
6. **Spring:** to see application MBeans, beans must be exported via a Spring JMX exporter or registered with the MBeanServer, in addition to the default JVM MBeans.

Check commands in a terminal with a JDK:

\`\`\`bash
java -version
jconsole
\`\`\`

On Windows, you can run \`jconsole.exe\` from the JDK's \`bin\` directory. If the command is not recognized, verify the JDK installation path or invoke the appropriate executable directly.

You do not need to add JConsole to your application's Maven/Gradle dependencies: it is an external JVM tool used to connect and observe.

## 5. Local Connection: JConsole and an Application on the Same Machine

### 5.1. Steps

1. Start the Java/Spring Boot application in a local JVM.
2. Open a terminal and run \`jconsole\`, or launch \`jconsole.exe\` from the JDK's \`bin\` directory.
3. In the **New Connection** window, select **Local Process**.
4. Select the Java process by PID and launch command description. If multiple JVMs are running, cross-check the PID to avoid picking the wrong one.
5. Click **Connect**. For JVM versions and configurations supporting the local management agent, the tool can enable/use this agent for access.
6. After connecting, open the **MBeans** tab and explore domains such as \`java.lang\`, \`com.sun.management\`, or the exported application domain.

You can check the PID using \`jps -l\` if the JDK includes the \`jps\` utility:

\`\`\`bash
jps -l
\`\`\`

On Windows, the PID can also be found in Task Manager; on Linux/macOS, use the corresponding process management tools. You only need the right PID and appropriate access permissions; you do not need to enable remote JMX just to connect on the same machine when local attach works.

### 5.2. Choosing the Right Process

If multiple Java processes are running on the machine, names like \`org.springframework.boot.loader.launch.JarLauncher\`, \`Application\`, or \`GradleDaemon\` may look similar. Verify the PID, application path, command line, or startup sequence. Do not choose a JVM solely by its order in the list.

Local JConsole may also fail to detect a process when it runs under a different account, JVM attach is restricted, the process runs in another container namespace, or the agent is disabled. In that case, diagnose permissions/namespace policies or switch to an intentionally configured connection method.

### 5.3. Local Connection Does Not Mean Unconditionally Safe Administration

An account on the same machine can have sensitive access rights. If an MBean exposes operations such as \`clearCache\`, \`resetStatistics\`, or \`pauseConsumer\`, a JConsole user with permission can execute them and affect the system. A local connection only differs in access path; it does not make every operation harmless.

## 6. Example Application with an MBean to Observe in JConsole

A Standard MBean works well for a simple example:

\`\`\`java
package example.jmx;

public interface TaskMonitorMBean {
    long getCompletedCount();
    boolean isPaused();
    void resume();
}
\`\`\`

\`\`\`java
package example.jmx;

public final class TaskMonitor implements TaskMonitorMBean {
    private volatile long completedCount = 42L;
    private volatile boolean paused;

    @Override
    public long getCompletedCount() {
        return completedCount;
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
\`\`\`

Register it and keep the application running long enough to observe:

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxDemoApplication {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=TaskMonitor,name=Primary"
        );
        server.registerMBean(new TaskMonitor(), name);

        System.out.println("MBean registered: " + name);
        System.out.println("Press Enter to stop.");

        try {
            System.in.read();
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

When connecting JConsole to this JVM, go to **MBeans → com.example → TaskMonitor → Primary** (tree display may vary by version). You will see:

- \`CompletedCount\` with an initial value of \`42\`, readable.
- \`Paused\` with an initial value of \`false\`, readable.
- \`resume\` appearing under Operations.

If your command line or environment causes \`System.in.read()\` to exit early because stdin is unavailable, replace it with your own long-running application lifecycle; the goal is to keep the JVM alive long enough for JConsole to attach.

### 6.1. Registering an MBean and Exposing a Spring Bean Are Different Things

A regular Spring bean does not automatically appear in the JMX MBean tree. With Spring Framework, you can use \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` with an appropriate exporter configuration.

The Spring JMX exporter registers managed objects in an MBeanServer, typically the platform MBeanServer. JConsole only displays MBeans that are actually registered on the server it is accessing.

## 7. Remote Connection: Two Configuration Parts to Understand

Remote JMX typically relies on the JVM's **JMX management agent** and RMI transport. You need to distinguish:

- **JMX management port:** where the client initially contacts the RMI registry/connector endpoint.
- **RMI server port:** the actual transport port returned by the remote endpoint to the client to continue the connection.

If the RMI server port is chosen dynamically, the client may reach the registry port yet fail to connect to the port advertised afterward, especially across firewalls, NAT, and containers. Therefore, many deployments fix both ports appropriately.

Other JVMs and JMX connector mechanisms may use different configurations; the examples below apply to the built-in RMI-based remote JMX agent commonly found on HotSpot/OpenJDK.

## 8. Configuring Remote JMX in a Lab Environment

### 8.1. Demonstration Command

Use a configuration **without authentication and without TLS** only in an isolated lab environment with no access from untrusted networks. Example:

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -cp out example.jmx.JmxDemoApplication
\`\`\`

Explanation:

| Setting | Meaning |
| --- | --- |
| \`com.sun.management.jmxremote\` | Enables the JMX management agent using the JVM-supported mechanism. |
| \`com.sun.management.jmxremote.port=9010\` | Sets the remote JMX management/registry port. |
| \`com.sun.management.jmxremote.rmi.port=9010\` | Fixes the RMI connector server port, avoiding a random port that would need to be opened separately. |
| \`com.sun.management.jmxremote.authenticate=false\` | Disables authentication; **suitable only for an isolated lab environment**. |
| \`com.sun.management.jmxremote.ssl=false\` | Disables TLS encryption; **do not use over untrusted networks**. |
| \`java.rmi.server.hostname=127.0.0.1\` | Sets the address advertised by the RMI stub, suitable for local loopback connections. |

With \`127.0.0.1\`, the example targets JConsole running on the **same host**, or on a client via an **SSH tunnel** with proper localhost forwarding. To connect directly from another host, the hostname advertised by RMI must be an address/name reachable **from the client** according to the network design, along with the necessary security layer and access controls.

Setting \`port\` and \`rmi.port\` to the same value is a common configuration; across different environments and JVM versions, you should verify how endpoints are bound. The JVM may also open a separate local management port for local attach.

### 8.2. Windows PowerShell

In PowerShell, \`\\\` is not a line-continuation character like in Bash. Single-line example:

\`\`\`powershell
java -Dcom.sun.management.jmxremote -Dcom.sun.management.jmxremote.port=9010 -Dcom.sun.management.jmxremote.rmi.port=9010 -Dcom.sun.management.jmxremote.authenticate=false -Dcom.sun.management.jmxremote.ssl=false -Djava.rmi.server.hostname=127.0.0.1 -cp out example.jmx.JmxDemoApplication
\`\`\`

In PowerShell 5.1, if line breaks are needed, use a backtick per shell syntax and make sure there is no space after the backtick. JVM options must appear **before** the main class name or \`-jar\`.

### 8.3. With a Spring Boot JAR

\`\`\`bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -jar app.jar
\`\`\`

This example is for a loopback lab; do not use this exact configuration to open production ports. Note the difference between **enabling the JVM's remote JMX agent** and **enabling Spring Boot JMX export**: the remote agent determines the connection path, while the Spring/JMX exporter determines which application MBeans are registered.

## 9. Connecting to a Remote Process in JConsole

UI steps:

1. Run the target JVM with the JMX remote agent and confirm the process is active.
2. Open JConsole on the client machine.
3. In the **New Connection** window, select **Remote Process**.
4. Enter the \`host:port\` advertised by the JVM, for example \`127.0.0.1:9010\` for the lab.
5. If the endpoint requires credentials, enter the provided username/password in the corresponding fields (or follow your environment's authentication procedure).
6. Click **Connect**. If a warning about an unencrypted connection appears, proceed only if this is a confirmed isolated lab; for real environments, use a protected connection path.
7. Once connected, inspect the **MBeans** tab and verify the right domain/application.

A typical JMX/RMI service URL:

\`\`\`text
service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi
\`\`\`

The exact URL structure depends on the connector. Use the URI configured/provided by your infrastructure instead of guessing when a custom connector is used.

### 9.1. Distinguishing Endpoint Errors from Permission Errors

- **Connection refused:** usually no process is listening on that address/port, or the network/firewall actively rejects it.
- **Connection timed out:** the network path or firewall drops packets, the hostname is unreachable, or the second RMI port is not open.
- **Authentication failed / SecurityException:** incorrect credentials, authentication policy, or authorization.
- **SSL/TLS handshake error:** an issue with SSL mode, truststore, certificate, protocol, or hostname verification.
- **Connected but missing application MBeans:** exporter did not register them, wrong MBeanServer, different ObjectName, or the application has not initialized the component yet.

Reading errors by failure stage helps avoid modifying the application by mistake when the real issue is in RMI or networking.

## 10. RMI, Hostname, NAT, and Containers

### 10.1. Why Does JConsole Still Fail to Connect When Port 9010 Is Open?

A JMX/RMI client can initially connect to the RMI registry on \`host:9010\`, receive an RMI stub containing the connector's address/port, and then open a subsequent connection to that address/port. If the stub advertises a private address such as \`127.0.0.1\` of the **server** to a client running on another machine, the client will try to connect to **its own** localhost and fail.

Example:

\`\`\`text
Client 10.0.0.50                Server 10.0.0.20
      |                               |
      | TCP 9010 -> registry          |
      +------------------------------>|
      |                               |
      | RMI stub: 127.0.0.1:random    |
      |<------------------------------+
      |
      +--> 127.0.0.1:random (client localhost)
           Connects to wrong target -> fails
\`\`\`

When connecting remotely directly, \`java.rmi.server.hostname\` must hold an address routable from the client, and the RMI server port must be fixed/opened in the proper scope. If using a tunnel, the advertised loopback must match that tunnel's design.

### 10.2. In Docker or Kubernetes

Considerations:

- A JVM inside a container has its own network namespace.
- The port the JVM listens on inside the container differs from the port mapped/exposed on the host.
- \`java.rmi.server.hostname\` must be an address the client can reach after routing/NAT/tunneling.
- Mapping only the registry port does not solve the issue if the RMI stub returns an unreachable address or port.
- In Kubernetes, \`kubectl port-forward\` forwards only the specified ports; the endpoint advertised by RMI must align with that connection.
- Container runtimes, NetworkPolicies, and ingress controllers do not automatically understand or rewrite RMI stubs.

A simple lab approach is to fix both the JMX port and RMI port to the same port, use a controlled tunnel, and verify how the client reaches the endpoint advertised by the stub. For production, your organization's network/security procedures determine the actual configuration.

## 11. Secure Remote Connections

JMX can allow viewing data, modifying attributes, and invoking operations that change application state. Do not treat a JMX endpoint like a read-only HTTP health endpoint.

### 11.1. Authentication

The standard HotSpot/OpenJDK JMX/RMI agent can use password/access files. Typical options:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/secure/path/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/path/jmxremote.access
\`\`\`

The files must be protected with appropriate filesystem permissions; the agent may reject a password file with overly broad permissions. Exact syntax and permissions depend on the JVM/OS; consult the JDK documentation for your environment.

Illustrative access file example:

\`\`\`text
monitorRole readonly
controlRole readwrite
\`\`\`

Example password file:

\`\`\`text
monitorRole <password-set-securely>
controlRole <another-password-set-securely>
\`\`\`

These are sample contents—do not use literal passwords from documentation as real credentials. These files must be placed outside the source repository in securely managed paths. Agent-level \`readonly\`/\`readwrite\` permissions are only part of a security strategy; which operations are exposed and additional authorization layers still need review.

### 11.2. TLS and Network Restrictions

In real environments, you should:

- Use properly configured TLS/SSL with verified certificates/truststores.
- Allow connections only from jump hosts, VPNs, tunnels, or operational network zones.
- Never expose JMX ports broadly to the internet.
- Store credentials in a secret manager or equivalent secrets management mechanism.
- Assign permissions according to read/control needs; avoid using readwrite accounts for monitoring tasks.
- Maintain appropriate auditing/logging for dangerous administrative operations.
- Never expose sensitive data via getters, notifications, or ObjectNames.

**Note:** some JMX/RMI SSL setups may require separate SSL configuration for the registry and the connector. If JConsole fails the TLS handshake, check the SSL mode and your JDK version's documentation instead of disabling security just to "make it work."

### 11.3. SSH Tunneling to Reduce Port Exposure

A practical design is to listen only on loopback or a private network, then create an SSH tunnel from the operator's machine to the server. Conceptual example:

\`\`\`bash
ssh -L 9010:127.0.0.1:9010 operator@server.example
\`\`\`

Once the tunnel is active, JConsole attempts to connect to \`127.0.0.1:9010\`. This requires the RMI stub to advertise an address/port compatible with the tunnel, such as port 9010/loopback. Do not assume tunneling just the registry port will work with an RMI configuration using dynamic ports or a different hostname.

An SSH tunnel does not eliminate the need to control who is allowed to SSH and who is allowed to invoke JMX operations.

## 12. Using JConsole to Read MBeans and Perform Actions

### 12.1. Attributes

In the **MBeans** tab, select an ObjectName and open **Attributes**. The tool displays attributes whose metadata permits reading. Writable attributes may provide a UI field to edit their values.

Standard MBean example:

\`\`\`java
public interface CacheAdminMBean {
    long getEntryCount();
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
\`\`\`

For this MBean, JConsole can display \`EntryCount\` as read-only and \`Enabled\` as read/write. Changing \`Enabled\` takes real effect on the MBean, not just in the UI.

### 12.2. Operations

The **Operations** section lists exposed operations. For actions with side effects like \`clearCache\` or \`requestPause\`, clicking the button instructs the server to execute the operation.

Read the description, confirm you are on the right environment, and check state before and after the operation. If the client times out after invoking, do not assume the operation did not run; the server may have already started processing it.

### 12.3. Notifications

Some MBeans support JMX notifications. JConsole may offer a subscription UI under Notifications depending on the MBean and tool version. If an MBean does not emit notifications, that tab will not generate events on its own.

For an MBean to emit events, it needs a mechanism such as \`NotificationBroadcaster\`/\`NotificationEmitter\`, and the client must subscribe via MBeanServerConnection or an appropriate UI.

### 12.4. MBeanInfo and ObjectName

JConsole renders a tree based on \`ObjectName\`, such as:

\`\`\`text
com.example:type=Cache,name=Products
java.lang:type=Memory
java.lang:type=Threading
\`\`\`

If an MBean is missing, check the domain, type, and name, and verify whether it is actually registered in the right MBeanServer. A minor typo in the ObjectName will cause you to look in the wrong tree branch.

## 13. Spring Framework and Spring Boot Integration

### 13.1. Spring-Managed MBeans

In Spring Framework, \`MBeanExporter\` can register beans into JMX. Example of a managed bean:

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example:type=Worker,name=Import",
    description = "Import worker status"
)
public class ImportWorkerAdmin {

    @ManagedAttribute
    public long getProcessedCount() {
        return 42L;
    }

    @ManagedAttribute
    public boolean isHealthy() {
        return true;
    }
}
\`\`\`

For annotation metadata to take effect, a corresponding exporter/assembler configuration is required. You can configure Spring JMX per the Spring documentation or use Spring Boot's conditional auto-configuration. Having only \`@Component\` and \`@ManagedResource\` is not enough to guarantee MBean registration in every application.

### 13.2. Spring Boot JMX Configuration

Depending on the Spring Boot version, a common property is:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

This property enables Spring Boot's JMX export auto-configuration when conditions are met. It does not directly open a remote JMX port on the JVM. To let JConsole access it from another machine, a connector/JMX remote agent or equivalent mechanism—along with security—is still required.

If using Spring Boot Actuator, management endpoints can be exposed via JMX with separate exposure configuration. Do not assume HTTP exposure settings apply verbatim to JMX; each channel must be reviewed independently.

### 13.3. Reasons Application MBeans May Not Appear

Possible causes:

1. The bean has not been registered by an exporter.
2. Spring Boot JMX auto-configuration is disabled or its conditions are not met.
3. JMX annotations are present, but the assembler does not read that metadata.
4. The generated ObjectName differs from what you expect.
5. The ApplicationContext has not finished initializing, or the MBean was unregistered.
6. JConsole connected to the wrong JVM/PID.
7. The client connected to a different MBeanServer than the one holding the MBean.
8. The exporter reported a name collision or MBean registration error.

How to verify directly in application code:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Import"
);

System.out.println(server.isRegistered(name));
\`\`\`

If it prints \`false\`, inspect the MBean export process rather than troubleshooting the firewall.

## 14. Connection Troubleshooting Table

| Symptom | Possible Cause | Diagnostic Step |
| --- | --- | --- |
| Local Process does not list the app | Wrong user, attach disabled, different namespace, JVM stopped | Confirm PID, account, permissions, and process status |
| Process selected but connection refused | Agent inactive, attach permission, incompatible JVM | Check logs and JDK local attach support |
| Remote \`Connection refused\` | Port not listening, wrong host/port | Check JVM options and listener |
| Remote timeout | Firewall, NAT, secondary RMI port unreachable | Check both the registry port and the endpoint in the RMI stub |
| Registry connects then fails | Stub advertises wrong hostname/port | Check \`java.rmi.server.hostname\`, \`jmxremote.rmi.port\`, and network mappings |
| Authentication failed | Wrong username/password, broken access file | Check credentials configuration and filesystem permissions |
| SSL handshake failed | Mismatched certificate, truststore, or TLS mode | Compare client and server SSL configurations |
| Connected, but app MBeans missing | Exporter not running, wrong MBeanServer/ObjectName | Check \`isRegistered\`, \`queryNames\`, and the exporter |
| MBeans appear but operation fails | Missing permission, wrong signature, MBean error | Check metadata, exceptions, and server logs |
| JConsole is slow/frozen | CPU-heavy getters, too many MBeans, slow network | Check getter/polling cost and limit data volume |

Never disable TLS or authentication to "fix" a production error without understanding the root cause. A configuration error can usually be resolved with the right hostname, certificate, or permissions.

## 15. Ordered Diagnostic Workflow

To avoid unfocused troubleshooting, follow this sequence:

\`\`\`text
(1) Is the JVM running?
        |
        v
(2) Are MBeanServer and target MBeans present?
        |
        v
(3) Local: Does JConsole see the right PID?
    Remote: Is the registry endpoint open?
        |
        v
(4) Remote: Which host/port does the RMI stub advertise?
        |
        v
(5) Does network/firewall/tunnel reach the next endpoint?
        |
        v
(6) Are authentication/TLS/authorization valid?
        |
        v
(7) Does JConsole connect and browse MBeans?
        |
        v
(8) Verify values and permitted operations.
\`\`\`

If local attach fails, you do not necessarily have to configure remote right away; check the JDK tools, PID, user, and OS permissions first. If the remote registry succeeds but the RMI stub is wrong, opening arbitrary additional firewall ports may not help.

## 16. Programmatic JMX Client Example Instead of GUI

Besides JConsole, Java code can connect to the same remote endpoint via the standard JMX API:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName memory = new ObjectName(
        "java.lang:type=Memory"
    );

    Object heap = connection.getAttribute(
        memory,
        "HeapMemoryUsage"
    );

    System.out.println(heap);
}
\`\`\`

In practice, if remote JMX requires authentication, pass an environment map with the appropriate credentials to \`connect\`; if TLS is used, configure the client/truststore per policy. The snippet above is for an unauthenticated lab endpoint.

This API also serves as the foundation for automated inspection tools, though a collector should favor lightweight getters and limit concurrency and polling rate.

### 16.1. Why Doesn't the Client Need the Application's Objects?

\`MBeanServerConnection\` provides \`getAttribute\`, \`invoke\`, \`queryNames\`, and \`getMBeanInfo\`. The client only needs to know the \`ObjectName\`, attribute/operation names, and JMX value types. With MXBeans/Open MBeans, complex values can be \`CompositeData\` or \`TabularData\` instead of custom application classes.

## 17. Common Misconceptions

**"JConsole only connects locally."** False. It has a Remote Process option, though the remote JVM must have a connector and proper network/security configuration.

**"Enabling Spring JMX automatically opens a remote port."** False. The Spring exporter registers MBeans; the remote JMX port belongs to a separate JVM connector/agent layer.

**"Opening any single port is enough for RMI."** Not necessarily. Both the registry port and the endpoint advertised by the RMI stub must be reachable. Fixing ports typically simplifies firewall/NAT rules.

**"RMI hostname 127.0.0.1 is always correct."** Only when the client's connection path actually leads to the corresponding loopback, such as locally or through a consistently configured tunnel.

**"Disabling authentication is safe because the port is hard to guess."** False. A port number is not an authentication mechanism.

**"MBeans are only read-only metrics."** False. MBeans can have writable attributes and state-mutating operations.

**"Not seeing an MBean means JConsole has a bug."** Usually you need to check the exporter, ObjectName, target JVM, and MBeanServer first.

## 18. Practice Exercises

### Exercise 1 — Local Connection

Start \`JmxDemoApplication\`, use \`jps -l\` to find the PID, open \`jconsole\`, and select the right process. Note the \`java.lang\` and \`com.example\` domains and the \`CompletedCount\` value.

**Expected result:** observe \`CompletedCount=42\` and the \`resume\` operation.

### Exercise 2 — Remote Loopback Lab

Run the application with the JMX management agent on \`127.0.0.1:9010\`, configuring \`port\` and \`rmi.port\` as in the example. In JConsole, select Remote Process and enter \`127.0.0.1:9010\`.

**Expected result:** successful connection on the same host, with access to \`java.lang:type=Memory\` and the demo MBean.

### Exercise 3 — Incompatible RMI Hostname

In an isolated test environment, configure the advertised hostname to differ from an address reachable by the client while keeping the registry port active, and observe the error. Then fix \`java.rmi.server.hostname\` and the RMI port to match the topology.

**Expected result:** recognize the difference between connecting to the registry and connecting to the RMI connector.

### Exercise 4 — Access Protection

Use the JMX agent with authentication and access files configured in a lab environment, creating a read-only role and a management role. Try reading attributes and invoking operations. Observe the difference between client permissions and what the MBean exposes.

**Expected result:** understand why authorization is still necessary even when operations appear in the UI.

### Exercise 5 — Spring

Create a \`@ManagedResource\` in Spring, configure an appropriate exporter, and start the app. Connect local JConsole, locate the configured ObjectName, and verify values. If it is missing, check \`isRegistered\` and the exporter configuration.

**Expected result:** distinguish exporting an MBean from connecting JMX to the JVM.

## 19. Review Questions

**1. Where does JConsole get management information from?** Through the JMX API and MBeanServer, directly in a qualifying local connection or through a connector for remote connections.

**2. Does Platform MBeanServer automatically open a remote port?** No. A separately configured agent/connector is required.

**3. When should you use Local Process?** When JConsole and the JVM run on the same host and permissions/attach mechanisms allow it.

**4. Why can remote JMX fail even when the registry port is open?** Because the RMI stub may point to a subsequent hostname or port that is unreachable.

**5. What is \`java.rmi.server.hostname\` used for?** It specifies the hostname exported/advertised by RMI for the client to connect to the endpoint.

**6. Should authentication/SSL be disabled in production?** No; use unprotected configurations only in intentionally isolated labs.

**7. What is needed to see a Spring bean in JConsole?** The bean must be exported as an MBean by an exporter or appropriate registration mechanism, and JConsole must connect to the right MBeanServer/JVM.

**8. Why must you be cautious when invoking an operation?** Because an operation can immediately alter application state on the server.

## 20. Summary

JConsole is a visual tool for observing the JVM and managing MBeans through JMX. **Local connections** typically rely on discovering and attaching to a JVM on the same machine; **remote connections** require a JMX connector with a clearly configured endpoint, hostname, ports, and security. With JMX/RMI, you must account for both the registry port and the address/port advertised by the RMI stub, especially across firewalls, NAT, and containers.

In Spring Framework applications, JConsole only sees MBeans that have been registered by an exporter or an equivalent JMX mechanism. When working on real systems, prioritize minimal management data, appropriate read permissions, secured connections, and verifying actions before changing state.

## References

- JDK 21 — \`jconsole\` manual: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html
- Oracle JMX Technology — Monitoring and Management: https://docs.oracle.com/javase/8/docs/technotes/guides/management/agent.html
- Java SE 21 — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE 21 — \`JMXServiceURL\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html
- Java SE 21 — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
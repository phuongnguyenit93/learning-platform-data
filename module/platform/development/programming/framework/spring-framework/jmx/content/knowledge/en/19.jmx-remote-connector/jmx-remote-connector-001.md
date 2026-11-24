# JSR-160 and the Remote JMX Connection Model

## 1. Objectives

In Java Management Extensions (JMX), \`MBeanServer\` manages MBeans residing inside a JVM. If a management tool runs in **another JVM, on another machine, or in a separate monitoring service**, it needs a mechanism to access the MBeanServer remotely.

**JSR-160 (JMX Remote API)** defines the client/server connector architecture and the Java API used to accomplish this. The key components include \`JMXConnectorServer\`, \`JMXConnector\`, \`JMXServiceURL\`, and \`MBeanServerConnection\`.

In Spring Framework JMX, beans can be registered into an MBeanServer by \`MBeanExporter\`. A remote connector provides an **access path** to those MBeans; it does not create MBeans itself or decide which beans are exported.

After this lesson, you will be able to:

1. Describe the JMX remote architecture according to JSR-160.
2. Distinguish between MBeanServer, connector server, connector client, and JMX proxy.
3. Understand the structure of \`JMXServiceURL\` and how RMI/JNDI are commonly used.
4. Configure, connect, and close a remote JMX connection using the Java API.
5. Understand remote notifications, connection lifecycle, and event delivery limitations.
6. Analyze issues related to networking, ports, NAT, TLS, authentication, and authorization.
7. Combine a JMX remote connector with Spring \`MBeanExporter\` and avoid operational misconceptions.

## 2. Overall Architecture

\`\`\`text
  JVM A: Spring application                  JVM B: JMX client
+--------------------------------+       +----------------------------------+
| Spring beans                   |       | JConsole / Java application      |
|     |                          |       |                                  |
|     v                          |       | JMXServiceURL                    |
| MBeanExporter                  |       |     |                            |
|     | register                 |       |     v                            |
|     v                          |       | JMXConnectorFactory.connect()    |
| MBeanServer                    |<----->| JMXConnector                     |
|     |                          |       |     |                            |
|     +-- java.lang:*            |       |     v                            |
|     +-- com.example:type=*     |       | MBeanServerConnection            |
|     |                          |       |     |                            |
|     v                          |       |     +-- queryNames()             |
| JMXConnectorServer             |       |     +-- getAttribute()           |
|     |                          |       |     +-- invoke()                 |
|     +-- RMI / connector        |       |     +-- addNotificationListener()|
+--------------------------------+       +----------------------------------+
\`\`\`

Reading the diagram by responsibility:

- \`MBeanExporter\` exports Spring beans as MBeans.
- \`MBeanServer\` is the registry/runtime providing management operations.
- \`JMXConnectorServer\` attaches a remote protocol to the MBeanServer.
- \`JMXConnector\` on the client side establishes and manages the connection.
- \`MBeanServerConnection\` is the client API used to query/control MBeans just as when working with a local server.
- \`JMXServiceURL\` describes the connection endpoint and protocol.

**Key point:** Remote JMX is a **remote transport and management mechanism**, not a persistence mechanism, message broker, or HTTP REST API.

## 3. What Does JSR-160 Add to JMX?

Core JMX provides:

- \`ObjectName\`: identifies an MBean.
- \`MBeanServer\`: registers, searches, reads/writes attributes, and invokes operations.
- Standard MBean, MXBean, Dynamic MBean.
- Notification broadcaster/listener.

JSR-160 adds the **remote access** layer through connector APIs:

| API | Role |
|---|---|
| \`JMXConnectorServer\` | Exposes an MBeanServer over a connector protocol |
| \`JMXConnectorServerFactory\` | Creates a connector server from a URL, environment, and MBeanServer |
| \`JMXConnector\` | Client-side connection to a remote server |
| \`JMXConnectorFactory\` | Creates/connects a connector client |
| \`JMXServiceURL\` | Address and protocol of the connector |
| \`MBeanServerConnection\` | API for managing MBeans over a connection |
| \`JMXConnectionNotification\` | Reports changes in the connector connection lifecycle |
| \`JMXAuthenticator\` | Interface for authenticating callers for the connector server |
| \`JMXPrincipal\` | Principal representing a JMX identity in the appropriate context |

Java SE provides a remote connector based on **RMI**. JSR-160 allows a connector architecture with other protocol providers, but specific support depends on the implementation and classpath.

Do not assume arbitrary URLs such as \`service:jmx:http://...\` are supported by default in Java SE. The protocol name must have a corresponding connector provider.

## 4. JMXServiceURL: Understanding the Connection Address Correctly

A general \`JMXServiceURL\` has the structure:

\`\`\`text
service:jmx:<protocol>://<host>[:<port>][/<url-path>]
\`\`\`

With RMI, two forms are commonly encountered:

\`\`\`text
service:jmx:rmi:///jndi/rmi://host.example.com:9010/jmxrmi
\`\`\`

and the direct RMI connector form depending on server configuration:

\`\`\`text
service:jmx:rmi://host.example.com:port
\`\`\`

The first form involves two concepts:

1. **RMI connector object** — the remote object for the client to make JMX calls.
2. **JNDI/RMI registry** — the location for the client to look up the connector stub.

The \`/jndi/rmi://host:9010/jmxrmi\` part is where the stub is looked up via the registry. It does not guarantee that the final endpoint uses only a single TCP port.

### Why Does "Opening Port 9010" Sometimes Still Fail to Connect?

In many RMI configurations, the client:
- Connects to the RMI registry on the port specified in the URL.
- Receives the stub or endpoint information for the RMI connector.
- Continues connecting to the host/port advertised by the stub.

If the connector uses a dynamic port or advertises an IP/hostname unreachable from the client, the second step can fail even though the registry port is open.

This is a common cause of the situation where "telnet to the registry succeeds, yet JConsole still times out".

## 5. A Remote Client Example in Java

\`\`\`java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteJmxClient {

    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            Set<ObjectName> names = connection.queryNames(
                new ObjectName("java.lang:*"),
                null
            );

            for (ObjectName name : names) {
                System.out.println(name.getCanonicalName());
            }

            ObjectName memory = new ObjectName(
                "java.lang:type=Memory"
            );

            Object heapUsage = connection.getAttribute(
                memory, "HeapMemoryUsage"
            );

            System.out.println(heapUsage);
        }
    }
}
\`\`\`

This snippet assumes a JMX connector server is already running at the address above. It does not start a server or configure security by itself.

\`try-with-resources\` calls \`JMXConnector.close()\` when done. For long-running monitoring programs, you should not create a new connection for every attribute read if proper connection pooling/lifecycle management can be used.

### Do Not Confuse with ManagementFactory in the Client

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

returns the platform MBeanServer of **the JVM executing the call**. When called from the client JVM, this is the client's server, not the remote application's server.

You must use:

\`\`\`java
MBeanServerConnection remote =
    connector.getMBeanServerConnection();
\`\`\`

to query the remote server.

## 6. MBeanServerConnection: One API, Two Environments

\`MBeanServerConnection\` allows the client to call methods such as:

- \`queryNames(ObjectName, QueryExp)\`.
- \`isRegistered(ObjectName)\`.
- \`getMBeanInfo(ObjectName)\`.
- \`getAttribute(ObjectName, String)\`.
- \`setAttribute(ObjectName, Attribute)\`.
- \`invoke(ObjectName, String, Object[], String[])\`.
- \`addNotificationListener(...)\`.
- \`removeNotificationListener(...)\`.

Example:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.orders:type=Queue,name=Orders"
);

boolean exists = connection.isRegistered(name);

if (exists) {
    Object depth = connection.getAttribute(
        name, "PendingCount"
    );
    System.out.println("Pending: " + depth);
}
\`\`\`

Because the same interface applies to both local and remote access, management code can share a common abstraction. However, **failure semantics** in remote calls are more complex than in local calls:

- Network failure or connection timeout.
- Authentication failure.
- Class serialization/deserialization issues.
- MBean unregistered during execution.
- Slow responses or server overload.
- Insufficient access permissions.

Therefore, do not design a remote JMX call as if it were an unfailing local Java getter call.

## 7. Remote Connector Server: Programmatic Configuration Example

You can create an RMI connector server attached to an \`MBeanServer\` via the JMX APIs.

Illustrative example in a test environment:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.rmi.registry.LocateRegistry;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

public final class LocalRmiJmxServer {

    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        // Registry serving RMI connector stub lookups.
        LocateRegistry.createRegistry(9010);

        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );

        JMXConnectorServer connector =
            JMXConnectorServerFactory.newJMXConnectorServer(
                url,
                null,
                server
            );

        connector.start();

        System.out.println(
            "JMX connector listening: " + connector.getAddress()
        );

        // In a real application: manage lifecycle and call stop()
        // when shutting down the app; do not exit the JVM right after start().
    }
}
\`\`\`

**Warning:** This example does not configure authentication, authorization, or TLS. Use it only for illustration in a local/isolated environment. Do not deploy this sample as-is to production, and especially do not bind it broadly to the network or Internet.

In production, you should use the remote management mechanism provided by the JVM/runtime or configure a connector server with explicit security, ports, and lifecycle. When using RMI with firewalls/NAT, you must control both the registry port and the actual RMI endpoint.

## 8. Spring Framework and Remote JMX

Spring Framework JMX has two independent groups of responsibilities:

\`\`\`text
A. Export management surface
   Spring bean
       -> MBeanExporter
       -> MBeanServer

B. Expose remote transport
   MBeanServer
       -> JMXConnectorServer
       -> network
       -> JMXConnector client
\`\`\`

Example of Spring exporting an MBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfig {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MBeanServer server,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(java.util.Map.of(
            "com.example.orders:type=Queue,name=Orders",
            queueMonitor
        ));
        return exporter;
    }
}
\`\`\`

\`QueueMonitor\` must be a valid MBean or be adapted by Spring through a suitable assembler. When the server is specified as above, the exporter registers into the platform MBeanServer.

When the remote connector is also attached to the platform MBeanServer, the client can see both application MBeans and platform MXBeans on the same endpoint, depending on client permissions.

**Do not infer:** Annotating with \`@ManagedResource\` or enabling \`MBeanExporter\` does not make the JVM automatically open an RMI registry or remote connector. The two must be configured separately.

### Spring Boot Notes

Spring Boot has JMX auto-configuration and Spring Boot Actuator endpoints. Certain settings involve \`spring.jmx.enabled\` or the exposure of Actuator JMX endpoints depending on the version.

You must separate:
- Enabling the JMX exporter.
- Allowing which Actuator endpoints are exposed via JMX.
- Initializing the JVM's remote connector.
- Applying network authentication/authorization.

Do not create a second exporter when Boot has already configured the same responsibility, as it may cause duplicate \`ObjectName\` conflicts.

## 9. RMI Connector and JNDI Registry

Many remote JMX configurations in Java SE use RMI:

\`\`\`text
Client                           Server
  |                                |
  | lookup rmi://host:9010/jmxrmi  |
  |------------------------------->| RMI registry
  |<-------------------------------| connector stub
  |                                |
  | connect to stub endpoint       |
  |------------------------------->| RMI connector endpoint
  |                                |
  | getAttribute()/invoke()        |
  |------------------------------->| MBeanServer
  |<-------------------------------| response
\`\`\`

Key takeaways:

- Registry lookup and JMX invocation are separate logical steps.
- The hostname/port advertised in the stub must be reachable.
- \`java.rmi.server.hostname\` can affect the advertised address in some RMI implementations.
- Not every JVM/runtime uses the exact same port arrangement.
- RMI can be complicated across NAT/firewalls/containers if endpoint ports are not controlled.

Example when deploying in a container:

\`\`\`text
Docker container:
  internal hostname = container-abc
  registry port = 9010
  connector endpoint = dynamic port
\`\`\`

An external client may be able to look up the registry but unable to reach the endpoint returned by the stub. Fixing this requires configuring consistent host, ports, and network mapping for the implementation in use, not just changing the URL on the client.

## 10. Authenticated Connections

\`JMXConnectorFactory.connect()\` accepts an environment map, for example with credentials:

\`\`\`java
import java.util.HashMap;
import java.util.Map;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXConnector.CREDENTIALS;

Map<String, Object> environment = new HashMap<>();

environment.put(
    JMXConnector.CREDENTIALS,
    new String[] {username, password}
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, environment)) {

    var connection = connector.getMBeanServerConnection();
    System.out.println(connection.getMBeanCount());
}
\`\`\`

Client-side credentials only matter if the connector server has appropriate authentication. Adding a username/password to the environment does not protect a server that is open without authentication.

### Authentication vs. Authorization

- **Authentication:** verifies who the caller is.
- **Authorization:** determines which attributes the caller is allowed to read/set or which operations the caller may invoke.

A connector may know the identity yet still need a policy for access permissions. In operations, ensure:
- Remote endpoints are not publicly exposed.
- JMX read/write permissions are restricted by role/function.
- TLS or appropriate channel protection is in place to prevent leaking credentials or transmitted data.
- Credentials are not committed to the repository.
- Secrets are not logged in logs or exceptions.

MBeans can have sensitive operations such as shutting down services, resetting state, or changing configuration. Exposing them via remote JMX requires evaluating their impact just like an administrative API.

## 11. Notifications Over a Remote Connector

JMX allows a client to register a listener remotely:

\`\`\`java
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    System.out.printf(
        "type=%s seq=%d%n",
        notification.getType(),
        notification.getSequenceNumber()
    );
};

connection.addNotificationListener(
    targetObjectName,
    listener,
    null,
    null
);
\`\`\`

When a notification is emitted on the server, the connector can forward the notification to the client.

However:
- The listener must be registered on the appropriate connection.
- An MBean may be unregistered or replaced.
- Network failures can interrupt delivery.
- Client restart/reconnect does not automatically replay all missed notifications.
- \`Notification.sequenceNumber\` can help detect anomalies if the source contract guarantees sequential numbering, but it does not provide a queue or persistent history on its own.

For operational tools, a notification should serve as an **update signal**, after which the client re-reads a snapshot of the MBean's state. If the business logic requires zero event loss, use a dedicated event store or durable messaging system.

## 12. JMXConnector Lifecycle

A remote client must manage the connection lifecycle like a network resource:

\`\`\`text
DISCONNECTED
     |
     | connect
     v
  CONNECTED
     |
     +-- query / read / invoke
     +-- subscribe notifications
     |
     | network error / server restart
     v
DISCONNECTED
     |
     | backoff + reconnect
     v
  CONNECTED
     |
     +-- re-register listeners
     +-- refresh current state
\`\`\`

What needs to be handled:

1. Initial connection fails.
2. Connection is closed or the server restarts.
3. MBean name/instance changes after a deployment.
4. Listeners are no longer registered after reconnecting.
5. An operation was sent before disconnect, and the client has not received a response.
6. State changed while the client was offline.

A connector client can emit \`JMXConnectionNotification\` with events related to connection open/close/failure. Use them to monitor connection health, but do not rely on notifications to replace all error detection mechanisms.

### Retrying Can Be Dangerous with invoke()

Suppose the client calls:

\`\`\`java
connection.invoke(
    name,
    "resetStatistics",
    new Object[0],
    new String[0]
);
\`\`\`

If the connection drops at that exact moment, the client may not know whether the server executed the operation or not. **Blind retrying** can cause double execution.

For non-idempotent operations, you need to:
- Define an idempotency contract.
- Have a request identifier or state to check the outcome when needed.
- Limit retries according to the operation type.
- Never treat connector transport as proof of exactly-once delivery.

## 13. Management Proxies via MBeanServerConnection

The client does not necessarily have to call \`getAttribute\`/\`invoke\` manually for every operation. JMX supports creating proxies for suitable management interfaces.

MXBean example:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import javax.management.MBeanServerConnection;

MemoryMXBean memory = ManagementFactory.newPlatformMXBeanProxy(
    connection,
    ManagementFactory.MEMORY_MXBEAN_NAME,
    MemoryMXBean.class
);

System.out.println(memory.getHeapMemoryUsage().getUsed());
\`\`\`

This snippet uses \`connection\` from a remote connector. The proxy enables writing a typed API, but it does not eliminate network or serialization errors. It still performs remote calls under the hood.

For application Standard MBeans or MXBeans, you can use \`JMX.newMBeanProxy()\` or \`JMX.newMXBeanProxy()\` with the matching interface.

Pay attention to:
- Accurate ObjectName.
- Client interface compatibility with the server contract.
- Java types used in signatures being transferable remotely.
- Handling runtime exceptions caused by JMX or the network.

## 14. Detecting and Diagnosing Connection Errors

| Symptom | Likely Cause | What to Check |
|---|---|---|
| Connection refused | No connector/listener on that port | Port, process, bind interface, firewall |
| Registry lookup succeeds but times out | RMI stub advertises an unreachable host/port | RMI endpoint, NAT, container mapping |
| Authentication failed | Incorrect credentials or server auth config | Environment map, credential store, server logs |
| Client connects but does not see app MBeans | Exporter and connector are attached to different MBeanServers | \`setServer()\`, connector binding, \`queryNames()\` |
| \`InstanceNotFoundException\` | Wrong ObjectName, bean not exported, or unregistered | \`isRegistered()\`, lifecycle |
| \`AttributeNotFoundException\` | Management interface does not expose that attribute | \`MBeanInfo\`, assembler/annotations |
| Deserialization exception | Client missing class or type filtered out | OpenTypes/MXBean, classpath, filter |
| Notifications stop after reconnect | Listener not re-registered | Re-subscribe + snapshot |
| \`invoke\` timeout | Slow operation / network failure | MBean implementation, timeout, server health |
| Port is open but remote client cannot connect | Firewall/TLS/RMI secondary port | Server config and network traces |

Do not merely check that a TCP port is listening and conclude that remote JMX is working. With RMI, the connection has multiple phases and may use multiple endpoints.

## 15. Comparing Local JMX and Remote JMX

| Aspect | Local | Remote |
|---|---|---|
| API | \`MBeanServer\` directly | \`MBeanServerConnection\` via connector |
| Network | Requires no network connection outside the JVM | Depends on transport/network |
| Errors | Registration/metadata/invocation | Adds timeout, disconnect, auth, serialization |
| Performance | Usually faster | Has network latency and serialization overhead |
| Listener lifecycle | Within the same JVM | Depends on connection and reconnect |
| Security | Depends on Java environment and caller code | Must explicitly inspect connector/network/auth |
| Invocation result | Local return/exception | Client may not know if server executed when connection drops |

This does not mean local JMX is always safe. A local MBean operation can still mutate critical state. The difference is that remote access introduces an additional trust boundary and distributed system failure modes.

## 16. Operational Best Practices

### Server Design

- Export only the MBeans you need; do not automatically expose all Spring beans.
- Use a consistent ObjectName convention, avoiding collisions across multiple contexts.
- Separate read-only methods from state-mutating methods.
- Use attribute types friendly to remote clients: scalars, Strings, OpenTypes, or appropriate MXBeans.
- Include metrics/logs to detect connector failures.
- Manage the connector lifecycle: startup, shutdown, port binding, and cleanup.

### Client Design

- Set connect/read timeouts according to the implementation's capabilities.
- Do not blindly retry non-idempotent \`invoke\` calls.
- Use bounded backoff when reconnecting.
- Re-register listeners and refresh state after reconnecting.
- Read \`MBeanInfo\` when you need to verify attributes/operations.
- Do not treat notifications as a persistent event log.
- Close \`JMXConnector\` when it is no longer needed.

### Deployment Safety

- Avoid exposing remote JMX to the Internet.
- Protect the transport channel, credentials, and administrative permissions.
- Check both the RMI registry port and the actual endpoint port.
- Determine the hostname that the server advertises to clients.
- In Kubernetes/Docker, consider network routing, service discovery, NAT, and the security model.
- Test connecting from the actual production network/client runtime, not just \`localhost\`.

## 17. Suitable Architecture Example for a Spring Application

\`\`\`text
   Spring Boot / Spring Framework application
                    |
               Business beans
                    |
               JMX monitor beans
                    |
                MBeanExporter
                    |
          Platform MBeanServer
             /            \
      JVM MXBeans      App MBeans
             \            /
              JMXConnectorServer
                    |
              Protected network
                    |
              JMXConnector client
                    |
            MBeanServerConnection
                    |
            Admin/monitoring tool
\`\`\`

Path when reading a metric:

1. Client obtains \`JMXServiceURL\`.
2. Client connects via \`JMXConnectorFactory\`.
3. Client obtains \`MBeanServerConnection\`.
4. Client queries the matching ObjectName.
5. Client reads the attribute via \`getAttribute()\`.
6. Connector server forwards the call to the MBeanServer.
7. MBean is invoked, and the value is serialized back to the client.
8. Client handles the result/exception and manages the connection lifecycle.

The path when invoking an operation can be similar, but requires special attention to access permissions and idempotency.

## 18. Practice Exercises

### Exercise A — Minimal Remote Client

1. Enable a JMX connector in a test JVM with a secure network configuration.
2. Create a \`JMXServiceURL\`.
3. Use \`JMXConnectorFactory.connect()\`.
4. Query \`java.lang:type=Memory\`.
5. Read \`HeapMemoryUsage\` and print the \`used\` value.
6. Close the connector.

### Exercise B — Spring Bean Over Remote

1. Create a \`QueueMonitor\` Spring bean.
2. Export it using \`MBeanExporter\` into the platform MBeanServer.
3. Verify locally using \`isRegistered()\`.
4. Connect remotely to a connector attached to the same server.
5. Read \`PendingCount\` from another JVM.
6. Compare the behavior when the MBean has not been exported and when the client connects to the wrong server.

### Exercise C — RMI and Firewalls

1. Start the connector in a test environment.
2. Check the registry port.
3. Observe the advertised host/port of the RMI endpoint.
4. Test the client from another JVM.
5. Explain why opening only the registry port may not be enough.

### Exercise D — Disconnection

1. Register a listener for an MBean that emits notifications.
2. Disconnect the connection.
3. Have the MBean emit notifications while the client is offline.
4. Reconnect and re-register the listener.
5. Read a snapshot and compare it against expectations.
6. Explain why a client cannot infer the complete history from JMX notifications alone.

## 19. Self-Check Questions

**Question 1.** What problem does JSR-160 solve?  
**Answer:** It provides the JMX Remote API and connector architecture allowing clients to manage MBeans on an MBeanServer remotely.

**Question 2.** Does \`MBeanExporter\` automatically open a JMX remote port?  
**Answer:** No. The exporter registers MBeans; a connector server opens the remote access path separately.

**Question 3.** Is \`JMXServiceURL\` the ObjectName of an MBean?  
**Answer:** No. The URL locates the connector; ObjectName identifies an MBean within the server.

**Question 4.** Which API does a remote client call to read MBeans?  
**Answer:** Obtain \`MBeanServerConnection\` from \`JMXConnector\`, then call \`getAttribute()\`, \`queryNames()\`, \`invoke()\`, etc.

**Question 5.** Why can an RMI registry port be open yet still time out?  
**Answer:** The RMI stub may advertise a different endpoint hostname/port that is not reachable through the network/NAT/firewall.

**Question 6.** Does reconnecting automatically replay all past notifications?  
**Answer:** You should not assume so. You must re-register listeners and synchronize state; if durable history is required, a separate event store is needed.

**Question 7.** Does a remote \`invoke()\` timeout guarantee that the operation did not run?  
**Answer:** No. The server may have already executed it while the response was lost; retries must consider idempotency.

## 20. Key Takeaways

- **JSR-160** defines the JMX Remote API: connector server, connector client, service URL, and connection interface.
- \`MBeanServer\` stores MBeans; \`JMXConnectorServer\` provides the access endpoint; \`JMXConnector\` connects the client; \`MBeanServerConnection\` executes management calls.
- Spring's \`MBeanExporter\` does not create a remote connector automatically.
- RMI/JNDI may have separate registry lookup and invocation endpoints, requiring careful network configuration.
- Remote JMX requires authentication, authorization, transport protection, and network restrictions.
- Network errors give remote calls different failure semantics from local calls; in particular, never blindly retry operations with side effects.
- Remote notifications do not provide durable replay by default.
- Check the exact MBeanServer, ObjectName, connector URL, and client permissions when diagnosing issues.

### References

- Java SE 21 API — JMX Remote package: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/package-summary.html
- Java SE 21 API — \`JMXServiceURL\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXServiceURL.html
- Java SE 21 API — \`JMXConnector\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE 21 API — \`JMXConnectorServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorServer.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- JSR-160 specification page: https://jcp.org/en/jsr/detail?id=160

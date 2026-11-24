# RMI Connector and Related Components in Spring Framework JMX

## 1. The RMI Connector in the JMX Ecosystem

JMX (Java Management Extensions) manages MBean objects within an MBeanServer. When a Spring application wants to allow JConsole, VisualVM, or a client running in another JVM to access MBeans, it needs to open a **JMX connector**. The commonly used protocol is RMI (Java Remote Method Invocation).

Four components must be distinguished:
- **MBeanServer:** the registry holding MBeans and executing operations such as getAttribute, invoke, and queryNames.
- **JMXConnectorServer:** the server-side endpoint, translating client requests into calls to the MBeanServer.
- **RMI Registry:** a name lookup service that helps clients locate the stub of the remote connector.
- **JMXConnector and MBeanServerConnection:** the client side, allowing Java code to access MBeans remotely.

Spring's MBeanExporter places beans into an MBeanServer; exporting beans **does not automatically open a remote JMX port**. The connector must be configured and started separately, or provided by the JVM management agent.

## 2. Two-Stage Connection Flow

Typical model:

~~~text
                   Spring Application JVM
      +-------------------------------------+
      | MBeanExporter -> MBeanServer        |
      |                         ^           |
      |                         |           |
      |                JMXConnectorServer   |
      |                         |           |
      +-------------------------|-----------+
                                | RMI stub
                          RMI Registry
                                ^
                                | 1. lookup "jmxrmi"
                                |
                JConsole / JMXConnector
                                |
                                | 2. use address inside stub
                                v
                       RMI endpoint
                                |
                                v
                     MBeanServerConnection
~~~

The RMI Registry is only a place to look up the stub; it does not contain MBeans. Clients typically connect to the registry first, then call the actual endpoint advertised by the stub. That is why **being able to reach the registry port does not prove JMX connectivity works**.

A common service URL address:

~~~text
service:jmx:rmi:///jndi/rmi://host.example.internal:9010/jmxrmi
~~~

Where:
- \`service:jmx:rmi\` selects the RMI JMX connector protocol.
- \`/jndi/rmi://host:9010/jmxrmi\` specifies where to look up the remote object via JNDI/RMI.
- \`jmxrmi\` is the binding name commonly used when the JVM management agent provides the connector.
- The returned RMI stub may contain a **different host and port** from the lookup endpoint.

Do not interpret the service URL like an HTTP URL or assume all network packets will pass through port 9010.

## 3. MBeanServer and JMXConnectorServer

Creating or obtaining the platform server:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();
~~~

A JVM can also contain an application-created MBeanServer:

~~~java
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.createMBeanServer("com.example.management");
~~~

When initializing the connector, attach it to **the same server** where MBeanExporter registered the MBeans. If the exporter writes to a custom server while the connector reads the platform server, a client may connect successfully yet see none of the application's MBeans.

Creating a connector via the JMX API:

~~~java
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer server = /* configured server */;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
);

JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        url, Map.of(), server
    );

connector.start();

// When the application stops:
// connector.stop();
~~~

This example assumes an appropriate RMI Registry already exists on port 9010. It only illustrates wiring and is **not a complete security configuration**: authentication, authorization, TLS, and network isolation are required for administrative endpoints.

## 4. What Is the RMI Registry Used For?

The RMI Registry maps a name such as \`jmxrmi\` to a remote reference. A registry can be created in the same JVM:

~~~java
import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

Registry registry = LocateRegistry.createRegistry(9010);
~~~

If the port is already occupied by another process, creating the registry may fail. In a container/application server, clearly determine which component owns the registry; do not create a new registry for every Spring bean when a shared registry already exists.

When JMXConnectorServer starts, the connector can register its stub in the registry via the JNDI URL configuration. The client uses the binding name to retrieve the stub and execute the second connection step.

The registry is not responsible for:
- deciding which MBeans are exported;
- granting permissions to invoke individual operations;
- converting a Spring bean into a Standard MBean;
- ensuring the RMI address inside the stub is externally reachable.

## 5. Registry Port vs. RMI Server Port

A characteristic of JMX RMI is that two TCP connections can occur:

1. Connecting to the **registry port** to perform the JNDI lookup.
2. Connecting to the **RMI connector endpoint** described in the stub.

Example JVM management agent configuration:

~~~text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.example.internal
~~~

In this model, the client needs access to port 9010 for lookup and port 9011 to call the RMI endpoint. If only 9010 is permitted through the firewall, lookup can complete while subsequent calls fail.

The \`com.sun.management.jmxremote.*\` properties are for the JVM management agent; they do not necessarily control a custom connector created by the application with \`JMXConnectorServerFactory\`. For self-created connectors, configure the endpoint port/socket factory according to the API and implementation in use.

Do not pick a random port in production if network policy requires whitelisting fixed ports.

## 6. java.rmi.server.hostname and the Advertised Address

The RMI stub can contain the host that the client must connect to. If the server runs inside a container, the container's internal IP address is usually not directly reachable from an administrative workstation.

Failure example:

~~~text
Laptop -> localhost:9010 (port-forward) -> RMI Registry
Registry -> returns stub with host 172.18.0.5:9011
Laptop -> 172.18.0.5:9011 -> timeout
~~~

A port check against the registry can still report success, yet the client cannot use the stub.

You must determine:
- the advertised RMI address;
- the actual port in the stub;
- the client's network path;
- NAT, tunnels, firewalls, Docker port mapping, or Kubernetes port-forward;
- whether DNS/hostname is resolvable by the client.

\`java.rmi.server.hostname\` can be used to control the hostname advertised for RMI objects in compatible configurations. For remote clients, do not set the hostname to \`localhost\` unless tunneling is set up such that the loopback address is genuinely the right endpoint on the client side.

In Kubernetes, load balancing may route the registry lookup and the subsequent RMI connection to two different pods. For JMX RMI, a stable connection/tunnel to a specific pod is usually less surprising.

## 7. Java Client Accessing a Remote MBeanServer

The client creates a JMXServiceURL, connects, and obtains an MBeanServerConnection:

~~~java
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
            MBeanServerConnection remote =
                connector.getMBeanServerConnection();

            System.out.println("MBean count = " +
                remote.getMBeanCount());

            ObjectName pattern =
                new ObjectName("com.example:*");

            for (ObjectName name :
                    remote.queryNames(pattern, null)) {
                System.out.println(name.getCanonicalName());
            }
        }
    }
}
~~~

Run a probe from the same network location as the failing tool to reproduce DNS, firewall, NAT, and authentication policies. If the server enables authentication or TLS, provide the corresponding client configuration.

The client does not need the bean's implementation class to query standard MBeans. It only needs to know the \`ObjectName\`, attribute/operation names, parameter signatures, and data types it can handle.

## 8. Spring Framework: Wiring Exporter and Connector to the Same Server

Spring Framework provides \`MBeanExporter\` to export beans and \`ConnectorServerFactoryBean\` to manage a connector according to the Spring lifecycle. Illustrative example:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.ConnectorServerFactoryBean;

@Configuration
public class JmxConfiguration {

    @Bean
    MBeanServer mbeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    MBeanExporter mbeanExporter(MBeanServer server) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        // Select beans and metadata per actual configuration.
        return exporter;
    }

    @Bean
    ConnectorServerFactoryBean connectorServer(
            MBeanServer server) throws Exception {
        ConnectorServerFactoryBean factory =
            new ConnectorServerFactoryBean();
        factory.setServer(server);
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
        );
        return factory;
    }
}
~~~

This is only a skeleton showing that both the exporter and connector share the same \`MBeanServer\` instance. To run, you need a pre-created registry, security environment, and actual bean registration configuration. In Spring Boot, JMX auto-configuration or the JVM management agent may have already created similar components; do not instantiate an additional duplicate connector/exporter without clear ownership.

**MBeanExporter does not imply a remote connector**: an MBean can be completely exported without opening any JMX remote port.

## 9. Securing the Remote Connector

Remote JMX can read JVM information and execute operations that affect the application. It must be designed as a sensitive administrative endpoint.

### Authentication

The client can pass credentials in the environment:

~~~java
import java.util.Map;
import javax.management.remote.JMXConnector;

Map<String, ?> env = Map.of(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);
~~~

Then:

~~~java
try (JMXConnector connector =
        JMXConnectorFactory.connect(url, env)) {
    // ...
}
~~~

Do not hard-code passwords in source code or include them in logs. The server must actually be configured with the matching authentication mechanism; merely sending credentials from the client does not enable server protection.

### Encryption

Both network channels involved in registry/bootstrap and the remote endpoint must be protected. Certificate, truststore, and hostname verification must match the deployed RMI model. Do not assume that having one TLS channel means every related channel is protected.

### Authorization and Connection Restrictions

The connector should be placed on an administrative network or controlled tunnel, allowing access only from required clients. Authentication alone does not guarantee per-operation business authorization; for state-changing actions, implement authorization and auditing at the application layer.

Do not open JMX ports to the Internet. Never use \`authenticate=false\` or \`ssl=false\` as a production fix.

## 10. Notifications Passing Through the RMI Connector

Besides reading attributes and invoking operations, a client can register a JMX notification listener:

~~~java
import javax.management.NotificationListener;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example:type=Worker,name=Primary"
);

NotificationListener listener =
    (notification, handback) -> {
        System.out.println(notification.getType());
    };

remote.addNotificationListener(
    name, listener, null, null
);
~~~

The MBean must actually support notifications. With remote JMX, callbacks should not be treated as synchronous calls guaranteed to occur right after an operation finishes: transport and connectivity can introduce latency or channel loss. When the client shuts down, remove listeners when possible and close \`JMXConnector\`; after reconnecting, check whether listeners need to be re-registered.

## 11. Lifecycle and Redeploy

There are at least three types of resources that need clear ownership:

- **MBean registrations:** owned by \`MBeanExporter\` or the management module.
- **JMX connector endpoint:** owned by \`JMXConnectorServer\` or Spring's \`ConnectorServerFactoryBean\`.
- **RMI Registry:** created by the JVM management agent, the application, or infrastructure.

If the Spring context shuts down while the connector/registry still holds references to the old classloader, redeploying the application may hit port-already-in-use errors, stale stubs, or memory leaks.

A sensible shutdown sequence:

1. Stop accepting new management requests at the module-managed endpoint.
2. Stop the module-created connector.
3. Unregister listeners/notification handlers registered by the module.
4. Let the exporter unregister MBeans owned by the context.
5. Clean up the registry if it genuinely belongs to the module; do not destroy a shared registry.

For registries created with \`LocateRegistry.createRegistry\`, unexporting/removal must follow RMI APIs and ownership. Never attempt to close a registry owned by the JVM or another application.

## 12. Common Errors

| Symptom | Error Layer to Check | How to Verify |
| --- | --- | --- |
| Connection refused to registry | Wrong host/port or registry not running | Check listener and URL |
| Registry lookup succeeds then times out | RMI stub advertises unreachable host/port | Check RMI endpoint, firewall, NAT |
| NotBoundException | Binding \`jmxrmi\` is missing from registry | Verify connector started and binding name |
| Address already in use | Registry/connector port collision on startup | Check process owner and lifecycle |
| Authentication failed | Wrong credentials or server policy | Check auth config and secrets |
| TLS handshake failed | Incompatible certificate/truststore/protocol | Check TLS on both client and server |
| Only \`java.lang\` MBeans visible | Connector uses a different server from exporter | Compare MBeanServer instances |
| MBean exists but operation missing | Contract/assembler/mapping mismatch | \`getMBeanInfo\` |
| Old connection breaks after redeploy | Old connector or registry still alive | Stop/cleanup, reconnect |
| Fails only inside containers | Internal advertised address or secondary port | Check hostname and forwarding both channels |

Do not read a network error and immediately assume the Spring exporter failed to register MBeans. Verify the registry and endpoint first, and only then check the MBeanServer.

## 13. Layer-by-Layer Diagnostic Process

\`\`\`text
Does the app have MBeans?
  |
  +-- No -> check exporter, ObjectName, MBean compliance
  |
  +-- Yes -> does connector use the right MBeanServer?
             |
             +-- No -> fix wiring
             |
             +-- Yes -> does registry lookup succeed?
                        |
                        +-- No -> host/port/binding
                        |
                        +-- Yes -> is RMI endpoint in stub reachable?
                                   |
                                   +-- No -> hostname/NAT/firewall
                                   |
                                   +-- Yes -> do auth/TLS succeed?
                                              |
                                              +-- No -> security
                                              |
                                              +-- Yes -> queryNames/getAttribute
\`\`\`

A TCP port test only confirms that a service accepts connections on the tested port. Stronger proof must include \`JMXConnectorFactory.connect\`, \`getMBeanServerConnection\`, \`queryNames\`, and reading a specific application MBean.

For JConsole or VisualVM, verify the tool is connecting to the right JVM/deployment, the right endpoint, and has the necessary access permissions.

## 14. Integration Testing the RMI Connector

Testing in an isolated environment can be implemented as follows:

1. Create a dedicated \`MBeanServer\` using \`MBeanServerFactory.createMBeanServer\`.
2. Create a test Standard MBean with a unique ObjectName.
3. Create an RMI registry on an available local port, ensuring the connector uses that registry.
4. Start \`JMXConnectorServer\`, pinning the endpoint if the test must pass through a firewall/container.
5. Connect using \`JMXConnectorFactory\` from the test client.
6. Use \`MBeanServerConnection.isRegistered\`, \`getAttribute\`, and \`invoke\` to verify the contract.
7. Close the connector client, stop the connector server, unregister the MBean, and release the registry in \`finally\`.

To avoid port conflicts among parallel tests, allocate/reserve ports atomically per test fixture or run tests in isolation. Finding a free port and closing the socket before binding still has a race condition, because another process can claim the port between those two steps.

In Spring integration tests, verify that the exporter and connector receive **the exact same MBeanServer bean**. If using the platform server for easier tool integration, give test ObjectNames a separate namespace.

## 15. When Should You Avoid Using JMX RMI Directly?

In multi-region environments, across multiple NAT layers, or in infrastructure that only allows HTTP, configuring RMI (registry port, endpoint port, advertised host) can be complex.

Alternatives to consider:
- **Micrometer/Prometheus** for metrics and alerting.
- **Spring Boot Actuator** for health/info and some monitoring needs over HTTP.
- **Authenticated, audited internal admin APIs** when business commands are needed.
- **Bridging JMX over another protocol** inside a protected network if MBeans are still needed.

These options do not completely replace JMX: JMX supports a rich model of attributes, operations, and notifications. Choose based on capabilities, network operations, and security standards.

## 16. Key Takeaways

**The RMI connector bridges a JMX client to an MBeanServer over an RMI endpoint.** The registry only helps look up the stub; the actual endpoint may use a different address/port, so both must be checked. In Spring, \`MBeanExporter\` determines which beans become MBeans, while the connector determines which server is accessed remotely. A reliable deployment requires proper wiring, reachable advertised hostname/port, appropriate authentication/TLS, and clean lifecycle teardown.

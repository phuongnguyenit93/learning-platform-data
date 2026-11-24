# Spring Framework JMX — Practice: Remote Connection via JSR-160 in a Test Environment

## 1. Lab Objectives and Scope

JSR-160 (Java Management Extensions Remote API) adds a way for JMX clients to connect to an `MBeanServer` through a connector, typically RMI. Spring Framework uses this API via `MBeanServerConnectionFactoryBean` and JMX abstractions. The goal is to start one JVM with an MBean, open a JMX RMI connector in an isolated test environment, connect from another JVM, read an attribute, invoke a safe operation, and inspect errors when the endpoint is unavailable.

**Important boundary:** This lab uses only loopback `127.0.0.1` and non-sensitive data. Examples without authentication or TLS are suitable only on an isolated development machine to understand the API. Never use that exact configuration on production servers, shared machines, containers with exposed ports, or networks accessible to others.

```text
JVM A — JMX server (loopback only)
  TrainingCounter MBean
           |
       MBeanServer
           |
     JMXConnectorServer
           | JSR-160 / RMI
           |
JVM B — JMX client
  JMXConnectorFactory.connect
           |
  MBeanServerConnection
           |
  getAttribute / invoke / getMBeanInfo

Spring client variant:
  MBeanServerConnectionFactoryBean -> MBeanServerConnection
```

## 2. Background Knowledge

| Component | Responsibility |
|---|---|
| `MBeanServer` | Registry holding MBeans in the target JVM |
| `ObjectName` | Identifies an MBean within an `MBeanServer` |
| `JMXServiceURL` | Address of the JSR-160 connector endpoint |
| `JMXConnectorServer` | Server side providing the remote protocol |
| `JMXConnectorServerFactory` | Creates a connector server from URL, environment, and `MBeanServer` |
| `JMXConnector` | Client session holding the connection and transport resources |
| `JMXConnectorFactory` | Establishes remote connections |
| `MBeanServerConnection` | Client API to query attributes, metadata, and operations |
| `MBeanServerConnectionFactoryBean` | Spring FactoryBean providing a connection for injection into Spring beans |

JSR-160 is the standard remote JMX API, not a single fixed network configuration. This lesson uses RMI and a JNDI/RMI registry because that is a common setup for Java/JMX. An existing `MBeanServer` does not automatically open a remote port; you must start a separate connector server.

## 3. Prerequisites

Requirements:

- A JDK with the `java.management` module and JMX RMI support; e.g., JDK 17+.
- Maven or the Java build tool used in your project.
- Two Java programs running on the same machine to avoid exposing the test connector externally.
- Spring Framework `spring-context` if you want to complete the Spring client section.
- Free loopback ports, e.g., `11099` and `11100`. If these ports are in use, update both server and client code consistently.

You do not need Internet access or remote JVM agent flags via `com.sun.management.jmxremote` for the Java API connector setup in this lesson. Those are two different ways of setting up a connector; avoid enabling both on the same port.

## 4. Create a Sample Standard MBean

First, create the `TrainingCounterMBean` interface, saving the file with the matching name:

```java
package com.example.jsr160;

public interface TrainingCounterMBean {
    int getCount();
    void reset();
}
```

Create the implementation:

```java
package com.example.jsr160;

import java.util.concurrent.atomic.AtomicInteger;

public class TrainingCounter implements TrainingCounterMBean {
    private final AtomicInteger count = new AtomicInteger(7);

    @Override
    public int getCount() {
        return count.get();
    }

    @Override
    public void reset() {
        count.set(0);
    }
}
```

In the JMX Standard MBean convention, an interface named `<ClassName>MBean` defines the contract. Thus `TrainingCounter` implements `TrainingCounterMBean`. The `Count` attribute is read-only, while `reset()` is an operation. Only call `reset` in the lab; never use an operation with side effects on a real service to test connectivity.

## 5. Create a JSR-160 RMI Connector Server in Java

For JMX RMI to work, the example below uses an RMI registry bound to loopback and an RMI server endpoint with a fixed port. Set `java.rmi.server.hostname=127.0.0.1` before exporting RMI objects so the stub does not advertise another network address.

```java
package com.example.jsr160;

import java.lang.management.ManagementFactory;
import java.rmi.registry.LocateRegistry;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

public final class TrainingJmxServer {
    public static void main(String[] args) throws Exception {
        System.setProperty("java.rmi.server.hostname", "127.0.0.1");

        int registryPort = 11099;
        int rmiServerPort = 11100;
        LocateRegistry.createRegistry(registryPort);

        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.training:type=Counter,name=primary"
        );

        if (!server.isRegistered(name)) {
            server.registerMBean(new TrainingCounter(), name);
        }

        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi://127.0.0.1:" + rmiServerPort
              + "/jndi/rmi://127.0.0.1:" + registryPort
              + "/jmxrmi"
        );

        JMXConnectorServer connector =
            JMXConnectorServerFactory.newJMXConnectorServer(
                url, null, server
            );

        connector.start();
        System.out.println("JMX URL: " + url);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("Press Enter to stop...");

        try {
            System.in.read();
        } finally {
            connector.stop();
            if (server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }
    }
}
```

### How it works

1. The registry uses port 11099 for clients to look up the RMI stub.
2. The JMX RMI server uses port 11100 as the exported endpoint in the URL.
3. The connector is attached to the platform MBeanServer already holding `TrainingCounter`.
4. `connector.start()` opens the connector and binds the stub into the registry under `jmxrmi`.
5. The client must be able to reach **both the endpoints returned by the stub**, not just the registry port.
6. When the user presses Enter, the program stops the connector and unregisters the lab's MBean.

**Lab safety note:** `java.rmi.server.hostname` affects the address advertised inside the RMI stub, but it is not a firewall/security boundary guaranteeing sockets only bind to loopback in all JDK configurations. If loopback-only binding must be enforced, use RMI socket factories bound to loopback or sandbox/firewall rules blocking inbound connections; do not assume the hostname property alone isolates the server. Production environments always require authentication, authorization, encryption, and network controls.

## 6. Create a Plain Java Client Connecting Remotely

```java
package com.example.jsr160;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class TrainingJmxClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi://127.0.0.1:11100"
              + "/jndi/rmi://127.0.0.1:11099/jmxrmi"
        );

        try (JMXConnector connector =
                 JMXConnectorFactory.connect(url)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "com.example.training:type=Counter,name=primary"
            );

            System.out.println("Registered: "
                + connection.isRegistered(name));

            Object value = connection.getAttribute(name, "Count");
            System.out.println("Count before: " + value);

            connection.invoke(
                name, "reset", new Object[0], new String[0]
            );

            System.out.println("Count after: "
                + connection.getAttribute(name, "Count"));
        }
    }
}
```

With the lab server, the client is expected to print `Count before: 7` and `Count after: 0` if no other actor intervened. The remote test performs operations through `MBeanServerConnection`, with no direct reference to JVM A's Java objects.

In the lab, run `TrainingJmxServer` in a first terminal, then run `TrainingJmxClient` in a second terminal. Do not shut down the server JVM before the client completes.

## 7. Discover MBeanInfo Over the Remote Connection

Read metadata to verify the right server and contract:

```java
ObjectName name = new ObjectName(
    "com.example.training:type=Counter,name=primary"
);

var info = connection.getMBeanInfo(name);
System.out.println(info.getClassName());

for (var attribute : info.getAttributes()) {
    System.out.printf(
        "%s type=%s read=%s write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(operation.getName());
}
```

Here, `Count` must show as readable and not writable, and `reset` is a zero-parameter operation. `MBeanInfo` is also helpful when management tools hit `AttributeNotFoundException` or fail to invoke an operation due to a signature mismatch.

## 8. Connect Using Spring MBeanServerConnectionFactoryBean

Spring Framework lets you declare a remote connection as a Spring bean. Example Java configuration:

```java
package com.example.jsr160;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class TrainingJmxClientConfig {
    @Bean
    public MBeanServerConnectionFactoryBean remoteMBeanConnection()
            throws Exception {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            "service:jmx:rmi://127.0.0.1:11100"
              + "/jndi/rmi://127.0.0.1:11099/jmxrmi"
        );
        return factory;
    }
}
```

With the FactoryBean, Spring injects its **product**—an `MBeanServerConnection`—into services, instead of making every service create and close a `JMXConnector` itself:

```java
package com.example.jsr160;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public class RemoteTrainingReader {
    private final MBeanServerConnection connection;

    public RemoteTrainingReader(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public int getCount() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.training:type=Counter,name=primary"
        );
        return (Integer) connection.getAttribute(name, "Count");
    }
}
```

Bean wiring:

```java
@Bean
RemoteTrainingReader remoteTrainingReader(
        @Qualifier("remoteMBeanConnection")
        MBeanServerConnection connection) {
    return new RemoteTrainingReader(connection);
}
```

The application needs to import `org.springframework.beans.factory.annotation.Qualifier`. The FactoryBean is convenient for dependency injection, but it does not mean Spring automatically reconnects after every network outage. If the client starts before the lab server, the context may fail during connection creation depending on configuration and initialization timing.

## 9. Handling Credentials on the Client

In production, JMX connectors must have authentication and authorization. With a connector supporting JMX credentials, the client can pass an environment map:

```java
import java.util.HashMap;
import java.util.Map;
import javax.management.remote.JMXConnector;

Map<String, Object> env = new HashMap<>();
env.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);

factory.setEnvironment(env);
```

The lab's unauthenticated RMI connector does not represent a production setup; **never treat passing credentials on the client as securing the server**. The server must enforce an authenticator/authorization, transport must be encrypted, and credentials must come from a secret manager. Never commit passwords to Git or log `env`.

## 10. Connecting Remotely with JConsole

To try the management UI:

1. Run the lab server JVM.
2. Open `jconsole` from the JDK.
3. Select **Remote Process** (or the corresponding connection field).
4. Enter the JMX service URL printed by the server.
5. Connect and open the **MBeans** tab.
6. Find the `com.example.training` domain and ObjectName `type=Counter,name=primary`.
7. Read the `Count` attribute and invoke the `reset()` operation in the test environment.

Different JConsole versions may format JMX URL input slightly differently. If connecting with JConsole fails while the Java client succeeds, check the URL, RMI connector support, JDK version, endpoint, and server JVM status.

## 11. Common JSR-160 Connection Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `Connection refused` at registry | Registry not running, wrong port, server not started | Check server JVM and port 11099 |
| Registry connects but RMI call fails | Stub returns unreachable hostname/port | Check `java.rmi.server.hostname` and port 11100 |
| `UnknownHostException` | Hostname in URL or RMI stub does not resolve | Use loopback in lab; check DNS |
| `IOException` during connect | Endpoint not ready or broken transport | Check `connector.start()`, network, cause chain |
| `SecurityException` | Authentication/authorization policy rejected call | Check server config and credentials |
| `InstanceNotFoundException` | ObjectName not registered in target server | `queryNames`, `isRegistered` |
| `AttributeNotFoundException` | Wrong attribute name, e.g., `count` instead of `Count` | Read `MBeanInfo.getAttributes()` |
| `ReflectionException` | Wrong operation name or signature | Read `MBeanInfo.getOperations()` |
| Client connects but does not see MBean | Connector attached to wrong MBeanServer or wrong ObjectName | Compare registry and server reference |
| Client runs after server stops | Connector/session closed | Restart server and open a new connection |

**Do not label every connection failure as an authentication error.** DNS/TCP/RMI can fail before the target JVM ever checks username/password. A `SecurityException` should also be classified by whether it occurred during connect or invoke.

## 12. Testing Connection Loss

Perform this test sequence:

1. Start the server and connect the client successfully.
2. Read `Count` and verify a valid value.
3. Stop the server by pressing Enter.
4. Call the client again; verify it receives a clear transport error rather than concluding the MBean does not exist.
5. Restart the server.
6. Open a new connection and check `Count` under the fresh state.

Do not assume an old `MBeanServerConnection` reference automatically returns to a healthy state after the target JVM restarts. A real monitoring application needs health checks, reconnect backoff, and explicit connector lifecycle management.

## 13. RMI Issues with Docker, NAT, and Kubernetes

In complex networks, opening only the registry port is not enough: the RMI stub can carry a different server address and a second port. If the advertised hostname is a container-internal address that clients outside the container cannot route to, registry lookup may still succeed while JMX invocations fail.

In production you must design:

- A hostname reachable from clients.
- Specific registry and RMI server ports.
- SSL/TLS with appropriate certificates and truststores.
- Firewall/network policies restricting connection sources.
- Authentication and authorization.
- Monitoring for connections, authentication failures, timeouts, and reconnects.

Never copy the lab's loopback/unauthenticated connector into production; never randomly open RMI ports to the Internet to fix connectivity errors.

## 14. Comparing Local and Remote Access

| Criterion | Local MBeanServer | Remote JSR-160 connection |
|---|---|---|
| How obtained | `ManagementFactory.getPlatformMBeanServer()` | `JMXConnectorFactory.connect(...)` |
| Boundary | Same JVM | Over network/transport |
| Latency | In-process Java call | Depends on RMI/network |
| Authentication | Per in-JVM permissions | Must configure connector authentication |
| Common errors | MBean registration/contract | Plus DNS, TLS, network, timeouts |
| Cleanup | Owner of MBean registration | Connector lifecycle and listener subscriptions |

Each JVM has its own MBeanServer. A client JVM calling `ManagementFactory.getPlatformMBeanServer()` only accesses **the client's own server**, not JVM A's server. To view MBeans in JVM A, you need a remote connection or a tool attached to that JVM.

## 15. Extension Exercises

### Exercise 1 — Read an attribute

Do not call `reset`. Use `MBeanServerConnection` to read `Count`, print the Java type of the result, and print the current ObjectName.

### Exercise 2 — Metadata

Read `MBeanInfo` to determine whether `Count` is writable, how many parameters `reset` takes, and try querying with an ObjectName pattern.

### Exercise 3 — Invalid URL

Change the client registry port to a port with no server. Observe the exception and classify it as a transport failure; do not call it a wrong password.

### Exercise 4 — Parameterized operation

Add `setCount(int value)` to the Standard MBean. From the client, invoke with params `new Object[]{5}` and signature `new String[]{"int"}`. Because the primitive method signature is `int`, do not use `"java.lang.Integer"` in the signature.

### Exercise 5 — Spring injection

Use `MBeanServerConnectionFactoryBean` to inject the connection into `RemoteTrainingReader`, read `Count`, and compare the result with the plain Java client.

### Exercise 6 — Auth test

Add a simple `JMXAuthenticator` in an **isolated test environment** using fixture credentials. Test valid/invalid login, without brute-forcing or logging passwords.

## 16. Lab Completion Checklist

- Server JVM registers `TrainingCounter` in the `MBeanServer`.
- Connector server is started and prints the JMX URL.
- Client connects via JSR-160 and obtains `MBeanServerConnection`.
- ObjectName is found via `isRegistered`.
- `Count` is read and `reset()` is invoked properly in the lab environment.
- `MBeanInfo` describes the attribute/operation accurately.
- Spring client injects the connection via FactoryBean.
- Endpoint and ports are tested on connection loss.
- Connector and MBean registration are cleaned up on stop.
- Test connector is never exposed to public networks or production.

## 17. Summary

JSR-160 lets JMX clients in another JVM manage MBeans over a connector. This lab created a Standard MBean, registered it with an `MBeanServer`, opened an RMI connector, connected with `JMXConnectorFactory`, and read/invoked through `MBeanServerConnection`. Spring Framework simplifies the client side via `MBeanServerConnectionFactoryBean`. Lab success depends on the right ObjectName, a complete JMX RMI URL, reachable registry/stub endpoints, and clear connector lifecycles. Production environments additionally require strict authentication, authorization, transport security, and network isolation.
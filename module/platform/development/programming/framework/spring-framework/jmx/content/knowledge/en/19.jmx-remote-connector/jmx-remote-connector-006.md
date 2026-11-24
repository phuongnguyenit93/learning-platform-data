# MBeanProxyFactoryBean with a Remote Server Connection

## 1. Context and Objectives

JMX (Java Management Extensions) is not just for tools running in the same JVM. A Spring application may need to read the state of a Java service on another machine, invoke management operations, or connect to an MBeanServer exposed through a remote connector. If application code interacts directly with `MBeanServerConnection`, every attribute read must call `getAttribute`, every operation must pass its name and signature to `invoke`, and the client must handle JMX data types. Spring Framework provides `MBeanProxyFactoryBean` so the client can invoke a **strongly typed Java interface**, while the actual calls are still forwarded to the MBean over the remote JMX connector.

Example:

```java
// Instead of:
Object value = connection.getAttribute(
    new ObjectName("demo.service:type=Worker,name=primary"),
    "ActiveJobs"
);

// We want:
int active = workerManagement.getActiveJobs();
```

In the second case, `workerManagement` is a JMX proxy, not a local target instance. Methods on the proxy trigger queries to the MBeanServer across the connection.

This lesson focuses on:

- The roles of `JMXServiceURL`, `JMXConnector`, `MBeanServerConnection`, and `ObjectName`.
- How `MBeanProxyFactoryBean` creates a proxy for a management interface.
- Configuring a remote connection via Spring and distinguishing `MBeanServerConnectionFactoryBean` from the proxy.
- Connector lifecycle and errors when the target MBean is not registered or the connection drops.
- Connection safety, authentication, data handling, timeouts, retries, and operations with side effects.
- Simple client/server examples and how to verify results using metadata.

## 2. Diagram of a Call's Path

```text
JVM client / Spring ApplicationContext
    |
    | workerManagement.getActiveJobs()
    v
MBeanProxyFactoryBean -> typed management proxy
    |
    v
MBeanClientInterceptor
    |
    | JMX request via MBeanServerConnection
    v
JMXConnector (client)
    |
    | remote transport: typically RMI/JMX
    v
JMXConnectorServer (server JVM)
    |
    v
MBeanServer
    |
    | ObjectName: demo.service:type=Worker,name=primary
    v
Registered MBean (target JVM)
    |
    v
Business service / runtime state
```

Roles to keep distinct:

| Component | Which Side? | Purpose |
|---|---|---|
| `MBeanExporter` | Spring Server (if using Spring) | Registers beans into the MBeanServer |
| `JMXConnectorServer` | Server JVM | Exposes MBeanServer over a remote protocol |
| `JMXServiceURL` | Client | Locates the connector endpoint |
| `JMXConnector` | Client | Manages the connection to the JMX server |
| `MBeanServerConnection` | Client | Interface for interacting with the MBeanServer |
| `MBeanProxyFactoryBean` | Spring Client | Creates a typed proxy to invoke MBeans |
| `ObjectName` | Both | Identifies the MBean on the server |
| Management interface | Client and server by contract | Getter/setter/operation signatures |

The proxy **does not create a remote connector server**, does not export the target MBean itself, and does not make an endpoint without a JMX connector reachable. Those are three independent responsibilities.

## 3. MBeanServerConnection: A Shared Contract for Local and Remote

`javax.management.MBeanServerConnection` defines operations such as:

```java
Object value = connection.getAttribute(name, "ActiveJobs");

connection.setAttribute(
    name, new Attribute("WarningThreshold", 50)
);

connection.invoke(
    name,
    "pause",
    new Object[0],
    new String[0]
);
```

For a **local** connection:

```java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
```

For a **remote** connection, the client typically obtains that interface from a `JMXConnector`:

```java
JMXServiceURL url = new JMXServiceURL(serviceUrl);
JMXConnector connector = JMXConnectorFactory.connect(url, environment);
MBeanServerConnection connection = connector.getMBeanServerConnection();
```

Although the caller uses the same interface, remote calls introduce factors absent in local calls: networking, authentication, firewall limits, sessions, connection failures, latency, serialization, and the possibility that an operation executed even though the client never received a response.

**Remote JMX is a privileged administrative interface.** Do not expose the connector to the public Internet; do not disable authentication or TLS just to run a quick example. Actual settings for ports, RMI host, and SSL depend on deployment topology and must be determined with the operations team.

## 4. Management Interface as the Client-Side Contract

Suppose the server has registered a Standard MBean at:

```text
demo.service:type=Worker,name=primary
```

Management interface:

```java
// WorkerManagementMBean.java
public interface WorkerManagementMBean {
    int getActiveJobs();
    int getWarningThreshold();
    void setWarningThreshold(int threshold);
    void pause();
    void resume();
}
```

By JMX convention:

- `ActiveJobs`: read-only attribute.
- `WarningThreshold`: read–write attribute.
- `pause()`, `resume()`: operations.

The server can implement:

```java
public class WorkerManagement
        implements WorkerManagementMBean {
    private volatile int activeJobs = 3;
    private volatile int warningThreshold = 100;
    private volatile boolean paused;

    @Override
    public int getActiveJobs() {
        return activeJobs;
    }

    @Override
    public int getWarningThreshold() {
        return warningThreshold;
    }

    @Override
    public void setWarningThreshold(int threshold) {
        if (threshold < 1 || threshold > 1000) {
            throw new IllegalArgumentException("threshold: 1..1000");
        }
        warningThreshold = threshold;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }

    public boolean isPausedInternally() {
        return paused;
    }
}
```

Because the class named `WorkerManagement` implements `WorkerManagementMBean`, it follows the Standard MBean convention. The `isPausedInternally()` method is not part of the management interface, so it is not exposed via that Standard MBean.

On the client, we need an interface compatible in names, signatures, and types. The client can reuse the same Java artifact containing the management interface, or maintain a compatible contract copy. **The server's implementation class is not strictly required**, but the client must understand the data types appearing in the interface.

If the server uses a Spring ModelMBean generated from annotations/assemblers, inspect the actual `MBeanInfo` to ensure the attributes and operations on the proxy interface map accurately. A client-side interface name does not create new APIs on the server by itself.

## 5. Creating a Proxy from the JDK Before Using Spring

The JDK provides a direct utility:

```java
WorkerManagementMBean proxy = JMX.newMBeanProxy(
    connection,
    objectName,
    WorkerManagementMBean.class
);

int current = proxy.getActiveJobs();
proxy.setWarningThreshold(75);
proxy.pause();
```

Here:

- `connection` is the remote `MBeanServerConnection`.
- `objectName` is the `ObjectName` of the registered MBean.
- `WorkerManagementMBean.class` is the interface implemented by the proxy.

The JDK proxy removes hardcoded attribute name strings from the caller, yet connector lifecycle, Spring wiring, and exception handling remain the application's responsibility.

If the target is an MXBean, consider `JMX.newMXBeanProxy(...)`, because MXBeans have OpenType mapping. Do not assume `JMX.newMBeanProxy` will automatically handle all DTO types the way an MXBean proxy does.

## 6. What Does MBeanProxyFactoryBean Provide?

`org.springframework.jmx.access.MBeanProxyFactoryBean` is a Spring `FactoryBean` that creates a proxy object implementing the specified interface. The proxy uses `MBeanClientInterceptor` to translate Java calls into JMX requests.

A consumer bean can use:

```java
public final class OperationsDashboard {
    private final WorkerManagementMBean worker;

    public OperationsDashboard(WorkerManagementMBean worker) {
        this.worker = worker;
    }

    public int activeJobs() {
        return worker.getActiveJobs();
    }

    public void changeWarningThreshold(int value) {
        worker.setWarningThreshold(value);
    }
}
```

The consumer does not need to know the `ObjectName` or call `MBeanServerConnection` directly. Those details are configured on the proxy factory.

However, remember that methods on the proxy can perform **network I/O**, even when the syntax looks like an ordinary Java method:

```java
worker.getActiveJobs(); // Remote round-trip can be slow or fail.
```

Do not call the proxy inside a high-frequency hot loop without considering latency and availability.

## 7. How to Configure Spring: Two Approaches

There are two sensible ways to organize this.

### Approach A — MBeanProxyFactoryBean Manages the Connection

Spring's `MBeanProxyFactoryBean` can configure the remote address via the service URL property it inherits from Spring's JMX client access classes. Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class RemoteJmxProxyConfiguration {

    @Bean
    public MBeanProxyFactoryBean workerManagementProxy() {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();

        proxy.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9999/jmxrmi"
        );
        proxy.setObjectName(
            "demo.service:type=Worker,name=primary"
        );
        proxy.setProxyInterface(WorkerManagementMBean.class);

        // Configure authentication/TLS per connector and infrastructure.
        return proxy;
    }
}
```

The URL above **is only a structural example**, not a connectable endpoint. Do not use it in production without deploying the corresponding connector server, DNS, firewall, and security.

This approach fits when a single proxy directly manages a connection to a single endpoint. When you need to manage multiple proxies, reuse a connection, or control the connector lifecycle separately, consider Approach B.

### Approach B — Configure MBeanServerConnectionFactoryBean and Attach It to the Proxy

Spring provides `org.springframework.jmx.support.MBeanServerConnectionFactoryBean` to build an `MBeanServerConnection` from a service URL.

```java
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class SharedRemoteConnectionConfiguration {

    @Bean
    public MBeanServerConnectionFactoryBean remoteJmxConnection() {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();

        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9999/jmxrmi"
        );

        // Add the environment map and connector settings
        // according to the deployed security system.
        return factory;
    }

    @Bean
    public MBeanProxyFactoryBean workerManagementProxy(
            MBeanServerConnection remoteConnection) {
        MBeanProxyFactoryBean proxy = new MBeanProxyFactoryBean();
        proxy.setServer(remoteConnection);
        proxy.setObjectName(
            "demo.service:type=Worker,name=primary"
        );
        proxy.setProxyInterface(WorkerManagementMBean.class);
        return proxy;
    }
}
```

Here, `setServer(remoteConnection)` instructs the proxy to use an already supplied `MBeanServerConnection`. Ensure Spring resolves the FactoryBean's produced bean properly and do not configure two conflicting connection strategies on the same proxy simultaneously.

**Important rule:** choose A or B based on connector ownership. Do not assume each `MBeanProxyFactoryBean` shares a connection if each proxy configures its own service URL; and do not create unnecessary connections if one centrally managed connection already satisfies the requirements.

## 8. Configuring Credentials and Connector Environment

In Java JMX, `JMXConnectorFactory.connect` accepts an environment map. For connectors using username/password authentication, the common key is `JMXConnector.CREDENTIALS`, which accepts a two-element `String[]`.

Illustrative example in a Java SE client:

```java
Map<String, Object> env = new HashMap<>();
env.put(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);

JMXConnector connector = JMXConnectorFactory.connect(
    serviceUrl,
    env
);
```

With Spring, you can pass the environment map via the corresponding connector configuration API:

```java
Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[]{username, password}
);

// factory.setEnvironmentMap(environment);
```

The snippet above shows the configuration shape; available setter names, reconnection capability, and runtime behavior must be verified against the Spring version in use.

**Never hard-code real credentials in source code.** Retrieve them from a secret manager or protected configuration. Avoid writing raw credentials to logs, exception messages, MBean attributes, or debug dumps.

Also do not assume that simply passing username/password enables TLS automatically. Authentication and transport protection are independent configurations on the connector/server and infrastructure; both sides must be checked.

## 9. Connection Lifecycle: Spring Bean and Network Session

A remote proxy has at least three states to care about:

1. **The Spring bean/proxy has been created.**
2. **The connector has established a session to the remote JMX server.**
3. **The target MBean is registered and can handle operations.**

These states are not equivalent. For example, while the server is still STARTING, the connector may work while the ObjectName is not yet present. Conversely, the MBean may be registered while the connector drops due to networking.

```text
Spring startup
    -> create proxy factory
    -> create connector (may be eager or lazy)
    -> proxy ready for caller to use
    -> remote target MBean exists / does not exist
    -> caller invokes operation/attribute
```

Spring's methods and options can change **when the connection/metadata are checked**, but cannot eliminate runtime errors. A successful application startup does not mean the remote MBean will always remain reachable.

When the application shuts down, factories/connectors managed by Spring should close sessions properly. Never create a `JMXConnector` outside the container and forget to call `close()`; that can leak resources, threads, or unnecessary connections.

## 10. Server Example with a Secure Remote Connector: Concepts and Configuration

For a remote client proxy to work, the target JVM must have:

1. An `MBeanServer`.
2. The MBean registered under the right `ObjectName`.
3. A `JMXConnectorServer` listening at a reachable address.
4. Appropriate authentication/transport protection and network policies.

Example snippet registering the target MBean (without opening a remote port):

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "demo.service:type=Worker,name=primary"
);

server.registerMBean(new WorkerManagement(), name);
```

This snippet only registers a local MBean. It does **not** create a `JMXConnectorServer` for remote access.

If deploying remote JMX over RMI, coordinate `com.sun.management.jmxremote.port`, `com.sun.management.jmxremote.rmi.port`, `java.rmi.server.hostname`, SSL, and authentication according to your JDK/infrastructure environment. Values and port numbers should not be copied unconditionally because RMI may need multiple endpoints and is affected by NAT, container port mapping, and firewalls.

Common URL example:

```text
service:jmx:rmi:///jndi/rmi://host.example.internal:9999/jmxrmi
```

**Do not enable remote JMX by adding `authenticate=false` and `ssl=false` on shared machines.** If learning in a personal environment, prefer using a local MBeanServer or a protected, isolated test environment.

## 11. Using JMXConnector Directly in Java SE

To clearly understand the connection flow before using a Spring proxy, here is a Java SE client template:

```java
import java.util.HashMap;
import java.util.Map;
import javax.management.JMX;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteClient {
    public static void main(String[] args) throws Exception {
        JMXServiceURL url = new JMXServiceURL(
            "service:jmx:rmi:///jndi/rmi://host.example.internal:9999/jmxrmi"
        );

        Map<String, Object> environment = new HashMap<>();
        // Supply appropriate authentication mechanism and trust configuration.
        // Do not embed passwords directly in source code.

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url, environment)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName name = new ObjectName(
                "demo.service:type=Worker,name=primary"
            );

            WorkerManagementMBean proxy = JMX.newMBeanProxy(
                connection,
                name,
                WorkerManagementMBean.class
            );

            System.out.println("Active jobs: " + proxy.getActiveJobs());
        }
    }
}
```

This runs when a real remote server exists, access permissions are valid, and the management interface contract matches. This is an integration skeleton, not a self-starting mock server.

Key point: `try-with-resources` ensures the connector is closed upon completion. If the client is a long-running Spring application, delegate session ownership to a lifecycle-managed bean/factory.

## 12. Spring Consumers Only See the Management Interface

When `MBeanProxyFactoryBean` is configured as above, a client bean can inject the interface:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class RemoteOperationsDashboard {
    private final WorkerManagementMBean worker;

    public RemoteOperationsDashboard(
            @Qualifier("workerManagementProxy")
            WorkerManagementMBean worker) {
        this.worker = worker;
    }

    public WorkerSnapshot readSnapshot() {
        return new WorkerSnapshot(
            worker.getActiveJobs(),
            worker.getWarningThreshold()
        );
    }

    public record WorkerSnapshot(
        int activeJobs,
        int warningThreshold
    ) {}
}
```

This code looks like two simple Java getters, yet in reality it makes **two remote JMX calls**. The two values may be captured at two different points in time; do not assume they form an atomic snapshot of the server.

If multiple consistent metrics are needed, design a composite snapshot attribute compatible with JMX type mapping or an operation returning a unified result. For high throughput, use periodic collection, caching, and rate limiting—avoid calling remote JMX continuously for every business request.

### When Client and Server Use Different Interface Versions

Most proxy errors surface **at invocation time**, not at compile time. If the client has `getActiveJobs()` while the server renamed the attribute or changed its return type, the proxy may fail. Treat management interfaces as versioned APIs and verify compatibility using `MBeanInfo`.

## 13. Metadata: Do Not Guess the Contract from Client Code

Before assuming a proxy works, inspect metadata through a raw connection:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("operation=" + op.getName());
}
```

Imports:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
```

Metadata helps confirm:

- `ActiveJobs` exists and is readable.
- `WarningThreshold` has the intended read/write access.
- `pause` and `resume` are operations.
- Whether the ObjectName points to the expected MBean type.
- Whether a deployment changed the contract while the client has not been updated.

Do not automatically dump the **values** of all attributes to "debug metadata", as that can expose sensitive data.

## 14. Common Errors and How to Distinguish Them

A remote proxy has several distinct error classes:

| Scenario | Typical Symptom | What to Check |
|---|---|---|
| Wrong URL or connector not listening | Connection error / `IOException` | Host, port, connector server |
| RMI registry reachable but stub endpoint unreachable | Timeout/connection failure | RMI hostname, port mapping, NAT/firewall |
| Authentication failure | `SecurityException` or auth error | Identity, permissions, auth config |
| TLS/truststore mismatch | Handshake/trust failure | Trust material, TLS configuration |
| ObjectName not registered | `InstanceNotFoundException` or Spring wrapper | Query server, lifecycle |
| Proxy interface differs from MBeanInfo | Attribute/operation invocation error | Metadata, method signature |
| Setter rejects input | Validation exception wrapped by JMX/Spring | Domain rules, input |
| Connection drops after startup | I/O error on subsequent calls | Reconnect strategy, monitoring |
| MBean replaced while client runs | Metadata or calls change | Versioning/registration policy |

**Do not lump every failure into "remote service is down".** A reachable endpoint lacking permissions must be resolved differently from a wrong ObjectName, a TLS trust error, or an unstarted server.

### 14.1. Why Does RMI Sometimes Connect to the First Port and Still Fail?

JMX RMI can use one registry endpoint and a separate remote object endpoint. If the firewall allows the registry while the hostname/port in the stub is unreachable from the client, the connection still fails. In containers or NAT, explicitly configure the appropriate RMI hostname and port rather than just "opening port 9999" and concluding the path is sufficient.

### 14.2. What Exceptions Can a Proxy Throw?

Depending on the Spring/JMX layer, an error may appear as a JMX exception, `IOException`, `MBeanException`, `ReflectionException`, `InvalidAttributeValueException`, `AttributeNotFoundException`, or a translated/wrapped Spring JMX access exception. Clients should classify errors by cause and meaning, not rely strictly on a single exception type across every deployment.

## 15. Timeouts, Retries, and Idempotency

With remote JMX, latency and network disruptions are normal. Distinguish between:

**State-reading getters:** may be retried in certain cases if the logic is purely read-only, though retries must be bounded and must not create a request storm when the server is overloaded.

**Setters or state-mutating operations:** blind retrying can trigger repeated side effects. For example, `rotateKey()`, `restartWorker()`, `clearCache()`, or `incrementCounter()` are not necessarily idempotent.

Suppose:

```text
Client sends pause()
Server executes pause()
Response is lost on the network
Client receives a timeout
```

A timeout **does not prove** the operation did not execute. If the client automatically retries, it may invoke it twice. For critical operations, design:

- Re-readable state, such as `getLifecycleState()`.
- A request ID or idempotency key if supported by the contract.
- Server-side audit logs.
- Bounded retries with exponential backoff where appropriate.
- Explicit timeout handling: check the outcome before sending the command again.
- Never execute side-effecting operations inside a getter just to "confirm".

`MBeanProxyFactoryBean` does not automatically make operations exactly-once.

## 16. Choosing an Appropriate Reconnect Mechanism

A remote connection can drop after the Spring context has started. Depending on the Spring version, `MBeanClientInterceptor` supports options such as refreshing the connection on failure, though you should not assume they handle every network scenario.

Clearly determine:

1. Who owns the `JMXConnector` or connection factory?
2. When the connection breaks, which component closes the old connector?
3. Which component establishes the new session?
4. Does the proxy hold onto the old connection or have a way to refresh?
5. If the server restarts and re-registers the MBean, can the proxy keep calling after reconnecting?
6. When the server is not yet ready, will the client fail fast, return a degraded status, or keep retrying in the background?

If one `MBeanServerConnectionFactoryBean` is shared across many proxies, a single connection failure can affect all of them. Conversely, creating a separate connector per proxy can cause excess sessions and complicate credential management. Choose based on MBean count, endpoint stability, and operational policy.

## 17. Integrating into Spring Boot and Spring Framework

In plain Spring Framework, the server-side exporter can be configured via:

```java
@Configuration
@EnableMBeanExport
public class ServerJmxConfiguration {
}
```

`@ManagedResource` beans can be exported to JMX if the annotation export infrastructure is properly configured. In Spring Boot, JMX export also depends on auto-configuration and `spring.jmx.enabled` in the corresponding version.

However, **Spring JMX export does not mean a remote connector is open**. `spring.jmx.enabled` can allow exporting MBeans into the local MBeanServer without setting up a remote RMI service URL. If another Spring client needs access, the server must still have remote JMX configured securely.

On the client side, `MBeanProxyFactoryBean` only needs the management interface, ObjectName, and connection. It does not require the server to also run Spring; the server can be any JVM providing a valid MBean over a compatible connector.

## 18. Security Notes for Remote JMX Proxies

Remote JMX can allow reading runtime data and invoking operations with side effects. An unprotected administrative endpoint can be more dangerous than a read-only metrics endpoint.

Principles to apply:

1. **Network restrictions:** allow only administrative hosts/segments to access it; avoid the public Internet.
2. **Authentication:** use a supported authentication mechanism and manage secrets securely.
3. **Encryption:** establish TLS or a suitable protected channel from client to server.
4. **Authorization:** monitoring identities typically need read-only access; state-changing operations require tighter restrictions.
5. **Do not expose secrets:** MBean getters must not return passwords, tokens, private keys, or raw configurations.
6. **Auditing:** record critical administrative actions on the server.
7. **Do not log credentials:** check logging in the client, connector, proxy, and exception handling.
8. **Protect key material:** truststores, keystores, and credential providers must have proper file permissions.
9. **Avoid unintended remote operations:** do not expand the management interface just for "quick debugging".
10. **Account for network and RMI topology:** registry/stub endpoints must be protected consistently.

Do not use `authenticate=false` or `ssl=false` as the default answer for labs in shared environments. If no secured remote endpoint is available yet, learn mapping/proxies with a local MBeanServer first, then implement remote connections in a controlled test environment.

## 19. When the Client Uses an MXBean

An MXBean has type mappings to Open Types. A raw connection can return `CompositeData` or `TabularData`, whereas a JDK typed MXBean proxy can map them back to appropriate Java types when the contract supports it.

```java
StatusMXBean proxy = JMX.newMXBeanProxy(
    connection,
    objectName,
    StatusMXBean.class
);
```

In this example, `StatusMXBean` must be defined and the target must be properly registered as an MXBean. Do not grab an arbitrary `CompositeData` and cast it directly to a Java DTO.

When using `MBeanProxyFactoryBean` for an MXBean, check the Spring version and its corresponding MXBean mapping support. If you need to rely strictly on JDK MXBean semantics, `JMX.newMXBeanProxy` is a clear choice.

## 20. A Practical Design Pattern: Monitoring Facade

Instead of letting many business services call the remote proxy continuously, create a single component to aggregate data:

```text
Remote Worker MBean
         |
Spring JMX proxy
         |
RemoteWorkerMonitor
         |
cached status / bounded polling
         |
dashboard / health endpoint / alert pipeline
```

A simple Java template:

```java
@Service
public class RemoteWorkerMonitor {
    private final WorkerManagementMBean proxy;

    public RemoteWorkerMonitor(
            @Qualifier("workerManagementProxy")
            WorkerManagementMBean proxy) {
        this.proxy = proxy;
    }

    public WorkerStatus sample() {
        return new WorkerStatus(
            proxy.getActiveJobs(),
            proxy.getWarningThreshold(),
            System.currentTimeMillis()
        );
    }

    public record WorkerStatus(
        int activeJobs,
        int threshold,
        long sampledAt
    ) {}
}
```

In production, `sample()` should be called on a bounded schedule or upon user action, not arbitrarily on every request. Store an `UNKNOWN` or `STALE` state when data cannot be fetched, instead of treating a connection error as zero.

Additionally, two JMX getters can reflect two different points in time. If an atomic snapshot is required, design a composite attribute or a dedicated operation on the server.

## 21. Practice Exercises

### Exercise 1 — Raw Connection and Proxy

Use a test JMX endpoint with authentication. Connect via `JMXConnector`, read `ActiveJobs` using `getAttribute`, then read it using `JMX.newMBeanProxy`. Compare the results and log execution times.

### Exercise 2 — Configuring MBeanProxyFactoryBean

Create a Spring context with `MBeanProxyFactoryBean` configured with `serviceUrl`, `objectName`, and `proxyInterface`. Inject the proxy into a consumer bean and read `getActiveJobs()`.

### Exercise 3 — Shared Connection Factory

Define one `MBeanServerConnectionFactoryBean` shared across two proxies corresponding to two different MBeans on the same server. Compare this with each proxy managing its own connection and describe the required ownership/lifecycle.

### Exercise 4 — Unregistered MBean

Keep the connector running but change the ObjectName to a non-existent name. Call the proxy and observe the exception. Check `queryNames` and `getMBeanInfo` to identify the error.

### Exercise 5 — Network Failure Mid-Operation

In a test environment, simulate a response timeout when calling a state-mutating operation. Explain why you must not automatically retry if the operation is not idempotent. Design a state readback or idempotency key.

### Exercise 6 — Security Configuration

List the components that must be secured: service URL, authentication credentials, truststore, firewall, audit logs, and management interface. Describe measures to reduce the risk to sensitive data and operations.

### Exercise 7 — MXBean Mapping

Create an MXBean returning a composite status, read the raw `CompositeData`, and use `JMX.newMXBeanProxy` to observe typed mapping. Compare with a Standard MBean proxy.

## 22. Self-Check Questions

1. What component does `MBeanProxyFactoryBean` create?
2. Why does a proxy not register the target MBean automatically?
3. On which interface are local and remote `MBeanServerConnection` alike, and how do their risks differ?
4. What role does `ObjectName` play in calls made through a proxy?
5. When using a shared connection, which component is responsible for closing the connector?
6. Why can calling a Java getter on a proxy trigger network I/O?
7. What is the difference between an `InstanceNotFoundException` and a connection refused error?
8. Does a timeout after `pause()` prove the server did not execute the operation?
9. Does `spring.jmx.enabled` automatically open a secured remote connector?
10. What measures must be in place before deploying remote JMX in a shared environment?

## 23. Key Takeaways

**`MBeanProxyFactoryBean` is Spring Framework's client-side mechanism for invoking a JMX MBean through a Java management interface.** With a remote connector, calls on the proxy pass through `MBeanServerConnection`, the transport, and the `MBeanServer` on the target JVM; therefore, you must handle network latency, lifecycle, authentication, TLS, API compatibility, and mid-flight failures.

Clearly distinguish **exporting the target**, **opening the connector server**, **creating the connector client**, and **creating the proxy**. Use stable ObjectNames, inspect `MBeanInfo`, manage connections centrally when appropriate, and never assume a timed-out remote operation did not run.

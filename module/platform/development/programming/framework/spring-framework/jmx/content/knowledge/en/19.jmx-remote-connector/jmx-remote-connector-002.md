# MBeanServerConnectionFactoryBean in Spring

## Purpose

Spring Framework provides `org.springframework.jmx.support.MBeanServerConnectionFactoryBean` to configure a JMX client connection as a Spring bean. The created bean has type `javax.management.MBeanServerConnection`, used to query or interact with MBeans already registered in a JVM, typically a remote JVM. This is not `MBeanExporter`: the exporter registers Spring beans into an MBeanServer, whereas the connection factory provides a connection path to access an existing MBeanServer.

## Components

| API | Function |
|---|---|
| `MBeanServer` | Registry of MBeans on the target JVM |
| `MBeanServerConnection` | Interface for querying attributes, operations, and MBean metadata |
| `JMXConnector` | Manages the remote JMX connection transport |
| `JMXServiceURL` | Identifies the connector address |
| `MBeanServerConnectionFactoryBean` | Spring FactoryBean providing a connection for DI |
| `MBeanExporter` | Exports Spring beans as MBeans on the server |

## Java Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class RemoteJmxConfig {
    @Bean
    public MBeanServerConnectionFactoryBean ordersJmxConnection(
            @Value("${app.jmx.orders.url}") String serviceUrl)
            throws Exception {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(serviceUrl);
        return factory;
    }
}
```

Example property: `app.jmx.orders.url=service:jmx:rmi:///jndi/rmi://jmx.example.internal:9999/jmxrmi`. The endpoint only works if the target JVM enables the JMX connector and the network allows access. JMX RMI may use different registry and RMI stub ports, which requires special attention when running in NAT, Docker, or Kubernetes.

## Credentials and Security

```java
Map<String,Object> env = new HashMap<>();
env.put(JMXConnector.CREDENTIALS, new String[] {username, password});
factory.setEnvironment(env);
```

Retrieve username and password from secret management; do not hardcode or log credentials. JMX security requires authentication, authorization, TLS or transport security, and server-side network isolation. The client environment alone does not secure the endpoint.

## Injecting the Connection into a Service

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class RemoteWorkerMonitor {
    private final MBeanServerConnection connection;

    public RemoteWorkerMonitor(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public int activeWorkers() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.app:type=WorkerPool,name=main");
        return (Integer) connection.getAttribute(name, "ActiveWorkers");
    }
}
```

When there are multiple remote connections, use `@Qualifier("ordersJmxConnection")` to inject the right JVM. Remote calls can time out and must not be treated like local Java field access.

## Querying Metadata and Invoking Operations

```java
ObjectName pattern = new ObjectName("com.example.app:type=WorkerPool,*");
for (ObjectName name : connection.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
    var info = connection.getMBeanInfo(name);
    for (var attribute : info.getAttributes()) {
        System.out.println(attribute.getName() + ":" + attribute.getType());
    }
}

ObjectName target = new ObjectName(
    "com.example.app:type=WorkerPool,name=main");
connection.invoke(target, "resize",
    new Object[] {Integer.valueOf(12)}, new String[] {"int"});
```

JMX `invoke` requires the signature according to the method's declared types. `resize(int)` uses `"int"`, not `"java.lang.Integer"`, even though the `Object[]` array contains a boxed value. You should read `MBeanInfo` before hardcoding operation names, parameter types, or writable attributes.

## Lifecycle, Network Errors, and Retry

With direct Java JMX, you can use `JMXConnectorFactory.connect(url)` in `try-with-resources` to close the connector when finished. With the Spring FactoryBean, the connector lifecycle is typically managed by the context according to the implementation; avoid closing a connection that is still in use by other singleton beans.

If the target JVM restarts, the client-side `MBeanServerConnection` reference still exists, but the transport may be broken. `@Lazy` does not guarantee automatic reconnection on its own. When long-lived monitoring is needed, design health checks, retry with backoff, and connection management. **Do not blindly retry operations with side effects** on timeout: the server may have already processed the request while the response was lost.

| Error | Handling |
|---|---|
| `IOException` | Check the network, JMX RMI endpoint, hostname, and port |
| `SecurityException` | Check credentials and server-side JMX permissions |
| `InstanceNotFoundException` | Verify the ObjectName, correct JVM, and MBean registration |
| `AttributeNotFoundException` | Compare the attribute against `MBeanInfo` |
| `ReflectionException` | Check the operation name and signature |
| `MBeanException` | Inspect the exception from the business MBean |
| `ListenerNotFoundException` | Check the notification listener lifecycle |

A notification listener can be registered using `connection.addNotificationListener(name, listener, filter, handback)` and removed using `removeNotificationListener`. Upon reconnect, subscriptions usually must be re-established; JMX Notifications do not replay missed events by default.

## Practice

1. Configure the FactoryBean to a secured test JMX server and use `queryNames` to list MBeans.
2. Read `java.lang:type=Memory` with the `HeapMemoryUsage` attribute (typically `CompositeData` via JMX MXBean mapping).
3. Try invoking a safe operation with the exact signature; check via metadata instead of guessing types.
4. Disconnect the remote connection and observe `IOException`; design reconnect with backoff.
5. Shut down the target JVM after registering a listener; determine the mechanism to re-register when the connection recovers.

## Key Takeaways

`MBeanServerConnectionFactoryBean` turns JMX endpoint configuration into an `MBeanServerConnection` dependency in Spring. It helps decouple connection infrastructure from monitoring code, but it does not replace exporting MBeans on the target JVM, does not guarantee automatic reconnection, and does not waive JMX security requirements. Proper design requires managing ObjectNames, metadata, access permissions, timeouts, lifecycle, and safe retries.

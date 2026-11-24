# Platform MBeanServer and Application-Created MBeanServer

## 1. What Is MBeanServer?

In Java Management Extensions (JMX), an `MBeanServer` is where MBeans (Managed Beans) are registered, looked up, and manipulated. An MBean represents the ability to observe or control a component such as memory, threads, caches, jobs, or business services. Clients use `ObjectName` to locate an MBean, read/write attributes, and invoke operations through `MBeanServer` or a JMX connector.

Multiple `MBeanServer` instances can exist within the same JVM. Two common choices are:

- **Platform MBeanServer**: the shared instance provided by the JVM via `ManagementFactory.getPlatformMBeanServer()`. Java platform MXBeans and many management libraries typically use this instance.
- **Application-created MBeanServer**: an instance created by an application or framework via `MBeanServerFactory.createMBeanServer(domain)` or an equivalent configuration mechanism. It has its own MBean registration namespace and does not automatically contain all MXBeans from the platform server.

Key point to understand: **MBeanServer is the in-process registry and dispatcher inside the JVM; a JMX remote connector is the path for an external client to access it.** Creating an MBeanServer does not mean opening a network port.

## 2. Comparing the Two Server Choices

| Criterion | Platform MBeanServer | Application-Created MBeanServer |
| --- | --- | --- |
| How to obtain | `ManagementFactory.getPlatformMBeanServer()` | `MBeanServerFactory.createMBeanServer("com.example.app")` |
| Owner | JVM and components sharing the platform server | Application/framework that creates and manages its lifecycle |
| Initial contents | Platform MXBeans for the JVM | Typically a fresh registry, separate from platform MBeans |
| ObjectName scope | Shares registration namespace with libraries using the platform server | Separate registration namespace for this server |
| Connection tools | Local JMX tools can usually access the platform server per JVM configuration | Must expose/attach this server to an appropriate connector if external clients need access |
| Suitable scenarios | Managing JVM and application in one common place; the common choice | Isolating a subsystem's MBeans, embedding a dedicated management environment, testing |
| Main risks | `ObjectName` collisions; exposing too many MBeans if connector configuration is broad | Assuming JMX tools will discover it automatically; lifecycle and connector must be managed manually |

A server's `defaultDomain` is not an authorization mechanism and does not create security tenant isolation. Domains in `ObjectName` are logical names; registering the same `ObjectName` on two different servers still creates two independent entries.

## 3. Platform MBeanServer: Choosing When You Want the JVM Ecosystem

Example obtaining the platform server and querying a standard JVM MXBean:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class PlatformServerExample {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName memory = new ObjectName("java.lang:type=Memory");

        System.out.println("Registered: " + server.isRegistered(memory));
        System.out.println("HeapMemoryUsage: " +
                server.getAttribute(memory, "HeapMemoryUsage"));
    }
}
\`\`\`

`HeapMemoryUsage` is an attribute of the Memory MXBean mapped through JMX; clients read data without depending on JVM implementation classes. Note that `javax.management` is the Java SE JMX namespace; do not replace it with `jakarta.management` just because the application uses a newer Spring Framework version or Jakarta EE.

The advantage of the platform server is centralized observation of both JVM and application MBeans, convenient for JConsole, VisualVM, and monitoring systems already connected to the platform server. The drawback is that multiple subsystems share a single registry, so naming and permission management must be consistent.

## 4. Creating a Separate MBeanServer

An application can create its own registry:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

public class PrivateServerExample {
    public static void main(String[] args) throws Exception {
        MBeanServer privateServer =
                MBeanServerFactory.createMBeanServer("com.example.private");

        try {
            ObjectName name = new ObjectName(
                "com.example.private:type=Counter,name=Operations"
            );

            privateServer.registerMBean(new Counter(), name);
            System.out.println(privateServer.getAttribute(name, "Count"));
        } finally {
            MBeanServerFactory.releaseMBeanServer(privateServer);
        }
    }

    public interface CounterMBean {
        int getCount();
        void reset();
    }

    public static class Counter implements CounterMBean {
        private int count = 42;
        public int getCount() { return count; }
        public void reset() { count = 0; }
    }
}
\`\`\`

This is a **Standard MBean**: a public interface suffixed with `MBean` matching the implementation. In production code, place the interface and implementation in clear top-level or static public classes, provide thread-safety for mutable state, and unregister MBeans according to lifecycle before releasing the server.

`MBeanServerFactory.createMBeanServer()` creates a server and adds it to the list of servers tracked by the factory; `newMBeanServer()` creates a server without adding it to that list. `releaseMBeanServer()` is only appropriate for servers created with `createMBeanServer()`, not for the platform server. Releasing from the factory does not replace closing connectors or cleaning up all application-owned resources.

**Separating registries does not mean separating memory or processes.** MBeans on two servers still run in the same JVM and can reference the same services or state if you explicitly wire them. If a connector only points to server A, clients of that connector will not automatically see registry B.

## 5. How Spring Framework Finds and Uses MBeanServer

In Spring JMX, `MBeanExporter` is responsible for exporting beans as MBeans and registering them with an `MBeanServer`. Spring can look up an existing server via `MBeanServerFactoryBean` or use a specific injected server bean. The critical decision is **determining exactly which instance the exporter is using**.

Example Spring configuration explicitly selecting the platform server:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class PlatformJmxConfig {
    @Bean
    public MBeanExporter mbeanExporter(ExampleAdminMBean admin) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(ManagementFactory.getPlatformMBeanServer());
        exporter.setBeans(
            java.util.Map.of("com.example:type=ExampleAdmin", admin)
        );
        return exporter;
    }
}
\`\`\`

Registered objects must follow a valid MBean model (Standard MBean, MXBean, DynamicMBean, or supported by a Spring assembler). When using `@ManagedResource` annotations, configure an appropriate metadata assembler/naming strategy or use the provided auto-configuration.

Example using a separate server and pointing the exporter to it:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class IsolatedJmxConfig {
    @Bean(destroyMethod = "")
    public MBeanServer isolatedMBeanServer() {
        return MBeanServerFactory.createMBeanServer(
            "com.example.isolated"
        );
    }

    @Bean
    public MBeanExporter isolatedExporter(
            MBeanServer isolatedMBeanServer,
            ExampleAdminMBean admin) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(isolatedMBeanServer);
        exporter.setBeans(
            java.util.Map.of("com.example.isolated:type=ExampleAdmin", admin)
        );
        return exporter;
    }
}
\`\`\`

In the second configuration, `destroyMethod=""` does not release the server; it merely prevents Spring from inferring a bean destroy method. If the application owns this server, manage cleanup explicitly with a lifecycle bean, calling `MBeanServerFactory.releaseMBeanServer(server)` on context close after the exporter has unregistered MBeans; also close any application-created `JMXConnectorServer` instances. For production environments, prefer clean lifecycle configuration to avoid lingering registered resources when contexts are recreated.

Spring Boot may auto-configure JMX when `spring.jmx.enabled=true` is enabled. When a Boot-configured `MBeanExporter` already exists, do not add another exporter managing the same MBeans unintentionally; it can lead to duplicate registrations or an exporter pointing to the wrong server. Check the `MBeanServer` and `MBeanExporter` beans and compatibility with your actual Boot version.

## 6. Registering the Same ObjectName on Two Different Servers

An `ObjectName` is scoped within **one MBeanServer**; there is no server-independent JVM-wide namespace.

\`\`\`java
MBeanServer platform =
        java.lang.management.ManagementFactory.getPlatformMBeanServer();
MBeanServer isolated =
        javax.management.MBeanServerFactory.createMBeanServer("custom");

ObjectName name =
        new ObjectName("com.example:type=Cache,name=Local");

// Can exist in both registries if each registration is valid.
platform.registerMBean(new CacheAdmin(), name);
isolated.registerMBean(new CacheAdmin(), name);
\`\`\`

These are two separate registrations. However, registering `name` a second time on the **same server** throws `InstanceAlreadyExistsException`, unless the framework uses a configured collision-handling policy. Do not rely on default MBean replacement behavior without understanding its operational impact.

When you need to see which server holds an MBean, check on each instance directly:

\`\`\`java
boolean inPlatform = platform.isRegistered(name);
boolean inIsolated = isolated.isRegistered(name);
\`\`\`

## 7. Why Might External Tools Not See an MBean?

Common scenario: application logs say "MBean registered" but JConsole does not display the corresponding entry.

Trace across the boundaries:

1. **Right JVM?** Which process is JConsole/VisualVM attached to?
2. **Right server?** Is the bean in the platform server or a separate server? Call `isRegistered(name)` on the exact instance passed to the exporter.
3. **Right name?** `ObjectName` must match domain and key properties. Use `queryNames(pattern, null)` to search in the right server.
4. **Where does the connector point?** A connector created with a given `MBeanServer` only exposes that server's registry.
5. **Read permissions?** The connector may require authentication, TLS, and authorization. Do not disable security to diagnose production.
6. **When was it registered?** The bean/exporter might be created after the client connected, or already unregistered when the Spring context closed.

Example querying registered names:

\`\`\`java
ObjectName pattern = new ObjectName("com.example:*");

for (ObjectName candidate : platform.queryNames(pattern, null)) {
    System.out.println(candidate);
}
\`\`\`

If querying the platform server returns nothing while the isolated server returns results, it is a registry difference, not an MBean failure.

## 8. Connecting Remotely to a Separate Server

A `JMXConnectorServer` binds to a specific `MBeanServer`. Core API example:

\`\`\`java
import java.util.Map;
import javax.management.MBeanServer;
import javax.management.remote.JMXConnectorServer;
import javax.management.remote.JMXConnectorServerFactory;
import javax.management.remote.JMXServiceURL;

MBeanServer server = /* previously created isolated server */ null;
JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

// Illustrates the API signature; the RMI/JNDI URL requires an appropriate registry and network configuration.
// Do not use an empty Map environment as a production remote configuration.
JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        url, Map.of(), server
    );
\`\`\`

This snippet illustrates where `server` is attached, **not a ready-to-run configuration**: you must initialize the RMI registry, supply a real server, start/stop the connector, and configure authentication, TLS, and port/host restrictions. In real deployments, avoid accidentally exposing JMX to the Internet and never leave dangerous operations publicly accessible.

If you only need internal JMX via local attach, a remote connector is usually unnecessary. If you want to monitor both JVM and app in a single connection, the platform server is usually the more direct choice.

## 9. Testing Isolation and Lifecycle

A useful test is creating an isolated server, registering an MBean, and asserting that the platform server does not contain that name:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

class MBeanServerIsolationTest {
    @Test
    void registrationIsScopedToOneServer() throws Exception {
        MBeanServer isolated =
            MBeanServerFactory.createMBeanServer("test");
        ObjectName name =
            new ObjectName("com.example.test:type=Counter,name=One");

        try {
            isolated.registerMBean(new PrivateServerExample.Counter(), name);

            assertTrue(isolated.isRegistered(name));
            assertFalse(
                ManagementFactory.getPlatformMBeanServer()
                    .isRegistered(name)
            );
        } finally {
            if (isolated.isRegistered(name)) {
                isolated.unregisterMBean(name);
            }
            MBeanServerFactory.releaseMBeanServer(isolated);
        }
    }
}
\`\`\`

In real projects, use unique names per test; do not assume the platform server is guaranteed clean if other tests run concurrently and do not reuse existing names. Test Spring context startup/shutdown to confirm the exporter registers and unregisters on the **same MBeanServer**.

An integration test suite should verify: the right server is selected, the MBean has the expected `ObjectName`, attributes/operations work, collisions behave as designed, and resources are released after the context closes.

## 10. Architectural Decisions Based on Needs

**Choose the platform server** when you need to observe JVM and application together, want good tooling compatibility, and have no special registry isolation requirements. This is usually the simplest option for a single-JVM Spring application.

**Choose a separate server** when you genuinely need a separate registration area for a module, embedded container, software hosting multiple subsystems, or a test application needing independent setup/teardown. This choice also brings responsibility for managing exporters, connectors, and lifecycles.

Do not use a separate server as your sole data-protection layer. JMX security must be designed at the connector/transport layer, access permissions, allowed operations, network policy, and application authentication mechanisms.

## 11. Common Mental Pitfalls

- **"Each JVM has only one MBeanServer."** False: multiple registries can be created, though the platform server is the standard, widely used instance.
- **"Having an MBeanServer means JConsole will see it."** False: clients only see the registry that the connector/attach mechanism grants access to.
- **"Same ObjectName means the same MBean."** False when the ObjectNames reside on two different servers.
- **"Changing default domain provides secure isolation."** False: domain is a naming convention, not a security policy.
- **"Releasing a server closes all connectors."** Do not assume that; manage owned resources explicitly.
- **"Spring always picks the server I expect."** Do not assume that; configure or inject the instance explicitly when multiple servers exist.

## 12. Key Takeaways

`MBeanServer` is the registration scope for MBeans. **Platform MBeanServer** is the common, convenient JVM management point; an **application-created MBeanServer** is an independent registry requiring separate management. When using Spring, determine which server the exporter registers into, which server clients connect to, and how the registration/connector lifecycle works. Understanding these three relationships resolves most "MBean exported but not visible" issues and avoids accidentally coupling your architecture to a single management channel.

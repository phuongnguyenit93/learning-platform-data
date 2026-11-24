# The JVM PlatformMBeanServer in Spring Framework JMX

## 1. Overview

In Java Management Extensions (JMX), **MBeanServer** is the component that registers, looks up, and executes management invocations on MBeans. A single JVM can have multiple MBeanServers, but the Java platform provides a shared **platform MBeanServer** for the JVM's platform MBeans that can also be used for application MBeans.

The most important API:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
\`\`\`

In Spring Framework JMX, \`MBeanExporter\` can register Spring-managed beans into the platform MBeanServer, enabling clients such as JConsole, VisualVM, or remote JMX clients to observe and invoke management attributes and operations.

**Core concept:** the platform MBeanServer is a **JVM**-scoped JMX registry, not a Spring bean registry, not an HTTP server, and not an automatic remote connection mechanism.

This lesson helps you:
- Understand the platform MBeanServer provided by the JVM and how it differs from an application-created MBeanServer.
- Know how to obtain and inspect the platform MBeanServer using \`ManagementFactory\`.
- Distinguish \`MBeanServer\`, \`MBeanServerConnection\`, and JMX connectors.
- Configure Spring \`MBeanExporter\` to register into the exact desired server.
- Understand platform MXBeans and the \`java.lang\`, \`java.nio\`, \`com.sun.management\` namespaces in real deployments.
- Analyze risks around ObjectName collisions, multiple ApplicationContexts, lifecycle, and security.
- Choose appropriately when to use the platform server or a custom MBeanServer.

## 2. What is the Platform MBeanServer?

\`ManagementFactory.getPlatformMBeanServer()\` returns the **platform MBeanServer** of the current JVM. If it does not yet exist, the API initializes the platform server; subsequent calls within the same JVM return the already-created platform server instance.

\`\`\`java
MBeanServer first = ManagementFactory.getPlatformMBeanServer();
MBeanServer second = ManagementFactory.getPlatformMBeanServer();

System.out.println(first == second); // true within the same JVM
\`\`\`

The platform server is where the Java runtime registers standard MXBeans reflecting JVM state, such as:

- \`MemoryMXBean\`: heap/non-heap memory and related operations.
- \`ThreadMXBean\`: thread information, deadlock/CPU time within supported scope.
- \`RuntimeMXBean\`: runtime and JVM information.
- \`ClassLoadingMXBean\`: class loading.
- \`GarbageCollectorMXBean\`: garbage collector statistics.
- \`MemoryPoolMXBean\`: memory pools.
- \`OperatingSystemMXBean\`: operating system information per API and implementation.
- \`CompilationMXBean\`: JIT compilation information if supported by the JVM.
- \`BufferPoolMXBean\`: buffer pools.

Not every implementation provides every extension or the exact same set of additional MBeans. Standard MXBeans and ObjectNames can be inspected via Java APIs and on the actual runtime.

### Difference from Creating Your Own MBeanServer

Java provides \`MBeanServerFactory.createMBeanServer(...)\` to create a new server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom = MBeanServerFactory.createMBeanServer(
    "com.example.custom"
);
\`\`\`

This new server **does not automatically become the platform MBeanServer** and does not automatically contain all platform MXBeans registered in the platform server. An MBean registered in the custom server also does not automatically appear in the platform server.

Visualize it:

\`\`\`text
                  JVM Process
               +-------------------+
               |                   |
               | Platform Server   |
               |  java.lang:*      |
               |  app MBeans (A)   |
               |                   |
               | Custom Server     |
               |  app MBeans (B)   |
               |                   |
               +-------------------+
\`\`\`

A JMX client connected to server A does not automatically see MBeans registered only in server B.

## 3. MBeanServer, MBeanServerConnection, and Connector

Three easily confused concepts:

| Component | Role |
|---|---|
| \`MBeanServer\` | JMX registry/runtime inside the JVM, supporting MBean registration and unregistration |
| \`MBeanServerConnection\` | Management and MBean query interface usable locally or over a connection |
| \`JMXConnector\` | Client-side object managing the connection to a JMX connector server |
| \`JMXConnectorServer\` | Server-side component exposing an MBeanServer over a remote connection protocol |
| \`MBeanExporter\` | Spring component registering Spring beans into the selected MBeanServer |

\`MBeanServer\` extends \`MBeanServerConnection\` and adds registration operations. Therefore, local code can use the server directly:

\`\`\`java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
server.queryNames(null, null);
\`\`\`

Meanwhile, a remote client typically receives an \`MBeanServerConnection\`:

\`\`\`java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();
\`\`\`

**Obtaining the platform MBeanServer does not automatically open a network port.** Remote observation depends on connector configuration, authentication, authorization, and JVM/application network settings.

## 4. Initializing the Platform MBeanServer and Inspecting ObjectNames

Plain Java example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

public class PlatformServerInspector {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        System.out.println("Default domain: "
            + server.getDefaultDomain());

        System.out.println("MBean count: "
            + server.getMBeanCount());

        Set<ObjectName> platformNames = server.queryNames(
            new ObjectName("java.lang:*"),
            null
        );

        for (ObjectName name : platformNames) {
            System.out.println(name.getCanonicalName());
        }
    }
}
\`\`\`

Example output may include:

\`\`\`text
java.lang:type=Memory
java.lang:type=Runtime
java.lang:type=Threading
java.lang:type=ClassLoading
java.lang:type=GarbageCollector,name=...
java.lang:type=MemoryPool,name=...
\`\`\`

The names and count of MBeans depend on the runtime; GC and memory pool names vary by JVM, collector, and configuration.

### The Default Domain Does Not Dictate Every MBean

\`server.getDefaultDomain()\` returns the server's default domain. This does **not** mean every MBean must reside in that domain; Java platform MXBeans have their own standard domains such as \`java.lang\`.

When registering your own MBeans, use an explicit domain owned by the application, such as \`com.example.orders\`, avoiding conflicts with system domains.

## 5. Platform MXBeans and JVM State

Platform MXBeans are the standard interface for reading operational data from the JVM.

Example reading memory directly:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

System.out.println(
    "Heap used: " + memory.getHeapMemoryUsage().getUsed()
);
\`\`\`

You can also access it through MBeanServer using ObjectName:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName memoryName =
    new ObjectName(ManagementFactory.MEMORY_MXBEAN_NAME);

Object heapUsage =
    server.getAttribute(memoryName, "HeapMemoryUsage");

System.out.println(heapUsage);
\`\`\`

Because \`MemoryMXBean\` is an MXBean, composite data such as \`MemoryUsage\` can be represented as \`CompositeData\` at the JMX boundary.

\`\`\`java
import javax.management.openmbean.CompositeData;

CompositeData usage = (CompositeData) heapUsage;
long used = (Long) usage.get("used");

System.out.println("Used heap bytes: " + used);
\`\`\`

Calling \`ManagementFactory.getMemoryMXBean()\` directly is convenient when code runs inside the JVM. Going through \`MBeanServerConnection\` is useful for general management tools, including remote ones.

### One Platform Server, Many Information Sources

The platform MBeanServer may contain:
- Platform MXBeans registered by the JVM.
- MBeans from libraries or frameworks.
- MBeans registered by Spring \`MBeanExporter\`.
- MBeans registered directly by application code.

Do not conclude an MBean is a platform MXBean just because it resides in the platform MBeanServer. **The origin of the server** differs from **the origin of each MBean**.

## 6. Spring MBeanExporter and the Platform Server

In Spring Framework, \`MBeanExporter\` has a \`server\` property. Specifying the platform server explicitly:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MBeanServer platformMBeanServer,
            QueueMonitor queueMonitor) {

        MBeanExporter exporter = new MBeanExporter();

        exporter.setServer(platformMBeanServer);
        exporter.setBeans(java.util.Map.of(
            "com.example.orders:type=Queue,name=Orders",
            queueMonitor
        ));

        return exporter;
    }
}
\`\`\`

This snippet assumes \`QueueMonitor\` is already a valid Standard MBean or is adapted appropriately by the exporter. For POJOs using \`@ManagedResource\`/\`@ManagedAttribute\`, a corresponding assembler/annotation export is needed.

### Illustrative Standard MBean

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
    void resetStatistics();
}

public class QueueMonitor implements QueueMonitorMBean {
    private volatile int pendingCount;

    @Override
    public int getPendingCount() {
        return pendingCount;
    }

    @Override
    public void resetStatistics() {
        pendingCount = 0;
    }
}
\`\`\`

From Spring's perspective:

\`\`\`text
ApplicationContext
     |
     +-- QueueMonitor bean
     |
     +-- MBeanExporter bean
               |
               v
       platform MBeanServer
               |
               +-- java.lang:type=Memory
               +-- java.lang:type=Threading
               +-- com.example.orders:type=Queue,name=Orders
\`\`\`

One advantage of specifying the server is avoiding confusion when the JVM has multiple MBeanServers and the JMX client is observing the platform server.

## 7. Using Spring MBeanServerFactoryBean

Spring provides \`org.springframework.jmx.support.MBeanServerFactoryBean\` to obtain or create an MBeanServer based on configuration.

Example of declaring a server bean:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.MBeanServerFactoryBean;

@Configuration
public class JmxServerConfiguration {

    @Bean
    public MBeanServerFactoryBean mBeanServer() {
        MBeanServerFactoryBean factory =
            new MBeanServerFactoryBean();
        factory.setLocateExistingServerIfPossible(true);
        return factory;
    }
}
\`\`\`

This factory bean is useful in Spring JMX configuration, but you should clearly distinguish the locate/create mechanism from requiring **the exact platform server**.

\`locateExistingServerIfPossible\` is not a universal guarantee that the retrieved server is always \`ManagementFactory.getPlatformMBeanServer()\` in every JVM. If the application must guarantee the exact platform server, passing the object directly from \`ManagementFactory.getPlatformMBeanServer()\` is clearer.

### How Does Spring Auto-Locate an MBeanServer?

If \`MBeanExporter\` is not given a \`server\`, Spring can use an MBeanServer lookup mechanism according to the environment and supporting configuration. When only one server exists, usage is usually straightforward. However, in a JVM containing multiple MBeanServers (application servers, plugin environments, multiple contexts), lookup can make verification harder to reason about.

Therefore:

- If the requirement is "export to the JVM's platform server", configure the server explicitly.
- If the requirement is "export to the container-provided server", obtain the exact reference per the container.
- If the requirement is to isolate the JMX registry, create a separate custom server and wire the exporter/connector to that server.

## 8. When is the Platform MBeanServer the Right Choice?

The platform server is usually suitable when:

- The Java/Spring application runs in a single JVM with clear ownership.
- You want to view JVM MXBeans and application MBeans together through one tool.
- There is no need to partition the registry across different applications in the same JVM.
- ObjectNames follow a stable convention, avoiding collisions.
- Remote JMX is managed at a single JVM/process scope.
- Monitoring tooling relies on the platform JMX endpoint.

Advantages:

1. **Already available:** no need to initialize a separate registry.
2. **Integrated with JVM metrics:** platform MXBeans reside in the same server.
3. **Tooling compatibility:** many Java management tools expect the platform MBeanServer.
4. **Operational simplicity:** one central JMX registry for the application and JVM.
5. **Suitable for Spring JMX:** the exporter can register application MBeans alongside them.

However, using the platform server also means modules in the same JVM share a namespace and certain operational constraints. This must be managed carefully when multiple Spring ApplicationContexts or third parties register MBeans.

## 9. When Should You Consider a Custom MBeanServer?

A custom MBeanServer fits certain architectures:

- An application server requiring multiple JMX registries with different ownership.
- Testing tools requiring an independent registry so as not to interfere with the platform server.
- An embedded component wanting control over its own server, connector, and lifecycle.
- Multiple applications running in the same JVM that need separate MBean sets for discovery/management.
- A framework needing to provide an MBeanServer configured according to its own conventions.

Example creating a custom server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer custom =
    MBeanServerFactory.createMBeanServer(
        "com.example.embedded"
    );
\`\`\`

Then:

\`\`\`java
MBeanExporter exporter = new MBeanExporter();
exporter.setServer(custom);
\`\`\`

A client connected to the platform server will not automatically see MBeans in the custom server. A JMX connector bound to the custom server must be configured if remote access is desired.

### A Custom Server Is Not a Security Boundary by Itself

Creating multiple MBeanServers separates management namespaces, but does not replace authentication/authorization. Objects running in the same JVM may still have permissions to interact via Java references, depending on the architecture. True security boundaries must be enforced at the connector or appropriate management layer.

## 10. ObjectName Collisions in the Platform Server

An MBeanServer does not allow registering two different MBeans simultaneously under the exact same \`ObjectName\`.

Example:

\`\`\`text
com.example.orders:type=Queue,name=Orders
\`\`\`

If two Spring contexts both export an MBean with that name into the platform server, a name collision can occur.

\`\`\`text
Context A -> MBeanExporter -> platform server -> ObjectName X
Context B -> MBeanExporter -> platform server -> ObjectName X
                                                ^
                                               conflict
\`\`\`

Spring provides \`RegistrationPolicy\`:

- \`FAIL_ON_EXISTING\`: throws an error when the name already exists.
- \`IGNORE_EXISTING\`: keeps the existing registration.
- \`REPLACE_EXISTING\`: replaces the existing registration according to policy.

Regardless of the mode, understand ownership before using it. \`REPLACE_EXISTING\` can affect MBeans belonging to another context or library, while \`IGNORE_EXISTING\` can mislead operators into thinking a new bean was exported.

### Recommended Naming Convention

A useful rule:

\`\`\`text
com.example.<module>:type=<Type>,name=<Name>,instance=<Instance>
\`\`\`

Example:

\`\`\`text
com.example.orders:type=Queue,name=Orders,instance=node1
com.example.orders:type=Queue,name=Orders,instance=node2
\`\`\`

For dynamic values, use the \`ObjectName\` API and \`ObjectName.quote(value)\` when necessary to protect delimiters and wildcard characters. Do not concatenate unescaped values directly into a \`domain:key=value\` string.

## 11. Checking Which Server an MBean Is Registered On

A common issue is that the Spring exporter ran, yet JConsole does not see the MBean.

Verification steps:

1. Identify which \`MBeanServer\` the exporter receives (via \`setServer\` or Spring config).
2. Verify the target bean's ObjectName.
3. Call \`isRegistered(name)\` on that exact server.
4. If the client is remote, check whether the connector server is attached to the right MBeanServer.
5. Check authentication, authorization, and networking.
6. If the name appears but attributes/operations are missing, check the assembler/metadata.

Example:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer platform =
    ManagementFactory.getPlatformMBeanServer();

ObjectName target = new ObjectName(
    "com.example.orders:type=Queue,name=Orders"
);

boolean registered = platform.isRegistered(target);

System.out.println(registered);
\`\`\`

If the result is false, possible causes include:
- The bean was not picked up by the exporter.
- The exporter is using a different MBeanServer.
- The actual ObjectName differs from expectations.
- Registration failed or the bean was already unregistered.
- The Spring context has not fully started or has already closed.

This does not prove the Spring bean was removed from the ApplicationContext; the Spring bean container and JMX MBean registry are two different registries.

## 12. Using MBeanInfo to Verify the Management Interface

After verifying registration:

\`\`\`java
import javax.management.MBeanInfo;

MBeanInfo info = platform.getMBeanInfo(target);

System.out.println("Description: " + info.getDescription());

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s, type=%s, readable=%s, writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}
\`\`\`

When connected remotely, the corresponding operations can be invoked on \`MBeanServerConnection\`.

Because the platform server can contain many types of MBeans, \`MBeanInfo\` helps distinguish the exposed API of each MBean. Do not look at an ObjectName alone and assume every method of the underlying Java object can be invoked via JMX.

## 13. Remote JMX and the Platform MBeanServer

The platform server can be accessed through a JMX connector if the connector is configured appropriately. Remote client example:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    ObjectName name =
        new ObjectName("java.lang:type=Memory");

    System.out.println(connection.isRegistered(name));
}
\`\`\`

This example illustrates the client API, assuming a JMX connector at that address has already been configured. It does not start a connector or guarantee that port 9010 is open.

### Security

For remote access, consider:

- Opening the port only to authorized networks/hosts.
- Appropriate authentication and authorization.
- Encrypting the connection if the context requires it.
- Controlling operations that can mutate JVM or application state.
- Not placing credentials in source code or logs.
- Not exposing remote JMX to the public Internet.

JMX is a potentially sensitive management interface; the platform MBeanServer holds both JVM MBeans and application MBeans, so overly broad access can expose operational data or allow unintended operations.

## 14. The Platform Server and Spring Boot

In a Spring Boot application, JMX registration can be affected by auto-configuration and the \`spring.jmx.enabled\` property. Depending on version/configuration, Boot may create an exporter or manage JMX exposure for other components such as Actuator.

Distinguish between:

- Spring Framework \`MBeanExporter\`: registers Spring beans as MBeans.
- Spring Boot JMX auto-configuration: decides and configures export capabilities.
- Spring Boot Actuator JMX endpoints: expose specific management endpoints via JMX when enabled/configured.
- Platform MXBeans: provided by the JVM, independent of the Spring application.

**Do not infer:** Enabling HTTP Actuator does not mean every Spring bean becomes an MBean, nor does having a platform MBeanServer mean a remote JMX port is enabled.

To avoid conflicts, check the actual exporter in the ApplicationContext before adding \`@EnableMBeanExport\` or a second \`MBeanExporter\`.

## 15. Testing with the Platform MBeanServer

### 15.1. Unit Tests and Integration Tests

Using the platform MBeanServer in integration tests is beneficial because it resembles a normal JVM environment. However, there is a downside: multiple tests running in the same JVM can share the registry and collide on ObjectNames.

Example:

\`\`\`java
MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.testing:type=Counter,name=Test1"
);

if (server.isRegistered(name)) {
    throw new IllegalStateException(
        "Unexpected existing test MBean"
    );
}
\`\`\`

After the test, clean up registrations owned by the test, or close the Spring context whose exporter is responsible for unregistering. Do not arbitrarily unregister system platform MBeans or MBeans owned by other components.

### 15.2. When Should Tests Use a Custom Server?

If multiple tests run in parallel in the same JVM or a test requires an isolated registry environment, a custom MBeanServer can prevent collisions:

\`\`\`java
MBeanServer isolated =
    MBeanServerFactory.createMBeanServer("test.domain");
\`\`\`

Pass \`isolated\` into the test's \`MBeanExporter\` and inspect only on that server.

When using \`createMBeanServer\`, tests should manage lifecycle and release/dereference appropriately to avoid retaining unnecessary registries after completion. Never indiscriminately clean up MBeans belonging to the JVM platform server.

## 16. Common Misconceptions

**Misconception 1: "Each Spring ApplicationContext has its own platform MBeanServer."**  
Incorrect. The platform MBeanServer is JVM-scoped and shared by contexts within that JVM.

**Misconception 2: "Once you obtain the platform server, remote JConsole can definitely access it."**  
Incorrect. Remote connectors and network/security settings are configured separately.

**Misconception 3: "Creating a new MBeanServer still automatically includes java.lang:type=Memory."**  
Incorrect. A custom server is not automatically the platform server and does not contain all platform MXBeans.

**Misconception 4: "Spring bean names are the same as MBean names."**  
Incorrect. JMX identifies MBeans by \`ObjectName\`, while the Spring container identifies beans by bean name.

**Misconception 5: "Once an MBean is on a server, every JMX client sees it."**  
Incorrect. Clients must connect to the connector/server holding that registration.

**Misconception 6: "You can freely replace MBeans to fix conflicts."**  
Incorrect. Ownership must be determined and an appropriate registration policy used to avoid affecting another component's MBeans.

**Misconception 7: "MBeanServer only contains platform MXBeans."**  
Incorrect. Application MBeans can be registered, including beans exported by Spring.

**Misconception 8: "A custom MBeanServer provides complete security isolation."**  
Incorrect. It separates registries but does not replace access control.

## 17. Practice Exercises

### Exercise A — Exploring the Platform Server

1. Create a Java class calling \`ManagementFactory.getPlatformMBeanServer()\`.
2. Print \`getDefaultDomain()\` and \`getMBeanCount()\`.
3. Query \`java.lang:*\`.
4. Identify the ObjectNames of Memory, Runtime, and Threading.
5. Use \`getMBeanInfo()\` to inspect attributes/operations.

### Exercise B — Exporting a Spring Bean

1. Create a Standard MBean \`QueueMonitorMBean\` and its implementation class.
2. Register the implementation as a Spring bean.
3. Create an \`MBeanExporter\` and pass the platform server via \`setServer\`.
4. Use \`setBeans\` to export under \`com.example.training:type=Queue,name=Demo\`.
5. Check \`isRegistered()\` and \`getMBeanInfo()\`.
6. Close the context and verify the unregister lifecycle where appropriate.

### Exercise C — Comparing Platform and Custom Servers

1. Create a custom server with \`MBeanServerFactory.createMBeanServer()\`.
2. Register a test MBean into the custom server.
3. Query the same ObjectName on the platform server.
4. Explain why the results differ.
5. Assign the custom server to a dedicated exporter in a test.

### Exercise D — Multi-Context Collision

1. Create two Spring contexts using the same platform MBeanServer.
2. Have each context export an MBean with the same ObjectName.
3. Observe the error or registration policy behavior.
4. Change naming so the names are distinct.
5. Verify both MBeans exist on the same server.

## 18. Self-Check Questions

**Question 1.** What does \`ManagementFactory.getPlatformMBeanServer()\` return?  
**Answer:** The platform MBeanServer of the running JVM, used for platform MXBeans and capable of registering application MBeans.

**Question 2.** How many MBeanServers can a JVM have?  
**Answer:** It can have multiple servers, while a single platform MBeanServer is obtained via ManagementFactory within that JVM.

**Question 3.** Is Spring \`MBeanExporter\` required to use the platform server?  
**Answer:** No. Another \`MBeanServer\` can be configured via \`setServer()\`.

**Question 4.** Why does JConsole not see an MBean registered in a custom server?  
**Answer:** JConsole may be connected to the platform server or another connector, rather than the server holding that MBean.

**Question 5.** Does creating a custom MBeanServer automatically protect operation invocation permissions?  
**Answer:** No. Appropriate access control is needed for the actual access path.

**Question 6.** Should you register application MBeans under the \`java.lang\` domain?  
**Answer:** Typically no. Use your application's own domain to avoid confusion and collisions.

**Question 7.** Why can two Spring contexts in one JVM have JMX conflicts?  
**Answer:** They can both export the same ObjectName into the shared platform MBeanServer.

## 19. Key Takeaways

- **The platform MBeanServer belongs to the JVM**, accessed via \`ManagementFactory.getPlatformMBeanServer()\`.
- A JVM can have multiple MBeanServers; the platform server is a special server managed by the platform.
- The platform server holds JVM platform MXBeans and can hold application MBeans.
- Spring \`MBeanExporter\` can export into the platform server via \`setServer()\`, or use a different server.
- \`ObjectName\` is the key within each MBeanServer; avoid colliding domains/key properties.
- \`MBeanServer\` does not automatically open a remote connector. Remote access is the responsibility of connection and security configuration.
- When multiple Spring contexts, tests, or modules share a JVM, manage ownership, naming, and lifecycle carefully.
- Use \`isRegistered()\`, \`queryNames()\`, and \`getMBeanInfo()\` on the **exact target server** to verify actual state.

### References

- Java SE 21 API — \`ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — \`MBeanServerFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerFactory.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — Platform MXBeans: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/package-summary.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`MBeanServerFactoryBean\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/MBeanServerFactoryBean.html

# MBeanServer as a Registry and Management Execution Point

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the central role of **MBeanServer** in Java Management Extensions (JMX): the place to register, look up, observe, and control MBeans.
- Distinguish between the **registry** (managing names and identifiers of managed objects) and the **management execution point** (reading/writing attributes, invoking operations, and receiving notifications).
- Use \`ObjectName\`, \`MBeanServerFactory\`, and \`ManagementFactory.getPlatformMBeanServer()\` to register and operate on MBeans.
- Recognize the boundary between an \`MBeanServer\` running inside the JVM and \`MBeanServerConnection\` used uniformly for local or connector-based access.
- Handle common errors: duplicate names, unregistered MBeans, mismatched attribute types, business errors, and access permissions.
- Design namespaces, registration lifecycles, and safe management operations for Spring Framework applications.

## 2. The Big Picture: MBean, ObjectName, and MBeanServer

JMX enables exposing the state and operational actions of a Java application through a structured management interface. A component intended to be managed is represented as an **MBean** (Managed Bean). The MBeanServer acts as an intermediary: management tools interact with the server, and the server routes requests to the appropriate MBean.

\`\`\`text
Application / Spring bean
       |
       | create, register MBean
       v
+--------------------------------------+
| MBeanServer (in JVM)                 |
|                                      |
| ObjectName -> MBean                  |
| com.example:type=Cache,name=Products |
| com.example:type=Jobs,name=Importer  |
|                                      |
| getAttribute / setAttribute          |
| invoke / queryNames / notifications  |
+--------------------------------------+
       ^
       | MBeanServerConnection
       |
JConsole / VisualVM / JMX client
       |
   can go through JMXConnectorServer
   when remote management is needed
\`\`\`

Core concepts:

| Component | Responsibility |
| --- | --- |
| **MBean** | Provides attributes, operations, or notifications with management significance. |
| **ObjectName** | Identifies an MBean within an MBeanServer using the pattern \`domain:key=value,...\`. |
| **MBeanServer** | Registers, unregisters, looks up, and executes management requests on MBeans. |
| **MBeanServerConnection** | JMX operation contract usable by both local clients and remote clients. |
| **JMXConnectorServer** | Provides a remote connection endpoint to an MBeanServer when configured. |

Key point: \`MBeanServer\` is neither a business data store nor a distributed service discovery system. It is an **MBean registry scoped to a single JVM/server** and the focal point for invoking management APIs.

## 3. First Role: Registry of MBeans

### 3.1. Registration by ObjectName

Each registered MBean must have a unique \`ObjectName\` within the same \`MBeanServer\`. For example:

\`\`\`text
com.example.application:type=Cache,name=Products
com.example.application:type=Cache,name=Customers
com.example.application:type=Jobs,name=DailyImport
\`\`\`

\`com.example.application\` is the domain; the part after the colon contains the key properties. The domain and set of key properties form the identifier name. The order of key properties in a name should not be used to distinguish MBeans: \`ObjectName\` handles names with key/value semantics.

An MBean can be registered using:

\`\`\`java
ObjectName name =
    new ObjectName("com.example.application:type=Cache,name=Products");
server.registerMBean(cacheMonitor, name);
\`\`\`

When an MBean is already registered under that name, registering another MBean with the same name throws \`InstanceAlreadyExistsException\`. Registration does not automatically overwrite the existing object.

### 3.2. Lookup and Inventory

Commonly used registry APIs:

\`\`\`java
boolean exists = server.isRegistered(name);

Set<ObjectName> allCaches = server.queryNames(
    new ObjectName("com.example.application:type=Cache,*"),
    null
);

int count = server.getMBeanCount();
ObjectInstance instance = server.getObjectInstance(name);
\`\`\`

- \`isRegistered\`: checks whether an identifier already exists.
- \`queryNames\`: finds \`ObjectName\` instances matching a pattern; the optional \`QueryExp\` parameter specifies filter conditions.
- \`getMBeanCount\`: counts the number of MBeans in the server.
- \`getObjectInstance\`: returns the name and class name of a registered MBean.

\`queryNames\` is an operation for discovering managed objects; it does not scan the Spring application context and does not find Java objects that have not been registered as MBeans.

### 3.3. Registry Lifecycle

Typical path:

\`\`\`text
Initialize component
    -> create MBean adapter
    -> create stable ObjectName
    -> registerMBean
    -> operate and handle management commands
    -> unregisterMBean when closing component/application
\`\`\`

Unregistering:

\`\`\`java
if (server.isRegistered(name)) {
    server.unregisterMBean(name);
}
\`\`\`

In applications with multiple threads or multiple components managing names concurrently, the sequence \`isRegistered\` followed by \`unregisterMBean\` is not an atomic operation. The object may be removed right after the check; therefore, \`InstanceNotFoundException\` should be handled if contention is possible.

## 4. Second Role: Execution Point for Management Requests

Registration is only the first step. What distinguishes MBeanServer is that it receives commands, resolves the target MBean, and forwards the management operation to that MBean.

| Request | Typical API | Meaning |
| --- | --- | --- |
| Read state | \`getAttribute(name, "Hits")\` | Retrieves the value of an exposed attribute. |
| Update configuration | \`setAttribute(name, new Attribute("Enabled", false))\` | Writes an attribute that has a setter and is writable. |
| Run action | \`invoke(name, "clear", ..., ...)\` | Calls an exposed MBean operation. |
| Discover interface | \`getMBeanInfo(name)\` | Reads metadata for attributes, operations, and notifications. |
| Receive events | \`addNotificationListener(...)\` | Registers a notification listener. |

MBeanServer **does not automatically expose** every field or method of a Java object. What can be called depends on the MBean's JMX interface (Standard MBean, MXBean, Dynamic MBean, etc.) and actual access configuration/permissions.

### 4.1. Reading and Writing Attributes

\`\`\`java
Long hits = (Long) server.getAttribute(name, "Hits");

server.setAttribute(
    name,
    new Attribute("Enabled", Boolean.FALSE)
);
\`\`\`

The \`Hits\` attribute can only be read if the MBean interface exposes a matching getter. \`Enabled\` can only be written if an exposed setter exists and the value type is compatible. JMX attribute names are case-sensitive.

For multiple attributes, \`getAttributes\` / \`setAttributes\` can be used; results should be checked because batch requests may not succeed uniformly across every attribute.

### 4.2. Invoking Operations

\`\`\`java
server.invoke(
    name,
    "clear",
    new Object[0],
    new String[0]
);
\`\`\`

The four parameters are \`ObjectName\`, operation name, argument array, and parameter type-name array. When an operation is overloaded, the signature helps MBeanServer select the right operation. For example, an operation \`resize(int)\` can be called with:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { 250 },
    new String[] { "int" }
);
\`\`\`

Invoking an operation can produce real side effects such as clearing a cache, refreshing configuration, or stopping a job. A JMX endpoint should not be treated solely as a place to read metrics.

### 4.3. Metadata and Discoverability

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(operation.getName());
}
\`\`\`

Tools like JConsole rely on this metadata to render the Attributes and Operations tabs. Metadata describes the exposed management capabilities, not the entire internal API of the application.

## 5. Runnable Example: Register, Query, Read/Write, and Invoke

This example uses standard Java, with no Spring dependencies, to clearly demonstrate the nature of \`MBeanServer\`.

### 5.1. Declaring a Standard MBean

The interface name must follow the Standard MBean convention: class \`CacheMonitor\` has interface \`CacheMonitorMBean\`.

\`\`\`java
package example.jmx;

public interface CacheMonitorMBean {
    int getSize();
    boolean isEnabled();
    void setEnabled(boolean enabled);
    void clear();
}
\`\`\`

\`\`\`java
package example.jmx;

public final class CacheMonitor implements CacheMonitorMBean {
    private volatile boolean enabled = true;
    private volatile int size = 42;

    @Override
    public int getSize() {
        return size;
    }

    @Override
    public boolean isEnabled() {
        return enabled;
    }

    @Override
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public void clear() {
        size = 0;
    }
}
\`\`\`

Here \`Size\` is a read-only attribute, \`Enabled\` is a read/write attribute, and \`clear\` is an operation. \`volatile\` enables visibility for simple updates across threads; for complex state, a dedicated synchronization mechanism is required.

### 5.2. Executing via the Platform MBeanServer

\`\`\`java
package example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.Attribute;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class JmxRegistryDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
            "com.example.application:type=Cache,name=Products"
        );

        CacheMonitor monitor = new CacheMonitor();
        server.registerMBean(monitor, name);

        try {
            System.out.println("Registered = " + server.isRegistered(name));
            System.out.println("Names = " + server.queryNames(
                new ObjectName("com.example.application:type=Cache,*"),
                null
            ));
            System.out.println("Size before = "
                + server.getAttribute(name, "Size"));

            server.setAttribute(
                name,
                new Attribute("Enabled", Boolean.FALSE)
            );
            System.out.println("Enabled = "
                + server.getAttribute(name, "Enabled"));

            server.invoke(name, "clear", new Object[0], new String[0]);
            System.out.println("Size after = "
                + server.getAttribute(name, "Size"));

            MBeanInfo info = server.getMBeanInfo(name);
            System.out.println("MBean class = " + info.getClassName());
        } finally {
            server.unregisterMBean(name);
        }
    }
}
\`\`\`

Semantically expected output:

\`\`\`text
Registered = true
Names = [com.example.application:type=Cache,name=Products]
Size before = 42
Enabled = false
Size after = 0
MBean class = example.jmx.CacheMonitor
\`\`\`

The \`Names\` line may display in a different order when multiple MBeans match the query. The key values to verify are: registration succeeds, \`Size=42\` is readable, \`Enabled=false\` is writable, and invoking \`clear\` sets \`Size=0\`.

Run this in a Java project with the appropriate package structure and a JDK containing the \`java.management\` module (standard JDKs typically include it). If the app is managed by a container/Spring, use the bean/container lifecycle instead of manually re-registering the same \`ObjectName\` from multiple places.

## 6. MBeanServer and MBeanServerConnection

\`MBeanServer\` extends the \`MBeanServerConnection\` operation interface. Clients can write code against \`MBeanServerConnection\` to use the same commands such as \`getAttribute\`, \`invoke\`, and \`queryNames\` without needing to know whether the connection is local or remote.

\`\`\`java
import javax.management.MBeanServerConnection;

MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();

Object value = connection.getAttribute(name, "Size");
\`\`\`

In remote management, clients typically obtain \`MBeanServerConnection\` from a \`JMXConnector\`, while the server-side \`JMXConnectorServer\` forwards requests to the actual MBeanServer. Remote connections depend on connectors, authentication, networking, and security configuration. \`ManagementFactory.getPlatformMBeanServer()\` by itself does not automatically open a remote port.

**Distinguishing three scopes:**

1. **Java MBean** holds the management logic and state.
2. **MBeanServer in the JVM** manages the namespace and dispatches commands to MBeans.
3. **JMX connector/client** transports requests across process boundaries if enabled.

A single JVM can have multiple MBeanServers created via \`MBeanServerFactory\`; therefore, the same \`ObjectName\` can exist independently on different servers. For typical applications, the platform MBeanServer is usually the convenient choice for JMX tools to observe.

## 7. ObjectName and Namespace Design Rules

An easy-to-operate convention:

\`\`\`text
<domain>:type=<component type>,name=<stable identifier>
\`\`\`

Examples:

\`\`\`text
com.acme.orders:type=Cache,name=OrderReadCache
com.acme.orders:type=Scheduler,name=Reconciliation
com.acme.orders:type=Queue,name=RetryQueue
\`\`\`

Principles:

- Choose a domain that distinguishes the organization or application; avoid occupying standard namespaces such as \`java.lang\`.
- Use \`type\` for the MBean category and \`name\` for a specific instance; you can add \`component\`, \`tenant\`, or \`id\` when needed.
- Keep names stable across the process lifecycle so monitoring tools can query consistently.
- Do not put passwords, tokens, or personal information in \`ObjectName\`: names are displayed to management tools and may appear in logs.
- For dynamic name values containing special characters, use \`ObjectName\` quoting mechanisms and validate naming rules; do not arbitrarily concatenate input strings and assume validity.
- When running multiple application instances across multiple JVMs, remember that ObjectName uniqueness applies only per MBeanServer; host/instance identification belongs to connection management or intentional namespacing.

\`ObjectName\` also supports patterns, for example:

\`\`\`java
ObjectName pattern = new ObjectName(
    "com.acme.orders:type=Cache,*"
);
Set<ObjectName> matches = server.queryNames(pattern, null);
\`\`\`

Patterns are primarily used for searching; \`registerMBean\` requires a concrete name, not a pattern.

## 8. Integration with Spring Framework

In Spring, application beans can be exported to JMX using Spring JMX mechanisms, notably \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` (when using the appropriate annotation model).

### 8.1. Managed Bean and Annotations

\`\`\`java
package example.springjmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.application:type=Cache,name=Products",
    description = "Product cache operations"
)
public class ProductCacheAdmin {

    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Whether cache is enabled")
    public boolean isEnabled() {
        return enabled;
    }

    @ManagedAttribute
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @ManagedOperation(description = "Clear product cache")
    public void clear() {
        // Call the real cache-clearing API in the application when implemented.
    }
}
\`\`\`

This is a regular Spring bean. The annotations provide JMX metadata; actually exporting the MBean requires an appropriate exporter configuration. Having annotations alone is not enough to guarantee that the MBean is registered in every Spring configuration.

### 8.2. Registering the Exporter in Plain Spring

\`\`\`java
package example.springjmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfig {

    @Bean
    public MBeanExporter mBeanExporter(
            ProductCacheAdmin productCacheAdmin) {
        AnnotationJmxAttributeSource source =
            new AnnotationJmxAttributeSource();

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);

        MetadataNamingStrategy naming =
            new MetadataNamingStrategy();
        naming.setAttributeSource(source);

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setBeans(java.util.Map.of(
            "productCacheAdmin", productCacheAdmin
        ));
        return exporter;
    }
}
\`\`\`

The example intentionally declares the exporter explicitly to show the export mechanism. When using Spring Boot, JMX management configuration may be auto-configured depending on dependencies and configuration properties; check the specific application's configuration to avoid registering two exporters with the same name.

When the container initializes the exporter, the MBean is registered in the selected MBeanServer; when the context is destroyed, the exporter can unregister MBeans under its management. Do not mix manual \`registerMBean\` calls and the exporter on the same \`ObjectName\` without clearly designed ownership.

### 8.3. JMX Does Not Replace the Spring Bean Registry

| Spring ApplicationContext | JMX MBeanServer |
| --- | --- |
| Manages dependency injection, lifecycle, and bean scope. | Manages exposed MBeans and administrative interactions. |
| Looks up beans by name/type/qualifier. | Looks up MBeans by \`ObjectName\` and JMX patterns. |
| Calls Java methods in application code. | Reads/writes attributes and invokes operations exposed via JMX. |
| Serves application logic. | Serves observation and operational control. |

A Spring bean does not automatically appear in JMX merely because it exists in the ApplicationContext.

## 9. Notification: MBeanServer Also Supports Management Event Streams

Besides reading/writing/invoking operations, an MBean can emit a \`Notification\`. MBeanServer allows registering listeners by \`ObjectName\`:

\`\`\`java
NotificationListener listener = (notification, handback) ->
    System.out.println(
        notification.getType() + ": " + notification.getMessage()
    );

server.addNotificationListener(
    name,
    listener,
    null,
    null
);

try {
    // Other operations and handling notifications from the MBean if any.
} finally {
    server.removeNotificationListener(name, listener);
}
\`\`\`

This snippet only works if the target MBean supports emitting notifications (for example, implementing \`NotificationBroadcaster\`); the \`CacheMonitor\` Standard MBean in the earlier example does not provide that capability yet. Listeners must be removed to avoid holding references longer than the intended lifecycle.

Certain MBean registration/unregistration events can be observed through the delegate MBean \`JMImplementation:type=MBeanServerDelegate\`. These are notifications about registry changes, distinct from business notifications emitted by an application MBean.

## 10. Error Handling and Race Conditions

Exceptions worth recognizing:

| Exception | Common Situation | How to Handle |
| --- | --- | --- |
| \`InstanceAlreadyExistsException\` | Registering a duplicate \`ObjectName\`. | Clarify ownership, avoid duplicate registration; do not overwrite arbitrarily. |
| \`InstanceNotFoundException\` | Accessing an MBean that does not exist or has been unregistered. | Handle lifecycle properly, re-check the registry list. |
| \`MalformedObjectNameException\` | Malformed name string. | Fix naming rules, quote dynamic data. |
| \`AttributeNotFoundException\` | Attribute name does not exist or lacks a matching accessor. | Check \`getMBeanInfo\` and case sensitivity. |
| \`InvalidAttributeValueException\` | Written value is incompatible. | Check type, constraints, and setter. |
| \`ReflectionException\` | Reflection error while processing a request. | Check signature and root cause. |
| \`MBeanException\` | An MBean operation or getter/setter threw a checked exception that was wrapped. | Inspect the target exception and recover business logic appropriately. |
| \`RuntimeMBeanException\` | Runtime exception thrown inside the MBean. | Inspect the root cause; do not swallow errors. |
| \`NotCompliantMBeanException\` | Object does not conform to the MBean contract at registration time. | Review Standard MBean/MXBean rules or use an appropriate adapter. |

Do not design logic relying solely on \`isRegistered\` and assuming the subsequent operation will succeed. Another thread may unregister the MBean between the two calls (time-of-check/time-of-use).

For operations with side effects, an exception from \`invoke\` does not always prove the action never ran. The action may have started or partially completed before the error was propagated back. Operations should be designed to be idempotent or provide dedicated status information when needed.

## 11. Security and Production Operations

MBeanServer can open control over critical application resources. For example, \`clearCache\`, \`reloadConfiguration\`, \`stopJob\`, or toggling feature flags all have operational impact.

The following principles should be applied:

1. **Limit the interface**: expose only attributes/operations intended for monitoring and management.
2. **Prefer read-only** for monitoring metrics; open setters or state-mutating operations only when truly necessary.
3. **Protect remote JMX**: if a remote connector is enabled, configure authentication, authorization, encryption, and network access restrictions according to the deployment environment. Do not assume enabling JMX provides full security by default.
4. **Do not expose secrets**: management getters, \`ObjectName\`, and notifications must not leak tokens, passwords, or sensitive data.
5. **Control load**: getters called by monitoring tools should be fast with minimal side effects; time-consuming operations should have progress state or appropriate asynchronous mechanisms.
6. **Ensure cleanup**: unregister MBeans and listeners when components shut down to avoid name collisions or reference leaks.
7. **Observe errors**: log high-impact management operations with appropriate context; avoid putting sensitive data in logs.

Distinguish between **being able to invoke an operation via JMX** and **the caller being authorized to do so**. Actual permissions depend on connector architecture, security policies, authorization layers, or system proxies. The \`MBeanServer\` API itself does not replace the application's security policy.

## 12. When Should You Use MBeanServer Directly?

**Use directly** when you need control over MBean creation, registration names, lifecycle, queries, or execution via the JMX API in Java; for example, an infrastructure library wanting to expose pool or scheduler status.

**Use Spring JMX exporter** when you want lifecycle management tied to the ApplicationContext and to export application beans with clear metadata.

**Use other metrics/observability tools** when the primary goal is collecting time-series data, building dashboards, or alerting on a metrics system. JMX is a source of management attributes; monitoring systems can pull JMX data via exporters/collectors, but JMX does not replace a metrics storage system by itself.

An application can combine these options: Spring exports MBeans to the platform MBeanServer, JConsole accesses it for local diagnostics, and a monitor component reads selected attributes to emit metrics.

## 13. Hands-On Exercises

**Exercise 1 — Registry.** Create two MBean instances named \`com.example:type=Cache,name=A\` and \`com.example:type=Cache,name=B\`. Use \`queryNames("com.example:type=Cache,*", null)\` to list both. Try registering a second time with name A and observe \`InstanceAlreadyExistsException\`.

**Exercise 2 — Attributes and operations.** Add a \`Threshold\` attribute with getter/setter and a \`resetStatistics()\` operation. Call \`getMBeanInfo\` to inspect readability/writability and exposed methods, then try \`setAttribute\` and \`invoke\`.

**Exercise 3 — Lifecycle.** Create an MBean at startup and unregister it when the application stops. Check \`isRegistered\` before and after shutdown. Handle the case where an access command occurs at the exact moment the MBean is removed.

**Exercise 4 — Spring.** Create a bean with \`@ManagedResource\` and one \`@ManagedOperation\`, configure \`MBeanExporter\`, then use JConsole to observe the domain, attributes, and operation. Prove that merely declaring a Spring bean without JMX export does not make the corresponding name appear in the registry.

## 14. Comprehension Check Questions

**1. Why is MBeanServer called a registry?** Because it manages the mapping from \`ObjectName\` to registered MBeans, supporting registration/unregistration and lookup by name/pattern.

**2. Why is MBeanServer called a management execution point?** Because it receives JMX requests such as \`getAttribute\`, \`setAttribute\`, and \`invoke\`, validates/routes them, and executes them on the target MBean.

**3. Is \`ObjectName\` globally unique across the entire system?** No. Uniqueness is guaranteed within a single MBeanServer; multiple JVMs or independent servers can have the same ObjectName.

**4. Can every public method of an MBean be called via \`invoke\`?** No. Only operations exposed through the appropriate JMX management interface are part of the invocation contract.

**5. Does the platform MBeanServer mean remote JMX is enabled?** No. Remote access requires a separate connector and access configuration.

**6. Does \`queryNames\` list all Spring beans?** No. It only returns MBeans registered in the corresponding MBeanServer.

**7. Why is \`finally\` needed when unregistering?** To release the name and resources even if management operations throw an exception.

## 15. Summary

\`MBeanServer\` fulfills two tightly coupled roles: the **registry** ensures each MBean has a management identity and can be discovered; the **execution point** receives read/write/operation/event commands based on that identity. \`ObjectName\` is the routing key; JMX metadata defines valid operations; connectors determine how clients access it. In Spring Framework, \`MBeanExporter\` bridges the Spring bean lifecycle with MBeanServer, helping expose operational capabilities in a controlled manner.

### References

- Java SE — \`javax.management.MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE — \`javax.management.ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE — \`java.lang.management.ManagementFactory\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Java Management Extensions (JMX) Technology: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
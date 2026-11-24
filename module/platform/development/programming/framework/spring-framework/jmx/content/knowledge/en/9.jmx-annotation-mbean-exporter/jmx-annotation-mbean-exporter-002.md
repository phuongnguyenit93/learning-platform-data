# @EnableMBeanExport to Enable Java Configuration

> **Topic:** Spring Framework JMX  
> **Knowledge Group:** AnnotationMBeanExporter  
> **Lesson:** @EnableMBeanExport to Enable Java Configuration

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain why a Spring bean with \`@ManagedResource\` does not automatically appear in a JMX MBeanServer by default.
- Use \`@EnableMBeanExport\` on a \`@Configuration\` class to activate MBean export with Java configuration.
- Understand the \`AnnotationMBeanExporter\` component and the roles of \`MBeanServer\`, \`ObjectName\`, assembler, naming strategy, and registration policy.
- Distinguish enabling JMX export in Spring Framework from configuring a remote JMX connector and Spring Boot auto-configuration settings.
- Write an example with attributes and operations that can be verified via JConsole or \`MBeanServerConnection\`.
- Troubleshoot cases where a bean is not exported, ObjectNames collide, the wrong MBeanServer is used, or annotations are not recognized.

## 2. The Big Picture

Java Management Extensions (JMX) describe JVM resources via **MBeans**. Spring can publish beans managed in an \`ApplicationContext\` as MBeans through \`MBeanExporter\`. When using annotations, Spring provides \`AnnotationMBeanExporter\` to recognize metadata such as \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\`.

\`@EnableMBeanExport\` is the concise declarative way in Java configuration to activate this mechanism.

\`\`\`text
@Configuration
@EnableMBeanExport
      |
      v
Spring registers infrastructure for JMX export
      |
      v
AnnotationMBeanExporter
      |
      +--> Finds Spring beans with @ManagedResource
      +--> Reads @ManagedAttribute / @ManagedOperation
      +--> Resolves ObjectName, metadata, and MBeanServer
      |
      v
MBeanServer (JVM JMX registry)
      |
      +--> learning.jmx:type=CacheMonitor,name=main
      |
      +--> JConsole / JMX client
           reads attributes, invokes operations, receives notifications
\`\`\`

Key point to remember: \`@ManagedResource\` describes **which bean can be published**, while \`@EnableMBeanExport\` provides **the infrastructure to perform the publishing**. Without an appropriate exporter, Spring does not automatically register an MBean just because a class has annotations.

This mechanism belongs to **application management**, independent of the HTTP request/response flow. After export, the Spring bean continues to exist in the container as before; JMX simply creates an additional observation or control surface.

## 3. What Does @EnableMBeanExport Do?

The \`org.springframework.context.annotation.EnableMBeanExport\` annotation is placed on a configuration class:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

When Spring processes this configuration, it activates the annotation-driven MBean registrar and publisher, corresponding to the \`AnnotationMBeanExporter\` mechanism.

Important responsibilities:

1. **Creates export infrastructure:** adds the necessary infrastructure beans to detect and register MBeans.
2. **Detects eligible beans:** inspects beans in the context that have \`@ManagedResource\` or the configured MBean detection rules.
3. **Reads metadata:** determines the corresponding attributes, operations, and notifications.
4. **Assigns ObjectName:** uses the declared name or a naming strategy.
5. **Registers:** places the MBean into the appropriate MBeanServer.
6. **Binds to lifecycle:** manages registration of exporter-created MBeans when the application context starts and closes.

This annotation **does not automatically enable remote JMX** and **does not expose every public method of every bean** by default. Nor does it automatically define authentication, TLS, firewall rules, or client operation permissions.

## 4. Components in the Export Mechanism

| Component | Role |
|---|---|
| \`@EnableMBeanExport\` | Activates the export mechanism using Java configuration. |
| \`AnnotationMBeanExporter\` | Exporter that uses annotation metadata to detect beans and build the JMX management model. |
| \`@ManagedResource\` | Marks a bean as a management resource and can specify ObjectName/description. |
| \`@ManagedAttribute\` | Describes a getter/setter exposed as a JMX attribute. |
| \`@ManagedOperation\` | Describes a method exposed as a JMX operation. |
| \`@ManagedOperationParameters\` | Provides parameter name and description metadata for operations. |
| \`@ManagedNotification\` / \`@ManagedNotifications\` | Publishes metadata about notifications the MBean can emit. |
| \`ObjectName\` | Unique identifier in an MBeanServer, in the form \`domain:key=value\`. |
| \`MBeanServer\` | Registers MBeans and handles queries, attribute access, invocations, and notifications. |
| \`JConsole\` / JMX client | Reads and interacts with registered MBeans. |

An illustrative \`ObjectName\`:

\`\`\`text
learning.jmx:type=CacheMonitor,name=main
\`\`\`

In this name, \`learning.jmx\` is the domain; \`type\` and \`name\` are key properties. Two MBeans cannot simultaneously use the same ObjectName in one MBeanServer without an appropriate registration conflict policy.

## 5. Minimal Example: Enabling Export in Java Configuration

An example using Spring Framework with a cache management bean. The bean has an attribute reading how many times the cache was refreshed and an operation to reset the counter.

### 5.1. Bean with JMX metadata

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main",
    description = "Cache refresh monitoring"
)
public class CacheMonitor {

    private final AtomicLong refreshCount = new AtomicLong();

    public void cacheRefreshed() {
        refreshCount.incrementAndGet();
    }

    @ManagedAttribute(
        description = "Number of cache refresh operations"
    )
    public long getRefreshCount() {
        return refreshCount.get();
    }

    @ManagedOperation(
        description = "Reset refresh count"
    )
    public void resetCounter() {
        refreshCount.set(0);
    }
}
\`\`\`

Meaning:

- \`@Component\` tells Spring to create \`CacheMonitor\` as a bean.
- \`@ManagedResource\` marks the bean so the JMX annotation export mechanism detects it and attaches a fixed ObjectName.
- \`@ManagedAttribute\` exposes \`RefreshCount\` as a read-only attribute.
- \`@ManagedOperation\` exposes \`resetCounter()\` as an operation.
- \`cacheRefreshed()\` has no management annotation, so it is not included in the annotation management surface in this example.

Spring keeps a single actual bean in the ApplicationContext. When a JMX client reads \`RefreshCount\`, the exporter/adapter delegates to the getter on that bean rather than creating a separate state copy for JConsole.

### 5.2. Java configuration

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = CacheMonitor.class)
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

\`@ComponentScan\` ensures \`CacheMonitor\` is discovered by Spring. \`@EnableMBeanExport\` activates the JMX export infrastructure.

### 5.3. Launching the Spring context

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class JmxExample {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                     JmxConfiguration.class
                 )) {

            CacheMonitor monitor =
                context.getBean(CacheMonitor.class);

            monitor.cacheRefreshed();
            monitor.cacheRefreshed();

            System.out.println(
                "Spring context started; JMX MBean exported"
            );
            System.out.println(
                "PID: " + ProcessHandle.current().pid()
            );

            // Keep the JVM alive to observe with JConsole.
            System.in.read();
        }
    }
}
\`\`\`

Once running, the context creates the bean, the exporter registers the MBean, and the program keeps the JVM alive so you can connect with JConsole. Upon exiting \`try-with-resources\`, the context closes and the exporter cleans up the MBeans under its managed lifecycle.

The example uses Spring libraries matching your application version. In a real Maven/Gradle project, the corresponding Spring Context and JMX dependencies are required; the standard JMX API \`javax.management\` is provided by the JDK.

## 6. Reading and Invoking the MBean via the JMX API

If the exporter uses the platform MBeanServer, you can verify it with code running in the same JVM:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "learning.jmx:type=CacheMonitor,name=main"
);

System.out.println(
    "Registered: " + server.isRegistered(name)
);

Object count = server.getAttribute(
    name,
    "RefreshCount"
);
System.out.println("RefreshCount: " + count);

server.invoke(
    name,
    "resetCounter",
    new Object[0],
    new String[0]
);

System.out.println(
    "After reset: "
        + server.getAttribute(name, "RefreshCount")
);
\`\`\`

Output when \`cacheRefreshed()\` has been called twice:

\`\`\`text
Registered: true
RefreshCount: 2
After reset: 0
\`\`\`

**Key assumption:** \`ManagementFactory.getPlatformMBeanServer()\` must be the exact server where the Spring exporter registered the MBean. If the exporter is configured with a different server, looking it up on the platform server can return \`false\` even though the MBean exported successfully.

### Call flow from a JMX client

\`\`\`text
JConsole / Java JMX Client
   |
   | getAttribute("RefreshCount")
   v
MBeanServer (ObjectName exact)
   |
   v
Spring ModelMBean / JMX adapter
   |
   v
CacheMonitor.getRefreshCount()
   |
   v
AtomicLong.get() -> 2
\`\`\`

For \`resetCounter()\`, the client calls \`MBeanServer.invoke\`; the adapter routes to the method on the Spring bean and updates its state.

## 7. Configuring MBeanServer with @EnableMBeanExport

In complex applications, there may be multiple MBeanServers or the Spring exporter may need a specific server. \`@EnableMBeanExport\` has a \`server\` attribute to specify the **bean name** representing the MBeanServer.

Example:

\`\`\`java
package example.jmx;

import javax.management.MBeanServer;
import java.lang.management.ManagementFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "jmxServer")
public class JmxServerConfiguration {

    @Bean
    public MBeanServer jmxServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

In this example, \`server = "jmxServer"\` is a **bean name**, not a URL, hostname, or ObjectName. Spring retrieves the MBeanServer bean with this name as the registration target.

When not explicitly specified, the export mechanism resolves the MBeanServer according to Spring Framework and environment rules. Do not assume every JVM configuration shares the same MBeanServer; verify the actual server when accessing it from tools.

Some configurations may use \`MBeanServerFactoryBean\` to create or locate an MBeanServer. If a separate MBeanServer is created, JConsole attaching to the platform server might not see that MBean. For management via JConsole, choose a registry aligned with how the tool will connect.

## 8. NamingStrategy and ObjectName

\`@ManagedResource(objectName = "...")\` lets you declare the name directly:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=CacheMonitor,name=main"
)
\`\`\`

If an ObjectName is not hardcoded, Spring needs an appropriate naming mechanism, typically through an \`ObjectNamingStrategy\` or a strategy integrated with the exporter. For multi-instance systems, it is good practice to have a convention:

\`\`\`text
learning.jmx:type=WorkerPool,name=primary,node=one
learning.jmx:type=WorkerPool,name=primary,node=two
\`\`\`

However, do not insert arbitrary unescaped data into an \`ObjectName\`, especially commas, equals signs, colons, and wildcard characters. Use \`ObjectName.quote(value)\` or an appropriate \`ObjectName\` construction method when key properties contain special data.

Two MBeans with the same name in the same server can trigger \`InstanceAlreadyExistsException\` (or a Spring-wrapped export error), unless a registration handling policy is explicitly configured. Do not rely on the class name or Spring bean name as proof of the actual ObjectName: read the metadata or use \`queryNames\` from the right MBeanServer.

## 9. Annotations for Attributes and Operations

### 9.1. Read-only attribute

\`\`\`java
@ManagedAttribute(description = "Current queue size")
public int getQueueSize() {
    return queue.size();
}
\`\`\`

Following JavaBeans naming conventions, the getter \`getQueueSize()\` exposes the \`QueueSize\` attribute.

### 9.2. Attribute with a setter

\`\`\`java
private volatile int maxRetries = 3;

@ManagedAttribute
public int getMaxRetries() {
    return maxRetries;
}

@ManagedAttribute
public void setMaxRetries(int maxRetries) {
    if (maxRetries < 0) {
        throw new IllegalArgumentException(
            "maxRetries must be non-negative"
        );
    }
    this.maxRetries = maxRetries;
}
\`\`\`

Properly annotated getters and setters allow clients to read/write the attribute, provided the exporter/assembler exposes them. Input values should be validated because management tools can modify application state.

### 9.3. Operation with parameters

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Resize worker pool")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "workers",
        description = "New worker count"
    )
})
public void resizeWorkers(int workers) {
    if (workers <= 0) {
        throw new IllegalArgumentException(
            "workers must be positive"
        );
    }
    // Update the actual worker pool.
}
\`\`\`

The client invokes it via:

\`\`\`java
server.invoke(
    name,
    "resizeWorkers",
    new Object[] { 8 },
    new String[] { "int" }
);
\`\`\`

\`@ManagedOperationParameters\` adds parameter names and descriptions, but does not change the Java type or the signature used in a JMX invocation. \`params\` holds the values, and \`signature\` holds the declared type names such as \`int\`, \`long\`, \`java.lang.String\`.

## 10. Notifications with @EnableMBeanExport

A Spring bean can also emit JMX notifications when supported by the exporter mechanism. One approach is implementing \`NotificationPublisherAware\` to receive a \`NotificationPublisher\` from Spring.

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;
import javax.management.Notification;

import org.springframework.jmx.export.notification.NotificationPublisher;
import org.springframework.jmx.export.notification.NotificationPublisherAware;

public class JobService
        implements NotificationPublisherAware {

    private NotificationPublisher publisher;
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public void setNotificationPublisher(
            NotificationPublisher publisher
    ) {
        this.publisher = publisher;
    }

    public void jobCompleted(String jobId) {
        Notification notification = new Notification(
            "app.job.completed",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Job completed: " + jobId
        );

        publisher.sendNotification(notification);
    }
}
\`\`\`

The snippet above illustrates the logic. For real use, \`JobService\` must be declared as a Spring bean, annotated with \`@ManagedResource\`, have the exporter enabled, and configure appropriate notification metadata. The publisher is typically only ready after the bean has been processed by the exporter; avoid calling notification-emitting methods too early in the lifecycle.

So that tools display the declared notification types, Spring provides metadata annotations \`@ManagedNotification\` and \`@ManagedNotifications\`, or the corresponding assembler. Declaring metadata does not emit events by itself: code must still call \`publisher.sendNotification\` or a broadcaster.

## 11. Distinguishing Plain Spring Framework from Spring Boot

With **plain Spring Framework**, \`@EnableMBeanExport\` is the Java configuration way to enable annotation-driven JMX export.

With **Spring Boot**, there is also auto-configuration and JMX-related properties. Depending on version and configuration, Spring Boot may automatically create an exporter when JMX is enabled, while also placing Actuator MBeans in their own domain. For example, some Boot versions use the property:

\`\`\`properties
spring.jmx.enabled=true
\`\`\`

Check the documentation for the exact Spring Boot version you are running and which exporters have already been initialized. You should not both enable auto-configuration export and add \`@EnableMBeanExport\` without checking for the possibility of creating multiple exporters or duplicate ObjectName registrations.

**JMX export is different from remote JMX:** \`spring.jmx.enabled\` or \`@EnableMBeanExport\` only concerns publishing MBeans within the server. Remote connectors/agents, authentication, TLS, and endpoints are a separate configuration layer.

### When to choose @EnableMBeanExport?

Choose it when:

- The application uses Java-based Spring configuration.
- You want \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` to become management resources.
- You want to reduce manual exporter configuration for multiple beans.
- You want to control which MBeanServer is used via Java configuration.

If you need to specify individual beans, a special naming strategy, a specific assembler, or complex listeners, explicit \`MBeanExporter\` configuration may also be suitable. Avoid enabling two exporters that register the same MBean unintentionally.

## 12. Reading Metadata to Confirm Export

\`MBeanInfo\` is the authoritative source for verifying the registered JMX surface. For example:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = server.getMBeanInfo(name);

System.out.println(info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s readable=%s writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println(
        "Operation: " + operation.getName()
    );
}
\`\`\`

If the bean is exported with metadata like the \`CacheMonitor\` example, you expect to see the \`RefreshCount\` attribute and the \`resetCounter\` operation. This is stronger evidence than merely observing that the annotations exist in the source code.

You can use JConsole:

1. Run the application and note its PID.
2. Open \`jconsole\` from the JDK.
3. Select the right local Java process.
4. Open the **MBeans** tab.
5. Find the \`learning.jmx\` domain.
6. Select \`type=CacheMonitor,name=main\`.
7. Inspect **Attributes** and **Operations**.
8. Read \`RefreshCount\`, invoke \`resetCounter\`, then read the attribute again.

JConsole might not be able to attach due to user permissions, containers, or JVM configuration. In that case, verify through \`MBeanServerConnection\` or set up an appropriate connector.

## 13. Common Issues

### 13.1. @ManagedResource is present, but JConsole does not show the bean

Check:

1. Is \`@EnableMBeanExport\` placed on a \`@Configuration\` class processed by the ApplicationContext?
2. Does the class have \`@Component\` and lie within the component scan scope, or have a corresponding \`@Bean\`?
3. Does the bean have \`@ManagedResource\` and a valid ObjectName?
4. Has the context finished initializing and has the exporter run?
5. Is JConsole connected to the right JVM and MBeanServer?
6. Are there any registration errors in the startup logs?

If there is no Spring bean in the context, the JMX exporter cannot create the bean on its own solely from management annotations.

### 13.2. MBean exists, but a method is missing

\`@ManagedResource\` does not expose all business methods by default. Check \`@ManagedOperation\`, \`@ManagedAttribute\`, JavaBeans conventions, and the active metadata assembler. Use \`MBeanInfo\` to see which methods were actually exposed.

### 13.3. Duplicate ObjectName error

If multiple beans are exported under the same name:

\`\`\`text
learning.jmx:type=CacheMonitor,name=main
\`\`\`

An MBeanServer cannot hold two MBeans with the same name under normal registration. Fix the naming strategy, ensure uniqueness, or configure an appropriate registration policy if handling an existing MBean is intentional. Do not arbitrarily unregister other MBeans.

### 13.4. MBeanServer not found

If using \`@EnableMBeanExport(server = "jmxServer")\`, confirm that the bean has the exact name, the exact type \`javax.management.MBeanServer\`, and can be initialized. Misconfiguration can prevent the exporter from registering.

### 13.5. Spring Boot encounters duplicate registration errors

Check the exporters provided by auto-configuration and any exporter you configured manually. MBeans with the same ObjectName may be registered twice. Choose one unified export mechanism for that bean or configure a clear domain/naming policy.

### 13.6. Attribute appears, but does not update

Confirm that the bean's state actually changes and the getter reads from the right source. JConsole may require refreshing/polling to see new values. A field changing does not automatically generate a JMX notification without a publisher/broadcaster emitting an event.

### 13.7. Remote JMX cannot connect

This is usually a connector, RMI address, port, authentication, TLS, or firewall issue. \`@EnableMBeanExport\` is not a switch to turn on remote JMX. Do not solve it by opening management ports publicly to the Internet.

## 14. Designing a Safe Management Surface

An MBean operation can modify running resources. You should apply these principles:

- Only export beans and methods with a clear operational purpose.
- Keep important observational attributes read-only if editing is unnecessary.
- Validate parameters on every operation just like a management API.
- Avoid exposing sensitive data through attributes, notification \`userData\`, or error descriptions.
- When a remote connector is present, configure authentication, authorization, encryption, and network restrictions.
- Log operations that have side effects, while never logging credentials or secrets.
- Keep ObjectNames structured and stable, avoiding naming collisions across instances.
- Consider idempotency and timeouts for operations that may be invoked repeatedly.

MBeans are useful for JVM management, but they do not replace metrics systems, audit trails, or business APIs. For long-term telemetry, a dedicated metrics system can be integrated; JMX is suited for direct inspection and control.

## 15. Hands-On Exercises

### Exercise 1: Add an attribute

Add to \`CacheMonitor\`:

\`\`\`java
private volatile boolean enabled = true;

@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}

@ManagedAttribute
public void setEnabled(boolean enabled) {
    this.enabled = enabled;
}
\`\`\`

Restart the application context, open JConsole, and check that the \`Enabled\` attribute is readable/writable according to the metadata. Read the value again after changing it, confirming the state resides on the same Spring bean.

### Exercise 2: Change the ObjectName

Change:

\`\`\`text
learning.jmx:type=CacheMonitor,name=main
\`\`\`

to:

\`\`\`text
learning.jmx:type=CacheMonitor,name=secondary
\`\`\`

After the context restarts, query the new ObjectName and verify that the old name no longer represents an MBean managed by this context. Do not modify an ObjectName when a production application has clients depending on the old name without coordinating the change.

### Exercise 3: Disable export

Temporarily remove \`@EnableMBeanExport\` in a plain Spring Framework application with no other exporter. The \`CacheMonitor\` bean still exists as a Spring bean created by \`@ComponentScan\`, but the MBean is no longer registered by the annotation exporter.

This illustrates two distinct lifecycles:

\`\`\`text
@Component -> Spring bean exists in the context

@EnableMBeanExport + @ManagedResource
    -> bean gains a management interface in the MBeanServer
\`\`\`

### Exercise 4: Verify with a JMX client

Write the code:

\`\`\`java
ObjectName name = new ObjectName(
    "learning.jmx:type=CacheMonitor,name=main"
);

if (server.isRegistered(name)) {
    System.out.println(
        server.getAttribute(name, "RefreshCount")
    );
}
\`\`\`

Then explain why \`isRegistered\` does not guarantee a subsequent \`getAttribute\` will always succeed if the MBean could be unregistered between the two calls.

## 16. Self-Check Questions

1. Why is \`@ManagedResource\` alone not enough for an MBean to appear if an exporter is missing?
2. Which component does \`@EnableMBeanExport\` activate?
3. How does \`AnnotationMBeanExporter\` differ from an \`MBeanServer\`?
4. Why must \`ObjectName\` be unique within an MBeanServer?
5. Are all public methods of a bean exposed when export is enabled?
6. Why might a local client fail to see an MBean if the exporter uses a separate MBeanServer?
7. Does \`@EnableMBeanExport(server = "jmxServer")\` take a bean name or an endpoint URL?
8. What are \`@ManagedAttribute\` and \`@ManagedOperation\` used for respectively?
9. Why does enabling export not equate to enabling remote JMX?
10. When Spring Boot has an auto-configured exporter, what must you watch out for when adding \`@EnableMBeanExport\`?

To answer, distinguish in turn between the Spring bean, annotation metadata, exporter, ObjectName, MBeanServer, and client connection. These are independent responsibilities forming a complete management flow.

## 17. Key Takeaways

\`\`\`text
@Configuration + @EnableMBeanExport
     |
     v
AnnotationMBeanExporter
     |
     v
Spring beans with @ManagedResource
     |
     +-- @ManagedAttribute -> JMX attribute
     |
     +-- @ManagedOperation -> JMX operation
     |
     +-- @ManagedNotification -> notification metadata
     |
     v
ObjectName + MBeanServer
     |
     v
JConsole / JMX client
\`\`\`

**Important rule:** \`@EnableMBeanExport\` activates **the MBean export process from Spring**, whereas \`@ManagedResource\` and the management annotations describe **what clients are permitted to see and invoke**. Remote connectivity, access permissions, ObjectName uniqueness, and lifecycle management still need to be configured and verified separately.
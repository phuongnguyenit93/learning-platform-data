# Configuring JMX with the XML context Namespace in Spring Framework

## 1. Lesson Objectives

Spring Framework supports exporting Spring beans as JMX MBeans using Java configuration, annotations, or XML. For projects using a Spring XML application context, the concise and common configuration approach is to declare the **\`context\` namespace** and use the element:

\`\`\`xml
<context:mbean-export/>
\`\`\`

This element activates the mechanism for exporting beans with **Spring JMX annotation metadata** as MBeans and sets up the required components such as the exporter, metadata source, assembler, and naming strategy. It does not arbitrarily turn every bean in the container into an MBean, nor does it automatically open a JMX remote port.

After this lesson, you will be able to:

1. Declare the \`context\` namespace and its corresponding XSD in XML.
2. Understand the role of \`<context:mbean-export/>\` in annotation-driven JMX.
3. Distinguish \`context:mbean-export\` from \`context:component-scan\`, a manual \`MBeanExporter\`, and a JMX remote connector.
4. Write a bean with \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` and export it using XML.
5. Specify an \`MBeanServer\` when the application has multiple servers or needs a specific platform server.
6. Check \`ObjectName\`, \`MBeanInfo\`, duplicate-name errors, and differences between Spring Framework XML and Spring Boot.
7. Evaluate security risks when MBeans are exposed.

## 2. How It Works

\`\`\`text
               applicationContext.xml
               +---------------------+
               | <context:component-scan/>
               | <context:mbean-export/>
               +----------+----------+
                          |
                Spring ApplicationContext
                          |
               +----------+-----------+
               |                      |
          Spring beans        JMX export support
               |                      |
               |              Annotation metadata
               |                      |
               |                MBeanExporter
               |                      |
               +----------------------+
                          |
                   MBeanServer
                          |
                       ObjectName
                          |
                      JMX clients
\`\`\`

**Two different tasks:**
- \`<context:component-scan/>\` creates or discovers Spring beans from classes with stereotype annotations.
- \`<context:mbean-export/>\` configures the mechanism to export Spring beans with appropriate JMX management metadata to an \`MBeanServer\`.

If a bean is declared with \`<bean>\` instead of component scan, it can still be exported as long as it has the appropriate JMX annotations and the exporter detects it. Component scan is not required for JMX export to work.

## 3. The context Namespace and XML Schema

A basic XML configuration:

\`\`\`xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="com.example.monitoring"/>

    <context:mbean-export/>

</beans>
\`\`\`

Where:

- The default \`xmlns\` is the \`beans\` namespace, allowing \`<bean>\`, \`<property>\`, and Spring container elements.
- \`xmlns:context\` declares the \`context\` prefix for additional Spring elements, including \`mbean-export\`.
- \`xsi:schemaLocation\` maps namespace URIs to XSD locations so parsers/IDEs recognize the syntax.
- \`<context:component-scan>\` scans the \`com.example.monitoring\` package and registers classes with stereotype annotations.
- \`<context:mbean-export/>\` enables annotation-driven JMX export.

Namespace URIs typically use \`http://www.springframework.org/schema/...\` as the **namespace identifier**; XSD URLs can use HTTPS. Spring's parser has an internal schema mapping mechanism tied to the corresponding Spring dependencies; you should not assume it must download XSDs over the Internet on every startup.

### Example missing prefix

\`\`\`xml
<!-- Invalid if xmlns:context is not declared -->
<context:mbean-export/>
\`\`\`

If the XML has not defined \`xmlns:context\` and the matching schema location, the parser cannot recognize the element.

### Why is it called "XML namespace context"?

This is an XML namespace of Spring Framework, not a Java \`Context\` class name or a JMX domain. It is the Spring XML way to configure features such as component scanning, annotation configuration, and JMX export.

## 4. Managed Bean with JMX Annotations

Create a simple bean:

\`\`\`java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders",
    description = "Order queue administration"
)
public class OrderQueueMonitor {

    private final AtomicInteger pending = new AtomicInteger();

    @ManagedAttribute(description = "Current pending jobs")
    public int getPendingCount() {
        return pending.get();
    }

    @ManagedOperation(description = "Reset queue counter")
    public void resetCounter() {
        pending.set(0);
    }

    public void recordPending(int count) {
        pending.set(count);
    }
}
\`\`\`

When the application loads the XML from section 3:

1. Component scan discovers \`OrderQueueMonitor\` and creates a Spring bean.
2. JMX export support reads \`@ManagedResource\`.
3. The JMX name is taken from \`objectName\`.
4. \`getPendingCount()\` is exposed as the JMX attribute \`PendingCount\`.
5. \`resetCounter()\` is exposed as a JMX operation.
6. \`recordPending(int)\` does not automatically become an operation just because it is a public method.

**Important:** \`@ManagedResource\` provides class-level metadata; \`@ManagedAttribute\` and \`@ManagedOperation\` describe the management surface at the method level. Do not omit annotations and expect all public methods to appear automatically under the same mechanism.

## 5. Checking Results After Loading XML

Assume the XML is in the classpath at \`applicationContext.xml\`:

\`\`\`java
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class JmxXmlDemo {
    public static void main(String[] args) throws Exception {
        try (ClassPathXmlApplicationContext context =
                 new ClassPathXmlApplicationContext(
                     "applicationContext.xml"
                 )) {

            // The application keeps the context active during its usage lifecycle.
            var server =
                java.lang.management.ManagementFactory
                    .getPlatformMBeanServer();

            var name = new javax.management.ObjectName(
                "com.example.monitoring:type=Queue,name=Orders"
            );

            System.out.println(
                "Registered: " + server.isRegistered(name)
            );

            if (server.isRegistered(name)) {
                var info = server.getMBeanInfo(name);

                System.out.println(
                    "MBean description: " + info.getDescription()
                );

                for (var attribute : info.getAttributes()) {
                    System.out.println(
                        "Attribute: " + attribute.getName()
                    );
                }

                for (var operation : info.getOperations()) {
                    System.out.println(
                        "Operation: " + operation.getName()
                    );
                }
            }
        }
    }
}
\`\`\`

This illustrates checking from within the same JVM. If the exporter uses an \`MBeanServer\` other than the platform server, retrieve the exact server configured by Spring rather than assuming \`ManagementFactory.getPlatformMBeanServer()\` is always the target.

To verify in a real environment, you can connect JConsole to the right JVM, select the **MBeans** tab, browse the \`com.example.monitoring\` domain, and check attributes/operations.

### Why can MBeanInfo be read?

\`MBeanInfo\` describes the management interface of an MBean:
- The MBean's description.
- List of attributes and data types.
- Readable/writable flags.
- List of operations and signatures.
- Notification metadata if any.

This is the data JMX clients actually see, which is different from merely inspecting annotations via reflection in the source code.

## 6. What Does the context:mbean-export Element Do?

\`<context:mbean-export/>\` sets up annotation-driven MBean export in the application context.

Conceptually:

\`\`\`text
<context:mbean-export/>
        |
        v
AnnotationJmxAttributeSource
        |
        +--> MetadataMBeanInfoAssembler
        |          |
        |          v
        |    Attributes/operations
        |
        +--> MetadataNamingStrategy
                   |
                   v
                ObjectName
        |
        v
     MBeanExporter
        |
        v
     MBeanServer
\`\`\`

This is a diagram of roles, not a guarantee that every Spring version always creates beans with the exact same internal names. The namespace configuration bundles the boilerplate for the exporter, assembler, metadata reader, and naming support.

### What it does not do

\`<context:mbean-export/>\` does not automatically:
- Open a remote RMI connector or JMX TCP port.
- Create a JMX client.
- Register every \`@Component\` that lacks appropriate management metadata.
- Convert \`@RestController\` endpoints into JMX operations.
- Replace Spring Boot Actuator configuration.
- Set up authentication/authorization for remote JMX.
- Create a metrics registry or persist notification history.

Exporting MBeans is one concern; how clients reach the MBeanServer is another concern.

## 7. Customizing the MBeanServer in XML

When multiple MBeanServers exist or you need to use the platform server explicitly, you can define a server bean and reference it from \`mbean-export\` via the \`server\` attribute supported in the Spring XML namespace.

One way to declare the platform MBeanServer using a factory method:

\`\`\`xml
<bean id="platformMBeanServer"
      class="java.lang.management.ManagementFactory"
      factory-method="getPlatformMBeanServer"/>

<context:mbean-export server="platformMBeanServer"/>
\`\`\`

This example can be placed inside \`<beans>\` alongside the namespace declarations from section 3.

Meaning:
- The \`platformMBeanServer\` bean is a reference to the current platform MBeanServer.
- \`server="platformMBeanServer"\` directs the export mechanism to that MBeanServer.
- This avoids relying on automatic selection when the JVM has multiple MBeanServers.

If a specific Spring Framework environment has a different XML configuration or the namespace schema version does not support a needed attribute, using an explicit \`MBeanExporter\` with the \`server\` property is an alternative.

### Why specify the server?

A JVM may contain:
- The platform MBeanServer.
- A custom MBeanServer from an embedded container.
- A server provided by an application server.
- A dedicated server from a test module.

An MBean registered in one server does not automatically appear in another server. If JConsole or a connector is looking at the platform server while the exporter uses a custom server, you might think the application is not exporting.

## 8. XML Bean Definition Without Component Scan

Using \`@Component\` is not mandatory if you want to create beans through XML:

\`\`\`xml
<bean id="orderQueueMonitor"
      class="com.example.monitoring.OrderQueueMonitor"/>

<context:mbean-export/>
\`\`\`

As long as the class has JMX metadata recognized by the exporter/assembler, a bean created via XML is also an export candidate.

Therefore:
- \`context:component-scan\` handles **bean discovery**.
- \`context:mbean-export\` handles **JMX management export**.

You can use either way to create beans:
- Explicit \`<bean>\` declarations.
- Scanning \`@Component\` with \`context:component-scan\`.

Depending on the project, they can be combined, but avoid registering two different Spring beans with the same ObjectName.

## 9. Explicit Registration in XML with MBeanExporter

When you want exact control over which beans are exported, you can configure \`MBeanExporter\` explicitly instead of using annotation autodetection.

Example of a Standard MBean:

\`\`\`java
package com.example.monitoring;

public interface CacheMonitorMBean {
    int getEntryCount();
    void resetStats();
}
\`\`\`

\`\`\`java
package com.example.monitoring;

public class CacheMonitor implements CacheMonitorMBean {
    @Override
    public int getEntryCount() {
        return 42;
    }

    @Override
    public void resetStats() {
        // Update metrics according to application logic.
    }
}
\`\`\`

XML:

\`\`\`xml
<bean id="cacheMonitor"
      class="com.example.monitoring.CacheMonitor"/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <property name="beans">
        <map>
            <entry key="com.example.monitoring:type=Cache,name=Products"
                   value-ref="cacheMonitor"/>
        </map>
    </property>
</bean>
\`\`\`

With this approach:
- The exporter receives an explicit list of beans.
- The JMX name is specified by the key in the map.
- A Standard MBean has an interface \`CacheMonitorMBean\` defining the management methods.
- Annotations on the class are not needed if a compliant Standard MBean interface is used.

If you want to export annotation-based POJOs using an explicit \`MBeanExporter\`, you must configure the appropriate metadata source/assembler/naming strategy; merely setting \`setBeans\` does not guarantee all annotations will be applied.

### Do not declare two overlapping exporters

Example configuration to avoid:

\`\`\`xml
<context:mbean-export/>

<bean id="jmxExporter"
      class="org.springframework.jmx.export.MBeanExporter">
    <!-- Configuring another exporter for the same set of MBeans -->
</bean>
\`\`\`

There may be cases requiring multiple exporters with separate ownership, but you should not add a second exporter when namespace export is already active without clearly defining each set of beans and server.

If two exporters attempt to register the same ObjectName on the same server, a registration collision will occur depending on the policy.

## 10. Naming: ObjectName and Java Bean Name

In XML:

\`\`\`xml
<bean id="orderQueueMonitor"
      class="com.example.monitoring.OrderQueueMonitor"/>
\`\`\`

\`orderQueueMonitor\` is the Spring bean name.

In the annotation:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
\`\`\`

\`com.example.monitoring:type=Queue,name=Orders\` is the JMX ObjectName.

An ObjectName typically has the structure:

\`\`\`text
domain:key=value,key=value
\`\`\`

Example:

\`\`\`text
com.example.monitoring:type=Queue,name=Orders
\`\`\`

Do not set ObjectName to an arbitrary string containing only the Spring bean name if it does not conform to JMX syntax.

### ObjectName with wildcards

\`\`\`java
ObjectName query = new ObjectName(
    "com.example.monitoring:type=Queue,*"
);
\`\`\`

This is a pattern for querying multiple MBeans. A specific MBean requires a concrete ObjectName.

### Dynamic values

If a name needs to contain commas or equals signs from configuration:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Queue");
properties.put("name", ObjectName.quote("Orders,EU=West"));

ObjectName name = new ObjectName(
    "com.example.monitoring",
    properties
);
\`\`\`

For dynamic ObjectNames per tenant/instance, annotations with compile-time constant values are usually not flexible enough; a naming strategy or explicit mapping/programmatic registration is needed.

## 11. Bean Lifecycle and JMX Registration

When a Spring context starts up normally:

\`\`\`text
Read XML config
      |
      v
Create Spring beans
      |
      v
Initialize JMX export support
      |
      v
Register MBeans
      |
      v
JMX clients use ObjectNames
      |
      v
Close ApplicationContext
      |
      v
Exporter unregisters MBeans it owns
\`\`\`

Things to keep in mind:
- Not every Spring bean is exported.
- An MBean may already exist on the server before the context starts.
- If the context closes normally, the exporter cleans up the registrations it is responsible for according to lifecycle/policy.
- If the JVM is killed or crashes, you cannot rely on shutdown logic completing.
- Multiple Spring contexts may share the platform MBeanServer and contend for names.

A stable ObjectName makes it easy for management tooling to find the MBean, but it can cause collisions when multiple instances of the same class are exported to one server.

## 12. XML Schema and Spring Versions

When working with XML configuration, there are three compatibility layers to distinguish:

1. **Spring Framework version:** the namespace parser and attributes of \`context:mbean-export\`.
2. **JDK version:** JMX APIs and the \`java.management\` module.
3. **Application dependencies:** the Spring jars providing context and JMX support.

Spring 5/6 both have JMX export mechanisms, though some APIs or properties may vary across versions. With Spring 6/7, use the matching dependencies and Java version.

If the XML parser reports:

\`\`\`text
Cannot locate BeanDefinitionParser for element [mbean-export]
\`\`\`

or an XSD error:
- Check that the \`spring-context\` dependency is present.
- Check that the namespace URI and schema location are correct.
- Check that Spring jar versions are consistent.
- Check whether the attributes used are supported by the schema of that version.

Do not try to fix the error by mixing different versions of Spring jars or replacing the namespace with an arbitrary URL.

## 13. Differences from Spring Boot Auto-Configuration

A traditional Spring Framework XML project typically loads:

\`\`\`java
new ClassPathXmlApplicationContext("applicationContext.xml");
\`\`\`

Spring Boot typically uses \`@SpringBootApplication\` and auto-configuration. Boot has its own JMX export mechanism, depending on properties like \`spring.jmx.enabled\` and Actuator configuration.

If integrating legacy XML into Boot via \`@ImportResource\`:

\`\`\`java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ImportResource;

@SpringBootApplication
@ImportResource("classpath:legacy-jmx.xml")
public class Application {
}
\`\`\`

you need to check whether Boot has already created an exporter. If the XML also has \`<context:mbean-export/>\`, duplicate registration may occur.

To stay in control, decide on one primary configuration path:
- Spring XML namespace export.
- Java \`@EnableMBeanExport\`.
- Spring Boot auto-configuration.
- Explicitly configured \`MBeanExporter\`.

Using multiple paths should only be intentional, with non-overlapping ownership and ObjectNames.

## 14. Troubleshooting When XML Export Fails

### 14.1. MBean does not appear

Possible causes:
- XML context has not been loaded.
- \`context:mbean-export\` has not been declared.
- Target bean was not created or package scan is wrong.
- Annotation metadata is inappropriate.
- Exporter uses a different MBeanServer.
- ObjectName is wrong or collides.

Procedure:
1. Verify the Spring bean exists in the context.
2. Check that the XML namespace parser is working.
3. Verify the exporter has initialized.
4. Check registration logs.
5. Query the right \`MBeanServer\` with \`isRegistered()\`.
6. Read \`MBeanInfo\` once the MBean appears.

### 14.2. ObjectName collision

Two beans might declare the same:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Queue,name=Orders"
)
\`\`\`

If both are exported to the same server, JMX does not allow the same ObjectName to register two MBeans simultaneously.

Solutions:
- Set a distinguishing \`instance\` or \`name\`.
- Narrow the scope of autodetection.
- Avoid multiple exporters overlapping on one set of MBeans.
- Choose a deliberate registration policy if needed; do not use replace indiscriminately.

### 14.3. Missing attribute or operation

If the MBean name exists but the interface is wrong:
- Check \`@ManagedAttribute\`/\`@ManagedOperation\`.
- Check getter/setter conventions.
- Check the metadata assembler.
- Check whether Spring proxy/AOP alters the exported object.
- Use \`MBeanInfo.getAttributes()\`/\`getOperations()\`.

### 14.4. JConsole cannot connect

Configuring \`<context:mbean-export/>\` does not enable remote JMX. To connect from another machine, a JMX connector and security/network configuration are needed.

If local JConsole attaches fine but remote fails, the cause usually lies in the remote connector/RMI port, firewall, hostname, or authentication, not a missing XML namespace.

## 15. Security: Exporting Does Not Mean Granting Access Control

MBeans can expose:
- Read-only metrics or status.
- Writable configuration attributes.
- State-changing operations.
- JVM and application information.

A sensitive example:

\`\`\`java
@ManagedOperation(description = "Clear all queued jobs")
public void clearAllJobs() {
    queueService.clearAll();
}
\`\`\`

If the exporter exposes that operation, users with corresponding JMX permissions can invoke it. Therefore:
- Do not expose sensitive methods merely for debugging convenience.
- Restrict \`invoke\` and \`setAttribute\` permissions.
- Secure remote connectors, especially over public networks.
- Avoid returning secrets and personal data via managed attributes.
- Log/audit high-impact operations when needed.
- Review each management annotation like changing an administrative API.

\`<context:mbean-export/>\` only configures the export mechanism; it does not automatically grant or deny permissions per method.

## 16. XML Namespace and Alternatives

| Configuration Approach | Best Used When | Characteristics |
|---|---|---|
| \`<context:mbean-export/>\` | Spring XML applications with JMX annotations | Concise, automatically sets up annotation export |
| \`@EnableMBeanExport\` | Java \`@Configuration\` | Conceptually equivalent for annotation-driven export |
| Explicit \`MBeanExporter\` bean | Wanting control over bean list, assembler, server | Flexible, though more boilerplate |
| Spring Boot JMX auto-config | Boot applications configured via properties | Requires understanding current Boot/Actuator behavior |

Do not pick "whatever is newest" while ignoring project structure. For legacy XML applications, \`context:mbean-export\` is usually concise and easy to maintain. When a project is migrating toward Java config, \`@EnableMBeanExport\` can be used. For strict security requirements and allowlists, an explicit exporter may be preferable.

## 17. Comprehensive Hands-On Exercises

### Exercise A — Export a bean with the XML namespace

1. Create \`OrderQueueMonitor\` with \`@Component\`, \`@ManagedResource\`, and \`@ManagedAttribute\`.
2. Create \`applicationContext.xml\` containing \`context:component-scan\` and \`context:mbean-export\`.
3. Initialize \`ClassPathXmlApplicationContext\`.
4. Query \`com.example.monitoring:type=Queue,name=Orders\`.
5. Inspect attributes and operations via \`MBeanInfo\`.
6. Close the context.

### Exercise B — Without component-scan

1. Remove \`@Component\`.
2. Declare the bean with \`<bean id="..." class="..."/>\`.
3. Keep \`@ManagedResource\` and namespace export.
4. Restart the context.
5. Verify the MBean can still be exported.

### Exercise C — Specifying the platform MBeanServer

1. Create a factory bean from \`ManagementFactory.getPlatformMBeanServer()\`.
2. Configure \`server\` on the namespace export.
3. Inspect the platform MBeanServer directly.
4. Compare with a custom server if the test environment supports it.

### Exercise D — Creating a conflict to observe

1. Create two beans with the same ObjectName.
2. Have the exporter consider both.
3. Observe the exception/collision.
4. Fix the naming or export scope.
5. Re-verify with \`isRegistered()\`.

## 18. Self-Check Questions

**Question 1.** What is \`<context:mbean-export/>\` used for?  
**Answer:** Enabling annotation-driven JMX export in a Spring XML application context.

**Question 2.** Does \`<context:component-scan/>\` automatically export MBeans?  
**Answer:** No. It registers Spring beans; JMX export is a separate mechanism.

**Question 3.** If a class has \`@ManagedResource\` but no exporter is declared, will the MBean appear?  
**Answer:** You cannot expect it to. The annotation is only metadata; an export mechanism is required.

**Question 4.** Does XML namespace export automatically open a remote JMX RMI port?  
**Answer:** No. A remote connector must be configured separately.

**Question 5.** What should you do to ensure MBeans reside in the platform server?  
**Answer:** Specify \`ManagementFactory.getPlatformMBeanServer()\` for the exporter if certainty is needed, then verify on the exact server.

**Question 6.** Why should you avoid enabling namespace export and declaring a second exporter for the same set of beans simultaneously?  
**Answer:** It can lead to registration collisions on the same ObjectName.

**Question 7.** If an MBean exists but is missing an operation, where should you check?  
**Answer:** Check the annotations/assembler and \`MBeanInfo.getOperations()\` of the registered MBean.

## 19. Key Takeaways

- \`<context:mbean-export/>\` is the way to configure annotation-driven JMX export using the XML \`context\` namespace.
- The XML must declare \`xmlns:context\` and the appropriate schema location.
- \`context:component-scan\` creates Spring beans; \`context:mbean-export\` manages exporting beans with appropriate JMX metadata.
- \`@ManagedResource\`, \`@ManagedAttribute\`, and \`@ManagedOperation\` define the management contract read by the exporter.
- Distinguish between the Spring bean name, JMX ObjectName, and MBeanServer.
- You can configure the target MBeanServer when the environment has multiple servers.
- Namespace export does not automatically enable JMX remote connections or authorization.
- Avoid multiple exporters with overlapping responsibilities and duplicate ObjectNames.
- Verify effectiveness using \`MBeanServer.isRegistered()\` and \`getMBeanInfo()\` on the actual server.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — XML Schema-based Configuration: https://docs.spring.io/spring-framework/reference/core/appendix/xsd-schemas.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`@EnableMBeanExport\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/EnableMBeanExport.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html

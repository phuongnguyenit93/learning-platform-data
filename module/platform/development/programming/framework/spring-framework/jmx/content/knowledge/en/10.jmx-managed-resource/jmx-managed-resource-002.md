# ObjectName, description, and Class-Level Metadata in @ManagedResource

## 1. Lesson Objectives

In Spring Framework JMX, the \`@ManagedResource\` annotation describes **a managed bean** at the class level. The most important pieces of information are \`objectName\` (JMX identifier) and \`description\` (description for management tools), along with several metadata attributes such as \`currencyTimeLimit\`, \`log\`, \`logFile\`, \`persistPolicy\`, \`persistPeriod\`, and \`persistName\`.

Key point: an annotation is **declarative metadata**. For metadata to take effect in JMX, Spring must have an appropriate export mechanism, typically an \`MBeanExporter\` configured consistently with an annotation reader, assembler, and naming strategy. The annotation does not call \`MBeanServer.registerMBean()\` by itself.

After this lesson, you will be able to:
- Explain the class-level role of \`@ManagedResource\` and distinguish it from \`@ManagedAttribute\` and \`@ManagedOperation\`.
- Define and validate an \`ObjectName\` according to JMX syntax.
- Understand the meaning of \`description\` and other metadata fields, as well as the practical limits of their effects.
- Configure Spring export so that metadata is reflected in \`MBeanInfo\`.
- Avoid common mistakes involving duplicate names, wildcards, dynamic values, exporter configuration, and confusing metadata with runtime behavior.

## 2. The Big Picture

\`\`\`text
Spring bean
   |
   | @ManagedResource(objectName=..., description=..., ...)
   | @ManagedAttribute / @ManagedOperation
   v
AnnotationJmxAttributeSource
   |
   +--> MetadataNamingStrategy ------> ObjectName
   |
   +--> MetadataMBeanInfoAssembler --> MBeanInfo
   |
   v
MBeanExporter
   |
   | register / adapt bean
   v
MBeanServer
   |
   v
JConsole / VisualVM / JMX client
\`\`\`

Roles:

| Component | Responsibility |
|---|---|
| \`@ManagedResource\` | Provides class-level management metadata; especially \`objectName\`, \`description\` |
| \`AnnotationJmxAttributeSource\` | Reads annotations and produces internal metadata used by Spring JMX |
| \`MetadataNamingStrategy\` | Uses metadata to determine the MBean name |
| \`MetadataMBeanInfoAssembler\` | Converts management metadata into the exposed MBean information |
| \`MBeanExporter\` | Exports Spring beans to \`MBeanServer\`, applying naming and assembly |
| \`MBeanServer\` | Registry of JMX MBeans; queried by \`ObjectName\` |
| \`MBeanInfo\` | Describes the MBean and its management interface (attributes, operations, notifications...) |

Not every \`@Component\` is exported automatically; not every \`@ManagedResource\` automatically appears in JConsole if the JMX export mechanism has not been enabled.

## 3. @ManagedResource Is a Class-Level Annotation

Example:

\`\`\`java
package com.example.monitoring;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration"
)
public class ProductCacheMonitor {
    private volatile int entryCount;

    @ManagedAttribute(description = "Current cached entries")
    public int getEntryCount() {
        return entryCount;
    }

    @ManagedOperation(description = "Clear cached entries")
    public void clear() {
        entryCount = 0;
    }
}
\`\`\`

In this example:

- \`@Component\` makes the object a Spring bean when component-scanned.
- \`@ManagedResource\` describes the bean as a class-level managed object, with a JMX name and description.
- \`@ManagedAttribute\` indicates that the \`getEntryCount()\` getter should be exposed as a JMX attribute.
- \`@ManagedOperation\` indicates that \`clear()\` should be exposed as a JMX operation.
- An appropriate exporter must be enabled for a JMX client to see the MBean.

**Annotation scope:** \`@ManagedResource\` applies to the type/class; method-level or management-attribute metadata is declared with separate annotations. Do not treat \`@ManagedResource\` as a directive to expose every public method.

## 4. objectName: The JMX Identifier of an MBean

### 4.1. Syntax and Meaning

A JMX \`ObjectName\` typically has the form:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Examples:

\`\`\`text
com.example.monitoring:type=Cache,name=Products
com.example.monitoring:type=Worker,name=Import
java.lang:type=Memory
\`\`\`

An \`ObjectName\` consists of:
- **Domain:** a namespace such as \`com.example.monitoring\`.
- **Key properties:** a list of key/value pairs, e.g., \`type=Cache\`, \`name=Products\`.
- **Concrete name or pattern:** wildcards \`*\`/\`?\` can turn a name into a query pattern. When registering an individual MBean, a concrete name is required.

ObjectName is a **JMX identifier**, not:
- a Spring bean name in \`ApplicationContext\`;
- a Java package/class name;
- a URI or HTTP endpoint;
- a Micrometer metric name.

The Spring bean \`productCacheMonitor\` can be exported under the ObjectName \`com.example.monitoring:type=Cache,name=Products\`; they live in two different namespaces.

### 4.2. Why Is objectName Important?

\`ObjectName\` is the identifier key used in \`MBeanServer\`. A client calls:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);
boolean exists = server.isRegistered(name);
\`\`\`

to query an MBean in a **specific MBeanServer**.

If two exporters attempt to register two different MBeans with the same \`ObjectName\` on the same server, a registration conflict occurs. The exporter's policy determines whether to fail, ignore, or replace, but a policy should not be used to mask a naming bug.

### 4.3. ObjectName Does Not Depend on Key Order

Two names can be equivalent:

\`\`\`java
ObjectName first = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

ObjectName second = new ObjectName(
    "com.example.monitoring:name=Products,type=Cache"
);

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
\`\`\`

Use \`ObjectName.equals()\` or \`getCanonicalName()\` to compare according to JMX rules; avoid relying on the original string order.

### 4.4. Do Not Arbitrarily Concatenate Dynamic Values into Annotations

The \`objectName\` value in an annotation is declared statically at compile time:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products"
)
\`\`\`

You cannot put a runtime Java variable into an annotation attribute in the usual way:

\`\`\`java
// Invalid if runtimeName is a variable computed at runtime:
// @ManagedResource(objectName = "com.example:type=Cache,name=" + runtimeName)
\`\`\`

If the ObjectName needs to depend on a tenant, instance, or runtime configuration, choose an appropriate naming strategy or programmatic registration and construct \`ObjectName\` via the Java API.

Example:

\`\`\`java
import java.util.Hashtable;
import javax.management.ObjectName;

String dynamicName = "Products,EU=West";

Hashtable<String, String> properties = new Hashtable<>();
properties.put("type", "Cache");
properties.put("name", ObjectName.quote(dynamicName));

ObjectName name =
    new ObjectName("com.example.monitoring", properties);
\`\`\`

\`ObjectName.quote(dynamicName)\` preserves the literal meaning of data containing delimiters or wildcards. Do not apply \`quote()\` to the entire ObjectName; only quote **property values** as needed.

### 4.5. Avoid ObjectName Patterns During Registration

Example:

\`\`\`java
ObjectName pattern =
    new ObjectName("com.example.monitoring:type=Cache,*");

System.out.println(pattern.isPattern()); // true
\`\`\`

This name is suitable for \`queryNames()\` but is not a concrete name for registering an MBean. If \`@ManagedResource.objectName\` is inadvertently configured as a pattern, export may fail.

## 5. description: Metadata That Helps Management Tools Understand the MBean

Example:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration"
)
\`\`\`

\`description\` provides an MBean-level description. When the assembler reads the annotation and builds \`MBeanInfo\`, the description can be viewed by clients through the API or UIs such as JConsole.

To read it in Java:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

MBeanInfo info = server.getMBeanInfo(name);
System.out.println(info.getDescription());
\`\`\`

**Important:** \`description\` is information for operators and clients; it does not by itself:
- create JMX attributes/operations;
- ensure an operation is safe;
- enable authentication/authorization;
- configure logs or metrics;
- change the bean's business behavior.

Choose a short, clear description aligned with the MBean's management purpose. For instance, \`"Product cache administration"\` is more helpful than \`"My Bean"\`.

### 5.1. Class-Level and Method-Level Descriptions

\`\`\`java
@ManagedResource(description = "Product cache administration")
public class ProductCacheMonitor {

    @ManagedAttribute(
        description = "Current number of cache entries"
    )
    public int getEntryCount() {
        return 42;
    }
}
\`\`\`

The class-level description resides in \`MBeanInfo.getDescription()\`. An attribute's description is presented in its attribute metadata, such as \`MBeanAttributeInfo.getDescription()\`.

Do not use \`@ManagedResource.description\` to substitute for metadata on every attribute or operation; each level has its own meaning.

## 6. Other Class-Level Metadata Fields

\`@ManagedResource\` also declares fields related to JMX management metadata:

| Attribute | Meaning | Things to Remember |
|---|---|---|
| \`objectName\` | JMX name of the MBean | It is an identifier; must be valid and avoid duplicates |
| \`description\` | MBean description | For clients/operators; does not change behavior by itself |
| \`currencyTimeLimit\` | Hints at the validity duration of management information in Model MBean metadata | Not an HTTP timeout or retry policy |
| \`log\` | Metadata related to Model MBean logging capability | Does not automatically guarantee application logging |
| \`logFile\` | Log path information for Model MBean features | Not synonymous with SLF4J/Logback configuration |
| \`persistPolicy\` | Metadata hinting at the Model MBean's persistence policy | Does not automatically create database transactions |
| \`persistPeriod\` | Time parameter of the persistence policy | Meaningful when supported by the corresponding mechanism |
| \`persistName\` | Name related to the persistence resource | Does not replace an application data store |
| \`persistLocation\` | Persistence location in metadata | Does not automatically implement durable storage |

Fields beyond \`objectName\` and \`description\` relate to JMX Model MBean capabilities and descriptors. **Do not infer that simply attaching the annotation causes the application to enable file logging, periodic state saving, or time-based caching.** Runtime effect depends on the exporter, assembler, Model MBean implementation, and operational configuration.

### Extended Metadata Example

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache administration",
    currencyTimeLimit = 15,
    log = false
)
public class ProductCacheMonitor {
    // ...
}
\`\`\`

Here \`currencyTimeLimit\` is management metadata placed into the descriptor as supported, not a 15-second timeout per Java method or a business cache TTL. Any side effects such as MBean result caching or descriptor updates must be verified against the JMX implementation in use.

For production systems, only declare Model MBean fields whose effects you clearly understand and operationally need. When only a name and description are needed, minimal configuration is usually easier to maintain.

## 7. How Does Spring Read and Apply Metadata?

A Spring bean with \`@ManagedResource\` does not become an MBean on its own. You can use annotation-driven export:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

This must be combined with component scanning or \`@Bean\` to create the target bean.

Or configure \`MBeanExporter\` explicitly:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ExplicitJmxConfiguration {

    @Bean
    public MBeanExporter mBeanExporter() {
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
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

The two snippets are **two alternative approaches**; within one context you should not create multiple exporters with overlapping responsibilities. When using Spring Boot, check JMX auto-configuration and properties like \`spring.jmx.enabled\` before adding manual configuration.

### Order of Responsibilities

1. Spring creates the \`ProductCacheMonitor\` bean.
2. The exporter selects the bean, directly or via autodetection.
3. \`AnnotationJmxAttributeSource\` extracts class-level metadata from \`@ManagedResource\`.
4. \`MetadataNamingStrategy\` obtains the appropriate ObjectName.
5. \`MetadataMBeanInfoAssembler\` describes attributes/operations and descriptors.
6. \`MBeanExporter\` registers the MBean into \`MBeanServer\`.
7. A JMX client reads \`MBeanInfo\`, attributes, or invokes operations.

If the exporter is not enabled, this processing chain does not happen just from having annotations on the class.

## 8. Distinguishing Class-Level Metadata from Member-Level Metadata

\`@ManagedResource\` is placed on the class and describes the entire managed resource.

Commonly accompanying annotations:

- \`@ManagedAttribute\` on getters/setters exposed as JMX attributes.
- \`@ManagedOperation\` on methods exposed as JMX operations.
- \`@ManagedOperationParameter\` on operation parameter metadata in the appropriate context.
- \`@ManagedNotification\` declares notification metadata for the MBean.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import",
    description = "Import worker administrator"
)
@ManagedNotification(
    name = "com.example.import.failed",
    description = "Import failed",
    notificationTypes = {"com.example.import.failed"}
)
public class ImportWorkerMonitor {

    @ManagedAttribute(description = "Current state")
    public String getState() {
        return "IDLE";
    }

    @ManagedOperation(description = "Request a state refresh")
    public void refresh() {
        // Request refresh from business component.
    }
}
\`\`\`

Correspondingly:

\`\`\`text
@ManagedResource
  -> describes the MBean and class-level ObjectName

@ManagedAttribute
  -> describes a JMX attribute

@ManagedOperation
  -> describes a JMX operation

@ManagedNotification
  -> describes notification types that may be emitted
\`\`\`

**Declaring notification metadata** does not mean the application actually emits notifications. To actually send notifications, you need a publisher/broadcaster and emitting code.

## 9. Verifying ObjectName and MBeanInfo via API

Technical verification after the application context starts:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxInspector {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.monitoring:type=Cache,name=Products"
        );

        System.out.println("Pattern? " + name.isPattern());
        System.out.println("Canonical: " + name.getCanonicalName());

        if (!server.isRegistered(name)) {
            System.out.println("MBean has not been registered");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println("Description: " + info.getDescription());

        for (var attribute : info.getAttributes()) {
            System.out.println("Attribute: " + attribute.getName()
                + " | " + attribute.getDescription());
        }

        for (var operation : info.getOperations()) {
            System.out.println("Operation: " + operation.getName()
                + " | " + operation.getDescription());
        }
    }
}
\`\`\`

The \`main\` snippet only works properly when run in the same JVM and against the same \`MBeanServer\` where the application exported the MBean. If run in a separate Java process, \`ManagementFactory.getPlatformMBeanServer()\` returns the platform server **of the new process**, which normally does not contain the target application's MBean.

In integration tests, invoke the inspector on the MBeanServer configured for the application context or obtain the server via the corresponding bean. When accessing another JVM, use \`JMXConnector\` and \`MBeanServerConnection\` with a configured connection.

### Checking Actual Metadata

- Did \`ObjectName\` parse validly?
- Is \`name.isPattern()\` equal to \`false\` upon registration?
- Is \`server.isRegistered(name)\` equal to \`true\`?
- Does \`MBeanInfo.getDescription()\` match expectations?
- Are the desired attributes and operations present in MBeanInfo?
- If using Model MBean descriptors, are the corresponding metadata fields populated according to the implementation?

An annotation declaration is **configuration intent**; the \`MBeanInfo\` of the registered object is the evidence of what a JMX client actually sees.

## 10. Class-Level Metadata and Inheritance

In Spring systems, beans may be created via subclasses, proxies, or AOP mechanisms. This raises a question: on **which class** does the exporter read metadata?

Things to note:

- Annotations are placed on the managed type or a type that the Spring JMX metadata reader can recognize.
- If a bean is wrapped with a JDK dynamic proxy, the runtime class may differ from the business implementation class.
- Spring has support for identifying the target class in many cases, but you should not assume every proxy type yields identical results.
- When metadata is not read, the ObjectName or exposed methods may not match expectations.

The practical solution is to inspect the ObjectName and MBeanInfo after export, especially for beans with \`@Transactional\`, \`@Async\`, Spring AOP, or proxy factories.

When naming and management metadata matter, having a dedicated interface/monitor bean for JMX often keeps the contract clearer than exporting a huge service carrying many cross-cutting proxies directly.

## 11. When to Use Static objectName vs. a Naming Strategy?

| Context | Approach |
|---|---|
| A fixed single MBean in the application | Explicit \`@ManagedResource(objectName="...")\` |
| Multiple MBeans of the same type with different instances | Factory/naming strategy computing name per instance and quoting values |
| Multi-tenant or multiple modules in one JVM | Domain/keys reflecting actual structure, avoiding collisions |
| Framework/library embedded by multiple applications | Naming policy with configurable prefix/domain and ownership rules |
| Compatibility needed with legacy JMX names | Preserve existing ObjectNames or plan client migration |

For example, you can use \`type\`, \`name\`, \`instance\` to avoid collisions:

\`\`\`text
com.example.monitoring:type=Worker,name=Import,instance=node01
com.example.monitoring:type=Worker,name=Import,instance=node02
\`\`\`

Do not add unbounded tenant IDs/user IDs into names if it causes MBean explosion or leaks sensitive information. JMX naming is also a decision about operations, access control, and client discoverability.

## 12. Common Pitfalls and How to Handle Them

### 12.1. Annotation Is Present, but JConsole Does Not Show the MBean

**Possible causes:** JMX exporter is not enabled, the bean is not created in the Spring context, autodetect does not select the bean, the name is invalid, or the client is connecting to the wrong JVM.

**How to handle:** Verify the Spring context, \`@EnableMBeanExport\` or \`MBeanExporter\` configuration, check registration logs, and call \`isRegistered()\` on the right server.

### 12.2. Description Does Not Appear as Expected

**Possible causes:** The assembler does not read annotations, the bean is exported in a way that does not use metadata as expected, or clients display MBeanInfo differently.

**How to handle:** Inspect \`MBeanInfo.getDescription()\` directly, then check \`AnnotationJmxAttributeSource\` and \`MetadataMBeanInfoAssembler\`.

### 12.3. Duplicate ObjectName

**Cause:** Two managed resources use the same domain and key/value pairs on the same MBeanServer.

**How to handle:** Choose a naming strategy with appropriate instance identifiers. If a fail/ignore/replace policy is needed, choose based on ownership and lifecycle—do not use replace indiscriminately.

### 12.4. Using Wildcards in Declared objectName

**Cause:** Unescaped \`*\` or \`?\` in the name part, or declaring a property-list pattern.

**How to handle:** Use a concrete ObjectName for registration; check \`isPattern()\`, and use \`quote()\` for dynamic values.

### 12.5. Confusing description with Security Documentation

**Cause:** Assuming an “admin only” description in an annotation protects an operation by itself.

**How to handle:** Set up authentication/authorization and restrict remote JMX connections separately. Description is only metadata.

### 12.6. Assuming persistPolicy Automatically Saves State to a Database

**Cause:** Misinterpreting a Model MBean descriptor as Spring business persistence policy.

**How to handle:** If durable saving is needed, design a real repository/transaction, database, or storage; verify Model MBean implementation capabilities before relying on metadata fields.

### 12.7. Checking Only Annotations, Skipping Export State

**Cause:** Unit tests check reflection for annotations without running MBeanExporter.

**How to handle:** Add integration tests with a Spring context and MBeanServer to verify ObjectName/MBeanInfo on the actual MBean.

## 13. Security and Metadata Design

Practical principles:

1. **Use a consistent domain:** e.g., \`com.example.monitoring\`; define specific names by resource type and instance.
2. **Keep descriptions useful:** describe management purpose; avoid exposing tokens, passwords, or personal data.
3. **Export only what is needed:** operations with side effects such as reset, clear, and reload must be evaluated carefully.
4. **Do not treat metadata as access control:** describing an MBean does not replace a security policy.
5. **Do not put unescaped dynamic data into ObjectName:** use the Java API to preserve exact key/value meaning.
6. **Verify from the client perspective:** read MBeanInfo of the registered object.
7. **Restrict remote JMX:** configure network, authentication, and appropriate protections if access outside the JVM is allowed.

## 14. Hands-On Exercises

### Exercise A: Minimal MBean

1. Create a \`SystemStatusMonitor\` bean with \`@Component\`.
2. Add:
   \`\`\`java
   @ManagedResource(
       objectName = "com.example.training:type=Status,name=System",
       description = "Application status for administrators"
   )
   \`\`\`
3. Add a \`getState()\` getter with \`@ManagedAttribute(description="Current state")\`.
4. Enable annotation-driven JMX export.
5. Use \`MBeanServer.isRegistered()\` to verify the name.
6. Use \`getMBeanInfo()\` to verify the class-level and attribute descriptions.

### Exercise B: Testing Name Collisions

1. Create two beans with the same \`@ManagedResource.objectName\`.
2. Start the context in a test environment.
3. Observe the registration error or configured policy.
4. Change the \`name\`/\`instance\` keys so the two ObjectNames differ.
5. Verify both via \`queryNames()\`.

### Exercise C: Metadata and Runtime

1. Place clear \`description\` values on the class and an operation.
2. Read back \`MBeanInfo\` of the exported MBean.
3. Add \`currencyTimeLimit\` if supported by the implementation.
4. Distinguish descriptor data from actual behavior through runtime observation, not just by looking at annotations.

## 15. Self-Check Questions

**Question 1.** What is the primary role of \`@ManagedResource\`?  
**Answer:** Declaring class-level management metadata for a bean, including ObjectName, description, and certain Model MBean metadata.

**Question 2.** Does \`@ManagedResource\` automatically register the MBean into MBeanServer?  
**Answer:** No. A JMX export mechanism is required, typically MBeanExporter or the corresponding annotation export configuration.

**Question 3.** Does \`description\` turn a method into a JMX operation?  
**Answer:** No. Operations are determined by member metadata and MBeanInfoAssembler.

**Question 4.** Why can \`com.example:type=Cache,name=A\` and \`com.example:name=A,type=Cache\` be equal?  
**Answer:** ObjectName identifies by domain and set of key/value pairs, independent of key order in the representation.

**Question 5.** Why is \`objectName="com.example:type=Cache,name=*"\` unsuitable for a specific MBean?  
**Answer:** It is an ObjectName pattern, suitable for querying but not as a concrete registration name.

**Question 6.** Does \`persistPolicy\` automatically implement persistence for a Spring service?  
**Answer:** No. It is metadata in the Model MBean context and depends on supporting mechanisms; business persistence must be designed separately.

**Question 7.** Where should you check to see the MBean description actually exported?  
**Answer:** Read \`MBeanInfo.getDescription()\` from the right \`MBeanServer\` and ObjectName after registration.

## 16. Key Takeaways

- \`@ManagedResource\` is class-level metadata for Spring JMX.
- \`objectName\` is the JMX identifier key; it must be concrete, valid, and unique within the same MBeanServer.
- \`description\` describes the entire MBean for management tools and does not replace attribute/operation annotations.
- Extended metadata such as \`currencyTimeLimit\`, \`log\`, and \`persistPolicy\` **do not automatically create** caching, logging, or business persistence.
- \`AnnotationJmxAttributeSource\`, \`MetadataNamingStrategy\`, \`MetadataMBeanInfoAssembler\`, and \`MBeanExporter\` work together to turn annotation declarations into registered MBeans.
- Spring bean name and ObjectName are two distinct identifiers.
- Always distinguish declared annotations from actual MBean information; verify with \`MBeanServer.isRegistered()\` and \`MBeanInfo\`.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`MetadataNamingStrategy\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/naming/MetadataNamingStrategy.html
- Java SE 21 API — \`ObjectName\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

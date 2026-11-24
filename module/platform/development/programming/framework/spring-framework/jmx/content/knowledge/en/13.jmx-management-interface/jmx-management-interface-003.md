# MetadataMBeanInfoAssembler and annotation metadata sources in Spring JMX

## 1. Purpose

In Spring Framework JMX, \`MetadataMBeanInfoAssembler\` is the component that turns a bean's **management metadata** into a JMX interface description. It answers the question: **which attributes, operations, and notifications will JMX clients see, along with their names and descriptions?**

With annotation-based configuration, Spring typically uses \`AnnotationJmxAttributeSource\` as the metadata source. Annotations such as \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@ManagedOperationParameter\`, and \`@ManagedNotification\` define the management contract right alongside Java code. \`MetadataMBeanInfoAssembler\` reads that contract through \`JmxAttributeSource\` and builds the information for \`MBeanExporter\` to create and register the MBean.

After this lesson, you will be able to:

- Distinguish metadata source, assembler, naming strategy, and exporter.
- Explain how annotations from classes, getters/setters, and operations become \`MBeanInfo\`.
- Configure \`MetadataMBeanInfoAssembler\` and \`AnnotationJmxAttributeSource\` in Spring Framework.
- Distinguish metadata annotations from the actual management interface on MBeanServer.
- Understand the impact of bean proxies, method visibility, property conventions, and certain metadata fields.
- Verify results using \`MBeanServer.getMBeanInfo()\` instead of only looking at source code.

## 2. Component map

\`\`\`text
          Spring bean class
                |
      @ManagedResource
      @ManagedAttribute
      @ManagedOperation
      @ManagedNotification
                |
                v
    AnnotationJmxAttributeSource
         (JmxAttributeSource)
                |
                v
    MetadataMBeanInfoAssembler
        (MBeanInfoAssembler)
                |
                v
         ModelMBeanInfo
      attributes / operations /
      notifications / descriptor
                |
                v
            MBeanExporter
                |
                v
             MBeanServer
                |
                v
       JConsole / JMX clients
\`\`\`

Another branch is responsible for naming:

\`\`\`text
@ManagedResource(objectName="...")
               |
               v
   AnnotationJmxAttributeSource
               |
               v
      MetadataNamingStrategy
               |
               v
           ObjectName
               |
               v
       MBeanExporter
\`\`\`

**An assembler is not a naming strategy.** The assembler determines the **management interface and metadata**. The naming strategy determines the **\`ObjectName\` identifier**. The exporter combines both roles and performs registration with the MBeanServer.

## 3. What is MBeanInfoAssembler?

\`org.springframework.jmx.export.assembler.MBeanInfoAssembler\` is Spring's contract for building metadata for MBeans exported from beans. An implementation can:

- Select which methods are getters/setters of managed attributes.
- Select which methods are managed operations.
- Attach descriptions and descriptor metadata.
- Define notification metadata.
- Create \`ModelMBeanInfo\` for Spring JMX infrastructure.

\`MetadataMBeanInfoAssembler\` is an implementation that reads data from \`JmxAttributeSource\`. It differs from assemblers based on conventions or explicit method lists because it relies on the supplied source metadata.

### Common assembler strategies

| Assembler | How the management interface is selected |
|---|---|
| \`MetadataMBeanInfoAssembler\` | Reads metadata from \`JmxAttributeSource\`, typically from annotations |
| \`MethodNameBasedMBeanInfoAssembler\` | Selects methods by a list of names/configuration |
| \`MethodExclusionMBeanInfoAssembler\` | Excludes methods by configuration |
| \`InterfaceBasedMBeanInfoAssembler\` | Selects methods belonging to specified interfaces |
| \`SimpleReflectiveMBeanInfoAssembler\` | Based on reflection per the assembler's policy |

Not every type of JMX MBean needs a Spring assembler. Standard MBeans and MXBeans already have their own management interface mechanisms according to the JMX specification. In particular, when Spring exports a bean that is already a compliant MBean, the adaptation path can differ from a POJO converted into a Model MBean by an assembler.

## 4. Metadata source: JmxAttributeSource

\`org.springframework.jmx.export.metadata.JmxAttributeSource\` is an abstraction that keeps the assembler decoupled from where metadata comes from. It provides metadata objects corresponding to:

- Class/resource.
- Attribute.
- Operation.
- Operation parameters.
- Notification declarations.

\`AnnotationJmxAttributeSource\` reads Spring JMX annotations and converts them into those metadata objects.

Example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor {

    private volatile int size;

    @ManagedAttribute(description = "Number of entries")
    public int getSize() {
        return size;
    }

    @ManagedOperation(description = "Clear cache statistics")
    public void resetStatistics() {
        size = 0;
    }
}
\`\`\`

The metadata source provides:

\`\`\`text
Class:
  ManagedResource
    objectName = com.example.monitoring:type=Cache,name=Products
    description = Product cache management

Method getSize:
  ManagedAttribute
    description = Number of entries

Method resetStatistics:
  ManagedOperation
    description = Clear cache statistics
\`\`\`

The assembler turns that metadata into a JMX interface, in which \`Size\` is an attribute and \`resetStatistics\` is an operation.

### An annotation does not automatically create an MBean

Having \`@ManagedResource\` on a class does not by itself make the bean appear in \`MBeanServer\`. An \`MBeanExporter\` (or an annotation export mechanism creating an exporter) must be properly configured and that bean must be exported.

Similarly, a bean registered through an exporter whose assembler does not read annotation metadata may produce a different management interface than expected.

## 5. Annotation groups and the role of each type

| Annotation | Location | Primary metadata |
|---|---|---|
| \`@ManagedResource\` | Class/type | MBean description, \`objectName\`, descriptor metadata |
| \`@ManagedAttribute\` | Getter or setter | Attribute description, units/limits metadata, property exposure |
| \`@ManagedOperation\` | Method | Operation description and management metadata |
| \`@ManagedOperationParameter\` | Declares operation parameter metadata (usually inside \`@ManagedOperationParameters\`) | Parameter name and description |
| \`@ManagedNotification\` | Class/type, repeatable | Notification types and description |
| \`@ManagedOperationParameters\` | Method | Container for parameter metadata when needed |

Combined example:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedNotification;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.monitoring:type=Worker,name=Import",
    description = "Import worker monitor"
)
@ManagedNotification(
    name = "com.example.worker.finished",
    notificationTypes = {"com.example.worker.finished"},
    description = "Worker finished"
)
public class ImportWorkerMonitor {

    private volatile String status = "IDLE";

    @ManagedAttribute(description = "Current worker status")
    public String getStatus() {
        return status;
    }

    @ManagedOperation(description = "Change worker status")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "newStatus",
            description = "New status value"
        )
    })
    public void changeStatus(String newStatus) {
        status = newStatus;
    }
}
\`\`\`

In this example:

- The class has an MBean name and description.
- The getter creates the managed attribute \`Status\`.
- The method creates the operation \`changeStatus\`, with parameter metadata.
- The notification annotation **describes** the type of notification that may be published. It does not emit events by itself.
- Any state-mutating operation still needs validation and authorization design.

A management interface should expose only necessary actions, especially if the MBean may be accessed remotely.

## 6. Manually configuring the assembler and annotation source

Example in a plain Spring Framework application:

\`\`\`java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {

        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {

        MetadataNamingStrategy strategy =
            new MetadataNamingStrategy();
        strategy.setAttributeSource(source);
        return strategy;
    }

    @Bean
    public MBeanExporter mBeanExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy namingStrategy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(namingStrategy);
        exporter.setAutodetectMode(
            MBeanExporter.AUTODETECT_ASSEMBLER
        );
        return exporter;
    }
}
\`\`\`

Here:

1. One \`AnnotationJmxAttributeSource\` is shared.
2. The assembler reads metadata via the source.
3. The naming strategy also uses the source to resolve \`ObjectName\`.
4. \`MBeanExporter\` uses both and selects eligible beans to export.

This configuration illustrates how the components fit together. In an application using \`@EnableMBeanExport\` or Spring Boot auto-configuration, you should not declare an additional exporter with duplicate functionality without a clear reason.

### Concise configuration

Spring Framework supports:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
\`\`\`

This approach uses the annotation-driven JMX export mechanism provided by Spring. Spring sets up the required components instead of every project repeating all the boilerplate.

Distinguish the two configuration styles: the manual example above and \`@EnableMBeanExport\` are alternatives; combining both at the same time can lead to multiple exporters and ObjectName conflicts.

## 7. How does the assembler turn getters/setters into JMX attributes?

A managed attribute typically corresponds to a JavaBean property.

\`\`\`java
private volatile int maxWorkers = 4;

@ManagedAttribute(description = "Maximum concurrent workers")
public int getMaxWorkers() {
    return maxWorkers;
}

@ManagedAttribute(description = "Maximum concurrent workers")
public void setMaxWorkers(int value) {
    if (value < 1 || value > 128) {
        throw new IllegalArgumentException(
            "maxWorkers must be between 1 and 128"
        );
    }
    maxWorkers = value;
}
\`\`\`

When the assembler recognizes both getter and setter, the JMX attribute can have metadata:

\`\`\`text
Name: MaxWorkers
Type: int
Readable: true
Writable: true
Description: Maximum concurrent workers
\`\`\`

If only the getter is exposed, the attribute is typically read-only; if the setter is exposed, the writable flag can be enabled. Each side can carry its own annotation metadata, so keep descriptions consistent and avoid conflicting configuration.

**Note:** \`@ManagedAttribute\` does not automatically enforce the \`1..128\` business limit. The setter must validate. JMX clients can send invalid values or invoke concurrently, so management code must protect invariants.

### Getter naming conventions

Getters such as \`getStatus()\` and \`isReady()\` follow JavaBeans conventions and can become attributes \`Status\` and \`Ready\`. However, do not guess names by manually slicing strings; when verification is needed, read \`MBeanInfo.getAttributes()\`.

## 8. Assembler turning methods into JMX operations

A method annotated with \`@ManagedOperation\` can appear in \`MBeanOperationInfo\`:

\`\`\`java
@ManagedOperation(description = "Reload non-sensitive configuration")
public void reloadConfiguration() {
    settings.reload();
}
\`\`\`

When an operation has parameters, metadata can supply names and descriptions for JMX clients to display clearly:

\`\`\`java
@ManagedOperation(description = "Set job processing mode")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "mode",
        description = "SAFE or FAST"
    )
})
public void setProcessingMode(String mode) {
    if (!"SAFE".equals(mode) && !"FAST".equals(mode)) {
        throw new IllegalArgumentException("Unsupported mode");
    }
    this.processingMode = mode;
}
\`\`\`

\`MBeanOperationInfo\` can include name, signature, return type, and description. You should still inspect the actual JMX metadata to see what clients receive.

**Distinction:** A method annotated with \`@ManagedOperation\` does not automatically become a JavaBean setter or JMX attribute. Operations and attributes are two different forms of management interface.

## 9. Assembler and class-level metadata

\`@ManagedResource\` provides resource-level metadata:

\`\`\`java
@ManagedResource(
    objectName = "com.example.monitoring:type=Cache,name=Products",
    description = "Product cache management"
)
public class ProductCacheMonitor { }
\`\`\`

\`description\` can appear in \`MBeanInfo.getDescription()\`. Other properties such as \`currencyTimeLimit\`, \`log\`, \`logFile\`, \`persistPolicy\`, \`persistPeriod\`, \`persistName\`, and \`persistLocation\` relate to the Model MBean descriptor, with runtime effects depending on the implementation.

Do not infer that:

- \`currencyTimeLimit\` is an HTTP request timeout.
- \`log=true\` automatically enables SLF4J application logging.
- \`persistPolicy\` automatically creates database persistence.
- \`description\` defines JMX access permissions.

They are management metadata; they do not replace the corresponding runtime mechanisms.

### Pluggable metadata source

The assembler uses the \`JmxAttributeSource\` abstraction. In annotation-based projects, the source is typically \`AnnotationJmxAttributeSource\`. This decoupled design allows the assembly mechanism to avoid hardcoding all annotation-reading logic.

However, in a specific application, choose **one metadata source with a clear contract**. Do not create separate annotation sources with different rules for naming and the assembler if that could cause ObjectName and interface mismatches.

## 10. Autodetect and the assembler's role

In \`MBeanExporter\`, autodetect can help select beans for export:

\`\`\`java
exporter.setAutodetectMode(
    MBeanExporter.AUTODETECT_ASSEMBLER
);
\`\`\`

This mode relies on the assembler to identify eligible beans. With \`MetadataMBeanInfoAssembler\` and \`AnnotationJmxAttributeSource\`, beans carrying properly configured management metadata are candidates.

Do not confuse:

- **Autodetect beans:** decides which beans are selected.
- **Assemble MBeanInfo:** decides what information is published.
- **Naming strategy:** assigns the JMX name.
- **Register:** performed by the exporter against \`MBeanServer\`.

If you use \`setBeans\` explicitly, the set of exported beans can be bounded more clearly. If autodetect is unnecessary, disabling autodetect can be a good choice to avoid exposing beans unintentionally.

## 11. Beans that are already MBeans vs. plain Java beans

Suppose:

\`\`\`java
public interface QueueMonitorMBean {
    int getPendingCount();
}

public class QueueMonitor implements QueueMonitorMBean {
    public int getPendingCount() {
        return 7;
    }
}
\`\`\`

This is a Standard MBean by convention if registered via JMX. In that case, the \`QueueMonitorMBean\` interface already defines the management interface.

For a POJO that does not implement a Standard MBean interface but carries Spring JMX annotations, Spring can use a Model MBean and the assembler to build the management interface.

Both paths can be supported by \`MBeanExporter\`, but you cannot conclude that every MBean has its interface determined by the assembler in the same way.

| Model | Management interface source |
|---|---|
| Standard MBean | Java interface \`XxxMBean\` |
| MXBean | Java MXBean interface and OpenType mapping rules |
| Spring POJO + annotations | Spring metadata source + assembler |
| Dynamic MBean | Implements \`DynamicMBean\` and returns \`MBeanInfo\` |

Which approach to choose depends on your goal: managing beans with Spring annotations or a standard JMX management interface independent of Spring.

## 12. Proxies, AOP, and target objects

In real applications, a Spring bean may be a proxy created by \`@Transactional\`, \`@Async\`, or Spring AOP. Metadata annotations may reside on the implementation class, while the runtime object being exported is a proxy.

Risks:

- The annotation source fails to locate metadata correctly because the proxy type differs from the target class.
- Exposed methods do not appear on the proxy interface.
- The naming strategy sees a different type than expected.
- Attributes or operations are missing or cannot be invoked.

Spring JMX supports handling these proxy situations in many configurations, but you should not assume all proxy types and annotation layouts behave identically.

How to handle it:
1. Verify the bean's runtime type and target class.
2. Place annotations in a location compatible with the application's introspection mechanism.
3. Inspect \`MBeanInfo\` after export.
4. Test \`getAttribute()\` or \`invoke()\` on the actual MBean.
5. If complex, create a dedicated JMX facade/monitor bean so the management contract stays stable.

## 13. How to verify metadata on MBeanServer

To know the management interface actually published, use \`MBeanServer\`.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.monitoring:type=Cache,name=Products"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("Description: " + info.getDescription());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute: %s, type=%s, read=%s, write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.printf(
        "Operation: %s, description=%s%n",
        operation.getName(),
        operation.getDescription()
    );
}
\`\`\`

The snippet above assumes the platform MBeanServer in the same JVM is used. If the exporter is wired to a different \`MBeanServer\` or the client is in another JVM, you must access the right server via the appropriate API/connection.

### Verifying notification metadata

\`\`\`java
for (var notification : info.getNotifications()) {
    System.out.println(notification.getName());
    System.out.println(
        java.util.Arrays.toString(notification.getNotifTypes())
    );
}
\`\`\`

The presence of notification metadata does not prove the MBean actually emits notifications. Emitting code must be configured via the corresponding \`NotificationPublisher\` or \`NotificationBroadcaster\`.

### Verification by risk type

| Symptom | Check point |
|---|---|
| MBean not visible | Exporter, autodetect, ObjectName, target MBeanServer |
| MBean exists but wrong description | \`AnnotationJmxAttributeSource\` and assembler |
| Missing attribute | Getter/setter conventions, annotation, assembler |
| Missing operation | \`@ManagedOperation\`, method visibility, proxy, assembler |
| Wrong MBean name | Naming strategy and \`@ManagedResource.objectName\` |
| Notification metadata present but not emitted | Publisher/broadcaster and sending logic |
| Duplicate export | Multiple exporters or duplicate ObjectName |
| Remote client cannot invoke | Connection, security, type/serialization |

## 14. The assembler does not replace security or runtime behavior

An important limitation of metadata-based exposure is that a method appearing in \`MBeanInfo\` does not mean it is **safe for every caller to invoke**.

Example:

\`\`\`java
@ManagedOperation(description = "Restart worker")
public void restartWorker() {
    workerService.restart();
}
\`\`\`

This operation has real side effects. You need to:
- Ensure only authorized callers can invoke it.
- Define behavior when multiple callers invoke concurrently.
- Have proper validation and logging/auditing.
- Avoid exposing secrets in params, return values, and exceptions.
- Restrict remote JMX connections, never exposing them publicly without protection.

\`@ManagedOperation(description="Admin only")\` does not enforce authorization. The assembler only supplies metadata for the management interface.

## 15. Designing a stable management interface

When using \`MetadataMBeanInfoAssembler\`, treat annotations as a management API contract:

- Name ObjectNames consistently by domain/type/name.
- Choose attributes with diagnostic value, fast reads, and minimal side effects.
- Prefer data types easily consumed by JMX clients.
- Clearly describe the units and semantics of each attribute.
- Avoid exposing internal methods just because they have \`public\` access.
- Use operations for management tasks with well-defined behavior.
- Define notification types and descriptions, while building the emission mechanism separately.
- Re-verify actual metadata when upgrading Spring or changing proxies/AOP.
- When changing the management interface, consider the impact on monitoring tools and JMX clients in use.

A good JMX contract has meaningful names and data types, changes infrequently rather than arbitrarily, and avoids exposing unnecessary business objects.

## 16. Practice exercises

### Exercise A: Configuring the annotation source

1. Create \`CacheMonitor\` with \`@ManagedResource\`.
2. Annotate the getter \`getEntryCount()\` with \`@ManagedAttribute\`.
3. Annotate \`resetStats()\` with \`@ManagedOperation\`.
4. Enable Spring JMX export via \`@EnableMBeanExport\` or manual exporter configuration.
5. Retrieve \`MBeanInfo\` and verify the name, description, attributes, and operations.

### Exercise B: Changing metadata

1. Change \`@ManagedResource.description\` and \`@ManagedAttribute.description\`.
2. Restart the context.
3. Compare \`MBeanInfo\` before/after.
4. Explain why the description changes metadata without changing getter behavior.

### Exercise C: Testing missing annotations

1. Remove \`@ManagedOperation\` from a method.
2. Restart the context with the annotation assembler.
3. Check whether the operation still appears in \`MBeanInfo\`.
4. Restore the annotation and confirm again.

### Exercise D: Proxies

1. Create a Spring bean with an AOP proxy.
2. Place JMX metadata on the implementation.
3. Export the bean and inspect \`MBeanInfo\`.
4. If annotations are not recognized or methods cannot be invoked, adjust the proxy/interface or use a dedicated JMX facade.

## 17. Self-check questions

**Question 1.** Does \`MetadataMBeanInfoAssembler\` generate the \`ObjectName\` for an MBean?  
**Answer:** Not directly. The assembler builds management metadata/interface; the naming strategy determines the ObjectName.

**Question 2.** What is the role of \`AnnotationJmxAttributeSource\`?  
**Answer:** It reads Spring JMX annotations and supplies metadata under the \`JmxAttributeSource\` contract to the assembler/naming strategy.

**Question 3.** Is placing \`@ManagedAttribute\` on a getter alone enough for JConsole to see the attribute?  
**Answer:** Not yet. The bean must be exported via JMX with an appropriate assembler/source and registered on the MBeanServer.

**Question 4.** Does \`@ManagedNotification\` emit events by itself?  
**Answer:** No. It declares notification metadata; publisher/broadcaster logic is what sends events.

**Question 5.** Is a Standard MBean required to use MetadataMBeanInfoAssembler?  
**Answer:** No. A Standard MBean has its own management interface by JMX convention.

**Question 6.** How do you know whether \`resetStats()\` is actually exposed?  
**Answer:** Read \`MBeanInfo.getOperations()\` from the right MBeanServer/ObjectName and, when needed, test invoking it in a controlled environment.

**Question 7.** Is \`description\` an authorization rule?  
**Answer:** No. It is descriptive metadata and does not enforce permissions.

## 18. Key takeaways

- \`MetadataMBeanInfoAssembler\` turns bean metadata into \`ModelMBeanInfo\` and the management interface presented by JMX.
- \`AnnotationJmxAttributeSource\` is the common metadata source when using Spring JMX annotations.
- \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\`, \`@ManagedOperationParameter\`, and \`@ManagedNotification\` describe different levels of the management API.
- \`MBeanExporter\` performs export/registration; \`MetadataNamingStrategy\` determines ObjectName; the assembler determines the interface.
- Autodetect can rely on the assembler to select beans with metadata.
- Standard MBean/MXBean has its own management interface contract, not synonymous with annotation-based Model MBeans.
- Inspect the real \`MBeanInfo\` and JMX call path rather than relying solely on annotations on the class.
- Metadata helps manage the contract, but does not replace validation, security, persistence, or notification-sending mechanisms.

### References

- Spring Framework Reference — JMX Exporting: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Javadoc — \`MetadataMBeanInfoAssembler\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework Javadoc — \`AnnotationJmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html
- Spring Framework Javadoc — \`JmxAttributeSource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/metadata/JmxAttributeSource.html
- Spring Framework Javadoc — \`MBeanExporter\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 API — \`ModelMBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/modelmbean/ModelMBeanInfo.html

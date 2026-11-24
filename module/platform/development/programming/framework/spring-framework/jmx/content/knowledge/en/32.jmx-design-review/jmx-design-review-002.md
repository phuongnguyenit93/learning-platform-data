# Choosing Standard MBean, MXBean, Annotations, or an Assembler in Spring Framework JMX

## 1. Learning Objectives

This lesson helps you make architectural decisions when exposing state and management operations of a Spring Framework application via Java Management Extensions (JMX). After studying this lesson, you will be able to:

- Distinguish **Standard MBean**, **MXBean**, **Spring annotation-driven JMX**, and **MBeanInfoAssembler**.
- Explain why "annotations" and "assembler" are not two standalone MBean types on the same tier as Standard MBean/MXBean.
- Evaluate options based on clients, data types, management API stability, exposure scope, security, AOP proxies, and operational cost.
- Understand the boundaries between \`MBeanExporter\`, \`MBeanServer\`, \`ObjectName\`, metadata assemblers, naming strategies, and JMX connectors.
- Choose a clean configuration for plain Spring Framework and Spring Boot without creating duplicate exporters.
- Build \`MBeanInfo\` and runtime invocation tests to verify the chosen approach.

## 2. First: These Are Not Four Mutually Exclusive Mechanisms

The question "Choose Standard MBean, MXBean, annotation, or assembler?" can easily cause confusion because the four terms live on **two different layers**:

| Term | Layer | Function |
|---|---|---|
| Standard MBean | JMX management contract | Defines attributes/operations via an interface by convention |
| MXBean | JMX management contract | Defines an interface and uses mapping rules from Java types to Open MBean types |
| Spring JMX annotations | Declarative metadata | Uses \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` to describe the management API |
| \`MBeanInfoAssembler\` | Metadata generation mechanism in Spring | Builds \`MBeanInfo\` so the Spring exporter can publish a bean via JMX |

Therefore, **annotation-driven export typically uses an assembler**. You can choose a plain Standard MBean, a plain MXBean, or publish a Spring bean using an annotation metadata assembler; you can also create a custom assembler for your own conventions. Do not treat an "assembler" as a JMX data type on par with MXBean.

Diagram:

~~~text
                        Spring bean / Java object
                                  |
                   +--------------+---------------+
                   |              |               |
                   v              v               v
            Standard MBean      MXBean      Spring metadata
             interface          interface   @ManagedResource
                   |              |               |
                   |              |               v
                   |              |         MBeanInfoAssembler
                   |              |               |
                   +--------------+---------------+
                                  |
                                  v
                             MBeanExporter
                                  |
                                  v
                              MBeanServer
                                  |
                                  v
                          ObjectName / MBeanInfo
                                  |
                                  v
                           JMX client / tools
~~~

This diagram is conceptual: Java code can register a Standard MBean/MXBean directly into an \`MBeanServer\` without Spring \`MBeanExporter\`. With a Spring exporter, the framework may use different exposure mechanisms depending on the bean and configuration. Not every path in the diagram is forced through an identical assembler.

## 3. Questions to Answer Before Choosing

Before writing an interface or annotation, determine:

1. **Who is the client?** JConsole/JMC, a Java client proxy, a JMX exporter, an APM agent, or a script?
2. **What data types are needed?** Only scalars \`int\`, \`long\`, \`boolean\`, \`String\`, or structured DTOs/collections/snapshots?
3. **Is remote JMX used?** If so, classloading, serialization, and security become more critical.
4. **Is an explicit Java management interface needed?** Will this API be shared across multiple Java modules/programs?
5. **Do you want to attach metadata to an existing Spring bean?** Or separate a management adapter from the business service?
6. **Does the bean have a Spring AOP proxy?** JDK dynamic proxies or CGLIB can affect interface visibility/annotation discovery.
7. **Are detailed attribute and operation descriptions needed?** For example, descriptions, units, and extended metadata.
8. **Do you need to control which beans are autodetected?** Or do you want an explicit allowlist?
9. **How many versions must the management contract survive?** Do dashboards/scripts depend on ObjectNames and types?
10. **What is the risk of write operations?** Who is allowed to pause workers, clear caches, or change configuration?

Answering these questions usually eliminates unsuitable options immediately without randomly trying multiple exporter styles.

## 4. Standard MBean: Clear Java Contract, Simple Convention

A Standard MBean has a management interface following a naming convention.

Example:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
    boolean isPaused();
    void pause();
    void resume();
}
~~~

Implementation:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueMonitor implements QueueMonitorMBean {
    private final AtomicInteger pending = new AtomicInteger(12);
    private volatile boolean paused;

    @Override
    public int getPendingCount() {
        return pending.get();
    }

    @Override
    public boolean isPaused() {
        return paused;
    }

    @Override
    public void pause() {
        paused = true;
    }

    @Override
    public void resume() {
        paused = false;
    }
}
~~~

Conventions:

- \`getPendingCount()\` creates the \`PendingCount\` attribute.
- \`isPaused()\` creates the boolean \`Paused\` attribute.
- \`pause()\` and \`resume()\` are JMX operations.

Direct registration:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.shop.jobs:type=QueueMonitor,name=primary");

server.registerMBean(new QueueMonitor(), name);
~~~

In a demo, clean up when finished:

~~~java
server.unregisterMBean(name);
~~~

### Strengths

- The management contract is expressed by a clear Java interface.
- Easy to read, organize, and review.
- Requires no Spring annotations on the implementation.
- Fits JMX clients that have a compatible management interface.
- Good for small MBeans with minimal specialized metadata.
- Can use \`JMX.newMBeanProxy()\` to invoke through the interface.

### Limitations

- Must comply with JMX naming/compliance rules.
- The interface can become tightly coupled to an implementation if not designed separately.
- Custom DTO returns in a Standard MBean can introduce classpath/classloader dependencies over remote JMX.
- Having an interface alone does not manage authorization, TLS, audit, or registration lifecycle.
- Rich metadata descriptions may require additional mechanisms.

**When to choose:** A standalone MBean, small management API, simple data types, needing a clear Java interface without depending on Spring-specific annotations.

## 5. StandardMBean Wrapper When Implementation/Interface Does Not Follow the Convention

Sometimes you have an interface not named \`QueueMonitorMBean\` per convention, or you want to avoid forcing the implementation to follow a mandatory name. Java provides \`StandardMBean\`.

Example:

~~~java
public interface QueueManagementApi {
    int getPendingCount();
}
~~~

~~~java
public class QueueManagementAdapter implements QueueManagementApi {
    @Override
    public int getPendingCount() {
        return 12;
    }
}
~~~

You can wrap it:

~~~java
import javax.management.StandardMBean;

QueueManagementApi implementation = new QueueManagementAdapter();

StandardMBean mbean = new StandardMBean(
        implementation,
        QueueManagementApi.class);

server.registerMBean(mbean, name);
~~~

This lets you explicitly choose the management interface without relying strictly on implementation naming. If the application uses Spring, you still need a clear registration owner and can delegate registration to a Spring exporter instead of registering manually.

Do not treat the \`StandardMBean\` wrapper as an automatic versioning feature. When the interface changes, client compatibility still needs to be verified.

## 6. MXBean: Prioritizing Interoperability and OpenType Mapping

An MXBean also uses a management interface, but applies type-mapping rules for smoother interoperability over JMX, especially with clients that lack custom application classes.

An example:

~~~java
import javax.management.MXBean;

@MXBean
public interface QueueStatsMXBean {
    long getPendingCount();
    String getState();
}
~~~

Implementation:

~~~java
public class QueueStats implements QueueStatsMXBean {

    @Override
    public long getPendingCount() {
        return 12L;
    }

    @Override
    public String getState() {
        return "RUNNING";
    }
}
~~~

MXBeans are especially useful when the management API needs data types that can be converted into Open MBean types such as:

- Primitives and boxed primitives per mapping rules.
- \`String\`.
- Certain arrays and enums.
- Structures representable as \`CompositeData\` or \`TabularData\` per MXBean mapping.
- Other Java types within the scope supported by the JDK.

**Important:** Not every custom class, Java record, or generic collection automatically maps to a valid OpenType across all Java versions. You must check MXBean mapping rules for the specific type and test registration/runtime access.

Clients can use:

~~~java
QueueStatsMXBean proxy = javax.management.JMX.newMXBeanProxy(
        server,
        name,
        QueueStatsMXBean.class);
~~~

### Strengths

- Well suited for management APIs requiring interoperability across JMX.
- Open-type representation reduces client dependence on Java application DTO classes.
- Good for snapshots with a well-defined schema and valid mapping.
- A Java MXBean proxy can handle the corresponding type conversions.

### Limitations

- Type-mapping rules can fail when a class is incompatible.
- Composite data schemas are also contracts that require versioning.
- Depending on types, mapping and unmarshalling can incur overhead.
- Does not exempt remote JMX from security/authentication/authorization.
- Does not solve the problem of a getter performing SQL or heavy I/O.

**When to choose:** Need portable complex types, diverse Java/JMX clients, or want to reduce remote client dependence on application DTOs.

## 7. Spring Annotation-Driven JMX: Metadata Near the Management Bean

Spring Framework provides annotations such as:

- \`@ManagedResource\`.
- \`@ManagedAttribute\`.
- \`@ManagedOperation\`.
- \`@ManagedOperationParameter\`.
- \`@ManagedMetric\`.
- \`@ManagedNotification\`.

Example:

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.jobs:type=WorkerControl,name=primary",
    description = "Worker pool management")
public class WorkerControlManagement {

    private final WorkerPoolMetrics metrics;

    public WorkerControlManagement(WorkerPoolMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Current active workers")
    public int getActiveWorkers() {
        return metrics.activeWorkers();
    }

    @ManagedOperation(description = "Reset diagnostic counters")
    public void resetDiagnosticCounters() {
        metrics.resetDiagnosticCounters();
    }
}
~~~

Here:

1. \`@Component\` registers the class in the Spring ApplicationContext.
2. \`@ManagedResource\` describes the resource and ObjectName.
3. \`@ManagedAttribute\` marks the getter to become a JMX attribute.
4. \`@ManagedOperation\` marks the exposed operation.
5. An appropriate exporter and assembler actually perform the registration.

### Strengths

- Convenient in a Spring application.
- Metadata is declared right next to the management adapter code.
- Allows declaring descriptions and other management attributes.
- Easy to combine with dependency injection.
- Allows selecting which methods are published instead of the entire public API.
- Integrates with \`AnnotationMBeanExporter\` and metadata assemblers.

### Limitations

- Depends on the Spring JMX export pipeline.
- Adding annotations alone does not register the MBean.
- If annotations are placed directly on a business service, the management surface can become mixed with business logic.
- Proxies and annotation discovery need to be tested.
- Configuring multiple exporters can cause ObjectName collisions.
- Annotations do not create access controls or protect operations.

**When to choose:** Spring applications with small management adapters, wanting to describe the API via annotations and leverage the IoC container.

## 8. What Is an Assembler Really?

\`MBeanInfoAssembler\` in Spring is responsible for generating \`MBeanInfo\` representing attributes, operations, and management metadata. An assembler can be based on:

- Specified interfaces.
- Naming conventions.
- Source code reflection according to a policy.
- Metadata annotations from \`JmxAttributeSource\`.
- Organization-specific custom rules.

Common assemblers include:

| Assembler | Usage Idea |
|---|---|
| \`InterfaceBasedMBeanInfoAssembler\` | Selects management methods by interfaces |
| \`MethodNameBasedMBeanInfoAssembler\` | Selects methods by allowed names |
| \`MethodExclusionMBeanInfoAssembler\` | Publishes methods except excluded names |
| \`MetadataMBeanInfoAssembler\` | Uses management metadata from \`JmxAttributeSource\` |

Exact class names/APIs and configuration details should be checked against the Spring Framework version in use. Not every assembler supports autodetection; if the exporter uses \`AUTODETECT_ASSEMBLER\`, the assembler must be able to evaluate candidate beans for discovery via \`AutodetectCapableMBeanInfoAssembler\`.

### When to use an assembler?

An assembler fits when:
- You want to define a centralized whitelist of attributes/operations.
- Multiple beans follow a common convention.
- You do not want to annotate every implementation.
- You need to control an interface/naming-based management contract.
- You want to use \`@Managed...\` metadata in the Spring export pipeline.

**An assembler is not a public JMX data type.** It is part of Spring's metadata-generation layer and can be combined with other approaches depending on the specific configuration.

## 9. Configuring an Annotation Assembler in Spring Framework

Here is an illustrative configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class ApplicationJmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
                new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    MetadataNamingStrategy jmxNamingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter jmxExporter(
            MetadataMBeanInfoAssembler assembler,
            MetadataNamingStrategy naming) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setAssembler(assembler);
        exporter.setNamingStrategy(naming);
        exporter.setAutodetectModeName("AUTODETECT_ASSEMBLER");
        return exporter;
    }
}
~~~

The configuration above clarifies each component's role. \`AnnotationJmxAttributeSource\` is the metadata source; the assembler builds \`MBeanInfo\` and can participate in selecting beans; the naming strategy constructs the ObjectName; the exporter registers beans with the server.

This is **one configuration option**. If the application already uses \`@EnableMBeanExport\`, \`AnnotationMBeanExporter\`, or Spring Boot auto-configuration that creates a suitable exporter, do not add another exporter scanning the same resources. There must be a single clear owner for each ObjectName.

## 10. Annotations vs. Interface-Based Assembler

Suppose a business service interface:

~~~java
public interface PaymentStatistics {
    long getSuccessfulPayments();
    long getFailedPayments();
    void resetStatistics();
}
~~~

You can create an annotated management adapter or use an assembler that selects methods by interface. Differences:

**Annotation-driven**
- Metadata lives on methods/class.
- \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` make intent clear.
- Management API changes typically follow class annotations.
- Can keep business interfaces independent of JMX when using an adapter.

**Interface-based assembler**
- The method set is chosen based on a configured interface.
- Easy to separate implementation from declaration of the management surface.
- Can reuse existing interfaces without adding annotations.
- Still requires naming/exporter/registration configuration.
- Must verify which getters are interpreted as attributes and which methods as operations.

If a business interface contains dangerous methods like \`refundPayment\` or \`deleteAccount\`, do not pick that entire interface as the management interface just because it already exists. Define an interface containing only the required management methods.

## 11. Method-Name-Based Assembler: Flexible but Brittle

Suppose you want to expose:

~~~text
getActiveWorkers
getQueueDepth
resetStatistics
~~~

A method-name-based assembler can allowlist these names. However, the design depends on exact method names:

- Renaming a Java method can break/remove the JMX attribute.
- Overloaded methods require careful attention to signatures.
- If configured by bean name and multiple beans share a convention, changing bean naming can break the policy.
- Metadata descriptions can be less informative than annotations.
- Clients still depend on the final ObjectName and MBeanInfo.

This approach fits legacy code where source cannot be edited to add annotations or interfaces. For new systems, an explicit management adapter/interface is usually easier to audit.

## 12. Decision Matrix for Choosing an Approach

| Criterion | Standard MBean | MXBean | Annotation + metadata assembler | Custom/interface assembler |
|---|---|---|---|---|
| Explicit Java management interface | Required per convention/wrapper | Yes | Not required | Policy-dependent |
| Ease of use with Spring IoC | Yes, via exporter | Yes, via exporter | Very convenient | Yes |
| Metadata on methods | Per interface/convention | Per interface/mapping | Uses annotations | Per policy |
| Scalar types | Good | Good | Good | Good |
| Portable complex types | Requires DTO/classpath care | Strong if open-type mapping is valid | Type/assembler-dependent | Metadata/type-dependent |
| Low Spring coupling | Good | Good | Lower | Lower |
| Reuse legacy beans | Possible | Possible | Needs annotations or adapter | Often flexible |
| Method selection control | Interface | Interface | \`@Managed\` annotations | Policy/interface/method names |
| API stability | Determined by design/tests | Determined by design/tests | Determined by design/tests | Determined by policy/tests |
| Risk of exposing methods | If interface is designed too broadly | If interface is broad | If annotated too broadly | If policy is too broad |
| Diverse client tooling | Good with suitable types | Good with open types | Depends on metadata and types | Depends on metadata and types |
| Config complexity | Low to medium | Low to medium | Medium | Medium to high |

No single column has an absolute default "security level" or "performance". Major issues usually stem from the specific management API, getter cost, network exposure, naming, and security—not merely from choosing an interface or annotation.

## 13. Quick Selection Rules

**Choose Standard MBean** if:
- Small Java contract, simple types.
- Clear management interface exists.
- JMX usage is relatively independent of Spring.
- MXBean open-type mapping is not needed.

**Choose MXBean** if:
- You want a JMX interface that interoperates easily with diverse clients.
- You need structured data that MXBean can map to OpenTypes.
- You want to minimize custom DTO dependencies on remote clients.
- You are prepared to test mapping/schema.

**Choose Spring annotations** if:
- The application uses Spring IoC.
- You want to write a short, clear management adapter.
- You need attribute/operation metadata described via annotations.
- A suitable annotation-aware exporter is already configured.

**Choose custom/interface assembler** if:
- Legacy classes cannot be annotated.
- A consistent policy is needed across a large set of beans.
- You want to centralize whitelisting/naming conventions.
- The team understands the maintenance risks of metadata rules.

A project may use Standard MBeans for platform integration, MXBeans for structured data, and annotation-driven adapters for application-specific management, provided each ObjectName is registered once and contracts are cleanly governed.

## 14. Scenario Example 1 — Only QueueDepth Needed

Requirements:
- JConsole reads queue depth.
- Java client uses an interface.
- No complex DTOs needed.
- Very small operation surface.

Typically suitable approach: **Standard MBean** with \`QueueMonitorMBean\` having \`int getQueueDepth()\`.

In a pure Spring application, an annotation adapter can still be used to reduce boilerplate; choosing Standard MBean vs. annotations depends on codebase standards and client interface needs. There is no need to build a custom assembler just for one small getter.

A minimal contract avoids coupling to the entire business service.

## 15. Scenario Example 2 — Multi-Field Snapshot

Requirements:
- Clients read \`queued\`, \`processing\`, \`completed\`, \`failed\`, and timestamp from the same generation.
- External Java/JMX clients exist outside the application.
- Want to limit dependencies on custom DTO classes.

Approach: **MXBean** with valid type mapping, or a Standard MBean explicitly returning \`CompositeData\`.

Do not stitch separate getters together and call it an atomic snapshot. The MBean implementation must perform coherent capture and publication. \`MXBean\` does not automatically turn multiple state sources into an atomic snapshot.

If complex data cannot be mapped, use explicit Open MBean types or simplify the schema. Never return JPA entities directly over JMX.

## 16. Scenario Example 3 — Spring Service with @Transactional

Requirements:
- An existing service has many business methods using transactions and caching.
- Want to expose \`getPendingCount()\` and \`getLastErrorCode()\`.
- Must NOT expose \`cancelOrder()\` or \`refundPayment()\`.

Approach: **Dedicated Spring management adapter**, using \`@ManagedResource\` and \`@ManagedAttribute\`, injecting the service through the Spring proxy interface.

~~~java
@Component
@ManagedResource(
        objectName = "com.example.shop.orders:type=OrderMonitor,name=primary")
public class OrderMonitorManagement {

    private final OrderService orderService;

    public OrderMonitorManagement(OrderService orderService) {
        this.orderService = orderService;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return orderService.pendingCountSnapshot();
    }

    @ManagedAttribute
    public String getLastErrorCode() {
        return orderService.lastErrorCode();
    }
}
~~~

The adapter keeps the business API separate from the management API. Use a cheap snapshot to limit SQL polling. If the adapter is AOP-proxied due to broad pointcuts, metadata discovery and invocation must be verified on the specific Spring version.

## 17. Scenario Example 4 — Legacy Bean Whose Source Cannot Be Modified

Requirements:
- An internal library provides a Java class, and annotations cannot be added.
- Only \`getActiveWorkers()\` and \`getQueueDepth()\` should be exposed.
- Library APIs must remain unchanged.

Options:
1. Create a dedicated wrapper/management adapter; or
2. Use an interface-based or method-name-based assembler to pick specific methods.

If there is only one bean, an adapter is usually easier to understand. If many beans share the same convention and maintainers control the rules, an assembler can reduce boilerplate.

Do not use an overly broad method exclusion policy and assume all future public methods will be safe. A newly added method in the library could accidentally appear in JMX if the policy allows methods by default.

## 18. Scenario Example 5 — Remote Client Without DTO Classes

Requirements:
- Remote JMX client runs outside the application classpath.
- Returned data needs multiple fields with a clear schema.
- Do not want client deployments to depend on custom entity/DTO jars.

Typically suitable approach: **MXBean/OpenType** or explicitly defined \`CompositeData\`/\`TabularData\`.

Keep in mind:
- Java serialization/classloading can still affect APIs that do not adhere to OpenTypes.
- Remote JMX/RMI requires proper authentication, authorization, and encryption.
- Not every generic class/record maps automatically.
- Metadata/schema is a versioned contract.

Do not disable TLS just because a client hits a class-loading error; those are two different kinds of issues.

## 19. AOP Proxies and Management Interfaces

When a Spring bean has \`@Transactional\`, security advice, or caching, Spring may use a JDK dynamic proxy or CGLIB.

A JDK proxy typically exposes interface methods, not necessarily public methods of the concrete class. If annotations exist only on the implementation class, verify whether the assembler finds target metadata properly and whether the proxy can execute the method.

Check:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("orderMonitorManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
~~~

Do not manually unwrap the target and export it directly if doing so bypasses transaction or security advice. A small management adapter reduces risk, yet still requires testing when pointcuts are broad.

With a Standard MBean interface and a JDK proxy, ensure the management interface is actually exposed by the proxy and accepted by the JMX registration path. Results can vary across configurations/versions, so \`MBeanInfo\` and invocation tests are mandatory.

## 20. Lifecycle and ObjectName

Regardless of the chosen approach, JMX still requires a unique \`ObjectName\` within an \`MBeanServer\`.

Example:

~~~text
com.example.shop.orders:type=QueueMonitor,name=outbox
~~~

Design rules:
- Domain reflects the application/module.
- Key properties identify logical type and instance.
- Do not confuse Spring bean name with ObjectName.
- Do not put secrets or personal data into ObjectName.
- Keep names stable if dashboards/scripts depend on them.
- One clear registration owner per name.
- Clean up on context/application shutdown.
- Avoid duplicate exporters leading to \`InstanceAlreadyExistsException\`.

Spring \`RegistrationPolicy\` has \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\`, and \`REPLACE_EXISTING\`. These options handle conflicts, not versioning or security.

When ownership of a name is unclear, it is usually better to detect the conflict and fix the architecture than to silently replace another component's MBean.

## 21. Security: MBean Type Choice Does Not Determine Safety

Standard MBeans, MXBeans, and Spring annotation-driven management can all expose state-mutating operations. Therefore, security must be treated as a separate concern.

Example of a risky operation:

~~~java
@ManagedOperation
public void pauseConsumers() {
    service.pause();
}
~~~

Considerations:
- Does it truly need to be exposed in production?
- Does the monitoring collector need invoke permissions?
- Is remote JMX authenticated and encrypted?
- Are operator permissions separated from read-only permissions?
- Are critical actions audited/logged?
- Is there rollback/recovery if the operation causes side effects?
- Are rate limiting or appropriate guardrails in place?

Do not use annotations or interface naming as an ACL mechanism. \`MBeanInfo\` only describes the management surface; client read/write permissions are enforced by the connector/security layer and application guardrails.

## 22. Performance: Getters Can Still Be a Bottleneck

A JMX getter may be polled frequently by clients. Example:

~~~java
@ManagedAttribute
public long getPendingCount() {
    return repository.countPending();
}
~~~

If every read runs SQL, monitoring can add DB load. Likewise, MXBean mapping constructing large \`CompositeData\` or a Standard MBean returning unbounded collections carries significant overhead.

Principles:
- Getters should be lightweight and side-effect free.
- Use counters, cached snapshots, or scheduled refreshes for expensive data.
- Expose a freshness timestamp if snapshots can go stale.
- Never return full entity graphs or secrets.
- Limit payload size and serialization cost.
- Measure latency/CPU/allocations if the system has many clients.

You cannot claim Standard MBean is "fastest", MXBean is "slower", or annotations have "zero overhead" without measuring the specific implementation.

## 23. Verifying Actual Results via MBeanInfo

Whichever approach you choose, the MBeanServer is where the actual contract is inspected:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public final class MBeanContractInspector {

    public static void inspect(ObjectName name) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        if (!server.isRegistered(name)) {
            throw new IllegalStateException(
                    "MBean not registered: " + name);
        }

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println("Class: " + info.getClassName());

        for (MBeanAttributeInfo attribute : info.getAttributes()) {
            System.out.printf(
                    "%s : %s readable=%s writable=%s%n",
                    attribute.getName(),
                    attribute.getType(),
                    attribute.isReadable(),
                    attribute.isWritable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.printf(
                    "operation=%s returns=%s%n",
                    op.getName(),
                    op.getReturnType());
        }
    }
}
~~~

This snippet uses the platform MBeanServer as an example. When an exporter uses a custom server, query the exact server where registration occurred.

\`MBeanInfo\` helps verify:
- Attribute names and types.
- Read/write flags.
- Operation list.
- Operation signatures.
- Metadata visible to clients.

However, metadata does not guarantee a getter avoids DB queries or that an operation is safe; separate invocation tests and semantic reviews are needed in development.

## 24. Integration Tests for Design Choices

An integration test can spin up an isolated context/server and verify:

1. The right MBean is registered.
2. ObjectName matches the expected convention.
3. Attributes and operations match the contract.
4. No unintended business methods are exposed.
5. Return types suit JMX clients.
6. \`getAttribute\` returns a value of the expected type.
7. \`invoke\` uses the right signature and produces expected side effects in the test environment.
8. Spring AOP proxies do not break management metadata.
9. No duplicate exporter registration occurs.
10. Context shutdown unregisters the MBeans it owns.

A dedicated test MBeanServer:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test");
~~~

Pass \`testServer\` into the Spring test context's exporter. Do not create a test server while the exporter still uses the platform server and then conclude the MBean is missing.

### Pseudocode assertion

~~~java
ObjectName name = new ObjectName(
    "com.example.shop.jobs:type=WorkerControl,name=primary");

assertTrue(testServer.isRegistered(name));

MBeanInfo info = testServer.getMBeanInfo(name);

assertTrue(
    java.util.Arrays.stream(info.getAttributes())
        .anyMatch(a -> "ActiveWorkers".equals(a.getName())
                    && "int".equals(a.getType())));
~~~

This snippet needs JUnit assertions and appropriate context/test dependencies; it illustrates how to check the runtime contract, not a complete standalone class.

## 25. Versioning the Management API

A JMX contract can be relied upon long-term by scripts and monitoring rules. The following changes can be breaking:

- Changing ObjectName.
- Changing attribute name or return type.
- Changing operation signature.
- Changing units from milliseconds to seconds while keeping the old name.
- Changing \`CompositeData\` schema.
- Changing operation semantics.
- Removing a notification type currently used by listeners.

If you only add a new attribute while preserving the old contract, evolution is usually compatible. When a breaking change is needed, consider keeping v1 and publishing v2 under a different ObjectName with a migration window.

Choosing MXBean over Standard MBean does not automatically solve contract versioning. Choosing annotations does not automatically make a management API backward-compatible. You must have a deprecation policy, tests, and a consumer migration plan.

## 26. Spring Boot and Actuator Scenarios

Spring Boot may create JMX export infrastructure depending on version and configuration; Actuator can expose endpoints over JMX technology. However:

- JVM platform MBeans are a separate component.
- Spring custom \`@ManagedResource\` MBeans have their own registration path.
- Actuator JMX endpoints belong to Actuator management infrastructure.
- \`management.endpoints.jmx.exposure.include\` is not an allowlist applying to all custom MBeans.
- \`spring.jmx.enabled\` does not automatically configure a remote JMX connector.
- \`management.server.port\` relates to the management HTTP server port, not by default a remote JMX port.

Before adding a manual \`MBeanExporter\`, check existing exporters, domain/naming, Spring Boot version, and registration scope.

## 27. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| \`NotCompliantMBeanException\` | Invalid Standard/MXBean contract | Fix interface/wrapper/type mapping |
| MBean does not appear | Spring bean or exporter inactive | Check context and export mode |
| Annotations have no effect | Assembler/source not reading annotations | Configure the metadata pipeline |
| Attributes exist but operations do not | Metadata selection differs from expectation | Inspect MBeanInfo and contract |
| \`ClassCastException\` on remote client | Incompatible DTO/type mapping | Use MXBean/OpenType or matching shared DTO |
| \`InstanceAlreadyExistsException\` | Two owners with the same ObjectName | Fix naming/ownership |
| JConsole shows MBean in wrong domain | Naming strategy differs from convention | Query ObjectNames and fix naming |
| Getter increases DB load | Expensive query inside getter | Use snapshot/cache/refresh |
| AOP proxy hides methods | Incompatible interface/proxy metadata | Test AOP, extract adapter |
| MXBean mapping error | Type violates open-type rules | Change type, test mapping |
| Management operation denied | Connector authorization | Configure proper permissions, do not open remote blindly |
| Dashboard loses metric after refactor | Contract changed name/type | Versioning and migration |

## 28. Design Evaluation Exercises

### Exercise 1 — MBean with three scalar attributes

A library needs to provide \`ThreadCount\`, \`QueueDepth\`, \`Paused\`. Clients are Java/JConsole; no extended metadata is needed.

Propose a Standard MBean interface and explain why a custom assembler may be unnecessary.

### Exercise 2 — Schema-backed snapshot

An application wants to return worker state containing \`active\`, \`idle\`, \`failed\`, \`capturedAt\` to remote JMX clients. Compare MXBean open-type mapping vs. a Standard MBean returning \`CompositeData\`. State the limitations of custom DTOs.

### Exercise 3 — Spring service with AOP

A service has \`@Transactional\` and public methods \`getPending()\`, \`refundOrder()\`, \`deleteOrder()\`. Design a management adapter annotated with \`@ManagedResource\` that exposes only \`getPending()\`, avoiding dangerous operations.

### Exercise 4 — Unmodifiable legacy class

You cannot modify a library class, yet want to expose two getters. Compare a wrapper adapter with an interface/method-name assembler; state maintenance tradeoffs.

### Exercise 5 — Contract tests

Pick an approach, implement an MBean, and verify \`MBeanInfo\`, \`getAttribute\`, \`invoke\`, \`isRegistered\`, and lifecycle cleanup. Also assert that an unwanted method is not exposed.

### Exercise 6 — Multi-module strategy

An application has a queue monitor, a database pool monitor, and cache statistics. Decide whether to use one consistent method or combine Standard MBean/MXBean/annotations. Establish an ObjectName convention and clear registration owner for each MBean.

## 29. Self-Check Questions

**1. Are annotations and assemblers two MBean types alongside Standard MBean and MXBean?**  
No. Annotations are a metadata source; an assembler is a metadata-generation mechanism in the Spring export pipeline.

**2. When is an MXBean more suitable than a Standard MBean?**  
When interoperability via OpenType mapping is needed for supported data types, especially with clients outside the application classpath.

**3. Does a Standard MBean require the application to use Spring?**  
No. It can be registered directly with a Java MBeanServer.

**4. Does simply placing \`@ManagedResource\` on a class guarantee it appears in JConsole?**  
No. A Spring bean and suitable exporter/assembler, plus registration to the right server/ObjectName, are required.

**5. Can an assembler decide which beans are autodetected?**  
If the assembler implements the appropriate autodetect capability, it can participate in inclusion decisions via the corresponding interface.

**6. Should you export an entire business service interface containing destructive operations?**  
No. Create a minimal management contract/adapter and enforce access control.

**7. What if a Java record cannot be mapped in an MXBean?**  
Choose a supported type/schema or return an explicit Open MBean structure, then test it.

**8. Does any approach automatically guarantee remote JMX security?**  
No. Authentication, authorization, TLS, network isolation, and audit are additional decisions.

## 30. Key Takeaways

- Standard MBean and MXBean are JMX management interface models.
- Spring annotations are a way to declare management metadata; an assembler is the \`MBeanInfo\`-building layer, often working alongside annotations.
- Standard MBean fits simple Java interfaces, small contracts, and low Spring coupling.
- MXBean is useful when OpenType interoperability across diverse clients is needed.
- Annotation-driven adapters fit applications using Spring IoC that want declaratively clear management APIs.
- Custom/interface assemblers fit legacy code or centralized method-selection policies.
- Do not broadly export business services or rely on uncontrolled method exclusion.
- Every approach needs stable ObjectNames, a clear registration owner, and \`MBeanInfo\` tests.
- Proxies, type mapping, remote security, performance, and API versioning can matter more than how the management interface is declared.
- There is no "one right choice for every case"; decide based on client needs, contract, lifecycle, and required level of control.

## 31. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — MBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MBeanInfoAssembler.html
- Spring Framework Javadoc — MetadataMBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Java SE 21 — StandardMBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/StandardMBean.html
- Java SE 21 — MXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MXBean.html
- Java SE 21 — MBeanInfo: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html

# Bean Not Appearing in MBeanServer — Spring Framework JMX Diagnostics

## Learning Objectives

This lesson guides you through diagnosing cases where a Spring bean or an MBean is expected to appear in JMX but cannot be found in JConsole or via the MBeanServer API. After this lesson, you will be able to:

- Distinguish between a Spring bean residing in the ApplicationContext and an MBean registered with an ObjectName.
- Isolate issues in component scanning, bean lifecycle, JMX exporter, assembler, naming strategy, registration policy, AOP proxy, MBeanServer, or JMX client.
- Use isRegistered, queryNames, getMBeanInfo, and getAttribute to verify actual runtime results.
- Understand the differences among Standard MBean, MXBean, DynamicMBean, and annotation-driven Spring JMX.
- Write regression-preventing integration tests and keep remote JMX access/security at an appropriate level.

## 1. Symptoms to Clarify

Suppose a Spring application has the following class:

~~~java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=QueueMonitor,name=outbox")
public class QueueManagement {
    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
~~~

The application starts up normally, but JConsole does not display the MBean com.example.shop.orders:type=QueueMonitor,name=outbox.

From that symptom alone, you cannot conclude the issue is in the annotations. There are several possibilities:

1. The class is not instantiated as a bean by Spring.
2. The bean is created, but no exporter selects it.
3. The exporter does not understand the annotations or does not auto-detect the resource.
4. The bean does not conform to the JMX management contract being used.
5. The generated ObjectName differs from the name the user is looking for.
6. Two exporters register a duplicate ObjectName and registration fails or is skipped.
7. The exporter uses a different MBeanServer than the one the client is observing.
8. The MBean was registered but has already been unregistered when the context closed.
9. A Spring AOP proxy causes metadata or methods not to be processed as expected.
10. The JMX remote connector, access permissions, or connecting to the wrong JVM prevents the client from seeing the resource.

What you need to do is check sequentially from where the bean is created to where the client queries it.

## 2. Distinguishing Between a Spring Bean and an MBean

Spring ApplicationContext manages objects, dependencies, scopes, and lifecycle. JMX MBeanServer is a registry for management objects, queried via ObjectName.

~~~text
@Configuration / @Component / XML definition
        |
        v
Spring ApplicationContext
        |
        v
Spring bean / AOP proxy
        |
        v
MBeanExporter + assembler + naming
        |
        v
MBeanServer.registerMBean(...)
        |
        v
ObjectName in the JMX registry
        |
        v
JConsole / custom client
~~~

A Spring bean can exist without being registered via JMX. Conversely, JVM platform MBeans such as java.lang:type=Memory can be registered by the Java runtime independently of application component scanning.

A Spring bean name, such as queueManagement, is not an ObjectName. An ObjectName is a JMX identifier such as com.example.shop.orders:type=QueueMonitor,name=outbox. The two names serve two different namespaces.

## 3. First Step: Are You Looking at the Right JVM?

When multiple Java processes are running on a machine or multiple pods exist in Kubernetes, connecting to the wrong process is an easily overlooked root cause.

~~~text
orders-service JVM    -> QueueMonitor may exist
payment-service JVM   -> Does not have orders' QueueMonitor
IDE test runner JVM   -> Separate MBeanServer
~~~

Identify the PID, application name, pod/container, and the management connector actually used by the client. The same ObjectName can exist in multiple independent JVMs without duplicate registration, because the registry belongs to each MBeanServer.

If checking with JConsole, verify that it is connected to the right JVM. If checking remotely, verify the address, port, host advertised over RMI, and client identity according to the allowed configuration.

Do not disable authentication or TLS just to make a connection succeed. Permission or network issues must be fixed at the proper layer, not by weakening security.

## 4. Checking the MBeanServer Directly

If you have permission to run diagnostic code inside the JVM, start with the platform MBeanServer:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.shop.orders:type=QueueMonitor,name=outbox");

System.out.println("Registered: " + server.isRegistered(name));
~~~

A false result only means the ObjectName is not registered in the server being queried. It does not prove there is no MBean in another MBeanServer.

Spring can be configured to use a custom MBeanServer:

~~~java
@Bean
MBeanExporter exporter(MBeanServer server, QueueMonitor monitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    // Configured export mapping / assembler is required.
    return exporter;
}
~~~

The snippet above only illustrates injecting the right server; an actual exporter also needs appropriate mapping or autodetection configured. When debugging, obtain the exact MBeanServer bean used by the exporter instead of assuming the platform server is always the registration target.

## 5. Listing ObjectNames Instead of Guessing Names

An ObjectName consists of a domain and key properties. If the name produced by a naming strategy differs from what you expect, checking a fixed ObjectName may return false even though the MBean exists under another name.

~~~java
import java.util.Set;
import javax.management.ObjectName;

Set<ObjectName> names = server.queryNames(
        new ObjectName("com.example.shop.*:*"), null);

names.stream()
        .map(ObjectName::getCanonicalName)
        .sorted()
        .forEach(System.out::println);
~~~

The pattern com.example.shop.*:* matches domains with the prefix com.example.shop. and does not include the exact domain com.example.shop. If you do not yet know the domain, you can use queryNames(null, null) and then filter the results, while avoiding printing too many unrelated MBeans.

Common mistakes:
- Confusing com.example.shop with com.example.shop.orders.
- Confusing the Spring bean name with the JMX ObjectName.
- Omitting or changing a key property such as name or type.
- The name being constructed by a naming strategy rather than taken from the annotation.
- Querying the ObjectName in a different custom MBeanServer.

An ObjectName must have valid syntax. If a value contains special characters, consider ObjectName.quote or an appropriate builder. A naming error can cause MalformedObjectNameException before registration.

## 6. Is the Bean in the ApplicationContext?

Verify that the bean has been created by Spring:

~~~java
import org.springframework.context.ApplicationContext;

public final class SpringBeanInspector {
    public static void inspect(ApplicationContext context) {
        for (String name :
                context.getBeanNamesForType(QueueManagement.class)) {
            System.out.println(name);
        }
    }
}
~~~

If the list is empty, check:
- Whether the class has an appropriate @Component, @Service, or @Bean definition.
- Whether component scanning includes the package containing the bean.
- Whether @Profile or @Conditional excludes the bean under the current configuration.
- Whether the configuration class containing @Bean is imported.
- Whether the bean was instantiated with new outside Spring instead of being managed by the container.
- Which parent or child context the bean belongs to.
- Whether bean initialization failed or the bean had not yet been created at the lifecycle point of inspection.

Example of wrong scope:

~~~java
@SpringBootApplication(scanBasePackages = "com.example.shop.web")
public class ShopApplication {}
~~~

If QueueManagement is in com.example.shop.orders.management, then scanning the package com.example.shop.web does not cover it.

One subtle point: getBeanNamesForType for a concrete class can be affected when the bean is a JDK dynamic proxy. If you suspect AOP, look up by bean name or an available interface and then inspect the target class. Do not conclude a bean is absent from a concrete-type lookup alone.

## 7. Is There an Exporter or Registration Mechanism Yet?

Annotations only declare metadata. Appearing in MBeanServer requires registration.

Common paths:

| Mechanism | Meaning |
|---|---|
| MBeanExporter.setBeans | Explicit export mappings |
| AnnotationMBeanExporter | Export annotation-driven Spring resources |
| MetadataMBeanInfoAssembler | Build MBeanInfo from metadata source |
| AnnotationJmxAttributeSource | Read @ManagedResource and method annotations |
| MBeanServer.registerMBean | Manual registration |
| Spring Boot JMX integration | Depends on version/auto-configuration |
| JVM platform management | Runtime automatically registers platform MBeans |

If the application has annotations without an appropriate exporter configured, the bean will not automatically become an MBean. If you add a new exporter when another exporter already exists, there is a risk of duplicate registration.

Before fixing, determine which exporter bean is currently running, which autoconfiguration is enabled, which MBeanServer it uses, and which mode it is in.

## 8. Example of Registering a Standard MBean with Spring

Management interface:

~~~java
public interface QueueMonitorMBean {
    int getPendingCount();
}
~~~

Implementation:

~~~java
public class QueueMonitor implements QueueMonitorMBean {
    @Override
    public int getPendingCount() {
        return 12;
    }
}
~~~

If QueueMonitor is a Spring bean, you can export that instance:

~~~java
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.jmx.export.MBeanExporter;

@Bean
MBeanExporter queueExporter(QueueMonitor monitor) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setBeans(Map.of(
        "com.example.shop.orders:type=QueueMonitor,name=outbox",
        monitor));
    return exporter;
}
~~~

Do not create a second new QueueMonitor() inside the exporter if the business application uses another singleton. Two different objects will have different state, misleading operators.

A Standard MBean follows the ClassNameMBean interface convention. If the object does not satisfy the contract, you may encounter NotCompliantMBeanException. MXBean and DynamicMBean have their own rules.

## 9. Does the Exporter Actually Select the Bean?

An exporter may be configured with explicit mapping only:

~~~java
exporter.setBeans(Map.of(
    "com.example.shop.orders:type=QueueMonitor,name=outbox",
    monitor));
~~~

In that case, other beans will not automatically appear just because they have @ManagedResource, unless an appropriate autodetection mechanism is active.

Spring JMX supports the following mode concepts:

~~~text
AUTODETECT_NONE
AUTODETECT_MBEAN
AUTODETECT_ASSEMBLER
AUTODETECT_ALL
~~~

AUTODETECT_ASSEMBLER lets AutodetectCapableMBeanInfoAssembler decide which Spring beans have appropriate managed-resource metadata. MetadataMBeanInfoAssembler with AnnotationJmxAttributeSource is a common configuration.

A method annotated with @ManagedAttribute on a class missing @ManagedResource may not be selected by metadata-based resource detection. The actual condition depends on the assembler; check the configuration/version in use.

If the bean is not selected, fix the mapping or selection criteria; changing the domain will not make the exporter suddenly detect the bean.

## 10. Annotations and Assembler

An annotation-driven management bean:

~~~java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=Queue,name=outbox",
    description = "Order queue monitor")
public class QueueManagement {
    @ManagedAttribute(description = "Pending jobs")
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation
    public void resetStatistics() {
        // Reset diagnostic counters only.
    }
}
~~~

Components that need to be compatible:
- @ManagedResource: resource-level metadata.
- @ManagedAttribute: getter/setter metadata.
- @ManagedOperation: operation metadata.
- AnnotationJmxAttributeSource: recognizes annotations.
- MetadataMBeanInfoAssembler: builds JMX metadata.
- MetadataNamingStrategy: derives the ObjectName.
- MBeanExporter: performs registration.

If the bean is present but the MBean is missing, inspect the resource annotation and the exporter. If the MBean is present but attributes/operations are missing, inspect the metadata assembler, interface, proxy, and MBeanInfo.

Do not assume every export path automatically merges management interfaces and annotations. A Standard MBean interface, an MXBean contract, and Spring annotation metadata can expose different surfaces; choose one primary contract per MBean.

## 11. Example of Annotation-Aware Configuration

An illustrative configuration with Spring Framework:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.annotation.AnnotationJmxAttributeSource;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.naming.MetadataNamingStrategy;

@Configuration
public class JmxConfiguration {

    @Bean
    AnnotationJmxAttributeSource attributeSource() {
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
    MetadataNamingStrategy namingStrategy(
            AnnotationJmxAttributeSource source) {
        MetadataNamingStrategy naming = new MetadataNamingStrategy();
        naming.setAttributeSource(source);
        return naming;
    }

    @Bean
    MBeanExporter mbeanExporter(
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

This is one illustrative way to wire the metadata source, assembler, naming, and exporter. Check the Spring API/version; do not add this configuration when the application already has AnnotationMBeanExporter/auto-config providing the same functionality. Use only one registration owner per ObjectName.

## 12. Is Registration Conflicting?

An ObjectName can only be used by one MBean within the same server. Two exporters attempting to register the same name can cause InstanceAlreadyExistsException.

~~~text
Exporter A --> com.example.shop.orders:type=Queue,name=outbox
Exporter B --> com.example.shop.orders:type=Queue,name=outbox
                                            |
                                            v
                                      conflict
~~~

Spring RegistrationPolicy provides these options:

| Policy | When Name Exists | Meaning |
|---|---|---|
| FAIL_ON_EXISTING | Throws an error | Easy to detect duplicates |
| IGNORE_EXISTING | Keeps the old MBean | New bean may not be registered |
| REPLACE_EXISTING | Replaces the old MBean | May cause disruption and lose old metadata |

If IGNORE_EXISTING is active, isRegistered(name)==true does not prove the new bean is the registered object. You must compare MBeanInfo, operations, and startup logs.

Do not enable REPLACE_EXISTING to mask conflicts; it can replace a registration belonging to another component and does not atomically roll back by default on failure.

## 13. Does a Spring AOP Proxy Alter the Contract?

A bean subject to @Transactional, @Cacheable, or security advice may be a JDK dynamic proxy or a CGLIB proxy. A JDK proxy only exposes interface methods; a concrete method with JMX annotations that is not on an interface may not be invokable through the proxy.

Runtime inspection:

~~~java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean("queueManagement");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
~~~

Do not unwrap the target for direct export if doing so bypasses transaction, security, or caching advice.

A separate management adapter often helps keep the management API clear:

~~~java
@Component
@ManagedResource(
    objectName = "com.example.shop.orders:type=OrderMonitor,name=main")
public class OrderManagement {
    private final OrderService service;

    public OrderManagement(OrderService service) {
        this.service = service;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return service.pendingCount();
    }
}
~~~

The adapter calls the service through the Spring proxy interface. However, the adapter itself can also be proxied if a pointcut is broad, so you must check at runtime and inspect MBeanInfo. If a getter runs heavy SQL, JMX polling can create load; use cheap snapshots/counters when appropriate.

## 14. Did the MBean Appear and Then Disappear?

An MBean can be unregistered when:
- The ApplicationContext closes.
- The exporter cleans up registrations it owns.
- Hot reload/devtools replaces the context.
- Test context teardown runs.
- A module/component shuts down.
- Application code calls unregisterMBean.
- Another exporter replaces the registration.

If the issue only occurs after a restart or shutdown/redeploy, focus on lifecycle. Do not take a single isRegistered snapshot at startup and assume the MBean stays present for the entire lifetime.

Check context startup/shutdown logs, the number of MBeanServers, exporters sharing the same ObjectName, and cleanup rules. In tests, use a dedicated server and unregister after each case.

## 15. JConsole Cannot See It Even Though the Server Has the MBean

When internal code confirms isRegistered(name)==true yet JConsole still does not see it:

1. Is JConsole attached to the right PID/JVM?
2. Is the server the exporter registered with the same server JConsole reads?
3. Are the domain and ObjectName correct?
4. Has the MBeans tab been refreshed?
5. Did the remote connector establish a connection successfully?
6. Does the client have permission to read metadata/attributes?
7. Was the MBean unregistered between the two observations?

If JMX remote fails to connect, investigate authentication, TLS, RMI registry/server port, and advertised hostname. Enabling JMX export in Spring does not automatically open a remote connector; remote management is independent.

Do not modify source annotations when the actual fault belongs to networking or client identity.

## 16. Spring Boot and Actuator

In Spring Boot, the following can coexist:
- JVM platform MBeans.
- Custom Spring @ManagedResource MBeans.
- Library MBeans.
- Actuator endpoints exposed via JMX.

Settings under management.endpoints.jmx.exposure.* mainly control Actuator JMX endpoints, not directly serving as an allowlist for all custom MBeans. HTTP /actuator/health working does not mean custom QueueManagement has been exported.

The spring.jmx.enabled property and export auto-configuration must be understood according to the Spring Boot version. Before adding a manual exporter, check whether an exporter has already been created by the framework. Two exporters registering the same ObjectName is usually a configuration error.

## 17. Reading MBeanInfo to Determine the Actual Contract

Once isRegistered(name) is true:

~~~java
import java.lang.management.ManagementFactory;
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class MetadataInspector {
    public static void inspect() throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.shop.orders:type=Queue,name=outbox");

        if (!server.isRegistered(name)) {
            System.out.println("No MBean");
            return;
        }

        MBeanInfo info = server.getMBeanInfo(name);
        System.out.println(info.getClassName());

        for (MBeanAttributeInfo a : info.getAttributes()) {
            System.out.printf("%s type=%s readable=%s%n",
                    a.getName(), a.getType(), a.isReadable());
        }

        for (MBeanOperationInfo op : info.getOperations()) {
            System.out.println("OP " + op.getName());
        }
    }
}
~~~

This is the actual metadata that JMX clients observe. Having the MBean but missing PendingCount means you need to inspect the annotation assembler, interface, getter naming, or proxy—it is no longer a complete registration failure.

If getAttribute throws an exception even though the attribute is in the metadata, investigate errors inside the getter, Spring AOP, data source, or type mapping.

## 18. Diagnostic Decision Table

| Check | If true | If false |
|---|---|---|
| Right JVM | Check server | Pick the right process/pod |
| Bean in context | Check exporter | Fix scan/profile/@Bean |
| Exporter active | Check selection | Configure an appropriate exporter |
| Bean selected | Check metadata | Fix mapping/autodetection |
| Contract compliant | Check ObjectName | Fix Standard/MXBean/assembler |
| Valid ObjectName | Check conflict | Fix naming |
| No duplicate conflict | Check registration | Fix owner/policy |
| MBeanServer.isRegistered true | Read MBeanInfo | Inspect logs/registration |
| Metadata correct | Check invocation | Fix annotation/interface |
| JConsole on right server | Check client auth/UI | Fix connection/permissions |

Focus on runtime evidence, avoiding changing multiple configurations at once which can obscure the root cause.

## 19. Common Exceptions

| Exception | Hint |
|---|---|
| NotCompliantMBeanException | Bean/proxy does not conform to the management contract |
| InstanceAlreadyExistsException | ObjectName is already registered |
| MalformedObjectNameException | Invalid name syntax |
| InstanceNotFoundException | Client called an unregistered or already unregistered name |
| AttributeNotFoundException | MBean exists, but the attribute does not |
| ReflectionException | JMX operation method/signature mismatch |
| MBeanException | MBean logic threw an error |
| Spring BeanCreationException | Bean/exporter/dependency could not be created |

Read the root cause and context of the stack trace; do not infer from a single exception line alone. For example, NotCompliantMBeanException is not solved by changing the domain; InstanceAlreadyExistsException is not solved by adding @ManagedAttribute.

## 20. Integration Testing to Prevent Regressions

A test should build a Spring context with the proper configuration, use a dedicated MBeanServer to avoid colliding with other tests, and verify:

1. The expected Spring bean exists.
2. The expected ObjectName is registered.
3. MBeanInfo contains the expected attributes/operations.
4. getAttribute returns the appropriate data type.
5. Internal beans are not unintentionally exposed.
6. There are no duplicate exporters/registrations.
7. Context close properly cleans up the MBeans it owns.
8. AOP proxies conform to the contract if the service has advice.

Example of creating an isolated MBeanServer:

~~~java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
        MBeanServerFactory.createMBeanServer("test");
~~~

For the test to be meaningful, you must inject this server into the test context's exporter. Simply creating a dedicated server and querying it while the exporter still uses the platform server will produce a false negative.

Example assertion after Spring context startup:

~~~java
ObjectName name = new ObjectName(
        "com.example.shop.orders:type=Queue,name=outbox");

if (!testServer.isRegistered(name)) {
    throw new AssertionError("MBean missing");
}

Object count = testServer.getAttribute(name, "PendingCount");

if (!(count instanceof Integer)) {
    throw new AssertionError("Unexpected type: " + count);
}
~~~

At the end of the test, close the context and unregister only the registrations belonging to the test. Do not arbitrarily remove MBeans owned by other libraries.

## 21. Controlled Debug Logs

If needed, enable logging for Spring JMX in an appropriate environment:

~~~yaml
logging:
  level:
    org.springframework.jmx: DEBUG
~~~

Use logs to inspect exporter initialization, bean selection, ObjectName, registration errors, and cleanup. Exact messages may vary across Spring versions. Do not leave DEBUG enabled long-term if volume is high or sensitive information is present.

## 22. Mistakes to Avoid

- Creating an additional exporter without knowing what exporters already exist.
- Changing the application-wide proxy strategy when only the ObjectName is wrong.
- Enabling IGNORE_EXISTING to hide duplicates.
- Enabling REPLACE_EXISTING to take over another component's MBean.
- Confusing the Spring bean name with the JMX ObjectName.
- Checking only the platform MBeanServer even though the exporter uses a different server.
- Believing @ManagedResource registers an MBean automatically without an exporter.
- Using getBeanNamesForType(concrete class) to conclude a bean is missing despite a JDK proxy.
- Using HTTP Actuator exposure to fix a custom JMX MBean issue.
- Disabling JMX remote authentication to debug.
- Checking only isRegistered without reading MBeanInfo.
- Polling heavy getters frequently to "confirm" registration when the system is under load.

## 23. Hands-on Exercises

**Exercise 1 — Missing bean.** Create a @Component class in a package outside component scanning. Confirm the Spring context does not have the bean; fix the scan and verify again. Do not conclude JMX succeeded just because the bean exists.

**Exercise 2 — Missing exporter.** Create @ManagedResource and @ManagedAttribute, and confirm that annotations do not self-register. Add exactly one annotation-aware exporter and query the ObjectName.

**Exercise 3 — Duplicate ObjectName.** In a test, register two MBeans with the same name and observe the conflict. Compare FAIL_ON_EXISTING with IGNORE_EXISTING and read MBeanInfo to see which implementation remains exposed.

**Exercise 4 — Wrong server.** Export a bean into a custom test MBeanServer, test isRegistered on both the test server and the platform server, and explain the difference in results.

**Exercise 5 — AOP proxy.** Make a managed bean subject to a JDK dynamic proxy; inspect AopUtils, interface methods, and MBeanInfo. Discuss the adapter approach.

**Exercise 6 — Lifecycle.** Start and then close the Spring context. Verify that registrations disappear properly according to their owner without affecting other MBeans.

## 24. Self-Check Questions

**Does having @ManagedResource guarantee registration?** No. You need a Spring bean and an appropriate exporter.

**Does isRegistered false on the platform server prove no server has the MBean?** No. A custom MBeanServer may be in use.

**What kind of error causes an MBean to exist while PendingCount is missing?** You usually need to check management metadata/interface/assembler and the getter.

**Can a JDK proxy affect JMX?** Yes. Interface method exposure and annotation lookup may differ from the target implementation.

**Why is IGNORE_EXISTING misleading?** Because it can keep the old MBean while silently ignoring the new bean under the same ObjectName.

**Does Spring Boot Actuator JMX exposure control all custom MBeans?** No. That configuration applies to Actuator JMX endpoints.

**Is it necessary to test MBeanInfo?** Yes. It shows the actual contract that clients see.

## 25. Key Takeaways

- Start from the right JVM, MBeanServer, and ObjectName.
- Verify the Spring bean exists, then verify the exporter selects the bean.
- Distinguish annotation metadata, Standard/MXBean interfaces, and registration.
- Check for duplicates, AOP proxies, and lifecycle before making broad configuration changes.
- Read MBeanInfo to verify attributes/operations.
- Write integration tests for presence, absence, data types, and cleanup.
- Keep remote JMX protected; do not widen exposure just for diagnostics.

## 26. References

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Javadoc — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework Javadoc — AnnotationMBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationMBeanExporter.html
- Java SE 21 — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — ObjectName: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

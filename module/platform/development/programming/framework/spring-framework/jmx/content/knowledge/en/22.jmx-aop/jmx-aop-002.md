# Interface-based proxies hiding target classes in Spring Framework JMX and AOP

## Learning objectives

In the Spring Framework, a bean can be wrapped by a **Spring AOP proxy**. If the proxy is created based on interfaces (an interface-based proxy, typically a JDK dynamic proxy), the externally observable object type may expose only the interfaces, while the implementation class (target class) is hidden from operations that rely on the runtime type. This is especially important when \`MBeanExporter\` or an annotation-based JMX exporter needs to locate methods, \`@ManagedResource\`, or an MBean contract from the target.

After this lesson, you will be able to:

- Explain the differences between a target object, a JDK dynamic proxy, and a class-based proxy.
- Recognize why a Spring bean works normally yet a JMX exporter may fail to read metadata on the implementation class.
- Distinguish between **Spring AOP interfaces** and **the JMX management interface**.
- Choose an appropriate export approach: an explicit management interface, annotation metadata on the target, an assembler, or a class-based proxy when justified.
- Use \`AopUtils\`, \`AopProxyUtils\`, \`MBeanInfo\`, and \`MBeanServer\` for diagnostics.
- Write integration tests that reproduce the issue and verify the solution.

## 1. Context: two different proxy systems

Both Spring AOP and JMX can use the concept of a “proxy”, but they solve two different problems:

- A **Spring AOP proxy** intercepts Java calls to a Spring bean to apply advice: transactions, logging, security, metrics, or cross-cutting concerns.
- A **JMX ModelMBean/Standard MBean** publishes a management contract for management tools via \`MBeanServer\`.
- An **MBean client proxy**, such as \`MBeanProxyFactoryBean\`, turns a client-side Java method call into a JMX operation targeting an \`ObjectName\`.

This lesson focuses on the case where **MBeanExporter receives a Spring AOP interface-based proxy as the bean to export**.

Model:

\`\`\`text
Spring ApplicationContext
    |
    +-- Target object: OrderProcessor
    |       implements OrderOperations
    |       @ManagedResource on implementation
    |
    +-- Spring AOP JDK proxy
            implements OrderOperations
            runtime class = com.sun.proxy... / jdk.proxy...
            |
            +-- advice (logging, transaction, ...)
            +-- delegate -> target OrderProcessor

MBeanExporter / JMX annotation discovery
    |
    +-- receives bean reference from ApplicationContext
    +-- needs to determine type, metadata, management API
    |
    v
MBeanServer registry
\`\`\`

If the framework introspects the **proxy class** as if it were the original implementation, annotations on \`OrderProcessor\` may not appear on the proxy class. Furthermore, public methods that exist only on the target class and are not part of the interfaces implemented by the proxy will not be directly callable through a proxy-typed reference variable.

Spring JMX includes extensive support for AOP proxies, but the degree of automatic handling depends on the Spring version, how the assembler/naming strategy is configured, the proxy type, and the exporter path used. Therefore, you must rely on runtime inspection rather than concluding categorically that every JDK proxy breaks JMX.

## 2. How does a JDK dynamic proxy hide the implementation class?

Suppose you have a business interface:

\`\`\`java
package com.example.orders;

public interface OrderOperations {
    void processOrder(String orderId);
}
\`\`\`

Implementation:

\`\`\`java
package com.example.orders;

public class OrderProcessor implements OrderOperations {

    @Override
    public void processOrder(String orderId) {
        System.out.println("Processing " + orderId);
    }

    public int getPendingCount() {
        return 12;
    }

    public void resetStatistics() {
        System.out.println("Reset statistics");
    }
}
\`\`\`

If Spring AOP uses a **JDK dynamic proxy**, the object reference returned by the container may look like:

\`\`\`text
jdk.proxy2.$Proxy...
  implements OrderOperations
\`\`\`

Key points:

1. The proxy implements \`OrderOperations\` and can invoke \`processOrder\`.
2. The proxy is generally not a subclass of \`OrderProcessor\`.
3. Therefore, \`proxy instanceof OrderProcessor\` may be \`false\`.
4. The methods \`getPendingCount\` and \`resetStatistics\` are not in \`OrderOperations\`, so they cannot be invoked through this interface.
5. Annotations placed on the implementation class do not automatically become annotations on the proxy's runtime class.

Example:

\`\`\`java
OrderOperations service = context.getBean(OrderOperations.class);

System.out.println(service.getClass());
System.out.println(service instanceof OrderProcessor);

// service.getPendingCount(); // Does not compile: interface lacks the method.
\`\`\`

If you look up by \`OrderProcessor.class\` instead of \`OrderOperations.class\`, dependency lookup can also fail if the exposed proxy type is not assignable to that class.

This is a **type visibility and contract issue**, not proof that the target has disappeared. The target can still exist behind the proxy and continue executing logic.

## 3. When is an interface-based proxy created?

Spring AOP can create a JDK dynamic proxy if the target has suitable interfaces and the configuration selects interface-based proxying. A class-based proxy (often called a CGLIB proxy in the Spring context) creates a subclass of the target, so type and method visibility differ.

Situations that commonly create a Spring AOP proxy:

- \`@Transactional\` combined with transaction infrastructure.
- \`@Aspect\` containing advice such as \`@Around\`, \`@Before\`, \`@After\`.
- Interceptors via \`ProxyFactory\`.
- Certain method security mechanisms or custom \`BeanPostProcessor\` implementations.

**Important note:** In Spring Boot or different framework setups/versions, class-based proxy mode may be enabled by default or auto-configured. Therefore, do not infer the proxy type solely from seeing \`@Transactional\`.

Check at runtime:

\`\`\`java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderProcessor");

System.out.println("Runtime class: " + bean.getClass().getName());
System.out.println("AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("JDK proxy: " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("CGLIB proxy: " + AopUtils.isCglibProxy(bean));
\`\`\`

These checks identify the wrapper class Spring is providing; they do not by themselves conclude whether the final JMX metadata is correct. That part requires inspecting \`MBeanInfo\` after registration.

## 4. Management interface vs. business interface

Suppose an application uses \`OrderOperations\` for business logic, yet wants to manage the pending order count via JMX.

You can create a separate management contract:

\`\`\`java
package com.example.orders;

public interface OrderAdminMBean {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

Then the implementation can implement both:

\`\`\`java
package com.example.orders;

public class OrderProcessor
        implements OrderOperations, OrderAdminMBean {

    @Override
    public void processOrder(String orderId) {
        System.out.println("Processing " + orderId);
    }

    @Override
    public int getPendingCount() {
        return 12;
    }

    @Override
    public void resetStatistics() {
        System.out.println("Reset statistics");
    }
}
\`\`\`

However, merely having the \`OrderAdminMBean\` interface **does not automatically guarantee** that a JDK proxy created for the bean will expose that interface. A proxy might be configured to implement only \`OrderOperations\`. If the exporter needs to locate/call management methods on the proxy, you must check which interfaces the proxy actually implements and whether the exporter has an appropriate unwrap/adapter mechanism.

In addition, for a Standard MBean under JMX conventions, the interface \`OrderProcessorMBean\` is what matches the class \`OrderProcessor\`. The name \`OrderAdminMBean\` in this example is a **custom management interface** and requires an appropriate adapter, assembler, or configuration; you cannot infer solely from the \`MBean\` suffix that JMX automatically recognizes it as the Standard MBean interface for \`OrderProcessor\`.

This is why *business API*, *Java proxy interfaces*, and *JMX management API* must be distinguished.

## 5. The issue of annotations on the target class

Spring JMX provides these annotations:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
\`\`\`

Example:

\`\`\`java
@ManagedResource(
    objectName = "com.example.orders:type=OrderAdmin,name=primary")
public class OrderProcessor implements OrderOperations {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }

    @ManagedOperation
    public void resetStatistics() {
        // ...
    }

    @Override
    public void processOrder(String id) {
        // ...
    }
}
\`\`\`

When Spring AOP wraps \`OrderProcessor\` in a JDK dynamic proxy:

- The \`@ManagedResource\` annotation remains on the target class.
- The runtime proxy class does not necessarily inherit that annotation.
- Management methods outside \`OrderOperations\` may not be exposed on the proxy interfaces.
- Type/metadata-based bean discovery needs to be able to locate the target class and an appropriate contract.

\`AnnotationMBeanExporter\`, \`MetadataMBeanInfoAssembler\`, and Spring AOP utilities can assist with metadata handling for AOP proxies. However, if you use a custom assembler that simply calls \`bean.getClass().getAnnotation(...)\`, the outcome can be completely different because \`bean.getClass()\` is the proxy class at that point.

Do not "fix" this yourself by casting:

\`\`\`java
OrderProcessor target = (OrderProcessor) context.getBean("orderProcessor");
\`\`\`

With a JDK proxy, the cast can throw \`ClassCastException\`. If an internal component needs to work with the implementation type, designing bean/proxy and interface injection properly from the start is safer.

## 6. Reproducing a JDK proxy with ProxyFactory

The following standalone example proactively creates an interface-based proxy.

\`\`\`java
package com.example.orders;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

public class JdkProxyExample {

    public static void main(String[] args) {
        OrderProcessor target = new OrderProcessor();

        ProxyFactory factory = new ProxyFactory();
        factory.setTarget(target);
        factory.setInterfaces(OrderOperations.class);
        factory.setProxyTargetClass(false);

        factory.addAdvice((MethodInterceptor) invocation -> {
            System.out.println("AOP before " +
                    invocation.getMethod().getName());
            return invocation.proceed();
        });

        Object proxy = factory.getProxy();

        System.out.println("proxyType = " + proxy.getClass().getName());
        System.out.println("isJdkProxy = "
                + AopUtils.isJdkDynamicProxy(proxy));
        System.out.println("isOrderProcessor = "
                + (proxy instanceof OrderProcessor));
        System.out.println("isOrderOperations = "
                + (proxy instanceof OrderOperations));

        ((OrderOperations) proxy).processOrder("A-123");
    }
}
\`\`\`

In this configuration, we explicitly ask the proxy to implement \`OrderOperations\`, not the target class. As a result, the difference in type visibility becomes clear.

When testing JMX, do not focus only on whether the proxy object has the same \`getClass()\` as the target. The necessary condition is that the exporter can register the managed object with the right metadata, and clients can then access the expected attributes/operations.

## 7. MBeanExporter registration: what happens when passing a proxy?

An \`MBeanExporter\` can accept a mapping between \`ObjectName\` and Spring beans:

\`\`\`java
@Bean
public MBeanExporter exporter(
        OrderOperations orderProcessor,
        MBeanServer mBeanServer) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(mBeanServer);
    exporter.setBeans(Map.of(
        "com.example.orders:type=OrderAdmin,name=primary",
        orderProcessor
    ));
    return exporter;
}
\`\`\`

Here, \`orderProcessor\` may be a JDK proxy. \`MBeanExporter\` needs to decide whether the object has a valid Standard MBean/MXBean contract or requires a ModelMBean adapter and assembler.

What can happen depending on configuration:

1. The exporter may use internal support to determine the managed target type/metadata.
2. The configured assembler may inspect the proxy interfaces instead of the implementation.
3. Management methods not belonging to the interfaces exposed by the proxy may not be accessible via normal invocation.
4. Registration may succeed, yet the MBean may be missing attributes/operations the author expected.
5. Registration may also fail if the metadata/type cannot form a valid MBean contract.

You should not state this failure as an absolute rule that "JDK proxies cannot be exported via JMX". Spring itself has mechanisms for handling proxies; the real issue is **alignment between the object the exporter receives, what the metadata assembler reads, and which methods the proxy can invoke**.

## 8. Inspecting the bean and target type with Spring AOP utilities

Some useful APIs:

\`\`\`java
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderProcessor");

Class<?> runtimeClass = bean.getClass();
Class<?> targetClass = AopUtils.getTargetClass(bean);
Class<?> ultimateTargetClass =
        AopProxyUtils.ultimateTargetClass(bean);

System.out.println("runtimeClass = " + runtimeClass.getName());
System.out.println("targetClass = " + targetClass.getName());
System.out.println("ultimateTargetClass = "
        + ultimateTargetClass.getName());
\`\`\`

Meaning:

- \`bean.getClass()\`: the runtime class currently provided by injection.
- \`AopUtils.isJdkDynamicProxy(bean)\`: determines whether the object is a JDK proxy under the Spring AOP mechanism.
- \`AopUtils.getTargetClass(bean)\`: attempts to determine the target type behind the AOP proxy when information is available.
- \`AopProxyUtils.ultimateTargetClass(bean)\`: attempts to find the ultimate target class across proxy layers as supported by Spring.

These utilities are for introspection. They **do not turn** a JDK proxy into an instance that can be cast to the target class, nor do they automatically add missing management methods to the proxy interface.

Do not abuse \`Advised.getTargetSource().getTarget()\` to bypass AOP and call the target directly. With scoped/dynamic target sources, retrieving the target can involve lifecycle concerns and require releasing it. Moreover, bypassing AOP can skip transaction, security, or logging advice that the application relies on.

## 9. Option 1 — Export a separate management facade

This is usually the least surprising design when a business service has multiple AOP advices.

\`\`\`java
package com.example.orders;

public interface OrderMetricsView {
    long getPendingCount();
}
\`\`\`

Business service:

\`\`\`java
package com.example.orders;

public class OrderService implements OrderOperations, OrderMetricsView {
    private volatile long pendingCount = 12;

    @Override
    public void processOrder(String id) {
        // Business logic
    }

    @Override
    public long getPendingCount() {
        return pendingCount;
    }
}
\`\`\`

Management facade:

\`\`\`java
package com.example.orders;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=OrderMetrics,name=primary")
public class OrderMetricsAdmin {

    private final OrderMetricsView metrics;

    public OrderMetricsAdmin(OrderMetricsView metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute
    public long getPendingCount() {
        return metrics.getPendingCount();
    }
}
\`\`\`

Java Config:

\`\`\`java
@Configuration
@EnableMBeanExport
public class OrderJmxConfiguration {

    @Bean
    public OrderMetricsAdmin orderMetricsAdmin(
            OrderMetricsView orderMetrics) {
        return new OrderMetricsAdmin(orderMetrics);
    }
}
\`\`\`

The configuration assumes a corresponding \`OrderMetricsView\` Spring bean already exists in the context. If \`OrderService\` is AOP-proxied under \`OrderOperations\` without exposing \`OrderMetricsView\`, you need to ensure that the \`OrderMetricsView\` interface is also exposed by the proxy or create an adapter that reads the metric from another dependency. Do not treat this example as a magic fix for a missing proxy interface.

**The advantage of a facade** is that only the dedicated management class carries \`@ManagedResource\`, separating the management contract from the AOP-wrapped business implementation. Exporter introspection of the facade is simpler, and the JMX surface is clearly bounded.

## 10. Option 2 — Include the management interface in the proxy interfaces

If you want the exporter to register the AOP-proxied bean directly, you can design an interface containing the management methods and ensure the JDK proxy implements that interface.

\`\`\`java
package com.example.orders;

public interface OrderManagement {
    int getPendingCount();
    void resetStatistics();
}
\`\`\`

Implementation:

\`\`\`java
public class OrderProcessor
        implements OrderOperations, OrderManagement {
    @Override
    public void processOrder(String id) { /* ... */ }

    @Override
    public int getPendingCount() { return 12; }

    @Override
    public void resetStatistics() { /* ... */ }
}
\`\`\`

If creating the proxy manually:

\`\`\`java
ProxyFactory factory = new ProxyFactory();
factory.setTarget(new OrderProcessor());
factory.setInterfaces(OrderOperations.class, OrderManagement.class);
factory.setProxyTargetClass(false);

Object proxy = factory.getProxy();
\`\`\`

Then the proxy can be cast to \`OrderManagement\` and the two management methods invoked through the AOP layer. However, **the JMX exporter still needs an appropriate assembler or contract**. \`OrderManagement\` is not automatically a Standard MBean interface because its name does not follow the \`OrderProcessorMBean\` convention and the runtime proxy class is not \`OrderProcessor\`.

One management configuration approach is \`InterfaceBasedMBeanInfoAssembler\` to select methods from \`OrderManagement\`, then using \`MBeanExporter\` to export the proxy. You should verify the metadata and actual dispatch of the proxy in your chosen Spring version.

## 11. Option 3 — Class-based proxy (proxyTargetClass)

Spring supports class-based proxies to subclass the target, which is often useful when you need to invoke methods not declared on an interface.

Spring AOP configuration example:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
\`\`\`

Or with \`ProxyFactory\`:

\`\`\`java
ProxyFactory factory = new ProxyFactory(new OrderProcessor());
factory.setProxyTargetClass(true);
Object proxy = factory.getProxy();
\`\`\`

Class-based proxies are typically assignable to the target class, so some JDK proxy type-visibility issues are reduced. However:

- Final classes cannot be subclassed; final methods cannot be overridden for advice.
- Private methods are not advised under the subclass proxy mechanism.
- Annotation introspection still needs to identify the proper target class/method.
- Choosing a class-based proxy does not mean every method should be exported via JMX.
- Changing the proxy strategy can affect the entire application; do not enable it globally just to fix a single MBean if a management facade meets your requirements.

For multi-module products, selecting a specific proxy level must consider transactions, security, performance, and compatibility—not just JMX.

## 12. Option 4 — Use an explicit assembler instead of relying on annotation guessing

\`MBeanExporter\` can use an \`MBeanInfoAssembler\` to control the management interface. With an interface-based assembler:

\`\`\`java
import org.springframework.jmx.export.assembler.InterfaceBasedMBeanInfoAssembler;

@Bean
public InterfaceBasedMBeanInfoAssembler managementAssembler() {
    InterfaceBasedMBeanInfoAssembler assembler =
            new InterfaceBasedMBeanInfoAssembler();
    assembler.setManagedInterfaces(OrderManagement.class);
    return assembler;
}
\`\`\`

Attaching the assembler:

\`\`\`java
@Bean
public MBeanExporter orderExporter(
        OrderManagement orderManagement,
        MBeanServer server,
        InterfaceBasedMBeanInfoAssembler managementAssembler) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setAssembler(managementAssembler);
    exporter.setBeans(Map.of(
        "com.example.orders:type=OrderAdmin,name=primary",
        orderManagement
    ));
    return exporter;
}
\`\`\`

Here, \`OrderManagement\` must genuinely be an interface exposed by the bean/proxy. The assembler creates metadata from the management methods instead of publishing every public method to JMX. This is suitable when you need to ensure a JDK-proxied service still has a callable management contract.

If you are using annotation-based \`@ManagedResource\` and \`MetadataMBeanInfoAssembler\`, you must coordinate the corresponding naming strategy and attribute source. Changing the assembler can change the set of attributes/operations. By design, do not combine multiple exporters for the same \`ObjectName\` unintentionally.

## 13. Illustrating the bug from custom introspection that only checks bean.getClass()

A typical bug in custom integrations:

\`\`\`java
Class<?> type = bean.getClass();

ManagedResource resource =
        type.getAnnotation(ManagedResource.class);

if (resource == null) {
    // Incorrectly concludes the bean has no JMX annotation.
}
\`\`\`

If \`bean\` is a JDK proxy, \`type\` will be the proxy class, and annotations on \`OrderProcessor\` may not be visible.

A more suitable way to resolve the type in Spring:

\`\`\`java
Class<?> targetType = AopUtils.getTargetClass(bean);

ManagedResource resource =
        org.springframework.core.annotation.AnnotatedElementUtils
                .findMergedAnnotation(
                        targetType, ManagedResource.class);
\`\`\`

This is an example of AOP-aware **metadata lookup**, not the entire MBean creation process. For a custom exporter, you must also ensure that methods selected by metadata can actually be invoked on the object receiving registration.

If the target class has \`@ManagedOperation\` on a method not present in the proxy interfaces, finding the annotation alone is not enough; the JMX ModelMBean still needs an appropriate target/invocation path.

## 14. Inspecting JMX metadata after exporter registration

An important way to distinguish proxy issues from registration issues is reading \`MBeanInfo\`:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = context.getBean(MBeanServer.class);
ObjectName name = new ObjectName(
        "com.example.orders:type=OrderAdmin,name=primary");

System.out.println("Registered: " + server.isRegistered(name));

if (server.isRegistered(name)) {
    MBeanInfo info = server.getMBeanInfo(name);

    System.out.println("Class: " + info.getClassName());

    for (var attr : info.getAttributes()) {
        System.out.println(
                "Attribute: " + attr.getName()
                + " / " + attr.getType());
    }

    for (var op : info.getOperations()) {
        System.out.println(
                "Operation: " + op.getName());
    }
}
\`\`\`

\`isRegistered(name)=true\` only confirms the name is in the registry; it does not prove the expected methods are published. You must inspect the list of attributes, operations, signatures, and invocation behavior to know whether the proxy/assembler is working properly.

For example, if \`getPendingCount\` does not appear, determine:

- Was the bean exported as a Standard MBean or a ModelMBean?
- Did the exporter receive a raw target, a JDK proxy, or a class-based proxy?
- Is the assembler reading the proxy interfaces or the target class?
- Was another MBean already registered under the same \`ObjectName\` beforehand?
- Does the proxy expose the method to be invoked?

## 15. Calls via MBeanServer and direct beans can differ

Suppose the direct bean is the \`OrderOperations\` interface:

\`\`\`java
OrderOperations direct = context.getBean(OrderOperations.class);
direct.processOrder("123");
\`\`\`

This call passes through the Spring AOP proxy and then to the target, applying configured advice. A JMX operation such as:

\`\`\`java
server.invoke(
        name,
        "resetStatistics",
        new Object[0],
        new String[0]);
\`\`\`

will go through \`MBeanServer\` and the adapter/registration, and then to the object registered by the exporter.

If the exporter registers the Spring AOP proxy itself and invocation goes through an exposed interface, advice can continue to operate. If the exporter registers a different target or the adapter interaction bypasses advice, the outcome may differ.

Therefore, do not claim that "JMX always bypasses AOP" or "JMX always has transactions". You must test behavior against the actual registered object.

## 16. How to write integration tests that detect the issue

A test should verify at least three parts:

1. The Spring bean is actually a JDK proxy.
2. \`MBeanServer\` contains the expected \`ObjectName\`.
3. \`MBeanInfo\` and operation behavior match the management contract.

Example checking the proxy type with JUnit Jupiter:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ProxyVisibilityTest {

    @Test
    void beanUsesJdkProxyAndHidesImplementationType() {
        try (var context = new AnnotationConfigApplicationContext(
                ProxyTestConfiguration.class)) {

            Object bean = context.getBean("orderProcessor");

            assertTrue(AopUtils.isJdkDynamicProxy(bean));
            assertTrue(bean instanceof OrderOperations);
            assertFalse(bean instanceof OrderProcessor);
        }
    }
}
\`\`\`

Here \`ProxyTestConfiguration\` is a self-created test fixture configuring an \`OrderProcessor\` proxied by interface. These assertions are only valid when the fixture explicitly requests a JDK proxy; they do not automatically hold for every Spring Boot application.

The JMX verification part needs to read metadata from the server used by the exporter:

\`\`\`java
@Test
void jmxExportsOnlyExpectedManagementOperations() throws Exception {
    try (var context = new AnnotationConfigApplicationContext(
            ProxyJmxTestConfiguration.class)) {

        MBeanServer server = context.getBean(MBeanServer.class);
        ObjectName name = new ObjectName(
            "com.example.orders:type=OrderAdmin,name=primary");

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(
            java.util.Arrays.stream(info.getOperations())
                .anyMatch(op -> "resetStatistics".equals(op.getName())));

        assertFalse(
            java.util.Arrays.stream(info.getOperations())
                .anyMatch(op -> "processOrder".equals(op.getName())));
    }
}
\`\`\`

This test snippet assumes \`ProxyJmxTestConfiguration\` has registered a valid exporter, server, and managed object. To isolate tests running in parallel, use a separate \`MBeanServer\` or distinct \`ObjectName\` instead of sharing the platform registry.

### Practice fixture with a proxy having two interfaces

\`\`\`java
@Configuration
public class ProxyJmxTestConfiguration {

    @Bean
    public OrderManagement orderManagement() {
        OrderProcessor target = new OrderProcessor();

        ProxyFactory factory = new ProxyFactory();
        factory.setTarget(target);
        factory.setInterfaces(
                OrderOperations.class,
                OrderManagement.class);
        factory.setProxyTargetClass(false);

        return (OrderManagement) factory.getProxy();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return java.lang.management.ManagementFactory
                .getPlatformMBeanServer();
    }

    @Bean
    public InterfaceBasedMBeanInfoAssembler assembler() {
        InterfaceBasedMBeanInfoAssembler assembler =
                new InterfaceBasedMBeanInfoAssembler();
        assembler.setManagedInterfaces(OrderManagement.class);
        return assembler;
    }

    @Bean
    public MBeanExporter exporter(
            OrderManagement orderManagement,
            MBeanServer mBeanServer,
            InterfaceBasedMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "com.example.orders:type=OrderAdmin,name=primary",
            orderManagement));
        return exporter;
    }
}
\`\`\`

This fixture illustrates how to ensure the proxy exposes the management interface and the assembler publishes only management methods. The corresponding imports come from \`javax.management\`, \`org.springframework.aop.framework\`, \`org.springframework.context.annotation\`, \`org.springframework.jmx.export\`, and \`org.springframework.jmx.export.assembler\`.

When implementing a real project, ensure \`OrderProcessor\` implements \`OrderManagement\` with the matching return types/signatures, and avoid simultaneously creating a separate \`OrderProcessor\` bean used by the business service—doing so could create two different instances, causing JMX to read stale/wrong state.

## 17. Diagnostics via logs and proxy types

A practical investigation workflow:

| Step | Question | How to verify |
| --- | --- | --- |
| 1 | Does the bean actually exist? | \`context.containsBean\`, \`getBean\` |
| 2 | Is the runtime object an AOP proxy? | \`AopUtils.isAopProxy\` |
| 3 | Is the proxy interface-based or class-based? | \`isJdkDynamicProxy\`, \`isCglibProxy\` |
| 4 | What is the target type? | \`getTargetClass\`, \`ultimateTargetClass\` |
| 5 | Which interfaces does the proxy expose? | \`bean.getClass().getInterfaces()\` / \`instanceof\` |
| 6 | Which object is the exporter registering? | \`setBeans\` configuration, bean references |
| 7 | Is the ObjectName in the server? | \`server.isRegistered\` |
| 8 | Are attributes/operations correct? | \`getMBeanInfo\` |
| 9 | Does invoking the operation go through advice? | Test instrumentation/logging around the method |
| 10 | Is there another exporter with the same name? | Check registration ownership and naming |

Distinguish two error groups:

- **Discovery/metadata error**: the exporter does not see annotations or methods because introspection mistakes the runtime proxy type.
- **Invocation/contract error**: metadata may be built, yet the object receiving calls does not expose the corresponding method or the JMX contract is invalid.

The remedies differ. Changing the naming strategy does not fix a missing method; changing the proxy mode does not fix a duplicate \`ObjectName\`.

## 18. When to choose which solution?

| Situation | Option to consider | Reason |
| --- | --- | --- |
| Business service has many methods that should not be exposed | Separate management facade | Limits JMX surface |
| Need to keep JDK proxy and manage a small set of methods | Management interface exposed by proxy + assembler | Clear contract |
| Project already uses JMX annotations on implementation | Check annotation-aware exporter + target introspection | Preserves metadata, avoids direct proxy-class lookup |
| Class-based proxy is already needed by the application | Class-based proxy + metadata tests | Reduces interface visibility limitations |
| Client only needs read-only metrics | Read-only facade/attributes | Avoids operations with side effects |
| Need to call management methods from another module in the same JVM | Local MBean proxy or direct interface depending on purpose | Separates management from business logic |

There is no single configuration change that fits every system. The goal is to keep the **Spring AOP contract, JMX management metadata, and runtime invocation path consistent**, while keeping the management surface as small as necessary.

## 19. Common mistakes

### Mistake 1 — Casting a JDK proxy to the implementation class

\`\`\`java
OrderProcessor processor =
        (OrderProcessor) context.getBean("orderProcessor");
\`\`\`

If the bean is a JDK dynamic proxy, the cast may fail. Inject via an interface exposed by the proxy or intentionally design a class-based proxy.

### Mistake 2 — Looking up @ManagedResource only on the runtime proxy class

\`\`\`java
bean.getClass().getAnnotation(ManagedResource.class);
\`\`\`

The result can be \`null\` even when the target class has the annotation. Use Spring AOP-aware introspection and verify the actual exporter.

### Mistake 3 — Having @ManagedOperation while the proxy does not expose the method

An annotation on the target does not mean the JDK proxy has that method. Consider moving the method to a management interface implemented by the proxy, or using a facade.

### Mistake 4 — Enabling proxyTargetClass solely to fix JMX without assessing consequences

Class-based proxies have limitations with final methods and can change type/injection behavior. Do not change this globally without integration tests.

### Mistake 5 — Registering the raw target to avoid the proxy, losing AOP advice

If the exporter bypasses the Spring proxy and registers the target separately, JMX operations may not pass through transaction/security advice. Verify runtime behavior and avoid stripping business protection layers.

### Mistake 6 — Using the same ObjectName for multiple exporters

When two exporters register the same name, \`InstanceAlreadyExistsException\` or ignore/replace policies may mask the wrong target. Keep the owner and JMX name clear.

## 20. Practice exercises

**Exercise 1 — Identifying a JDK proxy:** create \`OrderProcessor implements OrderOperations\`, use \`ProxyFactory.setInterfaces(OrderOperations.class)\`, call \`AopUtils.isJdkDynamicProxy\`, and try casting to \`OrderProcessor\`. Explain the result.

**Exercise 2 — Hidden metadata:** place \`@ManagedResource\` on the target class. Compare \`bean.getClass().getAnnotation(ManagedResource.class)\` with \`AopUtils.getTargetClass(bean)\` and Spring merged annotation lookup.

**Exercise 3 — Management interface:** add \`OrderManagement\` and ensure the JDK proxy implements both \`OrderOperations\` and \`OrderManagement\`. Use \`InterfaceBasedMBeanInfoAssembler\` to export only management methods.

**Exercise 4 — Facade:** create \`OrderMetricsAdmin\` with only \`getPendingCount\`, injecting the service via \`OrderMetricsView\`. Export the facade using JMX annotations and verify \`processOrder\` is absent from \`MBeanInfo\`.

**Exercise 5 — AOP advice:** add logging advice around a management method, call the interface directly, and then call via \`MBeanServer.invoke\`. Check which calls trigger the advice and explain based on the object the exporter actually registered.

**Exercise 6 — Changing proxy mode:** run the same fixture with a JDK proxy and a class-based proxy, comparing \`getClass()\`, \`instanceof\`, the interface list, and JMX metadata. Do not reuse conclusions from one mode for the other.

## Conclusion

**Interface-based proxies can hide target classes** because a JDK dynamic proxy exposes interfaces rather than becoming a subclass of the implementation. In Spring Framework JMX, this can prevent \`@ManagedResource\` metadata on the target from being detected by custom introspection, or prevent management methods outside the proxy interfaces from being invoked through the proxy path. The solution is to clearly separate the Spring AOP proxy, the JMX management contract, and the target object; use a facade, an appropriate management interface/assembler, or a class-based proxy when justified. Always inspect the runtime proxy type and \`MBeanInfo\` to confirm which methods are actually published over JMX.

# Impact of Spring AOP Proxies on JMX Annotation Detection

## Objectives

In the Spring Framework, a bean annotated with JMX annotations may no longer appear at runtime as its original class. AOP mechanisms such as `@Transactional`, `@Async`, `@Cacheable`, method security, and custom advice can create a **JDK dynamic proxy** or a **class-based proxy**. This affects how the exporter locates `@ManagedResource`, reads `@ManagedAttribute` and `@ManagedOperation`, determines callable methods, and routes JMX calls to the actual bean.

After this lesson, you will be able to:

- Distinguish between the target class, the runtime proxy class, and the interfaces exposed by the proxy.
- Explain the mechanism by which an exporter/metadata assembler detects JMX annotations on Spring beans.
- Understand why an annotation can exist on the target while the method remains inaccessible through the proxy.
- Organize `@EnableMBeanExport`, `MBeanExporter`, naming strategies, and AOP configuration appropriately.
- Diagnose cases where a JMX MBean is missing, its name changes, an operation does not appear, or a call bypasses advice.
- Design a management adapter and integration tests involving both Spring AOP and `MBeanServer`.

## 1. A Spring bean can be a proxy rather than the target

Suppose you have a service:

```java
@Service
@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main"
)
public class OrderProcessor {

    @ManagedAttribute
    public int getPendingCount() {
        return 10;
    }

    @ManagedOperation
    public void retryFailed() {
        // ...
    }
}
```

If an advisor or an annotation such as `@Transactional` applies to the bean, the `ApplicationContext` may provide a proxy instead of an instance of this class.

```text
ApplicationContext.getBean("orderProcessor")
         |
         v
    Spring AOP proxy
         |
         v
      target object
       OrderProcessor
```

From the caller's perspective, the proxy is the actual bean. However, JMX annotations are typically declared on **the target's class and methods**. A tool that reads metadata via `bean.getClass()` without understanding proxies may observe:

- A runtime class such as `jdk.proxy...` or `com.sun.proxy...` for a JDK dynamic proxy.
- A runtime class that is a subclass such as `OrderProcessor$$SpringCGLIB$$...` for a class-based proxy.
- Class-level or method-level annotations that may need to be looked up on the target class or the original declaring method.

Spring JMX and Spring AOP provide helpers to handle this situation, but the final outcome also depends on the proxy type, the exposed interfaces, the assembler, and the configured exporter.

## 2. What roles do JMX annotations play?

Spring JMX provides the following annotations:

- `@ManagedResource`: marks a managed resource, typically declaring an ObjectName and description.
- `@ManagedAttribute`: describes a getter/setter exported as a JMX attribute.
- `@ManagedOperation`: marks a method published as an operation.
- `@ManagedOperationParameter` and `@ManagedOperationParameters`: provide management parameter information.
- `@ManagedNotification` and `@ManagedNotifications`: declare notification metadata for a suitable resource.

Annotations do not register an MBean by themselves. They require infrastructure such as `AnnotationMBeanExporter` or an `MBeanExporter` with `MetadataMBeanInfoAssembler`/`AnnotationJmxAttributeSource`.

A simple Java configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

If the Spring bean has been scanned and its metadata detected, the exporter can register the MBean with the `MBeanServer`. However, if the bean is proxied, two questions must be distinguished:

1. Does Spring **find the annotations on the target**?
2. Can JMX **actually invoke the method** through the exported object?

These are two different layers of the problem. A configuration can pass metadata discovery and still fail when invoking an operation.

## 3. JDK dynamic proxy: exposes interfaces only

A JDK dynamic proxy creates an object that implements one or more Java interfaces. It does not directly inherit from the implementation class.

For example:

```java
public interface OrderService {
    int getPendingCount();
}

@Service
@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main"
)
public class OrderServiceImpl implements OrderService {

    @Override
    @ManagedAttribute
    public int getPendingCount() {
        return 10;
    }

    @ManagedOperation
    public void retryFailed() {
        // This method is NOT on OrderService.
    }
}
```

When Spring creates a JDK proxy for `OrderService` only, callers can invoke `getPendingCount()` through the proxy, but cannot invoke `retryFailed()` via that interface. Therefore, even though `retryFailed()` has `@ManagedOperation` on the target, an exporter using the proxy as the managed object may run into a situation where that method cannot be exposed or invoked.

```text
JDK proxy implements OrderService
  getPendingCount()    -> present
  retryFailed()        -> not in the proxy interface

OrderServiceImpl target
  getPendingCount()    -> present
  retryFailed()        -> present, @ManagedOperation
```

**You cannot fix the issue merely by adding annotations to the target method.** You need to design a suitable interface/proxy/adapter or use an export approach that ensures calls reach the target properly.

One option is to place the operations that genuinely need management onto an interface exposed by the proxy. However, it is not necessary to mix management methods into the business interface; a separate management adapter is usually clearer.

## 4. Class-based proxy: inherits the class but still has limitations

A class-based proxy (commonly using CGLIB in Spring AOP) creates a subclass of the target class.

```text
OrderServiceImpl
   ^
   |
OrderServiceImpl$$SpringCGLIB$$...
```

With this approach, inherited public methods can usually be invoked through the proxy, and Spring helpers can trace back to the target class to read annotations.

However, a class-based proxy does not mean every method will be advised:

- `final` methods cannot be overridden to be intercepted via subclassing.
- `private` methods cannot be intercepted by a proxy like public methods.
- Certain methods not visible to the subclass may not be advised.
- `final` classes cannot be class-based proxied via inheritance.
- Self-invocation within the target usually bypasses proxy-based advice.

Therefore, even when JMX export sees the operation, you should check whether **the call path goes through the expected advice**, especially for transactions, security, or logging.

## 5. Annotations on the original class, proxy at runtime

In Java, calling:

```java
bean.getClass().isAnnotationPresent(ManagedResource.class)
```

may produce an unexpected result if `bean` is a proxy. A JDK proxy class is not the original class carrying the annotation.

Spring provides AOP utility APIs to determine the target class, for example:

```java
import org.springframework.aop.framework.AopProxyUtils;
import org.springframework.aop.support.AopUtils;

Class<?> targetType = AopProxyUtils.ultimateTargetClass(bean);

System.out.println("runtime class = " + bean.getClass());
System.out.println("target class  = " + targetType);
System.out.println("is AOP proxy  = " + AopUtils.isAopProxy(bean));
System.out.println("is JDK proxy  = " + AopUtils.isJdkDynamicProxy(bean));
System.out.println("is class proxy= " + AopUtils.isCglibProxy(bean));
```

These helpers are useful for diagnostics and tests. Do not write export logic by arbitrarily unwrapping the inner target object from a proxy, as doing so can lose advice that the application depends on.

Reading metadata requires understanding the target class, while **invocation** must follow a path designed to preserve transactions/security if those advices are required.

## 6. MetadataMBeanInfoAssembler and AnnotationJmxAttributeSource

When using annotation-driven JMX export, extracting `@Managed*` information is the responsibility of the metadata source and assembler.

Typical components:

```text
Spring bean
  |
  +--> AnnotationJmxAttributeSource
  |      reads @ManagedResource/@ManagedAttribute/@ManagedOperation
  |
  +--> MetadataMBeanInfoAssembler
  |      creates JMX metadata (attributes, operations, descriptions)
  |
  +--> MetadataNamingStrategy
  |      determines the ObjectName when applying metadata naming
  |
  v
MBeanExporter / AnnotationMBeanExporter
  |
  v
MBeanServer
```

If you use:

```java
@EnableMBeanExport
```

Spring configures the appropriate infrastructure for annotation-driven export. If you configure `MBeanExporter` manually, do not assume that the exporter automatically uses the annotation metadata assembler without setting the required configuration.

For a proxied bean, differences between the target method and the proxy method can affect:

- Locating annotations placed on implementation methods.
- The class type used for introspection.
- The ability to map the method onto the object actually exposed via JMX.
- The ObjectName if the strategy relies on the runtime class.
- The list of attributes and operations in `MBeanInfo`.

Therefore, diagnosis must inspect **the actual registered metadata** rather than only looking at annotations in source code.

## 7. Do not confuse annotation detection with method invocation

Suppose Spring reads:

```java
@ManagedOperation
public void retryFailed() { ... }
```

However, the object invoked by `MBeanServer` is a JDK proxy exposing only `OrderService` without `retryFailed`. Several outcomes can occur depending on the Spring version and configuration:

1. The exporter does not include that operation in `MBeanInfo`.
2. The exporter builds metadata containing the operation, but invocation fails because the method cannot be resolved on the exposed object.
3. The exporter requires a different proxy/adapter handling approach before registration.
4. The exporter registers the target instead of the proxy; the operation runs, but Spring advice may be bypassed.

You cannot draw an accurate conclusion merely from saying "the class has the annotation". Check `isRegistered`, `MBeanInfo.getOperations()`, and `MBeanServer.invoke` execution in order.

## 8. Using a management adapter to decouple AOP and JMX

A more resilient design is a **JMX adapter** that receives a Spring-injected service interface.

Business interface:

```java
package com.example.orders;

public interface OrderService {
    int pendingCount();
    void retryFailed(int maxCount);
}
```

Implementation:

```java
package com.example.orders;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DefaultOrderService implements OrderService {

    @Override
    public int pendingCount() {
        return 10;
    }

    @Override
    @Transactional
    public void retryFailed(int maxCount) {
        // Business processing inside a transaction.
    }
}
```

Management adapter:

```java
package com.example.orders.management;

import com.example.orders.OrderService;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.orders:type=Processor,name=Main",
    description = "Order processing statistics and bounded retry operations"
)
public class OrderManagementAdapter {

    private final OrderService orderService;

    public OrderManagementAdapter(OrderService orderService) {
        this.orderService = orderService;
    }

    @ManagedAttribute(
        description = "Number of orders pending in this application instance"
    )
    public int getPendingCount() {
        return orderService.pendingCount();
    }

    @ManagedOperation(
        description = "Retries at most maxCount failed orders"
    )
    public void retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException("maxCount must be 1..100");
        }
        orderService.retryFailed(maxCount);
    }
}
```

Here:

- The adapter carries the JMX metadata.
- The adapter usually does not need to be wrapped by its own AOP proxy.
- The service can be a JDK proxy exposing only `OrderService`, matching the methods the adapter needs to call.
- Transaction advice on the service is executed when the adapter calls through the service proxy, provided transaction infrastructure is configured and the call is not bypassed.
- The management interface publishes only the necessary state and operations without exposing the entire business API.

## 9. Configuring Spring to export the adapter

A Java configuration example:

```java
package com.example.orders.management;

import com.example.orders.OrderService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxManagementConfiguration {

    @Bean
    public OrderManagementAdapter orderManagementAdapter(
            OrderService service) {
        return new OrderManagementAdapter(service);
    }
}
```

If the application uses component scanning or `@SpringBootApplication`, ensure the service implementation is registered in the `ApplicationContext` and that transaction/security infrastructure (if needed) is configured separately.

Do not use `@EnableMBeanExport` simultaneously with a manual `MBeanExporter` registering **the same ObjectName** unless you have a clear deduplication design. Two exporters can cause `InstanceAlreadyExistsException` or apply registration policies that produce unexpected results.

For XML-based Spring, `<context:mbean-export/>` enables the corresponding annotation export mechanism, but does not automatically resolve mismatches between target methods and interfaces exposed by a proxy.

## 10. When should you keep annotations directly on the service?

You do not always have to create an adapter.

If:

- The component is small and serves only management purposes.
- There are no complex AOP proxies.
- The management interface is a clear part of the public contract.
- The management methods can be invoked through the proxy under the mechanism in use.

then placing `@ManagedResource` and method annotations on the bean can be a simple choice.

However, if the service has multiple transaction/security advices, changes interfaces frequently, or has management operations with side effects, an adapter usually reduces coupling and risk.

There is no rule that "JDK proxies always lose annotations" or "CGLIB is always safe": you need to examine precisely how Spring resolves metadata and which class/interfaces the exporter actually sees.

## 11. ObjectNamingStrategy and proxy classes

Another source of errors is how the ObjectName is generated.

If the naming strategy uses `bean.getClass().getName()`, a class-based proxy may generate a name containing a dynamic suffix:

```text
com.example.orders:type=OrderServiceImpl$$SpringCGLIB$$...
```

Such names are unstable or unhelpful for dashboards. With a JDK proxy, the runtime class may look like `jdk.proxy2.$Proxy...`, which is even less suitable as a management identifier.

You should assign a clear logical name:

```text
com.example.orders:type=Processor,name=Main
```

or use a metadata naming strategy that takes the name from `@ManagedResource(objectName=...)`, if the exporter configuration supports it.

Separating **business identity** from the **runtime proxy class** avoids ObjectName changes when AOP advice or proxy modes change.

## 12. Checking the actual proxy created

In integration tests or diagnostic logs:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("orderService");

System.out.println(bean.getClass());
System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

You should record both the proxy type and the interfaces the bean actually exposes:

```java
for (Class<?> iface : bean.getClass().getInterfaces()) {
    System.out.println(iface.getName());
}
```

For a JDK proxy, the interface list is direct evidence of which methods can be invoked through the proxy type. For a class-based proxy, the method set is usually broader, though advice limitations still apply.

Do not write a test that only asserts `isAopProxy(bean)` and conclude that JMX definitely recognizes the annotations. Dedicated JMX tests are still required.

## 13. Inspecting MBeanInfo of the exported resource

Use `MBeanServer` to inspect what the Spring infrastructure actually published:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=Processor,name=Main"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("Expected MBean not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

System.out.println("MBean: " + info.getClassName());

for (var attr : info.getAttributes()) {
    System.out.println(
        "Attribute " + attr.getName() + " : " + attr.getType()
    );
}

for (var operation : info.getOperations()) {
    System.out.println(
        "Operation " + operation.getName()
        + " : " + operation.getReturnType()
    );
}
```

This code assumes the Spring exporter uses the platform MBeanServer; if the application uses a custom server, you must obtain the right server instance.

If the MBean exists but is missing `PendingCount` or `retryFailed`, possible causes include:

- The annotations were not recognized by the metadata source.
- The bean was not autodetected by the exporter.
- The proxy interface does not contain the method, or the method could not be introspected as expected.
- The exporter uses an assembler other than the annotation-based assembler.
- The exporter registered a different bean under the same ObjectName.

`MBeanInfo` is proof of the actual metadata, not merely reflection on the source class.

## 14. Testing AOP + JMX with a Spring context

An integration test can:

1. Enable AOP on a service.
2. Register the service bean and the JMX management adapter.
3. Enable `@EnableMBeanExport`.
4. Initialize the `ApplicationContext`.
5. Verify that the service is the expected JDK/CGLIB proxy.
6. Verify that the MBean is registered and its metadata is complete.
7. Invoke the operation via `MBeanServer.invoke`.
8. Verify that the service advice/side effect executed.
9. Close the context and verify cleanup.

JUnit 5 example with the adapter configuration:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class JmxAopIntegrationTest {
    @Test
    void exposesAdapterAndInvokesService() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.orders:type=Processor,name=Main"
        );

        try (var context = new AnnotationConfigApplicationContext(
                JmxManagementConfiguration.class,
                ServiceConfiguration.class)) {

            assertTrue(server.isRegistered(name));

            Object pending =
                server.getAttribute(name, "PendingCount");
            assertEquals(10, pending);

            server.invoke(
                name,
                "retryFailed",
                new Object[] { 5 },
                new String[] { "int" }
            );

            // In a real test, assert a side effect/counter
            // proving the service was invoked through the proxy.
        }
    }
}
```

`ServiceConfiguration` in the example is the application's test configuration containing the service bean and AOP infrastructure. If `@Transactional` is genuinely tested, a properly configured transaction manager is required; a single annotation alone does not guarantee transaction advice is applied.

For isolated testing, you can configure the exporter to use `MBeanServerFactory.newMBeanServer` and inject that server instead of the platform server; make sure the annotation exporter uses the chosen test server.

## 15. Common failure scenarios

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Bean has `@ManagedResource` but MBean is missing | Exporter/scanning inactive or proxy metadata not detected | Check context, annotation exporter, `MBeanInfo` |
| MBean exists but operation is missing | Method not in JDK proxy interface or metadata assembler failed to read it | Check interfaces, target method, assembler |
| `ReflectionException` when invoking operation | JMX signature mismatch or proxy does not expose method | Retrieve signature from `MBeanOperationInfo` |
| `NotCompliantMBeanException` error | Standard MBean/ModelMBean export approach incompatible with object or proxy | Use an appropriate annotation assembler/adapter/StandardMBean |
| Operation runs but transaction has no effect | Exported target bypassing proxy or self-invocation | Export an adapter that calls the service proxy |
| ObjectName changes after enabling AOP | Naming based on runtime proxy class | Use a stable logical/metadata naming |
| Client reads the wrong MBean | Two exporters or contexts using incorrect names | Check `ObjectName` and registration owner |
| JConsole does not display expected metadata | Client connected to wrong server or exporter uses different metadata | Check MBeanServer, class, `MBeanInfo` |

## 16. Design checklist when combining Spring AOP and JMX

Before exposing a bean via JMX:

- Determine whether the actual bean is a target or a Spring AOP proxy.
- For JDK proxies, verify that management methods belong to an interface exposed by the proxy or use an adapter.
- For class-based proxies, review `final`/`private` methods and the advice path.
- Verify that an annotation-based metadata assembler is actually configured.
- Keep the ObjectName stable, independent of the proxy class name.
- Do not expose all public methods solely for convenience.
- For sensitive operations, check authorization outside of JMX metadata.
- Inspect `MBeanInfo` and invoke operations on a real test server.
- Ensure service advice is applied along the JMX invocation path.
- Avoid duplicate exporter registrations and clean up MBeans according to lifecycle.

## 17. Practice exercises

1. Create an `OrderService` interface with `getPendingCount`, and an implementation class that also has `retryFailed` annotated with `@ManagedOperation`. Enable JDK proxies and observe the difference in the method set.
2. Switch to class-based proxies and inspect `MBeanInfo` again; explain why the result may change.
3. Use `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy`, and `AopProxyUtils.ultimateTargetClass` in a diagnostic test.
4. Create a JMX adapter receiving an `OrderService` proxy, exposing one attribute and one operation. Verify the call through `MBeanServer`.
5. Enable an advisor that counts `retryFailed` invocations. Compare calling through the adapter proxy versus calling the target directly.
6. Intentionally set a naming strategy based on `bean.getClass().getName()`, observe the name changing when AOP is enabled, and then fix it with a logical ObjectName.
7. Write an integration test verifying MBean registration, metadata, invocation, and unregistration when the context closes.

## 18. Self-check questions

- Why might `bean.getClass()` not be the class containing `@ManagedResource`?
- How do JDK proxies and class-based proxies differ in the set of exposed methods?
- Why does finding annotation metadata not guarantee that a method can be invoked via JMX?
- In what cases can exporting the target instead of the proxy cause transaction/security advice to be lost?
- Why should a JMX management adapter be used for services with multiple AOP advices?
- Does `@EnableMBeanExport` automatically create a transaction manager or protect JMX operations?
- What is the accurate way to inspect exported operations?
- What risks does a naming strategy based on the runtime proxy name carry across deployments?

**Remember:** When Spring AOP creates a proxy, the runtime class and method surface may differ from the target class containing JMX annotations. Distinguish **metadata discovery** from **method invocation**, inspect JDK/class-based proxies, keep the ObjectName independent of the proxy class, and prefer a management adapter calling through the Spring service proxy when transaction/security advice must be preserved.
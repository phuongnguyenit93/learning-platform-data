# Target-class proxies and the proxy-target-class flag in Spring AOP with JMX

## 1. Objectives

Spring AOP uses proxies to apply cross-cutting behaviors such as transactions, security, logging, caching, or metrics around method invocations. In a Spring Framework JMX application, a bean exported as an MBean may also already be an **AOP proxy**. In that case, you need to understand what kind of proxy it actually is, whether it exposes interfaces or the implementation class, and how Spring JMX determines which methods to expose for management.

This topic explains the difference between a **JDK dynamic proxy (interface-based)** and a **class-based proxy (commonly using CGLIB)**, the meaning of `proxy-target-class`, and its impact on `MBeanExporter`, `@ManagedResource`, assemblers, naming strategies, and method visibility in JMX.

**Key takeaway:** `proxy-target-class=true` instructs the relevant AOP proxy creation mechanisms to prefer proxies based on the **target class** rather than proxying only by interfaces when appropriate. It is **not** a switch that guarantees every target method is exported via JMX, nor does it automatically create MBeans or alter JMX connector authorization.

## 2. Two common Spring AOP proxy types

### 2.1. JDK dynamic proxy: proxying via interfaces

Suppose a service has an interface:

```java
public interface PaymentService {
    void processPayment(String paymentId);
    long getProcessedCount();
}
```

Implementation:

```java
@Service
public class DefaultPaymentService implements PaymentService {
    @Override
    public void processPayment(String paymentId) {
        // Perform business logic.
    }

    @Override
    public long getProcessedCount() {
        return 42L;
    }

    public void clearInternalCache() {
        // Method not present on PaymentService.
    }
}
```

When Spring creates a **JDK dynamic proxy**, the proxy object primarily implements the configured interfaces. With `PaymentService`, callers can invoke `processPayment` and `getProcessedCount` through the interface, but cannot treat the proxy as an instance of `DefaultPaymentService` via normal casting.

```text
Caller -> JDK Proxy implements PaymentService
                    |
                    v
          DefaultPaymentService target
```

The `clearInternalCache()` method belongs to the concrete class and is not defined in `PaymentService`; a JDK proxy representing only its interfaces does not allow clients to invoke this method directly via the proxy type.

### 2.2. Target-class proxy: proxying via concrete class

With a class-based proxy, Spring typically creates a proxy subclass using CGLIB. Such a proxy can preserve type compatibility with the concrete target class, allowing injection by concrete type in many cases.

```text
Caller -> CGLIB subclass of DefaultPaymentService
                    |
                    v
           DefaultPaymentService target
```

Class-based proxies have notable limitations:

- `final` classes cannot be subclassed to create a class-based proxy.
- `final` or `private` methods cannot be overridden for subclass-style advice.
- Methods that cannot be overridden due to access scope may also not be advised.
- Self-invocation (`this.someMethod()`) normally does not pass through the AOP proxy, so advice may be skipped.
- Proxy creation can interact with constructors, visibility, the module system, and other frameworks.

**Proxying by class does not mean the entire target class receives AOP advice**: the ability to intercept calls still depends on advisors, pointcuts, method overridability, and the call path.

## 3. What does proxy-target-class mean?

In Spring configuration, the `proxy-target-class` attribute indicates that class-based proxies should be preferred when creating AOP proxies for the configured mechanism.

XML example:

```xml
<aop:config proxy-target-class="true">
    <!-- advisor / aspect configuration -->
</aop:config>
```

With annotation-driven AOP:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
}
```

Note that the name in the Java annotation is **`proxyTargetClass`** in camelCase, while in XML you commonly see **`proxy-target-class`**. Both configure the same concept, but are applied through different entry points.

When set to `false` (or when class proxying is not forced), Spring can use a JDK proxy if the target has suitable interfaces; if there is no suitable interface, it can use a class-based proxy. When `true`, the target class is preferred as the proxy type, though limitations still apply if the target cannot be subclassed.

**Configuration scope:** elements such as `<aop:config>`, `<aop:aspectj-autoproxy>`, and `<tx:annotation-driven>` can share a common auto-proxy creation mechanism in the `ApplicationContext`; setting class proxying in one place can affect other AOP proxies created by the same infrastructure. Do not assume the flag affects only a single bean.

## 4. Spring Boot and proxy defaults

In Spring Boot, AOP defaults can be adjusted by Boot auto-configuration. Some Spring Boot versions prefer class-based proxies in AOP configuration, and provide a property such as `spring.aop.proxy-target-class` to control the choice.

```properties
spring.aop.proxy-target-class=true
```

Or:

```properties
spring.aop.proxy-target-class=false
```

Do not infer that plain Spring Framework automatically reads Spring Boot properties. In plain Framework, you must configure it via the corresponding AOP infrastructure, annotations, or XML. Also check the Boot/Framework version and the transaction, security, and caching components in use, because not all proxies are created by the same mechanism or governed by the same option.

## 5. Where does JMX relate to AOP proxies?

JMX does not create AOP proxies itself. However, a Spring-managed bean being exported may already have been AOP-proxied beforehand:

```text
ApplicationContext
     |
     +-- PaymentService bean
          |
          +-- AOP auto-proxying
          |      +-- JDK dynamic proxy
          |      +-- class-based proxy
          |
          v
     MBeanExporter sees bean
          |
          +-- chooses MBean interface / assembler
          +-- assigns ObjectName
          v
     MBeanServer
          |
          v
     JConsole / VisualVM / JMX client
```

When `MBeanExporter` receives a proxy instead of the raw target, **the class and interfaces visible on the proxy** may differ from the target implementation. This affects:

- Recognizing the bean as a Standard MBean/MXBean or a POJO requiring adaptation.
- Locating `@ManagedResource`, `@ManagedAttribute`, and `@ManagedOperation` on the target class or methods.
- Mapping selected methods to operations/attributes actually callable on the proxy.
- Checking signatures and return types, especially when a concrete method is not in the JDK proxy interface.
- Ensuring AOP advice (such as transactions/authorization) is still applied on the JMX call path.

There is no general rule that turning on `proxy-target-class=true` is enough to fix all JMX issues. You must inspect the **specific export path**, assembler, AOP proxy kind, and actual `MBeanInfo`.

## 6. Example of a bean with both a business interface and JMX metadata

Suppose the implementation has management annotations:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Service;

@Service
@ManagedResource(
    objectName = "com.example.payment:type=PaymentMonitor,name=Main",
    description = "Payment state and management operations"
)
public class DefaultPaymentService implements PaymentService {
    private volatile boolean paused;

    @Override
    public long getProcessedCount() {
        return 42;
    }

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void requestResume() {
        paused = false;
    }

    @Override
    public void processPayment(String id) {
        // Payment processing logic.
    }
}
```

The `PaymentService` interface publishes only business methods. If a JDK proxy implements only `PaymentService`, the `isPaused()` and `requestResume()` methods are not on that proxy's public API. With a class proxy, concrete methods may remain on the proxy type; however, Spring JMX must still select the right metadata and target invocation strategy.

**A design that is usually easier to control:** create a separate management adapter, avoiding forcing the business service to act as both a JMX endpoint and an AOP target with an incompatible set of interfaces.

## 7. Separate management adapter: a clear choice

Example:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.payment:type=PaymentMonitor,name=Main"
)
public class PaymentManagement {
    private final PaymentService service;
    private final PaymentStateView state;

    public PaymentManagement(
            PaymentService service, PaymentStateView state) {
        this.service = service;
        this.state = state;
    }

    @ManagedAttribute(description = "Is payment processing paused?")
    public boolean isPaused() {
        return state.isPaused();
    }

    @ManagedAttribute(description = "Number of processed payments")
    public long getProcessedCount() {
        return service.getProcessedCount();
    }

    @ManagedOperation(description = "Request resuming payment processing")
    public void requestResume() {
        state.requestResume();
    }
}
```

`PaymentStateView` is an abstraction provided by the application to read/control state; in a real project, a corresponding interface/bean must be defined. `PaymentManagement` is a small bean designed specifically for JMX; it delegates to the service. When the business service uses a JDK proxy, the adapter interacts only with methods declared in the `PaymentService` interface, so it does not depend on the concrete class for business calls.

Advantages:

1. The MBean surface is selected precisely via annotations.
2. Not all business methods are forced to become public JMX operations.
3. AOP advice on the business service can still operate when the adapter calls through the injected Spring proxy.
4. The management contract stays stable even when the implementation class is refactored.
5. It is easy to enforce permissions on operations with side effects.

## 8. Enabling annotation-driven JMX export

In the Spring Framework:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {
}
```

With `@ManagedResource` and the metadata assembler configured by Spring, eligible management beans are exported according to the corresponding naming/metadata.

**Important point:** `@EnableMBeanExport` does not mean every Spring bean is converted into an MBean and does not automatically force AOP class proxies. It configures the JMX exporter; the AOP proxy mode must be examined separately.

## 9. Why do JDK proxies sometimes cause JMX export errors?

A JDK dynamic proxy exposes only interfaces. If `MBeanExporter` or a manually configured assembler needs to reflect on a method that exists only on the target class, metadata resolution or invocation may not match the proxy class.

Example:

```java
public interface TaskService {
    int getPendingTasks();
}

public class DefaultTaskService implements TaskService {
    @Override
    public int getPendingTasks() { return 5; }

    public void forceCleanup() { /* ... */ }
}
```

If `DefaultTaskService` is proxied with a JDK proxy of `TaskService`, the proxy object does not have the `forceCleanup()` public method under that interface. An MBean assembler expecting to export `forceCleanup()` from the target class may lack a corresponding invocation path through the proxy in every configuration.

Reasonable options:

- Use a dedicated management interface and export supported interfaces/methods.
- Use a management adapter that delegates through the service's interface.
- Configure a class-based proxy when genuinely needed and the target can be subclassed.
- Inspect and fix the `MBeanInfoAssembler`, naming strategy, or exported target object instead of only flipping the proxy flag.
- Ensure JMX metadata is read from the proper target class, not merely from the proxy class.

You should not assume that making a method `public` on the implementation is sufficient if the Spring proxy still implements only the interface.

## 10. The proxy-target-class flag does not determine the JMX management interface

You must separate three concepts:

| Concept | Role |
| --- | --- |
| `proxy-target-class` / `proxyTargetClass` | Determines the AOP proxy type created by the corresponding Spring mechanism |
| `MBeanInfoAssembler` / `@ManagedAttribute` / `@ManagedOperation` | Determines which attributes/operations are published |
| `ObjectName` / `ObjectNamingStrategy` | Determines which MBean is registered and under what name JMX clients find it |

For example, enabling a class proxy does not automatically turn `deleteAll()` into a JMX operation if the annotation-based assembler selects only certain methods. Conversely, using `SimpleReflectiveMBeanInfoAssembler` can expose many public methods even when the AOP proxy has a different shape based on interfaces/classes.

To know the actual contract, you must read `MBeanInfo` after export rather than guessing from the AOP configuration.

## 11. Example of the same code with different proxy configurations

### 11.1. JDK interface proxy configuration

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class InterfaceProxyConfig {}
```

If a bean has suitable interfaces, Spring AOP can typically use a JDK dynamic proxy; the bean retrieved from IoC may be a `java.lang.reflect.Proxy` instance implementing the interfaces, not a subclass of the target concrete class.

### 11.2. Class proxy configuration

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class ClassProxyConfig {}
```

Spring AOP can create a subclass proxy. For an advised public, non-final method, a call through the proxy can run advice and then the target method.

**Avoid enabling both conflicting configurations in the same context for direct comparison**. For practical testing, run two separate test contexts/applications with explicit configurations.

## 12. Determining the proxy kind with Spring AopUtils

To observe what kind of proxy an injected object is:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("paymentService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

`AopUtils` is a Spring AOP support API. The snippet requires the `spring-aop` module on the classpath and an initialized `ApplicationContext`. If no advice applies to the bean, it may not be proxied even when `proxyTargetClass` is enabled: the flag chooses **the proxy type when a proxy needs to be created**, not a command forcing every bean to become a proxy.

With multiple nested proxy layers or a custom `TargetSource`, you must understand the actual invocation path; do not merely read `bean.getClass()` and assume all JMX metadata comes from that class.

## 13. Exporting an AOP proxy directly: points to consider

When you want to export an AOP-proxied bean, check:

1. **Metadata source:** does the assembler read `@ManagedResource` and annotations from the proper target class?
2. **Proxy interface:** are the getters/operations to expose present on the proxy type?
3. **AOP advice:** do JMX calls to the MBean actually pass through the proxy/advice as intended?
4. **Target object:** does the exporter manage the proxy or the raw target? Avoid intentionally unwrapping the proxy and silently losing security/transaction advice.
5. **Method visibility:** are final/private methods advised by the proxy?
6. **ObjectName:** is it stable, unique, and pointing to the right MBean in `MBeanServer`?
7. **Lifecycle:** does the exporter consistently register/unregister beans in the same context?

If JMX calls the implementation object directly instead of the AOP proxy carrying security advice, do not assume AOP method-level authorization is automatically enforced. For sensitive management operations, authorization checks at the connector/layer and validation inside the operation are required.

## 14. Distinguishing a JMX proxy from an AOP proxy

Spring has two different concepts:

**AOP proxy:** the client calls a Spring bean, and the proxy intercepts the call according to advisors/pointcuts before forwarding to the target.

**JMX client proxy:** Spring's `MBeanProxyFactoryBean` creates a Java proxy for an MBean; it uses `MBeanServerConnection`, `ObjectName`, and a management interface to translate calls into JMX operations/attributes.

```text
Business call
  -> AOP proxy -> target bean

JMX client call
  -> MBeanProxyFactoryBean proxy
  -> MBeanServerConnection -> ObjectName -> MBean
```

`proxy-target-class` primarily governs **how AOP proxies are created**. It is not a parameter deciding `ObjectName` or the JMX client proxy type of `MBeanProxyFactoryBean`.

## 15. Interface-based management contracts and class proxies

An application can use a Standard MBean interface:

```java
public interface QueueManagementMBean {
    int getQueueDepth();
    void requestPause();
}
```

```java
public class QueueManagement implements QueueManagementMBean {
    @Override
    public int getQueueDepth() { return 5; }

    @Override
    public void requestPause() { /* ... */ }
}
```

This interface-based MBean contract exists independently of whether AOP is present. If the exporter needs to create an AOP proxy for `QueueManagement`, choosing JDK vs. class proxy can affect the intermediate object type, yet the interface still clearly describes the management API. This is why a dedicated management interface or adapter is usually safer when the application has many advices.

## 16. When to consider enabling proxyTargetClass=true?

Consider it when:

- The application needs proxies compatible with concrete classes for injection/lookup by class and does not want to depend on interfaces.
- AOP advice applies to methods not on an interface, and those methods can be overridden.
- Another framework integration requires seeing target-class methods and has been verified to be compatible with class proxies.
- You understand the limitations of final methods/classes and classes with special constructors/visibility.

Do not enable it merely because:

- You want every Java method to automatically become a JMX operation.
- You want to bypass JMX connector security.
- You want to fix a non-existent `ObjectName`.
- You want proxies to intercept private/final methods.
- You want to resolve `MBeanServer`/registration policy conflicts.

Changing the proxy mode can affect dependency injection, AOP advice behavior, and other beans in the context; you must test with the real application configuration.

## 17. Inspecting MBeanInfo to see the exported JMX API

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.MBeanInfo;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.payment:type=PaymentMonitor,name=Main"
);

MBeanInfo info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "Attribute %s: readable=%s writable=%s%n",
        attr.getName(), attr.isReadable(), attr.isWritable()
    );
}

for (var operation : info.getOperations()) {
    System.out.println("Operation " + operation.getName());
}
```

The snippet assumes the MBean is registered in the platform `MBeanServer`. If the exporter uses a dedicated server, you must obtain that exact server. `MBeanInfo` shows the contract seen by JMX clients; this is how to determine the actual attributes/operations after annotations, the assembler, and the AOP proxy mode all take effect.

## 18. Common errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| JMX does not see `@ManagedAttribute` on target | Exporter/metadata source cannot resolve annotation from target class or proxy exposes interfaces only | Check AOP proxy kind, annotation assembler, target metadata |
| Casting Spring bean to concrete class fails | Bean is a JDK proxy implementing interfaces only | Inject the interface or consider a class proxy |
| Class proxy enabled yet final method not intercepted | CGLIB cannot override final methods | Move logic to a proxyable method or another mechanism |
| Transaction/security advice does not run when JMX invokes operation | Call path skips proxy advice or self-invocation | Check exported target object and call path |
| JMX exporter reports non-compliant MBean | Proxy object/interface does not satisfy export path | Use management adapter/interface or proper metadata assembler |
| Bean appears but unexpected operations are present | Reflective assembler exposes public methods | Choose annotation/interface/allowlist assembler |
| Bean disappears after enabling AOP | ObjectName, exporter, or metadata mismatch | Check registration, `MBeanInfo`, startup errors |
| Enabling `proxyTargetClass` causes startup errors | Final class or incompatible visibility/construction | Change proxy strategy or refactor target |

## 19. Security safety and performance

JMX is typically a high-privilege management surface. AOP proxy mode does not replace security policy:

- Do not export data-mutating APIs beyond operational needs.
- Do not trust that method-level Spring Security is always enforced if JMX calls along a path bypassing the AOP proxy.
- Always validate parameters for operations with impact.
- Limit sensitive information exposed in management attributes and notifications.
- Protect remote JMX connectors with appropriate network policies, authentication, TLS, and authorization.
- Avoid heavy work in JMX getters, since monitoring tools may poll frequently.
- Keep `ObjectName` and MBean contracts stable when changing proxies/assemblers.

With class proxies, applied advice can change timing, exceptions, and transaction boundaries. Do not invoke long-running JMX operations on a critical path without resource limits.

## 20. Mental model

```text
                   Spring target bean
                          |
                AOP infrastructure
                          |
         proxyTargetClass = false / true
                          |
                  +-------+-------+
                  |               |
              JDK proxy      Class proxy
             (interfaces)    (subclass)
                  |               |
                  +-------+-------+
                          |
                     MBeanExporter
                          |
                MBeanInfoAssembler
                          |
                       MBeanServer
                          |
                      JMX clients
```

**Conclusion:** `proxy-target-class` controls **the Spring AOP proxy type** under the corresponding configuration mechanism, rather than directly deciding permissions or the list of JMX attributes/operations. JDK proxies fit interface contracts, while class-based proxies can preserve concrete target APIs yet remain constrained by final/private methods. When combining Spring AOP and JMX, prefer a management interface or small adapter, configure the assembler explicitly, and verify `MBeanInfo` along with the actual advice execution path.

# Identifying Bean Proxies and Injectable Reference Types

In Spring Boot, a bean can be managed through a **proxy** so Spring can apply AOP, transactions, caching, async execution, or special lifecycle behavior. In that case, the object a service receives via dependency injection **is not necessarily a direct instance of the class written in source code**.

This raises a practical question: if Spring creates a bean from class `PaymentService`, can you declare a constructor accepting `PaymentService`, or should you only accept interface `PaymentOperations`? Why does an interface dependency inject cleanly while a class dependency throws an error, even when the bean name is completely right?

To answer that, distinguish clearly between:

- **Target object:** the original business object, such as `PaymentService`.
- **Proxy object:** the intermediary object that receives calls, applies advice, and forwards to the target using the appropriate mechanism.
- **Bean reference:** the actual object supplied to the client by the application context. This reference may point to a proxy.
- **Dependency type:** the type requested by a constructor or field. This type must be compatible with the injected object, not merely with the target class on paper.

Two key proxy strategies:

1. **JDK dynamic proxies** rely on interfaces; the proxy is usually not an instance of the concrete target class.
2. **Class-based proxies (CGLIB)** are generated as subclasses of the target class; the proxy is usually assignable to both the concrete class and any interfaces that class implements.

Understanding this mechanism lets you identify bean proxies accurately, choose compatible reference types, and avoid confusing dependency injection errors.

## 1. Where does the proxy sit in the method call flow?

Suppose there is a payment operation:

```java
package com.example.shop.payment;

public interface PaymentOperations {
    void charge(String orderId);
}
```

Implementation:

```java
package com.example.shop.payment;

import org.springframework.stereotype.Service;

@Service
public class PaymentService implements PaymentOperations {

    @Override
    public void charge(String orderId) {
        System.out.println("Charging order: " + orderId);
    }
}
```

An injected client:

```java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }

    public void checkout(String orderId) {
        payments.charge(orderId);
    }
}
```

Without a proxy, the call flow can be:

```text
CheckoutService
      |
      v
PaymentService.charge(...)
```

With a Spring AOP proxy:

```text
CheckoutService
      |
      | payments.charge(...)
      v
Payment proxy                     <-- injected reference
      |
      +--> Transaction / logging / cache / security advice
      |
      v
PaymentService target             <-- business object
      |
      v
charge(orderId)
```

Depending on the advice, some calls can return a result from cache without invoking the target, or be dispatched to an executor. The diagram is a general model, not a fixed description of every interceptor.

### 1.1. Proxies help separate cross-cutting concerns

Tasks like transactions, logging, metrics, and security appear across many services. If every method writes its own wrapping logic, business code gets duplicated.

Proxies allow frameworks or aspects to supply additional behavior at call boundaries.

Examples of annotations commonly related to proxies:

```java
@Transactional
public void transferMoney() {
    // Money transfer business logic
}
```

```java
@Cacheable("products")
public Product findProduct(String sku) {
    // Product query business logic
}
```

```java
@Async
public CompletableFuture<Void> sendEmail(String email) {
    // Email sending business logic
    return CompletableFuture.completedFuture(null);
}
```

These annotations require their corresponding mechanisms to be enabled and configured appropriately. Merely adding an annotation **does not guarantee** a proxy is created or advice always runs.

### 1.2. Bean definition, target, and proxy are not identical

| Component | Role |
| --- | --- |
| `BeanDefinition` | Metadata on how Spring registers and creates the bean |
| Target class | Business type, such as `PaymentService` |
| Target instance | Instance holding business state and logic |
| Proxy instance | Object created to apply intermediary behavior |
| Bean name | Identifier in the container, e.g. `paymentService` |
| Dependency type | Type requested by the client: `PaymentOperations` or `PaymentService` |

With normal AOP proxies, the bean name can remain `paymentService` even though the returned runtime object is a proxy.

Do not assume Spring creates two independent business beans named `paymentService` and `paymentServiceProxy`; Spring normally exposes the proxy under the wrapped object's bean name. Some scoped-proxy mechanisms keep an internal bean definition for the target, though that is an infrastructure detail.

## 2. When does Spring create a proxy?

Proxies typically appear when a bean is processed by an infrastructure mechanism, for example:

- An AOP advisor/pointcut matches the bean and methods.
- Transaction management handles `@Transactional`.
- Cache infrastructure handles `@Cacheable`, `@CachePut`, or `@CacheEvict`.
- Async method execution handles `@Async`.
- Scoped proxies serve request/session-scoped beans.
- Lazy-resolution proxies serve `@Lazy` dependencies.

A bean bearing only `@Service` **is not by default an AOP proxy**.

A class instantiated with:

```java
PaymentService service = new PaymentService();
```

does not automatically receive container proxies from Spring.

In a typical bean lifecycle, Spring creates the target, performs dependency injection and initialization, and then bean post-processors can supply a proxy reference to clients.

```text
BeanDefinition
      |
      v
Create and initialize target
      |
      v
BeanPostProcessor / auto-proxy creator
      |
      +--> No proxy needed -> Expose target
      |
      +--> Proxy needed ------> Expose proxy
                                      |
                                      v
                                 Inject into client
```

In practice, early references, scoped targets, factory beans, and other internal steps also exist. The model above highlights why **a bean's runtime type may differ from its target class**.

## 3. JDK dynamic proxies

JDK dynamic proxies use Java Reflection Proxy to create an object implementing one or more interfaces. With Spring AOP, this is a suitable option when a bean has a business interface and configuration prefers interface-based proxies.

Suppose:

```java
public interface NotificationSender {
    void send(String message);
}
```

```java
@Service
public class EmailSender implements NotificationSender {

    @Override
    public void send(String message) {
        System.out.println("Email: " + message);
    }
}
```

Type relationships:

```text
                  NotificationSender
                    ^          ^
                    |          |
              implements   implements
                    |          |
                    |          |
               EmailSender   JDK Proxy
                   ^            |
                   |            |
                target  <-------+ call forwarded
```

**The JDK proxy implements `NotificationSender`, but does not extend `EmailSender`.**

### 3.1. Why does injecting the interface succeed?

```java
@Service
public class AlertService {

    private final NotificationSender sender;

    public AlertService(NotificationSender sender) {
        this.sender = sender;
    }
}
```

The dependency requests the interface. If the bean is exposed via a JDK proxy implementing that interface, the JVM allows assigning:

```java
NotificationSender reference = proxy;
```

The remaining condition is that Spring finds a single suitable candidate under autowiring rules.

### 3.2. Why can injecting the concrete class fail?

```java
@Service
public class AlertService {

    private final EmailSender sender;

    public AlertService(EmailSender sender) {
        this.sender = sender;
    }
}
```

The constructor requires `EmailSender`, yet the exposed object is a JDK dynamic proxy, not an instance of `EmailSender`.

The equivalent assignment:

```text
EmailSender reference = object_of_JdkProxyType
```

is not type-compatible.

Spring may report a missing matching dependency or `BeanNotOfRequiredTypeException`, depending on how the bean is looked up and where the failure occurs. The error message usually shows the required type is the implementation class while the exposed object has a generated proxy type.

### 3.3. Casting does not solve it

Wrong:

```java
NotificationSender sender =
        context.getBean(NotificationSender.class);

EmailSender implementation = (EmailSender) sender;
```

If `sender` is a JDK proxy, casting can throw `ClassCastException`. The Java runtime does not automatically unwrap proxies to yield the target class.

Design clients to use methods declared by the interface. If a client needs another method, extend the contract with an appropriate interface instead of casting.

### 3.4. Methods existing only on the implementation

Example:

```java
public class EmailSender implements NotificationSender {

    @Override
    public void send(String message) {
        System.out.println(message);
    }

    public void rebuildTemplates() {
        System.out.println("Rebuild templates");
    }
}
```

`rebuildTemplates()` is not on `NotificationSender`, so clients holding the interface cannot call it directly.

If this capability must be used externally, declare another interface:

```java
public interface TemplateMaintenance {
    void rebuildTemplates();
}
```

And have the implementation implement both `NotificationSender` and `TemplateMaintenance`. When the proxy exposes both interfaces, clients can inject whichever contract they need.

## 4. Class-based proxies (CGLIB)

Spring can also create class-based proxies by generating a **subclass** of the target class, commonly called a CGLIB proxy.

Type relationship example:

```text
NotificationSender
       ^
       | implements
   EmailSender
       ^
       | extends
   EmailSender$$SpringCGLIB$$...
       ^
       |
Injected reference
```

When a class-based proxy can be created, the proxy object both implements `NotificationSender` and is an instance of `EmailSender` via Java inheritance.

### 4.1. Both injection styles can work

Injecting by interface:

```java
public AlertService(NotificationSender sender) {
    this.sender = sender;
}
```

Injecting by implementation class:

```java
public AlertService(EmailSender sender) {
    this.sender = sender;
}
```

With a class-based proxy extending `EmailSender`, both types are assignable.

However, injecting by implementation class couples the client to a specific class. If AOP configuration changes to JDK proxies or the implementation is swapped for another class, the client may need changes.

### 4.2. Important limitations

Class-based proxies require the ability to subclass and override eligible methods:

- **Final classes** cannot be subclassed.
- **Final methods** cannot be overridden to attach advice under normal subclass mechanics.
- **Private methods** cannot be overridden from a subclass.
- Certain methods whose visibility disallows overriding cannot be intercepted as expected either.
- Internal calls via `this` do not automatically cross the proxy boundary.

Example of a class unsuitable for CGLIB subclassing:

```java
public final class FinalPaymentService {
    public void pay() {
        System.out.println("Paid");
    }
}
```

Example of a final method:

```java
public class InventoryService {
    public final void reserve(String sku) {
        System.out.println("Reserve " + sku);
    }
}
```

Spring AOP class-based proxies cannot override final methods to apply advice in the normal way.

### 4.3. Being a proxy does not mean every method is advised

Suppose `InventoryService` has `reserve()` and `viewCatalog()`, but the pointcut matches only `reserve()`. The object is still a proxy; however, the corresponding advice logic does not necessarily run when calling `viewCatalog()`.

Therefore, distinguish:

1. Is the bean a proxy?
2. Is the proxy JDK or class-based?
3. Is the called method selected by an advisor?
4. Does the call actually go through the proxy?

Identifying the proxy answers only the first two questions.

## 5. Configuring proxy strategy in Spring Boot

In many modern Spring Boot projects, Spring AOP auto-configuration prefers **class-based proxies** by default. You can request interface-based proxies when appropriate.

In `application.properties`:

```properties
spring.aop.proxy-target-class=false
```

Or `application.yml`:

```yaml
spring:
  aop:
    proxy-target-class: false
```

The value `false` instructs Spring Boot to use JDK interface-based proxies when possible within the corresponding AOP mechanism.

To prefer class-based proxies:

```properties
spring.aop.proxy-target-class=true
```

### 5.1. Does this property change every proxy in the context?

Not necessarily. It governs the AOP auto-configuration supported by Spring Boot, **not every proxy** created by scoped proxies, external libraries, or a separately configured `ProxyFactory`.

If multiple configurations register auto-proxy creators or multiple annotations enable AOP, verify the outcome on the actual object.

### 5.2. When the target implements no interface

If the target lacks a suitable interface for creating a JDK proxy, Spring AOP can fall back to a class-based proxy even when the application prefers interface-based proxies. Therefore, do not conclude that `proxy-target-class=false` forces **every bean** to use a JDK proxy.

### 5.3. `@EnableAspectJAutoProxy`

In Spring Framework, proxy-based AspectJ-style AOP can be enabled via:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AopConfiguration {
}
```

Or:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfiguration {
}
```

In Spring Boot, this annotation is usually unnecessary if AOP auto-configuration already provides the needed setup. Avoid declaring multiple AOP configurations with conflicting strategies without understanding the final result.

### 5.4. Reference type selection table

| Target | Exposed object | Inject interface | Inject concrete class |
| --- | --- | --- | --- |
| `EmailSender implements NotificationSender` | Unproxied target | Yes | Yes |
| `EmailSender implements NotificationSender` | JDK proxy | Yes | No, proxy does not extend `EmailSender` |
| `EmailSender implements NotificationSender` | Class-based proxy | Yes | Yes, if subclass proxy is valid |
| Class implementing no business interface | Class-based proxy | No matching business interface | Yes, if subclass proxy is valid |
| Final target class | CGLIB proxy requested | Not guaranteed | Proxy creation may fail |

The "Yes" cells assume the bean can be created successfully and uniquely selected among candidates.

## 6. Injection rules: assignability first, candidate selection second

The dependency type declared by a constructor or field:

```java
public CheckoutService(PaymentOperations payments) {
    this.payments = payments;
}
```

requires Spring to supply an object assignable to `PaymentOperations`.

If the object is a JDK proxy implementing `PaymentOperations`, the assignment is valid. If the dependency requires concrete `PaymentService`, a proxy implementing only the interface cannot satisfy it.

### 6.1. Lookup by name does not bypass type checking

Example:

```java
PaymentOperations payments =
        context.getBean(
                "paymentService",
                PaymentOperations.class
        );
```

This call can succeed with a JDK proxy.

However:

```java
PaymentService payments =
        context.getBean(
                "paymentService",
                PaymentService.class
        );
```

can fail if the bean is exposed via a JDK proxy.

**The bean name identifies an entry in the container; it does not change the object's class hierarchy.**

### 6.2. `@Qualifier` does not fix a type mismatch

```java
public CheckoutService(
        @Qualifier("paymentService") PaymentService payments) {
    this.payments = payments;
}
```

A qualifier helps select the bean bearing the matching name or qualifier. Yet if that bean's object is a JDK proxy that is not a `PaymentService`, the dependency still mismatches on type.

Replace with:

```java
public CheckoutService(
        @Qualifier("paymentService") PaymentOperations payments) {
    this.payments = payments;
}
```

### 6.3. `@Primary` also does not fix a type mismatch

Suppose a class is marked `@Primary`:

```java
@Service
@Primary
public class CardPaymentService implements PaymentOperations {
    @Override
    public void charge(String orderId) {
        System.out.println("Card payment " + orderId);
    }
}
```

`@Primary` prioritizes one candidate among multiple matching beans; it does not make a JDK proxy an instance of `CardPaymentService`.

### 6.4. Collection injection

Example:

```java
@Service
public class PaymentRouter {

    private final List<PaymentOperations> handlers;

    public PaymentRouter(List<PaymentOperations> handlers) {
        this.handlers = handlers;
    }
}
```

Spring can inject a list of all objects implementing `PaymentOperations`, including matching JDK proxies.

Conversely, `List<CardPaymentService>` is not a general way to collect JDK proxies of concrete target classes. When handling multiple implementations, inject via the shared interface.

## 7. End-to-end running example: creating an AOP proxy and inspecting types

We build an application with an interface, a target service, an aspect, and a diagnostic runner.

### 7.1. Dependency

In a Spring Boot project with proper dependency management, Gradle Groovy DSL typically uses:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Or Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

### 7.2. Business interface

`InventoryOperations.java`:

```java
package com.example.demo.inventory;

public interface InventoryOperations {
    void reserve(String sku);
}
```

### 7.3. Target class

`InventoryService.java`:

```java
package com.example.demo.inventory;

import org.springframework.stereotype.Service;

@Service
public class InventoryService implements InventoryOperations {

    @Override
    public void reserve(String sku) {
        System.out.println("Reserved SKU: " + sku);
    }
}
```

### 7.4. Aspect

`InventoryLoggingAspect.java`:

```java
package com.example.demo.inventory;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InventoryLoggingAspect {

    @Before(
        "execution(* com.example.demo.inventory.InventoryOperations.reserve(..))"
    )
    public void beforeReserve() {
        System.out.println("AOP: before reserve");
    }
}
```

The aspect has a before advice applied when the pointcut matches the corresponding method call through a Spring AOP proxy.

### 7.5. Application startup

`DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

The package `com.example.demo.inventory` sits under the root package `com.example.demo` so default component scanning finds both the service and aspect.

### 7.6. Choose JDK proxy

In `application.properties`:

```properties
spring.aop.proxy-target-class=false
```

When the aspect matches and Spring AOP creates an interface-based proxy, the `inventoryService` bean is exposed as a JDK proxy implementing `InventoryOperations`.

### 7.7. Inject by interface

```java
package com.example.demo.inventory;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class InventoryRunner implements ApplicationRunner {

    private final InventoryOperations inventory;

    public InventoryRunner(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    @Override
    public void run(ApplicationArguments args) {
        inventory.reserve("SKU-100");
    }
}
```

Illustrative output:

```text
AOP: before reserve
Reserved SKU: SKU-100
```

If the aspect log does not appear, check the AOP dependency, pointcut, scanned classes, and proxy strategy. Do not conclude code is intercepted simply because the application starts cleanly.

## 8. Identifying proxies with `AopUtils`

Spring provides the utility:

```java
import org.springframework.aop.support.AopUtils;
```

Commonly used methods:

| API | Purpose |
| --- | --- |
| `AopUtils.isAopProxy(obj)` | Checks whether it is a Spring AOP proxy |
| `AopUtils.isJdkDynamicProxy(obj)` | Checks whether it is a Spring AOP JDK dynamic proxy |
| `AopUtils.isCglibProxy(obj)` | Checks whether it is a Spring AOP class-based proxy |
| `AopUtils.getTargetClass(obj)` | Returns the target class the framework can determine |

### 8.1. Type diagnostic runner

```java
package com.example.demo.inventory;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ProxyInspector implements ApplicationRunner {

    private final InventoryOperations inventory;

    public ProxyInspector(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    @Override
    public void run(ApplicationArguments args) {
        Object bean = inventory;

        System.out.println(
                "Runtime class: " + bean.getClass().getName()
        );

        System.out.println(
                "Spring AOP proxy: " + AopUtils.isAopProxy(bean)
        );

        System.out.println(
                "JDK proxy: " + AopUtils.isJdkDynamicProxy(bean)
        );

        System.out.println(
                "CGLIB proxy: " + AopUtils.isCglibProxy(bean)
        );

        System.out.println(
                "Target class: " +
                AopUtils.getTargetClass(bean).getName()
        );

        System.out.println(
                "Assignable to interface: " +
                (bean instanceof InventoryOperations)
        );

        System.out.println(
                "Assignable to concrete: " +
                (bean instanceof InventoryService)
        );
    }
}
```

### 8.2. Illustrative output with a JDK proxy

```text
Runtime class: jdk.proxy2.$Proxy...
Spring AOP proxy: true
JDK proxy: true
CGLIB proxy: false
Target class: com.example.demo.inventory.InventoryService
Assignable to interface: true
Assignable to concrete: false
```

The JDK-generated class name may differ across Java versions. Do not hard-code or assert the exact proxy class name in tests.

### 8.3. Illustrative output with a class-based proxy

Change configuration:

```properties
spring.aop.proxy-target-class=true
```

If the class can be proxied via subclassing:

```text
Runtime class: com.example.demo.inventory.InventoryService$$SpringCGLIB$$...
Spring AOP proxy: true
JDK proxy: false
CGLIB proxy: true
Target class: com.example.demo.inventory.InventoryService
Assignable to interface: true
Assignable to concrete: true
```

In the examples above, `getClass()` reports **the runtime class of the reference**, while `getTargetClass()` reports **the target class**. The proxy and target do not need to share the same runtime class.

## 9. How do `getClass()`, `instanceof`, and target class differ?

Three checks answer three different questions:

```java
bean.getClass()
```

Reports the actual runtime class of the object reference.

```java
bean instanceof InventoryService
```

Checks whether the object reference is assignable to `InventoryService`.

```java
AopUtils.getTargetClass(bean)
```

Identifies the target class based on information Spring AOP can access.

### 9.1. Do not confuse target class with injectable type

A JDK proxy can yield:

```java
AopUtils.getTargetClass(bean) == InventoryService.class
```

while:

```java
bean instanceof InventoryService
```

is `false`.

There is no contradiction: the target class is the type of the implementation behind the proxy; the assignability of the proxy object is governed by the proxy's own class hierarchy/implemented interfaces.

### 9.2. `AopUtils.getTargetClass()` does not return the target instance

This API returns `Class<?>`, not the target object:

```java
Class<?> type = AopUtils.getTargetClass(bean);
```

Do not use it to try grabbing the target and calling it directly. Calling the target outside the proxy can skip transactions, caching, security, or other advice.

### 9.3. Java `Proxy.isProxyClass()`

Java provides:

```java
import java.lang.reflect.Proxy;
```

Check:

```java
boolean jdkProxyClass =
        Proxy.isProxyClass(bean.getClass());
```

It tells whether the runtime class is a **Java dynamic proxy class**.

However:

- A Java dynamic proxy can be created by another library, not necessarily a Spring AOP proxy.
- A CGLIB proxy is not a Java dynamic proxy.
- When diagnosing Spring AOP, `AopUtils.isAopProxy(...)` usually expresses the intent better.

### 9.4. Do not detect proxies by substring

Avoid:

```java
boolean proxy = bean.getClass()
        .getName()
        .contains("SpringCGLIB");
```

Generated class names can change across Java/Spring versions. Moreover, Spring also uses bytecode enhancement for purposes other than Spring AOP.

## 10. Interface-first injection in service design

For many services with clear business contracts, inject by interface:

```java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }
}
```

This approach:

- Works with JDK proxies implementing the interface.
- Still works with CGLIB proxies of the implementation.
- Reduces coupling to concrete classes.
- Makes creating fakes, mocks, or decorators in tests easier.
- Lets implementations be swapped without modifying clients.

Not every class must have an interface. For a simple bean needing no abstraction, concrete injection can still fit. However, when a bean may be JDK-proxied, interface-first injection carries the lowest risk.

### 10.1. Multiple implementations and `@Qualifier`

```java
public interface PaymentOperations {
    void charge(String orderId);
}
```

```java
@Service("cardPayments")
public class CardPayments implements PaymentOperations {
    @Override
    public void charge(String orderId) {
        System.out.println("Card " + orderId);
    }
}
```

```java
@Service("walletPayments")
public class WalletPayments implements PaymentOperations {
    @Override
    public void charge(String orderId) {
        System.out.println("Wallet " + orderId);
    }
}
```

Select an implementation:

```java
public CheckoutService(
        @Qualifier("cardPayments") PaymentOperations payments) {
    this.payments = payments;
}
```

Combining qualifiers with **interface types** lets Spring pick the desired bean while keeping a type contract compatible with JDK proxies.

## 11. `@Transactional`: proxies can be required for external calls

A familiar scenario:

```java
public interface OrderOperations {
    void submit(String orderId);
}
```

```java
@Service
public class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void submit(String orderId) {
        System.out.println("Submit " + orderId);
    }
}
```

When transaction infrastructure is enabled, an appropriate transaction manager exists, and advice applies, `OrderService` can be exposed through a proxy.

Client:

```java
@Service
public class OrderWorkflow {

    private final OrderOperations orders;

    public OrderWorkflow(OrderOperations orders) {
        this.orders = orders;
    }

    public void run(String id) {
        orders.submit(id);
    }
}
```

If `orders` is a JDK proxy, a reference typed as `OrderOperations` remains valid.

### 11.1. Self-invocation bug

The existence of a proxy does not mean every internal call is intercepted:

```java
@Service
public class OrderService {

    public void runWorkflow(String id) {
        saveOrder(id);
    }

    @Transactional
    public void saveOrder(String id) {
        System.out.println("Save " + id);
    }
}
```

In proxy-based Spring AOP, calling `saveOrder(id)` from inside the target via `this` usually does not exit and re-enter through the proxy.

```text
Client
  |
  v
Proxy
  |
  v
target.runWorkflow()
  |
  +--> this.saveOrder()
           |
           v
      Target directly
      (bypasses proxy boundary)
```

If transaction advice sits only on `saveOrder`, the transaction may not apply as the author intended during an internal call.

### 11.2. Redesign to pass through the proxy

Extract the method needing advice into another bean:

```java
public interface OrderWriteOperations {
    void saveOrder(String id);
}
```

```java
@Service
public class OrderWriter implements OrderWriteOperations {

    @Override
    @Transactional
    public void saveOrder(String id) {
        System.out.println("Save " + id);
    }
}
```

```java
@Service
public class OrderWorkflow {

    private final OrderWriteOperations writer;

    public OrderWorkflow(OrderWriteOperations writer) {
        this.writer = writer;
    }

    public void runWorkflow(String id) {
        writer.saveOrder(id);
    }
}
```

When `writer` is a Spring proxy, calls from `OrderWorkflow` cross the proxy boundary.

Do not try to "unwrap the proxy to grab the target" to fix self-invocation; doing so makes bypassing advice even easier.

## 12. `@Async`, caching, and proxies with multiple advisors

Spring supports other AOP behaviors when enabled and properly configured.

Async example:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

```java
public interface NotificationOperations {
    CompletableFuture<Void> sendAsync(String message);
}
```

```java
@Service
public class NotificationService implements NotificationOperations {

    @Override
    @Async
    public CompletableFuture<Void> sendAsync(String message) {
        System.out.println(message);
        return CompletableFuture.completedFuture(null);
    }
}
```

Clients inject `NotificationOperations`, avoiding dependence on whether Spring creates a JDK proxy or CGLIB proxy in appropriate scenarios.

Caching:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

```java
@Cacheable("products")
public Product findProduct(String sku) {
    return repository.findBySku(sku);
}
```

The caching example assumes an appropriate cache manager, repository, and `Product` model exist. These are illustrative mechanisms, not complete runnable applications if dependencies are omitted.

One bean can have multiple advisors:

```text
Client
  |
  v
Spring AOP proxy
  |
  +--> Transaction advice
  +--> Metrics advice
  +--> Custom logging advice
  |
  v
Target
```

Not every annotation creates a separate proxy. One proxy can hold multiple advisors depending on configuration.

## 13. Scoped proxies: proxies are not only for AOP methods

A request-scoped bean has a shorter lifetime than a singleton. If a singleton needs a dependency bound to the current request, Spring can supply a **scoped proxy**.

```java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMetadata {

    public String requestId() {
        return "example-request";
    }
}
```

A singleton:

```java
@Service
public class AuditService {

    private final RequestMetadata metadata;

    public AuditService(RequestMetadata metadata) {
        this.metadata = metadata;
    }

    public String currentRequestId() {
        return metadata.requestId();
    }
}
```

In an appropriate Spring Web configuration, `@RequestScope` defaults to a class-based scoped proxy. The singleton can hold a stable proxy reference while the underlying target changes per HTTP request.

```text
AuditService (singleton)
           |
           v
RequestMetadata proxy
           |
           +--> HTTP Request A -> Target A
           |
           +--> HTTP Request B -> Target B
```

### 13.1. The proxy reference outlives the target

The proxy reference can exist before any request is active. However, calling a method requiring request scope outside an active request causes Spring to throw an error because there is no request context.

Do not assume injecting a scoped proxy guarantees every call is valid on every thread.

### 13.2. `ScopedProxyMode`

You can specify the proxy mode:

```java
@Component
@Scope(
    value = WebApplicationContext.SCOPE_REQUEST,
    proxyMode = ScopedProxyMode.INTERFACES
)
public class CurrentUserContext implements UserContext {
}
```

The example assumes `UserContext` is an application-defined interface. Import `Scope`, `WebApplicationContext`, and `ScopedProxyMode` from Spring.

With `ScopedProxyMode.INTERFACES`, clients should inject `UserContext`. With `ScopedProxyMode.TARGET_CLASS`, a class-based proxy can be assignable to the concrete class if subclass creation succeeds.

**Conclusion:** when debugging a bean's type, first determine *why* the proxy was created: transactions, custom aspect, scope, lazy resolution, or another library.

## 14. `@Lazy` on an injection point can create a proxy

Example:

```java
@Service
public class ReportService {

    private final HeavyReportEngine engine;

    public ReportService(@Lazy HeavyReportEngine engine) {
        this.engine = engine;
    }
}
```

`@Lazy` on an injection point can cause Spring to supply a proxy to defer resolving the target dependency.

Distinguish this from:

```java
@Component
@Lazy
public class HeavyReportEngine {
}
```

At the bean definition level, `@Lazy` allows deferring bean creation until needed. However, if a non-lazy singleton injects that bean directly, Spring may still need to create the dependency eagerly to finish the singleton.

Do not infer that "having a proxy" means the bean has transaction advice.

## 15. Target `getClass()` differs from client's `getClass()`

Consider:

```java
@Service
public class InventoryService implements InventoryOperations {

    public InventoryService() {
        System.out.println(
                "Inside target constructor: " +
                getClass().getName()
        );
    }

    @Override
    public void reserve(String sku) {
        System.out.println(sku);
    }
}
```

In a typical AOP JDK-proxy scenario, the target constructor can print `InventoryService`, whereas the bean reference injected into a client reports a JDK proxy class.

There is no contradiction. The target's `this` and the object reference held by the client do not have to be the same object.

With class-based proxies, instance creation and callback details can differ; do not rely on constructor logs to deduce the structure of every proxy type.

### 15.1. `instanceof` is an assignability check tool

```java
Object bean = context.getBean("inventoryService");

System.out.println(bean instanceof InventoryOperations);
System.out.println(bean instanceof InventoryService);
```

With an interface JDK proxy:

```text
true
false
```

With a valid CGLIB proxy extending the implementation:

```text
true
true
```

These values are expected outcomes for those respective proxy scenarios; do not use them to prove a specific call goes through a particular advisor.

## 16. `ApplicationContext.getType()` and the runtime object

Spring can infer a bean type from bean definitions and container metadata:

```java
Class<?> predicted = context.getType("inventoryService");
```

Whereas:

```java
Class<?> actual =
        context.getBean("inventoryService").getClass();
```

returns the runtime class of the object actually retrieved.

Depending on timing, `FactoryBean`, proxy creators, scope, or lazy initialization, predicted type resolution can differ from the runtime class of an instance retrieved later.

### 16.1. Do not force bean initialization solely for early inspection

`getBean()` can trigger bean creation. Calling it during bean definition processing or very early conditions can alter lifecycle timing and cause unexpected failures.

Usually inspect proxies after the context is ready, such as in an integration test or `ApplicationRunner`.

### 16.2. Multiple proxy layers may exist

A bean can be wrapped by multiple proxies or decorators:

```text
Client
   |
   v
Outer proxy
   |
   v
Inner proxy
   |
   v
Target
```

`AopUtils.getTargetClass(...)` helps locate the target class in common scenarios. Spring also offers `AopProxyUtils.ultimateTargetClass(...)` to assist diagnosing proxy chains when the target source allows.

Do not manually peel off proxy layers to call the target directly in business code, as that can strip transaction, cache, security, or scope semantics.

## 17. `Advised` and advisor metadata

Some Spring AOP proxies expose the `Advised` interface, allowing inspection of advisor metadata and target source.

```java
import org.springframework.aop.framework.Advised;

if (bean instanceof Advised advised) {
    System.out.println(
            "Advisor count: " + advised.getAdvisors().length
    );
}
```

This is an infrastructure diagnostic tool, not a business contract.

Not every proxy exposes `Advised`; a proxy may be configured as opaque or created by another library.

Do not use `Advised` to drive order processing logic, access permissions, or implementation selection. Clients should depend on business interfaces.

## 18. Enhanced `@Configuration` classes are not always AOP proxies

A configuration class can be subclassed by Spring to support calls between `@Bean` methods when `proxyBeanMethods=true`.

Example:

```java
@Configuration
public class TimeConfiguration {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    public TimeService timeService() {
        return new TimeService(clock());
    }
}
```

Where appropriate, Spring enhances the configuration class so calling `clock()` from another `@Bean` method still honors container bean lookup semantics.

This **is not necessarily** the same kind of Spring AOP proxy used for `@Transactional` or an aspect.

### 18.1. `proxyBeanMethods=false`

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {
}
```

This adjusts configuration-class enhancement; it does not disable all AOP proxies on beans created by that class.

Do not conclude a class is a transaction proxy solely because its runtime class name shows signs of a generated subclass.

## 19. Workflow for resolving concrete target class injection errors

Suppose application startup reports that bean `inventoryService` cannot be used as type `InventoryService`, and the actual runtime bean type is a JDK proxy.

### Step 1: identify the dependency type

```java
public InventoryController(InventoryService inventory) {
    this.inventory = inventory;
}
```

The client is requesting **the concrete class**.

### Step 2: find the business interface

```java
public class InventoryService implements InventoryOperations {
}
```

If the interface exposes all needed methods, it is a strong candidate for the dependency contract.

### Step 3: determine the proxy strategy

Check Spring AOP configuration, for example:

```properties
spring.aop.proxy-target-class=false
```

If the bean has a matching advisor and the actual proxy is JDK, concrete-class injection is incompatible.

### Step 4: inspect the actual object

In a test context without the mis-typed consumer:

```java
Object bean = context.getBean("inventoryService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.getTargetClass(bean));
```

### Step 5: fix the injection type

Change it to:

```java
public InventoryController(InventoryOperations inventory) {
    this.inventory = inventory;
}
```

If multiple beans implement `InventoryOperations`, add `@Qualifier` or design appropriate bean selection.

### Step 6: consider class-based proxies when genuinely needed

Changing:

```properties
spring.aop.proxy-target-class=true
```

can make concrete injection valid for subclassable target classes. However, this is an infrastructure-wide proxy strategy change and should not be used as a blanket patch for injection errors.

Check final classes, final methods, proxies from other libraries, and impact on remaining beans.

## 20. Other errors easily confused with proxy type issues

| Symptom | Distinction needed |
| --- | --- |
| `NoUniqueBeanDefinitionException` | Multiple beans match the type; select a candidate, not necessarily wrong proxy type |
| `NoSuchBeanDefinitionException` | No matching bean found; could be scan/config or proxy type |
| `BeanNotOfRequiredTypeException` | Bean found, yet the object is not the requested type |
| `ClassCastException` | Casting reference to incompatible class, common with JDK proxies |
| `AopUtils.isAopProxy(bean)` is false | Bean may not be proxied due to pointcut, configuration, or bean kind |
| Aspect does not run even though bean is a proxy | Call may bypass proxy or pointcut does not match |
| `@Transactional` does not work on self-call | Internal call does not cross proxy boundary |
| Request-scoped method reports no active scope | Proxy exists, yet request context is not active |
| Final class cannot create subclass proxy | Limitation of class-based proxies |

Do not assume every Spring autowiring failure is caused by AOP. Distinguish candidate selection, bean registration, proxy type, and method interception.

## 21. Testing proxy types in Spring Boot

Assume we use `InventoryOperations`, `InventoryService`, and `InventoryLoggingAspect` from section 7.

### 21.1. Testing JDK proxy

```java
package com.example.demo.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    properties = "spring.aop.proxy-target-class=false"
)
class InventoryJdkProxyTest {

    @Autowired
    InventoryOperations inventory;

    @Test
    void exposesInterfaceBasedProxy() {
        assertThat(AopUtils.isAopProxy(inventory)).isTrue();
        assertThat(AopUtils.isJdkDynamicProxy(inventory)).isTrue();
        assertThat(inventory)
                .isNotInstanceOf(InventoryService.class);
        assertThat(AopUtils.getTargetClass(inventory))
                .isEqualTo(InventoryService.class);
    }
}
```

The test requires the aspect to be component-scanned and an advisor to actually apply; if no advisor matches, the bean may not be proxied. In that case check AOP setup before drawing conclusions about injectability.

### 21.2. Testing CGLIB proxy

```java
@SpringBootTest(
    properties = "spring.aop.proxy-target-class=true"
)
class InventoryClassProxyTest {

    @Autowired
    InventoryService inventory;

    @Test
    void exposesClassBasedProxy() {
        assertThat(AopUtils.isAopProxy(inventory)).isTrue();
        assertThat(AopUtils.isCglibProxy(inventory)).isTrue();
        assertThat(inventory)
                .isInstanceOf(InventoryService.class);
    }
}
```

The example assumes the target class is non-final and can be subclassed.

### 21.3. Verifying advice behavior

Checking proxy type is not enough to confirm the aspect runs. Use a test collaborator recording advice invocations:

```java
@Component
public class AdviceRecorder {

    private final AtomicInteger calls = new AtomicInteger();

    public void mark() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
```

Aspect in the test:

```java
@Aspect
@Component
public class RecordingAspect {

    private final AdviceRecorder recorder;

    public RecordingAspect(AdviceRecorder recorder) {
        this.recorder = recorder;
    }

    @Before(
        "execution(* com.example.demo.inventory.InventoryOperations.reserve(..))"
    )
    public void before() {
        recorder.mark();
    }
}
```

Call `inventory.reserve("SKU-200")`, then verify the counter increments as expected. When running tests concurrently, isolate or reset the collaborator so calls from other tests do not interfere.

### 21.4. Do not assert generated class names

Avoid testing:

```java
assertThat(inventory.getClass().getName())
        .contains("com.sun.proxy");
```

Java proxy names can vary across JDK versions. Use the API:

```java
assertThat(AopUtils.isJdkDynamicProxy(inventory)).isTrue();
```

or:

```java
assertThat(AopUtils.isCglibProxy(inventory)).isTrue();
```

## 22. When should you avoid creating or unwrapping proxies?

### 22.1. Do not bypass a proxy to "avoid type errors"

If a constructor requests the concrete class while the bean is a JDK proxy, pulling the target object out of infrastructure and passing it manually into a service can cause transaction, cache, and security advice to be skipped.

Fixing the dependency contract properly is usually the better solution.

### 22.2. Do not change proxy strategy just for one cast statement

Switching from JDK to class-based proxies can affect many beans. Before switching, consider:

- Are there final classes/methods?
- Do external modules or libraries rely on their own proxy strategies?
- Does the interface already capture enough of the business contract?
- Do integration tests depend on proxy types?

If only one client needs an implementation method, extracting a suitable interface is often better than changing global configuration.

### 22.3. Do not depend on Spring AOP APIs in business logic

Calls such as:

```java
AopUtils.isAopProxy(service)
```

belong in observation, debugging, or infrastructure tests. Business logic must not alter payment outcomes based on whether a service is a JDK proxy or CGLIB proxy.

## 23. Practice exercises

### Exercise 1 — Predict assignability

Given:

```java
interface TaskPort {
    void run();
}

class DefaultTask implements TaskPort {
    @Override
    public void run() {
    }
}
```

Suppose Spring exposes the bean via a JDK proxy implementing `TaskPort`. Explain:

- Can injecting `TaskPort` succeed?
- Can injecting `DefaultTask` succeed?
- What do `proxy instanceof TaskPort` and `proxy instanceof DefaultTask` return?

### Exercise 2 — Observe both proxy strategies

Use the `InventoryService` and `InventoryLoggingAspect` example. Configure:

```properties
spring.aop.proxy-target-class=false
```

Record `getClass()`, `AopUtils.isJdkDynamicProxy`, `AopUtils.getTargetClass`, and `instanceof`.

Then change it to `true`, restart, and compare.

### Exercise 3 — Reproduce concrete-class injection failure

In JDK mode, change `InventoryRunner`'s constructor from `InventoryOperations` to `InventoryService`.

Observe the startup error message, then restore the interface. Explain why a matching bean name is insufficient to assign the object to the concrete class.

### Exercise 4 — Try `@Qualifier`

Create two implementations `EmailSender` and `SmsSender` both implementing `NotificationSender`. Inject one bean using:

```java
public AlertService(
        @Qualifier("emailSender") NotificationSender sender) {
    this.sender = sender;
}
```

Explain why the qualifier resolves **bean selection** rather than changing proxy type.

### Exercise 5 — Try a final class

Create a `final` class with a method selected by an aspect. Enable class-based proxies and observe whether Spring can create a suitable proxy.

Then remove `final` or switch to interface-based mode when the class has an interface.

### Exercise 6 — Self-invocation

Create a service where method A calls method B directly, while B is advised by `@Transactional` or a custom aspect.

Observe external calls through the proxy vs. internal calls. Move B into a separate service and call via an injected dependency; compare results.

### Exercise 7 — Scoped proxy

Create a `@RequestScope` bean and inject it into a singleton service. Hit an endpoint from two different requests and observe the scoped target.

Explain why the proxy reference stays stable while the request target changes.

### Exercise 8 — `@Lazy` dependency

Inject `HeavyReportEngine` via a constructor parameter marked `@Lazy`. Observe when the bean is resolved and compare with `@Lazy` on the class.

### Exercise 9 — Testing with `AopUtils`

Write integration tests verifying JDK proxies and CGLIB proxies using Spring's API. Do not compare generated class names.

Add a test calling a method and verifying advice actually runs.

### Exercise 10 — Designing interface contracts

A library provides `DocumentProcessor` and class `PdfProcessor`. The system must run under both JDK proxy mode and class-based mode.

Design `DocumentController` injecting `DocumentProcessor`; if `WordProcessor` is added, use an appropriate qualifier. Explain why this is more resilient than injecting `PdfProcessor` directly.

## 24. Summary

When Spring creates a proxy, the bean a client receives via dependency injection can be a **proxy object**, not the target instance. With **JDK dynamic proxies**, the object typically implements only exposed interfaces, so it can be injected by interface yet is not assignable to the concrete target class. With **CGLIB/class-based proxies**, the object typically extends the target class and can be injected by both interface and class when a subclass proxy can be built.

Use `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy`, and `getTargetClass` for diagnostics; use `instanceof` to understand assignability. Do not infer from generated class names, do not use `@Qualifier` or `@Primary` as a way to force proxies into concrete classes, and do not unwrap targets directly to bypass advice.

The design least dependent on proxy strategy is usually **constructor injection through clear business interfaces**. Finally, a bean being a proxy does not mean every method is advised: outcomes still depend on pointcuts, visibility, final methods, and whether calls cross the proxy boundary.

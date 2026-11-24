# BeanDefinition, Actual Bean Instance, and Bean Proxy

In Spring Boot, a class annotated with `@Service` does not instantly become an active object. Spring first **records how to create and manage the object**, then **instantiates the bean**, and in certain situations **exposes a proxy for other beans to use**. These three things are closely related yet not identical:

- **`BeanDefinition`**: the description or "recipe" telling Spring how to manage a bean.
- **Bean instance (actual bean object)**: the object created or supplied according to the definition, under the management of the IoC container.
- **Bean proxy**: an intermediary object that Spring may expose instead of direct access to the target object, in order to add behaviors such as transactions, caching, security, or scope handling.

Understanding the distinction helps explain why Spring can inject an interface without you calling `new`, why `@Transactional` sometimes does not work, and why `getBean(...).getClass()` occasionally returns a class with an unfamiliar name.

## 1. The Big Picture in the IoC Container

The Spring IoC container is responsible for registering bean configurations, resolving dependencies, creating objects, managing lifecycles, and providing beans to the rest of the application.

A simplified flow:

```text
Application source code / configuration
  @Component, @Service, @Configuration, @Bean, ...
                    |
                    v
      Read metadata and register BeanDefinition
                    |
                    v
            BeanFactory / registry
                    |
          need to create bean per scope
                    |
                    v
        Instantiate object and inject dependencies
                    |
                    v
         Run initialization / post-processing steps
                    |
                    +-----------------------------+
                    |                             |
                    v                             v
             Regular bean               May create proxy wrapping target
                    |                             |
                    +--------------+--------------+
                                   |
                                   v
                    Object supplied by the container
                                   |
                                   v
                        Consumed by other beans via DI
```

This diagram is conceptual. In practice, bean creation can involve more steps; Spring also has various bean types and registration mechanisms. In particular, **not every bean has a proxy**.

### 1.1. Two Important Roles: `BeanFactory` and `ApplicationContext`

`BeanFactory` is the core interface for retrieving beans and managing the fundamental capabilities of the IoC container. `ApplicationContext` extends that capability with configuration reading, events, resources, environment integration, and many other utilities.

A Spring Boot application typically obtains an `ApplicationContext` by calling:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);
```

You can retrieve a bean by name or type:

```java
PaymentService service = context.getBean(PaymentService.class);
```

Calling `getBean` returns **the object exposed by the container for consumption**. If an AOP proxy is present, the result may be a proxy rather than an instance of the original implementation class.

## 2. What Is a `BeanDefinition`?

`BeanDefinition` is an internal metadata object in Spring describing how to create and configure a bean. It is not an instance of `PaymentService`, `OrderService`, or any business class.

A bean definition can provide information such as:

| Attribute/Metadata | Meaning |
| --- | --- |
| Bean name | Identifier registered in the container |
| Bean class or factory method | Expected object type or how to call a factory to create the object |
| Scope | Such as `singleton`, `prototype`, `request`, `session` |
| Lazy initialization | Whether to defer instantiation until needed |
| Constructor arguments / property values | Configuration values or dependencies to supply at creation |
| Init / destroy methods | Configured initialization and destruction callbacks |
| Primary / qualifiers / autowire candidate | Metadata assisting in selecting the right bean during injection |
| Role and source metadata | Distinguishing application beans, infrastructure beans, and definition origin |

Not every `BeanDefinition` contains all of the attributes above. For instance, a bean created from a `@Bean` method may reference a **factory bean and factory method**, rather than having only a class whose constructor is called directly.

### 2.1. Where Does `BeanDefinition` Come From?

Spring has several ways to register bean definitions:

**Via component scanning:**

```java
package com.example.shop.service;

import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long calculate(long unitPrice, int quantity) {
        return unitPrice * quantity;
    }
}
```

When component scan scans this package, it can register a bean definition with the default name `priceService`.

**Via `@Bean` methods:**

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    public TaxPolicy taxPolicy() {
        return new TaxPolicy(0.10);
    }
}
```

Here, Spring registers a bean definition for the result of `taxPolicy()`. `TaxPolicy` does not have to carry `@Component`; Spring knows how to create the bean from the `@Bean` method.

**Other sources:** XML declarations, `@Import`, manual registration via a registry, Spring Boot auto-configuration, and integration mechanisms of other frameworks.

Therefore, the statement "a bean only exists if the class has `@Component`" is inaccurate.

### 2.2. Bean Name Differs from Java Class Name

With `@Service` without an explicit name, Spring typically derives a name from the class name by convention:

```java
@Service
public class PaymentService {
}
```

The bean name is usually `paymentService`. You can specify an explicit name:

```java
@Service("onlinePaymentService")
public class PaymentService {
}
```

With `@Bean`, the default name is usually the method name:

```java
@Bean
public Clock appClock() {
    return Clock.systemUTC();
}
```

The default bean name is `appClock`, even though the return type is `Clock`. Bean names are useful for looking up beans by name, specifying qualifiers, or diagnosing configuration; a bean name does not have to match the class or object name it represents.

### 2.3. When Does a `BeanDefinition` Exist Without an Instance Yet?

Example of a `@Lazy` bean:

```java
@Service
@Lazy
public class ReportGenerator {

    public ReportGenerator() {
        System.out.println("ReportGenerator created");
    }
}
```

Spring can still register the `reportGenerator` bean definition at startup, while deferring instance creation until the bean is actually retrieved or required by usage conditions. If another bean depends directly on `ReportGenerator` and that bean is created eagerly, `ReportGenerator` may still be instantiated during dependency resolution.

This demonstrates that **definition registration** and **object instantiation** are two distinct steps.

## 3. How Is the Actual Bean Instance Created?

For an ordinary bean, Spring uses metadata in the bean definition to select a constructor or factory method, resolve dependencies, and create the object.

Example:

```java
package com.example.shop;

import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
class InventoryClient {
    public boolean available(String sku) {
        return true;
    }
}

@Service
class OrderService {
    private final InventoryClient inventoryClient;

    OrderService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public boolean canOrder(String sku) {
        return inventoryClient.available(sku);
    }
}
```

When Spring creates `orderService`, the container resolves the constructor parameter of type `InventoryClient`, locates the matching bean, and passes it into the constructor. You do not have to write:

```java
new OrderService(new InventoryClient());
```

This is **dependency injection**: supplying dependencies is delegated to the IoC container. If multiple matching beans or none exist, Spring needs additional information such as `@Qualifier`, `@Primary`, or suitable bean configuration; otherwise bean creation can fail.

### 3.1. A Simplified Bean Lifecycle

For a typical singleton bean, the main stages can be pictured as follows:

```text
1. Register BeanDefinition
           |
2. Decide bean needs creation
           |
3. Choose constructor / factory method, create target instance
           |
4. Supply dependencies and properties
           |
5. Run pre-initialization callbacks and BeanPostProcessors
           |
6. Initialization: e.g. @PostConstruct / InitializingBean
           |
7. Run post-initialization BeanPostProcessors
           |              \
           |               \-- may return a proxy
           v
8. Expose bean for other components to use
           |
9. Destroy bean per appropriate lifecycle when context closes
```

The order above is simplified for learning. Different callback methods have specific detailed ordering, some proxy mechanisms may engage at different points in the lifecycle, and circular dependencies can complicate the sequence.

### 3.2. Distinguishing an Object Created with `new` from a Spring Bean

Suppose we have:

```java
@Service
public class ReceiptService {
    public String createReceipt() {
        return "Receipt created";
    }
}
```

These two lines do not necessarily produce the same kind of object in terms of management:

```java
ReceiptService managed = context.getBean(ReceiptService.class);
ReceiptService manual = new ReceiptService();
```

`managed` is supplied by the container, may have had dependencies injected, lifecycle callbacks run, and a proxy wrapped around it. `manual` is a Java object you created with `new`, so Spring **does not automatically** manage it. Features like `@Transactional`, `@Async`, or Spring-performed injection do not apply automatically to manually created objects.

An instance of a Java class **is not automatically a Spring bean just because the class is annotated with `@Service`**.

## 4. Scope Affects the Number of Bean Instances

A bean definition contains scope metadata. From the same definition, the count or timing of instance creation can differ.

| Scope | Typical Behavior |
| --- | --- |
| `singleton` | One container-managed bean instance per bean definition within one IoC container (default) |
| `prototype` | Creates a new instance each time a bean of this scope is requested |
| `request` | One instance per HTTP request when an appropriate web context exists |
| `session` | One instance per HTTP session when an appropriate web context exists |
| `application` | Scope tied to the servlet application context |

"Singleton in Spring" is scoped **per container and bean definition**; it does not mean only one object of that class can exist in the entire JVM. You can have multiple `ApplicationContext` instances, two bean definitions of the same type, or objects created with `new`.

### 4.1. Singleton Example

```java
@Component
public class IdGenerator {
}
```

Under the default scope:

```java
IdGenerator a = context.getBean(IdGenerator.class);
IdGenerator b = context.getBean(IdGenerator.class);

System.out.println(a == b); // usually true
```

For the same ordinary singleton bean, `getBean` returns the same reference managed by the container. If that bean is wrapped in a singleton proxy, two lookups may also return the same **proxy**, not a direct reference to the raw target.

### 4.2. Prototype Example

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
```

When calling:

```java
JobContext first = context.getBean(JobContext.class);
JobContext second = context.getBean(JobContext.class);

System.out.println(first == second); // false, with this prototype definition
```

You need to import `org.springframework.context.annotation.Scope` and `org.springframework.beans.factory.config.ConfigurableBeanFactory`. A practical note: if a prototype is injected directly into a singleton's constructor, the prototype is normally resolved **once when the singleton is created**. To retrieve a new prototype on each use, you can use `ObjectProvider<T>`, `Provider<T>`, or design a suitable lookup mechanism.

### 4.3. Scope and Destruction Lifecycle

The container manages the full lifecycle for standard singletons. For prototypes, Spring creates and supplies the bean, yet usually **does not invoke full destruction callbacks** when the context closes; the consumer must manage the prototype's resources if needed. Web scopes follow request/session lifecycles and require an appropriate web context.

## 5. What Is a Bean Proxy?

A **proxy** is an intermediary object sitting between the caller and the **target** object. The caller interacts with the proxy; the proxy can execute logic before, after, or around the call and then forward it to the target.

```text
Controller / Other Service
          |
          | calls placeOrder()
          v
    +---------------+
    |  Bean proxy   |
    |---------------|
    | Checks        |
    | Open tx       |
    | Logging / ... |
    +---------------+
          |
          | forwards call
          v
    +---------------+
    |  Target bean  |
    |---------------|
    | placeOrder()  |
    | business logic|
    +---------------+
          |
          v
        Result
```

With Spring AOP, a proxy can apply a chain of interceptors/advice rather than just a single step. For example:

```text
Client
   ↓
Proxy
   ├── Security interceptor
   ├── Transaction interceptor
   ├── Metrics interceptor
   ↓
Target.placeOrder()
   ↓
Return result / throw exception
   ↓
Interceptors complete corresponding logic
   ↓
Client
```

The actual advice order depends on configuration and interceptor ordering. The diagram merely illustrates multiple behaviors participating in a single call.

### 5.1. What Problem Does a Proxy Solve?

Without proxies, if you wanted every business method to log or open a transaction, you might have to duplicate code:

```java
public void placeOrder() {
    beginTransaction();
    try {
        // Business logic
        commitTransaction();
    } catch (RuntimeException ex) {
        rollbackTransaction();
        throw ex;
    }
}
```

When using Spring declarative transactions under proper conditions, you can express intent cleanly:

```java
@Transactional
public void placeOrder() {
    // Business logic
}
```

Transaction logic is handled by Spring Transaction infrastructure via interceptors and a transaction manager, rather than repeated in every method. The annotation is **metadata**; the proxy and infrastructure components perform the runtime behavior on matching calls.

Features commonly associated with proxies:

- `@Transactional`: manages transactions when transaction management is properly configured.
- `@Cacheable`: looks up/updates caches when caching is enabled and a `CacheManager` exists.
- `@Async`: dispatches execution to an executor when async support is enabled.
- Method-level security: enforces authorization checks when method security is configured.
- Spring AOP custom aspects: adds logging, tracing, metrics, or cross-cutting logic.
- Scoped proxies: holds a stable reference while resolving the target per request/session or other scope.

**Seeing an annotation does not guarantee a proxy exists.** You need the right dependencies, enabled infrastructure, matching conditions, and an appropriate method invocation path. There are also proxies serving purposes outside Spring AOP.

### 5.2. How Does a Proxy Differ from a Target?

| Component | Purpose | Visible via `getBean`? |
| --- | --- | --- |
| `BeanDefinition` | Describes how to register/create the bean | No, `getBean` does not return bean definitions |
| Target object | Holds state and business logic being invoked | Yes if no proxy is needed; when proxied, usually wrapped internally by the proxy |
| Proxy object | Intermediary applying advice, scoping, or other behavior | Yes, when Spring exposes the proxy as the bean |

When an AOP proxy is active, the object injected is typically the **proxy**. Thus, calling `getBean("orderService")` or injection may yield a runtime type different from the class you wrote in source code.

## 6. Two Common Types of Spring AOP Proxies

Spring AOP typically uses proxies based on **JDK dynamic proxies** or **CGLIB subclass proxies**.

### 6.1. JDK Dynamic Proxy

A JDK dynamic proxy implements one or more interfaces. Example:

```java
public interface PaymentOperations {
    void pay(long amount);
}

@Service
public class CardPaymentService implements PaymentOperations {
    @Override
    public void pay(long amount) {
        System.out.println("Paid: " + amount);
    }
}
```

When Spring is configured to use a JDK proxy for this bean, the exposed object will **implement `PaymentOperations`**, yet is not necessarily an instance of `CardPaymentService`:

```java
PaymentOperations payment = context.getBean(PaymentOperations.class);
```

Injecting by interface is usually the stable choice in this situation. Trying to inject `CardPaymentService` directly when the bean is exposed solely as a JDK dynamic proxy can run into type-matching errors.

### 6.2. CGLIB Subclass Proxy

A CGLIB proxy generates a subclass of the target class to intercept overridable method calls. The runtime class may look similar to:

```text
com.example.shop.CardPaymentService$$SpringCGLIB$$...
```

Because the proxy is a subclass, `instanceof CardPaymentService` checks can evaluate to true. However, not every method can be overridden: **`private`** and **`final` methods** cannot be intercepted via overriding, and a **`final` class** cannot be subclass-proxied.

### 6.3. Comparison

| Aspect | JDK Dynamic Proxy | CGLIB Subclass Proxy |
| --- | --- | --- |
| Basis for proxy creation | Implements interfaces | Subclasses target class |
| Interface requirement | Requires interface(s) to expose interactions | Does not require an interface |
| Typical exposed type | Interface | Target class or compatible supertypes |
| Common limitations | Only intercepts calls to public methods through the proxy interface | Cannot override `final`/`private` methods; cannot subclass `final` classes |
| Runtime name | JDK proxy style such as `jdk.proxy...` | Style `...$$SpringCGLIB$$...` |

In many Spring Boot applications using AOP, class-based proxies are selected by default when appropriately configured; defaults and customization vary by version and feature. When you need to verify the proxy type of **a running application**, check directly rather than guessing from annotation names.

You can adjust how Spring Boot creates Spring AOP proxies via a property in corresponding configurations:

```properties
# Prefer interface-based proxies when possible
spring.aop.proxy-target-class=false
```

Or:

```properties
# Use class-based proxies
spring.aop.proxy-target-class=true
```

This setting relates to Spring AOP auto-configuration, and does not mean every proxy mechanism across the Spring ecosystem is controlled by this single property.

## 7. Example Observing `BeanDefinition`, Bean, and AOP Proxy

The following example uses a Spring Boot application with **Spring AOP** to show the difference. Assume the project uses a compatible Java version and the AOP dependency matching the Spring Boot version. In Spring Boot 3.x projects, the commonly used dependency is:

**Gradle (Groovy DSL):**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

**Maven:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

If your project uses a newer Spring Boot line that reorganizes starters, pick the AOP starter supported in that version. The snippets assume dependency versions are managed by Spring Boot configuration.

### 7.1. Creating the Interface and Service

`src/main/java/com/example/demo/service/GreetingService.java`:

```java
package com.example.demo.service;

public interface GreetingService {
    String greet(String name);
}
```

`src/main/java/com/example/demo/service/DefaultGreetingService.java`:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class DefaultGreetingService implements GreetingService {

    public DefaultGreetingService() {
        System.out.println("Constructing DefaultGreetingService");
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

The class is picked up by component scan because it has `@Service` and resides in a subpackage of the application package. The default bean name is normally `defaultGreetingService`.

### 7.2. Creating an Aspect for Spring to Apply Advice

`src/main/java/com/example/demo/aop/TraceAspect.java`:

```java
package com.example.demo.aop;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {

    @Around("execution(* com.example.demo.service..*.greet(..))")
    public Object trace(ProceedingJoinPoint point) throws Throwable {
        System.out.println("Before: " + point.getSignature().getName());
        try {
            return point.proceed();
        } finally {
            System.out.println("After: " + point.getSignature().getName());
        }
    }
}
```

The aspect defines around advice for the `greet` method of classes in the specified service package. Spring AOP can create a corresponding proxy for beans with methods matching the pointcut. `point.proceed()` lets the call continue to the target; `finally` ensures trailing logging executes even if the target throws an exception.

### 7.3. Inspecting the Definition and the Object Returned by the Container

`src/main/java/com/example/demo/ProxyDemoApplication.java`:

```java
package com.example.demo;

import com.example.demo.service.GreetingService;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ProxyDemoApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ProxyDemoApplication.class, args);

        ConfigurableListableBeanFactory factory =
                context.getBeanFactory();

        BeanDefinition definition =
                factory.getBeanDefinition("defaultGreetingService");

        Object exposedBean = context.getBean("defaultGreetingService");
        GreetingService service = context.getBean(GreetingService.class);

        System.out.println("Bean name: defaultGreetingService");
        System.out.println("Definition class: " +
                definition.getBeanClassName());
        System.out.println("Definition scope: " +
                definition.getScope());
        System.out.println("Exposed class: " +
                exposedBean.getClass().getName());
        System.out.println("AOP proxy: " +
                AopUtils.isAopProxy(exposedBean));
        System.out.println("Same reference: " +
                (exposedBean == service));
        System.out.println(service.greet("Mai"));
    }
}
```

This illustrates a console or web application launched from a main class. In console mode, the process may exit after `main` finishes; with an embedded web server, the context normally keeps running until application shutdown.

Illustrative output:

```text
Constructing DefaultGreetingService
...
Bean name: defaultGreetingService
Definition class: com.example.demo.service.DefaultGreetingService
Definition scope:
Exposed class: com.example.demo.service.DefaultGreetingService$$SpringCGLIB$$...
AOP proxy: true
Same reference: true
Before: greet
After: greet
Hello, Mai
```

Actual output and startup log ordering vary by environment. If using a JDK dynamic proxy, `Exposed class` will show a JDK proxy name. On a bean definition with default scope, `definition.getScope()` may be an empty string (`""`), because **the scope is not explicitly recorded**; it is still treated as singleton by default.

Notice the key takeaways:

1. `getBeanDefinition(...)` returns **metadata**, including the original class and configuration settings.
2. `context.getBean(...)` returns the **exposed bean**; in this AOP example, it can be a proxy.
3. `AopUtils.isAopProxy(...)` checks whether an object is a Spring AOP proxy.
4. Two ways of retrieving the same singleton bean normally return **the same proxy reference**.
5. Calling `service.greet(...)` passes through the advice before executing the business logic.

If you remove the aspect or appropriate AOP dependency/infrastructure, the bean can be exposed directly and `AopUtils.isAopProxy(...)` will be `false`.

### 7.4. Checking the Specific Proxy Type

You can extend the inspection snippet:

```java
System.out.println(
    "JDK proxy: " + AopUtils.isJdkDynamicProxy(exposedBean)
);
System.out.println(
    "CGLIB proxy: " + AopUtils.isCglibProxy(exposedBean)
);
System.out.println(
    "Target class: " + AopUtils.getTargetClass(exposedBean).getName()
);
```

In a JDK proxy scenario:

```java
System.out.println(exposedBean instanceof GreetingService);
// true

System.out.println(exposedBean instanceof DefaultGreetingService);
// may be false when the proxy only implements the interface
```

In a CGLIB subclass proxy scenario, `instanceof DefaultGreetingService` usually evaluates to true because the proxy extends the target class. Do not rely on `getClass() == DefaultGreetingService.class` to conclude whether a bean has the expected functionality, because a proxy can have a different runtime class.

## 8. Why Do Proxies Alter the Call Path?

Suppose we have a bean:

```java
@Service
public class CheckoutService {

    @Transactional
    public void checkout() {
        // Write multiple records in the same transaction
    }

    public void placeOrder() {
        checkout();
    }
}
```

In Spring's **proxy-based** transaction model, there are two distinct call paths:

**Called from another bean via the Spring proxy:**

```text
OtherBean -> CheckoutService proxy
          -> TransactionInterceptor
          -> CheckoutService target.checkout()
```

When transaction infrastructure and a `PlatformTransactionManager` are properly configured, Spring can apply a transaction to that call.

**One method on the same target calls another via `this`:**

```text
OtherBean -> CheckoutService proxy
          -> CheckoutService target.placeOrder()
                                  |
                                  v
                             this.checkout()
                                  |
                                  v
                           checkout() logic
```

The internal call `this.checkout()` **does not go back through the proxy**, so transaction advice attached specifically to `checkout()` is normally not triggered by this internal call. If `placeOrder()` already entered through an appropriate transaction advice, the outer method's transaction can still cover the inner work; do not deduce that every internal call is "without a transaction" in all scenarios.

### 8.1. Common Solution for Self-Invocation

Extract the operation needing advice into another Spring bean and inject that bean:

```java
@Service
public class PaymentWriter {

    @Transactional
    public void savePayment() {
        // Persist payment data
    }
}

@Service
public class CheckoutFacade {
    private final PaymentWriter paymentWriter;

    public CheckoutFacade(PaymentWriter paymentWriter) {
        this.paymentWriter = paymentWriter;
    }

    public void checkout() {
        paymentWriter.savePayment(); // Call via injected bean reference
    }
}
```

When a transaction proxy is applied to `PaymentWriter`, calling from `CheckoutFacade` passes through the injected bean and can trigger the interceptor as expected.

Besides splitting beans, other AOP mechanisms like AspectJ weaving handle self-invocation differently; however, that model lies outside basic proxy-based Spring AOP. Avoid turning self-calls via `this` into an expectation that "Spring will intercept it anyway," as that contradicts proxy mechanics.

### 8.2. `private`, `final`, and Constructors

Proxy-based AOP primarily intercepts **method invocations passing through the proxy**. Constructors are not business method calls intercepted by AOP proxies in that manner. With class-based proxies, `private` and `final` methods cannot be overridden and therefore cannot be intercepted via overriding.

In business code needing advice, the straightforward choice is placing the annotation on a public method of a Spring bean and invoking it from another bean via dependency injection.

## 9. Scoped Proxy: One Proxy, Multiple Targets per Request

Proxies do not only serve transactions. They also help inject short-lived dependencies into longer-lived beans.

Suppose a web application has a singleton service needing information from the **current HTTP request**:

```java
package com.example.shop.web;

import java.util.UUID;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope(proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestTrace {

    private final String traceId = UUID.randomUUID().toString();

    public String traceId() {
        return traceId;
    }
}
```

A singleton service uses it:

```java
@Service
public class TraceService {
    private final RequestTrace requestTrace;

    public TraceService(RequestTrace requestTrace) {
        this.requestTrace = requestTrace;
    }

    public String currentTraceId() {
        return requestTrace.traceId();
    }
}
```

Directly injecting an actual request-scoped target into a singleton would clash in creation timing and scope. With a **scoped proxy**, Spring provides an intermediary object that can be safely injected into the singleton; when `currentTraceId()` is called during an HTTP request, the proxy locates the target corresponding to the active request.

```text
TraceService (singleton)
          |
          v
RequestTrace scoped proxy (retained reference)
          |
          +--- HTTP request A ---> RequestTrace target A
          |
          +--- HTTP request B ---> RequestTrace target B
```

Across two different requests, `traceId` can differ because the targets differ. Within the same request, calls to the request-scoped bean normally hit the same target for that request.

**Note:** if you try calling a method requiring a request-scoped target outside an HTTP request with an active scope, Spring may throw a scope-not-active exception. A scoped proxy does not fabricate an HTTP request.

### 9.1. One Bean Name Can Accompany Multiple Internal Bean Definitions

When using a scoped proxy, Spring may register one bean definition for the proxy under the public name and another bean definition for the underlying target, typically following an internal naming convention such as `scopedTarget.requestTrace`.

This illustrates why you should not apply a rigid formula like "each class has exactly one bean definition or one object." Bean definitions, exposed beans, and target objects serve separate roles; the actual model depends on bean type and configuration.

## 10. Who Creates Proxies? `BeanPostProcessor` and Infrastructure Components

A `BeanPostProcessor` can be invoked by Spring during bean initialization, before and after initialization callbacks. It may return the bean unchanged or return a different object, such as a proxy.

Conceptually:

```java
public interface BeanPostProcessor {
    Object postProcessBeforeInitialization(Object bean, String beanName);
    Object postProcessAfterInitialization(Object bean, String beanName);
}
```

The snippet above only illustrates the core API signatures; modern Spring versions provide default methods and additional support mechanisms. Spring AOP uses infrastructure processors such as auto-proxy creators to decide which beans need proxy wrapping. Not every `BeanPostProcessor` creates proxies.

**Distinguishing two processing levels:**

| Component | Primarily Works With | Timing / Role |
| --- | --- | --- |
| `BeanFactoryPostProcessor` | Bean definition metadata | Modifies or supplements definition configuration before ordinary beans are created |
| `BeanDefinitionRegistryPostProcessor` | Registry of bean definitions | Can add or modify definitions during registration |
| `BeanPostProcessor` | Bean instances | Intervenes in bean initialization; can create proxies or process annotations |
| Auto-proxy creator | Beans needing advice | Detects advisors and can create AOP proxies |

This is a critical distinction: `BeanFactoryPostProcessor` should not be thought of as "modifying an already created object," because it operates primarily on metadata. `BeanPostProcessor` works with bean instances and is a common link in proxy creation.

### 10.1. Why Doesn't `@PostConstruct` Prove a Bean Has No Proxy?

A `@PostConstruct` method normally executes on the target during initialization before the AOP proxy is fully exposed. Therefore, if you write:

```java
@PostConstruct
public void init() {
    System.out.println("Runtime class: " + getClass().getName());
}
```

you may see the original class name, whereas `context.getBean(...).getClass()` later shows the proxy name. This is not necessarily a contradiction: the two pieces of code are observing the object at different points in its lifecycle.

### 10.2. `@Configuration` Can Also Be Enhanced with a Proxy

In certain modes, Spring enhances `@Configuration` classes with a subclass to ensure calls between `@Bean` methods are consistently managed by the container. This mechanism relates to configuration class processing and `proxyBeanMethods`, which is **different in purpose** from AOP proxies running transactions or caching.

Consequently, seeing a class name containing `$$SpringCGLIB$$` is not enough to conclude the bean has transaction advice. When diagnosing Spring AOP, use APIs such as `AopUtils.isAopProxy` and inspect the actual configuration.

## 11. An Advanced Note: `FactoryBean` Differs from `BeanDefinition`

Spring has a `FactoryBean<T>` interface for beans tasked with **creating another object** according to container contracts. Do not confuse:

- `BeanDefinition`: metadata describing how the container creates/manages a bean.
- `@Bean`: annotation on a factory method.
- `FactoryBean<T>`: Spring interface for a specialized **factory bean**.
- `BeanFactory`: infrastructure for retrieving and managing beans.

With a `FactoryBean` registered under the name `reportClient`, by Spring convention:

```java
Object product = context.getBean("reportClient");
Object factory = context.getBean("&reportClient");
```

A regular name call may return **the product of the `FactoryBean`**, while the `&` prefix retrieves **the factory object itself**. This is another example showing that `getBean(name)` does not always return an instance of the class directly described in the initial registration metadata.

The `FactoryBean` mechanism differs from AOP proxies; an object created by a factory can still participate in other Spring mechanisms depending on configuration.

## 12. Common Errors and Questions

### 12.1. "If `BeanDefinition` Exists, Why Does `getBean` Still Fail?"

A bean definition only records the ability to create a bean. When instantiating, Spring must still resolve constructors, dependencies, properties, callbacks, and runtime conditions. If a dependency is missing, a constructor throws an exception, or an unresolvable circular dependency exists, `getBean` can fail.

Example:

```text
BeanCreationException
  caused by UnsatisfiedDependencyException
    caused by NoSuchBeanDefinitionException
```

Read the deepest `Caused by` section and identify which dependency is not registered or configured.

### 12.2. "Why Does `@Autowired ConcreteService` Fail While Injecting the Interface Succeeds?"

If the bean was replaced by a **JDK dynamic proxy**, the exposed object only guarantees implementing the proxied interface(s). Injecting the concrete implementation class can fail because the proxy is not an instance of that class.

```java
public interface Sender {
    void send(String message);
}

@Service
class EmailSender implements Sender {
    public void send(String message) {
        System.out.println(message);
    }
}
```

Designing clients against the interface is usually straightforward to use:

```java
@Service
class NotificationService {
    private final Sender sender;

    NotificationService(Sender sender) {
        this.sender = sender;
    }
}
```

If multiple implementations of `Sender` exist, add `@Qualifier`, `@Primary`, or an equivalent bean selection strategy.

### 12.3. "Why Does `getClass()` Differ from the Class in Source Code?"

It could be a JDK dynamic proxy or a CGLIB subclass proxy. Inspect `AopUtils.isAopProxy`, `AopUtils.isJdkDynamicProxy`, `AopUtils.isCglibProxy`, and `AopUtils.getTargetClass`. Avoid casting to concrete classes when unsure which proxy type is used.

### 12.4. "Why Isn't the `@Transactional` Annotation Working?"

Check in order:

1. Is the object being called actually a Spring bean, or was it created with `new`?
2. Are transaction management and a transaction manager configured for the appropriate resource?
3. Is the method called **through the proxy**, or is it self-invocation?
4. Is the method eligible for proxy interception, e.g., not restricted by `private`/`final` when a subclass proxy is needed?
5. Do transaction attributes, propagation, and rollback rules match the scenario?

Note: by default, Spring transaction rollback rules generally apply to `RuntimeException` and `Error`; checked exceptions may require configuring `rollbackFor` or corresponding rules. This is another reason developers think advice did not run.

### 12.5. "Why Doesn't `getBeanNamesForType` Show the Expected Bean?"

The bean might not be registered due to component scanning, profiles/conditions, or factory configuration. Furthermore, for factory beans and proxies, type detection may need metadata or initialization to determine the product type. Type-lookup results should not be interpreted separately from how the bean is declared.

### 12.6. "Can I Extract the Target from a Proxy to Call It Directly?"

Some Spring AOP proxies allow accessing target information through infrastructure APIs, yet this is not standard business-code usage. Calling the target directly can bypass advice, and the target source may have its own lifecycle or target-supplying mechanism. Most applications should interact through the interface/bean exposed by the container.

## 13. Brief Comparison Table of the Three Concepts

| Question | `BeanDefinition` | Bean Instance / Target | Bean Proxy |
| --- | --- | --- | --- |
| What is it? | Configuration metadata | Object holding logic/state | Intermediary object |
| Can it exist before object instantiation? | Yes | Not yet | Usually not yet |
| Who creates it? | Scanner/parser/registrar/configuration processor | Container or factory per definition | Appropriate post-processing/AOP/scope mechanism |
| Can it be injected directly as a service? | No, conceptually a bean definition is not a service | Yes if exposed directly by the container | Yes if the container exposes the proxy |
| Does it contain business logic? | No | Yes | Usually delegates to target logic while adding behavior |
| Related to scope? | Stores scope metadata | Instance count/creation timing depends on scope | Scoped proxy can route to target per scope |
| Easy to spot when debugging? | `getBeanDefinition(...)` | Constructor, lifecycle, and method bodies | `getBean(...).getClass()`, `AopUtils` |

**An easy-to-remember analogy:** `BeanDefinition` is like the recipe for preparing a dish, the target bean is the dish made from the recipe, and the proxy is like a server taking orders and applying extra rules before delivering the request to the right dish. This is only an analogy; with scoped proxies, the underlying target dish can vary per request.

## 14. Hands-On Practice in a Spring Boot Project

### Exercise 1 — Distinguishing Definition and Instance

Create a `ReportService` class annotated with `@Service`. In `main`, retrieve:

```java
BeanDefinition bd =
    context.getBeanFactory().getBeanDefinition("reportService");

Object bean = context.getBean("reportService");
```

`context` here has type `ConfigurableApplicationContext`. Print metadata from `bd` and the runtime class from `bean`; explain why they are not the same kind of object. Add `@Lazy` to `ReportService` and observe when the constructor is called.

### Exercise 2 — Distinguishing Scopes

Declare two beans, one default `singleton` and one `prototype`. Call `getBean` twice for each and compare with `==`. Explain why a Spring singleton is not equivalent to a JVM-wide singleton.

### Exercise 3 — Identifying Proxies

Implement the Spring AOP example in section 7. Record:

```java
AopUtils.isAopProxy(bean)
AopUtils.isJdkDynamicProxy(bean)
AopUtils.isCglibProxy(bean)
AopUtils.getTargetClass(bean)
```

Try toggling `spring.aop.proxy-target-class` between `false` and `true` in a supported environment, then compare the bean's runtime type. Explain why injecting by interface is advantageous when using JDK proxies.

### Exercise 4 — Predicting Call Paths

Given the code:

```java
@Service
public class AuditService {
    @Transactional
    public void record() {
        // Record history
    }

    public void execute() {
        record();
    }
}
```

Assume transactions are proxy-implemented and `execute()` has no separate transaction advice. Compare:

1. Bean A injects `AuditService` and calls `auditService.record()`.
2. Bean A injects `AuditService` and calls `auditService.execute()`, where `execute()` calls `record()`.

Which path passes through `record()`'s transaction interceptor? How can you redesign so both cases behave consistently?

### Exercise 5 — Scoped Proxy

Create a request-scoped bean `RequestTrace` and singleton `TraceService` as in section 9. Send two distinct HTTP requests and observe `traceId`. Explain why the singleton can hold a stable reference while per-request data remains isolated.

### Exercise 6 — Explaining a Real-World Bug Yourself

A developer writes:

```java
EmailService mail = new EmailService();
mail.sendWelcomeEmail();
```

Meanwhile, `EmailService` is `@Service` and `sendWelcomeEmail()` carries an AOP-related annotation. Explain why this call may bypass Spring-managed behavior and propose how to inject `EmailService` from the container.

## 15. Takeaways

In Spring Boot, **`BeanDefinition` answers "how will Spring create and manage this bean?"**; **the bean instance/target answers "which object executes the logic?"**; and **the proxy answers "which intermediary mechanism do callers pass through when using the bean?"**.

A bean can be registered before an instance exists; a bean can be exposed directly or through a proxy; and a proxy can route calls to different targets per scope. When inspecting an application, separate three questions clearly: *has the bean definition been registered, which object was created, and what object does the injected reference actually point to?*

This is the foundation for understanding dependency injection, bean lifecycles, AOP, transactions, caching, and the conditional behaviors of the Spring IoC container.

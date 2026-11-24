# @EnableAspectJAutoProxy vs. Spring Boot Auto-Configuration

In a Spring Boot application, some behaviors must apply across many services without being copied into every method: logging processing time, recording metrics, tracing calls, enforcing a shared rule, or placing monitoring at service boundaries. **Aspect-Oriented Programming (AOP)** helps separate these *cross-cutting concerns* from business logic.

When learning Spring AOP, developers often encounter the `@EnableAspectJAutoProxy` annotation. Yet in a Spring Boot application with `spring-boot-starter-aop`, many `@Aspect` examples work **without placing that annotation anywhere**.

These are not two completely separate AOP systems. Spring Boot normally auto-configures **proxy-based Spring AOP** infrastructure when the required dependencies are present. `@EnableAspectJAutoProxy` is Spring Framework's way of letting you explicitly enable the infrastructure that processes aspects written in `@AspectJ` syntax. Therefore, the difference is primarily **who registers the AOP infrastructure, when it is activated, and how proxy settings are chosen**, not a difference in advice semantics.

This lesson explains:

- Why `@Aspect` in Spring Boot can work without `@EnableAspectJAutoProxy`.
- What the Spring Framework annotation does and when to declare it explicitly.
- The roles of `spring-boot-starter-aop`, `spring.aop.auto`, and `spring.aop.proxy-target-class`.
- Differences between JDK and CGLIB proxies.
- Limitations of proxy-based AOP, especially **self-invocation**.
- How to enable, disable, test, and diagnose aspects in a Spring Boot project.

## 1. First: what problem does Spring AOP solve?

Suppose an order service and many other methods all need execution timing:

~~~java
@Service
public class OrderService {

    public String placeOrder(String customerId) {
        long start = System.nanoTime();
        try {
            // Order creation logic...
            return "order-created-for-" + customerId;
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println("Time: " + elapsed);
        }
    }
}
~~~

If every service copies the timing block, business code mixes with system observation logic. Changing how logs work, controlling which rules apply, and avoiding missed methods all become hard.

With Spring AOP, we can define an **aspect**:

~~~java
@Aspect
@Component
public class TimingAspect {

    @Around("execution(* com.example.orders..*Service.*(..))")
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println(
                    joinPoint.getSignature() + " took " + elapsed + " ns"
            );
        }
    }
}
~~~

Spring can wrap matching service beans in a **proxy**. When a caller invokes through the proxy, advice runs before/after the business call.

~~~text
Consumer / Controller
        |
        v
   Spring AOP proxy
        |
        +--> TimingAspect (@Around)
        |         |
        |         v
        |     target method
        |         |
        +<--------+
        |
        v
     Result
~~~

Key point: regular Spring AOP **does not rewrite the bytecode of every call in the program**. It uses proxy objects at bean boundaries. This is the source of many limitations and configuration mistakes analyzed in later sections.

## 2. Core terminology

| Term | Meaning in Spring AOP |
| --- | --- |
| **Aspect** | Module grouping one or more advices and pointcut rules |
| **Advice** | Logic running at a designated point, e.g., before or around a method |
| **Join point** | Execution point that can be affected; Spring AOP primarily supports method execution |
| **Pointcut** | Expression determining which methods get advice applied |
| **Target** | Business object invoked by the proxy |
| **Proxy** | Intermediary object created by Spring to apply advice |
| **Weaving** | Concept of connecting aspects with the program; proxy-based Spring AOP differs from AspectJ bytecode weaving |
| **Auto-configuration** | Spring Boot mechanism conditionally registering configuration based on classpath, properties, and existing beans |

Example:

~~~java
@Around("execution(* com.example.orders..*Service.*(..))")
~~~

This is an **around** advice and a pointcut expression using the `execution` designator.

`joinPoint.proceed()` inside advice is the call allowing the next step in the chain to execute, eventually reaching the target method. If an `@Around` advice skips calling `proceed()`, the target may not run; this is powerful, yet must be intentional.

## 3. @EnableAspectJAutoProxy is a Spring Framework annotation

The annotation:

~~~java
import org.springframework.context.annotation.EnableAspectJAutoProxy;
~~~

belongs to **Spring Framework**, not Spring Boot.

Example:

~~~java
@Configuration
@EnableAspectJAutoProxy
public class AopConfiguration {
}
~~~

Meaning: instructs Spring to register appropriate auto-proxy infrastructure to recognize `@AspectJ`-style aspects and create proxies for Spring beans matching pointcuts.

A plain Framework configuration might include:

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.orders")
public class ApplicationConfiguration {
}
~~~

When creating an `AnnotationConfigApplicationContext` with this configuration, Spring has what it needs to register aspect beans and proxy target beans.

### 3.1. @EnableAspectJAutoProxy does not register aspects on its own

The annotation only activates the AOP mechanism. It **does not replace component scanning** and does not automatically turn every class carrying `@Aspect` into a bean.

For Spring to discover an aspect, you can use:

~~~java
@Aspect
@Component
public class TimingAspect {
    // ...
}
~~~

and ensure the class's package is within scan scope.

Or register the aspect via `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
public class TimingAspectConfiguration {

    @Bean
    TimingAspect timingAspect() {
        return new TimingAspect();
    }
}
~~~

In this case, `TimingAspect` still needs `@Aspect`, though it does not strictly need `@Component` because a factory method creates the bean.

**Remember the two separate steps:** having auto-proxy infrastructure and having aspect beans registered. Missing either one prevents advice from running.

### 3.2. Two common attributes

`@EnableAspectJAutoProxy` has important attributes:

~~~java
@EnableAspectJAutoProxy(
        proxyTargetClass = true,
        exposeProxy = false
)
~~~

- `proxyTargetClass`: whether to prefer class-based proxies over JDK interface proxies.
- `exposeProxy`: whether to allow retrieving the current proxy via `AopContext.currentProxy()`.

When `@EnableAspectJAutoProxy` is used on its own, `proxyTargetClass` defaults to `false` and `exposeProxy` defaults to `false`.

However, in an application with **multiple sources of auto-proxy configuration**, the final choice can be influenced by other settings. In particular, Spring Boot defaults toward class-based proxies. Do not assume adding `@EnableAspectJAutoProxy(proxyTargetClass = false)` alone forces an entire Boot application onto JDK proxies.

## 4. What does Spring Boot do differently?

Spring Boot provides AOP auto-configuration through `spring-boot-autoconfigure`, typically `AopAutoConfiguration`.

When the required AspectJ/Spring AOP dependencies are on the classpath, auto-configuration is not disabled, and conditions match, Boot registers the infrastructure needed for `@Aspect`-style aspects to work.

Therefore, in Spring Boot you normally only need:

1. Appropriate AOP dependency.
2. Register an aspect bean.
3. Register a target bean.
4. Call the target bean through a Spring-managed proxy.

You do not need to add `@EnableAspectJAutoProxy` in ordinary cases.

Main class example:

~~~java
@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Aspect:

~~~java
@Aspect
@Component
public class TimingAspect {

    @Before("execution(* com.example.orders..*Service.placeOrder(..))")
    public void beforePlaceOrder() {
        System.out.println("Before placeOrder");
    }
}
~~~

Service:

~~~java
@Service
public class DefaultOrderService {

    public String placeOrder(String customerId) {
        return "created-for-" + customerId;
    }
}
~~~

If `spring-boot-starter-aop` is in the dependency graph and package scanning covers them, Boot usually enables Spring AOP infrastructure automatically. No need to write:

~~~java
@EnableAspectJAutoProxy
~~~

on the main class.

### 4.1. Spring Boot does not invent advice for arbitrary logic

Auto-configuration only prepares the infrastructure. It cannot guess which methods you want to time or log.

You still must provide an aspect (or use features provided by other modules), meaningful pointcuts, and advice.

### 4.2. Auto-configuration is conditional

If required modules are absent from the classpath, Boot may not enable `@AspectJ` support as expected. If a property disables AOP auto-configuration, Boot will not register that infrastructure via auto-configuration either.

Thus, when an aspect does not run, check **dependencies**, **bean registration**, **auto-configuration**, and **proxied call paths** before blaming the pointcut.

## 5. Dependencies: what does spring-boot-starter-aop include?

For a Spring Boot app using Maven, add the dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
~~~

The starter brings in the pieces required for Spring AOP proxies and parsing AspectJ-style pointcut expressions, including Spring AOP and AspectJ Weaver in the dependency graph.

Points to distinguish:

- **Spring AOP** provides proxies, interceptors, and integration with the Spring bean lifecycle.
- **AspectJ annotations/pointcut parser** lets you write `@Aspect`, `@Around`, `@Before`, and matching pointcut expressions.
- **AspectJ Weaver dependency** can be present to support syntax and types needed by Spring AOP, yet that **does not mean** the application performs compile-time weaving or load-time weaving.

In a plain Framework app not using Boot starters, you must ensure `spring-aop` and the relevant AspectJ libraries are included in the project. `@EnableAspectJAutoProxy` is an annotation; it does not download Maven/Gradle dependencies by itself.

### 5.1. No need to add the same dependency multiple times

If another starter already pulls `spring-boot-starter-aop` or equivalent modules onto the classpath, duplicating it is unnecessary. However, when a project uses AOP directly, declaring the starter explicitly makes the dependency intent clearer.

### 5.2. Do not confuse with aspectj-maven-plugin or a javaagent

Proxy-based Spring AOP does not require compile-time weaving. If a project uses `aspectj-maven-plugin`, `ajc`, or a Java agent for AspectJ weaving, that is a different mechanism from Spring Boot's AOP starter default.

## 6. Two configuration paths: direct comparison

### 6.1. Configuring with Spring Framework

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.orders")
public class FrameworkAopConfiguration {
}
~~~

The application or library explicitly enables auto-proxy infrastructure. This fits Spring Framework apps that do not rely on Boot auto-configuration or custom contexts.

### 6.2. Configuring with Spring Boot

~~~java
@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Combined with dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
~~~

Boot enables AOP via auto-configuration when conditions match.

### 6.3. Comparison table

| Question | `@EnableAspectJAutoProxy` | Spring Boot AOP auto-configuration |
| --- | --- | --- |
| Belongs to | Spring Framework | Spring Boot |
| How it enables | Explicit annotation placement | Dependency and matching auto-config conditions |
| Must write activation annotation? | Yes, if using this configuration path | Usually no |
| Auto-scans aspects? | Does not replace scanning | Does not replace scanning |
| Requires aspect beans? | Yes | Yes |
| Uses Spring AOP proxies? | Yes | Yes |
| Auto-enables AspectJ bytecode weaving? | No | No |
| How proxy type is chosen | `proxyTargetClass` | `spring.aop.proxy-target-class` and other auto-proxy configs |
| Own default proxyTargetClass value | `false` | `true` in standard Boot configs |
| How to disable automatically | Remove annotation/adjust related config | `spring.aop.auto=false` |
| Best suited for | Plain Spring Framework, explicitly controlled contexts | Most Spring Boot apps with AOP starter |

Both paths can appear together in an application, though it is usually unnecessary. When both configure auto-proxy infrastructure, evaluate the final outcome across the entire context configuration, not a single annotation in isolation.

## 7. Key Spring Boot AOP properties

Spring Boot has two most commonly asked-about properties:

~~~properties
spring.aop.auto=true
spring.aop.proxy-target-class=true
~~~

### 7.1. spring.aop.auto

The property:

~~~properties
spring.aop.auto=true
~~~

controls whether Spring Boot auto-configures Spring AOP infrastructure when required dependencies/conditions are present.

The default in typical Boot apps is enabled when the classpath matches.

To disable AOP along **Boot's auto-configuration path**:

~~~properties
spring.aop.auto=false
~~~

Crucial point: if the application **explicitly declares** `@EnableAspectJAutoProxy` in another configuration, `spring.aop.auto=false` cannot be treated as an absolute master switch "forbidding all AOP proxies." It turns off Boot's auto-configuration path; an explicit Spring Framework configuration can still register AOP infrastructure.

Similarly, specialized proxy mechanisms like transactions or method security have their own lifecycles/activators; `spring.aop.auto=false` must not be interpreted as "disabling every proxy in Spring."

### 7.2. spring.aop.proxy-target-class

Spring Boot typically defaults to **class-based proxies**:

~~~properties
spring.aop.proxy-target-class=true
~~~

To prefer JDK dynamic proxies when targets have interfaces:

~~~properties
spring.aop.proxy-target-class=false
~~~

Note: setting `false` does not guarantee every bean is a JDK proxy. If a target does not provide a suitable interface, Spring AOP may still have to use a class-based proxy.

### 7.3. Equivalent application.yml

~~~yaml
spring:
  aop:
    auto: true
    proxy-target-class: false
~~~

YAML is simply another property format. Properties can be overridden by environment variables, command-line arguments, or profile-specific configs per Spring Boot's property precedence order.

### 7.4. Practical behavior matrix

| AOP dependency | `spring.aop.auto` | Explicit `@EnableAspectJAutoProxy` | Expectation |
| --- | --- | --- | --- |
| Present | Default/enabled | No | Boot usually auto-configures AOP |
| Present | Disabled | No | Boot does not auto-enable `@AspectJ` infrastructure via AopAutoConfiguration |
| Present | Disabled | Yes | Explicit Spring Framework config can still enable `@AspectJ` proxying |
| Insufficient | Enabled | No | Missing classpath may prevent auto-config from applying |
| Insufficient | Disabled | Yes | Annotation does not supply missing dependencies; context may fail |

The matrix focuses on `@AspectJ`-style aspect infrastructure. Features such as transaction advice may be provided by other configurations and require separate evaluation.

## 8. Does Spring AOP create proxies with JDK or CGLIB?

A proxy is an object standing between the caller and target. Spring has two common mechanisms:

**JDK dynamic proxy**: proxy implements suitable interfaces of the target.

**CGLIB class-based proxy**: proxy is based on subclassing the target class (when class and methods permit).

Contract example:

~~~java
public interface OrderService {
    String placeOrder(String customerId);
}
~~~

Implementation:

~~~java
@Service
public class DefaultOrderService implements OrderService {

    @Override
    public String placeOrder(String customerId) {
        return "order-created-for-" + customerId;
    }
}
~~~

Both JDK and class-based proxies can be used under suitable conditions, yet the characteristics of the injected object differ.

### 8.1. When using JDK dynamic proxies

If the bean is JDK-proxied, the proxy object implements `OrderService`. Injection by interface works:

~~~java
@Service
public class CheckoutService {

    private final OrderService orderService;

    public CheckoutService(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

However, trying to inject `DefaultOrderService` directly can fail because the JDK proxy is not necessarily an instance of the implementation class.

### 8.2. When using class-based proxies

With class-based proxies, the object is typically a proxy subclass of `DefaultOrderService`. This can allow injection by implementation type, though interface-based design remains generally preferable.

Spring Boot defaults to class-based proxies for AOP via Boot's property. Do not assume a Boot app with an interface definitely uses JDK proxies.

### 8.3. Final classes and final methods

CGLIB relies on subclassing/overriding methods. Therefore:

- A `final` class cannot be subclassed this way.
- A `final` method cannot be overridden to intercept calls via class-based proxies.
- A `private` method cannot be overridden by a subclass.
- A `static` method is not an instance method intercepted through a proxy like normal target methods.

If AOP is needed on a `final` class that has an interface, an interface-based JDK proxy may fit methods exposed through the interface.

If a method falls outside proxiable/interceptable scope, even a matching pointcut name will not run advice for that call.

### 8.4. Selection table

| Characteristic | JDK proxy | CGLIB proxy |
| --- | --- | --- |
| Interface dependency | Usually requires suitable interface | Can proxy classes without interfaces |
| Form | Proxy implements interface | Subclass proxy |
| Inject by interface | Suitable | Suitable if class implements interface |
| Inject by concrete class | May not fit | Usually fits if target is proxiable |
| `final` target class | Usable via interface | Cannot subclass |
| Intercept `final` method via subclass | Not applicable via this mechanism | Cannot intercept |
| Related Boot property | `spring.aop.proxy-target-class=false` | `spring.aop.proxy-target-class=true` |

Limitations also depend on method accessibility, class design, and Spring version. For application AOP, the safe approach is placing advice on proxiable instance methods invoked through Spring beans.

## 9. Why might @EnableAspectJAutoProxy(proxyTargetClass=false) fail to change Boot's proxy?

Suppose a Boot project has:

~~~java
@SpringBootApplication
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class Application {
}
~~~

And in Boot's default configuration:

~~~properties
spring.aop.proxy-target-class=true
~~~

Both sources participate in configuring auto-proxy infrastructure. Spring merges/escalates auto-proxy creator settings. When one source requests stronger class proxying, setting `proxyTargetClass=false` elsewhere does not necessarily "undo" that selection.

Therefore, if the goal is JDK proxies in a Boot app, control Boot's property explicitly:

~~~properties
spring.aop.proxy-target-class=false
~~~

Then verify via API rather than guessing:

~~~java
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
~~~

If the application still has another configuration requesting class-based proxies, locate that configuration source. Do not stack conflicting annotations assuming the last-declared one wins.

## 10. Spring Boot example working without @EnableAspectJAutoProxy

Suppose the package structure is:

~~~text
src/main/java/com/example/orders/
├── OrderApplication.java
├── OrderService.java
├── DefaultOrderService.java
├── OrderController.java
└── LoggingAspect.java
~~~

### 10.1. Dependency

In a Spring Boot project with the appropriate parent/BOM, add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

No `@EnableAspectJAutoProxy` needed.

### 10.2. Application

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 10.3. Service contract

~~~java
package com.example.orders;

public interface OrderService {
    String placeOrder(String customerId);
}
~~~

### 10.4. Service implementation

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class DefaultOrderService implements OrderService {

    @Override
    public String placeOrder(String customerId) {
        return "order-created-for-" + customerId;
    }
}
~~~

### 10.5. Logging aspect

~~~java
package com.example.orders;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LoggingAspect {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingAspect.class);

    @Around("execution(* com.example.orders..*OrderService.placeOrder(..))")
    public Object logDuration(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long durationNanos =
                    System.nanoTime() - start;

            log.info(
                    "Method {} completed in {} ns",
                    joinPoint.getSignature().toShortString(),
                    durationNanos
            );
        }
    }
}
~~~

Here `@Around` attaches to calls to `placeOrder` on implementations whose name ends with `OrderService`. Since target class `DefaultOrderService` matches the pattern and is a Spring bean, advice applies when the method is called through the proxy.

In production, consider an appropriate metrics/tracing library, avoid logging sensitive data, and weigh logging verbosity against per-request overhead.

### 10.6. Controller calling service through the container

~~~java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/demo/order")
    public String createOrder(
            @RequestParam String customerId) {
        return orderService.placeOrder(customerId);
    }
}
~~~

You can run the application and call:

~~~bash
curl "http://localhost:8080/demo/order?customerId=abc"
~~~

The controller receives `OrderService` from Spring, so calls pass through the proxied bean. The aspect is registered via `@Component`, lies within component scan scope, and is automatically picked up by Boot's AOP infrastructure.

### 10.7. Execution flow

~~~text
GET /demo/order
       |
       v
OrderController
       |
       v
OrderService proxy
       |
       v
LoggingAspect.logDuration()
       |
       v
DefaultOrderService.placeOrder()
       |
       v
Return result; advice logs duration
       |
       v
HTTP response
~~~

**There is no `@EnableAspectJAutoProxy` on the main class.** When the starter and auto-configuration are active, this is normal Spring Boot behavior.

## 11. Same example, if you want to enable explicitly with @EnableAspectJAutoProxy

If you are not using auto-configuration to enable AOP or are experimenting with plain Spring Framework, you can declare it explicitly:

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.orders")
public class ManualAopConfiguration {
}
~~~

Or in a Boot application requiring specific configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(
        proxyTargetClass = true,
        exposeProxy = false
)
public class ExplicitAopConfiguration {
}
~~~

Yet in a Boot application that already has `spring-boot-starter-aop` and AOP auto-configuration, this annotation is normally **unnecessary**.

If you use it to tune proxy strategy, understand how `proxyTargetClass` interacts with Boot properties. If you only want to switch from class proxies to JDK proxies in a Boot app, `spring.aop.proxy-target-class=false` is usually clearer and more consistent.

### 11.1. Do not add the annotation "just in case"

A configuration having both:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = false)
~~~

and:

~~~properties
spring.aop.proxy-target-class=true
~~~

confuses readers. When a project uses auto-configuration, prefer Boot's extension/configuration points unless there is a clear technical reason to enable it manually.

### 11.2. Plain Spring Framework really differs at the bootstrap step

Example without `SpringApplication`:

~~~java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                     ManualAopConfiguration.class
             )) {

    OrderService service = context.getBean(OrderService.class);
    System.out.println(service.placeOrder("customer-1"));
}
~~~

Here there is no Spring Boot auto-configuration unless you explicitly import it. `@EnableAspectJAutoProxy` is the clear way to enable `@AspectJ`-style aspect processing in a context you construct yourself.

## 12. The most important limitation: self-invocation

Spring AOP is proxy-based, so calls are intercepted by advice only when they go **through the proxy**.

Look at this service:

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        validateOrder();
        // Save order...
    }

    public void validateOrder() {
        // Validate data...
    }
}
~~~

Suppose an aspect has a pointcut targeting only `validateOrder()`.

If a controller calls:

~~~java
orderService.validateOrder();
~~~

through the bean proxy, advice can run.

However, inside `placeOrder()`, the call:

~~~java
validateOrder();
~~~

is equivalent to `this.validateOrder()` on the target. This internal call usually **does not pass through the proxy**, so `validateOrder()`'s advice does not run on that call path.

~~~text
Controller -> proxy -> target.placeOrder()
                            |
                            +--> this.validateOrder()
                                 (bypasses proxy)
~~~

### 12.1. Why doesn't adding @EnableAspectJAutoProxy fix it?

Because the issue is not a missing AOP-activation annotation, but **the call path**. Even when the proxy is created properly, a target calling its own method via `this` still bypasses the proxy.

Similarly, switching to `spring.aop.proxy-target-class=true` does not turn self-invocation into proxied calls.

### 12.2. Preferred solution: extract responsibilities to another bean

~~~java
@Service
public class OrderValidator {

    public void validate(String orderId) {
        // Validate order...
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final OrderValidator validator;

    public OrderService(OrderValidator validator) {
        this.validator = validator;
    }

    public void placeOrder(String orderId) {
        validator.validate(orderId);
        // Save order...
    }
}
~~~

When `OrderValidator` is a Spring-proxied bean and `OrderService` injects it from the context, `validator.validate(orderId)` passes through the proxy and triggers advice.

This design is easy to read and minimizes dependence on AOP infrastructure in business logic.

### 12.3. Alternative: intentional call via self-proxy

In certain situations, a service can inject a proxy of its own type via a carefully designed abstraction/lazy provider. However, this approach easily causes circular dependencies or lifecycle complexity.

Do not treat self-injection as the default path when the intercepted method can be extracted into a dedicated bean.

## 13. exposeProxy and AopContext.currentProxy()

`@EnableAspectJAutoProxy` offers the option:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

When the current proxy is exposed, a method currently invoked through a Spring AOP proxy can access that proxy via:

~~~java
AopContext.currentProxy()
~~~

Example:

~~~java
public interface OrderOperations {
    void placeOrder(String id);
    void validateOrder(String id);
}
~~~

~~~java
@Service
public class DefaultOrderOperations implements OrderOperations {

    @Override
    public void placeOrder(String id) {
        ((OrderOperations) AopContext.currentProxy())
                .validateOrder(id);
    }

    @Override
    public void validateOrder(String id) {
        // ...
    }
}
~~~

The example is valid only when:

- `exposeProxy=true` is enabled for the corresponding proxy.
- The initial call into `placeOrder` actually passed through a Spring AOP proxy.
- A current proxy exists in the execution context.
- The cast matches the proxy type (especially with JDK proxies, cast to the interface).

If no exposed proxy exists, `AopContext.currentProxy()` can throw `IllegalStateException`.

### 13.1. Why is this not the preferred design choice?

- Business logic becomes dependent on Spring AOP APIs.
- Calls require proxy exposure, adding runtime overhead and preconditions.
- Current-context propagation is typically bound to the executing thread.
- Usage from async tasks or other threads must not rely on the current proxy.
- Code is harder to test in isolation without constructing a Spring proxy context.

Therefore, whenever possible, extract the advised behavior into another bean. `exposeProxy` is a specialized tool for difficult situations, not an automatic cure for every self-invocation.

### 13.2. Is there a spring.aop.expose-proxy property?

The common properties supported by Spring Boot to control AOP infrastructure here are `spring.aop.auto` and `spring.aop.proxy-target-class`. Do not assume every attribute of `@EnableAspectJAutoProxy` has a matching Boot property.

If a project genuinely needs `exposeProxy`, configure it explicitly via the appropriate API and verify interactions with existing proxy infrastructure.

## 14. @Aspect does not mean AspectJ weaving

The name `@EnableAspectJAutoProxy` easily leads newcomers to assume this annotation enables full AspectJ capabilities.

Distinguish:

**Spring AOP in `@AspectJ` style:**

- Uses `@Aspect` annotations and AspectJ-style pointcut expressions.
- Advice applies via Spring-managed proxies.
- Primarily intercepts method execution on Spring-managed beans.
- Does not rewrite all calls in bytecode.

**Full AspectJ weaving:**

- Can weave aspects into bytecode at compile time or load time using appropriate weaving mechanisms.
- Supports more join point kinds than Spring AOP, such as object construction or field access per AspectJ features.
- Requires different build/runtime setup (compiler/weaver, agent, or suitable integration).

Adding `@EnableAspectJAutoProxy` **does not automatically enable AspectJ compile-time weaving or load-time weaving**.

### 14.1. Do not expect Spring AOP to intercept constructors/fields like method execution

A common Spring AOP pointcut expression is:

~~~java
execution(* com.example.orders..*Service.*(..))
~~~

This binds to method execution. If you need to intercept `new` instantiation, field gets/sets, or join points unsupported by Spring AOP, consider AspectJ weaving or a different design.

### 14.2. Spring bean boundary

A directly instantiated object:

~~~java
OrderService service = new OrderService();
service.placeOrder();
~~~

does not become a Spring AOP proxy simply because the class has `@Service` or the package contains an `@Aspect`.

To receive Spring AOP advice, obtain the service from the Spring container or use an appropriate explicit proxy-creation mechanism.

### 14.3. Do not adopt weaving solely to "patch" a simple self-invocation design

Weaving can overcome some proxy-based AOP limits, yet complicates builds, deployment, and debugging. First check whether logic can be split into clean beans called through proxies in standard Spring style.

## 15. Which methods are hard or impossible for advice to intercept?

In proxy-based Spring AOP, cases requiring attention include:

- **Private methods**: cannot be intercepted via normal proxy overriding.
- **Final methods** with class-based proxies: cannot be overridden, so cannot be intercepted via a CGLIB subclass that way.
- **Final classes**: cannot be subclassed for CGLIB proxies.
- **Static methods**: do not go through instance proxies like bean method calls.
- **Self-invocation**: calling `this.someMethod()` inside the target usually bypasses the proxy.
- **Objects created with `new`**: not managed by Spring, so not proxied automatically.
- **Methods outside interfaces with JDK proxies**: cannot be called via the JDK proxy as methods absent from the interface.
- **Wrong component scan scope**: aspect or target bean is not registered.
- **Pointcut mismatch**: the method may be proxied, yet the specific advice still does not apply.

Not every "AOP is not running" issue is caused by missing `@EnableAspectJAutoProxy`.

## 16. Is @Configuration(proxyBeanMethods=false) related?

Another common point of confusion:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {
}
~~~

`@Configuration`'s `proxyBeanMethods` attribute controls whether Spring uses class enhancement to intercept `@Bean` method calls inside configuration classes to preserve bean container semantics.

It is **not** a property toggling AOP advice for all services.

For instance:

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfiguration {
}
~~~

does not disable `LoggingAspect`'s advice on `OrderService` when the application's AOP infrastructure is active.

The same word "proxy" is used at multiple Spring layers, though not always with the same mechanism or purpose.

## 17. Do @Transactional, @Async, and @Cacheable directly depend on @EnableAspectJAutoProxy?

These features often rely on proxies as well, yet each has **its own activation infrastructure**.

Examples:

~~~java
@Transactional
public void transferMoney() {
    // ...
}
~~~

~~~java
@Async
public void sendMessage() {
    // ...
}
~~~

~~~java
@Cacheable("catalog")
public Product findProduct(String id) {
    // ...
}
~~~

Points to distinguish:

- Transaction management is normally enabled/configured via Spring's transaction infrastructure and related Boot auto-configuration.
- `@Async` requires async infrastructure, typically `@EnableAsync` or suitable configuration; merely having the AOP starter does not make `@Async` work automatically.
- Cache abstraction requires caching enabled via `@EnableCaching` and a suitable cache manager; Boot can auto-configure a cache manager, yet distinguish that from activating caching advice.
- Method security has its own configuration, such as `@EnableMethodSecurity` in modern Spring Security applications.

Adding `@EnableAspectJAutoProxy` **does not automatically enable** transactions, async, caching, and security.

### 17.1. Why does self-invocation still matter?

Although each feature has its own activator, when its implementation uses Spring proxies, internal `this.method()` calls face the same proxy-bypass issue.

Example:

~~~java
@Service
public class BillingService {

    public void process() {
        saveInvoice(); // Internal call can bypass transaction proxy.
    }

    @Transactional
    public void saveInvoice() {
        // ...
    }
}
~~~

When `process()` calls `saveInvoice()` via `this`, transaction advice may not trigger for that internal call. Do not add `@EnableAspectJAutoProxy` expecting the problem to vanish; design bean and transaction boundaries properly.

### 17.2. Proxy creators can be shared across features

Spring can combine multiple advisors from AOP, transactions, and other modules onto the same proxy. Infrastructure-level `proxyTargetClass` configuration can have broader effects than a single aspect. Therefore, verify proxy strategy changes at application scope, not just on one service.

## 18. Ordering when multiple aspects exist

If two aspects match the same method, execution order can matter.

For example, a logging aspect and a metrics aspect:

~~~java
@Aspect
@Component
@Order(10)
public class LoggingAspect {
    // Logging advice.
}
~~~

~~~java
@Aspect
@Component
@Order(20)
public class MetricsAspect {
    // Metrics advice.
}
~~~

Under Spring's normal precedence order, smaller order values have higher precedence.

For around advice, higher-precedence aspects normally run **first on entry** and **last on exit** in a nested wrapper pattern:

~~~text
LoggingAspect (order 10) before
    MetricsAspect (order 20) before
        Target method
    MetricsAspect after
LoggingAspect after
~~~

When aspects interact with transaction or caching advisors, account for the order of those other advisors beyond user-defined aspects.

### 18.1. Do not use order to fix a non-matching pointcut

If an advice does not run due to self-invocation or an unproxied bean, adding `@Order` will not make it appear. Ordering matters only after advisors/pointcuts actually apply.

### 18.2. Do not rely on undeclared ordering

If execution order matters for correctness, declare an explicit policy and test it, rather than relying on class scan order or Java file naming.

## 19. Inspecting proxies with AopUtils

When diagnosing, you can query the bean object:

~~~java
import org.springframework.aop.support.AopUtils;
~~~

Example:

~~~java
@Component
public class ProxyReporter implements ApplicationRunner {

    private final OrderService orderService;

    public ProxyReporter(OrderService orderService) {
        this.orderService = orderService;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "isAopProxy: "
                        + AopUtils.isAopProxy(orderService)
        );

        System.out.println(
                "isJdkDynamicProxy: "
                        + AopUtils.isJdkDynamicProxy(orderService)
        );

        System.out.println(
                "isCglibProxy: "
                        + AopUtils.isCglibProxy(orderService)
        );

        System.out.println(
                "targetClass: "
                        + AopUtils.getTargetClass(orderService).getName()
        );
    }
}
~~~

If `isAopProxy` returns `false`, that bean is not a Spring AOP proxy under the check. This **does not automatically** prove AOP infrastructure is off: perhaps no advisor applies to that bean, or you are inspecting a non-proxy object.

If `isAopProxy` returns `true` yet advice does not run for a specific method, inspect the pointcut, visibility, final methods, self-invocation, and call path.

### 19.1. Do not use getClass() to guess the original type

A proxy can have a dynamically generated class with a different name from the target. `orderService.getClass()` is not necessarily `DefaultOrderService.class`.

When you need the target class during diagnostics, `AopUtils.getTargetClass(bean)` is usually more helpful.

### 19.2. Distinguish proxy presence from pointcut matching

A bean can have a proxy due to transactions or another advisor while your logging aspect fails to match the method. Seeing a proxy exist is therefore insufficient to prove the inspected advice runs.

Observe actual calls or write tests counting how many times the advice triggers.

## 20. Testing aspects in a Spring Boot context

A meaningful AOP test must call the method **through the bean proxy**, rather than calling aspect methods directly in plain Java.

### 20.1. Aspect using a counter for testing

Example aspect counting calls:

~~~java
package com.example.orders;

import java.util.concurrent.atomic.AtomicInteger;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InvocationCountAspect {

    private final AtomicInteger invocations =
            new AtomicInteger();

    @Before("execution(* com.example.orders..*OrderService.placeOrder(..))")
    public void count(JoinPoint joinPoint) {
        invocations.incrementAndGet();
    }

    public int count() {
        return invocations.get();
    }
}
~~~

`AtomicInteger` allows safely incrementing the counter when methods are called concurrently. This is an illustration tool for tests; in production systems, an appropriate metrics library is usually better than keeping a counter inside a singleton aspect.

### 20.2. Testing with @SpringBootTest

~~~java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.aop.support.AopUtils;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AopIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private InvocationCountAspect aspect;

    @Test
    void callsAspectAroundProxiedBean() {
        assertThat(AopUtils.isAopProxy(orderService)).isTrue();

        int before = aspect.count();

        orderService.placeOrder("customer-123");

        assertThat(aspect.count()).isEqualTo(before + 1);
    }
}
~~~

The test requires Spring Boot test dependencies, the aspect on the classpath, and matching configuration/component scanning. In a large test suite, if a singleton counter is mutated concurrently by multiple tests, isolate contexts/fixtures or use a suitable measurement strategy to avoid flaky tests.

### 20.3. Verifying proxy type when changing properties

With Boot defaults:

~~~properties
spring.aop.proxy-target-class=true
~~~

you can check:

~~~java
assertThat(AopUtils.isCglibProxy(orderService)).isTrue();
~~~

When using JDK proxies:

~~~properties
spring.aop.proxy-target-class=false
~~~

if the target has a suitable interface and no other config forces class proxies, you can check:

~~~java
assertThat(AopUtils.isJdkDynamicProxy(orderService)).isTrue();
~~~

Be aware that tests might observe proxies created by other advisors; pick a simple, controllable bean for tests.

### 20.4. Testing when AOP auto-configuration is disabled

You can use a test context enabling only:

~~~properties
spring.aop.auto=false
~~~

with no explicit `@EnableAspectJAutoProxy` configuration. Under suitable conditions, the aspect bean may still exist in the context while methods are not proxied by Boot's auto-configured `@AspectJ` infrastructure.

If the test still shows a proxy, check other infrastructure such as transactions or an explicit auto-proxy configuration. Do not immediately conclude the property was ignored.

## 21. Testing with plain Spring Framework

To isolate Framework behavior from Boot, you can build a small context explicitly enabling AOP:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class ManualAopTestConfiguration {

    @Bean
    OrderService orderService() {
        return new DefaultOrderService();
    }

    @Bean
    InvocationCountAspect invocationCountAspect() {
        return new InvocationCountAspect();
    }
}
~~~

Then create the context:

~~~java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(
                     ManualAopTestConfiguration.class
             )) {

    OrderService service = context.getBean(OrderService.class);

    assertThat(AopUtils.isAopProxy(service)).isTrue();

    service.placeOrder("customer-1");

    InvocationCountAspect aspect =
            context.getBean(InvocationCountAspect.class);

    assertThat(aspect.count()).isEqualTo(1);
}
~~~

This example assumes `DefaultOrderService` has a no-arg constructor and classes from earlier examples are placed in compatible packages/visibilities.

The test relies solely on a Spring application context you construct yourself. It illustrates that `@EnableAspectJAutoProxy` can be used without `SpringApplication` or Boot auto-configuration.

## 22. Debugging: where to look when an aspect does not run?

A logical diagnostic workflow:

### 22.1. Check dependencies

Does the project have `spring-boot-starter-aop` or at least the necessary Spring AOP and AspectJ modules?

Without them, `@Aspect` annotations may compile from a standalone dependency, yet auto-configuration infrastructure still will not work as expected.

### 22.2. Check auto-configuration

In Spring Boot:

~~~properties
spring.aop.auto=true
~~~

or omit the property to use the default when conditions match.

If `spring.aop.auto=false` appears in a profile, environment variable, or command line, Boot will not auto-enable `@AspectJ` infrastructure.

You can enable startup debug output:

~~~bash
java -jar application.jar --debug
~~~

Boot's condition evaluation report shows why `AopAutoConfiguration` did or did not apply. If Actuator's conditions endpoint is enabled and properly secured, it can also aid condition diagnostics.

### 22.3. Check whether the aspect is a bean

A class with only:

~~~java
@Aspect
public class TimingAspect {
}
~~~

does not guarantee component-scan registration. Add `@Component` or provide a `@Bean` and check package scanning.

### 22.4. Check whether the target is a bean

If calling:

~~~java
new DefaultOrderService().placeOrder("x");
~~~

that call bypasses the Spring proxy. Inject the container-managed bean instead.

### 22.5. Check the pointcut

For example:

~~~java
@Before("execution(* com.example.billing..*Service.*(..))")
~~~

does not match a service actually located in `com.example.orders`.

Cross-check package, class, method name, and parameters. An overly broad pointcut can intercept unintended methods; an overly narrow one may never run.

### 22.6. Check whether the call passes through the proxy

Use `AopUtils.isAopProxy(bean)`. If the proxy exists yet the call comes from another method in the same class, self-invocation may bypass advice.

### 22.7. Check whether the method can be intercepted

`final`, `private`, `static`, unmanaged targets, or non-interface methods under JDK proxies can all prevent interception.

### 22.8. Check for other proxy configurations

If JDK/CGLIB behaves unexpectedly, search for:

~~~text
spring.aop.proxy-target-class
@EnableAspectJAutoProxy
@EnableTransactionManagement
@EnableCaching
@EnableMethodSecurity
~~~

and other project-relevant proxy settings. Multiple Spring features can share or influence proxy infrastructure.

## 23. Common mistakes when comparing the two ways to enable AOP

### 23.1. Thinking Spring Boot must always have @EnableAspectJAutoProxy

Incorrect. With the AOP starter and matching auto-configuration conditions, Boot enables the needed mechanism automatically.

**Solution:** add the annotation only for specific configuration reasons or when working with plain Spring Framework/manual contexts.

### 23.2. Having @Aspect without @Component

The aspect class does not become a bean, so advice is not registered via component scanning.

**Solution:** add `@Component` or declare an aspect bean.

### 23.3. Adding @EnableAspectJAutoProxy without the dependency

The annotation does not supply the required runtime libraries.

**Solution:** add `spring-boot-starter-aop` in Boot or the corresponding Framework/AspectJ dependencies.

### 23.4. Setting proxyTargetClass=false yet still seeing CGLIB

Boot defaults may request class-based proxies; another feature may also enforce class proxies.

**Solution:** configure `spring.aop.proxy-target-class=false` consistently and inspect all sources of auto-proxy configuration.

### 23.5. Disabling spring.aop.auto=false yet still seeing proxies

The application may have an explicit `@EnableAspectJAutoProxy` or proxy infrastructure from transactions/caching/security.

**Solution:** distinguish Boot AOP auto-configuration from other proxy mechanisms, rather than treating this property as a system-wide switch.

### 23.6. Internal method calls do not run advice

**Cause:** self-invocation bypasses the proxy.

**Solution:** extract methods needing interception into another bean or consider intentional proxy exposure solutions.

### 23.7. Final classes or final methods are not intercepted

**Cause:** class-based proxies cannot subclass/override as required.

**Solution:** use proxiable classes/methods, or interface-based designs when appropriate; do not expect `proxyTargetClass=true` to overcome `final` limits.

### 23.8. Changing @Configuration(proxyBeanMethods=false) thinking it disables AOP

**Cause:** confusing `@Bean` configuration proxies with service Spring AOP proxies.

**Solution:** treat the two mechanisms as separate layers and inspect AOP with `AopUtils`.

### 23.9. Assuming having aspectjweaver means AspectJ weaving is running

**Cause:** confusing a dependency used for pointcut support with bytecode weaving configuration.

**Solution:** distinguish proxy-based Spring AOP from AspectJ compile-time/load-time weaving.

### 23.10. Using @Async or @Transactional while enabling only @EnableAspectJAutoProxy

Those annotations require their own respective infrastructure.

**Solution:** enable transactions/async/caching/security per each module's rules and check calls through proxies.

## 24. Workflow for choosing AOP configuration in real projects

When adopting AOP, follow this workflow:

1. **Identify the application type:** Spring Boot auto-configured or manually built Spring Framework context?
2. **Choose dependencies:** in Boot, typically `spring-boot-starter-aop`.
3. **Define aspect beans:** use `@Aspect` combined with `@Component` or `@Bean`.
4. **Pick narrow, clear pointcuts:** based on package, annotation, or suitable contract.
5. **Let Boot auto-configure unless special needs dictate otherwise:** avoid adding `@EnableAspectJAutoProxy` out of habit.
6. **If JDK proxies are needed, set the Boot property:** `spring.aop.proxy-target-class=false`, then verify at runtime.
7. **If special handling like exposeProxy is needed, weigh the design:** prefer extracting beans; enable manually only when needed.
8. **Do not rely on self-invocation:** advised methods must be called through proxies.
9. **Verify transactions/async/caching separately:** they have their own activation mechanisms and conditions.
10. **Write integration tests for advice:** invoke beans through the context, confirming advice actually runs.
11. **Inspect proxy types and conditions:** use `AopUtils` and condition reports when needed.
12. **Monitor overhead:** overly broad aspects or excessive logging can hurt latency and log volume.

Do not decide "do I need `@EnableAspectJAutoProxy`?" before knowing whether the app uses Spring Boot auto-configuration or a plain Spring Framework context. The bootstrap context dictates the right choice.

## 25. Practice exercises

### Exercise A: Boot AOP without @EnableAspectJAutoProxy

Create a Spring Boot project with `spring-boot-starter-aop`. Create:

~~~java
@Aspect
@Component
public class LogAspect {

    @Before("execution(* com.example.demo..*Service.work(..))")
    public void before() {
        System.out.println("AOP invoked");
    }
}
~~~

Create `DemoService.work()` and invoke it from a controller or runner via a bean injected from the context.

**Requirement:** confirm advice runs without placing `@EnableAspectJAutoProxy` on the main class.

### Exercise B: Disable Boot AOP auto-configuration

Add:

~~~properties
spring.aop.auto=false
~~~

Restart and observe aspect behavior. Explain why the `@Aspect` class can still be a bean while no longer having a corresponding advice proxy when no other activator exists.

### Exercise C: Enable manually with Spring Framework

Use:

~~~java
@Configuration
@EnableAspectJAutoProxy
@ComponentScan("com.example.demo")
class ManualConfig {
}
~~~

Create an `AnnotationConfigApplicationContext` and call the service. Compare behavior with Boot auto-configuration in Exercise A.

### Exercise D: Compare JDK proxies and CGLIB

Create a `GreetingService` interface and `DefaultGreetingService` implementation.

Try:

~~~properties
spring.aop.proxy-target-class=true
~~~

and:

~~~properties
spring.aop.proxy-target-class=false
~~~

Use:

~~~java
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
~~~

Record the proxy types and observe injecting by interface vs. concrete class.

### Exercise E: Reproduce self-invocation

Create a class where `outer()` calls `inner()` via `this`. Write advice matching only `inner()`.

Compare calling `outer()` with calling `inner()` directly from an external bean. Then extract `inner()` to a new bean and verify advice runs as expected.

### Exercise F: exposeProxy

Enable:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
~~~

Create a scenario calling through `AopContext.currentProxy()` inside a proxied call, then try calling the method using `new` to observe the difference.

Explain why this is a specialized mechanism that should not be overused in business services.

### Exercise G: Final methods

Create a class with a `final` method and an aspect matching it. Use a class-based proxy and observe the limitation. Switch to an overridable method and compare.

### Exercise H: Testing with @SpringBootTest

Write an aspect incrementing an `AtomicInteger` every time `placeOrder()` is called via a proxy. Use `@SpringBootTest` to assert the advice execution count after calling the service.

Do not call `aspect.count(...)` directly as a substitute for testing real AOP behavior.

### Exercise I: Distinguish from @Transactional

Create a service with `@Transactional` and an internally called method. Explain why self-invocation still matters and why adding `@EnableAspectJAutoProxy` does not replace transaction management configuration.

## 26. Self-check questions

**1. Does `@EnableAspectJAutoProxy` belong to Spring Framework or Spring Boot?**

It belongs to Spring Framework. It enables infrastructure for processing `@AspectJ`-style aspects using Spring AOP proxies.

**2. Why doesn't Spring Boot necessarily need that annotation?**

Because when appropriate AOP dependencies are present and auto-configuration conditions are met, Boot can register AOP infrastructure automatically.

**3. Which dependency is typically added to a Boot app to use Spring AOP?**

`spring-boot-starter-aop`.

**4. Does `spring.aop.auto=false` guarantee every proxy in the app disappears?**

No. It controls Boot's AOP auto-configuration path, not a switch disabling all proxy mechanisms registered by other modules or annotations.

**5. Does Spring Boot typically default to JDK or class-based proxies?**

In typical Boot AOP configurations, class-based proxies are preferred via `spring.aop.proxy-target-class=true`.

**6. Does standalone `@EnableAspectJAutoProxy` default to `proxyTargetClass=true`?**

No. The annotation's own default is `false`; however, in a context with multiple proxy configuration sources, the final outcome depends on the combined configuration.

**7. Does `@Aspect` automatically become a component-scanned bean?**

No. `@Component` or an appropriate bean registration method is required.

**8. Why doesn't `this.innerMethod()` typically run that method's advice?**

Because internal calls on the target bypass the Spring AOP proxy.

**9. Does `@EnableAspectJAutoProxy` activate full AspectJ bytecode weaving?**

No. It supports configuring proxy-based Spring AOP using `@AspectJ` syntax.

**10. Why can't CGLIB intercept final methods via subclass proxies?**

Because a subclass cannot override a `final` method.

**11. Can `@Order` fix a non-matching pointcut?**

No. Ordering only arranges advisors/advices once they already apply.

**12. What can check whether a bean is a JDK or CGLIB proxy?**

Methods such as `AopUtils.isJdkDynamicProxy(bean)` and `AopUtils.isCglibProxy(bean)`.

**13. Does `@Configuration(proxyBeanMethods=false)` turn off service AOP?**

No. It governs how enhancement handles `@Bean` methods inside configuration classes, not a toggle for service AOP.

**14. Does adding only `@EnableAspectJAutoProxy` automatically enable `@Async`, `@Cacheable`, and `@Transactional`?**

No. Each capability requires its own appropriate activation/infrastructure configuration.

**15. When should explicit `@EnableAspectJAutoProxy` be preferred?**

When working with manually configured Spring Framework contexts or when `@AspectJ` infrastructure is explicitly required without Boot's auto-configuration path.

## 27. Conclusion

`@EnableAspectJAutoProxy` and Spring Boot's automatic AOP configuration do not create two opposing AOP models. Both can lead to **proxy-based Spring AOP** running advice written with `@Aspect` and annotations like `@Before`, `@After`, and `@Around`.

The core difference lies in **the AOP activation mechanism**. In plain Spring Framework or manually built contexts, `@EnableAspectJAutoProxy` is the explicit configuration tool. In most Spring Boot applications with `spring-boot-starter-aop`, auto-configuration handles activating the infrastructure so you do not need to add the annotation just to make aspects work.

Remember three rules when implementing:

1. **Have the right dependencies and beans:** the AOP starter supplies infrastructure; `@Aspect` must still be registered as a Spring bean.
2. **Understand proxy creation:** Boot typically defaults to class-based; `spring.aop.proxy-target-class=false` prefers JDK proxies when suitable interfaces exist. Do not mix conflicting proxy settings without verifying.
3. **Calls must pass through the proxy:** self-invocation, `private`/`final` methods, objects created with `new`, and mismatched pointcuts can all keep advice from running.

When encountering AOP issues, do not reflexively add `@EnableAspectJAutoProxy`. Check in sequence: dependencies, Boot conditions, aspect bean, target bean, proxy type, pointcut, and call path. Understanding the clear boundary between **Spring Framework explicit configuration** and **Spring Boot auto-configuration** keeps code concise, avoids duplicate configuration, and uses AOP for its intended purpose.
